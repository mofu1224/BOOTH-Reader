# 対応ソースと提供条件

## certifi 2026.7.22

`certifi-2026.7.22.tar.gz` は同じ版のPyPI公式sdistを取得し、公開SHA-256と照合した原本です。
取得URL・ハッシュは `license-audit/packages.json` のcertifi行にあります。
MPL-2.0対象ファイルを変更せず配布する場合のSource Code Formを同梱します。
このフォルダーをバイナリ配布と同じ場所で入手できる状態に保ち、MPL原文と権利通知を保持してください。
Python初期アーカイブ内のpipが同梱する別版certifiは、このsdistで充足したと扱いません。

## 内包certifiの実ソース

`vendored-certifi-source.tar.gz` は配布アーカイブ内のcertifiファイルをbyte変更せず収録しています。
対象はensurepipのpip25.0.1内certifi2024.8.30、初期pip26.0.1内certifi2026.1.4、
固定wheelのpip26.2.1内certifi2026.6.17です。pipによるimport書換えも保持しています。
全22ファイルの元パス・SHA-256は `license-audit/vendored-certifi-source.json` を参照してください。
原文ライセンスは `THIRD_PARTY_LICENSES/` と元アーカイブ内に保持します。

## packageurl-python 0.17.6

`packageurl_python-0.17.6.tar.gz` は公式sdistです。wheelにない版固有MIT原文をここから取得しました。
MITによるソース提供義務ではなく、取得版と通知の対応を証明するため保存しています。

## pathspec 1.1.1

`pathspec-1.1.1.tar.gz` はPyPI公式の同版sdistです。公開SHA-256と固定wheelのhashを照合し、wheel内の全31 Pythonファイルがこのソースとbyte一致することを確認しました。
取得元・原通知・ファイルhashは `license-audit/pathspec-source.json` にあります。MPL-2.0原文と通知を維持し、実行形式と同じ配布先からこのSource Code Formを入手できる状態にします。

## 同梱物のソース・通知

FFmpeg revision 1011は未使用の動画記録機能用で、公開リポジトリのbrowser snapshotから除外しています。
旧chunkと旧Git履歴は公開リポジトリへ含めないため、その再配布は発生しません。
CPython/PBSの対応原文と全3,371ファイルの一致は `license-audit/pbs-correspondence.json`、wheelの通知は
`THIRD_PARTY_LICENSES/` と `license-audit/license-evidence.json` に保持しています。
WebView2の再配布条件と原文は `license-audit/27-github-clone-distribution.md` を参照してください。
このフォルダーは、同梱するMPL対象（certifi、pathspec）のSource Code Formと、通知対応を証明する同版sdistを提供します。
判定の入口は `license-audit/release-gate.json` と `license-audit/31-cross-platform-clone-distribution.md` です。

## Mac対応の追加（1.1.0）

`macos-vendored-certifi-source.tar.gz`はMac用CPython原本・ensurepip・固定pip wheelに含まれるcertifiの実ソースをbyte変更せず収録します。元ファイルとhashは`license-audit/macos-distribution-evidence.json`の`vendored_certifi_source`に記録します。

MacのネイティブwheelはWindowsと同じ版です。同じ版のsdistとRust lock依存の提供は`native/`・`rust-lock/`で行い、Macの実Mach-Oファイルから対応先へ結び付けた表も同じ証拠ファイルへ保存しています。Python 3.12.15の公式full/通常アーカイブ1,653ファイル一致と追加通知19件を確認しています。

MacのWebKitホストは本体MITの`tools/webkit_host.swift`とビルド手順を提供します。リンクするWebKit・AppKit・SwiftはmacOS標準ライブラリであり、このリポジトリに再配布しません。Google Chrome・Firefox・Playwright用WebKit・FFmpegのブラウザー本体を配布しません。
