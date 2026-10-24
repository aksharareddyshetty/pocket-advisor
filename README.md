# Pocket Advisor

A [Cubbie](https://cubbie.ai) Skill: the advisor who's never booked out.

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
| `scripts/visa_check.py` | Date and hours math: OPT, STEM OPT, unemployment, hours, enrollment, travel |
| `scripts/plan_schedule.py` | Picks class sections that fit requirements, time and credit limits |
| `assets/` | Made-up sample inputs for trying the scripts |

Try the scripts without any accounts (Python 3.9+, no packages):

```bash
python3 scripts/visa_check.py opt-window --sample
python3 scripts/plan_schedule.py --sample
```

Pocket Advisor gives general information, not legal advice. Your international office (DSO) and academic advisor
have the final word.
