# Changelog

## Unreleased — クローン配布の追加修正（2026-10-03）

- Git候補の全ファイルを配布ゲート・クローン検証に含める。旧ZIP用リストが監査ファイルを除外していた問題を修正。
- CIのwheel/sdist生成・配布物アップロード・タグ公開処理を撤去。旧アーカイブ生成コマンドも生成前に停止する。
- Webの例外応答とジョブ失敗表示のCookie・署名付きURLを伏せ、想定外の例外は本文を返さない。
- ブラウザーホストをソース・SDKのハッシュごとに生成し、実行中EXEの再コンパイルを回避。生成EXEの破損をハッシュで検出して再生成し、起動失敗時の一時プロフィールとログハンドルを回収。
- `cli.bat --db` がPowerShellの`-Debug`別名に消費され、指定DBを開けない不具合を修正。サブコマンド前後と日本語・空白パスを実BATで検証。
- 任意名のCookie取込・DBバックアップ・`.private/`をGit除外。旧履歴のバックアップブランチを非公開bundleの保全確認後に公開参照から分離。
- Microsoftコードの利用条件、SmartScreen・データ通知を文書・Web画面・ブラウザー起動時に追加。
- 原文・対応ソースの整合性検査をCIへ追加。秘密スキャンのディレクトリ一括除外をやめ、ハッシュ・ライセンスID・一次資料内の公開識別子の誤検知だけに限定。

## Unreleased — GitHubクローン配布の準備完了（2026-10-03）

- ブラウザーをPlaywright ChromiumからMicrosoft Edge WebView2 Fixed Version 154.0.4258.53（公式SDK 1.0.4258.31）へ切替。
  Chromium/headless shell/FFmpegは非同梱とし、doctor/error/portable/RC検査/文書をWebView2へ追随。
- `verify_clone.py` の破損復旧検査が旧Chromiumパスを参照して停止するバグを修正。`portable_probe` のcredits取得を`edge://credits`へ修正。
- WebView2 Runtime LicenseのDISTRIBUTABLE CODE条項、CPython/VCランタイム、wheel/Node通知、pip patchの証拠を整理し、
  `license-audit/27-github-clone-distribution.md` と `release-gate.json` を **READY FOR CLONE DISTRIBUTION** へ更新。
- 個人データはGit外のまま、追跡・追加候補・履歴の私用パス0、秘密スキャン未解決0を確認。
- 公開リポジトリの履歴はクリーンな単一rootへ作り直し、旧Chromium/FFmpegを含む旧履歴はローカル保全のみとする。
- 配布用ZIP/sdistは作成しない。GitHubへはリポジトリ自体を公開し、クローンで利用する（公開操作はこの作業では未実施）。

## Unreleased — 配布対象の訂正（2026-10-02）

- Cookieヘッダーの複数値・例外ログの伏字漏れ、Web入力検証エラーのCookie返却を修正。Webの応答キャッシュとRefererによる情報持出しを抑止。
- 通常・offlineセットアップでpipのセキュリティパッチが無効になっていた条件を修正。patch hashをsetup markerに追加し旧環境を再構築。
- 任意名DB/sidecar、Cookie取込、HAR、監査結果・画面をGit対象外に追加。Git追跡・追加候補・履歴の私用パス検査をCIへ追加。
- 原文から7依存のライセンス表記を訂正。pathspec 1.1.1のMPL-2.0対応ソースを追加し、公式hash・31ファイルの一致を確認。

- ユーザー指定により配布対象をフォルダー全体・リポジトリそのものへ訂正。別配布用ソース一式・アーカイブの経路を撤去。
- source-online専用の生成・試験・承認ツールを削除し、限定構成のREADY FOR RELEASE判定を取り下げ。全体監査のBLOCKEDは未解決事項が解消するまで維持。

## 1.0.3 source-online — 取り下げた構成の検証記録（2026-10-02）

- 正式配布をランタイム非同梱のソースZIP/sdistへ変更し、Chrome等の再配布を回避。初回CLI/Web起動から公式取得・ハッシュ照合・ローカルセットアップを自動実行。
- 配布向け取得依存を24wheelへ限定。pip内urllib3を公式2.8.0へ更新し、namespace、原文ライセンス、RECORD、改変記録を保持。旧base pipを除外しensurepipを更新。
- 過大チャンク行の修正回帰、新規OS-only初回起動、オフライン修復後のデータ保持、実Chrome UIを検証。
- 初回Git全28ファイルを実作成記録から再生して一致を確認。Muse Spark/OpenCode、Space Bunny/OpenCode Go、GPT/OpenAIの生成元と出力の権利譲渡条項を記録。
- 当時の候補46ファイル、26公式取得入力とSBOM・通知・checksumを照合。ソースZIP/sdistは現在の配布対象ではない。
- 旧オフライン同梱物・Git履歴・取得後runtime/cacheは承認対象外。実BOOTH資格情報、別OSイメージ、全native runtimeの再配布許諾を完了したとは扱わない。

