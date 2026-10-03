# 個別修正記録

## 現行HEAD 0028a5fの再監査

BR-R01〜06の再現・修正・個別/全体検証・外部制約は [13-reaudit-quality-report.md](13-reaudit-quality-report.md) に集約。Baseline327 passed→352 passed。Modify-onlyフォルダのCookie保存不能とWindows CSV同時rename拒否も実際に再現し、修正後に確認した。既存の監査証拠21ファイルを保全し、新規証拠は`reaudit-*`へ保存。

開始時の既存差分を維持。各IDについて再現条件、変更、実行した検証を追記する。

## BR-A01 — 完了

- `pytest tests/test_audit_http.py`: 変更前6 failed/2 passed。Cookie path/secure/期限/host-only違反、pool残留、401/403の誤分類、session混在期限を再現。redirect先漏えい自体は初期テストでは再現せず、redirectでscope維持する回帰として扱う。
- HTTP接続を再利用しつつCookieJarは要求単位に設定・終了時clear。redirectごとにstrict host-only policyでheader再構築。認証HTTP失敗はBoothAuthError、通信失敗をstatusで認証エラーへ変換しない。
- 最初の修正でCookieJarの存在しないget_policy呼出が失敗したため修正し再検証。
- `pytest -q tests/test_audit_http.py tests/test_auth_security.py tests/test_download.py tests/test_regression_102.py tests/test_purchases.py --basetemp=.cache/audit-http-green2 --tb=short`: **138 passed**。対象ruff・mypy合格。

## BR-A02 — 完了

- 変更前 `pytest tests/test_audit_download.py`: **4 failed**（partialの逐次/並列誤成功、破損ZIP exit0、空DL JSON混入）。
- item失敗をbatch failedへ集約し成功ファイルの詳細は維持。破損ZIPをfailedへ記録。空DLにもJSON。調査で再現した404の無用リトライを停止、worker thread HTTP接続をfinallyでclose。
- 関連 `tests/test_audit_download.py tests/test_download.py tests/test_cli.py tests/test_hardening.py`: **94 passed**、mypy合格。ruffがテスト未使用import1件を検出し除去。

## BR-A03 — 完了

- 変更前3回帰を実行。forceテストのリンクラベル条件を補正後、旧11byteのRange採用を再現。part喪失とskip hash消失も失敗確認。
- item処理は公開済みdestをresume prefixにしない。forceはzeroから取得し原本はatomic置換まで維持。失敗partを残し、skip時の既存hash/展開記録を保持。既存hash不一致は再取得する。
- `tests/test_audit_download.py tests/test_regression_102.py tests/test_download.py`: **76 passed**、ruff/mypy合格。

## BR-A04 — 完了

- 変更前8回帰は6 failed/2 passed（ADSサンプルはdriveとして拒否されるため、複数文字stemへ補正）。拡張子欠落、Windows禁止文字、CRC失敗による既存ファイル破壊、大小文字ZIP重複を再現。
- labelの拡張子を優先、台帳予約をcasefold比較、台帳名/サブディレクトリのcontainment確認。ZIPはpreflightで重複・禁止名検証、item処理ではunsafeを明示失敗。各memberは一時ファイル→CRC成功→atomic置換で既存memberを保護。
- DL/ZIP/CLI関連 **126 passed**、ruff/mypy合格。正常時の同名case testは開始時も合格したので、その不具合の再現とは主張しない。

## BR-A05 — 完了

- 変更前Web回帰 **4 failed**。実Chromiumでリスト作成後countが変わらずtimeoutすることを確認。
- refreshDataとbusy制御を分離。library_rootをDL subprocessへ伝達。Web job単位lockとCLI library OS lockでDL/cleanup競合を拒否。healthへ最終結果、UI表示更新で失敗を表示。cleanup本体をCLIへ統合。
- 関連 **54 passed**。Windows専用lockに合わせて型チェックを調整した後、新規CLI排他/回復を含むWeb **5 passed**、ruff/mypy合格。実browserでcreate→classify→delete→未分類復元とJS error無しを確認。

## BR-A06 — 完了

