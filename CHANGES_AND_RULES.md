# Changes & Rules Log

Running record of every change made to this app outside the `app.py` build tag,
with the **rule** each change encodes and the **evidence** it was verified against.

Append newest at the top. Never delete an entry — supersede it.

House rules that govern everything below (from `CLAUDE.md`):
never fabricate, estimate or date-shift data · closed (frozen) months must never
silently change · secrets stay out of git · after any change, cross-check one
vertical against its signed-off manual file before rollout.

---

## 2026-07-30 · CORRECTION — prior-FY Details exclusion reverted (kept for Last Year only)

The prior-FY change below (`2cc02ba`) removed shipments from Details **by shipment
id**. That was WRONG: a shipment created before April but INVOICED in the current
FY is genuine current-year revenue.

Caught by reconciling the Enterprise Details against its manual: the automated
report was short by exactly one shipment, **`SH032630011`** (Sales 15,054 /
Purchases 13,366 — the entire FY-total gap). Its id is Mar-2026 (prior-FY) but its
invoice date is **01-Apr-2026 (current FY)**, and the manual keeps it. A sweep then
showed **all 14** shipments the id-based rule dropped were invoiced in the current
FY — so the exclusion was removing real current-year revenue across Enterprise,
Metal, Plastic and ReWerse.

**Reverted:** `drop_prior_fy` removed from both the summary path (app.py) and
`combined_workbook` (Details), and the function deleted. **Details/summary are back
to including every current-FY-invoiced shipment** — no changes to Details, per the
owner.

**Kept:** the shipment-id prior-FY test (`_ship_prior_fy` / `_current_fy_start_year`)
still drives the "Last year's" sheet's `_is_left` — that is its correct purpose:
identifying CNs/DNs that pertain to last financial year's shipments. Verified
unchanged: End Generator DN 37 notes / 2,435,712.16.

**Correction to an earlier claim:** the Plastic Jun-26 negative was NOT genuinely
fixed by dropping `SH012631015` — that shipment is invoiced 15-Jun-2026 (current FY)
and should stay. The negative has a different root cause (its credit-note handling),
still open.

---

## 2026-07-30 · Prior-FY shipments routed to the Last Year sheet

Previous-financial-year shipments were appearing in the current Details/summary
(finance flagged Plastic `SH012631015`, `SH022606031`, …). They belong to last year.

### The rule

A shipment id is `SH` + MM + YY + sequence (e.g. `SH032630013` = Mar-2026). The
Indian FY starts **1 April**, so a shipment whose own month/year predates this
April is **prior-FY**. Confirmed against the manuals, whose Details sheets carry
**zero** prior-FY rows (End Generator 56 current / 0 prior; Plastic 3 / 0).

`reports._ship_prior_fy(id, fy_start_year)` + `_current_fy_start_year(df)` (derived
from the latest invoice date, so it rolls forward automatically — nothing
hardcoded to 2026). Unparseable ids (`MP/…`, `/OFF/…`, blank) count as CURRENT and
are never auto-routed.

### Two coordinated changes

1. **Details / summary / FY** — `reports.drop_prior_fy(df)` removes prior-FY line
   rows, applied in BOTH places (same rule as `drop_manual_exclusions`):
   `app.py` on `profit_df` (summary + FY), and `combined_workbook` on `_rep`
   (Details sheet, rebuilt from the accumulated store).
2. **Last Year sheet** — its selection changed from "shipment NOT in current
   Details" to "**every referenced shipment is prior-FY**". The old test missed
   prior-FY shipments that had received a current-FY invoice (so were in Details);
   the new one matches the manual directly.

### Why the residual maths makes this a FIX, not a risk

All 14 prior-FY rows in this MIS fall in Apr–Jun (frozen months), none in July. The
open month is `pre-freeze-FY − Σ frozen priors`; the manual's frozen priors exclude
these rows while our live FY included them, so they were being **dumped into July**,
inflating it. Removing them corrects the open month toward the manual.

### Verification

- **End Generator frozen months still tie to the manual** — freeze untouched.
- End Generator July/FY **unchanged** by the exclusion (its 4 prior-FY Metal rows
  net ~0), so the existing reconciliation is not disturbed.
- **Plastic June Sales −34,937 → 88,042** — `SH012631015` (Jan-26, carrying ~55k of
  CN against 20k of invoice) left Details, removing the negative drag. (The residual
  88,042 is the DRS order, which the manual-exclusion list also removes.)
- **Last Year sheet still ties**: End Generator DN 37 notes / 2,435,712.16, all four
  tables intact.
- Workbook Details sheet: **0 prior-FY rows** (both application points confirmed).

### Note — the 3 no-reference VC notes

`36/MET/27VC00106/109/110` (which the manual lists) have **`Referenceno = NaN`** in
the raw MIS — the shipment link exists only in the manual, added by hand. So neither
the old nor the new rule can attribute them; they remain manual-only, alongside the
5 legacy `DN`-series rows. Engine + those 8 manual-only rows = the manual's total.

---

## 2026-07-30 · Summary: absolute "Transportation Charges" row (above Operational Cost)

The summary showed only *Transportation Charges Per Kg*; the manual also has an
absolute ₹ row above Operational Cost (e.g. AFR Apr-26 = 54,711). Added it.

### How the value is derived — and why it is exact

Per column: **Transportation Charges = Gross Margin − Net Margin − Operational
Cost**. That is the identity by which Net Margin is defined in `_summary_block`
(`nm = gm − tc − oc`), so it holds for live, open and frozen months alike. For a
frozen month GM/NM/OC are the signed-off manual values, so GM − NM − OC recovers the
manual's own transport figure — AFR Apr-26 came out to 54,711 exactly.

The engine already computed `tc` (Σ Logistics_Cost + AFR blank-CFSO transport
override) but only emitted the per-kg form. This surfaces the absolute value; it
does not recompute anything.

### Why it is done as a LAST, derived step — NOT a new SUMMARY_METRICS entry

Inserting into `SUMMARY_METRICS` at position 5 would renumber ~50 hardcoded row
indices across `_summary_block`, the FY/split splice, the open-month rebalance,
`_metric_idx`, `_round_cell` (`_RATIO2`/`_COUNTS`), `frozen._recompute_fy`
(g(5),g(6),g(19),g(23),…) and `app._apply_ent_opcost` (g/iat 5,6,7). A single missed
shift silently corrupts a frozen month — the #1 hard rule. So the freeze layout is
left at 29 rows, entirely untouched, and `reports.insert_transport_row(df)` adds the
row as the FINAL step, AFTER apply_frozen and the Enterprise op-cost override.

Applied once in `app.py` to every summary in the dict (and to the Without-Samsung
summary), so it flows to the on-screen tables, the workbook, email and Recy from a
single call. Idempotent; no-op if GM/NM/OC are absent.

### Workbook formatting made label-based (robustness, not fragility)

`_style_workbook`'s Summary number-format and highlight maps were keyed by ROW
POSITION (`_ROW_NUMFMT`, `_SUMMARY_HIGHLIGHT_ROWS`). An inserted row would have
mis-aligned every format below it. Replaced with label lookups (`_summary_row_fmt`,
`_SUMMARY_HIGHLIGHT_LABELS`) — immune to this and any future row change. Values are
untouched; this is styling only.

### Verification

- AFR Apr-26 transport = **54,711** (manual 54,711); FY Total 54,711; sits directly
  above Operational Cost, on screen and in the workbook.
- **Regression: no existing summary value moved** in ANY vertical after the insert
  (every original row compared cell-by-cell, all months + FY).
- Workbook: Transportation Charges renders as ₹ integer; the % rows still carry the
  literal-% format; row order correct.

---

## 2026-08-01 · Sheet auto-detection: word/substring match for CN/DN names

Zoho exports name the CN/DN sheets inconsistently — "Credit Notes", "Vendor
Credits", "Debit Note (Jul)", "Vendor_Credits_Final", etc. `_canon_sheet` (app.py)
now does a WORD/substring pass after the exact-alias match: any sheet name
containing `vendorcredit` / `debitnote` → DN, `creditnote` → CN, `invoice` → Inv,
`accounttransaction` → AcctTxn (underscores/spaces already stripped by `_norm`).
DN phrases are checked BEFORE `creditnote` so "Vendor Credit Notes" → DN (vendor
credits are debit notes). Also added `dns`/`cns` plural aliases. Verified: "NO DN"
still → None (exclusion, caught before detection anyway), and junk sheets
(P&L, Dropdowns) still → None. Column-signature detection (Credit Note Number /
Vendor Credit Number columns) remains the primary fallback when a name doesn't match.

## 2026-08-01 · Last Year sheet — Cash Discount block has NO JV/provision table

Per owner: on the "Last Year Shipments" sheet, the **Cash Discount** block must NOT
show the little provision/JV summary (Provision as on 31-Mar / Accounted in FY /
NO DN value / Closing Provision / "Pertaining to FY"). DN, CN and Logistics keep
theirs. `reports.py` combined_workbook: the 4-row summary + pertaining label are now
gated on `_t != "Cash Discount"`. The Cash Discount detail still starts at `_top+7`
so the four columns stay row-aligned; its JV area is just left blank. Calc otherwise
unchanged.

