"""
Analytics Pro - upload a sheet, slice it, pivot it, chart it, export it.

Single-file Flask app.   python app.py
Needs: flask, pandas, openpyxl, requests
"""
import hashlib
import html
import io
import json
import os
import re
import threading
import warnings
from datetime import datetime

import pandas as pd
import requests
from flask import (Flask, Response, jsonify, redirect, render_template_string,
                   request, send_file, send_from_directory, url_for)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH", str(64 * 1024 * 1024)))

UPLOAD_DIR = os.environ.get("DASHBOARD_UPLOAD_DIR", "/tmp/dashboard_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATA_FILE_PATH = os.path.join(UPLOAD_DIR, "shared_data.pkl")
META_FILE_PATH = os.path.join(UPLOAD_DIR, "metadata.json")

# Google Apps Script Web App URL. Set APPS_SCRIPT_URL in the environment for Drive exports.
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "").strip()

RAW_ROW_LIMIT = 3000
PIVOT_ROW_LIMIT = 5000
CHART_MAX = 120
AGG_NAME = {"sum": "Sum", "count": "Count", "mean": "Avg"}
AGG_WORD = {"sum": "Sum", "count": "Count", "mean": "Average"}
DERIVED_FMT = {"Week of": "%d %b %y", "Month": "%b %Y"}
NON_ADDITIVE = re.compile(
    r"(^|[\s_\-])(id|no|num|number|code|sku|pin|pincode|phone|mobile|year|month|week|day|qtr|quarter)($|[\s_\-])", re.I)

_lock = threading.Lock()
_state = {"mtime": None, "df": None, "ctx": None}


def pick_date_col(cols):
    for c in ("Customized Sales Date", "Sale Date"):
        if c in cols:
            return c
    return next((c for c in cols if "date" in c.lower()), "")


def detect_columns(df):
    cols = list(df.columns)
    low = {c: c.lower() for c in cols}
    date = pick_date_col(cols)
    if date and not pd.api.types.is_datetime64_any_dtype(df[date]):
        date = ""

    num = df.select_dtypes(include="number").columns.tolist()

    qty = next(
        (c for c in cols if any(k in low[c] for k in ("qty", "quantity", "volume", "vol"))),
        ""
    )
    seg2 = next(
        (c for c in cols if any(k in low[c] for k in ("seg2", "segment2", "segment 2"))),
        ""
    )

    return {
        "date": date,
        "spc": next((c for c in cols if "spc" in low[c] and "name" in low[c]), ""),
        "seg": next((c for c in cols if "seg1" in low[c] or "segment 1" in low[c] or "segment1" in low[c]), ""),
        "seg2": seg2,
        "fam": next((c for c in cols if "family" in low[c]), ""),
        "qty": qty,
        "num_cols": num,
    }


def prepare_df(df):
    df.columns = [str(c).strip() for c in df.columns]
    d = pick_date_col(list(df.columns))
    if d and not pd.api.types.is_numeric_dtype(df[d]):
        df[d] = pd.to_datetime(df[d], errors="coerce", dayfirst=True)

    c = detect_columns(df)
    for key in ("spc", "seg", "seg2", "fam"):
        col = c[key]
        if col:
            s = df[col]
            df[col] = s.astype(object).where(s.isna(), s.astype(str))
    return df


def derived_names(columns, date):
    if not date:
        return []
    return [n for n in ("Week of", "Month") if n not in columns]


def week_start(s):
    return s.dt.normalize() - pd.to_timedelta(s.dt.weekday, unit="D")


def opts(names, hint="", checked=()):
    return [{"name": str(n), "hint": hint, "checked": n in checked} for n in names]


def build_context(df):
    c = detect_columns(df)
    cols = list(df.columns)
    num = c["num_cols"]

    lists = {k: (sorted(df[c[k]].dropna().unique().tolist()) if c[k] else [])
             for k in ("spc", "seg", "seg2")}
    keys = [(k, c[k]) for k in ("spc", "seg", "seg2") if c[k]]
    mapping = []
    if keys:
        m = df[[col for _, col in keys]].fillna("N/A").drop_duplicates()
        m.columns = [k for k, _ in keys]
        mapping = m.to_dict(orient="records")

    dmin = dmax = None
    weeks, months = [], []
    if c["date"]:
        s = df[c["date"]].dropna()
        if len(s):
            dmin, dmax = s.min(), s.max()
            for w in sorted(week_start(s).drop_duplicates())[-160:]:
                e = w + pd.Timedelta(days=6)
                weeks.append({
                    "key": w.strftime("%Y-%m-%d"),
                    "label": f"W{w.isocalendar()[1]:02d}",
                    "range": f"{w.day} {w:%b}" + (f" – {e.day} {e:%b}" if e.month != w.month else f"–{e.day}"),
                    "year": f"{w:%y}",
                })
            for mth in sorted((s.dt.year * 100 + s.dt.month).unique())[-60:]:
                y, mo = divmod(int(mth), 100)
                months.append({"key": f"{y:04d}-{mo:02d}", "label": f"{pd.Timestamp(y, mo, 1):%b} {y}"})

    non_num = [x for x in cols if x not in num and x != c["date"]]
    default_x = next((c[k] for k in ("spc", "seg", "seg2") if c[k]), non_num[0] if non_num else cols[0])

    default_y = "Tentative DP" if "Tentative DP" in num else (c["qty"] if c["qty"] in num else num[0] if num else "")
    if c["qty"] and c["qty"] not in num:
        num = num + [c["qty"]]

    x_opts = [{"name": n, "hint": "date", "checked": False} for n in derived_names(cols, c["date"])]
    for col in cols:
        hint = "date" if col == c["date"] else ("number" if col in num else "")
        x_opts.append({"name": col, "hint": hint, "checked": col == default_x})

    def label(d):
        return f"{d.day:02d} {d:%b %Y}" if d is not None else "N/A"

    boot = {
        "map": mapping,
        "dmin": dmin.strftime("%Y-%m-%d") if dmin is not None else "",
        "dmax": dmax.strftime("%Y-%m-%d") if dmax is not None else "",
        "all": f"All time · {label(dmin)} – {label(dmax)}" if dmin is not None else "All records",
    }

    return {
        **c,
        "dmin": dmin,
        "dmax": dmax,
        "weeks": weeks,
        "months": months,
        "spc_opts": opts(lists["spc"]),
        "seg_opts": opts(lists["seg"]),
        "seg2_opts": opts(lists["seg2"]),
        "qty_col": c["qty"],
        "x_opts": x_opts,
        "y_opts": opts(num, "number", {default_y}),
        "boot_json": json.dumps(boot).replace("<", "\\u003c"),
        "range_label": f"{label(dmin)} – {label(dmax)}" if dmin is not None else "",
    }


def get_state():
    try:
        mtime = os.path.getmtime(DATA_FILE_PATH)
    except OSError:
        return None
    with _lock:
        if _state["mtime"] != mtime:
            try:
                df = pd.read_pickle(DATA_FILE_PATH)
            except Exception:
                return None
            _state.update(mtime=mtime, df=df, ctx=build_context(df))
        return dict(_state)


def save_data(df):
    df = prepare_df(df)
    tmp = DATA_FILE_PATH + ".tmp"
    df.to_pickle(tmp)
    os.replace(tmp, DATA_FILE_PATH)
    with open(META_FILE_PATH, "w") as fh:
        json.dump({"upload_time": datetime.now().strftime("%d %b %Y, %I:%M %p")}, fh)


def get_upload_time():
    try:
        with open(META_FILE_PATH) as fh:
            return json.load(fh).get("upload_time", "")
    except (OSError, ValueError):
        return ""


# formatting
_GROUP = re.compile(r"(\d)(?=(\d\d)+$)")


def format_indian_number(x, dec=0):
    if x is None or (isinstance(x, str) and x == ""):
        return ""
    try:
        if pd.isna(x):
            return ""
        v = round(float(x), dec)
    except (ValueError, TypeError, OverflowError):
        return html.escape(str(x))
    neg = v < 0
    v = abs(v)
    s = str(int(v))
    if len(s) > 3:
        s = _GROUP.sub(r"\1,", s[:-3]) + "," + s[-3:]
    if dec:
        s += "." + f"{v:.{dec}f}".split(".")[1]
    return f"-{s}" if neg and v else s


def format_avg(x):
    try:
        return format_indian_number(x, 2 if abs(float(x)) < 100 else 0)
    except (TypeError, ValueError):
        return ""


def format_plain(v):
    if v is None or pd.isna(v):
        return ""
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else str(v)
    except (TypeError, ValueError):
        return html.escape(str(v))


