"""Loading + cleaning of uploaded attendance / marks / staff / timetable files.

Tolerant of messy input: case-insensitive, whitespace-stripped headers,
common aliases, blank cells, duplicate rows and non-numeric values.
Every problem surfaces as a DataError with a human-readable message.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd

SAMPLE_DIR = Path(__file__).parent / "sample_data"


class DataError(Exception):
    """Raised with a friendly message when a file can't be used."""


SCHEMAS = {
    "attendance": ["student_id", "name", "email", "department", "subject",
                   "classes_held", "classes_attended"],
    "marks": ["student_id", "subject", "test_name", "test_date", "marks", "max_marks"],
    "staff": ["department", "subject", "teacher_name", "teacher_email",
              "adviser_name", "adviser_email"],
    "timetable": ["teacher_name", "day", "time_slot", "status"],
}

NUMERIC = {
    "attendance": ["classes_held", "classes_attended"],
    "marks": ["marks", "max_marks"],
}

# Columns that may be blank without dropping the row.
OPTIONAL_VALUES = {
    "attendance": {"email", "department"},
    "marks": {"test_date", "test_name"},
    "staff": {"teacher_email", "adviser_email", "adviser_name", "teacher_name"},
    "timetable": set(),
}

# Keys are normalised (lowercase, non-alphanumerics -> "_").
ALIASES = {
    "student_id": ["roll_no", "roll_number", "rollno", "roll", "id", "student_no",
                   "student_number", "studentid", "reg_no", "registration_no", "usn", "enrollment_no"],
    "name": ["student_name", "full_name", "student"],
    "email": ["email_id", "e_mail", "mail", "student_email", "email_address"],
    "department": ["dept", "branch", "department_name"],
    "subject": ["course", "subject_name", "course_name", "paper"],
    "classes_held": ["held", "total_classes", "classes_conducted", "conducted", "total",
                     "lectures_held", "total_lectures"],
    "classes_attended": ["attended", "present", "classes_present", "lectures_attended",
                         "attended_classes"],
    "test_name": ["test", "exam", "assessment", "exam_name"],
    "test_date": ["date", "exam_date"],
    "marks": ["score", "marks_obtained", "obtained", "mark"],
    "max_marks": ["out_of", "total_marks", "maximum_marks", "max", "max_score"],
    "teacher_name": ["teacher", "faculty", "faculty_name", "instructor", "subject_teacher"],
    "teacher_email": ["faculty_email", "instructor_email", "teacher_mail"],
    "adviser_name": ["advisor_name", "adviser", "advisor", "faculty_adviser", "faculty_advisor",
                     "mentor", "mentor_name"],
    "adviser_email": ["advisor_email", "mentor_email", "faculty_adviser_email",
                      "faculty_advisor_email"],
    "day": ["weekday", "day_of_week"],
    "time_slot": ["slot", "time", "period", "timeslot"],
    "status": ["availability", "free_busy", "state"],
}


def _norm(col) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(col).strip().lower()).strip("_")


