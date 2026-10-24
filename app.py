import os
import io
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, send_file, jsonify
import pandas as pd
import numpy as np

app = Flask(__name__)

# Persistent file storage path for cloud deployments
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
    }
    
    body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg-main); margin: 0; padding: 0; color: var(--text-primary); -webkit-font-smoothing: antialiased; }
    
    .nav { background: rgba(255, 255, 255, 0.85); backdrop-filter: saturate(200%) blur(30px); border-bottom: 1px solid rgba(0, 0, 0, 0.08); padding: 0 16px; height: 56px; display: flex; justify-content: space-between; align-items: center; font-size: 15px; font-weight: 600; color: var(--text-primary); position: fixed; top: 0; width: 100%; box-sizing: border-box; z-index: 1000; }
    .view-toggle { background: rgba(0,0,0,0.04); padding: 6px 12px; border-radius: 980px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; transition: 0.2s; border: none; color: var(--text-primary); flex-shrink: 0; }
    .view-toggle:hover { background: rgba(0,0,0,0.08); }
    
    .upload-container { max-width: 520px; margin: 130px auto 40px auto; padding: 0 16px; box-sizing: border-box; }
    .title { font-size: 36px; font-weight: 700; letter-spacing: -0.015em; text-align: center; margin: 0 0 8px 0; }
    .subtitle { font-size: 17px; font-weight: 400; text-align: center; color: var(--text-secondary); margin: 0 0 32px 0; }
    
    .card { background: var(--glass-bg); backdrop-filter: blur(25px) saturate(180%); border-radius: 24px; padding: 24px; box-shadow: var(--shadow-glass); border: 1px solid var(--glass-border); box-sizing: border-box; }
    
    /* Clean Accordion Sidebar Styles */
    .sidebar-section { background: rgba(255,255,255,0.6); border: 1px solid rgba(0,0,0,0.06); border-radius: 14px; margin-bottom: 12px; padding: 0 12px; transition: background 0.2s; }
    .sidebar-section[open] { padding-bottom: 12px; background: rgba(255,255,255,0.85); box-shadow: 0 2px 8px rgba(0,0,0,0.02); }
    .section-title { font-size: 13px; font-weight: 600; color: var(--text-primary); padding: 12px 0; cursor: pointer; display: flex; justify-content: space-between; align-items: center; list-style: none; user-select: none; }
    .section-title::-webkit-details-marker { display: none; }
    .section-title i { font-style: normal; margin-right: 6px; font-size: 14px; }
    .section-title .indicator { font-size: 10px; color: var(--text-secondary); transition: transform 0.2s; }
    .sidebar-section[open] .section-title .indicator { transform: rotate(180deg); }
    
    .section-clear { background: rgba(0,113,227,0.1); border: none; color: var(--blue-apple); font-size: 10px; font-weight: 600; cursor: pointer; padding: 4px 8px; border-radius: 6px; margin-left: auto; margin-right: 10px; transition: 0.2s; text-transform: uppercase; }
    .section-clear:hover { background: rgba(0,113,227,0.2); }

    .form-input { width: 100%; padding: 10px 12px; font-size: 13px; border: 1px solid rgba(0,0,0,0.1); border-radius: 10px; background-color: rgba(255,255,255,0.9); color: var(--text-primary); box-sizing: border-box; transition: all 0.2s ease; margin-bottom: 8px; }
    .form-input:focus { border-color: var(--blue-apple); outline: none; box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.15); }
    
    .checkbox-group { background: rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.05); border-radius: 10px; padding: 8px; max-height: 140px; overflow-y: auto; }
    .checkbox-item { display: flex; align-items: center; margin-bottom: 4px; font-size: 12px; cursor: pointer; padding: 4px 8px; border-radius: 6px; transition: background 0.15s; }
    .checkbox-item:hover { background: rgba(0,0,0,0.04); }
    .checkbox-item:last-child { margin-bottom: 0; }
    .checkbox-item input { margin-right: 8px; width: 14px; height: 14px; accent-color: var(--blue-apple); cursor: pointer; flex-shrink: 0; }
    
    .btn-primary { background-color: var(--blue-apple); color: white; border: none; border-radius: 980px; padding: 12px 20px; font-size: 14px; font-weight: 500; cursor: pointer; text-align: center; display: inline-flex; align-items: center; justify-content: center; text-decoration: none; box-sizing: border-box; transition: background 0.2s, transform 0.1s; }
    .btn-primary:hover { background-color: var(--blue-hover); }
    .btn-secondary { background-color: rgba(0,0,0,0.05); color: var(--text-primary); border-radius: 980px; padding: 6px 10px; font-size: 11px; font-weight: 500; text-decoration: none; display: inline-block; cursor: pointer; border: 1px solid rgba(0,0,0,0.04); transition: 0.2s; margin: 2px; }
    .btn-secondary:hover { background-color: rgba(0,0,0,0.09); }
    
    /* Export Dropdown */
    .dropdown { position: relative; display: inline-block; }
    .dropdown-content { display: none; position: absolute; right: 0; background-color: rgba(255,255,255,0.95); backdrop-filter: blur(30px); min-width: 170px; box-shadow: 0 15px 35px rgba(0,0,0,0.12); border-radius: 16px; border: 1px solid rgba(255,255,255,0.8); z-index: 2000; overflow: hidden; margin-top: 8px; }
    .dropdown-content.show { display: block; animation: fadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
    .dropdown-item { color: var(--text-primary); padding: 12px 16px; text-decoration: none; display: block; font-size: 13px; font-weight: 500; cursor: pointer; border: none; background: none; width: 100%; text-align: left; transition: background 0.2s; box-sizing: border-box; }
    .dropdown-item:hover { background-color: rgba(0,113,227,0.08); color: var(--blue-apple); }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }

    .table-container { background: var(--glass-bg); backdrop-filter: blur(25px); border-radius: 20px; box-shadow: var(--shadow-glass); border: 1px solid var(--glass-border); overflow: hidden; width: 100%; box-sizing: border-box; display: flex; flex-direction: column; }
    .table-scroll { max-height: calc(100vh - 200px); overflow-y: auto; overflow-x: auto; -webkit-overflow-scrolling: touch; position: relative; }
    .excel-table { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; font-size: 13px; background: transparent; word-wrap: break-word; min-width: 550px; }
    .excel-table th, .excel-table td { padding: 12px 14px; text-align: left; border-bottom: 1px solid rgba(0,0,0,0.06); overflow: hidden; text-overflow: ellipsis; position: relative; }
    
    /* Highlighted Table Headers & Resizer */
    .excel-table th { background-color: rgba(0, 113, 227, 0.08); color: var(--blue-apple); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; position: sticky; top: 0; z-index: 100; border-bottom: 2px solid rgba(0, 113, 227, 0.2); user-select: none; }
    .resizer { position: absolute; right: 0; top: 0; bottom: 0; width: 6px; cursor: col-resize; z-index: 101; }
    .resizer:hover { background-color: rgba(0, 113, 227, 0.4); }

    .excel-table td { white-space: nowrap; }
    .excel-table tr:hover td { background-color: rgba(0, 113, 227, 0.03); }
    
    /* Highlight Side Total and Row Totals */
    .excel-table th.total-col-header, .excel-table td.total-col-cell { background-color: rgba(0, 113, 227, 0.04); font-weight: 600; border-left: 1px solid rgba(0, 113, 227, 0.1); }
    .excel-table tbody tr:last-child td { font-weight: 700; background-color: rgba(0, 113, 227, 0.12); color: var(--blue-apple); border-top: 2px solid var(--blue-apple); border-bottom: none; box-shadow: inset 0 1px 0 rgba(255,255,255,0.6); }
    
    .number-cell { font-variant-numeric: tabular-nums; }
    .pct-positive { color: #34c759; font-weight: 600; }
    .pct-negative { color: #ff3b30; font-weight: 600; }
    .pct-neutral { color: var(--text-secondary); }
    
    .drag-handle { cursor: grab; color: #aeaeb2; margin-right: 6px; font-weight: bold; user-select: none; }
    .drag-handle:active { cursor: grabbing; }

    /* Responsive Layout Engine */
    body.desktop-mode { overflow: auto; }
    body.desktop-mode .app-layout { display: flex; flex-direction: row; min-height: 100vh; padding-top: 56px; box-sizing: border-box; }
    body.desktop-mode .sidebar { width: 340px; background: var(--glass-sidebar); backdrop-filter: blur(40px) saturate(180%); border-right: 1px solid rgba(0,0,0,0.08); padding: 20px 14px; overflow-y: auto; flex-shrink: 0; box-sizing: border-box; height: calc(100vh - 56px); position: sticky; top: 56px; }
    body.desktop-mode .main-content { flex: 1; padding: 20px 24px; overflow-x: auto; background: var(--bg-main); box-sizing: border-box; min-width: 0; }
    body.desktop-mode .header-actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }
    
    body.mobile-mode { overflow: auto; }
    body.mobile-mode .app-layout { display: flex; flex-direction: column; padding-top: 56px; box-sizing: border-box; }
    body.mobile-mode .sidebar { width: 100%; background: var(--glass-sidebar); border-right: none; border-bottom: 1px solid rgba(0,0,0,0.08); padding: 16px; box-sizing: border-box; }
    body.mobile-mode .main-content { width: 100%; padding: 16px; box-sizing: border-box; background: var(--bg-main); }
    body.mobile-mode .header-actions { display: flex; flex-direction: column; align-items: stretch; gap: 12px; margin-bottom: 16px; }
    body.mobile-mode .header-actions .dropdown { width: 100%; }
    body.mobile-mode .header-actions .btn-primary { width: 100%; justify-content: center; }
    
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.2); border-radius: 10px; }
</style>

