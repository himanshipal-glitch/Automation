"""
Management Summary Reports
Generates supplier-wise, buyer-wise, material-wise, monthly, weekly
and top-N ranking summaries from the profitability DataFrame.

All functions accept the raw profitability DataFrame (exact column names, including
duplicates) and return clean summary DataFrames ready for display / download.
"""

import io
import re as _re
import pandas as pd
import numpy as np
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY-WISE PROFITABILITY SPLIT
# ══════════════════════════════════════════════════════════════════════════════

def _fifo_net_unused(sub: pd.DataFrame) -> float:
    """Receivable total AFTER applying each customer's unused credit balance
    against their OWN open invoices, oldest invoice date first (FIFO) — a
    credit settles the oldest outstanding bill before spilling onto newer ones.
    `sub` is an AR-aging subset (one or more invoice rows per customer)."""
    import receivables as _recv
    bal_c  = _recv._col(sub, "balance")
    cust_c = _recv._col(sub, "customer_name", "customer name")
    if not bal_c:
        return 0.0
    if not cust_c:
        return float(pd.to_numeric(sub[bal_c], errors="coerce").fillna(0).sum())
    un_c   = _recv._col(sub, "unused_credits_receivable_amount", "unused_credits")
    date_c = _recv._col(sub, "date")

    d = sub.copy()
    d["_bal"]    = pd.to_numeric(d[bal_c], errors="coerce").fillna(0.0)
    d["_cust"]   = d[cust_c].astype(str).str.upper().str.strip()
    d["_unused"] = pd.to_numeric(d[un_c], errors="coerce").fillna(0.0) if un_c else 0.0
    d["_dt"]     = pd.to_datetime(d[date_c], errors="coerce") if date_c else pd.NaT

    total = 0.0
    for _, grp in d.groupby("_cust"):
        credit = float(grp["_unused"].max())            # one credit value per customer
        for _, row in grp.sort_values("_dt", na_position="last").iterrows():  # oldest first
            bal = float(row["_bal"])
            if credit > 0 and bal > 0:
                applied = min(bal, credit)
                bal -= applied
                credit -= applied
            total += bal
    return total


def _ib_has_vendor_invoice(df: pd.DataFrame, ship: pd.Series) -> pd.Series:
    """Per-row boolean: does this shipment have ANY vendor (purchase) invoice?
    Enterprise shipments with only logistics bills and no material purchase invoice
    are dropped. A shipment qualifies if any of its rows has a non-blank Vendor
    Invoice No. or a non-zero Purchase Price."""
    def _pick(cands, pos):
        norm = {"".join(c for c in str(col).lower() if c.isalnum()): col for col in df.columns}
        for cand in cands:
            k = "".join(c for c in cand.lower() if c.isalnum())
            if k in norm:
                return df[norm[k]]
        return df.iloc[:, pos] if pos < df.shape[1] else pd.Series("", index=df.index)

    vinv = _pick(["Vendor Invoice No.", "Vendor Invoice No"], 6).astype(str).str.strip()
    ppx  = pd.to_numeric(_pick(["Purchase Price"], 15), errors="coerce").fillna(0)
    has_inv = (~vinv.isin(["", "nan", "None", "NaT"])) | (ppx != 0)
    return has_inv.groupby(ship).transform("max").astype(bool)


def parse_dates(s: pd.Series) -> pd.Series:
    """Parse a Date column that mixes ISO (YYYY-MM-DD) and Indian (DD-MM-YYYY)
    strings. ISO is tried FIRST — running dayfirst over ISO silently swaps
    day/month for days ≤ 12 (2026-04-12 → Dec 4!); dayfirst applies only to
    the non-ISO leftovers."""
    s = s.astype(object)
    d = pd.to_datetime(s, errors="coerce", format="ISO8601")
    miss = d.isna()
    if miss.any():
        d2 = pd.to_datetime(s[miss], errors="coerce", dayfirst=True, format="mixed")
        d.loc[miss] = d2
    return d


# AR invoice numbers counted in ENTERPRISE receivables regardless of the
# B2B/Warehouse shipment split (manually confirmed Enterprise invoices that
# carry MPIB-style numbering). The receivables rule itself is unchanged —
# these are simply added to the Enterprise invoice set.
ENTERPRISE_EXTRA_AR_INVOICES: set = {
    "26/MPPIB/DN0005",
    "26/MPPIB/INV0553",
    "26/MPPIB/INV0581",
    "26/MPPIB/INV0599",
    "26/MPPIB/INV0603",
    "27/MPIB/26IN0216",
    "26/MPPIB/INV0886",
    "27/MPIB/26IN0229",
    "26/MPPIB/INV0895",
    "27/MPIB/26IN0231",
    "27/MPIB/26IN0230",
}


def _ib_warehouse_set() -> set:
    """The persistent IB(Warehouse) shipment list (uppercased). Currently
    DORMANT — the split uses the SH heuristic (see _ib_split_masks); the store
    stays available for a future membership-based rule."""
    try:
        import database as _db
        return {str(s).strip().upper() for s in _db.load_ib_warehouse_shipments()}
    except Exception:
        return set()


CUSTOM_DUTY_COST_SOURCE = "Custom Duty (manual entry)"
CUSTOM_DUTY_VENDOR = "BLACK GOLD RECYCLING PRIVATE LIMITED"


def _custom_duty_mask(df: pd.DataFrame) -> pd.Series:
    """Rows that are manually-entered Custom Duty bills (no shipment id) —
    identified by their Cost Source marker. Normalized column lookup handles
    both 'Cost Source' and the session store's 'Cost_Source'."""
    cs_col = next((c for c in df.columns
                   if "".join(ch for ch in str(c).lower() if ch.isalnum()) == "costsource"), None)
    if cs_col is None:
        return pd.Series(False, index=df.index)
    return df[cs_col].astype(str).str.strip().eq(CUSTOM_DUTY_COST_SOURCE)


def _ib_split_masks(mask: pd.Series, ship: pd.Series,
                    df: pd.DataFrame | None = None) -> tuple[pd.Series, pd.Series]:
    """(b2b, warehouse) row masks within Institutional Business.

    B2B = SH-prefixed EXCEPT internal 'MPIB' ones (warehouse/internal
    transfers), requiring a vendor invoice when `df` is given;
    Warehouse = non-SH OR containing 'MPIB'.
    Custom-Duty line items (manual purchases, NO shipment id) are ALWAYS B2B."""
    _sh = ship.astype(str).str.strip().str.upper()
    b2b = mask & _sh.str.startswith("SH") & ~_sh.str.contains("MPIB", na=False)
    wh  = mask & (~_sh.str.startswith("SH") | _sh.str.contains("MPIB", na=False))
    if df is not None:
        b2b = b2b & _ib_has_vendor_invoice(df, ship)
        _cd = mask & _custom_duty_mask(df)
        if _cd.any():
            b2b = b2b | _cd
            wh  = wh & ~_cd
    return b2b, wh


