# Drystone — Status Project

Salinan status untuk repo (dibaca Yasin, Vincent, dan Claude masing-masing). Update di commit yang sama setiap ada keputusan atau hasil tes baru. Semua jam = waktu China.

Terakhir diperbarui: 18 Okt 2026. Live: `drystone-service:f5b647b` (halaman web dengan foto asli; image ini masih memakai tinggi kardus 19 cm, lihat Tinggi kardus terukur).

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
| 4 | AWS: Lambda foto → keputusan, S3, DynamoDB log, dashboard approve/override, CloudWatch | 21 Okt | ⏳ Lambda + Function URL + `agent.py --aws` ✅; halaman web juri ✅ live dengan foto asli (`f5b647b`); sisa S3, DynamoDB, CloudWatch |
| 5 | Evaluasi 20–30 percobaan baru + kasus gagal. **Fitur dikunci** | 21 Okt malam (dimajukan) | — |
| 6 | Gladi (23) + rekam video (24) | 24 Okt | — |
| 7 | Laporan teknis, diagram, README | 25 Okt | — |
| 8 | Edit video, isi Devpost, submit | 26 Okt malam | — |

Uji deteksi kardus tanpa marker adalah target tambahan, hanya dikerjakan kalau inti + AWS selesai.

## Pembagian tugas
- **Yasin:** kamera/OpenCV, tes, simulasi, agent (juga pegang teknis Echolocate, freeze 22 Okt).
- **AWS dipegang Yasin** (keputusan 17 Okt), IAM user `yasin-dev` di laptop Yasin.
- **Vincent:** bantu video (24 Okt, belum dikonfirmasi), naskah, diagram; opsional kalibrasi webcam-nya + Tes 1.
- Vincent perlu daftar Devpost dan kirim username untuk diundang ke tim.

## Hasil
### Kalibrasi webcam laptop Yasin (11 Okt) — LAYAK
- 61 view, RMS 0,366 px, fx/fy 900,0 ± 3,9 (0,43%), gambar 1280×720, cakupan 12/12. File: `data/camera_laptop.yaml`. Kalibrasi berlaku per kamera.

### Tes 1: akurasi posisi dari marker (11 Okt)
- Galat acak RMS 0,18 cm (maks 0,47 cm), rotasi ≤ 2,2°. Bias skala ±3% belum terjelaskan (dampaknya kecil).

### Tes 2: prediksi vs kenyataan (17 Okt) — lulus
- 12 percobaan (2–3 kardus, menjorok 20–65%), 11 dihitung. Data: `data/tes2_20261017_125209/hasil.csv`.
- **Pengaturan awal (posisi 0,5 cm, isi 1 cm): cocok 9/11 = 82%, Brier 0,177, 1 roboh di zona HIJAU** (3 kardus +23%/+38%, P 1%). Dua salah prediksi sama-sama ke arah berbahaya, dekat batas (margin pusat massa 1,3 dan 2,5 cm).
- **Ketidakpastian dinaikkan (posisi 1 cm, isi 2 cm), lalu hitung ulang (`--recheck`): 82%, Brier 0,145, 0 roboh di zona HIJAU** (kasus dekat batas jadi KUNING). Data: `recheck_pos1_com2/hasil.csv`. Karena disetel pada data yang sama, **wajib divalidasi di percobaan baru pada evaluasi tahap 5 (21 Okt)**, dan evaluasi itu wajib memakai pipeline persepsi baru (arah rata-rata semua marker × 10 frame), karena Tes 2 masih memakai cara lama. Menjorok 30–35% (2 kardus) belum teruji.

