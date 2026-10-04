# リポジトリフォルダ自体を使うポータブル版

配布はGitリポジトリのクローンで行い、別の配布用アーカイブは作成しません。Git追跡内容が配布物で、個人データは含まれません。
ライセンス判定は **READY FOR CLONE DISTRIBUTION** です。範囲・根拠・残る制限は
[license-audit/28-clone-distribution-followup.md](license-audit/28-clone-distribution-followup.md) に記録しています。

**Windows x64でクローン後、`start.bat` を起動すれば使えます。事前セットアップは不要で、必要かどうかは起動時に自動判定します。追加ダウンロード、グローバルPython/Nodeも不要です。**

```bat
start.bat                        rem 通常のWeb UI。初回準備・復旧・ブラウザー起動も自動
start.bat 8080                   rem ポート指定
start.bat --no-open              rem ブラウザーを自動で開かない
start.bat --repair               rem 生成環境を同梱物から修復
start.bat --check                rem 準備済みかを確認するだけ
start.bat doctor                 rem CLI。初回でもstdoutはJSONだけ
start.bat cli lists list --json  rem CLIを明示する場合
```

PowerShellでは `& .\start.bat ...` を使用します。初回は同梱物をフォルダ内に検証・展開します。検証PCではWeb約24秒、CLI約19秒。2回目以降は既存環境をそのまま使います。入口はこの1つだけで、`.tools` / `.venv` / `.playwright-browsers` / DB の不足や移動後の不整合は起動時に検出して自動復旧します。すでに起動中のときは二重起動せず既存の画面を開き、指定ポートが別アプリに使用中のときは空きポートへ自動で切り替えます。起動失敗時はウィンドウを閉じずにエラーを表示します。`start.bat --check` は準備状態だけを表示し、`start.bat /?` と `start.bat version` も受け付けます。エラーと対処は日本語で案内し、同梱物 (vendor/) の破損が疑われる場合は git clone による復元を案内します。

## クローンに入るもの

| 場所 | 内容 |
|---|---|
| `vendor/windows-x64/` | CPython3.12.13、SQLite3.53.4、固定62wheel、Microsoft Edge WebView2 Fixed Version 154.0.4258.53と公式SDKの同梱payload。Chrome for Testing・headless shell・FFmpegは非同梱 |
| `vendor/windows-x64/manifest.json` | 同梱物・分割片のサイズとSHA-256、lockの一致情報 |
| `portable-manifest.json` | 対象OS/CPU、配布元・版・原本ハッシュ |
| `requirements-portable-lock.txt` | 全パッケージの版とハッシュ |
| `cli.py`, `core/`, `web/`, `tools/`, `*.bat` | 本体と自動起動・修復 |

同梱バイナリは1ファイル40 MiB以下の `.chunk` に分割し、通常のGitで管理します。Git LFS、サブモジュール、別リポジトリへの依存はありません。`vendor/` を省略したsparse checkoutは起動対象ではありません。

Microsoftコードの利用・再配布条件とSmartScreenのデータ通知は [THIRD_PARTY_TERMS.md](THIRD_PARTY_TERMS.md) にあります。Web UIのリンクから、同じ条件とMicrosoft原文を確認できます。

## 生成先と保存先

| 場所 | 内容 |
|---|---|
| `.tools/python/` | ローカルRuntimeと修正版SQLite DLL |
| `.venv/` | 固定依存・開発ツール |
| `.playwright-browsers/` | ローカルブラウザ |
| `.cache/downloads`, `.cache/vendor`, `.cache/wheels` | 同梱物から再構築するローカル原本・wheel |
| `.cache/tmp/` | pip/Node/ブラウザの一時ファイル・一時プロフィール |
| `.cache/home/AppData/Local`, `Roaming` | 子プロセスのユーザー領域 |
| `.cache/powershell/` | PowerShellのmodule解析キャッシュ |
| `.cache/pytest*`, `ruff`, `mypy`, `pip`, `uv`, `xdg` | 開発・検証キャッシュ |
| `app.db`, `data/cookies.json`, `BOOTH-Reader-Library/` | 利用者のDB・Cookie・購入ファイル |
| `.private/` | 任意名のCookieインポート、私用出力、バックアップの推奨保存先（Git対象外） |

