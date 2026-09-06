#!/usr/bin/env python3
"""
Am I on the free tier right now?

Sends the smallest possible request and reports which rung of the waterfall
served it, plus what it cost. Costs ~2 tokens, so you can run it freely.

    python3 freecheck.py
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

for line in open(os.path.join(HERE, ".env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

KEY   = os.environ.get("API_KEY", "")
BASE  = os.environ.get("BASE_URL", "https://api.experientiallabs.ai/v1").rstrip("/")
MODEL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MODEL", "gpt-6-astra")

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()

body = json.dumps({
    "model": MODEL,
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 1,
}).encode()

req = urllib.request.Request(
    BASE + "/chat/completions", data=body,
    headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
)

try:
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        hdrs, data = dict(r.headers), json.loads(r.read().decode())
except urllib.error.HTTPError as e:
    sys.exit("HTTP %s: %s" % (e.code, e.read().decode()[:300]))

depth  = hdrs.get("x-gateway-route-depth")
reason = hdrs.get("x-gateway-route-reason")
usage  = data.get("usage", {}) or {}
cost   = usage.get("cost")

print("\n  model        %s" % MODEL)
print("  route depth  %s  (%s)" % (depth, reason))
print("  cost         %s" % cost)

if depth == "0" and (cost in (0, 0.0, None)):
    print("\n  ON THE FREE TIER -- requests are not touching your credits.\n")
elif cost:
    print("\n  PAYING -- this request billed credits (free allowance is used up).\n")
else:
    print("\n  UNCLEAR -- check the Logs page on the dashboard.\n")
