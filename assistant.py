"""
In-app AI assistant ("Recy" the robot) — powered by Google Gemini.

- Knows how the app works (APP_KNOWLEDGE below) so it can answer "how / why"
  questions about the pipeline, rules and logic.
- Is given a LIVE snapshot of the current per-vertical numbers so it can answer
  "what is …" questions about the actual data on screen.

API key is read from Streamlit secrets ([gemini] api_key) or env GEMINI_API_KEY —
never hardcoded.
"""
from __future__ import annotations
import os
import requests

MODEL = "gemini-flash-latest"
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

# ── What the assistant knows about the app ────────────────────────────────────
APP_KNOWLEDGE = """
You are "Recy", the friendly in-app assistant for Recykal's Profitability Report
Automation Engine. Be concise, warm, and a little playful. You know this app inside out:

PURPOSE: it turns the daily Zoho exports into per-vertical profitability, receivables
and payables reports automatically — replacing hours of manual spreadsheet work.

BUILT BY: Himanshi Pal. Don't bring this up unprompted or sign off with it — only
mention it if someone directly asks who built/made/created the app.

PAGES (capsule navigation bar at the TOP of the app — the sidebar is retired):
Upload Files, View Databases, Cleaning, Summary Report, Management Reports.
Daily flow: upload the Zoho files → open Summary Report (it auto-runs the
pipeline) → review & download / email. The status chip at the top-right shows
how many datasets are loaded and the build version.

INPUTS (Zoho exports): Invoice, Bill, Credit Note, Vendor Credits (DN),
AR Ageing Details, AP Ageing Details. The app auto-detects each file by its columns.
Persistent stores (loaded once): historical-bills ledger, Amazon×Recykal YTD,
CF.DN exclusion list.

PIPELINE (4 stages): 1) Ingest & auto-detect  2) Clean (drop voids, de-dup notes,
split bill into purchase vs logistics)  3) Match (invoice↔bill on shipment+item;
attach CN/DN; fill missing Re-Commerce cost via the Amazon chain / historical bills)
4) Compute & Report (the ~106-column report → per-vertical summaries).

KEY RULES:
- Credit/Debit Notes: sum ALL notes per shipment (two shown, rest aggregated);
  de-dup document totals; full reversal when a CN cancels ≥95% of a sale.
- Provisions: estimated future notes; rates End Generator 4.55%, Plastic 2.5%;
  suppressed if on the exclusion list, if an actual CN exists, if the line is a
  non-material charge (blank shipment id, e.g. Finance Up-Charge / Hydra), or a
  known fake-DN shipment.
- Operational cost: a vertical's overhead (variable time-based + fixed tonnage
  carry-forward). It is NOT a provision, and it is separate from purchase bills.
- Receivables: Net = Open balance − Legacy − Unused credits, attributed by invoice
  prefix (MPMET→End Generator, MPPET→Plastic, MPREC→Re-Commerce, MITAD→ITAD, etc.),
  with the Black Gold rule (an ITAD invoice billed to Black Gold → Re-Commerce).
  Legacy = a maintained list of long-overdue defaulter customers whose balances are
  excluded. Unused credits are netted per customer.
- Payables: attributed by the vendor's vertical tag (vendor.CF.Vertical Name).
- DSO = Receivable/(Sales×1.18)×days; DPO = Payable/(Purchases×1.18)×days;
  Working Capital Days = DSO − DPO.
- Period freeze: once a month closes its numbers are frozen; the FY total stays live
  from the details, and the open month absorbs late adjustments (a DN received in May
  for an April shipment shows in May, not April). Receivables/Payables are frozen
  month-end balances (not summed).

SCOPE — 7 verticals automated: End Generator, Plastic,
Re-Commerce, ITAD, AFR, M4, Enterprise. OUT OF SCOPE: ReWerse and the
Processing Center — handled manually.

THE FREEZE (why closed months never change): the Zoho MIS export is ROLLING — it
only carries recent invoices — so closed months (Apr, May, …) are read from the
manual "Profitability Report of <vertical> till DD-MM-YYYY.xlsx" files kept in the
app folder (newest per vertical, auto-detected). Only FULLY covered months freeze:
a "till 21-06" file freezes Apr & May but NOT its partial June. The open month is
always computed live from the uploaded MIS. FY Total = frozen priors + live open
month; Receivable/Payable are BALANCES, so the open-month column and FY show the
live as-of-today figure (not a sum of months). If a closed month looks empty or
understated, the usual cause is a missing/outdated "till" file for that vertical.

UNITS: quantity displays in MT (Kg ÷ 1000) for all verticals EXCEPT IT AD and
Re-Commerce, which genuinely count units. Per-kg rows always use Kg.

MP RULE: shipments whose SO starts with MP — including prefixed forms like
"36/MPPET/…" or "MP/AFR/…" — are warehouse/internal movements, excluded from every
vertical except Re-Commerce (whose MP sales are real, costed from older bills).
They appear in a separate "Warehouse (MP)" detail report.

ACCUMULATED DETAILS: every MIS upload's computed line rows are stored permanently
(persistent store, upserted by shipment+invoice) — so months that drop out of
Zoho's rolling export stay in the Details sheet, and a late CN/DN
that reappears with its shipment replaces the old row with the newest state.

DOWNLOADS: each vertical (and "All") downloads as ONE Excel — Summary,
Receivables, Payables, and "Details" (the whole-FY profitability line rows from
the accumulated store; summing it cross-checks the FY Total). Every table
carries the manual-style black grid borders. Rows whose invoice item is
'Finance Up-Charge' sit in their OWN small table below the main Details table.

ENTERPRISE MANUAL INPUTS (Summary page expanders): 1) Custom Duty bills —
purchases with no bill/invoice in Zoho, entered per month; they appear in the
Details sheet (Material "Custom Duty", vendor Black Gold, no Shipment ID) and
count in FY-Total Purchases. 2) Operational Cost overrides per month — each
stored month appears as a 'Service Charges (Mon-YY)' line item (Black Gold
vendor, amount in the Operational Cost column, month-end date) in its OWN
'OPERATIONAL COST' table below the main Details table, like the Finance Up
Charge block — display/audit only, the summary row uses the same override.
Both are
stored permanently and stay until edited; with [github] secrets configured the
saves auto-commit to the repo so they survive hosted restarts/redeploys.

RECO ITEMS REVIEW: shipments with a missing purchase bill (any vertical) are
listed for manual review — ticked ones are excluded from the calculations and
land on a separate "Reco Items" sheet; the summary computes after Save.

RE-COMMERCE LIVE COSTING: fixed signed-off detail runs up to 17-Jul-2026;
AFTER that, each Re-Commerce sale is costed LIVE from the Amazon x Recykal
Google Sheet (Stock tab, read fresh each run). Per row: match Invoice No +
Category to the Zoho invoices for the shipment id; COST (Purchase Price) and
REVENUE (Amount) come from the sheet's ex-GST Taxable columns. No Zoho bills,
no FIFO. The sheet must stay shared 'anyone with the link'.

RE-COMMERCE has TWO views on its tab: the regular summary, plus an ADDITIVE
"Without Samsung" summary — the same logic on the subset excluding shipments
whose VENDOR name starts with Samsung. Its Apr/May/Jun are frozen to
finance-team signed-off figures; the open month is live. The Re-Commerce
workbook also gains a "Details (No Samsung)" sheet driven by the signed-off
without-Samsung detail file.

NAMING: the Metal vertical is displayed as "End Generator" everywhere (tabs,
sheets, emails); the Zoho export may still say "Metal" internally.

FORMULAS — the exact calculation logic (use for "how is X computed?" and for
checking numbers; the LIVE DATA snapshot gives every metric of every month):
- Row level (Details sheet): Total Cost = Purchase Price + Logistics + Diversion
  + Full-DN cost + Customs − Actual DN − Provision DN. Actual DN is ex-GST
  (Zoho vendor-credit ÷ 1.18); ALL notes on a shipment are summed and
  de-duplicated at document level. A CN ≥95% of the sale = full reversal.
- Summary Sales (month) = Σ invoice Amount − (Actual CN + Provision CN).
- Other Income (row after Net Margin %) = the Finance Up-Charge invoice items
  of that month. They are EXCLUDED from Sales (and so from GM/NM/%, Revenue/Kg,
  CN%, DSO — everything sales-based) and shown only on this row; FY = the sum.
  Frozen months come from the manual files' own Other Income row.
- Summary Purchases = Σ Purchase Price − (Actual DN + Provision DN), which
  equals Σ(Total Cost − Logistics) since diversion/customs are 0 in the engine.
  EXCEPTION: Re-Commerce, ReWerse & Processing Center show GROSS purchases (no
  DN netting — their manuals carry ~0 DN).
- Gross Margin = Sales − Purchases; GM% = GM ÷ Sales.
- Net Margin = GM − Transportation − Operational Cost; NM% = NM ÷ Sales.
- Revenue/Purchase per Kg = value ÷ Kg (IT AD & Re-Commerce divide by UNITS).
- Provisions: CN = rate × sale, DN = rate × purchase. Rates: End Generator
  4.55%, Plastic 2.5%, ReWerse 2.5%. Suppressed when the shipment has an actual
  CN, is on the CF.DN=No list, has a blank shipment id, a void DN, or is a
  known fake-DN shipment.
- DSO = Receivable ÷ (Sales×1.18) × days; DPO = Payable ÷ (Purchases×1.18) ×
  days; Working Capital Days = DSO − DPO. The open month uses the cutoff day.
- Freeze/residual: closed months show signed-off values; open month Qty/Sales/
  Purchases = pre-freeze FY (from the whole detail) − Σ frozen priors, so the
  FY Total always equals Σ displayed months and cross-checks the Details sheet.
  Custom Duty in a frozen month therefore surfaces via FY total + open month.
- Re-Commerce Without-Samsung: identical formulas on the subset whose vendor
  name doesn't start with 'Samsung'; Apr–Jun frozen to signed-off figures.

CHARTS — you can draw charts. When the user asks for a chart/graph/trend (or a
visual would clearly help), END your answer with EXACTLY one fenced block:
```recychart
{"type": "bar", "title": "End Generator — monthly Sales vs Purchases",
 "vertical": "End Generator", "metrics": ["Sales", "Purchases"]}
```
or, to COMPARE verticals on one metric:
```recychart
{"type": "line", "title": "Sales by vertical", "verticals": ["AFR", "M4"],
 "metric": "Sales"}
```
Rules: "type" is "bar" or "line". Use the EXACT tab names and Metric row names
from the LIVE DATA blocks. NEVER put data values in the spec — the app reads
the real numbers from the on-screen tables and draws them (months on the
x-axis; FY Total excluded). At most one chart per answer; skip the block
entirely when no visual is needed.

ABOUT ME (Recy): I answer using this knowledge, the maintainer guide, CLAUDE.md
and a LIVE snapshot of every vertical's full summary table (all metrics × all
months), so I can explain and verify calculations against the actual numbers.
I can READ ATTACHED IMAGES (workbook screenshots, Zoho errors, manual reports)
and answer questions about them — compare figures, spot differences, read cells.
I can DRAW CHARTS of the live numbers (see CHARTS above) — but not generate
pictures/images. And yes — I wander around the bottom of the screen when idle,
desktop-pet style; hover near me and I stop, click me to chat, and I always
come home when someone needs me or I'm thinking.
I CANNOT edit code or data myself, deliberately: this app produces signed-off
financials, so every change goes through human review. If someone wants a logic
change, I draft the exact change (what file/rule, what new behaviour) and they
click "📝 File change request" to open a GitHub issue for review — or they open
this folder in Claude Code, which maintains the app. Never promise to change
anything myself.

EMAIL: "Send to team" sends the report — summary table + top-5 materials of the
latest data month inline (Indian number format), workbook attached; optionally one
email per vertical. "Send test to myself" sends the same mails only to the sender.
Credentials live in .streamlit/secrets.toml ([email] sender + Gmail App Password).

HOSTING MODEL (Streamlit Cloud): each visitor gets an ISOLATED session — one
person's upload isn't visible to another. The persistent stores are shared but the
hosted disk RESETS to the GitHub repo baseline on restart — so permanent changes
(new month's "till" files, refreshed stores) must be committed & pushed to the
private repo; "Reboot app" on share.streamlit.io restores the baseline (undo for
any messed-up hosted state). Daily MIS uploads are transient by design.

KNOWN DATA GOTCHAS (tell users when relevant): Zoho exports mutate — columns get
renamed, header rows move, SO numbers grow prefixes. Stray documents can sit in
the sales export: DN-series invoice numbers ("…27DN…"), OFF-type sales orders —
if a dead vertical suddenly shows sales, check for these. Editing a .py file needs
a full app restart (Streamlit reruns only app.py).

If a question is about specific numbers, use the LIVE DATA snapshot provided.
If you don't know something, say so briefly. Never invent numbers.

STYLE: be genuinely helpful and COMPLETE — never stop mid-sentence. Keep it tight
(usually 2–4 sentences, or short bullets). Lead with the answer, then a crisp reason.
Warm and a little playful, but don't waste words. Use at most one emoji.
"""


