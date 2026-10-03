# セキュリティ検査

## 実装と動作

- scoped CookieJar: domain/path/secure/expiry/host-only、redirect、logout後pool残留を検証。
- Cookie: ACL失敗時は保存を中止、空unique tmpを制限してから書込、atomic置換、以前のjar保持。
- ログ/CLI診断: 認証key、Bearer/JWT/PEM、URL query/userinfo、exc_info/stack_infoをredact。監査記録へCookie値を保存していない。
- Web: loopback bind、Host allowlist、scheme込みOrigin、cross-site Fetch Metadata拒否、JSON validation、HTML/JS escaping、argvによるsubprocess。
- DB: parameterised SQL、sort allowlist、FK、future schema拒否、atomic migration。
- ファイル: item containment、台帳名検証、ZIP traversal/Windows ADS/reserved names/case collision/size/ratio/count制限、CRC成功後atomic member publish。
- 配布: 非empty出力先の非破壊拒否、除外ancestor/symlink、user data/secret store除外。

## ツール結果

- `ruff check .`: security rulesを含め合格。
- `pip_audit --local`: インストール済みruntime/dev集合に既知の脆弱性報告なし。
- `pip_audit -r requirements-lock.txt --require-hashes --disable-pip`: 固定runtime21パッケージに既知の脆弱性報告なし。
- 実行時点のadvisory情報に基づく結果であり、未知の脆弱性不存在の保証ではない。
- 最終RCの配布ZIP/static secret-shape scan: 合格（product58ファイル、testsの鍵/credential storeも確認）。clean install依存監査も既知の脆弱性報告なし。
- Git全履歴のsecret scan、GitHub CI security job、ライセンス法務判定は今回未実施。
