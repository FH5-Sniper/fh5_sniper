import json
import os
import pytest
import time

import sniper
import settings
import window_utils
import vision_utils


def noop(*args, **kwargs):
    # placeholder for monkeypatched keystrokes
    pass


@pytest.fixture(autouse=True)
def disable_keystrokes(monkeypatch):
    """Prevent any test from sending real keystrokes via pyautogui."""
    monkeypatch.setattr(sniper.pyautogui, "press", noop)
    monkeypatch.setattr(sniper.pyautogui, "typewrite", noop)
    return None

class DummyVision:
    def __init__(self, result_sequence):
        self.seq = list(result_sequence)
    def locate_on_screen_with_variants(self, *args, **kwargs):
        return self.seq.pop(0) if self.seq else None


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    # redirect settings to temp config
    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    monkeypatch.setattr(settings, "CONFIG_FILE", str(cfg))
    return cfg


def test_buy_sequence_aborts_when_unfocused(monkeypatch, capsys):
    monkeypatch.setattr(window_utils, "is_fh5_focused", lambda: False)
    res = sniper.buy_sequence(settings.load_timings())
    assert res is None
    # check log printed
    captured = capsys.readouterr()
    assert "Buy sequence aborted" in captured.out


def test_buy_sequence_success_and_failure(monkeypatch):
    monkeypatch.setattr(window_utils, "is_fh5_focused", lambda: True)
    # simulate detection success then failure
    monkeypatch.setattr(vision_utils, "locate_on_screen_with_variants", lambda *args, **kw: (1,2,3,4))
    assert sniper.buy_sequence(settings.load_timings()) is True
    monkeypatch.setattr(vision_utils, "locate_on_screen_with_variants", lambda *args, **kw: None)
    # if both templates fail, result is undetermined (None)
    assert sniper.buy_sequence(settings.load_timings()) is None


def test_reset_search(monkeypatch):
    calls = []
    def fake_write(keys, interval=None):
        calls.append(tuple(keys))
    monkeypatch.setattr(window_utils, "wait_for_fh5_focus", lambda stop_flag=None: True)
    monkeypatch.setattr(window_utils, "is_fh5_focused", lambda: True)
    monkeypatch.setattr(sniper.pyautogui, "typewrite", fake_write)
    sniper.reset_search(settings.load_timings())
    assert calls, "reset_search should have sent keystrokes"

    # if unfocused, no write
    calls.clear()
    monkeypatch.setattr(window_utils, "is_fh5_focused", lambda: False)
    sniper.reset_search(settings.load_timings())
    assert not calls
