# 検証ログ (Verification Log)

## GitHub CI 全ジョブPASS（2026-10-03）

- `88afa49` のCI（run 37135441351）で3ジョブすべてPASS: 品質/クローン配布 2m49s、依存/秘密スキャン 1m3s、コールドクローン/再配置 6m22s。未検証だったGitHub runner実行を解消。
- 初回公開後のCIで見つかった不具合（ベンダーロックのCRLF、英語ロケールでの日本語tarパス、破損WebView2の停止、再配置監査の文字コード/キャッシュ変数）はすべて修正済み。

## 再配置検証のハング対策（2026-10-03）

- 3回目のCIは `cold-web-launch` 以降すべてPASSし、`relocated-web-restart` が10分でタイムアウト（ローカルは13.5秒）。タイムアウト時の出力が残らないため、`launcher_probe.py` に360秒のウォッチドッグ（`managed-web.log` 末尾を出して終了）を追加し、`verify_clone.py` の `run()` はタイムアウト時に部分出力を保存して失敗理由を残すよう変更。
- 4回目のCIのウォッチドッグで原因を特定: 破損させた `msedgewebview2.exe` の健全性チェックが長時間停止していた（`[portable] pinned environment already ready` の後）。`core/browser.py` の起動待機を90秒の期限に変更し、`manage_portable.py` の健全性チェックを150秒で打ち切り、修復前にアプリのWebView2ホストを解放するようにした。
- 続くCIで `relocated-web-restart` はPASS。最後の `relocated-audit` が日本語パスを英語コードページのstdoutへ出力できず `UnicodeEncodeError` になったため、該当の直接起動へ `-X utf8` を追加。
- `relocated-audit` は日本語出力をクリアした後、ワークフロー由来の `PIP_CACHE_DIR`（元リポジトリ）が再配置先の外を指すためFAIL。`verify_clone.py` の再配置環境でキャッシュ変数を再配置先へ上書き。
- 検証: ローカル全回帰410 passed、verify_clone PASS。ゲート更新。

## 日本語パスとWindows内蔵tarの制限の解消（2026-10-03）

- 2回目のCIで `cold-web-launch` の失敗内容を取得: 初回展開の `tar.exe` が日本語パスを開けず `[ERROR] Python archive extraction failed.`。Windows内蔵bsdtarは、システムコードページで表現できない文字を含むパスを扱えない既知の制限だった。
- `bootstrap.ps1` のPython展開を、.NET `GZipStream` とustar解析によるUnicode安全な `Expand-TarGz` へ置換し、`tar.exe` 依存を撤去。日本語以外のシステムコードページでも動作する。
- 検証: 抽出結果はPython tarfileと全2,336ファイルのSHA-256が一致（日本語パス、ローカル5.7秒）。`verify_clone.py` のテストディレクトリは日本語名のまま（回避策を撤去）で、ローカル全回帰410 passed・verify_clone PASS。ゲート更新。
- CI run `37139908849`（`8c198ff`）で3ジョブPASS。英語ロケールのランナー＋日本語クローンパスで解消を確認。

## GitHub初回CIで発見した不具合の修正（2026-10-03）

- 初回CI: security jobはPASS。verify jobは `vendor_payload.py verify`、portable jobは `cold-web-launch` でFAILした。
- 原因1: `requirements-portable-lock.txt` の作業ツリーがCRLFで、`vendor/windows-x64/manifest.json` の `lock_sha256` がCRLFバイト基準だった。LFでチェックアウトするクローン/CIでは不一致になるため、`eol=lf` の作業ツリーテキスト62ファイルをLFへ正規化し、manifestのロックハッシュをLF基準へ更新。
- 原因2: `cold-web-launch` は1.35秒で即失敗したが、失敗内容がCIログに出なかった。`verify_clone.py` が失敗チェックのログ末尾を出力・記録し、`launcher_probe.py` が `managed-web.log` 末尾とサーバー終了コードをstderrへ出すよう改善。
- 検証: ローカル全回帰 **410 passed**、`check_portable` 18/18、`vendor_payload verify` PASS、`check_license_evidence` PASS。ゲートの入力ハッシュを更新。

## 履歴リセットとWindows長パス対応（2026-10-03）

- ユーザー指示によりローカルのGit履歴を単一ルートコミットへ再初期化（旧履歴のローカルオブジェクトは削除、旧bundleは `%TEMP%\opencode` に保全）。
- 再初期化後、`verify_clone.py` のコミット済みツリーcloneがWindowsの260文字制限（MAX_PATH）で失敗することを再現。cloneへ `core.longpaths=true` を追加して修正。
- 検証: `check_distribution` 2,530 PASS、`verify_clone` 89チェックPASS（410 passed・secret scan・元index不変・後始末含む）。ゲートの入力ハッシュを更新。

## CIのNode 24対応と秘密スキャン固定（2026-10-03）