- 変更前worker回帰 **4 failed**: 初回8並列で8プロセス生成、stdout pipe残留、relative DBのtransport不一致、応答不明writeの再送。
- lazy lifecycleをlock、DBを呼出元で絶対化、terminate/kill/wait/全pipe close。失われた応答をwriteで再送しない。RPCのinteractive/recursive起動を拒否し、response id/shapeを検証。queue待ちもtimeout化。
- 関連worker/Web/CLI **54 passed**、ruff/mypy合格。relative DB再現が作った空repoファイルは当該検証生成物として除去。

## BR-A07 — 完了

- 変更前purchase回帰 **5 failed**。隣接商品への誤割当、nested anchorの全商品ID=1、silent上限、無効orderの空成功、2ページ目欠落。
- 注文IDが一意のbounded container内だけで商品/metadata解決。±文字位置の推測を削除。上限・解析不能を明示エラー。rel=nextを同じHTTPS library内だけ辿り、全ページ成功後transaction保存（循環/200page/20,000row制限）。
- purchase/旧regression/HTTP/basic **60 passed**。追加前提不足関連 **17 passed**、ruff/mypy合格。

## BR-A08 — 完了

- 変更前DB回帰 **4 failed**。通常connectionでfuture版を開く、DDL fault後に中間schema残留、doctorの不完全schema成功、未初期化DBのtraceback。
- 全connectionでfuture拒否、static schemaとmigrationをBEGIN IMMEDIATE〜commitに統合（fault rollback）。doctorのschema/tablesはfatal、書込probeはunique temporaryで利用者ファイルを壊さない。SQLite CLI例外は既存DB error taxonomyへ。
- 関連 **66 passed**。回帰の例外型をBoothDatabaseErrorへ精密化後 **4 passed**、ruff/mypy合格。

## BR-A09 — 完了

- 変更前11回帰 **11 failed**（数値名remove不整合、unknown itemがlistを作成、制御文字、CSV式）。
- add/remove/deleteのID優先→名前fallbackを共通解決。unknown itemをlist作成前に検査、name制御文字拒否、CSVの式開始文字はapostropheで無害化。通常CSV内容/日本語は維持。
- 関連 **79 passed**、ruff/mypy合格。

## BR-A10 — 完了

- 変更前配布回帰 **3 failed**（--out既存tree削除、cache/data子混入、必須file欠落を成功扱い）。
- 非empty出力拒否、ancestor/symlink除外、必須入力検証。toolsをwheelへ含め、MANIFESTでsdistにlauncher/test/toolを明示。PEP639 metadataに必要なsetuptools>=77へ整合。
- 回帰 **3 passed**、ruff合格。`.cache/audit-build-a10`でsdist→wheel/launcher成功。新規`.cache/audit-wheel`にhash固定21runtimeをクリーン導入、wheelをno-deps install、`python -I`でinstalled CLI/tools import・version・init-db・JSON照会成功。

## BR-A11 — 完了

- 変更前tooling **2 failed**（空白path分割、文書にあるlock generator未存在）。generatorはwheel metadataとhashを検証する動作回帰へ具体化。
- RCはargvリスト、repo-local scratch、秘密形検出の値を出力しない。lock generatorを実装、Python3.10向けtest-only tomliを明示。CIはbrowser導入とlocked runtime、verified build artifactをrelease jobへ渡す。portable --repairで依存再導入も実装。
- tooling/portable/CLI **44 passed**、ruff/mypy、portable audit **15/15 passed**。GitHub上のCI実行・3.10/3.11/3.13実行は未実施。

## 全体再確認で追加した項目

- BR-A12: Cookie保存時のACL失敗を無視、固定tmpの競合、診断の署名URL/traceback非redact、WebのOrigin scheme未確認・非loopback bind。
- BR-A13: タイトル変更でDLフォルダが変わり重複、no-extract完了後に展開要求がskipされる、resumeのrepresentation validator不足。
- BR-A14: 同条件でparser/API性能を再測定し、実測上の退行または明確な無駄だけを修正。

## BR-A12 — 完了

- 変更前security回帰 **5 failed**。ACL失敗後Cookie置換、grant失敗後inheritance除去、署名URL/例外情報、scheme違いOrigin、非loopback起動。
- unique empty tmpへACL適用成功してからCookieを書込・fsync・atomic置換。失敗時は以前のjar維持。ログ例外/stack・CLI errorsにもredact、URL query値は省略。Originはscheme含む完全比較＋cross-site Fetch Metadata拒否、bind/port検証をside effect前に実施。
- 関連 **84 passed**、ruff/mypy合格。既存redaction testはquery値を保持する旧契約を、新しいquery省略とpath維持の明示assertへ更新。

