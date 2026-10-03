# 自律監査・修正記録（2026-10-02、HEAD 0028a5f + 未コミット作業）

## 対象・環境・開始状態

- Repository: BOOTH-Reader、branch `main`、HEAD `0028a5f`。コミット・push・公開なし。
- 開始時、36ファイルに未コミット変更（DB schema v2→v4、Web UI分割 `web/ui.py` 新設、
  Cookie stdin import、list sort/reorder、license監査一式）あり。すべて保全し、
  `git reset --hard / clean / checkout -- .` は未使用。
- Windows x64、repo-local CPython 3.12.13（`.venv`）、SQLite WAL、httpx / BeautifulSoup /
  FastAPI / Uvicorn / Pydantic / Playwright + 同梱Chromium。CIは `ci.yml` の
  verify / portable / package / security を参照。

## Baseline（変更前・作業ツリー）

| コマンド | 結果 |
|---|---|
| `-m pytest -q` | 384 passed、約50s、第三者非推奨警告1件のみ |
| `-m ruff check cli.py core web tests tools conftest.py` | PASS |
| `-m ruff check .` | FAIL: 53件（`THIRD_PARTY_LICENSES/` 内の原文保持ソースのみ） |
| `-m ruff format --check .` | FAIL: 同梱原文3件が未整形扱い |
| `-m mypy` | PASS（18 source files） |
| `-m pip check` | PASS |
| `-m pip_audit --local` | 既知脆弱性なし |
| `tools/check_portable.py` | 17/18（`no unmanaged literal external CLI commands` がFAIL） |
| `tools/build_release.py --out <fresh>` | license gateで停止（想定通り、後述） |

## 問題登録・修正（詳細は `04-issue-register.md` の AUD-01 / AUD-02）

| ID | 重大度 / 原因 | 修正 / 検証 |
|---|---|---|
| AUD-01 | Medium / ライセンス原文保持 `THIRD_PARTY_LICENSES/` が ruff 対象のままで、CI verify の `ruff check .` / `ruff format --check .` が失敗 | `pyproject.toml` の `extend-exclude` に `THIRD_PARTY_LICENSES` と `SOURCE_OBLIGATIONS` を追加（原文改変の禁止をコメント化）。CIと同一コマンドで lint / format が PASS。第一者コードの対象範囲は不変 |
| AUD-02 | Medium / `check_portable.py` の外部CLI字面検査が、未コミット作業の正規2件（`launcher_probe.py` の `taskkill`、`license_compliance.py` の `git`）を違反扱いし、CI portable が失敗 | OS標準 `taskkill`（Windows専用・tar/whoami/icaclsと同分類）と監査用途 `git`（既存 `audit_probe.py` 免除の一般化）を検査側で明示許可。偽 `curl` 呼出の陰性対照で検査が依然違反を検出することを確認後、18/18 PASS |

ロールバックは各IDの差分（`pyproject.toml` の2行、`tools/check_portable.py` の許可集合）のみを戻す。
DB schema・vendor・lock・利用者データは変更していない。

## ゼロベース再監査（今回）

- TODO/FIXME/HACK/XXX/WIP/stub/NotImplemented：第一者コードに0件（原文保持の第三者は除外）。
- skip/xfail：`test_portable_bootstrap.py` の win32 条件、`test_portable.py` の source-bundle 条件のみで正当。
  無効化テスト・assertion弱化なし（test差分は fixture配置・UI selector・Cookie隔離の追随）。
- 抑制コメント（noqa / type: ignore / pragma）：全件に理由付記。SQLは固定ORDER_BY allowlist、
  subprocessは固定argv・shellなし、RNGはretry jitter、assertは内部不変条件。
- 空except・握り潰し：`core/` の exceptは型指定あり。BLE001はCLI/Web境界の要約表示用で、
  ログ＋exit code taxonomyを維持。
- 秘密情報：`data/cookies.json`・`app.db`・`BOOTH-Reader-Library/` はuntracked＋gitignore。
  `git ls-files` に該当なし。監査記録に秘密値を残していない。
- ハードコード絶対パス：`SYSTEMROOT` fallback（`C:\Windows`）のみで正当。
- 配布ゲート：`build_release.py` 通常実行は `license clearance BLOCKED` で停止（`license-audit/19`
  の判定どおり）。`--audit-candidate` は wheel/sdist/zip＋SHA256SUMSを正常生成（後削除）。
  これはバグではなく、未解決の外部制約（LC-01〜06）が残る間の正しい動作。

## 最終検証（修正後）

- `-m pytest -q`：**384 passed**、警告は第三者由来1件のみ。
- CI verify相当：`ruff check --output-format=github .` PASS、`ruff format --check --diff .` PASS（115 files）、
  `mypy` PASS、`compileall` PASS、`pip check` PASS、lock dry-run PASS。
- `tools/check_portable.py`：**18/18 PASS**（陰性対照で17/18 FAILを確認後、対照ファイルは削除）。
- Smoke：`--version` / `init-db`（schema v4）/ `unclassified` / `doctor --json`（ok:true、warnings 0）。
- `pip-audit --local`：既知脆弱性なし。

## 未検証・外部制約（変更なし・再掲）

- 実BOOTH認証/購入HTML/購入品DL：有効Cookieなし **BLOCKED**（local HTTP・mock・実Chromiumで代替済み）。
- Windows10/別PC、実Python 3.10/3.11/3.13、GitHub runner実行、長時間soak：**NOT TESTED**。
- 公開配布の可否：**BLOCKED**（`license-audit/19-release-readiness.md` の LC-01〜06。捏造せず維持）。
- 専用Codex Securityスキャンは実行基盤がなく **BLOCKED**（Bandit由来ruff `S`＋pip-auditで代替）。

## 最終品質ゲート

**CONDITIONAL** — 修正可能なCritical/High残件は0。確認済み範囲の全ゲートがPASS。
実サービス疎通・他OS/Python・CI runner・長時間soak・配布許諾閉包は外部制約として残る。

## 変更・証拠一覧

- 本体：`pyproject.toml`（ruff除外2件＋理由）、`tools/check_portable.py`（許可集合の明示化）。
- 記録：本報告、`04-issue-register.md`（AUD-01/02追記）、`06-repair-log.md`（AUD-01/02追記）。
- 検証用に作った `.cache/smoke-audit.db` / `.cache/audit-build-out` / 陰性対照ファイルは削除済み。
  開始時の未コミット変更・未追跡証拠・venv/runtime/browser/cache・利用者DB/Cookieは維持。
