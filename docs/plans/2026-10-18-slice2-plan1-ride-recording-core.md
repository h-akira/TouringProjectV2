# スライス2 計画1: 走行の記録の芯 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 走行を開始・一時停止・再開・終了でき、記録中は画面を消してもルートが端末の DB（Room）に溜まり、最長時間で自動で終わり、アプリが落ちても端末が止まっても記録が正しく片付く。ホームの走行のカード・走行の開始（SC-17）・走行終了の確認（SC-04）から操作できる。

**Architecture:** 新しいパッケージ `ride` に、Android に依存しない走行の型と計算（`Ride.kt`）と司令塔（`RideController`）を置き、外とのやり取りは `RidePorts.kt` の interface（記録の置き場・締め切りのアラーム・サービス）を通す。`store` が Room で置き場を実装する。前面サービスは1つのまま、`service/ServiceCoordinator` が「走行の記録中か」と「質問の一巡の途中か」から種類（`location`・`microphone`・`mediaPlayback`）を決め、サービスを始める・種類を変える・止める。サービスの中で Fused のルートの位置を受け、1分ごとに生きていた時刻を書き、締め切りを見る。正確でないアラームと電源を切る知らせの受け口も、同じ司令塔を呼ぶ。

**Tech Stack:** Kotlin 2.3.20・AGP 9.0.1・Gradle 9.4.1・Compose BOM 2026.03.01・Navigation 3・Play services location 21.3.0・Robolectric 4.16（SDK 35）。足すのは Room 2.8.4（`room-runtime`・`room-ktx`・`room-compiler`）と KSP 2.3.10・Room の Gradle プラグイン（Task 2）。

**Spec:** [docs/specs/2026-10-17-slice2-design.md](../specs/2026-10-17-slice2-design.md)（§3・§4・§5.1・§7.2・§7.3・§8・§9・§11）。見た目と文言は [画面モック](../mock/index.html) の SC-02 の走行のカード・SC-17・SC-04。

**範囲に入れた issue:** なし（Android の #7〜#13 は録音と音量の扱いで、この plan の範囲に関わらない。#12 は plan 3 の候補）。

**計画を書くときに決めたこと（spec からの具体化）:**
- 最長時間は、この plan では既定の24時間の定数（`DEFAULT_MAX_RECORDING_MS`）。選べるようにするのと、変えたときに記録中の区間の締め切りを計算し直す（spec §4.4・US-C-08.005）のは、SC-16 と一緒に plan 3。
- ホームの走行のカードと SC-04 の要約の「質問の数」は出さない。質問を端末に保存するのが plan 3 なので、そこで足す。SC-04 の「終了して保存」のあとは SC-06 ではなくホームに戻る（SC-06 は plan 4）。
- 走行の距離は、点を足すたびに `rides.distanceMeters` に足し込んでおく（ホームのカードと一覧が全部の点を読まずに済むように。spec §5.1 の列に足した）。
- 区間の開始より古い点は捨てる。Fused は監視を始め直した直後に古い位置を返すことがあり、再開の直後に一時停止の前の位置が新しい区間に入るのを防ぐ（spec §4.3 の「精度の悪い点を捨てる」と同じ扱い）。
- DB への書き込みに失敗しても、走行は画面の上で続け、ホームの警告の帯に「記録を保存できません」を、ほかの帯より先に出す（spec §8）。
- サービスの通知は「走行を記録中」（記録中）か「応答中」（一巡だけ）。通知のチャンネル名は「走行の記録と応答」に変える。自動終了の通知は別のチャンネル「走行の自動終了」。

この計画のコードは、使い捨てのフォルダで JVM のテスト243件・エミュレーターのテスト4件・`assembleDebug`・`assembleRelease`（lint を含む）・`scripts/check-release-permissions.sh`（15件）が通ることを確かめてから書いた。

## Global Constraints

- 作業するリポジトリは `Android/`（`TouringProjectV2_Android`）と親。どちらも `main` から作業ブランチ `slice2-plan1` を切る。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- パッケージ名 `com.touringproject.v2`。minSdk 29・targetSdk 36・compileSdk 36。JDK 17。
- 作りの決まり（移行の spec §5）: 1つの Gradle モジュールをパッケージで分ける。状態機械と司令塔は Android に依存させず、外とのやり取りは interface を通す。部品は `AppGraph` で手で組む（DI のライブラリは入れない）。
- ルートの位置: `PRIORITY_HIGH_ACCURACY`・5秒ごと・10m 動いたら。精度が 50m より悪い点は捨てる。値は `location/Route.kt` の定数で、利用者が変える設定にはしない（spec §4.3）。
- 最長時間は既定24時間。締め切りは「区間の開始＋最長時間」。終了の時刻は締め切りの時刻（spec §4.4）。
- 名前は必須で40字まで。前後の空白は落とす（SC-17・SC-04）。
- 端末の停止で終えた走行は、終了の理由を `shutdown` として残すが、画面ではふつうの終了と同じに見せ、通知も出さない（spec §4.5）。
- Room のスキーマは `app/schemas/` に書き出してコミットする。破壊的な作り直し（`fallbackToDestructiveMigration`）は使わない（spec §5.1）。
- 接続キー・API の URL・アカウント ID を、コードや文書に書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`（`rm` は置き換えられている）。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest`（絞るときは `--tests '*クラス名'` を引用符で囲む）。`-q` は付けない。重い実行はログをファイルに出す。ビルドのキャッシュで数秒で終わることがあるので、全体を確かめるときは `--rerun` を付け、`app/build/test-results/testDebugUnitTest/` の結果のファイルの時刻と件数を見る。
- 実機が USB で繋がったままエミュレーターのテストを回すときは、`export ANDROID_SERIAL=emulator-5554` でエミュレーターだけを指す。エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`（止めるときは `stop`）。起動の直後に「System UI isn't responding」が出たら「Wait」で閉じる。
- Robolectric の決まり: SDK 35 で動かす。`withContext(Dispatchers.Main)` を使うコードはテストのスレッドから直に呼ばない。`runTest` の `backgroundScope` で動かした処理は `advanceUntilIdle` で進まない。Room はそれ自身のスレッドで動いてメインのルーパーで戻るので、Robolectric のテストではメインのルーパーを回しながら結果を待つ（Task 5 の `waitUntil`）。
- ディスクの空きが少ない。大きなものを入れる前に `df -h /` を見る。

## Review Focus

- 一時停止してから再開した直後に、Fused が一時停止の前の古い位置を返す → その点は新しい区間に入らず、距離にも足されない。Task 3 の `a_fix_from_before_the_segment_started_is_not_recorded`。
- 一時停止中にアプリが落ちる（プロセスが殺される）→ 次に起動しても一時停止のまま。サービスもアラームも動かさない。Task 3 の `load_of_a_paused_ride_keeps_it_paused_without_the_service`。
- 走行を始める時点で DB に書けない（容量不足など）→ 走行は画面の上で始まり、サービスも動き、ホームに「記録を保存できません」が出る。Task 3 の `a_ride_starts_even_when_it_cannot_be_saved`。
- 名前の欄に41字以上を貼り付ける → 40字で切れ、その名前で始まる。Task 6 の `a_pasted_name_is_cut_at_40_characters`。
- 手で終了した直後に、締め切りのアラームが遅れて届く → 何も起きない（自動終了に書き換わらず、通知も出ない）。Task 3 の `the_alarm_after_the_rider_ended_does_nothing`。

---

## ファイル構成（`Android/app/src/` から。`...` は `com/touringproject/v2`）

| パス | 役割 | Task |
|---|---|---|
| `main/java/.../ride/Ride.kt`（新規） | 走行・区間・点の型と、開始・一時停止・再開・終了・走行時間・一時停止・距離・起動したときの突き合わせの計算（純粋） | 1 |
| `main/java/.../ride/RidePorts.kt`（新規） | 司令塔の外との窓口（`RideStore`・`DeadlineAlarm`・`RideDeps`） | 2 |
| `main/java/.../store/RideDatabase.kt`・`RoomRideStore.kt`（新規）・`app/schemas/`（生成） | Room の DB と、`RideStore` の実装 | 2 |
| `main/java/.../location/Route.kt`（新規） | ルートの位置の頼み方と、点のふるい分け | 3 |
| `main/java/.../ride/RideController.kt`（新規） | 走行の司令塔 | 3 |
| `main/java/.../service/ServiceCoordinator.kt`（新規） | サービスの種類を決める関数と、サービスの取りまとめ（一巡の `KeepAlive` を兼ねる） | 4 |
| `main/java/.../service/RideForegroundService.kt`（書き換え） | 種類を変える前面サービス・ルートの監視・1分ごとの書き込み・電源を切る知らせ | 5 |
| `main/java/.../service/RideAlarms.kt`（新規） | 締め切りのアラームとその受け口・自動終了の通知 | 5 |
| `main/java/.../AppGraph.kt`・`MainActivity.kt`・`main/AndroidManifest.xml`・`scripts/check-release-permissions.sh` | 組み立て・前面に来たときのサービスの始め直し・権限と受け口 | 5 |
| `main/java/.../ui/RideLabels.kt`・`RideScreens.kt`（新規）・`Labels.kt`・`HomeScreen.kt`・`AppUi.kt` | ホームの走行のカード・SC-17・SC-04・警告の帯 | 6 |
| `androidTest/java/.../RideRecordingTest.kt`（新規） | エミュレーターのテスト | 7 |
| `README.md`（Android）・親の `adr/0006`・`adr/README.md`・`docs/05_technical_policies.md` | 文書 | 8 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: 両方のリポジトリでブランチを切る**

```bash
cd $ROOT && git switch main && git switch -c slice2-plan1
cd $AND && git switch main && git pull --ff-only 2>/dev/null; git switch -c slice2-plan1
cd $AND && ./gradlew testDebugUnitTest > /tmp/trv2-base.log 2>&1; tail -3 /tmp/trv2-base.log
```

Expected: `BUILD SUCCESSFUL`（始める前の JVM のテストは183件。この plan で60件増え、243件になる）。

---

### Task 1: 走行の型と計算

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ride/Ride.kt`
- Test: `app/src/test/java/com/touringproject/v2/ride/RideTest.kt`

**Interfaces:**
- Consumes: `location/Heading.kt` の `Fix(latitude, longitude, timestamp, accuracy)` と `distanceMeters(a: Fix, b: Fix): Double`（既存）
- Produces: `enum class RideStatus { RECORDING, PAUSED, ENDED }`・`enum class EndReason { MANUAL, AUTO, SHUTDOWN }`・`HOUR_MS`・`DEFAULT_MAX_RECORDING_MS`・`RIDE_NAME_MAX`・`data class Segment(seq, startedAt, endedAt?, bootCount?)`・`data class Ride(id, name, status, segments, endReason?, deadline?, lastAliveAt?, distanceMeters, updatedAt)`・`data class RoutePoint(segment, t, lat, lon, accuracy?)`・`rideName(String): String?`・`newRide(id, name, now, bootCount, maxRecordingMs): Ride`・`Ride.pause(now)`・`Ride.resume(now, bootCount, maxRecordingMs)`・`Ride.end(at, reason, now, name = this.name)`・`Ride.recordedMs(now)`・`data class Pauses(count, totalMs)`・`Ride.pauses()`・`Ride.startedAt()`・`Ride.endedAt()`・`stepMeters(previous: RoutePoint?, next: RoutePoint): Double`・`sealed interface Reconcile { Nothing, EndShutdown(at), EndAuto(at), Resume, KeepPaused }`・`reconcile(ride: Ride?, now: Long, bootCount: Int?): Reconcile`

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ride/RideTest.kt`:

```kotlin
package com.touringproject.v2.ride

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

private const val MAX = 24 * HOUR_MS

class RideTest {
  private val started = newRide("r1", "箱根", 1_000, 7, MAX)

  @Test
  fun a_new_ride_records_one_open_segment_with_its_deadline() {
    assertEquals(RideStatus.RECORDING, started.status)
    assertEquals(listOf(Segment(0, 1_000, null, 7)), started.segments)
    assertEquals(1_000 + MAX, started.deadline)
  }

  @Test
  fun pausing_closes_the_segment_and_resuming_opens_the_next_with_a_new_deadline() {
    val paused = started.pause(5_000)
    assertEquals(Segment(0, 1_000, 5_000, 7), paused.segments.single())
    assertNull(paused.deadline)
    val resumed = paused.resume(9_000, 7, MAX)
    assertEquals(Segment(1, 9_000, null, 7), resumed.segments.last())
    assertEquals(9_000 + MAX, resumed.deadline)
  }

  @Test
  fun recorded_time_and_pauses_leave_out_the_gaps() {
    val ride = started.pause(5_000).resume(9_000, 7, MAX).pause(10_000).resume(20_000, 7, MAX)
    assertEquals(4_000 + 1_000 + 2_000, ride.recordedMs(22_000))
    assertEquals(Pauses(2, 4_000 + 10_000), ride.pauses())
  }

  @Test
  fun ending_closes_the_open_segment_at_the_given_time_and_keeps_the_new_name() {
    val ended = started.end(3_000, EndReason.MANUAL, 3_500, "箱根から御殿場へ")
    assertEquals(3_000L, ended.endedAt())
    assertEquals("箱根から御殿場へ", ended.name)
    assertEquals(EndReason.MANUAL, ended.endReason)
    assertEquals(3_500L, ended.updatedAt)
  }

  @Test
  fun an_end_before_the_segment_started_closes_it_at_its_start() {
    assertEquals(1_000L, started.end(500, EndReason.SHUTDOWN, 600).endedAt())
  }

  @Test
  fun names_are_trimmed_required_and_at_most_40_characters() {
    assertEquals("箱根", rideName("  箱根 "))
    assertNull(rideName("   "))
    assertEquals("あ".repeat(40), rideName("あ".repeat(40)))
    assertNull(rideName("あ".repeat(41)))
  }

  @Test
  fun the_distance_steps_never_join_two_segments() {
    val a = RoutePoint(0, 0, 35.0, 139.0, 5.0)
    val b = RoutePoint(0, 5_000, 35.001, 139.0, 5.0)
    val c = RoutePoint(1, 9_000, 35.002, 139.0, 5.0)
    assertEquals(111.2, stepMeters(a, b), 0.5)
    assertEquals(0.0, stepMeters(b, c), 0.0)
    assertEquals(0.0, stepMeters(null, a), 0.0)
  }
}

class ReconcileTest {
  private val recording = newRide("r1", "箱根", 1_000, 7, MAX).copy(lastAliveAt = 60_000)

  @Test
  fun nothing_is_left_over() {
    assertEquals(Reconcile.Nothing, reconcile(null, 2_000, 7))
  }

  @Test
  fun a_reboot_ends_the_ride_when_it_was_last_seen_alive() {
    assertEquals(Reconcile.EndShutdown(60_000), reconcile(recording, 120_000, 8))
  }

  @Test
  fun a_reboot_ends_a_paused_ride_at_the_pause() {
    val paused = recording.pause(90_000)
    assertEquals(Reconcile.EndShutdown(90_000), reconcile(paused, 120_000, 8))
  }

  @Test
  fun a_crash_past_the_deadline_ends_the_ride_at_the_deadline() {
    assertEquals(Reconcile.EndAuto(1_000 + MAX), reconcile(recording, 2_000 + MAX, 7))
  }