### Agent (17 Okt) — jalan dengan kardus asli
- `tools/agent.py` + `tools/drystone_core.py`. Monte Carlo adaptif (150 → 600 sampel di dekat garis 10%/50%; kalau masih ambigu, dipilih zona yang lebih aman). Agent mengusulkan posisi hijau terdekat (grid 1 cm), foto ulang otomatis kalau bacaan jelek, override wajib nama + alasan, cek ulang setelah penempatan, log JSONL + foto.
- **Perbaikan persepsi:** arah hadap satu marker goyang beberapa derajat per frame. Cara lama (tengah kardus dari arah tiap marker, rotasi kardus bawah per frame) membuat posisi melompat 1,5–3,6 cm. Sekarang arah = rata-rata semua marker × 10 frame dan posisi = median, sehingga goyangnya ±0,1 cm (uji sintetis) dan biasnya juga hilang. Tes 2 masih memakai cara lama.
- Uji nyata: B +6 cm HIJAU → ditaruh +1,6 cm (MELESET, tetap hijau) · C diminta +12 cm → KUNING 40%, usulan +8 cm (4%) → ditaruh meleset +2,1 cm → agent memperingatkan KUNING 20–29% → dibetulkan → OK +0,8 cm, HIJAU 6%.

### Agent lewat AWS + versi Inggris (17 Okt malam)
- Lambda `drystone` jalan (container image ECR `drystone-service`, 2048 MB, timeout 60 dtk) + Function URL. `agent.py --aws` (atau env `DRYSTONE_URL`): keputusan & cek ulang dihitung di Lambda, 3 foto JPEG; kalau AWS gagal → dihitung di laptop dan tercatat.
- Simulasi dipercepat (berhenti saat jatuh/diam; identik di 1.500 sampel, ±2,9×): kasus YELLOW di server Lambda 16,3 → 3,8–5,6 dtk; round trip dari laptop 7–8,5 dtk.
- Usulan posisi dikonfirmasi 150 simulasi sebelum disebut GREEN. Tampilan live dihaluskan (goyang wireframe 8,4 → 2,1 px).
- Uji nyata via AWS: B +6 cm GREEN → cek OK · C +12 cm YELLOW 25–37% → usulan +8/+10 cm → ditaruh pas (±0,3 cm).
- Semua teks produk sekarang bahasa Inggris (GREEN/YELLOW/RED, GUIDE/ASK_SUPERVISOR/REJECT, OK/OFF_PLAN/FELL).

### Layanan AWS (17 Okt) — kode
- `tools/service.py`: 1–5 foto → keputusan JSON (mode decide / check), `lambda_handler`. Uji dengan foto asli: +6 cm HIJAU 1% (1,7 dtk), +12 cm KUNING 41% + usulan (8,3 dtk), +16 cm MERAH 87% (8,2 dtk). Jalan di Python 3.12 bersih dengan paket Lambda (OpenCV headless).

### Tinggi kardus terukur (18 Okt)
- Penggaris (tengah / pojok): ID 0 19,7 / 19,5 · ID 1 19,6 / 19,4 · ID 2 19,4 / 19,3 cm → `config/boxes.json` (rata-rata, dibulatkan 0,1 cm): **ID 0 19,6 · ID 1 19,5 · ID 2 19,4 cm** (dulu 19). ID 3 dan ID 4 = 19,5 cm **perkiraan** sampai diukur. Panjang 29, tebal 17, massa tidak diubah.
- Tengah marker dari dasar kardus: ID 0 9,4 · ID 1 9,7 · ID 2 9,7 cm. Sisi hitam marker terukur **80 mm** (sama dengan `DRYSTONE_MARKER_MM`).
- **Jarak antar-marker ID 0 → ID 1 terbaca 20,2 cm** (foto s2/s3), padahal katalog dulu 19. Penjelasan: tinggi asli ID 0 (19,6) − tengah marker ID 0 (9,4) + tengah marker ID 1 (9,7) = **19,9 cm**; marker ID 0 ditempel 0,3 cm lebih rendah dari ID 1. Sisa 0,3 cm (±1,5%) masuk dalam bias skala ±3% dari Tes 1.
- **Tes 2 tidak berubah** dengan tinggi terukur (`--recheck` di salinan CSV, hasil yang di-commit tidak ditimpa): setelan 0,5/1 → 82%, Brier 0,177, 1 roboh di HIJAU; setelan 1/2 → 82%, Brier 0,145, 0 roboh di HIJAU; P(fall) ke-11 percobaan identik dengan 19 cm. **Zona contoh halaman juga identik** (tabel di bawah tetap berlaku).
- **Tes kontrol** (s2, geser +12/+13/+14 cm, tinggi semua kardus diubah): 19 cm 14,2% / 26,7% / 41,3% · 19,5 cm sama persis · 25 cm 14,3% / 27,3% / 42,0% · 40 cm 15,3% / 28,0% / 42,0%. Tinggi hampir tidak memengaruhi P(fall); yang menentukan adalah posisi horizontal titik berat terhadap tepi kardus di bawahnya.
- **Image live `f5b647b` masih memakai tinggi 19 cm.** Hasilnya identik (dicek di atas); `boxes.json` baru ikut di deploy berikutnya.

