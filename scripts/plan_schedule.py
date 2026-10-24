#!/usr/bin/env python3
"""Pick class sections that fit a student's remaining requirements. Standard library only, Python 3.9+.

Cubbie gathers the inputs (degree audit, class search, calendar) and writes them to one JSON file; this script
only does the math: no time conflicts, under the credit cap, F-1 full-time rules met, and as many requirements
filled as possible, favoring classes that fill two requirements at once.

  python3 scripts/plan_schedule.py --input plan.json [--top 3] [--json]
  python3 scripts/plan_schedule.py --sample

Input fields (see assets/sample_plan.json):
  credit_cap        max credits this term without an overload petition (ASU: 18, Fulton engineering: 19)
  target_credits    optional, credits the student wants (default: credit_cap)
  min_credits       optional, full-time minimum to stay above (F-1 undergrad: 12)
  min_in_person     optional, in-person credits required (ASU F-1 undergrad: 9)
  max_online_credits optional, online credits that count toward full-time (F-1: 3)
  requirements      list of {id, label, courses_needed} still open on the degree audit
  must_take         optional, course codes the student has to take this term
  avoid_times       optional, list of {days, start, end, label} the student is busy (work, practice)
  sections          list of {course, title, section, credits, mode, days, start, end, satisfies, seats_open?}
                    days like "MWF" or "TTh"; times "HH:MM" 24-hour; satisfies lists requirement ids;
                    provide days/start/end, or meetings: [{days,start,end,start_date?,end_date?}];
                    use asynchronous:true only for confirmed online/icourse sections without meetings;
                    start_date/end_date bound the session (missing bounds conservatively overlap)

Exit codes: 0 done, 2 bad input, 3 no schedule fits.
"""

from datetime import date
import argparse
import json
import re
import sys
from pathlib import Path
from enrollment_rules import assess

ASSETS = Path(__file__).resolve().parent.parent / "assets"
IN_PERSON_MODES = {"in_person", "hybrid", "immersion"}
DAY_TOKENS = ["Th", "Tu", "Sa", "Su", "M", "T", "W", "R", "F", "S", "U"]
DAY_MAP = {"M": "M", "T": "T", "Tu": "T", "W": "W", "Th": "R", "R": "R", "F": "F",
           "Sa": "S", "S": "S", "Su": "U", "U": "U"}
MAX_NODES = 400_000


def fail(msg, code=2):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_days(text):
    days, rest = set(), (text or "").replace(" ", "").replace(",", "")
    while rest:
        for tok in DAY_TOKENS:
            if rest.startswith(tok):
                days.add(DAY_MAP[tok])
                rest = rest[len(tok):]
                break
        else:
            fail(f"can't read days {text!r}; use letters like MWF or TTh")
    return days


def minutes(hhmm, name):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", hhmm or "")
    if not m:
        fail(f"{name} must be HH:MM in 24-hour time, got {hhmm!r}")
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        fail(f"{name} is not a valid clock time")
    return hour * 60 + minute


def session_dates(item, name):
    try:
        first = date.fromisoformat(item["start_date"]) if item.get("start_date") else date.min
        last = date.fromisoformat(item["end_date"]) if item.get("end_date") else date.max
    except (TypeError, ValueError):
        fail(f"{name} session dates must be YYYY-MM-DD")
    if first > last:
        fail(f"{name} session must end on or after it starts")
    return first, last


def meeting(item, name):
    if not item.get("days"):
        fail(f"confirm meeting days and times for {name}")
    start = minutes(item.get("start"), f"{name} start")
    end = minutes(item.get("end"), f"{name} end")
    if end <= start:
        fail(f"{name} meeting must end after it starts")
    first, last = session_dates(item, name)
    days = parse_days(item["days"])
    if not days:
        fail(f"confirm meeting days for {name}")
    return (days, start, end, first, last)


def section_meetings(section):
    name = f"section {section['course']}"
    session_dates(section, name)
    if section.get("asynchronous") is True:
        if section.get("mode") not in {"online", "icourse"}:
            fail(f"{name}: only an explicitly asynchronous online section can have no meetings")
        if section.get("days") or section.get("meetings") or section.get("start") or section.get("end"):
            fail(f"{name}: asynchronous conflicts with supplied meeting times")
        return []
    if "meetings" not in section:
        return [meeting(section, name)]
    if any(section.get(key) for key in ("days", "start", "end")):
        fail(f"{name}: use meetings or top-level times, not both")
    items = section["meetings"]
    if not isinstance(items, list) or not items:
        fail(f"{name}: provide all lecture/lab meetings or confirm asynchronous delivery")
    result = []
    for item in items:
        if not isinstance(item, dict):
            fail(f"{name}: every meeting must contain days, start and end")
        merged = {key: section[key] for key in ("start_date", "end_date") if key in section}
        merged.update(item)
        first, last = session_dates(merged, name)
        parent_first, parent_last = session_dates(section, name)
        if first < parent_first or last > parent_last:
            fail(f"{name}: meeting dates fall outside its session")
        result.append(meeting(merged, name))
    return result


