#!/usr/bin/env python3
"""Check a tab-separated list of feeds before you add them.

Usage:
  python tools/test_feeds.py CANDIDATES.tsv RESULTS.json

Columns, separated by tabs: topic, region, country, name, url
Lines that are empty or start with # are skipped.
A feed passes when it responds, parses, looks like English, and has an item
from the last 30 days. RESULTS.json is written beside the run. Do not commit it.
"""
import calendar
import json
import re
import sys
import time
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.build import (  # noqa: E402
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT_SECONDS,
    UA,
    http_get,
    valid_http_url,
)

STOP = set("the a an and of to in for on with is are was at by from how why what new its as be".split())
NOW = time.time()


def english(parsed):
    lang = (parsed.feed.get("language") or "").lower()
    titles = " ".join(entry.get("title", "") for entry in parsed.entries[:15]).lower()
    words = re.findall(r"[a-z']+", titles)
    ratio = sum(word in STOP for word in words) / max(1, len(words))
    note = f"lang={lang or '-'} ratio={ratio:.2f}"
    if lang and not lang.startswith("en") and ratio < 0.08:
        return False, note
    return ratio >= 0.05 or lang.startswith("en"), note


def check(row):
    result = dict(row)
    if not valid_http_url(row["url"]):
        result["result"] = "unsupported URL"
        return result
    try:
        body, status = http_get(row["url"], UA, REQUEST_TIMEOUT_SECONDS, MAX_RESPONSE_BYTES)
        result["http"] = status
        if status >= 400:
            result["result"] = f"HTTP {status}"
            return result
        parsed = feedparser.parse(body)
        if not parsed.entries:
            result["result"] = "no items / not a feed"
            return result
        stamps = []
        for entry in parsed.entries:
            stamp = entry.get("published_parsed") or entry.get("updated_parsed")
            if not stamp:
                continue
            try:
                stamps.append(calendar.timegm(stamp))
            except (TypeError, ValueError, OverflowError):
                continue
        latest = max(stamps) if stamps else None
        ok_en, note = english(parsed)
        result.update(
            items=len(parsed.entries),
            latest=time.strftime("%Y-%m-%d", time.gmtime(latest)) if latest else None,
            lang=note,
        )
        if not ok_en:
            result["result"] = "not English"
        elif not latest:
            result["result"] = "no dates"
        elif NOW - latest > 30 * 86400:
            result["result"] = f"stale (latest {result['latest']})"
        else:
            result["result"] = "OK"
    except Exception as ex:
        result["result"] = f"error: {type(ex).__name__}"
    return result


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python tools/test_feeds.py CANDIDATES.tsv RESULTS.json")
    rows = []
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        rows.append(dict(
            topic=parts[0], region=parts[1], country=parts[2], name=parts[3], url=parts[4],
        ))
    results = [check(row) for row in rows]
    Path(sys.argv[2]).write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    for row in results:
        if row["result"] != "OK":
            print(f'{row["topic"][:18]:18} {row["name"][:38]:38} {row["result"]}  {row.get("lang", "")}')
    print("OK:", sum(row["result"] == "OK" for row in results), "/", len(results))


if __name__ == "__main__":
    main()
