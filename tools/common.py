"""Shared settings and helpers for the Drystone hardware tests (OpenCV 5)."""
import glob
import os
import sys

import cv2
import numpy as np

# These match the print sheet opencv_marker_kalibrasi.pdf
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
        sys.exit(f"Kamera '{source}' tidak bisa dibuka.")
    if width and height:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    ok, frame = cap.read()
    if not ok:
        sys.exit("Kamera terbuka tapi tidak mengirim gambar.")
    print(f"Kamera aktif: {frame.shape[1]}x{frame.shape[0]}")
    return cap


def list_images(pattern):
    paths = sorted(glob.glob(pattern))
    if not paths:
        sys.exit(f"Tidak ada file yang cocok dengan: {pattern}")
    return paths


def read_image(path):
    # cv2.imread fails on Windows paths with non-ASCII characters, so decode from bytes instead
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        sys.exit(f"Gagal membaca gambar: {path}")
    return img


def save_calibration(path, K, dist, size, rms, views, square_mm):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fs = cv2.FileStorage(path, cv2.FILE_STORAGE_WRITE)
    fs.write("image_width", int(size[0]))
    fs.write("image_height", int(size[1]))
    fs.write("camera_matrix", K)
    fs.write("dist_coeffs", dist)
    fs.write("rms_px", float(rms))
    fs.write("views", int(views))
    fs.write("square_mm", float(square_mm))
    fs.release()


def load_calibration(path):
    if not os.path.exists(path):
        sys.exit(f"File kalibrasi tidak ada: {path}. Jalankan tools/calibrate.py dulu.")
    fs = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
    K = fs.getNode("camera_matrix").mat()
    dist = fs.getNode("dist_coeffs").mat()
    size = (int(fs.getNode("image_width").real()), int(fs.getNode("image_height").real()))
    fs.release()
    return K, dist, size


def check_size(img, calib_size, what):
    size = (img.shape[1], img.shape[0])
    if size != tuple(calib_size):
        sys.exit(f"Resolusi {what} {size[0]}x{size[1]} beda dengan kalibrasi {calib_size[0]}x{calib_size[1]}. "
                 "Pakai kamera dan resolusi yang sama, atau kalibrasi ulang.")