def format_pct(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return ""
    if x != x:
        return ""
    if round(x, 1) > 0:
        return f'<span class="pct-positive">↑ {x:.1f}%</span>'
    if round(x, 1) < 0:
        return f'<span class="pct-negative">↓ {abs(x):.1f}%</span>'
    return '<span class="pct-neutral">–</span>'


def format_pct_share(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return ""
    if x != x:
        return ""
    x = max(0.0, min(100.0, x))
    if x >= 50:
        color = "#1f8a3c"
        bg = "rgba(31,138,60,0.12)"
    elif x >= 25:
        color = "#0071e3"
        bg = "rgba(0,113,227,0.12)"
    elif x >= 10:
        color = "#5f6f8f"
        bg = "rgba(95,111,143,0.10)"
    else:
        color = "#7d8594"
        bg = "rgba(125,133,148,0.08)"
    return (
        f'<span class="pct-share" '
        f'style="color:{color};background:{bg};font-weight:700;">{x:.1f}%</span>'
    )


def col_cells(s, fmt=None, esc=True):
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.dt.strftime(fmt or "%d-%b-%y").fillna("").tolist()
    if pd.api.types.is_numeric_dtype(s):
        return [format_plain(v) for v in s]
    out = ["" if pd.isna(v) else str(v) for v in s]
    return [html.escape(v) for v in out] if esc else out


def num_cells(s, additive=True):
    if not additive:
        return [format_plain(v) for v in s]
    dec = 2 if (pd.api.types.is_float_dtype(s) and s.dropna().mod(1).ne(0).any()) else 0
    return [format_indian_number(v, dec) for v in s]


def render_table(headers, columns, css, numeric, nidx, foot=None, total_cols=()):
    def cls(i, base=""):
        out = [base] if base else []
        if i in numeric:
            out.append("num")
        if i in total_cols:
            out.append("total-col")
        return f' class="{" ".join(out)}"' if out else ""

    head = "".join(f"<th{cls(i)}>{html.escape(h)}</th>" for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f"<td{cls(i)}>{v}</td>" for i, v in enumerate(row)) + "</tr>"
                   for row in zip(*columns))
    tfoot = ""
    if foot:
        tfoot = "<tfoot><tr>" + "".join(f"<td{cls(i)}>{v}</td>" for i, v in enumerate(foot)) + "</tr></tfoot>"
    return (f'<table class="excel-table {css}" data-nidx="{nidx}"><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody>{tfoot}</table>")


def empty_block(title, msg=""):
    return (f'<div class="empty"><svg class="ic"><use href="#i-chart"/></svg>'
            f"<h3>{html.escape(title)}</h3><p>{html.escape(msg)}</p></div>")


def nice_join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " & " + items[-1]


def pivot_title(ys, aggs, xs):
    y = nice_join(ys[:3]) + (f" +{len(ys) - 3}" if len(ys) > 3 else "")
    x = " › ".join(xs[:3]) + (f" +{len(xs) - 3}" if len(xs) > 3 else "")
    return f"{y} by {x}"


def slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:80] or "Report"


def num_or_none(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else round(f, 2)


def parse_date(s):
    if not s:
        return None
    t = pd.to_datetime(s, errors="coerce")
    return None if pd.isna(t) else t


def clean_list(p, key, allowed):
    seen, out = set(), []
    for v in p.getlist(key):
        if v in allowed and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def apply_filters(df, ctx, p):
    mask = None

    def add(m):
        nonlocal mask
        mask = m if mask is None else (mask & m)

    dc = ctx["date"]
    if dc:
        d = df[dc]
        start, end = parse_date(p.get("start_date")), parse_date(p.get("end_date"))
        if start is not None:
            add(d >= start)
        if end is not None:
            add(d < end + pd.Timedelta(days=1))
        weeks = pd.to_datetime(p.getlist("weeks"), errors="coerce")
        if len(weeks):
            add(week_start(d).isin(weeks.dropna()))
        months = [int(m.replace("-", "")) for m in p.getlist("months") if re.fullmatch(r"\d{4}-\d{2}", m)]
        if months:
            add((d.dt.year * 100 + d.dt.month).isin(months))

    for key, field in (("spc", "spc_filters"), ("seg", "seg1_filters"), ("seg2", "seg2_filters")):
        col, vals = ctx[key], p.getlist(field)
        if col and vals:
            add(df[col].isin(vals))
    return df if mask is None else df[mask]


def filter_pills(ctx, p):
    out = []
    for key, field, label in (("spc", "spc_filters", "SPC"), ("seg", "seg1_filters", "Segment 1"), ("seg2", "seg2_filters", "Segment 2")):
        vals = p.getlist(field)
        if ctx[key] and vals:
            out.append([label, ", ".join(vals[:4]) + (f" +{len(vals) - 4}" if len(vals) > 4 else "")])
    return out


def fmt_d(t):
    return f"{t.day:02d} {t:%b %Y}"


def period_text(ctx, p):
    if not ctx["date"]:
        return "All records"
    label = re.sub(r"\s+", " ", (p.get("period_label") or "")).strip()[:40]
    weeks = sorted(t for t in pd.to_datetime(p.getlist("weeks"), errors="coerce") if pd.notna(t))
    if weeks:
        names = [f"W{w.isocalendar()[1]:02d}" for w in weeks]
        shown = ", ".join(names[:6]) + (f" +{len(names) - 6} more" if len(names) > 6 else "")
        return (f"{'Week' if len(names) == 1 else 'Weeks'} {shown} · "
                f"{fmt_d(weeks[0])} – {fmt_d(weeks[-1] + pd.Timedelta(days=6))}")
    months = sorted(m for m in p.getlist("months") if re.fullmatch(r"\d{4}-\d{2}", m))
    if months:
        names = [pd.Timestamp(f"{m}-01").strftime("%b %Y") for m in months]
        return "Months " + ", ".join(names[:5]) + (f" +{len(names) - 5} more" if len(names) > 5 else "")
    start, end = parse_date(p.get("start_date")), parse_date(p.get("end_date"))
    lo = start if start is not None else ctx["dmin"]
    hi = end if end is not None else ctx["dmax"]
    if lo is None or hi is None:
        return label or "All time"
    rng = fmt_d(lo) if lo == hi else f"{fmt_d(lo)} – {fmt_d(hi)}"
    if start is None and end is None:
        return f"All time · {rng}"
    return f"{label} · {rng}" if label else rng


def spc_review_data(dff, ctx, value_col):
    if not ctx.get("spc") or not value_col or value_col not in dff.columns:
        return {"pros": [], "cons": []}
    s = dff[[ctx["spc"], value_col]].dropna()
    if s.empty:
        return {"pros": [], "cons": []}
    total = s[value_col].sum()
    if total == 0:
        return {"pros": [], "cons": []}
    g = s.groupby(ctx["spc"], observed=True)[value_col].sum().reset_index()
    g.columns = ["spc", "value"]
    g["share"] = (g["value"] / total) * 100
    g = g.sort_values(["value", "share"], ascending=False).reset_index(drop=True)

    return {
        "pros": [{"label": r["spc"], "value": format_indian_number(r["value"]), "share": f"{r['share']:.1f}%"} for _, r in g.head(5).iterrows()],
        "cons": [{"label": r["spc"], "value": format_indian_number(r["value"]), "share": f"{r['share']:.1f}%"} for _, r in g.tail(5).sort_values(["value", "share"], ascending=True).iterrows()],
    }


def build_view(state, p, want_export=False):
    df, ctx = state["df"], state["ctx"]
    mode = "raw" if p.get("view_mode") == "raw" else "pivot"
    dff = apply_filters(df, ctx, p)
    default_value = "Tentative DP" if "Tentative DP" in dff.columns else (ctx.get("qty") if ctx.get("qty") in dff.columns else dff.select_dtypes(include="number").columns.tolist()[0] if len(dff.select_dtypes(include="number").columns) else "")
    chosen_value = p.get("value_cols") or [default_value]
    value_col = chosen_value[0] if chosen_value and chosen_value[0] else default_value
    base = {
        "period": period_text(ctx, p),
        "filters": filter_pills(ctx, p),
        "spc_review": spc_review_data(dff, ctx, value_col),
    }
    if mode == "raw":
        return build_raw(dff, ctx, base, want_export)
    return build_pivot(dff, ctx, p, base, want_export)


def empty_payload(base, title, head, msg):
    return {
        **base,
        "title": title,
        "table_html": empty_block(head, msg),
        "status": "0 results",
        "kpis": [],
        "chart": None,
        "spc_review": {"pros": [], "cons": []},
    }


def build_raw(dff, ctx, base, want_export):
    n = len(dff)
    title = f"Raw data · {format_indian_number(n)} record{'s' if n != 1 else ''}"
    if n == 0:
        return empty_payload(base, title, "No matching data", "Try widening the period or clearing a filter."), None, 200

    shown = dff.head(RAW_ROW_LIMIT)
    cols = list(shown.columns)
    columns, numeric, additive = [], set(), {}
    for i, c in enumerate(cols):
        s = shown[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            columns.append(col_cells(s))
        elif pd.api.types.is_numeric_dtype(s):
            add = not NON_ADDITIVE.search(str(c)) and not pd.api.types.is_bool_dtype(s)
            additive[i] = add
            numeric.add(i)
            columns.append(num_cells(s, add))
        else:
            columns.append(col_cells(s))

    foot = []
    for i, c in enumerate(cols):
        if i == 0:
            foot.append(f"Total · {format_indian_number(n)} rows")
        elif additive.get(i):
            sm = dff[c].sum()
            dec = 2 if (pd.api.types.is_float_dtype(dff[c]) and dff[c].dropna().mod(1).ne(0).any()) else 0
            foot.append(format_indian_number(sm, dec))
        else:
            foot.append("")

    kpis = [{"label": "Records", "value": format_indian_number(n), "sub": "in this view", "cols": []}]
    for i, c in enumerate(cols):
        if additive.get(i) and len(kpis) < 5:
            kpis.append({"label": str(c), "value": format_indian_number(dff[c].sum()), "sub": "Total", "cols": [i]})

    status = (f"{format_indian_number(n)} rows" if n <= RAW_ROW_LIMIT else
              f"Showing first {format_indian_number(RAW_ROW_LIMIT)} of {format_indian_number(n)} rows · Excel has all")
    payload = {**base, "title": title, "status": status, "kpis": kpis, "chart": None,
               "table_html": render_table([str(c) for c in cols], columns, "raw", numeric, 1, foot)}
    export = {"df": dff, "nidx": 1, "fmts": {}, "footer": False} if want_export else None
    return payload, export, 200


def metric_display_name(y, a):
    if a == "sum":
        return y
    return f"{y} {AGG_NAME[a]}" if AGG_NAME[a] != "Sum" else y


def build_pivot(dff, ctx, p, base, want_export):
    cols_set = set(dff.columns)
    dc = ctx["date"]
    derived_ok = set(derived_names(cols_set, dc))
    idx_cols = clean_list(p, "index_cols", cols_set | derived_ok)
    ycols = [c for c in clean_list(p, "value_cols", set(ctx["num_cols"])) if c not in idx_cols]
    aggs = [a for a in ("sum", "count", "mean") if a in p.getlist("agg_funcs")]

    if not idx_cols or not ycols or not aggs:
        return {"error": "Pick at least one X column, one Y column and one measure."}, None, 200

    share, growth = p.get("share") == "1", p.get("growth") == "1"
    row_total = p.get("row_total") == "1"
    title = pivot_title(ycols, aggs, idx_cols)
    if dff.empty:
        return empty_payload(base, title, "No matching data", "Try widening the period or clearing a filter."), None, 200

    derived = {}
    if dc:
        d = dff[dc]
        if "Week of" in idx_cols and "Week of" in derived_ok:
            derived["Week of"] = week_start(d)
        if "Month" in idx_cols and "Month" in derived_ok:
            derived["Month"] = d.dt.normalize() - pd.to_timedelta(d.dt.day - 1, unit="D")

    need = [c for c in dict.fromkeys(idx_cols + ycols) if c not in derived]
    sub = dff[need].assign(**derived)

    g = sub.groupby(idx_cols, observed=True, sort=True)[ycols].agg(aggs)
    if g.empty:
        return empty_payload(base, title, "No groups to show", "The chosen X columns only contain empty values."), None, 200

    res = g.index.to_frame(index=False)
    vals = g.reset_index(drop=True)
    metas = [("idx", "")] * len(idx_cols)

    def put(name, series, meta):
        res[name] = series
        metas.append(meta)

    for y in ycols:
        for a in aggs:
            name = metric_display_name(y, a)
            col = vals[(y, a)].astype(float)
            put(name, col.to_numpy(), ("metric", a))
            if share and a != "mean":
                tot = col.sum()
                put(f"{name} Share", (col / tot * 100).to_numpy() if tot else 0.0, ("pct", a))
            if growth:
                prev = col.shift()
                put(f"{name} Growth", ((col - prev) / prev.where(prev != 0) * 100).to_numpy(), ("pct", a))

    total_cols = {}
    if row_total and len(ycols) > 1:
        for a in ("sum", "count"):
            if a in aggs:
                parts = [metric_display_name(y, a) for y in ycols]
                name = f"Total {AGG_NAME[a]}"
                put(name, res[parts].sum(axis=1).to_numpy(), ("total", a))
                total_cols[name] = parts

    valid = sub.dropna(subset=idx_cols)
    foot = {}
    for y in ycols:
        for a in aggs:
            s = valid[y]
            foot[metric_display_name(y, a)] = {"sum": s.sum, "count": s.count, "mean": s.mean}[a]()
    for name, parts in total_cols.items():
        foot[name] = sum(foot[x] for x in parts)

    headers = list(res.columns)
    n = len(res)
    fmt_first = lambda c: DERIVED_FMT.get(c)
    labels_all = [" · ".join(parts) for parts in zip(*[
        col_cells(res[c], fmt_first(c), esc=False) for c in idx_cols])]

    shown = res.head(PIVOT_ROW_LIMIT)
    columns, numeric, foot_cells = [], set(), []
    for i, h in enumerate(headers):
        s, (kind, a) = shown[h], metas[i]
        if kind == "idx":
            columns.append(col_cells(s, fmt_first(h)))
            foot_cells.append("Grand total" if i == 0 else "")
        elif kind == "pct":
            if h.endswith("Share"):
                columns.append([format_pct_share(v) for v in s])
            else:
                columns.append([format_pct(v) for v in s])
            foot_cells.append("100%" if h.endswith("Share") else "")
            numeric.add(i)
        else:
            f = format_avg if a == "mean" else format_indian_number
            columns.append([f(v) for v in s])
            foot_cells.append(f(foot[h]))
            numeric.add(i)

    total_idx = {i for i, m in enumerate(metas) if m[0] == "total"}
    table_html = render_table(headers, columns, "pivot", numeric, len(idx_cols), foot_cells, total_idx)

    metric_idx = [i for i, m in enumerate(metas) if m[0] == "metric"]
    kpis = []
    for i in metric_idx[:6]:
        h, a = headers[i], metas[i][1]
        f = format_avg if a == "mean" else format_indian_number
        top = int(res.iloc[:, i].to_numpy().argmax()) if n else 0
        group = [i] + [j for j, m in enumerate(metas) if m[0] == "pct" and headers[j].startswith(h + " ")]
        kpis.append({
            "label": h,
            "value": f(foot[h]),
            "sub": "Top · " + (labels_all[top][:26] + ("…" if len(labels_all[top]) > 26 else "")),
            "cols": group,
        })
    kpis.append({"label": "Groups", "value": format_indian_number(n),
                 "sub": " › ".join(idx_cols)[:30], "cols": list(range(len(idx_cols)))})

    sel, note = list(range(n)), ""
    is_time = pd.api.types.is_datetime64_any_dtype(res[idx_cols[0]])
    if n > CHART_MAX and metric_idx:
        if is_time:
            sel, note = list(range(n - CHART_MAX, n)), f"Showing the latest {CHART_MAX} of {format_indian_number(n)} groups"
        else:
            sel = sorted(res.iloc[:, metric_idx[0]].nlargest(CHART_MAX).index.tolist())
            note = f"Showing the top {CHART_MAX} of {format_indian_number(n)} groups"

    chart = {
        "labels": [labels_all[i] for i in sel],
        "series": [{"name": headers[i], "agg": metas[i][1], "col": i,
                    "values": [num_or_none(v) for v in res.iloc[sel, i]]} for i in metric_idx],
        "x_title": " › ".join(idx_cols), "is_time": bool(is_time), "note": note,
    }

    status = (f"{format_indian_number(n)} groups" if n <= PIVOT_ROW_LIMIT else
              f"Showing first {format_indian_number(PIVOT_ROW_LIMIT)} of {format_indian_number(n)} groups · Excel has all")
    payload = {**base, "title": title, "status": status, "table_html": table_html, "kpis": kpis, "chart": chart}

    export = None
    if want_export:
        exp = res.copy()
        for c in idx_cols:
            if pd.api.types.is_datetime64_any_dtype(exp[c]):
                exp[c] = exp[c].dt.strftime(fmt_first(c) or "%d-%b-%y")
        row = {h: None for h in headers}
        row[headers[0]] = "GRAND TOTAL"
        for h, v in foot.items():
            row[h] = v
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            exp = pd.concat([exp, pd.DataFrame([row], columns=headers)], ignore_index=True)
        fmts = {}
        for i, (kind, a) in enumerate(metas):
            if kind == "pct":
                fmts[i] = '0.0"%"'
            elif kind in ("metric", "total"):
                fmts[i] = "#,##0.00" if a == "mean" else "#,##0"
        export = {"df": exp, "nidx": len(idx_cols), "fmts": fmts, "footer": True}
    return payload, export, 200


def write_excel(payload, export):
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    df, hdr = export["df"], 5
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl", datetime_format="DD-MMM-YY") as xw:
        df.to_excel(xw, index=False, sheet_name="Report", startrow=hdr - 1)
        ws = xw.sheets["Report"]
        ws.sheet_view.showGridLines = False
        ws["A1"], ws["A2"] = payload["title"], f"Period: {payload['period']}"
        pills = "  |  ".join(f"{k}: {v}" for k, v in payload.get("filters", []))
        ws["A3"] = f"Filters: {pills}" if pills else "Filters: none"
        ws["A1"].font = Font(size=16, bold=True, color="1D1D1F")
        ws["A2"].font = Font(size=11, bold=True, color="0071E3")
        ws["A3"].font = Font(size=10, color="86868B")
        ncols, nrows = len(df.columns), len(df)
        nidx = export["nidx"]
        blue, line = PatternFill("solid", fgColor="0071E3"), Side(style="thin", color="0071E3")
        for c in range(1, ncols + 1):
            cell = ws.cell(row=hdr, column=c)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = blue
            cell.alignment = Alignment(horizontal="left" if c <= nidx else "right", vertical="center", wrap_text=True)
        ws.row_dimensions[hdr].height = 26
        for c, fmt in export["fmts"].items():
            for r in range(hdr + 1, hdr + 1 + nrows):
                cell = ws.cell(row=r, column=c + 1)
                cell.number_format = fmt
                cell.alignment = Alignment(horizontal="right")
        if export["footer"] and nrows:
            fill = PatternFill("solid", fgColor="E8F1FD")
            for c in range(1, ncols + 1):
                cell = ws.cell(row=hdr + nrows, column=c)
                cell.font = Font(bold=True, color="1D1D1F")
                cell.fill = fill
                cell.border = Border(top=line)
        for c in range(ncols):
            sample = [len(str(v)) for v in df.iloc[:200, c].tolist()]
            ws.column_dimensions[get_column_letter(c + 1)].width = min(
                44, max(len(str(df.columns[c])) * 0.95, max(sample, default=0)) + 3)
        ws.freeze_panes = ws.cell(row=hdr + 1, column=max(nidx, 1) + 1)
    out.seek(0)
    return out


@app.route("/save-to-drive", methods=["POST"])
def save_to_drive():
    import base64
    try:
        if not APPS_SCRIPT_URL:
            return jsonify({"error": "Google Drive export is not configured."}), 400
        st = get_state()
        if st is None:
            return jsonify({"error": "No data available."}), 400
        payload, export, _ = build_view(st, request.form, want_export=True)
        if export is None:
            return jsonify({"error": "Nothing to export"}), 400
        out = write_excel(payload, export)

        encoded_file = base64.b64encode(out.read()).decode("utf-8")
        payload_data = {
            "fileName": f"{slug(payload['title'])}.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "fileData": encoded_file,
        }
        res = requests.post(APPS_SCRIPT_URL, json=payload_data, timeout=30)
        return jsonify(res.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.get("/")
def home():
    st = get_state()
    if st is None:
        return render_template_string(UPLOAD_HTML, error=None)
    return render_template_string(WORKSPACE_HTML, ctx=st["ctx"], upload_time=get_upload_time())


@app.get("/upload")
def upload_page():
    return render_template_string(UPLOAD_HTML, error=None)


@app.post("/dashboard")
def dashboard():
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect(url_for("home"))
    name = f.filename.lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(f)
        elif name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(f)
        else:
            raise ValueError("unsupported file type, please use .xlsx, .xls or .csv")
        if df.empty:
            raise ValueError("the file has no rows")
        save_data(df)
    except Exception as exc:
        return render_template_string(UPLOAD_HTML, error=f"Couldn't read that file: {exc}"), 400
    return redirect(url_for("home"))


@app.post("/calculate")
def calculate():
    st = get_state()
    if st is None:
        return jsonify({"error": "No data available."}), 400
    try:
        payload, _, code = build_view(st, request.form)
    except Exception as exc:
        return jsonify({"error": f"An error occurred: {exc}"}), 500
    return jsonify(payload), code


@app.get("/download")
def download():
    st = get_state()
    if st is None:
        return "No data to download", 400
    try:
        payload, export, _ = build_view(st, request.args, want_export=True)
        if export is None:
            return payload.get("error", "Nothing to export"), 400
        out = write_excel(payload, export)
    except Exception as exc:
        return f"Export failed: {exc}", 500
    return send_file(out, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     download_name=f"{slug(payload['title'])}.xlsx", as_attachment=True)


@app.get("/assets/app.css")
def asset_css():
    return Response(APP_CSS, mimetype="text/css", headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/assets/app.js")
def asset_js():
    return Response(APP_JS, mimetype="application/javascript",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.context_processor
def inject_assets():
    return {"asset_v": ASSET_VERSION, "sprite": SPRITE}


SPRITE = """
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<symbol id="i-chev" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></symbol>
<symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></symbol>
<symbol id="i-upload" viewBox="0 0 24 24"><path d="M12 16V4m0 0L8 8m4-4l4 4M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3"/></symbol>
<symbol id="i-share" viewBox="0 0 24 24"><path d="M12 15V3m0 0L8 7m4-4l4 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7"/></symbol>
<symbol id="i-sliders" viewBox="0 0 24 24"><path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/></symbol>
<symbol id="i-image" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.5"/><path d="M21 16l-5-5-8 8"/></symbol>
<symbol id="i-sheet" viewBox="0 0 24 24"><path d="M7 3h7l5 5v11a2 2 0 01-2 2H7a2 2 0 01-2-2V5a2 2 0 012-2z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></symbol>
<symbol id="i-chart" viewBox="0 0 24 24"><path d="M4 20V10M10 20V4M16 20v-7M2 20h20"/></symbol>
<symbol id="i-reset" viewBox="0 0 24 24"><path d="M3 12a9 9 0 109-9 9 9 0 00-6.4 2.6L3 8"/><path d="M3 3v5h5"/></symbol>
<symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></symbol>
<symbol id="i-moon" viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/></symbol>
<symbol id="i-auto" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 010 18z" fill="currentColor"/></symbol>
<symbol id="i-glass" viewBox="0 0 24 24"><path d="M12 3s6 6.2 6 10.5a6 6 0 01-12 0C6 9.2 12 3 12 3z"/></symbol>
<symbol id="i-cal" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="3.5"/><path d="M8 3v4M16 3v4M3 10h18"/></symbol>
<symbol id="i-table" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 10h18M9 10v10"/></symbol>
<symbol id="i-x" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></symbol>
</defs></svg>
"""

HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="{{ url_for('favicon') }}" type="image/x-icon">
<script>(function(){try{var d=document.documentElement,t=localStorage.getItem('ap-theme'),g=localStorage.getItem('ap-glass');
if(t==='light'||t==='dark')d.dataset.theme=t;if(g)d.style.setProperty('--glass',g);}catch(e){}})();</script>
<link rel="stylesheet" href="/assets/app.css?v={{ asset_v }}">
<script src="/assets/app.js?v={{ asset_v }}" defer></script>"""

MACROS = """
{% macro controls(layout=False) %}
<div class="nav-right">
  <div class="menu-wrap" id="glassWrap">
    <button type="button" class="icon-btn" id="glassBtn" aria-label="Liquid Glass transparency" aria-expanded="false" title="Liquid Glass"><svg class="ic"><use href="#i-glass"/></svg></button>
    <div class="popover" id="glassPop">
      <div class="pop-title">Liquid Glass</div>
      <input type="range" id="glassRange" min="30" max="96" step="1" aria-label="Glass transparency">
      <div class="pop-scale"><span>Clear</span><span>Frosted</span></div>
    </div>
  </div>

  <div class="net-status" id="netStatus" aria-live="polite" title="Connection status">
    <span class="net-dot" id="netDot"></span>
    <span class="net-text" id="netText">Online</span>
    <span class="net-sep"></span>
    <span class="net-text" id="netPing">Ping 0ms</span>
    <span class="net-sep"></span>
    <span class="net-text" id="netSpeed">Up 0MB/s · Down 0MB/s</span>
  </div>

  <button type="button" class="icon-btn" id="saveDriveBtn" title="Save Master Report to Google Drive" aria-label="Save to Google Drive">☁️</button>

  <div class="seg seg-icons" id="themeSeg" data-n="2" role="radiogroup" aria-label="Appearance">
    <span class="seg-thumb"></span>
    <input type="radio" name="theme" id="th_light" value="light"><label for="th_light" title="Light" aria-label="Light"><svg class="ic"><use href="#i-sun"/></svg></label>
    <input type="radio" name="theme" id="th_dark" value="dark"><label for="th_dark" title="Dark" aria-label="Dark"><svg class="ic"><use href="#i-moon"/></svg></label>
  </div>

  {% if layout %}
  <label class="ios-switch" title="Switch between desktop and mobile layout">
    <span class="sw-text">Mobile</span>
    <input type="checkbox" id="mobileSwitch" role="switch"><span class="track"><span class="knob"></span></span>
  </label>
  <a class="icon-btn" href="/upload" aria-label="Upload new file" title="Upload new file"><svg class="ic"><use href="#i-upload"/></svg></a>
  {% endif %}
</div>
{% endmacro %}
"""

UPLOAD_HTML = """<!doctype html>
<html lang="en"><head><title>Analytics Pro</title>""" + HEAD + """</head>
<body class="upload-page">""" + MACROS + """
{{ sprite|safe }}
<header class="nav glass"><span class="brand"><span class="brand-mark"></span>Analytics Pro</span>{{ controls() }}</header>
<main class="upload-wrap">
  <h1 class="hero-title">Analytics Engine.</h1>
  <p class="hero-sub">Upload your sales data to launch the workspace.</p>
  <form class="upload-card glass" action="/dashboard" method="post" enctype="multipart/form-data" id="uploadForm">
    {% if error %}<div class="alert" role="alert">{{ error }}</div>{% endif %}
    <label class="dropzone" id="dropzone" for="file">
      <svg class="ic ic-lg"><use href="#i-upload"/></svg>
      <span class="dz-title" id="dzTitle">Choose a file</span>
      <span class="dz-sub" id="dzSub">or drag it here · .xlsx, .xls, .csv</span>
    </label>
    <input id="file" class="sr-only" type="file" name="file" accept=".xlsx,.xls,.csv" required>
    <button type="submit" class="btn-primary block" id="launchBtn" disabled>Launch workspace</button>
  </form>
</main>
</body></html>"""

WORKSPACE_HTML = """<!doctype html>
<html lang="en"><head><title>Analytics Pro</title>""" + HEAD + """</head>
<body>
<script>(function(){var m=null;try{m=localStorage.getItem('ap-mobile')}catch(e){}
var mob=m===null?innerWidth<=768:m==='1';document.body.classList.add(mob?'mobile-mode':'desktop-mode');
if(mob)document.body.classList.add('sidebar-collapsed');})();</script>
""" + MACROS + """
{{ sprite|safe }}

{% macro acc(title, badge, open=False, structural=False) %}
<section class="acc{% if open %} open{% endif %}"{% if structural %} data-structural{% endif %}>
  <button type="button" class="acc-head" aria-expanded="{{ 'true' if open else 'false' }}">
    <span class="acc-title">{{ title }}</span>
    <span class="badge" data-badge-for="{{ badge }}" hidden>0</span>
    <svg class="ic chev"><use href="#i-chev"/></svg>
  </button>
  <div class="acc-panel"><div class="acc-inner"><div class="acc-body">{{ caller() }}</div></div></div>
</section>
{% endmacro %}

{% macro checklist(name, items, ordered=False) %}
{% set searchable = items|length > 7 %}
<div class="tools{% if not searchable %} end{% endif %}">
  {% if searchable %}<label class="search"><svg class="ic"><use href="#i-search"/></svg><input type="search" placeholder="Search" autocomplete="off" data-search="{{ name }}"></label>{% endif %}
  <span class="tool-btns">
    <button type="button" class="btn-micro" data-select="{{ name }}" data-on="1">All</button>
    <button type="button" class="btn-micro" data-select="{{ name }}" data-on="0">Clear</button>
  </span>
</div>
<div class="list" data-list="{{ name }}">
  {% for it in items %}<label class="row" data-val="{{ it.name }}"><input type="checkbox" name="{{ name }}" value="{{ it.name }}"{% if it.checked %} checked{% endif %}><span class="box"></span><span class="label">{{ it.name }}</span>{% if it.hint %}<small>{{ it.hint }}</small>{% endif %}</label>{% endfor %}
</div>
{% endmacro %}

<header class="nav glass">
  <div class="nav-left">
    <button type="button" class="icon-btn only-mobile" id="sidebarToggle" aria-label="Show or hide controls" aria-expanded="false"><svg class="ic"><use href="#i-sliders"/></svg></button>
    <span class="brand"><span class="brand-mark"></span>Analytics Pro</span>
  </div>
  {{ controls(True) }}
</header>
<div id="loadbar" aria-hidden="true"></div>

<div class="app">
  <aside class="sidebar glass" id="appSidebar">
    <div class="sidebar-head">
      <div class="head-row">
        <h2>Controls</h2>
        <button type="button" class="btn-text" id="resetBtn"><svg class="ic"><use href="#i-reset"/></svg>Reset</button>
      </div>
      <div class="sidebar-meta">{% if upload_time %}Updated {{ upload_time }}{% endif %}</div>
    </div>

    <form id="config-form" class="sidebar-scroll" autocomplete="off">
      <h3 class="group-cap">View & Export</h3>
      <div style="padding: 4px 8px 12px 8px;">
        <div class="seg seg-text" id="viewSeg" data-n="3" role="radiogroup" aria-label="View" style="width: 100%; margin-bottom: 10px;">
          <span class="seg-thumb"></span>
          <input type="radio" id="view_pivot" name="view_mode_toggle" value="pivot" checked><label for="view_pivot">Pivot</label>
          <input type="radio" id="view_raw" name="view_mode_toggle" value="raw"><label for="view_raw">Raw</label>
          <input type="radio" id="view_chart" name="view_mode_toggle" value="chart"><label for="view_chart">Chart</label>
        </div>
        <div style="display: flex; gap: 6px;">
          <button type="button" class="btn-primary" id="dlImage" style="flex: 1; height: 34px; font-size: 12px;"><svg class="ic" style="width:14px;height:14px"><use href="#i-image"/></svg>Image</button>
          <button type="button" class="btn-primary" id="dlExcel" style="flex: 1; height: 34px; font-size: 12px;" disabled><svg class="ic" style="width:14px;height:14px"><use href="#i-sheet"/></svg>Excel</button>
        </div>
      </div>

      <h3 class="group-cap">Period</h3>
      {% call acc('Date range', '__period', True) %}
        {% if ctx.date %}
        <div class="anchor"><span>Relative to</span>
          <div class="mini-seg" id="anchorSeg"><button type="button" data-anchor="today" class="on">Today</button><button type="button" data-anchor="data">Last data day</button></div>
        </div>
        <div class="chips">
          <button type="button" class="chip" data-preset="today">Today</button>
          <button type="button" class="chip" data-preset="yesterday">Yesterday</button>
          <button type="button" class="chip" data-preset="last7">7 days</button>
          <button type="button" class="chip" data-preset="last14">14 days</button>
          <button type="button" class="chip" data-preset="last30">30 days</button>
          <button type="button" class="chip" data-preset="last90">90 days</button>
          <button type="button" class="chip" data-preset="thisweek">This week</button>
          <button type="button" class="chip" data-preset="lastweek">Last week</button>
          <button type="button" class="chip" data-preset="mtd">Month to date</button>
          <button type="button" class="chip" data-preset="lastmonth">Last month</button>
          <button type="button" class="chip" data-preset="qtd">Quarter to date</button>
          <button type="button" class="chip" data-preset="lastqtr">Last quarter</button>
          <button type="button" class="chip" data-preset="ytd">Year to date</button>
          <button type="button" class="chip" data-preset="fytd">Fiscal YTD</button>
          <button type="button" class="chip" data-preset="all">All time</button>
        </div>
        <div class="date-grid">
          <div class="field"><label for="start_date">From</label><input type="date" name="start_date" id="start_date"></div>
          <div class="field"><label for="end_date">To</label><input type="date" name="end_date" id="end_date"></div>
        </div>
        {% if ctx.weeks %}
        <div class="sub-head"><span>Weeks <small>pick several</small></span>
          <span class="tool-btns"><button type="button" class="btn-micro" data-latest="4">Last 4</button><button type="button" class="btn-micro" data-select="weeks" data-on="0">Clear</button></span></div>
        <div class="wk-grid" data-list="weeks">
          {% for w in ctx.weeks|reverse %}<label class="wk"><input type="checkbox" name="weeks" value="{{ w.key }}"><span class="wk-chip"><b>{{ w.label }}</b><small>{{ w.range }} ’{{ w.year }}</small></span></label>{% endfor %}
        </div>
        {% endif %}
        {% if ctx.months %}
        <div class="sub-head"><span>Months <small>pick several</small></span>
          <span class="tool-btns"><button type="button" class="btn-micro" data-select="months" data-on="0">Clear</button></span></div>
        <div class="mo-grid" data-list="months">
          {% for m in ctx.months|reverse %}<label class="wk"><input type="checkbox" name="months" value="{{ m.key }}"><span class="wk-chip"><b>{{ m.label }}</b></span></label>{% endfor %}
        </div>
        {% endif %}
        {% else %}<p class="muted">No date column was detected in this file.</p>{% endif %}
      {% endcall %}

      <h3 class="group-cap">Table</h3>
      {% call acc('X axis · group by', 'index_cols', True, True) %}{{ checklist('index_cols', ctx.x_opts, True) }}{% endcall %}
      {% call acc('Y axis · values', 'value_cols', True, True) %}{{ checklist('value_cols', ctx.y_opts, True) }}{% endcall %}
      {% call acc('Measures', 'agg_funcs', True, True) %}
        <div class="chips agg">
          <label class="chip-check"><input type="checkbox" name="agg_funcs" value="sum" checked><span>Sum</span></label>
          <label class="chip-check"><input type="checkbox" name="agg_funcs" value="count"><span>Count</span></label>
          <label class="chip-check"><input type="checkbox" name="agg_funcs" value="mean"><span>Average</span></label>
        </div>

        <div class="list static">
          <label class="row switch"><span class="label">Share %<small>Contribution to the total</small></span><input type="checkbox" name="share" value="1"><span class="track"><span class="knob"></span></span></label>
          <label class="row switch"><span class="label">Growth %<small>Change versus previous row</small></span><input type="checkbox" name="growth" value="1"><span class="track"><span class="knob"></span></span></label>
          <label class="row switch"><span class="label">Total column<small>Adds across several Y columns</small></span><input type="checkbox" name="row_total" value="1" checked><span class="track"><span class="knob"></span></span></label>
        </div>
      {% endcall %}
    </form>
  </aside>

  <div class="sidebar-resizer" id="sidebarResizer" role="separator" aria-orientation="vertical" title="Drag to resize · double-click to reset"></div>

  <main class="main">
    <div id="report-area">
      <header class="report-head">
        <h1 id="reportTitle" class="report-title">Build your report</h1>
        <div class="report-meta">
          <span class="period-pill" id="periodPill"><svg class="ic"><use href="#i-cal"/></svg><span id="periodText"></span></span>
          <span class="pills" id="filterPills"></span>
        </div>
      </header>

      <div id="kpi-banner" class="kpis" hidden></div>

      <section id="spcReview" class="card review-card" hidden>
        <div class="review-head">
          <h3>SPC overview</h3>
        </div>
        <div class="review-grid">
          <div class="review-panel">
            <h4>Pros</h4>
            <ul id="spcPros"></ul>
          </div>
          <div class="review-panel">
            <h4>Cons</h4>
            <ul id="spcCons"></ul>
          </div>
        </div>
      </section>

      <section id="tableCard" class="card table-card">
        <div class="table-bar" id="table-bar" hidden><span id="statusText"></span><span class="no-export">Tap a header to sort</span></div>
        <div id="table-wrapper" class="table-scroll"></div>
      </section>

      <section id="chartCard" class="card chart-card" hidden>
        <div class="chart-bar">
          <div class="legend" id="legend"></div>
          <div class="chart-ctl no-export">
            <div class="seg seg-mini" id="typeSeg" data-n="3" role="radiogroup" aria-label="Chart type">
              <span class="seg-thumb"></span>
              <input type="radio" name="ctype" id="ct_bar" value="bar" checked><label for="ct_bar">Bar</label>
              <input type="radio" name="ctype" id="ct_line" value="line"><label for="ct_line">Line</label>
              <input type="radio" name="ctype" id="ct_area" value="area"><label for="ct_area">Area</label>
            </div>
            <div class="seg seg-mini" id="sortSeg" data-n="2" role="radiogroup" aria-label="Sort">
              <span class="seg-thumb"></span>
              <input type="radio" name="csort" id="cs_nat" value="natural" checked><label for="cs_nat">Natural</label>
              <input type="radio" name="csort" id="cs_val" value="value"><label for="cs_val">Highest</label>
            </div>

            <div class="chart-more">
              <button type="button" class="btn-micro" id="chartMoreBtn" aria-haspopup="true" aria-expanded="false">More</button>
              <div class="chart-more-menu glass" id="chartMoreMenu" role="menu">
                <button type="button" class="chart-more-item" data-chart-mode="labels">
                  <span>Toggle labels</span><span class="small" id="chartLabelState">On</span>
                </button>
                <button type="button" class="chart-more-item" data-chart-mode="top20">
                  <span>Top 20</span><span class="small">View</span>
                </button>
                <button type="button" class="chart-more-item" data-chart-mode="top50">
                  <span>Top 50</span><span class="small">View</span>
                </button>
                <button type="button" class="chart-more-item" data-chart-mode="all">
                  <span>Show all</span><span class="small">Reset</span>
                </button>
                <button type="button" class="chart-more-item" data-chart-mode="reset">
                  <span>Reset series</span><span class="small">All</span>
                </button>
              </div>
            </div>
          </div>
        </div>
        <div id="chartBody" class="chart-body"></div>
        <div class="chart-note" id="chartNote"></div>
      </section>
    </div>
  </main>
</div>
<script id="boot" type="application/json">{{ ctx.boot_json|safe }}</script>
</body></html>"""

APP_CSS = r"""
:root{
  color-scheme:light;
  --glass:72;
  --bg:#f2f2f7;--surface-base:#ffffff;--surface-solid:#ffffff;--table-bg:#ffffff;
  --nav-base:#fbfbfd;
  --hairline:rgba(60,60,67,.14);--hairline-strong:rgba(60,60,67,.3);
  --fill:rgba(120,120,128,.12);--fill-2:rgba(120,120,128,.07);--seg-thumb:#fff;
  --label:#1d1d1f;--label-2:#515154;--label-3:#86868b;
  --blue:#0071e3;--blue-h:#0077ed;--blue-a:#006edb;--blue-tint:rgba(0,113,227,.1);--hl:rgba(0,113,227,.12);
  --green:#34c759;--pos:#1f8a3c;--neg:#d70015;
  --th-bg:rgba(246,246,250,.9);--foot-bg:#e9f2fe;
  --spec:rgba(255,255,255,.7);
  --shadow-1:0 1px 2px rgba(0,0,0,.04),0 8px 24px rgba(0,0,0,.05);--shadow-2:0 18px 50px rgba(0,0,0,.18);
  --amb1:rgba(0,122,255,.16);--amb2:rgba(175,82,222,.12);--amb3:rgba(52,199,89,.10);
  --c1:#007aff;--c2:#34c759;--c3:#ff9500;--c4:#ff2d55;--c5:#af52de;--c6:#30b0c7;--c7:#e5a800;--c8:#5856d6;
}
:root[data-theme=dark]{
  color-scheme:dark;
  --bg:#000;--surface-base:#1c1c1e;--surface-solid:#1c1c1e;--table-bg:#1c1c1e;--nav-base:#161618;
  --hairline:rgba(255,255,255,.13);--hairline-strong:rgba(255,255,255,.28);
  --fill:rgba(120,120,128,.3);--fill-2:rgba(120,120,128,.16);--seg-thumb:#636366;
  --label:#f5f5f7;--label-2:#c7c7cc;--label-3:#8e8e93;
  --blue:#2997ff;--blue-h:#4aa8ff;--blue-a:#1a85ec;--blue-tint:rgba(41,151,255,.2);--hl:rgba(41,151,255,.2);
  --green:#30d158;--pos:#32d74b;--neg:#ff453a;
  --th-bg:rgba(40,40,43,.92);--foot-bg:#112741;
  --spec:rgba(255,255,255,.14);
  --shadow-1:0 1px 2px rgba(0,0,0,.5),0 8px 24px rgba(0,0,0,.35);--shadow-2:0 18px 50px rgba(0,0,0,.7);
  --amb1:rgba(10,132,255,.22);--amb2:rgba(191,90,242,.16);--amb3:rgba(48,209,88,.10);
  --c1:#0a84ff;--c2:#30d158;--c3:#ff9f0a;--c4:#ff375f;--c5:#bf5af2;--c6:#64d2ff;--c7:#ffd60a;--c8:#5e5ce6;
}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){
  color-scheme:dark;
  --bg:#000;--surface-base:#1c1c1e;--surface-solid:#1c1c1e;--table-bg:#1c1c1e;--nav-base:#161618;
  --hairline:rgba(255,255,255,.13);--hairline-strong:rgba(255,255,255,.28);
  --fill:rgba(120,120,128,.3);--fill-2:rgba(120,120,128,.16);--seg-thumb:#636366;
  --label:#f5f5f7;--label-2:#c7c7cc;--label-3:#8e8e93;
  --blue:#2997ff;--blue-h:#4aa8ff;--blue-a:#1a85ec;--blue-tint:rgba(41,151,255,.2);--hl:rgba(41,151,255,.2);
  --green:#30d158;--pos:#32d74b;--neg:#ff453a;
  --th-bg:rgba(40,40,43,.92);--foot-bg:#112741;
  --spec:rgba(255,255,255,.14);
  --shadow-1:0 1px 2px rgba(0,0,0,.5),0 8px 24px rgba(0,0,0,.35);--shadow-2:0 18px 50px rgba(0,0,0,.7);
  --amb1:rgba(10,132,255,.22);--amb2:rgba(191,90,242,.16);--amb3:rgba(48,209,88,.10);
  --c1:#0a84ff;--c2:#30d158;--c3:#ff9f0a;--c4:#ff375f;--c5:#bf5af2;--c6:#64d2ff;--c7:#ffd60a;--c8:#5e5ce6;
}}
:root{
  --surface:color-mix(in srgb,var(--surface-base) calc(var(--glass) * 1%),transparent);
  --nav-bg:color-mix(in srgb,var(--nav-base) calc(var(--glass) * 1%),transparent);
  --font:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --r-sm:10px;--r-md:16px;--r-lg:22px;--r-xl:30px;--nav-h:56px;
  --ease:cubic-bezier(.32,.72,0,1);--spring:cubic-bezier(.34,1.5,.64,1);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
[hidden]{display:none!important}
body{margin:0;min-height:100vh;font-family:var(--font);background:var(--bg);color:var(--label);-webkit-font-smoothing:antialiased;letter-spacing:-.011em;line-height:1.4;transition:background-color .2s,var(--ease);}
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:radial-gradient(60% 50% at 8% 0%,var(--amb1),transparent 70%),radial-gradient(50% 45% at 100% 10%,var(--amb2),transparent 70%),radial-gradient(55% 45% at 70% 100%,var(--amb3),transparent 70%);}
button,input{font:inherit;color:inherit;letter-spacing:inherit}
button{cursor:pointer;-webkit-tap-highlight-color:transparent}
:focus-visible{outline:3px solid color-mix(in srgb,var(--blue) 50%,transparent);outline-offset:1px}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.ic{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
.ic-lg{width:44px;height:44px;stroke-width:1.4}
"""

APP_JS = r"""
(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const root = document.documentElement, body = document.body;
const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const store = {
  get(k){ try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v){ try { localStorage.setItem(k, v); } catch (e) {} }
};

function toast(msg){
  const t = document.createElement('div');
  t.className = 'toast'; t.textContent = msg; body.appendChild(t);
  requestAnimationFrame(() => t.classList.add('in'));
  setTimeout(() => { t.classList.remove('in'); setTimeout(() => t.remove(), 400); }, 3200);
}

const saveDriveBtn = $('#saveDriveBtn');
if (saveDriveBtn) {
  saveDriveBtn.addEventListener('click', async () => {
    if (!confirm('Save and sync the current master report to Google Drive?')) return;
    toast('Syncing to Google Drive...');
    const fd = buildParams('pivot');
    try {
      const res = await fetch('/save-to-drive', { method: 'POST', body: fd });
      const data = await res.json();
      if (data.status === 'success') {
        toast('Master report successfully saved to Google Drive!');
      } else {
        alert('Failed to save to Drive: ' + (data.error || data.message || 'Unknown error'));
      }
    } catch (err) {
      alert('Network error while saving to Google Drive.');
    }
  });
}

function fmtMb(v){
  if (!Number.isFinite(v) || v <= 0) return '0MB/s';
  if (v >= 1) return `${v.toFixed(1)}MB/s`;
  return `${(v * 1024).toFixed(0)}KB/s`;
}

function setNetState(online, ping, up, down){
  const dot = $('#netDot');
  const text = $('#netText');
  const pingEl = $('#netPing');
  const speedEl = $('#netSpeed');
  const wrap = $('#netStatus');

  if (!dot || !text || !pingEl || !speedEl || !wrap) return;

  dot.classList.toggle('offline', !online);
  wrap.classList.toggle('offline', !online);
  text.textContent = online ? 'Online' : 'Offline';
  pingEl.textContent = `Ping ${ping || 0}ms`;
  speedEl.textContent = `Up ${fmtMb(up || 0)} · Down ${fmtMb(down || 0)}`;
}

function updateNetworkInfo(){
  const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  const online = navigator.onLine;
  const ping = conn && Number.isFinite(conn.rtt) ? Math.max(1, Math.round(conn.rtt)) : 0;
  const downlink = conn && Number.isFinite(conn.downlink) ? conn.downlink : 0;
  const uplink = conn && Number.isFinite(conn.downlink) ? conn.downlink * 0.25 : 0;
  setNetState(online, ping, uplink, downlink);
}
window.addEventListener('online', updateNetworkInfo);
window.addEventListener('offline', updateNetworkInfo);
updateNetworkInfo();

const themeNow = store.get('ap-theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
$$('#themeSeg input').forEach(i => {
  i.checked = i.value === themeNow;
  i.addEventListener('change', () => {
    if (!i.checked) return;
    root.dataset.theme = i.value;
    store.set('ap-theme', i.value);
  });
});
const gRange = $('#glassRange');
if (gRange) {
  const paint = () => gRange.style.setProperty('--p', ((gRange.value - gRange.min) / (gRange.max - gRange.min) * 100) + '%');
  gRange.value = parseInt(store.get('ap-glass') || '72', 10) || 72; paint();
  gRange.addEventListener('input', () => { root.style.setProperty('--glass', gRange.value); store.set('ap-glass', gRange.value); paint(); });
}

const popovers = [['#glassBtn', '#glassPop']].map(([b, p]) => [$(b), $(p)]).filter(([b, p]) => b && p);
function closePops(except){ popovers.forEach(([b, p]) => { if (p !== except) { p.classList.remove('show'); b.setAttribute('aria-expanded', 'false'); } }); }
popovers.forEach(([b, p]) => b.addEventListener('click', e => {
  e.stopPropagation(); const open = !p.classList.contains('show');
  closePops(open ? p : null); p.classList.toggle('show', open); b.setAttribute('aria-expanded', String(open));
}));
document.addEventListener('click', e => {
  const insideGlass = e.target.closest('#glassBtn, #glassPop');
  if (!insideGlass) closePops();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePops(); });

const dz = $('#dropzone');
if (dz) {
  const input = $('#file'), title = $('#dzTitle'), sub = $('#dzSub'), btn = $('#launchBtn');
  const size = n => n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
  const sync = () => {
    const f = input.files[0];
    dz.classList.toggle('has-file', !!f);
    title.textContent = f ? f.name : 'Choose a file';
    sub.textContent = f ? size(f.size) + ' · ready to launch' : 'or drag it here · .xlsx, .xls, .csv';
    btn.disabled = !f;
  };
  input.addEventListener('change', sync);
  ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('drag'); }));
  dz.addEventListener('drop', e => { if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; sync(); } });
  $('#uploadForm').addEventListener('submit', () => { btn.classList.add('busy'); btn.textContent = 'Uploading…'; });
}

const form = $('#config-form');
if (!form) return;

const sw = $('#mobileSwitch');
sw.checked = body.classList.contains('mobile-mode');
sw.addEventListener('change', () => {
  const on = sw.checked;
  body.classList.toggle('mobile-mode', on); body.classList.toggle('desktop-mode', !on);
  body.classList.toggle('sidebar-collapsed', on);
  $('#sidebarToggle').setAttribute('aria-expanded', String(!on));
  store.set('ap-mobile', on ? '1' : '0');
  redrawSoon();
});
$('#sidebarToggle').addEventListener('click', e => {
  const c = body.classList.toggle('sidebar-collapsed');
  e.currentTarget.setAttribute('aria-expanded', String(!c));
});

const rz = $('#sidebarResizer');
const savedW = store.get('ap-sidebar-w');
if (savedW) root.style.setProperty('--sidebar-w', savedW + 'px');
rz.addEventListener('pointerdown', e => { rz.setPointerCapture(e.pointerId); rz.classList.add('resizing'); body.style.cursor = 'col-resize'; body.style.userSelect = 'none'; });
rz.addEventListener('pointermove', e => { if (rz.hasPointerCapture(e.pointerId)) root.style.setProperty('--sidebar-w', Math.min(560, Math.max(270, e.clientX - 12)) + 'px'); });
const endResize = () => {
  rz.classList.remove('resizing'); body.style.cursor = ''; body.style.userSelect = '';
  const w = parseInt(getComputedStyle(root).getPropertyValue('--sidebar-w'), 10); if (w) store.set('ap-sidebar-w', w);
  redrawSoon();
};
rz.addEventListener('pointerup', endResize); rz.addEventListener('pointercancel', endResize);
rz.addEventListener('dblclick', () => { root.style.removeProperty('--sidebar-w'); store.set('ap-sidebar-w', ''); redrawSoon(); });

const boot = JSON.parse($('#boot').textContent || '{}');
const filterMap = boot.map || [];
const tableWrap = $('#table-wrapper'), tableCard = $('#tableCard'), chartCard = $('#chartCard');
const bar = $('#table-bar'), kpiEl = $('#kpi-banner'), chartBody = $('#chartBody');
const dlExcel = $('#dlExcel');
const dlImage = $('#dlImage');
const spcReview = $('#spcReview');
const spcPros = $('#spcPros');
const spcCons = $('#spcCons');
const view = () => $('input[name="view_mode_toggle"]:checked').value;
const order = { index_cols: [], value_cols: [] };
let data = null, dataMode = null, lastParams = null, ctrl = null, timer = null;
let periodLabel = '', activePreset = null, activeKpi = null, kpis = [];
const emptyBlock = (t, m, err) => `<div class="empty${err ? ' err' : ''}"><svg class="ic"><use href="#i-chart"/></svg><h3>${esc(t)}</h3><p>${m}</p></div>`;
const PROMPT = emptyBlock('Build your report', 'Pick at least one <b>X column</b>, one <b>Y column</b> and one <b>measure</b> in the sidebar.');

const checked = name => $$(`input[name="${name}"]:checked`);
const isShown = r => !r || (r.dataset.casc !== '1' && r.dataset.srch !== '1');

function syncOrder(name){
  const cur = checked(name).map(i => i.value), set = new Set(cur);
  order[name] = order[name].filter(v => set.has(v));
  cur.forEach(v => { if (!order[name].includes(v)) order[name].push(v); });
  $$(`[data-list="${name}"] .row`).forEach(r => {
    const o = r.querySelector('.ord'); if (!o) return;
    const n = order[name].indexOf(r.dataset.val); o.textContent = n >= 0 ? n + 1 : '';
  });
}

function updateBadges(){
  const sd = $('#start_date'), ed = $('#end_date');
  $$('[data-badge-for]').forEach(b => {
    const k = b.dataset.badgeFor;
    const n = k === '__period' ? (checked('weeks').length + checked('months').length || ((sd && sd.value) || (ed && ed.value) ? 1 : 0)) : checked(k).length;
    const was = b.textContent; b.hidden = n === 0; b.textContent = n;
    if (n && was !== String(n)) { b.style.animation = 'none'; void b.offsetWidth; b.style.animation = ''; }
  });
}

const parseISO = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const addD = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const monday = d => addD(d, -((d.getDay() + 6) % 7));
const PRESETS = {
  today: a => [a, a], yesterday: a => [addD(a, -1), addD(a, -1)],
  last7: a => [addD(a, -6), a], last14: a => [addD(a, -13), a], last30: a => [addD(a, -29), a], last90: a => [addD(a, -89), a],
  thisweek: a => [monday(a), a], lastweek: a => { const s = addD(monday(a), -7); return [s, addD(s, 6)]; },
  mtd: a => [new Date(a.getFullYear(), a.getMonth(), 1), a],
  lastmonth: a => [new Date(a.getFullYear(), a.getMonth() - 1, 1), new Date(a.getFullYear(), a.getMonth(), 0)],
  qtd: a => [new Date(a.getFullYear(), Math.floor(a.getMonth() / 3) * 3, 1), a],
  lastqtr: a => { const q = Math.floor(a.getMonth() / 3) * 3; return [new Date(a.getFullYear(), q - 3, 1), new Date(a.getFullYear(), q, 0)]; },
  ytd: a => [new Date(a.getFullYear(), 0, 1), a],
  fytd: a => { const y = a.getMonth() >= 3 ? a.getFullYear() : a.getFullYear() - 1; return [new Date(y, 3, 1), a]; }
};
const today0 = new Date(); today0.setHours(0, 0, 0, 0);
const dmax = boot.dmax ? parseISO(boot.dmax) : null;
let anchor = dmax && (today0 - dmax) > 3 * 864e5 ? 'data' : 'today';
function paintAnchor(){ $$('#anchorSeg button').forEach(b => b.classList.toggle('on', b.dataset.anchor === anchor)); }
paintAnchor();

function clearWM(){ $$('input[name="weeks"], input[name="months"]').forEach(i => { i.checked = false; }); }
function clearDates(){ const s = $('#start_date'), e = $('#end_date'); if (s) { s.value = ''; e.value = ''; } }
function setActiveChip(key){ activePreset = key; $$('.chip').forEach(c => c.classList.toggle('active', c.dataset.preset === key && key !== 'all')); }
function applyPreset(key){
  clearWM(); setActiveChip(key);
  const chip = $(`.chip[data-preset="${key}"]`); periodLabel = key === 'all' ? '' : (chip ? chip.textContent : '');
  if (key === 'all') { clearDates(); return; }
  const a = anchor === 'data' && dmax ? dmax : today0;
  const [s, e] = PRESETS[key](a);
  $('#start_date').value = iso(s); $('#end_date').value = iso(e);
}

function buildParams(server){
  const fd = new FormData(form);
  ['index_cols', 'value_cols'].forEach(n => { fd.delete(n); order[n].forEach(v => fd.append(n, v)); });
  fd.append('view_mode', server); fd.append('period_label', periodLabel);
  return fd;
}
function schedule(delay = 90){ clearTimeout(timer); timer = setTimeout(update, delay); }

async function update(){
  const server = view() === 'raw' ? 'raw' : 'pivot';
  const fd = buildParams(server);
  $$('[data-structural]').forEach(el => el.classList.toggle('is-disabled', server === 'raw'));
  updateBadges();
  if (server === 'pivot' && (!fd.getAll('index_cols').length || !fd.getAll('value_cols').length || !fd.getAll('agg_funcs').length)) {
    if (ctrl) ctrl.abort();
    body.classList.remove('loading'); data = null; lastParams = null; dataMode = server; render(); return;
  }
  if (ctrl) ctrl.abort();
  const mine = ctrl = new AbortController();
  body.classList.add('loading'); tableCard.classList.add('updating'); chartCard.classList.add('updating');
  try {
    const res = await fetch('/calculate', { method: 'POST', body: fd, signal: mine.signal });
    const d = await res.json();
    data = res.ok ? d : { error: d.error || 'Unknown error' };
    dataMode = server; lastParams = res.ok ? new URLSearchParams(fd).toString() : null;
    render();
  } catch (err) {
    if (err.name === 'AbortError') return;
    data = { error: 'Could not reach the server. Please try again.' }; lastParams = null; render();
  } finally {
    if (mine === ctrl) { body.classList.remove('loading'); tableCard.classList.remove('updating'); chartCard.classList.remove('updating'); }
  }
}

function renderReview(payload){
  const review = payload && payload.spc_review ? payload.spc_review : { pros: [], cons: [] };
  const has = review.pros.length || review.cons.length;
  spcReview.hidden = !has;
  if (!has) return;
  spcPros.innerHTML = review.pros.map(item => `
    <li>
      <strong>${esc(item.label)}</strong>
      <div class="meta">
        <span class="chip-share">${esc(item.share)}</span>
        <span>${esc(item.value)}</span>
      </div>
    </li>
  `).join('');
  spcCons.innerHTML = review.cons.map(item => `
    <li>
      <strong>${esc(item.label)}</strong>
      <div class="meta">
        <span class="chip-share">${esc(item.share)}</span>
        <span>${esc(item.value)}</span>
      </div>
    </li>
  `).join('');
}

function setHead(title, period, filters){
  $('#reportTitle').textContent = title; document.title = title + ' · Analytics Pro';
  $('#periodText').textContent = period || ''; $('#periodPill').hidden = !period;
  $('#filterPills').innerHTML = (filters || []).map(([k, v]) => `<span class="pill"><b>${esc(k)}</b> ${esc(v)}</span>`).join('');
}

function render(){
  const mode = view(), d = data;
  tableCard.hidden = mode === 'chart'; chartCard.hidden = mode !== 'chart';
  dlExcel.disabled = !(d && !d.error && lastParams);
  dlImage.disabled = !(d && !d.error);

  const block = html => {
    kpiEl.hidden = true; bar.hidden = true; tableWrap.innerHTML = html; chartBody.innerHTML = html; $('#legend').innerHTML = ''; $('#chartNote').textContent = ''; kpis = []; activeKpi = null; spcReview.hidden = true;
  };
  if (!d) { setHead('Build your report', boot.all, []); block(PROMPT); return; }
  if (d.error) { setHead('Something went wrong', '', []); block(emptyBlock('Something went wrong', esc(d.error), true)); return; }
  setHead(d.title, d.period, d.filters);

  const prevLabel = kpis[activeKpi] && kpis[activeKpi].label;
  kpis = d.kpis || [];
  activeKpi = Math.max(-1, kpis.findIndex(k => k.label === prevLabel)); if (activeKpi < 0) activeKpi = null;
  kpiEl.hidden = !kpis.length;
  kpiEl.innerHTML = kpis.map((k, i) => `<button type="button" class="kpi${k.cols && k.cols.length ? '' : ' static'}" data-i="${i}"><span class="kpi-label">${esc(k.label)}</span><span class="kpi-val">${esc(k.value)}</span><span class="kpi-sub">${esc(k.sub)}</span></button>`).join('');

  renderReview(d);

  if (mode === 'chart') { drawLegend(); drawChart(true); }
  else {
    bar.hidden = false; $('#statusText').textContent = d.status || '';
    tableWrap.innerHTML = d.table_html;
    $$('tbody tr', tableWrap).forEach((tr, i) => { tr.dataset.o = i; });
    addResizers();
  }
  applyHighlight();
}

const hlStyle = document.head.appendChild(document.createElement('style'));
kpiEl.addEventListener('click', e => {
  const b = e.target.closest('.kpi'); if (!b) return;
  const i = +b.dataset.i; if (!kpis[i].cols || !kpis[i].cols.length) return;
  activeKpi = activeKpi === i ? null : i; applyHighlight();
});
function applyHighlight(){
  const k = activeKpi != null ? kpis[activeKpi] : null;
  $$('.kpi', kpiEl).forEach((b, i) => b.classList.toggle('active', i === activeKpi));
  const tbl = $('.excel-table', tableWrap);
  let css = '';
  if (tbl) {
    tbl.classList.toggle('hl', !!k);
    if (k) {
      const nidx = Math.max(+tbl.dataset.nidx || 0, 1);
      const sel = k.cols.map(c => `:nth-child(${c + 1})`).join(',');
      css = `.excel-table.hl :is(td,th):not(:nth-child(-n+${nidx})){color:var(--label-3)!important}` +
            `.excel-table.hl td:not(:nth-child(-n+${nidx})) span{opacity:.5}` +
            `.excel-table.hl :is(td,th):is(${sel}){color:var(--label)!important;background-image:linear-gradient(var(--hl),var(--hl))}` +
            `.excel-table.hl th:is(${sel}){color:var(--blue)!important}` +
            `.excel-table.hl td:is(${sel}) span{opacity:1}`;
    }
  }
  hlStyle.textContent = css;
  const set = k ? new Set(k.cols) : null;
  const match = !!(set && chartData && chartData.series.some(s => set.has(s.col)));
  chartBody.classList.toggle('hl', match);
  $$('.ser', chartBody).forEach(g => g.classList.toggle('on', !!set && set.has(+g.dataset.col)));
  if (match) {
    const need = chartData.series.map((s, i) => set.has(s.col) && hidden.has(i) ? i : -1).filter(i => i >= 0);
    if (need.length) { need.forEach(i => hidden.delete(i)); drawLegend(); drawChart(false); }
  }
}

form.addEventListener('submit', e => e.preventDefault());
form.addEventListener('change', e => {
  const t = e.target, n = t.name;
  if (n === 'weeks' || n === 'months') {
    $$(`input[name="${n === 'weeks' ? 'months' : 'weeks'}"]`).forEach(i => { i.checked = false; });
    clearDates(); setActiveChip(null); periodLabel = '';
  } else if (t.type === 'date') { clearWM(); setActiveChip(null); periodLabel = ''; }
  if (n === 'index_cols' || n === 'value_cols') syncOrder(n);
  schedule();
});
form.addEventListener('input', e => {
  const q = e.target.dataset && e.target.dataset.search; if (!q) return;
  const needle = e.target.value.trim().toLowerCase();
  $$('.row', $(`[data-list="${q}"]`)).forEach(r => { r.dataset.srch = r.dataset.val.toLowerCase().includes(needle) ? '0' : '1'; });
});
form.addEventListener('click', e => {
  const head = e.target.closest('.acc-head');
  if (head) { const open = head.parentElement.classList.toggle('open'); head.setAttribute('aria-expanded', String(open)); return; }
  const sel = e.target.closest('[data-select]');
  if (sel) {
    const on = sel.dataset.on === '1', name = sel.dataset.select;
    $$(`input[name="${name}"]`).forEach(i => { if (!on || isShown(i.closest('.row'))) i.checked = on; });
    if (name === 'weeks' || name === 'months') { clearDates(); setActiveChip(null); periodLabel = ''; }
    if (name === 'index_cols' || name === 'value_cols') syncOrder(name);
    schedule(0); return;
  }
  const lat = e.target.closest('[data-latest]');
  if (lat) {
    const n = +lat.dataset.latest; clearDates(); setActiveChip(null); periodLabel = ''; $$('input[name="months"]').forEach(i => { i.checked = false; });
    $$('input[name="weeks"]').forEach((i, k) => { i.checked = k < n; }); schedule(0); return;
  }
  const chip = e.target.closest('.chip');
  if (chip) { applyPreset(chip.dataset.preset); schedule(0); return; }
  const an = e.target.closest('[data-anchor]');
  if (an) { anchor = an.dataset.anchor; paintAnchor(); if (activePreset && activePreset !== 'all') { applyPreset(activePreset); schedule(0); } }
});
$$('input[name="view_mode_toggle"]').forEach(r => r.addEventListener('change', () => {
  const server = view() === 'raw' ? 'raw' : 'pivot';
  if (server !== dataMode) { activeKpi = null; update(); } else { updateBadges(); render(); }
  $$('[data-structural]').forEach(el => el.classList.toggle('is-disabled', server === 'raw'));
}));

$('#resetBtn').addEventListener('click', () => {
  form.reset(); setActiveChip(null); periodLabel = ''; activeKpi = null;
  $$('.row').forEach(r => { delete r.dataset.casc; delete r.dataset.srch; });
  $$('[data-search]').forEach(i => { i.value = ''; });
  order.index_cols = []; order.value_cols = []; syncOrder('index_cols'); syncOrder('value_cols');
  $('#view_pivot').checked = true; schedule(0);
});

function addResizers(){
  $$('.excel-table th', tableWrap).forEach(th => { if (!th.querySelector('.resizer')) th.appendChild(Object.assign(document.createElement('div'), { className: 'resizer' })); });
}
const MON = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };
function sortKey(text, numeric){
  const t = text.trim();
  if (numeric) { const m = t.replace(/,/g, '').match(/-?\d+(\.\d+)?/); if (!m) return -Infinity; const v = parseFloat(m[0]); return /↓/.test(t) ? -Math.abs(v) : v; }
  const d = t.match(/^(\d{1,2})[ -]([A-Za-z]{3})[ -](\d{2,4})$/);
  if (d) { const y = +d[3] < 100 ? 2000 + +d[3] : +d[3]; return new Date(y, MON[d[2].toLowerCase()], +d[1]).getTime(); }
  return t.toLowerCase();
}
tableWrap.addEventListener('click', e => {
  const th = e.target.closest('th'); if (!th || e.target.closest('.resizer')) return;
  const table = th.closest('table'), ci = th.cellIndex, tb = table.tBodies[0];
  const dir = th.dataset.dir === 'asc' ? 'desc' : th.dataset.dir === 'desc' ? '' : 'asc';
  $$('th', table).forEach(h => { delete h.dataset.dir; }); if (dir) th.dataset.dir = dir;
  const numeric = th.classList.contains('num'), rows = Array.from(tb.rows);
  if (!dir) rows.sort((a, b) => a.dataset.o - b.dataset.o);
  else {
    const keys = new Map(rows.map(r => [r, sortKey(r.cells[ci].textContent, numeric)]));
    rows.sort((a, b) => { const x = keys.get(a), y = keys.get(b); const c = x < y ? -1 : x > y ? 1 : 0; return dir === 'asc' ? c : -c; });
  }
  const frag = document.createDocumentFragment(); rows.forEach(r => frag.appendChild(r)); tb.appendChild(frag);
});
tableWrap.addEventListener('pointerdown', e => {
  const h = e.target.closest('.resizer'); if (!h) return;
  const th = h.parentElement, sx = e.clientX, sw0 = th.offsetWidth;
  h.setPointerCapture(e.pointerId);
  const move = ev => { th.style.width = th.style.minWidth = Math.max(60, sw0 + ev.clientX - sx) + 'px'; };
  const up = () => { h.removeEventListener('pointermove', move); h.removeEventListener('pointerup', up); };
  h.addEventListener('pointermove', move); h.addEventListener('pointerup', up);
  e.preventDefault(); e.stopPropagation();
});

let ctype = 'bar', csort = 'natural', hidden = new Set(), chartData = null, chartSig = '', chartX = '', redrawT = null, uid = 0;
let chartLabelVisible = true;
let chartMaxRows = null;

const fmtFull = v => v == null ? '–' : (Math.abs(v) < 100 && v % 1 !== 0 ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : Math.round(v).toLocaleString('en-IN'));
const trim1 = n => String(Math.round(n * 10) / 10);
const fmtAxis = v => { const a = Math.abs(v); return a >= 1e7 ? trim1(v / 1e7) + ' Cr' : a >= 1e5 ? trim1(v / 1e5) + ' L' : a >= 1e3 ? trim1(v / 1e3) + 'K' : trim1(v); };
function niceTicks(lo, hi, n = 5){
  if (hi === lo) hi = lo + 1;
  const raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), nm = raw / mag;
  const step = (nm <= 1 ? 1 : nm <= 2 ? 2 : nm <= 2.5 ? 2.5 : nm <= 5 ? 5 : 10) * mag;
  const out = []; for (let v = Math.floor(lo / step) * step; v <= Math.ceil(hi / step) * step + step / 2; v += step) out.push(+v.toFixed(10));
  return out;
}
function monoPath(p){
  const n = p.length; if (n < 2) return `M${p[0][0]},${p[0][1]}`;
  const dx = [], m = [], t = new Array(n);
  for (let i = 0; i < n - 1; i++) { dx[i] = p[i + 1][0] - p[i][0]; m[i] = (p[i + 1][1] - p[i][1]) / dx[i]; }
  t[0] = m[0]; t[n - 1] = m[n - 2];
  for (let i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2;
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) { t[i] = 0; t[i + 1] = 0; continue; }
    const a = t[i] / m[i], b = t[i + 1] / m[i], s = a * a + b * b;
    if (s > 9) { const k = 3 / Math.sqrt(s); t[i] = k * a * m[i]; t[i + 1] = k * b * m[i]; }
  }
  let d = `M${p[0][0]},${p[0][1]}`;
  for (let i = 0; i < n - 1; i++) { const h = dx[i] / 3; d += `C${p[i][0] + h},${p[i][1] + t[i] * h} ${p[i + 1][0] - h},${p[i + 1][1] - t[i + 1] * h} ${p[i + 1][0]},${p[i + 1][1]}`; }
  return d;
}
function drawLegend(){
  const c = chartData; $('#legend').innerHTML = c ? c.series.map((s, i) => `<button type="button" class="lg${hidden.has(i) ? ' off' : ''}" data-i="${i}" title="Show or hide"><i style="background:var(--c${i % 8 + 1})"></i>${esc(s.name)}</button>`).join('') : '';
}
$('#legend').addEventListener('click', e => {
  const b = e.target.closest('.lg'); if (!b) return; const i = +b.dataset.i;
  if (hidden.has(i)) hidden.delete(i); else if (chartData.series.length - hidden.size > 1) hidden.add(i);
  drawLegend(); drawChart(false); applyHighlight();
});
$$('input[name="ctype"]').forEach(r => r.addEventListener('change', () => { ctype = r.value; drawChart(true); applyHighlight(); }));
$$('input[name="csort"]').forEach(r => r.addEventListener('change', () => { csort = r.value; drawChart(true); applyHighlight(); }));
const redrawSoon = () => { clearTimeout(redrawT); redrawT = setTimeout(() => { if (!chartCard.hidden && chartData) { drawChart(false); applyHighlight(); } }, 160); };
window.addEventListener('resize', redrawSoon);