<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Sortable/1.15.0/Sortable.min.js"></script>
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
                var openDropdown = dropdowns[i];
                if (openDropdown.classList.contains('show')) {
                    openDropdown.classList.remove('show');
                }
            }
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

            let x = 0;
            let w = 0;

            resizer.addEventListener('mousedown', function (e) {
                x = e.clientX;
                w = col.offsetWidth;
                document.addEventListener('mousemove', mouseMoveHandler);
                document.addEventListener('mouseup', mouseUpHandler);
                e.stopPropagation();
            });

            function mouseMoveHandler(e) {
                const dx = e.clientX - x;
                col.style.width = `${w + dx}px`;
            }

            function mouseUpHandler() {
                document.removeEventListener('mousemove', mouseMoveHandler);
                document.removeEventListener('mouseup', mouseUpHandler);
            }
        });
    }

    function toggleWeekSelector(show) {
        const container = document.getElementById('week-selector-container');
        if (container) {
            container.style.display = show ? 'block' : 'none';
        }
    }

    function selectAllColumns(source) {
        const checkboxes = document.querySelectorAll('.col-visibility-cb');
        checkboxes.forEach(cb => {
            cb.checked = source.checked;
        });
        filterSidebarColumns();
    }

    window.addEventListener('DOMContentLoaded', () => {
        const body = document.body;
        const btn = document.getElementById('viewToggleBtn');
        if (window.innerWidth <= 768) {
            body.classList.add('mobile-mode');
            if(btn) btn.innerHTML = "📱 Mobile Site";
        } else {
            body.classList.add('desktop-mode');
            if(btn) btn.innerHTML = "💻 Desktop Site";
        }

        const sortableLists = document.querySelectorAll('.sortable-list');
        sortableLists.forEach(el => {
            new Sortable(el, {
                animation: 150,
                handle: '.drag-handle',
                onUpdate: function () {
                    updateDashboard();
                }
            });
        });
    });
