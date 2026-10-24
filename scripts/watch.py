#!/usr/bin/env python3
"""Change detection for Pocket Advisor's scheduled check-ins. Standard library only, Python 3.9+.

  rules   Fetch each watched page, compare it with the copy saved last time, and print what changed.
          python3 scripts/watch.py rules --watchlist ~/.config/pocket-advisor/watchlist.json
          python3 scripts/watch.py rules --sample
  seen    Remember items a check-in already handled, so the student is never texted twice about one thing.
          python3 scripts/watch.py seen --kind email --id "<message id>"     exit 0 = pending, 1 = handled; --mark acknowledges successful handling
  add     Add a page to the watchlist.
          python3 scripts/watch.py add --name "ISSC CPT" --url https://issc.asu.edu/f-1j-1-students/employment/f1-cpt

State lives in ~/.config/pocket-advisor/ (kept across restarts and Skill updates).
Exit codes for rules: 0 checked (changes or not), 2 bad input, 4 at least one page could not be fetched.
"""

import argparse
import difflib
import hashlib
import json
import re
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
STATE = Path.home() / ".config" / "pocket-advisor"
UA = "Mozilla/5.0 (compatible; PocketAdvisor/1.0; +https://github.com/aksharareddyshetty/pocket-advisor)"


def fail(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(2)


class TextOnly(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "svg", "form"}
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "tr", "br", "section", "article", "td", "th"}

    def __init__(self):
        super().__init__()
        self.out, self.depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.depth:
            self.out.append(data)


def page_text(html):
    p = TextOnly()
    p.feed(html)
    lines = (re.sub(r"\s+", " ", line).strip() for line in "".join(p.out).splitlines())
    # Short table cells (20 vs 40 hours) and dates can be consequential changes.
    return "\n".join(line for line in lines if line)


def fetch(url):
    if not url.startswith("https://"):
        raise ValueError("only https:// pages can be watched")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


def load_watchlist(path):
    try:
        items = json.loads(Path(path).read_text())
    except FileNotFoundError:
        fail(f"no watchlist at {path}; add pages with: python3 scripts/watch.py add --name ... --url ...")
    except json.JSONDecodeError as e:
        fail(f"{path} is not valid JSON: {e}")
    if not isinstance(items, list) or not all("url" in i for i in items):
        fail("the watchlist must be a JSON list of {name, url}")
    return items


def rules(args):
    if args.sample:
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "snapshots"
            name, url = "Sample: school CPT page", "https://example.edu/cpt"
            compare(state, name, url, (ASSETS / "sample_page_before.html").read_text())
            report = compare(state, name, url, (ASSETS / "sample_page_after.html").read_text())
            return print_report(args, [report], [])

    state = STATE / "snapshots"
    reports, errors = [], []
    for item in load_watchlist(args.watchlist):
        name = item.get("name", item["url"])
        try:
            html = fetch(item["url"])
        except Exception as e:  # network errors, HTTP errors, bad URLs
            errors.append({"name": name, "url": item["url"], "error": str(e)[:160]})
            continue
        try:
            reports.append(compare(state, name, item["url"], html))
        except ValueError as e:
            errors.append({"name": name, "url": item["url"], "error": str(e)})
    print_report(args, reports, errors)
    if errors:
        sys.exit(4)


def compare(state, name, url, html):
    state.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    snap = state / f"{key}.txt"
    meta = state / f"{key}.json"
    new = page_text(html)
    if not new.strip():
        raise ValueError("page has no readable content; baseline was not changed")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not snap.exists():
        atomic_text(snap, new)
        atomic_json(meta, {"name": name, "url": url, "first_seen": now, "last_changed": None})
        return {"name": name, "url": url, "status": "baseline"}
    old = snap.read_text()
    if old == new:
        (state / f"{key}.pending.json").unlink(missing_ok=True)
        return {"name": name, "url": url, "status": "unchanged"}
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0))
    added = [l[1:] for l in diff[2:] if l.startswith("+")]
    removed = [l[1:] for l in diff[2:] if l.startswith("-")]
    revision = hashlib.sha256(new.encode()).hexdigest()
    # Keep the acknowledged baseline until Cubbie has reviewed the full diff.
    pending = state / f"{key}.pending.json"
    atomic_json(pending, {"name": name, "url": url, "revision": revision, "text": new})
    return {"name": name, "url": url, "status": "changed", "revision": revision,
            "added": added, "removed": removed, "more": 0}


