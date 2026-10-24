import os
import time
import urllib.request
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np

# Automatically download the required hand landmarker model if not present
model_path = 'hand_landmarker.task'
if not os.path.exists(model_path):
  print('Downloading MediaPipe hand landmarker model...')
  urllib.request.urlretrieve(
      'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
      model_path,
  )

# Initialize MediaPipe Tasks HandLandmarker
base_options = python.BaseOptions(model_asset_path=model_path)
options = vision.HandLandmarkerOptions(
    base_options=base_options,
    num_hands=1,
    min_hand_detection_confidence=0.7,
    min_hand_presence_confidence=0.7,
)
detector = vision.HandLandmarker.create_from_options(options)

# Cooldown and pinch tracking settings
last_sent_time = 0
COOLDOWN = 0.5  # seconds
last_pinch_time = 0
PINCH_COOLDOWN = 0.2  # Faster response for smooth sliding


def detect_gesture(hand_landmarks):
  global last_pinch_time

  tips = [8, 12, 16, 20]
  pips = [6, 10, 14, 18]

  # Count extended fingers
  extended_fingers = sum(
      1 for t, p in zip(tips, pips) if hand_landmarks[t].y < hand_landmarks[p].y
  )

  thumb_tip = hand_landmarks[4]
  index_tip = hand_landmarks[8]
  thumb_ip = hand_landmarks[3]

  # 1. Calculate 2D distance (x and y only) between thumb tip and index tip
  pinch_distance = np.sqrt(
      (thumb_tip.x - index_tip.x) ** 2 + (thumb_tip.y - index_tip.y) ** 2
  )

  # 2. Discrete Postures (Play/Pause, Mute)
  if extended_fingers == 4:
    return 'PLAYPAUSE'
  elif extended_fingers == 0:
    return 'MUTE'

  # 3. Continuous Pinch Mapping (Relaxed threshold for easier triggering)
  current_time = time.time()
  if current_time - last_pinch_time >= PINCH_COOLDOWN:
    if pinch_distance < 0.08:  # Relaxed from 0.05 to 0.08 (easier pinch close)
      last_pinch_time = current_time
      return 'VOLDOWN'
    elif pinch_distance > 0.22:  # Spread wide apart
      last_pinch_time = current_time
      return 'VOLUP'

  # Fallback legacy thumbs up/down if not pinching
  if thumb_tip.y < thumb_ip.y and extended_fingers <= 1:
    return 'VOLUP'
  elif thumb_tip.y > thumb_ip.y and extended_fingers <= 1:
    return 'VOLDOWN'

  return None
  # global last_pinch_time

  # tips = [8, 12, 16, 20]
  # pips = [6, 10, 14, 18]

  # # Count extended fingers
  # extended_fingers = sum(
  #     1 for t, p in zip(tips, pips) if hand_landmarks[t].y < hand_landmarks[p].y
  # )

  # thumb_tip = hand_landmarks[4]
  # index_tip = hand_landmarks[8]
  # thumb_ip = hand_landmarks[3]

  # # 1. Calculate distance between thumb tip and index tip for pinch actions
  # pinch_distance = np.sqrt(
  #     (thumb_tip.x - index_tip.x) ** 2
  #     + (thumb_tip.y - index_tip.y) ** 2
  #     + (thumb_tip.z - index_tip.z) ** 2
  # )

  # # 2. Discrete Postures (Play/Pause, Mute)
  # if extended_fingers == 4:
  #   return 'PLAYPAUSE'
  # elif extended_fingers == 0:
  #   return 'MUTE'

  # # 3. Continuous Pinch Mapping (Pinch close = VOLDOWN, Spread wide = VOLUP)
  # current_time = time.time()
  # if current_time - last_pinch_time >= PINCH_COOLDOWN:
  #   if pinch_distance < 0.05:  # Fingers pinched tight together
  #     last_pinch_time = current_time
  #     return 'VOLDOWN'
  #   elif pinch_distance > 0.20:  # Fingers spread wide apart
  #     last_pinch_time = current_time
  #     return 'VOLUP'

  # # Fallback legacy thumbs up/down if not pinching
  # if thumb_tip.y < thumb_ip.y and extended_fingers <= 1:
  #   return 'VOLUP'
  # elif thumb_tip.y > thumb_ip.y and extended_fingers <= 1:
  #   return 'VOLDOWN'

  # return None


