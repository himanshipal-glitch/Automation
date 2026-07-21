"""
Data cleaning rules per sheet.
Each function takes a raw DataFrame and returns (cleaned_df, stats_dict).
Column names are sanitized on DB write (spaces → underscores).
"""

import pandas as pd

# Re-Commerce costing cutover: the signed-off report up to this date is stored/
# frozen; MIS rows dated AFTER it are costed by the Amazon-invoice chain ONLY
# (the older-bill-by-shipment fallback is not applied to them).
RECOMMERCE_AMAZON_ONLY_AFTER = pd.Timestamp("2026-07-17")


def _col(df: pd.DataFrame, *candidates: str) -> str | None:
    """Return the first candidate column name found in df (raw or sanitized)."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


# ── Bill ─────────────────────────────────────────────────────────────────────
def clean_bill(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Keep rows where:
      - Account contains 'Marketplace Purchases' OR 'Marketplace Logistics'
      - Bill Status NOT IN ('Void', 'Draft')
    (Branch filter removed — bills from all branches are kept.)
    """
    original = len(df)
    stats = {"original_rows": original}

    account_col  = _col(df, "Account")
    status_col   = _col(df, "Bill_Status", "Bill Status")

    # 2. Account filter
    if account_col:
        mask = df[account_col].str.contains(
            "Marketplace Purchases|Marketplace Logistics", case=False, na=False
        )
        stats["dropped_wrong_account"] = int((~mask).sum())
        df = df[mask].copy()
    else:
        stats["dropped_wrong_account"] = 0

    # 3. Status filter — remove Void / Draft
    if status_col:
        mask = ~df[status_col].str.strip().str.lower().isin(["void", "draft"])
        stats["dropped_void_draft"] = int((~mask).sum())
        df = df[mask].copy()
    else:
        stats["dropped_void_draft"] = 0

    stats["final_rows"] = len(df)
    return df.reset_index(drop=True), stats


