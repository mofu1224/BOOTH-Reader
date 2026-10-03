# 配布対象

監査日: 2026-10-02。判定: **BLOCKED**。

現行監査候補はdist/license-audit-20261002-finalに生成。以前の候補は現行版の証拠ではない。正式配布の承認ではない。
launcherとsdistはvendorのPython/SQLite/wheel/browserアーカイブを含む。wheel自体はbootstrap vendorを同梱しない。
THIRD_PARTY_LICENSES/NOTICEをwheel metadataとsource/launcherへ収録、SOURCE_OBLIGATIONSはsource/launcherへ収録。
全内部ファイル: distribution-inventory.json、再構成payload内部: archive-files.json、元容器: containers.json。
既存dist/release/ローカル環境はlocal-inventory.jsonに識別、今回のクリアランス対象へ混同しない。