- Node 20がGitHubランナーから撤去されたため、`.github/workflows/ci.yml` のActionをNode 24版へ更新: `actions/checkout` v7.0.1、`actions/upload-artifact` v7.0.1（すべてcommit SHA固定）。
- 非対応の `gitleaks-action@v2` を撤去し、公式gitleaks 8.30.1のWindowsバイナリをSHA-256照合してから `gitleaks git --log-opts=--all` で全履歴を走査する手順へ変更。SARIFは `.cache/gitleaks/` へ出力してartifact保存。`GIT_LOG_ARGS` はv2/v3とも未対応のため削除。
- `release-gate.json` の `.github/workflows/ci.yml` ハッシュを `tools.repository_files.input_hashes` で更新（他2,528入力は不変）。
- 検証: `check_distribution` 2,530 PASS、`check_license_evidence` 2,137参照/1,506原文 PASS、`check_portable` 18/18、`vendor_payload verify` PASS、`verify_clone` 89チェックPASS（410 passed・secret scan・元index不変・後始末含む）。CIと同一のgitleaksコマンドを実機実行しexit 0・SARIF 0件を確認。
- 変更は未コミット。GitHub runner実行は引き続き未検証。

## クローン配布の追加修正・最終検証（2026-10-03）

- 開始時397 passed。Web機密値返却3経路、ブラウザー準備2経路、BATのDB引数消失2条件を再現して修正。
- 最終の隔離Git候補チェックアウトで **410 passed**。初回Web/CLI、再配置、旧配置読み取り拒否、DB/CSV/合成Cookie/UI、ブラウザー破損復旧、終了・再起動を確認。
- 全2,529入力（ゲート自身除外）が元候補とチェックアウト後で一致。上流原文・対応ソース・一次証拠の2,137参照とハッシュ名付き原文1,506ファイルも一致。
- Ruff/format/Mypy19ソース/compileall/pip check、portable18/18、vendor、PyPI固定62wheel、offline lock、CI相当のCLI7コマンド: PASS。pip-audit既知脆弱性0。
- gitleaks: 公開履歴とクリーン候補の未解決0。原文ディレクトリの一括除外を撤去し、ハッシュ・ライセンスID・Google公式資料の公開識別子だけを精査して許可。
- 実DB・CookieのSHA-256不変、元index不変、試験の外部profile/temp書き込み0。旧履歴は既存の非公開bundleの完全性を確認して、公開候補のブランチ参照から分離。
- CI・旧配布ツール・説明書をGitクローン配布へ統一。配布用アーカイブ・commit・push・公開は未実施。
- 詳細: [audit/18-clone-distribution-followup.md](audit/18-clone-distribution-followup.md)、[license-audit/28-clone-distribution-followup.md](license-audit/28-clone-distribution-followup.md)。実BOOTH通し疎通、別PC/Windows10、GitHub runnerは未確認。

## GitHubクローン配布の準備（2026-10-03）

- WebView2移行後のベースライン: **396 passed**、ruff/format/mypy/pip check、`check_portable` 18/18、`vendor_payload verify`、Git私用パス0。
- WebView2移行の残存バグを修正: `verify_clone.py` の旧Chromiumパス参照、`rc_test.gate_browser` の `playwright install`、doctor/エラー案内、
  `portable_probe` の `chrome://credits`、依存台帳のブラウザー表記。
- ライセンス: WebView2 Fixed Versionの配布条件（DISTRIBUTABLE CODE）とMicrosoft公式配布ガイド、VCランタイム再配布条件を証拠として保持。
  判定を `license-audit/27-github-clone-distribution.md` に記録し、`release-gate.json` を現行ツリーのハッシュでREADYへ更新。
- 詳細は `audit/17-final-distribution-readiness.md`。公開・push・GitHub CI実行はこの作業では未実施。

## リポジトリのクローン即起動・保存先封じ込め（2026-10-01）

- ユーザー指定をリポジトリフォルダ主体へ修正。Git管理するvendor同梱片から自動準備し、setup事前操作・ネットワーク取得・Git LFSを不要にした。
- Gitの独立index/treeを経由した候補checkoutに、生成済みRuntime/venv/cache/browserをコピーせず検証。元のGit indexは変更なし。
- 空profile/temp、無効なPython/pip設定、開発ツールなしPATH、到達不能proxyから、初回Web23.8秒、初回CLI19.4秒で起動。初回JSONも純粋なJSON。
- 初回調査でPowerShell開始前のprofileキャッシュ生成を検出し、BATでPS開始前にprofile/cache/tempを固定して再検証。指定した外部profile/tempのファイル・フォルダ生成0。
- 全 **327 passed**。Gitのreadonly object削除は所有した試験copyだけでreadonlyを解除して完了。証拠 `audit/clone-verification.json` / `junit-clone.xml`、ログ `.cache/clone-evidence/`。

## ポータブル構成の再整備（2026-10-01）

- 開始時310件合格。最終Windows11 x64隔離コピーで **322 passed / 0 failed / 0 errors / 0 skipped**。
- 開発ツールなしPATH、隔離profile、無効なPYTHONHOME/PYTHONPATH/PIP_TARGETからOS標準PowerShellだけでクリーン構築。
- E:からC:へ構築し、`移動 日本語 space`へ実移動。旧コピーは消失、元リポジトリ読み込みはCPython hookで拒否。起動前にvenvを自動修復。
- 実BATのCLI JSON、同梱ChromiumのUI・分類・リスト削除、CSV/合成Cookie ACL/DB、ブラウザ終了後のサーバーポート閉鎖を確認。
- package/Runtime破損からの自動修復、Runtime/venv/ブラウザの全削除後のオフライン再構築・非隔離ビルド・再起動を確認。
- 全62wheelのSHA-256をPyPI公開値と照合。pip-auditの既知脆弱性0件。ruff/mypy、パス/リンク監査合格。
- 同梱SQLite3.50.4のWAL-reset不具合を公式資料で確認し、公式DLL3.53.4へ置換。公開SHA3-256・DLL SHA-256・ABI検査後に構築〜322試験を再実行。
- 実DLL: repo内37種類、Windows/driver内127種類、ホストIME/RTSS2種類。Pythonの外部パスは検証CWDとNULのみ。
- 全面WPR traceは0xc5585011で開始不可。実BOOTH、別PC、Windows10、全nativeアクセス、公衆再配布条件の完全確認は未検証。
- 詳細は `audit/portable-report.md`、機械証拠は `portable-summary.json` / `portable-verification.json` / `junit-portable.xml`。生ログは `.cache/portable-evidence/`。所有した隔離コピーa〜dは削除済み。

