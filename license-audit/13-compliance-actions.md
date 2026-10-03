# 実施した遵守対応

監査日: 2026-10-02。判定: **BLOCKED**。

1. 原本archive/wheel全ファイルと版固定registryを再調査。
2. 原文LICENSE/COPYING/NOTICE/AUTHORS/sidecarsをTHIRD_PARTY_LICENSESへ複写。
3. certifi/packageurl使用版の公式sdistを取得・hash照合、source提供案内を実装。
4. 本体NOTICE、SQLite差替え要約、第三者条件分離を追加。
5. wheel/sdist/launcherの収録ルールを修正。
6. 通常buildは不足/未解決/stale監査を拒否。--audit-candidateでローカル検証に限定。
7. 旧成果物を正式最新版と誤認しないREADME/PORTABLE案内と候補checksumを追加。
未確認の権利を新しいMIT宣言・コードの書換えで隠さない。
