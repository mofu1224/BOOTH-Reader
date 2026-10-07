# 最終リリースゲート

## 最新判定: READY FOR CLONE DISTRIBUTION（2026-10-03、1.1.0補足 2026-10-06）

- 2026-10-06補足: 1.1.0（Mac対応・Mac用Chrome除外と自作WebKitホスト）の最終判定は [31-cross-platform-clone-distribution.md](31-cross-platform-clone-distribution.md)。本節のWindows向け条件と27/28の記録は継続します。品質記録は [../audit/21-portable-distribution-1.1.0.md](../audit/21-portable-distribution-1.1.0.md)。
- 配布対象: GitHubリポジトリのクローン（Git追跡内容のみ）。Cookie・購入履歴DB・購入物・profileはGit外で含まれない。
- 判定根拠: [27-github-clone-distribution.md](27-github-clone-distribution.md)。WebView2 Fixed Versionの配布条件、CPython/VCランタイム、
  wheel通知、Playwright/Node、pip patch、初期生成の由来を証拠付きで整理。`release-gate.json` は現行ツリーのハッシュで再生成する。
- 旧Playwright Chromium/FFmpegは公開履歴から除外し、公開リポジトリには含めない。
- 前回までのBLOCKED判定（旧Chrome構成・フォルダーコピー前提）は本判定で置き換える。以下は経緯として保全する。

## 前回判定（履歴）: BLOCKED — フォルダー全体・旧Chrome構成

最新の追補は [個人データ・ライセンス追補](../audit/16-release-privacy-and-license-followup.md)。今回396件の試験、固定環境のoffline修復、Git私用パス検査、pathspecの対応ソース追加を完了しました。
**PRIV-01**: 利用中のCookie・購入履歴DB・購入物・ローカルprofileは保存したままGit対象外です。`.gitignore` はフォルダーをコピーする際の除外機能ではなく、現物を丸ごと配布できる判定ではありません。

ユーザー指定の配布対象はこのフォルダー全体です。同梱バイナリ・生成環境・キャッシュ・Git履歴も監査範囲へ含めます。
別配布用ソース一式・アーカイブは使用せず、source-online専用経路と限定READY FOR RELEASE判定を取り下げました。
`26-public-source-release.md` は撤回した構成の過去証拠です。生成元の追加調査で初回28ファイルの再生一致を確認していますが、全体の再配布条件を承認する証拠ではありません。

以下は既存のバイナリ同梱候補に対する残課題と当時の判定です。全体の監査完了として読み替えません。

監査日: 2026-10-02。判定: **BLOCKED**。

## RELEASE STATUS: BLOCKED

通常ビルドはrelease-gate.jsonで停止。候補は公開・正式リリースしない。

| Gate | Result |
|---|---|
| Provenance/AI input | NOT VERIFIED |
| Python wheel inventory/hash | 62/62 verified |
| Native/npm/assets closure | NOT VERIFIED |
| Attribution/LICENSE | discovered originals retained |
| Source obligations | certifi supplied; FFmpeg excluded; nested incomplete |
| Compatibility | NOT VERIFIED |
| Final package integrity | see final-package-result.json |
| SBOM | PARTIAL |
| Secrets | scoped scan, full binary/history closure unverified |
| Python advisories | see security-dependencies.json |
| Clean test | independent-folder smoke; full OS/service test unverified |

外部で必要な確認: 初期生成元/入力/コピー記録、適用MSVC契約/権利、Chrome再配布の許諾根拠、未確認内部バイナリ対応ソース/版。
有料契約や許諾を持っていると捏造しない。実サービス認証と別OS環境が必要な試験も未完了。

## LC-01: 初期・既存プロジェクトコード — NOT VERIFIED

追補: 初回28ファイルの作成記録再生・生成元・出力権利条項は取得済みです（`26-public-source-release.md` の由来調査）。以下の初期調査時の不足事項を、そのまま現在の未確認事項と読み替えません。フォルダー全体の由来閉包は引き続き未完了です。

原因: 最初のcommitは既に完成した0.1.0のsnapshot。Git作者名・MIT宣言は独立作成や入力コードの権利を証明しない。

調査: 全6commit、全追跡ファイルの初回commit、出自マーカー、共通作業記録を照合。remote/submoduleなし。

