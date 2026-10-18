"""
Remote control: screen capture + command execution, both session-bound so
this only runs inside PulseHelper (same reasoning as usage_tracker.py).

Structured after the Android app's ScreenCaptureService: one loop uploads
frames, a second, independent loop polls for queued commands — so a slow
frame upload never delays a tap/swipe actually being executed. There is no
Android-style one-time consent dialog here (MediaProjection's own
screen-recording permission grant): on a company-owned Windows PC, the IT
admin who enrolled the device already has the access this is securing, so
remote control simply turns on/off in step with the dashboard's own
"active" flag (/api/v1/remote-state) rather than needing a per-session
local approval.
"""
import io
import threading
import time

from PIL import ImageGrab

from . import input_sim, uploader

# Tightened from 0.3/0.4s — the dashboard's own tap-feedback ping already
# masks most of this, but AnyDesk/TeamViewer-style responsiveness still
# showed up as noticeably laggier here, and PulseHelper has nothing else
# competing for its time while a remote session is actually active.
FRAME_INTERVAL_S = 0.2
COMMAND_INTERVAL_S = 0.2
STATE_POLL_IDLE_S = 5
STATE_POLL_ACTIVE_S = 3


class RemoteControl:
    def __init__(self):
        self._stop = threading.Event()
        self._active = threading.Event()
        self._threads = []

    def start_watcher(self):
        t = threading.Thread(target=self._watch_state, daemon=True, name='pulse-remote-state')
        t.start()
        self._threads.append(t)

    def stop(self):
        self._stop.set()
        self._active.clear()

    def _watch_state(self):
        while not self._stop.is_set():
            try:
                st = uploader.remote_state()
            except Exception:
                st = None
            active = bool(st and st.get('active'))
            if active and not self._active.is_set():
                self._active.set()
                self._spawn_active_loops()
            elif not active and self._active.is_set():
                self._active.clear()
            time.sleep(STATE_POLL_ACTIVE_S if active else STATE_POLL_IDLE_S)

    def _spawn_active_loops(self):
        threading.Thread(target=self._frame_loop, daemon=True, name='pulse-remote-frame').start()
        threading.Thread(target=self._command_loop, daemon=True, name='pulse-remote-cmd').start()

    def _frame_loop(self):
        while self._active.is_set() and not self._stop.is_set():
            try:
                img = ImageGrab.grab()
                buf = io.BytesIO()
                img.convert('RGB').save(buf, format='JPEG', quality=55)
                uploader.upload_frame(buf.getvalue(), img.width, img.height)
            except Exception:
                pass
            time.sleep(FRAME_INTERVAL_S)

    def _command_loop(self):
        while self._active.is_set() and not self._stop.is_set():
            try:
                for cmd in uploader.poll_commands():
                    self._execute(cmd)
            except Exception:
                pass
            time.sleep(COMMAND_INTERVAL_S)

    def _execute(self, cmd):
        action = cmd.get('action')
        params = cmd.get('params') or {}
        x, y = params.get('x'), params.get('y')
        try:
            if action == 'tap' and x is not None:
                input_sim.click(x, y)
            elif action == 'swipe' and x is not None:
                input_sim.drag(x, y, params.get('x2', x), params.get('y2', y),
                                max(80, min(1200, params.get('duration') or 220)))
            elif action == 'text' and params.get('text'):
                input_sim.type_text(params['text'])
            elif action == 'rightclick' and x is not None:
                input_sim.right_click(x, y)
            elif action == 'key' and params.get('key'):
                input_sim.key_press(params['key'], params.get('modifiers'))
            elif action == 'back':
                input_sim.key_combo(input_sim.VK_MENU, input_sim.VK_LEFT)       # Alt+Left: back, in browsers/Explorer
            elif action == 'home':
                input_sim.key_combo(input_sim.VK_LWIN, ord('D'))                # Win+D: show desktop
            elif action == 'recents':
                input_sim.key_combo(input_sim.VK_LWIN, input_sim.VK_TAB)        # Win+Tab: Task View
            elif action == 'launch' and params.get('pkg'):
                import os
                os.startfile(params['pkg'])
            elif action == 'close' and params.get('pkg'):
                import psutil
                target = params['pkg'].lower()
                for p in psutil.process_iter(['name']):
                    if (p.info.get('name') or '').lower() == target:
                        p.terminate()
            # 'pinch' has no desktop equivalent worth guessing at — ignored.
        except Exception:
            pass