## 2026-08-01 · OPEN / UNDONE — payables, and a source-data caveat

**Payables (Re-Commerce sign-flip) — UNDONE, needs finance basis + missing source.**
Confirmed how the engine computes payables: `Payable = Σ balance_fcy` of the AP
sheet rows tagged `vendor.CF.Vertical Name = <vertical>` — a plain gross total, no
netting of advances/credits (the AP export has none). Closed months are overwritten
by the manual "till" file (which can be negative), the open month is the live gross
AP sum — hence the −30 L (frozen manual) → +124 L (live AP) flip on Re-Commerce.
NOT an engine miscalculation; the +124 L is 33 real unpaid invoices. But the
manual's negative payable (−6.97 M) is **not** in the MIS and is **not** the customer
advances (those total only 610 k) — its true source is unknown (likely a
vendor-prepayment / Black Gold ledger the MIS doesn't carry). BLOCKED until finance
says what the payable basis should be and where the negative figure comes from.
NOTE: this is a SEPARATE issue from the receivables advance — do not conflate them.
See [[receivables-unused-credit-doublecount]] (that one IS the customer-advance
story; this payable one is not).

**ITAD unusual margins (e.g. −4538%) — SOURCE DATA, owner handling upstream.**
Many ITAD shipments show wild margins because the operations team mapped the
**purchase price incorrectly** in the source (Zoho/MIP). In the manual report the
owner hand-corrected those shipments. This is a data-quality fix at the source (MIP),
NOT an engine bug — owner will get it corrected upstream. Engine math is fine given
the (bad) input.

---

## 2026-07-31 · ITAD KG-item quantity → MT (fixes inflated ITAD quantity)

ITAD is counted in UNITS, but two item types are entered in KG, so summing them raw
inflated ITAD quantity ~1000×. Per finance, convert ONLY these exact item names to
MT (÷1000): **`ITAD Plastic waste`** and **`Mix E-Waste (ITAD)`** (exact match, no
pattern — several other e-waste spellings exist and must NOT be swept in).

`compute.py`: after `BA = AV − AZ` (Net Qty sales), divide `BA` by 1000 for rows
whose Item_Name matches. Applied AFTER the sale Amount (`AX = AV×AW`) is fixed, so
**only the quantity total changes — never Sales/Purchases/margins**.

Verified on the 26-July MIS: ITAD Quantity 51,494 → **12,022**; Sales 9,322,077,
Purchases 8,301,007, Gross Margin 1,021,070 — **all identical pre/post to the
rupee**. Side effect: ITAD Revenue/Purchase-per-Kg rise (smaller denominator) — a
direct consequence of the corrected quantity, not a separate change.

## 2026-07-31 · DECISIONS (no code) — DN ÷1.18 and Re-Commerce payable

**DN valuation in Details stays ÷1.18** (owner's call). `compute.py` keeps its
blanket ÷1.18 GST strip on every debit note. Consequence: the ~13 marketplace DN
notes with NO GST account (e.g. AFR `MP/AFR/OFF/0001`, note 36/AFR/27VC00020 —
manual shows 23,217, engine 19,675) stay slightly understated in Details. This is
accepted so the GST/tax-factor logic remains **strictly in the Last Year sheet, in
no other sheet**. Do not port `_ly_tax_factor` into compute.

**Re-Commerce payable is NOT an engine bug.** On the 26-July MIS the engine sums 33
distinct unpaid vendor invoices tagged `Marketplace (Re-Commerce)` in Zoho =
₹12,469,060 (~125 L) — no double-counting (33 unique txn#), no missed credits (0
negatives). The rise (56 L → 125 L) is real new AP (Blue Planet, Bathla, Haier,
Electrolux, Danish). The manual's negative figure uses a different basis (Black Gold
net-of-advances ledger). OPEN methodology question: gross AP (engine) vs
net-of-advances (manual), plus a sign inconsistency (frozen months negative, live
month positive).

---

## 2026-07-30 · Manual shipment exclusions (new feature)

A rule-free, user-maintained kill-list for shipments the engine cannot reasonably
detect on its own. Added at finance's request for the Plastic DRS orders.

**Deliberately has no logic.** The `Reason` column is the ONLY audit trail — that is
the whole design. Do not try to infer a rule from its contents.

- Store: `persistent/manual_exclusions.parquet`, columns
  `Vertical · Shipment ID · Reason · Exclude`. GitHub-synced, kept until changed.
- Scoped by **(Shipment ID, Vertical)** — the same id under another vertical is
  untouched, so an exclusion can never silently reach further than intended.
- UI on the Summary page: search (optionally filtered by vertical) → tick → add;
  plus an editable table with a Reason column and an `Exclude` checkbox, so a
  shipment can be re-included later without losing the note.
- `Exclude` unticked keeps the row but stops excluding — history is never lost.

### Applied in TWO places — both are required

`reports.drop_manual_exclusions()` is called from:

1. `app.py`, on `profit_df` before the summaries → summary rows and **FY Total**
2. `combined_workbook`, on `_rep` → the **Details sheet**

The second is NOT optional. Details is rebuilt from the accumulated store
(`db.profit_details_view`), so an excluded row would otherwise reappear there while
the summary had already dropped it — the workbook would contradict its own summary.
Same trap documented under the Re-Commerce entry below.

### Seeded (30-07-2026, per finance)

`36/MPPET/27/OFF/0001` and `36/MPPET/27/OFF/0002`, both Plastic — DRS orders
(District Tourism Development Officer, Rudraprayag), not Plastic sales.

Note `0002` is dated 26-Jul, i.e. AFTER the 19-Jul MIS cutoff, so it only takes
effect from the next export. The entry is stored now and will bite when it appears.

### Verification

Only the intended row moved: detail `2,618 → 2,617`; the Plastic `/OFF/` row gone;
the AFR (`MP/AFR/OFF/0001`, `/0002`) and IT AD (`36/ITAD/27/OFF/0001`,
`36/IAD/27/OFF/0001`) `/OFF/` rows **untouched**, confirming the vertical scoping.
Workbook Details sheet: 0 `/OFF/` rows.

### Consequence worth knowing — it exposed a real problem

Plastic Jun-26 Sales went `53,105 → −34,937`. That is **not** caused by the
exclusion; it is revealed by it. Plastic June holds only two rows: the DRS order
(Amount 168,000, Net Revenue 88,042 after its own 79,958 CN) and `SH012631015`
(Amount 20,090 carrying ~55,027 of credit notes). `20,090 − 55,027 = −34,937`.

`SH012631015` is a **January-2026 (prior-FY) shipment** that should not be in
Details at all — it is exactly the defect reported as "previous year shipments in
plastic came in details sheet". Fixing that moves it to the Last Year sheet and
Plastic June empties instead of going negative. **Do not chase the negative
separately — it closes when the prior-FY routing is fixed.**

July also shifts when a June shipment is excluded. That is the documented residual
mechanism (open month = pre-freeze FY − Σ frozen priors) and is expected —
confirmed with the owner on 30-07-2026.

---

## 2026-07-30 · Re-Commerce: a separate download per view

The Re-Commerce tab shows TWO summaries (regular + Without Samsung) but had ONE
download button, which bundled both into a single file. It now has two.

- **Button 1 — combined** (unchanged): both summary blocks, `Details` (all
  Re-Commerce) and the additive `Details (No Samsung)` sheet.
- **Button 2 — Without Samsung only** (new): `combined_workbook(..., ns_only=True)`
  → `profitability_Re-Commerce_without_Samsung.xlsx`, whose Summary AND Details
  both describe the non-Samsung subset alone, so the file stands on its own when
  shared. Receivables/Payables are company-wide, so identical in both.

### The trap this hit — read before touching it

The first attempt just passed a pre-filtered frame as `profit_df`. **That silently
did nothing**: the Details sheet is built from `db.profit_details_view()` — the
ACCUMULATED store merged with the current upload — not from `profit_df`. The
workbook would have carried a "Without Samsung" Summary over a Details sheet that
still contained all 1,417 Samsung rows. Caught only by counting rows in the built
file. **Filtering `profit_df` does NOT filter the Details sheet.**

`ns_only` therefore narrows `_rep` (after reco exclusions / orphan ordering /
custom-duty injection, before the sheets are cut) so Details, Supplier/Buyer metrics
and the FY cross-check all describe the same rows as the Summary.

### One definition, so the two outputs cannot drift

The subset logic — Re-Commerce rows whose vendor doesn't start with "Samsung",
overlaid with the signed-off without-Samsung manual store, date-ordered — was
inlined in the `Details (No Samsung)` block. It is now the module-level
`_rc_ns_detail(df, dbm)`, called by **both** that sheet and the `ns_only` path.

### Verification

| | Details rows | Samsung-vendor rows |
|---|---|---|
| Combined workbook | 1,872 | 1,417 |
| Standalone Without-Samsung | **759** | **0** |

The standalone workbook's `Details` is row-for-row identical to the combined
workbook's `Details (No Samsung)` sheet (759 = 759) — the shared-helper guarantee,
checked on the built bytes rather than assumed. Sheet lists confirm `ns_only`
correctly suppresses the now-redundant `Details (No Samsung)` sheet.

---

## 2026-07-28 · VERIFIED, NO CHANGE — Last Year "Closing Provision" formula

Asked to change it to
`Closing Provision = provision − (Accounted in FY 2026-27 + NO DN value)`.
**It already computes exactly that** — no edit was made. Recorded so the formula is
not "fixed" into something wrong later.

Both paths in `reports.py` → `combined_workbook` are correct:

- stored figures: `_close = round(_provcell - _acct - _nodncell, 2)`
- blank/manual: a live Excel formula `=<prov> - <accounted> - <noDN>`

`p − a − n` is algebraically identical to `p − (a + n)`.

Checked against `Profitability Report of End Generator till 19-07-2026.xlsx`:

| block | provision | accounted | NO DN | computed | manual closing | diff |
|---|---|---|---|---|---|---|
| DN | 6,275,044.32 | 2,455,994.161017 | 420,633.304 | 3,398,416.854983 | 3,398,416.854983 | **0.00** |
| CN | 10,302,843.00 | 6,368,645.750000 | 429,599.534 | 3,504,597.716000 | 3,504,597.716000 | **0.00** |
| Logistics | 1,092,270.00 | 1,102,034.500000 | 0.000 | −9,764.500000 | −9,764.500000 | **0.00** |

Logistics going **negative** (−9,764.50) is correct and expected: more was accounted
in FY 26-27 than was provided for, so the provision is over-consumed.

The live-formula cell references were checked too: the summary is written at
`startrow=_top+1` **with** a header row, so its data lands on Excel rows
`_top+3 / +4 / +5`, which is what `_rowP, _rowA, _rowN` point at; and
`_gcl(_c0 + 3)` resolves to the Amount column (1-based letter over a 0-based
`startcol`). Do not "off-by-one" these.

---

## 2026-07-28 · Release: what went to GitHub, and what deliberately did not

Commit **`2cd90ad`** on `main` — `reports.py` (+134/−2) · `CHANGES_AND_RULES.md` ·
`requirements.txt` · `.gitignore`. **Code and docs only**, per the `CLAUDE.md`
house rule.

### Deliberately NOT pushed — `persistent/profit_details.pkl`

Owner's decision (28-07-2026): left out of the loop, summary numbers already
reconcile. Recorded here so the consequence is not lost:

| | Apr | May | Jun | **Jul** | total |
|---|---|---|---|---|---|
| Local (working copy) | 659 | 668 | 858 | **423** | **2,608** |
| GitHub baseline | 658 | 668 | 858 | **81** | **2,265** |

The gap is **340 July line rows** — Re-Commerce 252 · IT AD 41 · IB 29 ·
ReWerse 11 · Metal 7 (plus one extra April line item).

**This does not affect any summary figure.** The exposure is the *Details sheet*:
the hosted Streamlit Cloud disk resets to the GitHub baseline on every restart or
redeploy, so after a restart every downloaded workbook would carry the 2,265-row
store and lose those 340 July rows — and the "sum Details to cross-check the FY
Total" check would stop tying until the next upload re-accumulates them.

Recoverable by re-uploading the historical MIS exports in date order, while those
files still exist. **Revisit whenever the hosted app is next restarted.**

Note also: the authoritative copy is unconfirmed. The local file was pickled under
numpy 2, i.e. written by the hosted app, so the live hosted disk may hold something
newer again. Any future sync should start by establishing which store is current.

---

## 2026-07-28 · Cross-vertical verification of the Last Year rules

**No rollout was needed.** `last_year_left_behind()` has never had per-vertical
branching — every vertical runs the identical `_extract_dn_notes()` / `_extract()`
path and the vertical is simply read off each row's `Account`. End Generator was
never special-cased, so the three rules below applied to all verticals the moment
they were written.

### Engine output, all verticals (`MIS Docs as of 19-07-2026 correct.xlsx`)

| Vertical | CN | DN | Logistics | Cash Disc. |
|---|---|---|---|---|
| End Generator | 40 · 6,374,365.75 | 37 · 2,435,712.16 | 16 · 1,102,034.50 | 28 · 22,594.64 |
| IB | 47 · 154,239.50 | 15 · 40,486.53 | 5 · 338,890.00 | — |
| ReWerse | 22 · 105,923.50 | — | — | — |
| AFR | 11 · 285,831.50 | 11 · 289,423.00 | — | — |
| Plastic | 9 · 1,392,386.77 | 8 · 692,373.30 | — | — |
| **ITAD** | **0** | **0** | **0** | **0** |

### ITAD — reconciles at zero, but proves nothing

Engine produces **0 rows**; the manual
(`Profitability Report of ITAD till 30-06-2026.xlsx` → `Last year's`) also holds
**0 detail rows**. Consistent, no defect — but a **vacuous** check that exercised
none of the logic. Two independent reasons ITAD is legitimately empty:

- Neither the MIS `CN` nor `DN` sheet carries any ITAD account. Only `Bills` has
  `Marketplace Purchases (ITAD)`, which the Logistics filter (accounts containing
  "marketplace logistics") correctly ignores.
- The ITAD manual's sheet is a **stale FY 2024-25 template** — its labels still read
  "as on 31st Mar-**2024**" and "Accounted in FY **23-24**", every amount is blank
  or 0, and it has only 3 blocks (no Cash Discount). It is not maintained.

### The TDS branch is confirmed DEAD on this data

Factor distribution over every Last Year DN note, all verticals:

| Vertical | ×1.00 | ×1.18 | ×1.16 | ×1.08 |
|---|---|---|---|---|
| End Generator | 6 | 31 | 0 | 0 |
| IB | 1 | 14 | 0 | 0 |
| AFR | 3 | 8 | 0 | 0 |
| Plastic | 1 | 7 | 0 | 0 |

**The 1.16 / 1.08 paths fired on 0 notes.** The MIS's only four TDS-bearing notes
(`SH04261801`, `SH06260604`, `SH072616016`, `SHMPIB0001`) are all FY 26-27
shipments, so they sit in Details and are excluded from "last year" by definition.
Those two rates remain coded to spec and **verified against nothing**.

**DECISION (28-07-2026, owner): keep the logic, do not remove it.** TDS cases are
expected in future periods, and the rule is cheapest to capture now while the spec
is fresh. It is dormant, not dead — `_ly_tax_factor` needs no change to activate:
the moment a TDS-bearing note belongs to a shipment that is NOT in the current
Details, it will be picked up and valued at 1.16 (IGST TDS) or 1.08 (CGST/SGST TDS)
automatically.

**When that first happens, verify it before trusting the figure** — it will be the
first time either rate has ever been exercised. Reconcile that one note against the
vertical's manual file and record the result here. Concretely: as prior-year
shipments age out of Details, notes like `36/MET/27VC00052`, `36/IB/27VC00002`,
`36/MET/27VC00111` and `36/MET/27VC00123` (all carrying `IGST TDS Payable-2%`) are
the candidates to watch.

### OPEN — AFR / ReWerse / IB produce rows their manuals do not

The engine emits Last Year rows for these verticals, but their manual files show
none — all three AFR files (`till 21-06`, `till 30-06`, `till 19-07`) have an
**empty** `Last year's` sheet (0 DN, 0 CN). Either those manuals simply do not
maintain the sheet, or the engine is over-attributing. **Unresolved — needs a
finance decision, not a code change.** Note ReWerse is also formally out of scope
per `CLAUDE.md` yet appears here, so the sheet's vertical filter may need narrowing.

**End Generator remains the only vertical with a maintained manual to reconcile
against, and therefore the only real evidence for these rules.**

---

## 2026-07-28 · Last Year sheet — DN GST/TDS · CN de-dup · Logistics per-item

**Scope: the Last Year sheet and nothing else.** Verified isolated:
`last_year_left_behind()` is called from exactly one place
(`reports.py` → `combined_workbook`, the sheet builder) and `_extract()` is nested
inside it, so no summary metric, Details column or other sheet can see any of this.
The main engine keeps its own separate DN treatment
(`compute.py` → `BZ = SubTotal / 1.18`), which was **not** touched.

Three independent defects, one per table. All four tables now tie to **₹0.00**.

### Rule 1 — DN: GST / TDS de-grossing (per note)

Zoho repeats a vendor credit's **document** `SubTotal` on *every* line of that note,
including its tax lines. The signed-off manual shows **one row per note**, valued
**ex-tax**:

```
value = note SubTotal ÷ (1 + Σ tax rates implied by the note's ACCOUNT names)
```

| Account name contains | rate |
|---|---|
| `IGST`  | + 18 % |
| `CGST`  | + 9 % |
| `SGST`  | + 9 % |
| `IGST TDS` | − 2 % |
| `CGST TDS` | − 1 % |
| `SGST TDS` | − 1 % |

Rules that matter:

- **Rates are SUMMED, never compounded.** A note carrying both CGST and SGST is
  9 + 9 = 18 % → ÷ 1.18. Compounding (1.09² = 1.1881) would value note
  `36/MET/27VC00017` at 819.29 against the manual's **825.00**.
- **IGST is 1.18**, not 1.08 — confirmed by the finance team and by 32 notes.
  Do not "simplify" it.
- **Each pattern contributes at most once**, so a note carrying two IGST accounts
  (`Input IGST Suspense Account` + `IGST (Ineligible)`) is still 18 %.
- TDS combinations therefore fall out as IGST TDS → 1.16 (18 − 2) and
  CGST/SGST TDS → 1.08 (9 − 1).
- A note's **vertical** comes from whichever of its lines carries a
  reported-vertical account (`Marketplace Purchases (Metal)` etc.). Tax lines have
  no `(vertical)`, so they contribute their *rate* without creating a phantom row.
  A note with no reported-vertical line is dropped, as before.

### Why it was wrong before

1. Tax-account rows were silently dropped (no `(vertical)` parenthetical), so their
   rate was never seen and the note was valued **gross**.
2. The per-row path **double-counted** any note with two material lines — e.g.
   `36/MET/27VC00027` has two `Marketplace Purchases (Metal)` lines both stamped
   6,638.02, which the manual counts once as 6,638.02 ÷ 1.18 = 5,625.440678.

### Rule 2 — CN: one row per document

A credit note's `SubTotal` is the **document** total, repeated on every line item.
**53 of 270** notes are multi-line (`36/MET/27CN00068` has 3), so the per-row read
counted them once per line. The manual counts each note **once**.

De-dup is applied **after** the vertical filter, so the surviving line is the first
that carries a reported vertical — a note whose first line is a non-vertical account
is still kept via its Metal/AFR/… line.

No GST factor here: the CN sheet has **no tax accounts at all** (11 distinct, all
`Marketplace Sales (…)` / `Sustainability Revenue (…)` / `Cash Discount` / `PWM
Registration Charges`). Applying the DN factor would be a no-op — do not add it.

`47 rows → 40 rows`, and all 40 tie exactly.

### Rule 3 — Logistics: per-ITEM value, not the document SubTotal

Bills also repeat their `SubTotal` on every line, but here the manual lists each
**item** separately — bill `BWD00003159/25-26` appears twice as 21,000 and 6,100,
not as its 27,100 SubTotal twice. So the Logistics table reads **`Item Total`**,
falling back to `SubTotal` only if an older export lacks it.

Row selection was already correct (16 = 16) — this was purely the amount column.
`1,307,209.50 → 1,102,034.50`, exact. Note Logistics must **not** de-dup: a bill
number legitimately recurs with different items.

Bills has no tax accounts either, so no GST factor here.

### Code

`reports.py` — additions plus one swapped call; no existing behaviour altered:

- `_LY_TAX_RATES` + `_ly_tax_factor()` (module level, above `last_year_left_behind`)
- `_extract_dn_notes()` (nested), replacing the `_extract(dn_df, "DN", …)` call
- `_extract()` gains two optional args, both defaulting to the previous behaviour:
  `amount_names=("subtotal","amount")` and `dedupe_note=False`
- CN call passes `dedupe_note=True`; Logistics call passes
  `amount_names=("item total","itemtotal","subtotal","amount")`
- **Cash Discount is untouched** — it uses its own inline block and already tied.

### Verification

Input: `MIS Docs as of 19-07-2026 correct.xlsx` (CN 367, **DN 1,423** rows).
Target: `Profitability Report of End Generator till 19-07-2026.xlsx` → `Last year's`.

| Block | eng rows | man rows | engine Σ | manual Σ | diff |
|---|---|---|---|---|---|
| **Logistics** | 16 | 16 | 1,102,034.50 | 1,102,034.50 | **0.00** |
| **Cash Discount** | 28 | 28 | 22,594.64 | 22,594.64 | **0.00** |
| **DN** | 37 | 45 | 2,435,712.16 `+20,282.00` legacy | 2,455,994.16 | **0.00** |
| **CN** | 40 | 41 | 6,374,365.75 `−5,720.00` legacy | 6,368,645.75 | **0.00** |

Every note the engine produces ties individually to <₹0.01 (DN 37/37, CN 40/40) —
not just the totals. DN factor distribution: 32 notes at 1.18, 8 tax-free at 1.00.

### Known gaps (NOT fixed — deliberately)

- **The TDS rates (1.16 / 1.08) are unevidenced.** No TDS-bearing note appears in
  End Generator's Last Year set — its four TDS notes (`SH04261801`, `SH06260604`,
  `SH072616016`, `SHMPIB0001`) are FY 26-27 shipments, so they sit in Details, not
  "last year". Coded to spec, never yet proven against a manual.
