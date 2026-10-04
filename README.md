# BOOTH-Reader

## 配布対象: GitHubリポジトリ（クローン）

配布はこのGitリポジトリをクローンする形で行い、配布用のZIP/sdistは作成しません。Git追跡内容には同梱ランタイム（`vendor/`）を含みます。
個人データ（Cookie・購入履歴DB・購入物・ブラウザーprofile）はGit対象外のまま利用中フォルダーに保存され、クローンには含まれません。
配布準備の現行判定は [クローン配布の追加監査](license-audit/28-clone-distribution-followup.md) と `license-audit/release-gate.json` に記録します。ゲートはGit追跡内容と追加候補の全ファイルを検証し、変更後は古い判定での配布を拒否します。
原文証拠と第三者への対応ソースは `THIRD_PARTY_LICENSES/`、`SOURCE_OBLIGATIONS/` に保持しています。

利用中のフォルダーを丸ごとコピーして第三者へ渡すことは想定していません。Cookie・DB・購入物を含むため、配布は必ずGitクローンで行ってください。
今回の範囲・必須条件・未確認事項は [リリース範囲と判定条件](audit/19-release-scope.md)、前回の検証結果は [クローン配布の最終確認](audit/18-clone-distribution-followup.md) にあります。ライセンスゲートの合格と製品全体のリリース準備完了は別の判定です。

Python・依存・ブラウザーは `vendor/` に同梱し、Git LFS、追加ダウンロード、システムへのインストールは不要です。
初回だけフォルダ内に自動展開します。設定・DB・Cookie・ダウンロード・キャッシュ・一時ファイルも既定でこのフォルダ内です。

同梱Microsoftコードの利用・再配布には [第三者ソフトウェアの利用条件・データ通知](THIRD_PARTY_TERMS.md) が適用されます。WebView2のSmartScreenは有効で、Microsoftへの情報送信があります。ローカル保存先の隔離と外部通信は別です。

BOOTH で購入したものを「取得・ダウンロード・解凍・分類」まで一括で管理する、個人利用向けのデスクトップツールです。

中心にある考え方はひとつだけです。**「リストに追加するとき、未分類のものだけを見ればよい」**。
分類済みの商品は追加候補から消え、全商品のライブラリでは引き続き確認できます。
それ以外の細部は、眺める必要がないように設計しています。

- 処理の本体は CLI です。Web UI は CLI を呼ぶだけなので、端末でもブラウザーでも同じコードが同じ結果になります。
- パスワードは一切保存しません。Cookie JSONの登録、または実ブラウザでのログインに対応します。
- BOOTH 公式の購入 API はないため HTML を解析します。マークアップが変わった場合は推測で進めず、`BOOTH_LAYOUT_CHANGED` で明示的に止まります。

---

## 目次