# ── Invoice ───────────────────────────────────────────────────────────────────
def clean_invoice(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Keep rows where:
      - Account contains 'Marketplace Sales' OR 'Marketplace Logistics'
      - Invoice Status NOT IN ('Void', 'Draft')
    (Branch filter removed — invoices from all branches are kept.)
    """
    original = len(df)
    stats = {"original_rows": original}

    account_col = _col(df, "Account")
    status_col  = _col(df, "Invoice_Status", "Invoice Status")

    # 2. Account filter
    if account_col:
        mask = df[account_col].str.contains(
            "Marketplace Sales|Marketplace Logistics", case=False, na=False
        )
        stats["dropped_wrong_account"] = int((~mask).sum())
        df = df[mask].copy()
    else:
        stats["dropped_wrong_account"] = "column absent"

    # 3. Status filter — remove Void / Draft
    if status_col:
        mask = ~df[status_col].str.strip().str.lower().isin(["void", "draft"])
        stats["dropped_void_draft"] = int((~mask).sum())
        df = df[mask].copy()
    else:
        stats["dropped_void_draft"] = 0

    stats["final_rows"] = len(df)
    return df.reset_index(drop=True), stats


# ── Bill Split ────────────────────────────────────────────────────────────────
def split_bill(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Split cleaned Bill into two sub-tables:
      - bill_purchases : Account contains 'Marketplace Purchases'
      - bill_logistics : Account contains 'Marketplace Logistics'
    Returns (purchases_df, logistics_df, stats)
    """
    account_col = _col(df, "Account")
    purchases = df[df[account_col].str.contains("Marketplace Purchases", case=False, na=False)].copy().reset_index(drop=True)
    logistics = df[df[account_col].str.contains("Marketplace Logistics", case=False, na=False)].copy().reset_index(drop=True)
    stats = {
        "total_rows": len(df),
        "purchases_rows": len(purchases),
        "logistics_rows": len(logistics),
        "purchases_accounts": purchases[account_col].unique().tolist(),
        "logistics_accounts": logistics[account_col].unique().tolist() if len(logistics) else [],
    }
    return purchases, logistics, stats


# ── Invoice + Bill Merge ───────────────────────────────────────────────────────
def _aggregate_bill_rows(rows: pd.DataFrame) -> dict:
    """Collapse several bill lines into one: sum qty/amounts, weighted-avg rate."""
    out = rows.iloc[0].to_dict()
    for c in ("Quantity", "Item_Total", "SubTotal"):
        if c in rows.columns:
            out[c] = rows[c].sum()
    if "Rate" in rows.columns:
        qty = out.get("Quantity", 0)
        total = out.get("Item_Total", rows["Rate"].mul(rows.get("Quantity", 1)).sum())
        out["Rate"] = (total / qty) if qty else rows["Rate"].mean()
    return out


import re as _re

# Amazon-style sellers (preferred when picking a supplier for historical cost)
_AMAZON_VENDORS = "clicktech|amazon|appario|cloudtail"


_SERVICE_ITEM = _re.compile(
    r"\b(charges?|penalty|penalties|fees?|services?|manpower|degauss\w*|"
    r"labou?r|freight|commission|handling)\b", _re.I)


def _is_service_item(name) -> bool:
    """True if a bill item is a service/penalty charge (not a physical material)."""
    return bool(_SERVICE_ITEM.search(str(name)))


def _norm_item(s) -> str:
    """
    Normalise a material name for matching: lowercase, collapse internal
    whitespace, strip surrounding spaces and trailing punctuation. So
    'HMD  Smartphones ', 'hmd smartphones' and 'HMD Smartphones.' all match.
    """
    s = str(s).strip().lower()
    s = _re.sub(r"\s+", " ", s)
    s = s.strip(" .,-_/")
    return s


def build_price_book(history_bill_df: pd.DataFrame) -> dict:
    """
    Build a Re-Commerce material → {cost, supplier} map from the OLDER bills
    file (the 7th upload). Used to cost shipments whose bill is missing from
    the current bill file.

    Filters applied (per the Re-Commerce rule):
      - Account contains 'Marketplace' AND '(Re-Commerce)'
      - CF.SO Number starts with 'MP/REC'
    For each Item Name:
      cost     = Σ Item_Total / Σ Quantity   (weighted average)
      supplier = a vendor that sold this material in the older bills,
                 Amazon-style sellers prioritised, else the most frequent vendor
    """
    if history_bill_df is None or history_bill_df.empty:
        return {}
    df = history_bill_df.copy()
    acc  = _col(df, "Account")
    so   = _col(df, "CFSO_Number", "CF.SO Number")
    item = _col(df, "Item_Name", "Item Name")
    qty  = _col(df, "Quantity")
    tot  = _col(df, "Item_Total", "Item Total")
    ven  = _col(df, "Vendor_Name", "Vendor Name")
    if not all([acc, so, item, qty, tot]):
        return {}

    m = (df[acc].astype(str).str.contains("Marketplace", case=False, na=False) &
         df[acc].astype(str).str.contains("Re-Commerce", case=False, na=False) &
         df[so].astype(str).str.strip().str.upper().str.startswith("MP/REC"))
    df = df[m]
    if df.empty:
        return {}

    df[qty] = pd.to_numeric(df[qty], errors="coerce").fillna(0)
    df[tot] = pd.to_numeric(df[tot], errors="coerce").fillna(0)
    df["_item_norm"] = df[item].apply(_norm_item)      # normalised match key
    df["_item_disp"] = df[item].astype(str).str.strip()

    # supplier-side detail columns to carry over from the older bills
    detail_cols = [c for c in [
        "GST_Identification_Number_GSTIN", "Bill_Number", "CFSupplier_Invoice_Date",
        "CFPurchase", "CFVoucher_Date", "Source_of_Supply", "CFVehicle_No",
        "Branch_Name", "Account",
    ] if c in df.columns]
    bd = _col(df, "Bill_Date")

    book = {}
    for key, g in df.groupby("_item_norm"):
        if not key:
            continue
        tq = g[qty].sum()
        if tq <= 0:
            continue
        cost = round(g[tot].sum() / tq, 4)              # weighted-avg cost (unchanged)
        supplier = ""
        rep = g
        if ven:
            vendors = g[ven].astype(str)
            amazon = vendors[vendors.str.contains(_AMAZON_VENDORS, case=False, na=False)]
            pool = amazon if len(amazon) else vendors
            pool = pool[pool.str.strip() != ""]
            if len(pool):
                supplier = pool.value_counts().index[0]
                sub = g[g[ven].astype(str) == supplier]
                if len(sub):
                    rep = sub                            # representative = chosen supplier's lines
        # most recent line (by Bill Date) for the supplier-side metadata
        if bd:
            rep = rep.sort_values(bd)
        rep_row = rep.iloc[-1]
        details = {c: rep_row[c] for c in detail_cols}

        book[key] = {"cost": cost, "supplier": supplier,
                     "display": g["_item_disp"].iloc[0], "details": details}
    return book


def price_book_table(book: dict) -> pd.DataFrame:
    """Return the price-book as a viewable inventory table."""
    if not book:
        return pd.DataFrame(columns=["Material", "Avg_Unit_Cost_History", "Supplier_History"])
    return (pd.DataFrame([{"Material": v.get("display", k),
                           "Avg_Unit_Cost_History": v["cost"],
                           "Supplier_History": v.get("supplier", "")}
                          for k, v in book.items()])
            .sort_values("Material").reset_index(drop=True))


def build_amazon_invoice_map(ytd_df: pd.DataFrame) -> dict:
    """
    From the Amazon × Recykal YTD sheet, map each Recykal invoice number
    (column 'Invoice ID') → set of Amazon invoice numbers (column 'Invoice no.').
    The Amazon invoice numbers equal the older bills' 'Bill Number'.
    """
    if ytd_df is None or ytd_df.empty:
        return {}
    inv_id = _col(ytd_df, "Invoice_ID", "Invoice ID")
    inv_no = _col(ytd_df, "Invoice_no", "Invoice no.", "Invoice_no.")
    if not inv_id or not inv_no:
        return {}
    from collections import defaultdict
    ids = ytd_df[inv_id].astype(str).str.strip()
    nos = ytd_df[inv_no].astype(str).str.strip()
    m: dict = defaultdict(set)
    for iid, ino in zip(ids.tolist(), nos.tolist()):
        iid = str(iid).strip(); ino = str(ino).strip()
        if iid and iid.lower() != "nan" and ino and ino.lower() != "nan":
            m[iid].add(ino)
    return dict(m)


def _history_billno_index(history_df: pd.DataFrame) -> dict:
    """
    Index older Re-Commerce bill lines by (Bill_Number, normalised item) for the
    Amazon-invoice chain. Bill_Number == Amazon 'Invoice no.'.
    """
    from collections import defaultdict
    idx: dict = defaultdict(list)
    if history_df is None or history_df.empty:
        return idx
    df = history_df.copy()
    acc = _col(df, "Account"); bn = _col(df, "Bill_Number", "Bill Number")
    item = _col(df, "Item_Name", "Item Name"); qty = _col(df, "Quantity")
    tot = _col(df, "Item_Total", "Item Total")
    if not all([acc, bn, item, qty, tot]):
        return idx
    m = (df[acc].astype(str).str.contains("Marketplace", case=False, na=False) &
         df[acc].astype(str).str.contains("Re-Commerce", case=False, na=False))
    df = df[m]
    df[qty] = pd.to_numeric(df[qty], errors="coerce").fillna(0)
    df[tot] = pd.to_numeric(df[tot], errors="coerce").fillna(0)
    detail_cols = [c for c in [
        "Vendor_Name", "GST_Identification_Number_GSTIN", "Bill_Number",
        "CFSupplier_Invoice_Date", "CFPurchase", "CFVoucher_Date",
        "Source_of_Supply", "CFVehicle_No", "Branch_Name", "Account",
    ] if c in df.columns]
    for ridx, r in df.iterrows():
        key = (str(r[bn]).strip(), _norm_item(r[item]))
        idx[key].append({"_uid": f"amz{ridx}", "qty": float(r[qty]),
                         "cost": float(r[tot]),
                         "details": {c: r[c] for c in detail_cols}})
    return idx


def _recommerce_history_index(history_df: pd.DataFrame) -> dict:
    """
    Index actual older Re-Commerce bill lines by (shipment_id, normalised item).
    Each entry is a list of line dicts: qty, cost (Item_Total), and supplier-side
    detail fields. Used to cost missing-bill rows from the REAL purchase lines.
    """
    from collections import defaultdict
    idx: dict = defaultdict(list)
    if history_df is None or history_df.empty:
        return idx
    df = history_df.copy()
    acc = _col(df, "Account"); so = _col(df, "CFSO_Number", "CF.SO Number")
    item = _col(df, "Item_Name", "Item Name"); qty = _col(df, "Quantity")
    tot = _col(df, "Item_Total", "Item Total")
    if not all([acc, so, item, qty, tot]):
        return idx
    m = (df[acc].astype(str).str.contains("Marketplace", case=False, na=False) &
         df[acc].astype(str).str.contains("Re-Commerce", case=False, na=False) &
         df[so].astype(str).str.strip().str.upper().str.startswith("MP/REC"))
    df = df[m]
    if df.empty:
        return idx
    df[qty] = pd.to_numeric(df[qty], errors="coerce").fillna(0)
    df[tot] = pd.to_numeric(df[tot], errors="coerce").fillna(0)
    detail_cols = [c for c in [
        "Vendor_Name", "GST_Identification_Number_GSTIN", "Bill_Number",
        "CFSupplier_Invoice_Date", "CFPurchase", "CFVoucher_Date",
        "Source_of_Supply", "CFVehicle_No", "Branch_Name", "Account",
    ] if c in df.columns]
    for ridx, r in df.iterrows():
        key = (str(r[so]).strip(), _norm_item(r[item]))
        idx[key].append({
            "_uid": ridx,
            "qty": float(r[qty]),
            "cost": float(r[tot]),
            "details": {c: r[c] for c in detail_cols},
        })
    return idx


def merge_invoice_bill(inv_df: pd.DataFrame, bill_df: pd.DataFrame,
                       history_df: pd.DataFrame | None = None,
                       amazon_map: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """
    Pair Invoice lines with Bill purchase lines per CFSO_Number + Item_Name.

    Matching logic per shipment + material:
      - 1 invoice line                 : all bill lines aggregated onto it
                                         (sum qty & amount, weighted-avg rate)
      - multiple invoice lines         : each line is matched to the bill line
                                         with the SAME quantity (each bill line
                                         used once) so every row's amount =
                                         its own qty × its own rate.
        Leftover bill lines are aggregated and placed on the remaining
        unmatched invoice lines (split by qty share), or — if every invoice
        line already matched — added onto the largest line so no cost is lost.
    """
    join_keys = ["CFSO_Number", "Item_Name"]

    missing_inv  = [k for k in join_keys if k not in inv_df.columns]
    missing_bill = [k for k in join_keys if k not in bill_df.columns]
    if missing_inv or missing_bill:
        raise ValueError(f"Missing join keys — Inv: {missing_inv}, Bill: {missing_bill}")

    inv  = inv_df.reset_index(drop=True)
    bill = bill_df.reset_index(drop=True)
    bill_cols = [c for c in bill.columns if c not in join_keys]

    # Index bill lines by (single shipment id, item) for fast lookup
    from collections import defaultdict
    bill_index: dict[tuple, list[int]] = defaultdict(list)
    for i, (s, it) in enumerate(zip(bill["CFSO_Number"].astype(str).str.strip(),
                                    bill["Item_Name"].astype(str).str.strip())):
        bill_index[(s, it)].append(i)

    bill_used: set[int] = set()
    assigned: list[dict | None] = [None] * len(inv)
    cost_source: list[str] = [""] * len(inv)   # per-row provenance of the cost
    op_cost_col: list[float] = [0.0] * len(inv)  # operational cost (service orphans)

    # Group invoice lines by (raw shipment string, item).
    # A multi-source invoice carries a comma list of shipment IDs
    # ("MP/X, MP/Y, MP/Z") — split it and pull candidate bill lines from
    # ALL listed shipments. Single-shipment groups are processed FIRST so
    # they claim their own bills before multi-shipment groups take leftovers.
    ship_key = inv["CFSO_Number"].astype(str).str.strip()
    item_key = inv["Item_Name"].astype(str).str.strip()
    groups = sorted(inv.groupby([ship_key, item_key]).groups.items(),
                    key=lambda kv: kv[0][0].count(","))

    for (ship_str, item), inv_pos_idx in groups:
        ships = [s.strip() for s in ship_str.split(",") if s.strip()]
        cand = [i for s in ships for i in bill_index.get((s, item), [])
                if i not in bill_used]
        if not cand:
            continue
        inv_pos = list(inv_pos_idx)
        ig = inv.loc[inv_pos]

        if len(inv_pos) == 1:
            # single invoice line — aggregate all candidate bill lines onto it
            assigned[inv_pos[0]] = _aggregate_bill_rows(bill.loc[cand])
            bill_used.update(cand)
            continue

        # multiple invoice lines — pair each with a bill line of SAME quantity
        used_local: set[int] = set()
        unmatched_inv = []
        for pos in inv_pos:
            inv_qty = ig.at[pos, "Quantity"] if "Quantity" in ig.columns else None
            hit = None
            if inv_qty is not None and "Quantity" in bill.columns:
                for bi in cand:
                    if bi not in used_local and abs(float(bill.at[bi, "Quantity"]) - float(inv_qty)) < 1e-6:
                        hit = bi
                        break
            if hit is not None:
                used_local.add(hit)
                assigned[pos] = bill.loc[hit].to_dict()
            else:
                unmatched_inv.append(pos)

        leftover_ids = [i for i in cand if i not in used_local]
        bill_used.update(used_local)
        if not leftover_ids:
            continue
        leftover = bill.loc[leftover_ids]

        if unmatched_inv:
            # split leftover bill cost across unmatched invoice lines by qty share
            agg = _aggregate_bill_rows(leftover)
            qts = [float(ig.at[p, "Quantity"]) if "Quantity" in ig.columns else 1.0
                   for p in unmatched_inv]
            total_q = sum(qts) or len(unmatched_inv)
            for p, q in zip(unmatched_inv, qts):
                share = q / total_q
                row = dict(agg)
                for c in ("Quantity", "Item_Total", "SubTotal"):
                    if c in row and pd.notna(row[c]):
                        row[c] = row[c] * share
                assigned[p] = row
        else:
            # every invoice line matched — add leftover onto the largest line
            big = max(inv_pos, key=lambda p: float(ig.at[p, "Quantity"]) if "Quantity" in ig.columns else 0)
            combined = pd.concat([pd.DataFrame([assigned[big]]), leftover], ignore_index=True)
            assigned[big] = _aggregate_bill_rows(combined)
        bill_used.update(leftover_ids)

    # current-bill matches get tagged
    for pos in range(len(inv)):
        if assigned[pos] is not None:
            cost_source[pos] = "Current Bill"

    # ── Missing-bill cost (Re-Commerce) — layered, most precise first ─────────
    #   1. AMAZON-INVOICE CHAIN: invoice no → Amazon×Recykal YTD 'Invoice ID' →
    #      Amazon 'Invoice no.' set → older bills (Bill Number + material) →
    #      actual line cost + GSTIN. The exact purchase for that sale.
    #   2. OLDER BILL (SHIPMENT): pool actual older-bill lines across the combo's
    #      shipment ids, cover sold qty.
    #   3. WEIGHTED AVG: material-only average from the older bills.
    #   4. NO COST FOUND.
    # Always ONE row per invoice line — revenue (from the invoice) untouched.
    hist_filled = 0
    hist_idx   = _recommerce_history_index(history_df)
    amz_idx    = _history_billno_index(history_df)
    amazon_map = amazon_map or {}
    consumed: set = set()
    acc_col  = _col(inv, "Account")
    invno_col = _col(inv, "Invoice_Number", "Invoice Number")
    item_col = "Item_Name"

    def _take_lines(line_list, q):
        """Take lines (use-once) covering qty q; return (cost, first_details)."""
        cost = 0.0; got = 0.0; det = None
        for line in line_list:
            if got >= q:
                break
            if line["_uid"] in consumed:
                continue
            need = q - got
            if line["qty"] <= need + 1e-9:
                cost += line["cost"]; got += line["qty"]
            else:
                cost += line["cost"] * (need / line["qty"] if line["qty"] else 0); got += need
            consumed.add(line["_uid"])
            if det is None:
                det = line["details"]
        return cost, det

    def _make_row(cost, det, q):
        row = {c: None for c in bill_cols}
        if "Quantity" in row:   row["Quantity"]   = q
        if "Item_Total" in row: row["Item_Total"] = round(cost, 2)
        if "SubTotal" in row:   row["SubTotal"]   = round(cost, 2)
        if "Rate" in row:       row["Rate"]       = round(cost / q, 4) if q else 0
        for c, val in (det or {}).items():
            if c in row:
                row[c] = val
        return row

    for pos in range(len(inv)):
        if assigned[pos] is not None:
            continue
        acc = str(inv.at[pos, acc_col]) if acc_col else ""
        if "re-commerce" not in acc.lower():
            cost_source[pos] = ""
            continue
        nm = _norm_item(inv.at[pos, item_col])
        q = float(inv.at[pos, "Quantity"]) if "Quantity" in inv.columns and pd.notna(inv.at[pos, "Quantity"]) else 0.0
        ships = [s.strip() for s in str(inv.at[pos, "CFSO_Number"]).split(",") if s.strip()]

        # 1. Amazon-invoice chain
        inv_no = str(inv.at[pos, invno_col]).strip() if invno_col else ""
        amz_bills = amazon_map.get(inv_no, set())
        if amz_bills:
            lines = [ln for b in amz_bills for ln in amz_idx.get((b, nm), [])]
            cost, det = _take_lines(lines, q)
            if cost > 0:
                assigned[pos] = _make_row(cost, det, q)
                cost_source[pos] = "Amazon Invoice Chain"
                hist_filled += 1
                continue

        # 2. Older bill by shipment id(s) — ONLY for rows dated on/before the
        # Re-Commerce cutover (12-07-2026). The signed-off report up to that
        # date is stored/frozen; every later MIS row is costed by the
        # Amazon-invoice chain ONLY (no older-bill fallback).
        _idate = pd.to_datetime(inv.at[pos, "Invoice_Date"], errors="coerce") \
            if "Invoice_Date" in inv.columns else pd.NaT
        if pd.isna(_idate) or _idate <= RECOMMERCE_AMAZON_ONLY_AFTER:
            lines = [ln for s in ships for ln in hist_idx.get((s, nm), [])]
            cost, det = _take_lines(lines, q)
            if cost > 0:
                assigned[pos] = _make_row(cost, det, q)
                cost_source[pos] = "Older Bill (shipment)"
                hist_filled += 1
                continue

        # (Weighted-average fallback removed — we rely on the Amazon-invoice
        #  chain and exact older-bill shipment match only.)

        # 3. nothing found
        cost_source[pos] = "No Cost Found"

    # ── Orphan bills (extra bills with no matching invoice) ───────────────────
    # For verticals OTHER than Re-Commerce: an uploaded bill that matched no
    # invoice line is appended at the BOTTOM as its own row, with the invoice /
    # sales columns left blank. Its purchase cost is shown so it isn't lost.
    # (Re-Commerce missing costs are handled by its own older-bills logic;
    #  MP/warehouse orphans land in the excluded Warehouse(MP) bucket.)
    orphan_inv_rows = []
    bn_col = _col(bill, "Bill_Date", "Bill Date")
    orphans_added = 0
    # Map invoice account category tokens (space/case-insensitive) → invoice
    # account string, so an orphan bill's category matches the invoice
    # convention (e.g. bill '(ITAD)' → invoice '(IT AD)').
    inv_acc_by_token = {}
    if "Account" in inv.columns:
        for a in inv["Account"].dropna().astype(str).unique():
            mt = _re.search(r"\((.+?)\)", a)
            if mt:
                inv_acc_by_token[mt.group(1).replace(" ", "").lower()] = a
    for bi in range(len(bill)):
        if bi in bill_used:
            continue
        acc = str(bill.at[bi, "Account"]) if "Account" in bill.columns else ""
        if "re-commerce" in acc.lower():
            continue                      # RC handled separately
        if "afr" in acc.lower():
            continue                      # AFR orphan (service/processing) bills are
                                          # captured as Operational Cost from the
                                          # CFSO-blank Paid bills — NOT Purchases.
        # translate bill account → invoice convention so category tabs merge
        acc_use = acc
        mt = _re.search(r"\((.+?)\)", acc)
        if mt:
            tok = mt.group(1).replace(" ", "").lower()
            if tok in inv_acc_by_token:
                acc_use = inv_acc_by_token[tok]
        irow = {c: None for c in inv.columns}
        if "CFSO_Number" in bill.columns: irow["CFSO_Number"] = bill.at[bi, "CFSO_Number"]
        if "Item_Name"  in bill.columns:  irow["Item_Name"]  = bill.at[bi, "Item_Name"]
        if "Account" in inv.columns:      irow["Account"]    = acc_use  # → Broad Category
        if "Invoice_Date" in inv.columns and bn_col:
            irow["Invoice_Date"] = bill.at[bi, bn_col]
        orphan_inv_rows.append(irow)
        bdict = bill.loc[bi].to_dict()
        # Service/penalty charges → Operational Cost (not material Purchases).
        # EXCEPT: (a) M4 and (b) AFR have no operational cost — their charges
        # (transport, testing, manpower, etc.) are part of the purchase cost;
        # (c) "Hydra" charges are kept in Purchases too.
        # (A definitive operational-cost subheading list is TBD — this is interim.)
        _item = str(bill.at[bi, "Item_Name"]) if "Item_Name" in bill.columns else ""
        _force_purchase = ("m4" in acc.lower()) or ("hydra" in _item.lower())
        _svc = _is_service_item(_item)
        if _svc and not _force_purchase:
            op_val = float(pd.to_numeric(pd.Series([bdict.get("Item_Total", 0)]),
                                         errors="coerce").fillna(0).iloc[0])
            for c in ("Quantity", "Item_Total", "SubTotal", "Rate"):
                if c in bdict:
                    bdict[c] = 0
            assigned.append(bdict)
            cost_source.append("Orphan Bill — Operational Cost")
            op_cost_col.append(op_val)
        else:
            assigned.append(bdict)
            cost_source.append("Orphan Bill (no invoice)")
            op_cost_col.append(0.0)
        orphans_added += 1
    if orphan_inv_rows:
        inv = pd.concat([inv, pd.DataFrame(orphan_inv_rows)], ignore_index=True)

    # ── Build merged frame with pandas-style _inv/_bill suffixes ──────────────
    bill_side = pd.DataFrame(
        [{c: (a.get(c) if a else None) for c in bill_cols} for a in assigned]
    )
    overlap = [c for c in bill_cols if c in inv.columns]
    inv_ren  = inv.rename(columns={c: f"{c}_inv" for c in overlap})
    bill_ren = bill_side.rename(columns={c: f"{c}_bill" for c in overlap})
    merged = pd.concat([inv_ren, bill_ren], axis=1)
    merged["_cost_source"] = cost_source
    merged["_operational_cost"] = op_cost_col

    matched = sum(1 for a in assigned if a is not None)
    stats = {
        "invoice_rows":   len(inv),
        "bill_rows":      len(bill_df),
        "bill_rows_agg":  len(bill_index),
        "merged_rows":    len(merged),
        "matched_rows":   matched,
        "unmatched_rows": len(inv) - matched,
        "hist_filled":    hist_filled,
        "orphan_bills":   orphans_added,
        "join_keys":      join_keys,
    }
    return merged, stats


# ── CN / DN pivot helpers ─────────────────────────────────────────────────────
def run_full_pipeline(inv_df, bill_purchases_df, bill_logistics_df,
                      cn_df, dn_df,
                      history_df: pd.DataFrame | None = None,
                      amazon_map: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """
    Single-call pipeline:
      1. Merge Invoice + Bill Purchases  (on CFSO_Number + Item_Name);
         Re-Commerce rows with no current bill fall back to the historical
         price book (older bills file) for their cost.
      2. Pivot CN & DN wide (max 2 each), left-join on CFSO_Number
      3. Return (full_merged_df, pipeline_stats)
    """
    merged, s1 = merge_invoice_bill(inv_df, bill_purchases_df,
                                    history_df=history_df, amazon_map=amazon_map)
    final,  s2 = merge_cn_dn(merged, cn_df, dn_df)
    stats = {**s1, **s2,
             "logistics_rows": len(bill_logistics_df) if bill_logistics_df is not None else 0}
    return final, stats


def _pivot_to_wide(df: pd.DataFrame, ref_col: str, fields: list[str], prefix: str) -> pd.DataFrame:
    """
    For each shipment (ref_col): slot 1 = the first note (all its fields);
    slot 2 = the AGGREGATE of every remaining note (SubTotal & Quantity summed,
    other fields take the first of the rest). The VALUES sum ALL notes — no note is
    dropped — but only TWO slots are SHOWN: prefix_1_SubTotal + prefix_2_SubTotal =
    the full total across all notes (the manual sums them all, displays two).
    Protected verticals come in pre-collapsed to ONE row per shipment, so slot 2
    is empty and they are unaffected.
    Returns a wide DataFrame with one row per shipment.
    """
    _AGG = ("SubTotal", "Quantity")
    rows = []
    for ref, grp in df.groupby(ref_col, sort=False):
        grp = grp.reset_index(drop=True)
        row = {ref_col: ref}
        for f in fields:                            # slot 1 = first note, verbatim
            row[f"{prefix}_1_{f}"] = grp.at[0, f] if f in grp.columns else None
        rest = grp.iloc[1:]                          # slot 2 = aggregate of the rest
        for f in fields:
            if f in _AGG:
                row[f"{prefix}_2_{f}"] = (pd.to_numeric(rest[f], errors="coerce").fillna(0).sum()
                                          if (len(rest) and f in grp.columns) else 0)
            else:
                row[f"{prefix}_2_{f}"] = rest.iloc[0][f] if (len(rest) and f in grp.columns) else None
        rows.append(row)
    return pd.DataFrame(rows)


def _collapse_notes(df: pd.DataFrame, ref_col: str, num_col: str,
                    sub_col: str, qty_col: str) -> pd.DataFrame:
    """
    Collapse a CN/DN sheet so each note (by note number) is ONE row:
      - SubTotal : taken once  (it's the document total, repeated on each line)
      - Quantity : summed       (real per-line return quantities)
      - others   : first value
    Prevents double-counting multi-line credit/debit notes.
    """
    if df is None or df.empty or num_col not in df.columns or ref_col not in df.columns:
        return df
    df = df.copy()
    if sub_col in df.columns:
        df[sub_col] = pd.to_numeric(df[sub_col], errors="coerce").fillna(0)
    if qty_col in df.columns:
        df[qty_col] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0)
    agg = {c: "first" for c in df.columns if c not in (ref_col, num_col)}
    if sub_col in agg:
        agg[sub_col] = "first"   # document-level total → once
    if qty_col in agg:
        agg[qty_col] = "sum"     # sum the line quantities
    return df.groupby([ref_col, num_col], as_index=False, sort=False).agg(agg)


def merge_cn_dn(merged_df: pd.DataFrame,
                cn_df: pd.DataFrame,
                dn_df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Pivot CN and DN to wide format (max 2 each per shipment) then
    left-join onto the inv_bill merged table on CFSO_Number.

    CN columns added: CN_1_*, CN_2_* (if a 2nd CN exists for that shipment)
    DN columns added: DN_1_*, DN_2_* (if a 2nd DN exists for that shipment)
    Shipments with 3+ CNs or DNs: only first 2 kept, rest silently dropped.

    (De-duplication happens earlier in clean_cn / clean_dn — collapsed to one
     row per DISTINCT note number: SubTotal once, Quantity summed. Distinct
     notes on one shipment survive as CN_1/CN_2 (DN_1/DN_2) and are summed.)
    """
    cn_fields = ["Credit_Note_Number", "Credit_Note_Date", "SubTotal", "Quantity"]
    dn_fields = ["Vendor_Credit_Number", "Vendor_Credit_Date", "SubTotal", "Quantity", "Associated_Bill_Number"]

    # --- CN stats ---
    cn_counts = cn_df.groupby("Referenceno").size()
    cn_stats = {
        "cn_shipments": int(cn_counts.shape[0]),
        "cn_with_1":    int((cn_counts == 1).sum()),
        "cn_with_2":    int((cn_counts == 2).sum()),
        "cn_capped_3plus": int((cn_counts >= 3).sum()),
    }

    # --- DN stats ---
    dn_counts = dn_df.groupby("Referenceno").size()
    dn_stats = {
        "dn_shipments": int(dn_counts.shape[0]),
        "dn_with_1":    int((dn_counts == 1).sum()),
        "dn_with_2":    int((dn_counts == 2).sum()),
        "dn_capped_3plus": int((dn_counts >= 3).sum()),
    }

    cn_wide = _pivot_to_wide(cn_df, "Referenceno", cn_fields, "CN")
    dn_wide = _pivot_to_wide(dn_df, "Referenceno", dn_fields, "DN")

    result = merged_df.copy()
    result = result.merge(cn_wide, left_on="CFSO_Number", right_on="Referenceno", how="left").drop(columns=["Referenceno"], errors="ignore")
    result = result.merge(dn_wide, left_on="CFSO_Number", right_on="Referenceno", how="left").drop(columns=["Referenceno"], errors="ignore")

    # ── CN/DN belong to the SHIPMENT, not to every order line ─────────────────
    # If a shipment has multiple rows (several items/orders), keep the CN/DN
    # values only on the FIRST row — blank them on the rest, so return
    # quantities and amounts are never double-counted.
    dup_mask = result["CFSO_Number"].duplicated(keep="first")
    cn_dn_cols = [c for c in result.columns if c.startswith("CN_") or c.startswith("DN_")]
    if cn_dn_cols:
        result.loc[dup_mask, cn_dn_cols] = None

    stats = {
        "base_rows": len(merged_df),
        "final_rows": len(result),
        **cn_stats,
        **dn_stats,
    }
    return result, stats


# ── Credit Notes (CN) ─────────────────────────────────────────────────────────
def clean_cn(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Keep rows where:
      - Account starts with 'Marketplace' (basic rule — only marketplace returns)
      - Credit Note Status NOT IN ('Void', 'Pending')
    """
    original = len(df)
    stats = {"original_rows": original}

    account_col = _col(df, "Account")
    status_col  = _col(df, "Credit_Note_Status", "Credit Note Status")

    if account_col:
        mask = df[account_col].str.strip().str.lower().str.startswith("marketplace")
        stats["dropped_non_marketplace"] = int((~mask).sum())
        df = df[mask].copy()
    else:
        stats["dropped_non_marketplace"] = 0

    if status_col:
        mask = ~df[status_col].str.strip().str.lower().isin(["void", "pending"])
        stats["dropped_void_pending"] = int((~mask).sum())
        df = df[mask].copy()
    else:
        stats["dropped_void_pending"] = 0

    df, dropped = _dedup_notes_by_account(df)
    stats["dropped_extra_lines"] = dropped

    stats["final_rows"] = len(df)
    return df.reset_index(drop=True), stats


def _one_line_per_note(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Collapse a CN/DN sheet to ONE row per DISTINCT NOTE number:
      - SubTotal : taken once  (it's the document total, repeated on each line
                   of the SAME note — summing those lines would double-count)
      - Quantity : summed       (real per-line return quantities of that note)
    DISTINCT notes on the same shipment stay as SEPARATE rows, so a shipment
    with two credit/debit notes keeps both — they get pivoted to CN_1/CN_2 (or
    DN_1/DN_2) and summed downstream, exactly as the manual does. This both
    avoids the within-note SubTotal double-count AND sums genuinely separate
    notes on one shipment.
    """
    ref = _col(df, "Referenceno", "Reference#")
    num = _col(df, "Credit_Note_Number", "Vendor_Credit_Number")
    sub = _col(df, "SubTotal")
    qty = _col(df, "Quantity")
    if not ref or not num or df.empty:
        return df, 0
    before = len(df)
    out = _collapse_notes(df, ref, num, sub, qty).reset_index(drop=True)
    return out, before - len(out)


def _one_line_per_shipment(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    LEGACY dedup, kept for the PROTECTED verticals (Re-Commerce, ReWerse,
    Institutional Business) so their numbers are unchanged. Keeps ONE line per
    shipment — the max-Quantity line (SubTotal taken once) — but sets that line's
    Quantity to the shipment's total returned quantity.
    """
    ref = _col(df, "Referenceno", "Reference#")
    qty = _col(df, "Quantity")
    if not ref or not qty or df.empty:
        return df, 0
    df = df.copy()
    df[qty] = pd.to_numeric(df[qty], errors="coerce").fillna(0)
    totals = df.groupby(ref)[qty].sum()
    before = len(df)
    kept = (df.sort_values(qty, ascending=False)
              .drop_duplicates(subset=[ref], keep="first")
              .sort_index().reset_index(drop=True))
    kept[qty] = kept[ref].map(totals)
    return kept, before - len(kept)


# Verticals to leave EXACTLY as before — their CN/DN keep the legacy per-shipment
# dedup; everyone else gets the note-level summing (sums genuinely separate notes).
# Re-Commerce, ReWerse and IB (Institutional) are protected — kept unchanged.
_PROTECTED_ACCOUNTS = ("recommerce", "re-commerce", "rewerse", "institutional")


def _dedup_notes_by_account(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Apply note-level summing to the non-protected verticals and the legacy
    per-shipment dedup to the protected ones (Re-Commerce / ReWerse / IB),
    so the protected verticals' figures are untouched.
    """
    acc = _col(df, "Account")
    if not acc or df.empty:
        return _one_line_per_note(df)
    prot_mask = df[acc].astype(str).str.lower().apply(
        lambda s: any(p in s for p in _PROTECTED_ACCOUNTS))
    prot, dp = _one_line_per_shipment(df[prot_mask])
    elig, de = _one_line_per_note(df[~prot_mask])
    out = pd.concat([prot, elig], ignore_index=True)
    return out, dp + de


def void_dn_shipments(dn_df: pd.DataFrame) -> set:
    """
    Shipment IDs whose marketplace DN is VOID and which have NO valid
    (non-void) marketplace DN — i.e. the debit note was raised then cancelled,
    so there is no actual debit note. The query file still treats these as
    'has a DN', so we surface them here to exclude them from the provision
    (a voided DN is not a valid DN).
    """
    if dn_df is None or dn_df.empty:
        return set()
    acc = _col(dn_df, "Account")
    sta = _col(dn_df, "Vendor_Credit_Status", "Vendor Credit Status")
    ref = _col(dn_df, "Referenceno", "Reference#")
    if not (acc and sta and ref):
        return set()
    mp   = dn_df[dn_df[acc].astype(str).str.lower().str.startswith("marketplace")]
    s    = mp[sta].astype(str).str.strip().str.lower()
    void  = set(mp.loc[s == "void", ref].astype(str).str.strip())
    valid = set(mp.loc[~s.isin(["void", "pending"]), ref].astype(str).str.strip())
    return void - valid


# ── Vendor Credits / DN ───────────────────────────────────────────────────────
def clean_dn(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Keep rows where:
      - Account starts with 'Marketplace' (basic rule — only marketplace returns)
      - Vendor Credit Status NOT IN ('Void', 'Pending')
    """
    original = len(df)
    stats = {"original_rows": original}

    account_col = _col(df, "Account")
    status_col  = _col(df, "Vendor_Credit_Status", "Vendor Credit Status")

    if account_col:
        mask = df[account_col].str.strip().str.lower().str.startswith("marketplace")
        stats["dropped_non_marketplace"] = int((~mask).sum())
        df = df[mask].copy()
    else:
        stats["dropped_non_marketplace"] = 0

    if status_col:
        mask = ~df[status_col].str.strip().str.lower().isin(["void", "pending"])
        stats["dropped_void_pending"] = int((~mask).sum())
        df = df[mask].copy()
    else:
        stats["dropped_void_pending"] = 0

    df, dropped = _dedup_notes_by_account(df)
    stats["dropped_extra_lines"] = dropped

    stats["final_rows"] = len(df)
    return df.reset_index(drop=True), stats
