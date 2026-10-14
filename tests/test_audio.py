import numpy as np

from jarvis.audio import NoiseFilter, pcm_level


def _pcm(samples):
    return np.asarray(samples, dtype=np.int16).tobytes()


def _rms(pcm):
    x = np.frombuffer(pcm, dtype=np.int16).astype(float)
    return float(np.sqrt(np.mean(x * x)))


def test_disabled_filter_is_passthrough():
    f = NoiseFilter(enabled=False)
    data = _pcm([1, 2, 3])
    assert f.process(data) == data


def test_highpass_removes_dc_offset():
    f = NoiseFilter(sample_rate=16000, highpass_hz=80, gate_margin_db=0)
    block = _pcm([3000] * 1600)  # 100 ms of constant DC
    for _ in range(5):
        out = f.process(block)
    assert _rms(out) < 300  # DC is strongly attenuated after settling


def test_gate_attenuates_steady_hiss_but_passes_speech():
    rng = np.random.default_rng(0)
    f = NoiseFilter(sample_rate=16000, highpass_hz=20, gate_margin_db=9)
    hiss = _pcm(rng.normal(0, 30, 800))
    for _ in range(20):
        out_hiss = f.process(hiss)
    t = np.arange(800) / 16000
    speech = _pcm(8000 * np.sin(2 * np.pi * 300 * t))
    out_speech = f.process(speech)
    assert _rms(out_hiss) < _rms(hiss) * 0.5
    assert _rms(out_speech) > 2000


def test_pcm_level_range():
    assert pcm_level(b"") == 0.0
    assert 0 < pcm_level(_pcm([3000] * 100)) < 1
    assert pcm_level(_pcm([32767] * 100)) == 1.0
