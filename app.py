"""Analytics Pro - upload a sheet, slice it, pivot it, export it.

Single-file Flask app. Run:  python app.py
Needs: flask, pandas, openpyxl
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
from flask import (Flask, Response, jsonify, redirect, render_template_string,
                   request, send_file, url_for)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB uploads

UPLOAD_DIR = os.environ.get("DASHBOARD_UPLOAD_DIR", "/tmp/dashboard_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATA_FILE_PATH = os.path.join(UPLOAD_DIR, "shared_data.pkl")
META_FILE_PATH = os.path.join(UPLOAD_DIR, "metadata.json")

RAW_ROW_LIMIT = 3000          # rows rendered in Raw view (Excel export is always complete)
LABELS = {"sum": "Value", "count": "Qty", "mean": "Avg Price"}

# ════════════════════════════════════════════════════════════════════
#  DATA LAYER  (parse once on upload, cache in memory by file mtime)
# ════════════════════════════════════════════════════════════════════
_lock = threading.Lock()
_state = {"mtime": None, "df": None, "ctx": None}


def pick_date_col(cols):
    for c in ("Customized Sales Date", "Sale Date"):
        if c in cols:
            return c
    return next((c for c in cols if "date" in c.lower()), "")


def prepare_df(df):
    """Normalise once at upload so every request afterwards is cheap."""
    df.columns = [str(c).strip() for c in df.columns]
    d = pick_date_col(list(df.columns))
    if d and not pd.api.types.is_numeric_dtype(df[d]):
        df[d] = pd.to_datetime(df[d], errors="coerce", dayfirst=True)
    c = detect_columns(df)
    for key in ("spc", "seg", "fam"):          # stable string keys for filtering
        col = c[key]
        if col:
            s = df[col]
            df[col] = s.astype(object).where(s.isna(), s.astype(str))
    return df


def detect_columns(df):
    cols = list(df.columns)
    low = {c: c.lower() for c in cols}
    date = pick_date_col(cols)
    if date and not pd.api.types.is_datetime64_any_dtype(df[date]):
        date = ""
    num = df.select_dtypes(include="number").columns.tolist()
    return {
        "date": date,
        "spc": next((c for c in cols if "spc" in low[c] and "name" in low[c]), ""),
        "seg": next((c for c in cols if "seg1" in low[c]), ""),
        "fam": next((c for c in cols if "family" in low[c]), ""),
        "value": "Tentative DP" if "Tentative DP" in num else (num[0] if num else ""),
    }


def build_context(df):
    c = detect_columns(df)
    lists = {k: (sorted(df[c[k]].dropna().unique().tolist()) if c[k] else [])
             for k in ("spc", "seg", "fam")}
    keys = [(k, c[k]) for k in ("spc", "seg", "fam") if c[k]]
    mapping = []
    if keys:
        m = df[[col for _, col in keys]].fillna("N/A").drop_duplicates()
        m.columns = [k for k, _ in keys]
        mapping = m.to_dict(orient="records")
    min_d = max_d = "N/A"
    if c["date"]:
        s = df[c["date"]]
        if s.notna().any():
            min_d, max_d = s.min().strftime("%d %b %y"), s.max().strftime("%d %b %y")
    return {
        **c,
        "spc_list": lists["spc"], "seg_list": lists["seg"], "fam_list": lists["fam"],
        "grouping": df.select_dtypes(exclude="number").columns.tolist(),
        "mapping_json": json.dumps(mapping).replace("<", "\\u003c"),
        "min_date": min_d, "max_date": max_d,
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
    os.replace(tmp, DATA_FILE_PATH)            # atomic: readers never see half a file
    with open(META_FILE_PATH, "w") as fh:
        json.dump({"upload_time": datetime.now().strftime("%d %b %Y, %I:%M %p")}, fh)


def get_upload_time():
    try:
        with open(META_FILE_PATH) as fh:
            return json.load(fh).get("upload_time", "")
    except (OSError, ValueError):
        return ""


# ════════════════════════════════════════════════════════════════════
#  FORMATTING / RENDERING
# ════════════════════════════════════════════════════════════════════
_GROUP = re.compile(r"(\d)(?=(\d\d)+$)")


def format_indian_number(x):
    if x is None or (isinstance(x, str) and x == ""):
        return ""
    try:
        if pd.isna(x):
            return ""
        n = int(round(float(x)))
    except (ValueError, TypeError, OverflowError):
        return html.escape(str(x))
    s = str(abs(n))
    if len(s) > 3:
        s = _GROUP.sub(r"\1,", s[:-3]) + "," + s[-3:]
    return f"-{s}" if n < 0 else s


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


def col_to_cells(s):
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.dt.strftime("%d-%b-%y").fillna("").tolist()
    if pd.api.types.is_numeric_dtype(s):
        return [format_indian_number(v) for v in s]
    return ["" if pd.isna(v) else html.escape(str(v)) for v in s]


def render_table(headers, columns, css, numeric, total_idx=-1):
    def cls(i):
        out = []
        if i in numeric:
            out.append("num")
        if i == total_idx:
            out.append("total-col")
        return f' class="{" ".join(out)}"' if out else ""

    head = "".join(f"<th{cls(i)}>{html.escape(h)}</th>" for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f"<td{cls(i)}>{v}</td>" for i, v in enumerate(row)) + "</tr>"
        for row in zip(*columns)
    )
    return (f'<table class="excel-table {css}"><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table>")


def empty_block(title, msg=""):
    return (f'<div class="empty"><svg class="ic"><use href="#i-chart"/></svg>'
            f"<h3>{html.escape(title)}</h3><p>{html.escape(msg)}</p></div>")


# ════════════════════════════════════════════════════════════════════
#  QUERY ENGINE
# ════════════════════════════════════════════════════════════════════
def parse_date(s):
    if not s:
        return None
    t = pd.to_datetime(s, errors="coerce")
    return None if pd.isna(t) else t


def _txt(label, vals):
    shown = ", ".join(html.escape(v) for v in vals[:6])
    more = f" +{len(vals) - 6} more" if len(vals) > 6 else ""
    return f"<b>{label}</b> {shown}{more}"


def apply_filters(df, ctx, params):
    mask, texts = None, []

    def add(m):
        nonlocal mask
        mask = m if mask is None else (mask & m)

    dc = ctx["date"]
    if dc:
        start, end = parse_date(params.get("start_date")), parse_date(params.get("end_date"))
        if start is not None:
            add(df[dc] >= start)
        if end is not None:
            add(df[dc] < end + pd.Timedelta(days=1))
        if start is not None or end is not None:
            a = start.strftime("%d-%b-%y") if start is not None else "Start"
            b = end.strftime("%d-%b-%y") if end is not None else "End"
            texts.append(f"<b>Date</b> {a} – {b}")

    for key, field, label in (("spc", "spc_filters", "SPC"),
                              ("seg", "seg1_filters", "SEG 1"),
                              ("fam", "family_filters", "Family")):
        col, vals = ctx[key], params.getlist(field)
        if col and vals:
            add(df[col].isin(vals))
            texts.append(_txt(label, vals))

    return (df if mask is None else df[mask]), texts


def build_view(state, params, want_export=False):
    """Returns (payload, export_df, http_status)."""
    df, ctx = state["df"], state["ctx"]
    mode = params.get("view_mode", "dashboard")
    index_cols = [c for c in params.getlist("index_cols")
                  if c in df.columns and c != ctx["value"]]
    agg_funcs = params.getlist("agg_funcs")

    if mode != "raw" and (not index_cols or not agg_funcs):
        return {"error": "Select at least one row grouping and one metric."}, None, 400

    dff, texts = apply_filters(df, ctx, params)
    filter_text = " · ".join(texts) if texts else "All data"
    value_col = ctx["value"]

    kpi = ""
    if len(dff) and value_col:
        active = format_indian_number(dff[ctx["spc"]].nunique()) if ctx["spc"] else "N/A"
        kpi = ('<div class="kpi"><div class="kpi-label">Total Volume</div>'
               f'<div class="kpi-val">{format_indian_number(dff[value_col].sum())}</div></div>'
               '<div class="kpi"><div class="kpi-label">Records</div>'
               f'<div class="kpi-val">{format_indian_number(len(dff))}</div></div>'
               '<div class="kpi"><div class="kpi-label">Active Entities</div>'
               f'<div class="kpi-val">{active}</div></div>')

    if dff.empty:
        return {"table_html": empty_block("No matching data", "Try widening the date range or clearing a filter."),
                "filter_text": filter_text, "status": "0 results", "kpi_html": ""}, None, 200

    # ── RAW ─────────────────────────────────────────────────────────
    if mode == "raw":
        shown = dff.head(RAW_ROW_LIMIT)
        headers = [str(c) for c in shown.columns]
        columns = [col_to_cells(shown[c]) for c in shown.columns]
        numeric = {i for i, c in enumerate(shown.columns) if pd.api.types.is_numeric_dtype(shown[c])}
        status = (f"{format_indian_number(len(dff))} rows" if len(dff) <= RAW_ROW_LIMIT else
                  f"First {format_indian_number(RAW_ROW_LIMIT)} of {format_indian_number(len(dff))} rows")
        return {"table_html": render_table(headers, columns, "raw", numeric),
                "filter_text": filter_text, "status": status, "kpi_html": kpi}, \
            (dff if want_export else None), 200

    # ── PIVOT ───────────────────────────────────────────────────────
    if not value_col:
        return {"error": "No numeric column found to aggregate."}, None, 400

    aggs = [a for a in ("sum", "count", "mean") if a in agg_funcs] or ["sum"]
    metrics = [LABELS[a] for a in aggs]
    sub = dff[index_cols + [value_col]]
    g = (sub.groupby(index_cols, observed=True)[value_col].agg(aggs)
            .rename(columns=LABELS).reset_index())
    if g.empty:
        return {"table_html": empty_block("No groups to show", "The selected grouping has only empty values."),
                "filter_text": filter_text, "status": "0 groups", "kpi_html": kpi}, None, 200
    g[metrics] = g[metrics].fillna(0)

    ordered = list(index_cols)
    for m in metrics:
        ordered.append(m)
        if "contrib" in agg_funcs and m != "Avg Price":
            tot = g[m].sum()
            g[f"{m} Contrib %"] = g[m] / tot * 100 if tot else 0.0
            ordered.append(f"{m} Contrib %")
        if "growth" in agg_funcs:
            prev = g[m].shift()
            g[f"{m} Growth %"] = (g[m] - prev) / prev.where(prev != 0) * 100
            ordered.append(f"{m} Growth %")

    total_idx = -1
    if params.get("show_row_total") == "true" and len(metrics) > 1:
        g["TOTAL"] = g[metrics].sum(axis=1)
        ordered.append("TOTAL")
        total_idx = len(ordered) - 1

    valid = sub.dropna(subset=index_cols)[value_col]
    base = {"Value": valid.sum(), "Qty": valid.count(), "Avg Price": valid.mean()}
    totals = {m: base[m] for m in metrics}
    if "TOTAL" in ordered:
        totals["TOTAL"] = sum(totals[m] for m in metrics)

    columns, numeric = [], set()
    for i, h in enumerate(ordered):
        s = g[h]
        if h in index_cols:
            cells = col_to_cells(s) + ["GRAND TOTAL" if i == 0 else ""]
        elif h.endswith(" %"):
            cells = [format_pct(v) for v in s] + [""]
            numeric.add(i)
        else:
            cells = [format_indian_number(v) for v in s] + [format_indian_number(totals[h])]
            numeric.add(i)
        columns.append(cells)

    export = None
    if want_export:
        row = {c: None for c in ordered}
        row[index_cols[0]] = "GRAND TOTAL"
        row.update(totals)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            export = pd.concat([g[ordered], pd.DataFrame([row], columns=ordered)], ignore_index=True)

    return {"table_html": render_table(ordered, columns, "pivot", numeric, total_idx),
            "filter_text": filter_text,
            "status": f"{format_indian_number(len(g))} groups", "kpi_html": kpi}, export, 200


# ════════════════════════════════════════════════════════════════════
#  ROUTES
# ════════════════════════════════════════════════════════════════════
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
    except Exception as exc:  # noqa: BLE001 - surface any parse error to the user
        return render_template_string(UPLOAD_HTML, error=f"Couldn't read that file: {exc}"), 400
    return redirect(url_for("home"))


@app.post("/calculate")
def calculate():
    st = get_state()
    if st is None:
        return jsonify({"error": "No data available."}), 400
    try:
        payload, _, code = build_view(st, request.form)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"An error occurred: {exc}"}), 500
    return jsonify(payload), code


@app.get("/download")
def download():
    st = get_state()
    if st is None:
        return "No data to download", 400
    try:
        payload, export, code = build_view(st, request.args, want_export=True)
    except Exception as exc:  # noqa: BLE001
        return f"Export failed: {exc}", 500
    if export is None:
        return payload.get("error", "Nothing to export"), 400
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        export.to_excel(writer, index=False, sheet_name="Dashboard_Report")
    out.seek(0)
    return send_file(out, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     download_name="Executive_Report.xlsx", as_attachment=True)


# Static assets are served once and cached forever (version-hashed URL).
@app.get("/assets/app.css")
def asset_css():
    return Response(APP_CSS, mimetype="text/css",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/assets/app.js")
def asset_js():
    return Response(APP_JS, mimetype="application/javascript",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.context_processor
def inject_assets():
    return {"asset_v": ASSET_VERSION, "sprite": SPRITE}


# ════════════════════════════════════════════════════════════════════
#  FRONT END
# ════════════════════════════════════════════════════════════════════
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
</defs></svg>
"""

HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<link rel="stylesheet" href="/assets/app.css?v={{ asset_v }}">
<script src="/assets/app.js?v={{ asset_v }}" defer></script>"""

UPLOAD_HTML = """<!doctype html>
<html lang="en"><head><title>Analytics Pro</title>""" + HEAD + """</head>
<body class="upload-page">
{{ sprite|safe }}
<header class="nav"><span class="brand"><span class="brand-mark"></span>Analytics Pro</span></header>
<main class="upload-wrap">
  <h1 class="hero-title">Analytics Engine.</h1>
  <p class="hero-sub">Upload your data to launch the business intelligence workspace.</p>
  <form class="upload-card" action="/dashboard" method="post" enctype="multipart/form-data" id="uploadForm">
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
<html lang="en"><head><title>Intelligence Workspace</title>""" + HEAD + """</head>
<body>
<script>document.body.classList.add(innerWidth<=768?'mobile-mode':'desktop-mode')</script>
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

{% macro checklist(name, items) %}
{% set searchable = items|length > 7 %}
<div class="tools{% if not searchable %} end{% endif %}">
  {% if searchable %}<label class="search"><svg class="ic"><use href="#i-search"/></svg><input type="search" placeholder="Search" autocomplete="off" data-search="{{ name }}"></label>{% endif %}
  <span class="tool-btns">
    <button type="button" class="btn-micro" data-select="{{ name }}" data-on="1">All</button>
    <button type="button" class="btn-micro" data-select="{{ name }}" data-on="0">Clear</button>
  </span>
