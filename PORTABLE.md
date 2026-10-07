# ポータブル構成

Windows x64は`start.bat`、Apple Silicon Macは`start.command`または`bash ./start.sh`で起動します。準備・復旧は同梱物から自動実行され、追加ランタイム・ダウンロード・管理者権限は不要です。Macの追加対応と検証範囲は[CROSS_PLATFORM.md](CROSS_PLATFORM.md)、操作は[README](README.md#インストール起動)を参照してください。

## 同梱物

| 場所 | 内容 |
|---|---|
| `vendor/windows-x64/` | CPython 3.12.13、SQLite 3.53.4、固定62wheel、WebView2 Runtime 154.0.4258.53・SDK |
| `vendor/macos-arm64/` | CPython 3.12.15（SQLite 3.53.1）、固定62wheel、自作MIT WebKitホスト |
| `vendor/windows-x64/manifest.json` | 原本・分割片のサイズ、SHA-256、lock照合 |
| `portable-manifest.json` | OS/CPU・配布元・版・原本ハッシュ |
| `portable/macos-arm64.json` | Mac用のOS/CPU・配布元・版・署名要件 |
| `requirements-portable-lock.txt` | パッケージの固定版・ハッシュ |
| `requirements-macos-arm64-lock.txt` | Mac用wheelの固定版・ハッシュ |
| `cli.py`, `core/`, `web/`, `tools/`, `start.bat` | 本体・起動・修復 |

バイナリは40MiB以下の`.chunk`で通常Gitに格納します。Git LFS・サブモジュール・別リポジトリ依存はなく、`vendor/`を省くsparse checkoutは非対応です。WindowsのブラウザーはWebView2、Macは自作ホストとOS標準WebKitです。Google Chrome・Chrome for Testing・headless shell・FFmpegは同梱しません。

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

Macの入口もPython起動前にHOME/TMPDIR・キャッシュ先をフォルダー内へ固定します。Python・Node・ブラウザーは同梱物を直接指定し、Homebrew・システムPython・Xcodeには依存しません。通常実行でディスクイメージのマウントや署名の変更は行いません。

既定の保存先はリポジトリ内です。`--db` / `--cookie-path` / `--output-dir` / `--csv` の外部指定には従います。

## 移動・修復・更新

- 停止後にフォルダー全体を移動できます。旧venvは実行前に検出・再構築します。
- OSを変えて移動した場合も、OS固有の生成環境を再構築します。DBと購入物は共通で、旧Windows/POSIXの取得パスは移動先ライブラリ内で解決します。
- 生成環境がなくても `vendor/` からオフライン復元します。欠損・ハッシュ不一致は停止し、未固定版やPATH上のツールで代用しません。
- Web起動・`auth login` でブラウザーを起動検査し、破損時は同梱原本から一度だけ復旧します。通常のCLI照会では追加検査を省きます。
- `--repair` / `--recreate` / `--update` は起動中・venv使用中なら変更前に停止します。DB・購入物は保持します。
- 更新はGitでソース・manifest・同梱物を取得し、固定環境へ同期します。依存変更時だけ検証済みローカル原本から `tools/vendor_payload.py build` で再生成します。
- バックアップ・復元・旧版への復帰は [README](README.md#バックアップと復旧)。環境修復ではデータを復元できません。
- 停止後にフォルダーを削除すれば専用環境・既定データも削除されます。Windows自身の履歴は対象外です。

## 通信・利用条件

起動・準備・修復はオフライン可。BOOTH/pixiv認証、同期、購入ファイル・画像取得、WebView2のSmartScreen等は外部通信を伴います。

Microsoftコードの条件・データ通知は [THIRD_PARTY_TERMS.md](THIRD_PARTY_TERMS.md)、出所は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。WebView2はDISTRIBUTABLE CODE条項に基づきアプリの一部として同梱し、Runtime原文をsnapshotと `THIRD_PARTY_LICENSES/browser/` に保持します。現行の両OS配布判定は [配布条件](license-audit/31-cross-platform-clone-distribution.md) に記録しています。

## 検証・対象範囲

```powershell
& .\.venv\Scripts\python.exe tools/vendor_payload.py verify
& .\.venv\Scripts\python.exe tools/check_portable.py
& .\.venv\Scripts\python.exe tools/verify_clone.py
```

`verify_clone` は生成環境なしの全Git候補を独立ツリーで検証し、元index・HEADを保持します。開発ツールなしPATH・無効Python/pip設定・到達不能proxy・空profile/tempで、初回Web/CLI、日本語・空白パスへの移動、DB/CSV/合成Cookie/UI、ブラウザー復旧、終了・再起動を確認します。

検証ツールの既定出力は `audit/clone-verification.json` / `audit/junit-clone.xml`、ログは `.cache/clone-evidence/`。現行1.1.0の結果は [両OS検証記録](audit/21-portable-distribution-1.1.0.md)、配布条件は [両OS配布判定](license-audit/31-cross-platform-clone-distribution.md) を参照してください。CIも同梱環境を使います。実BOOTHはWindowsの既存本人セッションで同期・購入ZIP取得・展開を確認済みです。検証はWindows 11とmacOS 27で実施しており、Windows 10・macOS 14の実機・別PC・長時間運転・全面nativeアクセスは検証範囲外です。

対象はWindows x64とApple Silicon Mac・書込み可能なローカルディスクです。Intel Mac・Windows ARM64/x86・Linux・UNC/NASの直接実行は非対応です。SQLite WALはnetwork filesystem非対応のため、NASはバックアップ用に使います。