- [特徴](#特徴)
- [動作環境](#動作環境)
- [インストール](#インストール)
- [起動](#起動)
- [設定](#設定)
- [使い方](#使い方)
- [使用例](#使用例)
- [終了コード](#終了コード)
- [更新](#更新)
- [アンインストール](#アンインストール)
- [トラブルシューティング](#トラブルシューティング)
- [制限事項](#制限事項)
- [ライセンス](#ライセンス)

---

## 特徴

- **未分類キューを第一級機能に** — `LEFT JOIN list_members` で分類済みを除外します。分類した瞬間に一覧から消えます。
- **分類はリスト名でも数値 ID でも** — どちらを渡しても正しく解決します。
- **ダウンロードは中断しても壊れない** — 書き込みは `.part` へ行い、完成とサイズの検証後に atomic rename で公開します。通信が切れても再実行で続き、壊れたファイルがライブラリに残ることはありません。
- **失敗を成功扱いしない** — 一部ファイルだけ失敗した商品や、破損ZIPの展開失敗も失敗として記録します。Webの最終ジョブ結果は `/health` で確認できます。
- **並列ダウンロード** — 既定 3・上限 5。WAL モードで書き込み競合を吸収します。
- **zip 自動解凍（安全）** — Zip Slip に加えて、zip bomb（展開後サイズの異常、圧縮比異常、エントリ数超過）も展開前に検出して拒否します。
- **リトライとバックオフ** — 一時的な 5xx・タイムアウト・接続断は指数バックオフと分散付きで自動再試行します。403 や 404 は無駄に再試行しません。
- **Web UI は loopback のみ** — Host ヘッダー検証と同一オリジン検証により、外部のページから操作されることを防ぎます。
- **機械取込用の JSON** — `--json` は stdout に ASCII のみの JSON だけを出力します。ログと進捗表示は必ず stderr に出ます。
- **診断コマンド** — `doctor` が環境・DB の整合性・空き容量・依存関係をまとめて確認します。
- **再実行しても壊れない** — 完了済みのファイルは再取得しません（`--force` で上書き可）。分類の追加も冪等です。
- **安全な再開** — strong ETag / Last-Modifiedを `.part.json` に記録し、If-Rangeで同じ版を確認します。確認情報がない部分ファイルは先頭から取り直します。

## 動作環境

| 項目 | 要件 |
|---|---|
| OS | Windows 11 x64で検証。Windows 10 x64 build 17763以降は構成上の対象・今回未検証 |
| Python | システムへの導入不要。OS標準PowerShellから固定CPython 3.12.13を `.tools\python` へ準備 |
| 対象 | ローカル利用の個人ツール。サーバー公開や複数ユーザーでの共有は対象外 |
| ネットワーク | BOOTHログイン・購入情報更新・新規ダウンロード・商品画像取得に必要。WebView2のSmartScreen通信は別途あり。起動と環境準備はオフライン可 |

ポータブル構成の詳細は [PORTABLE.md](PORTABLE.md) を参照してください。
フォルダをコピーするだけで移動でき、フォルダを削除するだけで
プロジェクト専用環境も削除できます。

## インストール

### クローンして起動

リポジトリをクローンし、`start.bat` を開くだけです。初回はGitに含まれる同梱物を検証・展開し、環境とDBを自動生成してからブラウザーでUIを開きます。セットアップを事前に実行する必要はなく、環境の不足・移動・破損・ポートの競合も起動時に自動判定して復旧します。

```powershell
git clone https://github.com/mofu1224/BOOTH-Reader.git
# クローン先で実行
& .\start.bat
```

Windows11 x64のクリーン配置では初回Web起動約24秒、CLI約19秒で完了しました。2回目からは生成済み環境を使用します。

```bat
start.bat              : クローン後の通常起動（Web UI）。初回準備もブラウザー起動も自動
start.bat 8080         : ポート番号を指定
start.bat --repair     : 環境の作り直し（移動後・破損時）
start.bat --check      : セットアップが必要かだけを確認（0=準備済み）
start.bat --skip-browser : ブラウザ導入の省略（auth login を使わない場合）
start.bat doctor       : CLIコマンドはそのまま指定できる
start.bat cli --help   : CLIを明示的に起動
start.bat /?           : ヘルプ（help と同じ）
```

`vendor/windows-x64/` はクローンに必要な同梱物です。固定版・ハッシュを検証して使用します。
`.tools` / `.venv` / `.cache` / `.playwright-browsers` は生成物なのでGitには入れません。
これらがなくても、同梱物だけから起動時に自動復元します。詳細は [PORTABLE.md](PORTABLE.md)。

## 起動

```bat
start.bat              : ブラウザーが自動で開く（通常はこれをダブルクリックするだけ）
start.bat 8080         : ポート番号を指定
start.bat --no-open    : ブラウザーを自動で開かない
start.bat cli --help   : CLI のヘルプ
start.bat doctor       : CLI 診断（同じ自動準備）
```

PowerShellでは `& .\start.bat` で同じように起動できます。

引数なしで起動するとWeb UIを立ち上げ、準備が整い次第お使いのブラウザーで
`http://127.0.0.1:8000/` を自動的に開きます。すでに起動中の場合は二重起動せず、
その画面を開くだけです。8000番が別のアプリに使われている場合は空いている番号へ
自動で切り替えて表示します。起動に失敗した場合はウィンドウが閉じずにエラーを表示します。
使用中はターミナルを開いたままにし、終了時はCtrl+Cでサーバーを停止します。
ブラウザーを閉じてもサーバーは動き続けます。

`--repair` / `--update` は、起動中のインスタンスがあると固定環境を壊さないよう、
変更する前に終了を案内して停止します（app.db・data・BOOTH-Reader-Libraryは残ります）。
`start.bat --check` は準備済みかどうかだけを表示し、セットアップは行いません。
`start.bat /?` や `start.bat version` も受け付けます。エラー時は次の操作を日本語で案内し、
同梱物 (vendor/) の破損が疑われる場合は git clone による復元を案内します。

以下の `python cli.py` はCLI構文の説明です。実際のポータブル実行では
`start.bat <command>`（CLIを明示する場合は `start.bat cli <command>`）に置き換えます。
PATH上のPythonへ依存せず、移動後の環境も起動前に検査できます。

## 設定

すべて任意です。指定しなければ既定値で動作します。

| 設定 | 既定値 | 変更方法 |
|---|---|---|
| DB の場所 | `./app.db` | `--db <path>`（サブコマンドの前でも後ろでも指定可） |
| ライブラリの保存先 | `./BOOTH-Reader-Library` | `download` / `web` に `--output-dir` |
| Cookie の保存先 | `./data/cookies.json` | `auth` 系に `--cookie-path` |
| ログレベル | `INFO` | `--log-level DEBUG\|INFO\|WARNING\|ERROR` |
| 並列ダウンロード数 | 3（上限 5） | `download --concurrent 1-5` |
| HTTP User-Agent | 実ブラウザ相当 | 環境変数 `BOOTH_READER_USER_AGENT` |
| 通信リトライ回数 | 3 | コード内で固定（指数バックオフ + 分散付き） |

Cookie・DB・購入物・ブラウザープロフィール・キャッシュはGit対象外です。
任意名のインポートJSONや独自出力・バックアップをリポジトリ内に保存する場合は、除外済みの `.private/` を使ってください。任意のファイル名・外部保存先をすべて自動判別できるわけではありません。

任意名のDB（`.db` / `.sqlite` / `.sqlite3`）とsidecar・バックアップ、Cookieインポート、CSV、ログ、HAR、ローカル監査結果・画面もGitから除外します。Webの入力検証エラーはCookie内容を返さず、例外応答・ジョブの失敗表示も機密値を伏せます。レスポンスには `Cache-Control: no-store` を付けます。
`tools/check_release_hygiene.py --git-only` は追跡・追加候補・到達可能履歴の私用パスを検査します。値を表示せず、内容の秘密情報検査や再配布許諾の証明とは別の検査です。

## 使い方

### Web UIのライブラリ

初回は画面の案内どおり、1) Cookieを登録 → 2) BOOTHと同期 → 3) リストへ分類してダウンロード、の順に進みます。

- **Cookieを登録**：BOOTH / pixivのCookie JSON（配列、または `cookies` 配列を持つJSON・1MB以下）を選びます。登録後は購入一覧の全ページを自動同期します。既存CookieやCLIでのログインも画面を開いたときに検出します。登録済みのCookieを置き換えるときは確認を表示します。
- **全商品を画像で確認**：左側で「すべての商品」「未分類」「マイリスト」を切り替えます。商品名・ショップ名で検索でき、48件ずつページを移動できます。画像を取得できない商品も名前を表示します。
- **リストを作成・追加**：「マイリスト」の `+` で作成し、「商品を追加」から未分類の商品を選びます。別のリストに登録済みの商品は追加できません。移す場合は元のリストから外します。リスト削除は確認後に実行し、商品は未分類へ戻ります。
- **商品の並び順を保存**：各リストで購入順（新しい／古い）、名前順、ショップ順を選べます。変更時に自動保存します。
- **マイリストを並べ替え**：上部の1行バー内で横にドラッグすると、隣のリストと1つずつ滑らかに入れ替わります。マウスを上下に動かしてもリストの高さは固定されます。端ではバーが自動で横スクロールし、マウスを離すと順番を自動保存します。「保存中」→「保存しました」で結果を確認でき、失敗時は元の順番へ戻します。Alt＋左右キーで移動、Escapeでドラッグの取り消しもできます。
- **同期・ダウンロード**：「BOOTHと同期」で再取得できます。ダウンロードは商品カードから開始し、画面下部の「ダウンロード進捗」で確認します。購入が見つからなかった場合は、Cookieの確認を案内します。
- **保存先**：購入ファイルはリポジトリ内の `BOOTH-Reader-Library` に保存されます。画面下部の「ダウンロード進捗」に実際の保存先を表示します。「未完了ファイルを削除」は確認後に `.part` だけを消し、完了済み・展開済みファイルは残します。

購入日をBOOTHから取得できない場合、購入順はBOOTHライブラリの掲載順を使用します。更新時もリストと手動順は保持します。旧版で複数リストに登録した既存の商品は削除せず維持します。

### ログイン

パスワードは保存しません。ブラウザでログインして Enter を押すと、Cookie だけが残ります。

```powershell
python cli.py auth login          # 実ブラウザが開く
python cli.py auth status         # Cookie の状態を確認
python cli.py auth logout         # Cookie を削除
```

`auth login` は保存前にログイン済みかどうかを確認します。確認できなかった場合は
何も保存せず、エラーで終了します。

### 購入一覧

```powershell
python cli.py purchases list --update-db        # BOOTH から取得して DB へ取り込む
python cli.py purchases list                    # DB の内容だけ表示
python cli.py purchases list --csv out.csv      # CSV 出力（BOM 付き、Excel 対応）
python cli.py purchases list --limit 50
```

CSVでは、販売者のタイトルなどが `=` / `+` / `-` / `@` 等で始まる場合、
先頭に `'` を付けてExcelの数式として実行されないようにします。

### 未分類キュー

```powershell
python cli.py unclassified                       # 登録日が新しい順
python cli.py unclassified --sort oldest         # 古い順
python cli.py unclassified --sort name           # タイトル順
python cli.py unclassified --sort shop           # ショップ順
python cli.py unclassified --csv unclassified.csv
```

### 分類

```powershell
python cli.py lists create --name お気に入り
python cli.py lists list
python cli.py lists add    --list お気に入り --item-id 1234567
python cli.py lists remove --list お気に入り --item-id 1234567
python cli.py lists delete --name お気に入り
python cli.py lists sort --list お気に入り --sort name
python cli.py lists reorder --list お気に入り --items '["1234567","7654321"]'
python cli.py lists reorder-lists --lists '[2,1,3]' --json
python cli.py lists library --json
```

`--list` にはリスト名でも ID でも指定できます。`add` は `ON CONFLICT DO NOTHING` を
使うため、同じリストへの再追加は冪等です。別のリストへの重複追加は拒否します。

### ダウンロード

```powershell
python cli.py download --item-id 1234567                  # 1 件
python cli.py download --item-id 1234567 --no-extract      # 解凍しない
python cli.py download --all --concurrent 3               # 全件
python cli.py download --all --force                      # 完了済みも取り直す
python cli.py downloads list                              # 進捗
python cli.py downloads list --status failed
python cli.py downloads cleanup                 # 中断時の .part を削除
```

ダウンロードと未完了ファイル削除はライブラリ単位で排他制御します。
未完了ファイル削除は商品フォルダの `downloads/` 内だけが対象です。
台帳に記録された原本と `extracted/` の展開済みファイルは維持します。
別のダウンロード実行中は拒否されます。`--force` は先頭から取得し、
成功するまで既存の原本を維持します。

**再実行しても再取得しません。** 完了済みのファイルはスキップされ、ファイル名も
変わりません。送信者がファイル名を変更しても URL が同じなら同じファイルを
使い回します。取り直したい場合は `--force` を付けてください（`_2` のような
連番のコピーは作られません）。

保存される構成:

```
BOOTH-Reader-Library/{item_id}_{title}/
  downloads/     原本のファイル
  extracted/     zip を解凍した結果
  meta.json      取得記録（sha256・展開ファイル一覧・取得元 URL）
```

### Web UI

```powershell
python cli.py web --port 8000
# http://127.0.0.1:8000/
```

Web UI の裏側は CLI と同じコードを呼んでいます（`web/cli_bridge.py` を参照）。
ブラウザからのリクエストは既定で `cli.py rpc` という常駐ワーカー経由で処理される
ため、リクエストごとに Python を起動し直すことがありません。

API:

| メソッド | パス | 呼び出す CLI |
|---|---|---|
| GET | `/` | サーバーレンダされた画面 |
| GET | `/purchases` | `purchases list --json` |
| GET | `/unclassified?sort=` | `unclassified --sort s --json` |
| GET | `/downloads` | `downloads list --json` |
| GET | `/lists` | `lists list --json` |
| POST | `/lists` | `lists create` / `add` / `remove` / `delete` |
| GET | `/auth/status` | `auth status --json` |
| POST | `/purchases/update` | `purchases list --update-db --json` |
| POST | `/download` | `download`（バックグラウンド実行） |
| POST | `/downloads/cleanup` | 中断時に残った `.part` の削除 |
| GET | `/health` | プロセス状態と使用中のトランスポート |

### 診断

```powershell
python cli.py doctor
python cli.py doctor --json
python cli.py doctor --cookie-path data\cookies.json   # 別の Cookie を確認
```

依存関係、DB のテーブルと整合性、Cookie、ライブラリの書き込み可否と空き容量を
まとめて確認します。動作しないときは最初にこれを実行してください。
`--cookie-path` を省略すると `data/cookies.json` を確認します。`auth login`
に `--cookie-path` を付けた場合はdoctorにも同じパスを指定してください。

## 使用例

未分類を片付けて、まとめて取得する一連の流れです。

```powershell
python cli.py auth login
python cli.py purchases list --update-db

# タイトルを見ていくつか分類する
python cli.py lists create --name "東方"
python cli.py lists add --list 東方 --item-id 1234567

# 残った未分類だけを確認する
python cli.py unclassified --sort oldest

# まとめて取得する
python cli.py download --all --concurrent 3
python cli.py downloads list --status failed
```

機械取込用に JSON だけを取り出す例:

```powershell
python cli.py unclassified --json | ConvertFrom-Json | Select-Object -ExpandProperty items
```

## 終了コード

すべてのコマンドが同じ規約に従います。

| コード | 意味 |
|---|---|
| 0 | 成功 |
| 1 | 実行時エラー（認証切れ、通信失敗、不正な値） |
| 2 | 使い方エラー（フラグの誤り、排他オプションの違反） |
| 3 | `BOOTH_LAYOUT_CHANGED`（BOOTH 側のマークアップ変更） |
| 130 | Ctrl+C による中断 |

いずれの場合も Python のトレースバックは表示されません。想定外の例外は
`ERROR 予期しないエラーが発生しました: <例外名>: <内容>` として要約されます。

## 更新

先にすべてのBOOTH-ReaderのターミナルでCtrl+Cを押し、CLI・ダウンロードも終了してください。更新前のバックアップは次の手順で作成します。

```powershell
git pull --ff-only                # 個人データを維持してソースを更新
& .\start.bat --update            # 新しいソースを配置後、固定環境へ同期
& .\start.bat --version
& .\start.bat doctor
```

DB とライブラリはそのまま残ります。スキーマの更新は `PRAGMA user_version` によって
前方適用のまま適用されます。**より新しいバージョンで作られた DB を古いバージョンで
開こうとすると、明示的に拒否します**（黙って壊すことはありません）。

ソース更新はGitで行います。ローカルに開発中の変更があって更新できない場合も、変更を破棄する処理は行いません。Gitはクローン・ソース更新・開発用検査に使い、アプリ本体の通常実行には不要です。

### バックアップと復旧

1. 全インスタンスを停止した状態で、`app.db`、存在する `app.db-wal` / `app.db-shm`、`data/`、`BOOTH-Reader-Library/` を一組として、本人だけがアクセスできる別の保存先へコピーします。独自のDB・保存先を指定している場合はそちらも対象です。起動中のDBをエクスプローラーでコピーしないでください。
2. 更新前のアプリの版も控えます。バックアップにCookieを含むため、Gitへ追加したり第三者へ渡したりしないでください。生成環境の `.tools` / `.venv` / `.cache` / `.playwright-browsers` は再生成でき、バックアップ必須ではありません。
3. 復元するときは、同じ版または新しい版を別フォルダーへ用意します。アプリを起動する前に保存した一組を配置し、`start.bat doctor --json` とリスト・購入物の表示を確認します。元のフォルダーとバックアップは、復元を確認するまで残します。
4. DB破損時は破損ファイルをその場で初期化せず、上記の別フォルダーで復元します。正常なバックアップがない場合、BOOTHの再同期だけでは手動分類や並び順は戻りません。`--repair` は実行環境の修復であり、DBや購入ファイルの復元ではありません。

DB移行は前方向だけです。旧アプリへ戻す場合は、**その旧版の時点のバックアップ**も一緒に使用します。新しいDBを旧版向けに書き換える手順はありません。バックアップの保持数・期間は利用者が決め、復元を確認した後に不要な古いコピーを削除します。

## アンインストール

```powershell
python cli.py auth logout           # Cookie を削除
```

残りはフォルダごと削除するだけです。`.venv`・`.tools`・ブラウザー・
キャッシュなどのプロジェクト専用環境もすべてフォルダ内にあり、
PC本体へのインストールは行っていないため、本体側の掃除は不要です。

購入物や分類を残す場合は、削除前に上記のバックアップを別フォルダーへ保存してください。`app.db`・`data/`・`BOOTH-Reader-Library/` を削除すると、購入履歴・分類・Cookie・ダウンロード済み原本も失われます。

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| コマンドやフラグを間違えた | エラーに日本語で案内が出ます。`start.bat help` でコマンド一覧、Web UIは引数なしの `start.bat` です |
| `--repair` / `--update` が「起動中です」と表示する | BOOTH-Readerを起動しているウィンドウでCtrl+Cを押して終了し、もう一度実行してください（データは残ります） |
| `BOOTH_PREREQUISITE_MISSING` | 必要な部品が未導入です。メッセージ内にインストールコマンドが示されます |
| `BOOTH_SCHEMA_TOO_NEW`（exit 1） | `app.db` が新しいバージョンで作られたものです。BOOTH-Reader を更新してください |
| `doctor` が FAIL を表示する | 表示された対象名を確認してください（`browser:webview2` は同梱ブラウザーの展開が必要です。`start.bat --repair` で復元されます） |
| `doctor` が `cookies` を「なし」と表示する | 確認先は `data/cookies.json` です。`--cookie-path` を付けた場合は同じパスを指定してください |
| 初回準備で「同梱物 (vendor/)」のエラーが出る | リポジトリの取得が不完全です。リポジトリを `git clone` し直してください。`app.db`・`data`・`BOOTH-Reader-Library` は削除しないでください |
| `auth login` が「ログインページを開けませんでした」と表示する | 通信環境（回線・DNS・プロキシ・ファイアウォール）の問題です。ブラウザの再インストールは不要です |
| `BOOTHへのログインが必要です`（exit 1） | `start.bat auth login` で再ログイン |
| `BOOTH_LAYOUT_CHANGED`（exit 3） | BOOTH の HTML が変わった可能性があります。`git pull` 後に `start.bat --update` で更新してください。更新しても直らない場合は開発側のセレクタ更新が必要です（`booth-manager` / `BoothPM-SDK` 参照） |
| `一覧取得に失敗しました`（exit 1） | ネットワーク断またはタイムアウトです。回線を確認して再実行してください（自動リトライ済み） |
| `database is locked` | 同時実行を避けてください。WAL と busy_timeout により大半は解消します |
| 日本語ヘルプが化ける | `.bat` 経由で起動してください。子PythonはUTF-8で起動します |
| `.part` ファイルが残っている | 通信断で途中まで取得できた状態のまま中断したものです。`download` を再実行すると続きから取得します |
| 展開時に `BOOTH_LIMIT_EXCEEDED` | zip bomb を検出しました。`extracted` ではなく `downloads` の原本を確認してください |
| WebUI が開かない | `start.bat --check` で準備状態を確認し、必要なら `start.bat --repair` を実行してください |

ログの機密性は既定で `core/logging_setup.py` のフィルタが保証します。
`token=`、`password=`、`Authorization:` などの値は伏せ字化されます。

## 制限事項

- FBX プレビューおよび VCC 連携には対応していません
- 常駐監視と自動振分は行いません（登録は手動です）
- Mac および Linux は非対応です（Windows 専用）
- BOOTH のマークアップ変更によって動作しなくなる可能性があります。その場合は明示的なエラーになるため、セレクタを更新してください
- 取り込み・展開には安全のための上限があります。超えた場合は黙って切り捨てず、明示的にエラーになります
  - 1 商品あたりのダウンロードリンク: 64 件（超過時は `BOOTH_LIMIT_EXCEEDED`）
  - 1 回に取り込む購入件数: 20,000 件・200ページ（超過時はDBを更新せず明示的に停止します。`rel=next` のページリンクに対応）
  - zip 展開: エントリ 50,000 件・展開後 8 GiB・圧縮比 200:1（超過時は `BOOTH_LIMIT_EXCEEDED`）
- **実BOOTHアカウントでのログインから購入取得・ダウンロードまでの通し検証は今回未実施です。** 自動テストは合成Cookie・モック・ローカルHTTPサーバーで、再開、破損検出、zip bomb、並列書き込み競合などを検証します。
- 同時ダウンロード数の上限 5 は、サーバー負荷に配慮するための固定値です

## ライセンス

- 本体: [MIT License](LICENSE)
- 依存ライブラリのライセンス: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- Microsoftコードの利用条件・データ通知: [THIRD_PARTY_TERMS.md](THIRD_PARTY_TERMS.md)（Web UIの案内から原文も読めます）
- 配布ライセンス判定: [license-audit/28-clone-distribution-followup.md](license-audit/28-clone-distribution-followup.md)
- 変更履歴: [CHANGELOG.md](CHANGELOG.md)
- 検証記録: [VERIFY_LOG.md](VERIFY_LOG.md)
- 最終配布準備レポート: [audit/18-clone-distribution-followup.md](audit/18-clone-distribution-followup.md)

## 開発・配布前の検証

固定環境は `start.bat` で準備します（初回起動時に自動判定）。配布用ZIP・wheel・sdistは生成しません。

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m ruff check .
& .\.venv\Scripts\python.exe -m ruff format --check .
& .\.venv\Scripts\python.exe -m mypy
& .\.venv\Scripts\python.exe -m pip check
& .\.venv\Scripts\python.exe tools/check_release_hygiene.py --git-only
& .\.venv\Scripts\python.exe tools/check_license_evidence.py
& .\.venv\Scripts\python.exe tools/vendor_payload.py verify
& .\.venv\Scripts\python.exe tools/verify_clone.py
& .\.venv\Scripts\python.exe tools/check_distribution.py
```

`check_distribution.py` は、現在のGit候補が監査済みの内容と一致するか確認します。ファイルの変更・追加・削除で判定が古くなった場合は、変更範囲の調査・検証後に `license-audit/release-gate.json` の証拠と入力ハッシュを更新します。ハッシュの更新だけではライセンス確認の代わりになりません。

本体の入力ハッシュはGit属性に従って改行を正規化します。第三者原文・対応ソース・取得した一次証拠は改行変換を禁止し、元バイトのハッシュを維持します。クローン検証で、元の候補とチェックアウト後の全入力の一致も確認します。

GitHub Actionsも同じ品質・プライバシー・ライセンス・クローン検証を行います。アップロードするのは合成テストの結果だけで、アプリの配布物や私用データはアップロードしません。
