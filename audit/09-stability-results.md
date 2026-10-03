# 安定性・障害耐性

`tools/audit_stability.py --out audit/stability-final.json` を隔離DBで実行。

- **8スレッド、1,000照会＋40分類リスト書込、2.77秒、worker再起動0**。
- Windows process handleはGC前157→169、終了executorを解放して同条件GC後**157→158**。最初の判定はexecutor保持を測って失敗したため、保持対象を調査し、fixtureを解放した後の値と生の値を両方記録した。
- active SQLite `BEGIN IMMEDIATE` 中に子プロセスを強制kill。未commit行は残らず、既存データ・8リストを保持。`integrity_check`/FK検査合格。
- 既存5並列DB書込、200回open/close、繰返しCLI、worker kill後回復も全体試験に含む。
- Webの同一ライブラリ重複DL/cleanup拒否、CLIとのprocess排他、job失敗のhealth表示、finally解放を確認。
- 通信断、HTTP503/403/404、validator変化、ZIP CRC破損、migration fault、Cookie ACL失敗は隔離試験で確認。
- 書込時の権限不足（errno13）・容量不足（errno28）をfault injectionし、既存公開ファイルが維持され、明示エラーになることを確認。最終310テストに含む。

これは短時間の有界stressであり、数時間・数日のsoakを実施したとは報告しない。実ディスクの容量枯渇、電源断、BOOTHサービス停止は意図的に発生させていない。