def inject_custom_duty(profit_df: pd.DataFrame, cd: pd.DataFrame) -> pd.DataFrame:
    """Append the Enterprise Custom Duty bills as profitability rows — same
    shape as the manual report's line items: BLANK Shipment ID, the supplier
    name (e.g. 'Customs duty') on the vendor column, purchase cost only.
    cd columns: 0 = Month (mmm-yy), 1 = Supplier Name, 2 = Amount."""
    if cd is None or getattr(cd, "empty", True) or profit_df.empty:
        return profit_df
    _mdt = pd.to_datetime(cd.iloc[:, 0].astype(str).str.strip(),
                          format="%b-%y", errors="coerce")
    rows = []
    for i in range(len(cd)):
        if pd.isna(_mdt.iloc[i]):
            continue
        r = {c: None for c in profit_df.columns}
        dt = _mdt.iloc[i]
        r[profit_df.columns[1]]  = dt.strftime("%B")             # Month
        r[profit_df.columns[2]]  = dt.strftime("%Y-%m-%d")       # Date (1st of month)
        r[profit_df.columns[3]]  = ""                            # NO Shipment ID
        # Vendor: the manual report books these bills under Black Gold — a
        # generic/blank supplier entry ("customs duty" etc.) displays that name;
        # a real vendor typed by the user is kept as-is.
        _sup = str(cd.iloc[i, 1]).strip() if cd.shape[1] > 2 else ""
        if not _sup or "custom" in _sup.lower() or "duty" in _sup.lower():
            _sup = CUSTOM_DUTY_VENDOR
        if profit_df.shape[1] > 4:
            r[profit_df.columns[4]] = _sup                       # Supplier / Vendor Name
        r[profit_df.columns[85]] = "Institutional Business"      # → Enterprise (forced B2B)
        amt = float(pd.to_numeric(pd.Series([cd.iloc[i, -1]]),
                                  errors="coerce").fillna(0).iloc[0])
        # normalized lookup — the session store sanitizes names ('Purchase Price'
        # → 'Purchase_Price'); an exact-name check silently skipped the amount
        # and the Cost Source marker there, so the summary never saw the bill.
        def _named(name):
            key = "".join(ch for ch in name.lower() if ch.isalnum())
            return next((c for c in profit_df.columns
                         if "".join(ch for ch in str(c).lower() if ch.isalnum()) == key), None)
        _pp, _cs, _rn = _named("Purchase Price"), _named("Cost Source"), _named("Resale Note")
        _mt = _named("Material")
        if _pp is not None:
            r[_pp] = amt
        if _mt is not None:
            r[_mt] = "Custom Duty"                               # material, like the manual
        if _cs is not None:
            r[_cs] = CUSTOM_DUTY_COST_SOURCE
        if _rn is not None:
            r[_rn] = "Custom Duty bill — manual purchase, no invoice/bill in Zoho"
        rows.append(r)
    if not rows:
        return profit_df
    return pd.concat([profit_df, pd.DataFrame(rows, columns=profit_df.columns)],
                     ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# COLUMN GUIDE — what each report column is, which SIDE it comes from, and its
# GST treatment. Written as a sheet into every downloaded workbook.
# Side: where the data originates. GST: Excl = Zoho subtotal (before GST).
# ══════════════════════════════════════════════════════════════════════════════
COLUMN_GUIDE = [
    # (Column, Side / Source, GST, What it is)
    ("Quarter",                "Key — derived",            "—", "Fiscal quarter of the invoice date"),
    ("Month",                  "Key — derived",            "—", "Invoice month (full name)"),
    ("Date",                   "Buyer (Invoice)",          "—", "Invoice date — drives month bucketing"),
    ("Shipment ID",            "Key — Zoho SO",            "—", "CF.SO Number linking invoice and bill"),
    ("Supplier Name",          "Seller (Bill)",            "—", "Vendor on the purchase bill"),
    ("GST Reg No.",            "Seller (Bill)",            "—", "Supplier GSTIN"),
    ("Vendor Invoice No.",     "Seller (Bill)",            "—", "Bill number"),
    ("Vendor Invoice Date",    "Seller (Bill)",            "—", "Supplier invoice date (CF)"),
    ("P V No.",                "Seller (Bill)",            "—", "Purchase voucher no. (CF)"),
    ("P V Date",               "Seller (Bill)",            "—", "Purchase voucher date (CF)"),
    ("State (Origin)",         "Seller (Bill)",            "—", "Source of supply"),
    ("Vehicle No.",            "Seller (Bill)",            "—", "Vehicle (CF)"),
    ("Material",               "Key — item",               "—", "Item name (joins invoice↔bill)"),
    ("Qty (Kg)",               "Seller (Bill)",            "—", "Purchased quantity in Kg"),
    ("Price/Kg",               "Seller (Bill)",            "Excl. GST", "Material rate agreed with supplier = Purchase Price ÷ Qty"),
    ("Purchase Price",         "Seller (Bill)",            "Excl. GST", "Material purchase amount (bill subtotal)"),
    ("Return Qty",             "Computed (purchase side)", "—", "Qty returned to supplier (from large DNs)"),
    ("Net Qty",                "Computed (purchase side)", "—", "Purchased qty − returns"),
    ("Basic Customs Duty",     "Seller (Bill)",            "Excl. GST", "Customs duty on imports (rarely used)"),
    ("Transporter Name",       "Logistics (Bill)",         "—", "Transport vendor"),
    ("LR NO/BILL NO",          "Logistics (Bill)",         "—", "Lorry receipt / bill no."),
    ("J V No.",                "Logistics (Bill)",         "—", "Journal voucher no."),
    ("JV Date",                "Logistics (Bill)",         "—", "Journal voucher date"),
    ("Logistics cost",         "Logistics (Bill)",         "Excl. GST", "Actual transport charge billed"),
    ("Debit note on logistic cost", "Logistics (DN)",      "Excl. GST", "Vendor DN recovering logistics"),
    ("Logistics Provision",    "Computed",                 "Excl. GST", "Estimated logistics (zero when actual exists)"),
    ("Total Logistics Cost",   "Computed",                 "Excl. GST", "Actual + provision − DN on logistics"),
    ("Operational Cost",       "Computed",                 "Excl. GST", "Vertical overhead allocated to the row"),
    ("Cost/Kg.",               "Computed",                 "Excl. GST", "OPERATIONAL COST PER KG — landed cost: (Purchase Price + Total Logistics) ÷ Net Qty"),
    ("Divertion/Internal",     "Computed (purchase side)", "—", "Internal diversion adjustment (purchase)"),
    ("Debit Note No.",         "Seller side (Vendor Credit)", "—", "1st vendor DN number"),
    ("Debit Note Date.",       "Seller side (Vendor Credit)", "—", "1st vendor DN date"),
    ("Debit Note No. 2",       "Seller side (Vendor Credit)", "—", "2nd DN (aggregates ALL remaining notes)"),
    ("Debit Note Date. 2",     "Seller side (Vendor Credit)", "—", "2nd DN date"),
    ("Full Debit Note",        "Computed",                 "Excl. GST", "DN treated as full purchase reversal (≥ threshold)"),
    ("Actual Debit Note",      "Seller side (Vendor Credit)", "Excl. GST", "Sum of ALL actual vendor DNs on the shipment"),
    ("Provision for DN",       "Computed",                 "Excl. GST", "Estimated future DN (per-vertical rate; zero if actual exists / excluded)"),
    ("Total Cost",             "Computed",                 "Excl. GST", "Purchase + logistics + diversion + full DN + customs − actual DN − DN provision"),
    ("Inv. Date",              "Buyer (Invoice)",          "—", "Sales invoice date"),
    ("Inv. No.",               "Buyer (Invoice)",          "—", "Sales invoice number"),
    ("Customer ID",            "Buyer (Invoice)",          "—", "Zoho customer id"),
    ("Buyer Name",             "Buyer (Invoice)",          "—", "Customer sold to"),
    ("Buyer GST Number ",      "Buyer (Invoice)",          "—", "Buyer GSTIN"),
    ("Location (Origin)",      "Buyer (Invoice)",          "—", "Dispatch from (CF)"),
    ("Location (Destination)", "Buyer (Invoice)",          "—", "Shipping city"),
    ("State (Destination)",    "Buyer (Invoice)",          "—", "Shipping state"),
    ("Qty(Kg)",                "Buyer (Invoice)",          "—", "Sold quantity in Kg (units for IT AD / Re-Commerce)"),
    ("Rate/Kg",                "Buyer (Invoice)",          "Excl. GST", "Sale rate per Kg"),
    ("Amount",                 "Buyer (Invoice)",          "Excl. GST", "Sales amount (invoice subtotal)"),
    ("Qty Check",              "Computed",                 "—", "Purchase-vs-sales quantity check"),
    ("Return Qty",             "Computed (sales side)",    "—", "Qty returned by buyer (from large CNs)"),
    ("Net Qty",                "Computed (sales side)",    "—", "Sold qty − buyer returns"),
    ("Divertion/Internal",     "Computed (sales side)",    "—", "Internal diversion adjustment (sales)"),
    ("Return Type",            "Manual note",              "—", "Analyst's return classification (blank in engine)"),
    ("Date : DN to Buyer",     "Manual note",              "—", "DN-to-buyer date (blank in engine)"),
    ("DN to Buyer",            "Manual note",              "—", "DN-to-buyer ref (blank in engine)"),
    ("Amount",                 "Computed (DN to buyer)",   "Excl. GST", "DN-to-buyer amount"),
    ("Credit Note No:1",       "Buyer side (Credit Note)", "—", "1st customer CN number"),
    ("CN Date. No:1",          "Buyer side (Credit Note)", "—", "1st CN date"),
    ("Credit Note No:2",       "Buyer side (Credit Note)", "—", "2nd CN (aggregates ALL remaining notes)"),
    ("CN Date. No:2",          "Buyer side (Credit Note)", "—", "2nd CN date"),
    ("Full Credit Notes",      "Computed",                 "Excl. GST", "CN treated as full sale reversal (≥95%)"),
    ("Actual Credit Note",     "Buyer side (Credit Note)", "Excl. GST", "Sum of ALL actual customer CNs on the shipment"),
    ("Provision for CN",       "Computed",                 "Excl. GST", "Estimated future CN (End Generator 4.55%, Plastic 2.5%; zero if actual/excluded)"),
    ("Net Revenue",            "Computed",                 "Excl. GST", "Sales − actual CN − CN provision − full reversals"),
    ("Margin",                 "Computed",                 "Excl. GST", "Net Revenue − Total Cost (row margin, without GST)"),
    ("Reamrks - Margin",       "Computed",                 "—", "Margin remark"),
    ("Remarks",                "Computed",                 "—", "Per-shipment: Finance Up Charge / Divertion / Full Rejection / DN & CN Issued / DN & CN Provision / No Debit Note"),
    ("LMI @ Inception",        "Computed",                 "Excl. GST", "Margin at inception (before notes)"),
    ("Remarks @ Inception",    "Computed",                 "—", "Inception remark"),
    ("Margin (%)",             "Computed",                 "—", "Margin ÷ Net Revenue"),
    ("Margin Bucket",          "Computed",                 "—", "Margin band classification"),
    ("Total CN(Inc.Provisions)","Computed",                "Excl. GST", "Actual CN + CN provision"),
    ("Total DN(Inc.Provisions)","Computed",                "Excl. GST", "Actual DN + DN provision"),
    ("Check",                  "Computed",                 "—", "Internal consistency check"),
    ("Actaul CN",              "Buyer side (Credit Note)", "Excl. GST", "Actual CN total (display copy)"),
    ("Actual DN",              "Seller side (Vendor Credit)", "Excl. GST", "Actual DN total (display copy)"),
    ("Check",                  "Computed",                 "—", "Internal consistency check (2nd)"),
    ("Material-Short Form",    "Manual note",              "—", "Analyst's short code (blank in engine)"),
    ("Supplier Type",          "Manual note",              "—", "Analyst's supplier classification (blank in engine)"),
    ("Month",                  "Key — derived",            "—", "Month in mmm-yy (2nd Month column)"),
    ("Cost",                   "Computed",                 "Excl. GST", "Total Cost copy for pivots"),
    ("Revenue",                "Computed",                 "Excl. GST", "Net Revenue copy for pivots"),
    ("Week No:",               "Key — derived",            "—", "ISO week of the invoice date"),
    ("Category (Material)",    "Manual note",              "—", "Analyst's material category (blank in engine)"),
    ("Broad Category",         "Buyer (Invoice)",          "—", "Vertical — parsed from the invoice Account"),
    ("POC Name",               "Manual note",              "—", "Analyst's POC (blank in engine)"),
    ("Gross Margin",           "Computed",                 "Excl. GST", "Revenue − Cost (gross)"),
    ("Recykal Margin",         "Computed",                 "Excl. GST", "Recykal share of margin"),
    ("Net Margin",             "Computed",                 "Excl. GST", "Net Revenue − Total Cost"),
    ("Sales ",                 "Computed — GST block",     "INCL. GST (×1.18)", "Sales with GST"),
    ("Purchases",              "Computed — GST block",     "INCL. GST (×1.18)", "Purchases with GST (negative = cost)"),
    ("Credit Note",            "Computed — GST block",     "INCL. GST (×1.18)", "CN with GST (negative)"),
    ("Debit Note",             "Computed — GST block",     "INCL. GST (×1.18)", "DN with GST (positive recovery)"),
    ("Margin",                 "Computed — GST block",     "INCL. GST", "Margin with GST (3rd Margin column)"),
    ("Bill Branch",            "Seller (Bill)",            "—", "Branch on the bill"),
    ("Inv Branch",             "Buyer (Invoice)",          "—", "Account on the invoice"),
    ("Vendor PAN No",          "Seller (Bill)",            "—", "Supplier GSTIN (PAN embedded)"),
    ("Customer PAN No",        "Buyer (Invoice)",          "—", "Buyer GSTIN (PAN embedded)"),
    ("GST TDS Applicability",  "Manual note",              "—", "Analyst's TDS flag (blank in engine)"),
    ("Cash Discount(Provision)","Manual note",             "Excl. GST", "Cash-discount provision (blank in engine)"),
    ("Cash Discount",          "Manual note",              "Excl. GST", "Actual cash discount (blank in engine)"),
    ("Cash Discount. No",      "Manual note",              "—", "Cash-discount ref (blank in engine)"),
    ("CD Date",                "Manual note",              "—", "Cash-discount date (blank in engine)"),
    ("SD",                     "Manual note",              "—", "Security deposit note (blank in engine)"),
    ("Cost Source",            "Computed — provenance",    "—", "Where the row's cost came from: Current Bill / Amazon chain / Older bill / blank = no cost found"),
    ("Resale Note",            "Computed — provenance",    "—", "Resold-item flag (return-to-seller → resale, original cost carried)"),
    ("Row Source",             "Computed — provenance",    "—", "Manual file (frozen month) vs Live (MIS) — which source produced this row"),
]


def _is_mp_ship(ship: pd.Series) -> pd.Series:
    """True where a Shipment/SO id is an MP (warehouse/marketplace-internal)
    movement. Zoho sometimes writes these with a numeric prefix — e.g.
    '36/MPPET/27/OFF/0001' — so strip a leading 'NN/' before checking 'MP'."""
    u = ship.astype(str).str.strip().str.upper()
    core = u.str.replace(r"^\d+/", "", regex=True)
    return core.str.startswith("MP")


# Verticals that KEEP their MP shipments (real sales booked via marketplace/offline
# orders), rather than dropping them as warehouse-internal movements. Matched
# case-insensitively against the Broad Category text.
_MP_KEEP_RE = r"re-commerce|recommerce|afr|metal|end generator|plastic"


def _keeps_mp(cat: pd.Series) -> pd.Series:
    return cat.str.contains(_MP_KEEP_RE, case=False, na=False)


# Recykal renamed the "Metal" vertical to "End Generator". The Zoho export (and
# older accumulated rows) may still carry the OLD name in Broad Category —
# detection keeps matching both, but every user-facing label (report tabs,
# workbook sheets, emails) shows the new name.
_LABEL_CANON = {"metal": "End Generator"}


def _canon_label(c):
    key = "".join(ch for ch in str(c).lower() if ch.isalnum())
    return _LABEL_CANON.get(key, c)


def _is_samsung(df: pd.DataFrame) -> pd.Series:
    """Per-row: is this a Samsung shipment? Detected by 'samsung' appearing in the
    Supplier Name (col 4) or Buyer Name (col 41). Used to route NEW (post-manual)
    Re-Commerce shipments to the right report variant."""
    def _c(i):
        return df.iloc[:, i].astype(str) if df.shape[1] > i else pd.Series("", index=df.index)
    return (_c(4) + " " + _c(41)).str.lower().str.contains("samsung", na=False)


def _schema_cores(cols) -> list[str]:
    """Normalized 'core' key per column, so the SAME column matches across the
    three name spellings in play: raw engine ('Qty(Kg)', 'Qty(Kg).1'), session-
    sanitized ('QtyKg', 'QtyKg1'), and the manual file's own ('Qty (Kg)').
    A '.N' uniquify suffix is stripped; a bare trailing-digit variant collapses
    onto an earlier identical core (sanitize strips the dot from '.1'), so
    'qtykg1' after 'qtykg' reads as occurrence #2 — while genuinely-numbered
    names like 'Credit Note No:1' (no unnumbered sibling) keep their digit."""
    import re as _re2
    seen, out = set(), []
    for c in cols:
        k = "".join(ch for ch in _re2.sub(r"\.\d+$", "", str(c)).lower() if ch.isalnum())
        m = _re2.match(r"^(.*?)\d+$", k)
        if k not in seen and m and m.group(1) in seen:
            k = m.group(1)
        seen.add(k)
        out.append(k)
    return out


def _align_to_schema(dfm: pd.DataFrame, tgt_cols) -> pd.DataFrame:
    """Reindex `dfm` onto `tgt_cols` matching by normalized core name instead of
    exact spelling (the session store sanitizes names — 'Shipment ID' vs
    'Shipment_ID' — which made an exact reindex NaN every column and broke the
    Re-Commerce dedup). Duplicate cores pair up by occurrence order on both
    sides. Unmatched target columns stay NaN; unmatched source columns drop."""
    tgt_cols = list(tgt_cols)
    src_cores, tgt_cores = _schema_cores(dfm.columns), _schema_cores(tgt_cols)
    slots: dict[str, list[int]] = {}
    for j, k in enumerate(tgt_cores):
        slots.setdefault(k, []).append(j)
    out = pd.DataFrame(index=dfm.index, columns=pd.Index(tgt_cols), dtype=object)
    used: dict[str, int] = {}
    for i, k in enumerate(src_cores):
        occ = used.get(k, 0)
        cand = slots.get(k, [])
        if occ < len(cand):
            out.isetitem(cand[occ], dfm.iloc[:, i].values)
        used[k] = occ + 1
    return out


def apply_recommerce_manual(base_df: pd.DataFrame,
                            manual_df: pd.DataFrame | None,
                            known_ships: set | None = None,
                            exclude_samsung_new: bool = False) -> pd.DataFrame:
    """Drive Re-Commerce from the stored manual detail, adding only the NEW
    shipments from the live MIS. Re-Commerce rows come from `manual_df`
    (accurate cost, no Amazon×Recykal re-costing); a live MIS Re-Commerce row is
    added ONLY if its Shipment ID isn't already known — i.e. genuinely new — and
    those get the live Amazon×Recykal cost. Every other vertical is untouched.

    `known_ships` = the reference set of already-costed Shipment IDs. Pass the
    WITH-Samsung manual's shipments for BOTH variants, so the without-Samsung
    report doesn't re-add the deliberately-excluded Samsung shipments as 'new'.
    If None, the manual's own shipments are used. Positional: 3 = Shipment ID,
    85 = Broad Category."""
    if manual_df is None or getattr(manual_df, "empty", True):
        return base_df
    m = _align_to_schema(manual_df, base_df.columns)   # align by NORMALIZED name —
    # the session store sanitizes column names ('Shipment ID' → 'Shipment_ID');
    # an exact-name reindex NaN'd every manual column there, so the known-ship
    # dedup saw nothing and the live RC rows doubled the manual's sales.
    # provenance: manual rows are the signed-off fixed report — mark them so they
    # don't read as missing-bill Reco candidates
    _csc = next((c for c in m.columns
                 if "".join(ch for ch in str(c).lower() if ch.isalnum()) == "costsource"), None)
    if _csc is not None:
        _cs = m[_csc].astype(str).str.strip()
        m[_csc] = _cs.where(~_cs.isin(["", "nan", "None", "NaT"]), "Manual (fixed report)")
    # the manual IS the Re-Commerce report — force the vertical tag (spreadsheet
    # exports often lose the Broad Category formula values)
    if m.shape[1] > 85:
        m.isetitem(85, pd.Series("Re-Commerce", index=m.index, dtype=object))
    # bucket by the manual's own Month column — its Date column can carry the
    # SOURCE bill date (e.g. an old purchase resold this FY), but the signed-off
    # month is the Month column. Rows whose Date disagrees get the month's 1st
    # so every downstream month bucket matches the fixed report.
    _mon = m.iloc[:, 1].astype(str).str.strip()
    _mdt = pd.to_datetime(_mon, format="%b-%y", errors="coerce")
    _dt = parse_dates(m.iloc[:, 2])
    _fix = _mdt.notna() & (_dt.isna() | (_dt.dt.strftime("%b-%y") != _mon))
    _new_dt = _dt.where(~_fix, _mdt)
    m.isetitem(2, _new_dt.dt.strftime("%Y-%m-%d").astype(object).where(_new_dt.notna(), m.iloc[:, 2]))
    known = set(known_ships) if known_ships is not None else \
        set(m.iloc[:, 3].astype(str).str.strip())
    # combo shipments ("A, B") share components with the manual's own combos —
    # compare COMPONENT-wise, else a re-combined ID double-counts sales that the
    # fixed report already carries under a different combination
    known_parts = {p.strip() for s in known for p in str(s).split(",") if p.strip()}
    cat = base_df.iloc[:, 85].astype(str)
    is_rc = cat.str.contains(r"re-commerce|recommerce", case=False, na=False)
    ship = base_df.iloc[:, 3].astype(str).str.strip()
    _is_known = ship.map(lambda s: any(p.strip() in known_parts
                                       for p in str(s).split(",") if p.strip()))
    new_rc = is_rc & ~_is_known                        # genuinely new RC shipments
    if exclude_samsung_new:                            # without-Samsung report:
        new_rc = new_rc & ~_is_samsung(base_df)        # keep only NON-Samsung new ones
    keep = ~is_rc | new_rc
    return pd.concat([base_df[keep], m], ignore_index=True)


def _itad_reco_mask(df: pd.DataFrame) -> pd.Series:
    """Rows whose shipment has a MISSING BILL (no cost source) — a purchase
    bill was never matched. Covers ALL verticals (not just ITAD). These are
    candidates for the manual Reco-Items review; only user-ticked shipments
    are excluded from calculations and listed on the 'Reco Items' sheet."""
    # normalized lookup — the session store sanitizes names ("Cost Source" →
    # "Cost_Source"), so match on alphanumerics only
    cs_col = next((c for c in df.columns
                   if "".join(ch for ch in str(c).lower() if ch.isalnum()) == "costsource"), None)
    if cs_col is None:
        return pd.Series(False, index=df.index)
    cs = df[cs_col].astype(str).str.strip().str.lower()
    return cs.isin(["", "nan", "none", "no cost found"])


def reco_candidates(profit_df: pd.DataFrame) -> pd.DataFrame:
    """Per-shipment list of missing-bill candidates (ALL verticals) for the manual
    Reco-Items review on the Summary page. Positional: 2=Date, 3=Shipment ID,
    12=Material, 41=Buyer Name, 48=Amount, 85=Broad Category (Vertical)."""
    mask = _itad_reco_mask(profit_df)
    cols = ["Vertical", "Shipment ID", "Date", "Buyer Name", "Material", "Amount"]
    if not mask.any():
        return pd.DataFrame(columns=cols)
    sub = profit_df[mask]
    g = pd.DataFrame({
        "Vertical": sub.iloc[:, 85].astype(str).str.strip(),
        "Shipment ID": sub.iloc[:, 3].astype(str).str.strip(),
        "Date": pd.to_datetime(sub.iloc[:, 2], errors="coerce").dt.strftime("%Y-%m-%d").fillna(""),
        "Buyer Name": sub.iloc[:, 41].astype(str),
        "Material": sub.iloc[:, 12].astype(str),
        "Amount": pd.to_numeric(sub.iloc[:, 48], errors="coerce").fillna(0.0),
    })
    return (g.groupby("Shipment ID", as_index=False)
             .agg({"Vertical": "first", "Date": "first", "Buyer Name": "first",
                   "Material": lambda x: ", ".join(sorted(set(x))), "Amount": "sum"}))[cols]


def _reco_exclusion_mask(df: pd.DataFrame, reco_ships: set | None) -> pd.Series:
    """Which rows are excluded as Reco Items. If `reco_ships` is given (the user's
    saved manual selection), exclude exactly those shipments; otherwise fall back
    to the automatic ITAD-missing-bill detection."""
    if reco_ships is None:
        return _itad_reco_mask(df)
    return df.iloc[:, 3].astype(str).str.strip().isin(set(reco_ships))


def split_by_category(profit_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Split the full profitability report into one report per Broad Category.

    Special rule — Institutional Business is split into TWO reports:
      - Enterprise       : rows whose Shipment ID starts with 'SHID'
      - Processing Center : all other Institutional Business rows

    Returns {report_name: DataFrame} preserving the exact 105 columns.
    """
    def _col(name, pos):
        norm = {"".join(c for c in str(col).lower() if c.isalnum()): col for col in profit_df.columns}
        k = "".join(c for c in name.lower() if c.isalnum())
        if k in norm:
            return profit_df[norm[k]].astype(str).str.strip()
        return profit_df.iloc[:, pos].astype(str).str.strip()

    cat  = _col("Broad Category", 85).map(_canon_label)   # "Metal" → "End Generator"
    ship = _col("Shipment ID", 3)

    out: dict[str, pd.DataFrame] = {}
    for c in sorted(cat.unique()):
        # Fake-DN rows stay only at the bottom of the full report — not a vertical.
        if str(c).strip().lower().startswith("fake dn"):
            continue
        mask = cat.eq(c)
        if c.lower().replace(" ", "").startswith("institutional"):
            # Warehouse = shipment in the persistent IB(Warehouse) list;
            # Enterprise = every other IB shipment (fallback: SH heuristic).
            b2b, wh = _ib_split_masks(mask, ship, profit_df)
            # always emit BOTH reports — even if one currently has 0 rows
            out["Enterprise"]       = profit_df[b2b].reset_index(drop=True)
            out["Processing Center"] = profit_df[wh].reset_index(drop=True)
        else:
            label = c if c and c.lower() != "nan" else "Uncategorised"
            # MP (warehouse) movements don't belong to the vertical's report —
            # except the verticals whose MP/offline orders are genuine sales
            # (Re-Commerce, AFR, Metal/End Generator, Plastic). For everyone else
            # MP rows go to a separate 'Warehouse (MP)' report so the detail sums
            # still cross-check the summary.
            if not _keeps_mp(pd.Series([c])).iloc[0]:
                mp_mask = mask & _is_mp_ship(ship)
                mask = mask & ~_is_mp_ship(ship)
                if mp_mask.any():
                    prev = out.get("Warehouse (MP)")
                    cur = profit_df[mp_mask]
                    out["Warehouse (MP)"] = (pd.concat([prev, cur], ignore_index=True)
                                             if prev is not None else cur.reset_index(drop=True))
            out[label] = profit_df[mask].reset_index(drop=True)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# MANAGEMENT SUMMARY REPORT  (monthly columns + FY total, per Broad Category)
# ══════════════════════════════════════════════════════════════════════════════

SUMMARY_METRICS = [
    "Quantity (MT)",   # IT AD & Re-Commerce count units; all others metric tonnes
    "Sales",
    "Purchases",
    "Gross Margin",
    "Gross Margin (%)",
    "Operational Cost",
    "Net Margin",
    "Net Margin (%)",
    "Revenue Per Kg",
    "Purchase Cost Per Kg",
    "Transportation Charges Per Kg",
    "No. of Transactions",
    "No. of Sellers (Aggregators)",
    "No. of Buyers (Recyclers)",
    "Full Rejection",
    "Receivables (exl Legacy)",
    # bifurcation by INVOICE date at the FY start (1-Apr) — display split only,
    # the parent Receivables/Payable rows keep their original formulas
    "FY 27 Receivables",
    "Old Receivables (pre-Apr, exl Legacy)",
    "DSO (Days)",
    "Payable",
    "FY 27 Payables",
    "Old Payables (pre-Apr)",
    "DPO (Days)",
    "Working Capital Days",
    "Credit Notes (Value - Incl. Prov)",
    "Credit Notes (% to Revenue)",
    "Debit Notes (Value - Incl. Prov)",
    "Debit Notes (% to Purchase)",
]


def _bal_sum(df: pd.DataFrame | None, month: str | None,
             fy_start: pd.Timestamp | None = None) -> float:
    """
    Sum the 'balance' column of an AR/AP sheet.
      month given   → only rows dated in that mmm-yy month
      month is None → full-FY total, EXCLUDING legacy rows dated before
                      fy_start ("exl Legacy")
    """
    if df is None or df.empty:
        return 0.0
    bal_col  = next((c for c in df.columns if "balance" in str(c).lower()), None)
    date_col = next((c for c in df.columns if str(c).lower() == "date"), None)
    if bal_col is None:
        return 0.0
    bal = pd.to_numeric(df[bal_col], errors="coerce").fillna(0)
    if date_col is None:
        return float(bal.sum())
    dts = pd.to_datetime(df[date_col], errors="coerce")
    # Receivable/Payable is the CUMULATIVE open balance as of the month-end
    # (every still-open invoice dated up to that month-end), not just that
    # month's invoices — matching how the manual carries the balance forward.
    # NOTE: this is rebuilt from a single current aging snapshot, so historical
    # months understate (invoices since collected have dropped off the export).
    if month is not None:
        mend = pd.to_datetime("01-" + month, format="%d-%b-%y", errors="coerce")
        if pd.isna(mend):
            return float(bal.sum())
        mend = mend + pd.offsets.MonthEnd(0)
        mask = dts <= mend
        if fy_start is not None:
            mask &= (dts >= fy_start)
        return float(bal[mask].sum())
    if fy_start is not None:
        return float(bal[dts >= fy_start].sum())
    return float(bal.sum())


def _summary_block(w: pd.DataFrame, recv: float, pay: float, wd: float = 30,
                   oc_override: float | None = None,
                   qty_in_mt: bool = True) -> list:
    """
    Compute the summary metrics for one slice (a month or the full FY).
    `wd` = number of working/calendar days in the period (per-column, not summed).
    Quantity & Sales come from the BUYER (invoice) side.
      Gross Margin  = Sales − Purchases
      Net Margin    = Gross Margin − Transportation Charges − Operational Cost
      DSO           = (Receivables / (Sales × 1.18)) × working_days   [per column]
      DPO           = (Payable     / (Sales × 1.18)) × working_days
      WC Days       = DSO − DPO
      CN/DN value   = Σ CN / DN subtotals on the slice
    For the FY Total column the ratios/derived rows (GM%, NM%, DSO, DPO, WC Days,
    Receivable, Payable) are calculated on the FY values — NOT summed from months.
    """
    qty   = float(w["Net_Qty_sales"].sum())   # NET of returns (gross sales qty − Return Qty)
    gross_sales = float(w["Amount_sales"].sum())
    # Net Revenue = gross sales − credit notes (actual + provisions)
    cn_val = float(w["Actaul_CN"].sum()) + float(w["Provision_for_CN"].sum())
    sales = gross_sales - cn_val
    # Net Purchases = gross purchase − debit notes (actual + provisions). Vendor
    # DNs (incl. full-reversal returns to seller) reduce the purchase cost, the
    # same way the manual nets DN out of its Purchases line.
    #   ── BUT only for the verticals that net DN. Re-Commerce, ReWerse and
    #      Processing Center are left exactly as before (gross purchase, no DN net):
    #      their manuals carry ~0 actual DN, so netting would over-state margin.
    _cat  = w["Broad_Category"].astype(str)
    _ship = w["Shipment_ID"].astype(str).str.strip().str.upper()
    _no_net = (
        _cat.str.contains("re-commerce", case=False, na=False)
        | _cat.str.contains("recommerce", case=False, na=False)
        | _cat.str.contains("rewerse", case=False, na=False)
        | (_cat.str.strip().str.lower().str.startswith("institutional")
           & ~_ship.str.startswith("SH"))             # Processing Center
    )
    _elig = ~_no_net
    net_dn = float(w.loc[_elig, "Actual_DN"].sum()) + float(w.loc[_elig, "Provision_for_DN"].sum())
    dn_val = float(w["Actual_DN"].sum()) + float(w["Provision_for_DN"].sum())  # display (all)
    gross_pur = float(w["Purchase_Price"].sum())
    pur   = gross_pur - net_dn          # only eligible verticals' DN reduces cost
    gm    = sales - pur
    tc    = float(w["Logistics_Cost"].sum())
    oc    = oc_override if oc_override is not None else float(w["Operational_Cost"].sum())
    nm    = gm - tc - oc

    def _nz(x, d):  # safe divide
        return round(x / d, 4) if d else 0.0

    ships  = w["Shipment_ID"].astype(str).str.strip()
    n_txn  = ships[(ships != "") & (ships.str.lower() != "nan")].nunique()
    vgst   = w["GST_Reg_No"].astype(str).str.strip()
    n_sell = vgst[(vgst != "") & (vgst.str.lower() != "nan")].nunique()
    bgst   = w["Buyer_GST"].astype(str).str.strip()
    n_buy  = bgst[(bgst != "") & (bgst.str.lower() != "nan")].nunique()

    rev_gst = sales * 1.18
    pur_gst = pur * 1.18
    dso = _nz(recv * wd, rev_gst)   # (recv / (sales×1.18))     × working_days
    dpo = _nz(pay * wd, pur_gst)    # (pay  / (purchases×1.18)) × working_days

    return [
        # quantity is DISPLAYED in MT for weight verticals (data is Kg);
        # IT AD / Re-Commerce count units and stay as-is. Per-kg rows below
        # keep using the raw Kg/unit figure.
        round(qty / 1000 if qty_in_mt else qty, 2),
        round(sales, 0),
        round(pur, 0),
        round(gm, 0),
        round(_nz(gm, sales) * 100, 2),
        round(oc, 0),
        round(nm, 0),
        round(_nz(nm, sales) * 100, 2),
        round(_nz(sales, qty), 2),
        round(_nz(pur, qty), 2),
        round(_nz(tc, qty), 2),
        int(n_txn),
        int(n_sell),
        int(n_buy),
        None,                                  # Full Rejection — usually null
        round(recv, 0),
        round(dso, 0),
        round(pay, 0),
        round(dpo, 0),
        round(dso - dpo, 0),
        round(cn_val, 0),
        round(_nz(cn_val, sales) * 100, 2),
        round(dn_val, 0),
        round(_nz(dn_val, pur) * 100, 2),
    ]


def summary_report(profit_df: pd.DataFrame,
                   ar_df: pd.DataFrame | None = None,
                   ap_df: pd.DataFrame | None = None,
                   op_cost_by_month: dict | None = None,
                   recv_override: float | None = None,
                   pay_override: float | None = None,
                   axis_end: pd.Timestamp | None = None,
                   qty_in_mt: bool = True) -> pd.DataFrame:
    """
    Build the management summary: rows = metrics, columns = each month
    (mmm-yy, chronological) + 'FY Total'.
    Receivables come from the AR sheet, Payables from the AP sheet
    (balance summed per month / full year).
    """
    w = _extract_key_cols(profit_df)
    dates = pd.to_datetime(w["Date"], errors="coerce")
    w = w.assign(_dt=dates, _month=dates.dt.strftime("%b-%y"))

    # months that actually carry data for this category (used for last_month)
    data_months = (w.dropna(subset=["_dt"])
                     .groupby("_month")["_dt"].min()
                     .sort_values().index.tolist())

    # FY start (Indian fiscal year, 1-Apr) from the earliest invoice date
    min_dt = w["_dt"].min()
    max_dt = w["_dt"].max()
    # the axis end is the GLOBAL data cutoff (same for every vertical) when given;
    # otherwise this vertical's own latest invoice date
    end_dt = axis_end if (axis_end is not None and pd.notna(axis_end)) else max_dt
    if pd.notna(min_dt):
        fy_start = pd.Timestamp(min_dt.year if min_dt.month >= 4 else min_dt.year - 1, 4, 1)
    elif pd.notna(end_dt):
        fy_start = pd.Timestamp(end_dt.year if end_dt.month >= 4 else end_dt.year - 1, 4, 1)
    else:
        fy_start = None

    # Display a CONTINUOUS fiscal axis: every month from the FY start (April)
    # through the global cutoff month — even months where this category had no
    # activity (they simply show 0), so all tabs read Apr → latest consistently.
    if fy_start is not None and pd.notna(end_dt):
        months = [d.strftime("%b-%y")
                  for d in pd.date_range(fy_start, end_dt, freq="MS")]
    else:
        months = data_months

    # the OPEN month = the axis's final month: it carries the current
    # receivable/payable snapshot and the day-of-cutoff working days
    last_month = months[-1] if months else (data_months[-1] if data_months else None)

    def _working_days(month: str) -> int:
        # calendar days in the month, EXCEPT the open month uses the cutoff day
        md = pd.to_datetime("01-" + month, format="%d-%b-%y", errors="coerce")
        if pd.isna(md):
            return 30
        if month == last_month and pd.notna(end_dt):
            return int(end_dt.day)
        return int(md.days_in_month)

    def _split(bal_df, parent_val, m):
        """Split the SHOWN balance (parent_val) into FY-27 vs Old by INVOICE date,
        using the FY-dated proportion of the same AR/AP subset. Always ties back to
        the parent (FY27 + Old = parent) and can never go negative — because the
        parent may use a special/frozen basis, we allocate it by the aging's
        date-composition rather than summing a different row set."""
        tot = _bal_sum(bal_df, m, None)          # all open balances (to month-end)
        fy  = _bal_sum(bal_df, m, fy_start)      # the FY-dated portion
        frac = (fy / tot) if tot else 0.0
        v = float(parent_val or 0)
        f27 = round(v * frac, 0)
        return f27, round(v - f27, 0)

    data = {"Metric": SUMMARY_METRICS}
    _ocm = op_cost_by_month or {}
    for m in months:
        # recv_override is a single point-in-time net (legacy+unused+prefix rule);
        # apply it to the LATEST month only (it's a current snapshot), leave history
        # on the per-month cumulative balance.
        _rv = recv_override if (recv_override is not None and m == last_month) \
              else _bal_sum(ar_df, m, fy_start)
        _pv = pay_override if (pay_override is not None and m == last_month) \
              else _bal_sum(ap_df, m, fy_start)
        _blk = _summary_block(w[w["_month"] == m],
                              _rv, _pv,
                              wd=_working_days(m),
                              oc_override=(_ocm.get(m) if _ocm else None),
                              qty_in_mt=qty_in_mt)
        # bifurcation rows, slotted under their parents (FY27 + Old = parent)
        _f27r, _oldr = _split(ar_df, _rv, m)
        _f27p, _oldp = _split(ap_df, _pv, m)
        data[m] = (_blk[:16]
                   + [_f27r, _oldr]
                   + _blk[16:18]
                   + [_f27p, _oldp]
                   + _blk[18:])

    # FY working days = total days from FY start to the global cutoff (not summed)
    fy_wd = int((end_dt - fy_start).days) + 1 if (pd.notna(end_dt) and fy_start is not None) else 30
    _fyb = _summary_block(w,
                          recv_override if recv_override is not None else _bal_sum(ar_df, None, fy_start),
                          pay_override if pay_override is not None else _bal_sum(ap_df, None, fy_start),
                          wd=fy_wd,
                          oc_override=(sum(_ocm.values()) if _ocm else None),
                          qty_in_mt=qty_in_mt)
    _rv_fy = recv_override if recv_override is not None else _bal_sum(ar_df, None, fy_start)
    _pv_fy = pay_override if pay_override is not None else _bal_sum(ap_df, None, fy_start)
    _f27r_fy, _oldr_fy = _split(ar_df, _rv_fy, None)
    _f27p_fy, _oldp_fy = _split(ap_df, _pv_fy, None)
    data["FY Total"] = (_fyb[:16]
                        + [_f27r_fy, _oldr_fy]
                        + _fyb[16:18]
                        + [_f27p_fy, _oldp_fy]
                        + _fyb[18:])

    # Force the open month (last_month) QTY, SALES, and PURCHASES to be the balancing
    # figure between the FY Total and the historical (frozen) months.
    if last_month and last_month in data and len(months) > 1:
        prev_months = [m for m in months if m != last_month]
        
        sum_qty = sum(data[m][0] for m in prev_months)
        sum_sales = sum(data[m][1] for m in prev_months)
        sum_pur = sum(data[m][2] for m in prev_months)
        
        new_last_qty = round(data["FY Total"][0] - sum_qty, 2)
        new_last_sales = round(data["FY Total"][1] - sum_sales, 0)
        new_last_pur = round(data["FY Total"][2] - sum_pur, 0)
        
        old_gm = data[last_month][3]
        old_nm = data[last_month][6]
        oc = data[last_month][5]
        tc = old_gm - old_nm - oc  # reverse-engineer transport cost
        
        data[last_month][0] = new_last_qty
        data[last_month][1] = new_last_sales
        data[last_month][2] = new_last_pur
        
        # Re-derive dependent metrics for internal consistency
        gm = new_last_sales - new_last_pur
        nm = gm - tc - oc
        data[last_month][3] = round(gm, 0)
        data[last_month][4] = round((gm / new_last_sales * 100), 2) if new_last_sales else 0.0
        data[last_month][6] = round(nm, 0)
        data[last_month][7] = round((nm / new_last_sales * 100), 2) if new_last_sales else 0.0
        
        data[last_month][8] = round(new_last_sales / new_last_qty, 2) if new_last_qty else 0.0
        data[last_month][9] = round(new_last_pur / new_last_qty, 2) if new_last_qty else 0.0
        data[last_month][10] = round(tc / new_last_qty, 2) if new_last_qty else 0.0

    return pd.DataFrame(data)


# ── Per-vertical receivables attribution (for DSO) ────────────────────────────
_AR_TOKEN_TAB = [
    ("rew", "ReWerse"), ("met", "End Generator"), ("rec", "Re-Commerce"),
    ("afr", "AFR"), ("pet", "Plastic"), ("iad", "IT AD"), ("m4", "M4"),
]


def _ar_token_tab(tn: str) -> str:
    """Map an AR invoice number's segment token (e.g. 36/MET/27IN.. → End Generator)."""
    import re as _re
    m = _re.match(r"^\d+/([A-Za-z0-9]+)/", str(tn))
    tok = m.group(1).lower() if m else ""
    for k, v in _AR_TOKEN_TAB:
        if k in tok:
            return v
    if tok == "ib" or "pib" in tok:
        return "Enterprise"
    return ""


def _inv_tab_map(profit_df: pd.DataFrame) -> dict:
    """invoice-number → tab label, from the profitability rows (handles the
    Enterprise/Processing Center split and the MP-warehouse carve-out)."""
    # fillna BEFORE astype — Arrow-backed columns keep NaN through .astype(str),
    # so a missing invoice number would arrive here as a float and crash .lower()
    inv  = profit_df.iloc[:, 39].fillna("").astype(str).str.strip()
    cat  = profit_df.iloc[:, 85].fillna("").astype(str).str.strip()
    ship = profit_df.iloc[:, 3].fillna("").astype(str).str.strip().str.upper()
    m = {}
    for iv, c, sh in zip(inv, cat, ship):
        iv, c, sh = str(iv), str(c), str(sh)
        if not iv or iv.lower() in ("nan", "none", "nat"):
            continue
        cl = c.lower().replace(" ", "")
        if cl.startswith("institutional"):
            lab = "Enterprise" if (sh.startswith("SH") and "MPIB" not in sh) else "Processing Center"
        elif _re.sub(r"^\d+/", "", sh).startswith("MP") and "re-commerce" not in c.lower():
            lab = "Warehouse (MP)"
        else:
            lab = _canon_label(c) if c and c.lower() != "nan" else ""
        m[iv] = lab
    return m


def _attribute_ar(ar_df, profit_df):
    """Tag each AR row with its vertical tab — exact invoice-number match first,
    falling back to the invoice token. Adds a '_tab' column."""
    if ar_df is None or ar_df.empty:
        return ar_df
    df = ar_df.copy()
    tn = next((c for c in df.columns if "transaction" in str(c).lower() and "number" in str(c).lower()), None)
    if tn is None:
        df["_tab"] = ""
        return df
    imap = _inv_tab_map(profit_df)
    s = df[tn].fillna("").astype(str).str.strip()
    df["_tab"] = s.map(lambda x: "Enterprise" if str(x) in ENTERPRISE_EXTRA_AR_INVOICES
                       else (imap.get(str(x)) or _ar_token_tab(str(x))))
    return df


def _afr_op_cost(bills_df) -> dict:
    """AFR Operational Cost by month = Σ Item_Total of bills where
    account is Marketplace Purchases (AFR) (Logistics → Transportation Charges,
    not op cost), CFSO is blank, and Bill Status is not Void (Paid + Overdue,
    consistent with the rest of the pipeline). Source: the older-bills store."""
    if bills_df is None or getattr(bills_df, "empty", True):
        return {}
    df = bills_df
    def col(*names):
        for n in names:
            for c in df.columns:
                if str(c).strip().lower() == n:
                    return c
        return None
    acc = col("account"); cfso = col("cfso_number", "cf.so number")
    stat = col("bill_status", "status"); itot = col("item_total")
    bdate = col("bill_date")
    if not all([acc, cfso, stat, itot, bdate]):
        return {}
    a = df[acc].astype(str)
    blank = df[cfso].isna() | df[cfso].astype(str).str.strip().isin(["", "nan", "None", "NaT"])
    sel = (a.str.contains("afr", case=False, na=False)
           & a.str.contains("marketplace purchases", case=False, na=False)   # Purchases only
           & blank
           & ~df[stat].astype(str).str.strip().str.lower().isin(["void"]))
    sub = df[sel]
    if sub.empty:
        return {}
    mth = pd.to_datetime(sub[bdate], errors="coerce").dt.strftime("%b-%y")
    val = pd.to_numeric(sub[itot], errors="coerce").fillna(0)
    return {k: float(v) for k, v in val.groupby(mth).sum().items()}


def summaries_by_category(profit_df: pd.DataFrame,
                          ar_df: pd.DataFrame | None = None,
                          ap_df: pd.DataFrame | None = None,
                          op_cost_bills: pd.DataFrame | None = None,
                          reco_ships: set | None = None) -> dict[str, pd.DataFrame]:
    """
    One summary report per Broad Category — with Institutional Business
    split into Enterprise (Shipment ID starts 'SHID') and Processing Center.
    Also includes an 'All Categories' overall summary first.
    Note: Receivables/Payables come from the company-wide AR/AP sheets and
    are the same on every tab (they are not category-attributable).
    """
    # positional access — works whether column names are exact or sanitized
    ship_all = profit_df.iloc[:, 3].astype(str).str.strip()    # Shipment ID
    cat_all  = profit_df.iloc[:, 85].astype(str)               # Broad Category

    # MP-prefixed shipments are WAREHOUSE movements, normally excluded — EXCEPT
    # for verticals whose MP/offline orders are genuine sales: Re-Commerce, AFR,
    # Metal (End Generator) and Plastic. Those keep their MP rows.
    is_mp = _is_mp_ship(ship_all)
    keep_mp = _keeps_mp(cat_all)
    # ITAD missing-bill rows are removed from ALL calculations (shown separately
    # on the 'Reco Items' sheet in the workbook).
    exclude = (is_mp & ~keep_mp) | _reco_exclusion_mask(profit_df, reco_ships)
    main_df = profit_df[~exclude]
    mp_df   = profit_df[exclude]

    cat  = (main_df.iloc[:, 85].astype(str).str.strip()       # Broad Category
            .map(_canon_label))                               # "Metal" → "End Generator"
    ship = main_df.iloc[:, 3].astype(str).str.strip()

    # Attribute receivables to each vertical (per-vertical DSO). Payables (AP)
    # are NOT vertical-tagged in the source, so they remain company-wide for now.
    ar_attr = _attribute_ar(ar_df, profit_df)
    def _ar(tab):
        if ar_attr is None or "_tab" not in getattr(ar_attr, "columns", []):
            return ar_df
        sub = ar_attr[ar_attr["_tab"] == tab]
        return sub if len(sub) else None

    # AFR operational cost (CFSO-blank, Paid AFR bills) — by month
    _afr_oc = _afr_op_cost(op_cost_bills)

    # Per-vertical NET receivable (invoice-prefix attribution − legacy − unused,
    # with the Black-Gold→Re-Commerce rule) from the receivables builder. This is
    # the figure the manual reports, so it overrides the raw AR balance.
    _net_by_v = {}
    if ar_df is not None and not getattr(ar_df, "empty", True):
        try:
            import receivables as _recv
            _summ = _recv.build_receivables(ar_df)["summary"]
            _net_by_v = dict(zip(_summ["Vertical"], _summ["Net Receivable"]))
        except Exception:
            _net_by_v = {}

    def _recv_net(tab: str):
        key = "".join(ch for ch in str(tab).lower() if ch.isalnum())
        # NOTE: IB is intentionally NOT mapped here. Enterprise and Processing Center need
        # their own receivable split (the Enterprise sheet's B2B figure is a specific
        # subset, not the whole-IB net) — until that rule is cracked, IB keeps its
        # prior per-month balance rather than a wrong override.
        alias = {"metal": "End Generator", "endgenerator": "End Generator",
                 "plastic": "Plastic", "rewerse": "ReWerse",
                 "recommerce": "Re-Commerce", "itad": "ITAD", "itassetsdisposition": "ITAD",
                 "afr": "AFR", "m4": "M4"}
        return _net_by_v.get(alias.get(key))

    # Per-vertical PAYABLE from the AP sheet, attributed by vendor.CF.Vertical Name.
    _ap_by_v = {}
    if ap_df is not None and not getattr(ap_df, "empty", True):
        _vc = next((c for c in ap_df.columns if "vertical" in str(c).lower()), None)
        _bc = next((c for c in ap_df.columns if "balance" in str(c).lower()), None)
        if _vc and _bc:
            _b = pd.to_numeric(ap_df[_bc], errors="coerce").fillna(0)
            _ap_by_v = _b.groupby(ap_df[_vc].astype(str).str.lower()).sum().to_dict()

    _ap_vc = None
    if ap_df is not None and not getattr(ap_df, "empty", True):
        _ap_vc = next((c for c in ap_df.columns if "vertical" in str(c).lower()), None)

    def _ap_sub(tab: str):
        t = "".join(ch for ch in str(tab).lower() if ch.isalnum())
        return {"metal": "metal waste", "endgenerator": "metal waste",
                "plastic": "plastic waste", "recommerce": "re-commerce",
                "itad": "it assets", "itassetsdisposition": "it assets",
                "afr": "(afr)", "m4": "(m4)", "enterprise": "institutional",
                "processingcenter": "institutional"}.get(t)

    def _ap(tab: str):
        """AP rows for a vertical, filtered by vendor.CF.Vertical Name — so every
        month's Payable/DPO is per-vertical, not company-wide."""
        if _ap_vc is None:
            return ap_df
        sub = _ap_sub(tab)
        if not sub:
            return None
        m = ap_df[ap_df[_ap_vc].astype(str).str.lower().str.contains(sub, na=False, regex=False)]
        return m if len(m) else None

    def _pay_net(tab: str):
        if not _ap_by_v:
            return None
        sub = _ap_sub(tab)
        if not sub:
            return None
        tot = sum(v for name, v in _ap_by_v.items() if sub in str(name))
        return float(tot) if tot else None

    # global data cutoff — every tab shares the same Apr→cutoff month axis
    _axis_end = pd.to_datetime(profit_df.iloc[:, 2], errors="coerce").max()

    # verticals that count UNITS; everything else displays quantity in MT (Kg÷1000)
    _UNIT_TABS = {"itad", "recommerce"}
    def _mt(tab: str) -> bool:
        return "".join(ch for ch in str(tab).lower() if ch.isalnum()) not in _UNIT_TABS

    out = {"All Categories": summary_report(main_df, ar_df, ap_df, axis_end=_axis_end)}
    for c in sorted(cat.unique()):
        # Fake-DN rows are kept in the detailed report (bottom) but are NOT shown
        # as their own vertical/summary.
        if str(c).strip().lower().startswith("fake dn"):
            continue
        mask = cat.eq(c)
        if c.lower().replace(" ", "").startswith("institutional"):
            # Warehouse = shipment in the persistent IB(Warehouse) list;
            # Enterprise = every other IB shipment (fallback: SH heuristic).
            b2b, wh = _ib_split_masks(mask, ship, main_df)
            # Enterprise receivable: only AR invoices that actually appear in the B2B
            # profitability (isolates B2B from warehouse, which share IB prefixes).
            _ib_recv = None
            if ar_df is not None and not getattr(ar_df, "empty", True):
                _tn = next((c for c in ar_df.columns
                            if "transaction" in str(c).lower() and "number" in str(c).lower()), None)
                _bc = next((c for c in ar_df.columns if "balance" in str(c).lower()), None)
                if _tn and _bc:
                    _b2b_invs = (set(main_df[b2b].iloc[:, 39].astype(str).str.strip())
                                 | ENTERPRISE_EXTRA_AR_INVOICES) - {"", "nan"}
                    _sel = ar_df[ar_df[_tn].astype(str).str.strip().isin(_b2b_invs)]
                    # net unused credits FIFO — each customer's credit settles
                    # their oldest open invoice first, then spills onto newer ones
                    _ib_recv = _fifo_net_unused(_sel)
            out["Enterprise"]       = summary_report(main_df[b2b], _ar("Enterprise"), _ap("Enterprise"),
                                                  recv_override=_ib_recv, pay_override=_pay_net("Enterprise"),
                                                  axis_end=_axis_end)
            out["Processing Center"] = summary_report(main_df[wh], _ar("Processing Center"), _ap("Processing Center"),
                                                  axis_end=_axis_end)
        else:
            label = c if c and c.lower() != "nan" else "Uncategorised"
            _oc = _afr_oc if label.upper() == "AFR" else None
            out[label] = summary_report(main_df[mask], _ar(label), _ap(label),
                                        op_cost_by_month=_oc, recv_override=_recv_net(label),
                                        pay_override=_pay_net(label), axis_end=_axis_end,
                                        qty_in_mt=_mt(label))

    # Out-of-scope verticals — handled manually, not part of the automated report.
    # (Their rows still roll into 'All Categories'; only their own tabs are hidden.)
    for _oos in ("ReWerse", "Processing Center"):
        out.pop(_oos, None)

    return out


def top_materials(profit_df: pd.DataFrame, tab: str, n: int = 5):
    """Top-n materials by margin for a vertical's LATEST data month — the table the
    manual mails carry ('these top 5 contributed X% of the month's margin').
    Returns (table_df, month_label, share_of_month_margin) or (None, None, None)."""
    w = _extract_key_cols(profit_df)
    ship = w["Shipment_ID"].astype(str).str.strip()
    cat  = w["Broad_Category"].astype(str)

    # same scoping as summaries_by_category: MP-warehouse rows excluded, except
    # for the verticals whose MP/offline orders are real sales
    is_mp = _is_mp_ship(ship)
    w = w[~(is_mp & ~_keeps_mp(cat))]
    ship = w["Shipment_ID"].astype(str).str.strip().str.upper()
    cat  = w["Broad_Category"].astype(str).map(_canon_label)

    key = "".join(ch for ch in str(tab).lower() if ch.isalnum())
    if key in ("enterprise", "processingcenter"):
        inst = cat.str.strip().str.lower().str.startswith("institutional")
        b2b, wh = _ib_split_masks(inst, ship, w)
        mask = b2b if key == "enterprise" else wh
    elif key == "allcategories":
        mask = ~cat.str.strip().str.lower().str.startswith("fake dn")
    else:
        mask = cat.apply(lambda c: "".join(ch for ch in str(c).lower() if ch.isalnum()) == key)
    sub = w[mask].copy()
    if sub.empty:
        return None, None, None

    dts = pd.to_datetime(sub["Date"], errors="coerce")
    sub["_month"] = dts.dt.strftime("%b-%y")
    months = dts.dropna().sort_values()
    if months.empty:
        return None, None, None
    month = months.iloc[-1].strftime("%b-%y")
    m = sub[sub["_month"] == month]

    g = (m.assign(_mat=m["Material"].astype(str).str.strip(),
                  _qty=pd.to_numeric(m["Net_Qty_sales"], errors="coerce").fillna(0),
                  _rev=pd.to_numeric(m["Amount_sales"], errors="coerce").fillna(0),
                  _mar=pd.to_numeric(m["Margin_BO"], errors="coerce").fillna(0))
          .groupby("_mat")[["_qty", "_rev", "_mar"]].sum())
    g = g[g.index.str.lower() != "nan"]
    month_margin = float(g["_mar"].sum())
    top = g.sort_values("_mar", ascending=False).head(n)

    rows = [{"Material": mat,
             "Qty": r["_qty"], "Revenue": r["_rev"], "Sum of Margin": r["_mar"],
             "MTD %": (100 * r["_mar"] / r["_rev"]) if r["_rev"] else 0.0}
            for mat, r in top.iterrows()]
    tq, tr, tm = top["_qty"].sum(), top["_rev"].sum(), top["_mar"].sum()
    rows.append({"Material": "Total", "Qty": tq, "Revenue": tr, "Sum of Margin": tm,
                 "MTD %": (100 * tm / tr) if tr else 0.0})
    share = (100 * tm / month_margin) if month_margin else 0.0
    return pd.DataFrame(rows), month, share


# Summary row positions (0-indexed into SUMMARY_METRICS) highlighted in every
# vertical block: Gross/Net Margin % (4, 7) + the Receivable/Payable parent rows
# and their FY27/Old splits.
_SUMMARY_HIGHLIGHT_ROWS = [4, 7, 15, 16, 17, 19, 20, 21]

# Indian digit grouping, single (non-conditional) custom format codes: the last
# explicit comma-group size (2 digits) repeats automatically for any higher
# magnitude, giving 3-2-2-2… grouping (12,34,56,789) for any value, no
# per-magnitude conditions needed.
_INR_INT = "#,##,##0"          # whole numbers: money, counts, days
_INR_DEC = "#,##,##0.00"       # 2-decimal: quantity, per-kg rates
_PCT_FMT = '0.00"%"'           # value is ALREADY the percent number (14.43 = 14.43%)
                                # — a literal suffix, NOT Excel's native % (which
                                # would multiply by 100 again and show 1443.00%).

# Per-row (0-indexed into SUMMARY_METRICS, 28 rows) number format for the
# Summary sheet — known exactly since every vertical block has this fixed shape.
_ROW_NUMFMT = {
    0: _INR_DEC,   1: _INR_INT,  2: _INR_INT,  3: _INR_INT,  4: _PCT_FMT,
    5: _INR_INT,   6: _INR_INT,  7: _PCT_FMT,  8: _INR_DEC,  9: _INR_DEC,
    10: _INR_DEC, 11: _INR_INT, 12: _INR_INT, 13: _INR_INT, 14: _INR_INT,
    15: _INR_INT, 16: _INR_INT, 17: _INR_INT, 18: _INR_INT, 19: _INR_INT,
    20: _INR_INT, 21: _INR_INT, 22: _INR_INT, 23: _INR_INT, 24: _INR_INT,
    25: _PCT_FMT, 26: _INR_INT, 27: _PCT_FMT,
}


def _style_workbook(raw: bytes, headers: list[tuple[str, int]],
                    highlights: list[tuple[str, int]],
                    summary_numfmt: list[tuple[str, int, str]]) -> bytes:
    """Post-process the workbook: black header rows (white bold text), a soft
    highlight on the Receivable/Payable (+FY27/Old) rows, Indian-grouped number
    formatting everywhere, and auto-fit column widths — so nobody has to
    manually resize columns or fight Excel's Western comma grouping again."""
    import io as _io
    import datetime as _dt
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.cell.cell import MergedCell

    wb = load_workbook(_io.BytesIO(raw))
    header_fill = PatternFill("solid", fgColor="000000")
    header_font = Font(bold=True, color="FFFFFF")
    highlight_fill = PatternFill("solid", fgColor="FFF2CC")
    highlight_font = Font(bold=True, color="000000")

    for sheet, r in headers:
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        for cell in ws[r]:
            if cell.value is None:
                continue
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical="center")

    for sheet, r in highlights:
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        for cell in ws[r]:
            if cell.value is None:
                continue
            cell.fill = highlight_fill
            cell.font = highlight_font

    def _is_num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) \
            and not (isinstance(v, float) and (v != v))   # exclude NaN

    # Summary sheet: exact per-row format (known row semantics)
    for sheet, r, fmt in summary_numfmt:
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        for cell in ws[r]:
            if cell.column == 1 or not _is_num(cell.value):
                continue
            cell.number_format = fmt

    # Every other sheet: Indian-group any numeric cell, scoped to each header's
    # own table extent (sheets like Receivables/Payables stack several small
    # tables, so formatting must not bleed from one table's columns into the
    # next). % is detected from the header text; decimals from the data itself.
    by_sheet: dict[str, list[int]] = {}
    for sheet, r in headers:
        if sheet == "Summary":
            continue
        by_sheet.setdefault(sheet, []).append(r)

    for sheet, hdr_rows in by_sheet.items():
        ws = wb[sheet]
        hdr_rows = sorted(hdr_rows)
        for i, hr in enumerate(hdr_rows):
            end = (hdr_rows[i + 1] - 2) if i + 1 < len(hdr_rows) else ws.max_row
            # stop early at the first fully-blank row (a table ends before that)
            for rr in range(hr + 1, end + 1):
                if all(c.value is None for c in ws[rr]):
                    end = rr - 1
                    break
            for col_idx in range(1, ws.max_column + 1):
                header_val = ws.cell(row=hr, column=col_idx).value
                is_pct = isinstance(header_val, str) and "%" in header_val
                has_dec = any(
                    _is_num(ws.cell(row=rr, column=col_idx).value)
                    and abs(ws.cell(row=rr, column=col_idx).value
                            - round(ws.cell(row=rr, column=col_idx).value)) > 1e-9
                    for rr in range(hr + 1, end + 1))
                fmt = _PCT_FMT if is_pct else (_INR_DEC if has_dec else _INR_INT)
                for rr in range(hr + 1, end + 1):
                    cell = ws.cell(row=rr, column=col_idx)
                    if _is_num(cell.value):
                        cell.number_format = fmt

    # ── black grid borders on EVERY table (matches the manual workbooks) ──────
    # Each table = its header row down to the first fully-blank row (or the row
    # before the next table's header), across the header's populated columns.
    _thin = Side(style="thin", color="000000")
    _grid = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
    all_tables: dict[str, list[int]] = {}
    for sheet, r in headers:                     # Summary included this time
        all_tables.setdefault(sheet, []).append(r)
    for sheet, hdr_rows in all_tables.items():
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        hdr_rows = sorted(set(hdr_rows))
        for i, hr in enumerate(hdr_rows):
            end = (hdr_rows[i + 1] - 2) if i + 1 < len(hdr_rows) else ws.max_row
            for rr in range(hr + 1, end + 1):
                if all(c.value is None for c in ws[rr]):
                    end = rr - 1
                    break
            width = max((c.column for c in ws[hr] if c.value is not None), default=0)
            for rr in range(hr, end + 1):
                for cc in range(1, width + 1):
                    ws.cell(row=rr, column=cc).border = _grid

    # auto-fit column widths (openpyxl has no native autofit — size from content)
    for ws in wb.worksheets:
        widths: dict[int, int] = {}
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None or isinstance(cell, MergedCell):
                    continue   # merged group-header cells report no column index
                v = cell.value
                if isinstance(v, (_dt.date, _dt.datetime)):
                    cell.number_format = "dd-mm-yyyy"   # DATE ONLY — strip the time
                    disp = v.strftime("%d-%b-%Y")
                elif isinstance(v, str) and _re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", v):
                    v = v[:10]                          # 'YYYY-MM-DD 00:00:00' → 'YYYY-MM-DD'
                    cell.value = v
                    disp = v
                elif _is_num(v) and cell.number_format not in ("General", None):
                    disp = f"{v:,.2f}" if "." in cell.number_format else f"{v:,.0f}"
                else:
                    disp = str(v)
                widths[cell.column] = max(widths.get(cell.column, 0), len(disp))
        for col_idx, w in widths.items():
            letter = get_column_letter(col_idx)
            ws.column_dimensions[letter].width = min(max(w + 2, 10), 45)

    out = _io.BytesIO()
    wb.save(out)
    return out.getvalue()


