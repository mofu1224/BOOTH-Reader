# 単一エントリ起動への変更（2026-10-04）

起動スクリプトを `start.bat` 一つへ統合した。`setup.bat` / `start-web.bat` / `cli.bat` / `run.cmd` / `run.ps1` / `run.sh` を削除し、セットアップの要否と引数の種別は起動時に自動判定する。ルーティングは `tools/manage_portable.py` の `resolve_mode` に集約し、引数なし・ポート番号はWeb UI、`--repair` などのフラグと `setup` / `repair` / `update` は環境の再同期、それ以外はCLIとして実行する。

## ライセンス範囲

- 変更したのは起動スクリプト、引数ルーティング、利用者向け案内、CI、試験、ドキュメントのみ。新しい第三者コンポーネント、依存パッケージ、同梱物、取得元、外部サービスは追加していない。
- `vendor/windows-x64/` の同梱payload、`requirements-portable-lock.txt`、`portable-manifest.json`、原文・対応ソースは変更していない。`vendor_payload.py verify`、`check_license_evidence.py` は変更後もPASSした。
- 配布scope・release_status・blockersは変更せず、`release-gate.json` の `input_hashes` のみ現行Git候補へ更新した。ハッシュ更新は新しい依存や条件の承認ではない。

## 検証

`start.bat` のWeb起動・CLI転送・`--check`・`--repair` 経路と、cold clone/再配置を含む `tools/verify_clone.py` の結果を [../VERIFY_LOG.md](../VERIFY_LOG.md) に記録した。引数なし起動のブラウザー自動オープン・二重起動検出・使用中ポートの自動回避・失敗時のウィンドウ維持は単体試験と実BATで確認した。ルーティングと単一エントリの不変条件は `tests/test_portable.py`、`tests/test_portable_bootstrap.py`、`tests/test_launcher_forwarding.py`、`tests/test_web_cli.py` が固定する。
