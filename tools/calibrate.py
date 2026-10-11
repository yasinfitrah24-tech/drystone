r"""Kalibrasi kamera dengan papan ChArUco (halaman 1 opencv_marker_kalibrasi.pdf).

Siapkan papan dulu: tempel kertasnya di bidang keras dan rata (sampul buku hardcover, papan klip,
karton tebal) dengan selotip di keempat sisi, lalu ukur sisi satu kotak hitam (misalnya 29.8 mm).
Kertas yang melengkung membuat kalibrasi gagal, dan tidak bisa diperbaiki oleh model lensa apa pun.

Webcam laptop, sendirian (disarankan): frame tersimpan sendiri tiap papan ditahan diam +-1 detik
    python tools/calibrate.py --name laptop --square-mm 29.8 --auto

Webcam laptop, ada yang menekan SPASI:
    python tools/calibrate.py --name laptop --square-mm 29.8

Foto dari HP (15-25 foto papan, zoom 1x, orientasi sama, taruh di data/calib_hp/):
    python tools/calibrate.py --name hp --square-mm 29.8 --images "data/calib_hp/*.jpg"

Panduan di jendela kamera:
  - kotak hijau = bagian gambar yang sudah terisi sudut papan. Isi minimal 9 dari 12 kotak,
    terutama pojok dan tepi gambar.
  - miring = perkiraan sudut papan terhadap kamera. Usahakan tiap arah (kiri, kanan, atas, bawah)
    punya frame dengan papan miring 20-40 derajat.
  - frame yang hampir sama dengan frame yang sudah tersimpan ditolak.
Tombol: SPASI = simpan frame, C = hitung kalibrasi, Q = keluar.

Setiap hasil diberi vonis. LAYAK disimpan ke data/camera_<nama>.yaml. ULANGI disimpan ke
data/camera_<nama>_draft.yaml beserta daftar perbaikannya, supaya kalibrasi LAYAK yang lama
tidak tertimpa.
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

import common

MIN_CORNERS = 8          # ChArUco corners needed to keep a view
MIN_VIEWS = 10           # distinct views needed before calibrating
SAME_SHIFT = 0.05        # a view repeats a saved one if the board outline moved less than 5% of its size
SAME_TURN_DEG = 15.0     # ... and the board turned less than this
MIN_TILT_DEG = 20.0      # a view counts as tilted toward a side from this angle
GRID = (4, 3)            # image coverage grid: columns, rows
CELL_POINTS = 4          # saved corners a grid cell needs to count as covered
MAX_RMS_PX = 1.0
MAX_F_SD_PCT = 1.0       # 1-sigma uncertainty of fx and fy, in percent
MIN_CELLS = 9
STILL_PX = 2.0           # auto mode: corners moving less than this per frame count as held still
STILL_SEC = 0.8          # ... for this long before the frame is saved
SIDES = ("kiri", "kanan", "atas", "bawah")


class BoardView:
    """One detected board: its corners plus what the duplicate check and the guide need."""

    def __init__(self, board, corners, ids, size, name=""):
        self.name = name
        obj, img = board.matchImagePoints(corners, ids)
        self.obj = np.asarray(obj, np.float32).reshape(-1, 3)
        self.img = np.asarray(img, np.float32).reshape(-1, 2)
        self.outline = board_outline(board, self.obj, self.img)
        self.normal = rough_normal(self.obj, self.img, size)


def detect(detector, img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _, _ = detector.detectBoard(gray)
    return corners, ids, (0 if ids is None else len(ids))


def board_outline(board, obj, img):
    """Image position of the board's four outer corners (via the plane homography), or None."""
    cols, rows = board.getChessboardSize()
    s = board.getSquareLength()
    H, _ = cv2.findHomography(obj[:, :2], img, 0)
    if H is None:
        return None
    quad = np.float32([[0, 0], [cols * s, 0], [cols * s, rows * s], [0, rows * s]]).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(quad, H).reshape(-1, 2)


