# GitHub issue の判定

この文書は、GitHub の issue そのもの（観点 I）を見た結果です。open の issue が、いまのコードと本文で成り立っているか。closed の issue が、閉じた理由のとおり直っているか、再発していないか。件数は Medium 1・Low 5（計 6 件）です。
個々のコードや文書の不具合は、ほかのファイルが扱います。ここには、issue を開き直す・書き直す・新しい issue にまとめる、という issue の扱いに関わる指摘だけを置きます。
R12-01 は、同じ根の R8-02（同じ会話への呼び出しの重なり）をまとめたもの、R12-02 は同じ根の R7-16（`headingSample` の古さの境目の揺れ）をまとめたものです。

## 判定の一覧

| ユニット | 番号 | 題 | 判定 | 理由の一行 |
|---|---|---|---|---|
| Android | #94 | RideForegroundServiceTest の keepAlive のテストがまれに落ちる | 残す | テストも `onStartCommand` の後回し（`RideForegroundService.kt` 82〜96行）もそのまま。本文は見出しどおりで単独で直せる。扱う時期も妥当 |
| Backend | #28 | 古い形の方位の材料（headingSample）の受け口を外す | 書き直す（まとめる: R7-16・`_note`/`_offline` の2か所・R2-11 の `SyncPlan` の重複） | 前提はいまも成り立つが、本文が Backend の3つの受け口しか挙げず、Android 側（`ApiClient.HeadingSample`・Room の `sample*` 列）と文書（07 UC-5・07a・07b §4・08b §2・両 README）を落としている（R12-02） |
| Agent | #8 | AI の費用を下げる検討 | 書き直す（まとめる: R5-03・R5-04・R5-05・R5-15） | モデルを変える以外の、答えの質に効かない手（キャッシュ・不要なツール）が対応案に無い。扱う時期が「気になったとき」であいまい（R12-03） |
| Android | #44 | 会話の詳細の小さな地図を縦に動かせず、ちらつきうる | 問題なし（Info） | 本文の扱う時期「実機で気にならなければ閉じる」どおり、利用者の判断を書いて閉じている。直していないので閉じた理由は NOT_PLANNED のほうが実態に合うが、変えなくてよい |
| Backend | #5 | 使用量のプランの上限（1日3000回）は全員の合計 | 問題なし | 前提（身内でほぼ一人。US-E-06.009）は変わっていない。`template.yaml` 21行の `DailyQuota` は引数のまま。利用者が増えたら見直す、で足りる |
| Agent | #6 | 同じ会話への同時の呼び出しで、片方の往復が履歴から消える | 再び開く | 閉じた理由「回答待ちのあいだは次の質問を始めない」が、待ちのあいだの取り消し（Android #30）と 120 秒の時間切れで成り立たない（R12-01） |
| Agent | #11 | 「調べきれませんでした。」を履歴に残すと、次もあきらめやすいかも | 問題なし | ログで `limit_turns` が0件と確かめて閉じ、開き直す条件も書いてある。`handler.py` 105行の履歴への追記は閉じたときのまま |
| Backend | #3 | SQS への送信に失敗すると JSON でない 502・pending のまま | 問題なし（R4-04・R7-12 とまとめて新しい issue） | `POST /asks` は直っていてテストもある（`tests/test_ask.py` 107行）。`/transcriptions` は #3 より後（`ffff268`、2026-10-21）に足されたが #3 の本文は `ask.py` だけが範囲。再発でなく取りこぼし（R12-04） |
| Backend | #17 | 地点メモの PUT が跡があっても住所を引き、方位を固定しない | 問題なし（R4-05 の出どころに #17 を書く） | 2点とも直り、テストもある（`tests/test_notes.py` 143・154行）。残る結果整合の読み出し（`store.get_note`、256〜258行）は #17 の範囲外の新しい穴（R12-05） |
| Backend | #18 | 削除と書き込みのトランザクションが重なると 5xx・rideId を結果整合で読む | 問題なし（R4-06 の出どころに #18 を書く） | 2点とも直り、テストもある（`tests/test_store.py` 110・158行）。削除の送り直しで跡の `rideId` が消えるのは別の経路（R12-05） |
| Backend | #4 | 会話の ID がユーザーと結び付いていない | 問題なし | `lib/agent.py` 19〜23行でユーザー名と会話の ID のハッシュにしている。`tests/test_agent.py` 132〜135行で別のユーザーが別のセッションになることを確かめている |
| Android | #1 | マイクが使用中だと空の音声を送る | 問題なし（回帰のテストは R1-06 で補う） | `PcmRecorder.kt` 30〜31行で録音の状態を確かめている。司令塔の水準のテストは空の PCM の場合だけで、開始・停止の失敗の分岐は R1-06 が挙げている |
| Android | #22 | 時計が戻ると区間が重なって走行が送れなくなる | 問題なし | `Ride.kt` 78〜86行で `maxOf(now, last.endedAt)`。`RideTest.kt` 74行・`RideControllerTest.kt` 182行で確かめている |
| Android | #25 | 必ず失敗する走行があると後の走行が送られない | 問題なし | `RideSync.kt` 285行の脇へ置く扱いと `RideSyncTest.kt` 344行 |
| Android | #38 | プロセスが消されたあとに「準備中…」のまま止まる | 問題なし | `Readiness.kt`・`AppGraph.kt` 393行。`MainActivityTest.kt` 59行・`ReadinessTest.kt` 32行 |
| Android | #53 | 書き込みが失敗し続けるあいだの編集と削除で保存待ちの変更が失われる | 問題なし | `RideController.kt` 216行。`RideControllerTest.kt` 854・871・887行の3件 |
| Android | #54 | 知らない削除の印が送信を止める・消した走行の質問が残る | 問題なし | `RoomAskLog.kt` 61行・`RideSync`。`RideSyncTest.kt` 418行・`RoomAskLogTest.kt` 138行 |
| Android | #68 | 試し直しの途中でプロセスが死ぬと録音が残らない | 問題なし | `AskController.kt` 56・386行。`AskControllerTest.kt` 696行・`RecordingStoreTest.kt` 91行 |
| Android | #72 | 名前の変更が記録の置き換えと名前の保存をまとめきれていない | 問題なし（R2-02 の出どころに #72 を書く） | 本文の2つの経路は直り、テストもある（`SettingsTest.kt` 137行・`TakeoverTest.kt` 162行・`RoomTakeoverTest.kt` 135行）。直しで入れた `Mismatched` のあとに送信が止まらないのは R2-02（R12-06） |
| Agent | #10 | 最初の2つの質問が同時に来ると MCP の接続の開始がぶつかる | 問題なし | `main.py` 32行の守りと `tests/test_main.py` 45行 |

