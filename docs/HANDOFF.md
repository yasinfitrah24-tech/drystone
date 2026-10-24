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
- Kalibrasi berlaku **per kamera dan per resolusi**. `common.load_calibration` memberi WARNING kalau kalibrasi belum PASS (`quality` di YAML bukan `LAYAK`).
- Analisis hasil tes dari CSV di `data/` (kolom tx_cm, ty_cm, tz_cm per posisi) untuk membedakan galat acak vs bias sistematis.

## Pelajaran dari tes 11 Okt
- Kalibrasi: papan ChArUco **wajib ditempel di bidang keras**. Default = mode terpandu (cocokkan papan dengan garis biru, 14 target, simpan sendiri; N lewati, B kembali, C hitung, Q keluar); `--auto` = mode bebas lama. Targetnya menutup 12/12 kotak cakupan dan miring 4 arah.
- **Setup selalu sinkron dengan kode.** Setiap perubahan perintah, nama opsi, nama file output, tombol keyboard, atau langkah di `tools/` atau `aws/` WAJIB ikut memperbarui tab Setup (`web/index.html`), `docs/SITE_COPY.md`, README "Run it yourself" dan `aws/README.md` di commit yang sama, lalu deploy supaya Setup live ikut berubah. `tests/test_setup_commands.py` mengeceknya (perintah `python tools/...` sama di Setup dan README, opsinya dikenal argparse, tombol sama dengan `calibrate.KEYS` / `agent_hud.AGENT_KEYS`, tanpa `< >`). Kalau tes gagal: perbaiki halaman / README, jangan longgarkan tesnya.
- Tes 1: tempel tanda selotip tiap 5 cm, tepi benda yang sama selalu di garis, rel buku ditempel ke meja, kamera agak menunduk (marker di sepertiga atas gambar), rentang gerak di tengah gambar. SPASI sekali per posisi, jangan sentuh meja ±1 detik.
- Ada bias skala ±3% yang belum terjelaskan → dicek ulang dengan kardus asli.

## Pelajaran 17 Okt
- Tes 2: ketidakpastian yang hanya berisi galat kamera (0,5 cm) terlalu yakin di dekat batas. Dua salah prediksi sama-sama "prediksi berdiri, ternyata roboh". Default sekarang posisi 1 cm + isi 2 cm. Metrik keselamatan utama: **roboh di zona HIJAU = 0**.
- Persepsi: jangan pakai arah hadap satu marker untuk posisi (goyang 3–5° per frame = 1,5–3,6 cm untuk kardus 40 cm di atas). Pakai `common_rotation` (chordal mean semua marker × frame) + median. Bacaan yang goyang ditolak dengan pesan berisi angka goyangnya.
- Yang terlihat kamera = yang dihitung. Kardus nganggur harus di luar pandangan; agent menolak kalau ada kardus di samping tumpukan.
- Uji dulu dengan kamera palsu (`test_agent.py` di sesi Claude: render kardus + ArUco dari kalibrasi asli, tombol & jawaban cmd di-script). Data sintetis terlalu bersih untuk goyangan, jadi untuk itu uji juga langsung di tingkat pose (rotasi diacak 1–5°).
- Mengirim file ke laptop lewat device bridge: SendUserFile → commit pakai fileUuid → stage ulang → `cmp`. Jangan pakai stagedPath dari file yang di-`cp` (pernah menulis isi lama).

## Pelajaran 18 Okt
- **Tumpukan = kontak fisik, bukan urutan tinggi di gambar.** `agent.build_stack` mulai dari ID 0 ke atas; kardus lain "di luar tumpukan". Arah hadap hanya dari anggota tumpukan (`stack_rotation`): satu kardus jatuh yang berputar pernah memiringkan acuan 16°.
- **Cek ulang:** kardus calon di luar tumpukan atau hilang dari pandangan = FELL, bukan retake. Untuk keputusan, kardus di luar tumpukan tetap ditolak (kardus nganggur harus di luar pandangan).
- Uji dengan `tests/synth_scene.py` (kardus pose bebas: tegak, rebah, berputar, keluar frame) + `tests/test_check.py`. Kamera palsu untuk loop agent: setelah keputusan ada satu `cv2.waitKey(1)` ekstra, jadi beri satu tombol kosong di urutan tombol.

