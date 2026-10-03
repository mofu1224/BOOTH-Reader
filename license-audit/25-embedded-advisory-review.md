# 内包依存のadvisory候補

監査日: 2026-10-02。判定: NOT VERIFIED / LC-07。

同一IDの重複を除き、parent・実申告版ごとに記録する。上流の全パッケージとpipの内包サブセットは同じではなく、未検証の実脆弱性件数として扱わない。

| Parent | Component | Version | Unique advisory IDs | Fixed versions |
|---|---|---|---|---|
| ensurepip-25.0.1 | msgpack | 1.1.0 | PYSEC-2026-3625 | 1.2.1 |
| ensurepip-25.0.1 | requests | 2.32.3 | PYSEC-2026-1872, PYSEC-2026-2275 | 2.32.4, 2.33.0 |
| ensurepip-25.0.1 | idna | 3.10 | PYSEC-2026-215 | 3.15 |
| ensurepip-25.0.1 | urllib3 | 1.26.20 | PYSEC-2026-1999, PYSEC-2026-1998, PYSEC-2026-1994, PYSEC-2026-1996, PYSEC-2026-141, PYSEC-2026-4177, PYSEC-2026-4175 | 2.5.0, 2.6.0, 2.6.3, 2.7.0, 2.8.0 |
| ensurepip-25.0.1 | pygments | 2.18.0 | PYSEC-2026-2987 | 2.20.0 |
| ensurepip-25.0.1 | setuptools | 70.3.0 | PYSEC-2025-49, PYSEC-2026-3447 | 78.1.1, 83.0.0 |
| CPython-3.12.13 | msgpack | 1.1.2 | PYSEC-2026-3625 | 1.2.1 |
| CPython-3.12.13 | requests | 2.32.5 | PYSEC-2026-2275 | 2.33.0 |
| CPython-3.12.13 | idna | 3.11 | PYSEC-2026-215 | 3.15 |
| CPython-3.12.13 | urllib3 | 1.26.20 | PYSEC-2026-1999, PYSEC-2026-1998, PYSEC-2026-1994, PYSEC-2026-1996, PYSEC-2026-141, PYSEC-2026-4177, PYSEC-2026-4175 | 2.5.0, 2.6.0, 2.6.3, 2.7.0, 2.8.0 |
| CPython-3.12.13 | pygments | 2.19.2 | PYSEC-2026-2987 | 2.20.0 |
| CPython-3.12.13 | setuptools | 70.3.0 | PYSEC-2025-49, PYSEC-2026-3447 | 78.1.1, 83.0.0 |
| pip-26.2.1 | msgpack | 1.1.2 | PYSEC-2026-3625 | 1.2.1 |
| pip-26.2.1 | urllib3 | 2.7.0 | PYSEC-2026-4177, PYSEC-2026-4176, PYSEC-2026-4175 | 2.8.0 |
| pip-26.2.1 | setuptools | 70.3.0 | PYSEC-2025-49, PYSEC-2026-3447 | 78.1.1, 83.0.0 |

## 適用判定と現在の対策

- pipのsetuptools宣言は主としてpkg_resourcesを内包し、setuptools全体を同梱した証明ではない。PackageIndex/FileListのadvisoryを版だけで適用しない。
- msgpackのUnpacker/C extension問題は、pipのfallback実装と実呼出条件の確認が必要。版だけで修正済み/該当と確定しない。
- urllib3/requests/idnaは通信処理の候補。公式setupはno-index/no-depsでネットワーク取得を行わず、アプリ本体はhttpxを使う。任意のpipネットワーク利用まで修正済みとは判定しない。
- 更新による内包importやvendor patchの破損を避けるため、上流版を単純上書きしない。適用する修正の確認と再監査が済むまでLC-07を維持する。
- 原advisoryの取得結果はadvisory-evidence.json。配布バイナリ全CVEの網羅検査ではない。
