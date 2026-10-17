r"""Send photo(s) to the Drystone service and print its decision.

Test the Docker image on the laptop (after `docker run -p 9000:8080 drystone-service`):
    python aws/test_endpoint.py --image data/agent_20261017_142634/langkah_003_cek_ulang.png --offset-cm 12
Test the Lambda on AWS (Function URL):
    python aws/test_endpoint.py --url https://xxxx.lambda-url.ap-southeast-1.on.aws/ --image ... --offset-cm 12
Test the Lambda through the AWS CLI (no public URL): write an event file, then `aws lambda invoke`:
    python aws/test_endpoint.py --image ... --offset-cm 12 --write-event event.json
    aws lambda invoke --function-name drystone --cli-binary-format raw-in-base64-out --payload fileb://event.json out.json --region ap-southeast-1
    python aws/test_endpoint.py --read-response out.json
Standard library only.
"""
import argparse
import base64
import json
import os
import time
import urllib.request

LOCAL = "http://localhost:9000/2015-03-31/functions/function/invocations"   # Lambda runtime emulator


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", nargs="+", help="1-5 photos from the calibrated laptop webcam (1280x720)")
    ap.add_argument("--write-event", help="only write a Lambda event to this file (for aws lambda invoke)")
    ap.add_argument("--read-response", help="read and print an aws lambda invoke response file")
    ap.add_argument("--offset-cm", type=float, default=0.0)
    ap.add_argument("--box-id", type=int)
    ap.add_argument("--url", default=LOCAL, help="default = Docker image on the laptop")
    ap.add_argument("--save", default="endpoint_result.jpg", help="where to save the annotated photo from the answer")
    args = ap.parse_args()

    if args.read_response:
        with open(args.read_response, encoding="utf-8") as f:
            show(json.load(f), args.save, None)
        return
    if not args.image:
        ap.error("--image is required")
    body = {"mode": "decide", "offset_cm": args.offset_cm,
            "images": [base64.b64encode(open(p, "rb").read()).decode() for p in args.image]}
    if args.box_id is not None:
        body["box_id"] = args.box_id
    payload = {"body": json.dumps(body)} if args.url == LOCAL else body   # the emulator expects a Lambda event
    if args.write_event:
        with open(args.write_event, "w", encoding="utf-8") as f:
            json.dump({"body": json.dumps(body)}, f)
        print(f"Event written: {os.path.abspath(args.write_event)} ({os.path.getsize(args.write_event) // 1024} KB)")
        return
    req = urllib.request.Request(args.url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    show(out, args.save, time.time() - t)


def show(out, save, seconds):
    if "body" in out and isinstance(out["body"], str):
        out = json.loads(out["body"])
    img = out.pop("image_jpg_b64", None)
    if img:
        with open(save, "wb") as f:
            f.write(base64.b64decode(img))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(("" if seconds is None else f"\nTotal {seconds:.1f} s (including upload).")
          + (f" Annotated photo: {os.path.abspath(save)}" if img else ""))


if __name__ == "__main__":
    main()
