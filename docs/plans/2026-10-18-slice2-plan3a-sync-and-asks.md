# スライス2 計画3a: 送信の待ち行列と質問の保存 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 走行（名前・状態・区間）とルートの点が Backend へ送られ、送れなかった分は次の機会に送り直される。回答が届いた質問と Backend 側で失敗した質問が端末の DB に残り、記録中に始めた質問は走行に結びつく。

**Architecture:** 新しいパッケージ `sync` に、何を送るかを決める純粋な関数（`SyncPlan.kt`）と送信の係（`RideSync`）を置く。係は `SyncStore`（Room で実装）から未送信を読み、`RideApi`（`ApiClient`）で送る。契機（走行の変更の保存・300点ごと・前面に戻ったとき・起動したとき）が来るたびに未送信を全部送り、送るものが無ければ通信しない。質問は、一巡の司令塔が結果を `AskLog`（Room で実装）に渡して残す。端末の DB は版2にし、`asks` の表と、送信を断られた印の列と、未送信の点の索引を足す。

**Tech Stack:** Kotlin 2.3.20・AGP 9.0.1・Compose BOM 2026.03.01・Room 2.8.4・OkHttp 4.12.0・kotlinx.serialization 1.9.0・Robolectric 4.16（SDK 35）。足すのは `androidx.room:room-testing` 2.8.4（JVM のテストだけ）。

**Spec:** [docs/specs/2026-10-17-slice2-design.md](../specs/2026-10-17-slice2-design.md)（§4.6・§5.1〜5.3・§8・§9・§11）。送る形の正本は Backend の `openapi.yaml`。

**範囲に入れた issue（Android）:** #12（質問ごとに OkHttpClient を作っている）・#16（位置の監視を始められないと、1分ごとの書き込みの処理が増える）・#18（名前を UTF-16 の単位で切る）・#22（一時停止のあとで端末の時計が戻ると、区間が重なって送れなくなる）。

**計画を書くときに決めたこと（spec からの具体化。利用者と決めたものを含む）:**
- plan 3 を 3a（この plan: 送信・質問の保存）と 3b（タブ・ホームの走行のカードと SC-04 の質問の数・SC-16 と締め切りの計算し直し。issue #15・#19・#20）に分けた。質問の数は 3a の `asks` の表を読むので 3b に置く。
- 送信はアプリのプロセスの中で行う。WorkManager は使わない（spec §3 の判断と同じ）。契機は spec §5.3 の4つで、契機では未送信を調べるだけ。送るものが無ければ通信しない。圏外で終えて、そのままアプリを開かないと、次に開くまで送られない（端末の記録は消えない）。これは spec の想定どおりで、通信できないときの後送はスライス3で見直す。
- ルートのかたまりの番号 k には、走行の点を記録した順（`route_points.id`）に並べた 300k 番目から300点が入る。記録中は満ちたかたまりだけを送る。一時停止と終了では、満ちていない最後のかたまり（端数）も送る。あとで点が増えたら、同じ番号で送り直す（Backend は同じ番号を丸ごと上書きする）。泊まりで一時停止しても、その日の点がすべて届くように、利用者と決めた。spec §5.3 に書き足した。
- 「300点たまるごと」は、このプロセスで書いた点の数で数える（`RideSync.pointAdded`）。起動し直したあとの最初の契機は、かたまりの境目とずれることがあるが、遅れるのは最大で1かたまり分。
- 送ったかの印: 走行は `rides.sentUpdatedAt`（版1からある）、点は `route_points.chunk`（版1からある。送ったかたまりの番号）。送った点はいつも走行の頭からの連なりになる（かたまりは順に送り、失敗したらその走行の残りを送らない）。
- 400 の扱い: 走行のメタ情報は、断られた版の `updatedAt` を `rides.rejectedUpdatedAt` に残し、その版は送り直さない（名前や状態が変わって `updatedAt` が進めば、また送る）。ルートのかたまりは、送ったものとして `chunk` を付け、`rides.routeRejected` を立てる（一覧の「未送信あり」は plan 4 でこの2つの印から出す）。どちらもログに `sync_refused` を出す。400 以外の失敗（通信・接続キー・サーバー・DB）は、その回の送信をそこで終え、次の契機に任せる。
- 走行の `updatedAt` は、変わるたびに必ず前の値より進める（`maxOf(now, updatedAt + 1)`）。端末の時計が戻ると、Backend の条件付き書き込みが新しい版を古いとみなして捨てるため（#22 と同じ原因）。
- 送り先のユーザー名は、送る時点の設定のもの。途中でユーザー名を変えると、それより後に送る分は新しい名前の下に入る（スライス3の引き継ぎで扱う）。
- 質問の保存: 一巡が結果（回答あり・Backend 側の失敗）を受け取ったときと、ポーリングを120秒で打ち切ったとき（`timeout`）に残す。取り消した（待ち中に大きなボタンを押した）質問と、ポーリングが致命的な失敗（接続キーが無効など）で終わった質問は残さない（結果が分からないため）。`askId` が出る前の失敗も残さない（spec §5.2）。
- 質問の日時は Backend の `askedAt`、無ければ端末が送った時刻。回答の日時は端末が結果を受け取った時刻。入力の種類はスライス2では `voice` だけ。読み上げの音声を作れなかった（`tts_failed`）が文がある質問は「回答あり」。
- `rideId` は、一巡の始め（前面サービスを始めたあと、録音の前）に、記録中の走行があれば読む。そのあと一時停止しても、その質問は走行に結びついたまま。
- 質問を端末に書けなかったときも、ホームの「記録を保存できません」の帯を出す（spec §8）。
- `ApiClient` の `http` 引数は必須にし、`AppGraph` の1つの `OkHttpClient` を渡す（#12。渡し忘れをコンパイルで防ぐ）。
- 走行の PUT は、記録中の区間の `endedAt` と精度の無い点の `accuracy` を、項目を省かず `null` で送る（`openapi.yaml` で必須の項目のため）。質問の POST は、これまでどおり null の項目を省く。
- 名前の40字は、文字（コードポイント）で数える。Backend の `len()` と同じ数え方（#18）。
- 再開の時刻は、前の区間の終わりより前にしない（#22）。
- 位置の監視とその1分ごとの書き込みは、`RecordingWatch` にまとめ、二重に始めない。始められなかった監視は、次に種類が変わったときに試し直す（#16）。
- Room の Migration（版1→2）は足すだけなので軽い。`RideController.load()` の中で走るが、前面サービスの開始の時間切れにはかからない（PROJECT.md の持ち越し）。
- Room のスキーマの JSON は、debug のビルドの資産にも入れる。Robolectric の `MigrationTestHelper` は、テストする側のビルドの資産を読むため（`test` の資産は読まない）。release には入らない。

この計画のコードは、使い捨てのフォルダで JVM のテスト299件（始める前の251件＋48件）・エミュレーターのテスト4件・`assembleDebug`・`assembleRelease`（lint を含む）・`scripts/check-release-permissions.sh`（15件）が通ることを確かめてから書いた。

## Global Constraints

- 作業するリポジトリは `Android/`（`TouringProjectV2_Android`）と親。親のブランチ `slice2-plan3a` はこの plan のコミットで作ってある。Android は `main` から `slice2-plan3a` を切る（Task 0）。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- パッケージ名 `com.touringproject.v2`。minSdk 29・targetSdk 36・compileSdk 36。JDK 17。
- 作りの決まり（移行の spec §5）: 1つの Gradle モジュールをパッケージで分ける。状態機械と司令塔は Android に依存させず、外とのやり取りは interface を通す。部品は `AppGraph` で手で組む（DI のライブラリは入れない）。走行の状態を変えるのは `RideController` だけ。`sync` の判断と係は Android に依存させない。
- 送る形（`Backend/openapi.yaml`）: 時刻はタイムゾーン付きの ISO 8601（`Instant.toString()` の `Z`）。`status` は `recording`・`paused`・`ended`。`autoEnded` は終了の理由が自動のときだけ true（端末の停止は false）。名前は前後の空白を落として40字まで。点の `segment` は区間の番号（0から）。1かたまり300点まで。400 は送り直さない。
- 端末の DB は版2にする。Migration を書き、`MigrationTestHelper` で確かめる。破壊的な作り直し（`fallbackToDestructiveMigration`）は使わない。`app/schemas/` に書き出された `2.json` をコミットする。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミット・チャットに書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`（`rm` は置き換えられている）。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest`（絞るときは `--tests '*クラス名'` を引用符で囲む）。`-q` は付けない。重い実行はログをファイルに出す。ビルドのキャッシュで数秒で終わることがあるので、全体を確かめるときは `--rerun` を付け、`app/build/test-results/testDebugUnitTest/` の結果のファイルの時刻と件数を見る。Room の Entity・Migration を変えた直後の1回目は、古いスキーマの資産で失敗することがある（使い捨てのフォルダで一度あった）。そのときは `--rerun` で回し直す。
- 実機が USB で繋がったままエミュレーターのテストを回すときは、`export ANDROID_SERIAL=emulator-5554` でエミュレーターだけを指す。エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`（止めるときは `stop`）。起動の直後に「System UI isn't responding」が出たら「Wait」で閉じる。テストのあいだは利用者にエミュレーターに触らないよう頼む。
- Robolectric の決まり: SDK 35 で動かす。`withContext(Dispatchers.Main)` を使うコードはテストのスレッドから直に呼ばない。`runTest` の `backgroundScope` で動かした処理は `advanceUntilIdle` で進まない。Room の閉じた DB は取り消しの例外（`CancellationException`）を投げるので、書き込みの失敗の作り物には使わない（作り物の DAO で例外を投げる）。
- macOS に `timeout` コマンドは無い。ディスクの空きが少ないので、大きなものを入れる前に `df -h /` を見る。

## Review Focus

- 泊まりで一時停止し、そのままアプリが閉じられる（プロセスが消える）→ その日の最後の端数のかたまりは、一時停止の時点で送られている。再開して点が増えたら、同じ番号で送り直される。Task 5 の `a_pause_sends_the_partial_chunk_and_it_goes_again_once_it_is_full`。
- 圏外で走行を終え、通信できないまま次にアプリを開く → 送れなかったかたまりから順に送られ、送り終えた走行はもう送られない。Task 5 の `a_failure_ends_the_pass_and_the_next_one_sends_what_is_left`・Task 6 の `an_ended_ride_reaches_the_backend_and_the_next_pass_sends_nothing`。
- Backend が走行を 400 で断る（区間の重なりなど）→ 前面に戻るたびに同じ版を送り直さない。名前や状態が変われば、新しい版を送る。Task 5 の `a_refused_ride_is_not_sent_again_until_it_changes`。
- 回答を待っているあいだに一時停止する → その質問は走行に結びついたまま（`POST /asks` は待つ前に送ってある）。Task 4 の `the_ride_is_read_when_the_ask_starts_so_a_pause_meanwhile_does_not_drop_it`。
- 名前の40字目に絵文字がある名前を貼り付ける → 絵文字が半分で切れず、Backend に 400 で断られない。Task 1 の `a_pasted_name_is_never_cut_inside_an_emoji`・`a_name_is_counted_in_characters_so_an_emoji_counts_once`。

---

## ファイル構成（`Android/app/src/` から。`...` は `com/touringproject/v2`）

| パス | 役割 | Task |
|---|---|---|
| `main/java/.../ride/Ride.kt`・`ui/RideScreens.kt` | 名前を文字で数えて切る・再開の時刻・`updatedAt` を必ず進める | 1 |
| `main/java/.../api/ApiClient.kt`・`AppGraph.kt`・`ui/AppUi.kt` | 走行の `PUT` 2つ・`POST /asks` の `rideId`・`GET /asks` の追加項目・1つの `OkHttpClient` | 2 |
| `main/java/.../store/RideDatabase.kt`・`app/schemas/.../2.json`（生成）・`app/build.gradle.kts`・`gradle/libs.versions.toml` | DB の版2（`asks`・断られた印・未送信の点の索引）と Migration | 3 |
| `main/java/.../ask/AskRecord.kt`（新規）・`ask/AskPorts.kt`・`ask/AskController.kt`・`store/RoomAskLog.kt`（新規）・`AppGraph.kt`・`ui/AppUi.kt` | 質問の記録の組み立てと保存・`rideId` | 4 |
| `main/java/.../sync/SyncPlan.kt`・`sync/RideSync.kt`（新規） | 何を送るかの判断（純粋）と送信の係 | 5 |
| `main/java/.../store/RideDatabase.kt`・`store/RoomSyncStore.kt`（新規）・`ride/RidePorts.kt`・`ride/RideController.kt`・`AppGraph.kt`・`MainActivity.kt` | 送信の置き場と契機の配線 | 6 |
| `main/java/.../service/RecordingWatch.kt`（新規）・`service/RideForegroundService.kt` | 位置の監視と1分ごとの書き込みを二重に始めない | 7 |
| `README.md`（Android）・親の `docs/specs/2026-10-17-slice2-design.md`（この plan のコミットで直した）・`docs/07_units_contracts.md`・`docs-parent/`（写し） | 文書 | 9 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、始める前のテストを回す**

```bash
cd $ROOT && git switch slice2-plan3a
cd $AND && git switch main && git pull --ff-only && git switch -c slice2-plan3a
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-base.log 2>&1; tail -3 /tmp/trv2-base.log
```

Expected: `BUILD SUCCESSFUL`（始める前の JVM のテストは251件。この plan で48件増え、299件になる）。

---

### Task 1: 名前を文字で数える・区間を重ねない（#18・#22）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ride/Ride.kt`
- Modify: `app/src/main/java/com/touringproject/v2/ui/RideScreens.kt`（`NameField`）
- Test: `app/src/test/java/com/touringproject/v2/ride/RideTest.kt`・`app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt`

