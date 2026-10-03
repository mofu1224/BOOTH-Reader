# 全体調査（2026-10-01）

## 開始状態と保護

- Git: `main`、HEAD `38a6c29`。追跡済み23ファイルに既存差分、未追跡7ファイル。開始状態は `inventory-baseline.json` に記録する。
- 既存の1.0.2修正・ポータブル化を作業開始時の正本として扱う。reset/clean/stash/commitは行わない。利用者のDB・Cookie・購入ファイルは変更しない。
- 初回調査では、本体16モジュール、全テスト11ファイル、全ツール5ファイル、bat3ファイル、CI、依存定義、README/PORTABLE/CHANGELOG/VERIFY_LOG/通知を確認。

## ファイル分類

| 対象 | 役割・生成元 |
|---|---|
| `cli.py`, `core/*.py`, `web/*.py` | CLI、SQLite、Cookie認証、HTTP、HTML解析、DL/展開、Web表示 |
| `tests/*.py`, `conftest.py` | 正常・異常・回帰・並行処理の自動試験 |
| `tools/*.py` | 配布物生成、RC検証、Python取得、仮想環境修復、ポータブル監査 |
| `*.bat` | Windows起動・セットアップ |
| `pyproject.toml`, `requirements*.txt` | package/pytest/ruff/mypy設定、実行/dev/固定依存 |
| `.github/workflows/ci.yml` | Windows 3.10〜3.13、検証・ビルド・セキュリティ・タグ公開 |
| `README.md`, `PORTABLE.md`, `CHANGELOG.md`, `VERIFY_LOG.md` | 現行仕様、操作、過去変更・検証 |
| `LICENSE`, `THIRD_PARTY_NOTICES.md` | MIT本体、外部依存通知 |
| `.tools/python` | 固定python-build-standaloneアーカイブから取得したCPython・DLL・標準ライブラリ |
| `.playwright-browsers` | Playwright取得のChromium/FFmpeg/winldd |
| `.venv` | 同梱Pythonをベースにpip導入した実行/dev依存 |
| `.cache`, 旧`.pytest_cache/.mypy_cache/.ruff_cache`, `__pycache__` | 再生成可能なツールキャッシュ。既存物は保全 |
| `build`, `booth_reader.egg-info`, `dist`, `release` | setuptools生成物、現行1.0.2配布物、旧0.1.0配布物。旧物は消さず今回成果物は別出力 |
| `app.db` | 利用者のSQLiteデータ。今回検証は隔離DBで行う |

実在ファイルは `tools/audit_probe.py inventory` で再帰的に数・サイズ・ソースハッシュを記録。リンク先を追跡せず、利用者データの内容は収集しない。第三者バイナリは取得スクリプト・package metadata・通知から出所を確認する。

## 外部依存

- Windows標準: cmd、`whoami`, `icacls`。初回だけPython 3.10+とネットワーク、以後`.tools/python`/`.venv`。
- 実行依存: httpx、beautifulsoup4、fastapi、uvicorn、pydantic、playwrightと推移依存（実測一覧JSON）。
- 外部通信: accounts.pixiv.netログイン、accounts.booth.pm/library/orders、booth.pm商品、HTML内DL/CDN、GitHub固定Python asset、PyPI、Playwrightブラウザ配布。
- 設定: `BOOTH_READER_USER_AGENT`, `PLAYWRIGHT_BROWSERS_PATH`, pip/uv/ruff/mypy cache、Python UTF-8。永続PATH/レジストリの設定処理なし。
- 絶対パスは実行時にファイル位置から生成。DB/出力/Cookieは任意指定できる。既存venvは移動後再生成が必要。
- 外部フォント・画像・音声・モデル・DBサーバー・共有ディレクトリの必須依存なし。