## 1.0.3 — 全体品質監査（2026-10-01）

- 全体調査後にBR-A01〜15を1単位ずつ再現・修正・検証。詳細は `audit/01-project-inventory.md`〜`audit/12-release-handoff.md`。
- 最終固定runtime別環境: **310 passed**。開始時238件から72件増加。
- 最終候補Release Gate: **44/44 PASS**。source bundle内308 passed、venv適用外fixture2 skip。
- ruff check/format、mypy、compileall、pip check、installed/locked dependency audit合格。
- parser2,000件中央値130.45ms、warm worker3.49ms、HTTP購入6.42ms、index14.98ms。
- 1,000folderでの新規DL保存先解決24.25ms→0.541ms、無関係directory stat1,000→0。
- 8 threads/1,000reads/40writes、active SQLite transaction中のkill後復旧を確認。
- 実BOOTH・別OS/Python・GitHub CI・長時間soakは今回未検証。ライセンス監査と実サービス疎通を次工程へ引き継ぐ。

このファイルは、リリース前の検証で**実際に何を確認し、何を示続きとして改善したか**の記録です。
推測や未実行の検査は記載していません。

---

## 1.0.2 — 再実行的重複ダウンロードと再開時の無音破損 (2026-09-29)

1.0.0 で「再開時のサイレントなデータ破損」を修正したが、**原因は症状の一つ
に過ぎなかった**。今回の調査はコードの読解ではなく、ローカル HTTP サーバを
立てて実際のソフトウェアを走らせて行った。品質ゲート (ruff / mypy / 200 tests)
は 1.0.1 の時点で全て緑だった。

### 1. Release Gate 結果

`python tools/build_release.py` → `python tools/rc_test.py` により、**配布物
そのもの**をクリーン環境で検証しました。

```
==========================================================================
  PASS 43   WARN 0   SKIP 0   FAIL 0
==========================================================================
RELEASE GATE: PASS
```

品質ゲート:

| ゲート | 結果 |
|---|---|
| `python -m ruff check .` | All checks passed! |
| `python -m ruff format --check .` | 32 files already formatted |
| `python -m mypy` | Success: no issues found in 15 source files |
| `python -m pytest -q` | **222 passed** |
| `python -m pip check` | No broken requirements found. |
| 配布物のクリーン環境でのテスト | 222 passed |

### 2. 発見・修正した不具合

#### 2.1 再実行のたびに全ファイルを取り直して複製する (Release Blocker)

- **症状**: `download` を 3 回実行すると `File.zip` / `File_2.zip` /
  `File_3.zip` が残り、転送も 3 回行われた。`download --all` と
  WebUI のダウンロードボタンは押すたびにライブラリ全体を再取得していた。
- **再現**: ローカル HTTP サーバ (item ページ 1 件 + ファイル 1 件) に対して
  `download_item` を 3 回。3 回目まで `File.zip` → `File_2.zip` →
  `File_3.zip`、テーブルも 3 行。
- **原因**: `core/download.py:_file_name_for` が**ファイルシステム上の存在**を
  根拠に「その名前は使用済み」と判定していた。1 回目に書いた `data.zip` を
  2 回目が「衝突」と見なし `data_2.zip` を選んだ。すると `done` と記録されて
  いる行は `data.zip` のままなので、`_existing_status` によるスキップ判定が
  当たらず、転送が実行される。名前と「done」の紐付けが一時的なファイル名に
  しか存在せず、**永続台帳に載っていない**。
- **症状 → 直接原因 → 根本原因**:
   symptom = 実行のたびに複製が増える
  → 直接原因 = ファイル名が実行ごとに `_2`, `_3` と変わる
  → 根本原因 = リンクとファイル名の対応が**永続化されておらず**、
    同じリンクを判定する手段がファイル名しかないこと
- **修正**: `downloads` テーブルに取得元 URL を持たせ (スキーマ v2、前方適用の
  マイグレーション)、リンクとファイル名の対応を台帳から解決する
  (`_NameLedger`)。優先順位は 1) 同じ URL に記録済みの名前 2) 旧形式の行
  (URL を持たないものは名前で照合) 3) 新規に割り当て。
  - 一意性の判定は「同一商品の台帳に存在する名前」と「このバッチで既に使った
    名前」のみで行い、**ファイルシステムを見ない**。
  - ユーザーが `downloads/` に手で置いたファイルは引き続き保護する。
  - 1.0.x 式で URL の無い行は名前で照合するため、**アップグレード時に既存の
    ライブラリが全件再ダウンロードされることはない**。
