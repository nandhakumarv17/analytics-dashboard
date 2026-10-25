import os
import io
import json
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, send_file, jsonify, redirect, url_for
import pandas as pd
import numpy as np

app = Flask(__name__)

UPLOAD_DIR = "/tmp/dashboard_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATA_FILE_PATH = os.path.join(UPLOAD_DIR, "shared_data.pkl")
META_FILE_PATH = os.path.join(UPLOAD_DIR, "metadata.pkl")

# --- APPLE iOS "LIQUID GLASS" THEME & STICKY MOBILE ENGINE ---
GLOBAL_HEAD = """
<style>
    :root {
        --bg-main: #f2f2f7;
        --glass-bg: rgba(255, 255, 255, 0.78);
        --glass-sidebar: rgba(255, 255, 255, 0.85);
        --glass-border: rgba(255, 255, 255, 0.85);
        --text-primary: #1d1d1f;
        --text-secondary: #86868b;
        --shadow-glass: 0 20px 40px rgba(0, 0, 0, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04);
        --blue-apple: #0071e3;
        --blue-hover: #0077ed;
        --code-pink: #ff375f; --code-purple: #bf5af2; --code-blue: #5ac8fa; --code-orange: #ff9f0a; --code-green: #32d74b;
    }
    body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg-main); margin: 0; padding: 0; color: var(--text-primary); -webkit-font-smoothing: antialiased; }
    .nav { background: rgba(255, 255, 255, 0.85); backdrop-filter: saturate(200%) blur(30px); border-bottom: 1px solid rgba(0, 0, 0, 0.08); padding: 0 24px; height: 60px; display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: 600; color: var(--text-primary); position: fixed; top: 0; width: 100%; box-sizing: border-box; z-index: 1000; }
    .view-toggle { background: rgba(0,0,0,0.04); padding: 8px 14px; border-radius: 980px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; transition: 0.2s; border: none; color: var(--text-primary); flex-shrink: 0; }
    .view-toggle:hover { background: rgba(0,0,0,0.08); }
    .upload-container { max-width: 480px; margin: 120px auto 40px auto; padding: 0 16px; box-sizing: border-box; animation: fadeIn 0.4s ease; }
    .title { font-size: 36px; font-weight: 700; letter-spacing: -0.015em; text-align: center; margin: 0 0 8px 0; }
    .subtitle { font-size: 16px; font-weight: 400; text-align: center; color: var(--text-secondary); margin: 0 0 32px 0; }
    .card { background: var(--glass-bg); backdrop-filter: blur(25px) saturate(180%); border-radius: 24px; padding: 32px; box-shadow: var(--shadow-glass); border: 1px solid var(--glass-border); box-sizing: border-box; }
    
    .sidebar-section { margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid rgba(0,0,0,0.06); transition: opacity 0.3s ease; }
    .sidebar-section:last-child { border-bottom: none; }
    .section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 0.03em; }
    .form-group { margin-bottom: 16px; }
    .form-label { font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; margin-bottom: 6px; display: block; }
    .form-label-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .form-label-header .form-label { margin-bottom: 0; }
    .btn-micro { background: rgba(0,0,0,0.04); border: none; color: var(--blue-apple); font-size: 10px; font-weight: 600; cursor: pointer; padding: 4px 8px; border-radius: 6px; transition: 0.2s; }
    .btn-micro:hover { background: rgba(0,113,227,0.1); }
    .form-input { width: 100%; padding: 10px 12px; font-size: 13px; border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; background-color: rgba(255,255,255,0.9); color: var(--text-primary); box-sizing: border-box; transition: all 0.2s ease; margin-bottom: 8px; }
    .form-input:focus { border-color: var(--blue-apple); outline: none; box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.15); }
    .checkbox-group { background: rgba(255,255,255,0.6); border: 1px solid rgba(0,0,0,0.08); border-radius: 10px; padding: 8px; max-height: 160px; overflow-y: auto; }
    .checkbox-item { display: flex; align-items: center; margin-bottom: 4px; font-size: 13px; cursor: pointer; padding: 6px 8px; border-radius: 6px; transition: background 0.15s; }
    .checkbox-item:hover { background: rgba(0,0,0,0.04); }
    .checkbox-item:last-child { margin-bottom: 0; }
    .checkbox-item input { margin-right: 10px; width: 16px; height: 16px; accent-color: var(--blue-apple); cursor: pointer; flex-shrink: 0; }
    .btn-primary { background-color: var(--blue-apple); color: white; border: none; border-radius: 980px; padding: 12px 20px; font-size: 14px; font-weight: 600; cursor: pointer; text-align: center; display: inline-flex; align-items: center; justify-content: center; text-decoration: none; box-sizing: border-box; transition: background 0.2s, transform 0.1s; width: 100%; }
    .btn-primary:hover { background-color: var(--blue-hover); }
    .btn-segmented { display: flex; background: rgba(0,0,0,0.05); border-radius: 10px; padding: 4px; gap: 4px; box-shadow: inset 0 1px 3px rgba(0,0,0,0.06); }
    .btn-segmented label { flex: 1; text-align: center; font-size: 12px; font-weight: 600; padding: 6px 16px; border-radius: 8px; cursor: pointer; color: var(--text-secondary); transition: 0.2s; white-space: nowrap; }
    .btn-segmented input { display: none; }
    .btn-segmented input:checked + label { background: #ffffff; color: var(--text-primary); box-shadow: 0 2px 6px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04); }
    .date-preset-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 12px; }
    .date-preset-btn { background: rgba(0,0,0,0.03); border: 1px solid rgba(0,0,0,0.05); color: var(--text-primary); padding: 8px; font-size: 11px; font-weight: 600; border-radius: 8px; cursor: pointer; transition: 0.2s; text-align: center; }
    .date-preset-btn:hover { background: rgba(0,113,227,0.1); color: var(--blue-apple); }
    .date-preset-btn.active { background: var(--blue-apple); color: #ffffff; border-color: var(--blue-apple); }
    .kpi-ribbon { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; animation: fadeIn 0.4s ease; }
    .kpi-card { flex: 1; min-width: 140px; background: rgba(255,255,255,0.85); backdrop-filter: blur(25px); border: 1px solid var(--glass-border); border-radius: 16px; padding: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); display: flex; flex-direction: column; justify-content: center; }
    .kpi-card .kpi-label { font-size: 11px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
    .kpi-card .kpi-val { font-size: 24px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; }
    .dropdown { position: relative; display: inline-block; }
    .dropdown-content { display: none; position: absolute; right: 0; background-color: rgba(255,255,255,0.95); backdrop-filter: blur(30px); min-width: 170px; box-shadow: 0 15px 35px rgba(0,0,0,0.12); border-radius: 16px; border: 1px solid rgba(255,255,255,0.8); z-index: 2000; overflow: hidden; margin-top: 8px; }
    .dropdown-content.show { display: block; animation: fadeIn 0.2s ease; }
    .dropdown-item { color: var(--text-primary); padding: 12px 16px; text-decoration: none; display: block; font-size: 13px; font-weight: 500; cursor: pointer; border: none; background: none; width: 100%; text-align: left; transition: background 0.2s; }
    .dropdown-item:hover { background-color: rgba(0,113,227,0.08); color: var(--blue-apple); }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }

    .table-container { background: var(--glass-bg); backdrop-filter: blur(25px); border-radius: 20px; box-shadow: var(--shadow-glass); border: 1px solid var(--glass-border); overflow: hidden; width: 100%; box-sizing: border-box; display: flex; flex-direction: column; animation: fadeIn 0.5s ease; }
    .filter-text-bar { padding: 14px 20px; border-bottom: 1px solid rgba(0,0,0,0.06); background: rgba(255,255,255,0.6); }
    .table-scroll { max-height: calc(100vh - 280px); overflow-y: auto; overflow-x: auto; -webkit-overflow-scrolling: touch; position: relative; }
    .excel-table { width: max-content; min-width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; background: transparent; }
    .excel-table th, .excel-table td { padding: 14px 20px; text-align: left; border-bottom: 1px solid rgba(0,0,0,0.06); white-space: nowrap; position: relative; }
    .excel-table th { background-color: rgba(30, 30, 34, 0.85); backdrop-filter: blur(20px) saturate(180%); font-family: 'SF Mono', ui-monospace, Menlo, Monaco, monospace; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; position: sticky; top: 0; z-index: 100; border-bottom: 1px solid rgba(255,255,255,0.1); user-select: none; }
    .excel-table th:nth-child(5n+1) { color: var(--code-blue); }
    .excel-table th:nth-child(5n+2) { color: var(--code-pink); }
    .excel-table th:nth-child(5n+3) { color: var(--code-orange); }
    .excel-table th:nth-child(5n+4) { color: var(--code-green); }
    .excel-table th:nth-child(5n+5) { color: var(--code-purple); }
    .resizer { position: absolute; right: 0; top: 0; bottom: 0; width: 6px; cursor: col-resize; z-index: 101; }
    .resizer:hover { background-color: rgba(0, 113, 227, 0.4); }
    .excel-table tr:hover td { background-color: rgba(0, 113, 227, 0.04); }
    .excel-table th.total-col-header { color: #ffffff !important; background-color: rgba(20, 20, 24, 0.98); border-left: 1px solid rgba(255,255,255,0.1); }
    .excel-table td.total-col-cell { background-color: rgba(0, 113, 227, 0.03); font-weight: 600; border-left: 1px solid rgba(0, 113, 227, 0.1); }
    .excel-table tbody tr:last-child td { font-weight: 700; background-color: rgba(0, 113, 227, 0.12); color: var(--blue-apple); border-top: 2px solid var(--blue-apple); border-bottom: none; box-shadow: inset 0 1px 0 rgba(255,255,255,0.6); }
    .number-cell { font-variant-numeric: tabular-nums; }
    .pct-positive { color: #34c759; font-weight: 600; }
    .pct-negative { color: #ff3b30; font-weight: 600; }
    .pct-neutral { color: var(--text-secondary); }

    /* HIGH-CONTRAST EXPORT MODE HACK */
    body.export-mode .main-content { background: #ffffff !important; }
    body.export-mode .kpi-card { background: #f2f2f7 !important; backdrop-filter: none !important; border: 1px solid #d1d1d6 !important; box-shadow: none !important; }
    body.export-mode .kpi-card .kpi-label { color: #86868b !important; }
    body.export-mode .kpi-card .kpi-val { color: #000000 !important; }
    body.export-mode .table-container { background: #ffffff !important; backdrop-filter: none !important; border: 1px solid #d1d1d6 !important; box-shadow: none !important; }
    body.export-mode .filter-text-bar { background: #f2f2f7 !important; color: #000000 !important; border-bottom: 1px solid #d1d1d6 !important; }
    body.export-mode .excel-table th { background-color: #f2f2f7 !important; color: #000000 !important; backdrop-filter: none !important; border-bottom: 1px solid #d1d1d6 !important; border-right: 1px solid #d1d1d6 !important; }
    body.export-mode .excel-table td { background-color: #ffffff !important; color: #000000 !important; border-bottom: 1px solid #e5e5ea !important; border-right: 1px solid #e5e5ea !important; }
    body.export-mode .excel-table th.total-col-header { background-color: #e5e5ea !important; color: #000000 !important; }
    body.export-mode .excel-table td.total-col-cell { background-color: #f8f8f8 !important; color: #000000 !important; }
    body.export-mode .excel-table tbody tr:last-child td { background-color: #e5e5ea !important; color: #000000 !important; border-top: 2px solid #000000 !important; }
    body.export-mode .pct-positive { color: #28a745 !important; }
    body.export-mode .pct-negative { color: #dc3545 !important; }

    /* Layout & Sidebar Resizer */
    body.desktop-mode { overflow: hidden; }
    body.desktop-mode .app-layout { display: flex; flex-direction: row; height: 100vh; padding-top: 60px; box-sizing: border-box; }
    body.desktop-mode .sidebar { width: 320px; background: var(--glass-sidebar); backdrop-filter: blur(40px) saturate(180%); padding: 24px 20px; overflow-y: auto; flex-shrink: 0; box-sizing: border-box; height: calc(100vh - 60px); }
    .sidebar-resizer { width: 5px; background: rgba(0,0,0,0.02); cursor: col-resize; z-index: 100; transition: background 0.2s; flex-shrink: 0; border-right: 1px solid rgba(0,0,0,0.06); }
    .sidebar-resizer:hover, .sidebar-resizer.resizing { background: var(--blue-apple); }
    body.desktop-mode .main-content { flex: 1; padding: 24px 32px; overflow-y: auto; overflow-x: hidden; background: var(--bg-main); box-sizing: border-box; height: calc(100vh - 60px); }
    body.desktop-mode .header-actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 16px; }
    
    body.mobile-mode { overflow: auto; }
    body.mobile-mode .app-layout { display: flex; flex-direction: column; padding-top: 60px; box-sizing: border-box; }
    body.mobile-mode .sidebar { width: 100% !important; background: var(--glass-sidebar); border-right: none; border-bottom: 1px solid rgba(0,0,0,0.08); padding: 20px; box-sizing: border-box; }
    body.mobile-mode .sidebar-resizer { display: none; }
    body.mobile-mode .main-content { width: 100%; padding: 20px; box-sizing: border-box; background: var(--bg-main); }
    body.mobile-mode .header-actions { display: flex; flex-direction: column; align-items: stretch; gap: 12px; margin-bottom: 20px; }
    body.mobile-mode .header-actions .dropdown { width: 100%; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.2); border-radius: 10px; }
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/dom-to-image/2.6.0/dom-to-image.min.js"></script>
<script>
    function toggleViewMode() {
        const body = document.body;
        const btn = document.getElementById('viewToggleBtn');
        if (body.classList.contains('desktop-mode')) {
            body.classList.remove('desktop-mode');
            body.classList.add('mobile-mode');
            if(btn) btn.innerHTML = "📱 Mobile Site";
        } else {
            body.classList.remove('mobile-mode');
            body.classList.add('desktop-mode');
            if(btn) btn.innerHTML = "💻 Desktop Site";
        }
    }
    function toggleExportMenu() {
        document.getElementById("exportDropdown").classList.toggle("show");
    }
    window.onclick = function(event) {
        if (!event.target.matches('.btn-primary') && !event.target.closest('.dropdown')) {
            var dropdowns = document.getElementsByClassName("dropdown-content");
            for (var i = 0; i < dropdowns.length; i++) {
                if (dropdowns[i].classList.contains('show')) dropdowns[i].classList.remove('show');
            }
        }
    }
</script>
"""

