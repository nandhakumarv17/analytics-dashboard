import os
import io
import json
import re
from datetime import datetime
from flask import Flask, request, render_template_string, send_file, jsonify, redirect, url_for
import pandas as pd
import numpy as np

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB

UPLOAD_DIR = "/tmp/dashboard_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATA_FILE_PATH = os.path.join(UPLOAD_DIR, "shared_data.pkl")

# --- iOS LIQUID GLASS & DARK MODE UI ---
GLOBAL_HEAD = """
<style>
    :root {
        --bg-main: #f2f2f7; --glass-bg: rgba(255, 255, 255, 0.78); --glass-sidebar: rgba(255, 255, 255, 0.85);
        --glass-border: rgba(0, 0, 0, 0.1); --text-primary: #1d1d1f; --text-secondary: #86868b;
        --shadow-glass: 0 10px 30px rgba(0,0,0,0.05); --blue-apple: #0071e3; --blue-hover: #0077ed;
        --header-bg: rgba(240, 240, 245, 0.95); --header-text: #1d1d1f;
        --total-bg: rgba(0, 113, 227, 0.08); --total-text: #0071e3;
    }
    body.dark-mode {
        --bg-main: #000000; --glass-bg: rgba(28, 28, 30, 0.75); --glass-sidebar: rgba(20, 20, 22, 0.85);
        --glass-border: rgba(255, 255, 255, 0.15); --text-primary: #f5f5f7; --text-secondary: #a1a1a6;
        --shadow-glass: 0 10px 30px rgba(0,0,0,0.5); --header-bg: rgba(44, 44, 46, 0.95); --header-text: #f5f5f7;
        --total-bg: rgba(10, 132, 255, 0.15); --total-text: #5ac8fa;
    }
    body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif; background: var(--bg-main); color: var(--text-primary); margin: 0; padding: 0; transition: background 0.3s, color 0.3s; }
    
    .nav { background: var(--glass-sidebar); backdrop-filter: saturate(180%) blur(20px); border-bottom: 1px solid var(--glass-border); padding: 0 24px; height: 60px; display: flex; justify-content: space-between; align-items: center; position: fixed; top: 0; width: 100%; z-index: 1000; box-sizing: border-box; }
    .nav-brand { font-weight: 700; font-size: 18px; letter-spacing: -0.5px; }
    .nav-controls { display: flex; gap: 12px; align-items: center; }
    
    .btn-liquid { background: rgba(120, 120, 128, 0.1); backdrop-filter: blur(10px); border: 1px solid var(--glass-border); color: var(--text-primary); border-radius: 980px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; transition: 0.2s; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    .btn-liquid:hover { background: rgba(120, 120, 128, 0.15); transform: scale(1.02); }
    .btn-primary { background: var(--blue-apple); color: #fff; border: none; box-shadow: 0 4px 10px rgba(0,113,227,0.3); }
    .btn-primary:hover { background: var(--blue-hover); }
    
    .app-layout { display: flex; height: 100vh; padding-top: 60px; box-sizing: border-box; }
    .sidebar { width: 340px; background: var(--glass-sidebar); backdrop-filter: blur(40px); border-right: 1px solid var(--glass-border); padding: 24px 20px; overflow-y: auto; flex-shrink: 0; }
    .main-content { flex: 1; padding: 24px; overflow: hidden; display: flex; flex-direction: column; }
    
    .section-title { font-size: 12px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; margin: 20px 0 10px; letter-spacing: 0.5px; }
    .checkbox-group { background: rgba(120,120,128,0.05); border: 1px solid var(--glass-border); border-radius: 12px; padding: 8px; max-height: 220px; overflow-y: auto; }
    .checkbox-item { display: flex; align-items: center; padding: 8px 10px; font-size: 13px; cursor: pointer; border-radius: 8px; font-weight: 500; }
    .checkbox-item:hover { background: rgba(120,120,128,0.1); }
    .checkbox-item input { margin-right: 10px; accent-color: var(--blue-apple); width: 16px; height: 16px; }
    .drag-handle { margin-right: 10px; cursor: grab; color: var(--text-secondary); opacity: 0.7; font-size: 16px; }
    
    .btn-segmented { display: flex; background: rgba(120,120,128,0.1); border-radius: 12px; padding: 4px; gap: 4px; }
    .btn-segmented label { flex: 1; text-align: center; font-size: 13px; font-weight: 600; padding: 6px 16px; border-radius: 8px; cursor: pointer; color: var(--text-secondary); transition: 0.2s; }
    .btn-segmented input { display: none; }
    .btn-segmented input:checked + label { background: var(--bg-main); color: var(--text-primary); box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    
    .table-container { background: var(--glass-bg); backdrop-filter: blur(20px); border-radius: 16px; border: 1px solid var(--glass-border); flex: 1; overflow: auto; box-shadow: var(--shadow-glass); }
    
    /* Equal Width Columns & Table UI */
    .excel-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 13px; }
    .excel-table th, .excel-table td { padding: 14px 16px; text-align: left; border-bottom: 1px solid var(--glass-border); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .excel-table th { background: var(--header-bg); color: var(--header-text); font-size: 11px; text-transform: uppercase; position: sticky; top: 0; z-index: 10; font-weight: 700; letter-spacing: 0.05em; }
    
    /* Freeze First Column */
    .excel-table th:first-child, .excel-table td:first-child { position: sticky; left: 0; z-index: 20; background: var(--bg-main); font-weight: 600; box-shadow: 1px 0 0 var(--glass-border); }
    .excel-table th:first-child { z-index: 30; background: var(--header-bg); }
    
    /* Row Hover */
    .excel-table tbody tr:hover td { background: rgba(120,120,128,0.05); }
    .excel-table tbody tr:hover td:first-child { background: var(--glass-sidebar); }
    
    /* Total Highlighting */
    .total-col { font-weight: 700 !important; background: var(--total-bg) !important; color: var(--total-text) !important; box-shadow: inset 1px 0 0 rgba(0,113,227,0.2); }
    .excel-table tbody tr:last-child td { font-weight: 700; background: var(--total-bg); border-top: 2px solid var(--blue-apple); color: var(--total-text); position: sticky; bottom: 0; z-index: 15; }
    .excel-table tbody tr:last-child td:first-child { z-index: 25; }
    
    .preset-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Sortable/1.15.0/Sortable.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/dom-to-image/2.6.0/dom-to-image.min.js"></script>
"""

