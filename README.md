# 🛡️ AttendGuard

**Student attendance and performance early-warning system** (Education track).

AttendGuard takes a college's attendance, marks and staff files and works out which students are at risk. For each of them it shows how many classes they must attend in a row to recover. It then emails the student a personal recovery plan and sends summary alerts to their subject teachers and faculty adviser. At-risk students can also book a support meeting from a teacher's free timetable slots.

## What it does

| Tab | What you get |
|---|---|
| **Dashboard** | KPI cards (total, critical, warning, safe, average attendance), risk-by-department and risk-by-subject charts, and a ranked at-risk table with department/subject filters |
| **Student view** | Per-subject attendance against the target, a plain-English recovery plan ("Attend the next 7 classes in a row in Physics to reach 85%"), subject details and a marks-trend chart |
| **Alerts** | Preview, then send personalised student warnings (all at-risk or selected). Teacher alerts list the at-risk students in their subjects; adviser alerts list those in their department. Also a department-wise weekly summary. Test mode is **on by default** |
| **Appointments** | Pick an at-risk student and subject, see the teacher's free slots, book one, and send confirmation emails to the student and the teacher |

Input files (CSV or XLSX, uploaded in the sidebar). A **Load sample data** button loads realistic data from `sample_data/` (40 students, 3 departments, 5 subjects).

| File | Columns |
|---|---|
| Attendance | `student_id, name, email, department, subject, classes_held, classes_attended` |
| Marks | `student_id, subject, test_name, test_date, marks, max_marks` |
| Staff | `department, subject, teacher_name, teacher_email, adviser_name, adviser_email` |
| Timetable *(optional)* | `teacher_name, day, time_slot, status` (`free` / `busy`) |

Messy input is handled:
- Headers are case-insensitive and whitespace-stripped, and common aliases are accepted (`Roll No`, `Dept`, `Course`, `Total Classes`, `Present`, …).
- Blank cells, duplicate rows and non-numeric values are cleaned, and the sidebar reports what was fixed.
- A missing column produces a specific message such as *"Attendance file is missing required column(s): classes_held"*. The app never crashes on a bad file.

## How it works

All the maths lives in [`logic.py`](logic.py) as pure functions with no Streamlit imports. [`tests.py`](tests.py) checks them, including the edge cases: zero classes held, 100% attendance, missing marks, an unreachable target, and garbage values.

### Attendance status
`attendance % = attended / held × 100`. Zero classes held counts as 100% (nothing has been missed yet). The target *T* comes from the sidebar slider (default 85%).

| Status | Rule |
|---|---|
| SAFE | % ≥ T + 5 |
| WARNING | T ≤ % < T + 5 |
| CRITICAL | % < T |

### Recovery formula
The number of consecutive classes to attend to reach target *t* (as a fraction):

```
x = ceil( (t × held − attended) / (1 − t) )      0 if already at or above target
```

This comes from solving `(attended + x) / (held + x) ≥ t`. If one subject needs more than **60** classes in a row, or the target is 100% with an absence already on record, the app shows **"Can't recover this term"**. A student's total "classes needed" is the sum over their subjects.

### Marks flags
For each student and subject, tests are ordered by date:
- **Weak**: the latest test is below 40%, *or* it dropped more than 10 percentage points from the previous test.
- **Trend**: the change from the previous test, where more than +5 is *Improving*, less than −5 is *Falling*, and anything else is *Stable*. The student-level trend uses the average change across subjects.

### Risk score (0–100, higher = more at risk)
```
attendance part (0–60) = min(60, 3 × max(0, (T + 5) − attendance %))
marks part      (0–40) = 25 × (weak subjects / subjects with marks) + 15 if overall trend is Falling
risk score             = min(100, attendance part + marks part)
```
A student is **at risk** if their status is WARNING or CRITICAL, or if they have any weak subject. The tables are sorted by risk score in descending order.

### Email
- Mail goes through Gmail SMTP (SSL, port 465) using the `SMTP_USER` / `SMTP_PASS` secrets.
- Each message is sent in its own `try/except`, so one failure never stops the batch. A progress bar runs during sending, and a results table shows sent/failed plus the reason for each message.
- **Test mode** (on by default) redirects every email to the test address in the sidebar. The subject line becomes `[TEST -> real.recipient@…] …`.

## Tools used
Python 3.12 · Streamlit · pandas · Plotly · openpyxl · smtplib (Gmail SMTP). There is no database: data lives in `st.session_state` and in-memory DataFrames, and the analysis is cached with `st.cache_data`.

## Run locally
Developed on **Python 3.12**.

```bash
py -3.12 -m venv .venv            # macOS/Linux: python3.12 -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install --only-binary=:all: -r requirements.txt
python tests.py                   # should print ALL PASSED
streamlit run app.py
```

To send real email, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in. That file is git-ignored. Without secrets, everything still works except the send buttons, which are disabled with a hint.

## Required secrets

| Secret | Value |
|---|---|
| `SMTP_USER` | The Gmail address that sends the emails |
| `SMTP_PASS` | A Gmail **App Password**: 16 characters, created under Google Account → Security → 2-Step Verification → App passwords. Your normal Gmail password won't work |

## Deployment checklist (Streamlit Community Cloud)
1. Push this repo to GitHub. `.venv/` and `.streamlit/secrets.toml` are git-ignored.
2. In Streamlit Cloud, choose **New app**, pick the repo and branch `main`, and set the main file to `app.py`.
3. Under **Advanced settings**, set Python to **3.12**.
4. Under **Secrets**, paste:
   ```toml
   SMTP_USER = "your.address@gmail.com"
   SMTP_PASS = "your16charapppassword"
   ```
5. Deploy, open the app, and click **Load sample data**. Check that all four tabs render.
6. With test mode on, type your own address in the sidebar and send one student warning. Confirm it arrives with `[TEST -> …]` in the subject.
7. Leave test mode **on** for the demo.

## Project layout
```
app.py            Streamlit UI (4 tabs)
logic.py          attendance %, status, recovery formula, marks flags, risk score
data_loader.py    CSV/XLSX loading, header aliases, validation, cleaning
emailer.py        email composition + Gmail SMTP batch sender
tests.py          checks for the formula, flags, edge cases and loader
sample_data/      attendance, marks, staff, timetable CSVs
```

## Roadmap (future work, not implemented)
- **Automated voice calls** to students (and parents) who stay CRITICAL after an email alert.
- **Scheduled weekly summaries** sent automatically by a cron job, instead of the manual "Send weekly summary" button.
- Persistent storage for bookings and alert history (currently per session).