  @Test
  fun a_crash_before_the_deadline_resumes_recording() {
    assertEquals(Reconcile.Resume, reconcile(recording, 120_000, 7))
  }

  @Test
  fun a_paused_ride_stays_paused_and_an_unknown_boot_count_is_not_a_reboot() {
    assertEquals(Reconcile.KeepPaused, reconcile(recording.pause(90_000), 120_000, 7))
    assertEquals(Reconcile.Resume, reconcile(recording, 120_000, null))
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideTest' --tests '*ReconcileTest'`
Expected: コンパイルの失敗（`Unresolved reference 'newRide'` など）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/ride/Ride.kt`:

```kotlin
package com.touringproject.v2.ride

import com.touringproject.v2.location.Fix
import com.touringproject.v2.location.distanceMeters

// A ride is a list of recorded segments; pausing closes one and resuming opens the next (slice 2 spec §4.1).

enum class RideStatus { RECORDING, PAUSED, ENDED }

/** SHUTDOWN is kept in the record but shown and sent like MANUAL (slice 2 spec §4.5). */
enum class EndReason { MANUAL, AUTO, SHUTDOWN }

const val HOUR_MS = 3_600_000L

/** US-C-08.003. SC-16 (slice 2 plan 3) lets the rider choose another one. */
const val DEFAULT_MAX_RECORDING_MS = 24 * HOUR_MS

/** SC-17. */
const val RIDE_NAME_MAX = 40

/** bootCount is the device's boot count when the segment started (null when the system does not tell). */
data class Segment(val seq: Int, val startedAt: Long, val endedAt: Long?, val bootCount: Int?)

/**
 * deadline is when the open segment reaches the longest recording time (null unless recording).
 * lastAliveAt is the last time the recording service was known to run. distanceMeters is cached so that
 * the home card and the lists need not read every point.
 */
data class Ride(
  val id: String,
  val name: String,
  val status: RideStatus,
  val segments: List<Segment>,
  val endReason: EndReason?,
  val deadline: Long?,
  val lastAliveAt: Long?,
  val distanceMeters: Double,
  val updatedAt: Long,
)

/** One stored route point. segment is the seq of the segment it was recorded in. */
data class RoutePoint(val segment: Int, val t: Long, val lat: Double, val lon: Double, val accuracy: Double?)

/** Returns the trimmed name, or null when it cannot name a ride (SC-17, SC-04: required, up to 40 characters). */
fun rideName(input: String): String? = input.trim().takeIf { it.isNotEmpty() && it.length <= RIDE_NAME_MAX }

fun newRide(id: String, name: String, now: Long, bootCount: Int?, maxRecordingMs: Long) = Ride(
  id = id,
  name = name,
  status = RideStatus.RECORDING,
  segments = listOf(Segment(0, now, null, bootCount)),
  endReason = null,
  deadline = now + maxRecordingMs,
  lastAliveAt = now,
  distanceMeters = 0.0,
  updatedAt = now,
)

private fun Ride.closeOpenSegment(at: Long) = segments.map {
  if (it.endedAt == null) it.copy(endedAt = maxOf(at, it.startedAt)) else it
}

fun Ride.pause(now: Long): Ride {
  check(status == RideStatus.RECORDING) { "only a recording ride can pause" }
  return copy(status = RideStatus.PAUSED, segments = closeOpenSegment(now), deadline = null, lastAliveAt = now, updatedAt = now)
}

fun Ride.resume(now: Long, bootCount: Int?, maxRecordingMs: Long): Ride {
  check(status == RideStatus.PAUSED) { "only a paused ride can resume" }
  val next = Segment(segments.last().seq + 1, now, null, bootCount)
  return copy(status = RideStatus.RECORDING, segments = segments + next, deadline = now + maxRecordingMs, lastAliveAt = now, updatedAt = now)
}

/** Ends the ride as of at (the open segment closes there); now is when the change is made. */
fun Ride.end(at: Long, reason: EndReason, now: Long, name: String = this.name): Ride {
  check(status != RideStatus.ENDED) { "the ride has already ended" }
  return copy(name = name, status = RideStatus.ENDED, segments = closeOpenSegment(at), endReason = reason, deadline = null, updatedAt = now)
}

/** The time spent recording; an open segment counts up to now (US-C-07.006). */
fun Ride.recordedMs(now: Long): Long = segments.sumOf { (it.endedAt ?: maxOf(now, it.startedAt)) - it.startedAt }

data class Pauses(val count: Int, val totalMs: Long)

/** The gaps between segments (US-C-07.007). A paused ride's current pause is not counted until it resumes. */
fun Ride.pauses(): Pauses {
  val gaps = segments.zipWithNext { a, b -> b.startedAt - (a.endedAt ?: b.startedAt) }
  return Pauses(gaps.size, gaps.sum())
}

fun Ride.startedAt(): Long = segments.first().startedAt

/** The end of the last closed segment, or null while a segment is open. */
fun Ride.endedAt(): Long? = segments.last().endedAt

/** How far a new point adds to the ride: points of different segments are never joined (US-C-07.006). */
fun stepMeters(previous: RoutePoint?, next: RoutePoint): Double {
  if (previous == null || previous.segment != next.segment) return 0.0
  return distanceMeters(Fix(previous.lat, previous.lon, previous.t, null), Fix(next.lat, next.lon, next.t, null))
}

/** What to do with a ride left recording or paused when the app starts again (slice 2 spec §4.5). */
sealed interface Reconcile {
  data object Nothing : Reconcile
  data class EndShutdown(val at: Long) : Reconcile
  data class EndAuto(val at: Long) : Reconcile
  data object Resume : Reconcile
  data object KeepPaused : Reconcile
}

fun reconcile(ride: Ride?, now: Long, bootCount: Int?): Reconcile {
  if (ride == null || ride.status == RideStatus.ENDED) return Reconcile.Nothing
  val last = ride.segments.last()
  if (bootCount != null && last.bootCount != null && bootCount > last.bootCount) {
    val closed = last.endedAt ?: last.startedAt
    return Reconcile.EndShutdown(maxOf(ride.lastAliveAt ?: closed, closed))
  }
  if (ride.status == RideStatus.PAUSED) return Reconcile.KeepPaused
  val deadline = ride.deadline
  if (deadline != null && now >= deadline) return Reconcile.EndAuto(deadline)
  return Reconcile.Resume
}
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideTest' --tests '*ReconcileTest'`
Expected: `BUILD SUCCESSFUL`。`TEST-...ride.RideTest.xml` が7件、`ReconcileTest.xml` が6件

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ride/Ride.kt app/src/test/java/com/touringproject/v2/ride/RideTest.kt
git commit -m "feat: add the ride model with segments, pauses and the restart decision"
```

---

### Task 2: Room の置き場

**Files:**
- Modify: `gradle/libs.versions.toml`・`build.gradle.kts`・`app/build.gradle.kts`
- Create: `app/src/main/java/com/touringproject/v2/ride/RidePorts.kt`・`app/src/main/java/com/touringproject/v2/store/RideDatabase.kt`・`app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt`
- Create（生成）: `app/schemas/com.touringproject.v2.store.RideDatabase/1.json`
- Test: `app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt`

**Interfaces:**
- Consumes: Task 1 の `Ride`・`Segment`・`RoutePoint`・`RideStatus`・`EndReason`・`newRide`・`pause`・`resume`・`end`
- Produces: `interface RideStore { suspend fun active(): Ride?; suspend fun save(ride: Ride); suspend fun lastPoint(rideId: String): RoutePoint?; suspend fun addPoint(rideId: String, point: RoutePoint, distanceMeters: Double, aliveAt: Long); suspend fun markAlive(rideId: String, at: Long) }`・`interface DeadlineAlarm { fun set(rideId: String, at: Long); fun cancel() }`・`class RideDeps(now, bootCount, newId, maxRecordingMs, store, alarm, recording: (Boolean) -> Unit, autoEnded: (Ride) -> Unit, log)`・`RideDatabase.open(context): RideDatabase`・`RideDatabase.rides(): RideDao`・`class RoomRideStore(dao: RideDao) : RideStore`・`RideDao.ride(id)`・`RideDao.points(rideId)`・`RideDao.upsertRide(entity)`

- [ ] **Step 1: Room と KSP をビルドに足す**

`gradle/libs.versions.toml` の `[versions]` の `robolectric = "4.16"` の下に足す:

```toml
room = "2.8.4"
ksp = "2.3.10"
```

`[libraries]` の `robolectric = ...` の行の下に足す:

```toml
androidx-room-runtime = { module = "androidx.room:room-runtime", version.ref = "room" }
androidx-room-ktx = { module = "androidx.room:room-ktx", version.ref = "room" }
androidx-room-compiler = { module = "androidx.room:room-compiler", version.ref = "room" }
```

`[plugins]` の最後に足す:

```toml
ksp = { id = "com.google.devtools.ksp", version.ref = "ksp" }
room = { id = "androidx.room", version.ref = "room" }
```

`build.gradle.kts`（ルート）の `plugins` の最後に足す:

```kotlin
  alias(libs.plugins.ksp) apply false
  alias(libs.plugins.room) apply false
```

`app/build.gradle.kts` の `plugins` の最後（`alias(libs.plugins.kotlin.serialization)` の下）に足す:

```kotlin
  alias(libs.plugins.ksp)
  alias(libs.plugins.room)
```

同じファイルの `kotlin { jvmToolchain(17) }` の下に足す:

```kotlin

// The schema of every version is kept in git so that later migrations can be tested against it (slice 2 spec §5.1).
room {
  schemaDirectory("$projectDir/schemas")
}
```

同じファイルの `implementation(libs.play.services.location)` の下に足す:

```kotlin
  implementation(libs.androidx.room.runtime)
  implementation(libs.androidx.room.ktx)
  ksp(libs.androidx.room.compiler)
```

- [ ] **Step 2: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt`:

```kotlin
package com.touringproject.v2.store

import android.app.Application
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.HOUR_MS
import com.touringproject.v2.ride.RideStatus
import com.touringproject.v2.ride.RoutePoint
import com.touringproject.v2.ride.end
import com.touringproject.v2.ride.newRide
import com.touringproject.v2.ride.pause
import com.touringproject.v2.ride.resume
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RoomRideStoreTest {
  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
    .allowMainThreadQueries()
    .build()
  private val dao = db.rides()
  private val store = RoomRideStore(dao)
  private val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)

  @After
  fun close() = db.close()

  @Test
  fun a_saved_ride_comes_back_with_its_segments() = runBlocking {
    val resumed = ride.pause(5_000).resume(9_000, 7, 24 * HOUR_MS)
    store.save(ride)
    store.save(resumed)
    assertEquals(resumed, store.active())
  }

  @Test
  fun an_ended_ride_is_not_active() = runBlocking {
    store.save(ride.end(3_000, EndReason.AUTO, 3_000))
    assertNull(store.active())
    assertEquals("auto", dao.ride("r1")?.endReason)
    assertEquals("ended", dao.ride("r1")?.status)
  }

  @Test
  fun a_point_updates_the_distance_and_the_alive_time_together() = runBlocking {
    store.save(ride)
    store.addPoint("r1", RoutePoint(0, 2_000, 35.0, 139.0, 5.0), 12.5, 2_100)
    store.addPoint("r1", RoutePoint(0, 7_000, 35.001, 139.0, null), 120.0, 7_100)
    assertEquals(RoutePoint(0, 7_000, 35.001, 139.0, null), store.lastPoint("r1"))
    assertEquals(2, dao.points("r1").size)
    val active = store.active()!!
    assertEquals(120.0, active.distanceMeters, 0.0)
    assertEquals(7_100L, active.lastAliveAt)
    store.markAlive("r1", 60_000)
    assertEquals(60_000L, store.active()?.lastAliveAt)
  }

  @Test
  fun saving_again_keeps_what_the_backend_has_accepted() = runBlocking {
    store.save(ride)
    dao.upsertRide(dao.ride("r1")!!.copy(sentUpdatedAt = 1_000))
    store.save(ride.pause(5_000))
    assertEquals(1_000L, dao.ride("r1")?.sentUpdatedAt)
    assertEquals(RideStatus.PAUSED, store.active()?.status)
  }
}
```

- [ ] **Step 3: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RoomRideStoreTest'`
Expected: コンパイルの失敗（`Unresolved reference 'RideDatabase'`）

- [ ] **Step 4: 窓口を書く**

`app/src/main/java/com/touringproject/v2/ride/RidePorts.kt`:

```kotlin
package com.touringproject.v2.ride

// Everything the ride controller does to the outside world comes in through these interfaces, so it is testable on the JVM.

interface RideStore {
  /** The ride that is recording or paused, if any (only one can be: US-C-01.005). */
  suspend fun active(): Ride?
  /** Writes the ride and its segments. The sent marker of an earlier write is kept. */
  suspend fun save(ride: Ride)
  suspend fun lastPoint(rideId: String): RoutePoint?
  /** Adds a point and, in the same transaction, the ride's new distance and the time it was seen alive. */
  suspend fun addPoint(rideId: String, point: RoutePoint, distanceMeters: Double, aliveAt: Long)
  suspend fun markAlive(rideId: String, at: Long)
}

/** Wakes the app at a ride's deadline even when the process has died (slice 2 spec §4.4). */
interface DeadlineAlarm {
  fun set(rideId: String, at: Long)
  fun cancel()
}

class RideDeps(
  val now: () -> Long,
  /** The device's boot count, or null when the system does not tell. */
  val bootCount: () -> Int?,
  val newId: () -> String,
  val maxRecordingMs: () -> Long,
  val store: RideStore,
  val alarm: DeadlineAlarm,
  /** Tells the foreground service whether a ride is recording (slice 2 spec §4.2). */
  val recording: (Boolean) -> Unit,
  val autoEnded: (Ride) -> Unit,
  val log: (event: String, data: Map<String, Any?>) -> Unit,
)
```

- [ ] **Step 5: Room の DB と置き場を書く**

`app/src/main/java/com/touringproject/v2/store/RideDatabase.kt`:

```kotlin
package com.touringproject.v2.store

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Transaction
import androidx.room.Upsert

// The device's record of rides (slice 2 spec §5.1). Every schema version is exported to app/schemas and is moved
// forward by a Migration; the database is never rebuilt destructively.

@Entity(tableName = "rides")
data class RideEntity(
  @PrimaryKey val id: String,
  val name: String,
  /** recording / paused / ended */
  val status: String,
  /** manual / auto / shutdown; null until the ride ends */
  val endReason: String?,
  val deadline: Long?,
  val lastAliveAt: Long?,
  val distanceMeters: Double,
  val updatedAt: Long,
  /** The updatedAt the Backend last accepted (slice 2 plan 3); null until then. */
  val sentUpdatedAt: Long?,
)

@Entity(
  tableName = "ride_segments",
  primaryKeys = ["rideId", "seq"],
  foreignKeys = [ForeignKey(entity = RideEntity::class, parentColumns = ["id"], childColumns = ["rideId"], onDelete = ForeignKey.CASCADE)],
)
data class SegmentEntity(val rideId: String, val seq: Int, val startedAt: Long, val endedAt: Long?, val bootCount: Int?)

@Entity(
  tableName = "route_points",
  indices = [Index(value = ["rideId", "segment", "t"])],
  foreignKeys = [ForeignKey(entity = RideEntity::class, parentColumns = ["id"], childColumns = ["rideId"], onDelete = ForeignKey.CASCADE)],
)
data class RoutePointEntity(
  @PrimaryKey(autoGenerate = true) val id: Long = 0,
  val rideId: String,
  val segment: Int,
  val t: Long,
  val lat: Double,
  val lon: Double,
  val accuracy: Double?,
  /** The seq of the chunk it was sent in (slice 2 plan 3); null until then. */
  val chunk: Int?,
)

@Dao
interface RideDao {
  @Query("SELECT * FROM rides WHERE status != 'ended' LIMIT 1")
  suspend fun active(): RideEntity?

  @Query("SELECT * FROM rides WHERE id = :id")
  suspend fun ride(id: String): RideEntity?

  @Query("SELECT * FROM ride_segments WHERE rideId = :rideId ORDER BY seq")
  suspend fun segments(rideId: String): List<SegmentEntity>

  @Upsert
  suspend fun upsertRide(ride: RideEntity)

  @Query("DELETE FROM ride_segments WHERE rideId = :rideId")
  suspend fun deleteSegments(rideId: String)

  @Insert
  suspend fun insertSegments(segments: List<SegmentEntity>)

  @Insert
  suspend fun insertPoint(point: RoutePointEntity)

  @Query("SELECT * FROM route_points WHERE rideId = :rideId ORDER BY id DESC LIMIT 1")
  suspend fun lastPoint(rideId: String): RoutePointEntity?

  @Query("SELECT * FROM route_points WHERE rideId = :rideId ORDER BY id")
  suspend fun points(rideId: String): List<RoutePointEntity>

  @Query("UPDATE rides SET distanceMeters = :distanceMeters, lastAliveAt = :aliveAt WHERE id = :rideId")
  suspend fun updateDistance(rideId: String, distanceMeters: Double, aliveAt: Long)

  @Query("UPDATE rides SET lastAliveAt = :at WHERE id = :rideId")
  suspend fun markAlive(rideId: String, at: Long)

  /** Keeps the sent marker: a save never undoes what the Backend has already accepted. */
  @Transaction
  suspend fun saveRide(ride: RideEntity, segments: List<SegmentEntity>) {
    upsertRide(ride.copy(sentUpdatedAt = ride(ride.id)?.sentUpdatedAt))
    deleteSegments(ride.id)
    insertSegments(segments)
  }

  @Transaction
  suspend fun addPoint(point: RoutePointEntity, distanceMeters: Double, aliveAt: Long) {
    insertPoint(point)
    updateDistance(point.rideId, distanceMeters, aliveAt)
  }
}

@Database(entities = [RideEntity::class, SegmentEntity::class, RoutePointEntity::class], version = 1, exportSchema = true)
abstract class RideDatabase : RoomDatabase() {
  abstract fun rides(): RideDao

  companion object {
    fun open(context: Context): RideDatabase = Room.databaseBuilder(context, RideDatabase::class.java, "rides.db").build()
  }
}
```

`app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt`:

```kotlin
package com.touringproject.v2.store

import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.Ride
import com.touringproject.v2.ride.RideStatus
import com.touringproject.v2.ride.RideStore
import com.touringproject.v2.ride.RoutePoint
import com.touringproject.v2.ride.Segment

private fun RideStatus.column() = name.lowercase()
private fun EndReason.column() = name.lowercase()

fun Ride.toEntity() = RideEntity(id, name, status.column(), endReason?.column(), deadline, lastAliveAt, distanceMeters, updatedAt, null)

fun RideEntity.toRide(segments: List<SegmentEntity>) = Ride(
  id = id,
  name = name,
  status = RideStatus.valueOf(status.uppercase()),
  segments = segments.map { Segment(it.seq, it.startedAt, it.endedAt, it.bootCount) },
  endReason = endReason?.let { EndReason.valueOf(it.uppercase()) },
  deadline = deadline,
  lastAliveAt = lastAliveAt,
  distanceMeters = distanceMeters,
  updatedAt = updatedAt,
)

fun RoutePointEntity.toPoint() = RoutePoint(segment, t, lat, lon, accuracy)

class RoomRideStore(private val dao: RideDao) : RideStore {
  override suspend fun active(): Ride? = dao.active()?.let { it.toRide(dao.segments(it.id)) }

  override suspend fun save(ride: Ride) =
    dao.saveRide(ride.toEntity(), ride.segments.map { SegmentEntity(ride.id, it.seq, it.startedAt, it.endedAt, it.bootCount) })

  override suspend fun lastPoint(rideId: String): RoutePoint? = dao.lastPoint(rideId)?.toPoint()

  override suspend fun addPoint(rideId: String, point: RoutePoint, distanceMeters: Double, aliveAt: Long) =
    dao.addPoint(RoutePointEntity(rideId = rideId, segment = point.segment, t = point.t, lat = point.lat, lon = point.lon, accuracy = point.accuracy, chunk = null), distanceMeters, aliveAt)

  override suspend fun markAlive(rideId: String, at: Long) = dao.markAlive(rideId, at)
}
```

- [ ] **Step 6: 通ることと、スキーマが書き出されたことを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RoomRideStoreTest' && ls app/schemas/com.touringproject.v2.store.RideDatabase/`
Expected: `BUILD SUCCESSFUL`（4件）と `1.json`

- [ ] **Step 7: コミット**

```bash
cd $AND && git add gradle/libs.versions.toml build.gradle.kts app/build.gradle.kts \
  app/src/main/java/com/touringproject/v2/ride/RidePorts.kt \
  app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt \
  app/schemas/com.touringproject.v2.store.RideDatabase/1.json \
  app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt
git commit -m "feat: keep rides, segments and route points in Room"
```

---

### Task 3: 走行の司令塔とルートの位置

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/location/Route.kt`・`app/src/main/java/com/touringproject/v2/ride/RideController.kt`
- Test: `app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt`

**Interfaces:**
- Consumes: Task 1 の型と計算・Task 2 の `RideStore`・`DeadlineAlarm`・`RideDeps`・既存の `location/PositionTracker.kt` の `Subscription` と `location/FusedPositionSource.kt` の `Location.toFix()`
- Produces: `ROUTE_INTERVAL_MS`・`ROUTE_MIN_DISTANCE_M`・`ROUTE_MAX_ACCURACY_M`・`acceptRoutePoint(fix: Fix): Boolean`・`fun interface RouteSource { fun watch(onFix: (Fix) -> Unit): Subscription }`・`class FusedRouteSource(context) : RouteSource`・`class RideController(deps: RideDeps)` の `active: StateFlow<Ride?>`・`storeFailed: StateFlow<Boolean>`・`suspend fun load()`・`start(name): Boolean`・`pause()`・`resume()`・`end(name): Boolean`・`onFix(fix)`・`heartbeat()`・`deadlineReached()`・`shutdown()`

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt`:

```kotlin
package com.touringproject.v2.ride

import com.touringproject.v2.location.Fix
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

private const val MAX = 24 * HOUR_MS

/** An in-memory store that can be told to fail, and a world that records what the controller asked of it. */
private class World(var now: Long = 1_000, var boot: Int? = 7) {
  val rides = mutableMapOf<String, Ride>()
  val points = mutableMapOf<String, MutableList<RoutePoint>>()
  var failWrites = false
  val events = mutableListOf<String>()
  val autoEnded = mutableListOf<Ride>()
  private var ids = 0

  val store = object : RideStore {
    override suspend fun active() = rides.values.firstOrNull { it.status != RideStatus.ENDED }
    override suspend fun save(ride: Ride) {
      if (failWrites) throw IOException("disk full")
      rides[ride.id] = ride
    }
    override suspend fun lastPoint(rideId: String) = points[rideId]?.lastOrNull()
    override suspend fun addPoint(rideId: String, point: RoutePoint, distanceMeters: Double, aliveAt: Long) {
      if (failWrites) throw IOException("disk full")
      points.getOrPut(rideId) { mutableListOf() } += point
      rides[rideId] = rides.getValue(rideId).copy(distanceMeters = distanceMeters, lastAliveAt = aliveAt)
    }
    override suspend fun markAlive(rideId: String, at: Long) {
      if (failWrites) throw IOException("disk full")
      rides[rideId] = rides.getValue(rideId).copy(lastAliveAt = at)
    }
  }

  val controller = RideController(
    RideDeps(
      now = { now },
      bootCount = { boot },
      newId = { "r${++ids}" },
      maxRecordingMs = { MAX },
      store = store,
      alarm = object : DeadlineAlarm {
        override fun set(rideId: String, at: Long) { events += "alarm:$at" }
        override fun cancel() { events += "alarm:cancel" }
      },
      recording = { events += "recording:$it" },
      autoEnded = { autoEnded += it },
      log = { _, _ -> },
    ),
  )

  fun stored() = rides.values.single()
}

private fun fix(t: Long, lat: Double, accuracy: Double? = 5.0) = Fix(lat, 139.0, t, accuracy)

class RideControllerTest {
  @Test
  fun start_saves_the_ride_sets_its_alarm_and_keeps_the_service_recording() = runTest {
    val w = World()
    w.controller.load()
    assertTrue(w.controller.start(" 箱根 "))
    assertEquals("箱根", w.stored().name)
    assertEquals(listOf("alarm:${1_000 + MAX}", "recording:true"), w.events)
    assertEquals("r1", w.controller.active.value?.id)
  }

  @Test
  fun only_one_ride_at_a_time_and_never_without_a_name() = runTest {
    val w = World()
    w.controller.load()
    assertFalse(w.controller.start("  "))
    assertTrue(w.controller.start("箱根"))
    assertFalse(w.controller.start("御殿場"))
    assertEquals(1, w.rides.size)
  }

  @Test
  fun pause_stops_the_service_and_the_alarm_and_resume_starts_both_again() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.events.clear()
    w.now = 5_000
    w.controller.pause()
    assertEquals(RideStatus.PAUSED, w.stored().status)
    assertEquals(listOf("alarm:cancel", "recording:false"), w.events)
    w.events.clear()
    w.now = 9_000
    w.controller.resume()
    assertEquals(listOf("alarm:${9_000 + MAX}", "recording:true"), w.events)
    assertEquals(2, w.stored().segments.size)
  }

  @Test
  fun points_add_up_within_a_segment_and_inaccurate_ones_are_dropped() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.controller.onFix(fix(2_000, 35.000))
    w.controller.onFix(fix(7_000, 35.001))
    w.controller.onFix(fix(12_000, 35.002, accuracy = 80.0))
    assertEquals(2, w.points.getValue("r1").size)
    assertEquals(111.2, w.stored().distanceMeters, 0.5)
    w.controller.pause()
    w.controller.resume()
    w.controller.onFix(fix(20_000, 35.010))
    // The first point after a resume adds nothing: the paused stretch is not ridden distance.
    assertEquals(111.2, w.controller.active.value!!.distanceMeters, 0.5)
  }

  @Test
  fun points_while_paused_are_not_recorded() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.controller.pause()
    w.controller.onFix(fix(2_000, 35.0))
    assertNull(w.points["r1"])
  }

  @Test
  fun the_first_call_at_or_past_the_deadline_ends_the_ride_at_the_deadline_and_says_so() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = 1_000 + MAX + 30_000
    w.controller.heartbeat()
    val ended = w.stored()
    assertEquals(RideStatus.ENDED, ended.status)
    assertEquals(EndReason.AUTO, ended.endReason)
    assertEquals(1_000 + MAX, ended.endedAt())
    assertEquals(listOf(ended), w.autoEnded)
    assertNull(w.controller.active.value)
    // The alarm coming afterwards finds nothing to do.
    w.controller.deadlineReached()
    assertEquals(1, w.autoEnded.size)
  }

  @Test
  fun a_point_past_the_deadline_ends_the_ride_instead_of_being_recorded() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = 1_000 + MAX
    w.controller.onFix(fix(1_000 + MAX, 35.0))
    assertNull(w.points["r1"])
    assertEquals(EndReason.AUTO, w.stored().endReason)
  }

  @Test
  fun the_alarm_before_the_deadline_does_nothing() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = MAX
    w.controller.deadlineReached()
    assertEquals(RideStatus.RECORDING, w.stored().status)
  }

  @Test
  fun a_shutdown_ends_the_ride_now_without_a_notice() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = 50_000
    w.controller.shutdown()
    assertEquals(EndReason.SHUTDOWN, w.stored().endReason)
    assertEquals(50_000L, w.stored().endedAt())
    assertTrue(w.autoEnded.isEmpty())
  }

  @Test
  fun end_keeps_the_ride_when_the_new_name_is_empty() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    assertFalse(w.controller.end(" "))
    assertEquals(RideStatus.RECORDING, w.stored().status)
    assertTrue(w.controller.end("箱根から御殿場へ"))
    assertEquals("箱根から御殿場へ", w.stored().name)
    assertEquals(EndReason.MANUAL, w.stored().endReason)
  }

  @Test
  fun load_after_a_crash_resumes_and_continues_the_distance_from_the_last_point() = runTest {
    val before = World()
    before.controller.load()
    before.controller.start("箱根")
    before.controller.onFix(fix(2_000, 35.000))
    val after = World(now = 30_000).apply {
      rides += before.rides
      points += before.points
    }
    after.controller.load()
    assertEquals(listOf("alarm:${1_000 + MAX}", "recording:true"), after.events)
    after.controller.onFix(fix(31_000, 35.001))
    assertEquals(111.2, after.stored().distanceMeters, 0.5)
  }

  @Test
  fun load_after_a_reboot_ends_the_ride_and_does_not_start_the_service() = runTest {
    val before = World()
    before.controller.load()
    before.controller.start("箱根")
    before.now = 60_000
    before.controller.heartbeat()
    val after = World(now = 300_000, boot = 8).apply { rides += before.rides }
    after.controller.load()
    assertEquals(EndReason.SHUTDOWN, after.stored().endReason)
    assertEquals(60_000L, after.stored().endedAt())
    assertEquals(listOf("alarm:cancel", "recording:false"), after.events)
  }

  @Test
  fun load_past_the_deadline_ends_the_ride_and_says_so() = runTest {
    val before = World()
    before.controller.load()
    before.controller.start("箱根")
    val after = World(now = 2_000 + MAX).apply { rides += before.rides }
    after.controller.load()
    assertEquals(EndReason.AUTO, after.stored().endReason)
    assertEquals(1, after.autoEnded.size)
  }

  @Test
  fun a_fix_from_before_the_segment_started_is_not_recorded() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = 5_000
    w.controller.pause()
    w.now = 9_000
    w.controller.resume()
    w.controller.onFix(fix(4_000, 35.0))
    assertNull(w.points["r1"])
    w.controller.onFix(fix(9_500, 35.0))
    assertEquals(1, w.points.getValue("r1").size)
  }

  @Test
  fun load_of_a_paused_ride_keeps_it_paused_without_the_service() = runTest {
    val before = World()
    before.controller.load()
    before.controller.start("箱根")
    before.controller.pause()
    val after = World(now = 300_000).apply { rides += before.rides }
    after.controller.load()
    assertEquals(RideStatus.PAUSED, after.controller.active.value?.status)
    assertTrue(after.events.isEmpty())
  }

  @Test
  fun the_alarm_after_the_rider_ended_does_nothing() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.controller.end("箱根")
    w.now = 2_000 + MAX
    w.controller.deadlineReached()
    assertEquals(EndReason.MANUAL, w.stored().endReason)
    assertTrue(w.autoEnded.isEmpty())
  }

  @Test
  fun a_ride_starts_even_when_it_cannot_be_saved() = runTest {
    val w = World()
    w.controller.load()
    w.failWrites = true
    assertTrue(w.controller.start("箱根"))
    assertTrue(w.controller.storeFailed.value)
    assertEquals(RideStatus.RECORDING, w.controller.active.value?.status)
    assertTrue("recording:true" in w.events)
  }

  @Test
  fun a_failed_write_is_shown_and_the_ride_goes_on() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.failWrites = true
    w.controller.onFix(fix(2_000, 35.000))
    assertTrue(w.controller.storeFailed.value)
    assertEquals(RideStatus.RECORDING, w.controller.active.value?.status)
    w.failWrites = false
    w.controller.onFix(fix(7_000, 35.001))
    assertFalse(w.controller.storeFailed.value)
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideControllerTest'`
Expected: コンパイルの失敗（`Unresolved reference 'RideController'`）

- [ ] **Step 3: ルートの位置を書く**

`app/src/main/java/com/touringproject/v2/location/Route.kt`:

```kotlin
package com.touringproject.v2.location

import android.annotation.SuppressLint
import android.content.Context
import android.os.Looper
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority

// The route of a ride (slice 2 spec §4.3). The values are reviewed after real rides; the rider does not change them.
const val ROUTE_INTERVAL_MS = 5_000L
const val ROUTE_MIN_DISTANCE_M = 10f
const val ROUTE_MAX_ACCURACY_M = 50.0

/** US-C-02.005: a point less accurate than 50 m is dropped. A point without an accuracy is kept. */
fun acceptRoutePoint(fix: Fix): Boolean = fix.accuracy == null || fix.accuracy <= ROUTE_MAX_ACCURACY_M

fun interface RouteSource {
  fun watch(onFix: (Fix) -> Unit): Subscription
}

// A separate request from the ask's 1 s one (PositionTracker): Fused serves both, and the two never mix.
// Without the location permission the request throws SecurityException; the caller then records no points.
@SuppressLint("MissingPermission")
class FusedRouteSource(context: Context) : RouteSource {
  private val client = LocationServices.getFusedLocationProviderClient(context)

  override fun watch(onFix: (Fix) -> Unit): Subscription {
    val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, ROUTE_INTERVAL_MS)
      .setMinUpdateDistanceMeters(ROUTE_MIN_DISTANCE_M)
      .build()
    val callback = object : LocationCallback() {
      override fun onLocationResult(result: LocationResult) = result.locations.forEach { onFix(it.toFix()) }
    }
    client.requestLocationUpdates(request, callback, Looper.getMainLooper())
    return Subscription { client.removeLocationUpdates(callback) }
  }
}
```

- [ ] **Step 4: 司令塔を書く**

`app/src/main/java/com/touringproject/v2/ride/RideController.kt`:

```kotlin
package com.touringproject.v2.ride

import com.touringproject.v2.location.Fix
import com.touringproject.v2.location.acceptRoutePoint
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Starts, pauses, resumes and ends the ride, and takes in its route points. The service, the deadline alarm, the
 * shutdown broadcast and the screens all call in here; one lock keeps their calls in order. Every call waits for
 * load(), which settles a ride left over from before the process started. A failed write is logged and shown
 * (storeFailed) but never stops the ride (slice 2 spec §8).
 */
class RideController(private val deps: RideDeps) {
  private val mutex = Mutex()
  private val loaded = CompletableDeferred<Unit>()
  private val activeRide = MutableStateFlow<Ride?>(null)
  /** The ride that is recording or paused; null when none is. */
  val active: StateFlow<Ride?> = activeRide.asStateFlow()
  private val storeFailing = MutableStateFlow(false)
  /** True while the last write to the device's database failed. */
  val storeFailed: StateFlow<Boolean> = storeFailing.asStateFlow()
  // The last stored point of the active ride, for the distance of the next one.
  private var lastPoint: RoutePoint? = null

  suspend fun load() {
    mutex.withLock {
      if (loaded.isCompleted) return
      val d = deps
      val ride = read("active") { d.store.active() }
      val now = d.now()
      val decision = reconcile(ride, now, d.bootCount())
      d.log("ride_load", mapOf("ride" to ride?.id, "decision" to decision.toString()))
      when (decision) {
        Reconcile.Nothing -> Unit
        is Reconcile.EndShutdown -> finish(ride!!.end(decision.at, EndReason.SHUTDOWN, now))
        is Reconcile.EndAuto -> finish(ride!!.end(decision.at, EndReason.AUTO, now))
        Reconcile.KeepPaused -> activeRide.value = ride
        Reconcile.Resume -> {
          activeRide.value = ride
          lastPoint = read("last_point") { d.store.lastPoint(ride!!.id) }
          d.alarm.set(ride!!.id, ride.deadline!!)
          d.recording(true)
        }
      }
      loaded.complete(Unit)
    }
  }

  private suspend fun <T> read(op: String, block: suspend () -> T?): T? = try {
    block()
  } catch (e: CancellationException) {
    throw e
  } catch (e: Exception) {
    failed(op, e)
    null
  }

  private suspend fun write(op: String, block: suspend () -> Unit) {
    try {
      block()
      storeFailing.value = false
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      failed(op, e)
    }
  }

  private fun failed(op: String, e: Exception) {
    deps.log("store_failed", mapOf("op" to op, "error" to e.toString()))
    storeFailing.value = true
  }

  private suspend fun <T> locked(block: suspend () -> T): T {
    loaded.await()
    return mutex.withLock { block() }
  }

  /** Returns false when the name is not usable or another ride is already recording or paused. */
  suspend fun start(name: String): Boolean = locked {
    val d = deps
    val clean = rideName(name)
    if (clean == null || activeRide.value != null) return@locked false
    val ride = newRide(d.newId(), clean, d.now(), d.bootCount(), d.maxRecordingMs())
    write("save") { d.store.save(ride) }
    activeRide.value = ride
    lastPoint = null
    d.alarm.set(ride.id, ride.deadline!!)
    d.recording(true)
    d.log("ride_start", mapOf("ride" to ride.id))
    true
  }

  suspend fun pause() = locked {
    val ride = activeRide.value?.takeIf { it.status == RideStatus.RECORDING } ?: return@locked
    val d = deps
    val paused = ride.pause(d.now())
    write("save") { d.store.save(paused) }
    activeRide.value = paused
    d.alarm.cancel()
    d.recording(false)
  }

  suspend fun resume() = locked {
    val ride = activeRide.value?.takeIf { it.status == RideStatus.PAUSED } ?: return@locked
    val d = deps
    val resumed = ride.resume(d.now(), d.bootCount(), d.maxRecordingMs())
    write("save") { d.store.save(resumed) }
    activeRide.value = resumed
    lastPoint = null
    d.alarm.set(resumed.id, resumed.deadline!!)
    d.recording(true)
  }

  /** SC-04. Returns false when the name is not usable. */
  suspend fun end(name: String): Boolean = locked {
    val ride = activeRide.value ?: return@locked true
    val clean = rideName(name) ?: return@locked false
    val now = deps.now()
    finish(ride.end(now, EndReason.MANUAL, now, clean))
    true
  }

  suspend fun onFix(fix: Fix) = locked {
    val ride = activeRide.value?.takeIf { it.status == RideStatus.RECORDING } ?: return@locked
    val d = deps
    val now = d.now()
    if (autoEndIfDue(ride, now)) return@locked
    // Fused may hand over a cached fix when the watch starts again: one from before this segment is not on its route.
    if (!acceptRoutePoint(fix) || fix.timestamp < ride.segments.last().startedAt) {
      write("alive") { d.store.markAlive(ride.id, now) }
      activeRide.value = ride.copy(lastAliveAt = now)
      return@locked
    }
    val point = RoutePoint(ride.segments.last().seq, fix.timestamp, fix.latitude, fix.longitude, fix.accuracy)
    val distance = ride.distanceMeters + stepMeters(lastPoint, point)
    write("point") { d.store.addPoint(ride.id, point, distance, now) }
    lastPoint = point
    activeRide.value = ride.copy(distanceMeters = distance, lastAliveAt = now)
  }

  /** Called every minute while the service records: the ride is alive, and its deadline may have come. */
  suspend fun heartbeat() = locked {
    val ride = activeRide.value?.takeIf { it.status == RideStatus.RECORDING } ?: return@locked
    val now = deps.now()
    if (autoEndIfDue(ride, now)) return@locked
    write("alive") { deps.store.markAlive(ride.id, now) }
    activeRide.value = ride.copy(lastAliveAt = now)
  }

  /** The deadline alarm went off. It may come late; it never comes early. */
  suspend fun deadlineReached() = locked {
    val ride = activeRide.value?.takeIf { it.status == RideStatus.RECORDING } ?: return@locked
    autoEndIfDue(ride, deps.now())
    Unit
  }

  /** The device is shutting down (ACTION_SHUTDOWN). */
  suspend fun shutdown() = locked {
    val ride = activeRide.value ?: return@locked
    val now = deps.now()
    finish(ride.end(now, EndReason.SHUTDOWN, now))
  }

  private suspend fun autoEndIfDue(ride: Ride, now: Long): Boolean {
    val deadline = ride.deadline ?: return false
    if (now < deadline) return false
    finish(ride.end(deadline, EndReason.AUTO, now))
    return true
  }

  private suspend fun finish(ended: Ride) {
    val d = deps
    write("save") { d.store.save(ended) }
    activeRide.value = null
    lastPoint = null
    d.alarm.cancel()
    d.recording(false)
    d.log("ride_end", mapOf("ride" to ended.id, "reason" to ended.endReason))
    if (ended.endReason == EndReason.AUTO) d.autoEnded(ended)
  }
}
```

- [ ] **Step 5: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideControllerTest'`
Expected: `BUILD SUCCESSFUL`（18件）

- [ ] **Step 6: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/location/Route.kt app/src/main/java/com/touringproject/v2/ride/RideController.kt \
  app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
git commit -m "feat: add the ride controller and the route location request"
```

---

### Task 4: サービスの取りまとめ

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/service/ServiceCoordinator.kt`
- Test: `app/src/test/java/com/touringproject/v2/service/ServiceCoordinatorTest.kt`

**Interfaces:**
- Consumes: 既存の `ask/AskPorts.kt` の `interface KeepAlive { fun start(); fun stop() }`（`start` は始められないとき例外を投げる）
- Produces: `enum class ServiceUse { LOCATION, MICROPHONE, MEDIA_PLAYBACK }`・`serviceUses(recording: Boolean, asking: Boolean): Set<ServiceUse>`・`interface ServiceLauncher { fun start(); fun stop() }`・`interface RunningService { fun apply(uses: Set<ServiceUse>) }`・`class ServiceCoordinator(launcher, log: (String, Throwable) -> Unit)` の `running: RunningService?`（読み取りだけ）・`uses`・`attach(service)`・`detach(service)`・`setRecording(on)`・`refresh()`・`keepAlive: KeepAlive`

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/service/ServiceCoordinatorTest.kt`:

```kotlin
package com.touringproject.v2.service

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class ServiceCoordinatorTest {
  private val events = mutableListOf<String>()
  private var refuseMicrophone = false
  private val launcher = object : ServiceLauncher {
    override fun start() { events += "start" }
    override fun stop() { events += "stop" }
  }
  private val service = object : RunningService {
    override fun apply(uses: Set<ServiceUse>) {
      if (refuseMicrophone && ServiceUse.MICROPHONE in uses) throw SecurityException("microphone from the background")
      events += "apply:${uses.sorted()}"
    }
  }
  private val coordinator = ServiceCoordinator(launcher) { _, _ -> events += "logged" }

  @Test
  fun the_uses_follow_the_ride_and_the_ask() {
    assertEquals(emptySet<ServiceUse>(), serviceUses(recording = false, asking = false))
    assertEquals(setOf(ServiceUse.LOCATION), serviceUses(recording = true, asking = false))
    assertEquals(setOf(ServiceUse.MICROPHONE, ServiceUse.MEDIA_PLAYBACK), serviceUses(recording = false, asking = true))
    assertEquals(ServiceUse.entries.toSet(), serviceUses(recording = true, asking = true))
  }

  @Test
  fun without_a_running_service_it_is_started_and_stopped() {
    coordinator.setRecording(true)
    coordinator.setRecording(false)
    assertEquals(listOf("start", "stop"), events)
  }

  @Test
  fun a_running_service_changes_its_types_and_an_ask_during_a_ride_adds_the_microphone() {
    coordinator.setRecording(true)
    coordinator.attach(service)
    coordinator.keepAlive.start()
    coordinator.keepAlive.stop()
    coordinator.setRecording(false)
    assertEquals(
      listOf(
        "start",
        "apply:[LOCATION, MICROPHONE, MEDIA_PLAYBACK]",
        "apply:[LOCATION]",
        "apply:[]",
      ),
      events,
    )
  }

  @Test
  fun when_the_microphone_is_refused_the_ask_fails_and_the_ride_keeps_its_location() {
    coordinator.setRecording(true)
    coordinator.attach(service)
    refuseMicrophone = true
    assertThrows(SecurityException::class.java) { coordinator.keepAlive.start() }
    assertEquals(setOf(ServiceUse.LOCATION), coordinator.uses)
    assertEquals(listOf("start", "apply:[LOCATION]"), events)
  }

  @Test
  fun a_refused_start_for_the_ride_is_logged_and_refresh_tries_again() {
    var refuse = true
    val picky = ServiceCoordinator(object : ServiceLauncher {
      override fun start() {
        if (refuse) throw IllegalStateException("not allowed from the background")
        events += "start"
      }
      override fun stop() { events += "stop" }
    }) { _, _ -> events += "logged" }
    picky.setRecording(true)
    refuse = false
    picky.refresh()
    assertEquals(listOf("logged", "start"), events)
  }

  @Test
  fun refresh_leaves_a_running_service_alone() {
    coordinator.setRecording(true)
    coordinator.attach(service)
    events.clear()
    coordinator.refresh()
    assertEquals(emptyList<String>(), events)
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ServiceCoordinatorTest'`
Expected: コンパイルの失敗（`Unresolved reference 'ServiceCoordinator'`）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/service/ServiceCoordinator.kt`:

```kotlin
package com.touringproject.v2.service

import com.touringproject.v2.ask.KeepAlive

// One foreground service serves both the ride and the ask; what it is used for decides its types (slice 2 spec §4.2).

enum class ServiceUse { LOCATION, MICROPHONE, MEDIA_PLAYBACK }

fun serviceUses(recording: Boolean, asking: Boolean): Set<ServiceUse> = buildSet {
  if (recording) add(ServiceUse.LOCATION)
  if (asking) {
    add(ServiceUse.MICROPHONE)
    add(ServiceUse.MEDIA_PLAYBACK)
  }
}

/** Starts and stops the service from outside it. */
interface ServiceLauncher {
  /** Throws when the system does not let the app start a foreground service now (e.g. from the background). */
  fun start()
  fun stop()
}

/** The running service. */
interface RunningService {
  /** Changes the service's types, or stops it when uses is empty. Throws when the system refuses a type. */
  fun apply(uses: Set<ServiceUse>)
}

/**
 * Keeps the service in line with whether a ride is recording and whether an ask is under way. Call it from the
 * main thread only. The ask's KeepAlive throws when its types cannot be added, so the ask fails instead of going
 * on without the service; the ride goes on either way.
 */
class ServiceCoordinator(private val launcher: ServiceLauncher, private val log: (String, Throwable) -> Unit) {
  private var recording = false
  private var asking = false
  /** The running service, if any (read by the emulator tests). */
  var running: RunningService? = null
    private set

  val uses: Set<ServiceUse> get() = serviceUses(recording, asking)

  fun attach(service: RunningService) {
    running = service
  }

  fun detach(service: RunningService) {
    if (running === service) running = null
  }

  fun setRecording(on: Boolean) {
    recording = on
    applyQuietly()
  }

  /** Brings the service back when it should run but does not (e.g. it could not start while the app was in the background). */
  fun refresh() {
    if (uses.isNotEmpty() && running == null) applyQuietly()
  }

  val keepAlive: KeepAlive = object : KeepAlive {
    override fun start() {
      asking = true
      try {
        apply()
      } catch (e: Exception) {
        asking = false
        applyQuietly()
        throw e
      }
    }

    override fun stop() {
      asking = false
      applyQuietly()
    }
  }

  private fun apply() {
    val wanted = uses
    val service = running
    when {
      wanted.isEmpty() -> if (service != null) service.apply(wanted) else launcher.stop()
      service != null -> service.apply(wanted)
      else -> launcher.start()
    }
  }

  private fun applyQuietly() {
    try {
      apply()
    } catch (e: Exception) {
      log("service_apply_failed uses=$uses", e)
    }
  }
}
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ServiceCoordinatorTest'`
Expected: `BUILD SUCCESSFUL`（6件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/service/ServiceCoordinator.kt app/src/test/java/com/touringproject/v2/service/ServiceCoordinatorTest.kt
git commit -m "feat: decide the foreground service types from the ride and the ask"
```

---

### Task 5: サービス・締め切りのアラーム・組み立て

**Files:**
- Modify（書き換え）: `app/src/main/java/com/touringproject/v2/service/RideForegroundService.kt`（`ServiceKeepAlive` を消し、`ContextServiceLauncher` に替える）
- Create: `app/src/main/java/com/touringproject/v2/service/RideAlarms.kt`
- Modify: `app/src/main/java/com/touringproject/v2/AppGraph.kt`・`app/src/main/java/com/touringproject/v2/MainActivity.kt`・`app/src/main/AndroidManifest.xml`・`scripts/check-release-permissions.sh`
- Test（書き換え）: `app/src/test/java/com/touringproject/v2/service/RideForegroundServiceTest.kt`

**Interfaces:**
- Consumes: Task 2 の `DeadlineAlarm`・`RideDeps`・`RideDatabase`・`RoomRideStore`・Task 3 の `RideController`・`RouteSource`・`FusedRouteSource`・Task 4 の `ServiceCoordinator`・`ServiceUse`・`ServiceLauncher`・`RunningService`
- Produces: `HEARTBEAT_MS`・`serviceTypes(uses): Int`・`class RideForegroundService : Service(), RunningService`・`class ContextServiceLauncher(context) : ServiceLauncher`・`class AlarmDeadline(context) : DeadlineAlarm`・`class DeadlineReceiver : BroadcastReceiver`・`class RideNotices(context)` の `autoEnded(ride)`・`AppGraph` の `serviceCoordinator`・`routeSource`・`rideStore`・`rides`

- [ ] **Step 1: 失敗するテストを書く（今のテストを置き換える）**

`app/src/test/java/com/touringproject/v2/service/RideForegroundServiceTest.kt`:

```kotlin
package com.touringproject.v2.service

import android.app.AlarmManager
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Looper
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.touringproject.v2.TouringApp
import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.HOUR_MS
import com.touringproject.v2.ride.newRide
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.Shadows.shadowOf
import java.time.Duration

@RunWith(AndroidJUnit4::class)
class RideForegroundServiceTest {
  private val app = ApplicationProvider.getApplicationContext<TouringApp>()

  // Room works on its own threads and resumes on the main looper, so the main looper is turned until the result shows.
  private fun waitUntil(condition: () -> Boolean) {
    repeat(200) {
      shadowOf(Looper.getMainLooper()).idle()
      if (condition()) return
      Thread.sleep(10)
    }
    throw AssertionError("condition never became true")
  }

  private fun startedService() = Robolectric.buildService(RideForegroundService::class.java).create().startCommand(0, 1)

  @Test
  fun the_launcher_starts_and_stops_the_service() {
    val launcher = ContextServiceLauncher(app)
    launcher.start()
    assertEquals(RideForegroundService::class.java.name, shadowOf(app).nextStartedService.component?.className)
    launcher.stop()
    assertEquals(RideForegroundService::class.java.name, shadowOf(app).nextStoppedService.component?.className)
  }

  @Test
  fun the_service_takes_the_types_it_is_used_for() {
    val controller = startedService()
    val service = controller.get()
    service.apply(setOf(ServiceUse.LOCATION))
    assertEquals(ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION, service.foregroundServiceType)
    assertEquals("走行を記録中", shadowOf(shadowOf(service).lastForegroundNotification).contentText)
    service.apply(ServiceUse.entries.toSet())
    assertEquals(
      ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
      service.foregroundServiceType,
    )
    service.apply(setOf(ServiceUse.MICROPHONE, ServiceUse.MEDIA_PLAYBACK))
    assertEquals("応答中", shadowOf(shadowOf(service).lastForegroundNotification).contentText)
  }

  @Test
  fun started_with_nothing_to_do_it_stops_itself() {
    val controller = startedService()
    waitUntil { shadowOf(controller.get()).isStoppedBySelf }
  }

  @Test
  fun the_ask_keep_alive_reaches_the_running_service() {
    val controller = startedService()
    val coordinator = app.graph.serviceCoordinator
    coordinator.keepAlive.start()
    assertEquals(
      ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
      controller.get().foregroundServiceType,
    )
    coordinator.keepAlive.stop()
    assertTrue(shadowOf(controller.get()).isStoppedBySelf)
  }

  @Test
  fun a_shutdown_ends_the_recording_ride() {
    val rides = app.graph.rides
    runBlocking { rides.load() }
    runBlocking { rides.start("箱根") }
    startedService()
    app.sendBroadcast(Intent(Intent.ACTION_SHUTDOWN))
    waitUntil { rides.active.value == null }
  }

  @Test
  fun while_recording_the_ride_is_marked_alive_every_minute() {
    val rides = app.graph.rides
    runBlocking { rides.load() }
    runBlocking { rides.start("箱根") }
    val controller = startedService()
    waitUntil { controller.get().foregroundServiceType == ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION }
    val before = runBlocking { app.graph.rideStore.active() }!!.lastAliveAt!!
    Thread.sleep(5)
    shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(HEARTBEAT_MS))
    waitUntil { runBlocking { app.graph.rideStore.active() }!!.lastAliveAt!! > before }
  }

  @Test
  fun the_deadline_alarm_is_set_and_cancelled() {
    val alarm = AlarmDeadline(app)
    val alarms = shadowOf(app.getSystemService(AlarmManager::class.java))
    alarm.set("r1", 123_456)
    assertEquals(123_456L, alarms.peekNextScheduledAlarm()?.triggerAtTime)
    alarm.cancel()
    assertNull(alarms.peekNextScheduledAlarm())
  }

  @Test
  fun the_deadline_receiver_ends_an_overdue_ride_and_posts_the_notice() {
    // Saved before the app's own load runs, as if the process had died while recording.
    runBlocking { app.graph.rideStore.save(newRide("r1", "箱根", 0, null, 1_000)) }
    app.sendBroadcast(Intent(app, DeadlineReceiver::class.java))
    waitUntil { app.graph.rides.active.value == null && runBlocking { app.graph.rideStore.active() } == null }
    val posted = shadowOf(app.getSystemService(NotificationManager::class.java)).allNotifications.single()
    assertEquals("走行を自動で終了しました", shadowOf(posted).contentTitle)
  }

  @Test
  fun the_auto_end_notice_names_the_ride() {
    val ride = newRide("r1", "箱根", 0, 7, 24 * HOUR_MS).copy(endReason = EndReason.AUTO)
    RideNotices(app).autoEnded(ride)
    val posted = shadowOf(app.getSystemService(NotificationManager::class.java)).allNotifications.single()
    assertEquals("走行を自動で終了しました", shadowOf(posted).contentTitle)
    assertNotNull(shadowOf(posted).contentText?.toString()?.takeIf { "「箱根」" in it })
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideForegroundServiceTest'`
Expected: コンパイルの失敗（`Unresolved reference 'ContextServiceLauncher'` など）

- [ ] **Step 3: サービスを書き換える**

`app/src/main/java/com/touringproject/v2/service/RideForegroundService.kt`:

```kotlin
package com.touringproject.v2.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.util.Log
import androidx.core.content.ContextCompat
import com.touringproject.v2.MainActivity
import com.touringproject.v2.TouringApp
import com.touringproject.v2.location.Subscription
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

const val HEARTBEAT_MS = 60_000L

fun serviceTypes(uses: Set<ServiceUse>): Int = uses.fold(0) { types, use ->
  types or when (use) {
    ServiceUse.LOCATION -> ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
    ServiceUse.MICROPHONE -> ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
    ServiceUse.MEDIA_PLAYBACK -> ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
  }
}

/**
 * Keeps the process alive while a ride records (taking in its route, every minute marking it alive and checking its
 * deadline) and while an answer is awaited and read out (adr/0004, adr/0005, slice 2 spec §4.2). Its notification
 * doubles as the notice that a ride is recording (EX-03).
 */
class RideForegroundService : Service(), RunningService {
  private val graph get() = (application as TouringApp).graph
  private lateinit var scope: CoroutineScope
  private var foreground = false
  private var route: Subscription? = null
  private var heartbeat: Job? = null

  private val shutdown = object : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
      val pending = goAsync()
      scope.launch {
        try {
          graph.rides.shutdown()
        } finally {
          pending.finish()
        }
      }
    }
  }

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onCreate() {
    super.onCreate()
    scope = MainScope()
    ContextCompat.registerReceiver(this, shutdown, IntentFilter(Intent.ACTION_SHUTDOWN), ContextCompat.RECEIVER_NOT_EXPORTED)
    graph.serviceCoordinator.attach(this)
  }

  // Also reached when the system restarts the service after the process died (START_STICKY): the ride left recording
  // is settled first (RideController.load), then the service takes on whatever is still wanted.
  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    scope.launch {
      graph.rides.load()
      val uses = graph.serviceCoordinator.uses
      try {
        apply(uses)
      } catch (e: RuntimeException) {
        // Android 14+ refuses a while-in-use type started from the background, or without its permission.
        Log.w("trv2.ride", "startForeground failed uses=$uses", e)
        val fallback = uses - setOf(ServiceUse.MICROPHONE, ServiceUse.MEDIA_PLAYBACK)
        if (fallback != uses && fallback.isNotEmpty()) runCatching { apply(fallback) }.onFailure { stop() } else stop()
      }
    }
    return START_STICKY
  }

  override fun apply(uses: Set<ServiceUse>) {
    if (uses.isEmpty()) {
      stop()
      return
    }
    startForeground(NOTIFICATION_ID, notification(uses), serviceTypes(uses))
    foreground = true
    if (ServiceUse.LOCATION in uses) watch() else unwatch()
  }

  private fun stop() {
    // From here on a new request starts the service again instead of reaching this stopping one.
    graph.serviceCoordinator.detach(this)
    unwatch()
    // A service started with startForegroundService must reach the foreground once, even to stop at once.
    if (!foreground) runCatching { startForeground(NOTIFICATION_ID, notification(emptySet()), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK) }
    stopForeground(STOP_FOREGROUND_REMOVE)
    foreground = false
    stopSelf()
  }

  private fun watch() {
    if (route != null) return
    val rides = graph.rides
    route = runCatching { graph.routeSource.watch { fix -> scope.launch { rides.onFix(fix) } } }
      .onFailure { Log.w("trv2.route", "route watch failed", it) }
      .getOrNull()
    heartbeat = scope.launch {
      while (true) {
        delay(HEARTBEAT_MS)
        rides.heartbeat()
      }
    }
  }

  private fun unwatch() {
    route?.remove()
    route = null
    heartbeat?.cancel()
    heartbeat = null
  }

  private fun notification(uses: Set<ServiceUse>): Notification {
    val manager = getSystemService(NotificationManager::class.java)
    manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "走行の記録と応答", NotificationManager.IMPORTANCE_LOW))
    val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
    return Notification.Builder(this, CHANNEL_ID)
      .setContentTitle("Touring V2")
      .setContentText(if (ServiceUse.LOCATION in uses) "走行を記録中" else "応答中")
      .setSmallIcon(android.R.drawable.ic_btn_speak_now)
      .setContentIntent(open)
      .setOngoing(true)
      .build()
  }

  override fun onDestroy() {
    unwatch()
    unregisterReceiver(shutdown)
    graph.serviceCoordinator.detach(this)
    scope.cancel()
    super.onDestroy()
  }

  companion object {
    const val CHANNEL_ID = "trv2_answer"
    const val NOTIFICATION_ID = 1
  }
}

class ContextServiceLauncher(private val context: Context) : ServiceLauncher {
  override fun start() {
    context.startForegroundService(Intent(context, RideForegroundService::class.java))
  }

  override fun stop() {
    context.stopService(Intent(context, RideForegroundService::class.java))
  }
}
```

- [ ] **Step 4: 締め切りのアラームと通知を書く**

`app/src/main/java/com/touringproject/v2/service/RideAlarms.kt`:

```kotlin
package com.touringproject.v2.service

import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationManagerCompat
import com.touringproject.v2.MainActivity
import com.touringproject.v2.TouringApp
import com.touringproject.v2.ride.DeadlineAlarm
import com.touringproject.v2.ride.Ride
import kotlinx.coroutines.launch

// An inexact alarm needs no permission (an exact one does from Android 12, and is off by default from 14). It may
// come minutes late; the ride still ends at its deadline, so only the notice is late (slice 2 spec §4.4).
class AlarmDeadline(private val context: Context) : DeadlineAlarm {
  private val alarms = context.getSystemService(AlarmManager::class.java)

  private fun pending() = PendingIntent.getBroadcast(
    context, 0, Intent(context, DeadlineReceiver::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
  )

  override fun set(rideId: String, at: Long) = alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending())

  override fun cancel() = alarms.cancel(pending())
}

/** Starts the process if it has died; RideController.load then settles the ride before deadlineReached runs. */
class DeadlineReceiver : BroadcastReceiver() {
  override fun onReceive(context: Context, intent: Intent) {
    val graph = (context.applicationContext as TouringApp).graph
    val pending = goAsync()
    graph.scope.launch {
      try {
        graph.rides.deadlineReached()
      } finally {
        pending.finish()
      }
    }
  }
}

class RideNotices(private val context: Context) {
  /** US-C-08.004. Skipped when the rider has turned notifications off. */
  fun autoEnded(ride: Ride) {
    if (!NotificationManagerCompat.from(context).areNotificationsEnabled()) return
    val manager = context.getSystemService(NotificationManager::class.java)
    manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "走行の自動終了", NotificationManager.IMPORTANCE_DEFAULT))
    val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
    val notification = Notification.Builder(context, CHANNEL_ID)
      .setContentTitle("走行を自動で終了しました")
      .setContentText("「${ride.name}」は、続けて記録した時間が最長時間に達したので終了しました")
      .setSmallIcon(android.R.drawable.ic_dialog_info)
      .setContentIntent(open)
      .setAutoCancel(true)
      .build()
    manager.notify(NOTIFICATION_ID, notification)
  }

  companion object {
    const val CHANNEL_ID = "trv2_ride_notice"
    const val NOTIFICATION_ID = 2
  }
}
```

- [ ] **Step 5: `AppGraph` で組み立てる**

`app/src/main/java/com/touringproject/v2/AppGraph.kt` を次のように直す。

import に足す（`android.util.Log` の上）:

```kotlin
import android.provider.Settings as SystemSettings
```

`import com.touringproject.v2.location.FusedPositionSource` の下に足す:

```kotlin
import com.touringproject.v2.location.FusedRouteSource
```

`import com.touringproject.v2.location.PositionTracker` の下に足す:

```kotlin
import com.touringproject.v2.location.RouteSource
```

`import com.touringproject.v2.service.ServiceKeepAlive` を、次に置き換える:

```kotlin
import com.touringproject.v2.ride.DEFAULT_MAX_RECORDING_MS
import com.touringproject.v2.ride.RideController
import com.touringproject.v2.ride.RideDeps
import com.touringproject.v2.service.AlarmDeadline
import com.touringproject.v2.service.ContextServiceLauncher
import com.touringproject.v2.service.RideNotices
import com.touringproject.v2.service.ServiceCoordinator
```

`import com.touringproject.v2.settings.SettingsRepository` の下に足す:

```kotlin
import com.touringproject.v2.store.RideDatabase
import com.touringproject.v2.store.RoomRideStore
```

`import java.io.File` の下に足す:

```kotlin
import java.util.UUID
```

`private val flowState = MutableStateFlow(IDLE)` の上に足す:

```kotlin
  val serviceCoordinator = ServiceCoordinator(ContextServiceLauncher(context)) { message, e -> Log.w("trv2.ride", message, e) }
  val routeSource: RouteSource = FusedRouteSource(context)
  private val database = RideDatabase.open(context)
  val rideStore = RoomRideStore(database.rides())
  private val notices = RideNotices(context)

  val rides = RideController(
    RideDeps(
      now = System::currentTimeMillis,
      bootCount = { runCatching { SystemSettings.Global.getInt(context.contentResolver, SystemSettings.Global.BOOT_COUNT) }.getOrNull() },
      newId = { UUID.randomUUID().toString() },
      maxRecordingMs = { DEFAULT_MAX_RECORDING_MS },
      store = rideStore,
      alarm = AlarmDeadline(context),
      recording = serviceCoordinator::setRecording,
      autoEnded = notices::autoEnded,
      log = { event, data -> Log.i("trv2.ride", "$event $data") },
    ),
  )

```

`AskDeps` の `service = ServiceKeepAlive(context),` を置き換える:

```kotlin
      service = serviceCoordinator.keepAlive,
```

`init` の `audioRoute.onVoiceRecognitionEnded = { router.recognitionEnded() }` の下に足す:

```kotlin
    // Settles a ride left recording or paused before this process started (slice 2 spec §4.5).
    scope.launch { rides.load() }
```

- [ ] **Step 6: 前面に来たときにサービスを始め直す**

`app/src/main/java/com/touringproject/v2/MainActivity.kt` の `override fun onNewIntent(` の上に足す:

```kotlin
  // A ride's service could not start while the app was in the background (slice 2 spec §4.5); it can now.
  override fun onStart() {
    super.onStart()
    graph.serviceCoordinator.refresh()
  }

```

- [ ] **Step 7: マニフェストと権限の検査を直す**

`app/src/main/AndroidManifest.xml` の `FOREGROUND_SERVICE_MEDIA_PLAYBACK` の行の下に足す:

```xml
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION" />
```

同じファイルの `<service ...RideForegroundService ... />` の `android:foregroundServiceType="microphone|mediaPlayback" />` を、次に置き換える:

```xml
      android:foregroundServiceType="location|microphone|mediaPlayback" />
    <!-- Ends a ride at its deadline even when the process has died (slice 2 spec §4.4). -->
    <receiver
      android:name=".service.DeadlineReceiver"
      android:exported="false" />
```

`scripts/check-release-permissions.sh` の `expected` の一覧で、`android.permission.FOREGROUND_SERVICE` の下に1行足す:

```text
android.permission.FOREGROUND_SERVICE_LOCATION
```

- [ ] **Step 8: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*service*'`
Expected: `BUILD SUCCESSFUL`。`RideForegroundServiceTest` 9件・`ServiceCoordinatorTest` 6件

- [ ] **Step 9: 全体を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t5.log 2>&1; tail -3 /tmp/trv2-t5.log`
Expected: `BUILD SUCCESSFUL`。既存のテスト（`AskControllerTest`・`MainActivityTest` など）も通る

- [ ] **Step 10: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/service/RideForegroundService.kt app/src/main/java/com/touringproject/v2/service/RideAlarms.kt \
  app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/MainActivity.kt \
  app/src/main/AndroidManifest.xml scripts/check-release-permissions.sh \
  app/src/test/java/com/touringproject/v2/service/RideForegroundServiceTest.kt
git commit -m "feat: record the route in the foreground service and end rides at their deadline or on shutdown"
```

---

### Task 6: ホームの走行のカード・SC-17・SC-04

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ui/RideLabels.kt`・`app/src/main/java/com/touringproject/v2/ui/RideScreens.kt`
- Modify: `app/src/main/java/com/touringproject/v2/ui/Labels.kt`・`app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt`・`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt`・`app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt`・`app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt`（1つ足す）

**Interfaces:**
- Consumes: Task 1 の `Ride`・`RideStatus`・`Pauses`・`pauses()`・`recordedMs()`・`startedAt()`・`rideName()`・`RIDE_NAME_MAX`・Task 5 の `AppGraph.rides`
- Produces: `elapsedLabel(ms)`・`distanceLabel(meters)`・`periodLabel(start, end, zone)`・`pausesLabel(pauses): String?`・`data class RideCardUi(name, paused, elapsed, distance)`・`rideCard(ride, now)`・`data class EndSummaryUi(elapsed, distance, note)`・`endSummary(ride, now, zone)`・`@Composable RideCard(ride: RideCardUi?, onStart, onPause, onResume, onEnd)`・`@Composable StartRideSheet(locationAllowed, onStart: (String) -> Unit, onDismiss)`・`@Composable EndRideSheet(summary, initialName, onEnd: (String) -> Unit, onDismiss)`・`Banner.STORE_FAILED`・`Banner.leads`・`homeBanner(..., storeFailed = false)`・`HomeScreen(..., ride: @Composable () -> Unit = {})`

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt`:

```kotlin
package com.touringproject.v2.ui

import com.touringproject.v2.ride.HOUR_MS
import com.touringproject.v2.ride.Pauses
import com.touringproject.v2.ride.newRide
import com.touringproject.v2.ride.pause
import com.touringproject.v2.ride.resume
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.ZoneId
import java.time.ZonedDateTime

private val TOKYO = ZoneId.of("Asia/Tokyo")
private fun at(day: Int, hour: Int, minute: Int) = ZonedDateTime.of(2026, 10, day, hour, minute, 0, 0, TOKYO).toInstant().toEpochMilli()

class RideLabelsTest {
  @Test
  fun elapsed_and_distance_read_like_the_mock() {
    assertEquals("1:26", elapsedLabel(86 * 60_000L + 59_000))
    assertEquals("0:00", elapsedLabel(0))
    assertEquals("52.8 km", distanceLabel(52_800.0))
  }

  @Test
  fun the_period_shows_dates_only_when_the_ride_runs_over_midnight() {
    assertEquals("08:58〜10:46", periodLabel(at(17, 8, 58), at(17, 10, 46), TOKYO))
    assertEquals("10月17日 18:00〜10月18日 09:30", periodLabel(at(17, 18, 0), at(18, 9, 30), TOKYO))
  }

  @Test
  fun pauses_are_mentioned_only_when_there_were_any() {
    assertNull(pausesLabel(Pauses(0, 0)))
    assertEquals("一時停止 1回（18分）は走行時間に含めません", pausesLabel(Pauses(1, 18 * 60_000L)))
  }

  @Test
  fun the_end_summary_of_a_paused_ride_ends_at_its_pause() {
    val ride = newRide("r1", "箱根", at(17, 8, 58), 7, 24 * HOUR_MS)
      .pause(at(17, 9, 30)).resume(at(17, 9, 48), 7, 24 * HOUR_MS).pause(at(17, 10, 46))
    val summary = endSummary(ride.copy(distanceMeters = 62_400.0), at(17, 11, 30), TOKYO)
    assertEquals(EndSummaryUi("1:30", "62.4 km", "08:58〜10:46 · 一時停止 1回（18分）は走行時間に含めません"), summary)
  }

  @Test
  fun the_card_says_whether_the_ride_is_paused() {
    val ride = newRide("r1", "箱根", 0, 7, 24 * HOUR_MS)
    assertEquals(RideCardUi("箱根", false, "0:01", "0.0 km"), rideCard(ride, 60_000))
    assertEquals(true, rideCard(ride.pause(60_000), 120_000).paused)
  }
}
```

`app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt`:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RideScreensTest {
  @get:Rule val rule = createComposeRule()

  @Test
  fun without_a_ride_the_card_offers_to_start_one() {
    var starts = 0
    rule.setContent { RideCard(null, { starts++ }, {}, {}, {}) }
    rule.onNodeWithText("記録しなくても質問できます（日ごとの記録に残ります）").assertExists()
    rule.onNodeWithTag("startRide").performClick()
    assertEquals(1, starts)
  }

  @Test
  fun a_recording_ride_shows_its_time_and_distance_and_can_pause_or_end() {
    val events = mutableListOf<String>()
    rule.setContent { RideCard(RideCardUi("箱根", false, "1:26", "52.8 km"), {}, { events += "pause" }, { events += "resume" }, { events += "end" }) }
    rule.onNodeWithText("● 走行を記録中").assertExists()
    rule.onNodeWithText("1:26").assertExists()
    rule.onNodeWithText("52.8 km").assertExists()
    rule.onNodeWithText("⏸ 一時停止").performClick()
    rule.onNodeWithTag("endRide").performClick()
    assertEquals(listOf("pause", "end"), events)
  }

  @Test
  fun a_paused_ride_says_its_questions_are_not_recorded_and_can_resume() {
    var resumes = 0
    rule.setContent { RideCard(RideCardUi("箱根", true, "1:26", "52.8 km"), {}, {}, { resumes++ }, {}) }
    rule.onNodeWithText("一時停止中の質問は走行の記録に入りません（日ごとには残ります）").assertExists()
    rule.onNodeWithText("▶ 再開").performClick()
    assertEquals(1, resumes)
  }

  @Test
  fun the_start_sheet_needs_a_name() {
    var started: String? = null
    rule.setContent { StartRideSheet(locationAllowed = true, onStart = { started = it }, onDismiss = {}) }
    rule.onNodeWithTag("startGo").assertIsNotEnabled()
    rule.onNodeWithTag("rideName").performTextInput("  ")
    rule.onNodeWithTag("startGo").assertIsNotEnabled()
    rule.onNodeWithTag("rideName").performTextInput("箱根 ")
    rule.onNodeWithTag("startGo").assertIsEnabled().performClick()
    assertEquals("箱根", started)
  }

  @Test
  fun a_pasted_name_is_cut_at_40_characters() {
    var started: String? = null
    rule.setContent { StartRideSheet(locationAllowed = true, onStart = { started = it }, onDismiss = {}) }
    rule.onNodeWithTag("rideName").performTextInput("あ".repeat(45))
    rule.onNodeWithTag("startGo").performClick()
    assertEquals("あ".repeat(40), started)
  }

  @Test
  fun the_start_sheet_says_why_without_the_location_permission() {
    rule.setContent { StartRideSheet(locationAllowed = false, onStart = {}, onDismiss = {}) }
    rule.onNodeWithTag("noLocation").assertExists()
    rule.onNodeWithTag("rideName").performTextInput("箱根")
    rule.onNodeWithTag("startGo").assertIsNotEnabled()
  }

  @Test
  fun the_end_sheet_shows_the_summary_and_keeps_the_name_from_being_emptied() {
    var ended: String? = null
    var dismissed = 0
    rule.setContent {
      EndRideSheet(EndSummaryUi("1:30", "62.4 km", "08:58〜10:46 · 一時停止 1回（18分）は走行時間に含めません"), "箱根", { ended = it }, { dismissed++ })
    }
    rule.onNodeWithText("08:58〜10:46 · 一時停止 1回（18分）は走行時間に含めません").assertExists()
    rule.onNodeWithTag("rideName").performTextClearance()
    rule.onNodeWithTag("endGo").assertIsNotEnabled()
    rule.onNodeWithTag("rideName").performTextInput("箱根から御殿場へ")
    rule.onNodeWithTag("endGo").performClick()
    assertEquals("箱根から御殿場へ", ended)
    rule.onNodeWithText("走行を続ける").performClick()
    assertEquals(1, dismissed)
  }
}
```

`app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt` の `the_low_volume_band_comes_last` の最後の `assertEquals(Banner.LOW_VOLUME, ...)` の下に足す:

```kotlin
    // A failing database is the most urgent: rides are being lost (slice 2 spec §8).
    assertEquals(Banner.STORE_FAILED, homeBanner(hasKey = false, returnAppMissing = true, volumeLow = true, storeFailed = true))
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideLabelsTest' --tests '*RideScreensTest' --tests '*LabelsTest'`
Expected: コンパイルの失敗（`Unresolved reference 'elapsedLabel'`・`'STORE_FAILED'` など）

- [ ] **Step 3: 表示の文字を書く**

`app/src/main/java/com/touringproject/v2/ui/RideLabels.kt`:

```kotlin
package com.touringproject.v2.ui

import com.touringproject.v2.ride.Pauses
import com.touringproject.v2.ride.Ride
import com.touringproject.v2.ride.RideStatus
import com.touringproject.v2.ride.pauses
import com.touringproject.v2.ride.recordedMs
import com.touringproject.v2.ride.startedAt
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

// How a ride is described on SC-02 and SC-04 (the mock's trip card and end sheet).

/** Hours and minutes, e.g. 1:26. */
fun elapsedLabel(ms: Long): String {
  val minutes = ms / 60_000
  return String.format(Locale.ROOT, "%d:%02d", minutes / 60, minutes % 60)
}

fun distanceLabel(meters: Double): String = String.format(Locale.ROOT, "%.1f km", meters / 1000)

/** 08:58〜10:46 within a day; with the dates when the ride runs over midnight. */
fun periodLabel(start: Long, end: Long, zone: ZoneId): String {
  val from = Instant.ofEpochMilli(start).atZone(zone)
  val to = Instant.ofEpochMilli(end).atZone(zone)
  val time = DateTimeFormatter.ofPattern("HH:mm")
  if (from.toLocalDate() == to.toLocalDate()) return "${time.format(from)}〜${time.format(to)}"
  val day = DateTimeFormatter.ofPattern("M月d日 HH:mm")
  return "${day.format(from)}〜${day.format(to)}"
}

fun pausesLabel(pauses: Pauses): String? =
  if (pauses.count == 0) null else "一時停止 ${pauses.count}回（${pauses.totalMs / 60_000}分）は走行時間に含めません"

data class RideCardUi(val name: String, val paused: Boolean, val elapsed: String, val distance: String)

fun rideCard(ride: Ride, now: Long) = RideCardUi(ride.name, ride.status == RideStatus.PAUSED, elapsedLabel(ride.recordedMs(now)), distanceLabel(ride.distanceMeters))

data class EndSummaryUi(val elapsed: String, val distance: String, val note: String)

/** SC-04's summary as if the ride ended now. */
fun endSummary(ride: Ride, now: Long, zone: ZoneId): EndSummaryUi {
  val end = if (ride.status == RideStatus.PAUSED) ride.segments.last().endedAt ?: now else now
  val note = listOfNotNull(periodLabel(ride.startedAt(), end, zone), pausesLabel(ride.pauses())).joinToString(" · ")
  return EndSummaryUi(elapsedLabel(ride.recordedMs(now)), distanceLabel(ride.distanceMeters), note)
}
```

- [ ] **Step 4: 走行のカードとシートを書く**

`app/src/main/java/com/touringproject/v2/ui/RideScreens.kt`:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
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
import com.touringproject.v2.ride.RIDE_NAME_MAX
import com.touringproject.v2.ride.rideName

private val MUTED = Color(0xFF5B6170)

/** SC-02's ride card (slice 2 spec §7.2). Memo buttons wait for slice 3; the question count waits for plan 3. */
@Composable
fun RideCard(ride: RideCardUi?, onStart: () -> Unit, onPause: () -> Unit, onResume: () -> Unit, onEnd: () -> Unit) {
  val card = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp)).padding(14.dp)
  if (ride == null) {
    Column(card, verticalArrangement = Arrangement.spacedBy(8.dp)) {
      Button(onClick = onStart, Modifier.fillMaxWidth().heightIn(min = 60.dp).testTag("startRide")) { Text("▶ 走行を開始", fontSize = 18.sp) }
      Text("記録しなくても質問できます（日ごとの記録に残ります）", color = MUTED, fontSize = 14.sp)
    }
    return
  }
  Column(card, verticalArrangement = Arrangement.spacedBy(8.dp)) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
      if (ride.paused) Text("⏸ 一時停止中", color = MUTED, fontWeight = FontWeight.Bold)
      else Text("● 走行を記録中", color = Color(0xFFD42A2A), fontWeight = FontWeight.Bold)
      Text(ride.name, color = MUTED, fontSize = 14.sp)
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround) {
      Stat(ride.elapsed, "走行時間", Modifier.testTag("rideElapsed"))
      Stat(ride.distance, "距離", Modifier.testTag("rideDistance"))
    }
    if (ride.paused) Text("一時停止中の質問は走行の記録に入りません（日ごとには残ります）", color = MUTED, fontSize = 14.sp)
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
      if (ride.paused) Button(onClick = onResume, Modifier.weight(1f)) { Text("▶ 再開") }
      else OutlinedButton(onClick = onPause, Modifier.weight(1f)) { Text("⏸ 一時停止") }
      OutlinedButton(onClick = onEnd, Modifier.weight(1f).testTag("endRide")) { Text("■ 終了") }
    }
  }
}

