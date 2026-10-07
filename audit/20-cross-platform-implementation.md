# Mac・Windows対応の実装と検証（2026-10-06）

**更新（2026-10-06）**: この記録の「公開前の残課題」（Chrome再配布許諾・配布検査BLOCKED）は、後続の [audit/21](21-portable-distribution-1.1.0.md) で解消済みです（Mac用Chrome payloadを除外し本体MITの自作WebKitホストへ変更、配布ゲートを再固定）。最新の判定は audit/21 と `audit/release-checklist-current.md` を参照してください。

対象は開発版`1.1.0.dev0`です。Windows x64とApple Silicon Macを追加対応し、同梱物からのオフライン準備・修復と、フォルダー内への保存を維持しました。起動手順と構成は[CROSS_PLATFORM.md](../CROSS_PLATFORM.md)に記載しています。

## 実装

- OS別のmanifest・Python/venv/Nodeパス・固定lock・vendor復元を実装。
- Macの`start.sh`、`start.command`、OS標準ツールだけのbootstrapを追加。
- Macは公式DMG由来の署名付きChromeを使用。Google Developer IDとApple公証を確認し、署名を変更せず同梱。
- ダウンロードと修復の排他制御を両OSへ対応。
- DB v5へ追加移行。旧記録を保持し、ライブラリ基準の新しいパスと旧Windows/POSIXパスを解決。
- Unicode正規化による取得名・ZIP展開先の衝突を防止。
- Mac用CI、原文通知182件と取得元・ハッシュ・署名の証拠を追加。

## 検証結果

| 確認 | 結果 |
|---|---|
| Windowsの全テスト | 457 passed |
| Mac実機（arm64・macOS 27.0.1）の全テスト | 453 passed、Windows専用APIの4件はskip |
| Ruff・format・mypy | 両OSで合格 |
| pip check | 両OSで合格 |
| 両ターゲットのvendor整合性 | 分割片・連結内容・lockを検証し合格 |
| ポータブル静的監査 | 両OSで18/18合格 |
| Git候補の私用パス検査 | 追跡・追加候補とも0件。内容の秘密スキャンとは別の検査 |
| 保存済みライセンス・対応ソースの整合性 | 原文ハッシュの照合は合格。Mac追加物の配布条件の承認ではない |

Macの独立コピーでは、生成環境なし・無効proxyからのオフライン初期化（11.96秒）、CLI JSONと日本語引数、実ブラウザー1440/768/390px、Web起動・終了、日本語/空白パスへの移動後の再構築、DB保持、署名不一致からの修復、起動中の修復拒否、再起動が合格しました。独立コピーは削除済みです。

MacへのSSH検証後、専用の検証フォルダー全体を削除しました。今回所有したプロセス0件・マウント0件を確認し、別のSSH接続でも検証フォルダーが存在しないことを確認しました。OSへのPython・Chrome等のインストールは行っていません。

既存の第三者TestClient非推奨警告は両OSで1件ずつ発生しています。

## 公開前の残課題

Mac用Chromeの再配布許諾、追加ネイティブ依存物の通知・対応ソース義務、候補全体の再監査は未完了です。配布検査は意図どおり`license clearance BLOCKED`で停止しました。

macOS 14・Windows 10の実機確認、Finderからの実クリック起動、実BOOTHの認証から購入ファイル取得までの通し確認、長時間運転、全面的なネイティブアクセス監査は未実施です。Git公開時にはshell/command入口の実行属性`100755`も保持する必要があります。今回Git index・コミット・pushは変更していません。
