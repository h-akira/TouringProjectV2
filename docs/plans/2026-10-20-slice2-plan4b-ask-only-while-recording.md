# スライス2 計画4b: 質問は走行の記録中だけ受ける 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 質問は走行の記録中だけ受ける。走行していないとき・一時停止中にインカムのボタンを押すと、録音を始めず、受けないことを声で知らせる。ホームの「押して話す」はそのあいだ押せない形にして、理由を出す。端末と DynamoDB から、走行に結びつかない質問を消す。あわせて、plan 4a の後回しの指摘（Android #41・#42・#43・#45・#46）を直す。

**Architecture:** 受けるかどうかは、一巡の司令塔（`AskController.run`）の入口で、走行の状態（`RideNow`: 記録中とその id・一時停止中・記録していない）を見て決める。受けないときは、今の失敗（接続キーが無いときなど）と同じ流れ（合図・読み上げ・ナビへ戻る）を、新しい失敗の理由 `NOT_RECORDING`・`PAUSED` で通す。`AppGraph` が `RideController` の記録中の走行から `RideNow` を作って渡す。ホームは `askHint`（記録中は null）でボタンと一行の文を変える。端末の質問は Room の版4の Migration で消し、DynamoDB の質問は AWS CLI で一度だけ消す。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版4）・Robolectric 4.16（SDK 35）・MapLibre 13.6.1。足す依存は無い。

**Spec:** [docs/specs/2026-10-17-slice2-design.md](../specs/2026-10-17-slice2-design.md)（§4.6・§4.7・§7.2・§11）。決定の記録は [adr/0008](../../adr/0008-ask-only-while-recording.md)。要件は [04](../04_detailed_requirements.md) の US-B-01.006。

**範囲に入れた issue（Android）:** #41（泊まりがけで翌日に質問の無い走行に日付の見出しが出ない）・#42（記録の一覧をタブの外でも受け続け、長いルートの GeoJSON をメインスレッドで組み立てる）・#43（同じ画面を2回続けて積める）・#45（短い場所の文字が都道府県で始まらない住所を削る）・#46（名前を変えられなかったとき何も知らせない）。

**前提:** Android の `main`（`70dcc8f`。版 0.4.0。plan 4a を含む）の上に作る。親はこの plan を書いたブランチ `slice2-plan4b`（spec と要件の文書の変更のコミットがある）。

**計画を書くときに決めたこと（spec からの具体化。利用者と決めたものを含む）:**
- 質問を受けるのは記録中だけ。一時停止中も受けない。受けないときの読み上げは、走行していないとき「走行を記録していないので、質問できません。」、一時停止中「一時停止中は質問できません。再開すると質問できます。」（利用者と決めた。spec §4.7）。合図（失敗の音）を鳴らし、インカムから始めたときは、戻り先があればナビへ戻す（今の失敗と同じ）。
- 受けるかどうかは、押下を受けた時点で一度だけ決める。始めた質問は、途中で一時停止・終了しても最後まで続け、始めたときの走行に結びつける（今の `rideId` を一度だけ読む作りのまま）。
- 判断の材料は `AskDeps.ride: () -> RideNow`。今の `AskDeps.rideId: () -> String?` を置き換える。`fun rideNow(active: Ride?): RideNow` を `ask/AskPorts.kt` に置く。
- 今の司令塔のテストの作り物（`Harness`）は、既定を「記録中の走行 r1」に変える（受けない場面だけ `RideNow.Paused`・`NotRecording` を渡す）。送り物（`AskBody`）にはいつも `rideId` が付く。
- ホーム: 「押して話す」は記録していないあいだ `enabled = false`。緑の「インカムのボタンで話せます」の一行を、記録していないときは「走行を開始すると、インカムのボタンで話せます」、一時停止中は「再開すると、インカムのボタンで話せます」（淡い色）に差し替える（`askHint`。spec §7.2 の「その下に理由」を、この一行で出す形に具体化した）。走行のカードの文は「走行を記録しているあいだだけ質問できます」「一時停止中は質問できません（再開すると質問できます）」。
- 端末の走行に結びつかない質問は、Room の版を4に上げ、`MIGRATION_3_4` で `DELETE FROM asks WHERE rideId IS NULL` する（走行用のビルドは外から DB に触れないため。利用者と決めた。spec §4.7 を合わせて直した）。表の形は変わらない。新しい版を入れたときに一度だけ走り、知人の端末でも同じになる。
- DynamoDB の走行に結びつかない質問（`sk` が `ASK#` で始まり `rideId` の項目が無いもの）は、Task 10 で AI が AWS CLI で探し、ユーザー名ごとの件数を利用者に見せて、了承を得てから消す（戻せない操作のため）。会話（`CONV#`）・走行・ルートには触れない。
- #42 は重さの直しで、見た目の振る舞いは変わらない。一覧は記録のタブの入口の中で受け、走行の詳細の中身（`rideDetailUi`）と地図の GeoJSON は `Dispatchers.Default` で組み立てる。地図に触る処理（描く・カメラを合わせる）は `withContext(Dispatchers.Main)` で UI スレッドに置く（エミュレーターのテストで、`Default` から戻った先が UI スレッドでない場合があり、MapLibre が `CalledFromWorkerThreadException` を出した）。新しい失敗するテストは作らず、今の画面のテストとエミュレーターの地図のテストで壊れていないことを確かめる。
- #46: `RideDetailScreen.onRename` を `suspend (String) -> Boolean` にし、false のときトースト「名前を変えられませんでした」を出す。
- #43: `TabStacks.push(key)`（一番上と同じなら積まない）を足し、`AppUi` の `tabs.current.add(...)` をすべて置き換える。
- #45: 短い場所は `^(東京都|北海道|(京都|大阪)府|.{2,3}県)` だけを外す。#41: 時系列の日付の見出しは、各区間の始まりと終わりの日付も数える。
- 版を 0.5.0（`versionCode` 6）に上げる。

この計画のコードは、使い捨てのフォルダで、次を確かめてから書いた。

- タスクの順に一つずつコミットし、各タスクのコミットで `clean` から JVM のテストが通る（371件→379件）。各タスクの失敗するテストが先に落ちることも見た。
- 最後に、JVM のテスト379件（始める前の368件＋11件）・エミュレーターのテスト6件・`assembleRelease`・`scripts/check-release-permissions.sh`（15件）が通る。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice2-plan4b` を切る（Task 0）。親は `slice2-plan4b`。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- 作りの決まり（移行の spec §5）: 状態機械と司令塔は Android に依存させない。部品は `AppGraph` で手で組む。走行の状態を変えるのは `RideController` だけ。
- 質問を受けるのは記録中だけ（spec §4.7）。受けないときは録音もサービスも始めない。
- ホームは全体がスクロールしない（spec §7.2）。
- Room のスキーマは版を上げて Migration を書き、`app/schemas/` の JSON をコミットする。破壊的な作り直しは使わない。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。DynamoDB の作業の結果（ユーザー名・件数）はチャットにだけ出す。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --tests '*クラス名'`。テストを確かめるときは `--rerun` を付ける。Kotlin の差分コンパイルは interface の変更を見逃すことがあるので、Task 9 は `./gradlew clean` から回す。
- Room のスキーマの版を新しく足した直後の1回目は「Missing file 4.json」で落ち、2回目で通る（Task 2）。
- `ScreensTest.kt` の中のクラスは `HomeScreenTest` などなので、クラスの名前で指す。
- Robolectric の決まり（SDK 35・`withContext(Dispatchers.Main)` を Robolectric のテストから直に呼ばない（地図の部品は Robolectric では動かさない）・`@Config(qualifiers)` で画面を大きくしない）。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。テストのあいだは利用者にエミュレーターに触らないよう頼む。
- AWS は `AWS_PROFILE=touring`・リージョン `ap-northeast-1`。認証が切れていたら（`UnrecognizedClientException`）利用者に有効にしてもらう。

## Review Focus

- 記録中に質問を始め、録音のあいだに一時停止する → 質問は止まらずに最後まで進み、その走行に入る。Task 1 の `the_ride_is_read_when_the_ask_starts_so_a_pause_meanwhile_neither_stops_nor_drops_it`。
- 走行していないときに、インカムで続けて何度も押す → 毎回すぐに読み上げて戻り、録音・サービス・送信は一度も始まらない。Task 1 の `without_a_recording_ride_the_button_starts_nothing_and_says_so`（1回の押下）と、エミュレーターの `VoiceCommandTest`（押下ごとに一巡が1つ）。
- 一時停止中にホームを見る → 「押して話す」が押せず、「再開すると、インカムのボタンで話せます」が出る。再開すると押せるようになる。Task 3 の `without_a_recording_ride_tap_to_talk_cannot_be_pressed_and_the_hint_says_why`・`the_hint_says_how_to_ask_unless_a_ride_records`。
- 版3から版4へ上げる端末に、走行に結びついた質問と結びつかない質問が混ざっている → 結びつかないものだけが消え、走行の質問は残る。Task 2 の `version_3_moves_to_4_dropping_the_asks_kept_without_a_ride`。
- 長い走行を開く → 地図と時系列が出るまでのあいだも画面が固まらず、地図に触る処理は UI スレッドで行う。Task 7（エミュレーターの `RouteMapTest`）。

---

## ファイル構成（`Android/` から。`...` は `app/src/main/java/com/touringproject/v2`）

