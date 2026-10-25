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
        --bg-main: #f5f5f7; --glass-sidebar: rgba(255, 255, 255, 0.85);
        --glass-border: rgba(0, 0, 0, 0.1); --text-primary: #1d1d1f; --text-secondary: #86868b;
        --shadow-glass: 0 10px 30px rgba(0,0,0,0.05); --blue-apple: #0071e3; --blue-hover: #0077ed;
        --header-bg: #f9f9fb; --header-text: #515154;
        --total-bg: #eaf3fe; --total-text: #1d1d1f;
        --green: #34c759; --card-bg: #ffffff;
    }
    body.dark-mode {
        --bg-main: #000000; --glass-sidebar: rgba(20, 20, 22, 0.85);
        --glass-border: rgba(255, 255, 255, 0.15); --text-primary: #f5f5f7; --text-secondary: #a1a1a6;
        --shadow-glass: 0 10px 30px rgba(0,0,0,0.5); --header-bg: #1c1c1e; --header-text: #a1a1a6;
        --total-bg: #10243b; --total-text: #f5f5f7;
        --green: #30d158; --card-bg: #151516;
    }
    body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif; background: var(--bg-main); color: var(--text-primary); margin: 0; padding: 0; transition: background 0.3s, color 0.3s; }
    
    .nav { background: var(--glass-sidebar); backdrop-filter: saturate(180%) blur(20px); border-bottom: 1px solid var(--glass-border); padding: 0 24px; height: 60px; display: flex; justify-content: space-between; align-items: center; position: fixed; top: 0; width: 100%; z-index: 1000; box-sizing: border-box; }
    .nav-brand { font-weight: 700; font-size: 18px; letter-spacing: -0.5px; }
    .nav-controls { display: flex; gap: 12px; align-items: center; }
    
    .btn-liquid { background: rgba(120, 120, 128, 0.1); border: 1px solid var(--glass-border); color: var(--text-primary); border-radius: 980px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; transition: 0.2s; }
    .btn-liquid:hover { background: rgba(120, 120, 128, 0.15); transform: scale(1.02); }
    .btn-primary { background: var(--blue-apple); color: #fff; border: none; }
    .btn-primary:hover { background: var(--blue-hover); }
    
    .app-layout { display: flex; height: 100vh; padding-top: 60px; box-sizing: border-box; }
    .sidebar { width: 350px; background: var(--glass-sidebar); backdrop-filter: blur(40px); border-right: 1px solid var(--glass-border); padding: 24px 20px; overflow-y: auto; flex-shrink: 0; }
    .main-content { flex: 1; padding: 32px 40px; overflow: hidden; display: flex; flex-direction: column; }
    
    .section-title { font-size: 12px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; margin: 24px 0 10px; letter-spacing: 0.5px; }
    .checkbox-group { background: rgba(120,120,128,0.05); border: 1px solid var(--glass-border); border-radius: 12px; padding: 8px; max-height: 220px; overflow-y: auto; }
    .checkbox-item { display: flex; align-items: center; padding: 8px 10px; font-size: 13px; cursor: pointer; border-radius: 8px; font-weight: 500; }
    .checkbox-item:hover { background: rgba(120,120,128,0.1); }
    .checkbox-item input[type="checkbox"]:not(.ios-switch), .checkbox-item input[type="radio"] { margin-right: 10px; accent-color: var(--blue-apple); width: 16px; height: 16px; }
    
    .btn-segmented { display: flex; background: rgba(120,120,128,0.1); border-radius: 12px; padding: 4px; gap: 4px; }
    .btn-segmented label { flex: 1; text-align: center; font-size: 13px; font-weight: 600; padding: 6px 16px; border-radius: 8px; cursor: pointer; color: var(--text-secondary); transition: 0.2s; z-index: 2; }
    .btn-segmented input { display: none; }
    .btn-segmented input:checked + label { color: var(--text-primary); }
    
    .table-container { background: var(--card-bg); border-radius: 16px; border: 1px solid var(--glass-border); flex: 1; overflow: hidden; display: flex; flex-direction: column; box-shadow: var(--shadow-glass); }
    
    .summary-bar { background: var(--card-bg); padding: 16px 20px; border-bottom: 1px solid var(--glass-border); font-size: 13px; font-weight: 500; display: flex; justify-content: space-between; align-items: center; color: var(--text-secondary); }
    .summary-bar b { color: var(--text-primary); font-weight: 600; }
    
    .table-scroll { flex: 1; overflow: auto; }
    .excel-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .excel-table th, .excel-table td { padding: 12px 20px; text-align: left; border-bottom: 1px solid var(--glass-border); white-space: nowrap; }
    .excel-table th { background: var(--header-bg); color: var(--header-text); font-size: 11px; text-transform: uppercase; position: sticky; top: 0; z-index: 10; font-weight: 600; letter-spacing: 0.05em; }
    .excel-table th:first-child, .excel-table td:first-child { position: sticky; left: 0; z-index: 20; background: var(--card-bg); font-weight: 600; box-shadow: 1px 0 0 var(--glass-border); }
    .excel-table th:first-child { z-index: 30; background: var(--header-bg); }
    
    .excel-table tbody tr:last-child td { font-weight: 700; background: var(--total-bg); color: var(--total-text); border-top: 1px solid var(--glass-border); border-bottom: none; position: sticky; bottom: 0; z-index: 15; }
    .excel-table tbody tr:last-child td:first-child { z-index: 25; }
    
    .kpis { display: flex; gap: 60px; margin-bottom: 32px; }
    .kpi { display: flex; flex-direction: column; }
    .kpi-label { font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
    .kpi-val { font-size: 34px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.03em; }

    /* iOS Toggle Switch */
    .switch-container { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; cursor: pointer; }
    .switch { position: relative; width: 44px; height: 24px; background: rgba(120,120,128,0.3); border-radius: 12px; transition: 0.3s; flex-shrink: 0; }
    .switch::after { content: ''; position: absolute; top: 2px; left: 2px; width: 20px; height: 20px; background: #fff; border-radius: 50%; box-shadow: 0 2px 4px rgba(0,0,0,0.2); transition: 0.3s; }
    input:checked + .switch { background: var(--green); }
    input:checked + .switch::after { transform: translateX(20px); }
    input.ios-switch { display: none; }
    
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .chip { padding: 6px 12px; border-radius: 8px; background: rgba(120,120,128,0.1); font-size: 12px; font-weight: 600; cursor: pointer; transition: 0.2s; border: none; color: var(--text-primary); }
    .chip.active { background: var(--blue-apple); color: #fff; }
</style>
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
        
        <form action="/dashboard" method="post" enctype="multipart/form-data" style="background: var(--card-bg); padding: 32px; border-radius: 24px; border: 1px solid var(--glass-border); box-shadow: var(--shadow-glass);">
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
            <button class="btn-liquid btn-primary" onclick="exportImage()">📸 Save Image</button>
            <button class="btn-liquid" id="dlExcel">📊 Download Excel</button>
        </div>
    </div>

    <div class="app-layout">
        <div class="sidebar">
            <form id="config-form">
                
                <div class="section-title" style="margin-top: 0;">Configure Axis Fields</div>
                <div class="checkbox-group">
                    <label class="switch-container">
                        <span style="font-size: 13px; font-weight: 500;">Select All Fields</span>
                        <input type="checkbox" class="ios-switch" onchange="toggleAll('master_fields', this.checked)">
                        <div class="switch"></div>
                    </label>
                    <div style="height: 1px; background: var(--glass-border); margin: 4px 0;"></div>
                    {% for col in grouping_cols %}
                    <label class="checkbox-item">
                        <input type="checkbox" name="master_fields" value="{{ col }}" onchange="updateAxisVisibility()" {% if loop.index <= 5 %}checked{% endif %}> 
                        <span>{{ col }}</span>
                    </label>
                    {% endfor %}
                </div>

                {% if status_list %}
                <div class="section-title">Final Status Filter</div>
                <div class="checkbox-group" style="max-height: 160px;">
                    <label class="switch-container">
                        <span style="font-size: 13px; font-weight: 500;">Select All Statuses</span>
                        <input type="checkbox" class="ios-switch" onchange="toggleAll('status_filters', this.checked)" checked>
                        <div class="switch"></div>
                    </label>
                    <div style="height: 1px; background: var(--glass-border); margin: 4px 0;"></div>
                    {% for st in status_list %}
                    <label class="checkbox-item"><input type="checkbox" name="status_filters" value="{{ st }}" checked onchange="updateDashboard()"> <span>{{ st }}</span></label>
                    {% endfor %}
                </div>
                {% endif %}
                
                <div class="section-title">Timeline & Comparison</div>
                <div class="chips">
                    <button type="button" class="chip" onclick="preset('yesterday', this)">Yesterday</button>
                    <button type="button" class="chip" onclick="preset('last7', this)">Last 7 Days</button>
                    <button type="button" class="chip" onclick="preset('mtd', this)">MTD</button>
                    <button type="button" class="chip" onclick="preset('lmtd', this)">LMTD</button>
                    <button type="button" class="chip" onclick="preset('lwtd', this)">LWTD</button>
                    <button type="button" class="chip" onclick="preset('ytd', this)">YTD</button>
                    <button type="button" class="chip" onclick="preset('lytd', this)">LYTD</button>
                </div>
                
                <div style="display:flex; gap:8px; margin-bottom: 12px;">
                    <div style="flex:1;">
                        <label style="font-size:10px; color:var(--text-secondary); font-weight:700;">FROM</label>
                        <input type="date" name="start_date" id="start_date" class="btn-liquid" style="width:100%; box-sizing:border-box;" onchange="updateDashboard()">
                    </div>
                    <div style="flex:1;">
                        <label style="font-size:10px; color:var(--text-secondary); font-weight:700;">TO</label>
                        <input type="date" name="end_date" id="end_date" class="btn-liquid" style="width:100%; box-sizing:border-box;" onchange="updateDashboard()">
                    </div>
                </div>

                <div class="checkbox-group" style="margin-bottom: 12px;">
                    <label class="switch-container">
                        <span style="font-size: 13px; font-weight: 600;">Enable Period Comparison</span>
                        <input type="checkbox" name="compare_mode" value="lmtd" class="ios-switch" onchange="updateDashboard()">
                        <div class="switch"></div>
                    </label>
                </div>
                
                <div class="section-title">Filter by Weeks</div>
                <div class="checkbox-group" style="margin-bottom: 12px;">
                    <label class="switch-container">
                        <span style="font-size: 13px; font-weight: 500;">Select All Weeks</span>
                        <input type="checkbox" class="ios-switch" onchange="toggleAll('week_num', this.checked)">
                        <div class="switch"></div>
                    </label>
                    <div style="height: 1px; background: var(--glass-border); margin: 4px 0;"></div>
                    <label class="checkbox-item"><input type="checkbox" name="week_num" value="1" onchange="updateDashboard()"> <span>Week 1 (Days 1–7)</span></label>
                    <label class="checkbox-item"><input type="checkbox" name="week_num" value="2" onchange="updateDashboard()"> <span>Week 2 (Days 8–14)</span></label>
                    <label class="checkbox-item"><input type="checkbox" name="week_num" value="3" onchange="updateDashboard()"> <span>Week 3 (Days 15–21)</span></label>
                    <label class="checkbox-item"><input type="checkbox" name="week_num" value="4" onchange="updateDashboard()"> <span>Week 4 (Days 22–28)</span></label>
                    <label class="checkbox-item"><input type="checkbox" name="week_num" value="5" onchange="updateDashboard()"> <span>Week 5 (Days 29+)</span></label>
                </div>

                <div id="pivot-controls">
                    <div class="section-title">Rows (Y-Axis)</div>
                    <div class="checkbox-group">
                        <label class="switch-container">
                            <span style="font-size: 13px; font-weight: 500;">Select All Rows</span>
                            <input type="checkbox" class="ios-switch" onchange="toggleAll('index_cols', this.checked)">
                            <div class="switch"></div>
                        </label>
                        <div style="height: 1px; background: var(--glass-border); margin: 4px 0;"></div>
                        {% for col in grouping_cols %}
                        <label class="checkbox-item axis-row-item" data-field="{{ col }}"><input type="checkbox" name="index_cols" value="{{ col }}" onchange="updateDashboard()"> <span>{{ col }}</span></label>
                        {% endfor %}
                    </div>
                    
                    <div class="section-title">Columns (X-Axis)</div>
                    <div class="checkbox-group">
                        <label class="switch-container">
                            <span style="font-size: 13px; font-weight: 500;">Select All Columns</span>
                            <input type="checkbox" class="ios-switch" onchange="toggleAll('columns_cols', this.checked)">
                            <div class="switch"></div>
                        </label>
                        <div style="height: 1px; background: var(--glass-border); margin: 4px 0;"></div>
                        {% for col in grouping_cols %}
                        <label class="checkbox-item axis-col-item" data-field="{{ col }}"><input type="checkbox" name="columns_cols" value="{{ col }}" onchange="updateDashboard()"> <span>{{ col }}</span></label>
                        {% endfor %}
                    </div>

                    <div class="section-title">Metrics & Configuration</div>
                    <label style="font-size: 10px; color: var(--text-secondary); margin-bottom: 4px; display:block;">VALUE FIELD</label>
                    <div class="checkbox-group" style="margin-bottom: 12px; max-height: 120px;">
                        {% for col in num_cols %}
                        <label class="checkbox-item"><input type="radio" name="value_col" value="{{ col }}" {% if loop.first %}checked{% endif %} onchange="updateDashboard()"> <span>{{ col }}</span></label>
                        {% endfor %}
                    </div>
                    
                    <label style="font-size: 10px; color: var(--text-secondary); margin-bottom: 4px; display:block;">AGGREGATION</label>
                    <div class="checkbox-group">
                        <label class="switch-container">
                            <span style="font-size: 13px; font-weight: 500;">Sum Total</span>
                            <input type="checkbox" name="agg_funcs" value="sum" class="ios-switch" checked onchange="updateDashboard()">
                            <div class="switch"></div>
                        </label>
                        <label class="switch-container">
                            <span style="font-size: 13px; font-weight: 500;">Count (Qty)</span>
                            <input type="checkbox" name="agg_funcs" value="count" class="ios-switch" onchange="updateDashboard()">
                            <div class="switch"></div>
                        </label>
                        <div style="height: 1px; background: var(--glass-border); margin: 4px 0;"></div>
                        
                        <label class="switch-container" id="total_wrapper">
                            <span style="font-size: 13px; font-weight: 500;">Show Grand Totals</span>
                            <input type="checkbox" id="show_total_cb" class="ios-switch" name="show_row_total" value="true" checked onchange="updateDashboard()">
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
            <div style="display: flex; justify-content: flex-end; margin-bottom: 12px;">
                <div class="btn-segmented" style="position: relative; width: 200px;">
                    <div class="seg-thumb" style="position: absolute; top: 4px; bottom: 4px; left: 4px; width: calc(50% - 4px); background: var(--card-bg); border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); transition: 0.3s; z-index: 1;"></div>
                    <input type="radio" id="view_dash" name="view_mode_toggle" value="dashboard" checked onchange="updateDashboard()">
                    <label for="view_dash">Pivot</label>
                    <input type="radio" id="view_chart" name="view_mode_toggle" value="chart" onchange="updateDashboard()">
                    <label for="view_chart">Chart</label>
                </div>
            </div>
            
            <div id="kpi-banner" class="kpis"></div>
            
            <div class="table-container" id="capture-area">
                <div class="summary-bar" id="summaryBar">Select fields to build your view.</div>
                <div id="table-wrapper" class="table-scroll">
                    <div style="padding: 60px; text-align: center; color: var(--text-secondary); font-size: 15px;">Configure Y-Axis and metrics to preview data.</div>
                </div>
                <div id="chart-wrapper" style="display:none; padding: 20px; flex: 1; min-height: 450px;"><canvas id="dataChart"></canvas></div>
            </div>
        </div>
    </div>

    <script>
        function updateAxisVisibility() {
            const selectedFields = Array.from(document.querySelectorAll('input[name="master_fields"]:checked')).map(cb => cb.value);
            
            document.querySelectorAll('.axis-row-item').forEach(item => {
                const field = item.getAttribute('data-field');
                if (selectedFields.includes(field)) item.style.display = 'flex';
                else { item.style.display = 'none'; item.querySelector('input').checked = false; }
            });

            document.querySelectorAll('.axis-col-item').forEach(item => {
                const field = item.getAttribute('data-field');
                if (selectedFields.includes(field)) item.style.display = 'flex';
                else { item.style.display = 'none'; item.querySelector('input').checked = false; }
            });
            updateDashboard();
        }
        
        function toggleAll(groupName, isChecked) {
            document.querySelectorAll(`input[name="${groupName}"]`).forEach(cb => {
                if (groupName === 'index_cols' || groupName === 'columns_cols') {
                    if (cb.parentElement.style.display !== 'none') cb.checked = isChecked;
                } else {
                    cb.checked = isChecked;
                }
            });
            if(groupName === 'master_fields') updateAxisVisibility();
            else updateDashboard();
        }

        document.querySelectorAll('input[name="view_mode_toggle"]').forEach(radio => {
            radio.addEventListener('change', function() {
                const thumb = document.querySelector('.seg-thumb');
                thumb.style.transform = this.value === 'chart' ? 'translateX(100%)' : 'translateX(0)';
                document.getElementById('dlExcel').style.display = this.value === 'chart' ? 'none' : 'flex';
                updateDashboard();
            });
        });

        function toggleDarkMode() { 
            const isDark = document.body.classList.toggle('dark-mode'); 
            document.getElementById('dm-btn').innerText = isDark ? '☀️ Light' : '🌙 Dark';
            if(document.querySelector('input[name="view_mode_toggle"]:checked').value === 'chart') updateDashboard();
        }

        const iso = d => new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
        function preset(key, chip) {
            document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            
            const t = new Date(); let s = new Date(t), e = new Date(t);
            if (key === 'yesterday') { s.setDate(t.getDate() - 1); e.setDate(t.getDate() - 1); }
            else if (key === 'last7') { s.setDate(t.getDate() - 6); }
            else if (key === 'mtd') { s = new Date(t.getFullYear(), t.getMonth(), 1); }
            else if (key === 'lmtd') { s = new Date(t.getFullYear(), t.getMonth() - 1, 1); e = new Date(t.getFullYear(), t.getMonth() - 1, t.getDate()); }
            else if (key === 'lwtd') { let day = t.getDay() || 7; s.setDate(t.getDate() - day - 6); e.setDate(t.getDate() - day); }
            else if (key === 'ytd') { s = new Date(t.getFullYear(), 0, 1); }
            else if (key === 'lytd') { s = new Date(t.getFullYear() - 1, 0, 1); e = new Date(t.getFullYear() - 1, t.getMonth(), t.getDate()); }
            
            document.getElementById('start_date').value = iso(s);
            document.getElementById('end_date').value = iso(e);
            updateDashboard();
        }

        let chartInstance = null;

        async function updateDashboard() {
            const form = document.getElementById('config-form');
            const formData = new FormData(form);
            const mode = document.querySelector('input[name="view_mode_toggle"]:checked').value;
            formData.append('view_mode', mode);

            const metrics = formData.getAll('agg_funcs');
            const totalCb = document.getElementById('show_total_cb');
            const totalWrap = document.getElementById('total_wrapper');
            
            if(metrics.includes('sum') && metrics.includes('count')) {
                totalCb.checked = false; totalCb.disabled = true; totalWrap.style.opacity = '0.4';
            } else {
                totalCb.disabled = false; totalWrap.style.opacity = '1';
            }

            try {
                const res = await fetch('/calculate', { method: 'POST', body: formData });
                let data;
                try { data = await res.json(); } 
                catch (e) { document.getElementById('table-wrapper').innerHTML = `<div style="padding:40px; color:#ff3b30; text-align:center; font-weight:600;">Server Error</div>`; return; }
                
                if (data.error) {
                    document.getElementById('chart-wrapper').style.display = 'none';
                    document.getElementById('table-wrapper').style.display = 'block';
                    document.getElementById('summaryBar').innerText = "Configuration Required";
                    document.getElementById('table-wrapper').innerHTML = `<div style="padding:40px; color:#ff3b30; text-align:center; font-weight:600;">${data.error}</div>`;
                    return;
                }
                
                document.getElementById('summaryBar').innerHTML = data.summary_text || "Data View";
                const kpiBanner = document.getElementById('kpi-banner');
                kpiBanner.innerHTML = data.kpi_html || '';
                
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
            } catch(e) { console.error(e); }
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

        function exportImage() {
            const mode = document.querySelector('input[name="view_mode_toggle"]:checked').value;
            if (mode === 'chart' && chartInstance) {
                const a = document.createElement('a'); a.download = 'Chart_Export.png';
                a.href = chartInstance.toBase64Image(); a.click();
            } else {
                const area = document.getElementById('capture-area');
                const bgColor = document.body.classList.contains('dark-mode') ? '#151516' : '#ffffff';
                const scrollEl = area.querySelector('.table-scroll');
                const origOverflow = scrollEl.style.overflow;
                const origHeight = scrollEl.style.height;
                scrollEl.style.overflow = 'visible';
                scrollEl.style.height = 'auto';
                
                domtoimage.toJpeg(area, { quality: 1.0, bgcolor: bgColor, height: area.scrollHeight })
                    .then(url => {
                        const a = document.createElement('a'); a.download = 'Executive_Report.jpeg'; a.href = url; a.click();
                        scrollEl.style.overflow = origOverflow;
                        scrollEl.style.height = origHeight;
                    })
                    .catch(err => { 
                        console.error(err); 
                        scrollEl.style.overflow = origOverflow;
                        scrollEl.style.height = origHeight;
                    });
            }
        }
        
        document.getElementById('dlExcel').addEventListener('click', () => { 
            const fd = new URLSearchParams(new FormData(document.getElementById('config-form'))); 
            location.href = '/download?' + fd.toString(); 
        });
        
        document.getElementById('start_date').addEventListener('change', () => document.querySelectorAll('.chip').forEach(c => c.classList.remove('active')));
        document.getElementById('end_date').addEventListener('change', () => document.querySelectorAll('.chip').forEach(c => c.classList.remove('active')));
        
        window.onload = () => { updateAxisVisibility(); };
    </script>
</body>
</html>
"""

def get_master_data():
    if os.path.exists(DATA_FILE_PATH):
        try:
            with open(DATA_FILE_PATH, 'rb') as f:
                saved = pd.read_pickle(f)
            df = saved['df'] if isinstance(saved, dict) and 'df' in saved else saved
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
    df = get_master_data()
    if df is not None:
        cols = df.columns.tolist()
        grouping = [c for c in df.select_dtypes(exclude=['number']).columns.tolist() if c != 'Month']
        if 'Month' not in grouping: grouping.insert(0, 'Month')
        
        if 'Tentative DP' in df.columns:
            df['Tentative DP'] = pd.to_numeric(df['Tentative DP'].astype(str).str.replace(',', ''), errors='coerce')
        num_cols = df.select_dtypes(include='number').columns.tolist()
        
        status_col = next((c for c in cols if 'status' in c.lower() or 'remarks' in c.lower()), None)
        status_list = []
        if status_col:
            raw_vals = df[status_col].dropna().astype(str).unique().tolist()
            status_list = sorted([v for v in raw_vals if v.lower() != 'finalstatus' and v.strip() != ''])
        
        return render_template_string(WORKSPACE_HTML, all_cols=cols, grouping_cols=grouping, num_cols=num_cols, status_list=status_list)
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
            xls = pd.ExcelFile(f)
            dfs = []
            for sheet in xls.sheet_names:
                temp_df = pd.read_excel(xls, sheet_name=sheet)
                if not temp_df.empty:
                    dfs.append(temp_df)
            df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        else:
            return render_template_string(UPLOAD_HTML, error="Unsupported file type."), 400
        
        if df.empty: return render_template_string(UPLOAD_HTML, error="File contains no data."), 400

        # Dynamically Extract Month Name from Master Date Column
        date_col_name = ""
        for c in ("Customized Sales Date", "Sale Date", "Sales Date"):
            if c in df.columns:
                date_col_name = c
                break
        if not date_col_name:
            for c in df.columns:
                if "date" in c.lower() and "activation" not in c.lower() and "tertiary" not in c.lower():
                    date_col_name = c
                    break
        
        if date_col_name:
            parsed_dates = pd.to_datetime(df[date_col_name], errors='coerce')
            df['Month'] = parsed_dates.dt.strftime('%b %Y').fillna('Unknown')
        else:
            df['Month'] = 'Current'

        df.to_pickle(DATA_FILE_PATH)
        return redirect(url_for('home'))
    except Exception as e:
        return render_template_string(UPLOAD_HTML, error=f"Error reading file: {str(e)}"), 400

@app.route("/calculate", methods=["POST"])
def calculate():
    try:
        df = get_master_data()
        if df is None: return jsonify({"error": "No data available. Please re-upload."}), 400
        
        mode = request.form.get('view_mode', 'dashboard')
        filter_texts = []
        
        status_col = next((c for c in df.columns if 'status' in c.lower() or 'remarks' in c.lower()), None)
        status_filters = request.form.getlist('status_filters')
        if status_col and status_filters:
            df = df[df[status_col].astype(str).isin(status_filters)]
            if len(status_filters) <= 3: filter_texts.append(f"Status: {', '.join(status_filters)}")
            else: filter_texts.append(f"Status: {len(status_filters)} selected")

        date_cols = df.columns.tolist()
        date_col_name = ""
        for c in ("Customized Sales Date", "Sale Date", "Sales Date"):
            if c in date_cols:
                date_col_name = c
                break
        if not date_col_name:
            for c in date_cols:
                if "date" in c.lower() and "activation" not in c.lower() and "tertiary" not in c.lower():
                    date_col_name = c
                    break
                    
        if date_col_name: df[date_col_name] = pd.to_datetime(df[date_col_name], errors='coerce')

        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        weeks = request.form.getlist("week_num")
        compare_mode = request.form.get('compare_mode')
        
        if date_col_name:
            if compare_mode == 'lmtd' and start_date and end_date:
                s_dt = pd.to_datetime(start_date)
                e_dt = pd.to_datetime(end_date)
                delta = (e_dt - s_dt).days + 1
                
                ls_dt = s_dt - pd.Timedelta(days=delta)
                le_dt = e_dt - pd.Timedelta(days=delta)
                
                df_curr = df[(df[date_col_name] >= s_dt) & (df[date_col_name] <= e_dt + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]
                df_prev = df[(df[date_col_name] >= ls_dt) & (df[date_col_name] <= le_dt + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]
                
                df_curr['Period'] = f"Current ({s_dt.strftime('%d-%b')} - {e_dt.strftime('%d-%b')})"
                df_prev['Period'] = f"Previous ({ls_dt.strftime('%d-%b')} - {le_dt.strftime('%d-%b')})"
                df = pd.concat([df_curr, df_prev], ignore_index=True)
                filter_texts.append(f"Comparison Mode Active")
            else:
                if start_date: 
                    df = df[df[date_col_name] >= pd.to_datetime(start_date)]
                    filter_texts.append(f"{pd.to_datetime(start_date).strftime('%d-%b-%y')}")
                if end_date: 
                    df = df[df[date_col_name] <= pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
                    filter_texts.append(f"{pd.to_datetime(end_date).strftime('%d-%b-%y')}")
                    
            if weeks and date_col_name and 'Period' not in df.columns:
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
        if compare_mode == 'lmtd' and 'Period' not in idx: idx.insert(0, 'Period')
        
        date_subtitle = " – ".join(filter_texts[:2]) if len(filter_texts)>=2 and "From" not in filter_texts[0] else (" · ".join(filter_texts) if filter_texts else "All Time")
        
        val_col = request.form.get('value_col')
        if val_col and val_col in df.columns:
            if df[val_col].dtype == object: df[val_col] = pd.to_numeric(df[val_col].astype(str).str.replace(',', ''), errors='coerce')
        else:
            num_cols = df.select_dtypes(include='number').columns.tolist()
            val_col = num_cols[0] if num_cols else None

        aggs = request.form.getlist('agg_funcs')
        if not aggs: aggs = ['sum']
        
        kpi_html = ""
        if not df.empty and val_col:
            active = format_indian_number(df[idx[0]].nunique()) if idx and idx[0] in df.columns else "N/A"
            kpi_html = f"""
                <div class="kpi"><div class="kpi-label">Total Volume</div><div class="kpi-val">{format_indian_number(df[val_col].sum())}</div></div>
                <div class="kpi"><div class="kpi-label">Records</div><div class="kpi-val">{format_indian_number(len(df))}</div></div>
                <div class="kpi"><div class="kpi-label">Active Entities</div><div class="kpi-val">{active}</div></div>
            """

        if df.empty:
            return jsonify({"table_html": '<div style="padding:60px; text-align:center;">No data found for selected filters.</div>', "summary_text": f"<b>Date</b> {date_subtitle} · 0 groups", "kpi_html": kpi_html})

        cols = request.form.getlist('columns_cols')
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
                            if isinstance(x, pd.Timestamp): parts.append(x.strftime('%d-%b-%y'))
                            else: parts.append(str(x))
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
            labels = chart_df[idx[0]].apply(lambda x: x.strftime('%d-%b-%y') if isinstance(x, pd.Timestamp) else str(x)).tolist() if idx else ["Total"]
            
            palette = ['#0071e3', '#34c759', '#ff9500', '#af52de', '#ff3b30', '#5ac8fa', '#ffcc00', '#5856d6']
            datasets = []
            for i, m in enumerate(metric_cols):
                if m != "TOTAL":
                    color = palette[i % len(palette)]
                    datasets.append({"label": m, "data": chart_df[m].tolist(), "backgroundColor": color, "borderRadius": 6})
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
        if 'TOTAL' in metric_cols: html = re.sub(r'(<td>)([\d,-]+)(</td></tr>)', r'<td class="total-col">\2\3', html)
        
        pivot.to_pickle(os.path.join(UPLOAD_DIR, "summary_data.pkl"))
        summary_text = f"<b>Date</b> {date_subtitle} · <b>Filters</b> {' + '.join(idx)} · {len(pivot)-1} groups"
        
        return jsonify({
            "table_html": html, "chart_data": chart_data,
            "summary_text": summary_text, "kpi_html": kpi_html
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
        with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False, sheet_name='Dashboard_Report')
        output.seek(0)
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", download_name="Executive_Report.xlsx", as_attachment=True)
    except Exception as e:
        traceback.print_exc()
        return f"Download Failed: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)
