"""Conservative credit arithmetic shared by the visa checker and class planner.

This checks supplied data, not immigration eligibility. Short-session rules need
school-specific review; semester totals alone cannot establish continuous enrollment.
"""

from datetime import date

IN_PERSON_MODES = {"in_person", "hybrid", "immersion"}
ONLINE_MODES = {"online", "icourse", "sync"}


def assess(courses, minimum, min_in_person, max_online, term_start=None, term_end=None):
    courses = [c for c in courses if not c.get("audit")]
    total = sum(float(c["credits"]) for c in courses)
    in_person = sum(float(c["credits"]) for c in courses if c.get("mode") in IN_PERSON_MODES)
    online = sum(float(c["credits"]) for c in courses if c.get("mode") in ONLINE_MODES)
    counted = in_person + (min(online, max_online) if max_online is not None else online)
    unknown = [c["course"] for c in courses if c.get("mode") not in IN_PERSON_MODES | ONLINE_MODES]
    missing, problems = [], []
    if unknown:
        missing.append("Confirm delivery mode for: " + ", ".join(unknown))
    if not term_start or not term_end:
        missing.append("Confirm term and course start/end dates before verifying enrollment throughout the term")
    else:
        first, last = date.fromisoformat(term_start), date.fromisoformat(term_end)
        if first > last:
            raise ValueError("term start must not be after term end")
        for c in courses:
            if not c.get("start_date") or not c.get("end_date"):
                missing.append(f"Confirm session dates for {c['course']}")
                continue
            start, end = date.fromisoformat(c["start_date"]), date.fromisoformat(c["end_date"])
            if start > end:
                raise ValueError(f"{c['course']} starts after it ends")
            if start > first or end < last:
                missing.append(f"Confirm school-specific short-session enrollment rules for {c['course']}")
    # Unknown delivery modes can change either total, so do not call them failures.
    if not unknown:
        if counted < minimum:
            problems.append(f"{counted:g} credits count toward full-time, below the {minimum:g} minimum")
        if min_in_person is not None and in_person < min_in_person:
            problems.append(f"only {in_person:g} in-person credits, below the {min_in_person:g} required")
    full_time = False if problems else None if missing else True
    return {"total": total, "in_person": in_person, "online": online,
            "counts_toward_full_time": counted, "full_time": full_time,
            "status": "below_minimum" if problems else "needs_information" if missing else "meets_supplied_rules",
            "problems": problems, "needs_information": missing}