# Start webcam capture
cap = cv2.VideoCapture(0)
print(
    '[GESTURE] Pinch-Enabled Engine started. Show hand to webcam. Press ESC to'
    ' exit.'
)

while cap.isOpened():
  success, image = cap.read()
  if not success:
    print('Ignoring empty camera frame.')
    continue

  # Flip image horizontally for a selfie-view experience
  image = cv2.flip(image, 1)

  # Convert OpenCV BGR to MediaPipe Image format
  mp_image = mp.Image(
      image_format=mp.ImageFormat.SRGB,
      data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB),
  )

  # Process frame
  detection_result = detector.detect(mp_image)

  if detection_result.hand_landmarks:
    for hand_landmarks in detection_result.hand_landmarks:
      cmd = detect_gesture(hand_landmarks)

      if cmd:
        current_time = time.time()
        if current_time - last_sent_time >= COOLDOWN:
          print(f'[GESTURE] {cmd}')
          last_sent_time = current_time

  cv2.imshow('TriSense - Gesture Engine (Person A)', image)
  if cv2.waitKey(5) & 0xFF == 27:  # Press ESC to quit
    break

cap.release()
cv2.destroyAllWindows()


# import os
# import time
# import urllib.request
# import cv2
# import mediapipe as mp
# from mediapipe.tasks import python
# from mediapipe.tasks.python import vision

# # Automatically download the required hand landmarker model if not present
# model_path = 'hand_landmarker.task'
# if not os.path.exists(model_path):
#   print('Downloading MediaPipe hand landmarker model...')
#   urllib.request.urlretrieve(
#       'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
#       model_path,
#   )

# # Initialize MediaPipe Tasks HandLandmarker
# base_options = python.BaseOptions(model_asset_path=model_path)
# options = vision.HandLandmarkerOptions(
#     base_options=base_options,
#     num_hands=1,
#     min_hand_detection_confidence=0.7,
#     min_hand_presence_confidence=0.7,
# )
# detector = vision.HandLandmarker.create_from_options(options)

# # Cooldown settings (Rule 2 of contract)
# last_sent_time = 0
# COOLDOWN = 0.5  # seconds


# def detect_gesture(hand_landmarks):
#   """Simple logic to map hand posture to official command names."""
#   tips = [8, 12, 16, 20]
#   pips = [6, 10, 14, 18]

#   # Count extended fingers
#   extended_fingers = sum(
#       1 for t, p in zip(tips, pips) if hand_landmarks[t].y < hand_landmarks[p].y
#   )

#   thumb_tip = hand_landmarks[4]
#   thumb_ip = hand_landmarks[3]

#   # Map postures to commands
#   if extended_fingers == 4:
#     return 'PLAYPAUSE'
#   elif extended_fingers == 0:
#     return 'MUTE'
#   elif thumb_tip.y < thumb_ip.y and extended_fingers <= 1:
#     return 'VOLUP'
#   elif thumb_tip.y > thumb_ip.y and extended_fingers <= 1:
#     return 'VOLDOWN'

#   return None


# # Start webcam capture
# cap = cv2.VideoCapture(0)
# print(
#     '[GESTURE] Modern Engine started. Show hand to webcam. Press ESC to exit.'
# )

# while cap.isOpened():
#   success, image = cap.read()
#   if not success:
#     print('Ignoring empty camera frame.')
#     continue

#   # Flip image horizontally for a selfie-view experience
#   image = cv2.flip(image, 1)

#   # Convert OpenCV BGR to MediaPipe Image format
#   mp_image = mp.Image(
#       image_format=mp.ImageFormat.SRGB,
#       data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB),
#   )

#   # Process frame
#   detection_result = detector.detect(mp_image)

#   if detection_result.hand_landmarks:
#     for hand_landmarks in detection_result.hand_landmarks:
#       cmd = detect_gesture(hand_landmarks)

#       if cmd:
#         current_time = time.time()
#         if current_time - last_sent_time >= COOLDOWN:
#           print(f'[GESTURE] {cmd}')
#           last_sent_time = current_time

#   cv2.imshow('TriSense - Gesture Engine (Person A)', image)
#   if cv2.waitKey(5) & 0xFF == 27:  # Press ESC to quit
#     break

# cap.release()
# cv2.destroyAllWindows()