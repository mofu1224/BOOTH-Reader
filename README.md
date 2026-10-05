# BOOTH-Reader

BOOTH購入品の取得・ダウンロード・ZIP展開・分類を管理する個人向けツールです。未分類の商品をリストへ追加し、全商品はライブラリで確認できます。

## インストール・起動

**GitHubからクローンし、`start.bat` をダブルクリック。** 初回準備・復旧・ブラウザー起動は自動です。Pythonの導入、Git LFS、追加ダウンロードは不要です。

```powershell
git clone https://github.com/mofu1224/BOOTH-Reader.git
# クローン先で実行
& .\start.bat
```

| コマンド | 用途 |
|---|---|
| `start.bat` | Web UI（既定: `http://127.0.0.1:8000/`） |
| `start.bat 8080` | ポート指定（`--port 8080` も可） |
| `start.bat --no-open` | ブラウザーを自動で開かない |
| `start.bat --check` | 準備状態の確認のみ（0=準備済み） |
| `start.bat --repair` | 実行環境を修復（データは保持） |
| `start.bat --skip-browser` | ブラウザー準備を省略 |
| `start.bat doctor` | 環境・DB・Cookie・容量を診断 |
| `start.bat help` | CLIヘルプ（`/?` も可） |
| `start.bat version` | バージョン表示 |

起動済みなら既存の画面を開き、ポート使用中なら空き番号を使います。ターミナルは開いたままにし、**Ctrl+Cで終了**してください。ブラウザーを閉じてもサーバーは停止しません。起動失敗時はエラーを表示して待機します。

CLIも `start.bat <command>` で実行できます（`start.bat cli <command>` も可）。PowerShellでは `& .\start.bat ...` を使います。

## 動作環境

- Windows x64・書込み可能なローカルディスク。Windows 11で検証、Windows 10 build 17763以降は未検証です。
- 起動・環境準備はオフライン可。BOOTH/pixiv認証、同期、購入ファイル・商品画像の取得は通信が必要です。
- Mac/Linux、ARM64/x86、UNC/NASからの直接実行、公開サーバー・複数ユーザー運用は対象外です。NASはバックアップ用に使います。
- 同梱WebView2のSmartScreenは有効で、Microsoftへの情報送信があります。[利用条件・データ通知](THIRD_PARTY_TERMS.md)を確認してください。

同梱物・保存先・移動時の詳細は [PORTABLE.md](PORTABLE.md)。

## 使い方

**Cookie登録 → BOOTHと同期 → 分類・ダウンロード** の順に進みます。

画面右上の **JA / EN** で日本語・英語を切り替えます。設定はブラウザーに保存します。ログ・CLI・起動出力は英語です。

- **Cookie**：BOOTH/pixivのCookie JSON（配列、または `cookies` 配列を持つJSON・1MB以下）を登録すると全ページを同期します。CLIでのログインも検出します。置換時は確認があります。
- **商品**：「すべての商品」「未分類」「マイリスト」を切替。商品名・ショップ名で検索し、48件ずつ表示します。画像がない商品も名前で確認できます。
- **分類**：「マイリスト」の `+` で作成し、「商品を追加」から未分類を選びます。別リストへ移すには元のリストから外します。リスト削除で商品は未分類に戻ります。
- **順番**：購入順・名前順・ショップ順を自動保存。マイリストは横ドラッグまたはAlt＋左右で並べ替え、Escapeで取り消せます。端では自動スクロールし、保存失敗時は元に戻ります。
- **同期・取得**：同期ボタンで再取得、商品カードからダウンロード。画面下部に英語ログと保存先を表示します。購入0件時はCookieを確認してください。
- **未完了ファイル**：確認後に `.part` だけを削除します。完了原本・展開済みファイルは保持します。

購入日が取得できない場合はBOOTH掲載順を使います。同期後も分類・手動順を保持し、旧版の複数リスト登録も維持します。パスワードは保存しません。

### CLI

