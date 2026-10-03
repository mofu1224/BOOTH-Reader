# クローン配布の最終確認（2026-10-03）

GitHubのリポジトリクローン配布を対象に、既存の配布準備を再点検しました。個人データを保全し、別の配布用アーカイブを生成しない構成へ統一します。

## 修正内容

| 項目 | 原因と対応 |
|---|---|
| クローン検証の欠落 | 旧ZIP収録リストが追跡済み監査ファイルを省いていた。Git追跡・追加候補の全体を検証する共通処理へ変更 |
| Git改行変換 | 本体はGit属性に従う正規化ハッシュへ変更し、上流原文・対応ソース・一次証拠は改行変換禁止。チェックアウト後との全入力一致を検証 |
| 配布方針とCIの不一致 | wheel/sdist生成・配布物アップロード・タグ公開が残っていた。検証結果だけを保存するCIへ統一し、アーカイブ生成コマンドを停止 |
| Webの機密値返却 | 例外とジョブ失敗表示にCookie・署名付きURL等が残った。既知エラーは伏せ、想定外エラーは本文を返さない |
| ブラウザー起動 | 同時起動で実行中EXEを再コンパイルする構成。ソース・SDKのハッシュごとにホストを生成・再利用し、生成EXEの整合性ハッシュで破損時は再生成 |
| 起動失敗の後始末 | プロセス生成前後の失敗で一時プロフィールが残った。生成失敗時の削除とログハンドル回収を追加 |
| CLIのDB指定 | PowerShellのadvanced bindingが`--db`を`-Debug`別名として消費。basic scriptの残余引数でそのまま転送し、前後指定と日本語・空白パスを実BATで検証 |
| 私用ファイル | Cookie名・DBバックアップ・任意名インポートの保存先を補強。`.private/` 等を除外し、実Gitの除外検証を追加 |
| Microsoft条件 | 原文保管に加え、利用者向け条件・原文表示・SmartScreen通知を整備 |
| 監査出力 | 依存台帳を再測定すると追跡済み報告を上書きする処理を、除外済みのcurrent記録へ変更 |

## 基準と局所検証

- 作業開始時: `pytest -q` **397 passed**。
- Webエラーの3経路とブラウザー準備の2経路を、合成値・隔離先で失敗として再現した後に修正。
- Git候補・ゲート・プライバシーの局所検証: 19 passed。ブラウザーとWebの局所検証: 12 passed（その後の追加検証は最終結果で記録）。
- 原文・対応ソース・一次証拠: 2,137参照、ハッシュ名付き原文1,506、整合性不一致0。
- vendor: 分割片・連結内容・lockの整合性PASS。
- 公開履歴のgitleaks: ディレクトリ一括除外なしで誤検知を精査し、未解決0。

## 最終検証

- クリーンなGit候補チェックアウトの全回帰: **410 passed**（既存Starlette TestClientの非推奨警告1件のみ）。
- `ruff check .` / `ruff format --check .` / `mypy`（19ソース）/ `compileall` / `pip check`: PASS。
- `pip-audit --local`: 既知脆弱性0。固定62wheelのPyPI公開ハッシュ照合とオフラインlock解決: PASS。
- `check_portable.py`: 18/18 PASS。
- `verify_clone.py`: PASS。生成環境なしの初回Web/CLI、日本語・空白パスへの移動、旧配置の読み取り拒否、合成DB/CSV/Cookieと画面操作、ブラウザー破損復旧、終了・再起動を確認。元index不変、指定した外部profile/tempへの書き込み0、所有したテスト配置は削除済み。
- 全 **2,529入力**（ゲート自身を除く）の元候補とチェックアウト後のハッシュ一致、コピー内の原文・対応ソース検証: PASS。
- 秘密情報: 公開履歴と、起動前のクリーンなGit候補をgitleaksで検査し、未解決0。原本同梱payloadは前回と同じハッシュのため、既存の内部棚卸し・秘密検査結果も再利用しています。
- CIと同じCLIスモーク7コマンド（各失敗で停止）: PASS。途中で発見した`--db`消失を修正し、実BAT回帰を追加した後にクローン全回帰を再実行しました。
- `check_release_hygiene.py --git-only`: 追跡・追加候補・到達可能履歴の私用パス0。

機械証拠は除外済みの `audit/clone-verification.json` / `audit/junit-clone.xml`、合成試験ログは `.cache/clone-evidence/` に保持します。最終文書とゲートの記録更新は機能検証後に行い、コード・同梱物については上記結果を再利用します。

## 個人データとGit

- 実DB・Cookieは開始時と終了時のSHA-256が一致しました。内容は表示していません。購入物・ブラウザープロフィールはテストへコピーしていません。
- `backup/pre-publish-20261003` は、リポジトリ外の既存bundleについて完全履歴と対象commitを検証した後、ブランチ参照だけを除去しました。`main`、その履歴、元のGit indexは変更しません。
- 現行参照は `main` のみです。旧履歴のbundle・reflogは公開対象ではありません。通常のリモートcloneは到達可能な公開履歴を取得します。

## ライセンスと残る確認範囲

- ライセンスの追加監査は [../license-audit/28-clone-distribution-followup.md](../license-audit/28-clone-distribution-followup.md)。
- 実BOOTHアカウントの通し疎通、別PC/Windows10/別OS、GitHub runnerでの実行は今回未実施です。
- コミット・push・GitHub公開・配布用ZIP/wheel/sdistの作成は実施しません。

## 追補: CIのNode 24対応（2026-10-03）

- Node 20撤去（2026-09-23）に合わせ、`.github/workflows/ci.yml` を更新しました。`actions/checkout` と `actions/upload-artifact` はv7.0.1のcommit SHAへ固定し、`gitleaks-action@v2` は公式gitleaks 8.30.1バイナリ（SHA-256照合）を実行するステップへ置換しました。`GIT_LOG_ARGS` はv2/v3とも未対応のため削除し、`--log-opts=--all` で全履歴を走査します。
- `release-gate.json` は `.github/workflows/ci.yml` のハッシュのみを更新しました。再検証は `check_distribution` 2,530 PASS、`check_license_evidence` PASS、`check_portable` 18/18、`vendor_payload verify` PASS、`verify_clone` 89チェックPASS（410 passed）。CI相当gitleaksは実機でexit 0・検出0です。