const chartMoreBtn = $('#chartMoreBtn');
const chartMoreMenu = $('#chartMoreMenu');
if (chartMoreBtn && chartMoreMenu) {
  chartMoreBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = !chartMoreMenu.classList.contains('show');
    chartMoreMenu.classList.toggle('show', open);
    chartMoreBtn.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#chartMoreBtn') && !e.target.closest('#chartMoreMenu')) {
      chartMoreMenu.classList.remove('show');
      chartMoreBtn.setAttribute('aria-expanded', 'false');
    }
  });
  document.querySelectorAll('[data-chart-mode]').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.chartMode;
      if (mode === 'labels') {
        chartLabelVisible = !chartLabelVisible;
        document.getElementById('chartLabelState').textContent = chartLabelVisible ? 'On' : 'Off';
        drawChart(false);
      }
      if (mode === 'top20') { chartMaxRows = 20; drawChart(false); }
      if (mode === 'top50') { chartMaxRows = 50; drawChart(false); }
      if (mode === 'all') { chartMaxRows = null; drawChart(false); }
      if (mode === 'reset') {
        hidden = new Set();
        chartSig = '';
        chartX = '';
        drawLegend();
        drawChart(false);
      }
      chartMoreMenu.classList.remove('show');
      chartMoreBtn.setAttribute('aria-expanded', 'false');
    });
  });
}

