# Drystone - OpenCV AI Competition 2026

Konteks untuk Claude (dipakai Yasin dan Vincent). Status, keputusan, dan jadwal terbaru ada di doc project HACKATHON `claude/opencv-ai-competition.md`.

## Projek
Drystone: satu kamera + OpenCV 5 membaca posisi tiap kardus (marker ArUco + katalog ukuran dan berat), membangun kembaran digital tumpukan, lalu simulasi MuJoCo (Monte Carlo) menghitung peluang roboh untuk calon posisi kardus berikutnya. Agent memandu, minta persetujuan, atau menolak, lalu mengecek ulang setelah kardus ditaruh.

- Lomba: OpenCV AI Competition 2026 (Devpost). Deadline 27 Okt 14.45 waktu China.
- Wajib: analisis gambar pakai OpenCV 5, dan bagian penting jalan di AWS (region ap-southeast-1, Free plan).
- Target: Agentic Vision Award + juara utama.

## Aturan agent
- P(roboh) < 10% = HIJAU: pandu penempatan.
- 10-50% = KUNING: minta persetujuan supervisor.
- > 50% = MERAH: tolak dan usulkan posisi lain. Lanjut hanya lewat override supervisor dengan alasan yang tercatat.
- Peluang roboh selalu dari Monte Carlo dengan galat kamera hasil ukur sendiri (Tes 1), bukan satu simulasi.
- Keputusan keselamatan tetap deterministik dan tercatat di log, tidak diserahkan ke LLM.

## Setup (Windows, PowerShell)
    cd E:\opencv-project
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt

## Struktur
- `tools/calibrate.py`: kalibrasi kamera dengan papan ChArUco
- `tools/pose_test.py`: Tes 1, akurasi posisi kardus dari marker
- `tools/predict_test.py`: Tes 2, prediksi roboh (statis + Monte Carlo MuJoCo) dibanding kenyataan
- `tools/common.py`: pengaturan marker dan fungsi bersama
- `config/boxes.json`: katalog kardus per ID marker (ukuran cm, berat kg). ID 0 = kardus paling bawah.
- `data/`: hasil kalibrasi (`camera_*.yaml`) dan hasil tes (`*.csv`). Foto mentah tidak di-commit.

## Marker
- Papan kalibrasi: ChArUco 7x5, kotak 30 mm, marker 22 mm, DICT_5X5_100
- Marker kardus: DICT_4X4_50, sisi hitam 80 mm, ID 0-11, ditempel di tengah sisi depan kardus
- Selalu ukur hasil cetak dan isi ukuran aslinya (`--square-mm`, `--marker-mm`)

## Aturan kerja
- Semua jam pakai waktu China.
- Secret (AWS key, API key) hanya di `.env` atau `aws configure`. Jangan pernah ditulis di kode, repo, atau file ini.
- Versi dependency di-pin di `requirements.txt`.
- Tiap klaim di README dan laporan harus didukung angka evaluasi. Drystone adalah alat bantu keputusan, bukan perangkat keselamatan bersertifikat.
- Jangan pakai layanan AWS Marketplace dan jangan upgrade akun AWS ke Paid plan.