DAY_NUMBERS = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4, "S": 5, "U": 6}


def clash(a, b):
    for left in a:
        for right in b:
            common = left[0] & right[0]
            if not common or left[1] >= right[2] or right[1] >= left[2]:
                continue
            first, last = max(left[3], right[3]), min(left[4], right[4])
            if first > last:
                continue
            if any((DAY_NUMBERS[d] - first.weekday()) % 7 <= (last - first).days for d in common):
                return True
    return False


def meeting_text(meetings):
    if not meetings:
        return "online, no set time (confirmed asynchronous)"
    def clock(value):
        return f"{value // 60:02d}:{value % 60:02d}"
    descriptions = []
    for days, start, end, first, last in meetings:
        text = f"{''.join(d for d in DAY_NUMBERS if d in days)} {clock(start)}-{clock(end)}"
        if first != date.min and last != date.max:
            text += f" ({first.isoformat()} to {last.isoformat()})"
        descriptions.append(text)
    return "; ".join(descriptions)


def norm(code):
    return re.sub(r"\s+", "", code).upper()


def load(path):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        fail(f"file not found: {path}")
    except json.JSONDecodeError as e:
        fail(f"{path} is not valid JSON: {e}")


def plan(data, top):
    cap = float(data.get("credit_cap", 18))
    target = float(data.get("target_credits", cap))
    min_credits = float(data.get("min_credits", 0))
    min_in_person = float(data.get("min_in_person", 0))
    max_online = data.get("max_online_credits")
    reqs = {r["id"]: r for r in data.get("requirements", [])}
    need = {rid: int(r.get("courses_needed", 1)) for rid, r in reqs.items()}
    must = {norm(c) for c in data.get("must_take", [])}
    avoid = [[meeting(a, "avoid_times")] for a in data.get("avoid_times", [])]

    sections = []
    for i, s in enumerate(data.get("sections", [])):
        if s.get("seats_open") is not None and int(s["seats_open"]) <= 0:
            continue
        if (min_credits or min_in_person or max_online is not None) and s.get("mode") not in IN_PERSON_MODES | {"online", "icourse", "sync"}:
            fail(f"confirm delivery mode for {s['course']} before checking enrollment")
        m = section_meetings(s)
        if any(clash(m, a) for a in avoid):
            continue
        s = dict(s, _m=m, _code=norm(s["course"]), _i=i,
                 _sat=[r for r in s.get("satisfies", []) if r in reqs])
        sections.append(s)
    if not sections:
        fail("no open sections fit around the busy times", 3)

    by_course = {}
    for s in sections:
        by_course.setdefault(s["_code"], []).append(s)
    missing = must - set(by_course)
    if missing:
        fail("required courses have no open section fitting busy times: " + ", ".join(sorted(missing)), 3)
    courses = sorted(by_course, key=lambda c: (c not in must, -max(len(s["_sat"]) for s in by_course[c])))

    def score(chosen):
        filled = {rid: 0 for rid in need}
        for s in chosen:
            for rid in s["_sat"]:
                filled[rid] += 1
        covered = sum(min(filled[r], need[r]) for r in need)
        doubles = sum(1 for s in chosen if sum(1 for r in s["_sat"] if filled[r] <= need[r]) >= 2)
        credits = sum(float(s["credits"]) for s in chosen)
        musts = sum(1 for s in chosen if s["_code"] in must)
        return (musts, covered, doubles, -abs(target - credits), -len(chosen))

    def rules_ok(chosen):
        if not must.issubset({s["_code"] for s in chosen}):
            return False
        credits = sum(float(s["credits"]) for s in chosen)
        in_person = sum(float(s["credits"]) for s in chosen if s.get("mode", "unknown") in IN_PERSON_MODES)
        online = sum(float(s["credits"]) for s in chosen if s.get("mode") in {"online", "icourse", "sync"})
        if (min_credits or min_in_person or max_online is not None) and any(
                s.get("mode") not in IN_PERSON_MODES | {"online", "icourse", "sync"} for s in chosen):
            return False
        counted = in_person + (min(online, float(max_online)) if max_online is not None else online)
        return counted >= min_credits and in_person >= min_in_person

    best, nodes = [], 0

    def consider(chosen):
        sc = score(chosen)
        key = tuple(sorted(s["_i"] for s in chosen))
        if any(k == key for _, k, _ in best):
            return
        best.append((sc, key, list(chosen)))
        best.sort(key=lambda t: t[0], reverse=True)
        del best[top * 4:]

    def walk(idx, chosen, credits):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES:
            return
        if chosen and rules_ok(chosen):
            consider(chosen)
        for j in range(idx, len(courses)):
            for s in by_course[courses[j]]:
                c = float(s["credits"])
                if credits + c > cap:
                    continue
                if any(clash(s["_m"], t["_m"]) for t in chosen):
                    continue
                chosen.append(s)
                walk(j + 1, chosen, credits + c)
                chosen.pop()

    walk(0, [], 0.0)
    if not best:
        if nodes > MAX_NODES:
            fail("search limit reached; narrow the candidate sections and try again", 3)
        fail("no schedule meets required courses, conflicts, credit cap and enrollment totals; do not loosen visa rules without DSO approval", 3)

    # Keep plans that differ in their courses, not just sections.
    seen, picks = set(), []
    for sc, _, chosen in best:
        sig = frozenset(s["_code"] for s in chosen)
        if sig in seen:
            continue
        seen.add(sig)
        picks.append(chosen)
        if len(picks) == top:
            break

    out = []
    for chosen in picks:
        credits = sum(float(s["credits"]) for s in chosen)
        filled = {}
        for s in chosen:
            for rid in s["_sat"]:
                filled[rid] = filled.get(rid, 0) + 1
        still_open = [reqs[r].get("label", r) for r in need if filled.get(r, 0) < need[r]]
        in_person = sum(float(s["credits"]) for s in chosen if s.get("mode", "unknown") in IN_PERSON_MODES)
        chosen_codes = {s["_code"] for s in chosen}
        optional = []
        for code in courses:
            if code in chosen_codes:
                continue
            for s in by_course[code]:
                if credits + float(s["credits"]) <= cap and not any(clash(s["_m"], t["_m"]) for t in chosen):
                    optional.append({"course": s["course"], "section": s.get("section"),
                                     "credits": s["credits"], "fills": s["_sat"]})
                    break
        try:
            enrollment = assess(chosen, min_credits, min_in_person, max_online, data.get("term_start"), data.get("term_end")) if (min_credits or min_in_person or max_online is not None) else None
        except (ValueError, KeyError, TypeError) as exc:
            fail(f"invalid session data: {exc}")
        out.append({
            "enrollment_check": enrollment,
            "credits": credits,
            "in_person_credits": in_person,
            "room_under_cap": cap - credits,
            "classes": [{
                "course": s["course"], "title": s.get("title"), "section": s.get("section"),
                "credits": s["credits"], "mode": s.get("mode", "unknown"),
                "when": meeting_text(s["_m"]),
                "fills": [reqs[r].get("label", r) for r in s["_sat"] if filled[r] <= need[r]] or
                         [reqs[r].get("label", r) for r in s["_sat"]],
                "double_counts": sum(1 for r in s["_sat"] if filled[r] <= need[r]) >= 2,
            } for s in sorted(chosen, key=lambda s: s["course"])],
            "requirements_still_open": still_open,
            "optional_adds": optional[:5],
        })
    return {"plans": out, "must_take_unavailable": sorted(missing), "searched_all": nodes <= MAX_NODES}


