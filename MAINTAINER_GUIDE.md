# Maintainer's Guide — Profitability Report Automation Engine

*For whoever runs, fixes, or extends this app after handover. No prior context assumed.*

---

## 1. What this is

A Streamlit app (`localhost:8502`) that turns Zoho MIS exports into per-vertical
profitability, receivables and payables reports, emails them to the team, and keeps
closed months frozen to the manually-signed-off figures.

**Daily routine (2 minutes):** run the app → Upload Files → drop the MIS export →
open Summary Report → review → Download / 📨 Send to team. That's it.

**Start the app:**
```
cd C:\...\AUTOMATION
streamlit run app.py --server.port 8502
```

---

## 2. The files — who does what

| File | Role | You'll edit it when… |
|---|---|---|
| `app.py` | UI, upload & auto-detection, page flow, Recy the assistant, email UI | changing screens, upload rules, Recy |
| `cleaning.py` | cleaning, bill split, invoice↔bill matching, CN/DN collapsing, Amazon cost chain | matching or note-handling rules change |
| `compute.py` | the ~107-column profitability engine, provisions, fake-DN buckets | provision rates/rules change |
| `reports.py` | summaries, MT/units display, receivables/payables/DSO/DPO, top-materials, combined Excel | summary metrics, workbook layout |
| `receivables.py` | receivable attribution: prefixes, legacy list, unused credits, Black Gold rule | new prefix, legacy customer changes |
| `frozen.py` | reads the manual "Profitability Report … till DD-MM-YYYY" files; freezes closed months | freeze behaviour |
| `mailer.py` | Gmail SMTP + the HTML email body (tables, Indian number format) | email look & feel |
| `database.py` | in-session store + persistent stores (older bills, Amazon YTD, No-DN list, month locks) | rarely |
| `.streamlit/secrets.toml` | **secrets** — Gemini API key, Gmail app password. NEVER commit/share | keys rotate |
| `persistent/` | on-disk stores that survive restarts | never edit by hand |

---

## 3. The rules of the system (where each lives)

| Rule | Where |
|---|---|
| Only Bill/CN/DN/AP/AR/INV sheets load (case/typo-tolerant); NO DN sheet replaces the exclusion list | `app.py` → `_CANON_ALIASES`, `_canon_sheet`, `_is_no_dn_sheet` |
| Aging sheets: header row auto-detected (title/total rows above it) | `app.py` → `_fix_title_header` |
| Provision rates: End Generator 4.55%, Plastic 2.5% | `compute.py` (search `0.0455`) |
| No provision when: blank shipment id, No-DN list, actual CN exists, void DN, fake-DN shipment | `compute.py` → `_prov_trig`, `FAKE_DN_SHIPMENTS` |
| CN/DN: sum ALL notes, show 2 (slot 2 aggregates rest); ≥95% CN = full reversal | `cleaning.py` → `_pivot_to_wide`, `_collapse_notes` |
| MP shipments excluded from all verticals except Re-Commerce (handles `36/MPPET/...`, `MP/AFR/...`) | `reports.py` → `_is_mp_ship` |
| IB(B2B) = SH-prefixed + has vendor invoice; rest = IB(Warehouse) (out of scope) | `reports.py` → `_ib_has_vendor_invoice` |
| Receivables: prefix → vertical, − legacy customers − unused credits; Black Gold ITAD → Re-Commerce | `receivables.py` → `PREFIX_TO_VERTICAL`, `LEGACY_CUSTOMERS`, `_attribute_vertical` |
| Payables by `vendor.CF.Vertical Name` | `reports.py` → `_ap_by_v` / workbook Payables sheet |
| Quantity displayed in MT (÷1000); IT AD & Re-Commerce count units | `reports.py` → `_summary_block(qty_in_mt)`, `frozen.py` → `UNIT_TABS` |
| Out-of-scope verticals hidden: ReWerse, IB(Warehouse) | `reports.py` → end of `summaries_by_category` |
| DSO/DPO: balance ÷ (sales/purchases × 1.18) × days; open month uses cutoff day | `reports.py` → `_summary_block`, `_working_days` |
| Metal displays as **End Generator** everywhere (tabs/sheets/emails); matching still accepts the old name | `reports.py` → `_canon_label` |
| Workbook detail sheet is named **Details**; 'Finance Up-Charge' invoice items get their own table below it | `reports.py` → `combined_workbook` |
| Enterprise **Custom Duty bills** (no bill in Zoho): entered on the Summary page, land in Details (Material "Custom Duty", Black Gold vendor) + FY-Total Purchases | `reports.py` → `inject_custom_duty`, store in `database.py` |
| Enterprise **Operational Cost overrides** per month (user-entered, persistent) | `app.py` → `_apply_ent_opcost`, store in `database.py` |
| **Re-Commerce (Without Samsung)** additive view: vendor-name subset, Apr–Jun frozen to signed-off figures, extra summary block + 'Details (No Samsung)' sheet | `reports.py` → `rc_without_samsung`, `frozen.py` → `RC_NOSAMSUNG_FROZEN` |
| Manual entries survive hosted restarts via GitHub write-through (`[github]` secrets: token/repo) | `database.py` → `_github_writethrough` |