def combined_workbook(summaries: dict[str, pd.DataFrame],
                      profit_df: pd.DataFrame,
                      ar_df: pd.DataFrame | None = None,
                      ap_df: pd.DataFrame | None = None,
                      vertical: str | None = None,
                      reco_ships: set | None = None) -> bytes:
    """One Excel with four stacked sheets — Summary, Receivables, Payables,
    Details (the profitability report). If `vertical` is given, everything is
    filtered to it; otherwise all verticals are included (stacked by type)."""
    import io as _io
    import receivables as _recv

    _headers: list[tuple[str, int]] = []      # (sheet, 1-indexed excel row) -> black header style
    _highlights: list[tuple[str, int]] = []   # (sheet, 1-indexed excel row) -> R/P soft highlight
    _numfmt: list[tuple[str, int, str]] = []  # (sheet, 1-indexed excel row, format) -> Summary rows

    buf = _io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        # ── Sheet 1: Summary (per-vertical blocks stacked) ────────────────────
        keys = [vertical] if (vertical and vertical in summaries) else list(summaries.keys())
        row = 0
        for k in keys:
            df = summaries.get(k)
            if df is None:
                continue
            pd.DataFrame([[f"■ {k}"]]).to_excel(w, sheet_name="Summary", startrow=row, startcol=0,
                                                index=False, header=False)
            df.to_excel(w, sheet_name="Summary", startrow=row + 1, index=False)
            _hdr_row = row + 2   # 1-indexed excel row of this block's header
            _headers.append(("Summary", _hdr_row))
            for _i in _SUMMARY_HIGHLIGHT_ROWS:
                if _i < len(df):
                    _highlights.append(("Summary", _hdr_row + 1 + _i))
            for _i in range(len(df)):
                _numfmt.append(("Summary", _hdr_row + 1 + _i, _ROW_NUMFMT.get(_i, _INR_DEC)))
            row += len(df) + 3

        # ── Sheet 2: Receivables (build-up table + Legacy box + detail) ───────
        if ar_df is not None and not getattr(ar_df, "empty", True):
            rb = _recv.build_receivables(ar_df)
            summ, det = rb["summary"], rb["detail"]
            if vertical:
                vn = "".join(c for c in vertical.lower() if c.isalnum())
                alias = {"metal": "End Generator", "endgenerator": "End Generator",
                         "plastic": "Plastic", "rewerse": "ReWerse",
                         "recommerce": "Re-Commerce", "itad": "ITAD", "afr": "AFR", "m4": "M4",
                         "enterprise": "IB", "institutionalbusiness": "IB"}.get(vn, vertical)
                summ = summ[summ["Vertical"].astype(str) == alias]
                if "Vertical" in det.columns:
                    det = det[det["Vertical"].astype(str) == alias]
            # 1) Net build-up: Gross − Legacy − Unused = Net (already columns of summ)
            pd.DataFrame([["NET RECEIVABLE = Gross − Legacy − Unused Credits"]]).to_excel(
                w, sheet_name="Receivables", startrow=0, startcol=0, index=False, header=False)
            summ.to_excel(w, sheet_name="Receivables", startrow=1, index=False)
            _headers.append(("Receivables", 2))
            r = len(summ) + 4
            # 2) Legacy box — the customers whose balances are excluded from Net
            pd.DataFrame([["LEGACY — customers excluded from Net Receivable"]]).to_excel(
                w, sheet_name="Receivables", startrow=r, startcol=0, index=False, header=False)
            r += 1
            leg_rows = []
            for v, names in _recv.LEGACY_CUSTOMERS.items():
                s2 = det[det["Vertical"].astype(str) == v] if "Vertical" in det.columns else det.iloc[0:0]
                for nm in names:
                    amt = s2.loc[s2["_cust"].astype(str).str.contains(nm, na=False), "_balance"].sum() \
                          if "_cust" in s2.columns else 0
                    if amt:
                        leg_rows.append({"Vertical": v, "Legacy Customer": nm,
                                         "Outstanding (excluded)": round(float(amt), 2)})
            if leg_rows:
                pd.DataFrame(leg_rows).to_excel(w, sheet_name="Receivables", startrow=r, index=False)
                _headers.append(("Receivables", r + 1))
                r += len(leg_rows) + 3
            else:
                pd.DataFrame([["(no legacy customers for this selection)"]]).to_excel(
                    w, sheet_name="Receivables", startrow=r, startcol=0, index=False, header=False)
                r += 3
            # 3) full detail (drop internal helper cols + mangled 17-digit IDs)
            _drop = [c for c in det.columns if str(c).strip().lower() in
                     ("_cust", "_balance", "_unused", "entity_id", "customer_id",
                      "currency_code", "balance_fcy", "amount_fcy", "exchange_rate")]
            det_out = det.drop(columns=_drop, errors="ignore")
            det_out.to_excel(w, sheet_name="Receivables", startrow=r, index=False)
            _headers.append(("Receivables", r + 1))

        # ── Sheet 3: Payables (AP by vendor vertical) ─────────────────────────
        if ap_df is not None and not getattr(ap_df, "empty", True):
            _vc = next((c for c in ap_df.columns if "vertical" in str(c).lower()), None)
            _bc = next((c for c in ap_df.columns if str(c).lower() == "balance"), None) \
                  or next((c for c in ap_df.columns if "balance" in str(c).lower()), None)
            ap = ap_df.copy()
            # drop mangled 17-digit ID columns & FCY duplicates that render as 8.3E+17.
            # NEVER drop the column we picked as the balance: the newer AP export has
            # only 'balance_fcy' (no plain 'balance'), so that IS the payable figure.
            _junk = [c for c in ap.columns if str(c).strip().lower() in
                     ("entity_id", "vendor_id", "customer_id", "currency_code",
                      "balance_fcy", "amount_fcy", "exchange_rate") and c != _bc]
            ap = ap.drop(columns=_junk, errors="ignore")
            if vertical and _vc:
                sub = {"metal": "metal waste", "endgenerator": "metal waste",
                       "plastic": "plastic waste", "recommerce": "re-commerce",
                       "itad": "it assets", "afr": "(afr)", "m4": "(m4)", "enterprise": "institutional"}.get(
                       "".join(c for c in vertical.lower() if c.isalnum()))
                if sub:
                    ap = ap[ap[_vc].astype(str).str.lower().str.contains(sub, na=False, regex=False)]
            if _vc and _bc:
                tot = (pd.to_numeric(ap[_bc], errors="coerce").fillna(0)
                       .groupby(ap[_vc].astype(str)).sum().reset_index()
                       .rename(columns={_bc: "Payable"}))
                tot.columns = ["Vendor Vertical", "Payable"]
                tot.to_excel(w, sheet_name="Payables", startrow=0, index=False)
                _headers.append(("Payables", 1))
                ap.to_excel(w, sheet_name="Payables", startrow=len(tot) + 3, index=False)
                _headers.append(("Payables", len(tot) + 4))
            else:
                ap.to_excel(w, sheet_name="Payables", index=False)
                _headers.append(("Payables", 1))

        # ── Sheet 4: Details (the profitability report) — whole FY, ONE schema ──
        # Every row (frozen months from the manual files' Details + live months
        # from the accumulated store) is aligned to the ENGINE's column set, so
        # the sheet is a single auditable table: filter by Month, sum any column,
        # cross-check the FY Total. Manual-only columns are dropped; engine
        # columns the manual lacks stay blank. 'Row Source' marks provenance.
        # No month appears twice per vertical. (Note: frozen details are no longer mixed in here 
        # as the user requested this sheet to be 100% live data).
        _fdet = {}
        try:
            import database as _dbm
            _acc = _dbm.load_profit_details()
        except Exception:
            _acc, _dbm = None, None
        if _acc is not None and len(_acc):
            _live_src = _acc
        else:
            _live_src = profit_df.copy()
            if _dbm is not None:      # de-duplicate repeated column names
                _live_src.columns = _dbm._uniq_cols(_live_src.columns)
        # Enterprise Custom Duty bills: the accumulated store is written at
        # upload time — BEFORE the Summary page injects them — so they must be
        # injected here too, or the sheet wouldn't carry the line items the
        # FY-Total Purchases already counts.
        try:
            _cds = _dbm.load_custom_duty() if _dbm is not None else None
        except Exception:
            _cds = None
        if _cds is not None and len(_cds) and not _custom_duty_mask(_live_src).any():
            _live_src = inject_custom_duty(_live_src, _cds)
        _tgt = list(_live_src.columns)

        def _nrm(s):
            return "".join(ch for ch in str(s).lower() if ch.isalnum() or ch == "%")

        # Build a map: normalised column name → engine column name.
        # _uniq_cols suffixes duplicates with .1, .2, … (e.g. "Qty(Kg).1").
        # We store EVERY suffixed variant so _align can resolve them.
        _tmap = {}
        for _c in _tgt:
            _tmap.setdefault(_nrm(_c), _c)

        # Aliases: manual report files may use different column names for the
        # same data (e.g. "Vendor Name" instead of "Supplier Name"). Map the
        # normalised manual name → the engine's normalised key so _align picks
        # it up. Case-insensitive because _nrm already lowercases.
        _DETAIL_ALIASES = {
            "vendorname": "suppliername",
        }
        for _ak, _av in _DETAIL_ALIASES.items():
            if _ak not in _tmap and _av in _tmap:
                _tmap[_ak] = _tmap[_av]

        def _align(dfm):
            """Map a manual Details frame onto the engine's columns by name.

            Handles duplicate column names: the engine's 107-col layout has
            repeated names (Qty(Kg), Return Qty, Net Qty, Amount, Month, …).
            After _uniq_cols these become Foo, Foo.1, Foo.2. The manual file
            still carries the RAW duplicates (two cols both called "Qty(Kg)").
            When the first occurrence is already used, we look for the .1, .2
            suffixed engine column matching the same base name."""
            ren, used = {}, set()
            # Track how many times each normalised key has been seen in the
            # manual file so we can map to the right .N engine column.
            _seen_count: dict[str, int] = {}
            for _c in dfm.columns:
                nk = _nrm(_c)
                # Apply alias (e.g. vendorname → suppliername)
                nk_resolved = nk
                if nk in _DETAIL_ALIASES:
                    nk_resolved = _DETAIL_ALIASES[nk]
                occ = _seen_count.get(nk_resolved, 0)
                _seen_count[nk_resolved] = occ + 1
                # First occurrence → use base key; subsequent → try .1, .2, …
                if occ == 0:
                    lookup = nk_resolved
                else:
                    lookup = nk_resolved + str(occ)
                _t2 = _tmap.get(lookup)
                if _t2 and _t2 not in used:
                    ren[_c] = _t2
                    used.add(_t2)
            out = dfm.rename(columns=ren)
            return out.loc[:, [c for c in out.columns if c in used]].reindex(columns=_tgt)

        rep_by_tab = ({vertical: split_by_category(_live_src).get(vertical, _live_src)}
                      if vertical else split_by_category(_live_src))
        _parts = []
        for _t, _df_t in rep_by_tab.items():
            _tab_parts = []
            _f = _fdet.get(_t)
            if _f is not None:
                _fdf, _fmonths = _f
                _al = _align(_fdf).copy()
                _al["Row Source"] = f"Manual file ({_t})"
                _tab_parts.append(_al)
                # live rows for this tab: months NOT already frozen above, PLUS
                # genuinely-new shipments the MIS carries for frozen months (a
                # shipment absent from the manual file) — merged in, disclosed
                # via Row Source, so late entries aren't silently lost.
                _mm = parse_dates(_df_t.iloc[:, 2]).dt.strftime("%b-%y")
                _in_frozen = _mm.isin(_fmonths)
                _known = (set(_al["Shipment ID"].astype(str).str.strip())
                          if "Shipment ID" in _al.columns else set())
                _ship_l = _df_t.iloc[:, 3].astype(str).str.strip()
                _extra = _in_frozen & ~_ship_l.isin(_known) & ~_ship_l.isin(["", "nan"])
                _df_t = _df_t[~_in_frozen | _extra]
            if len(_df_t):
                _lv = _df_t.reindex(columns=_tgt).copy()
                _lv["Row Source"] = "Live (MIS)"
                _tab_parts.append(_lv)
            if _tab_parts:
                _tab_df = pd.concat(_tab_parts, ignore_index=True)
                # FIFO month order within the tab — frozen and live rows
                # interleaved chronologically (Apr, May, Jun, …)
                if "Date" in _tab_df.columns:
                    _dts = parse_dates(_tab_df["Date"])
                    _ord = pd.concat([_dts[_dts.notna()].sort_values(kind="stable"),
                                      _dts[_dts.isna()]]).index
                    _tab_df = _tab_df.loc[_ord].reset_index(drop=True)
                _parts.append(_tab_df)
        if _parts:
            _rep = pd.concat(_parts, ignore_index=True)
        else:
            _rep = _live_src.copy()
            _rep["Row Source"] = "Live (MIS)"

        # ITAD missing-bill rows → pulled out of the Details sheet onto
        # their own 'Reco Items' sheet (they're also excluded from the summary).
        if len(_rep):
            _reco_mask = _reco_exclusion_mask(_rep, reco_ships)
            _reco = _rep[_reco_mask]
            _rep = _rep[~_reco_mask]
            if len(_reco):
                _reco.to_excel(w, sheet_name="Reco Items", index=False)
                _headers.append(("Reco Items", 1))

        # Display rename in the sheet itself: old accumulated rows may still say
        # "Metal" in Broad Category — show the current vertical name.
        if "Broad Category" in _rep.columns:
            _rep["Broad Category"] = _rep["Broad Category"].map(_canon_label)

        # Move orphan shipments (Service Charges, etc. with blank Shipment ID) to the bottom
        if "Shipment ID" in _rep.columns:
            _is_orphan = _rep["Shipment ID"].astype(str).str.strip().isin(["", "nan", "None", "NaT"])
            _rep = pd.concat([_rep[~_is_orphan], _rep[_is_orphan]], ignore_index=True)

        # Finance Up Charge rows → their OWN table below the main Details table
        # (matches the manual layout). Identified by the verified Remarks class.
        # Pulled from the SOURCE rows, not the tab split: IB's finance charges
        # carry no Shipment ID, so the B2B/warehouse split drops them from the
        # Enterprise tab — the manual still lists them there.
        def _rmk_of(df):
            c = next((c for c in df.columns
                      if "".join(ch for ch in str(c).lower() if ch.isalnum()) == "remarks"), None)
            if c is None:
                return pd.Series(False, index=df.index)
            return df[c].astype(str).str.strip().str.lower().eq("finance up charge")

        _main = _rep[~_rmk_of(_rep)]                       # keep them out of the main table
        _fu = _live_src[_rmk_of(_live_src)]
        if len(_fu) and vertical:
            _vkey = "".join(ch for ch in str(vertical).lower() if ch.isalnum())
            _fcat = _fu.iloc[:, 85].astype(str)
            if _vkey in ("enterprise", "processingcenter"):
                _fu = _fu[_fcat.str.strip().str.lower().str.replace(" ", "").str.startswith("institutional")]
            else:
                _fu = _fu[_fcat.map(_canon_label).map(
                    lambda c: "".join(ch for ch in str(c).lower() if ch.isalnum())) == _vkey]
        if len(_fu):
            _fu = _fu.reindex(columns=_tgt).copy()
            if "Broad Category" in _fu.columns:
                _fu["Broad Category"] = _fu["Broad Category"].map(_canon_label)
            _fu["Row Source"] = "Live (MIS)"
            _fu = _fu.reindex(columns=list(_main.columns))

        _main.to_excel(w, sheet_name="Details", index=False,
                       startrow=1)   # row 1 reserved for the colored group header
        _add_group_header(w.sheets["Details"], list(_main.columns))
        _headers.append(("Details", 2))   # column header, shifted by the group row
        if len(_fu):
            # 2 blank rows · title · repeated column header · the FU rows
            _fu_title = 2 + len(_main) + 3                     # 1-indexed excel row
            pd.DataFrame([["FINANCE UP CHARGE — non-material charge lines (blank Shipment ID)"]]) \
                .to_excel(w, sheet_name="Details", startrow=_fu_title - 1, startcol=0,
                          index=False, header=False)
            _fu.to_excel(w, sheet_name="Details", index=False, startrow=_fu_title)
            _headers.append(("Details", _fu_title + 1))

        # ── Sheets 5 & 6: Supplier / Buyer metrics — computed over the SAME
        # whole-FY rows as the Details sheet (main + Finance Up Charge), so
        # party totals reconcile against it. Includes GSTIN + materials dealt.
        try:
            _mrep = _rep.drop(columns=["Row Source"], errors="ignore")
            supplier_summary(_mrep).to_excel(w, sheet_name="Supplier Metrics", index=False)
            _headers.append(("Supplier Metrics", 1))
            buyer_summary(_mrep).to_excel(w, sheet_name="Buyer Metrics", index=False)
            _headers.append(("Buyer Metrics", 1))
        except Exception:
            pass    # metrics are additive extras — never block the workbook

        # ── Sheet 7: Column Guide — every report column's side/GST/meaning ───
        pd.DataFrame(COLUMN_GUIDE,
                     columns=["Column", "Side / Source", "GST", "What it is"]) \
            .to_excel(w, sheet_name="Column Guide", index=False)
        _headers.append(("Column Guide", 1))
    buf.seek(0)
    return _style_workbook(buf.read(), _headers, _highlights, _numfmt)


