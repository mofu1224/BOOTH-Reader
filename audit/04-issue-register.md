# 問題管理表

## 自律監査（2026-10-02、HEAD 0028a5f + 未コミット作業）

原因・再現・修正・回帰・残る外部制約は [15-autonomous-audit-20261002.md](15-autonomous-audit-20261002.md) を参照。

| ID | Severity | 問題 | Status |
|---|---|---|---|
| AUD-01 | Medium | CI verify の `ruff check .` / `format --check .` が原文保持 `THIRD_PARTY_LICENSES/` で失敗 | Done: `pyproject.toml` で除外、CI同一コマンドで lint/format PASS、全体回帰384 passed |
| AUD-02 | Medium | `check_portable.py` が正規の `taskkill`（launcher_probe）と監査用 `git`（license_compliance）を違反扱いし CI portable が失敗 | Done: OS標準・監査用途を明示許可、陰性対照で検出力維持を確認、18/18 PASS、全体回帰384 passed |

## 現行HEADの再監査（0028a5f、2026-10-01）

原因・再現・修正・回帰・残る外部制約は [13-reaudit-quality-report.md](13-reaudit-quality-report.md) を参照。

| ID | Severity | 問題 | Status |
|---|---|---|---|
| BR-R01 | High | 原本/展開済み`.part`をcleanupで削除、内部scratch名と原本の衝突 | Done: 原本保護・移動復旧・名称予約・CLI/全体回帰成功 |
| BR-R02 | Medium | HTTPエラーページをログイン成功と誤判定 | Done: 応答status/最終origin検証、既存login/全体回帰成功 |
| BR-R03 | Medium | CSV固定tmpの衝突、Windows同時publishの一時的拒否 | Done: unique tmp・限定retry・atomic publish・故障/並行/全体回帰成功 |
| BR-R04 | Medium | 3.10未対応hash API、3.12限定clone cleanup API | Done: streaming hash/API分岐と欠落API/readonly回帰。実3.10 matrixは未検証 |
| BR-R05 | Medium | CI packageのno-isolation backend未導入 | Done: build/setuptools/wheel導入。clean venvで失敗→build成功。GitHub runnerは未検証 |
| BR-R06 | High | Cookie ACLにDELETEがなくModify-only親フォルダで保存/更新/logoutが失敗 | Done: 同一アカウントへR/W/D、旧jar更新権限準備。実Windows ACLの赤→緑・全体回帰成功 |

以下は前回監査の問題登録。

初回全体調査完了後に確定。Statusは修正後テストを実行してから変更する。修正前の再現・個別結果は06へ追記。

