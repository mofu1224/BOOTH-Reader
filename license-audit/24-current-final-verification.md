# 現行配布候補の最終検証（2026-10-02）

## 最終判定

**RELEASE STATUS: BLOCKED**。
現行候補 `dist/license-audit-20261002-final/` の動作とアーカイブ整合性は検証した。
コード由来、再配布条件、内包ライセンス・脆弱性の閉包は未完了であり、正式配布を許可する判定ではない。

## 成果物とチェックサム

| 成果物 | サイズ（bytes） | SHA-256 |
|---|---:|---|
| BOOTH-Reader-1.0.3-windows-x64.zip | 447693300 | a0e133567a58631f44f66f3ea501cb39d872df8209241edf6ee0f6d947dc8fb2 |
| booth_reader-1.0.3-py3-none-any.whl | 1706927 | 8250807ef75ffedd91cf623ae155d30b37115f34252630f4d66f6018126d9e25 |
| booth_reader-1.0.3.tar.gz | 447372869 | 38e0cab3d15878cb23807b6e4a6a05482a58538b47cfab96b39ea38793d62eec |

同じ出力先に `SHA256SUMS.txt` と `DO-NOT-DISTRIBUTE.txt` を置いた。
候補を生成する明示オプション `--audit-candidate` は正式リリース承認を与えない。
通常buildが `license clearance BLOCKED` で停止することも実測した。

## 完成物の照合

| 項目 | 結果 |
|---|---|
| Checksum / ZIP CRC / 安全なpath | 合格。3アーカイブの計1,332エントリーを検査 |
| launcher入力との一致 | 518収録入力の現在のbyte/SHA-256とAUDITED-INPUTSを照合 |
| LICENSE / NOTICE / 第三者原文 | 各アーカイブ内の235ファイルが原本とbyte一致 |
| 対応ソース | launcher/sdistの案内・certifi/packageurl sdist・内包certifiソースarchiveの4ファイルが原本とbyte一致 |
| vendorと部分SBOM | 固定62wheel、5容器のhashと依存制約を照合。active chunk全件が一致し、旧chunk混入なし |
| FFmpegの除外 | launcher/sdistの再構成browser payloadにFFmpegなし。保持する全browserファイルは除外前とbyte一致 |
| 原本内部の列挙 | ensurepip wheel内部も含め8,855ファイル。archive-files.jsonを参照 |
| 配布物の秘密情報候補 | 13レコードは個別評価済みworktreeのダミー/赤塗りテンプレートとbyte一致。未評価候補0 |

証拠: `final-package-result.json`、`distribution-inventory.json`、`package-reconciliation.json`。
wheelにはbrowser/vendor payloadを同梱しないため、wheelのvendor/FFmpeg照合欄は適用外。
原文通知の収録を、全コンポーネントの再配布権・条件の充足へ読み替えない。

## 新規展開・オフライン試験

同一Windowsホストの新規専用フォルダーへ実launcher ZIPを展開した。
開始時に `.venv` / `.tools` / `.cache` / DBがないことを確認し、PATHをOSツールだけに制限、
proxyを到達不能なlocalhostへ設定、pipをno-indexとした。

8コマンドすべて終了コード0:

1. `cli.bat --help` — 同梱物だけで初回環境を作成。
2. `cli.bat lists create --name compliance-smoke`
3. `cli.bat lists list --json`
4. `cli.bat lists delete --name compliance-smoke`
5. `cli.bat lists list --json` — 再起動後の状態を確認。
6. `cli.bat doctor`
7. `tools/portable_probe.py` — 実headed Chromeでリスト作成、商品追加、リスト削除、未分類復元、health/APIと実DLL経路を確認。
8. 展開候補内の全回帰試験 — **386 passed / 51.87秒**。

FFmpegディレクトリーが新規展開後も存在しないことを確認した。
Starlette TestClientの非推奨警告1件は残る。試験の省略やタイムアウト延長で合格にしていない。
最初の候補は旧UI用probeが非表示ダイアログへ入力して停止したため、現行の操作経路へ修正し、
候補を再生成して全工程を再実行した。結果は `clean-candidate-result.json`。
専用展開フォルダーは削除済み。

開発環境でも386試験合格、Ruff対象検査合格、Mypy18ソース合格。
`git diff --check` に空白エラーなし。Windowsの改行正規化通知は既存作業も含めて発生している。
以前のformatter検査では監査ツール等に整形差分があり、formatter合格とは報告しない。

## セキュリティとリリース阻害事項

- 固定62wheelのpip-auditは既知advisory検出0件。
- pipの内包版宣言を追加検査し、重複排除後のparent・package単位advisory候補はensurepip系14、初期pip系13、固定pip系6。
  同じ問題の別parentへの出現を、全体の固有脆弱性件数として合算しない。
- GitHub原advisory15件を保存した。実vendor patch、非同梱のPackageIndex/FileList、msgpack実装、
  urllib3の通信条件等を確認するまで、該当性・修正完了を断定しない。`25-embedded-advisory-review.md` とLC-07を参照。
- 秘密情報検査は5種ルールによるworktree/reachable Git text blob/完成アーカイブの限定検査。
  binary history・私有データ・全資格情報形式の不存在を証明したものではない。
- 部分SBOMに内包metadataと3系統のvendor宣言を追加したが、Node/Chrome/native wheel/全素材の閉包はPARTIAL。
- LC-04（FFmpeg）は現行完成物からの除外を再検証して解決。旧Git履歴・旧配布物の再配布は依然対象外。
- LC-01/02/03/05/06/07は残る。詳細と外部で必要な権利確認は `19-release-readiness.md` と `release-gate.json`。

別OSイメージ、実BOOTHログイン/購入/DL、実upgrade、全binary advisory閉包は未検証。
購入物を除外して製品機能を検証したことと、実BOOTHアカウントでの動作確認を混同しない。

この文書と完成物のinventory/reconciliation/clean-test結果は、ビルド後の外部監査証拠として保存する。
自己参照hashを避けるためアーカイブへ後付けしない。commit/push/公開は実施していない。
