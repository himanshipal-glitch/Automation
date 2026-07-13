"""
Email sender for the profitability reports (Gmail SMTP).

Credentials are NEVER hardcoded — they're read from Streamlit secrets
(`.streamlit/secrets.toml`) or environment variables:

    [email]
    sender   = "you@recykal.com"          # a Gmail / Google-Workspace address
    app_password = "xxxx xxxx xxxx xxxx"   # a Google App Password (NOT the login pwd)
    recipients = ["a@recykal.com", "b@recykal.com"]   # default To-list (optional)

Google App Password: Google Account → Security → 2-Step Verification → App passwords.
"""
from __future__ import annotations
import os
import smtplib
from email.message import EmailMessage


def get_email_config() -> dict:
    """Read email config from Streamlit secrets, falling back to env vars.
    Returns {} if nothing is configured."""
    cfg = {}
    try:
        import streamlit as st
        if "email" in st.secrets:
            e = st.secrets["email"]
            cfg = {
                "sender": e.get("sender"),
                "app_password": e.get("app_password"),
                # Google Apps Script fallback (when the org disables app passwords):
                # deploy the provided script as a web app and put its URL + token here
                "gas_url": e.get("gas_url"),
                "gas_token": e.get("gas_token"),
                "recipients": list(e.get("recipients", [])),
                # optional: per-vertical recipient lists, e.g.
                #   [email.recipients_by_vertical]
                #   End Generator = ["metal.owner@recykal.com"]
                "recipients_by_vertical": dict(e.get("recipients_by_vertical", {})),
            }
    except Exception:
        pass
    # env-var fallback
    cfg.setdefault("sender", os.environ.get("REPORT_EMAIL_SENDER"))
    cfg.setdefault("app_password", os.environ.get("REPORT_EMAIL_APP_PASSWORD"))
    if not cfg.get("recipients"):
        env_r = os.environ.get("REPORT_EMAIL_RECIPIENTS", "")
        cfg["recipients"] = [r.strip() for r in env_r.split(",") if r.strip()]
    return cfg


def is_configured() -> bool:
    c = get_email_config()
    return bool((c.get("sender") and c.get("app_password"))          # SMTP route
                or (c.get("gas_url") and c.get("gas_token")))        # Apps Script route


def send_report(recipients: list[str], subject: str, body: str,
                attachment_bytes: bytes, filename: str,
                cfg: dict | None = None, html: str | None = None) -> tuple[bool, str]:
    """Send `attachment_bytes` (an .xlsx) to `recipients` via Gmail SMTP.
    If `html` is given it becomes the rich body (plain `body` stays as fallback).
    Returns (ok, message)."""
    cfg = cfg or get_email_config()
    recipients = [r.strip() for r in recipients if r and r.strip()]
    if not recipients:
        return False, "No recipients provided."

    # Apps Script route — used when no app password is available (org policy)
    if cfg.get("gas_url") and cfg.get("gas_token") and not cfg.get("app_password"):
        return _send_via_gas(recipients, subject, body, attachment_bytes,
                             filename, cfg, html)

    sender, pwd = cfg.get("sender"), cfg.get("app_password")
    if not (sender and pwd):
        return False, "Email not configured — add [email] sender & app_password to .streamlit/secrets.toml"

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    msg.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(sender, pwd)
            s.send_message(msg)
        return True, f"Sent to {len(recipients)} recipient(s)."
    except Exception as e:
        return False, f"Send failed: {e}"


def _send_via_gas(recipients, subject, body, attachment_bytes, filename,
                  cfg, html=None) -> tuple[bool, str]:
    """Send through the user's Google Apps Script web app (GmailApp.sendEmail) —
    no password leaves the machine; only a shared token authenticates the call."""
    import base64, requests
    try:
        r = requests.post(
            cfg["gas_url"],
            json={
                "token": cfg["gas_token"],
                "to": recipients,
                "subject": subject,
                "body": body,
                "html": html or "",
                "filename": filename,
                "attachment_b64": base64.b64encode(attachment_bytes).decode(),
            },
            timeout=60)
        if r.status_code == 200 and "ok" in r.text.lower():
            return True, f"Sent to {len(recipients)} recipient(s) (via Apps Script)."
        return False, f"Apps Script replied {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"Apps Script send failed: {e}"


# ── HTML body (the mail the team actually reads) ──────────────────────────────

