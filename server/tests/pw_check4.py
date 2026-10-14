"""Visual check for the multi-user / role-based permissions feature:
- superadmin sees the Users tab, can add a viewer and a scoped admin
- a viewer logging in sees read-only UI and no Users/Settings tabs
- a device-scoped admin only sees their assigned device
"""
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5050'
OUT = '/tmp/pw4'

with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
    pg = b.new_page(viewport={'width': 1280, 'height': 1000})
    pg.on('pageerror', lambda e: print('PAGEERROR:', e))
    pg.on('console', lambda m: print('CONSOLE:', m.type, m.text) if m.type == 'error' else None)
    pg.on('response', lambda r: print('RES', r.status, r.url) if r.status == 400 else None)

    # ── login as the bootstrap superadmin ───────────────────────────────
    pg.goto(f'{BASE}/login')
    pg.fill('input[name=username]', 'admin')
    pg.fill('input[name=password]', 'pulse2026')
    pg.click('button[type=submit]')
    pg.wait_for_url(f'{BASE}/')
    pg.wait_for_selector('.kpi', timeout=8000)

    tabs = pg.eval_on_selector_all('button.tab', 'els => els.map(e => e.dataset.t)')
    print('superadmin tabs:', tabs)
    assert 'users' in tabs and 'settings' in tabs

    pg.click('button.tab[data-t=users]')
    pg.wait_for_selector('#nuUser', timeout=8000)
    pg.screenshot(path=f'{OUT}_users_tab.png', full_page=True)

    # add a plain viewer
    pg.fill('#nuUser', 'viewer1')
    pg.fill('#nuPass', 'viewerpass')
    pg.select_option('#nuRole', 'viewer')
    pg.click('#nuAdd')
    pg.wait_for_timeout(500)

    # add a device-scoped admin limited to the first device
    dev_ids = pg.eval_on_selector_all('table tbody tr', 'rows => []')  # placeholder, real check below
    pg.fill('#nuUser', 'scopedadmin')
    pg.fill('#nuPass', 'scopedpass')
    pg.select_option('#nuRole', 'admin')
    pg.uncheck('#nuDevAll')
    pg.check('.nuDev >> nth=0')
    pg.click('#nuAdd')
    pg.wait_for_timeout(500)
    pg.screenshot(path=f'{OUT}_users_after_add.png', full_page=True)

    rows = pg.eval_on_selector_all('#tbl table tbody tr td:nth-child(2)', 'els => els.map(e => e.textContent)')
    print('users table usernames:', rows)
    assert 'viewer1' in rows and 'scopedadmin' in rows

    pg.click('#logoutBtn')
    pg.wait_for_url(f'{BASE}/login')

    # ── login as the viewer: read-only, no admin tabs ───────────────────
    pg.fill('input[name=username]', 'viewer1')
    pg.fill('input[name=password]', 'viewerpass')
    pg.click('button[type=submit]')
    pg.wait_for_url(f'{BASE}/')
    pg.wait_for_selector('.kpi', timeout=8000)

    viewer_tabs = pg.eval_on_selector_all('button.tab', 'els => els.map(e => e.dataset.t)')
    print('viewer tabs:', viewer_tabs)
    assert 'users' not in viewer_tabs and 'settings' not in viewer_tabs

    pg.click('button.tab[data-t=devices]')
    pg.wait_for_selector('table', timeout=8000)
    pg.screenshot(path=f'{OUT}_viewer_devices.png', full_page=True)
    print('viewer sees add-device form:', pg.is_visible('#newName'))
    print('viewer sees rename buttons:', pg.is_visible('.renamebtn'))
    print('viewer sees remote buttons:', pg.is_visible('.remotebtn'))
    print('viewer sees bulk-delete button:', pg.is_visible('.selbar .danger'))

    pg.click('#logoutBtn')
    pg.wait_for_url(f'{BASE}/login')

    # ── login as the scoped admin: only their device ────────────────────
    pg.fill('input[name=username]', 'scopedadmin')
    pg.fill('input[name=password]', 'scopedpass')
    pg.click('button[type=submit]')
    pg.wait_for_url(f'{BASE}/')
    pg.wait_for_selector('.kpi', timeout=8000)
    pg.click('button.tab[data-t=devices]')
    pg.wait_for_selector('table', timeout=8000)
    dev_rows = pg.eval_on_selector_all('#tbl table tbody tr', 'rows => rows.length')
    print('scoped admin sees N devices in table:', dev_rows)
    pg.screenshot(path=f'{OUT}_scopedadmin_devices.png', full_page=True)
    assert dev_rows == 1

    b.close()
    print('ALL OK')
