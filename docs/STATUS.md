# Drystone — Status Project

Salinan status untuk repo (dibaca Yasin, Vincent, dan Claude masing-masing). Update di commit yang sama setiap ada keputusan atau hasil tes baru. Semua jam = waktu China.

Terakhir diperbarui: 11 Okt 2026.

## Ringkasan
- **Lomba:** OpenCV AI Competition 2026 (https://opencv26.devpost.com/). Deadline **27 Okt, 14.45** (target submit 26 Okt malam). Penjurian 27 Okt–10 Nov, endpoint harus tetap hidup.
- **Tim:** Yasin (lead) + Vincent.
- **Ide:** Drystone, "prediksi sebelum menumpuk". Kamera + OpenCV 5 membaca pose tiap kardus (marker ArUco), membangun kembaran digital tumpukan, simulasi MuJoCo Monte Carlo menghitung P(roboh) untuk penempatan berikutnya. Agent: HIJAU < 10% pandu · KUNING 10–50% minta persetujuan supervisor · MERAH > 50% tolak + usul posisi lain (lanjut hanya lewat override dengan alasan tercatat). Keputusan keselamatan deterministik, bukan diserahkan ke LLM.
- **Wajib lomba:** analisis gambar pakai OpenCV 5; bagian penting jalan di AWS (region ap-southeast-1, Free plan, tanpa Marketplace). Kumpulkan laporan teknis, repo (dependency di-pin, instruksi build), diagram arsitektur, endpoint web/demo live, video ≤ 5 menit (wajah tim wajib), bukti evaluasi termasuk kasus gagal.
- **Target hadiah:** Agentic Vision Award (orkestrasi & otonomi 25%, kontrol manusia 15%) + juara utama (technical execution 30%).

## Tahapan dan deadline
| # | Tahap | Deadline | Status |
|---|---|---|---|
| 0 | Persiapan (Devpost, ide, OpenCV, AWS, marker) | 11 Okt | ✅ |
| 1 | Uji kelayakan: kalibrasi, Tes 1, uji tanpa marker, Tes 2, go/no-go | 13 Okt malam (paling lambat 14 Okt pagi) | ⏳ kalibrasi ✅, Tes 1 ✅ |
| 2 | Persepsi: banyak kardus, kembaran digital, deteksi tanpa marker, peta stabilitas | 16 Okt | — |
| 3 | Fisika + agent: Monte Carlo adaptif, aksi agent, log keputusan | 19 Okt | — |
| 4 | AWS: foto → keputusan, S3, DynamoDB log, dashboard approve/override, CloudWatch | 21 Okt | — |
| 5 | Evaluasi 30–50 percobaan + kasus gagal. **Fitur dikunci** | 23 Okt | — |
| 6 | Rekam video demo (gladi kasar 22–23 Okt) | 24 Okt (paling lambat 25 Okt) | — |
| 7 | Laporan teknis, diagram, README | 25 Okt | — |
| 8 | Edit video, isi Devpost, submit | 26 Okt malam | — |

Go/no-go gagal → fallback ide C "Pemeriksa langkah perakitan".

## Pembagian tugas
- **Yasin:** kamera/OpenCV, tes, simulasi, agent (juga pegang teknis Echolocate, freeze 22 Okt).
- **Vincent:** usulan: bagian AWS (tahap 4, 20–21 Okt). **Belum dikonfirmasi.**
- Vincent perlu daftar Devpost dan kirim username untuk diundang ke tim.

## Hasil yang sudah ada
### Kalibrasi webcam laptop Yasin (11 Okt) — LAYAK
- `tools/calibrate.py --name laptop --square-mm 29.8 --auto`: 61 view, RMS 0,366 px, fx/fy 900,0 ± 3,9 (0,43%), cx/cy 626,2 / 352,1 (gambar 1280×720), distorsi k1 −0,1094, k2 0,1389. Cakupan 12/12, miring 4 arah. File: `data/camera_laptop.yaml`.
- Percobaan pertama gagal (RMS 1,18 px): frame kembar, papan hampir lurus dan di tengah, kertas melengkung. Pelajaran → `calibrate.py` sekarang menolak frame kembar, memberi panduan cakupan & kemiringan, dan vonis LAYAK/ULANGI.
- **Kalibrasi berlaku per kamera.** Kamera lain wajib kalibrasi sendiri.

### Tes 1: akurasi posisi dari marker (11 Okt) — lulus untuk galat acak
- Marker ID 0 (sisi hitam terukur 80 mm) di benda kaku, digeser 0–45 cm di penggaris, kamera ±91 cm.
- Hasil dipakai (`data/pose_laptop_20261011_165046.csv`): galat acak **RMS 0,18 cm, maks 0,47 cm**; rotasi ≤ 2,2° (3,1° di ujung); jitter 0,4–2,1 mm.
- Ada **bias skala sistematis ±3%** (jarak menyamping terbaca kependekan, skala 0,971). Penyebab belum pasti. Dampak ke Drystone kecil (menjorok 40% terbaca ±38,9%). Dicek ulang dengan kardus asli 13 Okt.
- Input Tes 2: `--marker-mm 80 --pos-sd-cm 0.5`.

## Berikutnya
- **12 Okt:** mulai uji deteksi kardus tanpa marker (OpenCV 5 DNN, ArUco sebagai acuan). Siapkan lakban, selotip matte, beban.
- **13 Okt:** kardus datang → Tes 2 (10–15 susunan nyata vs prediksi; target cocok ≥ 80%) → go/no-go malamnya.
  - `python tools/predict_test.py --calib data/camera_laptop.yaml --marker-mm 80 --pos-sd-cm 0.5`
  - Tiap percobaan: susun 2–3 kardus, overhang ditopang buku → SPASI → ambil penyangga pelan-pelan → ketik r (roboh) / b (berdiri).

## Kardus
- 邮政纸箱 5号 五层特硬, 29 × 17 × 19 cm, 22 buah (sampai ±13 Okt).
- **Dipakai berdiri (flap di atas):** lebar 29 cm kiri-kanan (arah menjorok), tinggi 19 cm, dalam 17 cm. Tumpukan 3 = 57 cm → kamera ±0,9–1,0 m.
- Marker di tengah sisi depan polos 29 × 19 cm, ditempel selotip matte hanya di pinggiran putih.
- Lakban coklat kertas (matte), 1 lapis rata di atas & bawah. Lakban fragile opsional, hanya di samping/atas.
- Beban ±1 kg di tengah tiap kardus, diganjal; semua kardus berat sama; timbang dan isi `config/boxes.json`.
- Saat uji roboh: laptop di depan tumpukan, tidak di arah jatuhnya.

## Desain teknis (ringkas)
- OpenCV 5.0 (opencv-python 5.0.0.93): ChArUco untuk kalibrasi, ArUco DICT_4X4_50 marker kardus 80 mm (ID 0–11), solvePnPGeneric IPPE_SQUARE.
- MuJoCo 3.15 untuk simulasi (bukan PyBullet: tidak ada wheel Windows/Py3.12/ARM). Monte Carlo atas galat pose (dari Tes 1) dan pusat massa isi; sampel tambahan kalau P di 0,3–0,7.
- Per langkah cukup 1 foto dikirim ke AWS; preview real-time tetap di laptop. Replay simulasi digambar sebagai wireframe (`cv2.projectPoints`).
- Contoh adegan: hijau = 2 kardus 20%; kuning = 2 kardus ±45% (P ≈ 20%); merah/roboh = 3 kardus × 40% (P ≈ 100%).
- Tidak diklaim sebagai perangkat keselamatan bersertifikat; ini purwarupa alat bantu keputusan.

## Aturan kerja
- Semua jam waktu China.
- Secret (AWS key, API key) hanya di `.env` atau `aws configure` di laptop masing-masing. Jangan pernah di-commit. Tiap orang pakai IAM user sendiri.
- Repo akan public sebelum submit: jangan commit data pribadi atau info akun/pembayaran.
- Versi dependency di-pin di `requirements.txt`. Tiap klaim di README/laporan harus didukung angka evaluasi.
