"""
In-memory data store backed by st.session_state.
Session data lives only for the browser session — EXCEPT the older-bills store,
which is persisted to disk so historical costs survive across sessions.
"""

import pandas as pd
import streamlit as st
from pathlib import Path

# Keep DB_DIR so the rest of the app doesn't break (used for glob in old clear logic)
DB_DIR = Path(__file__).parent / "databases"
DB_DIR.mkdir(exist_ok=True)

# Permanent on-disk store (NOT wiped between sessions) for the merged older bills
PERSIST_DIR = Path(__file__).parent / "persistent"
PERSIST_DIR.mkdir(exist_ok=True)
OLDER_BILLS_PATH = PERSIST_DIR / "older_bills.parquet"


def _safe_col(c: str) -> str:
    return (str(c).strip()
            .replace(" ", "_").replace("/", "_").replace(".", "")
            .replace("(", "").replace(")", "").replace(":", "")
            .replace("&", "and").replace("#", "no"))


def save_older_bills(new_df: pd.DataFrame) -> int:
    """
    Merge newly-uploaded older bills into the permanent store and persist.
    Accumulates across uploads (so adding more historical files grows the
    coverage), de-duplicating identical rows. Returns total rows stored.
    """
    if new_df is None or new_df.empty:
        return older_bills_count()
    nd = new_df.copy()
    nd.columns = [_safe_col(c) for c in nd.columns]
    existing = load_older_bills()
    combined = pd.concat([existing, nd], ignore_index=True) if not existing.empty else nd
    subset = [c for c in combined.columns if c != "_source_file"]
    combined = combined.drop_duplicates(subset=subset).reset_index(drop=True)
    try:
        combined.to_parquet(OLDER_BILLS_PATH, index=False)
    except Exception:
        combined.to_pickle(OLDER_BILLS_PATH.with_suffix(".pkl"))
    return len(combined)


def load_older_bills() -> pd.DataFrame:
    """Load the permanent merged older-bills store (empty DataFrame if none)."""
    if OLDER_BILLS_PATH.exists():
        try:
            return pd.read_parquet(OLDER_BILLS_PATH)
        except Exception:
            pass
    pkl = OLDER_BILLS_PATH.with_suffix(".pkl")
    if pkl.exists():
        try:
            return pd.read_pickle(pkl)
        except Exception:
            pass
    return pd.DataFrame()


def older_bills_count() -> int:
    return len(load_older_bills())


def clear_older_bills() -> None:
    for p in (OLDER_BILLS_PATH, OLDER_BILLS_PATH.with_suffix(".pkl")):
        if p.exists():
            p.unlink()


# ── Amazon × Recykal YTD store (permanent) ────────────────────────────────────
AMAZON_YTD_PATH = PERSIST_DIR / "amazon_ytd.parquet"


def save_amazon_ytd(new_df: pd.DataFrame) -> int:
    """Persist the Amazon × Recykal YTD sheet (replaces — it's a full snapshot)."""
    if new_df is None or new_df.empty:
        return amazon_ytd_count()
    nd = new_df.copy()
    nd.columns = [_safe_col(c) for c in nd.columns]
    try:
        nd.to_parquet(AMAZON_YTD_PATH, index=False)
    except Exception:
        nd.to_pickle(AMAZON_YTD_PATH.with_suffix(".pkl"))
    return len(nd)


def load_amazon_ytd() -> pd.DataFrame:
    if AMAZON_YTD_PATH.exists():
        try:
            return pd.read_parquet(AMAZON_YTD_PATH)
        except Exception:
            pass
    pkl = AMAZON_YTD_PATH.with_suffix(".pkl")
    if pkl.exists():
        try:
            return pd.read_pickle(pkl)
        except Exception:
            pass
    return pd.DataFrame()


def amazon_ytd_count() -> int:
    return len(load_amazon_ytd())


