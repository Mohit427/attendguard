"""Core AttendGuard logic: attendance status, recovery maths, marks flags, risk score.

Pure functions only - no Streamlit. The scalar helpers at the top are plain
Python; the DataFrame builders import pandas lazily so the maths can be
tested on its own.
"""

from __future__ import annotations

import math
from datetime import datetime

SAFE, WARNING, CRITICAL = "SAFE", "WARNING", "CRITICAL"
STATUS_ORDER = [CRITICAL, WARNING, SAFE]

WARNING_BAND = 5.0          # percentage points above target that still count as WARNING
MAX_RECOVERABLE = 60        # more consecutive classes than this = "can't recover this term"
WEAK_MARK_PCT = 40.0        # latest test below this is weak
DROP_THRESHOLD = 10.0       # latest test dropping more than this (pct points) is weak
TREND_BAND = 5.0            # change within +/- this is "Stable"

FALLING, STABLE, IMPROVING, NO_MARKS = "Falling", "Stable", "Improving", "No marks"


# ---------------------------------------------------------------- scalars

def _num(value, default=0.0) -> float:
    """Coerce anything to a finite float (NaN/None/garbage -> default)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def attendance_pct(held, attended) -> float:
    """Attendance percentage. Zero classes held means nothing missed -> 100%."""
    held = max(_num(held), 0.0)
    attended = min(max(_num(attended), 0.0), held)
    if held == 0:
        return 100.0
    return round(attended / held * 100.0, 2)


def classes_needed(held, attended, target_pct) -> int | None:
    """Consecutive classes to attend to reach the target.

    x = ceil((t * held - attended) / (1 - t)), 0 if already at/above target.
    Returns None when the target can never be reached (target of 100% with
    an absence already on record).
    """
    t = _num(target_pct) / 100.0
    held = max(_num(held), 0.0)
    attended = min(max(_num(attended), 0.0), held)
    if held == 0 or attended >= t * held - 1e-9:
        return 0
    if t >= 1.0:
        return None
    # round() guards against float noise such as 0.85 * 20 = 16.999999...
    x = math.ceil(round((t * held - attended) / (1.0 - t), 6))
    return max(int(x), 0)


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def is_recoverable(needed) -> bool:
    return not _missing(needed) and needed <= MAX_RECOVERABLE


def format_needed(needed, limit=MAX_RECOVERABLE) -> str:
    """Display text. limit=None skips the cap (used for per-student totals)."""
    if _missing(needed) or (limit is not None and needed > limit):
        return "Can't recover this term"
    return str(int(needed))


def total_needed(per_subject) -> int | None:
    """Student-level need: sum of per-subject needs, None if any subject can't recover."""
    vals = list(per_subject)
    if any(not is_recoverable(v) for v in vals):
        return None
    return int(sum(vals))


def attendance_status(pct, target_pct) -> str:
    pct, target = _num(pct), _num(target_pct)
    if pct >= target + WARNING_BAND:
        return SAFE
    if pct >= target:
        return WARNING
    return CRITICAL


def trend_label(latest_pct, previous_pct) -> str:
    if latest_pct is None:
        return NO_MARKS
    if previous_pct is None:
        return STABLE
    change = latest_pct - previous_pct
    if change > TREND_BAND:
        return IMPROVING
    if change < -TREND_BAND:
        return FALLING
    return STABLE


def is_weak(latest_pct, previous_pct) -> bool:
    """Weak if latest < 40% or it dropped more than 10 points vs the previous test."""
    if latest_pct is None:
        return False
    if latest_pct < WEAK_MARK_PCT:
        return True
    return previous_pct is not None and (previous_pct - latest_pct) > DROP_THRESHOLD


def risk_score(att_pct, target_pct, weak_subjects, marked_subjects, trend) -> float:
    """0-100 risk score (higher = more at risk). See README for the formula.

    attendance part (0-60): 3 points per percentage point below (target + 5)
    marks part (0-40):      25 x share of subjects flagged weak
                            + 15 if the overall marks trend is Falling
    """
    gap = max(0.0, _num(target_pct) + WARNING_BAND - _num(att_pct))
    att_part = min(60.0, gap * 3.0)
    weak_share = (weak_subjects / marked_subjects) if marked_subjects else 0.0
    marks_part = 25.0 * weak_share + (15.0 if trend == FALLING else 0.0)
    return round(min(100.0, max(0.0, att_part + marks_part)), 1)


def recovery_message(subject, needed, target_pct) -> str:
    target = f"{_num(target_pct):g}%"
    if not _missing(needed) and needed == 0:
        return f"{subject}: on track - you are at or above {target}."
    if not is_recoverable(needed):
        return (f"{subject}: can't recover to {target} this term - "
                f"please meet your teacher to discuss options.")
    word = "class" if needed == 1 else "classes"
    return f"Attend the next {needed} {word} in a row in {subject} to reach {target}."


def _parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        import pandas as pd
        ts = pd.to_datetime(value, errors="coerce", dayfirst=False)
        return None if pd.isna(ts) else ts.to_pydatetime()
    except Exception:
        return None


