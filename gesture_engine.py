"""TriSense gesture engine (class version of your pinch engine).

Same detection logic as before. The only change is the structure: the camera
loop now lives in main.py so gesture and face can share one webcam.

Test alone:  python gesture_engine.py      (prints [GESTURE] COMMAND, ESC quits)
"""

import os
import time
import urllib.request

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE, 'hand_landmarker.task')
MODEL_URL = (
    'https://storage.googleapis.com/mediapipe-models/hand_landmarker/'
    'hand_landmarker/float16/1/hand_landmarker.task'
)

COOLDOWN = 0.5  # seconds between any two gesture commands (contract rule 2)
PINCH_COOLDOWN = 0.2  # faster repeat for smooth volume sliding
PINCH_CLOSE = 0.08  # thumb-index distance (fraction of image) below this = VOLDOWN
PINCH_OPEN = 0.22  # above this = VOLUP


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
        self._last_pinch = 0.0

    def _detect_gesture(self, lm):
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        extended = sum(1 for t, p in zip(tips, pips) if lm[t].y < lm[p].y)

        thumb_tip, index_tip, thumb_ip = lm[4], lm[8], lm[3]
        pinch = np.sqrt((thumb_tip.x - index_tip.x) ** 2 + (thumb_tip.y - index_tip.y) ** 2)

        # discrete postures
        if extended == 4:
            return 'PLAYPAUSE'
        if extended == 0:
            return 'MUTE'

        # continuous pinch -> volume
        now = time.time()
        if now - self._last_pinch >= PINCH_COOLDOWN:
            if pinch < PINCH_CLOSE:
                self._last_pinch = now
                return 'VOLDOWN'
            if pinch > PINCH_OPEN:
                self._last_pinch = now
                return 'VOLUP'

        # fallback: thumbs up / down
        if thumb_tip.y < thumb_ip.y and extended <= 1:
            return 'VOLUP'
        if thumb_tip.y > thumb_ip.y and extended <= 1:
            return 'VOLDOWN'
        return None

    def process(self, frame):
        """frame = mirrored BGR image from the webcam. Draws hand dots on it."""
        h, w = frame.shape[:2]
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        result = self.detector.detect(mp_image)
        if not result.hand_landmarks:
            return
        for lm in result.hand_landmarks:
            for p in lm:
                cv2.circle(frame, (int(p.x * w), int(p.y * h)), 3, (0, 255, 0), -1)
            cmd = self._detect_gesture(lm)
            if cmd:
                now = time.time()
                if now - self._last_sent >= COOLDOWN:
                    self._last_sent = now
                    self.on_command(cmd)


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




# """TriSense gesture engine (Person A).

# Detects hand gestures with MediaPipe and reports them as official command names.

#   Test alone :  python gesture_engine.py          (prints "[GESTURE] <COMMAND>")
#   From main  :  from gesture_engine import run ;  run(emit, stop_event)
#                 emit(source, command) is called like emit("GESTURE", "VOLUP")

# Gestures
#   Open palm (4 fingers up), hold still  -> PLAYPAUSE   (once per hold)
#   Fist, hold still                      -> MUTE        (once per hold)
#   Thumbs up / thumbs down (fist)        -> VOLUP / VOLDOWN   (repeats while held)
#   Pinch thumb+index, other fingers out  -> VOLDOWN     (repeats while held)
#   Thumb spread far from index (L shape) -> VOLUP       (repeats while held)
#   Swipe with TWO fingers (index+middle up, ring+pinky down) right / left
#                                         -> NEXT / PREV
# """
# import math
# import os
# import time
# import urllib.request
# from collections import deque

# MODEL_PATH = 'hand_landmarker.task'
# MODEL_URL = (
#     'https://storage.googleapis.com/mediapipe-models/hand_landmarker/'
#     'hand_landmarker/float16/1/hand_landmarker.task'
# )

# # ---------------- Tunables (change these while testing) ----------------
# HOLD_TIME = 0.25        # s a posture must be held before it fires
# REPEAT_INTERVAL = 0.5   # s between repeats for volume gestures
# PINCH_CLOSE = 0.35      # pinch distance / hand size below this = pinched
# PINCH_WIDE = 1.0        # pinch distance / hand size above this = spread
# THUMB_MARGIN = 0.4      # how far the thumb must point up/down (x hand size)
# STILL_LIMIT = 0.10      # hand moving more than this (frame fraction) = not a posture
# SWIPE_WINDOW = 0.5      # s of movement history used for swipes
# SWIPE_MIN_DIST = 0.2   # frame-width fraction the hand must travel
# SWIPE_MIN_TIME = 0.08   # s, ignore jumps shorter than this (tracking glitches)
# SWIPE_LOCKOUT = 1.0     # s of silence after a swipe (stops the return motion firing)

# TIPS = [8, 12, 16, 20]
# PIPS = [6, 10, 14, 18]


# def _dist(a, b):
#     return math.hypot(a.x - b.x, a.y - b.y)


# class GestureEngine:
#     """Turns one hand's 21 landmarks per frame into at most one command."""

#     def __init__(self):
#         self.history = deque()
#         self.posture = None
#         self.next_fire = float('inf')
#         self.lock_until = 0.0
#         self.blocked = None      # posture to ignore until the hand changes
#         self.debug = {}

#     def reset(self):
#         """Call when no hand is visible."""
#         self.history.clear()
#         self.posture = None
#         self.next_fire = float('inf')
#         self.blocked = None

#     def update(self, lm, now):
#         wrist = lm[0]
#         hand_size = max(_dist(wrist, lm[9]), 1e-6)   # wrist -> middle knuckle

