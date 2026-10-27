"""TriSense voice engine (your friend's engine + site opening and spoken search).

NEW (marked "NEW" below):
  "open youtube" / "open google" / "open gmail" ...   -> OPEN_SITE  (value = site name)
  "search"  (beep)  then say what to look for          -> SEARCH     (Google)
  "search youtube"  (beep)  then say the query         -> SEARCH_YT  (YouTube results)

How the search works: the normal recogniser only knows a fixed list of phrases,
so it cannot understand a random query. When it hears a search trigger it plays
a beep (LISTENING) and switches to a full-vocabulary recogniser for ONE sentence
(up to DICTATION_TIMEOUT seconds), then goes back to normal.

on_command is called as  on_command("VOLUP")  or, for the new commands,
on_command("SEARCH", "cute cats").  Test alone: python voice_engine.py
"""

import json
import os
import queue
import threading
import time

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE, "models", "vosk-model-small-en-us-0.15")
SAMPLE_RATE = 16000
DEVICE = None  # None = default mic
COOLDOWN = 0.5  # seconds per command (from the contract)
DEBUG = True  # prints what was heard
DICTATION_TIMEOUT = 8.0  # NEW: seconds you get to say the search words

# command name (from the contract) -> phrases that trigger it
COMMANDS = {
    "VOLUP": ["volume up", "louder"],
    "VOLDOWN": ["volume down", "quieter"],
    "MUTE": ["mute"],
    "PLAYPAUSE": ["play", "pause", "play music", "pause music"],
    "NEXT": ["next", "next song"],
    "PREV": ["previous", "previous song"],
    "SCROLLUP": ["scroll up"],
    "SCROLLDOWN": ["scroll down"],
    "ZOOMIN": ["zoom in"],
    "ZOOMOUT": ["zoom out"],
    "OPEN_CHROME": ["open chrome"],
    "OPEN_NOTEPAD": ["open notepad"],
    "SCREENSHOT": ["screenshot", "take screenshot"],
    "LOCK": ["lock screen", "lock computer"],
    "CLICK": ["click"],
}
LOOKUP = {p: cmd for cmd, phrases in COMMANDS.items() for p in phrases}

# NEW: "open <site>" -> site key used by actions.SITES.
# Several spellings per site, because the small Vosk model may not know a word
# like "youtube". Unknown words are simply ignored, the other spelling still works.
SITE_PHRASES = {
    "open youtube": "youtube",
    "open you tube": "youtube",
    "open google": "google",
    "open gmail": "gmail",
    "open g mail": "gmail",
    "open github": "github",
    "open git hub": "github",
    "open whatsapp": "whatsapp",
    "open whats app": "whatsapp",
    "open maps": "maps",
}

# NEW: trigger phrase -> command that will receive the spoken query
SEARCH_TRIGGERS = {
    "search": "SEARCH",
    "search google": "SEARCH",
    "google search": "SEARCH",
    "search youtube": "SEARCH_YT",
    "search you tube": "SEARCH_YT",
    "youtube search": "SEARCH_YT",
}

GRAMMAR_PHRASES = list(LOOKUP) + list(SITE_PHRASES) + list(SEARCH_TRIGGERS)


class VoiceEngine:
    def __init__(self, on_command=None, on_error=None, device=DEVICE):
        self.on_command = on_command or (lambda c, a=None: print(f"[VOICE] {c}" + (f" ({a})" if a else ""), flush=True))
        self.on_error = on_error or (lambda r: print(f"[VOICE] ERR:{r}", flush=True))
        self.device = device
        self.enabled = True  # main controller sets False when mode != VOICE
        self._stop = threading.Event()
        self._q = queue.Queue()
        self._last = {}
        self._thread = None
        self._model = None
        self._dict = None  # NEW: active search-dictation state, or None

    def _audio_cb(self, indata, frames, time_info, status):
        self._q.put(bytes(indata))

    # ---------- sending ----------
    def _emit(self, cmd, arg=None):
        now = time.time()
        key = (cmd, arg)
        if now - self._last.get(key, 0) < COOLDOWN:
            return
        self._last[key] = now
        if arg is None:
            self.on_command(cmd)
        else:
            self.on_command(cmd, arg)

    # ---------- normal command recognition ----------
    def _handle(self, text):
        if DEBUG and text:
            print(f"  (heard: '{text}')", flush=True)
        if text in SEARCH_TRIGGERS:  # NEW
            self._begin_dictation(SEARCH_TRIGGERS[text])
            return
        if text in SITE_PHRASES:  # NEW
            self._emit("OPEN_SITE", SITE_PHRASES[text])
            return
        cmd = LOOKUP.get(text)
        if cmd:
            self._emit(cmd)

    # ---------- NEW: one-sentence free dictation for searches ----------
    def _begin_dictation(self, cmd):
        self._emit("LISTENING")  # beep + LCD "Last: LISTENING"
        while True:  # throw away audio recorded during the beep
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        self._dict = {
            "cmd": cmd,
            "rec": KaldiRecognizer(self._model, SAMPLE_RATE),  # no grammar = any words
            "deadline": time.time() + DICTATION_TIMEOUT,
        }
        if DEBUG:
            print("  (listening for your search, speak now...)", flush=True)

    def _feed_dictation(self, data):
        d = self._dict
        if d["rec"].AcceptWaveform(data):
            text = json.loads(d["rec"].Result()).get("text", "")
            self._finish_dictation(text)
        elif time.time() > d["deadline"]:
            text = json.loads(d["rec"].FinalResult()).get("text", "")
            self._finish_dictation(text)

    def _finish_dictation(self, text):
        cmd = self._dict["cmd"]
        self._dict = None
        text = text.strip()
        if DEBUG:
            print(f"  (search words: '{text}')", flush=True)
        if not self.enabled:
            return
        if not text:
            self.on_error("NO_SPEECH")
            return
        self._emit(cmd, text)

    # ---------- main loop ----------
    def _run(self):
        try:
            SetLogLevel(-1)
            model = Model(MODEL_PATH)
            self._model = model
        except Exception as e:
            print("Model error:", e)
            self.on_error("NO_MODEL")
            return

        try:
            grammar = json.dumps(GRAMMAR_PHRASES + ["[unk]"])
            rec = KaldiRecognizer(model, SAMPLE_RATE, grammar)
            print("Voice engine ready. Say a command.", flush=True)
            with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=4000,
                                   device=self.device, dtype="int16",
                                   channels=1, callback=self._audio_cb):
                while not self._stop.is_set():
                    if self._dict and not self.enabled:  # left voice mode mid-search
                        self._dict = None
                    try:
                        data = self._q.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if self._dict:  # NEW: collecting the search words
                        self._feed_dictation(data)
                        if self._dict is None:
                            try:
                                rec.Reset()  # forget anything half-heard before the search
                            except Exception:
                                pass
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