@Composable
private fun Stat(value: String, label: String, modifier: Modifier = Modifier) {
  Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
    Text(value, fontSize = 24.sp, fontWeight = FontWeight.Bold)
    Text(label, color = MUTED, fontSize = 13.sp)
  }
}

@Composable
private fun NameField(name: String, onChange: (String) -> Unit, placeholder: String?) {
  OutlinedTextField(
    value = name,
    onValueChange = { onChange(it.take(RIDE_NAME_MAX)) },
    label = { Text("この走行の名前") },
    placeholder = placeholder?.let { { Text(it) } },
    singleLine = true,
    modifier = Modifier.fillMaxWidth().testTag("rideName"),
  )
}

/** SC-17 (slice 2 spec §7.3). Without the location permission the ride cannot start, and the sheet says why. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StartRideSheet(locationAllowed: Boolean, onStart: (String) -> Unit, onDismiss: () -> Unit) {
  var name by remember { mutableStateOf("") }
  ModalBottomSheet(onDismissRequest = onDismiss) {
    Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
      Text("走行を開始", fontSize = 20.sp, fontWeight = FontWeight.Bold)
      NameField(name, { name = it }, "例: 箱根・御殿場")
      Text("名前を入れると開始できます。あとで変えることもできます。", color = MUTED, fontSize = 14.sp)
      if (!locationAllowed) {
        Text("位置の許可が無いので、走行を記録できません。端末の設定で、このアプリに位置の使用を許可してください。", color = Color(0xFFD42A2A), modifier = Modifier.testTag("noLocation"))
      }
      Button(
        onClick = { rideName(name)?.let(onStart) },
        enabled = locationAllowed && rideName(name) != null,
        modifier = Modifier.fillMaxWidth().heightIn(min = 60.dp).testTag("startGo"),
      ) { Text("▶ 開始", fontSize = 18.sp) }
      FilledTonalButton(onClick = onDismiss, Modifier.fillMaxWidth()) { Text("やめる") }
    }
  }
}

/** SC-04 (slice 2 spec §7.3). The name may be changed here but not emptied. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EndRideSheet(summary: EndSummaryUi, initialName: String, onEnd: (String) -> Unit, onDismiss: () -> Unit) {
  var name by remember { mutableStateOf(initialName) }
  ModalBottomSheet(onDismissRequest = onDismiss) {
    Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
      Text("走行を終了しますか？", fontSize = 20.sp, fontWeight = FontWeight.Bold)
      Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround) {
        Stat(summary.elapsed, "走行時間")
        Stat(summary.distance, "距離")
      }
      Text(summary.note, color = MUTED, fontSize = 14.sp)
      NameField(name, { name = it }, null)
      Button(onClick = { rideName(name)?.let(onEnd) }, enabled = rideName(name) != null, modifier = Modifier.fillMaxWidth().testTag("endGo")) {
        Text("終了して保存")
      }
      FilledTonalButton(onClick = onDismiss, Modifier.fillMaxWidth()) { Text("走行を続ける") }
    }
  }
}
```

- [ ] **Step 5: 警告の帯に「記録を保存できません」を足す**

`app/src/main/java/com/touringproject/v2/ui/Labels.kt` の `enum class Banner` と `homeBanner` を、次に置き換える:

```kotlin
/** leads is true when tapping the band opens the setting that fixes it. */
enum class Banner(val text: String, val leads: Boolean = true) {
  STORE_FAILED("記録を保存できません", leads = false),
  NO_KEY("接続キーが未設定です（押して設定）"),
  NO_RETURN_APP("戻り先のアプリが未設定です（押して選ぶ）"),
  LOW_VOLUME("メディアの音量が低く、回答が聞こえないかもしれません", leads = false),
}

