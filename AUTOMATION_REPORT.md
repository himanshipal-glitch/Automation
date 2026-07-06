# The Profitability Report Automation Engine
### One upload. Every vertical. The full profitability picture, in seconds.

**Recykal · Product & Technical Documentation**

---

## 1. Why this exists

Recykal's profitability lived in spreadsheets. Every vertical's sales, purchases, credit and debit notes, provisions and margins were stitched together **by hand** from Zoho exports that don't naturally line up. It was already run often — about **10–11 times a month** (roughly twice a week, every ~3 days) — at around **6 hours per run**, or nearly **66 hours of manual effort a month**. It was slow, broke easily, and hard to keep consistent.

The engine cuts each run from ~6 hours to **~10 minutes**. Fast enough to run **every single day** — ~10 minutes × 30 days ≈ **5 hours a month** — turning ~66 hours of effort into ~5, while *increasing* the cadence to a **daily** profitability view. Dramatically more **time-efficient and data-efficient**: fresher numbers, a fraction of the effort.

The **Profitability Report Automation Engine** ends that. It ingests the raw Zoho exports, applies — deterministically — the exact judgement an experienced analyst would apply, and produces the **full ~106-column profitability report** and the **per-vertical management summary** in seconds. Same inputs, same output, every time.

This is not a spreadsheet with macros. It is a **data engine**: a typed pipeline that cleans, matches, costs, provisions and rolls up thousands of transactions into decision-ready numbers.

---

## 2. The problem it solves

Profitability is deceptively hard because the source data is fragmented and doesn't join cleanly:

- **Sales (Invoices)** and **Purchases (Bills)** live in separate exports and must be matched **line-by-line, per shipment** — one sale can span several purchase lines and vice-versa.
- **Credit Notes** and **Debit Notes** arrive in their own files, repeat their totals across line items, sometimes run to three or more notes per shipment, and must be attached to the right shipment, de-duplicated, and netted with the correct GST treatment.
- **Re-Commerce** (refurbished electronics sold via Amazon) frequently has **no direct purchase bill** — its cost has to be traced through a chain of Amazon invoice references back to historical bills.
- **Provisions** and **operational costs** are *estimates* the analyst computes from yet more sources, on rules that live only in their head.

Done by hand, this is slow, fragile, and impossible to scale across seven verticals every month.

---

## 3. The product

A **Recykal-themed Streamlit web application** (`localhost:8502`) is the entire experience:

1. **Upload** the day's Zoho exports (or a single ZIP) — the engine recognises each file by its structure.
2. Click **Merge & Compute**.
3. Read and download the **per-vertical summaries** and the **receivables workbook**.

Files that don't change day to day — the **historical-bills ledger**, the **Amazon × Recykal YTD** link, and the **provision-exclusion list** — are stored **persistently**, so they're uploaded once and reused automatically.

**Scope — 7 verticals:** End Generator, Plastic, Re-Commerce, ITAD, AFR, M4, and Enterprise. *(ReWerse and the Processing Center are handled separately and are outside this engine.)*

---

## 4. Architecture

A clean, modular Python/pandas engine behind the Streamlit UI:

| Module | Role |
|---|---|
| `app.py` | UI, file auto-detection & ingest, pipeline orchestration, downloads |
| `database.py` | In-session data store + the three persistent stores; column normalisation |
| `cleaning.py` | Cleaning, bill-split, the merge pipeline, CN/DN collapsing, cost-fill |
| `compute.py` | The ~106-column profitability formula engine |
| `reports.py` | Per-vertical summaries, the Enterprise split, receivables/payables, DSO/DPO |
| `receivables.py` | The receivables engine (attribution, legacy, unused credits) |

**Data model.** Uploaded data lives in session memory keyed by dataset and stage (`raw → cleaned → merged → profitability`). Reference data (historical bills, Amazon YTD, exclusion list) is persisted on disk and survives restarts. The design is **deterministic**: identical inputs always yield identical outputs.

**Flow:**
```
Zoho exports ─▶ 1. Ingest & auto-detect ─▶ 2. Clean (+ split purchase/logistics)
           ─▶ 3. Match (Invoice◀▶Bill◀▶CN◀▶DN + cost-fill)
           ─▶ 4. Compute & Report (106 cols → per-vertical summaries)
```

---

## 5. The pipeline — four stages

**1 · Ingest.** The Zoho exports are uploaded and **auto-detected** by their structure, then loaded into the engine (with the persistent stores — historical bills, Amazon YTD, exclusion list — reused automatically).

**2 · Clean.** Normalise every sheet, standardise column names, drop voids/drafts, collapse each credit/debit note to **one row per note**, and **split** each bill into material-purchase vs logistics/transport lines.

**3 · Match.** Match each **invoice line to its bill** on **shipment + item**; attach **credit and debit notes**; and, where a purchase is missing, **trace Re-Commerce cost** through the Amazon chain or the historical-bills ledger.

**4 · Compute & Report.** Build the **~106-column report** (sales, purchases, CN/DN, provisions, logistics, operational cost, margins, per-kg economics, receivables, payables, DSO/DPO), then roll it up into the **per-vertical management summary** and the downloadable **receivables workbook**.

---

## 6. The intelligence inside — the business logic

This is the heart of the engine: an analyst's judgement, encoded as deterministic rules.

### 6.1 Invoice ↔ Bill matching
Each sale line is matched to its purchase on **shipment ID + item**. Many-to-one and one-to-many relationships are resolved by aggregating the counterpart lines, so a multi-item invoice or a split bill still nets correctly.