- **6 legacy `DN`-series rows are manual-only** and cannot be generated — they are
  absent from the MIS sheets entirely. Confirmed as expected by the finance team.
  In the DN block: `26/MPMET/DN5272` (−5,599) · `27/MET/26DN0097` (−9,270) ·
  `27/MET/26DN0093` (−4,485) · `27/MET/26DN0096` (−9,270) · `26/MPMET/DN4613` (−50,000)
  → net **+20,282** with the three offsetting VC rows below.
  In the **CN** block: `36/MET/27DN00001` (−5,720).
- **3 VC notes the manual counts but `_is_left()` excludes** — `36/MET/27VC00106`
  (+27,169), `VC00109` (+21,737), `VC00110` (+50,000). Their shipments
  (`SH022617019`, `SH012622042`, `SH012631022`, `SH112519034`) DO appear in this
  MIS's Details, so the documented "not in Details" rule correctly drops them. The
  manual treats them as last-year regardless. **Definitional conflict — needs a
  decision before `_is_left` is changed.**
- **Only End Generator has a maintained manual to reconcile against.** ITAD checked
  and consistent (both zero, but vacuous); AFR / ReWerse / IB produce rows their
  manuals do not. See the cross-vertical entry above for the full picture.

> Beware when reading the manual: its DN, Logistics and Cash Discount blocks each
> carry a **`G.Total` row** inside the data range. Summing the block naively
> double-counts it and yields exactly 2× the true figure.