`start.bat` 段階でHOME/USERPROFILE/APPDATA/LOCALAPPDATA/TEMP/TMPとPowerShellキャッシュ先を固定してからPowerShellを起動します。スクリプトが始まる前にOSのプロフィール側へPowerShellキャッシュができる経路も修正しました。

すべて子プロセス内の設定です。親シェル、永続PATH、永続環境変数、サービス、タスク、レジストリ登録は変更しません。stdoutのJSONへ準備ログを混ぜず、診断はstderrへ出します。

本体ログはstderrです。通常の既定保存はすべてリポジトリ内です。`--db` / `--cookie-path` / `--output-dir` / `--csv` で利用者が明示指定した外部ファイルは、その指示に従います。

## 移動・修復・削除

- アプリを停止してフォルダ全体をコピー・移動できます。旧venvのhomeを実行前に拒否し、同梱物から再生成します。
- `--repair` / `--recreate` / `--update` は、起動中のインスタンスを検出すると変更前に終了を案内して停止します。固定環境 (.venv) が使用中で更新できない場合も、終了方法とデータ保護を日本語で案内します。
- `.tools` / `.venv` / `.cache` / `.playwright-browsers` がなくても、`vendor/` があれば通信なしで自動復元します。
- 破損した同梱片はハッシュ不一致として停止します。別の配布物やPATH上のツールへフォールバックしません。
- Web起動とCLIの `auth login` はブラウザを事前起動検査し、既存の実行ファイルが壊れている場合も検証済み同梱原本から一度だけ復旧します。通常のCLI照会ではこの追加検査を行いません。
- ターミナルに表示される `http://127.0.0.1:8000/` を普段のブラウザで開きます。使用中はターミナルを開いたままにし、Ctrl+Cで終了します。`--no-open` も互換用に受け付けます。
- アプリを停止してリポジトリフォルダを削除すると、アプリ専用環境と既定の設定・データ・キャッシュも削除できます。Windows自身の実行履歴まで消す処理は行いません。

## 取得・更新

通常の起動・修復は無通信です。BOOTH/pixivログイン、購入情報更新、新しい購入ファイルの取得だけは本来の外部通信です。

新しいソース・manifest・同梱物をGitから取得すると、次の起動で固定環境へ同期します。依存を意図的に更新する開発時は、検証済みローカル原本から `tools/vendor_payload.py build` で同梱物を更新します。未固定の最新版を通常起動で導入しません。

## 検証

```powershell
& .\.venv\Scripts\python.exe tools/vendor_payload.py verify
& .\.venv\Scripts\python.exe tools/check_portable.py
& .\.venv\Scripts\python.exe tools/verify_clone.py
```

Gitへ格納可能なソース・同梱物を独立したGitツリーへ書き出し、生成済みRuntime/venv/cache/browserなしのチェックアウトで検証します。未コミット修正がある場合は新規cloneへ候補ツリーだけをcheckoutし、元のindex・HEADは変更しません。開発ツールなしPATH、無効なPython/pip設定、到達不能proxy、リポジトリ外を模した空profile/tempで、初回Web・CLI、構築済みフォルダの日本語/空白パスへの実移動、DB/CSV/合成Cookie/画面操作、ブラウザ破損復旧、終了・再起動を確認します。

検証対象はGit追跡ファイルと除外されていない追加候補のすべてです。旧ZIP用の収録リストでは絞り込みません。現行証拠は `audit/clone-verification.json` / `audit/junit-clone.xml`、報告は [audit/18-clone-distribution-followup.md](audit/18-clone-distribution-followup.md)、ログは `.cache/clone-evidence/`。実機の別PC・Windows10・全native syscall監査は未実施です。CIも同梱Runtime・固定wheel・ローカルキャッシュを使い、グローバル開発環境を導入しません。GitHub runnerでの今回のworkflow実行は未確認です。

対象はWindows x64の書き込み可能なローカルディスクです。Mac/Linux、ARM64/x86、UNC/NASの直接実行は対象外です。SQLite WALはnetwork filesystem非対応のため、NASはコピー・バックアップ用途にします。

第三者原本の通知を同梱物内に保持し、出所を `THIRD_PARTY_NOTICES.md` に記録しています。WebView2はMicrosoftのRuntime License（DISTRIBUTABLE CODE条項）に基づきアプリの一部として同梱し、原文をvendor snapshot内と `THIRD_PARTY_LICENSES/browser/` に保持します。公開リポジトリの履歴はこの構成だけをクローンへ配布します。
