"""Minimal TriSense controller: gesture -> real PC action.

Run:  python main.py        (ESC in the camera window to quit)
Later the voice and face modules and the Arduino link plug into emit() here.
"""
from actions import perform
from gesture_engine import run


def emit(source, command):
    print(f'[{source}] {command}')
    perform(command)


if __name__ == '__main__':
    print('TriSense running. Gestures now control the PC. ESC to quit.')
    run(emit)