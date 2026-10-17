r"""Layanan Drystone: foto tumpukan -> keputusan (JSON). Dipakai di laptop dan di AWS Lambda.

Dua mode:
- decide: foto (1-5 foto berturut-turut, lebih banyak = lebih stabil) + calon posisi kardus berikutnya
  -> zona HIJAU/KUNING/MERAH, P(roboh), alasan, usulan posisi aman, dan "plan" untuk dicek nanti.
- check : foto setelah kardus ditaruh + "plan" dari hasil decide -> OK / MELESET / ROBOH / BELUM.
Keputusan keselamatan deterministik (drystone_core), bukan LLM.

Laptop:
    python tools/service.py --images "data/agent_x/langkah_003_cek_ulang.png" --offset-cm 12
    python tools/service.py --images "foto_setelah.png" --check data/service_x/plan.json
AWS Lambda: handler = service.lambda_handler, body JSON:
    {"mode": "decide", "images": ["<base64 jpg/png>", ...], "offset_cm": 12, "box_id": 2}
    {"mode": "check",  "images": [...], "plan": {...}}
"""
import argparse
import base64
import glob
import json
import os
import sys
import time

import cv2
import numpy as np

import common
import drystone_core as core
from agent import COLORS, draw_box, outlined, read_stack
from predict_test import load_catalog

ROOT = common.ROOT
CALIB = os.environ.get("DRYSTONE_CALIB", os.path.join(ROOT, "data", "camera_laptop.yaml"))
BOXES = os.environ.get("DRYSTONE_BOXES", os.path.join(ROOT, "config", "boxes.json"))
MARKER_MM = float(os.environ.get("DRYSTONE_MARKER_MM", "80"))
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
        result["problem"] = "tidak ada foto"
        return result, None
    images = images[:MAX_IMAGES]
    size = (images[0].shape[1], images[0].shape[0])
    if size != tuple(s["size"]):
        result["problem"] = (f"resolusi foto {size[0]}x{size[1]} beda dengan kalibrasi "
                             f"{s['size'][0]}x{s['size'][1]}")
        return result, images[0]
    stack, R0, t0, frame, problem = read_stack(_Frames(images), s["detector"], catalog, s["obj"],
                                                s["K"], s["dist"], BASE_ID, n=len(images))
    view = images[-1].copy()
    if stack is not None:
        result["stack"] = [_box_out(b) for b in stack]
    if problem:
        result["problem"] = problem
        result["action"] = "FOTO_ULANG"
        if mode == "check" and "tidak terlihat" in problem:
            result["verify"] = {"status": "ROBOH?", "message": "kardus bawah tidak terlihat setelah penempatan"}
        outlined(view, f"FOTO ULANG: {problem}"[:110], (10, 30), 0.6, (0, 200, 255))
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
        if v["status"] in ("OK", "MELESET"):
            p, n, ci, z = core.stack_risk(stack, catalog, settings)
            result["risk_now"] = {"p": round(p, 3), "ci": round(ci, 3), "n": n, "zone": z}
            result["action"] = "LANJUT" if z == "HIJAU" else "BETULKAN"
        else:
            result["action"] = {"ROBOH": "BERHENTI", "BELUM": "TUNGGU"}.get(v["status"], "PERIKSA")
        if box is not None:
            draw_box(view, box, catalog, R0, t0, s["K"], s["dist"], COLORS["HIJAU"], 2)
        outlined(view, f"cek ulang: {v['status']} {v['message']}"[:110], (10, 30))
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
        result.update(ok=True, action="SELESAI", problem=None,
                      risk_now={"p": round(p, 3), "ci": round(ci, 3), "n": n, "zone": z},
                      note="tidak ada kardus lain di katalog")
        result["seconds"] = round(time.time() - t_start, 2)
        return result, view
    offset = float(req.get("offset_cm", 0.0)) / 100.0
    d = core.decide(stack, int(box_id), offset, catalog, settings)
    cand = core.candidate_box(stack, int(box_id), offset, catalog)
    result["decision"] = {"box_id": d["box_id"], "offset_cm": round(offset * 100, 1),
                          "overhang_pct": round(d["overhang_pct"], 1), "zone": d["zone"], "action": d["action"],
                          "p": round(d["p"], 3), "ci": round(d["ci"], 3), "n": d["n"],
                          "static_margin_cm": round(d["static_margin_m"] * 100, 2), "trace": d["trace"]}
    plans = {"diminta": {"before": result["stack"], "box": _box_out(cand), "zone": d["zone"], "p": round(d["p"], 3)}}
    if d["alternative"]:
        a = d["alternative"]
        alt = core.candidate_box(stack, int(box_id), a["offset_m"], catalog)
        result["decision"]["alternative"] = {"offset_cm": round(a["offset_m"] * 100, 1),
                                             "overhang_pct": round(a["overhang_pct"], 1), "p": round(a["p"], 3)}
        plans["usulan"] = {"before": result["stack"], "box": _box_out(alt), "zone": "HIJAU", "p": round(a["p"], 3)}
        draw_box(view, alt, catalog, R0, t0, s["K"], s["dist"], COLORS["HIJAU"], 1)
    result["plans"] = plans
    result["action"] = d["action"]
    draw_box(view, cand, catalog, R0, t0, s["K"], s["dist"], COLORS[d["zone"]], 3)
    outlined(view, f"ID {box_id} {d['overhang_pct']:+.0f}%: P(roboh) {d['p']:.0%} {d['zone']} -> {d['action']}", (10, 30))
    if d["alternative"]:
        outlined(view, f"usulan: {d['alternative']['offset_m'] * 100:+.0f} cm, P(roboh) {d['alternative']['p']:.0%}",
                 (10, 60), 0.6, COLORS["HIJAU"])
    result["ok"] = True
    result["seconds"] = round(time.time() - t_start, 2)
    return result, view


