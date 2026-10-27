"""TriSense main controller.

Run:  python main.py

  * Arduino button (or the M key in the camera window) cycles GESTURE -> VOICE -> FACE.
  * Only the active mode's engine can trigger PC actions.
  * Every successful command  -> Arduino  CMD:xxx   (LCD line 2 + LED flicker)
  * Every failure             -> Arduino  ERR:xxx   (red LED blinks, LCD shows it)
  * ESC in the camera window quits.

Threads: the camera loop runs here (main thread). Voice runs in its own thread
(voice_engine.py), and ArduinoLink has its own serial thread. Button presses
are put in a queue and handled by the camera loop, so there are no race conditions.
"""

import queue
import time

import cv2
import numpy as np

from actions import perform
from arduino_link import ArduinoLink
from face_engine import FaceEngine
from gesture_engine import GestureEngine

try:
    from voice_engine import VoiceEngine
except Exception as e:  # vosk / sounddevice not installed
    VoiceEngine = None
    print(f'[MAIN] voice_engine unavailable: {e}')

MODES = ['GESTURE', 'VOICE', 'FACE']
CAMERA_RETRY_SECONDS = 3.0

# After a command fires, the same command is ignored for this many seconds
# (all modes). Stops PLAYPAUSE / MUTE from re-triggering again and again.
SLOW_COOLDOWN = 5.0
# These may repeat quickly (volume sliding, clicking, scrolling, search steps).
FAST_COMMANDS = {
    'VOLUP', 'VOLDOWN', 'CLICK', 'SCROLLUP', 'SCROLLDOWN', 'ZOOMIN', 'ZOOMOUT',
    'LISTENING', 'SEARCH', 'SEARCH_YT',
}


def open_camera():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # DirectShow opens much faster on Windows
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(0)
    return cap if cap.isOpened() else None


