#!/usr/bin/env python3
"""Build the Read it later library.

Reads config.yml, feeds.yml, and saved-links.json, fetches each feed, and
writes a self-contained page to _site/ (index.html and items.json).

Style and script are inline, with no root-relative URLs, so the same page
works at the root of a site or under a path such as /library.

Usage:
  python scripts/build.py [--out _site] [--cap N] [--max-age-days N]
"""
import argparse
import base64
import calendar
import hashlib
import html
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

ROOT = Path(__file__).resolve().parent.parent
SAVED_LABEL = "Saved links"
UA = "Mozilla/5.0 (compatible; ReadItLaterLibrary/1.0)"
# Some publishers reject a non-browser agent. Retry those once.
UA_FALLBACK = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Ceilings for a build. config.yml cannot raise them.
REQUEST_TIMEOUT_SECONDS = 20
TOTAL_TIMEOUT_SECONDS = 240
MAX_RESPONSE_BYTES = 5_000_000
MAX_ENTRIES_SCANNED = 100
MAX_WORKERS = 8
MAX_DATA_BYTES = 1_000_000

_BAD_URL = re.compile(r"[\x00-\x20\x7f\u2028\u2029<>\\]")
_TAG = re.compile(r"(?is)<(script|style)\b[^>]*>.*?</\1>")
_ANY_TAG = re.compile(r"(?s)<[^>]*>")
_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class FetchError(Exception):
    """A feed failure whose message is safe to print. It never includes the URL."""


def plain_text(value, limit):
    """Strip tags and control characters, then cap the length."""
    if not isinstance(value, str):
        value = ""
    text = html.unescape(value)
    text = _TAG.sub(" ", text)
    text = _ANY_TAG.sub(" ", text)
    text = html.unescape(text)
    text = _ANY_TAG.sub(" ", text)
    text = _CONTROLS.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0]
        text = (cut or text[:limit]).rstrip() + "…"
    return text


def valid_http_url(url):
    """True only for an http or https URL with a host. javascript: and data: are rejected."""
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


def embed_json(obj):
    """JSON for a script data block. Raw < is escaped so the script tag cannot be closed early."""
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def source_hash(content):
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def read_limited(path, limit=MAX_DATA_BYTES):
    data = path.read_bytes()
    if len(data) > limit:
        raise SystemExit(f"{path.name} is larger than {limit} bytes")
    return data.decode("utf-8")


def load_yaml(path):
    try:
        data = yaml.safe_load(read_limited(path))
    except yaml.YAMLError as ex:
        detail = _CONTROLS.sub(" ", str(ex))[:300]
        raise SystemExit(f"Could not read {path.name}: {detail}") from None
    return data


