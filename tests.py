"""Quick checks for the recovery formula, risk flags and data loading.

Run:  python tests.py
"""

import math

import logic as L


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    return bool(cond)


def run():
    ok = True
    # --- recovery formula
    ok &= check("zero classes held -> 100%, needs 0", L.attendance_pct(0, 0) == 100.0 and L.classes_needed(0, 0, 85) == 0)
    ok &= check("100% attendance -> needs 0", L.classes_needed(40, 40, 85) == 0)
    ok &= check("exactly at target (17/20 @85) -> 0, no float noise", L.classes_needed(20, 17, 85) == 0)
    # 30/40 @ 85: (34 - 30) / 0.15 = 26.67 -> 27; check it really reaches 85%
    x = L.classes_needed(40, 30, 85)
    ok &= check("30/40 @85 -> 27", x == 27 and (30 + x) / (40 + x) >= 0.85 and (30 + x - 1) / (40 + x - 1) < 0.85)
    ok &= check("0/10 @85 -> 57 (recoverable)", L.classes_needed(10, 0, 85) == 57 and L.is_recoverable(57))
    ok &= check("huge gap -> can't recover", L.format_needed(L.classes_needed(100, 20, 85)) == "Can't recover this term")
    ok &= check("target 100% with an absence -> None", L.classes_needed(10, 9, 100) is None and not L.is_recoverable(None))
    ok &= check("attended > held is capped", L.attendance_pct(10, 12) == 100.0 and L.classes_needed(10, 12, 85) == 0)
    ok &= check("garbage input doesn't crash", L.classes_needed("abc", None, 85) == 0 and L.attendance_pct(float("nan"), 3) == 100.0)

    ok &= check("student total = sum of subjects", L.total_needed([0, 5, 12]) == 17)
    ok &= check("student total unrecoverable if any subject is", L.total_needed([3, 400]) is None
                and L.format_needed(None, limit=None) == "Can't recover this term"
                and L.format_needed(150, limit=None) == "150"
                and L.format_needed(float("nan"), limit=None) == "Can't recover this term")

    # --- status bands
    ok &= check("status SAFE at target+5", L.attendance_status(90, 85) == L.SAFE)
    ok &= check("status WARNING at target", L.attendance_status(85, 85) == L.WARNING)
    ok &= check("status WARNING at 89.9", L.attendance_status(89.9, 85) == L.WARNING)
    ok &= check("status CRITICAL below target", L.attendance_status(84.99, 85) == L.CRITICAL)

    # --- marks flags
    ok &= check("latest < 40% is weak", L.is_weak(35, None))
    ok &= check("drop of 12 points is weak", L.is_weak(60, 72) and L.trend_label(60, 72) == L.FALLING)
    ok &= check("drop of exactly 10 is not weak", not L.is_weak(60, 70))
    ok &= check("missing marks -> not weak, 'No marks'", not L.is_weak(None, None) and L.trend_label(None, None) == L.NO_MARKS)
    ok &= check("improving trend", L.trend_label(70, 60) == L.IMPROVING and L.trend_label(62, 60) == L.STABLE)

    # --- risk score
    ok &= check("perfect student risk 0", L.risk_score(100, 85, 0, 5, L.STABLE) == 0)
    ok &= check("risk capped at 100", L.risk_score(0, 85, 5, 5, L.FALLING) == 100)
    ok &= check("missing marks doesn't crash", L.risk_score(80, 85, 0, 0, L.NO_MARKS) == 30.0)
    ok &= check("weak marks raise risk", L.risk_score(95, 85, 2, 4, L.FALLING) == 27.5)

    # --- end-to-end with pandas + sample data
    try:
        import pandas as pd
        import data_loader as D
        data = D.load_sample()
        rep = L.build_report(data["attendance"][0], data["marks"][0], 85)
        s = rep["students"]
        ok &= check("sample: 40 students", len(s) == 40)
        ok &= check("sample: all three statuses present", set(s["status"]) == {L.SAFE, L.WARNING, L.CRITICAL})
        ok &= check("sample: sorted by risk desc", s["risk_score"].is_monotonic_decreasing)
        ok &= check("sample: one student can't recover (demo case)", s["classes_needed"].isna().sum() >= 1)
        ok &= check("sample: duplicate row noted", any("duplicate" in n for n in data["attendance"][1]))
        free = data["timetable"][0].query("status == 'free'")["teacher_name"].nunique()
        ok &= check("sample: every teacher has a free slot", free == data["staff"][0]["teacher_name"].nunique())

        # student with no marks at all
        att = pd.DataFrame([{"student_id": "X1", "name": "No Marks", "email": "", "department": "D",
                             "subject": "Math", "classes_held": 10, "classes_attended": 5}])
        r2 = L.build_report(att, pd.DataFrame(columns=D.SCHEMAS["marks"]), 85)["students"].iloc[0]
        ok &= check("no marks file -> trend 'No marks', still scored",
                    r2["marks_trend"] == L.NO_MARKS and r2["status"] == L.CRITICAL and r2["risk_score"] == 60)

        # messy headers + aliases + junk values
        messy = b" Roll No ,Student Name,EMAIL , Dept,Course,Total Classes,Attended\nA1,Ann,a@x.com,CS,Math,20,abc\nA1,Ann,a@x.com,CS,Math,20,abc\nA2,Bob,,CS,Math,20,18\n,,,,,,\n"
        df, notes = D.load(messy, "attendance", "messy.csv")
        ok &= check("messy CSV: aliases mapped, junk row skipped", list(df["student_id"]) == ["A2"] and notes)
        try:
            D.load(b"student_id,name\n1,a\n", "attendance", "bad.csv")
            ok &= check("missing column raises DataError", False)
        except D.DataError as e:
            ok &= check("missing column raises friendly DataError", "classes_held" in str(e))
    except ImportError as exc:
        print(f"SKIP pandas checks ({exc})")

    print("\nALL PASSED" if ok else "\nSOME CHECKS FAILED")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
