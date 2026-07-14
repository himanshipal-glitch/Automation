"""
Frozen month-end snapshots for the Management Summary.

The MIS Zoho export only carries the CURRENT open invoices, so the live pipeline
can only compute the latest month(s). The true closed-month figures live in the
per-vertical "Profitability Report of <vertical> till <dd-mm-yyyy>.xlsx" files
(the manual's own monthly Summary grid).

This module:
  1. auto-discovers the LATEST per-vertical report file in the working folder,
  2. parses each file's monthly Summary grid,
  3. maps its rows onto the app's SUMMARY_METRICS,
so the Management Summary can FREEZE the closed months (Apr, May, Jun…) exactly as
the manual reports them, and only compute the latest/open month live from the MIS.

Nothing here fabricates data — it reads the numbers straight from the report files.
"""
from __future__ import annotations
import os, re, glob
import pandas as pd

from reports import SUMMARY_METRICS   # keep row order in sync with the live summary

# file-name vertical keyword → (app tab label, candidate summary sheet names)
_VERTICAL_MAP = [
    ("endgenerator", "End Generator", ["Summary"]),
    ("itad",         "IT AD",         ["IT AD", "Summary"]),
    ("plastic",      "Plastic",       ["Summary"]),
    ("recommerce",   "Re-Commerce",   ["Summary"]),
    ("afr",          "AFR",           ["Summary"]),
    ("m4",           "M4",            ["M4", "Summary"]),
    ("rewerse",      "ReWerse",       ["Summary"]),
    ("enterprise",   "Enterprise",    ["Enterprise", "Summary"]),
]

# Recykal is mid-transition on a couple of vertical names — the live Zoho MIS
# export may still say the OLD name (e.g. "Metal", "IB(B2B)") in its Account
# field while the manual per-vertical report files already use the NEW name
# (matched via _VERTICAL_MAP above). Mirror frozen data under both spellings
# so the freeze finds a match regardless of which name today's export uses.
_TAB_ALIASES = {
    "End Generator": ["Metal"],
    "Enterprise": ["IB(B2B)"],
    "Processing Center": ["IB(Warehouse)"],
}


def _apply_tab_aliases(d: dict) -> None:
    """Mutates `d` in place: for every canonical tab present, also expose its
    value under each known OLD-name alias (only if the alias isn't already a
    real key — never overwrite genuinely distinct data)."""
    for canon, olds in _TAB_ALIASES.items():
        if canon in d:
            for old in olds:
                d.setdefault(old, d[canon])

# money rows are rounded to 0, ratios/per-kg to 2, counts are ints, %-rows scale ×100
# Row indexes follow reports.SUMMARY_METRICS (28 rows):
# …14=Full Rejection, 15=Receivables, 16=FY27 R, 17=Old R, 18=DSO,
# 19=Payable, 20=FY27 P, 21=Old P, 22=DPO, 23=WC Days, 24=CN val, 25=CN%,
# 26=DN val, 27=DN%
_MONEY   = {0, 1, 2, 3, 5, 6, 24, 26}          # (0=Qty rounds to 2, handled below)
_RATIO2  = {4, 7, 8, 9, 10, 25, 27}
_COUNTS  = {11, 12, 13}
_DAYS    = {18, 22, 23}
_BALANCE = {15, 19}
# FY balances/day rows (incl. the FY27/Old splits) stay live, never summed:
_KEEP_LIVE_FY = {14, 15, 16, 17, 18, 19, 20, 21, 22, 23}
# additive rows summed for the FY total:
_ADDITIVE_FY = {0, 1, 2, 3, 5, 6, 11, 12, 13, 24, 26}


def _mkey(s) -> str:
    return re.sub(r"[^a-z0-9%]", "", str(s).lower())