**Interfaces:**
- Consumes: `Ride`・`Segment`・`newRide`・`pause`・`resume`・`end`・`rideName`・`RIDE_NAME_MAX`（既存）
- Produces: `cutRideName(input: String): String`（名前の欄が残す先頭の40字）。`rideName` は文字（コードポイント）で数える。`Ride.resume` の新しい区間の開始は `maxOf(now, 前の区間の終わり)`。`pause`・`resume`・`end` の `updatedAt` は `maxOf(now, updatedAt + 1)`

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ride/RideTest.kt` の `class ReconcileTest {` の直前に足す:

```kotlin
class RideClockAndNameTest {
  private val started = newRide("r1", "箱根", 1_000, 7, MAX)

  @Test
  fun a_clock_set_back_during_the_pause_does_not_overlap_the_segments() {
    val resumed = started.pause(5_000).resume(3_000, 7, MAX)
    assertEquals(Segment(1, 5_000, null, 7), resumed.segments.last())
    assertEquals(5_000 + MAX, resumed.deadline)
  }

  @Test
  fun every_change_moves_updatedAt_forward_even_when_the_clock_goes_back() {
    val paused = started.pause(500)
    assertEquals(1_001L, paused.updatedAt)
    val resumed = paused.resume(400, 7, MAX)
    assertEquals(1_002L, resumed.updatedAt)
    assertEquals(1_003L, resumed.end(300, EndReason.MANUAL, 300).updatedAt)
    assertEquals(9_000L, started.pause(9_000).updatedAt)
  }

  @Test
  fun a_name_is_counted_in_characters_so_an_emoji_counts_once() {
    val name = "あ".repeat(39) + "😀"
    assertEquals(name, rideName(name))
    assertNull(rideName(name + "😀"))
    assertEquals(name, cutRideName(name + "😀"))
    assertEquals("箱根", cutRideName("箱根"))
  }
}
```

`app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt` の `the_start_sheet_says_why_without_the_location_permission` の直前に足す:

```kotlin
  @Test
  fun a_pasted_name_is_never_cut_inside_an_emoji() {
    var started: String? = null
    rule.setContent { StartRideSheet(locationAllowed = true, onStart = { started = it }, onDismiss = {}) }
    rule.onNodeWithTag("rideName").performTextInput("あ".repeat(39) + "😀😀")
    rule.onNodeWithTag("startGo").performClick()
    assertEquals("あ".repeat(39) + "😀", started)
  }
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideClockAndNameTest' --tests '*RideScreensTest' > /tmp/trv2-t1.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t1.log`
Expected: `cutRideName` が無いのでコンパイルの失敗（`e: ... Unresolved reference 'cutRideName'`）

- [ ] **Step 3: 実装する**

`Ride.kt` の `rideName` を、次に置き換える:

```kotlin
// Characters are counted as code points, as the Backend counts them, so an emoji is never cut in half (Android #18).
private fun String.characters() = codePointCount(0, length)

/** Returns the trimmed name, or null when it cannot name a ride (SC-17, SC-04: required, up to 40 characters). */
fun rideName(input: String): String? = input.trim().takeIf { it.isNotEmpty() && it.characters() <= RIDE_NAME_MAX }

/** What the name field keeps of a typed or pasted name: its first 40 characters. */
fun cutRideName(input: String): String =
  if (input.characters() <= RIDE_NAME_MAX) input else input.substring(0, input.offsetByCodePoints(0, RIDE_NAME_MAX))
```

`private fun Ride.closeOpenSegment` の直前に足す:

```kotlin
// The Backend keeps a ride only when its updatedAt is newer than the one it has, so every change moves it forward,
// even when the device's clock has been set back.
private fun Ride.touched(now: Long) = maxOf(now, updatedAt + 1)
```

`Ride.pause` の `updatedAt = now` を `updatedAt = touched(now)` に、`Ride.end` の `updatedAt = now` を `updatedAt = touched(now)` に替える。`Ride.resume` を、次に置き換える:

```kotlin
/** A clock set back during the pause does not start the new segment before the last one ended (Android #22). */
fun Ride.resume(now: Long, bootCount: Int?, maxRecordingMs: Long): Ride {
  check(status == RideStatus.PAUSED) { "only a paused ride can resume" }
  val last = segments.last()
  val startedAt = maxOf(now, last.endedAt ?: now)
  val next = Segment(last.seq + 1, startedAt, null, bootCount)
  return copy(
    status = RideStatus.RECORDING, segments = segments + next, deadline = startedAt + maxRecordingMs, lastAliveAt = now, updatedAt = touched(now),
  )
}
```

`RideScreens.kt` の `NameField` の `onValueChange = { onChange(it.take(RIDE_NAME_MAX)) },` を `onValueChange = { onChange(cutRideName(it)) },` に替え、import の `com.touringproject.v2.ride.RIDE_NAME_MAX` を `com.touringproject.v2.ride.cutRideName` に替える。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideClockAndNameTest' --tests '*RideScreensTest' --tests '*RideControllerTest' --tests '*RideTest' > /tmp/trv2-t1.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t1.log`
Expected: `BUILD SUCCESSFUL`（`RideClockAndNameTest` 3件・`RideScreensTest` 9件・`RideControllerTest` 25件・`RideTest` 7件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ride/Ride.kt app/src/main/java/com/touringproject/v2/ui/RideScreens.kt \
  app/src/test/java/com/touringproject/v2/ride/RideTest.kt app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt
git commit -m "fix: count ride names in characters and never overlap segments" -m "Fixes #18" -m "Fixes #22"
```

---

### Task 2: API（走行の PUT・`rideId`・結果の追加項目・1つの OkHttpClient。#12）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/api/ApiClient.kt`
- Modify: `app/src/main/java/com/touringproject/v2/AppGraph.kt`・`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`（`ApiClient` を作るところ）
- Test: `app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt`

**Interfaces:**
- Consumes: 既存の `ApiClient.request`・`TRANSIENT`・`ApiError`
- Produces: `AskBody.rideId: String?`・`AskResult.askedAt: String?`・`AskResult.address: String?`・`AskResult.headingDegrees: Double?`・`data class SegmentBody(startedAt: String, endedAt: String?)`・`data class RideBody(name, status, segments: List<SegmentBody>, autoEnded: Boolean, updatedAt: String)`・`data class PointBody(t: String, lat, lon, accuracy: Double?, segment: Int)`・`data class RouteBody(points: List<PointBody>)`・`interface RideApi { suspend fun putRide(rideId, body: RideBody); suspend fun putRoute(rideId, seq: Int, body: RouteBody) }`（400 は `ApiError(BAD_REQUEST)`）。`ApiClient(baseUrl, apiKey, userName, http: OkHttpClient, maxAttempts = 3, timeoutMs = 15_000, retryDelay)` は `AskApi, RideApi`。`AppGraph.http: OkHttpClient`

- [ ] **Step 1: 失敗するテストを書く**

`ApiClientTest.kt` の import に `kotlinx.serialization.json.JsonNull`・`kotlinx.serialization.json.jsonArray`・`okhttp3.OkHttpClient` を足し、`client()` を次に置き換える:

```kotlin
  private val delays = mutableListOf<Long>()
  private val http = OkHttpClient()

  private fun client(timeoutMs: Long = 15_000) =
    ApiClient(server.url("/Prod/").toString(), "key-1", "rider01", http, timeoutMs = timeoutMs, retryDelay = { delays += it })
```

クラスの最後に足す:

```kotlin
  @Test
  fun clients_made_from_one_http_client_share_its_connections() = runTest {
    repeat(2) { server.enqueue(json(200, """{"askId":"a1","status":"processing"}""")) }
    client().getAsk("a1")
    client().getAsk("a1")
    server.takeRequest()
    // The second request is the second one on the first request's connection.
    assertEquals(1, server.takeRequest().sequenceNumber)
  }

  @Test
  fun postAsk_sends_the_ride_id_only_when_there_is_one() = runTest {
    repeat(2) { server.enqueue(json(202, """{"askId":"a1","conversationId":"c1","conversationExpiresAt":"2026-01-01T00:15:00Z"}""")) }
    client().postAsk(AskBody(text = "q", rideId = "r1"))
    client().postAsk(AskBody(text = "q"))
    assertEquals("r1", Json.parseToJsonElement(server.takeRequest().body.readUtf8()).jsonObject["rideId"]!!.jsonPrimitive.content)
    assertFalse("rideId" in Json.parseToJsonElement(server.takeRequest().body.readUtf8()).jsonObject)
  }

  @Test
  fun getAsk_reads_when_where_and_which_way() = runTest {
    server.enqueue(json(200, """{"askId":"a1","status":"completed","audio":[],"timings":{},"askedAt":"2026-10-18T01:02:03.456Z","address":"静岡県御殿場市","headingDegrees":92.5}"""))
    val result = client().getAsk("a1")
    assertEquals("2026-10-18T01:02:03.456Z", result.askedAt)
    assertEquals("静岡県御殿場市", result.address)
    assertEquals(92.5, result.headingDegrees!!, 0.0)
  }

  @Test
  fun putRide_sends_the_whole_ride_with_its_open_segment_as_null() = runTest {
    server.enqueue(json(200, """{"rideId":"r1","applied":true}"""))
    val body = RideBody("箱根", "recording", listOf(SegmentBody("2026-10-18T01:00:00Z", null)), false, "2026-10-18T01:00:00Z")
    client().putRide("r1", body)
    val request = server.takeRequest()
    assertEquals("PUT", request.method)
    assertEquals("/Prod/rides/r1", request.path)
    assertEquals("rider01", request.getHeader("x-user-name"))
    val sent = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
    assertEquals("recording", sent["status"]!!.jsonPrimitive.content)
    assertEquals(JsonNull, sent["segments"]!!.jsonArray.single().jsonObject["endedAt"])
  }

  @Test
  fun putRoute_sends_the_chunk_under_its_number() = runTest {
    server.enqueue(json(200, """{"rideId":"r1","seq":3}"""))
    client().putRoute("r1", 3, RouteBody(listOf(PointBody("2026-10-18T01:00:05Z", 35.0, 139.0, null, 0))))
    val request = server.takeRequest()
    assertEquals("/Prod/rides/r1/route/3", request.path)
    val point = Json.parseToJsonElement(request.body.readUtf8()).jsonObject["points"]!!.jsonArray.single().jsonObject
    assertEquals(JsonNull, point["accuracy"])
    assertEquals(0, point["segment"]!!.jsonPrimitive.content.toInt())
  }

  @Test
  fun a_put_is_retried_when_the_server_fails_but_not_when_it_rejects_the_input() = runTest {
    server.enqueue(json(503))
    server.enqueue(json(200, """{"rideId":"r1","seq":0}"""))
    client().putRoute("r1", 0, RouteBody(listOf(PointBody("2026-10-18T01:00:05Z", 35.0, 139.0, 5.0, 0))))
    assertEquals(2, server.requestCount)
    server.enqueue(json(400, """{"error":"bad_request","message":"segments must not overlap"}"""))
    val error = runCatching {
      client().putRide("r1", RideBody("箱根", "paused", listOf(SegmentBody("2026-10-18T01:00:00Z", "2026-10-18T02:00:00Z")), false, "2026-10-18T02:00:00Z"))
    }.exceptionOrNull() as ApiError
    assertEquals(ApiErrorKind.BAD_REQUEST, error.kind)
    assertEquals(3, server.requestCount)
  }
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ApiClientTest' > /tmp/trv2-t2.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t2.log | head`
Expected: コンパイルの失敗（`RideBody`・`rideId` などが無い）

- [ ] **Step 3: 実装する**

`ApiClient.kt` の `AskBody` の最後の項目 `val volumeDb: Int? = null,` のあとに足す:

```kotlin
  /** Only for an ask started while a ride is recording (slice 2 spec §4.6). */
  val rideId: String? = null,
```

`AskResult` の最後の項目 `val error: String? = null,` のあとに足す:

```kotlin
  /** When the Backend took the ask in (UTC). */
  val askedAt: String? = null,
  val address: String? = null,
  val headingDegrees: Double? = null,
```

`interface AskApi { ... }` のあとに足す:

```kotlin
// A ride and its route (slice 2 spec §6.2). Times are ISO 8601 with their time zone.
@Serializable data class SegmentBody(val startedAt: String, val endedAt: String?)

@Serializable
data class RideBody(val name: String, val status: String, val segments: List<SegmentBody>, val autoEnded: Boolean, val updatedAt: String)

@Serializable data class PointBody(val t: String, val lat: Double, val lon: Double, val accuracy: Double?, val segment: Int)

@Serializable data class RouteBody(val points: List<PointBody>)

/** Both calls may be sent again and again: the Backend keeps one copy of each. A 400 throws BAD_REQUEST. */
interface RideApi {
  suspend fun putRide(rideId: String, body: RideBody)
  suspend fun putRoute(rideId: String, seq: Int, body: RouteBody)
}
```

`class ApiClient(` の宣言を、次に置き換える（`http` を必須にし、`RideApi` を足す）:

```kotlin
/** http is the app's one OkHttpClient, so every client shares its connections and threads (Android #12). */
class ApiClient(
  baseUrl: String,
  private val apiKey: String,
  private val userName: String,
  http: OkHttpClient,
  private val maxAttempts: Int = 3,
  timeoutMs: Long = 15_000,
  private val retryDelay: suspend (Long) -> Unit = { delay(it) },
) : AskApi, RideApi {
```

`private val json = ...` の次の行に足す:

```kotlin
  // The ride's open segment and a point without an accuracy are sent as null, as the contract writes them.
  private val rideJson = Json { explicitNulls = true }
```

`suspend fun checkKey()` の直前に足す:

```kotlin
  override suspend fun putRide(rideId: String, body: RideBody) {
    request("PUT", "/rides/$rideId", rideJson.encodeToString(RideBody.serializer(), body), TRANSIENT)
  }

  override suspend fun putRoute(rideId: String, seq: Int, body: RouteBody) {
    request("PUT", "/rides/$rideId/route/$seq", rideJson.encodeToString(RouteBody.serializer(), body), TRANSIENT)
  }

```

`AppGraph.kt`: `val apiBaseUrl: String = BuildConfig.API_BASE_URL` の次の行に足し、import に `okhttp3.OkHttpClient` を足す:

```kotlin
  /** The one HTTP client of the app: every ApiClient shares its connections and threads (Android #12). */
  val http = OkHttpClient()
```

`AskDeps` の `api = { key, user -> ApiClient(apiBaseUrl, key, user) },` を `api = { key, user -> ApiClient(apiBaseUrl, key, user, http) },` に替える。

`AppUi.kt` の `ConnectionScreen` の `check = { key -> ApiClient(graph.apiBaseUrl, key, current.userName).checkKey() },` を `check = { key -> ApiClient(graph.apiBaseUrl, key, current.userName, graph.http).checkKey() },` に替える。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ApiClientTest' > /tmp/trv2-t2.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t2.log`
Expected: `BUILD SUCCESSFUL`（14件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/api/ApiClient.kt app/src/main/java/com/touringproject/v2/AppGraph.kt \
  app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
git commit -m "feat: send rides and route chunks through one shared HTTP client" -m "Fixes #12"
```

---

### Task 3: 端末の DB の版2

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/store/RideDatabase.kt`
- Modify: `gradle/libs.versions.toml`・`app/build.gradle.kts`
- Create: `app/schemas/com.touringproject.v2.store.RideDatabase/2.json`（ビルドで生成される）
- Test: `app/src/test/java/com/touringproject/v2/store/MigrationTest.kt`（新規）・`app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt`

**Interfaces:**
- Consumes: 既存の `RideEntity`・`RideDao.saveRide`
- Produces: `RideEntity.rejectedUpdatedAt: Long? = null`・`RideEntity.routeRejected: Boolean = false`・`route_points` の索引 `(chunk, rideId)`・`@Entity(tableName = "asks") data class AskEntity(askId, askedAt, answeredAt?, transcript?, answer?, latitude?, longitude?, address?, headingDegrees?, input, conversationId, newConversation, status, failure?, rideId?)`・`interface AskDao { upsert(AskEntity); ask(askId): AskEntity? }`・`RideDatabase.asks(): AskDao`・`val MIGRATION_1_2`。`saveRide` は3つの送信の印（`sentUpdatedAt`・`rejectedUpdatedAt`・`routeRejected`）を残す

- [ ] **Step 1: 道具を足す**

`gradle/libs.versions.toml` の `[libraries]` の `androidx-room-compiler` の次の行に足す:

```toml
androidx-room-testing = { module = "androidx.room:room-testing", version.ref = "room" }
```

`app/build.gradle.kts` の `testOptions { ... }` の閉じ括弧のあとに足す:

```kotlin
  // MigrationTestHelper reads the exported schemas as assets. Robolectric sees the assets of the build under test, so
  // they go into the debug build (never the release one).
  sourceSets {
    getByName("debug").assets.srcDir("$projectDir/schemas")
  }
```

`dependencies` の `testImplementation(libs.androidx.compose.ui.test.junit4)` の次の行に足す:

```kotlin
  testImplementation(libs.androidx.room.testing)
```

- [ ] **Step 2: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/store/MigrationTest.kt`:

```kotlin
package com.touringproject.v2.store

import androidx.room.Room
import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

private const val DB = "migration-test.db"

@RunWith(AndroidJUnit4::class)
class MigrationTest {
  @get:Rule
  val helper = MigrationTestHelper(InstrumentationRegistry.getInstrumentation(), RideDatabase::class.java, emptyList(), FrameworkSQLiteOpenHelperFactory())

  @Test
  fun version_1_moves_to_2_keeping_rides_and_points() {
    helper.createDatabase(DB, 1).apply {
      execSQL("INSERT INTO rides VALUES ('r1', '箱根', 'ended', 'manual', NULL, 5000, 120.0, 6000, 6000)")
      execSQL("INSERT INTO ride_segments VALUES ('r1', 0, 1000, 5000, 7)")
      execSQL("INSERT INTO route_points (rideId, segment, t, lat, lon, accuracy, chunk) VALUES ('r1', 0, 2000, 35.0, 139.0, 5.0, NULL)")
      close()
    }
    helper.runMigrationsAndValidate(DB, 2, true, MIGRATION_1_2).close()
    val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
      .addMigrations(MIGRATION_1_2)
      .allowMainThreadQueries()
      .build()
    runBlocking {
      val ride = db.rides().ride("r1")!!
      assertEquals(6_000L, ride.sentUpdatedAt)
      assertNull(ride.rejectedUpdatedAt)
      assertFalse(ride.routeRejected)
      assertEquals(1, db.rides().points("r1").size)
      assertNull(db.asks().ask("a1"))
    }
    db.close()
  }
}
```

`RoomRideStoreTest.kt` の `saving_again_keeps_what_the_backend_has_accepted` を、次に置き換え、import に `org.junit.Assert.assertTrue` を足す:

```kotlin
  @Test
  fun saving_again_keeps_what_the_backend_has_accepted_or_refused() = runBlocking {
    store.save(ride)
    dao.upsertRide(dao.ride("r1")!!.copy(sentUpdatedAt = 1_000, rejectedUpdatedAt = 900, routeRejected = true))
    store.save(ride.pause(5_000))
    val saved = dao.ride("r1")!!
    assertEquals(1_000L, saved.sentUpdatedAt)
    assertEquals(900L, saved.rejectedUpdatedAt)
    assertTrue(saved.routeRejected)
    assertEquals(RideStatus.PAUSED, store.active()?.status)
  }
```

- [ ] **Step 3: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*MigrationTest' --tests '*RoomRideStoreTest' > /tmp/trv2-t3.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t3.log | head`
Expected: コンパイルの失敗（`MIGRATION_1_2`・`asks()`・`rejectedUpdatedAt` が無い）

- [ ] **Step 4: 実装する**

`RideDatabase.kt` の import に `androidx.room.ColumnInfo`・`androidx.room.migration.Migration`・`androidx.sqlite.db.SupportSQLiteDatabase` を足す。

`RideEntity` の最後の項目 `val sentUpdatedAt: Long?,` のあとに足す:

```kotlin
  /** The updatedAt the Backend refused with 400; that version is not sent again (slice 2 spec §5.3). */
  val rejectedUpdatedAt: Long? = null,
  /** True once the Backend has refused one of the ride's route chunks with 400. */
  @ColumnInfo(defaultValue = "0") val routeRejected: Boolean = false,
```

`RoutePointEntity` の `indices = [Index(value = ["rideId", "segment", "t"])],` を、次に置き換える:

```kotlin
  // chunk first: finding the rides with points left to send reads only the unsent ones (slice 2 plan 3a).
  indices = [Index(value = ["rideId", "segment", "t"]), Index(value = ["chunk", "rideId"])],
```

`@Dao interface RideDao {` の直前に足す:

```kotlin
/** An ask whose loop ended with an answer or a failure the Backend reported (slice 2 spec §5.2). */
@Entity(tableName = "asks", indices = [Index(value = ["rideId"]), Index(value = ["askedAt"])])
data class AskEntity(
  @PrimaryKey val askId: String,
  val askedAt: Long,
  /** When the answer arrived; null for a failed ask. */
  val answeredAt: Long?,
  val transcript: String?,
  val answer: String?,
  val latitude: Double?,
  val longitude: Double?,
  val address: String?,
  val headingDegrees: Double?,
  /** voice / text */
  val input: String,
  val conversationId: String,
  /** True for the first ask of a conversation: the conversation breaks just before it (US-C-03.004). */
  val newConversation: Boolean,
  /** answered / failed */
  val status: String,
  /** no_speech / transcribe_failed / agent_failed / tts_failed / timeout; null when answered */
  val failure: String?,
  /** The ride that was recording when the ask started; null when none was. Not a foreign key: a ride's row may be missing for a while after a failed save. */
  val rideId: String?,
)

@Dao
interface AskDao {
  @Upsert
  suspend fun upsert(ask: AskEntity)

  @Query("SELECT * FROM asks WHERE askId = :askId")
  suspend fun ask(askId: String): AskEntity?
}
```

`RideDao.saveRide` を、次に置き換える:

```kotlin
  /** Keeps the sending markers: a save never undoes what the Backend has already accepted or refused. */
  @Transaction
  suspend fun saveRide(ride: RideEntity, segments: List<SegmentEntity>) {
    val saved = ride(ride.id)
    upsertRide(
      ride.copy(sentUpdatedAt = saved?.sentUpdatedAt, rejectedUpdatedAt = saved?.rejectedUpdatedAt, routeRejected = saved?.routeRejected ?: false),
    )
    deleteSegments(ride.id)
    insertSegments(segments)
  }
```

`@Database(...)` から最後までを、次に置き換える:

```kotlin
@Database(entities = [RideEntity::class, SegmentEntity::class, RoutePointEntity::class, AskEntity::class], version = 2, exportSchema = true)
abstract class RideDatabase : RoomDatabase() {
  abstract fun rides(): RideDao
  abstract fun asks(): AskDao

  companion object {
    fun open(context: Context): RideDatabase =
      Room.databaseBuilder(context, RideDatabase::class.java, "rides.db").addMigrations(MIGRATION_1_2).build()
  }
}

/**
 * 1 -> 2 (slice 2 plan 3a): the asks table, the rides' markers for what the Backend refused, and an index for the
 * points left to send. It only adds, so it stays quick: it runs inside RideController.load(), which the service awaits
 * before startForeground (adr/0006).
 */
val MIGRATION_1_2 = object : Migration(1, 2) {
  override fun migrate(db: SupportSQLiteDatabase) {
    db.execSQL("ALTER TABLE `rides` ADD COLUMN `rejectedUpdatedAt` INTEGER")
    db.execSQL("ALTER TABLE `rides` ADD COLUMN `routeRejected` INTEGER NOT NULL DEFAULT 0")
    db.execSQL(
      "CREATE TABLE IF NOT EXISTS `asks` (`askId` TEXT NOT NULL, `askedAt` INTEGER NOT NULL, `answeredAt` INTEGER, " +
        "`transcript` TEXT, `answer` TEXT, `latitude` REAL, `longitude` REAL, `address` TEXT, `headingDegrees` REAL, " +
        "`input` TEXT NOT NULL, `conversationId` TEXT NOT NULL, `newConversation` INTEGER NOT NULL, `status` TEXT NOT NULL, " +
        "`failure` TEXT, `rideId` TEXT, PRIMARY KEY(`askId`))",
    )
    db.execSQL("CREATE INDEX IF NOT EXISTS `index_asks_rideId` ON `asks` (`rideId`)")
    db.execSQL("CREATE INDEX IF NOT EXISTS `index_asks_askedAt` ON `asks` (`askedAt`)")
    db.execSQL("CREATE INDEX IF NOT EXISTS `index_route_points_chunk_rideId` ON `route_points` (`chunk`, `rideId`)")
  }
}
```

- [ ] **Step 5: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*MigrationTest' --tests '*RoomRideStoreTest' --rerun > /tmp/trv2-t3.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t3.log; ls app/schemas/com.touringproject.v2.store.RideDatabase/`
Expected: `BUILD SUCCESSFUL`（`MigrationTest` 1件・`RoomRideStoreTest` 4件）。`1.json` と `2.json` がある。Migration の SQL は、`2.json` の `createSql` と同じ形でないと検査で落ちる（`MigrationTestHelper` が表・列・既定値・索引を比べる）

- [ ] **Step 6: コミット**

```bash
cd $AND && git add gradle/libs.versions.toml app/build.gradle.kts app/src/main/java/com/touringproject/v2/store/RideDatabase.kt \
  app/schemas/com.touringproject.v2.store.RideDatabase/2.json \
  app/src/test/java/com/touringproject/v2/store/MigrationTest.kt app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt
git commit -m "feat: add the asks table, the ride's refused markers and an unsent-points index in database version 2"
```

---

### Task 4: 質問の保存と `rideId`

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ask/AskRecord.kt`・`app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt`
- Modify: `app/src/main/java/com/touringproject/v2/ask/AskPorts.kt`・`app/src/main/java/com/touringproject/v2/ask/AskController.kt`・`app/src/main/java/com/touringproject/v2/AppGraph.kt`・`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`
- Test: `app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt`・`app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt`（新規）

**Interfaces:**
- Consumes: `AskResult.askedAt`・`address`・`headingDegrees`・`AskBody.rideId`（Task 2）、`AskEntity`・`AskDao`・`RideDatabase.asks()`（Task 3）
- Produces: `enum class AskOutcome { ANSWERED, FAILED }`・`ASK_INPUT_VOICE`・`TIMEOUT_FAILURE`・`data class AskRecord(...)`・`data class SentAsk(askId, conversationId, newConversation, sentAt, here: Fix?, rideId: String?)`・`readable(AskResult): Boolean`・`askRecord(sent: SentAsk, result: AskResult?, now: Long): AskRecord`・`fun interface AskLog { fun keep(record: AskRecord) }`・`AskDeps.asks: AskLog`・`AskDeps.rideId: () -> String?`・`class RoomAskLog(dao: AskDao, scope, log): AskLog`（`failed: StateFlow<Boolean>`・`suspend fun save(record)`）・`AppGraph.askLog`

- [ ] **Step 1: 失敗するテストを書く**

`AskControllerTest.kt` の import に `kotlinx.coroutines.test.advanceUntilIdle` を足す。`Harness` の引数の最後（`val pcm: ByteArray = byteArrayOf(1, 2, 3),` のあと）に `var rideId: String? = null,` を足し、`val transcripts = ...` の次の行に `val kept = mutableListOf<AskRecord>()` を足す。`AskDeps(...)` の `recordings = object : RecordingSink { ... },` のあとに足す:

```kotlin
    asks = { kept += it },
    rideId = { rideId },
```

`class AskControllerTest` の最後に足し、ファイルの最後に `AskRecordTest` を足す:

```kotlin
  @Test
  fun an_answered_ask_is_kept_with_where_it_was_asked() = runTest {
    val h = Harness(this, stopAfterMs = 1_000)
    h.controller.run(Source.HANDSFREE)
    val kept = h.kept.single()
    assertEquals("a1", kept.askId)
    assertEquals(AskOutcome.ANSWERED, kept.outcome)
    assertEquals("愛鷹山です。", kept.answer)
    assertEquals(HERE.latitude, kept.latitude!!, 0.0)
    assertEquals("c1", kept.conversationId)
    assertTrue(kept.newConversation)
    assertEquals(null, kept.rideId)
  }

  @Test
  fun the_next_ask_of_the_conversation_does_not_start_a_new_one() = runTest {
    val h = Harness(this, stopAfterMs = null)
    h.controller.run(Source.HANDSFREE)
    h.controller.run(Source.HANDSFREE)
    assertEquals(listOf(true, false), h.kept.map { it.newConversation })
  }

  @Test
  fun a_failure_the_backend_reports_is_kept_with_its_reason() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, answers = listOf(done(status = "failed", error = "no_speech", answer = null, audio = emptyList())))
    h.controller.run(Source.HANDSFREE)
    val kept = h.kept.single()
    assertEquals(AskOutcome.FAILED, kept.outcome)
    assertEquals("no_speech", kept.failure)
    assertEquals(null, kept.answeredAt)
  }

  @Test
  fun an_ask_that_timed_out_is_kept_as_a_timeout() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, answers = List(200) { PROCESSING })
    h.controller.run(Source.HANDSFREE)
    assertEquals(TIMEOUT_FAILURE, h.kept.single().failure)
  }

  @Test
  fun an_ask_the_backend_never_took_in_is_not_kept() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, post = { throw ApiError(ApiErrorKind.NETWORK) })
    h.controller.run(Source.HANDSFREE)
    assertTrue(h.kept.isEmpty())
  }

  @Test
  fun an_ask_cancelled_while_waiting_is_not_kept() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, answers = List(200) { PROCESSING })
    launch { h.controller.run(Source.HANDSFREE) }
    h.until { h.phase == Phase.WAITING }
    h.controller.cancel()
    advanceUntilIdle()
    assertTrue(h.kept.isEmpty())
  }

  @Test
  fun an_ask_started_while_a_ride_records_goes_with_the_ride() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, rideId = "r1")
    h.controller.run(Source.HANDSFREE)
    assertEquals("r1", h.bodies.single().rideId)
    assertEquals("r1", h.kept.single().rideId)
  }

  @Test
  fun the_ride_is_read_when_the_ask_starts_so_a_pause_meanwhile_does_not_drop_it() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, rideId = "r1")
    launch { h.controller.run(Source.HANDSFREE) }
    h.until { h.phase == Phase.RECORDING }
    h.rideId = null
    advanceUntilIdle()
    assertEquals("r1", h.bodies.single().rideId)
  }
}