### Halaman web juri (17 Okt malam) — kode + tes
- Function URL yang sama (tidak dibuat ulang, cukup update image): `GET /` halaman (`web/index.html`), `GET /samples/<id>.jpg`, `POST {"sample","offset_cm"}` keputusan, `POST /log` approve/override. POST foto lama (`images`) tidak berubah → `agent.py --aws` tetap jalan. Function URL tidak ditulis di repo; README publik merujuk ke halaman Devpost.
- Acuan geseran: **dari kardus tepat di bawah** (sama dengan `drystone_core.candidate_box`), bulat 1 cm, rentang −16…+16 cm. Tertulis di halaman.
- Halaman: canvas foto + marker + kerangka kardus, P(fall) + zona berwarna, tindakan + usulan, trace bernomor 5 tahap (deteksi marker → kembaran digital → simulasi → keputusan → tindakan) dengan ms per tahap dan tanda cached. KUNING approve / use suggestion / reject; MERAH use suggestion / override / cancel. "Use suggestion" menggeser slider ke usulan lalu menganalisis ulang (loop saran → cek ulang → HIJAU). Override wajib nama + alasan, hanya dicatat (satu baris JSON `web_supervisor_choice` di CloudWatch, tanpa IP), keputusan tidak berubah. Loading "Analyzing… first run can take ~10 s". Disclaimer purwarupa. Tanpa upload foto. Halaman/foto pakai `Cache-Control`.
- **Foto contoh asli (18 Okt 00.30)** menggantikan placeholder: webcam laptop 1280×720, ±1 m, tembok polos, tanpa wajah/kamar/barang pribadi (dicek). Semua marker terbaca; bacaan: s2 ID 1 +0,1 cm, s3 ID 1 **+6,3 cm**; tinggi antar kardus terbaca 20,2–20,3 cm (katalog 19, masalah lama). Kerangka calon −16…+16 cm (dan usulan) masuk seluruhnya ke foto, jarak minimal 112 px ke tepi.
- Adegan (hitungan `drystone_core` dari foto asli, seed 0, 150 simulasi):

  | Contoh | Susunan | Kardus berikutnya | HIJAU | KUNING (usulan) | MERAH (usulan) |
  |---|---|---|---|---|---|
  | s1 | ID 0 saja | ID 1 | +6 cm, 0% | +14 cm, 35% (+11 cm, 5%) | +16 cm, 73% (+11 cm, 5%) |
  | s2 | ID 0 + ID 1 lurus | ID 2 | +6 cm, 0% | **+13 cm**, 27% (+10 cm, 3%) | +16 cm, 69% (+10 cm, 3%) |
  | s3 | ID 0 + ID 1 digeser +6,3 cm | ID 2 | +4 cm, 0% | +12 cm, 25% (+10 cm, 6%) | +16 cm, 77% (+10 cm, 7%) |

  Pindaian dari foto asli: s1 +11 6% / +12 12% / +15 62%; s2 +11 7% / +12 14% / +14 41% / +15 58%; s3 +10 6% / +11 13% / +14 51%. s2 KUNING diganti +14 → **+13 cm** karena 41% terlalu dekat garis 50% (interval ±8%). Geseran dekat garis 10%/50% tidak dipakai sebagai contoh.
