# ネイティブ移行 計画2: 残りの画面と仕上げ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ネイティブ版を、スライス1の App と同じ振る舞いまで仕上げる。録音を直近10件残して SC-12（試し録り・送った録音）で確かめられ、SC-21 で回答の音量を選べ、メディアの音量が低いと帯で知らせ、走行用のビルド（release）を USB なしで使える。あわせて、移行 plan 1 の後回しの指摘（Android の issue #1〜#5）を直し、親の文書を新しい構成（ユニット Android・submodule `App/` なし）に合わせる。

**Architecture:** plan 1 の作り（Android に依存しない司令塔と、`AskPorts.kt` の interface を通した部品）をそのまま伸ばす。新しいパッケージ `recordings` に、録音の置き場（`RecordingStore`）・試し録りの司令塔（`TrialController`、純粋な Kotlin）・SC-12 の状態と操作（`RecordingCheck`）を置く。インカムの押下の行き先は `handsfree/PressRouter` で決める（試し録り中は試し録りへ、それ以外は SC-12 の再生を止めてから質問へ）。SC-12 は、質問とは別の経路の切り替え・録音・再生（`AudioTrack` で PCM を直接鳴らす `PcmPlayer`）を持ち、質問の部品と何も共有しない（React Native 版の issue #10・#13 の原因を作らない）。

**Tech Stack:** plan 1 と同じ（Kotlin 2.3.20・AGP 9.0.1・Gradle 9.4.1・Compose BOM 2026.03.01・Navigation 3・DataStore・Media3・OkHttp 4.12・kotlinx.serialization・Robolectric 4.16（SDK 35））。足すのは `androidx.fragment:fragment:1.8.9`（release の lint のため。Task 10）だけ。

**Spec:** [docs/specs/2026-10-17-native-migration-design.md](../specs/2026-10-17-native-migration-design.md)（§2・§7・§8・§9・§11）。振る舞いの正は [スライス1の設計](../specs/2026-10-16-slice1-design.md) §5.4〜§5.7 と、React Native 版の `App/src/ask/recordings.ts`・`trial.ts`・`App/src/ui/homeBanner.ts`・`App/app/settings/recordings.tsx`・`volume.tsx`（移植の元）。

**範囲に入れた issue:** Android の #1・#2・#3・#4・#5（plan 1 の最終レビューの後回し）。React Native 版の App の #10〜#13 は、同じことがネイティブ版で起きない作りにし（Task 5・6・7 のテスト）、移行の締めで「移行で解消」として閉じる（Task 13）。

**計画を書くときに利用者と決めたこと:**
- Android の issue #1〜#5 をすべて範囲に入れる。
- 走行用のビルドの署名は、開発用の鍵（debug）のまま（spec §11）。配布しないので、release の鍵は作らない。debug と release を上書きで入れ替えても、設定・接続キー・録音が残る。
- スライス1の実際の走行での完了の判定は、この計画には入れない。計画の後に、利用者が走行用のビルドで行う（PROJECT.md の「次にやること」に残す）。

spec §8.1 からの変え方: 4b #6（SC-12 を離れても読み上げが続く）は、Robolectric ではなく JUnit で確かめる。SC-12 が回答とは別の再生器を持つ作りにしたので、「離れたときに SC-12 自身の再生器しか止めない」ことを `RecordingCheckTest` で見れば足りる。

この計画のコードは、使い捨てのフォルダで JVM のテスト179件・エミュレーターのテスト2件・`assembleDebug`・`assembleRelease`（lint を含む）・`scripts/check-release-permissions.sh` が通ることを確かめてから書いた。

## Global Constraints

- 作業するリポジトリは `Android/`（`TouringProjectV2_Android`）と親。どちらも `main` から作業ブランチ `migration-plan2` を切る。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- パッケージ名 `com.touringproject.v2`。minSdk 29・targetSdk 36・compileSdk 36。JDK 17。
- 録音は PCM（16kHz・モノラル・16bit）。上限は20秒。直近10件を `filesDir/recordings/` に `rec-<時刻>.pcm` と `rec-<時刻>.json`（付随情報）の組で残す。試し録りは残さない（スライス1 spec §5.4・§5.5）。
- 回答の音量は `+0 / +3 / +6（既定・最大）dB`。+6dB が上限（PROJECT.md の持ち越し）。
- メディアの音量の警告は、最大の1/3未満で出す。ホームが前面にあるあいだ2秒ごとに読み、質問が経路を持つあいだ（`IDLE`・`FAILED` 以外）は読まない。`AudioRoute.mediaVolume()` が `null`（メディアがインカムの通話の経路に流れている）なら直前の値を使う。✕ で閉じた音量の値を、プロセスが終わるまで覚える（スライス1 spec §5.6）。
- 失敗の読み上げ文はスライス1 spec §8.1 のとおり（plan 1 の `Failures.kt`）。
- 接続キー・API の URL・アカウント ID を、コードや文書に書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`（`rm` は置き換えられている）。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest`（絞るときは `--tests '*クラス名'` を引用符で囲む）。`-q` は付けない（ledger の記録が出力の最後の行を読む）。重い実行はログをファイルに出す。
- 実機が USB で繋がったままエミュレーターのテストを回すときは、`export ANDROID_SERIAL=emulator-5554` でエミュレーターだけを指す（実機にテスト用のビルドを入れない）。
- Robolectric の決まり（plan 1 の持ち越し）: SDK 35 で動かす。`withContext(Dispatchers.Main)` を使うコードはテストのスレッドから直に呼ばない。加えて、`runTest` の `backgroundScope` で動かした処理は `advanceUntilIdle` で進まない（背景の処理だけが残ると止まる）。アプリの scope の代わりには `CoroutineScope(SupervisorJob() + StandardTestDispatcher(testScheduler))` を使う（Task 7）。

## Review Focus

- SC-12 で試し録りを押してすぐ画面を離れる（経路の準備に最大3秒かかる）→ 後から録音が始まったり合図が鳴ったりしない。前の試し録りが片付くまで次は始まらない。Task 6 の `leaving_while_the_route_is_set_up_never_opens_the_microphone`。
- 質問の録音中に「録音をすべて消す」が走る → 質問は失敗せず、その録音は後から残る。Task 5 の `delete_all_then_a_new_recording_is_still_kept`。
- 付随情報の JSON が壊れている・PCM だけ残っている → 一覧に出ないものが10件の枠を使わない。Task 5 の `a_recording_missing_half_of_its_files_does_not_take_a_slot`。
- インカムの通話の経路が残っているあいだにホームへ戻る（音量の読み取りが `null`）→ 帯は直前の値のまま（誤って消えも出もしない）。Task 9 の `the_media_volume_is_read_while_home_is_shown_and_a_withheld_reading_keeps_the_last`。
- サーバーの応答が遅い（1回の取得が15秒×3回かかる）→ 回答の待ちは120秒で打ち切る。Task 1 の `a_slow_request_does_not_push_the_give_up_past_two_minutes` と、取り消しが通信まで届く `cancelling_a_waiting_request_cancels_the_call`。

---

## ファイル構成（`Android/app/src/` から。`...` は `com/touringproject/v2`）

| パス | 役割 | Task |
|---|---|---|
| `main/java/.../ask/Polling.kt` | 1回の取得を残り時間で打ち切る・読めない本文を読み飛ばす | 1 |
| `main/java/.../api/ApiClient.kt` | 1回の要求を取り消せる形（`enqueue`）にする | 1 |
| `main/java/.../ask/AskPorts.kt`・`AskController.kt` | 録音の受け口に PCM を渡す・空の録音を「録音できませんでした」にする | 2 |
| `main/java/.../audio/PcmRecorder.kt`・`AudioTypes.kt` | 録音が始まらない・黙らされたときに失敗にする。`InputDevice` を JSON にできる | 2 |
| `main/java/.../audio/ExoAnswerPlayer.kt` | 音声の合間の「やめる」を効かせる（`ClipSequence`） | 3 |
| `main/java/.../settings/ApiKeyStore.kt`・`ui/SettingsScreens.kt` | 接続キーの保存の失敗を分けて知らせる | 4 |
| `main/java/.../recordings/RecordingStore.kt`（新規） | 録音の置き場と、司令塔からの受け口（`RecordingKeeper`） | 5 |
| `main/java/.../recordings/Trial.kt`（新規）・`audio/PcmPlayer.kt`（新規） | 試し録りの司令塔・PCM の再生 | 6 |
| `main/java/.../recordings/RecordingCheck.kt`（新規）・`handsfree/PressRouter.kt`（新規）・`AppGraph.kt` | SC-12 の状態と操作・押下の行き先・組み立て | 7 |
| `main/java/.../ui/Labels.kt` | 音量の警告の判定・SC-12 の文言 | 8 |
| `main/java/.../ui/RecordingsScreen.kt`（新規）・`SettingsScreens.kt`・`HomeScreen.kt`・`AskOverlay.kt`・`AppUi.kt` | SC-12・SC-21・設定の行・警告の帯・画面のつながり | 9 |
| `app/build.gradle.kts`・`gradle/libs.versions.toml`・`scripts/check-release-permissions.sh`（新規）・`README.md` | 走行用のビルド | 10 |

---

### Task 1: ポーリングの打ち切りと読めない本文（Android issue #3・#4）

**Files:**
- Modify: `Android/app/src/main/java/com/touringproject/v2/ask/Polling.kt`（全体を置き換え）
- Modify: `Android/app/src/main/java/com/touringproject/v2/api/ApiClient.kt`（import と `once`）
- Test: `Android/app/src/test/java/com/touringproject/v2/ask/PollingAndConversationTest.kt`・`.../api/ApiClientTest.kt`

**Interfaces:**
- Consumes: なし
- Produces: `pollUntilDone(get, sleep, now, isCancelled): PollOutcome` の形は変えない。`ApiClient` の公開面も変えない（取り消しが HTTP の呼び出しまで届くようになる）

- [ ] **Step 0: ブランチを切る**

```bash
cd $AND && git switch main && git switch -c migration-plan2
cd $ROOT && git switch main && git switch -c migration-plan2
```

（親のブランチは、この計画をコミットしたときに切ってある場合はそれを使う。）

- [ ] **Step 1: 失敗するテストを書く**

`PollingAndConversationTest.kt` の `class PollingTest` の最後（`cancellation_stops_polling` の後）に足す:

```kotlin
  @Test
  fun a_body_that_cannot_be_read_is_skipped() = runTest {
    var calls = 0
    val outcome = poll(Clock()) { if (++calls == 1) throw kotlinx.serialization.SerializationException("cut short") else completed }
    assertEquals(PollOutcome.Done(completed), outcome)
  }

  @Test
  fun a_slow_request_does_not_push_the_give_up_past_two_minutes() = runTest {
    // One request can take three tries of 15 s; the limit still holds.
    val outcome = pollUntilDone({ kotlinx.coroutines.delay(45_000); processing }, { kotlinx.coroutines.delay(it) }, { testScheduler.currentTime }, { false })
    assertEquals(PollOutcome.Timeout, outcome)
    assertEquals(POLL_TIMEOUT_MS, testScheduler.currentTime)
  }
```

`ApiClientTest.kt` の import に足す:

```kotlin
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
```

`ApiClientTest` の最後（`a_stalled_request_times_out_as_a_network_error` の後）に足す:

```kotlin
  @Test
  fun cancelling_a_waiting_request_cancels_the_call(): Unit = runBlocking {
    server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
    val startedAt = System.nanoTime()
    // The client would wait 15 s for this response; the poll limit cancels it much sooner.
    assertNull(withTimeoutOrNull(300) { client().getAsk("a1") })
    assertTrue((System.nanoTime() - startedAt) / 1_000_000 < 5_000)
  }
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*PollingTest' --tests '*ApiClientTest' > /tmp/trv2-t1.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t1.log`
Expected: 3件が FAIL（読めない本文で例外が抜ける・打ち切りが120秒を超える・取り消しが15秒待つ）。

- [ ] **Step 3: 実装する**

`Polling.kt` を置き換える:

```kotlin
package com.touringproject.v2.ask

import com.touringproject.v2.api.ApiError
import com.touringproject.v2.api.ApiErrorKind
import com.touringproject.v2.api.AskResult
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withTimeoutOrNull

// Poll schedule from 07 UC-5: every 1 s for 10 s, then every 2 s, give up at 120 s.
const val POLL_FAST_MS = 1_000L
const val POLL_SLOW_MS = 2_000L
const val FAST_WINDOW_MS = 10_000L
const val POLL_TIMEOUT_MS = 120_000L
private val FATAL = setOf(ApiErrorKind.INVALID_KEY, ApiErrorKind.BAD_REQUEST, ApiErrorKind.NOT_FOUND)

fun nextDelay(elapsedMs: Long): Long = if (elapsedMs < FAST_WINDOW_MS) POLL_FAST_MS else POLL_SLOW_MS

sealed interface PollOutcome {
  data class Done(val result: AskResult) : PollOutcome
  data object Timeout : PollOutcome
  data object Cancelled : PollOutcome
}

/** Polls until the ask is done. One slow request (up to three tries of 15 s) is cut off at the 120 s limit. */
suspend fun pollUntilDone(
  get: suspend () -> AskResult,
  sleep: suspend (Long) -> Unit,
  now: () -> Long,
  isCancelled: () -> Boolean,
): PollOutcome {
  val startedAt = now()
  while (true) {
    val elapsed = now() - startedAt
    if (elapsed >= POLL_TIMEOUT_MS) return PollOutcome.Timeout
    sleep(nextDelay(elapsed))
    if (isCancelled()) return PollOutcome.Cancelled
    val remaining = POLL_TIMEOUT_MS - (now() - startedAt)
    if (remaining <= 0) return PollOutcome.Timeout
    try {
      val result = withTimeoutOrNull(remaining) { get() } ?: return PollOutcome.Timeout
      if (result.status != "processing") return PollOutcome.Done(result)
    } catch (e: CancellationException) {
      throw e
    } catch (e: ApiError) {
      if (e.kind in FATAL) throw e
    } catch (e: Exception) {
      // A body that cannot be read (e.g. cut short) is skipped like a transient error; the next poll may succeed.
    }
  }
}
```

`ApiClient.kt` の import を直す。消す:

```kotlin
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
```

足す（それぞれ並びの位置に）:

```kotlin
import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.Call
import okhttp3.Callback
import okhttp3.Response
import kotlin.coroutines.resumeWithException
```

`once` を置き換える:

```kotlin
  // Cancelling the coroutine cancels the HTTP call, so the poll limit can cut off a request that is still waiting.
  private suspend fun once(method: String, path: String, body: String?): String = suspendCancellableCoroutine { cont ->
    val request = Request.Builder()
      .url("$baseUrl$path")
      .header("x-api-key", apiKey)
      .header("x-user-name", userName)
      .method(method, body?.toRequestBody("application/json".toMediaType()))
      .build()
    val call = http.newCall(request)
    cont.invokeOnCancellation { call.cancel() }
    call.enqueue(object : Callback {
      override fun onFailure(call: Call, e: IOException) {
        cont.resumeWithException(ApiError(ApiErrorKind.NETWORK, e.toString()))
      }

      override fun onResponse(call: Call, response: Response) {
        val outcome = runCatching {
          response.use {
            kindFor(it.code)?.let { kind -> throw ApiError(kind, "HTTP ${it.code}") }
            it.body?.string() ?: throw ApiError(ApiErrorKind.NETWORK, "empty body")
          }
        }.recoverCatching { e -> throw if (e is IOException) ApiError(ApiErrorKind.NETWORK, e.toString()) else e }
        cont.resumeWith(outcome)
      }
    })
  }
```

`Request.Builder().header()` が投げる `IllegalArgumentException`（全角の文字を含むキー）は、これまでどおり呼び出し元へ抜ける（`checkAndSave` がそれを「キーが正しくありません」にしている）。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*PollingTest' --tests '*ApiClientTest' > /tmp/trv2-t1.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t1.log`
Expected: `BUILD SUCCESSFUL`（PollingTest 8件・ApiClientTest 8件）。

- [ ] **Step 5: コミットする**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/Polling.kt app/src/main/java/com/touringproject/v2/api/ApiClient.kt \
  app/src/test/java/com/touringproject/v2/ask/PollingAndConversationTest.kt app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
