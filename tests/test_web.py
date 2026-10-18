"""Judges' web page on the Function URL: routing, zones, supervisor log, limits, and the old photo POST.

    python -m pytest tests/test_web.py -q
The zone tests run the real OpenCV reading + Monte Carlo on the sample photos (about a minute in total).
"""
import base64
import json
import os

import pytest

import service

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "web", "samples", "samples.json"), encoding="utf-8") as f:
    META = json.load(f)
EXAMPLES = [(s["id"], zone, off) for s in META["samples"] for zone, off in s["examples"].items()]
S2 = next(s for s in META["samples"] if s["id"] == "s2")["examples"]


def event(method, path="/", body=None, ip="198.51.100.1"):
    if body is not None and not isinstance(body, str):
        body = json.dumps(body)
    return {"version": "2.0", "rawPath": path, "body": body, "isBase64Encoded": False,
            "requestContext": {"http": {"method": method, "path": path, "sourceIp": ip}}}


def call(method, path="/", body=None, ip="198.51.100.1"):
    out = service.lambda_handler(event(method, path, body, ip))
    data = out["body"]
    if out.get("headers", {}).get("Content-Type", "").startswith("application/json"):
        data = json.loads(data)
    return out["statusCode"], data, out


@pytest.fixture(autouse=True)
def fresh_limits():
    service._hits.clear()
    yield
    service._hits.clear()


def test_page_200():
    status, html, out = call("GET", "/")
    assert status == 200
    assert out["headers"]["Content-Type"].startswith("text/html")
    assert "max-age" in out["headers"]["Cache-Control"]
    assert "not a certified safety device" in html
    assert "first run can take ~10 s" in html
    assert 'type="file"' not in html                       # no photo upload


def test_sample_photo_200_and_unknown_404():
    status, body, out = call("GET", "/samples/s1.jpg")
    assert status == 200 and out["isBase64Encoded"]
    assert base64.b64decode(body)[:2] == b"\xff\xd8"        # JPEG
    assert "max-age" in out["headers"]["Cache-Control"]
    assert call("GET", "/samples/nope.jpg")[0] == 404
    assert call("GET", "/samples/../config/boxes.json")[0] == 404
    status, _, out = call("GET", "/samples/samples.json")
    assert status == 200 and out["headers"]["Cache-Control"] == "no-cache"


@pytest.mark.parametrize("sample,zone,offset", EXAMPLES)
def test_example_zones(sample, zone, offset):
    status, r, _ = call("POST", "/", {"sample": sample, "offset_cm": offset})
    assert status == 200 and r["ok"], r
    d = r["decision"]
    assert d["zone"] == zone
    assert d["action"] == {"GREEN": "GUIDE", "YELLOW": "ASK_SUPERVISOR", "RED": "REJECT"}[zone]
    if zone == "GREEN":
        assert d["alternative"] is None
    else:
        alt = d["alternative"]
        assert alt and alt["p"] < 0.10
        # margin: the spot 1 cm further out (more overhang) is green too, and it is the suggested shift
        assert alt["further_offset_cm"] == alt["offset_cm"] + (1 if alt["offset_cm"] >= 0 else -1)
        assert alt["p_further"] is not None and alt["p_further"] < 0.10
        expected = next(x for x in META["samples"] if x["id"] == sample)["suggestion_cm"][zone]
        assert round(alt["offset_cm"]) == expected
        assert {p["role"] for p in r["polygons"]} == {"stack", "candidate", "suggestion"}
    assert [s["name"].split(" (")[0] for s in r["stages"]] == [
        "Marker detection", "Digital twin", "Monte Carlo simulation", "Decision", "Action"]


def test_real_photos_no_placeholder():
    """Judges must see real photos: no sample may still be marked as a placeholder."""
    assert not [s["id"] for s in META["samples"] if s.get("placeholder")]


def test_photos_version_matches_photos():
    """The page adds ?v=<photos_version> to photo URLs, so a replaced photo is never shown from a browser cache."""
    import hashlib
    h = hashlib.sha256()
    for s in META["samples"]:
        with open(os.path.join(ROOT, "web", "samples", f"{s['id']}.jpg"), "rb") as f:
            h.update(f.read())
    assert META["photos_version"] == h.hexdigest()[:10]
    status, _, _ = call("GET", "/samples/s1.jpg")      # rawPath has no query string; the version is ignored
    assert status == 200


def test_suggestion_rechecks_green():
    """The page's 'use suggestion' loop: suggestion -> analyse again at that shift -> GREEN."""
    r = call("POST", "/", {"sample": "s2", "offset_cm": 16})[1]
    alt = round(r["decision"]["alternative"]["offset_cm"])
    again = call("POST", "/", {"sample": "s2", "offset_cm": alt})[1]
    assert again["decision"]["zone"] == "GREEN"


