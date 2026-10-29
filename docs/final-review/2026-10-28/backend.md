# Backend の指摘

Backend（`Backend/`）と、それに対応する文書（`docs/07a`・`08b` など）についての指摘。観点は A（不具合）・B（脆弱性）・C（細部）・D（文書の整合）・E（費用）。
件数は 15 件（Medium 2・Low 12・Info 1）。同じ根の R7-12 は R4-04 にまとめた。
構成（観点 S）の指摘は `structure.md` に集めてあり、ここには載せない。

## Medium

### R4-01 [A] [Medium] [ありうる] 受け付けの直後のポーリングが結果整合の読み出しで 404 になると、Android はその質問を失敗にする

- 場所: `Backend/src/handlers/result.py` の `handler()`（22行）・`Backend/src/lib/store.py` の `get_ask()`（237〜239行。`consistent` の既定は False）。同じ形が `Backend/src/handlers/transcriptions.py` の `_get()`（50行）と `store.get_transcription()`（378〜380行。一貫した読み出しの引数が無い）にもある
- 内容: `POST /asks` は `put_item` で質問を作って 202 を返し、Android は約1秒後から `GET /asks/{askId}` を取りに行く。`GET` は結果整合の `get_item` なので、書き込みがまだ届いていない複製を読むと項目が無く、404 を返す。Android の `ask/Polling.kt` は `NOT_FOUND` を `FATAL` に入れており（15行）、1回の 404 で取りに行くのをやめて質問を失敗にする。`POST /transcriptions` と `GET /transcriptions/{id}`（地点メモの声）も同じ。
- 起きる条件: 受け付けの書き込みから最初のポーリングまでのあいだ（1秒＋往復の時間）に、読む複製へ書き込みが届いていないとき。DynamoDB の結果整合は「ふつう1秒以内」なので、まれ。実際に遅れが1秒を超えるかは確かめられていない。
- 影響: 回答が届いているのに、利用者には失敗として知らされる（走行中の質問が無駄になり、聞き直すことになる）。頻度は低いが、起きたときは利用者に見える。
- 対応案: `result.handler` と `transcriptions._get` で `ConsistentRead=True` で読む（`store.get_ask(user, ask_id, consistent=True)`、`get_transcription` に同じ引数を足す）。費用は1回の読み出しが 0.5 RCU から 1 RCU に増えるだけ（1問あたり最大70回ほどのポーリングで +35 RCU 程度、無視できる）。テストは `test_records_are_read_consistently` と同じく、`table.get_item` を包んで `ConsistentRead=True` で呼んでいることを確かめる（moto はいつも一貫しているため）。

### R4-02 [A] [Medium] [確か] worker が受け持ちを取ったあとで落ちる（時間切れ・メモリ切れ）と、質問は `processing` のまま残り続け、SQS の送り直しも DLQ も働かない