## Pelajaran 17 Okt malam
- **Bahasa:** semua teks produk (pesan agent, overlay kamera, trace, JSON AWS, README publik) dalam **bahasa Inggris** karena lomba internasional. Obrolan dengan Yasin tetap bahasa Indonesia. Kode: `GREEN/YELLOW/RED`, `GUIDE/ASK_SUPERVISOR/REJECT`, cek `OK/OFF_PLAN/FELL/NOT_PLACED`, layanan `RETAKE/CONTINUE/FIX_PLACEMENT/STOP/WAIT/DONE`, plans `requested/suggested`. `predict_test.py`, `aws/README.md`, `docs/`, `CLAUDE.md` masih sebagian Indonesia → terjemahkan saat menyiapkan repo publik.
- **Simulasi cepat:** `drystone_core.simulate_once` = fisika & undian acak sama dengan `predict_test.simulate_once`, tapi berhenti saat kardus jatuh atau semua diam. Diuji identik di 1.500 sampel, ±2,9× lebih cepat. Kalau mengubah fisika, ulangi uji sampel-per-sampel itu.
- **Usulan posisi** wajib lolos konfirmasi 150 simulasi sebelum disebut GREEN (screening 60 sampel saja pernah memberi 3% lalu 8% setelah ditaruh pas).
- **Setelah penempatan:** RED, atau OFF_PLAN yang membuat tumpukan YELLOW → WARNING dan rencana ditahan sampai dibetulkan. Sesuai rencana tapi YELLOW (angka dekat garis 10%) → CAUTION saja.
- **Tampilan live** pakai `LiveSmoother` (arah dari semua marker + rata-rata bergerak alpha 0,15, lompat kalau pindah > 3 cm). Hanya tampilan; keputusan tetap `read_stack` (median 10 frame).
- **AWS dari China lambat:** build image pertama ±99 menit (`public.ecr.aws` + PyPI). Build berikutnya detik karena cache, **selama `aws/requirements-lambda.txt` tidak diubah**. Kalau terpaksa ubah: `--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`. Build untuk Lambda selalu `--provenance=false`.
- Kirim foto ke Lambda sebagai JPEG (PNG 1,4 MB butuh ±8 dtk upload). Overhead jaringan China→Singapura ±3–4 dtk per panggilan.

## Tugas berikutnya (urut)
1. ✅ **Halaman web untuk juri** — live dengan foto asli s1–s3 (18 Okt; live sekarang `drystone-service:3b023a4`, lihat STATUS; rollback ke `:9523213`). Function URL tidak pernah ditulis di repo (env `DRYSTONE_URL`) dan tidak boleh berubah sampai 10 Nov: jangan hapus/buat ulang fungsi, cukup update image. Kalau foto diganti lagi: hitung ulang zona, perbarui `examples` dan `photos_version` di `samples.json` (tes gagal kalau lupa), deploy dengan tag hash baru.
2. **S3 + DynamoDB log** (bonus, menambah nilai observability & human control): simpan foto + isi `log.jsonl` per keputusan, termasuk approval/override.
3. **Latihan adegan demo** dengan kardus asli: GREEN → YELLOW + usulan → meleset dibetulkan → RED + override → FELL terdeteksi (override → roboh belum pernah dicoba nyata).
4. **Evaluasi (21 Okt)**: 20–30 percobaan baru lewat agent; skrip ringkasan dari `data/agent_*/log.jsonl` (akurasi, Brier, roboh di zona GREEN, waktu keputusan, jumlah retake, berapa kali fallback laptop) + kasus gagal. Malamnya fitur dikunci.
5. Video 24 Okt (Yasin + Vincent), laporan/diagram/README 25 Okt, submit 26 Okt malam (deadline 27 Okt 14.45).

## Lingkungan
- **Laptop Yasin** (`E:\opencv-project`): webcam 1280×720 terkalibrasi (`data/camera_laptop.yaml`), Docker Desktop (data di `E:\DockerData`, harus "Engine running"), AWS CLI v2 + `aws configure` (IAM user pribadi di laptop Yasin, ap-southeast-1). Claude di akun mana pun yang dipakai di laptop ini bisa memakai semua itu.
- Agent lokal: `python tools/agent.py --calib data/camera_laptop.yaml --marker-mm 80 --supervisor Yasin`. Lewat AWS: `set DRYSTONE_URL=<Function URL>` dulu (berlaku per jendela cmd; minta URL ke Yasin, jangan ditulis di repo).
- **AWS sekarang:** ECR repo `drystone-service`; Lambda `drystone` (container image, x86_64, 2048 MB, timeout 60 dtk); Function URL auth NONE + CORS POST. Update kode Lambda:
  ```
  docker build --provenance=false -f aws/Dockerfile -t drystone-service .
  for /f %i in ('aws sts get-caller-identity --query Account --output text') do set ACC=%i
  set REPO=%ACC%.dkr.ecr.ap-southeast-1.amazonaws.com/drystone-service
  aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin %ACC%.dkr.ecr.ap-southeast-1.amazonaws.com
  docker tag drystone-service:latest %REPO%:latest
  docker push %REPO%:latest
  aws lambda update-function-code --function-name drystone --image-uri %REPO%:latest --region ap-southeast-1
  aws lambda wait function-updated --function-name drystone --region ap-southeast-1
  ```
  (beri ke user satu perintah per blok). Tes: `python aws/test_endpoint.py --url %DRYSTONE_URL% --image <foto> --offset-cm 12`.
- Laptop Vincent: repo hasil `git clone` (`C:\Users\Xlyph\drystone`), belum ada kalibrasi kamera Vincent, tidak punya akses AWS.
- AWS: akun **Paid plan** (bukan Free plan, koreksi 18 Okt); tetap dalam kuota gratis (Lambda 1 juta request dan 400.000 GB-detik/bulan, CloudWatch Logs 5 GB), tanpa AWS Marketplace, alarm Zero spend budget lewat email (`zero-spend-opencv`). Nomor akun dan Function URL jangan masuk repo publik. Jangan commit `event.json`, `out.json`, `*_result.jpg`, `hasil_endpoint.jpg`, `data/agent_*` (foto memuat kamar/wajah).
- Doc project claude.ai Yasin (`claude/opencv-ai-competition.md`) **tidak terbaca** dari akun lain → `docs/STATUS.md` adalah sumber status di repo. Update di commit yang sama setiap ada progres.
