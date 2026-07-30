# Changes & Rules Log

Running record of every change made to this app outside the `app.py` build tag,
with the **rule** each change encodes and the **evidence** it was verified against.

Append newest at the top. Never delete an entry — supersede it.

House rules that govern everything below (from `CLAUDE.md`):
never fabricate, estimate or date-shift data · closed (frozen) months must never
silently change · secrets stay out of git · after any change, cross-check one
vertical against its signed-off manual file before rollout.

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