</div>
<div class="list" data-list="{{ name }}">
  {% for it in items %}<label class="row" data-val="{{ it }}"><input type="checkbox" name="{{ name }}" value="{{ it }}"><span class="box"></span><span class="label" title="{{ it }}">{{ it }}</span></label>{% endfor %}
</div>
{% endmacro %}

<header class="nav">
  <div class="nav-left">
    <button type="button" class="icon-btn only-mobile" id="sidebarToggle" aria-label="Show or hide controls" aria-expanded="true"><svg class="ic"><use href="#i-sliders"/></svg></button>
    <span class="brand"><span class="brand-mark"></span>Analytics Pro</span>
  </div>
  <button type="button" class="pill-btn" id="viewToggleBtn">Desktop view</button>
</header>
<div id="loadbar" aria-hidden="true"></div>

<div class="app">
  <aside class="sidebar" id="appSidebar">
    <div class="sidebar-head">
      <div class="head-row">
        <h2>Workspace</h2>
        <button type="button" class="btn-text" id="resetBtn"><svg class="ic"><use href="#i-reset"/></svg>Reset</button>
      </div>
      <div class="sidebar-meta">{% if upload_time %}Updated {{ upload_time }}{% endif %}{% if ctx.min_date != 'N/A' %} · {{ ctx.min_date }} – {{ ctx.max_date }}{% endif %}</div>
    </div>

    <form id="config-form" class="sidebar-scroll" autocomplete="off">
      {% call acc('Timeline', '__date', True) %}
        {% if ctx.date %}
        <div class="chips">
          <button type="button" class="chip" data-preset="today">Today</button>
          <button type="button" class="chip" data-preset="last7">7 days</button>
          <button type="button" class="chip" data-preset="last30">30 days</button>
          <button type="button" class="chip" data-preset="mtd">Month to date</button>
          <button type="button" class="chip" data-preset="prev_month">Last month</button>
          <button type="button" class="chip" data-preset="ytd">Year to date</button>
          <button type="button" class="chip" data-preset="all">All time</button>
        </div>
        <div class="date-grid">
          <div class="field"><label for="start_date">From</label><input type="date" name="start_date" id="start_date"></div>
          <div class="field"><label for="end_date">To</label><input type="date" name="end_date" id="end_date"></div>
        </div>
        {% else %}<p class="muted">No date column was detected in this file.</p>{% endif %}
      {% endcall %}

      {% if ctx.spc_list %}{% call acc('SPC name', 'spc_filters') %}{{ checklist('spc_filters', ctx.spc_list) }}{% endcall %}{% endif %}
      {% if ctx.seg_list %}{% call acc('Segment 1', 'seg1_filters') %}{{ checklist('seg1_filters', ctx.seg_list) }}{% endcall %}{% endif %}
      {% if ctx.fam_list %}{% call acc('Family name', 'family_filters') %}{{ checklist('family_filters', ctx.fam_list) }}{% endcall %}{% endif %}

      {% call acc('Row grouping', 'index_cols', True, True) %}{{ checklist('index_cols', ctx.grouping) }}{% endcall %}

      {% call acc('Metrics', 'agg_funcs', True, True) %}
        <div class="list static">
          <label class="row"><input type="checkbox" name="agg_funcs" value="sum"><span class="box"></span><span class="label">Sum total<small>Total value per group</small></span></label>
          <label class="row"><input type="checkbox" name="agg_funcs" value="count"><span class="box"></span><span class="label">Count<small>Number of records</small></span></label>
          <label class="row"><input type="checkbox" name="agg_funcs" value="mean"><span class="box"></span><span class="label">Average price<small>Mean value per record</small></span></label>
        </div>
        <div class="list static">
          <label class="row"><input type="checkbox" name="agg_funcs" value="contrib"><span class="box"></span><span class="label">Contribution %<small>Share of the column total</small></span></label>
          <label class="row"><input type="checkbox" name="agg_funcs" value="growth"><span class="box"></span><span class="label">Growth %<small>Change versus the previous row</small></span></label>
        </div>
        <div class="list static">
          <label class="row switch"><span class="label">Row totals<small>Add a TOTAL column</small></span><input type="checkbox" name="show_row_total" value="true" checked><span class="track"><span class="knob"></span></span></label>
        </div>
      {% endcall %}
    </form>

    <div class="sidebar-foot">
      <a class="btn-tinted" href="/upload"><svg class="ic"><use href="#i-upload"/></svg>Upload new file</a>
    </div>
  </aside>

  <div class="sidebar-resizer" id="sidebarResizer" role="separator" aria-orientation="vertical" title="Drag to resize · double-click to reset"></div>

  <main class="main">
    <div class="page-head">
      <div>
        <h1 class="page-title">Executive Dashboard</h1>
        <div class="seg" role="radiogroup" aria-label="View mode">
          <span class="seg-thumb"></span>
          <input type="radio" id="view_dash" name="view_mode_toggle" value="dashboard" checked><label for="view_dash">Pivot</label>
          <input type="radio" id="view_raw" name="view_mode_toggle" value="raw"><label for="view_raw">Raw data</label>
        </div>
      </div>
      <div class="menu-wrap" id="exportWrap">
        <button type="button" class="btn-primary" id="exportBtn" aria-haspopup="true" aria-expanded="false"><svg class="ic"><use href="#i-share"/></svg>Export</button>
        <div class="menu" id="exportMenu" role="menu">
          <button type="button" class="menu-item" id="dlImage" role="menuitem"><svg class="ic"><use href="#i-image"/></svg>Save image</button>
          <button type="button" class="menu-item" id="dlExcel" role="menuitem"><svg class="ic"><use href="#i-sheet"/></svg>Download Excel</button>
        </div>
      </div>
    </div>

    <div id="report-area">
      <div id="kpi-banner" class="kpis" hidden></div>
      <div id="capture-area" class="table-card">
        <div class="table-bar" id="table-bar" hidden></div>
        <div id="table-wrapper" class="table-scroll"></div>
      </div>
    </div>
  </main>
