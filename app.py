import os
import io
import json
import random
import smtplib
from email.message import EmailMessage
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, send_file, jsonify, session, redirect, url_for
import pandas as pd
import numpy as np

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'liquid_glass_super_secret_key_2026')

UPLOAD_DIR = "/tmp/dashboard_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATA_FILE_PATH = os.path.join(UPLOAD_DIR, "shared_data.pkl")
META_FILE_PATH = os.path.join(UPLOAD_DIR, "metadata.pkl")

# --- AUTHENTICATION MIDDLEWARE ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
        
        /* Apple IDE Syntax Colors for Headers */
        --code-pink: #ff375f;
        --code-purple: #bf5af2;
        --code-blue: #5ac8fa;
        --code-orange: #ff9f0a;
        --code-green: #32d74b;
    }
    
    body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg-main); margin: 0; padding: 0; color: var(--text-primary); -webkit-font-smoothing: antialiased; }
    
    .nav { background: rgba(255, 255, 255, 0.85); backdrop-filter: saturate(200%) blur(30px); border-bottom: 1px solid rgba(0, 0, 0, 0.08); padding: 0 24px; height: 60px; display: flex; justify-content: space-between; align-items: center; font-size: 16px; font-weight: 600; color: var(--text-primary); position: fixed; top: 0; width: 100%; box-sizing: border-box; z-index: 1000; }
    .view-toggle { background: rgba(0,0,0,0.04); padding: 8px 14px; border-radius: 980px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; transition: 0.2s; border: none; color: var(--text-primary); flex-shrink: 0; }
    .view-toggle:hover { background: rgba(0,0,0,0.08); }
    .logout-btn { color: var(--text-secondary); text-decoration: none; font-size: 13px; font-weight: 500; margin-left: 16px; transition: 0.2s; }
    .logout-btn:hover { color: #ff3b30; }
    
    .upload-container { max-width: 480px; margin: 120px auto 40px auto; padding: 0 16px; box-sizing: border-box; animation: fadeIn 0.4s ease; }
    .title { font-size: 36px; font-weight: 700; letter-spacing: -0.015em; text-align: center; margin: 0 0 8px 0; }
    .subtitle { font-size: 16px; font-weight: 400; text-align: center; color: var(--text-secondary); margin: 0 0 32px 0; }
    
    .card { background: var(--glass-bg); backdrop-filter: blur(25px) saturate(180%); border-radius: 24px; padding: 32px; box-shadow: var(--shadow-glass); border: 1px solid var(--glass-border); box-sizing: border-box; }
    
    /* Clean Sidebar Elements */
    .sidebar-section { margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid rgba(0,0,0,0.06); }
    .sidebar-section:last-child { border-bottom: none; }
    .section-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 0.03em; }
    
    .form-group { margin-bottom: 16px; }
    .form-label { font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; margin-bottom: 6px; display: block; }
    .form-label-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .form-label-header .form-label { margin-bottom: 0; }
    
    .btn-micro { background: rgba(0,0,0,0.04); border: none; color: var(--blue-apple); font-size: 10px; font-weight: 600; cursor: pointer; padding: 4px 8px; border-radius: 6px; transition: 0.2s; }
    .btn-micro:hover { background: rgba(0,113,227,0.1); }
    
    .form-input { width: 100%; padding: 12px 14px; font-size: 14px; border: 1px solid rgba(0,0,0,0.1); border-radius: 12px; background-color: rgba(255,255,255,0.9); color: var(--text-primary); box-sizing: border-box; transition: all 0.2s ease; margin-bottom: 8px; }
    .form-input:focus { border-color: var(--blue-apple); outline: none; box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.15); }
    
    .checkbox-group { background: rgba(255,255,255,0.6); border: 1px solid rgba(0,0,0,0.08); border-radius: 10px; padding: 8px; max-height: 160px; overflow-y: auto; }
    .checkbox-item { display: flex; align-items: center; margin-bottom: 4px; font-size: 13px; cursor: pointer; padding: 6px 8px; border-radius: 6px; transition: background 0.15s; }
    .checkbox-item:hover { background: rgba(0,0,0,0.04); }
    .checkbox-item:last-child { margin-bottom: 0; }
    .checkbox-item input { margin-right: 10px; width: 16px; height: 16px; accent-color: var(--blue-apple); cursor: pointer; flex-shrink: 0; }
    
    .btn-primary { background-color: var(--blue-apple); color: white; border: none; border-radius: 980px; padding: 14px 20px; font-size: 15px; font-weight: 600; cursor: pointer; text-align: center; display: inline-flex; align-items: center; justify-content: center; text-decoration: none; box-sizing: border-box; transition: background 0.2s, transform 0.1s; width: 100%; }
    .btn-primary:hover { background-color: var(--blue-hover); }
    
    .btn-segmented { display: flex; background: rgba(0,0,0,0.04); border-radius: 8px; padding: 3px; gap: 3px; }
    .btn-segmented label { flex: 1; text-align: center; font-size: 12px; font-weight: 500; padding: 6px 0; border-radius: 6px; cursor: pointer; color: var(--text-secondary); transition: 0.2s; }
    .btn-segmented input { display: none; }
    .btn-segmented input:checked + label { background: #ffffff; color: var(--text-primary); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    
    /* KPI Ribbon Styles */
    .kpi-ribbon { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; animation: fadeIn 0.4s ease; }
    .kpi-card { flex: 1; min-width: 140px; background: rgba(255,255,255,0.85); backdrop-filter: blur(25px); border: 1px solid var(--glass-border); border-radius: 16px; padding: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); display: flex; flex-direction: column; justify-content: center; }
    .kpi-card .kpi-label { font-size: 11px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; }
    .kpi-card .kpi-val { font-size: 24px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; }
    
    /* Dropdown */
    .dropdown { position: relative; display: inline-block; }
    .dropdown-content { display: none; position: absolute; right: 0; background-color: rgba(255,255,255,0.95); backdrop-filter: blur(30px); min-width: 170px; box-shadow: 0 15px 35px rgba(0,0,0,0.12); border-radius: 16px; border: 1px solid rgba(255,255,255,0.8); z-index: 2000; overflow: hidden; margin-top: 8px; }
    .dropdown-content.show { display: block; animation: fadeIn 0.2s ease; }
    .dropdown-item { color: var(--text-primary); padding: 12px 16px; text-decoration: none; display: block; font-size: 13px; font-weight: 500; cursor: pointer; border: none; background: none; width: 100%; text-align: left; transition: background 0.2s; }
    .dropdown-item:hover { background-color: rgba(0,113,227,0.08); color: var(--blue-apple); }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }

    /* TABLE CSS FIXES FOR "STUFFED" DATES */
    .table-container { background: var(--glass-bg); backdrop-filter: blur(25px); border-radius: 20px; box-shadow: var(--shadow-glass); border: 1px solid var(--glass-border); overflow: hidden; width: 100%; box-sizing: border-box; display: flex; flex-direction: column; animation: fadeIn 0.5s ease; }
    .table-scroll { max-height: calc(100vh - 280px); overflow-y: auto; overflow-x: auto; -webkit-overflow-scrolling: touch; position: relative; }
    
    .excel-table { width: max-content; min-width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; background: transparent; }
    .excel-table th, .excel-table td { padding: 14px 20px; text-align: left; border-bottom: 1px solid rgba(0,0,0,0.06); white-space: nowrap; position: relative; }
    
    .excel-table th { 
        background-color: rgba(30, 30, 34, 0.95); 
        backdrop-filter: blur(20px) saturate(180%); 
        font-family: 'SF Mono', ui-monospace, Menlo, Monaco, monospace;
        font-size: 11px; 
        font-weight: 600; 
        text-transform: uppercase; 
        letter-spacing: 0.05em; 
        position: sticky; 
        top: 0; 
        z-index: 100; 
        border-bottom: 1px solid rgba(255,255,255,0.1); 
        user-select: none;
    }
    
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
    .excel-table tbody tr:last-child td { font-weight: 700; background-color: rgba(0, 113, 227, 0.12); color: var(--blue-apple); border-top: 2px solid var(--blue-apple); border-bottom: none; }
    
    .number-cell { font-variant-numeric: tabular-nums; }
    .pct-positive { color: #34c759; font-weight: 600; }
    .pct-negative { color: #ff3b30; font-weight: 600; }
    .pct-neutral { color: var(--text-secondary); }

    /* Layout & Sidebar Resizer */
    body.desktop-mode { overflow: hidden; }
    body.desktop-mode .app-layout { display: flex; flex-direction: row; height: 100vh; padding-top: 60px; box-sizing: border-box; }
    
    body.desktop-mode .sidebar { width: 340px; background: var(--glass-sidebar); backdrop-filter: blur(40px) saturate(180%); padding: 24px 20px; overflow-y: auto; flex-shrink: 0; box-sizing: border-box; height: calc(100vh - 60px); }
    
    .sidebar-resizer { width: 5px; background: rgba(0,0,0,0.02); cursor: col-resize; z-index: 100; transition: background 0.2s; flex-shrink: 0; border-right: 1px solid rgba(0,0,0,0.06); }
    .sidebar-resizer:hover, .sidebar-resizer.resizing { background: var(--blue-apple); }
    
    body.desktop-mode .main-content { flex: 1; padding: 24px 32px; overflow-y: auto; overflow-x: hidden; background: var(--bg-main); box-sizing: border-box; height: calc(100vh - 60px); }
    body.desktop-mode .header-actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px; }
    
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
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
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
        <h1 class="title">Corporate Access.</h1>
        <p class="subtitle">Enter your registered email to receive a One-Time Password.</p>
        <div class="card">
            <form action="/login" method="post">
                <div class="form-group">
                    <label class="form-label" style="margin-bottom: 8px;">Work Email</label>
                    <input type="email" name="user_id" required class="form-input" placeholder="e.g. executive@brand.com">
                </div>
                <button type="submit" class="btn-primary">Authenticate</button>
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
        <p class="subtitle">Enter the 6-digit code sent to your inbox.</p>
        <div class="card">
            {% if error %}
            <div style="background: rgba(255,59,48,0.1); color: #ff3b30; padding: 12px; border-radius: 12px; margin-bottom: 16px; font-size: 13px; font-weight: 600; text-align: center;">{{ error }}</div>
            {% endif %}
            <form action="/verify" method="post">
                <div class="form-group">
                    <label class="form-label" style="margin-bottom: 8px;">Secure OTP</label>
                    <input type="text" name="otp" required class="form-input" placeholder="● ● ● ● ● ●" maxlength="6" style="text-align: center; font-size: 24px; letter-spacing: 6px; font-weight: 600;">
                </div>
                <button type="submit" class="btn-primary">Login Securely</button>
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
            <a href="/logout" class="logout-btn">Logout</a>
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

                <!-- DATE & WEEKS -->
                <div class="sidebar-section">
                    <h3 class="section-title">Timeline</h3>
                    {% if default_date_col %}
                    <div style="display: flex; gap: 8px; margin-bottom: 12px;">
                        <div style="flex:1;">
                            <label class="form-label">FROM</label>
                            <input type="date" name="start_date" id="start_date" class="form-input">
                        </div>
                        <div style="flex:1;">
                            <label class="form-label">TO</label>
                            <input type="date" name="end_date" id="end_date" class="form-input">
                        </div>
                    </div>
                    
                    <div class="form-label-header">
                        <label class="form-label">SPECIFIC WEEKS</label>
                        <div>
                            <button type="button" class="btn-micro" onclick="selectAll('week_num', true)">All</button>
                            <button type="button" class="btn-micro" onclick="selectAll('week_num', false)">Clear</button>
                        </div>
                    </div>
                    <div style="display: flex; gap: 12px; margin-bottom: 8px;">
                        <label style="font-size:12px; cursor:pointer; display:flex; align-items:center;"><input type="checkbox" name="week_num" value="1" onchange="updateDashboard()" style="margin-right:6px;"> W1</label>
                        <label style="font-size:12px; cursor:pointer; display:flex; align-items:center;"><input type="checkbox" name="week_num" value="2" onchange="updateDashboard()" style="margin-right:6px;"> W2</label>
                        <label style="font-size:12px; cursor:pointer; display:flex; align-items:center;"><input type="checkbox" name="week_num" value="3" onchange="updateDashboard()" style="margin-right:6px;"> W3</label>
                        <label style="font-size:12px; cursor:pointer; display:flex; align-items:center;"><input type="checkbox" name="week_num" value="4" onchange="updateDashboard()" style="margin-right:6px;"> W4</label>
                    </div>
                    {% endif %}
                </div>

                <!-- DATA FILTERS -->
                <div class="sidebar-section">
                    <h3 class="section-title">Filters</h3>
                    
                    {% if status_col %}
                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">STATUS</label>
                            <div>
                                <button type="button" class="btn-micro" onclick="selectAll('status_filters', true)">All</button>
                                <button type="button" class="btn-micro" onclick="selectAll('status_filters', false)">Clear</button>
                            </div>
                        </div>
                        <div class="checkbox-group" style="max-height: 100px;">
                            {% for status in unique_statuses %}
                            <label class="checkbox-item"><input type="checkbox" name="status_filters" value="{{ status }}"> <span style="overflow:hidden; text-overflow:ellipsis;">{{ status }}</span></label>
                            {% endfor %}
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
                </div>

                <!-- TABLE STRUCTURE -->
                <div class="sidebar-section">
                    <h3 class="section-title">Structure</h3>

                    <div class="form-group">
                        <div class="form-label-header">
                            <label class="form-label">ROW GROUPING</label>
                            <div>
                                <button type="button" class="btn-micro" onclick="selectAll('index_cols', true)">All</button>
                                <button type="button" class="btn-micro" onclick="selectAll('index_cols', false)">Clear</button>
                            </div>
                        </div>
                        <div class="checkbox-group" id="row-grouping-container">
                            {% for col in grouping_cols %}
                            <label class="checkbox-item">
                                <input type="checkbox" name="index_cols" value="{{ col }}"> 
                                <span style="overflow: hidden; text-overflow: ellipsis;">{{ col }}</span>
                            </label>
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
                        <div class="checkbox-group" id="col-grouping-container">
                            {% for col in grouping_cols %}
                            <label class="checkbox-item">
                                <input type="checkbox" name="columns_cols" value="{{ col }}"> 
                                <span style="overflow: hidden; text-overflow: ellipsis;">{{ col }}</span>
                            </label>
                            {% endfor %}
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">COMPARE VIEW</label>
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

                <!-- METRICS -->
                <div class="sidebar-section">
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
                <h2 style="font-size: 28px; font-weight: 700; margin: 0; letter-spacing: -0.015em;">Executive Dashboard</h2>
                <div class="dropdown">
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
            document.querySelectorAll('.checkbox-item').forEach(el => el.style.display = 'flex');
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
            
            const indexCols = formData.getAll('index_cols');
            const aggFuncs = formData.getAll('agg_funcs');
            
            if (indexCols.length === 0 || aggFuncs.length === 0) {
                document.getElementById('table-wrapper').innerHTML = '<div style="padding: 100px 20px; text-align: center;"><p style="color: #86868b; font-size: 15px; font-weight: 500;">Select at least one <b>Row</b> and one <b>Metric</b> from the sidebar to compile intelligence.</p></div>';
                document.getElementById('kpi-banner').style.display = 'none';
                return;
            }

            try {
                const response = await fetch('/calculate', { method: 'POST', body: formData });
                const data = await response.json();
                
                if (response.ok) {
                    // Update KPIs
                    const kpiBanner = document.getElementById('kpi-banner');
                    if(data.kpi_html) {
                        kpiBanner.innerHTML = data.kpi_html;
                        kpiBanner.style.display = 'flex';
                    } else {
                        kpiBanner.style.display = 'none';
                    }
                    
                    // Update Table
                    let html = "";
                    if (data.filter_text) {
                        html += `<div style="padding: 14px 20px; border-bottom: 1px solid rgba(0,0,0,0.06); background: rgba(255,255,255,0.8);">${data.filter_text}</div>`;
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
                el.addEventListener('change', updateDashboard);
            }
        });
        document.querySelectorAll('#config-form input[type="date"]').forEach(el => {
            el.addEventListener('blur', () => {
                updateDashboard();
            });
        });
        
        window.addEventListener('DOMContentLoaded', () => {
            const body = document.body;
            if (window.innerWidth <= 768) { body.classList.add('mobile-mode'); document.getElementById('viewToggleBtn').innerHTML = "📱 Mobile Site"; } 
            else { body.classList.add('desktop-mode'); document.getElementById('viewToggleBtn').innerHTML = "💻 Desktop Site"; }
            updateDashboard();
        });
        
        // Accurate JPEG Download Logic for Scrolled Tables
        function exportImage() {
            const captureArea = document.querySelector('.main-content');
            const scrollArea = document.getElementById('table-wrapper');
            
            // Save original styles
            const origMaxHeight = scrollArea.style.maxHeight;
            const origOverflow = scrollArea.style.overflow;
            
            // Temporarily expand the container to full height so html2canvas sees everything
            scrollArea.style.maxHeight = 'none';
            scrollArea.style.overflow = 'visible';
            
            setTimeout(() => {
                html2canvas(captureArea, { scale: 2, backgroundColor: '#f2f2f7', useCORS: true }).then(canvas => {
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
                        
                        const inst = document.createElement('p');
                        inst.innerText = 'Long-press the image below to save it to your Photos.';
                        inst.style.color = '#ffffff'; 
                        inst.style.marginBottom = '20px';
                        inst.style.fontSize = '14px';
                        
                        const img = document.createElement('img');
                        img.src = imgData;
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
                        link.download = 'Dashboard_Export.jpeg';
                        link.href = imgData;
                        link.click();
                    }
                    
                    // Restore original styles
                    scrollArea.style.maxHeight = origMaxHeight;
                    scrollArea.style.overflow = origOverflow;
                });
            }, 150);
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

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        otp = str(random.randint(100000, 999999))
        session['pending_user'] = user_id
        session['expected_otp'] = otp
        
        # --- SEND LIVE EMAIL VIA GMAIL ---
        sender_email = os.environ.get('EMAIL_ADDRESS')
        sender_password = os.environ.get('EMAIL_PASSWORD')
        
        if sender_email and sender_password and '@' in user_id:
            try:
                msg = EmailMessage()
                msg.set_content(f"Your Analytics Pro verification code is: {otp}\n\nPlease do not share this code with anyone.")
                msg['Subject'] = 'Analytics Pro Access Code'
                msg['From'] = f"Analytics Pro <{sender_email}>"
                msg['To'] = user_id

                server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
                server.login(sender_email, sender_password)
                server.send_message(msg)
                server.quit()
                print(f"[EMAIL] Sent to {user_id}")
            except Exception as e:
                print(f"[EMAIL ERROR] Failed to send: {e}")
                # Print to logs so you can still log in if email fails
                print(f"\n\n[SECURITY] 🔒 OTP generated for {user_id}: {otp}\n\n")
        else:
            # Fallback if vars are missing
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
            error = "Invalid code. Please try again."
    return render_template_string(VERIFY_HTML, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    df = load_data()
    if df is not None:
        all_cols = df.columns.tolist()
        default_date_col = 'Customized Sales Date' if 'Customized Sales Date' in all_cols else ('Sale Date' if 'Sale Date' in all_cols else next((c for c in all_cols if 'date' in str(c).lower()), ""))
        
        grouping_cols = df.select_dtypes(exclude=['number']).columns.tolist()
        
        spc_list, seg1_list, family_list, status_col, filter_mapping_json = get_filter_lists(df)
        unique_statuses = df[status_col].dropna().unique().tolist() if status_col else []
        upload_time = get_metadata()
        min_sale_date, max_sale_date = get_date_bounds(df, default_date_col)

        return render_template_string(WORKSPACE_HTML, all_cols=all_cols, grouping_cols=grouping_cols, default_date_col=default_date_col, status_col=status_col, unique_statuses=unique_statuses, spc_list=spc_list, seg1_list=seg1_list, family_list=family_list, upload_time=upload_time, min_sale_date=min_sale_date, max_sale_date=max_sale_date, filter_mapping_json=filter_mapping_json)
    return render_template_string(UPLOAD_HTML)

@app.route("/upload", methods=["GET"])
@login_required
def upload_page():
    return render_template_string(UPLOAD_HTML)

@app.route("/dashboard", methods=["POST"])
@login_required
def dashboard():
    if 'file' in request.files and request.files['file'].filename != '':
        file = request.files['file']
        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        save_data(df)
    return redirect(url_for('home'))

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
    
    if not index_cols or not agg_funcs:
        return jsonify({"error": "Select at least one Row Grouping and one Metric."}), 400

    calc_contrib = 'contrib' in agg_funcs
    calc_growth = 'growth' in agg_funcs
    base_aggs = [f for f in agg_funcs if f in ['sum', 'count', 'mean']]
    if not base_aggs: base_aggs = ['sum']

    try:
        filter_texts = []
        df_filtered = df.copy()
        
        # Filtering Engine
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

        # Calculate Executive KPIs based strictly on the filtered slice
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
            return jsonify({"table_html": "<div style='padding: 60px 20px; text-align: center;'><p style='color: #ff3b30;'>No data found for the selected filters.</p></div>", "filter_text": filter_text, "kpi_html": ""})

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
@login_required
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
