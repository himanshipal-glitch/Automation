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


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY-WISE PROFITABILITY SPLIT
# ══════════════════════════════════════════════════════════════════════════════

def _ib_has_vendor_invoice(df: pd.DataFrame, ship: pd.Series) -> pd.Series:
    """Per-row boolean: does this shipment have ANY vendor (purchase) invoice?
    IB(B2B) shipments with only logistics bills and no material purchase invoice
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
    ("Remarks",                "Manual note",              "—", "Free remark (blank in engine)"),
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


def split_by_category(profit_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Split the full profitability report into one report per Broad Category.

    Special rule — Institutional Business is split into TWO reports:
      - IB(B2B)       : rows whose Shipment ID starts with 'SHID'
      - IB(Warehouse) : all other Institutional Business rows

    Returns {report_name: DataFrame} preserving the exact 105 columns.
    """
    def _col(name, pos):
        norm = {"".join(c for c in str(col).lower() if c.isalnum()): col for col in profit_df.columns}
        k = "".join(c for c in name.lower() if c.isalnum())
        if k in norm:
            return profit_df[norm[k]].astype(str).str.strip()
        return profit_df.iloc[:, pos].astype(str).str.strip()

    cat  = _col("Broad Category", 85)
    ship = _col("Shipment ID", 3)

    out: dict[str, pd.DataFrame] = {}
    for c in sorted(cat.unique()):
        # Fake-DN rows stay only at the bottom of the full report — not a vertical.
        if str(c).strip().lower().startswith("fake dn"):
            continue
        mask = cat.eq(c)
        if c.lower().replace(" ", "").startswith("institutional"):
            # B2B = SH-prefixed EXCEPT internal 'MPIB' ones (warehouse/internal
            # transfers); Warehouse = non-SH OR containing 'MPIB'.
            _sh = ship.str.upper()
            b2b = mask & _sh.str.startswith("SH") & ~_sh.str.contains("MPIB", na=False)
            wh  = mask & (~_sh.str.startswith("SH") | _sh.str.contains("MPIB", na=False))
            b2b = b2b & _ib_has_vendor_invoice(profit_df, ship)
            # always emit BOTH reports — even if one currently has 0 rows
            out["IB(B2B)"]       = profit_df[b2b].reset_index(drop=True)
            out["IB(Warehouse)"] = profit_df[wh].reset_index(drop=True)
        else:
            label = c if c and c.lower() != "nan" else "Uncategorised"
            # MP (warehouse) movements don't belong to the vertical's report —
            # except Re-Commerce, whose MP sales are genuine (costed from older
            # bills). Kept in a separate 'Warehouse (MP)' report so the detail
            # sums cross-check the summary.
            if "re-commerce" not in str(c).lower() and "recommerce" not in str(c).lower():
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
    "DSO (Days)",
    "Payable",
    "DPO (Days)",
    "Working Capital Days",
    "Credit Notes (Value - Incl. Prov)",
    "Credit Notes (% to Revenue)",
    "Debit Notes (Value - Incl. Prov)",
    "Debit Notes (% to Purchase)",
    # Receivable/Payable bifurcated by INVOICE date at the FY start (1-Apr).
    # Display-only split — the original Receivables/Payable rows are unchanged.
    "Old Receivables (pre-Apr, exl Legacy)",
    "FY 27 Receivables",
    "Old Payables (pre-Apr)",
    "FY 27 Payables",
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