def _rename_columns(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    wanted = SCHEMAS[kind]
    lookup = {}
    for canon in wanted:
        lookup[canon] = canon
        for alias in ALIASES.get(canon, []):
            lookup.setdefault(alias, canon)
    mapping, taken = {}, set()
    for col in df.columns:
        canon = lookup.get(_norm(col))
        if canon and canon not in taken:
            mapping[col] = canon
            taken.add(canon)
    return df.rename(columns=mapping)


def read_table(file, filename: str | None = None) -> pd.DataFrame:
    """Read a CSV/XLSX from a path, bytes or an uploaded file object."""
    name = (filename or getattr(file, "name", "") or str(file)).lower()
    try:
        if isinstance(file, (str, Path)):
            data = Path(file).read_bytes()
        elif isinstance(file, bytes):
            data = file
        else:
            data = file.getvalue() if hasattr(file, "getvalue") else file.read()
    except Exception as exc:
        raise DataError(f"Couldn't read the file ({exc}).") from exc
    if not data:
        raise DataError("The file is empty.")
    try:
        if name.endswith((".xlsx", ".xls", ".xlsm")):
            return pd.read_excel(io.BytesIO(data), dtype=str)
        for enc in ("utf-8-sig", "latin-1"):
            try:
                return pd.read_csv(io.BytesIO(data), dtype=str, encoding=enc,
                                   sep=None, engine="python", skip_blank_lines=True)
            except UnicodeDecodeError:
                continue
    except Exception as exc:
        raise DataError(f"Couldn't parse the file as {'Excel' if name.endswith('x') else 'CSV'} "
                        f"({exc}). Please upload a .csv or .xlsx file.") from exc
    raise DataError("Couldn't decode the file. Please save it as UTF-8 CSV or .xlsx.")


def clean(df: pd.DataFrame, kind: str) -> tuple[pd.DataFrame, list[str]]:
    """Normalise, validate and clean a raw table. Returns (df, notes)."""
    notes: list[str] = []
    label = kind.capitalize()
    if df is None or df.empty or len(df.columns) == 0:
        raise DataError(f"{label} file has no rows.")

    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]
    df = _rename_columns(df, kind)
    missing = [c for c in SCHEMAS[kind] if c not in df.columns]
    # Attendance can live without email/department; fill them in rather than reject.
    soft = {"attendance": {"email", "department"}}.get(kind, set())
    hard_missing = [c for c in missing if c not in soft]
    if hard_missing:
        found = ", ".join(str(c) for c in df.columns[:12])
        raise DataError(
            f"{label} file is missing required column(s): {', '.join(hard_missing)}. "
            f"Found columns: {found}. Expected: {', '.join(SCHEMAS[kind])}."
        )
    for c in missing:
        df[c] = ""
        notes.append(f"No '{c}' column - left blank.")

    df = df[SCHEMAS[kind]].copy()
    for c in df.columns:
        df[c] = df[c].astype("string").str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})

    before = len(df)
    df = df.dropna(how="all")
    required_values = [c for c in SCHEMAS[kind] if c not in OPTIONAL_VALUES.get(kind, set())]
    df = df.dropna(subset=[c for c in required_values if c not in NUMERIC.get(kind, [])])
    dropped_blank = before - len(df)

    for c in NUMERIC.get(kind, []):
        raw = df[c]
        num = pd.to_numeric(raw.str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce")
        bad = int((num.isna() & raw.notna()).sum())
        if bad:
            notes.append(f"{bad} non-numeric value(s) in '{c}' ignored.")
        df[c] = num
    if NUMERIC.get(kind):
        b = len(df)
        df = df.dropna(subset=NUMERIC[kind])
        dropped_blank += b - len(df)

    if kind == "attendance":
        df["classes_held"] = df["classes_held"].clip(lower=0)
        over = int((df["classes_attended"] > df["classes_held"]).sum())
        if over:
            notes.append(f"{over} row(s) had attended > held; capped at held.")
        df["classes_attended"] = df[["classes_attended", "classes_held"]].min(axis=1).clip(lower=0)
        df["email"] = df["email"].fillna("")
        df["department"] = df["department"].fillna("Unassigned")
    if kind == "marks":
        b = len(df)
        df = df[df["max_marks"] > 0]
        dropped_blank += b - len(df)
        df["test_name"] = df["test_name"].fillna("Test")
    if kind == "timetable":
        df["status"] = df["status"].str.lower()
    if kind == "staff":
        for c in ("teacher_name", "teacher_email", "adviser_name", "adviser_email"):
            df[c] = df[c].fillna("")

    if dropped_blank:
        notes.append(f"{dropped_blank} incomplete row(s) skipped.")
    b = len(df)
    df = df.drop_duplicates()
    if b - len(df):
        notes.append(f"{b - len(df)} duplicate row(s) removed.")

    if df.empty:
        raise DataError(f"{label} file has no usable rows after cleaning.")

    for c in df.columns:
        if c not in NUMERIC.get(kind, []):
            df[c] = df[c].astype(object).where(df[c].notna(), "")
    return df.reset_index(drop=True), notes


def load(file, kind: str, filename: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    return clean(read_table(file, filename), kind)


def load_sample() -> dict:
    """Load all four sample files. Returns {kind: (df, notes)}."""
    files = {"attendance": "attendance.csv", "marks": "marks.csv",
             "staff": "staff.csv", "timetable": "timetable.csv"}
    return {k: load(SAMPLE_DIR / f, k) for k, f in files.items()}
