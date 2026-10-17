"""Synthetic camera photos of boxes in any pose (upright, lying, off the stack), through the real calibration.

Test helper: renders grey boxes with their ArUco markers, so the same OpenCV reading as on real photos runs.
Coordinates are metres in the bottom box's marker frame (x right, y up, z toward the camera), as in agent.py.
"""
import os

import cv2
import numpy as np

import common
from make_placeholder_samples import QUIET_M, MARKER_M, camera_pose, to_px
from predict_test import load_catalog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = load_catalog(os.path.join(ROOT, "config", "boxes.json"))
K, DIST, SIZE = common.load_calibration(os.path.join(ROOT, "data", "camera_laptop.yaml"))
FLOOR_Y = -CATALOG[0]["H"] / 2          # bottom box marker sits at mid-height of its front face


def rot_z(deg):
    """Rotation about the camera-facing axis: 90 = box lying on its side, marker still facing the camera."""
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1.0]])


def rot_y(deg):
    """Rotation about the vertical axis (box turned)."""
    a = np.radians(deg)
    return np.array([[np.cos(a), 0, np.sin(a)], [0, 1.0, 0], [-np.sin(a), 0, np.cos(a)]])


def upright(box_id, x, level=None, y=None, z_front=0.0):
    """Upright box with its front face at z_front. level = how many boxes below it (0 = on the floor)."""
    H = CATALOG[box_id]["H"]
    if y is None:
        y = FLOOR_Y + sum(CATALOG[i]["H"] for i in range(level or 0)) + H / 2 if level else FLOOR_Y + H / 2
    return {"id": box_id, "c": np.array([x, y, z_front - CATALOG[box_id]["D"] / 2]), "R": np.eye(3)}


def lying_on_side(box_id, x, z_front=0.0):
    """Box tipped over sideways onto the floor: length vertical, marker still facing the camera, turned 90 deg."""
    L = CATALOG[box_id]["L"]
    return {"id": box_id, "c": np.array([x, FLOOR_Y + L / 2, z_front - CATALOG[box_id]["D"] / 2]), "R": rot_z(90)}


def render(boxes, shift_px=0):
    R, t = camera_pose()
    img = np.full((SIZE[1], SIZE[0], 3), 236, np.uint8)
    floor_px = to_px([[0, FLOOR_Y, 0]], R, t, K, DIST)[0][0][1]
    img[int(floor_px):] = 205
    faces = []
    for b in boxes:
        c = CATALOG[b["id"]]
        h = np.array([c["L"], c["H"], c["D"]]) / 2
        local = np.array([[sx * h[0], sy * h[1], sz * h[2]] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
        world = (b["R"] @ local.T).T + b["c"]
        px, cam = to_px(world, R, t, K, DIST)
        for idx, normal, grey in (((1, 5, 7, 3), (0, 0, 1), 168), ((0, 4, 6, 2), (0, 0, -1), 150),
                                  ((2, 6, 7, 3), (0, 1, 0), 196), ((0, 4, 5, 1), (0, -1, 0), 120),
                                  ((4, 6, 7, 5), (1, 0, 0), 140), ((0, 2, 3, 1), (-1, 0, 0), 140)):
            centre = cam[list(idx)].mean(axis=0)
            if (R @ b["R"] @ np.array(normal, float)) @ centre < 0:
                faces.append((float(np.linalg.norm(centre)), px[list(idx)], grey, b if normal == (0, 0, 1) else None))
    for _, poly, grey, marker_box in sorted(faces, key=lambda f: -f[0]):
        cv2.fillConvexPoly(img, poly.astype(np.int32), (grey, grey - 6, grey - 14), cv2.LINE_AA)
        cv2.polylines(img, [poly.astype(np.int32)], True, (90, 90, 95), 1, cv2.LINE_AA)
        if marker_box is not None:
            _marker(img, marker_box, R, t)
    if shift_px:
        img = np.roll(img, shift_px, axis=1)
    return cv2.GaussianBlur(img, (3, 3), 0)


def _marker(img, b, R, t):
    side = 400
    m = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(common.BOX_DICT), b["id"], side)
    pad = int(side * (QUIET_M / MARKER_M - 1) / 2)
    m = cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    q, d = QUIET_M / 2, CATALOG[b["id"]]["D"] / 2
    local = np.array([[-q, q, d], [q, q, d], [q, -q, d], [-q, -q, d]])
    dst, _ = to_px((b["R"] @ local.T).T + b["c"], R, t, K, DIST)
    n = m.shape[0]
    H = cv2.getPerspectiveTransform(np.float32([[0, 0], [n, 0], [n, n], [0, n]]), dst.astype(np.float32))
    size = (img.shape[1], img.shape[0])
    warped = cv2.warpPerspective(cv2.cvtColor(m, cv2.COLOR_GRAY2BGR), H, size, flags=cv2.INTER_AREA)
    mask = cv2.warpPerspective(np.full((n, n), 255, np.uint8), H, size)
    img[mask > 127] = warped[mask > 127]
