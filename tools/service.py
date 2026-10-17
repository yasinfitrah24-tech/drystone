r"""Drystone service: stack photo(s) -> decision (JSON). Runs on the laptop and on AWS Lambda.

Two modes:
- decide: 1-5 consecutive photos (more = steadier) + candidate position of the next box
  -> zone GREEN/YELLOW/RED, P(fall), reasoning trace, nearest safe suggestion, and "plans" to check later.
- check : photo(s) after the box is placed + one plan from decide -> OK / OFF_PLAN / FELL / NOT_PLACED.
Safety decisions are deterministic (drystone_core), not made by an LLM.

Laptop:
    python tools/service.py --images "data/agent_x/step_003_check.png" --offset-cm 12
    python tools/service.py --images "after.png" --check data/service_x/plan.json --plan suggested
AWS Lambda: handler = service.lambda_handler, JSON body:
    {"mode": "decide", "images": ["<base64 jpg/png>", ...], "offset_cm": 12, "box_id": 2}
    {"mode": "check",  "images": [...], "plan": {...}}
Judges' web page on the same Function URL (web/index.html, no photo upload):
    GET /                    the page
    GET /samples/<id>.jpg    sample photo listed in web/samples/samples.json
    POST {"sample": "s2", "offset_cm": 14}                         decision for a sample photo (cached)
    POST /log {"sample", "offset_cm", "choice", "name", "reason"}  approve / override etc., one JSON line
                                                                   in CloudWatch Logs; it never changes the decision
Limits: web JSON <= 16 KB, photo POST <= 2 MB (else 413); per IP and per container: 60 GET and 20 POST
per minute (else 429).
"""
import argparse
import base64
import glob
import json
import math
import os
import re
import sys
import time
from collections import deque

import cv2
import numpy as np

import common
import drystone_core as core
from agent import COLORS, draw_box, outlined, project_box, read_stack
from predict_test import detect_poses, load_catalog

ROOT = common.ROOT
CALIB = os.environ.get("DRYSTONE_CALIB", os.path.join(ROOT, "data", "camera_laptop.yaml"))
BOXES = os.environ.get("DRYSTONE_BOXES", os.path.join(ROOT, "config", "boxes.json"))
MARKER_MM = float(os.environ.get("DRYSTONE_MARKER_MM", "80"))
WEB_DIR = os.environ.get("DRYSTONE_WEB", os.path.join(ROOT, "web"))
BASE_ID = 0
MAX_IMAGES = 5


class _Frames:
    """Lets read_stack() read a list of photos as if they came from a camera."""
    def __init__(self, images):
        self.images = list(images)

    def read(self):
        if not self.images:
            return False, None
        return True, self.images.pop(0)


_state = {}


def _setup():
    """Loaded once per process (Lambda keeps it warm between requests)."""
    if not _state:
        K, dist, size = common.load_calibration(CALIB)
        _state.update(K=K, dist=dist, size=size, catalog=load_catalog(BOXES),
                      detector=common.make_marker_detector(),
                      obj=np.array([[-1, 1, 0], [1, 1, 0], [1, -1, 0], [-1, -1, 0]], np.float32) * (MARKER_MM / 2000.0))
    return _state


def _box_out(b):
    return {"id": int(b["id"]), "x_cm": round(b["x"] * 100, 2), "y_cm": round(b["y"] * 100, 2),
            "z_cm": round(b["z"] * 100, 2)}


def _box_in(b):
    return {"id": int(b["id"]), "x": b["x_cm"] / 100, "y": b["y_cm"] / 100, "z": b["z_cm"] / 100}