## Unreleased — ライセンス監査と配布ゲート（2026-10-01）

- 同梱アーカイブ・固定62wheel・Git履歴を独立調査し、`license-audit/` に由来台帳、一次証拠、部分SBOM、最終判定を追加。
- 原文LICENSE/NOTICEを `THIRD_PARTY_LICENSES/` へ収録。certifi/packageurl-pythonの使用版公式sdistと提供案内を追加。
- 本体NOTICE、SQLite差替え要約、wheel/sdist/launcherの通知収録を整備。
- 通常ビルドを未完了・古い監査結果で停止し、ローカル監査候補には `--audit-candidate` を必須化。
- 2026-10-02: 未使用FFmpegを現行配布snapshotから除外。旧chunkをsource/launcher配布へ混入させない収録規則と回帰試験を追加。
- CPython対応full archiveとinstall_only全3,371ファイルの一致を確認し、追加原文19件とensurepip内包依存を追跡。3系統の内包certifi実ソース22ファイルを追加。
- 正式リリース判定はBLOCKED。初期コード由来、CRT/Chromeの再配布条件、ネイティブ/素材の閉包、内包依存へのadvisory適用確認は未完了。

## Unreleased — リポジトリ自体のクローン即起動対応（2026-10-01）

- Python/修正版SQLite/固定62wheel/ブラウザ原本を `vendor/` に同梱。通常Gitの40 MiB以下の分割片で管理し、Git LFS・外部ダウンロード不要へ。
- `start-web.bat` / `cli.bat` が初回準備とDB/browser導入を自動実行。事前のsetup操作を不要にし、初回CLIのstdoutもJSONだけに維持。
- PowerShell開始前のBATでprofile/AppData/temp/cacheをrepo内へ固定し、PowerShell自身の起動時キャッシュが外へ作られる経路を解消。
- 生成物なしのGit候補checkoutで初回Web/CLI、空の外部profile/tempの無変更、327回帰試験を確認。

## Unreleased — ポータブル構成の再整備（2026-10-01）

- OS標準PowerShellとSHA-256固定アーカイブからPythonを構築。初回のシステムPython要件と、BATのグローバルPythonフォールバックを解消。
- 実行・開発・ビルド全62パッケージをハッシュ固定し、wheelとブラウザの復旧用アーカイブをローカル保管。
- 旧venvのhomeを実行前に拒否。移動・不足・破損を起動時に検出し、オフライン修復と失敗時のロールバックを追加。
- 一時ファイル・キャッシュをローカル化し、Web UIは同梱ブラウザで起動。ブラウザ終了時にサーバーも停止。
- 非隔離ビルド、個人用オフライン転送ZIP、OS-only CI、移動・アクセス観測・依存台帳を追加。
- 公式資料で同梱SQLite3.50.4のWAL-reset競合不具合を確認し、公開SHA3-256で検証した公式x64 DLL3.53.4へ置換。ABI・DLLハッシュを検査し、オフライン復元にも対応。
- 実BOOTH、別PC、全ネイティブアクセス、第三者バイナリの公衆再配布条件は未検証範囲として記録。

## 1.0.3 (2026-10-01)

- Cookieをdomain/path/secure/expiry/host-only条件で送信し、接続poolに認証状態を残さない。401/403と通信障害の分類を修正。
- partialダウンロードと破損ZIPを失敗として報告。forceの旧byte混入を防止、中断partとskip時のhash/展開記録を保持。
- ZIP禁止名/大小文字衝突を検証し、CRC失敗時も既存memberを保護するatomic展開へ。
- Webの分類/リスト作成後更新、指定出力先、ジョブ排他、失敗可視化を修正。cleanupをCLIへ統合。
- worker初回生成競合・pipe残留・relative DB差異・応答不明write再送を修正。
- 購入parserの近隣商品誤割当を防ぎ、rel=nextページ取り込みと上限の明示失敗を追加。
- DB全connectionでfuture schemaを拒否、migrationをatomic化。doctorの判定と既存ファイル保護を修正。
- 数値名リストのremoveとunknown itemの副作用を修正、CSV式注入を無害化。
- 配布の任意tree削除/除外子混入を防止し、wheel/sdistのtools不足を修正。CIブラウザ準備・RC空白path・lock生成手順を整備。
- 監査記録と回帰試験を追加。詳細・実行証拠・未検証範囲は `audit/` を参照。
- 最終再調査で新規DLのlibrary全走査を除去。コピー先の保存先復元も台帳basenameで行い、無関係folderのstatを回避。