## 確かめた範囲

issue の総数は、open が 3 件、closed が 109 件（Android 76・Backend 24・Agent 9）です。closed のうち NOT_PLANNED は 3 件（Backend #5・Agent #6・Agent #11）です。閉じたコミット・PR に結びついていない COMPLETED は Android #44 だけです。

- open: Android #94・Backend #28・Agent #8 の 3 件すべて。本文といまのコード、ほかの指摘との重なりを見た。
- closed（必ず見る対象としたもの）: Android #44（閉じたコミット・PR が無い COMPLETED）、NOT_PLANNED の Backend #5・Agent #6・Agent #11、再発の疑いがあった Backend #3・#17・#18 と Agent #6。
- closed（題から選んだ 10 件）: 記録の消失・他人のデータ・走行中に使えなくなる・送れなくなる、に当たりそうなもの。
  - Backend #4（他人の会話の文脈に入れる＝他人のデータ）
  - Android #1（空の音声を送り、誤った失敗を読み上げる＝走行中の誤動作）
  - Android #22（区間が重なり走行が永久に送れない＝記録がクラウドに届かない）
  - Android #25（1つの走行が後の全走行の送信を止める＝記録が届かない）
  - Android #38（「準備中…」のまま止まる＝走行中に使えなくなる）
  - Android #53（保存待ちの変更が失われる＝記録の消失）
  - Android #54（送信が止まり続ける・消したはずの質問が残る）
  - Android #68（プロセスの終了で録音が残らない＝記録の消失）
  - Android #72（名前の変更で記録が別の名前に混ざる＝記録の取り違え）
  - Agent #10（Web 検索なしの回答になる＝二重の開始の競合）
