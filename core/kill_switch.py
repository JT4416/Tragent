import signal
import threading
from pathlib import Path

_DEFAULT_KILL_FILE = Path(__file__).parent.parent / "KILL"


class KillSwitch:
    """
    Dual-mode kill switch:
    - File flag: create a file named KILL in the project root to trigger shutdown
    - Signal handler: SIGINT (Ctrl+C) and SIGTERM both trigger shutdown

    Usage:
        ks = KillSwitch(stop_event)
        ks.arm()           # call once at startup; removes stale KILL file
        # in main loop:
        ks.poll()          # sets stop_event if KILL file found
    """

    def __init__(self, stop_event: threading.Event,
                 kill_file: Path = _DEFAULT_KILL_FILE):
        self._stop = stop_event
        self._kill_file = kill_file
        # Signal handlers must be registered from the main thread only
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self._handle_signal)
            try:
                signal.signal(signal.SIGTERM, self._handle_signal)
            except (OSError, AttributeError):
                pass  # SIGTERM unavailable on some platforms (Windows)

    def _handle_signal(self, signum, frame):
        # Keep signal handler minimal — no print(), no I/O, just set the event
        self._stop.set()

    def arm(self) -> None:
        """Remove any stale KILL file left from a prior run."""
        if self._kill_file.exists():
            self._kill_file.unlink()

    def check(self) -> bool:
        """Return True if a KILL file is present."""
        return self._kill_file.exists()

    def poll(self) -> None:
        """Set stop_event and remove KILL file if detected. Call in the main loop."""
        if self.check():
            self._kill_file.unlink()  # remove so it won't retrigger
            self._stop.set()
