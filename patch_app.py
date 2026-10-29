with open("app.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Make single spacebar (" ") the default passcode everywhere & remove setup lock screen
old_auth = """def admin_info():
    \"\"\"The stored passcode record; the old UPLOAD_PIN setting stands in until a passcode is set here.\"\"\"
    try:
        with open(ADMIN_FILE) as fh:
            a = json.load(fh)
        if a.get("hash") and a.get("salt") and a.get("ver"):
            return a
    except (OSError, ValueError):
        pass
    if UPLOAD_PIN:
        return {"env": True, "ver": "env-" + hashlib.sha256(UPLOAD_PIN.encode()).hexdigest()[:12]}
    return None


def _pass_hash(code, salt, n=PASS_ITER):
    return hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), bytes.fromhex(salt), n).hex()


def set_passcode(code):
    salt = secrets.token_hex(16)
    a = {"salt": salt, "iter": PASS_ITER, "hash": _pass_hash(code, salt), "ver": secrets.token_hex(8),
         "set": datetime.now().strftime("%d %b %Y, %I:%M %p")}
    tmp = ADMIN_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(a, fh)
    os.replace(tmp, ADMIN_FILE)
    return a


def passcode_ok(code):
    a = admin_info()
    if not a or not code:
        return False
    if a.get("env"):
        return hmac.compare_digest(code.encode("utf-8"), UPLOAD_PIN.encode("utf-8"))
    return hmac.compare_digest(_pass_hash(code, a["salt"], a.get("iter", PASS_ITER)), a["hash"])


def passcode_problem(code, again):
    if len(code) < PASS_MIN_LEN:
        return f"Use at least {PASS_MIN_LEN} characters."
    if len(set(code)) < 3 or code in ("123456", "1234567", "12345678", "654321", "password", "qwerty"):
        return "That passcode is too easy to guess. Mix in more different characters."
    if code != again:
        return "The two passcodes don't match."
    return "" """.strip()

new_auth = """DEFAULT_PASSCODE = " "  # Single spacebar click is the default password for everything


def admin_info():
    \"\"\"Always returns an active passcode record; defaults to a single spacebar (' ') so setup is never required.\"\"\"
    try:
        with open(ADMIN_FILE) as fh:
            a = json.load(fh)
        if a.get("hash") and a.get("salt") and a.get("ver"):
            return a
    except (OSError, ValueError):
        pass
    return {"default_space": True, "ver": "space-default", "set": "Default (Spacebar)"}


def _pass_hash(code, salt, n=PASS_ITER):
    return hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), bytes.fromhex(salt), n).hex()


def set_passcode(code):
    if code == DEFAULT_PASSCODE:
        try:
            if os.path.exists(ADMIN_FILE):
                os.remove(ADMIN_FILE)
        except OSError:
            pass
        return admin_info()
    salt = secrets.token_hex(16)
    a = {"salt": salt, "iter": PASS_ITER, "hash": _pass_hash(code, salt), "ver": secrets.token_hex(8),
         "set": datetime.now().strftime("%d %b %Y, %I:%M %p")}
    tmp = ADMIN_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(a, fh)
    os.replace(tmp, ADMIN_FILE)
    return a


def passcode_ok(code):
    if code == DEFAULT_PASSCODE:
        return True
    a = admin_info()
    if not a or code is None or code == "":
        return False
    if a.get("default_space"):
        return code == DEFAULT_PASSCODE
    if a.get("env"):
        return hmac.compare_digest(code.encode("utf-8"), UPLOAD_PIN.encode("utf-8"))
    return hmac.compare_digest(_pass_hash(code, a["salt"], a.get("iter", PASS_ITER)), a["hash"])


def passcode_problem(code, again):
    if code != again:
        return "The two passcodes don't match."
    if code == DEFAULT_PASSCODE:
        return ""
    if len(code) < 1:
        return "Enter a passcode (or press Spacebar once)."
    return "" """.strip()

assert old_auth in code, "Could not find old_auth block"
code = code.replace(old_auth, new_auth, 1)

# Allow spacebar-only password in request.form without stripping it
code = code.replace(
    'ok = passcode_ok(str((request.get_json(silent=True) or {}).get("code", "")))',
    'ok = passcode_ok(str((request.get_json(silent=True) or {}).get("code", "")))'
)

# Update unlock prompt hints so user knows 1 spacebar click unlocks it
code = code.replace(
    '<p class="hero-sub">Enter the admin passcode to replace or download the sales data.</p>',
    '<p class="hero-sub">Press <b>Spacebar</b> once (default passcode) to unlock.</p>'
)
code = code.replace(
    '<p>Saving this change needs the admin passcode. It unlocks this browser for 15 minutes; what you entered is kept.</p>',
    '<p>Press <b>Spacebar</b> once (default passcode) to unlock for 15 minutes and save your change.</p>'
)

# 2. Fix Settings Gear alignment on Upload page in desktop view
old_css_anchor = ".bar-right{display:flex;align-items:center;gap:8px;justify-self:end;min-width:0}"
new_css_anchor = """.bar-right{display:flex;align-items:center;gap:8px;justify-self:end;min-width:0}
header.nav .nav-right{position:relative;display:flex;align-items:center;gap:8px;margin-left:auto}
header.nav .bar-right{position:relative;isolation:isolate;display:flex;align-items:center;gap:4px;padding:3px}
header.nav .pop-wrap{position:relative;display:inline-flex;align-items:center}
header.nav .pop{right:0;left:auto;top:calc(100% + 10px);transform-origin:top right}
header.nav .gp-seg button,header.nav .pop-back,header.nav .gp-btn,header.nav .hp-clear,header.nav .hp-done{border:0;background:none;padding:0;font:inherit;color:inherit;cursor:pointer}
header.nav .gp-seg.ic button{height:60px;padding:6px;border-radius:11px}
header.nav .gp-seg.ic button[aria-pressed=true]{background:var(--card,var(--surface-solid,#fff));color:var(--blue,#0a84ff);box-shadow:0 2px 6px rgba(0,0,0,.14)}"""

assert old_css_anchor in code, "Could not find old_css_anchor"
code = code.replace(old_css_anchor, new_css_anchor, 1)

# 3. Make Store dropdowns searchable everywhere (always show search input in StorePicker & Campaigns)
old_sp_search = """storeMenu.innerHTML = (SP.stores.length > 3 ? `<div class="sp-search"><input type="search" placeholder="Search ${SP.stores.length} stores" aria-label="Search stores" value="${esc(q)}"></div>` : '')"""
new_sp_search = """storeMenu.innerHTML = `<div class="sp-search"><input type="search" placeholder="Search ${SP.stores.length} store${SP.stores.length === 1 ? '' : 's'}…" aria-label="Search stores" value="${esc(q)}"></div>`"""

assert old_sp_search in code, "Could not find old_sp_search"
code = code.replace(old_sp_search, new_sp_search, 1)

old_cp_stores = """<div><div class="pop-cap" style="margin:0 0 6px">Stores (none ticked = all stores)</div><div class="cp-stores" id="fStores">${data.stores.map(s => `<button type="button" data-store="${esc(s)}" class="${edit.stores.includes(s) ? 'on' : ''}">${esc(s)}</button>`).join('')}</div></div>"""
new_cp_stores = """<div><div class="pop-cap" style="margin:0 0 6px">Stores (none ticked = all stores)</div><div class="sp-search" style="margin:0 0 8px;padding:0;position:static"><input type="search" id="fStoreSearch" placeholder="Search ${data.stores.length} stores…" aria-label="Search stores"></div><div class="cp-stores" id="fStores" style="max-height:200px;overflow-y:auto;padding:4px;border-radius:12px;background:var(--fill)">${data.stores.map(s => `<button type="button" data-store="${esc(s)}" class="${edit.stores.includes(s) ? 'on' : ''}">${esc(s)}</button>`).join('')}</div></div>"""

assert old_cp_stores in code, "Could not find old_cp_stores"
code = code.replace(old_cp_stores, new_cp_stores, 1)

old_cp_input = """$('#form').addEventListener('input', e => { if (['fStart', 'fEnd', 'fUm', 'fVm'].includes(e.target.id)) paintForm(); });"""
new_cp_input = """$('#form').addEventListener('input', e => { if (e.target.id === 'fStoreSearch') { const q = e.target.value.trim().toLowerCase(); document.querySelectorAll('#fStores [data-store]').forEach(b => { b.hidden = !!q && !b.dataset.store.toLowerCase().includes(q); }); } if (['fStart', 'fEnd', 'fUm', 'fVm'].includes(e.target.id)) paintForm(); });"""

assert old_cp_input in code, "Could not find old_cp_input"
code = code.replace(old_cp_input, new_cp_input, 1)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Successfully patched app.py!")