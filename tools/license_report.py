"""Assemble a conservative, evidence-linked compliance report and partial SBOM."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.license_compliance import AUDIT, digest, dump, fetch, retain  # noqa: E402


def load(name: str):
    return json.loads((AUDIT / name).read_text(encoding="utf-8"))


def notice_label(package: dict) -> str:
    # Reviewed exact upstream LICENSE texts; metadata alone omitted these labels.
    reviewed = {
        ("colorama", "0.4.6"): ("BSD-3-Clause", "cac35c02686e"),
        ("markdown-it-py", "4.2.0"): ("MIT", "4a2260d6e2cd"),
        ("mdurl", "0.1.2"): ("MIT", "7c605df6e286"),
        ("pathspec", "1.1.1"): ("MPL-2.0", "fab3dd6bdab2"),
        ("pip-api", "0.0.35"): ("Apache-2.0", "14ed54990120"),
        ("pip-audit", "2.10.1"): ("Apache-2.0", "0d542e0c8804"),
        ("tomli-w", "1.2.0"): ("MIT", "b80816b0d530"),
    }
    label, prefix = reviewed.get((package["name"], package["version"]), ("", ""))
    for notice in package["notices"]:
        if label and notice["sha256"].startswith(prefix):
            if digest((ROOT / notice["path"]).read_bytes()) != notice["sha256"]:
                raise RuntimeError("Reviewed license original changed")
            return label
    value = package["reported_license"]
    return value if len(value) < 100 else "原文metadata参照"


def md(name: str, title: str, text: str) -> None:
    (AUDIT / name).write_text(
        f"# {title}\n\n監査日: 2026-10-02。判定: **BLOCKED**。\n\n{text}\n", encoding="utf-8"
    )


def acquire() -> None:
    sources = {
        "python-distributions": "https://raw.githubusercontent.com/astral-sh/python-build-standalone/20260325/docs/distributions.rst",
        "playwright-registry": "https://raw.githubusercontent.com/microsoft/playwright/v1.63.0/packages/playwright-core/src/server/registry/index.ts",
        "playwright-license": "https://raw.githubusercontent.com/microsoft/playwright/v1.63.0/LICENSE",
        "winldd-readme": "https://raw.githubusercontent.com/microsoft/playwright/v1.63.0/browser_patches/winldd/README.md",
        "ffmpeg-build-attempt": "https://raw.githubusercontent.com/microsoft/playwright/v1.63.0/browser_patches/ffmpeg/build.sh",
        "openssl-license": "https://raw.githubusercontent.com/openssl/openssl/openssl-3.5.5/LICENSE.txt",
        "sqlite-copyright": "https://www.sqlite.org/copyright.html",
        "cpython-license": "https://raw.githubusercontent.com/python/cpython/v3.12.13/LICENSE",
        "cpython-libffi-license": "https://raw.githubusercontent.com/python/cpython/v3.12.13/Modules/_ctypes/libffi_osx/LICENSE",
        "ffmpeg-legal": "https://ffmpeg.org/legal.html",
    }
    evidence = []
    tree_url = "https://api.github.com/repos/microsoft/playwright/git/trees/v1.63.0?recursive=1"
    try:
        tree = json.loads(fetch(tree_url))
        matching = [item["path"] for item in tree["tree"] if "ffmpeg" in item["path"].lower()]
        dump(
            AUDIT / "evidence/playwright-ffmpeg-paths.json",
            {"url": tree_url, "paths": matching, "truncated": tree.get("truncated")},
        )
        for path in matching:
            if path.endswith((".sh", ".md")):
                sources["ffmpeg-" + Path(path).stem] = (
                    "https://raw.githubusercontent.com/microsoft/playwright/v1.63.0/" + path
                )
    except (OSError, ValueError, KeyError) as exc:
        evidence.append(
            {
                "name": "ffmpeg-tree",
                "url": tree_url,
                "status": "NOT VERIFIED",
                "error_type": type(exc).__name__,
            }
        )
    for name, url in sources.items():
        try:
            data = fetch(url)
            target = AUDIT / "evidence/upstream" / (name + ".txt")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            evidence.append(
                {
                    "name": name,
                    "url": url,
                    "path": target.relative_to(ROOT).as_posix(),
                    "sha256": digest(data),
                    "status": "retrieved",
                }
            )
            if name in {"openssl-license", "cpython-license", "playwright-license"}:
                retain(name, "LICENSE.txt", data, url)
        except (OSError, ValueError) as exc:
            evidence.append(
                {
                    "name": name,
                    "url": url,
                    "status": "NOT VERIFIED",
                    "error_type": type(exc).__name__,
                }
            )
    # Embedded terms are primary evidence for this actual executable.
    from playwright.sync_api import sync_playwright

    from core.portable import apply_portable_env

    apply_portable_env(ROOT)
    for name, executable, flag in (
        ("ffmpeg-version", ROOT / ".playwright-browsers/ffmpeg-1011/ffmpeg-win64.exe", "-version"),
        ("node-version", ROOT / ".venv/Lib/site-packages/playwright/driver/node.exe", "--version"),
    ):
        result = subprocess.run(
            [str(executable), flag], capture_output=True, check=True, timeout=30
        )
        output = result.stdout + result.stderr
        target = AUDIT / "evidence" / (name + ".txt")
        target.write_bytes(output)
        evidence.append(
            {
                "name": name,
                "path": target.relative_to(ROOT).as_posix(),
                "sha256": digest(output),
                "source": executable.relative_to(ROOT).as_posix(),
            }
        )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            executable_path=str(
                next((ROOT / ".playwright-browsers/chromium-1243").rglob("chrome.exe"))
            ),
        )
        try:
            page = browser.new_page()
            for name in ("credits", "terms"):
                page.goto("chrome://" + name + "/")
                data = page.content().encode("utf-8")
                text = page.locator("body").inner_text().encode("utf-8")
                evidence.append(
                    retain(
                        "Chrome-153.0.8010.12",
                        name + ".html",
                        data,
                        "embedded:chrome://" + name + "/",
                    )
                )
                evidence.append(
                    retain(
                        "Chrome-153.0.8010.12",
                        name + ".txt",
                        text,
                        "embedded:chrome://" + name + "/",
                    )
                )
            evidence.append({"browser_version": browser.version, "source": "actual executable"})
        finally:
            browser.close()
    dump(AUDIT / "upstream-evidence.json", evidence)
    print(f"Retained {len(evidence)} upstream/browser evidence records")


def report() -> None:
    packages, files = load("packages.json"), load("archive-files.json")
    notices = load("license-evidence.json")
    blockers = [
        {
            "id": "LC-01",
            "component": "初期・既存プロジェクトコード",
            "status": "NOT VERIFIED",
            "reason": "最初のcommitは既に完成した0.1.0のsnapshot。Git作者名・MIT宣言は独立作成や入力コードの権利を証明しない。",
            "investigation": "全6commit、全追跡ファイルの初回commit、出自マーカー、共通作業記録を照合。remote/submoduleなし。",
            "action": "UNKNOWNを維持。生成元サービス・モデル・利用時のOutput Terms・入力素材とコピー元の記録が必要。",
            "alternative": "不明部分は全主要機能に及び、既存表現を読んだ状態の書換えを独立再実装と認定できない。仕様と実装の独立した由来確認が必要。",
        },
        {
            "id": "LC-02",
            "component": "CPython/PBSとWindows CRT",
            "status": "NOT VERIFIED",
            "reason": "install_onlyアーカイブはPYTHON.jsonとビルド資料を含まない。複合ライセンス・バージョン・CRT配布条件の閉包が未確認。",
            "investigation": "原本全ファイル・LICENSE.txt・Tcl/Tk/Tix通知・内蔵pip通知を保全。原文Windows additional conditionsを確認。",
            "action": "SQLite差替えをNOTICEへ明記。対応full archiveのPYTHON.json/パッチとMSVCの適用契約・再配布権を特定する。",
            "alternative": "OS-only/offline起動に必要。別Pythonバイナリも同じ監査が必要で、除去すると承認済みポータブル機能を失う。",
        },
        {
            "id": "LC-03",
            "component": "Chrome for Testing/headless shellと付属素材",
            "status": "NOT VERIFIED",
            "reason": "Google Chrome利用条件とembedded creditsを保存したが、実バイナリ全素材と個別ライセンスの対応・再配布許諾は未確定。",
            "investigation": "153.0.8010.12/revision1243、ABOUT、実chrome://terms/credits、全DLL/pak/dat/ロケールを確認。Chromium BSDをChrome全体へ適用しない。",
            "action": "terms/creditsを原文収録。必要な個別条件の閉包と再配布権の証拠を取得する。",
            "alternative": "実ブラウザーは唯一のログイン経路。ユーザーのブラウザー依存へ変えるとOS-only/offline動作を満たさず、別エンジンも再監査が必要。",
        },
        {
            "id": "LC-04",
            "component": "FFmpeg revision1011",
            "status": "ACTION REQUIRED",
            "reason": "COPYING.LGPLv2.1だけでは対応ソース提供・改変・リンク条件を満たしたと確認できない。",
            "investigation": "原本exeとLGPL本文を保全。-versionでn7.0.1-playwright-build-1011、GCC9.3、static/libvpx/zlibを実測。使用タグのtreeにffmpeg build資料はなく旧pathは404。",
            "action": "対応する完全ソース・パッチ・ビルド構成と提供方式を取得するか、未使用動画機能を含めた依存検証のうえ配布payloadから除外する。",
            "alternative": "原本を保持して候補を監査。削除によるPlaywrightの環境検証/修復/既存fixtureへの影響を検証するまで解決済みにしない。",
        },
        {
            "id": "LC-05",
            "component": "Node/Playwright/ネイティブwheel/内蔵依存",
            "status": "NOT VERIFIED",
            "reason": "wheel主ライセンスだけでは静的リンクライブラリ・npm bundles・内蔵pip/certifi・データセットの閉包を保証できない。",
            "investigation": "全wheel内部ファイル/ネイティブ/入れ子metadata/headers、Node LICENSE、Playwright sidecar noticesを保全。",
            "action": "未解決の内蔵コンポーネントを台帳へ列挙。ソース/lock/ビルド情報とlicense-to-file対応を確認する。",
            "alternative": "一括置換は同じネイティブ閉包確認が必要。依存を単に減らしただけで残存の出自をPASSにしない。",
        },
        {
            "id": "LC-06",
            "component": "完全性・クリーン環境・実サービス",
            "status": "NOT VERIFIED",
            "reason": "同一Windowsホストの独立展開は可能だが別OS image/実BOOTHログイン・DL・upgradeの証拠はない。バイナリ脆弱性閉包と全履歴秘密検査も部分的。",
            "investigation": "同梱アーカイブとpip-audit対象を明示、過去結果を新しい候補の完了証明へ流用しない。",
            "action": "候補展開スモークを実施。管理対象外のアカウント/別OS検証とbinary advisory確認を完了する。",
            "alternative": "有効なBOOTH資格情報や別OS環境を捏造しない。",
        },
    ]
    pruning = AUDIT / "browser-pruning.json"
    if pruning.is_file() and not any(
        "ffmpeg-" in r["path"] and r["container"] == "browser" for r in files
    ):
        blockers = [b for b in blockers if b["id"] != "LC-04"]
    correspondence = AUDIT / "pbs-correspondence.json"
    if correspondence.is_file() and load("pbs-correspondence.json")["status"] == "PASS":
        block = next(b for b in blockers if b["id"] == "LC-02")
        block["reason"] = (
            "対応full archiveのPYTHON.jsonと原文19件を取得し、install_onlyの全3371ファイルとbyte一致を確認。CRT再配布契約と残る複合素材の条件確認は未完了。"
        )
        block["investigation"] = (
            "pbs-correspondence.json、pbs-embedded-components.json、タグ固定Windows build.pyを保存。bzip2/libffi/OpenSSL/liblzma/SQLite/Tcl/Tixのリンクと原文を追跡。"
        )
        block["action"] = (
            "取得済みライセンスと内包ファイルの対応を完成し、適用MSVC契約・再配布権を特定する。"
        )
    if (AUDIT / "security-embedded-vendors.json").is_file():
        blockers.append(
            {
                "id": "LC-07",
                "component": "pip内包ライブラリのadvisory適用範囲",
                "status": "NOT VERIFIED",
                "reason": "ensurepip25.0.1/初期pip26.0.1/固定pip26.2.1のvendor宣言にも既知advisory候補がある。top-level62依存の検出0件だけではセキュリティ閉包を証明できない。",
                "investigation": "3系統のvendor.txtを実原本から取得して個別pip-audit。security-embedded-vendors.json参照。重複advisory、削除されたupstream機能、C extension非同梱、vendor patchを区別する。",
                "action": "各実ファイルと呼出条件を照合し、該当箇所の更新/パッチ/除外を検証。upstream版を変えた場合はライセンスとsourceを再監査。",
                "alternative": "公式setupはno-index/no-deps/require-hashesで外部package indexを利用せず、本体通信はhttpx。これは同梱ライブラリ全体を修正済みとする証明ではない。",
            }
        )
    ledger = []
    for p in packages:
        texts = [
            (ROOT / n["path"]).read_text(encoding="utf-8", errors="replace") for n in p["notices"]
        ]
        copyright_lines = sorted(
            {
                line.strip()
                for text in texts
                for line in text.splitlines()
                if re.search(r"copyright|\(c\)", line, re.I)
            }
        )
        ledger.append(
            {
                "Component ID": p["id"],
                "Component Name": p["name"],
                "Component Type": "Python wheel",
                "Version": p["version"],
                "Local Path": "vendor/windows-x64/ (wheels archive) / " + p["wheel"],
                "Original Source": p.get("registry", {}).get("url", "NOT VERIFIED"),
                "Original Repository": p["upstream"],
                "Upstream URL": p["upstream"],
                "Copyright Holder": copyright_lines or ["NOT VERIFIED"],
                "Author": p["authors"],
                "License": p["reported_license"],
                "SPDX Identifier": "NOT VERIFIED (metadata is not adjudication)",
                "License Version": "see verbatim evidence",
                "License Evidence": p["notices"],
                "Usage": p["role"],
                "Source / Binary": "wheel contents: archive-files.json",
                "Modified": "original wheel SHA-256 verified; installation generates local metadata/bytecode",
                "Modification Details": "no wheel byte modifications",
                "Linked": "Python imports; native extensions when present",
                "Link Type": "dynamic Python/native load; embedded static closure NOT VERIFIED"
                if p["native_files"]
                else "Python imports",
                "Bundled": True,
                "Distributed": "local candidate only; public release BLOCKED",
                "Runtime Download": False,
                "Commercial Use": "NOT VERIFIED for complete closure",
                "Redistribution": "NOT VERIFIED for complete closure",
                "Required Attribution": "retain all evidence copyright/notice texts",
                "Required License Copy": p["notices"],
                "Required NOTICE": "retain shipped NOTICE/sidecars without modification",
                "Required Source Disclosure": "certifi source provided; nested closure NOT VERIFIED"
                if p["name"] == "certifi"
                else "NOT VERIFIED for nested closure",
                "Required Modification Notice": "no wheel patch; retain upstream patch notices",
                "Copyleft Scope": "MPL files for certifi; nested terms require individual analysis"
                if p["name"] == "certifi"
                else "NOT VERIFIED for complete closure",
                "Patent Terms": "see actual texts; no independent patent clearance",
                "Trademark Restrictions": "no endorsement permission inferred; actual texts apply",
                "Additional Restrictions": "NOT VERIFIED for complete closure",
                "Verification Evidence": p.get("registry", {}),
                "Compliance Actions": "all discovered original notices now copied into distribution; certifi/packageurl sdist supplied",
                "Final Status": "NOT VERIFIED",
                "Classification": "THIRD-PARTY",
                "Notes": {
                    "native": p["native_files"],
                    "nested": p["nested_metadata"],
                    "source_markers": p["source_markers"],
                },
            }
        )
    for b in blockers:
        ledger.append(
            {
                "Component ID": b["id"],
                "Component Name": b["component"],
                "Component Type": "aggregate unresolved audit boundary",
                "Classification": "UNKNOWN" if b["id"] == "LC-01" else "THIRD-PARTY",
                "Final Status": b["status"],
                "Notes": b,
            }
        )
    dump(AUDIT / "component-ledger.json", ledger)
    dump(
        AUDIT / "release-gate.json",
        {
            "release_status": "BLOCKED",
            "blockers": blockers,
            "input_hashes": {},
            "date": "2026-10-02",
        },
    )
    nested = [{"parent": p["id"], **n} for p in packages for n in p["nested_metadata"]]
    nested.extend(load("embedded-python-packages.json"))
    dump(AUDIT / "nested-components.json", nested)
    components = [
        {
            "type": "library",
            "bom-ref": p["id"],
            "name": p["name"],
            "version": p["version"],
            "purl": p["id"],
            "hashes": [{"alg": "SHA-256", "content": p["sha256"]}],
            "properties": [
                {"name": "audit:clearance", "value": "NOT VERIFIED"},
                {"name": "audit:role", "value": p["role"]},
            ],
        }
        for p in packages
    ]
    for n in nested:
        components.append(
            {
                "type": "library",
                "bom-ref": n["parent"] + ":embedded:" + n["name"] + "@" + n["version"],
                "name": n["name"],
                "version": n["version"],
                "properties": [
                    {"name": "audit:clearance", "value": "NOT VERIFIED"},
                    {"name": "audit:parent", "value": n["parent"]},
                    {"name": "audit:location", "value": n["path"]},
                ],
            }
        )
    vendor_requirements = AUDIT / "embedded-vendor-requirements.json"
    if vendor_requirements.is_file():
        for parent in load("embedded-vendor-requirements.json"):
            for name, version in re.findall(
                r"^\s*([\w.-]+)==([^\s]+)", parent["requirements"], re.M
            ):
                components.append(
                    {
                        "type": "library",
                        "bom-ref": parent["parent"] + ":vendor:" + name + "@" + version,
                        "name": name,
                        "version": version,
                        "properties": [
                            {"name": "audit:clearance", "value": "NOT VERIFIED"},
                            {"name": "audit:parent", "value": parent["parent"]},
                            {"name": "audit:evidence", "value": parent["path"]},
                        ],
                    }
                )
    for c in load("containers.json"):
        components.append(
            {
                "type": "file",
                "bom-ref": "archive:" + c["name"],
                "name": c["name"],
                "hashes": [{"alg": "SHA-256", "content": c["sha256"]}],
            }
        )
    dump(
        AUDIT / "sbom.cdx.json",
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "component": {"type": "application", "name": "BOOTH-Reader", "version": "1.0.3"},
                "properties": [
                    {
                        "name": "audit:scope",
                        "value": "PARTIAL: pinned wheels and archive containers; embedded native/npm/data closure unresolved",
                    }
                ],
            },
            "components": components,
            "dependencies": [
                {
                    "ref": p["id"],
                    "dependsOn": [
                        next(q["id"] for q in packages if q["name"] == name)
                        for name in p["dependencies"]
                    ],
                }
                for p in packages
            ],
        },
    )
    table = "| Component | Version | Role | Reported license | Primary notices | Status |\n|---|---|---|---|---|---|\n"
    for p in packages:
        label = notice_label(p)
        table += f"| {p['name']} | {p['version']} | {p['role']} | {label.replace('|', '/')} | {len(p['notices'])} | NOT VERIFIED |\n"
    third_party = "# Third-Party Notices — 監査候補\n\n正式リリース: **BLOCKED**。\n\n"
    third_party += "本体のMIT宣言は第三者の条件を上書きしません。下表はmetadataの申告と使用版原文の確認結果です。\n"
    third_party += "正式な使用版原文・著作権表示・NOTICEは `THIRD_PARTY_LICENSES/` に改変せず収録しています。\n"
    third_party += "取得元/元ファイル名/SHA-256は `license-audit/license-evidence.json`、義務と未確認範囲はcomponent-ledger.jsonを参照。\n\n"
    third_party += table
    third_party += "\n## バイナリ・内蔵依存\n\nCPython 3.12.13/PBS20260325、SQLite3.53.4、Chrome153.0.8010.12/rev1243、winldd1007、Playwright1.63.0内のNode24.21.0を含みます。\n"
    third_party += "CPython初期アーカイブ内のpip26.0.1も配布対象で、セットアップ後のpip26.2.1だけでは台帳が閉じません。\n"
    third_party += "ensurepip内のpip25.0.1も別に同梱されています。3系統のpipが内包するcertifiの実ソース22ファイルをSOURCE_OBLIGATIONS/vendored-certifi-source.tar.gzへ収録しました。\n"
    third_party += "NodeはMIT単一ではなく、同梱LICENSEに依存ライブラリの原文を含みます。PlaywrightにはPuppeteer由来コードとnpm sidecarsがあります。\n"
    third_party += "Chromeは実行ファイルのterms/creditsを収録しましたが、ChromiumのBSDを全バイナリへ適用していません。\n"
    third_party += "FFmpeg1011は未使用の動画記録機能用で、現行配布候補のbrowser snapshotから除外しました。旧chunk・旧配布物は配布許可の対象外です。browser-pruning.jsonを参照。certifi2026.7.22とpackageurl-python0.17.6は同版公式sdistをSOURCE_OBLIGATIONSへ収録しました。\n"
    third_party += "元通知の保全だけで再配布権・全義務の充足を断定しません。詳細はlicense-audit/19-release-readiness.md。\n"
    third_party += "\npathspecのMPL-2.0対応ソースと固定wheelとの一致証拠は `SOURCE_OBLIGATIONS/README.md`、`license-audit/pathspec-source.json` を参照してください。\n"
    (ROOT / "THIRD_PARTY_NOTICES.md").write_text(third_party, encoding="utf-8")
    md(
        "01-project-provenance.md",
        "プロジェクト由来",
        "HEAD: `0028a5fd70370087f7da49f6bda9213b9e659b61`。全6commitを独立列挙。\n"
        "remote設定とsubmoduleはなし。公開URLはpyproject内の宣言でありfork元の証拠ではない。\n"
        "最初の240edc9は完成コードのbaselineで、作成前の履歴なし。著作者名だけでFIRST-PARTY認定しない。\n"
        "開始時の既存変更・ユーザーデータ・旧配布物を保全。`repository-inventory.json`、`local-inventory.json`、`evidence/git-history.txt`参照。",
    )
    md(
        "02-component-inventory.md",
        "構成要素台帳",
        f"集計単位: {len(packages)}個の固定wheelと{len(blockers)}個の未完了監査境界。入れ子・個別ファイルは重複集計しない。\n\n{table}\n"
        "全要求フィールドは `component-ledger.json`。不明事項はNOT VERIFIEDと明記。バイナリ内部閉包の総数は未確定。",
    )
    md(
        "03-source-code-provenance.md",
        "ソースコード由来",
        "全追跡ファイルの初回commitとSHA-256、コメントの出自マーカーを採取。\n"
        "`source-markers.json`は行番号とキーワードだけを記録。core/webに明示的コピー元ヘッダーを検出しなかったことは独自性の証拠ではない。\n"
        "Git履歴では初回snapshot前を追跡できない。共通M0/M1-M5作業記録はエージェント実装を示すがモデル/入力コードを特定しない。\n"
        "外部全コードの類似性検索は未完了。生成元と入力コードの由来が確認できるまでUNKNOWN。新しい監査ツールもAI生成であり無条件FIRST-PARTYにしない。",
    )
    md(
        "04-external-repositories.md",
        "外部リポジトリ監査",
        "実使用の版/URLは `packages.json` とregistry evidence。\n"
        "CPython/PBS20260325、Playwright v1.63.0、Node同梱LICENSEが示すJoyent由来、Playwright NOTICEが示すPuppeteerを確認。\n"
        "Playwrightの使用ファイルはwheel全ファイルとdriver/npm bundle。Apache LICENSE/NOTICE/sidecarsを原文保持。\n"
        "winldd同タグREADMEはVS2019/static CRT/dbghelpを明記するがrevision1007バイナリとのbyte対応・CRT権利は未完了。\n"
        "登録upstream URLはソース一致の証明ではない。未公開・記録されなかった参考/コピー元はNOT VERIFIED。`upstream-evidence.json`参照。",
    )
    md(
        "05-dependency-tree.md",
        "固定依存の完全展開",
        "62wheelを原本から解析し全62SHA-256を使用版PyPI JSONと再照合。\n"
        "環境markerが有効なRequires-Distを版制約と照合。非有効marker/extra/optional条件もpackages.jsonに保存。\n"
        "実行/開発/ビルドを区別してもvendorに入る全62個は配布監査対象。\n"
        "トップレベルPython閉包は列挙済み。Node/npm、Rust静的依存、CPython内蔵pipの閉包は未完了。\n\n"
        + "\n".join(
            f"- {p['name']}@{p['version']} → {', '.join(p['dependencies']) or 'なし'}"
            for p in packages
        ),
    )
    native = [r for r in files if r["native"]]
    assets = [r for r in files if r["asset"]]
    dump(AUDIT / "binary-inventory.json", native)
    dump(AUDIT / "asset-inventory.json", assets)
    md(
        "06-binary-inventory.md",
        "バイナリ監査",
        f"ネイティブ/ライブラリファイル: {len(native)}。全件のcontainer/path/size/hashはbinary-inventory.json。\n"
        "exe/dll/pyd/lib等をアーカイブ内部まで列挙。分割.chunkはバイナリを隠すだけで配布義務をなくさない。\n"
        "CPython・VC CRT・Node・Chrome・winldd・compiled wheelのlicense-to-file対応/静的リンク閉包は未確認。FFmpegは現行配布snapshotから除外。\n"
        "OSのcmd/PowerShell/tar/whoami/icacls/dbghelp等は要求するがOSファイルをコピーして配布していない。",
    )
    md(
        "07-asset-inventory.md",
        "素材監査",
        f"依存内の画像/ico/svg/pak/dat等: {len(assets)}。全件asset-inventory.json。\n"
        "本体ソースには追加外部フォント・音声・モデルの参照を確認しなかったが、browser/python/tool内素材は別途対象。\n"
        "Chromeロケール・pak/dat、Python/Tclデモ画像、tool内テストデータの個別著作者/条件は未確定。\n"
        "BOOTH購入物/DB/Cookieは私有データとして除外し配布していない。購入は再配布権の証拠ではない。",
    )
    md(
        "08-ai-model-and-dataset-audit.md",
        "AI・生成物監査",
        "本体がAIモデルやモデル重みをロードする依存/設定は検出していない。\n"
        "既存コードのエージェント生成は過去記録から確認できるが利用サービス/モデル/当時規約/入力の外部コードが未記録。\n"
        "今回の監査コード/文書はOpenCode経由openai/gpt-6.1-sol生成。これも著作権上の独自性・入力履歴・サービス契約を証明しない。\n"
        "lockはgen_lock.py生成、wheelは各upstreamビルド、stdlib bytecode/venvはCPython生成。\n"
        "certifi CAデータ、license-expression SPDXデータ、Pygments文法/例示データ、Chromeロケールをデータ監査へ含める。\n"
        "Output Termsとモデルライセンスを混同せず、情報のない生成物をFIRST-PARTY/PASSにしない。",
    )
    md(
        "09-license-evidence.md",
        "一次ライセンス証拠",
        f"アーカイブ抽出通知: {len(notices)}件。\n"
        "license-evidence.jsonには元パス・取得容器・hash・配布先。原文はTHIRD_PARTY_LICENSES。\n"
        "全62使用版のPyPI情報はevidence/registry。メタデータのみで法的許諾を確定しない。\n"
        "公式タグ/doc/実ブラウザー証拠はupstream-evidence.json。404等失敗も保持。packageurlのmain通知だけに依存する状態を同版sdist取得で修正。",
    )
    with (AUDIT / "09-license-evidence.md").open("a", encoding="utf-8") as stream:
        stream.write(
            "\n2026-10-02追加: reaudit-upstream.json、PBS対応full archiveのPYTHON.json、pbs-correspondence.jsonで原本3371ファイル一致と追加19通知を確認。Chrome追加規約と使用版Node原文も取得。これだけで再配布契約の成立は確定しない。\n"
        )
    md(
        "10-license-obligations.md",
        "義務解析",
        "- MIT/ISC: 著作権・許諾・免責の原文保持。\n"
        "- BSD: source/binary条項に沿った原文保持、BSD-3では権利者名のendorsement不可。\n"
        "- Apache-2.0: LICENSEと該当NOTICE、改変通知、著作権保持、特許許諾/終了条項。商標許諾は別。\n"
        "- PSF: LICENSE/著作権保持、派生変更要約。Windows追加条件はMITへ統合しない。\n"
        "- MPL: 対象ファイルのSource Code Formと入手案内。certifi同版sdistを同梱。別版の内蔵certifiを同じsdistで充足しない。\n"
        "- LGPL: COPYING保持だけでなく実バイナリに対応したソース・改変・リンク条件の充足。FFmpegは現行payloadから除外し、旧配布物/履歴は未許可。\n"
        "- Tcl/Tk/Tix/複合データ/独自条件: 実原文を保持し適用範囲の閉包を特定。\n"
        "個別Commercial Use/Redistribution/Patent/Trademark判断は台帳の未確認項目を維持。",
    )
    md(
        "11-license-compatibility.md",
        "互換性",
        "本体MIT宣言と第三者の許諾を分離。Python import、pyd動的load、Playwright Node別process、Chrome別processを区別。\n"
        "別プロセスでも同梱バイナリのソース提供義務は消えない。compiled wheel、Node静的閉包を確認するまで全体互換性PASSにしない。FFmpegは配布対象から除外。\n"
        "MPL certifiファイルを改変していないことは本体全体をMPL化する理由ではないが同版source/noticeは保持。\n"
        "GPL/AGPLを含まないとの全体断定は未実施。専用ネットワーク提供義務も未検出を免除証明にしない。",
    )
    issues = "\n\n".join(
        f"## {b['id']}: {b['component']} — {b['status']}\n\n原因: {b['reason']}\n\n調査: {b['investigation']}\n\n対応: {b['action']}\n\n代替の判断: {b['alternative']}"
        for b in blockers
    )
    md("12-compliance-issues.md", "未解決事項", issues)
    md(
        "13-compliance-actions.md",
        "実施した遵守対応",
        "1. 原本archive/wheel全ファイルと版固定registryを再調査。\n"
        "2. 原文LICENSE/COPYING/NOTICE/AUTHORS/sidecarsをTHIRD_PARTY_LICENSESへ複写。\n"
        "3. certifi/packageurl使用版の公式sdistを取得・hash照合、source提供案内を実装。\n"
        "4. 本体NOTICE、SQLite差替え要約、第三者条件分離を追加。\n"
        "5. wheel/sdist/launcherの収録ルールを修正。\n"
        "6. 通常buildは不足/未解決/stale監査を拒否。--audit-candidateでローカル検証に限定。\n"
        "7. 旧成果物を正式最新版と誤認しないREADME/PORTABLE案内と候補checksumを追加。\n"
        "未確認の権利を新しいMIT宣言・コードの書換えで隠さない。",
    )
    md(
        "14-distribution-inventory.md",
        "配布対象",
        "現行監査候補はdist/license-audit-20261002-finalに生成。以前の候補は現行版の証拠ではない。正式配布の承認ではない。\n"
        "launcherとsdistはvendorのPython/SQLite/wheel/browserアーカイブを含む。wheel自体はbootstrap vendorを同梱しない。\n"
        "THIRD_PARTY_LICENSES/NOTICEをwheel metadataとsource/launcherへ収録、SOURCE_OBLIGATIONSはsource/launcherへ収録。\n"
        "全内部ファイル: distribution-inventory.json、再構成payload内部: archive-files.json、元容器: containers.json。\n"
        "既存dist/release/ローカル環境はlocal-inventory.jsonに識別、今回のクリアランス対象へ混同しない。",
    )
    md(
        "15-source-obligations.md",
        "対応ソース",
        "SOURCE_OBLIGATIONS/README.md参照。certifi2026.7.22公式sdistを同梱し配布と同時に取得できる形にした。\n"
        "packageurl-python0.17.6のMIT原文も同版sdistで証明。\n"
        "FFmpeg1011は現行配布対象から除外。旧chunk・Git履歴・旧配布物の再配布は別途BLOCKED。無根拠なSOURCE_OFFERは作成しない。\n"
        "Python/Nodeの内蔵別版certifi等のsource対象を同一扱いしない。ソース提供の全体ゲートはBLOCKED。",
    )
    md(
        "16-final-package-audit.md",
        "完成候補の検証",
        "最終候補を生成後、verifyでSHA-256/CRC/内部path/user data/ソースbyte一致/全ファイルinventoryを検証する。\n"
        "実行結果はfinal-package-result.json。SBOMはPython62wheelと5容器までの部分版、native/npm/素材閉包は未完了。\n"
        "証拠収録を完全遵守へ読み替えない。独立展開の結果はclean-candidate-result.json。",
    )
    md(
        "17-unverified-components.md",
        "未確認一覧",
        "全62wheelの主LICENSE原文は取得したが、完全な内包閉包の審査はNOT VERIFIED。\n"
        "入れ子metadataはnested-components.json。CPython内蔵pip26.0.1、ensurepip25.0.1とNode/Chrome/CRTを含む。vendor.txt宣言はembedded-vendor-requirements.json。\n"
        "全体の残課題は以下。\n\n" + issues,
    )
    counts = Counter(row["Final Status"] for row in ledger)
    summary = {
        "Total Components": len(ledger),
        "First-party Components": 0,
        "Third-party Components": len(ledger) - 1,
        "Generated Components": 0,
        "Derived Components": 0,
        "Unknown Components": 1,
        "count_scope": f"{len(packages)} wheels + {len(blockers)} aggregate audit boundaries; internal unique total NOT VERIFIED",
        **{
            k: counts[k]
            for k in [
                "PASS",
                "PASS WITH OBLIGATIONS",
                "ACTION REQUIRED",
                "REPLACEMENT REQUIRED",
                "REMOVAL REQUIRED",
                "REIMPLEMENTATION REQUIRED",
                "NOT VERIFIED",
                "BLOCKED",
            ]
        },
        "Final Distribution Audited": "candidate integrity only; license closure BLOCKED",
        "SBOM Verified": "PARTIAL",
        "Required Notices Included": "discovered originals included; completeness NOT VERIFIED",
        "Required Licenses Included": "discovered originals included; completeness NOT VERIFIED",
        "Source Obligations Satisfied": False,
        "Secrets Scan Passed": "scoped rule scan only; false positives reviewed in security report",
        "Clean Environment Test Passed": "independent-folder smoke only; full clean OS/service flow NOT VERIFIED",
        "Release Status": "BLOCKED",
    }
    dump(AUDIT / "final-compliance.json", summary)
    md(
        "18-final-compliance-report.md",
        "最終コンプライアンス報告",
        "**正式配布はBLOCKED**。通知追加とcandidate integrityは、権利/条件閉包の完了ではない。\n\n```json\n"
        + json.dumps(summary, ensure_ascii=False, indent=2)
        + "\n```\n\n"
        "FIRST-PARTY=0は著作権不在を意味せず、この監査基準で独立作成を証明できていないという意味。\n"
        "未知の内部コンポーネント数を総数へ捏造しない。全ファイル数は別のinventoryに記録。",
    )
    md(
        "19-release-readiness.md",
        "最終リリースゲート",
        "## RELEASE STATUS: BLOCKED\n\n"
        "通常ビルドはrelease-gate.jsonで停止。候補は公開・正式リリースしない。\n\n"
        "| Gate | Result |\n|---|---|\n| Provenance/AI input | NOT VERIFIED |\n| Python wheel inventory/hash | 62/62 verified |\n"
        "| Native/npm/assets closure | NOT VERIFIED |\n| Attribution/LICENSE | discovered originals retained |\n"
        "| Source obligations | certifi supplied; FFmpeg excluded; nested incomplete |\n| Compatibility | NOT VERIFIED |\n"
        "| Final package integrity | see final-package-result.json |\n| SBOM | PARTIAL |\n"
        "| Secrets | scoped scan, full binary/history closure unverified |\n| Python advisories | see security-dependencies.json |\n"
        "| Clean test | independent-folder smoke; full OS/service test unverified |\n\n"
        "外部で必要な確認: 初期生成元/入力/コピー記録、適用MSVC契約/権利、Chrome再配布の許諾根拠、未確認内部バイナリ対応ソース/版。"
        "\n有料契約や許諾を持っていると捏造しない。実サービス認証と別OS環境が必要な試験も未完了。\n\n"
        + issues,
    )
    scan = load("secret-scan.json")
    md(
        "20-security-audit.md",
        "セキュリティ・秘密情報",
        "使用版全62Python依存をpip-auditで照合し既知vulnerabilityなし(security-dependencies.json)。\n"
        "これはChrome/Node/CPython/CRT全binaryのCVE完了を意味しない。内包pip3系統の申告版検査にはadvisory候補がありsecurity-embedded-vendors.jsonとLC-07を参照。FFmpegは現行配布対象外。\n"
        f"{scan['historical_text_blobs']}個の到達可能なGit text blobとworktreeを5種ルールで走査。検出{len(scan['findings'])}レコード。"
        "core/logging_setup.pyの赤塗り用ヘッダー、tests/test_auth_security.pyのダミーPEM/テスト文字列、JUnitのテスト識別子を含む。"
        "個別評価はsecret-triage.json。既知のダミーであることを内容/テスト目的で確認した範囲だけ解決する。\n"
        "secret-scan.jsonに値は保存していない。binary history blob/ユーザーデータ/全種類資格情報は未検証。\n"
        "最終候補の追加検出をdistribution inventoryへ記録、未知検出を無条件無視しない。\n"
        "ruff security規則と回帰試験の結果はverification.json。全リポジトリ脆弱性不存在とは断定しない。",
    )
    md(
        "21-build-and-release-notes.md",
        "再生成とリリースノート",
        "## 変更\n\n"
        "1.0.3の機能版は維持。NOTICE/原文ライセンス/同版source/SBOM/監査台帳/ブロックゲートを追加。正式公開は行っていない。\n\n"
        "## 環境\n\nWindows x64、CPython3.12.13/PBS20260325、固定62wheel、setuptools84.0.0/wheel0.48.0/build1.6.1。\n"
        "setupはGit-owned材料からオフライン復元。外部取得は証拠取得時のGitHub/PyPI/公式siteのみ。\n"
        "環境変数はcore.portable.apply_portable_envでrepo内cache/TEMP/PLAYWRIGHT_BROWSERS_PATHを設定。\n\n"
        "```powershell\n.venv\\Scripts\\python.exe tools/license_compliance.py inventory --online\n"
        ".venv\\Scripts\\python.exe tools/license_report.py --acquire\n"
        ".venv\\Scripts\\python.exe tools/license_report.py\n"
        ".venv\\Scripts\\python.exe tools/build_release.py --out dist/license-audit-20261002-final --audit-candidate\n"
        ".venv\\Scripts\\python.exe tools/license_compliance.py verify --directory dist/license-audit-20261002-final\n```\n"
        "出力先が既存なら別の空ディレクトリを指定。package inputsはbyte照合、ZIP/tar timestampによるbit-for-bit再現性は保証しない。\n"
        "最終inventoryは監査後に外部証拠として保存するため、自己参照hashをarchive内部へ後付けしない。",
    )
    print(f"Wrote 21 reports, {len(ledger)} ledger rows, partial SBOM; release BLOCKED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", action="store_true")
    if parser.parse_args().acquire:
        acquire()
    else:
        report()