- 10 件とも、いまのコードに直しがあり、issue の番号を書いたテストがある。直しの周辺に残る穴は、R1-06・R2-02 がすでに挙げている。
- 読んでいないもの: 上の 17 件以外の closed の 92 件。

再発と判定したものは無い。Agent #6 は再発ではなく、閉じた前提が成り立たないもの（再び開く。R12-01）。Backend #3・#17・#18 と Android #72 は、直しの範囲の外の取りこぼしで、新しい issue の出どころに書く（R12-04〜06）。

## 指摘

### R12-01 [I] [Medium] [ありうる] Agent #6 を閉じた前提が崩れていて、同じ会話への呼び出しが重なり、聞いた回答の往復が履歴から消えうる

- 場所: `Agent/app/agentcore_trv2_dev_ask/handler.py` の `handle()`（82行で `deps.sessions.get(session_id)` の写しを取り、116行で `deps.sessions.put` で丸ごと書き戻す）、`history.py` の `SessionStore`（49〜66行。読みと書きのあいだに錠も版の比較も無い）。前提を崩す側: `Android/app/src/main/java/com/touringproject/v2/ask/AskController.kt` の `cancel()`（97行）・404〜405行（取り消した質問でも会話を続ける。`send()` の `d.conversation.current(...)` は382行）・446〜450行（待ちのあいだの取り消しはポーリングを止めるだけ）、`ask/Polling.kt` 14行（120 秒で待ち切る）、`Android/.../api/ApiClient.kt`（質問を取り消す API が無い。Backend にも取り消しの処理が無い）。Backend 側の呼び出し: `Backend/src/lib/agent.py` の `invoke()`（`RetryableConflictException` だけを0.5秒・1秒あけて試し直す）。
- 内容: Agent #6 は「Android の質問の一巡は1つずつで、回答待ちのあいだは次の質問を始めない」として NOT_PLANNED で閉じた（決定は `docs/specs/2026-10-25-slice5-design.md` §9）。しかし (1) 待っているあいだに利用者が取り消すと、Android はポーリングを止めるだけで Backend には知らせず、Backend の worker はその質問の Agent の呼び出しを最後まで続ける。取り消した質問が続きの質問だったときは、次の質問も同じ `conversationId` で送られ（404〜405行）、同じ `runtimeSessionId`（`Backend/src/lib/agent.py` 19〜23行）になる。(2) 120 秒の時間切れのあとに言い直したときも同じで、Agent の呼び出しには時間の上限が無い（R5-02）。どちらも、前の呼び出しが終わる前に次の呼び出しが始まると、両方が同じ古い履歴から始め、後に終わったほうが先に終わったほうの往復を消す。AgentCore の Runtime が並んだ呼び出しを `RetryableConflictException` で断る作りなら、Backend は2回試し直したあと（合わせて約1.5秒）`agent_failed` にするので、後の質問が失敗の音で終わる（履歴は消えないが、言い直しが通らない）。
- 起きる条件: 続きの質問を送ったあと、回答を待つあいだにインカムで取り消し、すぐ言い直す（前の Agent の呼び出しがまだ動いているうち。ツールを使う質問では数十秒かかる。スライス1 の実測で受け付けから音声まで中央値 12.6 秒なので、取り消してすぐ言い直せば重なりうる）。重なったとき、言い直した質問が先に終わり、取り消した質問が後に終わると、利用者が聞いた回答の往復が履歴から消え、取り消した（聞いていない）回答が残る。
- 影響: 次の「さっきの〜」が、聞いていない回答を前提に解釈される・聞いた回答を覚えていない。または言い直しが失敗になる。記録（DynamoDB の質問）は失われない。AgentCore の Runtime が同じセッションへの2つの呼び出しを同じコンテナで並べて処理するかは確かめていない（末尾の「確かめられなかった点」）。
- 対応案: Agent #6 を開き直し、本文を次の形に書き直す。
  - 内容: 上の (1)(2) の経路と、`handle()` の写しを取って書き戻す作り。
  - 対応案: (a) Agent で `session_id` ごとの `asyncio.Lock` を持ち、`handle()` の履歴の読みから書き戻しまでを錠の中で行う（元の #6 の案。次の呼び出しは前の呼び出しの往復を含む履歴から始まる）。または `put` を、自分の問いと答えだけを最新の履歴の後ろに足す `append(session_id, question, answer)` にして錠で守る。あわせて (b) R5-02 の時間の上限を入れると、重なりの窓が短くなる。(b) だけでは取り消しの経路が残るので (a) が要る。Runtime が並んだ呼び出しを断る作りなら、Backend の試し直しの間隔をツールを使う質問の長さに合わせて見直すか、取り消しのときに会話を区切る（Android が会話の識別子を捨てる）ことを検討する。取り消した質問の往復を履歴に残したくないなら、Android の取り消しを Backend に伝える（取り消しの API を足す）案もあるが費用は大きい。
  - テスト: `tests/test_handler.py` に、同じ `session_id` で2つの `handle()` を `asyncio.gather` で走らせ、遅いほうを先に始め・速いほうを後に終える作り物のエージェントで、最後の履歴に両方の往復が入っていることを確かめるテスト。実機では同じ `runtimeSessionId` を2本並べて呼び、Runtime が通すか断るかを確かめる。
  - 扱う時期: R5-02 を直すとき（同じ `handle()` を触る）。
  - 出どころ: Agent #6、`docs/specs/2026-10-25-slice5-design.md` §9、Android #30（待ちのあいだの取り消し）。
