"""Bounded, in-memory microphone recording and local transcription."""

from contextlib import redirect_stdout
import json
import queue
import sys
import threading

from .transcription import Transcriber
from .voice_activity import AutomaticCapture, EchoGate


MAX_SECONDS = 60


class Capture:
    def __init__(self, device=None):
        import numpy as np
        import sounddevice as sd

        info = sd.query_devices(device, "input")
        self.sample_rate = int(info["default_samplerate"])
        self.buffer = np.empty(self.sample_rate * MAX_SECONDS, dtype=np.float32)
        self.position = 0
        self.overflowed = False

        def callback(indata, frames, timing, status):
            if status.input_overflow:
                self.overflowed = True
            count = min(frames, len(self.buffer) - self.position)
            self.buffer[self.position:self.position + count] = indata[:count, 0]
            self.position += count
            if self.full:
                raise sd.CallbackStop

        self.stream = sd.InputStream(
            device=device, samplerate=self.sample_rate, channels=1, dtype="float32", callback=callback,
        )
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            raise

    @property
    def full(self):
        return self.position >= len(self.buffer)

    def level(self):
        import numpy as np

        end = self.position
        return min(100, int(float(np.max(np.abs(self.buffer[max(0, end - 2048):end]))) * 400)) if end else 0

    def close(self):
        self.stream.abort()
        self.stream.close()

    def finish(self):
        self.close()
        return self.buffer[:self.position].copy(), self.sample_rate


def input_devices():
    import sounddevice as sd

    hosts = sd.query_hostapis()
    return [
        {"id": index, "name": f"{device['name']} ({hosts[device['hostapi']]['name']})"}
        for index, device in enumerate(sd.query_devices()) if device["max_input_channels"] > 0
    ]


def run(input_stream=None, output_stream=None, capture_factory=Capture, transcriber=None,
        automatic_factory=AutomaticCapture):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    transcriber = transcriber or Transcriber()
    commands = queue.Queue()
    gate = EchoGate()  # Kept between turns: how loudly her voice reaches this microphone.

    def read_commands():
        from .pipe_lines import lines
        for line in lines(input_stream):  # Never a blocking pipe read: see pipe_lines.
            commands.put(line)
        commands.put(None)

    threading.Thread(target=read_commands, daemon=True).start()
    capture = None
    job_id = ""
    model_name = "base.en"
    automatic = False
    speaking = False

    def emit(kind, **values):
        output_stream.write(json.dumps({"id": job_id, "type": kind, **values}) + "\n")
        output_stream.flush()

    def finish():
        nonlocal capture
        audio, sample_rate = capture.finish()
        overflowed = capture.overflowed
        capture = None  # The microphone is closed before loading or running Whisper.
        if overflowed:
            emit("error", message="Microphone audio was interrupted. Please record again.")
            return
        emit("status", state="transcribing")
        with redirect_stdout(sys.stderr):
            text = transcriber.transcribe(
                audio, sample_rate, model_name, lambda state: emit("status", state=state),
            )
        emit("transcript", text=text)

    def fail():
        nonlocal capture
        if capture is not None:
            capture.close()
            capture = None
        emit("error", message=(
            "Microphone or transcription failed. Check Windows microphone permissions, "
            "the selected input, and your connection for the first model download."
        ))

    try:
        while True:
            try:
                line = commands.get(timeout=0.1)
            except queue.Empty:
                if capture is not None:
                    try:
                        if automatic:
                            capture.poll()
                            if capture.speaking and not speaking:
                                speaking = True
                                emit("status", state="recording")
                        emit("level", value=capture.level())
                        if capture.full:
                            if automatic and capture.timed_out:
                                capture.close()
                                capture = None
                                emit("error", message="Hands-free stopped after 30 seconds without speech. Start it again when ready.")
                                continue
                            finish()
                    except Exception:
                        fail()
                continue
            if line is None:
                break
            command = {}
            try:
                command = json.loads(line)
                if not isinstance(command, dict):
                    command = {}
                    raise ValueError("Expected a command object")
                action = command["action"]
                if action == "devices":
                    devices = input_devices()
                    output_stream.write(json.dumps({"id": command["id"], "type": "devices", "devices": devices}) + "\n")
                    output_stream.flush()
                elif action == "start":
                    if capture is not None:
                        capture.close()
                        capture = None
                    job_id = command["id"]
                    model_name = command["model"]
                    device = command.get("device")
                    device = int(device) if isinstance(device, str) and device.isdecimal() else device
                    automatic = bool(command.get("hands_free", False))
                    speaking = False
                    with redirect_stdout(sys.stderr):
                        if automatic and command.get("barge"):
                            capture = automatic_factory(device, command.get("pause_ms", 1200), gate=gate)
                        else:
                            capture = (automatic_factory(device, command.get("pause_ms", 1200))
                                       if automatic else capture_factory(device))
                    emit("status", state="listening" if automatic else "recording")
                elif action == "echo":
                    level = command.get("rms", 0)
                    if type(level) in (int, float) and 0 <= level <= 2:
                        gate.playing(float(level))
                elif action == "finish" and command["id"] == job_id and capture is not None:
                    finish()
            except Exception:
                if command.get("action") == "devices":
                    output_stream.write(json.dumps({
                        "id": command.get("id"), "type": "error", "message": "Could not list microphone inputs. Check your audio devices.",
                    }) + "\n")
                    output_stream.flush()
                else:
                    fail()
    finally:
        if capture is not None:
            capture.close()


if __name__ == "__main__":
    run()