- 場所: `Backend/src/handlers/worker.py` の `process()`（53〜62行）と `_run()`。`Backend/src/lib/store.py` の `_claim()`（169〜183行）。`Backend/template.yaml` の `WorkerFunction`（`Timeout: 120`）と `AskQueue`（`VisibilityTimeout: 180`・`maxReceiveCount: 2`）。`Backend/src/lib/transcribe.py` の `transcribe_pcm()`（時間の上限なし）。`Backend/src/lib/clients.py` の `agentcore()`（`read_timeout=90`）と `Backend/src/lib/agent.py` の `invoke()`（`RetryableConflictException` で最大3回）
- 内容: `process()` は先に `pending → processing` の条件付き書き込みで受け持ちを取り、例外は `except Exception` で `failed` にする。しかし Lambda の時間切れ（120秒）やメモリ切れは例外として捕まらず、記録は `processing` のまま残る。SQS は可視性タイムアウト（180秒）のあとにメッセージを送り直すが、2回目の `claim_ask` は条件が合わず `ask_skipped` で正常に終わるので、メッセージは消え、DLQ にも移らない。時間の予算も120秒に収まる保証が無い。Transcribe のストリーミングには時間の上限が無く、Agent の `read_timeout=90` はソケットの1回の読みごとの上限で全体の上限ではなく、`RetryableConflictException` では最大3回呼ぶ。
- 起きる条件: 文字起こしか Agent の応答が遅く、受け付けからの合計が120秒を超えたとき。Lambda の実行環境が落ちたとき。120秒を超える頻度は確かめられていない。
- 影響: Android は120秒で打ち切って時間切れとして扱い、引き継ぎでも `processing` を時間切れの失敗として取り込む（`Android/.../sync/Merge.kt` の `toRecord()`）ので、利用者に見える害は小さい。ただし Backend の記録はいつまでも解決せず、`08b` §5 の「worker が落ちたメッセージは SQS が送り直し、2回失敗したら DLQ に移す」が受け持ちの後の失敗には当てはまらない（DLQ を見ても気づけない）。
- 対応案: (1) `_run` の各段に時間の予算を持たせる（`context.get_remaining_time_in_millis()` を `Steps` に渡し、Agent の呼び出しの前に残りが足りなければ `agent_failed` で終える。文字起こしは `asyncio.wait_for` で上限を付ける）。(2) 受け持ちに時刻（`claimedAt`）を残し、`_claim` の条件を「`pending`、または `processing` で `claimedAt` が Lambda の時間切れより古い」にして、送り直しのときに `failed`（`agent_failed`）へ書き換えて終える。(3) `08b` §5 に「受け持ちを取ったあとの失敗は送り直しで `failed` にする」と書く。テストは、`claimedAt` が古い `processing` の質問に2回目のメッセージが来ると `failed` になること、新しい `processing` なら何もしないこと。
- 関わる文書: `docs/08b_backend-design.md` §5（76行）と §1 の図（20行の「2回失敗」）

## Low

### R4-03 [A] [Low] [確か] 質問を SQS に積めなかったときに録音を消そうとするが、ask の Lambda に S3 の削除の権限が無く、録音は1日残る

- 場所: `Backend/src/handlers/ask.py` の `_discard_audio()`（15〜19行）と `handler()`（64〜66行）。`Backend/template.yaml` の `AskFunction` の `Policies`（`s3:PutObject` だけ。85〜87行）
- 内容: 積めなかったときは `delete_object` で録音を消すが、`AskFunction` には `s3:DeleteObject` が無いので AccessDenied になり、`audio_delete_failed` を記録して続ける。録音はライフサイクルの1日まで残る。テスト（`test_an_ask_that_cannot_be_queued_is_503_and_leaves_no_ask_or_audio`）は moto で IAM を見ないので通る。
- 起きる条件: SQS への送信が失敗したとき（まれ）。
- 影響: README の「流れ」1 と `08b` §2.1 の「記録と音声を消して 503」と食い違う。録音（声の個人情報）が最大1日残る（US-C-06.003 の範囲には収まる）。
- 対応案: `AskFunction` の Statement に `s3:DeleteObject`（`${AudioBucket.Arn}/audio/*`）を足す。テストは `tests/test_template.py` に「`ask.py` が `delete_object` を呼ぶなら `AskFunction` の権限に `s3:DeleteObject` がある」ことを確かめる1件を足す。
- 同じ根: R4-04（transcriptions の側にも同じ権限が要る）

### R4-04 [A] [Low] [確か] `POST /transcriptions` で SQS に積めないと、JSON でない 502 になり、記録が `pending` のまま・録音も残る（文書は 503 のように読める）

