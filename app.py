"""AttendGuard - Student Attendance & Performance Early-Warning System."""

from __future__ import annotations

import uuid

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import caller as C
import data_loader as D
import emailer as E
import logic as L

st.set_page_config(page_title="AttendGuard", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

STATUS_COLORS = {L.CRITICAL: "#ef4444", L.WARNING: "#f59e0b", L.SAFE: "#10b981"}
STATUS_BG = {L.CRITICAL: "rgba(239,68,68,.14)", L.WARNING: "rgba(245,158,11,.16)", L.SAFE: "rgba(16,185,129,.14)"}
TREND_ICON = {L.FALLING: "↘ Falling", L.STABLE: "→ Stable", L.IMPROVING: "↗ Improving", L.NO_MARKS: "– No marks"}
PLOT_CFG = {"displayModeBar": False}
FILE_LABELS = {
    "attendance": ("Attendance", "student_id, name, email, department, subject, classes_held, classes_attended"),
    "marks": ("Marks", "student_id, subject, test_name, test_date, marks, max_marks"),
    "staff": ("Staff", "department, subject, teacher_name, teacher_email, adviser_name, adviser_email"),
    "timetable": ("Timetable (optional)", "teacher_name, day, time_slot, status (free/busy)"),
}

LOGO_SVG = """<svg width="{s}" height="{s}" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
<defs><linearGradient id="agg{k}" x1="6" y1="4" x2="42" y2="44" gradientUnits="userSpaceOnUse">
<stop stop-color="#c7d2fe"/><stop offset=".55" stop-color="#ffffff"/><stop offset="1" stop-color="#a5f3fc"/></linearGradient></defs>
<path d="M24 3.5 40.5 9.6v12.6c0 10.4-6.9 18.9-16.5 22.3C14.4 41.1 7.5 32.6 7.5 22.2V9.6L24 3.5Z" fill="url(#agg{k})"/>
<path d="m16.5 24 5.2 5.2 10.3-10.6" stroke="#4f46e5" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


def logo(size: int = 34, key: str = "a") -> str:
    return LOGO_SVG.format(s=size, k=key)


st.markdown("""
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 4rem; max-width: 1380px;}
[data-testid="stHeader"] {background: transparent;}

/* hero */
.ag-hero {position:relative; overflow:hidden; border-radius:22px; padding:26px 30px 22px; margin:0 0 22px;
  color:#fff; background: linear-gradient(118deg,#4338ca 0%,#6d28d9 48%,#0e7490 100%);
  box-shadow: 0 18px 40px -22px rgba(79,70,229,.75);}
.ag-hero::before {content:""; position:absolute; right:-80px; top:-90px; width:320px; height:320px; border-radius:50%;
  background: radial-gradient(circle, rgba(255,255,255,.25), rgba(255,255,255,0) 68%);}
.ag-hero::after {content:""; position:absolute; left:38%; bottom:-140px; width:300px; height:300px; border-radius:50%;
  background: radial-gradient(circle, rgba(103,232,249,.28), rgba(103,232,249,0) 70%);}
.ag-hero-row {position:relative; z-index:1; display:flex; align-items:center; gap:18px;}
.ag-logo {width:62px; height:62px; flex:0 0 62px; border-radius:18px; display:flex; align-items:center;
  justify-content:center; background: rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.3);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.25);}
.ag-title {font-size:2.05rem; font-weight:800; letter-spacing:-.025em; line-height:1.05; color:#fff;}
.ag-tag {margin-top:6px; font-size:1rem; color:rgba(255,255,255,.88);}
.ag-chips {position:relative; z-index:1; display:flex; flex-wrap:wrap; gap:8px; margin-top:18px;}
.ag-chip {font-size:.8rem; font-weight:600; padding:5px 12px; border-radius:999px; color:#fff;
  background: rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.26);}

/* KPI cards */
.ag-kpi {position:relative; height:100%; border-radius:18px; padding:16px 18px 14px; border:1px solid var(--bd);
  background: linear-gradient(150deg, var(--bg1), var(--bg2)); transition: transform .18s ease, box-shadow .18s ease;}