class AskRecordTest {
  private val sent = SentAsk("a1", "c1", true, 5_000, Fix(35.0, 139.0, 4_000, 5.0), "r1")

  @Test
  fun the_backend_time_of_the_ask_is_kept_and_the_device_time_stands_in_without_it() {
    val result = AskResult("a1", "completed", "Q", "A", askedAt = "2026-10-18T01:02:03.456Z", address = "御殿場市", headingDegrees = 90.0)
    val kept = askRecord(sent, result, 9_000)
    assertEquals(java.time.Instant.parse("2026-10-18T01:02:03.456Z").toEpochMilli(), kept.askedAt)
    assertEquals(9_000L, kept.answeredAt)
    assertEquals("御殿場市", kept.address)
    assertEquals(5_000L, askRecord(sent, result.copy(askedAt = null), 9_000).askedAt)
  }

  @Test
  fun text_whose_speech_failed_is_an_answer_and_a_failure_without_a_reason_is_the_agents() {
    assertEquals(AskOutcome.ANSWERED, askRecord(sent, AskResult("a1", "failed", "Q", "A", error = "tts_failed"), 9_000).outcome)
    val failed = askRecord(sent, AskResult("a1", "failed", "Q", null), 9_000)
    assertEquals(AskOutcome.FAILED, failed.outcome)
    assertEquals("agent_failed", failed.failure)
  }
}
```

`app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt`:

```kotlin
package com.touringproject.v2.store

