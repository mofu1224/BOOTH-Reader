# アーキテクチャ・機能復元

## 処理経路

`bat / booth-reader → cli.main → core`。Webは`FastAPI → Bridge → cli.py rpc（短い処理）/ subprocess（DL） → core`。SQLiteは5テーブル、schema v2、WAL、接続ごとFK/busy_timeout。DLは最大5スレッド、各スレッド独立SQLite/HTTP接続。

認証はPlaywrightブラウザの手動入力からCookieのみ保存。HTTPで一覧を取得、BeautifulSoupで注文・商品を解析、transactionでitems/purchases更新。分類はlists/list_members、未分類はLEFT JOIN。DLはリンク解析→台帳による名称決定→`.part`→サイズ検証→rename→sha256→ZIP展開→DB/meta.json。ログはstderr、JSONはstdout。

## 仕様と試験

| 必須機能 | 実装・初期検証 | 調査で見つかった不足 |
|---|---|---|
| 初期化・移行・診断 | db/CLI tests | 新版拒否がinit-dbだけ、移行のatomic性、doctorの判定 |
| Cookie login/status/logout | auth tests/実Chromium起動 | リダイレクト送信範囲、HTTP401/403分類、session混在期限 |
| 購入取り込み・CSV | parser/store/CSV tests | 近隣の商品誤割当、CSV式注入、上限/ページネーション |
| 分類・未分類 | lists/CLI tests | 数値リスト名のremove不整合、失敗時の副作用 |
| DL・再開・冪等性 | local HTTP/ZIP tests | partialをbatch成功扱い、forceに古いbyte混入、part削除、名前大小文字衝突、破損ZIP成功扱い |
| Web一覧・分類・DL | HTTP tests | 入れ子busyで再描画不能、出力先未伝達、重複DL/cleanup競合、初回worker生成競合 |
| パッケージ・再現性 | RC/CI/lock | 任意出力先のrecursive削除、除外ディレクトリの子を収集、sdistのtools不足、CIのbrowser準備不足 |

## 構造判断

- 本体に循環importの実害なし。遅延importは起動と前提不足メッセージを守る意図。
- CLIとdownloadが大きいが、今回責務全体の書換えより誤った境界（結果集約・HTTP Cookie・名前・worker lifecycle）の修正を優先。
- Webのファイル削除はCLI真核の原則に反するため、DL競合修正時にCLI cleanup経路へ統合する。
- 広告・VCC/FBX・監視・自動分類・Mac/Linuxは現仕様外。推測的新機能は追加しない。