def share_card(p):
    lines = ["My schedule (made with Pocket Advisor):"]
    for c in p["classes"]:
        lines.append(f"- {c['course']} sec {c['section']}, {c['when']}" if c.get("section") else f"- {c['course']}, {c['when']}")
    lines.append("Want to take one together? Send me yours and I'll check what fits.")
    return "\n".join(lines)


def text(result):
    lines = []
    if result["must_take_unavailable"]:
        lines.append("No open section fits for: " + ", ".join(result["must_take_unavailable"]))
    if not result["searched_all"]:
        lines.append("Search limit reached: these are candidate plans, not a complete search.")
    for n, p in enumerate(result["plans"], 1):
        check = p.get("enrollment_check")
        if check and check["full_time"] is not True:
            lines.append("Provisional: confirm session dates/rules and enrollment with your DSO before registering.")
            lines.extend("  - " + item for item in check["needs_information"] + check["problems"])
        lines.append(f"Option {n}: {p['credits']:g} credits ({p['in_person_credits']:g} in person), {p['room_under_cap']:g} under the cap")
        for c in p["classes"]:
            fills = f" fills {' + '.join(c['fills'])}" if c["fills"] else ""
            star = " (two for one)" if c["double_counts"] else ""
            lines.append(f"  - {c['course']} {c.get('title') or ''}, {c['when']}{fills}{star}".rstrip())
        if p["requirements_still_open"]:
            lines.append("  Still open after this: " + ", ".join(p["requirements_still_open"]))
        if p["optional_adds"]:
            lines.append("  Could also add: " + ", ".join(f"{o['course']} ({o['credits']} cr)" for o in p["optional_adds"]))
        lines.append("")
    lines.append("Share card for option 1:")
    lines.append(share_card(result["plans"][0]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", help="plan JSON file")
    ap.add_argument("--sample", action="store_true", help="use assets/sample_plan.json")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.input and not args.sample:
        fail("give --input FILE or --sample")
    data = load(ASSETS / "sample_plan.json" if args.sample else args.input)
    result = plan(data, max(1, args.top))
    if args.json:
        for p in result["plans"]:
            p["share_card"] = share_card(p)
        print(json.dumps(result, indent=2))
    else:
        print(text(result))


if __name__ == "__main__":
    main()