import android.app.Application
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.touringproject.v2.ask.ASK_INPUT_VOICE
import com.touringproject.v2.ask.AskOutcome
import com.touringproject.v2.ask.AskRecord
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.IOException

@RunWith(AndroidJUnit4::class)
class RoomAskLogTest {
  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
    .allowMainThreadQueries()
    .build()
  private val errors = mutableListOf<String>()
  private val log = RoomAskLog(db.asks(), kotlinx.coroutines.MainScope()) { message, _ -> errors += message }
  private val record = AskRecord(
    "a1", 1_000, 9_000, "Q", "A", 35.0, 139.0, "御殿場市", 90.0, ASK_INPUT_VOICE, "c1", true, AskOutcome.ANSWERED, null, "r1",
  )

  @Test
  fun a_kept_ask_is_stored_with_its_ride_and_outcome() = runBlocking {
    log.save(record)
    val stored = db.asks().ask("a1")!!
    assertEquals("answered", stored.status)
    assertEquals("r1", stored.rideId)
    assertTrue(stored.newConversation)
    assertFalse(log.failed.value)
    db.close()
  }

  @Test
  fun a_failed_write_is_logged_and_shown_until_the_next_one_works() = runBlocking {
    var full = true
    val dao = object : AskDao {
      override suspend fun upsert(ask: AskEntity) = if (full) throw IOException("disk full") else Unit
      override suspend fun ask(askId: String): AskEntity? = null
    }
    val failing = RoomAskLog(dao, kotlinx.coroutines.MainScope()) { message, _ -> errors += message }
    failing.save(record)
    assertTrue(failing.failed.value)
    assertEquals(1, errors.size)
    full = false
    failing.save(record)
    assertFalse(failing.failed.value)
    db.close()
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AskControllerTest' --tests '*AskRecordTest' --tests '*RoomAskLogTest' > /tmp/trv2-t4.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t4.log | head`
Expected: コンパイルの失敗（`AskRecord`・`asks`・`rideId`・`RoomAskLog` が無い）

- [ ] **Step 3: 質問の記録を組み立てる関数を書く**

`app/src/main/java/com/touringproject/v2/ask/AskRecord.kt`:

```kotlin
package com.touringproject.v2.ask

import com.touringproject.v2.api.AskResult
import com.touringproject.v2.location.Fix
import java.time.OffsetDateTime

// What the device keeps of an ask (slice 2 spec §5.2). The Backend makes the record; the app keeps its own copy and
// never sends it back (07 UC-7).

enum class AskOutcome { ANSWERED, FAILED }

/** Slice 2 asks only by voice; text asks come in slice 4. */
const val ASK_INPUT_VOICE = "voice"

const val TIMEOUT_FAILURE = "timeout"

data class AskRecord(
  val askId: String,
  val askedAt: Long,
  /** When the answer arrived; null for a failed ask. */
  val answeredAt: Long?,
  val transcript: String?,
  val answer: String?,
  val latitude: Double?,
  val longitude: Double?,
  val address: String?,
  val headingDegrees: Double?,
  val input: String,
  val conversationId: String,
  /** True for the first ask of a conversation: the conversation breaks just before it (US-C-03.004). */
  val newConversation: Boolean,
  val outcome: AskOutcome,
  /** The Backend's error, or "timeout"; null when answered. */
  val failure: String?,
  /** The ride that was recording when the ask started (slice 2 spec §4.6). */
  val rideId: String?,
)

/** What the loop knows once the Backend has taken the ask in. */
data class SentAsk(
  val askId: String,
  val conversationId: String,
  val newConversation: Boolean,
  val sentAt: Long,
  val here: Fix?,
  val rideId: String?,
)

/** An answer the rider can hear: a completed one, or text whose speech the Backend failed to make. */
fun readable(result: AskResult): Boolean = result.status == "completed" || (result.error == "tts_failed" && !result.answer.isNullOrEmpty())

/** result is the finished result, or null when polling gave up at 120 s (kept as a timeout). */
fun askRecord(sent: SentAsk, result: AskResult?, now: Long): AskRecord {
  val answered = result != null && readable(result)
  return AskRecord(
    askId = sent.askId,
    askedAt = result?.askedAt?.let { runCatching { OffsetDateTime.parse(it).toInstant().toEpochMilli() }.getOrNull() } ?: sent.sentAt,
    answeredAt = if (answered) now else null,
    transcript = result?.transcript,
    answer = result?.answer,
    latitude = sent.here?.latitude,
    longitude = sent.here?.longitude,
    address = result?.address,
    headingDegrees = result?.headingDegrees,
    input = ASK_INPUT_VOICE,
    conversationId = sent.conversationId,
    newConversation = sent.newConversation,
    outcome = if (answered) AskOutcome.ANSWERED else AskOutcome.FAILED,
    failure = when {
      answered -> null
      result == null -> TIMEOUT_FAILURE
      else -> result.error ?: "agent_failed"
    },
    rideId = sent.rideId,
  )
}
```

- [ ] **Step 4: 窓口を足し、司令塔から残す**

`AskPorts.kt` の `interface Positions {` の直前に足す:

```kotlin
/** Fire and forget: a failure to keep an ask must not end it. */
fun interface AskLog {
  fun keep(record: AskRecord)
}

```

`AskDeps` の `val recordings: RecordingSink,` の次の行に足す:

```kotlin
  /** Where the asks that reached the Backend are kept (slice 2 spec §5.2). */
  val asks: AskLog,
  /** The id of the ride that is recording now, or null (paused or none: slice 2 spec §4.6). */
  val rideId: () -> String?,
```

`AskController.kt` を次のとおり直す。import の `com.touringproject.v2.api.AskAccepted` は使わなくなるので消す。

`run()` の次の4行:

```kotlin
      serviceRunning = true
      val recording = record(run) ?: return
      val accepted = send(recording, api, run) ?: return
      maybeReturn(ReturnTiming.SENT, settings, run)
      val result = waitForAnswer(accepted.askId, recording.name, api, run) ?: return
```

を、次に置き換える:

```kotlin
      serviceRunning = true
      // Read when the ask starts: pausing while it waits does not take it out of the ride.
      val rideId = d.rideId()
      val recording = record(run) ?: return
      val sent = send(recording, rideId, api, run) ?: return
      maybeReturn(ReturnTiming.SENT, settings, run)
      val result = waitForAnswer(sent, recording.name, api, run) ?: return
```

`send` の宣言と `AskBody(...)` を、次に置き換える:

```kotlin
  private suspend fun send(recording: Recording, rideId: String?, api: AskApi, run: Run): SentAsk? {
    val d = deps
    val here = recording.current
    val body = AskBody(
      volumeDb = d.settings().answerVolumeDb,
      audio = recording.audio,
      location = here?.let { Point(it.latitude, it.longitude) },
      headingSample = here?.let { pickHeadingSample(recording.fixes, it) },
      conversationId = d.conversation.current(d.now()),
      rideId = rideId,
    )
```

`send` の最後の `return accepted` を、次に置き換える:

```kotlin
    return SentAsk(accepted.askId, accepted.conversationId, body.conversationId == null, d.now(), here, rideId)
```

`waitForAnswer` の宣言を `private suspend fun waitForAnswer(sent: SentAsk, recordingName: String, api: AskApi, run: Run): AskResult? {` に、`pollUntilDone({ api.getAsk(askId) }, ...` を `pollUntilDone({ api.getAsk(sent.askId) }, ...` に替える。`if (outcome is PollOutcome.Done) outcome.result.transcript?.let { ... }` の行の次に足す:

```kotlin
    // Kept even when the rider has cancelled meanwhile: the Backend has the ask either way.
    when (outcome) {
      is PollOutcome.Done -> d.asks.keep(askRecord(sent, outcome.result, d.now()))
      PollOutcome.Timeout -> d.asks.keep(askRecord(sent, null, d.now()))
      PollOutcome.Cancelled -> Unit
    }
```

同じ関数の次の2行:

```kotlin
    val readable = result.status == "completed" || (result.error == "tts_failed" && !result.answer.isNullOrEmpty())
    if (!readable) {
```

を `    if (!readable(result)) {` に置き換える。

- [ ] **Step 5: Room に残す部品を書く**

`app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt`:

```kotlin
package com.touringproject.v2.store

import com.touringproject.v2.ask.AskLog
import com.touringproject.v2.ask.AskOutcome
import com.touringproject.v2.ask.AskRecord
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

fun AskRecord.toEntity() = AskEntity(
  askId = askId,
  askedAt = askedAt,
  answeredAt = answeredAt,
  transcript = transcript,
  answer = answer,
  latitude = latitude,
  longitude = longitude,
  address = address,
  headingDegrees = headingDegrees,
  input = input,
  conversationId = conversationId,
  newConversation = newConversation,
  status = outcome.name.lowercase(),
  failure = failure,
  rideId = rideId,
)

/** Keeps asks in Room without holding up the ask loop. A failed write is logged and shown, like a ride's (slice 2 spec §8). */
class RoomAskLog(private val dao: AskDao, private val scope: CoroutineScope, private val log: (String, Throwable) -> Unit) : AskLog {
  private val failing = MutableStateFlow(false)
  /** True while the last write of an ask failed. */
  val failed: StateFlow<Boolean> = failing.asStateFlow()

  override fun keep(record: AskRecord) {
    scope.launch { save(record) }
  }

  suspend fun save(record: AskRecord) {
    try {
      dao.upsert(record.toEntity())
      failing.value = false
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      log("ask_store_failed askId=${record.askId}", e)
      failing.value = true
    }
  }
}
```

- [ ] **Step 6: 組み立てる**

`AppGraph.kt` の import に `com.touringproject.v2.ride.RideStatus`・`com.touringproject.v2.store.RoomAskLog` を足す。`val rideStore = RoomRideStore(database.rides())` の次の行に足す:

```kotlin
  val askLog = RoomAskLog(database.asks(), scope) { message, e -> Log.w("trv2.ask", message, e) }
```

`AskDeps` の `recordings = RecordingKeeper(...) { ... },` の次の行に足す:

```kotlin
      asks = askLog,
      rideId = { rides.active.value?.takeIf { it.status == RideStatus.RECORDING }?.id },
```

`AppUi.kt` の `val storeFailed by graph.rides.storeFailed.collectAsStateWithLifecycle()` の次の行に `val askStoreFailed by graph.askLog.failed.collectAsStateWithLifecycle()` を足し、`homeBanner(...)` の `storeFailed = storeFailed,` を `storeFailed = storeFailed || askStoreFailed,` に替える。

- [ ] **Step 7: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AskControllerTest' --tests '*AskRecordTest' --tests '*RoomAskLogTest' > /tmp/trv2-t4.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t4.log`
Expected: `BUILD SUCCESSFUL`（`AskControllerTest` 42件・`AskRecordTest` 2件・`RoomAskLogTest` 2件）

- [ ] **Step 8: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskRecord.kt app/src/main/java/com/touringproject/v2/ask/AskPorts.kt \
  app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt \
  app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
git commit -m "feat: keep each ask that reached the Backend and tie it to the recording ride"
```

---

### Task 5: 何を送るかの判断と、送信の係

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt`・`app/src/main/java/com/touringproject/v2/sync/RideSync.kt`
- Test: `app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt`・`app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt`（どちらも新規）

**Interfaces:**
- Consumes: `RideBody`・`SegmentBody`・`PointBody`・`RouteBody`・`RideApi`・`ApiError`（Task 2）、`Ride`・`RoutePoint`・`RideStatus`・`EndReason`（既存）
- Produces: `ROUTE_CHUNK_POINTS = 300`・`data class ChunkRange(seq, from, until)`・`chunksToSend(sent: Int, total: Int, partialToo: Boolean): List<ChunkRange>`・`metaToSend(updatedAt, sentUpdatedAt?, rejectedUpdatedAt?): Boolean`・`iso(ms): String`・`Ride.toBody(): RideBody`・`RoutePoint.toBody(): PointBody`・`data class Unsent(ride, sentUpdatedAt?, rejectedUpdatedAt?, sentPoints, totalPoints)`・`interface SyncStore { unsent(); points(rideId, from, until); rideSent(rideId, updatedAt); rideRefused(rideId, updatedAt); chunkSent(rideId, chunk, refused) }`・`class RideSync(store, api: () -> RideApi?, log)`（`request()`・`pointAdded()`・`suspend run()`・`suspend pass()`）

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt`:

```kotlin
package com.touringproject.v2.sync

import com.touringproject.v2.api.SegmentBody
import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.HOUR_MS
import com.touringproject.v2.ride.RoutePoint
import com.touringproject.v2.ride.end
import com.touringproject.v2.ride.newRide
import com.touringproject.v2.ride.pause
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SyncPlanTest {
  @Test
  fun while_recording_only_full_chunks_go() {
    assertEquals(emptyList<ChunkRange>(), chunksToSend(0, 0, false))
    assertEquals(emptyList<ChunkRange>(), chunksToSend(0, 299, false))
    assertEquals(listOf(ChunkRange(0, 0, 300), ChunkRange(1, 300, 600)), chunksToSend(0, 650, false))
    assertEquals(listOf(ChunkRange(2, 600, 900)), chunksToSend(600, 900, false))
  }

  @Test
  fun once_paused_or_ended_the_partial_chunk_goes_too() {
    assertEquals(listOf(ChunkRange(0, 0, 300), ChunkRange(1, 300, 350)), chunksToSend(0, 350, true))
  }

  @Test
  fun a_partial_chunk_that_went_goes_again_only_when_it_grows() {
    assertEquals(emptyList<ChunkRange>(), chunksToSend(120, 120, true))
    assertEquals(emptyList<ChunkRange>(), chunksToSend(120, 250, false))
    assertEquals(listOf(ChunkRange(0, 0, 300)), chunksToSend(120, 350, false))
    assertEquals(listOf(ChunkRange(0, 0, 250)), chunksToSend(120, 250, true))
  }

  @Test
  fun the_meta_goes_when_it_changed_unless_this_version_was_refused() {
    assertTrue(metaToSend(1_000, null, null))
    assertFalse(metaToSend(1_000, 1_000, null))
    assertTrue(metaToSend(2_000, 1_000, null))
    assertFalse(metaToSend(2_000, 1_000, 2_000))
    assertTrue(metaToSend(3_000, 1_000, 2_000))
  }

  @Test
  fun a_ride_is_sent_in_utc_with_its_open_segment_as_null_and_only_an_auto_end_as_autoEnded() {
    val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)
    val body = ride.toBody()
    assertEquals("recording", body.status)
    assertEquals(listOf(SegmentBody("1970-01-01T00:00:01Z", null)), body.segments)
    assertEquals("1970-01-01T00:00:01Z", body.updatedAt)
    assertFalse(body.autoEnded)
    assertEquals("paused", ride.pause(2_500).toBody().status)
    assertTrue(ride.end(5_000, EndReason.AUTO, 6_000).toBody().autoEnded)
    assertFalse(ride.end(5_000, EndReason.SHUTDOWN, 6_000).toBody().autoEnded)
    assertEquals("ended", ride.end(5_000, EndReason.SHUTDOWN, 6_000).toBody().status)
  }

  @Test
  fun a_point_keeps_its_segment_and_milliseconds() {
    val body = RoutePoint(2, 1_234, 35.0, 139.0, null).toBody()
    assertEquals("1970-01-01T00:00:01.234Z", body.t)
    assertEquals(2, body.segment)
  }
}
```

`app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt`:

```kotlin
package com.touringproject.v2.sync

import com.touringproject.v2.api.ApiError
import com.touringproject.v2.api.ApiErrorKind
import com.touringproject.v2.api.RideApi
import com.touringproject.v2.api.RideBody
import com.touringproject.v2.api.RouteBody
import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.HOUR_MS
import com.touringproject.v2.ride.Ride
import com.touringproject.v2.ride.RoutePoint
import com.touringproject.v2.ride.end
import com.touringproject.v2.ride.newRide
import com.touringproject.v2.ride.pause
import com.touringproject.v2.ride.resume
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

private const val MAX = 24 * HOUR_MS

/** The device's database as the sync sees it, and a Backend that records what it was sent. */
private class World {
  class Row(var ride: Ride, var sent: Long? = null, var rejected: Long? = null, val chunks: MutableList<Int?> = mutableListOf())
  val rows = linkedMapOf<String, Row>()
  val calls = mutableListOf<String>()
  /** Fails the call whose name (e.g. "route/r1/1") it is given, with the given kind. */
  val fail = mutableMapOf<String, ApiErrorKind>()
  var hasKey = true
  var gate: CompletableDeferred<Unit>? = null
  var passes = 0

