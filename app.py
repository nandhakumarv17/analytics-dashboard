"""Analytics Pro - upload a sheet, slice it, pivot it, chart it, export it.

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
    df.columns = [str(c).strip() for c in df.columns]
    d = pick_date_col(list(df.columns))
    if d and not pd.api.types.is_numeric_dtype(df[d]):
        df[d] = pd.to_datetime(df[d], errors="coerce", dayfirst=True)
    c = detect_columns(df)
    
    # Fill NAs for all categorical columns so they appear in filters
    for col in df.select_dtypes(exclude="number").columns:
        s = df[col]
        df[col] = s.astype(object).where(s.isna(), s.astype(str))
    return df


def detect_columns(df):
    cols = list(df.columns)
    date = pick_date_col(cols)
    if date and not pd.api.types.is_datetime64_any_dtype(df[date]):
        date = ""
    num = df.select_dtypes(include="number").columns.tolist()
    return {
        "date": date,
        "value": "Tentative DP" if "Tentative DP" in num else (num[0] if num else ""),
    }


def build_context(df):
    c = detect_columns(df)
    all_cats = df.select_dtypes(exclude="number").columns.tolist()
    
    min_d = max_d = "N/A"
    if c["date"]:
        s = df[c["date"]]
        if s.notna().any():
            min_d, max_d = s.min().strftime("%d-%b-%y"), s.max().strftime("%d-%b-%y")
            
    return {
        **c,
        "grouping": all_cats,
        "all_cols": df.columns.tolist(),
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
    os.replace(tmp, DATA_FILE_PATH)
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
        
        weeks = params.getlist("week_num")
        if weeks and pd.api.types.is_datetime64_any_dtype(df[dc]):
            week_masks = []
            for w in weeks:
                w = int(w)
                if w == 1: week_masks.append(df[dc].dt.day <= 7)
                elif w == 2: week_masks.append((df[dc].dt.day > 7) & (df[dc].dt.day <= 14))
                elif w == 3: week_masks.append((df[dc].dt.day > 14) & (df[dc].dt.day <= 21))
                elif w == 4: week_masks.append((df[dc].dt.day > 21) & (df[dc].dt.day <= 28))
                elif w == 5: week_masks.append(df[dc].dt.day > 28)
            if week_masks:
                combined = week_masks[0]
                for wm in week_masks[1:]: combined = combined | wm
                add(combined)
            texts.append(f"Weeks: {', '.join([f'W{w}' for w in weeks])}")
                
        if start is not None or end is not None:
            a = start.strftime("%d-%b-%y") if start is not None else "Start"
            b = end.strftime("%d-%b-%y") if end is not None else "End"
            texts.append(f"{a} to {b}")

    return (df if mask is None else df[mask]), texts


def build_view(state, params, want_export=False):
    """Returns (payload, export_df, http_status)."""
    df, ctx = state["df"], state["ctx"]
    mode = params.get("view_mode", "dashboard")
    index_cols = params.getlist("index_cols")
    columns_cols = params.getlist("columns_cols")
    agg_funcs = params.getlist("agg_funcs")

    if mode != "raw" and (not index_cols or not agg_funcs):
        return {"error": "Select at least one row grouping and one metric."}, None, 400

    dff, texts = apply_filters(df, ctx, params)
    
    dynamic_title = f"Sales Analysis by {' & '.join(index_cols)}" if index_cols else "Executive Dashboard"
    date_subtitle = " · ".join(texts) if texts else "All Time"
    value_col = ctx["value"]

    kpi = ""
    if len(dff) and value_col:
        active = format_indian_number(dff[index_cols[0]].nunique()) if index_cols and index_cols[0] in dff.columns else "N/A"
        kpi = ('<div class="kpi"><div class="kpi-label">Total Volume</div>'
               f'<div class="kpi-val">{format_indian_number(dff[value_col].sum())}</div></div>'
               '<div class="kpi"><div class="kpi-label">Records</div>'
               f'<div class="kpi-val">{format_indian_number(len(dff))}</div></div>'
               '<div class="kpi"><div class="kpi-label">Active Entities</div>'
               f'<div class="kpi-val">{active}</div></div>')

    if dff.empty:
        return {"table_html": empty_block("No matching data", "Try widening the date range."),
                "dyn_title": dynamic_title, "dyn_date": date_subtitle, "kpi_html": ""}, None, 200

    # ── RAW ─────────────────────────────────────────────────────────
    if mode == "raw":
        raw_cols = params.getlist("raw_cols")
        if not raw_cols: raw_cols = df.columns.tolist()
        shown = dff[raw_cols]
        headers = [str(c) for c in shown.columns]
        columns = [col_to_cells(shown[c]) for c in shown.columns]
        numeric = {i for i, c in enumerate(shown.columns) if pd.api.types.is_numeric_dtype(shown[c])}
        return {"table_html": render_table(headers, columns, "raw", numeric),
                "dyn_title": "Raw Data View", "dyn_date": date_subtitle, "kpi_html": kpi}, \
            (shown if want_export else None), 200

    # ── PIVOT / CHART ───────────────────────────────────────────────────────
    if not value_col:
        return {"error": "No numeric column found to aggregate."}, None, 400

    aggs = [a for a in ("sum", "count", "mean") if a in agg_funcs] or ["sum"]
    
    kwargs = {'data': dff, 'index': index_cols, 'values': [value_col], 'aggfunc': aggs}
    if columns_cols: kwargs['columns'] = columns_cols
    
    g = pd.pivot_table(**kwargs).reset_index().fillna(0)
    
    if g.empty:
        return {"table_html": empty_block("No groups to show", "The selected grouping has only empty values."),
                "dyn_title": dynamic_title, "dyn_date": date_subtitle, "kpi_html": kpi}, None, 200

    new_headers = []
    for c in g.columns:
        if isinstance(c, tuple):
            if c[0] in index_cols and all(x == '' for x in c[1:]): 
                new_headers.append(str(c[0]))
            else:
                parts = [str(x) for x in c if str(x) and str(x) not in [value_col, 'sum', 'count', 'mean']]
                new_headers.append(" - ".join(parts) if parts else str(c[-1]))
        else: 
            new_headers.append(str(c))
    
    g.columns = new_headers
    metric_cols = [c for c in g.columns if c not in index_cols]

    show_total = params.get("show_row_total") == "true"
    if show_total and len(metric_cols) > 1 and not ('sum' in agg_funcs and 'count' in agg_funcs):
        g["TOTAL"] = g[metric_cols].sum(axis=1)
        metric_cols.append("TOTAL")

    # Prepare Chart.js Data (Top 15 limit for legibility)
    chart_data = None
    if mode == "chart":
        chart_df = g.sort_values(by=metric_cols[0], ascending=False).head(15) if metric_cols else g.head(15)
        labels = chart_df[index_cols[0]].astype(str).tolist() if index_cols else ["Total"]
        datasets = [{"label": m, "data": chart_df[m].tolist(), "backgroundColor": "#0071e3"} for m in metric_cols if m != "TOTAL"]
        chart_data = {"labels": labels, "datasets": datasets}

    # Format output
    ordered = index_cols + metric_cols
    total_idx = len(ordered) - 1 if "TOTAL" in ordered else -1
    
    totals_row = {c: g[c].sum() if c in metric_cols else ("GRAND TOTAL" if c == index_cols[0] else "") for c in ordered}
    
    columns, numeric = [], set()
    for i, h in enumerate(ordered):
        s = g[h]
        if h in index_cols:
            cells = col_to_cells(s) + [totals_row[h]]
        else:
            cells = [format_indian_number(v) for v in s] + [format_indian_number(totals_row[h])]
            numeric.add(i)
        columns.append(cells)

    export = None
    if want_export:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            export = pd.concat([g[ordered], pd.DataFrame([totals_row], columns=ordered)], ignore_index=True)

    return {"table_html": render_table(ordered, columns, "pivot", numeric, total_idx),
            "chart_data": chart_data,
            "dyn_title": dynamic_title,
            "dyn_date": date_subtitle, 
            "kpi_html": kpi}, export, 200


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
    except Exception as exc:  # noqa: BLE001 
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


@app.get("/assets/app.css")
def asset_css():
    return Response(APP_CSS, mimetype="text/css", headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/assets/app.js")
def asset_js():
    return Response(APP_JS, mimetype="application/javascript", headers={"Cache-Control": "public, max-age=31536000, immutable"})


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
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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

{% macro checklist(name, items, required=False) %}
<div class="tools">
  <label class="search"><svg class="ic"><use href="#i-search"/></svg><input type="search" placeholder="Search" autocomplete="off" data-search="{{ name }}"></label>
  <span class="tool-btns">
    <button type="button" class="btn-micro" data-select="{{ name }}" data-on="1">All</button>
    <button type="button" class="btn-micro" data-select="{{ name }}" data-on="0">Clear</button>
  </span>
</div>
<div class="list" data-list="{{ name }}">
  {% for it in items %}<label class="row" data-val="{{ it }}"><input type="checkbox" name="{{ name }}" value="{{ it }}" {% if required and loop.first %}checked{% endif %}><span class="box"></span><span class="label" title="{{ it }}">{{ it }}</span></label>{% endfor %}
</div>
{% endmacro %}

<header class="nav">
  <div class="nav-left">
    <button type="button" class="icon-btn only-mobile" id="sidebarToggle" aria-label="Menu" aria-expanded="true"><svg class="ic"><use href="#i-sliders"/></svg></button>
    <span class="brand"><span class="brand-mark"></span>Analytics Pro</span>
  </div>
  <div style="display:flex; gap:12px; align-items:center;">
    <button type="button" class="pill-btn" onclick="document.body.classList.toggle('dark-mode')">Dark Mode</button>
    <button type="button" class="pill-btn" id="viewToggleBtn">Mobile view</button>
  </div>
</header>
<div id="loadbar" aria-hidden="true"></div>

<div class="app">
  <aside class="sidebar" id="appSidebar">
    <div class="sidebar-head">
      <div class="head-row">
        <h2>Workspace</h2>
        <button type="button" class="btn-text" id="resetBtn"><svg class="ic"><use href="#i-reset"/></svg>Reset</button>
      </div>
    </div>

    <form id="config-form" class="sidebar-scroll" autocomplete="off">
      {% call acc('Timeline', '__date', True) %}
        {% if ctx.date %}
        <div class="chips">
          <button type="button" class="chip" data-preset="mtd">Month to date</button>
          <button type="button" class="chip" data-preset="ytd">Year to date</button>
          <button type="button" class="chip" data-preset="last7">7 days</button>
        </div>
        <div class="date-grid">
          <div class="field"><label>From</label><input type="date" name="start_date" id="start_date"></div>
          <div class="field"><label>To</label><input type="date" name="end_date" id="end_date"></div>
        </div>
        <div class="chips" style="margin-top: 12px;">
          <label class="row" style="padding:0; min-height:0; background:none; border:none;"><input type="checkbox" name="week_num" value="1"><span class="chip">W1</span></label>
          <label class="row" style="padding:0; min-height:0; background:none; border:none;"><input type="checkbox" name="week_num" value="2"><span class="chip">W2</span></label>
          <label class="row" style="padding:0; min-height:0; background:none; border:none;"><input type="checkbox" name="week_num" value="3"><span class="chip">W3</span></label>
          <label class="row" style="padding:0; min-height:0; background:none; border:none;"><input type="checkbox" name="week_num" value="4"><span class="chip">W4</span></label>
          <label class="row" style="padding:0; min-height:0; background:none; border:none;"><input type="checkbox" name="week_num" value="5"><span class="chip">W5</span></label>
        </div>
        {% else %}<p class="muted">No date column detected.</p>{% endif %}
      {% endcall %}

      {% call acc('Rows (Y-Axis)', 'index_cols', True, True) %}{{ checklist('index_cols', ctx.grouping, True) }}{% endcall %}
      {% call acc('Columns (X-Axis)', 'columns_cols', False, True) %}{{ checklist('columns_cols', ctx.grouping) }}{% endcall %}

      {% call acc('Metrics', 'agg_funcs', True, True) %}
        <div class="list static">
          <label class="row"><input type="checkbox" name="agg_funcs" value="sum" checked><span class="box"></span><span class="label">Sum total<small>Total value per group</small></span></label>
          <label class="row"><input type="checkbox" name="agg_funcs" value="count"><span class="box"></span><span class="label">Count<small>Number of records</small></span></label>
        </div>
        <div class="list static" id="total_wrapper">
          <label class="row switch"><span class="label">Row totals<small>Add a TOTAL column</small></span><input type="checkbox" id="show_total_cb" name="show_row_total" value="true" checked><span class="track"><span class="knob"></span></span></label>
        </div>
      {% endcall %}
      
      <div id="raw_col_picker" style="display:none;">
          {% call acc('Raw Data Columns', 'raw_cols', True) %}{{ checklist('raw_cols', ctx.all_cols) }}{% endcall %}
      </div>
    </form>

    <div class="sidebar-foot">
      <a class="btn-tinted" href="/upload"><svg class="ic"><use href="#i-upload"/></svg>Upload new file</a>
    </div>
  </aside>

  <div class="sidebar-resizer" id="sidebarResizer"></div>

  <main class="main">
    <div class="page-head">
      <div>
        <h1 class="page-title" id="dashTitle">Executive Dashboard</h1>
        <div style="font-size:13px; color:var(--label-3); margin-top:-10px; margin-bottom:12px; font-weight:600;" id="dashDate">All Time</div>
        <div class="seg">
          <span class="seg-thumb"></span>
          <input type="radio" id="view_dash" name="view_mode_toggle" value="dashboard" checked><label for="view_dash">Pivot</label>
          <input type="radio" id="view_chart" name="view_mode_toggle" value="chart"><label for="view_chart">Chart</label>
          <input type="radio" id="view_raw" name="view_mode_toggle" value="raw"><label for="view_raw">Raw data</label>
        </div>
      </div>
      <div class="menu-wrap" id="exportWrap">
        <button type="button" class="btn-primary" id="exportBtn"><svg class="ic"><use href="#i-share"/></svg>Export</button>
        <div class="menu" id="exportMenu">
          <button type="button" class="menu-item" id="dlImage"><svg class="ic"><use href="#i-image"/></svg>Save image</button>
          <button type="button" class="menu-item" id="dlExcel"><svg class="ic"><use href="#i-sheet"/></svg>Download Excel</button>
        </div>
      </div>
    </div>

    <div id="report-area">
      <div id="kpi-banner" class="kpis" hidden></div>
      <div id="capture-area" class="table-card">
        <div id="table-wrapper" class="table-scroll"></div>
        <div id="chart-wrapper" style="display:none; padding:20px; height: 60vh;"><canvas id="dataChart"></canvas></div>
      </div>
    </div>
  </main>
</div>
</body></html>"""

