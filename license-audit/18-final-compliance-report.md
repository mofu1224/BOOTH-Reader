# 最終コンプライアンス報告

配布対象はこのフォルダー全体・リポジトリそのものです。source-online限定のREADY FOR RELEASE判定はユーザー指示による構成撤回で取り下げました。
現在の全体判定は **BLOCKED**。以下は既存のバイナリ同梱候補の集計であり、フォルダー全体の監査完了を意味しません。
生成元の追加証拠と撤回経緯は `26-public-source-release.md`、全体の残課題は `19-release-readiness.md` を参照してください。

監査日: 2026-10-02。判定: **BLOCKED**。

**正式配布はBLOCKED**。通知追加とcandidate integrityは、権利/条件閉包の完了ではない。

```json
{
  "Total Components": 68,
  "First-party Components": 0,
  "Third-party Components": 67,
  "Generated Components": 0,
  "Derived Components": 0,
  "Unknown Components": 1,
  "count_scope": "62 wheels + 6 aggregate audit boundaries; internal unique total NOT VERIFIED",
  "PASS": 0,
  "PASS WITH OBLIGATIONS": 0,
  "ACTION REQUIRED": 0,
  "REPLACEMENT REQUIRED": 0,
  "REMOVAL REQUIRED": 0,
  "REIMPLEMENTATION REQUIRED": 0,
  "NOT VERIFIED": 68,
  "BLOCKED": 0,
  "Final Distribution Audited": "candidate integrity only; license closure BLOCKED",
  "SBOM Verified": "PARTIAL",
  "Required Notices Included": "discovered originals included; completeness NOT VERIFIED",
  "Required Licenses Included": "discovered originals included; completeness NOT VERIFIED",
  "Source Obligations Satisfied": false,
  "Secrets Scan Passed": "scoped rule scan only; false positives reviewed in security report",
  "Clean Environment Test Passed": "independent-folder smoke only; full clean OS/service flow NOT VERIFIED",
  "Release Status": "BLOCKED"
}
```

FIRST-PARTY=0は著作権不在を意味せず、この監査基準で独立作成を証明できていないという意味。
未知の内部コンポーネント数を総数へ捏造しない。全ファイル数は別のinventoryに記録。
