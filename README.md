# Pocket Advisor

A [Cubbie](https://cubbie.ai) Skill: the advisor who's never booked out, and texts you first.

After one setup chat, Pocket Advisor keeps watch. Every morning it checks new email for job offers, flights and
USCIS mail; every week it checks the school's and the government's rule pages for changes; and it reminds you
before OPT, travel signature, drop and registration deadlines. It only texts when something needs you, and it can
send the exact moment in an immigration attorney's video that explains the issue.

- **Visa and work, for F-1 students.** "Can I take this job?", full-time checks before dropping a class,
  on-campus hour limits, OPT and STEM OPT deadlines, unemployment days, travel signatures. Every answer links
  the official page, and anything risky ends with an email to the international office, drafted and ready.
- **Classes, for every student.** Reads what's left on the degree audit, searches next term's classes, and builds
  a conflict-free schedule under the credit cap that favors classes filling two requirements at once.

Works at any US school. Arizona State University is fully mapped as the worked example.

## Install

Text this repository's link to Cubbie.

## What's inside

| Path | What it is |
| --- | --- |
| `SKILL.md` | Instructions Cubbie follows |
| `references/f1-rules.md` | Federal F-1 work and status rules, with sources |
| `references/schools.md` | How to look up any school's rules, plus the ASU profile |
| `references/course-planning.md` | How the class planner gathers its inputs |
| `references/watchers.md` | The scheduled check-ins and exactly what each one does |
| `scripts/visa_check.py` | Date and hours math: OPT, STEM OPT, unemployment, hours, enrollment, travel |
| `scripts/plan_schedule.py` | Picks class sections that fit requirements, time and credit limits |
| `scripts/watch.py` | Detects changes on watched rule pages and remembers what was already handled |
| `scripts/clips.py` | Finds the moment in a video transcript that answers a question, with a jump-to link |
| `assets/` | Made-up sample inputs for trying the scripts |

Try the scripts without any accounts (Python 3.9+; only `clips.py --video` needs a package):

```bash
python3 scripts/visa_check.py opt-window --sample
python3 scripts/plan_schedule.py --sample
python3 scripts/watch.py rules --sample
python3 scripts/clips.py --sample
```

Pocket Advisor gives general information, not legal advice. Your international office (DSO) and academic advisor
have the final word.