def bounded_int(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise SystemExit(f"config.yml {name} must be a whole number")
    if not low <= value <= high:
        raise SystemExit(f"config.yml {name} must be between {low} and {high}")
    return value


def load_config(path):
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise SystemExit("config.yml must be a set of named settings")
    title = plain_text(data.get("title"), 120)
    if not title:
        raise SystemExit("config.yml needs a title")
    timezone_name = data.get("timezone")
    if not isinstance(timezone_name, str) or not re.fullmatch(r"[A-Za-z0-9_+/-]{1,64}", timezone_name):
        raise SystemExit("config.yml timezone must be a name like Europe/London")
    locale = data.get("locale")
    if not isinstance(locale, str) or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", locale):
        raise SystemExit("config.yml locale must look like en-GB")
    return dict(
        title=title,
        per_feed_cap=bounded_int(data.get("per_feed_cap"), "per_feed_cap", 1, 30),
        max_age_days=bounded_int(data.get("max_age_days"), "max_age_days", 1, 365),
        refresh_hours=bounded_int(data.get("refresh_hours"), "refresh_hours", 1, 168),
        timezone=timezone_name,
        locale=locale,
    )


def text_field(feed, key, limit, required):
    if key not in feed or feed[key] is None:
        value = ""
    elif not isinstance(feed[key], str):
        raise SystemExit("feeds.yml name, url, region, and country must be text. Put quotes around them.")
    else:
        value = feed[key]
    if key == "url":
        return value.strip()
    cleaned = plain_text(value, limit)
    if required and not cleaned:
        raise SystemExit("feeds.yml is missing a name")
    return cleaned


def load_feeds(path):
    data = load_yaml(path)
    if not isinstance(data, dict) or not isinstance(data.get("topics"), list) or not data["topics"]:
        raise SystemExit("feeds.yml must contain a topics list")
    feeds, topics = [], []
    for topic in data["topics"]:
        if not isinstance(topic, dict):
            raise SystemExit("feeds.yml has a topic that is not a group")
        name = text_field(topic, "name", 80, True)
        if name in topics:
            raise SystemExit(f"feeds.yml repeats the topic {name}")
        children = topic.get("feeds")
        if not isinstance(children, list) or not children:
            raise SystemExit(f"feeds.yml topic {name} needs a feeds list")
        topics.append(name)
        for feed in children:
            if not isinstance(feed, dict):
                raise SystemExit(f"feeds.yml topic {name} has an entry that is not a name and url")
            feed_name = text_field(feed, "name", 120, True)
            url = text_field(feed, "url", 2000, True)
            if not feed_name or not url:
                raise SystemExit(f"feeds.yml topic {name} has a feed missing a name or url")
            feeds.append(dict(
                topic=name,
                name=feed_name,
                url=url,
                region=text_field(feed, "region", 80, False),
                country=text_field(feed, "country", 80, False),
            ))
    if not feeds:
        raise SystemExit("feeds.yml has no feeds")
    return feeds, topics


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        joined = urllib.parse.urljoin(req.full_url, newurl)
        if not valid_http_url(joined):
            raise FetchError("failed (redirect blocked)")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_get(url, agent, timeout, max_bytes):
    if not valid_http_url(url):
        raise FetchError("failed (unsupported URL)")
    request = urllib.request.Request(url, headers={
        "User-Agent": agent,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.1",
    })
    opener = urllib.request.build_opener(_SafeRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            final = response.geturl()
            if not valid_http_url(final):
                raise FetchError("failed (redirect blocked)")
            status = getattr(response, "status", 200) or 200
            announced = response.headers.get("Content-Length")
            if announced:
                try:
                    if int(announced) > max_bytes:
                        raise FetchError("failed (response too large)")
                except ValueError:
                    pass
            chunks, total = [], 0
            while True:
                block = response.read(64 * 1024)
                if not block:
                    break
                total += len(block)
                if total > max_bytes:
                    raise FetchError("failed (response too large)")
                chunks.append(block)
            return b"".join(chunks), int(status)
    except FetchError:
        raise
    except urllib.error.HTTPError as ex:
        raise FetchError(f"failed (HTTP {ex.code})") from None
    except urllib.error.URLError as ex:
        reason = ex.reason
        if isinstance(reason, FetchError):
            raise reason from None
        name = type(reason).__name__ if isinstance(reason, BaseException) else "URLError"
        raise FetchError(f"failed ({name})") from None


def extract_items(feed, body, status, cap, max_age):
    if status >= 400:
        return [], f"failed (HTTP {status})"
    try:
        parsed = feedparser.parse(body)
    except Exception:
        return [], "failed (parse error)"
    entries = list(getattr(parsed, "entries", []) or [])[:MAX_ENTRIES_SCANNED]
    if not entries:
        return [], "failed (no items)"
    now = time.time()
    items = []
    for entry in entries:
        link = entry.get("link")
        if not isinstance(link, str) or not valid_http_url(link):
            continue
        link = link.strip()
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        if not stamp:
            continue
        try:
            ts = int(calendar.timegm(stamp))
        except (TypeError, ValueError, OverflowError):
            continue
        if ts > now + 86400:
            ts = int(now)
        title = plain_text(entry.get("title"), 200) or link
        summary = plain_text(entry.get("summary"), 220)
        items.append(dict(
            title=title, url=link, summary=summary, ts=ts, topic=feed["topic"],
            source=feed["name"], country=feed["country"], region=feed["region"], tag="",
        ))
    items.sort(key=lambda item: -item["ts"])
    if not items:
        return [], "failed (no dated items)"
    latest = items[0]["ts"]
    if now - latest > max_age * 86400:
        when = time.strftime("%Y-%m-%d", time.gmtime(latest))
        return items[:2], f"stale (latest {when})"
    fresh = [item for item in items if now - item["ts"] <= max_age * 86400]
    return fresh[:cap], "ok"


def fetch(feed, cfg, deadline):
    if not valid_http_url(feed["url"]):
        return feed, [], "failed (unsupported URL)"
    last_items, last_status = [], "failed (no items)"
    for agent in (UA, UA_FALLBACK):
        if time.monotonic() > deadline:
            return feed, [], "failed (run timeout)"
        try:
            body, status = http_get(feed["url"], agent, REQUEST_TIMEOUT_SECONDS, MAX_RESPONSE_BYTES)
            items, status_text = extract_items(
                feed, body, status, cfg["per_feed_cap"], cfg["max_age_days"]
            )
        except FetchError as ex:
            last_items, last_status = [], str(ex)
            continue
        except Exception as ex:
            last_items, last_status = [], f"failed ({type(ex).__name__})"
            continue
        if status_text == "ok" or status_text.startswith("stale"):
            return feed, items, status_text
        last_items, last_status = items, status_text
    return feed, last_items, last_status


def fetch_all(feeds, cfg):
    deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS
    socket.setdefaulttimeout(REQUEST_TIMEOUT_SECONDS)
    if not feeds:
        return []
    results = []
    pool = ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(feeds)))
    try:
        futures = {pool.submit(fetch, feed, cfg, deadline): feed for feed in feeds}
        pending = set(futures)
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            done, pending = wait(pending, timeout=remaining, return_when=FIRST_COMPLETED)
            if not done:
                break
            for fut in done:
                feed = futures[fut]
                try:
                    results.append(fut.result())
                except Exception as ex:
                    results.append((feed, [], f"failed ({type(ex).__name__})"))
        for fut in list(pending):
            feed = futures[fut]
            if fut.done():
                try:
                    results.append(fut.result())
                except Exception as ex:
                    results.append((feed, [], f"failed ({type(ex).__name__})"))
            else:
                fut.cancel()
                results.append((feed, [], "failed (run timeout)"))
        return results
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def saved_items(path):
    if not path.exists():
        return []
    try:
        data = json.loads(read_limited(path))
    except json.JSONDecodeError:
        raise SystemExit("saved-links.json is not valid JSON") from None
    links = data.get("links") if isinstance(data, dict) else None
    if not isinstance(links, list):
        raise SystemExit("saved-links.json must contain a links list")
    items = []
    for entry in links:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        if not valid_http_url(url):
            print("  SKIP saved link with a non-http(s) address")
            continue
        url = url.strip()
        added = entry.get("added") if isinstance(entry.get("added"), str) else ""
        try:
            ts = int(calendar.timegm(time.strptime(added, "%Y-%m-%d")))
        except (TypeError, ValueError, OverflowError):
            ts = int(time.time())
        title = plain_text(entry.get("title"), 200) or url
        note = plain_text(entry.get("note"), 500)
        tag = plain_text(entry.get("topic"), 80)
        items.append(dict(
            title=title, url=url, summary=note, ts=ts, topic=SAVED_LABEL, tag=tag,
            source=SAVED_LABEL, country="", region="",
        ))
    return items


