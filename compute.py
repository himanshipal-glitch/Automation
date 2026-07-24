"""
Profitability Report Formula Engine
Builds the exact 105-column report matching Attribute_Formula_Mapping.xlsx.

FORMULA REFERENCE (col letter → formula used):
  B   Quarter          = fiscal quarter derived from Invoice Date (Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar)
  C   Month            = month name derived from Invoice Date (e.g. "May")
  D   Date             = Invoice.Invoice Date
  E   Shipment ID      = Bill.CF.SO Number
  F   Supplier Name    = Bill.Vendor Name
  G   GST Reg No.      = Bill.GST Identification Number (GSTIN)
  H   Vendor Invoice No= Bill.Bill Number
  I   Vendor Invoice Dt= Bill.CF.Supplier Invoice Date
  J   P V No.          = Bill.CF.Purchase
  K   P V Date         = Bill.CF.Voucher Date
  L   State (Origin)   = Bill.Source of Supply
  M   Vehicle No.      = Bill.CF.Vehicle No
  N   Material         = Bill.Item Name
  O   Qty (Kg)         = Bill.Quantity
  P   Price/Kg         = Bill.Rate
  Q   Purchase Price   = Bill.Quantity × Bill.Rate  (= Item Total)
  R   Return Qty       = SUM(Vendor_Credits.Quantity) [DN_1 + DN_2], but each
                         DN counts only if its SubTotal > 50% of Gross Margin
                         (Amount - Purchase Price); else treated as 0
  S   Net Qty          = O - R
  T   Basic Customs    = 0  [not populated]
  U   Transporter Name = Bill_Logistics.Vendor Name  [blank if no logistics bill]
  V   LR NO/BILL NO    = Bill_Logistics.Bill Number
  W   J V No.          = Bill_Logistics.CF.Purchase
  X   JV Date          = Bill_Logistics.CF.Supplier Invoice Date
  Y   Logistics cost   = Bill_Logistics.SubTotal  [0 if no logistics bill]
  Z   DN on logistics  = 0  [not in current data]
  AA  Logistics Prov.  = Invoice.CF.Estimated Logistics Cost
  AB  Total Log. Cost  = Y + Z + AA
  AC  Operational Cost = 0  [not populated]
  AD  Cost/Kg.         = IFERROR((Q + AB) / S, 0)
  AE  Divertion/Int.   = 0  [not populated]
  AF  Debit Note No.   = DN_1.Vendor Credit Number
  AG  Debit Note Date  = DN_1.Vendor Credit Date
  AH  Debit Note No.2  = DN_2.Vendor Credit Number
  AI  Debit Note Date.2= DN_2.Vendor Credit Date
  AJ  Full Debit Note  = 0  [not populated]
  AK  Actual Debit Note= 0  [hardcoded in report — analyst fills manually]
  AL  Provision for DN = 0  [not populated]
  AM  Total Cost       = Q + AB + AL + AK + AJ + T + AE
  AN  Inv. Date        = Invoice.Invoice Date
  AO  Inv. No.         = Invoice.Invoice Number
  AP  Customer ID      = Invoice.Customer ID
  AQ  Buyer Name       = Invoice.Customer Name
  AR  Buyer GST Number = Invoice.GST Identification Number (GSTIN)
  AS  Location (Origin)= Invoice.CF.Dispatch From
  AT  Location (Dest.) = Invoice.Shipping City
  AU  State (Dest.)    = Invoice.Shipping State
  AV  Qty(Kg)          = Invoice.Quantity
  AW  Rate/Kg          = Invoice.Item Price
  AX  Amount           = Invoice.SubTotal
  AY  Qty Check        = (AV == O)
  AZ  Return Qty(sales)= SUM(Credit_Note.Quantity) [CN_1 + CN_2], same rule:
                         each CN counts only if SubTotal > 50% of Gross Margin
  BA  Net Qty (sales)  = AV - AZ
  BB  Divertion/Int.   = 0  [not populated]
  BC  Return Type      = ""  [not populated]
  BD  Date DN to Buyer = ""  [not populated]
  BE  DN to Buyer      = ""  [not populated]
  BF  Amount(DN)       = 0   [not populated]
  BG  Credit Note No:1 = CN_1.Credit Note Number
  BH  CN Date. No:1    = CN_1.Credit Note Date
  BI  Credit Note No:2 = CN_2.Credit Note Number
  BJ  CN Date. No:2    = CN_2.Credit Note Date
  BK  Full Credit Notes= 0   [not populated]
  BL  Actual Credit Note= 0  [hardcoded in report — analyst fills manually]
  BM  Provision for CN = 0   [not populated]
  BN  Net Revenue      = AX + BK + BL + BM + BB + BF
  BO  Margin           = BN - AM
  BP  Reamrks - Margin = IF(BO>=0, "Positive Margin", "Negative Margin")
  BQ  Remarks          = ""  [not populated]
  BR  LMI @ Inception  = AX - Y - Q - AA - T + BB
  BS  Remarks@Inception= IF(BR<0, "Negative Margin at Inception", "Positive Margin at Inception")
  BT  Margin (%)       = IFERROR(BO / BN, 0)
  BU  Margin Bucket    = IF(BT<1%, "Less Than 1%", IF(BT>2%, "More than 2%", "1% - 2%"))
  BV  Total CN(Inc.P.) = BL + BM
  BW  Total DN(Inc.P.) = AL + AK
  BX  Check            = BV - BW
  BY  Actaul CN        = CN_1.SubTotal + CN_2.SubTotal  [raw positive, for check]
  BZ  Actual DN        = DN_1.SubTotal + DN_2.SubTotal  [raw positive, for check]
  CA  Check            = BY - BZ
  CB  Material-Short   = ""  [not populated]
  CC  Supplier Type    = ""  [not populated]
  CD  Month (mmm-yy)   = TEXT(AN, "mmm-yy")
  CE  Cost             = AM - AL - AA
  CF  Revenue          = BN - BM
  CG  Week No:         = INT((Date - FY_Start) / 7) + 1  [fiscal year starting 1-Apr]
  CH  Category(Mat.)   = ""  [not populated]
  CI  Broad Category   = ""  [not populated]
  CJ  POC Name         = ""  [not populated]
  CK  Gross Margin     = AX - Q
  CL  Recykal Margin   = CK - Y + Z
  CM  Net Margin       = BN - AM  [same as BO]
  CN  Sales            = AX * 1.18
  CO  Purchases        = -(Q * 1.18)  [negative: cost]
  CP  Credit Note      = -(BY * 1.18) [negative: reduces revenue]
  CQ  Debit Note       = BZ * 1.18   [positive: vendor recovery]
  CR  Margin(GST)      = SUM(CN:CQ)  = CN + CO + CP + CQ
  CS  Bill Branch      = Bill.Branch Name
  CT  Inv Branch       = Invoice.Account
  CU  Vendor PAN No    = Bill.GST Identification Number (GSTIN)
  CV  Customer PAN No  = Invoice.GST Identification Number (GSTIN)
  CW  GST TDS          = ""  [not populated]
  CX  Cash Disc(Prov.) = 0   [not populated]
  CY  Cash Discount    = 0   [not populated]
  CZ  Cash Disc. No    = ""  [not populated]
  DA  CD Date          = ""  [not populated]
  DB  SD               = ""  [external XLOOKUP — not available]
"""