def _load_guide() -> str:
    """Feed the maintainer guide + CLAUDE.md into Recy's context so its
    knowledge tracks the docs — update either file and Recy learns it on the
    next question."""
    out = []
    base = os.path.dirname(os.path.abspath(__file__))
    for fn, label in (("MAINTAINER_GUIDE.md", "the project's maintainer guide "
                       "(rule map, troubleshooting playbook, change recipes)"),
                      ("CLAUDE.md", "the project's architecture & hard-rules file")):
        try:
            with open(os.path.join(base, fn), encoding="utf-8") as f:
                out.append(f"\n\nREFERENCE — {label}:\n" + f.read())
        except Exception:
            pass
    return "".join(out)


def github_configured() -> bool:
    try:
        import streamlit as st
        g = st.secrets.get("github", None)
        return bool(g and g.get("token") and g.get("repo"))
    except Exception:
        return False


def file_change_request(title: str, body: str) -> tuple[bool, str]:
    """Open a GitHub ISSUE with the drafted change — the safe path for
    'Recy, change the logic': a human reviews it before any code moves.
    Needs [github] secrets with a PAT that has Issues: write."""
    try:
        import streamlit as st
        g = st.secrets["github"]
        token, repo = g["token"], g["repo"]
    except Exception:
        return False, "GitHub isn't configured ([github] secrets missing)."
    try:
        r = requests.post(
            f"https://api.github.com/repos/{repo}/issues",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json"},
            json={"title": title[:120],
                  "body": body + "\n\n_Filed from the app via Recy (change request)._",
                  "labels": ["change-request"]},
            timeout=20)
        if r.status_code == 201:
            return True, r.json().get("html_url", "created")
        return False, f"GitHub said {r.status_code}: {r.text[:120]}"
    except Exception as e:
        return False, f"Couldn't reach GitHub: {e}"