def zoned_now(name):
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(name))
    except Exception:
        print(f"WARNING: timezone {name} is unavailable here, so the clock line uses UTC")
        return datetime.now(timezone.utc)


def dead_section(dead):
    if not dead:
        return ""
    rows = []
    for item in dead:
        rows.append(
            "<li>%s (%s): %s</li>" % (
                html.escape(item["name"], quote=True),
                html.escape(item["topic"], quote=True),
                html.escape(item["status"], quote=True),
            )
        )
    return (
        '<details><summary>Feeds needing attention (%d)</summary><ul>%s</ul></details>'
        % (len(dead), "".join(rows))
    )


def security_header():
    data = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    for group in data.get("headers", []):
        for header in group.get("headers", []):
            if str(header.get("key", "")).lower() == "content-security-policy":
                return str(header.get("value", ""))
    raise SystemExit("vercel.json is missing a Content-Security-Policy header")


def assert_policy(css, js):
    policy = security_header()
    style_hash = source_hash(css)
    script_hash = source_hash(js)
    required = [
        "default-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'self'",
        f"script-src '{script_hash}'",
        f"style-src '{style_hash}'",
    ]
    missing = [piece for piece in required if piece not in policy]
    if missing:
        raise SystemExit(
            "vercel.json Content-Security-Policy does not match the inline style and script. "
            "Missing: " + "; ".join(missing)
        )
    if "'unsafe-inline'" in policy or "'unsafe-eval'" in policy or "*" in policy:
        raise SystemExit("vercel.json Content-Security-Policy is too loose")
    if "noopener noreferrer" not in js:
        raise SystemExit("library.js must set rel=noopener noreferrer on links")


def assert_portable(page):
    if re.search(r"""(?:href|src)\s*=\s*["']/(?!/)""", page):
        raise SystemExit("root-relative URL in the page")
    if re.search(r"""fetch\(\s*["']/""", page) or re.search(r"""url\(\s*["']?/""", page):
        raise SystemExit("root-relative asset URL in the page")