def atomic_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(value)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value))


def ack(args):
    state = STATE / "snapshots"
    key = hashlib.sha1(args.url.encode()).hexdigest()[:16]
    pending = state / f"{key}.pending.json"
    if not pending.exists():
        fail("no pending change for that URL")
    info = json.loads(pending.read_text())
    if info["revision"] != args.revision:
        fail("page changed again; review the latest diff before acknowledging")
    snap = state / f"{key}.txt"
    # The pending revision is durable, so an interruption here is safe to retry.
    atomic_text(snap, info["text"])
    atomic_json(state / f"{key}.json", {"name": info["name"], "url": args.url,
                "last_reviewed": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    pending.unlink()
    print("Reviewed change acknowledged.")


def print_report(args, reports, errors):
    if args.json:
        print(json.dumps({"pages": reports, "errors": errors}, indent=2))
        return
    changed = [r for r in reports if r["status"] == "changed"]
    if not changed:
        base = sum(1 for r in reports if r["status"] == "baseline")
        print(f"No changes on {len(reports)} watched pages" + (f" ({base} saved for the first time)." if base else "."))
    for r in changed:
        print(f"CHANGED: {r['name']}\n{r['url']}\nRevision: {r['revision']}")
        for l in r["added"]:
            print(f"  + {l}")
        for l in r["removed"]:
            print(f"  - {l}")
        if r["more"]:
            print(f"  ({r['more']} more changed lines)")
    for e in errors:
        print(f"Could not check {e['name']}: {e['error']}")


def seen(args):
    if not args.id or not args.kind:
        fail("give --kind and --id")
    path = STATE / "seen.json"
    STATE.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() else {}
    bucket = data.setdefault(args.kind, {})
    if args.id in bucket:
        print(f"Already handled on {bucket[args.id]}.")
        sys.exit(1)
    pending_path = STATE / "pending-items.json"
    pending = json.loads(pending_path.read_text()) if pending_path.exists() else {}
    waiting = pending.setdefault(args.kind, {})
    if not args.mark:
        waiting.setdefault(args.id, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        atomic_json(pending_path, pending)
        print("Pending. Process this item, then run seen with --mark only after successful handling.")
        return
    bucket[args.id] = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    if len(bucket) > 500:
        for k in sorted(bucket, key=bucket.get)[: len(bucket) - 500]:
            del bucket[k]
    # Save completion first: a crash before queue cleanup cannot redeliver it.
    atomic_json(path, data)
    waiting.pop(args.id, None)
    atomic_json(pending_path, pending)
    print("Handled. Recorded.")


def pending_items(args):
    path = STATE / "pending-items.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    handled_path = STATE / "seen.json"
    handled = json.loads(handled_path.read_text()) if handled_path.exists() else {}
    print(json.dumps([item for item in data.get(args.kind, {})
                      if item not in handled.get(args.kind, {})]))


def add(args):
    if not args.url or not args.url.startswith("https://"):
        fail("--url must start with https://")
    path = Path(args.watchlist)
    path.parent.mkdir(parents=True, exist_ok=True)
    items = json.loads(path.read_text()) if path.exists() else []
    if any(i["url"] == args.url for i in items):
        print("Already watched.")
        return
    items.append({"name": args.name or args.url, "url": args.url})
    path.write_text(json.dumps(items, indent=2))
    print(f"Watching {len(items)} pages.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    default_list = str(STATE / "watchlist.json")

    sp = sub.add_parser("rules")
    sp.add_argument("--watchlist", default=default_list)
    sp.add_argument("--sample", action="store_true", help="compare two bundled pages; saves nothing")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=rules)

    sp = sub.add_parser("seen")
    sp.add_argument("--kind", help="email, calendar, canvas, rule ...")
    sp.add_argument("--id")
    sp.add_argument("--mark", action="store_true", help="acknowledge only after successful handling")
    sp.set_defaults(fn=seen)

    sp = sub.add_parser("pending")
    sp.add_argument("--kind", required=True)
    sp.set_defaults(fn=pending_items)

    sp = sub.add_parser("ack")
    sp.add_argument("--url", required=True)
    sp.add_argument("--revision", required=True)
    sp.set_defaults(fn=ack)

    sp = sub.add_parser("add")
    sp.add_argument("--name")
    sp.add_argument("--url")
    sp.add_argument("--watchlist", default=default_list)
    sp.set_defaults(fn=add)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
