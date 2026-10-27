"""TriSense gesture engine.

Gestures: open palm = PLAYPAUSE, fist = MUTE, thumb+index touching = VOLDOWN,
wide thumb-index spread = VOLUP.
The camera loop lives in main.py so gesture and face can share one webcam.
With GESTURE_DEBUG on, the live finger count and thumb-index "gap" are drawn on
the video: use them to tune PINCH_CLOSE_RATIO.

Test alone:  python gesture_engine.py      (prints [GESTURE] COMMAND, ESC quits)
"""

import math
import os
import time
import urllib.request

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE, 'hand_landmarker.task')
MODEL_URL = (
    'https://storage.googleapis.com/mediapipe-models/hand_landmarker/'
    'hand_landmarker/float16/1/hand_landmarker.task'
)

COOLDOWN = 0.5  # seconds between any two gesture commands (contract rule 2)
PINCH_OPEN = 0.22  # thumb-index distance (fraction of image) above this = VOLUP (unchanged)

# --- VOLDOWN pinch vs MUTE fist ---
# gap = thumb-tip to index-tip distance divided by hand size (wrist to middle knuckle),
# so it does not change when you move closer to / further from the camera.
PINCH_CLOSE_RATIO = 0.28  # gap below this = fingertips touching = pinch (VOLDOWN)
FIST_AFTER_PINCH_GUARD = 1.0  # seconds: no MUTE right after a pinch (finger-shape flicker)
HOLD_FRAMES = {  # a gesture must be seen this many frames in a row before it counts
    'PLAYPAUSE': 4,
    'MUTE': 8,
    'VOLDOWN': 2,
    'VOLUP': 1,
}
ONE_SHOT = {'PLAYPAUSE', 'MUTE'}  # fire once per hold; volume keeps repeating while held
GESTURE_DEBUG = True  # draw the live numbers on the video so you can tune the values above


class GestureEngine:
    def __init__(self, on_command=None, on_error=None):
        self.on_command = on_command or (lambda c: print(f'[GESTURE] {c}', flush=True))
        self.on_error = on_error or (lambda r: print(f'[GESTURE] ERR:{r}', flush=True))

        if not os.path.exists(MODEL_PATH):
            print('Downloading MediaPipe hand landmarker model...')
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
            num_hands=1,
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.7,
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        self.reset()

    def reset(self):
        """Call when entering gesture mode."""
        self._last_sent = 0.0
        self._last_pinch_seen = 0.0
        self._cand = None
        self._n = 0
        self.debug = ''

    @staticmethod
    def _dist(a, b):
        return math.hypot(a.x - b.x, a.y - b.y)

    def _classify(self, lm, now):
        """Return the gesture name seen in this single frame (or None)."""
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        extended = sum(1 for t, p in zip(tips, pips) if lm[t].y < lm[p].y)

        thumb_tip, index_tip, thumb_ip = lm[4], lm[8], lm[3]
        pinch_abs = self._dist(thumb_tip, index_tip)
        hand_size = max(self._dist(lm[0], lm[9]), 1e-6)
        gap = pinch_abs / hand_size
        self.debug = f'fingers {extended}  gap {gap:.2f} (pinch<{PINCH_CLOSE_RATIO})'

        if extended == 4:
            return 'PLAYPAUSE'

        # pinch is checked BEFORE the fist: a pinch also has curled fingers
        if gap < PINCH_CLOSE_RATIO:
            self._last_pinch_seen = now
            return 'VOLDOWN'

        if extended == 0:
            if now - self._last_pinch_seen < FIST_AFTER_PINCH_GUARD:
                return None  # probably still coming out of / going into a pinch
            return 'MUTE'

        # wide thumb-index spread -> volume up (same rule as before)
        if pinch_abs > PINCH_OPEN:
            return 'VOLUP'

        # fallback: thumbs up / down
        if thumb_tip.y < thumb_ip.y and extended <= 1:
            return 'VOLUP'
        if thumb_tip.y > thumb_ip.y and extended <= 1:
            return 'VOLDOWN'
        return None

    def _stable(self, cand):
        """Count how many frames in a row the same gesture was seen.
        Returns the gesture when it should fire now, else None."""
        if cand == self._cand:
            self._n += 1
        else:
            self._cand = cand
            self._n = 1
        if cand is None:
            return None
        need = HOLD_FRAMES.get(cand, 1)
        if cand in ONE_SHOT:
            return cand if self._n == need else None  # exactly once per hold
        return cand if self._n >= need else None

    def process(self, frame):
        """frame = mirrored BGR image from the webcam. Draws hand dots on it."""
        h, w = frame.shape[:2]
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        result = self.detector.detect(mp_image)
        if not result.hand_landmarks:
            self._stable(None)  # hand left the picture: next gesture starts fresh
            self.debug = 'no hand'
            return
        now = time.time()
        for lm in result.hand_landmarks:
            for p in lm:
                cv2.circle(frame, (int(p.x * w), int(p.y * h)), 3, (0, 255, 0), -1)
            cmd = self._stable(self._classify(lm, now))
            if cmd and now - self._last_sent >= COOLDOWN:
                self._last_sent = now
                self.on_command(cmd)
            if GESTURE_DEBUG:
                shown = self._cand or '-'
                cv2.putText(frame, f'{self.debug}  -> {shown}', (10, 78),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)


if __name__ == '__main__':
    engine = GestureEngine()
    cap = cv2.VideoCapture(0)
    print('[GESTURE] engine started. Show your hand. ESC to exit.')
    while cap.isOpened():
        ok, img = cap.read()
        if not ok:
            continue
        img = cv2.flip(img, 1)
        engine.process(img)
        cv2.imshow('TriSense - Gesture Engine', img)
        if cv2.waitKey(5) & 0xFF == 27:
            break
    cap.release()
    cv2.destroyAllWindows()
