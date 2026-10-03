# Clone-to-Run・環境隔離の最終検証（2026-10-01）

Windows x64のローカルディスクを対象に、通常入口 `start-web.bat` だけで同梱環境を構築する構成を検証しました。システムPython、追加のRuntimeインストール、事前setup、初回ダウンロードは不要です。本来必要なBOOTH/pixiv/CDNとの通信を維持しています。

実装・観測範囲では起動、環境分離、移動、破損復旧に合格しています。全ネイティブアクセスの監視と第三者バイナリの公衆再配布条件の完全確認が残るため、総合判定は **PARTIALLY PORTABLE** とします。未配置のRuntimeや依存パッケージが残っているという意味ではありません。

## 概要と適用範囲

| 項目 | 内容 |
|---|---|
| Repository | BOOTH-Reader |
| Repository Type | デスクトップ向けWeb UI + CLI |
| OS / Architecture | Windows x64。Windows 11で実検証 |
| Language / Framework | Python、FastAPI、Uvicorn、Playwright |
| Runtime | CPython 3.12.13、SQLite 3.53.4、Playwright 1.63.0、Chrome for Testing 153.0.8010.12 |
| Entry Point | 通常利用は `start-web.bat`。CLI利用は `cli.bat` |
| 対象ストレージ | 書込み可能なローカルディスク |

Mac/Linux/ARM64向けランタイムをこのWindows専用リポジトリへ新設してはいません。SQLite WALは共有メモリとロックを必要とするため、UNC/NASへの直接配置は対象外です。NASを明示指定したバックアップ・購入データの入出力とは別の制約です。

## 依存分類と保存先

| 分類 | 対象 | 配置・扱い |
|---|---|---|
| A: 内包 | Python/SQLite、全62固定wheel、Node、Chromium/headless shell、FFmpeg、winldd | `vendor/windows-x64/`。サイズとSHA-256を検証して展開 |
| B: 初回取得 | なし | 通常起動・修復の外部ダウンロードなし |
| C: 生成 | Runtime、venv、browser、package/tool cache、temp/profile、DB | `.tools/`、`.venv/`、`.playwright-browsers/`、`.cache/`、`app.db` |
| C: 生成 | Cookie・購入ファイル | `data/cookies.json`、`BOOTH-Reader-Library/`。Git・配布物から除外 |
| D: OS標準 | cmd、PowerShell 5.1/.NET、tar、whoami/icacls、Windows DLL・ドライバー | OSによる提供。プロジェクト用の恒久登録・インストールなし |
| E: 外部統合 | BOOTH、pixiv認証、販売者CDN | 認証・購入情報・著作物を提供する本来の接続先 |
| F: 排除 | Global Python/pip、外部ブラウザcache、CIのglobal開発環境 | 起動とCIの通常工程から除去 |

Compiler/SDK、Docker、外部DB、別リポジトリ、AIモデルは不要です。Pythonのネイティブ拡張は固定wheelに含まれます。パッケージごとの直接・間接依存、license通知とnativeファイルは `portable-dependencies.json` / `portable-dependencies.md` に記録しています。

```text
Runtime Localized: YES
Package Manager Localized: YES (pip)
Dependencies Localized: YES (62 hash-pinned wheels)
Build Tools Localized: YES (build/setuptools/wheel)
External CLI Localized: YES (Node/browser tools; OS-standard tools excepted)
Cache / Temp / Config Localized: YES
Logs Localized: YES (stderr; audit logs in .cache)
Database Localized: YES (SQLite)
Models Localized: N/A
Path Resolution Fixed: YES
Launcher Added/Updated: existing start-web.bat / cli.bat retained
Auto Repair Added: browser launch-health failure, one verified offline retry
```

## 今回の変更

- Web起動と `cli.bat auth login` はブラウザを実起動して健康診断します。実行ファイルが存在していても起動できなければ、検証済み同梱snapshotから一度だけ復旧します。復旧後も起動できなければ明示的に失敗します。
- 通常のCLI照会には追加のブラウザ起動検査を入れません。既存の依存確認・Runtimeの不足修復・移動後venv再構築は維持します。
- `verify_clone.py` に構築済みcheckoutの実移動、原本読取拒否、データ/画面操作、破損ブラウザの通常入口からの復旧、終了・再起動、移動先監査を追加しました。
- `.github/workflows/ci.yml` の通常検証・ビルド・セキュリティ工程は同梱Runtimeへ統一しました。Global Python/pip導入、ユーザーcache、RUNNER_TEMPへの専用DB作成を除去しています。CIのRuntime対象は配布版の固定3.12です。従来のホストPython 3.10〜3.13 matrixは廃止しましたが、製品ソースのPython互換宣言・機能は変更していません。
- CIの静的セキュリティ検査は固定RuffのBandit由来ルールを使います。別の未固定Banditを導入しません。`check_portable.py` はCIへのglobal導入再混入も検出します。

## 検証方法と結果