- **検証**: 3 回実行して `skipped: true` のみ、ファイル 1 本・台帳 1 行・
  転送 1 回。5 並列 × 40 件 × 3 ラウンドでも 0 複製・台帳 40 行。
  送信者がラベルを変更した場合、同一 URL なら同じファイルを再利用。
  別 URL どうしで同名のリンクは `data.bin` / `data_2.bin` のまま区別される。
  `--force` は連番を作らず上書きする。

#### 2.2 再開時のサイレントなデータ破損 (2 件目, Release Blocker)

- **症状**: 4,096 byte のファイルが **4,096 byte で「成功」**と報告され、
  中間 100 byte が別データで、sha256 が記録された。
- **再現**: `Range: bytes=512-` に対し `206 / Content-Range: bytes 0-99/4096`
  を返すサーバ。1 回目はサイズ検査で失敗するが、**汚染された `.part` が残る**。
  2 回目 (正常応答) はその offset から再開し、期待長に一致して公開される。
- **原因**: `append = status == 206 and offset > 0` が**ステータスコードだけを**
  根拠に追記可否を判断し、返ってきた範囲の**開始位置**を検証していなかった。
  1.0.0 の修正は合計サイズを検証したが、開始位置は検証していなかった。
- **修正**: 書き込む 1 byte 也不算する前に `Content-Range` の開始位置と
  要求した offset を照合する。不一致なら `.part` を破棄して 0 からやり直す
  (不一致のまま追記すると次の試行を汚染するため)。206 で `Content-Range` が
  無い場合も拒否する。
- **検証**: 同一シナリオで `.part` は破棄され、以降の再開で**元と完全に一致**。
  正常サーバの再開は従来どおり。

#### 2.3 新しいスキーマの DB で traceback が出る

- **症状**: `init-db` が Python の**完全なトレースバック**と
  `ERROR 予期しないエラーが発生しました` を出力した。README は「黙って壊すことは
  なく明示的に拒否する」と明記しており、`cli.py` の冒頭も「生の traceback は
  決してユーザーに届かない」と宣言している。日常的な「更新してください」相当の
  ケースでスタックトレースが出ていた。
- **原因**: `init_db` が意図的な拒否として `sqlite3.DatabaseError` を投げて
  おり、CLI の最終 catch-all に落ちて `.exception()` がログされ、traceback が
  stderr に出た。
- **修正**: `BoothSchemaTooNewError` (`BOOTH_SCHEMA_TOO_NEW`) を新設。
  検出された版と対応版、「更新してください」という処置を示す 1 行のメッセージに。

#### 2.4 `doctor` が任意の Cookie を確認できない

- **症状**: `auth login --cookie-path <独自>` で作ったログイン済みなのに
  `doctor` が `cookies ... なし。python cli.py auth login を実行` と表示。
  ユーザーには「ログインしていない」と伝えていた。
- **原因**: `_cmd_doctor` は `getattr(args, "cookie_path", None)` を読んで
  いたが、`doctor` のパーサに `--cookie-path` が**定義されていなかった**。
  常に `None`、つまり死んだコード。README は `auth` 系に `--cookie-path` を
  記載しているため利用者は実際に使う、案内が空回りしていた。
- **修正**: `doctor` に `--cookie-path` を実装。あわせて `has_cookies` の
  二重呼び出しを解消。

#### 2.5 `auth login` が通信障害を「ブラウザ未導入」と報告する

- **症状**: DNS / プロキシ / captive portal でログインページが開けないとき
  (現実で最も多い失敗)、`BOOTH_PREREQUISITE_MISSING` と表示され
  `python -m playwright install chromium` を実行するよう指示した。ブラウザは
  正常に起動していたため、指示どおり実行しても**同じエラーが返る**。
  1.0.1 が「直前のコマンドを再度実行せよ」という自己矛盾を解消したのと同じ
  種類の欠陥。
- **再現**: `page.goto` が `net::ERR_NAME_NOT_RESOLVED` を投げる偽物 →
  `BOOTH_PREREQUISITE_MISSING` / `playwright install chromium` 指示。
- **原因**: `login()` の `except Exception` が**ブラウザ起動後の一式**(遷移・
  Cookie 読み出し)まで `BOOTH_PREREQUISITE_MISSING` に潰していた。
- **修正**: Playwright / Chromium の**起動時のみ** prerequisite 扱い。
  遷移失敗と Cookie 読み出し失敗は `BoothNetworkError` とし、Playwright
  自身が持つ原因 (ERR_NAME_NOT_RESOLVED 等) をそのまま載せる。

#### 2.6 入力が読めないとき login がスレッドで落ちる

- **症状**: stdin が閉じている / 転送されている (サービス、スケジューラ、
  `< NUL`) と、Enter 待ちの daemon スレッドで `OSError` が捕捉されず(stack trace
  が表示され)、メインスレッドは「ログインを確認できませんでした」という
  無関係な理由を表示した。
- **再現**: pytest の capture 環境 (pytest が strict で
  `PytestUnhandledThreadExceptionWarning` を error 扱いしている) を過程で検出。
  **テストの実装側が、潜在バグを検出する側になった。**
- **修正**: `OSError` を捕捉し、`標準入力が読み取れないため` を明示。
  ブラウザは必ず解放する。

#### 2.7 `POST /download` が「絶対に成功しない作業」を受け付ける

- **症状**: Cookie が無い状態でダウンロードを要求すると 200 `{"ok":true}` を
  返すが、実処理はレスポンス送信**後**に走り、失敗はユーザーが読まないログに
  しか残らない。UI は「ダウンロードを開始しました」と表示する。