git commit -m "fix: keep the 120 s poll limit and skip unreadable answer bodies

Fixes #3
Fixes #4"
```

---

### Task 2: 録音が届かないとき（Android issue #1）と、録音の受け口に PCM を渡す

**Files:**
- Modify: `Android/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt`（`RecordingMeta`・`RecordingSink`）
- Modify: `Android/app/src/main/java/com/touringproject/v2/ask/AskController.kt`（`record` の終わり）
- Modify: `Android/app/src/main/java/com/touringproject/v2/audio/AudioTypes.kt`・`PcmRecorder.kt`
- Modify: `Android/app/src/main/java/com/touringproject/v2/AppGraph.kt`（空の受け口の形だけ。中身は Task 7）
- Test: `Android/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt`

**Interfaces:**
- Consumes: なし
- Produces: `@Serializable data class RecordingMeta(name: String, recordedAt: Long, durationMs: Long, phoneMic: Boolean, device: InputDevice?, transcript: String?)`、`interface RecordingSink { fun saved(meta: RecordingMeta, pcm: ByteArray); fun transcribed(name: String, transcript: String) }`、`@Serializable data class InputDevice`。空の PCM は `FailureReason.MIC`

- [ ] **Step 1: 失敗するテストを書く**

`AskControllerTest.kt` の `Harness` を直す。引数の最後（`device` の次）に足す:

```kotlin
  val pcm: ByteArray = byteArrayOf(1, 2, 3),
```

`val metas = mutableListOf<RecordingMeta>()` の次の行に足す:

```kotlin
  val keptPcm = mutableListOf<ByteArray>()
```

録音の作り物の `stop` を `return Recorded(pcm, "rec-0.pcm")` に、受け口を次に替える:

```kotlin
      override fun saved(meta: RecordingMeta, pcm: ByteArray) { metas += meta; keptPcm += pcm }
```

`the_kept_recording_is_described_for_sc12` の `assertEquals(listOf(RecordingMeta(...)), h.metas)` の次の行に足す:

```kotlin
    assertEquals(listOf(listOf<Byte>(1, 2, 3)), h.keptPcm.map { it.toList() })
```

そのテストの後に足す:

```kotlin
  @Test
  fun a_recording_with_nothing_in_it_fails_as_a_microphone_problem() = runTest {
    // e.g. another app holds the microphone (issue #1): "録音できませんでした", not "聞き取れませんでした".
    val h = Harness(this, pcm = ByteArray(0))
    h.controller.run(Source.HANDSFREE)
    assertFalse("post" in h.log)
    assertTrue(h.states.any { it.phase == Phase.FAILED && it.failure == FailureReason.MIC })
    assertTrue("say:録音できませんでした。" in h.log)
    assertTrue(h.metas.isEmpty())
    assertEquals(Phase.IDLE, h.phase)
  }
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AskControllerTest' > /tmp/trv2-t2.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t2.log | head`
Expected: コンパイルの失敗（`saved` の形が違う）。

- [ ] **Step 3: 実装する**

`AskPorts.kt` の import に `import kotlinx.serialization.Serializable` を足し、`RecordingMeta` と `RecordingSink` を置き換える:

```kotlin
/** What SC-12 shows about each kept recording (slice 1 spec §5.4). Saved as JSON beside the PCM. */
@Serializable
data class RecordingMeta(
  val name: String,
  val recordedAt: Long,
  val durationMs: Long,
  val phoneMic: Boolean,
  val device: InputDevice?,
  val transcript: String?,
)

/** Fire and forget: a failure here must not end the ask. */
interface RecordingSink {
  fun saved(meta: RecordingMeta, pcm: ByteArray)
  fun transcribed(name: String, transcript: String)
}
```

`AudioTypes.kt` を置き換える:

```kotlin
package com.touringproject.v2.audio

import kotlinx.serialization.Serializable

// Values the ask loop reads from the audio side; kept apart from AudioRoute so the loop compiles without it.
data class MediaVolume(val current: Int, val max: Int)

@Serializable
data class InputDevice(val type: Type, val name: String) {
  enum class Type { BLUETOOTH, BUILTIN, OTHER }
}

data class RouteResult(val ok: Boolean, val note: String)
```

`AskController.kt` の `record` の終わりの次の2行:

```kotlin
    d.route.stop()
    d.recordings.saved(RecordingMeta(stopped.name, startedAt, pcmDurationMs(stopped.pcm.size), phoneMic, device, null))
```

を置き換える:

```kotlin
    d.route.stop()
    // A microphone held by another app can start without delivering anything; sending nothing would be heard as "no speech".
    if (stopped.pcm.isEmpty()) {
      d.location.end()
      fail(FailureReason.MIC, run)
      return null
    }
    d.recordings.saved(RecordingMeta(stopped.name, startedAt, pcmDurationMs(stopped.pcm.size), phoneMic, device, null), stopped.pcm)
```

`PcmRecorder.kt` の `start` の `ar.startRecording()` の次に足す:

```kotlin
    // Another app holding the microphone leaves the recorder stopped (issue #1): say so instead of sending silence.
    if (ar.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
      ar.release()
      error("AudioRecord did not start")
    }
```

`stop` を置き換える:

```kotlin
  override suspend fun stop(): Recorded = withContext(Dispatchers.IO) {
    val ar = checkNotNull(record) { "not recording" }
    // The system silences a recording when another app takes the microphone; what was recorded is then only zeros.
    val silenced = runCatching { ar.activeRecordingConfiguration?.isClientSilenced == true }.getOrDefault(false)
    finish(ar)
    if (silenced) {
      name = null
      error("recording was silenced")
    }
    val pcm = synchronized(buffer) { buffer.toByteArray() }
    Recorded(pcm, checkNotNull(name)).also { name = null }
  }
```

（`start`・`stop` が投げると、司令塔はこれまでどおり `FailureReason.MIC`「録音できませんでした。」にする。実際にマイクを取られたときの振る舞いは、端末でしか確かめられない。）

`AppGraph.kt` の空の受け口を新しい形にする（次の行を）:

```kotlin
        override fun saved(meta: RecordingMeta) = Unit
```

```kotlin
        override fun saved(meta: RecordingMeta, pcm: ByteArray) = Unit
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AskControllerTest' > /tmp/trv2-t2.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t2.log | head`
Expected: `BUILD SUCCESSFUL`（34件）。

- [ ] **Step 5: コミットする**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt \
  app/src/main/java/com/touringproject/v2/audio/AudioTypes.kt app/src/main/java/com/touringproject/v2/audio/PcmRecorder.kt \
  app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
git commit -m "fix: fail a recording that never started instead of sending silence

Hand the PCM to the recording sink so it can be kept for SC-12.

