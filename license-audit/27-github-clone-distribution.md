# GitHubクローン配布のライセンス判定（2026-10-03）

**更新（2026-10-06）**: 1.1.0の両OS最終判定は [31-cross-platform-clone-distribution.md](31-cross-platform-clone-distribution.md)。本文のWindows向け条件は継続します。

## 判定

**READY FOR CLONE DISTRIBUTION** — このリポジトリをGitHubへ公開し、`git clone` で配布する範囲
（Git追跡内容: アプリソース、ライセンス原文、対応ソース、同梱payload）について、再配布条件を証拠付きで整理した。
利用中フォルダーの丸ごとコピーは対象外（Cookie・購入履歴DB・購入物・profileを含むため。README/PORTABLE参照）。
本判定は法的意見ではなく、リポジトリ内の証拠に基づく技術的整理である。

## 配布範囲と除外

- 対象: Git追跡内容すべて。`vendor/windows-x64/*.chunk` の固定CPython・SQLite・62wheel・WebView2。
- 除外（cloneに含まれない）: `.cache/`、`.tools/`、`.venv/`、`.playwright-browsers/`、`app.db`、`data/`、
  `BOOTH-Reader-Library/`、`audit/*.json|xml|png`、`license-audit` の私用receipt（`.gitignore`）。
- 旧Playwright Chromium/FFmpeg payloadは公開リポジトリに含めない（公開履歴をクリーン化。旧履歴はローカル保全のみ）。

## コンポーネント別根拠

| コンポーネント | 版 | ライセンス/条件 | 証拠 |
|---|---|---|---|
| プロジェクトコード | 1.0.3 | MIT | `LICENSE`、`26-public-source-release.md`（初期生成の由来・出力権利条項の要約） |
| CPython (PBS) | 3.12.13 / 20260325 | PSF-2.0 + 同梱通知 | `THIRD_PARTY_LICENSES/CPython-3.12.13`、`pbs-correspondence.json`（full archiveと全3,371ファイルbyte一致） |
| VCランタイム | vcruntime140.dll / vcruntime140_1.dll | Microsoft再配布可能ファイル | `license-audit/evidence/redistribution/msvc-redistributing-files.html` |
| SQLite | 3.53.4 | Public domain | `portable-manifest.json`、`license-audit/packages.json` |
| 固定wheel | 62パッケージ | 各上流ライセンス | `requirements-portable-lock.txt`（hash固定）、`license-evidence.json`、`THIRD_PARTY_LICENSES/` |
| Playwright / Node | 1.63.0 / Node 24.21.0 | Apache-2.0 + Puppeteer/Node通知 | `THIRD_PARTY_LICENSES/playwright-1.63.0` |
| WebView2 | Fixed 154.0.4258.53 / SDK 1.0.4258.31 | Microsoft WebView2 Runtime License（DISTRIBUTABLE CODE） | 下記参照 |
| pip内urllib3 | 2.8.0（派生） | MIT + 改変記録 | `tools/pip_runtime_patch.py`、`license-audit/security-embedded-vendors.json` |

### WebView2の再配布根拠

`WEBVIEW2-RUNTIME-LICENSE.txt` の Section 2「DISTRIBUTABLE CODE」が、アプリケーションの一部としての
複製・配布を許可している（重要な主機能の追加、エンドユーザーへの保護条項の継承、Microsoftからの直接取得、
商標の非暗示、単体提供の禁止などの条件付き）。原文はvendor snapshot内の `WEBVIEW2-RUNTIME-LICENSE.txt` と
`THIRD_PARTY_LICENSES/browser/15bc46c641bc-WEBVIEW2-RUNTIME-LICENSE.txt`、SDKは
`THIRD_PARTY_LICENSES/browser/0af8f1b80751-webview2-sdk_LICENSE.txt` に保持している。

取得は公式CAB（Authenticode: Valid Microsoft Corporation）とNuGet公式SDK（publisher SHA-512照合）で、
`license-audit/evidence/redistribution/webview-acquisition.json` と `webview2-distribution.html`
（Microsoft公式配布ガイド）に記録した。Chrome for Testing・Chromium headless shell・FFmpegは非同梱
（`portable-manifest.json` の `excludedComponents`）。

## プライバシー

- `tools/check_release_hygiene.py --git-only`: 追跡・追加候補・到達可能履歴の私用パス 0。
- 秘密スキャン: `license-audit/secret-scan.json` / `secret-triage.json`、未解決0（合成fixtureのみ、値は保持しない）。
- 個人データ（Cookie・購入履歴DB・購入物・ブラウザprofile）はGit外に保存し、cloneへ含まれない。

## 残る制限（配布の停止事由ではない）

- 実BOOTHアカウントでのログイン〜購入取得〜ダウンロード、別OS/実Pythonバージョン、GitHub runner実行は未検証。
- nativeバイナリの全byteに対するlicense-to-file対応は、記録した台帳・inventoryの範囲に限る。完全な法的診断ではない。
- 本レポートは `19-release-readiness.md` の旧BLOCKED判定（旧Chrome/FFmpeg構成・フォルダーコピー前提）を置き換える。