- **修正**: 受け付ける前にセッションを確認し、401 と再ログイン案内を返す。

#### 2.8 上限に達した商品を「完了」と報告していた

- **症状**: 1 商品 64 リンクの上限に達すると先頭 64 件だけ残し、`done` と記録。
  ファイルが欠けた状態で「全部取得済み」と報告し、画面にも台帳にも
  それが分かる記載がなかった。
- **修正**: 上限超過を `BOOTH_LIMIT_EXCEEDED` として明示 (zip の各上限と同じ
  扱い)。購入一覧の 20,000 件上限は、切り詰めた結果と理由をログに明記。

#### 2.9 暫定 item_id が無警告で使われていた

- **症状**: 商品リンクが見つからない行は `order_<id>` という**別のキー**で
  記録される。後にリンクが見つかった場合、同じ購入が 2 件として重複登録
  される。黙って起きうる。
- **修正**: 警告ログを出力。

#### 2.10 その他の整合

| 事象 | 対応 |
|---|---|
| 最終失敗メッセージが例外**型名だけ**で、原因が分からなかった | 理由文を含める (`_reason`) |
| `tools/build_release.py` が存在しない `requirements-lock-playwright.txt` を参照し、CHANGELOG もそれを記載していた | 参照を削除。runtime lock が Playwright を含んでいるため冗長 |
| `VERIFY_LOG.md` / `README.md` に混入した無関係な英単語 (pinnacle / lego) | 修正 |

### 3. 実動作・異常系・負荷の確認

実際に動かした検証 (ローカル HTTP サーバ / 実ブラウザに相当する HTTP 表面):

| 項目 | 結果 |
|---|---|
| 異常系: 不正フラグ・空文字・巨大値・型違反・排他指定 | 17 種すべて期待した終了コード、**traceback なし** |
| 異常系: 破損 DB / 途中まで破損した DB | 6 コマンドすべて exit 1、traceback なし |
| 異常系: Cookie jar が壊れている (非 JSON / 空 / 配列でない / name 無し) | exit 0/1、traceback なし |
| 異常系: HTTP 503 が継続 | `BOOTH_NETWORK_ERROR` で明示、公開ファイルなし |
| 異常系: 書き込み時に容量不足 | `空き容量と書き込み権限を確認` を含むエラー、公開ファイルなし |
| 5 並列 × 40 商品 × 3 ラウンド | 失敗 0・複製 0・台帳 40 行、メモリ増加 4.8 MB |
| CLI を 50 回連続実行 | 安定、traceback なし |
| RPC worker: 不正 JSON / 非オブジェクト / 型違い / SQL 断片 / 存在しないコマンド | すべて安全に応答、ワーカーは生存 |
| RPC worker: 200 並列呼び出し | エラー 0 / 0.63 s |
| RPC worker: 処理中に kill された後 | 自動再生成して回復 |
| WebUI: 全 read/write エンドポイント | 期待どおりのステータス |
| WebUI: XSS (サーバーレンダ) | エスケープ済み |
| WebUI: クロスオリジン POST / DNS リバインド | 403 / 400 で拒否 |
| WebUI: Cookie 無しでダウンロード要求 | 401 (修正後) |
| 起動 → 操作 → 中断 → 再起動 | 状態は保持、異常なし |

### 4. 残存事項

| 項目 | 状態 |
|---|---|
| 実 BOOTH への疎通 (ログイン〜購入取得〜DL) | **NOT VERIFIED**。Cookie と著作物データが必要なため自動テストに含めていません。ローカル HTTP サーバとモックで、再実行の重複・再開・破損検出・zip bomb・並列競合は実検証済み。初回は手動で `purchases list --update-db` を確認してください |
| 1.0.x で作成された `*_2.zip` などの既存複製 | 新たに増えません。既存の複製は台帳に残ったままなので、不要なものは `downloads/` から手動で削除して構いません |
| BOOTH 側マークアップ変更への対応 | 想定内。`BOOTH_LAYOUT_CHANGED` (exit 3) で停止。README に手順を記載 |
| Mac / Linux | 仕様外 |

---

## 1.0.1 — 前提不足エラーの修正 (2026-09-29)

### 報告された不具合

    E:\...>python cli.py auth login
    ERROR BOOTHへのログインが必要です。`python cli.py auth login` で再ログインしてください。
    Playwrightが未導入です。`pip install playwright && ...` を実行してください。

- 原因1: 部品不足を `BoothAuthError` で報告していたため、実行したばかりのコマンドを
  再実行するよう指示する自己矛盾が生じていた。
- 原因2: Playwright を base 依存から外していた。実ブラウザでのログインが本アプリ
  唯一の認証経路であり、記載どおりの手順だと認証すらできない構成になっていた。

### 修正

- `BoothPrerequisiteError` (`BOOTH_PREREQUISITE_MISSING`) を新設。
  Playwright / httpx / beautifulsoup4 の 4 箇所の部品不足をこれに変更。
- 認証失敗の「再ログイン」案内は、認証が実際に失敗した場合にのみ残るよう確認済み。
- Playwright を `requirements.txt` に戻し、lock を再生成。
- `doctor` に `browser:chromium` 検査を追加 (パッケージとブラウザ本体を分けて判定)。
- 回帰テスト 12 件を追加 (200 件)。

