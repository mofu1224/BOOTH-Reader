# Mac起動スクリプトの実行権限復旧（2026-11-04）

## 症状と原因

- WindowsでフォルダーをZIP圧縮してMacへ移すと、ZIPにUnixの実行権限が保存されない。`start.command`と`start.sh`が`0644`になり、Finderのダブルクリックも`./start.command`も`permission denied`で起動できない。
- 実際にMacの`~/Downloads/BOOTH-Reader`で`start.command`が`-rw-rw-r--`、ZIP内の`external_attr`が`0o0`であることを確認した。`bash ./start.sh`では起動でき、Windows用`.venv`と`.tools/python`もMac用に再構築された。
- 原因はアプリ本体ではなく、配布物の移動方法がUnixの実行権限を保持しなかったこと。ただし、READMEのMac向け主経路が`start.command`のダブルクリックであり、復旧手段が目立っていなかった。

## 修正

- `tools/bootstrap.sh`の起動直後に`start.command`・`start.sh`・`tools/bootstrap.sh`の実行権限を検査し、失われていれば`chmod +x`で復元する。復元した場合は`[portable] Restored launcher permissions.`を表示する。
- 同スクリプトで、同梱Pythonの展開に失敗したときの退避先`backup`が未初期化の場合に`set -u`で失敗する問題を修正した。
- README・CROSS_PLATFORM・PORTABLEに、Windows製ZIPや権限を保持しないコピーを使った場合の`bash ./start.sh`復旧手順を追記した。
- `tools/verify_clone_macos.py`で、Windows ZIPを模して全`.sh`/`.command`を`0644`にした独立コピーを作り、起動後に実行権限が復元されることを検査するようにした。

## 検証

| 環境 | 結果 |
|---|---|
| Mac実機（macOS 27.2 arm64） | `chmod 644 start.command start.sh tools/bootstrap.sh`後に`bash ./start.sh --check`で3ファイルが`0755`へ復元。`./start.command --check`と`./start.sh --check`は終了0。 |
| Mac独立クローン | `tools/verify_clone_macos.py`が全7チェックPASS。Windows ZIP相当の権限喪失からの復元、オフライン初回準備6.558秒、CLI、実WebKit 1440/768/390px、移動後の再構築、修復拒否、署名破損復旧、再起動を確認。 |
| Mac WebKit | `tests/test_native_webkit.py` 1 passed。 |
| Windows | `pytest -q` 508 passed・1 skipped（macOS専用）、Ruff・format・mypy 25ソース・compileall・pip check・portable 18/18・vendor整合・原文照合PASS。 |
| GitHub Actions | run `41757361188`（`2b4590d`）のWindows品質・Windowsクローン・Mac arm64品質・Macクローン・依存監査・秘密検査が全ジョブ成功。 |

## 確認範囲

- 実機はApple Silicon Mac（macOS 27.2）とWindows 11 x64。Intel Mac、macOS 14実機、Finderの画面操作そのものは未確認。実行権限が復元された後の直接実行と、権限がない`.command`がFinderから実行されないことは確認した。
- この修正はアプリ本体・依存・同梱物を変更しない。DB・Cookie・購入物の形式変更もない。
