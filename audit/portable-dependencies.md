# ポータブル依存台帳

Windows x64 / CPython 3.12.13。全62パッケージの推移閉包を実測。
用途・保存場所・移行方式・検証・出所・実ライセンスのSHA-256は `portable-dependencies.json` に記録。
全パッケージは `.cache/wheels` から `.venv/Lib/site-packages` に導入する。
Compiler/SDKは不要。ネイティブ部分は固定Windows x64 wheelから導入する。

| 名前 | バージョン | 用途 | 有効な直接依存先 | ライセンス情報 | 通知ファイル数 |
|---|---|---|---|---|---|
| annotated-doc | 0.0.5 | 実行(推移) | なし | MIT | 1 |
| annotated-types | 0.8.0 | 実行(推移) | なし | MIT | 1 |
| anyio | 4.15.1 | 実行(推移) | idna, typing-extensions | MIT | 1 |
| ast-serialize | 0.11.2 | 開発・ビルド | なし | MIT | 2 |
| beautifulsoup4 | 4.15.0 | 実行(直接) | soupsieve, typing-extensions | MIT License | 2 |
| boolean-py | 5.0 | 開発・ビルド | なし | BSD-2-Clause | 3 |
| build | 1.6.1 | 開発・ビルド | packaging, pyproject-hooks, colorama | MIT | 1 |
| cachecontrol | 0.14.4 | 開発・ビルド | requests, msgpack | Apache-2.0 | 1 |
| certifi | 2026.7.22 | 実行(推移) | なし | MPL-2.0 | 1 |
| charset-normalizer | 3.5.2 | 開発・ビルド | なし | MIT | 1 |
| click | 8.5.0 | 実行(推移) | なし | BSD-3-Clause | 1 |
| colorama | 0.4.6 | 実行(推移) | なし | metadata未記載(実通知参照) | 1 |
| cyclonedx-python-lib | 11.12.0 | 開発・ビルド | license-expression, packageurl-python, py-serializable, sortedcontainers, typing-extensions | Apache-2.0 | 7 |
| defusedxml | 0.7.1 | 開発・ビルド | なし | PSFL | 1 |
| fastapi | 0.141.1 | 実行(直接) | starlette, pydantic, typing-extensions, typing-inspection, annotated-doc | MIT | 1 |
| filelock | 4.0.7 | 開発・ビルド | なし | MIT | 1 |
| greenlet | 3.5.6 | 実行(推移) | なし | MIT AND PSF-2.0 | 2 |
| h11 | 0.16.0 | 実行(推移) | なし | MIT | 1 |
| httpcore | 1.0.9 | 実行(推移) | certifi, h11 | BSD-3-Clause | 1 |
| httpx | 0.28.1 | 実行(直接) | anyio, certifi, httpcore, idna | BSD-3-Clause | 1 |
| idna | 3.20 | 実行(推移) | なし | BSD-3-Clause | 1 |
| iniconfig | 2.3.0 | 開発・ビルド | なし | MIT | 1 |
| librt | 0.16.0 | 開発・ビルド | なし | MIT | 1 |
| license-expression | 30.4.4 | 開発・ビルド | boolean-py | Apache-2.0 | 18 |
| markdown-it-py | 4.2.0 | 開発・ビルド | mdurl | metadata未記載(実通知参照) | 2 |
| mdurl | 0.1.2 | 開発・ビルド | なし | metadata未記載(実通知参照) | 1 |
| msgpack | 1.2.3 | 開発・ビルド | なし | Apache-2.0 | 1 |
| mypy | 2.3.1 | 開発・ビルド | typing-extensions, mypy-extensions, pathspec, librt, ast-serialize | MIT | 3 |
| mypy-extensions | 1.1.0 | 開発・ビルド | なし | MIT | 1 |
| opentelemetry-api | 1.45.0 | 開発・ビルド | typing-extensions | Apache-2.0 | 1 |
| packageurl-python | 0.17.6 | 開発・ビルド | なし | MIT | 1 |
| packaging | 26.3 | 開発・ビルド | なし | Apache-2.0 OR BSD-2-Clause | 5 |
| pathspec | 1.1.1 | 開発・ビルド | なし | metadata未記載(実通知参照) | 1 |
| pip | 26.2.1 | 開発・ビルド | なし | MIT | 46 |
| pip-api | 0.0.35 | 開発・ビルド | pip | Apache License | 3 |
| pip-audit | 2.10.1 | 開発・ビルド | cachecontrol, cyclonedx-python-lib, packaging, pip-api, pip-requirements-parser, requests, rich, tomli, tomli-w, platformdirs | metadata未記載(実通知参照) | 1 |
| pip-requirements-parser | 32.0.1 | 開発・ビルド | packaging, pyparsing | MIT | 1 |
| platformdirs | 4.12.2 | 開発・ビルド | なし | MIT | 1 |
| playwright | 1.63.0 | 実行(直接) | pyee, greenlet | Apache-2.0 | 8 |
| pluggy | 1.6.0 | 開発・ビルド | なし | MIT | 1 |
| py-serializable | 2.1.0 | 開発・ビルド | defusedxml | Apache-2.0 | 1 |
| pydantic | 2.13.5 | 実行(直接) | annotated-types, pydantic-core, typing-extensions, typing-inspection | MIT | 1 |
| pydantic-core | 2.46.5 | 実行(推移) | typing-extensions | MIT | 1 |
| pyee | 13.0.1 | 実行(推移) | typing-extensions | MIT | 1 |
| pygments | 2.21.0 | 開発・ビルド | なし | BSD-2-Clause | 2 |
| pyparsing | 3.3.3 | 開発・ビルド | なし | MIT | 1 |
| pyproject-hooks | 1.3.3 | 開発・ビルド | なし | MIT | 1 |
| pytest | 9.1.1 | 開発・ビルド | colorama, iniconfig, packaging, pluggy, pygments | MIT | 1 |
| requests | 2.34.2 | 開発・ビルド | charset-normalizer, idna, urllib3, certifi | Apache-2.0 | 2 |
| rich | 15.0.0 | 開発・ビルド | markdown-it-py, pygments | MIT | 1 |
| ruff | 0.16.9 | 開発・ビルド | なし | MIT | 1 |
| setuptools | 84.0.0 | 開発・ビルド | なし | MIT | 19 |
| sortedcontainers | 2.4.0 | 開発・ビルド | なし | Apache 2.0 | 1 |
| soupsieve | 2.10 | 実行(推移) | なし | MIT | 1 |
| starlette | 1.7.0 | 実行(推移) | anyio, typing-extensions | BSD-3-Clause | 1 |
| tomli | 2.4.1 | 開発・ビルド | なし | MIT | 1 |
| tomli-w | 1.2.0 | 開発・ビルド | なし | metadata未記載(実通知参照) | 1 |
| typing-extensions | 4.16.0 | 実行(推移) | なし | PSF-2.0 | 1 |
| typing-inspection | 0.4.4 | 実行(推移) | typing-extensions | MIT | 1 |
| urllib3 | 2.8.0 | 開発・ビルド | なし | MIT | 1 |
| uvicorn | 0.54.0 | 実行(直接) | click, h11 | BSD-3-Clause | 1 |
| wheel | 0.48.0 | 開発・ビルド | packaging | MIT | 1 |

