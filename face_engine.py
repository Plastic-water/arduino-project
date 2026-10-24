import os
import time
import urllib.request
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np

# Automatically download the required face landmarker model if not present
model_path = 'face_landmarker.task'
if not os.path.exists(model_path):
  print('Downloading MediaPipe face landmarker model...')
  urllib.request.urlretrieve(
      'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
      model_path,
  )

# Initialize MediaPipe Tasks FaceLandmarker
base_options = python.BaseOptions(model_asset_path=model_path)
options = vision.FaceLandmarkerOptions(
    base_options=base_options,
    num_faces=1,
    min_face_detection_confidence=0.7,
    min_face_presence_confidence=0.7,
)
detector = vision.FaceLandmarker.create_from_options(options)

# Cooldown settings (Rule 2 of contract)
last_sent_time = 0
COOLDOWN = 0.5  # seconds

# Start webcam capture
cap = cv2.VideoCapture(0)
print(
    '[FACE] Modern Engine started. Open mouth slightly for CLICK. Press ESC to'
    ' exit.'
)

while cap.isOpened():
  success, image = cap.read()
  if not success:
    print('Ignoring empty camera frame.')
    continue

  # Flip image horizontally for a selfie-view experience
  image = cv2.flip(image, 1)
  h, w, _ = image.shape

  # Convert OpenCV BGR to MediaPipe Image format
  mp_image = mp.Image(
      image_format=mp.ImageFormat.SRGB,
      data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB),
  )

  # Process frame
  detection_result = detector.detect(mp_image)

  if detection_result.face_landmarks:
    for face_landmarks in detection_result.face_landmarks:
      # Upper lip tip (index 13) and lower lip tip (index 14)
      lip_top = np.array([face_landmarks[13].x * w, face_landmarks[13].y * h])
      lip_bottom = np.array([face_landmarks[14].x * w, face_landmarks[14].y * h])
      mouth_distance = np.linalg.norm(lip_top - lip_bottom)

      # Check if mouth is open past a certain threshold to trigger CLICK
      current_time = time.time()
      if mouth_distance > 18.0:
        if current_time - last_sent_time >= COOLDOWN:
          print('[FACE] CLICK')
          last_sent_time = current_time

  cv2.imshow('TriSense - Face Engine (Person A)', image)
  if cv2.waitKey(5) & 0xFF == 27:  # Press ESC to quit
    break

cap.release()
cv2.destroyAllWindows()