### 修正後の出力

    ERROR Playwright (実ブラウザ操作) が未導入です。`pip install -r requirements.txt`
    を実行してください。setup.bat を使えば導入とブラウザのダウンロードまで自動です。

Release Gate 再実行: 43/43 PASS、200 passed。

---

## 1.0.0 — 完成化・Release Gate 通過 (2026-09-29)

### 1. Release Gate 結果

`python tools/rc_test.py` により、**配布物そのもの**をクリーン環境で検証しました。

```
==========================================================================
BOOTH-Reader Release Candidate validation
==========================================================================
[PASS] artifact built                                BOOTH-Reader-1.0.0-windows-x64.zip
[PASS] artifact checksums verify
[PASS] artifact extracts                             49 entries
[PASS] artifact carries no user data or secrets
[PASS] no credential-shaped strings in product source
[PASS] no key material or credential files in tests
[PASS] clean install from requirements.txt
[PASS] dependency tree coherent (pip check)          No broken requirements found.
[PASS] lxml not pulled in by runtime deps            stdlib html.parser backend in use
[PASS] hash-pinned lock resolves
[PASS] startup: --version / init-db / unclassified / purchases list
[PASS] startup: downloads list / lists list / doctor
[PASS] json contract: unclassified / purchases / downloads / lists / doctor
[PASS] exit code: version=0 help=0 unknown subcommand=2 init-db=0
[PASS] exit code: empty list name=2 overlong list name=2
[PASS] exit code: mutually exclusive flags=2 concurrent out of range=2
[PASS] exit code: invalid sort choice=2 not logged in=1
[PASS] malformed input handled without traceback
[PASS] corrupt database reported cleanly
[PASS] repeated execution is stable
[PASS] list creation is idempotent                    1 lists
[PASS] recovers after a forced kill
[PASS] every README command runs
[PASS] web ui http surface                            /health,/purchases,/unclassified,
                                                      /downloads,/lists=200 /auth/status=401
                                                      / =200 rebind Host=400
[PASS] web ui returns valid JSON
[PASS] 200 concurrent worker calls                    errors 0 elapsed 0.62
[PASS] dependency vulnerability audit                 No known vulnerabilities found
[PASS] shipped test suite passes                      199 passed

  PASS 43   WARN 0   SKIP 0   FAIL 0
==========================================================================
RELEASE GATE: PASS
```

検証環境: Windows 11 / Python 3.12.13 / クリーン venv (開発用 venv とは別)

### 2. 品質ゲート

| ゲート | 結果 |
|---|---|
| `python -m compileall -q cli.py core web tests conftest.py` | EXIT 0 |
| `python -m ruff check .` | All checks passed (0 errors) |
| `python -m ruff format --check .` | 30 files already formatted |
| `python -m mypy` | Success: no issues found in 15 source files |
| `python -m pytest -q` | **199 passed** |
| `python -m pip check` | No broken requirements found |
| `python -m pip_audit -r requirements.txt` | No known vulnerabilities found |
| `pip install --dry-run --require-hashes -r requirements-lock.txt` | 成功 (EXIT 0) |
| パッケージビルド (`python -m build`) | 警告なしで成功 |

ベースライン(0.1.0)は ruff 22 件・mypy 12 件・テスト 24 件・再現不能な
requirements でした。

### 3. 発見・修正した不具合

いずれも再現確認 → 根本原因修正 → 回帰テスト追加 の順で対応しました。

#### 3.1 ダウンロード再開時のサイレントなデータ破損 (Release Blocker)

- **症状**: 300,000 byte のファイルが **431,072 byte** で「成功」と報告され、
  中間 84,464 byte が重複し、sha256 が記録された。
- **再現**: 150,000 byte の部分ファイル + 2 回の接続切断が発生する HTTP サーバ。
- **原因**: `download_file` がリトライループの**外側**でオフセットを 1 度だけ取得していた。
  1 回目の試行で部分的に書き込まれた後、2 回目も同じオフセットを要求して
  再度追記していた。append/truncate の判断もリクエスト側ではなく
  「Range を送ったか」で行っていた。
- **修正**: オフセットをリトライごとにディスク上の実サイズから再計算。
  append/truncate は**レスポンス** (`206` か否か) から決定。
  完了サイズを `Content-Range` / `Content-Length` と照合してから公開。
  書き込みは `<name>.part` に行い、`os.replace` で atomic に公開。
- **検証**: 同一条件で **300,000 byte・sha256 完全一致** を確認。
  失敗時は `.part` のみが残り、ライブラリに破断ファイルは残りません。

#### 3.2 `item_id` によるパストラバーサル (Release Blocker)

- **症状**: `item_dir("C:/lib", "../../../Windows/System32/drivers/etc", "hosts")` が
  ライブラリ外を指した。
- **原因**: `item_id` が無検査でパス要素として結合されていた。
- **修正**: 区切り文字・ドライブ文字・`..` を拒否する `validate_item_id()` を追加し、
  解決後のパスが root 配下であることを再確認。

#### 3.3 zip bomb (未制限の展開)

- **症状**: 200 KB の zip が 200 MB に展開され、ディスクとメモリを消費。
- **原因**: 展開後のサイズ・エントリ数・圧縮比の制限が無く、各エントリを
  メモリ上に全面読み込みしていた。