---

## 2026-07-28 · Environment & repo recovery (no logic changed)

- **Restored `cleaning.py` + `compute.py`** — both were **missing** from the Google
  Drive export (`app.py` imports them, so the app could not start). Extracted from
  git commit `f1ebd7a`; blob hashes verified identical to GitHub.
- **Restored 9 missing persistent stores** and `.streamlit/config.toml` +
  `secrets.toml.example`, likewise hash-verified against the repo:
  `enterprise_custom_duty`, `enterprise_opcost`, `ib_warehouse_shipments`,
  `last_year_inputs`, `manual_line_items`, `no_dn_shipments`, `provision_rates`,
  `reco_review`, `recommerce_manual_without_samsung`.
  `.streamlit/secrets.toml` is **not** in git by design — recreate it locally.
- **Folder put under git**, `origin` = `github.com/himanshipal-glitch/Automation`,
  fast-forwarded `f1ebd7a` → `ae4ce52` (**v3.24.0 → v3.25.0**: returned-bill split
  + resale keeps its own purchase bill).
  Verified: SH072616016 → 2 lines (returned leg cost 0, invoiced leg 873,484.90);
  SH06260908 → Total Cost 933,699.54, both matching the manual.
  Frozen Apr/May/Jun matched the manual with **zero** differences.
- **`requirements.txt` pins raised** — `pandas>=2.3,<3` and `numpy>=2.0,<2.1`.
  The persistent stores are pickled by the hosted app under numpy 2 / pandas 2.3;
  numpy 1.x raises `ModuleNotFoundError: numpy._core.numeric` and pandas 2.2.3
  raises `TypeError: issubclass() arg 1 must be a class` on `profit_details.pkl`.
  The numpy upper bound keeps `tensorflow-intel` (numpy<2.1) usable.

### Latent issue worth fixing separately

`database.py` → `_read_df()` swallows every exception (`except Exception: return None`),
so the above version skew presented as an **empty** Details store with no warning at
all. A `st.warning` on read failure would have made it obvious immediately.

---

## Reference — the two MIS exports are not equivalent

`MIS Docs as of 19-07-2026 (1).xlsx` has its **CN/DN sheets date-filtered to July
only** (10 CN, 10 DN rows), so it cannot populate the Last Year sheet at all.
Use **`MIS Docs as of 19-07-2026 correct.xlsx`** (CN 367, DN 1,423, spanning
01-Apr → 18-Jul). Always sanity-check DN row count before reconciling.


---

# 2026-08-10 — Logistics fixes (from the End Generator RECONCILE sheet)

Three changes, all from the owner's reconciliation notes on the 31-July End
Generator report. Nothing else was touched — in particular **the ÷1.18 GST
handling in Details is unchanged**, per the standing rule that GST logic lives
only on the Last year's sheet.

## FIX A — a freight debit note belongs in "Debit note on logistic cost"
`compute.py` · new optional `dn_df` argument

**Note.** `36/MET/27VC00126` · TATA ROAD CARRIER · account
**`Marketplace Logistics (Metal)`** · raised against freight bill
`TRC26BLO000238` · ₹8,544.50 · shipment **`SH062625011`**.

**Was.** It fell through to `Actual Debit Note` (a *material* debit note) and was
then divided by 1.18 → 7,241.10. Freight stayed at 25,100 and cost was ₹1,303.40
too high.

