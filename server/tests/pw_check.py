import sys
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5050'
OUT = sys.argv[1] if len(sys.argv) > 1 else '/tmp/pw'


def run():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        ctx = b.new_context(viewport={'width': 1280, 'height': 800})
        pg = ctx.new_page()
        pg.goto(f'{BASE}/login')
        pg.fill('input[name=username]', 'admin')
        pg.fill('input[name=password]', 'pulse2026')
        pg.click('button[type=submit]')
        pg.wait_for_url(f'{BASE}/')
        pg.wait_for_selector('.kpi', timeout=8000)
        pg.screenshot(path=f'{OUT}_overview_ar.png', full_page=True)
        print('dir:', pg.evaluate("document.documentElement.dir"))

        # switch to apps tab, sort, check frozen col
        pg.click('button.tab[data-t=apps]')
        pg.wait_for_selector('table', timeout=8000)
        pg.click('th[data-k=ms]')
        pg.wait_for_timeout(300)
        pg.screenshot(path=f'{OUT}_apps_ar.png', full_page=True)

        # select a row + bulk delete bar
        pg.click('tbody tr:first-child .rowcb')
        pg.wait_for_timeout(200)
        sel_visible = pg.is_visible('.selbar.on')
        print('selbar visible after check:', sel_visible)
        pg.screenshot(path=f'{OUT}_apps_selected.png', full_page=True)

        # switch language to English (LTR)
        pg.click('#langBtn')
        pg.wait_for_timeout(300)
        print('dir after lang switch:', pg.evaluate("document.documentElement.dir"))
        pg.screenshot(path=f'{OUT}_apps_en.png', full_page=True)

        # devices tab
        pg.click('button.tab[data-t=devices]')
        pg.wait_for_timeout(300)
        pg.screenshot(path=f'{OUT}_devices.png', full_page=True)
        pg.fill('#newName', 'جهاز تجريبي')
        pg.click('#addBtn')
        pg.wait_for_timeout(500)
        has_code = pg.is_visible('.codebox')
        print('enroll code box visible:', has_code)
        pg.screenshot(path=f'{OUT}_devices_code.png', full_page=True)

        # mobile width check
        pg.set_viewport_size({'width': 390, 'height': 844})
        pg.click('button.tab[data-t=overview]')
        pg.wait_for_timeout(400)
        body_w = pg.evaluate("document.documentElement.scrollWidth")
        vp_w = pg.evaluate("window.innerWidth")
        print('mobile scrollWidth vs innerWidth:', body_w, vp_w)
        pg.screenshot(path=f'{OUT}_mobile.png', full_page=True)

        # kiosk screen (no session) via key
        ctx2 = b.new_context(viewport={'width': 1920, 'height': 1080})
        pg2 = ctx2.new_page()
        pg2.goto(f'{BASE}/screen?key=screen123')
        pg2.wait_for_selector('.kpi', timeout=8000)
        has_controls = pg2.is_visible('#periodChips button')
        print('kiosk has period chips:', has_controls, '(should be true, but no tabs/logout)')
        print('kiosk has tabs nav:', pg2.is_visible('#tabs'))
        pg2.screenshot(path=f'{OUT}_kiosk.png', full_page=True)

        b.close()
    print('DONE')


run()