  fun add(ride: Ride, points: Int = 0) {
    rows.getOrPut(ride.id) { Row(ride) }.also { it.ride = ride; repeat(points) { _ -> it.chunks += null } }
  }

  val store = object : SyncStore {
    override suspend fun unsent(): List<Unsent> {
      passes += 1
      gate?.await()
      return rows.values
        .filter { metaToSend(it.ride.updatedAt, it.sent, it.rejected) || it.chunks.any { c -> c == null } }
        .map { Unsent(it.ride, it.sent, it.rejected, it.chunks.count { c -> c != null }, it.chunks.size) }
    }
    override suspend fun points(rideId: String, from: Int, until: Int) =
      (from until until).map { RoutePoint(0, it.toLong(), 35.0, 139.0, 5.0) }
    override suspend fun rideSent(rideId: String, updatedAt: Long) { rows.getValue(rideId).sent = updatedAt }
    override suspend fun rideRefused(rideId: String, updatedAt: Long) { rows.getValue(rideId).rejected = updatedAt }
    override suspend fun chunkSent(rideId: String, chunk: ChunkRange, refused: Boolean) {
      val chunks = rows.getValue(rideId).chunks
      for (i in chunk.from until chunk.until) chunks[i] = chunk.seq
      if (refused) calls += "refused:route/$rideId/${chunk.seq}"
    }
  }

  private fun call(name: String) {
    calls += name
    fail[name]?.let { throw ApiError(it) }
  }

  val api = object : RideApi {
    override suspend fun putRide(rideId: String, body: RideBody) = call("ride/$rideId:${body.status}")
    override suspend fun putRoute(rideId: String, seq: Int, body: RouteBody) = call("route/$rideId/$seq:${body.points.size}")
  }

  val sync = RideSync(store, { if (hasKey) api else null }) { _, _ -> }
}

class RideSyncTest {
  private val recording = newRide("r1", "箱根", 1_000, 7, MAX)