import pandas as pd
import numpy as np

# Shipments removed by hand in the manual report (Recon Items). Add Shipment IDs
# (CF.SO Number) here to drop them from the profitability report. (Empty by default —
# don't exclude date-boundary shipments like SH06261404, which are simply newer than
# the manual's cutoff date, not genuine exclusions.)
MANUALLY_EXCLUDED_SHIPMENTS: set = set()

# Shipments found (manually) to carry a FAKE debit note. They stay in the report for
# their invoice month, but are pulled OUT of the vertical totals into a separate
# "Fake DN (Excluded)" bucket, annotated, and listed at the bottom of the report.
FAKE_DN_SHIPMENTS: set = {"SH032616011"}
FAKE_DN_CATEGORY = "Fake DN (Excluded)"

# ── CN/DN provision rates ─────────────────────────────────────────────────────
# Default provision rate per Broad Category, as a FRACTION (0.0455 = 4.55%).
# Applied to Sale Amount (Provision for CN) and Purchase Price (Provision for DN).
# The user can override these per-vertical from the Summary page (persisted via
# database.save_provision_rates); build_profitability takes the override dict.
# ReWerse is OUT OF SCOPE (popped from every summary) but keeps its rate so the
# raw report stays internally consistent — it is NOT shown in the editor.
DEFAULT_PROVISION_RATES: dict[str, float] = {
    "End Generator": 0.0455,
    "Plastic":       0.025,
    "AFR":           0.025,
    "ReWerse":       0.025,
}
# In-scope verticals whose provision the user may edit in the UI.
EDITABLE_PROVISION_VERTICALS: list[str] = ["End Generator", "Plastic", "AFR"]


def _safe_div(num, den, positive_only: bool = False):
    """Element-wise divide that returns 0 where the denominator is 0 (or <=0
    when positive_only) — never raises ZeroDivisionError."""
    num = np.asarray(num, dtype=float)
    den = np.asarray(den, dtype=float)
    num, den = np.broadcast_arrays(num, den)
    cond = (den > 0) if positive_only else (den != 0)
    return np.divide(num, den, out=np.zeros_like(den, dtype=float), where=cond)


def _s(df: pd.DataFrame, col: str, default=0):
    """Return column series if present, else constant series."""
    if col in df.columns:
        return df[col].fillna(default) if default != "" else df[col].fillna("")
    return pd.Series(default, index=df.index, dtype=type(default))


def _dt_str(series, fmt="%Y-%m-%d"):
    return pd.to_datetime(series, errors="coerce").dt.strftime(fmt).fillna("")


def _fiscal_quarter(dates: pd.Series) -> pd.Series:
    m = pd.to_datetime(dates, errors="coerce").dt.month
    def _q(x):
        if pd.isna(x): return ""
        if   x in [4,5,6]:  return "Q1"
        elif x in [7,8,9]:  return "Q2"
        elif x in [10,11,12]: return "Q3"
        else:                return "Q4"
    return m.apply(_q)


def _fiscal_week(dates: pd.Series) -> pd.Series:
    d = pd.to_datetime(dates, errors="coerce")
    def _wk(dt):
        if pd.isna(dt): return ""
        fy_start = pd.Timestamp(dt.year if dt.month >= 4 else dt.year - 1, 4, 1)
        return int((dt - fy_start).days / 7) + 1
    return d.apply(_wk)


