import os
import io
from datetime import datetime
from flask import Flask, request, render_template_string, send_file, jsonify
import pandas as pd

app = Flask(__name__)

# Persistent file storage path for cloud deployments
UPLOAD_DIR = "/tmp/dashboard_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATA_FILE_PATH = os.path.join(UPLOAD_DIR, "shared_data.pkl")
META_FILE_PATH = os.path.join(UPLOAD_DIR, "metadata.pkl")

# --- APPLE iOS "LIQUID GLASS" THEME & RESPONSIVE ENGINE ---
GLOBAL_HEAD = """
<style>
    :root {
        --bg-main: #f2f2f7;
        --glass-bg: rgba(255, 255, 255, 0.75);
        --glass-sidebar: rgba(255, 255, 255, 0.65);
        --glass-border: rgba(255, 255, 255, 0.8);
        --text-primary: #1d1d1f;
        --text-secondary: #86868b;
        --shadow-glass: 0 20px 40px rgba(0, 0, 0, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04);
        --blue-apple: #0071e3;
        --blue-hover: #0077ed;
    }
    
    body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg-main); margin: 0; padding: 0; color: var(--text-primary); -webkit-font-smoothing: antialiased; }
    
    .nav { background: rgba(255, 255, 255, 0.82); backdrop-filter: saturate(200%) blur(30px); border-bottom: 1px solid rgba(0, 0, 0, 0.08); padding: 0 20px; height: 56px; display: flex; justify-content: space-between; align-items: center; font-size: 15px; font-weight: 600; color: var(--text-primary); position: fixed; top: 0; width: 100%; box-sizing: border-box; z-index: 1000; letter-spacing: -0.01em; }
    .view-toggle { background: rgba(0,0,0,0.04); padding: 6px 14px; border-radius: 980px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; transition: 0.2s; border: none; color: var(--text-primary); }
    .view-toggle:hover { background: rgba(0,0,0,0.08); }
    
    .upload-container { max-width: 520px; margin: 130px auto 40px auto; padding: 0 16px; box-sizing: border-box; }
    .title { font-size: 36px; font-weight: 700; letter-spacing: -0.015em; text-align: center; margin: 0 0 8px 0; }
    .subtitle { font-size: 17px; font-weight: 400; text-align: center; color: var(--text-secondary); margin: 0 0 32px 0; letter-spacing: -0.01em; }
    
    .card { background: var(--glass-bg); backdrop-filter: blur(25px) saturate(180%); border-radius: 24px; padding: 32px; box-shadow: var(--shadow-glass); border: 1px solid var(--glass-border); box-sizing: border-box; }
    
    .form-group { margin-bottom: 20px; }
    .form-label { font-size: 13px; font-weight: 600; margin-bottom: 8px; display: block; color: var(--text-primary); letter-spacing: -0.01em; }
    .form-input { width: 100%; padding: 12px 16px; font-size: 14px; border: 1px solid rgba(0,0,0,0.1); border-radius: 12px; background-color: rgba(255,255,255,0.8); color: var(--text-primary); box-sizing: border-box; transition: all 0.2s ease; }
    .form-input:focus { border-color: var(--blue-apple); outline: none; box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.15); }
    
    .checkbox-group { background: rgba(255,255,255,0.6); border: 1px solid rgba(0,0,0,0.08); border-radius: 14px; padding: 12px; max-height: 160px; overflow-y: auto; backdrop-filter: blur(10px); }
    .checkbox-item { display: flex; align-items: center; margin-bottom: 8px; font-size: 13px; cursor: pointer; padding: 4px 6px; border-radius: 8px; transition: background 0.15s; }
    .checkbox-item:hover { background: rgba(0,0,0,0.03); }
    .checkbox-item:last-child { margin-bottom: 0; }
    .checkbox-item input { margin-right: 10px; width: 16px; height: 16px; accent-color: var(--blue-apple); cursor: pointer; }
    
    .btn-primary { background-color: var(--blue-apple); color: white; border: none; border-radius: 980px; padding: 12px 24px; font-size: 15px; font-weight: 500; cursor: pointer; text-align: center; display: inline-block; text-decoration: none; box-sizing: border-box; transition: background 0.2s, transform 0.1s; letter-spacing: -0.01em; }
    .btn-primary:hover { background-color: var(--blue-hover); }
    .btn-primary:active { transform: scale(0.98); }
    .btn-secondary { background-color: rgba(0,0,0,0.05); color: var(--text-primary); border-radius: 980px; padding: 8px 14px; font-size: 12px; font-weight: 500; text-decoration: none; display: inline-block; cursor: pointer; border: 1px solid rgba(0,0,0,0.04); transition: 0.2s; margin: 3px 3px 3px 0; }
    .btn-secondary:hover { background-color: rgba(0,0,0,0.09); }
    
    /* Export Dropdown */
    .dropdown { position: relative; display: inline-block; }
    .dropdown-content { display: none; position: absolute; right: 0; background-color: rgba(255,255,255,0.92); backdrop-filter: blur(30px); min-width: 180px; box-shadow: 0 15px 35px rgba(0,0,0,0.12); border-radius: 16px; border: 1px solid rgba(255,255,255,0.8); z-index: 2000; overflow: hidden; margin-top: 8px; }
    .dropdown-content.show { display: block; animation: fadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
    .dropdown-item { color: var(--text-primary); padding: 12px 18px; text-decoration: none; display: block; font-size: 13px; font-weight: 500; cursor: pointer; border: none; background: none; width: 100%; text-align: left; transition: background 0.2s; }
    .dropdown-item:hover { background-color: rgba(0,113,227,0.08); color: var(--blue-apple); }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }

    .table-container { background: var(--glass-bg); backdrop-filter: blur(25px); border-radius: 20px; box-shadow: var(--shadow-glass); border: 1px solid var(--glass-border); overflow: hidden; width: 100%; box-sizing: border-box; }
    .table-scroll { max-height: calc(100vh - 200px); overflow-y: auto; overflow-x: auto; -webkit-overflow-scrolling: touch; }
    .excel-table { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0; font-size: 13px; background: transparent; word-wrap: break-word; min-width: 600px; }
    .excel-table th, .excel-table td { padding: 12px 16px; text-align: left; border-bottom: 1px solid rgba(0,0,0,0.06); overflow: hidden; text-overflow: ellipsis; }
    .excel-table th { background-color: rgba(255, 255, 255, 0.85); backdrop-filter: blur(20px); font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.03em; position: sticky; top: 0; z-index: 10; border-bottom: 1px solid rgba(0,0,0,0.08); }
    .excel-table td { white-space: nowrap; }
    .excel-table tr:hover td { background-color: rgba(0, 113, 227, 0.03); }
    .excel-table tbody tr:last-child td { font-weight: 700; background-color: rgba(255,255,255,0.6); border-top: 2px solid rgba(0,0,0,0.1); border-bottom: none; }
    .number-cell { font-variant-numeric: tabular-nums; }
    
    /* Drag & Drop Handle Styles */
    .drag-handle { cursor: grab; color: #aeaeb2; margin-right: 8px; font-weight: bold; }
    .drag-handle:active { cursor: grabbing; }

    /* Layout Responsive Styles */
    body.desktop-mode { overflow: hidden; }
    body.desktop-mode .app-layout { display: flex; flex-direction: row; height: 100vh; padding-top: 56px; box-sizing: border-box; }
    body.desktop-mode .sidebar { width: 380px; background: var(--glass-sidebar); backdrop-filter: blur(40px) saturate(180%); border-right: 1px solid rgba(0,0,0,0.08); padding: 24px 20px; overflow-y: auto; flex-shrink: 0; box-sizing: border-box; }
    body.desktop-mode .main-content { flex: 1; padding: 24px 32px; overflow-y: auto; background: var(--bg-main); box-sizing: border-box; }
    body.desktop-mode .header-actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    
    body.mobile-mode { overflow: auto; }
    body.mobile-mode .app-layout { display: flex; flex-direction: column; padding-top: 56px; box-sizing: border-box; }
    body.mobile-mode .sidebar { width: 100%; background: var(--glass-sidebar); border-right: none; border-bottom: 1px solid rgba(0,0,0,0.08); padding: 20px 16px; box-sizing: border-box; }
    body.mobile-mode .main-content { width: 100%; padding: 20px 16px; box-sizing: border-box; background: var(--bg-main); }
    body.mobile-mode .header-actions { display: flex; flex-direction: column; align-items: flex-start; gap: 12px; margin-bottom: 20px; }
    
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.2); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.3); }
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

        // Enable Drag-and-Drop Reordering on Grouping Containers
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
                    <input type="file" name="file" accept=".xlsx, .xls, .csv" required class="form-input" style="border: 2px dashed rgba(0,0,0,0.15); background: rgba(255,255,255,0.5); padding: 24px; text-align: center; cursor: pointer;">
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
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h2 style="font-size: 18px; font-weight: 600; margin: 0; letter-spacing: -0.015em;">Parameters</h2>
                <button type="button" onclick="clearAll()" style="background: none; border: none; color: var(--blue-apple); font-size: 13px; font-weight: 500; cursor: pointer; padding: 0;">Clear All</button>
            </div>
            
            <!-- Metadata Widget -->
            <div style="background: rgba(255,255,255,0.7); padding: 12px 14px; border-radius: 12px; margin-bottom: 16px; font-size: 12px; color: var(--text-secondary); border: 1px solid rgba(0,0,0,0.04);">
                <div><b>Uploaded:</b> {{ upload_time }}</div>
                <div style="margin-top: 4px;"><b>Sale Data Up To:</b> <span style="color: var(--blue-apple); font-weight: 600;">{{ max_sale_date }}</span></div>
            </div>

            <form id="config-form">
                <input type="hidden" name="date_col" value="{{ default_date_col }}">

                {% if default_date_col %}
                <div class="form-group" style="background: rgba(255,255,255,0.6); padding: 14px; border-radius: 14px; border: 1px solid rgba(0,0,0,0.06);">
                    <label class="form-label" style="margin-bottom: 10px;">1. Date Filter ({{ default_date_col }})</label>
                    <div style="display: flex; gap: 4px; margin-bottom: 12px; flex-wrap: wrap;">
                        <button type="button" class="btn-secondary" onclick="setDateRange('today')">Today</button>
                        <button type="button" class="btn-secondary" onclick="setDateRange('week')">Week</button>
                        <button type="button" class="btn-secondary" onclick="setDateRange('month')">Month</button>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <div style="flex:1;">
                            <label style="font-size:10px; color:#86868b; margin-bottom:3px; display:block; text-transform: uppercase; font-weight: 600;">From</label>
                            <input type="date" name="start_date" id="start_date" class="form-input" style="padding: 8px;">
                        </div>
                        <div style="flex:1;">
                            <label style="font-size:10px; color:#86868b; margin-bottom:3px; display:block; text-transform: uppercase; font-weight: 600;">To</label>
                            <input type="date" name="end_date" id="end_date" class="form-input" style="padding: 8px;">
                        </div>
                    </div>
                </div>
                {% endif %}

                {% if status_col %}
                <div class="form-group">
                    <label class="form-label">2. Filter by {{ status_col }}</label>
                    <div class="checkbox-group" style="max-height: 110px;">
                        {% for status in unique_statuses %}
                        <label class="checkbox-item">
                            <input type="checkbox" name="status_filters" value="{{ status }}" {% if status|string|lower == 'ok' %}checked{% endif %}> 
                            {{ status }}
                        </label>
                        {% endfor %}
                    </div>
                </div>
                {% endif %}

                <div class="form-group">
                    <label class="form-label">3. Row Grouping (Drag ☰ to Reorder)</label>
                    <div class="checkbox-group sortable-list">
                        {% for col in all_cols %}
                        <div class="checkbox-item">
                            <span class="drag-handle">☰</span>
                            <input type="checkbox" name="index_cols" value="{{ col }}" {% if col == 'SPC Name' %}checked{% endif %}> 
                            <span style="overflow: hidden; text-overflow: ellipsis;">{{ col }}</span>
                        </div>
                        {% endfor %}
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">4. Column Grouping (Optional)</label>
                    <div class="checkbox-group sortable-list" style="max-height: 110px;">
                        {% for col in all_cols %}
                        <div class="checkbox-item">
                            <span class="drag-handle">☰</span>
                            <input type="checkbox" name="columns_cols" value="{{ col }}"> 
                            <span style="overflow: hidden; text-overflow: ellipsis;">{{ col }}</span>
                        </div>
                        {% endfor %}
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">5. Calculation Type</label>
                    <div class="checkbox-group" style="max-height: none;">
                        <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="sum" checked> Sum (Value)</label>
                        <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="count"> Count (Qty)</label>
                        <label class="checkbox-item"><input type="checkbox" name="agg_funcs" value="mean"> Average</label>
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">6. Options</label>
                    <div class="checkbox-group" style="max-height: none;">
                        <label class="checkbox-item"><input type="checkbox" name="show_row_total" value="true"> Add Row Totals</label>
                    </div>
                </div>
            </form>
            <div style="text-align: center; margin-top: 24px;">
                <a href="/" style="color: #ff3b30; font-size: 13px; text-decoration: none; font-weight: 500;">← Upload Different File</a>
            </div>
        </div>

        <div class="main-content">
            <div class="header-actions">
                <h2 style="font-size: 28px; font-weight: 700; margin: 0; letter-spacing: -0.015em;">Live Dashboard</h2>
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
                        <p style="color: #86868b; font-size: 15px;">Select at least one Row from the left panel to see your data instantly.</p>
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
            updateDashboard();
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
                document.getElementById('table-wrapper').innerHTML = '<div style="padding: 60px 20px; text-align: center;"><p style="color: #86868b; font-size: 15px;">Select at least one Row and one Calculation Type.</p></div>';
                return;
            }

            try {
                const response = await fetch('/calculate', { method: 'POST', body: formData });
                const data = await response.json();
                
                if (response.ok) {
                    let html = "";
                    if (data.filter_text) {
                        html += `<div style="padding: 14px 20px; border-bottom: 1px solid rgba(0,0,0,0.06); background: rgba(255,255,255,0.5);">${data.filter_text}</div>`;
                    }
                    html += data.table_html;
                    document.getElementById('table-wrapper').innerHTML = html;
                } else {
                    document.getElementById('table-wrapper').innerHTML = `<div style="padding: 60px 20px; text-align: center;"><p style="color: #ff3b30;">${data.error}</p></div>`;
                }
            } catch (err) {
                console.error("Failed to update", err);
            }
        }

        document.querySelectorAll('#config-form input, #config-form select').forEach(el => {
            el.addEventListener('change', updateDashboard);
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

def get_metadata(df):
    upload_time = "N/A"
    if os.path.exists(META_FILE_PATH):
        try:
            meta = pd.read_pickle(META_FILE_PATH)
            upload_time = meta.get("upload_time", "N/A")
        except Exception:
            pass
            
    max_sale_date = "N/A"
    all_cols = df.columns.tolist()
    date_col = 'Sale Date' if 'Sale Date' in all_cols else next((c for c in all_cols if 'date' in str(c).lower()), "")
    if date_col:
        try:
            parsed_dates = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
            max_dt = parsed_dates.max()
            if pd.notna(max_dt):
                max_sale_date = max_dt.strftime("%d %b %Y")
        except Exception:
            pass
            
    return upload_time, max_sale_date

@app.route("/", methods=["GET", "POST"])
def home():
    df = load_data()
    if df is not None:
        all_cols = df.columns.tolist()
        default_date_col = 'Sale Date' if 'Sale Date' in all_cols else next((c for c in all_cols if 'date' in str(c).lower()), "")
        status_col = ""
        for candidate in ['FinalStatus', 'Final Record Status', 'Validation Remarks']:
            if candidate in all_cols:
                status_col = candidate
                break
        unique_statuses = df[status_col].dropna().unique().tolist() if status_col else []
        upload_time, max_sale_date = get_metadata(df)
        return render_template_string(WORKSPACE_HTML, all_cols=all_cols, default_date_col=default_date_col, status_col=status_col, unique_statuses=unique_statuses, upload_time=upload_time, max_sale_date=max_sale_date)
    return render_template_string(UPLOAD_HTML)

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if 'file' in request.files and request.files['file'].filename != '':
        file = request.files['file']
        df = pd.read_csv(file) if file.filename.endswith('.csv') else pd.read_excel(file)
        save_data(df)
    
    df = load_data()
    if df is None:
        return render_template_string(UPLOAD_HTML)
        
    all_cols = df.columns.tolist()
    default_date_col = 'Sale Date' if 'Sale Date' in all_cols else next((c for c in all_cols if 'date' in str(c).lower()), "")
    
    status_col = ""
    for candidate in ['FinalStatus', 'Final Record Status', 'Validation Remarks']:
        if candidate in all_cols:
            status_col = candidate
            break
            
    unique_statuses = df[status_col].dropna().unique().tolist() if status_col else []
    upload_time, max_sale_date = get_metadata(df)
    
    return render_template_string(WORKSPACE_HTML, all_cols=all_cols, default_date_col=default_date_col, status_col=status_col, unique_statuses=unique_statuses, upload_time=upload_time, max_sale_date=max_sale_date)

@app.route("/calculate", methods=["GET", "POST"])
def calculate():
    df = load_data()
    if df is None: return jsonify({"error": "No data available. Please upload a file."}), 400
        
    date_col = request.form.get('date_col')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    index_cols = request.form.getlist('index_cols')
    columns_cols = request.form.getlist('columns_cols')
    agg_funcs = request.form.getlist('agg_funcs')
    status_filters = request.form.getlist('status_filters')
    show_row_total = request.form.get('show_row_total') == 'true'
    
    num_cols = df.select_dtypes(include='number').columns.tolist()
    value_cols = ['Tentative DP'] if 'Tentative DP' in num_cols else (num_cols[:1] if num_cols else [])
    
    if not index_cols or not value_cols or not agg_funcs:
        return jsonify({"error": "Missing parameters or no numeric column found."}), 400

    try:
        filter_texts = []
        df_filtered = df.copy()
        
        if date_col and date_col in df_filtered.columns and (start_date or end_date):
            df_filtered[date_col] = pd.to_datetime(df_filtered[date_col].astype(str), dayfirst=True, errors='coerce')
            if start_date:
                df_filtered = df_filtered[df_filtered[date_col] >= pd.to_datetime(start_date)]
            if end_date:
                end_datetime = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                df_filtered = df_filtered[df_filtered[date_col] <= end_datetime]
            filter_texts.append(f"<b>{date_col}</b>: {start_date or 'Start'} to {end_date or 'End'}")

        status_col = next((c for c in ['FinalStatus', 'Final Record Status', 'Validation Remarks'] if c in df_filtered.columns), "")
        if status_col and status_filters:
            df_filtered = df_filtered[df_filtered[status_col].isin(status_filters)]
            filter_texts.append(f"<b>{status_col}</b>: {', '.join(status_filters)}")

        filter_text = f"<p style='color:#86868b; font-size:13px; margin:0;'>Filtered by {' | '.join(filter_texts)}</p>" if filter_texts else ""

        if df_filtered.empty:
            return jsonify({"table_html": "<div style='padding: 60px 20px; text-align: center;'><p style='color: #ff3b30;'>No data found for the selected filters.</p></div>", "filter_text": filter_text})

        pivot_kwargs = {'data': df_filtered, 'index': index_cols, 'values': value_cols, 'aggfunc': agg_funcs}
        if columns_cols: pivot_kwargs['columns'] = columns_cols

        pivot_df = pd.pivot_table(**pivot_kwargs).reset_index().fillna(0)
        
        new_cols = []
        agg_map = {'sum': 'Value', 'count': 'Qty', 'mean': 'Avg'}
        
        for col in pivot_df.columns:
            if isinstance(col, tuple):
                parts = []
                for item in col:
                    item_str = str(item).strip()
                    if item_str in agg_map:
                        if len(agg_funcs) > 1: parts.append(agg_map[item_str])
                    elif item_str in value_cols:
                        if len(value_cols) > 1: parts.append(item_str)
                    elif item_str and item_str.lower() != 'nan':
                        parts.append(item_str)
                        
                if not parts:
                    new_cols.append(" - ".join(str(c) for c in col if str(c).strip()))
                else:
                    new_cols.append(" - ".join(parts))
            else:
                new_cols.append(str(col))
                
        pivot_df.columns = new_cols

        metric_columns = [col for col in pivot_df.columns if col not in index_cols]

        if show_row_total:
            pivot_df['TOTAL'] = pivot_df[metric_columns].sum(axis=1)
            metric_columns.append('TOTAL')
            
        if not pivot_df.empty:
            total_row = pd.DataFrame([{c: '' for c in pivot_df.columns}])
            total_row.iloc[0, 0] = 'GRAND TOTAL'
            for c in metric_columns:
                total_row.at[0, c] = pivot_df[c].sum()
            pivot_df = pd.concat([pivot_df, total_row], ignore_index=True)
            
        pivot_df.to_pickle(os.path.join(UPLOAD_DIR, "summary_data.pkl"))
        
        def format_indian_number(x):
            if pd.isna(x) or x == '': return ''
            try:
                num = int(round(float(x)))
                s = str(abs(num))
                if len(s) <= 3:
                    formatted = s
                else:
                    res = s[-3:]
                    s = s[:-3]
                    while len(s) > 2:
                        res = s[-2:] + ',' + res
                        s = s[:-2]
                    formatted = s + ',' + res
                return '-' + formatted if num < 0 else formatted
            except (ValueError, TypeError):
                return str(x)
                
        for c in metric_columns:
            pivot_df[c] = pivot_df[c].apply(format_indian_number)
        
        table_html = pivot_df.to_html(classes='excel-table', border=0, index=False, justify='left')
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
    
    return send_file(
        output, 
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name="Dynamic_Dashboard_Report.xlsx", 
        as_attachment=True
    )

if __name__ == '__main__':
    app.run(debug=True)
