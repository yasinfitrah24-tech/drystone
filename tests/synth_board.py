"""A synthetic camera photo of the ChArUco calibration board at a given pose (for the calibrate.py guided-mode tests).

The real board image (common.make_board) is warped onto the image with the plane homography K [r1 r2 t], so the
detector sees what a camera with intrinsics K would see. No lens distortion.
"""
import cv2
import numpy as np

import common

PX = 1600            # width of the board image that is warped (enough detail for the detector)


def render_board(board, R, tvec, K, size, bg=168):
    cols, rows = board.getChessboardSize()
    s = board.getSquareLength()
    bw, bh = cols * s, rows * s
    pw, ph = PX, int(round(PX * bh / bw))
    art = board.generateImage((pw, ph), marginSize=0)
    A = np.array([[bw / pw, 0, 0], [0, bh / ph, 0], [0, 0, 1]])            # board-image pixel -> board plane
    H = K @ np.column_stack([R[:, 0], R[:, 1], tvec]) @ A
    out = np.full((size[1], size[0]), bg, np.uint8)
    warped = cv2.warpPerspective(art, H, size, flags=cv2.INTER_AREA)
    mask = cv2.warpPerspective(np.full((ph, pw), 255, np.uint8), H, size) > 127
    out[mask] = warped[mask]
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def camera(size, f):
    return np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1]], float)


def default_board():
    return common.make_board(29.8)