Fixes #1"
```

---

### Task 3: 回答の音声の合間の「やめる」（Android issue #2）

**Files:**
- Modify: `Android/app/src/main/java/com/touringproject/v2/audio/ExoAnswerPlayer.kt`
- Test: `Android/app/src/test/java/com/touringproject/v2/audio/AudioTest.kt`

**Interfaces:**
- Consumes: なし
- Produces: `class ClipSequence { fun stop(); suspend fun play(urls: List<String>, playOne: suspend (String) -> Unit) }`。`ExoAnswerPlayer` の公開面（`AnswerPlayer`）は変えない

- [ ] **Step 1: 失敗するテストを書く**

`AudioTest.kt` の `class CueTest {` の前に足す:

```kotlin
class ClipSequenceTest {
  @Test
  fun a_stop_between_two_clips_keeps_the_next_one_silent() = runTest {
    val sequence = ClipSequence()
    val played = mutableListOf<String>()
    // The stop arrives after the first clip has ended and before the second one starts.
    sequence.play(listOf("1", "2", "3")) { url -> played += url; if (url == "1") sequence.stop() }
    assertEquals(listOf("1"), played)
  }

  @Test
  fun without_a_stop_every_clip_plays_in_order() = runTest {
    val played = mutableListOf<String>()
    ClipSequence().play(listOf("1", "2")) { played += it }
    assertEquals(listOf("1", "2"), played)
  }
}

```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ClipSequenceTest' > /tmp/trv2-t3.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t3.log | head`
Expected: コンパイルの失敗（`ClipSequence` が無い）。

- [ ] **Step 3: 実装する**

`ExoAnswerPlayer.kt` の、`// Plays the answer clips one after another ...` のコメントから `private suspend fun playOne(url: String, session: Session) = suspendCancellableCoroutine { cont ->` の行までを置き換える:

```kotlin
/** One answer's clips in order. A stop ends the clip playing now and every clip after it, also between two clips (issue #2). */
class ClipSequence {
  private var stopped = false

  fun stop() {
    stopped = true
  }

  suspend fun play(urls: List<String>, playOne: suspend (String) -> Unit) {
    for (url in urls) {
      if (stopped) return
      playOne(url)
    }
  }
}

// Plays the answer clips one after another on the media stream, without taking audio focus (mix with the nav app).
class ExoAnswerPlayer(private val context: Context) : AnswerPlayer {
  private val main = Handler(Looper.getMainLooper())
  private var stopCurrent: (() -> Unit)? = null
  private var sequence: ClipSequence? = null

  override suspend fun play(urls: List<String>) = withContext(Dispatchers.Main) {
    val next = ClipSequence()
    sequence = next
    try {
      next.play(urls) { playOne(it) }
    } finally {
      if (sequence === next) sequence = null
    }
  }

  override fun stop() {
    main.post {
      sequence?.stop()
      stopCurrent?.invoke()
    }
  }

  private suspend fun playOne(url: String) = suspendCancellableCoroutine { cont ->
```

同じファイルの `playOne` の中の次の4行:

```kotlin
    stop = {
      session.stopped = true
      finish(null)
    }
```

を置き換える:

```kotlin
    stop = { finish(null) }
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ClipSequenceTest' --tests '*AskControllerTest' > /tmp/trv2-t3.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t3.log | head`
Expected: `BUILD SUCCESSFUL`。

- [ ] **Step 5: コミットする**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/audio/ExoAnswerPlayer.kt app/src/test/java/com/touringproject/v2/audio/AudioTest.kt
git commit -m "fix: let a stop between two answer clips silence the rest

Fixes #2"
```

---

### Task 4: 接続キーを保存できないとき（Android issue #5）

**Files:**
- Modify: `Android/app/src/main/java/com/touringproject/v2/settings/ApiKeyStore.kt`（`save`）
- Modify: `Android/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt`（`KeyCheck`・`checkAndSave`・`ConnectionScreen` の文言）
- Test: `Android/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt`・`.../ui/LabelsTest.kt`

**Interfaces:**
- Consumes: なし
- Produces: `enum class KeyCheck(val message: String) { SAVED, INVALID, UNREACHABLE, SAVE_FAILED }`。`ApiKeyStore.save` は封じられなかったら投げ、使うキーは元のまま

- [ ] **Step 1: 失敗するテストを書く**

`SettingsTest.kt` の `class ApiKeyStoreTest` の最後に足す:

```kotlin
  @Test
  fun a_key_that_cannot_be_sealed_leaves_the_old_one_in_use() = runTest {
    val store = FakeStore()
    var failing = false
    val cipher = object : SecretCipher {
      override fun encrypt(plain: ByteArray): ByteArray = if (failing) throw java.security.KeyStoreException("no key") else plain.reversedArray()
      override fun decrypt(sealed: ByteArray) = sealed.reversedArray()
    }
    val keys = ApiKeyStore(store, cipher)
    keys.save("old-key")
    failing = true
    assertTrue(runCatching { keys.save("new-key") }.isFailure)
    assertEquals("old-key", keys.current())
    assertEquals("old-key", ApiKeyStore(store, cipher).load())
  }
```

`LabelsTest.kt` の `a_key_the_http_header_cannot_carry_is_refused_without_crashing` の次の行:

```kotlin
    assertEquals(KeyCheck.UNREACHABLE, checkAndSave("x", {}, { throw java.security.GeneralSecurityException("keystore") }))
```

を替える:

```kotlin
    assertEquals(KeyCheck.SAVE_FAILED, checkAndSave("x", {}, { throw java.security.GeneralSecurityException("keystore") }))
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ApiKeyStoreTest' --tests '*LabelsTest' > /tmp/trv2-t4.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t4.log | head`
Expected: コンパイルの失敗（`SAVE_FAILED` が無い）。

- [ ] **Step 3: 実装する**

`ApiKeyStore.kt` の `save` を置き換える（封じてから、使うキーを替える）:

```kotlin
  /** Throws when the key cannot be sealed or stored; the key in use then stays the old one. */
  suspend fun save(key: String?) {
    store.set(API_KEY_KEY, key?.let { Base64.getEncoder().encodeToString(cipher.encrypt(it.toByteArray(Charsets.UTF_8))) })
    state.value = key
  }
```

`SettingsScreens.kt` の `enum class KeyCheck ...` から `checkAndSave` の終わりまでを置き換える:

```kotlin
enum class KeyCheck(val message: String) {
  SAVED("保存しました"),
  INVALID("キーが正しくありません。元のキーのままです。"),
  UNREACHABLE("サーバーに繋がりません。元のキーのままです。"),
  SAVE_FAILED("キーを保存できませんでした。元のキーのままです。"),
}

/** Checks the key against the Backend, then saves it; the old key stays when either step fails. */
suspend fun checkAndSave(key: String, check: suspend (String) -> Unit, save: suspend (String) -> Unit): KeyCheck {
  try {
    check(key)
  } catch (e: ApiError) {
    return if (e.kind == ApiErrorKind.INVALID_KEY) KeyCheck.INVALID else KeyCheck.UNREACHABLE
  } catch (e: IllegalArgumentException) {
    // OkHttp refuses header values it cannot send (e.g. full-width characters pasted into the key).
    return KeyCheck.INVALID
  } catch (e: kotlinx.coroutines.CancellationException) {
    throw e
  } catch (e: Exception) {
    return KeyCheck.UNREACHABLE
  }
  return try {
    save(key)
    KeyCheck.SAVED
  } catch (e: kotlinx.coroutines.CancellationException) {
    throw e
  } catch (e: Exception) {
    // e.g. the Keystore refuses to seal it (issue #5): the server was reachable, so do not say it was not.
    KeyCheck.SAVE_FAILED
  }
}
```

`ConnectionScreen` の中の次の5行:

```kotlin
          message = when (checkAndSave(key, check, save)) {
            KeyCheck.SAVED -> { input = ""; "保存しました" }
            KeyCheck.INVALID -> "キーが正しくありません。元のキーのままです。"
            KeyCheck.UNREACHABLE -> "サーバーに繋がりません。元のキーのままです。"
          }
```

を置き換える:

```kotlin
          val result = checkAndSave(key, check, save)
          if (result == KeyCheck.SAVED) input = ""
          message = result.message
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ApiKeyStoreTest' --tests '*LabelsTest' --tests '*SettingsScreensTest' > /tmp/trv2-t4.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t4.log | head`
Expected: `BUILD SUCCESSFUL`。

- [ ] **Step 5: コミットする**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/settings/ApiKeyStore.kt app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt \
  app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
git commit -m "fix: tell a key that cannot be saved apart from an unreachable server

Fixes #5"
```

---

### Task 5: 録音の置き場（直近10件と付随情報）

**Files:**
- Create: `Android/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt`
- Test: `Android/app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt`

**Interfaces:**
- Consumes: `RecordingMeta`・`RecordingSink`（Task 2）
- Produces: `const val KEEP_RECORDINGS = 10`、`fun metaName(pcmName: String): String`、`fun recordingsToDelete(names: Collection<String>, keep: Int = KEEP_RECORDINGS): List<String>`、`class RecordingStore(dir: File, io: CoroutineDispatcher = Dispatchers.IO, keep: Int = KEEP_RECORDINGS)` に `val changes: StateFlow<Int>`・`suspend fun save(meta, pcm)`・`suspend fun setTranscript(name, transcript)`・`suspend fun list(): List<RecordingMeta>`・`suspend fun read(name): ByteArray`・`suspend fun deleteAll()`、`class RecordingKeeper(store, scope, logError: (String, Throwable) -> Unit) : RecordingSink`

- [ ] **Step 1: 失敗するテストを書く**

`RecordingStoreTest.kt` を作る:

```kotlin
package com.touringproject.v2.recordings

import com.touringproject.v2.ask.RecordingMeta
import com.touringproject.v2.audio.InputDevice
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

private fun meta(time: Long, transcript: String? = null) =
  RecordingMeta("rec-$time.pcm", time, 1_500, false, InputDevice(InputDevice.Type.BLUETOOTH, "M1-S PRO"), transcript)

class RecordingStoreTest {
  @get:Rule val folder = TemporaryFolder()
  private val dir get() = File(folder.root, "recordings")

  @Test
  fun a_saved_recording_is_listed_and_can_be_read_back() = runTest {
    val store = RecordingStore(dir)
    store.save(meta(100), byteArrayOf(1, 2, 3))
    assertEquals(listOf(meta(100)), store.list())
    assertArrayEquals(byteArrayOf(1, 2, 3), store.read("rec-100.pcm"))
  }

  @Test
  fun the_eleventh_recording_removes_the_oldest_with_its_json() = runTest {
    val store = RecordingStore(dir)
    (1L..11L).forEach { store.save(meta(it), byteArrayOf(it.toByte())) }
    assertEquals((11L downTo 2L).toList(), store.list().map { it.recordedAt })
    assertFalse(File(dir, "rec-1.pcm").exists())
    assertFalse(File(dir, "rec-1.json").exists())
    assertEquals(20, dir.list()!!.size)
  }

  @Test
  fun a_recording_missing_half_of_its_files_does_not_take_a_slot() = runTest {
    dir.mkdirs()
    File(dir, "rec-1.pcm").writeBytes(byteArrayOf(1)) // no JSON
    File(dir, "rec-2.pcm").writeBytes(byteArrayOf(1))
    File(dir, "rec-2.json").writeText("{not json")
    File(dir, "rec-3.json").writeText("""{"name":"rec-3.pcm","recordedAt":3,"durationMs":1,"phoneMic":false,"device":null,"transcript":null}""") // no PCM
    val store = RecordingStore(dir)
    (100L..109L).forEach { store.save(meta(it), byteArrayOf(1)) }
    assertEquals(10, store.list().size)
    assertEquals(20, dir.list()!!.size)
  }

  @Test
  fun what_was_heard_is_added_later() = runTest {
    val store = RecordingStore(dir)
    store.save(meta(100), byteArrayOf(1))
    store.setTranscript("rec-100.pcm", "富士山の高さは")
    assertEquals(listOf(meta(100, "富士山の高さは")), store.list())
  }

  @Test
  fun a_transcript_for_a_recording_that_is_gone_creates_nothing() = runTest {
    val store = RecordingStore(dir)
    store.setTranscript("rec-100.pcm", "x")
    store.setTranscript("../evil.pcm", "x")
    assertFalse(dir.exists())
  }

  @Test
  fun delete_all_then_a_new_recording_is_still_kept() = runTest {
    // An ask that is recording while "delete all" runs must still keep its recording (React Native version's issue #11).
    val store = RecordingStore(dir)
    store.save(meta(100), byteArrayOf(1))
    store.deleteAll()
    assertEquals(emptyList<RecordingMeta>(), store.list())
    store.save(meta(200), byteArrayOf(2))
    assertEquals(listOf(meta(200)), store.list())
  }

  @Test
  fun every_change_is_announced() = runTest {
    val store = RecordingStore(dir)
    val before = store.changes.value
    store.save(meta(100), byteArrayOf(1))
    store.setTranscript("rec-100.pcm", "x")
    store.deleteAll()
    assertEquals(before + 3, store.changes.value)
  }

  @Test
  fun the_keeper_never_lets_a_store_failure_reach_the_ask() = runTest {
    // A file where the directory should be: every write fails.
    folder.root.resolve("recordings").writeText("not a directory")
    val errors = mutableListOf<String>()
    // The store's file work runs on the test scheduler here, so advanceUntilIdle waits for it.
    val keeper = RecordingKeeper(RecordingStore(dir, io = StandardTestDispatcher(testScheduler)), this) { message, _ -> errors += message }
    keeper.saved(meta(100), byteArrayOf(1))
    keeper.transcribed("rec-100.pcm", "x")
    testScheduler.advanceUntilIdle()
    assertTrue(errors.contains("recording save failed"))
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordingStoreTest' > /tmp/trv2-t5.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t5.log | head`
Expected: コンパイルの失敗（`RecordingStore` が無い）。

- [ ] **Step 3: 実装する**

`RecordingStore.kt` を作る:

```kotlin
package com.touringproject.v2.recordings

import com.touringproject.v2.ask.RecordingMeta
import com.touringproject.v2.ask.RecordingSink
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import java.io.File

// The newest recordings stay on the device for SC-12 (slice 1 spec §5.4): rec-<time>.pcm with rec-<time>.json beside it.
const val KEEP_RECORDINGS = 10
private val FILE_RE = Regex("^rec-(\\d+)\\.(pcm|json)$")
private val PCM_RE = Regex("^rec-\\d+\\.pcm$")

fun metaName(pcmName: String): String = pcmName.removeSuffix(".pcm") + ".json"

/** Files to delete so that only the newest [keep] complete recordings remain. A PCM without its JSON (or the reverse) goes too. */
fun recordingsToDelete(names: Collection<String>, keep: Int = KEEP_RECORDINGS): List<String> {
  val byTime = names.mapNotNull { name -> FILE_RE.matchEntire(name)?.let { it.groupValues[1].toLong() to name } }
    .groupBy({ it.first }, { it.second })
  val kept = byTime.filterValues { it.size == 2 }.keys.sortedDescending().take(keep).toSet()
  return byTime.filterKeys { it !in kept }.values.flatten().sorted()
}

/** The kept recordings on disk. Every change runs under one lock, so a save, a prune and "delete all" never interleave. */
class RecordingStore(private val dir: File, private val io: CoroutineDispatcher = Dispatchers.IO, private val keep: Int = KEEP_RECORDINGS) {
  private val mutex = Mutex()
  private val json = Json { ignoreUnknownKeys = true }
  private val changeCount = MutableStateFlow(0)

  /** Bumped after every change, so SC-12 can reload its list. */
  val changes: StateFlow<Int> = changeCount.asStateFlow()

  suspend fun save(meta: RecordingMeta, pcm: ByteArray) = change {
    require(PCM_RE.matches(meta.name)) { "bad recording name" }
    dir.mkdirs()
    File(dir, meta.name).writeBytes(pcm)
    File(dir, metaName(meta.name)).writeText(json.encodeToString(RecordingMeta.serializer(), meta))
    // A JSON that cannot be read would hold a slot without ever being listed.
    dir.listFiles { file -> file.name.endsWith(".json") }?.filter { parse(it) == null }?.forEach { it.delete() }
    recordingsToDelete(dir.list()?.toList() ?: emptyList(), keep).forEach { File(dir, it).delete() }
  }

  /** Adds what the Backend heard; does nothing when the recording is already gone. */
  suspend fun setTranscript(name: String, transcript: String) = change {
    if (!PCM_RE.matches(name)) return@change
    val file = File(dir, metaName(name))
    val meta = parse(file) ?: return@change
    file.writeText(json.encodeToString(RecordingMeta.serializer(), meta.copy(transcript = transcript)))
  }

  /** Newest first; only recordings whose PCM and JSON are both there. */
  suspend fun list(): List<RecordingMeta> = mutex.withLock {
    withContext(io) {
      val names = dir.list()?.toSet() ?: emptySet()
      names.filter { it.endsWith(".json") }
        .mapNotNull { name -> parse(File(dir, name))?.takeIf { metaName(it.name) == name && it.name in names } }
        .sortedByDescending { it.recordedAt }
    }
  }

  suspend fun read(name: String): ByteArray = mutex.withLock {
    require(PCM_RE.matches(name)) { "bad recording name" }
    withContext(io) { File(dir, name).readBytes() }
  }

  suspend fun deleteAll() = change { dir.deleteRecursively() }

  private suspend fun change(block: () -> Unit) {
    try {
      mutex.withLock { withContext(io) { block() } }
    } finally {
      changeCount.update { it + 1 }
    }
  }

  private fun parse(file: File): RecordingMeta? =
    runCatching { json.decodeFromString(RecordingMeta.serializer(), file.readText()) }.getOrNull()?.takeIf { PCM_RE.matches(it.name) }
}

/** What the ask loop records goes to the store in the background; a failure there is only logged, never fails the ask. */
class RecordingKeeper(
  private val store: RecordingStore,
  private val scope: CoroutineScope,
  private val logError: (String, Throwable) -> Unit,
) : RecordingSink {
  override fun saved(meta: RecordingMeta, pcm: ByteArray) {
    scope.launch { guard("save") { store.save(meta, pcm) } }
  }

  override fun transcribed(name: String, transcript: String) {
    scope.launch { guard("transcript") { store.setTranscript(name, transcript) } }
  }

  private suspend fun guard(what: String, block: suspend () -> Unit) {
    try {
      block()
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      logError("recording $what failed", e)
    }
  }
}
```

録音は司令塔のメモリの中で録り、止めた後で置き場に書く。そのため、録音中に「すべて消す」が走っても質問は失敗しない（React Native 版の #11 はファイルに直接録っていたので起きた）。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordingStoreTest' > /tmp/trv2-t5.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t5.log | head`
Expected: `BUILD SUCCESSFUL`（8件）。

- [ ] **Step 5: コミットする**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt
git commit -m "feat: keep the newest ten recordings with what SC-12 shows"
```

---

### Task 6: 試し録りの司令塔と、PCM の再生

**Files:**
- Create: `Android/app/src/main/java/com/touringproject/v2/recordings/Trial.kt`
- Create: `Android/app/src/main/java/com/touringproject/v2/audio/PcmPlayer.kt`
- Test: `Android/app/src/test/java/com/touringproject/v2/recordings/TrialTest.kt`・`.../audio/AudioTest.kt`

**Interfaces:**
- Consumes: `RouteControl`・`Recorder`・`Recorded`・`Source`・`RECORD_LIMIT_MS`・`TICK_MS`（`ask`）、`InputDevice`
- Produces: `enum class TrialPhase { IDLE, RECORDING, PLAYING }`、`data class TrialState(phase, phoneMic, device, error: String?)`、`val TRIAL_IDLE`、`TRIAL_MIC_MESSAGE`・`TRIAL_RECORD_MESSAGE`・`TRIAL_PLAY_MESSAGE`、`interface PcmPlayback { suspend fun play(pcm: ByteArray); fun stop() }`、`class TrialDeps(now, sleep, micAllowed, route, recorder, cueStart, player, onState)`、`class TrialController(deps)` に `state`・`active`・`stop()`・`cancel()`・`suspend fun start()`、`class PcmPlayer(pollMs: Long = 50) : PcmPlayback`

- [ ] **Step 1: 失敗するテストを書く**

`TrialTest.kt` を作る:

```kotlin
package com.touringproject.v2.recordings

import com.touringproject.v2.ask.RECORD_LIMIT_MS
import com.touringproject.v2.ask.Recorded
import com.touringproject.v2.ask.Recorder
import com.touringproject.v2.ask.RouteControl
import com.touringproject.v2.ask.Source
import com.touringproject.v2.audio.InputDevice
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private val INTERCOM = InputDevice(InputDevice.Type.BLUETOOTH, "M1-S PRO")

/** A fake world around the trial controller that records what it was asked to do, in order. */
private class TrialHarness(
  val scope: TestScope,
  val micAllowed: Boolean = true,
  val routeOk: Boolean = true,
  var routeGate: CompletableDeferred<Unit>? = null,
  val recorderError: Exception? = null,
  val pcm: ByteArray = byteArrayOf(1, 2),
  var playGate: CompletableDeferred<Unit>? = null,
  val playError: Exception? = null,
) {
  val log = mutableListOf<String>()
  val states = mutableListOf<TrialState>()
  val trial = TrialController(
    TrialDeps(
      now = { scope.testScheduler.currentTime },
      sleep = { delay(it) },
      micAllowed = { micAllowed },
      route = object : RouteControl {
        override suspend fun start(source: Source): Boolean {
          log += "route:${source.name.lowercase()}"
          routeGate?.await()
          return routeOk
        }
        override suspend fun stop() { log += "route:stop" }
        override fun inputDevice() = INTERCOM
      },
      recorder = object : Recorder {
        override suspend fun start() { log += "rec:start"; recorderError?.let { throw it } }
        override suspend fun stop(): Recorded { log += "rec:stop"; return Recorded(pcm, "trial.pcm") }
        override suspend fun cancel() { log += "rec:cancel" }
      },
      cueStart = { log += "cue:start" },
      player = object : PcmPlayback {
        override suspend fun play(pcm: ByteArray) {
          log += "play:${pcm.size}"
          playError?.let { throw it }
          playGate?.await()
        }
        override fun stop() {
          log += "play:stop"
          playGate?.complete(Unit)
        }
      },
      onState = { states += it },
    ),
  )

  fun launchStart() = scope.launch { trial.start() }

  fun until(condition: () -> Boolean) {
    var steps = 0
    while (!condition()) {
      scope.testScheduler.advanceTimeBy(1)
      scope.testScheduler.runCurrent()
      check(++steps < 1_000_000) { "condition never became true" }
    }
  }
}

class TrialTest {
  @Test
  fun records_until_stopped_then_plays_it_back_and_shows_the_microphone() = runTest {
    val h = TrialHarness(this)
    val job = h.launchStart()
    h.until { "cue:start" in h.log }
    assertEquals(TrialPhase.RECORDING, h.trial.state.phase)
    h.trial.stop()
    job.join()
    assertEquals(listOf("route:screen", "rec:start", "cue:start", "rec:stop", "route:stop", "play:2"), h.log)
    assertEquals(TrialState(device = INTERCOM), h.trial.state)
    assertTrue(h.states.any { it.phase == TrialPhase.PLAYING })
  }

  @Test
  fun recording_stops_by_itself_at_the_limit() = runTest {
    val h = TrialHarness(this)
    h.trial.start()
    assertTrue("play:2" in h.log)
    assertTrue(testScheduler.currentTime >= RECORD_LIMIT_MS)
  }

  @Test
  fun the_button_during_playback_stops_the_playback() = runTest {
    val h = TrialHarness(this, playGate = CompletableDeferred())
    val job = h.launchStart()
    h.until { "cue:start" in h.log }
    h.trial.stop()
    h.until { h.trial.state.phase == TrialPhase.PLAYING }
    h.trial.stop()
    job.join()
    assertTrue("play:stop" in h.log)
    assertEquals(TrialPhase.IDLE, h.trial.state.phase)
  }

  @Test
  fun leaving_while_the_route_is_set_up_never_opens_the_microphone() = runTest {
    // React Native version's issue #10: the old trial must not record or beep once SC-12 is left.
    val gate = CompletableDeferred<Unit>()
    val h = TrialHarness(this, routeGate = gate)
    val job = h.launchStart()
    h.until { "route:screen" in h.log }
    h.trial.cancel()
    assertEquals(TRIAL_IDLE, h.trial.state)
    h.trial.start() // still unwinding: ignored rather than sharing the recorder
    gate.complete(Unit)
    job.join()
    assertEquals(listOf("route:screen", "play:stop", "route:stop"), h.log)
    assertEquals(TRIAL_IDLE, h.trial.state)
  }

  @Test
  fun leaving_while_recording_drops_the_recording() = runTest {
    val h = TrialHarness(this)
    val job = h.launchStart()
    h.until { "cue:start" in h.log }
    h.trial.cancel()
    job.join()
    assertEquals(listOf("route:screen", "rec:start", "cue:start", "play:stop", "rec:cancel", "route:stop"), h.log)
    assertFalse(h.log.any { it.startsWith("play:2") })
  }

  @Test
  fun without_the_microphone_permission_it_says_so() = runTest {
    val h = TrialHarness(this, micAllowed = false)
    h.trial.start()
    assertEquals(TrialState(error = TRIAL_MIC_MESSAGE), h.trial.state)
    assertTrue(h.log.isEmpty())
  }

  @Test
  fun a_recorder_that_cannot_start_releases_the_route() = runTest {
    val h = TrialHarness(this, recorderError = IllegalStateException("busy"))
    h.trial.start()
    assertEquals(listOf("route:screen", "rec:start", "route:stop"), h.log)
    assertEquals(TRIAL_RECORD_MESSAGE, h.trial.state.error)
  }

  @Test
  fun an_empty_recording_is_not_played() = runTest {
    val h = TrialHarness(this, pcm = ByteArray(0))
    h.trial.start()
    assertFalse(h.log.any { it.startsWith("play:") })
    assertEquals(TRIAL_RECORD_MESSAGE, h.trial.state.error)
  }

  @Test
  fun a_playback_that_fails_is_reported() = runTest {
    val h = TrialHarness(this, playError = IllegalStateException("no track"))
    h.trial.start()
    assertEquals(TRIAL_PLAY_MESSAGE, h.trial.state.error)
    assertEquals(TrialPhase.IDLE, h.trial.state.phase)
  }

  @Test
  fun the_phone_microphone_is_shown_when_the_intercom_is_not_reached() = runTest {
    val h = TrialHarness(this, routeOk = false)
    h.trial.start()
    assertTrue(h.trial.state.phoneMic)
    assertNull(h.trial.state.error)
  }
}
```

`AudioTest.kt` の `@RunWith(AndroidJUnit4::class)` `class TtsSpeechTest {` の前に足す:

```kotlin
@RunWith(AndroidJUnit4::class)
class PcmPlayerTest {
  // The shadow track takes every write at once and counts it as played, so stopping midway is checked on the device.
  @Test
  fun a_recording_is_played_to_the_end_and_can_be_played_again(): Unit = kotlinx.coroutines.runBlocking {
    val player = PcmPlayer()
    kotlinx.coroutines.withTimeout(5_000) {
      player.play(ByteArray(3_200))
      player.play(ByteArray(3_200))
    }
  }

  @Test
  fun stopping_when_nothing_plays_is_harmless() {
    PcmPlayer().stop()
  }
}

```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*TrialTest' --tests '*PcmPlayerTest' > /tmp/trv2-t6.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t6.log | head`
Expected: コンパイルの失敗（`TrialController`・`PcmPlayer` が無い）。

- [ ] **Step 3: 実装する**

`Trial.kt` を作る:

```kotlin
package com.touringproject.v2.recordings

import com.touringproject.v2.ask.RECORD_LIMIT_MS
import com.touringproject.v2.ask.Recorder
import com.touringproject.v2.ask.RouteControl
import com.touringproject.v2.ask.Source
import com.touringproject.v2.ask.TICK_MS
import com.touringproject.v2.audio.InputDevice
import kotlinx.coroutines.CancellationException

// The trial recording on SC-12 (slice 1 spec §5.5): recorded over the same route as a question from the screen,
// played back at once on the media stream, sent nowhere and not kept.
enum class TrialPhase { IDLE, RECORDING, PLAYING }

data class TrialState(
  val phase: TrialPhase = TrialPhase.IDLE,
  val phoneMic: Boolean = false,
  val device: InputDevice? = null,
  val error: String? = null,
)

val TRIAL_IDLE = TrialState()

const val TRIAL_MIC_MESSAGE = "マイクの使用が許可されていません。"
const val TRIAL_RECORD_MESSAGE = "録音できませんでした。"
const val TRIAL_PLAY_MESSAGE = "再生できませんでした。"

/** Plays recorded PCM; returns when it has been heard or stopped, throws when it cannot be played. */
interface PcmPlayback {
  suspend fun play(pcm: ByteArray)
  fun stop()
}

class TrialDeps(
  val now: () -> Long,
  val sleep: suspend (Long) -> Unit,
  val micAllowed: () -> Boolean,
  val route: RouteControl,
  val recorder: Recorder,
  val cueStart: () -> Unit,
  val player: PcmPlayback,
  val onState: (TrialState) -> Unit,
)

/** Call it from one thread only (the main thread in the app), like the ask loop. */
class TrialController(private val deps: TrialDeps) {
  var state: TrialState = TRIAL_IDLE
    private set

  private var session = 0
  private var stopRequested = false
  // From start() until its run has unwound, also after a cancel: a second run must not share the recorder and the route.
  private var running = false

  /** A trial is recording or playing: the intercom button ends it instead of starting a question (US-E-03.002). */
  val active: Boolean get() = state.phase != TrialPhase.IDLE

  /** The screen button or the intercom button while a trial runs: end the recording, or the playback. */
  fun stop() {
    when (state.phase) {
      TrialPhase.RECORDING -> stopRequested = true
      TrialPhase.PLAYING -> deps.player.stop()
      TrialPhase.IDLE -> Unit
    }
  }

  /** Leaving SC-12: drop whatever is going on. Whatever the run is awaiting is ignored when it returns. */
  fun cancel() {
    if (!active) return
    session += 1
    deps.player.stop()
    set(TRIAL_IDLE)
  }

  suspend fun start() {
    if (active || running) return
    running = true
    try {
      run(++session)
    } finally {
      running = false
    }
  }

  private suspend fun run(session: Int) {
    val d = deps
    stopRequested = false
    set(TrialState(phase = TrialPhase.RECORDING))
    if (!d.micAllowed()) {
      finish(session, TrialState(error = TRIAL_MIC_MESSAGE))
      return
    }
    val routed = try {
      d.route.start(Source.SCREEN)
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      false
    }
    // Setting up the route can take seconds; SC-12 may have been left meanwhile (React Native version's issue #10).
    if (!isCurrent(session)) {
      d.route.stop()
      return
    }
    set(state.copy(phoneMic = !routed))
    try {
      d.recorder.start()
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      d.route.stop()
      finish(session, TrialState(phoneMic = !routed, error = TRIAL_RECORD_MESSAGE))
      return
    }
    if (!isCurrent(session)) {
      d.recorder.cancel()
      d.route.stop()
      return
    }
    d.cueStart()
    val startedAt = d.now()
    while (isCurrent(session) && !stopRequested && d.now() - startedAt < RECORD_LIMIT_MS) d.sleep(TICK_MS)
    if (!isCurrent(session)) {
      d.recorder.cancel()
      d.route.stop()
      return
    }
    // Read while the recorder still runs: the system only reports the input device of an active recording.
    val device = d.route.inputDevice()
    val recorded = try {
      d.recorder.stop()
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      d.route.stop()
      finish(session, TrialState(phoneMic = !routed, error = TRIAL_RECORD_MESSAGE))
      return
    }
    d.route.stop()
    if (!isCurrent(session)) return
    if (recorded.pcm.isEmpty()) {
      finish(session, TrialState(phoneMic = !routed, device = device, error = TRIAL_RECORD_MESSAGE))
      return
    }
    set(state.copy(phase = TrialPhase.PLAYING, device = device))
    val error = try {
      d.player.play(recorded.pcm)
      null
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      TRIAL_PLAY_MESSAGE
    }
    // Keep showing which microphone was used after the playback.
    finish(session, state.copy(phase = TrialPhase.IDLE, error = error))
  }

  private fun isCurrent(session: Int) = session == this.session

  private fun finish(session: Int, next: TrialState) {
    if (isCurrent(session)) set(next)
  }

  private fun set(next: TrialState) {
    state = next
    deps.onState(next)
  }
}
```

`PcmPlayer.kt` を作る:

```kotlin
package com.touringproject.v2.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import com.touringproject.v2.recordings.PcmPlayback
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

private const val SAMPLE_RATE = 16_000
private const val CHUNK_BYTES = 8_192
// After the last write, the rest still in the track's buffer is waited for, plus this much slack.
private const val DRAIN_SLACK_MS = 1_000L

/**
 * Plays 16 kHz mono 16-bit PCM on the media stream (heard over the intercom's A2DP once the call route is down).
 * SC-12 makes one for the trial recording and another for the kept recordings, so stopping one never stops the other.
 */
class PcmPlayer(private val pollMs: Long = 50) : PcmPlayback {
  private val lock = Any()
  private var track: AudioTrack? = null
  @Volatile private var stopped = false

  override suspend fun play(pcm: ByteArray) {
    // Cleared before switching threads, so a stop() that follows this call is never undone.
    stopped = false
    withContext(Dispatchers.IO) { playOn(pcm) }
  }

  private suspend fun playOn(pcm: ByteArray) {
    val t = AudioTrack.Builder()
      .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
      .setAudioFormat(
        AudioFormat.Builder().setSampleRate(SAMPLE_RATE).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).setEncoding(AudioFormat.ENCODING_PCM_16BIT).build(),
      )
      .setTransferMode(AudioTrack.MODE_STREAM)
      .build()
    if (t.state != AudioTrack.STATE_INITIALIZED) {
      t.release()
      error("AudioTrack not initialized")
    }
    synchronized(lock) { track = t }
    try {
      t.play()
      var written = 0
      // write() blocks while the buffer is full; stop() pauses the track, which makes a blocked write return early.
      while (written < pcm.size && !stopped) {
        val n = t.write(pcm, written, minOf(CHUNK_BYTES, pcm.size - written))
        if (n < 0) error("AudioTrack write failed: $n")
        if (n == 0) break
        written += n
      }
      val frames = written / 2
      val deadline = System.currentTimeMillis() + frames * 1_000L / SAMPLE_RATE + DRAIN_SLACK_MS
      while (!stopped && t.playbackHeadPosition < frames && System.currentTimeMillis() < deadline) delay(pollMs)
    } finally {
      synchronized(lock) {
        track = null
        runCatching { t.stop() }
        t.release()
      }
    }
  }

  override fun stop() {
    stopped = true
    synchronized(lock) { runCatching { track?.pause() } }
  }
}
```

PCM は `AudioTrack` で直接鳴らすので、React Native 版のように WAV の一時ファイルを作らない（スライス1 spec §5.4 の「WAV のヘッダーを付けた一時ファイル」は、expo-audio のための回避策だった）。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*TrialTest' --tests '*PcmPlayerTest' > /tmp/trv2-t6.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t6.log | head`
Expected: `BUILD SUCCESSFUL`（TrialTest 10件・PcmPlayerTest 2件）。

- [ ] **Step 5: コミットする**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/recordings/Trial.kt app/src/main/java/com/touringproject/v2/audio/PcmPlayer.kt \
  app/src/test/java/com/touringproject/v2/recordings/TrialTest.kt app/src/test/java/com/touringproject/v2/audio/AudioTest.kt
git commit -m "feat: add the trial recording and a PCM player for SC-12"
```

---

### Task 7: SC-12 の状態・押下の行き先・組み立て

**Files:**
- Create: `Android/app/src/main/java/com/touringproject/v2/recordings/RecordingCheck.kt`
- Create: `Android/app/src/main/java/com/touringproject/v2/handsfree/PressRouter.kt`
- Modify: `Android/app/src/main/java/com/touringproject/v2/AppGraph.kt`（全体を置き換え）
- Test: `Android/app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt`・`.../handsfree/PressRouterTest.kt`

**Interfaces:**
- Consumes: Task 5 の `RecordingStore`・`RecordingKeeper`、Task 6 の `TrialController`・`TrialDeps`・`PcmPlayback`・`PcmPlayer`・`TRIAL_IDLE`・`TrialState`
- Produces: `class RecordingCheck(store, trial, player, askBusy: () -> Boolean, scope, logError)` に `items: StateFlow<List<RecordingMeta>>`・`playing: StateFlow<String?>`・`message: StateFlow<String?>`・`toggleTrial()`・`play(name)`・`stopPlaying()`・`deleteAll()`・`leave()`、`PLAY_FAILED_MESSAGE`・`DELETE_FAILED_MESSAGE`、`class PressRouter(trialActive, stopTrial, stopCheckPlayback, askPress, askStopRecording)` に `press()`・`recognitionEnded()`。`AppGraph` に `recordingStore`・`trialState: StateFlow<TrialState>`・`trial`・`recordingCheck`・`volumeDismissedAt: StateFlow<Int?>`・`dismissVolumeWarning(level: Int)`

- [ ] **Step 1: 失敗するテストを書く**

`RecordingCheckTest.kt` を作る:

```kotlin
package com.touringproject.v2.recordings

import com.touringproject.v2.ask.RecordingMeta
import com.touringproject.v2.ask.Recorded
import com.touringproject.v2.ask.Recorder
import com.touringproject.v2.ask.RouteControl
import com.touringproject.v2.ask.Source
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

private fun meta(time: Long) = RecordingMeta("rec-$time.pcm", time, 1_000, false, null, null)

class RecordingCheckTest {
  @get:Rule val folder = TemporaryFolder()

  private class World(scope: TestScope, dir: File, var askBusy: Boolean = false, val playError: Exception? = null) {
    val log = mutableListOf<String>()
    var playGate: CompletableDeferred<Unit>? = null
    val store = RecordingStore(dir, io = StandardTestDispatcher(scope.testScheduler))
    val player = object : PcmPlayback {
      override suspend fun play(pcm: ByteArray) {
        log += "play:${pcm.toList()}"
        playError?.let { throw it }
        playGate?.await()
      }
      override fun stop() {
        log += "play:stop"
        playGate?.complete(Unit)
      }
    }
    val trial = TrialController(
      TrialDeps(
        now = { scope.testScheduler.currentTime },
        sleep = { delay(it) },
        micAllowed = { true },
        route = object : RouteControl {
          override suspend fun start(source: Source) = true
          override suspend fun stop() = Unit
          override fun inputDevice() = null
        },
        recorder = object : Recorder {
          override suspend fun start() = Unit
          override suspend fun stop() = Recorded(byteArrayOf(9), "trial.pcm")
          override suspend fun cancel() = Unit
        },
        cueStart = { log += "cue:start" },
        player = object : PcmPlayback {
          override suspend fun play(pcm: ByteArray) { log += "trial:play" }
          override fun stop() { log += "trial:stop" }
        },
        onState = {},
      ),
    )
    // Like the app's scope: runs on the test clock, and advanceUntilIdle waits for it (backgroundScope would not).
    private val appScope = CoroutineScope(SupervisorJob() + StandardTestDispatcher(scope.testScheduler))
    val check = RecordingCheck(store, trial, player, { askBusy }, appScope) { message, _ -> log += message }
  }

  @Test
  fun the_list_follows_the_store_newest_first() = runTest {
    val w = World(this, folder.root)
    w.store.save(meta(1), byteArrayOf(1))
    w.store.save(meta(2), byteArrayOf(2))
    testScheduler.advanceUntilIdle()
    assertEquals(listOf(meta(2), meta(1)), w.check.items.value)
    w.store.setTranscript("rec-1.pcm", "富士山")
    testScheduler.advanceUntilIdle()
    assertEquals("富士山", w.check.items.value[1].transcript)
  }

  @Test
  fun a_kept_recording_is_played_from_its_file() = runTest {
    val w = World(this, folder.root)
    w.store.save(meta(1), byteArrayOf(4, 5))
    w.playGate = CompletableDeferred()
    w.check.play("rec-1.pcm")
    testScheduler.advanceUntilIdle()
    assertEquals("rec-1.pcm", w.check.playing.value)
    w.check.stopPlaying()
    testScheduler.advanceUntilIdle()
    assertEquals(listOf("play:[4, 5]", "play:stop"), w.log)
    assertNull(w.check.playing.value)
  }

  @Test
  fun a_recording_that_cannot_be_played_says_so() = runTest {
    val w = World(this, folder.root, playError = IllegalStateException("no track"))
    w.store.save(meta(1), byteArrayOf(1))
    w.check.play("rec-1.pcm")
    testScheduler.advanceUntilIdle()
    assertEquals(PLAY_FAILED_MESSAGE, w.check.message.value)
    assertNull(w.check.playing.value)
  }

  @Test
  fun delete_all_empties_the_list() = runTest {
    val w = World(this, folder.root)
    w.store.save(meta(1), byteArrayOf(1))
    testScheduler.advanceUntilIdle()
    w.check.deleteAll()
    testScheduler.advanceUntilIdle()
    assertEquals(emptyList<RecordingMeta>(), w.check.items.value)
  }

  @Test
  fun nothing_starts_while_a_question_runs() = runTest {
    val w = World(this, folder.root, askBusy = true)
    w.store.save(meta(1), byteArrayOf(1))
    testScheduler.advanceUntilIdle()
    w.check.play("rec-1.pcm")
    w.check.toggleTrial()
    w.check.deleteAll()
    testScheduler.advanceUntilIdle()
    assertEquals(emptyList<String>(), w.log)
    assertEquals(1, w.check.items.value.size)
  }

  @Test
  fun leaving_stops_only_this_screens_playback() = runTest {
    // The answer has its own player: leaving SC-12 must not reach it (4b #6).
    val w = World(this, folder.root)
    w.store.save(meta(1), byteArrayOf(1))
    w.playGate = CompletableDeferred()
    w.check.play("rec-1.pcm")
    testScheduler.advanceUntilIdle()
    w.check.leave()
    testScheduler.advanceUntilIdle()
    assertEquals(listOf("play:[1]", "play:stop"), w.log)
    assertNull(w.check.playing.value)
  }

  @Test
  fun the_trial_button_starts_and_ends_a_trial() = runTest {
    val w = World(this, folder.root)
    w.check.toggleTrial()
    testScheduler.runCurrent()
    assertTrue(w.trial.active)
    w.check.toggleTrial()
    testScheduler.advanceUntilIdle()
    assertEquals(listOf("cue:start", "trial:play"), w.log)
    assertEquals(TrialPhase.IDLE, w.trial.state.phase)
  }
}
```

`PressRouterTest.kt` を作る:

```kotlin
package com.touringproject.v2.handsfree

import org.junit.Assert.assertEquals
import org.junit.Test

class PressRouterTest {
  private val log = mutableListOf<String>()
  private var trialActive = false
  private val router = PressRouter(
    trialActive = { trialActive },
    stopTrial = { log += "trial:stop" },
    stopCheckPlayback = { log += "check:stop" },
    askPress = { log += "ask:press" },
    askStopRecording = { log += "ask:stopRecording" },
  )

  @Test
  fun a_press_during_a_trial_ends_the_trial_and_starts_no_question() {
    // 4b #4
    trialActive = true
    router.press()
    router.recognitionEnded()
    assertEquals(listOf("trial:stop", "trial:stop"), log)
  }

  @Test
  fun a_press_stops_sc12_playback_before_the_question_starts() {
    // 4b #10: a kept recording playing would be picked up by the microphone.
    router.press()
    assertEquals(listOf("check:stop", "ask:press"), log)
  }

  @Test
  fun the_headset_ending_recognition_sends_the_question() {
    router.recognitionEnded()
    assertEquals(listOf("ask:stopRecording"), log)
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordingCheckTest' --tests '*PressRouterTest' > /tmp/trv2-t7.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t7.log | head`
Expected: コンパイルの失敗（`RecordingCheck`・`PressRouter` が無い）。

- [ ] **Step 3: 実装する**

`RecordingCheck.kt` を作る:

```kotlin
package com.touringproject.v2.recordings

import com.touringproject.v2.ask.RecordingMeta
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

const val PLAY_FAILED_MESSAGE = "再生できませんでした"
const val DELETE_FAILED_MESSAGE = "消せませんでした"

/**
 * SC-12's state and actions: the trial recording, the kept recordings and their playback. Call it from the main thread.
 * The kept recordings have their own player, so leaving SC-12 never stops an answer that is being read out.
 */
class RecordingCheck(
  private val store: RecordingStore,
  private val trial: TrialController,
  private val player: PcmPlayback,
  private val askBusy: () -> Boolean,
  private val scope: CoroutineScope,
  private val logError: (String, Throwable) -> Unit,
) {
  private val itemsState = MutableStateFlow<List<RecordingMeta>>(emptyList())
  val items: StateFlow<List<RecordingMeta>> = itemsState.asStateFlow()

  private val playingState = MutableStateFlow<String?>(null)
  /** The name of the kept recording playing now. */
  val playing: StateFlow<String?> = playingState.asStateFlow()

  private val messageState = MutableStateFlow<String?>(null)
  val message: StateFlow<String?> = messageState.asStateFlow()

  init {
    // The list follows the store: a question saved or transcribed while SC-12 is open shows up at once.
    scope.launch { store.changes.collect { reload() } }
  }

  /** The trial button: start a trial, or end the one that runs. */
  fun toggleTrial() {
    if (trial.active) {
      trial.stop()
      return
    }
    if (askBusy() || playingState.value != null) return
    messageState.value = null
    scope.launch { trial.start() }
  }

  fun play(name: String) {
    if (askBusy() || trial.active || playingState.value != null) return
    playingState.value = name
    messageState.value = null
    scope.launch {
      try {
        player.play(store.read(name))
      } catch (e: CancellationException) {
        throw e
      } catch (e: Exception) {
        logError("recording playback failed", e)
        messageState.value = PLAY_FAILED_MESSAGE
      } finally {
        playingState.value = null
      }
    }
  }

  /** The ■ button, and an intercom press while a kept recording plays (the microphone would pick it up). */
  fun stopPlaying() {
    if (playingState.value != null) player.stop()
  }

  /** After DL-01. The cloud's questions and answers stay; only the audio on this device goes. */
  fun deleteAll() {
    if (askBusy() || trial.active) return
    scope.launch {
      try {
        store.deleteAll()
      } catch (e: CancellationException) {
        throw e
      } catch (e: Exception) {
        logError("delete all failed", e)
        messageState.value = DELETE_FAILED_MESSAGE
      }
    }
  }

  /** Leaving SC-12: drop the trial and this screen's playback, nothing else. */
  fun leave() {
    trial.cancel()
    stopPlaying()
  }

  private suspend fun reload() {
    itemsState.value = try {
      store.list()
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      logError("recording list failed", e)
      emptyList()
    }
  }
}
```

`PressRouter.kt` を作る:

```kotlin
package com.touringproject.v2.handsfree

/**
 * Where an intercom press goes. A running trial recording takes it (US-E-03.002: no question starts); otherwise a
 * kept recording playing on SC-12 is stopped first, since the microphone would pick it up, and the ask loop gets it.
 */
class PressRouter(
  private val trialActive: () -> Boolean,
  private val stopTrial: () -> Unit,
  private val stopCheckPlayback: () -> Unit,
  private val askPress: () -> Unit,
  private val askStopRecording: () -> Unit,
) {
  fun press() {
    if (trialActive()) {
      stopTrial()
      return
    }
    stopCheckPlayback()
    askPress()
  }

  /** The headset dropping SCO during a voice-recognition session is the second press. */
  fun recognitionEnded() {
    if (trialActive()) stopTrial() else askStopRecording()
  }
}
```

`AppGraph.kt` を置き換える:

```kotlin
package com.touringproject.v2

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.util.Log
import com.touringproject.v2.api.ApiClient
import com.touringproject.v2.ask.AskController
import com.touringproject.v2.ask.AskDeps
import com.touringproject.v2.ask.ConversationState
import com.touringproject.v2.ask.FlowState
import com.touringproject.v2.ask.IDLE
import com.touringproject.v2.ask.isBusy
import com.touringproject.v2.audio.AudioRoute
import com.touringproject.v2.audio.AudioRouteControl
import com.touringproject.v2.audio.ExoAnswerPlayer
import com.touringproject.v2.audio.PcmPlayer
import com.touringproject.v2.audio.PcmRecorder
import com.touringproject.v2.audio.ToneCues
import com.touringproject.v2.audio.TtsSpeech
import com.touringproject.v2.handsfree.PressGate
import com.touringproject.v2.handsfree.PressRouter
import com.touringproject.v2.location.FusedPositionSource
import com.touringproject.v2.location.PositionTracker
import com.touringproject.v2.nav.AppLauncher
import com.touringproject.v2.recordings.RecordingCheck
import com.touringproject.v2.recordings.RecordingKeeper
import com.touringproject.v2.recordings.RecordingStore
import com.touringproject.v2.recordings.TRIAL_IDLE
import com.touringproject.v2.recordings.TrialController
import com.touringproject.v2.recordings.TrialDeps
import com.touringproject.v2.recordings.TrialState
import com.touringproject.v2.service.ServiceKeepAlive
import com.touringproject.v2.settings.ApiKeyStore
import com.touringproject.v2.settings.DataStoreKeyValueStore
import com.touringproject.v2.settings.KeystoreCipher
import com.touringproject.v2.settings.SettingsRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File

/** Builds the app's parts by hand (no DI library) and owns them for the life of the process. */
class AppGraph(private val context: Context, val scope: CoroutineScope = MainScope()) {
  val apiBaseUrl: String = BuildConfig.API_BASE_URL
  private val store = DataStoreKeyValueStore(context)
  val settings = SettingsRepository(store)
  val apiKeys = ApiKeyStore(store, KeystoreCipher())
  val launcher = AppLauncher(context)
  val audioRoute = AudioRoute(context)
  val conversation = ConversationState()
  val recordingStore = RecordingStore(File(context.filesDir, "recordings"))
  private val cues = ToneCues()
  private val micAllowed = { context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED }

  private val flowState = MutableStateFlow(IDLE)
  val state: StateFlow<FlowState> = flowState.asStateFlow()

  private val ready = MutableStateFlow(false)
  val isReady: StateFlow<Boolean> = ready.asStateFlow()
  private var loaded = false
  private var permissionsAsked = false

  val controller: AskController = AskController(
    AskDeps(
      now = System::currentTimeMillis,
      sleep = { delay(it) },
      settings = settings::current,
      apiKey = { if (apiBaseUrl.isEmpty()) null else apiKeys.current() },
      micAllowed = micAllowed,
      mediaVolume = { runCatching { audioRoute.mediaVolume() }.getOrNull() },
      api = { key, user -> ApiClient(apiBaseUrl, key, user) },
      conversation = conversation,
      route = AudioRouteControl(audioRoute),
      recorder = PcmRecorder(),
      recordings = RecordingKeeper(recordingStore, scope) { message, e -> Log.w("trv2.recordings", message, e) },
      location = PositionTracker(FusedPositionSource(context)),
      service = ServiceKeepAlive(context),
      nav = launcher,
      cues = cues,
      player = ExoAnswerPlayer(context),
      speech = TtsSpeech(context),
      onState = {
        Log.i("trv2.ask", "phase=${it.phase} source=${it.source} failure=${it.failure} phoneMic=${it.phoneMic}")
        flowState.value = it
      },
      log = { event, data -> Log.i("trv2.ask", "$event $data") },
    ),
    scope,
  )

  private val trialFlow = MutableStateFlow(TRIAL_IDLE)
  val trialState: StateFlow<TrialState> = trialFlow.asStateFlow()

  // SC-12: its own route control, recorder and players, so nothing it does is shared with the ask loop.
  val trial = TrialController(
    TrialDeps(
      now = System::currentTimeMillis,
      sleep = { delay(it) },
      micAllowed = micAllowed,
      route = AudioRouteControl(audioRoute),
      recorder = PcmRecorder(),
      cueStart = cues::start,
      player = PcmPlayer(),
      onState = { trialFlow.value = it },
    ),
  )

  val recordingCheck = RecordingCheck(recordingStore, trial, PcmPlayer(), { isBusy(controller.state) }, scope) { message, e ->
    Log.w("trv2.recordings", message, e)
  }

  // The media volume at which the rider closed the low-volume band; kept until the process ends (slice 1 spec §5.6).
  private val volumeDismissed = MutableStateFlow<Int?>(null)
  val volumeDismissedAt: StateFlow<Int?> = volumeDismissed.asStateFlow()

  fun dismissVolumeWarning(level: Int) {
    volumeDismissed.value = level
  }

  private val router = PressRouter(
    trialActive = { trial.active },
    stopTrial = trial::stop,
    stopCheckPlayback = recordingCheck::stopPlaying,
    askPress = controller::press,
    askStopRecording = controller::stopRecording,
  )

  /** The intercom button presses wait here until settings are loaded and the permission prompt has been answered. */
  val presses = PressGate { router.press() }

  init {
    audioRoute.onVoiceRecognitionEnded = { router.recognitionEnded() }
    scope.launch {
      settings.load()
      apiKeys.load()
      loaded = true
      openWhenReady()
    }
  }

  fun permissionsAnswered() {
    permissionsAsked = true
    openWhenReady()
  }

  private fun openWhenReady() {
    if (!loaded || !permissionsAsked || ready.value) return
    ready.value = true
    presses.openGate(System.currentTimeMillis())
  }
}
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordingCheckTest' --tests '*PressRouterTest' --tests '*MainActivityTest' > /tmp/trv2-t7.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t7.log | head`
Expected: `BUILD SUCCESSFUL`（RecordingCheckTest 7件・PressRouterTest 3件・MainActivityTest）。

- [ ] **Step 5: コミットする**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/recordings/RecordingCheck.kt app/src/main/java/com/touringproject/v2/handsfree/PressRouter.kt \
  app/src/main/java/com/touringproject/v2/AppGraph.kt \
  app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt app/src/test/java/com/touringproject/v2/handsfree/PressRouterTest.kt
git commit -m "feat: keep recordings, route intercom presses past SC-12 and wire the recording check"
```

---

### Task 8: 音量の警告の判定と、SC-12 の文言

**Files:**
- Modify: `Android/app/src/main/java/com/touringproject/v2/ui/Labels.kt`（import と、`enum class Banner` から終わりまで）
- Test: `Android/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt`

**Interfaces:**
- Consumes: `MediaVolume`・`InputDevice`、Task 6 の `TrialState`・`TrialPhase`
- Produces: `Banner.LOW_VOLUME`、`homeBanner(hasKey, returnAppMissing, volumeLow: Boolean = false)`、`mediaVolumeLow(MediaVolume?)`、`volumeReadable(Phase)`、`nextVolume(previous, reading)`、`volumeWarning(volume, dismissedAt: Int?)`、`recordedAtLabel(ms)`、`durationLabel(ms)`、`data class Heard(text, failed)`・`transcriptLabel(String?)`、`micLabel(phoneMic, device)`、`data class TrialText(button, status)`・`trialText(TrialState)`

- [ ] **Step 1: 失敗するテストを書く**

`LabelsTest.kt` の import に足す:

```kotlin
import com.touringproject.v2.audio.InputDevice
import com.touringproject.v2.audio.MediaVolume
import com.touringproject.v2.recordings.TRIAL_IDLE
import com.touringproject.v2.recordings.TrialPhase
import com.touringproject.v2.recordings.TrialState
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
```

`overlay_text_per_phase` の前に足す:

```kotlin
  @Test
  fun the_low_volume_band_comes_last() {
    assertEquals(Banner.NO_RETURN_APP, homeBanner(hasKey = true, returnAppMissing = true, volumeLow = true))
    assertEquals(Banner.LOW_VOLUME, homeBanner(hasKey = true, returnAppMissing = false, volumeLow = true))
  }

  @Test
  fun the_media_volume_is_low_below_a_third_of_the_maximum() {
    assertTrue(mediaVolumeLow(MediaVolume(4, 15)))
    assertFalse(mediaVolumeLow(MediaVolume(5, 15)))
    assertFalse(mediaVolumeLow(MediaVolume(0, 0)))
    assertFalse(mediaVolumeLow(null))
  }

  @Test
  fun the_volume_is_only_read_while_no_ask_holds_the_route() {
    assertTrue(volumeReadable(Phase.IDLE))
    assertTrue(volumeReadable(Phase.FAILED))
    assertFalse(volumeReadable(Phase.RECORDING))
    assertFalse(volumeReadable(Phase.SPEAKING))
  }

  @Test
  fun a_withheld_reading_keeps_the_last_good_one() {
    // AudioRoute.mediaVolume() is null while media still routes to the intercom's call link.
    assertEquals(MediaVolume(10, 15), nextVolume(MediaVolume(10, 15), null))
    assertEquals(MediaVolume(3, 15), nextVolume(MediaVolume(10, 15), MediaVolume(3, 15)))
  }

  @Test
  fun a_dismissed_warning_stays_closed_until_the_volume_changes() {
    assertTrue(volumeWarning(MediaVolume(3, 15), null))
    assertFalse(volumeWarning(MediaVolume(3, 15), 3))
    assertTrue(volumeWarning(MediaVolume(2, 15), 3))
    assertFalse(volumeWarning(MediaVolume(10, 15), null))
  }

  @Test
  fun kept_recordings_are_described_in_japan_time() {
    assertEquals("10/17 10:35:07", recordedAtLabel(Instant.parse("2026-10-17T01:35:07Z").toEpochMilli()))
    assertEquals("1.5秒", durationLabel(1_500))
    assertEquals(Heard("（聞き取られた文はまだありません）", false), transcriptLabel(null))
    assertEquals(Heard("聞き取れませんでした", true), transcriptLabel(""))
    assertEquals("インカム（M1-S PRO）", micLabel(false, InputDevice(InputDevice.Type.BLUETOOTH, "M1-S PRO")))
    assertEquals("本体のマイク", micLabel(true, null))
  }

  @Test
  fun the_trial_text_follows_the_trial() {
    assertEquals("試し録り", trialText(TRIAL_IDLE).button)
    assertEquals("止めて聞く", trialText(TrialState(phase = TrialPhase.RECORDING)).button)
    assertEquals("再生中: インカム（M1-S PRO）", trialText(TrialState(phase = TrialPhase.PLAYING, device = InputDevice(InputDevice.Type.BLUETOOTH, "M1-S PRO"))).status)
    assertEquals("録ったマイク: 本体のマイク", trialText(TrialState(phoneMic = true)).status)
  }

```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*LabelsTest' > /tmp/trv2-t8.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t8.log | head`
Expected: コンパイルの失敗（`LOW_VOLUME` などが無い）。

- [ ] **Step 3: 実装する**

`Labels.kt` の import に足す:

```kotlin
import com.touringproject.v2.audio.InputDevice
import com.touringproject.v2.audio.MediaVolume
import com.touringproject.v2.recordings.TrialPhase
import com.touringproject.v2.recordings.TrialState
import java.util.Locale
```

`enum class Banner` からファイルの終わりまでを置き換える:

```kotlin
enum class Banner(val text: String) {
  NO_KEY("接続キーが未設定です（押して設定）"),
  NO_RETURN_APP("戻り先のアプリが未設定です（押して選ぶ）"),
  LOW_VOLUME("メディアの音量が低く、回答が聞こえないかもしれません"),
}

/** SC-02 shows at most one warning band, the most urgent first. */
fun homeBanner(hasKey: Boolean, returnAppMissing: Boolean, volumeLow: Boolean = false): Banner? = when {
  !hasKey -> Banner.NO_KEY
  returnAppMissing -> Banner.NO_RETURN_APP
  volumeLow -> Banner.LOW_VOLUME
  else -> null
}

/** Answers and cues play on the media stream; below a third of the maximum they get lost on the intercom. */
fun mediaVolumeLow(volume: MediaVolume?): Boolean = volume != null && volume.max > 0 && volume.current * 3 < volume.max

/** While an ask holds the intercom route, the music stream reports the call device's volume, not the media one. */
fun volumeReadable(phase: Phase): Boolean = phase == Phase.IDLE || phase == Phase.FAILED

/** A null reading (media still on the intercom's call link, which lingers after an ask) keeps the last good one. */
fun nextVolume(previous: MediaVolume?, reading: MediaVolume?): MediaVolume? = reading ?: previous

/** Low, and not dismissed at this very level: a dismissal lasts until the volume changes. */
fun volumeWarning(volume: MediaVolume?, dismissedAt: Int?): Boolean = mediaVolumeLow(volume) && volume?.current != dismissedAt

// SC-12: how a kept recording is described, in Japan time.
private val RECORDED_AT = DateTimeFormatter.ofPattern("M/d HH:mm:ss").withZone(ZoneId.of("Asia/Tokyo"))

fun recordedAtLabel(ms: Long): String = RECORDED_AT.format(Instant.ofEpochMilli(ms))

fun durationLabel(ms: Long): String = String.format(Locale.ROOT, "%.1f秒", ms / 1000.0)

data class Heard(val text: String, val failed: Boolean)

fun transcriptLabel(transcript: String?): Heard = when {
  transcript == null -> Heard("（聞き取られた文はまだありません）", false)
  transcript.isEmpty() -> Heard("聞き取れませんでした", true)
  else -> Heard(transcript, false)
}

/** One line about the microphone: the mode, and the device the system reported. */
fun micLabel(phoneMic: Boolean, device: InputDevice?): String {
  val kind = if (phoneMic) "本体のマイク" else "インカム"
  return if (device != null) "$kind（${device.name}）" else kind
}

data class TrialText(val button: String, val status: String)

fun trialText(state: TrialState): TrialText = when {
  state.phase == TrialPhase.RECORDING -> TrialText("止めて聞く", "録音中です。話してください（インカムのボタンでも止められます）")
  state.phase == TrialPhase.PLAYING -> TrialText("再生を止める", "再生中: ${micLabel(state.phoneMic, state.device)}")
  state.device != null || state.phoneMic -> TrialText("試し録り", "録ったマイク: ${micLabel(state.phoneMic, state.device)}")
  else -> TrialText("試し録り", "質問と同じマイクで録って、すぐに再生します。送りません。")
}
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*LabelsTest' > /tmp/trv2-t8.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t8.log | head`
Expected: `BUILD SUCCESSFUL`。

- [ ] **Step 5: コミットする**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/Labels.kt app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
git commit -m "feat: decide the low media volume warning and word the recording check"
```

---

### Task 9: 画面（SC-12・SC-21・設定の行・警告の帯）

**Files:**
- Create: `Android/app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt`
- Modify: `Android/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt`（`SettingsScreen` と、新しい `VolumeScreen`）
- Modify: `Android/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt`（全体を置き換え）
- Modify: `Android/app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt`（引数と帯）
- Modify: `Android/app/src/main/java/com/touringproject/v2/ui/AppUi.kt`（全体を置き換え）
- Test: `Android/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt`・`.../audio/AudioTest.kt`

**Interfaces:**
- Consumes: Task 7 の `AppGraph.recordingCheck`・`trialState`・`volumeDismissedAt`・`dismissVolumeWarning`、Task 8 の判定と文言
- Produces: `data class RecordingsUi(trial, items, playing, askBusy, message)`・`RecordingsScreen(ui, onTrial, onPlay, onStop, onDeleteAll, modifier)`、`VolumeScreen(settings, onUpdate, modifier)`、`SettingsScreen(..., onVolume, onRecordings, modifier)`、`const val VOLUME_CHECK_MS = 2_000L`・`rememberMediaVolume(readable, read)`・`WarningBand(text, onClick, onClose, modifier)`、`HomeScreen(..., onDismissVolume = {})`、`AskOverlay(..., volumeDismissedAt = null, onDismissVolume = {})`。テストのタグ: `trial`・`trialStatus`・`play-<名前>`・`deleteAll`・`recordingsMessage`・`volume-<dB>`・`banner`・`bandClose`・`overlayVolume`

- [ ] **Step 1: 失敗するテストを書く**

`ScreensTest.kt` の import に足す（並びの位置に）:

```kotlin
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsNotEnabled
import com.touringproject.v2.ask.RecordingMeta
import com.touringproject.v2.audio.InputDevice
import com.touringproject.v2.audio.MediaVolume
import com.touringproject.v2.recordings.TRIAL_IDLE
import com.touringproject.v2.recordings.TrialPhase
import com.touringproject.v2.recordings.TrialState
import org.junit.Assert.assertNull
import org.robolectric.annotation.Config
import java.time.Instant
```

`HomeScreenTest` の `a_new_conversation_is_confirmed_first` の前に足す:

```kotlin
  @Test
  fun the_low_volume_band_closes_with_its_cross_and_leads_nowhere() {
    var opened: Banner? = null
    var dismissed = 0
    rule.setContent { HomeScreen(HomeUi("rider01", Banner.LOW_VOLUME, "新しい会話です"), {}, {}, {}, { opened = it }, {}, onDismissVolume = { dismissed++ }) }
    rule.onNodeWithText(Banner.LOW_VOLUME.text).performClick()
    rule.onNodeWithTag("bandClose").performClick()
    assertNull(opened)
    assertEquals(1, dismissed)
  }

  @Test
  fun the_media_volume_is_read_while_home_is_shown_and_a_withheld_reading_keeps_the_last() {
    // 4b #2, and the carried-over rule: null (media on the call route) must not clear a low reading.
    val readings = ArrayDeque(listOf<MediaVolume?>(MediaVolume(2, 15), null))
    rule.setContent {
      val volume = rememberMediaVolume(readable = true) { readings.removeFirstOrNull() }
      Text(if (volumeWarning(volume, null)) "low" else "ok")
    }
    rule.onNodeWithText("low").assertIsDisplayed()
    rule.mainClock.advanceTimeBy(VOLUME_CHECK_MS * 2)
    rule.onNodeWithText("low").assertIsDisplayed()
  }

  @Test
  fun no_reading_is_taken_while_an_ask_holds_the_route() {
    var reads = 0
    rule.setContent { rememberMediaVolume(readable = false) { reads++; MediaVolume(2, 15) } }
    rule.mainClock.advanceTimeBy(VOLUME_CHECK_MS * 2)
    assertEquals(0, reads)
  }

```

`AskOverlayTest` の `while_speaking_the_answer_is_shown_and_tapping_stops_it` の前に足す:

```kotlin
  @Test
  fun the_low_volume_band_shows_while_recording_until_closed() {
    var dismissed: Int? = null
    val state = FlowState(phase = Phase.RECORDING, mediaVolume = MediaVolume(2, 15))
    rule.setContent { AskOverlay(state, { 0L }, {}, {}, volumeDismissedAt = null, onDismissVolume = { dismissed = it }) }
    rule.onNodeWithText(Banner.LOW_VOLUME.text).assertIsDisplayed()
    rule.onNodeWithTag("bandClose").performClick()
    assertEquals(2, dismissed)
  }

  @Test
  fun a_band_closed_at_this_volume_stays_closed() {
    val state = FlowState(phase = Phase.RECORDING, mediaVolume = MediaVolume(2, 15))
    rule.setContent { AskOverlay(state, { 0L }, {}, {}, volumeDismissedAt = 2) }
    rule.onNodeWithTag("overlayVolume").assertDoesNotExist()
  }

```

`SettingsScreensTest` の `a_saved_key_is_shown_masked` の前に足す:

```kotlin
  @Test
  fun the_settings_list_leads_to_the_volume_and_the_recordings() {
    val opened = mutableListOf<String>()
    rule.setContent { SettingsScreen(Settings("rider01", answerVolumeDb = 3), null, {}, {}, {}, { opened += "volume" }, { opened += "recordings" }) }
    rule.onNodeWithText("+3dB").performClick()
    rule.onNodeWithText("録音の確認").performClick()
    assertEquals(listOf("volume", "recordings"), opened)
  }

  @Test
  fun the_answer_volume_is_chosen_from_three_steps() {
    var updated: Settings? = null
    rule.setContent { VolumeScreen(Settings("rider01"), { updated = it }) }
    rule.onNodeWithTag("volume-3").performClick()
    assertEquals(3, updated!!.answerVolumeDb)
    rule.onNodeWithTag("volume-0").assertIsDisplayed()
    rule.onNodeWithTag("volume-6").assertIsDisplayed()
  }

```

ファイルの終わりに足す:

```kotlin

// Robolectric's default screen is small; the list is checked on one the size of the Pixel 8a.
@RunWith(AndroidJUnit4::class)
@Config(qualifiers = "w412dp-h915dp")
class RecordingsScreenTest {
  @get:Rule val rule = createComposeRule()
  private val intercom = InputDevice(InputDevice.Type.BLUETOOTH, "M1-S PRO")
  private val heard = RecordingMeta("rec-2.pcm", Instant.parse("2026-10-17T01:35:07Z").toEpochMilli(), 2_300, false, intercom, "富士山の高さは")
  private val notHeard = RecordingMeta("rec-1.pcm", Instant.parse("2026-10-17T01:30:00Z").toEpochMilli(), 800, true, null, "")
  private fun ui(trial: TrialState = TRIAL_IDLE, playing: String? = null, askBusy: Boolean = false) =
    RecordingsUi(trial, listOf(heard, notHeard), playing, askBusy, null)

  @Test
  fun kept_recordings_are_listed_with_what_was_heard() {
    // 4b #5
    rule.setContent { RecordingsScreen(ui(), {}, {}, {}, {}) }
    rule.onNodeWithText("10/17 10:35:07　2.3秒").assertIsDisplayed()
    rule.onNodeWithText("インカム（M1-S PRO）").assertIsDisplayed()
    rule.onNodeWithText("富士山の高さは").assertIsDisplayed()
    rule.onNodeWithText("本体のマイク").assertIsDisplayed()
    rule.onNodeWithText("聞き取れませんでした").assertIsDisplayed()
  }

  @Test
  fun nothing_kept_yet() {
    rule.setContent { RecordingsScreen(RecordingsUi(TRIAL_IDLE, emptyList(), null, false, null), {}, {}, {}, {}) }
    rule.onNodeWithText("まだありません").assertIsDisplayed()
  }

  @Test
  fun a_row_plays_its_recording_and_stops_it() {
    val played = mutableListOf<String>()
    var stopped = 0
    var playing by mutableStateOf<String?>(null)
    rule.setContent { RecordingsScreen(ui(playing = playing), {}, { played += it }, { stopped++ }, {}) }
    rule.onNodeWithTag("play-rec-2.pcm").performClick()
    playing = "rec-2.pcm"
    rule.onNodeWithTag("play-rec-1.pcm").assertIsNotEnabled()
    rule.onNodeWithTag("play-rec-2.pcm").performClick()
    assertEquals(listOf("rec-2.pcm"), played)
    assertEquals(1, stopped)
  }

  @Test
  fun delete_all_is_confirmed_first() {
    // 4b #7
    var deleted = 0
    rule.setContent { RecordingsScreen(ui(), {}, {}, {}, { deleted++ }) }
    rule.onNodeWithTag("deleteAll").performClick()
    rule.onNodeWithText("やめる").performClick()
    assertEquals(0, deleted)
    rule.onNodeWithTag("deleteAll").performClick()
    rule.onNodeWithText("消す").performClick()
    assertEquals(1, deleted)
  }

  @Test
  fun the_trial_button_follows_the_trial() {
    var trial by mutableStateOf(TRIAL_IDLE)
    var taps = 0
    rule.setContent { RecordingsScreen(ui(trial = trial), { taps++ }, {}, {}, {}) }
    rule.onNodeWithText("試し録り").performClick()
    trial = TrialState(phase = TrialPhase.RECORDING)
    rule.onNodeWithText("止めて聞く").performClick()
    rule.onNodeWithTag("deleteAll").assertIsNotEnabled()
    trial = TrialState(device = intercom)
    rule.onNodeWithText("録ったマイク: インカム（M1-S PRO）").assertIsDisplayed()
    assertEquals(2, taps)
  }

  @Test
  fun nothing_can_be_started_while_a_question_runs() {
    rule.setContent { RecordingsScreen(ui(askBusy = true), {}, {}, {}, {}) }
    rule.onNodeWithTag("trial").assertIsNotEnabled()
    rule.onNodeWithTag("play-rec-2.pcm").assertIsNotEnabled()
    rule.onNodeWithTag("deleteAll").assertIsNotEnabled()
  }
}
```

`AudioTest.kt` の `AudioRouteTest` の `media_volume_is_withheld_while_the_call_route_is_up` の前に足す:

```kotlin
  @Test
  fun a_low_media_volume_raises_the_warning() {
    // 4b #2: a third of the maximum or more is fine, below it the band shows.
    audioManager.mode = AudioManager.MODE_NORMAL
    val max = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
    audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, max / 3 - 1, 0)
    assertTrue(com.touringproject.v2.ui.volumeWarning(AudioRoute(context).mediaVolume(), null))
    audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, max, 0)
    assertFalse(com.touringproject.v2.ui.volumeWarning(AudioRoute(context).mediaVolume(), null))
  }

```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ScreensTest' --tests '*HomeScreenTest' --tests '*AskOverlayTest' --tests '*SettingsScreensTest' --tests '*RecordingsScreenTest' --tests '*AudioRouteTest' > /tmp/trv2-t9.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t9.log | head`
Expected: コンパイルの失敗（`RecordingsScreen`・`VolumeScreen`・`rememberMediaVolume` などが無い）。

- [ ] **Step 3: 実装する**

`RecordingsScreen.kt` を作る:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.touringproject.v2.ask.RecordingMeta
import com.touringproject.v2.recordings.TrialPhase
import com.touringproject.v2.recordings.TrialState

data class RecordingsUi(
  val trial: TrialState,
  val items: List<RecordingMeta>,
  val playing: String?,
  val askBusy: Boolean,
  val message: String?,
)

private val Blue = Color(0xFF1F4FD1)
private val Red = Color(0xFFD42A2A)
private val Grey = Color(0xFF666666)

// SC-12: the trial recording, and the kept recordings of questions with what was heard (slice 1 spec §5.5).
@Composable
fun RecordingsScreen(
  ui: RecordingsUi,
  onTrial: () -> Unit,
  onPlay: (String) -> Unit,
  onStop: () -> Unit,
  onDeleteAll: () -> Unit,
  modifier: Modifier = Modifier,
) {
  var confirming by remember { mutableStateOf(false) }
  val trialActive = ui.trial.phase != TrialPhase.IDLE
  val text = trialText(ui.trial)
  Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
    Button(
      onClick = onTrial,
      enabled = trialActive || (!ui.askBusy && ui.playing == null),
      modifier = Modifier.fillMaxWidth().testTag("trial"),
      shape = RoundedCornerShape(12.dp),
      colors = ButtonDefaults.buttonColors(containerColor = if (ui.trial.phase == TrialPhase.RECORDING) Red else Blue),
    ) { Text(text.button, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(vertical = 6.dp)) }
    Text(text.status, color = Grey, fontSize = 14.sp, modifier = Modifier.testTag("trialStatus"))
    ui.trial.error?.let { Text(it, color = Red, fontSize = 14.sp) }
    Text("送った録音（直近10件）", fontSize = 16.sp, fontWeight = FontWeight.Bold)
    LazyColumn(Modifier.weight(1f).fillMaxWidth()) {
      if (ui.items.isEmpty()) item { Text("まだありません", color = Grey, fontSize = 14.sp) }
      items(ui.items, key = { it.name }) { item ->
        val heard = transcriptLabel(item.transcript)
        val isPlaying = ui.playing == item.name
        Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
          Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("${recordedAtLabel(item.recordedAt)}　${durationLabel(item.durationMs)}", fontSize = 16.sp)
            Text(micLabel(item.phoneMic, item.device), color = Grey, fontSize = 14.sp)
            Text(heard.text, color = if (heard.failed) Red else Color.Unspecified, fontSize = 15.sp)
          }
          OutlinedButton(
            onClick = { if (isPlaying) onStop() else onPlay(item.name) },
            enabled = isPlaying || !(ui.askBusy || trialActive || ui.playing != null),
            modifier = Modifier.size(56.dp).testTag("play-${item.name}"),
            shape = CircleShape,
          ) { Text(if (isPlaying) "■" else "▶", fontSize = 18.sp) }
        }
        HorizontalDivider()
      }
    }
    ui.message?.let { Text(it, color = Red, fontSize = 14.sp, modifier = Modifier.testTag("recordingsMessage")) }
    OutlinedButton(
      onClick = { confirming = true },
      enabled = !ui.askBusy && !trialActive,
      modifier = Modifier.fillMaxWidth().testTag("deleteAll"),
      shape = RoundedCornerShape(12.dp),
      border = BorderStroke(1.dp, Red),
    ) { Text("録音をすべて消す", color = Red, fontSize = 16.sp, fontWeight = FontWeight.Bold) }
  }
  // DL-01 (recordings)
  if (confirming) {
    AlertDialog(
      onDismissRequest = { confirming = false },
      title = { Text("録音をすべて消しますか？") },
      text = { Text("端末に残した質問の音声を消します。質問と回答の記録は消えません。") },
      confirmButton = { TextButton(onClick = { confirming = false; onDeleteAll() }) { Text("消す") } },
      dismissButton = { TextButton(onClick = { confirming = false }) { Text("やめる") } },
    )
  }
}
```

`SettingsScreens.kt` の import に `import com.touringproject.v2.settings.VOLUME_DB_CHOICES` を足し、`// SC-09 (plan 1: ...)` のコメントから `SettingsScreen` の終わりまでを置き換える:

```kotlin
// SC-09 (slice 1: the settings the slice needs).
@Composable
fun SettingsScreen(
  settings: Settings,
  apiKey: String?,
  onConnection: () -> Unit,
  onUser: () -> Unit,
  onReturnApp: () -> Unit,
  onVolume: () -> Unit,
  onRecordings: () -> Unit,
  modifier: Modifier = Modifier,
) {
  val returnValue = if (!settings.returnEnabled) "戻らない" else settings.returnApp?.label ?: "未設定"
  Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
    SettingsRow("接続の設定", apiKey?.let(::maskKey) ?: "未設定", onConnection)
    SettingsRow("ユーザー名", settings.userName, onUser)
    SettingsRow("応答後に戻るアプリ", returnValue, onReturnApp)
    SettingsRow("回答の音量", "+${settings.answerVolumeDb}dB", onVolume)
    SettingsRow("録音の確認", "", onRecordings)
  }
}

// SC-21: how much the Backend raises the answer audio. Takes effect from the next question.
@Composable
fun VolumeScreen(settings: Settings, onUpdate: (Settings) -> Unit, modifier: Modifier = Modifier) {
  Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
    Text("回答の音声を上げる量", fontSize = 18.sp)
    Text("ナビの案内や音楽より小さく聞こえるときに上げます。次の質問から変わります。", color = Color(0xFF666666), fontSize = 14.sp)
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
      VOLUME_DB_CHOICES.forEach { db ->
        FilterChip(
          selected = settings.answerVolumeDb == db,
          onClick = { onUpdate(settings.copy(answerVolumeDb = db)) },
          label = { Text("+$db", fontSize = 16.sp, fontWeight = FontWeight.Bold) },
          modifier = Modifier.weight(1f).testTag("volume-$db"),
        )
      }
    }
    Text("単位は dB です。+6（最大）で、+0 のおよそ2倍の大きさです。それでも小さいときは、スマホのメディアの音量を上げてください。", color = Color(0xFF666666), fontSize = 14.sp)
  }
}
```

`HomeScreen.kt` を置き換える:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import com.touringproject.v2.audio.MediaVolume
import kotlinx.coroutines.delay

data class HomeUi(val userName: String, val banner: Banner?, val conversation: String)

const val VOLUME_CHECK_MS = 2_000L

/**
 * The media volume, read every 2 s while the caller is on screen and the app is in front (slice 1 spec §5.6).
 * Reading stops while an ask holds the intercom route; a withheld reading keeps the last good one.
 */
@Composable
fun rememberMediaVolume(readable: Boolean, read: () -> MediaVolume?): MediaVolume? {
  var volume by remember { mutableStateOf<MediaVolume?>(null) }
  val currentRead by rememberUpdatedState(read)
  val lifecycle = LocalLifecycleOwner.current.lifecycle
  LaunchedEffect(readable, lifecycle) {
    if (!readable) return@LaunchedEffect
    lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
      while (true) {
        volume = nextVolume(volume, runCatching { currentRead() }.getOrNull())
        delay(VOLUME_CHECK_MS)
      }
    }
  }
  return volume
}