  @Test
  fun with_nothing_new_a_pass_makes_no_request() = runTest {
    val w = World()
    w.add(recording, points = 120)
    w.rows.getValue("r1").sent = recording.updatedAt
    w.sync.pass()
    assertEquals(emptyList<String>(), w.calls)
  }

  @Test
  fun a_recording_ride_sends_its_meta_and_its_full_chunks_only() = runTest {
    val w = World()
    w.add(recording, points = 650)
    w.sync.pass()
    assertEquals(listOf("ride/r1:recording", "route/r1/0:300", "route/r1/1:300"), w.calls)
    w.calls.clear()
    w.sync.pass()
    assertEquals(emptyList<String>(), w.calls)
  }

  @Test
  fun a_pause_sends_the_partial_chunk_and_it_goes_again_once_it_is_full() = runTest {
    val w = World()
    val paused = recording.pause(5_000)
    w.add(paused, points = 120)
    w.sync.pass()
    assertEquals(listOf("ride/r1:paused", "route/r1/0:120"), w.calls)
    w.calls.clear()
    w.add(paused.resume(9_000, 7, MAX), points = 230)
    w.sync.pass()
    assertEquals(listOf("ride/r1:recording", "route/r1/0:300"), w.calls)
  }

  @Test
  fun an_ended_ride_sends_all_that_is_left() = runTest {
    val w = World()
    w.add(recording.end(5_000, EndReason.MANUAL, 5_000), points = 350)
    w.sync.pass()
    assertEquals(listOf("ride/r1:ended", "route/r1/0:300", "route/r1/1:50"), w.calls)
  }

  @Test
  fun a_failure_ends_the_pass_and_the_next_one_sends_what_is_left() = runTest {
    val w = World()
    w.add(recording.end(5_000, EndReason.MANUAL, 5_000), points = 350)
    w.add(newRide("r2", "御殿場", 6_000, 7, MAX))
    w.fail["route/r1/0:300"] = ApiErrorKind.NETWORK
    w.sync.pass()
    assertEquals(listOf("ride/r1:ended", "route/r1/0:300"), w.calls)
    w.fail.clear()
    w.calls.clear()
    w.sync.pass()
    assertEquals(listOf("route/r1/0:300", "route/r1/1:50", "ride/r2:recording"), w.calls)
  }

  @Test
  fun a_refused_ride_is_not_sent_again_until_it_changes() = runTest {
    val w = World()
    val paused = recording.pause(5_000)
    w.add(paused)
    w.fail["ride/r1:paused"] = ApiErrorKind.BAD_REQUEST
    w.sync.pass()
    w.calls.clear()
    w.sync.pass()
    assertEquals(emptyList<String>(), w.calls)
    w.fail.clear()
    w.add(paused.resume(9_000, 7, MAX))
    w.sync.pass()
    assertEquals(listOf("ride/r1:recording"), w.calls)
  }

  @Test
  fun a_refused_chunk_is_marked_and_the_next_chunks_still_go() = runTest {
    val w = World()
    w.add(recording.end(5_000, EndReason.MANUAL, 5_000), points = 350)
    w.fail["route/r1/0:300"] = ApiErrorKind.BAD_REQUEST
    w.sync.pass()
    assertEquals(listOf("ride/r1:ended", "route/r1/0:300", "refused:route/r1/0", "route/r1/1:50"), w.calls)
    w.calls.clear()
    w.sync.pass()
    assertEquals(emptyList<String>(), w.calls)
  }

  @Test
  fun without_a_key_nothing_is_read_or_sent() = runTest {
    val w = World()
    w.hasKey = false
    w.add(recording, points = 300)
    w.sync.pass()
    assertEquals(0, w.passes)
    assertEquals(emptyList<String>(), w.calls)
  }

  @Test
  fun triggers_during_a_pass_fold_into_one_more_pass() = runTest {
    val w = World()
    w.gate = CompletableDeferred()
    val job = launch { w.sync.run() }
    w.sync.request()
    runCurrent()
    repeat(3) { w.sync.request() }
    w.gate!!.complete(Unit)
    runCurrent()
    assertEquals(2, w.passes)
    job.cancel()
  }

  @Test
  fun every_300th_point_asks_for_a_pass() = runTest {
    val w = World()
    val job = launch { w.sync.run() }
    repeat(299) { w.sync.pointAdded() }
    runCurrent()
    assertEquals(0, w.passes)
    w.sync.pointAdded()
    runCurrent()
    assertEquals(1, w.passes)
    assertTrue(w.calls.isEmpty())
    job.cancel()
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*SyncPlanTest' --tests '*RideSyncTest' > /tmp/trv2-t5.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t5.log | head`
Expected: コンパイルの失敗（`sync` のパッケージが無い）

- [ ] **Step 3: 判断の関数を書く**

`app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt`:

```kotlin
package com.touringproject.v2.sync

import com.touringproject.v2.api.PointBody
import com.touringproject.v2.api.RideBody
import com.touringproject.v2.api.SegmentBody
import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.Ride
import com.touringproject.v2.ride.RoutePoint
import java.time.Instant

// What is left to send to the Backend, decided without touching it (slice 2 spec §5.3).

/** The most points the Backend takes in one route chunk. */
const val ROUTE_CHUNK_POINTS = 300

/** Route chunk seq holds the ride's points from index from (inclusive) to until (exclusive), in the order they were recorded. */
data class ChunkRange(val seq: Int, val from: Int, val until: Int)

/**
 * The chunks to send now, given that the ride's first sent points have gone (chunks go in order, and a failure stops
 * the rest) and it has total points. While the ride records, only full chunks go. Once it is paused or has ended, the
 * last, partial chunk goes too; when more points fill it later, it goes again under the same seq, which the Backend
 * overwrites.
 */
fun chunksToSend(sent: Int, total: Int, partialToo: Boolean): List<ChunkRange> {
  val chunks = mutableListOf<ChunkRange>()
  var seq = sent / ROUTE_CHUNK_POINTS
  while (true) {
    val from = seq * ROUTE_CHUNK_POINTS
    if (from >= total) break
    val until = minOf(from + ROUTE_CHUNK_POINTS, total)
    if (until <= sent) break
    if (until - from < ROUTE_CHUNK_POINTS && !partialToo) break
    chunks += ChunkRange(seq, from, until)
    seq += 1
  }
  return chunks
}

/** The ride's meta goes when it has changed since the Backend last took it, unless the Backend refused this very version. */
fun metaToSend(updatedAt: Long, sentUpdatedAt: Long?, rejectedUpdatedAt: Long?): Boolean =
  (sentUpdatedAt == null || sentUpdatedAt < updatedAt) && rejectedUpdatedAt != updatedAt

/** ISO 8601 in UTC with its zone ("Z"), as the Backend takes times. */
fun iso(ms: Long): String = Instant.ofEpochMilli(ms).toString()

/** A ride that ended because the device stopped is sent like one the rider ended (slice 2 spec §5.1). */
fun Ride.toBody() = RideBody(
  name = name,
  status = status.name.lowercase(),
  segments = segments.map { SegmentBody(iso(it.startedAt), it.endedAt?.let(::iso)) },
  autoEnded = endReason == EndReason.AUTO,
  updatedAt = iso(updatedAt),
)

fun RoutePoint.toBody() = PointBody(iso(t), lat, lon, accuracy, segment)
```

- [ ] **Step 4: 送信の係を書く**

`app/src/main/java/com/touringproject/v2/sync/RideSync.kt`:

```kotlin
package com.touringproject.v2.sync

import com.touringproject.v2.api.ApiError
import com.touringproject.v2.api.ApiErrorKind
import com.touringproject.v2.api.RideApi
import com.touringproject.v2.api.RouteBody
import com.touringproject.v2.ride.Ride
import com.touringproject.v2.ride.RideStatus
import com.touringproject.v2.ride.RoutePoint
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.Channel

/** A ride that may have something left to send, with what the Backend already has of it. */
data class Unsent(val ride: Ride, val sentUpdatedAt: Long?, val rejectedUpdatedAt: Long?, val sentPoints: Int, val totalPoints: Int)

interface SyncStore {
  /** Rides whose meta has changed since it was sent (and was not refused), or that have points not yet sent. */
  suspend fun unsent(): List<Unsent>
  /** The ride's points from index from to until, in the order they were recorded. */
  suspend fun points(rideId: String, from: Int, until: Int): List<RoutePoint>
  /** The Backend took the ride as of updatedAt. */
  suspend fun rideSent(rideId: String, updatedAt: Long)
  /** The Backend refused the ride as of updatedAt (400); that version is not sent again. */
  suspend fun rideRefused(rideId: String, updatedAt: Long)
  /** The chunk's points have gone; refused when the Backend refused them (400), so they are not sent again either. */
  suspend fun chunkSent(rideId: String, chunk: ChunkRange, refused: Boolean)
}

/**
 * Sends rides and their routes to the Backend (slice 2 spec §5.3). A pass reads what is left to send and sends it; with
 * nothing left it makes no request at all. Passes run one at a time; the ones asked for while a pass runs fold into one
 * more. A failure other than a refusal ends the pass, and the next trigger tries again; there is no timer of its own.
 */
class RideSync(
  private val store: SyncStore,
  /** The client for the current key and user name, or null while there is no key or no API URL. */
  private val api: () -> RideApi?,
  private val log: (event: String, data: Map<String, Any?>) -> Unit,
) {
  private val requests = Channel<Unit>(Channel.CONFLATED)
  private var points = 0

  /** A trigger: the ride changed, the app came to the front, or it started. Safe from any thread. */
  fun request() {
    requests.trySend(Unit)
  }

  /** Asks for a pass every ROUTE_CHUNK_POINTS points recorded in this process (slice 2 spec §5.3). Main thread only. */
  fun pointAdded() {
    points += 1
    if (points % ROUTE_CHUNK_POINTS == 0) request()
  }

  /** Runs the passes, one after another, until cancelled. */
  suspend fun run() {
    for (request in requests) pass()
  }

  suspend fun pass() {
    val client = api() ?: return
    val rides = try {
      store.unsent()
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      log("sync_failed", mapOf("op" to "unsent", "error" to e.toString()))
      return
    }
    for (unsent in rides) {
      if (!send(client, unsent)) return
    }
  }

  // False ends the pass: the network, the key or the database failed, and the next trigger tries again.
  private suspend fun send(client: RideApi, unsent: Unsent): Boolean {
    val ride = unsent.ride
    try {
      if (metaToSend(ride.updatedAt, unsent.sentUpdatedAt, unsent.rejectedUpdatedAt)) {
        if (accepted(ride.id, "ride") { client.putRide(ride.id, ride.toBody()) }) {
          store.rideSent(ride.id, ride.updatedAt)
        } else {
          store.rideRefused(ride.id, ride.updatedAt)
        }
      }
      for (chunk in chunksToSend(unsent.sentPoints, unsent.totalPoints, ride.status != RideStatus.RECORDING)) {
        val points = store.points(ride.id, chunk.from, chunk.until)
        val ok = accepted(ride.id, "route/${chunk.seq}") { client.putRoute(ride.id, chunk.seq, RouteBody(points.map { it.toBody() })) }
        store.chunkSent(ride.id, chunk, refused = !ok)
      }
      return true
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      log("sync_failed", mapOf("ride" to ride.id, "error" to e.toString()))
      return false
    }
  }

  // True when the Backend took it, false when it refused it (400: logged, never sent again). Other failures throw.
  private suspend fun accepted(rideId: String, what: String, put: suspend () -> Unit): Boolean = try {
    put()
    true
  } catch (e: ApiError) {
    if (e.kind != ApiErrorKind.BAD_REQUEST) throw e
    log("sync_refused", mapOf("ride" to rideId, "what" to what, "error" to e.message))
    false
  }
}
```

- [ ] **Step 5: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*SyncPlanTest' --tests '*RideSyncTest' > /tmp/trv2-t5.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t5.log`
Expected: `BUILD SUCCESSFUL`（`SyncPlanTest` 6件・`RideSyncTest` 10件）

- [ ] **Step 6: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/sync app/src/test/java/com/touringproject/v2/sync
git commit -m "feat: decide what is left to send and send it in passes"
```

---

### Task 6: 送信の置き場と契機の配線

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/store/RideDatabase.kt`（`RideDao` に問い合わせを足す）
- Create: `app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt`
- Modify: `app/src/main/java/com/touringproject/v2/ride/RidePorts.kt`・`app/src/main/java/com/touringproject/v2/ride/RideController.kt`・`app/src/main/java/com/touringproject/v2/AppGraph.kt`・`app/src/main/java/com/touringproject/v2/MainActivity.kt`
- Test: `app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt`（新規）・`app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt`

**Interfaces:**
- Consumes: `SyncStore`・`Unsent`・`ChunkRange`・`RideSync`（Task 5）、`ApiClient`（Task 2）、`RideEntity` の印（Task 3）
- Produces: `RideDao.unsentRides()`・`pointCount(rideId)`・`sentPointCount(rideId)`・`pointsFrom(rideId, from, count)`・`markChunk(rideId, seq, from, count)`・`markSent(rideId, updatedAt)`・`markRefused(rideId, updatedAt)`・`markRouteRefused(rideId)`・`class RoomSyncStore(dao: RideDao): SyncStore`・`RideDeps.changed: () -> Unit`（走行の変更を書けたとき）・`RideDeps.pointAdded: () -> Unit`（点を書けたとき）・`AppGraph.sync: RideSync`

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt`:

```kotlin
package com.touringproject.v2.store

import android.app.Application
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.touringproject.v2.api.ApiClient
import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.HOUR_MS
import com.touringproject.v2.ride.RoutePoint
import com.touringproject.v2.ride.end
import com.touringproject.v2.ride.newRide
import com.touringproject.v2.sync.ChunkRange
import com.touringproject.v2.sync.RideSync
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RoomSyncStoreTest {
  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
    .allowMainThreadQueries()
    .build()
  private val dao = db.rides()
  private val rides = RoomRideStore(dao)
  private val store = RoomSyncStore(dao)
  private val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)

  @After
  fun close() = db.close()

  private suspend fun addPoints(count: Int) = repeat(count) {
    rides.addPoint("r1", RoutePoint(0, 2_000L + it, 35.0, 139.0, 5.0), 0.0, 2_000L + it)
  }

  @Test
  fun a_ride_is_unsent_until_its_meta_and_points_have_gone() = runBlocking {
    rides.save(ride)
    addPoints(5)
    assertEquals(listOf(Triple("r1", 0, 5)), store.unsent().map { Triple(it.ride.id, it.sentPoints, it.totalPoints) })
    store.rideSent("r1", ride.updatedAt)
    store.chunkSent("r1", ChunkRange(0, 0, 5), refused = false)
    assertEquals(emptyList<String>(), store.unsent().map { it.ride.id })
    addPoints(1)
    assertEquals(5, store.unsent().single().sentPoints)
  }

  @Test
  fun points_are_read_and_marked_in_the_order_they_were_recorded() = runBlocking {
    rides.save(ride)
    addPoints(7)
    assertEquals(listOf(2_003L, 2_004L), store.points("r1", 3, 5).map { it.t })
    store.chunkSent("r1", ChunkRange(0, 0, 3), refused = false)
    assertEquals(listOf(0, 0, 0, null, null, null, null), dao.points("r1").map { it.chunk })
  }

  @Test
  fun a_refused_version_is_not_unsent_but_a_newer_one_is() = runBlocking {
    rides.save(ride)
    store.rideRefused("r1", ride.updatedAt)
    assertEquals(emptyList<String>(), store.unsent().map { it.ride.id })
    rides.save(ride.end(5_000, EndReason.MANUAL, 5_000))
    assertEquals(listOf("r1"), store.unsent().map { it.ride.id })
  }

  @Test
  fun a_refused_chunk_marks_the_ride() = runBlocking {
    rides.save(ride)
    addPoints(2)
    store.chunkSent("r1", ChunkRange(0, 0, 2), refused = true)
    assertTrue(dao.ride("r1")!!.routeRejected)
  }

  @Test
  fun an_ended_ride_reaches_the_backend_and_the_next_pass_sends_nothing() = runBlocking {
    val server = MockWebServer().apply { start() }
    repeat(3) { server.enqueue(MockResponse().setResponseCode(200).setBody("{}")) }
    val sync = RideSync(store, { ApiClient(server.url("/Prod/").toString(), "key-1", "rider01", OkHttpClient()) }) { _, _ -> }
    rides.save(ride)
    addPoints(350)
    rides.save(ride.end(5_000, EndReason.MANUAL, 5_000))
    sync.pass()
    val paths = (1..3).map { server.takeRequest() }
    assertEquals(listOf("/Prod/rides/r1", "/Prod/rides/r1/route/0", "/Prod/rides/r1/route/1"), paths.map { it.path })
    val last = Json.parseToJsonElement(paths[2].body.readUtf8()).jsonObject["points"]!!.jsonArray
    assertEquals(50, last.size)
    sync.pass()
    assertEquals(3, server.requestCount)
    server.shutdown()
  }
}
```

`RideControllerTest.kt` の `World` の `val autoEnded = mutableListOf<Ride>()` の次の行に足す:

```kotlin
  var changes = 0
  var pointsAdded = 0
```

`RideDeps(...)` の `autoEnded = { autoEnded += it },` の次の行に足す:

```kotlin
      changed = { changes += 1 },
      pointAdded = { pointsAdded += 1 },
```

`class RideControllerTest` の最後に足す:

```kotlin
  @Test
  fun every_saved_change_asks_for_a_send_and_a_failed_one_does_not() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = 5_000
    w.controller.pause()
    w.now = 9_000
    w.controller.resume()
    w.now = 12_000
    w.controller.end("箱根")
    assertEquals(4, w.changes)
    w.failWrites = true
    w.controller.start("御殿場")
    assertEquals(4, w.changes)
  }

