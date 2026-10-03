# 再生成とリリースノート

監査日: 2026-10-02。判定: **BLOCKED**。

## 変更

1.0.3の機能版は維持。NOTICE/原文ライセンス/同版source/SBOM/監査台帳/ブロックゲートを追加。正式公開は行っていない。

## 環境

Windows x64、CPython3.12.13/PBS20260325、固定62wheel、setuptools84.0.0/wheel0.48.0/build1.6.1。
setupはGit-owned材料からオフライン復元。外部取得は証拠取得時のGitHub/PyPI/公式siteのみ。
環境変数はcore.portable.apply_portable_envでrepo内cache/TEMP/PLAYWRIGHT_BROWSERS_PATHを設定。

```powershell
.venv\Scripts\python.exe tools/license_compliance.py inventory --online
.venv\Scripts\python.exe tools/license_report.py --acquire
.venv\Scripts\python.exe tools/license_report.py
.venv\Scripts\python.exe tools/build_release.py --out dist/license-audit-20261002-final --audit-candidate
.venv\Scripts\python.exe tools/license_compliance.py verify --directory dist/license-audit-20261002-final
```
出力先が既存なら別の空ディレクトリを指定。package inputsはbyte照合、ZIP/tar timestampによるbit-for-bit再現性は保証しない。
最終inventoryは監査後に外部証拠として保存するため、自己参照hashをarchive内部へ後付けしない。