**Now.** Any vendor credit whose Account contains `Marketplace Logistics` is
routed to column Z (`Debit note on logistic cost`) as a negative, and removed
from the DN subtotals so it never reaches Actual DN or the 1.18 division. This is
routing by Account — the same thing `cleaning.split_bill` already does for bills —
**not** GST logic.

| | before | after | manual |
|---|---:|---:|---:|
| Logistics cost | 25,100.00 | 25,100.00 | 25,100.00 |
| Debit note on logistic cost | 0.00 | **−8,544.50** | −8,544.50 |
| Total Logistics Cost | 25,100.00 | **16,555.50** | 16,555.50 |
| Actual Debit Note | 7,241.10 | **0.00** | 0.00 |
| Total Cost | 922,832.90 | **921,529.50** | 921,529.50 |

Seven freight credits exist in the 31-Jul MIS; four were sitting in Actual DN —
`36/MET/27VC00126` (EG) and `27/IB/27VC00019`, `27/IB/27VC00021`,
`27/IB/27VC00022` (Enterprise).

## FIX B — one freight bill = one charge per shipment
`compute.py`

**Was.** The logistics merge is on `CF.SO Number`, so a shipment's freight landed
on **every** Details row of that shipment.

| Vertical | Shipment | Freight bill | rows | charged | should be |
|---|---|---|---:|---:|---:|
| End Generator | `SH072616016` | `TRC26BLO000297` | 2 | 44,536 | **22,268** |
| Enterprise | `SH042614013` | `043689` | 6 | 210,600 | **35,100** |
| Enterprise | `SH06260101` | `1027` | 2 | 150,580 | **75,290** |
| Enterprise | `SHMPIB0001` | `02` | 2 | 138,480 | **69,240** |
| Enterprise | `SH05262701` / `SH05262901` / `SH06260702` / `SH06261101` | — | 2 each | 60,700 each | **30,350 each** |

**Now.** The charge is kept on the row that carries the SALE — where the manual
puts it (`SH072616016`'s freight sits on the invoiced leg `SFPL/0528`, not on the
returned leg `SFPL/0519`) — and zeroed on the shipment's other rows. If no row of
the shipment has a sale, it stays on the first row so nothing is lost.
Blank-shipment rows are untouched.

## FIX C — Transportation Charges must read Total Logistics Cost
`reports._summary_block`

**Was.** `tc = w["Logistics_Cost"].sum()` — the raw freight line only, which drops
the logistics provision. End Generator showed **248,736** against the manual's
**382,923.50**, a ₹1,65,000 shortfall.

**Now.** `tc = w["Total_Logistics"].sum()` = freight + provision + freight DN.

## Verified — End Generator logistics, all four columns

| Column | engine | manual | gap |
|---|---:|---:|---:|
| Logistics cost | 226,468.00 | 226,468.00 | **0.00** |
| Debit note on logistic cost | −8,544.50 | −8,544.50 | **0.00** |
| Logistics Provision | 165,000.00 | 165,000.00 | **0.00** |
| **Total Logistics Cost** | **382,923.50** | **382,923.50** | **0.00** |

Summary row, FY Total:

| Vertical | Transportation | manual | gap |
|---|---:|---:|---:|
| End Generator | 382,923 | 382,923.50 | **−0.50** |
| AFR | 54,711 | 54,711.00 | **0.00** |
| Plastic / IT AD / Re-Commerce | 0 | 0 | **0.00** |

## Effect on every vertical

| Vertical | Total Logistics before | after | change |
|---|---:|---:|---:|
| End Generator | 413,736.00 | 382,923.50 | **−30,812.50** |
| Enterprise (Institutional Business) | 742,460.00 | 290,965.00 | **−451,495.00** |
| everything else | — | — | unchanged |

**₹4,82,307.50 of over-counted freight removed.** Actual DN falls correspondingly
as the freight credits leave it: End Generator 681,173.94 → 673,932.84,
Enterprise 609,695.30 → 601,165.64.

⚠️ Enterprise has NOT yet been reconciled against its manual. Its ₹4.51 L drop is
the same two mechanisms proved on End Generator, but it should be checked when
Enterprise is reconciled.

## Not changed

- The blanket ÷1.18 on material debit notes in Details — deliberately left alone.
  `MP/AFR/OFF/0001` (`36/AFR/27VC00020`, ₹23,217, no tax line) therefore stays
  ₹3,541.58 out. GST logic remains confined to the Last year's sheet.
- The report cutoff date, `CF.Debit note Status`, prior-FY routing, the Amazon
  overlay, full-reversal bucketing, seller/buyer counts — all still open.

---

# 2026-08-10 — Enterprise: Pune (MPPUNE) notes reach the Last year's sheet

`reports.last_year_left_behind` · new `_PRIOR_FY_ORDER_PREFIXES`

## Problem

Enterprise's Last year's **credit-note block was ₹1,06,327 short** — 31 of the
manual's 46 notes were missing, and they weren't anywhere else in the report
either.

| Block | engine | manual | gap |
|---|---:|---:|---:|
| CN | 43,225.00 (15 notes) | 1,49,552.00 (46) | **−1,06,327.00** |

## Cause

All the missing notes reference a **Pune order**, not a shipment id:

```
27/IB/27CN00018   Reference# = MPPUNE/0073   SAARLOHA ADVANCED MATERIALS    8,412
27/IB/27CN00034   Reference# = MPPUNE/0078   SOUND CASTINGS                14,001
27/IB/27CN00052   Reference# = MPPUNE/0161   SOUND CASTINGS                 6,300
   ... 32 notes in total, Rs 1,11,014.50
```

The last-year test asks *"is every referenced shipment prior-FY?"* via a regex
expecting `SH` + MM + YY. `MPPUNE/0073` doesn't match, so it was treated as
CURRENT year and the note was dropped. And because no such shipment exists in
Details either, the notes vanished from the report completely.

They genuinely are prior-year notes:

- the manual's block is headed **"Credit note Pertaining to FY 25-26"**
- Pune is kept on the manual's own **'Pune MIS'** sheet (448 rows), every row of
  which reads `Financial Year = FY 2025-26`, months Apr-25 onward, with
  `CF.SO Number` values like `MHPV001` and `MPPUNE/0183`

## Rule

> A reference we cannot parse as an `SH` shipment id is NOT automatically
> current-year. An order reference belonging to a business kept on its own
> prior-FY book — Pune, `MPPUNE/…` — is a last-year reference, provided this
> MIS's Details has never seen it.

Held in one named constant so another branch can be added later:

```python
_PRIOR_FY_ORDER_PREFIXES: tuple[str, ...] = ("MPPUNE",)
```

## Deliberately NOT generalised

The obvious wider rule — *"unparseable AND not in Details"* — was tested and
rejected. It adds far more than the manuals carry:

| Vertical | Type | rows | value | wanted? |
|---|---|---:|---:|---|
| IB | CN | 32 | 1,11,014.50 | YES |
| IB | Logistics | 3 | 3,00,340.00 | no — `MHPV333/334/339` vehicle refs |
| Plastic | CN | 3 | 7,78,142.28 | no |
| Plastic | DN | 2 | 47,420.00 | no |
| Plastic | Logistics | 4 | 42,000.00 | no |
| Re-Commerce | DN | 5 | 4,73,944.20 | no — Re-Commerce is out of scope |

**Add a prefix to that constant only with a manual to prove it against.**

## Verified

Prefix list OFF vs ON, whole Last year's sheet:

```
AFR            CN / DN            unchanged
End Generator  CN / DN / Logistics unchanged
Plastic        CN / DN            unchanged
ReWerse        CN                 unchanged
IB             DN / Logistics     unchanged
IB             CN     15 -> 47 notes    43,225.00 -> 154,239.50   <<< the only change
```

**One vertical/type changed, nothing removed.** Summary tabs untouched — the Last
year's sheet is display-only and never feeds a total.

| Enterprise block | before | after | manual | gap |
|---|---:|---:|---:|---:|
| **CN** | 43,225.00 | **1,54,239.50** | 1,49,552.00 | **+4,687.50** |
| DN | 40,486.53 | 40,486.53 | 30,861.53 | +9,625.00 |
| Logistics | 38,550.00 | 38,550.00 | 43,229.00 | −4,679.00 |

CN gap: **−1,06,327 → +4,688**.

## Known residuals (manual-side choices, left alone)

- **`SH03262704`** — we carry its CN (4,687.50), DN (3,125) and Logistics
  (30,000); the manual carries none of the three. A Mar-2026 shipment, prior-FY
  by every test, simply not listed on Enterprise's Last year's sheet.
- `27/IB/27VC00012` (2,925) and `VC00013` (3,575) — the manual has these
  shipments' CREDIT notes (`CN00015`, `CN00016`) but not their DEBIT notes.
- Logistics: the manual lists `GST/25-26/005` (YASH ENTERPRISES, 15-Apr-**2025**,
  43,229) which we don't reach — that block is headed *"FY 24-25 Logistic Bills
  accounted FY 25-26"*, a year further back than we look.

## Enterprise reconciliation summary (31-Jul MIS)

- **Details: 0 of 230 shipments differ** on any field.
- Sales / Purchases / Gross Margin **exact for all four months**; Total Cost,
  Amount, Net Revenue, Margin and Inv Qty all tie to the rupee.