- Cache foto: halaman memuat `samples/<id>.jpg?v=<photos_version>` (`photos_version` = 10 hex pertama sha256 foto, dicek tes) dan `samples.json` dikirim `no-cache`, jadi foto yang diganti tidak tampil dari cache browser (foto tetap `max-age` 1 hari). Ditemukan saat cek lokal: tanpa ini, browser yang pernah membuka halaman menampilkan placeholder lama dengan kerangka dari foto asli.
- Tes: `tests/test_web.py` 25 lulus (200, zona semua contoh, loop usulan → HIJAU, cache + pembulatan, 400 override tanpa nama/alasan, tombol sesuai zona, 413 web/foto, 429 GET/POST, POST foto lama + direct invoke tidak berubah). `pytest` hanya di `requirements-dev.txt`, tidak masuk image Lambda.
- Alat: `tools/web_local.py` (server lokal, event Function URL palsu), `tools/capture_sample.py` (foto contoh mentah tanpa anotasi; tolak kalau ada marker hilang di salah satu dari 10 frame; cetak geseran antar kardus dalam cm), `tools/make_placeholder_samples.py` (render sintetis lewat kalibrasi asli; hanya untuk sampel bertanda `placeholder`, foto asli tidak ditimpa).
- **Batasan perlindungan:** reserved concurrency **tidak bisa dipasang** (limit concurrency akun = 10, AWS mewajibkan 10 tetap unreserved; cek 17 Okt). Batas 60 GET + 20 POST per menit per IP dan cache **berlaku per container** (in-memory), jadi dengan banyak container batas efektif bisa lebih tinggi. Biaya tetap terbatas: cache maksimal 3 × 33 = **99 entri per container** (hasil deterministik), body JSON web ≤ 16 KB, POST foto ≤ 2 MB, dan akun Free plan.

### Deploy halaman web (17 Okt malam)
- **Rollback image** (yang jalan sebelum deploy halaman web; dulu ber-tag `:latest`, tag itu sekarang tertimpa, jadi pakai digest):
  `<account>.dkr.ecr.ap-southeast-1.amazonaws.com/drystone-service@sha256:9afba661f36d7f3582315ecef1d3777d2eb06c584f38c7fc3e8bd9e87be27261`
  (`<account>` = nomor akun AWS, sengaja tidak ditulis di repo.)
- **Rollback ke image lama** (cmd, dari folder repo; ganti `<account>` dengan nomor akun, lihat dengan `aws sts get-caller-identity --query Account --output text`):
  ```
  aws lambda update-function-code --function-name drystone --image-uri <account>.dkr.ecr.ap-southeast-1.amazonaws.com/drystone-service@sha256:9afba661f36d7f3582315ecef1d3777d2eb06c584f38c7fc3e8bd9e87be27261 --region ap-southeast-1 --query LastUpdateStatus
  ```
  ```
  aws lambda wait function-updated --function-name drystone --region ap-southeast-1
  ```
  ```
  aws lambda get-function --function-name drystone --region ap-southeast-1 --query "{Uri:Code.ImageUri,Status:Configuration.LastUpdateStatus}"
  ```
  Function URL tidak berubah karena rollback. Untuk kembali ke versi halaman web: perintah pertama dengan `drystone-service:7e9f416` sebagai pengganti `drystone-service@sha256:...`.
- Image baru di-push dengan dua tag: `:latest` dan hash commit `main`. Lambda di-update ke tag hash, bukan `:latest`.
- **Live sejak 17 Okt 23.25: `drystone-service:7e9f416`** (digest `sha256:ac87187c…`), Function URL tetap sama. ECR tanpa lifecycle policy, jadi image lama tidak terhapus otomatis.
- Tes live (dari laptop, China → Singapura): `GET /` 200 (cold start 5,4 dtk) · foto contoh 200 · `POST` s2 +16 cm → RED 69%, usulan +10 cm 3% (round trip 7,7 dtk, server 5,9 dtk; kedua kali `cached` 1,7 dtk) · POST foto lama (`test_endpoint.py`, s2 +6 cm) → GREEN 0% (5,6 dtk) · `POST /log` → baris `web_supervisor_choice` muncul di CloudWatch. Tidak ada baris error.
- **Tes dari HP lewat data seluler (Wi-Fi mati), 17 Okt 23.45 — lulus:** loading cold start muncul · s2 +16 cm → RED · "Use suggestion" → +10 cm GREEN · override tanpa nama/alasan ditolak · halaman tidak bisa digeser ke samping · s1 dan s3 tampil.

