# 両OSクローン配布のライセンス判定（2026-10-06）

対象はBOOTH-Reader 1.1.0のWindows x64・Apple Silicon Mac構成です。配布方式は、Git候補のソース・vendor・原文通知・対応ソースを含むクローンです。利用中のDB・Cookie・購入物・プロフィール・検証用キャッシュは含めません。

## 阻害要因の解消

前回候補のGoogle Chromeは再配布候補から除外しました。Macは本体MITの`tools/webkit_host.swift`をビルドした小さなホストとOS標準WebKitを使います。OSのWebKit・AppKit・Swiftライブラリのコピーは配布しません。バイナリのソースhash・生成物hash・リンク先は`macos-distribution-evidence.json`に保存し、ソースと候補の一致を検査します。

Appleの一次資料では、[WKWebsiteDataStore.nonPersistent](https://developer.apple.com/documentation/webkit/wkwebsitedatastore/nonpersistent())はメモリー内だけにWebサイトデータを保存する方式と説明されています。追加ブラウザーの利用・再配布条件に依存せず、利用者側のコンパイルや追加インストールを要求しません。署名変更・Gatekeeper無効化は行いません。

## コンポーネント別の根拠

| 対象 | 条件・対応 | 証拠 |
|---|---|---|
| Windows同梱物 | 既存のPSF/MIT/Apache/BSD/MPL通知、WebView2のDISTRIBUTABLE CODE条件を継続 | `27-github-clone-distribution.md`、`28-clone-distribution-followup.md` |
| Mac CPython 3.12.15 | 公式releaseの公開SHA-256を照合。通常版1,653ファイルを対応full版と照合し、複合ライブラリ原文19件を保持 | `macos-distribution-evidence.json`、`THIRD_PARTY_LICENSES/macos/CPython-3.12.15` |
| Mac固定62wheel | 公式PyPI hashとlockを照合。Windowsで原文確認済みの同じ版を使用し、Mac原文も保持 | `macos-publisher-inputs.json`、`macos-notice-inventory.json`、`requirements-macos-arm64-lock.txt` |
| MacのMach-O実行形式 | 同じ版のsdist、既存の完全Cargo lockソース閉包へ結び付ける | `macos-distribution-evidence.json`、`native-source-evidence.json` |
| MPL certifi/pathspec | 同版公式sdist、Mac原本の内包certifi実ソースを同じ配布先に保持 | `SOURCE_OBLIGATIONS/README.md` |
| 自作WebKitホスト | 本体MIT。ソース・ビルド手順・生成物の対応を記録 | `tools/webkit_host.swift`、`tools/build_webkit_host.py` |

Mac CPythonの複合ライブラリは、full版metadataに記録された0BSD/Apache/BSD/MIT/OpenSSL/TCL/X11/Zlib/bzip2の原文条件を保持します。OSの`libSystem`等はApple提供物として使用するだけで再配布しません。pipのurllib3修正はMIT原文・変更記録を保持し、元のMPLファイルは実ソースを提供します。

高度なUI試験のため保守者・CIが個人利用として取得するChromeは、無配布の`.cache/ui-test-driver`に限定します。配布payloadの検査は生成環境を対象に混ぜず、Git候補とvendorアーカイブから列挙します。

## 判定と制限

この文書は記録した原文と同梱構成に基づく技術的な配布条件整理で、法律専門家の保証ではありません。正式な候補固定は`release-gate.json`の全入力hashと`check_distribution.py`で照合します。入力や同梱物が変わった場合は古い合格を流用しません。

製品の検証範囲・最低OS実機・実サービス・長時間運転等は品質記録に別途記載し、未実施を配布条件の確認結果へ混ぜません。公開・pushはこのローカル判定とは別の操作です。
