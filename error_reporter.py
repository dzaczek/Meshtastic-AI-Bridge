"""
error_reporter.py - Lightweight Matrix error reporter.

Sends critical errors/warnings directly to a Matrix room using plain HTTP
(no async, no matrix-nio dependency). Runs sends in background threads so
it never blocks the main application.

Configuration via environment variables:
  ERROR_MATRIX_HOMESERVER  - e.g. https://matrix.org
  ERROR_MATRIX_USERNAME    - e.g. @bot:matrix.org
  ERROR_MATRIX_PASSWORD    - bot password
  ERROR_MATRIX_ROOM_ID     - !roomid:server  (the error notification room)
"""

import logging
import os
import threading
import time
import traceback

logger = logging.getLogger("error_reporter")

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


class MatrixErrorReporter:
    def __init__(self):
        self._homeserver = os.environ.get("ERROR_MATRIX_HOMESERVER", "").rstrip("/")
        self._username = os.environ.get("ERROR_MATRIX_USERNAME", "")
        self._password = os.environ.get("ERROR_MATRIX_PASSWORD", "")
        self._room_id = os.environ.get("ERROR_MATRIX_ROOM_ID", "")
        self._access_token: str | None = None
        self._lock = threading.Lock()

        self.enabled = bool(
            _HAS_REQUESTS
            and self._homeserver
            and self._username
            and self._password
            and self._room_id
        )

        if self.enabled:
            self._login()
        else:
            if not _HAS_REQUESTS:
                logger.warning("error_reporter: 'requests' not installed, Matrix reporting disabled")
            else:
                logger.info("error_reporter: Matrix credentials not configured, reporting disabled")

    # ------------------------------------------------------------------

    def _login(self):
        try:
            url = f"{self._homeserver}/_matrix/client/v3/login"
            resp = requests.post(
                url,
                json={"type": "m.login.password", "user": self._username, "password": self._password},
                timeout=15,
            )
            resp.raise_for_status()
            self._access_token = resp.json()["access_token"]
            logger.info("error_reporter: Matrix login successful")
        except Exception as e:
            logger.error(f"error_reporter: Matrix login failed: {e}")
            self.enabled = False

    def _send_sync(self, title: str, details: str, level: str):
        """Blocking send - called from background thread."""
        if not self._access_token:
            return
        try:
            icon = {"ERROR": "🔴", "WARNING": "⚠️", "INFO": "ℹ️"}.get(level, "🔴")
            plain = f"{icon} [{level}] {title}"
            if details:
                plain += f"\n\n{details[:3000]}"

            html = f"<p><strong>{icon} [{level}] {title}</strong></p>"
            if details:
                html += f"<pre><code>{details[:3000]}</code></pre>"

            txn_id = f"err_{int(time.time() * 1000)}_{threading.get_ident()}"
            url = (
                f"{self._homeserver}/_matrix/client/v3/rooms/"
                f"{self._room_id}/send/m.room.message/{txn_id}"
            )
            with self._lock:
                resp = requests.put(
                    url,
                    json={
                        "msgtype": "m.text",
                        "body": plain,
                        "format": "org.matrix.custom.html",
                        "formatted_body": html,
                    },
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    timeout=15,
                )
                if resp.status_code == 401:
                    logger.warning("error_reporter: token expired, re-logging in")
                    self._login()
                elif not resp.ok:
                    logger.warning(f"error_reporter: send failed {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"error_reporter: send exception: {e}")

    def report(self, title: str, details: str = "", level: str = "ERROR"):
        """Send an error report to Matrix (non-blocking)."""
        if not self.enabled:
            return
        t = threading.Thread(
            target=self._send_sync,
            args=(title, details, level),
            daemon=True,
            name="ErrorReporterSend",
        )
        t.start()

    def report_exception(self, title: str, exc: BaseException | None = None):
        """Convenience: report an exception with its traceback."""
        details = traceback.format_exc() if exc is None else "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        self.report(title, details, level="ERROR")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_reporter: MatrixErrorReporter | None = None


def init() -> MatrixErrorReporter:
    """Initialize the global reporter. Call once at startup."""
    global _reporter
    _reporter = MatrixErrorReporter()
    return _reporter


def report(title: str, details: str = "", level: str = "ERROR"):
    """Report an error. No-op if init() was not called or Matrix not configured."""
    if _reporter:
        _reporter.report(title, details, level)


def report_exception(title: str, exc: BaseException | None = None):
    """Report an exception with traceback."""
    if _reporter:
        _reporter.report_exception(title, exc)


def is_enabled() -> bool:
    return bool(_reporter and _reporter.enabled)
