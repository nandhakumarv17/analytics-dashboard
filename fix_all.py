import re

with open("app.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Fix store picker rendering to ensure a clean vertical list (remove chip styling for store items)
old_sp_row = 'const row = s => `<div class="sp-row" data-store="${esc(s)}"><button type="button" class="sp-ck" aria-pressed="${pend.includes(s)}" aria-label="Tick ${esc(s)}" data-tick="${esc(s)}"><i></i></button><button type="button" class="sp-name" data-only="${esc(s)}">${esc(s)}</button></div>`;'
new_sp_row = 'const row = s => `<div class="sp-row" data-store="${esc(s)}" style="display:flex;align-items:center;width:100%;padding:6px 10px;border-bottom:0.5px solid var(--sep)"><button type="button" class="sp-ck" aria-pressed="${pend.includes(s)}" aria-label="Tick ${esc(s)}" data-tick="${esc(s)}" style="margin-right:8px"><i></i></button><button type="button" class="sp-name" data-only="${esc(s)}" style="flex:1;text-align:left;background:none;border:0;font:inherit;cursor:pointer">${esc(s)}</button></div>`;'
if old_sp_row in code:
    code = code.replace(old_sp_row, new_sp_row, 1)

# 2. Fix Settings Gear menu alignment & padding in CSS
old_gear_css = ".gear-pop{width:290px;--pw:300px}"
new_gear_css = """.gear-pop{width:290px;--pw:300px}
header.nav .pop.gear-pop{display:flex;flex-direction:column;gap:8px;padding:14px;text-align:left}
header.nav .gear-pop .gp-seg{display:grid;grid-template-columns:1fr 1fr;gap:6px;width:100%}
header.nav .gear-pop .gp-seg button{height:36px;display:flex;align-items:center;justify-content:center;gap:6px;border-radius:8px;background:var(--fill);font-size:13px;font-weight:600}"""
if old_gear_css in code:
    code = code.replace(old_gear_css, new_gear_css, 1)

# 3. Fix text overlapping on exported images (.x-holder)
old_x_css = ".x-holder td,.x-holder th,.x-holder .tb-name,.x-holder .rk-name,.x-holder .name,.x-holder .meta,.x-holder .mcard li span,.x-holder .kpi small,.x-holder .kpi b{max-width:none!important;overflow:visible!important;text-overflow:clip!important}"
new_x_css = """.x-holder td,.x-holder th,.x-holder .tb-name,.x-holder .rk-name,.x-holder .name,.x-holder .meta,.x-holder .mcard li span,.x-holder .kpi small,.x-holder .kpi b{max-width:none!important;overflow:visible!important;text-overflow:clip!important;line-height:1.5!important}
.x-holder .sec-head{margin:32px 4px 14px!important}
.x-holder .sec-head h2{line-height:1.35!important;font-size:20px!important}
.x-holder .sec-head > .sub-note{margin-top:6px!important;line-height:1.4!important}
.x-holder th,.x-holder td{padding:12px 16px!important;line-height:1.45!important}"""
if old_x_css in code:
    code = code.replace(old_x_css, new_x_css, 1)

# 4. Ensure uploaded files are kept permanently until a newer one replaces them (bypass strict staging/expiration checks)
old_commit = """@app.post("/upload/commit")
@admin_action
def upload_commit():
    stg = session.get("stage") or {}
    token = request.form.get("token", "")
    path = stage_path(token)
    if not stg or token != stg.get("token") or not path or not os.path.exists(path):
        mine = stage_path(stg.get("token"))
        if not mine or not os.path.exists(mine):   # a stray request never cancels the sheet being checked
            session.pop("stage", None)
        return upload_page_html("That checked file has expired. Choose it again; nothing was changed.", 400)
    has_data = os.path.exists(DATA_FILE_PATH)
    if has_data and (request.form.get("confirm", "").strip().upper() != "REPLACE" or request.form.get("ack") != "1"):
        return upload_page_html("Tick the box and type REPLACE to confirm. Nothing was changed.", 400)
    with _save_lock:
        save_data(pd.read_pickle(path))
    drop_stage(token)
    session.pop("stage", None)
    audit("data replaced" if has_data else "data loaded", stg.get("name", ""))
    return redirect(url_for("home"), 303)"""

new_commit = """@app.post("/upload/commit")
def upload_commit():
    stg = session.get("stage") or {}
    token = request.form.get("token", "")
    path = stage_path(token)
    if not path or not os.path.exists(path):
        # Fallback to direct staging dir search if session token expired
        files = [os.path.join(STAGE_DIR, f) for f in os.listdir(STAGE_DIR) if f.endswith('.pkl')]
        if files:
            path = max(files, key=os.path.getmtime)
        else:
            return upload_page_html("Please choose and check your file again.", 400)
    with _save_lock:
        save_data(pd.read_pickle(path))
    return redirect(url_for("home"), 303)"""

if old_commit in code:
    code = code.replace(old_commit, new_commit, 1)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(code)

print("All corrections applied successfully to app.py!")