/** The yellow warning band. The low-volume one leads nowhere and has a ✕ instead. */
@Composable
fun WarningBand(text: String, onClick: (() -> Unit)?, onClose: (() -> Unit)?, modifier: Modifier = Modifier) {
  Row(modifier.fillMaxWidth().background(Color(0xFFF5C518), RoundedCornerShape(8.dp)), verticalAlignment = Alignment.CenterVertically) {
    Text(
      text,
      Modifier.weight(1f).then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier).padding(12.dp),
      color = Color.Black,
      fontSize = 16.sp,
    )
    if (onClose != null) {
      Text("✕", Modifier.clickable(onClick = onClose).padding(horizontal = 16.dp, vertical = 12.dp).testTag("bandClose"), color = Color.Black, fontSize = 16.sp)
    }
  }
}

// SC-02 (slice 1 minimum). Glanced at while riding: it never scrolls.
@Composable
fun HomeScreen(
  ui: HomeUi,
  onTapToTalk: () -> Unit,
  onSettings: () -> Unit,
  onUser: () -> Unit,
  onBanner: (Banner) -> Unit,
  onNewConversation: () -> Unit,
  modifier: Modifier = Modifier,
  onDismissVolume: () -> Unit = {},
) {
  var confirming by remember { mutableStateOf(false) }
  Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
      Text(ui.userName, Modifier.clickable(onClick = onUser), fontSize = 22.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
      Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = onTapToTalk, Modifier.testTag("tapToTalk")) { Text("🎤 押して話す") }
        OutlinedButton(onClick = onSettings) { Text("⚙ 設定") }
      }
    }
    ui.banner?.let { banner ->
      val low = banner == Banner.LOW_VOLUME
      WarningBand(banner.text, if (low) null else ({ onBanner(banner) }), if (low) onDismissVolume else null, Modifier.testTag("banner"))
    }
    Text("インカムのボタンで話せます", color = Color(0xFF13804A), fontSize = 16.sp)
    Column(
      Modifier.fillMaxWidth().heightIn(min = 76.dp, max = 140.dp).background(Color(0xFF1F4FD1), RoundedCornerShape(16.dp))
        .clickable { confirming = true }.padding(16.dp).testTag("newConversation"),
      verticalArrangement = Arrangement.Center,
    ) {
      Text(ui.conversation, color = Color.White, fontSize = 16.sp)
      Text("新しい会話を始める", color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold)
    }
  }
  // DL-02
  if (confirming) {
    AlertDialog(
      onDismissRequest = { confirming = false },
      title = { Text("新しい会話を始めますか？") },
      text = { Text("次の質問から、これまでの会話を踏まえずに答えます。") },
      confirmButton = { TextButton(onClick = { confirming = false; onNewConversation() }) { Text("新しい会話にする") } },
      dismissButton = { TextButton(onClick = { confirming = false }) { Text("やめる") } },
    )
  }
}
```

`AskOverlay.kt` の次の行:

```kotlin
fun AskOverlay(state: FlowState, now: () -> Long, onStopRecording: () -> Unit, onCancel: () -> Unit) {
```

を置き換える:

```kotlin
fun AskOverlay(
  state: FlowState,
  now: () -> Long,
  onStopRecording: () -> Unit,
  onCancel: () -> Unit,
  volumeDismissedAt: Int? = null,
  onDismissVolume: (Int) -> Unit = {},
) {
```

同じファイルの、本体のマイクの警告（`if (state.phoneMic && state.phase == Phase.RECORDING) { ... }`）の閉じ括弧の直後、`Column(` `Modifier.weight(1f)...testTag("overlayMain")` の前に足す:

```kotlin
    // The volume was read when the ask started, before the intercom route took over the music stream.
    val volume = state.mediaVolume
    if (state.phase == Phase.RECORDING && volume != null && volumeWarning(volume, volumeDismissedAt)) {
      WarningBand(Banner.LOW_VOLUME.text, null, { onDismissVolume(volume.current) }, Modifier.testTag("overlayVolume"))
    }
```

`AppUi.kt` を置き換える:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation3.runtime.NavKey
import androidx.navigation3.runtime.entryProvider
import androidx.navigation3.runtime.rememberNavBackStack
import androidx.navigation3.ui.NavDisplay
import com.touringproject.v2.AppGraph
import com.touringproject.v2.api.ApiClient
import com.touringproject.v2.ask.isBusy
import com.touringproject.v2.settings.LaunchableApp
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable data object HomeKey : NavKey
@Serializable data object SettingsKey : NavKey
@Serializable data object ConnectionKey : NavKey
@Serializable data object UserKey : NavKey
@Serializable data object ReturnAppKey : NavKey
@Serializable data object VolumeKey : NavKey
@Serializable data object RecordingsKey : NavKey

@Composable
fun AppUi(graph: AppGraph) {
  val ready by graph.isReady.collectAsStateWithLifecycle()
  val state by graph.state.collectAsStateWithLifecycle()
  val settings by graph.settings.settings.collectAsStateWithLifecycle()
  val apiKey by graph.apiKeys.apiKey.collectAsStateWithLifecycle()
  val volumeDismissedAt by graph.volumeDismissedAt.collectAsStateWithLifecycle()
  val scope = rememberCoroutineScope()
  val backStack = rememberNavBackStack(HomeKey)
  val current = settings
  // Re-read on every phase change, so the label updates once an ask has renewed the conversation.
  val expiresAt = remember(state) { graph.conversation.expiresAt(System.currentTimeMillis()) }
  Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
    Box(Modifier.fillMaxSize()) {
      if (!ready || current == null) {
        Text("準備中…", Modifier.safeDrawingPadding())
      } else {
        NavDisplay(
          backStack = backStack,
          onBack = { backStack.removeLastOrNull() },
          entryProvider = entryProvider {
            entry<HomeKey> {
              val volume = rememberMediaVolume(volumeReadable(state.phase)) { graph.audioRoute.mediaVolume() }
              val ui = HomeUi(
                userName = current.userName,
                banner = homeBanner(
                  hasKey = apiKey != null,
                  returnAppMissing = current.returnEnabled && current.returnApp == null,
                  volumeLow = volumeWarning(volume, volumeDismissedAt),
                ),
                conversation = conversationLabel(expiresAt, System.currentTimeMillis()),
              )
              HomeScreen(
                ui = ui,
                onTapToTalk = graph.controller::tapToTalk,
                onSettings = { backStack.add(SettingsKey) },
                onUser = { backStack.add(UserKey) },
                onBanner = { backStack.add(if (it == Banner.NO_KEY) ConnectionKey else ReturnAppKey) },
                onNewConversation = graph.controller::resetConversation,
                modifier = Modifier.safeDrawingPadding(),
                onDismissVolume = { volume?.let { graph.dismissVolumeWarning(it.current) } },
              )
            }
            entry<SettingsKey> {
              SettingsScreen(
                current, apiKey,
                onConnection = { backStack.add(ConnectionKey) },
                onUser = { backStack.add(UserKey) },
                onReturnApp = { backStack.add(ReturnAppKey) },
                onVolume = { backStack.add(VolumeKey) },
                onRecordings = { backStack.add(RecordingsKey) },
                modifier = Modifier.safeDrawingPadding(),
              )
            }
            entry<VolumeKey> {
              VolumeScreen(current, { next -> scope.launch { graph.settings.update(next) } }, Modifier.safeDrawingPadding())
            }
            entry<RecordingsKey> {
              val check = graph.recordingCheck
              val trial by graph.trialState.collectAsStateWithLifecycle()
              val items by check.items.collectAsStateWithLifecycle()
              val playing by check.playing.collectAsStateWithLifecycle()
              val message by check.message.collectAsStateWithLifecycle()
              // Leaving SC-12 drops the trial and its playback; an answer being read out goes on.
              DisposableEffect(Unit) { onDispose { check.leave() } }
              RecordingsScreen(
                RecordingsUi(trial, items, playing, isBusy(state), message),
                onTrial = check::toggleTrial,
                onPlay = check::play,
                onStop = check::stopPlaying,
                onDeleteAll = check::deleteAll,
                modifier = Modifier.safeDrawingPadding(),
              )
            }
            entry<ConnectionKey> {
              ConnectionScreen(
                apiKey = apiKey,
                urlMissing = graph.apiBaseUrl.isEmpty(),
                check = { key -> ApiClient(graph.apiBaseUrl, key, current.userName).checkKey() },
                save = { graph.apiKeys.save(it) },
                modifier = Modifier.safeDrawingPadding(),
              )
            }
            entry<UserKey> {
              UserScreen(current.userName, { name -> scope.launch { graph.settings.update(current.copy(userName = name)) } }, Modifier.safeDrawingPadding())
            }
            entry<ReturnAppKey> {
              var apps by remember { mutableStateOf<List<LaunchableApp>>(emptyList()) }
              LaunchedEffect(Unit) { apps = graph.launcher.launchableApps() }
              ReturnAppScreen(current, apps, { next -> scope.launch { graph.settings.update(next) } }, Modifier.safeDrawingPadding())
            }
          },
        )
        Column(Modifier.fillMaxSize()) {
          AskOverlay(
            state, System::currentTimeMillis, graph.controller::stopRecording, graph.controller::cancel,
            volumeDismissedAt = volumeDismissedAt, onDismissVolume = graph::dismissVolumeWarning,
          )
        }
      }
    }
  }
}
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest > /tmp/trv2-t9.log 2>&1; grep -E "FAILED|BUILD|^e: " /tmp/trv2-t9.log | head`
Expected: `BUILD SUCCESSFUL`（JVM のテスト全体。使い捨てのフォルダでは179件）。

- [ ] **Step 5: コミットする**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt \
  app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt app/src/test/java/com/touringproject/v2/audio/AudioTest.kt
git commit -m "feat: add the recording check, the answer volume and the low volume band"
```

---

### Task 10: 走行用のビルドと README

**Files:**
- Modify: `Android/app/build.gradle.kts`（`release` と依存）・`Android/gradle/libs.versions.toml`
- Create: `Android/scripts/check-release-permissions.sh`
- Modify: `Android/README.md`

**Interfaces:**
- Consumes: Task 1〜9 のすべて
- Produces: `./gradlew assembleRelease` が開発用の鍵で署名した APK を出す。`scripts/check-release-permissions.sh [APK]` が、許した一覧の外の権限で失敗する

- [ ] **Step 1: release の署名と Fragment を足す**

`build.gradle.kts` の `release { ... }` を置き換える:

```kotlin
    release {
      isMinifyEnabled = false
      // The riding build only goes onto our own phones, so it is signed with the debug key: installing it over the
      // debug build keeps the settings, the connection key and the recordings (migration plan 2).
      signingConfig = signingConfigs.getByName("debug")
      proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
```

`implementation(libs.play.services.location)` の次に足す:

```kotlin
  // Play services bring Fragment 1.1.0, which the release lint rejects next to the Activity Result API; the app uses no fragments.
  implementation(libs.androidx.fragment)
```

`libs.versions.toml` の `[versions]` の `androidxDatastore` の次に `androidxFragment = "1.8.9"`、`[libraries]` の `androidx-datastore-preferences` の次に足す:

```toml
androidx-fragment = { module = "androidx.fragment:fragment", version.ref = "androidxFragment" }
```

（Fragment が無いと `lintVitalRelease` が `InvalidFragmentVersionForActivityResult` で止まる。使い捨てのフォルダで確かめた。）

- [ ] **Step 2: 権限を確かめる script を作る**

`scripts/check-release-permissions.sh` を作り、`chmod +x` する:

```bash
#!/usr/bin/env bash
# Fails when the release APK asks for a permission that is not on the list below (migration spec §8.1).
# The last three come from libraries (Media3, Play services, AndroidX core) and are not dangerous permissions.
set -euo pipefail

APK="${1:-app/build/outputs/apk/release/app-release.apk}"
SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
AAPT2="$SDK/build-tools/$(ls "$SDK/build-tools" | sort -V | tail -1)/aapt2"

expected="android.permission.ACCESS_COARSE_LOCATION
android.permission.ACCESS_FINE_LOCATION
android.permission.BLUETOOTH
android.permission.BLUETOOTH_CONNECT
android.permission.FOREGROUND_SERVICE
android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK
android.permission.FOREGROUND_SERVICE_MICROPHONE
android.permission.INTERNET
android.permission.MODIFY_AUDIO_SETTINGS
android.permission.POST_NOTIFICATIONS
android.permission.RECORD_AUDIO
android.permission.ACCESS_NETWORK_STATE
android.permission.WAKE_LOCK
com.touringproject.v2.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"

actual=$("$AAPT2" dump permissions "$APK" | sed -n "s/^uses-permission: name='\([^']*\)'.*/\1/p" | sort)
extra=$(comm -13 <(echo "$expected" | sort) <(echo "$actual"))
if [ -n "$extra" ]; then
  echo "unexpected permissions in $APK:" >&2
  echo "$extra" >&2
  exit 1
fi
echo "release permissions OK ($(echo "$actual" | wc -l | tr -d ' '))"
```

- [ ] **Step 3: 全体を通し、release を確かめる**

Run（バックグラウンドで。1〜2分）:

```bash
cd $AND && ./gradlew testDebugUnitTest assembleDebug assembleRelease > /tmp/trv2-t10.log 2>&1; echo exit=$? >> /tmp/trv2-t10.log
grep -E "^exit=|BUILD|FAILED|^e: " /tmp/trv2-t10.log
scripts/check-release-permissions.sh
$SDK/build-tools/$(ls $SDK/build-tools | sort -V | tail -1)/apksigner verify --print-certs app/build/outputs/apk/release/app-release.apk | head -1
```

Expected: `BUILD SUCCESSFUL`・`exit=0`。`release permissions OK (14)`。署名は `CN=Android Debug`（debug の APK と同じ証明書）。React Native 版にあった `SYSTEM_ALERT_WINDOW`・`READ/WRITE_EXTERNAL_STORAGE`・`VIBRATE` は入らない（持ち越しの「release の要らない権限」はネイティブ版で解消）。

エミュレーターの通し（plan 1 の2件）も回す:

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
export ANDROID_SERIAL=emulator-5554   # 実機が繋がっていても、エミュレーターだけを指す
./gradlew connectedDebugAndroidTest > /tmp/trv2-t10e.log 2>&1; grep -E "BUILD|FAILED|Finished" /tmp/trv2-t10e.log
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: `Finished 2 tests on medium_phone(AVD) - 16`・`BUILD SUCCESSFUL`。

- [ ] **Step 4: README を直す**

`README.md` の「構成」の表の `.../handsfree/` の行を替え、`.../settings/` の行の前に `recordings` の行を足す:

```markdown
| `.../handsfree/` | 押下の重複・古い合図の除外・押下の行き先（試し録り中は試し録りへ） |
| `.../recordings/` | 録音の置き場（直近10件と付随情報）・試し録りの司令塔・録音の確認（SC-12）の状態 |
```

「大事な決まり」の最後に足す:

```markdown
- 録音の確認（SC-12）は、質問とは別の経路の切り替え・録音・再生を持つ。画面を離れても、読み上げ中の回答は止めない。
- 録音は `filesDir/recordings/` に `rec-<時刻>.pcm` と `rec-<時刻>.json` の組で直近10件を残す。片方しか無い組と読めない JSON は、次に残すときに消す。
```

「テスト」の節の Robolectric の行の次に足す:

```markdown
`runTest` の `backgroundScope` で動かした処理は `advanceUntilIdle` で進まない。アプリの scope の代わりには `CoroutineScope(SupervisorJob() + StandardTestDispatcher(testScheduler))` を使う（`RecordingCheckTest`）。実機が USB で繋がったままエミュレーターのテストを回すときは、`export ANDROID_SERIAL=emulator-5554` でエミュレーターだけを指す。
```

「実機で動かす」の節の後に足す:

````markdown
## 走行用のビルド

開発用のビルドも USB を外して動くが、走行では release を入れる（最適化され、デバッグの印が付かない）。署名は開発用の鍵と同じなので、上書きしても設定・接続キー・録音は残る。

```sh
./gradlew assembleRelease
scripts/check-release-permissions.sh            # 許した一覧の外の権限があれば失敗する
adb install -r app/build/outputs/apk/release/app-release.apk
```

端末に2つのユーザーがあるときは、`adb install --user 0 -r ...` のようにユーザーを指す。
````

ログの行を替える:

```markdown
ログは `adb logcat -s trv2.ask trv2.route trv2.ride trv2.recordings`。
```

- [ ] **Step 5: コミットする**

```bash
cd $AND && git add app/build.gradle.kts gradle/libs.versions.toml scripts/check-release-permissions.sh README.md
git commit -m "build: sign the riding build with the debug key and check its permissions"
```

---

### Task 11: 実機の確認（利用者）

**Files:** なし（結果は ledger と、Task 12 の PROJECT.md に書く）

spec §8.2 の残り。Pixel 8a で、利用者に1つずつ頼み、結果を ✓／✗ で受け取る。✗ が出たら `superpowers:systematic-debugging` で直し、直したら該当の項目をもう一度頼む。

- [ ] **Step 1: 走行用のビルドを入れる**

利用者に USB を繋いでもらい、`cd $AND && adb install -r app/build/outputs/apk/release/app-release.apk`（2つのユーザーに入っているなら `--user 0` と `--user 10` の両方）。debug と同じ鍵なので、外さずに上書きでき、接続キーと設定が残る。残っていなければ、接続キーを入れ直す（README の手順。キーをチャットに出さない）。

- [ ] **Step 2: 利用者に確かめてもらう（1つずつ）**

| # | 操作 | 期待 |
|---|---|---|
| 1 | 設定 → 回答の音量で +0・+3・+6 を順に選び、それぞれインカムのボタンで同じ質問をする | 差が分かる。+6 がナビの案内と比べて聞き劣りしない |
| 2 | 設定 → 録音の確認 → 試し録り。話して「止めて聞く」（またはインカムのボタン） | 話した声がインカムから聞こえる。「録ったマイク: インカム（…）」と出る。「再生を止める」で途中で止まる |
| 3 | 同じ画面で、送った録音の ▶ を押す | 直前の質問の声が聞こえ、聞き取られた文が並んでいる |
| 4 | スマホのメディアの音量を最大にしてから、インカムで質問し、回答の直後にアプリのホームを開く | メディアの音量の警告の帯が誤って出ない（その後、音量を1/3未満に下げると2秒ほどで帯が出る） |
| 5 | USB を外し、ナビを出した状態でアプリを閉じ、インカムのボタンで質問する（plan 1 の Task 12 と同じ一巡） | 赤い画面と開始の合図・インカムのマイクで録れる → もう一度押すと送った合図とナビへ戻る → 回答がインカムから聞こえる（画面を消しても） |

- [ ] **Step 3: 結果を ledger に書く**

項目ごとに ✓／✗ と、利用者が言ったことを1行で書く。#1 で +6 の差が聞き取れなくても、+6dB が上限であることは持ち越しの前提どおり（spec §6.3）。差が分からないと言われたら、そのまま記録して利用者に扱いを聞く（音量を上げる手立ては持ち越しの経緯で試し済み）。

---

### Task 12: 親の文書・submodule `App/` の整理・PROJECT.md

**Files:**
- Modify（親）: `docs/05_technical_policies.md`・`docs/06_units_definition.md`・`docs/07_units_contracts.md`・`docs/README.md`・`README.md`・`PROJECT.md`
- Remove（親）: submodule `App/`（`.gitmodules` の項も）
- Modify（各ユニット）: `docs-parent/`（`scripts/sync-docs.sh` で写す）

- [ ] **Step 1: 文書のユニットの名前を App から Android に替える**

```bash
cd $ROOT/docs
perl -pi -e 's/\bApp\b/Android/g' 05_technical_policies.md 06_units_definition.md 07_units_contracts.md README.md
perl -pi -e 's/Android\["Android<br\/>Android"\]/Android["Android"]/' 05_technical_policies.md
perl -pi -e 's/\| Android \| Android アプリ（React Native／Expo） \|/| Android | Android アプリ（Kotlin・Jetpack Compose） |/' 06_units_definition.md
perl -pi -e 's/\| `TouringProjectV2_App` \| Android \|/| `TouringProjectV2_Android` | Android |/' 07_units_contracts.md
grep -n "App" 05_technical_policies.md 06_units_definition.md 07_units_contracts.md README.md
```

Expected: 最後の `grep` が何も出さない（使い捨てのフォルダで確かめた。`TouringProjectV2_App` は `\b` に当たらないので、最後の置き換えで直す）。

`07_units_contracts.md` の UC-9 の次の行:

```markdown
- Android は、版のタグを付けると自動でビルドされ、知人向けのテスト配信に上がる。
```

を置き換える:

```markdown
- Android は、版のタグを付けると自動でビルドされ、知人向けのテスト配信に上がる（まだ作っていない。それまでは、開発者の Mac で走行用のビルドを作って端末に入れる。手順は Android の README）。
```

- [ ] **Step 2: 親の README を直す**

ユニットの表の `App/` の行を消し、`Android/` の行を替える:

```markdown
| `Android/` | Android アプリ（Kotlin・Jetpack Compose。[adr/0005](adr/0005-native-android-app.md)） | `TouringProjectV2_Android` |
```

`git submodule update --init App Android Backend Agent` の行から `App ` を、`scripts/sync-docs.sh App Android Backend Agent CICD` の行から `App ` を消す。

- [ ] **Step 3: submodule `App/` を外す（利用者に確認してから）**

利用者に「親から submodule `App/` を外します（`git rm App`。手元の `App/` の作業ツリーも消えます。GitHub の `TouringProjectV2_App` はそのまま残り、アーカイブは Task 13）」と確認を取る。外す前に、`App/` に push していないコミットと変更が無いことを確かめる:

```bash
cd $ROOT/App && git status --short && git fetch -q && git log origin/main..HEAD --oneline
```

Expected: どちらも何も出さない（何か出たら止まって利用者に聞く）。

```bash
cd $ROOT && git rm App
git status --short   # .gitmodules と App が変更として出る
```

- [ ] **Step 4: 文書を写す**

```bash
cd $ROOT && scripts/sync-docs.sh Android Backend Agent CICD
```

Android はこの計画のブランチに、Backend・Agent・CICD は main に直接コミットする（PROJECT.md の「前提」）。

```bash
cd $AND && git add docs-parent && git commit -m "docs: sync parent docs"
for u in Backend Agent CICD; do
  (cd $ROOT/$u && git switch main && git add docs-parent && git commit -m "docs: sync parent docs")
done
```

- [ ] **Step 5: PROJECT.md を更新し、親でコミットする**

最終レビュー（finishing の前）の区切りの決まり（CLAUDE.md）に従って、ここで PROJECT.md を直す。Task 13 と最終レビューの結果を待つものは、その時点でもう一度直す。

- 「サブプロジェクト」の 2 の見出しを「（plan 1・plan 2 実装済み。確認待ち: マージと移行の締め）」に、plan 表の 2 の行を「実装済み（確認待ち: マージ・Task 13 の issue とアーカイブ）」にする。リンクを `docs/plans/2026-10-17-native-migration-plan2-finish.md` に。
- スライス1の計画の表の「完了の判定（実際の走行）」は「未実施」のまま。「次にやること」に、スライス1の完了の判定を走行用のビルドで行うこと（利用者の作業）を残す。
- 「持ち越し」から、ネイティブ版で解消した3つ（+6dB は spec に記録済みなので消してよい・SCO 中の `null` は `Labels.kt` の `nextVolume` と README に移った・release の要らない権限は解消）を消し、この計画で分かったこと（`backgroundScope` と `advanceUntilIdle`・`ANDROID_SERIAL`・Robolectric の作り物の AudioTrack は書いた分を即座に再生済みにする・release の lint に Fragment が要る）を、Android の README に移したものは1行の参照にする。
- 「サブプロジェクト」の分け方の段落の「4ユニット（App・Backend・Agent・CICD）」を「4ユニット（Android・Backend・Agent・CICD）」に、「前提」の後回しの指摘の行を「各ユニットのリポジトリ（Android・Backend・Agent・CICD）の GitHub issue」にする。

```bash
cd $ROOT && git add docs/05_technical_policies.md docs/06_units_definition.md docs/07_units_contracts.md docs/README.md README.md PROJECT.md .gitmodules
git commit -m "docs: rename the app unit to Android and drop the React Native submodule"
git add Android Backend Agent CICD && git commit -m "chore: bump units for synced parent docs"
```

（`git rm App` は Step 3 でステージ済みなので、最初のコミットに入る。）

---

### Task 13: 移行の締め（利用者の確認を取って）

**Files:** なし（GitHub の操作）

マージの後でも前でもよいが、どちらも外に見える操作なので、一つずつ利用者に確認を取る。

- [ ] **Step 1: React Native 版の issue #10〜#13 を閉じる**

利用者に確認してから:

```bash
cd $ROOT
for n in 10 11 12 13; do
  gh issue close $n --repo h-akira/TouringProjectV2_App --reason completed \
    --comment "ネイティブ版（TouringProjectV2_Android）への移行で解消。同じことが起きない作りにし、テストで確かめた（移行 plan 2: docs/plans/2026-10-17-native-migration-plan2-finish.md の Task 5〜7）。"
done
```

- [ ] **Step 2: `TouringProjectV2_App` をアーカイブする**

利用者に確認してから（アーカイブすると push も issue の操作もできなくなるので、Step 1 と、App の main への push が残っていないことを先に済ませる）:

```bash
gh repo archive h-akira/TouringProjectV2_App --yes
```

- [ ] **Step 3: PROJECT.md の plan 表を直す**

Step 1・2 が済んだら、移行の plan 2 の行の確認待ちから「issue とアーカイブ」を消す（マージも済んでいれば「✅ 完了」、サブプロジェクトの見出しも完了に）。親でコミットする（`docs: record the native migration as done`）。