def _decode(b64):
    data = base64.b64decode(b64.split(",", 1)[-1])
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("foto tidak bisa dibaca")
    return img


def lambda_handler(event, context=None):
    """AWS Lambda entry point (API Gateway / Function URL, or a direct invoke with the same JSON)."""
    try:
        body = event.get("body", event)
        if isinstance(body, str):
            body = json.loads(base64.b64decode(body) if event.get("isBase64Encoded") else body)
        images = [_decode(b) for b in body.get("images", [])]
        result, view = analyze(images, body)
        if view is not None and body.get("return_image", True):
            ok, jpg = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 80])
            result["image_jpg_b64"] = base64.b64encode(jpg.tobytes()).decode() if ok else None
        status = 200
    except Exception as e:                       # report, never crash the endpoint
        result, status = {"ok": False, "problem": f"{type(e).__name__}: {e}"}, 400
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(result, ensure_ascii=False)}


def main():
    ap = argparse.ArgumentParser(description="Foto tumpukan -> keputusan Drystone (JSON)")
    ap.add_argument("--images", required=True, help='file foto, boleh pola, misalnya "data/x/*.png" (maks 5)')
    ap.add_argument("--offset-cm", type=float, default=0.0, help="geser calon ke kanan dari kardus teratas (cm)")
    ap.add_argument("--box-id", type=int, help="ID kardus berikutnya (kosong = ID terkecil yang belum dipakai)")
    ap.add_argument("--check", help="file plan.json dari hasil decide -> mode cek ulang")
    ap.add_argument("--plan", default="diminta", choices=["diminta", "usulan"],
                    help="untuk --check: rencana mana yang dipakai dari plan.json")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    paths = sorted(glob.glob(args.images))[:MAX_IMAGES]
    if not paths:
        sys.exit(f"Tidak ada file yang cocok dengan: {args.images}")
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
        cv2.imwrite(os.path.join(out_dir, "hasil.jpg"), view)
    with open(os.path.join(out_dir, "hasil.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    if result.get("plans"):
        with open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as f:
            json.dump(result["plans"], f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nTersimpan di {out_dir} (hasil.json, hasil.jpg" + (", plan.json)" if result.get("plans") else ")"))


if __name__ == "__main__":
    main()
