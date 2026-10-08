"""AttendGuard - Student Attendance & Performance Early-Warning System."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data_loader as D
import emailer as E
import logic as L

st.set_page_config(page_title="AttendGuard", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

STATUS_COLORS = {L.CRITICAL: "#dc2626", L.WARNING: "#f59e0b", L.SAFE: "#16a34a"}
STATUS_BG = {L.CRITICAL: "#fee2e2", L.WARNING: "#fef3c7", L.SAFE: "#dcfce7"}
TREND_ICON = {L.FALLING: "↘ Falling", L.STABLE: "→ Stable", L.IMPROVING: "↗ Improving", L.NO_MARKS: "– No marks"}
PLOT_CFG = {"displayModeBar": False}
FILE_LABELS = {
    "attendance": ("Attendance", "student_id, name, email, department, subject, classes_held, classes_attended"),
    "marks": ("Marks", "student_id, subject, test_name, test_date, marks, max_marks"),
    "staff": ("Staff", "department, subject, teacher_name, teacher_email, adviser_name, adviser_email"),
    "timetable": ("Timetable (optional)", "teacher_name, day, time_slot, status (free/busy)"),
}

st.markdown("""
<style>
.block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px;}
.ag-header {display:flex; align-items:center; gap:14px; margin-bottom: .25rem;}
.ag-logo {font-size: 2.1rem; line-height: 1;}
.ag-title {font-size: 1.9rem; font-weight: 700; color:#0f172a; margin:0;}
.ag-sub {color:#64748b; margin: 0 0 1.2rem 0; font-size: .98rem;}
.ag-card {background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:14px 18px;
          box-shadow: 0 1px 2px rgba(15,23,42,.04); height: 100%;}
.ag-card .lbl {color:#64748b; font-size:.82rem; font-weight:600; text-transform:uppercase; letter-spacing:.04em;}
.ag-card .val {font-size:1.9rem; font-weight:700; color:#0f172a; margin-top:2px;}
.ag-card .hint {color:#94a3b8; font-size:.78rem;}
.ag-card.critical {border-left: 5px solid #dc2626;}
.ag-card.warning {border-left: 5px solid #f59e0b;}
.ag-card.safe {border-left: 5px solid #16a34a;}
.ag-card.neutral {border-left: 5px solid #2563eb;}
.ag-badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:.78rem; font-weight:700;
           letter-spacing:.03em;}
.ag-banner {padding:10px 14px; border-radius:10px; margin-bottom: 12px; font-weight:500;}
.ag-banner.test {background:#eff6ff; border:1px solid #bfdbfe; color:#1e3a8a;}
.ag-banner.live {background:#fef2f2; border:1px solid #fecaca; color:#991b1b;}
.ag-empty {text-align:center; padding: 2.5rem 1rem; border:1px dashed #cbd5e1; border-radius:14px;
           background:#f8fafc; color:#475569;}
div[data-testid="stTabs"] button p {font-size: 1rem; font-weight: 600;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers

def get_secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "") or "")
    except Exception:
        return ""


def badge(status: str) -> str:
    return (f'<span class="ag-badge" style="background:{STATUS_BG.get(status, "#e2e8f0")};'
            f'color:{STATUS_COLORS.get(status, "#334155")}">{status}</span>')


def card(label: str, value, hint: str = "", kind: str = "neutral") -> str:
    return (f'<div class="ag-card {kind}"><div class="lbl">{label}</div>'
            f'<div class="val">{value}</div><div class="hint">{hint}</div></div>')


def style_status(df: pd.DataFrame, col: str = "Status"):
    def f(v):
        c = STATUS_COLORS.get(v)
        return f"background-color:{STATUS_BG[v]};color:{c};font-weight:700" if c else ""
    return df.style.map(f, subset=[col])


def student_needed(n) -> str:
    """Per-student total (sum over subjects) - no per-subject cap."""
    return L.format_needed(n, limit=None)


def empty_state(title: str, body: str):
    st.markdown(f'<div class="ag-empty"><h4 style="margin:0 0 .4rem 0">{title}</h4>'
                f'<div>{body}</div></div>', unsafe_allow_html=True)


def init_state():
    ss = st.session_state
    ss.setdefault("data", {})        # kind -> DataFrame
    ss.setdefault("notes", {})       # kind -> list[str]
    ss.setdefault("source", {})      # kind -> "sample" | filename
    ss.setdefault("upload_sig", {})  # kind -> signature of the last processed upload
    ss.setdefault("bookings", [])
    ss.setdefault("send_results", None)


def load_sample_into_state():
    try:
        sample = D.load_sample()
    except Exception as exc:
        st.error(f"Couldn't load sample data: {exc}")
        return
    for kind, (df, notes) in sample.items():
        st.session_state.data[kind] = df
        st.session_state.notes[kind] = notes
        st.session_state.source[kind] = "sample data"
    st.session_state.upload_sig = {}
    st.session_state.bookings = []
    st.session_state.send_results = None


def handle_upload(kind: str, file):
    if file is None:
        return
    sig = (file.name, file.size)
    if st.session_state.upload_sig.get(kind) == sig:
        return
    st.session_state.upload_sig[kind] = sig
    try:
        df, notes = D.load(file, kind, file.name)
    except D.DataError as exc:
        st.session_state.notes[kind] = [f"ERROR: {exc}"]
        return
    except Exception as exc:
        st.session_state.notes[kind] = [f"ERROR: Unexpected problem reading {file.name}: {exc}"]
        return
    st.session_state.data[kind] = df
    st.session_state.notes[kind] = notes
    st.session_state.source[kind] = file.name
    st.session_state.send_results = None


@st.cache_data(show_spinner=False)
def compute_report(att: pd.DataFrame, marks: pd.DataFrame | None, target: float):
    m = marks if marks is not None else pd.DataFrame(columns=D.SCHEMAS["marks"])
    return L.build_report(att, m, target)


def marks_pct_table(marks: pd.DataFrame | None) -> pd.DataFrame:
    if marks is None or marks.empty:
        return pd.DataFrame(columns=["student_id", "subject", "test_name", "date", "pct"])
    m = marks.copy()
    m["date"] = pd.to_datetime(m["test_date"], errors="coerce")
    m["pct"] = (m["marks"] / m["max_marks"] * 100).round(1)
    m["_order"] = range(len(m))
    return m.sort_values(["date", "_order"], na_position="first")


# ---------------------------------------------------------------- sidebar

init_state()
ss = st.session_state

with st.sidebar:
    st.markdown("## 🛡️ AttendGuard")
    st.caption("Upload your files or try the sample data.")
    if st.button("📂 Load sample data", width="stretch", type="primary",
                 help="Loads 40 realistic students across 3 departments and 5 subjects."):
        load_sample_into_state()

    for kind, (label, cols) in FILE_LABELS.items():
        f = st.file_uploader(label, type=["csv", "xlsx", "xls"], key=f"up_{kind}",
                             help=f"Columns: {cols}. Headers are case-insensitive; common aliases like 'Roll No' work.")
        handle_upload(kind, f)
        notes = ss.notes.get(kind, [])
        errors = [n for n in notes if n.startswith("ERROR:")]
        if errors:
            st.error(errors[0][7:])
        elif kind in ss.data:
            st.caption(f"✅ {len(ss.data[kind])} rows from *{ss.source.get(kind, '')}*")
            for n in notes:
                st.caption(f"ℹ️ {n}")

    if ss.data and st.button("Clear all data", width="stretch",
                             help="Forget all loaded files, bookings and send results."):
        for k in ("data", "notes", "source", "upload_sig", "bookings"):
            ss[k] = {} if k != "bookings" else []
        ss.send_results = None
        st.rerun()

    st.divider()
    target = st.slider("Attendance target (%)", 50, 100, 85, 1,
                       help="SAFE ≥ target + 5 · WARNING within 5 points above target · CRITICAL below target.")
    st.divider()
    st.markdown("**Email settings**")
    test_mode = st.toggle("Test mode", value=True, key="test_mode",
                          help="Redirects ALL outgoing emails to the test address below. "
                               "The real recipient is noted in the subject line.")
    test_address = st.text_input("Test address", value=ss.get("test_address", get_secret("SMTP_USER")),
                                 placeholder="you@example.com", key="test_address_input",
                                 help="Every email goes here while test mode is on.")
    ss.test_address = test_address
    smtp_user, smtp_pass = get_secret("SMTP_USER"), get_secret("SMTP_PASS")
    if smtp_user and smtp_pass:
        st.caption(f"✉️ Sending as {smtp_user}")
    else:
        st.caption("⚠️ Email not configured - add SMTP_USER and SMTP_PASS to secrets. Previews still work.")


# ---------------------------------------------------------------- header

st.markdown('<div class="ag-header"><div class="ag-logo">🛡️</div>'
            '<p class="ag-title">AttendGuard</p></div>'
            '<p class="ag-sub">Student attendance &amp; performance early-warning system - spot at-risk '
            'students, show them exactly how to recover, and alert the right staff.</p>',
            unsafe_allow_html=True)

if "attendance" not in ss.data:
    empty_state("No attendance data yet",
                "Upload an <b>attendance</b> file in the sidebar (CSV or Excel), or load the sample data "
                "to explore AttendGuard with 40 realistic students.")
    c = st.columns([2, 1, 2])[1]
    if c.button("📂 Load sample data", width="stretch", type="primary", key="load_main"):
        load_sample_into_state()
        st.rerun()
    with st.expander("Expected file formats"):
        for kind, (label, cols) in FILE_LABELS.items():
            st.markdown(f"**{label}:** `{cols}`")
    st.stop()

att_df = ss.data["attendance"]
marks_df = ss.data.get("marks")
staff_df = ss.data.get("staff")
tt_df = ss.data.get("timetable")

try:
    with st.spinner("Crunching attendance and marks..."):
        report = compute_report(att_df, marks_df, float(target))
except Exception as exc:
    st.error(f"Couldn't analyse the data: {exc}. Please check the uploaded files.")
    st.stop()

students = report["students"]
subjects = report["subjects"]
marks_pct = marks_pct_table(marks_df)

if marks_df is None:
    st.info("No marks file loaded - risk scores use attendance only. Upload a marks file to add performance flags.")

# KPI cards
counts = students["status"].value_counts()
avg_att = students["attendance_pct"].mean() if len(students) else 0
kpis = [
    ("Total students", len(students), f"{students['department'].nunique()} departments", "neutral"),
    ("Critical", int(counts.get(L.CRITICAL, 0)), f"below {target}%", "critical"),
    ("Warning", int(counts.get(L.WARNING, 0)), f"{target}-{target + 5}%", "warning"),
    ("Safe", int(counts.get(L.SAFE, 0)), f"≥ {target + 5}%", "safe"),
    ("Avg attendance", f"{avg_att:.1f}%", f"{int(students['at_risk'].sum())} students need attention", "neutral"),
]
for col, (lbl, val, hint, kind) in zip(st.columns(5), kpis):
    col.markdown(card(lbl, val, hint, kind), unsafe_allow_html=True)
st.write("")

tab_dash, tab_student, tab_alerts, tab_appt = st.tabs(
    ["📊 Dashboard", "🎓 Student view", "✉️ Alerts", "📅 Appointments"])


# ---------------------------------------------------------------- dashboard

with tab_dash:
    try:
        f1, f2, f3 = st.columns([2, 2, 1])
        depts = sorted(students["department"].astype(str).unique())
        subs = sorted(subjects["subject"].astype(str).unique())
        sel_d = f1.multiselect("Department", depts, placeholder="All departments")
        sel_s = f2.multiselect("Subject", subs, placeholder="All subjects",
                               help="Attendance and status are recomputed over the selected subjects only.")
        show_safe = f3.toggle("Include SAFE", value=False, key="show_safe", help="Show safe students in the ranked table too.")

        if sel_d or sel_s:
            a = att_df
            if sel_d:
                a = a[a["department"].astype(str).isin(sel_d)]
            if sel_s:
                a = a[a["subject"].astype(str).isin(sel_s)]
            m = marks_df
            if m is not None and sel_s:
                m = m[m["subject"].astype(str).isin(sel_s)]
            view = compute_report(a, m, float(target)) if len(a) else None
        else:
            view = report

        if view is None or view["students"].empty:
            empty_state("No students match these filters", "Try a different department or subject.")
        else:
            vs, vsub = view["students"], view["subjects"]
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### Risk by department")
                dd = (vs.groupby(["department", "status"]).size().reset_index(name="students"))
                fig = px.bar(dd, x="department", y="students", color="status",
                             color_discrete_map=STATUS_COLORS,
                             category_orders={"status": L.STATUS_ORDER})
                fig.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="",
                                  xaxis_title=None, yaxis_title="Students", bargap=0.35,
                                  plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.1))
                st.plotly_chart(fig, width="stretch", config=PLOT_CFG)
            with c2:
                st.markdown("##### Risk by subject")
                sd = (vsub.groupby(["subject", "status"]).size().reset_index(name="students"))
                fig = px.bar(sd, x="subject", y="students", color="status",
                             color_discrete_map=STATUS_COLORS,
                             category_orders={"status": L.STATUS_ORDER})
                fig.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10), legend_title_text="",
                                  xaxis_title=None, yaxis_title="Students (per subject)", bargap=0.35,
                                  plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.1))
                st.plotly_chart(fig, width="stretch", config=PLOT_CFG)

            st.markdown("##### Ranked at-risk students")
            tbl = vs if show_safe else vs[vs["at_risk"]]
            if tbl.empty:
                st.success("No at-risk students for this selection. 🎉")
            else:
                out = pd.DataFrame({
                    "Name": tbl["name"], "Department": tbl["department"],
                    "Attendance %": tbl["attendance_pct"],
                    "Classes needed": tbl["classes_needed"].map(student_needed),
                    "Marks trend": tbl["marks_trend"].map(lambda t: TREND_ICON.get(t, t)),
                    "Risk score": tbl["risk_score"], "Status": tbl["status"],
                })
                st.dataframe(
                    style_status(out), hide_index=True, width="stretch",
                    height=min(38 + 35 * len(out), 520),
                    column_config={
                        "Attendance %": st.column_config.NumberColumn(format="%.1f%%"),
                        "Classes needed": st.column_config.TextColumn(
                            help="Total classes to attend in a row (summed over subjects) to reach the target in every subject"),
                        "Risk score": st.column_config.ProgressColumn(
                            min_value=0, max_value=100, format="%.0f",
                            help="0-100: attendance gap (up to 60) + weak/falling marks (up to 40)"),
                    })
                st.caption(f"{len(out)} students · most at-risk first · weak marks = latest test < 40% "
                           f"or a drop of more than 10 points.")
    except Exception as exc:
        st.error(f"Something went wrong drawing the dashboard: {exc}")


# ---------------------------------------------------------------- student view

with tab_student:
    try:
        labels = {sid: f"{n}  ·  {sid}  ·  {s}" for sid, n, s in
                  zip(students["student_id"], students["name"], students["status"])}
        sid = st.selectbox("Choose a student (most at-risk first)", list(labels),
                           format_func=lambda x: labels[x], key="student_pick")
        srow = students[students["student_id"] == sid].iloc[0]
        ssub = subjects[subjects["student_id"] == sid].sort_values("attendance_pct")

        st.markdown(f"### {srow['name']} &nbsp; {badge(srow['status'])}", unsafe_allow_html=True)
        st.caption(f"{srow['student_id']} · {srow['department']} · {srow['email'] or 'no email on file'}")
        k = st.columns(4)
        k[0].markdown(card("Overall attendance", f"{srow['attendance_pct']:.1f}%",
                           f"{int(srow['classes_attended'])} of {int(srow['classes_held'])} classes",
                           srow["status"].lower()), unsafe_allow_html=True)
        k[1].markdown(card("Classes needed", student_needed(srow["classes_needed"]),
                           "in a row, across all subjects"), unsafe_allow_html=True)
        k[2].markdown(card("Marks trend", TREND_ICON.get(srow["marks_trend"], srow["marks_trend"]),
                           ", ".join(srow["weak_subjects"]) and f"Weak: {', '.join(srow['weak_subjects'])}"
                           or "No weak subjects"), unsafe_allow_html=True)
        k[3].markdown(card("Risk score", f"{srow['risk_score']:.0f}/100", "higher = more at risk"),
                      unsafe_allow_html=True)
        st.write("")

        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("##### Attendance by subject")
            fig = go.Figure(go.Bar(
                x=ssub["attendance_pct"], y=ssub["subject"], orientation="h",
                marker_color=[STATUS_COLORS[s] for s in ssub["status"]],
                text=[f"{p:.1f}%" for p in ssub["attendance_pct"]], textposition="outside",
                hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
            fig.add_vline(x=target, line_dash="dash", line_color="#334155",
                          annotation_text=f"target {target}%", annotation_position="top")
            fig.update_layout(height=60 + 48 * len(ssub), margin=dict(l=10, r=40, t=30, b=10),
                              xaxis=dict(range=[0, 110], title=None), yaxis_title=None,
                              plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, width="stretch", config=PLOT_CFG)
        with c2:
            st.markdown("##### Recovery plan")
            for _, r in ssub.iterrows():
                msg = L.recovery_message(r["subject"], r["classes_needed"], target)
                if r["classes_needed"] == 0:
                    st.success(msg, icon="✅")
                elif L.is_recoverable(r["classes_needed"]):
                    st.warning(msg, icon="📌")
                else:
                    st.error(msg, icon="⛔")

        st.markdown("##### Subject details")
        det = pd.DataFrame({
            "Subject": ssub["subject"], "Attended": ssub["classes_attended"].astype(int),
            "Held": ssub["classes_held"].astype(int), "Attendance %": ssub["attendance_pct"],
            "Classes needed": ssub["classes_needed"].map(L.format_needed),
            "Latest test %": ssub["latest_pct"],
            "Marks trend": ssub["trend"].map(lambda t: TREND_ICON.get(t, t)),
            "Weak marks": ssub["weak"].map({True: "⚠️ Yes", False: ""}), "Status": ssub["status"],
        })
        st.dataframe(style_status(det), hide_index=True, width="stretch",
                     column_config={"Attendance %": st.column_config.NumberColumn(format="%.1f%%"),
                                    "Latest test %": st.column_config.NumberColumn(format="%.0f%%")})

        st.markdown("##### Marks trend")
        sm = marks_pct[marks_pct["student_id"] == sid]
        if sm.empty:
            st.info("No marks on record for this student.")
        else:
            sm = sm.assign(label=sm["test_name"].astype(str))
            fig = px.line(sm, x="label", y="pct", color="subject", markers=True,
                          hover_data={"test_date": True, "label": False})
            fig.add_hline(y=L.WEAK_MARK_PCT, line_dash="dot", line_color="#dc2626",
                          annotation_text="40% weak line", annotation_position="bottom right")
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), xaxis_title=None,
                              yaxis=dict(title="Score %", range=[0, 105]), legend_title_text="",
                              plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, width="stretch", config=PLOT_CFG)
    except Exception as exc:
        st.error(f"Couldn't show this student: {exc}")


# ---------------------------------------------------------------- email helpers

def mode_banner():
    if test_mode:
        addr = test_address.strip() or "(no test address set - add one in the sidebar)"
        st.markdown(f'<div class="ag-banner test">🧪 <b>Test mode is ON</b> - every email is redirected to '
                    f'<b>{addr}</b>. The real recipient is noted in the subject line.</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="ag-banner live">📨 <b>Live mode</b> - emails go to the real students and '
                    'staff addresses in your files.</div>', unsafe_allow_html=True)


def send_blocker() -> str | None:
    if not (smtp_user and smtp_pass):
        return "Email isn't configured yet - add SMTP_USER and SMTP_PASS to the app secrets."
    if test_mode and not E.valid_email(test_address):
        return "Test mode is on - enter a valid test address in the sidebar first."
    return None


def run_batch(emails, label: str):
    """Send a batch with a progress bar; store per-message results in session state."""
    if not emails:
        st.info("Nothing to send.")
        return
    emails = E.apply_test_mode(emails, test_mode, test_address)
    bar = st.progress(0.0, text=f"Sending {label}...")

    def prog(i, total, _e):
        bar.progress(i / total, text=f"Sending {label}: {i} of {total}")

    try:
        results = E.send_batch(emails, smtp_user, smtp_pass, progress=prog)
    except Exception as exc:  # send_batch is already per-message safe; this is a last resort
        st.error(f"Sending stopped unexpectedly: {exc}")
        return
    finally:
        bar.empty()
    ss.send_results = {"label": label, "rows": results, "test_mode": test_mode}
    sent = sum(r["status"] == "sent" for r in results)
    st.toast(f"{label}: {sent} sent, {len(results) - sent} failed", icon="✉️")


def show_results():
    res = ss.send_results
    if not res:
        st.caption("Results of your last send will appear here.")
        return
    df = pd.DataFrame(res["rows"])
    sent = int((df["status"] == "sent").sum())
    failed = len(df) - sent
    msg = f"**{res['label']}** - {sent} sent, {failed} failed" + (" (test mode)" if res["test_mode"] else "")
    (st.success if failed == 0 else st.warning)(msg)
    out = pd.DataFrame({"Recipient": df["recipient"], "Original address": df["original_address"],
                        "Delivered to": df["sent_to"], "Type": df["kind"],
                        "Result": df["status"].str.upper(), "Reason": df["reason"]})

    def color(v):
        return "color:#15803d;font-weight:700" if v == "SENT" else "color:#b91c1c;font-weight:700"
    st.dataframe(out.style.map(color, subset=["Result"]), hide_index=True, width="stretch")


def preview(email: E.Email):
    shown = E.apply_test_mode([email], test_mode, test_address)[0]
    with st.container(border=True):
        st.markdown(f"**To:** {shown.to or '_(missing address)_'}"
                    + (f" &nbsp;·&nbsp; _originally {shown.original_to}_" if test_mode else ""))
        st.markdown(f"**Subject:** {shown.subject}")
        st.html(email.html)
    with st.expander("Plain-text version"):
        st.code(email.text, language=None)


def student_email(sid) -> E.Email:
    srow = students[students["student_id"] == sid].iloc[0].to_dict()
    rows = subjects[subjects["student_id"] == sid].sort_values("attendance_pct").to_dict("records")
    return E.student_warning(srow, rows, target)


def _key(v) -> str:
    return str(v).strip().lower()


def staff_emails() -> list:
    """Teacher alerts (their at-risk students per subject) + adviser alerts (per department)."""
    if staff_df is None or staff_df.empty:
        return []
    risk = dict(zip(students["student_id"], students["risk_score"]))
    flagged = subjects[(subjects["status"] != L.SAFE) | subjects["weak"]].copy()
    flagged["risk_score"] = flagged["student_id"].map(risk)
    flagged["_d"], flagged["_s"] = flagged["department"].map(_key), flagged["subject"].map(_key)
    out = []
    for (tname, temail), g in staff_df.groupby(["teacher_name", "teacher_email"], sort=True):
        if not str(tname).strip() and not str(temail).strip():
            continue
        pairs = {(_key(d), _key(s)) for d, s in zip(g["department"], g["subject"])}
        subs_only = {_key(s) for d, s in zip(g["department"], g["subject"]) if not _key(d)}
        mine = flagged[[(d, s) in pairs or s in subs_only for d, s in zip(flagged["_d"], flagged["_s"])]]
        if mine.empty:
            continue
        mine = mine.sort_values("risk_score", ascending=False)
        scope = ", ".join(sorted(g["subject"].astype(str).unique()))
        out.append(E.staff_alert(tname, temail, "Teacher", scope, mine.to_dict("records"), target))
    risky = students[students["at_risk"]]
    for (aname, aemail), g in staff_df.groupby(["adviser_name", "adviser_email"], sort=True):
        if not str(aname).strip() and not str(aemail).strip():
            continue
        depts = {_key(d) for d in g["department"]}
        mine = risky[risky["department"].map(_key).isin(depts)]
        if mine.empty:
            continue
        rows = [dict(r, subject="All subjects", trend=r["marks_trend"],
                     needed_text=student_needed(r["classes_needed"])) for r in mine.to_dict("records")]
        scope = ", ".join(sorted(g["department"].astype(str).unique()))
        out.append(E.staff_alert(aname, aemail, "Adviser", scope, rows, target))
    return out


def weekly_emails() -> list:
    """One department-wise summary per (adviser, department)."""
    if staff_df is None or staff_df.empty:
        return []
    out = []
    advisers = staff_df.drop_duplicates(["department", "adviser_name", "adviser_email"])
    for _, a in advisers.iterrows():
        dk = _key(a["department"])
        ds = students[students["department"].map(_key) == dk]
        if ds.empty:
            continue
        dsub = subjects[subjects["department"].map(_key) == dk]
        stats = {"students": len(ds), "critical": int((ds["status"] == L.CRITICAL).sum()),
                 "warning": int((ds["status"] == L.WARNING).sum()),
                 "safe": int((ds["status"] == L.SAFE).sum()),
                 "avg_attendance": ds["attendance_pct"].mean(),
                 "weak": int(ds["weak_subjects"].map(bool).sum())}
        subj_rows = [{"subject": s, "avg_attendance": g["attendance_pct"].mean(),
                      "critical": int((g["status"] == L.CRITICAL).sum()),
                      "warning": int((g["status"] == L.WARNING).sum())}
                     for s, g in dsub.groupby("subject")]
        top = [dict(r, needed_text=student_needed(r["classes_needed"]))
               for r in ds[ds["at_risk"]].head(5).to_dict("records")]
        out.append(E.weekly_summary(a["adviser_name"], a["adviser_email"], a["department"],
                                    stats, top, subj_rows, target))
    return out


def email_label(e: E.Email) -> str:
    return f"{e.kind}: {e.recipient_name or e.to}"


# ---------------------------------------------------------------- alerts

with tab_alerts:
    try:
        mode_banner()
        blocker = send_blocker()
        if blocker:
            st.warning(blocker, icon="⚙️")

        st.markdown("#### 1 · Student warnings")
        at_risk = students[students["at_risk"]]
        if at_risk.empty:
            st.success("No at-risk students right now - nothing to send. 🎉")
        else:
            names = dict(zip(at_risk["student_id"], at_risk["name"] + "  ·  " + at_risk["status"]))
            c1, c2 = st.columns([3, 2], gap="large")
            with c1:
                pick = st.selectbox("Preview email for", list(names), format_func=lambda x: names[x],
                                    key="preview_student")
                preview(student_email(pick))
            with c2:
                st.markdown(f"**{len(at_risk)} at-risk students** (CRITICAL, WARNING or weak marks)")
                chosen = st.multiselect("Select students", list(names), format_func=lambda x: names[x],
                                        key="send_selected", placeholder="Pick one or more students")
                b1 = st.button(f"Send to all at-risk ({len(at_risk)})", type="primary", width="stretch",
                               disabled=bool(blocker), key="send_all")
                b2 = st.button(f"Send to selected ({len(chosen)})", width="stretch",
                               disabled=bool(blocker) or not chosen, key="send_sel")
                st.caption("Each email includes subject-wise attendance, classes needed, a weak-marks "
                           "note and how to book a meeting.")
                if b1 or b2:
                    ids = list(at_risk["student_id"]) if b1 else chosen
                    emails = []
                    for sid in ids:
                        try:
                            emails.append(student_email(sid))
                        except Exception as exc:
                            st.error(f"Couldn't compose the email for {sid}: {exc}")
                    run_batch(emails, "Student warnings")

        st.divider()
        st.markdown("#### 2 · Teacher & adviser alerts")
        if staff_df is None:
            st.info("Upload a **staff** file (or load the sample data) to alert subject teachers and "
                    "faculty advisers.", icon="👩‍🏫")
        else:
            staff_mail = staff_emails()
            if not staff_mail:
                st.success("No teacher or adviser has at-risk students right now.")
            else:
                n_t = sum(e.kind == "Teacher alert" for e in staff_mail)
                c1, c2 = st.columns([3, 2], gap="large")
                with c1:
                    i = st.selectbox("Preview alert for", range(len(staff_mail)),
                                     format_func=lambda k: email_label(staff_mail[k]), key="preview_staff")
                    preview(staff_mail[i])
                with c2:
                    st.markdown(f"**{n_t} teacher alerts** (at-risk students in their subjects) and "
                                f"**{len(staff_mail) - n_t} adviser alerts** (at-risk students in their department).")
                    if st.button(f"Send teacher & adviser alerts ({len(staff_mail)})", type="primary",
                                 width="stretch", disabled=bool(blocker), key="send_staff"):
                        run_batch(staff_mail, "Teacher & adviser alerts")

        st.divider()
        st.markdown("#### 3 · Weekly summary")
        if staff_df is None:
            st.info("Upload a **staff** file to send department-wise weekly summaries to advisers.", icon="🗓️")
        else:
            weekly = weekly_emails()
            if not weekly:
                st.info("No departments matched between the staff and attendance files.")
            else:
                c1, c2 = st.columns([3, 2], gap="large")
                with c1:
                    j = st.selectbox("Preview summary for", range(len(weekly)),
                                     format_func=lambda k: f"{weekly[k].subject.split(' - ')[-1]} → "
                                                           f"{weekly[k].recipient_name or weekly[k].to}",
                                     key="preview_weekly")
                    preview(weekly[j])
                with c2:
                    st.markdown(f"**{len(weekly)} department summaries**: headline numbers, subject "
                                f"breakdown and the five highest-risk students.")
                    if st.button(f"Send weekly summary ({len(weekly)})", type="primary", width="stretch",
                                 disabled=bool(blocker), key="send_weekly"):
                        run_batch(weekly, "Weekly summary")

        st.divider()
        st.markdown("#### Send results")
        show_results()
    except Exception as exc:
        st.error(f"Something went wrong in the alerts tab: {exc}")


# ---------------------------------------------------------------- appointments

with tab_appt:
    st.info("Appointments are coming next.")
