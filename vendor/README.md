# 同梱依存

クローンに必須です。Git LFS・外部ダウンロードは不要です。

`windows-x64/manifest.json` にCPython・SQLite・固定62wheel・ブラウザーの原本/ハッシュを記録。バイナリは40MiB以下の `.chunk` で通常Gitに格納します。

`start.bat` が準備を判定・検証・展開し、環境とデータをリポジトリ内へ保存します。

原通知を保持。出所・条件は [第三者通知](../THIRD_PARTY_NOTICES.md) と `portable-manifest.json`。Cookie・DB・購入物・プロフィールは非同梱です。

依存変更時だけ、検証済みローカル原本から `.venv\Scripts\python.exe tools\vendor_payload.py build` で再生成します。通常起動では取得・更新しません。
