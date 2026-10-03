# 再監査・修正記録（2026-10-01、HEAD 0028a5f）

## 対象・環境・開始状態

- Repository: BOOTH-Reader、branch `main`、開始/最終HEAD `0028a5fd70370087f7da49f6bda9213b9e659b61`。コミット・push・公開なし。
- 開始時、追跡ファイルに変更なし。`audit/` に既存の未追跡JSON/XMLが21件あり、内容とファイルを保全した。
- Windows x64、repo-local CPython 3.12.13。CLIを処理本体とするローカルWebアプリ。SQLite、httpx、BeautifulSoup、FastAPI/Starlette、Pydantic、Uvicorn、Playwright/Chromium。
- setuptools/wheel/build、pytest、Ruff、mypy、pip-audit。CIはWindows Python 3.10〜3.13とポータブル起動・package・securityを定義。
- モノレポ、submodule、Git LFS管理ファイル、DBサーバー、GPUの必須依存なし。LFS 3.7.1はホストに存在するが起動には不要。

## インベントリ・アーキテクチャ・仕様

実在ファイルの再帰的件数・サイズ・ソースハッシュ・導入依存を `reaudit-inventory.json` に保存した。`core/`、`cli.py`、`web/` の実行経路、tests、起動bat/PowerShell、配布・ポータブル・検証tools、CI、マニフェストとlockを確認した。生成済みvenv/cache/バイナリは第三者実装を直接改変せず、取得定義・ハッシュ・依存検査で確認。

依存・データフローは `Web → cli_bridge → 常駐rpc/単発CLI → core → SQLite/ライブラリ/HTTP`。UIはloopbackのみ、Host/Originを検証。CLIとworkerは同じdispatchを利用し、ダウンロードは単発子プロセスと最大5threads、ライブラリロックでcleanupと排他。Cookieは手動ブラウザ認証後、アクセス制限した固有一時ファイルからatomic publish。HTTPはTLS・scope付きCookie・timeout・bounded retry。SQLiteはWAL、FK、busy timeout、前方移行。

主要フローは、起動/診断、手動認証、購入HTML取込、未分類表示、分類create/add/remove/delete、CSV export、DL/再開/force/ZIP展開、失敗状態照会、未完了cleanup、終了/再起動。仕様はREADME・公開CLI・既存テスト・コード・履歴から確認した。

同梱 `vendor/windows-x64` のPython/SQLite/wheels/ChromiumをOS PowerShellで検証・復元し、通常起動はネットワーク/システムPythonなしで準備できる。実サービスはpixiv/BOOTHとDLリンクのCDN。既定のDB/Cookie/library/キャッシュはrepo内。Windows標準cmd/PowerShell/tar/whoami/icaclsに依存する。

## Baseline

実行場所はリポジトリルート、Pythonは `.venv/Scripts/python.exe`。

| コマンド | 結果 |
|---|---|
| `-m pytest -q` | PASS: 327 passed、37.97s、第三者非推奨警告1件 |
| `-m ruff check .` | PASS |
| `-m ruff format --check .` | PASS: 83 files |
| `-m mypy` | PASS: 17 source files |
| `-m pip check` | PASS |
| clean venvに`build bandit`だけ導入、`-m build --no-isolation --outdir .cache/audit-ci-build` | FAIL: `Cannot import setuptools.build_meta`。CI packageと同条件で再現 |
| `-m bandit -r cli.py core web -c pyproject.toml --severity-level medium --confidence-level medium` | PASS: 合致する指摘なし（低重大度/低確信度は別途確認） |

## 問題登録・修正順・個別修正

