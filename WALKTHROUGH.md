# Profitability Automation — Visual Walkthrough
### A guided tour of the tool, screen by screen

This walkthrough shows the tool exactly as it appears in the browser, page by page, with what each screen does and what to do there. Open the app at **http://localhost:8502**. The green menu on the left is how you move between pages.

---

## The layout

Every screen has the same shape:
- **Left sidebar (green):** the menu — `Upload Files`, `View Databases`, `Cleaning`, `Merge & Compute`, `Summary Report`, `Management Reports`. It also shows how much data is currently loaded.
- **Main area (right):** the content of the page you're on.

You'll normally use just three pages each day: **Upload Files → Merge & Compute → Summary Report.**

---

## 1. Upload Files

**This is where the day starts.** You drop in the Zoho exports and the tool sorts them automatically.

![Upload Files](walkthrough_shots/01_upload.png)

**What you see:**
- A **drag-and-drop box** — drop the day's Zoho files (or one ZIP) here. The tool reads each file's columns and figures out on its own whether it's Invoice, Bill, Credit Note, Vendor Credit, AR or AP — filenames don't need to be exact.
- **Three permanent stores** (the expandable bars at the top) that stay loaded across sessions, so you don't re-upload them daily:
  - **Older-bills store** — historical purchase costs used to fill in missing/older bills.
  - **Amazon × Recykal YTD** — the link used to cost Re-Commerce sales.
  - **CF.DN exclusion list** — shipments that should skip the provision.
- **Expected datasets** — a checklist of the files the tool is looking for.

**What to do:** drag in the 6 daily reports (plus the Black Gold service-charge bills for ReWerse), and confirm they're recognised.

---

## 2. View Databases

**A quick check that everything loaded correctly.**

![View Databases](walkthrough_shots/02_view_databases.png)

**What you see:** a tile per dataset showing the row count now in memory (e.g. AP 1,349 · AR 1,313 · Bill 6,123 · CN 315 · DN 1,150 · Invoice 2,045). Below, you can pick any dataset and preview the actual rows.

**What to do:** glance at the tiles to confirm each file came through with a sensible number of rows. (Optional — you can skip straight to Merge & Compute.)

---

## 3. Cleaning

**Shows how each file was tidied up before use.** You don't need to change anything here — it's for transparency.

![Cleaning](walkthrough_shots/03_cleaning.png)

**What you see:** for each dataset (Invoice, Bill, CN, DN) the cleaning rules applied — e.g. dropping Void/Pending notes, standardising columns, and removing duplicate lines. This is what keeps the numbers consistent every month.

---

## 4. Merge & Compute

**The engine room — one click turns the raw files into the full profitability report.**

![Merge & Compute](walkthrough_shots/04_merge_compute.png)

**What you see:**
- **"How the data is merged"** — the steps the tool follows: match each sale invoice to its purchase bill (by shipment + item), then attach Credit Notes and Debit Notes, then run the calculations.
- **Row counts** for each input (Invoices, Bill purchases, Bill logistics, CN, DN).
- **"Pipeline complete — 1,495 rows · 107 columns"** — confirmation the report was built.
- **Missing-bill costing note** — e.g. *47 Re-Commerce rows costed from the Amazon chain; 23 extra bills appended.*
- **Key metrics** — Total rows, Matched (bill found), Unmatched, Total Margin.

**What to do:** open this page (it runs automatically) and wait for *"Pipeline complete."* That's it — every number is now built.

---

## 5. Summary Report

**Your main output — the management summary for every vertical.**

![Summary Report](walkthrough_shots/05_summary.png)

**What you see:**
- **Tabs across the top** — one per vertical (All Categories, Metal, Plastic, ReWerse, Re-Commerce, ITAD, IB(B2B), IB(Warehouse), AFR, M4). Click a tab to switch vertical.
- **The summary table** — months across the columns (Apr / May / Jun … + FY Total) and the key metrics down the side: **Quantity, Sales, Purchases, Gross & Net Margin, Operational Cost, Revenue/Purchase per Kg, Receivable, DSO, Payable, DPO, Working-Capital days, Credit/Debit Notes.**
- **Download buttons** at the bottom — per-vertical CSV, **all summaries (Excel)**, and the **Receivables workbook (one sheet per vertical)**.

**What to do:** review each vertical's numbers, and download the Excel/CSV you need to share.

---

## 6. Management Reports

**The detailed, line-by-line view behind the summary.**

![Management Reports](walkthrough_shots/06_management.png)

**What you see:** the full profitability report (every shipment, all 100+ columns) plus extra breakdowns — by supplier, buyer, material, and by month/week. Everything is downloadable.

**What to do:** use this when you need to drill into a specific number — e.g. *which shipments* make up a vertical's margin, or a supplier-level view.

---

## The daily routine in one line

> **Upload Files** (drop the day's Zoho exports) → **Merge & Compute** (one click, wait for "Pipeline complete") → **Summary Report** (review & download). About 5 minutes.

If the app is ever restarted, the uploaded files are cleared — just re-upload and run Merge & Compute again. The three permanent stores stay loaded.