- 関わる文書: `docs/07_units_contracts.md` UC-8（「Agent は同じ識別子が来るあいだ文脈を続ける」。並んだ呼び出しの扱いが書かれていない）、`docs/08c_agent-design.md`（35行）
- 同じ根: R8-02（まとめた。R8-02 は Low だったが、閉じた issue の前提が崩れている点を重く見て Medium とする）・R5-02

### R12-02 [I] [Low] [確か] Backend #28 の本文が、外すときに直す場所の半分を挙げておらず、本文だけでは片付けきれない

- 場所: GitHub `h-akira/TouringProjectV2_Backend` #28 の「内容」「対応案」。
- 内容: 本文は Backend の3つの受け口と `lib/geo.py`、07a と 07 UC-5 だけを挙げる。実際には次も古い形の材料を持つ。Backend: `src/lib/offline.py`・`request.py`・`notes.py`・`handlers/ask_edit.py`・`worker.py`・README。Android: `api/ApiClient.kt` の `HeadingSample`（34・109〜132行）、`sync/SyncPlan.kt` の `UnsentNote.toBody()`・`UnsentUnreached.toBody()`（R2-11）、Room の `sample*` の列、README 37行。文書: 07b §4・08b §2。また、07a の中で `headingSample` の古さの境目が揺れている（R7-16）。`AskRequest.headingSample`（511行）は「2分より古いものは使わない」、`NoteRequest.headingSample`（674行）と `OfflineAskRequest.headingSample`（785行）は「2分以上古いものは使わない」。実装は3つとも同じ関数（`Backend/src/lib/geo.py` 11〜12行・51行。`age > 120` で捨て、ちょうど2分は使う。未来の時刻は30秒まで許す）なので、674行・785行の「以上」は実装と違い、未来の30秒の許しはどこにも書かれていない。外せば消えるので実害はほぼ無い。さらに、Android の送り口を先に外すと、古い未送信が `headingSample` も `headingDegrees` も無しで送られる（方位なしで記録される）ことを、本文が書いていない。
- 起きる条件: #28 を片付けるとき。
- 影響: Backend だけ外すと、Android に使われない列と型、文書に古い項目が残る。`_note` と `_offline` の2か所の整理も片方だけ直りうる。
- 対応案: #28 の本文の「内容」「対応案」に上の場所を足し、順序（Android の版を入れ、SC-14 で未送信0を確かめる → Backend と文書を外す → Android の型と送り口を外す。Room の `sample*` の列は Migration で落とすか、使わない列として残すかを決める）を書く。R7-16 の揺れ（07a の674行・785行）は #28 にまとめて閉じる（外すときに一緒に消える）。テストは本文の「`headingSample` だけを送ると方位なしで記録される」に加え、Android 側で `toBody()` が `headingSample` を出さないこと。扱う時期は今のままでよい（0.14.0 が実機にあり、plan 6 の Task 8 の走行のあとに SC-14 で確かめられる）。
- 同じ根: R7-16（まとめた）・R2-11