def _metric_idx(label: str):
    """Map a Summary-sheet row label to (SUMMARY_METRICS index, scale) or None.
    scale=100 turns a stored fraction (0.29) into a percent (29)."""
    n = _mkey(label)
    if not n:
        return None
    if n.startswith("quantity"):
        # kept verbatim — MT for weight verticals, units for IT AD / Re-Commerce
        # (the live summary also displays MT, so the axis is consistent).
        # scale=-1 flags an MT row so per-kg maths uses qty×1000.
        return (0, -1 if "mt" in n else 1)
    if n in ("sales", "netrevenue"):        return (1, 1)
    if n == "purchases":                    return (2, 1)
    if n == "grossmargin%":                 return (4, 100)
    if n == "grossmargin":                  return (3, 1)
    if n == "operationalcost":              return (5, 1)
    if n == "netmargin%":                   return (7, 100)
    if n == "netmargin":                    return (6, 1)
    if n in ("revenueperunit", "revenueperkg"):        return (8, 1)
    if n in ("purchasecostperunit", "purchasecostperkg"): return (9, 1)
    if n.startswith("nooftransactions"):    return (11, 1)
    if n.startswith("noofsellers"):         return (12, 1)
    if n.startswith("noofbuyers"):          return (13, 1)
    if n == "fullrejection":                return (14, 1)
    if n.startswith("receivable"):          return (15, 1)   # incl. "Receivable (Exl Legacy)"
    if n.startswith("dso"):                 return (18, 1)
    if n in ("payable", "payables"):        return (19, 1)
    if n.startswith("dpo"):                 return (22, 1)
    if n == "workingcapitaldays":           return (23, 1)
    if "creditnotes" in n and "%" in n:     return (25, 100)
    if "creditnotes" in n and "value" in n: return (24, 1)
    if "debitnotes" in n and "%" in n:      return (27, 100)
    if "debitnotes" in n and "value" in n:  return (26, 1)
    return None


_MRE = re.compile(r"^[A-Za-z]{3}-\d{2}$")


def parse_summary(path: str, sheet_candidates: list[str]) -> dict:
    """Parse one report's monthly Summary grid → {mmm-yy: {metric_idx: value}}."""
    try:
        xl = pd.ExcelFile(path)
    except Exception:
        return {}
    sheet = next((s for s in sheet_candidates if s in xl.sheet_names), None)
    if sheet is None:
        return {}
    raw = pd.read_excel(path, sheet_name=sheet, header=None, nrows=60)
    ncol = raw.shape[1]

    # month row = first row carrying ≥2 'mmm-yy' labels. The sheet can hold
    # extra grids to the right (e.g. last year's Apr-25 block) — keep only the
    # FIRST occurrence of each month label so this year's block wins.
    month_row, month_cols = None, {}
    for i in range(len(raw)):
        hits, seen = {}, set()
        for j in range(ncol):
            v = raw.iat[i, j]
            if isinstance(v, str) and _MRE.match(v.strip()):
                mv = v.strip()
                if mv not in seen:
                    hits[j] = mv
                    seen.add(mv)
        if len(hits) >= 2:
            month_row, month_cols = i, hits
            break
    if month_row is None:
        return {}

    first_mc = min(month_cols)
    # label column = the column left of the months with the most text labels
    label_col, best_n = first_mc - 1, -1
    for j in range(first_mc):
        n = sum(1 for i in range(month_row + 1, len(raw))
                if isinstance(raw.iat[i, j], str) and raw.iat[i, j].strip())
        if n > best_n:
            best_n, label_col = n, j

    out = {m: {} for m in month_cols.values()}
    tc_abs = {m: None for m in month_cols.values()}
    qty    = {m: None for m in month_cols.values()}
    qty_is_mt = False

    for i in range(month_row + 1, len(raw)):
        lab = raw.iat[i, label_col]
        if not (isinstance(lab, str) and lab.strip()):
            continue
        n = _mkey(lab)
        # absolute transport charges → used to derive Transportation Charges Per Kg
        if n in ("transportationcharges", "transportcharges"):
            for j, m in month_cols.items():
                v = pd.to_numeric(raw.iat[i, j], errors="coerce")
                if pd.notna(v) and tc_abs[m] is None:
                    tc_abs[m] = float(v)
            continue
        r = _metric_idx(lab)
        if r is None:
            continue
        idx, scale = r
        for j, m in month_cols.items():
            if idx in out[m]:
                continue        # FIRST occurrence wins — the main grid sits on top;
                                # lower blocks ("KPI's without Prov", trends) repeat
                                # labels like Sales/Gross Margin and must not overwrite
            v = pd.to_numeric(raw.iat[i, j], errors="coerce")
            if pd.isna(v):
                continue
            val = float(v)
            if scale == 100:                      # fraction → percent (guard if already %)
                val = val * 100 if -2 < val < 2 else val
            elif scale == -1:                     # MT row — kept verbatim, flagged
                qty_is_mt = True
            out[m][idx] = val
            if idx == 0:
                qty[m] = val

    # Per-kg rows are RECOMPUTED (sales/qty_kg, pur/qty_kg) rather than copied —
    # the manual's own per-unit rows use inconsistent scales. Quantity stays in MT
    # for weight verticals, so the per-kg divisor is qty×1000 there.
    for m in month_cols.values():
        q = (qty.get(m) or 0.0) * (1000 if qty_is_mt else 1)
        c = out[m]
        if 1 in c:
            c[8] = round(c[1] / q, 2) if q else 0.0
        if 2 in c:
            c[9] = round(c[2] / q, 2) if q else 0.0
        if tc_abs[m] is not None:
            c[10] = round(tc_abs[m] / q, 2) if q else 0.0
    return out


