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
             ((0, 0.20 * z, 0), {}, "move up"),     # (small enough to keep the whole board in view)
             ((0, -0.20 * z, 0), {}, "move down"),
             ((0, 0, 0.5 * z), {}, "closer"),
             ((0, 0, -0.3 * z), {}, "further"),
             ((0, 0, 0), {"yaw": -25}, "face the camera")]
    for shift, turn_to, want in cases:
        v, n = seen(board, detector, *at_target(board, 0, shift, **turn_to))
        for now in (0.0, 1.0, 2.0):
            event, hints = g.update(v, n, [], now)
            assert event == "move", (want, event, hints)
        assert want in hints, (want, hints)


@pytest.mark.parametrize("k, want, edge", [(5, "pull the left edge toward you", "left"),
                                           (6, "pull the right edge toward you", "right"),
                                           (7, "pull the top edge toward you", "top"),
                                           (8, "pull the bottom edge toward you", "bottom")])
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
    v, n = seen(board, detector, *at_target(board, 0, (0.70 * z, 0, 0)))  # most of the board past the right edge
    assert v is not None and n < c.FULL_CORNERS                       # seen, but less than half of it
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


def test_side_target_needs_a_tilt_that_counts_for_the_verdict(board, detector):
    """Within the loose tolerance but under MIN_TILT_DEG for the verdict: no match, "tilt more"."""
    g = c.Guide(board, SIZE)
    g.i = 5                                                                # left edge, left side away (yaw -30)
    v, n = seen(board, detector, *at_target(board, 5, yaw=-15))
    assert "left" not in c.tilt_sides(v.normal)
    matched, hints = g.check(v, n)
    assert not matched and "pull the left edge a bit more toward you" in hints, hints
    v, n = seen(board, detector, *at_target(board, 5, yaw=-26))
    matched, hints = g.check(v, n)
    assert matched and "left" in c.tilt_sides(v.normal), hints


def test_mirrored_window_speaks_in_what_the_person_sees(board, detector, monkeypatch):
    monkeypatch.setattr(c, "MIRROR", True)
    g = c.Guide(board, SIZE)
    z = c.target_pose(board, SIZE, c.TARGETS[0])[1][2]
    v, n = seen(board, detector, *at_target(board, 0, (0.30 * z, 0, 0)))   # board on the camera image's right
    assert "move right" in g.check(v, n)[1]                                  # = the mirror's left: move it right
    g.i = 5
    v, n = seen(board, detector, *at_target(board, 5, yaw=0, pitch=0))
    assert "pull the right edge toward you" in g.check(v, n)[1]              # the camera's left side is the mirror's right
    assert c.say("top-left corner") == "top-right corner" and c.say("top away") == "top away"
    # the drawing: the target on the camera image's left edge shows up on the right half of the window
    frame = np.zeros((SIZE[1], SIZE[0], 3), np.uint8)
    canvas = c.draw_guide(frame, [], None, None, 0, SIZE, None, "keys", "title", guide=g)
    blue = np.all(canvas == hud_brand(), axis=2)
    xs = np.nonzero(blue)[1]
    assert xs.size and xs.mean() > SIZE[0] / 2


def hud_brand():
    import agent_hud
    return np.array(agent_hud.BGR["BRAND"], np.uint8)


def test_square_mm_note_only_when_the_option_is_missing(tmp_path):
    import os
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run = lambda *extra: subprocess.run([sys.executable, "tools/calibrate.py", "--name", "notetest", "--images",
                                         str(tmp_path / "none" / "*.jpg"), *extra], cwd=root, capture_output=True,
                                        text=True, timeout=120).stdout
    assert "--square-mm not given" not in run("--square-mm", "30")
    assert "--square-mm not given" in run()


def test_wrong_way_round_says_which_edge_and_the_gauge_shows_it(board, detector):
    """Target 8 wants the top edge away from the camera; held the other way round (bottom away, as in a hand test on
    24 Okt), the hint names the top edge and the gauge reads below 0."""
    g = c.Guide(board, SIZE)
    g.i = 7
    v, n = seen(board, detector, *at_target(board, 7, pitch=30))
    matched, hints = g.check(v, n)
    assert not matched and "pull the top edge toward you" in hints, hints
    assert c.turn(v.guide_normal)[1] > 20                                  # the bottom edge is the one away now
    frame = np.zeros((SIZE[1], SIZE[0], 3), np.uint8)
    canvas = c.draw_guide(frame, [], v, None, 0, SIZE, None, "keys", "title", guide=g)
    assert canvas.shape == frame.shape
    assert "toward you" not in c.tilt_text(v.normal) and "away from the camera" in c.tilt_text(v.normal)


def test_skip_hint_after_a_while_on_one_target(board, detector):
    g = c.Guide(board, SIZE)
    g.i = 7
    v, n = seen(board, detector, *at_target(board, 7, pitch=30))
    assert not any("N skips" in h for h in g.update(v, n, [], now=100.0)[1])
    assert not any("N skips" in h for h in g.update(v, n, [], now=100.0 + c.SKIP_HINT_SEC - 1)[1])
    assert any("N skips" in h for h in g.update(v, n, [], now=100.0 + c.SKIP_HINT_SEC)[1])
    g.next()                                                               # a new target: the clock starts again
    assert not any("N skips" in h for h in g.update(v, n, [], now=200.0)[1])


@pytest.mark.parametrize("skip", range(len(c.TARGETS)))
def test_one_skipped_target_still_passes(board, all_views, skip):
    """On clean synthetic photos, any single target can be skipped and the verdict is still PASS (real prints are
    noisier: this shows the skip itself is not what fails a calibration)."""
    views = [v for k, (v, _) in enumerate(all_views) if k != skip]
    rms, K, dist, sd, _ = c.calibrate(views, SIZE)
    assert c.assess(views, SIZE, rms, K, sd)[0] == common.CALIB_PASS
