# スライス6 plan 4: 音声の経路を札で借りる（R10-01・R10-06 と R1-01・R1-02・R1-03）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** アプリに1つの音声の経路を、質問・試し録り・声の入力が1度に1人ずつ札で借りる形にし、取り消した処理の後始末が次の処理の経路と位置を壊さないようにする。あわせて、端末の音声合成が終わりを知らせなくても質問が終わるようにする。

**Architecture:** (1) 位置の監視 `Positions` に札（`begin(): Int` / `end(token)`）を付け、古い呼び出しの `end` が新しい監視を止めないようにする。(2) `AudioRoute` の経路の準備（`startVoiceRecognition`・`acquireSco`）を取り消せるようにし、取り消されたら呼び出しが返る前にその場で元に戻す。(3) 新しい `RouteLeases` が `RouteDriver`（今の `AudioRouteControl`）を1つのロックで包み、`lease(source)` が前の持ち主の `release()` を待ってから経路を張って `RouteLease` を返す。質問・試し録り・声の入力はこの札で経路を借りる。質問と試し録りは `LeaseRequest` で、経路が張れるまでの待ちを大きなボタンの取り消しから呼び止める。(4) `AskController` の読み上げ（`speech.say`）に文字数から見積もった上限を付ける。(5) `AskController` の入口の確かめ・送信の組み立て・後始末の重複を1か所にまとめる。

**Tech Stack:** Kotlin・Coroutines（`Mutex`・`withTimeout`・`coroutineScope`/`async`）・JUnit4・kotlinx-coroutines-test・Robolectric 4.16（`AudioRoute` の取り消しのテスト）。Android の `./gradlew`。

**Spec:** [docs/specs/2026-10-29-slice6-design.md](../specs/2026-10-29-slice6-design.md)（§3 の plan 4）。指摘の出どころは [全体レビュー](../final-review/2026-10-28/README.md) の android.md（R1-01・R1-02・R1-03）と structure.md（R10-01・R10-06）。

## Global Constraints

- 利用者に見える文章（ツール実行の合間の報告を含む）と文書は日本語。コード・コード中のコメント・コミットメッセージは英語。コミットメッセージは Conventional Commits。
- インデントは2スペース。型注釈を付ける。秘密情報をハードコードしない。
- `git add` はファイルを個別に指定する（`git add .`・`-A` は禁止）。コミットは許可を求めずに行ってよい。push・merge・デプロイは利用者が明示したときだけ。push の前に `pre-push-secret-scan` を回して報告する。
- Android のブランチは `slice6-plan4`、親のブランチも `slice6-plan4`。コマンドは必ず絶対パスへ `cd` してから実行する。
- JVM のテストは `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`。基準値は main で 721 件（このplanの完了時は 734 件）。クラスを絞った実行（`--tests`）は、Robolectric のテストが `FileSystemAlreadyExistsException`・`UnsatisfiedLinkError` で落ちることがある（絞った実行の環境の癖で、コードの不具合ではない）。タスクの区切りの確かめは `clean` から全体で行う。
- 振る舞いを変えるのは、取り消し・背面・言い直しの後始末と、読み上げの上限だけ。画面・API・Room のスキーマ・Backend・Agent は変えない。Room の版は上げない。
- Android の版は 0.14.2（`versionCode` 17）に上げる。
- 実機: 区切りで `app-debug.apk` を実機に入れて確かめる（Task 7）。実機の確かめは利用者が行う。

## Rulings（brainstorming で決めたこと）

- 範囲は spec §3 の plan 4 のとおり R10-01 → R10-06、関連は R1-01・R1-02・R1-03。R1-02 を入れる（2026-10-30、利用者が決めた）。
- R10-06 は報告の `sealed interface AskInput` の分け方でなく、重複している3か所（入口の確かめ・送信の本文の組み立て・後始末）を1か所にまとめる形にする。声の質問の「録る → 通信できなければ質問できなかった地点」と、文字の質問の「最後の位置 → 通信できなければシートに出す」は中身が違うので、2つの短い関数のまま残す。完了の判定は報告のとおり「入口の確かめを1か所に足すと両方に効く」。
- `RouteBusyException`（前の持ち主が8秒たっても返さない）は、経路を張れなかった失敗として扱い、本体のマイクで録る。経路を持たないので返すものも無い。インカムが死にっぱなしになるより、本体のマイクに落ちるほうを選ぶ。
- 位置の札・経路の札の導入で、`PressRouter` の `trialBusy`・`voiceBusy`、`TrialController.busy` は不要になるので消す。`VoiceInput.busy` は押下に失敗の合図を鳴らすために残す。
- インカムの音声認識の経路（`startVoiceRecognition`）の取り消しは、Robolectric で headset の作り物を用意できないので、自動テストは画面のボタンの経路（`acquireSco`）だけ。音声認識の経路は実機で確かめる（Task 7）。

## Review Focus

- 録音中・経路の準備中に取り消し、すぐ押し直した質問が、前の質問の後始末に邪魔されない（経路・位置・録音）。Task 3 の `an_ask_started_after_a_cancel_during_route_setup_is_recorded_with_its_position`・`an_ask_waits_for_the_one_before_to_let_go_of_the_route`。
- 前の持ち主が経路を返さないままでも、次の呼び出しは永久に待たない（8秒で本体のマイクに落ちる）。Task 3 の `a_holder_that_never_lets_go_is_given_up_on_after_the_wait`。
- SC-19 を離れた直後に押した質問・声の入力が、離れた声の入力の準備に邪魔されない。Task 3 の `leaving_during_the_route_setup_lets_the_next_press_start_at_once`。
- 端末の音声合成が終わりを知らせなくても、質問が読み上げ中のまま止まらず、長い回答が途中で切れない（上限は文字数×300ms＋5秒）。Task 4。
- インカムの音声認識の経路の準備中に取り消しても、通話の経路（`MODE_IN_COMMUNICATION`）が残らない。自動テストは無く、実機で確かめる（Task 7）。

---

## ファイルの構成

| ファイル（`Android/app/src/main/java/com/touringproject/v2/` からの相対） | 変更 |
|---|---|
| `location/Positions.kt`・`location/PositionTracker.kt` | `begin(): Int`・`end(token)` |
| `audio/AudioRoute.kt` | 経路の準備を取り消すと、呼び出しが返る前に元に戻す |
| `audio/AudioPorts.kt` | `RouteDriver`（今の `RouteControl`）・`RouteLease`・新しい `RouteControl` |
| `audio/RouteLeases.kt`（新規） | `RouteLeases`・`LeaseRequest`・`RouteBusyException`・`LEASE_WAIT_MS` |
| `audio/AudioRouteControl.kt` | `RouteDriver` の実装に名前の型だけ変える |
| `audio/TtsSpeech.kt` | 待ちが切られたら `pending` から消す |
| `ask/AskController.kt` | 位置の札・経路の札・読み上げの上限・入口/本文/後始末の共有 |
| `recordings/Trial.kt`・`voice/VoiceInput.kt` | 経路の札 |
| `handsfree/PressRouter.kt`・`AppGraph.kt` | `trialBusy`・`voiceBusy` を消す・`RouteLeases` を1つ作って渡す |
| テスト | `PositionTrackerTest`・`AudioTest`・`RouteLeasesTest`（新規）・`AskControllerTest`・`TrialTest`・`VoiceInputTest`・`RecordingCheckTest`・`NoteRoutesTest`・`PressRouterTest` |
| 文書 | `Android/README.md`・`docs/08a_android-design.md`（plan のコミットで書いた）・`PROJECT.md`・`Android/app/build.gradle.kts`（版） |

---

### Task 0: 指摘を現在のコードで確かめる

**Files:**（捨てる作業場。リポジトリには何も残さない）

spec §4: 不具合は再現テストを先に書き、失敗すれば本物。

- [ ] **Step 1: 捨てる worktree を作る**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git worktree add /private/tmp/claude-501/p4-red -b scratch-p4-red main
cp local.properties /private/tmp/claude-501/p4-red/
```

- [ ] **Step 2: R1-01・R1-02 の再現テストを足す**

`/private/tmp/claude-501/p4-red/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt` を次のように変える（今の API のままのテスト）。`Harness` の末尾の引数に足す:

```kotlin
  /** A real tracker, to see what the cleanup of one ask does to the next. */
  val positions: Positions? = null,