- 場所: `Backend/src/handlers/transcriptions.py` の `_accept()`（42〜43行。`send_message` の例外を捕まえない）。対して `Backend/src/handlers/ask.py` 59〜67行は 503 を返す
- 内容: `ask.py` は SQS の失敗を捕まえて記録と録音を消し 503 を返すが、`transcriptions` の受け付けは捕まえない。Lambda が落ちて API Gateway が JSON でない 502 を返し、`TRANSCRIPTION#` の記録は `pending` のまま（TTL の1日まで）、録音は S3 に1日残る。一方 `07` UC-6 は「受け付けと受け取りの形は UC-5 と同じ」、UC-4 は「処理に回せなかったときは、記録を残さずに 503」と書くので、503 が返ると読め、`07a` の `/transcriptions` の `post` には 503 の応答が無い。文書と実装が食い違っている。
- 起きる条件: SQS への送信が失敗したとき（まれ）。
- 影響: Android は 5xx を通信の失敗として扱うので利用者への害は小さい。文書と実装の食い違いが主。
- 対応案: どちらかに揃える。文書に合わせるなら、`ask.py` と同じく送れなければ記録を消し（`delete_item`）、録音を消して（R4-03 と同じく権限を足す）503 を返し、`07a` に 503 を足す。テストは `test_an_ask_that_cannot_be_queued_is_503_and_leaves_no_ask_or_audio` と同じ形で、`transcriptions` について書く（SQS の `send_message` を失敗させて 503 と記録が無いことを確かめる）。実装に合わせるなら、`07` UC-6 に「積めなかったときの 503 は無い（5xx）」と書く。
- 関わる文書: `docs/07_units_contracts.md` UC-4（73行）・UC-6（117行）、`docs/07a_openapi.yaml` の `/transcriptions` の `post`（352〜380行）、`docs/08b_backend-design.md` §2
- 同じ根: R7-12（文書の食い違いの側の指摘。ここにまとめた）・R4-03

### R4-05 [A] [Low] [ありうる] 地点メモの PUT は保存済みの地点メモを結果整合で読むので、続けて届いた版が住所と方位を決め直して上書きすることがある

- 場所: `Backend/src/handlers/rides.py` の `_note()`（61行と82行の `store.get_note`）・`Backend/src/lib/store.py` の `get_note()`（256〜258行。一貫した読み出しの引数が無い）
- 内容: 地点メモの住所と方位は「最初に受けたときに決め、あとの PUT では変えない」（07a）。`_note()` は保存済みの地点メモを結果整合で読み、無ければ受けた版から方位を求め、住所を引き直し、`put_note` が項目を丸ごと置き換える。直前の PUT がまだ読めないと、2つ目の版が自分の方位と住所で上書きする（`updatedAt` が新しいので条件は通る）。同じ扱いの `ask_edit._offline()` は `get_ask(..., consistent=True)` で読んでいる（47・76行）ので、2か所で揃っていない。82行の「書かなかったときに読み直す」も結果整合なので、古い値を返すことがある。
- 起きる条件: 地点メモを作ってすぐ（1秒以内）に書き直し、両方の PUT が続けて届いたとき。送れなかった分をまとめて送るときにも起きうる。結果整合の遅れに当たるかは確かめられていない。
- 影響: 住所の引き直しが1回増える（Location Service の費用）。作った後に Android が方位を変えないなら方位は同じ値になるが、変わる場合は「最初の方位」の決まりが破れる。
- 対応案: `get_note` に `consistent` の引数を足し、`_note()` の2か所で `True` にする（`_offline` と揃える）。テストは `test_deleting_a_ride_reads_its_records_with_consistent_reads` と同じく、`get_item` の引数で `ConsistentRead=True` を確かめる。

### R4-06 [A] [Low] [確か] 削除をもう一度送ると削除の跡が書き直され、質問の跡の `rideId` が消え、`deletedAt` が後ろにずれる

- 場所: `Backend/src/lib/store.py` の `mark_deleted()`（97〜101行。条件なしの `put_item`）と `delete_ask()`（311〜317行）
- 内容: `delete_ask` は保存済みの質問から `rideId` を読んで跡に書く。質問がもう無い（1回目の削除で消えた・走行の削除で消えた）と `rideId` は `None` になり、`put_item` が跡を丸ごと置き換えるので、1回目の跡にあった `rideId` が消える。どの跡も、送り直すたびに `deletedAt` が新しい時刻になる。
- 起きる条件: Android が削除を送り直したとき（応答が届かず 5xx・通信の失敗で試し直す。`TRANSIENT` で最大3回）。走行の削除のあとに、その走行の質問の削除が届いたとき。
- 影響: いまの Android は跡の `rideId` と `deletedAt` を使っていない（`sync/Merge.kt` の `merge()`）ので、利用者への害は無い。`07` UC-4「書き込みと削除は、何度送っても同じ結果になる」・`07a` の `DeletedRecord.rideId`（「分かれば」）と食い違い、後で跡の `rideId` を使う機能を足すと踏む。
- 対応案: `mark_deleted` を `attribute_not_exists(pk)` の条件付きの書き込みにし、条件が合わなければ何もしない（`ConditionalCheckFailedException` を無視する）。テストは「質問を消して、もう一度消しても、跡の `rideId` と `deletedAt` が1回目のまま」「走行を消したあとでその質問を消しても、跡の `rideId` が残る」。

