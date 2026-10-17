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

## Pelajaran 17 Okt
- Tes 2: ketidakpastian yang hanya berisi galat kamera (0,5 cm) terlalu yakin di dekat batas. Dua salah prediksi sama-sama "prediksi berdiri, ternyata roboh". Default sekarang posisi 1 cm + isi 2 cm. Metrik keselamatan utama: **roboh di zona HIJAU = 0**.
- Persepsi: jangan pakai arah hadap satu marker untuk posisi (goyang 3–5° per frame = 1,5–3,6 cm untuk kardus 40 cm di atas). Pakai `common_rotation` (chordal mean semua marker × frame) + median. Bacaan yang goyang ditolak dengan pesan berisi angka goyangnya.
- Yang terlihat kamera = yang dihitung. Kardus nganggur harus di luar pandangan; agent menolak kalau ada kardus di samping tumpukan.
- Uji dulu dengan kamera palsu (`test_agent.py` di sesi Claude: render kardus + ArUco dari kalibrasi asli, tombol & jawaban cmd di-script). Data sintetis terlalu bersih untuk goyangan, jadi untuk itu uji juga langsung di tingkat pose (rotasi diacak 1–5°).
- Mengirim file ke laptop lewat device bridge: SendUserFile → commit pakai fileUuid → stage ulang → `cmp`. Jangan pakai stagedPath dari file yang di-`cp` (pernah menulis isi lama).

## Tugas berikutnya (urut)
1. **Deploy Lambda** (18–19 Okt): ikuti `aws/README.md` (Docker Desktop → ECR → Lambda container 2048 MB / 60 dtk → Function URL AWS_IAM). Uji dengan foto dari `data/agent_*/langkah_*_cek_ulang.png` (foto mentah). Siapa yang deploy: Vincent kalau setuju (≤19 Okt), kalau tidak Yasin dengan IAM user sendiri.
2. **Latihan adegan demo:** hijau → kuning + usulan → meleset dibetulkan → merah + override → roboh terdeteksi (belum dicoba nyata).
3. **AWS lanjutan** (20–21 Okt): S3 foto bukti, DynamoDB log (isi = `log.jsonl`), dashboard statis approve/override, CloudWatch; `agent.py` opsi memanggil endpoint.
4. **Evaluasi** (22 Okt): 20–30 percobaan baru lewat agent, catat hasil nyata; skrip ringkasan dari `log.jsonl` (akurasi, Brier, roboh di HIJAU, waktu, jumlah foto ulang) + kasus gagal. Malamnya fitur dikunci.
5. Lalu video (24), dokumen (25), submit (26).

## Lingkungan
- Laptop Yasin: repo di `E:\opencv-project`, webcam 1280×720 sudah dikalibrasi (`data/camera_laptop.yaml`). Agent: `python tools/agent.py --calib data/camera_laptop.yaml --marker-mm 80 --supervisor Yasin`.
- Laptop Vincent: repo di folder hasil `git clone` (misalnya `C:\Users\Xlyph\drystone`). Belum ada kalibrasi kamera Vincent.
- Kalau Claude bisa mengakses folder repo di laptop user, kerjakan file langsung di sana; kalau tidak, kirim file dan perintah untuk dijalankan user.
- AWS: region ap-southeast-1, Free plan. Jangan pakai Marketplace, jangan upgrade ke Paid plan. Tiap orang pakai IAM user sendiri.