- **修正**: 上限を**1バイトも書く前に**検証 (エントリ数 / 合計サイズ / 個別サイズ /
  圧縮比 200:1)。書き込みは `shutil` 相当のチャンク転送に変更。
  上限超過は専用の `BoothLimitExceededError` (exit 1) として明示。
- **検証**: 60 MB の爆弾が 0 バイトの書き込みで拒否されることを確認。

#### 3.4 ログにおける JWT トークン漏えい (セキュリティ)

- **症状**: `Authorization: Bearer <jwt>` に対し、フィルタが `Bearer` という
  語だけを削除し、**トークン本体がそのままログに残っていた**
  (パターンが `\S+` で空白で止まるため)。同時に `cookies count=42` という
  正常运行ログが `[REDACTED]` に破壊されていた。
- **修正**: 秘密キーの語彙リストに対するキー+区切り子+**値全体**の一致に書き直し。
  JSON 形式 (`{"token": "..."}`)、`X-API-Key`、`Basic`、PEM ブロック、
  単独 JWT も対象。`cookies count=42` や URL は保持される。
- **検証**: 11 種の漏えいパターンと 9 種の保持パターンをテストで固定。

#### 3.5 Cookie ファイルのロックアウト可能性

- **症状**: `icacls /inheritance:r` を先に実行していたため、後続の grant が失敗すると
  ユーザーが**自分の Cookie ファイルを読めなくなる**可能性があった。
- **修正**: grant を先に適用し、結果を確認。読めなくなった場合は
  完全アクセスを付与して継承を戻す。`whoami` / `icacls` は絶対パス解決後に実行。

#### 3.6 ログイン未確認のまま Cookie を保存

- **症状**: Enter を押すだけで未ログインの Cookie jar が保存され、
  後で不可解なエラーになっていた。
- **修正**: 保存前にライブラリへ遷移して認証済みか確認。空ライブラリでも
  ログイン成功とみなす (判定は「ログインページに飛ばされなかったか」)。

#### 3.7 壊れた DB で利用者が次に取れる行動が示されない

- **症状**: 破損した `app.db` に対し `ERROR 予期しないエラーが発生しました` と
  traceback が出て、用户在什么都不知道。
- **修正**: `BoothDatabaseError` を追加し、ファイル名・退避手順・
  `--db` での代替指定・`init-db` での再作成を案内するメッセージに。
  3 パターンをテスト (完全破損 / 途中破損 / ディレクトリ指定)。

#### 3.8 その他

| 事象 | 対応 |
|---|---|
| `subprocess.run(text=True)` が `icacls` の日本語出力を UTF-8 として解釈し reader thread で例外 | `errors="replace"` を指定 |
| Beautiful Soup の属性が `list` / `None` を返し `TypeError` | `_attr()` で常に `str` に正規化 |
| `save_cookies` が不正な引数で `len()` の `TypeError` | 検証をログ出力より前に実行 |
| RPC worker が要求内の `--db` を通 sadly 別 DB を参照し得た | worker の DB を常に優先 |
| `POST /download` が件数表示のためだけに `purchases` を実行 | 事前取得を削除 |

### 4. パフォーマンス (実測 Before / After)

測定条件: Windows 11 / Python 3.12.13 / DB に 500 件

| 計測項目 | Before | After | 改善 |
|---|---|---|---|
| `parse_library_html` 2000 行 | **98.16 s** | **0.228 s** | 約 430 倍 |
| `parse_library_html` 8000 行 | 実行不能 | 1.366 s | 線形化 |
| パースコスト / 行 | 行数とともに増加 | 0.12–0.18 ms で一定 | — |
| Web データ取得 (1 回) | 184.9 ms | 3.7 ms | 約 50 倍 |
| ページ描画的数据取得 (4 回) | 726.1 ms | 13.4 ms | 約 54 倍 |
| `GET /` エンドツーエンド | — | 16.8 ms | — |
| Web 並列 200 リクエスト | — | 0.62 s / エラー 0 | — |

**原因**: `parse_library_html` のメタデータ探索が `<body>` まで登り、行ごとに
CSS セレクタを**文書全体**に対して実行していた (2000 行で 2,886,002 回の
セレクタマッチ)。行サイズ上限 (`_is_row_sized`) を導入し、
`order_id` の位置索引を一度だけ構築する実装に変更。

**追加した最適化**:
- リクエストごとに `httpx.Client` を作らず、スレッドごとのプールを使い回す
- Web 層の常駐ワーカー (`cli.py rpc`) により、要求ごとの Python 起動を廃止
- SQLite を WAL モードに (並列 DL の書き込み競合を吸収)
- 読み取り専用のコマンドでは WAL checkpoint を省略

### 5. セキュリティ監査

| 項目 | 結果 |
|---|---|
| コマンドインジェクション | 該当なし。shell は不使用、argv は固定、`shell=False` |
| パストラバーサル | `item_id` と zip エントリ名の両方を検証。テスト済み |
| SQL インジェクション | 値は全てプレースホルダ。ORDER BY は固定 dict からのみ |
| XSS | サーバーレンダと JS の両方でエスケープ。テスト済み |
| CSRF / DNS リバインディング | `TrustedHostMiddleware` + 同一オリジン検証。テスト済み |
| 資格情報の漏えい | Cookie 値はログに出ない。Cookie は送信先ドメインで絞り込む。URL の query はログから除去 |
| 安全でないデシリアライゼーション | 独自形式のみ。`pickle` 等の使用なし |
| 権限 | Cookie は本人アカウントのみに制限。失敗時はロールバック |
| TLS | 検証を無効化していない。`certifi` 経由 |
| ランダム性 | ジッタに非暗号学的 RNG を使用 (要件は retry の分散のみ) |
| 依存関係 | `pip-audit` 既知の脆弱性なし。ハッシュ固定 lock あり |
| 秘密情報の混入 | ソース・配布物・Git 履歴を走査。検出なし |

