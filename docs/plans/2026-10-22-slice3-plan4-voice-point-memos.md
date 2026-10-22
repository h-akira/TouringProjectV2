# スライス3 計画4: Android（声の地点メモ） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SC-19 で、地点メモを声でも書けるようにする（「🎤 声で入力」とインカムのボタン）。声は文字にするだけの依頼として Backend に送り、聞き取れた文を入力欄の終わりに足す。通信できないときは声の入力を受けず、文字で書けることを示す。あわせて Android #57 を直す。最後に spec §1 の判定を実機で確かめ、スライス3を終える。

**Architecture:** 声の入力の司令塔 `VoiceInput`（新しい `voice/`）が、試し録り（SC-12）と同じく、質問とは別の経路の切り替えと録音の部品を持つ。録音して `POST /transcriptions` に送り、質問と同じ間隔で `GET` する（取りに行く処理 `pollUntil` を質問と共通にする）。SC-19 が出ているあいだは `VoiceInput` が「つながっている」状態になり、押下の行き先（`PressRouter`）がインカムのボタンを質問ではなく声の入力へ回す。通信できるかは `Connectivity`（新しい `net/`）が追う。画面は SC-19 の下部に声の入力の欄を足し、聞き取れた文を共通の編集部品 `MemoEditor` が入力欄の終わりに足す。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版5のまま）・Robolectric 4.16（SDK 35）・OkHttp・kotlinx.serialization。足す依存は無い（`ACCESS_NETWORK_STATE` はライブラリからすでに入っていて、権限の検査は15件のまま）。

**Spec:** [docs/specs/2026-10-21-slice3-design.md](../specs/2026-10-21-slice3-design.md)（§1・§2・§6.2 の `/transcriptions`・§7.3・§8・§9・§11・§12）。Backend の受け口（`POST /transcriptions`・`GET /transcriptions/{id}`）は plan 1 でデプロイ済み（07 の UC-6、`Backend/openapi.yaml` の `TranscriptionRequest`・`TranscriptionResult`）。

**範囲に入れた issue（Android）:** #57（SC-19 の起きにくい操作の隙: 削除中の Back・別のタブに開く・プロセスの終了後の保存・見つからないときの画面）。

**前提:** Android の `main`（`c048147`。版 0.7.0）の上に作る。

**計画を書くときに決めたこと（spec からの具体化）:**
- 声の入力の失敗の文言（spec §12。利用者と決めた、2026-10-22）は、理由と次の手を入力欄の下に赤字で出す。聞き取れなかった「声が聞き取れませんでした。もう一度話してください。」、文字にできなかった「声を文字にできませんでした。もう一度試すか、文字で書いてください。」、通信できない（送れない・時間切れ）「通信できないため、文字にできませんでした。文字で書けば保存できます。」、マイクが使えない「マイクを使えませんでした。マイクの許可を確かめてください。」。接続キーが無い・無効なときは、同じ言い方で「接続キーを使えないため、文字にできませんでした。文字で書けば保存できます。」とした。どの失敗でも、質問と同じ失敗の合図を鳴らす（インカムのボタンで始めたときに分かるように）。モックの SC-19 に、この plan のコミットで反映した。
- 通信できないときにインカムのボタンを押したら、録音を始めず、失敗の合図だけを鳴らす（利用者と決めた）。画面の「🎤 声で入力」は押せなくし、「通信できないため、声では入力できません。文字で書けば保存できます。」を出す（spec §7.3）。
- 通信できるか: 端末の既定のネットワークが internet の能力を持つかを追う（`Connectivity`）。通信できると見えても Backend に届かないことはあり、そのときは送るところで「通信できないため、文字にできませんでした。…」になる。
- 録音: 画面のボタンは質問の「押して話す」と同じ経路（`Source.SCREEN`、通話の経路）、インカムのボタンは質問のインカムと同じ経路（`Source.HANDSFREE`、音声認識の経路）。経路の切り替えと録音の部品は、試し録りと同じく `VoiceInput` 専用のものを `AppGraph` で作る（質問のものと分ける）。開始の合図は録音が始まってから鳴らす（質問と同じ）。もう一度押すか、ヘッドセットが音声認識を終えたら止める。60秒で自動で止める。
- 送る前に: 録音が空ならマイクの失敗、0.25秒より短ければ（Backend が受けない）送らずに「聞き取れませんでした」。送ったあとの答えの扱いは、400 を「聞き取れませんでした」、403 と接続キーが無いときを接続キーの失敗、通信・流量の制限・サーバーの失敗・120秒の時間切れ・`GET` の 404 を「通信できないため…」にする。`done` でも文が空白だけなら「聞き取れませんでした」。`POST` は質問と同じく 429 だけ送り直す（応答が失われても、文字起こしはすでにできているかもしれないため）。
- 聞き取れた文は、前後の空白を落とし、入力欄の終わりに改行を挟んで足す（入力欄が空か改行で終わっていれば挟まない）。2000字（コードポイント）で切り、カーソルを末尾に置く。そのあと手で直せる。同じ文を二度足さないように、聞き取れた文には通し番号を付け、画面が足したら `taken` で消す。
- SC-19 が出ているあいだだけ、インカムのボタンは声の入力を始める・止める（`VoiceInput.attach`。spec §7.3）。ただし、質問がすでに進んでいるときは質問のまま（録音を止める・応答中であることを伝える）。SC-19 を離れる（✕・Back・保存・削除、画面の作り直しを含む）と、録音も文字起こしの待ちも捨て、あとから来た結果はどこにも足さない。保存は声の入力のあいだもできる（保存で閉じると、待っていた結果は捨てる）。
- 前面サービスは使わない。SC-19 は画面を見ながら使う前提で、走行の記録中は位置の前面サービスがプロセスを保つ。画面を消したまま声で書く使い方は、spec の範囲外（走行中にインカムのボタンだけで声の地点メモを書くことは 01 の未確定事項のまま）。
- 取りに行く処理: `pollUntilDone`（質問）を、終わったかを渡せる `pollUntil` に広げ、`PollOutcome` を型つきにする。質問の振る舞いは変えない。
- #57: (1) 削除を確かめてから終わるまで、✕・Back・保存・2回目の削除を受けない（`MemoEditor` の `busy`）。(2) ホームの「📝 地点メモ」は、位置を読んでいるあいだに別のタブへ移ったら SC-19 を開かない（`TabStacks.pushOn`）。(3) 同じ下書きの id で2回目の保存が来たら、保存済みの地点メモの本文を変える（同じ走行のときだけ）。(4) 走行か地点メモが見つからないときは「この走行は見つかりません。」「この地点メモは見つかりません。」と ✕ を出す（`NoteNotFound`）。
- `AppUi` の通しのテストは書けない（plan 3 と同じ）。SC-19 の route がインカムのボタンを受ける・離すことは Robolectric で（`NoteRoutesTest`）、インカムのボタンでの開始と停止・声の文字起こしは Task 8 の実機で確かめる。
- 版を 0.8.0（`versionCode` 9）に上げる。

この計画のコードは、使い捨てのフォルダで、次を確かめてから書いた。

- タスクの順に一つずつコミットし、各タスクのコミットで `clean` から JVM のテストが通る（493件 → 521件）。各タスクのテストだけを1つ前のコミットに当てると、まだ無い名前を使うので、コンパイルで落ちる。
- 最後に、JVM のテスト521件・エミュレーターのテスト6件・`assembleRelease`・`scripts/check-release-permissions.sh`（15件）が通る。
- plan の差分を新しい写しへ機械的に当てると、最終形と一致する。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice3-plan4` を切る（Task 0）。親は `slice3-plan4`。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- 作りの決まり: 状態機械と司令塔は Android に依存させない（`VoiceInput` は JVM でテストする）。部品は `AppGraph` で手で組む。`VoiceInput` は `AskController` と同じく、メインスレッドだけから呼ぶ。
- 声は文字にするためだけに送り、AI には聞かない。音声は端末に残さない（録音の確認 SC-12 の直近10件にも入れない）。
- 地点メモは1〜2000字（コードポイント）。ホームは全体がスクロールしない。Room のスキーマは変えない（版5のまま）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --tests '*クラス名'`。テストを確かめるときは `--rerun` を付ける。`clean` のあとの1回目は、`--rerun` が無いとビルドキャッシュから結果が返る。Kotlin の差分コンパイルは interface の変更を見逃すことがあるので、Task 7 は `./gradlew clean` から回す。
- Robolectric の決まり（SDK 35・`@Config(qualifiers)` で画面を大きくしない・画面の外の行は `performScrollTo`／`performScrollToNode` で出す・地図の部品は動かさない・入力欄にフォーカスがあるあいだの最初の Back は入力欄が受ける）。Robolectric のアプリ自身（`AppGraph`）も `Connectivity` の受け口を登録するので、テストで作ったものの受け口は差で選ぶ（Task 3 の `ConnectivityTest`）。
- `RideForegroundServiceTest` の1件がまれに落ちる（Android #59。この plan の範囲外）。落ちたら単独で回し直し、全体をもう一度回す。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。使い終わったら止める。
- AWS は `AWS_PROFILE=touring`・リージョン `ap-northeast-1`（Task 8 で DynamoDB を読むことと、Backend の smoke）。

## Review Focus

- 録音中に SC-19 を離れる（✕・Back・保存） → 録音を捨てて経路を戻し、何も送らない。Task 2 の `leaving_drops_the_recording_or_the_text_still_being_made`。
- 文字にしているあいだに SC-19 を離れ、別の地点メモの SC-19 を開く → 前の結果はどの地点メモにも足されない。Task 2 の `leaving_drops_the_recording_or_the_text_still_being_made`、Task 4 の `sc19_takes_the_intercom_button_while_it_is_shown`。
- 質問の答えを待っているあいだに SC-19 を開き、インカムのボタンを押す → 声の入力ではなく質問のまま（応答中であることを伝える）。Task 3 の `an_ask_under_way_keeps_the_button_even_on_sc19`。
- 2000字近く書いたあとで声を足す → 2000字で切れ、絵文字を割らない。Task 2 の `what_was_heard_goes_at_the_end_on_a_line_of_its_own`。
- 通信できないときにインカムのボタンを押す → 録音を始めず、失敗の合図だけが鳴る。Task 2 の `without_a_network_a_press_records_nothing_and_gives_the_failure_cue`。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `api/ApiClient.kt`・`ask/Polling.kt`・`ask/AskController.kt` | 文字起こしの `POST`・`GET`（`TranscriptionApi`）・型つきの `pollUntil` | 1 |
| `voice/VoiceInput.kt`（新規）・`records/Notes.kt` | 声の入力の司令塔と失敗の理由・聞き取れた文の足し方（`appendHeard`） | 2 |
| `handsfree/PressRouter.kt`・`net/Connectivity.kt`（新規）・`AppGraph.kt` | インカムのボタンの行き先・通信の状態・`voice` と `connectivity` の組み立て | 3 |
| `ui/NoteScreen.kt`・`ui/MemoScreen.kt`・`ui/RecordsRoutes.kt`・`ui/AppUi.kt` | 声の入力の欄（`NoteVoiceUi`）・聞き取れた文を足す・SC-19 のあいだつなぐ（`NoteVoice`） | 4 |
| `ui/Tabs.kt`・`store/RideDatabase.kt`・`ui/NoteScreen.kt`・`ui/MemoScreen.kt`・`ui/RecordsRoutes.kt`・`ui/AppUi.kt` | #57 | 5 |
| `app/build.gradle.kts`・`README.md`・`docs-parent/` | 版 0.8.0・決まり・親の文書の写し | 6 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、今のテストを回す**

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice3-plan4
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t0.log 2>&1; tail -1 /tmp/trv2-t0.log
```

Expected: `BUILD SUCCESSFUL`（493件）。親はこの plan を書いたブランチ `slice3-plan4` のまま。

---
### Task 1: API: 文字起こしの依頼と、取りに行く処理の共通化

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `api/ApiClient.kt`・`ask/AskController.kt`・`ask/Polling.kt`
- Test: `api/ApiClientTest.kt`・`ask/PollingAndConversationTest.kt`

**Interfaces:**
- Consumes: `ApiClient.request`・`AskResult`・`pollUntilDone`
- Produces:
  - `TranscriptionBody(audio)`・`TranscriptionAccepted(transcriptionId)`・`TranscriptionResult(transcriptionId, status, text: String? = null, failure: String? = null)`・`interface TranscriptionApi { postTranscription(body); getTranscription(id) }`（`ApiClient` が実装。`POST` は 429 だけ送り直す）
  - `sealed interface PollOutcome<out T>`（`Done<T>(result)`・`Timeout`・`Cancelled`）・`pollUntil(get, pending: (T) -> Boolean, sleep, now, isCancelled): PollOutcome<T>`。`pollUntilDone` は質問の `processing` を渡すだけになる

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
index 791b753..ed44309 100644
--- a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
+++ b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
@@ -268,4 +268,30 @@ class ApiClientTest {
     client().deleteNote("r1", "n1")
     assertEquals("DELETE /Prod/rides/r1/notes/n1", server.takeRequest().let { "${it.method} ${it.path}" })
   }
+
+  // Slice 3 spec §6.2: the voice of a point memo goes to be turned into text only. Like an ask, a lost response may
+  // already have made one, so only 429 is sent again.
+  @Test
+  fun postTranscription_sends_the_audio_and_tries_again_only_on_a_rate_limit() = runTest {
+    server.enqueue(json(503))
+    val error = runCatching { client().postTranscription(TranscriptionBody("AAAA")) }.exceptionOrNull() as ApiError
+    assertEquals(ApiErrorKind.SERVER, error.kind)
+    assertEquals(1, server.requestCount)
+    server.takeRequest()
+    server.enqueue(json(429))
+    server.enqueue(json(202, """{"transcriptionId":"t1"}"""))
+    assertEquals(TranscriptionAccepted("t1"), client().postTranscription(TranscriptionBody("AAAA")))
+    val request = server.takeRequest()
+    assertEquals("POST /Prod/transcriptions", "${request.method} ${request.path}")
+    assertEquals("AAAA", Json.parseToJsonElement(request.body.readUtf8()).jsonObject["audio"]!!.jsonPrimitive.content)
+  }
+
+  @Test
+  fun getTranscription_reads_what_was_heard_or_why_not() = runTest {
+    server.enqueue(json(200, """{"transcriptionId":"t1","status":"done","text":"展望スペース","failure":null}"""))
+    server.enqueue(json(200, """{"transcriptionId":"t2","status":"failed","text":null,"failure":"no_speech"}"""))
+    assertEquals(TranscriptionResult("t1", "done", "展望スペース", null), client().getTranscription("t1"))
+    assertEquals(TranscriptionResult("t2", "failed", null, "no_speech"), client().getTranscription("t2"))
+    assertEquals("GET /Prod/transcriptions/t1", server.takeRequest().let { "${it.method} ${it.path}" })
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ask/PollingAndConversationTest.kt b/app/src/test/java/com/touringproject/v2/ask/PollingAndConversationTest.kt
index bb5c9f9..08016b0 100644
--- a/app/src/test/java/com/touringproject/v2/ask/PollingAndConversationTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/PollingAndConversationTest.kt
@@ -3,6 +3,7 @@ package com.touringproject.v2.ask
 import com.touringproject.v2.api.ApiError
 import com.touringproject.v2.api.ApiErrorKind
 import com.touringproject.v2.api.AskResult
+import com.touringproject.v2.api.TranscriptionResult
 import kotlinx.coroutines.test.runTest
 import org.junit.Assert.assertEquals
 import org.junit.Assert.assertNull
@@ -22,6 +23,16 @@ class PollingTest {
   private suspend fun poll(clock: Clock, cancelled: () -> Boolean = { false }, get: suspend () -> AskResult) =
     pollUntilDone(get, clock::sleep, { clock.now }, cancelled)
 
+  // Slice 3 spec §7.3: a transcription is fetched on the same schedule as an ask, until it is no longer processing.
+  @Test
+  fun a_transcription_is_polled_like_an_ask_until_it_has_finished() = runTest {
+    val done = TranscriptionResult("t1", "done", "展望スペース")
+    val results = mutableListOf(TranscriptionResult("t1", "processing"), done)
+    val clock = Clock()
+    assertEquals(PollOutcome.Done(done), pollUntil({ results.removeAt(0) }, { it.status == "processing" }, clock::sleep, { clock.now }, { false }))
+    assertEquals(listOf(1_000L, 1_000L), clock.sleeps)
+  }
+
   @Test
   fun delays_are_1s_for_10s_then_2s() {
     assertEquals(1_000L, nextDelay(0))
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ApiClientTest' --tests '*PollingTest' > /tmp/trv2-t1.log 2>&1; grep -c '^e: ' /tmp/trv2-t1.log
```