def analyze(images, req):
    """images: list of BGR arrays (same camera as the calibration). req: dict (see module doc).
    Returns (result dict, annotated BGR image)."""
    t_start = time.time()
    s = _setup()
    catalog = s["catalog"]
    mode = req.get("mode", "decide")
    result = {"ok": False, "mode": mode, "problem": None}
    if not images:
        result["problem"] = "no photos"
        return result, None
    images = images[:MAX_IMAGES]
    size = (images[0].shape[1], images[0].shape[0])
    if size != tuple(s["size"]):
        result["problem"] = (f"photo resolution {size[0]}x{size[1]} differs from the calibration "
                             f"{s['size'][0]}x{s['size'][1]}")
        return result, images[0]
    stack, R0, t0, frame, problem = read_stack(_Frames(images), s["detector"], catalog, s["obj"],
                                                s["K"], s["dist"], BASE_ID, n=len(images))
    view = images[-1].copy()
    if stack is not None:
        result["stack"] = [_box_out(b) for b in stack]
    if problem:
        result["problem"] = problem
        result["action"] = "RETAKE"
        if mode == "check" and "not visible" in problem:
            result["verify"] = {"status": "FELL?", "message": "bottom box not visible after the placement"}
        outlined(view, f"RETAKE: {problem}"[:110], (10, 30), 0.6, (0, 200, 255))
        result["seconds"] = round(time.time() - t_start, 2)
        return result, view
    settings = core.Settings(req.get("pos_sd_cm", 1.0), req.get("com_sd_cm", 2.0), req.get("friction", 0.5),
                             req.get("seed", 0))

    if mode == "check":
        plan = req.get("plan") or {}
        before = [_box_in(b) for b in plan.get("before", [])]
        box = _box_in(plan["box"]) if plan.get("box") else None
        v = core.verify(before, stack, box, catalog)
        result["verify"] = {k: (round(val * 100, 2) if k == "deviation_m" and val is not None else val)
                            for k, val in v.items()}
        result["verify"]["deviation_cm"] = result["verify"].pop("deviation_m")
        if v["status"] in ("OK", "OFF_PLAN"):
            p, n, ci, z = core.stack_risk(stack, catalog, settings)
            result["risk_now"] = {"p": round(p, 3), "ci": round(ci, 3), "n": n, "zone": z}
            result["action"] = "CONTINUE" if z == "GREEN" else "FIX_PLACEMENT"
        else:
            result["action"] = {"FELL": "STOP", "NOT_PLACED": "WAIT"}.get(v["status"], "CHECK")
        if box is not None:
            draw_box(view, box, catalog, R0, t0, s["K"], s["dist"], COLORS["GREEN"], 2)
        outlined(view, f"check: {v['status']} {v['message']}"[:110], (10, 30))
        result["ok"] = True
        result["seconds"] = round(time.time() - t_start, 2)
        return result, view

    box_id = req.get("box_id")
    if box_id is None:
        used = {b["id"] for b in stack}
        free = [i for i in sorted(catalog) if i not in used]
        box_id = free[0] if free else None
    if box_id is None or box_id not in catalog:
        p, n, ci, z = core.stack_risk(stack, catalog, settings)
        result.update(ok=True, action="DONE", problem=None,
                      risk_now={"p": round(p, 3), "ci": round(ci, 3), "n": n, "zone": z},
                      note="no other box in the catalogue")
        result["seconds"] = round(time.time() - t_start, 2)
        return result, view
    offset = float(req.get("offset_cm", 0.0)) / 100.0
    d = core.decide(stack, int(box_id), offset, catalog, settings)
    cand = core.candidate_box(stack, int(box_id), offset, catalog)
    result["decision"] = {"box_id": d["box_id"], "offset_cm": round(offset * 100, 1),
                          "overhang_pct": round(d["overhang_pct"], 1), "zone": d["zone"], "action": d["action"],
                          "p": round(d["p"], 3), "ci": round(d["ci"], 3), "n": d["n"],
                          "static_margin_cm": round(d["static_margin_m"] * 100, 2), "trace": d["trace"]}
    plans = {"requested": {"before": result["stack"], "box": _box_out(cand), "zone": d["zone"], "p": round(d["p"], 3)}}
    if d["alternative"]:
        a = d["alternative"]
        alt = core.candidate_box(stack, int(box_id), a["offset_m"], catalog)
        result["decision"]["alternative"] = {"offset_cm": round(a["offset_m"] * 100, 1),
                                             "overhang_pct": round(a["overhang_pct"], 1), "p": round(a["p"], 3)}
        plans["suggested"] = {"before": result["stack"], "box": _box_out(alt), "zone": "GREEN", "p": round(a["p"], 3)}
        draw_box(view, alt, catalog, R0, t0, s["K"], s["dist"], COLORS["GREEN"], 1)
    result["plans"] = plans
    result["action"] = d["action"]
    draw_box(view, cand, catalog, R0, t0, s["K"], s["dist"], COLORS[d["zone"]], 3)
    outlined(view, f"ID {box_id} {d['overhang_pct']:+.0f}%: P(fall) {d['p']:.0%} {d['zone']} -> {d['action']}", (10, 30))
    if d["alternative"]:
        outlined(view, f"suggestion: {d['alternative']['offset_m'] * 100:+.0f} cm, P(fall) {d['alternative']['p']:.0%}",
                 (10, 60), 0.6, COLORS["GREEN"])
    result["ok"] = True
    result["seconds"] = round(time.time() - t_start, 2)
    return result, view


