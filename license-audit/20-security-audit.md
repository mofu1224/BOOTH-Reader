# セキュリティ・秘密情報

監査日: 2026-10-02。判定: **BLOCKED**。

使用版全62Python依存をpip-auditで照合し既知vulnerabilityなし(security-dependencies.json)。
これはChrome/Node/CPython/CRT全binaryのCVE完了を意味しない。内包pip3系統の申告版検査にはadvisory候補がありsecurity-embedded-vendors.jsonとLC-07を参照。FFmpegは現行配布対象外。
197個の到達可能なGit text blobとworktreeを5種ルールで走査。検出21レコード。core/logging_setup.pyの赤塗り用ヘッダー、tests/test_auth_security.pyのダミーPEM/テスト文字列、JUnitのテスト識別子を含む。個別評価はsecret-triage.json。既知のダミーであることを内容/テスト目的で確認した範囲だけ解決する。
secret-scan.jsonに値は保存していない。binary history blob/ユーザーデータ/全種類資格情報は未検証。
最終候補の追加検出をdistribution inventoryへ記録、未知検出を無条件無視しない。
ruff security規則と回帰試験の結果はverification.json。全リポジトリ脆弱性不存在とは断定しない。
