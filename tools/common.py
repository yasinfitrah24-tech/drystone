"""Shared settings and helpers for the Drystone hardware tests (OpenCV 5)."""
import glob
import os
import sys

import cv2
import numpy as np

# These match the print sheet docs/print/charuco_A4.pdf
# Calibration verdict: stored as `quality` in camera_<name>.yaml with the original values (LAYAK / ULANGI), so
# files made before the English text still load; the user sees PASS / RETRY.
CALIB_PASS = "LAYAK"
VERDICT_TEXT = {"LAYAK": "PASS", "ULANGI": "RETRY"}
BOARD_SQUARES = (7, 5)               # ChArUco board: columns, rows
BOARD_SQUARE_MM = 30.0               # nominal square size; pass the measured value with --square-mm
BOARD_MARKER_RATIO = 22.0 / 30.0     # board marker size / square size
BOARD_DICT = cv2.aruco.DICT_5X5_100
BOX_DICT = cv2.aruco.DICT_4X4_50     # box markers, IDs 0-11
BOX_MARKER_MM = 80.0                 # nominal box-marker size; pass the measured value with --marker-mm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")


def make_board(square_mm):
    s = square_mm / 1000.0
    return cv2.aruco.CharucoBoard(BOARD_SQUARES, s, s * BOARD_MARKER_RATIO,
                                  cv2.aruco.getPredefinedDictionary(BOARD_DICT))


def make_marker_detector():
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX   # sub-pixel corners = better pose
    return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(BOX_DICT), params)


def open_camera(source, width, height):
    cap = cv2.VideoCapture(int(source) if str(source).isdigit() else source)
    if not cap.isOpened():
        sys.exit(f"Camera '{source}' cannot be opened.")
    if width and height:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    ok, frame = cap.read()
    if not ok:
        sys.exit("The camera is open but sends no images.")
    print(f"Camera on: {frame.shape[1]}x{frame.shape[0]}")
    return cap


def list_images(pattern):
    paths = sorted(glob.glob(pattern))
    if not paths:
        sys.exit(f"No files match: {pattern}")
    return paths


def read_image(path):
    # cv2.imread fails on Windows paths with non-ASCII characters, so decode from bytes instead
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        sys.exit(f"Could not read the image: {path}")
    return img


def save_calibration(path, K, dist, size, rms, views, square_mm, extra=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fs = cv2.FileStorage(path, cv2.FILE_STORAGE_WRITE)
    fs.write("image_width", int(size[0]))
    fs.write("image_height", int(size[1]))
    fs.write("camera_matrix", K)
    fs.write("dist_coeffs", dist)
    fs.write("rms_px", float(rms))
    fs.write("views", int(views))
    fs.write("square_mm", float(square_mm))
    for key, value in (extra or {}).items():
        fs.write(key, value)
    fs.release()


def load_calibration(path):
    if not os.path.exists(path):
        sys.exit(f"Calibration file not found: {path}. Run tools/calibrate.py first.")
    fs = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
    K = fs.getNode("camera_matrix").mat()
    dist = fs.getNode("dist_coeffs").mat()
    size = (int(fs.getNode("image_width").real()), int(fs.getNode("image_height").real()))
    node = fs.getNode("quality")
    quality = "" if node.isNone() else node.string()
    fs.release()
    if quality != CALIB_PASS:
        print(f"WARNING: {os.path.basename(path)} has not passed the calibration quality check "
              f"({VERDICT_TEXT.get(quality, quality) or 'not checked'}). Positions may be off. "
              "Run tools/calibrate.py again until the verdict is PASS.")
    return K, dist, size


def check_size(img, calib_size, what):
    size = (img.shape[1], img.shape[0])
    if size != tuple(calib_size):
        sys.exit(f"Resolution of {what} {size[0]}x{size[1]} differs from the calibration {calib_size[0]}x{calib_size[1]}. "
                 "Use the same camera and resolution, or calibrate again.")
