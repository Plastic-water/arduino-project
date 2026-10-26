"""TriSense face engine.

What it does (face mode):
  * Head = mouse.   Move your nose and the cursor follows (smoothed, NOT sent to Arduino).
  * CLICK           Open your mouth and hold ~0.1 s. One click per mouth-open (must close
                    the mouth again before the next click).
  * LOCK (eyes)     Keep both eyes closed for 2 s -> locks Windows.
  * LOCK (walk away) Leave the camera view for 10 s -> locks Windows.
                    Only arms after your face has been seen for 2 s, and fires once.

Why it is better than the pixel-distance version: it uses MediaPipe blendshapes
(jawOpen, eyeBlinkLeft/Right, 0.0 to 1.0), so it does not depend on how far you
sit from the camera or the webcam resolution.

Everything you might want to tune is in the TUNABLES block. The live values of
jaw/eyes are drawn on the video so you can pick thresholds by looking at them.

Test alone:  python face_engine.py     (prints [FACE] CLICK / [FACE] LOCK, never locks, ESC quits)
"""

import os
import time
import urllib.request

import cv2
import mediapipe as mp
import numpy as np
import pyautogui
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE, 'face_landmarker.task')
MODEL_URL = (
    'https://storage.googleapis.com/mediapipe-models/face_landmarker/'
    'face_landmarker/float16/1/face_landmarker.task'
)

# ---------------- TUNABLES ----------------
ENABLE_CURSOR = True  # head moves the mouse
ENABLE_CLICK = True  # mouth open = click
ENABLE_EYES_LOCK = True  # eyes closed 2 s = LOCK
ENABLE_AWAY_LOCK = True  # face gone 10 s = LOCK

COOLDOWN = 0.5  # seconds per command (contract rule 2)

JAW_ON = 0.45  # jawOpen above this = mouth "open"
JAW_OFF = 0.20  # must drop below this before the next click can happen
CLICK_HOLD = 0.10  # mouth must stay open this long (filters talking/yawning flicker)
JAW_FREEZE = 0.25  # cursor stops while the mouth is opening so the click lands where you aimed

EYES_CLOSED = 0.60  # eyeBlink score (both eyes) above this = closed
EYES_LOCK_SECONDS = 2.0  # normal blinks are ~0.2 s, so this is deliberate

AWAY_LOCK_SECONDS = 10.0  # no face for this long -> LOCK
AWAY_ARM_SECONDS = 2.0  # face must be seen this long first (prevents instant lock on entering mode)

CURSOR_BOX = (0.35, 0.65)  # part of the camera image that maps to the whole screen
CURSOR_SMOOTH = 0.30  # 0..1, lower = smoother but laggier
CURSOR_DEADZONE = 2  # pixels, ignore tiny jitters
EDGE_MARGIN = 6  # keep cursor off the screen corners (pyautogui fail-safe)
# ------------------------------------------