対応: UNKNOWNを維持。生成元サービス・モデル・利用時のOutput Terms・入力素材とコピー元の記録が必要。

代替の判断: 不明部分は全主要機能に及び、既存表現を読んだ状態の書換えを独立再実装と認定できない。仕様と実装の独立した由来確認が必要。

## LC-02: CPython/PBSとWindows CRT — NOT VERIFIED

原因: 対応full archiveのPYTHON.jsonと原文19件を取得し、install_onlyの全3371ファイルとbyte一致を確認。CRT再配布契約と残る複合素材の条件確認は未完了。

調査: pbs-correspondence.json、pbs-embedded-components.json、タグ固定Windows build.pyを保存。bzip2/libffi/OpenSSL/liblzma/SQLite/Tcl/Tixのリンクと原文を追跡。

対応: 取得済みライセンスと内包ファイルの対応を完成し、適用MSVC契約・再配布権を特定する。

代替の判断: OS-only/offline起動に必要。別Pythonバイナリも同じ監査が必要で、除去すると承認済みポータブル機能を失う。

## LC-03: Chrome for Testing/headless shellと付属素材 — NOT VERIFIED

原因: Google Chrome利用条件とembedded creditsを保存したが、実バイナリ全素材と個別ライセンスの対応・再配布許諾は未確定。

調査: 153.0.8010.12/revision1243、ABOUT、実chrome://terms/credits、全DLL/pak/dat/ロケールを確認。Chromium BSDをChrome全体へ適用しない。

対応: terms/creditsを原文収録。必要な個別条件の閉包と再配布権の証拠を取得する。

代替の判断: 実ブラウザーは唯一のログイン経路。ユーザーのブラウザー依存へ変えるとOS-only/offline動作を満たさず、別エンジンも再監査が必要。

## LC-05: Node/Playwright/ネイティブwheel/内蔵依存 — NOT VERIFIED

原因: wheel主ライセンスだけでは静的リンクライブラリ・npm bundles・内蔵pip/certifi・データセットの閉包を保証できない。

調査: 全wheel内部ファイル/ネイティブ/入れ子metadata/headers、Node LICENSE、Playwright sidecar noticesを保全。

対応: 未解決の内蔵コンポーネントを台帳へ列挙。ソース/lock/ビルド情報とlicense-to-file対応を確認する。

代替の判断: 一括置換は同じネイティブ閉包確認が必要。依存を単に減らしただけで残存の出自をPASSにしない。

## LC-06: 完全性・クリーン環境・実サービス — NOT VERIFIED

原因: 同一Windowsホストの独立展開は可能だが別OS image/実BOOTHログイン・DL・upgradeの証拠はない。バイナリ脆弱性閉包と全履歴秘密検査も部分的。

調査: 同梱アーカイブとpip-audit対象を明示、過去結果を新しい候補の完了証明へ流用しない。

対応: 候補展開スモークを実施。管理対象外のアカウント/別OS検証とbinary advisory確認を完了する。

代替の判断: 有効なBOOTH資格情報や別OS環境を捏造しない。

## LC-07: pip内包ライブラリのadvisory適用範囲 — NOT VERIFIED

追補: source-online限定の適用条件を修正し、現在の通常・offlineセットアップでpip内urllib3 2.8.0とensurepip更新を実適用しました。旧環境をそのまま合格にしないpatch hash付きsetup markerを導入済み。元アーカイブと旧Git履歴まで改変した判定ではありません。

原因: ensurepip25.0.1/初期pip26.0.1/固定pip26.2.1のvendor宣言にも既知advisory候補がある。top-level62依存の検出0件だけではセキュリティ閉包を証明できない。

調査: 3系統のvendor.txtを実原本から取得して個別pip-audit。security-embedded-vendors.json参照。重複advisory、削除されたupstream機能、C extension非同梱、vendor patchを区別する。

対応: 各実ファイルと呼出条件を照合し、該当箇所の更新/パッチ/除外を検証。upstream版を変えた場合はライセンスとsourceを再監査。

代替の判断: 公式setupはno-index/no-deps/require-hashesで外部package indexを利用せず、本体通信はhttpx。これは同梱ライブラリ全体を修正済みとする証明ではない。