def latest_files(folder: str) -> dict:
    """{app tab label: (path, sheet_candidates, till_date)} — the newest
    'till <date>' file per vertical found in `folder`."""
    chosen = {}   # tab -> (date, path, sheets)
    for path in glob.glob(os.path.join(folder, "*.xlsx")):
        base = os.path.basename(path)
        m = re.search(r"report of (.+?)\s+till\s+(\d{2}-\d{2}-\d{4})", base, re.I)
        if not m:
            continue
        vkey = _mkey(m.group(1))
        try:
            dt = pd.to_datetime(m.group(2), format="%d-%m-%Y")
        except Exception:
            continue
        for kw, tab, sheets in _VERTICAL_MAP:
            if kw in vkey:
                if tab not in chosen or dt > chosen[tab][0]:
                    chosen[tab] = (dt, path, sheets)
                break
    return {tab: (p, sh, dt) for tab, (dt, p, sh) in chosen.items()}


# parse cache — reading ~8 manual workbooks takes ~10s; per-vertical emails would
# re-pay that per vertical. Keyed by the files' paths + modification times, so
# dropping a NEW "till" file into the folder still refreshes automatically.
_CACHE: dict = {}


def _cache_key(kind: str, folder: str):
    import os
    files = latest_files(folder)
    sig = tuple(sorted((p, os.path.getmtime(p)) for p, _sh, _t in files.values()))
    return (kind, folder, sig)


def frozen_columns(folder: str) -> dict:
    """{app tab label: {mmm-yy: {metric_idx: value}}} for every vertical file found,
    plus an aggregated 'All Categories'. Only months FULLY covered by the file
    (month-end ≤ the filename's till-date) are kept — a 'till 21-06' file freezes
    Apr & May but NOT its partial June."""
    try:
        k = _cache_key("columns", folder)
        if k in _CACHE:
            return _CACHE[k]
    except Exception:
        k = None
    per = {}
    for tab, (path, sheets, till) in latest_files(folder).items():
        # current Indian FY of the till-date (some sheets carry last year's block)
        fy_start = pd.Timestamp(till.year if till.month >= 4 else till.year - 1, 4, 1)
        cols = parse_summary(path, sheets)
        cols = {m: c for m, c in cols.items()
                if pd.notna(_mdt(m)) and _mdt(m) >= fy_start
                and (_mdt(m) + pd.offsets.MonthEnd(0)) <= till}
        if cols:
            per[tab] = cols
    per["All Categories"] = _aggregate_all(per)   # BEFORE aliasing — avoid double-counting
    _apply_tab_aliases(per)
    if k is not None:
        _CACHE[k] = per
    return per


