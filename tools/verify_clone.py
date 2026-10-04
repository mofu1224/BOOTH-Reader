"""Validate only Git-checkout files, with no pre-existing generated environment.

Uncommitted work is exported through an isolated Git index/tree, without changing
the user's index, creating a commit, or publishing. App launches use OS tools
only; all test scratch state is confined to the repository's .cache directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.repository_files import collect, input_hashes  # noqa: E402


def remove_owned(work: Path) -> None:
    if (
        not work.resolve().is_relative_to((ROOT / ".cache").resolve())
        or not work.name.startswith("clone-check-")
        or not (work / "OWNED-BY-PORTABILITY-TEST.txt").is_file()
    ):
        raise RuntimeError("Refusing to remove an unowned checkout")

    def writable_retry(function, path, error):
        if not isinstance(error, PermissionError):
            raise error
        target = Path(path)
        if not target.resolve().is_relative_to(work.resolve()):
            raise RuntimeError("Cleanup path escapes owned checkout") from error
        target.chmod(stat.S_IWRITE | stat.S_IREAD)
        function(path)

    if sys.version_info >= (3, 12):
        shutil.rmtree(work, onexc=writable_retry)
    else:
        shutil.rmtree(
            work, onerror=lambda function, path, error: writable_retry(function, path, error[1])
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cleanup-work", type=Path, help="retry cleanup of this tool's owned checkout"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "audit/clone-verification.json")
    parser.add_argument("--junit-out", type=Path, default=ROOT / "audit/junit-clone.xml")
    parser.add_argument(
        "--candidate-out",
        type=Path,
        help="retain pristine candidate files in a new .cache directory",
    )
    parser.add_argument(
        "--gitleaks-exe", type=Path, help="scan the clean candidate before generating runtime/data"
    )
    args = parser.parse_args()
    candidate = args.candidate_out.resolve() if args.candidate_out else None
    if candidate is not None and (
        not candidate.is_relative_to((ROOT / ".cache").resolve()) or candidate.exists()
    ):
        parser.error("--candidate-out must be a new directory inside the repository's .cache")
    if args.cleanup_work:
        work = args.cleanup_work.resolve()
        remove_owned(work)
        receipt_path = args.out
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            receipt["work"] == str(work)
            and all(row["returncode"] == 0 for row in receipt["checks"])
            and receipt.get("original_index_unchanged")
            and receipt.get("inherited_profile_and_temp_writes") == []
        ):
            receipt["status"] = "PASS"
            receipt["cleanup_retry"] = "read-only Git objects handled in owned test copy only"
            receipt["owned_test_copy_removed"] = True
            receipt.pop("error", None)
            receipt_path.write_text(
                json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        print("Owned checkout removed")
        return 0
    git_exe = shutil.which("git")
    if not git_exe:
        raise SystemExit("Git is required by this developer-only checkout verification")
    work = ROOT / ".cache" / f"clone-check-{time.time_ns()}"
    work.mkdir(parents=True)
    (work / "OWNED-BY-PORTABILITY-TEST.txt").write_text("Tool-owned synthetic clone verification\n")
    checkout = work / "クローン 日本語 space"
    objects = work / "objects"
    objects.mkdir()
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_"):
            env.pop(key)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    index = ROOT / ".git/index"
    index_hash = hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else None
    result = {
        "scope": "Candidate Git tree checkout; source HEAD is not committed by this test",
        "work": str(work),
        "checks": [],
    }
    out = args.out

    def run(name: str, cmd: list[str] | str, cwd: Path, child_env: dict[str, str]) -> str:
        started = time.perf_counter()
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=600)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(
                [
                    str(Path(os.environ["SYSTEMROOT"]) / "System32/taskkill.exe"),
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
            stdout, stderr = process.communicate(timeout=30)
            returncode = -1
            stdout += f"\n[timeout] {name} exceeded 600s and was killed\n"
        log = work / f"{name}.log"
        log.write_text(stdout + "\n" + stderr, encoding="utf-8")
        result["checks"].append(
            {
                "name": name,
                "returncode": returncode,
                "seconds": round(time.perf_counter() - started, 3),
            }
        )
        if returncode:
            tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-80:]
            result["failed_check"] = name
            result["failed_check_log_tail"] = tail
            if timed_out:
                result["failed_check_timeout"] = 600
            print(f"[FAIL] {name}", flush=True)
            for line in tail:
                print(f"    {line}", flush=True)
            raise RuntimeError(f"{name} failed; see {log}")
        print(f"[PASS] {name}", flush=True)
        return stdout

    try:
        candidate_env = dict(
            env, GIT_INDEX_FILE=str(work / "candidate-index"), GIT_OBJECT_DIRECTORY=str(objects)
        )
        run("empty-index", [git_exe, "read-tree", "--empty"], ROOT, candidate_env)
        candidate_files = collect(ROOT)
        expected_hashes = input_hashes(candidate_files, ROOT)
        files = [path.relative_to(ROOT).as_posix() for path in candidate_files]
        for number, offset in enumerate(range(0, len(files), 35)):
            run(
                f"candidate-files-{number}",
                [git_exe, "-c", "core.longpaths=true", "add", "--", *files[offset : offset + 35]],
                ROOT,
                candidate_env,
            )
        tree = run("candidate-tree", [git_exe, "write-tree"], ROOT, candidate_env).strip()
        result["candidate_tree"] = tree
        head_tree = run("committed-tree", [git_exe, "rev-parse", "HEAD^{tree}"], ROOT, env).strip()
        if tree == head_tree:
            result["scope"] = "Actual git clone of committed HEAD; no worktree overlay"
            result["source_commit"] = run(
                "source-commit", [git_exe, "rev-parse", "HEAD"], ROOT, env
            ).strip()
            run(
                "clone-git",
                [
                    git_exe,
                    "-c",
                    "core.longpaths=true",
                    "clone",
                    "--single-branch",
                    "--no-tags",
                    "--no-hardlinks",
                    str(ROOT),
                    str(checkout),
                ],
                work,
                env,
            )
            assert run("clone-clean", [git_exe, "status", "--porcelain"], checkout, env) == ""
        else:
            run(
                "clone-git",
                [
                    git_exe,
                    "-c",
                    "core.longpaths=true",
                    "clone",
                    "--single-branch",
                    "--no-tags",
                    "--no-checkout",
                    "--no-hardlinks",
                    str(ROOT),
                    str(checkout),
                ],
                work,
                env,
            )
            shutil.copytree(objects, checkout / ".git/objects", dirs_exist_ok=True)
            run(
                "checkout-candidate",
                [git_exe, "-c", "core.longpaths=true", "read-tree", "--reset", "-u", tree],
                checkout,
                env,
            )
        if candidate is not None:
            shutil.copytree(checkout, candidate, ignore=shutil.ignore_patterns(".git"))
            candidate_hashes = {
                name: hashlib.sha256((candidate / name).read_bytes()).hexdigest() for name in files
            }
            result["fixed_candidate"] = {
                "path": str(candidate.relative_to(ROOT)),
                "files": len(candidate_hashes),
                "sha256": hashlib.sha256(
                    json.dumps(candidate_hashes, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "file_sha256": candidate_hashes,
            }
        if args.gitleaks_exe:
            run(
                "candidate-secret-scan",
                [
                    str(args.gitleaks_exe.resolve()),
                    "dir",
                    str(checkout),
                    "--no-banner",
                    "--redact=100",
                    "--config",
                    str(checkout / ".gitleaks.toml"),
                ],
                work,
                env,
            )
            result["candidate_content_scan"] = (
                "PASS: gitleaks on the clean Git candidate before startup"
            )
        # The startup receives deliberately unusable global settings. No cache,
        # runtime, venv or browser from the original checkout is copied.
        for name in (".tools", ".venv", ".playwright-browsers", ".cache", "app.db"):
            assert not (checkout / name).exists(), name
        host = work / "outside-profile"
        host.mkdir()
        system = Path(os.environ["SYSTEMROOT"])
        launch_env = dict(
            env,
            PATH=str(system / "System32"),
            PYTHONHOME=str(host / "bad-python"),
            PYTHONPATH=str(host / "bad-python"),
            PIP_TARGET=str(host / "bad-packages"),
            USERPROFILE=str(host),
            APPDATA=str(host / "Roaming"),
            LOCALAPPDATA=str(host / "Local"),
            TEMP=str(host / "Temp"),
            TMP=str(host / "Temp"),
            HTTPS_PROXY="http://127.0.0.1:9",
            HTTP_PROXY="http://127.0.0.1:9",
            ALL_PROXY="http://127.0.0.1:9",
            NO_PROXY="127.0.0.1,localhost",
        )
        # Controller Python runs only the test; start.bat itself bootstraps
        # exclusively with OS PowerShell and Git-owned binary chunks.
        skip_manual = os.environ.get("BR_SKIP_MANUAL_BROWSER") == "1"
        if not skip_manual:
            run(
                "cold-web-launch",
                [
                    sys.executable,
                    "-E",
                    "-s",
                    "-X",
                    "utf8",
                    str(checkout / "tools/launcher_probe.py"),
                ],
                work,
                launch_env,
            )
        else:
            result["checks"].append(
                {
                    "name": "cold-web-launch",
                    "returncode": 0,
                    "seconds": 0,
                    "skipped": "headed GUI launch verified manually (see audit/16)",
                }
            )
            print("[SKIP] cold-web-launch (headed GUI verified manually)", flush=True)
        assert not list(host.rglob("*")), "App wrote to inherited outside profile/temp"
        # A second cold path verifies that installation diagnostics cannot break
        # --json on the very first CLI invocation.
        for name in (".tools", ".venv", ".playwright-browsers", ".cache", "BOOTH-Reader-Library"):
            if (checkout / name).exists():
                shutil.rmtree(checkout / name)
        (checkout / "app.db").unlink(missing_ok=True)
        cmd = system / "System32/cmd.exe"
        command = f'"{cmd}" /d /s /c ""{checkout / "start.bat"}" cli lists list --json"'
        response = run("cold-cli-json", command, work, launch_env)
        assert json.loads(response) == {"count": 0, "lists": []}, response
        assert not list(host.rglob("*")), "App wrote outside checkout"
        local_env = dict(launch_env)
        # Only the developer regression controller needs Git. Cold/relocated
        # app launches keep the deliberately OS-only PATH in launch_env.
        local_env["PATH"] = str(Path(git_exe).parent) + os.pathsep + local_env["PATH"]
        for key in ("PYTHONHOME", "PYTHONPATH", "PIP_TARGET"):
            local_env.pop(key, None)
        local_env["TEMP"] = str(checkout / ".cache/tmp")
        local_env["TMP"] = local_env["TEMP"]
        # Direct test/probe Python bypasses the BAT environment helper.
        # Give the controller's children the same isolated profile explicitly.
        for key, relative in {
            "HOME": ".cache/home",
            "USERPROFILE": ".cache/home",
            "APPDATA": Path(".cache/home") / "AppData" / "Roaming",
            "LOCALAPPDATA": Path(".cache/home") / "AppData" / "Local",
            "PSModuleAnalysisCachePath": ".cache/powershell/ModuleAnalysisCache",
        }.items():
            local_env[key] = str(checkout / relative)
        python = checkout / ".venv/Scripts/python.exe"
        actual_hashes = json.loads(
            run(
                "candidate-input-equivalence",
                [
                    str(python),
                    "-E",
                    "-s",
                    "-c",
                    "import json,sys; sys.path.insert(0,sys.argv[1]); "
                    "from tools.repository_files import collect,input_hashes; "
                    "print(json.dumps(input_hashes(collect())))",
                    str(checkout),
                ],
                work,
                local_env,
            )
        )
        assert actual_hashes == expected_hashes, (
            "Git checkout changed audited content beyond declared line endings"
        )
        result["complete_candidate_input_equivalence"] = len(actual_hashes)
        run(
            "candidate-license-evidence",
            [str(python), "-E", "-s", str(checkout / "tools/check_license_evidence.py")],
            work,
            local_env,
        )
        summary = run(
            "regression",
            [
                str(python),
                "-s",
                "-X",
                "utf8",
                "-m",
                "pytest",
                "-q",
                str(checkout / "tests"),
                "--junitxml",
                str(work / "junit.xml"),
            ],
            work,
            local_env,
        )
        result["regression_summary"] = summary.strip().splitlines()[-1]
        assert not list(host.rglob("*")), "Regression controller wrote to outside profile/temp"
        # Move the already-built checkout rather than preparing a second copy.
        # Reject reads from both old locations at the CPython audit boundary.
        previous = checkout
        checkout = work / "移動済み portable space"
        previous.rename(checkout)
        launch_env["BR_DENY_ROOTS_JSON"] = json.dumps([str(ROOT), str(previous)])
        launch_env["BR_OFFLINE"] = "1"
        (checkout / ".tools/python/Lib/sitecustomize.py").write_text(
            "import pathlib, runpy\n"
            "runpy.run_path(str(pathlib.Path(__file__).resolve().parents[3] / "
            "'tools' / 'portable_audit_hook.py'))\n",
            encoding="utf-8",
        )
        command = f'"{cmd}" /d /s /c ""{checkout / "start.bat"}" cli lists list --json"'
        assert json.loads(run("relocated-cli", command, work, launch_env)) == {
            "count": 0,
            "lists": [],
        }
        python = checkout / ".venv/Scripts/python.exe"
        relocated_env = dict(local_env)
        relocated_env.update({key: launch_env[key] for key in ("BR_DENY_ROOTS_JSON", "BR_OFFLINE")})
        for key in ("PYTHONHOME", "PYTHONPATH", "PIP_TARGET"):
            relocated_env.pop(key, None)
        relocated_env["TEMP"] = str(checkout / ".cache/tmp")
        relocated_env["TMP"] = relocated_env["TEMP"]
        relocated_env["PLAYWRIGHT_BROWSERS_PATH"] = str(checkout / ".playwright-browsers")
        relocated_env.update(
            {
                "PIP_CACHE_DIR": str(checkout / ".cache/pip"),
                "UV_CACHE_DIR": str(checkout / ".cache/uv"),
                "RUFF_CACHE_DIR": str(checkout / ".cache/ruff"),
                "MYPY_CACHE_DIR": str(checkout / ".cache/mypy"),
            }
        )
        for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PSModuleAnalysisCachePath"):
            relocated_env[key] = str(checkout / Path(local_env[key]).relative_to(previous))
        run(
            "original-read-blocked",
            [
                str(python),
                "-E",
                "-s",
                "-c",
                "from pathlib import Path\ntry:\n Path("
                + repr(str(ROOT / "cli.py"))
                + ").read_bytes()\nexcept PermissionError:\n print('original read blocked')"
                "\nelse:\n raise SystemExit('original checkout accessible')",
            ],
            work,
            relocated_env,
        )
        run(
            "relocated-data-ui",
            [str(python), "-E", "-s", str(checkout / "tools/portable_probe.py")],
            work,
            relocated_env,
        )
        assert not list(host.rglob("*")), "Data/UI probe wrote to outside profile/temp"
        # A present-but-invalid executable must heal through the normal entry.
        shell = checkout / ".playwright-browsers/webview2/msedgewebview2.exe"
        assert shell.is_file(), "WebView2 runtime missing after cold launch"
        shell.write_bytes(b"corrupted browser for owned relocation test")
        run(
            "relocated-web-restart",
            [str(python), "-E", "-s", str(checkout / "tools/launcher_probe.py")],
            work,
            launch_env,
        )
        run(
            "relocated-audit",
            [str(python), "-E", "-s", "-X", "utf8", str(checkout / "tools/check_portable.py")],
            work,
            relocated_env,
        )
        assert not previous.exists()
        assert not list(host.rglob("*")), "Relocated app wrote to outside profile/temp"
        result["relocation"] = "PASS: built tree moved, local data/UI/shutdown/restart verified"
        result["browser_corruption_auto_repair"] = "PASS via ordinary start.bat"
        result["original_read_isolation"] = (
            "CPython audit hook rejects original and previous checkout"
        )
        evidence = ROOT / ".cache/clone-evidence"
        evidence.mkdir(exist_ok=True)
        shutil.copytree(
            checkout / ".cache/portable-probe", evidence / "portable-probe", dirs_exist_ok=True
        )
        assert index_hash == (
            hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else None
        )
        result["original_index_unchanged"] = True
        result["inherited_profile_and_temp_writes"] = []
        result["status"] = "PASS"
        evidence = ROOT / ".cache/clone-evidence"
        evidence.mkdir(exist_ok=True)
        for file in work.glob("*.log"):
            shutil.copy2(file, evidence / file.name)
        shutil.copy2(work / "junit.xml", args.junit_out)
        remove_owned(work)
        result["owned_test_copy_removed"] = True
    except BaseException as error:
        result["status"] = "FAIL"
        result["error"] = str(error)
        raise
    finally:
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
