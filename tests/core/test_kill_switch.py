import threading
from pathlib import Path
from core.kill_switch import KillSwitch


def test_file_flag_sets_stop_event(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    ks = KillSwitch(stop, kill_file=kill_file)
    ks.arm()
    assert not stop.is_set()
    kill_file.touch()
    ks.poll()
    assert stop.is_set()


def test_arm_removes_stale_kill_file(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    kill_file.touch()
    ks = KillSwitch(stop, kill_file=kill_file)
    ks.arm()
    assert not kill_file.exists()
    assert not stop.is_set()


def test_no_kill_file_does_not_set_event(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    ks = KillSwitch(stop, kill_file=kill_file)
    ks.arm()
    ks.poll()
    assert not stop.is_set()


def test_check_returns_true_when_file_exists(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    ks = KillSwitch(stop, kill_file=kill_file)
    assert not ks.check()
    kill_file.touch()
    assert ks.check()
