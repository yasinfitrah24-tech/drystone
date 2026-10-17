# Drystone di AWS Lambda

Layanan `tools/service.py` menerima foto tumpukan dan mengembalikan keputusan dalam bentuk JSON. Kodenya sama dengan agent di laptop (`drystone_core.py`), jadi tidak ada logika keputusan yang ditulis ulang.

Region **ap-southeast-1**. Pakai akun Free plan dan IAM user masing-masing. **Jangan pernah** menulis access key di repo, file ini, atau chat. Simpan hanya lewat `aws configure` di laptop sendiri.

## Kenapa memakai container image
OpenCV 5 + MuJoCo + NumPy terlalu besar untuk zip Lambda (batas 250 MB setelah diekstrak), jadi dipakai container image (batas 10 GB).

## Sudah diuji (17 Okt)
- Handler dijalankan di Python 3.12 bersih dengan `requirements-lambda.txt` (OpenCV headless, tanpa GUI), memakai foto asli tumpukan 2 kardus:
  - +6 cm: HIJAU 1% (1,7 dtk)
  - +12 cm: KUNING 41%, usulan +8 cm (8,3 dtk)
  - +16 cm: MERAH 87% (8,2 dtk)
- Image Docker **belum** dibangun, karena registry `public.ecr.aws` diblokir di lingkungan uji. Langkah build di bawah perlu dicoba sekali.

## Pengaturan fungsi
- Memori **2048 MB** (CPU Lambda naik seiring memori; simulasi butuh CPU).
- Timeout **60 detik** (keputusan biasanya 2–10 detik).
- Arsitektur x86_64.
- Env (sudah di Dockerfile): `DRYSTONE_CALIB`, `DRYSTONE_BOXES`, `DRYSTONE_MARKER_MM=80`.
- Kalibrasi yang dibawa adalah `data/camera_laptop.yaml`, jadi foto **harus dari webcam laptop Yasin, 1280×720**. Kamera lain butuh kalibrasi sendiri.

## Langkah deploy (sekali)
Butuh Docker (Docker Desktop di Windows) dan AWS CLI yang sudah `aws configure`. Jalankan dari folder repo.

1. Build:
   ```
   docker build -f aws/Dockerfile -t drystone-service .
   ```
2. Buat repo ECR (sekali):
   ```
   aws ecr create-repository --repository-name drystone-service --region ap-southeast-1
   ```
3. Login, tag, push (`<akun>` = 12 digit ID akun AWS):
   ```
   aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin <akun>.dkr.ecr.ap-southeast-1.amazonaws.com
   docker tag drystone-service:latest <akun>.dkr.ecr.ap-southeast-1.amazonaws.com/drystone-service:latest
   docker push <akun>.dkr.ecr.ap-southeast-1.amazonaws.com/drystone-service:latest
   ```
4. Buat fungsi di Console: Lambda → Create function → **Container image** → pilih image tadi → x86_64. Lalu Configuration → General: memori 2048 MB, timeout 60 dtk.
5. Configuration → **Function URL** → Auth type **AWS_IAM** saat masih tahap uji, NONE untuk demo juri (sekarang NONE). *Reserved concurrency* **tidak bisa** dipasang di akun ini (limit akun 10, AWS mewajibkan 10 tetap unreserved), jadi perlindungan ada di kode: batas body, batas request per IP, dan cache (lihat bagian Halaman web juri).
6. Uji di tab Test dengan event:
   ```json
   {"mode": "decide", "images": ["<base64 foto>"], "offset_cm": 12, "return_image": false}
   ```

## Format
Request (body JSON):
- `mode`: `"decide"` atau `"check"`
- `images`: 1–5 foto base64 (jpg/png) berturut-turut. Lebih banyak foto = lebih stabil, karena arah hadap dirata-rata.
- `decide`: `offset_cm` (geser ke kanan dari kardus teratas), `box_id` (opsional)
- `check`: `plan` = salah satu isi `plans` dari jawaban decide (`plans.diminta` atau `plans.usulan`)
- `return_image`: true = kirim balik foto beranotasi (`image_jpg_b64`, ±190 KB)

Jawaban:
- `ok`, `problem`
- `action`: PANDU / MINTA_PERSETUJUAN / TOLAK / FOTO_ULANG / LANJUT / BETULKAN / BERHENTI / TUNGGU / SELESAI
- `stack` (posisi kardus, cm)
- `decision`: zone, p, ci, n, trace, alternative
- `plans`
- `verify` dan `risk_now` (mode check)
- `seconds`

## Halaman web juri (Function URL yang sama)
- `GET /` halaman (`web/index.html`), `GET /samples/<id>.jpg` foto contoh dari `web/samples/samples.json`.
- `POST {"sample": "s2", "offset_cm": 14}` → keputusan untuk foto contoh (OpenCV + `drystone_core`, seed 0, di-cache per container, `"cached": true`).
- `POST /log {"sample", "offset_cm", "choice", "name", "reason"}` → satu baris JSON `web_supervisor_choice` di CloudWatch Logs. Override wajib nama + alasan dan tidak mengubah keputusan.
- POST foto lama (body berisi `images`) tidak berubah, jadi `agent.py --aws` tetap jalan.
- Batas: JSON web ≤ 16 KB, POST foto ≤ 2 MB (413); per IP per container 60 GET dan 20 POST per menit (429); geseran dibulatkan ke 1 cm dalam −16…+16 cm, jadi cache maksimal 3 × 33 = 99 entri per container.
- Uji lokal tanpa AWS: `python tools/web_local.py` lalu buka http://127.0.0.1:8000/. Tes: `python -m pytest tests -q`.

## Berikutnya (20–21 Okt)
- S3: simpan foto bukti per keputusan.
- DynamoDB: log keputusan, persetujuan, dan override (isi sama dengan `log.jsonl` di laptop).
- Dashboard statis (S3) untuk melihat log dan menyetujui atau override KUNING/MERAH.
- CloudWatch: durasi, jumlah error, jumlah FOTO_ULANG.
- Biaya: cek Billing setelah deploy. Harusnya sangat kecil dan tertutup kredit, tapi tetap dicek, jangan diasumsikan.