### Deploy foto asli (18 Okt)
- **Rollback target** (yang jalan sebelum deploy ini): `drystone-service:7e9f416` (digest `sha256:ac87187cb0ff494ddf5742c5e08841cd0f3360a8b709b54734c97707fd783c2d`, halaman web dengan foto placeholder). Tag `7e9f416` tetap ada di ECR. Rollback (cmd; ganti `<account>`):
  ```
  aws lambda update-function-code --function-name drystone --image-uri <account>.dkr.ecr.ap-southeast-1.amazonaws.com/drystone-service:7e9f416 --region ap-southeast-1 --query LastUpdateStatus
  ```
  ```
  aws lambda wait function-updated --function-name drystone --region ap-southeast-1
  ```
  ```
  aws lambda get-function --function-name drystone --region ap-southeast-1 --query "{Uri:Code.ImageUri,Status:Configuration.LastUpdateStatus}"
  ```
- Image baru: `drystone-service:f5b647b` (+ `:latest`, digest `sha256:7f243d8f…`). Commit dokumen sesudahnya tidak mengubah image (`docs/` tidak masuk build).
- **Live sejak 18 Okt 00.45: `drystone-service:f5b647b`**, Function URL tetap sama.
- Tes live (dari laptop): `GET /` 200 (3,3 dtk) · `samples.json` `no-cache`, `photos_version` a7aba3ca6c, tidak ada tanda placeholder, contoh s2 KUNING +13 · foto `?v=a7aba3ca6c` s1–s3 identik (sha256) dengan foto asli di repo, bukan placeholder · `POST` s2 +16 cm → RED 69%, usulan +10 cm 3%, `placeholder: false`, ID 1 x +0,1 cm (7,7 dtk) · POST foto lama (`test_endpoint.py`, s2 +6 cm) → GREEN (4,1 dtk) · `POST /log` → baris `web_supervisor_choice` (`placeholder: false`) muncul di CloudWatch · 0 baris error.

## Wajib sebelum submit
- **Cek di HP** bahwa foto asli tampil tanpa label "placeholder image" (HP yang kemarin membuka halaman menyimpan foto lama di cache; `?v=` seharusnya mengatasinya).
- **Validasi setelan ketidakpastian** (posisi 1 cm, isi 2 cm) di percobaan baru (evaluasi 21 Okt, pipeline persepsi baru), target **0 roboh di zona GREEN**.
- **Vincent masuk tim di Devpost.**
- **Cek Official Rules** apakah repo wajib publik.

## Berikutnya
- **18–19 Okt:** foto contoh asli · S3 + DynamoDB log · latihan adegan override → roboh · tempel ulang marker ID 2.
- **20 Okt:** CloudWatch, rapikan, cadangan.
- **21 Okt:** evaluasi 20–30 percobaan baru dengan pipeline persepsi baru (akurasi, Brier, roboh di zona GREEN, waktu keputusan, retake, fallback) + kasus gagal; sekaligus validasi setelan ketidakpastian Tes 2; malamnya fitur dikunci.

## Kardus
- 邮政纸箱 5号, 29 × 17 × 19,3–19,7 cm, dipakai berdiri: lebar 29 cm kiri-kanan (arah menjorok), tinggi terukur rata-rata ID 0 19,6 · ID 1 19,5 · ID 2 19,4 cm (ID 3–4 19,5 perkiraan), dalam 17. Marker 80 mm (terukur) di tengah sisi depan; tengah marker dari dasar ID 0 9,4 · ID 1 9,7 · ID 2 9,7 cm. Isi 1,0 kg di tengah, semua sama. ID 0 selalu di bawah. Hanya kardus yang ditumpuk boleh terlihat kamera.
- Kamera ±0,95–1,0 m. Saat uji roboh, laptop jangan di arah jatuhnya.

## Aturan kerja
- Semua jam waktu China.
- Secret (AWS key, API key) hanya di `.env` atau `aws configure`. Jangan pernah di-commit. Tiap orang pakai IAM user sendiri.
- Repo akan dibuat public sebelum submit: jangan commit data pribadi, foto kamar/wajah, atau info akun/pembayaran.
- Versi dependency di-pin. Tiap klaim di README/laporan harus didukung angka evaluasi. Drystone adalah alat bantu keputusan, bukan perangkat keselamatan bersertifikat.
