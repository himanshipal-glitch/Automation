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

PAGES (left sidebar): Upload Files, View Databases, Cleaning, Summary Report,
Management Reports. Daily flow: upload the Zoho files → open Summary Report (it
auto-runs the pipeline) → review & download / email.

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
Zoho's rolling export stay in the Profitability Report sheet, and a late CN/DN
that reappears with its shipment replaces the old row with the newest state.

DOWNLOADS: each vertical (and "All") downloads as ONE Excel with 4 sheets —
Summary, Receivables, Payables, Profitability Report (whole FY: closed-month rows
from the manual files' Details sheets + live rows from the accumulated store; no
month is double-counted, so summing the sheet cross-checks the FY Total).

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
    """Feed the maintainer guide into Recy's context so its knowledge tracks the
    docs — update MAINTAINER_GUIDE.md and Recy learns it on the next question."""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MAINTAINER_GUIDE.md")
        with open(p, encoding="utf-8") as f:
            return ("\n\nREFERENCE — the project's maintainer guide (rule map, "
                    "troubleshooting playbook, change recipes):\n" + f.read())
    except Exception:
        return ""


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
    """Compact per-vertical snapshot (FY figures) so the bot can answer data Qs."""
    if not summaries:
        return "LIVE DATA: (no report is loaded yet — the user hasn't run it.)"
    want = {"Sales", "Purchases", "Gross Margin", "Net Margin", "Operational Cost",
            "Receivables (exl Legacy)", "DSO (Days)", "Payable", "DPO (Days)"}
    lines = ["LIVE DATA — FY totals per vertical:"]
    for name, df in summaries.items():
        try:
            if "Metric" not in df.columns or "FY Total" not in df.columns:
                continue
            picks = []
            for _, r in df.iterrows():
                m = str(r["Metric"])
                if m in want:
                    v = r["FY Total"]
                    picks.append(f"{m}={v:,.0f}" if isinstance(v, (int, float)) else f"{m}={v}")
            if picks:
                lines.append(f"• {name}: " + ", ".join(picks))
        except Exception:
            continue
    return "\n".join(lines)


def ask(question: str, summaries: dict | None = None, history: list | None = None,
        app_state: str | None = None) -> str:
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
    prompt += f"\n\nUser question: {question}\n\nAnswer as Recy:"
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": 0.5, "maxOutputTokens": 1400}}
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