### R12-03 [I] [Low] [確か] Agent #8 の対応案が「モデルを変える」中心で、答えの質を変えずに下げる手と、扱う時期の目安が無い

- 場所: GitHub `h-akira/TouringProjectV2_Agent` #8 の「対応案」「扱う時期」。
- 内容: モデルを変えずに入力のトークンを下げる手が見つかっている。プロンプトのキャッシュ（R5-03。ツールを使う質問の2回目以降の周回）、Gateway の意味検索のツールを外す（R5-04）、ツールの上限に達したあとの周回を止める（R5-05）、履歴の事実の行を削る（R5-15）。これらは答えの質への影響が小さいので、モデルの切り替え（質の比較が要る）より先に試す順が合う。扱う時期の「費用が気になったとき」は、利用者が費用に敏感（`PROJECT.md`「前提」の「LLM の入力のトークンを増やす設計は避ける」）なのに、いつ見直すかの目安が無い。
- 起きる条件: 質問のたび。
- 影響: #8 をそのまま着手すると、モデルの比較から始め、質を落とさずに済む手を後回しにしうる。
- 対応案: #8 の対応案に R5-03・R5-04・R5-05・R5-15 を「モデルを変えない手」として足し（各指摘の場所と確かめ方を写す）、モデルの切り替えはそのあとにする。扱う時期を「次の Agent の plan のとき」か、具体の目安（例: 月の Bedrock の費用が X 円を超えたら）にする。確かめ方は本文のとおり `ask_done` の `usage`（R5-03 を入れるならキャッシュの読み書きのトークンも）で比べる。
- 同じ根: R5-03・R5-04・R5-05・R5-15

### R12-04 [I] [Low] [確か] Backend #3 の直しが `POST /transcriptions` に入っておらず、R4-04 と R7-12 が同じことを別の側から指している

- 場所: `Backend/src/handlers/transcriptions.py` の `_accept()`（42〜43行。`send_message` が例外を捕まえない）。比べる先は `handlers/ask.py` 59〜67行。
- 内容: #3 は `ask.py` だけを範囲にした（本文の場所）。`transcriptions.py` は #3 より前に足され（`ffff268`、2026-10-21。#3 を閉じた PR#26 は 2026-10-22 にマージ）、同じ形の直しが入らなかった。再発ではなく取りこぼし。R4-04（JSON でない 502・`pending` のまま・録音が残る）と R7-12（07 UC-6 は「UC-5 と同じ」として 503 を約束するが、07a にも実装にも無い）は同じ原因の両面。
- 起きる条件: 地点メモの声の入力で SQS に積めないとき。
- 影響: R4-04 のとおり（まれ）。
- 対応案: R4-04 と R7-12 を1つの issue にまとめ、出どころに Backend #3 を書く。#3 は開き直さない。直したことは `tests/test_transcriptions.py` に `tests/test_ask.py` 107行と同じ形のテスト（`send_message` を壊し、503 の JSON・記録と録音が残らない）を足して確かめる。07a の `/transcriptions` に 503 を書く。
- 同じ根: R4-04・R7-12

