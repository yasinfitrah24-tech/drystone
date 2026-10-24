"""A synthetic camera photo of the ChArUco calibration board at a given pose (for the calibrate.py guided-mode tests).

The real board image (common.make_board) is warped onto the image with the plane homography K [r1 r2 t], so the
detector sees what a camera with intrinsics K would see. No lens distortion. The warp runs at 4x the resolution and is
then averaged down, as a camera sensor integrates light over each pixel: a direct warp shifts the detected corners
slightly and biases the focal length (by up to 2% for a small board, measured 24 Okt).
"""
import cv2
import numpy as np

import common

PX = 3200            # width of the board image that is warped
SS = 4               # supersampling factor


def render_board(board, R, tvec, K, size, bg=168):
    cols, rows = board.getChessboardSize()
    s = board.getSquareLength()
    bw, bh = cols * s, rows * s
    pw, ph = PX, int(round(PX * bh / bw))
    art = board.generateImage((pw, ph), marginSize=0)
    A = np.array([[bw / pw, 0, 0], [0, bh / ph, 0], [0, 0, 1]])            # board-image pixel -> board plane
    S = np.diag([SS, SS, 1.0])                                            # image pixel -> supersampled pixel
    H = S @ K @ np.column_stack([R[:, 0], R[:, 1], tvec]) @ A
    big = (size[0] * SS, size[1] * SS)
    out = np.full((big[1], big[0]), bg, np.uint8)
    warped = cv2.warpPerspective(art, H, big, flags=cv2.INTER_LINEAR)
    mask = cv2.warpPerspective(np.full((ph, pw), 255, np.uint8), H, big) > 127
    out[mask] = warped[mask]
    out = cv2.resize(out, size, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def camera(size, f):
    return np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1]], float)


def default_board():
    return common.make_board(29.8)