| ID | 重大度 / 原因・影響 | 修正 / 検証 |
|---|---|---|
| BR-R01 | High / ファイル名に内部`.part`名前空間を許し、cleanupが原本や展開済みファイルまで削除 | 新規名は予約suffixを回避。台帳原本/移動後の同名原本/原本sidecarを保護。CLI cleanupはitem/downloads直下のみ。scratchと別原本の衝突も回避し、既存台帳衝突は書込前に拒否。修正前にcleanup件数2を再現。移動・旧台帳・展開原本・名称衝突の回帰試験 |
| BR-R02 | Medium / Playwright gotoのHTTP statusと最終originを見ず、401/403/404/429/500/503でもログイン成功 | 200応答かつ正しいHTTPS libraryだけ認める。空購入libraryは有効。HTTP6ケースは修正前失敗→修正後成功。既存login7経路含む19 tests成功 |
| BR-R03 | Medium / CSVが固定`export.csv.tmp`を使用し、既存ファイル/同時exportを上書き | 同一ディレクトリのmkstemp・flush/fsync・atomic rename・finally cleanup。既存tmp喪失を修正前再現。clean cloneでWindows同時renameのWinError5も再現し、10/20ms待機の最大3回retryを追加。永続lockは明示失敗。同時2export・locked publish失敗・式無害化を検証 |
| BR-R04 | Medium / hashlib.file_digest（3.11+）でPython3.10 matrixのvendor試験が失敗。clone cleanupも3.12+APIのみ | 1MiB streaming hashへ変更、clone cleanupはPython版に合うshutil APIを使用。欠けたAPIを再現した試験とreadonly削除を検証。実Python3.10実行は未検証 |
| BR-R05 | Medium / CI packageがbuildのみ導入し、no-isolationに必要なsetuptools/wheelがない | CIで`build "setuptools>=77" wheel`を明示。同じclean venvへ導入後、wheel/sdist build成功 |
| BR-R06 | High / CookieのACLがR/Wのみで、親folderがModify-onlyの場合にatomic rename・更新・logoutが拒否される | 実ブラウザprobeのCookie保存でWinError5を検出。実Windows ACLをMだけにした隔離テストでも赤を再現。現在アカウントだけへR/W/Dを付与し、旧R/W jarの更新・削除も準備。auth/security/関連91 tests成功 |

依存順はデータ保護→認証→CSV→互換性→配布/CI。各修正は対応するテストを先に実行し、原因を確認してから変更した。BR-R01関連既存テストのfixtureは実際のitem/downloads配置へ変更した。排他・削除件数・復旧のassertionは維持し、原本保護を追加検証した。

ロールバックは各IDのソース・テスト差分のみを手動で戻す。schema/lock/vendorは変更していない。既存原本・DB・Cookieの修正や削除は実施していない。

## 検証・性能・安定性

- 最終全体回帰: **352 passed / 38.82s**、`reaudit-junit.xml`。追加25ケース。既存テスト削除/skip/assertion弱化なし。
- lint/type成功。配布backend不足はclean venvで失敗→成功を確認。
- `reaudit-performance.json`: parser2000件中央値131.26ms（3回）、worker200行4.01ms、HTTP購入7.02ms、index16.67ms（各7回）。今回性能最適化は行っていない。以前の測定との環境差を改善率として扱わない。
- `reaudit-stability.json`: 8threads、1,000reads、40writes、約3.00s、worker再起動0、GC後handle157→158。未commitのSQLite transactionを強制killし、原データ/8lists/整合性維持。
- portable静的・配置監査 **17/17 PASS**。vendor全chunk・joined hash **PASS**。

## セキュリティ・依存・再監査

確認境界: Cookieのhost/path/secure/期限/redirect/ログ/ACL、URL/queryのredaction、固定argvとshellなし、SQL値bindingと固定sort、Web Host/OriginとHTML escape、ZIP traversal/ADS/CRC/サイズ上限、台帳path containment、原本とscratch/cleanup、配布物のuser data除外、固定ハッシュとOS-only起動。未完成実装・TODO/FIXME・disabled tests・型/lint抑制を検索し、実行境界の例外処理と既存fixtureのskip理由を確認した。

専用Codex Securityは必要なMCP開始/保存/完了ツールがないため **BLOCKED**。その専用scan成果物は生成していない。通常のソース境界監査・Bandit・pip-auditは別の実行証拠として扱う。

`pip-audit --local` と `pip-audit -r requirements-lock.txt --require-hashes` はどちらもexit 0、既知脆弱性の報告なし（`reaudit-security-installed.json` / `reaudit-security-lock.json`）。Bandit全重大度/全確信度の生結果は `reaudit-bandit.json`。10候補（Low8、Medium/Low-confidence2）を確認した。SQL2件は固定ORDER_BY allowlistを検証後に挿入、subprocess関連は固定実行先/argv・shellなし、RNGは非暗号用途のretry jitter、assertはworkerの内部状態不変条件であり、認可には使用していない。今回確認した候補には修正を要する脆弱性はなかった。scanner結果の抑制は追加していない。

## 未検証・外部制約

- 実BOOTH認証/購入HTML/購入品DL: 有効Cookieがなく **BLOCKED**。local HTTP、mock transport、実ローカルChromiumで代替検証。
- Windows10/別PC、実Python3.10/3.11/3.13、GitHub runner実行、数時間soak、電源断/ディスク満杯・全native I/O trace: **NOT TESTED**。
- 開発環境FastAPI/Starletteのhttpx TestClient移行警告1件は第三者由来。抑制を追加せず、既存互換性を保持した。固定配布環境とは区別する。
- 任意markup、暫定order IDから商品IDへの統合、外部CDN変化は既存の制約。実サービス適合性や第三者全バイナリの無欠陥は保証しない。

## 最終品質ゲート