  @Test
  fun each_saved_point_is_reported_and_a_dropped_or_failed_one_is_not() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = 6_000
    w.controller.onFix(fix(6_000, 35.0))
    w.controller.onFix(fix(7_000, 35.001, accuracy = 80.0))
    assertEquals(1, w.pointsAdded)
    w.failWrites = true
    w.controller.onFix(fix(8_000, 35.002))
    assertEquals(1, w.pointsAdded)
  }
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RoomSyncStoreTest' --tests '*RideControllerTest' > /tmp/trv2-t6.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t6.log | head`
Expected: コンパイルの失敗（`RoomSyncStore`・`changed`・`pointAdded` が無い）

- [ ] **Step 3: DAO の問い合わせと置き場を書く**

`RideDatabase.kt` の `RideDao` の `suspend fun markAlive(rideId: String, at: Long)` の次に足す:

```kotlin
  // Sending (slice 2 spec §5.3). Points are counted and cut into chunks in the order they were recorded (id).

  @Query(
    "SELECT * FROM rides WHERE ((sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
      "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt)) " +
      "OR id IN (SELECT rideId FROM route_points WHERE chunk IS NULL) ORDER BY updatedAt",
  )
  suspend fun unsentRides(): List<RideEntity>

  @Query("SELECT COUNT(*) FROM route_points WHERE rideId = :rideId")
  suspend fun pointCount(rideId: String): Int

  @Query("SELECT COUNT(*) FROM route_points WHERE rideId = :rideId AND chunk IS NOT NULL")
  suspend fun sentPointCount(rideId: String): Int

  @Query("SELECT * FROM route_points WHERE rideId = :rideId ORDER BY id LIMIT :count OFFSET :from")
  suspend fun pointsFrom(rideId: String, from: Int, count: Int): List<RoutePointEntity>

  @Query(
    "UPDATE route_points SET chunk = :seq WHERE id IN " +
      "(SELECT id FROM route_points WHERE rideId = :rideId ORDER BY id LIMIT :count OFFSET :from)",
  )
  suspend fun markChunk(rideId: String, seq: Int, from: Int, count: Int)

  /** A later save of an older version (none is made today) cannot move the marker back. */
  @Query("UPDATE rides SET sentUpdatedAt = :updatedAt WHERE id = :rideId AND (sentUpdatedAt IS NULL OR sentUpdatedAt < :updatedAt)")
  suspend fun markSent(rideId: String, updatedAt: Long)

  @Query("UPDATE rides SET rejectedUpdatedAt = :updatedAt WHERE id = :rideId")
  suspend fun markRefused(rideId: String, updatedAt: Long)

  @Query("UPDATE rides SET routeRejected = 1 WHERE id = :rideId")
  suspend fun markRouteRefused(rideId: String)
```

`app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt`:

```kotlin
package com.touringproject.v2.store

import com.touringproject.v2.ride.RoutePoint
import com.touringproject.v2.sync.ChunkRange
import com.touringproject.v2.sync.SyncStore
import com.touringproject.v2.sync.Unsent

class RoomSyncStore(private val dao: RideDao) : SyncStore {
  override suspend fun unsent(): List<Unsent> = dao.unsentRides().map {
    Unsent(it.toRide(dao.segments(it.id)), it.sentUpdatedAt, it.rejectedUpdatedAt, dao.sentPointCount(it.id), dao.pointCount(it.id))
  }

  override suspend fun points(rideId: String, from: Int, until: Int): List<RoutePoint> =
    dao.pointsFrom(rideId, from, until - from).map { it.toPoint() }

  override suspend fun rideSent(rideId: String, updatedAt: Long) = dao.markSent(rideId, updatedAt)

  override suspend fun rideRefused(rideId: String, updatedAt: Long) = dao.markRefused(rideId, updatedAt)

  override suspend fun chunkSent(rideId: String, chunk: ChunkRange, refused: Boolean) {
    dao.markChunk(rideId, chunk.seq, chunk.from, chunk.until - chunk.from)
    if (refused) dao.markRouteRefused(rideId)
  }
}
```

- [ ] **Step 4: 司令塔から知らせる**

`RidePorts.kt` の `RideDeps` の `val autoEnded: (Ride) -> Unit,` の次の行に足す:

```kotlin
  /** A change of the ride was saved: something new to send (slice 2 spec §5.3). */
  val changed: () -> Unit,
  /** A route point was saved. */
  val pointAdded: () -> Unit,
```

`RideController.kt` の `write` を、書けたかを返すように置き換える:

```kotlin
  /** False when the write failed (logged and shown). */
  private suspend fun write(op: String, block: suspend () -> Unit): Boolean {
    try {
      block()
      storeFailing.value = unsaved != null
      return true
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      failed(op, e)
      return false
    }
  }
```

`save` の `write("save") { ... }` を、次に置き換える:

```kotlin
    val saved = write("save") {
      deps.store.save(ride)
      unsaved = null
    }
    if (saved) deps.changed()
```

`onFix` の `write("point") { d.store.addPoint(ride.id, point, distance, now) }` を、次に置き換える:

```kotlin
    if (write("point") { d.store.addPoint(ride.id, point, distance, now) }) d.pointAdded()
```

- [ ] **Step 5: 組み立てと契機**

`AppGraph.kt` の import に `com.touringproject.v2.store.RoomSyncStore`・`com.touringproject.v2.sync.RideSync` を足す。`private val notices = RideNotices(context)` の次に足す（`rides` より前に置く）:

```kotlin

  /** Sends rides and routes; a pass runs on each trigger (slice 2 spec §5.3). */
  val sync = RideSync(
    RoomSyncStore(database.rides()),
    api = {
      val key = apiKeys.current()
      val user = settings.settings.value?.userName
      if (apiBaseUrl.isEmpty() || key == null || user == null) null else ApiClient(apiBaseUrl, key, user, http)
    },
    log = { event, data -> Log.i("trv2.sync", "$event $data") },
  )
```

`RideDeps(...)` の `autoEnded = notices::autoEnded,` の次の行に足す:

```kotlin
      changed = sync::request,
      pointAdded = sync::pointAdded,
```

`init` の `scope.launch { rides.load() }` から始まるところを、次に置き換える:

```kotlin
    // Settles a ride left recording or paused before this process started (slice 2 spec §4.5).
    scope.launch { rides.load() }
    scope.launch { sync.run() }
    scope.launch {
      settings.load()
      apiKeys.load()
      loaded = true
      openWhenReady()
      // The start of the app is a trigger; before this the key and the user name are not known.
      sync.request()
    }
```

`MainActivity.kt` の `onStart` を、次に置き換える:

```kotlin
  // A ride's service could not start while the app was in the background (slice 2 spec §4.5); it can now. Coming to
  // the front is also a trigger to send what is left (slice 2 spec §5.3); with nothing left, nothing is sent.
  override fun onStart() {
    super.onStart()
    graph.serviceCoordinator.refresh()
    graph.sync.request()
  }
```

- [ ] **Step 6: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RoomSyncStoreTest' --tests '*RideControllerTest' > /tmp/trv2-t6.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t6.log`
Expected: `BUILD SUCCESSFUL`（`RoomSyncStoreTest` 5件・`RideControllerTest` 27件）

- [ ] **Step 7: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt \
  app/src/main/java/com/touringproject/v2/ride/RidePorts.kt app/src/main/java/com/touringproject/v2/ride/RideController.kt \
  app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/MainActivity.kt \
  app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
git commit -m "feat: send rides on each saved change, every 300 points, at start and when the app comes to the front"
```

---

### Task 7: 位置の監視と1分ごとの書き込みを二重に始めない（#16）

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/service/RecordingWatch.kt`
- Modify: `app/src/main/java/com/touringproject/v2/service/RideForegroundService.kt`
- Test: `app/src/test/java/com/touringproject/v2/service/RecordingWatchTest.kt`（新規）

**Interfaces:**
- Consumes: `RouteSource`・`Subscription`・`Fix`（既存）
- Produces: `class RecordingWatch(source: RouteSource, onFix: (Fix) -> Unit, startHeartbeat: () -> Job, log: (String, Throwable) -> Unit)`（`start()`・`stop()`）

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/service/RecordingWatchTest.kt`:

```kotlin
package com.touringproject.v2.service

