# 変更前Baseline

環境: Windows、repo-local CPython 3.12.13。対象は開始時の未コミット変更を含む1.0.2。

| コマンド | 終了 | 結果 |
|---|---|---|
| `.venv\Scripts\python.exe -m pytest -q --basetemp=.cache/audit-baseline-tests` | 0 | 238 passed、31.44秒、7 warnings（Starlette/httpx非推奨） |
| `python -m ruff check .` | 0 | 合格 |
| `python -m ruff format --check .` | 0 | 38 files already formatted |
| `python -m mypy` | 0 | 16 source files合格 |
| `python -m pip check` | 0 | 整合 |
| `python -m pip_audit --local --disable-pip` | 2 | オプション不整合。installed監査は`--local`のみで再実行 |

性能は `tools/audit_probe.py benchmark --out audit/performance-baseline.json`。2,000件HTML/隔離DB、parser3回、warm worker/API7回、中央値と全標本を保存。実BOOTHは未ログインのため未検証。既存テスト合格は未知不具合の不存在を意味しない。
