#!/usr/bin/env python3
"""
Minimal LLM API key tester. Standard library only -- no pip install needed.

Usage:
    python3 test.py                      # send the default prompt
    python3 test.py "your prompt here"   # send your own prompt
    python3 test.py --models             # just list models (cheapest key check)
"""

import json
import os
import sys
import ssl
import urllib.error
import urllib.request

# python.org builds on macOS ship without root certificates unless you run
# "Install Certificates.command". Fall back to certifi's bundle so this script
# works regardless of how Python was installed.
try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env(path):
    """Dead-simple .env reader: KEY=value per line, # for comments."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))


load_env(os.path.join(HERE, ".env"))

API_KEY  = os.environ.get("API_KEY", "")
BASE_URL = os.environ.get("BASE_URL", "https://api.experientiallabs.ai/v1").rstrip("/")
MODEL    = os.environ.get("MODEL", "gpt-6-astra")
STYLE    = os.environ.get("STYLE", "openai").lower()   # "openai" or "anthropic"
TIMEOUT  = float(os.environ.get("TIMEOUT", "60"))


def request(path, payload=None, method="GET"):
    """Fire one HTTP call. Returns (status, parsed_body_or_text)."""
    url = BASE_URL + path

    if STYLE == "anthropic":
        headers = {
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    else:
        headers = {
            "Authorization": "Bearer " + API_KEY,
            "Content-Type": "application/json",
        }

    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else method)

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=SSL_CTX) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass
        return e.code, body
    except Exception as e:
        return 0, "{}: {}".format(type(e).__name__, e)


def show(status, body, label):
    """Print the outcome of a call in a readable way."""
    print("\n--- {} ---".format(label))
    print("HTTP {}".format(status))
    if status != 200:
        print("FAILED. Response body:")
        print(json.dumps(body, indent=2) if isinstance(body, (dict, list)) else body)
        print("\nCommon causes:")
        print("  401 / 403 -> key is wrong, expired, or lacks permission")
        print("  404       -> BASE_URL or the endpoint path is wrong for this provider")
        print("  400       -> MODEL name is not valid for this provider")
        print("  429       -> rate limited or out of credits")
        print("  HTTP 0    -> network/TLS problem, not the key (see message above)")
        return False
    return True


def list_models():
    path = "/models"
    status, body = request(path)
    if not show(status, body, "GET " + BASE_URL + path):
        return
    items = body.get("data", body) if isinstance(body, dict) else body
    names = []
    for m in (items if isinstance(items, list) else []):
        names.append(m.get("id") or m.get("name") if isinstance(m, dict) else str(m))
    print("Key works. {} model(s) available:".format(len(names)))
    for n in names[:60]:
        print("  " + str(n))
    if len(names) > 60:
        print("  ... and {} more".format(len(names) - 60))


def chat(prompt):
    if STYLE == "anthropic":
        path = "/messages"
        payload = {
            "model": MODEL,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
    else:
        path = "/chat/completions"
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
        }

    print("POST {}{}".format(BASE_URL, path))
    print("model: {}   style: {}".format(MODEL, STYLE))
    print("prompt: {}".format(prompt))

    status, body = request(path, payload)
    if not show(status, body, "response"):
        return

    # Pull the text out of whichever shape came back.
    text = None
    try:
        if STYLE == "anthropic":
            text = "".join(b.get("text", "") for b in body["content"]
                           if b.get("type") == "text")
        else:
            msg = body["choices"][0]["message"]
            text = msg.get("content") or msg.get("reasoning_content")
    except (KeyError, IndexError, TypeError):
        pass

    if text:
        print(text)
    else:
        print("Got a 200 but could not find the text field. Full body:")
        print(json.dumps(body, indent=2))

    usage = body.get("usage") if isinstance(body, dict) else None
    if usage:
        print("\nusage: {}".format(json.dumps(usage)))


if __name__ == "__main__":
    if not API_KEY or API_KEY.startswith("paste-"):
        sys.exit("No API key. Put it in the .env file next to this script (API_KEY=...).")

    args = sys.argv[1:]
    if args and args[0] in ("--models", "-m"):
        list_models()
    else:
        chat(" ".join(args) if args else "Reply with exactly: API key works.")
