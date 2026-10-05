"""BOOTH-Reader error taxonomy.

Every failure the application raises on purpose derives from :class:`BoothError`
and carries a machine-readable ``CODE``. The CLI maps the exception type to an
exit code, and the Web layer maps it to an HTTP status, so the same condition
is reported consistently through every interface.

Exit code contract
------------------
===== ==========================================================
Code  Meaning
===== ==========================================================
0     success
1     operational failure (auth expired, network, bad input)
2     usage error (bad flags, mutually exclusive options)
3     BOOTH markup changed -- selectors need updating
===== ==========================================================
"""

from __future__ import annotations

BOOTH_LAYOUT_CHANGED = "BOOTH_LAYOUT_CHANGED"
BOOTH_AUTH_REQUIRED = "BOOTH_AUTH_REQUIRED"
BOOTH_NETWORK_ERROR = "BOOTH_NETWORK_ERROR"
BOOTH_LIMIT_EXCEEDED = "BOOTH_LIMIT_EXCEEDED"
BOOTH_DB_ERROR = "BOOTH_DB_ERROR"
BOOTH_PREREQUISITE_MISSING = "BOOTH_PREREQUISITE_MISSING"
BOOTH_SCHEMA_TOO_NEW = "BOOTH_SCHEMA_TOO_NEW"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_LAYOUT_CHANGED = 3

_RELOGIN_HINT = "BOOTH login required. Run `start.bat auth login`."


class BoothError(Exception):
    """Base error. ``CODE`` is stable and machine-readable."""

    CODE = "BOOTH_ERROR"


class BoothAuthError(BoothError):
    """Not logged in, or the cookie jar is no longer valid."""

    CODE = BOOTH_AUTH_REQUIRED

    def __init__(self, msg: str = "") -> None:
        super().__init__(f"{_RELOGIN_HINT} {msg}".strip())


class BoothLayoutChangedError(BoothError):
    """BOOTH served markup this version does not understand."""

    CODE = BOOTH_LAYOUT_CHANGED

    def __init__(self, msg: str = "") -> None:
        base = "Unexpected BOOTH page layout (BOOTH_LAYOUT_CHANGED). Update BOOTH-Reader."
        super().__init__(f"{base} {msg}".strip())


class BoothNetworkError(BoothError):
    """Transport or I/O failure: timeout, connection loss, bad status, bad disk."""

    CODE = BOOTH_NETWORK_ERROR


class BoothLimitExceededError(BoothError):
    """A safety limit was hit, e.g. an archive that expands beyond the cap.

    Separate from :class:`BoothNetworkError` because the remedy is different:
    the archive is rejected on purpose, not because the network misbehaved.
    """

    CODE = BOOTH_LIMIT_EXCEEDED


class BoothDatabaseError(BoothError):
    """The database file could not be opened or is not a usable database.

    Raised for a truncated, corrupt or non-SQLite file. The message names the
    file and the recovery path, because the generic "unexpected error" that
    SQLite's own exception would produce is useless to a user who has just lost
    their library index.
    """

    CODE = BOOTH_DB_ERROR

    def __init__(self, path: str = "", detail: str = "") -> None:
        base = (
            f"Cannot read database ({path}); it may be corrupt or not SQLite. "
            "Use --db <path> for another database. To rebuild, back up the damaged file, "
            "then run `start.bat init-db` and `start.bat purchases list --update-db`."
        )
        super().__init__(f"{base} {detail}".strip())


class BoothSchemaTooNewError(BoothError):
    """The database was written by a newer build of BOOTH-Reader.

    A deliberately raised condition, not a crash. It used to be a bare
    ``sqlite3.DatabaseError``, which meant the CLI's catch-all handler logged a
    full traceback and told the user "予期しないエラーが発生しました" -- a stack
    trace for a routine "please update the program" case, and a direct
    violation of the promise in :mod:`cli` that no raw traceback ever reaches a
    user. It is a separate class from :class:`BoothDatabaseError` because the
    remedy is the opposite: the file is *not* damaged, the program is old.
    """

    CODE = BOOTH_SCHEMA_TOO_NEW

    def __init__(self, path: str = "", found: int = 0, supported: int = 0) -> None:
        super().__init__(
            f"Database ({path}) schema v{found} is newer than supported v{supported}. "
            "Update BOOTH-Reader. If unavailable, run `start.bat doctor` with the version "
            "that last opened this database."
        )


class BoothPrerequisiteError(BoothError):
    """A required component is missing from the environment.

    Deliberately **not** a :class:`BoothAuthError`. An earlier version reused
    the auth error for "Playwright is not installed", which produced this:

        ERROR BOOTHへのログインが必要です。`start.bat auth login` で
        再ログインしてください。 Playwrightが未導入です。

    -- telling the user to re-run the command they had just run, while burying
    the real cause. A missing dependency needs an install command, never a
    log-in prompt.
    """

    CODE = BOOTH_PREREQUISITE_MISSING

    def __init__(self, component: str, remedy: str) -> None:
        super().__init__(f"Required component: {component}. {remedy}")


EXIT_CODE_BY_ERROR: dict[type[BoothError], int] = {
    BoothLayoutChangedError: EXIT_LAYOUT_CHANGED,
    BoothAuthError: EXIT_ERROR,
    BoothNetworkError: EXIT_ERROR,
    BoothLimitExceededError: EXIT_ERROR,
    BoothDatabaseError: EXIT_ERROR,
    BoothSchemaTooNewError: EXIT_ERROR,
    BoothPrerequisiteError: EXIT_ERROR,
}


def exit_code_for(exc: BaseException) -> int:
    """Map an exception to this project's exit code contract."""
    for exc_type, code in EXIT_CODE_BY_ERROR.items():
        if isinstance(exc, exc_type):
            return code
    if isinstance(exc, (ValueError, TypeError)):
        return EXIT_USAGE
    return EXIT_ERROR
