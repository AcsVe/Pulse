from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5050'
OUT = '/tmp/pw2'

with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
    pg = b.new_page(viewport={'width': 1280, 'height': 900})
    pg.goto(f'{BASE}/login')
    pg.fill('input[name=username]', 'admin')
    pg.fill('input[name=password]', 'pulse2026')
    pg.click('button[type=submit]')
    pg.wait_for_url(f'{BASE}/')
    pg.wait_for_selector('.kpi', timeout=8000)
    pg.screenshot(path=f'{OUT}_overview.png', full_page=True)

    pg.click('button.tab[data-t=data]')
    pg.wait_for_selector('table', timeout=8000)
    pg.screenshot(path=f'{OUT}_data_tab.png', full_page=True)

    # rename an app label via the edit button, then verify it persisted
    pg.once('dialog', lambda d: d.accept('اسمي المخصص'))
    pg.click('.editbtn >> nth=0')
    pg.wait_for_timeout(500)
    print('renamed label visible:', pg.is_visible('text=اسمي المخصص'))
    pg.screenshot(path=f'{OUT}_data_renamed.png', full_page=True)

    pg.click('button.tab[data-t=devices]')
    pg.wait_for_selector('table', timeout=8000)
    pg.screenshot(path=f'{OUT}_devices_ip.png', full_page=True)

    pg.once('dialog', lambda d: d.accept('اسم جديد للجهاز'))
    pg.click('.renamebtn >> nth=0')
    pg.wait_for_timeout(500)
    # NOTE: a bare 'text=' selector is ambiguous here — the device-filter popover
    # (#devList) also lists device names inside hidden <label> checkboxes, so it
    # must match within the visible table specifically.
    print('device renamed visible:', pg.is_visible('.tw table .lbl:has-text("اسم جديد للجهاز")'))

    pg.click('button.tab[data-t=settings]')
    pg.wait_for_timeout(500)
    pg.screenshot(path=f'{OUT}_settings.png', full_page=True)

    pg.fill('#esHost', 'smtp.gmail.com')
    pg.fill('#esUser', 'me@example.com')
    pg.fill('#esRecipient', 'owner@example.com')
    pg.check('#esEnabled')
    pg.click('.esSec[value=overview]')
    pg.click('#esSave')
    pg.wait_for_timeout(600)
    pg.screenshot(path=f'{OUT}_settings_saved.png', full_page=True)

    b.close()
print('DONE')
