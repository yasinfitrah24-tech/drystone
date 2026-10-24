"""Why the calibration accepts a focal length uncertainty up to 3% (calibrate.MAX_F_SD_PCT): the stack is read
relative to the bottom box, and a focal length that is off scales depth and size together, so the boxes barely move.
Read the demo photo s2 and a synthetic stack with fx, fy off by up to 5%; only the camera distance changes.

    python -m pytest tests/test_focal_error.py -q
"""
import os

import cv2
import numpy as np
import pytest

import calibrate
import service
import synth_scene as S
from agent import read_scene

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = [S.CATALOG[i]["H"] for i in range(3)]


def stack_at(images, scale):
    s = service._setup()
    K = s["K"].copy()
    K[0, 0] *= scale
    K[1, 1] *= scale
    stack, _, _, t0, _, problem = read_scene(service._Frames(list(images)), s["detector"], s["catalog"], s["obj"], K,
                                             s["dist"], 0, n=len(images))
    assert problem is None and stack is not None, problem
    return {b["id"]: np.array([b["x"], b["y"]]) for b in stack}, float(np.linalg.norm(t0))


@pytest.mark.parametrize("name", ["photo s2", "synthetic, ID 1 at +6 cm"])
def test_focal_error_barely_moves_the_boxes(name):
    images = ([cv2.imread(os.path.join(ROOT, "web", "samples", "s2.jpg"))] if name == "photo s2" else
              [S.render([S.upright(0, 0.0, y=0.0), S.upright(1, 0.06, y=S.FLOOR_Y + H[0] + H[1] / 2)])])
    true, dist = stack_at(images, 1.0)
    assert len(true) == 2
    for scale in (0.95, 0.97, 1.03, 1.05):
        boxes, d = stack_at(images, scale)
        assert set(boxes) == set(true)
        moved = max(np.abs(boxes[i] - true[i]).max() for i in true)
        assert moved < 0.001, (scale, moved)                    # under 1 mm, x (overhang) and y (height)
        assert abs(d / dist - scale) < 0.01                     # what does change: the distance to the camera


def test_limit_is_three_percent():
    assert calibrate.MAX_F_SD_PCT == 3.0
