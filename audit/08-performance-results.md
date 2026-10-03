# 性能測定

同じWindows11/CPython3.12.13、同じ依存、同じ2,000件HTML/隔離DBを使用。`tools/audit_probe.py benchmark --out <json>` で再現できる。parser3回、warm worker/API7回、全標本と中央値をJSONへ保存。単位ms。

| 対象 | 開始時 | 正確性修正直後 | 最終 |
|---|---:|---:|---:|
| HTML parser 2,000件 | 139.73 | 194.73 | **130.45** |
| warm worker 200件 | 3.51 | 3.56 | 3.49 |
| GET /purchases 200件 | 6.80 | 6.85 | 6.42 |
| GET / | 15.54 | 15.55 | 14.98 |

cProfileでparser3回1.876秒、CSS select系0.780秒を確認し、同じrowの注文/productリンクを一度だけ走査する形へ変更した。正確性修正後の解析コストを減らし、開始時水準へ戻した。短い標本の小差を保証された改善率とは表現しない。

記録: `performance-baseline.json`, `performance-before-optimization.json`, `performance-final.json`。プロファイル下の時間と非プロファイルの測定値を混同しない。実BOOTH回線・CDN速度、巨大な実購入アーカイブの速度は未測定。

## 保存先解決の追加測定（BR-A15）

1,000個の無関係フォルダを持つ同じ隔離libraryで、新規商品の保存先解決を7回測定。中央値 **24.25ms→0.541ms**。実際の無関係directory stat回数は **1,000→0回**。この処理を新規商品ごとに繰り返す初回batchの二次的なI/O増加を除いた。

再現: `tools/audit_probe.py paths --out <json>`。証拠: `path-performance-baseline.json`, `path-performance-final.json`、`test_audit_performance.py`。
