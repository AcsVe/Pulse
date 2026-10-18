"""
Synthesizes mouse and keyboard input via the Win32 SendInput API, through
ctypes directly rather than pywin32's older keybd_event/mouse_event calls —
those only accept virtual-key codes, which are tied to the active keyboard
layout and can't type arbitrary text (Arabic included, which matters here
given this dashboard's own Arabic-first UI). SendInput's KEYEVENTF_UNICODE
mode injects any Unicode character directly, bypassing layout entirely.

This only works, and is only meant to run, inside PulseHelper — the
per-user process in the logged-in user's own session. Session-0 input
injection is blocked by the same session-isolation wall discussed in
usage_tracker.py.
"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
WHEEL_DELTA = 120  # one Win32 "notch" — mouseData for MOUSEEVENTF_WHEEL/HWHEEL is a multiple of this

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_LWIN = 0x5B
VK_TAB = 0x09
VK_MENU = 0x12   # Alt
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_RETURN = 0x0D
VK_BACK = 0x08
VK_ESCAPE = 0x1B
VK_DELETE = 0x2E

# Names the dashboard's remote-control keyboard (app.js's #rcKeyboard) sends
# for keys that have no printable character of their own, mapped to their
# Win32 virtual-key codes.
NAMED_KEYS = {
    'enter': VK_RETURN, 'backspace': VK_BACK, 'tab': VK_TAB, 'escape': VK_ESCAPE,
    'delete': VK_DELETE, 'up': VK_UP, 'down': VK_DOWN, 'left': VK_LEFT, 'right': VK_RIGHT,
    'win': VK_LWIN, 'ctrl': VK_CONTROL, 'alt': VK_MENU, 'shift': VK_SHIFT,
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.POINTER(wintypes.ULONG))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.POINTER(wintypes.ULONG))]


class _INPUTunion(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('union', _INPUTunion)]


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def _abs_coords(x, y):
    sw, sh = _screen_size()
    return int(x * 65535 / max(1, sw - 1)), int(y * 65535 / max(1, sh - 1))


def move_to(x, y):
    ax, ay = _abs_coords(x, y)
    mi = MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None)
    _send(INPUT(INPUT_MOUSE, _INPUTunion(mi=mi)))


def click(x, y):
    move_to(x, y)
    ax, ay = _abs_coords(x, y)
    down = MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE, 0, None)
    up = MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE, 0, None)
    _send(INPUT(INPUT_MOUSE, _INPUTunion(mi=down)))
    time.sleep(0.03)
    _send(INPUT(INPUT_MOUSE, _INPUTunion(mi=up)))


def right_click(x, y):
    """Windows Session-0 services can never do this (see remote.py's module
    docstring on session isolation) — this only runs from PulseHelper, in the
    logged-in user's own session, same as click()/drag() above."""
    move_to(x, y)
    ax, ay = _abs_coords(x, y)
    down = MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_ABSOLUTE, 0, None)
    up = MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_RIGHTUP | MOUSEEVENTF_ABSOLUTE, 0, None)
    _send(INPUT(INPUT_MOUSE, _INPUTunion(mi=down)))
    time.sleep(0.03)
    _send(INPUT(INPUT_MOUSE, _INPUTunion(mi=up)))


def scroll(dx, dy):
    """Two-finger-drag-to-scroll from the dashboard's remote-control panel
    (app.js's finishPinch — a two-finger pan that isn't a quick stationary
    tap) — trackpad-style, the same gesture 'pinch' used to be silently
    ignored for on Windows (no pinch/zoom equivalent on a desktop; see
    README's "Known gaps"). dx/dy arrive as CSS pixels dragged across the
    dashboard's own screen image, not device pixels — scaled down here to
    a handful of Win32 wheel "notches" (WHEEL_DELTA=120 each, capped at 5)
    so one full-panel drag doesn't fly through pages of content.
    Direction follows the drag (content tracks the fingers, like a
    touchscreen) — if it ever feels backwards on real hardware, flip the
    sign on the affected axis here."""
    def notches(px):
        return max(-5, min(5, round(px / 40))) * WHEEL_DELTA

    vy = notches(dy)
    if vy:
        mi = MOUSEINPUT(0, 0, vy & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, None)
        _send(INPUT(INPUT_MOUSE, _INPUTunion(mi=mi)))
    vx = notches(dx)
    if vx:
        mi = MOUSEINPUT(0, 0, vx & 0xFFFFFFFF, MOUSEEVENTF_HWHEEL, 0, None)
        _send(INPUT(INPUT_MOUSE, _INPUTunion(mi=mi)))


def key_press(name, modifiers=None):
    """Presses one named key (NAMED_KEYS — Enter/Backspace/Tab/Escape/arrows/
    Win/etc.), optionally held together with modifier keys ('ctrl'/'alt'/
    'shift' in `modifiers`) — e.g. key_press('escape') or
    key_press('a', ['ctrl']) for Ctrl+A. For anything not in NAMED_KEYS and
    with no modifiers (an ordinary printable character the dashboard's
    keyboard sent as-is), falls back to type_text() so it still goes through
    KEYEVENTF_UNICODE rather than needing a virtual-key code for every
    possible character."""
    key = (name or '')
    vk = NAMED_KEYS.get(key.lower())
    if vk is None:
        if modifiers and key:
            vk = ord(key[0].upper())
        else:
            type_text(key)
            return
    mod_vks = [NAMED_KEYS[m] for m in (modifiers or []) if m in NAMED_KEYS]
    key_combo(*mod_vks, vk)


def drag(x1, y1, x2, y2, duration_ms):
    """Linear-interpolated drag so the OS sees a real gesture (useful for
    things like dismissing a toast or dragging a window) rather than a
    teleport — mirrors why the Android app caps/paces its own swipe
    duration (see app.js's endDrag) instead of just jumping the finger."""
    steps = max(1, min(40, duration_ms // 16))
    ax1, ay1 = _abs_coords(x1, y1)
    down = MOUSEINPUT(ax1, ay1, 0, MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE, 0, None)
    _send(INPUT(INPUT_MOUSE, _INPUTunion(mi=down)))
    for i in range(1, steps + 1):
        x = x1 + (x2 - x1) * i / steps
        y = y1 + (y2 - y1) * i / steps
        move_to(x, y)
        time.sleep(max(0.005, duration_ms / 1000 / steps))
    ax2, ay2 = _abs_coords(x2, y2)
    up = MOUSEINPUT(ax2, ay2, 0, MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE, 0, None)
    _send(INPUT(INPUT_MOUSE, _INPUTunion(mi=up)))


def key_combo(*vks):
    downs = [INPUT(INPUT_KEYBOARD, _INPUTunion(ki=KEYBDINPUT(vk, 0, 0, 0, None))) for vk in vks]
    ups = [INPUT(INPUT_KEYBOARD, _INPUTunion(ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, None))) for vk in reversed(vks)]
    _send(*downs)
    time.sleep(0.03)
    _send(*ups)


def type_text(text):
    for ch in text:
        code = ord(ch)
        down = INPUT(INPUT_KEYBOARD, _INPUTunion(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, None)))
        up = INPUT(INPUT_KEYBOARD, _INPUTunion(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)))
        _send(down)
        _send(up)
        time.sleep(0.01)
