# 配布前・ライセンス監査への引き継ぎ

## 成果物

| 項目 | 参照 |
|---|---|
| ソース | cli.py / core / web / tools、version 1.0.3 |
| 修正履歴 | CHANGELOG.md、audit/06-repair-log.md |
| 問題管理 | audit/04-issue-register.md（BR-A01〜15） |
| テスト | audit/07-test-results.md、junit-final.xml |
| 性能 | audit/08-performance-results.md、performance-*.json |
| 安定性 | audit/09-stability-results.md、stability-final.json |
| security | audit/10-security-results.md |
| 依存 | requirements*.txt、pyproject.toml、inventory-baseline/final.json |
| ライセンス入口 | LICENSE、THIRD_PARTY_NOTICES.md、本ノート |

配布前のローカル成果物は `dist/1.0.3/`:

- `BOOTH-Reader-1.0.3-windows-x64.zip`
- `booth_reader-1.0.3-py3-none-any.whl`
- `booth_reader-1.0.3.tar.gz`
- `SHA256SUMS.txt`

checksum/内容検証と最終RC候補ソースの一致は `audit/artifacts-final.json`（BR-A15追加後は44ファイル）。監査結果JSON/JUnitはrepoの`audit/`に保存し、配布ZIPには説明Markdownのみを含めた。成果物の生成後の閉じ検証はrepoの本ノートとJSONが最新。

## 再現可能なセットアップ・ビルド

Windows x64のポータブル利用は `setup.bat`。固定runtimeを再現する場合:

```powershell
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-lock.txt
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe tools/build_release.py --out dist/1.0.3
.venv\Scripts\python.exe tools/rc_test.py --artifact dist/1.0.3/BOOTH-Reader-1.0.3-windows-x64.zip
```

browser/cacheの既定はrepo-local。明示的に環境変数を設定する場合もPORTABLE.mdの場所へ指定。buildは非empty出力先を拒否するため再実行時は新しい出力ディレクトリを指定する。

lockはWindows/CPython3.12の21runtime。build backendはsetuptools>=77/wheelを要求するが、build/devツールの全バージョンまでhash固定してはいない。byte-identical ZIPの再現を保証する仕様ではない。

## 監査対象の外部コード・バイナリ

- runtime21: annotated-doc, annotated-types, anyio, beautifulsoup4, certifi, click, fastapi, greenlet, h11, httpcore, httpx, idna, playwright, pydantic, pydantic-core, pyee, soupsieve, starlette, typing-extensions, typing-inspection, uvicorn。
- exact versions/hashes: `requirements-lock.txt`。通常開発環境のFastAPIは0.142.2、lockは0.141.1。両環境の検証結果を区別する。
- dev/監査: pytest、ruff、mypy、pip-audit、buildと推移依存。tomliをPython3.10 test用に明示した（既存環境にはpip-audit経由でも存在）。
- setup-download: python-build-standalone `20260325` CPython3.12.13 asset（URL/固定SHA-256はtools/fetch_python.py）、Playwright1.63.0のChromium build1243・headless shell・FFmpeg・winldd。
- Playwright wheel内のNode driver、CPython同梱DLL/stdlib、Chromium/FFmpegの推移ライセンスも確認する。metadataのlicense表記だけで完了判定しない。
- 本体の新規実行依存・外部素材・コピーコードは追加していない。購入コンテンツは利用者の著作物データで配布物へ含めない。
- `.venv`, `.tools`, `.playwright-browsers`, `.cache`, DB/Cookie/library、旧dist/releaseは配布収集から除外。wheelは本体＋tools、sdist/launcherはテスト・bat・設定も含む。

## 対応環境・既知の制限

- 今回実行済み: Windows11 build26200 x64、同梱CPython3.12.13、repo-local Chromium。
- Python3.10/3.11/3.13、Windows10、別PC: CI/仕様上の対象だが今回の実行確認なし。Mac/Linux非対応。
- 実BOOTH認証と著作物DLはCookieがないため未検証。parserはモック/local HTTPで検証した。実サイト変更は明示layout errorになる。
- 商品IDが不明な注文は暫定order_ID。後日のreal IDとの自動統合は現在のschemaにない。ログで暫定IDを報告する。
- rel=next以外の未知pagination、無認証購入API、VCC/FBX、自動分類、公開サーバーは仕様外。
- unsafe/重複ZIP memberはitem処理で拒否。validator無し/legacy部分ファイルは安全のため最初から取り直す。
- background downloadの既定上限は1時間。終了/timeout後に再実行で回復する。数時間の実DL/soakは未実行。
- 本段階ではライセンス監査・実サービス確認・公開承認を代行完了したとは扱わない。
