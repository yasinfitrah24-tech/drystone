r"""Synthetic PLACEHOLDER photos for the judges' web page, until real sample photos are taken.

Renders grey boxes with their ArUco markers through the real laptop calibration (1280x720), so the
service reads them with the same OpenCV code as a real photo. No room, no faces. Replace them with real
photos (tools/capture_sample.py) before submitting, and remove "placeholder" from web/samples/samples.json.

    python tools/make_placeholder_samples.py
"""
import json
import os

import cv2
import numpy as np

import common
from predict_test import load_catalog

OUT_DIR = os.path.join(common.ROOT, "web", "samples")
MARKER_M = common.BOX_MARKER_MM / 1000.0
QUIET_M = MARKER_M * 1.25            # white paper around the printed marker
# Base marker pose in the camera: about 1 m away, low in the picture, camera above, looking ~12 deg down
TILT_DEG = -12.0
BASE_T = np.array([-0.05, 0.20, 1.0])


def camera_pose():
    a = np.radians(TILT_DEG)
    flip = np.diag([1.0, -1.0, -1.0])               # marker frame (x right, y up, z to camera) -> camera frame
    tilt = np.array([[1, 0, 0], [0, np.cos(a), np.sin(a)], [0, -np.sin(a), np.cos(a)]])
    return tilt @ flip, BASE_T


def to_px(pts, R, t, K, dist):
    cam = (R @ np.asarray(pts, float).T).T + t
    px, _ = cv2.projectPoints(cam, np.zeros(3), np.zeros(3), K, dist)
    return px.reshape(-1, 2), cam


def render(stack, catalog, K, dist, size, label):
    """stack: boxes {"id", "x"} (metres, x of the box centre relative to the bottom box), bottom first."""
    R, t = camera_pose()
    img = np.full((size[1], size[0], 3), 236, np.uint8)
    floor_y = to_px([[0, -catalog[0]["H"] / 2, 0]], R, t, K, dist)[0][0][1]
    img[int(floor_y):] = 205                         # table top
    # faces as corner indices (index = 4*x + 2*y + z bit), outward normal, grey level
    face_defs = (((1, 5, 7, 3), (0, 0, 1), 168), ((2, 6, 7, 3), (0, 1, 0), 196),
                 ((4, 6, 7, 5), (1, 0, 0), 140), ((0, 2, 3, 1), (-1, 0, 0), 140))
    faces = []                                       # (distance, polygon, grey, front-face marker or None)
    y = 0.0                                          # box centre height = marker centre height (base marker = 0)
    for b in stack:
        c = catalog[b["id"]]
        hx, hy, hz = c["L"] / 2, c["H"] / 2, c["D"] / 2
        corners = [[b["x"] + sx * hx, y + sy * hy, -hz + sz * hz]          # front face (marker) at z = 0
                   for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        px, cam = to_px(corners, R, t, K, dist)
        for idx, normal, grey in face_defs:
            centre = cam[list(idx)].mean(axis=0)
            if (R @ np.array(normal, float)) @ centre < 0:                # facing the camera
                marker = (b["id"], b["x"], y) if normal == (0, 0, 1) else None
                faces.append((float(np.linalg.norm(centre)), px[list(idx)], grey, marker))
        y += c["H"]
    for _, poly, grey, marker in sorted(faces, key=lambda f: -f[0]):
        cv2.fillConvexPoly(img, poly.astype(np.int32), (grey, grey - 6, grey - 14), cv2.LINE_AA)
        cv2.polylines(img, [poly.astype(np.int32)], True, (90, 90, 95), 1, cv2.LINE_AA)
        if marker:
            draw_marker(img, *marker, R, t, K, dist)
    cv2.putText(img, label, (16, size[1] - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 60, 60), 1, cv2.LINE_AA)
    return cv2.GaussianBlur(img, (3, 3), 0)


def draw_marker(img, marker_id, x, y, R, t, K, dist):
    side = 400
    m = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(common.BOX_DICT), marker_id, side)
    pad = int(side * (QUIET_M / MARKER_M - 1) / 2)
    m = cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    h = QUIET_M / 2
    dst, _ = to_px([[x - h, y + h, 0], [x + h, y + h, 0], [x + h, y - h, 0], [x - h, y - h, 0]], R, t, K, dist)
    n = m.shape[0]
    H = cv2.getPerspectiveTransform(np.float32([[0, 0], [n, 0], [n, n], [0, n]]), dst.astype(np.float32))
    warped = cv2.warpPerspective(cv2.cvtColor(m, cv2.COLOR_GRAY2BGR), H, (img.shape[1], img.shape[0]),
                                 flags=cv2.INTER_AREA)
    mask = cv2.warpPerspective(np.full((n, n), 255, np.uint8), H, (img.shape[1], img.shape[0]))
    img[mask > 127] = warped[mask > 127]


def main():
    K, dist, size = common.load_calibration(os.path.join(common.DATA_DIR, "camera_laptop.yaml"))
    catalog = load_catalog(os.path.join(common.ROOT, "config", "boxes.json"))
    with open(os.path.join(OUT_DIR, "samples.json"), encoding="utf-8") as f:
        samples = json.load(f)["samples"]
    for s in samples:
        stack = [{"id": i, "x": x_cm / 100.0} for i, x_cm in s["render"]]
        img = render(stack, catalog, K, dist, size, "PLACEHOLDER IMAGE (synthetic render)")
        path = os.path.join(OUT_DIR, f"{s['id']}.jpg")
        cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        print(f"{path}: {len(stack)} box(es), {os.path.getsize(path) // 1024} KB")


if __name__ == "__main__":
    main()