def _decode(b64):
    data = base64.b64decode(b64.split(",", 1)[-1])
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("photo cannot be decoded")
    return img


def _legacy(body):
    """Photo(s) -> decision or check (agent.py --aws, aws/test_endpoint.py). Behaviour unchanged."""
    try:
        images = [_decode(b) for b in body.get("images", [])]
        result, view = analyze(images, body)
        if view is not None and body.get("return_image", True):
            ok, jpg = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 80])
            result["image_jpg_b64"] = base64.b64encode(jpg.tobytes()).decode() if ok else None
        return _response(200, result)
    except Exception as e:                       # report, never crash the endpoint
        return _response(400, {"ok": False, "problem": f"{type(e).__name__}: {e}"})


# ---------- judges' web page ----------

WEB_MAX_BODY = 16 * 1024          # bytes: web JSON (decision / log)
PHOTO_MAX_BODY = 2 * 1024 * 1024  # bytes: photo POST from the agent (3 JPEG ~ 450 KB)
RATE_WINDOW_S = 60.0
RATE_LIMITS = {"GET": 60, "POST": 20}
NAME_LEN = (2, 60)
REASON_LEN = (5, 300)
# Buttons per zone, as in the laptop agent. GREEN needs no approval (the agent guides the placement).
CHOICES = {"YELLOW": ("approve", "use_suggestion", "reject"), "RED": ("use_suggestion", "override", "cancel")}

_web = {}            # samples.json, page and photo bytes, decoded photos
_cache = {}          # (sample id, offset cm) -> decision; at most samples x offsets entries per container
_hits = {}           # (ip, method) -> deque of request times
_now = time.time     # replaced in tests


def _web_setup():
    if not _web:
        with open(os.path.join(WEB_DIR, "samples", "samples.json"), encoding="utf-8") as f:
            meta = json.load(f)
        _web.update(meta=meta, samples={x["id"]: x for x in meta["samples"]}, files={}, images={})
    return _web


def _web_file(name):
    w = _web_setup()
    if name not in w["files"]:
        with open(os.path.join(WEB_DIR, name), "rb") as f:
            w["files"][name] = f.read()
    return w["files"][name]


def _response(status, body, content_type="application/json", cache="no-store", binary=False):
    headers = {"Content-Type": content_type, "Cache-Control": cache, "X-Content-Type-Options": "nosniff"}
    if binary:
        return {"statusCode": status, "headers": headers, "isBase64Encoded": True,
                "body": base64.b64encode(body).decode()}
    if not isinstance(body, str):
        body = json.dumps(body, ensure_ascii=False)
    return {"statusCode": status, "headers": headers, "body": body}


def _error(status, message):
    return _response(status, {"ok": False, "problem": message})


def _rate_ok(ip, method):
    """Sliding one-minute window per IP, in this container's memory only."""
    now = _now()
    if len(_hits) > 5000:                          # many IPs: drop windows that are over
        for k in [k for k, q in _hits.items() if not q or now - q[-1] > RATE_WINDOW_S]:
            del _hits[k]
    q = _hits.setdefault((ip, method), deque())
    while q and now - q[0] > RATE_WINDOW_S:
        q.popleft()
    if len(q) >= RATE_LIMITS[method]:
        return False
    q.append(now)
    return True


