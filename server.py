#!/usr/bin/env python3
"""
Local web UI for the chat API.

    python3 server.py          then open http://localhost:8765

The API key is read from .env and stays in this process -- it is never sent
to the browser. The page talks only to this server.
"""
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8765"))


def load_env():
    path = os.path.join(HERE, ".env")
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


load_env()

API_KEY  = os.environ.get("API_KEY", "")
BASE_URL = os.environ.get("BASE_URL", "https://api.experientiallabs.ai/v1")
MODEL    = os.environ.get("MODEL", "gpt-6-astra")

if not API_KEY or API_KEY.startswith("paste-"):
    sys.exit("No API key. Set API_KEY in .env next to this script.")

try:
    from openai import OpenAI
except ImportError:
    sys.exit("The openai package is missing. Run: pip3 install -r requirements.txt")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)


def build_attachment_block(attachments):
    """Turn the attached files into one text block for the model."""
    if not attachments:
        return ""
    tree = "\n".join("  " + a["path"] for a in attachments)
    parts = [
        "The user attached {} file(s):\n{}\n".format(len(attachments), tree),
        "File contents follow.\n",
    ]
    for a in attachments:
        parts.append("\n===== {} =====\n{}\n".format(a["path"], a["content"]))
    return "".join(parts)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    # ---------- helpers ----------
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, obj):
        self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode("utf-8"))
        self.wfile.flush()

    # ---------- routes ----------
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/api/config":
            self._send(200, {"model": MODEL, "base_url": BASE_URL})
        elif self.path == "/api/models":
            try:
                ids = sorted(m.id for m in client.models.list().data)
                self._send(200, {"models": ids})
            except Exception as e:
                self._send(500, {"error": str(e)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/chat":
            return self._send(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            return self._send(400, {"error": "bad json: %s" % e})

        messages    = req.get("messages") or []
        model       = req.get("model") or MODEL
        attachments = req.get("attachments") or []
        effort      = req.get("effort") or ""
        sys.stderr.write("  -> chat request, model=%s, effort=%s, %d message(s)\n"
                         % (model, effort or "(default)", len(messages)))

        # Fold attachments into the final user message.
        if attachments and messages and messages[-1].get("role") == "user":
            block = build_attachment_block(attachments)
            messages[-1] = {
                "role": "user",
                "content": block + "\n" + messages[-1].get("content", ""),
            }

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def make(**extra):
            kw = dict(model=model, messages=messages, stream=True, **extra)
            return client.chat.completions.create(**kw)

        stream = None
        attempts = []
        if effort:
            attempts.append({"reasoning_effort": effort,
                             "stream_options": {"include_usage": True}})
        attempts.append({"stream_options": {"include_usage": True}})
        attempts.append({})

        for i, kw in enumerate(attempts):
            try:
                stream = make(**kw)
                # Say so if the effort setting had to be dropped to succeed.
                if effort and i > 0:
                    self._sse({"type": "notice",
                               "message": "this model rejected reasoning_effort="
                                          + effort + " -- sent without it"})
                break
            except Exception as e:
                last_err = e
        if stream is None:
            self._sse({"type": "error", "message": str(last_err)})
            self._sse({"type": "done"})
            self.close_connection = True
            return

        try:
            reported = None
            for chunk in stream:
                # The gateway echoes back which model actually served this
                # request -- surface it so the UI can show ground truth.
                m = getattr(chunk, "model", None)
                if m and m != reported:
                    reported = m
                    self._sse({"type": "model", "model": m})
                usage = getattr(chunk, "usage", None)
                if usage:
                    ctd = getattr(usage, "completion_tokens_details", None)
                    self._sse({
                        "type": "usage",
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                        "reasoning_tokens": getattr(ctd, "reasoning_tokens", None),
                        "cost": getattr(usage, "cost", None),
                    })
                if not chunk.choices:
                    continue
                piece = chunk.choices[0].delta.content
                if piece:
                    self._sse({"type": "delta", "text": piece})
        except Exception as e:
            self._sse({"type": "error", "message": str(e)})

        self._sse({"type": "done"})
        # SSE has no Content-Length, so close the socket to signal the end --
        # otherwise the client waits on a connection that never finishes.
        self.close_connection = True


def start_server(port, tries=10):
    """Bind to `port`, or the next free one if something already has it."""
    last = None
    for candidate in range(port, port + tries):
        try:
            return ThreadingHTTPServer(("127.0.0.1", candidate), Handler), candidate
        except OSError as e:
            if e.errno not in (48, 98):        # 48 macOS, 98 Linux: in use
                raise
            last = candidate
            print("  port %d is busy, trying %d..." % (candidate, candidate + 1))
    raise SystemExit(
        "Could not find a free port between %d and %d.\n"
        "Something is already listening. Find it with:\n"
        "    lsof -nP -iTCP:%d -sTCP:LISTEN\n"
        "then stop it, or run this on another port:\n"
        "    PORT=9000 python3 server.py" % (port, last, port)
    )


if __name__ == "__main__":
    srv, PORT = start_server(PORT)
    url = "http://localhost:%d" % PORT
    print("\n  chat UI running at  %s" % url)
    print("  model: %s" % MODEL)
    print("  key stays in this process, never sent to the browser")
    print("  Ctrl-C to stop\n")
    if "--no-open" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