## BR-A13 — 完了

- 変更前recovery **4 failed**。title更新時の再取得、後から展開されない、validator有/無の両方でold prefix＋new tailを再現。
- 台帳/既存item directoryから保存先を安定解決（複数候補は拒否）。skipでも必要なZIP展開を実施。`.part.json`にstrong ETag/Last-ModifiedとURLを保持しIf-Range、変化/validator欠落/legacy prefixは先頭から再取得。416の等しいsizeだけでは公開しない。identity encodingを要求し、login HTML redirectを拒否。
- DL/recovery関連 **88 passed**、追加login-redirect含むrecovery **5 passed**、ruff/mypy合格。旧range testsはvalidator付きの実際の中断状態をseedし、範囲拒否/正しいresumeのassertを維持。
- 修正後同条件2,000件parser中央値194.73ms（開始時139.73ms）で退行を測定したためBR-A14へ進む。

## BR-A14 — 完了

- cProfileで8,060,855呼出、parser3回で1.876s、soupsieve select系が0.780sを占めることを確認（profile下の時間はbenchmark値と区別）。
- bounded rowの注文/productリンクを一度だけ走査・共有し、metadata単純検索をfindへ置換。注文の一意性/隣接商品拒否は維持。
- purchase回帰 **27 passed**、ruff/mypy合格。同条件最終parser中央値**130.45ms**、開始時139.73ms、正確性修正直後194.73ms。warm worker3.49ms、HTTP購入6.42ms、index14.98ms。短い標本の小差は保証された改善率としない。

## 最終全体検証

- 通常環境306 passed/36.49秒、fault injection2件追加後の固定runtime別環境**308 passed/33.52秒**。
- RC **44/44 PASS**。source bundle tests **306 passed/2 fixture skips/36.84秒**。clean runtime/browsers、HTTP、CLI、secret shape、dependency auditを実行。
- 8 threads/1,000reads/40writes **2.77秒**、worker再起動0。handle初回失敗はexecutorをまだ保持している測定条件を調査し、raw/GC後を記録。active transaction kill後のDB整合性合格。
- 配布前記録の集約後は、本体/テストを変えず最終artifactを再生成し、候補とのhash同一性を確認する。

## 最終成果物の閉じ検証

- `tools/audit_package.py dist/1.0.3 --candidate .cache/audit-candidate-103/BOOTH-Reader-1.0.3-windows-x64.zip --out audit/artifacts-final.json`: RC検証済み本体/テスト/依存43ファイルがbyte一致、ZIP CRC/3成果物checksum/wheel-sdist必須入力/利用者データ除外に合格。
- 最終wheelのclean fixed-runtime installed CLI/worker/doctor smoke合格。
- `tools/audit_probe.py inventory --out audit/inventory-final.json` で再調査時の実ファイル数、ソースhash、依存version/license-files/upstream URL/requiresを引き渡す。

## BR-A15 — 最終再調査で追加・完了

- BR-A13のstable directory fallbackを再確認し、新規商品にも既存libraryを全走査する経路を検出。1,000folderの試験で無関係なdirectory stat **1,000回**を再現し、修正前テスト失敗を確認。
- 台帳のない新規商品は直接item directoryを解決。コピー後のlibraryは台帳basenameからO(1)で復元し、legacy fallbackでもnameを絞ってからstatする。
- 同条件7標本中央値 **24.25ms→0.541ms**、無関係folder stat **1,000→0回**。path-performance-baseline/final.jsonに保存。
- DL/recovery関連44 passed。コピーされたlibraryのtitle変更でも再取得しない回帰を追加し、全体試験・RCを更新する。最終成果物はこの修正後の版で再生成する。

- コピー復旧を含む関連30 passed、ruff/mypy合格。修正後の固定runtime全体 **310 passed/36.34秒**。最終RCを改めて実行し **44/44 PASS**、source bundle **308 passed/2 fixture skips/38.12秒**。

- 追加前にこの作業で生成した成果物だけを、ファイル集合・既存checksumが不変と確認して退役。BR-A15後の `dist/1.0.3` を再生成し、最終RC候補44ソースのbyte一致、3成果物checksum/CRC/内容に合格。最終wheelのisolated installed CLI/worker smokeも合格。

