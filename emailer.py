"""Email composition and Gmail SMTP sending. No Streamlit imports.

Every message is sent inside its own try/except so one failure never stops
the batch; send_batch returns one result row per message.
"""

from __future__ import annotations

import html
import re
import smtplib
import ssl
from dataclasses import dataclass, replace
from email.message import EmailMessage

from logic import format_needed, recovery_message

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BOOKING_TEXT = ("Need help catching up? Book a one-to-one slot with your subject teacher "
                "in the AttendGuard Appointments tab, or simply reply to this email.")

STATUS_COLORS = {"SAFE": "#15803d", "WARNING": "#b45309", "CRITICAL": "#b91c1c"}


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str
    kind: str = ""
    recipient_name: str = ""
    original_to: str = ""


def valid_email(addr) -> bool:
    return bool(addr) and bool(EMAIL_RE.match(str(addr).strip()))


def apply_test_mode(emails, enabled: bool, test_address: str):
    """Redirect every email to test_address, noting the real recipient in the subject."""
    out = []
    for e in emails:
        orig = e.to or "(no address)"
        if enabled:
            out.append(replace(e, to=test_address.strip(), original_to=orig,
                               subject=f"[TEST -> {orig}] {e.subject}"))
        else:
            out.append(replace(e, original_to=orig))
    return out


# ---------------------------------------------------------------- sending

def send_batch(emails, smtp_user, smtp_pass, progress=None, sender_name="AttendGuard"):
    """Send emails one by one. progress(i, total, email) is called after each.

    Returns a list of dicts: recipient, sent_to, kind, subject, status, reason.
    """
    results, server, login_error = [], None, None
    total = len(emails)

    def connect():
        ctx = ssl.create_default_context()
        s = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=20)
        s.login(smtp_user, smtp_pass)
        return s

    for i, e in enumerate(emails, 1):
        row = {"recipient": e.recipient_name or e.original_to or e.to,
               "original_address": e.original_to or e.to, "sent_to": e.to,
               "kind": e.kind, "subject": e.subject, "status": "failed", "reason": ""}
        try:
            if not smtp_user or not smtp_pass:
                raise RuntimeError("SMTP credentials missing - add SMTP_USER and SMTP_PASS to secrets.")
            if not valid_email(e.to):
                raise ValueError(f"Invalid email address: '{e.to}'")
            if login_error:
                raise RuntimeError(login_error)
            if server is None:
                try:
                    server = connect()
                except smtplib.SMTPAuthenticationError:
                    login_error = ("Gmail rejected the login - check SMTP_USER and that "
                                   "SMTP_PASS is a 16-character App Password.")
                    raise RuntimeError(login_error)
                except Exception as exc:
                    login_error = f"Couldn't connect to Gmail SMTP: {exc}"
                    raise RuntimeError(login_error)
            msg = EmailMessage()
            msg["From"] = f"{sender_name} <{smtp_user}>"
            msg["To"] = e.to
            msg["Subject"] = e.subject
            msg.set_content(e.text)
            msg.add_alternative(e.html, subtype="html")
            try:
                server.send_message(msg)
            except smtplib.SMTPServerDisconnected:
                server = connect()          # one reconnect attempt, then give up on this message
                server.send_message(msg)
            row.update(status="sent", reason="")
        except Exception as exc:
            row["reason"] = str(exc) or exc.__class__.__name__
            if isinstance(exc, smtplib.SMTPServerDisconnected):
                server = None
        results.append(row)
        if progress:
            try:
                progress(i, total, e)
            except Exception:
                pass
    if server is not None:
        try:
            server.quit()
        except Exception:
            pass
    return results


# ---------------------------------------------------------------- composition

def _fmt_pct(v) -> str:
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return "-"