UPLOAD_HTML = """
<!DOCTYPE html>
<html>
<head><title>Data Portal - Analytics Pro</title><meta name="viewport" content="width=device-width, initial-scale=1.0">""" + GLOBAL_HEAD + """</head>
<body style="background: #f2f2f7;">
    <div class="nav">
        <div>Analytics Pro</div>
        <div>
            <button class="view-toggle" onclick="toggleViewMode()" id="viewToggleBtn">💻 Desktop Site</button>
        </div>
    </div>
    <div class="upload-container">
        <h1 class="title">Analytics Engine.</h1>
        <p class="subtitle">Upload your data to launch the Business Intelligence workspace.</p>
        <div class="card">
            <form action="/dashboard" method="post" enctype="multipart/form-data">
                <div class="form-group">
                    <input type="file" name="file" accept=".xlsx, .xls, .csv" required class="form-input" style="border: 2px dashed rgba(0,0,0,0.15); background: rgba(255,255,255,0.5); padding: 30px; text-align: center; cursor: pointer;">
                </div>
                <button type="submit" class="btn-primary">Launch Workspace →</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

WORKSPACE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Intelligence Workspace</title><meta name="viewport" content="width=device-width, initial-scale=1.0">""" + GLOBAL_HEAD + """</head>
<body>
    <div class="nav">
        <div>Analytics Pro</div>
        <div style="display: flex; align-items: center;">
            <button class="view-toggle" onclick="toggleViewMode()" id="viewToggleBtn">💻 Desktop Site</button>
        </div>
    </div>
    
    <div class="app-layout">
        <div class="sidebar" id="appSidebar">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                <h2 style="font-size: 20px; font-weight: 700; margin: 0; letter-spacing: -0.015em;">Workspace</h2>
                <button type="button" onclick="clearAll()" style="background: rgba(0,113,227,0.1); border: none; color: var(--blue-apple); font-size: 11px; font-weight: 600; cursor: pointer; padding: 6px 12px; border-radius: 8px;">Reset All</button>
            </div>

            <form id="config-form">
                <input type="hidden" name="date_col" value="{{ default_date_col }}">

                <!-- TIMELINE -->
                <div class="sidebar-section">
                    <h3 class="section-title">Timeline</h3>
                    {% if default_date_col %}
                    <div class="date-preset-grid">
                        <div class="date-preset-btn" onclick="setDateRange('today', this)">Today</div>
                        <div class="date-preset-btn" onclick="setDateRange('last7', this)">Last 7 Days</div>
                        <div class="date-preset-btn" onclick="setDateRange('last30', this)">Last 30 Days</div>
                        <div class="date-preset-btn" onclick="setDateRange('mtd', this)">Month-to-Date</div>
                        <div class="date-preset-btn" onclick="setDateRange('prev_month', this)">Prev Month</div>
                        <div class="date-preset-btn" onclick="setDateRange('ytd', this)">Year-to-Date</div>
                    </div>
                    
                    <div style="display: flex; gap: 8px;">
                        <div style="flex:1;">
                            <label class="form-label">FROM</label>
                            <input type="date" name="start_date" id="start_date" class="form-input">
                        </div>
                        <div style="flex:1;">
                            <label class="form-label">TO</label>
                            <input type="date" name="end_date" id="end_date" class="form-input">
                        </div>
                    </div>
                    {% endif %}
                </div>

                <!-- DATA FILTERS -->
                <div class="sidebar-section">
                    <h3 class="section-title">Filters</h3>
                    
                    {% if spc_list %}
                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">SPC NAME</label>
                            <div>
                                <button type="button" class="btn-micro" onclick="selectAll('spc_filters', true)">All</button>
                                <button type="button" class="btn-micro" onclick="selectAll('spc_filters', false)">Clear</button>
                            </div>
                        </div>
                        <div class="checkbox-group" id="spc-container">
                            {% for spc in spc_list %}
                            <label class="checkbox-item" data-val="{{ spc }}"><input type="checkbox" name="spc_filters" value="{{ spc }}" onchange="handleCascade()"> <span style="overflow:hidden; text-overflow:ellipsis;">{{ spc }}</span></label>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}

                    {% if seg1_list %}
                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">SEG 1</label>
                            <div>
                                <button type="button" class="btn-micro" onclick="selectAll('seg1_filters', true)">All</button>
                                <button type="button" class="btn-micro" onclick="selectAll('seg1_filters', false)">Clear</button>
                            </div>
                        </div>
                        <div class="checkbox-group" id="seg-container">
                            {% for seg in seg1_list %}
                            <label class="checkbox-item" data-val="{{ seg }}"><input type="checkbox" name="seg1_filters" value="{{ seg }}" onchange="handleCascade()"> <span style="overflow:hidden; text-overflow:ellipsis;">{{ seg }}</span></label>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}

                    {% if family_list %}
                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">FAMILY NAME</label>
                            <div>
                                <button type="button" class="btn-micro" onclick="selectAll('family_filters', true)">All</button>
                                <button type="button" class="btn-micro" onclick="selectAll('family_filters', false)">Clear</button>
                            </div>
                        </div>
                        <div class="checkbox-group" id="fam-container">
                            {% for fam in family_list %}
                            <label class="checkbox-item" data-val="{{ fam }}"><input type="checkbox" name="family_filters" value="{{ fam }}"> <span style="overflow:hidden; text-overflow:ellipsis;">{{ fam }}</span></label>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}
                </div>

                <!-- TABLE STRUCTURE -->
                <div class="sidebar-section" id="sidebar-structure">
                    <h3 class="section-title">Structure</h3>

                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">ROW GROUPING</label>
                            <div>
                                <button type="button" class="btn-micro" onclick="selectAll('index_cols', true)">All</button>
                                <button type="button" class="btn-micro" onclick="selectAll('index_cols', false)">Clear</button>
                            </div>
                        </div>
                        <div class="checkbox-group" id="row-grouping-container" style="max-height: none;">
                            {% for col in grouping_cols %}
                            <label class="checkbox-item">
                                <input type="checkbox" name="index_cols" value="{{ col }}"> 
                                <span style="overflow: hidden; text-overflow: ellipsis;">{{ col }}</span>
                            </label>
                            {% endfor %}
                        </div>
                    </div>
                </div>

                <!-- METRICS -->
                <div class="sidebar-section" id="sidebar-metrics">
                    <h3 class="section-title">Metrics</h3>
                    <div class="form-group">
                        <div class="checkbox-group" style="max-height: none;">
                            <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="sum"> Sum Total</label>
                            <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="count"> Count (Quantity)</label>
                            <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="mean"> Average Price</label>
                            <div style="border-top: 1px solid rgba(0,0,0,0.06); margin: 6px 0;"></div>
                            <label class="checkbox-item" title="% of Column Total"><input type="checkbox" name="agg_funcs" value="contrib"> Contribution %</label>
                            <label class="checkbox-item" title="Period-over-Period Growth"><input type="checkbox" name="agg_funcs" value="growth"> Growth % (PoP)</label>
                            <div style="border-top: 1px solid rgba(0,0,0,0.06); margin: 6px 0;"></div>
                            <label class="checkbox-item"><input type="checkbox" name="show_row_total" value="true" checked> <b>Show Grand Totals</b></label>
                        </div>
                    </div>
                </div>

            </form>
            <div style="text-align: center; margin: 24px 0;">
                <a href="/upload" style="color: #ff3b30; font-size: 13px; text-decoration: none; font-weight: 600; background: rgba(255,59,48,0.1); padding: 10px 20px; border-radius: 980px;">← Upload New File</a>
            </div>
        </div>
        
        <div class="sidebar-resizer" id="sidebarResizer"></div>

        <div class="main-content">
            <div class="header-actions">
                <div style="display: flex; align-items: center; gap: 20px; flex-wrap: wrap;">
                    <h2 style="font-size: 28px; font-weight: 700; margin: 0; letter-spacing: -0.015em;">Executive Dashboard</h2>
                    
                    <!-- Seamless View Toggle -->
                    <div class="btn-segmented" style="width: max-content;">
                        <input type="radio" id="view_dash" name="view_mode_toggle" value="dashboard" checked onchange="updateDashboard()">
                        <label for="view_dash">Pivot View</label>
                        
                        <input type="radio" id="view_raw" name="view_mode_toggle" value="raw" onchange="updateDashboard()">
                        <label for="view_raw">Raw Data</label>
                    </div>
                </div>
                
                <div class="dropdown" id="exportDropdownContainer">
                    <button onclick="toggleExportMenu()" class="btn-primary">Export ▾</button>
                    <div id="exportDropdown" class="dropdown-content">
                        <button onclick="exportImage(); toggleExportMenu();" class="dropdown-item">🖼️ Save Image</button>
                        <a href="/download" download="Executive_Report.xlsx" class="dropdown-item" onclick="toggleExportMenu();">📊 Download Excel</a>
                    </div>
                </div>
            </div>
            
            <!-- KPI RIBBON -->
            <div id="kpi-banner" class="kpi-ribbon" style="display:none;"></div>
            
            <div id="capture-area" class="table-container">
                <div id="table-wrapper" class="table-scroll">
                    <div style="padding: 100px 20px; text-align: center;">
                        <p style="color: #86868b; font-size: 15px; font-weight: 500;">Select at least one <b>Row</b> and one <b>Metric</b> from the sidebar to compile intelligence.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Injecting Data Map for Cascading Filters -->
    <script>
        const filterMap = {{ filter_mapping_json|safe }};
    </script>

    <script>
        // Sidebar Resizer Logic
        const resizer = document.getElementById('sidebarResizer');
        const sidebar = document.getElementById('appSidebar');
        let isResizing = false;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            resizer.classList.add('resizing');
            document.body.style.cursor = 'col-resize';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            if(e.clientX > 200 && e.clientX < 600) {
                sidebar.style.width = e.clientX + 'px';
            }
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                resizer.classList.remove('resizing');
                document.body.style.cursor = 'default';
            }
        });
        
        // Date Presets Logic
        function setDateRange(range, btnElement) {
            document.querySelectorAll('.date-preset-btn').forEach(btn => btn.classList.remove('active'));
            if(btnElement) btnElement.classList.add('active');
            
            const today = new Date();
            let start = new Date();
            let end = new Date();
            
            if (range === 'today') {
                // start and end stay as today
            } else if (range === 'last7') {
                start.setDate(today.getDate() - 6);
            } else if (range === 'last30') {
                start.setDate(today.getDate() - 29);
            } else if (range === 'mtd') {
                start = new Date(today.getFullYear(), today.getMonth(), 1);
            } else if (range === 'prev_month') {
                start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
                end = new Date(today.getFullYear(), today.getMonth(), 0);
            } else if (range === 'ytd') {
                start = new Date(today.getFullYear(), 0, 1);
            }
            
            start.setMinutes(start.getMinutes() - start.getTimezoneOffset());
            end.setMinutes(end.getMinutes() - end.getTimezoneOffset());
            
            document.getElementById('start_date').value = start.toISOString().split('T')[0];
            document.getElementById('end_date').value = end.toISOString().split('T')[0];
            
            updateDashboard();
        }

        function selectAll(name, checked) {
            const checkboxes = document.querySelectorAll(`input[name="${name}"]`);
            checkboxes.forEach(cb => { cb.checked = checked; });
            if(['spc_filters', 'seg1_filters', 'family_filters'].includes(name)) {
                handleCascade();
            } else {
                updateDashboard();
            }
        }

        function clearAll() {
            document.getElementById('config-form').reset();
            document.querySelectorAll('.date-preset-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.checkbox-item').forEach(el => el.style.display = 'flex');
            
            document.getElementById('sidebar-structure').style.opacity = '1';
            document.getElementById('sidebar-structure').style.pointerEvents = 'auto';
            document.getElementById('sidebar-metrics').style.opacity = '1';
            document.getElementById('sidebar-metrics').style.pointerEvents = 'auto';
            document.getElementById('view_dash').checked = true;
            
            document.getElementById('table-wrapper').innerHTML = '<div style="padding: 100px 20px; text-align: center;"><p style="color: #86868b; font-size: 15px; font-weight: 500;">Select at least one <b>Row</b> and one <b>Metric</b> from the sidebar to compile intelligence.</p></div>';
            document.getElementById('kpi-banner').style.display = 'none';
        }

        function handleCascade() {
            const selectedSpcs = Array.from(document.querySelectorAll('input[name="spc_filters"]:checked')).map(cb => cb.value);
            const selectedSegs = Array.from(document.querySelectorAll('input[name="seg1_filters"]:checked')).map(cb => cb.value);
            
            let validSegs = new Set();
            let validFams = new Set();

            if (selectedSpcs.length === 0) {
                document.querySelectorAll('#seg-container .checkbox-item, #fam-container .checkbox-item').forEach(el => el.style.display = 'flex');
            } else {
                filterMap.forEach(row => {
                    if (selectedSpcs.includes(row.spc)) {
                        validSegs.add(row.seg);
                        if (selectedSegs.length === 0 || selectedSegs.includes(row.seg)) {
                            validFams.add(row.fam);
                        }
                    }
                });

                document.querySelectorAll('#seg-container .checkbox-item').forEach(el => {
                    if (validSegs.has(el.dataset.val)) el.style.display = 'flex';
                    else { el.style.display = 'none'; el.querySelector('input').checked = false; }
                });

                document.querySelectorAll('#fam-container .checkbox-item').forEach(el => {
                    if (validFams.has(el.dataset.val) || selectedSpcs.length === 0) el.style.display = 'flex';
                    else { el.style.display = 'none'; el.querySelector('input').checked = false; }
                });
            }
            updateDashboard();
        }

        async function updateDashboard() {
            const form = document.getElementById('config-form');
            const formData = new FormData(form);
            
            const viewMode = document.querySelector('input[name="view_mode_toggle"]:checked').value;
            formData.append('view_mode', viewMode);
            
            const indexCols = formData.getAll('index_cols');
            const aggFuncs = formData.getAll('agg_funcs');
            
            const structureSection = document.getElementById('sidebar-structure');
            const metricsSection = document.getElementById('sidebar-metrics');
            if (viewMode === 'raw') {
                structureSection.style.opacity = '0.3';
                structureSection.style.pointerEvents = 'none';
                metricsSection.style.opacity = '0.3';
                metricsSection.style.pointerEvents = 'none';
            } else {
                structureSection.style.opacity = '1';
                structureSection.style.pointerEvents = 'auto';
                metricsSection.style.opacity = '1';
                metricsSection.style.pointerEvents = 'auto';
            }
            
            if (viewMode === 'dashboard' && (indexCols.length === 0 || aggFuncs.length === 0)) {
                document.getElementById('table-wrapper').innerHTML = '<div style="padding: 100px 20px; text-align: center;"><p style="color: #86868b; font-size: 15px; font-weight: 500;">Select at least one <b>Row</b> and one <b>Metric</b> from the sidebar to compile intelligence.</p></div>';
                document.getElementById('kpi-banner').style.display = 'none';
                return;
            }

            try {
                const response = await fetch('/calculate', { method: 'POST', body: formData });
                const data = await response.json();
                
                if (response.ok) {
                    const kpiBanner = document.getElementById('kpi-banner');
                    if(data.kpi_html) {
                        kpiBanner.innerHTML = data.kpi_html;
                        kpiBanner.style.display = 'flex';
                    } else {
                        kpiBanner.style.display = 'none';
                    }
                    
                    let html = "";
                    if (data.filter_text) {
                        html += `<div class="filter-text-bar">${data.filter_text}</div>`;
                    }
                    html += data.table_html;
                    document.getElementById('table-wrapper').innerHTML = html;
                    makeTableResizable();
                } else {
                    document.getElementById('table-wrapper').innerHTML = `<div style="padding: 100px 20px; text-align: center;"><p style="color: #ff3b30; font-weight: 600;">${data.error}</p></div>`;
                    document.getElementById('kpi-banner').style.display = 'none';
                }
            } catch (err) {
                console.error("Failed to update", err);
            }
        }

        function makeTableResizable() {
            const table = document.querySelector('.excel-table');
            if (!table) return;
            const cols = table.querySelectorAll('th');
            cols.forEach((col) => {
                if (col.querySelector('.resizer')) return;
                const resizer = document.createElement('div');
                resizer.className = 'resizer';
                col.appendChild(resizer);
                let x = 0, w = 0;
                resizer.addEventListener('mousedown', function (e) {
                    x = e.clientX; w = col.offsetWidth;
                    document.addEventListener('mousemove', mouseMoveHandler);
                    document.addEventListener('mouseup', mouseUpHandler);
                    e.stopPropagation();
                });
                function mouseMoveHandler(e) { col.style.width = `${w + (e.clientX - x)}px`; }
                function mouseUpHandler() { document.removeEventListener('mousemove', mouseMoveHandler); document.removeEventListener('mouseup', mouseUpHandler); }
            });
        }

        document.querySelectorAll('#config-form input').forEach(el => {
            if(el.type !== 'date') {
                el.addEventListener('change', () => {
                    if (el.name !== 'start_date' && el.name !== 'end_date') {
                        updateDashboard();
                    }
                });
            }
        });
        
        document.querySelectorAll('#config-form input[type="date"]').forEach(el => {
            el.addEventListener('change', () => {
                document.querySelectorAll('.date-preset-btn').forEach(btn => btn.classList.remove('active'));
                updateDashboard();
            });
        });
        
        window.addEventListener('DOMContentLoaded', () => {
            const body = document.body;
            if (window.innerWidth <= 768) { body.classList.add('mobile-mode'); document.getElementById('viewToggleBtn').innerHTML = "📱 Mobile Site"; } 
            else { body.classList.add('desktop-mode'); document.getElementById('viewToggleBtn').innerHTML = "💻 Desktop Site"; }
            updateDashboard();
        });
        
        function exportImage() {
            const captureArea = document.querySelector('.main-content');
            const scrollArea = document.getElementById('table-wrapper');
            const exportBtn = document.getElementById('exportDropdownContainer');
            
            const origMaxHeight = scrollArea.style.maxHeight;
            const origOverflow = scrollArea.style.overflow;
            
            scrollArea.style.maxHeight = 'none';
            scrollArea.style.overflow = 'visible';
            exportBtn.style.display = 'none'; 
            
            document.body.classList.add('export-mode');
            
            setTimeout(() => {
                domtoimage.toJpeg(captureArea, { quality: 1.0, bgcolor: '#ffffff' })
                    .then(function (dataUrl) {
                        if (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)) {
                            const modal = document.createElement('div');
                            modal.style.position = 'fixed';
                            modal.style.top = '0'; modal.style.left = '0'; 
                            modal.style.width = '100%'; modal.style.height = '100%';
                            modal.style.backgroundColor = 'rgba(0,0,0,0.95)'; 
                            modal.style.zIndex = '99999';
                            modal.style.display = 'flex'; 
                            modal.style.flexDirection = 'column'; 
                            modal.style.alignItems = 'center'; 
                            modal.style.justifyContent = 'center';
                            
                            const closeBtn = document.createElement('button');
                            closeBtn.innerText = 'Close Preview';
                            closeBtn.style.padding = '12px 24px'; 
                            closeBtn.style.marginBottom = '20px'; 
                            closeBtn.style.borderRadius = '980px';
                            closeBtn.style.border = 'none';
                            closeBtn.style.backgroundColor = '#ffffff';
                            closeBtn.style.color = '#1d1d1f';
                            closeBtn.style.fontWeight = '600';
                            closeBtn.onclick = () => document.body.removeChild(modal);
                            
                            const inst = document.createElement('p');
                            inst.innerText = 'Long-press the image below to save it to your Photos.';
                            inst.style.color = '#ffffff'; 
                            inst.style.marginBottom = '20px';
                            inst.style.fontSize = '14px';
                            
                            const img = document.createElement('img');
                            img.src = dataUrl;
                            img.style.maxWidth = '90%'; 
                            img.style.maxHeight = '70%'; 
                            img.style.borderRadius = '12px';
                            img.style.boxShadow = '0 10px 30px rgba(0,0,0,0.5)';
                            
                            modal.appendChild(closeBtn);
                            modal.appendChild(inst);
                            modal.appendChild(img);
                            document.body.appendChild(modal);
                        } else {
                            let link = document.createElement('a');
                            link.download = 'Executive_Report.jpeg';
                            link.href = dataUrl;
                            link.click();
                        }
                        
                        scrollArea.style.maxHeight = origMaxHeight;
                        scrollArea.style.overflow = origOverflow;
                        exportBtn.style.display = 'inline-block';
                        document.body.classList.remove('export-mode');
                    })
                    .catch(function (error) {
                        console.error('Export failed:', error);
                        scrollArea.style.maxHeight = origMaxHeight;
                        scrollArea.style.overflow = origOverflow;
                        exportBtn.style.display = 'inline-block';
                        document.body.classList.remove('export-mode');
                        alert("Could not export image. Please check console logs.");
                    });
            }, 500);
        }
    </script>
</body>
</html>
"""