def rough_normal(obj, img, size):
    """Board normal (pointing at the camera) in camera axes, from a pose with a guessed focal length.

    A guess of 0.8 x image width is enough to tell how far and which way the board is turned;
    the real focal length is what the calibration is about to measure."""
    f = 0.8 * size[0]
    K = np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1]])
    ok, rvec, _ = cv2.solvePnP(obj, img, K, None, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        return np.array([0.0, 0.0, -1.0])
    R, _ = cv2.Rodrigues(rvec)
    return -R[:, 2]


def turn(normal):
    """(left-right, up-down) turn in degrees. Negative = the board faces the left / top of the image."""
    yaw = float(np.degrees(np.arctan2(normal[0], -normal[2])))
    pitch = float(np.degrees(np.arctan2(normal[1], -normal[2])))
    return yaw, pitch


def tilt_sides(normal):
    yaw, pitch = turn(normal)
    hits = (yaw <= -MIN_TILT_DEG, yaw >= MIN_TILT_DEG, pitch <= -MIN_TILT_DEG, pitch >= MIN_TILT_DEG)
    return {side for side, hit in zip(SIDES, hits) if hit}


def tilt_text(normal):
    yaw, pitch = turn(normal)
    return (f"miring {'kiri' if yaw < 0 else 'kanan'} {abs(yaw):.0f}, "
            f"{'atas' if pitch < 0 else 'bawah'} {abs(pitch):.0f} derajat")


def find_repeat(view, saved):
    """The saved view this one practically repeats (same place, same tilt), or None."""
    if view.outline is None:
        return None
    for s in saved:
        if s.outline is None:
            continue
        move = np.mean(np.linalg.norm(view.outline - s.outline, axis=1))
        size_px = 0.5 * (np.linalg.norm(view.outline[0] - view.outline[2]) +
                         np.linalg.norm(s.outline[0] - s.outline[2]))
        turned = np.degrees(np.arccos(np.clip(np.dot(view.normal, s.normal), -1.0, 1.0)))
        if move / size_px < SAME_SHIFT and turned < SAME_TURN_DEG:
            return s
    return None


def coverage(views, size):
    """Boolean grid (rows x columns): which parts of the image the saved corners cover."""
    counts = np.zeros((GRID[1], GRID[0]), int)
    for v in views:
        col = np.clip((v.img[:, 0] * GRID[0] / size[0]).astype(int), 0, GRID[0] - 1)
        row = np.clip((v.img[:, 1] * GRID[1] / size[1]).astype(int), 0, GRID[1] - 1)
        np.add.at(counts, (row, col), 1)
    return counts >= CELL_POINTS


def calibrate(views, size):
    if len(views) < MIN_VIEWS:
        print(f"Baru {len(views)} posisi papan yang berbeda, butuh minimal {MIN_VIEWS}.")
        return None
    obj = [v.obj for v in views]
    img = [v.img for v in views]
    # k3 is left out: with 15-25 views it tends to overfit on ordinary webcams and phone cameras
    rms, K, dist, _, _, sd, _, per_view = cv2.calibrateCameraExtended(
        obj, img, size, None, None, flags=cv2.CALIB_FIX_K3)
    return rms, K, dist, np.asarray(sd).ravel(), np.asarray(per_view).ravel()


def assess(views, size, rms, K, sd):
    """Acceptance rules. Returns (verdict, fixes, f_sd_pct, cells, sides)."""
    f_sd = 100.0 * max(sd[0] / K[0, 0], sd[1] / K[1, 1])
    cells = coverage(views, size)
    sides = set().union(*(tilt_sides(v.normal) for v in views))
    missing = [s for s in SIDES if s not in sides]
    fixes = []
    if rms > MAX_RMS_PX:
        fixes.append("RMS terlalu besar: papan belum rata atau gambar blur. Tempel papan di bidang keras, "
                     "tahan diam saat frame diambil, cahaya cukup.")
    if f_sd > MAX_F_SD_PCT:
        # with a bent board the focal length drifts too; then the RMS fix above comes first
        if missing:
            fixes.append("Fokus kamera belum terkunci: miringkan papan 20-40 derajat, terutama ke arah "
                         + ", ".join(missing) + ".")
        elif rms <= MAX_RMS_PX:
            fixes.append("Fokus kamera belum terkunci: miringkan papan lebih jauh (30-40 derajat) dan tambah frame.")
    if cells.sum() < MIN_CELLS:
        fixes.append("Cakupan kurang: taruh papan di bagian '.' pada peta cakupan (pojok dan tepi gambar).")
    return ("ULANGI" if fixes else "LAYAK"), fixes, f_sd, cells, sides


def report_and_save(views, size, result, args, frames_dir):
    rms, K, dist, sd, per_view = result
    verdict, fixes, f_sd, cells, sides = assess(views, size, rms, K, sd)
    mark = lambda good: "OK" if good else "KURANG"
    print("\n=== Hasil kalibrasi ===")
    print(f"View dipakai   : {len(views)} posisi papan berbeda")
    print(f"RMS error      : {rms:.3f} px  {mark(rms <= MAX_RMS_PX)}  (maks {MAX_RMS_PX}, bagus < 0.5)")
    print(f"Ketidakpastian : fx {100 * sd[0] / K[0, 0]:.2f}%, fy {100 * sd[1] / K[1, 1]:.2f}%  "
          f"{mark(f_sd <= MAX_F_SD_PCT)}  (maks {MAX_F_SD_PCT}%)")
    print(f"Cakupan gambar : {cells.sum()}/{cells.size} kotak  {mark(cells.sum() >= MIN_CELLS)}  "
          f"(min {MIN_CELLS}; # = terisi, . = kosong)")
    for row in cells:
        print("                 " + " ".join("#" if c else "." for c in row))
    print(f"Arah miring    : {', '.join(s for s in SIDES if s in sides) or 'belum ada'}  "
          f"(perkiraan, >= {MIN_TILT_DEG:.0f} derajat)")
    print(f"fx, fy         : {K[0, 0]:.1f}, {K[1, 1]:.1f}  (+- {sd[0]:.1f}, {sd[1]:.1f})")
    print(f"cx, cy         : {K[0, 2]:.1f}, {K[1, 2]:.1f}  (+- {sd[2]:.1f}, {sd[3]:.1f}; gambar {size[0]}x{size[1]})")
    print("Distorsi       : " + ", ".join(f"{v:.4f}" for v in dist.ravel()[:5]))
    worst = np.argsort(per_view)[::-1][:3]
    print("View terburuk  : " + ", ".join(f"{views[i].name} ({per_view[i]:.2f} px)" for i in worst))
    print(f"VONIS          : {verdict}")
    for fix in fixes:
        print("  - " + fix)
    if verdict == "LAYAK" and rms > 0.5:
        # simulated: a board sagging 1 mm still passes at ~0.6 px but shifts fx by ~2.5%
        print("  Catatan: RMS di atas 0.5 px biasanya tanda papan kurang rata atau gambar kurang tajam. "
              "Masih boleh dipakai; hasil Tes 1 yang menentukan.")
    name = args.name if verdict == "LAYAK" else f"{args.name}_draft"
    out = os.path.join(common.DATA_DIR, f"camera_{name}.yaml")
    try:
        frames_dir = os.path.relpath(frames_dir, common.ROOT)
    except ValueError:      # Windows: frames on another drive
        pass
    common.save_calibration(out, K, dist, size, rms, len(views), args.square_mm, extra={
        "quality": verdict, "f_sd_pct": float(f_sd), "coverage_cells": int(cells.sum()),
        "tilt_sides": ",".join(s for s in SIDES if s in sides), "frames": frames_dir})
    print(f"Tersimpan      : {out}")
    if verdict != "LAYAK":
        print(f"                 (draft; data/camera_{args.name}.yaml tidak ditimpa)")
    print()
    return verdict


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
        name = os.path.basename(p)
        corners, ids, n = detect(detector, img)
        if n < MIN_CORNERS:
            print(f"{name}: {n} sudut, dilewati (butuh minimal {MIN_CORNERS})")
            continue
        view = BoardView(board, corners, ids, size, name)
        same = find_repeat(view, views)
        if same:
            print(f"{name}: {n} sudut, hampir sama dengan {same.name}, dilewati")
            continue
        views.append(view)
        print(f"{name}: {n} sudut, {tilt_text(view.normal)}")
    result = calibrate(views, size)
    if result:
        report_and_save(views, size, result, args, os.path.dirname(os.path.abspath(args.images)))


def corner_map(corners, ids):
    return {int(i): c for i, c in zip(np.asarray(ids).ravel(), np.asarray(corners).reshape(-1, 2))}


def mean_shift(a, b):
    """Average movement (px) of the ChArUco corners two frames have in common."""
    common_ids = set(a) & set(b)
    if len(common_ids) < 4:
        return float("inf")
    return float(np.mean([np.linalg.norm(a[k] - b[k]) for k in common_ids]))


def put(canvas, text, row, color):
    org = (10, 28 + 30 * row)
    cv2.putText(canvas, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(canvas, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)


def draw_guide(frame, views, cur, corners, ids, n, size, status, keys):
    """Live view: covered grid cells in green, saved corners as dots, current tilt, what is still missing."""
    cells = coverage(views, size)
    cw, ch = size[0] / GRID[0], size[1] / GRID[1]
    canvas = frame.copy()
    if cells.any():
        tint = canvas.copy()
        for r, c in zip(*np.nonzero(cells)):
            cv2.rectangle(tint, (int(c * cw), int(r * ch)), (int((c + 1) * cw), int((r + 1) * ch)), (0, 200, 0), -1)
        canvas = cv2.addWeighted(tint, 0.25, canvas, 0.75, 0)
    for c in range(1, GRID[0]):
        cv2.line(canvas, (int(c * cw), 0), (int(c * cw), size[1]), (210, 210, 210), 1)
    for r in range(1, GRID[1]):
        cv2.line(canvas, (0, int(r * ch)), (size[0], int(r * ch)), (210, 210, 210), 1)
    for v in views:
        for x, y in v.img:
            cv2.circle(canvas, (int(x), int(y)), 2, (0, 255, 0), -1)
    if n:
        # OpenCV 5 returns (N,2) corners and (N,) ids; the drawing function wants (N,1,2) and (N,1)
        cv2.aruco.drawDetectedCornersCharuco(canvas, np.asarray(corners).reshape(-1, 1, 2).astype(np.float32),
                                             np.asarray(ids).reshape(-1, 1).astype(np.int32), (255, 160, 0))
    sides = set().union(*(tilt_sides(v.normal) for v in views)) if views else set()
    put(canvas, f"sudut: {n}  tersimpan: {len(views)}  cakupan: {cells.sum()}/{cells.size}  {keys}",
        0, (0, 220, 0) if n >= MIN_CORNERS else (0, 0, 255))
    if cur is not None:
        tilted = bool(tilt_sides(cur.normal))
        put(canvas, tilt_text(cur.normal), 1, (0, 230, 0) if tilted else (255, 255, 255))
    put(canvas, f"arah >= {MIN_TILT_DEG:.0f}: " + "  ".join(f"{s} [{'x' if s in sides else ' '}]" for s in SIDES), 2, (255, 255, 255))
    if not status:
        missing = [s for s in SIDES if s not in sides]
        if cur is not None and cur.outline is not None and cv2.contourArea(cur.outline) < 0.05 * size[0] * size[1]:
            status = "papan terlalu kecil di gambar: dekatkan"
        elif missing:
            status = f"belum ada papan miring ke: {', '.join(missing)}"
        elif cells.sum() < cells.size:
            status = "geser papan ke kotak yang belum hijau (pojok dan tepi)"
        elif len(views) < MIN_VIEWS:
            status = f"tambah frame di posisi lain (minimal {MIN_VIEWS})"
        else:
            status = "cakupan dan arah lengkap, tekan C untuk hitung"
    if status:
        put(canvas, status, 3, (0, 220, 255))
    return canvas


def run_camera(args, board, detector):
    cap = common.open_camera(args.source, args.width, args.height)
    frames_dir = os.path.join(common.DATA_DIR, f"calib_{args.name}", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(frames_dir, exist_ok=True)
    print(f"Frame disimpan di: {frames_dir}")
    if args.auto:
        print(f"Mode otomatis: tahan papan diam di posisi baru, frame tersimpan sendiri. "
              f"Setelah {args.target} frame, kalibrasi dihitung otomatis. C = hitung, Q = keluar")
    else:
        print("SPASI = simpan frame, C = hitung kalibrasi, Q = keluar")
    keys = "C hitung | Q keluar" if args.auto else "SPASI simpan | C hitung | Q keluar"
    views, size = [], None
    prev, still_since, auto_done, flash = {}, None, False, 0

    def save(frame, view):
        view.name = f"{len(views) + 1:02d}.png"
        views.append(view)
        cv2.imwrite(os.path.join(frames_dir, view.name), frame)
        print(f"{view.name} disimpan ({len(view.img)} sudut, {tilt_text(view.normal)})")

    def compute():
        result = calibrate(views, size)
        if result and report_and_save(views, size, result, args, frames_dir) != "LAYAK":
            print("Tambah frame sesuai saran di atas, lalu tekan C untuk hitung ulang.")

    while True:
        ok, frame = cap.read()
        if not ok:
            print("Kamera berhenti mengirim gambar.")
            break
        size = (frame.shape[1], frame.shape[0])
        corners, ids, n = detect(detector, frame)
        cur = BoardView(board, corners, ids, size) if n >= MIN_CORNERS else None
        same = find_repeat(cur, views) if cur is not None else None
        positions = corner_map(corners, ids) if n else {}
        if same is None:
            status = ""
        elif same is views[-1]:
            status = f"{same.name} tersimpan. Pindah ke posisi atau kemiringan baru"
        else:
            status = f"mirip {same.name}: pindahkan atau miringkan papan"
        if args.auto and (cur is None or same):
            still_since = None
        elif args.auto:
            still = bool(prev) and mean_shift(positions, prev) < STILL_PX
            still_since = (still_since or time.time()) if still else None
            if still_since and time.time() - still_since >= STILL_SEC:
                save(frame, cur)
                still_since, flash, status = None, 4, ""
                if len(views) >= args.target and not auto_done:
                    auto_done = True
                    compute()
            else:
                status = "tahan diam..."
        prev = positions
        canvas = draw_guide(frame, views, cur, corners, ids, n, size, status, keys)
        if flash:
            cv2.rectangle(canvas, (0, 0), (size[0] - 1, size[1] - 1), (255, 255, 255), 12)
            flash -= 1
        cv2.imshow("Kalibrasi ChArUco", canvas)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" "):
            if cur is None:
                print(f"Belum disimpan: baru {n} sudut terbaca, butuh minimal {MIN_CORNERS}.")
            elif same:
                print(f"Belum disimpan: hampir sama dengan {same.name}. Pindahkan atau miringkan papan dulu.")
            else:
                save(frame, cur)
                flash = 4
        elif key in (ord("c"), ord("C")):
            compute()
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
    ap.add_argument("--auto", action="store_true",
                    help="simpan frame otomatis saat papan diam di posisi baru (tanpa menekan SPASI)")
    ap.add_argument("--target", type=int, default=20, help="mode otomatis: jumlah frame sebelum kalibrasi dihitung")
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