def _inr(x) -> str:
    """Indian-style grouping: 3212254 → 32,12,254."""
    try:
        n = int(round(float(x)))
    except (TypeError, ValueError):
        return "-"
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) <= 3:
        return sign + s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return sign + ",".join(parts) + "," + tail


def _fmt_cell(metric: str, v) -> tuple[str, bool]:
    """Format one summary value → (text, is_percent_row). '-' for zero/blank."""
    import pandas as pd
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).lower() in ("nan", "none", ""):
        return "-", False
    m = metric.lower()
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v), False
    if "(%)" in m or "% to" in m:
        return f"{f:.2f}%", True
    if not f:
        return "-", False
    if "per kg" in m or "quantity" in m:
        return f"{f:,.2f}", False
    if "days" in m or "no. of" in m:
        return f"{f:,.0f}", False
    return _inr(f), False          # money


def materials_html(mat_df, month: str, share: float) -> str:
    """The 'top 5 materials' block the manual mails carry, same table styling."""
    if mat_df is None or len(mat_df) == 0:
        return ""
    head = "".join(
        f'<th style="background:#1a1a1a;color:#fff;padding:5px 10px;border:1px solid #444;'
        f'font-size:13px;">{h}</th>' for h in ["Material", "Qty", "Revenue", "Sum of Margin", "MTD %"])
    rows = []
    for _, r in mat_df.iterrows():
        is_total = str(r["Material"]) == "Total"
        w = "font-weight:bold;" if is_total else ""
        rows.append(
            f'<tr><td style="padding:4px 10px;border:1px solid #bbb;font-size:13px;{w}">{r["Material"]}</td>'
            f'<td style="padding:4px 10px;border:1px solid #bbb;text-align:right;font-size:13px;{w}">{_inr(r["Qty"])}</td>'
            f'<td style="padding:4px 10px;border:1px solid #bbb;text-align:right;font-size:13px;{w}">{_inr(r["Revenue"])}</td>'
            f'<td style="padding:4px 10px;border:1px solid #bbb;text-align:right;font-size:13px;{w}">{_inr(r["Sum of Margin"])}</td>'
            f'<td style="padding:4px 10px;border:1px solid #bbb;text-align:right;font-size:13px;{w}">{r["MTD %"]:.0f}%</td></tr>')
    note = (f'<p style="margin-top:16px;"><b>Note:</b> These top 5 materials contributed '
            f'<b>{share:.0f}%</b> of the total margin generated during <b>{month}</b>.</p>')
    return (note + '<table style="border-collapse:collapse;font-family:Calibri,Arial,sans-serif;">'
            f'<tr>{head}</tr>' + "".join(rows) + "</table>")


def summary_html(df, vertical: str, intro: str, regards: str = "Regards",
                 extra_html: str = "") -> str:
    """Email body: intro paragraph + the vertical's summary table styled like the
    manual's report mail (dark header row, blue italic % rows, Indian grouping)."""
    cols = [c for c in df.columns if c != "Metric"]
    head = "".join(
        f'<th style="background:#1a1a1a;color:#fff;padding:5px 10px;'
        f'border:1px solid #444;font-size:13px;">{c}</th>' for c in cols)
    rows_html = []
    for _, r in df.iterrows():
        metric = str(r["Metric"])
        tds, pct_row = [], False
        for c in cols:
            txt, is_pct = _fmt_cell(metric, r[c])
            pct_row = pct_row or is_pct
            tds.append(txt)
        sty = "color:#1f4fd8;font-style:italic;" if pct_row else ""
        cells = "".join(
            f'<td style="padding:4px 10px;border:1px solid #bbb;text-align:right;'
            f'font-size:13px;{sty}">{t}</td>' for t in tds)
        rows_html.append(
            f'<tr><td style="padding:4px 10px;border:1px solid #bbb;font-size:13px;'
            f'{sty}"><b>{metric}</b></td>{cells}</tr>')
    table = (
        '<table style="border-collapse:collapse;font-family:Calibri,Arial,sans-serif;">'
        f'<tr><th style="background:#1a1a1a;color:#fff;padding:5px 10px;border:1px solid #444;'
        f'font-size:13px;text-align:left;">{vertical}</th>{head}</tr>'
        + "".join(rows_html) + "</table>")
    return (
        '<div style="font-family:Calibri,Arial,sans-serif;font-size:14px;color:#222;">'
        f'<p>{intro}</p>{table}{extra_html}<p style="margin-top:14px;">{regards}</p></div>')