def load_data():
    if os.path.exists(DATA_FILE_PATH):
        try: return pd.read_pickle(DATA_FILE_PATH)
        except: return None
    return None

def save_data(df):
    df.to_pickle(DATA_FILE_PATH)
    meta = {"upload_time": datetime.now().strftime("%d %b %Y, %I:%M %p")}
    pd.to_pickle(meta, META_FILE_PATH)

def get_metadata():
    upload_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
    if os.path.exists(META_FILE_PATH):
        try:
            meta = pd.read_pickle(META_FILE_PATH)
            upload_time = meta.get("upload_time", upload_time)
        except: pass
    return upload_time

def get_filter_lists(df):
    spc_col = next((c for c in df.columns if 'spc' in str(c).lower() and 'name' in str(c).lower()), 'SPC Name' if 'SPC Name' in df.columns else '')
    seg1_col = next((c for c in df.columns if 'seg1' in str(c).lower()), 'SEG1' if 'SEG1' in df.columns else '')
    family_col = next((c for c in df.columns if 'family' in str(c).lower()), 'Family Name' if 'Family Name' in df.columns else '')
    
    spc_list = df[spc_col].dropna().unique().tolist() if spc_col and spc_col in df.columns else []
    seg1_list = df[seg1_col].dropna().unique().tolist() if seg1_col and seg1_col in df.columns else []
    family_list = df[family_col].dropna().unique().tolist() if family_col and family_col in df.columns else []
    
    mapping_df = df[[c for c in [spc_col, seg1_col, family_col] if c]].dropna(how='all').fillna('N/A').astype(str).drop_duplicates()
    mapping_df.columns = ['spc' if c == spc_col else 'seg' if c == seg1_col else 'fam' if c == family_col else c for c in mapping_df.columns]
    filter_mapping_json = json.dumps(mapping_df.to_dict(orient='records'))
    
    return sorted([str(x) for x in spc_list]), sorted([str(x) for x in seg1_list]), sorted([str(x) for x in family_list]), filter_mapping_json