</script>
"""

UPLOAD_HTML = """
<!DOCTYPE html>
<html>
<head><title>Data Portal - Liquid Glass</title><meta name="viewport" content="width=device-width, initial-scale=1.0">""" + GLOBAL_HEAD + """</head>
<body style="background: #f2f2f7;">
    <div class="nav">
        <div>Analytics Pro</div>
        <button class="view-toggle" onclick="toggleViewMode()" id="viewToggleBtn">💻 Desktop Site</button>
    </div>
    <div class="upload-container">
        <h1 class="title">Real-Time Insights.</h1>
        <p class="subtitle">Upload your data to launch the Liquid Glass workspace.</p>
        <div class="card">
            <form action="/dashboard" method="post" enctype="multipart/form-data">
                <div class="form-group">
                    <input type="file" name="file" accept=".xlsx, .xls, .csv" required class="form-input" style="border: 2px dashed rgba(0,0,0,0.15); background: rgba(255,255,255,0.5); padding: 20px; text-align: center; cursor: pointer;">
                </div>
                <button type="submit" class="btn-primary" style="width: 100%; padding: 14px;">Enter Workspace →</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

WORKSPACE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Interactive Workspace</title><meta name="viewport" content="width=device-width, initial-scale=1.0">""" + GLOBAL_HEAD + """</head>
<body>
    <div class="nav">
        <div>Analytics Pro</div>
        <button class="view-toggle" onclick="toggleViewMode()" id="viewToggleBtn">💻 Desktop Site</button>
    </div>
    
    <div class="app-layout">
        <div class="sidebar">
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 0 4px;">
                <h2 style="font-size: 16px; font-weight: 700; margin: 0;">Workspace</h2>
                <button type="button" onclick="clearAll()" style="background: none; border: none; color: var(--blue-apple); font-size: 12px; font-weight: 600; cursor: pointer; padding: 0;">Reset All</button>
            </div>
            
            <div style="background: rgba(255,255,255,0.6); padding: 10px 12px; border-radius: 12px; margin-bottom: 16px; font-size: 11px; color: var(--text-secondary); border: 1px solid rgba(0,0,0,0.04);">
                <div style="margin-bottom: 4px;"><b>Data Synced:</b> {{ upload_time }}</div>
                <div style="color: var(--blue-apple); font-weight: 600;">{{ min_sale_date }} → {{ max_sale_date }}</div>
            </div>

            <form id="config-form">
                <input type="hidden" name="date_col" value="{{ default_date_col }}">

                <!-- 1. TIME FRAME -->
                <details class="sidebar-section" open>
                    <summary class="section-title">
                        <div><i>📅</i> Date & Time</div>
                        <div style="display: flex; align-items: center;">
                            <button type="button" class="section-clear" onclick="event.preventDefault(); clearSection('date')">Clear</button>
                            <span class="indicator">▼</span>
                        </div>
                    </summary>
                    {% if default_date_col %}
                    <div style="display: flex; gap: 4px; margin-bottom: 10px; flex-wrap: wrap;">
                        <button type="button" class="btn-secondary" onclick="setDateRange('today'); toggleWeekSelector(false);">Today</button>
                        <button type="button" class="btn-secondary" onclick="setDateRange('week'); toggleWeekSelector(true);">Week</button>
                        <button type="button" class="btn-secondary" onclick="setDateRange('month'); toggleWeekSelector(false);">Month</button>
                    </div>
                    
                    <div id="week-selector-container" style="display: none; margin-bottom: 10px; background: rgba(0,113,227,0.05); padding: 8px; border-radius: 10px;">
                        <label style="font-size:11px; font-weight: 600; color: var(--blue-apple); display:block; margin-bottom: 6px;">Select Week:</label>
                        <div style="display: flex; gap: 6px;">
                            <label style="font-size:11px; cursor:pointer;"><input type="radio" name="week_num" value="1" onchange="updateDashboard()"> W1</label>
                            <label style="font-size:11px; cursor:pointer;"><input type="radio" name="week_num" value="2" onchange="updateDashboard()"> W2</label>
                            <label style="font-size:11px; cursor:pointer;"><input type="radio" name="week_num" value="3" onchange="updateDashboard()"> W3</label>
                            <label style="font-size:11px; cursor:pointer;"><input type="radio" name="week_num" value="4" onchange="updateDashboard()"> W4</label>
                        </div>
                    </div>

                    <div style="display: flex; gap: 8px;">
                        <div style="flex:1;">
                            <label style="font-size:10px; color:#86868b; margin-bottom:4px; display:block; font-weight: 600;">START DATE</label>
                            <input type="date" name="start_date" id="start_date" class="form-input" onchange="toggleWeekSelector(false);">
                        </div>
                        <div style="flex:1;">
                            <label style="font-size:10px; color:#86868b; margin-bottom:4px; display:block; font-weight: 600;">END DATE</label>
                            <input type="date" name="end_date" id="end_date" class="form-input" onchange="toggleWeekSelector(false);">
                        </div>
                    </div>
                    {% endif %}
                </details>

                <!-- 2. DATA FILTERS -->
                <details class="sidebar-section">
                    <summary class="section-title">
                        <div><i>🔍</i> Data Filters</div>
                        <div style="display: flex; align-items: center;">
                            <button type="button" class="section-clear" onclick="event.preventDefault(); clearSection('filters')">Clear</button>
                            <span class="indicator">▼</span>
                        </div>
                    </summary>
                    
                    {% if status_col %}
                    <div style="margin-bottom: 12px;">
                        <label style="font-size:11px; font-weight: 600; margin-bottom:4px; display:block;">STATUS</label>
                        <div class="checkbox-group">
                            {% for status in unique_statuses %}
                            <label class="checkbox-item"><input type="checkbox" name="status_filters" value="{{ status }}" {% if status|string|lower == 'ok' %}checked{% endif %}> <span style="overflow:hidden; text-overflow:ellipsis;">{{ status }}</span></label>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}

                    {% if spc_list %}
                    <div style="margin-bottom: 12px;">
                        <label style="font-size:11px; font-weight: 600; margin-bottom:4px; display:block;">SPC NAME</label>
                        <div class="checkbox-group">
                            {% for spc in spc_list %}
                            <label class="checkbox-item"><input type="checkbox" name="spc_filters" value="{{ spc }}"> <span style="overflow:hidden; text-overflow:ellipsis;">{{ spc }}</span></label>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}

                    {% if seg1_list %}
                    <div style="margin-bottom: 12px;">
                        <label style="font-size:11px; font-weight: 600; margin-bottom:4px; display:block;">SEG 1</label>
                        <div class="checkbox-group">
                            {% for seg in seg1_list %}
                            <label class="checkbox-item"><input type="checkbox" name="seg1_filters" value="{{ seg }}"> <span style="overflow:hidden; text-overflow:ellipsis;">{{ seg }}</span></label>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}

                    {% if family_list %}
                    <div style="margin-bottom: 6px;">
                        <label style="font-size:11px; font-weight: 600; margin-bottom:4px; display:block;">FAMILY NAME</label>
                        <div class="checkbox-group">
                            {% for fam in family_list %}
                            <label class="checkbox-item"><input type="checkbox" name="family_filters" value="{{ fam }}"> <span style="overflow:hidden; text-overflow:ellipsis;">{{ fam }}</span></label>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}
                </details>

                <!-- 3. GROUPING & LAYOUT -->
                <details class="sidebar-section" open>
                    <summary class="section-title">
                        <div><i>📊</i> Grouping & Layout</div>
                        <div style="display: flex; align-items: center;">
                            <button type="button" class="section-clear" onclick="event.preventDefault(); clearSection('layout')">Clear</button>
                            <span class="indicator">▼</span>
                        </div>
                    </summary>

                    <!-- Sidebar Configuration -->
                    <div style="background: rgba(0,113,227,0.03); padding: 10px; border-radius: 10px; border: 1px dashed rgba(0,113,227,0.2); margin-bottom: 12px;">
                        <label style="font-size:11px; font-weight: 600; color: var(--blue-apple); display: flex; justify-content: space-between; cursor: pointer;" onclick="document.getElementById('column-visibility-box').style.display = document.getElementById('column-visibility-box').style.display === 'none' ? 'block' : 'none';">
                            <span>Manage Visible Fields</span> <span>+/-</span>
                        </label>
                        <div id="column-visibility-box" style="display: none; margin-top: 8px;">
                            <div style="margin-bottom: 6px; border-bottom: 1px solid rgba(0,0,0,0.06); padding-bottom: 4px;">
                                <label style="font-size: 11px; font-weight: 600; cursor: pointer;"><input type="checkbox" id="select-all-cols" onclick="selectAllColumns(this)" checked> Select All</label>
                            </div>
                            <div style="max-height: 120px; overflow-y: auto;" class="checkbox-group">
                                {% for col in all_cols %}
                                <label class="checkbox-item"><input type="checkbox" class="col-visibility-cb" value="{{ col }}" checked onchange="filterSidebarColumns()"> {{ col }}</label>
                                {% endfor %}
                            </div>
                        </div>
                    </div>

                    <!-- SPC Compare -->
                    <div style="background: rgba(52,199,89,0.04); padding: 10px; border-radius: 10px; border: 1px solid rgba(52,199,89,0.15); margin-bottom: 12px;">
                        <label style="font-size:11px; font-weight: 600; color: #248a3d; margin-bottom:6px; display:block;">SPC COMPARISON</label>
                        <div style="display: flex; gap: 8px;">
                            <label style="font-size: 11px; cursor: pointer;"><input type="radio" name="spc_compare" value="none" checked onchange="updateDashboard()"> Off</label>
                            <label style="font-size: 11px; cursor: pointer;"><input type="radio" name="spc_compare" value="day" onchange="updateDashboard()"> Daily</label>
                            <label style="font-size: 11px; cursor: pointer;"><input type="radio" name="spc_compare" value="week" onchange="updateDashboard()"> Weekly</label>
                        </div>
                    </div>

                    <div style="margin-bottom: 12px;">
                        <label style="font-size:11px; font-weight: 600; margin-bottom:4px; display:block;">ROWS (DRAG ☰)</label>
                        <div class="checkbox-group sortable-list" id="row-grouping-container">
                            {% for col in all_cols %}
                            <div class="checkbox-item" data-col-name="{{ col }}">
                                <span class="drag-handle">☰</span>
                                <input type="checkbox" name="index_cols" value="{{ col }}" {% if col == 'Customized Sales Date' or col == 'SPC Name' %}checked{% endif %}> 
                                <span style="overflow: hidden; text-overflow: ellipsis;">{{ col }}</span>
                            </div>
                            {% endfor %}
                        </div>
                    </div>

                    <div style="margin-bottom: 6px;">
                        <label style="font-size:11px; font-weight: 600; margin-bottom:4px; display:block;">COLUMNS (DRAG ☰)</label>
                        <div class="checkbox-group sortable-list" id="col-grouping-container">
                            {% for col in all_cols %}
                            <div class="checkbox-item" data-col-name="{{ col }}">
                                <span class="drag-handle">☰</span>
                                <input type="checkbox" name="columns_cols" value="{{ col }}"> 
                                <span style="overflow: hidden; text-overflow: ellipsis;">{{ col }}</span>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                </details>

                <!-- 4. METRICS & OPTIONS -->
                <details class="sidebar-section" open>
                    <summary class="section-title">
                        <div><i>⚙️</i> Metrics & Settings</div>
                        <div style="display: flex; align-items: center;">
                            <button type="button" class="section-clear" onclick="event.preventDefault(); clearSection('metrics')">Clear</button>
                            <span class="indicator">▼</span>
                        </div>
                    </summary>

                    <div style="margin-bottom: 12px;">
                        <label style="font-size:11px; font-weight: 600; margin-bottom:4px; display:block;">CALCULATION TYPE</label>
                        <div class="checkbox-group" style="max-height: none;">
                            <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="sum" checked> Sum (Value)</label>
                            <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="count"> Count (Qty)</label>
                            <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="mean"> Average</label>
                            <div style="border-top: 1px solid rgba(0,0,0,0.06); margin: 4px 0;"></div>
                            <label class="checkbox-item" title="% of Column Total"><input type="checkbox" name="agg_funcs" value="contrib"> Contrib % (of Col)</label>
                            <label class="checkbox-item" title="Period-over-Period Growth"><input type="checkbox" name="agg_funcs" value="growth"> Growth % (PoP)</label>
                        </div>
                    </div>

                    <div style="margin-bottom: 6px;">
                        <label style="font-size:11px; font-weight: 600; margin-bottom:4px; display:block;">TABLE OPTIONS</label>
                        <div class="checkbox-group" style="max-height: none;">
                            <label class="checkbox-item"><input type="checkbox" name="show_row_total" value="true" checked> Show Grand Totals</label>
                        </div>
                    </div>
                </details>

            </form>
            <div style="text-align: center; margin-top: 24px; margin-bottom: 24px;">
                <a href="/" style="color: #ff3b30; font-size: 13px; text-decoration: none; font-weight: 600; background: rgba(255,59,48,0.1); padding: 10px 20px; border-radius: 980px;">← New File</a>
            </div>
        </div>

        <div class="main-content">
            <div class="header-actions">
                <h2 style="font-size: 26px; font-weight: 700; margin: 0; letter-spacing: -0.015em;">Live Dashboard</h2>
                <div class="dropdown">
                    <button onclick="toggleExportMenu()" class="btn-primary">Export ▾</button>
                    <div id="exportDropdown" class="dropdown-content">
                        <button onclick="exportImage(); toggleExportMenu();" class="dropdown-item">🖼️ Save Image</button>
                        <a href="/download" download="Dynamic_Dashboard_Report.xlsx" class="dropdown-item" onclick="toggleExportMenu();">📊 Download Excel</a>
                    </div>
                </div>
            </div>
            
            <div id="capture-area" class="table-container">
                <div id="table-wrapper" class="table-scroll">
                    <div style="padding: 60px 20px; text-align: center;">
                        <p style="color: #86868b; font-size: 15px;">Configure your parameters on the left to see the data instantly.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function clearAll() {
            document.getElementById('config-form').reset();
            document.getElementById('start_date').value = '';
            document.getElementById('end_date').value = '';
            toggleWeekSelector(false);
            updateDashboard();
        }

        function clearSection(section) {
            if (section === 'date') {
                document.getElementById('start_date').value = '';
                document.getElementById('end_date').value = '';
                toggleWeekSelector(false);
                document.querySelectorAll('input[name="week_num"]').forEach(r => r.checked = false);
            } else if (section === 'filters') {
                document.querySelectorAll('input[name="status_filters"], input[name="spc_filters"], input[name="seg1_filters"], input[name="family_filters"]').forEach(cb => cb.checked = false);
            } else if (section === 'layout') {
                document.querySelectorAll('input[name="index_cols"], input[name="columns_cols"]').forEach(cb => cb.checked = false);
                document.querySelectorAll('input[name="spc_compare"][value="none"]').forEach(r => r.checked = true);
            } else if (section === 'metrics') {
                document.querySelectorAll('input[name="agg_funcs"], input[name="show_row_total"]').forEach(cb => cb.checked = false);
            }
            updateDashboard();
        }

        function filterSidebarColumns() {
            const visibleCols = Array.from(document.querySelectorAll('.col-visibility-cb'))
                                      .filter(cb => cb.checked)
                                      .map(cb => cb.value);

            ['row-grouping-container', 'col-grouping-container'].forEach(containerId => {
                const container = document.getElementById(containerId);
                if (!container) return;
                const items = container.querySelectorAll('.checkbox-item');
                items.forEach(item => {
                    const colName = item.getAttribute('data-col-name');
                    if (visibleCols.includes(colName)) {
                        item.style.display = 'flex';
                    } else {
                        item.style.display = 'none';
                        const cb = item.querySelector('input[type="checkbox"]');
                        if (cb && cb.checked) {
                            cb.checked = false;
                            updateDashboard();
                        }
                    }
                });
            });
        }

        function setDateRange(range) {
            const today = new Date();
            let start = new Date();
            let end = new Date();
            if (range === 'today') {
            } else if (range === 'week') {
                const day = today.getDay() || 7; 
                if(day !== 1) start.setHours(-24 * (day - 1));
                end = new Date(start);
                end.setDate(end.getDate() + 6);
            } else if (range === 'month') {
                start = new Date(today.getFullYear(), today.getMonth(), 1);
                end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
            }
            start.setMinutes(start.getMinutes() - start.getTimezoneOffset());
            end.setMinutes(end.getMinutes() - end.getTimezoneOffset());
            document.getElementById('start_date').value = start.toISOString().split('T')[0];
            document.getElementById('end_date').value = end.toISOString().split('T')[0];
            updateDashboard();
        }

        async function updateDashboard() {
            const form = document.getElementById('config-form');
            const formData = new FormData(form);
            
            const indexCols = formData.getAll('index_cols');
            const aggFuncs = formData.getAll('agg_funcs');
            
            if (indexCols.length === 0 || aggFuncs.length === 0) {
                document.getElementById('table-wrapper').innerHTML = '<div style="padding: 60px 20px; text-align: center;"><p style="color: #86868b; font-size: 15px;">Select at least one Row and one Metric.</p></div>';
                return;
            }

            try {
                const response = await fetch('/calculate', { method: 'POST', body: formData });
                const data = await response.json();
                
                if (response.ok) {
                    let html = "";
                    if (data.filter_text) {
                        html += `<div style="padding: 12px 16px; border-bottom: 1px solid rgba(0,0,0,0.06); background: rgba(255,255,255,0.5);">${data.filter_text}</div>`;
                    }
                    html += data.table_html;
                    document.getElementById('table-wrapper').innerHTML = html;
                    makeTableResizable();
                } else {
                    document.getElementById('table-wrapper').innerHTML = `<div style="padding: 60px 20px; text-align: center;"><p style="color: #ff3b30;">${data.error}</p></div>`;
                }
            } catch (err) {
                console.error("Failed to update", err);
            }
        }

        document.querySelectorAll('#config-form input').forEach(el => {
            if(!el.classList.contains('col-visibility-cb') && el.type !== 'date') {
                el.addEventListener('change', updateDashboard);
            }
        });
        document.querySelectorAll('#config-form input[type="date"]').forEach(el => {
            el.addEventListener('blur', updateDashboard);
        });

        window.onload = function() {
            updateDashboard();
        };

        function exportImage() {
            const captureArea = document.getElementById('capture-area');
            const scrollArea = document.getElementById('table-wrapper');
            
            const origMaxHeight = scrollArea.style.maxHeight;
            const origOverflowX = scrollArea.style.overflowX;
            const origWidth = captureArea.style.width;
            const origOverflow = captureArea.style.overflow;
            
            scrollArea.style.maxHeight = 'none';
            scrollArea.style.overflowX = 'visible';
            captureArea.style.width = scrollArea.scrollWidth + 'px';
            captureArea.style.overflow = 'visible';
            
            setTimeout(() => {
                html2canvas(captureArea, { scale: 2, backgroundColor: '#f2f2f7' }).then(canvas => {
                    const imgData = canvas.toDataURL('image/jpeg', 1.0);
                    
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
                        
                        const img = document.createElement('img');
                        img.src = imgData;
                        img.style.maxWidth = '90%'; 
                        img.style.maxHeight = '70%'; 
                        img.style.borderRadius = '12px';
                        img.style.boxShadow = '0 10px 30px rgba(0,0,0,0.5)';
                        
                        modal.appendChild(closeBtn);
                        modal.appendChild(img);
                        document.body.appendChild(modal);
                    } else {
                        let link = document.createElement('a');
                        link.download = 'Dashboard_Export.jpeg';
                        link.href = imgData;
                        link.click();
                    }
                    
                    scrollArea.style.maxHeight = origMaxHeight;
                    scrollArea.style.overflowX = origOverflowX;
                    captureArea.style.width = origWidth;
                    captureArea.style.overflow = origOverflow;
                });
            }, 150);
        }
    </script>
