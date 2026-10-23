"""Outline of the next box on each sample photo, for every shift the page allows (no simulation).

The judges' page draws this "ghost" box while a shift is picked and not checked yet. The outline comes from the
same reading and projection as tools/service.py (read_stack, drystone_core.candidate_box, project_box), so it is
the same outline the service returns as the "candidate" polygon after a check. tests/test_web.py checks both.

    python tools/ghost_boxes.py            print the data as JSON
    python tools/ghost_boxes.py --write    put it into web/index.html (the line starting with "var GHOST = ")
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import drystone_core as core  # noqa: E402
import service  # noqa: E402
from agent import project_box, read_stack  # noqa: E402

PAGE = os.path.join(service.WEB_DIR, "index.html")


def compute():
    """{sample id: {"shift in cm": 8 corners [x, y] in photo pixels}} for every shift in offset_range_cm."""
    w, s = service._web_setup(), service._setup()
    lo, hi = w["meta"]["offset_range_cm"]
    out = {}
    for sample_id, sample in w["samples"].items():
        img = cv2.imdecode(np.frombuffer(service._web_file(f"samples/{sample_id}.jpg"), np.uint8), cv2.IMREAD_COLOR)
        stack, R0, t0, _, problem = read_stack(service._Frames([img]), s["detector"], s["catalog"], s["obj"], s["K"],
                                               s["dist"], service.BASE_ID, n=1)
        if problem or stack is None:
            raise SystemExit(f"{sample_id}: the stack could not be read ({problem})")
        box_id = int(sample["next_box"])
        out[sample_id] = {}
        for off in range(lo, hi + 1):
            pts = project_box(core.candidate_box(stack, box_id, off / 100.0, s["catalog"]), s["catalog"], R0, t0,
                              s["K"], s["dist"])
            if pts is not None:
                out[sample_id][str(off)] = service._px(pts)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="write the data into web/index.html")
    args = ap.parse_args()
    data = json.dumps(compute(), separators=(",", ":"))
    if not args.write:
        print(data)
        return
    with open(PAGE, encoding="utf-8", newline="") as f:
        html = f.read()
    new, n = re.subn(r"(?m)^(  var GHOST = ).*;$", lambda m: m.group(1) + data + ";", html)
    if n != 1:
        raise SystemExit('web/index.html needs exactly one line starting with "  var GHOST = "')
    with open(PAGE, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    print(f"wrote {len(data)} characters into {PAGE}")


if __name__ == "__main__":
    main()
