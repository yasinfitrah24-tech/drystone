r"""Run the judges' web page on this laptop, through the same lambda_handler as AWS.

Each browser request is turned into a fake Function URL event (payload 2.0), so routing, limits and
answers are the same as on Lambda.

    python tools/web_local.py            -> open http://127.0.0.1:8000/
    python tools/web_local.py --port 8080
"""
import argparse
import base64
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import service  # noqa: E402

MAX_READ = 4 * 1024 * 1024        # read at most this much; the handler answers 413 above its own limits


def make_event(method, path, body, ip):
    return {"version": "2.0", "rawPath": path.split("?", 1)[0], "body": body, "isBase64Encoded": False,
            "headers": {"content-type": "application/json"},
            "requestContext": {"http": {"method": method, "path": path, "sourceIp": ip}}}


class Handler(BaseHTTPRequestHandler):
    def _send(self, out):
        body = out.get("body") or ""
        data = base64.b64decode(body) if out.get("isBase64Encoded") else body.encode("utf-8")
        self.send_response(out["statusCode"])
        for k, v in (out.get("headers") or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(service.lambda_handler(make_event("GET", self.path, None, self.client_address[0])))

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(min(n, MAX_READ)).decode("utf-8", errors="replace")
        if n > MAX_READ:
            body += " " * (n - MAX_READ)              # keep the real size so the handler answers 413
        self._send(service.lambda_handler(make_event("POST", self.path, body, self.client_address[0])))

    def log_message(self, fmt, *args):
        sys.stderr.write("[web] " + (fmt % args) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Judges' web page on this laptop (fake Function URL events)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1", help="127.0.0.1 = this laptop only")
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Drystone web page: http://{args.host}:{args.port}/   (Ctrl+C to stop)")
    print("Supervisor choices are printed here as one JSON line each, as in CloudWatch Logs.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
