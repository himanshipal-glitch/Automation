# Profitability Automation — How to Run It
### A simple, step-by-step guide

This tool turns the daily **Zoho reports** into ready-made **profitability, receivables and payables** for every vertical — automatically. You download a few files, upload them, click once, and the reports come out.

**Open the app:** in your browser go to **http://localhost:8502**

---

## The daily routine — who does what

> **Zoho reports refresh every day.** Each working day, the assigned person:
> 1. Downloads the latest **6 reports** from Zoho (list below),
> 2. Uploads them into the app,
> 3. Clicks **Merge & Compute**, and
> 4. Downloads the updated **Summary**.
>
> That's it — the app does all the cleaning, matching and calculations in between. Plan ~5 minutes a day.

---

## Part 1 — Download these 6 reports from Zoho

Export each one as an **Excel (.xlsx)** file. **Don't rename the columns** — leave them exactly as Zoho gives them.

| Report | Where in Zoho | Gives us |
|---|---|---|
| **Invoice** | Sales → Invoices → Export | Sales (revenue & quantity) |
| **Bill** | Purchases → Bills → Export | Purchase cost + transport |
| **Credit Note** | Sales → Credit Notes → Export | Sales returns |
| **Vendor Credits** | Purchases → Vendor Credits → Export | Purchase returns |
| **AR Ageing Details** (by Invoice Due Date) | Reports → Receivables | Receivables (money owed to us) |
| **AP Ageing Details** (by Bill Due Date) | Reports → Payables | Payables (money we owe) |

> **Tip:** You can drag all 6 files in together, or zip them into one `.zip` and drop that. The app recognises each file automatically — the file names don't need to be exact.

---

## Part 2 — Run the app (4 steps)

**Step 1 · Upload Files** — Drag the 6 files (or the ZIP) into the upload box. Check the sidebar shows them loaded.

**Step 2 · Merge & Compute** — Click the button. Wait for *"Pipeline complete."* This is where the app cleans, matches invoices to bills, and builds every number.

**Step 3 · Summary Report** — Your main output: the per-vertical summary (sales, purchases, margins, receivables, payables, DSO/DPO). Download per-vertical CSV, all-summaries Excel, or the Receivables workbook.

**Step 4 · Management Reports** — The detailed view: the full line-by-line report and supplier/buyer/material/monthly/weekly breakdowns. Download whatever you need.

*(There's also a **Cleaning** page if you ever want to review how each file was tidied up — but you don't need it for the normal run.)*

---

## Set-once reference data

These are already loaded and **stay loaded** — you only refresh them when a new file is shared with you.

| Reference data | What it's for | Update it when… |
|---|---|---|
| **Older-bills store** | Fills in costs for older/missing purchases | a new historical-bills file is shared |
| **Amazon × Recykal YTD** | Costs Re-Commerce sales | a new YTD file is shared |
| **Exclusion list** | Shipments that should skip the provision | the list changes |

---

## Good to know

- **Cut-off dates:** If a shipment is dated *after* the manual report's cut-off (say the 15th vs a 14th), it will show in the app but not the manual. That's a timing difference, **not a mistake**.
- **After the app is restarted**, the uploaded files are cleared — just **re-upload and re-run Merge & Compute**.
- **Keep Zoho's original columns.** If a column is renamed, the app may not recognise the file.
- **Receivables / Payables** are pulled from the AR / AP ageing reports and split per vertical automatically.
- **Scope — 7 verticals:** End Generator, Plastic, Re-Commerce, ITAD, AFR, M4, and Enterprise. **ReWerse and the Processing Center are out of scope** — they're handled manually, not by this tool.

---

## If something looks off

| You see… | Do this |
|---|---|
| *"No raw data found for: …"* | That report wasn't uploaded — go to **Upload Files** and add it. |
| Numbers look old / blank | The app was restarted — **re-upload** the files and re-run **Merge & Compute**. |
| A file didn't get picked up | Make sure it's the **original Zoho export** with unchanged columns, then re-upload. |
| The page shows an error | Note the message and let the tech team know — a restart usually clears it. |

---

*Questions or anything unclear? Reach out to the team that owns the tool — they can walk you through it.*
