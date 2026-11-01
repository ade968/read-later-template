#!/usr/bin/env python3
"""Save one link from an Add link issue, or from a repository_dispatch payload.

Issue text is read only from environment variables. It is never passed to a shell.
The workflow sets ISSUE_AUTHOR and REPO_OWNER. A mismatch is refused.
"""
import html
import json
import os
import re
import sys
import urllib.parse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "saved-links.json"
LIMITS = {"title": 300, "topic": 80, "note": 500}
_BAD_URL = re.compile(r"[\x00-\x20\x7f\u2028\u2029<>\\]")
_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SCRIPT = re.compile(r"(?is)<(script|style)\b[^>]*>.*?</\1>")
_TAG = re.compile(r"(?s)<[^>]*>")


def valid_http_url(url):
    if not isinstance(url, str):
        return False
    url = url.strip()
    if not url or len(url) > 2000 or _BAD_URL.search(url):
        return False
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        return False
    if not parts.netloc or not parts.hostname:
        return False
    return True


def plain_field(value, limit):
    if not isinstance(value, str):
        value = ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = _CONTROLS.sub("", value)
    value = html.unescape(value)
    value = _SCRIPT.sub(" ", value)
    value = _TAG.sub(" ", value)
    value = html.unescape(value)
    value = _SCRIPT.sub(" ", value)
    value = _TAG.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if value in {"_No response_", "None"}:
        return ""
    return value[:limit]


def capped(name, limit):
    value = os.environ.get(name, "")
    if not isinstance(value, str):
        value = ""
    if len(value) > limit:
        value = value[:limit]
    return value


def require_owner():
    """Refuse unless the issue author is the repository owner.

    A local run that only sets LINK_URL (no issue body, no author, not in Actions)
    is the person at that computer typing a command. Anything that arrived as an
    issue, or any run inside Actions, must name the owner and match them.
    """
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    from_issue = "ISSUE_BODY" in os.environ
    named = "ISSUE_AUTHOR" in os.environ or "REPO_OWNER" in os.environ
    if not (in_actions or from_issue or named):
        return
    owner = plain_field(os.environ.get("REPO_OWNER", ""), 100)
    author = plain_field(os.environ.get("ISSUE_AUTHOR", ""), 100)
    if not owner or not author or author.lower() != owner.lower():
        sys.exit("Refusing: only the repository owner can add a link.")


def require_label():
    if "ISSUE_BODY" not in os.environ:
        return
    labels = [part.strip().lower() for part in capped("ISSUE_LABELS", 2000).split(",")]
    if "add-link" not in labels:
        sys.exit("Refusing: the issue does not have the add-link label.")


def parse_form(body):
    fields, key = {}, None
    for line in body.splitlines():
        match = re.match(r"^###\s+(.*)$", line.strip())
        if match:
            key = plain_field(match.group(1), 80).lower()
            fields[key] = []
        elif key is not None:
            fields[key].append(line)

    def value(name):
        return "\n".join(fields.get(name, []))

    return dict(url=value("link"), title=value("title"), topic=value("topic"), note=value("note"))


def entry_from_env():
    if "ISSUE_BODY" in os.environ:
        return parse_form(capped("ISSUE_BODY", 20000))
    return dict(
        url=capped("LINK_URL", 4000),
        title=capped("LINK_TITLE", 2000),
        topic=capped("LINK_TOPIC", 500),
        note=capped("LINK_NOTE", 4000),
    )


def main():
    require_owner()
    require_label()
    incoming = entry_from_env()
    raw_url = incoming.get("url") if isinstance(incoming.get("url"), str) else ""
    if not valid_http_url(raw_url):
        sys.exit("Not a valid http(s) link.")
    url = raw_url.strip()
    title = plain_field(incoming.get("title", ""), LIMITS["title"])
    topic = plain_field(incoming.get("topic", ""), LIMITS["topic"])
    note = plain_field(incoming.get("note", ""), LIMITS["note"])
    if not PATH.exists():
        sys.exit("Missing saved-links.json")
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        sys.exit("saved-links.json is not valid JSON")
    if not isinstance(data, dict) or not isinstance(data.get("links"), list):
        sys.exit("saved-links.json must contain a links list")
    if any(isinstance(item, dict) and item.get("url") == url for item in data["links"]):
        print("Already saved.")
        return
    record = {"url": url}
    if title:
        record["title"] = title
    if topic:
        record["topic"] = topic
    record["added"] = date.today().isoformat()
    if note:
        record["note"] = note
    data["links"].insert(0, record)
    blob = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temporary = PATH.with_name(PATH.name + ".tmp")
    temporary.write_text(blob, encoding="utf-8")
    temporary.replace(PATH)
    print("Saved:", url)


if __name__ == "__main__":
    main()
