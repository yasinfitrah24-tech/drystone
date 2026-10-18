# Drystone on AWS Lambda

`tools/service.py` turns stack photos into a decision (JSON) and serves the judges' page. It calls the same
decision code as the laptop agent (`tools/drystone_core.py`), so no decision rule is written twice.

Region **ap-southeast-1**, no AWS Marketplace. The account is on the AWS **Paid plan** (not the Free plan), so usage above the always-free quota is billed: stay inside it (Lambda 1 million requests and 400,000 GB-seconds a month, CloudWatch Logs 5 GB), and keep the zero-spend budget alarm (email) on. Never put access keys in the repository, in this
file or in chat: use `aws configure` on your own machine. The Function URL is not written in the repository;
keep it in the environment variable `DRYSTONE_URL`.

## Why a container image
OpenCV 5 + MuJoCo + NumPy are too large for a Lambda zip (250 MB unzipped), so the function is a container image
(limit 10 GB). The image copies `tools/`, `config/boxes.json`, `data/camera_laptop.yaml` and `web/`.

## Function settings
- Container image from ECR repository `drystone-service`, x86_64.
- Memory **2048 MB** (Lambda CPU grows with memory; the simulation needs CPU). Timeout **60 s**.
- Environment (set in the Dockerfile): `DRYSTONE_CALIB`, `DRYSTONE_BOXES`, `DRYSTONE_MARKER_MM=80`, `DRYSTONE_WEB`.
- The calibration is `data/camera_laptop.yaml`: photos must come from that webcam at **1280×720**.
- Function URL with auth type NONE and CORS for POST. Reserved concurrency cannot be set on this account (account
  limit 10 concurrent executions, and AWS keeps 10 unreserved), so the protection is in the code (see Limits).

## Update the function (Windows cmd, from the repository folder)
Docker Desktop must be running. Build and push with two tags, `latest` and the commit hash, and point the function
at the **commit-hash tag** so the live version is always clear. One command per line:

```
docker build --provenance=false -f aws/Dockerfile -t drystone-service .
```
```
for /f %i in ('aws sts get-caller-identity --query Account --output text') do set ACC=%i
```
```
for /f %i in ('git rev-parse --short HEAD') do set TAG=%i
```
```
set REPO=%ACC%.dkr.ecr.ap-southeast-1.amazonaws.com/drystone-service
```
```
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin %ACC%.dkr.ecr.ap-southeast-1.amazonaws.com
```
```
docker tag drystone-service:latest %REPO%:latest
```
```
docker tag drystone-service:latest %REPO%:%TAG%
```
```
docker push %REPO%:%TAG%
```
```
docker push %REPO%:latest
```
```
aws lambda update-function-code --function-name drystone --image-uri %REPO%:%TAG% --region ap-southeast-1 --query LastUpdateStatus
```
```
aws lambda wait function-updated --function-name drystone --region ap-southeast-1
```

Before each deploy, write the current image tag down as the rollback target (`docs/STATUS.md`). To roll back, run
`update-function-code` with the previous tag and wait again. Never delete or recreate the function: that would
change the Function URL. Builds after the first are fast (cached) as long as `aws/requirements-lambda.txt` does
not change. From China, PyPI can be very slow; build with
`--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple` if that file changes.

## First-time setup (already done for this project)
1. `aws ecr create-repository --repository-name drystone-service --region ap-southeast-1`
2. Build, tag and push as above.
3. Console: Lambda → Create function → Container image → the image → x86_64. Configuration → General: 2048 MB,
   60 s.
4. Configuration → Function URL: auth type NONE (public demo), CORS allow POST.

## Routes on the Function URL
- `GET /`: the judges' page (`web/index.html`). `GET /samples/<id>.jpg`: sample photos listed in
  `web/samples/samples.json`.
- `POST /` with `{"sample": "s2", "offset_cm": 14}`: decision for a sample photo (OpenCV + `drystone_core`, fixed
  seed, cached per container and marked `"cached": true`).
- `POST /log` with `{"sample", "offset_cm", "choice", "name", "reason"}`: one JSON line `web_supervisor_choice` in
  CloudWatch Logs, without the IP address. An override needs a name and a reason and never changes the decision.
- `POST /` with `"images"`: the photo API used by `agent.py --aws` (below).

## Limits
Web JSON ≤ 16 KB and photo POST ≤ 2 MB (else 413). Per IP and per container: 60 GET and 20 POST per minute (else
429). The shift is rounded to 1 cm in −16…+16 cm, so the decision cache holds at most 3 × 33 = 99 entries per
container.

## Photo API (used by `agent.py --aws`)
Request body (JSON):
- `mode`: `"decide"` or `"check"`
- `images`: 1–5 base64 photos (JPEG or PNG) in a row; more photos give a steadier reading
- decide: `offset_cm` (shift to the right of the box directly below), `box_id` (optional: smallest ID not on the
  stack)
- check: `plan` = one of the `plans` from a decide answer (`plans.requested` or `plans.suggested`)
- `return_image`: true = also return the annotated photo (`image_jpg_b64`)

Answer:
- `ok`, `problem`, `seconds`, `stack` (box positions in cm), `off_stack` (visible boxes not on the stack, with
  `where`: floor / beside / gap)
- `action`: GUIDE / ASK_SUPERVISOR / REJECT (decide), RETAKE (bad reading), CONTINUE / FIX_PLACEMENT / STOP /
  WAIT (check), DONE (every box is on the stack)
- `decision`: `zone`, `p`, `ci`, `n`, `trace`, `alternative` (`offset_cm`, `p`, `further_offset_cm`, `p_further`)
- `plans` (decide); `verify` with `status` OK / OFF_PLAN / FELL and `risk_now` (check)

## Test it
- Without AWS: `python tools/web_local.py` (same handler, fake Function URL events), then http://127.0.0.1:8000/,
  and `python -m pytest tests -q`.
- The Docker image on the laptop: `docker run -p 9000:8080 drystone-service`, then
  `python aws/test_endpoint.py --image <photo> --offset-cm 12`.
- The live Function URL: `python aws/test_endpoint.py --url %DRYSTONE_URL% --image web\samples\s2.jpg --offset-cm 6`.
- Logs: `aws logs tail /aws/lambda/drystone --since 15m --region ap-southeast-1`.