def category_reports_excel(category_dfs: dict[str, pd.DataFrame]) -> bytes:
    """One Excel workbook — one sheet per category report."""
    def _sheet_name(name: str) -> str:
        for ch in r"[]:*?/\\":
            name = name.replace(ch, "-")
        return name[:31]

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in category_dfs.items():
            df.to_excel(writer, sheet_name=_sheet_name(name), index=False)
        _style_workbook_simple(writer.book)
    buf.seek(0)
    return buf.read()

# ── Column‐group definitions for Profitability Report ────────────────────────
# Each entry: (group_label, list_of_column_names_belonging_to_the_group).
# The order here defines the order groups appear in the header row.
# Column names must match the engine output EXACTLY (pre-_uniq_cols names).

_PROF_GROUPS: list[tuple[str, list[str]]] = [
    ("Raw Data", [
        "Quarter", "Month", "Date", "Shipment ID",
    ]),
    ("Purchase Details", [
        "Supplier Name", "GST Reg No.", "Vendor Invoice No.",
        "Vendor Invoice Date", "P V No.", "P V Date", "State (Origin)",
        "Vehicle No.", "Material", "Qty (Kg)", "Price/Kg",
        "Purchase Price", "Return Qty", "Net Qty", "Basic Customs Duty",
    ]),
    ("Logistics", [
        "Transporter Name", "LR NO/BILL NO", "J V No.", "JV Date",
        "Logistics cost", "Debit note on logistic cost",
        "Logistics Provision", "Total Logistics Cost",
        "Operational Cost", "Cost/Kg.", "Divertion/Internal",
    ]),
    ("Debit Notes to Suppliers", [
        "Debit Note No.", "Debit Note Date.", "Debit Note No. 2",
        "Debit Note Date. 2", "Full Debit Note", "Actual Debit Note",
        "Provision for DN", "Total Cost",
    ]),
    ("Sales Details", [
        "Inv. Date", "Inv. No.", "Customer ID", "Buyer Name",
        "Buyer GST Number ", "Location (Origin)", "Location (Destination)",
        "State (Destination)", "Qty(Kg)", "Rate/Kg", "Amount",
        "Qty Check", "Return Qty", "Net Qty", "Divertion/Internal",
    ]),
    ("DN to Customer", [
        "Return Type", "Date : DN to Buyer", "DN to Buyer", "Amount",
    ]),
    ("Credit Notes from Customers", [
        "Credit Note No:1", "CN Date. No:1", "Credit Note No:2",
        "CN Date. No:2", "Full Credit Notes", "Actual Credit Note",
        "Provision for CN",
    ]),
    ("Without Provisions", [
        "Net Revenue", "Margin", "Reamrks - Margin", "Remarks",
        "LMI @ Inception", "Remarks @ Inception", "Margin (%)",
        "Margin Bucket",
    ]),
    ("CN & DN Checks", [
        "Total CN(Inc.Provisions)", "Total DN(Inc.Provisions)",
        "Check", "Actaul CN", "Actual DN", "Check",
    ]),
    ("Derived", [
        "Material-Short Form", "Supplier Type", "Month",
        "Cost", "Revenue", "Week No:", "Category (Material)",
        "Broad Category", "POC Name", "Gross Margin",
        "Recykal Margin", "Net Margin",
    ]),
    ("Financials with GST", [
        "Sales ", "Purchases", "Credit Note", "Debit Note", "Margin",
        "Bill Branch", "Inv Branch", "Vendor PAN No", "Customer PAN No",
        "GST TDS Applicability", "Cash Discount(Provision)",
        "Cash Discount", "Cash Discount. No", "CD Date", "SD",
    ]),
    ("Provenance", [
        "Cost Source", "Resale Note", "Row Source",
    ]),
]