def _aggregate_all(per: dict) -> dict:
    """Sum the per-vertical frozen months into an 'All Categories' grid.
    Only months covered by EVERY vertical are aggregated — a month one vertical's
    file only partially covers must not freeze as an incomplete company total.
    Additive rows sum; ratios are recomputed; DSO/DPO/WC are left to the live FY."""
    if not per:
        return {}
    months = set.intersection(*(set(cols) for cols in per.values()))
    allc = {}
    for m in months:
        add = {i: 0.0 for i in (_ADDITIVE_FY | _BALANCE)}
        tc_abs = 0.0
        got = False
        for tab, cols in per.items():
            c = cols.get(m)
            if not c:
                continue
            got = True
            for i in (_ADDITIVE_FY | _BALANCE):
                add[i] += float(c.get(i, 0) or 0)
            tc_abs += float(c.get(10, 0) or 0) * float(c.get(0, 0) or 0)
        if not got:
            continue
        qty, sales, pur = add[0], add[1], add[2]
        cell = dict(add)
        cell[4]  = round(100 * add[3] / sales, 2) if sales else 0.0
        cell[7]  = round(100 * add[6] / sales, 2) if sales else 0.0
        cell[8]  = round(sales / qty, 2) if qty else 0.0
        cell[9]  = round(pur / qty, 2) if qty else 0.0
        cell[10] = round(tc_abs / qty, 2) if qty else 0.0
        cell[25] = round(100 * add[24] / sales, 2) if sales else 0.0
        cell[27] = round(100 * add[26] / pur, 2) if pur else 0.0
        allc[m] = cell
    return allc


def _round_cell(idx: int, val: float):
    if idx in _COUNTS:
        return int(round(val))
    if idx == 0:
        return round(val, 2)
    if idx in _RATIO2:
        return round(val, 2)
    return round(val, 0)   # money, balances, days


def _mdt(m: str):
    return pd.to_datetime("01-" + m, format="%d-%b-%y", errors="coerce")


def apply_frozen(summaries: dict, folder: str, open_month: str | None) -> dict:
    """Overwrite each summary's CLOSED month columns (those before `open_month`)
    with the frozen manual figures, then recompute the FY Total. The open month
    and anything after it stay live. Mutates & returns `summaries`."""
    fc = frozen_columns(folder)
    open_dt = _mdt(open_month) if open_month else None

    for tab, df in summaries.items():
        cells_by_month = fc.get(tab)
        if not cells_by_month:
            continue
        for m, cells in cells_by_month.items():
            if m not in df.columns:
                continue
            if open_dt is not None and pd.notna(_mdt(m)) and _mdt(m) >= open_dt:
                continue                                   # keep the open month live
            cloc = df.columns.get_loc(m)
            for idx, val in cells.items():
                if 0 <= idx < len(df):
                    df.iat[idx, cloc] = _round_cell(idx, val)
        _recompute_fy(df, open_month, tab)
        _rederive_splits(df)
    return summaries


def _rederive_splits(df: pd.DataFrame) -> None:
    """Re-split the FY-27/Old rows AFTER the frozen overlay rewrites the parent
    Receivable/Payable — keep the FY-vs-old RATIO but rescale to the (frozen)
    parent, so FY27 + Old always equals the shown parent and neither goes
    negative. Rows: 15 Recv, 16 FY27 R, 17 Old R · 19 Pay, 20 FY27 P, 21 Old P."""
    if len(df) <= 21:
        return
    def g(i, c):
        return float(pd.to_numeric(pd.Series([df.iat[i, c]]), errors="coerce").fillna(0).iloc[0])
    for c in range(1, df.shape[1]):
        for parent, i27, iold in ((15, 16, 17), (19, 20, 21)):
            p = g(parent, c)
            tot = g(i27, c) + g(iold, c)
            r = (g(i27, c) / tot) if tot else 0.0     # FY-dated share, preserved
            df.iat[i27, c] = round(p * r, 0)
            df.iat[iold, c] = round(p - p * r, 0)