今回のソースには既存の未コミット修正があるため、独立index/object storeから候補Gitツリーを生成しました。新規 `git clone --no-checkout --no-hardlinks` 後に、そのGitツリーだけをcheckoutして検証しています。生成済み環境、元DB、Cookie、個人ライブラリはコピーしていません。元index/HEADは変更していません。

この試験は候補ソースのClone-to-Run検証です。今回の未コミット修正が既存HEADやリモートへ含まれているという証拠ではありません。

開発CLIを含まないPATH、無効なPython/pip設定、到達不能proxy、空の外部profile/tempを継承して通常BATを実行しました。初回Webと初回CLIを独立したcold状態から実行し、画面を閉じた後のポート閉鎖と終了コードを確認しています。

構築済みcheckoutを日本語・空白パスへrenameし、旧パスを消失させて再起動しました。CPython audit hookは元リポジトリ・旧checkoutの読取りを拒否します。移動先でSQLite/CSV/合成Cookie ACL、リスト作成・分類・削除、画面の更新を確認しました。headless-shellの実行ファイルを試験コピー内で破壊した後、通常の `start-web.bat` から復旧し、Web再起動・終了に成功しています。

| Test | 結果 | 根拠・範囲 |
|---|---|---|
| Repository Audit | PASS | 起動・ソース・build/CI・生成先監査 |
| Dependency Audit | PASS | 62wheelの推移閉包とPyPI公開SHA-256一致 |
| Clean Clone | PASS | 候補Gitツリーの新規clone/checkout。生成環境なし |
| Clone-to-Run | PASS | 通常BATのみ。準備ログはstderr、CLI stdoutは有効JSON |
| Runtime Isolation | PASS | 移動先sys.executable/prefix/base_prefix/DLLを観測 |
| Dependency Isolation | PASS | checkout内venv、pip check、hash固定 |
| Global Dependency Independence | PASS | 開発ツールなしPATH、poison設定でも起動 |
| Repository Boundary | PASS | 既定保存先・temp/profile・リンク監査の観測範囲 |
| Repository Pollution | PASS | 継承した外部profile/tempのファイル・フォルダ生成0 |
| External File Access Audit | NOT TESTED | 全native file/registry/network syscallは未監視。Python/DLL観測は実施 |
| Relocation | PASS | 構築済みcheckoutの実移動、自動venv修復、入出力、終了・再起動 |
| Original Repository Isolation | PASS | Python原本アクセスを拒否し、明示的な拒否試験も成功 |
| Offline Startup | PASS | 到達不能proxy、依存ダウンロードなし。BOOTH本来の通信は例外 |
| Regression | PASS | 355 passed、0 failed。`final-portability-junit.xml`。FastAPI/Starlette由来の非推奨警告1件 |
| Security | PASS | pip-audit既知脆弱性0、Ruff、hash/探索/secret除外/ACL/ZIP安全性試験 |
| License | NOT TESTED | 通知・出所・license本文確認済み。公衆再配布条件の完全照合は未完了 |

最終初回Webは25.868秒、初回CLIは21.280秒、移動後venv修復は16.959秒でした。Ruff check/format、mypy、pip check、同梱物全hash検証、18/18のポータブル監査を実施しています。CI YAMLは同梱Node/PlaywrightのYAML parserで構文確認しました。GitHub Actions上でworkflowを実行した結果ではありません。

失敗した試験も `final-portability-clone.json` / `final-portability-verified.json` に残しています。最初は検証用の直接Python実行が外部profileに空フォルダを生成しました。BATを迂回する検証プロセスにも同じprofile隔離を適用して修正しました。次は静的監査が相対 `home` パスを開発者homeと誤検知したため、検証側のパスをPathで構成しました。さらに並行した `git diff --check` がindexのstat情報を更新し、検証のbyte一致確認が失敗しました。Git操作を並行させず再実行した最終試験はindex不変・全工程PASSです。製品の汚染試験からこれらを黙って除外していません。

## ホストへの影響

```text
Project Files Created Outside Repository: NONE observed (inherited profile/temp)
Project Files Modified Outside Repository: NONE observed
Global Packages Installed: NONE
System Packages Installed: NONE
Persistent PATH Changes: NONE
Persistent Environment Changes: NONE
Registry Changes: no project registration; all native writes NOT TESTED
Services Added: NONE
Scheduled Tasks Added: NONE
Shell Profile Changes: NONE
```

OS自身の履歴・証明書・フォント・ドライバーはOS標準アクセスに分類します。GitHub Actionsのcheckout/artifact/secret-scanはCI基盤による処理で、アプリの起動依存には含まれません。ユーザーがCLIで明示指定した外部DB/CSV/出力先は指定データ操作として維持します。共通Obsidianへの作業記録は開発エージェントの記憶処理であり、製品の起動処理ではありません。

## 正常な外部統合

