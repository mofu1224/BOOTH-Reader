# 同梱Microsoftソフトウェアの利用・再配布条件

本体のソースコードには [MIT License](LICENSE) が適用されます。以下は、同梱するMicrosoftコードに限って適用する条件です。Python本体や、このアプリのソースコードの権利を制限するものではありません。

## 同意と適用する原文

同梱Microsoftコードを利用または再配布するには、以下の原文を含む条件に同意する必要があります。同梱Microsoftコードの利用開始または再配布をもって、その条件への同意を表明するものとします。同意しない場合は同梱Microsoftコードを利用・再配布できません。

- WebView2 Fixed Version Runtime: [Microsoft Software License Termsの原文](THIRD_PARTY_LICENSES/browser/15bc46c641bc-WEBVIEW2-RUNTIME-LICENSE.txt)。この原文を本条件に組み込み、Microsoftコードにはその全条項を適用します。
- WebView2 SDK: [SDKライセンス原文](THIRD_PARTY_LICENSES/browser/0af8f1b80751-webview2-sdk_LICENSE.txt)。SDKのDLL・Loaderにはこの原文を適用します。
- Windows版CPythonのMicrosoft Distributable Code: [CPython同梱ライセンス原文](THIRD_PARTY_LICENSES/CPython-3.12.13/886a0ead2d89-python_LICENSE.txt) の「Additional Conditions for this Windows binary build」。Microsoftコードに関する以下の保護条件も適用します。

## Microsoftコードの保護条件

- Microsoftコードは使用許諾されたもので、所有権を移転するものではありません。Microsoftとその供給者の権利を保持します。
- Microsoftコードの著作権・商標・特許・その他の権利通知を削除、変更、隠蔽してはいけません。
- 適用法または同梱オープンソース部分のライセンスが認める範囲を除き、Microsoftコードの技術的制限の回避、リバースエンジニアリング、逆コンパイル、逆アセンブルを禁止します。
- Microsoftから提供または承認されたアプリであると誤認させる商標・表示を用いてはいけません。
- Windows用コードを、許諾されていないプラットフォーム向けに再配布してはいけません。Microsoftコードを悪意のある、欺瞞的な、違法なプログラムに含めてはいけません。
- Microsoftコードは、このアプリの機能の一部としてのみ再配布できます。単体のMicrosoftランタイムとして提供したり、Microsoftコードに本体のMIT Licenseを適用したりしてはいけません。
- 再配布する場合は、この条件と原文・権利通知を保持し、下流の配布者と外部利用者にも同等以上のMicrosoft保護条件への同意を要求してください。
- Microsoftコードは「現状有姿」で提供されます。適用法が認める最大限の範囲で、Microsoftとその供給者は明示・黙示の保証を行わず、間接・特別・付随・結果的損害等に責任を負いません。直接損害に関するMicrosoftとその供給者の責任はUS $5.00を上限とします。適用法上排除できない権利・責任は維持します。

WebView2の利用・再配布には、原文のDISTRIBUTABLE CODE条項、データ、輸出、地域別条件、紛争解決、保証・責任制限なども適用されます。この要約が原文を変更するものではありません。

## Microsoft Defender SmartScreenとデータ通知

同梱WebView2にはMicrosoft Defender SmartScreenが含まれます。SmartScreenは既定で有効です。このアプリはSmartScreenを無効化しません。WebView2は利用者の情報を収集し、Microsoftへ送信することがあります。

- Microsoftのプライバシーステートメント: https://aka.ms/privacy
- Microsoft Edge Privacy Whitepaper（SmartScreen）: https://learn.microsoft.com/en-us/microsoft-edge/privacy-whitepaper#smartscreen

Cookie・購入履歴・購入ファイルをGitから除外することと、WebView2自身の外部通信は別の事項です。ローカル保存先の隔離は、Microsoftへの通信を停止する保証ではありません。

## 同梱オープンソース部分

Microsoftコードに含まれる第三者オープンソース部分は、その個別ライセンスが適用されます。上記の制限によって個別ライセンスの権利を取り消すものではありません。WebView2の第三者通知・ソース提供案内はRuntime原文と同梱creditsにあります。

その他の同梱依存の通知は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)、対応ソースは [SOURCE_OBLIGATIONS/README.md](SOURCE_OBLIGATIONS/README.md) を参照してください。
