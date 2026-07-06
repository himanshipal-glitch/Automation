# Profitability Report Automation Engine — Recykal

Streamlit app (port 8502: `streamlit run app.py --server.port 8502`) that converts
Zoho MIS exports into per-vertical profitability/receivables/payables reports,
freezes closed months to the manually signed-off figures, and emails the team.

Read `MAINTAINER_GUIDE.md` for the full rule map, troubleshooting playbook and
change recipes. High-level module map:

- `app.py` — UI/pages, upload auto-detection (`_canon_sheet`: only Bill/CN/DN/AP/AR/INV
  load, case/typo-tolerant; `NO DN` sheet replaces the no-DN store; `_fix_title_header`
  finds the real header under Zoho's title/total rows), Recy assistant, email UI.
- `cleaning.py` — clean/split/match pipeline, CN/DN collapsing (sum ALL notes, display 2),
  ≥95% CN = full reversal, Amazon cost chain for Re-Commerce.
- `compute.py` — 107-col profitability. Provisions: EG 4.55%, Plastic 2.5%; suppressed for
  blank shipment, no-DN list, actual CN present, void DN, `FAKE_DN_SHIPMENTS`.
- `reports.py` — summaries (`SUMMARY_METRICS` rows × months Apr→cutoff + FY Total),
  `_is_mp_ship` (MP shipments excluded everywhere except Re-Commerce; handles
  `36/MPPET/...` numeric prefixes), IB(B2B)=SH+vendor-invoice, quantity displayed in MT
  (÷1000) except `IT AD`/`Re-Commerce` (units), `top_materials`, `combined_workbook`
  (4 sheets; Profitability Report sheet = frozen closed-month detail + live MIS rows).
  ReWerse & IB(Warehouse) are OUT OF SCOPE (popped from summaries).
- `receivables.py` — prefix→vertical attribution, `LEGACY_CUSTOMERS` excluded, unused
  credits netted per customer, Black Gold ITAD→Re-Commerce.
- `frozen.py` — reads `Profitability Report of <vertical> till DD-MM-YYYY.xlsx` files in
  THIS folder (newest per vertical); freezes only FULLY covered months (a till-21-06 file
  freezes Apr/May, not partial June); open month always live; FY Total = frozen priors +
  live open month; Receivable/Payable stay live balances; `frozen_details` supplies
  closed-month line rows for the workbook.
- `mailer.py` — Gmail SMTP (secrets `[email]`), HTML body with Indian number grouping.
- `database.py` — session store + persistent stores under `persistent/`.

## Hard rules — do not violate
- NEVER fabricate, estimate, or date-shift data; disclose any fill. Zeros must be honest.
- Closed (frozen) months must never silently change.
- Secrets live only in `.streamlit/secrets.toml` (gitignored). Never hardcode credentials.
- Any push to GitHub: code only, no financial data files, and only with explicit user OK.
- After changing report logic, cross-check one vertical against its manual file.

## Gotchas
- Streamlit reruns only re-execute `app.py`; edits to imported modules need a full
  `streamlit run` restart.
- Uploads accumulate within a session — a browser refresh clears the session store.
- Zoho exports mutate: columns get renamed (`balance` → `balance_fcy`), header rows move,
  SO numbers grow prefixes (`36/MPPET/...`). Loaders use normalized-name lookup — extend
  aliases rather than hardcoding positions.
- The MIS export only contains recent months; Apr/May detail exists only in the manual
  per-vertical files (that's why the freeze exists).
- Windows console: use `python -X utf8` when scripts print ₹/emoji.

## Verification
Regression checks that must hold (run the pipeline headless on a known MIS): provisions
zero on blank-shipment/no-DN-listed/actual-CN shipments; fake-DN rows bucketed; provision
rates exact; Black Gold → Re-Commerce; Net ≤ Gross receivables; frozen overlay leaves the
open month byte-identical; frozen months equal the manual files' Summary values.