UPLOAD_HTML = """
<!DOCTYPE html>
<html>
<head><title>Upload - Analytics Pro</title><meta name="viewport" content="width=device-width, initial-scale=1.0">""" + GLOBAL_HEAD + """</head>
<body>
    <div class="nav"><div class="nav-brand">Analytics Pro</div></div>
    <div style="max-width: 480px; margin: 120px auto; padding: 20px; text-align: center;">
        <h1 style="font-size: 32px; margin-bottom: 8px;">Analytics Engine.</h1>
        <p style="color: var(--text-secondary); margin-bottom: 32px;">Upload data to launch the Business Intelligence workspace.</p>
        <form action="/dashboard" method="post" enctype="multipart/form-data" style="background: var(--glass-bg); padding: 32px; border-radius: 24px; border: 1px solid var(--glass-border); box-shadow: var(--shadow-glass);">
            <input type="file" name="file" accept=".xlsx, .xls, .csv" required style="width: 100%; margin-bottom: 24px; padding: 16px; border: 2px dashed var(--glass-border); border-radius: 12px; cursor: pointer;">
            <button type="submit" class="btn-liquid btn-primary" style="width: 100%; padding: 14px; font-size: 15px;">Launch Workspace →</button>
        </form>
    </div>
</body>
</html>
"""

