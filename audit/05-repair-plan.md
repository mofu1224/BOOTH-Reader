# 修正計画

1. 全体ソース・設定・テスト・実ファイル分類を完了しBaselineを保存（完了）。
2. BR-A01からA11まで1単位ずつ、変更前回帰→失敗確認→根本修正→対象/関連テスト→記録。優先は情報漏えい・誤成功・破損・主要UI。
3. 性能: parserとwarm worker/APIを同条件で比較。メタデータ誤割当の修正で共有祖先の繰り返し走査も減らす。効果が無い大規模最適化を導入しない。
4. 最終gate: 全pytest、ruff check/format、mypy、compileall、pip check、installed/locked vulnerability audit、portable audit、実ブラウザ、isolated wheel/sdist/launcher clean install、RC、並行/障害復旧。
5. 再調査: データ・Cookie・HTTP・DL結果/名前/part・UI/state・worker・移行・配布収集を再確認。新規問題はIDを追加して修正する。
6. 最終: 07〜12に実際の試験結果・性能・障害・security・品質判定・外部素材/依存/対応環境/ビルド手順を記録。

完了条件: 修正可能な既知高重大問題を残さない。未検証実環境は検証済みと表現しない。新依存は既存/stdlibで不足がある場合のみ。
