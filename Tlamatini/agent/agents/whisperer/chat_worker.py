# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Internal resident dictation worker under source/carried Python.

Private loopback JSON protocol; no shell, window or model planner. Diagnostics
go to the main application logger. Microphone opens ONLY on start; EOF cancels.
"""
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

MAX_FRAME = 131072


class DictationWorker:
    def __init__(self, send, whisperer):
        self.send = send
        self.whisperer = whisperer
        self.cache = {}
        self.job = None
        self.busy = False
        self.run_id = None
        self.cancelled = threading.Event()

    def start(self, run_id):
        if self.busy:
            self.send({"event": "error", "run_id": run_id, "message": "Whisperer is still busy."})
            return
        self.busy = True
        self.run_id = run_id
        self.cancelled = threading.Event()
        self.job = threading.Thread(target=self.run, args=(run_id, self.cancelled), daemon=True)
        self.job.start()

    def cancel(self, run_id):
        if run_id == self.run_id:
            self.cancelled.set()

    def run(self, run_id, cancelled):
        w = self.whisperer
        started = time.monotonic()
        first_sample = None
        warmup = None
        wav = None
        completion = None

        def emit(event, **data):
            nonlocal completion
            frame = {"event": event, "run_id": run_id, **data}
            if event in {"result", "empty", "error", "cancelled"}:
                completion = frame
            else:
                self.send(frame)

        try:
            config = w.load_config(str(Path(w.__file__).with_name("config.yaml")))
            config.update(input_source="mic", record_seconds=0, silence_gate="on",
                          ollama_cleanup=False, target_agents=[])
            engine = str(config.get("engine", "faster-whisper")).lower()
            print(f"DICTATION {run_id}: opening configured host microphone; engine={engine}", flush=True)

            def warm():
                try:
                    w.warm_recognition_model(config, self.cache)
                except Exception as exc:
                    # The real transcription path reports errors and owns CPU fallback.
                    print(f"Recognition warmup: {type(exc).__name__}; capture continues.", flush=True)

            def progress(data):
                nonlocal first_sample, warmup
                if first_sample is None:
                    first_sample = time.monotonic()
                    print(f"RECORDING: first samples after {first_sample - started:.3f}s", flush=True)
                    if engine == "faster-whisper":
                        warmup = threading.Thread(target=warm, daemon=True)
                        warmup.start()
                emit("recording", **{k: v for k, v in data.items() if k != "event"})

            audio, meta = w.record_from_microphone(
                config, progress=progress, cancel_event=cancelled, strict_stream=True)
            if cancelled.is_set():
                raise w.CaptureCancelled()
            if meta.get("speech_seconds", 0) <= 0:
                emit("empty", message="No speech detected. Your draft is unchanged.")
                return
            emit("transcribing", stop_reason=meta["stop_reason"])
            print(f"TRANSCRIBING: gate closed ({meta['stop_reason']}); {meta['duration_seconds']}s captured", flush=True)
            decode_started = time.monotonic()
            if engine in ("cloud-groq", "cloud-openai"):
                wav = w.save_capture_wav(audio, w.resolve_temp_dir())
                result = w.transcribe_cloud(wav, config)
            elif engine == "faster-whisper":
                if warmup:
                    warmup.join()
                if cancelled.is_set():
                    raise w.CaptureCancelled()
                result = w.transcribe_faster_whisper(audio, config, model_cache=self.cache)
            else:
                raise RuntimeError(f"Unsupported Whisperer engine: {engine}")
            if cancelled.is_set():
                raise w.CaptureCancelled()
            text = str(result.get("text", "")).strip()
            if not text:
                emit("empty", message="No words recognized. Your draft is unchanged.")
            elif len(text) > 24000:
                emit("error", message="The transcript is too long for one voice prompt.")
            else:
                timings = {"capture_start_ms": round(((first_sample or started) - started) * 1000),
                           "transcription_ms": round((time.monotonic() - decode_started) * 1000),
                           "audio_seconds": meta["duration_seconds"]}
                print(f"TRANSCRIBED: {len(text)} characters; timings={timings}", flush=True)
                emit("result", text=text, timings=timings, stop_reason=meta["stop_reason"])
        except w.CaptureCancelled:
            emit("cancelled", message="Dictation cancelled. Your draft is unchanged.")
        except (Exception, SystemExit) as exc:
            # The standalone config loader exits on missing/invalid YAML.
            # Report that as a terminal job error so chat can recover.
            import traceback
            traceback.print_exc()
            # No credentials, paths or provider response bodies in a browser frame.
            emit("error", message=f"Whisperer could not complete dictation ({type(exc).__name__}). "
                 "Check the microphone, configured speech engine and Tlamatini log.")
        finally:
            if warmup and warmup.is_alive():
                warmup.join()
            if wav:
                try:
                    Path(wav).unlink(missing_ok=True)
                except OSError:
                    pass
            print(f"DICTATION {run_id}: finished", flush=True)
            if cancelled.is_set():
                completion = {"event": "cancelled", "run_id": run_id}
            self.busy = False
            if completion:
                self.send(completion)


def main():
    connection = socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=15)
    connection.settimeout(None)
    writer_lock = threading.Lock()

    def send(data):
        payload = (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
        with writer_lock:
            connection.sendall(payload)

    send({"token": os.environ.pop("TLAMATINI_VOICE_TOKEN")})
    # Import before ready, but neither microphone nor model is opened here.
    import numpy  # noqa: F401
    import sounddevice  # noqa: F401
    import whisperer
    worker = DictationWorker(send, whisperer)
    send({"event": "ready"})
    print("READY: direct dictation. No microphone is open. Waiting for a click.", flush=True)
    try:
        with connection.makefile("rb") as reader:
            while True:
                line = reader.readline(MAX_FRAME + 1)
                if not line:
                    break
                if len(line) > MAX_FRAME:
                    raise ValueError("Oversized control frame.")
                message = json.loads(line)
                action = message.get("action")
                if action == "start":
                    worker.start(message["run_id"])
                elif action == "cancel":
                    worker.cancel(message["run_id"])
                elif action == "shutdown":
                    break
    finally:
        worker.cancelled.set()
        connection.close()
        if worker.job:
            worker.job.join(timeout=2)
        print("Whisperer control connection closed. Microphone stopped.", flush=True)


if __name__ == "__main__":
    main()