```powershell
# 認証（ブラウザーでログイン後、Enter。認証確認後にCookieだけ保存）
& .\start.bat auth login
& .\start.bat auth status
& .\start.bat auth logout

# 購入一覧・未分類
& .\start.bat purchases list --update-db
& .\start.bat purchases list --csv .private\out.csv
& .\start.bat purchases list --limit 50
& .\start.bat unclassified --sort oldest
& .\start.bat unclassified --json | ConvertFrom-Json | Select-Object -ExpandProperty items

# 分類（--list は名前またはID。再追加は冪等、別リストへの重複追加は拒否）
& .\start.bat lists create --name お気に入り
& .\start.bat lists list
& .\start.bat lists add --list お気に入り --item-id 1234567
& .\start.bat lists remove --list お気に入り --item-id 1234567
& .\start.bat lists delete --name お気に入り
& .\start.bat lists sort --list お気に入り --sort name
& .\start.bat lists reorder --list お気に入り --items '["1234567","7654321"]'
& .\start.bat lists reorder-lists --lists '[2,1,3]' --json
& .\start.bat lists library --json

# 取得・進捗・診断
& .\start.bat download --item-id 1234567
& .\start.bat download --all --concurrent 3
& .\start.bat download --all --force
& .\start.bat downloads list --status failed
& .\start.bat downloads cleanup
& .\start.bat doctor --json
```

一覧の `--update-db` なしはDB照会のみ。未分類の `--sort` は `newest`（既定）/ `oldest` / `name` / `shop`、CSV出力も可能です。CSVはUTF-8 BOM付きで、数式として実行される値に `'` を付けます。

### ダウンロード

完了ファイルは再取得しません。同じURLなら名前変更後も再利用します。`--force` で取り直し、`--no-extract` でZIP展開を省略できます。

`.part` へ書込み、サイズ検証後に原本を置換します。再開はETag/Last-ModifiedとIf-Rangeで同版を確認し、確認できなければ先頭から取得します。失敗時は既存原本を保持し、一部失敗・破損ZIPも失敗として記録します。

取得と未完了ファイル削除はライブラリ単位で排他制御。削除対象は商品フォルダーの `downloads/` 内だけで、台帳の原本と `extracted/` は保持します。

```text
BOOTH-Reader-Library/{item_id}_{title}/
  downloads/   原本
  extracted/   ZIP展開結果
  meta.json    SHA-256・展開一覧・取得元URL
```

### 設定

すべて任意です。

| 設定 | 既定値 | 指定 |
|---|---|---|
| DB | `app.db` | `--db <path>`（コマンド前後どちらでも可） |
| 購入ファイル | `BOOTH-Reader-Library/` | `download` / `web --output-dir` |
| Cookie | `data/cookies.json` | `auth` / `doctor --cookie-path` |
| ログ | `INFO`・stderr | `--log-level DEBUG\|INFO\|WARNING\|ERROR` |
| 同時取得 | 3（上限5） | `download --concurrent 1-5` |
| User-Agent | 実ブラウザー相当 | 環境変数 `BOOTH_READER_USER_AGENT` |
| 再試行 | 3回 | 固定・指数バックオフ＋分散 |

独自Cookieを使う場合、`doctor` にも同じ `--cookie-path` を指定します。`--json` のstdoutはASCII-safe JSONのみで、ログ・進捗はstderrです。ログのトークン・認証値は伏せ字にします。

### Web API