WORKSPACE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Executive Dashboard</title><meta name="viewport" content="width=device-width, initial-scale=1.0">""" + GLOBAL_HEAD + """</head>
<body>
    <div class="nav">
        <div class="nav-brand">Analytics Pro</div>
        <div class="nav-controls">
            <div class="btn-segmented">
                <input type="radio" id="view_pivot" name="view_mode" value="pivot" checked onchange="toggleView()">
                <label for="view_pivot">Pivot</label>
                <input type="radio" id="view_raw" name="view_mode" value="raw" onchange="toggleView()">
                <label for="view_raw">Raw Data</label>
            </div>
            <button class="btn-liquid" onclick="toggleDarkMode()" id="dm-btn">🌙 Dark</button>
            <button class="btn-liquid btn-primary" onclick="exportImage()">📸 Export</button>
        </div>
    </div>
    
    <div class="app-layout">
        <div class="sidebar">
            <form id="config-form">
                <div class="preset-grid">
                    <button type="button" class="btn-liquid" onclick="applyPreset('daily_ba')">Daily Sales by BA</button>
                    <button type="button" class="btn-liquid" onclick="applyPreset('fam_seg')">Family vs Segment</button>
                </div>

                <div id="pivot-controls">
                    <div class="section-title">Hierarchy (Drag to Reorder)</div>
                    <label style="font-size: 10px; color: var(--text-secondary); margin-bottom: 4px; display:block;">ROWS (Y-AXIS)</label>
                    <div class="checkbox-group sortable-list" id="rows-container">
                        {% for col in grouping_cols %}
                        <label class="checkbox-item"><span class="drag-handle">≡</span><input type="checkbox" name="index_cols" value="{{ col }}"> <span>{{ col }}</span></label>
                        {% endfor %}
                    </div>
                    
                    <label style="font-size: 10px; color: var(--text-secondary); margin: 16px 0 4px; display:block;">COLUMNS (X-AXIS)</label>
                    <div class="checkbox-group sortable-list" id="cols-container">
                        {% for col in grouping_cols %}
                        <label class="checkbox-item"><span class="drag-handle">≡</span><input type="checkbox" name="columns_cols" value="{{ col }}"> <span>{{ col }}</span></label>
                        {% endfor %}
                    </div>

                    <div class="section-title">Metrics</div>
                    <div class="checkbox-group">
                        <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="sum" checked> <span>Sum Total (₹)</span></label>
                        <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="count"> <span>Count (Qty)</span></label>
                        <div style="height: 1px; background: var(--glass-border); margin: 8px 0;"></div>
                        <label class="checkbox-item" id="total_wrapper"><input type="checkbox" id="show_total_cb" name="show_row_total" value="true" checked> <span>Show Grand Totals</span></label>
                    </div>
                </div>

                <div id="raw-controls" style="display:none;">
                    <div class="section-title">Select Raw Columns</div>
                    <div class="checkbox-group" style="max-height: 500px;">
                        {% for col in all_cols %}
                        <label class="checkbox-item"><input type="checkbox" name="raw_cols" value="{{ col }}" checked> <span>{{ col }}</span></label>
                        {% endfor %}
                    </div>
                </div>
            </form>
        </div>
        
        <div class="main-content">
            <div class="table-container" id="capture-area">
                <div id="table-wrapper"><div style="padding: 60px; text-align: center; color: var(--text-secondary); font-size: 15px;">Select rows and metrics from the sidebar to build your view.</div></div>
            </div>
        </div>
    </div>

    <script>
        function toggleDarkMode() { 
            const isDark = document.body.classList.toggle('dark-mode'); 
            document.getElementById('dm-btn').innerText = isDark ? '☀️ Light' : '🌙 Dark';
        }
        
        function toggleView() {
            const mode = document.querySelector('input[name="view_mode"]:checked').value;
            document.getElementById('pivot-controls').style.display = mode === 'pivot' ? 'block' : 'none';
            document.getElementById('raw-controls').style.display = mode === 'raw' ? 'block' : 'none';
            updateDashboard();
        }

        function applyPreset(type) {
            document.getElementById('config-form').reset();
            document.getElementById('view_pivot').checked = true;
            toggleView();
            
            if(type === 'daily_ba') {
                checkValue('index_cols', 'BA Name');
                checkValue('columns_cols', 'Customized Sales Date');
            } else if(type === 'fam_seg') {
                checkValue('index_cols', 'Family Name');
                checkValue('columns_cols', 'SEG1');
            }
            updateDashboard();
        }

        function checkValue(name, val) {
            document.querySelectorAll(`input[name="${name}"]`).forEach(cb => {
                if(cb.value === val || cb.value === val.replace('BA Name', 'SPC Name')) cb.checked = true;
            });
        }

        // Initialize drag and drop for hierarchy
        document.querySelectorAll('.sortable-list').forEach(el => {
            new Sortable(el, { handle: '.drag-handle', animation: 150, onEnd: updateDashboard });
        });

        async function updateDashboard() {
            const form = document.getElementById('config-form');
            const formData = new FormData(form);
            formData.append('view_mode', document.querySelector('input[name="view_mode"]:checked').value);

            // Smart Totals Logic: Disable if mixing sum (₹) and count (qty)
            const metrics = formData.getAll('agg_funcs');
            const totalCb = document.getElementById('show_total_cb');
            const totalWrap = document.getElementById('total_wrapper');
            
            if(metrics.includes('sum') && metrics.includes('count')) {
                totalCb.checked = false; 
                totalCb.disabled = true;
                totalWrap.style.opacity = '0.4';
                totalWrap.title = "Cannot total mixed metrics (₹ and Qty)";
            } else {
                totalCb.disabled = false;
                totalWrap.style.opacity = '1';
                totalWrap.title = "";
            }

            try {
                const res = await fetch('/calculate', { method: 'POST', body: formData });
                const data = await res.json();
                document.getElementById('table-wrapper').innerHTML = data.table_html || `<div style="padding:40px; color:#ff3b30; text-align:center;">${data.error}</div>`;
            } catch(e) { console.error(e); }
        }

        document.getElementById('config-form').addEventListener('change', updateDashboard);
        window.onload = updateDashboard;

        function exportImage() {
            const area = document.getElementById('capture-area');
            const bgColor = document.body.classList.contains('dark-mode') ? '#1c1c1e' : '#ffffff';
            
            // Temporarily expand scroll area for full capture
            const origOverflow = area.style.overflow;
            area.style.overflow = 'visible';
            
            domtoimage.toJpeg(area, { quality: 1.0, bgcolor: bgColor })
                .then(url => {
                    const a = document.createElement('a'); a.download = 'Dashboard_Export.jpeg'; a.href = url; a.click();
                    area.style.overflow = origOverflow;
                })
                .catch(err => {
                    console.error("Export failed", err);
                    area.style.overflow = origOverflow;
                });
        }
    </script>
