# 検証ログ

各時点の結果です。過去の合格を現行版・実BOOTH・未試験環境の保証とは扱いません。詳細は [audit/](audit/) と [license-audit/](license-audit/)。

## 2026-10-05 文書・案内の短縮

- 主要5文書の文字数を約71%削減。手順・検証結果・未確認範囲・参照先を保持し、起動/CLI/取得ログも短縮。
- **432 passed**、Ruff/format/Mypy19、PS5.1構文・BOM、文書リンク、実BATのcheck/versionを確認。Python差分は文字列のみ。

## 2026-10-05 長いパスの修正

- tikv-jemalloc-sysの通知3件を短いパスへ移動。原文・取得元・ハッシュを保持し、生成時の短縮と配布候補の相対180 UTF-16単位上限を追加。
- 新規5ケースは修正前失敗→修正後成功。**432 passed**（既存Starlette警告1件）、Ruff/format/diff、原文2,137参照・1,506通知、配布2,529ファイルPASS。
- クリーン候補で初回Web/CLI・移動・ブラウザー復旧・入力2,528等価・元index不変・後始末PASS。証拠: `.cache/path-fix-clone-verification.json`。
- Windowsシェルで2,529ファイルをコピー成功。保存先root78文字で最長257文字。現PCでは旧277〜282文字もコピーでき、報告されたExplorer操作の失敗自体は未再現。

## 2026-10-04 起動・操作案内

- 起動・復旧を日本語化。PS5.1でUTF-8 BOMを検証。`--check` / `/?` / `version` / 不正引数を実BATで確認。
- 起動中の `--repair` はexit 1、venv更新時刻不変。UIの初回案内・Cookie置換・未完了削除・保存先・構造変更ヒントを確認。
- **425 passed**、Ruff/format/Mypy19ソース/pip、portable18/18、私用パス0、原文・vendor PASS。clone88チェック、入力2,526等価、外部profile書込み0、後始末PASS。

## 2026-10-04 単一起動

- 入口を `start.bat` に統合。引数・DB位置・日本語/空白パス、既存画面の再利用、ポート回避（23106→23107、9610→9611）を実BATで確認。
- **417 passed**、品質・依存・portable18/18・原文・vendor PASS。clone88チェック・入力2,525等価・移動・復旧・元index不変。
- `Write-Host` が初回CLI JSONへ混入したためstderrへ変更し、JSON純度を再確認。

## 2026-10-03 GitHub CI・クローン配布

- CI run `37135441351`（`88afa49`）は3ジョブPASS：品質2m49s、秘密/依存1m3s、clone/移動6m22s。
- LF/CRLFでvendor lockが不一致になる問題を修正。テキスト62件をLF化し、manifestを更新。
- Windows tarが英語ロケールの日本語パスで失敗。.NET GZipStream/ustarへ置換し、抽出2,336ファイルのSHA-256をtarfileと照合（5.7秒）。CI run `37139908849`（`8c198ff`）も全ジョブPASS。
- 破損WebView2の停止を90秒起動期限・150秒検査期限で解消。probe watchdog360秒、検証タイムアウト600秒、失敗ログ保存を追加。再配置監査のUTF-8・キャッシュ先も修正。
- 独立cloneのMAX_PATH失敗を `core.longpaths=true` で修正。履歴再初期化後、配布2,530・clone89チェックPASS。
- ActionsをNode24対応のcheckout/upload-artifact v7.0.1（SHA固定）へ更新。gitleaks8.30.1をSHA-256検証後に全履歴へ実行し、exit0・SARIF0件。
- Web機密値返却、ブラウザーホスト破損/再生成、BATのDB引数消失を修正。最終隔離候補 **410 passed**、入力2,529等価、原文2,137参照・1,506通知PASS。
- Ruff/format/Mypy19/compile/pip、portable18/18、vendor、PyPI62wheel、offline lock、CLI7コマンドPASS。pip-audit・gitleaks未解決0。実DB/Cookie・元index不変、外部profile/temp書込み0。
- WebView2移行時の基準は **396 passed**。Runtime/SDK・VC CRTの公式条件を保持。詳細: [追加確認](audit/18-clone-distribution-followup.md)・[配布条件](license-audit/28-clone-distribution-followup.md)。

## 2026-10-01 クローン即起動・ポータブル再整備

- vendor同梱、準備の自動化、PowerShell起動前のprofile/cache/temp固定。空profile・無効Python/pip・開発ツールなし・到達不能proxyで初回Web23.8秒/CLI19.4秒、stdout JSON・外部書込み0。
- 生成物なし候補 **327 passed**。先行隔離コピー **322 passed**（開始310）。C/Eドライブ、日本語/空白パスへ移動し、旧配置の読取をaudit hookで拒否。
- CLI JSON・UI分類/削除・CSV・合成Cookie ACL・DB・停止・環境全削除後のオフライン再構築を確認。PyPI62wheel hash一致、pip-audit0、Ruff/Mypy/リンク検査PASS。
- SQLite3.50.4のWAL-reset問題を公式DLL3.53.4へ置換。公開SHA3-256・DLL SHA-256・ABI確認後に再試験。
- DLL観測: repo37種、Windows/driver127種、IME/RTSS2種。Python外部パスは検証CWDとNULのみ。WPRは `0xc5585011` で開始不可、全nativeアクセスは未検証。
- 詳細: [portable-report](audit/portable-report.md)、`audit/portable-summary.json` / `portable-verification.json` / `junit-portable.xml`。隔離コピーは削除済み。

## 1.0.3（2026-10-01）

