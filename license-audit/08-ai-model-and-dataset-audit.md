# AI・生成物監査

監査日: 2026-10-02。判定: **BLOCKED**。

本体がAIモデルやモデル重みをロードする依存/設定は検出していない。
既存コードのエージェント生成は過去記録から確認できるが利用サービス/モデル/当時規約/入力の外部コードが未記録。
今回の監査コード/文書はOpenCode経由openai/gpt-6.1-sol生成。これも著作権上の独自性・入力履歴・サービス契約を証明しない。
lockはgen_lock.py生成、wheelは各upstreamビルド、stdlib bytecode/venvはCPython生成。
certifi CAデータ、license-expression SPDXデータ、Pygments文法/例示データ、Chromeロケールをデータ監査へ含める。
Output Termsとモデルライセンスを混同せず、情報のない生成物をFIRST-PARTY/PASSにしない。
