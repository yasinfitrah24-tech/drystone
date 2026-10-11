# Handoff untuk Claude (sesi baru / akun lain)

Baca file ini setelah `CLAUDE.md` dan `docs/STATUS.md`. Isinya cara kerja yang sudah disepakati dengan Yasin dan Vincent, supaya sesi baru bisa langsung lanjut tanpa mengulang.

## Cara kerja dengan user
- Jawab dalam **bahasa Indonesia**, santai tapi jelas. Semua jam pakai **waktu China**.
- User memakai **Windows Command Prompt (cmd)**, bukan PowerShell. Beri perintah cmd, **satu perintah per baris/blok**, dan ingatkan aktifkan venv dulu:
  ```
  cd /d <folder repo>
  .venv\Scripts\activate
  ```
  Pastikan muncul `(.venv)`. Python global user bisa 3.14; venv project **3.12**.
- Pandu **langkah demi langkah**: apa yang disiapkan, perintah yang dijalankan, apa yang dicek, apa yang ditempel balik. Setelah user menempel output terminal, analisis angkanya (bukan cuma "bagus"), jelaskan penyebab kalau gagal, lalu beri langkah berikutnya.
- Kalau user minta "prompt 3D", buat prompt bahasa Inggris untuk Claude Design (three.js, ukuran nyata dalam cm, label bahasa Indonesia).
- Pesan WhatsApp untuk anggota tim: bahasa Indonesia, nada netral, dipecah per bubble.
- **Jangan pernah** menempel nomor kartu, API key, password, atau secret di chat, repo, atau dokumen. Secret hanya di `.env` / `aws configure` di laptop masing-masing.
- Setiap ada keputusan atau hasil tes baru: update `docs/STATUS.md` di commit yang sama.

## Kebiasaan teknis yang sudah terbukti
- **Uji dulu sebelum diberikan ke user.** Script baru diuji di gambar sintetis dengan kamera yang diketahui (render ChArUco/ArUco + distorsi), dan untuk mode kamera dipakai "kamera palsu" (patch `cv2.VideoCapture`, `imshow`, `waitKey`). Baru setelah lulus, file dikirim.
- OpenCV 5 (opencv-python 5.0.0.93) beda bentuk array dari OpenCV 4: `CharucoDetector.detectBoard` mengembalikan corners (N,2) dan ids (N,); `drawDetectedCornersCharuco` butuh (N,1,2) float32 dan (N,1) int32. `matchImagePoints` mengembalikan (N,3)/(N,2).
- Kalibrasi berlaku **per kamera dan per resolusi**. `common.load_calibration` memberi PERINGATAN kalau kalibrasi belum LAYAK.
- Analisis hasil tes dari CSV di `data/` (kolom tx_cm, ty_cm, tz_cm per posisi) untuk membedakan galat acak vs bias sistematis.

## Pelajaran dari tes 11 Okt
- Kalibrasi: papan ChArUco **wajib ditempel di bidang keras**. Pakai `--auto`; isi 12/12 kotak cakupan dan miring 4 arah.
- Tes 1: tempel tanda selotip tiap 5 cm, tepi benda yang sama selalu di garis, rel buku ditempel ke meja, kamera agak menunduk (marker di sepertiga atas gambar), rentang gerak di tengah gambar. SPASI sekali per posisi, jangan sentuh meja ±1 detik.
- Ada bias skala ±3% yang belum terjelaskan → dicek ulang dengan kardus asli.

## Tugas berikutnya (urut)
1. **Uji deteksi kardus tanpa marker** (mulai 12 Okt): buat `tools/markerless_test.py`. Ide: deteksi kardus dengan engine DNN OpenCV 5 (atau segmentasi/kontur sebagai cadangan), estimasi pose/posisi dari tepi kardus + ukuran katalog, bandingkan dengan pose ArUco sebagai acuan (tingkat deteksi, galat posisi cm, galat sudut). Script harus bisa jalan dari foto (`--images`) dan kamera, dan diuji dulu di gambar sintetis.
2. **Tes 2** (13 Okt, kardus datang): `python tools/predict_test.py --calib data/camera_laptop.yaml --marker-mm 80 --pos-sd-cm 0.5`. Sebelumnya isi `config/boxes.json` (ukur ulang ukuran luar, timbang berat). Target prediksi cocok ≥ 80%, laporkan juga Brier score.
3. **Go/no-go** 13 Okt malam (paling lambat 14 Okt pagi). Gagal → ide C "Pemeriksa langkah perakitan".
4. Lalu tahap 2–8 sesuai tabel di `docs/STATUS.md`.

## Lingkungan
- Laptop Yasin: repo di `E:\opencv-project`, webcam 1280×720 sudah dikalibrasi (`data/camera_laptop.yaml`).
- Laptop Vincent: repo di folder hasil `git clone` (misalnya `C:\Users\Xlyph\drystone`). Belum ada kalibrasi kamera Vincent.
- Kalau Claude bisa mengakses folder repo di laptop user, kerjakan file langsung di sana; kalau tidak, kirim file dan perintah untuk dijalankan user.
- AWS: region ap-southeast-1, Free plan. Jangan pakai Marketplace, jangan upgrade ke Paid plan. Tiap orang pakai IAM user sendiri.
