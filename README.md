# Profitability Report Automation Engine

One upload. Every vertical. The full profitability picture, in seconds.

A Streamlit app that turns Recykal's daily **Zoho Books exports** into per-vertical
**profitability, receivables and payables reports** — replacing ~6 hours of manual
spreadsheet work per run with ~10 minutes, and emailing the results to the team.

---

## What it does

- **Ingest & auto-detect** — drop the Zoho MIS export (or individual files/ZIP);
  every sheet is recognised by its columns/name (only `Bill / CN / DN / AP / AR / INV`
  load; a `NO DN` sheet refreshes the provision-exclusion list automatically).
- **Clean → Match → Compute** — invoices matched to bills per shipment+item, credit
  and debit notes collapsed and netted, Re-Commerce costs traced through the Amazon
  chain, provisions applied by vertical rules → the full ~107-column report.
- **Freeze** — closed months are locked to the manually signed-off per-vertical
  report files; only the open month is computed live. Closed numbers never move.
- **Report** — per-vertical management summaries (Apr → current month + FY Total),
  one combined Excel per vertical (Summary · Receivables · Payables · full-FY
  line-by-line report), and one-click **email to the team** with the summary table
  and top-5 materials inline.
- **Recy 🤖** — an in-app assistant (Google Gemini) that knows the app and the live
  numbers, with a face.

**In scope (7 verticals):** End Generator (Metal), Plastic, Re-Commerce, ITAD, AFR,
M4, Enterprise / IB(B2B). ReWerse and the Processing Center are handled manually.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8502
```

Then open `http://localhost:8502`, upload the MIS export on **Upload Files**, and
read the **Summary Report** page.

### Secrets (never committed)

Copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml` and fill in:

```toml
[gemini]
api_key = "..."          # for Recy — free key at aistudio.google.com/app/apikey

[email]
sender = "you@company.com"
app_password = "..."     # Gmail App Password (Google Account → Security → App passwords)
recipients = ["team@company.com"]
```

### Data files (never committed)

The app expects, in its working folder:
- the day's **MIS export** (uploaded through the UI),
- the manual **`Profitability Report of <vertical> till DD-MM-YYYY.xlsx`** files —
  the source of frozen closed months (newest per vertical is picked automatically),
- `persistent/` stores (historical bills, Amazon YTD, exclusion list, accumulated
  details) — built up through the UI, survive restarts.

## Module map

| File | Role |
|---|---|
| `app.py` | UI, upload auto-detection, pipeline orchestration, Recy, email UI |
| `cleaning.py` | cleaning, bill split, invoice↔bill matching, CN/DN collapsing, Amazon cost chain |
| `compute.py` | the ~107-column profitability engine, provisions |
| `reports.py` | summaries, MT/units display, DSO/DPO, top materials, combined workbook |
| `receivables.py` | receivable attribution (prefixes, legacy, unused credits) |
| `frozen.py` | closed-month freeze from the manual report files |
| `mailer.py` | Gmail SMTP + HTML report email |
| `database.py` | session store + persistent stores |

## Documentation

- **`MAINTAINER_GUIDE.md`** — rule map, troubleshooting playbook, change recipes. Start here.
- **`USER_SOP.md`** — the daily operator routine.
- **`AUTOMATION_REPORT.md`** — what/why, architecture, business logic.
- **`CLAUDE.md`** — context for AI-assisted maintenance (open Claude Code in this folder).

## House rules

- Never fabricate, estimate, or date-shift data — zeros must be honest.
- Closed (frozen) months must never silently change.
- Secrets and financial data files stay out of git (`.gitignore` is whitelist-mode).
