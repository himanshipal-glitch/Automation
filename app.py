"""
Zoho Data Pipeline Dashboard
"""

import io
import pandas as pd
import streamlit as st

import database as db
import cleaning
import compute
import reports

st.set_page_config(
    page_title="Zoho Data Pipeline",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Visual theme (Recykal — recykal.market design language) — presentation only ─
# Bricolage Grotesque display headings · Geist UI text · Kode Mono meta labels ·
# warm blacks (#16160F) on warm paper (#FAFAFA/#F2F2EE) · black pill CTAs ·
# one green whisper (#1B8B3A). No content or logic in here.
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700&family=Geist:wght@400;500;600;700&family=Kode+Mono:wght@400;500;600&display=swap');

:root{
  --ink:#16160F;            /* warm black — text, fills            */
  --ink-soft:#3D3D36;
  --grey:#6F6F66;           /* warm secondary text                 */
  --paper:#FAFAFA;          /* page                                */
  --paper-2:#F2F2EE;        /* warm surfaces                       */
  --paper-3:#ECEBE8;        /* capsule / deep surfaces             */
  --hair:rgba(22,22,15,.12);
  --hair-soft:rgba(22,22,15,.07);
  --green:#1B8B3A;          /* the one accent — meta labels, live dots */
  --shadow-s:0 1px 2px rgba(22,22,15,.05), 0 3px 6px -2px rgba(22,22,15,.05);
  --shadow-m:0 2px 4px rgba(22,22,15,.04), 0 12px 24px -8px rgba(22,22,15,.10);
  --shadow-l:0 4px 8px rgba(22,22,15,.05), 0 25px 42px -12px rgba(22,22,15,.16);
  --ease:cubic-bezier(.22,.9,.28,1);
}

html, body, [class*="css"], .stApp{
  font-family:'Geist', -apple-system, system-ui, sans-serif;
  -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
  color:var(--ink);
}
.stApp{
  background-color:var(--paper);
  background-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D'http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg'%20width%3D'560'%20height%3D'560'%20viewBox%3D'0%200%20560%20560'%3E%3Cg%20fill%3D'none'%20stroke%3D'%2316160F'%20stroke-opacity%3D'.055'%20stroke-width%3D'2'%20stroke-linecap%3D'round'%20stroke-linejoin%3D'round'%3E%3C!--%20PET%20bottle%20--%3E%3Cg%20transform%3D'translate(60%2052)%20rotate(-14)'%3E%3Crect%20x%3D'7'%20y%3D'0'%20width%3D'12'%20height%3D'6'%20rx%3D'2'%2F%3E%3Cpath%20d%3D'M9%206%20v5%20c0%205%20-7%207%20-7%2014%20v32%20a6%206%200%200%200%206%206%20h10%20a6%206%200%200%200%206%20-6%20V25%20c0%20-7%20-7%20-9%20-7%20-14%20V6'%2F%3E%3Cpath%20d%3D'M4%2034%20h18%20M4%2048%20h18'%2F%3E%3C%2Fg%3E%3C!--%20recycle%20arrows%20triangle%20--%3E%3Cg%20transform%3D'translate(400%2084)%20rotate(9)'%3E%3Cpath%20d%3D'M0%2026%20L12%205%20l8%2013'%2F%3E%3Cpath%20d%3D'M14%202%20l-2%2010%2010%20-1'%2F%3E%3Cpath%20d%3D'M20%2044%20h-24%20l7%20-12'%2F%3E%3Cpath%20d%3D'M-8%2040%20l9%205%20-4%20-10'%2F%3E%3Cpath%20d%3D'M28%2022%20l12%2021%20-14%201'%2F%3E%3Cpath%20d%3D'M44%2049%20l-9%20-5%203%2010'%2F%3E%3C%2Fg%3E%3C!--%20crushed%20can%20--%3E%3Cg%20transform%3D'translate(160%20260)%20rotate(7)'%3E%3Cellipse%20cx%3D'14'%20cy%3D'4'%20rx%3D'14'%20ry%3D'4.5'%2F%3E%3Cpath%20d%3D'M0%204%20c3%208%20-4%2012%201%2020%20c4%207%20-3%2010%201%2016%20a14%204.5%200%200%200%2026%200%20c3%20-7%20-2%20-10%201%20-16%20c4%20-8%20-2%20-12%20-1%20-20'%2F%3E%3Cpath%20d%3D'M9%202.5%20h10'%2F%3E%3C%2Fg%3E%3C!--%20leaf%20--%3E%3Cg%20transform%3D'translate(452%20300)%20rotate(-18)'%3E%3Cpath%20d%3D'M0%2040%20Q-2%206%2036%200%20Q40%2036%206%2042%20Q2%2042%200%2040%20Z'%2F%3E%3Cpath%20d%3D'M4%2038%20Q16%2024%2032%206'%2F%3E%3C%2Fg%3E%3C!--%20circuit%20chip%20(ITAD)%20--%3E%3Cg%20transform%3D'translate(272%20128)%20rotate(-5)'%3E%3Crect%20x%3D'0'%20y%3D'0'%20width%3D'30'%20height%3D'30'%20rx%3D'5'%2F%3E%3Crect%20x%3D'9'%20y%3D'9'%20width%3D'12'%20height%3D'12'%20rx%3D'2'%2F%3E%3Cpath%20d%3D'M5%20-6%20v6%20M15%20-6%20v6%20M25%20-6%20v6%20M5%2030%20v6%20M15%2030%20v6%20M25%2030%20v6%20M-6%205%20h6%20M-6%2015%20h6%20M-6%2025%20h6%20M30%205%20h6%20M30%2015%20h6%20M30%2025%20h6'%2F%3E%3C%2Fg%3E%3C!--%20battery%20--%3E%3Cg%20transform%3D'translate(84%20420)%20rotate(12)'%3E%3Crect%20x%3D'0'%20y%3D'4'%20width%3D'40'%20height%3D'20'%20rx%3D'4'%2F%3E%3Crect%20x%3D'40'%20y%3D'10'%20width%3D'5'%20height%3D'8'%20rx%3D'1.5'%2F%3E%3Cpath%20d%3D'M20%207%20l-6%208%20h7%20l-5%207'%2F%3E%3C%2Fg%3E%3C!--%20cardboard%20box%20--%3E%3Cg%20transform%3D'translate(330%20430)%20rotate(-8)'%3E%3Crect%20x%3D'0'%20y%3D'8'%20width%3D'34'%20height%3D'26'%20rx%3D'2'%2F%3E%3Cpath%20d%3D'M0%208%20L6%200%20h22%20l6%208%20M17%208%20V0'%2F%3E%3C%2Fg%3E%3C!--%20water%20drop%20--%3E%3Cg%20transform%3D'translate(500%20480)%20rotate(6)'%3E%3Cpath%20d%3D'M11%200%20C18%2010%2022%2015%2022%2021%20a11%2011%200%201%201%20-22%200%20C0%2015%204%2010%2011%200%20Z'%2F%3E%3C%2Fg%3E%3C!--%20gear%20--%3E%3Cg%20transform%3D'translate(40%20300)%20rotate(20)'%3E%3Ccircle%20cx%3D'14'%20cy%3D'14'%20r%3D'8'%2F%3E%3Ccircle%20cx%3D'14'%20cy%3D'14'%20r%3D'3'%2F%3E%3Cpath%20d%3D'M14%202%20v4%20M14%2022%20v4%20M2%2014%20h4%20M22%2014%20h4%20M5.5%205.5%20l2.8%202.8%20M19.7%2019.7%20l2.8%202.8%20M22.5%205.5%20l-2.8%202.8%20M8.3%2019.7%20l-2.8%202.8'%2F%3E%3C%2Fg%3E%3C!--%20newspaper%20%2F%20sheet%20--%3E%3Cg%20transform%3D'translate(220%20500)%20rotate(-10)'%3E%3Crect%20x%3D'0'%20y%3D'0'%20width%3D'30'%20height%3D'22'%20rx%3D'3'%2F%3E%3Cpath%20d%3D'M6%206%20h18%20M6%2011%20h18%20M6%2016%20h10'%2F%3E%3C%2Fg%3E%3C%2Fg%3E%3C%2Fsvg%3E");
  background-size:560px 560px; background-attachment:fixed;
}
::selection{ background:var(--ink); color:var(--paper); }
::-webkit-scrollbar{ width:10px; height:10px; }
::-webkit-scrollbar-thumb{ background:#D6D5D0; border-radius:999px; border:2.5px solid var(--paper); }
::-webkit-scrollbar-track{ background:transparent; }

/* page entrance — content settles like a sheet of paper */
.main .block-container, .stMainBlockContainer{
  animation:rkPage .5s var(--ease) both; padding-top:.6rem; max-width:1400px; }
/* opacity-only on the page container — a TRANSFORM here would hijack
   position:fixed for everything inside (Recy would scroll with the page) */
@keyframes rkPage{ from{opacity:0;} to{opacity:1;} }
@keyframes rkRise{ from{opacity:0; transform:translateY(16px) scale(.995);} to{opacity:1; transform:none;} }

[data-testid="stHeader"]{ background:transparent; }

/* ── sidebar retired — navigation lives in the top capsule bar ── */
[data-testid="stSidebar"], [data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"]{ display:none !important; }

/* ═══ display type — Bricolage Grotesque, editorial and tight ═══ */
h1{ font-family:'Bricolage Grotesque', 'Geist', sans-serif !important;
    font-weight:600; font-size:2.4rem; letter-spacing:-.045em; line-height:1.08;
    color:var(--ink); }
[data-testid="stHeading"] h1, .stMainBlockContainer h1{ padding-top:.1rem; margin-bottom:.15rem; }
[data-testid="stMarkdownContainer"] > p:first-child{ margin-top:.1rem; }
h2{ font-family:'Bricolage Grotesque', 'Geist', sans-serif !important;
    font-weight:600; letter-spacing:-.035em; color:var(--ink); }
h3{ font-family:'Bricolage Grotesque', 'Geist', sans-serif !important;
    font-weight:500; letter-spacing:-.025em; color:var(--ink); }
p, li, label{ color:var(--ink-soft); }
small, .stCaption, [data-testid="stCaptionContainer"]{ color:var(--grey) !important; }

/* ═══ the top capsule nav — a segmented control on warm paper ═══ */
div[role="radiogroup"][aria-label="Navigate"]{
  display:flex; width:max-content; margin:0 auto; gap:2px;
  background:var(--paper-3); border:1px solid var(--hair-soft);
  border-radius:999px; padding:5px; flex-wrap:nowrap;
  box-shadow:inset 0 1px 2px rgba(22,22,15,.05);
}
div[role="radiogroup"][aria-label="Navigate"] label{
  margin:0 !important; padding:8px 19px; border-radius:999px; cursor:pointer;
  transition:background .3s var(--ease), box-shadow .3s var(--ease), transform .15s var(--ease);
  white-space:nowrap; position:relative;
}
div[role="radiogroup"][aria-label="Navigate"] label > div:first-child{ display:none; } /* radio dot */
div[role="radiogroup"][aria-label="Navigate"] label p{
  font-family:'Geist', sans-serif; font-weight:600; font-size:.855rem;
  letter-spacing:-.005em; color:var(--grey); transition:color .25s var(--ease); }
div[role="radiogroup"][aria-label="Navigate"] label:hover p{ color:var(--ink); }
div[role="radiogroup"][aria-label="Navigate"] label:active{ transform:scale(.97); }
div[role="radiogroup"][aria-label="Navigate"] label:has(input:checked){
  background:var(--ink); box-shadow:0 2px 6px rgba(22,22,15,.28), 0 8px 18px -6px rgba(22,22,15,.30); }
div[role="radiogroup"][aria-label="Navigate"] label:has(input:checked) p{ color:#fff !important; }

/* header block — logo & meta chip */
.st-key-rkheader{ padding:2px 0 10px; border-bottom:1px solid var(--hair-soft); margin-bottom:.7rem; }
.st-key-rkheader [data-testid="stImage"] img{ border-radius:14px;
  box-shadow:var(--shadow-s); image-rendering:auto; }
/* the status chip: a quiet mono meta label with the green whisper */
.st-key-rkheader [data-testid="stExpander"]{
  border:1px solid var(--hair-soft); border-radius:999px; background:var(--paper-2);
  box-shadow:none; overflow:hidden; }
.st-key-rkheader [data-testid="stExpander"] summary{ padding:.35rem .9rem; min-height:0; }
.st-key-rkheader [data-testid="stExpander"] summary p{
  font-family:'Kode Mono', monospace; font-size:.68rem; font-weight:600;
  text-transform:uppercase; letter-spacing:.06em; color:var(--green); }
.st-key-rkheader [data-testid="stExpander"] summary:hover p{ color:var(--ink); }

/* ═══ metric cards — white paper, Bricolage numerals ═══ */
[data-testid="stMetric"]{
  background:#fff; border:1px solid var(--hair-soft); border-radius:20px;
  padding:1.05rem 1.25rem; box-shadow:var(--shadow-s);
  transition:transform .35s var(--ease), box-shadow .35s var(--ease);
  animation:rkRise .55s var(--ease) both;
}
[data-testid="stMetric"]:hover{ transform:translateY(-3px); box-shadow:var(--shadow-m); }
[data-testid="stMetricValue"]{
  font-family:'Bricolage Grotesque', sans-serif; font-weight:600;
  letter-spacing:-.03em; color:var(--ink); }
[data-testid="stMetricLabel"]{
  font-family:'Geist', sans-serif; font-weight:600; font-size:.72rem;
  text-transform:uppercase; letter-spacing:.07em; color:var(--grey); }

/* ═══ tabs — editorial uppercase, black underline glides ═══ */
.stTabs [data-baseweb="tab-list"]{ gap:22px; border-bottom:1px solid var(--hair-soft); }
.stTabs [data-baseweb="tab"]{
  padding:9px 2px; background:transparent;
  font-family:'Geist', sans-serif; font-weight:600; font-size:.8rem;
  text-transform:uppercase; letter-spacing:.055em; color:var(--grey);
  transition:color .25s var(--ease); }
.stTabs [data-baseweb="tab"]:hover{ color:var(--ink); background:transparent; }
.stTabs [aria-selected="true"]{ color:var(--ink) !important; }
.stTabs [data-baseweb="tab-highlight"]{ background-color:var(--ink); height:2px; border-radius:2px; }
.stTabs [data-baseweb="tab-border"]{ background-color:var(--hair-soft); }

/* ═══ buttons ═══
   action buttons   → warm-black pills that lift
   download buttons → outline pills that fill on hover                      */
.stButton>button, .stFormSubmitButton>button{
  background:var(--ink); color:#fff !important;
  border:1px solid var(--ink); border-radius:999px; padding:.52rem 1.35rem;
  font-family:'Geist', sans-serif; font-weight:600; font-size:.875rem;
  box-shadow:0 1px 2px rgba(22,22,15,.2);
  transition:transform .25s var(--ease), box-shadow .25s var(--ease), background .25s var(--ease);
}
.stButton>button:hover, .stFormSubmitButton>button:hover{
  background:#000; transform:translateY(-2px);
  box-shadow:0 4px 8px rgba(22,22,15,.14), 0 14px 28px -8px rgba(22,22,15,.32); }
.stButton>button:active, .stFormSubmitButton>button:active{ transform:translateY(0) scale(.985); }
.stDownloadButton>button{
  background:#fff; color:var(--ink) !important;
  border:1.5px solid var(--ink); border-radius:999px; padding:.5rem 1.3rem;
  font-family:'Geist', sans-serif; font-weight:600; font-size:.875rem;
  box-shadow:none; transition:all .25s var(--ease);
}
.stDownloadButton>button:hover{
  background:var(--ink); color:#fff !important; transform:translateY(-2px);
  box-shadow:0 12px 24px -8px rgba(22,22,15,.35); }
.stDownloadButton>button:active{ transform:translateY(0) scale(.985); }
/* button captions render as <p> inside the button — they must follow the
   button's own color (white on ink pills), not the page's paragraph ink */
.stButton>button p, .stDownloadButton>button p, .stFormSubmitButton>button p,
[data-testid="stFileUploaderDropzone"] button p{ color:inherit !important; }

/* ═══ tables · expanders · inputs ═══ */
[data-testid="stDataFrame"], [data-testid="stTable"]{
  border-radius:16px; overflow:hidden; border:1px solid var(--hair-soft);
  box-shadow:var(--shadow-s); }
[data-testid="stExpander"]{
  border:1px solid var(--hair-soft); border-radius:16px; background:#fff;
  box-shadow:var(--shadow-s); transition:box-shadow .3s var(--ease); }
[data-testid="stExpander"]:hover{ box-shadow:var(--shadow-m); }
[data-testid="stExpander"] summary p{ font-weight:600; color:var(--ink); }
hr{ border-color:var(--hair-soft); }

[data-testid="stFileUploaderDropzone"]{
  border:1.5px dashed var(--hair); border-radius:20px; background:var(--paper-2);
  transition:border-color .3s var(--ease), background .3s var(--ease); }
[data-testid="stFileUploaderDropzone"]:hover{ border-color:var(--ink); background:var(--paper-3); }
[data-testid="stFileUploaderDropzone"] button{
  border-radius:999px; border:1.5px solid var(--ink); background:#fff;
  color:var(--ink); font-weight:600; }

/* text inputs / selects — soft paper fields */
[data-baseweb="input"], [data-baseweb="select"] > div{ border-radius:12px !important; }
[data-testid="stTextInput"] input{ font-family:'Geist', sans-serif; }

/* alerts — quieter, warmer */
[data-testid="stAlert"]{ border-radius:14px; border:1px solid var(--hair-soft); }
</style>
""", unsafe_allow_html=True)


# ── Top header: logo · capsule nav · build/status ─────────────────────────────
# Same page list & variable as the old sidebar — routing logic is untouched.
with st.container(key="rkheader"):
    _hdr_logo, _hdr_nav, _hdr_meta = st.columns([0.16, 0.66, 0.18], vertical_alignment="center")
    with _hdr_logo:
        st.image("Recykal logo.jpg", width=124)
    with _hdr_nav:
        page = st.radio(
            "Navigate",
            ["Upload Files", "View Databases", "Cleaning", "Summary Report", "Management Reports"],
            horizontal=True,
            label_visibility="collapsed",
        )
    with _hdr_meta:
        status = db.all_db_status()
        loaded = [s for s, v in status.items() if v["exists"]]
        # build tag — bump when pushing significant changes; confirms which version
        # a deployed instance is running (hosted apps can lag behind the repo)
        with st.expander(f"{len(loaded)}/{len(status)} sheets · v3.3.0"):
            st.caption("build: **v3.3.0 — Re-Commerce live-costed from the Amazon×Recykal Google Sheet after 17-Jul; fixed detail before it**")
            for sheet in loaded:
                tbls = status[sheet]["tables"]
                row_str = " · ".join(f"{t}: {n:,}" for t, n in tbls.items())
                st.caption(f"**{sheet}** — {row_str}")


# ══════════════════════════════════════════════════════════════════════════════
# RECY — floating robot (eyes follow cursor + activity quips) with click-to-chat
# ══════════════════════════════════════════════════════════════════════════════
import assistant as _assistant
import streamlit.components.v1 as _components

_RECY_QUIPS = {
    "Upload Files":       "Drop those Zoho files on me! 📥",
    "View Databases":     "Peeking under the hood? 🔍",
    "Cleaning":           "All tidied up ✨",
    "Summary Report":     "Ohh — grabbing the sheets? 📊 Click me to chat!",
    "Management Reports": "The nitty-gritty lives here 🧾",
}

# The chat is a popover whose trigger is CSS-fixed top-right and made invisible;
# the animated robot is drawn on top of it, so clicking the robot opens the chat.
_recy_pop = st.popover("Recy", use_container_width=False)
with _recy_pop:
    st.markdown("**🤖 Recy** — ask about the app or the numbers")
    if not _assistant.is_configured():
        st.caption("Add a Gemini API key to `.streamlit/secrets.toml` (`[gemini]` → `api_key`) to switch me on.")
    # process a pending question (set by the form below, handled on rerun)
    _pend = st.session_state.pop("recy_pending", None)
    if _pend:
        if isinstance(_pend, str):                     # backward compat
            _pend = {"q": _pend, "imgs": []}
        _hist = st.session_state.setdefault("recy_hist", [])
        _hist.append({"role": "user", "content": _pend["q"],
                      "imgs": _pend.get("imgs") or []})
        # live app-state snapshot so Recy knows where the user is & what's loaded
        _built = bool(st.session_state.get("_recy_summaries"))
        _state = (f"CURRENT STATE: the user is on the '{page}' page. "
                  f"Datasets loaded: {', '.join(loaded) if loaded else 'none yet'}. "
                  f"Profitability report is {'BUILT and on screen' if _built else 'not built yet'}. "
                  "Answer with this in mind — don't tell them to upload/build things that are already done.")
        with st.spinner("Recy is thinking…"):
            _ans = _assistant.ask(_pend["q"], st.session_state.get("_recy_summaries"),
                                  _hist, app_state=_state,
                                  images=_pend.get("imgs") or None)
        _txt, _chart = _assistant.extract_chart(_ans)
        _hist.append({"role": "assistant", "content": _txt, "chart": _chart})
    # fixed-size scrollable log — latest at the bottom, scroll up for older
    with st.container(height=300):
        _h = st.session_state.get("recy_hist", [])
        if not _h:
            st.caption("Hi! I'm Recy 🤖 — ask me how the app works, a rule, or a number.")
        for _m in _h:
            _msg = st.chat_message("user" if _m["role"] == "user" else "assistant")
            _msg.write(_m["content"])
            for _mime, _bd in _m.get("imgs", []):
                import base64 as _b64d
                _msg.image(_b64d.b64decode(_bd))
            if _m.get("chart"):
                _cdf = _assistant.chart_frame(_m["chart"], st.session_state.get("_recy_summaries"))
                if _cdf is not None:
                    if _m["chart"].get("title"):
                        _msg.caption(f"📊 {_m['chart']['title']} — drawn from the live summary")
                    (_msg.line_chart if _m["chart"].get("type") == "line"
                     else _msg.bar_chart)(_cdf, height=240)
        st.markdown('<span class="recylog-end"></span>', unsafe_allow_html=True)
    with st.form("recy_form", clear_on_submit=True):
        _q = st.text_input("Ask…", label_visibility="collapsed",
                           placeholder="Ask about the app, the numbers, or an attached image…")
        _img_files = st.file_uploader("📷 Attach image(s) — screenshots of workbooks, errors…",
                                      type=["png", "jpg", "jpeg", "webp"],
                                      accept_multiple_files=True, key="recy_imgs")
        if st.form_submit_button("Ask", use_container_width=True) and _q.strip():
            import base64 as _b64e
            _imgs = [( _f.type or "image/png", _b64e.b64encode(_f.getvalue()).decode())
                     for _f in (_img_files or [])[:4]]
            st.session_state["recy_pending"] = {"q": _q.strip(), "imgs": _imgs}
            st.rerun()
    # change requests: Recy drafts the change in chat; this files it for HUMAN
    # review as a GitHub issue — Recy never edits code or data itself.
    if _assistant.github_configured() and st.session_state.get("recy_hist"):
        if st.button("📝 File the last exchange as a change request (GitHub issue)",
                     key="recy_cr", use_container_width=True):
            _h2 = st.session_state["recy_hist"]
            _lq = next((m["content"] for m in reversed(_h2) if m["role"] == "user"), "")
            _la = next((m["content"] for m in reversed(_h2) if m["role"] == "assistant"), "")
            _ok, _res = _assistant.file_change_request(
                f"Change request: {_lq[:100]}",
                "**Request (asked in-app):**\n\n" + _lq
                + "\n\n**Recy's draft:**\n\n" + _la)
            (st.success if _ok else st.error)(_res)
            if _ok:
                st.caption("A human reviews & merges it — nothing changes automatically.")

# Fix the popover trigger as an invisible 56px hotspot; robot SVG drawn over it.
st.markdown("""
<style>
[data-testid="stPopover"]{position:fixed !important;bottom:26px;right:26px;z-index:100000;width:56px;}
[data-testid="stPopover"] button{width:56px;height:56px;border-radius:50%;
   background:transparent !important;border:none !important;color:transparent !important;
   box-shadow:none !important;}
@keyframes recybob{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
</style>
""", unsafe_allow_html=True)

st.markdown(
    f"""
<div style="position:fixed;bottom:22px;right:26px;z-index:100001;
            display:flex;align-items:flex-end;gap:6px;pointer-events:none;">
  <div id="recy-bubble" style="max-width:210px;background:#16160F;color:#fff;padding:8px 11px;
              border-radius:12px 12px 2px 12px;font-size:11.5px;line-height:1.35;margin-bottom:6px;
              box-shadow:0 4px 12px rgba(0,0,0,.22);transition:all .15s;">{_RECY_QUIPS.get(page, "Hey, I'm Recy 🤖 — click me!")}</div>
  <div id="recy-bot" style="position:relative;filter:drop-shadow(0 3px 5px rgba(0,0,0,.28));animation:recybob 2.6s ease-in-out infinite;">
    <svg width="46" height="50" viewBox="0 0 46 50" xmlns="http://www.w3.org/2000/svg">
      <line x1="23" y1="3" x2="23" y2="12" stroke="#16160F" stroke-width="2.4"/>
      <circle id="recy-antenna" cx="23" cy="3.5" r="3.2" fill="#12b866" style="transition:fill .3s ease;"/>
      <rect x="3" y="21" width="4.5" height="12" rx="2.2" fill="#16160F"/>
      <rect x="38.5" y="21" width="4.5" height="12" rx="2.2" fill="#16160F"/>
      <rect x="6" y="12" width="34" height="28" rx="9" fill="#ffffff" stroke="#16160F" stroke-width="2.6"/>
      <rect x="11" y="18" width="24" height="15" rx="6" fill="#F2F2EE"/>
      <!-- eyebrows (curious) -->
      <g id="recy-acc-brows" style="opacity:0;transition:opacity .25s ease;">
        <line x1="14.5" y1="21" x2="20" y2="21.4" stroke="#16160F" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="26" y1="19.8" x2="31.5" y2="21.6" stroke="#16160F" stroke-width="1.5" stroke-linecap="round"/>
      </g>
      <!-- the eyes (hidden behind glasses / heart-eyes) -->
      <g id="recy-eyes" style="transition:opacity .2s ease;">
        <circle id="recy-eye-l" cx="17.5" cy="25.5" r="3.3" fill="#16160F" style="transform-box:fill-box;transform-origin:center;transition:transform .16s ease-out;"/>
        <circle id="recy-eye-r" cx="28.5" cy="25.5" r="3.3" fill="#16160F" style="transform-box:fill-box;transform-origin:center;transition:transform .16s ease-out;"/>
      </g>
      <!-- sunglasses (cool) -->
      <g id="recy-acc-glasses" style="opacity:0;transition:opacity .25s ease;">
        <rect x="12.8" y="22.2" width="8.6" height="6.4" rx="3.1" fill="#16160F"/>
        <rect x="24.6" y="22.2" width="8.6" height="6.4" rx="3.1" fill="#16160F"/>
        <rect x="21.2" y="24.3" width="3.6" height="1.6" fill="#16160F"/>
        <line x1="7.5" y1="24" x2="12.8" y2="24.6" stroke="#16160F" stroke-width="1.4"/>
        <line x1="33.2" y1="24.6" x2="38.5" y2="24" stroke="#16160F" stroke-width="1.4"/>
        <line x1="14.5" y1="24" x2="18.5" y2="24" stroke="#D6D5D0" stroke-width="1" stroke-linecap="round" opacity=".7"/>
        <line x1="26.5" y1="24" x2="30.5" y2="24" stroke="#D6D5D0" stroke-width="1" stroke-linecap="round" opacity=".7"/>
      </g>
      <path id="recy-mouth" d="M18 30.5 Q23 34 28 30.5" stroke="#16160F" stroke-width="2" fill="none" stroke-linecap="round" style="transition:d .28s ease;"/>
      <circle cx="12.5" cy="30" r="1.8" fill="#D6D5D0"/>
      <circle cx="33.5" cy="30" r="1.8" fill="#D6D5D0"/>
      <!-- sweat drop (alert) -->
      <g id="recy-acc-sweat" fill="#4fa3ff" style="opacity:0;transition:opacity .25s ease;">
        <path transform="translate(35 14.5)" d="M0 0 C2.2 3 2.2 5.2 0 5.2 C-2.2 5.2 -2.2 3 0 0 Z"/>
      </g>
      <!-- sparkles (celebrate) -->
      <g id="recy-acc-sparkles" fill="#f4b400" style="opacity:0;transition:opacity .25s ease;">
        <path transform="translate(9 15)"        d="M0 -2.6 L0.7 -0.7 L2.6 0 L0.7 0.7 L0 2.6 L-0.7 0.7 L-2.6 0 L-0.7 -0.7 Z"/>
        <path transform="translate(37 14) scale(.8)" d="M0 -2.6 L0.7 -0.7 L2.6 0 L0.7 0.7 L0 2.6 L-0.7 0.7 L-2.6 0 L-0.7 -0.7 Z"/>
        <path transform="translate(38 34) scale(.9)" d="M0 -2.6 L0.7 -0.7 L2.6 0 L0.7 0.7 L0 2.6 L-0.7 0.7 L-2.6 0 L-0.7 -0.7 Z"/>
        <path transform="translate(8 35) scale(.7)"  d="M0 -2.6 L0.7 -0.7 L2.6 0 L0.7 0.7 L0 2.6 L-0.7 0.7 L-2.6 0 L-0.7 -0.7 Z"/>
      </g>
      <rect x="15" y="40" width="16" height="6" rx="3" fill="#16160F"/>
    </svg>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

_components.html(
    """
<script>
(function(){
  const pdoc = window.parent.document;
  // All mutable behaviour lives on pdoc.__recy so a Streamlit rerun (which re-injects
  // this script) refreshes the logic WITHOUT re-adding listeners — edits hot-apply,
  // no full browser refresh needed. The listeners/intervals below bind exactly once.
  const R = pdoc.__recy = (pdoc.__recy || {mood:'idle', moodT:null, wasThinking:false, last:''});

  // vertical tab labels → clean display name; matched on a punctuation-stripped key
  // ("IT AD"→"itad", "IB(B2B)"→"ibb2b") so spaces/brackets don't make the match miss.
  const VERTS=[['endgenerator','END GENERATOR'],['metal','END GENERATOR'],['plastic','PLASTIC'],
    ['recommerce','RE-COMMERCE'],['itad','IT AD'],['afr','AFR'],['m4','M4'],
    ['ibb2b','ENTERPRISE'],['ibwarehouse','PROCESSING CENTER'],['enterprise','ENTERPRISE'],
    ['rewerse','REWERSE']];
  R.quip=function(t){t=(t||'').toLowerCase();if(!t)return null;
    if(t.includes('download'))return 'Ohh — grabbing the sheets? 📊';
    if(t.includes('send')||t.includes('email'))return 'Emailing the team? 📧';
    if(t.includes('upload')||t.includes('choose files')||t.includes('drop')||t.includes('browse'))return 'Feed me those Zoho files! 📥';
    if(t.includes('merge')||t.includes('compute')||t.includes('run pipeline'))return 'Crunching the numbers… 🔧';
    if(t.includes('summary'))return 'The money view 💰';
    if(t.includes('receiv'))return 'Who owes us? 🧾';
    if(t.includes('payable'))return 'Who we owe 💸';
    if(t.includes('all categories'))return 'The whole picture 🗂️';
    const key=t.replace(/[^a-z0-9]/g,'');
    for(const [k,label] of VERTS){if(key===k)return label+' — nice pick! 👀';}
    if(t.includes('view database'))return 'Peeking under the hood 🔍';
    if(t.includes('cleaning'))return 'All tidied up ✨';
    return null;};
  R.setBubble=function(t){const b=pdoc.getElementById('recy-bubble');if(b&&t&&t!==R.last){b.textContent=t;R.last=t;}};
  R.hover=function(e){const el=e.target.closest('button,[role="tab"],label,a,summary,[data-testid="stFileUploaderDropzone"]');
    if(!el)return;const q=R.quip((el.innerText||el.textContent||'').trim().slice(0,50));if(q)R.setBubble(q);};

  // ── mood engine ───────────────────────────────────────────────────────────
  // Each mood reshapes Recy's OWN face — no floating stickers. A mood declares:
  //   mouth : the #recy-mouth path
  //   eyeL/eyeR : per-eye transform (lets us wink one eye)
  //   ant  : antenna colour
  //   acc  : which face accessories to show — 'brows','glasses','sweat','sparkles'
  //   hideEyes : hide the plain eyes (when glasses / heart-eyes take over)
  // Add a new expression by adding one entry (+ an accessory <g> in the SVG if needed).
  R.ACCS=['brows','glasses','sweat','sparkles'];
  R.MOODS={
    idle:     {mouth:'M18 30.5 Q23 34 28 30.5',                          eyeL:'',                eyeR:'',                ant:'#12b866', acc:[]},
    thinking: {mouth:'M19 31.5 H27',                                     eyeL:'translateY(-1.6px)',eyeR:'translateY(-1.6px)',ant:'#f4b400', acc:['brows']},
    happy:    {mouth:'M16.5 29.5 Q23 37 29.5 29.5',                      eyeL:'scaleY(.55)',     eyeR:'scaleY(.55)',     ant:'#12b866', acc:[]},
    curious:  {mouth:'M18.5 31 Q23 33 27.5 30.5',                        eyeL:'translateY(-1px)',eyeR:'translateY(-1px)',ant:'#12b866', acc:['brows']},
    wink:     {mouth:'M17 30 Q23 35.5 29 30.5',                          eyeL:'scaleY(.12)',     eyeR:'',                ant:'#12b866', acc:[]},
    cool:     {mouth:'M17.5 31 Q23 34.5 28.5 31',                        eyeL:'',                eyeR:'',                ant:'#12b866', acc:['glasses'], hideEyes:true},
    alert:    {mouth:'M20.5 32 a2.5 2.5 0 1 0 5 0 a2.5 2.5 0 1 0 -5 0',  eyeL:'scale(1.25)',     eyeR:'scale(1.25)',     ant:'#e23b3b', acc:['sweat']},
    celebrate:{mouth:'M15.5 29 Q23 39 30.5 29',                          eyeL:'scaleY(.55)',     eyeR:'scaleY(.55)',     ant:'#f4b400', acc:['sparkles']},
  };
  // faces Recy cycles through each time you open the chat — a little surprise
  R.GREETINGS=['happy','wink','curious','cool','celebrate'];
  R.greetIdx=(R.greetIdx==null?-1:R.greetIdx);
  R.setEyes=function(lt,rt){const l=pdoc.getElementById('recy-eye-l'),r=pdoc.getElementById('recy-eye-r');
    if(l)l.style.transform=lt;if(r)r.style.transform=rt;};
  R.paintEyes=function(tf){R.setEyes(tf,tf);};   // used by cursor-follow & blink (both eyes alike)
  R.setMood=function(name,revert){const m=R.MOODS[name]||R.MOODS.idle;R.mood=name;
    const mo=pdoc.getElementById('recy-mouth');if(mo)mo.setAttribute('d',m.mouth);
    const an=pdoc.getElementById('recy-antenna');if(an)an.style.fill=m.ant;
    const eyes=pdoc.getElementById('recy-eyes');if(eyes)eyes.style.opacity=m.hideEyes?'0':'1';
    if(name==='idle')R.setEyes('','');           // idle hands the eyes back to the cursor
    else R.setEyes(m.eyeL||'',m.eyeR||'');
    R.ACCS.forEach(function(a){const g=pdoc.getElementById('recy-acc-'+a);
      if(g)g.style.opacity=(m.acc&&m.acc.indexOf(a)>=0)?'1':'0';});
    clearTimeout(R.moodT);
    if(revert)R.moodT=setTimeout(function(){R.setMood('idle');},revert);
  };
  pdoc.__recySetMood=R.setMood;                // exposed for preview/manual testing

  // opening the chat: cycle to the next fun greeting face
  R.greet=function(){R.greetIdx=(R.greetIdx+1)%R.GREETINGS.length;
    R.setMood(R.GREETINGS[R.greetIdx],2600);};

  R.onClick=function(e){
    R.hover(e);
    const el=e.target.closest('button,[role="tab"],label,a,summary,[data-testid="stFileUploaderDropzone"],[data-testid="stDownloadButton"],[data-testid="stPopover"]');
    if(!el)return;const t=(el.innerText||el.textContent||'').trim().toLowerCase();
    // specific actions win first; the bare popover trigger (empty label) → new face
    if(t==='ask'){R.setMood('thinking');}
    else if(t.includes('download')||el.closest('[data-testid="stDownloadButton"]')){R.setMood('celebrate',3800);}
    else if(el.closest('[data-testid="stPopover"]')&&(t===''||t.includes('recy'))){R.greet();}  // clicked Recy's face
  };
  R.onMove=function(e){
    if(R.mood!=='idle')return;
    const bot=pdoc.getElementById('recy-bot');if(!bot)return;
    const r=bot.getBoundingClientRect();const cx=r.left+r.width/2,cy=r.top+r.height/2;
    const a=Math.atan2(e.clientY-cy,e.clientX-cx),d=2.4;
    R.paintEyes('translate('+Math.cos(a)*d+'px,'+Math.sin(a)*d+'px)');
  };
  R.scrollLog=function(){const m=pdoc.querySelector('.recylog-end');if(!m)return;
    let p=m.parentElement;for(let i=0;i<8&&p;i++){if(p.scrollHeight>p.clientHeight+4){p.scrollTop=p.scrollHeight;return;}p=p.parentElement;}};
  R.reactToState=function(){
    if(pdoc.querySelector('[data-testid="stException"]')&&R.mood!=='alert'){R.setMood('alert',4000);return;}
    const spin=/thinking/i.test((pdoc.querySelector('[data-testid="stSpinner"]')||{}).innerText||'');
    if(spin){R.wasThinking=true;}
    else if(R.wasThinking){R.wasThinking=false;if(R.mood==='thinking')R.setMood('happy',2800);}
    const ok=Array.from(pdoc.querySelectorAll('[data-testid="stAlert"],[data-baseweb="notification"]'))
      .some(function(n){return /sent to/i.test(n.innerText||'');});
    if(ok&&R.mood!=='celebrate')R.setMood('celebrate',3000);
  };


  // ── roaming pet engine — Recy wanders the WHOLE screen when idle ──────────
  // Desktop-pet style: strolls to random spots, perches on top of buttons/tabs,
  // lingers, eventually heads home to his corner. Never wanders while the chat
  // is open or he's thinking; freezes when the cursor comes near so he's always
  // clickable; the chat hotspot travels with him.
  R.BOTW=46; R.BOTH=50; R.PAD=26;
  R.homeX=function(){return pdoc.documentElement.clientWidth-R.PAD-R.BOTW;};
  R.homeY=function(){return pdoc.documentElement.clientHeight-22-R.BOTH;};
  if(R.px===undefined){R.px=null;R.py=null;}   // null = anchored at his corner
  R.tx=R.tx||null; R.ty=R.ty||null; R.pauseT=R.pauseT||0;
  R.nextRoamAt=R.nextRoamAt||(Date.now()+15000);
  R.mx=-9999; R.my=-9999;
  R.chatOpen=function(){const p=pdoc.querySelector('[data-testid="stPopover"]');
    return !!(p&&p.querySelector('button[aria-expanded="true"]'));};
  R.pickTarget=function(w,h){
    // 60%: perch on a visible button / tab / expander header
    if(Math.random()<0.6){
      const els=Array.from(pdoc.querySelectorAll('button,[role="tab"],summary'))
        .filter(function(el){if(!el.offsetParent)return false;
          const r=el.getBoundingClientRect();
          return r.width>=46&&r.height>=18&&r.top>96&&r.bottom<h-60&&r.left>36&&r.right<w-36;});
      if(els.length){const r=els[(Math.random()*els.length)|0].getBoundingClientRect();
        return {x:Math.min(Math.max(r.left+r.width/2-R.BOTW/2,10),w-R.BOTW-10),
                y:Math.max(r.top-R.BOTH+8,70)};}                 // sit ON its top edge
    }
    return {x:40+Math.random()*Math.max(w-140,60),               // or any open spot
            y:100+Math.random()*Math.max(h-280,60)};
  };
  R.applyPos=function(){const bot=pdoc.getElementById('recy-bot');if(!bot)return;
    const cont=bot.parentElement,pop=pdoc.querySelector('[data-testid="stPopover"]'),
          bub=pdoc.getElementById('recy-bubble');
    if(R.px==null){cont.style.left='';cont.style.top='';cont.style.right='26px';cont.style.bottom='22px';
      if(pop){pop.style.left='';pop.style.top='';pop.style.right='26px';pop.style.bottom='26px';}
      if(bub)bub.style.display='';
      bot.style.transform='';bot.style.animation='';return;}
    if(bub)bub.style.display='none';            // quips live at home only
    cont.style.right='auto';cont.style.bottom='auto';
    cont.style.left=R.px+'px';cont.style.top=R.py+'px';
    if(pop){pop.style.right='auto';pop.style.bottom='auto';
      pop.style.left=R.px+'px';pop.style.top=R.py+'px';}};
  R.roamTick=function(){
    const bot=pdoc.getElementById('recy-bot');if(!bot)return;
    const w=pdoc.documentElement.clientWidth,h=pdoc.documentElement.clientHeight;
    if(w<760||pdoc.defaultView.matchMedia('(prefers-reduced-motion: reduce)').matches){
      if(R.px!=null){R.px=null;R.py=null;R.applyPos();}return;}
    const now=Date.now(), busy=R.chatOpen()||R.mood!=='idle';
    const r=bot.getBoundingClientRect();
    const near=Math.abs(R.mx-(r.left+r.width/2))<70&&Math.abs(R.my-(r.top+r.height/2))<90;
    if(R.px==null){                                       // anchored at home
      if(busy||near||now<R.nextRoamAt)return;
      R.px=R.homeX();R.py=R.homeY();
      const t=R.pickTarget(w,h);R.tx=t.x;R.ty=t.y;        // set off!
    }
    if(busy){R.tx=R.homeX();R.ty=R.homeY();}              // called back to duty
    if((near&&!busy)||now<R.pauseT){R.applyPos();return;} // freeze / linger
    const dx=R.tx-R.px,dy=R.ty-R.py,dist=Math.hypot(dx,dy),step=2.4;
    if(dist<=step){                                       // arrived
      R.px=R.tx;R.py=R.ty;
      if(Math.hypot(R.px-R.homeX(),R.py-R.homeY())<6){    // back home → re-anchor
        R.px=null;R.py=null;R.tx=null;R.ty=null;
        R.nextRoamAt=now+20000+Math.random()*40000;R.applyPos();return;}
      R.pauseT=now+3000+Math.random()*7000;               // perch a while
      bot.style.transform='scaleX(1)';                    // sit straight
      if(Math.random()<0.5){R.tx=R.homeX();R.ty=R.homeY();}
      else{const t=R.pickTarget(w,h);R.tx=t.x;R.ty=t.y;}
      R.applyPos();return;}
    R.px+=dx/dist*step;R.py+=dy/dist*step;
    bot.style.animation='none';                           // waddle instead of bob
    bot.style.transform='scaleX('+(dx<0?-1:1)+') rotate('+(Math.sin((R.px+R.py)/7)*5).toFixed(2)+'deg)';
    R.applyPos();};

  // ── bind listeners + timers ONCE (all delegate to the R.* above) ───────────
  if(!pdoc.__recyBound){
    pdoc.__recyBound=true;
    pdoc.addEventListener('mouseover',function(e){R.hover(e);},true);
    pdoc.addEventListener('click',function(e){R.onClick(e);},true);
    pdoc.addEventListener('mousemove',function(e){R.mx=e.clientX;R.my=e.clientY;R.onMove(e);},true);
    setInterval(function(){try{R.roamTick();}catch(err){}},40);
    // gentle blink every few seconds, only when idle — so Recy feels alive
    setInterval(function(){
      if(R.mood!=='idle')return;
      const l=pdoc.getElementById('recy-eye-l'),r=pdoc.getElementById('recy-eye-r');
      if(!l||!r)return;const pl=l.style.transform,pr=r.style.transform;
      l.style.transform='scaleY(.1)';r.style.transform='scaleY(.1)';
      setTimeout(function(){if(R.mood==='idle'){l.style.transform=pl;r.style.transform=pr;}},130);
    },4200);
    new MutationObserver(function(){clearTimeout(R.st);
      R.st=setTimeout(function(){R.scrollLog();R.reactToState();},80);})
      .observe(pdoc.body,{childList:true,subtree:true});
  }
})();
</script>
""",
    height=0,
)


# ── Pipeline helper — auto-clean + split without user intervention ────────────
def _auto_clean():
    """Clean every sheet that has raw data but no cleaned table, then split Bill."""
    for sheet, fn in [("Inv",  cleaning.clean_invoice),
                      ("Bill", cleaning.clean_bill),
                      ("CN",   cleaning.clean_cn),
                      ("DN",   cleaning.clean_dn)]:
        if db.read_table(sheet, "cleaned").empty:
            raw = db.read_table(sheet, "raw").drop(columns=["_source_file"], errors="ignore")
            if not raw.empty:
                cleaned, _ = fn(raw)
                db.write_cleaned(cleaned, sheet)
    if db.read_table("Bill", "bill_purchases").empty:
        cleaned_bill = db.read_table("Bill", "cleaned").drop(columns=["_source_file"], errors="ignore")
        if not cleaned_bill.empty:
            pur, log, _ = cleaning.split_bill(cleaned_bill)
            db.write_table(pur, "Bill", "bill_purchases")
            db.write_table(log, "Bill", "bill_logistics")


def _auto_pipeline():
    """Run full pipeline (clean → merge → compute) if raw data exists."""
    _auto_clean()
    if db.read_table("Merged", "profitability").empty:
        inv      = db.read_table("Inv",  "cleaned").drop(columns=["_source_file"], errors="ignore")
        bill_pur = db.read_table("Bill", "bill_purchases").drop(columns=["_source_file"], errors="ignore")
        bill_log = db.read_table("Bill", "bill_logistics").drop(columns=["_source_file"], errors="ignore")
        cn       = db.read_table("CN",   "cleaned").drop(columns=["_source_file"], errors="ignore")
        dn       = db.read_table("DN",   "cleaned").drop(columns=["_source_file"], errors="ignore")
        if not any(df.empty for df in [inv, bill_pur, cn, dn]):
            # Older-bills store (exact shipment match) + Amazon×Recykal chain
            hist = db.load_older_bills()
            ytd = db.load_amazon_ytd()
            amazon_map = cleaning.build_amazon_invoice_map(ytd) if not ytd.empty else {}
            merged, _ = cleaning.run_full_pipeline(
                inv, bill_pur, bill_log if not bill_log.empty else None, cn, dn,
                history_df=hist if not hist.empty else None,
                amazon_map=amazon_map)
            profit = compute.build_profitability(
                merged, logistics_df=bill_log if not bill_log.empty else None,
                no_dn_shipments=db.load_no_dn_shipments()
                | cleaning.void_dn_shipments(
                    db.read_table("DN", "raw").drop(columns=["_source_file"], errors="ignore")))
            db.write_table(merged,  "Merged", "inv_bill_cn_dn")
            db.write_table(profit,  "Merged", "profitability")
            # accumulate line rows permanently — Zoho's export is rolling, so a
            # month's rows would otherwise vanish from later uploads. Upsert by
            # shipment+invoice: late CN/DN updates replace the old version.
            db.upsert_profit_details(profit)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1: Upload
# ══════════════════════════════════════════════════════════════════════════════
if page == "Upload Files":
    st.title("Upload Zoho Excel Files")

    import re as _re

    def _is_history_bill(filename: str) -> bool:
        """
        Older bills file (the 7th upload) is named with extra descriptive words
        (3+ tokens) or a 4-digit year — e.g. 'bills 2025', 'bill_old_recommerce'.
        The current bills file is just 'bill' / 'Bills_1'.
        """
        base = filename.rsplit(".", 1)[0]
        tokens = [t for t in _re.split(r"[\s_\-]+", base) if t]
        has_year = any(_re.fullmatch(r"(19|20)\d{2}", t) for t in tokens)
        return len(tokens) > 2 or has_year

    import difflib as _difflib

    # The ONLY sheets we load — everything else in the workbook is ignored.
    # Each canonical dataset lists case-insensitive name variants; typos are caught
    # by fuzzy matching below. "NO DN" is handled separately (exclusion list).
    _CANON_ALIASES = {
        "Bill": ["bill", "bills"],
        "CN":   ["cn", "creditnote", "creditnotes"],
        "DN":   ["dn", "debitnote", "debitnotes", "vendorcredit", "vendorcredits"],
        "AP":   ["ap", "payable", "payables", "apageing", "apaging"],
        "AR":   ["ar", "receivable", "receivables", "arageing", "araging"],
        "Inv":  ["inv", "invoice", "invoices"],
    }

    def _norm(s) -> str:
        return _re.sub(r"[^a-z0-9]", "", str(s).lower())

    def _canon_sheet(name: str) -> str | None:
        """Resolve a sheet name to a core dataset — case-insensitive + typo-tolerant.
        'Bills'→Bill, 'INV'→Inv, 'Credit Notes'→CN, 'invoic'→Inv. 'NO DN' → None."""
        n = _norm(name)
        if not n or n == "nodn":
            return None
        for canon, aliases in _CANON_ALIASES.items():
            if n in aliases:
                return canon
        pairs = [(a, c) for c, al in _CANON_ALIASES.items() for a in al]
        m = _difflib.get_close_matches(n, [a for a, _ in pairs], n=1, cutoff=0.82)
        if m:
            return next(c for a, c in pairs if a == m[0])
        return None

    def _is_no_dn_sheet(df: pd.DataFrame, sheetname: str) -> bool:
        """The exclusion list: a 'NO DN' sheet or any sheet with a
        DebitNotefromBuyer flag column."""
        if _norm(sheetname) == "nodn":
            return True
        cols = {_norm(c) for c in df.columns}
        return any("debitnote" in c and "buyer" in c for c in cols)

    # ── Dataset detection for individual files ────────────────────────────────
    def _detect_dataset(df: pd.DataFrame, filename: str, sheetname: str) -> str | None:
        target = _detect_dataset_base(df, filename, sheetname)
        # A standalone Bill file with a historical name → BillHistory dataset.
        # (Skip when the sheet is named exactly 'Bill' — that's the combined MIS
        #  export, whose long filename would otherwise trip the history rule.)
        if target == "Bill" and _canon_sheet(sheetname) is None and _is_history_bill(filename):
            return "BillHistory"
        return target

    def _detect_dataset_base(df: pd.DataFrame, filename: str, sheetname: str) -> str | None:
        """
        Figure out which dataset (Bill / Inv / CN / DN / AP / AR ...) a sheet
        belongs to. Priority: exact sheet name → column signature →
        aging-report keywords → filename keywords.
        """
        # 1. Sheet-name match — case-insensitive + typo-tolerant (Bills→Bill, INV→Inv)
        canon = _canon_sheet(sheetname)
        if canon:
            return canon

        # 2. Column signature — most reliable for standalone exports
        cols = {str(c).strip().lower() for c in df.columns}
        signatures = [
            ("Bill", {"bill status", "bill number"}),
            ("Inv",  {"invoice status", "invoice number"}),
            ("CN",   {"credit note status", "credit note number"}),
            ("DN",   {"vendor credit status", "vendor credit number"}),
            ("AP",   {"age", "vendor_name", "balance"}),
            ("AR",   {"age", "customer_name", "balance"}),
        ]
        for target, sig in signatures:
            if sig.issubset(cols):
                return target

        text = f"{filename} {sheetname}".lower()

        # 3. Aging reports FIRST — their filenames contain "bill"/"invoice"
        #    ("AP Aging Details By Bill Due Date") and would otherwise be
        #    misrouted to Bill/Inv, overwriting real data.
        if "ap aging" in text or "ap ageing" in text:
            return "AP"
        if "ar aging" in text or "ar ageing" in text:
            return "AR"

        # 4. Junk guard — sheets with <3 columns (dropdowns, notes) are never
        #    routed by filename keywords; they'd overwrite a real dataset.
        if len(df.columns) < 3:
            return None

        # 5. Filename / sheet-name keywords
        keyword_map = [
            ("vendor credit", "DN"), ("debit note", "DN"), ("debitnote", "DN"), ("dn", "DN"),
            ("credit note", "CN"), ("creditnote", "CN"), ("cn", "CN"),
            ("bill", "Bill"),
            ("invoice", "Inv"), ("inv", "Inv"),
            ("payable", "AP"), ("ap", "AP"),
            ("receivable", "AR"), ("ar", "AR"),
            ("p&l", "P&L"), ("pnl", "P&L"),
        ]
        for kw, target in keyword_map:
            if kw in text.split() or kw in text:
                return target
        return None

    def _fix_title_header(file_bytes: bytes, sheet: str, df: pd.DataFrame) -> pd.DataFrame:
        """
        Zoho aging exports carry one or more title/total rows above the real header
        (so most columns read as 'Unnamed: N'). Older exports had 1 title row; the
        newer MIS export has 2 (a blank row + a totals row). Instead of assuming a
        fixed offset, FIND the header row: the top row whose cells are mostly text
        labels (headers), not the numeric totals row or blank rows.
        """
        unnamed = sum(1 for c in df.columns if str(c).startswith("Unnamed"))
        if len(df.columns) > 0 and unnamed >= len(df.columns) / 2:
            raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=None, nrows=15)
            best_i, best_score = 0, -1
            for i in range(len(raw)):
                # score = how many cells are non-empty text labels (header-like);
                # the totals row scores low (numbers), blank rows score 0.
                strn = sum(1 for x in raw.iloc[i] if isinstance(x, str) and x.strip())
                if strn > best_score:
                    best_score, best_i = strn, i
            return pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=best_i)
        return df

    def _ingest_sheet(df: pd.DataFrame, dataset: str, filename: str, sheetname: str,
                      results: list, accum: dict):
        """Accumulate the sheet under its dataset (multiple sheets/files combine)."""
        df = df.dropna(how="all")
        if df.empty:
            results.append({"File": filename, "Sheet": sheetname, "Dataset": "—", "Rows": 0, "Status": "⚠ Empty"})
            return
        df = df.copy()
        df["_source_file"] = filename
        accum.setdefault(dataset, []).append(df)
        results.append({"File": filename, "Sheet": sheetname, "Dataset": dataset, "Rows": len(df), "Status": "✅"})

    def _process_excel(file_bytes: bytes, filename: str, results: list, accum: dict):
        """Parse one Excel file's sheets, auto-detect each sheet's dataset, accumulate."""
        try:
            xl = pd.ExcelFile(io.BytesIO(file_bytes))
            low = filename.lower()
            # Does the workbook contain core dataset sheets (Bill/CN/DN/AP/AR/Inv)?
            # The combined MIS export does; a STANDALONE no-DN file does not. Zoho
            # sometimes puts 'NO DN' FIRST in the combined file, so we must NOT let
            # the standalone-file shortcut below swallow the whole workbook — the
            # per-sheet loop handles the NO DN sheet correctly on its own.
            has_core = any(_canon_sheet(s) for s in xl.sheet_names)
            # "CF.DN = No" exclusion list — a STANDALONE file, detected by a
            # DebitNotefromBuyer column or a no-dn filename keyword.
            ex0 = pd.read_excel(io.BytesIO(file_bytes), sheet_name=xl.sheet_names[0], nrows=3)
            ex_cols = {str(c).strip().lower().replace(" ", "") for c in ex0.columns}
            has_dnbuyer = any("debitnote" in c and "buyer" in c for c in ex_cols)
            if not has_core and (has_dnbuyer or any(k in low for k in
                    ["no dn", "no_dn", "cf.dn", "cf dn", "dn no", "dn status", "non dn", "exclude"])):
                ex = pd.read_excel(io.BytesIO(file_bytes), sheet_name=xl.sheet_names[0]).dropna(how="all")
                n = db.save_no_dn_shipments(ex)
                results.append({"File": filename, "Sheet": xl.sheet_names[0], "Dataset": "No-DN exclusion (saved)",
                                "Rows": n, "Status": "✅"})
                return
            # Re-Commerce MANUAL DETAIL file (accurate costs, Profitability-sheet
            # format) — stored in the DB and used AS-IS for Re-Commerce's FY.
            # Two variants by filename: '… WITHOUT SAMSUNG' vs '… WID/WITH SAMSUNG'.
            if "recommerce" in low and ("detail" in low or "reco" in low):
                _with_s = "without" not in low
                _pick = next((s for s in xl.sheet_names
                              if any("shipment id" in str(c).strip().lower()
                                     for c in pd.read_excel(io.BytesIO(file_bytes),
                                                            sheet_name=s, nrows=1).columns)),
                             xl.sheet_names[0])
                rd = pd.read_excel(io.BytesIO(file_bytes), sheet_name=_pick).dropna(how="all")
                n = db.save_recommerce_manual(rd, _with_s)
                results.append({"File": filename, "Sheet": _pick,
                                "Dataset": f"Re-Commerce manual detail ({'WITH' if _with_s else 'WITHOUT'} Samsung)",
                                "Rows": n, "Status": "✅"})
                return
            # Amazon × Recykal file — grab the 'YTD Sales' sheet (header on row 4)
            if "YTD Sales" in xl.sheet_names or "amazon" in low or "recykal" in low:
                if "YTD Sales" in xl.sheet_names:
                    ytd = pd.read_excel(io.BytesIO(file_bytes), sheet_name="YTD Sales", header=3).dropna(how="all")
                    accum.setdefault("AmazonYTD", []).append(ytd)
                    results.append({"File": filename, "Sheet": "YTD Sales", "Dataset": "AmazonYTD",
                                    "Rows": len(ytd), "Status": "✅"})
                    return
            # Only these are ever ingested — any other sheet (P&L, Account
            # Transactions, dropdowns, …) is ignored even if present in the file.
            ALLOWED_INGEST = {"Bill", "CN", "DN", "AP", "AR", "Inv", "BillHistory"}
            for sheet in xl.sheet_names:
                df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet)
                df = _fix_title_header(file_bytes, sheet, df)
                # NO-DN sheet → REPLACE the permanent exclusion list, then skip it
                if _is_no_dn_sheet(df, sheet):
                    n = db.save_no_dn_shipments(df.dropna(how="all"))
                    results.append({"File": filename, "Sheet": sheet,
                                    "Dataset": "No-DN exclusion (replaced)", "Rows": n, "Status": "✅"})
                    continue
                dataset = _detect_dataset(df, filename, sheet)
                if dataset not in ALLOWED_INGEST:
                    why = ("not one of Bill/CN/DN/AP/AR/Inv — ignored"
                           if dataset else "not recognised as a dataset")
                    results.append({"File": filename, "Sheet": sheet, "Dataset": "—",
                                    "Rows": 0, "Status": f"⏭ Skipped — {why}"})
                    continue
                _ingest_sheet(df, dataset, filename, sheet, results, accum)
        except Exception as e:
            results.append({"File": filename, "Sheet": "—", "Dataset": "—", "Rows": 0, "Status": f"❌ {e}"})

    st.markdown(
        "Upload the Zoho exports as **individual Excel files** (multiple allowed) or a single **ZIP** "
        "containing them. Each file/sheet is auto-detected and routed to the right dataset — "
        "**Bill, Invoice, CN, DN, AP, AR** — by its columns, sheet name, or filename."
    )

    # ── Permanent older-bills store status ────────────────────────────────────
    _ob_count = db.older_bills_count()
    with st.expander(f"🗄️ Permanent older-bills store — {_ob_count:,} rows"
                     + ("" if _ob_count else " (empty)"), expanded=False):
        st.caption(
            "Older bills (e.g. Apr-25 → Mar-26) are merged and saved here permanently. "
            "They survive across sessions, so you only upload them once — any future MIS "
            "upload with missing bills automatically pulls costs from this store. "
            "Uploading more older-bill files adds to it (duplicates removed)."
        )
        if _ob_count:
            ob = db.load_older_bills()
            rc = ob["Account"].astype(str).str.contains("Re-Commerce", case=False, na=False).sum() if "Account" in ob.columns else 0
            st.write(f"Total rows: **{_ob_count:,}** · Re-Commerce lines: **{rc:,}**")
            if st.button("🗑️ Clear permanent older-bills store", key="clear_ob"):
                db.clear_older_bills()
                st.success("Older-bills store cleared.")
                st.rerun()

    _ytd_count = db.amazon_ytd_count()
    with st.expander(f"🟠 Amazon × Recykal YTD store — {_ytd_count:,} rows"
                     + ("" if _ytd_count else " (empty)"), expanded=False):
        st.caption(
            "The Amazon × Recykal 'YTD Sales' sheet links each Recykal invoice "
            "(Invoice ID) to its Amazon invoice numbers (Invoice no.). Used to pin the "
            "EXACT older-bill line for a missing-bill item: invoice → Amazon invoice no. "
            "→ older bills (Bill Number + material). Upload once; persists across sessions."
        )
        if _ytd_count and st.button("🗑️ Clear Amazon×Recykal store", key="clear_ytd"):
            db.clear_amazon_ytd()
            st.success("Amazon×Recykal store cleared.")
            st.rerun()

    _pd_count = db.profit_details_count()
    with st.expander(f"📚 Accumulated profitability details — {_pd_count:,} line rows"
                     + ("" if _pd_count else " (empty)"), expanded=False):
        st.caption(
            "Every MIS upload's computed line rows are stored here permanently, "
            "upserted by Shipment + Invoice — so months that drop out of Zoho's "
            "rolling export stay in the Details sheet, and late CN/DN "
            "updates replace a shipment's old rows with the newest state."
        )
        if _pd_count and st.button("🗑️ Clear accumulated details", key="clear_pdet"):
            db.clear_profit_details()
            st.success("Accumulated details cleared.")
            st.rerun()

    _rw_n, _ro_n = db.recommerce_manual_count(True), db.recommerce_manual_count(False)
    with st.expander(f"🛒 Re-Commerce manual detail — WITH Samsung: {_rw_n:,} · "
                     f"WITHOUT Samsung: {_ro_n:,} rows"
                     + ("" if (_rw_n or _ro_n) else " (empty)"), expanded=False):
        st.caption(
            "Re-Commerce's accurate costs come from a manually-maintained detail sheet "
            "(Profitability-Report format). Rows up to its cutoff date are used AS-IS "
            "(no Amazon×Recykal re-costing); later transactions fall back to the live "
            "Amazon×Recykal logic. Two versions — WITH and WITHOUT Samsung — each drive a "
            "separate full report. Upload a file whose name contains 'Recommerce Details' "
            "(add 'without samsung' for that version)."
        )
        if (_rw_n or _ro_n) and st.button("🗑️ Clear Re-Commerce manual detail", key="clear_reco"):
            db.clear_recommerce_manual()
            st.success("Re-Commerce manual detail cleared.")
            st.rerun()

    _nodn_count = db.no_dn_count()
    with st.expander(f"🚫 'CF.DN = No' shipment exclusion list — {_nodn_count:,} shipments"
                     + ("" if _nodn_count else " (empty)"), expanded=False):
        st.caption(
            "Shipments listed here (CF.DN = No/false) are **excluded** from the ReWerse "
            "2.5% CN/DN provision. Provision applies to ReWerse shipments NOT in this list. "
            "Upload a file whose name contains 'no dn' / 'cf.dn' with a Shipment ID column. "
            "Until uploaded, the list is empty so the provision applies to all ReWerse shipments."
        )
        if _nodn_count and st.button("🗑️ Clear exclusion list", key="clear_nodn"):
            db.clear_no_dn_shipments()
            st.success("Exclusion list cleared.")
            st.rerun()

    uploaded_files = st.file_uploader(
        "Drop Excel files or a ZIP here",
        type=["xlsx", "xls", "zip"],
        accept_multiple_files=True,
    )

    results = []
    if uploaded_files:
        import zipfile
        accum: dict = {}
        with st.spinner(f"Processing {len(uploaded_files)} upload(s)..."):
            for uploaded in uploaded_files:
                file_bytes = uploaded.read()
                if uploaded.name.lower().endswith(".zip"):
                    try:
                        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                            excel_members = [m for m in zf.namelist()
                                             if m.lower().endswith((".xlsx", ".xls"))
                                             and not m.startswith("__MACOSX")]
                            if not excel_members:
                                results.append({"File": uploaded.name, "Sheet": "—", "Dataset": "—",
                                                "Rows": 0, "Status": "❌ No Excel files inside ZIP"})
                            for member in excel_members:
                                _process_excel(zf.read(member), member.split("/")[-1], results, accum)
                    except Exception as e:
                        results.append({"File": uploaded.name, "Sheet": "—", "Dataset": "—", "Rows": 0, "Status": f"❌ {e}"})
                else:
                    _process_excel(file_bytes, uploaded.name, results, accum)

            # Write each dataset ONCE — combining all its sheets/files (e.g. the
            # older-bills file's two bill sheets are concatenated, not overwritten).
            for dataset, frames in accum.items():
                combined = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
                if dataset == "BillHistory":
                    # Persist to the permanent on-disk older-bills store (accumulates
                    # across uploads, de-duped) — survives sessions so the user need
                    # not re-upload it every time.
                    total = db.save_older_bills(combined)
                    results.append({"File": "→ permanent older-bills store", "Sheet": "merged",
                                    "Dataset": "BillHistory (saved)", "Rows": total, "Status": "✅"})
                elif dataset == "AmazonYTD":
                    total = db.save_amazon_ytd(combined)
                    results.append({"File": "→ permanent Amazon×Recykal store", "Sheet": "YTD Sales",
                                    "Dataset": "AmazonYTD (saved)", "Rows": total, "Status": "✅"})
                else:
                    db.write_sheet(combined, dataset, table="raw")
            # Reset any stale derived tables so the pipeline recomputes cleanly
            for tbl in ("cleaned", "bill_purchases", "bill_logistics"):
                for sh in ("Inv", "Bill", "CN", "DN"):
                    db.session_drop(sh, tbl)
            db.session_drop("Merged", "profitability")
            db.session_drop("Merged", "inv_bill_cn_dn")
            db.session_drop("Merged", "price_book")

    if results:
        ok = sum(1 for r in results if r["Status"] == "✅")
        st.success(f"Loaded {ok} dataset(s) successfully")
        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

        loaded_now = {r["Dataset"] for r in results if r["Status"] == "✅"}
        needed = {"Bill", "Inv", "CN", "DN"}
        missing = needed - loaded_now - {s for s, v in db.all_db_status().items() if v["exists"]}
        if missing:
            st.warning(f"Still missing for profitability: {', '.join(sorted(missing))}")
        else:
            st.info("All 4 core datasets present — go to **Summary Report** for the profitability report.")
    else:
        st.markdown("### Expected datasets")
        cols = st.columns(3)
        for i, sheet in enumerate(["Bill", "Inv", "CN", "DN", "AP", "AR"]):
            with cols[i % 3]:
                st.info(f"**{sheet}** — auto-detected by columns, or name the file `{sheet.lower()}.xlsx`")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2: View Databases
# ══════════════════════════════════════════════════════════════════════════════
elif page == "View Databases":
    st.title("View Databases")
    status = db.all_db_status()
    loaded = {s: v for s, v in status.items() if v["exists"]}

    if not loaded:
        st.info("No data yet. Upload a file on the **Upload Files** page.")
    else:
        cols = st.columns(4)
        for i, (sheet, v) in enumerate(loaded.items()):
            with cols[i % 4]:
                total = sum(v["tables"].values())
                st.metric(sheet, f"{total:,} rows", v["db_file"])

        st.markdown("---")
        sheet_sel = st.selectbox("Sheet / DB", list(loaded.keys()))
        if sheet_sel:
            tables = db.list_tables(sheet_sel)
            tbl_sel = st.selectbox("Table", tables)
            n = st.slider("Rows", 10, 500, 50, step=10)
            if tbl_sel:
                df = db.read_table(sheet_sel, tbl_sel).drop(columns=["_source_file"], errors="ignore")
                st.dataframe(df.head(n), use_container_width=True, hide_index=True)
                st.download_button(
                    f"Download {sheet_sel}_{tbl_sel}.csv",
                    df.to_csv(index=False).encode(),
                    file_name=f"{sheet_sel}_{tbl_sel}.csv",
                    mime="text/csv",
                )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3: Cleaning
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Cleaning":
    st.title("Data Cleaning")

    tab_bill, tab_inv, tab_cn, tab_dn = st.tabs(["📄 Bill", "🧾 Invoice", "📝 Credit Notes (CN)", "📋 Vendor Credits (DN)"])

    # ── helper to render a cleaning section ──────────────────────────────────
    def render_cleaning(sheet: str, clean_fn, rules_md: str, rule_cols: dict):
        raw_df = db.read_table(sheet, "raw").drop(columns=["_source_file"], errors="ignore")
        if raw_df.empty:
            st.warning(f"No {sheet} data found. Please upload the Excel file first.")
            return

        st.metric("Raw rows", len(raw_df))

        with st.expander("Raw data preview", expanded=False):
            st.dataframe(raw_df.head(30), use_container_width=True, hide_index=True)

        st.markdown("#### Cleaning Rules")
        st.markdown(rules_md)

        # Show value counts for key columns
        vcols = st.columns(len(rule_cols))
        for i, (col_label, col_candidates) in enumerate(rule_cols.items()):
            actual = cleaning._col(raw_df, *col_candidates)
            with vcols[i]:
                st.markdown(f"**{col_label}**")
                if actual:
                    vc = raw_df[actual].value_counts(dropna=False).rename("Count").reset_index()
                    vc.columns = [actual, "Count"]
                    st.dataframe(vc, use_container_width=True, hide_index=True)
                else:
                    st.caption("Column not found in data")

        st.markdown("---")

        # Preview stats before running
        preview_df, preview_stats = clean_fn(raw_df.copy())
        dropped = preview_stats["original_rows"] - preview_stats["final_rows"]
        st.info(
            f"Cleaning will reduce **{preview_stats['original_rows']:,} → "
            f"{preview_stats['final_rows']:,} rows** (drop {dropped:,} rows)."
        )

        if st.button(f"▶ Run Cleaning — {sheet}", type="primary", key=f"run_{sheet}"):
            cleaned_df, stats = clean_fn(raw_df.copy())
            db.write_cleaned(cleaned_df, sheet)
            st.success(f"Saved to `{db.SHEET_DB_MAP.get(sheet, sheet)}.db` → table `cleaned`")

            # Stats row
            stat_items = {k: v for k, v in stats.items() if k not in ("original_rows", "final_rows", "accounts_kept")}
            scols = st.columns(len(stat_items) + 2)
            scols[0].metric("Original", stats["original_rows"])
            for i, (k, v) in enumerate(stat_items.items()):
                label = k.replace("dropped_", "Dropped — ").replace("_", " ").title()
                scols[i + 1].metric(label, v if isinstance(v, str) else f"-{v}")
            scols[-1].metric("Final rows", stats["final_rows"])

            st.subheader("Cleaned Data")
            st.dataframe(cleaned_df, use_container_width=True, hide_index=True)
            st.download_button(
                f"Download cleaned_{sheet.lower()}.csv",
                cleaned_df.to_csv(index=False).encode(),
                file_name=f"cleaned_{sheet.lower()}.csv",
                mime="text/csv",
            )

    # ── Bill ──────────────────────────────────────────────────────────────────
    with tab_bill:
        render_cleaning(
            sheet="Bill",
            clean_fn=cleaning.clean_bill,
            rules_md=(
                "| # | Column | Rule |\n"
                "|---|--------|------|\n"
                "| 1 | Account | Keep rows containing `Marketplace Purchases` or `Marketplace Logistics` |\n"
                "| 2 | Bill Status | Remove `Void` and `Draft` |\n"
                "| — | Branch Name | No filter — all branches kept |"
            ),
            rule_cols={
                "Account": ["Account"],
                "Bill Status": ["Bill_Status", "Bill Status"],
            },
        )

        st.markdown("---")
        st.subheader("Split Cleaned Bill by Account")
        st.markdown(
            "Splits the cleaned Bill table into two sub-tables stored in `bill.db`:\n"
            "- `bill_purchases` — Marketplace Purchases rows\n"
            "- `bill_logistics` — Marketplace Logistics rows"
        )

        cleaned_bill = db.read_table("Bill", "cleaned").drop(columns=["_source_file"], errors="ignore")
        if cleaned_bill.empty:
            st.warning("Run Bill cleaning first to generate the cleaned table.")
        else:
            # Preview split counts
            purchases_prev = cleaned_bill[cleaned_bill["Account"].str.contains("Marketplace Purchases", case=False, na=False)]
            logistics_prev = cleaned_bill[cleaned_bill["Account"].str.contains("Marketplace Logistics", case=False, na=False)]
            c1, c2 = st.columns(2)
            c1.metric("Marketplace Purchases rows", len(purchases_prev))
            c2.metric("Marketplace Logistics rows", len(logistics_prev))

            if st.button("▶ Split Bill", type="primary", key="split_bill"):
                purchases_df, logistics_df, stats = cleaning.split_bill(cleaned_bill)
                db.write_table(purchases_df, "Bill", "bill_purchases")
                db.write_table(logistics_df, "Bill", "bill_logistics")
                st.success("Saved `bill_purchases` and `bill_logistics` to `bill.db`")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Marketplace Purchases**")
                    st.dataframe(purchases_df, use_container_width=True, hide_index=True)
                    st.download_button("Download bill_purchases.csv",
                                       purchases_df.to_csv(index=False).encode(),
                                       file_name="bill_purchases.csv", mime="text/csv")
                with col2:
                    st.markdown("**Marketplace Logistics**")
                    if logistics_df.empty:
                        st.info("No Marketplace Logistics rows in current data.")
                    else:
                        st.dataframe(logistics_df, use_container_width=True, hide_index=True)
                        st.download_button("Download bill_logistics.csv",
                                           logistics_df.to_csv(index=False).encode(),
                                           file_name="bill_logistics.csv", mime="text/csv")

    # ── Invoice ───────────────────────────────────────────────────────────────
    with tab_inv:
        render_cleaning(
            sheet="Inv",
            clean_fn=cleaning.clean_invoice,
            rules_md=(
                "| # | Column | Rule |\n"
                "|---|--------|------|\n"
                "| 1 | Account | Keep rows containing `Marketplace Sales` or `Marketplace Logistics` |\n"
                "| 2 | Invoice Status | Remove `Void` and `Draft` |\n"
                "| — | Branch Name | No filter — all branches kept |"
            ),
            rule_cols={
                "Account": ["Account"],
                "Invoice Status": ["Invoice_Status", "Invoice Status"],
            },
        )

    # ── CN ────────────────────────────────────────────────────────────────────
    with tab_cn:
        render_cleaning(
            sheet="CN",
            clean_fn=cleaning.clean_cn,
            rules_md=(
                "| # | Column | Rule |\n"
                "|---|--------|------|\n"
                "| 1 | Credit Note Status | Remove `Void` and `Pending` |"
            ),
            rule_cols={
                "Credit Note Status": ["Credit_Note_Status", "Credit Note Status"],
            },
        )

    # ── DN ────────────────────────────────────────────────────────────────────
    with tab_dn:
        render_cleaning(
            sheet="DN",
            clean_fn=cleaning.clean_dn,
            rules_md=(
                "| # | Column | Rule |\n"
                "|---|--------|------|\n"
                "| 1 | Vendor Credit Status | Remove `Void` and `Pending` |"
            ),
            rule_cols={
                "Vendor Credit Status": ["Vendor_Credit_Status", "Vendor Credit Status"],
            },
        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4: Merge
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Merge & Compute":
    st.title("Merge & Profitability Compute")

    # ── Auto-run full pipeline (clean → split → merge → compute) ────────────
    with st.spinner("Preparing data..."):
        _auto_pipeline()

    # ── Load all cleaned tables ────────────────────────────────────────────────
    inv_df      = db.read_table("Inv",  "cleaned").drop(columns=["_source_file"], errors="ignore")
    bill_pur_df = db.read_table("Bill", "bill_purchases").drop(columns=["_source_file"], errors="ignore")
    bill_log_df = db.read_table("Bill", "bill_logistics").drop(columns=["_source_file"], errors="ignore")
    cn_df       = db.read_table("CN",   "cleaned").drop(columns=["_source_file"], errors="ignore")
    dn_df       = db.read_table("DN",   "cleaned").drop(columns=["_source_file"], errors="ignore")

    # ── Status check ──────────────────────────────────────────────────────────
    missing = [name for name, df in [("Invoice",inv_df),("Bill",bill_pur_df),("CN",cn_df),("DN",dn_df)] if df.empty]
    if missing:
        st.warning(f"No raw data found for: {', '.join(missing)}. Please upload a file first.")
    else:
        # ── Merge info (informational, no button) ─────────────────────────────
        st.markdown("### How the data is merged")
        st.markdown("""
| Step | Left table | Right table | Join key | Type |
|------|-----------|-------------|----------|------|
| 1 | Invoice (cleaned) | Bill Purchases | `CFSO_Number` + `Item_Name` | Left join |
| 2 | Step 1 result | CN (pivoted wide, max 2) | `CFSO_Number` = `Referenceno` | Left join |
| 3 | Step 2 result | DN (pivoted wide, max 2) | `CFSO_Number` = `Referenceno` | Left join |
| 4 | Step 3 result | Formula engine (compute.py) | — | Calculated columns |
        """)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Invoice rows", len(inv_df))
        c2.metric("Bill (purchases)", len(bill_pur_df))
        c3.metric("Bill (logistics)", len(bill_log_df))
        c4.metric("CN rows", len(cn_df))
        c5.metric("DN rows", len(dn_df))

        with st.expander("CN / DN distribution per shipment"):
            ea, eb = st.columns(2)
            with ea:
                st.caption("Credit Notes per Shipment")
                cn_cnt = cn_df.groupby("Referenceno").size().value_counts().sort_index().reset_index()
                cn_cnt.columns = ["CN count", "Shipments"]
                st.dataframe(cn_cnt, use_container_width=True, hide_index=True)
                capped = int((cn_df.groupby("Referenceno").size() >= 3).sum())
                if capped: st.warning(f"{capped} shipment(s) have 3+ CNs — only first 2 kept.")
            with eb:
                st.caption("Vendor Credits per Shipment")
                dn_cnt = dn_df.groupby("Referenceno").size().value_counts().sort_index().reset_index()
                dn_cnt.columns = ["DN count", "Shipments"]
                st.dataframe(dn_cnt, use_container_width=True, hide_index=True)
                capped = int((dn_df.groupby("Referenceno").size() >= 3).sum())
                if capped: st.warning(f"{capped} shipment(s) have 3+ DNs — only first 2 kept.")

        st.markdown("---")
        st.markdown("### Run Pipeline")

        with st.spinner("Merging all 4 sheets and computing profitability columns..."):
            # Older-bills store (exact shipment match) + Amazon×Recykal chain
            hist_df = db.load_older_bills()
            ytd_df = db.load_amazon_ytd()
            amazon_map = cleaning.build_amazon_invoice_map(ytd_df) if not ytd_df.empty else {}
            merged_raw, pipe_stats = cleaning.run_full_pipeline(
                inv_df, bill_pur_df, bill_log_df if not bill_log_df.empty else None,
                cn_df, dn_df,
                history_df=hist_df if not hist_df.empty else None,
                amazon_map=amazon_map
            )
            db.write_table(merged_raw, "Merged", "inv_bill_cn_dn")

            # Build exact-named report (for display + download)
            profit_df = compute.build_profitability(
                merged_raw,
                logistics_df=bill_log_df if not bill_log_df.empty else None,
                no_dn_shipments=db.load_no_dn_shipments()
                | cleaning.void_dn_shipments(
                    db.read_table("DN", "raw").drop(columns=["_source_file"], errors="ignore"))
            )
            # Write to DB (auto-deduplicates col names for SQLite)
            db.write_table(profit_df, "Merged", "profitability")

        st.success(f"Pipeline complete — {len(profit_df):,} rows · {len(profit_df.columns)} columns saved to `merged.db → profitability`")

        # ── Missing-bill cost fill notice ─────────────────────────────────────
        hist_filled = pipe_stats.get("hist_filled", 0)
        orphan_bills = pipe_stats.get("orphan_bills", 0)
        if hist_filled or orphan_bills:
            st.info(
                f"**Missing-bill costing** — {hist_filled} Re-Commerce row(s) costed from the "
                f"Amazon × Recykal invoice chain / exact older-bill shipment match. "
                f"{orphan_bills} extra bill(s) (other verticals) appended at the bottom with "
                f"blank invoice columns. See the **Cost Source** column."
            )

        # ── Key metrics ───────────────────────────────────────────────────────
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total rows", f"{len(profit_df):,}")
        m2.metric("Matched (bill found)", pipe_stats.get("matched_rows","—"))
        m3.metric("Unmatched invoices", pipe_stats.get("unmatched_rows","—"))
        # 'Margin' col 66 (index 65) = BO = profitability margin
        margin_col = profit_df.iloc[:, 65]
        m4.metric("Total Margin", f"₹{margin_col.sum():,.0f}")

        # ── Section previews ──────────────────────────────────────────────────
        # Use iloc-based column selection to handle duplicate names safely
        col_list = list(profit_df.columns)
        def _idx(*names):
            """Return list of positional indices for given column names (first match each)."""
            result = []
            used = set()
            for name in names:
                for i, c in enumerate(col_list):
                    if c == name and i not in used:
                        result.append(i)
                        used.add(i)
                        break
            return result

        sections = {
            "Raw Data + Purchase":  _idx("Shipment ID","Quarter","Month","Date","Supplier Name","Material","Qty (Kg)","Price/Kg","Purchase Price","Return Qty","Net Qty","Basic Customs Duty"),
            "Logistics":            _idx("Shipment ID","Transporter Name","Logistics cost","Logistics Provision","Total Logistics Cost","Cost/Kg."),
            "Debit Notes (DN)":     _idx("Shipment ID","Debit Note No.","Debit Note Date.","Debit Note No. 2","Debit Note Date. 2","Actual Debit Note","Provision for DN","Total Cost"),
            "Sales + Credit Notes": _idx("Shipment ID","Inv. No.","Buyer Name","Qty(Kg)","Amount","Credit Note No:1","CN Date. No:1","Credit Note No:2","CN Date. No:2","Actual Credit Note"),
            "Profitability":        _idx("Shipment ID","Amount","Actual Credit Note","Net Revenue","Total Cost","Margin","Margin (%)","Margin Bucket","Reamrks - Margin","LMI @ Inception"),
            "Financials with GST":  _idx("Shipment ID","Sales ","Purchases","Credit Note","Debit Note","Margin","Bill Branch","Inv Branch"),
        }

        tab_names = list(sections.keys())
        tabs = st.tabs(tab_names)
        for tab, (sec, idxs) in zip(tabs, sections.items()):
            with tab:
                st.dataframe(profit_df.iloc[:50, idxs], use_container_width=True, hide_index=True)

        st.markdown("---")
        st.download_button(
            "⬇ Download Full Profitability Report (CSV)",
            profit_df.to_csv(index=False).encode(),
            file_name="profitability_report.csv",
            mime="text/csv",
        )

        # ── Category-wise Profitability Reports ──────────────────────────────
        st.markdown("---")
        st.markdown("### Category-wise Profitability Reports")
        st.markdown(
            "One report per **Broad Category**. Institutional Business is split into "
            "**Enterprise** (Shipment ID starts with `SHID`) and **Processing Center** (the rest)."
        )

        cat_dfs = reports.split_by_category(profit_df)
        if not cat_dfs:
            st.info("No categories found in the data.")
        else:
            # Summary of categories
            cat_summary = pd.DataFrame([
                {"Report": name,
                 "Rows": len(df),
                 "Total Margin": round(float(df.iloc[:, 65].sum()), 2)}
                for name, df in cat_dfs.items()
            ])
            st.dataframe(cat_summary, use_container_width=True, hide_index=True)

            def _display_safe(df):
                """Dedupe column names for st.dataframe (Arrow can't render duplicates)."""
                seen, new_cols = {}, []
                for c in df.columns:
                    if c in seen:
                        seen[c] += 1
                        new_cols.append(f"{c} ({seen[c]})")
                    else:
                        seen[c] = 1
                        new_cols.append(c)
                out = df.copy()
                out.columns = new_cols
                return out

            cat_tabs = st.tabs(list(cat_dfs.keys()))
            for tab, (name, cdf) in zip(cat_tabs, cat_dfs.items()):
                with tab:
                    st.caption(f"{len(cdf):,} rows · Margin ₹{cdf.iloc[:, 65].sum():,.0f}")
                    st.dataframe(_display_safe(cdf.head(50)), use_container_width=True, hide_index=True)
                    safe = name.replace("(", "_").replace(")", "").replace("/", "-")
                    st.download_button(
                        f"⬇ Download {name} (CSV)",
                        cdf.to_csv(index=False).encode(),
                        file_name=f"profitability_{safe}.csv",
                        mime="text/csv",
                        key=f"dl_cat_{name}",
                    )

            st.download_button(
                "⬇ Download ALL Category Reports (Excel — one sheet per category)",
                reports.category_reports_excel(cat_dfs),
                file_name="profitability_by_category.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5: Summary Report
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Summary Report":
    st.title("📋 Management Summary Report")

    with st.spinner("Preparing data..."):
        _auto_pipeline()

    profit_df = db.read_table("Merged", "profitability")
    if "_source_file" in profit_df.columns:
        profit_df = profit_df.drop(columns=["_source_file"])

    if profit_df.empty:
        st.warning("No data found. Please upload files on the **Upload Files** page first.")
    else:
        st.markdown(
            "Monthly summary per **Broad Category** — Quantity & Sales from the buyer "
            "(invoice) side. `Net Margin = Gross Margin − Transportation Charges − Operational Cost`."
        )

        ar_df = db.read_table("AR", "raw").drop(columns=["_source_file"], errors="ignore")
        ap_df = db.read_table("AP", "raw").drop(columns=["_source_file"], errors="ignore")
        # Operational-cost bills: the CURRENT MIS's cleaned Bill table (holds this
        # period's AFR service charges — blank-CFSO Manpower/Transport/etc.), with
        # the older-bills store as fallback. Drives the AFR Operational Cost row.
        _cur_bills = db.read_table("Bill", "cleaned").drop(columns=["_source_file"], errors="ignore")
        op_bills = _cur_bills if not _cur_bills.empty else db.load_older_bills()
        _ar = ar_df if not ar_df.empty else None
        _ap = ap_df if not ap_df.empty else None
        _obills = op_bills if not op_bills.empty else None

        # ── Re-Commerce: FIXED signed-off detail up to the cutover (17-07-2026);
        # everything AFTER it is built LIVE from the Amazon × Recykal Google
        # Sheet (cost & revenue from there, shipment id from the Zoho invoice).
        # Runs BEFORE the Reco gate/summary so every downstream view sees it.
        _rc_fixed = db.load_recommerce_manual(True)
        if not _rc_fixed.empty:
            import amazon_live as _amz

            @st.cache_data(ttl=180, show_spinner=False)
            def _fetch_amazon_stock():
                return _amz.fetch_stock()      # live Google Sheet, cached ~3 min

            _stock, _amz_status = _fetch_amazon_stock()
            _zinv = db.read_table("Inv", "cleaned").drop(columns=["_source_file"], errors="ignore")
            if _zinv.empty:
                _zinv = db.read_table("Inv", "raw").drop(columns=["_source_file"], errors="ignore")
            st.session_state["_amz_status"] = _amz_status
            profit_df = reports.apply_recommerce_manual(
                profit_df, _rc_fixed, exclude_samsung_new=False,
                stock_df=_stock if not _stock.empty else None,
                zoho_inv_df=_zinv if not _zinv.empty else None,
                cutoff_date=cleaning.RECOMMERCE_AMAZON_ONLY_AFTER)

        import frozen as _frozen
        _app_dir = str(db.DB_DIR.parent)              # the AUTOMATION folder
        _pdates = reports.parse_dates(profit_df.iloc[:, 2])
        _open_m = _pdates.max().strftime("%b-%y") if _pdates.notna().any() else None

        # ── Reco Items — manual review, ALL verticals (gate the summary until saved) ──
        # Shipments (any vertical) with a missing bill are candidates for exclusion.
        # The user ticks the ones to KEEP in Reco Items (excluded from calcs);
        # unticked ones flow into the Details & summary. The box is always shown.
        _cand = reports.reco_candidates(profit_df)
        _sig = tuple(sorted(_cand["Shipment ID"].tolist())) if len(_cand) else ()

        def _render_reco_review(suffix=""):
            st.markdown("### 🧾 Reco Items — manual review (all verticals)")
            if not len(_cand):
                st.info("No missing-bill shipments detected in the current data — "
                        "every shipment has a matched cost source. Nothing to review.")
                return
            st.caption("Tick a shipment to **keep it in Reco Items** (excluded from the "
                       "Details & summary). Unticked shipments are **included** in the "
                       "calculations. Click **Save** to (re)compute the summary.")
            _verts = sorted(_cand["Vertical"].unique())
            _pick = st.multiselect("Filter by vertical", _verts, default=_verts,
                                   key=f"reco_vert_filter{suffix}")
            _prev = st.session_state.get("reco_selected", set())
            _ed = _cand[_cand["Vertical"].isin(_pick)].copy()
            _ed["Reco? (exclude)"] = _ed["Shipment ID"].isin(_prev)
            _res = st.data_editor(
                _ed, hide_index=True, use_container_width=True, key=f"reco_editor{suffix}",
                disabled=["Vertical", "Shipment ID", "Date", "Buyer Name", "Material", "Amount"])
            if st.button("💾 Save & compute summary", key=f"reco_save{suffix}"):
                # Keep prior ticks for shipments hidden by the vertical filter;
                # update only the rows shown in the editor.
                _shown = set(_res["Shipment ID"].astype(str))
                _picked = set(_res.loc[_res["Reco? (exclude)"], "Shipment ID"].astype(str))
                st.session_state["reco_selected"] = (_prev - _shown) | _picked
                st.session_state["reco_sig"] = _sig
                st.rerun()

        _reco_ready = (len(_cand) == 0) or (st.session_state.get("reco_sig") == _sig)
        if not _reco_ready:
            st.warning(f"{len(_cand)} shipment(s) have a missing bill — review below, "
                       "then **Save** to compute the summary.")
            _render_reco_review()
            st.stop()
        reco_ships = st.session_state.get("reco_selected", set()) if len(_cand) else set()

        # ── ENTERPRISE manual inputs (after Reco review) ────────────────────
        # 1) Custom Duty bills: shipments with NO bill/invoice side in Zoho,
        #    entered as manual purchases into a chosen month. Enterprise ONLY.
        # 2) Operational Cost per month: user override for the Enterprise
        #    summary row. Both persist until edited again.
        # durability: with [github] secrets the saves auto-commit to the repo, so
        # entries survive hosted restarts/redeploys (the container disk is wiped).
        _gh_on = False
        try:
            _gh_on = bool(st.secrets.get("github", {}).get("token"))
        except Exception:
            pass
        _durability_note = (
            "🔒 Saves auto-commit to GitHub — entries **survive app restarts and redeploys**."
            if _gh_on else
            "⚠ Hosted durability: add `[github]` secrets (`token`, `repo`) so saved entries "
            "survive app restarts/redeploys — without them they live only on this "
            "container's disk and reset when the app reboots.")

        def _save_feedback(n: int, what: str) -> str:
            """Build the post-save message: stored count + any REJECTED rows +
            whether the values are durably synced to GitHub."""
            msg = f"Stored {n} {what}."
            if db.LAST_SAVE_DROPPED:
                msg += (" ⚠ REJECTED: " + "; ".join(db.LAST_SAVE_DROPPED)
                        + " — the month must be a real month (any format works: Jul-26, July 2026, 07-26…).")
            if db.LAST_SYNC_OK is True:
                msg += " 🔒 Synced to GitHub — survives restarts."
            elif db.LAST_SYNC_OK is False:
                msg += (" ⚠ GitHub sync FAILED — saved on this server only (resets on "
                        "restart). Reason: " + (db.LAST_SYNC_ERR or "unknown")
                        + ". Common fixes: the token needs Contents: Read-and-write on "
                        "himanshipal-glitch/Automation; repo must be exactly "
                        "'himanshipal-glitch/Automation'.")
            return msg

        _cd_store = db.load_custom_duty()
        with st.expander(f"🛃 Enterprise — Custom Duty bills ({len(_cd_store)} stored)"):
            st.caption("Custom-duty line items — **no bill/invoice in Zoho and no Shipment "
                       "ID**, added manually as purchases (they also count in the FY-Total "
                       "Purchases). Each row lands in the Enterprise profitability in the "
                       "selected month and **stays stored** until edited here. "
                       "Month format: `Jul-26`.")
            st.caption(_durability_note)
            _cd_seed = _cd_store if not _cd_store.empty else pd.DataFrame(
                {"Month (mmm-yy)": pd.Series(dtype="str"),
                 "Supplier Name": pd.Series(dtype="str"),
                 "Amount": pd.Series(dtype="float")})
            _cd_res = st.data_editor(_cd_seed, num_rows="dynamic",
                                     use_container_width=True, key="cd_editor")
            _m0 = st.session_state.pop("cd_save_msg", None)
            if _m0:
                (st.warning if "⚠" in _m0 else st.success)(_m0)
            if st.button("💾 Save Custom Duty bills", key="cd_save"):
                _n = db.save_custom_duty(_cd_res)
                st.session_state["cd_save_msg"] = _save_feedback(_n, "Custom Duty bill(s)")
                st.rerun()
        if not _cd_store.empty:
            profit_df = reports.inject_custom_duty(profit_df, _cd_store)

        _ent_oc = db.load_enterprise_opcost()
        with st.expander(f"⚙️ Enterprise — Operational Cost overrides ({len(_ent_oc)} month(s) stored)"):
            st.caption("Set the Enterprise **Operational Cost** for any month — the summary "
                       "row (and Net Margin) uses your value, overriding the computed/frozen "
                       "figure, and **stays stored** until you change it. Month format: `Jul-26`.")
            st.caption(_durability_note)
            _oc_seed = (pd.DataFrame({"Month (mmm-yy)": list(_ent_oc.keys()),
                                      "Operational Cost": list(_ent_oc.values())})
                        if _ent_oc else
                        pd.DataFrame({"Month (mmm-yy)": pd.Series(dtype="str"),
                                      "Operational Cost": pd.Series(dtype="float")}))
            _oc_res = st.data_editor(_oc_seed, num_rows="dynamic",
                                     use_container_width=True, key="ent_oc_editor")
            _m1 = st.session_state.pop("oc_save_msg", None)
            if _m1:
                (st.warning if "⚠" in _m1 else st.success)(_m1)
            if st.button("💾 Save Operational Cost", key="ent_oc_save"):
                _n = db.save_enterprise_opcost(_oc_res)
                st.session_state["oc_save_msg"] = _save_feedback(_n, "operational-cost month(s)")
                st.rerun()

        def _apply_ent_opcost(_s):
            """Overwrite the Enterprise Operational Cost row with the stored user
            values, re-derive Net Margin / NM% for those months, and re-sum FY."""
            _df = _s.get("Enterprise")
            if _df is None or not _ent_oc:
                return _s
            def g(i, c):
                return float(pd.to_numeric(pd.Series([_df.iat[i, c]]), errors="coerce").fillna(0).iloc[0])
            _mcols = [c for c in _df.columns if c not in ("Metric", "FY Total")]
            for _mn, _val in _ent_oc.items():
                if _mn not in _df.columns or len(_df) <= 7:
                    continue
                _c = _df.columns.get_loc(_mn)
                _gm, _nm0, _oc0 = g(3, _c), g(6, _c), g(5, _c)
                _tc = _gm - _nm0 - _oc0                      # absolute transport (unchanged)
                _df.iat[5, _c] = round(_val, 0)
                _nm = _gm - _tc - _val
                _df.iat[6, _c] = round(_nm, 0)
                _sales = g(1, _c)
                _df.iat[7, _c] = round(100 * _nm / _sales, 2) if _sales else 0.0
            if "FY Total" in _df.columns and len(_df) > 7:
                _fy = _df.columns.get_loc("FY Total")
                _df.iat[5, _fy] = round(sum(g(5, _df.columns.get_loc(m)) for m in _mcols), 0)
                _df.iat[6, _fy] = round(sum(g(6, _df.columns.get_loc(m)) for m in _mcols), 0)
                _fs = g(1, _fy)
                _df.iat[7, _fy] = round(100 * g(6, _fy) / _fs, 2) if _fs else 0.0
            return _s

        # ── Re-Commerce = a normal vertical (Samsung rule removed) ──────────
        # Closed months come from the newest 'Profitability Report of Recommerce
        # till DD-MM-YYYY.xlsx' via the frozen overlay (same as every other
        # vertical); the open month is computed live from the MIS. The manual
        # detail store no longer overrides the summary.
        _variants: dict[str, pd.DataFrame] = {"Report": profit_df}
        _reco_skip: set = set()

        def _build(_pdf):
            _s = reports.summaries_by_category(_pdf, _ar, _ap, op_cost_bills=_obills,
                                               reco_ships=reco_ships)
            try:
                _s = _frozen.apply_frozen(_s, _app_dir, _open_m, skip_tabs=_reco_skip)
            except Exception as _fe:
                st.caption(f"⚠ Frozen-month overlay skipped: {_fe}")
            return _apply_ent_opcost(_s)

        _labels = list(_variants.keys())
        if len(_labels) > 1:
            st.caption("Re-Commerce is maintained in two versions — pick which to view; "
                       "both are downloadable/emailable below.")
            _sel = st.radio("Re-Commerce version", _labels, horizontal=True, key="reco_variant")
        else:
            _sel = _labels[0]
        _sel_pdf = _variants[_sel]
        summaries = _build(_sel_pdf)
        st.session_state["_recy_summaries"] = summaries

        # ── Re-Commerce (Without Samsung) — ADDITIVE view ────────────────────
        # Same pipeline over the same data, minus RC rows whose VENDOR starts
        # with 'Samsung'. Closed months freeze to the signed-off figures in
        # frozen.RC_NOSAMSUNG_FROZEN; the open month is live. The regular
        # Re-Commerce summary above is computed exactly as before — untouched.
        _rc_ns = None
        try:
            if "Re-Commerce" in summaries:
                _s_ns = reports.summaries_by_category(
                    reports.rc_without_samsung(_sel_pdf), _ar, _ap,
                    op_cost_bills=_obills, reco_ships=reco_ships)
                _rc_ns = _s_ns.get("Re-Commerce")
                if _rc_ns is not None:
                    _frozen.apply_rc_nosamsung(_rc_ns, _open_m)
        except Exception as _nse:
            _rc_ns = None
            st.caption(f"⚠ Without-Samsung Re-Commerce view skipped: {_nse}")
        if _rc_ns is not None:
            st.session_state["_recy_summaries"] = {
                **summaries, "Re-Commerce (Without Samsung)": _rc_ns}

        try:
            _frozen_tabs = sorted(set(_frozen.latest_files(_app_dir)))
            if _frozen_tabs and _open_m:
                _cut = _pdates.max().strftime("%d-%b-%Y")
                st.caption(f"🔒 Closed months frozen from the per-vertical report files "
                           f"({', '.join(_frozen_tabs)}); **{_open_m} live up to {_cut}**"
                           + ("; Re-Commerce from its manual detail." if _reco_skip else "."))
        except Exception:
            pass
        _as = st.session_state.get("_amz_status")
        if _as:
            _icon = "🟢" if _as == "live" else ("🟠" if _as.startswith("snapshot") else "🔴")
            st.caption(f"{_icon} Amazon × Recykal live sheet: {_as} — Re-Commerce after "
                       f"17-Jul-2026 is costed from it (cost & revenue from the sheet, "
                       f"shipment id from the Zoho invoice).")

        sum_tabs = st.tabs(list(summaries.keys()))
        for tab, (name, sdf) in zip(sum_tabs, summaries.items()):
            with tab:
                if sdf.shape[1] <= 2 and len(_sel_pdf) and sdf.iloc[0, -1] == 0:
                    st.info("No data in this category yet.")
                st.dataframe(sdf, use_container_width=True, hide_index=True, height=640)
                if name == "Re-Commerce" and _rc_ns is not None:
                    st.markdown("#### Re-Commerce — Without Samsung (vendor)")
                    st.caption("Additive view: the same report minus shipments whose vendor "
                               "name starts with 'Samsung'. Closed months are the signed-off "
                               "figures; the open month is live.")
                    st.dataframe(_rc_ns, use_container_width=True, hide_index=True, height=640)
                safe = name.replace("(", "_").replace(")", "").replace("/", "-").replace(" ", "_")
                if name != "All Categories":
                    try:
                        _wb_v = reports.combined_workbook(
                            summaries, _sel_pdf, _ar, _ap, vertical=name, reco_ships=reco_ships,
                            rc_ns_summary=_rc_ns if name == "Re-Commerce" else None, op_cost_bills=_obills)
                        st.download_button(
                            f"⬇ Download {name} (Excel — Summary · Receivables · Payables · Report)",
                            _wb_v, file_name=f"profitability_{safe}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_comb_{name}",
                        )
                    except Exception as _we:
                        st.warning(f"Couldn't build the {name} workbook: {_we}")

        # ── Reco Items — the review is a GATE shown BEFORE the summary (above).
        # After the summary is computed we no longer show the full table (it was
        # appearing twice and pushing the email section out of view); the
        # selection can still be revised from a collapsed expander.
        if len(_cand):
            st.markdown("---")
            _in_reco = len(reco_ships)
            with st.expander(f"🧾 Reco Items — {_in_reco} of {len(_cand)} excluded "
                             f"(click to revise the selection)", expanded=False):
                _render_reco_review(suffix="_bottom")

        st.markdown("---")
        # One "Download ALL" for the single report (all shipments incl. Samsung).
        # Guarded so a workbook build error can never hide the email section below.
        for _lbl, _pdf in _variants.items():
            _sfx = "" if _lbl == "Report" else f" — {_lbl}"
            _fn = "profitability_all" + ("" if _lbl == "Report"
                                         else "_" + _lbl.lower().replace(" ", "_")) + ".xlsx"
            try:
                _s = summaries if _lbl == _sel else _build(_pdf)
                _wb_all = reports.combined_workbook(_s, _pdf, _ar, _ap, reco_ships=reco_ships,
                                                    rc_ns_summary=_rc_ns, op_cost_bills=_obills)
                st.download_button(
                    f"⬇ Download ALL Verticals{_sfx} (Excel — Summary · Receivables · Payables · Report)",
                    _wb_all, file_name=_fn,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_all_{_lbl}",
                )
            except Exception as _we:
                st.warning(f"Couldn't build the ALL-verticals workbook ({_lbl}): {_we}")

        # ── Email the report to the team ──────────────────────────────────────
        st.markdown("---")
        st.markdown("### 📧 Send to team")
        import mailer as _mailer
        _cfg = _mailer.get_email_config()
        if not _mailer.is_configured():
            st.info(
                "Email isn't set up yet. Add your Gmail **sender** + **App Password** to "
                "`.streamlit/secrets.toml` under an `[email]` section to enable sending "
                "(App Password: Google Account → Security → 2-Step Verification → App passwords)."
            )
        # period line for the mail body — "April 1, 2026 and July 2, 2026"
        _pd_all = pd.to_datetime(profit_df.iloc[:, 2], errors="coerce")
        _p_to = _pd_all.max()
        _p_from = pd.Timestamp(_p_to.year if _p_to.month >= 4 else _p_to.year - 1, 4, 1) \
            if pd.notna(_p_to) else None
        # NB: build the day with .day (NOT strftime '%#d'/'%-d' — those are
        # platform-specific: '%#d' is Windows-only and raises on the hosted
        # Linux app, which was breaking the whole "Send to team" section).
        _period = (f"{_p_from.strftime('%B')} {_p_from.day}, {_p_from.year} and "
                   f"{_p_to.strftime('%B')} {_p_to.day}, {_p_to.year}"
                   if _p_from is not None else "the period")

        _to = st.text_input("Recipients (comma-separated)",
                            value=", ".join(_cfg.get("recipients", [])), key="mail_to")
        _subj = st.text_input("Subject", value="Marketplace Profitability Report", key="mail_subj")
        _body = st.text_area(
            "Message (the summary table is added below this automatically)",
            value=(f"Dear Team,\n\nPlease find the attached Marketplace Profitability "
                   f"Report for the transactions between {_period}."),
            key="mail_body", height=100)
        _per_vertical = st.checkbox(
            "Send a separate email per vertical (one attachment each)", key="mail_perv",
            help="One email per vertical — its summary table in the body and only that "
                 "vertical's workbook attached. Per-vertical recipient lists from secrets "
                 "are used when set; otherwise the recipients above.")

        def _mail_html(_s, vert_label, body_text):
            intro = body_text.replace("\n", "<br>")
            return _mailer.summary_html(_s[vert_label], vert_label, intro,
                                        regards="Regards,<br>Profitability Automation Engine")

        def _send_all(only_to=None):
            """Send the single all-shipments report — per vertical if that box
            is ticked."""
            _rbv = _cfg.get("recipients_by_vertical", {})
            _base_to = [x.strip() for x in _to.split(",") if x.strip()]
            results = []
            for _lbl, _pdf in _variants.items():
                _s = summaries if _lbl == _sel else _build(_pdf)
                _vsfx = "" if _lbl == "Report" else f" — {_lbl}"
                _fsfx = "" if _lbl == "Report" else "_" + _lbl.lower().replace(" ", "_")
                if _per_vertical:
                    for _v in _s.keys():
                        if _v == "All Categories":
                            continue
                        _wb = reports.combined_workbook(_s, _pdf, _ar, _ap, vertical=_v, reco_ships=reco_ships,
                                                        rc_ns_summary=_rc_ns if _v == "Re-Commerce" else None, op_cost_bills=_obills)
                        _rcpts = only_to or _rbv.get(_v, _base_to)
                        _safe = _v.replace("(", "_").replace(")", "").replace("/", "-").replace(" ", "_")
                        _vbody = _body.replace("Profitability Report", f"Profitability Report - {_v}")
                        _ok, _msg = _mailer.send_report(
                            _rcpts, f"{_subj} — {_v}{_vsfx}", _vbody, _wb,
                            f"profitability_{_safe}{_fsfx}.xlsx", _cfg,
                            html=_mail_html(_s, _v, _vbody))
                        results.append(f"{'✅' if _ok else '❌'} {_v}{_vsfx}: {_msg}")
                else:
                    _wb = reports.combined_workbook(_s, _pdf, _ar, _ap, reco_ships=reco_ships,
                                                    rc_ns_summary=_rc_ns, op_cost_bills=_obills)
                    _ok, _msg = _mailer.send_report(
                        only_to or _base_to, f"{_subj}{_vsfx}", _body, _wb,
                        f"profitability_all{_fsfx}.xlsx", _cfg,
                        html=_mail_html(_s, "All Categories", _body))
                    results.append(("✅ " if _ok else "❌ ") + f"{_lbl}{_vsfx}: {_msg}"
                                    if _lbl != "Report" else ("✅ " if _ok else "❌ ") + _msg)
            return results

        _c1, _c2 = st.columns([1, 1])
        with _c1:
            if st.button("📨 Send report", key="mail_send", disabled=not _mailer.is_configured()):
                with st.spinner("Sending…"):
                    st.write("\n".join(_send_all()))
        with _c2:
            if st.button("🧪 Send test to myself", key="mail_test",
                         disabled=not _mailer.is_configured(),
                         help="Sends the exact same email(s) ONLY to the sender address — "
                              "check your own inbox before mailing the team."):
                with st.spinner("Sending test…"):
                    st.write("\n".join(_send_all(only_to=[_cfg.get("sender", "")])))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 6: Management Reports
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Management Reports":
    st.title("📈 Management Reports")

    # ── Auto-run full pipeline if not yet done ───────────────────────────────
    with st.spinner("Preparing data..."):
        _auto_pipeline()

    # ── Load profitability table ──────────────────────────────────────────────
    profit_df = db.read_table("Merged", "profitability")
    if "_source_file" in profit_df.columns:
        profit_df = profit_df.drop(columns=["_source_file"])

    if profit_df.empty:
        st.warning("No data found. Please upload a file on the **Upload Files** page first.")
    else:
        # ── Executive KPIs header ─────────────────────────────────────────────
        kpis = reports.executive_kpis(profit_df)
        st.markdown("### Executive Summary")
        k_cols = st.columns(4)
        kpi_items = list(kpis.items())
        for i, (label, val) in enumerate(kpi_items[:4]):
            with k_cols[i]:
                if "₹" in label:
                    st.metric(label, f"₹{val:,.0f}")
                elif "%" in label:
                    st.metric(label, f"{val:.2f}%")
                else:
                    st.metric(label, f"{val:,.0f}" if isinstance(val, (int, float)) else val)
        k_cols2 = st.columns(5)
        for i, (label, val) in enumerate(kpi_items[4:]):
            with k_cols2[i]:
                if "₹" in label:
                    st.metric(label, f"₹{val:,.0f}")
                elif "%" in label:
                    st.metric(label, f"{val:.2f}%")
                else:
                    st.metric(label, f"{val:,.0f}" if isinstance(val, (int, float)) else val)

        st.markdown("---")

        # ── Report tabs ───────────────────────────────────────────────────────
        (
            tab_sup, tab_buy, tab_mat,
            tab_mon, tab_wk, tab_bucket,
            tab_rank
        ) = st.tabs([
            "🏭 Supplier-wise",
            "🛒 Buyer-wise",
            "📦 Material-wise",
            "📅 Monthly",
            "📆 Weekly",
            "📊 Margin Buckets",
            "🏆 Rankings",
        ])

        # ── Supplier-wise ─────────────────────────────────────────────────────
        with tab_sup:
            st.subheader("Supplier-wise Profitability")
            sup_df = reports.supplier_summary(profit_df)
            st.dataframe(sup_df, use_container_width=True, hide_index=True)
            # Highlight best/worst
            c1, c2, c3 = st.columns(3)
            if not sup_df.empty:
                best   = sup_df.iloc[0]
                worst  = sup_df.iloc[-1]
                c1.metric("Best Margin Supplier",  best["Supplier"],  f"₹{best['Margin']:,.0f}")
                c2.metric("Worst Margin Supplier", worst["Supplier"], f"₹{worst['Margin']:,.0f}")
                c3.metric("Total Suppliers", len(sup_df))
            st.download_button("⬇ Download Supplier Summary",
                               sup_df.to_csv(index=False).encode(),
                               file_name="supplier_summary.csv", mime="text/csv")

        # ── Buyer-wise ────────────────────────────────────────────────────────
        with tab_buy:
            st.subheader("Buyer-wise Profitability")
            buy_df = reports.buyer_summary(profit_df)
            st.dataframe(buy_df, use_container_width=True, hide_index=True)
            c1, c2, c3 = st.columns(3)
            if not buy_df.empty:
                best  = buy_df.iloc[0]
                worst = buy_df.iloc[-1]
                c1.metric("Best Margin Buyer",  best["Buyer"],  f"₹{best['Margin']:,.0f}")
                c2.metric("Worst Margin Buyer", worst["Buyer"], f"₹{worst['Margin']:,.0f}")
                c3.metric("Total Buyers", len(buy_df))
            st.download_button("⬇ Download Buyer Summary",
                               buy_df.to_csv(index=False).encode(),
                               file_name="buyer_summary.csv", mime="text/csv")

        # ── Material-wise ─────────────────────────────────────────────────────
        with tab_mat:
            st.subheader("Material-wise Profitability")
            mat_df = reports.material_summary(profit_df)
            st.dataframe(mat_df, use_container_width=True, hide_index=True)
            c1, c2 = st.columns(2)
            c1.metric("Total Materials", len(mat_df))
            if not mat_df.empty:
                top_mat = mat_df.iloc[0]
                c2.metric("Best Material", top_mat["Material"], f"₹{top_mat['Margin']:,.0f}")
            st.download_button("⬇ Download Material Summary",
                               mat_df.to_csv(index=False).encode(),
                               file_name="material_summary.csv", mime="text/csv")

        # ── Monthly ───────────────────────────────────────────────────────────
        with tab_mon:
            st.subheader("Monthly Profitability")
            mon_df = reports.monthly_summary(profit_df)
            st.dataframe(mon_df, use_container_width=True, hide_index=True)
            if not mon_df.empty:
                best_m  = mon_df.loc[mon_df["Margin"].idxmax()]
                worst_m = mon_df.loc[mon_df["Margin"].idxmin()]
                c1, c2 = st.columns(2)
                c1.metric("Best Month",  f"{best_m['Month_mmm_yy']} ({best_m['Quarter']})",
                          f"₹{best_m['Margin']:,.0f}")
                c2.metric("Worst Month", f"{worst_m['Month_mmm_yy']} ({worst_m['Quarter']})",
                          f"₹{worst_m['Margin']:,.0f}")
            st.download_button("⬇ Download Monthly Summary",
                               mon_df.to_csv(index=False).encode(),
                               file_name="monthly_summary.csv", mime="text/csv")

        # ── Weekly ────────────────────────────────────────────────────────────
        with tab_wk:
            st.subheader("Weekly Profitability")
            wk_df = reports.weekly_summary(profit_df)
            st.dataframe(wk_df, use_container_width=True, hide_index=True)
            if not wk_df.empty:
                best_w = wk_df.loc[wk_df["Margin"].idxmax()]
                c1, c2 = st.columns(2)
                c1.metric("Best Week", f"Week {int(best_w['Week_No'])}", f"₹{best_w['Margin']:,.0f}")
                c2.metric("Total Weeks", len(wk_df))
            st.download_button("⬇ Download Weekly Summary",
                               wk_df.to_csv(index=False).encode(),
                               file_name="weekly_summary.csv", mime="text/csv")

        # ── Margin Buckets ────────────────────────────────────────────────────
        with tab_bucket:
            st.subheader("Margin Bucket Distribution")
            bkt_df = reports.margin_bucket_summary(profit_df)
            st.dataframe(bkt_df, use_container_width=True, hide_index=True)
            c1, c2, c3 = st.columns(3)
            for col_w, row in zip([c1, c2, c3], bkt_df.itertuples()):
                col_w.metric(
                    row.Margin_Bucket if hasattr(row, "Margin_Bucket") else str(row[1]),
                    f"{row.Shipments} shipments",
                    f"₹{row.Margin:,.0f} ({row._6:.2f}%)" if hasattr(row, '_6') else ""
                )

        # ── Rankings ──────────────────────────────────────────────────────────
        with tab_rank:
            st.subheader("Top / Bottom Rankings")
            n_rank = st.slider("Show Top / Bottom N", 3, 20, 5)
            rankings = reports.top_n_rankings(profit_df, n=n_rank)

            r1, r2 = st.columns(2)
            with r1:
                st.markdown(f"#### 🥇 Top {n_rank} Suppliers — Margin")
                st.dataframe(rankings["top_suppliers_margin"], use_container_width=True, hide_index=True)
                st.markdown(f"#### 📉 Bottom {n_rank} Suppliers — Margin")
                st.dataframe(rankings["worst_suppliers_margin"], use_container_width=True, hide_index=True)
                st.markdown(f"#### 📦 Top {n_rank} Suppliers — Volume")
                st.dataframe(rankings["top_suppliers_volume"], use_container_width=True, hide_index=True)
            with r2:
                st.markdown(f"#### 🥇 Top {n_rank} Buyers — Margin")
                st.dataframe(rankings["top_buyers_margin"], use_container_width=True, hide_index=True)
                st.markdown(f"#### 📦 Top {n_rank} Buyers — Volume")
                st.dataframe(rankings["top_buyers_volume"], use_container_width=True, hide_index=True)
                st.markdown(f"#### 🔬 Top {n_rank} Materials — Margin")
                st.dataframe(rankings["top_materials_margin"], use_container_width=True, hide_index=True)

        st.markdown("---")
        # ── Download All Reports in one ZIP ──────────────────────────────────
        import zipfile, io as _io
        def _make_zip():
            buf = _io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("supplier_summary.csv",  reports.supplier_summary(profit_df).to_csv(index=False))
                zf.writestr("buyer_summary.csv",     reports.buyer_summary(profit_df).to_csv(index=False))
                zf.writestr("material_summary.csv",  reports.material_summary(profit_df).to_csv(index=False))
                zf.writestr("monthly_summary.csv",   reports.monthly_summary(profit_df).to_csv(index=False))
                zf.writestr("weekly_summary.csv",    reports.weekly_summary(profit_df).to_csv(index=False))
                zf.writestr("margin_buckets.csv",    reports.margin_bucket_summary(profit_df).to_csv(index=False))
            buf.seek(0)
            return buf.read()

        st.download_button(
            "⬇ Download All Reports (ZIP)",
            _make_zip(),
            file_name="management_reports.zip",
            mime="application/zip",
        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 6: Query Data
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Query Data":
    st.title("Query Data")
    status = db.all_db_status()
    loaded = {s: v for s, v in status.items() if v["exists"]}

    if not loaded:
        st.info("No data yet. Upload a file on the **Upload Files** page.")
    else:
        sheet_sel = st.selectbox("Choose Sheet", list(loaded.keys()))
        tables = db.list_tables(sheet_sel)
        if not tables:
            st.info("No tables available for this sheet.")
        else:
            tbl_sel = st.selectbox("Choose Table", tables)
            df_query = db.read_table(sheet_sel, tbl_sel).drop(columns=["_source_file"], errors="ignore")

            # Simple filter UI
            st.caption(f"{len(df_query):,} rows · {len(df_query.columns)} columns")
            filter_col = st.selectbox("Filter column (optional)", ["— none —"] + list(df_query.columns))
            if filter_col != "— none —":
                vals = df_query[filter_col].dropna().unique().tolist()
                chosen = st.multiselect(f"Keep values for {filter_col}", vals, default=vals)
                df_query = df_query[df_query[filter_col].isin(chosen)]

            st.dataframe(df_query, use_container_width=True, hide_index=True)
            st.download_button("Download CSV", df_query.to_csv(index=False).encode(),
                               file_name=f"{sheet_sel}_{tbl_sel}.csv", mime="text/csv")
