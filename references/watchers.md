# Watchers: Pocket Advisor's scheduled check-ins

Pocket Advisor's value is that the student doesn't have to ask. After the setup chat, these check-ins run on
their own and text the student only when something needs them. Silence means all clear.

Create each check-in only after the student says yes (one yes can cover the whole bundle). Each one runs days
later without this conversation, so its wording must stand alone: name the Skill, what to read, what to run and
when to text. Copy the wording below, filling in the profile values.

## The bundle

| Check-in | When | Who gets it |
| --- | --- | --- |
| Morning inbox sweep | Daily, 8 am | Every F-1 student |
| Rules watch | Weekly, Monday 9 am | Every F-1 student |
| Hours preview | Weekly, Sunday 7 pm | F-1 students with an on-campus job |
| Date alarms | One-off dates from the profile | Every F-1 student |
| Term alarms | Registration and drop deadlines | Every student |

Offer it like this, then wait for the yes:

```text
Want me to keep watch so you don't have to ask?
- every morning I check new email for job offers, flights and USCIS mail
- every Monday I check your school's and the government's rule pages for changes
- I remind you before OPT, travel signature and registration deadlines
I only text when something needs you. Say yes, or pick the ones you want.
```

## 1. Morning inbox sweep

Check-in wording:

> Pocket Advisor morning sweep for <student>. Search the student's email from the last 26 hours for (a) job or
> internship offers, recruiter emails and interview invitations, (b) flight or travel bookings, (c) mail from USCIS,
> SEVP or <school international office>, (d) registration or drop deadline notices. For each item, run
> `python3 scripts/watch.py seen --kind email --id "<message id>"` and skip it if the exit code is 1. Then handle it
> as section 1 of Pocket Advisor's references/watchers.md says. Text the student only for items that need action.

How to handle each kind:

- **Job, internship or recruiter email.** Work out on or off campus, dates and hours from the email. Walk the
  "Can I take this job?" steps in `f1-rules.md` and text the verdict before the student answers the recruiter:
  "That Stripe internship offer: you'd need CPT first. Here's the path." Add the school's page and an offer to
  draft the advisor email. Interview invitations only get a text when the job would need authorization the student
  doesn't have yet.
- **Flight booking.** Read the departure and return dates. If the return is to the US, run
  `visa_check.py travel` with the remembered signature date. Text only when the signature, passport (6 months
  past return) or I-20 would not cover the return date.
- **USCIS, SEVP or school mail.** A receipt notice, approval, EAD card shipped, request for evidence, or SEVIS
  update. Update the remembered profile dates (confirm with the student in the same text), and recompute the date
  alarms. A request for evidence or a denial is urgent: text right away with the deadline it gives and offer to
  draft a DSO email.
- **Registration or drop deadline.** Add a term alarm (section 5).

## 2. Rules watch

At setup, build the watchlist once:

```bash
python3 scripts/watch.py add --name "<school> CPT" --url <school CPT page>
python3 scripts/watch.py add --name "<school> OPT" --url <school OPT page>
python3 scripts/watch.py add --name "<school> STEM OPT" --url <school STEM OPT page>
python3 scripts/watch.py add --name "<school> full-time enrollment" --url <school enrollment page>
python3 scripts/watch.py add --name "<school> on-campus work" --url <school hours page>
python3 scripts/watch.py add --name "Study in the States: training" --url https://studyinthestates.dhs.gov/students/training-opportunities-in-the-united-states
python3 scripts/watch.py add --name "USCIS I-765" --url https://www.uscis.gov/i-765
```

Use the school profile's links (`schools.md`). The first run only saves each page.

Check-in wording:

> Pocket Advisor rules watch for <student>. Run `python3 scripts/watch.py rules` from the Skill folder. For each
> CHANGED page, decide whether the added or removed lines change anything for this student's profile (visa
> status, CPT or OPT plans, job, travel). If yes, text a two-line summary of what changed and what it means for
> them, with the page link. Also search the web for news from the last 7 days about F-1, OPT, CPT or SEVP rule
> changes from official sources (ice.gov, uscis.gov, dhs.gov, studyinthestates.dhs.gov, the school's site) and
> treat it the same way. Text nothing if nothing affects them.

Exit code 4 means a page couldn't be fetched; open it in the browser instead. If it fails two weeks running, tell
the student once that the page may have moved.

When a change is confusing, add an expert clip (section 6 of SKILL.md) so the student hears an explanation.

## 3. Hours preview

> Pocket Advisor hours preview for <student>. Read the student's work shifts for next Monday to Sunday from Google
> Calendar (events with <job names>). Run `python3 scripts/visa_check.py hours --shifts shifts.json --limit 20
> --break-limit 40 --breaks <official break ranges>`. Text only if a week is over or within 2 hours of the limit,
> naming the shift to drop.

## 4. Date alarms

Compute once from the profile with `visa_check.py` and create a reminder for each date that applies. Recompute
whenever a profile date changes.

| Alarm | Date | Text |
| --- | --- | --- |
| OPT request opens | `school_request_opens` from `opt-window` | "Your OPT request window opens today." + school OPT page |
| OPT last call | 14 days before `uscis_last_day` | "14 days left to file OPT." |
| Travel signature | 30 days before it expires | "Your travel signature expires <date>. Request one before your next trip." |
| Program end | 30 days before the I-20 program end | Finishing checklist: OPT, on-campus job ends, grace period |
| Unemployment count | Weekly while on OPT with no qualifying job | Run `visa_check.py unemployment`; text at 60, 30 and 15 days left |
| STEM OPT window | `school_request_opens` from `stem-window` | "Your STEM OPT window opens today." |
| Passport | 7 months before expiry | "Your passport expires <date>; renew before travel." |

Word each reminder so it stands alone, for example: "Pocket Advisor: <student>'s OPT request window at ISSC opens
today (program end May 8, 2027). Text them the ISSC OPT link and offer to walk through the steps."

## 5. Term alarms

- **Registration:** 7 days before the student's registration date, build next term's plan with
  `course-planning.md` and text option 1. Ask for the date at setup, or read it from the school's academic
  calendar or an email.
- **Drop deadline:** 3 days before it, for F-1 students, rerun the full-time check on the current Canvas courses
  and text only if the student would be below full-time after any change they mentioned.

## Rules for every check-in

- Text only when there is something to do or know. No "nothing new" texts unless the student asks for them.
- Lead with what happened and what to do, then the link.
- Never act for the student: draft, then wait for their yes.
- If an account is disconnected, text once ("I can't see your email anymore; reconnect to keep the morning
  check on") and skip that part until it is back.
- The student can say "stop watching" or name one check-in to turn off; delete those check-ins and confirm.
