#!/usr/bin/env python3
"""
Interactive chat against the API -- like a normal LLM conversation.
Keeps history across turns and streams the reply as it arrives.

    python3 chat.py                 # start chatting
    python3 chat.py "one question"  # single question, then exit

Commands inside the chat:
    /reset    forget the conversation and start over
    /system   <text>   change the system prompt (also resets)
    /tokens   show token usage of the last reply
    /exit     quit  (Ctrl-D or Ctrl-C also work)
"""
import os
import sys

from openai import OpenAI

HERE = os.path.dirname(os.path.abspath(__file__))


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
SYSTEM   = os.environ.get("SYSTEM", "")

if not API_KEY or API_KEY.startswith("paste-"):
    sys.exit("No API key. Set API_KEY in the .env file next to this script.")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

# terminal colours, disabled when piping to a file
_tty = sys.stdout.isatty()
DIM  = "\033[2m"  if _tty else ""
BOLD = "\033[1m"  if _tty else ""
CYAN = "\033[36m" if _tty else ""
OFF  = "\033[0m"  if _tty else ""

last_usage = None
USE_USAGE_OPT = True   # ask for token usage in streaming responses


def fresh_history():
    return [{"role": "system", "content": SYSTEM}] if SYSTEM else []


def ask(messages):
    """Send the conversation, stream the reply, return the text."""
    global last_usage, USE_USAGE_OPT
    parts = []
    try:
        kwargs = {"model": MODEL, "messages": messages, "stream": True}
        if USE_USAGE_OPT:
            # OpenAI-compatible servers only report token usage while streaming
            # if you ask for it. Not every gateway accepts the option.
            kwargs["stream_options"] = {"include_usage": True}
        try:
            stream = client.chat.completions.create(**kwargs)
        except Exception:
            if not USE_USAGE_OPT:
                raise
            USE_USAGE_OPT = False           # unsupported -- don't try again
            kwargs.pop("stream_options")
            stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            # The usage totals arrive in a final chunk that has no choices,
            # so read usage before skipping choice-less chunks.
            if getattr(chunk, "usage", None):
                last_usage = chunk.usage
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content
            if piece:
                parts.append(piece)
                print(piece, end="", flush=True)
        print()
    except Exception as stream_err:
        # Some gateways don't support streaming -- fall back to a normal call.
        if parts:
            raise
        try:
            resp = client.chat.completions.create(model=MODEL, messages=messages)
        except Exception as e:
            print("\n{}request failed:{} {}".format(BOLD, OFF, e))
            print("{}(streaming attempt said: {}){}".format(DIM, stream_err, OFF))
            return None
        text = resp.choices[0].message.content or ""
        last_usage = getattr(resp, "usage", None)
        print(text)
        return text
    return "".join(parts)


def main():
    history = fresh_history()

    # one-shot mode: python3 chat.py "question"
    if len(sys.argv) > 1:
        history.append({"role": "user", "content": " ".join(sys.argv[1:])})
        ask(history)
        return

    print("{}{} @ {}{}".format(BOLD, MODEL, BASE_URL, OFF))
    print("{}/reset  /system <text>  /tokens  /exit{}\n".format(DIM, OFF))

    while True:
        try:
            user = input("{}you>{} ".format(CYAN + BOLD, OFF)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user:
            continue
        if user in ("/exit", "/quit", "/q"):
            break
        if user == "/reset":
            history = fresh_history()
            print("{}history cleared{}\n".format(DIM, OFF))
            continue
        if user.startswith("/system"):
            global SYSTEM
            SYSTEM = user[len("/system"):].strip()
            history = fresh_history()
            print("{}system prompt set, history cleared{}\n".format(DIM, OFF))
            continue
        if user == "/tokens":
            print("{}{}{}\n".format(DIM, last_usage or "no usage reported yet", OFF))
            continue

        history.append({"role": "user", "content": user})
        print("\n{}{}>{} ".format(BOLD, MODEL, OFF), end="", flush=True)
        reply = ask(history)
        print()

        if reply is None:
            history.pop()          # request failed, don't poison the history
        else:
            history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
