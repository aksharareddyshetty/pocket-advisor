#!/usr/bin/env python3
"""Change detection for Pocket Advisor's scheduled check-ins. Standard library only, Python 3.9+.

  rules   Fetch each watched page, compare it with the copy saved last time, and print what changed.
          python3 scripts/watch.py rules --watchlist ~/.config/pocket-advisor/watchlist.json
          python3 scripts/watch.py rules --sample
  seen    Remember items a check-in already handled, so the student is never texted twice about one thing.
          python3 scripts/watch.py seen --kind email --id "<message id>"     exit 0 = new (now recorded), 1 = seen before
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
MAX_CHANGED_LINES = 12


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
    # Drop short boilerplate fragments and dates that change on every load.
    return "\n".join(l for l in lines if len(l) > 3 and not re.fullmatch(r"(last updated|updated)[: ].{0,40}", l, re.I))


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
        state = Path(tempfile.mkdtemp()) / "snapshots"
        pages = [("Sample: school CPT page", (ASSETS / "sample_page_before.html").read_text()),
                 ("Sample: school CPT page", (ASSETS / "sample_page_after.html").read_text())]
        reports = []
        for name, html in pages:
            reports = [compare(state, name, "https://example.edu/cpt", html)]
        return print_report(args, reports, [])

    state = STATE / "snapshots"
    reports, errors = [], []
    for item in load_watchlist(args.watchlist):
        name = item.get("name", item["url"])
        try:
            html = fetch(item["url"])
        except Exception as e:  # network errors, HTTP errors, bad URLs
            errors.append({"name": name, "url": item["url"], "error": str(e)[:160]})
            continue
        reports.append(compare(state, name, item["url"], html))
    print_report(args, reports, errors)
    if errors:
        sys.exit(4)


def compare(state, name, url, html):
    state.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    snap = state / f"{key}.txt"
    meta = state / f"{key}.json"
    new = page_text(html)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not snap.exists():
        snap.write_text(new)
        meta.write_text(json.dumps({"name": name, "url": url, "first_seen": now, "last_changed": None}))
        return {"name": name, "url": url, "status": "baseline"}
    old = snap.read_text()
    if old == new:
        return {"name": name, "url": url, "status": "unchanged"}
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0))
    added = [l[1:] for l in diff if l.startswith("+") and not l.startswith("+++")]
    removed = [l[1:] for l in diff if l.startswith("-") and not l.startswith("---")]
    snap.write_text(new)
    info = json.loads(meta.read_text()) if meta.exists() else {"name": name, "url": url}
    info["last_changed"] = now
    meta.write_text(json.dumps(info))
    return {"name": name, "url": url, "status": "changed",
            "added": added[:MAX_CHANGED_LINES], "removed": removed[:MAX_CHANGED_LINES],
            "more": max(0, len(added) + len(removed) - 2 * MAX_CHANGED_LINES)}


def print_report(args, reports, errors):
    if args.json:
        print(json.dumps({"pages": reports, "errors": errors}, indent=2))
        return
    changed = [r for r in reports if r["status"] == "changed"]
    if not changed:
        base = sum(1 for r in reports if r["status"] == "baseline")
        print(f"No changes on {len(reports)} watched pages" + (f" ({base} saved for the first time)." if base else "."))
    for r in changed:
        print(f"CHANGED: {r['name']}\n{r['url']}")
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
    bucket[args.id] = datetime.now(timezone.utc).date().isoformat()
    # Keep the file small: the newest 500 per kind.
    if len(bucket) > 500:
        for k in sorted(bucket, key=bucket.get)[: len(bucket) - 500]:
            del bucket[k]
    path.write_text(json.dumps(data))
    print("New. Recorded.")


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
    sp.set_defaults(fn=seen)

    sp = sub.add_parser("add")
    sp.add_argument("--name")
    sp.add_argument("--url")
    sp.add_argument("--watchlist", default=default_list)
    sp.set_defaults(fn=add)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