def clear_amazon_ytd() -> None:
    for p in (AMAZON_YTD_PATH, AMAZON_YTD_PATH.with_suffix(".pkl")):
        if p.exists():
            p.unlink()


# ── Re-Commerce manual detail store (permanent) ───────────────────────────────
# Re-Commerce's accurate costs live in a manually-maintained detail sheet (same
# format as the Profitability Report) — used AS-IS for the FY (no Amazon×Recykal
# re-costing) through its own cutoff date; transactions after the cutoff fall
# back to the live Amazon×Recykal logic. Maintained in two variants — WITH and
# WITHOUT Samsung — so two separate reports can be generated.
RECO_MANUAL_WITH_PATH    = PERSIST_DIR / "recommerce_manual_with_samsung.parquet"
RECO_MANUAL_WITHOUT_PATH = PERSIST_DIR / "recommerce_manual_without_samsung.parquet"


def _reco_manual_path(with_samsung: bool):
    return RECO_MANUAL_WITH_PATH if with_samsung else RECO_MANUAL_WITHOUT_PATH


def save_recommerce_manual(df: pd.DataFrame, with_samsung: bool) -> int:
    """Persist a Re-Commerce manual detail sheet (full snapshot — replaces)."""
    if df is None or df.empty:
        return recommerce_manual_count(with_samsung)
    nd = df.copy()
    nd.columns = _uniq_cols([str(c) for c in nd.columns])
    p = _reco_manual_path(with_samsung)
    try:
        nd.to_parquet(p, index=False)
    except Exception:
        nd.to_pickle(p.with_suffix(".pkl"))
    return len(nd)


def load_recommerce_manual(with_samsung: bool) -> pd.DataFrame:
    p = _reco_manual_path(with_samsung)
    for pp in (p, p.with_suffix(".pkl")):
        if pp.exists():
            try:
                return (pd.read_parquet(pp) if pp.suffix == ".parquet"
                        else pd.read_pickle(pp))
            except Exception:
                pass
    return pd.DataFrame()


def recommerce_manual_count(with_samsung: bool) -> int:
    return len(load_recommerce_manual(with_samsung))


def clear_recommerce_manual(with_samsung: bool | None = None) -> None:
    paths = ([_reco_manual_path(True), _reco_manual_path(False)]
             if with_samsung is None else [_reco_manual_path(with_samsung)])
    for p in paths:
        for pp in (p, p.with_suffix(".pkl")):
            if pp.exists():
                pp.unlink()


# ── "CF.DN = No" shipment exclusion list (permanent) ──────────────────────────
NO_DN_PATH = PERSIST_DIR / "no_dn_shipments.parquet"


def save_no_dn_shipments(df: pd.DataFrame) -> int:
    """
    Persist the list of shipment IDs that have CF.DN = No/false. The provision
    is applied only to shipments NOT in this list. Stores the shipment-id column.
    """
    if df is None or df.empty:
        return no_dn_count()
    df = df.copy()
    df.columns = [_safe_col(c) for c in df.columns]
    # if a DebitNotefromBuyer-style flag exists, keep only the NO/false rows
    flag = next((c for c in df.columns if "debitnote" in c.lower() and "buyer" in c.lower()), None)
    if flag:
        df = df[df[flag].astype(str).str.strip().str.lower().isin(["no", "false", "n", "0"])]
    # pick the shipment-id column (case-insensitive)
    col = None
    for c in df.columns:
        if c.lower() in ("shipment_id", "cfso_number", "shipment", "cf_so_number", "so_number", "shipmentid"):
            col = c; break
    if col is None:                       # fall back to first column
        col = df.columns[0]
    ships = (df[col].astype(str).str.strip())
    ships = ships[(ships != "") & (ships.str.lower() != "nan")].unique()
    out = pd.DataFrame({"Shipment_ID": ships})
    try:
        out.to_parquet(NO_DN_PATH, index=False)
    except Exception:
        out.to_pickle(NO_DN_PATH.with_suffix(".pkl"))
    return len(out)