import com.touringproject.v2.location.RouteSource
import com.touringproject.v2.location.Subscription
import kotlinx.coroutines.Job
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RecordingWatchTest {
  private var watches = 0
  private var removed = 0
  private var refuse = false
  private val heartbeats = mutableListOf<Job>()
  private val errors = mutableListOf<String>()
  private val source = RouteSource {
    watches += 1
    if (refuse) throw SecurityException("no location permission")
    Subscription { removed += 1 }
  }
  private val watch = RecordingWatch(source, {}, { Job().also { heartbeats += it } }) { message, _ -> errors += message }

  @Test
  fun a_watch_that_cannot_start_is_tried_again_but_the_heartbeat_runs_once() {
    refuse = true
    watch.start()
    watch.start()
    assertEquals(2, watches)
    assertEquals(1, heartbeats.size)
    assertEquals(2, errors.size)
  }

  @Test
  fun starting_again_while_running_starts_nothing_and_stop_ends_both() {
    watch.start()
    watch.start()
    assertEquals(1, watches)
    assertEquals(1, heartbeats.size)
    watch.stop()
    assertEquals(1, removed)
    assertTrue(heartbeats.single().isCancelled)
    watch.start()
    assertEquals(2, heartbeats.size)
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordingWatchTest' > /tmp/trv2-t7.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t7.log | head`
Expected: コンパイルの失敗（`RecordingWatch` が無い）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/service/RecordingWatch.kt`:

```kotlin
package com.touringproject.v2.service

import com.touringproject.v2.location.Fix
import com.touringproject.v2.location.RouteSource
import com.touringproject.v2.location.Subscription
import kotlinx.coroutines.Job

/**
 * What the service runs while a ride records: the route watch and the minute's heartbeat. start() is called again on
 * every change of the service's types and starts only what is not running: a watch that could not start (e.g. the
 * location permission was taken away) is tried again, but the heartbeat never runs twice (Android #16).
 */
class RecordingWatch(
  private val source: RouteSource,
  private val onFix: (Fix) -> Unit,
  private val startHeartbeat: () -> Job,
  private val log: (String, Throwable) -> Unit,
) {
  private var route: Subscription? = null
  private var heartbeat: Job? = null

  fun start() {
    if (route == null) {
      route = runCatching { source.watch(onFix) }.onFailure { log("route watch failed", it) }.getOrNull()
    }
    if (heartbeat == null) heartbeat = startHeartbeat()
  }

  fun stop() {
    route?.remove()
    route = null
    heartbeat?.cancel()
    heartbeat = null
  }
}
```

`RideForegroundService.kt` を次のとおり直す。import の `com.touringproject.v2.location.Subscription` と `kotlinx.coroutines.Job` を消す。

`private var route: Subscription? = null` と `private var heartbeat: Job? = null` の2行を `private lateinit var recording: RecordingWatch` に置き換える。

`onCreate` の `scope = MainScope()` の次に足す:

```kotlin
    val rides = graph.rides
    recording = RecordingWatch(
      graph.routeSource,
      onFix = { fix -> scope.launch { rides.onFix(fix) } },
      startHeartbeat = {
        scope.launch {
          while (true) {
            delay(HEARTBEAT_MS)
            rides.heartbeat()
          }
        }
      },
    ) { message, e -> Log.w("trv2.route", message, e) }
```

`apply` の `if (ServiceUse.LOCATION in uses) watch() else unwatch()` を `if (ServiceUse.LOCATION in uses) recording.start() else recording.stop()` に、`stop()` と `onDestroy()` の `unwatch()` を `recording.stop()` に替える。`private fun watch()` と `private fun unwatch()` を消す。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordingWatchTest' --tests '*RideForegroundServiceTest' > /tmp/trv2-t7.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t7.log`
Expected: `BUILD SUCCESSFUL`（`RecordingWatchTest` 2件・`RideForegroundServiceTest` 9件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/service/RecordingWatch.kt app/src/main/java/com/touringproject/v2/service/RideForegroundService.kt \
  app/src/test/java/com/touringproject/v2/service/RecordingWatchTest.kt
git commit -m "fix: never run the ride heartbeat twice when the route watch cannot start" -m "Fixes #16"
```

---

### Task 8: 全体の確かめ

- [ ] **Step 1: JVM のテストを全部回す**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-full.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-full.log
grep -ho 'tests="[0-9]*"' app/build/test-results/testDebugUnitTest/*.xml | grep -o '[0-9]*' | paste -sd+ - | bc
grep -h 'timestamp=' app/build/test-results/testDebugUnitTest/*.xml | grep -o 'timestamp="[^"]*"' | sort | sed -n '1p;$p'
```

Expected: `BUILD SUCCESSFUL`、299件、時刻がいまの実行のもの

- [ ] **Step 2: ビルドと release の権限**

```bash
cd $AND && ./gradlew assembleDebug assembleRelease > /tmp/trv2-build.log 2>&1; grep -E "BUILD|FAILED" /tmp/trv2-build.log
scripts/check-release-permissions.sh
unzip -l app/build/outputs/apk/release/app-release.apk | grep -c "RideDatabase/"
```

Expected: `BUILD SUCCESSFUL`・`release permissions OK (15)`・`0`（スキーマの JSON は release に入らない）

- [ ] **Step 3: エミュレーターのテスト**

利用者に、テストのあいだエミュレーターに触らないよう頼む。

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
export ANDROID_SERIAL=emulator-5554
cd $AND && ./gradlew connectedDebugAndroidTest > /tmp/trv2-emu.log 2>&1; grep -E "BUILD|FAILED" /tmp/trv2-emu.log
grep -ho 'tests="[0-9]*" failures="[0-9]*" errors="[0-9]*" skipped="[0-9]*"' app/build/outputs/androidTest-results/connected/debug/*.xml
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: `tests="4" failures="0" errors="0" skipped="0"`（記録中の質問のテストは `local.properties` に API の URL があるときだけ走る。無ければ skipped が1になる）

---

### Task 9: 文書

**Files:**
- Modify: Android の `README.md`・`docs-parent/`（写し）
- Modify: 親の `docs/07_units_contracts.md`

- [ ] **Step 1: Android の README を直す**

`$AND/README.md` の「構成」の表で、`.../ask/` の行を置き換える:

```markdown
| `app/src/main/java/com/touringproject/v2/ask/` | 一巡の状態機械（`Flow.kt`）・司令塔（`AskController.kt`）・外との窓口（`AskPorts.kt`）・質問の記録の組み立て（`AskRecord.kt`）・ポーリング・会話・失敗の読み上げ文 |
```

`.../store/` の行を置き換え、その下に1行足す:

```markdown
| `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・送信の置き場（`RoomSyncStore.kt`）。スキーマは `app/schemas/` に版ごとに残す |
| `.../sync/` | 走行とルートの送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`） |
```

「大事な決まり」の Room の行（`- Room のスキーマを変えるときは、...`）を、次に置き換える:

```markdown
- Room のスキーマを変えるときは、版を上げて Migration を書き、`app/schemas/` に書き出された JSON もコミットする。破壊的な作り直しは使わない。スキーマの JSON は debug のビルドの資産にも入る（Robolectric の `MigrationTestHelper` が読むため。release には入らない）。Entity や Migration を変えた直後のテストは `--rerun` で確かめる。
- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと。契機では未送信を調べるだけで、送るものが無ければ通信しない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（`rides.rejectedUpdatedAt`・`rides.routeRejected` に残す）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。
```

ログの行（`adb logcat -s ...`）を、`trv2.sync` を足して置き換える:

```markdown
ログは `adb logcat -s trv2.ask trv2.route trv2.ride trv2.sync trv2.recordings`。
```

- [ ] **Step 2: 契約（07 UC-7）に、かたまりの番号の決め方を足す**

`$ROOT/docs/07_units_contracts.md` の「走行の送り方（スライス2の暫定）」の `- ルートの点は、300点までのかたまりに番号を付けて置く。同じ番号は丸ごと上書きする。かたまりは走行のメタ情報より先に届いてもよい。` の次の行に足す:

```markdown
- かたまりの番号は、Android が走行の点を記録した順に300点ずつ区切った順番（0から）。記録中は満ちたかたまりだけを置き、一時停止と終了では満ちていない最後のかたまりも置く。あとで点が増えたら、同じ番号で置き直す。
```

- [ ] **Step 3: 親の文書をユニットに写す**

```bash
cd $ROOT && scripts/sync-docs.sh Android
cd $AND && git status --short docs-parent/
```

Expected: `docs-parent/07_units_contracts.md` だけが変わっている（`specs/`・`plans/` は写さない）。

- [ ] **Step 4: コミット**

```bash
cd $ROOT && git add docs/07_units_contracts.md
git commit -m "docs: say how route chunks are numbered and when a partial one is sent"
cd $AND && git add README.md docs-parent/07_units_contracts.md
git commit -m "docs: describe sending rides and keeping asks"
```

---

### Task 10: 利用者の実機の確認

AI はこの Task を自分で通さない。走行用のビルドを入れ、利用者に手順を渡し、終わったら DynamoDB を読んで確かめる。

- [ ] **Step 1: 走行用のビルドを入れる（AI が行う。実機を USB で繋いでもらう）**

実機には版1の DB を持つビルド（Android `46eea83`）が入っている。このビルドを入れて最初に開いたとき、版2への Migration が走る。

```bash
unset ANDROID_SERIAL
cd $AND && ./gradlew assembleRelease > /tmp/trv2-rel.log 2>&1; tail -1 /tmp/trv2-rel.log
scripts/check-release-permissions.sh
adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
```

Expected: `Success`。走行のログを後から読みたいときは、走る前に `adb logcat -G 16M` で置き場を広げる（端末の設定を変えるので、利用者に確かめてから）。

- [ ] **Step 2: 利用者に確かめてもらう**

| # | 操作 | 期待 |
|---|---|---|
| 1 | アプリを開く | いつものホームが出る（版2への移行で落ちない）。plan 4 まで一覧は無いので、落ちないことだけ見る。plan 1 の確かめで記録した走行は、このとき初めて送られる |
| 2 | 走行を開始し、ナビを前面に出して画面を消し、30分ほど走る（300点を超えるよう、25分以上） | 記録が続く |
| 3 | 記録中に、インカムのボタンで1回質問する | いつもどおり回答が聞こえる |
| 4 | 止まって「⏸ 一時停止」→ 一時停止中に1回質問する → 「▶ 再開」 | どちらの質問も回答が聞こえる |
| 5 | 少し走ってから「■ 終了」→「終了して保存」 | ホームに戻る |
| 6 | 終えたら、AI にユーザー名を伝える（チャットに書いてよいか迷うなら、設定の画面で見せるだけでもよい） | — |

- [ ] **Step 3: DynamoDB を読んで確かめる（AI が行う）**

ユーザー名を `U` に入れて、走行とかたまりと質問を読む（値は表示するが、文書やコミットには書かない）。

```bash
U=<利用者のユーザー名>
T=dynamodb-trv2-dev-records
AWS_PROFILE=touring aws dynamodb query --region ap-northeast-1 --table-name $T \
  --key-condition-expression "pk = :p AND begins_with(sk, :s)" \
  --expression-attribute-values "{\":p\":{\"S\":\"USER#$U\"},\":s\":{\"S\":\"RIDE#\"}}" \
  --query "Items[].{sk: sk.S, status: status.S, name: name.S, autoEnded: autoEnded.BOOL, points: length(points.L)}" --output table
AWS_PROFILE=touring aws dynamodb query --region ap-northeast-1 --table-name $T \
  --key-condition-expression "pk = :p AND begins_with(sk, :s)" \
  --expression-attribute-values "{\":p\":{\"S\":\"USER#$U\"},\":s\":{\"S\":\"ASK#\"}}" \
  --query "sort_by(Items, &timings.M.receivedAt.S)[-4:].{sk: sk.S, rideId: rideId.S, receivedAt: timings.M.receivedAt.S}" --output table
```

Expected（plan 1 の確かめで記録した走行も並ぶ。それらも `status` が `ended` で、かたまりがある）:
- いま走った走行の記録（`status` が `ended`、`autoEnded` が false、名前が入れたもの）と、その走行の `#ROUTE#00000` から続くかたまり。最後のかたまり以外は300点。かたまりの点の合計が、走った時間に見合う（5秒ごと・10m ごとなので、30分で300〜360点ほど）
- 最近の質問のうち、記録中にした質問には `rideId` があり、その走行の `rideId` と同じ。一時停止中にした質問には `rideId` が無い

- [ ] **Step 4: 結果を記録する**

✗ があれば `superpowers:systematic-debugging` で原因を探す。✓ になったら、PROJECT.md の区切り点の作業に進む（かたまりの数と点の数を、持ち越しの「電池・点の抜け」の材料として PROJECT.md に1行残す）。
