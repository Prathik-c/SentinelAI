from pynput import mouse, keyboard
import time
import ctypes

_last_activity_time = time.time()
_event_count = 0

def _on_activity(*args):
    global _last_activity_time, _event_count
    _last_activity_time = time.time()
    _event_count += 1

def start_activity_tracking():
    mouse_listener = mouse.Listener(on_move=_on_activity, on_click=_on_activity, on_scroll=_on_activity)
    keyboard_listener = keyboard.Listener(on_press=_on_activity)
    mouse_listener.start()
    keyboard_listener.start()

def get_idle_seconds():
    return time.time() - _last_activity_time

def get_and_reset_event_count():
    global _event_count
    count = _event_count
    _event_count = 0
    return count

def get_foreground_window_title():
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value if buf.value else ""
    except Exception:
        return ""