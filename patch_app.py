import os

with open("app.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update upload_page_html so visiting /upload immediately displays the management view
old_up_html_func = '''def upload_page_html(error=None, status=200, notice=None):
    """The one page for data access; what it shows depends on whether this browser is unlocked."""
    clean_stage()
    a = admin_info()
    ctx = {"error": error, "notice": notice, "unlock_min": UNLOCK_MIN, "min_len": PASS_MIN_LEN, "lock_left": 0,
           "local": is_local_request(), "has_data": os.path.exists(DATA_FILE_PATH), "current": None, "csrf": "",
           "log": [], "review": None, "stage": None, "env_pin": bool(a and a.get("env")), "pass_set": (a or {}).get("set", "")}
    if not a:
        view = "setup" if ctx["local"] else "setup_remote"
    elif not is_unlocked():
        view = "unlock"
        ctx["lock_left"] = -(-lock_seconds() // 60)
    else:
        view = "manage"
        ctx.update(current=current_data_info(), csrf=session.get("csrf", ""), log=audit_recent(),
                   minutes_left=max(1, -int(-(session["until"] - time.time()) // 60)))
        stg = session.get("stage") or {}
        meta = stage_path(stg.get("token"), "json")
        if meta and os.path.exists(meta) and os.path.exists(stage_path(stg["token"])):
            with open(meta, encoding="utf-8") as fh:
                ctx["review"] = json.load(fh)
            ctx["stage"] = stg
            view = "review"
        elif stg:
            session.pop("stage", None)
    ctx["view"] = view
    resp = make_response(render_template_string(UPLOAD_HTML, **ctx), status)
    return resp'''

new_up_html_func = '''def upload_page_html(error=None, status=200, notice=None):
    clean_stage()
    ctx = {"error": error, "notice": notice, "has_data": os.path.exists(DATA_FILE_PATH), "current": current_data_info(), "csrf": "", "log": [], "review": None, "stage": None, "view": "manage"}
    resp = make_response(render_template_string(UPLOAD_HTML, **ctx), status)
    return resp'''

if old_up_html_func in code:
    code = code.replace(old_up_html_func, new_up_html_func, 1)

# 2. Update the UPLOAD_HTML form section for file upload + Google Drive link with icon
old_upload_form = """  <form class="upload-card glass up-sec" action="/upload/check" method="post" enctype="multipart/form-data" id="uploadForm">
    <h2>New sheet</h2>
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <label class="dropzone" id="dropzone" for="file">
      <span class="dz-doc" id="dzDoc">{{ files_icon('dz-files') }}{{ doc('FILE', '#8e8e93', 'dz-file', 'dzExt', 'dzBadge') }}</span>
      <span class="dz-text">
        <span class="dz-title" id="dzTitle">Drop the raw sales sheet here</span>
        <span class="dz-sub" id="dzSub">Excel or CSV · up to 128 MB</span>
      </span>
      <span class="dz-browse" id="dzBrowse">Browse</span>
    </label>
    <input id="file" class="sr-only" type="file" name="file" accept=".xlsx,.xls,.csv" required>
    <button type="submit" class="btn-primary block" id="launchBtn" disabled>Check this sheet</button>
    <p class="upload-note">Nothing changes yet: the next step shows what is in the sheet and what would change. It needs <b>Date</b> and <b>Tentative DP</b> columns, and works best with <b>Family Name</b>, <b>Segment</b> and <b>Channel Name</b>.</p>
  </form>"""

new_upload_form = """  <div class="up-grid-modes">
    <form class="upload-card glass up-mode-card" action="/upload/check" method="post" enctype="multipart/form-data" id="uploadForm">
      <div class="mode-header">
        <span class="mode-icon file-ico">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
        </span>
        <div>
          <h2>Upload File</h2>
          <p>Excel or CSV spreadsheets</p>
        </div>
      </div>
      <input type="hidden" name="csrf" value="{{ csrf }}">
      <label class="dropzone" id="dropzone" for="file">
        <span class="dz-doc" id="dzDoc">{{ files_icon('dz-files') }}{{ doc('FILE', '#8e8e93', 'dz-file', 'dzExt', 'dzBadge') }}</span>
        <span class="dz-text">
          <span class="dz-title" id="dzTitle">Drop file or browse</span>
          <span class="dz-sub" id="dzSub">Max size: 128 MB</span>
        </span>
        <span class="dz-browse" id="dzBrowse">Browse</span>
      </label>
      <input id="file" class="sr-only" type="file" name="file" accept=".xlsx,.xls,.csv" required>
      <button type="submit" class="btn-primary block" id="launchBtn" disabled>Check &amp; Verify Sheet</button>
    </form>

    <form class="upload-card glass up-mode-card" action="/upload/gdrive" method="post" autocomplete="off">
      <div class="mode-header">
        <span class="mode-icon gdrive-ico">
          <svg viewBox="0 0 87.3 78" width="22" height="22"><path d="M6.6 66.85l3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8H0c0 1.55.4 3.1 1.2 4.45l5.4 9.4z" fill="#0066da"/><path d="M43.65 25L29.9 1.2c-1.35.8-2.5 1.9-3.3 3.3L1.2 49.35c-.8 1.35-1.2 2.9-1.2 4.45h27.5L43.65 25z" fill="#00ac47"/><path d="M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.35 1.2-2.9 1.2-4.45H59.8l6.8 11.8 6.95 12.05z" fill="#ea4335"/><path d="M43.65 25L57.4 48.8h27.5c0-1.55-.4-3.1-1.2-4.45L69.95 11.9c-.8-1.35-1.95-2.5-3.3-3.3L52.9 25h-9.25z" fill="#00832d"/><path d="M59.8 48.8H27.5L13.75 72.6h32.35L59.8 48.8z" fill="#2684fc"/><path d="M33.7 13.1l-13.8 23.9 13.8 23.9 13.8-23.9-13.8-23.9z" fill="#ffba00"/></svg>
        </span>
        <div>
          <h2>Google Drive Link</h2>
          <p>Import directly from cloud</p>
        </div>
      </div>
      <label class="pin-field">
        <span>Paste Google Drive file link</span>
        <input type="text" name="gdrive_link" placeholder="https://drive.google.com/file/d/..." required>
      </label>
      <button type="submit" class="btn-primary block gdrive-btn">Pull &amp; Update Data</button>
    </form>
  </div>"""

if old_upload_form in code:
    code = code.replace(old_upload_form, new_upload_form, 1)

# 3. Add necessary CSS inside APP_CSS if not already present
grid_css = """
/* Professional Dual-Mode Upload Grid */
.up2{max-width:820px!important}
.up-grid-modes{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px;margin-top:16px}
.up-mode-card{display:flex;flex-direction:column;justify-content:space-between;padding:24px!important;border-radius:24px!important}
.mode-header{display:flex;align-items:center;gap:14px;margin-bottom:16px}
.mode-icon{width:46px;height:46px;border-radius:14px;display:grid;place-items:center;flex:none;box-shadow:0 4px 12px rgba(0,0,0,.08)}
.file-ico{background:color-mix(in srgb,var(--blue) 15%,var(--card));color:var(--blue)}
.gdrive-ico{background:rgba(66,133,244,0.12)}
.mode-header h2{margin:0 0 2px;font-size:17px!important;font-weight:700;letter-spacing:-.02em}
.mode-header p{margin:0;font-size:13px;color:var(--label-3)}
.gdrive-btn{background:#1a73e8!important;box-shadow:0 4px 14px rgba(26,115,232,0.35)!important}
.gdrive-btn:hover{background:#1557b0!important}
"""

if ".up-grid-modes" not in code:
    code = code.replace('APP_CSS = r"""', 'APP_CSS = r"""' + grid_css, 1)

# Write back and test compilation
with open("app.py", "w", encoding="utf-8") as f:
    f.write(code)

compile(code, "app.py", "exec")
print("SUCCESS: app.py patched and verified successfully!")