| パス | 役割 | Task |
|---|---|---|
| `.../ask/AskPorts.kt`・`ask/Flow.kt`・`ask/Failures.kt`・`ask/AskController.kt`・`AppGraph.kt`・`api/ApiClient.kt` | 質問を記録中だけ受ける（`RideNow`・失敗の理由と読み上げ） | 1 |
| `.../store/RideDatabase.kt`・`app/schemas/.../4.json` | 版4で走行に結びつかない質問を消す | 2 |
| `.../ui/RideLabels.kt`・`ui/HomeScreen.kt`・`ui/RideScreens.kt`・`ui/AppUi.kt` | ホームの「押して話す」と理由の一行・走行のカードの文 | 3 |
| `.../ui/RecordLabels.kt` | #41・#45 | 4 |
| `.../ui/Tabs.kt`・`ui/AppUi.kt` | #43 | 5 |
| `.../ui/RecordsScreens.kt`・`ui/RecordsRoutes.kt` | #46 | 6 |
| `.../ui/AppUi.kt`・`ui/RecordsRoutes.kt`・`map/RouteMap.kt` | #42 | 7 |
| `app/build.gradle.kts`・`README.md`・`docs-parent/` | 版 0.5.0・文書・親の文書の写し | 8 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android に `slice2-plan4b` を切り、始める前のテストの件数を見る**

```bash
cd $ROOT && git branch --show-current          # slice2-plan4b
cd $AND && git switch main && git pull --ff-only && git switch -c slice2-plan4b
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-base.log 2>&1; tail -3 /tmp/trv2-base.log
```

Expected: `BUILD SUCCESSFUL`。結果のファイルの件数の合計は368件。

---
### Task 1: 質問を記録中だけ受ける

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ask/AskPorts.kt`・`app/src/main/java/com/touringproject/v2/ask/Flow.kt`・`app/src/main/java/com/touringproject/v2/ask/Failures.kt`・`app/src/main/java/com/touringproject/v2/ask/AskController.kt`・`app/src/main/java/com/touringproject/v2/AppGraph.kt`・`app/src/main/java/com/touringproject/v2/api/ApiClient.kt`（コメント）・`app/src/androidTest/java/com/touringproject/v2/VoiceCommandTest.kt`（コメント）
- Test: `app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt`

**Interfaces:**
- Produces: `sealed interface RideNow { data class Recording(val rideId: String); data object Paused; data object NotRecording }`・`fun rideNow(active: Ride?): RideNow`・`AskDeps.ride: () -> RideNow`（`AskDeps.rideId` は消す）・`FailureReason.NOT_RECORDING`・`FailureReason.PAUSED` と、それぞれの読み上げ（`spokenMessage`）。

- [ ] **Step 1: 失敗するテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index 1fa0167..b30dce8 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -12,6 +12,9 @@ import com.touringproject.v2.api.Point
 import com.touringproject.v2.audio.InputDevice
 import com.touringproject.v2.audio.MediaVolume
 import com.touringproject.v2.location.Fix
+import com.touringproject.v2.ride.HOUR_MS
+import com.touringproject.v2.ride.newRide
+import com.touringproject.v2.ride.pause
 import com.touringproject.v2.settings.LaunchableApp
 import com.touringproject.v2.settings.ReturnTiming
 import com.touringproject.v2.settings.Settings
@@ -57,7 +60,8 @@ private class Harness(
   val serviceError: Exception? = null,
   val device: InputDevice? = InputDevice(InputDevice.Type.BLUETOOTH, "M1-S PRO"),
   val pcm: ByteArray = byteArrayOf(1, 2, 3),
-  var rideId: String? = null,
+  /** Asks start only while a ride records (slice 2 spec §4.7); most tests ride. */
+  var ride: RideNow = RideNow.Recording("r1"),
 ) {
   val log = mutableListOf<String>()
   val states = mutableListOf<FlowState>()
@@ -112,7 +116,7 @@ private class Harness(
       override fun transcribed(name: String, transcript: String) { transcripts += name to transcript }
     },
     asks = { kept += it },
-    rideId = { rideId },
+    ride = { ride },
     location = object : Positions {
       override fun begin() { log += "loc:begin" }
       override fun end() = HERE to listOf(BEHIND, HERE)
@@ -178,6 +182,7 @@ class AskControllerTest {
         location = Point(35.6812, 139.7671),
         headingSample = HeadingSample(35.6806, 139.7671, "1970-01-01T00:01:30Z"),
         conversationId = null,
+        rideId = "r1",
       ),
       h.bodies[0],
     )
@@ -542,7 +547,7 @@ class AskControllerTest {
     assertEquals(HERE.latitude, kept.latitude!!, 0.0)
     assertEquals("c1", kept.conversationId)
     assertTrue(kept.newConversation)
-    assertEquals(null, kept.rideId)
+    assertEquals("r1", kept.rideId)
   }
 
   @Test
@@ -589,20 +594,39 @@ class AskControllerTest {
 
   @Test
   fun an_ask_started_while_a_ride_records_goes_with_the_ride() = runTest {
-    val h = Harness(this, stopAfterMs = 1_000, rideId = "r1")
+    val h = Harness(this, stopAfterMs = 1_000, ride = RideNow.Recording("r7"))
     h.controller.run(Source.HANDSFREE)
-    assertEquals("r1", h.bodies.single().rideId)
-    assertEquals("r1", h.kept.single().rideId)
+    assertEquals("r7", h.bodies.single().rideId)
+    assertEquals("r7", h.kept.single().rideId)
   }
 
   @Test
-  fun the_ride_is_read_when_the_ask_starts_so_a_pause_meanwhile_does_not_drop_it() = runTest {
-    val h = Harness(this, stopAfterMs = 1_000, rideId = "r1")
+  fun the_ride_is_read_when_the_ask_starts_so_a_pause_meanwhile_neither_stops_nor_drops_it() = runTest {
+    val h = Harness(this, stopAfterMs = 1_000)
     launch { h.controller.run(Source.HANDSFREE) }
     h.until { h.phase == Phase.RECORDING }
-    h.rideId = null
+    h.ride = RideNow.Paused
     advanceUntilIdle()
     assertEquals("r1", h.bodies.single().rideId)
+    assertEquals(AskOutcome.ANSWERED, h.kept.single().outcome)
+  }
+
+  // Slice 2 spec §4.7: no ride recording, no ask. The rider hears why, and the nav app comes back as after any failure.
+  @Test
+  fun without_a_recording_ride_the_button_starts_nothing_and_says_so() = runTest {
+    val h = Harness(this, ride = RideNow.NotRecording)
+    h.controller.run(Source.HANDSFREE)
+    assertEquals(listOf("vol:read", "cue:failure", "say:走行を記録していないので、質問できません。", "return:maps"), h.log)
+    assertTrue(h.states.any { it.phase == Phase.FAILED && it.failure == FailureReason.NOT_RECORDING })
+    assertTrue(h.kept.isEmpty())
+  }
+
+  @Test
+  fun while_the_ride_is_paused_the_button_starts_nothing_and_says_how_to_ask() = runTest {
+    val h = Harness(this, ride = RideNow.Paused)
+    h.controller.run(Source.HANDSFREE)
+    assertEquals(listOf("vol:read", "cue:failure", "say:一時停止中は質問できません。再開すると質問できます。", "return:maps"), h.log)
+    assertTrue(h.states.any { it.phase == Phase.FAILED && it.failure == FailureReason.PAUSED })
   }
 }
 
@@ -627,3 +651,14 @@ class AskRecordTest {
     assertEquals("agent_failed", failed.failure)
   }
 }
+
+class RideNowTest {
+  private val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)
+
+  @Test
+  fun only_a_recording_ride_takes_asks() {
+    assertEquals(RideNow.Recording("r1"), rideNow(ride))
+    assertEquals(RideNow.Paused, rideNow(ride.pause(5_000)))
+    assertEquals(RideNow.NotRecording, rideNow(null))
+  }
+}
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AskControllerTest'`
Expected: コンパイルの失敗（`Unresolved reference 'RideNow'`・`No parameter with name 'ride' found`）。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/androidTest/java/com/touringproject/v2/VoiceCommandTest.kt b/app/src/androidTest/java/com/touringproject/v2/VoiceCommandTest.kt
index bd7d9f9..214dd49 100644
--- a/app/src/androidTest/java/com/touringproject/v2/VoiceCommandTest.kt
+++ b/app/src/androidTest/java/com/touringproject/v2/VoiceCommandTest.kt
@@ -17,7 +17,7 @@ import org.junit.Test
 import org.junit.runner.RunWith
 
 // On the emulator: the intercom's assistant button arrives as VOICE_COMMAND and starts exactly one ask