### R4-12 [B] [Low] [確か] API の Lambda に、表全体の `Scan` を含む広い DynamoDB の権限を与えている

- 場所: `Backend/template.yaml` の `AskFunction`・`RidesFunction`・`AskEditFunction`・`TranscriptionsFunction`・`WorkerFunction`（`DynamoDBCrudPolicy`）、`ResultFunction`・`RecordsFunction`（`DynamoDBReadPolicy`）
- 内容: SAM のポリシーの雛形は `Scan`・`BatchWriteItem` などを含む。コードが使うのは `GetItem`・`PutItem`・`UpdateItem`・`DeleteItem`・`Query`・`BatchGetItem`・`BatchWriteItem`（rides のみ）・`ConditionCheckItem` で、`Scan` はどこも使わない。
- 影響: いまのコードでは害は無い。将来の不具合や依存の脆弱性でコードが乗っ取られたとき、すべてのユーザーの記録を読める（記録はユーザー名ごとに分ける約束、`07` UC-4）。
- 対応案: 関数ごとに使う操作だけの Statement にする（例: result は `dynamodb:GetItem`、records は `dynamodb:Query`）。テストは `tests/test_template.py` に「どの関数にも `dynamodb:Scan` が無い」。

### R4-07 [E] [Low] [確か] Lambda のログの保持期間が決まっておらず、CloudWatch Logs に無期限に溜まる

- 場所: `Backend/template.yaml`（`AWS::Logs::LogGroup` が無い。8つの関数すべて）
- 内容: ロググループを template で作っていないので、Lambda が初回に作るロググループは「無期限に保持」になる。worker は1問ごとに `ask_done`（`usage`・`tools`・`durationsMs`）を出し、ポーリングの Lambda も呼ばれるたびに開始・終了の行を出す。
- 起きる条件: 使い続けるほど。
- 影響: 保管の費用（東京で約 0.033 USD/GB・月）が増え続ける。量は小さいが、減ることが無い。消すときはスタックの外の手作業になる。
- 対応案: 関数ごとに `AWS::Logs::LogGroup`（`/aws/lambda/lambda-trv2-${Environment}-<名前>`・`RetentionInDays`。所要時間を後から見るなら 30〜90 日）を template に足す（または Globals の `LoggingConfig` でロググループを指定する）。既にあるロググループは、デプロイの前に消すか import する（README のデプロイの手順に書く）。テストは `tests/test_template.py` に「すべての関数にロググループと保持期間がある」。

### R4-08 [E] [Low] [確か] 走行を1つ消すたびに、ユーザーの質問をすべて（全期間）読む

- 場所: `Backend/src/lib/store.py` の `delete_ride()`（331行）と `_query_keys()`（287〜301行。`ASK#` の前方一致に `FilterExpression` で `rideId` を絞る）
- 内容: 質問は `ASK#<id>` で走行の下に無いので、`begins_with(sk, "ASK#")` でユーザーのすべての質問を読み、`FilterExpression` で絞る。DynamoDB の読み出しの費用は絞る前の量で数え、`ProjectionExpression` でも減らない。質問の項目は回答の文・`usage`・`timings` を持つので数 KB ある。跡も1件ずつ `put_item` を順に呼ぶ（333〜335行）。
- 起きる条件: 走行を消すたび。質問の数が増えるほど重くなる（1000問・各4KB なら一貫した読みで約 1000 RCU、Lambda の時間も延びる。`RidesFunction` の時間の上限は 10 秒）。費用の大きさは見積もり。
- 影響: いまの量（走行20本ほど）では費用はごくわずか。記録が年単位で増えると、削除の費用と時間が増え、時間切れになると途中まで消した状態で 5xx になる（送り直しで続きは消える）。
- 対応案: 質問の項目に、走行の下に「質問の索引」（`RIDE#<走行>#ASK#<質問>`・キーだけ）を受け付けのときに一緒に置き、`delete_ride` は `RIDE#<走行>` の前方一致の1回の問い合わせだけで集める（`08b` §3 の「一度の問い合わせでまとめて集められる」とも合う）。跡は `batch_writer` でまとめて書く。急がないなら「記録が大きく増えたら測り直す」として持ち越しに書くだけでもよい。テストは「別の走行の質問が多くても、読む項目が消す走行のものだけ」。

