from pynput import mouse, keyboard
import time

_last_activity_time = time.time()

def _on_activity(*args):
    global _last_activity_time
    _last_activity_time = time.time()

def start_activity_tracking():
    mouse_listener = mouse.Listener(on_move=_on_activity, on_click=_on_activity)
    keyboard_listener = keyboard.Listener(on_press=_on_activity)
    mouse_listener.start()
    keyboard_listener.start()

def get_idle_seconds():
    return time.time() - _last_activity_time