---

## 4. The freeze (why old months never change)

- The MIS export only carries recent invoices, so **closed months come from the
  manual per-vertical files** — `Profitability Report of <vertical> till DD-MM-YYYY.xlsx`
  — sitting **in this folder**. The app auto-picks the newest per vertical.
- Only **fully-covered** months freeze (a "till 21-06" file freezes Apr & May, NOT
  its partial June). The **open month is always live** from the uploaded MIS.
- FY Total = frozen priors + live open month (additive rows); Receivable/Payable
  stay the **live as-of-today balance**.
- The Profitability Report sheet in every download carries the whole FY:
  closed-month rows from the manual files' Details sheets + live rows from the MIS.

**Monthly job for the team:** when a month closes, drop that month's final
"till DD-MM" per-vertical files into this folder. That's the entire maintenance.

---

## 5. Email

- Config in `.streamlit/secrets.toml` → `[email]` (sender, app_password, recipients,
  optional `recipients_by_vertical`). Gmail App Password: Google Account → Security →
  2-Step Verification → App passwords.
- **🧪 Send test to myself** sends the exact production mails only to the sender —
  always test after changing anything.
- Body = summary table + top-5 materials table, rebuilt from live data every send
  (`mailer.summary_html`, `reports.top_materials`).

## 6. Recy (the assistant)

- Gemini API key in secrets `[gemini] api_key` (free at aistudio.google.com).
- Its app knowledge lives in `assistant.py` → `APP_KNOWLEDGE` — **update this text
  when behaviour changes**, it's how Recy stays truthful.

---

## 7. Troubleshooting playbook (every incident we've actually hit)

| Symptom | Cause & fix |
|---|---|
| `KeyError` right after a new Zoho format | A column was renamed/moved in the export. Find the failing column in the traceback; the loaders use name-normalized lookup — add the new alias. (June-2026 format needed: header-row detection, `balance_fcy`.) |
| Changes to a `.py` file don't show | Streamlit reruns only `app.py`; imported modules need a **full restart** of `streamlit run`. |
| "Couldn't reach Gemini … timed out" | Network/VPN blip — retry. Persistent → check VPN/proxy to `generativelanguage.googleapis.com`. |
| Emails don't send / button disabled | `[email]` missing in secrets, or app password revoked → make a new one. `535 BadCredentials` = wrong password. |
| A vertical's month suddenly zero | Is it a closed month? Check the per-vertical "till" file for that month exists in the folder (partial files don't freeze). Live month → check the MIS actually contains those invoices. |
| Numbers look wrong vs manual | 1) Date coverage of the MIS. 2) Stray docs: DN-series invoice numbers (`…27DN…`), `OFF` orders, MP shipments — see §3. 3) Compare with the manual's own file using the frozen parser. |
| Status chip (top-right) shows more rows than the MIS has | Two files got uploaded in one session (uploads accumulate). Refresh the browser tab (clears session) and re-upload only the MIS. |
| Robot/chat looks stale | Hard-refresh the browser once (Ctrl+R). |

---

## 8. Changing common things (recipes)

- **Add a legacy (defaulter) customer:** `receivables.py` → `LEGACY_CUSTOMERS` — add the
  name (UPPERCASE substring) under the vertical.
- **New invoice prefix:** `receivables.py` → `PREFIX_TO_VERTICAL`.
- **Change a provision rate:** `compute.py` — search the current rate (e.g. `0.0455`).
- **New fake-DN shipment:** `compute.py` → `FAKE_DN_SHIPMENTS`.
- **Change email recipients:** secrets `[email] recipients`, or per-vertical under
  `[email.recipients_by_vertical]`.
- **New vertical:** needs prefix (receivables), AP vertical-tag mapping (`_ap_sub`),
  unit type (`UNIT_TABS` if unit-counted), and the manual file name keyword
  (`frozen._VERTICAL_MAP`).

After ANY change: restart, upload a known MIS, and compare one vertical against its
manual file before trusting the rest.

## 9. Using AI to maintain this (recommended)

This folder has a `CLAUDE.md` — open **Claude Code** in this directory and it knows
the entire architecture and rules. Effective asks look like:
- "The Zoho export renamed a column and Summary crashes — here's the traceback, fix the loader."
- "Add a new vertical called X with prefix MPX, MT-quantified, files named 'Report of X till …'."
- "Verify no rules are broken" (it knows the regression checks in CLAUDE.md).

**House rules for any change (human or AI):** never fabricate or date-shift data;
disclose any fill; closed months must never silently change; secrets stay out of
git; after each change, cross-check one vertical against the manual before rollout.