- BR-A01〜15を再現・修正・回帰確認。**310 passed**（238→310）、RC44/44、配布ソース308 passed/venvなし2 skip。品質・依存検査PASS。
- 性能中央値: parser2,000件130.45ms、worker3.49ms、HTTP購入6.42ms、index14.98ms。保存先解決（1,000フォルダー）24.25→0.541ms、無関係stat1,000→0。
- 8スレッド/1,000読込/40書込、SQLite transaction中の強制終了後復旧を確認。詳細: [修正ログ](audit/06-repair-log.md)・[引継ぎ](audit/12-release-handoff.md)。

## 2026-09-30 ポータブル化（当時の構成）

- **235 passed**、Ruff/format/Mypy16/pip、portable14/14、RC44/44。配布環境234 passed/venvなし1 skip。
- 追跡ファイルからsetup、システムPython遮断、別配置のCLI/health/doctor、repair、局所17テストを確認。skip-browser監査の残1 FAILはブラウザー省略によるもの。
- 当時は初回通信・Python3.10+が必要。後の同梱構成で解消。旧ユーザー領域のChromiumは不使用・自動削除なし。

## 1.0.2（2026-09-29）

**222 passed**、Ruff/format/Mypy15/pip、クリーン配布テスト、RC43/43 PASS。ローカルHTTPで次を再現・修正しました。

| 問題 | 原因・修正・確認 |
|---|---|
| 再実行で複製・再転送 | ディスクから毎回改名→URLと名前をDB v2台帳へ固定。3回実行で1転送/1ファイル/1行、旧URLなし行は名前照合、手置き原本を保持 |
| 再開後に同サイズの別データ | 206開始位置を未確認→書込み前にoffset照合、不一致partを破棄。4,096byteの中間100byte汚染を防ぎ、原本と一致 |
| 新版DBでtraceback | `BoothSchemaTooNewError` と更新案内へ |
| 独自Cookieをdoctorが見ない | `--cookie-path` を定義、重複検査を除去 |
| DNS等の障害をブラウザー不足扱い | 起動失敗と遷移/読取失敗を分離、通信の原因を保持 |
| stdin閉塞でスレッド例外 | OSErrorを捕捉し、入力不可を明示・ブラウザー解放 |
| 認証なしDLを受理 | 開始前検査で401 |
| リンク上限を完了扱い | `BOOTH_LIMIT_EXCEEDED`。暫定order ID使用は警告 |
| 原因不明の失敗・不存在lock参照 | 最終理由を保持、旧Playwright専用lock参照を除去 |

- 不正入力17種・破損DB6コマンド・不正Cookie・HTTP503・容量不足を確認。公開原本なし、tracebackなし。
- 5並列×40商品×3回: 失敗/複製0、台帳40行、メモリ増加4.8MB。CLI50回安定。
- RPC不正入力・200並列（0.63秒/エラー0）・kill後復旧、Web read/write・XSS・Origin/Host拒否、再起動後の状態保持を確認。
- 旧版の既存複製は保持。実BOOTH通しは未検証。

## 1.0.1（2026-09-29）

部品不足を認証エラーにしていたため `BoothPrerequisiteError` を追加。Playwrightを必須依存へ戻し、doctorへブラウザー本体検査を追加。回帰12件、**200 passed**・RC43/43。

## 1.0.0（2026-09-29・当時の配布構成）

Windows11/Python3.12.13の別venvで **199 passed**・RC43/43、Ruff/format/Mypy15/compile/pip、pip-audit0、hash lock・ビルド・wheel導入PASS。基準0.1.0は24テスト、Ruff22/Mypy12件、不再現requirements。

| 問題 | 修正・検証 |
|---|---|
| 切断後の範囲重複（300,000→431,072byte） | retryごとにoffset再計算、応答でappend判定、サイズ確認後atomic公開。原本byte/hash一致 |
| item_idによるパス逸脱 | 区切り・ドライブ・親参照を拒否しroot再検査 |
| ZIP bomb | サイズ・件数・圧縮比を事前制限しstream展開。60MB試料を0byte書込みで拒否 |
| JWT漏えい・正常ログ破壊 | 値全体を伏せ字化。漏えい11種・保持9種を回帰確認 |
| Cookie ACLで読取不能 | grant先行・検査・失敗rollback |
| 未認証Cookie保存 | ライブラリ遷移で確認後に保存（空ライブラリ可） |
| 破損DBの生例外 | DB名・退避・代替DBを案内。完全/途中破損・ディレクトリ指定を確認 |
| 日本語icacls・属性型・不正Cookie引数 | decode置換・str正規化・検証順修正 |
| RPCの別DB指定・不要な購入照会 | worker DBを固定、余分な照会を除去 |

- 性能（500商品DB）：parser2,000行98.16s→0.228s、8,000行1.366s、Web照会184.9→3.7ms、4照会726.1→13.4ms、GET `/` 16.8ms、200並列0.62s/エラー0。
- 文書全体の繰返し探索を行単位＋order位置索引へ変更。HTTP pool・常駐worker・WAL・読取checkpoint省略を導入。
- SQL値のbind、XSS、Origin/Host、Cookie送信先・ACL・伏せ字、TLS・lock、ソース/配布物/履歴スキャンを確認。当時の依存19件の通知を調査（第三者物非同梱）。
- 当時の成果物: ZIP122.9KB・wheel68.5KB・sdist86.6KB・SHA256SUMS。個人データなし、クリーン導入確認。現在はGitクローン配布です。

## 未確認範囲

実BOOTHのログイン→購入取得→DL、Windows10・別PC・長時間運転・全nativeアクセスは未検証です。製品全体の条件は [リリース範囲](audit/19-release-scope.md)、現行入力は `license-audit/release-gate.json` を参照。