判定は実サービス等の未検証を含め **CONDITIONAL**。確認できた修正可能なCritical/High問題の残件は0。6修正単位は個別・全体回帰まで完了。

| Gate | 状態・実行証拠 |
|---|---|
| 開発環境全体回帰 | PASS: 352 passed、38.82s、JUnit |
| clean candidate Git tree | PASS: `reaudit-clone.json`。未commitソースを隔離index/treeでcheckout。元index不変 |
| OS-only offline初回Web/CLI | PASS: 約26.80s/21.20s。生成済みruntime/venv/cache/browserをコピーせず、壊れたglobal設定・接続不能proxy・日本語spaceパスで検証 |
| clean candidate全回帰 | PASS: 352 passed / 42.60s、`reaudit-junit-clone.xml`、candidate tree `beb22955aed2e1d17a035cc9c1f7eed51eadf27f`。テストコピー削除済み |
| managed browser正常終了/再起動 | PASS: cloneのlauncher probeでbrowser close後server port閉鎖、初回CLI再構築成功 |
| lint/format/mypy/compile/pip check | PASS。85 files format、17 source files type check |
| installed/固定runtime依存audit | PASS: 既知脆弱性報告なし |
| stress/SQLite kill recovery | PASS: 上記JSON |
| portable配置/vendor integrity | PASS: 17/17、全chunk hash |
| wheel/sdist/launcher build | PASS: 3成果物とSHA256SUMS生成、76 source files byte一致、CRC/必須入力/原本データ除外。`reaudit-artifacts.json` |
| installed wheel / worker / doctor | PASS: clean venvにhash固定runtimeをoffline導入してwheel install。installed CLI version/init/list、worker classify/remove、doctor fatal checksすべて成功 |
| 実BOOTH・他OS/Python・GitHub runner・長時間soak | BLOCKED / NOT TESTED: 上記制約 |

Buildでのsetuptools manifest警告は、存在しない第三者`.md`と安全除外globが未一致という情報。配布物の必要ファイル・hash・CRC・秘密データ除外を別途検証し、重大なbuild warningとして扱っていない。クローンの第一回回帰はCSV競合1件でFAIL、修正後の新規クローンがPASSとなった。失敗結果を成功に置換せず修正理由として記録した。

実ローカルChromiumで画面の「リスト作成」→「分類に追加」→dialog承認付き削除を操作し、表示件数1→0→1の復元、API全200、正常終了を検証。probeをfetchだけから実コントロール操作へ強化した。隔離先 `.cache/reaudit-ui` を出力先とし、実行ソースはこのrepoのCLI/core/web。最初の直接probeではambient browser/tempを利用したため、その結果をポータブル性の証拠にはしない。最終probeではrepoのbrowser/tempを明示し、`reaudit-ui.json` と画面を保存した。

wheel doctorはportable構成外のsite-packages配置と未ログインを3件の非fatal warningとして正しく報告した。インストール済みwheelの一般動作と、クローン自体のポータブル性は別のgateで検証済み。

## 最終変更・証拠一覧

- 本体: `cli.py`, `core/auth.py`, `core/download.py`, `core/purchases.py`。
- tests: 新規 `tests/test_reaudit.py`（25ケース）、fixture更新 `tests/test_audit_web.py`, `tests/test_regression_102.py`。
- tooling/CI: `.github/workflows/ci.yml`, `tools/audit_package.py`, `tools/dependency_inventory.py`, `tools/manage_portable.py`, `tools/vendor_payload.py`, `tools/verify_clone.py`, `tools/portable_probe.py`。
- docs: `README.md`, `audit/04-issue-register.md`, `06-repair-log.md`, `11-final-quality-report.md`, 本報告。
- 新規証拠: `reaudit-inventory.json`, `reaudit-inventory-final.json`, `reaudit-junit.xml`, `reaudit-junit-clone.xml`, `reaudit-clone.json`, `reaudit-performance.json`, `reaudit-stability.json`, `reaudit-security-installed.json`, `reaudit-security-lock.json`, `reaudit-bandit.json`, `reaudit-artifacts.json`, `reaudit-ui.json`, `reaudit-ui.png`。
- 失敗したshell呼出（pip-auditの非対応引数、PowerShell assignmentのchain構文）は検証成功に含めず、正しいコマンドへ修正した後の実行を採用。
- 最終再確認で新たにBR-R06を処理。最終コードはclone回帰・build・installed操作で確認し、その後の変更は記録のみ。依存lock/schema/vendorのdriftなし、秘密値追加/skip/抑制追加なし。
- 検証用に作成したvenv/候補archive/UI scratchは証拠保存後に削除。既存venv/runtime/browser/cache/dist/releaseと開始時の未追跡証拠は維持。
