# 完全ポータブル・両OSクローン配布候補（1.2.0）

対象はWindows x64・Apple Silicon Mac、配布方式はGit候補のクローンです。Python・固定依存・認証ホストをフォルダー内に同梱し、初回準備と修復はオフラインで行います。設定・DB・Cookie・購入物・キャッシュは既定でフォルダー内です。OS標準ライブラリ・証明書・GUI機能はOSの構成要素として使用します。

## 1.2.0の変更

- 無料ダウンロード商品を商品URLからマイリストへ追加できるようにした。商品ページのメタデータを取得し、購入品と区別してDBへ登録する。
- 購入日が未取得の商品を、BOOTHの購入履歴にある注文一覧・注文詳細から自動補完する。注文ID・購入日・商品IDはDB v7の`orders`・`order_items`へキャッシュし、次回以降は新規注文だけを取得する。
- 同期で購入日が空になっても、補完済みの購入日を上書きしない。
- Web UIの画面上部に「URLから追加」を追加し、一覧のどこからでもURLと追加先リストを選べるようにした。
- DBをv7へ移行。既存の分類・取得記録・購入原本のパスは保持する。

## 実行・機能検証

- Windows: `pytest -q` は508 passed、1 skipped（macOS WebKit専用テスト）。Ruff・format・mypy（25ソース）・pip checkは合格。
- `tools/check_release_hygiene.py --git-only` は追跡・追加候補・履歴の私用パス0件。`tools/check_license_evidence.py` は2,317参照・1,720原文で不一致0。
- `tools/vendor_payload.py verify` と `tools/check_portable.py` は合格（portable 18/18）。固定候補のWindows入力・依存・ローカルパスを確認した。
- 実BOOTHの既存セッションで通常同期を実行し、購入71件・購入日0件のDBを注文83件から補完。全71件に購入日が入り、再同期は3.8秒で日付を保持した。注文履歴の取得は初回のみ注文数分の通信が発生する。
- URL追加した無料ダウンロード商品を一時ライブラリへ取得し、1ファイルのダウンロード・展開・検証が成功した。実DB・Cookie・購入物は証拠に保存しない。
- Windowsの独立Git候補検証（`tools/verify_clone.py`）は合格。候補ツリーの回帰は508 passed、1 skipped、入力等価2,793ファイル、移動後のCLI/UI、旧配置読み取り拒否、終了・再起動を確認した。手動の前面GUI起動だけはヘッドレスUI試験済みのため省略した。結果は`audit/clone-verification.json`と`audit/junit-clone.xml`に保存する。
- 候補固定後のWindows配布検査（`tools/check_distribution.py`）は2,794ファイルでPASS。`license-audit/release-gate.json`を1.2.0の全入力hashへ更新した。
- GitHub Actions run `41584608002` は、Windows品質・Windows独立クローン、Mac arm64品質・Mac独立クローン、依存監査・秘密検査の全ジョブが成功した。この実行はリリース準備コミット `a95e791` を対象とする。最終mainのCI実行記録を公開後の最終確認とする。

## Macの確認範囲

- 今回のWindowsセッションではMac実機へ接続できなかった（Tailscale上でオフライン）。Mac実機の対話的ログイン、実BOOTH操作、macOS 14実機は未確認。
- 変更はPython・Web UI・DBスキーマ・テスト・文書が中心で、Mac固有のWebKitホスト、vendor、固定wheel、起動スクリプトは変更していない。1.1.0で確認済みのMac構成を継承する。
- GitHub Actions run `41584608002` の`macos-15`ジョブは成功した。macOS上で依存整合・Lint・型検査・全テスト・`verify_clone_macos.py`・配布検査を実行している。macOS 14実機と実BOOTHの対話操作は引き続き未確認で、これらを確認済みとは扱わない。

## 配布範囲

ソース、固定manifest/lock、両OSのvendor、原文通知・対応ソースを配布候補に含めます。`app.db`、`data/`、購入物、ログ、プロフィール、私用`.cache/`、UI検証専用Chromeは含めません。shell/command入口は候補Gitツリーで`100755`として固定します。

最低OS版・別の物理PC・長時間運転・全面nativeアクセス追跡は本記録の実施範囲外です。OSが管理する通常の履歴・driver cacheまでフォルダー内になるという主張は含みません。

## 判定

- ライセンス条件と候補入力の一致は`license-audit/release-gate.json`で固定する。1.2.0は第三者コード・バイナリ・依存を追加していないため、1.1.0の原文・対応ソース・依存監査を継承する。
- この文書は製品の完成判定とライセンス判定を分けて記録する。公開・push・GitHub Actionsの実行結果はCIの実行記録を参照する。