def load_no_dn_shipments() -> set:
    df = pd.DataFrame()
    if NO_DN_PATH.exists():
        try: df = pd.read_parquet(NO_DN_PATH)
        except Exception: df = pd.DataFrame()
    elif NO_DN_PATH.with_suffix(".pkl").exists():
        try: df = pd.read_pickle(NO_DN_PATH.with_suffix(".pkl"))
        except Exception: df = pd.DataFrame()
    if df.empty:
        return set()
    return set(df.iloc[:, 0].astype(str).str.strip())


def no_dn_count() -> int:
    return len(load_no_dn_shipments())


def clear_no_dn_shipments() -> None:
    for p in (NO_DN_PATH, NO_DN_PATH.with_suffix(".pkl")):
        if p.exists():
            p.unlink()


# ── IB (Warehouse) shipment list ──────────────────────────────────────────────
# The definitive list of Institutional Business shipments that are WAREHOUSE
# operations. Every IB shipment NOT in this list is Enterprise (B2B) — this
# replaces the old 'SH prefix = B2B' heuristic.
IB_WAREHOUSE_PATH = PERSIST_DIR / "ib_warehouse_shipments.parquet"


def save_ib_warehouse_shipments(ships) -> int:
    """Persist the warehouse shipment-id list (replaces — it's a full snapshot)."""
    s = pd.Series(sorted(set(str(x).strip() for x in ships)), dtype=str)
    s = s[(s != "") & (s.str.lower() != "nan")]
    out = pd.DataFrame({"Shipment_ID": s.values})
    try:
        out.to_parquet(IB_WAREHOUSE_PATH, index=False)
    except Exception:
        out.to_pickle(IB_WAREHOUSE_PATH.with_suffix(".pkl"))
    return len(out)


def load_ib_warehouse_shipments() -> set:
    df = pd.DataFrame()
    if IB_WAREHOUSE_PATH.exists():
        try: df = pd.read_parquet(IB_WAREHOUSE_PATH)
        except Exception: df = pd.DataFrame()
    elif IB_WAREHOUSE_PATH.with_suffix(".pkl").exists():
        try: df = pd.read_pickle(IB_WAREHOUSE_PATH.with_suffix(".pkl"))
        except Exception: df = pd.DataFrame()
    if df.empty:
        return set()
    return set(df.iloc[:, 0].astype(str).str.strip())


def ib_warehouse_count() -> int:
    return len(load_ib_warehouse_shipments())


# ── ENTERPRISE manual inputs ──────────────────────────────────────────────────
# 1) Custom Duty bills: shipments with NO bill/invoice side in Zoho, entered
#    manually as purchases into a user-selected month (Enterprise only).
# 2) Operational Cost per month: user-entered override for the Enterprise
#    summary row. Both persist until the user edits them again.
CUSTOM_DUTY_PATH = PERSIST_DIR / "enterprise_custom_duty.parquet"
ENT_OPCOST_PATH  = PERSIST_DIR / "enterprise_opcost.parquet"


# True/False result of the last GitHub write-through (for UI feedback),
# plus the exact failure reason so the UI can say WHY a sync failed.
LAST_SYNC_OK: bool | None = None
LAST_SYNC_ERR: str = ""