</body>
</html>
"""

def load_data():
    if os.path.exists(DATA_FILE_PATH):
        try:
            return pd.read_pickle(DATA_FILE_PATH)
        except Exception:
            return None
    return None

def save_data(df):
    df.to_pickle(DATA_FILE_PATH)
    meta = {
        "upload_time": datetime.now().strftime("%d %b %Y, %I:%M %p")
    }
    pd.to_pickle(meta, META_FILE_PATH)

def get_metadata():
    upload_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
    if os.path.exists(META_FILE_PATH):
        try:
            meta = pd.read_pickle(META_FILE_PATH)
            upload_time = meta.get("upload_time", upload_time)
        except Exception:
            pass
    return upload_time

def get_filter_lists(df):
    spc_col = next((c for c in df.columns if 'spc' in str(c).lower() and 'name' in str(c).lower()), 'SPC Name' if 'SPC Name' in df.columns else '')
    seg1_col = next((c for c in df.columns if 'seg1' in str(c).lower()), 'SEG1' if 'SEG1' in df.columns else '')
    family_col = next((c for c in df.columns if 'family' in str(c).lower()), 'Family Name' if 'Family Name' in df.columns else '')
    
    spc_list = df[spc_col].dropna().unique().tolist() if spc_col and spc_col in df.columns else []
    seg1_list = df[seg1_col].dropna().unique().tolist() if seg1_col and seg1_col in df.columns else []
    family_list = df[family_col].dropna().unique().tolist() if family_col and family_col in df.columns else []
    
    return sorted([str(x) for x in spc_list]), sorted([str(x) for x in seg1_list]), sorted([str(x) for x in family_list])

@app.route("/", methods=["GET", "POST"])
def home():
    df = load_data()
    if df is not None:
        all_cols = df.columns.tolist()
        default_date_col = 'Customized Sales Date' if 'Customized Sales Date' in all_cols else ('Sale Date' if 'Sale Date' in all_cols else next((c for c in all_cols if 'date' in str(c).lower()), ""))
        status_col = ""
        for candidate in ['FinalStatus', 'Final Record Status', 'Validation Remarks']:
            if candidate in all_cols:
                status_col = candidate
                break
        unique_statuses = df[status_col].dropna().unique().tolist() if status_col else []
        spc_list, seg1_list, family_list = get_filter_lists(df)
        upload_time = get_metadata()
        
        min_sale_date = "N/A"
        max_sale_date = "N/A"
        if default_date_col and default_date_col in df.columns:
            try:
                parsed = pd.to_datetime(df[default_date_col], errors='coerce', dayfirst=True)
                if pd.notna(parsed.min()): min_sale_date = parsed.min().strftime("%d %b %y")
                if pd.notna(parsed.max()): max_sale_date = parsed.max().strftime("%d %b %y")
            except: pass

        return render_template_string(WORKSPACE_HTML, all_cols=all_cols, default_date_col=default_date_col, status_col=status_col, unique_statuses=unique_statuses, spc_list=spc_list, seg1_list=seg1_list, family_list=family_list, upload_time=upload_time, min_sale_date=min_sale_date, max_sale_date=max_sale_date)
    return render_template_string(UPLOAD_HTML)

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if 'file' in request.files and request.files['file'].filename != '':
        file = request.files['file']
        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        save_data(df)
    return home()

@app.route("/calculate", methods=["GET", "POST"])
def calculate():
    df = load_data()
    if df is None: return jsonify({"error": "No data available. Please upload a file."}), 400
        
    date_col = request.form.get('date_col')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    week_num = request.form.get('week_num')
    spc_compare = request.form.get('spc_compare', 'none')
    index_cols = request.form.getlist('index_cols')
    columns_cols = request.form.getlist('columns_cols')
    agg_funcs = request.form.getlist('agg_funcs')
    
    status_filters = request.form.getlist('status_filters')
    spc_filters = request.form.getlist('spc_filters')
    seg1_filters = request.form.getlist('seg1_filters')
    family_filters = request.form.getlist('family_filters')
    show_row_total = request.form.get('show_row_total') == 'true'
    
    num_cols = df.select_dtypes(include='number').columns.tolist()
    value_cols = ['Tentative DP'] if 'Tentative DP' in num_cols else (num_cols[:1] if num_cols else [])
    
    if not index_cols or not value_cols or not agg_funcs:
        return jsonify({"error": "Missing parameters or numeric column."}), 400

    calc_contrib = 'contrib' in agg_funcs
    calc_growth = 'growth' in agg_funcs
    base_aggs = [f for f in agg_funcs if f in ['sum', 'count', 'mean']]
    if not base_aggs: 
        base_aggs = ['sum']

    try:
        filter_texts = []
        df_filtered = df.copy()
        
        # 1. Date & Week Filters
        if date_col and date_col in df_filtered.columns:
            df_filtered[date_col] = pd.to_datetime(df_filtered[date_col], errors='coerce', dayfirst=True)
            if week_num and week_num.isdigit():
                w_idx = int(week_num)
                valid_dates = df_filtered[date_col].dropna()
                if not valid_dates.empty:
                    base_date = pd.to_datetime(start_date) if start_date else valid_dates.min()
                    month_start = datetime(base_date.year, base_date.month, 1)
                    if w_idx == 1: w_start, w_end = month_start, datetime(base_date.year, base_date.month, 7, 23, 59, 59)
                    elif w_idx == 2: w_start, w_end = datetime(base_date.year, base_date.month, 8), datetime(base_date.year, base_date.month, 14, 23, 59, 59)
                    elif w_idx == 3: w_start, w_end = datetime(base_date.year, base_date.month, 15), datetime(base_date.year, base_date.month, 21, 23, 59, 59)
                    else:
                        w_start = datetime(base_date.year, base_date.month, 22)
                        nm = datetime(base_date.year, base_date.month + 1, 1) if base_date.month < 12 else datetime(base_date.year + 1, 1, 1)
                        w_end = nm - timedelta(seconds=1)
                    df_filtered = df_filtered[(df_filtered[date_col] >= w_start) & (df_filtered[date_col] <= w_end)]
                    filter_texts.append(f"<b>{date_col}</b>: Week {w_idx} ({w_start.strftime('%d-%b-%y')} to {w_end.strftime('%d-%b-%y')})")
            else:
                if start_date: df_filtered = df_filtered[df_filtered[date_col] >= pd.to_datetime(start_date)]
                if end_date: df_filtered = df_filtered[df_filtered[date_col] <= pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
                if start_date or end_date:
                    s_str = pd.to_datetime(start_date).strftime('%d-%b-%y') if start_date else 'Start'
                    e_str = pd.to_datetime(end_date).strftime('%d-%b-%y') if end_date else 'End'
                    filter_texts.append(f"<b>{date_col}</b>: {s_str} to {e_str}")

        # 2. Checkbox Filters
        status_col = next((c for c in ['FinalStatus', 'Final Record Status', 'Validation Remarks'] if c in df_filtered.columns), "")
        if status_col and status_filters:
            df_filtered = df_filtered[df_filtered[status_col].isin(status_filters)]
            filter_texts.append(f"<b>{status_col}</b>: {', '.join(status_filters)}")

        spc_col = next((c for c in df_filtered.columns if 'spc' in str(c).lower() and 'name' in str(c).lower()), 'SPC Name' if 'SPC Name' in df_filtered.columns else '')
        if spc_col and spc_filters and spc_col in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[spc_col].astype(str).isin(spc_filters)]
            filter_texts.append(f"<b>SPC Name</b>: {', '.join(spc_filters)}")

        seg1_col = next((c for c in df_filtered.columns if 'seg1' in str(c).lower()), 'SEG1' if 'SEG1' in df_filtered.columns else '')
        if seg1_col and seg1_filters and seg1_col in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[seg1_col].astype(str).isin(seg1_filters)]
            filter_texts.append(f"<b>SEG1</b>: {', '.join(seg1_filters)}")

        family_col = next((c for c in df_filtered.columns if 'family' in str(c).lower()), 'Family Name' if 'Family Name' in df_filtered.columns else '')
        if family_col and family_filters and family_col in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[family_col].astype(str).isin(family_filters)]
            filter_texts.append(f"<b>Family Name</b>: {', '.join(family_filters)}")

        # 3. SPC Comparison Injection
        if spc_compare in ['day', 'week'] and spc_col and date_col:
            if spc_compare == 'day':
                df_filtered['_Day'] = df_filtered[date_col].dt.strftime('%d-%b-%y')
                if spc_col not in index_cols: index_cols = [spc_col]
                if '_Day' not in columns_cols: columns_cols = ['_Day']
            elif spc_compare == 'week':
                def gw(dt):
                    if pd.isna(dt): return 'Unknown'
                    w = (dt.day - 1) // 7 + 1
                    return f"W{w} ({dt.strftime('%b')})"
                df_filtered['_Week'] = df_filtered[date_col].apply(gw)
                if spc_col not in index_cols: index_cols = [spc_col]
                if '_Week' not in columns_cols: columns_cols = ['_Week']
            filter_texts.append(f"<b>Compare</b>: {spc_compare.capitalize()}-wise")

        filter_text = f"<p style='color:#86868b; font-size:12px; margin:0;'>{' | '.join(filter_texts)}</p>" if filter_texts else ""

        if df_filtered.empty:
            return jsonify({"table_html": "<div style='padding: 60px 20px; text-align: center;'><p style='color: #ff3b30;'>No data found for the selected filters.</p></div>", "filter_text": filter_text})

        for col in index_cols:
            if col in df_filtered.columns and pd.api.types.is_datetime64_any_dtype(df_filtered[col]):
                df_filtered[col] = df_filtered[col].dt.strftime('%d-%b-%y')

        # 4. Generate Pivot
        pivot_kwargs = {'data': df_filtered, 'index': index_cols, 'values': value_cols, 'aggfunc': base_aggs}
        if columns_cols: pivot_kwargs['columns'] = columns_cols
        pivot_df = pd.pivot_table(**pivot_kwargs).reset_index().fillna(0)
        
        # Flatten Headers
        new_cols = []
        agg_map = {'sum': 'Value', 'count': 'Qty', 'mean': 'Avg'}
        for col in pivot_df.columns:
            if isinstance(col, tuple):
                parts = []
                for item in col:
                    item_str = str(item).strip()
                    if item_str in agg_map:
                        if len(base_aggs) > 1: parts.append(agg_map[item_str])
                    elif item_str in value_cols:
                        if len(value_cols) > 1: parts.append(item_str)
                    elif item_str and item_str.lower() != 'nan':
                        try: parts.append(pd.to_datetime(item_str, errors='raise').strftime('%d-%b-%y'))
                        except Exception: parts.append(item_str)
                new_cols.append(" - ".join(parts) if parts else " - ".join(str(c) for c in col if str(c).strip()))
            else:
                try: new_cols.append(pd.to_datetime(str(col), errors='raise').strftime('%d-%b-%y'))
                except Exception: new_cols.append(str(col).replace('sum - ', '').replace('count - ', '').replace('mean - ', ''))
        pivot_df.columns = new_cols

        # 5. Calculate Advanced Metrics (Contrib % and Growth %)
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

        # Merge them sequentially
        final_cols = index_cols.copy()
        for i, c in enumerate(metric_columns):
            final_cols.append(c)
            if calc_contrib: 
                pivot_df[f"{c} Contrib %"] = contrib_data[f"{c} Contrib %"]
                final_cols.append(f"{c} Contrib %")
            if calc_growth and i > 0:
                pivot_df[f"{c} Growth %"] = growth_data[f"{c} Growth %"]
                final_cols.append(f"{c} Growth %")
        
        # 6. Row Totals
        if show_row_total:
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
        
        # 7. Formatter (Number & Percentages)
        def format_metric(x, is_pct=False):
            if pd.isna(x) or x == '': return ''
            try:
                if is_pct:
                    val = float(x)
                    if val > 0: return f'<span class="pct-positive">+{val:.1f}%</span>'
                    elif val < 0: return f'<span class="pct-negative">{val:.1f}%</span>'
                    return f'<span class="pct-neutral">0.0%</span>'
                else:
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
                
        for c in pivot_df.columns:
            if c not in index_cols:
                is_pct = 'Contrib %' in c or 'Growth %' in c
                pivot_df[c] = pivot_df[c].apply(lambda x: format_metric(x, is_pct))
        
        table_html = pivot_df.to_html(classes='excel-table', border=0, index=False, justify='left', escape=False)
        table_html = table_html.replace('<th>TOTAL</th>', '<th class="total-col-header">TOTAL</th>')
        table_html = table_html.replace('<td>', '<td class="number-cell">')

        return jsonify({"table_html": table_html, "filter_text": filter_text})
        
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
    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", download_name="Dynamic_Dashboard_Report.xlsx", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