class TriSense:
    def __init__(self):
        self.mode_idx = 0
        self.last_cmd = '---'
        self.events = queue.Queue()
        self.cam_ok = False
        self._last_fire = {}  # (command, value) -> time it last ran

        self.link = ArduinoLink(
            on_button=lambda: self.events.put('BTN'),
            on_ready=lambda: self.events.put('READY'),
        )

        self.gesture = self._make(GestureEngine, 'GESTURE')
        self.face = self._make(FaceEngine, 'FACE')
        self.voice = None
        if VoiceEngine is not None:
            self.voice = VoiceEngine(
                on_command=lambda c, a=None: self.emit('VOICE', c, a),
                on_error=self.error,
            )
            self.voice.enabled = False

    # ---------- helpers ----------
    @property
    def mode(self):
        return MODES[self.mode_idx]

    def _make(self, cls, source):
        try:
            return cls(on_command=lambda c: self.emit(source, c), on_error=self.error)
        except Exception as e:
            print(f'[MAIN] could not start {source} engine: {e}')
            return None

    def error(self, reason):
        print(f'[MAIN] ERR:{reason}', flush=True)
        self.link.send('ERR', reason)

    def emit(self, source, command, arg=None):
        """Called by the engines. Runs the PC action and tells the Arduino."""
        if source != self.mode:  # ignore engines that are not active
            return
        now = time.time()
        key = (command, arg)
        if command not in FAST_COMMANDS and now - self._last_fire.get(key, 0.0) < SLOW_COOLDOWN:
            return  # same command too soon: ignore
        self._last_fire[key] = now

        print(f'[{source}] {command}' + (f' ({arg})' if arg else ''), flush=True)
        if perform(command, arg):
            # what the LCD shows: OPEN_SITE + youtube -> OPEN_YOUTUBE (12 chars max)
            label = f'OPEN_{arg}' if command == 'OPEN_SITE' and arg else command
            self.last_cmd = label.upper()[:12]
            self.link.send('CMD', label)
        else:
            self.error('ACTION_FAIL')

    def set_mode(self, idx):
        self.mode_idx = idx % len(MODES)
        m = self.mode
        print(f'--- MODE: {m} ---', flush=True)
        if self.voice:
            self.voice.enabled = (m == 'VOICE')
        if self.gesture:
            self.gesture.reset()
        if self.face:
            self.face.reset()
        self.link.send('MODE', m)
        if m == 'VOICE' and self.voice is None:
            self.error('NO_VOICE')
        elif m == 'GESTURE' and self.gesture is None:
            self.error('NO_MODEL')
        elif m == 'FACE' and self.face is None:
            self.error('NO_MODEL')
        elif m in ('GESTURE', 'FACE') and not self.cam_ok:
            self.error('NO_CAM')

    # ---------- main loop ----------
    def run(self):
        self.link.start()
        if self.voice:
            self.voice.start()
        print(f'[MAIN] engines: gesture={"ok" if self.gesture else "FAILED"}  '
              f'face={"ok" if self.face else "FAILED"}  voice={"ok" if self.voice else "FAILED"}')
        print('[MAIN] looking for the Arduino (up to 5 s)...')
        if self.link.ready.wait(timeout=5.0):
            print('[MAIN] Arduino is ready.')
        else:
            print('[MAIN] Arduino not found. Running without it (use the M key to change mode).')

        cap = open_camera()
        self.cam_ok = cap is not None
        cam_err_sent = False
        next_cam_try = time.time() + CAMERA_RETRY_SECONDS
        self.set_mode(0)

        while True:
            # 1) events from the Arduino
            while True:
                try:
                    ev = self.events.get_nowait()
                except queue.Empty:
                    break
                if ev == 'BTN':
                    print('[MAIN] button pressed', flush=True)
                    self.set_mode(self.mode_idx + 1)
                elif ev == 'READY':  # Arduino (re)booted: tell it where we are
                    self.link.send('MODE', self.mode)

            # 2) camera (retry if missing)
            now = time.time()
            if cap is None and now >= next_cam_try:
                cap = open_camera()
                next_cam_try = now + CAMERA_RETRY_SECONDS
                self.cam_ok = cap is not None
                if self.cam_ok:
                    cam_err_sent = False
                    print('[MAIN] camera is back.')
                elif not cam_err_sent:
                    cam_err_sent = True
                    if self.mode in ('GESTURE', 'FACE'):
                        self.error('NO_CAM')

            frame = None
            if cap is not None:
                ok, img = cap.read()
                if ok:
                    frame = cv2.flip(img, 1)
                else:  # camera unplugged or taken by another app
                    cap.release()
                    cap = None
                    self.cam_ok = False
                    next_cam_try = now + CAMERA_RETRY_SECONDS
                    if not cam_err_sent:
                        cam_err_sent = True
                        if self.mode in ('GESTURE', 'FACE'):
                            self.error('NO_CAM')
            if frame is None:
                frame = np.zeros((480, 640, 3), np.uint8)
                cv2.putText(frame, 'NO CAMERA', (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            elif self.mode == 'GESTURE' and self.gesture:
                self.gesture.process(frame)
            elif self.mode == 'FACE' and self.face:
                self.face.process(frame)

            # 3) overlay + keys
            self._draw(frame)
            cv2.imshow('TriSense', frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
            if key in (ord('m'), ord('M')):
                self.set_mode(self.mode_idx + 1)

        # cleanup
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        if self.voice:
            self.voice.stop()
        self.link.stop()

    def _draw(self, frame):
        arduino = 'Arduino: OK' if self.link.connected else 'Arduino: not connected'
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 52), (30, 30, 30), -1)
        cv2.putText(frame, f'MODE: {self.mode}   Last: {self.last_cmd}', (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, arduino, (10, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        if self.mode == 'FACE' and self.face:
            cv2.putText(frame, self.face.status, (frame.shape[1] - 330, 44),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        if self.mode == 'VOICE':
            cv2.putText(frame, 'Say a command (e.g. "volume up")', (10, frame.shape[0] - 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, 'M = next mode   ESC = quit', (10, frame.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)


if __name__ == '__main__':
    print('TriSense starting. Button or M key = change mode, ESC = quit.')
    TriSense().run()