def get_date_bounds(df, date_col):
    min_date, max_date = "N/A", "N/A"
    if date_col and date_col in df.columns:
        try:
            parsed = pd.to_datetime(df[date_col], errors='coerce', dayfirst=True)
            if pd.notna(parsed.min()): min_date = parsed.min().strftime("%d %b %y")
            if pd.notna(parsed.max()): max_date = parsed.max().strftime("%d %b %y")
        except: pass
    return min_date, max_date

def format_indian_number(x):
    if pd.isna(x) or x == '': return ''
    try:
        num = int(round(float(x)))
        s = str(abs(num))
        if len(s) > 3:
            res = s[-3:]
            s = s[:-3]
            while len(s) > 2:
                res = s[-2:] + ',' + res
                s = s[:-2]
            s = s + ',' + res
        return '-' + s if num < 0 else s
    except (ValueError, TypeError): return str(x)

# --- ROUTES ---
@app.route("/", methods=["GET", "POST"])
def home():
    df = load_data()
    if df is not None:
        all_cols = df.columns.tolist()
        default_date_col = 'Customized Sales Date' if 'Customized Sales Date' in all_cols else ('Sale Date' if 'Sale Date' in all_cols else next((c for c in all_cols if 'date' in str(c).lower()), ""))
        grouping_cols = df.select_dtypes(exclude=['number']).columns.tolist()
        spc_list, seg1_list, family_list, filter_mapping_json = get_filter_lists(df)
        upload_time = get_metadata()
        min_sale_date, max_sale_date = get_date_bounds(df, default_date_col)
        return render_template_string(WORKSPACE_HTML, all_cols=all_cols, grouping_cols=grouping_cols, default_date_col=default_date_col, spc_list=spc_list, seg1_list=seg1_list, family_list=family_list, upload_time=upload_time, min_sale_date=min_sale_date, max_sale_date=max_sale_date, filter_mapping_json=filter_mapping_json)
    return render_template_string(UPLOAD_HTML)

