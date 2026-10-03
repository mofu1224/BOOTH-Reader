# ポータブル化の実装・検証報告（2026-10-01）

> 更新: リポジトリフォルダ自体のクローン即起動を実装しました。`vendor/` のGit管理同梱物から `start-web.bat` / `cli.bat` が無通信で初回自動準備します。外部profile/temp生成0、327試験合格。現在の手順は [../PORTABLE.md](../PORTABLE.md)、最新証拠は `clone-verification.json`。以下は先行するZIP/セットアップ方式の調査・残存制約の記録です。

## 判定

**PARTIALLY PORTABLE**。Windows11 x64・ローカルディスクについて、環境構築、移動、自動修復、オフライン再構築、ビルド、主要機能は実装・実検証を完了しました。実BOOTH、別PC、全ネイティブアクセス、再配布ライセンスの完全確認が残ることを総合判定へ反映しています。

## A. 作業概要

- 対象: `BOOTH-Reader`。Python CLIが本体、FastAPI/UvicornのWeb UIがCLIの常駐worker/one-shotを呼びます。
- 技術: CPython、SQLite/WAL、httpx、BeautifulSoup、FastAPI、Pydantic、Playwright/Chromium、setuptools/wheel。ネイティブ拡張は固定wheelから導入し、Compiler/SDKは不要です。
- 本来の外部通信: BOOTH、pixivログイン、販売者CDN。AIモデル、外部DBサーバー、追加フォント、独自サービスはありません。
- 開始時の未コミット1.0.3修正とデータを保護。reset/clean/stash/commit/push/公開は行っていません。検証前後で元のapp.dbのSHA-256一致を確認しました。
- 問題: 初回システムPython要件、グローバルPythonフォールバック、未固定導入、venvの旧home参照、外部temp、通信必須の修復、Git依存の監査、同梱SQLite3.50.4のWAL-reset不具合。

## B. 実装

| 対象 | 実施内容 |
|---|---|
| Runtime | 固定CPython3.12.13を `.tools/python` へ。OS標準PowerShell/.NET/TLS/tarからSHA-256検証して構築 |
| SQLite | 公式Windows x64 DLL3.53.4。公開SHA3-256、DLL SHA-256、ABI・版を検査。既存DB形式/WAL/並行処理を維持 |
| packages/tools | 実行・開発・ビルド全62packageをハッシュ固定。wheelを `.cache/wheels` へ保管し `.venv` へ導入 |
| native/browser | wheel内Node/greenlet/pydantic-core等、repo内Chromium/headless shell/FFmpeg/winldd。PATHの同名ツールを使用しない |
| paths | `__file__`基準。内部ルートのCWDフォールバックを排除。利用者指定の外部DB/出力先等は維持 |
| env/cache | 子プロセスだけでtemp/pip/uv/ruff/mypy/pytest/HOME等をローカル化。外部Python/Node/pip設定の暗黙利用を排除 |
| setup/repair | 版・import・lock・旧homeを検査。移動/不足/破損を起動前に修復し、venv導入失敗時は旧生成環境を復元 |
| build | ローカル固定build/setuptools/wheelの `--no-isolation`。source ZIPと個人用オフラインZIPを生成 |
| startup/shutdown | 同梱ChromiumでUIを表示。ブラウザ終了でサーバーも停止。`--no-open`でサーバーのみ起動 |
| prevention | Gitなしの実ソース/AST監査、外部リンク監査、禁止恒久変更/未管理CLIの回帰試験、OS-only Windows CI |

依存台帳: [portable-dependencies.md](portable-dependencies.md) / `portable-dependencies.json`。版・用途・依存先・配置・出所・移行・検証・実通知ハッシュを記録しました。

### A〜Dの独立検証

| 要件 | 結果と範囲 |
|---|---|
| A 環境の独立性 | PASS。生成環境・キャッシュなしのコピーを開発ツールなしPATH/無効なPython・pip設定からOS-only構築 |
| B 移動可能性 | PASS。E:からC:へ構築、日本語・空白パスへ実移動。旧コピーがない状態で起動前に再生成 |
| C 実行の独立性 | PASS（観測範囲）。Python原checkoutアクセスを拒否。コード・依存DLL/Node/Browserは移動先からロード。全native traceは未完了 |
| D データの自己完結性 | PASS（観測範囲）。DB/CSV/合成Cookie/ブラウザprofile/temp/cacheをコピー内へ保存。明示指定の外部ファイルとOS処理は別扱い |