### R4-09 [D] [Low] [確か] `08b` は「会話を区切る分数を受け付けのたびに SSM から読む」と書くが、実装は60秒覚えておく

- 場所: `Backend/src/lib/conversation.py` の `reset_minutes()`（`CACHE_SECONDS = 60`。18・42〜49行）
- 内容: 実装は SSM の値を60秒覚え、README の「運用」も「60秒以内に反映」と書く。`08b` §6 は「受け付けのたびに読む」。
- 影響: 値を変えた直後の振る舞いを `08b` で読むと誤る（小さい）。
- 対応案: `08b` §6 を「受け付けのときに読む（少しのあいだ覚えておく）」にする（数値は 08 系に書かない決まりなので、60秒は README に任せる）。
- 関わる文書: `docs/08b_backend-design.md` §6（81行）

### R4-10 [D] [Low] [確か] `08b` の作りの説明が2か所で実装と合わない（API の Lambda は「積むだけ」・走行の下の記録は「一度の問い合わせ」）

- 場所: `docs/08b_backend-design.md` §1（27行）・§3（57行）。実装は `Backend/src/handlers/rides.py` の `_note()`（75〜76行で Location Service を呼ぶ）・`Backend/src/handlers/ask_edit.py` の `_offline()`（69〜70行）・`Backend/src/lib/store.py` の `delete_ride()`（329〜331行で2回問い合わせる）
- 内容: §1「API の Lambda は検証して積むだけで、すぐ返す」とあるが、地点メモと質問できなかった地点の PUT は、その場で住所を引く（外部の呼び出しを待つ）。§3「走行を消すときに一度の問い合わせでまとめて集められる」とあるが、質問は走行の下に無く、`ASK#` をもう1回問い合わせる（R4-08）。
- 影響: 仕組みを `08b` で掴んだ人が、API の Lambda の時間の上限や、走行の削除の重さを見誤る。
- 対応案: §1 を「重い処理（文字起こし・Agent・音声合成）は worker だけが行う。地点メモと質問できなかった地点の住所は、最初の PUT でその場で引く」にする。§3 を「ルートと地点メモは走行の識別子の前方一致で、質問は走行の識別子で絞って集める」にする（R4-08 で索引を足すなら、そのときに戻す）。
- 関わる文書: `docs/08b_backend-design.md` §1・§3

### R4-11 [D] [Low] [確か] `07a` の質問の `rideId` の説明が「一時停止中・記録していないときは付けない」と、走行の外の質問があるように読める

- 場所: `docs/07a_openapi.yaml` の `AskRequest.rideId`（530〜534行）。Backend は `rideId` の無い質問を受けて記録する（`Backend/src/lib/request.py` の `parse_ask()` 154〜157行、テスト `test_an_ask_outside_a_ride_has_no_ride_id`）
- 内容: `04` US-B-01.006・US-C-03.005 と `07b` §1（「地点メモと質問は、いつもどれか1つの走行に入る」・adr/0008）では、質問は記録中だけ受ける。`07a` は `rideId` を nullable にして、付けない場合を「一時停止中・記録していないとき」と書く。Android は引き継ぎで `rideId` の無い質問を捨てる（`sync/Merge.kt` の `merge()`）。
- 影響: `07a` を読むと、走行の外の質問が正しい使い方に見え、Backend はそれを黙って記録するが、引き継ぎでは消える。
- 対応案: `07a` の説明を「走行の記録中に始めた質問に付ける（質問は記録中だけ受ける。adr/0008）。古い版のために省いてもよいが、省いた質問は引き継ぎで読み込まれない」にする。必須にするなら新しい版の Android がいつも付けることを確かめてから、Backend で 400 にする（別の plan）。
- 関わる文書: `docs/07a_openapi.yaml`・`docs/07b_datamodel.md` §1

