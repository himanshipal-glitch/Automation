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

SCOPE — 7 verticals automated: End Generator (a.k.a. Metal in the tool), Plastic,
Re-Commerce, ITAD, AFR, M4, Enterprise (IB B2B). OUT OF SCOPE: ReWerse and the
Processing Center (IB Warehouse) — handled manually.

DOWNLOADS: each vertical (and "All") downloads as ONE Excel with 4 sheets —
Summary, Receivables, Payables, Profitability Report. There's also a "Send to team"
button that emails the report (optionally one email per vertical).

If a question is about specific numbers, use the LIVE DATA snapshot provided.
If you don't know something, say so briefly. Never invent numbers.

STYLE: be genuinely helpful and COMPLETE — never stop mid-sentence. Keep it tight
(usually 2–4 sentences, or short bullets). Lead with the answer, then a crisp reason.
Warm and a little playful, but don't waste words. Use at most one emoji.
"""


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
    prompt = APP_KNOWLEDGE + "\n\n" + build_data_context(summaries)
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
            if resp.status_code != 200:
                return f"(Gemini error {resp.status_code}: {resp.text[:150]})"
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
            continue          # transient — try once more
        except Exception as e:
            return f"(Couldn't reach Gemini: {e})"
    return ("Hmm, I couldn't reach Gemini just now — the connection timed out twice. "
            "That's usually a slow network or VPN/proxy hiccup, not the app. "
            "Give it another go in a moment. 🤖")
