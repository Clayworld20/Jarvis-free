"""Microphone capture, noise filtering and simple audio feedback."""
from __future__ import annotations

import logging
import queue
from typing import Any

import numpy as np

log = logging.getLogger("jarvis.audio")


class AudioError(RuntimeError):
    pass


class NoiseFilter:
    """Real-time cleanup for 16-bit mono PCM.

    1. First-order high-pass filter removes rumble / DC offset (fans, desk vibration).
    2. Adaptive noise gate: the noise floor is tracked (fast down, slow up) and
       frames whose level stays close to that floor are attenuated by ~20 dB, so
       background hiss is not transcribed while speech passes unchanged.
    """

    GATE_ATTENUATION = 0.1  # -20 dB for frames treated as noise
    MIN_FLOOR = 40.0        # absolute floor (int16 RMS) to avoid gating silence to nothing

    def __init__(self, sample_rate: int = 16000, highpass_hz: float = 80.0, gate_margin_db: float = 9.0, enabled: bool = True):
        self.enabled = enabled
        self.gate_factor = 10 ** (gate_margin_db / 20.0)
        dt = 1.0 / sample_rate
        rc = 1.0 / (2 * np.pi * max(highpass_hz, 1.0))
        self._alpha = rc / (rc + dt)
        self._prev_x = 0.0
        self._prev_y = 0.0
        self._floor: float | None = None

    def reset(self) -> None:
        self._prev_x = self._prev_y = 0.0
        self._floor = None

    def process(self, pcm: bytes) -> bytes:
        if not self.enabled or not pcm:
            return pcm
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
        y = np.empty_like(x)
        px, py, a = self._prev_x, self._prev_y, self._alpha
        for i in range(x.size):  # IIR high-pass; blocks are short (<=200 ms) so this is cheap
            py = a * (py + x[i] - px)
            px = x[i]
            y[i] = py
        self._prev_x, self._prev_y = px, py

        rms = float(np.sqrt(np.mean(y * y))) if y.size else 0.0
        if self._floor is None:
            self._floor = rms
        elif rms < self._floor:
            self._floor = 0.8 * self._floor + 0.2 * rms   # adapt quickly to quieter background
        else:
            self._floor *= 1.002                           # rise slowly so speech does not raise the floor
        threshold = max(self._floor, self.MIN_FLOOR) * self.gate_factor
        if rms < threshold:
            y *= self.GATE_ATTENUATION
        return np.clip(y, -32768, 32767).astype(np.int16).tobytes()


def pcm_level(pcm: bytes) -> float:
    """Normalised loudness 0..1 of a 16-bit PCM block (for the GUI meter)."""
    if not pcm:
        return 0.0
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    rms = float(np.sqrt(np.mean(x * x))) if x.size else 0.0
    return min(1.0, rms / 6000.0)


def list_input_devices() -> list[dict[str, Any]]:
    try:
        import sounddevice as sd
    except (ImportError, OSError):
        return []
    devices = []
    try:
        for index, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                devices.append({"index": index, "name": dev["name"]})
    except Exception as exc:  # no audio backend available
        log.warning("Не удалось получить список микрофонов: %s", exc)
    return devices


class Microphone:
    """Streams 16 kHz mono int16 blocks into a queue via sounddevice."""

    def __init__(self, sample_rate: int = 16000, block_ms: int = 50, device: int | str | None = None):
        self.sample_rate = sample_rate
        self.blocksize = sample_rate * block_ms // 1000
        self.device = device
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=400)
        self._stream: Any = None

    def start(self) -> None:
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise AudioError(
                "Не найдена библиотека PortAudio/sounddevice. На Windows установите зависимости из requirements.txt."
            ) from exc
        try:
            self._stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                device=self.device,
                channels=1,
                dtype="int16",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            raise AudioError(f"Не удалось открыть микрофон: {exc}") from exc
        log.info("Микрофон открыт (%d Гц, блок %d сэмплов)", self.sample_rate, self.blocksize)

    def _callback(self, indata, frames, time_info, status) -> None:  # called from PortAudio thread
        try:
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            pass

    def read(self, timeout: float = 0.2) -> bytes | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None


def play_chime(sample_rate: int = 22050) -> None:
    """Short confirmation beep played when the wake word is heard. Silently skipped if no output device."""
    try:
        import sounddevice as sd
    except (ImportError, OSError):
        return
    t = np.arange(int(sample_rate * 0.14)) / sample_rate
    tone = np.sin(2 * np.pi * 880 * t) * np.hanning(t.size)
    try:
        sd.play((tone * 0.25 * 32767).astype(np.int16), sample_rate, blocking=False)
    except Exception as exc:
        log.debug("Звук подтверждения не воспроизведён: %s", exc)
