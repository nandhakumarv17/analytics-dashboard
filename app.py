import os
import io
import json
import re
import traceback
from datetime import datetime
from flask import Flask, request, render_template_string, send_file, jsonify, redirect, url_for
import pandas as pd
import numpy as np

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

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
        --green: #34c759;
    }
    body.dark-mode {
        --bg-main: #000000; --glass-bg: rgba(28, 28, 30, 0.75); --glass-sidebar: rgba(20, 20, 22, 0.85);
        --glass-border: rgba(255, 255, 255, 0.15); --text-primary: #f5f5f7; --text-secondary: #a1a1a6;
        --shadow-glass: 0 10px 30px rgba(0,0,0,0.5); --header-bg: rgba(44, 44, 46, 0.95); --header-text: #f5f5f7;
        --total-bg: rgba(10, 132, 255, 0.15); --total-text: #5ac8fa;
        --green: #30d158;
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
    .checkbox-item input[type="checkbox"]:not(.ios-switch) { margin-right: 10px; accent-color: var(--blue-apple); width: 16px; height: 16px; }
    .drag-handle { margin-right: 10px; cursor: grab; color: var(--text-secondary); opacity: 0.7; font-size: 16px; }
    
    .btn-segmented { display: flex; background: rgba(120,120,128,0.1); border-radius: 12px; padding: 4px; gap: 4px; }
    .btn-segmented label { flex: 1; text-align: center; font-size: 13px; font-weight: 600; padding: 6px 16px; border-radius: 8px; cursor: pointer; color: var(--text-secondary); transition: 0.2s; z-index: 2; }
    .btn-segmented input { display: none; }
    .btn-segmented input:checked + label { color: var(--text-primary); }
    
    .table-container { background: var(--glass-bg); backdrop-filter: blur(20px); border-radius: 16px; border: 1px solid var(--glass-border); flex: 1; overflow: auto; box-shadow: var(--shadow-glass); }
    
    .excel-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 13px; }
    .excel-table th, .excel-table td { padding: 14px 16px; text-align: left; border-bottom: 1px solid var(--glass-border); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .excel-table th { background: var(--header-bg); color: var(--header-text); font-size: 11px; text-transform: uppercase; position: sticky; top: 0; z-index: 10; font-weight: 700; letter-spacing: 0.05em; }
    .excel-table th:first-child, .excel-table td:first-child { position: sticky; left: 0; z-index: 20; background: var(--bg-main); font-weight: 600; box-shadow: 1px 0 0 var(--glass-border); }
    .excel-table th:first-child { z-index: 30; background: var(--header-bg); }
    .excel-table tbody tr:hover td { background: rgba(120,120,128,0.05); }
    .excel-table tbody tr:hover td:first-child { background: var(--glass-sidebar); }
    
    .total-col { font-weight: 700 !important; background: var(--total-bg) !important; color: var(--total-text) !important; box-shadow: inset 1px 0 0 rgba(0,113,227,0.2); }
    .excel-table tbody tr:last-child td { font-weight: 700; background: var(--total-bg); border-top: 2px solid var(--blue-apple); color: var(--total-text); position: sticky; bottom: 0; z-index: 15; }
    .excel-table tbody tr:last-child td:first-child { z-index: 25; }
    
    .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 16px; }
    .kpi { padding: 16px; border-radius: 16px; background: var(--glass-bg); border: 1px solid var(--glass-border); box-shadow: var(--shadow-glass); }
    .kpi-label { font-size: 11px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; margin-bottom: 6px; }
    .kpi-val { font-size: 24px; font-weight: 700; color: var(--text-primary); }

    /* iOS Toggle Switch */
    .switch-container { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; cursor: pointer; }
    .switch { position: relative; width: 44px; height: 24px; background: rgba(120,120,128,0.3); border-radius: 12px; transition: 0.3s; flex-shrink: 0; }
    .switch::after { content: ''; position: absolute; top: 2px; left: 2px; width: 20px; height: 20px; background: #fff; border-radius: 50%; box-shadow: 0 2px 4px rgba(0,0,0,0.2); transition: 0.3s; }
    input:checked + .switch { background: var(--green); }
    input:checked + .switch::after { transform: translateX(20px); }
    input.ios-switch { display: none; }
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Sortable/1.15.0/Sortable.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/dom-to-image/2.6.0/dom-to-image.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
        
        {% if error %}
        <div style="background: rgba(255, 59, 48, 0.1); color: #ff3b30; padding: 12px; border-radius: 12px; margin-bottom: 16px; font-weight: 600; font-size: 13px;">
            {{ error }}
        </div>
        {% endif %}
        
        <form action="/dashboard" method="post" enctype="multipart/form-data" style="background: var(--glass-bg); padding: 32px; border-radius: 24px; border: 1px solid var(--glass-border); box-shadow: var(--shadow-glass);">
            <input type="file" name="file" accept=".xlsx, .xls, .csv" required style="width: 100%; margin-bottom: 24px; padding: 16px; border: 2px dashed var(--glass-border); border-radius: 12px; cursor: pointer; color: var(--text-primary);">
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
            <button class="btn-liquid" onclick="toggleDarkMode()" id="dm-btn">🌙 Dark</button>
            <button class="btn-liquid btn-primary" onclick="exportImage()">📸 Export</button>
            <button class="btn-liquid" id="dlExcel">📊 Download Excel</button>
        </div>
    </div>
    
    <div class="app-layout">
        <div class="sidebar">
            <form id="config-form">
                <div class="section-title" style="margin-top: 0;">Filters</div>
                <div class="checkbox-group" style="margin-bottom: 16px; opacity: 0.8;">
                    <label class="switch-container" style="cursor: not-allowed;" title="Permanently locked">
                        <span style="font-size: 13px; font-weight: 500;">Final Status: Ok</span>
                        <input type="checkbox" class="ios-switch" checked disabled>
                        <div class="switch"></div>
                    </label>
                </div>
                
                <div class="section-title">Timeline & Periods</div>
                <div style="display:flex; gap:8px;">
                    <div style="flex:1;">
                        <label style="font-size:10px; color:var(--text-secondary);">FROM</label>
                        <input type="date" name="start_date" id="start_date" class="btn-liquid" style="width:100%; box-sizing:border-box;">
                    </div>
                    <div style="flex:1;">
                        <label style="font-size:10px; color:var(--text-secondary);">TO</label>
                        <input type="date" name="end_date" id="end_date" class="btn-liquid" style="width:100%; box-sizing:border-box;">
                    </div>
                </div>
                
                <div style="margin-top: 12px; display:flex; flex-wrap:wrap; gap:6px;">
                    <label class="btn-liquid" style="padding:4px 8px; font-size:11px; border-radius:6px; font-weight:500; cursor:pointer;"><input type="checkbox" name="week_num" value="1" style="display:none;" onchange="updateDashboard()">W1</label>
                    <label class="btn-liquid" style="padding:4px 8px; font-size:11px; border-radius:6px; font-weight:500; cursor:pointer;"><input type="checkbox" name="week_num" value="2" style="display:none;" onchange="updateDashboard()">W2</label>
                    <label class="btn-liquid" style="padding:4px 8px; font-size:11px; border-radius:6px; font-weight:500; cursor:pointer;"><input type="checkbox" name="week_num" value="3" style="display:none;" onchange="updateDashboard()">W3</label>
                    <label class="btn-liquid" style="padding:4px 8px; font-size:11px; border-radius:6px; font-weight:500; cursor:pointer;"><input type="checkbox" name="week_num" value="4" style="display:none;" onchange="updateDashboard()">W4</label>
                    <label class="btn-liquid" style="padding:4px 8px; font-size:11px; border-radius:6px; font-weight:500; cursor:pointer;"><input type="checkbox" name="week_num" value="5" style="display:none;" onchange="updateDashboard()">W5</label>
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

                    <div class="section-title">Metrics & Configuration</div>
                    <div class="checkbox-group">
                        <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="sum" checked> <span>Sum Total (₹)</span></label>
                        <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="count"> <span>Count (Qty)</span></label>
                        <div style="height: 1px; background: var(--glass-border); margin: 4px 0;"></div>
                        
                        <label class="switch-container" id="total_wrapper">
                            <span style="font-size: 13px; font-weight: 500;">Show Grand Totals</span>
                            <input type="checkbox" id="show_total_cb" class="ios-switch" name="show_row_total" value="true" checked>
                            <div class="switch"></div>
                        </label>
                    </div>
                </div>
                
                <div style="text-align: center; margin-top: 24px;">
                    <a href="/upload" style="color: #ff3b30; font-size: 12px; text-decoration: none; font-weight: 600; padding: 8px 16px; border-radius: 980px; background: rgba(255, 59, 48, 0.1);">← Upload New File</a>
                </div>
            </form>
        </div>
        
        <div class="main-content">
            <div style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-end;">
                <div>
                    <h1 style="margin:0; font-size: 28px; font-weight: 700; letter-spacing: -0.02em;" id="dashTitle">Executive Dashboard</h1>
                    <div style="font-size: 13px; color: var(--text-secondary); font-weight: 600; margin-top: 4px;" id="dashDate">All Time</div>
                </div>
                <div class="btn-segmented" style="position: relative;">
                    <div class="seg-thumb" style="position: absolute; top: 4px; bottom: 4px; left: 4px; width: calc(50% - 4px); background: var(--bg-main); border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); transition: 0.3s; z-index: 1;"></div>
                    <input type="radio" id="view_dash" name="view_mode_toggle" value="dashboard" checked onchange="updateDashboard()">
                    <label for="view_dash">Pivot</label>
                    <input type="radio" id="view_chart" name="view_mode_toggle" value="chart" onchange="updateDashboard()">
                    <label for="view_chart">Chart</label>
                </div>
            </div>
            
            <div id="kpi-banner" class="kpis" hidden></div>
            
            <div class="table-container" id="capture-area">
                <div id="table-wrapper"><div style="padding: 60px; text-align: center; color: var(--text-secondary); font-size: 15px;">Select rows and metrics from the sidebar to build your view.</div></div>
                <div id="chart-wrapper" style="display:none; padding: 20px; height: calc(100% - 40px); box-sizing: border-box;"><canvas id="dataChart"></canvas></div>
            </div>
        </div>
    </div>

    <script>
        // Update segmented toggle background slider
        document.querySelectorAll('input[name="view_mode_toggle"]').forEach(radio => {
            radio.addEventListener('change', function() {
                const thumb = document.querySelector('.seg-thumb');
                thumb.style.transform = this.value === 'chart' ? 'translateX(100%)' : 'translateX(0)';
            });
        });

        function toggleDarkMode() { 
            const isDark = document.body.classList.toggle('dark-mode'); 
            document.getElementById('dm-btn').innerText = isDark ? '☀️ Light' : '🌙 Dark';
            if(document.querySelector('input[name="view_mode_toggle"]:checked').value === 'chart') {
                updateDashboard();
            }
        }

        // Initialize drag and drop for hierarchy
        document.querySelectorAll('.sortable-list').forEach(el => {
            new Sortable(el, { handle: '.drag-handle', animation: 150, onEnd: updateDashboard });
        });
        
        // Highlight active week buttons
        document.querySelectorAll('input[name="week_num"]').forEach(cb => {
            cb.addEventListener('change', function() {
                if(this.checked) { this.parentElement.style.background = 'var(--blue-apple)'; this.parentElement.style.color = '#fff'; }
                else { this.parentElement.style.background = ''; this.parentElement.style.color = ''; }
            });
        });

        function checkValue(name, val) {
            document.querySelectorAll(`input[name="${name}"]`).forEach(cb => {
                if(cb.value === val || cb.value === val.replace('BA Name', 'SPC Name')) cb.checked = true;
            });
        }

        let chartInstance = null;

        async function updateDashboard() {
            const form = document.getElementById('config-form');
            const formData = new FormData(form);
            const mode = document.querySelector('input[name="view_mode_toggle"]:checked').value;
            formData.append('view_mode', mode);

            // Smart Totals Logic
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
                
                // Advanced Error Catching
                let data;
                try {
                    data = await res.json();
                } catch (e) {
                    const text = await res.text();
                    document.getElementById('table-wrapper').innerHTML = `<div style="padding:40px; color:#ff3b30; text-align:center; font-weight:600;">Server crashed. (500 Error)<br><span style="font-size:12px; font-weight:normal;">${text.substring(0,250)}</span></div>`;
                    return;
                }
                
                if (data.error) {
                    document.getElementById('chart-wrapper').style.display = 'none';
                    document.getElementById('table-wrapper').style.display = 'block';
                    document.getElementById('table-wrapper').innerHTML = `<div style="padding:40px; color:#ff3b30; text-align:center; font-weight:600;">${data.error}</div>`;
                    return;
                }
                
                document.getElementById('dashTitle').innerText = data.dyn_title || "Executive Dashboard";
                document.getElementById('dashDate').innerText = data.dyn_date || "All Time";
                
                const kpiBanner = document.getElementById('kpi-banner');
                kpiBanner.innerHTML = data.kpi_html || '';
                kpiBanner.hidden = !data.kpi_html;
                
                const tw = document.getElementById('table-wrapper');
                const cw = document.getElementById('chart-wrapper');
                
                if (mode === 'chart') {
                    tw.style.display = 'none';
                    cw.style.display = 'block';
                    renderChart(data.chart_data);
                } else {
                    cw.style.display = 'none';
                    tw.style.display = 'block';
                    tw.innerHTML = data.table_html;
                }
            } catch(e) { 
                console.error(e);
                document.getElementById('table-wrapper').innerHTML = `<div style="padding:40px; color:#ff3b30; text-align:center; font-weight:600;">Network Request Failed: ${e.message}</div>`;
            }
        }

        function renderChart(data) {
            const cw = document.getElementById('chart-wrapper');
            if(!data) { cw.innerHTML = "<div style='text-align:center; padding:40px; color:var(--text-secondary);'>Select rows and metrics to generate chart.</div>"; return; }
            
            cw.innerHTML = '<canvas id="dataChart"></canvas>';
            const ctx = document.getElementById('dataChart').getContext('2d');
            const isDark = document.body.classList.contains('dark-mode');
            const textColor = isDark ? '#a1a1a6' : '#86868b';
            const gridColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)';
            
            chartInstance = new Chart(ctx, {
                type: 'bar',
                data: data,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { labels: { color: isDark ? '#f5f5f7' : '#1d1d1f', font: { family: '-apple-system' } } } },
                    scales: {
                        x: { ticks: { color: textColor, font: { family: '-apple-system' } }, grid: { color: gridColor } },
                        y: { ticks: { color: textColor, font: { family: '-apple-system' } }, grid: { color: gridColor } }
                    }
                }
            });
        }

        document.getElementById('config-form').addEventListener('change', updateDashboard);
        window.onload = updateDashboard;

        function exportImage() {
            const area = document.getElementById('capture-area');
            const bgColor = document.body.classList.contains('dark-mode') ? '#1c1c1e' : '#ffffff';
            
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
        
        document.getElementById('dlExcel').addEventListener('click', () => { 
            const fd = new URLSearchParams(new FormData(document.getElementById('config-form'))); 
            location.href = '/download?' + fd.toString(); 
        });
    </script>
</body>
</html>
"""

def get_data():
    if os.path.exists(DATA_FILE_PATH):
        try:
            df = pd.read_pickle(DATA_FILE_PATH)
            df.rename(columns=lambda x: str(x).replace('SPC Name', 'BA Name').replace('SPC', 'BA'), inplace=True)
            return df
        except Exception:
            return None
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
        return render_template_string(WORKSPACE_HTML, all_cols=cols, grouping_cols=grouping)
    return render_template_string(UPLOAD_HTML, error=None)

@app.route("/upload", methods=["GET"])
def upload_page():
    return render_template_string(UPLOAD_HTML, error=None)

@app.route("/dashboard", methods=["POST"])
def dashboard():
    f = request.files.get('file')
    if not f or not f.filename:
        return redirect(url_for('home'))
    
    try:
        name = f.filename.lower()
        if name.endswith('.csv'):
            df = pd.read_csv(f)
        elif name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(f)
        else:
            return render_template_string(UPLOAD_HTML, error="Unsupported file type. Please use .csv, .xls, or .xlsx"), 400
        
        if df.empty:
            return render_template_string(UPLOAD_HTML, error="The uploaded file contains no data."), 400
            
        df.to_pickle(DATA_FILE_PATH)
        return redirect(url_for('home'))
    except Exception as e:
        return render_template_string(UPLOAD_HTML, error=f"Error reading file: {str(e)}"), 400

@app.route("/calculate", methods=["POST"])
def calculate():
    try:
        df = get_data()
        if df is None: return jsonify({"error": "No data available. Please re-upload your file."}), 400
        
        mode = request.form.get('view_mode', 'dashboard')
        
        # 1. PERMANENT STATUS FILTER: Final Status == Ok
        status_cols = [c for c in df.columns if c.lower() in ['finalstatus', 'final record status', 'validation remarks', 'status']]
        filter_texts = []
        if status_cols:
            status_col = status_cols[0]
            df = df[df[status_col].astype(str).str.lower().str.strip() == 'ok']
            filter_texts.append("Status: Ok")

        # Global Date Setup
        date_cols = df.select_dtypes(include=['datetime64', 'object']).columns
        date_col_name = None
        for c in date_cols:
            try: 
                if pd.api.types.is_datetime64_any_dtype(df[c]) or "Date" in c:
                    df[c] = pd.to_datetime(df[c], errors='coerce')
                    date_col_name = c
            except: pass

        # Filter by Date & Weeks
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        weeks = request.form.getlist("week_num")
        
        if date_col_name:
            if start_date: 
                df = df[df[date_col_name] >= pd.to_datetime(start_date)]
                filter_texts.append(f"From {pd.to_datetime(start_date).strftime('%d-%b-%y')}")
            if end_date: 
                df = df[df[date_col_name] <= pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
                filter_texts.append(f"To {pd.to_datetime(end_date).strftime('%d-%b-%y')}")
                
            if weeks:
                week_masks = []
                for w in weeks:
                    w = int(w)
                    if w == 1: week_masks.append(df[date_col_name].dt.day <= 7)
                    elif w == 2: week_masks.append((df[date_col_name].dt.day > 7) & (df[date_col_name].dt.day <= 14))
                    elif w == 3: week_masks.append((df[date_col_name].dt.day > 14) & (df[date_col_name].dt.day <= 21))
                    elif w == 4: week_masks.append((df[date_col_name].dt.day > 21) & (df[date_col_name].dt.day <= 28))
                    elif w == 5: week_masks.append(df[date_col_name].dt.day > 28)
                if week_masks:
                    combined = week_masks[0]
                    for wm in week_masks[1:]: combined = combined | wm
                    df = df[combined]
                filter_texts.append(f"Weeks: {', '.join([f'W{w}' for w in weeks])}")

        idx = request.form.getlist('index_cols')
        dynamic_title = f"Sales Analysis by {' & '.join(idx)}" if idx else "Executive Dashboard"
        date_subtitle = " · ".join(filter_texts) if filter_texts else "All Time"
        
        # Ensure Numeric Safety
        if 'Tentative DP' in df.columns:
            df['Tentative DP'] = pd.to_numeric(df['Tentative DP'].astype(str).str.replace(',', ''), errors='coerce')
            val_col = 'Tentative DP'
        else:
            num_cols = df.select_dtypes(include='number').columns.tolist()
            val_col = num_cols[0] if num_cols else None

        kpi_html = ""
        if not df.empty and val_col:
            active = format_indian_number(df[idx[0]].nunique()) if idx and idx[0] in df.columns else "N/A"
            kpi_html = f"""
                <div class="kpi"><div class="kpi-label">Total Volume</div><div class="kpi-val">{format_indian_number(df[val_col].sum())}</div></div>
                <div class="kpi"><div class="kpi-label">Records</div><div class="kpi-val">{format_indian_number(len(df))}</div></div>
                <div class="kpi"><div class="kpi-label">Active Entities</div><div class="kpi-val">{active}</div></div>
            """

        if df.empty:
            return jsonify({"table_html": '<div style="padding:40px; text-align:center;">No data found for selected dates/weeks.</div>', "dyn_title": dynamic_title, "dyn_date": date_subtitle, "kpi_html": kpi_html})

        cols = request.form.getlist('columns_cols')
        aggs = request.form.getlist('agg_funcs')
        show_total = request.form.get('show_row_total') == 'true'

        if not idx or not aggs: return jsonify({"error": "Select rows and metrics from the sidebar."})
        if not val_col: return jsonify({"error": "No numeric data found to aggregate."})

        kwargs = {'data': df, 'index': idx, 'values': [val_col], 'aggfunc': aggs}
        if cols: kwargs['columns'] = cols
        
        pivot = pd.pivot_table(**kwargs).reset_index().fillna(0)
        
        new_headers = []
        for c in pivot.columns:
            if isinstance(c, tuple):
                if c[0] in idx and all(x == '' for x in c[1:]): 
                    new_headers.append(str(c[0]))
                else:
                    parts = []
                    for x in c:
                        if str(x) and str(x) not in [val_col, 'sum', 'count', 'mean']:
                            if isinstance(x, pd.Timestamp):
                                parts.append(x.strftime('%d-%b-%y'))
                            else:
                                parts.append(str(x))
                    new_headers.append(" - ".join(parts) if parts else str(c[-1]))
            else: 
                new_headers.append(c.strftime('%d-%b-%y') if isinstance(c, pd.Timestamp) else str(c))
        
        pivot.columns = new_headers
        metric_cols = [c for c in pivot.columns if c not in idx]

        if show_total and len(metric_cols) > 1 and not ('sum' in aggs and 'count' in aggs):
            pivot['TOTAL'] = pivot[metric_cols].sum(axis=1)
            metric_cols.append('TOTAL')
            
        chart_data = None
        if mode == 'chart':
            chart_df = pivot.sort_values(by=metric_cols[0], ascending=False).head(15) if metric_cols else pivot.head(15)
            labels = chart_df[idx[0]].astype(str).tolist() if idx else ["Total"]
            datasets = [{"label": m, "data": chart_df[m].tolist(), "backgroundColor": "#0071e3", "borderRadius": 4} for m in metric_cols if m != "TOTAL"]
            chart_data = {"labels": labels, "datasets": datasets}

        if not pivot.empty:
            totals = {c: pivot[c].sum() if c in metric_cols else ('' if c != idx[0] else 'GRAND TOTAL') for c in pivot.columns}
            pivot = pd.concat([pivot, pd.DataFrame([totals])], ignore_index=True)

        for c in idx:
            if c in pivot.columns and pd.api.types.is_datetime64_any_dtype(pivot[c]):
                pivot[c] = pivot[c].dt.strftime('%d-%b-%y')
        for c in metric_cols: pivot[c] = pivot[c].apply(format_indian_number)

        html = pivot.to_html(classes='excel-table', border=0, index=False)
        html = html.replace('<th>TOTAL</th>', '<th class="total-col">TOTAL</th>')
        
        if 'TOTAL' in metric_cols:
            html = re.sub(r'(<td>)([\d,-]+)(</td></tr>)', r'<td class="total-col">\2\3', html)
        
        pivot.to_pickle(os.path.join(UPLOAD_DIR, "summary_data.pkl"))
        
        return jsonify({
            "table_html": html, "chart_data": chart_data,
            "dyn_title": dynamic_title, "dyn_date": date_subtitle, "kpi_html": kpi_html
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Backend Error: {str(e)}"}), 500

@app.route("/download", methods=["GET"])
def download():
    try:
        summary_path = os.path.join(UPLOAD_DIR, "summary_data.pkl")
        if not os.path.exists(summary_path): return "No data to download", 400
        df = pd.read_pickle(summary_path)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Dashboard_Report')
        output.seek(0)
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", download_name="Executive_Report.xlsx", as_attachment=True)
    except Exception as e:
        traceback.print_exc()
        return f"Download Failed: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)