def frozen_details(folder: str) -> dict:
    """{app tab label: (detail_df, {mmm-yy, …})} — the LINE-BY-LINE rows of each
    vertical's fully-covered closed months, read from the manual report files'
    'Details' sheet. Lets the workbook's Profitability Report sheet carry the
    whole FY so Σ(rows) cross-checks the FY Total."""
    try:
        k = _cache_key("details", folder)
        if k in _CACHE:
            return _CACHE[k]
    except Exception:
        k = None
    out = {}
    for tab, (path, sheets, till) in latest_files(folder).items():
        try:
            xl = pd.ExcelFile(path)
        except Exception:
            continue
        if "Details" not in xl.sheet_names:
            continue
        raw = pd.read_excel(path, sheet_name="Details", header=None, nrows=8)
        hdr = None
        for i in range(len(raw)):
            vals = [str(x).strip().lower() for x in raw.iloc[i, :8].tolist()]
            if "quarter" in vals and "month" in vals:
                hdr = i
                break
        if hdr is None:
            continue
        df = pd.read_excel(path, sheet_name="Details", header=hdr)
        df = df.dropna(how="all")
        df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
        mcol = next((c for c in df.columns if str(c).strip().lower() == "month"), None)
        if mcol is None:
            continue
        mstr = df[mcol].apply(
            lambda v: v.strftime("%b-%y") if hasattr(v, "strftime") else str(v).strip())
        mdt = pd.to_datetime("01-" + mstr, format="%d-%b-%y", errors="coerce")
        fy_start = pd.Timestamp(till.year if till.month >= 4 else till.year - 1, 4, 1)
        keep = mdt.notna() & (mdt >= fy_start) & ((mdt + pd.offsets.MonthEnd(0)) <= till)
        if keep.any():
            out[tab] = (df[keep], set(mstr[keep]))
    _apply_tab_aliases(out)
    if k is not None:
        _CACHE[k] = out
    return out


# verticals that count UNITS (per-kg maths uses qty as-is); the rest are MT (×1000)
UNIT_TABS = {"IT AD", "Re-Commerce"}


