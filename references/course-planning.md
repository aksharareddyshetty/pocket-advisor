# Planning next term's classes

How Cubbie gathers the inputs for `scripts/plan_schedule.py` and turns the result into a schedule the student
can register for. Read `schools.md` first for the student's class search, degree audit and credit cap.

## 1. What is still left (the degree audit)

Best to worst source:

1. **The school's degree audit**, opened in Cubbie's browser (ASU: DARS in My ASU). The student signs in on the
   secure login page or takes over the browser for two-factor. Read the requirements marked not complete, with how
   many courses or credits each still needs, and the student's catalog year.
2. **A PDF or screenshot of the audit** the student sends. Read it as a file.
3. **The major map or checksheet** for the student's major and catalog year (public on most catalog sites), plus
   the courses the student says they have done. Canvas can list past courses to jog their memory.

Turn each open requirement into `{id, label, courses_needed}`. Use the school's own labels (ASU: HUAD, SOBE, SCIT,
QTRS, MATH, AMIT, CIVI, GCSI, SUST, plus "Major core", "Minor", "Electives").

## 2. What is offered next term (the class search)

1. Open the school's class search in the browser for the next term. Most are public (ASU's is).
2. Search the courses that fill the open requirements: for general education use the category filter
   (ASU: General Studies filter in Advanced Search), for the major use the courses on the major map.
3. For each candidate section record course code, title, section or class number, credits, mode (in_person,
   hybrid, immersion, icourse, sync), days, start and end time, seats open, and every requirement it fills.
4. Look for **two-for-one** classes: a course that is on the major map and also carries a general education tag,
   or carries two tags. For example, an economics class that is also tagged SUST. Check the course's catalog page
   to see every requirement it carries.
5. Prerequisites: skip a course when its catalog page lists a prerequisite the student has not done.

Collect 15 to 40 sections; more makes the script slow and the choices noisy.

## 3. Limits and busy times

- `credit_cap`: the school's maximum without an overload petition (ASU: 18, or 19 for Fulton engineering).
- `target_credits`: ask the student ("Aiming for 15?").
- F-1 students: `min_credits` 12 (undergraduate) and the school's in-person rule (ASU: `min_in_person` 9),
  `max_online_credits` 3. Others: `min_credits` 12 if they want to stay full-time, else leave it out.
- `avoid_times`: work shifts and practices from Google Calendar, or what the student says.
- `must_take`: courses the student or the audit says must happen this term.

## 4. Run and reply

Write the JSON to a file in the sandbox and run:

```bash
python3 scripts/plan_schedule.py --input plan.json --top 3
```

Text option 1 first: the classes with days and times, which ones are two-for-one, credits, and what stays open.
Offer options 2 and 3 in one line. If the student wants all of it in one place, make a PDF or a calendar (.ics)
file of the chosen schedule.

Exit code 3 means nothing fits: say which limit blocked it (busy times, full sections, the credit cap, the
in-person rule) and offer to loosen one.

## 5. Share with friends

The script prints a share card. Offer to put it in a message draft for the student to send to friends. When a friend's
card comes back, compare the two and say which classes or sections they could take together. Cubbie never sends
it itself.

## Honesty rules

- Say "your degree audit is the final word, and your advisor signs off" once per plan.
- Never claim a course double-counts unless the catalog or major map shows both requirements.
- Never register the student. Show the class numbers so they can add them, or open the registration page and hand
  over the browser after they say yes.
