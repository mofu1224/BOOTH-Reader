# Mac・Windows対応

`1.1.0`では、Apple Silicon MacとWindows x64で同じCLI・Web UI・ライブラリを使用します。初回準備と修復は同梱物だけで完結し、生成データの既定保存先はフォルダー内です。

## 起動と環境

| 項目 | Windows x64 | Apple Silicon Mac |
|---|---|---|
| 起動入口 | `start.bat` | `start.command`、`bash ./start.sh` |
| Python | CPython 3.12.13 | CPython 3.12.15 |
| SQLite | 3.53.4 DLL | 同梱3.53.1（WAL修正を含む） |
| 認証ブラウザー | WebView2 154.0.4258.53 | 自作MITホスト＋OS標準WebKit（非永続セッション） |
| Python実行ファイル | `.venv/Scripts/python.exe` | `.venv/bin/python3` |
| manifest | `portable-manifest.json` | `portable/macos-arm64.json` |
| lock | `requirements-portable-lock.txt` | `requirements-macos-arm64-lock.txt` |

Macの最低要件はmacOS 14です。Intel Mac、Windows ARM64、Linuxは対応対象に含めません。OSの証明書・GUIフレームワーク・標準ツールは使用します。

## データの移動

全インスタンスを停止し、READMEのバックアップ手順に従ってフォルダーを移動します。新しいOS・配置先に合うランタイムとvenvを自動構築し、分類・並び順・購入原本を保持します。明示指定した外部保存先は別途移動してください。

DB v5では、ライブラリ内の新しい取得パスを`library:/商品フォルダー/downloads/ファイル名`として記録します。旧Windows/POSIX絶対パスの記録も読み取り、指定されたライブラリ内で商品フォルダーを回復します。同じ商品IDの候補が複数ある場合は推測で選びません。旧版はv5を拒否するため、戻す場合は更新前のバックアップが必要です。

ダウンロード・未完了削除はライブラリ単位で排他制御します。起動中の環境には共有ロックを取り、準備・修復には排他ロックを取ります。ZIPでは大文字小文字とUnicode正規化が同じ展開先になる名前を拒否します。

## 開発検証

```bash
bash ./start.sh setup
bash tools/prepare_ui_test_driver.sh
.venv/bin/python3 -m pytest -q
.venv/bin/python3 -m ruff check .
.venv/bin/python3 -m ruff format --check .
.venv/bin/python3 -m mypy
.venv/bin/python3 -m pip check
.venv/bin/python3 tools/vendor_payload.py verify --target all
.venv/bin/python3 tools/check_portable.py
.venv/bin/python3 tools/verify_clone_macos.py
```

クローン検証は生成環境なしの独立コピーを作り、オフライン準備、CLI、実ブラウザー、移動後の再構築、署名不一致からの修復、起動中の修復拒否を確認します。コピーは成否にかかわらず削除し、結果だけを`.cache/macos-clone-result.json`に保存します。

## 同梱物の更新

`tools/prepare_macos.py`は保守者が公式Python・PyPIのハッシュを照合してMac用入力を取得するためのツールです。通常起動では通信しません。

Macの認証ホストは`tools/webkit_host.swift`から保守者が`tools/build_webkit_host.py`でビルドします。利用者にはビルド済みファイルを同梱し、Xcode・Swiftコンパイラーを要求しません。ソースhash・生成物hash・macOS 14のdeployment target・OSライブラリだけへのリンクを保存します。WebKit・AppKit・SwiftのOSライブラリ自体は再配布しません。セッションは`WKWebsiteDataStore.nonPersistent()`でメモリー内に置きます。

高度なUI自動試験に使う署名付きChromeは、開発者が公式サイトから個人利用として`.cache/ui-test-driver`へ準備する検証専用ツールです。`vendor/`、Git候補、通常起動・修復には含めません。検証には追加通信が必要ですが、利用者の初回起動には不要です。

## 配布条件と確認範囲

配布物からChromeを除外し、MacのPythonと固定wheelを公式入力・原文通知・既存の同版対応ソースへ結び付けています。内包certifiの実ソースも同梱します。[両OSクローン配布の判定](license-audit/31-cross-platform-clone-distribution.md)と、候補全入力のhashを持つ`license-audit/release-gate.json`を配布条件の入口とします。個人データを含む利用中フォルダーは配布しません。

検証はWindows 11 x64とApple Silicon Mac（macOS 27）で実施しています。Windows 10・macOS 14の実機、別PC、長時間運転、実BOOTHの対話的ログイン入力は検証範囲外です。実BOOTHの同期・購入ファイル取得・展開はWindowsの既存セッションで確認済みです。

現行1.1.0の実機結果と確認範囲は[実装・検証記録](audit/21-portable-distribution-1.1.0.md)を参照してください。
