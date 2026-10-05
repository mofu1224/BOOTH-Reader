# Terms for bundled Microsoft software

The application's source code is licensed under the [MIT License](LICENSE). The conditions below apply only to bundled Microsoft code, not to Python itself or this application's source code.

## Acceptance and incorporated originals

Use or redistribution of bundled Microsoft code requires acceptance of the applicable terms, including the originals below. Starting to use or redistributing the Microsoft code indicates acceptance. If you do not accept, you may not use or redistribute that code.

- WebView2 Fixed Version Runtime: [original Microsoft Software License Terms](THIRD_PARTY_LICENSES/browser/15bc46c641bc-WEBVIEW2-RUNTIME-LICENSE.txt), incorporated here in full for Microsoft code.
- WebView2 SDK: [original SDK license](THIRD_PARTY_LICENSES/browser/0af8f1b80751-webview2-sdk_LICENSE.txt), applicable to SDK DLLs and Loader.
- Microsoft Distributable Code in Windows CPython: “Additional Conditions for this Windows binary build” in the [bundled CPython license](THIRD_PARTY_LICENSES/CPython-3.12.13/886a0ead2d89-python_LICENSE.txt), together with the protections below.

## Protections for Microsoft code

- Microsoft code is licensed, not sold. Microsoft and its suppliers retain their rights.
- Do not remove, alter or obscure copyright, trademark, patent or other rights notices.
- Do not bypass technical limitations, reverse engineer, decompile or disassemble Microsoft code, except to the extent permitted by applicable law or the licenses of bundled open-source components.
- Do not use trademarks or representations suggesting that Microsoft supplies or endorses this application.
- Do not redistribute Windows code for unlicensed platforms or include Microsoft code in malicious, deceptive or unlawful programs.
- Redistribute Microsoft code only as part of this application's functionality. Do not provide it as a standalone Microsoft runtime or apply this application's MIT License to Microsoft code.
- Preserve these terms, originals and rights notices when redistributing. Require downstream distributors and external users to accept protections at least equivalent to these Microsoft protections.
- Microsoft code is provided “as is.” To the maximum extent permitted by law, Microsoft and its suppliers disclaim express and implied warranties and liability for indirect, special, incidental, consequential and similar damages. Their liability for direct damages is limited to US $5.00. Rights and liabilities that applicable law does not allow to be excluded remain in effect.

The originals' DISTRIBUTABLE CODE provisions, data, export, regional, dispute resolution, warranty and liability terms also apply to WebView2 use and redistribution. This summary does not amend the originals.

## Microsoft Defender SmartScreen and data notices

Bundled WebView2 includes Microsoft Defender SmartScreen, enabled by default. This application does not disable it. WebView2 may collect user information and send it to Microsoft.

- Microsoft Privacy Statement: https://aka.ms/privacy
- Microsoft Edge Privacy Whitepaper (SmartScreen): https://learn.microsoft.com/en-us/microsoft-edge/privacy-whitepaper#smartscreen

Excluding cookies, purchase history and purchased files from Git is separate from WebView2's external communication. Isolating local storage does not guarantee that communication with Microsoft stops.

## Bundled open-source components

Third-party open-source components in Microsoft code retain their individual licenses; the restrictions above do not revoke those licenses' rights. WebView2 notices and source availability information are in the Runtime original and bundled credits.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for other dependency notices and [SOURCE_OBLIGATIONS/README.md](SOURCE_OBLIGATIONS/README.md) for corresponding sources.