#         # A finger is "extended" if its tip is farther from the wrist than its
#         # middle joint. This works even when the hand is tilted.
#         ext = [_dist(wrist, lm[t]) > _dist(wrist, lm[p]) for t, p in zip(TIPS, PIPS)]
#         n = sum(ext)
#         two_fingers = ext == [True, True, False, False]   # peace-sign pose = swipe pose
#         ratio = _dist(lm[4], lm[8]) / hand_size      # pinch size, independent of camera distance
#         self.debug = {'fingers': n, 'pinch': round(ratio, 2)}

#         # Wrist movement history, for swipes and "is the hand still?"
#         self.history.append((now, wrist.x, wrist.y))
#         while self.history and now - self.history[0][0] > SWIPE_WINDOW:
#             self.history.popleft()
#         t0, x0, y0 = self.history[0]
#         dx, dy = wrist.x - x0, wrist.y - y0
#         moved = math.hypot(dx, dy)

#         if now < self.lock_until:
#             self.posture = None
#             return None

#         # ---- Swipe: two-finger hand travels far and mostly sideways, quickly ----
#         if (two_fingers and now - t0 >= SWIPE_MIN_TIME
#                 and abs(dx) >= SWIPE_MIN_DIST and abs(dy) <= 0.6 * abs(dx)):
#             self.history.clear()
#             self.posture = None
#             self.lock_until = now + SWIPE_LOCKOUT
#             return 'NEXT' if dx > 0 else 'PREV'

#         # ---- Static postures ----
#         if two_fingers:
#             cand, repeat = None, False      # swipe-ready pose: no static action
#         elif n == 4:
#             cand, repeat = 'PLAYPAUSE', False
#         elif n == 0:
#             thumb_dy = (lm[4].y - lm[2].y) / hand_size   # negative = thumb points up
#             if thumb_dy < -THUMB_MARGIN:
#                 cand, repeat = 'VOLUP', True
#             elif thumb_dy > THUMB_MARGIN:
#                 cand, repeat = 'VOLDOWN', True
#             else:
#                 cand, repeat = 'MUTE', False
#         else:
#             if ratio < PINCH_CLOSE:
#                 cand, repeat = 'VOLDOWN', True
#             elif ratio > PINCH_WIDE:
#                 cand, repeat = 'VOLUP', True
#             else:
#                 cand, repeat = None, False

#         if cand != self.blocked:
#             self.blocked = None
#         if cand is None or cand == self.blocked:
#             self.posture = None
#             return None
#         if not repeat and moved > STILL_LIMIT:
#             self.posture = None          # hand is travelling, not posing
#             return None

#         if cand != self.posture:         # new posture: start the hold timer
#             self.posture = cand
#             self.next_fire = now + HOLD_TIME
#             return None
#         if now >= self.next_fire:
#             self.next_fire = now + REPEAT_INTERVAL if repeat else float('inf')
#             return cand
#         return None


# def run(emit, stop_event=None, show_preview=True, camera_index=0):
#     """Open the webcam and call emit('GESTURE', command) for every gesture."""
#     # Heavy imports live here so GestureEngine can be tested without a camera.
#     import cv2
#     import mediapipe as mp
#     from mediapipe.tasks import python
#     from mediapipe.tasks.python import vision

#     if not os.path.exists(MODEL_PATH):
#         print('Downloading MediaPipe hand landmarker model...')
#         urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

#     detector = vision.HandLandmarker.create_from_options(
#         vision.HandLandmarkerOptions(
#             base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
#             num_hands=1,
#             min_hand_detection_confidence=0.7,
#             min_hand_presence_confidence=0.7,
#         )
#     )
#     cap = cv2.VideoCapture(camera_index)
#     if not cap.isOpened():
#         emit('GESTURE', 'ERR_NO_CAM')
#         return

#     engine = GestureEngine()
#     failures = 0
#     last_cmd, last_cmd_time = '', 0.0
#     try:
#         while not (stop_event is not None and stop_event.is_set()):
#             ok, image = cap.read()
#             if not ok:
#                 failures += 1
#                 if failures > 30:
#                     emit('GESTURE', 'ERR_NO_CAM')
#                     break
#                 time.sleep(0.05)
#                 continue
#             failures = 0

#             image = cv2.flip(image, 1)   # mirror view; swipe right = hand moves right on screen
#             mp_image = mp.Image(
#                 image_format=mp.ImageFormat.SRGB,
#                 data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB),
#             )
#             result = detector.detect(mp_image)

#             if result.hand_landmarks:
#                 cmd = engine.update(result.hand_landmarks[0], time.time())
#             else:
#                 engine.reset()
#                 cmd = None
#             if cmd:
#                 emit('GESTURE', cmd)
#                 last_cmd, last_cmd_time = cmd, time.time()

#             if show_preview:
#                 info = engine.debug
#                 cv2.putText(image, f"fingers={info.get('fingers', '-')}  pinch={info.get('pinch', '-')}",
#                             (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
#                 if time.time() - last_cmd_time < 1.0:
#                     cv2.putText(image, last_cmd, (10, 70),
#                                 cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 255), 3)
#                 cv2.imshow('TriSense - Gesture Engine', image)
#                 if cv2.waitKey(1) & 0xFF == 27:   # ESC
#                     break
#     finally:
#         cap.release()
#         cv2.destroyAllWindows()
#         detector.close()


# if __name__ == '__main__':
#     def _print_emit(source, command):
#         print(f'[{source}] {command}')

#     print('[GESTURE] Engine started. Show your hand to the webcam. ESC to exit.')
#     run(_print_emit)