All notable changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.0.2 (2026-09-29)

Bug-fix release. Two release blockers, both found by running the software
against a local HTTP server rather than by reading the code.

### Fixed

- **Re-running `download` re-fetched every file under a new name.** File names
  were derived from what was already on disk, so the first run wrote
  `data.zip` and the next run saw that name taken and chose `data_2.zip`. The
  ledger row that said `done` was filed under `data.zip`, so the skip check
  missed, the transfer ran again, and every repetition added another copy.
  `download --all` and the Web UI's download button therefore re-downloaded the
  whole library on every press, multiplying bandwidth, disk usage and the DL
  progress table, and contradicting the documented "a re-run does not
  re-fetch completed files". The `downloads` ledger now records the source URL
  of each file (schema v2, forward-only migration) and the link-to-name binding
  is resolved from it. Rows written before this release carry no URL and are
  matched on the file name, so an existing library stays idempotent across the
  upgrade. Uniqueness is still enforced between different links of the same
  item, and a file the user placed in the `downloads` directory by hand is
  still not overwritten.
- **Silent data corruption on resume (second instance).** The resume path
  verified the *total* size of a `206` response but never that the response
  started where it was asked to. A server that answered with a different range
  had its bytes appended to the partial file; the size check caught that
  attempt, but the poisoned `.part` survived it, and the next attempt resumed
  from that offset and completed at exactly the expected length — a file of the
  right size with the wrong content, published as complete and recorded as
  `done` together with its sha256. The returned range start is now verified
  before a single byte is written, and a mismatch discards the partial file
  instead of poisoning the next attempt.
- A database written by a newer build was refused with a raw Python traceback
  and "予期しないエラーが発生しました". It is a routine "please update" case,
  and `cli.py` promises that no traceback ever reaches a user. Added
  `BoothSchemaTooNewError` (`BOOTH_SCHEMA_TOO_NEW`), which reports the found
  and supported schema versions and the remedy, with no traceback.
- `doctor` could not inspect any cookie jar other than the default one: the
  check read a `--cookie-path` that the parser did not define, so a user who
  had authenticated with `--cookie-path` was told "not logged in" and told to
  log in again. `--cookie-path` is now a real option.
- `auth login` reported a failure to open the login page — a DNS, proxy or
  captive-portal problem, the common real-world case — as
  `BOOTH_PREREQUISITE_MISSING` telling the user to run
  `playwright install chromium`. The browser had launched fine, so following
  that advice changed nothing and the identical error came back. Only a failure
  to start Playwright or Chromium is a prerequisite problem now; navigation and
  cookie-read failures are reported as transport failures with Playwright's own
  message, which names the real cause.
- An unreadable standard input (stdin closed or redirected — a service, a
  scheduler, `< NUL`) raised `OSError` inside the daemon thread that waits for
  Enter, printing a stack trace and then reporting a misleading "login could
  not be confirmed". It is now reported as "標準入力が読み取れないため" and the
  browser is still released.
- `POST /download` accepted a request and answered "started" for work that
  cannot run without a session; the failure appeared only in a log the user
  does not read. The session is now checked first and the request is refused
  with 401 and a re-login hint.
- A cap on the number of download links per item kept the first 64 and then
  recorded the item as complete, so a purchase with more files than the cap
  was reported as fully downloaded with a file missing and nothing on screen
  saying so. Exceeding the cap is now `BOOTH_LIMIT_EXCEEDED`, consistent with
  the archive limits.
- The purchase-list row cap now states the consequence and the remedy in the
  log instead of a single line saying the parse stopped.
- A row whose product link cannot be found is keyed by its order id, which is a
  different key from the real product id; that is now logged, because a later
  parse that does find the link would add a second copy of the same purchase.
- The final download failure message now carries the underlying reason instead
  of only the exception type name.
- `tools/build_release.py` referenced `requirements-lock-playwright.txt`, which
  has not existed since Playwright returned to the base requirements. The
  reference is gone; the runtime lock already pins Playwright.

### Added

- `downloads.url` (schema v2) — the source URL each ledger row came from, and
  the durable link-to-file-name binding behind idempotent re-runs.