.ag-kpi:hover {transform: translateY(-3px); box-shadow: 0 14px 28px -18px var(--c);}
.ag-kpi .top {display:flex; align-items:center; justify-content:space-between; gap:8px;}
.ag-kpi .lbl {font-size:.74rem; font-weight:700; letter-spacing:.07em; text-transform:uppercase; opacity:.72;}
.ag-kpi .ico {width:34px; height:34px; border-radius:11px; display:flex; align-items:center; justify-content:center;
  background: var(--c); color:#fff; font-size:1rem; box-shadow: 0 6px 14px -6px var(--c);}
.ag-kpi .val {font-size:2.15rem; font-weight:800; letter-spacing:-.03em; line-height:1.1; margin-top:8px; color:var(--c);}
.ag-kpi .hint {font-size:.8rem; opacity:.66; margin-top:2px;}
.ag-kpi .bar {height:6px; border-radius:99px; margin-top:12px; background: rgba(127,127,127,.18); overflow:hidden;}
.ag-kpi .bar > span {display:block; height:100%; border-radius:99px; background: var(--c);}

/* recovery plan items */
.ag-plan {display:flex; gap:12px; align-items:flex-start; padding:12px 14px; border-radius:14px; margin-bottom:10px;
  border:1px solid var(--bd); border-left:4px solid var(--c); background: linear-gradient(120deg, var(--bg1), rgba(127,127,127,.02));}
.ag-plan .i {font-size:1.15rem; line-height:1.4;}
.ag-plan .sj {font-weight:700; display:flex; align-items:center; gap:8px; flex-wrap:wrap;}
.ag-plan .tg {font-size:.7rem; font-weight:800; letter-spacing:.04em; padding:2px 8px; border-radius:999px;
  color:var(--c); background: var(--bg1); border:1px solid var(--bd); text-transform:uppercase;}
.ag-plan .tx {font-size:.9rem; opacity:.8; margin-top:2px;}
.ag-kpi .val.sm {font-size:1.35rem; line-height:1.25;}

/* section titles */
.ag-sec {display:flex; align-items:baseline; gap:10px; margin: 4px 0 10px;}
.ag-sec .pip {width:6px; height:20px; border-radius:6px; align-self:center; background: linear-gradient(180deg,#6366f1,#06b6d4);}
.ag-sec .t {font-size:1.06rem; font-weight:700; letter-spacing:-.01em;}
.ag-sec .s {font-size:.84rem; opacity:.6;}

/* badges, banners */
.ag-badge {display:inline-block; padding:3px 11px; border-radius:999px; font-size:.74rem; font-weight:800;
  letter-spacing:.05em; vertical-align:middle;}
.ag-banner {display:flex; gap:12px; align-items:center; padding:12px 16px; border-radius:14px; margin-bottom:16px;
  font-size:.95rem; border:1px solid;}
.ag-banner .ic {font-size:1.25rem;}
.ag-banner.test {background: rgba(99,102,241,.10); border-color: rgba(99,102,241,.38);}
.ag-banner.live {background: rgba(239,68,68,.10); border-color: rgba(239,68,68,.40);}

/* profile header (student view) */
.ag-profile {display:flex; align-items:center; gap:16px; padding:16px 18px; border-radius:18px; margin:6px 0 16px;
  border:1px solid rgba(127,127,127,.2); background: linear-gradient(120deg, rgba(99,102,241,.12), rgba(6,182,212,.06));}
.ag-avatar {width:56px; height:56px; flex:0 0 56px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-weight:800; font-size:1.15rem; color:#fff;
  background: linear-gradient(135deg,#6366f1,#8b5cf6 55%,#06b6d4);}
.ag-profile .nm {font-size:1.35rem; font-weight:800; letter-spacing:-.02em;}
.ag-profile .meta {font-size:.88rem; opacity:.65; margin-top:2px;}

/* welcome / empty states */
.ag-welcome {text-align:center; padding: 6px 8px 0;}
.ag-welcome .h {font-size:1.6rem; font-weight:800; letter-spacing:-.02em;}
.ag-welcome .p {opacity:.7; margin: 6px auto 0; max-width: 660px;}
.ag-steps {display:grid; grid-template-columns: repeat(3, 1fr); gap:16px; margin: 24px 0 26px;}
.ag-step {text-align:left; padding:20px; border-radius:18px; border:1px solid var(--bd);
  background: linear-gradient(160deg, var(--bg1), rgba(127,127,127,.02));}
.ag-step .n {width:40px; height:40px; border-radius:12px; display:flex; align-items:center; justify-content:center;
  font-size:1.15rem; color:#fff; background: var(--c); margin-bottom:12px; box-shadow: 0 8px 18px -8px var(--c);}
.ag-step .t {font-weight:700; font-size:1.02rem;}
.ag-step .d {opacity:.68; font-size:.9rem; margin-top:4px;}
@media (max-width: 900px) {.ag-steps {grid-template-columns: 1fr;}}
.ag-empty {text-align:center; padding: 2.2rem 1rem; border:1.5px dashed rgba(127,127,127,.35); border-radius:18px;
  background: rgba(127,127,127,.04);}
.ag-empty .h {font-size:1.15rem; font-weight:700; margin-bottom:.35rem;}
.ag-empty .b {opacity:.72;}

/* sidebar */
.ag-brand {display:flex; align-items:center; gap:12px; padding: 0 2px 6px;}
.ag-brand .mk {width:44px; height:44px; flex:0 0 44px; border-radius:13px; display:flex; align-items:center;
  justify-content:center; background: linear-gradient(135deg,#4f46e5,#7c3aed 60%,#0891b2);
  box-shadow: 0 8px 18px -8px rgba(79,70,229,.8);}
.ag-brand .nm {font-weight:800; font-size:1.2rem; letter-spacing:-.02em; line-height:1.1;}
.ag-brand .sb {font-size:.78rem; opacity:.6;}
.ag-side-h {font-size:.72rem; font-weight:800; letter-spacing:.09em; text-transform:uppercase; opacity:.55;
  margin: 14px 0 4px;}
.ag-file-ok {font-size:.8rem; padding:6px 10px; border-radius:10px; margin:-4px 0 12px;
  background: rgba(16,185,129,.12); border:1px solid rgba(16,185,129,.3);}
.ag-file-ok .note {display:block; opacity:.72; margin-top:2px;}

/* tabs as a pill bar */
div[data-testid="stTabs"] [role="tablist"] {gap:6px; padding:6px; border-radius:16px; border-bottom:0;
  background: rgba(127,127,127,.08); border:1px solid rgba(127,127,127,.16); width:fit-content; max-width:100%;}
div[data-testid="stTabs"] [data-testid="stTab"] {height:44px; padding:0 20px; border-radius:11px; display:flex;
  align-items:center; background:transparent; transition: background .15s ease;}
div[data-testid="stTabs"] [data-testid="stTab"]:hover {background: rgba(127,127,127,.12);}
div[data-testid="stTabs"] [data-testid="stTab"] p {font-size:.98rem; font-weight:700; margin:0;}
div[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] {
  background: linear-gradient(118deg,#4f46e5,#7c3aed); box-shadow: 0 8px 18px -10px rgba(79,70,229,.9);}
div[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] p {color:#fff !important;}
div[data-testid="stTabs"] .react-aria-SelectionIndicator {display:none;}
div[data-testid="stTabs"] [role="tabpanel"] {padding-top: 18px;}

/* buttons */
button[data-testid="stBaseButton-primary"] {background: linear-gradient(118deg,#4f46e5,#7c3aed) !important;
  border:0 !important; color:#fff !important; font-weight:700; box-shadow: 0 8px 18px -10px rgba(79,70,229,.95);
  transition: transform .15s ease, filter .15s ease;}
button[data-testid="stBaseButton-primary"]:hover {filter: brightness(1.1); transform: translateY(-1px);}
button[data-testid="stBaseButton-primary"]:disabled {filter: grayscale(.6) opacity(.55); transform:none;}
button[data-testid="stBaseButton-secondary"] {font-weight:600;}
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


INDIGO, VIOLET, CYAN = "#6366f1", "#8b5cf6", "#06b6d4"


def tint(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[k:k + 2], 16) for k in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def kpi_card(label: str, value, hint: str, icon: str, color: str, pct: float | None = None) -> str:
    bar = (f'<div class="bar"><span style="width:{max(0.0, min(100.0, float(pct))):.0f}%"></span></div>'
           if pct is not None else "")
    return (f'<div class="ag-kpi" style="--c:{color};--bg1:{tint(color, .16)};--bg2:{tint(color, .03)};'
            f'--bd:{tint(color, .30)}"><div class="top"><div class="lbl">{label}</div>'
            f'<div class="ico">{icon}</div></div><div class="val{" sm" if len(str(value)) > 10 else ""}">{value}</div>'
            f'<div class="hint">{hint}</div>{bar}</div>')


def card(label: str, value, hint: str = "", kind: str = "neutral") -> str:
    color = {"critical": STATUS_COLORS[L.CRITICAL], "warning": STATUS_COLORS[L.WARNING],
             "safe": STATUS_COLORS[L.SAFE]}.get(kind, INDIGO)
    return kpi_card(label, value, hint, "", color).replace('<div class="ico"></div>', "")


def chart_layout(height: int, ytitle, legend: bool = True) -> dict:
    """Shared Plotly look: transparent, rounded bars, soft grid - follows the light/dark theme."""
    return dict(
        height=height, margin=dict(l=8, r=16, t=8 if not legend else 34, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Plus Jakarta Sans, sans-serif", size=13),
        barcornerradius=7, bargap=0.38, xaxis_title=None, yaxis_title=ytitle,
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="rgba(127,127,127,.18)", zeroline=False),
        showlegend=legend, legend_title_text="",
        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, xanchor="left"),
        hoverlabel=dict(font_family="Plus Jakarta Sans, sans-serif"),
    )


def section(title: str, sub: str = ""):
    st.markdown(f'<div class="ag-sec"><span class="pip"></span><span class="t">{title}</span>'
                f'<span class="s">{sub}</span></div>', unsafe_allow_html=True)


def style_status(df: pd.DataFrame, col: str = "Status"):
    def f(v):
        c = STATUS_COLORS.get(v)
        return f"background-color:{STATUS_BG[v]};color:{c};font-weight:800" if c else ""
    return df.style.map(f, subset=[col])


def student_needed(n) -> str:
    """Per-student total (sum over subjects) - no per-subject cap."""
    return L.format_needed(n, limit=None)


def empty_state(title: str, body: str):
    st.markdown(f'<div class="ag-empty"><div class="h">{title}</div>'
                f'<div class="b">{body}</div></div>', unsafe_allow_html=True)


def init_state():
    ss = st.session_state
    ss.setdefault("data", {})        # kind -> DataFrame
    ss.setdefault("notes", {})       # kind -> list[str]
    ss.setdefault("source", {})      # kind -> "sample" | filename
    ss.setdefault("upload_sig", {})  # kind -> signature of the last processed upload
    ss.setdefault("bookings", [])
    ss.setdefault("send_results", None)
    ss.setdefault("uploader_nonce", 0)  # bumped to reset the file uploaders


def load_sample_into_state():
    try:
        with st.spinner("Loading sample data..."):
            sample = D.load_sample()
    except Exception as exc:
        st.error(f"Couldn't load sample data: {exc}")
        return
    for kind, (df, notes) in sample.items():
        st.session_state.data[kind] = df
        st.session_state.notes[kind] = notes
        st.session_state.source[kind] = "sample data"
    st.session_state.upload_sig = {}
    st.session_state.uploader_nonce += 1   # clear any previously uploaded files
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
    # Don't mix the judge's own files with leftover sample tables.
    leftovers = [k for k, src in st.session_state.source.items() if src == "sample data" and k != kind]
    for k in leftovers:
        for store in ("data", "notes", "source"):
            st.session_state[store].pop(k, None)
    if leftovers:
        st.session_state.bookings = []
        st.toast("Sample data cleared - now using your uploaded files.", icon="📁")
    st.session_state.data[kind] = df
    st.session_state.notes[kind] = notes
    st.session_state.source[kind] = file.name
    st.session_state.send_results = None


REPORT_VERSION = 2  # bump when build_report's output changes, so stale cached reports are never reused


@st.cache_data(show_spinner=False)
def compute_report(att: pd.DataFrame, marks: pd.DataFrame | None, target: float, version: int = REPORT_VERSION):
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


# ---------------------------------------------------------------- theme switch

@st.cache_resource
def _theme_stash() -> dict:
    """Server-side hand-off so loaded data survives the page reload a theme switch needs."""
    return {}


STASH_KEYS = ("data", "notes", "source", "bookings", "send_results", "test_address", "test_phone")


def restore_after_theme_switch():
    tok = st.query_params.get("restore")
    if not tok or st.session_state.get("_restored") == tok:
        return
    saved = _theme_stash().pop(tok, None)
    if saved:
        for k, v in saved.items():
            st.session_state[k] = v
    st.session_state._restored = tok
    try:
        del st.query_params["restore"]
    except Exception:
        pass


def theme_is_dark() -> bool:
    q = st.query_params.get("theme")
    if q in ("dark", "light"):
        return q == "dark"
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def _on_theme_toggle():
    st.session_state._theme_request = "Dark" if st.session_state.dark_mode else "Light"


def apply_theme_request():
    """Persist the choice where Streamlit's frontend reads it, then reload with data handed over."""
    mode = st.session_state.pop("_theme_request", None)
    if not mode:
        return
    tok = uuid.uuid4().hex
    _theme_stash()[tok] = {k: st.session_state[k] for k in STASH_KEYS if k in st.session_state}
    components.html(f"""<script>
      const p = window.parent;
      try {{ p.localStorage.setItem("stActiveTheme-" + p.location.pathname + "-v2", JSON.stringify("{mode}")); }} catch (e) {{}}
      const u = new URL(p.location.href);
      u.searchParams.set("theme", "{mode.lower()}");
      u.searchParams.set("restore", "{tok}");
      // Run the navigation in the parent's own JS realm - the sandboxed iframe itself may not navigate the page.
      p.setTimeout(new p.Function("url", "window.location.replace(url)"), 50, u.toString());
    </script>""", height=0)


# ---------------------------------------------------------------- sidebar

init_state()
ss = st.session_state
restore_after_theme_switch()

with st.sidebar:
    st.markdown(f'<div class="ag-brand"><div class="mk">{logo(28, "s")}</div><div>'
                f'<div class="nm">AttendGuard</div><div class="sb">Early-warning for student success</div>'
                f'</div></div>', unsafe_allow_html=True)
    st.toggle("🌙 Dark mode", value=theme_is_dark(), key="dark_mode", on_change=_on_theme_toggle,
              help="Switch between light and dark themes. Your loaded data is kept.")
    apply_theme_request()

    st.markdown('<div class="ag-side-h">Data</div>', unsafe_allow_html=True)
    if st.button("📂 Load sample data", width="stretch", type="primary",
                 help="Loads 40 realistic students across 3 departments and 5 subjects."):
        load_sample_into_state()

    for kind, (label, cols) in FILE_LABELS.items():
        f = st.file_uploader(label, type=["csv", "xlsx", "xls"], key=f"up_{kind}_{ss.uploader_nonce}",
                             help=f"Columns: {cols}. Headers are case-insensitive; common aliases like 'Roll No' work.")
        handle_upload(kind, f)
        notes = ss.notes.get(kind, [])
        errors = [n for n in notes if n.startswith("ERROR:")]
        if errors:
            st.error(errors[0][7:])
        elif kind in ss.data:
            extra = "".join(f'<span class="note">ℹ️ {n}</span>' for n in notes)
            st.markdown(f'<div class="ag-file-ok">✅ <b>{len(ss.data[kind])}</b> rows · '
                        f'{ss.source.get(kind, "")}{extra}</div>', unsafe_allow_html=True)

    if ss.data and st.button("Clear all data", width="stretch",
                             help="Forget all loaded files, bookings and send results."):
        for k in ("data", "notes", "source", "upload_sig", "bookings"):
            ss[k] = {} if k != "bookings" else []
        ss.send_results = None
        ss.uploader_nonce += 1
        st.rerun()

    st.markdown('<div class="ag-side-h">Rules</div>', unsafe_allow_html=True)
    target = st.slider("Attendance target (%)", 50, 100, 85, 1,
                       help="SAFE ≥ target + 5 · WARNING within 5 points above target · CRITICAL below target.")

    st.markdown('<div class="ag-side-h">Email</div>', unsafe_allow_html=True)
    test_mode = st.toggle("🧪 Test mode", value=True, key="test_mode",
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

    st.markdown('<div class="ag-side-h">Voice calls</div>', unsafe_allow_html=True)
    test_phone_raw = st.text_input("Test phone", value=ss.get("test_phone", get_secret("TEST_PHONE")),
                                   placeholder="+91 98765 43210", key="test_phone_input",
                                   help="While test mode is on, every call rings this number instead. "
                                        "On a Twilio trial it must be a verified number.")
    ss.test_phone = test_phone_raw
    test_phone = C.normalize_phone(test_phone_raw)
    tw_sid, tw_token, tw_from = (get_secret("TWILIO_ACCOUNT_SID"), get_secret("TWILIO_AUTH_TOKEN"),
                                 C.normalize_phone(get_secret("TWILIO_FROM_NUMBER")))
    if tw_sid and tw_token and tw_from:
        st.caption(f"📞 Calling from {tw_from}")
    else:
        st.caption("⚠️ Calls not configured - add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and "
                   "TWILIO_FROM_NUMBER to secrets. Script previews still work.")


# ---------------------------------------------------------------- header

st.markdown(
    f'<div class="ag-hero"><div class="ag-hero-row"><div class="ag-logo">{logo(38, "h")}</div><div>'
    f'<div class="ag-title">AttendGuard</div>'
    f'<div class="ag-tag">Spot at-risk students early, show them exactly how to recover, '
    f'and alert the right staff - in minutes.</div></div></div>'
    f'<div class="ag-chips"><span class="ag-chip">📊 Attendance analytics</span>'
    f'<span class="ag-chip">📈 Marks trends</span><span class="ag-chip">🎯 Recovery plans</span>'
    f'<span class="ag-chip">✉️ Smart alerts</span><span class="ag-chip">📅 Appointments</span></div></div>',
    unsafe_allow_html=True)

if "attendance" not in ss.data:
    steps = [("📁", "Upload your files", "Attendance, marks, staff and an optional timetable - CSV or Excel, "
              "messy headers welcome.", INDIGO),
             ("🔍", "Spot risk instantly", "Status, classes needed to recover, marks trends and a 0-100 "
              "risk score for every student.", CYAN),
             ("🚀", "Act in one click", "Personalised emails to students, alerts to teachers and advisers, "
              "and meeting bookings.", VIOLET)]
    cards_html = "".join(
        f'<div class="ag-step" style="--c:{c};--bg1:{tint(c, .10)};--bd:{tint(c, .28)}">'
        f'<div class="n">{i}</div><div class="t">{t}</div><div class="d">{d}</div></div>'
        for i, t, d, c in steps)
    st.markdown('<div class="ag-welcome"><div class="h">Welcome! Let\'s find who needs help.</div>'
                '<div class="p">Upload an <b>attendance</b> file in the sidebar, or load the sample data to '
                'explore AttendGuard with 40 realistic students.</div></div>'
                f'<div class="ag-steps">{cards_html}</div>', unsafe_allow_html=True)
    c = st.columns([1.3, 1, 1.3])[1]
    if c.button("📂 Load sample data", width="stretch", type="primary", key="load_main"):
        load_sample_into_state()
        st.rerun()
    st.write("")
    with st.expander("📋 Expected file formats"):
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
n_students = max(len(students), 1)
avg_att = students["attendance_pct"].mean() if len(students) else 0
n_risk = int(students["at_risk"].sum())
kpis = [
    ("Total students", len(students), f"{students['department'].nunique()} departments · "
     f"{subjects['subject'].nunique()} subjects", "👥", INDIGO, 100),
    ("Critical", int(counts.get(L.CRITICAL, 0)), f"below {target}%", "🚨", STATUS_COLORS[L.CRITICAL],
     counts.get(L.CRITICAL, 0) / n_students * 100),
    ("Warning", int(counts.get(L.WARNING, 0)), f"{target}–{target + 5}%", "⚠️", STATUS_COLORS[L.WARNING],
     counts.get(L.WARNING, 0) / n_students * 100),
    ("Safe", int(counts.get(L.SAFE, 0)), f"≥ {target + 5}%", "✅", STATUS_COLORS[L.SAFE],
     counts.get(L.SAFE, 0) / n_students * 100),
    ("Avg attendance", f"{avg_att:.1f}%", f"{n_risk} students need attention", "📈", CYAN, avg_att),
]
for col, (lbl, val, hint, icon, color, pct) in zip(st.columns(5), kpis):
    col.markdown(kpi_card(lbl, val, hint, icon, color, pct), unsafe_allow_html=True)
st.write("")

tab_dash, tab_student, tab_alerts, tab_appt = st.tabs(
    ["📊  Dashboard", "🎓  Student view", "✉️  Alerts", "📅  Appointments"])


# ---------------------------------------------------------------- dashboard

with tab_dash:
    try:
        f1, f2, f3 = st.columns([2, 2, 1], vertical_alignment="bottom")
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
            c1, c2 = st.columns(2, gap="medium")
            with c1.container(border=True):
                section("Risk by department", "students by status")
                dd = (vs.groupby(["department", "status"]).size().reset_index(name="students"))
                fig = px.bar(dd, x="department", y="students", color="status",
                             color_discrete_map=STATUS_COLORS,
                             category_orders={"status": L.STATUS_ORDER})
                fig.update_layout(**chart_layout(330, "Students"))
                st.plotly_chart(fig, width="stretch", config=PLOT_CFG)
            with c2.container(border=True):
                section("Risk by subject", "student-subject pairs by status")
                sd = (vsub.groupby(["subject", "status"]).size().reset_index(name="students"))
                sd["subject"] = sd["subject"].astype(str).str.replace(" ", "<br>", n=1, regex=False)
                fig = px.bar(sd, x="subject", y="students", color="status",
                             color_discrete_map=STATUS_COLORS,
                             category_orders={"status": L.STATUS_ORDER})
                fig.update_layout(**chart_layout(330, "Students"))
                st.plotly_chart(fig, width="stretch", config=PLOT_CFG)

            st.write("")
            section("Ranked at-risk students", "most at-risk first")
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

        initials = "".join(w[0] for w in str(srow["name"]).split()[:2]).upper() or "?"
        st.markdown(f'<div class="ag-profile"><div class="ag-avatar">{initials}</div><div>'
                    f'<div class="nm">{srow["name"]} &nbsp;{badge(srow["status"])}</div>'
                    f'<div class="meta">🆔 {srow["student_id"]} &nbsp;·&nbsp; 🏛️ {srow["department"]} &nbsp;·&nbsp; '
                    f'✉️ {srow["email"] or "no email on file"}</div></div></div>', unsafe_allow_html=True)
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

        c1, c2 = st.columns([3, 2], gap="medium")
        with c1.container(border=True):
            section("Attendance by subject", f"dashed line = {target}% target")
            fig = go.Figure(go.Bar(
                x=ssub["attendance_pct"], y=ssub["subject"], orientation="h", width=0.62,
                marker_color=[STATUS_COLORS[s] for s in ssub["status"]],
                text=[f"{p:.1f}%" for p in ssub["attendance_pct"]], textposition="outside",
                hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
            fig.add_vline(x=target, line_dash="dash", line_color="rgba(127,127,127,.85)", line_width=2)
            fig.update_layout(**chart_layout(80 + 52 * len(ssub), None, legend=False))
            fig.update_layout(xaxis=dict(range=[0, 112], title=None, ticksuffix="%"))
            st.plotly_chart(fig, width="stretch", config=PLOT_CFG)
        with c2.container(border=True):
            section("Recovery plan", "what to do next")
            items = ""
            for _, r in ssub.iterrows():
                msg = L.recovery_message(r["subject"], r["classes_needed"], target)
                if r["classes_needed"] == 0:
                    color, icon, tag = STATUS_COLORS[L.SAFE], "✅", "On track"
                elif L.is_recoverable(r["classes_needed"]):
                    color, icon, tag = STATUS_COLORS[L.WARNING], "🎯", f"{int(r['classes_needed'])} classes"
                else:
                    color, icon, tag = STATUS_COLORS[L.CRITICAL], "⛔", "Can't recover"
                items += (f'<div class="ag-plan" style="--c:{color};--bg1:{tint(color, .13)};--bd:{tint(color, .35)}">'
                          f'<div class="i">{icon}</div><div class="m"><div class="sj">{r["subject"]}'
                          f'<span class="tg">{tag}</span></div><div class="tx">{msg}</div></div></div>')
            st.markdown(items, unsafe_allow_html=True)

        st.write("")
        section("Subject details")
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

        st.write("")
        section("Marks trend", "score % per test · dotted line = 40% weak mark")
        sm = marks_pct[marks_pct["student_id"] == sid]
        if sm.empty:
            st.info("No marks on record for this student.")
        else:
            sm = sm.assign(label=sm["test_name"].astype(str))
            fig = px.line(sm, x="label", y="pct", color="subject", markers=True,
                          hover_data={"test_date": True, "label": False})
            fig.add_hline(y=L.WEAK_MARK_PCT, line_dash="dot", line_color=STATUS_COLORS[L.CRITICAL], line_width=2)
            fig.update_traces(line=dict(width=3), marker=dict(size=9))
            fig.update_layout(**chart_layout(340, "Score %"))
            fig.update_layout(yaxis=dict(range=[0, 105], ticksuffix="%"))
            with st.container(border=True):
                st.plotly_chart(fig, width="stretch", config=PLOT_CFG)
    except Exception as exc:
        st.error(f"Couldn't show this student: {exc}")


# ---------------------------------------------------------------- email helpers

def mode_banner():
    if test_mode:
        addr = test_address.strip() or "(no test address set - add one in the sidebar)"
        st.markdown(f'<div class="ag-banner test"><span class="ic">🧪</span><div><b>Test mode is ON</b> - every '
                    f'email is redirected to <b>{addr}</b>. The real recipient is noted in the subject line.</div></div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="ag-banner live"><span class="ic">📨</span><div><b>Live mode</b> - emails go to '
                    'the real students and staff addresses in your files.</div></div>', unsafe_allow_html=True)


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
        return []
    emails = E.apply_test_mode(emails, test_mode, test_address)
    bar = st.progress(0.0, text=f"Sending {label}...")

    def prog(i, total, _e):
        bar.progress(i / total, text=f"Sending {label}: {i} of {total}")

    try:
        results = E.send_batch(emails, smtp_user, smtp_pass, progress=prog)
    except Exception as exc:  # send_batch is already per-message safe; this is a last resort
        st.error(f"Sending stopped unexpectedly: {exc}")
        return []
    finally:
        bar.empty()
    ss.send_results = {"label": label, "rows": results, "test_mode": test_mode}
    sent = sum(r["status"] == "sent" for r in results)
    st.toast(f"{label}: {sent} sent, {len(results) - sent} failed", icon="✉️")
    return results


def call_blocker() -> str | None:
    if not (tw_sid and tw_token and tw_from):
        return "Voice calls aren't configured yet - add the TWILIO_* secrets (see README)."
    if test_mode and not C.valid_phone(test_phone):
        return "Test mode is on - enter a valid test phone in the sidebar first (e.g. +91 98765 43210)."
    return None


def call_for(sid) -> C.Call:
    srow = students[students["student_id"] == sid].iloc[0].to_dict()
    rows = subjects[subjects["student_id"] == sid].sort_values("attendance_pct").to_dict("records")
    return C.Call(to=C.normalize_phone(srow.get("phone", "")),
                  script=C.call_script(srow, rows, target), recipient_name=str(srow["name"]))


def run_calls(calls, label: str):
    """Place calls with a progress bar; results go to the shared results table."""
    if not calls:
        st.info("Nothing to call.")
        return []
    calls = C.apply_test_mode(calls, test_mode, test_phone)
    bar = st.progress(0.0, text=f"Placing {label}...")

    def prog(i, total, _c):
        bar.progress(i / total, text=f"Placing {label}: {i} of {total}")

    try:
        results = C.place_calls(calls, tw_sid, tw_token, tw_from, progress=prog)
    except Exception as exc:  # place_calls is already per-call safe; this is a last resort
        st.error(f"Calling stopped unexpectedly: {exc}")
        return []
    finally:
        bar.empty()
    ss.send_results = {"label": label, "rows": results, "test_mode": test_mode}
    ok = sum(r["status"] == "sent" for r in results)
    st.toast(f"{label}: {ok} placed, {len(results) - ok} failed", icon="📞")
    return results


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
                        "Result": df["status"].str.upper(), "Details": df["reason"]})

    def color(v):
        return "color:#15803d;font-weight:700" if v == "SENT" else "color:#b91c1c;font-weight:700"
    st.dataframe(out.style.map(color, subset=["Result"]), hide_index=True, width="stretch")


def preview(email: E.Email):
    shown = E.apply_test_mode([email], test_mode, test_address)[0]
    with st.container(border=True):
        st.markdown(f"**To:** {shown.to or '_(set a test address in the sidebar)_'}"
                    + (f" &nbsp;·&nbsp; _originally {shown.original_to}_" if test_mode else ""))
        st.markdown(f"**Subject:** {shown.subject}")
        st.html('<div style="background:#ffffff;color:#0f172a;border-radius:12px;padding:18px 22px;'
                'border:1px solid #e2e8f0;box-shadow:0 10px 30px -18px rgba(15,23,42,.45)">' + email.html + '</div>')
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


def voice_section():
    """Alerts section 4: preview and place Twilio calls to CRITICAL students."""
    crit = students[students["status"] == L.CRITICAL]
    if crit.empty:
        st.success("No CRITICAL students - no calls needed. 🎉")
    else:
        cblock = call_blocker()
        if cblock:
            st.warning(cblock, icon="📞")
        phones = crit["phone"] if "phone" in crit.columns else pd.Series("", index=crit.index)
        has_phone = phones.map(lambda v: bool(C.normalize_phone(v)))
        cnames = dict(zip(crit["student_id"], crit["name"] + "  ·  " + crit["attendance_pct"].map(lambda v: f"{v:.1f}%")))
        c1, c2 = st.columns([3, 2], gap="large")
        with c1:
            cpick = st.selectbox("Preview call for", list(cnames), format_func=lambda x: cnames[x],
                                 key="preview_call")
            pc = C.apply_test_mode([call_for(cpick)], test_mode, test_phone)[0]
            with st.container(border=True):
                st.markdown(f"**Calls:** {pc.to or '_(no valid number)_'}"
                            + (f" &nbsp;·&nbsp; _student's number: {pc.original_to}_" if test_mode else ""))
                st.markdown(f"🗣️ _“{pc.script}”_")
        with c2:
            st.markdown(f"**{len(crit)} CRITICAL students** · {int(has_phone.sum())} with a phone number")
            cchosen = st.multiselect("Select students to call", list(cnames), format_func=lambda x: cnames[x],
                                     key="call_selected", placeholder="Pick one or more students")
            cb1 = st.button(f"📞 Call all CRITICAL ({len(crit)})", type="primary", width="stretch",
                            disabled=bool(cblock), key="call_all")
            cb2 = st.button(f"📞 Call selected ({len(cchosen)})", width="stretch",
                            disabled=bool(cblock) or not cchosen, key="call_sel")
            st.caption("A short spoken message: attendance, the next step to recover, weak marks, "
                       "and a pointer to the emailed plan. In test mode every call rings your test phone.")
            if cb1 or cb2:
                ids = list(crit["student_id"]) if cb1 else cchosen
                calls = []
                for sid_ in ids:
                    try:
                        calls.append(call_for(sid_))
                    except Exception as exc:
                        st.error(f"Couldn't prepare the call for {sid_}: {exc}")
                run_calls(calls, "Voice calls")


# ---------------------------------------------------------------- alerts

with tab_alerts:
    try:
        mode_banner()
        blocker = send_blocker()
        if blocker:
            st.warning(blocker, icon="⚙️")

        section("1 · Student warnings", "personalised recovery plan for each at-risk student")
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
        section("2 · Teacher & adviser alerts", "summary tables for the right staff")
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
        section("3 · Weekly summary", "department-wise digest for advisers")
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
        section("4 · Voice calls", "automated phone call for CRITICAL students (via Twilio)")
        try:
            voice_section()
        except Exception as exc:
            st.error(f"Voice calls are unavailable right now: {exc}")

        st.divider()
        section("Send results", "sent / failed per message")
        show_results()
    except Exception as exc:
        st.error(f"Something went wrong in the alerts tab: {exc}")




# ---------------------------------------------------------------- appointments

DAY_ORDER = {d: i for i, d in enumerate(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
     "mon", "tue", "wed", "thu", "fri", "sat", "sun"])}
FREE_WORDS = {"free", "available", "open", "yes", "f"}


def find_teacher(dept, subject):
    if staff_df is None:
        return None
    s = staff_df[staff_df["subject"].map(_key) == _key(subject)]
    exact = s[s["department"].map(_key) == _key(dept)]
    s = exact if not exact.empty else s
    s = s[s["teacher_name"].astype(str).str.strip() != ""]
    return None if s.empty else s.iloc[0].to_dict()


with tab_appt:
    try:
        mode_banner()
        if tt_df is None:
            empty_state("No timetable uploaded",
                        "Upload a <b>timetable</b> file (teacher_name, day, time_slot, status) in the sidebar "
                        "to let at-risk students book a support meeting with their teacher. "
                        "Everything else in AttendGuard works without it.")
        elif students["at_risk"].sum() == 0:
            st.success("No at-risk students right now - no appointments needed. 🎉")
        else:
            risky = students[students["at_risk"]]
            names = dict(zip(risky["student_id"], risky["name"] + "  ·  " + risky["status"]))
            c1, c2 = st.columns([2, 3], gap="large")
            with c1.container(border=True):
                section("Book a support meeting")
                sid = st.selectbox("At-risk student", list(names), format_func=lambda x: names[x],
                                   key="appt_student")
                srow = students[students["student_id"] == sid].iloc[0]
                ssub = subjects[subjects["student_id"] == sid].copy()
                ssub["_rank"] = ssub["status"].map({L.CRITICAL: 0, L.WARNING: 1, L.SAFE: 2}) - ssub["weak"].astype(int) * 0.5
                ssub = ssub.sort_values(["_rank", "attendance_pct"])
                sub_lbl = {r["subject"]: f"{r['subject']}  ·  {r['attendance_pct']:.1f}%  ·  {r['status']}"
                           + ("  ·  weak marks" if r["weak"] else "") for _, r in ssub.iterrows()}
                subject = st.selectbox("Subject", list(sub_lbl), format_func=lambda x: sub_lbl[x],
                                       key="appt_subject", help="Subjects needing the most help are listed first.")
                teacher = find_teacher(srow["department"], subject)
                if teacher is None:
                    st.info("No teacher found for this subject - upload a **staff** file that lists it.")
                else:
                    st.markdown(f"**Teacher:** {teacher['teacher_name']}  \n"
                                f"<span style='color:#64748b'>{teacher['teacher_email'] or 'no email on file'}</span>",
                                unsafe_allow_html=True)
            with c2:
                if teacher is not None:
                    tname = str(teacher["teacher_name"])
                    tt = tt_df[(tt_df["teacher_name"].map(_key) == _key(tname))
                               & (tt_df["status"].map(_key).isin(FREE_WORDS))].copy()
                    taken = {(_key(b["Teacher"]), _key(b["Day"]), _key(b["Slot"])) for b in ss.bookings}
                    tt = tt[[(_key(tname), _key(d), _key(t)) not in taken
                             for d, t in zip(tt["day"], tt["time_slot"])]]
                    tt["_d"] = tt["day"].map(lambda d: DAY_ORDER.get(_key(d), 99))
                    tt = tt.sort_values(["_d", "time_slot"])
                    section(f"Free slots with {tname}", "✅ = free")
                    if tt.empty:
                        st.info(f"{tname} has no free slots left in the timetable. Try another subject, "
                                "or contact the teacher directly.")
                    else:
                        grid = (tt.assign(v="✅").pivot_table(index="time_slot", columns="day", values="v",
                                                             aggfunc="first", fill_value=""))
                        grid = grid[sorted(grid.columns, key=lambda d: DAY_ORDER.get(_key(d), 99))]
                        st.dataframe(grid, width="stretch")
                        slots = [(d, t) for d, t in zip(tt["day"], tt["time_slot"])]
                        slot = st.selectbox("Choose a slot", range(len(slots)),
                                            format_func=lambda k: f"{slots[k][0]} · {slots[k][1]}", key="appt_slot")
                        if st.button("📅 Book this slot", type="primary", key="book_slot"):
                            day, tslot = slots[slot]
                            booking = {"Student": srow["name"], "Student ID": sid, "Department": srow["department"],
                                       "Subject": subject, "Teacher": tname, "Day": day, "Slot": tslot,
                                       "Confirmation": "not sent"}
                            ss.bookings.append(booking)
                            mails = [
                                E.booking_confirmation(srow["name"], srow["email"], srow["name"], tname,
                                                       subject, day, tslot, for_teacher=False),
                                E.booking_confirmation(tname, teacher["teacher_email"], srow["name"], tname,
                                                       subject, day, tslot, for_teacher=True),
                            ]
                            msgs = []
                            blocker = send_blocker()
                            if blocker:
                                msgs.append(("success", f"Booked {srow['name']} with {tname} on {day}, {tslot}."))
                                msgs.append(("info", f"Confirmation emails not sent: {blocker}"))
                            else:
                                res = run_batch(mails, "Booking confirmation")
                                ok_n = sum(r["status"] == "sent" for r in res)
                                booking["Confirmation"] = f"{ok_n}/2 emails sent"
                                msgs.append(("success", f"Booked {srow['name']} with {tname} on {day}, {tslot}. "
                                                        f"Confirmation emails: {ok_n} of 2 sent."))
                                msgs += [("warning", f"Email to {r['recipient']} failed: {r['reason']}")
                                         for r in res if r["status"] != "sent"]
                            ss.appt_msgs = msgs
                            st.rerun()

            for kind, msg in ss.pop("appt_msgs", []):
                getattr(st, kind)(msg)
            st.divider()
            section("Bookings", "this session")
            if not ss.bookings:
                st.caption("No bookings yet. Booked meetings will appear here for this session.")
            else:
                st.dataframe(pd.DataFrame(ss.bookings), hide_index=True, width="stretch")
    except Exception as exc:
        st.error(f"Something went wrong in appointments: {exc}")
