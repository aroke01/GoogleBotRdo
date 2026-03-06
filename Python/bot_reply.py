"""
Pipeline bot reply script.
Usage: python bot_reply.py "<raw message from Space>"
Example: python bot_reply.py "@Louis Paré /note 734dbc_1480 the cache seems broken"
"""

import requests
import re
import sys

WEBHOOK = "https://chat.googleapis.com/v1/spaces/AAQA_zvdsdQ/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=Kk172XQnlzDx9YIbQsbj7CcsS8wQJhH5901P99Una4E"
LOOKUP_URL = "http://mtl-webapps01/sg_dependencies/api/sg/lookup"


def lookup(code):
    r = requests.get(LOOKUP_URL, params={"q": code}, timeout=10)
    return r.json()


def parse_message(text):
    """Extract tagged user, shot/asset code, and note."""
    tagged = re.search(r'@([\w\s\-À-ÿ]+?)(?=\s*/note|\s+/note)', text, re.IGNORECASE)
    command = re.search(r'/note\s+([\w._-]+)[,\s]*(.+)?', text, re.IGNORECASE)

    name = tagged.group(1).strip() if tagged else None
    code = command.group(1).strip().rstrip(',') if command else None
    note = command.group(2).strip() if command and command.group(2) else ""

    return name, code, note


def get_sg_link(data):
    links = data.get("links", {})
    return links.get("shot") or links.get("version") or links.get("asset", "")


def format_reply(name, code, note, data):
    if not data.get("found"):
        return f"❓ `{code}` — not found in ShotGrid."

    sg_link = get_sg_link(data)

    parts = ["✅ recorded:"]
    
    if name:
        parts.append(f"to {name}")
    
    parts.append("-")
    parts.append(f"Please check {code}")
    
    if note:
        parts.append(f", {note}")
    
    if sg_link:
        parts.append(f"<{sg_link}|→ ShotGrid>")
    else:
        parts.append("→ ShotGrid")
    
    return " ".join(parts)


def send(text):
    r = requests.post(WEBHOOK, json={"text": text}, timeout=10)
    print(r.status_code)


if __name__ == "__main__":
    raw = " ".join(sys.argv[1:])
    name, code, note = parse_message(raw)

    if not code:
        send("❓ No `/note` command found.")
        sys.exit(1)

    data = lookup(code)
    reply = format_reply(name, code, note, data)
    send(reply)