def _old_bal(df: pd.DataFrame | None, fy_start, exclude_legacy: bool = False) -> float:
    """Open balance of documents dated BEFORE the FY start ('Old' receivable/
    payable). For receivables the legacy-customer rule applies: long-overdue
    defaulter accounts are excluded, same list the Net Receivable uses."""
    if df is None or getattr(df, "empty", True) or fy_start is None:
        return 0.0
    bal_col  = next((c for c in df.columns if "balance" in str(c).lower()), None)
    date_col = next((c for c in df.columns if str(c).lower() == "date"), None)
    if bal_col is None or date_col is None:
        return 0.0
    bal = pd.to_numeric(df[bal_col], errors="coerce").fillna(0)
    dts = pd.to_datetime(df[date_col], errors="coerce")
    mask = dts.notna() & (dts < fy_start)
    if exclude_legacy:
        cust_col = next((c for c in df.columns if "customer_name" in str(c).lower()
                         or "customer name" in str(c).lower()), None)
        if cust_col is not None:
            try:
                import receivables as _rcv
                _names = [n for names in _rcv.LEGACY_CUSTOMERS.values() for n in names]
                cu = df[cust_col].astype(str).str.upper()
                legacy = cu.apply(lambda x: any(n in x for n in _names))
                mask &= ~legacy
            except Exception:
                pass
    return float(bal[mask].sum())


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
    #      IB(Warehouse) are left exactly as before (gross purchase, no DN net):
    #      their manuals carry ~0 actual DN, so netting would over-state margin.
    _cat  = w["Broad_Category"].astype(str)
    _ship = w["Shipment_ID"].astype(str).str.strip().str.upper()
    _no_net = (
        _cat.str.contains("re-commerce", case=False, na=False)
        | _cat.str.contains("recommerce", case=False, na=False)
        | _cat.str.contains("rewerse", case=False, na=False)
        | (_cat.str.strip().str.lower().str.startswith("institutional")
           & ~_ship.str.startswith("SH"))            # IB(Warehouse)
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

    data = {"Metric": SUMMARY_METRICS}
    _ocm = op_cost_by_month or {}
    # Old (pre-FY) balances are constants — the documents predate every column.
    _old_r = _old_bal(ar_df, fy_start, exclude_legacy=True)
    _old_p = _old_bal(ap_df, fy_start)
    for m in months:
        # recv_override is a single point-in-time net (legacy+unused+prefix rule);
        # apply it to the LATEST month only (it's a current snapshot), leave history
        # on the per-month cumulative balance.
        _rv = recv_override if (recv_override is not None and m == last_month) \
              else _bal_sum(ar_df, m, fy_start)
        _pv = pay_override if (pay_override is not None and m == last_month) \
              else _bal_sum(ap_df, m, fy_start)
        data[m] = _summary_block(w[w["_month"] == m],
                                 _rv, _pv,
                                 wd=_working_days(m),
                                 oc_override=(_ocm.get(m) if _ocm else None),
                                 qty_in_mt=qty_in_mt) + [
            # bifurcation rows — same balance math, split by invoice date at 1-Apr
            round(_old_r, 0),
            round(_bal_sum(ar_df, m, fy_start), 0),   # FY-dated, cumulative to month-end
            round(_old_p, 0),
            round(_bal_sum(ap_df, m, fy_start), 0),
        ]

    # FY working days = total days from FY start to the global cutoff (not summed)
    fy_wd = int((end_dt - fy_start).days) + 1 if (pd.notna(end_dt) and fy_start is not None) else 30
    data["FY Total"] = _summary_block(w,
                                      recv_override if recv_override is not None else _bal_sum(ar_df, None, fy_start),
                                      pay_override if pay_override is not None else _bal_sum(ap_df, None, fy_start),
                                      wd=fy_wd,
                                      oc_override=(sum(_ocm.values()) if _ocm else None),
                                      qty_in_mt=qty_in_mt) + [
        round(_old_r, 0),
        round(_bal_sum(ar_df, None, fy_start), 0),    # all FY-dated open balances
        round(_old_p, 0),
        round(_bal_sum(ap_df, None, fy_start), 0),
    ]

    return pd.DataFrame(data)


# ── Per-vertical receivables attribution (for DSO) ────────────────────────────
_AR_TOKEN_TAB = [
    ("rew", "ReWerse"), ("met", "Metal"), ("rec", "Re-Commerce"),
    ("afr", "AFR"), ("pet", "Plastic"), ("iad", "IT AD"), ("m4", "M4"),
]


def _ar_token_tab(tn: str) -> str:
    """Map an AR invoice number's segment token (e.g. 36/MET/27IN.. → Metal)."""
    import re as _re
    m = _re.match(r"^\d+/([A-Za-z0-9]+)/", str(tn))
    tok = m.group(1).lower() if m else ""
    for k, v in _AR_TOKEN_TAB:
        if k in tok:
            return v
    if tok == "ib" or "pib" in tok:
        return "IB(B2B)"
    return ""


def _inv_tab_map(profit_df: pd.DataFrame) -> dict:
    """invoice-number → tab label, from the profitability rows (handles the
    IB B2B/Warehouse split and the MP-warehouse carve-out)."""
    inv  = profit_df.iloc[:, 39].astype(str).str.strip()
    cat  = profit_df.iloc[:, 85].astype(str).str.strip()
    ship = profit_df.iloc[:, 3].astype(str).str.strip().str.upper()
    m = {}
    for iv, c, sh in zip(inv, cat, ship):
        if not iv or iv.lower() == "nan":
            continue
        cl = c.lower().replace(" ", "")
        if cl.startswith("institutional"):
            lab = "IB(B2B)" if (sh.startswith("SH") and "MPIB" not in sh) else "IB(Warehouse)"
        elif _re.sub(r"^\d+/", "", sh).startswith("MP") and "re-commerce" not in c.lower():
            lab = "Warehouse (MP)"
        else:
            lab = c if c and c.lower() != "nan" else ""
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
    s = df[tn].astype(str).str.strip()
    df["_tab"] = s.map(lambda x: imap.get(x) or _ar_token_tab(x))
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
                          op_cost_bills: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """
    One summary report per Broad Category — with Institutional Business
    split into IB(B2B) (Shipment ID starts 'SHID') and IB(Warehouse).
    Also includes an 'All Categories' overall summary first.
    Note: Receivables/Payables come from the company-wide AR/AP sheets and
    are the same on every tab (they are not category-attributable).
    """
    # positional access — works whether column names are exact or sanitized
    ship_all = profit_df.iloc[:, 3].astype(str).str.strip()    # Shipment ID
    cat_all  = profit_df.iloc[:, 85].astype(str)               # Broad Category

    # MP-prefixed shipments are WAREHOUSE movements and are normally excluded —
    # EXCEPT Re-Commerce, whose MP/RECM sales are now costed from the older
    # bills, so they DO count in the Re-Commerce summary.
    is_mp = _is_mp_ship(ship_all)
    is_rc = cat_all.str.contains("Re-Commerce", case=False, na=False)
    exclude = is_mp & ~is_rc
    main_df = profit_df[~exclude]
    mp_df   = profit_df[exclude]

    cat  = main_df.iloc[:, 85].astype(str).str.strip()        # Broad Category
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
        # NOTE: IB is intentionally NOT mapped here. IB(B2B) and IB(Warehouse) need
        # their own receivable split (the Enterprise sheet's B2B figure is a specific
        # subset, not the whole-IB net) — until that rule is cracked, IB keeps its
        # prior per-month balance rather than a wrong override.
        alias = {"metal": "Metal", "plastic": "Plastic", "rewerse": "ReWerse",
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
        return {"metal": "metal waste", "plastic": "plastic waste", "recommerce": "re-commerce",
                "itad": "it assets", "itassetsdisposition": "it assets",
                "afr": "(afr)", "m4": "(m4)", "ibb2b": "institutional",
                "ibwarehouse": "institutional"}.get(t)

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
            # B2B = SH-prefixed EXCEPT internal 'MPIB' ones (warehouse/internal
            # transfers); Warehouse = non-SH OR containing 'MPIB'.
            _sh = ship.str.upper()
            b2b = mask & _sh.str.startswith("SH") & ~_sh.str.contains("MPIB", na=False)
            wh  = mask & (~_sh.str.startswith("SH") | _sh.str.contains("MPIB", na=False))
            b2b = b2b & _ib_has_vendor_invoice(main_df, ship)
            # IB(B2B) receivable: only AR invoices that actually appear in the B2B
            # profitability (isolates B2B from warehouse, which share IB prefixes).
            _ib_recv = None
            if ar_df is not None and not getattr(ar_df, "empty", True):
                _tn = next((c for c in ar_df.columns
                            if "transaction" in str(c).lower() and "number" in str(c).lower()), None)
                _bc = next((c for c in ar_df.columns if "balance" in str(c).lower()), None)
                if _tn and _bc:
                    _b2b_invs = set(main_df[b2b].iloc[:, 39].astype(str).str.strip()) - {"", "nan"}
                    _sel = ar_df[ar_df[_tn].astype(str).str.strip().isin(_b2b_invs)]
                    _ib_recv = float(pd.to_numeric(_sel[_bc], errors="coerce").fillna(0).sum())
            out["IB(B2B)"]       = summary_report(main_df[b2b], _ar("IB(B2B)"), _ap("IB(B2B)"),
                                                  recv_override=_ib_recv, pay_override=_pay_net("IB(B2B)"),
                                                  axis_end=_axis_end)
            out["IB(Warehouse)"] = summary_report(main_df[wh], _ar("IB(Warehouse)"), _ap("IB(Warehouse)"),
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
    for _oos in ("ReWerse", "IB(Warehouse)"):
        out.pop(_oos, None)

    return out


def top_materials(profit_df: pd.DataFrame, tab: str, n: int = 5):
    """Top-n materials by margin for a vertical's LATEST data month — the table the
    manual mails carry ('these top 5 contributed X% of the month's margin').
    Returns (table_df, month_label, share_of_month_margin) or (None, None, None)."""
    w = _extract_key_cols(profit_df)
    ship = w["Shipment_ID"].astype(str).str.strip()
    cat  = w["Broad_Category"].astype(str)

    # same scoping as summaries_by_category: MP-warehouse rows excluded (except RC)
    is_mp = _is_mp_ship(ship)
    is_rc = cat.str.contains("Re-Commerce", case=False, na=False)
    w = w[~(is_mp & ~is_rc)]
    ship = w["Shipment_ID"].astype(str).str.strip().str.upper()
    cat  = w["Broad_Category"].astype(str)

    key = "".join(ch for ch in str(tab).lower() if ch.isalnum())
    if key in ("ibb2b", "ibwarehouse"):
        inst = cat.str.strip().str.lower().str.startswith("institutional")
        b2b = inst & ship.str.startswith("SH") & ~ship.str.contains("MPIB", na=False)
        if key == "ibb2b":
            mask = b2b & _ib_has_vendor_invoice(w, w["Shipment_ID"].astype(str).str.strip())
        else:
            mask = inst & ~b2b
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


def combined_workbook(summaries: dict[str, pd.DataFrame],
                      profit_df: pd.DataFrame,
                      ar_df: pd.DataFrame | None = None,
                      ap_df: pd.DataFrame | None = None,
                      vertical: str | None = None) -> bytes:
    """One Excel with four stacked sheets — Summary, Receivables, Payables,
    Profitability Report. If `vertical` is given, everything is filtered to it;
    otherwise all verticals are included (stacked by type)."""
    import io as _io
    import receivables as _recv

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
            row += len(df) + 3

        # ── Sheet 2: Receivables (build-up table + Legacy box + detail) ───────
        if ar_df is not None and not getattr(ar_df, "empty", True):
            rb = _recv.build_receivables(ar_df)
            summ, det = rb["summary"], rb["detail"]
            if vertical:
                vn = "".join(c for c in vertical.lower() if c.isalnum())
                alias = {"metal": "Metal", "plastic": "Plastic", "rewerse": "ReWerse",
                         "recommerce": "Re-Commerce", "itad": "ITAD", "afr": "AFR", "m4": "M4",
                         "ibb2b": "IB", "institutionalbusiness": "IB"}.get(vn, vertical)
                summ = summ[summ["Vertical"].astype(str) == alias]
                if "Vertical" in det.columns:
                    det = det[det["Vertical"].astype(str) == alias]
            # 1) Net build-up: Gross − Legacy − Unused = Net (already columns of summ)
            pd.DataFrame([["NET RECEIVABLE = Gross − Legacy − Unused Credits"]]).to_excel(
                w, sheet_name="Receivables", startrow=0, startcol=0, index=False, header=False)
            summ.to_excel(w, sheet_name="Receivables", startrow=1, index=False)
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
                sub = {"metal": "metal waste", "plastic": "plastic waste", "recommerce": "re-commerce",
                       "itad": "it assets", "afr": "(afr)", "m4": "(m4)", "ibb2b": "institutional"}.get(
                       "".join(c for c in vertical.lower() if c.isalnum()))
                if sub:
                    ap = ap[ap[_vc].astype(str).str.lower().str.contains(sub, na=False, regex=False)]
            if _vc and _bc:
                tot = (pd.to_numeric(ap[_bc], errors="coerce").fillna(0)
                       .groupby(ap[_vc].astype(str)).sum().reset_index()
                       .rename(columns={_bc: "Payable"}))
                tot.columns = ["Vendor Vertical", "Payable"]
                tot.to_excel(w, sheet_name="Payables", startrow=0, index=False)
                ap.to_excel(w, sheet_name="Payables", startrow=len(tot) + 3, index=False)
            else:
                ap.to_excel(w, sheet_name="Payables", index=False)

        # ── Sheet 4: Profitability Report — whole FY, ONE uniform schema ─────
        # Every row (frozen months from the manual files' Details + live months
        # from the accumulated store) is aligned to the ENGINE's column set, so
        # the sheet is a single auditable table: filter by Month, sum any column,
        # cross-check the FY Total. Manual-only columns are dropped; engine
        # columns the manual lacks stay blank. 'Row Source' marks provenance.
        # No month appears twice per vertical.
        try:
            import frozen as _frozen
            import os as _os
            _fdet = _frozen.frozen_details(_os.path.dirname(_os.path.abspath(__file__)))
        except Exception:
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
        _tgt = list(_live_src.columns)

        def _nrm(s):
            return "".join(ch for ch in str(s).lower() if ch.isalnum() or ch == "%")
        _tmap = {}
        for _c in _tgt:
            _tmap.setdefault(_nrm(_c), _c)

        def _align(dfm):
            """Map a manual Details frame onto the engine's columns by name."""
            ren, used = {}, set()
            for _c in dfm.columns:
                _t2 = _tmap.get(_nrm(_c))
                if _t2 and _t2 not in used:
                    ren[_c] = _t2
                    used.add(_t2)
            out = dfm.rename(columns=ren)
            return out.loc[:, [c for c in out.columns if c in used]].reindex(columns=_tgt)

        rep_by_tab = ({vertical: split_by_category(_live_src).get(vertical, _live_src)}
                      if vertical else split_by_category(_live_src))
        _parts = []
        for _t, _df_t in rep_by_tab.items():
            _f = _fdet.get(_t)
            if _f is not None:
                _fdf, _fmonths = _f
                _al = _align(_fdf).copy()
                _al["Row Source"] = f"Manual file ({_t})"
                _parts.append(_al)
                # live rows for this tab: only months NOT already frozen above
                _mm = pd.to_datetime(_df_t.iloc[:, 2], errors="coerce").dt.strftime("%b-%y")
                _df_t = _df_t[~_mm.isin(_fmonths)]
            if len(_df_t):
                _lv = _df_t.reindex(columns=_tgt).copy()
                _lv["Row Source"] = "Live (MIS)"
                _parts.append(_lv)
        if _parts:
            _rep = pd.concat(_parts, ignore_index=True)
        else:
            _rep = _live_src.copy()
            _rep["Row Source"] = "Live (MIS)"
        _rep.to_excel(w, sheet_name="Profitability Report", index=False)

        # ── Sheets 5 & 6: Supplier / Buyer metrics — computed over the SAME
        # whole-FY rows as the Profitability Report sheet, so party totals
        # reconcile against it. Includes each party's GSTIN + materials dealt.
        try:
            _mrep = _rep.drop(columns=["Row Source"], errors="ignore")
            supplier_summary(_mrep).to_excel(w, sheet_name="Supplier Metrics", index=False)
            buyer_summary(_mrep).to_excel(w, sheet_name="Buyer Metrics", index=False)
        except Exception:
            pass    # metrics are additive extras — never block the workbook

        # ── Sheet 7: Column Guide — every report column's side/GST/meaning ───
        pd.DataFrame(COLUMN_GUIDE,
                     columns=["Column", "Side / Source", "GST", "What it is"]) \
            .to_excel(w, sheet_name="Column Guide", index=False)

    buf.seek(0)
    return buf.read()


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
    buf.seek(0)
    return buf.read()


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
