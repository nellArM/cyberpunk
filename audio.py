"""Procedurally synthesised sounds: loops (wind, rocket roar, elevator hum) and one-shot thunder."""
import numpy as np
import pygame


def _shaped_noise(rng, n, sr, gain):
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.maximum(np.fft.rfftfreq(n, 1.0 / sr), 1.0)
    x = np.fft.irfft(spec * gain(f), n)          # circular -> loops seamlessly
    return x / (np.max(np.abs(x)) + 1e-9)


class Audio:
    def __init__(self):
        self.ok = False
        self.vol = [0.0, 0.0, 0.0]
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 1024)
            sr, _, ch = pygame.mixer.get_init()
            rng = np.random.default_rng(7)
            n = sr * 4
            t = np.arange(n) / sr
            wind = _shaped_noise(rng, n, sr, lambda f: f ** -0.9 * np.exp(-f / 2500.0))
            wind *= 0.75 + 0.25 * np.sin(2 * np.pi * t / 4.0)
            rumble = _shaped_noise(rng, n, sr, lambda f: f ** -1.2 * (1.0 + 3.0 * np.exp(-((f - 70.0) / 40.0) ** 2)))
            hiss = _shaped_noise(rng, n, sr, lambda f: ((f > 1500) & (f < 6000)).astype(float))
            rocket = rumble + 0.25 * hiss
            hum = 0.6 * np.sin(2 * np.pi * 55 * t) + 0.3 * np.sin(2 * np.pi * 110 * t) + 0.1 * np.sin(
                2 * np.pi * 165 * t) + 0.05 * _shaped_noise(rng, n, sr, lambda f: f ** -1.0)
            self.sounds = [self._make(x, ch) for x in (wind, rocket, hum)]
            for s in self.sounds:
                s.set_volume(0.0)
                s.play(loops=-1)
            # thunder: a sharp crack into a long rolling rumble (one-shot)
            m = sr * 5
            tt = np.arange(m) / sr
            crack = _shaped_noise(rng, m, sr, lambda f: f ** -0.6 * np.exp(-f / 4000.0)) * np.exp(-tt * 9.0)
            roll = _shaped_noise(rng, m, sr, lambda f: f ** -1.6 * np.exp(-f / 300.0))
            roll *= np.minimum(tt / 0.25, 1.0) * np.exp(-tt * 0.7) * (0.7 + 0.3 * np.sin(2 * np.pi * 1.3 * tt) ** 2)
            self.thunder_sound = self._make(0.5 * crack + roll, ch)
            self.ok = True
        except Exception as exc:                 # no audio device etc. -> stay silent
            print(f"[audio] disabled: {exc}")

    @staticmethod
    def _make(x, channels):
        a = (np.clip(x / (np.max(np.abs(x)) + 1e-9), -1, 1) * 0.8 * 32767).astype(np.int16)
        if channels == 2:
            a = np.column_stack([a, np.roll(a, 1103)])
        return pygame.sndarray.make_sound(np.ascontiguousarray(a))

    def thunder(self, strength):
        if self.ok:
            ch = self.thunder_sound.play()
            if ch is not None:
                ch.set_volume(max(0.0, min(1.0, strength)))

    def update(self, dt, wind, rocket, hum):
        if not self.ok:
            return
        k = min(1.0, dt * 6.0)
        for i, target in enumerate((wind, rocket, hum)):
            self.vol[i] += (max(0.0, min(1.0, target)) - self.vol[i]) * k
            self.sounds[i].set_volume(self.vol[i])