| ID | Title / Category | Severity | Affected Files | Root Cause / Impact | Proposed Fix / Required Tests | Status |
|---|---|---|---|---|---|---|
| BR-A01 | Cookie送信・認証失敗境界 / security | 高 | core/net.py, download.py, auth.py, purchases.py | domainなしdict化、path/secure/expiry無視、redirect scope欠落、shared jar残留。401/403は認証分岐に届かない | RFC cookie jarをリクエスト単位に隔離、HTTP認証分類。redirect/expiry/path/secure/logout試験 | verified |
| BR-A02 | DL失敗を成功と報告 / correctness | 高 | download.py, cli.py | item内部failedをbatchがokへ格納、破損ZIPを握りつぶす、空件数JSON混入 | partialをfailedへ集約、ZIP失敗明示、空JSON。CLI exit/API回帰 | verified |
| BR-A03 | force破損・中断再開データ喪失 / data | 高 | download.py | forceでも旧完了destをpart採用、item失敗時part削除、再実行でmeta hash消去 | forceはzeroからatomic置換、part維持、skip metadata保持。changed-origin/故障後復旧 | verified |
| BR-A04 | Windows名称・ZIP書込境界 / security/data | 高 | download.py | 台帳予約の大小文字不整合、ZIP ADS禁止不足、展開失敗で既存member破壊 | casefold一意化、禁止文字検証、member atomic書込。衝突/CRC/ADS/境界試験 | verified |
| BR-A05 | Web更新不能・出力先とジョブ競合 / functionality | 高 | web/app.py, cli_bridge.py, cli.py | refreshがbusy内から再入、library_rootをDLへ渡さない、無制限重複job/cleanup | refresh処理分離、argv出力伝達、排他とCLI cleanup。実browser分類/create/delete/復旧 | verified |
| BR-A06 | worker生成・終了・transport一致 / stability | 中 | web/cli_bridge.py, cli.py | lazy生成競合、pipe未close、relative DBのcwd差、transport失敗でwrite再実行 | lifecycle排他、DB絶対化、close/wait、writeを再送しない。concurrency/death/timeout試験 | verified |
| BR-A07 | 別商品のメタデータ割当 / data/performance | 高 | purchases.py | ±2000文字/共有祖先の最初productを推測で選択 | 注文単位のunique containerのみ、暫定IDへ安全fallback、page/上限明示。隣接欠落/large parser計測 | verified |
| BR-A08 | DB新版拒否・移行・doctor / stability | 高 | db.py, cli.py | initのみversion確認、executescriptのimplicit commit、doctor tables/schema非fatal | 全接続拒否・transaction migration・診断明示。v0/v1/rollback/future tests | verified |
| BR-A09 | 分類の不整合・CSV安全性 / correctness/security | 中 | lists.py, purchases.py | 数値名removeだけfallbackなし、item検証前create、CSV formula未処理 | 共通list解決と入力検証、式文字quote。numeric/unknown item/CSV tests | verified |
| BR-A10 | 配布収集・任意パス削除・sdist / build/security | 高 | tools/build_release.py, pyproject.toml, MANIFEST.in | --outで任意tree削除、除外がbasenameのみ、source packageにtools無し | 非破壊出力、ancestor/symlink除外、manifest。sentinel/zip/wheel/sdist clean install | verified |
| BR-A11 | CI・bootstrap・検証手順の再現不足 / tooling | 中 | ci.yml, tools, tests/test_portable.py, docs | CI doctor前Chromium未導入、3.10にtomllib、gen_lock未存在、RC space分割 | 依存固定・browser準備・互換test/lock生成・RC argv修正。locked install/RC | verified (CI matrix未実行) |
| BR-A12 | 保存・診断の秘密情報境界 / security | 高 | auth.py, logging_setup.py, cli.py, web/app.py | ACL失敗無視、固定tmp、例外/query非redact、Origin scheme未検証 | unique tmpを先にlockdown、診断redact、loopback/origin検証。security回帰 | verified |
| BR-A13 | 同一商品・再開データの版管理 / data | 高 | download.py, net.py | titleでdir変更、後から展開skip、validator無しprefixの混合 | stable dir、cached展開、If-Range/state、不明prefixは再取得。recovery回帰 | verified |
| BR-A14 | 正確性修正後のparser退行 / performance | 中 | purchases.py | 同じbounded subtreeをCSSで繰返し検索 | profileに従い1回走査共有。同条件benchmark/27回帰 | verified |
| BR-A15 | 新規DLで既存library全走査 / performance | 中 | download.py | 保存先安定化のfallbackが台帳なし新規商品にも適用され、1,000無関係folderをstat | 新規は直接解決、コピー先は台帳basenameから復元。1,000folder計測/コピー復旧回帰 | verified |
| AUD-03 | WebView2移行後の旧Chromium前提 / tooling | 高 | verify_clone.py, rc_test.py, portable_probe.py, cli.py, auth.py, tests | `verify_clone` が旧headless shellをglobして停止。RC検査は `playwright install chromium` のまま。doctor/案内/台帳も旧表記 | WebView2のvendor復元・`edge://credits`・`setup.bat --repair` 案内へ統一し、doctorを `browser:webview2` に。回帰更新 | verified |
| AUD-04 | 移動後に生成junctionを外部リンクと誤判定 / portability | 中 | check_portable.py | Edgeが分離profile内に絶対targetの `Content.IE5` junctionを作り、移動後は解決不能 | 生成キャッシュ（.cache等）をリンク検査の対象外に。配布対象の検査は不変 | verified |
| AUD-05 | ブラウザー子プロセスが継承profile依存 / portability | 高 | core/browser.py | WebView2がUSERPROFILE/LOCALAPPDATA等へ書き、無効profileではCDP起動前に失敗 | `browser_env()` でHOME/USERPROFILE/APPDATA/LOCALAPPDATA/TEMPをリポジトリ内へ固定。回帰テスト追加 | verified |
| AUD-06 | 試験失敗時に子プロセスが残存 / tooling | 中 | launcher_probe.py | `finally` がcmdのみ終了し、web worker/browser子が残り旧copyを削除できない | `finally` でbrowser killとserverのツリーtaskkill。旧所有copyを整理 | verified |

## 共通追跡欄

- Affected Components: 各行のファイルが属するHTTP/CLI/DL/Web/DB/分類/build/tooling。
- Reproduction Steps: 対応する新規回帰テストを変更前に実行（失敗）、06にコマンドを記録。
- Dependencies: A01→A02→A03→A04→A05→A06、A07/A08/A09は独立、A10→A11→最終全体gate。
- Rollback Strategy: 当該IDの差分だけを手動で戻す。既存開始差分・利用者データ・他ID差分は維持。DB schema version変更なし、migrationはtransaction内。
- 認証を必要とする実BOOTH試験、未導入Python/OS、真の長時間soakは環境制限欄として最終報告に残す。
