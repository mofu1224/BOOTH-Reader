# 変更履歴

## 未リリース（2026-10-05）

- Windowsで長すぎるtikv-jemalloc-sys通知3件のパスを短縮。生成・配布前検査で再発を防止。
- README・ポータブル説明・変更/検証ログ・起動メッセージを短縮。

## 2026-10-04 起動・操作案内

- 入口を `start.bat` に統合。旧setup/start-web/cli/run各スクリプトを削除し、Web・CLI・準備/修復を引数から自動判定。
- ブラウザー自動起動、二重起動回避、空きポート選択、失敗時の画面維持。`--port` / `--no-open` / `--check` / `/?` / `version` に対応。
- 起動・エラーを日本語化し、対処とデータ保持を案内。起動中・venv使用中の更新/修復を拒否。
- UIに初回3手順、同期0件案内、Cookie置換・未完了削除の確認、保存先・構造変更ヒントを追加。

## 2026-10-03 GitHubクローン配布

- 配布対象を全Git候補に統一。ZIP/wheel/sdist生成・タグ公開・配布物アップロードを撤去。
- ブラウザーをWebView2 Runtime154.0.4258.53・SDK1.0.4258.31へ変更。Chrome/headless shell/FFmpegは非同梱。
- WebView2/VC CRT等の原文・再配布条件、SmartScreen通知を整備。個人データと旧Chromium/FFmpeg履歴を配布から除外。
- Web例外・ジョブのCookie/署名URLを伏せ字化。ブラウザーホストをhash別生成し、破損再生成・起動失敗後の資源回収を修正。
- BATの `--db` 消失、旧ブラウザーパス/credits参照を修正。原文/ソース検査をCIへ追加し、秘密スキャンを個別の誤検知許可へ限定。
- CIのLF lock・英語ロケール日本語パス・WebView2停止・再配置UTF-8/キャッシュ先を修正。ActionsをNode24対応の固定SHAへ更新。

## 2026-10-02 配布・ライセンス監査

- Cookie複数値・例外の伏せ字漏れ、Web検証応答のCookie返却を修正。応答キャッシュ・Refererによる持出しを抑止。
- 通常/オフラインでpip patchが無効になる条件を修正。旧環境をpatch hashで再構築。
- 任意DB/sidecar・Cookie取込・HAR・監査結果・画面をGit除外。私用パスの追跡/候補/履歴検査をCIへ追加。
- 7依存のライセンス表記を原文から訂正。pathspec1.1.1の同版MPLソースを追加し、wheel31ファイル一致を確認。
- ランタイム非同梱のsource-online構成を一度検証（46ファイル/26公式取得入力）後、ユーザー指定のリポジトリ配布へ訂正・専用経路を撤去。当時の限定READY判定は取り下げ。
- source-onlineではpip内urllib3の公式2.8.0への更新、原文/RECORD/派生記録、初期28ファイルの生成元・権利条項も確認。旧同梱物・runtimeの全面許諾は当時の承認範囲外。

## 2026-10-01 ポータブル・配布監査

- CPython・修正版SQLite・固定62wheel・ブラウザーを40MiB以下のGit片で同梱。システムPython・初回取得・事前setupを不要化。
- 起動前にprofile/AppData/temp/cacheをローカル化。旧venv拒否、移動/欠損/破損のオフライン修復・rollbackを追加。
- SQLite3.50.4のWAL-reset問題を公式DLL3.53.4へ置換し、hash・ABIを確認。
- 原文/NOTICE・対応ソース・由来台帳・一次証拠・部分SBOMを追加。古い/未完了の判定で配布を拒否。
- CPython full/install_only3,371ファイル、追加通知19件、内包certifi22ファイルを照合。未使用FFmpegをsnapshotから除外。
- 当時の全体ライセンス判定はBLOCKED。後続のクローン配布監査で条件を整理。実BOOTH・別PC・全nativeアクセスは未確認。

## 1.0.3（2026-10-01）

- Cookieをdomain/path/secure/expiry/host-onlyで送信し、pool残留・認証/通信誤分類を修正。
- 部分失敗・破損ZIPを失敗扱いに。forceでの旧byte混入を防ぎ、part・hash・展開記録を保持。
- ZIP禁止名・大小文字衝突を検査し、CRC失敗でも既存原本を壊さないatomic展開へ。
- Webの分類更新・指定保存先・ジョブ排他/失敗表示、worker生成競合・pipe残留・DB差異・書込再送を修正。
- 購入IDの近隣誤割当を防止。rel=nextページと上限超過の明示失敗に対応。
- 全DB接続で新版schemaを拒否、移行をatomic化。数値名リスト・unknown item・CSV式注入を修正。
- 配布先削除/除外漏れ、tools収録、CI/RC/lock生成を修正。新規DL保存先の全走査を除去。
- 詳細・回帰・未確認範囲は [audit/](audit/)。

## 1.0.2（2026-09-29）

- 再実行の改名・複製・再転送を修正。DB v2のURL→ファイル名台帳で同一原本を再利用し、旧URLなし行・手置き原本も保持。
- 206応答の開始位置を書込み前に検証し、不一致partを破棄。再開後の同サイズ破損を防止。
- 新版DBに専用エラー、doctorに `--cookie-path` を追加。ログインの起動失敗/通信失敗、stdin閉塞を分離。
- 未認証DLを401で拒否。リンク上限を明示エラー、暫定order IDを警告。最終失敗の原因を保持。
- 不存在Playwright専用lock参照を除去。全不具合の回帰試験を追加。

## 1.0.1（2026-09-29）

- 部品不足を認証失敗と混同しない `BoothPrerequisiteError` を追加。Playwrightを必須依存へ戻し、doctorでブラウザー本体を検査。

## 1.0.0（2026-09-29）

- doctor、常駐RPC、`--force`、ログインtimeout、未完了削除、Webリスト削除、前方DB移行・整合性検査を追加。
- hash固定依存・packaging・コンソール入口・改行属性・品質/配布CIを整備。
- 再開offsetをretryごとに再計算し、応答・サイズ確認後に `.part` からatomic公開。複数ファイルの失敗を個別集計。
- 商品パス/ZIP逸脱・ZIP bomb・予約名、JWT漏えい、Cookie ACLロックアウト、未認証Cookie保存を修正。
- 日本語icacls、属性型、不正Cookie引数、RPCの別DB指定、不要な購入照会を修正。
- 行単位parser＋位置索引、HTTP pool、GETバックオフ/Retry-After、SQLite WAL・15秒busy timeout、同一オリジン/Host検査を導入。
- JSON/ヘルプ文字コード、UIのlabel/aria-live・テーマ対応、依存の分離を整備。

性能（Windows11/Python3.12.13・500商品DB）：parser2,000行98.2→0.23秒、8,000行1.37秒、Web1照会185→3.7ms、4照会726→13.4ms、GET `/` 16.8ms。

## 0.1.0（2026-09-29）

- 開発初版。version・保存先・CI・MIT/通知・16境界テストを追加。共通エラー、LIMIT制限、atomic書込、busy_timeout、JS escapeを導入。
- 再開破損・パス逸脱・ログ漏えいがあり、配布非推奨。
