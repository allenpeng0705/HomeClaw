#!/usr/bin/env python3
"""
Vosk microphone listener for HomeClaw voice on Linux.
Prints one JSON object per line to stdout: {"partial": "..."} or {"final": "..."}.
Stops when stdin closes or on SIGTERM.

Usage:
  python3 vosk_listen.py --model /path/to/vosk-model
  VOSK_MODEL=/path/to/model python3 vosk_listen.py

Requires: pip install vosk sounddevice
"""
import argparse
import json
import queue
import sys
import signal

try:
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer
except ImportError as e:
    sys.stderr.write("Missing dependency: %s\n" % e)
    sys.stderr.write("Install with: pip install vosk sounddevice\n")
    sys.exit(1)

SAMPLE_RATE = 16000
BLOCK_SIZE = 4000
q = queue.Queue()
shutdown = False


def callback(indata, frames, time, status):
    if status:
        sys.stderr.write("%s\n" % status)
    if not shutdown:
        q.put(bytes(indata))


def main():
    global shutdown
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Path to Vosk model dir (or set VOSK_MODEL)",
    )
    args = parser.parse_args()
    model_path = args.model or __import__("os").environ.get("VOSK_MODEL")
    if not model_path:
        sys.stderr.write("Set VOSK_MODEL or pass --model /path/to/model\n")
        sys.exit(1)
    model_path = __import__("os").path.expanduser(model_path)

    def on_sigterm(*_):
        global shutdown
        shutdown = True

    signal.signal(signal.SIGTERM, on_sigterm)
    signal.signal(signal.SIGINT, on_sigterm)

    model = Model(model_path)
    rec = KaldiRecognizer(model, SAMPLE_RATE)
    rec.SetPartialWords(True)

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        dtype="int16",
        channels=1,
        callback=callback,
    ):
        while not shutdown:
            try:
                data = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = (result.get("text") or "").strip()
                if text:
                    print(json.dumps({"final": text}), flush=True)
            else:
                partial = json.loads(rec.PartialResult())
                part = (partial.get("partial") or "").strip()
                if part:
                    print(json.dumps({"partial": part}), flush=True)

    # Flush final result
    final = json.loads(rec.FinalResult())
    text = (final.get("text") or "").strip()
    if text:
        print(json.dumps({"final": text}), flush=True)


if __name__ == "__main__":
    main()
