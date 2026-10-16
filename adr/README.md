# adr

決定の記録（Architecture Decision Record）。何をなぜ決めたかを残す。番号は詰め直さない。
いまの姿は [docs/](../docs/README.md) に書き、ここには経緯と理由を書く。

| 番号 | 決定 | 状態 |
|---|---|---|
| [0001](0001-response-time-target.md) | 応答時間の目安を30秒に緩める | 採用 |
| [0002](0002-streaming-transcription.md) | 音声の質問はストリーミングで文字にする | 採用（スパイクで確認中） |
| [0003](0003-conversation-context.md) | 会話の文脈は実行環境のセッションに持ち、15分で区切る | 採用 |
