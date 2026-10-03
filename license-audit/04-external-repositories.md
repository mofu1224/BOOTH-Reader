# 外部リポジトリ監査

監査日: 2026-10-02。判定: **BLOCKED**。

実使用の版/URLは `packages.json` とregistry evidence。
CPython/PBS20260325、Playwright v1.63.0、Node同梱LICENSEが示すJoyent由来、Playwright NOTICEが示すPuppeteerを確認。
Playwrightの使用ファイルはwheel全ファイルとdriver/npm bundle。Apache LICENSE/NOTICE/sidecarsを原文保持。
winldd同タグREADMEはVS2019/static CRT/dbghelpを明記するがrevision1007バイナリとのbyte対応・CRT権利は未完了。
登録upstream URLはソース一致の証明ではない。未公開・記録されなかった参考/コピー元はNOT VERIFIED。`upstream-evidence.json`参照。
