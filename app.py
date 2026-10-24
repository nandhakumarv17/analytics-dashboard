import os
import io
import json
import random
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, send_file, jsonify, session, redirect, url_for
import pandas as pd
import numpy as np

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'liquid_glass_super_secret_key_2026')

# --- AUTHENTICATION MIDDLEWARE ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

UPLOAD_DIR = "/tmp/dashboard_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATA_FILE_PATH = os.path.join(UPLOAD_DIR, "shared_data.pkl")
META_FILE_PATH = os.path.join(UPLOAD_DIR, "metadata.pkl")

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
    
    .nav { background: rgba(255, 255, 255, 0.85); backdrop-filter: saturate(200%) blur(30px); border-bottom: 1px solid rgba(0, 0, 0, 0.08); padding: 0 24px; height: 60px; display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: 600; color: var(--text-primary); position: fixed; top: 0; width: 100%; box-sizing: border-box; z-index: 1000; }
    .view-toggle { background: rgba(0,0,0,0.04); padding: 8px 14px; border-radius: 980px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; transition: 0.2s; border: none; color: var(--text-primary); flex-shrink: 0; }
    .view-toggle:hover { background: rgba(0,0,0,0.08); }
    .logout-btn { color: var(--text-secondary); text-decoration: none; font-size: 13px; font-weight: 500; margin-left: 16px; transition: 0.2s; }
    .logout-btn:hover { color: #ff3b30; }
    
    .upload-container { max-width: 520px; margin: 130px auto 40px auto; padding: 0 16px; box-sizing: border-box; }
    .title { font-size: 36px; font-weight: 700; letter-spacing: -0.015em; text-align: center; margin: 0 0 8px 0; }
    .subtitle { font-size: 17px; font-weight: 400; text-align: center; color: var(--text-secondary); margin: 0 0 32px 0; }
    .card { background: var(--glass-bg); backdrop-filter: blur(25px) saturate(180%); border-radius: 24px; padding: 32px; box-shadow: var(--shadow-glass); border: 1px solid var(--glass-border); box-sizing: border-box; }
    
    .step-card { background: rgba(255,255,255,0.7); border: 1px solid rgba(0,0,0,0.06); border-radius: 16px; margin-bottom: 16px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.02); }
    .step-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid rgba(0,0,0,0.05); padding-bottom: 8px; }
    .step-title { font-size: 14px; font-weight: 700; color: var(--text-primary); margin: 0; display: flex; align-items: center; }
    
    .form-group { margin-bottom: 16px; }
    .form-group:last-child { margin-bottom: 0; }
    .form-label-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .form-label { font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; margin: 0; }
    
    .btn-micro { background: rgba(0,0,0,0.04); border: none; color: var(--blue-apple); font-size: 10px; font-weight: 600; cursor: pointer; padding: 4px 8px; border-radius: 6px; transition: 0.2s; }
    .btn-micro:hover { background: rgba(0,113,227,0.1); }
    
    .form-input { width: 100%; padding: 10px 12px; font-size: 13px; border: 1px solid rgba(0,0,0,0.1); border-radius: 10px; background-color: rgba(255,255,255,0.9); color: var(--text-primary); box-sizing: border-box; transition: all 0.2s ease; margin-bottom: 8px; }
    .form-input:focus { border-color: var(--blue-apple); outline: none; box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.15); }
    
    .checkbox-group { background: rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.05); border-radius: 10px; padding: 8px; max-height: 140px; overflow-y: auto; }
    .checkbox-item { display: flex; align-items: center; margin-bottom: 4px; font-size: 12px; cursor: pointer; padding: 4px 8px; border-radius: 6px; transition: background 0.15s; }
    .checkbox-item:hover { background: rgba(0,0,0,0.04); }
    .checkbox-item:last-child { margin-bottom: 0; }
    .checkbox-item input { margin-right: 8px; width: 14px; height: 14px; accent-color: var(--blue-apple); cursor: pointer; flex-shrink: 0; }
    
    .btn-primary { background-color: var(--blue-apple); color: white; border: none; border-radius: 980px; padding: 12px 20px; font-size: 14px; font-weight: 500; cursor: pointer; text-align: center; display: inline-flex; align-items: center; justify-content: center; text-decoration: none; box-sizing: border-box; transition: background 0.2s, transform 0.1s; width: 100%; }
    .btn-primary:hover { background-color: var(--blue-hover); }
    
    .btn-segmented { display: flex; background: rgba(0,0,0,0.04); border-radius: 8px; padding: 2px; gap: 2px; }
    .btn-segmented label { flex: 1; text-align: center; font-size: 11px; font-weight: 500; padding: 6px 0; border-radius: 6px; cursor: pointer; color: var(--text-secondary); transition: 0.2s; }
    .btn-segmented input { display: none; }
    .btn-segmented input:checked + label { background: #ffffff; color: var(--text-primary); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    
    .dropdown { position: relative; display: inline-block; }
    .dropdown-content { display: none; position: absolute; right: 0; background-color: rgba(255,255,255,0.95); backdrop-filter: blur(30px); min-width: 170px; box-shadow: 0 15px 35px rgba(0,0,0,0.12); border-radius: 16px; border: 1px solid rgba(255,255,255,0.8); z-index: 2000; overflow: hidden; margin-top: 8px; }
    .dropdown-content.show { display: block; animation: fadeIn 0.2s ease; }
    .dropdown-item { color: var(--text-primary); padding: 12px 16px; text-decoration: none; display: block; font-size: 13px; font-weight: 500; cursor: pointer; border: none; background: none; width: 100%; text-align: left; transition: background 0.2s; }
    .dropdown-item:hover { background-color: rgba(0,113,227,0.08); color: var(--blue-apple); }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }

    .table-container { background: var(--glass-bg); backdrop-filter: blur(25px); border-radius: 20px; box-shadow: var(--shadow-glass); border: 1px solid var(--glass-border); overflow: hidden; width: 100%; box-sizing: border-box; display: flex; flex-direction: column; }
    .table-scroll { max-height: calc(100vh - 200px); overflow-y: auto; overflow-x: auto; -webkit-overflow-scrolling: touch; position: relative; }
    .excel-table { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; font-size: 13px; background: transparent; word-wrap: break-word; min-width: 550px; }
    .excel-table th, .excel-table td { padding: 14px 16px; text-align: left; border-bottom: 1px solid rgba(0,0,0,0.06); overflow: hidden; text-overflow: ellipsis; position: relative; }
    
    .excel-table th { background-color: rgba(0, 113, 227, 0.08); color: var(--blue-apple); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; position: sticky; top: 0; z-index: 100; border-bottom: 2px solid rgba(0, 113, 227, 0.2); user-select: none; }
    .resizer { position: absolute; right: 0; top: 0; bottom: 0; width: 6px; cursor: col-resize; z-index: 101; }
    .resizer:hover { background-color: rgba(0, 113, 227, 0.4); }

    .excel-table td { white-space: nowrap; }
    .excel-table tr:hover td { background-color: rgba(0, 113, 227, 0.03); }
    .excel-table th.total-col-header, .excel-table td.total-col-cell { background-color: rgba(0, 113, 227, 0.04); font-weight: 600; border-left: 1px solid rgba(0, 113, 227, 0.1); }
    .excel-table tbody tr:last-child td { font-weight: 700; background-color: rgba(0, 113, 227, 0.12); color: var(--blue-apple); border-top: 2px solid var(--blue-apple); border-bottom: none; box-shadow: inset 0 1px 0 rgba(255,255,255,0.6); }
    
    .number-cell { font-variant-numeric: tabular-nums; }
    .pct-positive { color: #34c759; font-weight: 600; }
    .pct-negative { color: #ff3b30; font-weight: 600; }
    .pct-neutral { color: var(--text-secondary); }
    
    .drag-handle { cursor: grab; color: #aeaeb2; margin-right: 8px; font-weight: bold; user-select: none; font-size: 14px; }
    .drag-handle:active { cursor: grabbing; }

    body.desktop-mode { overflow: auto; }
    body.desktop-mode .app-layout { display: flex; flex-direction: row; min-height: 100vh; padding-top: 60px; box-sizing: border-box; }
    body.desktop-mode .sidebar { width: 360px; background: var(--glass-sidebar); backdrop-filter: blur(40px) saturate(180%); border-right: 1px solid rgba(0,0,0,0.08); padding: 24px 20px; overflow-y: auto; flex-shrink: 0; box-sizing: border-box; height: calc(100vh - 60px); position: sticky; top: 60px; }
    body.desktop-mode .main-content { flex: 1; padding: 24px 32px; overflow-x: auto; background: var(--bg-main); box-sizing: border-box; min-width: 0; }
    body.desktop-mode .header-actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px; }
    
    body.mobile-mode { overflow: auto; }
    body.mobile-mode .app-layout { display: flex; flex-direction: column; padding-top: 60px; box-sizing: border-box; }
    body.mobile-mode .sidebar { width: 100%; background: var(--glass-sidebar); border-right: none; border-bottom: 1px solid rgba(0,0,0,0.08); padding: 20px; box-sizing: border-box; }
    body.mobile-mode .main-content { width: 100%; padding: 20px; box-sizing: border-box; background: var(--bg-main); }
    body.mobile-mode .header-actions { display: flex; flex-direction: column; align-items: stretch; gap: 12px; margin-bottom: 20px; }
    body.mobile-mode .header-actions .dropdown { width: 100%; }
    
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
                if (dropdowns[i].classList.contains('show')) dropdowns[i].classList.remove('show');
            }
        }
    }