function drawChart(animate){
  const d = data && data.chart;
  if (!d || !d.series.length || !d.labels.length) {
    chartData = null;
    chartBody.innerHTML = emptyBlock('Nothing to chart', 'Choose at least one X column and a measure.', false);
    $('#chartNote').textContent = '';
    return;
  }

  const sig = d.series.map(s => s.name).join('|');
  if (sig !== chartSig) {
    chartSig = sig; hidden = new Set(); const a = d.series[0].agg;
    d.series.forEach((s, i) => { if (s.agg !== a || i >= 4) hidden.add(i); });
    drawLegendFor(d);
  }
  if (d.x_title !== chartX) {
    chartX = d.x_title; ctype = d.is_time ? 'line' : 'bar'; csort = 'natural';
    $(`#ct_${ctype}`).checked = true; $('#cs_nat').checked = true;
  }
  chartData = d; drawLegend();
  $('#chartNote').textContent = d.note || '';

  let idx = d.labels.map((_, i) => i);
  const labelsAll = idx.map(i => d.labels[i]);
  if (chartMaxRows && labelsAll.length > chartMaxRows) {
    idx = idx.slice(0, chartMaxRows);
  }

  const mobile = body.classList.contains('mobile-mode');
  const vis = d.series.map((s, i) => i).filter(i => !hidden.has(i));
  if (csort === 'value') {
    const s = d.series[vis[0]];
    idx.sort((a, b) => (s.values[b] ?? -Infinity) - (s.values[a] ?? -Infinity));
  }
  const labels = idx.map(i => d.labels[i]);
  const ser = vis.map(i => ({ i, s: d.series[i], v: idx.map(k => d.series[i].values[k]) }));
  const n = labels.length, ns = ser.length;
  const H = mobile ? 300 : 380, m = { t: 22, r: 12, l: 8 };
  const longest = Math.max(...labels.map(l => l.length));
  const rotate = n > 6 || longest > 10; m.b = rotate ? 92 : 44;
  const avail = Math.max(chartBody.clientWidth - 70, 240);
  const minStep = ctype === 'bar' ? Math.max(38, ns * 15 + 22) : 36;
  const step = Math.max((avail - m.l - m.r) / n, minStep), plotW = step * n, W = m.l + plotW + m.r;
  const all = ser.flatMap(x => x.v).filter(v => v != null);
  const ticks = niceTicks(Math.min(0, ...all), Math.max(0, ...all));
  const y0 = ticks[0], y1 = ticks[ticks.length - 1], ph = H - m.t - m.b;
  const Y = v => m.t + (1 - (v - y0) / (y1 - y0)) * ph, X = i => m.l + step * (i + .5);
  const id = ++uid;

  let ya = `<svg class="yaxis" width="54" height="${H}" aria-hidden="true">`;
  ticks.forEach(t => { ya += `<text x="46" y="${Y(t) + 4}" text-anchor="end">${fmtAxis(t)}</text>`; });
  ya += '</svg>';

  let s = `<svg class="plot${animate ? ' anim' : ''}" width="${W}" height="${H}" role="img" aria-label="${esc(d.x_title)}">`;
  if (ctype === 'area') s += '<defs>' + ser.map(x => `<linearGradient id="g${id}_${x.i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--c${x.i % 8 + 1})" stop-opacity=".45"/><stop offset="1" stop-color="var(--c${x.i % 8 + 1})" stop-opacity="0"/></linearGradient>`).join('') + '</defs>';
  ticks.forEach(t => { s += `<line class="${t === 0 ? 'zero' : 'grid'}" x1="0" x2="${W}" y1="${Y(t)}" y2="${Y(t)}"/>`; });
  s += '<rect class="band" id="band" y="0" height="' + H + '" width="' + step + '" rx="8"/><line class="rule" id="rule" y1="' + m.t + '" y2="' + (H - m.b) + '"/>';
  const every = Math.ceil((rotate ? 17 : 70) / step);
  labels.forEach((l, i) => {
    if (i % every) return;
    const t = l.length > 18 ? l.slice(0, 17) + '…' : l;
    if (chartLabelVisible) {
      s += rotate ? `<text class="xtick" transform="translate(${X(i) + 4},${H - m.b + 16}) rotate(-38)" text-anchor="end">${esc(t)}</text>` : `<text class="xtick" x="${X(i)}" y="${H - m.b + 20}" text-anchor="middle">${esc(t)}</text>`;
    }
  });
  const showVals = ctype === 'bar' && n * ns <= 14;
  ser.forEach(x => {
    s += `<g class="ser" data-col="${x.s.col}" style="--sc:var(--c${x.i % 8 + 1})">`;
    if (ctype === 'bar') {
      const gw = Math.min(step * .72, ns * 44), bw = gw / ns;
      x.v.forEach((v, i) => {
        if (v == null) return; const j = ser.indexOf(x), bx = X(i) - gw / 2 + j * bw + (ns > 1 ? 1 : 0), top = Y(Math.max(v, 0)), bot = Y(Math.min(v, 0));
        s += `<rect class="bar" style="--k:${i}" x="${bx}" y="${top}" width="${Math.max(bw - (ns > 1 ? 2 : 0), 2)}" height="${Math.max(bot - top, 1.5)}" rx="${Math.min(6, bw / 2)}"/>`;
        if (showVals) s += `<text class="vlabel" x="${bx + (bw - 2) / 2}" y="${top - 6}">${fmtAxis(v)}</text>`;
      });
    } else {
      const pts = x.v.map((v, i) => v == null ? null : [X(i), Y(v)]).filter(Boolean);
      if (pts.length) {
        const path = monoPath(pts);
        if (ctype === 'area') s += `<path class="area" d="${path}L${pts[pts.length - 1][0]},${Y(0)}L${pts[0][0]},${Y(0)}Z" fill="url(#g${id}_${x.i})"/>`;
        s += `<path class="line" pathLength="1" d="${path}"/>`;
        if (n <= 60) pts.forEach(p => { s += `<circle class="dot" cx="${p[0]}" cy="${p[1]}" r="3.5"/>`; });
        x.v.forEach((v, i) => { if (v != null) s += `<circle class="hdot" data-s="${x.i}" data-i="${i}" cx="${X(i)}" cy="${Y(v)}" r="5.5"/>`; });
      }
    }
    s += '</g>';
  });
  s += `<rect class="hit" id="hit" x="0" y="0" width="${W}" height="${H}"/></svg>`;
  chartBody.innerHTML = `${ya}<div class="plot-scroll">${s}</div><div class="tip" id="tip"></div>`;

  const hit = $('#hit'), band = $('#band'), rule = $('#rule'), tip = $('#tip'), scroller = $('.plot-scroll', chartBody);
  const hdots = $$('.hdot', chartBody);
  const hide = () => { band.style.opacity = 0; rule.style.opacity = 0; tip.classList.remove('show'); hdots.forEach(c => { c.style.opacity = 0; }); };
  hit.addEventListener('pointermove', e => {
    const r = hit.getBoundingClientRect(), i = Math.min(n - 1, Math.max(0, Math.floor((e.clientX - r.left - m.l) / step)));
    if (ctype === 'bar') { band.setAttribute('x', m.l + step * i); band.style.opacity = 1; rule.style.opacity = 0; }
    else { rule.setAttribute('x1', X(i)); rule.setAttribute('x2', X(i)); rule.style.opacity = 1; band.style.opacity = 0; }
    hdots.forEach(c => { c.style.opacity = +c.dataset.i === i ? 1 : 0; });
    tip.innerHTML = `<div class="tip-title">${esc(labels[i])}</div>` + ser.map(x => `<div class="tip-row"><i style="background:var(--c${x.i % 8 + 1})"></i><span>${esc(x.s.name)}</span><b>${fmtFull(x.v[i])}</b></div>`).join('');
    const cb = chartBody.getBoundingClientRect(); let left = e.clientX - cb.left + 16;
    if (left + tip.offsetWidth > cb.width - 6) left = e.clientX - cb.left - tip.offsetWidth - 16;
    tip.style.left = Math.max(4, left) + 'px'; tip.classList.add('show');
  });
  hit.addEventListener('pointerleave', hide);
  scroller.scrollLeft = 0;
}
function drawLegendFor(d){ chartData = d; drawLegend(); }

