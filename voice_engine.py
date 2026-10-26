import json, queue, time, threading, os
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel

BASE        = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH  = os.path.join(BASE, "models", "vosk-model-small-en-us-0.15")
SAMPLE_RATE = 16000
DEVICE      = None      # None = default mic (device 1 on your laptop)
COOLDOWN    = 0.5       # seconds per command (from the contract)
DEBUG       = True      # prints what was heard

# command name (from the contract) -> phrases that trigger it
COMMANDS = {
    "VOLUP":        ["volume up", "louder"],
    "VOLDOWN":      ["volume down", "quieter"],
    "MUTE":         ["mute"],
    "PLAYPAUSE":    ["play", "pause", "play music", "pause music"],
    "NEXT":         ["next", "next song"],
    "PREV":         ["previous", "previous song"],
    "SCROLLUP":     ["scroll up"],
    "SCROLLDOWN":   ["scroll down"],
    "ZOOMIN":       ["zoom in"],
    "ZOOMOUT":      ["zoom out"],
    "OPEN_CHROME":  ["open chrome"],
    "OPEN_NOTEPAD": ["open notepad"],
    "SCREENSHOT":   ["screenshot", "take screenshot"],
    "LOCK":         ["lock screen", "lock computer"],
    "CLICK":        ["click"],
}
LOOKUP = {p: cmd for cmd, phrases in COMMANDS.items() for p in phrases}


class VoiceEngine:
    def __init__(self, on_command=None, on_error=None, device=DEVICE):
        self.on_command = on_command or (lambda c: print(f"[VOICE] {c}", flush=True))
        self.on_error   = on_error   or (lambda r: print(f"[VOICE] ERR:{r}", flush=True))
        self.device  = device
        self.enabled = True          # main controller sets False when mode != VOICE
        self._stop   = threading.Event()
        self._q      = queue.Queue()
        self._last   = {}
        self._thread = None

    def _audio_cb(self, indata, frames, time_info, status):
        self._q.put(bytes(indata))

    def _handle(self, text):
        if DEBUG and text:
            print(f"   (heard: '{text}')", flush=True)
        cmd = LOOKUP.get(text)
        if not cmd:
            return
        now = time.time()
        if now - self._last.get(cmd, 0) < COOLDOWN:
            return
        self._last[cmd] = now
        self.on_command(cmd)

    def _run(self):
        try:
            SetLogLevel(-1)
            model = Model(MODEL_PATH)
        except Exception as e:
            print("Model error:", e)
            self.on_error("NO_MODEL")
            return
        try:
            grammar = json.dumps(list(LOOKUP) + ["[unk]"])
            rec = KaldiRecognizer(model, SAMPLE_RATE, grammar)
            print("Voice engine ready. Say a command.", flush=True)
            with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000,
                                   device=self.device, dtype="int16",
                                   channels=1, callback=self._audio_cb):
                while not self._stop.is_set():
                    try:
                        data = self._q.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if rec.AcceptWaveform(data):
                        text = json.loads(rec.Result()).get("text", "")
                        if self.enabled:
                            self._handle(text)
        except Exception as e:
            print("Mic error:", e)
            self.on_error("NO_MIC")

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()


if __name__ == "__main__":
    engine = VoiceEngine()
    engine.start()
    print("Loading... (Ctrl+C to quit)")
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        engine.stop()