### R12-05 [I] [Low] [確か] Backend #17・#18 の直しの周りに残る穴（R4-05・R4-06）の出どころに、元の issue が書かれる必要がある

- 場所: `Backend/src/lib/store.py` の `get_note()`（256〜258行。`ConsistentRead` 無し）、`delete_ask()`（311〜317行。2回目の削除で `stored` が `None` になり、跡の `rideId` を `None` で書き直す）。
- 内容: #17 の2点（跡があれば住所を引かない・方位を保存済みから取る）と #18 の2点（`mark_deleted` の重なりの再試行・`delete_ask` の一貫した読み出し）は、どれも直りテストもある。R4-05（地点メモの保存済みを結果整合で読むので、続けて届いた版が方位と住所を決め直しうる）と R4-06（削除を送り直すと跡の `rideId` が消える）は、同じ関数の別の経路で、#17・#18 の範囲外。再発ではない。
- 起きる条件: R4-05・R4-06 のとおり。
- 影響: R4-05・R4-06 のとおり。
- 対応案: R4-05・R4-06 を issue にするとき、出どころに「Backend #17 の直し（`handlers/rides.py` の `_note`）」「Backend #18 の直し（`store.delete_ask`）」を書く。R4-06 の直し（跡があれば `rideId` を上書きしない＝`put_item` に `attribute_not_exists(pk)` の条件、または既存の跡の `rideId` を残す）は #18 のテスト（`tests/test_store.py` 158行）の隣に置く。#17・#18 は開き直さない。
- 同じ根: R4-05・R4-06

### R12-06 [I] [Low] [確か] Android #72 の直しで生まれた `Mismatched` の状態のあとを守っていない（R2-02）。#72 は直っている

- 場所: `Android/app/src/main/java/com/touringproject/v2/sync/Takeover.kt` の `switchTo()`・`start()`。
- 内容: #72 の2つの経路（名前の保存の失敗を握りつぶす・メモリ上の書き直し待ちを確かめない）は直り、テストがある。直しで「戻す保存も失敗した」ときの `TakeResult.Mismatched` が入ったが、そのあとも送信が走る（R2-02）。R2-01（設定を読めなかった起動でランダムな名前を保存する）も、#72 と同じ「名前と記録の食い違い」の別の入口。
- 起きる条件: R2-01・R2-02 のとおり。
- 影響: R2-01・R2-02 のとおり。
- 対応案: R2-01・R2-02 を issue にするとき、出どころに Android #72 を書き、記録の持ち主を Room に持たせる構成にすれば両方を一度に塞げることを添える。#72 は開き直さない。
- 同じ根: R2-01・R2-02

## 確かめられなかった点

- AgentCore の Runtime が、同じ `runtimeSessionId` への2つの呼び出しを同じコンテナで並べて処理するか（直列にするか・断るか）。並べるなら R12-01 はそのまま起きる。断るなら、言い直した質問が失敗になる別の症状になる。CloudWatch の Agent のログで、同じ `session` の `invoke_done` の時刻が重なっているものを探せば確かめられる。
- Android #94 の「2 になる」順序（本文も確かめていないと書いている）。テストを回さない決まりのため、再現していない。
- Android #44 の地図は、閉じたあとの実機の見え方を確かめていない（利用者の判断で閉じたものなので判定は変えない）。

issue を開く・閉じる・書き直すのは、利用者がこの報告を読んで決める。このレビューでは issue を変えていない。