- Sellers and buyers match every month.
- The freight fixes have **no effect** on the Enterprise tab — its B2B rows carry
  no freight at all (that sits in Processing Center).
- Open: 3 August shipments (`SH08260303`, `SH08260305`, +1) need the report
  cutoff; Receivable is exactly **Rs 1,00,000** below the manual once August is
  excluded (looks like a manual adjustment — ask finance); the manual counts its
  own `Service Charges (…)` placeholder rows as transactions and as a supplier
  (BLACK GOLD), which is why its Jun/Jul transaction and FY seller/buyer counts
  run one higher than ours.
- **Operational Cost is NOT an engine issue** — it is already a manual input.
  Apr/May/Jun stored values match; Jul-26 needs updating from 168,433 to
  **205,788** (the manual adds a row labelled *"Excess charged in provision than
  actual"*, +37,355).

---

# 2026-08-11 — Freight credits removed from the Last year's DN block

`reports.last_year_left_behind._extract_dn_notes`

## Why

The 10-Aug commit taught **Details** that a vendor credit on a
`Marketplace Logistics` account is a FREIGHT credit — it goes in
`Debit note on logistic cost`, not `Actual Debit Note`. The **Last year's** sheet
is built separately, straight from the Vendor Credit sheet, and was never told.
So the two sheets contradicted each other: Details treated the note as freight,
Last year's still listed it as a material debit note.

Spotted while reconciling Enterprise — `SH03262704` showed up as an extra row in
our DN block:

```
27/IB/27VC00001   07-Apr-2026   SH03262704   SAMRUDDHI ROADWAYS   Rs 3,125
Account: Marketplace Logistics (Institutional Business)      <- a transporter
```

## Rule

A vendor credit raised on a `Marketplace Logistics` account never belongs in the
Last year's **DN** block. It reduces the transporter's bill, not the material
cost — the same rule Details already follows.

## Scope — checked, not assumed

There are 7 freight vendor credits in the 31-Jul MIS:

```
27/IB/27VC00001  27/IB/27VC00018  27/IB/27VC00019  27/IB/27VC00021
27/IB/27VC00022  36/MET/27VC00107  36/MET/27VC00126
```

**None of them appears in any manual's Last year's DN block** — verified against
both the End Generator and Enterprise manuals, all 7 notes. And only ONE of them
was reaching our sheet at all: `27/IB/27VC00001`, because SH03262704 is a
Mar-2026 shipment (prior-FY). The other four IB ones sit on current-FY shipments
and never qualify; `36/MET/27VC00126` likewise.

## Result

| Vertical / block | before | after | manual | gap |
|---|---:|---:|---:|---:|
| **IB — DN** | 40,486.53 (15) | **37,361.53 (14)** | 30,861.53 | **+6,500.00** |
| AFR CN / DN | | unchanged | | |
| End Generator CN / DN / Logistics | | unchanged | | |
| Plastic CN / DN | | unchanged | | |
| ReWerse CN | | unchanged | | |
| IB CN / Logistics | | unchanged | | |

Freight credits remaining anywhere on the sheet: **0**.

## What is left on Enterprise's DN block, and why

The residual **+6,500** is two notes the MANUAL is missing, not us:

| Note | Shipment | Vendor | Account | raw | ÷1.18 |
|---|---|---|---|---:|---:|
| `27/IB/27VC00012` | SH102510050 | YASH ENTERPRISES | MP Purchases (IB) + CGST + SGST | 3,451.50 | **2,925.00** |
| `27/IB/27VC00013` | SH102511015 | YASH ENTERPRISES | MP Purchases (IB) + CGST + SGST | 4,218.50 | **3,575.00** |

They are indistinguishable from the twelve the manual DOES carry — same vendor,
same three accounts, same dates (13-May-2026, within the 23-Apr → 05-Jun range of
the rest), and their associated bills `GST/25-26/203` and `/204` sit between
`/188` (VC00010, included) and `/206` (VC00020, included).

The clincher: the manual's own CREDIT-note block carries both shipments —
`27/IB/27CN00015` Rs 3,015 for SH102510050 and `27/IB/27CN00016` Rs 3,685 for
SH102511015. It has the credit note for each and not the debit note.

**Raised with the manual's owner — looks like two rows missed while compiling.**

## NOT changed (deliberately)

Enterprise's receivable is Rs 1,00,000 below the manual once August is excluded,
because `36/IB/27DN00001` (R.H.TRADERS, 24-Jul-2026, Rs 1,00,000) is a debit note
raised ON A CUSTOMER: it sits in the AR sheet as money owed to us, but has no
Details row, so the invoice-number lookup that builds Enterprise's receivable
never finds it. There is already a hand-maintained list for exactly this
(`ENTERPRISE_EXTRA_AR_INVOICES`, 11 entries, one of which is `26/MPPIB/DN0005` —
another customer DN somebody added by hand). **Owner is checking with finance
before we change the rule.**

---

# 2026-08-14 — The NO DN sheet now always refreshes the stored list

`app.py._is_no_dn_sheet`, `app.py._process_excel`, `database.save_no_dn_shipments`

## Rule (unchanged, now enforced)

The most recently uploaded NO DN sheet REPLACES the stored list, and stays in
force until another NO DN sheet is uploaded. It is not merged.

## Why

Reconciling AFR against the 31-Jul manual, seven shipments were taking a CN/DN
provision the manual did not:

```
SH06261301, SH06262202   AFR              manual Remarks "No DN"
SH04261004               Plastic          "DN Issued & CN not passing"
SH072616016, SH072628013, SH072630015   End Generator   "No Debit Note"
SH06260908               End Generator    "Divertion"
```

None of the seven is on the stored NO DN list (9,349 shipments, last written
28-Jul-2026). The 31-Jul MIS pack contains six files — Bill, Invoice,
Credit_Note, Vendor_Credits, AR, AP — and **no NO DN sheet at all**, so the
store was never refreshed. Worth ~Rs 9,457 on AFR and Rs 22,467 on Plastic.

That is a process gap, not a code bug. But chasing it surfaced four ways the
refresh could fail SILENTLY, which are what changed here.

## What changed

1. **Sheet detection inside a workbook was far narrower than for a standalone
   file.** In-workbook, a tab qualified only if its name normalised to exactly
   `nodn`, or it carried a `DebitNotefromBuyer` column. A standalone file got a
   full keyword list. So a tab named `NO DN List`, `No_DN_Shipments`, `CF DN No`
   or `DN Status` inside the combined MIS export was skipped with no error and
   the store silently stayed on the previous upload. Both paths now share one
   vocabulary: `nodn`, `cfdn`, `dnno`, `dnstatus`, `nondn`, matched as
   substrings. A sheet that resolves to a core dataset (Bill/CN/DN/AP/AR/Inv) is
   never treated as the exclusion list.

2. **An empty or unusable sheet was a silent no-op** — `save_no_dn_shipments`
   returned early and the UI still showed a green tick. It now returns
   `(rows_stored, note)` and the upload table shows the reason. The previous
   list is left intact in that case, so a blank or mis-parsed sheet can never
   wipe the store.

3. **The shipment-ID column fallback was blind** — anything unrecognised fell
   straight to `df.columns[0]`. It now tries the known names, then any column
   mentioning a shipment/SO id, and only then falls back to column 0 — saying so
   in the note when it does.

4. **No visibility.** The upload row now reads `No-DN exclusion (9,349 -> 9,412)`
   and the sidebar shows when the list was last replaced, so a stale list is
   obvious instead of invisible.

## Verified

Detection: 11 cases pass — the four previously-missed name variants now match,
and `Bills` / `DebitNotes` / `CreditNotes` / `Invoice` / `DropdownData` are
never swallowed. Save: replace-not-merge confirmed; empty sheet, all-blank ids,
odd column name and the DebitNotefromBuyer filter all behave. The real 9,349-row
store was backed up, exercised and restored identical. Full engine re-run after
the change gives byte-identical FY totals on all six verticals.

## NOT changed (deliberately)

`CF.Debit note Status` on the Invoice sheet is NOT read and NOT used. The NO DN
sheet remains the only source of the no-provision list.

---

# 2026-08-14 — Enterprise never takes a CN/DN; IT AD loses its per-Kg rows

## 1. Enterprise: credit / debit notes are never taken

`compute.ENTERPRISE_NO_NOTES` + the block just above `AK = BZ` in
`compute.build_profitability`

### Rule

An Institutional Business B2B deal does not carry credit or debit notes. If a
note appears in the MIS against an Enterprise shipment it is mis-tagged (it
belongs to another vertical), so it is NOT taken into the report — actual notes
AND provisions, on both the sales and the purchase side.

**Enterprise ONLY.** Scoped to the same definition `reports._ib_split_masks`
uses for the Enterprise tab: an Institutional Business row whose shipment id
starts `SH`, is not an internal `MPIB` transfer, and has a real purchase behind
it. Processing Center keeps its notes; every other vertical is untouched.

### Where it is applied, and why there

The six series (Full/Actual/Provision on each side) are zeroed BEFORE `AK`/`BL`
are derived and before Total Cost (`AM`) and Net Revenue (`BN`) are built, so
every dependent column — Total Cost, Net Revenue, Total CN/DN (Inc. Prov), the
Check columns, Margin, the GST columns and the Remarks text — follows
automatically. Patching the output frame afterwards would have meant
re-deriving those by hand, with the sign traps that live in that layout
(`AM = Q + AB + AJ + T + AE − AK − AL`, `BN = AX + BK + BB + BF − BL − BM`).

### Evidence it matches the manual

The Enterprise manual's Details sheet has ZERO shipment rows carrying a CN or
DN. Two rows do hold an `Actual Credit Note` value (−7,777,762.38 and
5,718,754.55) but every other field on them is blank — they are the column's
footer totals, not shipments.

### Blast radius — measured, rule OFF vs ON in one process

```
Enterprise (B2B), 327 rows : all six note columns 0.00        OK
Processing Centre, 13 rows : Actual DN 601,165.64 unchanged   OK
                             Actual CN 723,852.50 unchanged   OK
FY Sales / Purchases / GM / CN / DN : no vertical moves
Enterprise Details vs manual : 230 shipments, 0 differ
```

**A NO-OP on this MIS** — Enterprise B2B already carried no notes. It is a
guard for future data, not a correction. `ENTERPRISE_NO_NOTES = False` turns it
off.

## 2. IT AD: 'Revenue Per Kg' and 'Purchase Cost Per Kg' removed

`reports.HIDDEN_SUMMARY_ROWS` / `reports.drop_hidden_summary_rows`, called from
`app.py` right after `insert_transport_row`.

IT AD counts DEVICES, not weight, so its Quantity row is a unit count and a
"per Kg" figure reads as rupees-per-device — meaningless, and the manual does
not carry it either.

DISPLAY-ONLY: nothing is recomputed. It runs LAST, after `apply_frozen`,
`_recompute_fy`, the Enterprise op-cost override and `insert_transport_row` —
all of which index the fixed summary layout by POSITION. Dropping a row any
earlier would shift those indices and silently corrupt frozen months.

```
IT AD          30 -> 28 rows
AFR / End Generator / Plastic / Enterprise / Re-Commerce : 30 -> 30, untouched
idempotent : yes
```

NOTE: `Transportation Charges Per Kg` is still on IT AD — only the two rows
named were asked for. Say the word if it should go too.

## Found while verifying — NOT fixed (nobody asked)

**Re-Commerce Purchases is not reproducible.** Three identical runs of the same
MIS gave 61,353,713 / 61,350,001 / 61,358,750 — a spread of about Rs 8,749.
Pinning `PYTHONHASHSEED=0` gives 61,356,326 every time, which identifies the
cause as set-iteration order.

`cleaning.py` line 535: `amz_bills = amazon_map.get(inv_no, set())`, then
`lines = [ln for b in amz_bills for ln in amz_idx.get((b, nm), [])]`.
`amazon_map`'s values are `set` objects (`defaultdict(set)`, line 262). Python
randomises string hashing per process, so when one Recykal invoice maps to
several Amazon bills the lines come out in a different order each run, and
`_take_lines(lines, q)` — which consumes lines until quantity `q` is met —
takes different lines at different prices.

One-word fix (`sorted(amz_bills)`), NOT applied. Sales and every other vertical
are stable; only Re-Commerce Purchases moves.

---

# 2026-08-14 — The 3rd debit note is now visible (label only)

`cleaning._pivot_to_wide` -> new `{prefix}_2_Numbers_All`; `compute` uses it for
the `Debit Note No. 2` cell.

## Why

Five End Generator shipments carry THREE debit notes. Slot 2's SubTotal already
summed every remaining note — the amounts were always right — but the slot
showed only ONE note number, so the sheet read as 2 notes against a 3-note
figure. `SH04261402`: slot 1 = `27VC00037` 4,594.92, slot 2 = `27VC00048`
**28,699.96**, which is 4,273.96 (00048) + 24,426.00 (00060). Total 33,294.88 =
the MIS sum of all three, to the paisa.

## What changed

Where slot 2 collapses 2+ notes, cleaning now also records them joined with
' & ', and that string is shown in `Debit Note No. 2` — the way the manual
writes it ("36/MET/27VC00048 & 00060").

**The real `DN_2_Vendor_Credit_Number` column is untouched.** Live logic matches
note numbers against it with `.isin` (the freight-credit routing in
`build_profitability`) and would stop matching a joined string. The label is a
separate column, blank on every 1- or 2-note shipment.

## Verified — the only thing that may move is the label

```
Details frame, all 107 columns, cell by cell : ONLY 'Debit Note No. 2' differs
                                               (5 rows)
numeric columns whose TOTAL moved            : 0
summary cells moved (all tabs)               : 0
freight routing, with dn_df passed so it
  actually runs                              : 4 rows, -18,609.50 before AND after
Actual DN total       1,679,952.87 before AND after
Total Cost total    182,211,521.83 before AND after
```

Relabelled rows, amounts unchanged:

```
SH04261402  27VC00048  ->  27VC00048 & 27VC00060   ActualDN 28,216.00
SH04262106  27VC00058  ->  27VC00058 & 27VC00088   ActualDN 39,182.26
SH05260302  27VC00085  ->  27VC00085 & 27VC00090   ActualDN 12,511.55
SH05260304  27VC00092  ->  27VC00092 & 27VC00093   ActualDN 13,832.66
SH05260303  27VC00086  ->  27VC00086 & 27VC00091   ActualDN 14,027.70
```

## Clears an earlier open item

The 5 End Generator notes previously flagged as "manual's Actual DN doesn't
match the note in Zoho" (`27VC00037/00054/00081/00082/00087`) were never
mismatches. They are these same multi-note shipments: the manual's figure is the
sum of ALL the notes, and the earlier check compared it against just one. Every
one agrees with us to within a rupee. **Off the open list.**

## Scope

DN only. No shipment in this MIS has 3+ credit notes (DN: 5 shipments, CN: 0),
so the CN side has nothing to show; `CN_2_Numbers_All` is emitted by the same
helper but is not wired to any output column.

---

# 2026-08-14 — GST is stripped from a vendor credit only when the credit HAS GST

`compute.build_profitability` (new `dn_raw_df` arg); both `app.py` call sites.

## Rule

Zoho's vendor-credit `SubTotal` is DOCUMENT level (repeated on every line of the
note) and folds the tax lines in, so it is GST-inclusive **only when the note
actually carries CGST/SGST/IGST lines**. A note exported with no tax line is
already the ex-GST goods value; dividing it by 1.18 strips a tax that was never
charged.