-// (4a #1 and 4b #9 of the slice 1 checklist). Without an API key the ask ends at once with "no key".
+// (4a #1 and 4b #9 of the slice 1 checklist). With no ride recording the ask ends at once and says so (slice 2 spec §4.7).
 // MainActivity is singleTask, which ActivityScenario cannot follow, so the activity is started directly.
 @RunWith(AndroidJUnit4::class)
 class VoiceCommandTest {
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 8fe6ae3..b346413 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -12,6 +12,7 @@ import com.touringproject.v2.ask.ConversationState
 import com.touringproject.v2.ask.FlowState
 import com.touringproject.v2.ask.IDLE
 import com.touringproject.v2.ask.isBusy
+import com.touringproject.v2.ask.rideNow
 import com.touringproject.v2.audio.AudioRoute
 import com.touringproject.v2.audio.AudioRouteControl
 import com.touringproject.v2.audio.ExoAnswerPlayer
@@ -143,7 +144,7 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       recorder = PcmRecorder(),
       recordings = RecordingKeeper(recordingStore, scope) { message, e -> Log.w("trv2.recordings", message, e) },
       asks = askLog,
-      rideId = { rides.active.value?.takeIf { it.status == RideStatus.RECORDING }?.id },
+      ride = { rideNow(rides.active.value) },
       location = PositionTracker(FusedPositionSource(context)),
       service = serviceCoordinator.keepAlive,
       nav = launcher,
diff --git a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
index 37b208f..9499d85 100644
--- a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
+++ b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
@@ -32,7 +32,7 @@ data class AskBody(
   val headingSample: HeadingSample? = null,
   val conversationId: String? = null,
   val volumeDb: Int? = null,
-  /** Only for an ask started while a ride is recording (slice 2 spec §4.6). */
+  /** The recording ride the ask belongs to; every ask has one since asks need a recording ride (slice 2 spec §4.7). */
   val rideId: String? = null,
 )
 
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index c6623a9..56e5d6c 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -96,6 +96,19 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     runsStarted += 1
     dispatch(FlowEvent.Start(source, d.now(), d.mediaVolume()))
     try {
+      // Slice 2 spec §4.7: only a recording ride takes asks. Read once, so pausing meanwhile neither stops the ask nor
+      // takes it out of the ride.
+      val rideId = when (val ride = d.ride()) {
+        is RideNow.Recording -> ride.rideId
+        RideNow.Paused -> {
+          fail(FailureReason.PAUSED, run)
+          return
+        }
+        RideNow.NotRecording -> {
+          fail(FailureReason.NOT_RECORDING, run)
+          return
+        }
+      }
       val apiKey = d.apiKey()
       if (apiKey == null) {
         fail(FailureReason.NO_KEY, run)
@@ -117,8 +130,6 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
         return
       }
       serviceRunning = true
-      // Read when the ask starts: pausing while it waits does not take it out of the ride.
-      val rideId = d.rideId()
       val recording = record(run) ?: return
       val sent = send(recording, rideId, api, run) ?: return
       maybeReturn(ReturnTiming.SENT, settings, run)
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
index d79bf16..be387ee 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
@@ -1,5 +1,7 @@
 package com.touringproject.v2.ask
 
+import com.touringproject.v2.ride.Ride
+import com.touringproject.v2.ride.RideStatus
 import com.touringproject.v2.api.AskApi
 import com.touringproject.v2.audio.InputDevice
 import com.touringproject.v2.audio.MediaVolume
@@ -81,6 +83,19 @@ interface Speech {
   fun stop()
 }
 
+/** Where the rider's ride stands when an ask is asked for (slice 2 spec §4.7). */
+sealed interface RideNow {
+  data class Recording(val rideId: String) : RideNow
+  data object Paused : RideNow
+  data object NotRecording : RideNow
+}
+
+fun rideNow(active: Ride?): RideNow = when {
+  active == null || active.status == RideStatus.ENDED -> RideNow.NotRecording
+  active.status == RideStatus.PAUSED -> RideNow.Paused
+  else -> RideNow.Recording(active.id)
+}
+
 class AskDeps(
   val now: () -> Long,
   val sleep: suspend (Long) -> Unit,
@@ -95,8 +110,8 @@ class AskDeps(
   val recordings: RecordingSink,
   /** Where the asks that reached the Backend are kept (slice 2 spec §5.2). */
   val asks: AskLog,
-  /** The id of the ride that is recording now, or null (paused or none: slice 2 spec §4.6). */
-  val rideId: () -> String?,
+  /** Whether a ride is recording now: an ask starts only then (slice 2 spec §4.7). */
+  val ride: () -> RideNow,
   val location: Positions,
   val service: KeepAlive,
   val nav: NavReturn,
diff --git a/app/src/main/java/com/touringproject/v2/ask/Failures.kt b/app/src/main/java/com/touringproject/v2/ask/Failures.kt
index a834257..b2d845e 100644
--- a/app/src/main/java/com/touringproject/v2/ask/Failures.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/Failures.kt
@@ -11,6 +11,8 @@ fun spokenMessage(reason: FailureReason): String = when (reason) {
   FailureReason.INVALID_KEY, FailureReason.NO_KEY -> "接続キーを確かめてください。"
   FailureReason.MIC -> "録音できませんでした。"
   FailureReason.SERVICE -> "準備できなかったため、質問できませんでした。もう一度お試しください。"
+  FailureReason.NOT_RECORDING -> "走行を記録していないので、質問できません。"
+  FailureReason.PAUSED -> "一時停止中は質問できません。再開すると質問できます。"
 }
 
 private val SERVER_REASONS = mapOf(
diff --git a/app/src/main/java/com/touringproject/v2/ask/Flow.kt b/app/src/main/java/com/touringproject/v2/ask/Flow.kt
index 18df2e3..2ae98b0 100644
--- a/app/src/main/java/com/touringproject/v2/ask/Flow.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/Flow.kt
@@ -9,7 +9,8 @@ enum class Source { HANDSFREE, SCREEN }
 
 enum class Phase { IDLE, RECORDING, SENDING, WAITING, SPEAKING, FAILED }
 
-enum class FailureReason { NO_SPEECH, TRANSCRIBE_FAILED, AGENT_FAILED, TTS_FAILED, TIMEOUT, NETWORK, INVALID_KEY, NO_KEY, MIC, SERVICE }
+/** NOT_RECORDING and PAUSED: the ask was not taken, as only a recording ride takes asks (slice 2 spec §4.7). */
+enum class FailureReason { NO_SPEECH, TRANSCRIBE_FAILED, AGENT_FAILED, TTS_FAILED, TIMEOUT, NETWORK, INVALID_KEY, NO_KEY, MIC, SERVICE, NOT_RECORDING, PAUSED }
 
 data class FlowState(
   val phase: Phase = Phase.IDLE,
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*.ask.*' --tests '*MainActivityTest' --tests '*AppUiTest' --rerun`
Expected: `AskControllerTest` 44件・`RideNowTest` 1件を含む `ask` のテストと、`MainActivityTest` 4件・`AppUiTest` 7件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/ask/Flow.kt \
  app/src/main/java/com/touringproject/v2/ask/Failures.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt \
  app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/api/ApiClient.kt \
  app/src/androidTest/java/com/touringproject/v2/VoiceCommandTest.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
git commit -m "feat: take asks only while a ride records and say why otherwise"
```

---

### Task 2: 走行に結びつかない質問を端末から消す（版4）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/store/RideDatabase.kt`
- Create（生成）: `app/schemas/com.touringproject.v2.store.RideDatabase/4.json`
- Test: `app/src/test/java/com/touringproject/v2/store/MigrationTest.kt`

**Interfaces:**
- Produces: `MIGRATION_3_4`・`RideDatabase` の版4（表の形は変わらない）。

- [ ] **Step 1: 失敗するテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt b/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
index a60eaf3..e3960e1 100644
--- a/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
@@ -30,7 +30,7 @@ class MigrationTest {
     }
     helper.runMigrationsAndValidate(DB, 2, true, MIGRATION_1_2).close()
     val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
-      .addMigrations(MIGRATION_1_2, MIGRATION_2_3)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
       .allowMainThreadQueries()
       .build()
     runBlocking {
@@ -56,7 +56,7 @@ class MigrationTest {
     }
     helper.runMigrationsAndValidate(DB, 3, true, MIGRATION_2_3).close()
     val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
-      .addMigrations(MIGRATION_1_2, MIGRATION_2_3)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
       .allowMainThreadQueries()
       .build()
     runBlocking {
@@ -65,4 +65,26 @@ class MigrationTest {
     }
     db.close()
   }
+
+  // Slice 2 spec §4.7 (adr/0008): asks are taken only while a ride records, and the ones kept without a ride go.
+  @Test
+  fun version_3_moves_to_4_dropping_the_asks_kept_without_a_ride() {
+    helper.createDatabase(DB, 3).apply {
+      execSQL("INSERT INTO rides VALUES ('r1', '箱根', 'ended', 'manual', NULL, 5000, 120.0, 6000, 6000, NULL, 0)")
+      val columns = "(askId, askedAt, answeredAt, transcript, answer, latitude, longitude, address, headingDegrees, input, conversationId, newConversation, status, failure, rideId)"
+      execSQL("INSERT INTO asks $columns VALUES ('a1', 1000, 2000, 'Q', 'A', 35.0, 139.0, '箱根町', 90.0, 'voice', 'c1', 1, 'answered', NULL, 'r1')")
+      execSQL("INSERT INTO asks $columns VALUES ('a2', 3000, 4000, 'Q', 'A', 35.0, 139.0, '箱根町', 90.0, 'voice', 'c1', 0, 'answered', NULL, NULL)")
+      close()
+    }
+    helper.runMigrationsAndValidate(DB, 4, true, MIGRATION_3_4).close()
+    val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
+      .allowMainThreadQueries()
+      .build()
+    runBlocking {
+      assertEquals("r1", db.asks().ask("a1")?.rideId)
+      assertNull(db.asks().ask("a2"))
+    }
+    db.close()
+  }
 }
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*MigrationTest'`
Expected: コンパイルの失敗（`Unresolved reference 'MIGRATION_3_4'`）。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 800a19b..dea6b9a 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -96,7 +96,11 @@ data class AskEntity(
   val status: String,
   /** no_speech / transcribe_failed / agent_failed / tts_failed / timeout; null when answered */
   val failure: String?,
-  /** The ride that was recording when the ask started; null when none was. Not a foreign key: a ride's row may be missing for a while after a failed save. */
+  /**
+   * The ride that was recording when the ask started. Asks need a recording ride since version 4 (slice 2 spec §4.7), so
+   * it is set on every ask; the column stays nullable for the API's sake. Not a foreign key: a ride's row may be
+   * missing for a while after a failed save.
+   */
   val rideId: String?,
 )
 
@@ -228,14 +232,14 @@ interface RideDao {
   }
 }
 
-@Database(entities = [RideEntity::class, SegmentEntity::class, RoutePointEntity::class, AskEntity::class], version = 3, exportSchema = true)
+@Database(entities = [RideEntity::class, SegmentEntity::class, RoutePointEntity::class, AskEntity::class], version = 4, exportSchema = true)
 abstract class RideDatabase : RoomDatabase() {
   abstract fun rides(): RideDao
   abstract fun asks(): AskDao
 
   companion object {
     fun open(context: Context): RideDatabase =
-      Room.databaseBuilder(context, RideDatabase::class.java, "rides.db").addMigrations(MIGRATION_1_2, MIGRATION_2_3).build()
+      Room.databaseBuilder(context, RideDatabase::class.java, "rides.db").addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4).build()
   }
 }
 
@@ -272,3 +276,13 @@ val MIGRATION_2_3 = object : Migration(2, 3) {
     db.execSQL("CREATE INDEX IF NOT EXISTS `index_route_points_refused_rideId` ON `route_points` (`refused`, `rideId`)")
   }
 }
+
+/**
+ * 3 -> 4 (slice 2 plan 4b, adr/0008): asks are taken only while a ride records, and the asks kept without a ride (the
+ * test asks of development) go. The schema itself does not change.
+ */
+val MIGRATION_3_4 = object : Migration(3, 4) {
+  override fun migrate(db: SupportSQLiteDatabase) {
+    db.execSQL("DELETE FROM `asks` WHERE `rideId` IS NULL")
+  }
+}
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*.store.*' --rerun` を2回。
Expected: 1回目は「Missing file 4.json」で落ちる。2回目は `MigrationTest` 3件を含む19件が通る。`app/schemas/com.touringproject.v2.store.RideDatabase/4.json` ができている。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/schemas/com.touringproject.v2.store.RideDatabase/4.json \
  app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
git commit -m "feat: drop the asks kept without a ride when the database moves to version 4"
```

---

### Task 3: ホームの「押して話す」と理由の一行・走行のカードの文

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/RideLabels.kt`・`app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt`・`app/src/main/java/com/touringproject/v2/ui/RideScreens.kt`・`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt`・`app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt`（`HomeScreenTest`）・`app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt`・`app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt`

**Interfaces:**
- Consumes: 既存の `Ride`・`RideStatus`。
- Produces: `fun askHint(ride: Ride?): String?`（記録中は null）・`HomeUi.askHint: String? = null`。テストのタグ `askHint`。

- [ ] **Step 1: 失敗するテストを書く**

`AppUiTest` の「質問のあいだはタブの帯が隠れる」は、画面のボタンが押せなくなるので、インカムの押下（`controller.press()`）で確かめる形に変える（走行していないので「質問できません」の失敗の画面が出て、帯が隠れる）。

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
index 6cfd172..3f7395b 100644
--- a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
@@ -87,10 +87,12 @@ class AppUiTest {
     assertFalse(rule.activity.onBackPressedDispatcher.hasEnabledCallbacks())
   }
 
-  // Android #36: the ask screen covers the tabs. Without a connection key the ask fails at once and says so.
+  // Android #36: the ask screen covers the tabs. Without a recording ride the intercom press fails at once and says so
+  // (slice 2 spec §4.7).
   @Test
   fun the_tabs_hide_while_an_ask_is_on_screen() {
-    rule.onNodeWithTag("tapToTalk").performClick()
+    val graph = (rule.activity.application as TouringApp).graph
+    rule.runOnUiThread { graph.controller.press() }
     rule.waitUntil(5_000) { !rule.onAllNodesWithTagExists("tab-HOME") }
   }
 
diff --git a/app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt
index 2aab356..2ca0217 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt
@@ -15,6 +15,15 @@ private val TOKYO = ZoneId.of("Asia/Tokyo")
 private fun at(day: Int, hour: Int, minute: Int) = ZonedDateTime.of(2026, 10, day, hour, minute, 0, 0, TOKYO).toInstant().toEpochMilli()
 
 class RideLabelsTest {
+  // Slice 2 spec §4.7, §7.2
+  @Test
+  fun the_hint_says_how_to_ask_unless_a_ride_records() {
+    val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)
+    assertEquals(null, askHint(ride))
+    assertEquals("再開すると、インカムのボタンで話せます", askHint(ride.pause(5_000)))
+    assertEquals("走行を開始すると、インカムのボタンで話せます", askHint(null))
+  }
+
   @Test
   fun elapsed_and_distance_read_like_the_mock() {
     assertEquals("1:26", elapsedLabel(86 * 60_000L + 59_000))
diff --git a/app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt
index 6864e55..301ddab 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt
@@ -35,7 +35,7 @@ class RideScreensTest {
   fun without_a_ride_the_card_offers_to_start_one() {
     var starts = 0
     rule.setContent { RideCard(null, { starts++ }, {}, {}, {}) }
-    rule.onNodeWithText("記録しなくても質問できます（日ごとの記録に残ります）").assertExists()
+    rule.onNodeWithText("走行を記録しているあいだだけ質問できます").assertExists()
     rule.onNodeWithTag("startRide").performClick()
     assertEquals(1, starts)
   }
@@ -69,7 +69,7 @@ class RideScreensTest {
   fun a_paused_ride_says_its_questions_are_not_recorded_and_can_resume() {
     var resumes = 0
     rule.setContent { RideCard(RideCardUi("箱根", true, "1:26", "52.8 km", "4"), {}, {}, { resumes++ }, {}) }
-    rule.onNodeWithText("一時停止中の質問は走行の記録に入りません（日ごとには残ります）").assertExists()
+    rule.onNodeWithText("一時停止中は質問できません（再開すると質問できます）").assertExists()
     rule.onNodeWithText("▶ 再開").performClick()
     assertEquals(1, resumes)
   }
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index c5f265d..143c8e8 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -7,6 +7,8 @@ import androidx.compose.runtime.setValue
 import androidx.compose.ui.test.assertHasNoClickAction
 import androidx.compose.ui.test.assertIsDisplayed
 import androidx.compose.ui.test.assertIsNotEnabled
+import androidx.compose.ui.test.assertIsEnabled
+import androidx.compose.ui.test.assertTextEquals
 import androidx.compose.ui.test.junit4.createComposeRule
 import androidx.compose.ui.test.onNodeWithTag
 import androidx.compose.ui.test.onNodeWithText
@@ -44,6 +46,23 @@ class HomeScreenTest {
     assertEquals(1, taps)
   }
 
+  // Slice 2 spec §4.7: without a recording ride the button stays where it is but cannot be pressed, and says why.
+  @Test
+  fun without_a_recording_ride_tap_to_talk_cannot_be_pressed_and_the_hint_says_why() {
+    var taps = 0
+    rule.setContent { HomeScreen(HomeUi("rider01", null, "新しい会話です", askHint = "再開すると、インカムのボタンで話せます"), { taps++ }, {}, {}, {}) }
+    rule.onNodeWithTag("tapToTalk").assertIsNotEnabled().performClick()
+    assertEquals(0, taps)
+    rule.onNodeWithTag("askHint").assertTextEquals("再開すると、インカムのボタンで話せます")
+  }
+
+  @Test
+  fun while_a_ride_records_the_hint_says_the_intercom_is_ready() {
+    rule.setContent { HomeScreen(HomeUi("rider01", null, "新しい会話です"), {}, {}, {}, {}) }
+    rule.onNodeWithTag("tapToTalk").assertIsEnabled()
+    rule.onNodeWithTag("askHint").assertTextEquals("インカムのボタンで話せます")
+  }
+
   @Test
   fun the_banner_leads_to_its_setting() {
     var opened: Banner? = null
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideLabelsTest'`
Expected: コンパイルの失敗（`Unresolved reference 'askHint'`）。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index fb7652d..03e7383 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -123,6 +123,7 @@ fun AppUi(graph: AppGraph) {
                     storeFailed = storeFailed || askStoreFailed,
                   ),
                   conversation = conversationLabel(expiresAt, System.currentTimeMillis()),
+                  askHint = askHint(ride),
                 )
                 HomeScreen(
                   ui = ui,
diff --git a/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt b/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
index 4630667..e325983 100644
--- a/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
@@ -11,6 +11,7 @@ import androidx.compose.foundation.layout.heightIn
 import androidx.compose.foundation.layout.padding
 import androidx.compose.foundation.shape.RoundedCornerShape
 import androidx.compose.material3.AlertDialog
+import androidx.compose.material3.MaterialTheme
 import androidx.compose.material3.OutlinedButton
 import androidx.compose.material3.Text
 import androidx.compose.material3.TextButton
@@ -35,7 +36,8 @@ import androidx.lifecycle.repeatOnLifecycle
 import com.touringproject.v2.audio.MediaVolume
 import kotlinx.coroutines.delay
 
-data class HomeUi(val userName: String, val banner: Banner?, val conversation: String)
+/** askHint is set while no ask can start (no ride recording: slice 2 spec §4.7); it says how to make one possible. */
+data class HomeUi(val userName: String, val banner: Banner?, val conversation: String, val askHint: String? = null)
 
 const val VOLUME_CHECK_MS = 2_000L
 
@@ -93,14 +95,19 @@ fun HomeScreen(
     Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
       Text(ui.userName, Modifier.clickable(onClick = onUser), fontSize = 22.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
       // Settings is a tab now (slice 2 spec §7.1).
-      OutlinedButton(onClick = onTapToTalk, Modifier.testTag("tapToTalk")) { Text("🎤 押して話す") }
+      OutlinedButton(onClick = onTapToTalk, Modifier.testTag("tapToTalk"), enabled = ui.askHint == null) { Text("🎤 押して話す") }
     }
     ui.banner?.let { banner ->
       val low = banner == Banner.LOW_VOLUME
       WarningBand(banner.text, if (banner.leads) ({ onBanner(banner) }) else null, if (low) onDismissVolume else null, Modifier.testTag("banner"))
     }
     ride()
-    Text("インカムのボタンで話せます", color = Color(0xFF13804A), fontSize = 16.sp)
+    Text(
+      ui.askHint ?: "インカムのボタンで話せます",
+      Modifier.testTag("askHint"),
+      color = if (ui.askHint == null) Color(0xFF13804A) else MaterialTheme.colorScheme.onSurfaceVariant,
+      fontSize = 16.sp,
+    )
     Column(
       Modifier.fillMaxWidth().heightIn(min = 76.dp, max = 140.dp).background(Color(0xFF1F4FD1), RoundedCornerShape(16.dp))
         .clickable { confirming = true }.padding(16.dp).testTag("newConversation"),
diff --git a/app/src/main/java/com/touringproject/v2/ui/RideLabels.kt b/app/src/main/java/com/touringproject/v2/ui/RideLabels.kt
index f81201e..e64d5cb 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RideLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RideLabels.kt
@@ -34,6 +34,16 @@ fun periodLabel(start: Long, end: Long, zone: ZoneId): String {
 fun pausesLabel(pauses: Pauses): String? =
   if (pauses.count == 0) null else "一時停止 ${pauses.count}回（${pauses.totalMs / 60_000}分）は走行時間に含めません"
 
+/**
+ * What Home says under the intercom line when no ask can start (slice 2 spec §4.7, §7.2): null while a ride records,
+ * so the line says the intercom is ready.
+ */
+fun askHint(ride: Ride?): String? = when (ride?.status) {
+  RideStatus.RECORDING -> null
+  RideStatus.PAUSED -> "再開すると、インカムのボタンで話せます"
+  else -> "走行を開始すると、インカムのボタンで話せます"
+}
+
 /** questions is how many of the ride's asks the device has kept (answered or failed; slice 2 spec §7.2). */
 data class RideCardUi(val name: String, val paused: Boolean, val elapsed: String, val distance: String, val questions: String)
 
diff --git a/app/src/main/java/com/touringproject/v2/ui/RideScreens.kt b/app/src/main/java/com/touringproject/v2/ui/RideScreens.kt
index 647a619..c4b44e0 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RideScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RideScreens.kt
@@ -38,7 +38,7 @@ fun RideCard(ride: RideCardUi?, onStart: () -> Unit, onPause: () -> Unit, onResu
   if (ride == null) {
     Column(card, verticalArrangement = Arrangement.spacedBy(8.dp)) {
       Button(onClick = onStart, Modifier.fillMaxWidth().heightIn(min = 60.dp).testTag("startRide")) { Text("▶ 走行を開始", fontSize = 18.sp) }
-      Text("記録しなくても質問できます（日ごとの記録に残ります）", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
+      Text("走行を記録しているあいだだけ質問できます", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
     }
     return
   }
@@ -53,7 +53,7 @@ fun RideCard(ride: RideCardUi?, onStart: () -> Unit, onPause: () -> Unit, onResu
       Stat(ride.distance, "距離", Modifier.testTag("rideDistance"))
       Stat(ride.questions, "質問", Modifier.testTag("rideQuestions"))
     }
-    if (ride.paused) Text("一時停止中の質問は走行の記録に入りません（日ごとには残ります）", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
+    if (ride.paused) Text("一時停止中は質問できません（再開すると質問できます）", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
     Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
       if (ride.paused) Button(onClick = onResume, Modifier.weight(1f)) { Text("▶ 再開") }
       else OutlinedButton(onClick = onPause, Modifier.weight(1f)) { Text("⏸ 一時停止") }
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideLabelsTest' --tests '*HomeScreenTest' --tests '*RideScreensTest' --tests '*AppUiTest' --rerun`
Expected: `RideLabelsTest` 6件・`HomeScreenTest` 8件・`RideScreensTest` 10件・`AppUiTest` 7件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RideLabels.kt app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt \
  app/src/main/java/com/touringproject/v2/ui/RideScreens.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt \
  app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
git commit -m "feat: grey out tap to talk on Home and say how to ask while no ride records"
```

---

### Task 4: 泊まりがけの日付の見出しと、短い場所の文字（#41・#45）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt`

- [ ] **Step 1: 失敗するテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
index f729662..823b98c 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
@@ -129,4 +129,30 @@ class RecordLabelsTest {
     assertEquals("1 · 09:41 · 足柄下郡箱根町仙石原", card.heading)
     assertEquals("金時山です。", card.answer)
   }
+
+  // Android #41: the day after the night has no ask, yet the ride runs over two days.
+  @Test
+  fun an_overnight_ride_without_asks_after_midnight_still_gets_its_day_headings() {
+    val overnight = newRide("r2", "伊豆", ms(16, 15, 0), 7, 48 * HOUR_MS).pause(ms(16, 21, 10)).resume(ms(17, 8, 30), 7, 48 * HOUR_MS)
+      .end(ms(17, 12, 0), EndReason.MANUAL, ms(17, 12, 0))
+    assertEquals(
+      listOf(
+        TimelineRow.Day("10月16日（金）"),
+        TimelineRow.Ask("a1", 1, "16:00", "足柄下郡箱根町仙石原", "右手の山は？", false),
+        TimelineRow.Pause("⏸ 一時停止 21:10〜10月17日 08:30"),
+      ),
+      rideTimeline(overnight, listOf(ask("a1", ms(16, 16, 0))), zone),
+    )
+  }
+
+  // Android #45
+  @Test
+  fun the_short_place_drops_only_a_real_prefecture() {
+    assertEquals("御殿場市", shortPlace("静岡県御殿場市"))
+    assertEquals("札幌市", shortPlace("北海道札幌市"))
+    assertEquals("中央区", shortPlace("東京都中央区"))
+    assertEquals("京都市左京区", shortPlace("京都府京都市左京区"))
+    assertEquals("国道1号線沿い", shortPlace("国道1号線沿い"))
+    assertEquals("場所不明", shortPlace(null))
+  }
 }
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordLabelsTest' --rerun`
Expected: 11件のうち2件が落ちる。`the_short_place_drops_only_a_real_prefecture`（「国道1号線沿い」が「1号線沿い」になる）と `an_overnight_ride_without_asks_after_midnight_still_gets_its_day_headings`（見出しが無い）。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
index 4417aed..7569a9b 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
@@ -125,8 +125,10 @@ fun askPins(asks: List<AskRecord>): List<MapPin> {
   }
 }
 
-/** The mock's short place: the address without its prefecture. */
-fun shortPlace(address: String?): String = address?.replace(Regex("^(東京都|.+?[県府道])"), "")?.ifBlank { null } ?: "場所不明"
+private val PREFECTURE = Regex("^(東京都|北海道|(京都|大阪)府|.{2,3}県)")
+
+/** The mock's short place: the address without its prefecture; an address that starts otherwise is kept whole (Android #45). */
+fun shortPlace(address: String?): String = address?.replace(PREFECTURE, "")?.ifBlank { null } ?: "場所不明"
 
 /** What a list shows of an ask: what was heard, or why nothing was. */
 fun askText(ask: AskRecord): String = ask.transcript?.takeIf { it.isNotBlank() } ?: when {
@@ -167,7 +169,9 @@ fun rideTimeline(ride: Ride, asks: List<AskRecord>, zone: ZoneId): List<Timeline
   val open = if (ride.status == RideStatus.PAUSED) listOfNotNull(ride.segments.last().endedAt?.let { Event.PauseAt(it, null) }) else emptyList()
   // An ask comes before a pause that starts at the same moment.
   val events = (asks.map { Event.AskAt(it.askedAt, it) } + pauses + open).sortedWith(compareBy<Event> { it.t }.thenBy { if (it is Event.AskAt) 0 else 1 })
-  val days = (events.map { it.t } + ride.startedAt()).map { at(it, zone).toLocalDate() }.toSet()
+  // Every day the ride recorded on counts, not only the days with an ask or a pause (Android #41).
+  val recorded = ride.segments.flatMap { listOfNotNull(it.startedAt, it.endedAt) }
+  val days = (events.map { it.t } + recorded).map { at(it, zone).toLocalDate() }.toSet()
   val rows = mutableListOf<TimelineRow>()
   var day: LocalDate? = null
   var asked = false
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordLabelsTest' --rerun`
Expected: 11件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
git commit -m "fix: head every day an overnight ride ran and cut only a real prefecture" -m "Fixes #41" -m "Fixes #45"
```

---

### Task 5: 同じ画面を2回続けて積まない（#43）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/Tabs.kt`・`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/TabsTest.kt`

**Interfaces:**
- Produces: `TabStacks.push(key: K)`（一番上と同じなら積まない）。`AppUi` の画面の入口はすべて `tabs.push(...)` を使う（SC-07 の前後の入れ替えはそのまま）。

- [ ] **Step 1: 失敗するテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt b/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
index 68fc9ca..606de64 100644
--- a/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
@@ -48,6 +48,17 @@ class TabsTest {
     assertEquals(Tab.HOME, selected)
   }
 
+  // Android #43: a second tap before the screen has moved does not stack the same screen twice.
+  @Test
+  fun pushing_the_screen_already_on_top_adds_nothing() {
+    tabs.press(Tab.SETTINGS)
+    tabs.push("volume")
+    tabs.push("volume")
+    assertEquals(listOf("settings", "volume"), tabs.current)
+    tabs.push("user")
+    assertEquals(listOf("settings", "volume", "user"), tabs.current)
+  }
+
   @Test
   fun opening_a_screen_of_another_tab_shows_it_above_that_tabs_first_screen() {
     tabs.press(Tab.SETTINGS)
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*TabsTest'`
Expected: コンパイルの失敗（`Unresolved reference 'push'`）。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 03e7383..e34b4c5 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -152,7 +152,7 @@ fun AppUi(graph: AppGraph) {
               entry<RecordsKey> {
                 RideListScreen(
                   rideList?.let { rideSections(it, System.currentTimeMillis(), ZoneId.systemDefault()) },
-                  onRide = { tabs.current.add(RideKey(it)) },
+                  onRide = { tabs.push(RideKey(it)) },
                   modifier = Modifier.safeDrawingPadding(),
                 )
               }
@@ -162,7 +162,7 @@ fun AppUi(graph: AppGraph) {
                   updateSettings = { next -> scope.launch { graph.settings.update(next) } },
                   rideId = key.rideId,
                   onBack = { tabs.back() },
-                  onAsk = { tabs.current.add(AskKey(key.rideId, it)) },
+                  onAsk = { tabs.push(AskKey(key.rideId, it)) },
                   onFullMap = { mapFull = it },
                   modifier = Modifier.safeDrawingPadding(),
                 )
@@ -179,12 +179,12 @@ fun AppUi(graph: AppGraph) {
               entry<SettingsKey> {
                 SettingsScreen(
                   current, apiKey,
-                  onConnection = { tabs.current.add(ConnectionKey) },
-                  onUser = { tabs.current.add(UserKey) },
-                  onRideRecording = { tabs.current.add(RideRecordingKey) },
-                  onReturnApp = { tabs.current.add(ReturnAppKey) },
-                  onVolume = { tabs.current.add(VolumeKey) },
-                  onRecordings = { tabs.current.add(RecordingsKey) },
+                  onConnection = { tabs.push(ConnectionKey) },
+                  onUser = { tabs.push(UserKey) },
+                  onRideRecording = { tabs.push(RideRecordingKey) },
+                  onReturnApp = { tabs.push(ReturnAppKey) },
+                  onVolume = { tabs.push(VolumeKey) },
+                  onRecordings = { tabs.push(RecordingsKey) },
                   version = BuildConfig.VERSION_NAME,
                   modifier = Modifier.safeDrawingPadding(),
                 )
diff --git a/app/src/main/java/com/touringproject/v2/ui/Tabs.kt b/app/src/main/java/com/touringproject/v2/ui/Tabs.kt
index 29badc9..59142c7 100644
--- a/app/src/main/java/com/touringproject/v2/ui/Tabs.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/Tabs.kt
@@ -42,6 +42,12 @@ class TabStacks<K>(
     return true
   }
 
+  /** Opens key in the tab shown, unless it is already on top: a quick second tap adds nothing (Android #43). */
+  fun push(key: K) {
+    val stack = current
+    if (stack.lastOrNull() != key) stack += key
+  }
+
   /** Shows key above the first screen of tab, e.g. the user name from Home's user chip. */
   fun open(tab: Tab, key: K) {
     val stack = stacks.getValue(tab)
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*TabsTest' --tests '*AppUiTest' --rerun`
Expected: `TabsTest` 6件・`AppUiTest` 7件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/Tabs.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
git commit -m "fix: do not stack the screen already on top again" -m "Fixes #43"
```

---

### Task 6: 名前を変えられなかったときの知らせ（#46）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt`・`app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt`

**Interfaces:**
- Produces: `RideDetailScreen(..., onRename: suspend (String) -> Boolean, ...)`（false でトースト「名前を変えられませんでした」）。

- [ ] **Step 1: 失敗するテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
index b85d44d..3635f17 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
@@ -33,6 +33,7 @@ import org.junit.Assert.assertEquals
 import org.junit.Rule
 import org.junit.Test
 import org.junit.runner.RunWith
+import org.robolectric.shadows.ShadowToast
 
 @RunWith(AndroidJUnit4::class)
 class RecordsScreensTest {
@@ -84,7 +85,7 @@ class RecordsScreensTest {
   @Test
   fun the_detail_shows_the_summary_and_the_timeline_and_a_row_opens_its_ask() {
     val asked = mutableListOf<String>()
-    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, { asked += it }, {}, {}) }
+    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, { asked += it }, { true }, {}) }
     rule.onNodeWithTag("summaryQuestions").onChildAt(0).assertTextEquals("2")
     // Robolectric's screen is small: the timeline under the map is scrolled to each row.
     val timeline = rule.onNodeWithTag("timeline")
@@ -98,7 +99,7 @@ class RecordsScreensTest {
   @Test
   fun a_tapped_pin_shows_its_card_which_opens_the_ask() {
     val asked = mutableListOf<String>()
-    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, { asked += it }, {}, {}) }
+    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, { asked += it }, { true }, {}) }
     rule.onNodeWithTag("pin-a1").performClick()
     rule.onNodeWithTag("mapState").assertTextEquals("pins 2 selected a1")
     rule.onNodeWithText("金時山です。").assertExists()
@@ -109,7 +110,7 @@ class RecordsScreensTest {
   @Test
   fun the_pins_can_be_hidden_and_the_choice_goes_to_the_settings() {
     var shown by mutableStateOf(true)
-    rule.setContent { RideDetailScreen(detail(), fakeMap, shown, { shown = it }, {}, {}, {}, {}) }
+    rule.setContent { RideDetailScreen(detail(), fakeMap, shown, { shown = it }, {}, {}, { true }, {}) }
     rule.onNodeWithTag("pin-a1").performClick()
     rule.onNodeWithTag("pinToggle").performClick()
     rule.onNodeWithTag("mapState").assertTextEquals("pins 0 selected null")
@@ -119,7 +120,7 @@ class RecordsScreensTest {
   @Test
   fun the_map_fills_the_screen_until_back_and_tells_so() {
     val full = mutableListOf<Boolean>()
-    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, {}, { full += it }) }
+    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, { true }, { full += it }) }
     rule.onNodeWithTag("fullMap").performClick()
     rule.waitForIdle()
     rule.onNodeWithTag("timeline").assertDoesNotExist()
@@ -133,7 +134,7 @@ class RecordsScreensTest {
   @Test
   fun the_menu_renames_the_ride_but_not_to_an_empty_name() {
     val names = mutableListOf<String>()
-    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, { names += it }, {}) }
+    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, { names += it; true }, {}) }
     rule.onNodeWithTag("rideMenu").performClick()
     rule.onNodeWithTag("renameRide").performClick()
     rule.onNodeWithTag("renameInput").performTextReplacement("  ")
@@ -143,9 +144,21 @@ class RecordsScreensTest {
     assertEquals(listOf("御殿場"), names)
   }
 
+  // Android #46: a name the device could not save is told, not silently lost.
+  @Test
+  fun a_rename_that_could_not_be_saved_is_told() {
+    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, { false }, {}) }
+    rule.onNodeWithTag("rideMenu").performClick()
+    rule.onNodeWithTag("renameRide").performClick()
+    rule.onNodeWithTag("renameInput").performTextReplacement("御殿場")
+    rule.onNodeWithTag("renameGo").performClick()
+    rule.waitForIdle()
+    assertEquals("名前を変えられませんでした", ShadowToast.getTextOfLatestToast())
+  }
+
   @Test
   fun a_ride_ended_by_its_longest_time_says_so() {
-    rule.setContent { RideDetailScreen(detail(autoEnded = true), fakeMap, true, {}, {}, {}, {}, {}) }
+    rule.setContent { RideDetailScreen(detail(autoEnded = true), fakeMap, true, {}, {}, {}, { true }, {}) }
     rule.onNodeWithTag("autoEnded").assertExists()
   }
 
@@ -184,7 +197,7 @@ class RecordsScreensTest {
       }
       fakeMap(data, selected, onPin, modifier)
     }
-    rule.setContent { RideDetailScreen(detail(), countingMap, true, {}, {}, {}, {}, {}) }
+    rule.setContent { RideDetailScreen(detail(), countingMap, true, {}, {}, {}, { true }, {}) }
     rule.onNodeWithTag("fullMap").performClick()
     rule.waitForIdle()
     back()
@@ -203,7 +216,7 @@ class RecordsScreensTest {
         onBack = { stack.removeAt(stack.lastIndex) },
         entryProvider = { key ->
           NavEntry(key) {
-            if (key == "list") Text("list") else RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, {}, {})
+            if (key == "list") Text("list") else RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, { true }, {})
           }
         },
       )
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordsScreensTest' --rerun`
Expected: 13件のうち `a_rename_that_could_not_be_saved_is_told` が落ちる（トーストが無い: `expected:<名前を変えられませんでした> but was:<null>`）。ほかの呼び出しの `{ true }` は今の `(String) -> Unit` にも渡せるので、コンパイルは通る。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
index 76ab111..8e4ee51 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
@@ -4,7 +4,6 @@ import androidx.compose.runtime.Composable
 import androidx.compose.runtime.getValue
 import androidx.compose.runtime.produceState
 import androidx.compose.runtime.remember
-import androidx.compose.runtime.rememberCoroutineScope
 import androidx.compose.ui.Modifier
 import androidx.lifecycle.compose.collectAsStateWithLifecycle
 import com.touringproject.v2.ask.AskRecord
@@ -19,7 +18,6 @@ import com.touringproject.v2.ride.RoutePoint
 import com.touringproject.v2.settings.Settings
 import com.touringproject.v2.store.RoomRecords
 import kotlinx.coroutines.flow.map
-import kotlinx.coroutines.launch
 import java.time.ZoneId
 
 // Reads what SC-06 and SC-07 show from the device's records and hands it to the screens. Nothing is drawn until the
@@ -67,7 +65,6 @@ fun RideDetailRoute(
   val ride = readRide(records, rideId) ?: return
   val asks = readAsks(records, rideId) ?: return
   val route = readRoute(records, rideId) ?: return
-  val scope = rememberCoroutineScope()
   val ui = remember(ride, asks, route) {
     ride.value?.let { rideDetailUi(it, asks, route, System.currentTimeMillis(), ZoneId.systemDefault()) }
   }
@@ -77,7 +74,7 @@ fun RideDetailRoute(
     onShowPins = { updateSettings(settings.copy(showAskPins = it)) },
     onBack = onBack,
     onAsk = onAsk,
-    onRename = { name -> scope.launch { rides.rename(rideId, name) } },
+    onRename = { name -> rides.rename(rideId, name) },
     onFullMap = onFullMap,
     modifier = modifier,
   )
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
index 7962feb..57aec7a 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
@@ -1,5 +1,6 @@
 package com.touringproject.v2.ui
 
+import android.widget.Toast
 import androidx.activity.compose.BackHandler
 import androidx.compose.foundation.background
 import androidx.compose.foundation.clickable
@@ -32,11 +33,13 @@ import androidx.compose.runtime.LaunchedEffect
 import androidx.compose.runtime.getValue
 import androidx.compose.runtime.key
 import androidx.compose.runtime.mutableStateOf
+import androidx.compose.runtime.rememberCoroutineScope
 import androidx.compose.runtime.saveable.rememberSaveable
 import androidx.compose.runtime.setValue
 import androidx.compose.ui.Alignment
 import androidx.compose.ui.Modifier
 import androidx.compose.ui.graphics.Color
+import androidx.compose.ui.platform.LocalContext
 import androidx.compose.ui.platform.testTag
 import androidx.compose.ui.text.font.FontWeight
 import androidx.compose.ui.text.style.TextOverflow
@@ -45,6 +48,7 @@ import androidx.compose.ui.unit.sp
 import com.touringproject.v2.map.MapData
 import com.touringproject.v2.ride.cutRideName
 import com.touringproject.v2.ride.rideName
+import kotlinx.coroutines.launch
 
 // SC-05, SC-06 and SC-07 (slice 2 spec §7.4–§7.6). The map comes in as a slot, so these screens are tested without
 // MapLibre, which needs a real device.
@@ -113,7 +117,8 @@ data class RideDetailUi(
 
 /**
  * SC-06. The map can fill the screen (onFullMap tells AppUi to hide the tabs), its pins can be hidden (showPins is
- * kept in the settings), and a tapped pin shows its card above the map's bottom edge.
+ * kept in the settings), and a tapped pin shows its card above the map's bottom edge. onRename says whether the new
+ * name was saved; one that was not is told (Android #46).
  */
 @Composable
 fun RideDetailScreen(
@@ -123,7 +128,7 @@ fun RideDetailScreen(
   onShowPins: (Boolean) -> Unit,
   onBack: () -> Unit,
   onAsk: (String) -> Unit,
-  onRename: (String) -> Unit,
+  onRename: suspend (String) -> Boolean,
   onFullMap: (Boolean) -> Unit,
   modifier: Modifier = Modifier,
 ) {
@@ -138,6 +143,8 @@ fun RideDetailScreen(
   var full by rememberSaveable { mutableStateOf(false) }
   var menu by rememberSaveable { mutableStateOf(false) }
   var renaming by rememberSaveable { mutableStateOf<String?>(null) }
+  val scope = rememberCoroutineScope()
+  val context = LocalContext.current
   LaunchedEffect(full) { onFullMap(full) }
   DisposableEffect(Unit) { onDispose { onFullMap(false) } }
   BackHandler(enabled = full) { full = false }
@@ -193,7 +200,12 @@ fun RideDetailScreen(
       },
       confirmButton = {
         TextButton(
-          onClick = { rideName(name)?.let(onRename); renaming = null },
+          onClick = {
+            rideName(name)?.let { clean ->
+              scope.launch { if (!onRename(clean)) Toast.makeText(context, "名前を変えられませんでした", Toast.LENGTH_SHORT).show() }
+            }
+            renaming = null
+          },
           enabled = rideName(name) != null,
           modifier = Modifier.testTag("renameGo"),
         ) { Text("変える") }
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordsScreensTest' --tests '*AppUiTest' --rerun`
Expected: `RecordsScreensTest` 13件・`AppUiTest` 7件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt \
  app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
git commit -m "fix: tell the rider when a new ride name could not be saved" -m "Fixes #46"
```

---

### Task 7: 一覧の受け方と、地図のデータをメインスレッドの外で組む（#42）

見た目の振る舞いは変わらない、重さの直し。新しい失敗するテストは作らない（計画を書くときに決めたこと）。今の画面のテストとエミュレーターの地図のテストで、壊れていないことを確かめる。

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/AppUi.kt`・`app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt`・`app/src/main/java/com/touringproject/v2/map/RouteMap.kt`

- [ ] **Step 1: 直す**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/map/RouteMap.kt b/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
index 85d10ce..ddcb5cf 100644
--- a/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
+++ b/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
@@ -32,6 +32,8 @@ import androidx.compose.ui.viewinterop.AndroidView
 import androidx.lifecycle.Lifecycle
 import androidx.lifecycle.LifecycleEventObserver
 import androidx.lifecycle.compose.LocalLifecycleOwner
+import kotlinx.coroutines.Dispatchers
+import kotlinx.coroutines.withContext
 import org.maplibre.android.MapLibre
 import org.maplibre.android.camera.CameraUpdateFactory
 import org.maplibre.android.geometry.LatLng
@@ -132,17 +134,22 @@ private fun addLayers(style: Style, faint: Boolean, dark: Boolean) {
   )
 }
 
-private fun draw(style: Style, data: MapData, selected: String?, density: Float) {
+/** The GeoJSON of each source, made off the main thread (Android #42). */
+private class MapJson(val routes: String, val pauses: String, val ends: String, val pins: String)
+
+private fun mapJson(data: MapData, selected: String?) = MapJson(routesJson(data), pausesJson(data), endsJson(data), pinsJson(data, selected))
+
+private fun draw(style: Style, data: MapData, json: MapJson, density: Float) {
   data.pins.forEach { pin ->
     listOf(false, true).forEach { sel ->
       val name = pinIcon(pin.number, sel)
       if (style.getImage(name) == null) style.addImage(name, pinBitmap(pin.number, sel, density))
     }
   }
-  style.getSourceAs<GeoJsonSource>("routes")?.setGeoJson(routesJson(data))
-  style.getSourceAs<GeoJsonSource>("pauses")?.setGeoJson(pausesJson(data))
-  style.getSourceAs<GeoJsonSource>("ends")?.setGeoJson(endsJson(data))
-  style.getSourceAs<GeoJsonSource>(PINS_LAYER)?.setGeoJson(pinsJson(data, selected))
+  style.getSourceAs<GeoJsonSource>("routes")?.setGeoJson(json.routes)
+  style.getSourceAs<GeoJsonSource>("pauses")?.setGeoJson(json.pauses)
+  style.getSourceAs<GeoJsonSource>("ends")?.setGeoJson(json.ends)
+  style.getSourceAs<GeoJsonSource>(PINS_LAYER)?.setGeoJson(json.pins)
 }
 
 /** Takes in the whole route and every pin; a single place is shown close up (slice 2 spec §7.5). */
@@ -232,11 +239,15 @@ fun RouteMap(
   }
   LaunchedEffect(loaded, data, selected) {
     val (map, style) = loaded ?: return@LaunchedEffect
-    draw(style, data, selected, density)
-    // Until the first places arrive the map shows Japan, and the camera fits again once they do.
-    if (!fitted) {
-      fit(map, data.extent, (48 * density).toInt())
-      fitted = data.extent.isNotEmpty()
+    val json = withContext(Dispatchers.Default) { mapJson(data, selected) }
+    // MapLibre is touched only on the UI thread; where the effect resumes is not left to chance.
+    withContext(Dispatchers.Main) {
+      draw(style, data, json, density)
+      // Until the first places arrive the map shows Japan, and the camera fits again once they do.
+      if (!fitted) {
+        fit(map, data.extent, (48 * density).toInt())
+        fitted = data.extent.isNotEmpty()
+      }
     }
   }
   Box(modifier) {
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index e34b4c5..722bad3 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -81,7 +81,6 @@ fun AppUi(graph: AppGraph) {
   val storeFailed by graph.rides.storeFailed.collectAsStateWithLifecycle()
   val askStoreFailed by graph.askLog.failed.collectAsStateWithLifecycle()
   val questions by graph.activeAskCount.collectAsStateWithLifecycle()
-  val rideList by graph.records.list.collectAsStateWithLifecycle(null)
   // SC-06 tells while its map fills the screen; the tabs go with it (slice 2 spec §7.1).
   var mapFull by remember { mutableStateOf(false) }
   // Saveable: SC-17 and SC-04 stay open when the activity is recreated, e.g. on rotation (Android #20).
@@ -150,6 +149,8 @@ fun AppUi(graph: AppGraph) {
                 )
               }
               entry<RecordsKey> {
+                // Read only while the list is shown: Room runs the query again for every route point (Android #42).
+                val rideList by graph.records.list.collectAsStateWithLifecycle(null)
                 RideListScreen(
                   rideList?.let { rideSections(it, System.currentTimeMillis(), ZoneId.systemDefault()) },
                   onRide = { tabs.push(RideKey(it)) },
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
index 8e4ee51..3267da7 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
@@ -17,7 +17,9 @@ import com.touringproject.v2.ride.RideStatus
 import com.touringproject.v2.ride.RoutePoint
 import com.touringproject.v2.settings.Settings
 import com.touringproject.v2.store.RoomRecords
+import kotlinx.coroutines.Dispatchers
 import kotlinx.coroutines.flow.map
+import kotlinx.coroutines.withContext
 import java.time.ZoneId
 
 // Reads what SC-06 and SC-07 show from the device's records and hands it to the screens. Nothing is drawn until the
@@ -65,11 +67,12 @@ fun RideDetailRoute(
   val ride = readRide(records, rideId) ?: return
   val asks = readAsks(records, rideId) ?: return
   val route = readRoute(records, rideId) ?: return
-  val ui = remember(ride, asks, route) {
-    ride.value?.let { rideDetailUi(it, asks, route, System.currentTimeMillis(), ZoneId.systemDefault()) }
-  }
+  // A long ride has tens of thousands of points: the map's data is made off the main thread (Android #42).
+  val ui = produceState<Read<RideDetailUi?>?>(null, ride, asks, route) {
+    value = Read(withContext(Dispatchers.Default) { ride.value?.let { rideDetailUi(it, asks, route, System.currentTimeMillis(), ZoneId.systemDefault()) } })
+  }.value ?: return
   RideDetailScreen(
-    ui, routeMap,
+    ui.value, routeMap,
     showPins = settings.showAskPins,
     onShowPins = { updateSettings(settings.copy(showAskPins = it)) },
     onBack = onBack,
PATCH
````

- [ ] **Step 2: 画面のテストを回す**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AppUiTest' --tests '*RecordsScreensTest' --rerun`
Expected: `AppUiTest` 7件・`RecordsScreensTest` 13件が通る。

- [ ] **Step 3: エミュレーターのテストを回す**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
```

Expected: 6件が通る（`RouteMapTest` 2件を含む）。`CalledFromWorkerThreadException` が出たら、地図に触る処理が `withContext(Dispatchers.Main)` の中にあるかを見る。

- [ ] **Step 4: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt \
  app/src/main/java/com/touringproject/v2/map/RouteMap.kt
git commit -m "fix: read the ride list only on its tab and build the map data off the main thread" -m "Fixes #42"
```

---

### Task 8: 版と文書

**Files:**
- Modify: `app/build.gradle.kts`（版 0.5.0）・`README.md`（Android）・`docs-parent/`

- [ ] **Step 1: 版を上げ、README を直す**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/README.md b/README.md
index 350c08a..3cf896f 100644
--- a/README.md
+++ b/README.md
@@ -27,6 +27,7 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 
 - 走行の記録中と一巡のあいだは、前面サービスを動かす（無いと、画面を消したあと位置・通信・再生が止まる）。種類は、記録中は `location`、一巡のあいだは `microphone|mediaPlayback` を足す。Android 14 以降、この2つはアプリが前面にあるときにしか始められず、足せない（理由は親の `adr/0006`）。
 - 走行の状態を変えるのは `RideController` だけ。サービス・締め切りのアラーム・電源を切る知らせ・画面は、どれもこれを呼ぶ。起動したときは `load()` が先に、残っていた走行を片付ける（端末が止まっていれば終了、締め切りを過ぎていれば自動終了、それ以外は記録の再開）。最長時間を変えたときの締め切りの計算し直しも `maxRecordingChanged()` が行う（`AppGraph` が設定の変化を受けて呼ぶ）。名前の変更は `rename()`。
+- 質問を受けるのは走行の記録中だけ。`AskController.run` の入口で `RideNow`（記録中・一時停止中・記録していない）を見て、記録中でなければ録音を始めず、理由を読み上げる。画面の「押して話す」も押せない形にする（親の spec 2 §4.7・adr/0008）。
 - Room のスキーマを変えるときは、版を上げて Migration を書き、`app/schemas/` に書き出された JSON もコミットする。破壊的な作り直しは使わない。スキーマの JSON は debug のビルドの資産にも入る（Robolectric の `MigrationTestHelper` が読むため。release には入らない）。Entity や Migration を変えた直後のテストは `--rerun` で確かめる。
 - 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと。契機では未送信を調べるだけで、送るものが無ければ通信しない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index 0022394..aa5c05b 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 5
-    versionName = "0.4.0"
+    versionCode = 6
+    versionName = "0.5.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
PATCH
````

- [ ] **Step 2: 親の文書を写す**

この plan を書いた親のブランチで、要件（01・02・03・04・07）とモックを adr/0008 に合わせて直したので、Android の `docs-parent/` に写す。

```bash
cd $ROOT && scripts/sync-docs.sh Android
cd $AND && git status --short docs-parent
```

Expected: `docs-parent/` の `01_requirements.md`・`02_screen_list.md`・`03_screen_transition.md`・`04_detailed_requirements.md`・`07_units_contracts.md`・`mock/index.html` が変わっている。

- [ ] **Step 3: コミット**

```bash
cd $AND && git add app/build.gradle.kts README.md docs-parent/01_requirements.md docs-parent/02_screen_list.md \
  docs-parent/03_screen_transition.md docs-parent/04_detailed_requirements.md docs-parent/07_units_contracts.md docs-parent/mock/index.html
git commit -m "chore: raise the version to 0.5.0 and say asks need a recording ride"
```

---

### Task 9: 全体の確かめ

- [ ] **Step 1: `clean` から JVM のテスト・ビルド・権限の検査**

```bash
cd $AND && ./gradlew clean && ./gradlew testDebugUnitTest > /tmp/trv2-all.log 2>&1; tail -3 /tmp/trv2-all.log
python3 - <<'EOF'
import glob, re
t = f = 0
for x in glob.glob('app/build/test-results/testDebugUnitTest/*.xml'):
    m = re.search(r'tests="(\d+)" skipped="\d+" failures="(\d+)" errors="(\d+)"', open(x).read())
    t += int(m[1]); f += int(m[2]) + int(m[3])
print(t, f)
EOF
cd $AND && ./gradlew assembleDebug assembleRelease && scripts/check-release-permissions.sh
```

Expected: `379 0`。`BUILD SUCCESSFUL`。`release permissions OK (15)`。

- [ ] **Step 2: エミュレーターのテスト**

```bash
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: 6件が通る。

---

### Task 10: DynamoDB の走行に結びつかない質問を消す（AI。利用者の了承を得てから）

戻せない操作なので、消す前に件数を見せて了承を得る。会話（`CONV#`）・走行（`RIDE#`）には触れない。

- [ ] **Step 1: 探して数える**

```bash
export AWS_PROFILE=touring AWS_REGION=ap-northeast-1
aws dynamodb scan --table-name dynamodb-trv2-dev-records \
  --filter-expression 'begins_with(sk, :a) AND attribute_not_exists(rideId)' \
  --expression-attribute-values '{":a":{"S":"ASK#"}}' --projection-expression 'pk, sk' --output json > /tmp/trv2-rideless-asks.json
python3 - <<'EOF'
import json, collections
items = json.load(open('/tmp/trv2-rideless-asks.json'))['Items']
print(len(items), collections.Counter(i['pk']['S'] for i in items))
EOF
```

`scan` が `NextToken`（または `LastEvaluatedKey`）を返したら、AWS CLI は既定でページを繋いで返すので、そのままでよい。件数とユーザー名ごとの内訳を、チャットで利用者に見せる（文書・コミットには書かない）。

- [ ] **Step 2: 了承を得てから消す**

```bash
python3 - <<'EOF'
import json, subprocess
items = json.load(open('/tmp/trv2-rideless-asks.json'))['Items']
for i in range(0, len(items), 25):
    batch = {"dynamodb-trv2-dev-records": [{"DeleteRequest": {"Key": {"pk": it["pk"], "sk": it["sk"]}}} for it in items[i:i + 25]]}
    out = subprocess.run(["aws", "dynamodb", "batch-write-item", "--request-items", json.dumps(batch), "--output", "json"],
                         check=True, capture_output=True, text=True).stdout
    left = json.loads(out).get("UnprocessedItems") or {}
    if left:
        raise SystemExit(f"unprocessed: {left}")
print("deleted", len(items))
EOF
```

Expected: `deleted <件数>`。Step 1 の `scan` をもう一度回すと0件。`/tmp/trv2-rideless-asks.json` は消す。

---

### Task 11: 利用者の実機の確認

走行用のビルド（版 0.5.0）を実機に入れる。入れたときに版4の Migration が一度だけ走り、端末の走行に結びつかない質問が消える。

```bash
cd $AND && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

1. 設定 → バージョンが 0.5.0。
2. 走行を記録していないとき、ホームの「押して話す」が淡く押せず、その下に「走行を開始すると、インカムのボタンで話せます」が出る。走行のカードに「走行を記録しているあいだだけ質問できます」。
3. 走行していないときにインカムのボタンを押すと、録音が始まらず、失敗の音のあと「走行を記録していないので、質問できません。」と聞こえ、戻り先のアプリ（ナビ）に戻る。
4. 走行を始めると「押して話す」が押せて、一行が緑の「インカムのボタンで話せます」に戻る。インカムで質問でき、答えが返る。
5. 一時停止すると、「押して話す」が押せず「再開すると、インカムのボタンで話せます」が出る。インカムを押すと「一時停止中は質問できません。再開すると質問できます。」と聞こえる。再開すると、また質問できる。
6. 記録中に質問を始め、答えを待っているあいだにホームで一時停止する → 答えは最後まで読み上げられ、その質問は走行の詳細の時系列に出る。
7. 記録のタブの走行の一覧と詳細が、これまでどおり出る（走行の質問は残っている）。
8. 走行の詳細で名前を変えられる（#46 の失敗の知らせは、書き込みが失敗したときだけなので、実機では出ないことを確かめるだけでよい）。

✗ が出たら `superpowers:systematic-debugging`。