| Name | Type / Purpose | Required For | 外部に残す理由 | Portable Client Side Completed |
|---|---|---|---|---|
| BOOTH | HTTPS、購入情報 | 購入一覧の同期 | 正式な履歴・商品情報はサービス側で管理 | YES |
| pixiv / BOOTH login | ブラウザ認証 | 正規ログイン | アカウント認証はサービス側処理 | YES |
| 販売者download CDN | HTTPS、購入ファイル | 新規取得 | 配信・権限判定は販売側で管理 | YES |

実アカウントのログイン〜購入〜著作物DLは有効Cookieがなく未検証です。認証を代替したり外部通信機能を削除したりしてはいません。ローカルHTTP/モック・実ブラウザ・合成Cookieによる回帰検証とは区別します。

## 未解決項目

### 1. 全nativeアクセスと他ホストの検証

```text
UNRESOLVED PORTABILITY ITEM
対象: Windows/Chromium/Nodeの全nativeアクセス監査、別PC、Windows10、GitHub runner
現在必要な外部Component: Windows標準機能・必要ドライバー
問題: 全file/registry/network書込み、別PCとrunnerでの動作は未確認
なぜRepository内へ移行できないか: OS/driverはプロジェクトRuntimeではない。未確認は未移行依存ではない
原因分類: OS Constraint / Technical Constraint（検証範囲）
調査したPortable方式: 同梱runtime/browser、process-local profile/temp、原本アクセス拒否
試した方法: fresh Git checkout、開発PATH排除、実移動、CPython audit hook、実DLL列挙
試した結果: 観測範囲の外部profile/temp生成0、元リポジトリ読取拒否、ローカル動作合格
採用した代替方式: 上記の反復可能な自動検証とCI。前回WPR失敗も既存reportに記録
実際にPortable化できた範囲: 全アプリruntime/dependency/browser/default state
現在残っている外部要件: OS/driverと本来のWebサービス
Repository外への影響: 観測なし。全native監視についてNONEと断言できない
影響する機能: 無汚染の完全証明と他ホストの保証範囲
完全解決に必要な条件: native全体を監視できる対象Windows環境、別ホスト/runnerでの実行
```

### 2. 第三者バイナリの公衆再配布条件

```text
UNRESOLVED PORTABILITY ITEM
対象: Python内包ライブラリ/VC runtime、Node、Chrome for Testing、FFmpeg、winldd
現在必要な外部Component: なし（バイナリは同梱済み）
問題: 全内包物の通知・対応ソース・再配布許諾を版単位で完全には照合できていない
なぜRepository内へ移行できないか: 保存先の問題ではなく、第三者配布条件の未確定
原因分類: License Constraint
調査したPortable方式: 原本/通知の保持、公式配布元からの初回取得、ライブラリ置換
試した方法: 全62wheelのlicense/notice/native台帳、公式PyPI hash、CPython LICENSE、Chrome ABOUT/terms/credits、Playwright Apache-2.0とwinldd公式説明
試した結果: 出所・原通知を追跡可能。Chrome ABOUTはGoogle製品のterms参照であり、Chromium BSDだけでは判定できない
採用した代替方式: 既存の原archive・wheel・通知を保持し、実装中に新たなバイナリ配布は行わない
実際にPortable化できた範囲: 全runtime/package/browser/toolをcheckout内で利用可能
現在残っている外部要件: 新たな実行時外部依存はなし
Repository外への影響: なし
影響する機能: 同梱バイナリを公衆へ再配布する判断。ローカル起動試験とは独立
完全解決に必要な条件: 固定原本の全内包通知・必要対応ソース・再配布条件の照合。必要なら公式初回取得へ切替
```

## 最終判定

```text
PORTABILITY STATUS: PARTIALLY PORTABLE
CLEAN CLONE: PASS (candidate Git tree)
CLONE-TO-RUN: PASS (Windows x64 / local disk)
SINGLE ENTRY POINT: PASS (start-web.bat for ordinary users)
MANUAL INSTALLATION REQUIRED: NO
MANUAL SETUP REQUIRED: NO (service login excepted)
REPOSITORY BOUNDARY: PASS (audited scope)
ZERO PROJECT POLLUTION: PASS (observed profile/temp; complete native audit pending)
DELETE-TO-UNINSTALL: PASS (owned isolated test copies deleted)
REQUIRED EXTERNAL INTEGRATIONS: BOOTH / pixiv login / seller download CDNs
UNRESOLVED PORTABILITY ITEMS: 2 (verification scope / redistribution license closure)
```

ソースのcommit/push/公開は行っていません。最新機械証拠は `final-portability-result.json` / `final-portability-junit.xml` / `final-portability-security.json`、生ログと画面・ブラウザ通知は `.cache/clone-evidence/` に保存しています。

一次情報: [Playwright LICENSE](https://raw.githubusercontent.com/microsoft/playwright/main/LICENSE)、[winldd公式説明](https://raw.githubusercontent.com/microsoft/playwright/main/browser_patches/winldd/README.md)、各固定wheelのPyPI公開メタデータ。同梱原本の `.tools/python/LICENSE.txt`、Chrome `ABOUT` と実ブラウザの `chrome://terms` / `chrome://credits` も確認しました。