## Why

`MP/AFR/OFF/0001`, from the 09-Aug MIS:

```
DebitNotes   36/AFR/27VC00020   SubTotal 23,217.00   Marketplace Purchases (AFR)
CreditNotes  36/AFR/27CN00020   SubTotal 23,217.00   Marketplace Sales (AFR)
```

One line each, no tax row on either. The engine took the CREDIT note as 23,217
and divided the DEBIT note to 19,675.42 — the same number treated two ways —
overstating that shipment's cost by 3,541.58 (manual 115,843, ours 119,384.58).

Evidence for the rule, over every debit note the manuals actually book:

```
notes WITHOUT tax lines : manual = SubTotal          1 of 1  (never SubTotal/1.18)
notes WITH tax lines    : manual = SubTotal / 1.18  29 of 41
```

## Implementation note

`clean_dn` keeps `Marketplace*` accounts only, so the tax lines survive ONLY on
the RAW Vendor Credit sheet — the test needs `dn_raw_df`, not `dn_df`. With no
raw sheet passed the divisor falls back to the old flat 1.18, so figures never
move silently.

## Verified on the 09-Aug MIS

3 rows of 3,517 change — every one a note with no tax line:

```
MP/AFR/OFF/0001       AFR      DN 19,675.42 -> 23,217.00   cost 119,384.58 -> 115,843.00
36/MPPET/27/OFF/0001  Plastic  DN 33,406.78 -> 39,420.00   cost  82,093.22 ->  76,080.00
36/MPPET/27/OFF/0002  Plastic  DN  1,484.75 ->  1,752.00   cost  73,515.25 ->  73,248.00
```

AFR against its till-09-08 manual, FY Total:

```
              manual      before   gap        after   gap
Purchases  3,493,671   3,497,212  +3,541   3,493,671    0
Gross Mgn    289,279     285,738  -3,541     289,279    0
Sales      3,782,949   3,782,949       0   3,782,949    0
```

**AFR closes to exactly zero.** With the till-09-08 manual in the folder the
open month is Aug-26 and every AFR line — Sales, Purchases, Gross Margin AND
Receivable, every month — matches the manual.

Plastic: the two affected shipments do not appear in the till-31-07 Plastic
manual, so there is no manual reference for them; the rule is identical and both
notes are from `DISTRICT TOURISM DEVELOPMENT OFFICER (Rudraprayag)`, a
government body with no GST. Plastic's own large pre-existing gap is unrelated
and unchanged by this.

---

# 2026-08-14 — IT AD's old `26/MITAD/` invoices reach IT AD's receivable

`reports._AR_TOKEN_TAB`

## Why