- 検証で作成した一時ディレクトリ/別venv/候補artifactは、証拠をauditへ保存した後に所有対象50ディレクトリだけを削除。既存`.venv`/Python/browser/cache/旧dist・releaseは保全。最終inventory、ruff、format、mypy、compileall、git diff --checkを確認して終了。

## AUD-01 — 完了（2026-10-02）

- 変更前 `ruff check .` は **53 errors**、すべて `THIRD_PARTY_LICENSES/` 内の原文保持ソース（CPython idlelib、cyclonedx）。
  `ruff format --check .` も同梱原文3件を未整形扱い。第一者コードは開始時から合格。
- 原文を改変すると出所保全が壊れるため、検査側で `THIRD_PARTY_LICENSES` と `SOURCE_OBLIGATIONS` を
  `extend-exclude` へ追加（理由をコメント化）。第一者の検査範囲は不変。
- CIと同一コマンド `ruff check --output-format=github .` / `ruff format --check --diff .` が **PASS**。
  全体回帰 **384 passed**、mypy・pip check・lock dry-runも合格。

## AUD-02 — 完了（2026-10-02）

- 変更前 `tools/check_portable.py` は **17/18**。未コミット作業の新規2件を違反扱い：
  `launcher_probe.py:116` の `taskkill`、新規 `license_compliance.py:89` の `git`。
- `taskkill` はWindows OS標準（本プロジェクトはWindows専用でtar/whoami/icaclsと同分類、
  [14-final-portability-report.md](14-final-portability-report.md) の分類D）。
  `git` は出所特定のmetadata-onlyで、既存 `audit_probe.py` 免除と同質。
  検査の字面走査が過剰検出していたため、検査側に許可集合（OS標準・監査用途）を明示化。
  テスト弱化ではなく検査の誤検出修正であり、対象の呼出自体は不変。
- 偽の `curl` 呼出ファイルを一時配置する陰性対照で **17/18 FAIL**（検出力維持）を確認後、対照は削除。
- `tools/check_portable.py` は **18/18 PASS**。全体回帰 **384 passed**、ruff・mypy合格。

## AUD-03〜06 — GitHubクローン配布準備（2026-10-03）

- ベースライン **396 passed**、portable 18/18、vendor verify、Git私用パス0を確認後、WebView2移行の残件を修正。
- `verify_clone.py` の破損復旧検査を `chrome-headless-shell` globから `.playwright-browsers/webview2/msedgewebview2.exe` へ変更
  （旧コードは `next()` が `StopIteration` となりportable CIが停止した）。`rc_test.gate_browser` は
  `playwright install chromium` を廃止し、bundleのvendorから `ensure_browser` で復元する検査へ変更。
  `portable_probe` のcredits取得を `edge://credits` へ、doctorを `browser:webview2`（manifestのengine名）へ、
  起動失敗時の案内を `setup.bat --repair` へ更新。依存台帳のブラウザー記述も現行化。
- `core/browser.browser_env()` を追加し、ブラウザー子プロセスのHOME/USERPROFILE/APPDATA/LOCALAPPDATA/TEMPを
  リポジトリ内へ固定。無効な継承profileではWebView2がCDPを開く前に停止していたため（マニュアル再現で確認）、
  `tests/test_portable.py` に回帰を追加。
- `launcher_probe` の `finally` を修正し、失敗時に残っていたbrowser/web worker子プロセスを停止。旧試験copyを整理。
- Edgeが生成する `Content.IE5` junctionはフォルダー移動後に解決不能になるため、`check_portable` のリンク検査から
  生成キャッシュ（`.cache` 等）を除外。配布対象の検査は弱めていない。
- 検証: **397 passed**、ruff/format/mypy/pip check、portable 18/18、vendor verify、`verify_clone` **PASS**
  （85 checks、コピー内回帰397 passed、外部profile/temp書込み0、元index不変）。
- ライセンス: WebView2配布条件とVCランタイム条件の一次証拠を追加し、`license-audit/27-github-clone-distribution.md`
  を作成。`release-gate.json` を現行ハッシュでREADY FOR CLONE DISTRIBUTIONへ更新。NOTICE/README/PORTABLE/
  THIRD_PARTY_NOTICES/SOURCE_OBLIGATIONS/CHANGELOG/VERIFY_LOGを現行構成へ整合。
- 公開・push・GitHub CI実行は未実施。