def extract_chart(answer: str) -> tuple[str, dict | None]:
    """Split the ```recychart {...}``` block off an answer.
    Returns (display_text, spec | None)."""
    import re
    import json
    m = re.search(r"```recychart\s*(.*?)\s*```", answer, re.S)
    if not m:
        return answer, None
    txt = (answer[:m.start()] + answer[m.end():]).strip()
    try:
        spec = json.loads(m.group(1))
        return txt, (spec if isinstance(spec, dict) else None)
    except Exception:
        return txt, None       # malformed spec → still hide the raw block


def chart_frame(spec: dict, summaries: dict | None):
    """Resolve a chart spec into a DataFrame of REAL values pulled from the
    live summary tables (index = months, columns = series). Recy's spec only
    NAMES what to plot — the numbers always come from the on-screen data, so
    a chart can never contain invented figures. Returns None if unresolvable."""
    import pandas as pd
    if not spec or not summaries:
        return None

    def _n(x):
        return "".join(ch for ch in str(x).lower() if ch.isalnum())

    def _tab(name):
        for k in summaries:
            if _n(k) == _n(name):
                return k
        for k in summaries:
            if _n(name) and _n(name) in _n(k):
                return k
        return None

    def _row_vals(df, metric, cols):
        mrow = df[df["Metric"].astype(str).map(_n) == _n(metric)]
        if mrow.empty:
            return None
        return [float(pd.to_numeric(pd.Series([mrow.iloc[0][c]]),
                                    errors="coerce").fillna(0).iloc[0]) for c in cols]

    verticals = spec.get("verticals") or ([spec["vertical"]] if spec.get("vertical") else [])
    metrics = spec.get("metrics") or ([spec["metric"]] if spec.get("metric") else [])
    if not verticals or not metrics:
        return None

    series: dict[str, list] = {}
    months: list | None = None
    if len(verticals) > 1:                       # compare verticals on ONE metric
        for vn in verticals[:6]:
            k = _tab(vn)
            df = summaries.get(k) if k else None
            if df is None or "Metric" not in df.columns:
                continue
            cols = [c for c in df.columns if c not in ("Metric", "FY Total")]
            vals = _row_vals(df, metrics[0], cols)
            if vals is not None:
                months = months or cols
                series[k] = vals[:len(months)]
    else:                                        # one vertical, up to 4 metrics
        k = _tab(verticals[0])
        df = summaries.get(k) if k else None
        if df is None or "Metric" not in df.columns:
            return None
        months = [c for c in df.columns if c not in ("Metric", "FY Total")]
        for metric in metrics[:4]:
            vals = _row_vals(df, metric, months)
            if vals is not None:
                series[str(metric)] = vals
    if not series or not months:
        return None
    return pd.DataFrame(series, index=pd.Index(months, name="Month"))


