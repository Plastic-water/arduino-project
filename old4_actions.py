"""TriSense actions: turns a command name into a real change on the PC.

from actions import perform

perform("VOLUP")   # raises the system volume, returns True
                   # returns False if the command is unknown or the action failed

Windows: each volume key press changes the volume by about 2%.
"""

import os
import subprocess
import time

import pyautogui

# ---------------- Tunables ----------------
VOLUME_PRESSES = 3  # key presses per VOLUP/VOLDOWN (3 presses ~ 6% on Windows)
SCROLL_AMOUNT = 400  # mouse-wheel units per SCROLLUP / SCROLLDOWN
ZOOM_AMOUNT = 200  # ctrl + wheel units per ZOOMIN / ZOOMOUT
SCREENSHOT_DIR = 'screenshots'

pyautogui.PAUSE = 0.02  # default is 0.1 s after every call, too slow for volume


def _press(key, times=1):
    for _ in range(times):
        pyautogui.press(key)


def _lock():
    import ctypes

    ctypes.windll.user32.LockWorkStation()


def _screenshot():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOT_DIR, time.strftime('shot_%Y%m%d_%H%M%S.png'))
    pyautogui.screenshot(path)
    print(f'[ACTION] screenshot saved to {path}')


def _zoom(amount):
    # Ctrl + mouse wheel zooms browsers, Office, most editors
    pyautogui.keyDown('ctrl')
    try:
        pyautogui.scroll(amount)
    finally:
        pyautogui.keyUp('ctrl')


ACTIONS = {
    'VOLUP': lambda: _press('volumeup', VOLUME_PRESSES),
    'VOLDOWN': lambda: _press('volumedown', VOLUME_PRESSES),
    'MUTE': lambda: _press('volumemute'),
    'PLAYPAUSE': lambda: _press('playpause'),
    'NEXT': lambda: _press('nexttrack'),
    'PREV': lambda: _press('prevtrack'),
    'SCROLLUP': lambda: pyautogui.scroll(SCROLL_AMOUNT),
    'SCROLLDOWN': lambda: pyautogui.scroll(-SCROLL_AMOUNT),
    'ZOOMIN': lambda: _zoom(ZOOM_AMOUNT),
    'ZOOMOUT': lambda: _zoom(-ZOOM_AMOUNT),
    'CLICK': lambda: pyautogui.click(),
    'SCREENSHOT': _screenshot,
    'LOCK': _lock,
    'OPEN_CHROME': lambda: subprocess.Popen('start chrome', shell=True),
    'OPEN_NOTEPAD': lambda: subprocess.Popen(['notepad.exe']),
}


def perform(command):
    """Run the PC action for a command. Returns True if it worked."""
    action = ACTIONS.get(command)
    if action is None:
        print(f'[ACTION] no action for "{command}"')
        return False
    try:
        action()
    except Exception as e:  # never let one failed action crash the whole program
        print(f'[ACTION] {command} failed: {e}')
        return False
    return True