def _recompute_fy(df: pd.DataFrame, open_month: str | None, tab: str = "") -> None:
    """FY Total = additive rows summed across displayed months (through the open
    month); ratios recomputed on those FY aggregates. Balance/day rows (Receivable,
    Payable, DSO, DPO, WC) are left as the live FY snapshot."""
    if "FY Total" not in df.columns:
        return
    months = [c for c in df.columns if c not in ("Metric", "FY Total")]
    open_dt = _mdt(open_month) if open_month else None
    use = [m for m in months if pd.notna(_mdt(m)) and
           (open_dt is None or _mdt(m) <= open_dt)]
    if not use:
        return
    fyloc = df.columns.get_loc("FY Total")

    def g(idx, m):
        return float(pd.to_numeric(pd.Series([df.iat[idx, df.columns.get_loc(m)]]),
                                   errors="coerce").fillna(0).iloc[0])

    def S(idx):
        return sum(g(idx, m) for m in use)

    # ── Open month (July) — Qty/Sales/Purchases DERIVED from the detail ────────
    # FY comes from the DETAIL (pre-freeze FY cell = _summary_block over the whole
    # Profitability Report detail). The open month is then the residual:
    #     open = detail-FY − Σ(prior displayed months).
    # And CRUCIALLY every open-month figure that USES Sales/Purchases/Qty is
    # re-derived from those residuals (not the live-pipeline July slice), so the
    # whole July column is internally consistent with its subtracted Sales/Purch.
    # Kept live (independent of the sales/purchase residual): Operational Cost,
    # absolute transport, CN/DN values, Receivable, Payable, and the counts.
    if open_month in months:
        _oc = df.columns.get_loc(open_month)
        _priors = [m for m in use if m != open_month]

        # live open-month values captured BEFORE overwriting (needed to re-derive)
        _S0, _P0 = g(1, open_month), g(2, open_month)          # live Sales / Purchases
        _gm0, _nm0, _ocst = g(3, open_month), g(6, open_month), g(5, open_month)
        _dso0, _dpo0 = g(18, open_month), g(22, open_month)
        _cnv, _dnv = g(24, open_month), g(26, open_month)      # CN / DN value (kept live)
        _tc_abs = _gm0 - _nm0 - _ocst                          # absolute transport (kept live)

        def _fyv(i):
            return float(pd.to_numeric(pd.Series([df.iat[i, fyloc]]),
                                       errors="coerce").fillna(0).iloc[0])
        _Qr = round(_fyv(0) - sum(g(0, m) for m in _priors), 2)
        _Sr = round(_fyv(1) - sum(g(1, m) for m in _priors), 0)
        _Pr = round(_fyv(2) - sum(g(2, m) for m in _priors), 0)
        df.iat[0, _oc], df.iat[1, _oc], df.iat[2, _oc] = _Qr, _Sr, _Pr

        _qkg = _Qr * (1 if tab in UNIT_TABS else 1000)
        _gm_r = _Sr - _Pr
        _nm_r = _gm_r - _tc_abs - _ocst
        df.iat[3, _oc]  = round(_gm_r, 0)                        # Gross Margin
        df.iat[6, _oc]  = round(_nm_r, 0)                        # Net Margin
        df.iat[4, _oc]  = round(100 * _gm_r / _Sr, 2) if _Sr else 0.0   # GM %
        df.iat[7, _oc]  = round(100 * _nm_r / _Sr, 2) if _Sr else 0.0   # NM %
        df.iat[8, _oc]  = round(_Sr / _qkg, 2) if _qkg else 0.0         # Revenue / Kg
        df.iat[9, _oc]  = round(_Pr / _qkg, 2) if _qkg else 0.0         # Purchase Cost / Kg
        df.iat[10, _oc] = round(_tc_abs / _qkg, 2) if _qkg else 0.0     # Transport / Kg
        df.iat[25, _oc] = round(100 * _cnv / _Sr, 2) if _Sr else 0.0    # CN % to Revenue
        df.iat[27, _oc] = round(100 * _dnv / _Pr, 2) if _Pr else 0.0    # DN % to Purchase
        # DSO/DPO scale inversely with Sales/Purchases (Receivable, Payable, days
        # are unchanged), so DSO_resid = DSO_live × Sales_live / Sales_resid.
        _dso_r = round(_dso0 * _S0 / _Sr, 0) if (_Sr and _S0) else _dso0
        _dpo_r = round(_dpo0 * _P0 / _Pr, 0) if (_Pr and _P0) else _dpo0
        df.iat[18, _oc], df.iat[22, _oc] = _dso_r, _dpo_r
        df.iat[23, _oc] = round(_dso_r - _dpo_r, 0)             # Working Capital Days

    qty, sales, pur = S(0), S(1), S(2)
    gm, oc, nm = S(3), S(5), S(6)
    cnv, dnv = S(24), S(26)
    # qty is displayed in MT for weight verticals — per-kg maths needs Kg
    qkg = qty * (1 if tab in UNIT_TABS else 1000)
    tc_abs = sum(g(10, m) * g(0, m) * (1 if tab in UNIT_TABS else 1000) for m in use)

    fy = {
        0: round(qty, 2), 1: round(sales, 0), 2: round(pur, 0), 3: round(gm, 0),
        5: round(oc, 0), 6: round(nm, 0), 24: round(cnv, 0), 26: round(dnv, 0),
        11: int(round(S(11))), 12: int(round(S(12))), 13: int(round(S(13))),
        4: round(100 * gm / sales, 2) if sales else 0.0,
        7: round(100 * nm / sales, 2) if sales else 0.0,
        8: round(sales / qkg, 2) if qkg else 0.0,
        9: round(pur / qkg, 2) if qkg else 0.0,
        10: round(tc_abs / qkg, 2) if qkg else 0.0,
        25: round(100 * cnv / sales, 2) if sales else 0.0,
        27: round(100 * dnv / pur, 2) if pur else 0.0,
    }
    for idx, val in fy.items():
        if idx not in _KEEP_LIVE_FY and 0 <= idx < len(df):
            df.iat[idx, fyloc] = val


# ── self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    files = latest_files(folder)
    print("Latest per-vertical files picked:")
    for tab, (p, sh, till) in files.items():
        print(f"  {tab:14} <- {os.path.basename(p)}  (till {till.date()})")
    # Check that required tabs are present.
    for tab in ["IT AD", "End Generator", "Enterprise", "All Categories"]:
        if tab not in files:
            continue
        cols = frozen_columns(folder).get(tab, {})
        print(f"\n=== {tab} ===")
        for m in sorted(cols, key=lambda x: _mdt(x)):
            c = cols[m]
            print(f"  {m}: Sales={c.get(1):,.0f}  Purch={c.get(2):,.0f}  "
                  f"GM={c.get(3):,.0f}  GM%={c.get(4)}  Recv={c.get(15)}  Pay={c.get(19)}")
