# 取り下げたソース限定構成の監査記録（2026-10-02）

## 現在の配布対象

ユーザー指示により配布対象はこのフォルダー全体・リポジトリそのものです。別配布用ソース一式・アーカイブは不要として撤回しました。
以下のsource-online限定のREADY FOR RELEASE判定は取り下げ済みです。完成物の出力先は現存せず、専用生成・試験・承認経路も削除しました。
以下は当時の検証証拠を保持する過去記録です。再生成手順は撤去し、現在の配布手順には使用しません。
全体の監査状態は `release-gate.json` と最新の [31-cross-platform-clone-distribution.md](31-cross-platform-clone-distribution.md) を参照してください。

## 判定と配布対象

**当時の判定: READY FOR RELEASE — source-online構成限定（取り下げ済み）。**

正式配布物は `dist/BOOTH-Reader-1.0.3-source-release/`:

| Artifact | Size | SHA-256 |
|---|---:|---|
| BOOTH-Reader-1.0.3-source-online.zip | 124383 bytes | 2134ab5ed5f71ea7fadfcca42cf1a5d858b794f7ebba4852c404d16abb75f508 |
| booth_reader-1.0.3.tar.gz | 109848 bytes | 8313880122adf8be36378203512c1c1fe5444883d7a362de6ca1e2a7dadaff0f |

同じフォルダーにREADME、LICENSE、NOTICE、RELEASE_NOTES、SBOM、ソース台帳、取得依存の証拠、
最終コンプライアンス報告、PACKAGE_AUDIT、SHA256SUMSを保存した。
build-test wheelは検証用で、今回の正式配布対象には含めない。

初回だけインターネット接続が必要。Windows x64のOS標準PowerShellから公式取得し、システムPythonや管理者権限を要求しない。
CLI/Web初回起動はセットアップを自動実行する。セットアップ後の環境・データ・キャッシュは展開先に保存し、
ローカル分類・再起動・修復はオフラインで動作する。BOOTHログイン・同期・商品取得には通信が必要。

## 出自とプロジェクト権利の確認

OpenCodeの初期3セッションを読み取り専用で調査し、61write/95editを初回Git commitまで再生した。
初回Gitの**全28ファイルと一致**し、再生不能0件。
最初の生成元は `opencode/muse-spark-1.3-contributor-free`。
その後の作業元もsession metadataから `opencode-go/space-bunny-free` と `openai/gpt-6.1-sol` を確認した。
原入力・認証値を監査文書へ複製せず、モデル、日時、生成ファイルhashと入力basenameを保存した。
初期の外部検索2件は依存CVE調査で、source repositoryの取り込みではなかった。

証拠（私用保全・cloneには非同梱）: `creation-session-evidence.json`、`project-generation-models.json`。

OpenCode利用規約のeffective dateは2026-08-15で、初期生成の2026-09-29より前。
“Your IP”は当事者間で利用者がOutputを所有し、OpenCode側の権利を利用者へ譲渡することを明記する。
OpenAI Services Agreement §4.1にも利用者がOutputを所有し、OpenAI側の権利を譲渡する条項を保存した。
モデルの重み・推論サービス自体のライセンスを、出力コードへ無条件に適用していない。
本体LICENSEのMIT宣言、実生成記録、Git/作業記録と当事者間の出力権利条項に基づき、
選択したプロジェクトソースの配布条件を確認した。

生成物を無条件にhuman FIRST-PARTYへ変更せず、ソース46ファイルはGENERATEDと記録する。
権利譲渡はサービス当事者の権利に限り、他者の権利やAI出力の完全な一意性・非侵害を保証するものではない。
この報告も独立した法的判断・全世界のコード類似性証明ではない。
原文とhash: `public-profile-legal-evidence.json`、`evidence/legal/`。

## 第三者ランタイムの扱いを変更した理由

Google Terms of Service（2026-07-30）“Software in Google services”は、個人・非譲渡の使用許諾と
ソフトウェアのcopy/modify/distribute等の禁止を明記する。
Chrome利用追加条件とembedded creditsを保持したことだけでは、Chrome実体の再配布許諾を確定できない。
そのため、正式配布物にブラウザーその他のランタイムを入れず、利用者端末で各配布元から取得する構成へ変更した。

