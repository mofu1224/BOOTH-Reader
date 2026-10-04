# 利用者導線のフールプルーフ化（2026-10-04）

`start.bat` 単一入口の上に、迷いや誤操作を減らす案内と安全弁を追加した。新しい第三者コンポーネント、依存パッケージ、同梱物、取得元、外部サービスは追加していない。

## 変更

- 起動・復旧メッセージを日本語に統一（`tools/manage_portable.py`、`tools/bootstrap.ps1`）。同梱物の欠損・破損、初回展開のタイムアウト、非対応OSでは、git clone による復元とデータ (app.db・data・BOOTH-Reader-Library) を削除しないことを案内する。PowerShell 5.1で日本語リテラルを正しく読むため `bootstrap.ps1` はUTF-8 BOM付きとした。
- `--repair` / `--recreate` / `--update` は起動中のWeb UIを検出すると、環境を変更する前に終了を案内して停止する。固定環境 (.venv) が使用中で更新できない場合も、終了方法とデータ保護を案内して停止する。
- `--check` は準備状態をstderrへ表示（0=準備済み）。`/?` `-?` `help` `version` を受け付ける。
- CLIの使い方エラー（不明コマンド・不明フラグ）に日本語の案内を追加し、エラー内の実行例を実際の入口 `start.bat` に統一（`cli.py`、`core/errors.py`、`core/auth.py`、`web/app.py`）。
- Web UIに初回3手順、同期0件時のCookie確認案内、Cookie置き換えと未完了ファイル削除の確認、購入ファイル保存先の表示、レイアウト変更時ヒントを追加（`web/ui.py`、`web/app.py`）。

## ライセンス範囲

- 変更は起動スクリプト、CLI/Webの案内、テスト、ドキュメントのみ。`vendor/windows-x64/` の同梱payload、`requirements-portable-lock.txt`、`portable-manifest.json`、原文・対応ソースは変更していない。`vendor_payload.py verify`、`check_license_evidence.py` は変更後もPASSした。
- 配布scope・release_status・blockersは変更せず、`release-gate.json` の `input_hashes` / `input_count` のみ現行Git候補へ更新した。ハッシュ更新は新しい依存や条件の承認ではない。

## 検証

ローカル検証の結果は [../VERIFY_LOG.md](../VERIFY_LOG.md) に記録した。

## 追補: 00〜14工程の再確認（2026-10-04）

型診断修正、検証ランチャーの所有PID限定、停止後バックアップ・復元手順、候補保持とUI検証を追加した。配布方式・第三者物・lockは同じ。原文2,137参照・1,506原本、vendor全体、PyPI固定62wheel（派生pipは原本と派生の対応）、pip check、pip-auditを再確認し合格した。既存の同版・同ハッシュのライセンス判断を再利用する。

`release-gate.json` の入力を現行候補へ対応付ける。これはライセンス整備と入力一致の判定で、実BOOTH通しや全対応環境の合格ではない。製品全体の条件と残件は [../audit/19-release-scope.md](../audit/19-release-scope.md)、候補固定後の実行証拠・チェック表は候補外のローカル記録で管理する。