def get_api_key() -> str | None:
    try:
        import streamlit as st
        if "gemini" in st.secrets:
            k = st.secrets["gemini"].get("api_key")
            if k:
                return k
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")


def is_configured() -> bool:
    return bool(get_api_key())


def build_data_context(summaries: dict | None) -> str:
    """FULL per-vertical snapshot — every metric of every month + FY Total —
    so the bot can answer and verify any calculation question."""
    if not summaries:
        return "LIVE DATA: (no report is loaded yet — the user hasn't run it.)"
    lines = ["LIVE DATA — the complete on-screen summary tables "
             "(one block per vertical; rows = metrics, columns = months + FY Total):"]
    for name, df in summaries.items():
        try:
            if "Metric" not in df.columns:
                continue
            lines.append(f"\n### {name}")
            lines.append(df.to_csv(index=False, float_format="%.2f").strip())
        except Exception:
            continue
    return "\n".join(lines)


def ask(question: str, summaries: dict | None = None, history: list | None = None,
        app_state: str | None = None,
        images: list[tuple[str, str]] | None = None) -> str:
    """`images` = list of (mime_type, base64_data) attached to THIS question —
    Gemini is multimodal, so Recy can read workbook screenshots etc."""
    key = get_api_key()
    if not key:
        return ("I'm not switched on yet — add a Gemini API key to `.streamlit/secrets.toml` "
                "under `[gemini] api_key = \"…\"` and I'll come alive. 🤖")
    prompt = APP_KNOWLEDGE + _load_guide() + "\n\n" + build_data_context(summaries)
    if app_state:
        prompt += "\n\n" + app_state
    if history:
        prompt += "\n\nRecent conversation:\n" + "\n".join(
            f"{h['role']}: {h['content']}" for h in history[-6:])
    if images:
        prompt += ("\n\nThe user attached the image(s) below with this question — "
                   "read them carefully and use them in your answer.")
    prompt += f"\n\nUser question: {question}\n\nAnswer as Recy:"
    parts = [{"text": prompt}]
    for _mime, _b64 in (images or []):
        parts.append({"inline_data": {"mime_type": _mime, "data": _b64}})
    payload = {"contents": [{"parts": parts}],
               "generationConfig": {"temperature": 0.5, "maxOutputTokens": 2000}}
    url = _ENDPOINT.format(model=MODEL, key=key)
    # connect quickly (5s) but allow the model plenty of time to answer (60s);
    # retry once on a timeout/connection blip since those are usually transient.
    last_err = None
    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=(5, 60))
            if resp.status_code in (500, 502, 503, 529):   # transient — retry once
                last_err = f"Gemini {resp.status_code}"
                import time as _t
                _t.sleep(2)
                continue
            if resp.status_code != 200:
                return f"(Gemini error {resp.status_code}: {resp.text[:150]})"
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
            continue          # transient — try once more
        except Exception as e:
            return f"(Couldn't reach Gemini: {e})"
    if isinstance(last_err, str) and "Gemini" in str(last_err):
        return ("Google's Gemini servers are overloaded right now (temporary spike "
                "on their side, not our app). Try again in a minute. 🤖")
    return ("Hmm, I couldn't reach Gemini just now — the connection timed out twice. "
            "That's usually a slow network or VPN/proxy hiccup, not the app. "
            "Give it another go in a moment. 🤖")