/** SC-02 shows at most one warning band, the most urgent first. */
fun homeBanner(hasKey: Boolean, returnAppMissing: Boolean, volumeLow: Boolean = false, storeFailed: Boolean = false): Banner? = when {
  storeFailed -> Banner.STORE_FAILED
  !hasKey -> Banner.NO_KEY
  returnAppMissing -> Banner.NO_RETURN_APP
  volumeLow -> Banner.LOW_VOLUME
  else -> null
}
```

- [ ] **Step 6: ホームに走行のカードの場所を作る**

`app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt` の `HomeScreen` の引数の最後（`onDismissVolume: () -> Unit = {},` の下）に足す:

```kotlin
  ride: @Composable () -> Unit = {},
```

同じ関数の帯の部分を、次に置き換える（帯を押して開く先が無いものを `leads` で決め、帯の下に走行のカードを置く）:

```kotlin
    ui.banner?.let { banner ->
      val low = banner == Banner.LOW_VOLUME
      WarningBand(banner.text, if (banner.leads) ({ onBanner(banner) }) else null, if (low) onDismissVolume else null, Modifier.testTag("banner"))
    }
    ride()
```

- [ ] **Step 7: `AppUi` に組み込む**

`app/src/main/java/com/touringproject/v2/ui/AppUi.kt` を次のように直す。

import に足す（ファイルの先頭の `import androidx.compose.foundation.layout.Box` の上）:

```kotlin
import android.Manifest
import android.content.pm.PackageManager
import android.widget.Toast
```

`import androidx.compose.runtime.getValue` の下に `import androidx.compose.runtime.mutableLongStateOf`、`import androidx.compose.ui.Modifier` の下に `import androidx.compose.ui.platform.LocalContext`、`import kotlinx.coroutines.launch` の上に `import kotlinx.coroutines.delay`、下に `import java.time.ZoneId` を足す。

`@Composable fun AppUi(graph: AppGraph) {` の上に足す:

```kotlin
private enum class RideSheet { START, END }

/** The clock for the ride card, ticking every second while a ride is shown. */
@Composable
private fun rememberNow(ticking: Boolean): Long {
  var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
  LaunchedEffect(ticking) {
    while (ticking) {
      now = System.currentTimeMillis()
      delay(1_000)
    }
  }
  return now
}

```

`val volumeDismissedAt by graph.volumeDismissedAt.collectAsStateWithLifecycle()` の下に足す:

```kotlin
  val ride by graph.rides.active.collectAsStateWithLifecycle()
  val storeFailed by graph.rides.storeFailed.collectAsStateWithLifecycle()
  var sheet by remember { mutableStateOf<RideSheet?>(null) }
  val now = rememberNow(ride != null)
  val context = LocalContext.current
```

`homeBanner(` の呼び出しの `volumeLow = volumeWarning(volume, volumeDismissedAt),` の下に足す:

```kotlin
                  storeFailed = storeFailed,
```

`HomeScreen(` の呼び出しの最後の引数 `onDismissVolume = { volume?.let { graph.dismissVolumeWarning(it.current) } },` の下に足す:

```kotlin
                ride = {
                  RideCard(
                    ride?.let { rideCard(it, now) },
                    onStart = { sheet = RideSheet.START },
                    onPause = {
                      scope.launch { graph.rides.pause() }
                      Toast.makeText(context, "一時停止しました", Toast.LENGTH_SHORT).show()
                    },
                    onResume = {
                      scope.launch { graph.rides.resume() }
                      Toast.makeText(context, "再開しました", Toast.LENGTH_SHORT).show()
                    },
                    onEnd = { sheet = RideSheet.END },
                  )
                },
```

`NavDisplay(...)` の閉じかっこのあと、`Column(Modifier.fillMaxSize()) { AskOverlay(` の上に足す（対話の画面がシートより上に重なるように、シートを先に置く）:

```kotlin
        when (sheet) {
          RideSheet.START -> StartRideSheet(
            locationAllowed = context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED,
            onStart = { name ->
              sheet = null
              scope.launch { graph.rides.start(name) }
            },
            onDismiss = { sheet = null },
          )
          RideSheet.END -> ride?.let { active ->
            EndRideSheet(
              endSummary(active, now, ZoneId.systemDefault()),
              active.name,
              onEnd = { name ->
                sheet = null
                scope.launch { graph.rides.end(name) }
              },
              onDismiss = { sheet = null },
            )
          }
          null -> Unit
        }
        // The ride may end elsewhere (deadline, shutdown) while SC-04 is open.
        LaunchedEffect(ride == null) { if (ride == null && sheet == RideSheet.END) sheet = null }
```

- [ ] **Step 8: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideLabelsTest' --tests '*RideScreensTest' --tests '*LabelsTest' --tests '*HomeScreenTest'`
Expected: `BUILD SUCCESSFUL`。`RideLabelsTest` 5件・`RideScreensTest` 7件

- [ ] **Step 9: 全体を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t6.log 2>&1; tail -3 /tmp/trv2-t6.log`
Expected: `BUILD SUCCESSFUL`。結果のファイルを数えて243件・失敗0件

- [ ] **Step 10: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RideLabels.kt app/src/main/java/com/touringproject/v2/ui/RideScreens.kt \
  app/src/main/java/com/touringproject/v2/ui/Labels.kt app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
git commit -m "feat: start, pause, resume and end a ride from the home screen"
```

---

### Task 7: エミュレーターのテストと走行用のビルド

**Files:**
- Create: `app/src/androidTest/java/com/touringproject/v2/RideRecordingTest.kt`

**Interfaces:**
- Consumes: Task 3 の `RideController`・Task 4 の `ServiceCoordinator.running`・Task 5 の `AppGraph.rides`・`AppGraph.serviceCoordinator`・既存の `AppGraph.apiKeys.save(key: String?)`・`AppGraph.controller`・`AppGraph.state`・`AppGraph.isReady`・`AppGraph.apiBaseUrl`
- Produces: なし

マイクのテストは、接続キーを入れて一巡をサービスまで進め、録音の途中で取り消す（Backend には何も送らない）。`local.properties` に `trv2.apiBaseUrl` が無いと飛ばす。後片付けでキーを消す（`VoiceCommandTest` はキーが無い前提で動く）。

- [ ] **Step 1: テストを書く**

`app/src/androidTest/java/com/touringproject/v2/RideRecordingTest.kt`:

```kotlin
package com.touringproject.v2

import android.Manifest
import android.app.Activity
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.location.Location
import android.os.SystemClock
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import com.google.android.gms.location.LocationServices
import com.google.android.gms.tasks.Tasks
import com.touringproject.v2.ask.Phase
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

// On the emulator (slice 2 spec §9): a ride keeps taking in its route with the screen off, and an ask during the ride
// adds the microphone to the running service. Positions come from Fused's mock mode, so the app is made the mock
// location app first.
@RunWith(AndroidJUnit4::class)
class RideRecordingTest {
  private val instrumentation = InstrumentationRegistry.getInstrumentation()
  private val app = ApplicationProvider.getApplicationContext<TouringApp>()
  private val fused = LocationServices.getFusedLocationProviderClient(app)

  private fun shell(command: String) {
    instrumentation.uiAutomation.executeShellCommand(command).close()
    SystemClock.sleep(300)
  }

  @Before
  fun setUp() {
    listOf(
      Manifest.permission.RECORD_AUDIO,
      Manifest.permission.ACCESS_FINE_LOCATION,
      Manifest.permission.ACCESS_COARSE_LOCATION,
      Manifest.permission.BLUETOOTH_CONNECT,
      Manifest.permission.POST_NOTIFICATIONS,
    ).forEach { instrumentation.uiAutomation.grantRuntimePermission(app.packageName, it) }
    shell("appops set ${app.packageName} android:mock_location allow")
    Tasks.await(fused.setMockMode(true))
    shell("input keyevent KEYCODE_WAKEUP")
    // A location service can only start while the app is in front (Android 14+).
    app.startActivity(Intent(app, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    waitUntil { resumed() is MainActivity }
    waitUntil { app.graph.isReady.value }
  }

  @After
  fun tearDown() {
    onMain { app.graph.controller.cancel() }
    onMain { app.graph.scope.launch { app.graph.rides.end("emulator") } }
    waitUntil { app.graph.rides.active.value == null }
    // VoiceCommandTest relies on there being no key.
    runBlocking { app.graph.apiKeys.save(null) }
    Tasks.await(fused.setMockMode(false))
    shell("input keyevent KEYCODE_WAKEUP")
    resumed()?.let { activity -> instrumentation.runOnMainSync { activity.finish() } }
  }

  private fun onMain(block: () -> Unit) = instrumentation.runOnMainSync(block)

  private fun waitUntil(timeoutMs: Long = 20_000, condition: () -> Boolean) {
    val deadline = SystemClock.uptimeMillis() + timeoutMs
    while (!condition()) {
      check(SystemClock.uptimeMillis() < deadline) { "condition never became true" }
      SystemClock.sleep(100)
    }
  }

  private fun resumed(): Activity? {
    var activity: Activity? = null
    onMain { activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).firstOrNull() }
    return activity
  }

  private fun serviceTypes(): Int? {
    var types: Int? = null
    onMain { types = (app.graph.serviceCoordinator.running as? Service)?.foregroundServiceType }
    return types
  }

  private fun startRide() {
    onMain { app.graph.scope.launch { app.graph.rides.start("emulator") } }
    waitUntil { serviceTypes() == ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION }
  }

  private fun mock(lat: Double) {
    val location = Location("fused").apply {
      latitude = lat
      longitude = 139.0
      accuracy = 5f
      time = System.currentTimeMillis()
      elapsedRealtimeNanos = SystemClock.elapsedRealtimeNanos()
    }
    Tasks.await(fused.setMockLocation(location))
  }

  @Test
  fun the_route_keeps_coming_in_with_the_screen_off() {
    startRide()
    shell("input keyevent KEYCODE_SLEEP")
    // One point every 5 s, about 111 m apart, for a minute.
    repeat(12) { i ->
      mock(35.0 + i * 0.001)
      SystemClock.sleep(5_000)
    }
    shell("input keyevent KEYCODE_WAKEUP")
    val distance = app.graph.rides.active.value!!.distanceMeters
    assertTrue("distance was $distance", distance > 800)
  }

  @Test
  fun an_ask_during_a_ride_adds_the_microphone_and_gives_it_back() {
    assumeTrue("needs trv2.apiBaseUrl in local.properties", app.graph.apiBaseUrl.isNotEmpty())
    // A key is needed for the ask to reach the service; the ask is cancelled before anything is sent.
    runBlocking { app.graph.apiKeys.save("emulator-test-key") }
    startRide()
    app.startActivity(Intent(app, MainActivity::class.java).setAction(Intent.ACTION_VOICE_COMMAND).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    waitUntil { app.graph.state.value.phase == Phase.RECORDING }
    assertEquals(
      ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
      serviceTypes(),
    )
    onMain { app.graph.controller.cancel() }
    waitUntil { serviceTypes() == ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION }
  }
}
```

- [ ] **Step 2: エミュレーターで回す**

```bash
df -h / | tail -1
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
export ANDROID_SERIAL=emulator-5554
cd $AND && ./gradlew connectedDebugAndroidTest > /tmp/trv2-emu.log 2>&1; grep -E "FAILED|Finished|BUILD" /tmp/trv2-emu.log
```

Expected: `Finished 4 tests on medium_phone(AVD) - 16` と `BUILD SUCCESSFUL`（`VoiceCommandTest` 2件と `RideRecordingTest` 2件）。落ちたら `app/build/outputs/androidTest-results/connected/debug/` の logcat を見る。

- [ ] **Step 3: 走行用のビルドと権限を確かめる**

```bash
cd $AND && ./gradlew assembleDebug assembleRelease > /tmp/trv2-rel.log 2>&1; tail -3 /tmp/trv2-rel.log
scripts/check-release-permissions.sh
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: `BUILD SUCCESSFUL`（lint を含む）と `release permissions OK (15)`

- [ ] **Step 4: コミット**

```bash
cd $AND && git add app/src/androidTest/java/com/touringproject/v2/RideRecordingTest.kt
git commit -m "test: check on the emulator that the route keeps coming in and an ask adds the microphone"
```

---

### Task 8: 文書

**Files:**
- Create: 親の `adr/0006-background-ride-recording.md`
- Modify: 親の `adr/README.md`・`docs/05_technical_policies.md`・Android の `README.md`・`docs-parent/`（写し）

- [ ] **Step 1: ADR 0006 を書く**

`$ROOT/adr/0006-background-ride-recording.md`:

```markdown
# 0006. 走行中のルートは、前面サービスの中で Fused の位置を受けて端末の DB に書く

- 日付: 2026-10-18
- 状態: 採用

## 背景

スライス2では、走行の始まりから終わりまでのルートを記録する。画面を消し、ナビを前面に出したまま何時間も走るので、アプリは背面にある。React Native 版では、位置を JS で受けると背面で届き方が間引かれないかが分からず、スパイクで確かめる予定だった。ネイティブ版（[0005](0005-native-android-app.md)）に移ったので、Android の標準の部品で作り直す。

縛り:

- Android 14 以降、種類が `location`・`microphone` の前面サービスは、アプリが前面にあるときにしか始められず、種類も足せない。
- 正確な時刻のアラームは、Android 12 以降 `SCHEDULE_EXACT_ALARM` の許可が要り、Android 14 以降は新しく入れたアプリでは既定で許されない。
- 端末は、電源を切ったとき・電池が切れたとき・再起動したときに止まる。アプリだけが落ちることもある。

## 選択肢

| 論点 | 案 | 判断 |
|---|---|---|
| 位置の受け方 | A. 前面サービスの中で `FusedLocationProviderClient` から受ける | 採用。前面で始めたサービスなので、背面での位置の許可（`ACCESS_BACKGROUND_LOCATION`）は要らない |
| | B. 背面での位置の許可を取り、サービスなしで受ける | 不採用。許可の画面が増え、届き方が間引かれる |
| サービスの組み方 | A. 走行の記録と質問の一巡で1つのサービスを使い、種類を状態で変える | 採用。通知1つで「記録中」の知らせを兼ねる |
| | B. サービスを2つに分ける | 不採用。走行中の質問で通知が2つ並ぶ |
| 締め切り（自動終了） | A. サービスの中の待ちと、正確でないアラームの二段構え | 採用。終了の時刻は締め切りの時刻で記録するので、アラームが遅れても記録は狂わない |
| | B. 正確なアラーム | 不採用。利用者に設定の画面で許してもらう手間がある |
| | C. WorkManager | 不採用。遅れ方は A と同じで、依存が増える |
| 端末の記録 | A. Room | 採用。マイグレーションとその検査の道具が付いてくる |
| | B. SQLite を直に使う | 不採用。変換・マイグレーション・変化の通知を自分で書く |
| 使い捨てのスパイク | 置かない | 作りを変えうる問い（JS で位置を受けられるか）がネイティブ化で消えた。残る数字の確かめ（何時間もの点の抜け・電池）は、実際の走行で測る |

## 決定

- `RideForegroundService` を「走行の記録中、または質問の一巡の途中」なら動かす。記録中は `location`、一巡のあいだは `microphone|mediaPlayback` を足す。走行中の質問では、インカムのボタンが `MainActivity` を開いて前面に出た時点で `microphone` を足す。足せなければ、その質問を失敗にし、記録は続ける。
- 位置は Fused に、高精度・5秒ごと・10m 動いたら、で頼む。精度が 50m より悪い点と、区間の開始より古い点（監視を始め直した直後に返る古い位置）は捨てる。届いた点はすぐ Room に書く。
- 締め切りは、サービスの中（1分ごとと、点が届くたび）と、正確でないアラーム（`setAndAllowWhileIdle`）の受け口の両方で見る。どちらで気付いても、締め切りの時刻で終える。
- サービスが動いているあいだ、点を書くたびと1分ごとに「最後に生きていた時刻」を書く。区間の開始のときに端末の起動の回数（`Settings.Global.BOOT_COUNT`）を残す。電源を切る知らせ（`ACTION_SHUTDOWN`）を受けたら、その時刻で終える。起動したとき、起動の回数が増えていれば最後に生きていた時刻で終え、締め切りを過ぎていれば締め切りの時刻で終え、それ以外で記録中なら記録を再開する。
- サービスは `START_STICKY` にする。背面から起こし直されて前面に出られなければ、サービスを止め、次にアプリを開いたとき（`MainActivity.onStart`）に始め直す。

詳しくは [スライス2の設計](../docs/specs/2026-10-17-slice2-design.md) §3・§4・§5.1。

## 影響

- 確かめていないこと: 何時間も走ったときの点の抜けと電池の減り（スライス2の最後の走行で測る）、端末が眠ったときに点が間引かれないか、`START_STICKY` で起こし直したサービスが `location` で前面に出られるか（スライス2 plan 1 の終わりの実機の確認で見る）。分かったら、ここに書き足す。
- エミュレーターで確かめたこと: 画面を消しても、作り物の位置（Fused の mock mode）で1分間に点が溜まる。記録中に `VOICE_COMMAND` を送ると、サービスに `microphone` を足せ、一巡のあとで `location` だけに戻る。
```

- [ ] **Step 2: ADR の一覧と 05 §9 を直す**

`$ROOT/adr/README.md` の表の最後に足す:

```markdown
| [0006](0006-background-ride-recording.md) | 走行中のルートは、前面サービスの中で Fused の位置を受けて端末の DB に書く | 採用 |
```

`$ROOT/docs/05_technical_policies.md` §9 の「背面での動作」の行を、次に置き換える:

```markdown
| 背面での動作 | 決定済み。回答の待ち受け・読み上げは [adr/0004](../adr/0004-background-processing.md)（ネイティブ版では一巡をコルーチンで動かし、前面サービスでプロセスを生かす。[adr/0005](../adr/0005-native-android-app.md)）。走行中のルートの記録は [adr/0006](../adr/0006-background-ride-recording.md)。何時間も走ったときの点の抜けと電池の減りは、スライス2の走行で測る |
```

- [ ] **Step 3: Android の README を直す**

`$AND/README.md` の「構成」の表で、`.../location/` の行を置き換え、その下に2行足す:

```markdown
| `.../location/` | 質問の位置の監視と方位の材料の選び方・走行のルートの位置の頼み方と点のふるい分け（`Route.kt`） |
| `.../ride/` | 走行の型と計算（`Ride.kt`、純粋）・司令塔（`RideController.kt`）・外との窓口（`RidePorts.kt`） |
| `.../store/` | 端末の DB（Room）。スキーマは `app/schemas/` に版ごとに残す |
```

同じ表の `.../service/`・`.../nav/` の行を置き換える:

```markdown
| `.../service/`・`.../nav/` | 前面サービス（走行の記録と一巡で1つ。種類の取りまとめは `ServiceCoordinator.kt`）・締め切りのアラームと自動終了の通知（`RideAlarms.kt`）・ナビを開く |
```

「大事な決まり」の最初の行を置き換える:

```markdown
- 走行の記録中と一巡のあいだは、前面サービスを動かす（無いと、画面を消したあと位置・通信・再生が止まる）。種類は、記録中は `location`、一巡のあいだは `microphone|mediaPlayback` を足す。Android 14 以降、この2つはアプリが前面にあるときにしか始められず、足せない（理由は親の `adr/0006`）。
- 走行の状態を変えるのは `RideController` だけ。サービス・締め切りのアラーム・電源を切る知らせ・画面は、どれもこれを呼ぶ。起動したときは `load()` が先に、残っていた走行を片付ける（端末が止まっていれば終了、締め切りを過ぎていれば自動終了、それ以外は記録の再開）。
- Room のスキーマを変えるときは、版を上げて Migration を書き、`app/schemas/` に書き出された JSON もコミットする。破壊的な作り直しは使わない。
```

「エミュレーター」の節の最後に足す:

```markdown
`RideRecordingTest` は、Fused の mock mode で作り物の位置を流す（テストが自分で、アプリを位置の作り物を出すアプリにする）。記録中の質問のテストは、`local.properties` に `trv2.apiBaseUrl` が無いと飛ばす。接続キーを入れて録音の途中で取り消し、最後にキーを消す。
```

ログの行（`adb logcat -s ...`）は、`trv2.ride`・`trv2.route` がすでに入っているので変えない。

- [ ] **Step 4: 親の文書をユニットに写す**

```bash
cd $ROOT && scripts/sync-docs.sh Android
cd $AND && git status --short docs-parent/
```

Expected: `docs-parent/05_technical_policies.md` が変わっている

- [ ] **Step 5: コミット**

```bash
cd $ROOT && git add adr/0006-background-ride-recording.md adr/README.md docs/05_technical_policies.md
git commit -m "docs: record how a ride's route is kept in the background"
cd $AND && git add README.md docs-parent/05_technical_policies.md
git commit -m "docs: describe the ride packages and their rules"
```

---

### Task 9: 利用者の実機の確認（短い走行）

AI はこの Task を自分で通さない。利用者に、次の手順と表を渡して結果を聞く。

- [ ] **Step 1: 走行用のビルドを入れる（AI が行う。実機を USB で繋いでもらう）**

```bash
unset ANDROID_SERIAL
cd $AND && ./gradlew assembleRelease > /tmp/trv2-rel.log 2>&1; tail -1 /tmp/trv2-rel.log
scripts/check-release-permissions.sh
adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
```

Expected: `Success`。端末にユーザーが2つあるので `--user 0` でメインのユーザーを指す。

- [ ] **Step 2: 利用者に確かめてもらう**

| # | 操作 | 期待 |
|---|---|---|
| 1 | ホームの「▶ 走行を開始」→ 名前を入れずに「開始」を見る → 名前を入れて「開始」 | 名前が空のあいだは押せない。開始すると「● 走行を記録中」・走行時間・距離が出て、通知に「走行を記録中」が出る |
| 2 | ナビを前面に出し、画面を消して30分〜1時間走る | 戻ってホームを開くと、距離が走った距離に近い（大きく足りなければ、点が抜けている） |
| 3 | 走行中に、インカムのボタンで1回質問する | いつもどおり回答が聞こえる。走行の記録は続いている（距離が増え続ける） |
| 4 | 止まって「⏸ 一時停止」→ 少し動いてから「▶ 再開」 | 一時停止中は走行時間が止まり、「一時停止中の質問は走行の記録に入りません」が出る。通知が消え、再開で戻る |
| 5 | 「■ 終了」 | 要約に走行時間・距離・時刻と一時停止の回数が出る。「走行を続ける」で戻れる。「終了して保存」でホームが「▶ 走行を開始」に戻る |
| 6 | 新しく走行を始め、記録中のまま「最近使ったアプリ」からアプリを払って消す。そのまま数分待つ | 通知の「走行を記録中」が残るか、消えても、アプリを開くと記録中のまま続いている（システムが起こし直したか、開いたときに始め直した） |
| 7 | 6 の走行を記録中のまま、端末を再起動してアプリを開く | 「▶ 走行を開始」に戻っている（再起動の前の時刻で終わっている） |

ログを見るときは `adb logcat -s trv2.ride trv2.route` を勧める（`ride_load`・`ride_start`・`ride_end`・`startForeground failed`）。

- [ ] **Step 3: 結果を記録する**

✗ があれば `superpowers:systematic-debugging` で原因を探す。✓ になったら、#2 の距離・#6 でサービスが起こし直されたか（ログの `ride_load decision=Resume` と `startForeground failed` の有無）を ADR 0006 の「影響」に書き足し（親で `docs: ...` としてコミット）、PROJECT.md の区切り点の作業に進む。