### R4-13 [C] [Low] [確か] 同じ小さな処理が `src/` の中で何度も書かれている（更新の式の組み立て・UTC の時刻の書式・質問の状態の対応表）

- 場所:
  - 更新の式（`SET #k0 = :v0, ...`）の組み立て: `Backend/src/lib/store.py` の `update_ask()`（191〜199行）・`put_offline_ask()`（224〜232行）・`finish_transcription()`（368〜375行）
  - UTC・ミリ秒・`Z` の書式: `Backend/src/handlers/common.py` の `iso()`（16〜18行）・`Backend/src/lib/rides.py` の `utc_time()`（40〜41行）・`Backend/src/lib/request.py` の `heading_sample()`（94〜95行）
  - 質問の状態の対応表: `Backend/src/handlers/result.py` の `_STATUS`（12〜13行）と `Backend/src/lib/records.py` の `_ASK_STATUS`（15〜16行）
- 内容: どれも同じ規則を別々に書いている。時刻の書式は新旧の比べ方（文字列の比較）を支えるので、1か所だけ変わると `updatedAt` の比べ方が壊れる。
- 対応案: `store._set_expression(values)`・`common.iso()` を使う形に寄せる（`utc_time` と `heading_sample` は `iso(parsed)` を呼ぶ）・状態の対応表を `lib/records.py` に1つ置いて `result.py` から読む。振る舞いは変わらないので、今のテストが通ることで確かめる。

### R4-14 [C] [Low] [確か] `handlers/rides.py` の冒頭の説明が古い（「読み出しは後で」）

- 場所: `Backend/src/handlers/rides.py` の docstring（1〜3行「Reading them back comes later.」）
- 内容: 読み出しは `GET /records`（`handlers/records.py`）で既にある。
- 対応案: その一文を消すか「Reading them back is GET /records (handlers/records.py).」にする。

## Info

### R4-15 [E] [Info] [確か] smoke は回すたびに削除の跡を残し、そのユーザーの記録を毎回すべて読むので、少しずつ重くなる

- 場所: `Backend/scripts/smoke.py` の冒頭の説明（1〜3行「a run leaves only deletion marks」）・`read_records()`（168〜179行。`records_check` と `records_after_delete_check` で2回）
- 内容: 跡は期限なし（adr/0009）なので、`smoketest` のパーティションに1回あたり数件ずつ溜まり、`GET /records` を最後まで読む量が回すたびに増える。
- 影響: いまは無視できる。CICD で smoke を頻繁に回すようになると、読み出しと時間が線形に増える。
- 対応案: smoke の最後に、AWS の権限で `smoketest` の `DELETED#` を消す（smoke は既に boto3 で CloudFormation と API Gateway を読んでいる）。あるいは CICD のときに考える。

## 確かめられなかった点

- worker の実際の所要時間の分布（120秒に近い質問があるか）。CloudWatch の `ask_done` の `durationsMs` で確かめられる（R4-02 の起きやすさ）。
- DynamoDB の結果整合の遅れが実際に1秒を超えるか（R4-01・R4-05 の起きやすさ）。
- `GET /records` の1ページ（DynamoDB の 1MB）が JSON になったときの大きさ。数の表し方から見積もると 2MB 前後で、Lambda の応答の上限（6MB）には収まると読んだが、実際の記録では測っていない。
- SQS をイベントの元にした Lambda の、待っているあいだの SQS への問い合わせの回数（アイドルの費用）。同じアカウントのほかのプロジェクトと合わせて無料枠を超えているかは、AWS に触れないので確かめていない。