def render_page(cfg, feed_count, items, dead, css, js):
    assert_policy(css, js)
    template = (ROOT / "assets" / "page.html").read_text(encoding="utf-8")
    tokens_found = set(re.findall(r"%%([A-Z]+)%%", template))
    expected = {"LANG", "TITLE", "BUILT", "COUNT", "FEEDS", "CAP", "AGE", "HOURS", "DEAD", "DATA", "STYLE", "SCRIPT"}
    if tokens_found != expected:
        raise SystemExit("assets/page.html placeholders changed")
    safe_items = []
    for item in items:
        url = item.get("url", "")
        if not valid_http_url(url):
            continue
        if url.strip().startswith("/") and not url.strip().startswith("//"):
            raise SystemExit("root-relative article URL")
        safe_items.append(dict(
            title=plain_text(item.get("title"), 200) or url.strip(),
            url=url.strip(),
            summary=plain_text(item.get("summary"), 500),
            ts=int(item.get("ts") or 0),
            topic=plain_text(item.get("topic"), 80),
            source=plain_text(item.get("source"), 120),
            country=plain_text(item.get("country"), 80),
            region=plain_text(item.get("region"), 80),
            tag=plain_text(item.get("tag"), 80),
        ))
    built = zoned_now(cfg["timezone"]).strftime("%a %d %b %Y, %H:%M") + " " + cfg["timezone"]
    payload = {
        "locale": cfg["locale"],
        "timezone": cfg["timezone"],
        "savedLabel": SAVED_LABEL,
        "topics": [SAVED_LABEL] + list(cfg["topics"]),
        "items": safe_items,
    }
    values = {
        "LANG": html.escape(cfg["locale"], quote=True),
        "TITLE": html.escape(cfg["title"], quote=True),
        "BUILT": html.escape(built, quote=True),
        "COUNT": str(len(safe_items)),
        "FEEDS": str(int(feed_count)),
        "CAP": str(cfg["per_feed_cap"]),
        "AGE": str(cfg["max_age_days"]),
        "HOURS": str(cfg["refresh_hours"]),
        "DEAD": dead_section(dead),
        "DATA": embed_json(payload),
        "STYLE": css,
        "SCRIPT": js,
    }

    def replace(match):
        return values[match.group(1)]

    page = re.sub(r"%%([A-Z]+)%%", replace, template)
    assert_portable(page)
    if "<" in values["DATA"]:
        raise SystemExit("embedded JSON still contains a raw <")
    return page, safe_items, built


def write_site(out, page, built, items, dead):
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "items.json").write_text(
        json.dumps({"built": built, "items": items, "dead": dead}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "_site"))
    parser.add_argument("--cap", type=int, default=None)
    parser.add_argument("--max-age-days", type=int, default=None)
    args = parser.parse_args()
    cfg = load_config(ROOT / "config.yml")
    if args.cap is not None:
        cfg["per_feed_cap"] = bounded_int(args.cap, "per_feed_cap", 1, 30)
    if args.max_age_days is not None:
        cfg["max_age_days"] = bounded_int(args.max_age_days, "max_age_days", 1, 365)
    feeds, topics = load_feeds(ROOT / "feeds.yml")
    cfg["topics"] = topics
    results = fetch_all(feeds, cfg)
    items, dead = [], []
    for feed, found, status in results:
        items.extend(found)
        if status != "ok":
            dead.append(dict(name=feed["name"], topic=feed["topic"], url=feed["url"], status=status))
    dead.sort(key=lambda item: (item["topic"].lower(), item["name"].lower()))
    seen, uniq = set(), []
    for item in sorted(saved_items(ROOT / "saved-links.json") + items, key=lambda item: -item["ts"]):
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        item.pop("newsletter", None)
        uniq.append(item)
    css = (ROOT / "assets" / "library.css").read_text(encoding="utf-8")
    js = (ROOT / "assets" / "library.js").read_text(encoding="utf-8")
    page, safe_items, built = render_page(cfg, len(feeds), uniq, dead, css, js)
    write_site(Path(args.out), page, built, safe_items, dead)
    print(f"Built {built}: {len(safe_items)} articles from {len(feeds)} feeds")
    counts = {topic: sum(item["topic"] == topic for item in safe_items) for topic in [SAVED_LABEL] + topics}
    for topic, count in counts.items():
        print(f"  {topic}: {count}")
    if dead:
        print(f"WARNING: {len(dead)} feed(s) need attention")
    for item in dead:
        print(f"  DEAD/STALE: {item['name']} [{item['topic']}] {item['status']}")


if __name__ == "__main__":
    main()
