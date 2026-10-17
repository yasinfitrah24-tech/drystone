# Drystone — Status Project

Salinan status untuk repo (dibaca Yasin, Vincent, dan Claude masing-masing). Update di commit yang sama setiap ada keputusan atau hasil tes baru. Semua jam = waktu China.

Terakhir diperbarui: 17 Okt 2026 sore.

## Ringkasan
- **Lomba:** OpenCV AI Competition 2026 (https://opencv26.devpost.com/). Deadline **27 Okt, 14.45** (target submit 26 Okt malam). Penjurian 27 Okt–10 Nov, endpoint harus tetap hidup.
- **Tim:** Yasin (lead) + Vincent.
- **Ide:** Drystone, "prediksi sebelum menumpuk". Kamera + OpenCV 5 membaca pose tiap kardus (marker ArUco) dan membangun kembaran digital. Simulasi MuJoCo Monte Carlo menghitung P(roboh) calon penempatan. Agent: HIJAU < 10% pandu · KUNING 10–50% minta persetujuan supervisor · MERAH > 50% tolak + usul posisi lain (lanjut hanya lewat override dengan alasan tercatat). Setelah kardus ditaruh: cek ulang (sesuai / meleset / roboh). Keputusan keselamatan deterministik, bukan LLM.
- **Wajib lomba:** analisis gambar pakai OpenCV 5; bagian penting jalan di AWS (ap-southeast-1, Free plan, tanpa Marketplace). Kumpulkan laporan teknis, repo, diagram arsitektur, endpoint web/demo live, video ≤ 5 menit (wajah tim), bukti evaluasi termasuk kasus gagal.
- **Target hadiah:** Agentic Vision Award + juara utama.

## Tahapan dan deadline
| # | Tahap | Deadline | Status |
|---|---|---|---|
| 0 | Persiapan | 11 Okt | ✅ |
| 1 | Uji kelayakan: kalibrasi, Tes 1, Tes 2, go/no-go | 17 Okt | ✅ **GO** |
| 2+3 | Persepsi + fisika + agent | 19 Okt | ✅ inti jalan dengan kardus asli (17 Okt) |
| 4 | AWS: Lambda foto → keputusan, S3, DynamoDB log, dashboard approve/override, CloudWatch | 21 Okt | ⏳ kode layanan + Dockerfile siap, belum di-deploy |
| 5 | Evaluasi 20–30 percobaan baru + kasus gagal. **Fitur dikunci** | 22 Okt malam | — |
| 6 | Gladi (23) + rekam video (24) | 24 Okt | — |
| 7 | Laporan teknis, diagram, README | 25 Okt | — |
| 8 | Edit video, isi Devpost, submit | 26 Okt malam | — |

Uji deteksi kardus tanpa marker adalah target tambahan, hanya dikerjakan kalau inti + AWS selesai.

## Pembagian tugas
- **Yasin:** kamera/OpenCV, tes, simulasi, agent (juga pegang teknis Echolocate, freeze 22 Okt).
- **Vincent:** usulan: AWS (deploy Lambda 18–21 Okt, ikuti `aws/README.md`). **Belum dikonfirmasi, jawaban paling lambat 19 Okt.**
- Vincent perlu daftar Devpost dan kirim username untuk diundang ke tim.

## Hasil
### Kalibrasi webcam laptop Yasin (11 Okt) — LAYAK
- 61 view, RMS 0,366 px, fx/fy 900,0 ± 3,9 (0,43%), gambar 1280×720, cakupan 12/12. File: `data/camera_laptop.yaml`. Kalibrasi berlaku per kamera.

### Tes 1: akurasi posisi dari marker (11 Okt)
- Galat acak RMS 0,18 cm (maks 0,47 cm), rotasi ≤ 2,2°. Bias skala ±3% belum terjelaskan (dampaknya kecil).

### Tes 2: prediksi vs kenyataan (17 Okt) — lulus
- 12 percobaan (2–3 kardus, menjorok 20–65%), 11 dihitung. Data: `data/tes2_20261017_125209/hasil.csv`.
- **Pengaturan awal (posisi 0,5 cm, isi 1 cm): cocok 9/11 = 82%, Brier 0,177, 1 roboh di zona HIJAU** (3 kardus +23%/+38%, P 1%). Dua salah prediksi sama-sama ke arah berbahaya, dekat batas (margin pusat massa 1,3 dan 2,5 cm).
- **Ketidakpastian dinaikkan (posisi 1 cm, isi 2 cm), lalu hitung ulang (`--recheck`): 82%, Brier 0,145, 0 roboh di zona HIJAU** (kasus dekat batas jadi KUNING). Data: `recheck_pos1_com2/hasil.csv`. Karena disetel pada data yang sama, **wajib divalidasi di percobaan baru (22 Okt).** Menjorok 30–35% (2 kardus) belum teruji.

### Agent (17 Okt) — jalan dengan kardus asli
- `tools/agent.py` + `tools/drystone_core.py`. Monte Carlo adaptif (150 → 600 sampel di dekat garis 10%/50%; kalau masih ambigu, dipilih zona yang lebih aman). Agent mengusulkan posisi hijau terdekat (grid 1 cm), foto ulang otomatis kalau bacaan jelek, override wajib nama + alasan, cek ulang setelah penempatan, log JSONL + foto.
- **Perbaikan persepsi:** arah hadap satu marker goyang beberapa derajat per frame. Cara lama (tengah kardus dari arah tiap marker, rotasi kardus bawah per frame) membuat posisi melompat 1,5–3,6 cm. Sekarang arah = rata-rata semua marker × 10 frame dan posisi = median, sehingga goyangnya ±0,1 cm (uji sintetis) dan biasnya juga hilang. Tes 2 masih memakai cara lama.
- Uji nyata: B +6 cm HIJAU → ditaruh +1,6 cm (MELESET, tetap hijau) · C diminta +12 cm → KUNING 40%, usulan +8 cm (4%) → ditaruh meleset +2,1 cm → agent memperingatkan KUNING 20–29% → dibetulkan → OK +0,8 cm, HIJAU 6%.

### Layanan AWS (17 Okt) — siap deploy
- `tools/service.py`: 1–5 foto → keputusan JSON (mode decide / check), `lambda_handler`. Uji dengan foto asli: +6 cm HIJAU 1% (1,7 dtk), +12 cm KUNING 41% + usulan (8,3 dtk), +16 cm MERAH 87% (8,2 dtk). Jalan di Python 3.12 bersih dengan paket Lambda (OpenCV headless). Image Docker belum pernah dibangun.

## Berikutnya
- **18–19 Okt:** build Docker + deploy Lambda (`aws/README.md`) · latihan adegan demo termasuk override → roboh · tempel ulang marker ID 2 · ukur tinggi asli kardus (terbaca ±20 cm, katalog 19).
- **20–21 Okt:** S3 foto bukti, DynamoDB log, dashboard approve/override, CloudWatch; agent laptop memanggil endpoint.
- **22 Okt:** evaluasi 20–30 percobaan baru (akurasi, Brier, roboh di HIJAU, waktu keputusan, foto ulang) + kasus gagal; malamnya fitur dikunci.

## Kardus
- 邮政纸箱 5号, 29 × 17 × 19 cm, dipakai berdiri: lebar 29 cm kiri-kanan (arah menjorok), tinggi 19, dalam 17. Marker 80 mm di tengah sisi depan. Isi 1,0 kg di tengah, semua sama. ID 0 selalu di bawah. Hanya kardus yang ditumpuk boleh terlihat kamera.
- Kamera ±0,95–1,0 m. Saat uji roboh, laptop jangan di arah jatuhnya.

## Aturan kerja
- Semua jam waktu China.
- Secret (AWS key, API key) hanya di `.env` atau `aws configure`. Jangan pernah di-commit. Tiap orang pakai IAM user sendiri.
- Repo akan dibuat public sebelum submit: jangan commit data pribadi, foto kamar/wajah, atau info akun/pembayaran.
- Versi dependency di-pin. Tiap klaim di README/laporan harus didukung angka evaluasi. Drystone adalah alat bantu keputusan, bukan perangkat keselamatan bersertifikat.