def html_table(headers, rows) -> str:
    th = "".join(f'<th style="text-align:left;padding:6px 10px;background:#f1f5f9;'
                 f'border-bottom:1px solid #e2e8f0">{html.escape(str(h))}</th>' for h in headers)
    body = ""
    for r in rows:
        tds = ""
        for cell in r:
            txt = html.escape(str(cell))
            color = STATUS_COLORS.get(str(cell))
            style = f"color:{color};font-weight:600;" if color else ""
            tds += f'<td style="padding:6px 10px;border-bottom:1px solid #f1f5f9;{style}">{txt}</td>'
        body += f"<tr>{tds}</tr>"
    return (f'<table style="border-collapse:collapse;font-size:14px;margin:8px 0">'
            f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>")


def text_table(headers, rows) -> str:
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(str(h)), *(len(r[i]) for r in rows)) if rows else len(str(h))
              for i, h in enumerate(headers)]
    line = lambda cells: "  ".join(c.ljust(w) for c, w in zip(cells, widths))
    return "\n".join([line([str(h) for h in headers]), line(["-" * w for w in widths])]
                     + [line(r) for r in rows])


def _wrap_html(inner: str) -> str:
    return (f'<div style="font-family:Segoe UI,Arial,sans-serif;color:#0f172a;max-width:680px;'
            f'line-height:1.5">{inner}<p style="color:#64748b;font-size:12px;margin-top:24px">'
            f"Sent by AttendGuard - Student Attendance &amp; Performance Early-Warning System</p></div>")


def student_warning(student: dict, subjects: list[dict], target_pct: float) -> Email:
    """Personalised warning for one student. subjects = per-subject rows from logic."""
    name = student.get("name", "Student")
    first = str(name).split()[0] if name else "Student"
    headers = ["Subject", "Attended / Held", "Attendance", "Classes needed", "Status"]
    rows = [[s["subject"], f"{int(s['classes_attended'])} / {int(s['classes_held'])}",
             _fmt_pct(s["attendance_pct"]), format_needed(s["classes_needed"]), s["status"]]
            for s in subjects]
    plan = [recovery_message(s["subject"], s["classes_needed"], target_pct)
            for s in subjects if s["classes_needed"] != 0]
    weak = [s for s in subjects if s.get("weak")]
    weak_lines = [f"{s['subject']}: latest test {_fmt_pct(s.get('latest_pct'))} ({s.get('trend', '')})"
                  for s in weak]

    overall = _fmt_pct(student.get("attendance_pct"))
    status = student.get("status", "")
    intro = (f"Your overall attendance is {overall} against the required {target_pct:g}% "
             f"(status: {status}). Here is your subject-wise picture:")

    text = [f"Dear {first},", "", intro, "", text_table(headers, rows), ""]
    if plan:
        text += ["Your recovery plan:"] + [f"  - {p}" for p in plan] + [""]
    if weak_lines:
        text += ["Your recent marks need attention:"] + [f"  - {w}" for w in weak_lines] + [""]
    text += [BOOKING_TEXT, "", "We're here to help you get back on track.", "AttendGuard"]

    h = f"<p>Dear {html.escape(first)},</p><p>{html.escape(intro)}</p>{html_table(headers, rows)}"
    if plan:
        h += "<p><b>Your recovery plan</b></p><ul>" + "".join(f"<li>{html.escape(p)}</li>" for p in plan) + "</ul>"
    if weak_lines:
        h += ("<p><b>Your recent marks need attention</b></p><ul>"
              + "".join(f"<li>{html.escape(w)}</li>" for w in weak_lines) + "</ul>")
    h += (f'<p style="background:#eff6ff;padding:10px 12px;border-radius:6px">'
          f"{html.escape(BOOKING_TEXT)}</p><p>We're here to help you get back on track.</p>")

    return Email(to=str(student.get("email", "")).strip(),
                 subject=f"Attendance alert: {status} - action needed ({overall})",
                 text="\n".join(text), html=_wrap_html(h), kind="Student warning",
                 recipient_name=str(name))


