# Drystone — Status Project

Salinan status untuk repo (dibaca Yasin, Vincent, dan Claude masing-masing). Update di commit yang sama setiap ada keputusan atau hasil tes baru. Semua jam = waktu China.

Terakhir diperbarui: 23 Okt 2026. Live: `drystone-service:f465e07` (halaman juri + link lembar cetak, sejak 23 Okt 23.40; rollback `37b1380`). **Evaluasi 25 percobaan baru selesai: FAIL (C2b, kelebihan 1 roboh); C1, C2a, C3, C4 lulus.**

## Ringkasan
- **Lomba:** OpenCV AI Competition 2026 (https://opencv26.devpost.com/). Deadline **27 Okt, 14.45** (target submit 26 Okt malam). Penjurian 27 Okt–10 Nov, endpoint harus tetap hidup.
- **Tim:** Yasin (lead) + Vincent.
- **Ide:** Drystone, "prediksi sebelum menumpuk". Kamera + OpenCV 5 membaca pose tiap kardus (marker ArUco) dan membangun kembaran digital. Simulasi MuJoCo Monte Carlo menghitung P(roboh) calon penempatan. Agent: HIJAU < 10% pandu · KUNING 10–50% minta persetujuan supervisor · MERAH > 50% tolak + usul posisi lain (lanjut hanya lewat override dengan alasan tercatat). Setelah kardus ditaruh: cek ulang (sesuai / meleset / roboh). Keputusan keselamatan deterministik, bukan LLM.
- **Wajib lomba:** analisis gambar pakai OpenCV 5; bagian penting jalan di AWS (ap-southeast-1, tanpa Marketplace). Akun AWS **Paid plan** (dicek 18 Okt: PAID, ACTIVE, kredit 0, tagihan Okt USD 0,00; tidak bisa turun ke Free plan): tetap dalam kuota gratis (Lambda 1 juta request dan 400.000 GB-detik/bulan, CloudWatch Logs 5 GB), tanpa AWS Marketplace, alarm Zero spend budget lewat email (`zero-spend-opencv`). Kumpulkan laporan teknis, repo, diagram arsitektur, endpoint web/demo live, video ≤ 5 menit (wajah tim), bukti evaluasi termasuk kasus gagal.
- **Target hadiah:** Agentic Vision Award + juara utama.

## Tahapan dan deadline
| # | Tahap | Deadline | Status |
|---|---|---|---|
| 0 | Persiapan | 11 Okt | ✅ |
| 1 | Uji kelayakan: kalibrasi, Tes 1, Tes 2, go/no-go | 17 Okt | ✅ **GO** |
| 2+3 | Persepsi + fisika + agent | 19 Okt | ✅ inti jalan dengan kardus asli (17 Okt) |
| 4 | AWS: Lambda foto → keputusan, halaman web juri dengan approve/override | 21 Okt | ✅ Lambda + Function URL + `agent.py --aws`; halaman web juri live dengan foto asli (`3b023a4`); log approve/override masuk CloudWatch Logs. S3, DynamoDB, dashboard/alarm CloudWatch → Bonus |
| 5 | Evaluasi 20–30 percobaan baru + kasus gagal. **Fitur dikunci** | 21 Okt malam (dimajukan) | ✅ dijalankan 18 Okt (25/25, protokol dikunci `8a953e4`): **FAIL di C2b** (12 roboh, interval 6–11); C1, C2a, C3, C4 lulus. Fitur dikunci. |
| 6 | Review naskah/diagram (23) + rekam video (24) | 24 Okt | — (Vincent dikonfirmasi) |
| 7 | Laporan teknis, diagram, README | 25 Okt | ⏳ README dan draf REPORT ada; finalisasi 23 dan 25 Okt |
| 8 | Edit video + isi Devpost (25), repo publik + submit (26) | 26 Okt | — (form Devpost sudah dicek) |

Target tambahan (S3, DynamoDB, dashboard/alarm CloudWatch, deteksi tanpa marker) ada di bagian Bonus, hanya dikerjakan kalau inti selesai.

## Pembagian tugas
- **Yasin:** kamera/OpenCV, tes, simulasi, agent (juga pegang teknis Echolocate, freeze 22 Okt).
- **AWS dipegang Yasin** (keputusan 17 Okt), IAM user pribadi di laptop Yasin.
- **Vincent:** sudah masuk tim Drystone di Devpost; naskah, diagram, dan **rekam video Sabtu 24 Okt (dikonfirmasi)**.
- Form submit Devpost sudah dicek.

## Hasil
### Kalibrasi webcam laptop Yasin (11 Okt) — LAYAK
- 61 view, RMS 0,366 px, fx/fy 900,0 ± 3,9 (0,43%), gambar 1280×720, cakupan 12/12. Kotak ChArUco tercetak 30 mm, terukur **29,8 mm** (dipakai di kalibrasi). File: `data/camera_laptop.yaml`. Kalibrasi berlaku per kamera.

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

### Alur video final, teruji dengan kardus asli 18 Okt
Latihan final 18 Okt 13.36–13.41, `agent.py --aws`, Lambda `drystone-service:3b023a4`. Log: `data/agent_20261018_133639/log.jsonl` (tidak di-commit, foto memuat wajah). Semua langkah lulus; tidak ada pertanyaan f/p, marker ID 2 terbaca terus. Naskah adegan untuk rekaman 24 Okt dan draf naskah video Vincent.

**Persiapan**
- Kamera laptop ±1 m, latar polos, cahaya cukup (marker pudar di cahaya redup tidak terbaca). Hanya kardus yang ditumpuk terlihat kamera; ID 1 dan ID 2 disiapkan di luar pandangan. ID 0 sudah di lantai, di tengah gambar.
- cmd, dari folder repo, satu per baris:
  ```
  cd /d E:\opencv-project
  ```
  ```
  .venv\Scripts\activate
  ```
  ```
  set DRYSTONE_URL=<Function URL>
  ```
  ```
  python tools/agent.py --calib data/camera_laptop.yaml --marker-mm 80 --aws %DRYSTONE_URL%
  ```
- Tombol di jendela kamera: **D** / **A** geser calon 1 cm ke kanan / kiri · **SPASI** minta keputusan, atau cek ulang setelah kardus ditaruh · **X** batalkan rencana · **Q** selesai. Jawaban supervisor diketik di cmd.

**Adegan (urutan teruji, angka dari latihan final)**

| # | Yang dilakukan | Tombol / jawaban | Yang tampil (latihan final) |
|---|---|---|---|
| 1 | Geser calon ID 1 ke +6 cm, minta keputusan | **D** ×6, **SPASI** | GREEN 0% → GUIDE, kerangka hijau (Lambda 5,0 dtk) |
| 2 | Taruh ID 1 di kerangka, lepas tangan, cek ulang | **SPASI** | check OK (−0,4 cm), tumpukan GREEN |
| 3 | Geser calon ID 2 ke +18 cm, minta keputusan | **D** ×18, **SPASI** | **RED 93%** → REJECT. Trace margin: +10 cm (4%) ditolak karena +11 cm 12%; usulan **+9 cm** (1%, +10 cm 4% juga GREEN). Lambda 10,0 dtk (server 7,1) |
| 4 | Supervisor memaksa | **o**, nama (Yasin), alasan (≥ 5 huruf) | "override logged. The supervisor takes responsibility for the risk." |
| 5 | Taruh ID 2 di +18 cm, lepas → roboh ke lantai, cek ulang | **SPASI** | **FELL** "box ID 2 is on the floor next to the stack -> it fell" + "box ID 2 fell. Pick it up and keep it out of the camera view, then press SPACE to plan ID 2 again." (sekali, tanpa retake; cek 3,1 dtk) |
| 6 | Angkat ID 2 keluar pandangan, minta keputusan lagi (geseran tetap +18) | **SPASI** | "planning box ID 2 again after it fell", RED 93% lagi, usulan +9 cm (Lambda 10,4 dtk, server 7,5) |
| 7 | Pakai usulan agent | **s** | kerangka hijau di +9 cm |
| 8 | Taruh ID 2 di kerangka hijau, lepas, cek ulang | **SPASI** | check OK (−0,3 cm), tumpukan **GREEN 1%** (cek 3,9 dtk) |
| 9 | Selesai | **Q** | ringkasan: decisions 3, GREEN 1, RED 2, override 1, fell 1, retry_after_fall 1 |

- Durasi aksi di latihan: ±2,5 menit (13.38.07–13.40.34), termasuk tunggu Lambda ±10 dtk per keputusan MERAH.
- Kalau SPASI cek ulang ditekan sebelum kardus ditaruh, atau markernya tidak terbaca: agent bertanya "f = it fell out of view, p = not placed yet" → jawab **p**, taruh kardus, **SPASI** lagi.
- Untuk video: +18 cm (93–95% di semua latihan). Keselamatan saat uji roboh: laptop jangan di arah jatuhnya.

### Latihan alur setelah jatuh dengan kardus asli (18 Okt 12.46–12.58, `agent.py --aws`)
- Log: `data/agent_20261018_124638/log.jsonl` (tidak di-commit: foto per langkah memuat **wajah dua orang**).
- **Jatuh nyata: 3/3 override MERAH roboh** (ID 2 +18 cm 95%, +19 cm 98%, +18 cm 94% → P 94–98%), **FELL terdeteksi 3/3** ("on the floor next to the stack"), pesan "Pick it up…" sekali, tanpa loop retake.
- **Alur video lengkap berhasil** (percobaan terakhir): ID 2 +18 cm RED 94% → override → roboh → FELL → "Pick it up…" sekali → keputusan ulang → s → +10 cm → cek OK (+0,5 cm, tumpukan P 7% GREEN).
- Waktu: keputusan MERAH lewat Lambda 8,5–10,3 dtk round trip; HIJAU 3,7–5,6 dtk; cek ulang 3,0–6,9 dtk.
- **2 FELL palsu** "not on the stack and not visible" (ringkasan log mencatat fell: 5, yang nyata 3), sudah diperbaiki (lihat di bawah):
  - Langkah 11 (setelah s di +9 cm): foto menunjukkan ID 2 **sudah berdiri di tumpukan**, tapi markernya tidak terbaca (kontras rendah siang hari; terbaca kalau gambar diperbesar 2×). Bukan SPASI terlalu cepat.
  - Langkah 13: ID 1 dan ID 2 sudah diangkat; agent merencanakan ID 2 di atas tumpukan [0] ("1 box(es)"), lalu yang ditaruh ID 1 → ID 2 tidak terlihat.
- **Usulan terlalu dekat garis 10%:** usulan +9 cm (P 5%) ditaruh meleset +1,3 cm → tumpukan YELLOW 18% (langkah 19). Kesalahan penempatan nyata di latihan: 0,0–1,3 cm.

### Perbaikan alur (18 Okt siang) — laptop saja, belum deploy
- **Kardus calon tidak terlihat sama sekali dan tumpukan di bawahnya utuh** → agent bertanya "box ID 2 is not visible. f = it fell out of view, p = not placed yet (look again)"; jawaban dicatat (`worker_answer`). p → rencana tetap, lihat lagi; f → FELL "(confirmed by the worker)". Kardus yang terlihat di lantai tetap otomatis FELL tanpa bertanya.
- **Tumpukan berubah:** kalau kardus yang tadi berdiri hilang, agent bilang "stack changed: ID 1 is missing from the stack." (log `stack_changed`) dan merencanakan ulang menurut urutan ID (ID 1 dulu, bukan ID 2). Kardus yang tadi dianggap jatuh tapi kini berdiri: `back_on_stack`. "every box in the catalogue is already on the stack" hanya kalau semua kardus memang berdiri.
- Tes kamera palsu `tests/test_agent_flow.py` (lokal dan `--aws`): jatuh → angkat → keputusan ulang → s → OK · SPASI sebelum menaruh → tanya → p → lihat lagi → OK (fell 0) · jawaban f → FELL · ID 1 diangkat → "stack changed" → ID 1 direncanakan lagi. Total 48 tes lulus.
- Lambda tidak memakai loop ini → **tidak perlu deploy** untuk perbaikan ini.

### Usulan dengan margin 1 cm (18 Okt) — aturan A dipakai, live di `3b023a4`
- **Kasus nyata (latihan 18 Okt, langkah 19):** usulan +9 cm (P 5%) ditaruh meleset +1,3 cm → tumpukan YELLOW 18%. Kesalahan penempatan nyata di latihan: 0,0–1,3 cm.
- **Analisis (7 kasus:** 6 contoh KUNING/MERAH halaman juri + tumpukan latihan langkah 17): aturan A (posisi usulan DAN posisi 1 cm lebih jauh ke arah bahaya sama-sama GREEN) dan aturan B (P ≤ 5% dan batas atas 95% < 10%) memberi usulan yang sama di 7/7 kasus, 1 cm lebih dekat, **P usulan 1–3%**, dan kalau meleset +1 cm P tetap ≤ 7%. Dengan aturan lama, meleset +1 cm memberi **P 10–14% (YELLOW)**.
- **Keputusan: aturan A** di `drystone_core.search_alternative` (satu sumber untuk laptop dan Lambda). Trace menulis kedua angka, misalnya "try +10 cm: P = 3%, but 1 cm further out (+11 cm P = 12%) is not green -> no margin, keep looking" lalu "try +9 cm: P = 1%; 1 cm further out (+10 cm P = 3%) also green -> suggestion". JSON usulan berisi `further_offset_cm` dan `p_further`; halaman juri menulis "The suggested spot stays green even if the box lands 1 cm further out"; README juga.
- Usulan baru di halaman (hitungan dari foto asli, `suggestion_cm` di `samples.json`, dicek tes): **s1 +10 cm** (3%; +11 cm 5%), **s2 +9 cm** (1%; +10 cm 3%), **s3 +9 cm** (1–2%; +10 cm 6–7%). Zona contoh tidak berubah. Waktu keputusan KUNING/MERAH di laptop 4,5–12 dtk (dulu 3,4–7 dtk), karena posisi tambahan disimulasikan.

### Setelan detektor marker (18 Okt) — diuji, DITOLAK
- Usulan: `adaptiveThreshConstant` 7 → 3 untuk membaca marker pudar (ID 2 di langkah 11 latihan kedua tidak terbaca).
- Validasi di **148 foto asli** (126 foto latihan 17–18 Okt, 15 foto Tes 2, 1 foto service, 3 foto contoh, 3 foto contoh mentah): marker terbaca **341 vs 340** (hanya ID 2 langkah 11 bertambah, tidak ada yang hilang), **0 deteksi palsu**. Tapi **sudut marker bergeser sampai 6,4 px** (56 dari 340 marker > 0,1 px), keluar dari bingkai hitam ke kertas putih di foto yang lebih gelap, sehingga **posisi kardus meleset sampai 61 mm di 44 bacaan** (> 1 mm). Gagal syarat ≤ 0,1 cm → **ditolak**, detektor tetap setelan lama.
- Penanganan marker yang tidak terbaca: pertanyaan f/p di agent ("box ID 2 is not visible. f = it fell out of view, p = not placed yet"), **cetak ulang marker kalau pudar**, dan **cahaya cukup saat rekaman**.

### Latihan override → roboh dengan kardus asli (18 Okt 02.37–02.48, `agent.py --aws`)
- Log: `data/agent_20261018_023749/log.jsonl` (tidak di-commit; folder berisi foto). ID 1 HIJAU di +6 cm tiap kali (cek ulang OK, −0,5 / +0,1 / −0,0 cm).
- **3 percobaan ID 2 MERAH** (+17 cm 86%, +18 cm 95%, +18 cm 95%), semua override oleh Yasin, **semua roboh (3/3)**, **FELL terdeteksi 3/3** ("box ID 2 is on the floor next to the stack -> it fell"), tanpa retake. Perbaikan cek ulang terbukti dengan kardus asli.
- Waktu: keputusan MERAH lewat Lambda **8,8–9,5 dtk** round trip (server 5,9–6,6 dtk); keputusan HIJAU 3,8–5,2 dtk; cek ulang **2,9–4,1 dtk**.
- Usulan agent selalu **+10 cm**, P(fall) 4,0 / 5,7 / 5,3%.
- **Untuk video: pakai +18 cm (95%).**
- Ditemukan bug alur setelah FELL (lihat di bawah): agent langsung meminta keputusan berikutnya, retake otomatis 3× untuk ID 2 yang masih di lantai (langkah 7–15 di log, 3 kali SPASI), dan ID 2 tidak ditawarkan lagi.

### Alur setelah FELL (18 Okt) — diperbaiki di laptop, belum diuji dengan kardus asli
- Setelah FELL, kardus yang jatuh kembali berstatus "belum ditaruh"; tumpukan = kardus yang masih berdiri. Agent berhenti dengan instruksi "box ID 2 fell. Pick it up and keep it out of the camera view, then press SPACE to plan ID 2 again." Geseran yang diminta dipertahankan, jadi keputusan ulang menampilkan risiko dan usulan yang sama (pilih s → kotak hijau → cek ulang OK).
- SPASI saat kardus yang jatuh masih terlihat: satu bacaan, instruksi diulang, tercatat `wait_pickup`; tidak ada retake otomatis. Untuk keputusan biasa, kardus di luar tumpukan juga tidak lagi di-retake 3× (kardus tidak pindah sendiri): satu pesan, tunggu pekerja.
- Kardus yang jatuh direncanakan ulang lebih dulu. "every box in the catalogue is already on the stack" hanya kalau semua kardus berdiri di tumpukan. Ringkasan akhir punya `retry_after_fall`; log keputusan punya `retry_after_fall`, log cek punya `fell_ids`.
- Tes `tests/test_agent_flow.py` (kamera palsu, loop `agent.py` utuh, lokal dan `--aws` lewat handler Lambda): ID 1 HIJAU → ID 2 MERAH → override → jatuh → FELL → SPASI saat masih di lantai (1× `wait_pickup`, 0 retake) → diangkat → keputusan ulang ID 2 MERAH → s → OK. Tes gagal dengan kode lama. Total 42 tes lulus.
- Hanya loop laptop yang berubah (`main`, `perceive`); Lambda tidak memakainya, jadi **tidak perlu deploy** untuk perbaikan ini.

### Bug cek ulang setelah override MERAH (18 Okt) — diperbaiki, live di `9523213`
- **Kejadian:** ID 2 di +18 cm, RED 95%, override Yasin. ID 2 jatuh dan mendarat tegak di lantai, kanan tumpukan. Layar `stack: [0, 2, 1]`; cek ulang 3× "box ID 1 is not on the stack (lying next to it?) -> move it out of the camera view" lalu "still failing". Jatuhnya tidak tercatat.
- **Penyebab (direproduksi dengan foto sintetis):** (1) urutan tumpukan diambil dari tinggi di gambar, jadi kardus di lantai samping tumpukan (y ≈ 0) masuk ke urutan, dan pesan menyebut kardus yang salah; (2) arah hadap gabungan ikut merata-ratakan marker kardus yang jatuh: kardus di lantai yang berputar 20 / 35 / 50° memiringkan acuan seluruh tumpukan 6 / 11 / 16° (juga sebab kerangka merah miring di layar). Angka persis "ID 1" dari kejadian asli tidak tereproduksi; kedua penyebab ini tetap diperbaiki.
- **Perbaikan** (`tools/agent.py`, dipakai laptop dan Lambda): tumpukan dibangun dari ID 0 ke atas lewat kontak (dasar kardus berikutnya ±4 cm dari atas kardus di bawahnya + tumpang-tindih horizontal); kardus lain = "di luar tumpukan" dengan lokasi (lantai / samping / melayang di atas). Arah hadap dihitung dari marker kardus dasar dulu, lalu dari anggota tumpukan saja. Tampilan live juga. Untuk keputusan, kardus di luar tumpukan tetap ditolak ("box ID 2 is on the floor next to the stack, not on it -> move it out of the camera view", ID benar). Untuk cek ulang (`drystone_core.verify`, laptop dan `service.py` mode check): kardus calon di lantai / di samping / melayang → **FELL**, tercatat di log, tanpa retake; kardus calon tidak terlihat sama sekali dan tumpukan lain utuh → **FELL** ("likely fell out of view"; dulu NOT_PLACED/WAIT).
- **Tes** `tests/test_check.py` (foto sintetis lewat kalibrasi asli, jalur laptop + jalur Lambda): (a) jatuh tegak di samping → FELL · (b) jatuh rebah di samping → FELL · (c) jatuh keluar frame → FELL · (d) penempatan normal → OK · (e) tergeser 3 cm → OFF_PLAN (bukan FELL) · kardus jatuh berputar 35° tidak lagi menggeser bacaan tumpukan (ID 1 x < 0,5 cm) · kardus melayang di atas = gap. Total 40 tes lulus. Loop `agent.py` dengan kamera palsu (RED +18, override, jatuh di samping): `check: FELL - box ID 2 is on the floor next to the stack -> it fell`, `fell: 1` di ringkasan, tanpa retake.
- **Live sejak 18 Okt 02.30 di `drystone-service:9523213`**, juga untuk `agent.py --aws` (cek ulang di Lambda). Halaman juri tidak terpengaruh: zona ketiga contoh identik (dicek live).

### Tinggi kardus terukur (18 Okt)
- Penggaris (tengah / pojok): ID 0 19,7 / 19,5 · ID 1 19,6 / 19,4 · ID 2 19,4 / 19,3 cm → `config/boxes.json` (rata-rata, dibulatkan 0,1 cm): **ID 0 19,6 · ID 1 19,5 · ID 2 19,4 cm** (dulu 19). Panjang 29, tebal 17, massa tidak diubah.
- Tengah marker dari dasar kardus: ID 0 9,4 · ID 1 9,7 · ID 2 9,7 cm. Sisi hitam marker terukur **80 mm** (sama dengan `DRYSTONE_MARKER_MM`).
- **Jarak antar-marker ID 0 → ID 1 terbaca 20,2 cm** (foto s2/s3), padahal katalog dulu 19. Penjelasan: tinggi asli ID 0 (19,6) − tengah marker ID 0 (9,4) + tengah marker ID 1 (9,7) = **19,9 cm**; marker ID 0 ditempel 0,3 cm lebih rendah dari ID 1. Sisa 0,3 cm (±1,5%) masuk dalam bias skala ±3% dari Tes 1.
- **Tes 2 tidak berubah** dengan tinggi terukur (`--recheck` di salinan CSV, hasil yang di-commit tidak ditimpa): setelan 0,5/1 → 82%, Brier 0,177, 1 roboh di HIJAU; setelan 1/2 → 82%, Brier 0,145, 0 roboh di HIJAU; P(fall) ke-11 percobaan identik dengan 19 cm. **Zona contoh halaman juga identik** (tabel di bawah tetap berlaku).
- **Tes kontrol** (s2, geser +12/+13/+14 cm, tinggi semua kardus diubah): 19 cm 14,2% / 26,7% / 41,3% · 19,5 cm sama persis · 25 cm 14,3% / 27,3% / 42,0% · 40 cm 15,3% / 28,0% / 42,0%. Tinggi hampir tidak memengaruhi P(fall); yang menentukan adalah posisi horizontal titik berat terhadap tepi kardus di bawahnya.
- **Tinggi terukur sudah live** di `drystone-service:9523213` (`boxes.json` di dalam image dicek: 19,6 / 19,5 / 19,4 cm). Hasil identik dengan 19 cm (dicek di atas dan live).

### Halaman web juri (17 Okt malam) — kode + tes
- Function URL yang sama (tidak dibuat ulang, cukup update image): `GET /` halaman (`web/index.html`), `GET /samples/<id>.jpg`, `POST {"sample","offset_cm"}` keputusan, `POST /log` approve/override. POST foto lama (`images`) tidak berubah → `agent.py --aws` tetap jalan. Function URL tidak ditulis di repo; README publik merujuk ke halaman Devpost.
- Acuan geseran: **dari kardus tepat di bawah** (sama dengan `drystone_core.candidate_box`), bulat 1 cm, rentang −16…+16 cm. Tertulis di halaman.
- Halaman: canvas foto + marker + kerangka kardus, P(fall) + zona berwarna, tindakan + usulan, trace bernomor 5 tahap (deteksi marker → kembaran digital → simulasi → keputusan → tindakan) dengan ms per tahap dan tanda cached. KUNING approve / use suggestion / reject; MERAH use suggestion / override / cancel. "Use suggestion" menggeser slider ke usulan lalu menganalisis ulang (loop saran → cek ulang → HIJAU). Override wajib nama + alasan, hanya dicatat (satu baris JSON `web_supervisor_choice` di CloudWatch, tanpa IP), keputusan tidak berubah. Loading "Analyzing… first run can take ~10 s". Disclaimer purwarupa. Tanpa upload foto. Halaman/foto pakai `Cache-Control`.
- **Foto contoh asli (18 Okt 00.30)** menggantikan placeholder: webcam laptop 1280×720, ±1 m, tembok polos, tanpa wajah/kamar/barang pribadi (dicek). Semua marker terbaca; bacaan: s2 ID 1 +0,1 cm, s3 ID 1 **+6,3 cm**; tinggi antar kardus terbaca 20,2–20,3 cm (katalog 19, masalah lama). Kerangka calon −16…+16 cm (dan usulan) masuk seluruhnya ke foto, jarak minimal 112 px ke tepi.
- Adegan (hitungan `drystone_core` dari foto asli, seed 0, 150 simulasi):

  | Contoh | Susunan | Kardus berikutnya | HIJAU | KUNING (usulan) | MERAH (usulan) |
  |---|---|---|---|---|---|
  | s1 | ID 0 saja | ID 1 | +6 cm, 0% | +14 cm, 35% (+10 cm, 3%) | +16 cm, 73% (+10 cm, 3%) |
  | s2 | ID 0 + ID 1 lurus | ID 2 | +6 cm, 0% | **+13 cm**, 27% (+9 cm, 1%) | +16 cm, 69% (+9 cm, 1%) |
  | s3 | ID 0 + ID 1 digeser +6,3 cm | ID 2 | +4 cm, 0% | +12 cm, 25% (+9 cm, 1%) | +16 cm, 77% (+9 cm, 2%) |

  Pindaian dari foto asli: s1 +11 6% / +12 12% / +15 62%; s2 +11 7% / +12 14% / +14 41% / +15 58%; s3 +10 6% / +11 13% / +14 51%. s2 KUNING diganti +14 → **+13 cm** karena 41% terlalu dekat garis 50% (interval ±8%). Geseran dekat garis 10%/50% tidak dipakai sebagai contoh.
- Cache foto: halaman memuat `samples/<id>.jpg?v=<photos_version>` (`photos_version` = 10 hex pertama sha256 foto, dicek tes) dan `samples.json` dikirim `no-cache`, jadi foto yang diganti tidak tampil dari cache browser (foto tetap `max-age` 1 hari). Ditemukan saat cek lokal: tanpa ini, browser yang pernah membuka halaman menampilkan placeholder lama dengan kerangka dari foto asli.
- Tes: `tests/test_web.py` 25 lulus (200, zona semua contoh, loop usulan → HIJAU, cache + pembulatan, 400 override tanpa nama/alasan, tombol sesuai zona, 413 web/foto, 429 GET/POST, POST foto lama + direct invoke tidak berubah). `pytest` hanya di `requirements-dev.txt`, tidak masuk image Lambda.
- Alat: `tools/web_local.py` (server lokal, event Function URL palsu), `tools/capture_sample.py` (foto contoh mentah tanpa anotasi; tolak kalau ada marker hilang di salah satu dari 10 frame; cetak geseran antar kardus dalam cm), `tools/make_placeholder_samples.py` (render sintetis lewat kalibrasi asli; hanya untuk sampel bertanda `placeholder`, foto asli tidak ditimpa).
- **Batasan perlindungan:** reserved concurrency **tidak bisa dipasang** (limit concurrency akun = 10, AWS mewajibkan 10 tetap unreserved; cek 17 Okt). Batas 60 GET + 20 POST per menit per IP dan cache **berlaku per container** (in-memory), jadi dengan banyak container batas efektif bisa lebih tinggi. Biaya dibatasi oleh: cache maksimal 3 × 33 = **99 entri per container** (hasil deterministik), body JSON web ≤ 16 KB, POST foto ≤ 2 MB, dan limit concurrency akun 10. **Koreksi 18 Okt:** akun ternyata Paid plan, jadi biaya di atas kuota gratis ditagih (lihat bagian Biaya AWS).

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
- **Tes dari HP lewat data seluler dengan foto asli (18 Okt, dari screenshot Yasin) — lulus:** foto asli tampil di ketiga contoh tanpa label "placeholder image" · contoh s2 sudah +13 cm (samples.json baru) · s2 +16 cm → RED 69%, usulan +10 cm 3% · "Use suggestion" → +10 cm GREEN 1% · trace 5 tahap tampil · halaman pas di layar HP.

### Deploy perbaikan cek ulang + tinggi terukur (18 Okt)
- **Rollback target** (yang jalan sebelum deploy ini): `drystone-service:f5b647b` (digest `sha256:7f243d8f54b5d621737fa1aead4d96b051f0b9a65c574ab5fb52637ae77236e8`, foto asli, logika cek ulang lama, tinggi 19 cm). Tag `f5b647b` tetap ada di ECR. Rollback (cmd; ganti `<account>`):
  ```
  aws lambda update-function-code --function-name drystone --image-uri <account>.dkr.ecr.ap-southeast-1.amazonaws.com/drystone-service:f5b647b --region ap-southeast-1 --query LastUpdateStatus
  ```
  ```
  aws lambda wait function-updated --function-name drystone --region ap-southeast-1
  ```
  ```
  aws lambda get-function --function-name drystone --region ap-southeast-1 --query "{Uri:Code.ImageUri,Status:Configuration.LastUpdateStatus}"
  ```
- Image baru: `drystone-service:9523213` (+ `:latest`, digest `sha256:04b6f06b…`). Commit dokumen sesudahnya tidak mengubah image (`docs/` tidak masuk build).
- **Live sejak 18 Okt 02.30: `drystone-service:9523213`**, Function URL tetap sama. Berisi perbaikan cek ulang (kardus jatuh = FELL) dan `boxes.json` dengan tinggi terukur (dicek di dalam image).
- Tes live (dari laptop): `GET /` 200 (3,4 dtk), `samples.json` versi foto a7aba3ca6c tanpa placeholder · **9 keputusan contoh identik dengan tabel** (s1 +6 GREEN 0% · +14 YELLOW 35% · +16 RED 73%; s2 +6 GREEN 0% · +13 YELLOW 27% · +16 RED 69%; s3 +4 GREEN 0% · +12 YELLOW 25% · +16 RED 77%; usulan sama) · POST foto lama (s2 +6 cm, box 2) → GREEN GUIDE (3,3 dtk) · `POST /log` → baris `web_supervisor_choice` di CloudWatch · **check lewat Lambda, foto sintetis ID 2 tegak di lantai samping tumpukan (berputar 25°) → FELL, action STOP**, "box ID 2 is on the floor next to the stack -> it fell", stack [0, 1], off_stack ID 2 (floor), tanpa retake (2,4 dtk) · pembanding penempatan sesuai rencana → OK, CONTINUE (+0,1 cm) · 0 baris error di CloudWatch.

### Copy baru situs (19–23 Okt) — `docs/SITE_COPY.md`
- Copy situs dari Yasin disimpan apa adanya di **`docs/SITE_COPY.md`** (sumber utama teks halaman), bagian [ ] diisi dari REPORT/README/`aws/README.md`/respons API tercatat. Diterapkan ke kelima tab; kata zona seragam: **GREEN · place it / YELLOW · ask / RED · move it**, kode aksi (GUIDE / ASK_SUPERVISOR / REJECT) jadi badge kecil.
- **Disesuaikan dengan REPORT/kode** (dicatat di bagian Notes SITE_COPY): 99,800 = "nonfatal cases" (bukan injuries); OVERRIDE hanya untuk RED (YELLOW = approve, nama opsional), alasan 5–300 karakter; RETAKE = marker dasar tak terlihat / marker berubah antar-frame / goyang > 1 cm / miring > 12°, 3 kali lalu tanya orang; pita tengah = margin pusat massa +0,5…+2,5 cm (T16, T17, T01, T25), bukan overhang; tinggi kardus 19,4–19,6 cm; Setup: `git clone` tidak ada di README, log evaluasi mentah tidak dipublikasikan. Kalimat "usually made in a second" di The problem tidak ada sumbernya; 23 Okt diganti "usually made by eye" (sama dengan REPORT §1), lihat bagian di bawah.
- Revisi Yasin setelahnya: kotak definisi "dry·stone wall" dihapus; header: ikon Video + GitHub (tanpa tulisan), tombol hero "View report"; footer tinggal "MIT License"; Setup memakai ikon (globe, laptop, kamera, awan, perisai-centang), bukan angka 01–05; tombol copy jadi ikon (berubah centang setelah menyalin); How it works: lima langkah jadi alur berikon (logo OpenCV dan MuJoCo digambar ulang sebagai SVG, Twin = digital twin, ikon kubus; Decide disorot dengan ikon lampu lalu lintas). Duplikat #1–4 dan #6–8 dihapus (daftar di SITE_COPY).
- `tests/test_web.py`: frasa yang dicek jadi "can take ~10 s" (copy Demo: "The first check can take ~10 s"). 53 tes lulus. Logika keputusan, `samples.json`, format API, setelan evaluasi tidak berubah. Screenshot `docs/img/web_desktop.png` dan `web_mobile.png` diperbarui.
- **Deploy 23 Okt 08.34:** image `drystone-service:b0f4b7f` (+ `:latest`, digest `sha256:52ecb387…baa4`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:3ca4c46`.**
- **Tes live (08.35–08.37):** `GET /` 200, copy baru ada (judul, kata zona place it/ask/move it, teks "can take ~10 s", ikon copy, logo OpenCV dan MuJoCo, ikon GitHub, tombol "View report") · lima tab, kedua diagram 200, `/img/web_desktop.png` → 404 · s1 +16 cm → RED 73% dan s2 +13 cm → YELLOW 27%, sama persis dengan rekaman · s2 +16 cm → RED 69%, usulan +9 cm · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Lembar cetak marker dan papan kalibrasi (23 Okt malam)
- Belum ada generator di repo (`assets/opencv_marker_kalibrasi.pdf` dibuat di luar repo). Baru: **`tools/make_print_sheets.py`** (OpenCV 5, pengaturan dari `tools/common.py`: `BOX_DICT`, `BOX_MARKER_MM`, `make_board`) menulis PDF vektor; tiap sel marker digambar sebagai kotak dalam mm (tanpa raster), `PrintScaling /None`.
- **`docs/print/markers_A4.pdf`** (A4 tegak): ArUco DICT_4X4_50 ID 0, 1, 2, hitam 80 mm, label "ID n · 80 mm", kotak potong 100 mm (tepi putih 10 mm), penggaris 100 mm, "Print at 100% (Actual size). Do not fit to page.", petunjuk tempel + `--marker-mm`.
- **`docs/print/charuco_A4.pdf`** (A4 **landscape**: papan 210 × 150 mm akan menyentuh kedua tepi A4 tegak): ChArUco 7×5, kotak 30 mm, marker 22 mm, DICT_5X5_100, "Mount on a rigid, flat board. Measure a square and pass it as --square-mm.", penggaris 100 mm.
- **Cek skala dari angka di file:** halaman 210 × 297 / 297 × 210 mm; kotak marker 80,000 mm, sel 13,333 mm (80/6); kotak papan 30,000 mm, marker papan 22,000 mm, sel 3,143 mm (22/7).
- **Cek render** (Windows.Data.Pdf, 300 dpi): `cv2.aruco` menemukan ID 0, 1, 2, sisi 79,93 mm (< 1 piksel dari 80); `CharucoDetector` dengan `common.make_board` menemukan 24/24 sudut dan 17/17 marker, kotak 30,006 mm.
- Tab Setup (opsi kamera): link "Download printable markers (PDF)" dan "Download calibration board (PDF)" lewat `LINKS.markers` dan `LINKS.board` (link file GitHub, **diisi Senin**; tersembunyi selama kosong). README bagian setup menunjuk ke kedua PDF. `tests/test_web.py`: jumlah link tersembunyi 4 → 6. 67 tes lulus.
- `.gitattributes`: `*.pdf binary`, supaya Git tidak mengubah akhir baris PDF (offset xref tetap benar di checkout Windows).
- **Deploy 23 Okt 23.40:** image `drystone-service:f465e07` (+ `:latest`, digest `sha256:209d7aca…a0bd`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:37b1380`.** (PDF tidak masuk image; link-nya ke GitHub.)
- **Tes live (23.41):** `GET /` 200, link unduhan markers/board ada di HTML (tersembunyi sampai `LINKS` diisi) · lima tab, kedua diagram 200 · s1 +16 cm → RED 73% dan s2 +13 cm → YELLOW 27%, sama persis dengan rekaman · s2 +16 cm → RED 69%, usulan +9 cm · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Tombol hero "Check a placement" (23 Okt malam)
- Tombol utama hero "Try the demo" → **"Check a placement"** (keputusan Yasin; padanan "Scan a repo" di Subtext, tanpa menjanjikan foto sendiri). Tujuan tetap `#demo`. `docs/SITE_COPY.md` ikut. 67 tes lulus.
- **Deploy 23 Okt 23.06:** image `drystone-service:37b1380` (+ `:latest`, digest `sha256:9423a860…42ea`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:aac07c7`.**
- **Tes live (23.07):** `GET /` 200, tombol "Check a placement" ada · lima tab, kedua diagram 200 · s1 +16 cm → RED 73% dan s2 +13 cm → YELLOW 27%, sama persis dengan rekaman di halaman · s2 +16 cm → RED 69%, usulan +9 cm · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### PNG diagram baru (23 Okt malam)
- Yasin menaruh `architecture.png` dan `agent_loop.png` baru di Downloads (22.12). Dicek: 1920×1080, tanpa metadata, isi sesuai REPORT §4/§6/§8.1 (architecture kini juga menampilkan Function URL (public) dan zero-spend budget alarm, keduanya dari §6), tanpa URL, nomor akun, atau data pribadi.
- Diganti di **`web/img/`** (link "Open as image" dan rute `/img/*.png`) dan **`docs/img/`** (README, REPORT §4/§8.1, galeri Devpost); kedua folder tetap identik (sha256 `582e8bff…` / `7e2efcbb…`). 67 tes lulus.
- **Deploy 23 Okt 22.28:** image `drystone-service:aac07c7` (+ `:latest`, digest `sha256:c2a47932…2501`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:ea42837`.**
- **Tes live (22.29–22.31):** `/img/architecture.png` dan `/img/agent_loop.png` 200 `image/png`, sha256 sama persis dengan file di Downloads · `GET /` 200, HTML identik · s1 +16 → RED 73% usulan +10 · s2 +13 → YELLOW 27% usulan +9 · s2 +16 → RED 69% usulan +9 · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + baris CloudWatch · override tanpa alasan → 400 · 0 baris ERROR. Catatan: rute gambar dikirim dengan cache 1 hari, jadi browser yang pernah membuka gambar lama bisa menampilkannya sampai sehari.

### Diagram hidup di How it works (23 Okt)
- Permintaan Yasin: dua PNG (architecture, agent loop) diganti diagram asli di halaman dengan gaya kartu hero (panel navy, grid tipis, label mono, titik REPLAY, warna zona). Desktop: SVG inline (viewBox 1100) dengan teks asli; HP ≤ 760 px: daftar vertikal (`<ol>`) dengan isi yang sama. Dibuat oleh skrip generator dari satu sumber teks, yang mengisi `docs/SITE_COPY.md` dulu lalu halaman.
- **Isi = REPORT:** architecture = §4 (webcam → OpenCV 5 → twin → MuJoCo 150–600 → aturan + margin 1 cm → supervisor → box placed → check again → kembali ke OpenCV) + §6 (`--aws`: Lambda + Function URL, ECR tag = git commit, CloudWatch Logs, fallback ke laptop); agent loop = §8.1 dengan semua cabang (retake max 3, Wait, Replan, Ask, Reject, Warn, Fell, Ask f/p). Teks di kotak dipersingkat; kalimat lengkap di baris keterangan (tap/hover/Tab, dari tabel §4/§6 dan "agent does / person does" §8.1) dan di daftar HP.
- **Animasi:** architecture = paket data berjalan sepanjang panah dari webcam sampai keputusan dan kembali lewat Check, satu putaran "computed on the laptop" lalu satu putaran `--aws` (Lambda, ECR, CloudWatch menyala: kode yang sama di dua tempat). Agent loop = latihan final 18 Okt ("Alur video final") langkah demi langkah ±19 dtk, angka dari STATUS saja (GREEN 0% 5,0 dtk · OK −0,4 · RED 93% 10,0 dtk · usulan +9 cm 1% · override · FELL · rencana ulang · OK −0,3 · GREEN 1% · decisions 3 · override 1 · fell 1); setelah FELL lewat Wait → Read (bukan Replan, sesuai §8.1). Berhenti saat tab tersembunyi atau diagram di luar layar; reduced motion statis.
- Di bawah tiap diagram link "Open as image" ke `img/architecture.png` / `img/agent_loop.png` (PNG dan rute tidak berubah). Tes baru `test_live_diagrams_link_to_their_images` → **67 tes lulus**; halaman, SITE_COPY, REPORT §7.5, DEVPOST ikut 67.
- Uji lokal + Edge headless (protokol DevTools, juga untuk emulasi reduced motion): desktop 1440 px tanpa teks keluar kotak (huruf terkecil ±10,6 px); HP 390 px tanpa scroll ke samping, huruf ≥ 12 px; klik, hover, dan Tab memunculkan keterangan.
- **Deploy 23 Okt 21.29:** image `drystone-service:ea42837` (+ `:latest`, digest `sha256:cb183be6…5c3c`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:123fb03`.**
- **Tes live (21.30–21.32):** `GET /` 200 (11,0 dtk), HTML identik (sha256) dengan `web/index.html`, kedua diagram ada (24 node SVG), link PNG ke `img/architecture.png` dan `img/agent_loop.png` (keduanya 200 `image/png`), `var REC` identik dengan `123fb03`, "67 tests" · s1 +16 → RED 73% usulan +10 · s2 +13 → YELLOW 27% usulan +9 · s2 +16 → RED 69% usulan +9 · teks batch UX, tombol "Check +X cm", 4/4 link kosong tersembunyi · `/img/web_desktop.png` 404 · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + baris CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Kartu hero: layar kamera Drystone dengan replay (23 Okt)
- Permintaan Yasin: kartu hero dirombak dengan pola kartu hero Subtext (salinan lokal `E:\subtext\web`, `pages/index.tsx` + `styles/Home.module.css`): kartu gaya terminal, garis scan berpendar di atas isi, ritme dengan jeda, isi muncul bertahap, kedip keras `steps(1)`, aksen hemat. Isi, teks, logo, dan warna Subtext tidak dipakai.
- Kartu baru: panel navy gelap seperti layar kamera (sudut viewfinder, grid tipis, label tahap + penghitung, bar keputusan merah penuh saat RED, kotak "Safer spot" biru putus-putus, status bar `RED · P(fall) 73% ±7 · suggest +10 cm · 150 sims`); titik **REPLAY** berkedip (bukan "LIVE", karena ini rekaman; disetujui Yasin).
- Replay `REC` (s1 +16 cm) ±7,9 dtk: scan → bracket marker + "ID 0" → kerangka twin → 150 run berkedip merah/hijau di sekitar +16 cm (±1 cm) dengan tepi kardus bawah, pusat massa, "overhang 55%" dan "margin −1.5 cm", penghitung sampai "fell 110" (= 0,733 × 150 dari `REC`; hanya urutan kedip yang ilustrasi) → P(fall) naik ke 73% → RED → usulan +10 cm. **Diputar sekali saat halaman dimuat dan setiap kali tab Home dibuka, lalu diam di hasil**; yang terus bergerak hanya garis scan tipis dan titik REPLAY (keputusan Yasin setelah melihat versi loop). Berhenti saat tab tidak terlihat atau kartu di luar layar; reduced motion = hasil tanpa gerak (dicek dengan Edge headless `--force-prefers-reduced-motion`). `REC`/`REC2`, tes replay, API, `service.py`, `samples.json` tidak berubah.
- Diperbaiki saat uji lokal: label overlay jadi kotak putih (bentrok kelas `.stage` milik trace) → `ov-stage`/`ov-count`; kardus +16 cm terpotong di atas → layar 880×360 + ruang di atas; di HP "P(fall)" turun baris → huruf lebih kecil di ≤ 520 px. Hero muat satu layar di 1440×900 (kartu berakhir di 658 px); di 390 px tanpa scroll ke samping.
- **Screenshot `docs/img/web_desktop.png` (1440×1040) dan `web_mobile.png` (390×1533) diambil ulang** dengan Edge headless (protokol DevTools) dari server lokal: Demo s1, chip RED +16 → Check → RED 73%, usulan +10; PNG tanpa metadata teks; keterangan REPORT §8 dikembalikan ke slider.
- 66 tes lulus. **Deploy 23 Okt 20.53:** image `drystone-service:123fb03` (+ `:latest`, digest `sha256:50f9c247…a33c`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:65f4559`.** Percobaan pertama berhenti sebelum build karena Docker Desktop mati (live tetap `65f4559`).
- **Tes live (20.54–20.56):** `GET /` 200 (9,7 dtk), HTML identik (sha256) dengan `web/index.html`, kartu baru ada (REPLAY, viewfinder, status bar, `replayProof`), baris `var REC` identik dengan versi `65f4559` · s1 +16 → RED 73% usulan +10 (= REC) · s2 +13 → YELLOW 27% usulan +9 · s2 +16 → RED 69% usulan +9 · teks batch UX, "66 tests", tombol "Check +X cm", 4/4 link kosong tersembunyi · kedua diagram 200, `/img/web_desktop.png` 404 · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + baris CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Slider penempatan + contoh kiri (23 Okt)
- Permintaan Yasin (draft lokal dulu, lalu "aku suka, deploy"): ruler + baris "Or pick any shift" (−/+) diganti **satu slider −16…+16 cm** (jalur biru netral tanpa warna zona; tick tiap 1 cm, angka tiap 4 cm, titik 0 ditebalkan; gelembung nilai di pegangan) + chip contoh dalam dua grup, kiri dan kanan. **Memilih posisi tidak menghitung apa pun** (slider, chip, panah keyboard hanya memindahkan bayangan kardus dan gelembung); cek hanya lewat tombol **"Check +X cm"** atau Enter. Menggeser setelah ada hasil menghapus hasil itu. Subjudul: "cm from the box below: − left, + right". Kartu awal: "Pick a spot with the slider or an example, then press Check." Di HP tombol Check selebar kartu.
- **Contoh kiri (disetujui Yasin setelah melihat tabel)**: zona −1…−16 cm dihitung 23 Okt dengan `service.web_decide` (seed 0). s1: −1…−11 GREEN (0–5,3%), −12…−14 YELLOW (16,7 / 28,7 / 39,0%), −15/−16 RED (65,3 / 78,0%). s2 dan s3 identik satu sama lain (batas kritis = tepi kiri ID 1): −1…−10 GREEN (0–5,3%), −11 YELLOW 9,0% (dekat garis, aturan zona lebih aman), −12…−14 YELLOW (17,3 / 32,0 / 42,3%), −15/−16 RED (60,0 / 74,0%). Dipilih jauh dari garis 10%/50%: **GREEN −6, YELLOW −13, RED −16** di ketiga foto; usulan s1 −10 (2,7%; −11: 7,0%), s2/s3 −9 (1,3%; −10: 2,7%). `web/samples/samples.json` dapat `examples_left` + `suggestion_left_cm` (kolom lama tidak berubah; `service.py` tidak membaca contoh). `tests/test_web.py` memeriksa contoh kiri juga → **66 tes lulus**; halaman, SITE_COPY, REPORT §7.5, DEVPOST ikut 66.
- Dokumen: README (Live demo langkah 2), REPORT (tabel bagian + keterangan screenshot §8), DEVPOST diperbarui ke slider. Screenshot `docs/img` sudah diambil ulang 23 Okt malam (lihat bagian kartu hero di atas).
- Uji browser lokal: drag mouse sungguhan dan chip → 0 request; Check → tepat 1 request (s1 +14 YELLOW 35%); panah + Enter; geser lagi menghapus hasil; HP 390 px tanpa scroll ke samping, target ≥ 44 px; bayangan −13 di kiri kardus bawah.
- **Deploy 23 Okt 15.51:** image `drystone-service:65f4559` (+ `:latest`, digest `sha256:9655c90a…decc1`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:e04e740`.**
- **Tes live (15.52–15.55):** `GET /` 200 (5,6 dtk), HTML identik (sha256) dengan `web/index.html`, tombol "Check +X cm", "66 tests" · `samples.json` live memuat `examples_left` ketiga foto · **s1 −13 → YELLOW 29% usulan −10 · s2 −16 → RED 74% usulan −9** · s1 +16 → RED 73% usulan +10 · s2 +13 → YELLOW 27% usulan +9 · s2 +16 → RED 69% usulan +9 · teks batch UX tetap ada, 4/4 link kosong tersembunyi · kedua diagram 200, `/img/web_desktop.png` 404 · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + baris CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Bayangan kardus sebelum cek (23 Okt)
- Permintaan Yasin (pilihan A): saat geseran dipilih tapi belum dicek (ruler, drag, − / +), foto menampilkan kardus berikutnya di geseran itu sebagai kerangka abu-abu putus-putus + chip di kiri bawah foto "next box +X cm · not checked yet". Tanpa warna zona sampai Check; setelah Check diganti kotak berwarna zona dari service. Tidak ada request selama drag atau −/+.
- Data: 99 kerangka (3 foto × −16…+16 cm, ±11,8 KB) di `var GHOST` di `web/index.html`, dibuat oleh **`tools/ghost_boxes.py`** (baru) dengan bacaan dan proyeksi yang sama dengan `tools/service.py` (`read_stack`, `drystone_core.candidate_box`, `project_box`), tanpa simulasi. `service.py`, API, `samples.json`, logika keputusan tidak berubah. **Kalau foto, kalibrasi, atau katalog kardus berubah: jalankan `python tools/ghost_boxes.py --write`** (tes gagal kalau lupa).
- Tes baru `test_ghost_boxes_match_the_service`: data di halaman = `ghost_boxes.compute()`, 33 geseran per foto, dan sama persis dengan polygon `candidate` dari service (s2 +13, s1 +16) → **57 tes lulus**; REPORT §7.5, DEVPOST, halaman, SITE_COPY ikut 57; README bagian Repository menyebut `ghost_boxes.py`.
- Label kanvas awalnya tertutup chip nama foto di s3 (kardus atas tinggi) → dipindah ke chip HTML di kiri bawah foto.
- Uji browser lokal: desktop s1 +5 dan s2 +11 (bayangan tepat di posisi kotak hijau setelah Check, GREEN 7%); HP s3 drag +8 → +14 (0 request), s3 +12 → YELLOW 25%, bayangan hilang setelah hasil dan kembali setelah −.
- **Deploy 23 Okt 14.47:** image `drystone-service:e04e740` (+ `:latest`, digest `sha256:0579d24f…8ebb`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:4a2676b`.** Percobaan pertama berhenti sebelum build karena Docker Desktop mati (live tetap `4a2676b`).
- **Tes live (14.48–14.50):** `GET /` 200 (6,7 dtk), HTML identik (sha256) dengan `web/index.html`, data bayangan 33/33/33, chip dan `ghost()` ada · teks batch UX tetap ada, 4/4 link kosong tersembunyi, "57 tests" · kedua diagram 200, `/img/web_desktop.png` 404, `samples.json` `no-cache`, `s1.jpg` 200 · s1 +16 → RED 73% usulan +10 · s2 +13 → YELLOW 27% usulan +9 · s2 +16 → RED 69% usulan +9 · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + baris CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Pipeline How it works bergerak seperti situs Subtext (23 Okt)
- Permintaan Yasin: animasi lima langkah How it works dibuat mirip https://subtext-sable.vercel.app/how-it-works. Dari CSS Subtext: langkah muncul naik (0,7 dtk, jeda 0,3 dtk), lingkaran berpendar bergantian (siklus 6 dtk, jeda 1,2 dtk), garis putus-putus berjalan (1,1 dtk), vertikal di layar sempit, diam dengan reduced motion. Diterapkan dengan warna biru Drystone (bukan oranye Subtext); Decide tetap disorot dengan cincinnya sendiri. Hanya CSS + satu baris di `showView`; markup, service, API tidak berubah. Catatan di `docs/SITE_COPY.md` GLOBAL.
- Animasi dipicu saat tab How it works dibuka (langkah yang sama yang menampilkan tab), jadi tidak ada yang disembunyikan sebelumnya dan tidak ada kedipan.
- Uji browser lokal: desktop 1440×900, muncul bergiliran 1→5, pendar berurutan 1→2→3→4→5, garis bergerak; HP 390×844, garis vertikal bergerak, kelima langkah tampil, tanpa scroll ke samping. 56 tes lulus.
- **Deploy 23 Okt 11.39:** image `drystone-service:4a2676b` (+ `:latest`, digest `sha256:f9187aec…7021`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:f031add`.**
- **Tes live (11.40–11.42):** `GET /` 200 (3,8 dtk), HTML identik (sha256) dengan `web/index.html`, keyframes pp-rise/pp-ring/pp-march + pemicu ada, 10 angka `data-count` · teks batch UX tetap ada, 4/4 link kosong tersembunyi · kedua diagram 200, `/img/web_desktop.png` 404, `samples.json` `no-cache`, `s1.jpg` 200 · s1 +16 → RED 73% usulan +10 · s2 +13 → YELLOW 27% usulan +9 · s2 +16 → RED 69% usulan +9 · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + baris CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Angka besar menghitung naik dari 0 (23 Okt)
- Permintaan Yasin: 10 angka besar (The problem 99,800 / 12,100 / 65; ringkasan evidence Home 0/8 · 8/8 · 25/25; Evidence "The agent, under test" 25/25 · 12/12 · 4 · 0) menghitung naik dari 0 sekali, ±1,2 dtk, saat pertama masuk layar. Hanya tampilan (`web/index.html` + catatan di `docs/SITE_COPY.md` GLOBAL); angka, service, API tidak berubah.
- Mulai 80 px sebelum angka masuk layar, sehingga tidak ada kedipan. Angka tertulis tetap tampil sampai hitungan mulai (tidak pernah tertahan di 0; dicek di pane tersembunyi tempat observer/animasi tidak jalan) · bagian setelah garis miring tetap ("/8") · koma tetap · lebar dikunci selama menghitung · pembaca layar membaca angka akhir · reduced motion atau tanpa skrip → angka akhir langsung.
- Uji browser lokal: desktop 1440×900 dan HP 390×844, kesepuluh angka berakhir tepat, label tidak bergeser, tanpa scroll ke samping. 56 tes lulus.
- Bayangan kardus di foto saat menggeser ruler (usulan 23 Okt): sempat ditunda, lalu dikerjakan (lihat bagian di atas).
- **Deploy 23 Okt 11.27:** image `drystone-service:f031add` (+ `:latest`, digest `sha256:fe6f8d13…0e3f`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:3f9eff9`.**
- **Tes live (11.28–11.30):** `GET /` 200 (5,1 dtk), HTML identik (sha256) dengan `web/index.html`, 10 angka `data-count` · teks batch UX tetap ada, 4/4 link kosong tersembunyi · kedua diagram 200, `/img/web_desktop.png` 404, `samples.json` `no-cache`, `s1.jpg` 200 · s1 +16 → RED 73% usulan +10 · s2 +13 → YELLOW 27% usulan +9 · s2 +16 → RED 69% usulan +9 · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + baris CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Batch perbaikan audit UX (23 Okt)
- Audit UX halaman juri (23 Okt pagi, server lokal, 1440×900 dan 390×844) → 15 temuan; #1–#11, #13–#15 diperbaiki dalam satu batch (#12 simpan pilihan di hash dan skip link dilewati). Teks diubah di `docs/SITE_COPY.md` dulu, lalu `web/index.html`. `tools/service.py`, `samples.json`, API, dan logika keputusan tidak berubah.
- Isi: link kosong (`LINKS` "" atau "#") disembunyikan dan muncul sendiri begitu diisi; Setup "Repository link: on the submission page" sampai `LINKS.repo` ada · kartu loading setelah 8 dtk "The server is waking up. The first check can take up to 10 s." (catatan Demo ikut) · Evidence: "Verdict: FAIL on 1 of 5 locked criteria…" di atas tabel; Home: "1 of 5 locked criteria failed (C2b) →" · hero: "For anyone stacking boxes by hand. One webcam, one printed marker per box." · ruler tap atau drag (satu cek saat dilepas, `touch-action: none` hanya di ruler) · round trip diukur di request, "<0.1 s" bukan "0.0 s" · "(+11 cm: 5%)" · Approve/Reject/Override/Cancel terkunci setelah pilihan tercatat · error override per kolom, `role="alert"` · fokus ke H1 tab baru · label copy unik · target sentuh ≥ 44 px · catatan Windows cmd + macOS/Linux di Setup dan README · "LAYAK (passes)".
- "Round trip 0.0 s" dengan "not cached" dari audit tidak bisa direproduksi; 0.0 hanya muncul untuk jawaban cache di server lokal (< 50 ms).
- **Cold start (idle, bukan tepat setelah deploy):** ronde 1 (idle 47 menit, 10.23) GET / 4,2 dtk, POST s2 +13 9,9 dtk · ronde 2 (idle 22 menit, 10.46) GET / 2,5 dtk, POST s2 +13 9,3 dtk. Terburuk 9,9 dtk → **N = 10 dtk**. Tepat setelah deploy GET / 17,3–17,8 dtk (container baru).
- Tes: 3 tes baru (link tersembunyi di HTML; blok `applyLinks` dijalankan di Node dengan LINKS "#" dan terisi) → **56 tes lulus**; REPORT §7.5, DEVPOST, halaman ikut 56. Uji browser lokal (desktop + HP): hero muat satu layar, link kosong tersembunyi, pesan bangun muncul di 9 dtk (tidak di 3 dtk), drag = 0 request selama bergerak + 1 saat dilepas, round trip use suggestion 1,3 dtk, tombol pilihan terkunci, tanpa target < 44 px dan tanpa scroll ke samping di 390 px.
- **Deploy 23 Okt 10.51:** image `drystone-service:3f9eff9` (+ `:latest`, digest `sha256:069e607b…1490`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:b1f13a7`.** Percobaan pertama 10.49 gagal karena Docker Desktop mati (update ditolak, live tetap `b1f13a7`).
- **Tes live (10.52–10.54):** `GET /` 200 (17,3 dtk, tepat setelah deploy), HTML identik (sha256) dengan `web/index.html` · baris hero, kalimat Verdict, link C2b di Home, teks "waking up" + ambang 8 dtk, catatan Demo "up to 10 s", "Tap or drag", "56 tests" ada · 4/4 link `data-link` tersembunyi (LINKS masih kosong) · kedua diagram 200, `/img/web_desktop.png` 404, `samples.json` `no-cache`, `s1.jpg` 200 · s1 +16 → RED 73% usulan +10 · s2 +13 → YELLOW 27% usulan +9 · s2 +16 → RED 69% usulan +9 · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + baris CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### The problem tanpa "in a second" (23 Okt)
- Home > The problem, di `docs/SITE_COPY.md` dan `web/index.html`: "that call is usually made in a second, by eye, with the next box already in hand" → **"that call is usually made by eye, with the next box already in hand"**. "In a second" tidak punya sumber; REPORT §1 memakai "by eye". Hanya teks; 53 tes lulus.
- **Deploy 23 Okt 09.32:** image `drystone-service:b1f13a7` (+ `:latest`, digest `sha256:6b9865f1…1ce4`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:b0f4b7f`.** `main` dan `web-judges` di-push ke `b1f13a7`.
- **Tes live (09.33–09.36):** `GET /` 200 (cold start 17,8 dtk), kalimat baru ada dan "in a second" hilang, kata zona place it/ask/move it, "can take ~10 s", "View report", lima tab · kedua diagram 200 `image/png`, `/img/web_desktop.png` → 404 · `samples/samples.json` 200 `no-cache`, `samples/s1.jpg` 200 · s1 +16 cm → RED 73%, usulan +10 · s2 +13 cm → YELLOW 27%, usulan +9 · s2 +16 cm → RED 69%, usulan +9 · `aws/test_endpoint.py` s2 +6 cm → GREEN GUIDE · `/log` cancel → 200 + satu baris `web_supervisor_choice` di CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Favicon Drystone (19 Okt malam)
- Tab browser sekarang menampilkan logo Drystone (tiga balok biru bertumpuk, yang atas bergeser ke kanan, di kotak navy), sebagai SVG data-URI di `<head>` `web/index.html`, plus `theme-color` #13294B. Tanpa file baru dan tanpa perubahan `service.py`. 53 tes lulus.
- **Deploy 19 Okt 22.19:** image `drystone-service:3ca4c46` (+ `:latest`, digest `sha256:7a03bbf7…a301`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:c8da45b`.**
- **Tes live (22.20):** `GET /` 200, favicon ada · lima tab, kedua diagram 200 · s1 +16 cm → RED 73% dan s2 +13 cm → YELLOW 27%, sama dengan rekaman · s2 +16 cm → RED 69% · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Halaman juri jadi lima tab (19 Okt malam)
- `web/index.html` sekarang situs bertab seperti Subtext, tetap satu file dengan routing hash: **Home** (`#home`: hero + kartu "real check", The problem, evidence ringkas 0/8 · 8/8 · 25/25 · 4/9, "The rules are the gate, not the model." dengan kartu OpenCV 5 / MuJoCo / AWS Lambda+ECR+CloudWatch / budget alarm dan baris "53 tests · 25 locked trials · every decision logged"), **How it works** (`#how`: 5 checkpoint, "RED is not the end" dengan trace asli 18 Okt dan alur FELL → pick up → re-plan, tombol "What you see / What the camera reads" untuk s2 +13 cm, tabel aturan keputusan, diagram), **Demo** (`#demo`: Try it + How it decided, fungsi tidak berubah), **Evidence** (`#evidence`: C1–C4 dengan C2b FAIL, per zona, kasus gagal, Limits & responsible use, link REPORT lewat `LINKS`), **Setup** (`#setup`: 4 tingkat dengan tombol Copy; tingkat 3 jujur butuh kardus, marker cetak 80 mm DICT_4X4_50 dan webcam). Angka dan perintah dari REPORT/README/`aws/README.md`. Menu aktif bergaris bawah biru; di HP menu satu baris di bawah logo.
- **`tools/service.py` diubah sedikit (disetujui Yasin):** rute `GET /img/<nama>.png` untuk dua diagram saja (`WEB_IMAGES` = `architecture`, `agent_loop`), file disalin ke `web/img/` (±0,47 MB), cache sehari. API keputusan, `samples.json`, foto tidak berubah.
- Rekaman kedua `REC2` (s2 +13 cm, YELLOW 27%, usulan +9 cm) untuk tampilan kamera; tes `test_hero_replay_matches_service` sekarang memeriksa REC dan REC2. Tes baru `test_diagram_images_200_and_unknown_404`. **53 tes lulus** (REPORT §7.5 dan DEVPOST ikut 53). REPORT §6 tidak lagi menulis tag live (lihat STATUS). Screenshot `docs/img/web_desktop.png` dan `web_mobile.png` dari tab Demo.
- **Deploy 19 Okt 21.34:** image `drystone-service:c8da45b` (+ `:latest`, digest `sha256:a81560a0…d33a`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:64d6249`.** (Percobaan pertama 21.32 gagal karena Docker Desktop mati; update Lambda ditolak karena image belum ada, versi live tetap `64d6249` sampai deploy ini.)
- **Tes live (21.35):** `GET /` 200 (3,9 dtk), lima tab ada · `GET /img/architecture.png` dan `/img/agent_loop.png` 200 `image/png`, `/img/web_desktop.png` → 404 · s1 +16 cm → RED 73% dan s2 +13 cm → YELLOW 27%, keduanya sama persis dengan rekaman di halaman · s2 +16 cm → RED 69%, usulan +9 cm · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### "The problem" lebih ramping (19 Okt sore)
- Proporsi mengikuti Subtext: judul 28–44 px, angka 44–68 px satu baris, keterangan langsung di bawah angka, sumber satu baris; seluruh bagian 555 px (muat di layar 1366×630). Kolom ketiga "Stable and secure" diganti angka **>7 ft**: tumpukan kardus lebih dari 7 kaki roboh di toko dan menjepit pekerja (Oregon OSHA, Nov 2025; REPORT §1 [3]). Sumber: BLS + Oregon OSHA, dengan catatan "BLS counts all objects and equipment, not only falling stacks". 52 tes lulus.
- **Deploy 19 Okt 17.29:** image `drystone-service:64d6249` (+ `:latest`, digest `sha256:d2fa0467…7b63`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:1a261ca`.**
- **Tes live (17.30):** `GET /` 200 (3,8 dtk), angka ">7 ft" tampil · s1 +16 cm → RED 73%, sama persis dengan rekaman kartu hero · s2 +16 cm → RED 69%, usulan +9 cm · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Hero muat satu layar (19 Okt sore)
- Seperti Subtext: hero setinggi layar (`min-height: 100svh` di atas 860 px), judul sedikit lebih kecil, tombol "Try the demo" + "How it decides". Kartu "real check" dipadatkan dari ±600 px menjadi 442 px: foto dipotong ke area tumpukan (880×320, dihitung dari marker dan kerangka di rekaman), baris "Rule" dihapus (sudah terwakili label REJECT). Cek: kartu utuh terlihat tanpa scroll di 1366×630, 1280×720, 1440×900, 1024×700; tanpa scroll horizontal di 390 px. 52 tes lulus.
- **Deploy 19 Okt 17.16:** image `drystone-service:1a261ca` (+ `:latest`, digest `sha256:29bb5f24…dde7`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:6cc42b1`.**
- **Tes live (17.17):** `GET /` 200 (3,5 dtk), tombol hero ada · s1 +16 cm → RED 73%, sama persis dengan rekaman kartu hero · s2 +16 cm → RED 69%, usulan +9 cm · `aws/test_endpoint.py` → GREEN GUIDE · `/log` → 200 + CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Tata letak hero + bagian "The problem" (19 Okt sore)
- Hero jadi grid dua kolom (teks kiri, kartu "real check" kanan, maks 440 px); judul sedikit lebih kecil; pita biru menimpa kartu "Try it" lebih sedikit (`--overlap` 96–160 px); "Try it" jadi grid dua kolom sampai 861 px (di 1024 px kartu tidak turun ke bawah).
- Kalimat "Why it matters" diganti bagian **"The problem"** (gaya Subtext): judul "Every stack is a judgement call, made by eye.", satu paragraf masalah, tiga angka bersumber dari REPORT §1 — **12,100** dari 99,800 cedera (BLS 2020, "struck by object or equipment"), **65** kematian "contact with objects and equipment" (62–75/tahun 2016–2020), dan kutipan OSHA 1910.176(b) **"stable and secure"** — plus catatan batasan (kategori BLS lebih luas dari tumpukan roboh) dan link sumber BLS + OSHA.
- Kartu awal "Try it" sekarang menawarkan contoh YELLOW (alur supervisor), karena kartu hero sudah menunjukkan RED.
- 52 tes lulus. Screenshot `docs/img/web_desktop.png` dan `web_mobile.png` diperbarui.
- **Deploy 19 Okt 17.06:** image `drystone-service:6cc42b1` (+ `:latest`, digest `sha256:227da379…799c`), Lambda `Successful`/`Active`. **Rollback target: `drystone-service:9a67671`.**
- **Tes live (17.07):** `GET /` 200 (3,7 dtk), bagian "The problem" dan kartu hero ada · s1 +16 cm → RED 73%, sama persis dengan rekaman kartu hero · s2 +16 cm → RED 69%, usulan +9 cm · `aws/test_endpoint.py` s2 +6 cm → GREEN GUIDE · `/log` → 200 + CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Kartu hero "real check" (19 Okt sore)
- Di kanan hero ada kartu yang memutar ulang **satu keputusan asli**: s1, kardus berikutnya +16 cm → RED 73% (± 7%, 150 simulasi), usulan +10 cm 3% GREEN. Data direkam dari `tools/service.py` (seed 0, kode dan jawaban sama dengan Lambda) dan disimpan di `web/index.html` (`REC`, ±0,8 KB); foto diambil dari `samples/s1.jpg`. Animasi ±3 dtk sekali jalan (marker → kerangka → kardus berikutnya + P(fall) naik → RED → usulan); *reduced motion* langsung hasil akhir. "Run it yourself →" menjalankan cek yang sama secara live. Label: "real check", "Replay of a real check".
- Tes baru `test_hero_replay_matches_service`: rekaman harus sama dengan jawaban service (zona, P, CI, n, usulan, marker, poligon). **52 tes lulus** (README/REPORT/DEVPOST ikut diperbarui).
- Foto "diperjelas" dari ChatGPT (gpt-image, C2PA `trainedAlgorithmicMedia`, 1672×941, marker s2/s3 bergeser 28–36 px) **tidak dipakai**: foto sampel tetap foto webcam asli. File AI dipindah ke luar repo (`Downloads\drystone_ai_photos`).
- Screenshot `docs/img/web_desktop.png` dan `web_mobile.png` diperbarui.
- **Deploy 19 Okt 16.45:** image `drystone-service:9a67671` (+ `:latest`, digest `sha256:7d48cf7b…9057`), Lambda `Successful`/`Active`, Function URL tetap. **Rollback target: `drystone-service:368b0d5`** (perintah rollback seperti di bagian deploy 18 Okt, dengan tag `368b0d5`).
- **Tes live (16.46):** `GET /` 200 (4,5 dtk), kartu hero ada · `samples.json` 200 `no-cache` · **s1 +16 cm (cek kartu hero) → RED 73%, usulan +10 cm; jawaban Lambda sama persis dengan rekaman di halaman** (5,8 dtk) · s2 +16 cm → RED 69%, usulan +9 cm (9,1 dtk) · `aws/test_endpoint.py` s2 +6 cm → GREEN GUIDE (4,2 dtk) · `POST /log` cancel → 200, baris `web_supervisor_choice` di CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Header tipis (19 Okt sore)
- Header jadi bar tipis selebar layar (tinggi 56 px, seperti contoh Atlas): logo dan nama lebih kecil, tautan "GitHub repo" jadi ikon GitHub (target 44 px, `aria-label` "GitHub repository", tetap memakai `LINKS.repo`). Hanya tampilan; 51 tes lulus. `docs/img/web_desktop.png` dan `web_mobile.png` diperbarui.
- **Deploy 19 Okt 16.01:** image `drystone-service:368b0d5` (+ `:latest`, digest `sha256:d784ed9e…fe48`), Lambda `Successful`/`Active`, Function URL tetap. **Rollback target: `drystone-service:e622387`** (perintah rollback seperti di bagian deploy 18 Okt, dengan tag `e622387`).
- **Tes live (16.02):** `GET /` 200 (3,8 dtk), header baru dengan ikon GitHub · `samples.json` 200 `no-cache` · **s2 +16 cm → RED 69%, REJECT, usulan +9 cm (1%; +10 cm 2,7%)**, 9,2 dtk · `aws/test_endpoint.py` s2 +6 cm → GREEN GUIDE (4,2 dtk) · `POST /log` cancel → 200, baris `web_supervisor_choice` di CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Halaman juri: perbaikan Impeccable + DEVPOST Humanizer (19 Okt sore)
- Skill lokal **Impeccable** (`.claude/`, tidak di-commit) dijalankan pada `web/index.html`: `audit`, `critique` (dua penilaian terpisah, skor 31/40; detektor 7 temuan, 5 positif palsu), lalu `typeset`, `layout`, `bolder`, `delight`, `polish`. **Hanya tampilan**; API, `service.py`, `samples.json`, dan aturan keputusan tidak berubah. Warna, font, dan susunan mockup Blueprint tetap.
- Perubahan: label zona di penggaris 9 → 11 px; judul foto tidak terpotong; label "EVIDENCE" dihapus; lebar baca ±70 karakter; kartu keputusan menempel (sticky) di desktop; stepper jadi "Fine-tune" + tombol "Check +X cm"; **batang waktu per tahap** di "How it decided"; keterangan Action menyebut pencarian posisi aman; "± 7% (95% CI, n runs)"; kartu awal menawarkan contoh RED ("Check +16 cm"); penghitung detik saat loading; pin penggaris berwarna zona setelah hasil; hover/disabled; disclaimer juga di form override; kartu tahap sebelum hasil tidak memudar (kontras); `aria-live` satu baris; tombol Trace 44 px; tahap 0 ms = "<1 ms".
- Skill global **Humanizer** dijalankan pada `docs/DEVPOST.md`: label hiasan dan pengulangan dibuang, kalimat dipecah; angka dicek dengan skrip (tidak ada angka baru; yang hilang hanya duplikat), batasan klaim tetap.
- Screenshot `docs/img/web_desktop.png` dan `web_mobile.png` diperbarui. 51 tes lulus.
- **Deploy 19 Okt 15.43:** image `drystone-service:e622387` (+ `:latest`, digest `sha256:6c03b8c9…44be`), Lambda `Successful`/`Active`, Function URL tetap. **Rollback target: `drystone-service:7a08913`** (perintah rollback seperti di bagian deploy 18 Okt, dengan tag `7a08913`). ECR saat deploy: `e622387`/`latest`, `7a08913`, `3b023a4`, `9523213`; lifecycle policy menyisakan 2 image bertag terbaru.
- **Tes live (15.44):** `GET /` 200 (3,8 dtk), halaman versi Impeccable ("Fine-tune", batang waktu) · `samples.json` 200 `no-cache` · **s2 +16 cm → RED 69%, REJECT, usulan +9 cm (1%; +10 cm 2,7%)**, 9,1 dtk, sama seperti sebelumnya · `aws/test_endpoint.py` s2 +6 cm → GREEN GUIDE (4,3 dtk) · `POST /log` cancel → 200, baris `web_supervisor_choice` di CloudWatch · override tanpa alasan → 400 · 0 baris ERROR.

### Halaman juri: desain Blueprint (19 Okt) — live `7a08913` (digantikan versi Impeccable)
- `web/index.html` ditulis ulang dengan desain "TURN 4 · Blueprint · rhythm fix" dari Claude Design; **hanya tampilan**. `tools/service.py`, `tools/*.py`, `samples.json`, foto, format API, dan setelan evaluasi tidak berubah. Mockup disimpan sebagai referensi di `docs/design/judge_mockup.html` (tidak di-deploy; runtime `support.js` dari Claude Design tidak di-commit).
- Slider diganti **penggaris penempatan**: penanda dari `samples.json` per foto (contoh GREEN/YELLOW/RED + usulan: s1 +10, s2/s3 +9), tap di mana saja di penggaris = geseran cm terdekat 0…+16, tombol −/+ dan **Check** untuk −16…+16. P(fall), tindakan, usulan, dan trace dari respons API asli; nama tahap dari trace; tahap 0 ms ditampilkan "<1 ms".
- KUNING: Approve / Reject (+ nama opsional), "Check +X cm" = use_suggestion. MERAH: Override… (nama 2–60, alasan ≥ 5, dicek di halaman dan server) / Cancel. Isi request `/log` sama seperti sebelumnya.
- Loading "Running Monte Carlo on AWS Lambda…" (tombol terkunci; teks tetap memuat "first run can take ~10 s" untuk tes), pesan ramah untuk timeout 30 dtk, 429, dan jaringan putus, dengan tombol Try again. HP: auto-scroll ke keputusan setelah tap penggaris, tanpa scroll horizontal (dicek 390 px), tombol ≥ 44 px. Baris "Why it matters" dengan angka BLS dari REPORT §1 + link sumber.
- Link repo/video/laporan: konstanta `LINKS` di awal skrip `web/index.html` (kosong = `#`). **Isi sebelum submit.**
- Foto beranotasi `docs/img/annotated_s2.png` (canvas halaman, s2 +13 cm YELLOW, 1280×720) dipasang di REPORT §5 dengan arti tiap garis; dicek: tanpa wajah, barang pribadi, URL, atau nomor akun.
- Screenshot: `docs/img/web_desktop.png` (1440 px) dan `docs/img/web_mobile.png` (390 px), dipasang di REPORT §8; hanya kardus, tanpa orang, metadata PNG kosong. 51 tes lulus. `.claude/` (skill Impeccable lokal) masuk `.gitignore`.
- **Deploy 19 Okt 14.58:** image `drystone-service:7a08913` (+ `:latest`, digest `sha256:deba90cc…2815`), Lambda `Successful`/`Active`, Function URL tetap sama. **Rollback target: `drystone-service:3b023a4`** (versi sebelumnya; perintah rollback seperti di bagian deploy 18 Okt di bawah, dengan tag `3b023a4`). Di ECR sekarang ada `7a08913`/`latest`, `3b023a4`, dan `9523213`; lifecycle policy akan menghapus `9523213` (bertag ketiga).
- **Tes live (19 Okt 14.59, dari laptop):** `GET /` 200 (3,7 dtk), halaman baru (judul, penggaris, disclaimer, teks "first run can take ~10 s") · `samples.json` 200 `no-cache` · **s2 +16 cm → RED 69%, REJECT, usulan +9 cm (1%, +10 cm 2,7%)**, 150 simulasi, 9,0 dtk, sama dengan deploy 18 Okt · `aws/test_endpoint.py` foto s2 +6 cm → GREEN GUIDE (4,1 dtk) · `POST /log` cancel → 200 dan baris `web_supervisor_choice` masuk CloudWatch · override tanpa alasan → 400 · 0 baris ERROR di log 10 menit terakhir.

### Deploy margin usulan (18 Okt)
- **Rollback target** (yang jalan sebelum deploy ini): `drystone-service:9523213` (digest `sha256:04b6f06b7b7cb01414c4b630e425589a6ddab4f734e7eb9e409465ece71953cf`, usulan tanpa margin). Tag `9523213` tetap ada di ECR. Rollback (cmd; ganti `<account>`):
  ```
  aws lambda update-function-code --function-name drystone --image-uri <account>.dkr.ecr.ap-southeast-1.amazonaws.com/drystone-service:9523213 --region ap-southeast-1 --query LastUpdateStatus
  ```
  ```
  aws lambda wait function-updated --function-name drystone --region ap-southeast-1
  ```
  ```
  aws lambda get-function --function-name drystone --region ap-southeast-1 --query "{Uri:Code.ImageUri,Status:Configuration.LastUpdateStatus}"
  ```

- Image baru: `drystone-service:3b023a4` (+ `:latest`, digest `sha256:4ec67926…`).
- **Live sejak 18 Okt 13.30: `drystone-service:3b023a4`**, Function URL tetap sama. Detektor marker tetap setelan lama.
- Tes live (dari laptop): `GET /` 200 (3,2 dtk) · 9 keputusan contoh: zona identik dengan tabel, usulan sesuai `suggestion_cm` (s1 +10 cm 3%, 1 cm lebih jauh 5% · s2 +9 cm 1%, +10 cm 2,7% · s3 +9 cm 1–2%, +10 cm 6,2–6,7%) · **s2 +16 cm → RED 69%, usulan +9 cm** (8,7 dtk) · POST foto lama (s2 +6 cm, box 2) → GREEN GUIDE (3,4 dtk) · `POST /log` → baris di CloudWatch · check lewat Lambda, ID 2 tegak di lantai samping tumpukan → FELL, STOP, tanpa retake (2,3 dtk); pembanding sesuai rencana → OK · 0 baris error.

### Evaluasi percobaan baru — HASIL (18 Okt 15.26–15.53): FAIL di C2b
- Semua 25 percobaan dalam satu sesi (log `data/agent_20261018_152640/log.jsonl`, `agent.py --aws`), 26 menit (median ±56 dtk per percobaan, jauh lebih cepat dari perkiraan 75–80 menit). Log 15.23 (0 keputusan) diabaikan. Koreksi administratif di protokol: sesi 2 tidak dipakai. Integritas: sha256 daftar percobaan tetap `e69deb9d…e114`, tidak ada diff di `tools/`, `tests/`, `config/` sejak `8a953e4`; agent mencatat sha yang sama di `eval_start`.
- Laporan: `python tools/eval_report.py --logs data/agent_20261018_152640/log.jsonl` → `data/eval_report/trials.csv`, `summary.md` (di-commit, tanpa foto dan nama).
- **C1** 0 roboh di 8 percobaan GREEN → LULUS · **C2a** 14/14 (100%) percobaan jelas → LULUS · **C2b** 12 roboh; Σp = 8,537, sd 1,772, interval 90% 5,623–11,451 → 6–11 → **GAGAL** (z = 1,96; model terkalibrasi dengan P ini hanya 4,7% kemungkinan ≥ 12 roboh) · **C3** Brier 0,1254 → LULUS · **C4** 25/25 → LULUS. **Vonis: FAIL** menurut kriteria yang dikunci. Setelan, kriteria, dan kode tidak diubah.
- Akurasi keseluruhan (bukan kriteria) 84% (21/25), Tes 2 82%. Per zona: GREEN 0/8 roboh (P rata-rata 3%), YELLOW 4/9 (P rata-rata 25%), RED 8/8 (P rata-rata 75%). Kalibrasi: 0–10% → 0/9 · 10–30% → 40% (P 20%) · 30–50% → 67% (P 39%) · 50–70% → 100% (P 60%) · 70–90% → 100% (P 80%) · 90–100% → 100% (P 92%).
- Operasional: galat penempatan kardus yang berdiri rata-rata 0,6 cm, median 0,6, maks 1,7 cm (T06, OFF_PLAN, tetap berdiri), 10/13 ≤ 1 cm · Lambda median 7,6 dtk, maks 11,1 dtk, 25/25 di AWS · retake 0, f/p 0, fallback 0, koreksi pekerja 0 · persiapan ditolak 4× (T03: ID 1 di +10 cm bukan +5, 2×; T09: ID 1 belum ditaruh, 2×).
- **Kasus gagal** (semua KUNING yang roboh): T16 (3 kardus, +12, margin +2,5 cm, P 14%), T17 (3 kardus, −12, +2,5 cm, 17%), T01 (2 kardus, +14, +0,5 cm, 35%), T25 (3 kardus, +14, +0,5 cm, 43%). MERAH dekat garis (T18 62%, T20 58%, T21 60%) semuanya roboh.
- **Pola menurut margin statis pusat massa:** ≤ −0,5 cm → 8/8 roboh (semua RED) · ≥ +3,5 cm → 9/9 berdiri · **+0,5…+2,5 cm → 4/8 roboh, P 12–43%**: model terlalu optimis di pita tengah, GREEN tetap aman. Di pita itu 3 kardus 3/4 roboh, 2 kardus 1/4 (sampel kecil).
- **Metrik tugas agent (evaluasi):** cek ulang cocok dengan hasil yang dikonfirmasi pekerja di **25/25** percobaan (0 koreksi); roboh terdeteksi sebagai FELL **12/12** (semuanya "on the floor next to the stack"), di latihan 7/7.
- **Baseline cek statis** (prediksi roboh kalau margin pusat massa < 0) di 25 percobaan yang sama: akurasi **21/25 (84%)**, sama dengan Monte Carlo; Brier **0,160** (ramalan 0/1) vs **0,125** Monte Carlo. Nilai tambah simulasi: probabilitas bertingkat + ketidakpastian (dipakai untuk GUIDE/ASK/REJECT dan usulan dengan margin), bukan akurasi.
- Hipotesis (bukan kesimpulan): gesekan simulasi tidak cocok, ketidakpastian isi/pusat massa terlalu kecil, lantai licin/kardus dasar goyang, cara melepas kardus (terutama dari 40 cm), kardus lentur.
- **Post-hoc, tidak dipakai sistem, tidak di-deploy** (tabel lengkap di `docs/REPORT.md` §7.4, direproduksi dengan `python tools/posthoc_sim_settings.py --log data/agent_20261018_152640/log.jsonl`): P dihitung ulang di 25 tumpukan yang tercatat (setelan terkunci mereproduksi P di log persis). 9 setelan (posisi 1–2 cm, isi 2–4 cm, gesekan 0,3–0,8): Brier 0,121–0,132, tidak ada yang jelas lebih baik; ketidakpastian lebih besar menaikkan Σp (sampai 10,4) tapi log-likelihood memburuk; **gesekan 0,3 malah menurunkan Σp (8,48)**, jadi hipotesis "gesekan terlalu tinggi" tidak didukung. Semua setelan tetap 0 roboh di GREEN. Kesimpulan sementara: celahnya struktural, bukan parameter. Pekerjaan lanjutan: percobaan khusus di pita margin +0,5…+2,5 cm (2 vs 3 kardus), ukur gesekan dengan tes miring, modelkan gangguan saat melepas, kunci setelan baru, uji lagi di percobaan baru.

### Evaluasi percobaan baru — protokol DIKUNCI (18 Okt)
- Protokol `docs/EVAL_PROTOCOL.md` (bahasa Inggris), dikunci di commit **`8a953e4`** sebelum data diambil. Koreksi tercatat sesudah kunci (18 Okt): tanggal di judul 21–22 → 20–21 Okt, administratif saja. Daftar percobaan `config/eval_plan.json` (dari `tools/make_eval_plan.py`, seed 20261021), sha256 `e69deb9dc325212b3ccd455f3266a83af389b7951fd8d6a412bbb8b27993e114` (file dijaga LF lewat `.gitattributes`; agent mencatat sha256 ini di log `eval_start`).
- Setelan dikunci: posisi 1 cm, isi 2 cm, ambang 10%/50%, margin usulan A, detektor lama, katalog terukur, Lambda `3b023a4`.
- 25 percobaan acak: 10 × 2 kardus, 15 × 3 kardus, 15 geseran positif dan 10 negatif; rencana 8 GREEN, 9 YELLOW, 8 RED; 11 sengaja dekat garis zona; perkiraan total roboh 8,6.
- Kriteria lulus (peluang lulus model yang terkalibrasi, dari P rencana): **C1** 0 roboh di GREEN (78%; peluang ≥1 roboh di GREEN tetap ±22%) · **C2a** akurasi ≥ 85% pada percobaan jelas, P < 10% atau > 70% (92%; 14 percobaan) · **C2b** jumlah roboh di interval 90% Σp ± 1,645·√Σp(1−p) (91%; rencana 6–11 roboh) · **C3** Brier ≤ 0,20 (97%; Brier diharapkan 0,125) · **C4** ≥ 20 dari 25 percobaan. Semua sekaligus: **±70% untuk model terkalibrasi** (simulasi 200.000 kali); penyumbang gagal terbesar adalah **C1**: peluang ≥1 roboh di GREEN ±22% walau modelnya terkalibrasi, karena 8 percobaan GREEN dengan P 0–8%. Laporan nanti harus menjelaskan ini kalau C1 gagal oleh satu roboh di dekat garis 10%. Akurasi keseluruhan (P ≥ 50%) dilaporkan untuk dibandingkan dengan Tes 2 (82%), bukan kriteria: model sempurna pun diharapkan ±82% dan gagal target 80% ±27%.
- Alat: `agent.py --eval-plan config/eval_plan.json --supervisor Yasin --aws %DRYSTONE_URL%` (lanjut sesi: `--eval-start 13`); laporan `python tools/eval_report.py --logs "data/agent_*/log.jsonl"` → `data/eval_report/trials.csv` + `summary.md`. Tes kamera palsu `tests/test_eval.py`; 51 tes lulus.
- **Jadwal (koreksi administratif 18 Okt, tercatat di protokol): sesi 1 T01–T12 dimajukan ke Sabtu 18 Okt siang (cahaya terang); sesi 2 T13–T25 tetap Rabu 21 Okt** (`--eval-start 13`). Daftar percobaan, sha256, setelan, dan kriteria tidak berubah. Perkiraan ±1,2 menit per percobaan 2 kardus, ±1,7 menit per percobaan 3 kardus → ±40 menit murni, 75–80 menit dengan persiapan dan cadangan (Selasa ±40 menit, Rabu ±45 menit).
- Persiapan tiap sesi: lampu terang (Selasa malam!), kedua sisi tumpukan kosong ±30 cm (geseran negatif jatuh ke kiri), laptop di depan tumpukan.

### Biaya AWS (koreksi 18 Okt)
- `aws freetier get-account-plan-state`: **PAID, ACTIVE, kredit 0**; tagihan Oktober USD 0,00. Turun ke Free plan tidak bisa. Klaim "Free plan" sebagai pengaman biaya dihapus dari CLAUDE.md, README, aws/README, STATUS, HANDOFF.
- Aturan: tetap dalam kuota gratis (Lambda 1 juta request + 400.000 GB-detik per bulan, CloudWatch Logs 5 GB), tanpa Marketplace, budget `zero-spend-opencv` (USD 1, notifikasi biaya aktual > 0,01, email) sudah ada.
- Akun tidak tutup sendiri → endpoint aman sampai 10 Nov. Biaya di atas kuota ditagih.
- Batas terburuk: 10 eksekusi bersamaan (limit akun) × 2 GB × 3.600 dtk = 72.000 GB-detik per jam ≈ **USD 1,20 per jam** (harga daftar Lambda x86 ap-southeast-1, USD 0,0000166667/GB-detik; ±USD 29 per hari); kuota gratis bulanan cukup untuk ±5,5 jam beban terburuk. Halaman juri hampir gratis karena cache maks 99 entri per container; beban terburuk hanya lewat POST foto baru (≤ 2 MB, 20 per menit per IP per container). Request: USD 0,20 per juta, tidak berarti.
- **Lifecycle policy ECR diterapkan (18 Okt)**, `aws/ecr-lifecycle.json`: image tanpa tag dihapus setelah 14 hari; hanya **2 image bertag terbaru** yang disimpan. Preview sebelum diterapkan: yang kedaluwarsa hanya `7e9f416` dan `f5b647b`; tetap ada `3b023a4`/`latest` (live) dan `9523213`. Akibatnya **target rollback selalu tepat satu versi sebelumnya** (deploy baru menghapus versi bertag ketiga). Rollback lama di bagian deploy di atas (`7e9f416`, `f5b647b`, dan digest tanpa tag `9afba661…`, kedaluwarsa ±31 Okt) tidak bisa dipakai lagi.

## Wajib sebelum submit
- Tidak ada item terpisah lagi; semua sisa pekerjaan ada di rencana 23–26 Okt di bawah.

## Berikutnya
- **18 Okt:** ~~latihan adegan override → roboh~~ (selesai: alur video final teruji dengan kardus asli, 13.41) · ~~alur jatuh → angkat → keputusan ulang → s → OK~~ · ~~margin usulan~~ (aturan A) · ~~setelan deteksi marker~~ (ditolak) · opsional: uji dengan kardus asli SPASI sebelum menaruh (p) dan ID 1 diangkat.
- **19 Okt:** ~~README utama~~ (18 Okt: README bahasa Inggris dengan angka dari STATUS, diagram Mermaid, contoh trace nyata, batasan; LICENSE MIT; `.gitignore` ditambah `.pytest_cache/`; scan file yang di-track dan seluruh riwayat git: tidak ada Function URL, nomor akun AWS, atau key) · ~~rapikan repo~~ (18 Okt: `test_cam.py` dihapus; `aws/README.md` diperbarui ke bahasa Inggris dan cara deploy dengan tag hash; nama IAM user dihapus dari docs; `data/camera_laptop_draft.yaml` dipertahankan sebagai file kalibrasi).
- **18 Okt (Sabtu) sore:** ~~evaluasi 25 percobaan~~ (selesai dalam satu sesi, FAIL di C2b). **20 Okt:** cadangan.
- **21 Okt (Rabu):** sesi 2 evaluasi tidak dipakai (semua percobaan selesai 18 Okt); fitur dikunci. Opsional, bukan untuk submit: percobaan lanjutan di pita margin tengah (lihat hasil evaluasi).
- **19 Okt (dimajukan):** ~~percantik UI halaman juri~~ — desain Blueprint selesai, di-deploy (`7a08913`) dan dites live, lihat "Halaman juri: desain Blueprint".
- ~~**Kamis 22–Jumat 23 Okt:** percantik UI halaman juri,~~ **hanya tampilan** (CSS, layout, teks, tampilan HP); logika keputusan, `samples.json`, dan API tidak berubah. `pytest` lulus, deploy dengan tag hash baru + tes live. **Selesai Jumat malam**, sebelum rekam video Sabtu.
- **Jumat 23 Okt:** ~~rapikan `docs/REPORT.md`~~ (tanggal 23 Okt, Summary di bawah disclaimer, §12 Reproduce, §13 Team; angka tidak berubah) + review naskah dan diagram Vincent.
- **Diagram final (18 Okt):** `docs/img/architecture.png` dan `docs/img/agent_loop.png` (dari Claude Design, 1920×1080, ±0,23 MB tiap file, dicek: tanpa Function URL atau nomor akun, metadata PNG kosong). Dipasang di REPORT §4 dan §8.1 (Mermaid tetap ada di bawahnya sebagai versi teks) dan di README. **Saat submit:** unggah ke galeri gambar Devpost, architecture dulu, lalu agent_loop.
- **Sabtu 24 Okt:** rekam video (Yasin + Vincent), adegan sesuai "Alur video final".
- **Minggu 25 Okt:** edit video, finalisasi laporan, isi Devpost.
- **Senin 26 Okt:** isi `LINKS` di awal skrip `web/index.html` (repo, video, REPORT, markers, board; sekarang sengaja masih kosong) → deploy ulang dengan tag hash baru (rollback = `f465e07`) → tes live (`GET /`, link terbuka, s2 +16 → RED, `aws/test_endpoint.py`, `/log` di CloudWatch). **Sebelum repo dibuat publik: scan ulang seluruh riwayat git** (bukan hanya commit terakhir) untuk secret, access key, nomor akun AWS, dan Function URL; REPORT §6 menyebut scan 18 Okt bersih, commit sesudahnya belum di-scan. Lalu jadikan repo publik, cek akhir halaman juri dari HP, submit (deadline 27 Okt 14.45).

## Bonus (hanya kalau inti selesai)
- S3 (foto bukti per keputusan) + DynamoDB (log keputusan, approval, override). Log approve/override dari halaman juri **sudah** tercatat di CloudWatch Logs (satu baris JSON `web_supervisor_choice`).
- Dashboard + alarm CloudWatch (durasi, error, jumlah RETAKE).
- Deteksi kardus tanpa marker.

## Kardus
- 邮政纸箱 5号, 29 × 17 × 19,3–19,7 cm, dipakai berdiri: lebar 29 cm kiri-kanan (arah menjorok), tinggi terukur rata-rata ID 0 19,6 · ID 1 19,5 · ID 2 19,4 cm, dalam 17. Marker 80 mm (terukur) di tengah sisi depan; tengah marker dari dasar ID 0 9,4 · ID 1 9,7 · ID 2 9,7 cm. Isi 1,0 kg di tengah, semua sama. ID 0 selalu di bawah. Hanya kardus yang ditumpuk boleh terlihat kamera.
- Kamera ±0,95–1,0 m. Saat uji roboh, laptop jangan di arah jatuhnya.

## Aturan kerja
- Semua jam waktu China.
- Secret (AWS key, API key) hanya di `.env` atau `aws configure`. Jangan pernah di-commit. Tiap orang pakai IAM user sendiri.
- Repo akan dibuat public sebelum submit: jangan commit data pribadi, foto kamar/wajah, atau info akun/pembayaran. Official Rules (dicek 18 Okt): repo tidak wajib publik ("A public or private judge-accessible code repository or archive. The code does not have to be open source."); keputusan: tetap dijadikan publik supaya juri pasti bisa mengakses.
- **Desain halaman juri (keputusan Yasin, 19 Okt):** permintaan desain (hanya tampilan `web/index.html`) langsung di-commit, push, deploy, dan dites live tanpa tanya dulu, lalu dicatat di STATUS dengan target rollback. Perubahan di luar desain (service, sampel, foto, API, evaluasi) atau tes yang gagal: tetap tanya dulu.
- Versi dependency di-pin. Tiap klaim di README/laporan harus didukung angka evaluasi. Drystone adalah alat bantu keputusan, bukan perangkat keselamatan bersertifikat.
