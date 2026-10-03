# GitHubクローン配布の追加監査（2026-10-03）

対象はGit追跡ファイルと、除外されていない追加候補の全体です。前回の [27-github-clone-distribution.md](27-github-clone-distribution.md) の同梱構成を維持し、利用条件・検証範囲・CIの残件を修正しました。最終判定と入力ハッシュは `release-gate.json`、実行結果は [../audit/18-clone-distribution-followup.md](../audit/18-clone-distribution-followup.md) を参照してください。

判定: **READY FOR CLONE DISTRIBUTION**。現行Git候補の範囲で、原文・対応ソース・利用者向け条件と検証を整備しました。変更後はゲートの入力一致を再確認します。

## 現行構成と原文の確認

- CPython/PBS、SQLite、固定62wheel、Playwright内Node、WebView2 Fixed VersionとSDKの同梱payloadは前回と同一です。`vendor_payload.py verify` で分割片・連結内容・lockのSHA-256を検証しました。
- `check_license_evidence.py` で原文・対応ソース・一次証拠の **2,137参照**と、ハッシュ名付き原文 **1,506ファイル**を検証し、不足・改変・ハッシュ不一致は0でした。
- certifi・内包certifi・pathspecの対応ソース、native packageの同版ソース、Cargo.lock対応crateを保持しています。前回の版別通知と対応ソースの確認結果を、同じハッシュの入力について再利用しました。
- 旧FFmpegの通知や旧構成の監査資料は履歴資料としてGitに含まれます。通知の存在は、現行payloadへFFmpegを同梱したことを意味しません。旧Chromium/FFmpegのpayloadを持つブランチ参照は公開候補から外しました。

## Microsoftコードの条件

WebView2原文Section 2(b)(ii)は、下流配布者と外部利用者への保護条件の継承、Section 8はSmartScreen通知を要求しています。原文を保存するだけでは、この利用者向け対応を実装したことになりません。

- [../THIRD_PARTY_TERMS.md](../THIRD_PARTY_TERMS.md) に適用原文を組み込み、利用・再配布の条件として同意を要求します。条件の対象はMicrosoftコードに限定し、本体MIT・Python・個別OSSの権利を保持します。
- Web画面の案内リンクから、利用条件とWebView2 Runtime/SDK・CPythonの原文を読めます。ブラウザー生成前にも条件とSmartScreen通知をstderrへ表示します。
- SmartScreenを無効化する設定は導入しません。Microsoftへの情報送信があること、プライバシーステートメントとPrivacy Whitepaperを通知します。
- CPython原文の「Additional Conditions for this Windows binary build」も保持します。これはMicrosoftコードへの保護条件を下流へ継承する必要を明記しています。VC再配布の一般案内を、無条件の許諾と読み替えてはいません。

一次情報の再確認:

- https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution
- https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170
- https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution
- 同梱WebView2/SDK原文、CPython Windows binary buildの原文。

## 公開対象の検証

旧ZIP収録リストは、追跡済みの `license-audit/24-current-final-verification.md` を除外していました。現行の `repository_files.collect` は収録リストで絞らず、Git候補の全体を検査します。私用ファイルや非現行chunkを見つけた場合は、黙って除外せず失敗します。

`check_distribution.py` は、現行全入力のハッシュ・配布scope・Gitプライバシーを確認します。ゲートは内容の変更・追加・削除で古くなります。ハッシュの再生成だけで新しい依存やライセンス条件を承認する仕組みではありません。

本体のハッシュはGitのtext/eol属性に合わせたSHA-256です。`THIRD_PARTY_LICENSES/`、`SOURCE_OBLIGATIONS/`、`license-audit/evidence/` は `-text` とし、上流原文・一次証拠のバイトを改行変換しません。独立したチェックアウトで、元候補との全入力一致と原文・対応ソースの整合性を確認します。

## 秘密情報スキャンの誤検知

ディレクトリ単位のスキャン除外を撤去し、公開履歴を再走査しました。233候補は、ScanCodeのライセンスID200件、監査入力のSHA-256 23件、Google公式ページの公開フロントエンド識別子10件でした。GCPルールの判定を絞った後にgenericルールが重複検出した2件も、同じ公開識別子です。

原文は改変せず、対象ファイル・ルール・値の形式を組み合わせて誤検知だけを許可しました。公開ページ・ScanCode原文はハッシュ整合性検査の対象です。合成fixtureも既存の限定許可を保持し、ディレクトリ全体や実キー一般を許可しません。値は監査記録に複製しません。

## 検証範囲

記録した原文、取得元、ハッシュ、対応ソース、利用者向け条件の整備に基づく配布準備の技術的判定です。実BOOTHアカウントの通し疎通、別PC・Windows10・別OS、GitHub runner実行、nativeバイナリ全byteの独立した法的診断は今回の確認範囲ではありません。