def staff_alert(staff_name: str, staff_email: str, role: str, scope: str,
                rows: list[dict], target_pct: float) -> Email:
    """Summary of at-risk students for a teacher (per subject) or adviser (per department)."""
    headers = ["Student", "ID", "Department", "Subject", "Attendance", "Classes needed",
               "Marks trend", "Risk", "Status"]
    table = [[r["name"], r["student_id"], r["department"], r.get("subject", "All"),
              _fmt_pct(r["attendance_pct"]), r.get("needed_text") or format_needed(r["classes_needed"]),
              r.get("trend", ""), r.get("risk_score", ""), r["status"]] for r in rows]
    n = len(rows)
    intro = (f"{n} student{'s' if n != 1 else ''} in {scope} need{'s' if n == 1 else ''} attention "
             f"(attendance target {target_pct:g}%).")
    greet = f"Dear {staff_name}," if staff_name else "Hello,"
    text = "\n".join([greet, "", intro, "", text_table(headers, table), "",
                      "Students have been sent a personalised recovery plan. "
                      "A quick check-in from you can make a big difference.", "", "AttendGuard"])
    h = (f"<p>{html.escape(greet)}</p><p>{html.escape(intro)}</p>{html_table(headers, table)}"
         f"<p>Students have been sent a personalised recovery plan. "
         f"A quick check-in from you can make a big difference.</p>")
    return Email(to=str(staff_email or "").strip(),
                 subject=f"AttendGuard {role} alert: {n} at-risk student{'s' if n != 1 else ''} in {scope}",
                 text=text, html=_wrap_html(h), kind=f"{role} alert", recipient_name=staff_name)


def weekly_summary(adviser_name: str, adviser_email: str, department: str, stats: dict,
                   top_rows: list[dict], subject_rows: list[dict], target_pct: float) -> Email:
    kpi_headers = ["Students", "Critical", "Warning", "Safe", "Avg attendance", "Weak marks"]
    kpi = [[stats["students"], stats["critical"], stats["warning"], stats["safe"],
            _fmt_pct(stats["avg_attendance"]), stats["weak"]]]
    subj_headers = ["Subject", "Avg attendance", "Critical", "Warning"]
    subj = [[r["subject"], _fmt_pct(r["avg_attendance"]), r["critical"], r["warning"]] for r in subject_rows]
    top_headers = ["Student", "Attendance", "Classes needed", "Marks trend", "Risk", "Status"]
    top = [[r["name"], _fmt_pct(r["attendance_pct"]), r.get("needed_text") or format_needed(r["classes_needed"]),
            r["marks_trend"], r["risk_score"], r["status"]] for r in top_rows]
    greet = f"Dear {adviser_name}," if adviser_name else "Hello,"
    intro = f"Here is this week's attendance and performance summary for {department} (target {target_pct:g}%)."
    text = "\n".join([greet, "", intro, "", text_table(kpi_headers, kpi), "", "By subject:",
                      text_table(subj_headers, subj), "", "Highest-risk students:",
                      text_table(top_headers, top) if top else "None - great week!", "", "AttendGuard"])
    h = (f"<p>{html.escape(greet)}</p><p>{html.escape(intro)}</p>{html_table(kpi_headers, kpi)}"
         f"<p><b>By subject</b></p>{html_table(subj_headers, subj)}"
         f"<p><b>Highest-risk students</b></p>"
         + (html_table(top_headers, top) if top else "<p>None - great week!</p>"))
    return Email(to=str(adviser_email or "").strip(),
                 subject=f"AttendGuard weekly summary - {department}",
                 text=text, html=_wrap_html(h), kind="Weekly summary", recipient_name=adviser_name)


def booking_confirmation(to_name: str, to_email: str, student_name: str, teacher_name: str,
                         subject: str, day: str, slot: str, for_teacher: bool) -> Email:
    if for_teacher:
        line = f"{student_name} has booked a support meeting with you for {subject}."
    else:
        line = f"Your support meeting with {teacher_name} for {subject} is confirmed."
    when = f"{day}, {slot}"
    text = "\n".join([f"Dear {to_name},", "", line, f"When: {when}", "", "AttendGuard"])
    h = (f"<p>Dear {html.escape(to_name)},</p><p>{html.escape(line)}</p>"
         f'<p style="background:#f0fdf4;padding:10px 12px;border-radius:6px"><b>When:</b> {html.escape(when)}</p>')
    return Email(to=str(to_email or "").strip(),
                 subject=f"Meeting confirmed: {subject} - {when}",
                 text=text, html=_wrap_html(h), kind="Booking confirmation", recipient_name=to_name)
