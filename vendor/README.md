# Git管理するポータブル依存

このフォルダはクローンに含める必須ファイルです。Git LFSや外部ダウンロードは使いません。

`windows-x64/manifest.json` にCPython、修正版SQLite、固定62wheel、ブラウザの版に対応する原本とハッシュを記録しています。バイナリは1ファイル40 MiB以下の `.chunk` に分割し、通常のGitで管理します。

初回の `start.bat` が自動で検証・展開し、生成環境と利用者データはこのリポジトリ内へ保存します。セットアップ用の別スクリプトはなく、必要かどうかは起動時に自動判定します。

原本のライセンス通知を保持しています。出所と条件はルートの `THIRD_PARTY_NOTICES.md` と `portable-manifest.json` を参照してください。Cookie・DB・購入ファイル・ブラウザ利用者プロフィールは含めません。

依存を意図的に更新した開発時だけ、検証済みのローカル取得物から `.venv\Scripts\python.exe tools\vendor_payload.py build` で再生成します。通常の起動では取得・更新を行いません。