</script>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>Login - Analytics Pro</title><meta name="viewport" content="width=device-width, initial-scale=1.0">""" + GLOBAL_HEAD + """</head>
<body>
    <div class="nav">
        <div>Analytics Pro</div>
    </div>
    <div class="upload-container">
        <h1 class="title">Secure Access.</h1>
        <p class="subtitle">Enter your email or phone to receive a One-Time Password.</p>
        <div class="card">
            <form action="/login" method="post">
                <div class="form-group">
                    <label class="form-label" style="margin-bottom: 8px;">Email or Phone Number</label>
                    <input type="text" name="user_id" required class="form-input" placeholder="e.g. user@brand.com">
                </div>
                <button type="submit" class="btn-primary">Send OTP</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

VERIFY_HTML = """
<!DOCTYPE html>
<html>
<head><title>Verify OTP - Analytics Pro</title><meta name="viewport" content="width=device-width, initial-scale=1.0">""" + GLOBAL_HEAD + """</head>
<body>
    <div class="nav">
        <div>Analytics Pro</div>
    </div>
    <div class="upload-container">
        <h1 class="title">Verify Identity.</h1>
        <p class="subtitle">Enter the 6-digit code sent to your device.</p>
        <div class="card">
            {% if error %}
            <div style="background: rgba(255,59,48,0.1); color: #ff3b30; padding: 12px; border-radius: 12px; margin-bottom: 16px; font-size: 13px; font-weight: 600; text-align: center;">{{ error }}</div>
            {% endif %}
            <form action="/verify" method="post">
                <div class="form-group">
                    <label class="form-label" style="margin-bottom: 8px;">Secure OTP</label>
                    <input type="text" name="otp" required class="form-input" placeholder="● ● ● ● ● ●" maxlength="6" style="text-align: center; font-size: 20px; letter-spacing: 4px;">
                </div>
                <button type="submit" class="btn-primary">Authenticate</button>
            </form>
        </div>
    </div>
</body>
</html>
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
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
    </div>
    <div class="upload-container">
        <h1 class="title">Real-Time Insights.</h1>
        <p class="subtitle">Upload your data to launch the workspace.</p>
        <div class="card">
            <form action="/dashboard" method="post" enctype="multipart/form-data">
                <div class="form-group">
                    <input type="file" name="file" accept=".xlsx, .xls, .csv" required class="form-input" style="border: 2px dashed rgba(0,0,0,0.15); background: rgba(255,255,255,0.5); padding: 20px; text-align: center; cursor: pointer;">
                </div>
                <button type="submit" class="btn-primary">Enter Workspace →</button>
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
        <div style="display: flex; align-items: center;">
            <button class="view-toggle" onclick="toggleViewMode()" id="viewToggleBtn">💻 Desktop Site</button>
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
    </div>
    
    <div class="app-layout">
        <div class="sidebar">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 0 4px;">
                <h2 style="font-size: 20px; font-weight: 700; margin: 0;">Workspace</h2>
                <button type="button" onclick="clearAll()" style="background: none; border: none; color: var(--blue-apple); font-size: 13px; font-weight: 600; cursor: pointer; padding: 0;">Reset All</button>
            </div>

            <form id="config-form">
                <input type="hidden" name="date_col" value="{{ default_date_col }}">

                <!-- STEP 1: FILTER DATA -->
                <div class="step-card">
                    <div class="step-header">
                        <h3 class="step-title">1. Filter Data</h3>
                    </div>
                    
                    {% if default_date_col %}
                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">DATE RANGE</label>
                        </div>
                        <div class="btn-segmented" style="margin-bottom: 12px;">
                            <input type="radio" id="dr_today" name="dr_preset" onclick="setDateRange('today')">
                            <label for="dr_today">Today</label>
                            
                            <input type="radio" id="dr_week" name="dr_preset" onclick="setDateRange('week')">
                            <label for="dr_week">Week</label>
                            
                            <input type="radio" id="dr_month" name="dr_preset" onclick="setDateRange('month')">
                            <label for="dr_month">Month</label>
                            
                            <input type="radio" id="dr_custom" name="dr_preset" checked>
                            <label for="dr_custom">Custom</label>
                        </div>
                        
                        <div style="display: flex; gap: 8px; margin-bottom: 12px;">
                            <div style="flex:1;">
                                <label style="font-size:10px; color:#86868b; margin-bottom:4px; display:block; font-weight:600;">FROM</label>
                                <input type="date" name="start_date" id="start_date" class="form-input" style="padding: 8px;">
                            </div>
                            <div style="flex:1;">
                                <label style="font-size:10px; color:#86868b; margin-bottom:4px; display:block; font-weight:600;">TO</label>
                                <input type="date" name="end_date" id="end_date" class="form-input" style="padding: 8px;">
                            </div>
                        </div>

                        <div style="background: rgba(0,113,227,0.04); border-radius: 8px; padding: 8px;">
                            <div class="form-label-header">
                                <label class="form-label" style="color: var(--blue-apple);">WEEKS IN MONTH</label>
                                <div>
                                    <button type="button" class="btn-micro" onclick="selectAll('week_num', true)">All</button>
                                    <button type="button" class="btn-micro" onclick="selectAll('week_num', false)">Clear</button>
                                </div>
                            </div>
                            <div style="display: flex; gap: 8px;">
                                <label class="checkbox-item" style="margin:0;"><input type="checkbox" name="week_num" value="1"> W1</label>
                                <label class="checkbox-item" style="margin:0;"><input type="checkbox" name="week_num" value="2"> W2</label>
                                <label class="checkbox-item" style="margin:0;"><input type="checkbox" name="week_num" value="3"> W3</label>
                                <label class="checkbox-item" style="margin:0;"><input type="checkbox" name="week_num" value="4"> W4</label>
                            </div>
                        </div>
                    </div>
                    {% endif %}

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
                    
                    {% if status_col %}
                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">STATUS</label>
                        </div>
                        <div class="checkbox-group" style="max-height: 80px;">
                            {% for status in unique_statuses %}
                            <label class="checkbox-item"><input type="checkbox" name="status_filters" value="{{ status }}" {% if status|string|lower == 'ok' %}checked{% endif %}> <span style="overflow:hidden; text-overflow:ellipsis;">{{ status }}</span></label>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}
                </div>

                <!-- STEP 2: BUILD TABLE -->
                <div class="step-card">
                    <div class="step-header">
                        <h3 class="step-title">2. Build Table</h3>
                    </div>

                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">ROW GROUPING</label>
                            <div>
                                <button type="button" class="btn-micro" onclick="selectAll('index_cols', true)">All</button>
                                <button type="button" class="btn-micro" onclick="selectAll('index_cols', false)">Clear</button>
                            </div>
                        </div>
                        <div class="checkbox-group sortable-list" id="row-grouping-container">
                            {% for col in grouping_cols %}
                            <div class="checkbox-item">
                                <span class="drag-handle">☰</span>
                                <input type="checkbox" name="index_cols" value="{{ col }}" {% if col == 'Customized Sales Date' or col == 'SPC Name' %}checked{% endif %}> 
                                <span style="overflow: hidden; text-overflow: ellipsis;">{{ col }}</span>
                            </div>
                            {% endfor %}
                        </div>
                    </div>

                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">COLUMN SPLIT</label>
                            <div>
                                <button type="button" class="btn-micro" onclick="selectAll('columns_cols', true)">All</button>
                                <button type="button" class="btn-micro" onclick="selectAll('columns_cols', false)">Clear</button>
                            </div>
                        </div>
                        <div class="checkbox-group sortable-list" id="col-grouping-container">
                            {% for col in grouping_cols %}
                            <div class="checkbox-item">
                                <span class="drag-handle">☰</span>
                                <input type="checkbox" name="columns_cols" value="{{ col }}"> 
                                <span style="overflow: hidden; text-overflow: ellipsis;">{{ col }}</span>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                    
                    <div class="form-group" style="background: rgba(52,199,89,0.06); padding: 10px; border-radius: 10px;">
                        <div class="form-label-header">
                            <label class="form-label" style="color: #248a3d;">COMPARE VIEW</label>
                        </div>
                        <div class="btn-segmented">
                            <input type="radio" id="cv_none" name="spc_compare" value="none" checked onchange="updateDashboard()">
                            <label for="cv_none">None</label>
                            
                            <input type="radio" id="cv_day" name="spc_compare" value="day" onchange="updateDashboard()">
                            <label for="cv_day">Daily</label>
                            
                            <input type="radio" id="cv_week" name="spc_compare" value="week" onchange="updateDashboard()">
                            <label for="cv_week">Weekly</label>
                        </div>
                    </div>
                </div>

                <!-- STEP 3: METRICS -->
                <div class="step-card">
                    <div class="step-header">
                        <h3 class="step-title">3. Choose Metrics</h3>
                    </div>

                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">VALUES</label>
                        </div>
                        <div class="checkbox-group" style="max-height: none;">
                            <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="sum" checked> Sum Total</label>
                            <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="count"> Count (Quantity)</label>
                            <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="mean"> Average Price</label>
                        </div>
                    </div>

                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">INSIGHTS</label>
                        </div>
                        <div class="checkbox-group" style="max-height: none;">
                            <label class="checkbox-item" title="% of Column Total"><input type="checkbox" name="agg_funcs" value="contrib"> Contribution %</label>
                            <label class="checkbox-item" title="Period-over-Period Growth"><input type="checkbox" name="agg_funcs" value="growth"> Growth % (PoP)</label>
                        </div>
                    </div>

                    <div class="form-group">
                        <div class="checkbox-group" style="max-height: none; background: transparent; border: none; padding: 0;">
                            <label class="checkbox-item"><input type="checkbox" name="show_row_total" value="true" checked> <b>Show Grand Totals</b></label>
                        </div>
                    </div>
                </div>

            </form>
            <div style="text-align: center; margin: 24px 0;">
                <a href="/upload" style="color: #ff3b30; font-size: 13px; text-decoration: none; font-weight: 600; background: rgba(255,59,48,0.1); padding: 10px 20px; border-radius: 980px;">← Upload New File</a>
            </div>
        </div>

        <div class="main-content">
            <div class="header-actions">
                <h2 style="font-size: 28px; font-weight: 700; margin: 0; letter-spacing: -0.015em;">Dashboard</h2>
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
                        <p style="color: #86868b; font-size: 15px;">Configure your parameters on the left to view data.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const filterMap = {{ filter_mapping_json|safe }};
    </script>

    <script>
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
            document.getElementById('start_date').value = '';
            document.getElementById('end_date').value = '';
            document.getElementById('dr_custom').checked = true;
            document.querySelectorAll('.checkbox-item').forEach(el => el.style.display = 'flex');
            updateDashboard();
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

        function setDateRange(range) {
            const today = new Date();
            let start = new Date();
            let end = new Date();
            
            document.querySelectorAll('input[name="week_num"]').forEach(r => r.checked = false);
            
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
                document.getElementById('table-wrapper').innerHTML = '<div style="padding: 60px 20px; text-align: center;"><p style="color: #86868b; font-size: 15px;">Select at least one Row Grouping and one Metric.</p></div>';
                return;
            }

            try {
                const response = await fetch('/calculate', { method: 'POST', body: formData });
                const data = await response.json();
                
                if (response.ok) {
                    let html = "";
                    if (data.filter_text) {
                        html += `<div style="padding: 14px 16px; border-bottom: 1px solid rgba(0,0,0,0.06); background: rgba(255,255,255,0.8);">${data.filter_text}</div>`;
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
            if(el.type !== 'date' && el.name !== 'dr_preset') {
                el.addEventListener('change', updateDashboard);
            }
        });
        document.querySelectorAll('#config-form input[type="date"]').forEach(el => {
            el.addEventListener('blur', () => {
                document.getElementById('dr_custom').checked = true;
                updateDashboard();
            });
        });
        
        window.addEventListener('DOMContentLoaded', () => {
            const body = document.body;
            if (window.innerWidth <= 768) { body.classList.add('mobile-mode'); document.getElementById('viewToggleBtn').innerHTML = "📱 Mobile Site"; } 
            else { body.classList.add('desktop-mode'); document.getElementById('viewToggleBtn').innerHTML = "💻 Desktop Site"; }
            
            const sortableLists = document.querySelectorAll('.sortable-list');
            sortableLists.forEach(el => { new Sortable(el, { animation: 150, handle: '.drag-handle', onUpdate: updateDashboard }); });
        });
        
        window.onload = updateDashboard;
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
    status_col = next((c for c in ['FinalStatus', 'Final Record Status', 'Validation Remarks'] if c in df.columns), "")
    
    spc_list = df[spc_col].dropna().unique().tolist() if spc_col and spc_col in df.columns else []
    seg1_list = df[seg1_col].dropna().unique().tolist() if seg1_col and seg1_col in df.columns else []
    family_list = df[family_col].dropna().unique().tolist() if family_col and family_col in df.columns else []
    
    mapping_df = df[[c for c in [spc_col, seg1_col, family_col] if c]].dropna(how='all').fillna('N/A').astype(str).drop_duplicates()
    mapping_df.columns = ['spc' if c == spc_col else 'seg' if c == seg1_col else 'fam' if c == family_col else c for c in mapping_df.columns]
    filter_mapping_json = json.dumps(mapping_df.to_dict(orient='records'))
    
    return sorted([str(x) for x in spc_list]), sorted([str(x) for x in seg1_list]), sorted([str(x) for x in family_list]), status_col, filter_mapping_json

def get_date_bounds(df, date_col):
    min_date, max_date = "N/A", "N/A"
    if date_col and date_col in df.columns:
        try:
            parsed = pd.to_datetime(df[date_col], errors='coerce', dayfirst=True)
            if pd.notna(parsed.min()): min_date = parsed.min().strftime("%d %b %y")
            if pd.notna(parsed.max()): max_date = parsed.max().strftime("%d %b %y")
        except: pass
    return min_date, max_date

# --- ROUTES ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        otp = str(random.randint(100000, 999999))
        session['pending_user'] = user_id
        session['expected_otp'] = otp
        print(f"\n\n[SECURITY] 🔒 OTP generated for {user_id}: {otp}\n\n")
        return redirect(url_for('verify'))
    return render_template_string(LOGIN_HTML)

@app.route("/verify", methods=["GET", "POST"])
def verify():
    error = None
    if request.method == 'POST':
        user_otp = request.form.get('otp')
        if user_otp == session.get('expected_otp'):
            session['authenticated'] = True
            session.pop('expected_otp', None)
            return redirect(url_for('home'))
        else:
            error = "Invalid or expired OTP. Please try again."
    return render_template_string(VERIFY_HTML, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/", methods=["GET"])
@login_required
def home():
    df = load_data()
    if df is not None:
        return redirect(url_for('workspace'))
    return redirect(url_for('upload_page'))

@app.route("/upload", methods=["GET"])
@login_required
def upload_page():
    return render_template_string(UPLOAD_HTML)

@app.route("/workspace", methods=["GET"])
@login_required
def workspace():
    df = load_data()
    if df is None: return redirect(url_for('upload_page'))
    
    all_cols = df.columns.tolist()
    default_date_col = 'Customized Sales Date' if 'Customized Sales Date' in all_cols else ('Sale Date' if 'Sale Date' in all_cols else next((c for c in all_cols if 'date' in str(c).lower()), ""))
    
    # Filter grouping columns to categorical/dates only (exclude raw numeric metrics)
    grouping_cols = df.select_dtypes(exclude=['number']).columns.tolist()
    
    spc_list, seg1_list, family_list, status_col, filter_mapping_json = get_filter_lists(df)
    unique_statuses = df[status_col].dropna().unique().tolist() if status_col else []
    upload_time = get_metadata()
    min_sale_date, max_sale_date = get_date_bounds(df, default_date_col)

    return render_template_string(WORKSPACE_HTML, all_cols=all_cols, grouping_cols=grouping_cols, default_date_col=default_date_col, status_col=status_col, unique_statuses=unique_statuses, spc_list=spc_list, seg1_list=seg1_list, family_list=family_list, upload_time=upload_time, min_sale_date=min_sale_date, max_sale_date=max_sale_date, filter_mapping_json=filter_mapping_json)

@app.route("/dashboard", methods=["POST"])
@login_required
def dashboard():
    if 'file' in request.files and request.files['file'].filename != '':
        file = request.files['file']
        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        save_data(df)
    return redirect(url_for('workspace'))

@app.route("/calculate", methods=["POST"])
@login_required
def calculate():
    df = load_data()
    if df is None: return jsonify({"error": "No data available."}), 400
        
    date_col = request.form.get('date_col')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    week_nums = request.form.getlist('week_num')
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
    if not base_aggs: base_aggs = ['sum']

    try:
        filter_texts = []
        df_filtered = df.copy()
        
        if date_col and date_col in df_filtered.columns:
            df_filtered[date_col] = pd.to_datetime(df_filtered[date_col], errors='coerce', dayfirst=True)
            if week_nums:
                valid_dates = df_filtered[date_col].dropna()
                if not valid_dates.empty:
                    base_date = pd.to_datetime(start_date) if start_date else valid_dates.min()
                    month_start = datetime(base_date.year, base_date.month, 1)
                    valid_masks = []
                    for w in week_nums:
                        w_idx = int(w)
                        if w_idx == 1: w_start, w_end = month_start, datetime(base_date.year, base_date.month, 7, 23, 59, 59)
                        elif w_idx == 2: w_start, w_end = datetime(base_date.year, base_date.month, 8), datetime(base_date.year, base_date.month, 14, 23, 59, 59)
                        elif w_idx == 3: w_start, w_end = datetime(base_date.year, base_date.month, 15), datetime(base_date.year, base_date.month, 21, 23, 59, 59)
                        else:
                            w_start = datetime(base_date.year, base_date.month, 22)
                            nm = datetime(base_date.year, base_date.month + 1, 1) if base_date.month < 12 else datetime(base_date.year + 1, 1, 1)
                            w_end = nm - timedelta(seconds=1)
                        valid_masks.append((df_filtered[date_col] >= w_start) & (df_filtered[date_col] <= w_end))
                    if valid_masks:
                        df_filtered = df_filtered[pd.concat(valid_masks, axis=1).any(axis=1)]
                        filter_texts.append(f"<b>{date_col}</b>: Weeks {', '.join(week_nums)}")
            else:
                if start_date: df_filtered = df_filtered[df_filtered[date_col] >= pd.to_datetime(start_date)]
                if end_date: df_filtered = df_filtered[df_filtered[date_col] <= pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
                if start_date or end_date:
                    s_str = pd.to_datetime(start_date).strftime('%d-%b-%y') if start_date else 'Start'
                    e_str = pd.to_datetime(end_date).strftime('%d-%b-%y') if end_date else 'End'
                    filter_texts.append(f"<b>{date_col}</b>: {s_str} to {e_str}")

        status_col = next((c for c in ['FinalStatus', 'Final Record Status', 'Validation Remarks'] if c in df_filtered.columns), "")
        if status_col and status_filters:
            df_filtered = df_filtered[df_filtered[status_col].isin(status_filters)]
            filter_texts.append(f"<b>{status_col}</b>: {', '.join(status_filters)}")

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

        if spc_compare in ['day', 'week'] and spc_col and date_col:
            if spc_compare == 'day':
                df_filtered['_Day_Comp'] = df_filtered[date_col].dt.strftime('%d-%b-%y')
                if spc_col not in index_cols: index_cols.append(spc_col)
                if '_Day_Comp' not in columns_cols: columns_cols.append('_Day_Comp')
            elif spc_compare == 'week':
                def gw(dt):
                    if pd.isna(dt): return 'Unknown'
                    w = (dt.day - 1) // 7 + 1
                    return f"W{w} ({dt.strftime('%b')})"
                df_filtered['_Week_Comp'] = df_filtered[date_col].apply(gw)
                if spc_col not in index_cols: index_cols.append(spc_col)
                if '_Week_Comp' not in columns_cols: columns_cols.append('_Week_Comp')
            filter_texts.append(f"<b>Compare</b>: {spc_compare.capitalize()}-wise")

        filter_text = f"<p style='color:#86868b; font-size:12px; margin:0;'>{' | '.join(filter_texts)}</p>" if filter_texts else ""

        if df_filtered.empty:
            return jsonify({"table_html": "<div style='padding: 60px 20px; text-align: center;'><p style='color: #ff3b30;'>No data found for the selected filters.</p></div>", "filter_text": filter_text})

        for col in index_cols:
            if col in df_filtered.columns and pd.api.types.is_datetime64_any_dtype(df_filtered[col]):
                df_filtered[col] = df_filtered[col].dt.strftime('%d-%b-%y')

        pivot_kwargs = {'data': df_filtered, 'index': index_cols, 'values': value_cols, 'aggfunc': base_aggs}
        if columns_cols: pivot_kwargs['columns'] = columns_cols
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
                        if len(item_str) >= 6 and any(char.isdigit() for char in item_str):
                            try: parts.append(pd.to_datetime(item_str, errors='raise').strftime('%d-%b-%y'))
                            except Exception: parts.append(item_str)
                        else:
                            parts.append(item_str)
                new_cols.append(" - ".join(parts) if parts else " - ".join(str(c) for c in col if str(c).strip()))
            else:
                if col in index_cols:
                    new_cols.append(str(col))
                else:
                    col_str = str(col)
                    if len(col_str) >= 6 and any(char.isdigit() for char in col_str):
                        try: new_cols.append(pd.to_datetime(col_str, errors='raise').strftime('%d-%b-%y'))
                        except Exception: new_cols.append(col_str.replace('sum - ', '').replace('count - ', '').replace('mean - ', ''))
                    else:
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
        
        def format_metric(x, is_pct=False):
            if pd.isna(x) or x == '': return ''
            try:
                if is_pct:
                    val = float(x)
                    if val > 0: return f'<span class="pct-positive">↑ {val:.1f}%</span>'
                    elif val < 0: return f'<span class="pct-negative">↓ {abs(val):.1f}%</span>'
                    return f'<span class="pct-neutral">-</span>'
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
@login_required
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
