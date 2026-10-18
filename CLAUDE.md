# Drystone - OpenCV AI Competition 2026

Konteks untuk Claude (akun Yasin maupun Vincent). **Baca `docs/STATUS.md` lalu `docs/HANDOFF.md` dulu** untuk status, jadwal, hasil tes, dan tugas berikutnya. Doc project claude.ai Yasin tidak terbaca dari akun lain, jadi `docs/STATUS.md` adalah sumber status di repo.

**Bahasa:** ngobrol dengan Yasin/Vincent pakai bahasa Indonesia. Semua teks produk (output agent, overlay kamera, JSON AWS, README publik, komentar baru) pakai **bahasa Inggris** karena lombanya internasional.

## Projek
Drystone: satu kamera + OpenCV 5 membaca posisi tiap kardus (marker ArUco + katalog ukuran dan berat), membangun kembaran digital tumpukan, lalu simulasi MuJoCo (Monte Carlo) menghitung peluang roboh untuk calon posisi kardus berikutnya. Agent memandu, minta persetujuan, atau menolak, lalu mengecek ulang setelah kardus ditaruh.

- Lomba: OpenCV AI Competition 2026 (Devpost). Deadline 27 Okt 14.45 waktu China.
- Wajib: analisis gambar pakai OpenCV 5, dan bagian penting jalan di AWS (region ap-southeast-1). Akun AWS ternyata **Paid plan** (dicek 18 Okt: PAID, ACTIVE, kredit 0; tagihan Okt USD 0,00), tidak bisa turun ke Free plan.
- Target: Agentic Vision Award + juara utama.

## Aturan agent
- P(fall) < 10% = GREEN -> GUIDE: pandu penempatan.
- 10-50% = YELLOW -> ASK_SUPERVISOR: minta persetujuan supervisor (a approve / s use suggestion / r reject).
- > 50% = RED -> REJECT: tolak dan usulkan posisi lain (s use suggestion / o override dengan nama + alasan / c cancel).
- Setelah kardus ditaruh, cek ulang: OK / OFF_PLAN / FELL / NOT_PLACED.
- Peluang roboh selalu dari Monte Carlo, bukan satu simulasi. Ketidakpastian default: posisi 1 cm (kamera 0,5 dari Tes 1 + penempatan/tepi kardus dari Tes 2) dan titik berat isi 2 cm.
- Kode keputusan hanya di `tools/drystone_core.py`; agent laptop dan layanan AWS sama-sama memakainya. Jangan menulis ulang aturan zona di tempat lain.
- Keputusan keselamatan tetap deterministik dan tercatat di log, tidak diserahkan ke LLM.

## Setup (Windows)
Command Prompt (cmd):
    cd /d E:\opencv-project
    .venv\Scripts\activate
    pip install -r requirements.txt

PowerShell:
    cd E:\opencv-project
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt

Pastikan muncul `(.venv)` di awal baris sebelum menjalankan pip atau python. Python global di laptop ini 3.14, venv 3.12.

## Struktur
- `tools/calibrate.py`: kalibrasi kamera dengan papan ChArUco
- `tools/pose_test.py`: Tes 1, akurasi posisi kardus dari marker
- `tools/predict_test.py`: Tes 2, prediksi roboh (statis + Monte Carlo MuJoCo) dibanding kenyataan
- `tools/common.py`: pengaturan marker dan fungsi bersama
- `tools/drystone_core.py`: keputusan (zona, Monte Carlo adaptif, usulan posisi, cek ulang). Tanpa kamera/GUI.
- `tools/agent.py`: agent live di laptop (kamera, wireframe calon, persetujuan/override di cmd, log `data/agent_<waktu>/log.jsonl`)
- `tools/service.py`: foto -> keputusan JSON (CLI + `lambda_handler` untuk AWS)
- `aws/test_endpoint.py`: kirim foto ke Docker lokal / Function URL / `aws lambda invoke`
- `aws/`: Dockerfile Lambda, `requirements-lambda.txt`, langkah deploy (`aws/README.md`)
- `config/boxes.json`: katalog kardus per ID marker (ukuran cm, berat kg). ID 0 = kardus paling bawah.
- `data/`: hasil kalibrasi (`camera_*.yaml`) dan hasil tes (`*.csv`). Foto mentah dan folder `agent_*` / `service_*` tidak di-commit (bisa memuat wajah/kamar).