# ---------------------------------------------------------------- tables

def subject_attendance(att, target_pct):
    """One row per student x subject with %, classes needed and status."""
    import pandas as pd

    df = att.copy()
    grouped = (df.groupby(["student_id", "subject"], as_index=False)
                 .agg(name=("name", "first"), email=("email", "first"),
                      department=("department", "first"),
                      classes_held=("classes_held", "sum"),
                      classes_attended=("classes_attended", "sum")))
    grouped["attendance_pct"] = [attendance_pct(h, a) for h, a in
                                 zip(grouped.classes_held, grouped.classes_attended)]
    grouped["classes_needed"] = [classes_needed(h, a, target_pct) for h, a in
                                 zip(grouped.classes_held, grouped.classes_attended)]
    grouped["status"] = [attendance_status(p, target_pct) for p in grouped.attendance_pct]
    grouped["classes_needed"] = pd.Series(grouped["classes_needed"].tolist(), dtype="object")
    return grouped.reset_index(drop=True)


def marks_by_subject(marks):
    """One row per student x subject: latest/previous test %, change, trend, weak flag."""
    import pandas as pd

    cols = ["student_id", "subject", "tests", "latest_test", "latest_pct",
            "previous_pct", "change", "trend", "weak"]
    if marks is None or len(marks) == 0:
        return pd.DataFrame(columns=cols)

    df = marks.copy()
    df["_order"] = range(len(df))
    df["_date"] = pd.to_datetime(df["test_date"], errors="coerce")
    df["pct"] = [
        round(_num(m) / _num(mx) * 100.0, 1) if _num(mx) > 0 else None
        for m, mx in zip(df["marks"], df["max_marks"])
    ]
    df = df[df["pct"].notna()]
    rows = []
    for (sid, subj), g in df.groupby(["student_id", "subject"], sort=False):
        g = g.sort_values(["_date", "_order"], na_position="first")
        latest = float(g["pct"].iloc[-1])
        prev = float(g["pct"].iloc[-2]) if len(g) > 1 else None
        rows.append({
            "student_id": sid, "subject": subj, "tests": len(g),
            "latest_test": str(g["test_name"].iloc[-1]),
            "latest_pct": latest, "previous_pct": prev,
            "change": None if prev is None else round(latest - prev, 1),
            "trend": trend_label(latest, prev), "weak": is_weak(latest, prev),
        })
    return pd.DataFrame(rows, columns=cols)


def _overall_trend(changes) -> str:
    changes = [c for c in changes if c is not None and not (isinstance(c, float) and math.isnan(c))]
    if not changes:
        return STABLE
    avg = sum(changes) / len(changes)
    return IMPROVING if avg > TREND_BAND else FALLING if avg < -TREND_BAND else STABLE


def build_report(att, marks, target_pct):
    """Everything the UI needs, computed once.

    Returns dict with:
      subjects - per student x subject attendance (+ marks columns merged in)
      marks    - per student x subject marks summary
      students - per student overview, sorted by risk score (desc)
    """
    import pandas as pd

    subj = subject_attendance(att, target_pct)
    msum = marks_by_subject(marks)
    subj = subj.merge(msum[["student_id", "subject", "latest_pct", "trend", "weak"]],
                      on=["student_id", "subject"], how="left")
    subj["trend"] = subj["trend"].fillna(NO_MARKS)
    subj["weak"] = subj["weak"].fillna(False).astype(bool)

    students = (subj.groupby("student_id", as_index=False)
                    .agg(name=("name", "first"), email=("email", "first"),
                         department=("department", "first"),
                         classes_held=("classes_held", "sum"),
                         classes_attended=("classes_attended", "sum")))
    students["attendance_pct"] = [attendance_pct(h, a) for h, a in
                                  zip(students.classes_held, students.classes_attended)]
    need = subj.groupby("student_id")["classes_needed"].agg(total_needed)
    students["classes_needed"] = pd.Series(
        [need.get(sid) for sid in students["student_id"]], dtype="object")
    students["status"] = [attendance_status(p, target_pct) for p in students.attendance_pct]

    trends, weak_lists, marked = [], [], []
    for sid in students["student_id"]:
        m = msum[msum["student_id"] == sid]
        marked.append(len(m))
        weak_lists.append(sorted(m.loc[m["weak"], "subject"].astype(str).tolist()))
        trends.append(_overall_trend(m["change"].tolist()) if len(m) else NO_MARKS)
    students["marks_trend"] = trends
    students["weak_subjects"] = weak_lists
    students["risk_score"] = [
        risk_score(p, target_pct, len(w), n, t)
        for p, w, n, t in zip(students.attendance_pct, weak_lists, marked, trends)
    ]
    students["at_risk"] = (students["status"] != SAFE) | students["weak_subjects"].map(bool)
    students = students.sort_values(["risk_score", "attendance_pct"],
                                    ascending=[False, True]).reset_index(drop=True)
    return {"subjects": subj, "marks": msum, "students": students}
