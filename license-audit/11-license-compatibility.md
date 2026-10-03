# 互換性

監査日: 2026-10-02。判定: **BLOCKED**。

本体MIT宣言と第三者の許諾を分離。Python import、pyd動的load、Playwright Node別process、Chrome別processを区別。
別プロセスでも同梱バイナリのソース提供義務は消えない。compiled wheel、Node静的閉包を確認するまで全体互換性PASSにしない。FFmpegは配布対象から除外。
MPL certifiファイルを改変していないことは本体全体をMPL化する理由ではないが同版source/noticeは保持。
GPL/AGPLを含まないとの全体断定は未実施。専用ネットワーク提供義務も未検出を免除証明にしない。