```

`location = object : Positions {` を `location = positions ?: object : Positions {` に変える。`class AskControllerTest {` の直後に足す:

```kotlin
  // Android R1-01: the cleanup of a cancelled ask must not take the next ask's position.
  @Test
  fun a_cancelled_asks_late_cleanup_leaves_the_next_asks_position() = runTest {
    val source = object : com.touringproject.v2.location.PositionSource {
      override fun now() = 100_000L
      override fun elapsed() = 50_000L
      override fun lastKnown(onFix: (Fix) -> Unit) = onFix(HERE)
      override fun watch(onFix: (Fix) -> Unit) = com.touringproject.v2.location.Subscription {}
    }
    val gate = CompletableDeferred<Boolean>()
    var starts = 0
    val h = Harness(this, stopAfterMs = 1_000, routeStart = { if (++starts == 1) gate.await() else true }, positions = com.touringproject.v2.location.PositionTracker(source))
    val first = launch { h.controller.run(Source.HANDSFREE) }
    h.until { starts == 1 }
    h.controller.cancel()
    val second = launch { h.controller.run(Source.HANDSFREE) }
    h.until { starts == 2 }
    gate.complete(true)
    second.join()
    first.join()
    assertEquals(Point(HERE.latitude, HERE.longitude), h.bodies.single().location)
  }

  // Android R1-02: the device voice may never say it is done; the ask must not stay SPEAKING for good.
  @Test
  fun a_speech_that_never_returns_is_cut_off_and_the_ask_ends() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, play = { throw IllegalStateException("cannot play") }, sayGate = CompletableDeferred())
    val running = launch { h.controller.run(Source.SCREEN) }
    h.until { "say:愛鷹山です。" in h.log }
    testScheduler.advanceTimeBy(30_000)
    testScheduler.runCurrent()
    assertEquals(Phase.IDLE, h.phase)
    assertTrue("say:stop" in h.log)
    running.join()
  }
```

- [ ] **Step 3: 実行して失敗を確かめる**

```bash
cd /private/tmp/claude-501/p4-red && ./gradlew clean testDebugUnitTest --tests '*AskControllerTest'
```
Expected: 2件が失敗する。`a_cancelled_asks_late_cleanup_leaves_the_next_asks_position` は `expected: Point(...) but was: null`（次の質問が位置なしで送られる）、`a_speech_that_never_returns_is_cut_off_and_the_ask_ends` は `expected: IDLE but was: SPEAKING`。

- [ ] **Step 4: R1-03 の再現テストを足す**

`/private/tmp/claude-501/p4-red/app/src/test/java/com/touringproject/v2/audio/AudioTest.kt` に、Task 2 の Step 1 のテスト（`PendingScoAudioManager` と `AudioRouteCancelTest`、import を含む）をそのまま足し、実行する:

```bash
cd /private/tmp/claude-501/p4-red && ./gradlew testDebugUnitTest --rerun --tests '*AudioRouteCancelTest'
```
Expected: `expected:<1> but was:<0>`（取り消しても通話の経路が戻らない。`AudioTest.kt` の `assertEquals(1, shadow.cleared)` の行）。

- [ ] **Step 5: 捨てて、結果を ledger に書く**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git worktree remove --force /private/tmp/claude-501/p4-red && git branch -D scratch-p4-red
```
3つとも失敗した（指摘は本物）ことを ledger に書く。失敗しなかったものがあれば、その指摘は直さず、止まって聞く。

---

### Task 1: 位置の監視に札を付ける（R1-01 の位置の部分）

**Files:**
- Modify: `Android/app/src/main/java/com/touringproject/v2/location/Positions.kt`
- Modify: `Android/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt`
- Modify: `Android/app/src/main/java/com/touringproject/v2/ask/AskController.kt`
- Test: `Android/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt`
- Test: `Android/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt`

**Interfaces:**
- Produces: `Positions.begin(): Int`（札）・`Positions.end(token: Int): Fix?`（その札のときだけ効く。古い札は何も変えず null）。

- [ ] **Step 1: 失敗するテストを書く**

`PositionTrackerTest.kt` の `end_removes_the_watch` を次の2つに置き換える:

```kotlin
  @Test
  fun end_removes_the_watch() {
    val source = FakeSource()
    val tracker = PositionTracker(source)
    val token = tracker.begin()
    tracker.end(token)
    assertEquals(1, source.removed)
  }

  // Android R1-01: the cleanup of an ask that was cancelled can run after the next ask has begun.
  @Test
  fun an_end_with_an_earlier_token_changes_nothing_of_the_newer_watch() {
    val source = FakeSource()
    val tracker = PositionTracker(source)
    val older = tracker.begin()
    val newer = tracker.begin()
    source.onFix!!(fix(99_500))
    assertNull(tracker.end(older))
    assertEquals(1, source.removed)
    assertEquals(fix(99_500), tracker.end(newer))
    assertEquals(2, source.removed)
  }
```

同じファイルの残りのテストは、`begin()` の結果を `end` に渡す形に直す:

`fixes_from_an_earlier_begin_are_not_mixed_in`:
```kotlin
    tracker.begin()
    val oldCallback = source.onFix!!
    val token = tracker.begin()
    source.onFix!!(fix(99_500))
    oldCallback(fix(99_900))
    assertEquals(fix(99_500), tracker.end(token))
```
`a_last_known_point_that_arrives_after_end_is_ignored`:
```kotlin
    tracker.end(tracker.begin())
    source.lateLastKnown!!(fix(99_000))
    assertNull(tracker.end(tracker.begin()))
```
`a_stale_last_known_point_is_not_the_current_position`: `assertNull(tracker.end(tracker.begin()))`。
`the_newest_fresh_fix_is_the_current_position` と `a_fix_is_as_old_as_the_time_since_boot_says_whatever_the_clock_says`: `tracker.begin()` を `val token = tracker.begin()` にし、`tracker.end()` を `tracker.end(token)` にする。

- [ ] **Step 2: 失敗を確かめる**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest --rerun --tests '*PositionTrackerTest'`
Expected: コンパイルエラー（`begin()` が Unit を返す・`end` に引数が無い）。

- [ ] **Step 3: 実装する**

`location/Positions.kt` の `fun begin()` と `fun end(): Fix?`（とその KDoc）を次に置き換える:

```kotlin
  /** Starts collecting fixes; the token tells this begin from a later one. */
  fun begin(): Int
  /**
   * Where the ask is: the newest fix since the begin() that gave the token, unless it is older than 30 s. A token that
   * a later begin() has replaced changes nothing and gives none: the cleanup of a cancelled ask must not end the next
   * ask's watch (Android R1-01).
   */
  fun end(token: Int): Fix?
```

`location/PositionTracker.kt`:

```kotlin
  @Synchronized
  override fun begin(): Int {
    subscription?.remove()
    subscription = null
    fixes.clear()
    val gen = ++generation
    val add: (Fix) -> Unit = { fix -> synchronized(this) { if (gen == generation) fixes.add(fix) } }
    runCatching { source.lastKnown(add) }
    subscription = runCatching { source.watch(add) }.getOrNull()
    return gen
  }

  @Synchronized
  override fun end(token: Int): Fix? {
    if (token != generation) return null
    generation += 1
    subscription?.remove()
    subscription = null
    val latest = fixes.maxByOrNull { it.timestamp }
    fixes.clear()
    return latest?.takeIf { it.isFresh(source.now(), source.elapsed()) }
  }
```
（`begin` の `fun begin()` の行と本文の末尾に `return gen` を足し、`end` の先頭に `if (token != generation) return null` を足す。他の行は今のまま。）

`ask/AskController.kt` の `record()` で、`d.location.begin()` を `val track = d.location.begin()` に、`d.location.end()` をすべて `d.location.end(track)` に変える（7か所）。

`AskControllerTest.kt` の `Harness` の `location` の作り物を次に変える:

```kotlin
    location = positions ?: object : Positions {
      override fun begin(): Int { log += "loc:begin"; return 1 }
      override fun end(token: Int) = HERE
      override suspend fun latest(): Fix? { log += "loc:latest"; return latest }
    },
```
そして `Harness` の引数の末尾（`var latest: Fix? = HERE,` の次）に足す:
```kotlin
  /** A real tracker, to see what the cleanup of one ask does to the next. */
  val positions: Positions? = null,
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`
Expected: 全件通る（722件）。

- [ ] **Step 5: コミットする**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git checkout -b slice6-plan4
git add app/src/main/java/com/touringproject/v2/location/Positions.kt app/src/main/java/com/touringproject/v2/location/PositionTracker.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
git commit -m "fix: tell the position watches of one ask from the next by a token, so a cancelled ask's cleanup cannot end the next one's (R1-01)"
```

---

### Task 2: 経路の準備を取り消せるようにする（R1-03）

**Files:**
- Modify: `Android/app/src/main/java/com/touringproject/v2/audio/AudioRoute.kt`
- Test: `Android/app/src/test/java/com/touringproject/v2/audio/AudioTest.kt`

**Interfaces:**
- Produces: `AudioRoute.startVoiceRecognition(timeoutMs)`・`acquireSco(timeoutMs)` は、取り消されると呼び出しが `CancellationException` で返る前に、始めたこと（聞き手・時間切れ・通話の経路・音声認識の開始）をその場で元に戻す。取り消し後に遅れて来る headset の知らせは何もしない。

- [ ] **Step 1: 失敗するテストを書く**

`AudioTest.kt` の import に足す:

```kotlin
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import android.media.AudioDeviceInfo
import android.os.Looper
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Implementation
import org.robolectric.annotation.Implements
import org.robolectric.shadows.AudioDeviceInfoBuilder
import org.robolectric.shadows.ShadowAudioManager
import org.robolectric.shadow.api.Shadow
import java.time.Duration
```

ファイルの末尾に足す:

```kotlin
/** An audio manager whose call route never comes up by itself: the request is taken, the device is not set. */
@Implements(value = AudioManager::class, isInAndroidSdk = false)
class PendingScoAudioManager : ShadowAudioManager() {
  var requested = 0
  var cleared = 0

  @Implementation
  override fun setCommunicationDevice(device: AudioDeviceInfo): Boolean {
    requested += 1
    return true
  }

  @Implementation
  override fun clearCommunicationDevice() {
    cleared += 1
    super.clearCommunicationDevice()
  }
}

// Android R1-03: a route's setup that is called off is undone at once, not left to run on inside AudioRoute.
@RunWith(AndroidJUnit4::class)
@Config(sdk = [31], shadows = [PendingScoAudioManager::class])
class AudioRouteCancelTest {
  private val context = ApplicationProvider.getApplicationContext<Context>()
  private val audioManager = context.getSystemService(AudioManager::class.java)
  private val shadow = Shadow.extract<PendingScoAudioManager>(audioManager)
  private val scope = CoroutineScope(Dispatchers.Default)

  private fun idle(ms: Long = 0) {
    val looper = shadowOf(Looper.getMainLooper())
    if (ms > 0) looper.idleFor(Duration.ofMillis(ms)) else looper.idle()
  }

  /** The main looper is paused, so the test thread runs it while the coroutine waits on its own thread. */
  private fun pumpUntil(condition: () -> Boolean) {
    repeat(400) {
      if (condition()) return
      idle()
      Thread.sleep(5)
    }
    check(condition()) { "condition never became true" }
  }

  @Test
  fun a_screen_route_setup_that_is_called_off_clears_the_call_route_at_once_and_leaves_nothing_for_the_timeout() {
    val sco = AudioDeviceInfoBuilder.newBuilder().setType(AudioDeviceInfo.TYPE_BLUETOOTH_SCO).build()
    shadow.setAvailableCommunicationDevices(listOf(sco))
    val route = AudioRoute(context)
    val job = scope.launch { route.acquireSco(3_000) }
    pumpUntil { shadow.requested == 1 }
    assertEquals(0, shadow.cleared)
    runBlocking {
      scope.launch { job.cancelAndJoin() }
      pumpUntil { job.isCompleted }
    }
    assertEquals(1, shadow.cleared)
    assertEquals(AudioManager.MODE_NORMAL, audioManager.mode)
    // The 3 s timeout must not come back to clear the route of whoever has it by then.
    idle(5_000)
    assertEquals(1, shadow.cleared)
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest --rerun --tests '*AudioRouteCancelTest'`
Expected: FAIL（`expected:<1> but was:<0>`）。

- [ ] **Step 3: 実装する**

`audio/AudioRoute.kt` を次のとおり変える（各 old は一意）。

1. import に `import kotlinx.coroutines.CancellationException` を足す（`import kotlinx.coroutines.Dispatchers` の前）。

2. ファイル先頭のコメントの `// All Bluetooth and AudioManager work runs on the main thread.` を次に置き換える:

```kotlin
// A setup (startVoiceRecognition, acquireSco) that is cancelled is undone on the main thread before the call returns:
// whatever it had begun or brought up is let go, and nothing it left waiting (a listener, a timeout, a headset
// callback) acts later on the route of whoever holds it by then (Android R1-03).
//
// All Bluetooth and AudioManager work runs on the main thread.
```

3. `releaseSco()` を次に置き換える:

```kotlin
  suspend fun releaseSco() = withContext(Dispatchers.Main) { release() }

  private fun release() {
    runCatching { audioManager.clearCommunicationDevice() }
    audioManager.mode = AudioManager.MODE_NORMAL
  }
```

4. `onMain` を次に置き換える（直後に `VrAttempt` を置く）:

```kotlin
  /** block starts a setup and gives back what undoes it, however far it has come. */
  private suspend fun onMain(block: (done: (Boolean, String) -> Unit) -> (() -> Unit)): RouteResult = withContext(Dispatchers.Main) {
    var undo: () -> Unit = {}
    try {
      suspendCancellableCoroutine { cont ->
        var resumed = false
        undo = block { ok, note ->
          if (!resumed) {
            resumed = true
            cont.resume(RouteResult(ok, note))
          }
        }
      }
    } catch (e: CancellationException) {
      undo()
      throw e
    }
  }

  /** One startVoiceRecognition: a headset callback that comes after the cancel does nothing. */
  private class VrAttempt {
    var cancelled = false
    var session = 0
  }
```

5. `private fun startVoiceRecognition(timeoutMs: Long, done: (Boolean, String) -> Unit) {` から `begin` の先頭 `vrDevice = device` まで（`startVoiceRecognition`・`begin` の先頭）を次に置き換える。`begin` の残り（`val onTimeout` 以降）は今のまま:

```kotlin
  private fun startVoiceRecognition(timeoutMs: Long, done: (Boolean, String) -> Unit): () -> Unit {
    if (vrPending != null) {
      done(false, "already starting")
      return {}
    }
    val attempt = VrAttempt()
    ensureReceiver()
    withHeadset { h ->
      if (attempt.cancelled) return@withHeadset
      if (h == null) {
        done(false, "no headset proxy")
        return@withHeadset
      }
      val device = try {
        pickDevice(h)
      } catch (e: SecurityException) {
        done(false, "no Bluetooth permission")
        return@withHeadset
      }
      if (device == null) {
        done(false, "no HFP device connected")
        return@withHeadset
      }
      if (vrDevice != null) endSession(h, "superseded")
      waitAudioOff(h, device, attempt) { begin(h, device, timeoutMs, done, attempt) }
    }
    return {
      attempt.cancelled = true
      // Only a setup that had begun owns the session; one still waiting for the headset has brought nothing up.
      if (attempt.session != 0 && attempt.session == vrSession) {
        vrPending?.invoke(false, "cancelled")
        headset?.let { endSession(it, "cancelled") }
        audioManager.mode = AudioManager.MODE_NORMAL
      }
    }
  }

  private fun begin(h: BluetoothHeadset, device: BluetoothDevice, timeoutMs: Long, done: (Boolean, String) -> Unit, attempt: VrAttempt) {
    val session = ++vrSession
    attempt.session = session
    vrDevice = device
```

6. `waitAudioOff` の先頭を次に置き換える（`private fun waitAudioOff(h: BluetoothHeadset, device: BluetoothDevice, then: () -> Unit) {` から `val on = ...` の手前まで）:

```kotlin
  private fun waitAudioOff(h: BluetoothHeadset, device: BluetoothDevice, attempt: VrAttempt, then: () -> Unit) {
    val deadline = System.currentTimeMillis() + AUDIO_OFF_WAIT_MS
    val check = object : Runnable {
      override fun run() {
        if (attempt.cancelled) return
```
（`val on = runCatching { h.isAudioConnected(device) }...` 以降は今のまま。）

7. `acquireSco` の本体の頭から `val sink` の判定までを次に置き換える:

```kotlin
  private fun acquireSco(timeoutMs: Long, done: (Boolean, String) -> Unit): () -> Unit {
    // The communication-device API is Android 12+; before that the screen button records from the phone's microphone.
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
      done(false, "needs Android 12")
      return {}
    }
    val am = audioManager
    am.communicationDevice?.let { if (it.type == SCO_TYPE) { done(true, "already SCO"); return { release() } } }
    am.mode = AudioManager.MODE_IN_COMMUNICATION
    val sink = am.availableCommunicationDevices.firstOrNull { it.type == SCO_TYPE }
    if (sink == null) {
      am.mode = AudioManager.MODE_NORMAL
      done(false, "no SCO output")
      return {}
    }
```
そして `acquireSco` の末尾（`val accepted = ...` 以降）を次に置き換える:

```kotlin
    val accepted = runCatching { am.setCommunicationDevice(sink) }.getOrDefault(false)
    if (!accepted) {
      finish(false, "setCommunicationDevice returned false")
      return {}
    }
    am.communicationDevice?.let { if (it.type == SCO_TYPE) finish(true, "connected (immediate)") }
    // Called off while pending: settle as a failure (clears the route, drops the listener and the timeout). Called off
    // after it connected: the route is up and the caller never got it, so let it go.
    return { if (settled) release() else finish(false, "cancelled") }
  }
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`
Expected: 全件通る（723件）。

- [ ] **Step 5: コミットする**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/audio/AudioRoute.kt app/src/test/java/com/touringproject/v2/audio/AudioTest.kt
git commit -m "fix: undo a called-off route setup at once instead of leaving its listener, timeout and call route behind (R1-03)"
```

---

### Task 3: 経路を札で借りる（R10-01・R1-01）

**Files:**
- Create: `Android/app/src/main/java/com/touringproject/v2/audio/RouteLeases.kt`
- Create: `Android/app/src/test/java/com/touringproject/v2/audio/RouteLeasesTest.kt`
- Modify: `…/audio/AudioPorts.kt`・`…/audio/AudioRouteControl.kt`・`…/ask/AskController.kt`・`…/recordings/Trial.kt`・`…/voice/VoiceInput.kt`・`…/handsfree/PressRouter.kt`・`…/AppGraph.kt`
- Test: `AskControllerTest.kt`・`TrialTest.kt`・`VoiceInputTest.kt`・`RecordingCheckTest.kt`・`NoteRoutesTest.kt`・`PressRouterTest.kt`

**Interfaces:**
- Produces:
  - `interface RouteDriver { suspend fun start(source: Source): Boolean; suspend fun stop(); fun inputDevice(): InputDevice? }`（今の `RouteControl` の中身。実装は `AudioRouteControl`）
  - `interface RouteLease { val routed: Boolean; fun inputDevice(): InputDevice?; suspend fun release() }`（`release` は最初の1回だけ効く）
  - `interface RouteControl { suspend fun lease(source: Source): RouteLease }`（前の持ち主が返すのを待つ。取り消されたら何も持たない。取れないときは例外）
  - `class RouteLeases(driver: RouteDriver, waitMs: Long = LEASE_WAIT_MS) : RouteControl`、`const val LEASE_WAIT_MS = 8_000L`、`class RouteBusyException`
  - `class LeaseRequest(route: RouteControl, source: Source) { suspend fun take(): RouteLease?; fun callOff() }`（`take` は呼び止められると null。他の例外はそのまま投げる）

- [ ] **Step 1: 失敗するテストを書く**

`RouteLeasesTest.kt`（新規）:

```kotlin
package com.touringproject.v2.audio

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

// Android R10-01 / R1-01 / R1-03: the audio route goes to one user at a time, and a user that is called off leaves
// nothing held.
class RouteLeasesTest {
  private class Driver : RouteDriver {
    val log = mutableListOf<String>()
    var gate: CompletableDeferred<Unit>? = null
    var error: Exception? = null
    override suspend fun start(source: Source): Boolean {
      log += "start:${source.name.lowercase()}"
      error?.let { throw it }
      gate?.await()
      return true
    }
    override suspend fun stop() { log += "stop" }
    override fun inputDevice(): InputDevice? = null
  }

  @Test
  fun a_second_lease_waits_until_the_first_is_let_go() = runTest {
    val driver = Driver()
    val leases = RouteLeases(driver)
    val first = leases.lease(Source.HANDSFREE)
    var second: RouteLease? = null
    launch { second = leases.lease(Source.SCREEN) }
    runCurrent()
    assertNull(second)
    assertEquals(listOf("start:handsfree"), driver.log)
    first.release()
    runCurrent()
    assertNotNull(second)
    assertEquals(listOf("start:handsfree", "stop", "start:screen"), driver.log)
  }

  @Test
  fun a_lease_let_go_of_twice_acts_once_and_never_lets_go_of_the_next_ones_route() = runTest {
    val driver = Driver()
    val leases = RouteLeases(driver)
    val first = leases.lease(Source.HANDSFREE)
    first.release()
    val second = leases.lease(Source.HANDSFREE)
    // The cleanup of the first, running late.
    first.release()
    assertEquals(listOf("start:handsfree", "stop", "start:handsfree"), driver.log)
    second.release()
    assertEquals(listOf("start:handsfree", "stop", "start:handsfree", "stop"), driver.log)
  }

  @Test
  fun a_setup_that_is_cancelled_holds_nothing_and_does_not_stop_a_route_it_never_brought_up() = runTest {
    val driver = Driver().apply { gate = CompletableDeferred() }
    val leases = RouteLeases(driver)
    val job = launch { leases.lease(Source.HANDSFREE) }
    runCurrent()
    job.cancel()
    runCurrent()
    driver.gate = null
    val next = leases.lease(Source.SCREEN)
    assertTrue(next.routed)
    assertEquals(listOf("start:handsfree", "start:screen"), driver.log)
  }

  @Test
  fun a_wait_that_is_cancelled_leaves_the_route_to_its_holder() = runTest {
    val driver = Driver()
    val leases = RouteLeases(driver)
    val first = leases.lease(Source.HANDSFREE)
    val waiting = launch { leases.lease(Source.SCREEN) }
    runCurrent()
    waiting.cancel()
    runCurrent()
    first.release()
    // Nobody is waiting any more: the route is free for the next one at once.
    leases.lease(Source.SCREEN)
    assertEquals(listOf("start:handsfree", "stop", "start:screen"), driver.log)
  }

  @Test
  fun a_setup_that_throws_holds_nothing() = runTest {
    val driver = Driver().apply { error = SecurityException("BLUETOOTH_CONNECT") }
    val leases = RouteLeases(driver)
    val thrown = try {
      leases.lease(Source.HANDSFREE)
      null
    } catch (e: SecurityException) {
      e
    }
    assertNotNull(thrown)
    driver.error = null
    assertTrue(leases.lease(Source.HANDSFREE).routed)
  }

  @Test
  fun a_holder_that_never_lets_go_is_given_up_on_after_the_wait() = runTest {
    val leases = RouteLeases(Driver(), waitMs = 5_000)
    leases.lease(Source.HANDSFREE)
    var thrown: Exception? = null
    launch {
      try {
        leases.lease(Source.SCREEN)
      } catch (e: RouteBusyException) {
        thrown = e
      }
    }
    runCurrent()
    advanceTimeBy(4_999)
    assertNull(thrown)
    advanceTimeBy(2)
    runCurrent()
    assertNotNull(thrown)
  }

  @Test
  fun a_request_called_off_during_the_setup_gives_none() = runTest {
    val driver = Driver().apply { gate = CompletableDeferred() }
    val request = LeaseRequest(RouteLeases(driver), Source.HANDSFREE)
    var taken: RouteLease? = null
    var finished = false
    launch {
      taken = request.take()
      finished = true
    }
    runCurrent()
    request.callOff()
    runCurrent()
    assertTrue(finished)
    assertNull(taken)
  }

  @Test
  fun a_request_called_off_before_it_started_gives_none_and_one_called_off_late_changes_nothing() = runTest {
    val early = LeaseRequest(RouteLeases(Driver()), Source.HANDSFREE)
    early.callOff()
    assertNull(early.take())
    val late = LeaseRequest(RouteLeases(Driver()), Source.HANDSFREE)
    val lease = late.take()
    late.callOff()
    assertNotNull(lease)
    assertNull(lease!!.inputDevice())
  }
}
```

`AskControllerTest.kt` の `class AskControllerTest {` の直後に足す（`a_cancel_during_route_setup_does_not_start_the_recording` の書き換えは Step 5）:

```kotlin
  // Android R1-01: an ask that starts right after a cancel waits for the route, and the cancelled ask's cleanup takes
  // neither its route nor its position.
  @Test
  fun an_ask_started_after_a_cancel_during_route_setup_is_recorded_with_its_position() = runTest {
    val source = object : com.touringproject.v2.location.PositionSource {
      override fun now() = 100_000L
      override fun elapsed() = 50_000L
      override fun lastKnown(onFix: (Fix) -> Unit) = onFix(HERE)
      override fun watch(onFix: (Fix) -> Unit) = com.touringproject.v2.location.Subscription {}
    }
    var starts = 0
    val h = Harness(
      this,
      stopAfterMs = 1_000,
      routeStart = { if (++starts == 1) CompletableDeferred<Boolean>().await() else true },
      positions = com.touringproject.v2.location.PositionTracker(source),
    )
    val first = launch { h.controller.run(Source.HANDSFREE) }
    h.until { starts == 1 }
    h.controller.cancel()
    val second = launch { h.controller.run(Source.HANDSFREE) }
    second.join()
    first.join()
    assertEquals(2, starts)
    assertEquals(Point(HERE.latitude, HERE.longitude), h.bodies.single().location)
    assertEquals(1, h.log.count { it == "route:stop" })
  }

  // Android R10-01: the ask after a cancelled one in its recording waits until the first has let go of the route.
  @Test
  fun an_ask_waits_for_the_one_before_to_let_go_of_the_route() = runTest {
    val h = Harness(this, stopAfterMs = null)
    val first = launch { h.controller.run(Source.HANDSFREE) }
    h.until { "rec:start" in h.log }
    h.controller.cancel()
    val second = launch { h.controller.run(Source.HANDSFREE) }
    h.until { h.log.count { it == "rec:start" } == 2 }
    // The first one let go (rec:cancel, route:stop) before the second brought the route up again.
    val firstStop = h.log.indexOf("route:stop")
    val secondStart = h.log.lastIndexOf("route:handsfree")
    assertTrue(firstStop in 0 until secondStart)
    h.controller.cancel()
    first.join()
    second.join()
  }
```

`VoiceInputTest.kt`: ファイル末尾の `// Final review I-1, I-2: ...` から最後までのテスト（`a_press_while_the_run_before_still_unwinds_gets_the_failure_cue`）を次に置き換える（クラスの閉じ括弧まで）:

```kotlin
  // Final review I-1, I-2: a run that is still unwinding is busy for a moment: a press gets the failure cue rather than
  // nothing. The route's setup is called off with the run (Android R1-03), so there is nothing to let go of.
  @Test
  fun a_press_while_the_run_before_still_unwinds_gets_the_failure_cue() = runTest {
    val h = VoiceHarness(this, routeGate = CompletableDeferred())
    val left = h.voice.attach()
    h.voice.press(Source.HANDSFREE)
    runCurrent()
    h.voice.detach(left)
    assertTrue(h.voice.busy)
    h.voice.attach()
    h.voice.press(Source.HANDSFREE)
    assertEquals("cue:failure", h.log.last())
    advanceUntilIdle()
    assertEquals(false, h.voice.busy)
    assertEquals(listOf("route:handsfree", "cue:failure"), h.log)
    assertEquals(VOICE_IDLE, h.voice.state)
  }

  // Android R1-03: leaving SC-19 while the route comes up ends the run at once; the next press starts as usual.
  @Test
  fun leaving_during_the_route_setup_lets_the_next_press_start_at_once() = runTest {
    val h = VoiceHarness(this, routeGate = CompletableDeferred())
    val left = h.voice.attach()
    h.voice.press(Source.HANDSFREE)
    runCurrent()
    h.voice.detach(left)
    runCurrent()
    assertEquals(false, h.voice.busy)
    h.routeGate = null
    h.voice.attach()
    h.voice.press(Source.HANDSFREE)
    runCurrent()
    assertEquals(VoicePhase.RECORDING, h.voice.state.phase)
    assertEquals(listOf("route:handsfree", "route:handsfree", "rec:start", "cue:start"), h.log)
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew compileDebugUnitTestKotlin`
Expected: コンパイルエラー（`RouteLeases`・`RouteDriver`・`LeaseRequest` が無い）。

- [ ] **Step 3: 実装する（経路の部品）**

`audio/AudioPorts.kt` の `interface RouteControl { ... }` を次に置き換える:

```kotlin
/** The audio route itself, which one user at a time may bring up and let go of; users reach it through [RouteControl]. */
interface RouteDriver {
  /** Brings up the intercom microphone; false means the phone's own microphone will be used. */
  suspend fun start(source: Source): Boolean
  suspend fun stop()
  /** The microphone of the recording that is running right now (only visible while it runs). */
  fun inputDevice(): InputDevice?
}

/** One user's hold on the audio route: from [RouteControl.lease] until [release]. */
interface RouteLease {
  /** False: the intercom microphone did not come up and the phone's own microphone will be used. */
  val routed: Boolean
  /** The microphone of the recording that is running right now (only visible while it runs). */
  fun inputDevice(): InputDevice?
  /** Lets go of the route. Idempotent: only the first call acts. */
  suspend fun release()
}

/** The audio route is shared by questions, SC-12's trial and SC-19's voice input, one user at a time. */
interface RouteControl {
  /**
   * Waits for the user before to let go, then brings the route up. Cancelling the wait or the setup leaves nothing held.
   * Throws when the route cannot be taken (e.g. the Bluetooth permission was denied, or the user before never let go);
   * the caller records from the phone's own microphone then and has nothing to release.
   */
  suspend fun lease(source: Source): RouteLease
}
```

`audio/AudioRouteControl.kt` の `class AudioRouteControl(private val route: AudioRoute) : RouteControl {` を `: RouteDriver {` に変える。

`audio/RouteLeases.kt`（新規）:

```kotlin
package com.touringproject.v2.audio

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.util.concurrent.atomic.AtomicBoolean

/** The longest a user waits for the one before to let go of the route. */
const val LEASE_WAIT_MS = 8_000L

class RouteBusyException : IllegalStateException("the audio route is held by another user")

/**
 * Hands the one audio route to one user at a time (Android R10-01). A user that is cancelled while it waits or while the
 * route comes up leaves nothing held, and a lease let go of twice acts once, so the cleanup of an ask that was
 * cancelled can never let go of the route of the ask after it.
 */
class RouteLeases(private val driver: RouteDriver, private val waitMs: Long = LEASE_WAIT_MS) : RouteControl {
  private val gate = Mutex()

  override suspend fun lease(source: Source): RouteLease {
    var locked = false
    try {
      withTimeout(waitMs) {
        gate.lock()
        locked = true
      }
    } catch (e: CancellationException) {
      if (locked) gate.unlock()
      throw if (e is TimeoutCancellationException) RouteBusyException() else e
    }
    try {
      return Lease(driver.start(source))
    } catch (e: Throwable) {
      gate.unlock()
      throw e
    }
  }

  private inner class Lease(override val routed: Boolean) : RouteLease {
    private val released = AtomicBoolean(false)

    override fun inputDevice(): InputDevice? = driver.inputDevice()

    override suspend fun release() {
      if (!released.compareAndSet(false, true)) return
      try {
        withContext(NonCancellable) { driver.stop() }
      } finally {
        gate.unlock()
      }
    }
  }
}

/**
 * One try to take the route that its owner can call off from another coroutine, e.g. the big button while the route
 * is still coming up. [take] gives null then.
 */
class LeaseRequest(private val route: RouteControl, private val source: Source) {
  private var attempt: Deferred<RouteLease>? = null
  private var calledOff = false

  suspend fun take(): RouteLease? = coroutineScope {
    val job: Deferred<RouteLease> = async { route.lease(source) }
    attempt = job
    if (calledOff) job.cancel()
    try {
      job.await()
    } catch (e: CancellationException) {
      // The caller's own cancellation goes on; only a call-off ends here.
      currentCoroutineContext().ensureActive()
      null
    }
  }

  fun callOff() {
    calledOff = true
    attempt?.cancel()
  }
}
```

- [ ] **Step 4: 実装する（使う側）**

`ask/AskController.kt`:
- import に足す: `import com.touringproject.v2.audio.LeaseRequest` と `import com.touringproject.v2.audio.RouteLease`（`import com.touringproject.v2.audio.Source` の前）。
- `private class Run(val id: Int, val source: Source, var returned: Boolean = false, val cancelled: () -> Unit = {})` を次に置き換える:

```kotlin
  // routeRequest is the try to take the audio route while it is coming up: the big button calls it off at once.
  private class Run(val id: Int, val source: Source, var returned: Boolean = false, val cancelled: () -> Unit = {}) {
    var routeRequest: LeaseRequest? = null
  }
```
- `cancel()` の `current?.cancelled?.invoke()` の次の行に `current?.routeRequest?.callOff()` を足す。
- `record()` 関数全体（`private suspend fun record(` から、次の `private suspend fun send(` の手前まで）を次に置き換える:

```kotlin
  private suspend fun record(run: Run, settings: Settings): Recording? {
    val d = deps
    val track = d.location.begin()
    val request = LeaseRequest(d.route, run.source)
    run.routeRequest = request
    var lease: RouteLease? = null
    var calledOff = false
    try {
      lease = request.take()
      calledOff = lease == null
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      // e.g. the Bluetooth permission was denied: record from the phone's microphone instead of failing the ask.
      d.log("route_failed", mapOf("error" to e.toString()))
    }
    // Setting up the route can take seconds; a cancel or a newer ask meanwhile owns the recorder and the route.
    if (calledOff || !isCurrent(run)) {
      lease?.release()
      d.location.end(track)
      return null
    }
    try {
      if (lease?.routed != true) dispatch(FlowEvent.PhoneMic(d.now()))
      try {
        d.recorder.start()
      } catch (e: Exception) {
        lease?.release()
        d.location.end(track)
        fail(FailureReason.MIC, run)
        return null
      }
      // After the recorder is running: the rider starts talking on this cue, so nothing said after it is lost.
      d.cues.start(settings.startCueMs)
      val startedAt = d.now()
      while (state.phase == Phase.RECORDING && isCurrent(run) && d.now() - startedAt < settings.recordLimitMs) {
        d.sleep(TICK_MS)
      }
      if (!isCurrent(run)) {
        d.recorder.cancel()
        lease?.release()
        d.location.end(track)
        return null
      }
      // Read while the recorder still runs: the system only reports the input device of an active recording.
      val device = lease?.inputDevice()
      val phoneMic = state.phoneMic
      stopRecording()
      val stopped = try {
        d.recorder.stop()
      } catch (e: Exception) {
        lease?.release()
        d.location.end(track)
        fail(FailureReason.MIC, run)
        return null
      }
      lease?.release()
      // A microphone held by another app can start without delivering anything; sending nothing would be heard as "no speech".
      if (stopped.pcm.isEmpty()) {
        d.location.end(track)
        fail(FailureReason.MIC, run)
        return null
      }
      val endedAt = d.now()
      val meta = RecordingMeta(stopped.name, startedAt, pcmDurationMs(stopped.pcm.size), phoneMic, device, null)
      val here = d.location.end(track)
      val heading = d.heading(here)
      return Recording(Base64.getEncoder().encodeToString(stopped.pcm), stopped.name, here, heading, endedAt, meta, stopped.pcm)
    } finally {
      // Whatever ended the recording, the route is let go (a lease let go of already acts once).
      lease?.release()
    }
  }

```

`recordings/Trial.kt`:
- import に足す: `import com.touringproject.v2.audio.LeaseRequest`（`PcmPlayback` の前）と `import com.touringproject.v2.audio.RouteLease`（`RouteControl` の次）。
- `private var running = false` の行の直前のコメントを `// From start() until its run has unwound, also after a cancel: a second run must not share the recorder.` にし、`private var running = false` の次に足す:

```kotlin
  // The try to take the audio route; a cancel calls it off while the route is still coming up.
  private var routeRequest: LeaseRequest? = null
```
- `busy` のプロパティ（KDoc 付きの2行）を削除する。
- `cancel()` の `session += 1` の次の行に `routeRequest?.callOff()` を足す。
- `run()` の中の、`val routed = try { d.route.start(Source.SCREEN) } ...` から、`d.route.stop()` の後の `if (!isCurrent(session)) return` までの部分（`recorded.pcm.isEmpty()` の判定の手前）を次に置き換え、`recorded.pcm.isEmpty()` 以降を新しい関数 `playBack` に移す:

```kotlin
    val request = LeaseRequest(d.route, Source.SCREEN)
    routeRequest = request
    var lease: RouteLease? = null
    var calledOff = false
    try {
      lease = request.take()
      calledOff = lease == null
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      // The route could not be taken: the phone's own microphone records.
    }
    // Setting up the route can take seconds; SC-12 may have been left meanwhile (React Native version's issue #10).
    if (calledOff || !isCurrent(session)) {
      lease?.release()
      return
    }
    try {
      val routed = lease?.routed == true
      set(state.copy(phoneMic = !routed))
      try {
        d.recorder.start()
      } catch (e: CancellationException) {
        throw e
      } catch (e: Exception) {
        lease?.release()
        finish(session, TrialState(phoneMic = !routed, error = TRIAL_RECORD_MESSAGE))
        return
      }
      if (!isCurrent(session)) {
        d.recorder.cancel()
        lease?.release()
        return
      }
      d.cueStart(d.startCueMs())
      val startedAt = d.now()
      val limitMs = d.recordLimitMs()
      while (isCurrent(session) && !stopRequested && d.now() - startedAt < limitMs) d.sleep(TICK_MS)
      if (!isCurrent(session)) {
        d.recorder.cancel()
        lease?.release()
        return
      }
      // Read while the recorder still runs: the system only reports the input device of an active recording.
      val device = lease?.inputDevice()
      val recorded = try {
        d.recorder.stop()
      } catch (e: CancellationException) {
        throw e
      } catch (e: Exception) {
        lease?.release()
        finish(session, TrialState(phoneMic = !routed, error = TRIAL_RECORD_MESSAGE))
        return
      }
      lease?.release()
      if (!isCurrent(session)) return
      playBack(session, recorded.pcm, routed, device)
    } finally {
      // Whatever ended the run, the route is let go (a lease let go of already acts once).
      lease?.release()
    }
  }

  private suspend fun playBack(session: Int, pcm: ByteArray, routed: Boolean, device: InputDevice?) {
    val d = deps
    if (pcm.isEmpty()) {
      finish(session, TrialState(phoneMic = !routed, device = device, error = TRIAL_RECORD_MESSAGE))
      return
    }
    set(state.copy(phase = TrialPhase.PLAYING, device = device))
    val error = try {
      d.player.play(pcm)
      null
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      TRIAL_PLAY_MESSAGE
    }
    // Keep showing which microphone was used after the playback.
    finish(session, state.copy(phase = TrialPhase.IDLE, error = error))
  }
```
（元の `run()` の `recorded.pcm.isEmpty()` から `finish(session, state.copy(phase = TrialPhase.IDLE, error = error))` と閉じ括弧までは、上の `playBack` に移るので、`run()` の中には残さない。）

`voice/VoiceInput.kt`:
- import に足す: `import com.touringproject.v2.audio.RouteLease`（`RouteControl` の次）。
- クラスの KDoc の `the run is cancelled and lets go of the recorder and the route at once, except for a route still being set up, which cannot be cut short; until then the run is busy.` を `the run is cancelled and lets go of the recorder and the route at once, also while the route is still coming up; the run is busy only for the moment that takes.` に変える（`*` の行頭は今のまま）。
- `private var routeUp = false` を `private var lease: RouteLease? = null` に変える。
- `busy` の KDoc を `/** Also true while a run left on SC-19 still unwinds; a press then gets the failure cue. */` にする。
- `run()` の中の `routeUp = true` と `d.route.start(source)` の `try { ... }` を次にする（`catch` の中身は今のまま）:

```kotlin
    try {
      lease = d.route.lease(source)
    } catch (e: CancellationException) {
```
- `stopRoute()` を次に置き換える:

```kotlin
  private suspend fun stopRoute() {
    val held = lease ?: return
    lease = null
    held.release()
  }
```

`handsfree/PressRouter.kt`:
- コンストラクタから `private val trialBusy: () -> Boolean,` と `private val voiceBusy: () -> Boolean = { false },` を消す。
- `press()` から `if (trialBusy()) return` と `if (voiceBusy()) return` を消す。
- `tap()` を `fun tap() = askTap()` にする。
- クラスの KDoc の末尾の4行（` * playing on SC-12 is stopped first, ...` で始まり ` */` で終わる）を次の3行に置き換える:

```kotlin
 * playing on SC-12 is stopped first, since the microphone would pick it up, and the ask loop gets it. A trial or a
 * voice input that was left and still unwinds holds the audio route; the ask waits for its lease to be let go
 * ([com.touringproject.v2.audio.RouteLeases]), so the router has nothing to hold back.
 */
```

`AppGraph.kt`:
- import に足す: `import com.touringproject.v2.audio.RouteLeases`（`PcmRecorder` の次）。
- `val audioRoute = AudioRoute(context)` の次に足す:

```kotlin
  // The one audio route, handed to the ask loop, SC-12's trial and SC-19's voice input one at a time.
  private val routes = RouteLeases(AudioRouteControl(audioRoute))
```
- `route = AudioRouteControl(audioRoute),` を3か所（controller・trial・voice）とも `route = routes,` にする。
- `router` の `PressRouter(` から `trialBusy = { trial.busy },` と `voiceBusy = { voice.busy },` を消す。
- コメント `// SC-12: its own route control, recorder and players, so nothing it does is shared with the ask loop.` を `// SC-12: its own recorder and players; the audio route is the app's one, taken one user at a time.` にする。
- コメント `// SC-19's voice input: its own route control and recorder, like SC-12's trial. The audio route underneath is the` と次の行 `// app's one, so the press router keeps asks off it while a voice input unwinds.` を `// SC-19's voice input: its own recorder, like SC-12's trial. The audio route is the app's one, taken one user at a time.` の1行にする。

- [ ] **Step 5: 既存のテストの作り物を直す**

各テストの `RouteControl` の作り物を `RouteLeases(object : RouteDriver {...})` で包む（import は `com.touringproject.v2.audio.RouteControl` を `RouteDriver` と `RouteLeases` の2つに変える）:

- `AskControllerTest.kt` の `Harness`: `route = object : RouteControl {` … `}` を `route = RouteLeases(object : RouteDriver {` … `}),` にする（中身は今のまま）。
- `TrialTest.kt`: 同じ。`routeGate?.await()` は今のまま。
- `VoiceInputTest.kt`: 同じ。ただし `routeGate?.let { gate -> kotlinx.coroutines.withContext(kotlinx.coroutines.NonCancellable) { gate.await() } }` を `routeGate?.await()` にし、`routeGate` の KDoc を `/** Holds the route's setup (up to 4 s on the headset); a cancel ends the wait, as AudioRoute now undoes a called-off setup. */` にする。
- `RecordingCheckTest.kt`・`ui/NoteRoutesTest.kt`: 同じ。
- `ui/NoteRoutesTest.kt` の `PressRouter(` の呼び出しから `trialBusy = { false },` を消す。
- `PressRouterTest.kt`: `trialBusy`・`voiceBusy` の変数と、コンストラクタ引数 `trialBusy = { trialBusy || trialActive },`・`voiceBusy = { voiceBusy },` を消す。`a_press_while_a_left_trial_still_unwinds_starts_no_question` と `a_press_while_a_left_voice_input_still_unwinds_starts_no_question`（とその直前のコメント）を消す。

`AskControllerTest.kt` の `a_cancel_during_route_setup_does_not_start_the_recording` を次に置き換える:

```kotlin
  @Test
  fun a_cancel_during_route_setup_does_not_start_the_recording() = runTest {
    val gate = CompletableDeferred<Boolean>()
    val h = Harness(this, stopAfterMs = null, routeStart = { gate.await() })
    val running = launch { h.controller.run(Source.SCREEN) }
    h.until { "route:screen" in h.log }
    h.controller.cancel()
    running.join()
    assertFalse("rec:start" in h.log)
    assertFalse("cue:start" in h.log)
    // The setup is called off with the ask (Android R1-03), so nothing was brought up and nothing is let go of.
    assertFalse("route:stop" in h.log)
    assertEquals(Phase.IDLE, h.phase)
  }
```

`TrialTest.kt` の `leaving_while_the_route_is_set_up_never_opens_the_microphone` を次に置き換え、直後の `a_trial_left_during_route_setup_stays_busy_until_it_has_unwound` を次の新しいテストに置き換える:

```kotlin
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
    job.join()
    // The setup was called off, so nothing was brought up and there is nothing to let go of (Android R1-03).
    assertEquals(listOf("route:screen", "play:stop"), h.log)
    assertEquals(TRIAL_IDLE, h.trial.state)
  }

  @Test
  fun a_trial_left_during_route_setup_ends_at_once_without_waiting_for_the_route() = runTest {
    val h = TrialHarness(this, routeGate = CompletableDeferred())
    val job = h.launchStart()
    h.until { "route:screen" in h.log }
    h.trial.cancel()
    assertFalse(h.trial.active)
    job.join()
    assertTrue(job.isCompleted)
  }
```
（`leaving_while_the_route_is_set_up_never_opens_the_microphone` の本文は、元の `val gate`… `h.trial.start()` までは変えず、`gate.complete(Unit)` の行を消し、最後の期待値を上のとおりにする。）

`RecordingCheckTest.kt` の `leaving_right_after_the_trial_button_starts_nothing_later` の期待を次にする:

```kotlin
    // The cancel stops the trial's player and calls off the route's setup: nothing was brought up to give back.
    assertEquals(listOf("trial:stop"), w.log)
```

- [ ] **Step 6: 通ることを確かめる**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest && ./gradlew compileDebugAndroidTestKotlin assembleDebug && python3 scripts/package-cycles.py | tail -3`
Expected: 全件通る（732件）。androidTest と debug のビルドが通る。パッケージの循環は `(root) <-> service`・`(root) <-> ui` の2組のまま。

- [ ] **Step 7: コミットする**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/audio/AudioPorts.kt app/src/main/java/com/touringproject/v2/audio/RouteLeases.kt app/src/main/java/com/touringproject/v2/audio/AudioRouteControl.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/recordings/Trial.kt app/src/main/java/com/touringproject/v2/voice/VoiceInput.kt app/src/main/java/com/touringproject/v2/handsfree/PressRouter.kt app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/test/java/com/touringproject/v2/audio/RouteLeasesTest.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/recordings/TrialTest.kt app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt app/src/test/java/com/touringproject/v2/voice/VoiceInputTest.kt app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt app/src/test/java/com/touringproject/v2/handsfree/PressRouterTest.kt
git commit -m "feat: lend the audio route to one user at a time by a lease, so a cancelled user's cleanup cannot break the next one's route (R10-01, R1-01, R1-03)"
```

---

### Task 4: 読み上げに上限を付ける（R1-02）

**Files:**
- Modify: `Android/app/src/main/java/com/touringproject/v2/ask/AskController.kt`
- Modify: `Android/app/src/main/java/com/touringproject/v2/audio/TtsSpeech.kt`
- Test: `Android/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt`

**Interfaces:**
- Produces: `const val SAY_BASE_MS = 5_000L`・`const val SAY_PER_CHAR_MS = 300L`・`fun sayLimitMs(text: String): Long`（`AskController.kt` のトップレベル）。

- [ ] **Step 1: 失敗するテストを書く**

`AskControllerTest.kt` の `class AskControllerTest {` の直後に足す:

```kotlin
  // Android R1-02: the device voice may never say it is done; the ask must not stay SPEAKING for good.
  @Test
  fun a_speech_that_never_returns_is_cut_off_and_the_ask_ends() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, play = { throw IllegalStateException("cannot play") }, sayGate = CompletableDeferred())
    val running = launch { h.controller.run(Source.SCREEN) }
    h.until { "say:愛鷹山です。" in h.log }
    testScheduler.advanceTimeBy(sayLimitMs("愛鷹山です。") - 1)
    testScheduler.runCurrent()
    assertEquals(Phase.SPEAKING, h.phase)
    testScheduler.advanceTimeBy(2)
    testScheduler.runCurrent()
    assertEquals(Phase.IDLE, h.phase)
    assertTrue("say:stop" in h.log)
    running.join()
  }

  // The same limit holds for the notice said while an ask is under way: the answer must not wait for it for good.
  @Test
  fun a_busy_notice_that_never_returns_does_not_hold_the_answer() = runTest {
    val gate = CompletableDeferred<Unit>()
    val h = Harness(this, stopAfterMs = 1_000, answers = listOf(PROCESSING, PROCESSING, PROCESSING, done()), sayGate = gate)
    val running = launch { h.controller.run(Source.HANDSFREE) }
    h.until { h.phase == Phase.WAITING }
    h.controller.press()
    h.until { BUSY in h.log }
    running.join()
    assertEquals(Phase.IDLE, h.phase)
    assertTrue("play:https://audio/1.mp3" in h.log)
  }
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest --rerun --tests '*AskControllerTest'`
Expected: コンパイルエラー（`sayLimitMs` が無い）。

- [ ] **Step 3: 実装する**

`ask/AskController.kt`:
- import に `import kotlinx.coroutines.withTimeoutOrNull` を足す（`import kotlinx.coroutines.launch` の次）。
- `const val FAILED_SCREEN_MS = 5_000L` の次に足す:

```kotlin

/** The longest the device voice may take to say a text (Android R1-02): the engine may never say it is done. */
const val SAY_BASE_MS = 5_000L
const val SAY_PER_CHAR_MS = 300L
fun sayLimitMs(text: String): Long = SAY_BASE_MS + SAY_PER_CHAR_MS * text.length
```
- `val said = scope.async { d.speech.say(BUSY_MESSAGE) }` を `val said = scope.async { say(BUSY_MESSAGE) }` に、`d.speech.say(result.answer)` を `say(result.answer)` に、`    d.speech.say(spokenMessage(reason))`（`fail` の中）を `    say(spokenMessage(reason))` に変える。
- `private fun stopService() {` の直前に足す:

```kotlin
  /** Says the text with the device voice; one that outlasts its limit is stopped, so the ask can end (Android R1-02). */
  private suspend fun say(text: String) {
    if (withTimeoutOrNull(sayLimitMs(text)) { deps.speech.say(text) } == null) {
      deps.log("say_timeout", mapOf("chars" to text.length))
      deps.speech.stop()
    }
  }

```

`audio/TtsSpeech.kt` の `say()` の末尾の `done.await()` を次に置き換える:

```kotlin
    try {
      done.await()
    } finally {
      // Cut short (the caller gave up waiting): nothing may stay in the table for an utterance nobody waits for.
      pending.remove(id)
    }
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`
Expected: 全件通る（734件）。

- [ ] **Step 5: コミットする**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/audio/TtsSpeech.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
git commit -m "fix: stop the device voice when it outlasts its limit, so a silent engine cannot hold an ask in SPEAKING for good (R1-02)"
```

---

### Task 5: 声の質問と文字の質問の入口・本文・後始末をまとめる（R10-06）

**Files:**
- Modify: `Android/app/src/main/java/com/touringproject/v2/ask/AskController.kt`

**Interfaces:**
- Produces（private）: `Entry(rideId, api, settings)`・`enter(run, refused, extra): Entry?`・`endRun(run)`・`askBody(rideId, here, heading, audio, text)`。

完了の判定: 既存の `AskControllerTest` の声と文字のケースが変更なく通る。入口の確かめは `enter` の1か所。

- [ ] **Step 1: 実装する**

`ask/AskController.kt`:

1. `run()` の `try {` の直後から `val recording = record(run, atStart) ?: return` の手前まで（ride の確かめから `serviceRunning = true` まで）を次に置き換える:

```kotlin
      val entry = enter(run) {
        if (!d.micAllowed()) {
          fail(FailureReason.MIC, run)
          false
        } else {
          isCurrent(run)
        }
      } ?: return
      val (rideId, api, settings) = entry
```
2. `run()` の `finally { ... }` の中身を `endRun(run)` の1行にする（`// A newer ask (or a cancel) owns...` のコメントと `if (isCurrent(run)) {...}` を消す）。
3. `runText()` の `try {` の直後から `val here = d.location.latest()` の手前まで（ride・key・online・settings・api・service）を次に置き換える:

```kotlin
      val entry = enter(run, refused = { tell(TextAskOutcome.NOT_TAKEN) }) {
        if (!d.online()) {
          tell(TextAskOutcome.OFFLINE)
          false
        } else {
          true
        }
      } ?: return
      val (rideId, api, settings) = entry
```
4. `runText()` の `finally` の `tell(TextAskOutcome.NOT_TAKEN)` の次の `if (isCurrent(run)) {...}` を `endRun(run)` にする。
5. `runText()` の閉じ括弧の直後（`sendText` の前）に足す:

```kotlin

  /** What both kinds of ask need to go on: the recording ride, the client for the key, the settings of the moment. */
  private data class Entry(val rideId: String, val api: AskApi, val settings: Settings)

  /**
   * The entry both kinds of ask share (Android R10-06): the ride, the key, whatever else the kind needs (extra, which
   * tells and fails by itself and answers false to stop), and the foreground service. null: the ask is not taken, and
   * the failure is shown if there is one. refused is told first for a failure that is shown.
   */
  private suspend fun enter(run: Run, refused: () -> Unit = {}, extra: suspend () -> Boolean): Entry? {
    val d = deps
    // Slice 2 spec §4.7: only a recording ride takes asks. Read once, so pausing meanwhile neither stops the ask nor
    // takes it out of the ride.
    val ride = d.ride()
    refusal(ride)?.let {
      refused()
      fail(it, run)
      return null
    }
    val rideId = (ride as RideNow.Recording).rideId
    val apiKey = d.apiKey()
    if (apiKey == null) {
      refused()
      fail(FailureReason.NO_KEY, run)
      return null
    }
    if (!extra()) return null
    val settings = d.settings()
    val api = d.api(apiKey, settings.userName)
    try {
      d.service.start()
    } catch (e: Exception) {
      // Without the foreground service the ask would stall once the screen is off; say so instead.
      d.log("service_failed", mapOf("error" to e.toString()))
      refused()
      fail(FailureReason.SERVICE, run)
      return null
    }
    serviceRunning = true
    return Entry(rideId, api, settings)
  }

  /** A newer ask (or a cancel) owns the screen state and the foreground service; leave both to it. */
  private fun endRun(run: Run) {
    if (!isCurrent(run)) return
    current = null
    dispatch(FlowEvent.Dismiss(deps.now()))
    stopService()
  }

  /** The body of an ask to the Backend, voice or text alike. */
  private fun askBody(rideId: String, here: Fix?, heading: Double?, audio: String? = null, text: String? = null) = AskBody(
    volumeDb = deps.settings().answerVolumeDb,
    audio = audio,
    text = text,
    location = here?.let { Point(it.latitude, it.longitude) },
    headingDegrees = heading,
    conversationId = deps.conversation.current(deps.now()),
    rideId = rideId,
  )
```
6. `sendText` の `val body = AskBody(...)`（`volumeDb`・`text`・`location`・`headingDegrees`・`conversationId`・`rideId` を並べた8行）を `val body = askBody(rideId, here, heading, text = text)` にする。
7. `send` の `val body = AskBody(...)` を `val body = askBody(rideId, here, recording.heading, audio = recording.audio)` にする。

- [ ] **Step 2: 通ることを確かめる**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`
Expected: 全件通る（734件）。`AskControllerTest` の既存のテストは変更なしで通る。

- [ ] **Step 3: コミットする**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/ask/AskController.kt
git commit -m "refactor: share the entry checks, the ask body and the run's end between voice and text asks (R10-06)"
```

---

### Task 6: 文書と版

**Files:**
- Modify: `Android/README.md`
- Modify: `Android/app/build.gradle.kts`
- （`docs/08a_android-design.md` は plan のコミットで書いてある）

- [ ] **Step 1: README を直す**

`Android/README.md`:

1. SC-19 の声の入力の項の `その下の `AudioRoute` はアプリに1つなので、…… `busy` で、押下の行き先は質問を始めない。` を次に置き換える（`` `attach` は札を返し、…`` 以降は今のまま）:

```
その下の `AudioRoute` はアプリに1つで、`RouteLeases` が質問・試し録り・声の入力に1度に1人ずつ貸す。SC-19 を離れたら、経路の準備ごと取り消して（準備中の取り消しは `AudioRoute` がその場で元に戻す）経路を返す。返しきるまでの一瞬だけ `busy` で、その間の押下は失敗の合図を鳴らす。
```

2. 録音の確認（SC-12）の項の `SC-12 を離れた試し録りが片付くまで（経路の準備で最大3秒）、インカムの押下と「押して話す」は何も始めない（片付けの経路の解放が質問の経路を壊すため）。試し録りは `voice.busy` を見ていない。` を次に置き換える:

```
SC-12 を離れた試し録りは、経路の準備ごと取り消されてすぐ経路を返す。その間に始まった質問は、返されるのを `RouteLeases` の中で待つ（`PressRouter` は何も止めない）。
```

3. `location/` の行の `質問の位置の窓口（`Positions.kt`）` を `質問の位置の窓口（`Positions.kt`。`begin()` が札を返し、`end(札)` はその札のときだけ効く。取り消した質問の後始末が次の質問の監視を止めないため）` にする。

4. 「大事な決まり」の項（`インカムは音の出だしを落とす` の前）に1項目足す:

```
- 音声の経路（`AudioRoute`）はアプリに1つ。質問（`AskController`）・試し録り（`TrialController`）・声の入力（`VoiceInput`）は `RouteControl.lease` で借り、`RouteLease.release` で返す（`RouteLeases`）。前の持ち主が返すまで次の `lease` は待ち、8秒たっても返らなければ `RouteBusyException` で、本体のマイクで録る。`release` は最初の1回だけ効くので、取り消した処理の後始末が次の持ち主の経路を返すことはない。取り消した処理の経路の準備は `LeaseRequest.callOff` で呼び止める（`AskController.cancel`・`TrialController.cancel`）。
- 端末の音声合成（`TtsSpeech`）は終わりを知らせないことがあるので、`AskController` は読み上げに文字数×300ms＋5秒の上限（`sayLimitMs`）を付け、切れたら止めて先へ進む。
```

- [ ] **Step 2: 08a と写し**

`docs/08a_android-design.md` の音声の経路の札の記述は、plan をコミットしたときに書いてある（plan で決めた部品の分け方）。実装で変わったところがあれば直し、`scripts/sync-docs.sh Android Backend Agent CICD` で写す。

- [ ] **Step 3: 版を上げる**

`Android/app/build.gradle.kts` の `versionCode = 16` を `versionCode = 17` に、`versionName = "0.14.1"` を `versionName = "0.14.2"` にする。

- [ ] **Step 4: 写して、通ることを確かめて、コミットする**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2
scripts/sync-docs.sh Android Backend Agent CICD
cd Android
./gradlew clean testDebugUnitTest && ./gradlew assembleDebug
git add README.md app/build.gradle.kts docs-parent
git commit -m "chore: raise the version to 0.14.2 and describe the route lease in the README"
```
Backend・Agent・CICD の `docs-parent` の写しは、それぞれのユニットの `main` に直接コミットする（これまでの写しと同じ）。

---

### Task 7: 実機の確かめと PROJECT.md

**Files:**
- Modify: `PROJECT.md`

- [ ] **Step 1: 最終レビュー（新しい文脈で）**

`superpowers:executing-plans` の手順どおり、ブランチ全体を最も高性能なモデルの別のレビュアーに見せる。Critical・Important は1回の修正で直す（再現テストを先に書く）。Minor は GitHub issue（`h-akira/TouringProjectV2_Android`）に書く。

- [ ] **Step 2: 実機の確かめを利用者に頼む**

`app-debug.apk`（0.14.2）を実機に入れてもらい、次を確かめてもらう。結果は PROJECT.md に書く。

1. 走行の記録中に、インカムのボタンで質問を始め、準備のあいだ（録音の合図の前）に画面の大きなボタンで取り消し、すぐインカムのボタンをもう一度押す。→ 2回目の質問が、ヘルメットの声で録音され、位置が付く（地図に出る）。
2. 走行の記録中に、SC-19 を開いて「🎤 声で入力」を押し、すぐ SC-19 を閉じて、インカムのボタンで質問する。→ 質問が普通に始まる。
3. SC-12 で試し録りを押し、すぐ画面を離れ、インカムのボタンで質問する。→ 質問が普通に始まる。
4. 回答の音声を再生できない状態（機内モードで回答を取りにいく、など）で端末の読み上げに落ちても、質問が終わり、次のボタンが効く（再現しにくい。見つかれば）。

- [ ] **Step 3: PROJECT.md を更新する**

plan 表の plan 4 の行を、実機の結果に合わせて「✅ 完了」か「実装済み（確認待ち: 実機）」にし、持ち越し（Rulings・後回しの指摘）を書く。「次にやること」を plan 5（Android: 記録の持ち主と未送信の条件）の範囲決めにする。

- [ ] **Step 4: ledger を消し、コミットする**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2
git add PROJECT.md docs
git commit -m "docs: record slice 6 plan 4 as done"
```
（この plan の workspace `.superpowers/sdd/2026-10-30-slice6-plan4-audio-route-lease` は、最終レビューが済んだあとで消す。）
