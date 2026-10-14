from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5050'
OUT = '/tmp/pw3'

with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
    pg = b.new_page(viewport={'width': 1280, 'height': 900})
    pg.on('pageerror', lambda e: print('PAGEERROR:', e))
    pg.on('console', lambda m: print('CONSOLE:', m.type, m.text) if m.type == 'error' else None)

    pg.goto(f'{BASE}/login')
    pg.fill('input[name=username]', 'admin')
    pg.fill('input[name=password]', 'pulse2026')
    pg.click('button[type=submit]')
    pg.wait_for_url(f'{BASE}/')
    pg.wait_for_selector('.kpi', timeout=8000)

    pg.click('button.tab[data-t=devices]')
    pg.wait_for_selector('table', timeout=8000)
    pg.screenshot(path=f'{OUT}_devices.png', full_page=True)

    # open the remote-control modal for the first device
    pg.click('.remotebtn >> nth=0')
    pg.wait_for_timeout(1500)
    pg.screenshot(path=f'{OUT}_remote_modal.png', full_page=True)
    print('remote modal visible:', pg.is_visible('.remote-box'))
    print('wait text visible (no frame yet):', pg.is_visible('#rcWait'))
    pg.click('#rcClose')
    pg.wait_for_timeout(300)
    print('modal closed:', not pg.is_visible('.remote-box'))

    pg.click('button.tab[data-t=settings]')
    pg.wait_for_timeout(500)
    pg.screenshot(path=f'{OUT}_settings.png', full_page=True)

    # exercise the new settings controls
    pg.select_option('#esFreq', 'hourly')
    print('hour input disabled on hourly:', pg.is_disabled('#esHour'))
    pg.check('#esUnrestricted')
    pg.wait_for_timeout(200)
    pg.screenshot(path=f'{OUT}_settings_unrestricted.png', full_page=True)
    pg.check('#esPerDevice')
    pg.fill('#esHost', 'smtp.gmail.com')
    pg.fill('#esRecipient', 'owner@example.com')
    pg.click('#esSave')
    pg.wait_for_timeout(600)
    pg.screenshot(path=f'{OUT}_settings_saved.png', full_page=True)

    b.close()
print('DONE')