## C. テスト結果

Windows11 x64、CPython3.12.13、SQLite3.53.4、Playwright1.63.0、Chrome for Testing153.0.8010.12。同一PCの別ドライブ・別配置で検証しました。

| Test | 結果 | 証拠・制約 |
|---|---|---|
| Dependency Audit | PASS | 62wheelのPyPI公開SHA-256、閉包/版、pip check、native/notice台帳 |
| Clean Bootstrap | PASS | Runtime/package/browser/cacheなしからOS-only構築。最終試験約62秒 |
| Clean Build | PASS | 同梱環境の非隔離wheel/sdist/source ZIP生成 |
| Relocation Test | PASS | C:の日本語・空白パスへ実移動。旧homeの自動修復 |
| Original Repository Isolation | PASS（限定） | 旧C:コピー消失、E:原本を保全してPython読み込み拒否。OS全体のアクセス禁止sandboxではない |
| Global Dependency Independence | PASS | 開発ツールをPATHから除去、profile隔離、Python/pip誤設定を無視 |
| External File Access Audit | NOT TESTED（全面） | Pythonイベントと実DLLを観測。WPR全面traceは0xc5585011で開始不可 |
| Offline Startup | PASS | 到達不能proxyを設定、依存取得なしでCLI/ローカルUI起動。NICのOS全体無効化試験ではない |
| Offline Rebuild | PASS | Runtime/venv/browser全削除後、保存materialだけで再構築・非隔離ビルド・再起動 |
| Regression Tests | PASS | **322 passed / 0 failed / 0 errors / 0 skipped**。実UI/BAT/DB/CSV/合成Cookie ACL/終了/破損修復も確認 |
| Security Audit | PASS（限定） | 62Python packageの既知脆弱性0、導入経路/hash/探索/secret除外、SQLite既知不具合修正。全C/C++監査ではない |
| License Audit | NOT TESTED（完全確認） | 出所・実通知・Node/FFmpeg/Chrome terms/creditsを確認し保持。公衆再配布の全閉包は未完了 |

ruff check/format、mypy、compileall、pip checkも実施。GitHub CI実行、実BOOTH認証・著作物DL、別PC、Windows10、UNC/NAS、数時間soakは未検証です。

### 実アクセス観測

- 実DLL: repo内37種類、Windows/driver内127種類、ホスト側2種類。
- 外部2種類はGoogle日本語入力とRivaTunerのRTSSHooks64。アプリが取得/起動要求する必須依存ではなくホストの入力・描画統合/注入です。ホスト設定は変更していません。
- Python側の外部パスは、意図的な検証CWDとWindowsのNULデバイスだけでした。
- nativeの全open/registry/network/getenvを捕捉したものではありません。システムフォント・証明書・GPUドライバー・IME・OS履歴をプロジェクト専用データと混同しません。

証拠: `portable-summary.json` / `portable-verification.json` / `junit-portable.xml` / `portable-security.json`。生ログ・スクリーンショット・Chrome terms/creditsは `.cache/portable-evidence/booth-portable-20261001-d.zip`。修正途中の証拠も別zipへ保存し、所有した隔離コピーa〜dは削除済みです。

## D. PC本体への影響

```text
System Package Installations: 0
Global Package Installations: 0
System PATH Modifications: 0（子プロセス内PATHのみ）
Persistent Environment Modifications: 0
Registry Modifications: プロジェクト側の恒久登録操作なし。全native書込みは未監視
Services Installed: 0
Scheduled Tasks Created: 0
Project Files Outside Repository: 実行用ファイルなし。所有した隔離コピーは削除済み
Required External Components: Windows標準機能/ドライバー、BOOTH/pixiv/販売者CDN
```

作業記憶は既存の共通Obsidianへ保存します。OS自身のPrefetch・セキュリティ記録・native副作用が一切残らないとは保証しません。既存のユーザー領域ツール/ブラウザ、旧生成物、未コミット差分を保護しました。

## E. 未解決項目の詳細

### 1. 外部サービスと実アカウント疎通