</div>
<script id="filter-map" type="application/json">{{ ctx.mapping_json|safe }}</script>
</body></html>"""

APP_CSS = r"""
:root,body.export-mode{
  color-scheme:light;
  --bg:#f5f5f7;--surface:rgba(255,255,255,.72);--surface-solid:#fff;--sidebar:rgba(250,250,252,.8);
  --nav-bg:rgba(251,251,253,.8);--menu-bg:rgba(255,255,255,.86);--th-bg:rgba(250,250,252,.92);
  --hairline:rgba(0,0,0,.09);--hairline-strong:rgba(0,0,0,.18);
  --fill:rgba(120,120,128,.12);--fill-2:rgba(120,120,128,.07);--seg-thumb:#fff;
  --label:#1d1d1f;--label-2:#515154;--label-3:#86868b;
  --blue:#0071e3;--blue-h:#0077ed;--blue-a:#006edb;--blue-tint:rgba(0,113,227,.1);--total-bg:#eaf3fe;
  --green:#34c759;--pos:#1f8a3c;--neg:#d70015;
  --shadow-1:0 1px 2px rgba(0,0,0,.04),0 6px 20px rgba(0,0,0,.04);--shadow-2:0 16px 48px rgba(0,0,0,.16);
}
@media (prefers-color-scheme:dark){:root{
  color-scheme:dark;
  --bg:#000;--surface:rgba(28,28,30,.72);--surface-solid:#1c1c1e;--sidebar:rgba(20,20,22,.8);
  --nav-bg:rgba(22,22,24,.8);--menu-bg:rgba(44,44,46,.86);--th-bg:rgba(34,34,36,.92);
  --hairline:rgba(255,255,255,.12);--hairline-strong:rgba(255,255,255,.24);
  --fill:rgba(120,120,128,.28);--fill-2:rgba(120,120,128,.14);--seg-thumb:#636366;
  --label:#f5f5f7;--label-2:#c7c7cc;--label-3:#8e8e93;
  --blue:#2997ff;--blue-h:#4aa8ff;--blue-a:#1a85ec;--blue-tint:rgba(41,151,255,.18);--total-bg:#10243b;
  --green:#30d158;--pos:#32d74b;--neg:#ff453a;
  --shadow-1:0 1px 2px rgba(0,0,0,.4),0 6px 20px rgba(0,0,0,.3);--shadow-2:0 16px 48px rgba(0,0,0,.6);
}}
:root{
  --font:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --r-md:12px;--r-lg:18px;--nav-h:52px;
  --ease:cubic-bezier(.32,.72,0,1);--spring:cubic-bezier(.34,1.45,.64,1);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
[hidden]{display:none!important}
body{margin:0;font-family:var(--font);background:var(--bg);color:var(--label);-webkit-font-smoothing:antialiased;letter-spacing:-.01em;line-height:1.4}
button,input{font:inherit;color:inherit;letter-spacing:inherit}
button{cursor:pointer;-webkit-tap-highlight-color:transparent}
:focus-visible{outline:3px solid color-mix(in srgb,var(--blue) 45%,transparent);outline-offset:1px}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.ic{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
.ic-lg{width:40px;height:40px;stroke-width:1.5}
.muted{margin:0;font-size:13px;color:var(--label-3)}
.glass,.nav,.sidebar,.acc,.kpi,.menu,.table-bar{-webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px)}

/* ── nav ── */
.nav{position:fixed;inset:0 0 auto 0;height:var(--nav-h);z-index:1000;display:flex;align-items:center;justify-content:space-between;padding:0 20px;background:var(--nav-bg);border-bottom:.5px solid var(--hairline)}
.nav-left{display:flex;align-items:center;gap:8px}
.brand{display:flex;align-items:center;gap:10px;font-size:15px;font-weight:600;letter-spacing:-.015em}
.brand-mark{width:22px;height:22px;border-radius:7px;background:linear-gradient(135deg,#5ac8fa,#0071e3 55%,#5e5ce6);box-shadow:inset 0 0 0 .5px rgba(255,255,255,.45),0 2px 6px rgba(0,113,227,.35)}
.pill-btn{height:30px;padding:0 14px;border:0;border-radius:15px;background:var(--fill);font-size:12px;font-weight:500;transition:background .2s,transform .25s var(--spring)}
.pill-btn:hover{background:var(--hairline-strong)} .pill-btn:active{transform:scale(.95)}
.icon-btn{width:34px;height:34px;display:none;place-items:center;border:0;border-radius:10px;background:none;color:var(--blue);transition:background .2s,transform .25s var(--spring)}
.icon-btn:hover{background:var(--blue-tint)} .icon-btn:active{transform:scale(.9)}
#loadbar{position:fixed;top:var(--nav-h);left:0;width:100%;height:2px;z-index:999;overflow:hidden;opacity:0;transition:opacity .25s}
#loadbar::after{content:"";position:absolute;inset:0;width:40%;background:var(--blue);border-radius:2px}
body.loading #loadbar{opacity:1}
body.loading #loadbar::after{animation:slide 1.1s var(--ease) infinite}
@keyframes slide{from{transform:translateX(-100%)}to{transform:translateX(250%)}}

/* ── layout ── */
body.desktop-mode{overflow:hidden}
.desktop-mode .app{display:flex;height:100vh;padding-top:var(--nav-h)}
.mobile-mode .app{display:block;padding-top:var(--nav-h)}
.sidebar{display:flex;flex-direction:column;flex:none;width:var(--sidebar-w,340px);min-width:260px;height:calc(100vh - var(--nav-h));background:var(--sidebar)}
.sidebar-head{padding:22px 20px 12px}
.head-row{display:flex;align-items:center;justify-content:space-between}
.sidebar-head h2{margin:0;font-size:22px;font-weight:700;letter-spacing:-.025em;line-height:1.15}
.sidebar-meta{margin-top:4px;font-size:12px;color:var(--label-3);min-height:16px}
.sidebar-scroll{flex:1;overflow-y:auto;padding:4px 14px 20px;overscroll-behavior:contain;scrollbar-gutter:stable}
.sidebar-foot{padding:12px 14px calc(12px + env(safe-area-inset-bottom));border-top:.5px solid var(--hairline)}
.sidebar-resizer{position:relative;flex:none;width:1px;background:var(--hairline);cursor:col-resize;transition:background .2s,box-shadow .2s}
.sidebar-resizer::before{content:"";position:absolute;inset:0 -4px}
.sidebar-resizer:hover,.sidebar-resizer.resizing{background:var(--blue);box-shadow:0 0 0 1px var(--blue)}
.main{flex:1;min-width:0;height:calc(100vh - var(--nav-h));overflow-y:auto;padding:28px 36px 40px}
.page-head{display:flex;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;gap:16px;margin-bottom:20px}
.page-title{margin:0 0 14px;font-size:32px;font-weight:700;letter-spacing:-.03em;line-height:1.1}

/* ── accordion ── */
.acc{margin-bottom:10px;border-radius:var(--r-md);background:var(--surface);box-shadow:0 0 0 .5px var(--hairline),var(--shadow-1);overflow:hidden;transition:opacity .3s,filter .3s}
.acc.is-disabled{opacity:.4;filter:saturate(.3);pointer-events:none}
.acc-head{display:flex;align-items:center;gap:8px;width:100%;padding:13px 14px;border:0;background:none;text-align:left;font-size:13px;font-weight:600;transition:background .2s}
.acc-head:hover{background:var(--fill-2)}
.acc-title{flex:1}
.chev{width:14px;height:14px;color:var(--label-3);transition:transform .4s var(--ease)}
.acc.open .chev{transform:rotate(90deg)}
.acc-panel{display:grid;grid-template-rows:0fr;transition:grid-template-rows .45s var(--ease)}
.acc.open .acc-panel{grid-template-rows:1fr}
.acc-inner{min-height:0;overflow:hidden;visibility:hidden;opacity:0;transition:opacity .3s,visibility 0s .45s}
.acc.open .acc-inner{visibility:visible;opacity:1;transition:opacity .35s .08s,visibility 0s}
.acc-body{padding:2px 12px 12px}
.badge{min-width:20px;height:20px;padding:0 6px;display:grid;place-items:center;border-radius:10px;background:var(--blue);color:#fff;font-size:11px;font-weight:600;animation:pop .35s var(--spring)}
@keyframes pop{from{transform:scale(.4);opacity:0}to{transform:none;opacity:1}}

/* ── lists, checks, switch ── */
.tools{display:flex;align-items:center;gap:8px;margin:0 0 10px}
.tools.end{justify-content:flex-end}
.tool-btns{display:flex;gap:6px}
.search{position:relative;flex:1;min-width:0}
.search .ic{position:absolute;left:9px;top:50%;width:14px;height:14px;transform:translateY(-50%);color:var(--label-3)}
.search input{width:100%;height:30px;padding:0 10px 0 28px;border:0;border-radius:8px;background:var(--fill);font-size:13px;transition:background .2s,box-shadow .2s}
.search input:focus{outline:0;background:var(--surface-solid);box-shadow:0 0 0 3px color-mix(in srgb,var(--blue) 35%,transparent)}
.btn-micro{height:26px;padding:0 11px;border:0;border-radius:13px;background:var(--blue-tint);color:var(--blue);font-size:12px;font-weight:500;transition:background .2s,transform .25s var(--spring)}
.btn-micro:hover{background:color-mix(in srgb,var(--blue) 20%,transparent)} .btn-micro:active{transform:scale(.93)}
.list{max-height:200px;overflow-y:auto;border-radius:10px;background:var(--surface-solid);box-shadow:0 0 0 .5px var(--hairline)}
.list.static{max-height:none;overflow:visible}
.list+.list{margin-top:10px}
.row{position:relative;display:flex;align-items:center;gap:11px;min-height:40px;padding:9px 12px;font-size:13px;cursor:pointer;transition:background .15s}
.row+.row::before{content:"";position:absolute;top:0;left:43px;right:0;height:.5px;background:var(--hairline)}
.row:hover{background:var(--fill-2)} .row:active{background:var(--fill)}
.row[data-casc="1"],.row[data-srch="1"]{display:none}
.row .label{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row small{display:block;margin-top:1px;font-size:11px;color:var(--label-3);white-space:normal}
.row input{position:absolute;opacity:0;pointer-events:none}
.box{flex:none;width:20px;height:20px;display:grid;place-items:center;border-radius:50%;border:1.5px solid color-mix(in srgb,var(--label-3) 75%,transparent);transition:background .25s var(--ease),border-color .25s,transform .3s var(--spring)}
.box::after{content:"";width:9px;height:5px;margin-top:-2px;border:2px solid #fff;border-top:0;border-right:0;transform:rotate(-45deg) scale(0);transition:transform .35s var(--spring)}
.row input:checked+.box{background:var(--blue);border-color:var(--blue)}
.row input:checked+.box::after{transform:rotate(-45deg) scale(1)}
.row input:focus-visible+.box{outline:3px solid color-mix(in srgb,var(--blue) 45%,transparent);outline-offset:1px}
.row:active .box{transform:scale(.86)}
.switch .track{position:relative;flex:none;width:44px;height:26px;border-radius:13px;background:var(--fill);transition:background .3s var(--ease)}
.switch .knob{position:absolute;top:2px;left:2px;width:22px;height:22px;border-radius:50%;background:#fff;box-shadow:0 2px 5px rgba(0,0,0,.28);transition:transform .4s var(--spring),width .2s}
.switch input:checked+.track{background:var(--green)}
.switch input:checked+.track .knob{transform:translateX(18px)}
.switch:active .knob{width:27px}
.switch:active input:checked+.track .knob{transform:translateX(13px)}
.switch input:focus-visible+.track{outline:3px solid color-mix(in srgb,var(--blue) 45%,transparent);outline-offset:2px}
.switch::before{display:none}

/* ── timeline ── */
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.chip{height:28px;padding:0 12px;border:0;border-radius:14px;background:var(--fill);font-size:12px;font-weight:500;transition:background .2s,color .2s,transform .3s var(--spring)}
.chip:hover{background:var(--blue-tint);color:var(--blue)} .chip:active{transform:scale(.94)}
.chip.active{background:var(--blue);color:#fff}
.date-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.field label{display:block;margin:0 0 4px 2px;font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--label-3)}
.field input{width:100%;height:36px;padding:0 8px;border:0;border-radius:9px;background:var(--surface-solid);box-shadow:0 0 0 .5px var(--hairline);font-size:13px;transition:box-shadow .2s}
.field input:focus{outline:0;box-shadow:0 0 0 3px color-mix(in srgb,var(--blue) 40%,transparent)}

/* ── buttons ── */
.btn-primary{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:40px;padding:0 20px;border:0;border-radius:980px;background:var(--blue);color:#fff;font-size:14px;font-weight:500;text-decoration:none;transition:background .2s,transform .3s var(--spring),box-shadow .2s}
.btn-primary:hover{background:var(--blue-h);box-shadow:0 4px 14px color-mix(in srgb,var(--blue) 35%,transparent)}
.btn-primary:active{background:var(--blue-a);transform:scale(.96)}
.btn-primary:disabled{opacity:.35;cursor:not-allowed;box-shadow:none;transform:none}
.btn-primary.block{width:100%}
.btn-primary.busy{pointer-events:none;opacity:.7}
.btn-tinted{display:flex;align-items:center;justify-content:center;gap:8px;height:38px;border-radius:10px;background:var(--fill);color:var(--label);font-size:13px;font-weight:500;text-decoration:none;transition:background .2s,transform .3s var(--spring)}
.btn-tinted:hover{background:var(--hairline-strong)} .btn-tinted:active{transform:scale(.97)}
.btn-text{display:inline-flex;align-items:center;gap:5px;padding:5px 8px;border:0;border-radius:8px;background:none;color:var(--blue);font-size:13px;font-weight:500;transition:background .2s,transform .25s var(--spring)}
.btn-text:hover{background:var(--blue-tint)} .btn-text:active{transform:scale(.95)}
.btn-text .ic{width:14px;height:14px}

/* ── segmented control ── */
.seg{position:relative;display:inline-grid;grid-auto-flow:column;grid-auto-columns:1fr;padding:2px;border-radius:10px;background:var(--fill);isolation:isolate}
.seg-thumb{position:absolute;z-index:-1;top:2px;bottom:2px;left:2px;width:calc(50% - 2px);border-radius:8px;background:var(--seg-thumb);box-shadow:0 3px 8px rgba(0,0,0,.12),0 1px 1px rgba(0,0,0,.08);transition:transform .4s var(--ease)}
.seg:has(#view_raw:checked) .seg-thumb{transform:translateX(100%)}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg label{padding:6px 20px;border-radius:8px;text-align:center;font-size:13px;font-weight:500;color:var(--label-2);cursor:pointer;white-space:nowrap;transition:color .25s}
.seg input:checked+label{color:var(--label)}
.seg input:focus-visible+label{outline:3px solid color-mix(in srgb,var(--blue) 45%,transparent)}

/* ── export menu ── */
.menu-wrap{position:relative}
.menu{position:absolute;right:0;top:calc(100% + 8px);z-index:50;min-width:210px;padding:6px;border-radius:14px;background:var(--menu-bg);box-shadow:0 0 0 .5px var(--hairline),var(--shadow-2);transform-origin:top right;opacity:0;visibility:hidden;pointer-events:none;transform:scale(.9) translateY(-6px);transition:opacity .2s,transform .35s var(--spring),visibility 0s .35s}
.menu.show{opacity:1;visibility:visible;pointer-events:auto;transform:none;transition-delay:0s}
.menu-item{display:flex;align-items:center;gap:10px;width:100%;padding:9px 10px;border:0;border-radius:8px;background:none;font-size:13px;text-align:left;transition:background .15s,color .15s}
.menu-item:hover{background:var(--blue);color:#fff}
.menu-item:disabled{opacity:.4;pointer-events:none}

/* ── KPIs + table ── */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:16px}
.kpi{padding:16px 18px;border-radius:var(--r-lg);background:var(--surface);box-shadow:0 0 0 .5px var(--hairline),var(--shadow-1)}
.kpi-label{margin-bottom:6px;font-size:12px;font-weight:500;color:var(--label-3)}
.kpi-val{font-size:28px;font-weight:700;letter-spacing:-.03em;line-height:1.1;font-variant-numeric:tabular-nums}
.table-card{display:flex;flex-direction:column;overflow:hidden;border-radius:var(--r-lg);background:var(--surface-solid);box-shadow:0 0 0 .5px var(--hairline),var(--shadow-1)}
.table-bar{display:flex;justify-content:space-between;gap:16px;padding:12px 18px;font-size:12px;color:var(--label-2);background:var(--surface);border-bottom:.5px solid var(--hairline)}
.table-bar b{margin-right:2px;font-weight:600;color:var(--label)}
.table-bar span:last-child{flex:none;color:var(--label-3)}
.table-scroll{max-height:calc(100vh - 320px);overflow:auto;-webkit-overflow-scrolling:touch;transition:opacity .25s}
.table-card.updating .table-scroll{opacity:.55}
.excel-table{width:max-content;min-width:100%;border-collapse:separate;border-spacing:0;font-size:13px;font-variant-numeric:tabular-nums}
.excel-table th,.excel-table td{padding:11px 18px;border-bottom:.5px solid var(--hairline);text-align:left;white-space:nowrap}
.excel-table .num{text-align:right}
.excel-table th{position:sticky;top:0;z-index:2;background:var(--th-bg);-webkit-backdrop-filter:blur(16px);backdrop-filter:blur(16px);font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--label-2);user-select:none}
.excel-table tbody tr{transition:background .15s}
.excel-table tbody tr:hover td{background:var(--blue-tint)}
.excel-table th.total-col{color:var(--blue)}
.excel-table td.total-col{font-weight:600;border-left:.5px solid var(--hairline);background:color-mix(in srgb,var(--blue) 5%,transparent)}
.pivot tbody tr:last-child td{position:sticky;bottom:0;z-index:1;border-top:1px solid var(--hairline-strong);border-bottom:0;background:var(--total-bg);color:var(--label);font-weight:700}
.pct-positive{color:var(--pos);font-weight:600}.pct-negative{color:var(--neg);font-weight:600}.pct-neutral{color:var(--label-3)}
.resizer{position:absolute;top:0;right:0;bottom:0;width:10px;cursor:col-resize;touch-action:none}
.resizer::after{content:"";position:absolute;right:4px;top:28%;bottom:28%;width:1px;background:var(--hairline-strong);transition:background .2s,width .2s}
.resizer:hover::after{background:var(--blue);width:2px}
.empty{display:grid;justify-items:center;gap:6px;padding:90px 24px;text-align:center;color:var(--label-3)}
.empty .ic{width:44px;height:44px;stroke-width:1.4;opacity:.7}
.empty h3{margin:10px 0 0;font-size:19px;font-weight:600;letter-spacing:-.02em;color:var(--label)}
.empty p{max-width:340px;margin:0;font-size:14px}
.empty.err h3{color:var(--neg)}

/* ── export mode (flat, white, print-safe) ── */
body.export-mode *{-webkit-backdrop-filter:none!important;backdrop-filter:none!important;box-shadow:none!important;animation:none!important}
body.export-mode #report-area{padding:24px;background:#fff}
body.export-mode .table-card{border:1px solid #d1d1d6}

/* ── upload page ── */
.upload-wrap{max-width:520px;margin:0 auto;padding:calc(var(--nav-h) + 72px) 20px 48px;animation:rise .6s var(--ease) both}
.hero-title{margin:0 0 10px;text-align:center;font-size:clamp(34px,7vw,56px);font-weight:700;letter-spacing:-.035em;line-height:1.05}
.hero-sub{margin:0 0 32px;text-align:center;font-size:17px;color:var(--label-3)}
.upload-card{display:grid;gap:16px;padding:28px;border-radius:26px;background:var(--surface);box-shadow:0 0 0 .5px var(--hairline),var(--shadow-1);-webkit-backdrop-filter:blur(24px);backdrop-filter:blur(24px)}
.dropzone{display:grid;justify-items:center;gap:6px;padding:38px 20px;border:1.5px dashed var(--hairline-strong);border-radius:18px;background:var(--fill-2);color:var(--label-3);text-align:center;cursor:pointer;transition:border-color .3s var(--ease),background .3s,transform .4s var(--spring)}
.dropzone:hover{border-color:var(--blue);color:var(--blue)}
.dropzone.drag{border-color:var(--blue);background:var(--blue-tint);color:var(--blue);transform:scale(1.015)}
.dropzone.has-file{border-style:solid;border-color:var(--blue);background:var(--blue-tint);color:var(--blue)}
.dz-title{margin-top:6px;font-size:17px;font-weight:600;color:var(--label);word-break:break-all}
.dz-sub{font-size:13px}
.alert{padding:12px 14px;border-radius:12px;background:color-mix(in srgb,var(--neg) 12%,transparent);color:var(--neg);font-size:13px;font-weight:500}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}

/* ── toast + mobile preview ── */
.toast{position:fixed;left:50%;bottom:28px;z-index:3000;padding:11px 18px;border-radius:980px;background:rgba(40,40,44,.92);color:#fff;font-size:13px;font-weight:500;transform:translate(-50%,16px);opacity:0;transition:opacity .3s,transform .4s var(--spring)}
.toast.in{opacity:1;transform:translate(-50%,0)}
.preview-modal{position:fixed;inset:0;z-index:5000;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:20px;background:rgba(0,0,0,.92);animation:fade .25s}
.preview-modal img{max-width:92%;max-height:68%;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.5)}
.preview-modal p{margin:0;color:#fff;font-size:14px}
.preview-modal .btn-primary{background:#fff;color:#1d1d1f}
@keyframes fade{from{opacity:0}to{opacity:1}}

/* ── mobile mode ── */
.only-mobile{display:none}
.mobile-mode .only-mobile{display:grid}
.mobile-mode .sidebar{width:100%;min-width:0;height:auto;max-height:4000px;overflow:hidden;border-bottom:.5px solid var(--hairline);transition:max-height .55s var(--ease),opacity .3s,visibility 0s}
.mobile-mode.sidebar-collapsed .sidebar{max-height:0;opacity:0;visibility:hidden;border:0;transition:max-height .5s var(--ease),opacity .3s,visibility 0s .5s}
.mobile-mode .sidebar-scroll{overflow:visible}
.mobile-mode .sidebar-resizer{display:none}
.mobile-mode .main{height:auto;overflow:visible;padding:20px 16px 36px}
.mobile-mode .page-title{font-size:28px}
.mobile-mode .table-scroll{max-height:70vh}
.mobile-mode .page-head{align-items:stretch;flex-direction:column}
.mobile-mode .menu-wrap .btn-primary{width:100%}
.mobile-mode .menu{left:0;right:0;transform-origin:top center}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--hairline-strong);border-radius:8px;border:2px solid transparent;background-clip:content-box}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{transition-duration:.01ms!important;animation-duration:.01ms!important}}
"""

APP_JS = r"""
(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const root = document.documentElement, body = document.body;
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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

/* ── upload page ── */
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

/* ── shared chrome (workspace) ── */
const form = $('#config-form');
if (!form) return;

const viewBtn = $('#viewToggleBtn');
const labelView = () => { viewBtn.textContent = body.classList.contains('mobile-mode') ? 'Mobile view' : 'Desktop view'; };
viewBtn.addEventListener('click', () => {
  const m = body.classList.contains('mobile-mode');
  body.classList.toggle('mobile-mode', !m); body.classList.toggle('desktop-mode', m); labelView();
});
labelView();
$('#sidebarToggle').addEventListener('click', e => {
  const c = body.classList.toggle('sidebar-collapsed');
  e.currentTarget.setAttribute('aria-expanded', String(!c));
});

const menu = $('#exportMenu'), exportBtn = $('#exportBtn'), dlExcel = $('#dlExcel');
const setMenu = open => { menu.classList.toggle('show', open); exportBtn.setAttribute('aria-expanded', String(open)); };
exportBtn.addEventListener('click', e => { e.stopPropagation(); setMenu(!menu.classList.contains('show')); });
document.addEventListener('click', e => { if (!menu.contains(e.target)) setMenu(false); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') setMenu(false); });

/* sidebar resizer (pointer events: mouse + touch + pen) */
const rz = $('#sidebarResizer');
const savedW = store.get('ap-sidebar-w');
if (savedW) root.style.setProperty('--sidebar-w', savedW + 'px');
rz.addEventListener('pointerdown', e => {
  rz.setPointerCapture(e.pointerId); rz.classList.add('resizing');
  body.style.cursor = 'col-resize'; body.style.userSelect = 'none';
});
rz.addEventListener('pointermove', e => {
  if (!rz.hasPointerCapture(e.pointerId)) return;
  root.style.setProperty('--sidebar-w', Math.min(560, Math.max(260, e.clientX)) + 'px');
});
const endResize = () => {
  rz.classList.remove('resizing'); body.style.cursor = ''; body.style.userSelect = '';
  const w = parseInt(getComputedStyle(root).getPropertyValue('--sidebar-w'), 10);
  if (w) store.set('ap-sidebar-w', w);
};
rz.addEventListener('pointerup', endResize);
rz.addEventListener('pointercancel', endResize);
rz.addEventListener('dblclick', () => { root.style.removeProperty('--sidebar-w'); store.set('ap-sidebar-w', ''); });

/* ── workspace state ── */
const filterMap = JSON.parse($('#filter-map').textContent || '[]');
const tableWrap = $('#table-wrapper'), card = $('#capture-area'), bar = $('#table-bar'), kpi = $('#kpi-banner');
const EMPTY_ICON = '<svg class="ic"><use href="#i-chart"/></svg>';
const emptyBlock = (t, m, err) => `<div class="empty${err ? ' err' : ''}">${EMPTY_ICON}<h3>${esc(t)}</h3><p>${m}</p></div>`;
const PROMPT = emptyBlock('Build your view', 'Pick at least one <b>row grouping</b> and one <b>metric</b> in the sidebar to compile your report.');
let ctrl = null, timer = null, lastParams = null;

const checked = name => $$(`input[name="${name}"]:checked`);
const isShown = r => r.dataset.casc !== '1' && r.dataset.srch !== '1';

function updateBadges(){
  const sd = $('#start_date'), ed = $('#end_date');
  $$('[data-badge-for]').forEach(b => {
    const k = b.dataset.badgeFor;
    const n = k === '__date' ? ((sd && sd.value) || (ed && ed.value) ? 1 : 0) : checked(k).length;
    const was = b.textContent;
    b.hidden = n === 0;
    b.textContent = n;
    if (n && was !== String(n)) { b.style.animation = 'none'; void b.offsetWidth; b.style.animation = ''; }
  });
}

function schedule(delay = 90){ clearTimeout(timer); timer = setTimeout(update, delay); }

async function update(){
  const fd = new FormData(form);
  const mode = $('input[name="view_mode_toggle"]:checked').value;
  fd.append('view_mode', mode);
  $$('[data-structural]').forEach(el => el.classList.toggle('is-disabled', mode === 'raw'));
  updateBadges();

  if (mode === 'dashboard' && (!fd.getAll('index_cols').length || !fd.getAll('agg_funcs').length)) {
    if (ctrl) ctrl.abort();
    body.classList.remove('loading'); card.classList.remove('updating');
    kpi.hidden = true; bar.hidden = true; tableWrap.innerHTML = PROMPT;
    lastParams = null; dlExcel.disabled = true;
    return;
  }

  if (ctrl) ctrl.abort();
  const mine = ctrl = new AbortController();
  body.classList.add('loading'); card.classList.add('updating');
  try {
    const res = await fetch('/calculate', { method: 'POST', body: fd, signal: mine.signal });
    const d = await res.json();
    if (res.ok) {
      kpi.innerHTML = d.kpi_html || ''; kpi.hidden = !d.kpi_html;
      bar.innerHTML = `<span>${d.filter_text}</span><span>${esc(d.status || '')}</span>`; bar.hidden = false;
      tableWrap.innerHTML = d.table_html;
      addResizers();
      lastParams = new URLSearchParams(fd).toString();
      dlExcel.disabled = false;
    } else {
      kpi.hidden = true; bar.hidden = true;
      tableWrap.innerHTML = emptyBlock('Something went wrong', esc(d.error || 'Unknown error'), true);
      lastParams = null; dlExcel.disabled = true;
    }
  } catch (err) {
    if (err.name === 'AbortError') return;
    tableWrap.innerHTML = emptyBlock('Connection problem', 'Could not reach the server. Please try again.', true);
  } finally {
    if (mine === ctrl) { body.classList.remove('loading'); card.classList.remove('updating'); }
  }
}

/* cascading filters: SPC → SEG1 → Family */
function cascade(){
  const spc = new Set(checked('spc_filters').map(i => i.value));
  const apply = (name, valid) => {
    $$('.row', $(`[data-list="${name}"]`) || document.createElement('div')).forEach(r => {
      const hide = !valid.has(r.dataset.val);
      r.dataset.casc = hide ? '1' : '0';
      if (hide) r.querySelector('input').checked = false;
    });
  };
  apply('seg1_filters', new Set(filterMap.filter(r => !spc.size || spc.has(r.spc)).map(r => r.seg)));
  const seg = new Set(checked('seg1_filters').map(i => i.value));
  apply('family_filters', new Set(filterMap.filter(r => (!spc.size || spc.has(r.spc)) && (!seg.size || seg.has(r.seg))).map(r => r.fam)));
}

/* delegated events */
form.addEventListener('submit', e => e.preventDefault());
form.addEventListener('change', e => {
  const t = e.target;
  if (t.type === 'date') $$('.chip').forEach(c => c.classList.remove('active'));
  if (t.name === 'spc_filters' || t.name === 'seg1_filters') cascade();
  schedule();
});
form.addEventListener('input', e => {
  const q = e.target.dataset && e.target.dataset.search;
  if (!q) return;
  const needle = e.target.value.trim().toLowerCase();
  $$('.row', $(`[data-list="${q}"]`)).forEach(r => { r.dataset.srch = r.dataset.val.toLowerCase().includes(needle) ? '0' : '1'; });
});
form.addEventListener('click', e => {
  const head = e.target.closest('.acc-head');
  if (head) {
    const open = head.parentElement.classList.toggle('open');
    head.setAttribute('aria-expanded', String(open));
    return;
  }
  const sel = e.target.closest('[data-select]');
  if (sel) {
    const on = sel.dataset.on === '1', name = sel.dataset.select;
    $$(`input[name="${name}"]`).forEach(i => { if (!on || isShown(i.closest('.row'))) i.checked = on; });
    if (name === 'spc_filters' || name === 'seg1_filters') cascade();
    schedule(0);
    return;
  }
  const chip = e.target.closest('.chip');
  if (chip) preset(chip.dataset.preset, chip);
});
$$('input[name="view_mode_toggle"]').forEach(r => r.addEventListener('change', () => schedule(0)));

/* date presets */
const iso = d => new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
function preset(key, chip){
  $$('.chip').forEach(c => c.classList.toggle('active', c === chip && key !== 'all'));
  const t = new Date(); let s = new Date(), e = new Date();
  if (key === 'last7') s.setDate(t.getDate() - 6);
  else if (key === 'last30') s.setDate(t.getDate() - 29);
  else if (key === 'mtd') s = new Date(t.getFullYear(), t.getMonth(), 1);
  else if (key === 'prev_month') { s = new Date(t.getFullYear(), t.getMonth() - 1, 1); e = new Date(t.getFullYear(), t.getMonth(), 0); }
  else if (key === 'ytd') s = new Date(t.getFullYear(), 0, 1);
  $('#start_date').value = key === 'all' ? '' : iso(s);
  $('#end_date').value = key === 'all' ? '' : iso(e);
  schedule(0);
}

/* reset */
$('#resetBtn').addEventListener('click', () => {
  form.reset();
  $$('.chip').forEach(c => c.classList.remove('active'));
  $$('.row').forEach(r => { delete r.dataset.casc; delete r.dataset.srch; });
  $('#view_dash').checked = true;
  schedule(0);
});

/* column resizing */
function addResizers(){
  $$('.excel-table th', tableWrap).forEach(th => {
    if (!th.querySelector('.resizer')) th.appendChild(Object.assign(document.createElement('div'), { className: 'resizer' }));
  });
}
tableWrap.addEventListener('pointerdown', e => {
  const h = e.target.closest('.resizer');
  if (!h) return;
  const th = h.parentElement, sx = e.clientX, sw = th.offsetWidth;
  h.setPointerCapture(e.pointerId);
  const move = ev => { th.style.width = th.style.minWidth = Math.max(60, sw + ev.clientX - sx) + 'px'; };
  const up = () => { h.removeEventListener('pointermove', move); h.removeEventListener('pointerup', up); };
  h.addEventListener('pointermove', move); h.addEventListener('pointerup', up);
  e.preventDefault(); e.stopPropagation();
});

/* export: Excel (server recomputes from the same params, so it is always in sync) */
dlExcel.addEventListener('click', () => { setMenu(false); if (lastParams) location.href = '/download?' + lastParams; });

/* export: image (library is lazy-loaded on first use) */
let d2i = null;
const loadD2I = () => d2i || (d2i = new Promise((ok, fail) => {
  const s = document.createElement('script');
  s.src = 'https://cdnjs.cloudflare.com/ajax/libs/dom-to-image/2.6.0/dom-to-image.min.js';
  s.onload = ok; s.onerror = () => { d2i = null; fail(new Error('load')); };
  document.head.appendChild(s);
}));
$('#dlImage').addEventListener('click', async () => {
  setMenu(false);
  const area = $('#report-area');
  const prev = [tableWrap.style.maxHeight, tableWrap.style.overflow];
  try {
    await loadD2I();
    tableWrap.style.maxHeight = 'none'; tableWrap.style.overflow = 'visible';
    body.classList.add('export-mode');
    await new Promise(r => setTimeout(r, 350));
    const url = await domtoimage.toPng(area, { bgcolor: '#ffffff', cacheBust: true });
    if (/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent)) {
      const m = document.createElement('div'); m.className = 'preview-modal';
      m.innerHTML = '<button class="btn-primary" type="button">Close preview</button><p>Press and hold the image to save it to Photos.</p><img alt="Report">';
      m.querySelector('img').src = url;
      m.querySelector('button').onclick = () => m.remove();
      body.appendChild(m);
    } else {
      const a = document.createElement('a'); a.download = 'Executive_Report.png'; a.href = url; a.click();
    }
  } catch (err) {
    console.error(err); toast('Could not export the image. Please try again.');
  } finally {
    tableWrap.style.maxHeight = prev[0]; tableWrap.style.overflow = prev[1];
    body.classList.remove('export-mode');
  }
});

updateBadges();
update();
})();
"""

ASSET_VERSION = hashlib.md5((APP_CSS + APP_JS).encode()).hexdigest()[:8]

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1")
