# ポータブル構成

Windows x64でクローンし、`start.bat` を起動します。準備・復旧は同梱物から自動実行され、追加ランタイム・ダウンロード・管理者権限は不要です。操作は [README](README.md#インストール起動) を参照。

## 同梱物

| 場所 | 内容 |
|---|---|
| `vendor/windows-x64/` | CPython 3.12.13、SQLite 3.53.4、固定62wheel、WebView2 Runtime 154.0.4258.53・SDK |
| `vendor/windows-x64/manifest.json` | 原本・分割片のサイズ、SHA-256、lock照合 |
| `portable-manifest.json` | OS/CPU・配布元・版・原本ハッシュ |
| `requirements-portable-lock.txt` | パッケージの固定版・ハッシュ |
| `cli.py`, `core/`, `web/`, `tools/`, `start.bat` | 本体・起動・修復 |

バイナリは40MiB以下の `.chunk` で通常Gitに格納します。Git LFS・サブモジュール・別リポジトリ依存はなく、`vendor/` を省くsparse checkoutは非対応です。Chrome/headless shell/FFmpegは非同梱です。

## 保存先（Git対象外）

| 場所 | 内容 |
|---|---|
| `.tools/python/`, `.venv/`, `.playwright-browsers/` | Python・修正版SQLite・依存・ブラウザー |
| `.cache/downloads`, `vendor`, `wheels` | 復旧用原本・wheel |
| `.cache/tmp/`, `.cache/home/AppData/{Local,Roaming}` | 一時ファイル・子プロセスのプロフィール |
| `.cache/powershell/`, `.cache/{pytest*,ruff,mypy,pip,uv,xdg}` | 起動・開発キャッシュ |
| `app.db`, `data/cookies.json`, `BOOTH-Reader-Library/` | DB・Cookie・購入ファイル |
| `.private/` | 任意名の私用出力・バックアップ |

BATでPowerShell起動前にHOME/USERPROFILE/APPDATA/LOCALAPPDATA/TEMP/TMP・キャッシュ先を固定します。変更は子プロセス内だけで、永続PATH・環境変数・サービス・タスク・レジストリ登録は変更しません。ログはstderr、`--json` のstdoutはJSONのみです。

既定の保存先はリポジトリ内です。`--db` / `--cookie-path` / `--output-dir` / `--csv` の外部指定には従います。

## 移動・修復・更新

- 停止後にフォルダー全体を移動できます。旧venvは実行前に検出・再構築します。
- 生成環境がなくても `vendor/` からオフライン復元します。欠損・ハッシュ不一致は停止し、未固定版やPATH上のツールで代用しません。
- Web起動・`auth login` でブラウザーを起動検査し、破損時は同梱原本から一度だけ復旧します。通常のCLI照会では追加検査を省きます。
- `--repair` / `--recreate` / `--update` は起動中・venv使用中なら変更前に停止します。DB・購入物は保持します。
- 更新はGitでソース・manifest・同梱物を取得し、固定環境へ同期します。依存変更時だけ検証済みローカル原本から `tools/vendor_payload.py build` で再生成します。
- バックアップ・復元・旧版への復帰は [README](README.md#バックアップと復旧)。環境修復ではデータを復元できません。
- 停止後にフォルダーを削除すれば専用環境・既定データも削除されます。Windows自身の履歴は対象外です。

## 通信・利用条件

起動・準備・修復はオフライン可。BOOTH/pixiv認証、同期、購入ファイル・画像取得、WebView2のSmartScreen等は外部通信を伴います。

Microsoftコードの条件・データ通知は [THIRD_PARTY_TERMS.md](THIRD_PARTY_TERMS.md)、出所は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。WebView2はDISTRIBUTABLE CODE条項に基づきアプリの一部として同梱し、Runtime原文をsnapshotと `THIRD_PARTY_LICENSES/browser/` に保持します。配布判定は [追加監査](license-audit/28-clone-distribution-followup.md) に記録しています。

## 検証・対象範囲

```powershell
& .\.venv\Scripts\python.exe tools/vendor_payload.py verify
& .\.venv\Scripts\python.exe tools/check_portable.py
& .\.venv\Scripts\python.exe tools/verify_clone.py
```

`verify_clone` は生成環境なしの全Git候補を独立ツリーで検証し、元index・HEADを保持します。開発ツールなしPATH・無効Python/pip設定・到達不能proxy・空profile/tempで、初回Web/CLI、日本語・空白パスへの移動、DB/CSV/合成Cookie/UI、ブラウザー復旧、終了・再起動を確認します。

証拠は `audit/clone-verification.json` / `audit/junit-clone.xml`、ログは `.cache/clone-evidence/`。過去結果は [追加確認](audit/18-clone-distribution-followup.md)、現行条件は [リリース範囲](audit/19-release-scope.md)。CIも同梱環境を使います。実BOOTH・Windows 10・別PC・全nativeアクセスは未検証です。

対象はWindows x64・書込み可能なローカルディスク。Mac/Linux・ARM64/x86・UNC/NASの直接実行は非対応です。SQLite WALはnetwork filesystem非対応のため、NASはバックアップ用に使います。