- Regression tests in `tests/test_regression_102.py` covering every defect
  above, including the byte-exactness of a resume that follows a mis-ranged
  `206` and a three-run re-download that must produce exactly one file.

## 1.0.1 (2026-09-29)

Bug-fix release. A missing Playwright was reported as an authentication
failure that told the user to re-run the command they had just run, and
Playwright had wrongly been moved out of the base requirements.

## 1.0.0 (2026-09-29)

First release qualified for distribution to third parties. This version fixes
several correctness and security defects present in 0.1.0; see the Fixed and
Security sections before upgrading.

### Fixed

- A missing component was reported as an authentication failure. `auth login`
  without Playwright printed ``ERROR BOOTHへのログインが必要です。`python cli.py
  auth login` で再ログインしてください。 Playwrightが未導入です。`` -- telling
  the user to re-run the command that had just failed, while burying the real
  cause. Added `BoothPrerequisiteError` (code `BOOTH_PREREQUISITE_MISSING`) and
  used it at all four sites where a dependency was missing: Playwright, httpx
  and beautifulsoup4. The legitimate re-login hint is unchanged for real
  authentication failures.
- Playwright had been moved out of the base requirements as an optional extra.
  That was wrong: a real-browser login is the only authentication path this
  application has, so the documented "minimal install" produced an application
  that could not authenticate at all. It is back in `requirements.txt`, and
  `doctor` now checks the Chromium binary separately from the package and
  reports a missing browser as fatal.

### Added

- `cli.py doctor` — one command that checks dependencies, database tables and
  integrity, cookie state, and library writability plus free space. `--json`
  supported.
- `cli.py rpc` — a persistent worker speaking newline-delimited JSON on
  stdin/stdout. The Web UI uses it so a request no longer costs a fresh
  interpreter start. Long-running downloads deliberately still use a one-shot
  subprocess so they cannot stall the worker.
- `download --force` — re-fetch files already recorded as `done`.
- `auth login --timeout` — bound the wait for the login confirmation.
- `POST /downloads/cleanup` in the Web UI — remove `.part` files left behind by
  an interrupted run.
- `lists delete` is now reachable from the Web UI.
- Forward-only schema migrations driven by `PRAGMA user_version`; `init_db`
  upgrades an older database in place and refuses a newer one explicitly.
- `PRAGMA integrity_check` and `foreign_key_check` surfaced through `doctor`.
- `pyproject.toml` with packaging metadata, a `booth-reader` console script, and
  tool configuration. Requirements split into runtime / dev / all, plus
  hash-pinned `requirements-lock.txt` and `requirements-lock-playwright.txt`.
- `.gitattributes` so `.bat` launchers always check out with CRLF and text files
  with LF, making a clean clone byte-reproducible.
- Comprehensive CI: lint, format check, type check, byte-compile, tests across
  Python 3.10–3.13, package build and clean-environment install, dependency
  audit, secret scan, Bandit, and tag-driven release notes.
- Test suite expanded from 24 to 186 tests.

### Changed

- **Download resume reworked.** The resume offset is recomputed from the file on
  disk inside the retry loop, and the append-or-truncate decision is taken from
  the response rather than the request. Bytes are written to `<name>.part` and
  published with an atomic replace only after the size is verified against
  `Content-Range`/`Content-Length`.
- A single failing file no longer abandons the remaining files of a
  multi-file purchase; failures are collected and reported per item.
- Re-running `download` skips files already recorded as `done`, making repeated
  execution cheap and idempotent.
- `parse_library_html` resolves the product id from the row's own container
  first, falling back to a pre-indexed positional lookup. This both fixes
  mis-association of an order with a neighbouring item and removes the
  quadratic scan.
- Per-thread pooled `httpx.Client` replaces a new client per request.
- Idempotent GETs retry with exponential backoff and full jitter; 4xx other than
  408/425/429 are not retried; `Retry-After` is honoured.
- Cookies are filtered by domain per request instead of being sent to every host.
- SQLite runs in WAL mode with `synchronous=NORMAL` and a 15 s busy timeout.
- Invalid arguments consistently exit 2 (usage error). Previously some paths
  returned 1 for what is clearly a usage mistake.
- `auth login` verifies the session against the library before writing cookies.
- The Web layer enforces same-origin on state-changing requests and validates
  the `Host` header.
- `piped` stdout is forced to UTF-8 while consoles keep their native codepage,
  removing a class of garbled-output reports.
- Web UI markup is accessible (`<label for>`, `<caption>`, `scope`, `aria-live`)
  and honours `prefers-color-scheme`.

### Fixed