Expected: `BUILD FAILED`。まだ無い `TranscriptionBody`・`postTranscription`・`pollUntil` を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
index 66889c2..80f1256 100644
--- a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
+++ b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
@@ -62,6 +62,20 @@ interface AskApi {
   suspend fun getAsk(askId: String): AskResult
 }
 
+/** A point memo's voice, to be turned into text only (slice 3 spec §6.2): 16 kHz mono 16-bit PCM in base64, 0.25 to 60 s. */
+@Serializable data class TranscriptionBody(val audio: String)
+
+@Serializable data class TranscriptionAccepted(val transcriptionId: String)
+
+/** status: processing / done / failed. text is set when done; failure (no_speech / transcribe_failed) when failed. */
+@Serializable
+data class TranscriptionResult(val transcriptionId: String, val status: String, val text: String? = null, val failure: String? = null)
+
+interface TranscriptionApi {
+  suspend fun postTranscription(body: TranscriptionBody): TranscriptionAccepted
+  suspend fun getTranscription(transcriptionId: String): TranscriptionResult
+}
+
 // A ride and its route (slice 2 spec §6.2). Times are ISO 8601 with their time zone.
 @Serializable data class SegmentBody(val startedAt: String, val endedAt: String?)
 
@@ -138,7 +152,7 @@ class ApiClient(
   private val maxAttempts: Int = 3,
   timeoutMs: Long = 15_000,
   private val retryDelay: suspend (Long) -> Unit = { delay(it) },
-) : AskApi, RideApi {
+) : AskApi, RideApi, TranscriptionApi {
   private val baseUrl = baseUrl.trimEnd('/')
   // callTimeout bounds the whole exchange, so a stalled connection cannot hang the ask.
   private val http = http.newBuilder().callTimeout(timeoutMs, TimeUnit.MILLISECONDS).build()
@@ -152,6 +166,14 @@ class ApiClient(
 
   override suspend fun getAsk(askId: String): AskResult = json.decodeFromString(request("GET", "/asks/$askId", null, TRANSIENT))
 
+  // Like postAsk: a lost response may already have made a transcription, so only 429 is sent again.
+  override suspend fun postTranscription(body: TranscriptionBody): TranscriptionAccepted = json.decodeFromString(
+    request("POST", "/transcriptions", json.encodeToString(TranscriptionBody.serializer(), body), setOf(ApiErrorKind.RATE_LIMITED)),
+  )
+
+  override suspend fun getTranscription(transcriptionId: String): TranscriptionResult =
+    json.decodeFromString(request("GET", "/transcriptions/$transcriptionId", null, TRANSIENT))
+
   override suspend fun putRide(rideId: String, body: RideBody) {
     request("PUT", "/rides/$rideId", rideJson.encodeToString(RideBody.serializer(), body), TRANSIENT)
   }
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index 56e5d6c..f6b8cb6 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -294,7 +294,7 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       fail(FailureReason.TIMEOUT, run)
       return null
     }
-    val result = (outcome as PollOutcome.Done).result
+    val result = (outcome as PollOutcome.Done<AskResult>).result
     if (!readable(result)) {
       fail(failureFromServer(result.error), run)
       return null
diff --git a/app/src/main/java/com/touringproject/v2/ask/Polling.kt b/app/src/main/java/com/touringproject/v2/ask/Polling.kt
index c6d6ddd..d816a2f 100644
--- a/app/src/main/java/com/touringproject/v2/ask/Polling.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/Polling.kt
@@ -6,7 +6,8 @@ import com.touringproject.v2.api.AskResult
 import kotlinx.coroutines.CancellationException
 import kotlinx.coroutines.withTimeoutOrNull
 
-// Poll schedule from 07 UC-5: every 1 s for 10 s, then every 2 s, give up at 120 s.
+// Poll schedule from 07 UC-5: every 1 s for 10 s, then every 2 s, give up at 120 s. A point memo's transcription is
+// fetched on the same schedule (slice 3 spec §7.3).
 const val POLL_FAST_MS = 1_000L
 const val POLL_SLOW_MS = 2_000L
 const val FAST_WINDOW_MS = 10_000L
@@ -15,19 +16,31 @@ private val FATAL = setOf(ApiErrorKind.INVALID_KEY, ApiErrorKind.BAD_REQUEST, Ap
 
 fun nextDelay(elapsedMs: Long): Long = if (elapsedMs < FAST_WINDOW_MS) POLL_FAST_MS else POLL_SLOW_MS
 
-sealed interface PollOutcome {
-  data class Done(val result: AskResult) : PollOutcome
-  data object Timeout : PollOutcome
-  data object Cancelled : PollOutcome
+sealed interface PollOutcome<out T> {
+  data class Done<T>(val result: T) : PollOutcome<T>
+  data object Timeout : PollOutcome<Nothing>
+  data object Cancelled : PollOutcome<Nothing>
 }
 
-/** Polls until the ask is done. One slow request (up to three tries of 15 s) is cut off at the 120 s limit. */
+/** Polls until the ask is done. */
 suspend fun pollUntilDone(
   get: suspend () -> AskResult,
   sleep: suspend (Long) -> Unit,
   now: () -> Long,
   isCancelled: () -> Boolean,
-): PollOutcome {
+): PollOutcome<AskResult> = pollUntil(get, { it.status == "processing" }, sleep, now, isCancelled)
+
+/**
+ * Polls until pending says the result has finished. One slow request (up to three tries of 15 s) is cut off at the
+ * 120 s limit.
+ */
+suspend fun <T> pollUntil(
+  get: suspend () -> T,
+  pending: (T) -> Boolean,
+  sleep: suspend (Long) -> Unit,
+  now: () -> Long,
+  isCancelled: () -> Boolean,
+): PollOutcome<T> {
   val startedAt = now()
   while (true) {
     val elapsed = now() - startedAt
@@ -38,7 +51,7 @@ suspend fun pollUntilDone(
     if (remaining <= 0) return PollOutcome.Timeout
     try {
       val result = withTimeoutOrNull(remaining) { get() } ?: return PollOutcome.Timeout
-      if (result.status != "processing") return PollOutcome.Done(result)
+      if (!pending(result)) return PollOutcome.Done(result)
     } catch (e: CancellationException) {
       throw e
     } catch (e: ApiError) {
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t1.log 2>&1; tail -1 /tmp/trv2-t1.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト496件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/api/ApiClient.kt \
  app/src/main/java/com/touringproject/v2/ask/AskController.kt \
  app/src/main/java/com/touringproject/v2/ask/Polling.kt \
  app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt \
  app/src/test/java/com/touringproject/v2/ask/PollingAndConversationTest.kt
git commit -m "feat: ask the Backend to turn a voice into text and fetch it on the asks' schedule"
```

---

### Task 2: 声の入力の司令塔（`VoiceInput`）と、聞き取れた文の足し方

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `records/Notes.kt`・`voice/VoiceInput.kt`（新規）
- Test: `records/NotesTest.kt`・`voice/VoiceInputTest.kt`（新規）

**Interfaces:**
- Consumes: Task 1 の `TranscriptionApi`・`pollUntil`・`RouteControl`・`Recorder`・`Source`・`TICK_MS`・`pcmDurationMs`・`cutMemo`
- Produces:
  - `enum class VoicePhase { IDLE, RECORDING, TRANSCRIBING }`・`enum class VoiceFailure(message)`（`NO_SPEECH`・`TRANSCRIBE_FAILED`・`NETWORK`・`MIC`・`KEY`）・`Heard(seq, text)`・`VoiceState(phase, failure, heard)`・`VOICE_IDLE`・`VOICE_LIMIT_MS = 60_000`・`VOICE_MIN_MS = 250`
  - `VoiceDeps(now, sleep, micAllowed, online, api: () -> TranscriptionApi?, route, recorder, cueStart, cueFailure, onState, log)`・`VoiceInput(deps, scope)`: `state`・`attached`・`recording`・`attach()`・`detach()`・`press(source)`・`stop()`・`taken(seq)`
  - `appendHeard(current, heard): String`（`records/Notes.kt`）

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/records/NotesTest.kt b/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
index 1e7956f..a33dd96 100644
--- a/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
+++ b/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
@@ -37,4 +37,14 @@ class NotesTest {
     assertEquals("展望スペース", noteText("  展望スペース \n"))
     assertNull(noteText(" \n "))
   }
+
+  // Slice 3 spec §7.3: what was heard goes at the end of what is written, on a line of its own, within 2000 characters.
+  @Test
+  fun what_was_heard_goes_at_the_end_on_a_line_of_its_own() {
+    assertEquals("展望スペース", appendHeard("", "展望スペース"))
+    assertEquals("料金所の手前\n展望スペース", appendHeard("料金所の手前", "展望スペース"))
+    assertEquals("料金所の手前\n展望スペース", appendHeard("料金所の手前\n", "展望スペース"))
+    val full = appendHeard("あ".repeat(1998), "いうえ")
+    assertEquals(2000, full.codePointCount(0, full.length))
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/voice/VoiceInputTest.kt b/app/src/test/java/com/touringproject/v2/voice/VoiceInputTest.kt
new file mode 100644
index 0000000..49bb8fe
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/voice/VoiceInputTest.kt
@@ -0,0 +1,249 @@
+package com.touringproject.v2.voice
+
+import com.touringproject.v2.api.ApiError
+import com.touringproject.v2.api.ApiErrorKind
+import com.touringproject.v2.api.TranscriptionAccepted
+import com.touringproject.v2.api.TranscriptionApi
+import com.touringproject.v2.api.TranscriptionBody
+import com.touringproject.v2.api.TranscriptionResult
+import com.touringproject.v2.ask.Recorded
+import com.touringproject.v2.ask.Recorder
+import com.touringproject.v2.ask.RouteControl
+import com.touringproject.v2.ask.Source
+import kotlinx.coroutines.CompletableDeferred
+import kotlinx.coroutines.delay
+import kotlinx.coroutines.test.TestScope
+import kotlinx.coroutines.test.advanceTimeBy
+import kotlinx.coroutines.test.advanceUntilIdle
+import kotlinx.coroutines.test.runCurrent
+import kotlinx.coroutines.test.runTest
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
+import org.junit.Test
+
+/** 1 s of 16 kHz mono 16-bit PCM. */
+private val ONE_SECOND = ByteArray(32_000)
+
+/** A fake world around the voice input that records what it was asked to do, in order. */
+private class VoiceHarness(
+  val scope: TestScope,
+  var online: Boolean = true,
+  val micAllowed: Boolean = true,
+  val hasKey: Boolean = true,
+  val recorderError: Exception? = null,
+  var pcm: ByteArray = ONE_SECOND,
+  val postError: Exception? = null,
+  /** What each GET answers, in turn; the last one repeats. */
+  val results: MutableList<TranscriptionResult> = mutableListOf(TranscriptionResult("t1", "done", "展望スペース")),
+  var getGate: CompletableDeferred<Unit>? = null,
+) {
+  val log = mutableListOf<String>()
+  val states = mutableListOf<VoiceState>()
+  val api = object : TranscriptionApi {
+    override suspend fun postTranscription(body: TranscriptionBody): TranscriptionAccepted {
+      log += "post:${body.audio.length}"
+      postError?.let { throw it }
+      return TranscriptionAccepted("t1")
+    }
+    override suspend fun getTranscription(transcriptionId: String): TranscriptionResult {
+      log += "get"
+      getGate?.await()
+      return if (results.size > 1) results.removeAt(0) else results[0]
+    }
+  }
+  val voice = VoiceInput(
+    VoiceDeps(
+      now = { scope.testScheduler.currentTime },
+      sleep = { delay(it) },
+      micAllowed = { micAllowed },
+      online = { online },
+      api = { if (hasKey) api else null },
+      route = object : RouteControl {
+        override suspend fun start(source: Source): Boolean {
+          log += "route:${source.name.lowercase()}"
+          return true
+        }
+        override suspend fun stop() { log += "route:stop" }
+        override fun inputDevice() = null
+      },
+      recorder = object : Recorder {
+        override suspend fun start() { log += "rec:start"; recorderError?.let { throw it } }
+        override suspend fun stop(): Recorded { log += "rec:stop"; return Recorded(pcm, "voice.pcm") }
+        override suspend fun cancel() { log += "rec:cancel" }
+      },
+      cueStart = { log += "cue:start" },
+      cueFailure = { log += "cue:failure" },
+      onState = { states += it },
+      log = { _, _ -> },
+    ),
+    scope,
+  )
+}
+
+class VoiceInputTest {
+  // Slice 3 spec §7.3: press to record, press again to stop and send; what was heard comes back to be added.
+  @Test
+  fun a_second_press_stops_the_recording_and_what_was_heard_comes_back() = runTest {
+    val h = VoiceHarness(this)
+    h.voice.press(Source.SCREEN)
+    runCurrent()
+    assertEquals(VoicePhase.RECORDING, h.voice.state.phase)
+    advanceTimeBy(3_000)
+    h.voice.press(Source.SCREEN)
+    advanceUntilIdle()
+    assertEquals(listOf("route:screen", "rec:start", "cue:start", "rec:stop", "route:stop", "post:${ONE_SECOND.size / 3 * 4 + 4}", "get"), h.log)
+    assertEquals(Heard(1, "展望スペース"), h.voice.state.heard)
+    assertEquals(VoicePhase.IDLE, h.voice.state.phase)
+    assertTrue(h.states.any { it.phase == VoicePhase.TRANSCRIBING })
+  }
+
+  @Test
+  fun the_recording_stops_by_itself_after_60_seconds() = runTest {
+    val h = VoiceHarness(this)
+    h.voice.press(Source.HANDSFREE)
+    advanceTimeBy(VOICE_LIMIT_MS - 1_000)
+    assertEquals(VoicePhase.RECORDING, h.voice.state.phase)
+    advanceUntilIdle()
+    assertEquals(Heard(1, "展望スペース"), h.voice.state.heard)
+    assertTrue("rec:stop" in h.log)
+  }
+
+  // The result is fetched every second at first, as an ask's is, until it is no longer processing.
+  @Test
+  fun the_text_is_fetched_until_it_is_ready() = runTest {
+    val h = VoiceHarness(this, results = mutableListOf(TranscriptionResult("t1", "processing"), TranscriptionResult("t1", "processing"), TranscriptionResult("t1", "done", " 給油 ")))
+    h.voice.press(Source.SCREEN)
+    runCurrent()
+    h.voice.press(Source.SCREEN)
+    advanceUntilIdle()
+    assertEquals(3, h.log.count { it == "get" })
+    assertEquals(Heard(1, "給油"), h.voice.state.heard)
+  }
+
+  // Taking what was heard clears it, so the screen adds it once; the next one gets a new number.
+  @Test
+  fun what_was_heard_is_taken_once_and_the_next_one_is_numbered_anew() = runTest {
+    val h = VoiceHarness(this)
+    repeat(2) {
+      h.voice.press(Source.SCREEN)
+      runCurrent()
+      h.voice.press(Source.SCREEN)
+      advanceUntilIdle()
+      val heard = h.voice.state.heard!!
+      assertEquals(it + 1, heard.seq)
+      h.voice.taken(heard.seq)
+      assertNull(h.voice.state.heard)
+    }
+  }
+
+  // Slice 3 spec §7.3: without a network the voice cannot be sent; the intercom button only gets the failure cue.
+  @Test
+  fun without_a_network_a_press_records_nothing_and_gives_the_failure_cue() = runTest {
+    val h = VoiceHarness(this, online = false)
+    h.voice.press(Source.HANDSFREE)
+    advanceUntilIdle()
+    assertEquals(listOf("cue:failure"), h.log)
+    assertEquals(VOICE_IDLE, h.voice.state)
+  }
+
+  @Test
+  fun a_press_while_the_text_is_being_made_does_nothing() = runTest {
+    val h = VoiceHarness(this, getGate = CompletableDeferred())
+    h.voice.press(Source.SCREEN)
+    runCurrent()
+    h.voice.press(Source.SCREEN)
+    advanceTimeBy(1_500)
+    assertEquals(VoicePhase.TRANSCRIBING, h.voice.state.phase)
+    h.voice.press(Source.SCREEN)
+    runCurrent()
+    assertEquals(1, h.log.count { it == "rec:start" })
+    h.getGate!!.complete(Unit)
+    advanceUntilIdle()
+    assertEquals("展望スペース", h.voice.state.heard?.text)
+  }
+
+  @Test
+  fun the_reason_of_a_failure_is_told_with_the_failure_cue() = runTest {
+    val cases = listOf(
+      VoiceHarness(this, micAllowed = false) to VoiceFailure.MIC,
+      VoiceHarness(this, recorderError = IllegalStateException("busy")) to VoiceFailure.MIC,
+      VoiceHarness(this, pcm = ByteArray(0)) to VoiceFailure.MIC,
+      VoiceHarness(this, pcm = ByteArray(32 * 200)) to VoiceFailure.NO_SPEECH,
+      VoiceHarness(this, hasKey = false) to VoiceFailure.KEY,
+      VoiceHarness(this, postError = ApiError(ApiErrorKind.INVALID_KEY)) to VoiceFailure.KEY,
+      VoiceHarness(this, postError = ApiError(ApiErrorKind.NETWORK)) to VoiceFailure.NETWORK,
+      VoiceHarness(this, results = mutableListOf(TranscriptionResult("t1", "failed", failure = "no_speech"))) to VoiceFailure.NO_SPEECH,
+      VoiceHarness(this, results = mutableListOf(TranscriptionResult("t1", "done", " "))) to VoiceFailure.NO_SPEECH,
+      VoiceHarness(this, results = mutableListOf(TranscriptionResult("t1", "failed", failure = "transcribe_failed"))) to VoiceFailure.TRANSCRIBE_FAILED,
+      VoiceHarness(this, results = mutableListOf(TranscriptionResult("t1", "processing"))) to VoiceFailure.NETWORK,
+    )
+    cases.forEach { (h, failure) ->
+      h.voice.press(Source.SCREEN)
+      runCurrent()
+      h.voice.press(Source.SCREEN)
+      advanceUntilIdle()
+      assertEquals(VoiceState(failure = failure), h.voice.state)
+      assertEquals("cue:failure", h.log.last())
+    }
+  }
+
+  // A recording too short for the Backend (under 0.25 s) is not sent at all.
+  @Test
+  fun a_recording_too_short_is_not_sent() = runTest {
+    val h = VoiceHarness(this, pcm = ByteArray(32 * 200))
+    h.voice.press(Source.SCREEN)
+    runCurrent()
+    h.voice.press(Source.SCREEN)
+    advanceUntilIdle()
+    assertTrue(h.log.none { it.startsWith("post") })
+  }
+
+  @Test
+  fun a_new_recording_clears_the_reason_of_the_last_failure() = runTest {
+    val h = VoiceHarness(this, results = mutableListOf(TranscriptionResult("t1", "failed", failure = "no_speech"), TranscriptionResult("t1", "done", "二度目")))
+    h.voice.press(Source.SCREEN)
+    runCurrent()
+    h.voice.press(Source.SCREEN)
+    advanceUntilIdle()
+    assertEquals(VoiceFailure.NO_SPEECH, h.voice.state.failure)
+    h.voice.press(Source.SCREEN)
+    runCurrent()
+    assertEquals(VoiceState(VoicePhase.RECORDING), h.voice.state)
+  }
+
+  // Leaving SC-19 drops what is going on; a result that comes later is not added anywhere.
+  @Test
+  fun leaving_drops_the_recording_or_the_text_still_being_made() = runTest {
+    val recording = VoiceHarness(this)
+    recording.voice.attach()
+    recording.voice.press(Source.SCREEN)
+    runCurrent()
+    recording.voice.detach()
+    advanceUntilIdle()
+    assertEquals(listOf("route:screen", "rec:start", "cue:start", "rec:cancel", "route:stop"), recording.log)
+    assertEquals(VOICE_IDLE, recording.voice.state)
+    assertEquals(false, recording.voice.attached)
+
+    val making = VoiceHarness(this, getGate = CompletableDeferred())
+    making.voice.press(Source.SCREEN)
+    runCurrent()
+    making.voice.press(Source.SCREEN)
+    advanceTimeBy(1_500)
+    making.voice.detach()
+    making.getGate!!.complete(Unit)
+    advanceUntilIdle()
+    assertEquals(VOICE_IDLE, making.voice.state)
+  }
+
+  // The headset ending its voice recognition is the second press of the intercom button.
+  @Test
+  fun the_headset_ending_the_session_stops_the_recording() = runTest {
+    val h = VoiceHarness(this)
+    h.voice.press(Source.HANDSFREE)
+    runCurrent()
+    h.voice.stop()
+    advanceUntilIdle()
+    assertEquals(Heard(1, "展望スペース"), h.voice.state.heard)
+  }
+}
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*VoiceInputTest' --tests '*NotesTest' > /tmp/trv2-t2.log 2>&1; grep -c '^e: ' /tmp/trv2-t2.log
```

Expected: `BUILD FAILED`。まだ無い `VoiceInput`・`appendHeard` を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/records/Notes.kt b/app/src/main/java/com/touringproject/v2/records/Notes.kt
index b65757a..ec00298 100644
--- a/app/src/main/java/com/touringproject/v2/records/Notes.kt
+++ b/app/src/main/java/com/touringproject/v2/records/Notes.kt
@@ -58,3 +58,7 @@ fun noteDraft(id: String, rideId: String, at: Long, recent: List<RoutePoint>): N
   val sample = pickHeadingSample(fixes, Fix(newest.lat, newest.lon, newest.t, newest.accuracy))
   return NoteDraft(id, rideId, at, newest.lat, newest.lon, sample?.latitude, sample?.longitude, sample?.let { Instant.parse(it.at).toEpochMilli() })
 }
+
+/** SC-19's voice input: what was heard goes at the end of what is written, on a line of its own, within 2000 characters. */
+fun appendHeard(current: String, heard: String): String =
+  cutMemo(if (current.isEmpty() || current.endsWith("\n")) current + heard else current + "\n" + heard)
diff --git a/app/src/main/java/com/touringproject/v2/voice/VoiceInput.kt b/app/src/main/java/com/touringproject/v2/voice/VoiceInput.kt
new file mode 100644
index 0000000..c41c851
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/voice/VoiceInput.kt
@@ -0,0 +1,223 @@
+package com.touringproject.v2.voice
+
+import com.touringproject.v2.api.ApiError
+import com.touringproject.v2.api.ApiErrorKind
+import com.touringproject.v2.api.TranscriptionApi
+import com.touringproject.v2.api.TranscriptionBody
+import com.touringproject.v2.api.TranscriptionResult
+import com.touringproject.v2.ask.PollOutcome
+import com.touringproject.v2.ask.Recorder
+import com.touringproject.v2.ask.RouteControl
+import com.touringproject.v2.ask.Source
+import com.touringproject.v2.ask.TICK_MS
+import com.touringproject.v2.ask.pcmDurationMs
+import com.touringproject.v2.ask.pollUntil
+import kotlinx.coroutines.CancellationException
+import kotlinx.coroutines.CoroutineScope
+import kotlinx.coroutines.launch
+import java.util.Base64
+
+// The voice input of SC-19 (slice 3 spec §7.3): recorded over the same route and with the same kind of recorder as an
+// ask, sent to be turned into text only (UC-6), and fetched on the asks' schedule. What was heard is added to the text
+// by the screen. The voice is kept nowhere on the device.
+enum class VoicePhase { IDLE, RECORDING, TRANSCRIBING }
+
+/** Why no text came, told under the field with what to do next (slice 3 plan 4, settled with the rider). */
+enum class VoiceFailure(val message: String) {
+  NO_SPEECH("声が聞き取れませんでした。もう一度話してください。"),
+  TRANSCRIBE_FAILED("声を文字にできませんでした。もう一度試すか、文字で書いてください。"),
+  NETWORK("通信できないため、文字にできませんでした。文字で書けば保存できます。"),
+  MIC("マイクを使えませんでした。マイクの許可を確かめてください。"),
+  KEY("接続キーを使えないため、文字にできませんでした。文字で書けば保存できます。"),
+}
+
+/** What was heard, numbered so the screen adds each one once. */
+data class Heard(val seq: Int, val text: String)
+
+data class VoiceState(val phase: VoicePhase = VoicePhase.IDLE, val failure: VoiceFailure? = null, val heard: Heard? = null)
+
+val VOICE_IDLE = VoiceState()
+
+/** The longest voice the Backend takes (slice 3 spec §6.2); the recording stops by itself then. */
+const val VOICE_LIMIT_MS = 60_000L
+
+/** The shortest the Backend takes; a shorter one is taken as nothing said. */
+const val VOICE_MIN_MS = 250L
+
+class VoiceDeps(
+  val now: () -> Long,
+  val sleep: suspend (Long) -> Unit,
+  val micAllowed: () -> Boolean,
+  /** Whether the device has a network now (slice 3 spec §7.3: without one, the voice cannot be sent). */
+  val online: () -> Boolean,
+  /** The client for the current key and user name, or null while there is no key or no API URL. */
+  val api: () -> TranscriptionApi?,
+  val route: RouteControl,
+  val recorder: Recorder,
+  val cueStart: () -> Unit,
+  val cueFailure: () -> Unit,
+  val onState: (VoiceState) -> Unit,
+  val log: (event: String, data: Map<String, Any?>) -> Unit,
+)
+
+/**
+ * Call it from one thread only (the main thread in the app), like the ask loop. SC-19 attaches it while it is shown:
+ * the intercom button then goes here instead of starting an ask (spec §7.3). Leaving SC-19 drops whatever is going on;
+ * whatever the run is awaiting is ignored when it returns.
+ */
+class VoiceInput(private val deps: VoiceDeps, private val scope: CoroutineScope) {
+  var state: VoiceState = VOICE_IDLE
+    private set
+
+  /** True while SC-19 is shown. */
+  var attached = false
+    private set
+
+  val recording: Boolean get() = state.phase == VoicePhase.RECORDING
+
+  private var session = 0
+  private var heardSeq = 0
+  private var stopRequested = false
+  // From a start until its run has unwound, also after a leave: a second run must not share the recorder and the route.
+  private var running = false
+
+  fun attach() {
+    attached = true
+  }
+
+  fun detach() {
+    attached = false
+    cancel()
+  }
+
+  /** "🎤 声で入力" and the intercom button: start, or stop and send. Nothing while the text is being made. */
+  fun press(source: Source) {
+    when (state.phase) {
+      VoicePhase.RECORDING -> stop()
+      VoicePhase.TRANSCRIBING -> Unit
+      VoicePhase.IDLE -> {
+        if (running) return
+        // The screen's button cannot be pressed without a network; the intercom button gets the failure cue.
+        if (!deps.online()) {
+          deps.cueFailure()
+          return
+        }
+        running = true
+        val s = ++session
+        scope.launch {
+          try {
+            run(s, source)
+          } finally {
+            running = false
+          }
+        }
+      }
+    }
+  }
+
+  /** The second press, or the headset ending its voice recognition. */
+  fun stop() {
+    if (state.phase == VoicePhase.RECORDING) stopRequested = true
+  }
+
+  /** The screen has added what was heard. */
+  fun taken(seq: Int) {
+    if (state.heard?.seq == seq) set(state.copy(heard = null))
+  }
+
+  private fun cancel() {
+    session += 1
+    if (state != VOICE_IDLE) set(VOICE_IDLE)
+  }
+
+  private suspend fun run(s: Int, source: Source) {
+    val d = deps
+    stopRequested = false
+    set(VoiceState(VoicePhase.RECORDING))
+    if (!d.micAllowed()) return fail(s, VoiceFailure.MIC)
+    try {
+      d.route.start(source)
+    } catch (e: CancellationException) {
+      throw e
+    } catch (e: Exception) {
+      // Without the intercom route the phone's own microphone records, as for an ask.
+      d.log("voice_route_failed", mapOf("error" to e.toString()))
+    }
+    if (!isCurrent(s)) return d.route.stop()
+    try {
+      d.recorder.start()
+    } catch (e: CancellationException) {
+      throw e
+    } catch (e: Exception) {
+      d.route.stop()
+      return fail(s, VoiceFailure.MIC)
+    }
+    if (!isCurrent(s)) {
+      d.recorder.cancel()
+      return d.route.stop()
+    }
+    d.cueStart()
+    val startedAt = d.now()
+    while (isCurrent(s) && !stopRequested && d.now() - startedAt < VOICE_LIMIT_MS) d.sleep(TICK_MS)
+    if (!isCurrent(s)) {
+      d.recorder.cancel()
+      return d.route.stop()
+    }
+    val pcm = try {
+      d.recorder.stop().pcm
+    } catch (e: CancellationException) {
+      throw e
+    } catch (e: Exception) {
+      d.route.stop()
+      return fail(s, VoiceFailure.MIC)
+    }
+    d.route.stop()
+    if (!isCurrent(s)) return
+    // A microphone held by another app can start without delivering anything.
+    if (pcm.isEmpty()) return fail(s, VoiceFailure.MIC)
+    if (pcmDurationMs(pcm.size) < VOICE_MIN_MS) return fail(s, VoiceFailure.NO_SPEECH)
+    val api = d.api() ?: return fail(s, VoiceFailure.KEY)
+    set(VoiceState(VoicePhase.TRANSCRIBING))
+    val result = try {
+      val accepted = api.postTranscription(TranscriptionBody(Base64.getEncoder().encodeToString(pcm)))
+      if (!isCurrent(s)) return
+      when (val outcome = pollUntil({ api.getTranscription(accepted.transcriptionId) }, { it.status == "processing" }, d.sleep, d.now) { !isCurrent(s) }) {
+        is PollOutcome.Done -> outcome.result
+        PollOutcome.Timeout -> return fail(s, VoiceFailure.NETWORK)
+        PollOutcome.Cancelled -> return
+      }
+    } catch (e: CancellationException) {
+      throw e
+    } catch (e: Exception) {
+      d.log("voice_send_failed", mapOf("error" to e.toString()))
+      return fail(s, failureFor(e))
+    }
+    if (!isCurrent(s)) return
+    val text = result.text?.trim()
+    when {
+      result.status == "done" && !text.isNullOrEmpty() -> set(VoiceState(heard = Heard(++heardSeq, text)))
+      result.status == "done" || result.failure == "no_speech" -> fail(s, VoiceFailure.NO_SPEECH)
+      else -> fail(s, VoiceFailure.TRANSCRIBE_FAILED)
+    }
+  }
+
+  private fun failureFor(e: Exception): VoiceFailure = when ((e as? ApiError)?.kind) {
+    ApiErrorKind.INVALID_KEY -> VoiceFailure.KEY
+    // The Backend refuses a voice it cannot take (too short or too long): nothing usable was said.
+    ApiErrorKind.BAD_REQUEST -> VoiceFailure.NO_SPEECH
+    else -> VoiceFailure.NETWORK
+  }
+
+  private fun fail(s: Int, failure: VoiceFailure) {
+    if (!isCurrent(s)) return
+    set(VoiceState(failure = failure))
+    deps.cueFailure()
+  }
+
+  private fun isCurrent(s: Int) = s == session
+
+  private fun set(next: VoiceState) {
+    state = next
+    deps.onState(next)
+  }
+}
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t2.log 2>&1; tail -1 /tmp/trv2-t2.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト508件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/records/Notes.kt \
  app/src/main/java/com/touringproject/v2/voice/VoiceInput.kt \
  app/src/test/java/com/touringproject/v2/records/NotesTest.kt \
  app/src/test/java/com/touringproject/v2/voice/VoiceInputTest.kt
git commit -m "feat: record a point memo's voice, have it turned into text and tell why when it could not be"
```

---

### Task 3: インカムのボタンの行き先・通信の状態・`AppGraph` の組み立て

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `AppGraph.kt`・`handsfree/PressRouter.kt`・`net/Connectivity.kt`（新規）
- Test: `handsfree/PressRouterTest.kt`・`net/ConnectivityTest.kt`（新規）

**Interfaces:**
- Consumes: Task 2 の `VoiceInput`・`VoiceDeps`・`VoiceState`
- Produces:
  - `PressRouter(..., askBusy = { false }, voiceAttached = { false }, voicePress = {}, voiceRecording = { false }, voiceStop = {})`。SC-19 のあいだの押下は声の入力へ（質問が進んでいるときは質問のまま）、ヘッドセットが音声認識を終えたら声の録音を止める
  - `Connectivity(context).online: StateFlow<Boolean>`（`net/Connectivity.kt`）
  - `AppGraph.connectivity`・`AppGraph.voice: VoiceInput`・`AppGraph.voiceState: StateFlow<VoiceState>`

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/handsfree/PressRouterTest.kt b/app/src/test/java/com/touringproject/v2/handsfree/PressRouterTest.kt
index 988ef18..44584d2 100644
--- a/app/src/test/java/com/touringproject/v2/handsfree/PressRouterTest.kt
+++ b/app/src/test/java/com/touringproject/v2/handsfree/PressRouterTest.kt
@@ -7,6 +7,9 @@ class PressRouterTest {
   private val log = mutableListOf<String>()
   private var trialActive = false
   private var trialBusy = false
+  private var askBusy = false
+  private var noteOpen = false
+  private var voiceRecording = false
   private val router = PressRouter(
     trialActive = { trialActive },
     trialBusy = { trialBusy || trialActive },
@@ -15,6 +18,11 @@ class PressRouterTest {
     askPress = { log += "ask:press" },
     askStopRecording = { log += "ask:stopRecording" },
     askTap = { log += "ask:tap" },
+    askBusy = { askBusy },
+    voiceAttached = { noteOpen },
+    voicePress = { log += "voice:press" },
+    voiceRecording = { voiceRecording },
+    voiceStop = { log += "voice:stop" },
   )
 
   @Test
@@ -53,4 +61,23 @@ class PressRouterTest {
     router.recognitionEnded()
     assertEquals(listOf("ask:stopRecording"), log)
   }
+
+  // Slice 3 spec §7.3: while SC-19 is shown, the intercom button starts and stops its voice input, not an ask.
+  @Test
+  fun while_sc19_is_shown_a_press_goes_to_the_voice_input_and_its_end_stops_it() {
+    noteOpen = true
+    router.press()
+    voiceRecording = true
+    router.recognitionEnded()
+    assertEquals(listOf("voice:press", "voice:stop"), log)
+  }
+
+  // An ask already under way keeps the button: its recording is stopped, or the rider hears that it is busy.
+  @Test
+  fun an_ask_under_way_keeps_the_button_even_on_sc19() {
+    noteOpen = true
+    askBusy = true
+    router.press()
+    assertEquals(listOf("check:stop", "ask:press"), log)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt b/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt
new file mode 100644
index 0000000..85bcfd0
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt
@@ -0,0 +1,36 @@
+package com.touringproject.v2.net
+
+import android.app.Application
+import android.net.ConnectivityManager
+import android.net.NetworkCapabilities
+import androidx.test.core.app.ApplicationProvider
+import androidx.test.ext.junit.runners.AndroidJUnit4
+import org.junit.Assert.assertFalse
+import org.junit.Assert.assertTrue
+import org.junit.Test
+import org.junit.runner.RunWith
+import org.robolectric.Shadows.shadowOf
+import org.robolectric.shadows.ShadowNetworkCapabilities
+
+// Slice 3 spec §7.3: SC-19 follows whether the device has a network.
+@RunWith(AndroidJUnit4::class)
+class ConnectivityTest {
+  private val app = ApplicationProvider.getApplicationContext<Application>()
+  private val manager = app.getSystemService(ConnectivityManager::class.java)
+
+  @Test
+  fun the_state_follows_the_default_network() {
+    // The app's own graph has registered one already; the new one is this test's.
+    val before = shadowOf(manager).networkCallbacks.toSet()
+    val connectivity = Connectivity(app)
+    val callback = (shadowOf(manager).networkCallbacks - before).single()
+    val network = manager.activeNetwork!!
+    callback.onLost(network)
+    assertFalse(connectivity.online.value)
+    val caps = ShadowNetworkCapabilities.newInstance().also { shadowOf(it).addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) }
+    callback.onCapabilitiesChanged(network, caps)
+    assertTrue(connectivity.online.value)
+    callback.onCapabilitiesChanged(network, ShadowNetworkCapabilities.newInstance())
+    assertFalse(connectivity.online.value)
+  }
+}
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*PressRouterTest' --tests '*ConnectivityTest' > /tmp/trv2-t3.log 2>&1; grep -c '^e: ' /tmp/trv2-t3.log
```

Expected: `BUILD FAILED`。まだ無い `PressRouter` の引数と `Connectivity` を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 18bd73f..df913e0 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -11,6 +11,7 @@ import com.touringproject.v2.ask.AskDeps
 import com.touringproject.v2.ask.ConversationState
 import com.touringproject.v2.ask.FlowState
 import com.touringproject.v2.ask.IDLE
+import com.touringproject.v2.ask.Source
 import com.touringproject.v2.ask.isBusy
 import com.touringproject.v2.ask.rideNow
 import com.touringproject.v2.audio.AudioRoute
@@ -27,6 +28,7 @@ import com.touringproject.v2.location.FusedRouteSource
 import com.touringproject.v2.location.PositionTracker
 import com.touringproject.v2.location.RouteSource
 import com.touringproject.v2.nav.AppLauncher
+import com.touringproject.v2.net.Connectivity
 import com.touringproject.v2.recordings.RecordingCheck
 import com.touringproject.v2.recordings.RecordingKeeper
 import com.touringproject.v2.recordings.RecordingStore
@@ -59,6 +61,10 @@ import com.touringproject.v2.store.RoomRideStore
 import com.touringproject.v2.store.RoomSyncStore
 import com.touringproject.v2.sync.RideSync
 import com.touringproject.v2.sync.credentialChanges
+import com.touringproject.v2.voice.VOICE_IDLE
+import com.touringproject.v2.voice.VoiceDeps
+import com.touringproject.v2.voice.VoiceInput
+import com.touringproject.v2.voice.VoiceState
 import kotlinx.coroutines.CoroutineScope
 import kotlinx.coroutines.MainScope
 import kotlinx.coroutines.delay
@@ -199,6 +205,34 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     Log.w("trv2.recordings", message, e)
   }
 
+  /** Whether the device has a network now (SC-19's voice input). */
+  val connectivity = Connectivity(context)
+
+  private val voiceFlow = MutableStateFlow(VOICE_IDLE)
+  val voiceState: StateFlow<VoiceState> = voiceFlow.asStateFlow()
+
+  // SC-19's voice input: its own route control and recorder, like SC-12's trial, so nothing is shared with the ask loop.
+  val voice = VoiceInput(
+    VoiceDeps(
+      now = System::currentTimeMillis,
+      sleep = { delay(it) },
+      micAllowed = micAllowed,
+      online = { connectivity.online.value },
+      api = {
+        val key = apiKeys.current()
+        val user = settings.settings.value?.userName
+        if (apiBaseUrl.isEmpty() || key == null || user == null) null else ApiClient(apiBaseUrl, key, user, http)
+      },
+      route = AudioRouteControl(audioRoute),
+      recorder = PcmRecorder(),
+      cueStart = cues::start,
+      cueFailure = cues::failure,
+      onState = { voiceFlow.value = it },
+      log = { event, data -> Log.i("trv2.note", "$event $data") },
+    ),
+    scope,
+  )
+
   // The media volume at which the rider closed the low-volume band; kept until the process ends (slice 1 spec §5.6).
   private val volumeDismissed = MutableStateFlow<Int?>(null)
   val volumeDismissedAt: StateFlow<Int?> = volumeDismissed.asStateFlow()
@@ -215,6 +249,11 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     askPress = controller::press,
     askStopRecording = controller::stopRecording,
     askTap = controller::tapToTalk,
+    askBusy = { isBusy(controller.state) },
+    voiceAttached = { voice.attached },
+    voicePress = { voice.press(Source.HANDSFREE) },
+    voiceRecording = { voice.recording },
+    voiceStop = voice::stop,
   )
 
   /** The screen's "押して話す", routed like an intercom press so it waits for a left trial to unwind. */
diff --git a/app/src/main/java/com/touringproject/v2/handsfree/PressRouter.kt b/app/src/main/java/com/touringproject/v2/handsfree/PressRouter.kt
index 4de3bb0..ad7cfc0 100644
--- a/app/src/main/java/com/touringproject/v2/handsfree/PressRouter.kt
+++ b/app/src/main/java/com/touringproject/v2/handsfree/PressRouter.kt
@@ -1,8 +1,9 @@
 package com.touringproject.v2.handsfree
 
 /**
- * Where an intercom press goes. A running trial recording takes it (US-E-03.002: no question starts); otherwise a
- * kept recording playing on SC-12 is stopped first, since the microphone would pick it up, and the ask loop gets it.
+ * Where an intercom press goes. A running trial recording takes it (US-E-03.002: no question starts). While SC-19 is
+ * shown, its voice input takes it, unless an ask is already under way (slice 3 spec §7.3). Otherwise a kept recording
+ * playing on SC-12 is stopped first, since the microphone would pick it up, and the ask loop gets it.
  * While a trial that was left is still unwinding (up to the 3 s SCO setup), presses start nothing: the old trial may
  * still set up or release SCO, which would break the new ask's intercom route.
  */
@@ -14,6 +15,11 @@ class PressRouter(
   private val askPress: () -> Unit,
   private val askStopRecording: () -> Unit,
   private val askTap: () -> Unit,
+  private val askBusy: () -> Boolean = { false },
+  private val voiceAttached: () -> Boolean = { false },
+  private val voicePress: () -> Unit = {},
+  private val voiceRecording: () -> Boolean = { false },
+  private val voiceStop: () -> Unit = {},
 ) {
   fun press() {
     if (trialActive()) {
@@ -21,6 +27,10 @@ class PressRouter(
       return
     }
     if (trialBusy()) return
+    if (voiceAttached() && !askBusy()) {
+      voicePress()
+      return
+    }
     stopCheckPlayback()
     askPress()
   }
@@ -32,6 +42,10 @@ class PressRouter(
 
   /** The headset dropping SCO during a voice-recognition session is the second press. */
   fun recognitionEnded() {
-    if (trialActive()) stopTrial() else askStopRecording()
+    when {
+      trialActive() -> stopTrial()
+      voiceRecording() -> voiceStop()
+      else -> askStopRecording()
+    }
   }
 }
diff --git a/app/src/main/java/com/touringproject/v2/net/Connectivity.kt b/app/src/main/java/com/touringproject/v2/net/Connectivity.kt
new file mode 100644
index 0000000..add4ecb
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/net/Connectivity.kt
@@ -0,0 +1,35 @@
+package com.touringproject.v2.net
+
+import android.content.Context
+import android.net.ConnectivityManager
+import android.net.Network
+import android.net.NetworkCapabilities
+import kotlinx.coroutines.flow.MutableStateFlow
+import kotlinx.coroutines.flow.StateFlow
+import kotlinx.coroutines.flow.asStateFlow
+
+/**
+ * Whether the device's default network reaches the internet, followed for the life of the process (slice 3 spec §7.3:
+ * SC-19 cannot send a voice without one). It says nothing of whether the Backend answers; a send can still fail.
+ */
+class Connectivity(context: Context) {
+  private val manager = context.getSystemService(ConnectivityManager::class.java)
+  private val state = MutableStateFlow(manager.activeNetwork?.let { manager.getNetworkCapabilities(it) }.reaches())
+  val online: StateFlow<Boolean> = state.asStateFlow()
+
+  init {
+    manager.registerDefaultNetworkCallback(
+      object : ConnectivityManager.NetworkCallback() {
+        override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) {
+          state.value = capabilities.reaches()
+        }
+
+        override fun onLost(network: Network) {
+          state.value = false
+        }
+      },
+    )
+  }
+}
+
+private fun NetworkCapabilities?.reaches() = this?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t3.log 2>&1; tail -1 /tmp/trv2-t3.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト511件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt \
  app/src/main/java/com/touringproject/v2/handsfree/PressRouter.kt \
  app/src/main/java/com/touringproject/v2/net/Connectivity.kt \
  app/src/test/java/com/touringproject/v2/handsfree/PressRouterTest.kt \
  app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt
git commit -m "feat: route the intercom button to SC-19's voice input while it is shown, and follow the network"
```

---

### Task 4: SC-19 の声の入力の欄と、SC-19 のあいだのつなぎ

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `ui/AppUi.kt`・`ui/MemoScreen.kt`・`ui/NoteScreen.kt`・`ui/RecordsRoutes.kt`
- Test: `ui/NoteRoutesTest.kt`・`ui/NoteScreenTest.kt`

**Interfaces:**
- Consumes: Task 2 の `VoicePhase`・`Heard`・`VoiceFailure.message`・`appendHeard`・`VoiceInput.attach`/`detach`/`press`/`taken`・Task 3 の `AppGraph.voice`・`voiceState`・`connectivity`
- Produces:
  - `MemoEditor(..., heard: Heard? = null, onHeard: (Int) -> Unit = {})`
  - `NoteVoiceUi(phase, failure: String?, heard: Heard?, online)`・`NoteScreen(..., voice: NoteVoiceUi? = null, onVoice = {}, onHeard = {})`（タグ `voice`・`voiceFailure`）
  - `NoteVoice(input, state, online)`・`NewNoteRoute(..., voice: NoteVoice? = null)`・`NoteRoute(..., voice: NoteVoice? = null)`（SC-19 が出ているあいだ `attach`）

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt b/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
index 3f8b650..e4f049a 100644
--- a/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
@@ -17,9 +17,23 @@ import com.touringproject.v2.store.RideDatabase
 import com.touringproject.v2.store.RoomNotes
 import com.touringproject.v2.store.RoomRecords
 import com.touringproject.v2.store.RoomRideStore
+import com.touringproject.v2.ask.Recorded
+import com.touringproject.v2.ask.Recorder
+import com.touringproject.v2.ask.RouteControl
+import com.touringproject.v2.ask.Source
+import com.touringproject.v2.voice.VOICE_IDLE
+import com.touringproject.v2.voice.VoiceDeps
+import com.touringproject.v2.voice.VoiceInput
+import androidx.compose.runtime.getValue
+import androidx.compose.runtime.mutableStateOf
+import androidx.compose.runtime.setValue
+import kotlinx.coroutines.MainScope
+import kotlinx.coroutines.flow.MutableStateFlow
 import kotlinx.coroutines.runBlocking
 import org.junit.After
 import org.junit.Assert.assertEquals
+import org.junit.Assert.assertFalse
+import org.junit.Assert.assertTrue
 import org.junit.Assert.assertNull
 import org.junit.Rule
 import org.junit.Test
@@ -74,4 +88,34 @@ class NoteRoutesTest {
     assertEquals(1, closed)
     assertNull(runBlocking { db.notes().note("n1") })
   }
+
+  private val idleRoute = object : RouteControl {
+    override suspend fun start(source: Source) = true
+    override suspend fun stop() = Unit
+    override fun inputDevice() = null
+  }
+  private val idleRecorder = object : Recorder {
+    override suspend fun start() = Unit
+    override suspend fun stop() = Recorded(ByteArray(0), "voice.pcm")
+    override suspend fun cancel() = Unit
+  }
+  private val input = VoiceInput(
+    VoiceDeps({ 0 }, {}, { true }, { true }, { null }, idleRoute, idleRecorder, {}, {}, {}) { _, _ -> },
+    MainScope(),
+  )
+
+  // Slice 3 spec §7.3: the intercom button belongs to SC-19's voice input only while SC-19 is shown.
+  @Test
+  fun sc19_takes_the_intercom_button_while_it_is_shown() {
+    keepRide()
+    var shown by mutableStateOf(true)
+    rule.setContent {
+      if (shown) NewNoteRoute(records, notes, draft, onClose = {}, voice = NoteVoice(input, MutableStateFlow(VOICE_IDLE), MutableStateFlow(true)))
+    }
+    waitFor("voice")
+    assertTrue(input.attached)
+    shown = false
+    rule.waitForIdle()
+    assertFalse(input.attached)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt b/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
index e92e329..d071f23 100644
--- a/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
@@ -9,7 +9,13 @@ import androidx.compose.ui.test.onNodeWithTag
 import androidx.compose.ui.test.onNodeWithText
 import androidx.compose.ui.test.performClick
 import androidx.compose.ui.test.performTextReplacement
+import androidx.compose.runtime.getValue
+import androidx.compose.runtime.mutableStateOf
+import androidx.compose.runtime.setValue
 import androidx.test.ext.junit.runners.AndroidJUnit4
+import com.touringproject.v2.voice.Heard
+import com.touringproject.v2.voice.VoiceFailure
+import com.touringproject.v2.voice.VoicePhase
 import org.junit.Assert.assertEquals
 import org.junit.Rule
 import org.junit.Test
@@ -114,4 +120,59 @@ class NoteScreenTest {
     assertEquals(0, closed)
     assertEquals("削除できませんでした", ShadowToast.getTextOfLatestToast())
   }
+
+  private fun showVoice(ui: NoteVoiceUi, initial: String? = null, presses: MutableList<Unit> = mutableListOf()) = rule.setContent {
+    NoteScreen(header, initial, { true }, {}, voice = ui, onVoice = { presses += Unit })
+  }
+
+  // Slice 3 spec §7.3: "🎤 声で入力" starts the recording; the note says the voice goes only to be turned into text.
+  @Test
+  fun the_voice_button_starts_the_recording_and_says_where_the_voice_goes() {
+    val presses = mutableListOf<Unit>()
+    showVoice(NoteVoiceUi(VoicePhase.IDLE, null, null, online = true), presses = presses)
+    rule.onNodeWithText("声は文字にするためだけにサーバーへ送ります。AI には聞きません。").assertExists()
+    rule.onNodeWithTag("voice").assertTextEquals("🎤 声で入力").performClick()
+    assertEquals(1, presses.size)
+  }
+
+  @Test
+  fun while_recording_the_button_stops_it_and_while_the_text_is_made_it_waits() {
+    var phase by mutableStateOf(VoicePhase.RECORDING)
+    rule.setContent { NoteScreen(header, null, { true }, {}, voice = NoteVoiceUi(phase, null, null, online = true)) }
+    rule.onNodeWithTag("voice").assertTextEquals("■ 止めて文字にする").assertIsEnabled()
+    phase = VoicePhase.TRANSCRIBING
+    rule.onNodeWithTag("voice").assertTextEquals("文字にしています…").assertIsNotEnabled()
+  }
+
+  // Slice 3 spec §7.3: without a network the voice button cannot be pressed, and the screen says what still works.
+  @Test
+  fun without_a_network_the_voice_button_cannot_be_pressed() {
+    showVoice(NoteVoiceUi(VoicePhase.IDLE, null, null, online = false))
+    rule.onNodeWithTag("voice").assertIsNotEnabled()
+    rule.onNodeWithText("通信できないため、声では入力できません。文字で書けば保存できます。").assertExists()
+  }
+
+  @Test
+  fun the_reason_of_a_failed_voice_is_told_under_the_field() {
+    showVoice(NoteVoiceUi(VoicePhase.IDLE, VoiceFailure.NO_SPEECH.message, null, online = true))
+    rule.onNodeWithTag("voiceFailure").assertTextEquals("声が聞き取れませんでした。もう一度話してください。")
+  }
+
+  // What was heard goes at the end of the text, once, and can be changed by hand afterwards.
+  @Test
+  fun what_was_heard_is_added_at_the_end_once() {
+    var heard by mutableStateOf<Heard?>(null)
+    val taken = mutableListOf<Int>()
+    rule.setContent {
+      NoteScreen(header, null, { saved += it; true }, {}, voice = NoteVoiceUi(VoicePhase.IDLE, null, heard, online = true), onHeard = { taken += it; heard = null })
+    }
+    rule.onNodeWithTag("memoInput").performTextReplacement("料金所の手前")
+    heard = Heard(1, "展望スペース")
+    rule.waitForIdle()
+    rule.onNodeWithText("料金所の手前\n展望スペース").assertExists()
+    assertEquals(listOf(1), taken)
+    rule.onNodeWithTag("memoSave").performClick()
+    rule.waitForIdle()
+    assertEquals(listOf("料金所の手前\n展望スペース"), saved)
+  }
 }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*NoteScreenTest' --tests '*NoteRoutesTest' > /tmp/trv2-t4.log 2>&1; grep -c '^e: ' /tmp/trv2-t4.log
```

Expected: `BUILD FAILED`。まだ無い `NoteVoiceUi`・`NoteVoice` を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index f967d46..b9be198 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -101,6 +101,7 @@ fun AppUi(graph: AppGraph) {
   val recordsStack = rememberNavBackStack(RecordsKey)
   val settingsStack = rememberNavBackStack(SettingsKey)
   var selectedTab by rememberSaveable { mutableStateOf(Tab.HOME) }
+  val noteVoice = remember(graph) { NoteVoice(graph.voice, graph.voiceState, graph.connectivity.online) }
   val tabs = remember(homeStack, recordsStack, settingsStack) {
     TabStacks(mapOf(Tab.HOME to homeStack, Tab.RECORDS to recordsStack, Tab.SETTINGS to settingsStack), { selectedTab }, { selectedTab = it })
   }
@@ -205,10 +206,10 @@ fun AppUi(graph: AppGraph) {
                 AskMemoRoute(graph.records, graph.askEdits, key.rideId, key.askId, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding())
               }
               entry<NewNoteKey> { key ->
-                NewNoteRoute(graph.records, graph.notes, key.draft, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding())
+                NewNoteRoute(graph.records, graph.notes, key.draft, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding(), voice = noteVoice)
               }
               entry<NoteKey> { key ->
-                NoteRoute(graph.records, graph.notes, key.rideId, key.noteId, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding())
+                NoteRoute(graph.records, graph.notes, key.rideId, key.noteId, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding(), voice = noteVoice)
               }
               entry<SettingsKey> {
                 SettingsScreen(
diff --git a/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt b/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
index 93e87a8..4576bfb 100644
--- a/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
@@ -37,8 +37,10 @@ import androidx.compose.ui.text.input.TextFieldValue
 import androidx.compose.ui.unit.dp
 import androidx.compose.ui.unit.sp
 import com.touringproject.v2.records.MEMO_MAX
+import com.touringproject.v2.records.appendHeard
 import com.touringproject.v2.records.cutMemo
 import com.touringproject.v2.records.memoText
+import com.touringproject.v2.voice.Heard
 import kotlinx.coroutines.launch
 
 /**
@@ -46,7 +48,8 @@ import kotlinx.coroutines.launch
  * below. initial is the text kept now; onSave gets the cleaned text (memoText: null when blank) and says whether it was
  * written: a text that was not is told and the screen stays, so nothing typed is lost (slice 3 spec §8). canSave says
  * whether a cleaned text may be saved. ✕ and Back ask before throwing a change away. While a save runs, 保存, ✕ and
- * Back take nothing, so the screen is closed once (Android #55). The field opens with the cursor at the end.
+ * Back take nothing, so the screen is closed once (Android #55). The field opens with the cursor at the end. heard is
+ * what SC-19's voice input heard: it is added at the end of the text once, and onHeard tells it was.
  */
 @Composable
 fun MemoEditor(
@@ -60,6 +63,8 @@ fun MemoEditor(
   saveColor: Color? = null,
   header: @Composable () -> Unit = {},
   footer: @Composable ColumnScope.() -> Unit = {},
+  heard: Heard? = null,
+  onHeard: (Int) -> Unit = {},
 ) {
   var field by rememberSaveable(stateSaver = TextFieldValue.Saver) {
     mutableStateOf((initial ?: "").let { TextFieldValue(it, TextRange(it.length)) })
@@ -72,6 +77,12 @@ fun MemoEditor(
   val context = LocalContext.current
   val focus = remember { FocusRequester() }
   LaunchedEffect(Unit) { focus.requestFocus() }
+  LaunchedEffect(heard?.seq) {
+    val next = heard ?: return@LaunchedEffect
+    val text = appendHeard(field.text, next.text)
+    field = TextFieldValue(text, TextRange(text.length))
+    onHeard(next.seq)
+  }
   val close = {
     if (!saving) {
       if (changed) discarding = true else onClose()
diff --git a/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt b/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt
index f7ee606..b884304 100644
--- a/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt
@@ -6,8 +6,11 @@ import androidx.compose.foundation.background
 import androidx.compose.foundation.layout.Arrangement
 import androidx.compose.foundation.layout.Column
 import androidx.compose.foundation.layout.fillMaxWidth
+import androidx.compose.foundation.layout.heightIn
 import androidx.compose.foundation.layout.padding
 import androidx.compose.foundation.shape.RoundedCornerShape
+import androidx.compose.material3.ButtonDefaults
+import androidx.compose.material3.FilledTonalButton
 import androidx.compose.material3.MaterialTheme
 import androidx.compose.material3.OutlinedButton
 import androidx.compose.material3.Text
@@ -24,17 +27,23 @@ import androidx.compose.ui.platform.testTag
 import androidx.compose.ui.text.font.FontWeight
 import androidx.compose.ui.unit.dp
 import androidx.compose.ui.unit.sp
+import com.touringproject.v2.voice.Heard
+import com.touringproject.v2.voice.VoicePhase
 import kotlinx.coroutines.launch
 
 // The mock's --memo and --danger.
 private val Memo = Color(0xFF13804A)
 private val Danger = Color(0xFFD42A2A)
 
+/** SC-19's voice input as drawn (slice 3 spec §7.3). failure is the reason of the last voice that gave no text. */
+data class NoteVoiceUi(val phase: VoicePhase, val failure: String?, val heard: Heard?, val online: Boolean)
+
 /**
- * SC-19 (slice 3 spec §7.3), with text only: voice input comes with plan 4. header says when, where and for which ride
- * the memo is; initial is its text kept now (null for one opened from Home). An empty memo cannot be saved. onDelete is
- * given for a kept memo: "この地点メモを削除" asks first (DL-01), and once the memo is deleted the screen closes, back to
- * where it was opened from.
+ * SC-19 (slice 3 spec §7.3). header says when, where and for which ride the memo is; initial is its text kept now (null
+ * for one opened from Home). An empty memo cannot be saved. voice draws the voice input ("🎤 声で入力"; none without
+ * it): onVoice starts and stops it, and what it heard is added to the text, then told with onHeard. onDelete is given
+ * for a kept memo: "この地点メモを削除" asks first (DL-01), and once the memo is deleted the screen closes, back to where
+ * it was opened from.
  */
 @Composable
 fun NoteScreen(
@@ -44,6 +53,9 @@ fun NoteScreen(
   onClose: () -> Unit,
   modifier: Modifier = Modifier,
   onDelete: (suspend () -> Boolean)? = null,
+  voice: NoteVoiceUi? = null,
+  onVoice: () -> Unit = {},
+  onHeard: (Int) -> Unit = {},
 ) {
   var deleting by rememberSaveable { mutableStateOf(false) }
   val scope = rememberCoroutineScope()
@@ -62,7 +74,10 @@ fun NoteScreen(
         Text(header.ride, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp, modifier = Modifier.testTag("noteRide"))
       }
     },
+    heard = voice?.heard,
+    onHeard = onHeard,
     footer = {
+      if (voice != null) VoiceInputArea(voice, onVoice)
       if (onDelete != null) {
         OutlinedButton(onClick = { deleting = true }, modifier = Modifier.fillMaxWidth().testTag("deleteNote"), border = BorderStroke(1.dp, Danger)) {
           Text("この地点メモを削除", color = Danger, fontWeight = FontWeight.Bold)
@@ -81,3 +96,29 @@ fun NoteScreen(
     )
   }
 }
+
+@Composable
+private fun VoiceInputArea(voice: NoteVoiceUi, onVoice: () -> Unit) {
+  val recording = voice.phase == VoicePhase.RECORDING
+  FilledTonalButton(
+    onClick = onVoice,
+    enabled = recording || (voice.phase == VoicePhase.IDLE && voice.online),
+    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).testTag("voice"),
+    colors = if (recording) ButtonDefaults.filledTonalButtonColors(containerColor = Danger, contentColor = Color.White) else ButtonDefaults.filledTonalButtonColors(),
+  ) {
+    Text(
+      when (voice.phase) {
+        VoicePhase.IDLE -> "🎤 声で入力"
+        VoicePhase.RECORDING -> "■ 止めて文字にする"
+        VoicePhase.TRANSCRIBING -> "文字にしています…"
+      },
+      fontSize = 17.sp,
+    )
+  }
+  voice.failure?.let { Text(it, color = Danger, fontSize = 14.sp, modifier = Modifier.testTag("voiceFailure")) }
+  if (voice.online) {
+    Text("声は文字にするためだけにサーバーへ送ります。AI には聞きません。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
+  } else {
+    Text("通信できないため、声では入力できません。文字で書けば保存できます。", color = Danger, fontSize = 13.sp)
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
index f383e79..0502a88 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
@@ -1,6 +1,7 @@
 package com.touringproject.v2.ui
 
 import androidx.compose.runtime.Composable
+import androidx.compose.runtime.DisposableEffect
 import androidx.compose.runtime.getValue
 import androidx.compose.runtime.mutableStateOf
 import androidx.compose.runtime.setValue
@@ -23,6 +24,10 @@ import com.touringproject.v2.ride.RideStatus
 import com.touringproject.v2.ride.RoutePoint
 import com.touringproject.v2.settings.Settings
 import com.touringproject.v2.store.RoomRecords
+import com.touringproject.v2.ask.Source
+import com.touringproject.v2.voice.VoiceInput
+import com.touringproject.v2.voice.VoiceState
+import kotlinx.coroutines.flow.StateFlow
 import kotlinx.coroutines.Dispatchers
 import kotlinx.coroutines.flow.map
 import kotlinx.coroutines.withContext
@@ -148,13 +153,35 @@ fun AskMemoRoute(records: RoomRecords, edits: AskEdits, rideId: String, askId: S
   MemoScreen(target, ask.memo, { edits.memo(askId, it) }, onClose, modifier)
 }
 
+/** SC-19's voice input as the routes take it from AppGraph. */
+class NoteVoice(val input: VoiceInput, val state: StateFlow<VoiceState>, val online: StateFlow<Boolean>)
+
+/**
+ * The voice input while SC-19 is shown: attached, the intercom button goes to it (slice 3 spec §7.3); leaving SC-19
+ * detaches it and drops whatever it was doing.
+ */
+@Composable
+private fun voiceUi(voice: NoteVoice?): NoteVoiceUi? {
+  voice ?: return null
+  DisposableEffect(voice) {
+    voice.input.attach()
+    onDispose { voice.input.detach() }
+  }
+  val state by voice.state.collectAsStateWithLifecycle()
+  val online by voice.online.collectAsStateWithLifecycle()
+  return NoteVoiceUi(state.phase, state.failure?.message, state.heard, online)
+}
+
 /** SC-19 opened from Home: the memo is kept for the ride it was opened in when it is first saved (slice 3 spec §7.3). */
 @Composable
-fun NewNoteRoute(records: RoomRecords, notes: NoteEdits, draft: NoteDraft, onClose: () -> Unit, modifier: Modifier = Modifier) {
+fun NewNoteRoute(records: RoomRecords, notes: NoteEdits, draft: NoteDraft, onClose: () -> Unit, modifier: Modifier = Modifier, voice: NoteVoice? = null) {
   val ride = readRide(records, draft.rideId) ?: return
   val kept = ride.value ?: return
   val header = remember(draft, kept.name) { newNoteHeader(draft, kept.name, ZoneId.systemDefault()) }
-  NoteScreen(header, null, { notes.create(draft, it) }, onClose, modifier)
+  NoteScreen(
+    header, null, { notes.create(draft, it) }, onClose, modifier,
+    voice = voiceUi(voice), onVoice = { voice?.input?.press(Source.SCREEN) }, onHeard = { voice?.input?.taken(it) },
+  )
 }
 
 /**
@@ -162,7 +189,15 @@ fun NewNoteRoute(records: RoomRecords, notes: NoteEdits, draft: NoteDraft, onClo
  * the deletion in progress is not cancelled with the screen and closes it once.
  */
 @Composable
-fun NoteRoute(records: RoomRecords, notes: NoteEdits, rideId: String, noteId: String, onClose: () -> Unit, modifier: Modifier = Modifier) {
+fun NoteRoute(
+  records: RoomRecords,
+  notes: NoteEdits,
+  rideId: String,
+  noteId: String,
+  onClose: () -> Unit,
+  modifier: Modifier = Modifier,
+  voice: NoteVoice? = null,
+) {
   val ride = readRide(records, rideId) ?: return
   val list = readNotes(records, rideId) ?: return
   var shown by remember(noteId) { mutableStateOf(list.firstOrNull { it.id == noteId }) }
@@ -170,5 +205,8 @@ fun NoteRoute(records: RoomRecords, notes: NoteEdits, rideId: String, noteId: St
   val note = shown ?: return
   val name = ride.value?.name ?: return
   val header = remember(note, name) { noteHeader(note, name, ZoneId.systemDefault()) }
-  NoteScreen(header, note.text, { notes.text(noteId, it) }, onClose, modifier, onDelete = { notes.delete(noteId) })
+  NoteScreen(
+    header, note.text, { notes.text(noteId, it) }, onClose, modifier, onDelete = { notes.delete(noteId) },
+    voice = voiceUi(voice), onVoice = { voice?.input?.press(Source.SCREEN) }, onHeard = { voice?.input?.taken(it) },
+  )
 }
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t4.log 2>&1; tail -1 /tmp/trv2-t4.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト517件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt \
  app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt \
  app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt \
  app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt \
  app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
git commit -m "feat: write a point memo by voice on SC-19, the intercom button included"
```

---

### Task 5: Android #57: 削除中・別のタブ・プロセスの終了後の保存・見つからないとき

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `store/RideDatabase.kt`・`ui/AppUi.kt`・`ui/MemoScreen.kt`・`ui/NoteScreen.kt`・`ui/RecordsRoutes.kt`・`ui/Tabs.kt`
- Test: `store/RoomNotesTest.kt`・`ui/NoteRoutesTest.kt`・`ui/NoteScreenTest.kt`・`ui/TabsTest.kt`

**Interfaces:**
- Consumes: Task 4 の `MemoEditor`・`NoteScreen`・plan 3 の `NoteDao.create`・`writeText`・`TabStacks`
- Produces:
  - `TabStacks.pushOn(tab, key, unlessTop: (K) -> Boolean)`
  - `MemoEditor(..., busy: Boolean = false)`。`NoteScreen` は削除のあいだ `busy`
  - `NoteDao.create` は同じ id・同じ走行の地点メモがあれば本文を変える
  - `NoteNotFound(text, onClose, modifier)`（タグ `notFound`・`notFoundClose`）

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
index 55688d3..eaeb177 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
@@ -144,4 +144,15 @@ class RoomNotesTest {
     assertEquals(NoteDraft("n1", "r1", 5_000, null, null, null, null, null), notes.draft("r1"))
     assertEquals(1, errors.size)
   }
+
+  // Android #57: a memo saved just before the process died is saved again from the restored SC-19; it is the same memo.
+  @Test
+  fun saving_a_drafted_memo_again_changes_the_one_kept() = runBlocking {
+    rides.save(ride)
+    assertTrue(notes.create(draft, "一つ目"))
+    now = 6_000
+    assertTrue(notes.create(draft, "二つ目"))
+    assertEquals("二つ目" to 6_000L, db.notes().note("n1")!!.let { it.text to it.updatedAt })
+    assertFalse(notes.create(draft.copy(rideId = "r9"), "別の走行"))
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt b/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
index e4f049a..880f357 100644
--- a/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
@@ -118,4 +118,15 @@ class NoteRoutesTest {
     rule.waitForIdle()
     assertFalse(input.attached)
   }
+
+  // Android #57: a memo or ride that is not found says so, and the screen can still be closed.
+  @Test
+  fun a_memo_not_found_says_so_and_can_be_closed() {
+    keepRide()
+    rule.setContent { NoteRoute(records, notes, "r1", "n9", onClose = { closed++ }) }
+    waitFor("notFound")
+    rule.onNodeWithTag("notFound").assertTextEquals("この地点メモは見つかりません。")
+    rule.onNodeWithTag("notFoundClose").performClick()
+    assertEquals(1, closed)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt b/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
index d071f23..b1f6dff 100644
--- a/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
@@ -175,4 +175,20 @@ class NoteScreenTest {
     rule.waitForIdle()
     assertEquals(listOf("料金所の手前\n展望スペース"), saved)
   }
+
+  // Android #57: while the memo is being deleted, ✕, Back and a second delete do nothing; the screen closes once.
+  @Test
+  fun while_the_memo_is_being_deleted_nothing_else_closes_it() {
+    val gate = kotlinx.coroutines.CompletableDeferred<Boolean>()
+    rule.setContent { NoteScreen(header, "消すメモ", { true }, { closed++ }, onDelete = { deletes++; gate.await() }) }
+    rule.onNodeWithTag("deleteNote").performClick()
+    rule.onNodeWithTag("deleteGo").performClick()
+    rule.onNodeWithTag("memoClose").performClick()
+    rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
+    rule.onNodeWithTag("deleteNote").assertIsNotEnabled()
+    gate.complete(true)
+    rule.waitForIdle()
+    assertEquals(1, deletes)
+    assertEquals(1, closed)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt b/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
index 606de64..529a33e 100644
--- a/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
@@ -76,4 +76,17 @@ class TabsTest {
     assertTrue(tabsShown(Phase.IDLE))
     for (phase in Phase.entries - Phase.IDLE) assertFalse(phase.name, tabsShown(phase))
   }
+
+  // Android #57: SC-19 opened from Home lands on Home, not on a tab the rider moved to while its place was read; and a
+  // second press while the first one's memo is on top adds nothing.
+  @Test
+  fun a_screen_is_pushed_only_on_its_tab_and_not_over_one_like_it() {
+    tabs.pushOn(Tab.HOME, "note-1") { it.startsWith("note") }
+    tabs.pushOn(Tab.HOME, "note-2") { it.startsWith("note") }
+    assertEquals(listOf("home", "note-1"), home)
+    tabs.press(Tab.RECORDS)
+    tabs.pushOn(Tab.HOME, "note-3") { false }
+    assertEquals(listOf("records"), records)
+    assertEquals(listOf("home", "note-1"), home)
+  }
 }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TabsTest' --tests '*RoomNotesTest' --tests '*NoteScreenTest' --tests '*NoteRoutesTest' > /tmp/trv2-t5.log 2>&1; grep -c '^e: ' /tmp/trv2-t5.log
```

Expected: `BUILD FAILED`。まだ無い `pushOn`・`notFound` の画面を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 04bca6e..516f018 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -238,12 +238,20 @@ interface NoteDao {
   @Query("SELECT EXISTS (SELECT 1 FROM rides WHERE id = :rideId)")
   suspend fun rideKept(rideId: String): Boolean
 
-  /** SC-19 from Home. False when the memo's ride is no longer kept. */
+  /**
+   * SC-19 from Home. False when the memo's ride is no longer kept. A memo already kept under the draft's id (saved just
+   * before the process died, then saved again from the restored SC-19) takes the new text (Android #57).
+   */
   @Transaction
   suspend fun create(note: NoteEntity): Boolean {
     if (!rideKept(note.rideId)) return false
-    insert(note)
-    return true
+    val kept = note(note.id)
+    if (kept == null) {
+      insert(note)
+      return true
+    }
+    if (kept.rideId != note.rideId) return false
+    return writeText(note.id, note.text, note.updatedAt)
   }
 
   @Query("UPDATE notes SET text = :text, updatedAt = :at WHERE id = :id")
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index b9be198..1f14c18 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -157,12 +157,13 @@ fun AppUi(graph: AppGraph) {
                       onMemo = { ride?.let { tabs.push(RideMemoKey(it.id)) } },
                     )
                   },
-                  // The place is read when the button is pressed (slice 3 spec §4.3); a second press while it is read adds nothing.
+                  // The place is read when the button is pressed (slice 3 spec §4.3); a second press while it is read adds
+                  // nothing, and a tab moved to meanwhile is left as it is (Android #57).
                   onNote = ride?.let { active ->
                     {
                       scope.launch {
                         val draft = graph.notes.draft(active.id)
-                        if (tabs.current.lastOrNull() !is NewNoteKey) tabs.push(NewNoteKey(draft))
+                        tabs.pushOn(Tab.HOME, NewNoteKey(draft)) { it is NewNoteKey }
                       }
                     }
                   },
diff --git a/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt b/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
index 4576bfb..f501cbf 100644
--- a/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
@@ -49,7 +49,8 @@ import kotlinx.coroutines.launch
  * written: a text that was not is told and the screen stays, so nothing typed is lost (slice 3 spec §8). canSave says
  * whether a cleaned text may be saved. ✕ and Back ask before throwing a change away. While a save runs, 保存, ✕ and
  * Back take nothing, so the screen is closed once (Android #55). The field opens with the cursor at the end. heard is
- * what SC-19's voice input heard: it is added at the end of the text once, and onHeard tells it was.
+ * what SC-19's voice input heard: it is added at the end of the text once, and onHeard tells it was. busy is set by
+ * the screen while it does something of its own (SC-19 deleting the memo): 保存, ✕ and Back then take nothing either.
  */
 @Composable
 fun MemoEditor(
@@ -65,6 +66,7 @@ fun MemoEditor(
   footer: @Composable ColumnScope.() -> Unit = {},
   heard: Heard? = null,
   onHeard: (Int) -> Unit = {},
+  busy: Boolean = false,
 ) {
   var field by rememberSaveable(stateSaver = TextFieldValue.Saver) {
     mutableStateOf((initial ?: "").let { TextFieldValue(it, TextRange(it.length)) })
@@ -84,7 +86,7 @@ fun MemoEditor(
     onHeard(next.seq)
   }
   val close = {
-    if (!saving) {
+    if (!saving && !busy) {
       if (changed) discarding = true else onClose()
     }
   }
@@ -103,7 +105,7 @@ fun MemoEditor(
             saving = false
           }
         },
-        enabled = !saving && canSave(clean),
+        enabled = !saving && !busy && canSave(clean),
         colors = saveColor?.let { ButtonDefaults.buttonColors(containerColor = it, contentColor = Color.White) } ?: ButtonDefaults.buttonColors(),
         modifier = Modifier.testTag("memoSave"),
       ) { Text("保存") }
diff --git a/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt b/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt
index b884304..88a22de 100644
--- a/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt
@@ -1,6 +1,7 @@
 package com.touringproject.v2.ui
 
 import android.widget.Toast
+import androidx.activity.compose.BackHandler
 import androidx.compose.foundation.BorderStroke
 import androidx.compose.foundation.background
 import androidx.compose.foundation.layout.Arrangement
@@ -14,9 +15,11 @@ import androidx.compose.material3.FilledTonalButton
 import androidx.compose.material3.MaterialTheme
 import androidx.compose.material3.OutlinedButton
 import androidx.compose.material3.Text
+import androidx.compose.material3.TextButton
 import androidx.compose.runtime.Composable
 import androidx.compose.runtime.getValue
 import androidx.compose.runtime.mutableStateOf
+import androidx.compose.runtime.remember
 import androidx.compose.runtime.rememberCoroutineScope
 import androidx.compose.runtime.saveable.rememberSaveable
 import androidx.compose.runtime.setValue
@@ -58,6 +61,8 @@ fun NoteScreen(
   onHeard: (Int) -> Unit = {},
 ) {
   var deleting by rememberSaveable { mutableStateOf(false) }
+  // From "削除する" until the deletion has returned: nothing else may close the screen meanwhile (Android #57).
+  var removing by remember { mutableStateOf(false) }
   val scope = rememberCoroutineScope()
   val context = LocalContext.current
   MemoEditor(
@@ -76,10 +81,16 @@ fun NoteScreen(
     },
     heard = voice?.heard,
     onHeard = onHeard,
+    busy = removing,
     footer = {
       if (voice != null) VoiceInputArea(voice, onVoice)
       if (onDelete != null) {
-        OutlinedButton(onClick = { deleting = true }, modifier = Modifier.fillMaxWidth().testTag("deleteNote"), border = BorderStroke(1.dp, Danger)) {
+        OutlinedButton(
+          onClick = { deleting = true },
+          enabled = !removing,
+          modifier = Modifier.fillMaxWidth().testTag("deleteNote"),
+          border = BorderStroke(1.dp, Danger),
+        ) {
           Text("この地点メモを削除", color = Danger, fontWeight = FontWeight.Bold)
         }
       }
@@ -90,7 +101,15 @@ fun NoteScreen(
       DeleteKind.NOTE,
       onConfirm = {
         deleting = false
-        scope.launch { if (onDelete()) onClose() else Toast.makeText(context, "削除できませんでした", Toast.LENGTH_SHORT).show() }
+        removing = true
+        scope.launch {
+          if (onDelete()) {
+            onClose()
+          } else {
+            removing = false
+            Toast.makeText(context, "削除できませんでした", Toast.LENGTH_SHORT).show()
+          }
+        }
       },
       onDismiss = { deleting = false },
     )
@@ -122,3 +141,13 @@ private fun VoiceInputArea(voice: NoteVoiceUi, onVoice: () -> Unit) {
     Text("通信できないため、声では入力できません。文字で書けば保存できます。", color = Danger, fontSize = 13.sp)
   }
 }
+
+/** SC-19 for a ride or memo that is not kept: it says so, and ✕ and Back still close it (Android #57). */
+@Composable
+fun NoteNotFound(text: String, onClose: () -> Unit, modifier: Modifier = Modifier) {
+  BackHandler(onBack = onClose)
+  Column(modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
+    TextButton(onClick = onClose, modifier = Modifier.testTag("notFoundClose")) { Text("✕", fontSize = 22.sp) }
+    Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 16.sp, modifier = Modifier.testTag("notFound"))
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
index 0502a88..d888194 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
@@ -176,7 +176,7 @@ private fun voiceUi(voice: NoteVoice?): NoteVoiceUi? {
 @Composable
 fun NewNoteRoute(records: RoomRecords, notes: NoteEdits, draft: NoteDraft, onClose: () -> Unit, modifier: Modifier = Modifier, voice: NoteVoice? = null) {
   val ride = readRide(records, draft.rideId) ?: return
-  val kept = ride.value ?: return
+  val kept = ride.value ?: return NoteNotFound("この走行は見つかりません。", onClose, modifier)
   val header = remember(draft, kept.name) { newNoteHeader(draft, kept.name, ZoneId.systemDefault()) }
   NoteScreen(
     header, null, { notes.create(draft, it) }, onClose, modifier,
@@ -202,8 +202,8 @@ fun NoteRoute(
   val list = readNotes(records, rideId) ?: return
   var shown by remember(noteId) { mutableStateOf(list.firstOrNull { it.id == noteId }) }
   list.firstOrNull { it.id == noteId }?.let { shown = it }
-  val note = shown ?: return
-  val name = ride.value?.name ?: return
+  val note = shown ?: return NoteNotFound("この地点メモは見つかりません。", onClose, modifier)
+  val name = ride.value?.name ?: return NoteNotFound("この走行は見つかりません。", onClose, modifier)
   val header = remember(note, name) { noteHeader(note, name, ZoneId.systemDefault()) }
   NoteScreen(
     header, note.text, { notes.text(noteId, it) }, onClose, modifier, onDelete = { notes.delete(noteId) },
diff --git a/app/src/main/java/com/touringproject/v2/ui/Tabs.kt b/app/src/main/java/com/touringproject/v2/ui/Tabs.kt
index 59142c7..af1132a 100644
--- a/app/src/main/java/com/touringproject/v2/ui/Tabs.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/Tabs.kt
@@ -48,6 +48,18 @@ class TabStacks<K>(
     if (stack.lastOrNull() != key) stack += key
   }
 
+  /**
+   * Opens key in tab only while tab is the one shown and its top screen is not like it (unlessTop): a screen asked for
+   * from one tab never lands on another the rider has moved to meanwhile, and a quick second press adds nothing
+   * (Android #57).
+   */
+  fun pushOn(tab: Tab, key: K, unlessTop: (K) -> Boolean) {
+    if (tab != this.tab) return
+    val top = current.lastOrNull()
+    if (top != null && unlessTop(top)) return
+    current += key
+  }
+
   /** Shows key above the first screen of tab, e.g. the user name from Home's user chip. */
   fun open(tab: Tab, key: K) {
     val stack = stacks.getValue(tab)
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t5.log 2>&1; tail -1 /tmp/trv2-t5.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト521件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/store/RideDatabase.kt \
  app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt \
  app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt \
  app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt \
  app/src/main/java/com/touringproject/v2/ui/Tabs.kt \
  app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt \
  app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt \
  app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt \
  app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
git commit -m "fix: keep SC-19 from closing twice while deleting, open it only on Home, save a restored draft again, and say when nothing is found (Android #57)"
```

---

### Task 6: 版と文書

**Files:**
- Modify: `app/build.gradle.kts`（版 0.8.0）・`README.md`（Android）・`docs-parent/mock/index.html`

- [ ] **Step 1: 版を上げ、README を直す**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/README.md b/README.md
index 1d75b10..815ebb3 100644
--- a/README.md
+++ b/README.md
@@ -17,7 +17,9 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 | `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋）・メモの決まり（`Memos.kt`、純粋）・地点メモの型と位置の選び方（`Notes.kt`、純粋）・質問と地点メモを変える窓口（`AskEdits.kt`・`NoteEdits.kt`） |
 | `.../map/` | 地図（MapLibre と国土地理院の淡色地図）。描くデータの組み立ては `MapData.kt`（純粋）、地図の部品は `RouteMap.kt`、スタイルは `app/src/main/assets/map/gsi-pale.json` |
 | `.../sync/` | 走行・ルート・地点メモ・メモ・削除の送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`） |
-| `.../handsfree/` | 押下の重複・古い合図の除外・押下の行き先（試し録り中は試し録りへ） |
+| `.../handsfree/` | 押下の重複・古い合図の除外・押下の行き先（試し録り中は試し録りへ、SC-19 を開いているあいだは声の入力へ） |
+| `.../voice/` | SC-19 の声の入力（`VoiceInput.kt`）。録音・文字起こしの依頼・取りに行く処理・失敗の理由 |
+| `.../net/` | 端末が通信できるか（`Connectivity.kt`。SC-19 の声の入力が使う） |
 | `.../recordings/` | 録音の置き場（直近10件と付随情報）・試し録りの司令塔・録音の確認（SC-12）の状態 |
 | `.../service/`・`.../nav/` | 前面サービス（走行の記録と一巡で1つ。種類の取りまとめは `ServiceCoordinator.kt`）・締め切りのアラームと自動終了の通知（`RideAlarms.kt`）・ナビを開く |
 | `.../settings/` | 設定（DataStore）と接続キー（Keystore で暗号化） |
@@ -32,6 +34,7 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 - 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと。契機では未送信を調べるだけで、送るものが無ければ通信しない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。
 - 1回の送信は、削除の印（`deletions`）→ 走行とルート → 地点メモ → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため）。記録を消すときは、同じトランザクションで削除の印を書く。送れない削除の印（知らない種類）は、ログ `sync_unsendable` に出して消す（残すと、毎回の送信がそこで止まる）。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
 - 地点メモ（SC-19）は、走行の記録中と一時停止中にホームの「📝 地点メモ」から開く。開いたときに、その走行の最後の点を位置に、質問と同じ選び方で方位の材料を決め（`noteDraft`）、保存するまで書かない。住所と方位は、最初に送ったときに Backend が決めて返し、端末はそれを行に書く（`notes.address`・`headingDegrees`）。地図のピンは緑で、質問とは別の通し番号。質問の一巡が終わったときに、その走行が消えていれば質問は書かない（`AskDao.keep`）。
+- SC-19 の声の入力（`VoiceInput`）は、質問とは別の経路の切り替えと録音の部品を持つ（試し録りと同じ）。SC-19 を開いているあいだ（`attach`）は、インカムのボタンが質問を始めず、声の入力を始める・止める（質問が進んでいるときは質問のまま）。録音は60秒まで。`POST /transcriptions` に送り、質問と同じ間隔で `GET` し、120秒で打ち切る。聞き取れた文は入力欄の終わりに足す。通信できないときは画面のボタンを押せず、インカムのボタンは失敗の合図だけを鳴らす。SC-19 を離れると、録音も文字起こしの待ちも捨てる。前面サービスは使わない（SC-19 を見ながら使う前提）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
 - インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
 - 回答は音声の焦点（audio focus）を取らずに鳴らす（ナビの案内と重ねる）。
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index 24c1105..2d15875 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 8
-    versionName = "0.7.0"
+    versionCode = 9
+    versionName = "0.8.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
PATCH
````

- [ ] **Step 2: 親の文書を写す**

親のモックの SC-19（声の入力の文言）を、この plan のコミットで直してあるので、Android の `docs-parent/` に写す。

```bash
cd $ROOT && scripts/sync-docs.sh Android
cd $AND && git status --short docs-parent
```

Expected: `docs-parent/mock/index.html` だけが変わっている。

- [ ] **Step 3: コミット**

```bash
cd $AND && git add app/build.gradle.kts README.md docs-parent/mock/index.html
git commit -m "chore: raise the version to 0.8.0 and describe the voice input of point memos"
```

---
### Task 7: 全体の確かめ

- [ ] **Step 1: `clean` から JVM のテスト・ビルド・権限の検査**

```bash
cd $AND && ./gradlew clean && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-all.log 2>&1; tail -3 /tmp/trv2-all.log
python3 - <<'EOF'
import glob, re
t = f = 0
for x in glob.glob('app/build/test-results/testDebugUnitTest/*.xml'):
    m = re.search(r'tests="(\d+)" skipped="\d+" failures="(\d+)" errors="(\d+)"', open(x).read())
    t += int(m[1]); f += int(m[2]) + int(m[3])
print(t, f)
EOF
cd $AND && ./gradlew assembleDebug assembleRelease --rerun-tasks && scripts/check-release-permissions.sh
```

Expected: `521 0`。`BUILD SUCCESSFUL`。`release permissions OK (15)`。

- [ ] **Step 2: エミュレーターのテスト**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: 6件が通る。

---

### Task 8: 利用者の実機の確認と、spec §1 の判定

走行用のビルド（版 0.8.0）を実機に入れる。Room の版は変わらないので、Migration は走らない。

```bash
cd $AND && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

声の入力:

1. 設定 → バージョンが 0.8.0。
2. 走行を始めて停車し、「📝 地点メモ」で SC-19 を開く。入力欄の下に「🎤 声で入力」と「声は文字にするためだけにサーバーへ送ります。AI には聞きません。」が出る。
3. 「🎤 声で入力」→ 開始の合図のあとに話す → ボタンが赤の「■ 止めて文字にする」になる。押すと「文字にしています…」になり、聞き取れた文が入力欄の終わりに足される。手で直して保存できる。
4. もう一度 SC-19 を開き、インカムのボタンを押す → 質問は始まらず、声の入力の録音が始まる。もう一度インカムのボタンを押すと止まり、文が足される。
5. 何も話さずに止める → 入力欄の下に「声が聞き取れませんでした。もう一度話してください。」が出て、失敗の合図が鳴る。
6. 機内モードにする → 「🎤 声で入力」が押せなくなり、「通信できないため、声では入力できません。文字で書けば保存できます。」が出る。インカムのボタンを押すと、録音は始まらず、失敗の合図だけが鳴る。
7. 録音中に ✕ で閉じる（変更があれば「破棄する」）→ 録音が止まり、あとで文が足されることはない。SC-19 を閉じたあとのインカムのボタンは、今までどおり質問を始める。

spec §1 の判定（plan 3 で省いた通信できないときの手順を含む）:

8. 走行の記録中に停車し、ホームから地点メモを文字でも声でも書ける。走行の詳細に緑のピン（質問とは別の通し番号）で出て、時系列には質問と時刻順に混ざって出る。
9. 機内モードのまま、文字の地点メモを書いて保存する → 端末に残る（走行を終えると一覧で「未送信あり」、SC-19 で「📍 住所は送ったあとに付きます」）。機内モードを外してアプリを前面に出し直すと送られ、住所が付く（一覧は「保存済み」）。
10. 会話と走行にメモを書け、直せ、空にして保存すると消える。メモのある会話・走行が、一覧と地図で分かる（plan 2 で確かめたもの。0.8.0 でも変わらないことを見る）。
11. 会話・地点メモ・終えた走行を削除すると、端末から消える。
12. AI が DynamoDB を読んで確かめる（読むだけ）: 手順 3・4・9 の地点メモの `RIDE#<rideId>#NOTE#<noteId>` に `text`・`address` があり、手順 9 の地点メモは住所付き。手順 11 で消したものは記録が無く、`DELETED#…` の跡がある。ユーザー名と識別子はチャットにだけ出す。
13. AI が Backend の smoke を回す: `cd $ROOT/Backend && AWS_PROFILE=touring env/bin/python scripts/smoke.py`。消した記録への古い `PUT` が 410 になることを含めて、全部が通る（新しい経路だけが 403 なら、1分ほど待って回し直す）。

✓ なら、spec §1 の判定の5項目すべてに印を付けられる。✗ が出たら `superpowers:systematic-debugging`。