APP_CSS = r"""
:root {
  color-scheme:light;
  --bg:#f2f2f7;--surface:rgba(255,255,255,.78);--surface-solid:#fff;--sidebar:rgba(255,255,255,.85);
  --nav-bg:rgba(255,255,255,.85);--menu-bg:rgba(255,255,255,.95);--th-bg:rgba(240,240,245,.95);
  --hairline:rgba(0,0,0,.08);--hairline-strong:rgba(0,0,0,.15);
  --fill:rgba(120,120,128,.1);--fill-2:rgba(120,120,128,.05);--seg-thumb:#fff;
  --label:#1d1d1f;--label-2:#515154;--label-3:#86868b;
  --blue:#0071e3;--blue-h:#0077ed;--blue-a:#006edb;--blue-tint:rgba(0,113,227,.1);--total-bg:rgba(0,113,227,.08);
  --green:#34c759;--pos:#1f8a3c;--neg:#d70015;
  --shadow-1:0 10px 30px rgba(0,0,0,.05);--shadow-2:0 16px 48px rgba(0,0,0,.16);
}
body.dark-mode {
  color-scheme:dark;
  --bg:#000000;--surface:rgba(28,28,30,.75);--surface-solid:#1c1c1e;--sidebar:rgba(20,20,22,.85);
  --nav-bg:rgba(20,20,22,.85);--menu-bg:rgba(44,44,46,.95);--th-bg:rgba(44,44,46,.95);
  --hairline:rgba(255,255,255,.15);--hairline-strong:rgba(255,255,255,.25);
  --fill:rgba(120,120,128,.2);--fill-2:rgba(120,120,128,.1);--seg-thumb:#636366;
  --label:#f5f5f7;--label-2:#c7c7cc;--label-3:#8e8e93;
  --blue:#0a84ff;--blue-h:#409cff;--blue-a:#006edb;--blue-tint:rgba(10,132,255,.15);--total-bg:rgba(10,132,255,.15);
  --green:#30d158;--pos:#32d74b;--neg:#ff453a;
  --shadow-1:0 10px 30px rgba(0,0,0,.5);
}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display",sans-serif;background:var(--bg);color:var(--label);-webkit-font-smoothing:antialiased; transition: background 0.3s, color 0.3s;}
button,input{font:inherit;color:inherit;letter-spacing:inherit}
button{cursor:pointer;-webkit-tap-highlight-color:transparent}
:focus-visible{outline:3px solid color-mix(in srgb,var(--blue) 45%,transparent);outline-offset:1px}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.ic{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
.ic-lg{width:40px;height:40px;stroke-width:1.5}
.muted{margin:0;font-size:13px;color:var(--label-3)}
.glass,.nav,.sidebar,.acc,.kpi,.menu,.table-bar{-webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px)}

.nav{position:fixed;inset:0 0 auto 0;height:60px;z-index:1000;display:flex;align-items:center;justify-content:space-between;padding:0 20px;background:var(--nav-bg);border-bottom:1px solid var(--hairline)}
.nav-left{display:flex;align-items:center;gap:8px}
.brand{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:700;letter-spacing:-.015em}
.brand-mark{width:22px;height:22px;border-radius:7px;background:linear-gradient(135deg,#5ac8fa,#0071e3 55%,#5e5ce6);}
.pill-btn{height:32px;padding:0 14px;border:1px solid var(--hairline);border-radius:16px;background:rgba(120,120,128,0.1);font-size:12px;font-weight:600;transition:0.2s;}
.pill-btn:hover{background:rgba(120,120,128,0.2);}
.icon-btn{width:34px;height:34px;display:none;place-items:center;border:0;border-radius:10px;background:none;color:var(--blue);transition:0.2s}
.icon-btn:hover{background:var(--blue-tint)} 

body.desktop-mode{overflow:hidden}
.desktop-mode .app{display:flex;height:100vh;padding-top:60px}
.mobile-mode .app{display:block;padding-top:60px}
.sidebar{display:flex;flex-direction:column;flex:none;width:340px;min-width:260px;height:calc(100vh - 60px);background:var(--sidebar)}
.sidebar-head{padding:22px 20px 12px}
.head-row{display:flex;align-items:center;justify-content:space-between}
.sidebar-head h2{margin:0;font-size:22px;font-weight:700;letter-spacing:-.025em;line-height:1.15}
.sidebar-scroll{flex:1;overflow-y:auto;padding:4px 14px 20px;overscroll-behavior:contain;scrollbar-gutter:stable}
.sidebar-foot{padding:12px 14px;border-top:1px solid var(--hairline)}
.sidebar-resizer{position:relative;flex:none;width:1px;background:var(--hairline);cursor:col-resize;transition:0.2s}
.sidebar-resizer:hover,.sidebar-resizer.resizing{background:var(--blue);box-shadow:0 0 0 1px var(--blue)}
.main{flex:1;min-width:0;height:calc(100vh - 60px);overflow-y:auto;padding:28px 36px 40px}
.page-head{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:16px;margin-bottom:20px}
.page-title{margin:0;font-size:28px;font-weight:700;letter-spacing:-.03em;line-height:1.1}

.acc{margin-bottom:10px;border-radius:12px;background:var(--surface);box-shadow:var(--shadow-1);border:1px solid var(--hairline);overflow:hidden;transition:0.3s}
.acc.is-disabled{opacity:.4;pointer-events:none}
.acc-head{display:flex;align-items:center;gap:8px;width:100%;padding:13px 14px;border:0;background:none;text-align:left;font-size:13px;font-weight:600;transition:0.2s}
.acc-head:hover{background:var(--fill-2)}
.acc-title{flex:1}
.chev{width:14px;height:14px;color:var(--label-3);transition:transform .4s}
.acc.open .chev{transform:rotate(90deg)}
.acc-panel{display:grid;grid-template-rows:0fr;transition:0.45s}
.acc.open .acc-panel{grid-template-rows:1fr}
.acc-inner{min-height:0;overflow:hidden;}
.acc-body{padding:2px 12px 12px}

.tools{display:flex;align-items:center;gap:8px;margin:0 0 10px}
.search{position:relative;flex:1;min-width:0}
.search .ic{position:absolute;left:9px;top:50%;width:14px;height:14px;transform:translateY(-50%);color:var(--label-3)}
.search input{width:100%;height:30px;padding:0 10px 0 28px;border:0;border-radius:8px;background:var(--fill);font-size:13px;}
.btn-micro{height:26px;padding:0 11px;border:0;border-radius:13px;background:var(--blue-tint);color:var(--blue);font-size:12px;font-weight:600;}
.list{max-height:200px;overflow-y:auto;border-radius:10px;background:var(--surface-solid); border:1px solid var(--hairline)}
.list.static{max-height:none;overflow:visible}
.row{position:relative;display:flex;align-items:center;gap:11px;min-height:36px;padding:8px 12px;font-size:13px;cursor:pointer;}
.row:hover{background:var(--fill-2)} 
.row[data-casc="1"],.row[data-srch="1"]{display:none}
.row .label{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; font-weight:500;}
.row small{display:block;margin-top:1px;font-size:11px;color:var(--label-3);white-space:normal}
.row input{position:absolute;opacity:0;pointer-events:none}
.box{flex:none;width:18px;height:18px;display:grid;place-items:center;border-radius:5px;border:1.5px solid var(--label-3);transition:0.25s}
.row input:checked+.box{background:var(--blue);border-color:var(--blue)}
.box::after{content:"";width:8px;height:4px;margin-top:-2px;border:2px solid #fff;border-top:0;border-right:0;transform:rotate(-45deg) scale(0);transition:0.35s}
.row input:checked+.box::after{transform:rotate(-45deg) scale(1)}
.switch .track{position:relative;flex:none;width:44px;height:26px;border-radius:13px;background:var(--fill);}
.switch .knob{position:absolute;top:2px;left:2px;width:22px;height:22px;border-radius:50%;background:#fff;box-shadow:0 2px 5px rgba(0,0,0,.28);transition:0.4s}
.switch input:checked+.track{background:var(--green)}
.switch input:checked+.track .knob{transform:translateX(18px)}

.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.chip{height:28px;display:flex;align-items:center;padding:0 12px;border:0;border-radius:14px;background:var(--fill);font-size:12px;font-weight:600;transition:0.2s}
.row input:checked+.chip{background:var(--blue);color:#fff}
.date-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.field label{display:block;margin:0 0 4px 2px;font-size:11px;font-weight:700;color:var(--label-3)}
.field input{width:100%;height:36px;padding:0 8px;border:1px solid var(--hairline);border-radius:9px;background:var(--surface-solid);font-size:13px;}

.btn-primary{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:36px;padding:0 20px;border:0;border-radius:980px;background:var(--blue);color:#fff;font-size:13px;font-weight:600;box-shadow: 0 4px 10px var(--blue-tint);}
.btn-tinted{display:flex;align-items:center;justify-content:center;gap:8px;height:38px;border-radius:10px;background:var(--fill);color:var(--label);font-size:13px;font-weight:600;text-decoration:none;}
.btn-text{display:inline-flex;align-items:center;gap:5px;padding:5px 8px;border:0;border-radius:8px;background:none;color:var(--blue);font-size:13px;font-weight:600;}

.seg{position:relative;display:inline-grid;grid-auto-flow:column;grid-auto-columns:1fr;padding:3px;border-radius:12px;background:var(--fill);}
.seg-thumb{position:absolute;z-index:-1;top:3px;bottom:3px;left:3px;width:calc(33.333% - 2px);border-radius:9px;background:var(--seg-thumb);box-shadow:0 3px 8px rgba(0,0,0,.12);transition:0.4s}
.seg:has(#view_chart:checked) .seg-thumb{transform:translateX(100%)}
.seg:has(#view_raw:checked) .seg-thumb{transform:translateX(200%)}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg label{padding:6px 20px;text-align:center;font-size:13px;font-weight:600;color:var(--label-2);cursor:pointer; transition:0.25s}
.seg input:checked+label{color:var(--label)}

.menu-wrap{position:relative}
.menu{position:absolute;right:0;top:calc(100% + 8px);z-index:50;min-width:180px;padding:6px;border-radius:14px;background:var(--menu-bg);border:1px solid var(--hairline);box-shadow:var(--shadow-2);opacity:0;visibility:hidden;transform:translateY(-6px);transition:0.2s}
.menu.show{opacity:1;visibility:visible;transform:none;}
.menu-item{display:flex;align-items:center;gap:10px;width:100%;padding:10px;border:0;border-radius:8px;background:none;font-size:13px;font-weight:500;}
.menu-item:hover{background:var(--blue);color:#fff}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:16px}
.kpi{padding:16px 18px;border-radius:16px;background:var(--surface);border:1px solid var(--hairline);box-shadow:var(--shadow-1)}
.kpi-label{margin-bottom:6px;font-size:11px;font-weight:700;color:var(--label-3);text-transform:uppercase;letter-spacing:0.05em;}
.kpi-val{font-size:26px;font-weight:700;letter-spacing:-.03em;color:var(--label)}
.table-card{display:flex;flex-direction:column;overflow:hidden;border-radius:16px;background:var(--surface-solid);border:1px solid var(--hairline);box-shadow:var(--shadow-1)}
.table-scroll{max-height:calc(100vh - 320px);overflow:auto; transition:0.25s}

.excel-table{width:max-content;min-width:100%;border-collapse:collapse;font-size:13px; text-align:left;}
.excel-table th,.excel-table td{padding:14px 16px;border-bottom:1px solid var(--hairline); white-space:nowrap;}
.excel-table th{position:sticky;top:0;z-index:2;background:var(--th-bg);font-size:11px;font-weight:700;text-transform:uppercase;color:var(--label);letter-spacing:0.05em; border-bottom:1px solid var(--hairline-strong)}
.excel-table th:first-child,.excel-table td:first-child{position:sticky;left:0;z-index:20;background:var(--surface-solid);font-weight:600;box-shadow:1px 0 0 var(--hairline);}
.excel-table th:first-child{z-index:30;background:var(--th-bg);}
.excel-table tbody tr:hover td{background:rgba(120,120,128,0.05)}
.excel-table tbody tr:hover td:first-child{background:var(--surface)}
.excel-table td.total-col{font-weight:700;background:var(--total-bg);color:var(--total-text);box-shadow:inset 1px 0 0 rgba(0,113,227,0.15)}
.excel-table tbody tr:last-child td{font-weight:700;background:var(--total-bg);color:var(--total-text);border-top:2px solid var(--blue);position:sticky;bottom:0;z-index:15;}
.excel-table tbody tr:last-child td:first-child{z-index:25;}

.empty{display:grid;justify-items:center;gap:6px;padding:90px 24px;text-align:center;color:var(--label-3)}
.empty .ic{width:44px;height:44px;opacity:0.7}
.empty h3{margin:10px 0 0;font-size:18px;font-weight:600;color:var(--label)}

body.export-mode #report-area{padding:24px;background:var(--bg)}
body.export-mode .table-card{border:1px solid var(--hairline-strong)}

.upload-wrap{max-width:500px;margin:0 auto;padding:120px 20px 48px;animation:rise 0.6s both}
.hero-title{margin:0 0 10px;text-align:center;font-size:42px;font-weight:700;letter-spacing:-.03em;}
.hero-sub{margin:0 0 32px;text-align:center;font-size:16px;color:var(--label-3)}
.upload-card{display:grid;gap:16px;padding:32px;border-radius:24px;background:var(--surface);border:1px solid var(--hairline);box-shadow:var(--shadow-1);}
.dropzone{display:grid;justify-items:center;gap:6px;padding:38px 20px;border:2px dashed var(--hairline-strong);border-radius:16px;background:var(--fill-2);color:var(--label-3);text-align:center;cursor:pointer;transition:0.3s}
.dropzone:hover{border-color:var(--blue);color:var(--blue)}
.dz-title{margin-top:6px;font-size:16px;font-weight:600;color:var(--label);}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}

.mobile-mode .only-mobile{display:grid}
.mobile-mode .sidebar{width:100%;min-width:0;height:auto;max-height:4000px;border-bottom:1px solid var(--hairline);transition:0.5s}
.mobile-mode.sidebar-collapsed .sidebar{max-height:0;opacity:0;border:0;}
.mobile-mode .sidebar-resizer{display:none}
.mobile-mode .main{height:auto;overflow:visible;padding:20px 16px 36px}
.mobile-mode .page-title{font-size:24px}
.mobile-mode .table-scroll{max-height:70vh}
.mobile-mode .page-head{flex-direction:column}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--hairline-strong);border-radius:6px;}
"""

