"""TriSense serial bridge (Python <-> Arduino).

    link = ArduinoLink(on_button=..., on_ready=...)
    link.start()
    link.send('MODE', 'VOICE')     # -> "MODE:VOICE\n"
    link.send('CMD', 'VOLUP')
    link.send('ERR', 'NO_MIC')

Follows the message contract: 9600 baud, TYPE:VALUE, ALL CAPS, no spaces,
value max 12 chars, at most ~10 messages per second.

If no Arduino is found the program keeps working (the link just stays
offline and retries every few seconds, so you can plug it in later or
re-plug it if the cable wiggles).

Close the Arduino Serial Monitor before running: only one program can use
the COM port.
"""

import queue
import threading
import time

import serial
from serial.tools import list_ports

BAUD = 9600
MIN_INTERVAL = 0.1        # 10 messages per second max (contract rule 3)
READY_GRACE = 4.0         # if READY is missed, start sending anyway after this many seconds
RETRY_SECONDS = 3.0


def find_arduino_port():
    """Look for the CH340 clone chip. Ignores the laptop's internal ports (like COM3)."""
    for p in list_ports.comports():
        text = f'{p.description} {p.manufacturer or ""}'.upper()
        if 'CH340' in text or 'CH341' in text or 'ARDUINO' in text or 'USB-SERIAL' in text:
            return p.device
    return None


class ArduinoLink:
    def __init__(self, on_button=None, on_ready=None, port=None):
        self.on_button = on_button or (lambda: None)
        self.on_ready = on_ready or (lambda: None)
        self.port = port                  # e.g. 'COM6' to force a port, None = auto-detect
        self.connected = False
        self.ready = threading.Event()    # set when the Arduino says READY
        self._ser = None
        self._connected_at = 0.0
        self._out = queue.Queue(maxsize=50)
        self._stop = threading.Event()
        self._thread = None

    # ---------- public ----------
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._close()

    def send(self, msg_type, value=''):
        """Queue a message. Silently dropped while the Arduino is offline."""
        if not self.connected:
            return
        msg_type = str(msg_type).upper()
        value = str(value).upper().replace(' ', '_').replace(':', '_')[:12]
        line = f'{msg_type}:{value}\n' if value else f'{msg_type}\n'
        try:
            self._out.put_nowait(line)
        except queue.Full:
            print('[LINK] send queue full, message dropped', flush=True)

    # ---------- internals ----------
    def _close(self):
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        self.connected = False
        self.ready.clear()

    def _try_connect(self):
        port = self.port or find_arduino_port()
        if not port:
            return False
        try:
            self._ser = serial.Serial(port, BAUD, timeout=0.05)  # opening resets the Uno
        except (serial.SerialException, OSError) as e:
            print(f'[LINK] cannot open {port}: {e}  (is the Serial Monitor still open?)', flush=True)
            self._ser = None
            return False
        # drop anything queued while offline
        while not self._out.empty():
            try:
                self._out.get_nowait()
            except queue.Empty:
                break
        self.ready.clear()
        self._connected_at = time.time()
        self.connected = True
        print(f'[LINK] connected on {port}', flush=True)
        return True

    def _handle_line(self, line):
        if line == 'READY':
            self.ready.set()
            self.on_ready()
        elif line == 'BTN:PRESSED':
            self.on_button()
        else:
            print(f'[ARDUINO] {line}', flush=True)

    def _run(self):
        last_write = 0.0
        while not self._stop.is_set():
            if self._ser is None:
                if not self._try_connect():
                    self._stop.wait(RETRY_SECONDS)
                continue
            try:
                now = time.time()
                can_write = self.ready.is_set() or (now - self._connected_at) > READY_GRACE
                if can_write and now - last_write >= MIN_INTERVAL:
                    try:
                        line = self._out.get_nowait()
                        self._ser.write(line.encode('ascii'))
                        last_write = now
                    except queue.Empty:
                        pass
                raw = self._ser.readline()
                if raw:
                    text = raw.decode('ascii', errors='ignore').strip()
                    if text:
                        self._handle_line(text)
            except (serial.SerialException, OSError) as e:
                print(f'[LINK] lost connection: {e}', flush=True)
                self._close()