### 6. ライセンス監査

- 本体: MIT (`LICENSE`)
- 実行時依存 19 パッケージ: すべて permissive
  (MIT / BSD-3-Clause / Apache-2.0 / MPL-2.0 / PSF-2.0)
- 開発用ツール (pytest / ruff / mypy / pip-audit / build / bandit): CI のみ
- 同梱する第三者アセット (フォント・画像・音声・動画・モデル・バイナリ・コード断片): **なし**
- **lxml は意図的に非依存**。stdlib の `html.parser` を使用。
  クリーン環境での非導入を RC テストで確認済み
- 詳細は `THIRD_PARTY_NOTICES.md`

### 7. 成果物

```
dist/BOOTH-Reader-1.0.0-windows-x64.zip   122.9 KB   展開してすぐ実行
dist/booth_reader-1.0.0-py3-none-any.whl    68.5 KB   pip install
dist/booth_reader-1.0.0.tar.gz              86.6 KB   ソース配布
dist/SHA256SUMS.txt                                   チェックサム
```

- `booth-reader` コンソールスクリプトが wheel に含まれます
- wheel をクリーン venv に導入して動作確認済み (CI の `package` ジョブでも実施)
- 配布物に `app.db` / `data/` / `BOOTH-Reader-Library/` は含まれません

### 8. 残存事項 (技術的に解消不能)

| 項目 | 状態 |
|---|---|
| 実 BOOTH への疎通 (ログイン〜購入取得〜DL) | **NOT VERIFIED**。Cookie と著作物データが必要なため自動テストに含めていません。ローカル HTTP サーバとモックで DL 再開・破損検出・zip bomb・並列競合は実検証済みです。初回は手動で `purchases list --update-db` を確認してください |
| BOOTH 側マークアップ変更への対応 | 想定内の制約です。`BOOTH_LAYOUT_CHANGED` (exit 3) で明示的に停止し、`booth-manager` / `BoothPM-SDK` を参照した修正手順を README に記載しています |
| Mac / Linux 対応 | 仕様外です。`.bat` ランチャーと Windows ACL に依存します |
| GitHub への公開 | 技術的には可能です。`git remote add` / `git push` と Release 作成が必要で、この環境では認証情報が利用できないため未実施です。タグ `v1.0.0` を作成した状態なので、`git push` するだけです |

### 9. 最終確認

```
v1.0.0 タグ作成前の最終確認:
  テスト      199 passed
  ruff        0 errors
  ruff format 30 files formatted
  mypy        0 errors
  pip-audit   0 vulnerabilities
  RC gate     43/43 PASS
```

---

## 完全ポータブル化 (2026-09-30)

リポジトリ外依存の排除と環境の自己完結化。以下はすべて実実行の結果。

### 1. Release Gate 結果

`python tools/build_release.py` → `python tools/rc_test.py` により、**配布物
そのもの**をクリーン環境で検証しました。

```
==========================================================================
  PASS  44   WARN 0   SKIP 0   FAIL 0
==========================================================================
RELEASE GATE: PASS
```

品質ゲート:

| ゲート | 結果 |
|---|---|
| `python -m ruff check .` | All checks passed! |
| `python -m ruff format --check .` | 37 files already formatted |
| `python -m mypy` | Success: no issues found in 16 source files |
| `python -m pytest -q` | **235 passed** |
| `python -m pip check` | No broken requirements found. |
| `python tools/check_portable.py` | 14/14 passed |
| 配布物のクリーン環境でのテスト | 234 passed, 1 skipped（skipはバンドル内に.venvがないための想定内スキップ） |

### 2. 移動・再構築試験（実実行）

| 試験 | 結果 |
|---|---|
| 追跡ファイルのみの複製 → `setup.bat --skip-browser` | 成功（同梱Python取得・venv作成・依存導入・init-db・監査6/7。残1はブラウザ未導入の想定内FAIL） |
| システムPythonなし（PATH遮断）+ `.tools`同梱 → `setup.bat` | 成功（同梱Pythonをランナーとして使用） |
| セットアップ済みフォルダの別ディレクトリへのコピー | 成功（`health` OK・監査7/7・`doctor ok=True`・`unclassified` 動作） |
| コピー先での `setup.bat --repair` | 成功（venvをコピー先の同梱Python基準で再構築・`pip check` 正常） |
| クリーン環境での `tests/test_portable.py` + `test_basic.py` | 17 passed |

### 3. 残存する制約（再掲。詳細は PORTABLE.md）

- Windows 10/11 64bit 専用（仕様）
- 初回セットアップ時のみネットワークと何らかの Python 3.10+ が必要
- 実BOOTHとの疎通は従来どおり自動テスト対象外（Cookie・著作物のため）
- 開発者PCのユーザープロファイルに残る旧Chromium（`%USERPROFILE%\AppData\Local\ms-playwright`）は本件の動作に不使用。削除は利用者判断に委ね、自動削除しない