## Marker
- Papan kalibrasi: ChArUco 7x5, kotak 30 mm, marker 22 mm, DICT_5X5_100
- Marker kardus: DICT_4X4_50, sisi hitam 80 mm, ID 0-11, ditempel di tengah sisi depan kardus. `config/boxes.json` hanya berisi kardus yang benar-benar ada (sekarang ID 0-2). Kardus 29 × 17 × 19,3–19,7 cm: tinggi terukur ID 0 19,6 · ID 1 19,5 · ID 2 19,4 cm.
- Posisi kardus dihitung dengan arah hadap rata-rata semua marker x 10 frame (bukan arah tiap marker): arah satu marker goyang beberapa derajat dan dulu membuat posisi melompat 1,5-3,6 cm.
- Selalu ukur hasil cetak dan isi ukuran aslinya (`--square-mm`, `--marker-mm`)

## Kalibrasi
- Papan ChArUco wajib ditempel di bidang keras dan rata. Kertas yang dipegang langsung melengkung dan merusak kalibrasi (percobaan 11 Okt: RMS 1.18 px, fx meleset +-75 px).
- Kalibrasi hanya dipakai kalau vonisnya LAYAK: RMS <= 1.0 px (bagus < 0.5), ketidakpastian fx/fy <= 1%, cakupan >= 9 dari 12 kotak gambar, minimal 10 posisi papan berbeda. Hasil ULANGI disimpan sebagai `camera_<nama>_draft.yaml`.
- Kamera sendirian: pakai `--auto`. Frame kembar ditolak otomatis.

## Aturan kerja
- Semua jam pakai waktu China.
- Secret (AWS key, API key) hanya di `.env` atau `aws configure`. Jangan pernah ditulis di kode, repo, atau file ini. Nomor kartu, API key, secret juga jangan ditempel di chat.
- Nomor akun AWS dan Function URL jangan masuk repo. URL dipakai lewat `set DRYSTONE_URL=...` di cmd.
- Jangan commit `event.json`, `out.json`, `*_result.jpg`, `hasil_endpoint.jpg`, `data/agent_*`, `data/service_*` (foto memuat kamar/wajah).
- Perintah untuk Yasin: cmd Windows, satu perintah per baris/blok, dijelaskan singkat.
- Versi dependency di-pin di `requirements.txt`.
- Tiap klaim di README dan laporan harus didukung angka evaluasi. Drystone adalah alat bantu keputusan, bukan perangkat keselamatan bersertifikat.
- Biaya AWS: tetap dalam kuota gratis (Lambda 1 juta request dan 400.000 GB-detik/bulan, CloudWatch Logs 5 GB), tanpa AWS Marketplace, alarm Zero spend budget lewat email (`zero-spend-opencv`). Akun tidak tutup sendiri; biaya di atas kuota ditagih. Jangan tulis nomor akun di mana pun.

## Kerja berdua (Yasin + Vincent)
- Repo: GitHub private `drystone`. Selalu `git pull` sebelum mulai, commit + push setelah selesai.
- AWS dipegang Yasin (laptop Yasin). Vincent: video, naskah, diagram, Devpost.
- Kalibrasi kamera per kamera: `data/camera_laptop.yaml` hanya untuk webcam laptop Yasin. Kamera lain wajib kalibrasi sendiri (`--name <nama>`).
- Kalau ada keputusan atau hasil tes baru, update `docs/STATUS.md` di commit yang sama.
- Repo akan dibuat public sebelum submit: jangan commit secret, data pribadi, atau info akun/pembayaran.

