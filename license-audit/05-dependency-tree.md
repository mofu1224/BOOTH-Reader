# 固定依存の完全展開

監査日: 2026-10-02。判定: **BLOCKED**。

62wheelを原本から解析し全62SHA-256を使用版PyPI JSONと再照合。
環境markerが有効なRequires-Distを版制約と照合。非有効marker/extra/optional条件もpackages.jsonに保存。
実行/開発/ビルドを区別してもvendorに入る全62個は配布監査対象。
トップレベルPython閉包は列挙済み。Node/npm、Rust静的依存、CPython内蔵pipの閉包は未完了。

- annotated-doc@0.0.5 → なし
- annotated-types@0.8.0 → なし
- anyio@4.15.1 → idna, typing-extensions
- ast-serialize@0.11.2 → なし
- beautifulsoup4@4.15.0 → soupsieve, typing-extensions
- boolean-py@5.0 → なし
- build@1.6.1 → packaging, pyproject-hooks, colorama
- cachecontrol@0.14.4 → requests, msgpack
- certifi@2026.7.22 → なし
- charset-normalizer@3.5.2 → なし
- click@8.5.0 → なし
- colorama@0.4.6 → なし
- cyclonedx-python-lib@11.12.0 → license-expression, packageurl-python, py-serializable, sortedcontainers, typing-extensions
- defusedxml@0.7.1 → なし
- fastapi@0.141.1 → starlette, pydantic, typing-extensions, typing-inspection, annotated-doc
- filelock@4.0.7 → なし
- greenlet@3.5.6 → なし
- h11@0.16.0 → なし
- httpcore@1.0.9 → certifi, h11
- httpx@0.28.1 → anyio, certifi, httpcore, idna
- idna@3.20 → なし
- iniconfig@2.3.0 → なし
- librt@0.16.0 → なし
- license-expression@30.4.4 → boolean-py
- markdown-it-py@4.2.0 → mdurl
- mdurl@0.1.2 → なし
- msgpack@1.2.3 → なし
- mypy@2.3.1 → typing-extensions, mypy-extensions, pathspec, librt, ast-serialize
- mypy-extensions@1.1.0 → なし
- opentelemetry-api@1.45.0 → typing-extensions
- packageurl-python@0.17.6 → なし
- packaging@26.3 → なし
- pathspec@1.1.1 → なし
- pip@26.2.1 → なし
- pip-api@0.0.35 → pip
- pip-audit@2.10.1 → cachecontrol, cyclonedx-python-lib, packaging, pip-api, pip-requirements-parser, requests, rich, tomli, tomli-w, platformdirs
- pip-requirements-parser@32.0.1 → packaging, pyparsing
- platformdirs@4.12.2 → なし
- playwright@1.63.0 → pyee, greenlet
- pluggy@1.6.0 → なし
- py-serializable@2.1.0 → defusedxml
- pydantic@2.13.5 → annotated-types, pydantic-core, typing-extensions, typing-inspection
- pydantic-core@2.46.5 → typing-extensions
- pyee@13.0.1 → typing-extensions
- pygments@2.21.0 → なし
- pyparsing@3.3.3 → なし
- pyproject-hooks@1.3.3 → なし
- pytest@9.1.1 → colorama, iniconfig, packaging, pluggy, pygments
- requests@2.34.2 → charset-normalizer, idna, urllib3, certifi
- rich@15.0.0 → markdown-it-py, pygments
- ruff@0.16.9 → なし
- setuptools@84.0.0 → なし
- sortedcontainers@2.4.0 → なし
- soupsieve@2.10 → なし
- starlette@1.7.0 → anyio, typing-extensions
- tomli@2.4.1 → なし
- tomli-w@1.2.0 → なし
- typing-extensions@4.16.0 → なし
- typing-inspection@0.4.4 → typing-extensions
- urllib3@2.8.0 → なし
- uvicorn@0.54.0 → click, h11
- wheel@0.48.0 → packaging