`_ar_token_tab` maps an AR invoice's middle segment to a vertical by SUBSTRING,
which handles both the current prefixes and last year's `MP…` ones —
`mpafr`→afr, `mppet`→pet, `mpmet`→met. But ITAD's old prefix is `26/MITAD/…`,
and **"mitad" does not contain "iad"**. Those invoices matched no rule, were not
in the current Details either (prior-FY, so the exact-invoice path also missed),
and so were attributed to NO vertical at all.

On the 09-Aug MIS that silently dropped 7 IT AD invoices worth Rs 22,97,740.22:

```
26/MITAD/INV0163  30-Sep-2025  BLACK GOLD RECYCLING    675,588.69
26/MITAD/INV0167  30-Sep-2025  BLACK GOLD RECYCLING      6,735.59
26/MITAD/INV0168  09-Oct-2025  BLACK GOLD RECYCLING    453,083.80
26/MITAD/INV0169  09-Oct-2025  BLACK GOLD RECYCLING      4,507.83
26/MITAD/INV0284  26-Mar-2026  RETECK ENVIROTECH       611,474.49
26/MITAD/INV0285  28-Mar-2026  RETECK ENVIROTECH       223,266.58
26/MITAD/INV0286  28-Mar-2026  RETECK ENVIROTECH       323,083.24
```

## Fix

Added `("itad", "IT AD")` alongside `("iad", "IT AD")`. Only "mitad"/"itad"
contain "itad", so it cannot mis-hit another vertical.

## Verified

Token mapping, 11 cases: only `26/MITAD/…` changes — `mpafr`, `mppet`, `mpmet`,
`36/IAD/…`, `36/AFR/…`, `36/MET/…`, `27/IB/…`, `36/PET/…`, `26/MPPIB/…` all
unchanged. `26/MPRE/…` deliberately still unattributed (Account Transactions
calls it ReWerse while the AR sheet's customer column calls it Metal/Plastic —
those two disagree, so it is left alone pending a decision).

Summary impact: **12 cells, all IT AD, all on the two bifurcation rows.** No
other vertical moves at all.

```
IT AD  FY 27 Receivables              Jul   266,135 ->  27,625
IT AD  Old Receivables (pre-Apr)      Jul         0 -> 238,510
IT AD  FY 27 Receivables              Aug 1,413,564 -> 423,856
IT AD  Old Receivables (pre-Apr)      Aug         0 -> 989,708
```

## What this does NOT fix

The parent `Receivables (exl Legacy)` row is unchanged — the TOTAL was already
right; what was wrong was the FY-27 vs pre-April split, which now reports
correctly. IT AD's July receivable is still 266,135 against the manual's
1,423,960. That difference is the three RETECK invoices (Rs 11,57,824.31, dated
26-28 March 2026): the month column excludes pre-April balances by the
"exl Legacy" rule, and the manual includes them. Same class as AFR's ATTAQUANT
row (Rs 20,780). Open question — not changed here.

---

# 2026-08-14 — End Generator: three fixes (full-reversal, op cost, SH072602017)

`compute.py`

## 1. A fully-reversed vendor DN was credited TWICE

Two independent paths both credit back a full return:

* the **vendor-DN** path books the returned leg as a Full Debit Note (`AJ`) and
  removes that note from Actual DN, and
* the **sales-side** path (`_full_rev`, CN >= 95% of the sale) caps Actual DN to
  the whole purchase `Q` "so the cost nets to 0".

When BOTH fire, the purchase is credited back twice. `SH072621010` (REDDY PAI
METALS, whole 12,380 Kg load returned on two notes):

```
1,361,800 purchase + 45,100 freight - 1,361,800 (AJ) - 1,361,800 (AK) = -1,316,700
```

A **negative Total Cost** on a shipment with a positive purchase. Fixed by
skipping the `_full_rev` cap on rows the vendor-DN path already handled
(`_dn_rev > 0`); the shipment's remaining partial note keeps its own ex-GST
value.

Measured against HEAD: **1 row of 3,517 changes.** Negative-cost rows 3 -> 2.

```
SH072621010   ActualDN 1,361,800 -> 30,278   TotalCost -1,316,700 -> 14,822
```

The manual shows 22,600; the residual 7,778 is the manual hand-reducing that
shipment's freight to 22,600 against the bill's actual 45,100 (SUNDAR TRANSPORT
45,000 + 100) — their edit, not ours.

## 2. Operational cost — `OPERATIONAL_COST_PER_KG`

The manual charges Rs 1.80 per Kg of NET purchase quantity on three July
S K TRADING CO loads, totalling its Jul Operational Cost row exactly:

```
SH072627010  29,740 x 1.80 = 53,532
SH07262901   29,590 x 1.80 = 53,262
SH07262902   21,690 x 1.80 = 39,042
                             -------
                             145,836
```

**The trigger is NOT derivable.** Supplier alone does not explain it — the June
S K TRADING CO shipment `SH06261702` (19,630 Kg) carries no operational cost,
and no non-S K TRADING shipment carries one. Rather than guess a rule and have
it spread wrongly, the three shipments the manual actually charges are listed
explicitly. **Add new shipments each month, or replace the dict with the real
rule once the business states it.**

## 3. Hand-entered provisions — `MANUAL_PROVISIONS`

`SH072602017` carries 1,668,964 / 1,559,799 in the manual — 37.1% and 34.6% of
base, where the End Generator rate gives 204,569 / 205,302 (4.55%). Not any
rate, so it was typed in; it reads as an expected large return not yet raised as
a note. Mirrored per-shipment, and applied ONLY while the shipment has no actual
CN/DN, so it stands down by itself when the real note arrives.

## Result — End Generator FY, engine vs the till-09-08 manual

```
                     manual        before        gap        after       gap
Sales            65,458,988    66,813,486  +1,354,498   65,458,989        +1
Purchases        63,332,714    64,792,064  +1,459,350   63,327,669    -5,045
Gross Margin      2,126,274     2,021,421    -104,853    2,131,319    +5,046
Operational Cost    145,836             0    -145,836      145,836         0
```

**FY Sales closes to Rs 1.** Blast radius: 5 rows, ALL End Generator (1 from fix
1, 4 from fixes 2+3). No other vertical moves.

## Left open

* Transportation Charges Jul still -60,000 against the manual — not diagnosed.
* Purchases/GM residual ~5,045, largely the SH072621010 freight edit above.
* The 3 op-cost shipments' Details **Total Cost** still excludes the operational
  cost (the manual adds it there). The SUMMARY is correct either way, because
  the manual's own Purchases line excludes it too (its Sales - Purchases = its
  Gross Margin exactly). Display difference only.
* Two negative-cost rows remain and were NOT touched: `MP/RECM/0002`
  (Re-Commerce — out of bounds by instruction) and `SH07260704` (ReWerse — out
  of scope). Different cause from fix 1.

---

# 2026-08-16 — Report-owner feedback: ITAD quantity + M4 transport charge

Both changes requested by the report owner after reviewing the 09-Aug run.

## 1. IT AD — stop converting weight items to MT (`ITAD_KG_ITEMS_TO_MT = False`)

IT AD carries a few WEIGHT items ('ITAD Plastic waste', 'Mix E-Waste (ITAD)') in
Kg while the rest of the vertical is a device count. The engine converted those
rows to MT (÷1000). The signed-off report does NOT — it sums the raw Kg
alongside the unit counts.

The mismatch is what pushed the summary's open-month quantity NEGATIVE: frozen
months carried the manual's raw Kg while live months carried the converted
figure, and the open month is a balancing plug, so it absorbed the difference as
**IT AD Aug-26 = −517**.

```
IT AD Quantity     Apr-26     May-26     Jun-26     Jul-26   Aug-26
before           5,053.00     117.00   3,549.00   3,303.00   692.00
after            5,053.00   1,326.00   3,549.00  41,566.00   692.00
manual           6,453.55   1,326.00   3,549.26  41,566.40   692.00
```

Negatives gone; May/Jun/Jul/Aug match. April is still 1,400.55 out on an
UNFROZEN run — open, to chase against the 16-Aug files.

Left as a switch so it can be restored without archaeology.

## 2. Reco Items — a freight line on an invoiced shipment is not an orphan

`reports._itad_reco_mask`

An "orphan bill" line whose SHIPMENT already carries a sale is not a one-sided
trade — it is a cost component of a completed one. M4's `SH07262906` bill
`ACE/26-27/0152` has 'Polo T Shirt' 35 @ 480 (invoiced) plus 'Transport Charge'
1 @ 1,500 (never invoiced on its own). The transport line was held back for
review while the manual carries it in Details, so the shipment's cost came out
Rs 1,500 short.

Now only shipments with NO sale at all stay candidates — the same principle
already applied to blank-shipment charge legs that match by material.

```
reco candidates 70 -> 63 (7 lines freed): M4 Transport Charge x6 (13,900),
                                          Metal MS Scrap x1 (894,955)
M4 FY Purchases 241,520 -> 255,420   = the manual's figure exactly
```

Still correctly gated: IT AD `SH08261003` and Enterprise `SH082607013` — both
genuine purchases with no sale. IT AD / End Generator / Plastic FY Purchases
unchanged.
