"""Judges' web page on the Function URL: routing, zones, supervisor log, limits, and the old photo POST.

    python -m pytest tests/test_web.py -q
The zone tests run the real OpenCV reading + Monte Carlo on the sample photos (about a minute in total).
"""
import base64
import json
import os
import re
import shutil
import subprocess

import pytest

import service

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "web", "samples", "samples.json"), encoding="utf-8") as f:
    META = json.load(f)
# (sample, zone, shift, key of its suggestion): examples to the right, then to the left
EXAMPLES = [(s["id"], zone, off, sug) for s in META["samples"]
            for ex, sug in (("examples", "suggestion_cm"), ("examples_left", "suggestion_left_cm"))
            for zone, off in s[ex].items()]
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
    assert "can take up to 10 s" in html
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


def test_diagram_images_200_and_unknown_404():
    status, body, out = call("GET", "/img/architecture.png")
    assert status == 200 and out["isBase64Encoded"] and out["headers"]["Content-Type"] == "image/png"
    assert base64.b64decode(body)[:8] == b"\x89PNG\r\n\x1a\n"
    assert call("GET", "/img/agent_loop.png")[0] == 200
    assert call("GET", "/img/web_desktop.png")[0] == 404             # only the listed diagrams
    assert call("GET", "/img/../index.html")[0] == 404


@pytest.mark.parametrize("sample,zone,offset,sug_key", EXAMPLES)
def test_example_zones(sample, zone, offset, sug_key):
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
        expected = next(x for x in META["samples"] if x["id"] == sample)[sug_key][zone]
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


def test_hero_replay_matches_service():
    """The page replays recorded checks; they must still be what the service answers."""
    with open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8") as f:
        html = f.read()
    for var in ("REC", "REC2"):                      # hero card, and the camera view on How it works
        start = html.index(f"var {var} = ") + len(f"var {var} = ")
        rec = json.loads(html[start:html.index(";\n", start)])
        status, r, _ = call("POST", "/", {"sample": rec["sample"], "offset_cm": rec["offset_cm"]})
        assert status == 200 and r["ok"]
        assert r["decision"] == rec["decision"]
        assert r["box_id"] == rec["box_id"]
        assert [m["id"] for m in r["markers"]] == [m["id"] for m in rec["markers"]]
        assert [p["role"] for p in r["polygons"]] == [p["role"] for p in rec["polygons"]]


def _page_html():
    with open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8") as f:
        return f.read()


def test_links_start_hidden():
    """Links whose LINKS value is still empty are hidden in the HTML itself, before any script runs."""
    html = _page_html()
    tags = re.findall(r"<a [^>]*data-link=[^>]*>", html)
    assert len(tags) == 6 and all(" hidden" in t for t in tags)   # video, repo, report x2, markers, board


@pytest.mark.parametrize("links, shown", [
    ({"repo": "#", "video": "", "report": "#"}, False),
    ({"repo": "https://github.com/example/drystone/", "video": "https://youtu.be/example",
      "report": "https://github.com/example/drystone/blob/main/docs/REPORT.md"}, True),
])
def test_links_hidden_until_filled(links, shown):
    """The page's own applyLinks block, run in Node on stand-in elements."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    html = _page_html()
    block = html[html.index("// links:start"):html.index("// links:end")]
    script = block + """
    function el(data) { return { dataset: data, hidden: true, href: "#", textContent: "<repository URL>" }; }
    var nodes = {
      "[data-link]": [el({ link: "video" }), el({ link: "repo" }), el({ link: "report" }), el({ link: "report" })],
      "[data-need]": [el({ need: "repo" })], "[data-no]": [el({ no: "repo" })], "[data-clone]": [el({})]
    };
    nodes["[data-no]"][0].hidden = false;
    applyLinks(%s, { querySelectorAll: function (sel) { return nodes[sel]; } });
    console.log(JSON.stringify(nodes));
    """ % json.dumps(links)
    out = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
    assert [a["hidden"] for a in out["[data-link]"]] == [not shown] * 4
    assert out["[data-need]"][0]["hidden"] is (not shown)           # the git clone line
    assert out["[data-no]"][0]["hidden"] is shown                   # "Repository link: on the submission page"
    if shown:
        assert [a["href"] for a in out["[data-link]"]] == [links["video"], links["repo"], links["report"], links["report"]]
        assert out["[data-clone]"][0]["textContent"] == "https://github.com/example/drystone.git"
    else:
        assert all(a["href"] == "#" for a in out["[data-link]"])
        assert out["[data-clone]"][0]["textContent"] == "<repository URL>"   # the clone command keeps its placeholder


def test_ghost_boxes_match_the_service():
    """The page's dashed 'not checked yet' outlines are current and are the service's candidate polygons."""
    import ghost_boxes
    html = _page_html()
    start = html.index("  var GHOST = ") + len("  var GHOST = ")
    page = json.loads(html[start:html.index(";\n", start)])
    data = ghost_boxes.compute()
    assert page == data, "run: python tools/ghost_boxes.py --write"
    lo, hi = META["offset_range_cm"]
    assert all(len(v) == hi - lo + 1 for v in page.values())
    for sample, off in (("s2", S2["YELLOW"]), ("s1", 16)):        # answers other tests already compute (cached)
        status, r, _ = call("POST", "/", {"sample": sample, "offset_cm": off})
        cand = next(p["corners"] for p in r["polygons"] if p["role"] == "candidate")
        assert page[sample][str(off)] == cand


def test_live_diagrams_link_to_their_images():
    """How it works draws both diagrams on the page; each keeps a link to its PNG, which the service still serves."""
    html = _page_html()
    for fid, img in (("dg-arch", "img/architecture.png"), ("dg-loop", "img/agent_loop.png")):
        start = html.index('<figure class="dg" id="%s">' % fid)
        fig = html[start:html.index("</figure>", start)]
        assert "<svg" in fig and '<ol class="dg-list"' in fig
        assert '<a href="%s"' % img in fig and "Open as image" in fig
        status, _, out = call("GET", "/" + img)
        assert status == 200 and out["headers"]["Content-Type"] == "image/png"


def test_setup_git_clone_is_always_the_first_command():
    """With LINKS.repo empty or filled, the Setup tab shows git clone first; only links are hidden, never a command."""
    html = _page_html()
    i = html.index('aria-labelledby="h-l2"')
    section = html[i:html.index("</section>", i)]
    clone = section.index("<code>git clone ")
    assert clone < section.index("<code>cd drystone</code>")
    block = section[section.rindex('<div class="code"', 0, clone):clone]
    assert "hidden" not in block and "data-need" not in block
    assert "data-need=" not in html                                   # no command depends on a link any more
    assert section.index("<code>git clone ") < section.index('data-no="repo">Repository link: on the submission page.')