@app.route("/upload", methods=["GET"])
def upload_page():
    return render_template_string(UPLOAD_HTML)

@app.route("/dashboard", methods=["POST"])
def dashboard():
    if 'file' in request.files and request.files['file'].filename != '':
        file = request.files['file']
        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        save_data(df)
    return redirect(url_for('home'))

@app.route("/calculate", methods=["POST"])
def calculate():
    df = load_data()
    if df is None: return jsonify({"error": "No data available."}), 400
        
    view_mode = request.form.get('view_mode', 'dashboard')
    date_col = request.form.get('date_col')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    index_cols = request.form.getlist('index_cols')
    agg_funcs = request.form.getlist('agg_funcs')
    
    spc_filters = request.form.getlist('spc_filters')
    seg1_filters = request.form.getlist('seg1_filters')
    family_filters = request.form.getlist('family_filters')
    show_row_total = request.form.get('show_row_total') == 'true'
    
    num_cols = df.select_dtypes(include='number').columns.tolist()
    value_cols = ['Tentative DP'] if 'Tentative DP' in num_cols else (num_cols[:1] if num_cols else [])
    
    if view_mode == 'dashboard' and (not index_cols or not agg_funcs):
        return jsonify({"error": "Select at least one Row Grouping and one Metric."}), 400

    calc_contrib = 'contrib' in agg_funcs
    calc_growth = 'growth' in agg_funcs
    base_aggs = [f for f in agg_funcs if f in ['sum', 'count', 'mean']]
    if not base_aggs: base_aggs = ['sum']

    try:
        filter_texts = []
        df_filtered = df.copy()
        
        if date_col and date_col in df_filtered.columns:
            df_filtered[date_col] = pd.to_datetime(df_filtered[date_col], errors='coerce', dayfirst=True)
            if start_date: df_filtered = df_filtered[df_filtered[date_col] >= pd.to_datetime(start_date)]
            if end_date: df_filtered = df_filtered[df_filtered[date_col] <= pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
            if start_date or end_date:
                s_str = pd.to_datetime(start_date).strftime('%d-%b-%y') if start_date else 'Start'
                e_str = pd.to_datetime(end_date).strftime('%d-%b-%y') if end_date else 'End'
                filter_texts.append(f"<b>{date_col}</b>: {s_str} to {e_str}")

        spc_col = next((c for c in df_filtered.columns if 'spc' in str(c).lower() and 'name' in str(c).lower()), 'SPC Name' if 'SPC Name' in df_filtered.columns else '')
        if spc_col and spc_filters and spc_col in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[spc_col].astype(str).isin(spc_filters)]
            filter_texts.append(f"<b>SPC</b>: {', '.join(spc_filters)}")

        seg1_col = next((c for c in df_filtered.columns if 'seg1' in str(c).lower()), 'SEG1' if 'SEG1' in df_filtered.columns else '')
        if seg1_col and seg1_filters and seg1_col in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[seg1_col].astype(str).isin(seg1_filters)]
            filter_texts.append(f"<b>SEG1</b>: {', '.join(seg1_filters)}")

        family_col = next((c for c in df_filtered.columns if 'family' in str(c).lower()), 'Family Name' if 'Family Name' in df_filtered.columns else '')
        if family_col and family_filters and family_col in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[family_col].astype(str).isin(family_filters)]
            filter_texts.append(f"<b>Family</b>: {', '.join(family_filters)}")

        kpi_html = ""
        if not df_filtered.empty and value_cols:
            total_val = format_indian_number(df_filtered[value_cols[0]].sum())
            total_rows = format_indian_number(len(df_filtered))
            active_spcs = df_filtered[spc_col].nunique() if spc_col in df_filtered.columns else "N/A"
            kpi_html = f"""
                <div class="kpi-card"><div class="kpi-label">Total Volume</div><div class="kpi-val">{total_val}</div></div>
                <div class="kpi-card"><div class="kpi-label">Records</div><div class="kpi-val">{total_rows}</div></div>
                <div class="kpi-card"><div class="kpi-label">Active Entities</div><div class="kpi-val">{active_spcs}</div></div>
            """

        filter_text = f"<p style='color:#86868b; font-size:12px; margin:0;'>{' | '.join(filter_texts)}</p>" if filter_texts else ""

        if df_filtered.empty:
            return jsonify({"table_html": "<div style='padding: 60px 20px; text-align: center;'><p style='color: #ff3b30;'>No data found for the selected filters.</p></div>", "filter_text": filter_text, "kpi_html": ""})

        # RAW DATA VIEW HACK (No Limits)
        if view_mode == 'raw':
            for col in df_filtered.columns:
                if pd.api.types.is_datetime64_any_dtype(df_filtered[col]):
                    df_filtered[col] = df_filtered[col].dt.strftime('%d-%b-%y')
                elif pd.api.types.is_numeric_dtype(df_filtered[col]):
                    df_filtered[col] = df_filtered[col].apply(format_indian_number)
            
            df_filtered.to_pickle(os.path.join(UPLOAD_DIR, "summary_data.pkl"))
            table_html = df_filtered.to_html(classes='excel-table', border=0, index=False, justify='left', escape=False)
            table_html = table_html.replace('<td>', '<td class="number-cell">')
            return jsonify({"table_html": table_html, "filter_text": filter_text, "kpi_html": kpi_html})

        for col in index_cols:
            if col in df_filtered.columns and pd.api.types.is_datetime64_any_dtype(df_filtered[col]):
                df_filtered[col] = df_filtered[col].dt.strftime('%d-%b-%y')

        pivot_kwargs = {'data': df_filtered, 'index': index_cols, 'values': value_cols, 'aggfunc': base_aggs}
        pivot_df = pd.pivot_table(**pivot_kwargs).reset_index().fillna(0)
        
        new_cols = []
        agg_map = {'sum': 'Value', 'count': 'Qty', 'mean': 'Avg'}
        for col in pivot_df.columns:
            if isinstance(col, tuple):
                if col[0] in index_cols and all(x == '' for x in col[1:]):
                    new_cols.append(str(col[0]))
                    continue
                parts = []
                for item in col:
                    item_str = str(item).strip()
                    if item_str in agg_map:
                        if len(base_aggs) > 1: parts.append(agg_map[item_str])
                    elif item_str in value_cols:
                        if len(value_cols) > 1: parts.append(item_str)
                    elif item_str and item_str.lower() != 'nan':
                        parts.append(item_str)
                new_cols.append(" - ".join(parts) if parts else " - ".join(str(c) for c in col if str(c).strip()))
            else:
                if col in index_cols:
                    new_cols.append(str(col))
                else:
                    col_str = str(col)
                    new_cols.append(col_str.replace('sum - ', '').replace('count - ', '').replace('mean - ', ''))
        
        pivot_df.columns = [str(c) for c in new_cols]

        metric_columns = [col for col in pivot_df.columns if col not in index_cols]
        contrib_data = {}
        if calc_contrib:
            for c in metric_columns:
                total = pivot_df[c].sum()
                contrib_data[f"{c} Contrib %"] = (pivot_df[c] / total * 100).fillna(0) if total else 0
                
        growth_data = {}
        if calc_growth and len(metric_columns) > 1:
            for i in range(1, len(metric_columns)):
                prev = metric_columns[i-1]
                curr = metric_columns[i]
                growth_data[f"{curr} Growth %"] = ((pivot_df[curr] - pivot_df[prev]) / pivot_df[prev].replace(0, pd.NA) * 100).fillna(0)

        final_cols = index_cols.copy()
        for i, c in enumerate(metric_columns):
            final_cols.append(c)
            if calc_contrib: 
                pivot_df[f"{c} Contrib %"] = contrib_data[f"{c} Contrib %"]
                final_cols.append(f"{c} Contrib %")
            if calc_growth and i > 0:
                pivot_df[f"{c} Growth %"] = growth_data[f"{c} Growth %"]
                final_cols.append(f"{c} Growth %")
        
        if show_row_total and len(metric_columns) > 1:
            pivot_df['TOTAL'] = pivot_df[metric_columns].sum(axis=1)
            final_cols.append('TOTAL')
            metric_columns.append('TOTAL')
            
        pivot_df = pivot_df[final_cols]
            
        if not pivot_df.empty:
            total_row = pd.DataFrame([{c: '' for c in pivot_df.columns}])
            total_row.iloc[0, 0] = 'GRAND TOTAL'
            for c in metric_columns:
                total_row.at[0, c] = pivot_df[c].sum()
            pivot_df = pd.concat([pivot_df, total_row], ignore_index=True)
            
        pivot_df.to_pickle(os.path.join(UPLOAD_DIR, "summary_data.pkl"))
        
        def format_pct(x):
            if pd.isna(x) or x == '': return ''
            try:
                val = float(x)
                if val > 0: return f'<span class="pct-positive">↑ {val:.1f}%</span>'
                elif val < 0: return f'<span class="pct-negative">↓ {abs(val):.1f}%</span>'
                return f'<span class="pct-neutral">-</span>'
            except: return str(x)
                
        for c in pivot_df.columns:
            if c not in index_cols:
                if 'Contrib %' in c or 'Growth %' in c:
                    pivot_df[c] = pivot_df[c].apply(format_pct)
                else:
                    pivot_df[c] = pivot_df[c].apply(format_indian_number)
        
        table_html = pivot_df.to_html(classes='excel-table', border=0, index=False, justify='left', escape=False)
        table_html = table_html.replace('<th>TOTAL</th>', '<th class="total-col-header">TOTAL</th>')
        table_html = table_html.replace('<td>', '<td class="number-cell">')

        return jsonify({"table_html": table_html, "filter_text": filter_text, "kpi_html": kpi_html})
        
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route("/download", methods=["GET"])
def download():
    summary_path = os.path.join(UPLOAD_DIR, "summary_data.pkl")
    if not os.path.exists(summary_path): return "No data to download", 400
    df = pd.read_pickle(summary_path)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dashboard_Report')
    output.seek(0)
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", download_name="Executive_Report.xlsx", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