## 実行・ビルド以外の依存

- Runtime: `.tools/python`。Python、OpenSSL、SQLite、libffi、VC runtime等の実DLLをJSONで記録。
- Browser: `.playwright-browsers`。Microsoft WebView2 Fixed Version 154.0.4258.53と公式SDK 1.0.4258.31 (同梱payloadから展開)。
- Playwright driver: wheel内 `playwright/driver/node.exe`(Node24.21.0)とJS。グローバルNode/npmは不要。
- OS: Windows x64、PowerShell5.1、tar、cmd、whoami、icacls、標準DLL、GPUドライバー。
- 外部サービス: BOOTH/pixiv認証/販売者CDN。購入・ログイン・DLの機能仕様上必要。
- 初回取得のみ: GitHub/PyPI/Playwright CDN。取得済みアーカイブからオフライン再構築可能。
- データ/アセット: ローカルSQLite、Cookie、購入ファイル、動的HTML。AIモデル/外部DB/追加フォントなし。
- Git: 任意の開発メタデータ診断だけ。セットアップ・本体・ポータブル監査はGit不要。
- 古いdist/release/トップレベルキャッシュは未使用。既存物を保護し、自動削除しない。
- `.venv`の絶対パスは生成物。起動前に旧homeを拒否し、ローカルwheelから再生成。
- CPythonのPDB/未使用Tcl開発設定にあるビルド元パスはデバッグ情報であり、アプリの実行参照ではない。