def _github_writethrough(path: Path, message: str) -> bool:
    """Commit a persistent store file to the GitHub repo, so manual entries
    survive hosted redeploys (Streamlit Cloud wipes the container filesystem
    on every reboot/redeploy — only repo-tracked files come back).

    Needs `[github]` in secrets: token (fine-grained PAT with Contents
    read+write on the repo), repo ("owner/name"), optional branch (main).
    Silent no-op when secrets are absent (e.g. running locally, where the
    folder IS the git checkout and the file simply persists on disk)."""
    global LAST_SYNC_ERR
    LAST_SYNC_ERR = ""
    try:
        import streamlit as st
        g = st.secrets.get("github", None)
        token = g.get("token") if g else None
        repo = g.get("repo") if g else None
        branch = (g.get("branch") if g else None) or "main"
        if not token or not repo:
            LAST_SYNC_ERR = "[github] secrets missing (token/repo)"
            return False
    except Exception:
        LAST_SYNC_ERR = "[github] secrets missing"
        return False
    try:
        import base64
        import requests
        url = f"https://api.github.com/repos/{repo}/contents/persistent/{Path(path).name}"
        hdrs = {"Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}
        sha = None
        r = requests.get(url, headers=hdrs, params={"ref": branch}, timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
        payload = {"message": message, "branch": branch,
                   "content": base64.b64encode(Path(path).read_bytes()).decode()}
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=hdrs, json=payload, timeout=20)
        if r.status_code in (200, 201):
            return True
        try:
            _gh_msg = r.json().get("message", "")
        except Exception:
            _gh_msg = r.text[:100]
        LAST_SYNC_ERR = f"GitHub HTTP {r.status_code}: {_gh_msg}"
        return False
    except Exception as e:
        LAST_SYNC_ERR = f"network error: {e}"
        return False


def _save_small(df: pd.DataFrame, path, sync_msg: str | None = None) -> int:
    global LAST_SYNC_OK
    written = path
    try:
        df.to_parquet(path, index=False)
    except Exception:
        written = path.with_suffix(".pkl")
        df.to_pickle(written)
    LAST_SYNC_OK = _github_writethrough(written, sync_msg) if sync_msg else None
    return len(df)


def _load_small(path) -> pd.DataFrame:
    for pp in (path, path.with_suffix(".pkl")):
        if pp.exists():
            try:
                return (pd.read_parquet(pp) if pp.suffix == ".parquet"
                        else pd.read_pickle(pp))
            except Exception:
                pass
    return pd.DataFrame()


# rows the last save REJECTED (for loud UI feedback — silent drops made it
# look like "the app can't store the data" when a month was typed as July-26)
LAST_SAVE_DROPPED: list = []


def _parse_month_series(mon: pd.Series) -> pd.Series:
    """FORGIVING month parser → canonical 'Mmm-yy'. Accepts Jul-26, july-26,
    July 26, Jul 2026, July 2026, 07-26, 2026-07, 07/2026 … NaT when hopeless."""
    s = mon.astype(str).str.strip().str.replace(r"[./]", "-", regex=True)
    out = pd.to_datetime(s, format="%b-%y", errors="coerce")
    for fmt in ("%B-%y", "%b-%Y", "%B-%Y", "%b %y", "%B %y", "%b %Y", "%B %Y",
                "%m-%y", "%m-%Y", "%Y-%m"):
        left = out.isna()
        if not left.any():
            break
        out[left] = pd.to_datetime(s[left], format=fmt, errors="coerce")
    left = out.isna()
    if left.any():   # last resort: pandas' general parser
        out[left] = pd.to_datetime(s[left], errors="coerce", dayfirst=True)
    return out


def save_custom_duty(df: pd.DataFrame) -> int:
    """Full snapshot — replaces. Columns: Month (mmm-yy), Supplier Name, Amount.
    Custom-duty line items carry NO shipment id (same as the manual report).
    Keeps rows with a parseable month and a non-zero amount; rejected rows are
    reported via LAST_SAVE_DROPPED (never dropped silently)."""
    global LAST_SAVE_DROPPED
    LAST_SAVE_DROPPED = []
    if df is None:
        return 0
    d = df.copy()
    d.columns = [str(c) for c in d.columns]
    mdt = _parse_month_series(d.iloc[:, 0])
    amt = pd.to_numeric(d.iloc[:, -1], errors="coerce")
    blank = mdt.isna() & amt.isna()          # empty editor row — not an error
    ok = mdt.notna() & amt.notna() & amt.ne(0)
    LAST_SAVE_DROPPED = [f"'{d.iloc[i, 0]}' / amount '{d.iloc[i, -1]}'"
                         for i in d.index[~ok & ~blank]]
    d = d[ok].reset_index(drop=True)
    if len(d):
        d.isetitem(0, mdt[ok].dt.strftime("%b-%y").values)   # canonical Mmm-yy
    return _save_small(d, CUSTOM_DUTY_PATH,
                       sync_msg="Update Enterprise Custom Duty bills (app entry)")


def load_custom_duty() -> pd.DataFrame:
    return _load_small(CUSTOM_DUTY_PATH)


def save_enterprise_opcost(df: pd.DataFrame) -> int:
    """Full snapshot — replaces. Rows: Month (mmm-yy) + Amount. Months parse
    forgivingly (July-26, 07-26 … → 'Mmm-yy'); rejected rows are reported via
    LAST_SAVE_DROPPED (never dropped silently)."""
    global LAST_SAVE_DROPPED
    LAST_SAVE_DROPPED = []
    if df is None:
        return 0
    d = df.copy()
    mdt = _parse_month_series(d.iloc[:, 0])
    amt = pd.to_numeric(d.iloc[:, 1], errors="coerce")
    blank = mdt.isna() & amt.isna()          # empty editor row — not an error
    ok = mdt.notna() & amt.notna()
    LAST_SAVE_DROPPED = [f"'{d.iloc[i, 0]}' / amount '{d.iloc[i, 1]}'"
                         for i in d.index[~ok & ~blank]]
    d = d[ok].reset_index(drop=True)
    if len(d):
        d.isetitem(0, mdt[ok].dt.strftime("%b-%y").values)   # canonical Mmm-yy
        d = d.drop_duplicates(subset=[d.columns[0]], keep="last").reset_index(drop=True)
    return _save_small(d, ENT_OPCOST_PATH,
                       sync_msg="Update Enterprise Operational Cost overrides (app entry)")


def load_enterprise_opcost() -> dict:
    """{mmm-yy: amount}"""
    d = _load_small(ENT_OPCOST_PATH)
    if d.empty:
        return {}
    return {str(m).strip(): float(a) for m, a in
            zip(d.iloc[:, 0], pd.to_numeric(d.iloc[:, 1], errors="coerce").fillna(0))}


# ── Accumulated profitability-details store (permanent) ──────────────────────
# Zoho's MIS export is ROLLING — each one only carries recent invoices, so a
# month's line rows vanish from later exports. This store accumulates every
# upload's profitability rows and UPSERTS by (Shipment ID + Invoice No): when a
# shipment reappears in a newer MIS (e.g. a late CN/DN updated it), its rows are
# replaced with the newer version; months no longer in the export are kept.
PROFIT_DETAILS_PATH = PERSIST_DIR / "profit_details.parquet"


def _uniq_cols(cols) -> list[str]:
    """Parquet forbids duplicate column names (the 107-col report repeats a few,
    e.g. 'Month') — suffix repeats with .1, .2 …"""
    seen, out = {}, []
    for c in cols:
        c = str(c)
        if c in seen:
            seen[c] += 1
            out.append(f"{c}.{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out


def _profit_key(df: pd.DataFrame) -> pd.Series:
    # positions 3 / 39 = Shipment ID / Inv. No. (stable in the 107-col layout)
    return (df.iloc[:, 3].astype(str).str.strip() + "||"
            + df.iloc[:, 39].astype(str).str.strip())


def upsert_profit_details(profit_df: pd.DataFrame) -> int:
    """Merge this run's profitability rows into the permanent store.
    Rows sharing a (Shipment ID + Inv No) key with the new batch are REPLACED
    (late CN/DN updates win); everything else is kept. Returns total rows."""
    if profit_df is None or profit_df.empty:
        return profit_details_count()
    new = profit_df.copy()
    new = new.drop(columns=["_source_file"], errors="ignore")
    new.columns = _uniq_cols(new.columns)
    cur = load_profit_details()
    if not cur.empty:
        keep = cur[~_profit_key(cur).isin(set(_profit_key(new)))]
        # align schemas by name (new export's layout wins the column order)
        allc = list(new.columns) + [c for c in keep.columns if c not in new.columns]
        keep = keep.reindex(columns=allc)
        new = new.reindex(columns=allc)
        out = pd.concat([keep, new], ignore_index=True)
    else:
        out = new
    try:
        out.to_parquet(PROFIT_DETAILS_PATH, index=False)
    except Exception:
        out.to_pickle(PROFIT_DETAILS_PATH.with_suffix(".pkl"))
    return len(out)


def load_profit_details() -> pd.DataFrame:
    for p in (PROFIT_DETAILS_PATH, PROFIT_DETAILS_PATH.with_suffix(".pkl")):
        if p.exists():
            try:
                return (pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_pickle(p))
            except Exception:
                pass
    return pd.DataFrame()


def profit_details_view(current_df: pd.DataFrame) -> pd.DataFrame:
    """Accumulated store MERGED with the current run's rows (current wins on the
    Shipment+Inv key), WITHOUT persisting. So a workbook's Details sheet always
    reflects the LATEST upload plus history for months that dropped out of the
    rolling MIS — even if upsert_profit_details hasn't run yet this session.
    Alignment is POSITIONAL (both are the fixed engine layout) so the session's
    sanitized column names don't misalign against the store's names."""
    cur = load_profit_details()
    if current_df is None or getattr(current_df, "empty", True):
        return cur
    new = current_df.copy().drop(columns=["_source_file"], errors="ignore")
    if cur.empty:
        new.columns = _uniq_cols([str(c) for c in new.columns])
        return new
    if new.shape[1] == cur.shape[1]:
        new.columns = list(cur.columns)          # align by position, store names win
    else:
        new.columns = _uniq_cols([str(c) for c in new.columns])
    keep = cur[~_profit_key(cur).isin(set(_profit_key(new)))]
    allc = list(cur.columns) + [c for c in new.columns if c not in cur.columns]
    keep = keep.reindex(columns=allc)
    new = new.reindex(columns=allc)
    return pd.concat([keep, new], ignore_index=True)


def profit_details_count() -> int:
    return len(load_profit_details())


def clear_profit_details() -> None:
    for p in (PROFIT_DETAILS_PATH, PROFIT_DETAILS_PATH.with_suffix(".pkl")):
        if p.exists():
            p.unlink()


# ── Month-lock store (frozen month-end summary snapshots) ─────────────────────
# Once a month closes it is frozen here and never recomputed. Additive metrics
# (Sales, Purchases, …) use these to derive the open month as FY_live − Σ(frozen
# priors). Balance metrics (Receivable, Payable) are shown directly from here.
# Columns: fy, vertical, metric, month, value, kind ('additive' | 'balance').
MONTH_LOCKS_PATH = PERSIST_DIR / "month_locks.parquet"
_LOCK_COLS = ["fy", "vertical", "metric", "month", "value", "kind"]


def load_month_locks() -> pd.DataFrame:
    for p in (MONTH_LOCKS_PATH, MONTH_LOCKS_PATH.with_suffix(".pkl")):
        if p.exists():
            try:
                return (pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_pickle(p))
            except Exception:
                pass
    return pd.DataFrame(columns=_LOCK_COLS)


def is_month_locked(fy: str, vertical: str, month: str) -> bool:
    df = load_month_locks()
    if df.empty:
        return False
    return bool(((df["fy"] == fy) & (df["vertical"] == vertical) & (df["month"] == month)).any())


def save_month_lock(rows: list[dict]) -> int:
    """Persist frozen snapshots for one (fy, vertical, month). `rows` = list of
    {fy, vertical, metric, month, value, kind}. Idempotent: an already-locked
    (fy, vertical, metric, month) is NOT overwritten."""
    if not rows:
        return 0
    new = pd.DataFrame(rows, columns=_LOCK_COLS)
    cur = load_month_locks()
    keys = ["fy", "vertical", "metric", "month"]
    if not cur.empty:
        merged = cur.merge(new[keys], on=keys, how="left", indicator=True)
        # keep existing; append only genuinely new keys
        add = new.merge(cur[keys], on=keys, how="left", indicator=True)
        add = add[add["_merge"] == "left_only"].drop(columns="_merge")
        out = pd.concat([cur, add], ignore_index=True)
    else:
        out = new
    try:
        out.to_parquet(MONTH_LOCKS_PATH, index=False)
    except Exception:
        out.to_pickle(MONTH_LOCKS_PATH.with_suffix(".pkl"))
    return len(out)


def get_locked_value(fy: str, vertical: str, metric: str, month: str):
    df = load_month_locks()
    if df.empty:
        return None
    m = df[(df["fy"] == fy) & (df["vertical"] == vertical)
           & (df["metric"] == metric) & (df["month"] == month)]
    return float(m["value"].iloc[0]) if len(m) else None


def clear_month_locks() -> None:
    for p in (MONTH_LOCKS_PATH, MONTH_LOCKS_PATH.with_suffix(".pkl")):
        if p.exists():
            p.unlink()


# canonical sheet-name → logical key prefix
SHEET_DB_MAP = {
    "AP":           "ap",
    "AR":           "ar",
    "Bill":         "bill",
    "BillHistory":  "bill_history",
    "CN":           "cn",
    "DN":           "dn",
    "Inv":          "inv",
    "Query result": "query_result",
    "Sheet1 (2)":   "sheet1_2",
    "P&L":          "pnl",
    "Merged":       "merged",
}


def _key(sheet_name: str, table: str) -> str:
    prefix = SHEET_DB_MAP.get(sheet_name, sheet_name.lower().replace(" ", "_"))
    return f"__db__{prefix}__{table}"


def write_sheet(df: pd.DataFrame, sheet_name: str, table: str = "raw",
                source_file: str = "") -> int:
    if df.empty:
        return 0
    df = df.copy()
    df.columns = [_safe_col(c) for c in df.columns]   # sanitize — same as SQLite version
    if source_file:
        df["_source_file"] = source_file
    st.session_state[_key(sheet_name, table)] = df
    return len(df)


def write_cleaned(df: pd.DataFrame, sheet_name: str) -> int:
    return write_sheet(df, sheet_name, table="cleaned")


def write_table(df: pd.DataFrame, sheet_name: str, table: str) -> int:
    return write_sheet(df, sheet_name, table=table)


def read_table(sheet_name: str, table: str = "raw") -> pd.DataFrame:
    return st.session_state.get(_key(sheet_name, table), pd.DataFrame()).copy()


def session_drop(sheet_name: str, table: str) -> None:
    """Remove a table from the in-memory store (no error if absent)."""
    st.session_state.pop(_key(sheet_name, table), None)


def list_tables(sheet_name: str) -> list[str]:
    prefix = f"__db__{SHEET_DB_MAP.get(sheet_name, sheet_name.lower())}__"
    return [k.replace(prefix, "") for k in st.session_state if k.startswith(prefix)]


def all_db_status() -> dict[str, dict]:
    result = {}
    for sheet in SHEET_DB_MAP:
        tables = {}
        for tbl in list_tables(sheet):
            df = read_table(sheet, tbl)
            tables[tbl] = len(df)
        exists = bool(tables)
        result[sheet] = {"db_file": "in-memory", "exists": exists, "tables": tables}
    return result


# Legacy stubs — no-ops since there are no files
def db_path(sheet_name: str) -> Path:
    return DB_DIR / "in_memory.db"

def get_conn(sheet_name):
    raise RuntimeError("SQLite connections not used — data is in-memory only.")
