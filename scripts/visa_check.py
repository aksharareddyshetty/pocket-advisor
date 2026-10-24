#!/usr/bin/env python3
"""Date and hours math for F-1 students. Standard library only, Python 3.9+.

Cubbie passes in everything (dates, shifts, courses); this script never reads accounts.
Every subcommand prints a short plain-text summary, or JSON with --json.
Exit codes: 0 done, 2 bad input.

  opt-window    --program-end DATE --today DATE [--school-lead-days 97]
  stem-window   --opt-end DATE --today DATE [--stem-i20-date DATE] [--school-lead-days 97]
  unemployment  --ead-start DATE --today DATE [--jobs FILE] [--stem]
  hours         --shifts FILE [--limit 20] [--break-limit 40] [--breaks START:END,...]
  enrollment    --courses FILE [--level undergrad|grad] [--min-credits N] [--min-in-person N]
                [--max-online-credits N] [--drop "COURSE"]
  travel        --signed DATE --return-date DATE --today DATE [--on-opt]
                [--i20-end DATE] [--ead-end DATE]

Add --sample to any subcommand to run it on the bundled files in assets/.
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"

IN_PERSON_MODES = {"in_person", "hybrid", "immersion"}


def fail(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(2)


def parse_date(value, name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        fail(f"{name} must be a date like 2027-05-08, got {value!r}")


def parse_datetime(value, name):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        fail(f"{name} must be a date and time like 2026-10-20T09:00, got {value!r}")


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        fail(f"file not found: {path}")
    except json.JSONDecodeError as e:
        fail(f"{path} is not valid JSON: {e}")


def add_months(d, months):
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    days_in_month = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(d.day, days_in_month))


def fmt(d):
    return f"{d:%a %b} {d.day}, {d.year}"


def emit(args, result, lines):
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("\n".join(lines))


# --- opt-window ------------------------------------------------------------

def opt_window(args):
    if args.sample:
        args.program_end, args.today = "2027-05-08", "2027-02-20"
    end = parse_date(args.program_end, "--program-end")
    today = parse_date(args.today, "--today")
    school_opens = end - timedelta(days=args.school_lead_days)
    uscis_opens = end - timedelta(days=90)
    uscis_closes = end + timedelta(days=60)
    start_latest = end + timedelta(days=60)

    if today < school_opens:
        status = "too_early"
        line = f"Too early. Your school can take the OPT request from {fmt(school_opens)} ({(school_opens - today).days} days away)."
    elif today <= uscis_closes:
        status = "open"
        line = f"The OPT window is open. USCIS must receive the I-765 by {fmt(uscis_closes)} ({(uscis_closes - today).days} days left), and within 30 days of your OPT I-20 date."
    else:
        status = "closed"
        line = f"The OPT filing window closed on {fmt(uscis_closes)}. Talk to your DSO today."

    result = {
        "status": status,
        "program_end": end,
        "school_request_opens": school_opens,
        "uscis_accepts_from": uscis_opens,
        "uscis_last_day": uscis_closes,
        "start_date_choices": [end + timedelta(days=1), start_latest],
        "file_within_days_of_i20": 30,
    }
    lines = [
        line,
        f"School request opens: {fmt(school_opens)}",
        f"USCIS accepts from: {fmt(uscis_opens)}",
        f"Last day USCIS can receive it: {fmt(uscis_closes)} (also within 30 days of the OPT I-20 date)",
        f"Start date you can pick: {fmt(end + timedelta(days=1))} to {fmt(start_latest)}",
    ]
    emit(args, result, lines)


# --- stem-window -----------------------------------------------------------

def stem_window(args):
    if args.sample:
        args.opt_end, args.today, args.stem_i20_date = "2028-06-30", "2028-04-10", None
    opt_end = parse_date(args.opt_end, "--opt-end")
    today = parse_date(args.today, "--today")
    school_opens = opt_end - timedelta(days=args.school_lead_days)
    uscis_opens = opt_end - timedelta(days=90)
    last_day = opt_end - timedelta(days=1)
    if args.stem_i20_date:
        i20 = parse_date(args.stem_i20_date, "--stem-i20-date")
        last_day = min(last_day, i20 + timedelta(days=60))

    if today < school_opens:
        status = "too_early"
        line = f"Too early. Your school can take the STEM OPT request from {fmt(school_opens)}."
    elif today <= last_day:
        status = "open"
        line = f"The STEM OPT window is open. USCIS must receive it by {fmt(last_day)} ({(last_day - today).days} days left)."
    else:
        status = "closed"
        line = f"The STEM OPT window has closed (last day {fmt(last_day)}). Talk to your DSO today."

    result = {
        "status": status,
        "opt_end": opt_end,
        "school_request_opens": school_opens,
        "uscis_accepts_from": uscis_opens,
        "uscis_last_day": last_day,
        "needs": ["employer enrolled in E-Verify", "Form I-983 signed with employer", "STEM I-20 from the DSO"],
    }
    lines = [
        line,
        f"School request opens: {fmt(school_opens)}",
        f"USCIS accepts from: {fmt(uscis_opens)}",
        f"Last day USCIS can receive it: {fmt(last_day)}"
        + ("" if args.stem_i20_date else " (and within 60 days of the STEM I-20 date)"),
        "You need: an E-Verify employer, a signed Form I-983, and the STEM I-20.",
    ]
    emit(args, result, lines)


# --- unemployment ----------------------------------------------------------

def unemployment(args):
    if args.sample:
        args.ead_start, args.today, args.jobs = "2027-06-15", "2027-10-01", str(ASSETS / "sample_jobs.json")
    ead_start = parse_date(args.ead_start, "--ead-start")
    today = parse_date(args.today, "--today")
    if today < ead_start:
        fail("--today is before --ead-start; the unemployment clock has not started")
    limit = 150 if args.stem else 90

    employed_days = set()
    jobs = load_json(args.jobs) if args.jobs else []
    for job in jobs:
        if float(job.get("hours_per_week", 0)) < 20:
            continue  # under 20 hours a week counts as unemployed
        start = max(parse_date(job["start"], "job start"), ead_start)
        end = min(parse_date(job["end"], "job end") if job.get("end") else today, today)
        d = start
        while d <= end:
            employed_days.add(d)
            d += timedelta(days=1)

    total = (today - ead_start).days + 1
    used = total - len(employed_days)
    if args.prior_days:
        used += args.prior_days
    left = limit - used
    if left <= 0:
        status, line = "over", f"You've used {used} of {limit} unemployment days. That's at or over the limit. Contact your DSO today."
    elif left <= 15:
        status, line = "urgent", f"{left} unemployment days left out of {limit}. That's very close to the limit."
    elif left <= 30:
        status, line = "warning", f"{left} unemployment days left out of {limit}."
    else:
        status, line = "ok", f"{left} unemployment days left out of {limit}."
    run_out = today + timedelta(days=max(left, 0)) if left > 0 else today
    result = {"status": status, "limit": limit, "used": used, "left": max(left, 0),
              "runs_out_if_still_unemployed": run_out,
              "jobs_counted": [j for j in jobs if float(j.get("hours_per_week", 0)) >= 20]}
    lines = [line, f"Used: {used} (since {fmt(ead_start)})"]
    if left > 0:
        lines.append(f"If you stay unemployed, you hit the limit on {fmt(run_out)}.")
    skipped = [j for j in jobs if float(j.get("hours_per_week", 0)) < 20]
    if skipped:
        lines.append("Jobs under 20 hours a week don't count as employment: " + ", ".join(j.get("employer", "?") for j in skipped))
    emit(args, result, lines)


# --- hours -----------------------------------------------------------------

def hours(args):
    if args.sample:
        args.shifts = str(ASSETS / "sample_shifts.json")
    shifts = load_json(args.shifts)
    breaks = []
    if args.breaks:
        for part in args.breaks.split(","):
            a, _, b = part.partition(":")
            breaks.append((parse_date(a, "break start"), parse_date(b, "break end")))

    weeks = {}
    for s in shifts:
        start = parse_datetime(s["start"], "shift start")
        end = parse_datetime(s["end"], "shift end")
        if end <= start:
            fail(f"shift ends before it starts: {s}")
        monday = start.date() - timedelta(days=start.weekday())
        w = weeks.setdefault(monday, {"hours": 0.0, "jobs": set()})
        w["hours"] += (end - start).total_seconds() / 3600
        w["jobs"].add(s.get("job", "job"))

    report = []
    for monday in sorted(weeks):
        sunday = monday + timedelta(days=6)
        in_break = any(a <= monday and sunday <= b for a, b in breaks)
        limit = args.break_limit if in_break else args.limit
        h = round(weeks[monday]["hours"], 2)
        report.append({"week_of": monday, "hours": h, "limit": limit,
                       "over_by": round(max(0.0, h - limit), 2),
                       "left": round(max(0.0, limit - h), 2),
                       "jobs": sorted(weeks[monday]["jobs"])})
    over = [r for r in report if r["over_by"] > 0]
    result = {"weeks": report, "any_over": bool(over)}
    lines = []
    for r in report:
        flag = f"OVER by {r['over_by']}" if r["over_by"] else f"{r['left']} left"
        week = f"{r['week_of']:%b} {r['week_of'].day}"
        lines.append(f"Week of {week} (Mon-Sun): {r['hours']} of {r['limit']} hours, {flag}")
    lines.insert(0, "Over the limit in at least one week. Fix the schedule before working those shifts." if over
                 else "All weeks are within the limit.")
    emit(args, result, lines)


# --- enrollment ------------------------------------------------------------

def enrollment(args):
    if args.sample:
        args.courses = str(ASSETS / "sample_courses.json")
        args.drop = args.drop or "CSE 230"
    courses = load_json(args.courses)
    default_min = 12 if args.level == "undergrad" else 9
    min_credits = args.min_credits if args.min_credits is not None else default_min
    max_online = args.max_online_credits

    def tally(cs):
        counted = [c for c in cs if not c.get("audit")]
        total = sum(float(c["credits"]) for c in counted)
        in_person = sum(float(c["credits"]) for c in counted if c.get("mode", "in_person") in IN_PERSON_MODES)
        online = total - in_person
        online_counted = min(online, max_online) if max_online is not None else online
        counted_total = in_person + online_counted
        problems = []
        if counted_total < min_credits:
            problems.append(f"{counted_total:g} credits count toward full-time, below the {min_credits:g} minimum")
        if args.min_in_person is not None and in_person < args.min_in_person:
            problems.append(f"only {in_person:g} in-person credits, below the {args.min_in_person:g} required")
        return {"total": total, "in_person": in_person, "online": online,
                "counts_toward_full_time": counted_total, "full_time": not problems, "problems": problems}

    now = tally(courses)
    result = {"min_credits": min_credits, "now": now}
    lines = [("Full-time now: " if now["full_time"] else "NOT full-time now: ")
             + f"{now['counts_toward_full_time']:g} credits count ({now['in_person']:g} in person, {now['online']:g} online)."]
    lines += [f"- {p}" for p in now["problems"]]

    if args.drop:
        key = args.drop.replace(" ", "").lower()
        remaining = [c for c in courses if c["course"].replace(" ", "").lower() != key]
        if len(remaining) == len(courses):
            fail(f"{args.drop} is not in the course list")
        after = tally(remaining)
        result["after_drop"] = {"dropped": args.drop, **after}
        if after["full_time"]:
            lines.append(f"Dropping {args.drop} keeps you full-time ({after['counts_toward_full_time']:g} credits).")
        else:
            lines.append(f"Dropping {args.drop} takes you below full-time. Get Reduced Course Load approval from your DSO first, or swap it for another class.")
            lines += [f"- {p}" for p in after["problems"]]
    emit(args, result, lines)


# --- travel ----------------------------------------------------------------

def travel(args):
    if args.sample:
        args.signed, args.return_date, args.today = "2026-01-10", "2027-01-12", "2026-10-24"
        args.i20_end, args.ead_end, args.on_opt = "2028-05-15", None, False
    signed = parse_date(args.signed, "--signed")
    ret = parse_date(args.return_date, "--return-date")
    today = parse_date(args.today, "--today")
    valid_until = add_months(signed, 6 if args.on_opt else 12)
    if args.i20_end:
        valid_until = min(valid_until, parse_date(args.i20_end, "--i20-end"))
    if args.on_opt and args.ead_end:
        valid_until = min(valid_until, parse_date(args.ead_end, "--ead-end"))
    request_from = ret - timedelta(days=args.request_lead_days)
    ok = ret <= valid_until
    result = {"valid_until": valid_until, "valid_on_return": ok, "request_new_from": request_from,
              "can_request_now": today >= request_from}
    if ok:
        lines = [f"Your travel signature is good for that trip. It's valid until {fmt(valid_until)}."]
    else:
        lines = [f"Your travel signature expires {fmt(valid_until)}, before you return on {fmt(ret)}. You need a new one."]
        if today >= request_from:
            lines.append("You can request it now.")
        else:
            lines.append(f"You can request it from {fmt(request_from)} ({(request_from - today).days} days from now).")
    emit(args, result, lines)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--json", action="store_true", help="print JSON instead of text")
        sp.add_argument("--sample", action="store_true", help="use the bundled sample inputs")
        return sp

    sp = common(sub.add_parser("opt-window"))
    sp.add_argument("--program-end")
    sp.add_argument("--today")
    sp.add_argument("--school-lead-days", type=int, default=97)
    sp.set_defaults(fn=opt_window)

    sp = common(sub.add_parser("stem-window"))
    sp.add_argument("--opt-end")
    sp.add_argument("--today")
    sp.add_argument("--stem-i20-date")
    sp.add_argument("--school-lead-days", type=int, default=97)
    sp.set_defaults(fn=stem_window)

    sp = common(sub.add_parser("unemployment"))
    sp.add_argument("--ead-start")
    sp.add_argument("--today")
    sp.add_argument("--jobs", help="JSON list of {employer, start, end?, hours_per_week}")
    sp.add_argument("--stem", action="store_true", help="use the 150-day STEM OPT limit")
    sp.add_argument("--prior-days", type=int, default=0, help="unemployment days used before the current EAD (STEM)")
    sp.set_defaults(fn=unemployment)

    sp = common(sub.add_parser("hours"))
    sp.add_argument("--shifts", help="JSON list of {job, start, end} with local date-times")
    sp.add_argument("--limit", type=float, default=20)
    sp.add_argument("--break-limit", type=float, default=40)
    sp.add_argument("--breaks", help="official break ranges, START:END comma-separated")
    sp.set_defaults(fn=hours)

    sp = common(sub.add_parser("enrollment"))
    sp.add_argument("--courses", help="JSON list of {course, credits, mode, audit?}")
    sp.add_argument("--level", choices=["undergrad", "grad"], default="undergrad")
    sp.add_argument("--min-credits", type=float)
    sp.add_argument("--min-in-person", type=float)
    sp.add_argument("--max-online-credits", type=float, default=3,
                    help="online credits that count toward full-time (federal rule: 3)")
    sp.add_argument("--drop", help="course to test dropping, e.g. \"CSE 230\"")
    sp.set_defaults(fn=enrollment)

    sp = common(sub.add_parser("travel"))
    sp.add_argument("--signed")
    sp.add_argument("--return-date")
    sp.add_argument("--today")
    sp.add_argument("--on-opt", action="store_true")
    sp.add_argument("--i20-end")
    sp.add_argument("--ead-end")
    sp.add_argument("--request-lead-days", type=int, default=120)
    sp.set_defaults(fn=travel)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
