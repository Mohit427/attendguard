"""Automated voice calls via the Twilio REST API. No Streamlit imports.

Each call is placed inside its own try/except so one failure never stops the
batch; place_calls returns one result row per call, in the same shape as
emailer.send_batch so the UI can show both in one results table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from xml.sax.saxutils import escape

from logic import is_recoverable

TWILIO_CALLS_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
VOICE, LANGUAGE = "Polly.Aditi", "en-IN"

# Friendlier text for the Twilio errors people actually hit.
TWILIO_HINTS = {
    20003: "Twilio rejected the credentials - check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.",
    21210: "TWILIO_FROM_NUMBER isn't a Twilio number on this account.",
    21211: "Invalid phone number.",
    21214: "Phone number can't be reached.",
    21215: "Calling this country is disabled - enable it in Twilio Console > Voice > Geo permissions.",
    21219: "Trial accounts can only call verified numbers - verify it in Twilio Console > Verified Caller IDs.",
}


@dataclass
class Call:
    to: str
    script: str
    recipient_name: str = ""
    original_to: str = ""
    kind: str = "Voice call"


def normalize_phone(raw, default_cc: str = "+91") -> str:
    """Best-effort E.164: '98765 43210' -> '+919876543210'. Returns '' if unusable."""
    s = str(raw or "").strip()
    if not s or s.lower() in ("nan", "none"):
        return ""
    s = re.sub(r"\.0$", "", s)
    plus = s.startswith("+") or s.startswith("00")
    digits = re.sub(r"\D", "", s)
    if s.startswith("00"):
        digits = digits[2:]
    if plus:
        out = "+" + digits
    elif len(digits) == 10:
        out = default_cc + digits
    elif len(digits) == 11 and digits.startswith("0"):
        out = default_cc + digits[1:]
    elif len(digits) == 12 and digits.startswith(default_cc.lstrip("+")):
        out = "+" + digits
    else:
        out = "+" + digits
    return out if E164_RE.match(out) else ""


def valid_phone(p) -> bool:
    return bool(E164_RE.match(str(p or "")))


def _pct(v) -> str:
    try:
        return f"{float(v):.1f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "unknown"


def call_script(student: dict, subjects: list[dict], target_pct: float) -> str:
    """Short spoken message: who, how bad, the single most useful next step."""
    first = (str(student.get("name") or "student").split() or ["student"])[0]
    lines = [f"Hello {first}. This is an automated call from AttendGuard, your college's attendance system.",
             f"Your overall attendance is {_pct(student.get('attendance_pct'))} percent, "
             f"against the required {_pct(target_pct)} percent."]
    behind = [s for s in subjects if s.get("classes_needed") != 0]  # None/NaN = can't recover
    recoverable = sorted((s for s in behind if is_recoverable(s.get("classes_needed"))),
                         key=lambda s: s["classes_needed"])
    lost = [s for s in behind if not is_recoverable(s.get("classes_needed"))]
    if recoverable:
        s = recoverable[0]
        n = int(s["classes_needed"])
        lines.append(f"To get back on track in {s['subject']}, please attend the next {n} "
                     f"class{'es' if n != 1 else ''} in a row.")
        if len(recoverable) > 1:
            lines.append(f"You are also behind in {len(recoverable) - 1} other "
                         f"subject{'s' if len(recoverable) > 2 else ''}.")
    if lost:
        lines.append(f"In {', '.join(s['subject'] for s in lost)}, you can no longer reach the target this term. "
                     f"Please meet your teacher this week.")
    weak = [s["subject"] for s in subjects if s.get("weak")]
    if weak:
        lines.append(f"Your recent marks in {', '.join(weak[:3])} also need attention.")
    lines.append("We have emailed you a full recovery plan. You can book a meeting with your teacher "
                 "through AttendGuard. Thank you, and goodbye.")
    return " ".join(lines)


def twiml(script: str) -> str:
    say = f'<Say voice="{VOICE}" language="{LANGUAGE}">{escape(script)}</Say>'
    return f"<Response><Pause length=\"1\"/>{say}</Response>"


def apply_test_mode(calls, enabled: bool, test_phone: str):
    out = []
    for c in calls:
        orig = c.to or "(no phone)"
        out.append(replace(c, to=test_phone.strip(), original_to=orig) if enabled
                   else replace(c, original_to=orig))
    return out


def _twilio_error(resp) -> str:
    try:
        data = resp.json()
        code, msg = data.get("code"), data.get("message", "")
    except Exception:
        code, msg = None, resp.text[:200]
    hint = TWILIO_HINTS.get(code)
    return f"{hint} (Twilio {code})" if hint else f"Twilio error {code or resp.status_code}: {msg}"


def place_calls(calls, account_sid, auth_token, from_number, progress=None, http=None):
    """Place calls one by one. progress(i, total, call) is called after each.

    Returns rows: recipient, original_address, sent_to, kind, subject, status, reason.
    """
    if http is None:
        import requests as http
    results, total, fatal = [], len(calls), None
    for i, c in enumerate(calls, 1):
        row = {"recipient": c.recipient_name or c.original_to or c.to, "original_address": c.original_to or c.to,
               "sent_to": c.to, "kind": c.kind, "subject": c.script[:80] + "...",
               "status": "failed", "reason": ""}
        try:
            if not (account_sid and auth_token and from_number):
                raise RuntimeError("Twilio not configured - add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN "
                                   "and TWILIO_FROM_NUMBER to secrets.")
            if fatal:
                raise RuntimeError(fatal)
            if not valid_phone(c.to):
                raise ValueError(f"Invalid phone number: '{c.to or '(blank)'}'")
            resp = http.post(TWILIO_CALLS_URL.format(sid=account_sid), auth=(account_sid, auth_token),
                             data={"To": c.to, "From": from_number, "Twiml": twiml(c.script)}, timeout=20)
            if resp.status_code in (200, 201):
                info = resp.json()
                row.update(status="sent", reason=f"Call {info.get('status', 'queued')} ({info.get('sid', '')})")
            else:
                reason = _twilio_error(resp)
                if resp.status_code == 401:
                    fatal = reason  # bad credentials: don't hammer Twilio for every row
                raise RuntimeError(reason)
        except Exception as exc:
            row["reason"] = str(exc) or exc.__class__.__name__
        results.append(row)
        if progress:
            try:
                progress(i, total, c)
            except Exception:
                pass
    return results
