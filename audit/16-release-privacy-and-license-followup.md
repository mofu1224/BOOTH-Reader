# 配布前の個人データ・ライセンス追補（2026-10-02）

## 結果

本体の追加修正と検証を完了。**フォルダー全体・リポジトリそのものの配布判定はBLOCKED**。
既存未コミット変更を維持し、別配布用ソース・アーカイブを生成していない。

## 再現した問題と修正

| 問題 | 原因と対応 | 証拠 |
|---|---|---|
| Cookieログ漏れ | 汎用key/value伏字がセミコロンで停止し、2個目のCookieを残す。HTTP認証ヘッダーを行単位で伏字化 | 合成値によるログ・例外テストで修正前3件失敗、修正後成功 |
| Web検証エラーの入力漏れ | Pydanticの標準422応答がCookie入力を `input` に含む。type/locと固定文言だけを返すhandlerを追加 | 合成Cookieによる修正前失敗、修正後成功 |
| ブラウザーに購入情報が残る | Webレスポンスのcache制御がなかった。成功・エラーともno-store/no-referrer | HTTP境界試験成功 |
| pip修正の不適用 | 撤回済みsource-online条件が通常構成でfalse。条件を除去しpatch hash付きmarkerで旧環境を拒否 | 修正前のoffline設定試験失敗、修正後成功。実offline repair・内包urllib3 2.8.0を確認 |
| Git除外不足 | 既定app.db以外のDB・Cookieコピー、監査receipt/screenshotが追加可能 | `.gitignore`補強、追跡/追加候補/到達可能履歴の私用パス各0 |
| 旧配布収集の除外漏れ | Git除外と独立した収集でDB sidecar/HAR/.env派生/CSV/作成記録が混入。共有の私用パス規則とsdist除外を適用 | 修正前の収集試験失敗、修正後成功。配布アーカイブは生成していない |
| ライセンス名・対応ソース不足 | metadataの欠落を原文未確認としていた。7依存を原文から識別、pathspec MPLソースを追加 | 公式PyPI wheel/sdist hash、全31 `.py` のbyte一致 |
| CI整形・portable判定失敗 | 既存監査ツールの未整形/改行混在、読取専用Git監査の検査対象漏れ | 第一者ソースを整形、Git監査用途を明示。18/18 portable成功 |

## 検証

- 開始時: **387 passed**。
- 固定62依存を `setup.bat --offline --repair` で再構築。pip patch実適用、ensurepip更新、marker有効を確認。
- 最終本体試験: **396 passed**。第三者Starlette TestClient非推奨警告1件を保持。
- Ruff lint/format成功（129ファイル）、Mypy 18ソース成功、pip check成功、pip-audit installedの既知脆弱性検出0。
- private headers/422/ログ/通常offline patchの回帰試験成功。`check_portable.py`: **18/18 PASS**。
- Git私用パス検査: 追跡0、追加候補0、到達可能履歴0。これはパス規則の検査で、全blobの秘密値検査ではない。
- pathspec公開hash/使用版ソース: `license-audit/pathspec-source.json`。原LICENSEを改変せず保持。
- 7依存の識別ラベルと対応する原通知hashを再照合。CLI版表示・setup check成功。`git diff --check`は空白エラーなし。

## 配布の阻害事項

- **PRIV-01**: 現物には私用ルート2、直下私用ファイル1、生成ルート4がある。Cookie・購入履歴・購入物・profileを保持したため、現物の丸ごと配布は不可。Git除外はフォルダーコピーには作用しない。
- **LC-01**: 初回28ファイルの作成記録・出力権利の証拠は有効。現在のフォルダー全体の由来閉包は未完了。
- **LC-02/03/05**: CRT、Chrome、Node/native/付属素材の完全な再配布条件が未確定。原LICENSEを持つことだけで全体を承認しない。
- **LC-07**: 現在生成するpipのurllib3対策は有効。元vendorアーカイブ・旧履歴の内包依存と全nativeのadvisoryは未完了。
- **LC-06**: 実BOOTHの認証・購入取得・DL、別OS/別PC、遠隔CI、長時間動作は今回未検証。

公開・commit/push・Git履歴書換えは実施していない。正式な入口は `license-audit/19-release-readiness.md` と `release-gate.json`。
