"""Portable-layout audit: fail loudly on any dependency outside the repo.

Checks (all read-only except ``--repair``):

* ``.venv`` exists and its ``sys.prefix`` resolves inside the checkout
  (a moved or copied folder with a stale venv is reported, not silently used)
* ``PLAYWRIGHT_BROWSERS_PATH`` resolves inside the checkout
* default DB / cookie / library paths resolve inside the checkout
* no developer-absolute path or user-profile reference in tracked sources
* pip / uv / ruff / mypy caches resolve inside the checkout

Usage:
    python tools/check_portable.py          # full audit, exit != 0 on failure
    python tools/check_portable.py --quick  # venv + browser + paths only
    python tools/check_portable.py --repair # rebuild a stale venv, then audit

The audit never changes machine state (no installs, no registry, no PATH).
``--repair`` only recreates the repo-local ``.venv`` and reinstalls into it.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.portable import (  # noqa: E402
    apply_portable_env,
    browsers_path,
    portable_env,
    repo_root,
)

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def _is_inside(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def check_repo_root() -> None:
    found = repo_root(ROOT)
    record("repo root resolves", found == ROOT.resolve(), str(found))


def check_venv() -> bool:
    from tools.portable import venv_base_home, venv_health

    ok, reason = venv_health(ROOT)
    record("venv healthy and repo-local", ok, reason)
    # A venv whose base interpreter lives outside the repo runs here but
    # breaks when the folder is moved or the original machine is gone
    # (pyvenv.cfg `home` is an absolute path). start.bat rebases it onto the
    # bundled interpreter; the audit names it so a moved folder is diagnosable.
    home = venv_base_home(ROOT)
    if home is None:
        record("venv base is repo-local", True, "base unknown; nothing to check")
    else:
        inside = _is_inside(home, ROOT)
        record(
            "venv base is repo-local",
            inside,
            f"{home} " + ("(bundled)" if inside else "(outside: run start.bat --repair)"),
        )
    return ok


def check_browser_path() -> None:
    explicit = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if explicit:
        inside = _is_inside(Path(explicit), ROOT)
        record("PLAYWRIGHT_BROWSERS_PATH is repo-local", inside, explicit)
    else:
        record(
            "PLAYWRIGHT_BROWSERS_PATH defaults into repo",
            True,
            f"(unset; cli.py defaults to {browsers_path(ROOT)})",
        )
    # If a browser was ever installed, it must live in the repo dir.
    found = sorted((browsers_path(ROOT)).glob("chromium*")) if browsers_path(ROOT).is_dir() else []
    if (browsers_path(ROOT) / "webview2/msedgewebview2.exe").is_file():
        found = [browsers_path(ROOT) / "webview2"]
    if (browsers_path(ROOT) / "native-webkit/booth-webkit-host").is_file():
        found = [browsers_path(ROOT) / "native-webkit"]
    if found:
        record(
            "browser binary not stranded in user profile",
            True,
            "; ".join(p.name for p in found[:3]),
        )
    else:
        record(
            "browser binary not stranded in user profile",
            False,
            "no browser installed; auth login is unavailable until start.bat runs.",
        )


def check_default_paths() -> None:
    from cli import DEFAULT_DB, DEFAULT_LIBRARY
    from core.auth import DEFAULT_COOKIE_PATH

    for label, value in (
        ("db", DEFAULT_DB),
        ("library", DEFAULT_LIBRARY),
        ("cookies", str(DEFAULT_COOKIE_PATH)),
    ):
        record(f"default {label} path is repo-local", _is_inside(Path(value), ROOT), value)


def check_caches() -> None:
    env = portable_env(ROOT)
    for key in ("PIP_CACHE_DIR", "UV_CACHE_DIR", "RUFF_CACHE_DIR", "MYPY_CACHE_DIR"):
        current = os.environ.get(key, env[key])
        record(f"{key} is repo-local", _is_inside(Path(current), ROOT), current)


def check_no_absolute_refs() -> None:
    """Scan actual shipped sources, including untracked changes, without Git."""
    patterns = [
        re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
        re.compile(r"/home/|/Users/", re.IGNORECASE),
        re.compile(r"%LOCALAPPDATA%|%APPDATA%|%USERPROFILE%", re.IGNORECASE),
        re.compile(r"AppData[\\/]Local[\\/]ms-playwright", re.IGNORECASE),
        re.compile(r"[A-Za-z]:[\\/](?:Creative|Projects|Dev|Work)[\\/]", re.IGNORECASE),
        re.compile(r"\b[A-Za-z]:[\\/](?!Windows(?:[\\/]|\b))", re.IGNORECASE),
    ]
    # Files allowed to name these locations: the portable layer itself and
    # its tests, which exist precisely to keep them out of the product code.
    allowed = {"check_portable.py", "portable.py", "test_portable.py"}
    files = (
        list(ROOT.glob("*.py"))
        + list(ROOT.glob("*.bat"))
        + list(ROOT.glob("*.cmd"))
        + list(ROOT.glob("*.ps1"))
        + list(ROOT.glob("*.sh"))
        + list(ROOT.glob("*.toml"))
    )
    for directory in ("core", "web", "tools"):
        files.extend(p for p in (ROOT / directory).rglob("*") if p.is_file())
    hits: list[str] = []
    for path in files:
        if path.suffix not in {".py", ".bat", ".cmd", ".toml", ".ps1", ".sh"}:
            continue
        if path.name in allowed:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if path.suffix == ".py":
            # Decode literals before matching. A generated script's "as r:\n"
            # must not be mistaken for a drive-R absolute path.
            text = "\n".join(
                node.value
                for node in ast.walk(ast.parse(text))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            )
        rel = str(path.relative_to(ROOT))
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                snippet = text[max(0, match.start() - 40) : match.end() + 40].replace("\n", " ")
                hits.append(f"{rel}: ...{snippet.strip()}...")
                break
    record(
        "no machine-absolute references in tracked sources",
        not hits,
        "; ".join(hits[:5]) or f"{len(files)} files scanned",
    )


def check_machine_state() -> None:
    """Static prevention of system installs/persistent mutations, not OS tracing."""
    forbidden = re.compile(
        r"\bsetx\b|\breg\s+add\b|\bschtasks\s+/create\b|\bsc\s+create\b|"
        r"\b(?:winget|choco|scoop|apt-get)\s+install\b|"
        r"\b(?:npm|pip)\s+install\s+(?:-g|--user)\b|"
        r"SetEnvironmentVariable\([^\n]*(?:User|Machine)|"
        r"\bwinreg\.(?:SetValue|CreateKey)|PLAYWRIGHT_NODEJS_PATH.*shutil\.which",
        re.IGNORECASE,
    )
    hits = []
    unmanaged = []
    # Windows OS-standard process control. The project is Windows-only and
    # already depends on OS-provided cmd/PowerShell/tar/whoami/icacls (see
    # PORTABLE.md); taskkill.exe ships with Windows and is not a third-party
    # dependency that breaks clone-to-run portability.
    os_standard = {
        "taskkill",
        "/usr/bin/codesign",
        "/usr/sbin/spctl",
        "/usr/bin/otool",
        "/usr/bin/swiftc",
        "/bin/bash",
    }
    # Git is used only for developer provenance and clone-candidate checks,
    # never by the app's runtime/bootstrap or this portability auditor.
    git_audit_tools = {
        "audit_probe.py",
        "license_compliance.py",
        "check_release_hygiene.py",
        "release_provenance.py",
        "repository_files.py",
        "verify_clone_macos.py",
    }
    paths = list(ROOT.glob("*.py")) + list(ROOT.glob("*.bat")) + list(ROOT.glob("*.cmd"))
    paths += list(ROOT.glob("*.ps1"))
    for directory in ("core", "web", "tools"):
        paths.extend(p for p in (ROOT / directory).rglob("*") if p.suffix in {".py", ".ps1"})
    for path in paths:
        if path.name == "check_portable.py":
            continue
        text = path.read_text(encoding="utf-8")
        if forbidden.search(text):
            hits.append(path.relative_to(ROOT).as_posix())
        if path.suffix == ".py":
            for node in ast.walk(ast.parse(text)):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.args
                    and isinstance(node.args[0], ast.List)
                    and node.args[0].elts
                ):
                    exe = node.args[0].elts[0]
                    # Git is optional metadata-only in audit tooling; launchers
                    # and the portability auditor themselves do not need it.
                    # OS-standard commands (taskkill) travel with Windows.
                    if (
                        isinstance(exe, ast.Constant)
                        and isinstance(exe.value, str)
                        and (
                            exe.value in os_standard
                            or (exe.value == "git" and path.name in git_audit_tools)
                        )
                    ):
                        continue
                    if isinstance(exe, ast.Constant) and isinstance(exe.value, str):
                        unmanaged.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    record(
        "no forbidden system mutations in product/tool sources",
        not hits,
        ", ".join(hits) or f"{len(paths)} sources checked; static evidence only",
    )
    record("no unmanaged literal external CLI commands", not unmanaged, "; ".join(unmanaged))


def check_links() -> None:
    """Do not follow junctions/reparse points into other checkouts.

    Generated roots (caches, runtimes, browsers) stay out of scope: they are
    never distributed, and Edge/Windows itself creates system cache junctions
    inside the isolated profile whose absolute targets cannot survive a folder
    move even though the app keeps working.
    """
    import stat

    generated = {".git", ".cache", ".tools", ".venv", ".verify-venv", ".playwright-browsers"}
    external = []
    hardlinks = []
    for directory, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = [name for name in dirs if name not in generated]
        for name in [*dirs, *files]:
            path = Path(directory) / name
            info = path.lstat()
            reparse = getattr(info, "st_file_attributes", 0) & 0x400
            if path.is_symlink() or reparse:
                if not _is_inside(path, ROOT):
                    external.append(path.relative_to(ROOT).as_posix())
                if name in dirs:
                    dirs.remove(name)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
                hardlinks.append(path.relative_to(ROOT).as_posix())
    record("no external symlinks/junctions", not external, "; ".join(external))
    record("no shared hardlinked files", not hardlinks, "; ".join(hardlinks[:5]))


def check_ci_isolation() -> None:
    """CI build/test commands must use the same checkout-owned environment."""
    forbidden = re.compile(
        r"actions/setup-python@|^\s*(?:python|pip|pip3|npm)\s+|\$env:RUNNER_TEMP",
        re.MULTILINE,
    )
    hits = []
    for path in (ROOT / ".github/workflows").glob("*.y*ml"):
        if forbidden.search(path.read_text(encoding="utf-8")):
            hits.append(path.relative_to(ROOT).as_posix())
    record("CI runtime/install/temp commands are repo-local", not hits, "; ".join(hits))


def main(argv: list[str] | None = None) -> int:
    RESULTS.clear()
    args = set(argv if argv is not None else sys.argv[1:])
    apply_portable_env(ROOT)

    if "--repair" in args:
        from tools.manage_portable import install_environment

        install_environment(offline=True, repair=True)
        record("repair dependencies installed from pinned local wheels", True)

    quick = "--quick" in args
    check_repo_root()
    venv_ok = check_venv()
    check_browser_path()
    check_default_paths()
    if not quick:
        check_caches()
        check_no_absolute_refs()
        check_machine_state()
        check_links()
        check_ci_isolation()

    failures = [name for name, ok, _ in RESULTS if not ok]
    print()
    print(f"portable audit: {len(RESULTS) - len(failures)}/{len(RESULTS)} passed")
    if failures:
        print("Failures:")
        for name in failures:
            print(f"  - {name}")
        if not venv_ok:
            print("Hint: run start.bat (or start.bat --repair) to rebuild .venv.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