def test_cached_and_rounded():
    first = call("POST", "/", {"sample": "s2", "offset_cm": 6})[1]
    second = call("POST", "/", {"sample": "s2", "offset_cm": 6.4})[1]   # rounds to 6 cm
    assert second["cached"] is True and second["offset_cm"] == 6
    assert second["decision"] == first["decision"]


@pytest.mark.parametrize("body", [{"sample": "s2", "offset_cm": 17}, {"sample": "s2", "offset_cm": "6"},
                                  {"sample": "s9", "offset_cm": 6}, {"sample": "s2"}])
def test_bad_decision_request_400(body):
    assert call("POST", "/", body)[0] == 400


def test_log_override_needs_name_and_reason(capsys):
    red = {"sample": "s2", "offset_cm": 16, "choice": "override"}
    assert call("POST", "/log", red)[0] == 400
    assert call("POST", "/log", dict(red, name="Judge A"))[0] == 400
    assert call("POST", "/log", dict(red, reason="testing the override"))[0] == 400
    assert call("POST", "/log", dict(red, name="J", reason="too short name"))[0] == 400
    capsys.readouterr()
    status, r, _ = call("POST", "/log", dict(red, name="Judge A", reason="testing the override"))
    assert status == 200 and r["ok"]
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])     # one JSON line = CloudWatch
    assert line["choice"] == "override" and line["zone"] == "RED" and line["name"] == "Judge A"
    # an override is only logged: the decision is unchanged
    assert call("POST", "/", {"sample": "s2", "offset_cm": 16})[1]["decision"]["zone"] == "RED"


def test_log_choices_follow_the_zone():
    green, yellow, red = S2["GREEN"], S2["YELLOW"], S2["RED"]
    assert call("POST", "/log", {"sample": "s2", "offset_cm": red, "choice": "approve"})[0] == 400
    assert call("POST", "/log", {"sample": "s2", "offset_cm": yellow, "choice": "override",
                                 "name": "Judge A", "reason": "not allowed here"})[0] == 400
    assert call("POST", "/log", {"sample": "s2", "offset_cm": green, "choice": "approve"})[0] == 400
    for choice in ("approve", "use_suggestion", "reject"):
        assert call("POST", "/log", {"sample": "s2", "offset_cm": yellow, "choice": choice})[0] == 200
    for choice in ("use_suggestion", "cancel"):
        assert call("POST", "/log", {"sample": "s2", "offset_cm": red, "choice": choice})[0] == 200


def test_413_web_json_over_16kb():
    body = json.dumps({"sample": "s2", "offset_cm": 6, "pad": "x" * 17000})
    assert call("POST", "/", body)[0] == 413
    assert call("POST", "/log", body)[0] == 413


def test_413_photo_post_over_2mb():
    body = json.dumps({"mode": "decide", "images": ["A" * (2 * 1024 * 1024 + 10)], "offset_cm": 6})
    assert call("POST", "/", body)[0] == 413


def test_429_after_20_posts_per_minute():
    ip = "203.0.113.7"
    for _ in range(20):
        assert call("POST", "/", "not json", ip=ip)[0] == 400
    assert call("POST", "/", "not json", ip=ip)[0] == 429
    assert call("POST", "/", "not json", ip="203.0.113.8")[0] == 400        # other IP not affected
    service._now = lambda: service.time.time() + 61                        # a minute later
    try:
        assert call("POST", "/", "not json", ip=ip)[0] == 400
    finally:
        service._now = service.time.time


def test_429_after_60_gets_per_minute():
    ip = "203.0.113.9"
    for _ in range(60):
        assert call("GET", "/samples/s1.jpg", ip=ip)[0] == 200
    assert call("GET", "/", ip=ip)[0] == 429


def _photo_b64(sample):
    with open(os.path.join(ROOT, "web", "samples", f"{sample}.jpg"), "rb") as f:
        return base64.b64encode(f.read()).decode()


def test_old_photo_post_unchanged():
    """agent.py --aws sends photos as before (Function URL) -> same JSON as before."""
    status, r, _ = call("POST", "/", {"mode": "decide", "images": [_photo_b64("s2")], "offset_cm": 6,
                                      "box_id": 2, "return_image": False})
    assert status == 200 and r["ok"] and r["decision"]["zone"] == "GREEN"
    assert set(r["plans"]) == {"requested"} and "trace" in r["decision"]


def test_direct_invoke_unchanged():
    out = service.lambda_handler({"mode": "decide", "images": [_photo_b64("s1")], "offset_cm": 6,
                                  "return_image": False})
    r = json.loads(out["body"])
    assert out["statusCode"] == 200 and r["decision"]["zone"] == "GREEN"
    bad = service.lambda_handler({"mode": "decide", "images": ["bm90IGFuIGltYWdl"]})
    assert bad["statusCode"] == 400 and "cannot be decoded" in json.loads(bad["body"])["problem"]