def _clean_text(value, limits):
    if not isinstance(value, str):
        return None
    text = re.sub(r"[\x00-\x1f\x7f]", " ", value).strip()
    return text if limits[0] <= len(text) <= limits[1] else None


def _parse_offset(meta, value):
    """Shift in cm relative to the box directly below, rounded to 1 cm, inside the fixed range; or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    off = int(round(value))
    lo, hi = meta["offset_range_cm"]
    return off if lo <= off <= hi else None


def _cm1(m):
    return round(m * 100, 1) + 0.0          # + 0.0 turns -0.0 into 0.0


def _px(points):
    return [[round(float(x), 1), round(float(y), 1)] for x, y in points]


def web_decide(sample_id, offset_cm):
    """Decision for a sample photo + shift: same OpenCV reading and drystone_core.decide as the agent."""
    key = (sample_id, offset_cm)
    if key in _cache:
        return dict(_cache[key], cached=True)
    w, s = _web_setup(), _setup()
    catalog = s["catalog"]
    sample = w["samples"][sample_id]
    t_all = t = time.perf_counter()
    if sample_id not in w["images"]:
        data = np.frombuffer(_web_file(f"samples/{sample_id}.jpg"), np.uint8)
        w["images"][sample_id] = cv2.imdecode(data, cv2.IMREAD_COLOR)
    img = w["images"][sample_id]
    stack, R0, t0, _, problem = read_stack(_Frames([img]), s["detector"], catalog, s["obj"], s["K"], s["dist"],
                                           BASE_ID, n=1)
    poses = detect_poses(s["detector"], img, catalog, s["obj"], s["K"], s["dist"], BASE_ID)
    markers = [{"id": int(i), "corners": _px(c4)} for i, (_, _, c4) in sorted(poses.items())]
    t_detect = time.perf_counter() - t
    result = {"ok": False, "sample": sample_id, "offset_cm": offset_cm, "cached": False,
              "placeholder": bool(sample.get("placeholder")),
              "image": {"width": int(img.shape[1]), "height": int(img.shape[0])}, "markers": markers}
    detect_lines = [f"OpenCV found {len(markers)} box marker(s): ID " + ", ".join(str(m["id"]) for m in markers)]
    if problem or stack is None:
        result["problem"] = problem or "the stack could not be read"
        result["stages"] = [{"name": "Marker detection", "ms": round(t_detect * 1000),
                             "lines": detect_lines + [f"reading rejected: {result['problem']}"]}]
        return result
    box_id = int(sample["next_box"])
    settings = core.Settings(seed=0)          # fixed seed: the same request always gets the same answer
    d = core.decide(stack, box_id, offset_cm / 100.0, catalog, settings)
    boxes = [("stack", b) for b in stack] + [("candidate", core.candidate_box(stack, box_id, offset_cm / 100.0,
                                                                              catalog))]
    alt = None
    if d["alternative"]:
        a = d["alternative"]
        alt = {"offset_cm": round(a["offset_m"] * 100, 1), "overhang_pct": round(a["overhang_pct"], 2),
               "p": round(a["p"], 3), "n": a["n"]}
        boxes.append(("suggestion", core.candidate_box(stack, box_id, a["offset_m"], catalog)))
    polygons = []
    for role, b in boxes:
        pts = project_box(b, catalog, R0, t0, s["K"], s["dist"])
        if pts is not None:
            polygons.append({"role": role, "id": int(b["id"]), "corners": _px(pts)})
    tr, st, sec = d["trace"], d["stages"], d["seconds"]
    below = stack[-1]
    action_line = {"GUIDE": "GREEN -> GUIDE: place the box in the outline, no approval needed",
                   "ASK_SUPERVISOR": "YELLOW -> ASK_SUPERVISOR: a supervisor approves, uses the suggestion, or rejects",
                   "REJECT": "RED -> REJECT: refused; go on only with the suggestion or a logged override"}[d["action"]]
    result.update(ok=True, stack=[_box_out(b) for b in stack], box_id=box_id, polygons=polygons,
                  decision={"zone": d["zone"], "action": d["action"], "p": round(d["p"], 3),
                            "ci": round(d["ci"], 3), "n": d["n"], "overhang_pct": round(d["overhang_pct"], 2),
                            "static_margin_cm": _cm1(d["static_margin_m"]), "alternative": alt})
    result["stages"] = [
        {"name": "Marker detection (OpenCV)", "ms": round(t_detect * 1000),
         "lines": detect_lines + [f"bottom box ID {BASE_ID} sets the reference frame"]},
        {"name": "Digital twin", "ms": round(sec["twin"] * 1000),
         "lines": [f"box ID {b['id']}: x {_cm1(b['x']):+.1f} cm, height {_cm1(b['y']):.1f} cm" for b in stack]
         + [f"candidate box ID {box_id}: {offset_cm:+d} cm from box ID {below['id']} directly below"]
         + tr[:st["twin"]]},
        {"name": "Monte Carlo simulation (MuJoCo)", "ms": round(sec["simulation"] * 1000),
         "lines": tr[st["twin"]:st["simulation"]]},
        {"name": "Decision", "ms": 0,
         "lines": [f"P(fall) {d['p']:.0%} -> {d['zone']} (GREEN < 10%, YELLOW 10-50%, RED > 50%)"]},
        {"name": "Action", "ms": round(sec["search"] * 1000), "lines": [action_line] + tr[st["simulation"]:]},
    ]
    result["seconds"] = round(time.perf_counter() - t_all, 2)
    _cache[key] = result
    return dict(result)


def web_log(body):
    """Supervisor choice from the page -> one JSON line in CloudWatch Logs. It never changes the decision."""
    w = _web_setup()
    sample_id = body.get("sample")
    if sample_id not in w["samples"]:
        return _error(400, "unknown sample")
    off = _parse_offset(w["meta"], body.get("offset_cm"))
    if off is None:
        return _error(400, "offset_cm must be a number in the allowed range")
    d = web_decide(sample_id, off)          # from the cache, or recomputed if this container has not seen it
    if not d.get("ok"):
        return _error(400, "this sample could not be read")
    zone_now = d["decision"]["zone"]
    allowed = CHOICES.get(zone_now, ())
    choice = body.get("choice")
    if choice not in allowed:
        return _error(400, f"{zone_now} needs no approval" if not allowed
                      else f"for {zone_now} the choice must be one of: {', '.join(allowed)}")
    if choice == "use_suggestion" and not d["decision"]["alternative"]:
        return _error(400, "there is no suggestion for this placement")
    name = _clean_text(body.get("name"), NAME_LEN)
    reason = _clean_text(body.get("reason"), REASON_LEN)
    if choice == "override" and (not name or not reason):
        return _error(400, f"an override needs a name ({NAME_LEN[0]}-{NAME_LEN[1]} characters) "
                           f"and a reason ({REASON_LEN[0]}-{REASON_LEN[1]} characters)")
    entry = {"event": "web_supervisor_choice", "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "sample": sample_id, "placeholder": d["placeholder"], "offset_cm": off, "zone": zone_now,
             "action": d["decision"]["action"], "p": d["decision"]["p"], "choice": choice,
             "suggestion_cm": (d["decision"]["alternative"] or {}).get("offset_cm"), "name": name,
             "reason": reason}
    print(json.dumps(entry, ensure_ascii=False), flush=True)      # Lambda stdout = CloudWatch Logs
    note = f"Override logged. The decision stays {zone_now}." if choice == "override" else "Logged."
    return _response(200, {"ok": True, "logged": entry, "note": note})


def _http(event, http):
    """Function URL request (payload format 2.0)."""
    method = (http.get("method") or "GET").upper()
    path = event.get("rawPath") or "/"
    ip = http.get("sourceIp") or "unknown"
    if method not in RATE_LIMITS:
        return _error(405, "method not allowed")
    if not _rate_ok(ip, method):
        return _error(429, "too many requests, wait a minute")
    if method == "GET":
        if path in ("/", "/index.html"):
            return _response(200, _web_file("index.html").decode("utf-8"), "text/html; charset=utf-8",
                             "public, max-age=300")
        if path == "/samples/samples.json":
            # small, and it carries photos_version: always revalidated so a replaced photo shows at once
            return _response(200, _web_file("samples/samples.json").decode("utf-8"), cache="no-cache")
        m = re.fullmatch(r"/samples/([a-z0-9_-]{1,20})\.jpg", path)
        if m and m.group(1) in _web_setup()["samples"]:
            return _response(200, _web_file(f"samples/{m.group(1)}.jpg"), "image/jpeg", "public, max-age=86400",
                             binary=True)
        return _error(404, "not found")
    raw = event.get("body") or ""
    size = len(raw) * 3 // 4 if event.get("isBase64Encoded") else len(raw.encode("utf-8"))
    if size > PHOTO_MAX_BODY:
        return _error(413, "request body too large")
    try:
        body = json.loads(base64.b64decode(raw) if event.get("isBase64Encoded") else raw)
    except (ValueError, TypeError):
        return _error(400, "body must be JSON")
    if not isinstance(body, dict):
        return _error(400, "body must be a JSON object")
    if path == "/" and "images" in body:
        return _legacy(body)
    if size > WEB_MAX_BODY:
        return _error(413, "request body too large")
    if path == "/log":
        return web_log(body)
    if path != "/":
        return _error(404, "not found")
    w = _web_setup()
    if body.get("sample") not in w["samples"]:
        return _error(400, "unknown sample")
    off = _parse_offset(w["meta"], body.get("offset_cm"))
    if off is None:
        lo, hi = w["meta"]["offset_range_cm"]
        return _error(400, f"offset_cm must be a number from {lo} to {hi}")
    return _response(200, web_decide(body["sample"], off))


def lambda_handler(event, context=None):
    """AWS Lambda entry point: Function URL (page, samples, decisions, photo POST) or a direct invoke."""
    http = (event.get("requestContext") or {}).get("http")
    if not http:                                   # direct invoke (aws lambda invoke) with the photo JSON
        try:
            body = event.get("body", event)
            if isinstance(body, str):
                body = json.loads(base64.b64decode(body) if event.get("isBase64Encoded") else body)
        except Exception as e:
            return _response(400, {"ok": False, "problem": f"{type(e).__name__}: {e}"})
        return _legacy(body)
    try:
        return _http(event, http)
    except Exception as e:                         # details stay in CloudWatch, the browser gets a short message
        print(json.dumps({"event": "error", "error": f"{type(e).__name__}: {e}"}), flush=True)
        return _error(500, "internal error")


def main():
    ap = argparse.ArgumentParser(description="Stack photo(s) -> Drystone decision (JSON)")
    ap.add_argument("--images", required=True, help='photo file(s), a pattern is fine, e.g. "data/x/*.png" (max 5)')
    ap.add_argument("--offset-cm", type=float, default=0.0, help="candidate shift to the right of the top box (cm)")
    ap.add_argument("--box-id", type=int, help="next box ID (empty = smallest unused ID)")
    ap.add_argument("--check", help="plan.json from a decide run -> check mode")
    ap.add_argument("--plan", default="requested", choices=["requested", "suggested"],
                    help="for --check: which plan in plan.json to use")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    paths = sorted(glob.glob(args.images))[:MAX_IMAGES]
    if not paths:
        sys.exit(f"No file matches: {args.images}")
    images = [common.read_image(p) for p in paths]
    req = {"mode": "decide", "offset_cm": args.offset_cm, "box_id": args.box_id, "seed": args.seed}
    if args.check:
        with open(args.check, encoding="utf-8") as f:
            plans = json.load(f)
        req = {"mode": "check", "plan": plans.get(args.plan, plans), "seed": args.seed}
    result, view = analyze(images, req)
    out_dir = os.path.join(common.DATA_DIR, f"service_{time.strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(out_dir, exist_ok=True)
    if view is not None:
        cv2.imwrite(os.path.join(out_dir, "result.jpg"), view)
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if result.get("plans"):
        with open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as f:
            json.dump(result["plans"], f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nSaved in {out_dir} (result.json, result.jpg" + (", plan.json)" if result.get("plans") else ")"))


if __name__ == "__main__":
    main()