class FaceEngine:
    def __init__(self, on_command=None, on_error=None):
        self.on_command = on_command or (lambda c: print(f'[FACE] {c}', flush=True))
        self.on_error = on_error or (lambda r: print(f'[FACE] ERR:{r}', flush=True))
        self.status = ''  # short text main.py shows on the video

        if not os.path.exists(MODEL_PATH):
            print('Downloading MediaPipe face landmarker model...')
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
            num_faces=1,
            output_face_blendshapes=True,
            min_face_detection_confidence=0.7,
            min_face_presence_confidence=0.7,
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)
        self.screen_w, self.screen_h = pyautogui.size()
        self.reset()

    def reset(self):
        """Call whenever face mode is entered, so old timers don't fire."""
        self._last_cmd = {}
        self._armed = False
        self._face_since = None
        self._last_seen = time.time()
        self._jaw_since = None
        self._jaw_latched = False
        self._eyes_since = None
        self._eyes_latched = False
        self._cx = None
        self._cy = None

    # ---------- helpers ----------
    def _fire(self, cmd, now):
        if now - self._last_cmd.get(cmd, 0.0) < COOLDOWN:
            return
        self._last_cmd[cmd] = now
        self.on_command(cmd)

    def _move_cursor(self, nx, ny):
        lo, hi = CURSOR_BOX
        fx = float(np.clip((nx - lo) / (hi - lo), 0.0, 1.0))
        fy = float(np.clip((ny - lo) / (hi - lo), 0.0, 1.0))
        tx = fx * (self.screen_w - 1)
        ty = fy * (self.screen_h - 1)
        if self._cx is None:
            self._cx, self._cy = pyautogui.position()
        nxp = self._cx + (tx - self._cx) * CURSOR_SMOOTH
        nyp = self._cy + (ty - self._cy) * CURSOR_SMOOTH
        if abs(nxp - self._cx) < CURSOR_DEADZONE and abs(nyp - self._cy) < CURSOR_DEADZONE:
            return
        self._cx = float(np.clip(nxp, EDGE_MARGIN, self.screen_w - 1 - EDGE_MARGIN))
        self._cy = float(np.clip(nyp, EDGE_MARGIN, self.screen_h - 1 - EDGE_MARGIN))
        try:
            pyautogui.moveTo(int(self._cx), int(self._cy), _pause=False)
        except pyautogui.FailSafeException:
            pass

    # ---------- per frame ----------
    def process(self, frame):
        """frame = mirrored BGR webcam image. Draws debug info on it."""
        h, w = frame.shape[:2]
        now = time.time()
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        result = self.detector.detect(mp_image)

        if not result.face_landmarks:
            self._no_face(now)
            return

        # ---- face present ----
        self._last_seen = now
        if self._face_since is None:
            self._face_since = now
        if not self._armed and now - self._face_since >= AWAY_ARM_SECONDS:
            self._armed = True

        lm = result.face_landmarks[0]
        scores = {}
        if result.face_blendshapes:
            scores = {c.category_name: c.score for c in result.face_blendshapes[0]}
        jaw = scores.get('jawOpen', 0.0)
        eyes = min(scores.get('eyeBlinkLeft', 0.0), scores.get('eyeBlinkRight', 0.0))

        # CLICK: mouth open, held briefly, one click per open
        if ENABLE_CLICK:
            if jaw >= JAW_ON:
                if self._jaw_since is None:
                    self._jaw_since = now
                if not self._jaw_latched and now - self._jaw_since >= CLICK_HOLD:
                    self._jaw_latched = True
                    self._fire('CLICK', now)
            elif jaw <= JAW_OFF:
                self._jaw_since = None
                self._jaw_latched = False

        # LOCK: eyes held closed
        if ENABLE_EYES_LOCK:
            if eyes >= EYES_CLOSED:
                if self._eyes_since is None:
                    self._eyes_since = now
                if not self._eyes_latched and now - self._eyes_since >= EYES_LOCK_SECONDS:
                    self._eyes_latched = True
                    self._fire('LOCK', now)
            else:
                self._eyes_since = None
                self._eyes_latched = False

        # CURSOR: nose tip (landmark 1). Frozen while mouth opens or eyes close.
        nose = lm[1]
        if ENABLE_CURSOR and jaw < JAW_FREEZE and eyes < 0.5:
            self._move_cursor(nose.x, nose.y)

        # debug drawing
        cv2.circle(frame, (int(nose.x * w), int(nose.y * h)), 5, (0, 255, 255), -1)
        x0, x1 = int(CURSOR_BOX[0] * w), int(CURSOR_BOX[1] * w)
        y0, y1 = int(CURSOR_BOX[0] * h), int(CURSOR_BOX[1] * h)
        cv2.rectangle(frame, (x0, y0), (x1, y1), (255, 255, 0), 1)
        self.status = f'jaw {jaw:.2f}  eyes {eyes:.2f}'

    def _no_face(self, now):
        self._face_since = None
        self._jaw_since = None
        self._jaw_latched = False
        self._eyes_since = None
        self._eyes_latched = False
        if not (ENABLE_AWAY_LOCK and self._armed):
            self.status = 'no face'
            return
        gone = now - self._last_seen
        if gone >= AWAY_LOCK_SECONDS:
            self._armed = False  # fire once; re-arms after the face is seen again
            self.status = 'locked (away)'
            self._fire('LOCK', now)
        else:
            self.status = f'no face - lock in {AWAY_LOCK_SECONDS - gone:.0f}s'


if __name__ == '__main__':
    # Stand-alone test: prints commands, moves cursor, but never locks Windows.
    engine = FaceEngine()
    cap = cv2.VideoCapture(0)
    print('[FACE] engine started. Open mouth = CLICK. ESC to exit.')
    while cap.isOpened():
        ok, img = cap.read()
        if not ok:
            continue
        img = cv2.flip(img, 1)
        engine.process(img)
        cv2.putText(img, engine.status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.imshow('TriSense - Face Engine', img)
        if cv2.waitKey(5) & 0xFF == 27:
            break
    cap.release()
    cv2.destroyAllWindows()