配布ZIP46ファイル・sdist54エントリーを全件検査し、runtime/vendor/画像/フォント/DB/Cookie/Git履歴の混入0。
配布物はアプリソースと生成設定・文書・起動スクリプトのみ。動的に使用する第三者の条件を本体MITで上書きしない。
取得先はSHA-256固定のPython、SQLite、24wheel。Playwrightからブラウザーを公式取得し、原通知を利用者端末へ保持する。
SQLite/Python/Node/Chromeやnative内部の**再配布条件まで承認した判定ではない**。

以下はこの承認の対象外: 旧offline ZIP、開発リポジトリ全体とGit履歴、`.tools/`、`.venv/`、
`.playwright-browsers/`、`.cache/`、`vendor/`、購入物、DB、Cookie。
旧バイナリ同梱用 `tools/build_release.py` はBLOCKEDのまま。取得後フォルダー全体を公開してはいけない。

## 脆弱性・通知・対応ソース

- 取得依存を実行閉包22wheelとpip/urllib3の24wheelへ限定し、開発・ビルド用の不要な依存を配布用セットアップから除外。
- pip内urllib3を、別途公式hash照合済みの2.8.0から更新。3件の対象advisoryに対応する上流修正を取り込み、
  `response.py`のbyte一致、vendored namespace、requests import、過大チャンク行の読み込み制限を試験した。
- 古いbase pip26.0.1を生成環境から除外し、ensurepip25.0.1を更新。再作成・オフライン修復でも更新を適用する。
- 新しいurllib3 LICENSE、wheel RECORD、`pip/_vendor/BOOTH-MODIFICATIONS.json`を保持。
- msgpackの実使用はC extensionではなくpure-Python fallbackであることを実プロセスで確認。
  pipのsetuptools宣言はpkg_resourcesのサブセットで、PackageIndex/FileListの上流機能を同梱した証明ではない。
  上流の版宣言によるadvisory候補を、実在しない機能の脆弱性と同一視しない。
- アプリ側の固定実行依存は前回62依存の検査対象に含まれ、top-levelの既知advisory検出0件。
  全native-runtimeのCVE不存在や任意のpipネットワーク操作の完全安全性を保証するものではない。
- 正式配布物にcopyleft runtimeを同梱しないため、その再配布に伴うソース提供義務は発生させない。
  MIT本体の全文とNOTICE、全アプリソースを実際に配布する。従来のcertifi source提供物を別版へ代用しない。

## 完成物と試験

| Check | Evidence / result |
|---|---|
| Source / sdist / build-test wheel | current入力45件のbyte一致、原文LICENSE/NOTICE一致、CRC、path、安全な収録範囲を検証 |
| Secrets | 全配布textを限定ルールで走査。core/logging_setup.pyの赤塗りテンプレートだけをbyte照合して解決。未評価0 |
| SBOM | 実ZIP46ファイルと26公式取得入力のhash・参照を照合。private native bundleのSBOMとは明確に分離 |
| Initial setup | OS-only PATH・生成環境なしから初回CLIが公式取得とローカル構築を自動実行 |
| Offline repair | 到達不能proxyでvenv/browserを修復し、既存リストの保持を確認 |
| UI | 実headed Chromeで作成・追加・削除・未分類復元、health/API、実DLL経路を確認 |
| Test suite | 最終開発環境390 passed。Mypy18ソース、Ruff対象検査合格。Starlette TestClient非推奨警告1件 |
| Final promotion | source ZIP/sdistをbyte変更せず正式出力へコピーし、全sidecar checksumとSBOMを再検証 |

実BOOTHアカウント、別OSイメージ、全native binary advisoryは未検証で、READMEと最終報告へ明記する。
これはソース配布の技術的条件を確認した判定で、未実施試験の成功や全ランタイムの再配布許諾を捏造しない。
専用の新規展開フォルダーは試験後に削除済み。commit/push/公開は実施していない。

## 現在の扱い

ソース限定構成の再生成・承認経路は削除済みです。過去の試験・権利証拠は保全します。
現在の監査はフォルダー全体を対象とし、テスト成功だけで著作権・ライセンスの判定を付与しません。