# Group header colour palette — alternating so adjacent groups are distinct.
_GROUP_COLORS = [
    "1F4E79",  # deep blue
    "4472C4",  # medium blue
    "2E75B6",  # steel blue
    "548235",  # forest green
    "BF8F00",  # dark gold
    "843C0B",  # brown
    "7030A0",  # purple
    "C00000",  # dark red
    "2F5496",  # navy
    "385723",  # dark green
    "8C4B1A",  # copper
    "404040",  # charcoal
]


def _add_group_header(ws, columns: list[str]) -> None:
    """Insert a merged group‐header row (row 1) above the column headers
    (which are now in row 2 because pandas wrote with startrow=1).

    Matches column names to the _PROF_GROUPS definitions.  Duplicate column
    names (e.g. two 'Qty(Kg)') are handled by tracking how many times each
    name has been assigned — the first occurrence maps to the first group
    that claims it, the second to the next group, etc.

    _uniq_cols may have suffixed duplicates with '.1', '.2', etc.
    We strip those suffixes to recover the base name for group lookup."""

    import re as _re_local

    def _base_name(col: str) -> str:
        """Strip the '.N' suffix added by _uniq_cols (e.g. 'Qty(Kg).1' → 'Qty(Kg)')."""
        return _re_local.sub(r'\.\d+$', '', col)

    # Build a mapping: for each column position (0-indexed) → group label.
    _col_group: dict[int, str] = {}

    # Walk the actual columns and assign each to its group.
    _seen: dict[str, int] = {}  # base_name → how many times seen so far
    for pos, cname in enumerate(columns):
        base = _base_name(cname)
        occ = _seen.get(base, 0)
        _seen[base] = occ + 1
        # Find which group this (base_name, occurrence) belongs to
        cum_occ = 0
        for glabel, gcols_list in _PROF_GROUPS:
            if base in gcols_list:
                count_in_group = gcols_list.count(base)
                if occ >= cum_occ and occ < cum_occ + count_in_group:
                    _col_group[pos] = glabel
                    break
                cum_occ += count_in_group

    # Now write merged cells in row 1.
    # Walk columns left to right, grouping consecutive cols with the same label.
    ncols = len(columns)
    i = 0
    while i < ncols:
        label = _col_group.get(i, "")
        j = i + 1
        while j < ncols and _col_group.get(j, "") == label:
            j += 1
        # Columns i..j-1 share the same group.  Excel is 1-indexed.
        start_col = i + 1
        end_col = j  # j-1+1
        if label:  # only write non-empty groups
            if end_col > start_col:
                ws.merge_cells(
                    start_row=1, start_column=start_col,
                    end_row=1, end_column=end_col,
                )
            cell = ws.cell(row=1, column=start_col, value=label)
            # Pick colour from palette
            g_idx = next(
                (k for k, (gl, _) in enumerate(_PROF_GROUPS) if gl == label), 0
            )
            bg = _GROUP_COLORS[g_idx % len(_GROUP_COLORS)]
            cell.font = Font(bold=True, color="FFFFFF", size=11)
            cell.fill = PatternFill(start_color=bg, end_color=bg,
                                    fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")
        i = j


# ── Excel formatting ─────────────────────────────────────────────────────────

_HDR_FONT = Font(bold=True, color="FFFFFF")
_HDR_FILL = PatternFill(start_color="000000", end_color="000000", fill_type="solid")


def _style_workbook_simple(wb) -> None:
    """Auto-fit column widths and style header rows (black bg, white bold text)
    across every sheet in an openpyxl Workbook.  The Summary sheet uses stacked
    blocks (title row + header row + data rows) so we detect header rows by
    looking for the row immediately after a title row.

    The Profitability Report sheet has a group header in row 1 and column
    headers in row 2 (written with startrow=1), so we style row 2 as the
    header instead of row 1."""
    for ws in wb.worksheets:
        # ── 1. Identify header rows ───────────────────────────────────────────
        header_rows: set[int] = set()
        if ws.title == "Summary":
            # Stacked layout: "■ End Generator" title in col A, header is the NEXT row.
            for row_idx in range(1, ws.max_row + 1):
                val = ws.cell(row=row_idx, column=1).value
                if isinstance(val, str) and val.strip().startswith("■"):
                    if row_idx + 1 <= ws.max_row:
                        header_rows.add(row_idx + 1)
        elif ws.title in ("Profitability Report", "Details"):
            # Group header is row 1 (styled separately by _add_group_header).
            # Column headers are in row 2.
            header_rows.add(2)
        else:
            # Normal sheets: row 1 is the header (pandas default).
            header_rows.add(1)
            # Receivables/Payables have secondary tables further down.
            # Detect any row whose col-A value matches a known header name.
            if ws.title in ("Receivables", "Payables"):
                for row_idx in range(2, ws.max_row + 1):
                    v = ws.cell(row=row_idx, column=1).value
                    if isinstance(v, str) and v.strip().lower() in (
                        "vertical", "vendor vertical",
                        "transaction_number", "transaction number",
                        "date", "vendor_name", "vendor name",
                    ):
                        header_rows.add(row_idx)

        # ── 2. Apply header styling ───────────────────────────────────────────
        for row_idx in header_rows:
            for col_idx in range(1, ws.max_column + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = _HDR_FONT
                cell.fill = _HDR_FILL
                cell.alignment = Alignment(horizontal="center", vertical="center")

        # ── 3. Auto-fit column widths ─────────────────────────────────────────
        for col_idx in range(1, ws.max_column + 1):
            max_len = 0
            for row_idx in range(1, ws.max_row + 1):
                val = ws.cell(row=row_idx, column=col_idx).value
                if val is not None:
                    cell_len = len(str(val))
                    if cell_len > max_len:
                        max_len = cell_len
            # clamp: minimum 8, maximum 50; add small padding
            width = min(max(max_len + 3, 8), 50)
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = width


# ── internal helpers ─────────────────────────────────────────────────────────

def _safe(df: pd.DataFrame, col: str, default=0):
    """Return column if exists, else constant Series."""
    if col in df.columns:
        return df[col].fillna(default)
    return pd.Series(default, index=df.index)


def _get_col_by_pos(df: pd.DataFrame, pos: int):
    """Return column as Series by position (handles duplicate names)."""
    return df.iloc[:, pos]


def _base_agg(grp: pd.core.groupby.DataFrameGroupBy,
              qty_col: str,
              rev_col: str = "Amount_sales",
              cost_col: str = "Total Cost",
              margin_col: str = "Margin_BO") -> pd.DataFrame:
    """
    Standard aggregation: volume, revenue, cost, margin, margin%.
    Rename these before calling based on the positional columns extracted.
    """
    agg = grp.agg(
        Shipments    = (qty_col,    "count"),
        Total_Qty_Kg = (qty_col,    "sum"),
        Total_Revenue = (rev_col,   "sum"),
        Total_Cost   = (cost_col,   "sum"),
        Margin       = (margin_col, "sum"),
    ).reset_index()
    agg["Margin_%"] = np.where(
        agg["Total_Revenue"] != 0,
        (agg["Margin"] / agg["Total_Revenue"] * 100).round(2),
        0.0,
    )
    agg = agg.sort_values("Margin", ascending=False).reset_index(drop=True)
    return agg


def _extract_key_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pull the key numeric columns (by position, to avoid duplicate-name errors)
    and return a working copy with safe unique names.
    """
    cols = list(df.columns)

    # Position map (0-indexed, matching compute.py order):
    # 0=Quarter, 1=Month, 2=Date, 3=Shipment ID
    # 4=Supplier Name, 12=Material
    # 13=Qty(Kg) purchase, 15=Purchase Price, 16=Return Qty purch, 17=Net Qty purch
    # 27=Total Logistics Cost, 37=Total Cost (AM)
    # 46=Qty(Kg) sales, 49=Amount(sales), 65=Margin(BO), 67=LMI @ Inception
    # 69=Margin(%), 70=Margin Bucket
    # 39=Inv.Date, 40=Inv.No., 41=Customer ID, 42=Buyer Name
    # 1_dup=Month(mmm-yy) at pos 87, 93=Week No:, 22=Logistics cost(Y)
    # 84=Cost(CE), 85=Revenue(CF)

    # Position map matches compute.py cols list (0-indexed):
    # 0=Quarter,1=Month,2=Date,3=Shipment ID,4=Supplier Name,...
    # 12=Material,13=Qty(Kg),14=Price/Kg,15=Purchase Price
    # 16=Return Qty(purch),17=Net Qty(purch),18=Basic Customs Duty
    # 19=Transporter,20=LR NO,21=JV No,22=JV Date
    # 23=Logistics cost(Y),24=DN on logistics,25=Logistics Provision
    # 26=Total Logistics Cost(AB),27=Operational Cost,28=Cost/Kg.,29=Divertion/Int(purch)
    # 30-33=DN dates/numbers,34=Full DN,35=Actual DN,36=Provision DN,37=Total Cost(AM)
    # 38=Inv Date,39=Inv No,40=Customer ID,41=Buyer Name,42=Buyer GST
    # 43=Location Origin,44=Location Dest,45=State Dest
    # 46=Qty(Kg)sales,47=Rate/Kg,48=Amount(AX),49=Qty Check
    # 50=Return Qty(sales),51=Net Qty(sales),52=Divertion/Int(sales)
    # 53=Return Type,54=Date DN to Buyer,55=DN to Buyer,56=Amount(BF)
    # 57=CN No1,58=CN Date1,59=CN No2,60=CN Date2
    # 61=Full CN,62=Actual CN,63=Provision CN
    # 64=Net Revenue(BN),65=Margin(BO),66=Reamrks-Margin
    # 67=Remarks,68=LMI@Inception,69=Remarks@Inception
    # 70=Margin(%)(BT),71=Margin Bucket(BU)
    # 72=Total CN(Inc.Prov),73=Total DN(Inc.Prov),74=Check
    # 75=Actaul CN(BY),76=Actual DN(BZ),77=Check2
    # 78=Material-Short Form,79=Supplier Type
    # 80=Month(mmm-yy)(CD),81=Cost(CE),82=Revenue(CF),83=Week No(CG)
    # 84=Category(Material),85=Broad Category,86=POC Name
    # 87=Gross Margin(CK),88=Recykal Margin(CL),89=Net Margin(CM)
    # 90=Sales(gst),91=Purchases(gst),92=Credit Note(gst),93=Debit Note(gst),94=Margin(gst)
    # 95=Bill Branch,96=Inv Branch,...,104=SD
    pos_map = {
        "Quarter":          0,
        "Month_name":       1,
        "Date":             2,
        "Shipment_ID":      3,
        "Supplier_Name":    4,
        "GST_Reg_No":       5,
        "Vendor_Inv_No":    6,
        "Buyer_GST":        42,
        "Operational_Cost": 27,
        "Broad_Category":   85,
        "Material":         12,
        "Qty_Kg_purch":     13,
        "Price_Kg":         14,
        "Purchase_Price":   15,
        "Return_Qty_purch": 16,
        "Net_Qty_purch":    17,
        "Basic_Customs":    18,
        "Logistics_Cost":   23,    # Y
        "Total_Logistics":  26,    # AB
        "Cost_Kg":          28,
        "Total_Cost":       37,    # AM
        "Inv_Date":         38,
        "Inv_No":           39,
        "Customer_ID":      40,
        "Buyer_Name":       41,
        "Qty_Kg_sales":     46,
        "Rate_Kg_sales":    47,
        "Amount_sales":     48,    # AX
        "Return_Qty_sales": 50,
        "Net_Qty_sales":    51,
        "Net_Revenue":      64,    # BN
        "Margin_BO":        65,    # BO — profitability margin
        "Reamrks_Margin":   66,
        "LMI_Inception":    68,    # BR
        "Margin_pct":       70,    # BT
        "Margin_Bucket":    71,    # BU
        "Actaul_CN":        75,    # BY
        "Actual_DN":        76,    # BZ
        "Provision_for_DN": 36,    # AL (ReWerse 2.5% DN provision)
        "Provision_for_CN": 63,    # BM (ReWerse 2.5% CN provision)
        "Month_mmm_yy":     80,    # CD — second Month col (mmm-yy)
        "Cost_CE":          81,    # CE
        "Revenue_CF":       82,    # CF
        "Week_No":          83,    # CG
        "Bill_Branch":      95,
        "Inv_Branch":       96,
    }

    NUMERIC = {
        "Qty_Kg_purch","Price_Kg","Purchase_Price","Return_Qty_purch","Net_Qty_purch",
        "Basic_Customs","Logistics_Cost","Total_Logistics","Cost_Kg","Total_Cost",
        "Qty_Kg_sales","Rate_Kg_sales","Amount_sales","Return_Qty_sales","Net_Qty_sales",
        "Net_Revenue","Margin_BO","LMI_Inception","Margin_pct",
        "Actaul_CN","Actual_DN","Cost_CE","Revenue_CF","Operational_Cost",
        "Provision_for_DN","Provision_for_CN",
    }

    safe = {}
    ncols = len(df.columns)
    n_rows = len(df)
    for name, pos in pos_map.items():
        if pos < ncols:
            col = df.iloc[:, pos].reset_index(drop=True)
            if name in NUMERIC:
                col = pd.to_numeric(col, errors="coerce").fillna(0)
            safe[name] = col
        else:
            safe[name] = pd.Series(0 if name in NUMERIC else "", index=range(n_rows))

    return pd.DataFrame(safe)


# ══════════════════════════════════════════════════════════════════════════════
# 1. SUPPLIER-WISE SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def _first_text(s) -> str:
    """First non-blank value (used for a party's GSTIN)."""
    for x in s:
        t = str(x).strip()
        if t and t.lower() not in ("nan", "none", "0", "0.0"):
            return t
    return ""


def _uniq_join(s) -> str:
    """Unique, sorted, comma-joined values (the materials a party deals in)."""
    vals = sorted({str(x).strip() for x in s
                   if str(x).strip() and str(x).strip().lower() not in ("nan", "none")})
    return ", ".join(vals)


def supplier_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate by Supplier Name.
    Columns: Supplier, GSTIN, Shipments, Total_Qty_Kg, Purchase_Price,
             Logistics_Cost, Total_Cost, Net_Revenue, Margin, Margin_%,
             Avg_Cost_Kg, Materials
    """
    w = _extract_key_cols(df)
    grp = w.groupby("Supplier_Name")
    out = grp.agg(
        GSTIN           = ("GST_Reg_No",     _first_text),
        Shipments       = ("Shipment_ID",    "count"),
        Total_Qty_Kg    = ("Qty_Kg_purch",   "sum"),
        Purchase_Price  = ("Purchase_Price", "sum"),
        Logistics_Cost  = ("Total_Logistics","sum"),
        Total_Cost      = ("Total_Cost",     "sum"),
        Net_Revenue     = ("Net_Revenue",    "sum"),
        Margin          = ("Margin_BO",      "sum"),
        Materials       = ("Material",       _uniq_join),
    ).reset_index()
    out.rename(columns={"Supplier_Name": "Supplier"}, inplace=True)
    out["Margin_%"]    = np.where(out["Net_Revenue"] != 0,
                                  (out["Margin"] / out["Net_Revenue"] * 100).round(2), 0.0)
    out["Avg_Cost_Kg"] = np.where(out["Total_Qty_Kg"] != 0,
                                  (out["Total_Cost"] / out["Total_Qty_Kg"]).round(2), 0.0)
    out = out.sort_values("Margin", ascending=False).reset_index(drop=True)
    # Round numeric cols
    num_cols = ["Total_Qty_Kg","Purchase_Price","Logistics_Cost","Total_Cost","Net_Revenue","Margin"]
    out[num_cols] = out[num_cols].round(2)
    # keep the original column order — Materials goes last
    return out[[c for c in out.columns if c != "Materials"] + ["Materials"]]


# ══════════════════════════════════════════════════════════════════════════════
# 2. BUYER-WISE SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def buyer_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate by Buyer Name.
    Columns: Buyer, Shipments, Total_Qty_Kg, Amount_Sales, Net_Revenue, Margin, Margin_%
    """
    w = _extract_key_cols(df)
    grp = w.groupby("Buyer_Name")
    out = grp.agg(
        GSTIN         = ("Buyer_GST",     _first_text),
        Shipments     = ("Shipment_ID",   "count"),
        Total_Qty_Kg  = ("Qty_Kg_sales",  "sum"),
        Amount_Sales  = ("Amount_sales",  "sum"),
        Net_Revenue   = ("Net_Revenue",   "sum"),
        Total_Cost    = ("Total_Cost",    "sum"),
        Margin        = ("Margin_BO",     "sum"),
        Materials     = ("Material",      _uniq_join),
    ).reset_index()
    out.rename(columns={"Buyer_Name": "Buyer"}, inplace=True)
    out["Margin_%"] = np.where(out["Net_Revenue"] != 0,
                               (out["Margin"] / out["Net_Revenue"] * 100).round(2), 0.0)
    out = out.sort_values("Margin", ascending=False).reset_index(drop=True)
    num_cols = ["Total_Qty_Kg","Amount_Sales","Net_Revenue","Total_Cost","Margin"]
    out[num_cols] = out[num_cols].round(2)
    # keep the original column order — Materials goes last
    return out[[c for c in out.columns if c != "Materials"] + ["Materials"]]


# ══════════════════════════════════════════════════════════════════════════════
# 3. MATERIAL-WISE SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def material_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate by Material (Item Name).
    Includes avg Purchase Price/Kg and avg Sale Rate/Kg.
    """
    w = _extract_key_cols(df)
    grp = w.groupby("Material")
    out = grp.agg(
        Shipments       = ("Shipment_ID",    "count"),
        Total_Qty_Purch = ("Qty_Kg_purch",   "sum"),
        Total_Qty_Sales = ("Qty_Kg_sales",   "sum"),
        Purchase_Price  = ("Purchase_Price", "sum"),
        Net_Revenue     = ("Net_Revenue",    "sum"),
        Total_Cost      = ("Total_Cost",     "sum"),
        Margin          = ("Margin_BO",      "sum"),
        Avg_Buy_Rate    = ("Price_Kg",       "mean"),
        Avg_Sale_Rate   = ("Rate_Kg_sales",  "mean"),
    ).reset_index()
    out["Margin_%"] = np.where(out["Net_Revenue"] != 0,
                               (out["Margin"] / out["Net_Revenue"] * 100).round(2), 0.0)
    out = out.sort_values("Margin", ascending=False).reset_index(drop=True)
    out["Avg_Buy_Rate"]  = out["Avg_Buy_Rate"].round(2)
    out["Avg_Sale_Rate"] = out["Avg_Sale_Rate"].round(2)
    num_cols = ["Total_Qty_Purch","Total_Qty_Sales","Purchase_Price","Net_Revenue","Total_Cost","Margin"]
    out[num_cols] = out[num_cols].round(2)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 4. MONTHLY SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate by Quarter + Month (mmm-yy).
    Sorted by calendar order.
    """
    w = _extract_key_cols(df)
    # Use mmm-yy month for display; build sort key from Date
    w["_sort_key"] = pd.to_datetime(w["Date"], errors="coerce")
    w["Month_mmm_yy"] = w["Month_mmm_yy"].replace("", np.nan).fillna(
        w["_sort_key"].dt.strftime("%b-%y")
    )

    grp = w.groupby(["Quarter", "Month_mmm_yy"])
    out = grp.agg(
        Shipments      = ("Shipment_ID",    "count"),
        Total_Qty_Kg   = ("Qty_Kg_purch",   "sum"),
        Purchase_Price = ("Purchase_Price", "sum"),
        Logistics_Cost = ("Total_Logistics","sum"),
        Total_Cost     = ("Total_Cost",     "sum"),
        Net_Revenue    = ("Net_Revenue",    "sum"),
        Margin         = ("Margin_BO",      "sum"),
    ).reset_index()
    out["Margin_%"] = np.where(out["Net_Revenue"] != 0,
                               (out["Margin"] / out["Net_Revenue"] * 100).round(2), 0.0)
    # Sort by fiscal quarter then by date within month
    q_order = {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3, "": 4}
    out["_q_order"] = out["Quarter"].map(q_order).fillna(4)
    out["_m_order"] = pd.to_datetime(out["Month_mmm_yy"], format="%b-%y", errors="coerce")
    out = out.sort_values(["_q_order", "_m_order"]).drop(columns=["_q_order","_m_order"]).reset_index(drop=True)
    num_cols = ["Total_Qty_Kg","Purchase_Price","Logistics_Cost","Total_Cost","Net_Revenue","Margin"]
    out[num_cols] = out[num_cols].round(2)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 5. WEEKLY SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def weekly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate by fiscal Week No.
    """
    w = _extract_key_cols(df)
    w["Week_No"] = pd.to_numeric(w["Week_No"], errors="coerce").fillna(0).astype(int)
    w = w[w["Week_No"] > 0]

    grp = w.groupby("Week_No")
    out = grp.agg(
        Shipments      = ("Shipment_ID",    "count"),
        Total_Qty_Kg   = ("Qty_Kg_purch",   "sum"),
        Total_Cost     = ("Total_Cost",     "sum"),
        Net_Revenue    = ("Net_Revenue",    "sum"),
        Margin         = ("Margin_BO",      "sum"),
    ).reset_index()
    out["Margin_%"] = np.where(out["Net_Revenue"] != 0,
                               (out["Margin"] / out["Net_Revenue"] * 100).round(2), 0.0)
    out = out.sort_values("Week_No").reset_index(drop=True)
    num_cols = ["Total_Qty_Kg","Total_Cost","Net_Revenue","Margin"]
    out[num_cols] = out[num_cols].round(2)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 6. MARGIN BUCKET SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def margin_bucket_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Count and sum by Margin Bucket (Less Than 1%, 1%-2%, More than 2%).
    """
    w = _extract_key_cols(df)
    grp = w.groupby("Margin_Bucket")
    out = grp.agg(
        Shipments   = ("Shipment_ID",  "count"),
        Net_Revenue = ("Net_Revenue",  "sum"),
        Margin      = ("Margin_BO",    "sum"),
    ).reset_index()
    out["Margin_%"] = np.where(out["Net_Revenue"] != 0,
                               (out["Margin"] / out["Net_Revenue"] * 100).round(2), 0.0)
    bucket_order = {"Less Than 1%": 0, "1% - 2%": 1, "More than 2%": 2}
    out["_order"] = out["Margin_Bucket"].map(bucket_order).fillna(9)
    out = out.sort_values("_order").drop(columns="_order").reset_index(drop=True)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 7. TOP-N RANKINGS
# ══════════════════════════════════════════════════════════════════════════════

def top_n_rankings(df: pd.DataFrame, n: int = 5) -> dict:
    """
    Returns dict of DataFrames:
      - top_suppliers_margin   : Top N suppliers by Margin
      - top_buyers_margin      : Top N buyers by Margin
      - top_materials_margin   : Top N materials by Margin
      - top_suppliers_volume   : Top N suppliers by Qty
      - top_buyers_volume      : Top N buyers by Sales Qty
      - worst_suppliers_margin : Bottom N suppliers by Margin (lowest/most negative)
    """
    sup = supplier_summary(df)
    buy = buyer_summary(df)
    mat = material_summary(df)

    return {
        "top_suppliers_margin":   sup.head(n)[["Supplier","Shipments","Total_Qty_Kg","Net_Revenue","Margin","Margin_%"]],
        "top_buyers_margin":      buy.head(n)[["Buyer","Shipments","Net_Revenue","Margin","Margin_%"]],
        "top_materials_margin":   mat.head(n)[["Material","Shipments","Total_Qty_Purch","Net_Revenue","Margin","Margin_%"]],
        "top_suppliers_volume":   sup.sort_values("Total_Qty_Kg", ascending=False).head(n)[["Supplier","Total_Qty_Kg","Net_Revenue","Margin"]],
        "top_buyers_volume":      buy.sort_values("Total_Qty_Kg", ascending=False).head(n)[["Buyer","Total_Qty_Kg","Net_Revenue","Margin"]],
        "worst_suppliers_margin": sup.sort_values("Margin").head(n)[["Supplier","Shipments","Net_Revenue","Margin","Margin_%"]],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 8. EXECUTIVE SUMMARY (single-row KPIs)
# ══════════════════════════════════════════════════════════════════════════════

def executive_kpis(df: pd.DataFrame) -> dict:
    """
    Returns dict of top-level KPIs for the Management Dashboard header.
    """
    w = _extract_key_cols(df)
    total_revenue   = w["Net_Revenue"].sum()
    total_cost      = w["Total_Cost"].sum()
    total_margin    = w["Margin_BO"].sum()
    margin_pct      = round(total_margin / total_revenue * 100, 2) if total_revenue else 0
    total_shipments = w["Shipment_ID"].nunique()
    total_qty_purch = w["Qty_Kg_purch"].sum()
    total_qty_sales = w["Qty_Kg_sales"].sum()
    total_logistics = w["Total_Logistics"].sum()
    lmi_total       = w["LMI_Inception"].sum()

    return {
        "Total Shipments":       int(total_shipments),
        "Total Qty Purchased":   round(total_qty_purch, 2),
        "Total Qty Sold":        round(total_qty_sales, 2),
        "Total Revenue (₹)":     round(total_revenue, 2),
        "Total Cost (₹)":        round(total_cost, 2),
        "Total Logistics (₹)":   round(total_logistics, 2),
        "Total Margin (₹)":      round(total_margin, 2),
        "Overall Margin %":      margin_pct,
        "LMI @ Inception (₹)":  round(lmi_total, 2),
    }
