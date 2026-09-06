# api-key-test

Tester and interactive chat for an Experiential Labs API key.
Endpoint is OpenAI-compatible: `https://api.experientiallabs.ai/v1`

## Setup

The key lives in `.env` next to these scripts — nothing to export:

```
API_KEY=xpl_...
BASE_URL=https://api.experientiallabs.ai/v1
MODEL=gpt-6-astra
```

`test.py` and `freecheck.py` need no dependencies. `chat.py` and `server.py` use the official
OpenAI SDK (already installed here; otherwise `pip install -r requirements.txt`).

## The scripts

| Script | What it does |
|---|---|
| `test.py --models` | Lists all 313 models the key can reach. Cheapest way to check the key — spends no tokens. |
| `test.py "prompt"` | One request, one answer. Standard library only, so it works even if the SDK is broken. |
| `chat.py` | **Interactive chat** — multi-turn history, streamed replies. This is the normal way to talk to it. |


## Web UI (recommended)

```
python3 server.py
```

Opens `http://localhost:8765` in your browser. Chat window with:

- **+ Files** — attach individual files
- **+ Folder** — attach a whole folder; it walks the tree for you
- **model dropdown** — switch between all 313 models mid-conversation
- token count and cost under every reply

Attached files stay in the conversation, so follow-up questions still see them
without re-attaching.

Your key never reaches the browser. The page talks only to the local Python
server, which holds the key and calls the API.

### Watching what it costs

The header shows a running total for the session:

```
$0.0142 this session · 8,431 tok · carrying ~29,255/msg
```

- **this session** — cost of every reply so far, reset by **Clear**
- **carrying ~N/msg** — how many tokens the current history plus attachments
  drags into *every* further message. This turns amber above 20k.

That last number is the one to watch. Attached files stay in the conversation
so follow-ups can see them, which means the whole bundle is resent every turn.
A 30k-token attachment costs roughly $0.30 per message at $10/M input, not
just once. Hit **Clear** when you're done with a set of files.

### Reasoning effort

The dropdown next to the model picker sets `reasoning_effort`. The gateway
accepts eight levels:

`none` · `minimal` · `low` · `medium` · `high` · `xhigh` · `ultra` · `max`

Leave it on **default** to let the model decide. Each reply shows how many
reasoning tokens were actually spent, so you can see the setting take effect —
measured on one puzzle with `gpt-6-astra`:

| effort | reasoning tokens |
|---|---|
| low | 65 |
| max | 193 |

Not every model supports it. If one rejects the setting, the request is
automatically retried without it and a note appears under the input box rather
than the message failing.

From the command line it's just another field:

```
curl https://api.experientiallabs.ai/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-6-astra","reasoning_effort":"high",
       "messages":[{"role":"user","content":"hi"}]}'
```

### What gets skipped when you attach a folder

To avoid burning tokens on junk, these are filtered out automatically and
listed under the input box so you know what was dropped:

- `.git`, `node_modules`, `__pycache__`, `venv`, `dist`, `build`, `target`, `.idea`, `.vscode`, `vendor`
- binaries and media (images, PDFs, archives, fonts, compiled files, lockfiles)
- any single file over 200 KB, or once the total passes 1.5 MB

Watch the token estimate next to the attachment chips before sending a large
folder — the whole bundle is resent on every follow-up turn, so a big
attachment costs on each message, not just the first.

## Chatting (terminal)

```
python3 chat.py
```

Then just type. It remembers the conversation. Commands:

- `/reset` — forget the conversation
- `/system <text>` — set a system prompt (also resets)
- `/tokens` — token usage and cost of the last reply
- `/exit` — quit (Ctrl-D works too)

Single question without entering the REPL:

```
python3 chat.py "explain HTTP 429 in one sentence"
```

## Switching models

313 are available. Run `python3 test.py --models` to list them, then either edit
`MODEL` in `.env` or override for one run:

```
MODEL=claude-opus-5 python3 chat.py
```

## Note on certificates

This machine's python.org Python 3.10 has no root certificates installed, so
plain `urllib` calls fail with `CERTIFICATE_VERIFY_FAILED`. `test.py` works
around it by using `certifi`'s CA bundle. To fix it globally for every Python
script on the machine, run once:

```
/Applications/Python\ 3.10/Install\ Certificates.command
```

The OpenAI SDK is unaffected — it bundles `certifi` already.

## Troubleshooting

| Status | Means |
|---|---|
| 401 / 403 | Key wrong, expired, or lacking permission |
| 404 | `BASE_URL` or endpoint path wrong |
| 400 | `MODEL` not valid for this provider |
| 429 | Rate limited or out of credits |
| HTTP 0 | Network/TLS problem locally, not the key |

`.env` is gitignored — don't commit your key.
