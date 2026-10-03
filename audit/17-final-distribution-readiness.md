# 最終配布準備レポート（2026-10-03）

GitHubリポジトリのクローン配布に向けた最終点検の記録。公開・push・GitHub CI実行は未実施。

## 対象と目的

- 配布物はGitリポジトリのクローン（Git追跡内容のみ）。配布用ZIP/sdistは作成しない。
- 個人データ（Cookie・購入履歴DB・購入物・ブラウザーprofile）はGit外に保持し、cloneへ含めない。
- WebView2移行後の未検証部分、ライセンス判定、CI、履歴を点検して「配布しても問題ない状態」にそろえた。

## 実施した修正

| ID | 内容 | 修正 |
|---|---|---|
| AUD-03 | WebView2移行後に旧Playwright Chromium前提が残り、`verify_clone.py` の破損復旧検査が `StopIteration` で停止。`rc_test.gate_browser` は `playwright install chromium` のまま。`portable_probe` は `chrome://credits`、doctor/エラー案内・依存台帳も旧表記 | すべてWebView2（`edge://credits`、vendor snapshot復元、`setup.bat --repair`案内）へ追随。doctor名は `browser:webview2` |
| AUD-04 | WebView2/Edgeが分離profile内に作る `Content.IE5` junction（絶対target）がフォルダー移動後の `check_portable` で外部リンク扱いになる | 生成キャッシュ（`.cache` 等）をリンク検査の対象外に。配布対象の検査は不変 |
| AUD-05 | ブラウザー子プロセスが継承profileの `LOCALAPPDATA` 等へ書く／書けない環境で起動不能 | `core/browser.browser_env()` でHOME/USERPROFILE/APPDATA/LOCALAPPDATA/TEMPをリポジトリ内へ固定。回帰テスト追加 |
| AUD-06 | `launcher_probe` が失敗時にサーバー子プロセスを残し、旧試験copyの削除とプロセスを妨げていた | `finally` でbrowserをkillし、serverをプロセスツリーごとtaskkill |
| — | lint/format/型の残件（新規ツールのimport順・未使用noqa・XML解析・例外連鎖） | 解消 |

## 検証結果

- `pytest -q`: **397 passed**（第三者Starlette TestClient非推奨警告1件のみ）。
- `ruff check .` / `ruff format --check .` / `mypy` / `pip check`: PASS。
- `tools/check_portable.py`: **18/18 PASS**。
- `tools/vendor_payload.py verify`: PASS（CPython/SQLite/62wheel/WebView2 chunkのSHA-256）。
- `tools/verify_clone.py`: **PASS**（85 checks、cold Web/CLI、移行、データ/UI、ブラウザー破損復旧、再配置後audit、元index不変、外部profile/temp書込み0。コピー内回帰 **397 passed**）。
- `tools/check_release_hygiene.py --git-only`: 追跡・追加候補・到達可能履歴の私用パス **0**。
- 秘密スキャン（`license-audit/secret-scan.json` / `secret-triage.json`）: 未解決0（合成fixtureのみ、値は保持しない）。

## ライセンス

- 判定 **READY FOR CLONE DISTRIBUTION**。根拠と残る制限は [../license-audit/27-github-clone-distribution.md](../license-audit/27-github-clone-distribution.md)。
- WebView2 Fixed VersionのDISTRIBUTABLE CODE条項、Microsoft公式配布ガイド、VCランタイム再配布条件を一次証拠として保持。
- `release-gate.json` は現行ツリーの `input_hashes` でREADYへ更新（`tools/build_release.py` の通常実行はゲート通過後にのみ成果物を作る）。
- 旧Playwright Chromium/FFmpegは非同梱。公開履歴はクリーンな単一rootとし、旧履歴はローカル保全のみ。

## 残る制限（配布の停止事由ではない）

- 実BOOTHアカウントでのログイン〜購入取得〜DL、別OS/実Pythonバージョン、GitHub Actions runnerでの実行は未検証。
- nativeバイナリのlicense-to-file対応は記録した台帳の範囲。完全な法的診断ではない。
- 公開・pushは未実施。後日公開する場合の入口は [../license-audit/release-gate.json](../license-audit/release-gate.json) と本レポート。
- 公開時はクリーンな `main` のみを push する。旧Chromium/FFmpegを含むローカル保全履歴（backup ref / bundle）を
  `--all` / `--mirror` / `--tags` で送らない。配布対象はクリーン履歴だけとする。
