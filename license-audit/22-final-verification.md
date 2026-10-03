# 最終候補の実測結果

この文書は以前の `dist/license-audit-1.0.3-final/` の検証記録です。
現行版は `23-reaudit-20261002.md` と `24-current-final-verification.md` を参照してください。

## 結論

**RELEASE STATUS: BLOCKED**。候補の動作・整合性は確認したが、ライセンス閉包と権利確認は完了していない。
対象は `dist/license-audit-1.0.3-final/` のZIP・wheel・sdist。公開・commit・pushは行っていない。

## 確認したこと

| 検証 | 結果・証拠 |
|---|---|
| SHA-256 | 3アーカイブとDO-NOT-DISTRIBUTE表示を照合。`final-package-result.json` |
| アーカイブ | 1,169エントリーのpath/内容、ZIP CRC、symlink・ユーザーデータ除外を確認 |
| 監査入力との一致 | ZIP内AUDITED-INPUTSの全入力SHA-256と実ソースを照合 |
| 原文通知 | 各アーカイブ内の208ファイルとLICENSE/NOTICE/THIRD_PARTY_NOTICESが原本とbyte一致 |
| ソース提供物 | ZIP/sdistのcertifi・packageurl使用版sdistと案内が原本とbyte一致 |
| vendor | 配布物から各分割片と連結SHA-256を再検証。原本内部8,421ファイルの台帳へ対応 |
| SBOM | 固定62wheelと5archive容器のhash一致・依存参照を検証。内部native/npm/素材閉包はPARTIAL |
| 開発環境 | Ruff変更ファイル検査、Mypy17ソース、pytest357 passed。既存TestClient非推奨警告1件 |
| Python依存の既知脆弱性 | 固定62依存にpip-auditの検出なし。その他バイナリのCVE完了は未確認 |
| 秘密情報 | Git197text blob/worktreeの19候補と配布物13候補は既知ダミー・赤塗りテンプレートとして個別確認。全binary/全形式の不存在は保証しない |

照合の詳細: `package-reconciliation.json`、`verification.json`、`secret-triage.json`。
配布物の最終inventory/試験結果はビルド後に保存した外部監査証拠で、アーカイブへ後付けしていない。
私有ローカルファイル名を含む `local-inventory.json` は3配布候補すべてから除外した。

## 独立展開試験

同一Windowsホストの新規フォルダーへ実ZIPを展開し、`.venv` / `.tools` / `.cache` / DBの不存在から開始した。
PATHはOS標準ツールのみ、proxyは到達不能、pipはno-index。システムPythonを使用せず、初回CLIは21.27秒で起動した。

8コマンドすべて終了コード0:

1. `cli.bat --help`
2. `cli.bat lists create --name compliance-smoke`
3. `cli.bat lists list --json`
4. `cli.bat lists delete --name compliance-smoke`
5. `cli.bat lists list --json`（別起動で永続状態を確認）
6. `cli.bat doctor`
7. `tools/portable_probe.py`（実Chromium・WebUI/health・内部API疎通）
8. 展開候補内の全回帰試験: **357 passed / 41.22秒**

`clean-candidate-result.json` に出力を保存し、専用試験フォルダーを削除した。
最初の試験はハーネスがCLIの必須`--name`を指定せず停止したため修正し、新しい最終候補で全工程を再実行した。
別OSイメージ、実BOOTH資格情報、購入・DL、実アップグレード、長時間運転は未検証。

## 残るリリース阻害要因

`19-release-readiness.md` と `release-gate.json` のLC-01〜06を維持する。
特に初期コードの生成元/入力、CPython・CRTの条件、Chromeの再配布/素材条件、
FFmpeg7.0.1 Playwright1011の静的libvpx/zlibを含む対応ソース、Node/compiled wheel内包閉包は未完了。
62wheelの主通知を保存したことを、全内包要素のライセンス確認済みへ読み替えない。

通常ビルドはBLOCKED/欠落/入力不一致を拒否する回帰試験で検証した。
`--audit-candidate` はローカル検証用の明示オプションで、配布許可を付与するものではない。

作業開始前の既存変更・旧dist/release・私有データは保全した。今回生成した旧候補と専用一時試験フォルダーのみ整理した。

## 2026-10-02 独立再検証追記 (新規配布物は生成せず)

今回 (2026-10-02) は新規candidateを生成していない。2026-10-01候補
`dist/license-audit-1.0.3-final/` (ZIP/wheel/sdist + DO-NOT-DISTRIBUTE) を正式配布として扱わない。
再検証は既存証拠と軽量コマンドのみ:

- vendor verify: PASS
- release gate (通常build): BLOCKED停止を確認
- pip-audit portable-lock: 0件 (binary閉包は対象外)
- SBOM hash再照合: 62/62一致、5 containers
- secret quick scan: 既知テンプレートのみ
- `git status` の未commit変更 (THIRD_PARTY_LICENSES/NOTICE/SOURCE_OBLIGATIONS/license-audit等) は
  2026-10-01監査作業の未commit成果物であり、今回の検証で削除・commit・pushは行っていない。

RELEASE STATUS: BLOCKED を維持。