Web UIは `web/cli_bridge.py` から常駐CLIワーカー（`cli.py rpc`）を呼びます。loopback限定でHost・同一オリジンを検証し、応答は `Cache-Control: no-store` です。

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/` | 画面 |
| GET | `/purchases`, `/unclassified?sort=`, `/downloads`, `/lists` | 一覧 |
| GET | `/auth/status`, `/health` | 認証・プロセス・ジョブ状態 |
| POST | `/lists` | 作成・追加・除外・削除 |
| POST | `/purchases/update`, `/download`, `/downloads/cleanup` | 同期・取得・未完了削除 |

### 終了コード

| コード | 意味 |
|---|---|
| 0 | 成功 |
| 1 | 認証・通信・実行エラー |
| 2 | 引数・使い方エラー |
| 3 | `BOOTH_LAYOUT_CHANGED`（HTML変更） |
| 130 | Ctrl+C |

エラーは原因を要約し、トレースバックを表示しません。

## 更新

全インスタンス・CLI・ダウンロードを停止し、[バックアップ](#バックアップと復旧)後に更新します。

```powershell
git pull --ff-only
& .\start.bat --update
& .\start.bat --version
& .\start.bat doctor
```

DB・購入ファイルは保持します。DB移行は前方向のみで、新版DBを旧アプリで開くと拒否します。Gitは取得・更新・開発検査に必要ですが、通常実行には不要です。更新時もローカル変更を自動破棄しません。

### バックアップと復旧

1. **全インスタンスを停止**し、`app.db`、存在する `app.db-wal` / `app.db-shm`、`data/`、`BOOTH-Reader-Library/` を一組で別の私用保存先へコピーします。独自DB・保存先も含め、アプリの版を控えます。
2. 同じ版または新版を別フォルダーへ用意し、起動前に一組を復元します。`start.bat doctor --json` と分類・購入物の表示を確認するまで元データとバックアップを保持します。
3. 旧版へ戻すには**その旧版時点のバックアップ**を使います。DB破損時も別フォルダーへ復元してください。正常なバックアップがなければ、BOOTH再同期で手動分類・順番は戻りません。

バックアップにはCookieを含むため、Git追加・第三者への提供を避けます。生成環境は再構築可能です。`--repair` は環境修復で、DB・購入物の復元ではありません。バックアップの保持数・期間は利用者が決めます。

## アンインストール

停止後、必要なデータをバックアップしてフォルダーを削除します。Cookieだけ消す場合は `start.bat auth logout`。フォルダー削除でDB・分類・Cookie・購入原本・専用環境も消えます。

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| 引数エラー | `start.bat help`。Web UIは引数なし |
| 更新・修復時に「起動中」 | 起動ウィンドウでCtrl+C後に再実行 |
| vendor欠損・破損 | 別フォルダーへ再クローン。`app.db`・`data/`・購入物は保持 |
| `BOOTH_PREREQUISITE_MISSING` / Webが開かない | `start.bat --check` → `start.bat --repair` |
| `BOOTH_SCHEMA_TOO_NEW` | アプリを更新 |
| `doctor` FAIL | 表示された対象を確認。ブラウザーは `--repair` で復元 |
| Cookieなし・認証切れ | Cookieを登録、または `start.bat auth login`。独自パスも確認 |
| ログインページ・一覧の取得失敗 | 回線・DNS・プロキシ・ファイアウォールを確認して再実行 |
| `BOOTH_LAYOUT_CHANGED` | 更新後も続く場合はセレクタ修正が必要 |
| `database is locked` | 同時実行を避ける（WAL・busy_timeout対応） |
| 文字化け | `start.bat` 経由で起動 |
| `.part` が残る | 同じdownloadを再実行 |
| 展開時の `BOOTH_LIMIT_EXCEEDED` | `downloads/` の原本を確認 |

## 制限事項

- FBXプレビュー・VCC連携・常駐監視・自動分類には非対応です。
- HTML解析のためBOOTHの構造変更で停止します。上限超過も明示エラーとなり、購入一覧はDBを更新しません。
- 上限：64リンク/商品、20,000購入・200ページ/同期、ZIP 50,000エントリ・展開後8GiB・圧縮比200:1。
- **実BOOTHのログイン→購入取得→DL通し、Windows 10・別PC・長時間運転は未検証です。** 自動試験は合成データ・モック・ローカルHTTPで実施しています。

## 配布・ライセンス

配布は**Gitクローン**です。利用中フォルダーには個人データがあるため第三者へ渡さないでください。Cookie・DB・購入物・プロフィール・CSV・ログ等はGit対象外です。任意名の私用出力は `.private/` へ保存します（未知のファイル名や外部保存先は自動判別できません）。

- [本体MIT](LICENSE)・[第三者通知](THIRD_PARTY_NOTICES.md)・[Microsoft利用条件](THIRD_PARTY_TERMS.md)
- [対応ソース](SOURCE_OBLIGATIONS/README.md)・[ライセンス配布判定](license-audit/28-clone-distribution-followup.md)
- [製品の判定条件・未確認範囲](audit/19-release-scope.md)・[前回クローン検証](audit/18-clone-distribution-followup.md)
- [変更履歴](CHANGELOG.md)・[検証ログ](VERIFY_LOG.md)

ライセンスゲートの合格と製品全体の完成判定は別です。第三者原文は `THIRD_PARTY_LICENSES/` に保持します。

## 開発・配布前の検証

`start.bat` で固定環境を準備し、次を実行します。配布ZIP・wheel・sdistは生成しません。

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

ゲートは追跡・追加候補の全入力を照合し、変更後の古い判定を拒否します。影響を検証して `license-audit/release-gate.json` を更新してください。ハッシュ更新だけではライセンス確認になりません。

本体の改行はGit属性で正規化し、第三者原文・対応ソース・一次証拠は元バイトを保持します。クローン検証で全入力の一致を確認します。私用パス検査は内容の秘密スキャンと別です。GitHub Actionsも同じ検査を行い、合成試験結果だけをアップロードします。
