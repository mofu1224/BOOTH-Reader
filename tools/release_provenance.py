"""Read narrowly scoped creation records without exporting conversation contents."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SESSIONS = [
    "ses_f1456997fffeOozkdcVSdJ2GHR",
    "ses_f1447bbb7ffe3pFft7n367WLot",
    "ses_f14250521ffe8Xp8yUZhEJoZ3U",
]


def inspect(database: Path, output: Path | None) -> None:
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    schema = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' AND name IN ('session','message','part')"
        )
    }
    if output is None:
        print(json.dumps(schema, indent=2))
        return
    models, writes, reads, tools = [], [], [], []
    searches = []
    reconstructed = {}
    replay_failures = []
    cutoff = (
        int(
            subprocess.check_output(
                ["git", "show", "-s", "--format=%ct", "240edc9"], cwd=ROOT
            ).strip()
        )
        * 1000
    )
    for session in SESSIONS:
        for row in connection.execute(
            "SELECT data FROM message WHERE session_id=? AND time_created<=?", (session, cutoff)
        ):
            message = json.loads(row[0])
            if message.get("role") == "assistant":
                models.append(
                    {
                        "session": session,
                        "model": message.get("modelID"),
                        "provider": message.get("providerID"),
                        "time": message.get("time"),
                    }
                )
        for row in connection.execute(
            "SELECT data FROM part WHERE session_id=? AND time_created<=? ORDER BY time_created,id",
            (session, cutoff),
        ):
            part = json.loads(row[0])
            if part.get("type") != "tool":
                continue
            tool = part.get("tool")
            state = part.get("state", {})
            if state.get("status") != "completed":
                continue
            tools.append(tool)
            parameters = state.get("input", {})
            if tool == "websearch":
                query = parameters.get("query", parameters.get("search_query", ""))
                from tools.license_compliance import secret_findings

                if isinstance(query, str) and not secret_findings(query.encode(), "query"):
                    searches.append({"session": session, "query": query[:500]})
            name = (
                parameters.get("filePath") or parameters.get("file_path") or parameters.get("path")
            )
            if tool in {"write", "edit", "read"} and name:
                normalized = str(name).replace("\\", "/")
                marker = "/BOOTH-Reader/"
                if marker in normalized:
                    relative = normalized.split(marker, 1)[1]
                elif (
                    not Path(normalized).is_absolute()
                    and ":" not in normalized
                    and ".." not in Path(normalized).parts
                ):
                    relative = normalized
                else:
                    relative = "external-input: " + Path(normalized).name
                if tool == "read":
                    reads.append(
                        {
                            "session": session,
                            "path": relative,
                            "source_classification": "NOT VERIFIED"
                            if relative.startswith("external-input:")
                            else "repository",
                        }
                    )
                elif tool == "write":
                    content = parameters.get("content", "").encode("utf-8")
                    reconstructed[relative] = content.decode("utf-8")
                    sha = hashlib.sha256(content).hexdigest()
                    baseline = subprocess.run(
                        ["git", "show", "240edc9:" + relative], cwd=ROOT, capture_output=True
                    )
                    equivalent = baseline.returncode == 0 and baseline.stdout.replace(
                        b"\r\n", b"\n"
                    ) == content.replace(b"\r\n", b"\n")
                    writes.append(
                        {
                            "session": session,
                            "path": relative,
                            "generated_sha256": sha,
                            "matches_first_snapshot_normalized_newlines": equivalent,
                        }
                    )
                elif tool == "edit":
                    previous = reconstructed.get(relative)
                    old = parameters.get("oldString") or parameters.get("old_string")
                    new = parameters.get("newString", parameters.get("new_string", ""))
                    if previous is not None and old is not None and old in previous:
                        reconstructed[relative] = previous.replace(
                            old, new, -1 if parameters.get("replaceAll", False) else 1
                        )
                    else:
                        replay_failures.append(
                            {
                                "session": session,
                                "path": relative,
                                "reason": "edit input cannot be replayed against captured write",
                            }
                        )
    connection.close()
    replay = []
    for relative, content in reconstructed.items():
        baseline = subprocess.run(
            ["git", "show", "240edc9:" + relative], cwd=ROOT, capture_output=True
        )
        if baseline.returncode == 0:
            replay.append(
                {
                    "path": relative,
                    "generated_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "baseline_sha256": hashlib.sha256(baseline.stdout).hexdigest(),
                    "matches_first_snapshot_normalized_newlines": baseline.stdout.replace(
                        b"\r\n", b"\n"
                    )
                    == content.encode("utf-8").replace(b"\r\n", b"\n"),
                }
            )
    result = {
        "sessions": SESSIONS,
        "baseline_cutoff_unix_ms": cutoff,
        "models": models,
        "generated_writes": writes,
        "reconstructed_baseline": replay,
        "replay_failures": replay_failures,
        "read_inputs": reads,
        "search_queries": searches,
        "completed_tool_counts": {tool: tools.count(tool) for tool in sorted(set(tools))},
        "scope": "initial creation sessions up to first Git snapshot only; raw prompts, tool outputs and credential values not exported; external input basenames retained",
        "rights_status": "NOT VERIFIED pending applicable output terms and input-source evidence",
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "models": sorted({(row["provider"], row["model"]) for row in models}),
                "writes": len(writes),
                "baseline_replayed": len(replay),
                "baseline_matches": sum(
                    row["matches_first_snapshot_normalized_newlines"] for row in replay
                ),
                "replay_failures": len(replay_failures),
                "reads": len(reads),
                "tools": result["completed_tool_counts"],
            },
            indent=2,
        )
    )


def terms() -> None:
    from tools.license_compliance import dump, fetch
    from tools.license_reaudit import PageText

    sources = {
        "opencode-terms-20260815": "https://opencode.ai/legal/terms-of-service",
        "opencode-muse-spark-provider": "https://opencode.ai/docs/zen/",
        "google-terms-20260730": "https://policies.google.com/terms",
        "meta-api-models": "https://dev.meta.ai/docs/overview",
        "openai-services-agreement": "https://openai.com/policies/services-agreement/",
    }
    rows = []
    for name, url in sources.items():
        try:
            data = fetch(url)
            target = ROOT / "license-audit/evidence/legal" / (name + ".html")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            text = PageText()
            text.feed(data.decode("utf-8", errors="replace"))
            target.with_suffix(".txt").write_text("\n".join(text.parts), encoding="utf-8")
            rows.append(
                {
                    "name": name,
                    "url": url,
                    "path": target.relative_to(ROOT).as_posix(),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "status": "retrieved",
                }
            )
        except (OSError, ValueError) as error:
            rows.append(
                {"name": name, "url": url, "status": "NOT VERIFIED", "error": type(error).__name__}
            )
    dump(ROOT / "license-audit/public-profile-legal-evidence.json", rows)
    print(json.dumps(rows, indent=2))


def project_models(database: Path) -> None:
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    directory = str(ROOT).replace("\\", "/").lower()
    rows = connection.execute(
        "SELECT DISTINCT json_extract(m.data,'$.providerID'),json_extract(m.data,'$.modelID') FROM message m JOIN session s ON s.id=m.session_id WHERE lower(replace(s.directory,char(92),'/'))=? AND json_extract(m.data,'$.role')='assistant'",
        (directory,),
    ).fetchall()
    connection.close()
    result = [{"provider": row[0], "model": row[1]} for row in rows]
    (ROOT / "license-audit/project-generation-models.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--terms", action="store_true")
    parser.add_argument("--models", action="store_true")
    args = parser.parse_args()
    if args.terms:
        terms()
    elif args.models and args.database:
        project_models(args.database.resolve())
    elif args.database:
        inspect(args.database.resolve(), args.output)
    else:
        parser.error("--database or --terms required")
