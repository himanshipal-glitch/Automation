"""
Live Amazon × Recykal tracker reader.

The Amazon × Recykal "Stock" sheet is a Google Sheet that updates continuously,
so — unlike the other stores — it is read LIVE each run rather than uploaded.
It carries, per line, a PURCHASE side (what Recykal paid Amazon/Clicktech) and a
SALES side (the Recykal invoice). For Re-Commerce transactions AFTER the fixed
cutoff, this sheet is the driver: match (Invoice No + Category Name) to the Zoho
invoices for the shipment id, and take cost & revenue straight from here.

Access: the sheet must be shared "anyone with the link → Viewer" (or published),
so it can be read with a plain HTTPS CSV export — no credentials. Sheet id / gid
come from `[amazon_live]` in secrets, else the defaults below.
"""
from __future__ import annotations
import io
import os
import pandas as pd

# Defaults (overridable via secrets [amazon_live] sheet_id / gid)
DEFAULT_SHEET_ID = "1kL3rCeXZFEe7dMZtwiRbn0LkacOXFy6tYgN8gDp1usM"
DEFAULT_GID = "262170078"          # the "Stock" tab

# on-disk fallback snapshot so a network/permission blip never breaks a report
_SNAP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "persistent", "amazon_live_stock.parquet")


def _cfg():
    sid, gid = DEFAULT_SHEET_ID, DEFAULT_GID
    try:
        import streamlit as st
        a = st.secrets.get("amazon_live", None)
        if a:
            sid = a.get("sheet_id", sid) or sid
            gid = str(a.get("gid", gid) or gid)
    except Exception:
        pass
    return sid, gid


def _csv_url(sid: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"


def fetch_stock(sheet_id: str | None = None, gid: str | None = None,
                use_snapshot_on_fail: bool = True) -> tuple[pd.DataFrame, str]:
    """Read the live Stock tab → (DataFrame, status). Falls back to the last
    good on-disk snapshot if the live fetch fails. status ∈ {'live','snapshot',
    'empty'} plus a short note."""
    import requests
    sid = sheet_id or _cfg()[0]
    gid = gid or _cfg()[1]
    try:
        r = requests.get(_csv_url(sid, gid), timeout=25, allow_redirects=True)
        ct = r.headers.get("content-type", "")
        if r.status_code == 200 and "text/html" not in ct.lower():
            # read raw bytes as UTF-8 so the ₹ symbol / non-ASCII don't mojibake
            df = pd.read_csv(io.BytesIO(r.content), encoding="utf-8")
            df = _normalize(df)
            if not df.empty:
                try:
                    df.to_parquet(_SNAP, index=False)
                except Exception:
                    pass
                return df, "live"
        note = (f"live fetch failed (HTTP {r.status_code}"
                + ("; sheet not public — share 'anyone with the link'"
                   if "text/html" in ct.lower() else "") + ")")
    except Exception as e:
        note = f"live fetch error: {e}"
    if use_snapshot_on_fail:
        snap = load_snapshot()
        if not snap.empty:
            return snap, "snapshot (" + note + ")"
    return pd.DataFrame(), "empty (" + note + ")"


def load_snapshot() -> pd.DataFrame:
    for p in (_SNAP, _SNAP.replace(".parquet", ".pkl")):
        if os.path.exists(p):
            try:
                return pd.read_parquet(p) if p.endswith(".parquet") else pd.read_pickle(p)
            except Exception:
                pass
    return pd.DataFrame()


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Trim, drop fully-blank rows/cols, and drop the trailing '.1' pandas adds
    to the duplicated Invoice-Date column (sales side) — we address columns by
    their canonical names in the builder."""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(how="all").dropna(axis=1, how="all").copy()
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    return df.reset_index(drop=True)
