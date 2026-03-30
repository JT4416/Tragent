import signal
import threading
from pathlib import Path
import pytest
from core.kill_switch import KillSwitch


@pytest.fixture(autouse=True)
def restore_sigint():
    original = signal.getsignal(signal.SIGINT)
    yield
    signal.signal(signal.SIGINT, original)


def test_file_flag_sets_stop_event(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    ks = KillSwitch(stop, kill_file=kill_file)
    ks.arm()
    assert not stop.is_set()
    kill_file.touch()
    ks.poll()
    assert stop.is_set()


def test_poll_removes_kill_file_after_acting(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    ks = KillSwitch(stop, kill_file=kill_file)
    kill_file.touch()
    ks.poll()
    assert stop.is_set()
    assert not kill_file.exists()


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


def test_handle_signal_sets_stop_event(tmp_path):
    stop = threading.Event()
    kill_file = tmp_path / "KILL"
    ks = KillSwitch(stop, kill_file=kill_file)
    ks._handle_signal(signal.SIGINT, None)
    assert stop.is_set()


def test_kill_switch_from_non_main_thread_does_not_raise(tmp_path):
    """KillSwitch constructed off main thread should not raise (skips signal registration)."""
    errors = []

    def make_in_thread():
        try:
            stop = threading.Event()
            KillSwitch(stop, kill_file=tmp_path / "KILL")
        except Exception as e:
            errors.append(e)

    t = threading.Thread(target=make_in_thread)
    t.start()
    t.join(timeout=3)
    assert errors == []
