"""tools/calibrate.py guided mode on synthetic board photos (tests/synth_board.py): targets reached are saved, wrong
positions are not and get hints in the right direction, the full target list covers the image and every tilt side.

    python -m pytest tests/test_calibrate_guided.py -q
"""
import io
import types
from contextlib import redirect_stdout

import cv2
import numpy as np
import pytest

import calibrate as c
import common
from synth_board import camera, default_board, render_board

SIZE = (1280, 720)
K_TRUE = camera(SIZE, 900.0)          # the "real" camera; the guide only guesses 0.7 x width = 896


@pytest.fixture(scope="module")
def board():
    return default_board()


@pytest.fixture(scope="module")
def detector(board):
    return cv2.aruco.CharucoDetector(board)


def seen(board, detector, R, tvec, name=""):
    """Render the board at (R, tvec), detect it, and return (view or None, corners found)."""
    corners, ids, n = c.detect(detector, render_board(board, R, tvec, K_TRUE, SIZE))
    return (c.BoardView(board, corners, ids, SIZE, name) if n >= c.MIN_CORNERS else None), n


def at_target(board, k, shift=(0.0, 0.0, 0.0), yaw=None, pitch=None):
    """The pose of target k, optionally moved (board units, camera axes) or with another yaw / pitch."""
    t = list(c.TARGETS[k])
    if yaw is not None:
        t[4] = yaw
    if pitch is not None:
        t[5] = pitch
    R, tvec = c.target_pose(board, SIZE, tuple(t))
    return R, tvec + np.asarray(shift, float)


@pytest.fixture(scope="module")
def all_views(board, detector):
    views = []
    for k in range(len(c.TARGETS)):
        v, n = seen(board, detector, *at_target(board, k), name=f"{k + 1:02d}.png")
        views.append((v, n))
    return views


def test_every_target_is_reached_and_the_list_covers_everything(board, all_views):
    g = c.Guide(board, SIZE)
    views = []
    for k, (v, n) in enumerate(all_views):
        g.i = k
        matched, hints = g.check(v, n)
        assert matched, (c.TARGETS[k][0], hints)
        views.append(v)
    assert c.coverage(views, SIZE).sum() == 12
    assert set().union(*(c.tilt_sides(v.normal) for v in views)) == set(c.SIDES)
    # the first nine targets already do it; the others add perspective
    assert c.coverage(views[:9], SIZE).sum() == 12
    assert set().union(*(c.tilt_sides(v.normal) for v in views[:9])) == set(c.SIDES)
    rms, K, dist, sd, _ = c.calibrate(views, SIZE)
    verdict = c.assess(views, SIZE, rms, K, sd)[0]
    assert verdict == common.CALIB_PASS and abs(K[0, 0] - 900) < 9


def test_target_reached_and_held_still_is_saved(board, all_views):
    g = c.Guide(board, SIZE)
    v, n = all_views[0]
    assert g.update(v, n, [], now=10.0)[0] == "hold"
    assert g.update(v, n, [], now=10.3)[0] == "hold"
    assert g.update(v, n, [], now=10.6, still=False)[0] == "hold"        # moving: the clock starts again
    assert g.update(v, n, [], now=10.7)[0] == "hold"
    assert g.update(v, n, [], now=11.25)[0] == "save"
    g.next()
    assert g.i == 1
    # going back to it: the same frame again is a repeat, not a second save
    g.back()
    event, hints = g.update(v, n, [v], now=20.0)
    assert event == "repeat" and "N for the next target" in hints[0]


def test_wrong_position_is_not_saved_and_the_hints_point_the_right_way(board, detector):
    g = c.Guide(board, SIZE)                                             # target 1: centre, flat
    z = c.target_pose(board, SIZE, c.TARGETS[0])[1][2]
    cases = [((0.30 * z, 0, 0), {}, "move left"),          # board too far right in the image
             ((-0.30 * z, 0, 0), {}, "move right"),
             ((0, 0.15 * z, 0), {}, "move up"),     # (small enough to keep the whole board in view)
             ((0, -0.15 * z, 0), {}, "move down"),
             ((0, 0, 0.5 * z), {}, "closer"),
             ((0, 0, -0.3 * z), {}, "further"),
             ((0, 0, 0), {"yaw": -25}, "face the camera")]
    for shift, turn_to, want in cases:
        v, n = seen(board, detector, *at_target(board, 0, shift, **turn_to))
        for now in (0.0, 1.0, 2.0):
            event, hints = g.update(v, n, [], now)
            assert event == "move", (want, event, hints)
        assert want in hints, (want, hints)


@pytest.mark.parametrize("k, want, edge", [(5, "tilt left side away", "left"), (6, "tilt right side away", "right"),
                                           (7, "tilt top away", "top"), (8, "tilt bottom away", "bottom")])
def test_tilt_hints_name_the_side_that_must_go_away(board, detector, k, want, edge):
    g = c.Guide(board, SIZE)
    g.i = k
    v, n = seen(board, detector, *at_target(board, k, yaw=0, pitch=0))   # held flat at the tilted target's spot
    matched, hints = g.check(v, n)
    assert not matched and want in hints, hints
    # and the target really has that side away from the camera: its edge is the shorter one in the image
    q = g.target()["quad"]                                                # corners: top-left, top-right, bottom-right, bottom-left
    length = lambda a, b: float(np.linalg.norm(q[a] - q[b]))
    edges = {"left": length(0, 3), "right": length(1, 2), "top": length(0, 1), "bottom": length(3, 2)}
    other = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}[edge]
    assert edges[edge] < edges[other]


def test_whole_board_needed_away_from_the_corners(board, detector):
    g = c.Guide(board, SIZE)
    z = c.target_pose(board, SIZE, c.TARGETS[0])[1][2]
    v, n = seen(board, detector, *at_target(board, 0, (0.62 * z, 0, 0)))  # half the board past the right edge
    assert n < c.FULL_CORNERS
    event, hints = g.update(v, n, [], 0.0)
    assert event == "move" and hints == ["show the whole board"]


def test_verdict_labels(board, all_views, monkeypatch):
    """RMS and uncertainty that are too big say TOO HIGH; too little coverage says TOO LOW."""
    monkeypatch.setattr(common, "save_calibration", lambda *a, **k: None)
    views = [v for v, _ in all_views[:3]]                                 # three views: little coverage
    K = np.array([[900.0, 0, 640], [0, 900.0, 360], [0, 0, 1]])
    result = (1.4, K, np.zeros(5), np.array([20.0, 20.0, 3.0, 3.0]), np.zeros(len(views)))
    out = io.StringIO()
    with redirect_stdout(out):
        c.report_and_save(views, SIZE, result, types.SimpleNamespace(name="labeltest", square_mm=29.8), "frames")
    text = out.getvalue()
    for row, label in (("RMS error", "TOO HIGH"), ("Uncertainty", "TOO HIGH"), ("Image coverage", "TOO LOW")):
        line = next(l for l in text.splitlines() if row in l)
        assert label in line, line
    assert "TOO LOW" not in next(l for l in text.splitlines() if "Uncertainty" in l)