```text
================================================
UNRESOLVED PORTABILITY ITEM
================================================
対象: core/auth.py、net.py、purchases.py、download.py
問題: 認証・最新購入情報・購入ファイルには外部サービスが必要。実アカウント経路も未検証。
原因: サービス側の認証/購入履歴/コンテンツをローカルだけでは再現できない。実Cookieがない。
根拠: accounts.pixiv.net、accounts.booth.pm、商品/CDNへ接続。ローカル試験は合成データ。
試した方法: 取得済みSQLite/ファイルの利用、ローカルHTTP/モック、実ブラウザ。
試した結果: 起動・照会・分類・DL再開・展開・失敗処理は検証済み。実認証の代替にはならない。
実際に行った対処: Runtime/browser/依存を内包し、既存の認証・通信経路とオフライン可能機能を維持。
現在の状態: ローカル機能は検証済み。通信機能を削除していない。
残存する制約: 正規セッションと外部サービスへの通信。
影響: ログイン、購入情報更新、新規DL。
解決に必要な条件: 正規セッションでの実検証。完全ローカル化にはサービス側の同等オフライン機能が必要。
================================================
```

### 2. 別PCと全ネイティブアクセスの検証

```text
================================================
UNRESOLVED PORTABILITY ITEM
================================================
対象: Windows実行環境、Chromium/Node/OS統合、実アクセス監査
問題: 別PC/Windows10、全nativeファイル・registry・networkの確認が未完了。
原因: 利用できた対象Windows環境は1台。WPR GeneralProfileは0xc5585011で開始不可。
根拠: WPRの実エラー、portable-summary.json。実DLLにはホストのIME/RTSSも存在。
試した方法: OS標準WPR、開発ツールなしPATH/隔離profile、Python hook、OS Process.Modules、実移動。
試した結果: Runtime/依存の外部配置は排除。全native traceと別PCの証明にはならない。
実際に行った対処: 再現可能なverify_portable.py、原本参照拒否、実DLL/UI/入出力/終了観測、CIを実装。
現在の状態: Windows11の別ドライブ・別配置・オフライン再構築に合格。
残存する制約: ホスト注入のない別PCとnative全体を観測できる環境。
影響: 完全ポータブルと認証できる検証範囲。不動作を観測したわけではない。
解決に必要な条件: 適切な検証権限/隔離環境、別対象PCで同じ試験。
================================================
```

### 3. 第三者バイナリの再配布条件

```text
================================================
UNRESOLVED PORTABILITY ITEM
================================================
対象: Python内包物、Node、Chrome for Testing、FFmpeg、winldd、Microsoft Distributable Code
問題: 全通知・対応ソース・実行コード条件を含む公衆再配布の許諾閉包は未確認。
原因: 複数のlicenseと独立した実行コード条件がある。metadataやChromium BSD表示だけでは確定不能。
根拠: 実LICENSE/Node LICENSE/FFmpeg LGPL/Chrome ABOUT・terms・credits/Python Windows追加条件。
試した方法: 全62wheelの出所/通知hash、vendored metadata、native inventory、ブラウザ組み込み文書。
試した結果: 出所と原通知を追跡可能にした。公衆再配布条件の完全確認には至らない。
実際に行った対処: 原archives/wheels/noticesを保持し、purl MIT通知を補足。通常ZIPはsource-only、offline ZIPは個人転送用。
現在の状態: ローカル導入・移動・個人用offline再構築を実検証。第三者バイナリを公開していない。
残存する制約: 各componentの条件・通知・対応ソースの完全照合。
影響: バイナリ同梱の公衆配布の判断。
解決に必要な条件: 実条件と必要通知/対応ソースを満たす再配布構成の確認。
================================================
```

### 4. UNC/NAS上での実行

```text
================================================
UNRESOLVED PORTABILITY ITEM
================================================
対象: core/db.py、SQLite WAL、network filesystem
問題: UNC/NAS上に全環境を置く直接運用は非対応・未検証。
原因: WALが共有メモリ/ロックを必要とし、SQLite公式仕様でnetwork filesystem非対応。
根拠: https://www.sqlite.org/wal.html のOverview/Concurrency。
試した方法: ローカル自己完結構成、別ドライブのコピー・実移動・復元。
試した結果: ローカルは合格。別journal方式の並行性能・安定性同等性は未検証。
実際に行った対処: WALと並行処理を維持し、書込み可能なローカルディスクを対象と明記。
現在の状態: NASはコピー/backup用途、実行時はローカル配置。
残存する制約: 全環境をNAS上で直接実行する要件。
影響: network共有上の直接起動・複数ホスト共有。
解決に必要な条件: WALに依存しない同等の並行永続化方式と、対象NASでの実検証。
================================================
```
