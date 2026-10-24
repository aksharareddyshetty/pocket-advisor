#!/usr/bin/env python3
"""Find the exact moment in an expert's video that answers a student's question.

Cubbie finds candidate videos (immigration attorneys, school international offices) with a web search and passes
their YouTube IDs here. The script reads each transcript, scores 45-second windows against the question, and prints
the best moments with a link that starts playback right there.

  ~/.local/share/venvs/pocket-advisor/bin/python scripts/clips.py --question "can I do CPT in my first year" --video ID [--video ID ...]
  python3 scripts/clips.py --question "..." --transcript FILE --video-id ID     (transcript copied from the page)
  python3 scripts/clips.py --sample

Transcript files: JSON list of {start, text} (start in seconds), or text lines like "12:34 words..." or
"1:02:03 words...". Fetching by ID needs the youtube-transcript-api package (see SKILL.md Setup).

Exit codes: 0 found, 2 bad input, 4 no transcript could be read, 5 nothing in the transcripts matches.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
WINDOW = 45  # seconds per candidate clip
STOP = set("""a an the and or but if of to in on at for with from by is are was were be been am do does did i me my
we you your it its this that these those can could would should will shall may might must have has had not no so
what when where which who how why about into than then there here just also very really get got go going
okay ok um uh like yeah right know mean thing things lot""".split())
SYNONYMS = {
    "cpt": ["curricular", "practical"], "opt": ["optional", "practical"], "stem": ["extension"],
    "job": ["work", "employment", "employer"], "work": ["job", "employment"], "intern": ["internship"],
    "internship": ["intern", "cpt"], "visa": ["status"], "status": ["visa"], "i20": ["i-20"],
    "ead": ["card", "authorization"], "travel": ["signature", "reentry"], "unemployed": ["unemployment"],
    "freelance": ["self-employed", "1099"], "remote": ["online", "abroad"],
}


def fail(msg, code=2):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


def words(text):
    toks = re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower().replace("i-20", "i20"))
    return [t for t in toks if t not in STOP and len(t) > 1]


def clock(seconds):
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def parse_transcript_file(path):
    raw = Path(path).read_text()
    try:
        data = json.loads(raw)
        return [{"start": float(d["start"]), "text": str(d["text"])} for d in data]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    out = []
    for line in raw.splitlines():
        m = re.match(r"\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s+(.*)", line)
        if m:
            h, mnt, sec, text = m.groups()
            out.append({"start": int(h or 0) * 3600 + int(mnt) * 60 + int(sec), "text": text})
        elif out and line.strip():
            out[-1]["text"] += " " + line.strip()
    if not out:
        fail(f"{path} has no timestamps; use JSON [{{start, text}}] or lines like '12:34 text'")
    return out


def fetch_transcript(video_id):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None, "youtube-transcript-api is not installed (see Setup)"
    try:
        t = YouTubeTranscriptApi().fetch(video_id, languages=("en", "en-US"))
        return [{"start": s.start, "text": s.text} for s in t.snippets], None
    except Exception as e:  # disabled transcripts, private videos, network blocks
        return None, f"{type(e).__name__}"


def best_windows(snippets, question, top):
    q = words(question)
    want = set(q)
    for t in q:
        want.update(SYNONYMS.get(t, []))
    if not want:
        fail("the question has no searchable words")
    windows = []
    for i, s in enumerate(snippets):
        end = s["start"] + WINDOW
        chunk = [x for x in snippets[i:i + 40] if x["start"] < end]
        text = " ".join(x["text"] for x in chunk)
        toks = words(text)
        if not toks:
            continue
        hits = {t for t in toks if t in want}
        exact = sum(1 for t in set(q) if t in toks)
        score = len(hits) + 2 * exact + 0.1 * sum(1 for t in toks if t in want)
        windows.append((score, s["start"], text))
    windows.sort(key=lambda w: w[0], reverse=True)
    picked = []
    for w in windows:
        if w[0] <= 1:
            break
        if all(abs(w[1] - p[1]) > WINDOW for p in picked):
            picked.append(w)
        if len(picked) == top:
            break
    return picked


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--question")
    ap.add_argument("--video", action="append", default=[], help="YouTube video ID; repeat for several")
    ap.add_argument("--transcript", help="transcript file instead of fetching")
    ap.add_argument("--video-id", help="the video ID the --transcript file belongs to, for the link")
    ap.add_argument("--top", type=int, default=2, help="moments per video")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.sample:
        args.question = "Can I do CPT in my first year?"
        args.transcript = str(ASSETS / "sample_transcript.txt")
        args.video_id = "SAMPLE00000"
    if not args.question:
        fail("give --question")

    sources = []
    if args.transcript:
        sources.append((args.video_id or "unknown", parse_transcript_file(args.transcript), None))
    for vid in args.video:
        snippets, err = fetch_transcript(vid)
        sources.append((vid, snippets, err))
    if not sources:
        fail("give --video ID or --transcript FILE")

    results, problems = [], []
    for vid, snippets, err in sources:
        if snippets is None:
            problems.append({"video": vid, "error": err})
            continue
        for score, start, text in best_windows(snippets, args.question, args.top):
            results.append({"video": vid, "start": int(start), "at": clock(start),
                            "link": f"https://www.youtube.com/watch?v={vid}&t={int(start)}s",
                            "score": round(score, 1), "excerpt": text[:600]})
    results.sort(key=lambda r: r["score"], reverse=True)

    if args.json:
        print(json.dumps({"moments": results, "unreadable": problems}, indent=2))
    else:
        for r in results:
            print(f"{r['at']} in {r['video']} (score {r['score']})\n{r['link']}\n  \"{r['excerpt'][:300]}\"\n")
        for p in problems:
            print(f"Couldn't read the transcript for {p['video']}: {p['error']}")
    if not any(s is not None for _, s, _ in sources):
        sys.exit(4)
    if not results:
        sys.exit(5)


if __name__ == "__main__":
    main()
