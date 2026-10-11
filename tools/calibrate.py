r"""Kalibrasi kamera dengan papan ChArUco (halaman 1 opencv_marker_kalibrasi.pdf).

Ukur dulu sisi satu kotak hitam papan hasil cetak (misalnya 29.8 mm), lalu:

Webcam laptop:
    python tools/calibrate.py --name laptop --square-mm 29.8

Foto dari HP (15-25 foto papan, zoom 1x, orientasi sama, taruh di data/calib_hp/):
    python tools/calibrate.py --name hp --square-mm 29.8 --images "data/calib_hp/*.jpg"

Tombol di jendela kamera: SPASI = simpan frame, C = hitung kalibrasi, Q = keluar.
Ambil 15-25 frame yang beda-beda: dekat dan jauh, papan dimiringkan ke kiri/kanan/atas/bawah,
papan di tengah dan di pojok-pojok gambar. Papan harus rata (tempel di karton/buku keras).
"""
import argparse
import os
import sys

import cv2
import numpy as np

import common

MIN_CORNERS = 8     # ChArUco corners needed to keep a view
MIN_VIEWS = 10


def detect(detector, img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _, _ = detector.detectBoard(gray)
    return corners, ids, (0 if ids is None else len(ids))


def calibrate(board, views, size):
    obj_pts, img_pts, used = [], [], []
    for k, (corners, ids) in enumerate(views):
        o, i = board.matchImagePoints(corners, ids)
        if o is not None and len(o) >= MIN_CORNERS:
            obj_pts.append(o.astype(np.float32))
            img_pts.append(i.astype(np.float32))
            used.append(k + 1)
    if len(obj_pts) < MIN_VIEWS:
        print(f"Baru {len(obj_pts)} view yang bisa dipakai, butuh minimal {MIN_VIEWS}.")
        return None
    # k3 is left out: with 15-25 views it tends to overfit on ordinary webcams and phone cameras
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(obj_pts, img_pts, size, None, None, flags=cv2.CALIB_FIX_K3)
    per_view = []
    for o, i, r, t in zip(obj_pts, img_pts, rvecs, tvecs):
        proj, _ = cv2.projectPoints(o, r, t, K, dist)
        diff = proj.reshape(-1, 2) - i.reshape(-1, 2)    # OpenCV 5 returns (N,2) here, projectPoints (N,1,2)
        per_view.append(float(np.sqrt(np.mean(np.sum(diff ** 2, axis=1)))))
    return rms, K, dist, per_view, used


def report_and_save(result, size, args):
    rms, K, dist, per_view, used = result
    print("\n=== Hasil kalibrasi ===")
    print(f"View dipakai  : {len(used)}")
    print(f"RMS error     : {rms:.3f} px  (bagus < 0.5, cukup < 1.0, di atas 1.0 ulangi)")
    print(f"fx, fy        : {K[0, 0]:.1f}, {K[1, 1]:.1f}  (harusnya hampir sama)")
    print(f"cx, cy        : {K[0, 2]:.1f}, {K[1, 2]:.1f}  (gambar {size[0]}x{size[1]})")
    print("Distorsi      : " + ", ".join(f"{v:.4f}" for v in dist.ravel()[:5]))
    worst = np.argsort(per_view)[::-1][:3]
    print("View terburuk : " + ", ".join(f"#{used[i]} ({per_view[i]:.2f} px)" for i in worst))
    out = os.path.join(common.DATA_DIR, f"camera_{args.name}.yaml")
    common.save_calibration(out, K, dist, size, rms, len(used), args.square_mm)
    print(f"Tersimpan     : {out}\n")


def run_images(args, board, detector):
    views, size = [], None
    for p in common.list_images(args.images):
        img = common.read_image(p)
        s = (img.shape[1], img.shape[0])
        if size is None:
            size = s
        elif s != size:
            sys.exit(f"Ukuran {os.path.basename(p)} beda ({s[0]}x{s[1]} vs {size[0]}x{size[1]}). "
                     "Semua foto harus dari kamera, zoom, dan orientasi yang sama.")
        corners, ids, n = detect(detector, img)
        print(f"{os.path.basename(p)}: {n} sudut")
        if n >= MIN_CORNERS:
            views.append((corners, ids))
    result = calibrate(board, views, size)
    if result:
        report_and_save(result, size, args)


def run_camera(args, board, detector):
    cap = common.open_camera(args.source, args.width, args.height)
    save_dir = os.path.join(common.DATA_DIR, f"calib_{args.name}")
    os.makedirs(save_dir, exist_ok=True)
    views, size = [], None
    print("SPASI = simpan frame, C = hitung kalibrasi, Q = keluar")
    while True:
        ok, frame = cap.read()
        if not ok:
            print("Kamera berhenti mengirim gambar.")
            break
        size = (frame.shape[1], frame.shape[0])
        corners, ids, n = detect(detector, frame)
        view = frame.copy()
        if n:
            # OpenCV 5 returns (N,2) corners and (N,) ids; the drawing function wants (N,1,2) and (N,1)
            cv2.aruco.drawDetectedCornersCharuco(view, corners.reshape(-1, 1, 2).astype(np.float32),
                                                 ids.reshape(-1, 1).astype(np.int32), (0, 255, 0))
        color = (0, 180, 0) if n >= MIN_CORNERS else (0, 0, 255)
        cv2.putText(view, f"sudut: {n}   tersimpan: {len(views)}   SPASI simpan | C hitung | Q keluar",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
        cv2.imshow("Kalibrasi ChArUco", view)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" "):
            if n >= MIN_CORNERS:
                views.append((corners, ids))
                cv2.imwrite(os.path.join(save_dir, f"{len(views):02d}.png"), frame)
                print(f"Frame {len(views)} disimpan ({n} sudut)")
            else:
                print(f"Belum disimpan: baru {n} sudut terbaca, butuh minimal {MIN_CORNERS}.")
        elif key in (ord("c"), ord("C")):
            result = calibrate(board, views, size)
            if result:
                report_and_save(result, size, args)
        elif key in (ord("q"), ord("Q"), 27):
            break
    cap.release()
    cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description="Kalibrasi kamera dengan papan ChArUco")
    ap.add_argument("--name", required=True, help="nama kamera, misalnya laptop atau hp")
    ap.add_argument("--square-mm", type=float, default=common.BOARD_SQUARE_MM,
                    help="sisi satu kotak papan hasil cetak, dalam mm")
    ap.add_argument("--images", help='pola file foto, misalnya "data/calib_hp/*.jpg"')
    ap.add_argument("--source", default="0", help="indeks webcam (0, 1, ...) atau URL kamera")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    args = ap.parse_args()
    if args.square_mm == common.BOARD_SQUARE_MM:
        print("Catatan: --square-mm tidak diisi, dipakai 30.0 mm. Ukur hasil cetak supaya akurat.")
    board = common.make_board(args.square_mm)
    detector = cv2.aruco.CharucoDetector(board)
    if args.images:
        run_images(args, board, detector)
    else:
        run_camera(args, board, detector)


if __name__ == "__main__":
    main()