### 6.2 Credit & Debit Notes
- **Sum all notes** per shipment — a shipment may carry several; every distinct note is included (two are displayed, slot 2 aggregating the rest, so no value is lost).
- **Document-level de-duplication** — a note's total repeats on each line item; it is counted once.
- **Full reversals** — when a credit note cancels ≥95% of a sale, the deal is treated as reversed: revenue nets to zero, and if goods went back to the vendor, purchase nets to zero too.
- **Void debit notes** — a voided DN is not a valid DN; such shipments are excluded from provisioning.

### 6.3 Provisions (estimated future notes)
Provisions estimate credit/debit notes not yet raised. Rates are per vertical (**End Generator 4.55%, Plastic 2.5%**, ReWerse 2.5% where applicable). A provision applies to a shipment **only when it isn't already covered by an actual credit note** and isn't on the uploaded **exclusion list**.
`Net Revenue = Sales − Actual CN − Provision CN.`

### 6.4 Operational cost
Operational cost is the vertical's **overhead cost** — a distinct line, separate from the purchase bills **and** from the CN/DN provisions above. Ordinary service charges — *Transport Charge, Manpower Services, Hydra charges* — are booked to **Purchases** (where they belong), not here. The operational-cost figure itself is derived two ways:
- **Variable (time-based):** service charges with no shipment link, spread across the month (÷30 × days elapsed).
- **Fixed (tonnage-based):** the prior billed month's service rate carried forward and applied to the current month's tonnes sold — the rate persists until a new bill lands.

For **AFR**, the marketplace-purchase service bills are captured (CFSO-blank, not voided) so operational cost lands where the business books it. *(Non-material lines like Finance Up-Charge and Hydra remain in the vertical's revenue but take no CN/DN provision.)*

### 6.5 Re-Commerce — the Amazon cost chain
Re-Commerce sales often have no direct bill. Cost is traced through a chain:
`Recykal Invoice No. → Amazon YTD "Invoice ID" → Amazon "Invoice no." → Historical Bill Number + item → cost` (fallback: historical bill by shipment + item). Every costed row is tagged with its **Cost Source** so its origin is traceable.

### 6.6 Resold items (End Generator)
When goods returned to a seller are re-sold under a new shipment, **both legs are kept and flagged**, with the resale carrying the **original purchase cost** — no double-counting.

### 6.7 Receivables
`Net Receivable = Open balance − Legacy − Unused credits`, per vertical.
- **Attribution by invoice prefix** — `MPMET → End Generator`, `MPPET → Plastic`, `MPREC → Re-Commerce`, `MITAD → ITAD`, `AFR → AFR`, `MPM4 → M4`, `IB/MPIB → Enterprise`.
- **Cross-vertical customer rule** — an ITAD-prefixed invoice billed to a Re-Commerce customer (Black Gold) is booked to Re-Commerce.
- **Legacy** — a maintained list of long-overdue defaulter accounts per vertical, whose balances are excluded from the operational receivable.
- **Unused credits** — customer advances, netted off once per customer.
- **Enterprise** — because B2B and warehouse share invoice prefixes, the Enterprise receivable counts only the invoices that appear in the Enterprise (B2B) output, isolating true B2B.

### 6.8 Payables
Vendor bill numbers carry no vertical code, so payables are attributed **by the vendor's vertical tag** (`vendor.CF.Vertical Name`) and computed per vertical for every period.

### 6.9 Working-capital metrics
`DSO = Receivable / (Sales × 1.18) × days` · `DPO = Payable / (Purchases × 1.18) × days` · `Working-Capital Days = DSO − DPO`.

### 6.10 Vertical structure
Institutional Business is split into **Enterprise (B2B)** — SH-prefixed shipments backed by a vendor invoice — and the **Processing Center (warehouse)**, which is out of scope. Warehouse (MP) movements are held out of the main verticals.

---

## 7. What makes it robust

- **Deterministic** — identical inputs always produce identical outputs; no hand-built drift between months.
- **Traceable** — every costed row carries its source (Cost Source tag), and every rule is explicit in code, not tribal knowledge.
- **Self-updating by design** — the provision logic is built to roll forward as each new month's data lands.
- **Protected verticals** — signed-off verticals are guarded so later changes can't silently move their numbers.
- **Scales effortlessly** — thousands of rows across seven verticals process in seconds; volume doesn't slow it or degrade quality.

---

## 8. Roadmap — what's next

- **Always-On Dashboard** — a live profitability view; no manual trigger required.
- **Direct Zoho Integration** — eliminate file uploads; data flows in automatically.
- **Real-Time Exception Alerts** — automatic flags for anomalies, mismatches, or threshold breaches.
- **Scheduled Hands-Free Runs** — reports generated and delivered on a fixed close-cycle schedule.
- **AI Chatbot** — ask questions in plain language and get instant, data-backed answers.

---

## 9. Glossary

| Term | Meaning |
|---|---|
| **CN / DN** | Credit Note (to customer) / Debit Note (from vendor) — sales & purchase adjustments |
| **CFSO Number** | Shipment / sales-order ID linking invoices and bills |
| **Provision** | An estimated future **credit/debit note**, booked before the actual note arrives |
| **Full reversal** | A credit note that cancels essentially the entire sale |
| **Net Revenue** | Sales − Credit Notes (actual + provisions) |
| **Operational Cost** | A vertical's overhead cost (variable + fixed), distinct from purchase/service bills and from CN/DN provisions |
| **MT** | Metric tonnes — the quantity basis for the fixed operational-cost provision |
| **Cost Source** | The provenance tag showing how a row's cost was derived |

---

*Built as a Streamlit application (Python / pandas). Inputs: standard Zoho Books exports. Outputs: per-vertical management summaries, the full profitability report, and a receivables workbook — all downloadable as Excel / CSV.*