</body>
</html>
"""

def get_data():
    if os.path.exists(DATA_FILE_PATH):
        df = pd.read_pickle(DATA_FILE_PATH)
        # Globally rename SPC to BA
        df.rename(columns=lambda x: str(x).replace('SPC Name', 'BA Name').replace('SPC', 'BA'), inplace=True)
        return df
    return None

def format_indian_number(x):
    if pd.isna(x) or x == '': return ''
    try:
        n = int(round(float(x)))
        s = str(abs(n))
        if len(s) > 3:
            res = s[-3:]
            s = s[:-3]
            while len(s) > 2:
                res = s[-2:] + ',' + res
                s = s[:-2]
            s = s + ',' + res
        return f"-{s}" if n < 0 else s
    except: return str(x)

@app.route("/")
def home():
    df = get_data()
    if df is not None:
        cols = df.columns.tolist()
        grouping = df.select_dtypes(exclude=['number']).columns.tolist()
        date_col = next((c for c in ['Customized Sales Date', 'Sale Date'] if c in cols), "")
        return render_template_string(WORKSPACE_HTML, all_cols=cols, grouping_cols=grouping, default_date_col=date_col)
    return render_template_string(UPLOAD_HTML)

@app.route("/dashboard", methods=["POST"])
def dashboard():
    if 'file' in request.files and request.files['file'].filename != '':
        f = request.files['file']
        df = pd.read_csv(f) if f.filename.endswith('.csv') else pd.read_excel(f)
        df.to_pickle(DATA_FILE_PATH)
    return redirect(url_for('home'))

@app.route("/calculate", methods=["POST"])
def calculate():
    df = get_data()
    if df is None: return jsonify({"error": "No data available."}), 400
    
    mode = request.form.get('view_mode', 'pivot')
    
    # Global Date Formatting (dd-MMM-yy)
    date_cols = df.select_dtypes(include=['datetime64', 'object']).columns
    for c in date_cols:
        try: 
            if pd.api.types.is_datetime64_any_dtype(df[c]) or "Date" in c:
                df[c] = pd.to_datetime(df[c]).dt.strftime('%d-%b-%y')
        except: pass

    # --- RAW DATA VIEW ---
    if mode == 'raw':
        raw_cols = request.form.getlist('raw_cols')
        if not raw_cols: return jsonify({"error": "Select at least one column."})
        sub = df[raw_cols].fillna('')
        
        # Format numbers in raw view
        for c in sub.select_dtypes(include='number').columns:
            sub[c] = sub[c].apply(format_indian_number)
            
        return jsonify({"table_html": sub.to_html(classes='excel-table', border=0, index=False)})

    # --- PIVOT VIEW ---
    idx = request.form.getlist('index_cols')
    cols = request.form.getlist('columns_cols')
    aggs = request.form.getlist('agg_funcs')
    show_total = request.form.get('show_row_total') == 'true'

    if not idx or not aggs: return jsonify({"error": "Select rows and metrics from the sidebar."})
    
    num_cols = df.select_dtypes(include='number').columns.tolist()
    val_col = 'Tentative DP' if 'Tentative DP' in num_cols else (num_cols[0] if num_cols else None)
    if not val_col: return jsonify({"error": "No numeric data found to aggregate."})

    kwargs = {'data': df, 'index': idx, 'values': [val_col], 'aggfunc': aggs}
    if cols: kwargs['columns'] = cols
    
    pivot = pd.pivot_table(**kwargs).reset_index().fillna(0)
    
    # Clean, Prefix-Free Headers
    new_headers = []
    for c in pivot.columns:
        if isinstance(c, tuple):
            if c[0] in idx and all(x == '' for x in c[1:]): 
                new_headers.append(str(c[0]))
            else:
                # Strip out 'Tentative DP', 'sum', 'count' to leave only the raw category name
                parts = [str(x) for x in c if str(x) and str(x) not in [val_col, 'sum', 'count', 'mean']]
                new_headers.append(" - ".join(parts) if parts else str(c[-1]))
        else: 
            new_headers.append(str(c))
    
    pivot.columns = new_headers
    metric_cols = [c for c in pivot.columns if c not in idx]

    # Smart Totals
    if show_total and len(metric_cols) > 1 and not ('sum' in aggs and 'count' in aggs):
        pivot['TOTAL'] = pivot[metric_cols].sum(axis=1)
        metric_cols.append('TOTAL')

    # Grand Total Footer
    if not pivot.empty:
        totals = {c: pivot[c].sum() if c in metric_cols else ('' if c != idx[0] else 'GRAND TOTAL') for c in pivot.columns}
        pivot = pd.concat([pivot, pd.DataFrame([totals])], ignore_index=True)

    # Format numbers
    for c in metric_cols: pivot[c] = pivot[c].apply(format_indian_number)

    # Render HTML and apply total-col CSS class
    html = pivot.to_html(classes='excel-table', border=0, index=False)
    html = html.replace('<th>TOTAL</th>', '<th class="total-col">TOTAL</th>')
    
    # Inject total-col class to the last column cells if TOTAL exists
    if 'TOTAL' in metric_cols:
        html = re.sub(r'(<td>)([\d,-]+)(</td></tr>)', r'<td class="total-col">\2\3', html)
    
    return jsonify({"table_html": html})

if __name__ == '__main__':
    app.run(debug=True)
