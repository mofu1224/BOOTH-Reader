# テスト結果

## 本体・回帰・UI

- 開始時: **238 passed / 31.44秒**。
- 通常開発環境の全体試験: **306 passed / 36.49秒**。`junit-final.xml` に機械可読結果を保存。その後、容量不足・権限不足のfault injectionを2件追加した。
- BR-A15追加前のhash固定runtime（FastAPI0.141.1）＋pytest別環境: **308 passed / 33.52秒**。
- BR-A15追加後の最終固定runtime全体試験: **310 passed / 36.34秒**。`junit-locked.xml` に最新の機械可読結果を保存。開始時より72件増加。
- 新しい回帰はHTTP、DL、ZIP、Web UI、worker、parser、DB、分類/CSV、build、tooling、secret境界、recovery。個別の修正前失敗と修正後結果は [06-repair-log.md](06-repair-log.md)。
- 実Chromiumと実loopback HTTPでリスト作成→分類→削除→未分類復元。JavaScript例外なし。
- 異常系: Cookie失効/前提不足/通信、partial/CRC/Zip Slip/bomb/範囲不一致/別版、DB fault/future/破損、CSV式/制御文字、cross-origin、worker死活/応答不明write、出力tree保護。
- 最終静的検査: ruff check合格、ruff format 68 files合格、mypy 17 source files合格、compileall合格、pip check合格。
- 非推奨警告1件: StarletteのTestClientがhttpx利用をdeprecatedと報告。現行試験は動作し、診断を隠すfilterは追加していない。実行HTTPクライアントはhttpxを維持。

## 成果物・環境

- 新規仮想環境でhash固定runtime21パッケージを導入、wheelをno-deps install。isolated `python -I`でCLI/tools import・version・DB初期化・JSON照会成功。
- wheelはsdistからビルドできた。launcher ZIP、SHA256SUMSを生成。
- 1.0.3最終候補RC: **44/44 PASS、FAIL/WARN/SKIP=0**。clean install、repo-local browser導入、CLI/JSON/異常系/HTTP/200並列worker、dependency audit、artifact secret scanを含む。
- BR-A15を含む展開source bundleの最終全試験: **308 passed / 2 skipped / 38.12秒**。skip2件はsource bundleに`.venv`がないため、venv health/base fixtureの適用対象がないことによる。ブラウザ試験のskipではない。
- 最終成果物を `dist/1.0.3/` に再生成し、BR-A15を含むRC候補と本体・テスト・依存定義の**44ファイルがbyte一致**することを確認。ZIP CRC/checksum/必須ファイル/利用者データ除外も合格。最新結果は `artifacts-final.json`。
- 最終wheelを固定依存別venvに導入し、`python -I`によるinstalled CLI/worker/doctor smoke合格。portable情報とCookieなしは非fatal警告で、DB・browserを含むfatal検査はすべて合格。

Python3.10/3.11/3.13のCI matrix、Windows10、別PCは今回未実行。既存の過去記録を今回の成功件数に含めない。