def build_profitability(merged_df: pd.DataFrame,
                        logistics_df: pd.DataFrame | None = None,
                        no_dn_shipments: set | None = None,
                        provision_rates: dict | None = None,
                        bill_purchases_df: pd.DataFrame | None = None) -> pd.DataFrame:

    d = merged_df.copy()

    # ── Manually-excluded shipments (Recon Items) ─────────────────────────────
    # Shipments the team removes by hand in the manual report (e.g. SH06261404,
    # an off-rate metal deal). Add Shipment IDs here to drop them from the report.
    if MANUALLY_EXCLUDED_SHIPMENTS and "CFSO_Number" in d.columns:
        _ex = d["CFSO_Number"].astype(str).str.strip().isin(MANUALLY_EXCLUDED_SHIPMENTS)
        if _ex.any():
            d = d[~_ex].reset_index(drop=True)

    # Flag shipments listed in the 'cf.dn = no' exclusion file (no provision)
    if no_dn_shipments and "CFSO_Number" in d.columns:
        def _excl(s):
            return 1 if any(p.strip() in no_dn_shipments for p in str(s).split(",")) else 0
        d["_no_dn_excluded"] = d["CFSO_Number"].map(_excl)

    # ── Raw source series ─────────────────────────────────────────────────────
    inv_date = pd.to_datetime(_s(d, "Invoice_Date", ""), errors="coerce")

    # O, P, Q  — Bill purchase
    O = _s(d, "Quantity_bill")          # Qty (Kg)
    P = _s(d, "Rate")                   # Price/Kg
    Q = O * P                           # Purchase Price = Qty × Rate

    # AV, AW, AX — Invoice sales
    AV = _s(d, "Quantity_inv")          # Qty(Kg) sales
    AW = _s(d, "Item_Price")            # Rate/Kg sales
    AX = AV * AW                        # Amount sales = Qty × Rate (per line —
                                        # SubTotal is invoice-level and repeats
                                        # across lines of multi-item invoices)

    # CN raw subtotals (positive from source)
    cn1_sub = _s(d, "CN_1_SubTotal");  cn2_sub = _s(d, "CN_2_SubTotal")
    cn1_qty = _s(d, "CN_1_Quantity");  cn2_qty = _s(d, "CN_2_Quantity")

    # DN raw subtotals (positive from source)
    dn1_sub = _s(d, "DN_1_SubTotal");  dn2_sub = _s(d, "DN_2_SubTotal")
    dn1_qty = _s(d, "DN_1_Quantity");  dn2_qty = _s(d, "DN_2_Quantity")

    BY = cn1_sub + cn2_sub              # Actaul CN (raw positive)
    # Actual DN — the vendor-credit SubTotal in Zoho is GST-INCLUSIVE (18%), but
    # the cost should carry the EX-GST value (the manual divides SubTotal by
    # 1.18). Full reversals are re-set to the full purchase further below.
    _GST = 1.18
    BZ = (dn1_sub + dn2_sub) / _GST     # Actual DN (ex-GST goods value)

    # ── End Generator resell linkage ───────────────────────────────────────────────────
    # An End Generator shipment that was fully reversed AND returned to the seller (full
    # CN + DN) can be re-purchased and re-sold under a NEW shipment id with the
    # SAME material + quantity. Following the manual, the RESALE keeps the
    # ORIGINAL bill's purchase cost (not the new rebuy bill); both legs are
    # flagged so resold items are visible. End Generator only — no merging of rows, so
    # no double-count (the returned leg still nets to 0 via its own CN/DN).
    _resale_note = pd.Series("", index=d.index)
    try:
        _ship_r  = _s(d, "CFSO_Number", "").astype(str).str.strip()
        _ismetal = _s(d, "Account_inv", "").astype(str).str.contains("metal|end generator", case=False, na=False)
        _mat_r   = _s(d, "Item_Name", "").astype(str).str.strip()
        _gr = pd.DataFrame({"sid": _ship_r, "metal": _ismetal, "mat": _mat_r,
                            "sale": AX, "cn": BY, "dn": BZ, "qty": O})
        _gg = _gr[_gr["metal"]].groupby("sid").agg(
            sale=("sale", "sum"), cn=("cn", "sum"), dn=("dn", "sum"),
            qty=("qty", "sum"), mat=("mat", "first"))
        _returned = _gg[(_gg["sale"] > 0) & (_gg["cn"] >= 0.95 * _gg["sale"]) & (_gg["dn"] > 0)]
        _cleanish = _gg[(_gg["cn"] == 0) & (_gg["dn"] == 0)]
        for _asid, _ar in _returned.iterrows():
            _a_pur = float(Q[_ship_r == _asid].sum())          # original bill cost
            _cand = _cleanish[(_cleanish["mat"] == _ar["mat"])
                              & ((_cleanish["qty"] - _ar["qty"]).abs() < 1)]
            for _bsid in _cand.index:
                _bmask = (_ship_r == _bsid)
                # If the resale already has its OWN current purchase bill, keep it
                # (the manual costs each shipment at its own bill). Only re-cost at
                # the original bill when the resale has NO purchase of its own.
                if float(Q[_bmask].sum()) > 0:
                    continue
                _bqty  = float(O[_bmask].sum())
                # re-cost the resale at the ORIGINAL bill (spread by qty share)
                if _bqty > 0:
                    Q.loc[_bmask] = _a_pur * (O[_bmask] / _bqty)
                else:
                    Q.loc[_bmask] = _a_pur / max(int(_bmask.sum()), 1)
                _resale_note.loc[_bmask] = "Resold — cost = original bill (" + _asid + ")"
                _resale_note.loc[_ship_r == _asid] = "Returned to seller; resold as " + _bsid
    except Exception:
        pass

    # ── Logistics ─────────────────────────────────────────────────────────────
    # Y  = Logistics cost from bill_logistics
    if logistics_df is not None and not logistics_df.empty:
        log_map = (logistics_df.groupby("CFSO_Number")[["SubTotal","Vendor_Name","Bill_Number","CFPurchase","CFSupplier_Invoice_Date"]]
                   .first().reset_index())
        d = d.merge(log_map.rename(columns={
            "SubTotal":              "_log_Y",
            "Vendor_Name":           "_log_vendor",
            "Bill_Number":           "_log_bill_no",
            "CFPurchase":            "_log_jv",
            "CFSupplier_Invoice_Date":"_log_jv_date",
        }), on="CFSO_Number", how="left")

    Y   = _s(d, "_log_Y")               # Logistics cost
    Z   = pd.Series(0.0, index=d.index) # Debit note on logistic cost (not in data)
    AA  = _s(d, "CFEstimated_Logistics_Cost")  # Logistics Provision (estimate)
    # The provision is only an ESTIMATE of the transport cost. Drop it whenever the
    # SHIPMENT has any ACTUAL logistics bill — decided at SHIPMENT level, not line
    # level: if even one line of the shipment carries a real logistics cost, no
    # estimate is taken for the whole shipment.
    _ship_id = _s(d, "CFSO_Number", "").astype(str).str.strip()
    _has_actual_log = (Y.fillna(0) != 0)
    _drop_est = np.where(_ship_id != "",
                         _has_actual_log.groupby(_ship_id).transform("max").astype(bool),
                         _has_actual_log)
    AA  = pd.Series(np.where(_drop_est, 0.0, AA), index=d.index)
    AB  = Y + Z + AA                    # Total Logistics Cost
    AC  = _s(d, "_operational_cost", 0.0)  # Operational Cost (service/penalty orphan bills)
    AE  = pd.Series(0.0, index=d.index) # Divertion/Internal (purchase)
    T   = pd.Series(0.0, index=d.index) # Basic Customs Duty
    BB  = pd.Series(0.0, index=d.index) # Divertion/Internal (sales)
    BF  = pd.Series(0.0, index=d.index) # Amount DN to Buyer
    BK  = pd.Series(0.0, index=d.index) # Full Credit Notes
    AJ  = pd.Series(0.0, index=d.index) # Full Debit Note

    # ── Vendor-DN FULL REVERSAL (goods returned to seller) ────────────────────
    # When a vendor credit (DN) covers ~the whole of the bill it's raised against,
    # the goods were fully RETURNED to that supplier. The manual books that bill
    # leg as a "Full Debit Note": the leg's purchase is credited back (cost → 0,
    # NO DN provision on it) while the shipment's OTHER bill legs stay normal.
    # Detect per DN via its Associated Bill Number — DN ex-GST >= 95% of that
    # bill's purchase (qty × rate). `_dn_rev` = ex-GST purchase of the reversed
    # leg(s) (booked as Full DN, and excluded from the provision base);
    # `_dn_rev_actual` = the DN ex-GST removed from Actual DN so it isn't counted
    # twice. PARTIAL DNs (< 95%) are untouched — only true full returns change.
    _dn_rev = pd.Series(0.0, index=d.index)
    _dn_rev_actual = pd.Series(0.0, index=d.index)
    if bill_purchases_df is not None and not getattr(bill_purchases_df, "empty", True):
        _bp = bill_purchases_df
        _bp_pur = (pd.to_numeric(_s(_bp, "Quantity"), errors="coerce").fillna(0.0)
                   * pd.to_numeric(_s(_bp, "Rate"), errors="coerce").fillna(0.0))
        _bp_map = _bp_pur.groupby(_s(_bp, "Bill_Number", "").astype(str).str.strip()).sum().to_dict()
        _row_bill = _s(d, "Bill_Number", "").astype(str).str.strip()
        for _dsub, _acol in ((dn1_sub, "DN_1_Associated_Bill_Number"),
                             (dn2_sub, "DN_2_Associated_Bill_Number")):
            _assoc = _s(d, _acol, "").astype(str).str.strip()
            _legpur = _assoc.map(lambda b: float(_bp_map.get(b, 0.0)))
            _exgst = _dsub / _GST
            # only reverse the row whose OWN bill is the one the DN is against —
            # so a fully-returned leg (its own orphan line) is zeroed, while the
            # invoiced leg (a different bill number) keeps its cost.
            _isfull = (_legpur > 0) & (_exgst >= 0.95 * _legpur) & (_row_bill == _assoc)
            _dn_rev = _dn_rev + pd.Series(np.where(_isfull, _legpur, 0.0), index=d.index)
            _dn_rev_actual = _dn_rev_actual + pd.Series(np.where(_isfull, _exgst, 0.0), index=d.index)
    AJ = -_dn_rev                       # Full Debit Note — credit back the returned leg
    BZ = BZ - _dn_rev_actual            # remove the reversed DN from Actual DN (booked via AJ)

    # ── ReWerse provision rule ────────────────────────────────────────────────
    # Provision applies to ReWerse shipments that are NOT in the 'cf.dn = no'
    # exclusion file (those shipments don't get a provision). For the rest:
    #   Provision for CN = 2.5% of Sale Amount                      (buyer side)  → reduces revenue
    #   Provision for DN = 2.5% of (Purchase Price + Transport AB)  (seller side)
    # '_no_dn_excluded' is 1 for shipments listed in the exclusion file.
    #   ...AND only if the SHIPMENT has NO actual Credit Note on ANY of its rows.
    #      If any row of a shipment has a CN, the WHOLE shipment is excluded
    #      (treated like it's in the query sheet) — no provision on any of its rows.
    # Provision rate is per Broad Category. Defaults (ReWerse 2.5%, End Generator
    # 4.55%, Plastic 2.5%) come from DEFAULT_PROVISION_RATES; the caller may
    # override any of them per-vertical via `provision_rates` (fractions).
    _rates  = {**DEFAULT_PROVISION_RATES, **(provision_rates or {})}
    _bcat   = _s(d, "Account_inv", "").astype(str)
    _rate   = pd.Series(0.0, index=d.index)
    _rate[_bcat.str.contains("rewerse", case=False, na=False)] = float(_rates.get("ReWerse", 0.0))
    _rate[_bcat.str.contains("metal|end generator",   case=False, na=False)] = float(_rates.get("End Generator", 0.0))
    _rate[_bcat.str.contains("plastic", case=False, na=False)] = float(_rates.get("Plastic", 0.0))
    _rate[_bcat.str.contains("afr", case=False, na=False)] = float(_rates.get("AFR", 0.0))
    _excluded   = _s(d, "_no_dn_excluded", 0).astype(float)
    _ship_key   = _s(d, "CFSO_Number", "").astype(str).str.strip()
    _ship_has_cn = BY.groupby(_ship_key).transform("max")   # >0 if shipment has any CN
    # Charge lines (Hydra charges, Finance Up-Charge, etc.) have NO real shipment
    # behind them — blank Shipment ID — so they take NO CN/DN provision. The manual
    # carries the full charge with no provision (verified: Finance Up-Charge 108,894
    # with no 4.55% deduction). Ordinary material sales all carry a Shipment ID.
    _prov_trig  = (_rate > 0) & (_excluded == 0) & (_ship_has_cn <= 0) & (_ship_key != "")
    BM  = pd.Series(np.where(_prov_trig, _rate * AX, 0.0), index=d.index)  # Provision for CN
    # Provision for DN is charged on the PURCHASE side. Base = Purchase Price PLUS
    # Transportation Charges (AB = Total Logistics Cost): provision = (Q + AB) × rate.
    # (Previously it was Q × rate only.) Applies to every vertical carrying a rate.
    # base excludes any FULLY-REVERSED leg (_dn_rev) — no provision on returned goods
    AL  = pd.Series(np.where(_prov_trig, _rate * ((Q - _dn_rev).clip(lower=0) + AB), 0.0), index=d.index)  # Provision for DN

    # ── Full credit-note reversal ──────────────────────────────────────────────
    # When a shipment's total Actual CN is >= 95% of its total Sale, the deal is
    # treated as fully reversed (the manual logs it under "Full Credit Notes"):
    #   • the full sale stays in Actual CN  → nets Net Revenue to ~0, AND
    #   • if a vendor DN exists (goods returned to seller), the Actual DN is
    #     capped at the full PURCHASE value (the raw DN SubTotal carries tax and
    #     can exceed the bill) → nets the cost to ~0.
    # Partial CN/DN are left untouched. (Resell case — a second invoice on the
    # same SH-id + item — keeps the bill side unchanged and must not be double
    # counted; that is handled upstream in merge_invoice_bill.)
    _ship_sale = AX.groupby(_ship_key).transform("sum")
    _ship_cn   = BY.groupby(_ship_key).transform("sum")
    _full_rev  = (_ship_sale > 0) & (_ship_cn >= 0.95 * _ship_sale)
    # Full reversal returned to seller → the ENTIRE purchase is credited back,
    # so the Actual DN = full purchase (Q), nets cost to 0. Partial DNs keep the
    # ex-GST value computed above.
    BZ  = pd.Series(np.where(_full_rev & (BZ > 0), Q, BZ), index=d.index)

    # ── Calculated columns ────────────────────────────────────────────────────
    # Return Qty rule: a note counts as a PHYSICAL return only if its SubTotal
    # exceeds 50% of the relevant side at SHIPMENT level —
    #   • Debit Note  SubTotal > 50% of the shipment's PURCHASE  → return (DN qty)
    #   • Credit Note SubTotal > 50% of the shipment's SALES     → return (CN qty)
    # otherwise the note is a value/price adjustment, not a return → qty 0.
    if "CFSO_Number" in d.columns:
        _grp       = d["CFSO_Number"].astype(str)
        _pur_ship  = Q.groupby(_grp).transform("sum").fillna(Q)
        _sale_ship = AX.groupby(_grp).transform("sum").fillna(AX)
    else:
        _pur_ship, _sale_ship = Q, AX
    _pur_half  = 0.5 * _pur_ship      # DN threshold (vs purchase)
    _sale_half = 0.5 * _sale_ship     # CN threshold (vs sales)

    R   = (pd.Series(np.where(dn1_sub > _pur_half, dn1_qty, 0.0), index=d.index)
           + pd.Series(np.where(dn2_sub > _pur_half, dn2_qty, 0.0), index=d.index))   # Return Qty (purchase)
    S   = O - R                                     # Net Qty (purchase)

    # AD  Cost/Kg = IFERROR((Q+AB)/S, 0) — 0 if Net Qty <= 0
    AD  = _safe_div(Q + AB, S, positive_only=True)

    # AK  Actual Debit Note = the actual vendor DN credit (reduces cost).
    #     Equals Actual DN (BZ), capped above for full reversals.
    AK  = BZ

    # AM  Total Cost = Purchase + Logistics + Diversion + Full DN + Custom
    #     − Actual DN (AK) − Provision DN (AL).  Both the actual and the
    #     provisioned vendor DN REDUCE cost (the manual stores them negative).
    AM  = Q + AB + AJ + T + AE - AK - AL

    # AZ  Return Qty (sales) — CN SubTotal > 50% of the shipment's SALES
    AZ  = (pd.Series(np.where(cn1_sub > _sale_half, cn1_qty, 0.0), index=d.index)
           + pd.Series(np.where(cn2_sub > _sale_half, cn2_qty, 0.0), index=d.index))

    # BA  Net Qty (sales) = AV - AZ
    BA  = AV - AZ

    # AY  Qty Check
    AY  = (AV == O)

    # BL  Actual Credit Note = the actual credit-note value on the row
    #     (same as Actaul CN / BY — distinct-note SubTotal, no double-count)
    BL  = BY

    # BN  Net Revenue = Sale Amount − Credit Notes (actual BL + provision BM) + others
    BN  = AX + BK + BB + BF - BL - BM

    # BO  Margin = BN - AM
    BO  = BN - AM

    # BP  Reamrks - Margin
    BP  = np.where(BO >= 0, "Positive Margin", "Negative Margin")

    # BR  LMI @ Inception = AX - Y - Q - AA - T + BB
    BR  = AX - Y - Q - AA - T + BB

    # BS  Remarks @ Inception
    BS  = np.where(BR < 0, "Negative Margin at Inception", "Positive Margin at Inception")

    # BT  Margin (%) = IFERROR(BO / BN, 0)
    BT  = _safe_div(BO, BN)

    # BU  Margin Bucket
    def _bucket(p):
        if pd.isna(p): return ""
        if   p <  0.01: return "Less Than 1%"
        elif p <= 0.02: return "1% - 2%"
        else:           return "More than 2%"
    BU  = pd.Series(BT).apply(_bucket)

    # BV  Total CN(Inc.Provisions) = BL + BM
    BV  = BL + BM

    # BW  Total DN(Inc.Provisions) = AL + AK
    BW  = AL + AK

    # BX  Check = BV - BW
    BX  = BV - BW

    # CA  Check = BY - BZ
    CA  = BY - BZ

    # CD  Month (mmm-yy) = TEXT(Inv.Date, "mmm-yy")
    CD  = inv_date.dt.strftime("%b-%y").fillna("")

    # CE  Cost = AM - AL - AA
    CE  = AM - AL - AA

    # CF  Revenue = BN - BM
    CF  = BN - BM

    # CG  Week No: = fiscal year week
    CG  = _fiscal_week(_s(d, "Invoice_Date", ""))

    # CK  Gross Margin = AX - Q
    CK  = AX - Q

    # CL  Recykal Margin = CK - Y + Z
    CL  = CK - Y + Z

    # CM  Net Margin = BN - AM  (same as BO)
    CM  = BN - AM

    # Financials with GST
    # CN col  Sales       = AX * 118%
    Sales_gst = AX * 1.18
    # CO      Purchases   = -(Q * 118%)  [cost, negative]
    Purch_gst = -(Q * 1.18)
    # CP      Credit Note = -(BY * 118%) [reduces revenue, negative]
    CN_gst    = -(BY * 1.18)
    # CQ      Debit Note  = BZ * 118%   [vendor recovery, positive]
    DN_gst    = BZ * 1.18
    # CR      Margin      = SUM(CN:CQ)
    Margin_gst = Sales_gst + Purch_gst + CN_gst + DN_gst

    # ── Remarks — verified, deterministic per-shipment classification ─────────
    # First matching rule wins (priority top→bottom):
    #   Finance Up Charge  : non-material charge line (blank Shipment ID)
    #   Divertion          : resell case (a resold shipment)
    #   Full Rejection     : shipment fully reversed (Actual CN ≥ 95% of sale)
    #   DN & CN Issued     : shipment has BOTH an actual DN and an actual CN
    #   DN & CN Provision  : shipment has BOTH a DN provision and a CN provision
    #   No Debit Note      : shipment has no actual DN
    #   (blank)            : none of the above (e.g. DN present but no CN/provision)
    def _ship_sum(S):
        return pd.to_numeric(S, errors="coerce").fillna(0).abs().groupby(_ship_key).transform("sum")
    _adn = _ship_sum(BZ) > 1          # actual DN present on the shipment
    _acn = _ship_sum(BY) > 1          # actual CN present
    _pdn = _ship_sum(AL) > 1          # DN provision taken
    _pcn = _ship_sum(BM) > 1          # CN provision taken
    _blank_ship = _ship_key.str.lower().isin(["", "nan", "none", "nat"])
    _resell = _resale_note.astype(str).str.strip().ne("")
    _remarks = pd.Series(np.select(
        [_blank_ship, _resell, _full_rev, _adn & _acn, _pdn & _pcn, ~_adn],
        ["Finance Up Charge", "Divertion", "Full Rejection",
         "DN & CN Issued", "DN & CN Provision", "No Debit Note"],
        default=""), index=d.index)

    # ── Build output with EXACT column names in report order ──────────────────
    # Duplicate column names handled via list of (name, series) pairs
    cols = [
        # Raw Data
        ("Quarter",                  _fiscal_quarter(_s(d, "Invoice_Date", ""))),
        ("Month",                    inv_date.dt.strftime("%b-%y").fillna("")),
        ("Date",                     _dt_str(_s(d, "Invoice_Date", ""))),
        ("Shipment ID",              _s(d, "CFSO_Number", "")),

        # Purchase Details
        ("Supplier Name",            _s(d, "Vendor_Name", "")),
        ("GST Reg No.",              _s(d, "GST_Identification_Number_GSTIN_bill", "")),
        ("Vendor Invoice No.",       _s(d, "Bill_Number", "")),
        ("Vendor Invoice Date",      _dt_str(_s(d, "CFSupplier_Invoice_Date", ""))),
        ("P V No.",                  _s(d, "CFPurchase", "")),
        ("P V Date",                 _dt_str(_s(d, "CFVoucher_Date", ""))),
        ("State (Origin)",           _s(d, "Source_of_Supply", "")),
        ("Vehicle No.",              _s(d, "CFVehicle_No_bill", "")),
        ("Material",                 _s(d, "Item_Name", "")),
        ("Qty (Kg)",                 O),
        ("Price/Kg",                 P),
        ("Purchase Price",           Q),
        ("Return Qty",               R),
        ("Net Qty",                  S),
        ("Basic Customs Duty",       T),

        # Logistics
        ("Transporter Name",         _s(d, "_log_vendor", "")),
        ("LR NO/BILL NO",            _s(d, "_log_bill_no", "")),
        ("J V No.",                  _s(d, "_log_jv", "")),
        ("JV Date",                  _dt_str(_s(d, "_log_jv_date", ""))),
        ("Logistics cost",           Y),
        ("Debit note on logistic cost", Z),
        ("Logistics Provision",      AA),
        ("Total Logistics Cost",     AB),
        ("Operational Cost",         AC),
        ("Cost/Kg.",                 pd.Series(AD, index=d.index)),
        ("Divertion/Internal",       AE),   # purchase side

        # Debit Notes to Suppliers
        ("Debit Note No.",           _s(d, "DN_1_Vendor_Credit_Number", "")),
        ("Debit Note Date.",         _dt_str(_s(d, "DN_1_Vendor_Credit_Date", ""))),
        ("Debit Note No. 2",         _s(d, "DN_2_Vendor_Credit_Number", "")),
        ("Debit Note Date. 2",       _dt_str(_s(d, "DN_2_Vendor_Credit_Date", ""))),
        ("Full Debit Note",          AJ),
        ("Actual Debit Note",        AK),
        ("Provision for DN",         AL),
        ("Total Cost",               AM),

        # Sales Details
        ("Inv. Date",                _dt_str(inv_date)),
        ("Inv. No.",                 _s(d, "Invoice_Number", "")),
        ("Customer ID",              _s(d, "Customer_ID", "")),
        ("Buyer Name",               _s(d, "Customer_Name", "")),
        ("Buyer GST Number ",        _s(d, "GST_Identification_Number_GSTIN_inv", "")),
        ("Location (Origin)",        _s(d, "CFDispatch_From", "")),
        ("Location (Destination)",   _s(d, "Shipping_City", "")),
        ("State (Destination)",      _s(d, "Shipping_State", "")),
        ("Qty(Kg)",                  AV),
        ("Rate/Kg",                  AW),
        ("Amount",                   AX),
        ("Qty Check",                AY),
        ("Return Qty",               AZ),   # sales return qty — same name as purchase Return Qty
        ("Net Qty",                  BA),   # sales net qty — same name as purchase Net Qty
        ("Divertion/Internal",       BB),   # sales side — same name as purchase Divertion

        # DN to Customer
        ("Return Type",              pd.Series("", index=d.index)),
        ("Date : DN to Buyer",       pd.Series("", index=d.index)),
        ("DN to Buyer",              pd.Series("", index=d.index)),
        ("Amount",                   BF),   # DN amount — same name as sales Amount

        # Credit Notes from Customers
        ("Credit Note No:1",         _s(d, "CN_1_Credit_Note_Number", "")),
        ("CN Date. No:1",            _dt_str(_s(d, "CN_1_Credit_Note_Date", ""))),
        ("Credit Note No:2",         _s(d, "CN_2_Credit_Note_Number", "")),
        ("CN Date. No:2",            _dt_str(_s(d, "CN_2_Credit_Note_Date", ""))),
        ("Full Credit Notes",        BK),
        ("Actual Credit Note",       BL),
        ("Provision for CN",         BM),

        # Without Provisions
        ("Net Revenue",              BN),
        ("Margin",                   BO),
        ("Reamrks - Margin",         pd.Series(BP, index=d.index)),
        ("Remarks",                  _remarks),
        ("LMI @ Inception",          BR),
        ("Remarks @ Inception",      pd.Series(BS, index=d.index)),
        ("Margin (%)",               pd.Series(BT, index=d.index)),
        ("Margin Bucket",            BU),

        # CN & DN Checks
        ("Total CN(Inc.Provisions)", BV),
        ("Total DN(Inc.Provisions)", BW),
        ("Check",                    BX),
        ("Actaul CN",                BY),
        ("Actual DN",                BZ),
        ("Check",                    CA),   # second Check column

        # Margin Buckets / Derived
        ("Material-Short Form",      pd.Series("", index=d.index)),
        ("Supplier Type",            pd.Series("", index=d.index)),
        ("Month",                    CD),   # second Month column — mmm-yy format
        ("Cost",                     CE),
        ("Revenue",                  CF),
        ("Week No:",                 CG),
        ("Category (Material)",      pd.Series("", index=d.index)),
        ("Broad Category",           _s(d, "Account_inv", "").str.extract(r'\((.+?)\)', expand=False).fillna("")),
        ("POC Name",                 pd.Series("", index=d.index)),
        ("Gross Margin",             CK),
        ("Recykal Margin",           CL),
        ("Net Margin",               CM),

        # Financials with GST
        ("Sales ",                   Sales_gst),
        ("Purchases",                Purch_gst),
        ("Credit Note",              CN_gst),
        ("Debit Note",               DN_gst),
        ("Margin",                   Margin_gst),   # third Margin column
        ("Bill Branch",              _s(d, "Branch_Name", "")),
        ("Inv Branch",               _s(d, "Account_inv", "")),
        ("Vendor PAN No",            _s(d, "GST_Identification_Number_GSTIN_bill", "")),
        ("Customer PAN No",          _s(d, "GST_Identification_Number_GSTIN_inv", "")),
        ("GST TDS Applicability",    pd.Series("", index=d.index)),
        ("Cash Discount(Provision)", pd.Series(0.0, index=d.index)),
        ("Cash Discount",            pd.Series(0.0, index=d.index)),
        ("Cash Discount. No",        pd.Series("", index=d.index)),
        ("CD Date",                  pd.Series("", index=d.index)),
        ("SD",                       pd.Series("", index=d.index)),
        # provenance of the cost on each row (where the purchase cost came from)
        ("Cost Source",              _s(d, "_cost_source", "")),
        # resold-item flag (End Generator return-to-seller → re-purchase → resale)
        ("Resale Note",              _resale_note),
    ]

    # Assemble — use concat to support duplicate column names
    out = pd.concat(
        [pd.Series(series, name=name).reset_index(drop=True) for name, series in cols],
        axis=1
    )
    out.columns = [name for name, _ in cols]

    # ── Non-material charge lines (no provision) ──────────────────────────────
    # Hydra charges, Finance Up-Charge, etc. have NO Shipment ID — they're service/
    # finance charges, not material trades. They stay in their vertical's totals
    # (the manual includes them in Net Revenue), but they take NO CN/DN provision
    # (already enforced in _prov_trig). Annotate them here for transparency.
    if "Shipment ID" in out.columns and "Resale Note" in out.columns:
        _chg = out["Shipment ID"].astype(str).str.strip().isin(["", "nan", "None", "NaT"])
        _empty_note = out["Resale Note"].astype(str).str.strip().isin(["", "nan", "None"])
        out.loc[_chg & _empty_note, "Resale Note"] = "Non-material charge (e.g. Finance Up-Charge / Hydra) — no CN/DN provision applied"

    # ── Chronological order ───────────────────────────────────────────────────
    # Orphan bills (appended after the invoice rows by the cleaning stage) carry
    # their Bill Date in "Date" — a stable date sort interleaves them into the
    # details instead of leaving them stacked at the bottom. Same-date rows keep
    # their original order; undated rows stay at the end.
    if "Date" in out.columns:
        # ISO first, dayfirst only for the leftovers — dayfirst over an ISO
        # date silently swaps day/month when the day is ≤ 12
        _d = pd.to_datetime(out["Date"].astype(object), errors="coerce", format="ISO8601")
        _miss = _d.isna()
        if _miss.any():
            _d.loc[_miss] = pd.to_datetime(out["Date"].astype(object)[_miss],
                                           errors="coerce", dayfirst=True, format="mixed")
        _order = pd.concat([_d[_d.notna()].sort_values(kind="stable"),
                            _d[_d.isna()]]).index
        out = out.loc[_order].reset_index(drop=True)

    # ── Fake-DN shipments ─────────────────────────────────────────────────────
    # Keep them in their invoice month, but move them out of the vertical totals
    # into the "Fake DN (Excluded)" bucket, flag the reason, and push to the bottom.
    if FAKE_DN_SHIPMENTS and "Shipment ID" in out.columns:
        _fd = out["Shipment ID"].astype(str).str.strip().isin(FAKE_DN_SHIPMENTS)
        if _fd.any():
            out.loc[_fd, "Broad Category"] = FAKE_DN_CATEGORY
            if "Resale Note" in out.columns:
                out.loc[_fd, "Resale Note"] = "Fake DN raised against this shipment — excluded from vertical totals"
            out = pd.concat([out[~_fd], out[_fd]], ignore_index=True)
    return out