let d2i = null;
const loadD2I = () => d2i || (d2i = new Promise((ok, fail) => {
  const s = document.createElement('script');
  s.src = 'https://cdnjs.cloudflare.com/ajax/libs/dom-to-image/2.6.0/dom-to-image.min.js';
  s.onload = ok; s.onerror = () => { d2i = null; fail(new Error('load')); }; document.head.appendChild(s);
}));

dlImage.addEventListener('click', async () => {
  const area = $('#report-area'), mode = view();
  const titleText = ($('#reportTitle').textContent || 'Report').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 70) || 'Report';
  const fileName = `${titleText}_${mode}.png`;

  try {
    await loadD2I();
    body.classList.add('exporting');
    if (mode === 'chart') { drawChart(false); applyHighlight(); }
    await sleep(260);

    const rect = area.getBoundingClientRect();
    const scale = Math.max(1.5, Math.min(2.5, 1800 / Math.max(rect.width, 1)));
    const width = Math.max(1200, Math.ceil(rect.width * scale));
    const height = Math.max(900, Math.ceil(rect.height * scale));
    const bg = getComputedStyle(body).backgroundColor;

    const blob = await domtoimage.toBlob(area, {
      bgcolor: bg,
      cacheBust: true,
      width,
      height,
      style: {
        transform: `scale(${scale})`,
        transformOrigin: 'top left',
        width: `${rect.width}px`,
        height: `${rect.height}px`
      }
    });

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);

    toast('Image saved');
  } catch (err) {
    console.error(err);
    toast('Could not export the image. Please try again.');
  } finally {
    area.style.width = '';
    body.classList.remove('exporting');
    if (mode === 'chart') { drawChart(false); applyHighlight(); }
  }
});

syncOrder('index_cols'); syncOrder('value_cols'); updateBadges(); update();
})();
"""

ASSET_VERSION = hashlib.md5((APP_CSS + APP_JS).encode()).hexdigest()[:8]

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
