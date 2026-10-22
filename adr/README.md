# adr

決定の記録（Architecture Decision Record）。何をなぜ決めたかを残す。番号は詰め直さない。
いまの姿は [docs/](../docs/README.md) に書き、ここには経緯と理由を書く。

| 番号 | 決定 | 状態 |
|---|---|---|
| [0001](0001-response-time-target.md) | 応答時間の目安を30秒に緩める | 採用 |
| [0002](0002-streaming-transcription.md) | 音声の質問はストリーミングで文字にし、録音は PCM にする | 採用 |
| [0003](0003-conversation-context.md) | 会話の文脈は実行環境のセッションに持ち、15分で区切る | 採用 |
| [0004](0004-background-processing.md) | 背面での回答待ちと読み上げは、JS とフォアグラウンドサービスで行う | 一部置き換え（0005） |
| [0005](0005-native-android-app.md) | App を React Native からネイティブ（Kotlin）に移し、新しいリポジトリで作る | 採用 |
| [0006](0006-background-ride-recording.md) | 走行中のルートは、前面サービスの中で Fused の位置を受けて端末の DB に書く | 採用 |
| [0007](0007-stay-home-after-ending-a-ride.md) | 走行を「終了して保存」したあとは、ホームに残る | 採用 |
| [0008](0008-ask-only-while-recording.md) | 質問は走行の記録中だけ受け、日ごとの振り返りをやめる | 採用 |
| [0009](0009-keep-deletion-marks-in-the-cloud.md) | 削除はクラウドにも跡を残し、跡のある記録への置き直しを断る | 採用 |
| [0010](0010-read-the-cloud-only-when-taking-over.md) | クラウドの記録は引き継ぎのときだけ読み、新しいほうを勝たせて突き合わせる | 採用 |