APP_JS = r"""
(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const body = document.body;
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Navigation & Theme
const viewBtn = $('#viewToggleBtn');
const labelView = () => { viewBtn.textContent = body.classList.contains('mobile-mode') ? 'Mobile view' : 'Desktop view'; };
viewBtn.addEventListener('click', () => {
    const m = body.classList.contains('mobile-mode');
    body.classList.toggle('mobile-mode', !m); body.classList.toggle('desktop-mode', m); labelView();
});
labelView();
$('#sidebarToggle').addEventListener('click', e => { body.classList.toggle('sidebar-collapsed'); });

const menu = $('#exportMenu'), exportBtn = $('#exportBtn');
const setMenu = open => { menu.classList.toggle('show', open); };
exportBtn.addEventListener('click', e => { e.stopPropagation(); setMenu(!menu.classList.contains('show')); });
document.addEventListener('click', e => { if (!menu.contains(e.target)) setMenu(false); });

// Form Elements
const form = $('#config-form');
if (!form) return;

const tableWrap = $('#table-wrapper'), chartWrap = $('#chart-wrapper'), card = $('#capture-area'), kpi = $('#kpi-banner');
let chartInstance = null;

async function update(){
    const fd = new FormData(form);
    const mode = $('input[name="view_mode_toggle"]:checked').value;
    fd.append('view_mode', mode);
    
    // Toggle structural UI
    $$('[data-structural]').forEach(el => el.classList.toggle('is-disabled', mode === 'raw'));
    $('#raw_col_picker').style.display = mode === 'raw' ? 'block' : 'none';
    
    // Smart Totals Disable
    const metrics = fd.getAll('agg_funcs');
    const totWrap = $('#total_wrapper');
    if(metrics.includes('sum') && metrics.includes('count')) {
        $('#show_total_cb').checked = false; $('#show_total_cb').disabled = true;
        totWrap.style.opacity = '0.4';
    } else {
        $('#show_total_cb').disabled = false; totWrap.style.opacity = '1';
    }

    try {
        const res = await fetch('/calculate', { method: 'POST', body: fd });
        const d = await res.json();
        
        $('#dashTitle').innerText = d.dyn_title || "Executive Dashboard";
        $('#dashDate').innerText = d.dyn_date || "All Time";
        
        kpi.innerHTML = d.kpi_html || ''; kpi.hidden = !d.kpi_html;
        tableWrap.innerHTML = d.table_html;
        
        // Handle views
        if (mode === 'chart') {
            tableWrap.style.display = 'none';
            chartWrap.style.display = 'block';
            renderChart(d.chart_data);
        } else {
            tableWrap.style.display = 'block';
            chartWrap.style.display = 'none';
        }
        
    } catch (err) { console.error(err); }
}

function renderChart(data) {
    if(!data) { chartWrap.innerHTML = "<div style='text-align:center; padding:40px;'>Not enough data for chart.</div>"; return; }
    chartWrap.innerHTML = '<canvas id="dataChart"></canvas>';
    const ctx = document.getElementById('dataChart').getContext('2d');
    const isDark = document.body.classList.contains('dark-mode');
    
    chartInstance = new Chart(ctx, {
        type: 'bar',
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: isDark ? '#fff' : '#000' } } },
            scales: {
                x: { ticks: { color: isDark ? '#a1a1a6' : '#86868b' }, grid: { color: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)' } },
                y: { ticks: { color: isDark ? '#a1a1a6' : '#86868b' }, grid: { color: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)' } }
            }
        }
    });
}

// Events
form.addEventListener('change', update);
form.addEventListener('click', e => {
  const head = e.target.closest('.acc-head');
  if (head) { head.parentElement.classList.toggle('open'); return; }
  const sel = e.target.closest('[data-select]');
  if (sel) {
    const on = sel.dataset.on === '1', name = sel.dataset.select;
    $$(`input[name="${name}"]`).forEach(i => { i.checked = on; });
    update();
  }
});
form.addEventListener('input', e => {
  const q = e.target.dataset && e.target.dataset.search;
  if (!q) return;
  const needle = e.target.value.trim().toLowerCase();
  $$('.row', $(`[data-list="${q}"]`)).forEach(r => { r.style.display = r.dataset.val.toLowerCase().includes(needle) ? 'flex' : 'none'; });
});
$$('input[name="view_mode_toggle"]').forEach(r => r.addEventListener('change', update));
$('#resetBtn').addEventListener('click', () => { form.reset(); $('#view_dash').checked = true; update(); });

// Image Export via dom-to-image
let d2i = null;
const loadD2I = () => d2i || (d2i = new Promise((ok, fail) => {
  const s = document.createElement('script');
  s.src = 'https://cdnjs.cloudflare.com/ajax/libs/dom-to-image/2.6.0/dom-to-image.min.js';
  s.onload = ok; document.head.appendChild(s);
}));
$('#dlImage').addEventListener('click', async () => {
  setMenu(false);
  const area = $('#report-area');
  try {
    await loadD2I();
    area.style.overflow = 'visible';
    body.classList.add('export-mode');
    await new Promise(r => setTimeout(r, 400));
    const url = await domtoimage.toJpeg(area, { bgcolor: body.classList.contains('dark-mode') ? '#000000' : '#f2f2f7', quality: 1.0 });
    const a = document.createElement('a'); a.download = 'Executive_Report.jpeg'; a.href = url; a.click();
  } catch (err) { console.error(err); } 
  finally { area.style.overflow = 'hidden'; body.classList.remove('export-mode'); }
});

$('#dlExcel').addEventListener('click', () => { setMenu(false); const fd = new URLSearchParams(new FormData(form)); location.href = '/download?' + fd.toString(); });

update();
})();
"""

ASSET_VERSION = hashlib.md5((APP_CSS + APP_JS).encode()).hexdigest()[:8]

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1")