- **Silent data corruption on resume.** A pre-existing partial file plus a
  dropped connection caused the retry to re-request a stale byte range and
  append it again. A 300,000-byte file was published as 431,072 bytes with
  84,464 wrong bytes, recorded as `done`, and reported as a success. Covered by
  a regression test that asserts byte-for-byte equality.
- **Path traversal through `item_id`.** `item_dir()` did not sanitise the item
  id, so an id such as `../../../Windows/System32/drivers/etc` wrote outside the
  library root. Ids are now validated and the resolved path re-checked.
- **Zip bomb.** Extraction had no size or entry limits and read each member
  fully into memory; a 200 KB archive expanded to 200 MB. Caps on entry count,
  total size, per-entry size and compression ratio are now enforced *before* any
  byte is written, and members are streamed.
- **JWT tokens leaked through the redaction filter.**
  `Authorization: Bearer <jwt>` only had the literal word `Bearer` removed
  because the pattern stopped at the first space, so the token itself was
  written to the log. The same filter also destroyed legitimate lines:
  `cookies count=42` was rendered as `[REDACTED]`.
- **Possible lockout from the cookie ACL.** `icacls /inheritance:r` ran before
  the account was granted access, so a failed grant left the user unable to read
  their own cookie file. The grant now runs first, and the result is verified
  and rolled back if the file became unreadable.
- `auth login` saved a cookie jar even when the user had not actually logged in;
  the session is now confirmed first.
- `subprocess.run(text=True)` on `icacls` raised `UnicodeDecodeError` inside a
  reader thread when decoding Japanese tool output as UTF-8.
- Beautiful Soup attributes are coerced to `str`; a missing `href` caused a
  `TypeError` instead of skipping the row.
- `save_cookies` raised `TypeError` from `len()` on a malformed argument instead
  of reporting a clean error.
- The RPC worker executed requests with an unfiltered `--db`, allowing a request
  to redirect the worker at a different database.
- `POST /download` ran an extra full `purchases` query purely to report a count.

### Performance

Measured on Windows 11 / Python 3.12.13 with 500 items in the database.

| Operation | Before | After | Change |
|---|---|---|---|
| `parse_library_html`, 2000 rows | 98.2 s | 0.23 s | ~430x |
| `parse_library_html`, 8000 rows | not viable | 1.37 s | now linear |
| Web data call, one-shot subprocess | 185 ms | — | — |
| Web data call, persistent worker | — | 3.7 ms | ~50x |
| Full page data load (4 calls) | 726 ms | 13.4 ms | ~54x |
| `GET /` end to end | — | 16.8 ms | — |

Parser cost is now flat at roughly 0.12–0.18 ms per row instead of growing with
page size.

### Security

- Fixed the token leak in log redaction, and added coverage for JSON-style
  (`{"token": "..."}`), `X-API-Key`, `Basic`, PEM private key blocks and bare
  JWTs, while preserving useful log lines.
- Web layer: `TrustedHostMiddleware` blocks DNS rebinding, and a same-origin
  check blocks a hostile page from triggering a download through a cross-site
  request.
- Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`LPT9`) are
  escaped in generated paths, which previously produced unusable names.
- Zip entries are rejected for absolute paths, drive letters, UNC prefixes,
  parent references, control characters, reserved names and trailing dots.
- Query strings are stripped before a URL reaches a log, so signed download URLs
  do not leak.
- `icacls` and `whoami` are resolved to absolute paths before execution.
- `requirements.txt` no longer installs pytest, shrinking the default install
  and its dependency surface. All dependencies are permissively licensed.

### Removed

- Nothing user-visible. Internal duplicate code paths were consolidated; the
  dead single-item branch in `download_many` and the duplicated
  `log_level`/`log_format` handling were folded into one place.

## 0.1.0 (2026-09-29)

Initial development snapshot. Not recommended for distribution: it contained the
resume corruption, path traversal and log token-leak defects listed above.

### Added

- `cli.py --version` (single source of truth: `core/version.py`)
- `--output-dir` on the `web` command
- Initial CI (`.github/workflows/ci.yml`)
- `LICENSE` (MIT), `THIRD_PARTY_NOTICES.md`, `CHANGELOG.md`
- 16 hardening tests (zip slip, boundaries, negative input, XSS, JSON purity,
  smoke roundtrip)

### Changed

- Errors unified under `BoothError`
- `LIMIT` bound and clamped
- Zip Slip detection based on `relative_to`
- Atomic writes for the cookie jar and `meta.json`
- `busy_timeout` on SQLite
- JS `esc()` for dynamic Web rendering
