# 完成候補の検証

監査日: 2026-10-02。判定: **BLOCKED**。

最終候補を生成後、verifyでSHA-256/CRC/内部path/user data/ソースbyte一致/全ファイルinventoryを検証する。
実行結果はfinal-package-result.json。SBOMはPython62wheelと5容器までの部分版、native/npm/素材閉包は未完了。
証拠収録を完全遵守へ読み替えない。独立展開の結果はclean-candidate-result.json。
