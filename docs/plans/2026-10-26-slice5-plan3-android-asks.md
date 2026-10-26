# スライス5 計画3: Android（質問と録音） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 進行方位を Android が走行のルートから求めて度数で送り（止まっているあいだも保つ）、ホームから文字で質問でき、SC-11 で録音の上限と開始の合図を変えられるようにする。あわせて Android #7〜#11・#30・#48・#68 を直す。

**Architecture:** 方位の決まりは純粋な関数 `findHeading`（`location/Heading.kt`）にし、`RouteHeading`（`ride/`）が記録中か一時停止中の走行の最後の区間の点を Room から読んで、この関数に渡す。質問・質問できなかった地点・地点メモは、どれも `RouteHeading` を通る。文字の質問は質問の司令塔（`AskController.askText`）が送信から始め、結果を `TextAskOutcome` でホームのシートに返す。SC-11 の値と方位のパラメーターは `Settings`（DataStore の JSON）に足し、質問の始まりに読む。Room は版6のまま。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版6のまま。問い合わせを1つ足すだけ）・Robolectric 4.16（SDK 35）・OkHttp・kotlinx.serialization。足す依存は無い。

**Spec:** [docs/specs/2026-10-25-slice5-design.md](../specs/2026-10-25-slice5-design.md)（§4.1〜§4.4・§5・§6・§9・§10・§11）。決定の記録は [adr/0013](../../adr/0013-heading-on-android-held-while-stopped.md)。`headingDegrees` の受け口は plan 1 でデプロイ済み（`docs/07a_openapi.yaml`）。

**範囲に入れた issue（Android）:** #7（試し録りを始めた直後に SC-12 を離れると、試し録りが画面の外で動きうる）・#8（音量の警告を閉じたあと、音量を変えて戻すと帯が出ない）・#9（直前の音量が画面の切り替えと続けての質問で引き継がれない）・#10（録音をすべて消すのに失敗しても知らせない）・#11（録音をすべて消す確認中に質問が始まると「消す」が何もしない）・#30（質問の保存のコメント）・#48（ホームの受け付けの判断が二重）・#68（録音の保存を POST の後にした）。

**前提:** Android の `main`（`1944160`。版 0.10.0・JVM のテスト605件）の上に作る。Backend は plan 1（`headingDegrees` を受ける）、Agent は plan 2 がデプロイ済み。

**計画を書くときに決めたこと（spec からの具体化）:**

- **Room は版6のまま（利用者と決めた、2026-10-26）。** spec §5.4 は「版7で質問に `inputType` を足す」としているが、`asks` にはすでに `input` 列（`voice`・`text`）があり、引き継ぎの読み込みは `GET /records` の `inputType` をそこへ写し（`text` 以外は `voice`）、SC-07 は「🎤 声で質問／⌨ 文字で質問」を出している。文字の質問は `input = text` で残す。方位も、`asks`（質問できなかった地点）と `notes` の `headingDegrees` 列に端末の値を入れて送る（Backend の答えで上書きされる）。
- **方位のパラメーター（利用者と決めた、2026-10-26）:** `Settings` に `headingReferenceMeters`（10・15・20・30、既定15）・`headingAccuracyMeters`（10・20・30・50、既定20）・`headingHoldMinutes`（2・5・10・30、既定10）を足し、計算はそこから読む。選べる値の外は既定に戻す。変える画面（SC-22）は plan 4。
- **方位の求め方:** `findHeading(route, here, now, params)` が spec §4.2 の決まりを持つ。今の位置より後の点（録音を終えたあとに足された点）は使わない（そこからの向きは後ろ向きになるため）。保つ上限は `now`（質問は録音を終えた時刻、文字の質問は送る時刻、地点メモは開いた時刻）から測る。結果は `HeadingResult`（`Found(degrees, reference, meters)` か `None(reason)`。理由は `NO_POSITION`・`POOR_ACCURACY`・`NOT_MOVED`・`HELD_TOO_LONG`）で、plan 4 の SC-22 がそのまま使う。
- **方位の材料の出どころ:** `RouteHeading.find(here, now)` が、記録中か一時停止中の走行（`RideController.active`）の最後の区間の点を、Room の `segmentTail` で新しいほうから120点読む（点は10m 以上離れて足されるので、30m 先の基準には数点で足りる。残りは止まっているあいだの揺れのため）。走行が無いとき・読めないときは点が無いもの（`NOT_MOVED`）とする。`RideController` の手元には最後の1点しか無いので、DB を読む。
- **今の位置（利用者と決めた、2026-10-26）:** 声の質問は今のまま録音を終えたときの位置（`Positions.end()`。録音のあいだの位置は今の位置を決めるのにだけ使う）。文字の質問は送るときの端末の最後の位置（`Positions.latest()`。Fused の `lastLocation` を最大2秒待ち、30秒より古ければ無し。記録中は走行のルートが5秒ごとに位置を求めているので新しい）。地点メモは今のまま、開いたときの走行の最新の点。
- **送る形:** 新しく作る質問・質問できなかった地点・地点メモは `headingDegrees` だけを送り、`headingSample` を送らない。版を上げる前に作った未送信の地点メモと質問できなかった地点は、行に残る `sample*` の列から今までどおり `headingSample` も送る（Backend は `headingDegrees` を先に使う）。列は残し、`AskRecord.sample`・`pickHeadingSample`・`NoteDraft` の材料の項目は消す。方位なし（null）は JSON から省く（Backend は無いものとして扱う）。
- **SC-11:** `Settings` に `recordLimitSeconds`（10〜60の5秒刻み、既定20）と `startCueMs`（0・500・1000・1500・2000・3000、既定1500。0 は「なし」）を足す。質問は始めるときに読み、SC-03 の残り秒数もその値から数える（`FlowState.recordLimitMs`）。開始の合図は `Cues.start(durationMs)` で、0 なら鳴らさない。試し録りも同じ値を使う。SC-19 の声の入力は今のまま（60秒・1.5秒）。設定の一覧の行は「応答後に戻るアプリ」と「回答の音量」のあいだ（モックで「録音の設定」が並ぶ位置。spec §14）。画面はモックのとおり上限の −・＋、合図の6つの選択、「既定値に戻す」（2項目だけを戻し、トースト「既定値に戻しました」）。
- **文字の質問（シートの扱いは利用者と決めた、2026-10-26）:** ホームの上の行に「🎤 押して話す」「⌨ 文字で質問」の順（モックの順）。シートは `TextAskSheet`（500字まで・残りの字数・空白だけは押せない）。「質問する」で `AskController.askText` を呼び、SC-03 の「送っています…」（`FlowEvent.StartText` で SENDING から）に進む。結果は `TextAskOutcome`:
  - `SENT`（Backend が受け付けた）: シートを閉じて文を消す。あとは回答待ち・読み上げ（声の質問と同じ。ナビへは戻らない）。
  - `OFFLINE`（送る前に通信が無い・`POST` が通信の失敗）: 質問できなかった地点を作らず、SC-03 も失敗を出さない。シートに「通信できません」と文が残る。
  - `NOT_TAKEN`（記録中でない・接続キーが無いか誤り・Backend の 400・前面サービスを始められない・送る前に取り消した）: SC-03 に理由を出し（400 は「うまく答えられませんでした」）、シートに文が残る。
  - シートの状態（`TextSheet`）は `AppUi` が持ち、SC-03 のあいだシートを消して、終わると戻す（シートは一番上の窓に出るので、SC-03 を隠さないため）。送っているあいだは「質問する」を押せない（二重に送らない）。
  - 質問の行は `input = text`、質問の文（`transcript`）は打った文（Backend が返す文が無いときも）。前面サービスは声の質問と同じに始める。
- **#48:** 受け付けるかどうかは `refusal(RideNow)` だけが決め、司令塔とホームの文言（`askHint(RideNow)`）の両方が使う。
- **#68:** 録音は `POST` の前に SC-12 へ残し、通信の失敗で質問できなかった地点になったら `RecordingSink.discarded` で消す（保存と削除は同じ scope で順に投げ、置き場の鍵が順に取る）。
- **#8・#9:** 音量は `MediaVolumeWatch` がプロセスのあいだ持つ（直前の良い値・閉じた音量）。違う音量が読めたら閉じた音量を忘れる。読めない（null）ときは変わったとみなさない。
- **#10・#11:** `RecordingStore.deleteAll` は消せなかったら例外を投げ、SC-12 が「消せませんでした」を出す。質問が始まったら DL-01 を閉じる。
- **#7:** 試し録りは `CoroutineStart.UNDISPATCHED` で始める（ボタンの呼び出しの中で録音中になり、直後の `leave()` が取り消せる）。
- 版を 0.11.0（`versionCode` 12）に上げる。

この計画のコードは、使い捨てのフォルダで、次を確かめてから書いた。

- タスクの順に一つずつコミットし、各コミットで `clean` から JVM のテストが通る（605件 → 655件）。各タスクのテストだけを1つ前のコミットに当てると落ちる（まだ無い名前を使うのでコンパイルで落ちるか、期待が外れて落ちる）。
- 最後に、JVM のテスト655件・`assembleDebug`・`assembleRelease`・`scripts/check-release-permissions.sh` が通り、エミュレーターのテストのコードがコンパイルできる。
- plan の差分を新しい写しへ機械的に当てると、最終形と一致する。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice5-plan3` を切る（Task 0）。親は `slice5-plan3`。push・マージはしない（利用者が明示したときだけ）。push の前に `pre-push-secret-scan`。
- 作りの決まり: 判断の芯（`findHeading`・`refusal`・`TextSheet.after`・文字数の決まり）は Android に依存させない。部品は `AppGraph` で手で組む。走行を変えるのは `RideController` だけ（方位は読むだけ）。
- Room は版6のまま（表を変えない）。破壊的な作り直しは使わない。
- ホームは全体がスクロールしない。
- 方位のパラメーターと SC-11 の値は端末の設定（DataStore）に置く。SSM には置かない（spec §4.3）。
- 新しく作る記録には `headingSample` を送らない（spec §4.4）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない（テストの作り物の名前 `rider01` などは除く）。端末のログ（`adb logcat`）には API の URL が出るので、書き写さない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*クラス名'`。Gradle のビルドキャッシュはフォルダをまたいで共有されるので、テストを確かめるときは `--rerun` を付ける。Kotlin の差分コンパイルは interface の変更を見逃すことがあるので、Task 14 は `./gradlew clean` から回す。
- interface にメソッドを足したら、作り物にも足す（`Positions.latest`・`RecordingSink.discarded`・`Cues.start(durationMs)` は、各タスクの差分の中で `AskControllerTest` の作り物に入っている）。
- Robolectric の決まり（SDK 35・画面の外の行は `performScrollTo` で出す・地図の部品は動かさない）。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。使い終わったら止める。1回目に APK を入れる途中で「device offline」で止まったら、起動し直して回す。
- `RideForegroundServiceTest` の1件がまれに落ちる（Android #59）。落ちたら単独で回し直し、全体をもう一度回す。
- この Mac はディスクの空きが少ない。Gradle のキャッシュは使うたびに増える。
- AWS は `AWS_PROFILE=touring`・リージョン `ap-northeast-1`（Task 15 で DynamoDB を読むだけ）。

## Review Focus

- 信号待ちで2分止まってから質問する（止まっているあいだルートの点は増えない） → 止まる直前に走ってきた向きが出る。Task 1 の `a_stop_of_two_minutes_keeps_the_heading_it_came_in_with`・Task 3 の `a_paused_ride_takes_the_segment_before_the_pause`。
- フェリーで離れた場所から再開した直後に質問する → 一時停止の前の区間の点は使わず、方位なし。走り出すと新しい向き。Task 3 の `the_heading_comes_from_the_last_segment_only`。
- 文字の質問の「質問する」を続けて2度押す → 送るのは1回。Task 9 の `the_sheet_says_it_cannot_reach_the_network_and_waits_while_sending`（送っているあいだ押せない）・Task 8 の `nothing_starts_while_an_ask_runs`。
- 文字の質問を送った瞬間にトンネルに入る（`POST` が通信の失敗に終わる） → 質問できなかった地点を作らず、シートに「通信できません」と文が残る。Task 8 の `a_network_failure_on_send_keeps_nothing_and_tells_the_sheet`・Task 9 の `what_became_of_the_text_decides_the_sheet`。
- 0.10.0 で通信できずに残した地点メモ・質問できなかった地点が、0.11.0 を入れたあとで送られる → 古い材料（`headingSample`）で送られ、Backend が方位を付ける。Task 3 の `an_unreached_ask_kept_before_slice_5_still_goes_with_its_sample`・`an_unreached_ask_goes_with_its_heading_and_an_old_one_with_its_sample`、Task 4 の `a_point_memo_goes_with_its_place_and_sample_in_utc`。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `location/Heading.kt` | 方位の決まり `findHeading`・`bearingDegrees`・`HeadingParams`・`HeadingResult`（1）、古い選び方を消す（4） | 1・4 |
| `settings/Settings.kt` | 方位のパラメーターと SC-11 の値（2）、`DEFAULT_RECORD_LIMIT_MS`（5）、`withRecordingDefaults`（6） | 2・5・6 |
| `ride/RouteHeading.kt`・`store/RideDatabase.kt` | 走行の最後の区間の点から方位を求める係・`segmentTail` | 3 |
| `location/PositionTracker.kt`・`ask/AskPorts.kt` | 今の位置（`end(): Fix?`・`latest()`）・`AskDeps.heading`（3）、`Cues.start(durationMs)`（5）、`refusal`（7）、`latest`（8）、`RecordingSink.discarded`（10） | 3・5・7・8・10 |
| `ask/AskController.kt`・`ask/AskRecord.kt`・`ask/Flow.kt` | 方位を送る（3）、SC-11 の値（5）、`refusal`（7）、文字の質問・#30（8）、#68（10） | 3・5・7・8・10 |
| `ask/TextAsk.kt` | 文字の質問の字数の決まりと `TextAskOutcome` | 8 |
| `api/ApiClient.kt`・`sync/SyncPlan.kt`・`sync/RideSync.kt`・`store/RoomSyncStore.kt`・`store/RoomAskLog.kt`・`store/RoomRecords.kt` | `headingDegrees` を送る形 | 3・4 |
| `records/Notes.kt`・`store/RoomNotes.kt` | 地点メモの方位 | 4 |
| `audio/ToneCues.kt`・`recordings/Trial.kt`・`recordings/RecordingCheck.kt`・`ui/AskOverlay.kt` | 合図の長さ・試し録りの値・#7・残り秒数 | 5 |
| `ui/SettingsScreens.kt`・`ui/Labels.kt`・`ui/AppUi.kt` | SC-11 と設定の行 | 6 |
| `ui/RideLabels.kt` | `askHint(RideNow)` | 7 |
| `ui/TextAskSheet.kt`・`ui/HomeScreen.kt`・`ui/AppUi.kt` | 文字の質問のシートとホームの入口 | 9 |
| `recordings/RecordingStore.kt` | `delete`（10）、`deleteAll` の失敗（12） | 10・12 |
| `audio/MediaVolumeWatch.kt`・`ui/HomeScreen.kt`・`ui/AppUi.kt`・`AppGraph.kt` | 音量（#8・#9） | 11 |
| `ui/RecordingsScreen.kt` | #11 | 12 |
| `AppGraph.kt` | `routeHeading`（3）、地点メモへの方位（4）、試し録りと声の入力の合図（5）、`mediaVolume`（11） | 3・4・5・11 |
| `app/build.gradle.kts`・`README.md` | 版と説明 | 13 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、今のテストを回す**

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice5-plan3
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t0.log 2>&1; tail -1 /tmp/trv2-t0.log
```

Expected: `BUILD SUCCESSFUL`（605件）。親はこの plan を書いたブランチ `slice5-plan3` のまま。

---

### Task 1: 方位の決まり

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/location/Heading.kt`
- Test: `app/src/test/java/com/touringproject/v2/location/FindHeadingTest.kt`（新規）

**Interfaces:**
- Produces: `const val DEFAULT_HEADING_REFERENCE_M = 15`・`DEFAULT_HEADING_ACCURACY_M = 20`・`DEFAULT_HEADING_HOLD_MINUTES = 10`。`data class HeadingParams(referenceMeters: Int, accuracyMeters: Int, holdMinutes: Int)`（既定値つき）。`enum class NoHeading { NO_POSITION, POOR_ACCURACY, NOT_MOVED, HELD_TOO_LONG }`。`sealed interface HeadingResult { Found(degrees: Double, reference: Fix, meters: Double); None(reason: NoHeading) }`・`val HeadingResult.degrees: Double?`。`fun bearingDegrees(from: Fix, to: Fix): Double`（0以上360未満）。`fun findHeading(route: List<Fix>, here: Fix?, now: Long, params: HeadingParams): HeadingResult`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/location/FindHeadingTest.kt b/app/src/test/java/com/touringproject/v2/location/FindHeadingTest.kt
new file mode 100644
index 0000000..2569829
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/location/FindHeadingTest.kt
@@ -0,0 +1,114 @@
+package com.touringproject.v2.location
+
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertTrue
+import org.junit.Test
+import kotlin.math.cos
+
+// Slice 5 spec §4.2 and its table of scenes. Points are laid out in metres north and east of one place.
+private const val LAT = 35.0
+private const val LON = 139.0
+private const val M_PER_DEG = 111_195.0
+
+private fun at(north: Double, east: Double, seconds: Long, accuracy: Double? = 5.0) =
+  Fix(LAT + north / M_PER_DEG, LON + east / (M_PER_DEG * cos(Math.toRadians(LAT))), seconds * 1_000, accuracy)
+
+private val DEFAULTS = HeadingParams()
+
+private fun found(result: HeadingResult): HeadingResult.Found {
+  assertTrue("expected a heading, got $result", result is HeadingResult.Found)
+  return result as HeadingResult.Found
+}
+
+class FindHeadingTest {
+  @Test
+  fun bearings_run_clockwise_from_north_and_never_reach_360() {
+    val o = at(0.0, 0.0, 0)
+    assertEquals(0.0, bearingDegrees(o, at(100.0, 0.0, 0)), 0.1)
+    assertEquals(90.0, bearingDegrees(o, at(0.0, 100.0, 0)), 0.1)
+    assertEquals(180.0, bearingDegrees(o, at(-100.0, 0.0, 0)), 0.1)
+    assertEquals(270.0, bearingDegrees(o, at(0.0, -100.0, 0)), 0.1)
+    val nearlyNorth = bearingDegrees(o, at(100.0, -1e-9, 0))
+    assertTrue(nearlyNorth >= 0.0 && nearlyNorth < 360.0)
+  }
+
+  // Riding north, a point every 5 s and 10 m: the reference is the newest point 15 m behind.
+  @Test
+  fun riding_takes_the_heading_from_a_few_seconds_back() {
+    val route = (0..5).map { at(it * 10.0, 0.0, it * 5L) }
+    val here = at(56.0, 0.0, 27)
+    val heading = found(findHeading(route, here, 27_000, DEFAULTS))
+    assertEquals(0.0, heading.degrees, 0.5)
+    assertEquals(route[4], heading.reference)
+  }
+
+  @Test
+  fun after_a_turn_the_heading_follows_the_new_road_once_it_has_gone_far_enough() {
+    // North to the corner, then east.
+    val north = (0..4).map { at(-40.0 + it * 10.0, 0.0, it * 5L) }
+    val justTurned = found(findHeading(north, at(0.0, 10.0, 22), 22_000, DEFAULTS))
+    assertTrue("between the two roads: ${justTurned.degrees}", justTurned.degrees > 0.0 && justTurned.degrees < 90.0)
+    val east = north + at(0.0, 10.0, 25)
+    val turned = found(findHeading(east, at(0.0, 20.0, 27), 27_000, DEFAULTS))
+    assertEquals(90.0, turned.degrees, 0.5)
+  }
+
+  // A red light: no point is added while the bike stands, so the points it came along still give the heading.
+  @Test
+  fun a_stop_of_two_minutes_keeps_the_heading_it_came_in_with() {
+    val route = (0..4).map { at(-40.0 + it * 10.0, 0.0, it * 5L) }
+    val here = at(0.5, 0.3, 140, accuracy = 8.0)
+    assertEquals(0.0, found(findHeading(route, here, 140_000, DEFAULTS)).degrees, 2.0)
+  }
+
+  @Test
+  fun a_stop_longer_than_the_hold_has_no_heading() {
+    val route = (0..4).map { at(-40.0 + it * 10.0, 0.0, it * 5L) }
+    val here = at(0.0, 0.0, 20 + 10 * 60 + 1)
+    assertEquals(HeadingResult.None(NoHeading.HELD_TOO_LONG), findHeading(route, here, here.timestamp, DEFAULTS))
+  }
+
+  @Test
+  fun a_reference_point_that_is_not_accurate_enough_is_passed_over() {
+    val route = listOf(at(-30.0, 0.0, 0), at(-20.0, 0.0, 5, accuracy = 25.0))
+    val heading = found(findHeading(route, at(0.0, 0.0, 10), 10_000, DEFAULTS))
+    assertEquals(route[0], heading.reference)
+    val unknown = listOf(at(-20.0, 0.0, 5, accuracy = null))
+    assertEquals(unknown[0], found(findHeading(unknown, at(0.0, 0.0, 10), 10_000, DEFAULTS)).reference)
+  }
+
+  @Test
+  fun without_a_good_position_here_there_is_no_heading() {
+    val route = listOf(at(-30.0, 0.0, 0))
+    assertEquals(HeadingResult.None(NoHeading.NO_POSITION), findHeading(route, null, 10_000, DEFAULTS))
+    assertEquals(HeadingResult.None(NoHeading.POOR_ACCURACY), findHeading(route, at(0.0, 0.0, 10, accuracy = 21.0), 10_000, DEFAULTS))
+    assertEquals(0.0, found(findHeading(route, at(0.0, 0.0, 10, accuracy = null), 10_000, DEFAULTS)).degrees, 0.5)
+  }
+
+  @Test
+  fun a_segment_that_has_not_gone_the_reference_distance_has_no_heading() {
+    val route = listOf(at(0.0, 0.0, 0), at(10.0, 0.0, 5))
+    assertEquals(HeadingResult.None(NoHeading.NOT_MOVED), findHeading(route, at(12.0, 0.0, 6), 6_000, DEFAULTS))
+    assertEquals(HeadingResult.None(NoHeading.NOT_MOVED), findHeading(emptyList(), at(12.0, 0.0, 6), 6_000, DEFAULTS))
+  }
+
+  // A route point taken after here lies ahead of it; a heading from it would point backwards.
+  @Test
+  fun points_after_here_are_not_used() {
+    val route = listOf(at(-30.0, 0.0, 0), at(30.0, 0.0, 20))
+    assertEquals(0.0, found(findHeading(route, at(0.0, 0.0, 10), 10_000, DEFAULTS)).degrees, 0.5)
+  }
+
+  @Test
+  fun the_parameters_change_the_next_heading() {
+    val route = listOf(at(-40.0, 10.0, 0), at(-20.0, 0.0, 5))
+    val here = at(0.0, 0.0, 10)
+    assertEquals(route[1], found(findHeading(route, here, 10_000, DEFAULTS)).reference)
+    assertEquals(route[0], found(findHeading(route, here, 10_000, HeadingParams(referenceMeters = 30))).reference)
+    assertEquals(
+      HeadingResult.None(NoHeading.POOR_ACCURACY),
+      findHeading(route, here.copy(accuracy = 12.0), 10_000, HeadingParams(accuracyMeters = 10)),
+    )
+    assertEquals(HeadingResult.None(NoHeading.HELD_TOO_LONG), findHeading(route, here, 5_000 + 2 * 60_000 + 1, HeadingParams(holdMinutes = 2)))
+  }
+}
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*FindHeadingTest'`
Expected: コンパイルで落ちる（`findHeading`・`HeadingParams` などが無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/location/Heading.kt b/app/src/main/java/com/touringproject/v2/location/Heading.kt
index cda07be..adcfd76 100644
--- a/app/src/main/java/com/touringproject/v2/location/Heading.kt
+++ b/app/src/main/java/com/touringproject/v2/location/Heading.kt
@@ -3,16 +3,70 @@ package com.touringproject.v2.location
 import com.touringproject.v2.api.HeadingSample
 import java.time.Instant
 import kotlin.math.asin
+import kotlin.math.atan2
 import kotlin.math.cos
 import kotlin.math.pow
 import kotlin.math.sin
 import kotlin.math.sqrt
 
-// Picks the older point the Backend uses to work out the direction of travel (07 UC-5).
+// The direction of travel, worked out on the device from the ride's route (slice 5 spec §4, adr/0013).
 
 /** accuracy is the radius in metres the device reports (null when unknown). */
 data class Fix(val latitude: Double, val longitude: Double, val timestamp: Long, val accuracy: Double?)
 
+// Slice 5 spec §4.3: the rider changes these (SC-22); the defaults hold the heading through a long red light.
+const val DEFAULT_HEADING_REFERENCE_M = 15
+const val DEFAULT_HEADING_ACCURACY_M = 20
+const val DEFAULT_HEADING_HOLD_MINUTES = 10
+
+/**
+ * referenceMeters: how far the point the heading is taken from must be from here. accuracyMeters: the worst accuracy
+ * of that point and of here. holdMinutes: how old that point may be, so a heading held at a stop runs out.
+ */
+data class HeadingParams(
+  val referenceMeters: Int = DEFAULT_HEADING_REFERENCE_M,
+  val accuracyMeters: Int = DEFAULT_HEADING_ACCURACY_M,
+  val holdMinutes: Int = DEFAULT_HEADING_HOLD_MINUTES,
+)
+
+/** Why there is no heading (SC-22 tells the rider). */
+enum class NoHeading { NO_POSITION, POOR_ACCURACY, NOT_MOVED, HELD_TOO_LONG }
+
+sealed interface HeadingResult {
+  /** reference is the route point the heading is taken from, meters its distance from here. */
+  data class Found(val degrees: Double, val reference: Fix, val meters: Double) : HeadingResult
+  data class None(val reason: NoHeading) : HeadingResult
+}
+
+val HeadingResult.degrees: Double? get() = (this as? HeadingResult.Found)?.degrees
+
+/** Degrees clockwise from true north, 0 or more and less than 360. */
+fun bearingDegrees(from: Fix, to: Fix): Double {
+  fun rad(d: Double) = Math.toRadians(d)
+  val dLon = rad(to.longitude - from.longitude)
+  val y = sin(dLon) * cos(rad(to.latitude))
+  val x = cos(rad(from.latitude)) * sin(rad(to.latitude)) - sin(rad(from.latitude)) * cos(rad(to.latitude)) * cos(dLon)
+  return (Math.toDegrees(atan2(y, x)) % 360 + 360) % 360
+}
+
+/**
+ * Slice 5 spec §4.2. route is the points of the ride's last segment, in any order. Going back from the newest point
+ * not after here, the first one accurate enough and far enough from here is the reference; the heading runs from it to
+ * here. A reference older than the hold (measured at now) gives none, as does no or a poor position here.
+ */
+fun findHeading(route: List<Fix>, here: Fix?, now: Long, params: HeadingParams): HeadingResult {
+  if (here == null) return HeadingResult.None(NoHeading.NO_POSITION)
+  val accuracy = params.accuracyMeters.toDouble()
+  if (here.accuracy != null && here.accuracy > accuracy) return HeadingResult.None(NoHeading.POOR_ACCURACY)
+  val reference = route
+    .filter { it.timestamp <= here.timestamp }
+    .sortedByDescending { it.timestamp }
+    .firstOrNull { (it.accuracy == null || it.accuracy <= accuracy) && distanceMeters(it, here) >= params.referenceMeters }
+    ?: return HeadingResult.None(NoHeading.NOT_MOVED)
+  if (now - reference.timestamp > params.holdMinutes * 60_000L) return HeadingResult.None(NoHeading.HELD_TOO_LONG)
+  return HeadingResult.Found(bearingDegrees(reference, here), reference, distanceMeters(reference, here))
+}
+
 const val MIN_SAMPLE_DISTANCE_M = 15.0
 const val MAX_SAMPLE_AGE_MS = 60_000L
 // GPS jitter of a stationary phone can exceed MIN_SAMPLE_DISTANCE_M with poor fixes.
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*FindHeadingTest' --tests '*HeadingTest'`
Expected: PASS（全体で615件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/location/Heading.kt app/src/test/java/com/touringproject/v2/location/FindHeadingTest.kt
git commit -m "feat: work the heading out from the ride's route on the device"
```

---

### Task 2: 設定に録音と方位の値を足す

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/settings/Settings.kt`
- Test: `app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt`

**Interfaces:**
- Consumes: Task 1 の `HeadingParams`・`DEFAULT_HEADING_*`。
- Produces: `RECORD_LIMIT_SECONDS_CHOICES`（10〜60の5秒刻み）・`DEFAULT_RECORD_LIMIT_SECONDS = 20`・`START_CUE_MS_CHOICES`（0・500・1000・1500・2000・3000）・`DEFAULT_START_CUE_MS = 1_500`・`HEADING_REFERENCE_M_CHOICES`・`HEADING_ACCURACY_M_CHOICES`・`HEADING_HOLD_MINUTES_CHOICES`。`Settings` の `recordLimitSeconds`・`startCueMs`・`headingReferenceMeters`・`headingAccuracyMeters`・`headingHoldMinutes`（既定値つき）。`val Settings.recordLimitMs: Long`・`val Settings.headingParams: HeadingParams`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
index a979411..737c7f0 100644
--- a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
@@ -1,5 +1,6 @@
 package com.touringproject.v2.settings
 
+import com.touringproject.v2.location.HeadingParams
 import kotlinx.coroutines.flow.MutableStateFlow
 import kotlinx.coroutines.launch
 import kotlinx.coroutines.test.runTest
@@ -71,6 +72,31 @@ class SettingsTest {
     assertEquals(listOf(6, 12, 24, 48), MAX_RECORDING_HOURS_CHOICES)
   }
 
+  // Slice 5 spec §6 and §4.3: SC-11's and SC-22's values, with their defaults until chosen.
+  @Test
+  fun recording_and_heading_values_start_at_their_defaults() {
+    val s = decodeSettings("""{"userName":"rider01"}""").first
+    assertEquals(20, s.recordLimitSeconds)
+    assertEquals(20_000L, s.recordLimitMs)
+    assertEquals(1_500, s.startCueMs)
+    assertEquals(HeadingParams(referenceMeters = 15, accuracyMeters = 20, holdMinutes = 10), s.headingParams)
+    assertEquals(listOf(10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60), RECORD_LIMIT_SECONDS_CHOICES)
+    assertEquals(listOf(0, 500, 1_000, 1_500, 2_000, 3_000), START_CUE_MS_CHOICES)
+    assertEquals(listOf(10, 15, 20, 30), HEADING_REFERENCE_M_CHOICES)
+    assertEquals(listOf(10, 20, 30, 50), HEADING_ACCURACY_M_CHOICES)
+    assertEquals(listOf(2, 5, 10, 30), HEADING_HOLD_MINUTES_CHOICES)
+  }
+
+  @Test
+  fun recording_and_heading_values_round_trip_and_odd_ones_fall_back() = runTest {
+    val store = FakeStore()
+    val s = Settings("rider01", recordLimitSeconds = 45, startCueMs = 0, headingReferenceMeters = 30, headingAccuracyMeters = 50, headingHoldMinutes = 2)
+    SettingsRepository(store).update(s)
+    assertEquals(s, SettingsRepository(store).load())
+    val odd = """{"userName":"rider01","recordLimitSeconds":12,"startCueMs":"long","headingReferenceMeters":5,"headingAccuracyMeters":100,"headingHoldMinutes":60}"""
+    assertEquals(Settings("rider01"), decodeSettings(odd).first)
+  }
+
   @Test
   fun not_json_falls_back_to_defaults() {
     val (s, needsSave) = decodeSettings("{not json", Random(3))
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SettingsTest'`
Expected: コンパイルで落ちる（`recordLimitSeconds` などが無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/settings/Settings.kt b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
index cbb440c..9e932f2 100644
--- a/app/src/main/java/com/touringproject/v2/settings/Settings.kt
+++ b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
@@ -1,5 +1,9 @@
 package com.touringproject.v2.settings
 
+import com.touringproject.v2.location.DEFAULT_HEADING_ACCURACY_M
+import com.touringproject.v2.location.DEFAULT_HEADING_HOLD_MINUTES
+import com.touringproject.v2.location.DEFAULT_HEADING_REFERENCE_M
+import com.touringproject.v2.location.HeadingParams
 import kotlinx.coroutines.flow.Flow
 import kotlinx.coroutines.flow.distinctUntilChanged
 import kotlinx.coroutines.flow.drop
@@ -30,6 +34,18 @@ const val DEFAULT_VOLUME_DB = 6
 val MAX_RECORDING_HOURS_CHOICES = listOf(6, 12, 24, 48)
 const val DEFAULT_MAX_RECORDING_HOURS = 24
 
+// SC-11 (slice 5 spec §6): how long a question may be recorded, and how long its start cue sounds (0: none). The trial
+// on SC-12 takes the same values; SC-19's voice input does not.
+val RECORD_LIMIT_SECONDS_CHOICES = (10..60 step 5).toList()
+const val DEFAULT_RECORD_LIMIT_SECONDS = 20
+val START_CUE_MS_CHOICES = listOf(0, 500, 1_000, 1_500, 2_000, 3_000)
+const val DEFAULT_START_CUE_MS = 1_500
+
+// SC-22 (slice 5 spec §4.3): how the heading is worked out from the route.
+val HEADING_REFERENCE_M_CHOICES = listOf(10, 15, 20, 30)
+val HEADING_ACCURACY_M_CHOICES = listOf(10, 20, 30, 50)
+val HEADING_HOLD_MINUTES_CHOICES = listOf(2, 5, 10, 30)
+
 data class Settings(
   val userName: String,
   val returnEnabled: Boolean = true,
@@ -42,8 +58,18 @@ data class Settings(
   val showAskPins: Boolean = true,
   /** SC-06: whether the map shows the point memos' pins, kept like showAskPins (slice 3 spec §7.6). */
   val showNotePins: Boolean = true,
+  val recordLimitSeconds: Int = DEFAULT_RECORD_LIMIT_SECONDS,
+  val startCueMs: Int = DEFAULT_START_CUE_MS,
+  val headingReferenceMeters: Int = DEFAULT_HEADING_REFERENCE_M,
+  val headingAccuracyMeters: Int = DEFAULT_HEADING_ACCURACY_M,
+  val headingHoldMinutes: Int = DEFAULT_HEADING_HOLD_MINUTES,
 )
 
+/** The longest a question is recorded (SC-11). */
+val Settings.recordLimitMs: Long get() = recordLimitSeconds * 1_000L
+
+val Settings.headingParams: HeadingParams get() = HeadingParams(headingReferenceMeters, headingAccuracyMeters, headingHoldMinutes)
+
 /**
  * The longest recording time each time the rider changes it, but not the value first loaded (US-C-08.005). AppGraph
  * follows it, so the recording ride's deadline moves even when SC-16 goes away mid-save (Android #33).
@@ -62,6 +88,8 @@ fun randomUserName(random: Random = Random.Default): String =
 fun decodeSettings(raw: String?, random: Random = Random.Default): Pair<Settings, Boolean> {
   val obj: JsonObject = runCatching { json.parseToJsonElement(raw ?: "").jsonObject }.getOrElse { JsonObject(emptyMap()) }
   fun string(key: String) = runCatching { obj[key]?.jsonPrimitive?.contentOrNull }.getOrNull()
+  fun choice(key: String, choices: List<Int>, default: Int) =
+    runCatching { obj[key]?.jsonPrimitive?.intOrNull }.getOrNull()?.takeIf { it in choices } ?: default
   fun app(element: kotlinx.serialization.json.JsonElement?) =
     runCatching { element?.let { json.decodeFromJsonElement<LaunchableApp>(it) } }.getOrNull()
   val savedName = string("userName")?.takeIf { USER_NAME_RE.matches(it) }
@@ -77,6 +105,11 @@ fun decodeSettings(raw: String?, random: Random = Random.Default): Pair<Settings
       ?.takeIf { it in MAX_RECORDING_HOURS_CHOICES } ?: DEFAULT_MAX_RECORDING_HOURS,
     showAskPins = runCatching { obj["showAskPins"]?.jsonPrimitive?.booleanOrNull }.getOrNull() ?: true,
     showNotePins = runCatching { obj["showNotePins"]?.jsonPrimitive?.booleanOrNull }.getOrNull() ?: true,
+    recordLimitSeconds = choice("recordLimitSeconds", RECORD_LIMIT_SECONDS_CHOICES, DEFAULT_RECORD_LIMIT_SECONDS),
+    startCueMs = choice("startCueMs", START_CUE_MS_CHOICES, DEFAULT_START_CUE_MS),
+    headingReferenceMeters = choice("headingReferenceMeters", HEADING_REFERENCE_M_CHOICES, DEFAULT_HEADING_REFERENCE_M),
+    headingAccuracyMeters = choice("headingAccuracyMeters", HEADING_ACCURACY_M_CHOICES, DEFAULT_HEADING_ACCURACY_M),
+    headingHoldMinutes = choice("headingHoldMinutes", HEADING_HOLD_MINUTES_CHOICES, DEFAULT_HEADING_HOLD_MINUTES),
   )
   return settings to (savedName == null)
 }
@@ -93,6 +126,11 @@ fun encodeSettings(settings: Settings): String = json.encodeToString(
     maxRecordingHours = settings.maxRecordingHours,
     showAskPins = settings.showAskPins,
     showNotePins = settings.showNotePins,
+    recordLimitSeconds = settings.recordLimitSeconds,
+    startCueMs = settings.startCueMs,
+    headingReferenceMeters = settings.headingReferenceMeters,
+    headingAccuracyMeters = settings.headingAccuracyMeters,
+    headingHoldMinutes = settings.headingHoldMinutes,
   ),
 )
 
@@ -107,6 +145,11 @@ private data class SavedSettings(
   val maxRecordingHours: Int,
   val showAskPins: Boolean,
   val showNotePins: Boolean,
+  val recordLimitSeconds: Int,
+  val startCueMs: Int,
+  val headingReferenceMeters: Int,
+  val headingAccuracyMeters: Int,
+  val headingHoldMinutes: Int,
 )
 
 fun withRecentApp(recent: List<LaunchableApp>, app: LaunchableApp, max: Int = 5): List<LaunchableApp> =
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SettingsTest'`
Expected: PASS（全体で617件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/settings/Settings.kt app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
git commit -m "feat: keep the recording limit, the start cue and the heading's parameters in the settings"
```

---

### Task 3: 質問と質問できなかった地点に、端末の方位を付けて送る

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt`
- Modify: `store/RideDatabase.kt`（`segmentTail`）・`location/PositionTracker.kt`・`ask/AskPorts.kt`・`ask/AskController.kt`・`ask/AskRecord.kt`・`api/ApiClient.kt`・`sync/RideSync.kt`・`sync/SyncPlan.kt`・`store/RoomSyncStore.kt`・`store/RoomAskLog.kt`・`store/RoomRecords.kt`・`AppGraph.kt`
- Test: `ride/RouteHeadingTest.kt`（新規）・`location/PositionTrackerTest.kt`・`ask/AskControllerTest.kt`・`store/RoomAskLogTest.kt`・`store/RoomSyncStoreTest.kt`・`api/ApiClientTest.kt`・`sync/SyncPlanTest.kt`

**Interfaces:**
- Consumes: Task 1 の `findHeading`・`HeadingResult.degrees`、Task 2 の `Settings.headingParams`。
- Produces: `RideDao.segmentTail(rideId: String, segment: Int, count: Int): List<RoutePointEntity>`（新しい順）。`const val HEADING_POINTS = 120`。`class RouteHeading(ride: () -> Ride?, points: suspend (rideId, segment, count) -> List<RoutePoint>, params: () -> HeadingParams, log: (String, Throwable) -> Unit)` の `suspend fun find(here: Fix?, now: Long): HeadingResult`。`Positions.end(): Fix?`（位置の一覧は返さない）。`AskDeps.heading: suspend (here: Fix?, now: Long) -> Double?`（`location` の次）。`AskBody.headingDegrees: Double?`（`headingSample` は消す）。`OfflineAskBody(..., headingDegrees: Double? = null)`（末尾）。`UnsentUnreached(..., headingDegrees: Double? = null)`（末尾）。`unreachedAsk(askId, at, here, headingDegrees: Double?, rideId)`。`AskRecord.sample` は消す。`AppGraph.routeHeading`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
index 2aa805b..ea0a010 100644
--- a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
+++ b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
@@ -307,6 +307,22 @@ class ApiClientTest {
     assertEquals("r1", sent["rideId"]!!.jsonPrimitive.content)
     assertEquals(JsonNull, sent["location"])
     assertEquals(JsonNull, sent["headingSample"])
+    // No heading is left out, which the Backend takes as none.
+    assertEquals(null, sent["headingDegrees"])
+  }
+
+  // Slice 5 spec §4.4: the heading the device worked out goes as degrees, with an ask and with an unreached one.
+  @Test
+  fun the_devices_heading_goes_as_degrees() = runTest {
+    server.enqueue(json(202, """{"askId":"a1","conversationId":"c1","conversationExpiresAt":"2999-01-01T00:00:00Z"}"""))
+    server.enqueue(json(200, """{"askId":"u1","applied":true}"""))
+    client().postAsk(AskBody(text = "q", headingDegrees = 271.5))
+    client().putOfflineAsk("u1", OfflineAskBody("2026-10-22T01:24:00Z", null, null, "r1", "2026-10-22T01:24:00Z", 33.0))
+    val asked = Json.parseToJsonElement(server.takeRequest().body.readUtf8()).jsonObject
+    assertEquals(271.5, asked["headingDegrees"]!!.jsonPrimitive.content.toDouble(), 0.0)
+    assertEquals(null, asked["headingSample"])
+    val unreached = Json.parseToJsonElement(server.takeRequest().body.readUtf8()).jsonObject
+    assertEquals(33.0, unreached["headingDegrees"]!!.jsonPrimitive.content.toDouble(), 0.0)
   }
 
   // 409: the id is an ask the Backend took in; it is not retried.
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index 1f3460a..68d78f5 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -7,7 +7,6 @@ import com.touringproject.v2.api.AskApi
 import com.touringproject.v2.api.AskBody
 import com.touringproject.v2.api.AskResult
 import com.touringproject.v2.api.AudioClip
-import com.touringproject.v2.api.HeadingSample
 import com.touringproject.v2.api.Point
 import com.touringproject.v2.audio.InputDevice
 import com.touringproject.v2.audio.MediaVolume
@@ -42,7 +41,6 @@ private fun done(
 ) = AskResult("a1", status, transcript, answer, audio, error)
 private val PROCESSING = done(status = "processing")
 private val HERE = Fix(35.6812, 139.7671, 100_000, 5.0)
-private val BEHIND = Fix(35.6806, 139.7671, 90_000, 5.0)
 
 /** A fake world around the controller that records what it was asked to do, in order. */
 private class Harness(
@@ -64,7 +62,11 @@ private class Harness(
   var ride: RideNow = RideNow.Recording("r1"),
   /** Whether the device has a network when the recording ends (slice 4 spec §4.1). */
   var online: Boolean = true,
+  /** What the ride's route gives as the heading (slice 5 spec §4). */
+  var heading: Double? = 12.5,
 ) {
+  /** Where and when the heading was asked for. */
+  val headingAsked = mutableListOf<Pair<Fix?, Long>>()
   val log = mutableListOf<String>()
   val states = mutableListOf<FlowState>()
   val bodies = mutableListOf<AskBody>()
@@ -123,8 +125,9 @@ private class Harness(
     ride = { ride },
     location = object : Positions {
       override fun begin() { log += "loc:begin" }
-      override fun end() = HERE to listOf(BEHIND, HERE)
+      override fun end() = HERE
     },
+    heading = { here, at -> headingAsked += here to at; heading },
     service = object : KeepAlive {
       override fun start() { log += "svc:start"; serviceError?.let { throw it } }
       override fun stop() { log += "svc:stop" }
@@ -184,12 +187,14 @@ class AskControllerTest {
         volumeDb = 6,
         audio = "AQID",
         location = Point(35.6812, 139.7671),
-        headingSample = HeadingSample(35.6806, 139.7671, "1970-01-01T00:01:30Z"),
+        headingDegrees = 12.5,
         conversationId = null,
         rideId = "r1",
       ),
       h.bodies[0],
     )
+    // Slice 5 spec §4.1: the heading is taken where and when the recording ended.
+    assertEquals(listOf<Pair<Fix?, Long>>(HERE to 3_000L), h.headingAsked)
     assertEquals(Phase.IDLE, h.phase)
     assertEquals(listOf(Phase.RECORDING, Phase.SENDING, Phase.WAITING, Phase.SPEAKING, Phase.IDLE), h.states.map { it.phase })
   }
@@ -603,7 +608,7 @@ class AskControllerTest {
     assertEquals(1_000L, kept.askedAt)
     assertEquals(1_000L, kept.updatedAt)
     assertEquals(HERE.latitude, kept.latitude!!, 0.0)
-    assertEquals(HeadingSample(BEHIND.latitude, BEHIND.longitude, "1970-01-01T00:01:30Z"), kept.sample)
+    assertEquals(12.5, kept.headingDegrees!!, 0.0)
     assertEquals(null, kept.conversationId)
     assertFalse(kept.newConversation)
     assertFalse(kept.sent)
diff --git a/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt b/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
index bd3fe63..0fc3ad5 100644
--- a/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
@@ -40,9 +40,9 @@ class PositionTrackerTest {
     tracker.begin()
     val oldCallback = source.onFix!!
     tracker.begin()
-    oldCallback(fix(99_000))
     source.onFix!!(fix(99_500))
-    assertEquals(listOf(fix(99_500)), tracker.end().second)
+    oldCallback(fix(99_900))
+    assertEquals(fix(99_500), tracker.end())
   }
 
   @Test
@@ -53,7 +53,7 @@ class PositionTrackerTest {
     tracker.end()
     source.lateLastKnown!!(fix(99_000))
     tracker.begin()
-    assertEquals(emptyList<Fix>(), tracker.end().second)
+    assertNull(tracker.end())
   }
 
   @Test
@@ -61,9 +61,7 @@ class PositionTrackerTest {
     val source = FakeSource().apply { last = fix(100_000 - MAX_CURRENT_AGE_MS - 1) }
     val tracker = PositionTracker(source)
     tracker.begin()
-    val (current, fixes) = tracker.end()
-    assertNull(current)
-    assertEquals(1, fixes.size)
+    assertNull(tracker.end())
   }
 
   @Test
@@ -73,8 +71,6 @@ class PositionTrackerTest {
     tracker.begin()
     source.onFix!!(fix(99_000))
     source.onFix!!(fix(98_000))
-    val (current, fixes) = tracker.end()
-    assertEquals(fix(99_000), current)
-    assertEquals(listOf(fix(90_000), fix(98_000), fix(99_000)), fixes)
+    assertEquals(fix(99_000), tracker.end())
   }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ride/RouteHeadingTest.kt b/app/src/test/java/com/touringproject/v2/ride/RouteHeadingTest.kt
new file mode 100644
index 0000000..c7c2f6e
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/ride/RouteHeadingTest.kt
@@ -0,0 +1,91 @@
+package com.touringproject.v2.ride
+
+import android.app.Application
+import androidx.room.Room
+import androidx.test.core.app.ApplicationProvider
+import androidx.test.ext.junit.runners.AndroidJUnit4
+import com.touringproject.v2.location.Fix
+import com.touringproject.v2.location.HeadingParams
+import com.touringproject.v2.location.HeadingResult
+import com.touringproject.v2.location.NoHeading
+import com.touringproject.v2.location.degrees
+import com.touringproject.v2.store.RideDatabase
+import com.touringproject.v2.store.RoomRideStore
+import com.touringproject.v2.store.toPoint
+import kotlinx.coroutines.runBlocking
+import org.junit.After
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
+import org.junit.Test
+import org.junit.runner.RunWith
+
+// Slice 5 spec §4.1: the heading comes from the last segment's points in Room, with the parameters of the moment.
+@RunWith(AndroidJUnit4::class)
+class RouteHeadingTest {
+  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
+    .allowMainThreadQueries()
+    .build()
+  private val store = RoomRideStore(db.rides())
+  private var ride: Ride? = null
+  private var params = HeadingParams()
+  private val failures = mutableListOf<String>()
+  private val heading = RouteHeading(
+    ride = { ride },
+    points = { rideId, segment, count -> db.rides().segmentTail(rideId, segment, count).map { it.toPoint() } },
+    params = { params },
+    log = { message, _ -> failures += message },
+  )
+
+  @After
+  fun close() = db.close()
+
+  // About 11 m a step north of 35.0, 139.0.
+  private fun point(segment: Int, step: Int, t: Long) = RoutePoint(segment, t, 35.0 + step * 0.0001, 139.0, 5.0)
+
+  private fun here(step: Int, t: Long) = Fix(35.0 + step * 0.0001, 139.0, t, 5.0)
+
+  @Test
+  fun the_heading_comes_from_the_last_segment_only() = runBlocking {
+    val first = newRide("r1", "箱根", 0, 7, 24 * HOUR_MS)
+    store.save(first)
+    // Riding south before the pause, then north after it, from far away (a ferry).
+    (0..3).forEach { store.addPoint("r1", point(0, -it, it * 5_000L), 0.0, 0) }
+    val resumed = first.pause(20_000).resume(600_000, 7, 24 * HOUR_MS)
+    store.save(resumed)
+    ride = resumed
+    assertEquals(HeadingResult.None(NoHeading.NOT_MOVED), heading.find(here(-500, 600_000), 600_000))
+    store.addPoint("r1", point(1, -500, 600_000), 0.0, 0)
+    store.addPoint("r1", point(1, -499, 605_000), 0.0, 0)
+    val north = heading.find(here(-498, 610_000), 610_000).degrees!!
+    assertTrue("north: $north", north < 1.0 || north > 359.0)
+  }
+
+  @Test
+  fun a_paused_ride_takes_the_segment_before_the_pause() = runBlocking {
+    val started = newRide("r1", "箱根", 0, 7, 24 * HOUR_MS)
+    store.save(started)
+    (0..3).forEach { store.addPoint("r1", point(0, it, it * 5_000L), 0.0, 0) }
+    ride = started.pause(20_000)
+    assertEquals(0.0, heading.find(here(3, 15_000), 60_000).degrees!!, 1.0)
+  }
+
+  @Test
+  fun the_parameters_of_the_moment_are_used() = runBlocking {
+    val started = newRide("r1", "箱根", 0, 7, 24 * HOUR_MS)
+    store.save(started)
+    ride = started
+    (0..3).forEach { store.addPoint("r1", point(0, it, it * 5_000L), 0.0, 0) }
+    assertEquals(0.0, heading.find(here(3, 15_000), 15_000 + 5 * 60_000).degrees!!, 1.0)
+    params = HeadingParams(holdMinutes = 2)
+    assertEquals(HeadingResult.None(NoHeading.HELD_TOO_LONG), heading.find(here(3, 15_000), 15_000 + 5 * 60_000))
+  }
+
+  @Test
+  fun without_a_ride_or_its_points_there_is_no_route() = runBlocking {
+    assertEquals(HeadingResult.None(NoHeading.NOT_MOVED), heading.find(here(0, 0), 0))
+    val broken = RouteHeading({ newRide("r1", "箱根", 0, 7, HOUR_MS) }, { _, _, _ -> error("closed") }, { params }) { message, _ -> failures += message }
+    assertNull(broken.find(here(0, 0), 0).degrees)
+    assertEquals(listOf("heading_points_failed rideId=r1"), failures)
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
index 40e06b9..a48174d 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
@@ -8,7 +8,6 @@ import com.touringproject.v2.ask.ASK_INPUT_VOICE
 import com.touringproject.v2.ask.AskOutcome
 import com.touringproject.v2.ask.AskRecord
 import com.touringproject.v2.ask.unreachedAsk
-import com.touringproject.v2.api.HeadingSample
 import com.touringproject.v2.location.Fix
 import com.touringproject.v2.ride.EndReason
 import com.touringproject.v2.ride.HOUR_MS
@@ -148,21 +147,22 @@ class RoomAskLogTest {
     db.close()
   }
 
-  // Slice 4 spec §4.2: an ask that never reached the Backend keeps when and where it was, and the heading's sample.
+  // Slice 4 spec §4.2: an ask that never reached the Backend keeps when and where it was, and (slice 5 spec §4.4) the
+  // heading the device worked out; no sample any more.
   @Test
-  fun an_unreached_ask_is_kept_without_a_conversation_and_with_its_sample() = runBlocking {
+  fun an_unreached_ask_is_kept_without_a_conversation_and_with_its_heading() = runBlocking {
     keepRide()
-    val sample = HeadingSample(35.0, 138.999, "1970-01-01T00:00:00.500Z")
-    log.save(unreachedAsk("u1", 1_000, Fix(35.001, 139.0, 1_000, 5.0), sample, "r1"))
+    log.save(unreachedAsk("u1", 1_000, Fix(35.001, 139.0, 1_000, 5.0), 271.5, "r1"))
     val stored = db.asks().ask("u1")!!
     assertEquals("offline", stored.status)
     assertNull(stored.conversationId)
     assertEquals(1_000L, stored.updatedAt)
     assertNull(stored.sentUpdatedAt)
-    assertEquals(500L, stored.sampleAt)
+    assertEquals(271.5, stored.headingDegrees!!, 0.0)
+    assertEquals(listOf(null, null, null), listOf(stored.sampleLatitude, stored.sampleLongitude, stored.sampleAt))
     val record = stored.toRecord()
     assertEquals(AskOutcome.OFFLINE, record.outcome)
-    assertEquals(sample, record.sample)
+    assertEquals(271.5, record.headingDegrees!!, 0.0)
     assertFalse(record.sent)
     assertEquals(1, db.asks().countForRide("r1").first())
     db.close()
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
index f208808..910b571 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
@@ -16,7 +16,6 @@ import com.touringproject.v2.sync.PendingDeletion
 import com.touringproject.v2.sync.UnsentAskMemo
 import com.touringproject.v2.sync.UnsentNote
 import com.touringproject.v2.sync.UnsentUnreached
-import com.touringproject.v2.api.HeadingSample
 import com.touringproject.v2.ask.unreachedAsk
 import com.touringproject.v2.location.Fix
 import kotlinx.coroutines.MainScope
@@ -206,10 +205,13 @@ class RoomSyncStoreTest {
   fun an_unreached_ask_is_unsent_until_its_version_is_taken_and_keeps_its_address() = runBlocking {
     rides.save(ride)
     val log = RoomAskLog(db.asks(), MainScope()) { _, _ -> }
-    log.save(unreachedAsk("u1", 1_400, Fix(35.0, 139.0, 1_400, 5.0), HeadingSample(34.99, 139.0, "1970-01-01T00:00:01.300Z"), "r1"))
+    log.save(unreachedAsk("u1", 1_400, Fix(35.0, 139.0, 1_400, 5.0), 33.0, "r1"))
     log.save(unreachedAsk("u2", 1_600, null, null, "r1"))
     assertEquals(
-      listOf(UnsentUnreached("u1", "r1", 1_400, 35.0, 139.0, 34.99, 139.0, 1_300, 1_400), UnsentUnreached("u2", "r1", 1_600, null, null, null, null, null, 1_600)),
+      listOf(
+        UnsentUnreached("u1", "r1", 1_400, 35.0, 139.0, null, null, null, 1_400, 33.0),
+        UnsentUnreached("u2", "r1", 1_600, null, null, null, null, null, 1_600, null),
+      ),
       store.unsentUnreached(),
     )
     store.unreachedSent("u1", 1_400, "神奈川県箱根町仙石原", 12.5)
@@ -224,6 +226,19 @@ class RoomSyncStoreTest {
     assertEquals(emptyList<UnsentUnreached>(), store.unsentUnreached())
   }
 
+  // Slice 5 spec §4.4: an unreached ask kept before slice 5 has a sample and no heading yet; it still goes with its sample.
+  @Test
+  fun an_unreached_ask_kept_before_slice_5_still_goes_with_its_sample() = runBlocking {
+    rides.save(ride)
+    db.asks().upsert(
+      AskEntity(
+        "u0", 1_400, null, null, null, 35.0, 139.0, null, null, "voice", null, false, "offline", null, "r1",
+        updatedAt = 1_400, sampleLatitude = 34.99, sampleLongitude = 139.0, sampleAt = 1_300,
+      ),
+    )
+    assertEquals(listOf(UnsentUnreached("u0", "r1", 1_400, 35.0, 139.0, 34.99, 139.0, 1_300, 1_400, null)), store.unsentUnreached())
+  }
+
   // Android #67: what the Backend took without a place gets a newer version and goes again; the others stay as they are.
   @Test
   fun a_place_the_backend_could_not_tell_is_asked_for_again() = runBlocking {
diff --git a/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt b/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
index a030759..fb43e86 100644
--- a/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
@@ -80,4 +80,16 @@ class SyncPlanTest {
     assertNull(bare.location)
     assertNull(bare.headingSample)
   }
+
+  // Slice 5 spec §4.4: an unreached ask goes with the device's heading; one kept before slice 5 still has its sample.
+  @Test
+  fun an_unreached_ask_goes_with_its_heading_and_an_old_one_with_its_sample() {
+    val ask = UnsentUnreached("u1", "r1", 1_000, 35.3, 138.9, null, null, null, 2_000, 271.5)
+    val body = ask.toBody()
+    assertEquals(271.5, body.headingDegrees!!, 0.0)
+    assertNull(body.headingSample)
+    val old = UnsentUnreached("u0", "r1", 1_000, 35.3, 138.9, 35.29, 138.89, 500, 2_000).toBody()
+    assertNull(old.headingDegrees)
+    assertEquals(HeadingSample(35.29, 138.89, "1970-01-01T00:00:00.500Z"), old.headingSample)
+  }
 }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RouteHeadingTest' --tests '*AskControllerTest' --tests '*PositionTrackerTest'`
Expected: コンパイルで落ちる（`RouteHeading`・`segmentTail`・`AskDeps.heading`・`AskBody.headingDegrees` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index f767039..070253a 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -25,8 +25,10 @@ import com.touringproject.v2.handsfree.PressGate
 import com.touringproject.v2.handsfree.PressRouter
 import com.touringproject.v2.location.FusedPositionSource
 import com.touringproject.v2.location.FusedRouteSource
+import com.touringproject.v2.location.HeadingParams
 import com.touringproject.v2.location.PositionTracker
 import com.touringproject.v2.location.RouteSource
+import com.touringproject.v2.location.degrees
 import com.touringproject.v2.nav.AppLauncher
 import com.touringproject.v2.net.Connectivity
 import com.touringproject.v2.recordings.RecordingCheck
@@ -43,6 +45,7 @@ import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.RideController
 import com.touringproject.v2.ride.RideDeps
 import com.touringproject.v2.ride.RideStatus
+import com.touringproject.v2.ride.RouteHeading
 import com.touringproject.v2.service.AlarmDeadline
 import com.touringproject.v2.service.ContextServiceLauncher
 import com.touringproject.v2.service.RideNotices
@@ -53,6 +56,7 @@ import com.touringproject.v2.settings.DataStoreKeyValueStore
 import com.touringproject.v2.settings.KeystoreCipher
 import com.touringproject.v2.settings.LastSaved
 import com.touringproject.v2.settings.SettingsRepository
+import com.touringproject.v2.settings.headingParams
 import com.touringproject.v2.settings.maxRecordingChanges
 import com.touringproject.v2.store.RideDatabase
 import com.touringproject.v2.store.RoomAskEdits
@@ -62,6 +66,7 @@ import com.touringproject.v2.store.RoomRecords
 import com.touringproject.v2.store.RoomRideStore
 import com.touringproject.v2.store.RoomSyncStore
 import com.touringproject.v2.store.RoomTakeover
+import com.touringproject.v2.store.toPoint
 import com.touringproject.v2.sync.RideSync
 import com.touringproject.v2.sync.Takeover
 import com.touringproject.v2.sync.credentialChanges
@@ -175,6 +180,14 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     ),
   )
 
+  /** The heading from the ride's route, with the parameters the rider chose (slice 5 spec §4). */
+  val routeHeading = RouteHeading(
+    ride = { rides.active.value },
+    points = { rideId, segment, count -> database.rides().segmentTail(rideId, segment, count).map { it.toPoint() } },
+    params = { settings.settings.value?.headingParams ?: HeadingParams() },
+    log = { message, e -> Log.w("trv2.ride", message, e) },
+  )
+
   /** How many asks the device keeps for the ride recording or paused (SC-02, SC-04; Android #35). */
   val activeAskCount: StateFlow<Int> =
     activeAskCount(rides.active.map { it?.id }, database.asks()::countForRide).stateIn(scope, SharingStarted.Eagerly, 0)
@@ -202,6 +215,7 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       newId = { UUID.randomUUID().toString() },
       ride = { rideNow(rides.active.value) },
       location = PositionTracker(FusedPositionSource(context)),
+      heading = { here, now -> routeHeading.find(here, now).degrees },
       service = serviceCoordinator.keepAlive,
       nav = launcher,
       cues = cues,
diff --git a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
index 9d0f813..48b18cb 100644
--- a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
+++ b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
@@ -27,6 +27,10 @@ class ApiError(val kind: ApiErrorKind, message: String? = null) : Exception(mess
 
 @Serializable data class Point(val latitude: Double, val longitude: Double)
 
+/**
+ * The older point the Backend once worked a heading out from. Only point memos and unreached asks kept before
+ * slice 5 still have one; whatever the device makes now goes with headingDegrees (slice 5 spec §4.4).
+ */
 @Serializable data class HeadingSample(val latitude: Double, val longitude: Double, val at: String)
 
 @Serializable
@@ -34,7 +38,8 @@ data class AskBody(
   val audio: String? = null,
   val text: String? = null,
   val location: Point? = null,
-  val headingSample: HeadingSample? = null,
+  /** Worked out on the device from the ride's route (slice 5 spec §4); null when there is none. */
+  val headingDegrees: Double? = null,
   val conversationId: String? = null,
   val volumeDb: Int? = null,
   /** The recording ride the ask belongs to; every ask has one since asks need a recording ride (slice 2 spec §4.7). */
@@ -106,9 +111,19 @@ data class NoteBody(val at: String, val location: Point?, val headingSample: Hea
 /** What the Backend settled for a point memo when it first took it; null when it could not tell (no place, no heading). */
 @Serializable data class NoteSaved(val address: String? = null, val headingDegrees: Double? = null)
 
-/** An ask that never reached the Backend, as a whole (slice 4 spec §4.4). location is null when it had no place yet. */
+/**
+ * An ask that never reached the Backend, as a whole (slice 4 spec §4.4). location is null when it had no place yet.
+ * headingDegrees is the device's heading; headingSample is left only on one kept before slice 5 (spec §4.4).
+ */
 @Serializable
-data class OfflineAskBody(val askedAt: String, val location: Point?, val headingSample: HeadingSample?, val rideId: String, val updatedAt: String)
+data class OfflineAskBody(
+  val askedAt: String,
+  val location: Point?,
+  val headingSample: HeadingSample?,
+  val rideId: String,
+  val updatedAt: String,
+  val headingDegrees: Double? = null,
+)
 
 /** What the Backend settled for an unreached ask when it first took it; null when it could not tell. */
 @Serializable data class OfflineAskSaved(val address: String? = null, val headingDegrees: Double? = null)
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index a75c9a0..3279be3 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -7,7 +7,6 @@ import com.touringproject.v2.api.AskBody
 import com.touringproject.v2.api.AskResult
 import com.touringproject.v2.api.Point
 import com.touringproject.v2.location.Fix
-import com.touringproject.v2.location.pickHeadingSample
 import com.touringproject.v2.settings.ReturnTiming
 import com.touringproject.v2.settings.Settings
 import kotlinx.coroutines.CancellationException
@@ -54,11 +53,12 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
   private class Run(val id: Int, val source: Source, var returned: Boolean = false)
 
   // meta and pcm go to SC-12 once the ask has reached the Backend, or failed there; an unreached ask's recording goes.
+  // heading is worked out once, where the recording ended, for the ask sent and the unreached one alike.
   private class Recording(
     val audio: String,
     val name: String,
     val current: Fix?,
-    val fixes: List<Fix>,
+    val heading: Double?,
     val endedAt: Long,
     val meta: RecordingMeta,
     val pcm: ByteArray,
@@ -250,8 +250,9 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     }
     val endedAt = d.now()
     val meta = RecordingMeta(stopped.name, startedAt, pcmDurationMs(stopped.pcm.size), phoneMic, device, null)
-    val (currentFix, fixes) = d.location.end()
-    return Recording(Base64.getEncoder().encodeToString(stopped.pcm), stopped.name, currentFix, fixes, endedAt, meta, stopped.pcm)
+    val here = d.location.end()
+    val heading = d.heading(here, endedAt)
+    return Recording(Base64.getEncoder().encodeToString(stopped.pcm), stopped.name, here, heading, endedAt, meta, stopped.pcm)
   }
 
   private suspend fun send(recording: Recording, rideId: String, api: AskApi, run: Run): SentAsk? {
@@ -261,7 +262,7 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       volumeDb = d.settings().answerVolumeDb,
       audio = recording.audio,
       location = here?.let { Point(it.latitude, it.longitude) },
-      headingSample = here?.let { pickHeadingSample(recording.fixes, it) },
+      headingDegrees = recording.heading,
       conversationId = d.conversation.current(d.now()),
       rideId = rideId,
     )
@@ -289,15 +290,14 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
   }
 
   /**
-   * US-C-09: the ask never reached the Backend. Its time, place and heading's sample are kept as an unreached ask, which
-   * is sent later; the recording is dropped (US-C-09.001) and the conversation is left as it was (US-C-09.006). An ask
-   * the rider cancelled meanwhile is not kept: they let it go.
+   * US-C-09: the ask never reached the Backend. Its time, place and heading are kept as an unreached ask, which is sent
+   * later; the recording is dropped (US-C-09.001) and the conversation is left as it was (US-C-09.006). An ask the
+   * rider cancelled meanwhile is not kept: they let it go.
    */
   private suspend fun keepUnreached(recording: Recording, rideId: String, run: Run) {
     val d = deps
     if (isCurrent(run)) {
-      val here = recording.current
-      d.asks.keep(unreachedAsk(d.newId(), recording.endedAt, here, here?.let { pickHeadingSample(recording.fixes, it) }, rideId))
+      d.asks.keep(unreachedAsk(d.newId(), recording.endedAt, recording.current, recording.heading, rideId))
       d.log("ask_unreached", mapOf("rideId" to rideId))
     }
     fail(FailureReason.NETWORK, run)
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
index 4907dbe..99a60b0 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
@@ -51,7 +51,8 @@ fun interface AskLog {
 
 interface Positions {
   fun begin()
-  fun end(): Pair<Fix?, List<Fix>>
+  /** Where the ask is: the newest fix since begin(), unless it is older than 30 s. */
+  fun end(): Fix?
 }
 
 interface KeepAlive {
@@ -117,6 +118,8 @@ class AskDeps(
   /** Whether a ride is recording now: an ask starts only then (slice 2 spec §4.7). */
   val ride: () -> RideNow,
   val location: Positions,
+  /** The heading at here, as of now, from the recording ride's route (slice 5 spec §4); null when there is none. */
+  val heading: suspend (here: Fix?, now: Long) -> Double?,
   val service: KeepAlive,
   val nav: NavReturn,
   val cues: Cues,
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt b/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
index 7d2e64e..f16bf52 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
@@ -1,7 +1,6 @@
 package com.touringproject.v2.ask
 
 import com.touringproject.v2.api.AskResult
-import com.touringproject.v2.api.HeadingSample
 import com.touringproject.v2.location.Fix
 import java.time.OffsetDateTime
 
@@ -39,8 +38,6 @@ data class AskRecord(
   val rideId: String?,
   /** The conversation's memo (US-D-04.001). The ask loop never sets it; only SC-08 does, through AskEdits. */
   val memo: String? = null,
-  /** The older point the Backend takes an unreached ask's heading from (slice 4 spec §4.2); null for the other asks. */
-  val sample: HeadingSample? = null,
   /** When an unreached ask last changed: the version the Backend compares. null for the asks the Backend made. */
   val updatedAt: Long? = null,
   /** False until an unreached ask has reached the Backend; the asks the Backend made are there from the start. */
@@ -48,10 +45,10 @@ data class AskRecord(
 )
 
 /**
- * An ask that never reached the Backend (slice 4 spec §4): when the recording ended, where, and the sample for the
- * heading. Its id is the device's; nothing it said is kept, and it joins no conversation.
+ * An ask that never reached the Backend (slice 4 spec §4): when the recording ended, where, and the heading the device
+ * worked out there (slice 5 spec §4.4). Its id is the device's; nothing it said is kept, and it joins no conversation.
  */
-fun unreachedAsk(askId: String, at: Long, here: Fix?, sample: HeadingSample?, rideId: String) = AskRecord(
+fun unreachedAsk(askId: String, at: Long, here: Fix?, headingDegrees: Double?, rideId: String) = AskRecord(
   askId = askId,
   askedAt = at,
   answeredAt = null,
@@ -60,14 +57,13 @@ fun unreachedAsk(askId: String, at: Long, here: Fix?, sample: HeadingSample?, ri
   latitude = here?.latitude,
   longitude = here?.longitude,
   address = null,
-  headingDegrees = null,
+  headingDegrees = headingDegrees,
   input = ASK_INPUT_VOICE,
   conversationId = null,
   newConversation = false,
   outcome = AskOutcome.OFFLINE,
   failure = null,
   rideId = rideId,
-  sample = sample,
   updatedAt = at,
   sent = false,
 )
diff --git a/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt b/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt
index ea19bdc..98caba8 100644
--- a/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt
+++ b/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt
@@ -2,8 +2,9 @@ package com.touringproject.v2.location
 
 import com.touringproject.v2.ask.Positions
 
-// Collects position fixes while a question is recorded. A last-known point older than MAX_CURRENT_AGE_MS is not
-// sent as the current position, and callbacks that belong to an earlier begin() are ignored.
+// Collects position fixes while a question is recorded, only to tell where it was asked: the heading comes from the
+// ride's route (slice 5 spec §4.1). A last-known point older than MAX_CURRENT_AGE_MS is not sent as the current
+// position, and callbacks that belong to an earlier begin() are ignored.
 const val MAX_CURRENT_AGE_MS = 30_000L
 
 fun interface Subscription {
@@ -34,14 +35,12 @@ class PositionTracker(private val source: PositionSource) : Positions {
   }
 
   @Synchronized
-  override fun end(): Pair<Fix?, List<Fix>> {
+  override fun end(): Fix? {
     generation += 1
     subscription?.remove()
     subscription = null
-    val sorted = fixes.sortedBy { it.timestamp }
+    val latest = fixes.maxByOrNull { it.timestamp }
     fixes.clear()
-    val latest = sorted.lastOrNull()
-    val current = latest?.takeIf { source.now() - it.timestamp <= MAX_CURRENT_AGE_MS }
-    return current to sorted
+    return latest?.takeIf { source.now() - it.timestamp <= MAX_CURRENT_AGE_MS }
   }
 }
diff --git a/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt b/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt
new file mode 100644
index 0000000..0dfe14a
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt
@@ -0,0 +1,42 @@
+package com.touringproject.v2.ride
+
+import com.touringproject.v2.location.Fix
+import com.touringproject.v2.location.HeadingParams
+import com.touringproject.v2.location.HeadingResult
+import com.touringproject.v2.location.findHeading
+import kotlinx.coroutines.CancellationException
+
+/**
+ * How many of the segment's last points are read. Points are 10 m apart at least, so a reference 30 m back is a few
+ * points away; the rest only covers points jittering at a stop.
+ */
+const val HEADING_POINTS = 120
+
+/**
+ * The heading of the ride recording or paused (slice 5 spec §4.1): from the points of its last segment only, since a
+ * ride may resume far from where it paused (a ferry). Asks, unreached asks and point memos all go through here, so
+ * each takes its heading the same way. Without a ride, or when its points cannot be read, there is no route.
+ */
+class RouteHeading(
+  private val ride: () -> Ride?,
+  private val points: suspend (rideId: String, segment: Int, count: Int) -> List<RoutePoint>,
+  private val params: () -> HeadingParams,
+  private val log: (String, Throwable) -> Unit,
+) {
+  suspend fun find(here: Fix?, now: Long): HeadingResult {
+    val active = ride()
+    val route = if (active == null) {
+      emptyList()
+    } else {
+      try {
+        points(active.id, active.segments.last().seq, HEADING_POINTS).map { Fix(it.lat, it.lon, it.t, it.accuracy) }
+      } catch (e: CancellationException) {
+        throw e
+      } catch (e: Exception) {
+        log("heading_points_failed rideId=${active.id}", e)
+        emptyList()
+      }
+    }
+    return findHeading(route, here, now, params())
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 34e71a9..84bf304 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -427,6 +427,10 @@ interface RideDao {
   @Query("SELECT * FROM route_points WHERE rideId = :rideId ORDER BY id DESC LIMIT :count")
   suspend fun lastPoints(rideId: String, count: Int): List<RoutePointEntity>
 
+  /** The segment's last count points, newest first: what the heading is worked out from (slice 5 spec §4.1). */
+  @Query("SELECT * FROM route_points WHERE rideId = :rideId AND segment = :segment ORDER BY id DESC LIMIT :count")
+  suspend fun segmentTail(rideId: String, segment: Int, count: Int): List<RoutePointEntity>
+
   @Query("UPDATE rides SET distanceMeters = :distanceMeters, lastAliveAt = :aliveAt WHERE id = :rideId")
   suspend fun updateDistance(rideId: String, distanceMeters: Double, aliveAt: Long)
 
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
index 51870cf..b4852bf 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
@@ -9,7 +9,6 @@ import kotlinx.coroutines.flow.MutableStateFlow
 import kotlinx.coroutines.flow.StateFlow
 import kotlinx.coroutines.flow.asStateFlow
 import kotlinx.coroutines.launch
-import java.time.Instant
 
 /**
  * The memo is not copied: the loop writes an ask once, at its end, and SC-08 changes its memo apart (AskDao.writeMemo),
@@ -32,9 +31,6 @@ fun AskRecord.toEntity() = AskEntity(
   failure = failure,
   rideId = rideId,
   updatedAt = updatedAt,
-  sampleLatitude = sample?.latitude,
-  sampleLongitude = sample?.longitude,
-  sampleAt = sample?.let { Instant.parse(it.at).toEpochMilli() },
 )
 
 /**
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
index ac79714..d12d63d 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
@@ -2,7 +2,6 @@ package com.touringproject.v2.store
 
 import com.touringproject.v2.ask.AskOutcome
 import com.touringproject.v2.ask.AskRecord
-import com.touringproject.v2.api.HeadingSample
 import com.touringproject.v2.records.NoteRecord
 import com.touringproject.v2.records.RideListItem
 import com.touringproject.v2.records.SaveSummary
@@ -12,7 +11,6 @@ import com.touringproject.v2.ride.Ride
 import com.touringproject.v2.ride.RoutePoint
 import kotlinx.coroutines.flow.Flow
 import kotlinx.coroutines.flow.map
-import java.time.Instant
 
 fun AskEntity.toRecord() = AskRecord(
   askId = askId,
@@ -31,11 +29,6 @@ fun AskEntity.toRecord() = AskRecord(
   failure = failure,
   rideId = rideId,
   memo = memo,
-  sample = if (sampleLatitude != null && sampleLongitude != null && sampleAt != null) {
-    HeadingSample(sampleLatitude, sampleLongitude, Instant.ofEpochMilli(sampleAt).toString())
-  } else {
-    null
-  },
   updatedAt = updatedAt,
   sent = status != "offline" || sentUpdatedAt != null,
 )
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
index d402527..a61ce59 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
@@ -53,7 +53,7 @@ class RoomSyncStore(
   override suspend fun unsentUnreached(): List<UnsentUnreached> = asks.unsentUnreached().mapNotNull {
     val rideId = it.rideId ?: return@mapNotNull null
     val updatedAt = it.updatedAt ?: return@mapNotNull null
-    UnsentUnreached(it.askId, rideId, it.askedAt, it.latitude, it.longitude, it.sampleLatitude, it.sampleLongitude, it.sampleAt, updatedAt)
+    UnsentUnreached(it.askId, rideId, it.askedAt, it.latitude, it.longitude, it.sampleLatitude, it.sampleLongitude, it.sampleAt, updatedAt, it.headingDegrees)
   }
 
   override suspend fun unreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?) =
diff --git a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
index cd510c7..4505301 100644
--- a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
@@ -49,7 +49,10 @@ data class UnsentNote(
   val updatedAt: Long,
 )
 
-/** An unreached ask that has changed since the Backend last took it (slice 4 spec §5.1). */
+/**
+ * An unreached ask that has changed since the Backend last took it (slice 4 spec §5.1). headingDegrees is the device's
+ * heading, or what the Backend settled once it has taken it; the sample is left only on one kept before slice 5.
+ */
 data class UnsentUnreached(
   val askId: String,
   val rideId: String,
@@ -60,6 +63,7 @@ data class UnsentUnreached(
   val sampleLongitude: Double?,
   val sampleAt: Long?,
   val updatedAt: Long,
+  val headingDegrees: Double? = null,
 )
 
 interface SyncStore {
diff --git a/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt b/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
index 06b89d7..2117017 100644
--- a/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
@@ -67,9 +67,12 @@ fun UnsentNote.toBody(): NoteBody {
   return NoteBody(iso(at), location, sample, text, iso(updatedAt))
 }
 
-/** An unreached ask goes with its place and sample as a point memo does: each only when it is whole. */
+/**
+ * An unreached ask goes with its place and heading; a sample (kept before slice 5) goes too while it is whole, and the
+ * Backend takes the heading first (slice 5 spec §4.4).
+ */
 fun UnsentUnreached.toBody(): OfflineAskBody {
   val location = if (latitude != null && longitude != null) Point(latitude, longitude) else null
   val sample = if (sampleLatitude != null && sampleLongitude != null && sampleAt != null) HeadingSample(sampleLatitude, sampleLongitude, iso(sampleAt)) else null
-  return OfflineAskBody(iso(askedAt), location, sample, rideId, iso(updatedAt))
+  return OfflineAskBody(iso(askedAt), location, sample, rideId, iso(updatedAt), headingDegrees)
 }
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun`
Expected: PASS（624件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/location/PositionTracker.kt app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/ask/AskRecord.kt app/src/main/java/com/touringproject/v2/api/ApiClient.kt app/src/main/java/com/touringproject/v2/sync/RideSync.kt app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt app/src/main/java/com/touringproject/v2/store/RoomRecords.kt app/src/main/java/com/touringproject/v2/AppGraph.kt
cd $AND && git add app/src/test/java/com/touringproject/v2/ride/RouteHeadingTest.kt app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
git commit -m "feat: send the device's heading with asks and unreached asks"
```

---

### Task 4: 地点メモに端末の方位を付けて送り、古い材料の選び方を消す

**Files:**
- Modify: `records/Notes.kt`・`store/RoomNotes.kt`・`sync/RideSync.kt`・`sync/SyncPlan.kt`・`store/RoomSyncStore.kt`・`api/ApiClient.kt`・`location/Heading.kt`・`store/RideDatabase.kt`（コメント）・`AppGraph.kt`
- Test: `location/HeadingTest.kt`・`records/NotesTest.kt`・`store/RoomNotesTest.kt`・`sync/SyncPlanTest.kt`・`ui/NoteRoutesTest.kt`・`ui/RecordLabelsTest.kt`

**Interfaces:**
- Consumes: Task 3 の `RouteHeading`・`AppGraph.routeHeading`。
- Produces: `NoteDraft(id, rideId, at, latitude, longitude, headingDegrees: Double? = null)`（材料の3項目は消す）。`fun RoutePoint.toFix(): Fix`。`fun noteDraft(id, rideId, at, newest: RoutePoint?, headingDegrees: Double?): NoteDraft`。`RoomNotes(notes, rides, now, newId, changed, heading: suspend (Fix?, Long) -> Double? = { _, _ -> null }, log)`。`UnsentNote(..., headingDegrees: Double? = null)`（末尾）。`NoteBody(..., headingDegrees: Double? = null)`（末尾）。`pickHeadingSample`・`NOTE_RECENT_POINTS`・`MIN_SAMPLE_DISTANCE_M` などは消す。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/location/HeadingTest.kt b/app/src/test/java/com/touringproject/v2/location/HeadingTest.kt
index 817e54d..0bbda3e 100644
--- a/app/src/test/java/com/touringproject/v2/location/HeadingTest.kt
+++ b/app/src/test/java/com/touringproject/v2/location/HeadingTest.kt
@@ -1,51 +1,15 @@
 package com.touringproject.v2.location
 
-import com.touringproject.v2.api.HeadingSample
-import org.junit.Assert.assertEquals
-import org.junit.Assert.assertNull
 import org.junit.Assert.assertTrue
 import org.junit.Test
 
 class HeadingTest {
   private val here = Fix(35.6812, 139.7671, 100_000, 5.0)
   private val behind = Fix(35.6806, 139.7671, 90_000, 5.0) // about 67 m south
-  private val near = Fix(35.68119, 139.7671, 95_000, 5.0) // about 1 m
 
   @Test
   fun distance() {
     val d = distanceMeters(behind, here)
     assertTrue(d in 60.0..75.0)
   }
-
-  @Test
-  fun picks_the_newest_point_far_enough_behind() {
-    val older = behind.copy(timestamp = 80_000)
-    assertEquals(HeadingSample(35.6806, 139.7671, "1970-01-01T00:01:30Z"), pickHeadingSample(listOf(older, behind, near, here), here))
-  }
-
-  @Test
-  fun test_no_sample_when_stationary() {
-    assertNull(pickHeadingSample(listOf(near, here), here))
-  }
-
-  @Test
-  fun ignores_points_older_than_a_minute_and_points_not_before_the_current_one() {
-    assertNull(pickHeadingSample(listOf(behind.copy(timestamp = 30_000)), here))
-    assertNull(pickHeadingSample(listOf(behind.copy(timestamp = 100_000)), here))
-  }
-
-  @Test
-  fun test_no_sample_from_inaccurate_points() {
-    assertNull(pickHeadingSample(listOf(behind.copy(accuracy = 30.0)), here))
-  }
-
-  @Test
-  fun no_sample_when_the_current_point_itself_is_inaccurate() {
-    assertNull(pickHeadingSample(listOf(behind), here.copy(accuracy = 30.0)))
-  }
-
-  @Test
-  fun unknown_accuracy_is_accepted() {
-    assertEquals(35.6806, pickHeadingSample(listOf(behind.copy(accuracy = null)), here.copy(accuracy = null))!!.latitude, 0.0)
-  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/records/NotesTest.kt b/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
index a33dd96..c3b144b 100644
--- a/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
+++ b/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
@@ -6,30 +6,16 @@ import org.junit.Assert.assertNull
 import org.junit.Test
 
 class NotesTest {
-  private fun p(t: Long, lat: Double, lon: Double, accuracy: Double? = 5.0) = RoutePoint(0, t, lat, lon, accuracy)
-
-  // Slice 3 spec §4.3: the newest point is the place, and an older one far enough back is the heading's sample.
+  // Slice 3 spec §4.3: the newest point is the place; slice 5 spec §4: the heading is the device's.
   @Test
-  fun a_memo_is_at_the_newest_point_with_an_older_one_for_the_heading() {
-    val recent = listOf(p(1_000, 35.000, 139.000), p(30_000, 35.001, 139.000), p(55_000, 35.002, 139.000), p(60_000, 35.0201, 139.000))
-    val draft = noteDraft("n1", "r1", 70_000, recent)
-    assertEquals(NoteDraft("n1", "r1", 70_000, 35.0201, 139.000, 35.002, 139.000, 55_000), draft)
+  fun a_memo_is_at_the_newest_point_with_the_devices_heading() {
+    val draft = noteDraft("n1", "r1", 70_000, RoutePoint(0, 60_000, 35.0201, 139.0, 5.0), 271.5)
+    assertEquals(NoteDraft("n1", "r1", 70_000, 35.0201, 139.0, 271.5), draft)
   }
 
   @Test
   fun without_a_point_the_memo_has_no_place() {
-    assertEquals(NoteDraft("n1", "r1", 70_000, null, null, null, null, null), noteDraft("n1", "r1", 70_000, emptyList()))
-  }
-
-  // The same rules as an ask's sample: none closer than 15 m, older than a minute, or from a poor fix.
-  @Test
-  fun the_heading_sample_is_left_out_when_no_older_point_will_do() {
-    val near = listOf(p(50_000, 35.0000, 139.0), p(60_000, 35.0001, 139.0))
-    assertNull(noteDraft("n1", "r1", 70_000, near).sampleAt)
-    val old = listOf(p(1_000, 35.0, 139.0), p(90_000, 35.01, 139.0))
-    assertNull(noteDraft("n1", "r1", 95_000, old).sampleAt)
-    val poor = listOf(p(50_000, 35.0, 139.0, accuracy = 80.0), p(60_000, 35.01, 139.0))
-    assertNull(noteDraft("n1", "r1", 70_000, poor).sampleAt)
+    assertEquals(NoteDraft("n1", "r1", 70_000, null, null, null), noteDraft("n1", "r1", 70_000, null, null))
   }
 
   @Test
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
index eaeb177..8c12902 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
@@ -4,6 +4,7 @@ import android.app.Application
 import androidx.room.Room
 import androidx.test.core.app.ApplicationProvider
 import androidx.test.ext.junit.runners.AndroidJUnit4
+import com.touringproject.v2.location.Fix
 import com.touringproject.v2.records.NoteDraft
 import com.touringproject.v2.records.NoteRecord
 import com.touringproject.v2.ride.EndReason
@@ -31,7 +32,11 @@ class RoomNotesTest {
   private var now = 5_000L
   private var changes = 0
   private val errors = mutableListOf<String>()
-  private val notes = RoomNotes(db.notes(), db.rides(), { now }, { "n1" }, { changes += 1 }) { message, _ -> errors += message }
+  private val headingAsked = mutableListOf<Pair<Fix?, Long>>()
+  private val notes = RoomNotes(
+    db.notes(), db.rides(), { now }, { "n1" }, { changes += 1 },
+    heading = { here, at -> headingAsked += here to at; 271.5 },
+  ) { message, _ -> errors += message }
   private val records = RoomRecords(db.rides(), db.asks(), db.notes())
   private val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)
 
@@ -42,26 +47,28 @@ class RoomNotesTest {
     buildList { while (c.moveToNext()) add(DeletionEntity(c.getString(0), c.getString(1), c.getString(2), c.getLong(3))) }
   }
 
-  private val draft = NoteDraft("n1", "r1", 4_000, 35.02, 139.0, 35.0, 139.0, 3_000)
+  private val draft = NoteDraft("n1", "r1", 4_000, 35.02, 139.0, 90.0)
 
-  // Slice 3 spec §4.3: the memo opened now is at the ride's newest point; nothing is written until it is saved.
+  // Slice 3 spec §4.3: the memo opened now is at the ride's newest point; nothing is written until it is saved. Slice 5
+  // spec §4.1: its heading is the route's, at that point, as of when it was opened.
   @Test
-  fun a_draft_is_at_the_rides_newest_point_and_writes_nothing() = runBlocking {
+  fun a_draft_is_at_the_rides_newest_point_with_the_routes_heading_and_writes_nothing() = runBlocking {
     rides.save(ride)
     rides.addPoint("r1", RoutePoint(0, 2_000, 35.0, 139.0, 5.0), 0.0, 2_000)
     rides.addPoint("r1", RoutePoint(0, 3_000, 35.01, 139.0, 5.0), 0.0, 3_000)
-    assertEquals(NoteDraft("n1", "r1", 5_000, 35.01, 139.0, 35.0, 139.0, 2_000), notes.draft("r1"))
+    assertEquals(NoteDraft("n1", "r1", 5_000, 35.01, 139.0, 271.5), notes.draft("r1"))
+    assertEquals(listOf<Pair<Fix?, Long>>(Fix(35.01, 139.0, 3_000, 5.0) to 5_000L), headingAsked)
     assertEquals(emptyList<NoteRecord>(), records.notes("r1").first())
   }
 
   @Test
-  fun a_saved_memo_keeps_its_place_and_time_and_is_something_to_send() = runBlocking {
+  fun a_saved_memo_keeps_its_place_time_and_heading_and_is_something_to_send() = runBlocking {
     rides.save(ride)
     assertTrue(notes.create(draft, "展望スペース"))
     val kept = db.notes().note("n1")!!
     assertEquals(listOf(4_000L, 5_000L), listOf(kept.at, kept.updatedAt))
-    assertEquals(listOf(35.02, 139.0, 35.0, 139.0), listOf(kept.latitude, kept.longitude, kept.sampleLatitude, kept.sampleLongitude))
-    assertEquals(3_000L, kept.sampleAt)
+    assertEquals(listOf(35.02, 139.0, 90.0), listOf(kept.latitude, kept.longitude, kept.headingDegrees))
+    assertEquals(listOf(null, null, null), listOf(kept.sampleLatitude, kept.sampleLongitude, kept.sampleAt))
     assertNull(kept.sentUpdatedAt)
     assertEquals(1, changes)
     assertEquals(listOf(NoteRecord("n1", "r1", 4_000, 35.02, 139.0, "展望スペース", null, sent = false)), records.notes("r1").first())
@@ -141,7 +148,7 @@ class RoomNotesTest {
       override suspend fun lastPoints(rideId: String, count: Int): List<RoutePointEntity> = throw IOException("disk")
     }
     val notes = RoomNotes(db.notes(), failing, { now }, { "n1" }, { changes += 1 }) { message, _ -> errors += message }
-    assertEquals(NoteDraft("n1", "r1", 5_000, null, null, null, null, null), notes.draft("r1"))
+    assertEquals(NoteDraft("n1", "r1", 5_000, null, null, null), notes.draft("r1"))
     assertEquals(1, errors.size)
   }
 
diff --git a/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt b/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
index fb43e86..3d548a3 100644
--- a/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
@@ -81,6 +81,14 @@ class SyncPlanTest {
     assertNull(bare.headingSample)
   }
 
+  // Slice 5 spec §4.4: a memo written since slice 5 goes with the device's heading and no sample.
+  @Test
+  fun a_point_memo_goes_with_the_devices_heading() {
+    val body = UnsentNote("n1", "r1", 1_000, 35.3, 138.9, null, null, null, "展望スペース", 2_000, 90.0).toBody()
+    assertEquals(90.0, body.headingDegrees!!, 0.0)
+    assertNull(body.headingSample)
+  }
+
   // Slice 5 spec §4.4: an unreached ask goes with the device's heading; one kept before slice 5 still has its sample.
   @Test
   fun an_unreached_ask_goes_with_its_heading_and_an_old_one_with_its_sample() {
diff --git a/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt b/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
index 880f357..68a7dba 100644
--- a/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
@@ -50,7 +50,7 @@ class NoteRoutesTest {
   private val records = RoomRecords(db.rides(), db.asks(), db.notes())
   private val notes = RoomNotes(db.notes(), db.rides(), { 5_000 }, { "n1" }, {}) { _, _ -> }
   private var closed = 0
-  private val draft = NoteDraft("n1", "r1", 4_000, 35.3, 138.9, null, null, null)
+  private val draft = NoteDraft("n1", "r1", 4_000, 35.3, 138.9, null)
 
   @After
   fun close() = db.close()
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
index 908181f..5f7c532 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
@@ -228,7 +228,7 @@ class RecordLabelsTest {
   // SC-19: when, where and which ride; the address comes from the Backend once the memo has gone (slice 3 spec §7.3).
   @Test
   fun sc_19_says_when_where_and_for_which_ride() {
-    val draft = NoteDraft("n1", "r1", ms(22, 10, 24), 35.3, 138.9, null, null, null)
+    val draft = NoteDraft("n1", "r1", ms(22, 10, 24), 35.3, 138.9, null)
     assertEquals(
       NoteHeaderUi("10月22日（木） 10:24 · 今いる地点", "📍 住所は送ったあとに付きます", "走行「箱根」に入ります"),
       newNoteHeader(draft, "箱根", zone),
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*NotesTest' --tests '*RoomNotesTest'`
Expected: コンパイルで落ちる（`NoteDraft` の項目・`RoomNotes` の `heading`・`UnsentNote.headingDegrees` が合わない）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 070253a..ba89fbd 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -158,11 +158,6 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   /** SC-07 and SC-08 change kept asks through here; each change is something new to send (slice 3 spec §5.1). */
   val askEdits = RoomAskEdits(database.asks(), System::currentTimeMillis, sync::request) { message, e -> Log.w("trv2.ask", message, e) }
 
-  /** SC-19 writes point memos through here; each change is something new to send (slice 3 spec §5.1). */
-  val notes = RoomNotes(database.notes(), database.rides(), System::currentTimeMillis, { UUID.randomUUID().toString() }, sync::request) { message, e ->
-    Log.w("trv2.note", message, e)
-  }
-
   val rides = RideController(
     RideDeps(
       now = System::currentTimeMillis,
@@ -188,6 +183,12 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     log = { message, e -> Log.w("trv2.ride", message, e) },
   )
 
+  /** SC-19 writes point memos through here; each change is something new to send (slice 3 spec §5.1). */
+  val notes = RoomNotes(
+    database.notes(), database.rides(), System::currentTimeMillis, { UUID.randomUUID().toString() }, sync::request,
+    heading = { here, now -> routeHeading.find(here, now).degrees },
+  ) { message, e -> Log.w("trv2.note", message, e) }
+
   /** How many asks the device keeps for the ride recording or paused (SC-02, SC-04; Android #35). */
   val activeAskCount: StateFlow<Int> =
     activeAskCount(rides.active.map { it?.id }, database.asks()::countForRide).stateIn(scope, SharingStarted.Eagerly, 0)
diff --git a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
index 48b18cb..bfc3f3c 100644
--- a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
+++ b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
@@ -104,9 +104,19 @@ data class RideBody(
 /** A conversation's memo (slice 3 spec §6.2); null removes it. */
 @Serializable data class AskMemoBody(val memo: String?, val updatedAt: String)
 
-/** A point memo as a whole (slice 3 spec §6.2). location is null for one opened before its ride had a point. */
+/**
+ * A point memo as a whole (slice 3 spec §6.2). location is null for one opened before its ride had a point.
+ * headingDegrees and headingSample are as an unreached ask's (OfflineAskBody).
+ */
 @Serializable
-data class NoteBody(val at: String, val location: Point?, val headingSample: HeadingSample?, val text: String, val updatedAt: String)
+data class NoteBody(
+  val at: String,
+  val location: Point?,
+  val headingSample: HeadingSample?,
+  val text: String,
+  val updatedAt: String,
+  val headingDegrees: Double? = null,
+)
 
 /** What the Backend settled for a point memo when it first took it; null when it could not tell (no place, no heading). */
 @Serializable data class NoteSaved(val address: String? = null, val headingDegrees: Double? = null)
diff --git a/app/src/main/java/com/touringproject/v2/location/Heading.kt b/app/src/main/java/com/touringproject/v2/location/Heading.kt
index adcfd76..c37248f 100644
--- a/app/src/main/java/com/touringproject/v2/location/Heading.kt
+++ b/app/src/main/java/com/touringproject/v2/location/Heading.kt
@@ -1,7 +1,5 @@
 package com.touringproject.v2.location
 
-import com.touringproject.v2.api.HeadingSample
-import java.time.Instant
 import kotlin.math.asin
 import kotlin.math.atan2
 import kotlin.math.cos
@@ -67,13 +65,6 @@ fun findHeading(route: List<Fix>, here: Fix?, now: Long, params: HeadingParams):
   return HeadingResult.Found(bearingDegrees(reference, here), reference, distanceMeters(reference, here))
 }
 
-const val MIN_SAMPLE_DISTANCE_M = 15.0
-const val MAX_SAMPLE_AGE_MS = 60_000L
-// GPS jitter of a stationary phone can exceed MIN_SAMPLE_DISTANCE_M with poor fixes.
-const val MAX_ACCURACY_M = 20.0
-
-private fun accurate(f: Fix) = f.accuracy == null || f.accuracy <= MAX_ACCURACY_M
-
 fun distanceMeters(a: Fix, b: Fix): Double {
   val r = 6_371_000.0
   fun rad(d: Double) = Math.toRadians(d)
@@ -82,16 +73,3 @@ fun distanceMeters(a: Fix, b: Fix): Double {
   val h = sin(dLat / 2).pow(2) + cos(rad(a.latitude)) * cos(rad(b.latitude)) * sin(dLon / 2).pow(2)
   return 2 * r * asin(sqrt(h))
 }
-
-fun pickHeadingSample(fixes: List<Fix>, current: Fix): HeadingSample? {
-  if (!accurate(current)) return null
-  val newest = fixes
-    .filter {
-      accurate(it) &&
-        it.timestamp < current.timestamp &&
-        current.timestamp - it.timestamp <= MAX_SAMPLE_AGE_MS &&
-        distanceMeters(it, current) >= MIN_SAMPLE_DISTANCE_M
-    }
-    .maxByOrNull { it.timestamp } ?: return null
-  return HeadingSample(newest.latitude, newest.longitude, Instant.ofEpochMilli(newest.timestamp).toString())
-}
diff --git a/app/src/main/java/com/touringproject/v2/records/Notes.kt b/app/src/main/java/com/touringproject/v2/records/Notes.kt
index ec00298..6fb33ca 100644
--- a/app/src/main/java/com/touringproject/v2/records/Notes.kt
+++ b/app/src/main/java/com/touringproject/v2/records/Notes.kt
@@ -1,10 +1,8 @@
 package com.touringproject.v2.records
 
 import com.touringproject.v2.location.Fix
-import com.touringproject.v2.location.pickHeadingSample
 import com.touringproject.v2.ride.RoutePoint
 import kotlinx.serialization.Serializable
-import java.time.Instant
 
 // Point memos (US-D-08, SC-19). One is written while a ride records or is paused, at the place the ride has reached,
 // and belongs to that ride. Its text follows the memos' rules (Memos.kt), but it cannot be empty.
@@ -26,8 +24,8 @@ data class NoteRecord(
 )
 
 /**
- * A point memo opened from Home and not yet saved: when it was opened and where the ride was then, with the older
- * point the Backend works the heading out from (slice 3 spec §4.3). Nothing is written until it is saved. Serializable:
+ * A point memo opened from Home and not yet saved: when it was opened, where the ride was then, and the heading the
+ * device worked out there (slice 3 spec §4.3, slice 5 spec §4). Nothing is written until it is saved. Serializable:
  * SC-19 keeps it in its key, so the memo stays where it was opened when the activity is recreated.
  */
 @Serializable
@@ -37,27 +35,18 @@ data class NoteDraft(
   val at: Long,
   val latitude: Double?,
   val longitude: Double?,
-  val sampleLatitude: Double?,
-  val sampleLongitude: Double?,
-  val sampleAt: Long?,
+  val headingDegrees: Double? = null,
 )
 
 /** The text a point memo keeps: trimmed, and none when it is blank (SC-19 does not save an empty one). */
 fun noteText(input: String): String? = memoText(input)
 
-/** How many of the ride's last points are read for a memo's place: 30 at the route's 5 s cover the sample's minute. */
-const val NOTE_RECENT_POINTS = 30
+/** The ride's newest point as the place a memo is written at (slice 3 spec §4.3). */
+fun RoutePoint.toFix() = Fix(lat, lon, t, accuracy)
 
-/**
- * A memo opened at at, given the ride's last points (oldest first): the newest point is its place, and its heading
- * sample is picked from the others as an ask's is (07 UC-5). Without a point it has no place.
- */
-fun noteDraft(id: String, rideId: String, at: Long, recent: List<RoutePoint>): NoteDraft {
-  val newest = recent.maxByOrNull { it.t } ?: return NoteDraft(id, rideId, at, null, null, null, null, null)
-  val fixes = recent.map { Fix(it.lat, it.lon, it.t, it.accuracy) }
-  val sample = pickHeadingSample(fixes, Fix(newest.lat, newest.lon, newest.t, newest.accuracy))
-  return NoteDraft(id, rideId, at, newest.lat, newest.lon, sample?.latitude, sample?.longitude, sample?.let { Instant.parse(it.at).toEpochMilli() })
-}
+/** A memo opened at at: the ride's newest point is its place. Without a point it has no place. */
+fun noteDraft(id: String, rideId: String, at: Long, newest: RoutePoint?, headingDegrees: Double?) =
+  NoteDraft(id, rideId, at, newest?.lat, newest?.lon, headingDegrees)
 
 /** SC-19's voice input: what was heard goes at the end of what is written, on a line of its own, within 2000 characters. */
 fun appendHeard(current: String, heard: String): String =
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 84bf304..5ff91ec 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -123,7 +123,10 @@ data class AskEntity(
   val updatedAt: Long? = null,
   val sentUpdatedAt: Long? = null,
   val rejectedUpdatedAt: Long? = null,
-  /** The older point the Backend takes an unreached ask's heading from; null when there was none. */
+  /**
+   * The older point the Backend took an unreached ask's heading from, on asks kept before slice 5 only; since then the
+   * device's heading is in headingDegrees (slice 5 spec §4.4).
+   */
   val sampleLatitude: Double? = null,
   val sampleLongitude: Double? = null,
   val sampleAt: Long? = null,
@@ -131,8 +134,9 @@ data class AskEntity(
 
 /**
  * A point memo (slice 3 spec §4.1, US-D-08). Written while its ride records or is paused, and gone with the ride. The
- * place it was written at is null when the ride had no point yet; the sample is the older point the Backend takes the
- * heading from. address and headingDegrees are what the Backend answered; null until it has.
+ * place it was written at is null when the ride had no point yet. headingDegrees is the device's heading (slice 5 spec
+ * §4.4) until the Backend answers the one it settled; the sample is left only on memos kept before slice 5. address is
+ * what the Backend answered; null until it has.
  */
 @Entity(
   tableName = "notes",
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt b/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt
index 78a4641..2aab933 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt
@@ -1,15 +1,17 @@
 package com.touringproject.v2.store
 
-import com.touringproject.v2.records.NOTE_RECENT_POINTS
+import com.touringproject.v2.location.Fix
 import com.touringproject.v2.records.NoteDraft
 import com.touringproject.v2.records.NoteEdits
 import com.touringproject.v2.records.memoFits
 import com.touringproject.v2.records.noteDraft
+import com.touringproject.v2.records.toFix
 import kotlinx.coroutines.CancellationException
 
 /**
  * Point memos in Room. Like RoomAskEdits, a change that was written is something new to send (changed), and a failed
- * write is logged and reported as false, so SC-19 can say so and keep what was typed (slice 3 spec §8).
+ * write is logged and reported as false, so SC-19 can say so and keep what was typed (slice 3 spec §8). heading is the
+ * ride's route's heading at the memo's place, as of when it was opened (slice 5 spec §4.1).
  */
 class RoomNotes(
   private val notes: NoteDao,
@@ -17,20 +19,21 @@ class RoomNotes(
   private val now: () -> Long,
   private val newId: () -> String,
   private val changed: () -> Unit,
+  private val heading: suspend (here: Fix?, now: Long) -> Double? = { _, _ -> null },
   private val log: (String, Throwable) -> Unit,
 ) : NoteEdits {
   override suspend fun draft(rideId: String): NoteDraft {
     val at = now()
     // A memo whose points cannot be read is still opened, without a place.
-    val recent = try {
-      rides.lastPoints(rideId, NOTE_RECENT_POINTS).map { it.toPoint() }
+    val newest = try {
+      rides.lastPoints(rideId, 1).firstOrNull()?.toPoint()
     } catch (e: CancellationException) {
       throw e
     } catch (e: Exception) {
       log("note_points_failed rideId=$rideId", e)
-      emptyList()
+      null
     }
-    return noteDraft(newId(), rideId, at, recent)
+    return noteDraft(newId(), rideId, at, newest, heading(newest?.toFix(), at))
   }
 
   override suspend fun create(draft: NoteDraft, text: String): Boolean =
@@ -63,13 +66,14 @@ private fun NoteDraft.toEntity(text: String, at: Long) = NoteEntity(
   at = this.at,
   latitude = latitude,
   longitude = longitude,
-  sampleLatitude = sampleLatitude,
-  sampleLongitude = sampleLongitude,
-  sampleAt = sampleAt,
+  sampleLatitude = null,
+  sampleLongitude = null,
+  sampleAt = null,
   text = text,
   updatedAt = at,
   sentUpdatedAt = null,
   rejectedUpdatedAt = null,
   address = null,
-  headingDegrees = null,
+  // The device's heading until the Backend answers the one it settled (slice 5 spec §4.4).
+  headingDegrees = headingDegrees,
 )
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
index a61ce59..f0c30f5 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
@@ -41,7 +41,7 @@ class RoomSyncStore(
   override suspend fun askMemoRefused(askId: String, updatedAt: Long) = asks.markMemoRefused(askId, updatedAt)
 
   override suspend fun unsentNotes(): List<UnsentNote> = notes.unsent().map {
-    UnsentNote(it.id, it.rideId, it.at, it.latitude, it.longitude, it.sampleLatitude, it.sampleLongitude, it.sampleAt, it.text, it.updatedAt)
+    UnsentNote(it.id, it.rideId, it.at, it.latitude, it.longitude, it.sampleLatitude, it.sampleLongitude, it.sampleAt, it.text, it.updatedAt, it.headingDegrees)
   }
 
   override suspend fun noteSent(noteId: String, updatedAt: Long, address: String?, headingDegrees: Double?) =
diff --git a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
index 4505301..fedab71 100644
--- a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
@@ -35,7 +35,10 @@ data class PendingDeletion(val kind: String, val id: String, val rideId: String?
 /** A conversation's memo that has changed since the Backend last took it; memo null removes it. */
 data class UnsentAskMemo(val askId: String, val memo: String?, val updatedAt: Long)
 
-/** A point memo that has changed since the Backend last took it, as a whole; it goes as it is now (slice 3 spec §5.1). */
+/**
+ * A point memo that has changed since the Backend last took it, as a whole; it goes as it is now (slice 3 spec §5.1).
+ * headingDegrees and the sample are as an unreached ask's (UnsentUnreached).
+ */
 data class UnsentNote(
   val id: String,
   val rideId: String,
@@ -47,6 +50,7 @@ data class UnsentNote(
   val sampleAt: Long?,
   val text: String,
   val updatedAt: Long,
+  val headingDegrees: Double? = null,
 )
 
 /**
diff --git a/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt b/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
index 2117017..960cd36 100644
--- a/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
@@ -60,11 +60,14 @@ fun Ride.toBody() = RideBody(
 
 fun RoutePoint.toBody() = PointBody(iso(t), lat, lon, accuracy, segment)
 
-/** A memo opened before its ride had a point goes without a place; the sample goes only when it is whole. */
+/**
+ * A memo opened before its ride had a point goes without a place. Its heading goes as degrees; a sample (kept before
+ * slice 5) goes too while it is whole, and the Backend takes the heading first (slice 5 spec §4.4).
+ */
 fun UnsentNote.toBody(): NoteBody {
   val location = if (latitude != null && longitude != null) Point(latitude, longitude) else null
   val sample = if (sampleLatitude != null && sampleLongitude != null && sampleAt != null) HeadingSample(sampleLatitude, sampleLongitude, iso(sampleAt)) else null
-  return NoteBody(iso(at), location, sample, text, iso(updatedAt))
+  return NoteBody(iso(at), location, sample, text, iso(updatedAt), headingDegrees)
 }
 
 /**
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun`
Expected: PASS（618件。古い材料の選び方のテストを消した分、減る）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/records/Notes.kt app/src/main/java/com/touringproject/v2/store/RoomNotes.kt app/src/main/java/com/touringproject/v2/sync/RideSync.kt app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt app/src/main/java/com/touringproject/v2/api/ApiClient.kt app/src/main/java/com/touringproject/v2/location/Heading.kt app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/AppGraph.kt
cd $AND && git add app/src/test/java/com/touringproject/v2/location/HeadingTest.kt app/src/test/java/com/touringproject/v2/records/NotesTest.kt app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
git commit -m "feat: send the device's heading with point memos, and drop the heading samples"
```

---

### Task 5: 録音の上限と開始の合図を、質問と試し録りに効かせる（#7）

**Files:**
- Modify: `ask/AskController.kt`・`ask/AskPorts.kt`・`ask/Flow.kt`・`audio/ToneCues.kt`・`recordings/RecordingCheck.kt`・`recordings/Trial.kt`・`settings/Settings.kt`・`ui/AskOverlay.kt`・`AppGraph.kt`
- Test: `ask/AskControllerTest.kt`・`audio/AudioTest.kt`・`recordings/RecordingCheckTest.kt`・`recordings/TrialTest.kt`・`ui/LabelsTest.kt`

**Interfaces:**
- Consumes: Task 2 の `Settings.recordLimitMs`・`startCueMs`・`DEFAULT_START_CUE_MS`。
- Produces: `Cues.start(durationMs: Int)`（0 は鳴らさない）。`ToneCues.play(cue, durationMs = cue.durationMs)`。`const val DEFAULT_RECORD_LIMIT_MS`（`settings`。`RECORD_LIMIT_MS` は消す）。`FlowState.recordLimitMs`・`FlowEvent.Start(..., recordLimitMs)`。`TrialDeps(..., cueStart: (durationMs: Int) -> Unit, ..., recordLimitMs: () -> Long, startCueMs: () -> Int)`（後ろの2つは既定値つき）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index 68d78f5..0ffd6ea 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -14,6 +14,7 @@ import com.touringproject.v2.location.Fix
 import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.newRide
 import com.touringproject.v2.ride.pause
+import com.touringproject.v2.settings.DEFAULT_RECORD_LIMIT_MS
 import com.touringproject.v2.settings.LaunchableApp
 import com.touringproject.v2.settings.ReturnTiming
 import com.touringproject.v2.settings.Settings
@@ -47,6 +48,8 @@ private class Harness(
   val scope: TestScope,
   var apiKey: String? = "key",
   val settings: Settings = SETTINGS,
+  /** Read at every use, so a test can change the settings between asks. */
+  val settingsOf: () -> Settings = { settings },
   var post: suspend () -> AskAccepted = { ACCEPTED },
   answers: List<Any> = listOf(done()),
   val routeOk: Boolean = true,
@@ -67,6 +70,8 @@ private class Harness(
 ) {
   /** Where and when the heading was asked for. */
   val headingAsked = mutableListOf<Pair<Fix?, Long>>()
+  /** How long each start cue was asked to sound. */
+  val startCues = mutableListOf<Int>()
   val log = mutableListOf<String>()
   val states = mutableListOf<FlowState>()
   val bodies = mutableListOf<AskBody>()
@@ -99,7 +104,7 @@ private class Harness(
       delay(ms)
       if (stopAfterMs != null && controller.state.phase == Phase.RECORDING && now() >= stopAfterMs) controller.stopRecording()
     },
-    settings = { settings },
+    settings = settingsOf,
     apiKey = { apiKey },
     micAllowed = { micAllowed },
     mediaVolume = { log += "vol:read"; MediaVolume(2, 25) },
@@ -136,7 +141,7 @@ private class Harness(
       override suspend fun returnTo(packageName: String): Boolean { log += "return:$packageName"; return true }
     },
     cues = object : Cues {
-      override fun start() { log += "cue:start" }
+      override fun start(durationMs: Int) { log += "cue:start"; startCues += durationMs }
       override fun sent() { log += "cue:sent" }
       override fun waiting() { log += "cue:waiting" }
       override fun failure() { log += "cue:failure" }
@@ -219,7 +224,28 @@ class AskControllerTest {
     val h = Harness(this, stopAfterMs = null)
     h.controller.run(Source.HANDSFREE)
     assertTrue("post" in h.log)
-    assertTrue(h.now() >= RECORD_LIMIT_MS)
+    assertTrue(h.now() >= DEFAULT_RECORD_LIMIT_MS)
+    assertEquals(listOf(1_500), h.startCues)
+    assertEquals(DEFAULT_RECORD_LIMIT_MS, h.states.first().recordLimitMs)
+  }
+
+  // Slice 5 spec §6: SC-11's limit and start cue as they are when the ask starts; SC-03 counts down from that limit.
+  @Test
+  fun the_recording_limit_and_start_cue_come_from_sc_11() = runTest {
+    var settings = SETTINGS.copy(recordLimitSeconds = 10, startCueMs = 0)
+    val h = Harness(this, stopAfterMs = null, settingsOf = { settings })
+    // How long each ask recorded: from its start to its SENDING.
+    fun recorded() = h.states.filter { it.phase == Phase.RECORDING || it.phase == Phase.SENDING }
+      .zipWithNext { a, b -> if (a.phase == Phase.RECORDING && b.phase == Phase.SENDING) b.phaseStartedAt - a.phaseStartedAt else null }
+      .filterNotNull()
+    h.controller.run(Source.HANDSFREE)
+    assertEquals(listOf(10_000L), recorded())
+    assertEquals(listOf(0), h.startCues)
+    assertEquals(10_000L, h.states.first().recordLimitMs)
+    settings = SETTINGS.copy(recordLimitSeconds = 45, startCueMs = 3_000)
+    h.controller.run(Source.HANDSFREE)
+    assertEquals(listOf(10_000L, 45_000L), recorded())
+    assertEquals(listOf(0, 3_000), h.startCues)
   }
 
   @Test
@@ -305,7 +331,7 @@ class AskControllerTest {
     h.until { "rec:start" in h.log }
     h.controller.press()
     running.join()
-    assertTrue(h.now() < RECORD_LIMIT_MS)
+    assertTrue(h.now() < DEFAULT_RECORD_LIMIT_MS)
   }
 
   @Test
diff --git a/app/src/test/java/com/touringproject/v2/audio/AudioTest.kt b/app/src/test/java/com/touringproject/v2/audio/AudioTest.kt
index 7225a16..80e8b98 100644
--- a/app/src/test/java/com/touringproject/v2/audio/AudioTest.kt
+++ b/app/src/test/java/com/touringproject/v2/audio/AudioTest.kt
@@ -62,6 +62,21 @@ class CueTest {
   }
 }
 
+// SC-11: the start cue sounds as long as chosen, and not at all for 「なし」.
+@RunWith(AndroidJUnit4::class)
+class ToneCuesTest {
+  @Test
+  fun the_start_cue_takes_the_chosen_length_and_none_sounds_nothing() {
+    val streams = mutableListOf<Int>()
+    // The generator is made per cue; failing here keeps the test off the real ToneGenerator.
+    val cues = ToneCues { stream -> streams += stream; throw RuntimeException("no tone in tests") }
+    cues.start(0)
+    assertEquals(emptyList<Int>(), streams)
+    cues.start(500)
+    assertEquals(listOf(AudioManager.STREAM_VOICE_CALL), streams)
+  }
+}
+
 @RunWith(AndroidJUnit4::class)
 class AudioRouteTest {
   private val context = ApplicationProvider.getApplicationContext<Context>()
diff --git a/app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt b/app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt
index ffd5d8b..8fe25c1 100644
--- a/app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt
+++ b/app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt
@@ -25,7 +25,8 @@ private fun meta(time: Long) = RecordingMeta("rec-$time.pcm", time, 1_000, false
 class RecordingCheckTest {
   @get:Rule val folder = TemporaryFolder()
 
-  private class World(scope: TestScope, dir: File, var askBusy: Boolean = false, val playError: Exception? = null) {
+  /** routeMs: how long setting up the route takes (SCO takes up to 3 s on the phone). */
+  private class World(scope: TestScope, dir: File, var askBusy: Boolean = false, val playError: Exception? = null, val routeMs: Long = 0) {
     val log = mutableListOf<String>()
     var playGate: CompletableDeferred<Unit>? = null
     val store = RecordingStore(dir, io = StandardTestDispatcher(scope.testScheduler))
@@ -46,12 +47,15 @@ class RecordingCheckTest {
         sleep = { delay(it) },
         micAllowed = { true },
         route = object : RouteControl {
-          override suspend fun start(source: Source) = true
-          override suspend fun stop() = Unit
+          override suspend fun start(source: Source): Boolean {
+            if (routeMs > 0) delay(routeMs)
+            return true
+          }
+          override suspend fun stop() { log += "route:stop" }
           override fun inputDevice() = null
         },
         recorder = object : Recorder {
-          override suspend fun start() = Unit
+          override suspend fun start() { log += "rec:start" }
           override suspend fun stop() = Recorded(byteArrayOf(9), "trial.pcm")
           override suspend fun cancel() = Unit
         },
@@ -162,7 +166,19 @@ class RecordingCheckTest {
     assertTrue(w.trial.active)
     w.check.toggleTrial()
     testScheduler.advanceUntilIdle()
-    assertEquals(listOf("cue:start", "trial:play"), w.log)
+    assertEquals(listOf("rec:start", "cue:start", "route:stop", "trial:play"), w.log)
+    assertEquals(TrialPhase.IDLE, w.trial.state.phase)
+  }
+
+  // Android #7: SC-12 left right after 試し録り, before the trial got going: no cue, no microphone, after the screen.
+  @Test
+  fun leaving_right_after_the_trial_button_starts_nothing_later() = runTest {
+    val w = World(this, folder.root, routeMs = 3_000)
+    w.check.toggleTrial()
+    w.check.leave()
+    testScheduler.advanceUntilIdle()
+    // The cancel stops the trial's player, and the route set up meanwhile is given back.
+    assertEquals(listOf("trial:stop", "route:stop"), w.log)
     assertEquals(TrialPhase.IDLE, w.trial.state.phase)
   }
 }
diff --git a/app/src/test/java/com/touringproject/v2/recordings/TrialTest.kt b/app/src/test/java/com/touringproject/v2/recordings/TrialTest.kt
index 98018da..0f2b95f 100644
--- a/app/src/test/java/com/touringproject/v2/recordings/TrialTest.kt
+++ b/app/src/test/java/com/touringproject/v2/recordings/TrialTest.kt
@@ -1,11 +1,12 @@
 package com.touringproject.v2.recordings
 
-import com.touringproject.v2.ask.RECORD_LIMIT_MS
 import com.touringproject.v2.ask.Recorded
 import com.touringproject.v2.ask.Recorder
 import com.touringproject.v2.ask.RouteControl
 import com.touringproject.v2.ask.Source
 import com.touringproject.v2.audio.InputDevice
+import com.touringproject.v2.settings.DEFAULT_RECORD_LIMIT_MS
+import com.touringproject.v2.settings.DEFAULT_START_CUE_MS
 import kotlinx.coroutines.CompletableDeferred
 import kotlinx.coroutines.delay
 import kotlinx.coroutines.launch
@@ -29,8 +30,12 @@ private class TrialHarness(
   val pcm: ByteArray = byteArrayOf(1, 2),
   var playGate: CompletableDeferred<Unit>? = null,
   val playError: Exception? = null,
+  /** SC-11's values (slice 5 spec §6). */
+  val limitMs: Long = DEFAULT_RECORD_LIMIT_MS,
+  val cueMs: Int = DEFAULT_START_CUE_MS,
 ) {
   val log = mutableListOf<String>()
+  val cues = mutableListOf<Int>()
   val states = mutableListOf<TrialState>()
   val trial = TrialController(
     TrialDeps(
@@ -51,7 +56,7 @@ private class TrialHarness(
         override suspend fun stop(): Recorded { log += "rec:stop"; return Recorded(pcm, "trial.pcm") }
         override suspend fun cancel() { log += "rec:cancel" }
       },
-      cueStart = { log += "cue:start" },
+      cueStart = { log += "cue:start"; cues += it },
       player = object : PcmPlayback {
         override suspend fun play(pcm: ByteArray) {
           log += "play:${pcm.size}"
@@ -64,6 +69,8 @@ private class TrialHarness(
         }
       },
       onState = { states += it },
+      recordLimitMs = { limitMs },
+      startCueMs = { cueMs },
     ),
   )
 
@@ -98,7 +105,17 @@ class TrialTest {
     val h = TrialHarness(this)
     h.trial.start()
     assertTrue("play:2" in h.log)
-    assertTrue(testScheduler.currentTime >= RECORD_LIMIT_MS)
+    assertTrue(testScheduler.currentTime >= DEFAULT_RECORD_LIMIT_MS)
+    assertEquals(listOf(1_500), h.cues)
+  }
+
+  // US-E-03.001: the trial records with SC-11's limit and start cue, as a question does.
+  @Test
+  fun the_trial_takes_sc_11s_limit_and_cue() = runTest {
+    val h = TrialHarness(this, limitMs = 35_000, cueMs = 0)
+    h.trial.start()
+    assertTrue(testScheduler.currentTime in 35_000L until 36_000L)
+    assertEquals(listOf(0), h.cues)
   }
 
   @Test
diff --git a/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
index bf0675f..b88cba1 100644
--- a/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
@@ -119,6 +119,8 @@ class LabelsTest {
     assertEquals("17", recording.big)
     assertEquals("送らずにやめる", recording.button)
     assertEquals("0", overlayText(FlowState(phase = Phase.RECORDING), seconds = 25).big)
+    // SC-11: the countdown starts from the ask's own limit.
+    assertEquals("42", overlayText(FlowState(phase = Phase.RECORDING, recordLimitMs = 45_000), seconds = 3).big)
     assertEquals("12", overlayText(FlowState(phase = Phase.WAITING), seconds = 12).big)
     assertEquals("愛鷹山です。", overlayText(FlowState(phase = Phase.SPEAKING, answer = "愛鷹山です。"), 0).detail)
     assertEquals("時間切れです。もう一度お話しください。", overlayText(FlowState(phase = Phase.FAILED, failure = FailureReason.TIMEOUT), 0).title)
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*AskControllerTest' --tests '*TrialTest' --tests '*RecordingCheckTest'`
Expected: コンパイルで落ちる（`Cues.start(durationMs)`・`DEFAULT_RECORD_LIMIT_MS`・`FlowState.recordLimitMs` が無い）。#7 のテスト `leaving_right_after_the_trial_button_starts_nothing_later` は、コンパイルが通っても `UNDISPATCHED` が無いと落ちる（使い捨てのフォルダで確かめた）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index ba89fbd..459b70a 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -52,11 +52,13 @@ import com.touringproject.v2.service.RideNotices
 import com.touringproject.v2.service.ServiceCoordinator
 import com.touringproject.v2.settings.ApiKeyStore
 import com.touringproject.v2.settings.DEFAULT_MAX_RECORDING_HOURS
+import com.touringproject.v2.settings.DEFAULT_START_CUE_MS
 import com.touringproject.v2.settings.DataStoreKeyValueStore
 import com.touringproject.v2.settings.KeystoreCipher
 import com.touringproject.v2.settings.LastSaved
 import com.touringproject.v2.settings.SettingsRepository
 import com.touringproject.v2.settings.headingParams
+import com.touringproject.v2.settings.recordLimitMs
 import com.touringproject.v2.settings.maxRecordingChanges
 import com.touringproject.v2.store.RideDatabase
 import com.touringproject.v2.store.RoomAskEdits
@@ -245,6 +247,9 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       cueStart = cues::start,
       player = PcmPlayer(),
       onState = { trialFlow.value = it },
+      // SC-11's values, as a question takes them (US-E-03.001).
+      recordLimitMs = { settings.current().recordLimitMs },
+      startCueMs = { settings.current().startCueMs },
     ),
   )
 
@@ -270,7 +275,8 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       },
       route = AudioRouteControl(audioRoute),
       recorder = PcmRecorder(),
-      cueStart = cues::start,
+      // Not a question: SC-11 does not change SC-19's voice input (slice 5 spec §6).
+      cueStart = { cues.start(DEFAULT_START_CUE_MS) },
       cueFailure = cues::failure,
       onState = { voiceFlow.value = it },
       log = { event, data -> Log.i("trv2.note", "$event $data") },
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index 3279be3..f0a22c0 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -9,6 +9,7 @@ import com.touringproject.v2.api.Point
 import com.touringproject.v2.location.Fix
 import com.touringproject.v2.settings.ReturnTiming
 import com.touringproject.v2.settings.Settings
+import com.touringproject.v2.settings.recordLimitMs
 import kotlinx.coroutines.CancellationException
 import kotlinx.coroutines.CoroutineScope
 import kotlinx.coroutines.Deferred
@@ -16,7 +17,6 @@ import kotlinx.coroutines.async
 import kotlinx.coroutines.launch
 import java.util.Base64
 
-const val RECORD_LIMIT_MS = 20_000L
 const val TICK_MS = 250L
 const val WAITING_CUE_MS = 5_000L
 const val FAILED_SCREEN_MS = 5_000L
@@ -103,7 +103,9 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     val run = Run(++runId, source)
     current = run
     runsStarted += 1
-    dispatch(FlowEvent.Start(source, d.now(), d.mediaVolume()))
+    // SC-11's values as they are when the ask starts; a change takes effect from the next ask.
+    val atStart = d.settings()
+    dispatch(FlowEvent.Start(source, d.now(), d.mediaVolume(), atStart.recordLimitMs))
     try {
       // Slice 2 spec §4.7: only a recording ride takes asks. Read once, so pausing meanwhile neither stops the ask nor
       // takes it out of the ride.
@@ -139,7 +141,7 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
         return
       }
       serviceRunning = true
-      val recording = record(run) ?: return
+      val recording = record(run, atStart) ?: return
       // US-C-09: without a network the ask cannot be asked; when and where it was is kept instead (slice 4 spec §4.1).
       if (!d.online()) {
         keepUnreached(recording, rideId, run)
@@ -190,7 +192,7 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     }
   }
 
-  private suspend fun record(run: Run): Recording? {
+  private suspend fun record(run: Run, settings: Settings): Recording? {
     val d = deps
     d.location.begin()
     val routed = try {
@@ -218,9 +220,9 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       return null
     }
     // After the recorder is running: the rider starts talking on this cue, so nothing said after it is lost.
-    d.cues.start()
+    d.cues.start(settings.startCueMs)
     val startedAt = d.now()
-    while (state.phase == Phase.RECORDING && isCurrent(run) && d.now() - startedAt < RECORD_LIMIT_MS) {
+    while (state.phase == Phase.RECORDING && isCurrent(run) && d.now() - startedAt < settings.recordLimitMs) {
       d.sleep(TICK_MS)
     }
     if (!isCurrent(run)) {
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
index 99a60b0..8f6f586 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
@@ -66,7 +66,8 @@ interface NavReturn {
 }
 
 interface Cues {
-  fun start()
+  /** The start cue, durationMs long (SC-11); 0 sounds none. */
+  fun start(durationMs: Int)
   fun sent()
   fun waiting()
   fun failure()
diff --git a/app/src/main/java/com/touringproject/v2/ask/Flow.kt b/app/src/main/java/com/touringproject/v2/ask/Flow.kt
index 2ae98b0..86e8442 100644
--- a/app/src/main/java/com/touringproject/v2/ask/Flow.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/Flow.kt
@@ -1,6 +1,7 @@
 package com.touringproject.v2.ask
 
 import com.touringproject.v2.audio.MediaVolume
+import com.touringproject.v2.settings.DEFAULT_RECORD_LIMIT_MS
 import com.touringproject.v2.settings.ReturnTiming
 import com.touringproject.v2.settings.Settings
 
@@ -22,13 +23,20 @@ data class FlowState(
   val phaseStartedAt: Long = 0,
   // Read when the ask starts, before the intercom route switches the music stream to the call device's volume.
   val mediaVolume: MediaVolume? = null,
+  /** How long this ask may record (SC-11), for SC-03's countdown. */
+  val recordLimitMs: Long = DEFAULT_RECORD_LIMIT_MS,
 )
 
 val IDLE = FlowState()
 
 sealed interface FlowEvent {
   val now: Long
-  data class Start(val source: Source, override val now: Long, val mediaVolume: MediaVolume? = null) : FlowEvent
+  data class Start(
+    val source: Source,
+    override val now: Long,
+    val mediaVolume: MediaVolume? = null,
+    val recordLimitMs: Long = DEFAULT_RECORD_LIMIT_MS,
+  ) : FlowEvent
   data class PhoneMic(override val now: Long) : FlowEvent
   data class StopRecording(override val now: Long) : FlowEvent
   data class Sent(val askId: String, override val now: Long) : FlowEvent
@@ -41,7 +49,10 @@ sealed interface FlowEvent {
 fun reduce(state: FlowState, event: FlowEvent): FlowState = when (event) {
   is FlowEvent.Start ->
     if (state.phase == Phase.IDLE || state.phase == Phase.FAILED) {
-      FlowState(phase = Phase.RECORDING, source = event.source, phaseStartedAt = event.now, mediaVolume = event.mediaVolume)
+      FlowState(
+        phase = Phase.RECORDING, source = event.source, phaseStartedAt = event.now, mediaVolume = event.mediaVolume,
+        recordLimitMs = event.recordLimitMs,
+      )
     } else state
   is FlowEvent.PhoneMic -> if (state.phase == Phase.RECORDING) state.copy(phoneMic = true) else state
   is FlowEvent.StopRecording ->
diff --git a/app/src/main/java/com/touringproject/v2/audio/ToneCues.kt b/app/src/main/java/com/touringproject/v2/audio/ToneCues.kt
index 5b622a6..870a2c9 100644
--- a/app/src/main/java/com/touringproject/v2/audio/ToneCues.kt
+++ b/app/src/main/java/com/touringproject/v2/audio/ToneCues.kt
@@ -6,11 +6,13 @@ import android.os.Handler
 import android.os.Looper
 import android.util.Log
 import com.touringproject.v2.ask.Cues
+import com.touringproject.v2.settings.DEFAULT_START_CUE_MS
 
 enum class Cue(val tone: Int, val durationMs: Int, val stream: Int) {
-  // Intercoms drop the first part of a sound: a 1 s tone is heard as a short blip, so the start cue is longer.
-  // It plays on the voice-call stream, which is what the intercom hears while SCO is up.
-  START(ToneGenerator.TONE_SUP_DIAL, 1_500, AudioManager.STREAM_VOICE_CALL),
+  // Intercoms drop the first part of a sound: a 1 s tone is heard as a short blip, so the start cue is longer. The
+  // rider may change its length (SC-11); this is the default. It plays on the voice-call stream, which is what the
+  // intercom hears while SCO is up.
+  START(ToneGenerator.TONE_SUP_DIAL, DEFAULT_START_CUE_MS, AudioManager.STREAM_VOICE_CALL),
   // The rest play on the media stream: heard over the intercom's A2DP after returning to the nav app.
   SENT(ToneGenerator.TONE_DTMF_D, 800, AudioManager.STREAM_MUSIC),
   WAITING(ToneGenerator.TONE_DTMF_1, 600, AudioManager.STREAM_MUSIC),
@@ -21,20 +23,23 @@ enum class Cue(val tone: Int, val durationMs: Int, val stream: Int) {
 class ToneCues(private val makeGenerator: (stream: Int) -> ToneGenerator = { ToneGenerator(it, VOLUME) }) : Cues {
   private val main = Handler(Looper.getMainLooper())
 
-  fun play(cue: Cue): Boolean {
+  fun play(cue: Cue, durationMs: Int = cue.durationMs): Boolean {
     val generator = try {
       makeGenerator(cue.stream)
     } catch (e: RuntimeException) {
       Log.w(TAG, "ToneGenerator failed", e)
       return false
     }
-    val started = generator.startTone(cue.tone, cue.durationMs)
-    main.postDelayed({ generator.release() }, cue.durationMs + 200L)
+    val started = generator.startTone(cue.tone, durationMs)
+    main.postDelayed({ generator.release() }, durationMs + 200L)
     Log.i(TAG, "cue ${cue.name} started=$started")
     return started
   }
 
-  override fun start() { play(Cue.START) }
+  /** SC-11's 「なし」 is 0: no start cue at all. */
+  override fun start(durationMs: Int) {
+    if (durationMs > 0) play(Cue.START, durationMs)
+  }
   override fun sent() { play(Cue.SENT) }
   override fun waiting() { play(Cue.WAITING) }
   override fun failure() { play(Cue.FAILURE) }
diff --git a/app/src/main/java/com/touringproject/v2/recordings/RecordingCheck.kt b/app/src/main/java/com/touringproject/v2/recordings/RecordingCheck.kt
index 30e429a..bc52c1e 100644
--- a/app/src/main/java/com/touringproject/v2/recordings/RecordingCheck.kt
+++ b/app/src/main/java/com/touringproject/v2/recordings/RecordingCheck.kt
@@ -3,6 +3,7 @@ package com.touringproject.v2.recordings
 import com.touringproject.v2.ask.RecordingMeta
 import kotlinx.coroutines.CancellationException
 import kotlinx.coroutines.CoroutineScope
+import kotlinx.coroutines.CoroutineStart
 import kotlinx.coroutines.Job
 import kotlinx.coroutines.flow.MutableStateFlow
 import kotlinx.coroutines.flow.StateFlow
@@ -50,7 +51,8 @@ class RecordingCheck(
     }
     if (askBusy() || playingState.value != null) return
     messageState.value = null
-    scope.launch { trial.start() }
+    // Undispatched: the trial is RECORDING before this returns, so leaving SC-12 at once cancels it (Android #7).
+    scope.launch(start = CoroutineStart.UNDISPATCHED) { trial.start() }
   }
 
   fun play(name: String) {
diff --git a/app/src/main/java/com/touringproject/v2/recordings/Trial.kt b/app/src/main/java/com/touringproject/v2/recordings/Trial.kt
index 99873e5..f898bc1 100644
--- a/app/src/main/java/com/touringproject/v2/recordings/Trial.kt
+++ b/app/src/main/java/com/touringproject/v2/recordings/Trial.kt
@@ -1,11 +1,12 @@
 package com.touringproject.v2.recordings
 
-import com.touringproject.v2.ask.RECORD_LIMIT_MS
 import com.touringproject.v2.ask.Recorder
 import com.touringproject.v2.ask.RouteControl
 import com.touringproject.v2.ask.Source
 import com.touringproject.v2.ask.TICK_MS
 import com.touringproject.v2.audio.InputDevice
+import com.touringproject.v2.settings.DEFAULT_RECORD_LIMIT_MS
+import com.touringproject.v2.settings.DEFAULT_START_CUE_MS
 import kotlinx.coroutines.CancellationException
 
 // The trial recording on SC-12 (slice 1 spec §5.5): recorded over the same route as a question from the screen,
@@ -31,15 +32,18 @@ interface PcmPlayback {
   fun stop()
 }
 
+/** recordLimitMs and startCueMs are SC-11's, as for a question (US-E-03.001); cueStart sounds the start cue that long. */
 class TrialDeps(
   val now: () -> Long,
   val sleep: suspend (Long) -> Unit,
   val micAllowed: () -> Boolean,
   val route: RouteControl,
   val recorder: Recorder,
-  val cueStart: () -> Unit,
+  val cueStart: (durationMs: Int) -> Unit,
   val player: PcmPlayback,
   val onState: (TrialState) -> Unit,
+  val recordLimitMs: () -> Long = { DEFAULT_RECORD_LIMIT_MS },
+  val startCueMs: () -> Int = { DEFAULT_START_CUE_MS },
 )
 
 /** Call it from one thread only (the main thread in the app), like the ask loop. */
@@ -120,9 +124,10 @@ class TrialController(private val deps: TrialDeps) {
       d.route.stop()
       return
     }
-    d.cueStart()
+    d.cueStart(d.startCueMs())
     val startedAt = d.now()
-    while (isCurrent(session) && !stopRequested && d.now() - startedAt < RECORD_LIMIT_MS) d.sleep(TICK_MS)
+    val limitMs = d.recordLimitMs()
+    while (isCurrent(session) && !stopRequested && d.now() - startedAt < limitMs) d.sleep(TICK_MS)
     if (!isCurrent(session)) {
       d.recorder.cancel()
       d.route.stop()
diff --git a/app/src/main/java/com/touringproject/v2/settings/Settings.kt b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
index 9e932f2..d95eada 100644
--- a/app/src/main/java/com/touringproject/v2/settings/Settings.kt
+++ b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
@@ -38,6 +38,7 @@ const val DEFAULT_MAX_RECORDING_HOURS = 24
 // on SC-12 takes the same values; SC-19's voice input does not.
 val RECORD_LIMIT_SECONDS_CHOICES = (10..60 step 5).toList()
 const val DEFAULT_RECORD_LIMIT_SECONDS = 20
+const val DEFAULT_RECORD_LIMIT_MS = DEFAULT_RECORD_LIMIT_SECONDS * 1_000L
 val START_CUE_MS_CHOICES = listOf(0, 500, 1_000, 1_500, 2_000, 3_000)
 const val DEFAULT_START_CUE_MS = 1_500
 
diff --git a/app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt b/app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt
index 3d2d217..5af76db 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt
@@ -29,14 +29,13 @@ import androidx.compose.ui.unit.dp
 import androidx.compose.ui.unit.sp
 import com.touringproject.v2.ask.FlowState
 import com.touringproject.v2.ask.Phase
-import com.touringproject.v2.ask.RECORD_LIMIT_MS
 import com.touringproject.v2.ask.spokenMessage
 import kotlinx.coroutines.delay
 
 data class OverlayText(val title: String, val big: String, val detail: String, val button: String)
 
 fun overlayText(state: FlowState, seconds: Long): OverlayText = when (state.phase) {
-  Phase.RECORDING -> OverlayText("話してください", (RECORD_LIMIT_MS / 1000 - seconds).coerceAtLeast(0).toString(), "もう一度ボタンを押すか、ここを押すと送ります", "送らずにやめる")
+  Phase.RECORDING -> OverlayText("話してください", (state.recordLimitMs / 1000 - seconds).coerceAtLeast(0).toString(), "もう一度ボタンを押すか、ここを押すと送ります", "送らずにやめる")
   Phase.SENDING -> OverlayText("送っています…", "", "", "送らずにやめる")
   Phase.WAITING -> OverlayText("考えています…", seconds.toString(), "最初の質問は10秒ほど", "待つのをやめる")
   Phase.SPEAKING -> OverlayText("回答中", "", state.answer ?: "", "読み上げを止める")
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun`
Expected: PASS（622件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/ask/Flow.kt app/src/main/java/com/touringproject/v2/audio/ToneCues.kt app/src/main/java/com/touringproject/v2/recordings/RecordingCheck.kt app/src/main/java/com/touringproject/v2/recordings/Trial.kt app/src/main/java/com/touringproject/v2/settings/Settings.kt app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt app/src/main/java/com/touringproject/v2/AppGraph.kt
cd $AND && git add app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/audio/AudioTest.kt app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt app/src/test/java/com/touringproject/v2/recordings/TrialTest.kt app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
git commit -m "feat: take the recording limit and the start cue from the settings for asks and trials

Fixes #7"
```

---

### Task 6: SC-11 と設定の行

**Files:**
- Modify: `settings/Settings.kt`・`ui/SettingsScreens.kt`・`ui/Labels.kt`・`ui/AppUi.kt`
- Test: `settings/SettingsTest.kt`・`ui/ScreensTest.kt`・`ui/LabelsTest.kt`・`ui/AppUiTest.kt`

**Interfaces:**
- Consumes: Task 2 の選べる値。
- Produces: `fun Settings.withRecordingDefaults(): Settings`。`fun cueLabel(ms: Int): String`（「なし」「0.5秒」「1秒」…）・`fun recordingRowValue(settings): String`（「上限 20秒 · 合図 1.5秒」）。`@Composable fun RecordingSettingsScreen(settings, onUpdate, onReset, modifier)`（テストの印 `limitDown`・`limitValue`・`limitUp`・`cue-<ms>`・`recordingDefaults`）。`SettingsScreen(..., onRecordingSettings: () -> Unit = {})`。`RecordingSettingsKey`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
index 737c7f0..74e4852 100644
--- a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
@@ -97,6 +97,13 @@ class SettingsTest {
     assertEquals(Settings("rider01"), decodeSettings(odd).first)
   }
 
+  // SC-11's 「既定値に戻す」 puts back its two values only.
+  @Test
+  fun the_recording_defaults_leave_the_other_settings_as_they_are() {
+    val s = Settings("rider01", answerVolumeDb = 3, recordLimitSeconds = 45, startCueMs = 0, headingHoldMinutes = 2)
+    assertEquals(s.copy(recordLimitSeconds = 20, startCueMs = 1_500), s.withRecordingDefaults())
+  }
+
   @Test
   fun not_json_falls_back_to_defaults() {
     val (s, needsSave) = decodeSettings("{not json", Random(3))
diff --git a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
index 6588c5f..d08d20f 100644
--- a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
@@ -15,11 +15,13 @@ import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.end
 import com.touringproject.v2.ride.newRide
 import kotlinx.coroutines.runBlocking
+import org.junit.Assert.assertEquals
 import org.junit.Assert.assertFalse
 import org.junit.Before
 import org.junit.Rule
 import org.junit.Test
 import org.junit.runner.RunWith
+import org.robolectric.shadows.ShadowToast
 
 @RunWith(AndroidJUnit4::class)
 class AppUiTest {
@@ -54,6 +56,22 @@ class AppUiTest {
     rule.onNodeWithText("クラウドから読み直す").assertExists()
   }
 
+  // Slice 5 spec §6: SC-11 opens from the settings, saves each change at once, and puts both values back with a toast.
+  @Test
+  fun the_recording_settings_save_at_once_and_go_back_to_their_defaults() {
+    val graph = (rule.activity.application as TouringApp).graph
+    rule.onNodeWithTag("tab-SETTINGS").performClick()
+    rule.onNodeWithText("上限 20秒 · 合図 1.5秒").performScrollTo().performClick()
+    rule.onNodeWithTag("limitUp").performClick()
+    rule.onNodeWithTag("cue-0").performClick()
+    rule.waitUntil(5_000) { graph.settings.current().let { it.recordLimitSeconds == 25 && it.startCueMs == 0 } }
+    rule.onNodeWithTag("recordingDefaults").performClick()
+    rule.waitUntil(5_000) { graph.settings.current().let { it.recordLimitSeconds == 20 && it.startCueMs == 1_500 } }
+    assertEquals("既定値に戻しました", ShadowToast.getTextOfLatestToast())
+    back()
+    rule.onNodeWithText("上限 20秒 · 合図 1.5秒").assertExists()
+  }
+
   @Test
   fun the_records_tab_lists_the_kept_rides_and_home_keeps_its_place() {
     val graph = (rule.activity.application as TouringApp).graph
diff --git a/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
index b88cba1..002e863 100644
--- a/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
@@ -12,6 +12,7 @@ import com.touringproject.v2.recordings.TRIAL_IDLE
 import com.touringproject.v2.recordings.TrialPhase
 import com.touringproject.v2.recordings.TrialState
 import com.touringproject.v2.settings.LaunchableApp
+import com.touringproject.v2.settings.Settings
 import kotlinx.coroutines.test.runTest
 import org.junit.Assert.assertEquals
 import org.junit.Assert.assertFalse
@@ -113,6 +114,13 @@ class LabelsTest {
     assertEquals("録ったマイク: 本体のマイク", trialText(TrialState(phoneMic = true)).status)
   }
 
+  @Test
+  fun the_recording_row_says_the_limit_and_the_cue() {
+    assertEquals(listOf("なし", "0.5秒", "1秒", "1.5秒", "2秒", "3秒"), listOf(0, 500, 1_000, 1_500, 2_000, 3_000).map(::cueLabel))
+    assertEquals("上限 20秒 · 合図 1.5秒", recordingRowValue(Settings("rider01")))
+    assertEquals("上限 60秒 · 合図 なし", recordingRowValue(Settings("rider01", recordLimitSeconds = 60, startCueMs = 0)))
+  }
+
   @Test
   fun overlay_text_per_phase() {
     val recording = overlayText(FlowState(phase = Phase.RECORDING), seconds = 3)
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index 951df2c..e9855c1 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -346,12 +346,47 @@ class SettingsScreensTest {
         Settings("rider01", answerVolumeDb = 3, maxRecordingHours = 12), null, {}, {}, { opened += "ride" }, {}, { opened += "volume" }, { opened += "recordings" }, "0.2.0",
       )
     }
-    rule.onNodeWithText("最長 12時間").performClick()
-    rule.onNodeWithText("+3dB").performClick()
+    rule.onNodeWithText("最長 12時間").performScrollTo().performClick()
+    rule.onNodeWithText("+3dB").performScrollTo().performClick()
     rule.onNodeWithText("録音の確認").performScrollTo().performClick()
     assertEquals(listOf("ride", "volume", "recordings"), opened)
   }
 
+  // Slice 5 spec §6: SC-09's row says SC-11's values and opens it.
+  @Test
+  fun the_settings_list_leads_to_the_recording_settings() {
+    var opened = false
+    rule.setContent {
+      SettingsScreen(Settings("rider01", recordLimitSeconds = 45, startCueMs = 0), null, {}, {}, {}, {}, {}, {}, "0.2.0", onRecordingSettings = { opened = true })
+    }
+    rule.onNodeWithText("録音の設定").assertExists()
+    rule.onNodeWithText("上限 45秒 · 合図 なし").performScrollTo().performClick()
+    assertTrue(opened)
+  }
+
+  // SC-11: the limit goes in 5 s steps from 10 to 60 s, and the cue is one of six lengths.
+  @Test
+  fun the_recording_limit_steps_by_5_seconds_within_10_to_60_and_the_cue_is_chosen() {
+    var settings by mutableStateOf(Settings("rider01"))
+    var resets = 0
+    rule.setContent { RecordingSettingsScreen(settings, { settings = it }, { resets++ }) }
+    rule.onNodeWithTag("limitValue").assertTextEquals("20秒")
+    rule.onNodeWithTag("limitUp").performClick()
+    rule.onNodeWithTag("limitValue").assertTextEquals("25秒")
+    settings = settings.copy(recordLimitSeconds = 60)
+    rule.onNodeWithTag("limitUp").assertIsNotEnabled()
+    settings = settings.copy(recordLimitSeconds = 10)
+    rule.onNodeWithTag("limitDown").assertIsNotEnabled()
+    rule.onNodeWithTag("limitUp").assertIsEnabled()
+    for ((ms, label) in listOf(0 to "なし", 500 to "0.5秒", 1_000 to "1秒", 1_500 to "1.5秒", 2_000 to "2秒", 3_000 to "3秒")) {
+      rule.onNodeWithTag("cue-$ms").assertTextEquals(label)
+    }
+    rule.onNodeWithTag("cue-3000").performClick()
+    assertEquals(3_000, settings.startCueMs)
+    rule.onNodeWithTag("recordingDefaults").performClick()
+    assertEquals(1, resets)
+  }
+
   @Test
   fun the_settings_list_shows_the_app_version_as_a_row_that_leads_nowhere() {
     rule.setContent { SettingsScreen(Settings("rider01"), null, {}, {}, {}, {}, {}, {}, "0.2.0") }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SettingsScreensTest' --tests '*LabelsTest' --tests '*AppUiTest'`
Expected: コンパイルで落ちる（`RecordingSettingsScreen`・`cueLabel`・`withRecordingDefaults` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/settings/Settings.kt b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
index d95eada..2e72bed 100644
--- a/app/src/main/java/com/touringproject/v2/settings/Settings.kt
+++ b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
@@ -69,6 +69,9 @@ data class Settings(
 /** The longest a question is recorded (SC-11). */
 val Settings.recordLimitMs: Long get() = recordLimitSeconds * 1_000L
 
+/** SC-11's 「既定値に戻す」: both of its values, and nothing else. */
+fun Settings.withRecordingDefaults(): Settings = copy(recordLimitSeconds = DEFAULT_RECORD_LIMIT_SECONDS, startCueMs = DEFAULT_START_CUE_MS)
+
 val Settings.headingParams: HeadingParams get() = HeadingParams(headingReferenceMeters, headingAccuracyMeters, headingHoldMinutes)
 
 /**
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index e415d3c..4845dba 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -41,6 +41,7 @@ import com.touringproject.v2.records.NoteDraft
 import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.ride.RideStatus
 import com.touringproject.v2.settings.LaunchableApp
+import com.touringproject.v2.settings.withRecordingDefaults
 import com.touringproject.v2.sync.TakeOp
 import kotlinx.coroutines.delay
 import kotlinx.coroutines.launch
@@ -54,6 +55,7 @@ import kotlinx.serialization.Serializable
 @Serializable data object ReturnAppKey : NavKey
 @Serializable data object VolumeKey : NavKey
 @Serializable data object RecordingsKey : NavKey
+@Serializable data object RecordingSettingsKey : NavKey
 @Serializable data object RideRecordingKey : NavKey
 @Serializable data object DataKey : NavKey
 @Serializable data object RecordsKey : NavKey
@@ -232,6 +234,18 @@ fun AppUi(graph: AppGraph) {
                   modifier = Modifier.safeDrawingPadding(),
                   saved = saveRowValue(summary ?: SaveSummary()),
                   onData = { tabs.push(DataKey) },
+                  onRecordingSettings = { tabs.push(RecordingSettingsKey) },
+                )
+              }
+              entry<RecordingSettingsKey> {
+                RecordingSettingsScreen(
+                  current,
+                  { next -> scope.launch { graph.settings.update(next) } },
+                  onReset = {
+                    scope.launch { graph.settings.update(current.withRecordingDefaults()) }
+                    Toast.makeText(context, "既定値に戻しました", Toast.LENGTH_SHORT).show()
+                  },
+                  modifier = Modifier.safeDrawingPadding(),
                 )
               }
               entry<DataKey> {
diff --git a/app/src/main/java/com/touringproject/v2/ui/Labels.kt b/app/src/main/java/com/touringproject/v2/ui/Labels.kt
index 02912e8..e0da02d 100644
--- a/app/src/main/java/com/touringproject/v2/ui/Labels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/Labels.kt
@@ -6,6 +6,8 @@ import com.touringproject.v2.audio.InputDevice
 import com.touringproject.v2.audio.MediaVolume
 import com.touringproject.v2.recordings.TrialPhase
 import com.touringproject.v2.recordings.TrialState
+import com.touringproject.v2.settings.Settings
+import java.math.BigDecimal
 import java.time.Instant
 import java.time.ZoneId
 import java.time.format.DateTimeFormatter
@@ -65,6 +67,12 @@ fun nextVolume(previous: MediaVolume?, reading: MediaVolume?): MediaVolume? = re
 /** Low, and not dismissed at this very level: a dismissal lasts until the volume changes. */
 fun volumeWarning(volume: MediaVolume?, dismissedAt: Int?): Boolean = mediaVolumeLow(volume) && volume?.current != dismissedAt
 
+/** SC-11's start cue: 「なし」, or its length in seconds (0.5秒, 1秒, 1.5秒). */
+fun cueLabel(ms: Int): String = if (ms <= 0) "なし" else "${BigDecimal(ms).divide(BigDecimal(1_000)).stripTrailingZeros().toPlainString()}秒"
+
+/** SC-09's row for SC-11 (slice 5 spec §6). */
+fun recordingRowValue(settings: Settings): String = "上限 ${settings.recordLimitSeconds}秒 · 合図 ${cueLabel(settings.startCueMs)}"
+
 // SC-12: how a kept recording is described, in Japan time.
 private val RECORDED_AT = DateTimeFormatter.ofPattern("M/d HH:mm:ss").withZone(ZoneId.of("Asia/Tokyo"))
 
diff --git a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
index 27ffd32..95ec282 100644
--- a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
@@ -35,6 +35,7 @@ import androidx.compose.ui.graphics.Color
 import androidx.compose.ui.platform.testTag
 import androidx.compose.ui.text.font.FontFamily
 import androidx.compose.ui.text.font.FontWeight
+import androidx.compose.ui.text.style.TextAlign
 import androidx.compose.ui.unit.dp
 import androidx.compose.ui.unit.sp
 import com.touringproject.v2.api.ApiError
@@ -43,7 +44,9 @@ import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.recordings.KEEP_RECORDINGS
 import com.touringproject.v2.settings.LaunchableApp
 import com.touringproject.v2.settings.MAX_RECORDING_HOURS_CHOICES
+import com.touringproject.v2.settings.RECORD_LIMIT_SECONDS_CHOICES
 import com.touringproject.v2.settings.ReturnTiming
+import com.touringproject.v2.settings.START_CUE_MS_CHOICES
 import com.touringproject.v2.settings.Settings
 import com.touringproject.v2.settings.USER_NAME_RE
 import com.touringproject.v2.settings.VOLUME_DB_CHOICES
@@ -87,6 +90,7 @@ fun SettingsScreen(
   /** SC-14's row: 保存済み or 未送信あり (slice 4 spec §7.1). */
   saved: String = "",
   onData: () -> Unit = {},
+  onRecordingSettings: () -> Unit = {},
 ) {
   val returnValue = if (!settings.returnEnabled) "戻らない" else settings.returnApp?.label ?: "未設定"
   // Scrolls: the list outgrows a small screen.
@@ -96,6 +100,8 @@ fun SettingsScreen(
     SettingsRow("☁️ データの保存", saved, onData)
     SettingsRow("走行の記録", "最長 ${settings.maxRecordingHours}時間", onRideRecording)
     SettingsRow("応答後に戻るアプリ", returnValue, onReturnApp)
+    // Next to the other settings of an ask, as the mock puts it (slice 5 spec §14).
+    SettingsRow("録音の設定", recordingRowValue(settings), onRecordingSettings)
     SettingsRow("回答の音量", "+${settings.answerVolumeDb}dB", onVolume)
     SettingsRow("録音の確認", "", onRecordings)
     SettingsRow("バージョン", version, null, Modifier.testTag("versionRow"))
@@ -220,6 +226,47 @@ fun RideRecordingScreen(settings: Settings, onUpdate: (Settings) -> Unit, modifi
   }
 }
 
+/**
+ * SC-11 (slice 5 spec §6): how long a question may be recorded, and the start cue. Each change is saved at once and
+ * takes effect from the next question and trial. onReset puts both back (SC-11's 「既定値に戻す」, told by a toast).
+ */
+@Composable
+fun RecordingSettingsScreen(settings: Settings, onUpdate: (Settings) -> Unit, onReset: () -> Unit, modifier: Modifier = Modifier) {
+  val muted = Color(0xFF666666)
+  val limit = settings.recordLimitSeconds
+  val choices = RECORD_LIMIT_SECONDS_CHOICES
+  Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
+    Text("録音の上限", fontSize = 18.sp)
+    Text("インカムのボタンを再度押さなくても、この時間で自動的に送ります", color = muted, fontSize = 14.sp)
+    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
+      Button(
+        onClick = { onUpdate(settings.copy(recordLimitSeconds = choices[choices.indexOf(limit) - 1])) },
+        enabled = limit > choices.first(),
+        modifier = Modifier.testTag("limitDown"),
+      ) { Text("−", fontSize = 20.sp) }
+      Text("${limit}秒", Modifier.weight(1f).testTag("limitValue"), fontSize = 22.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
+      Button(
+        onClick = { onUpdate(settings.copy(recordLimitSeconds = choices[choices.indexOf(limit) + 1])) },
+        enabled = limit < choices.last(),
+        modifier = Modifier.testTag("limitUp"),
+      ) { Text("＋", fontSize = 20.sp) }
+    }
+    Text("開始の合図", fontSize = 18.sp)
+    Text("録音が始まったことを知らせる音の長さ。インカムは音の出だしを落とすので、短いと聞こえにくいことがあります", color = muted, fontSize = 14.sp)
+    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
+      START_CUE_MS_CHOICES.forEach { ms ->
+        FilterChip(
+          selected = settings.startCueMs == ms,
+          onClick = { onUpdate(settings.copy(startCueMs = ms)) },
+          label = { Text(cueLabel(ms), fontSize = 13.sp) },
+          modifier = Modifier.weight(1f).testTag("cue-$ms"),
+        )
+      }
+    }
+    Button(onClick = onReset, modifier = Modifier.fillMaxWidth().testTag("recordingDefaults")) { Text("既定値に戻す", fontSize = 16.sp) }
+  }
+}
+
 enum class KeyCheck(val message: String) {
   SAVED("保存しました"),
   INVALID("キーが正しくありません。元のキーのままです。"),
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun`
Expected: PASS（627件）。設定の一覧の行が増えるので、`the_settings_list_leads_to_the_volume_and_the_recordings` は行を `performScrollTo` で出す（Step 1 の差分に入っている）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/settings/Settings.kt app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt app/src/main/java/com/touringproject/v2/ui/Labels.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt
cd $AND && git add app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
git commit -m "feat: add SC-11 for the recording limit and the start cue"
```

---

### Task 7: 受け付けの判断を1つにまとめる（#48）

**Files:**
- Modify: `ask/AskPorts.kt`・`ask/AskController.kt`・`ui/RideLabels.kt`・`ui/AppUi.kt`
- Test: `ask/AskControllerTest.kt`・`ui/RideLabelsTest.kt`

**Interfaces:**
- Produces: `fun refusal(ride: RideNow): FailureReason?`（記録中は null、一時停止中は `PAUSED`、記録していないは `NOT_RECORDING`）。`fun askHint(ride: RideNow): String?`（`Ride?` から変える。呼ぶ側は `askHint(rideNow(ride))`）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index 0ffd6ea..3922f17 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -737,6 +737,19 @@ class AskControllerTest {
     assertEquals(listOf("vol:read", "cue:failure", "say:一時停止中は質問できません。再開すると質問できます。", "return:maps"), h.log)
     assertTrue(h.states.any { it.phase == Phase.FAILED && it.failure == FailureReason.PAUSED })
   }
+
+  // Android #48: from the screen (normally its button cannot be pressed then), a refused ask shows why on SC-03 and stays
+  // in this app.
+  @Test
+  fun a_screen_ask_without_a_recording_ride_is_refused_on_screen_and_stays_here() = runTest {
+    for ((ride, reason) in listOf(RideNow.NotRecording to FailureReason.NOT_RECORDING, RideNow.Paused to FailureReason.PAUSED)) {
+      val h = Harness(this, ride = ride)
+      h.controller.run(Source.SCREEN)
+      assertTrue(h.states.any { it.phase == Phase.FAILED && it.failure == reason && it.source == Source.SCREEN })
+      assertFalse(h.log.any { it.startsWith("return:") || it == "svc:start" || it == "rec:start" })
+      assertTrue(h.kept.isEmpty())
+    }
+  }
 }
 
 class AskRecordTest {
@@ -770,4 +783,11 @@ class RideNowTest {
     assertEquals(RideNow.Paused, rideNow(ride.pause(5_000)))
     assertEquals(RideNow.NotRecording, rideNow(null))
   }
+
+  @Test
+  fun only_a_recording_ride_has_no_refusal() {
+    assertEquals(null, refusal(RideNow.Recording("r1")))
+    assertEquals(FailureReason.PAUSED, refusal(RideNow.Paused))
+    assertEquals(FailureReason.NOT_RECORDING, refusal(RideNow.NotRecording))
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt
index 2ca0217..dc494b0 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt
@@ -1,7 +1,10 @@
 package com.touringproject.v2.ui
 
+import com.touringproject.v2.ask.rideNow
+import com.touringproject.v2.ride.EndReason
 import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.Pauses
+import com.touringproject.v2.ride.end
 import com.touringproject.v2.ride.newRide
 import com.touringproject.v2.ride.pause
 import com.touringproject.v2.ride.resume
@@ -15,13 +18,14 @@ private val TOKYO = ZoneId.of("Asia/Tokyo")
 private fun at(day: Int, hour: Int, minute: Int) = ZonedDateTime.of(2026, 10, day, hour, minute, 0, 0, TOKYO).toInstant().toEpochMilli()
 
 class RideLabelsTest {
-  // Slice 2 spec §4.7, §7.2
+  // Slice 2 spec §4.7, §7.2; Android #48: the hint follows the ask loop's own refusal.
   @Test
   fun the_hint_says_how_to_ask_unless_a_ride_records() {
     val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)
-    assertEquals(null, askHint(ride))
-    assertEquals("再開すると、インカムのボタンで話せます", askHint(ride.pause(5_000)))
-    assertEquals("走行を開始すると、インカムのボタンで話せます", askHint(null))
+    assertEquals(null, askHint(rideNow(ride)))
+    assertEquals("再開すると、インカムのボタンで話せます", askHint(rideNow(ride.pause(5_000))))
+    assertEquals("走行を開始すると、インカムのボタンで話せます", askHint(rideNow(null)))
+    assertEquals("走行を開始すると、インカムのボタンで話せます", askHint(rideNow(ride.end(9_000, EndReason.MANUAL, 9_000))))
   }
 
   @Test
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*AskControllerTest' --tests '*RideLabelsTest'`
Expected: コンパイルで落ちる（`refusal`・`askHint(RideNow)` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index f0a22c0..07d3388 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -109,17 +109,12 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     try {
       // Slice 2 spec §4.7: only a recording ride takes asks. Read once, so pausing meanwhile neither stops the ask nor
       // takes it out of the ride.
-      val rideId = when (val ride = d.ride()) {
-        is RideNow.Recording -> ride.rideId
-        RideNow.Paused -> {
-          fail(FailureReason.PAUSED, run)
-          return
-        }
-        RideNow.NotRecording -> {
-          fail(FailureReason.NOT_RECORDING, run)
-          return
-        }
+      val ride = d.ride()
+      refusal(ride)?.let {
+        fail(it, run)
+        return
       }
+      val rideId = (ride as RideNow.Recording).rideId
       val apiKey = d.apiKey()
       if (apiKey == null) {
         fail(FailureReason.NO_KEY, run)
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
index 8f6f586..a90bc63 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
@@ -98,6 +98,16 @@ fun rideNow(active: Ride?): RideNow = when {
   else -> RideNow.Recording(active.id)
 }
 
+/**
+ * Why an ask is not taken now, or null when it is (slice 2 spec §4.7). The ask loop and Home's buttons both decide by
+ * this, so the two never part (Android #48).
+ */
+fun refusal(ride: RideNow): FailureReason? = when (ride) {
+  is RideNow.Recording -> null
+  RideNow.Paused -> FailureReason.PAUSED
+  RideNow.NotRecording -> FailureReason.NOT_RECORDING
+}
+
 class AskDeps(
   val now: () -> Long,
   val sleep: suspend (Long) -> Unit,
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 4845dba..768283b 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -37,6 +37,7 @@ import com.touringproject.v2.AppGraph
 import com.touringproject.v2.BuildConfig
 import com.touringproject.v2.api.ApiClient
 import com.touringproject.v2.ask.isBusy
+import com.touringproject.v2.ask.rideNow
 import com.touringproject.v2.records.NoteDraft
 import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.ride.RideStatus
@@ -139,7 +140,7 @@ fun AppUi(graph: AppGraph) {
                     askStoreFailed = askStoreFailed,
                   ),
                   conversation = conversationLabel(expiresAt, System.currentTimeMillis()),
-                  askHint = askHint(ride),
+                  askHint = askHint(rideNow(ride)),
                 )
                 HomeScreen(
                   ui = ui,
diff --git a/app/src/main/java/com/touringproject/v2/ui/RideLabels.kt b/app/src/main/java/com/touringproject/v2/ui/RideLabels.kt
index e64d5cb..f865e83 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RideLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RideLabels.kt
@@ -1,5 +1,8 @@
 package com.touringproject.v2.ui
 
+import com.touringproject.v2.ask.FailureReason
+import com.touringproject.v2.ask.RideNow
+import com.touringproject.v2.ask.refusal
 import com.touringproject.v2.ride.Pauses
 import com.touringproject.v2.ride.Ride
 import com.touringproject.v2.ride.RideStatus
@@ -35,12 +38,12 @@ fun pausesLabel(pauses: Pauses): String? =
   if (pauses.count == 0) null else "一時停止 ${pauses.count}回（${pauses.totalMs / 60_000}分）は走行時間に含めません"
 
 /**
- * What Home says under the intercom line when no ask can start (slice 2 spec §4.7, §7.2): null while a ride records,
- * so the line says the intercom is ready.
+ * What Home says under the intercom line when no ask can start (slice 2 spec §4.7, §7.2): null while asks are taken,
+ * so the line says the intercom is ready. It follows the ask loop's own refusal (Android #48).
  */
-fun askHint(ride: Ride?): String? = when (ride?.status) {
-  RideStatus.RECORDING -> null
-  RideStatus.PAUSED -> "再開すると、インカムのボタンで話せます"
+fun askHint(ride: RideNow): String? = when (refusal(ride)) {
+  null -> null
+  FailureReason.PAUSED -> "再開すると、インカムのボタンで話せます"
   else -> "走行を開始すると、インカムのボタンで話せます"
 }
 
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun`
Expected: PASS（629件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/ui/RideLabels.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt
git commit -m "refactor: decide whether an ask is taken in one place for the ask loop and Home

Fixes #48"
```

---

### Task 8: 文字の質問の一巡（#30）

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ask/TextAsk.kt`
- Modify: `ask/AskController.kt`・`ask/AskPorts.kt`・`ask/AskRecord.kt`・`ask/Flow.kt`・`location/PositionTracker.kt`
- Test: `ask/AskControllerTest.kt`（`TextAskTest` を足す）・`ask/FlowTest.kt`・`location/PositionTrackerTest.kt`

**Interfaces:**
- Consumes: Task 3 の `AskDeps.heading`、Task 7 の `refusal`。
- Produces: `const val TEXT_ASK_MAX = 500`・`fun cutTextAsk(input): String`・`fun textAskLeft(input): Int`・`fun textQuestion(input): String?`・`enum class TextAskOutcome { SENT, OFFLINE, NOT_TAKEN }`。`Positions.latest(): Fix?`（suspend）・`const val LATEST_WAIT_MS = 2_000L`。`FlowEvent.StartText(now)`。`const val ASK_INPUT_TEXT = "text"`。`SentAsk(..., input: String = ASK_INPUT_VOICE, question: String? = null)`。`AskController.askText(text: String, taken: (TextAskOutcome) -> Unit)` と `suspend fun runText(text, taken)`（`taken` はちょうど1回呼ばれる）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index 3922f17..42749c2 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -67,7 +67,11 @@ private class Harness(
   var online: Boolean = true,
   /** What the ride's route gives as the heading (slice 5 spec §4). */
   var heading: Double? = 12.5,
+  /** The device's last known fix, where a text ask is (slice 5 spec §4.1). */
+  var latest: Fix? = HERE,
 ) {
+  /** What each text ask told the sheet. */
+  val outcomes = mutableListOf<TextAskOutcome>()
   /** Where and when the heading was asked for. */
   val headingAsked = mutableListOf<Pair<Fix?, Long>>()
   /** How long each start cue was asked to sound. */
@@ -131,6 +135,7 @@ private class Harness(
     location = object : Positions {
       override fun begin() { log += "loc:begin" }
       override fun end() = HERE
+      override suspend fun latest(): Fix? { log += "loc:latest"; return latest }
     },
     heading = { here, at -> headingAsked += here to at; heading },
     service = object : KeepAlive {
@@ -164,6 +169,8 @@ private class Harness(
 
   val phase get() = controller.state.phase
 
+  suspend fun askText(text: String) = controller.runText(text) { outcomes += it }
+
   /** Advances virtual time in small steps until the condition holds. */
   fun until(condition: () -> Boolean) {
     var steps = 0
@@ -752,6 +759,130 @@ class AskControllerTest {
   }
 }
 
+// Slice 5 spec §5: asking by text from Home.
+class TextAskTest {
+  // §5.3: no recording; it starts as it is sent, waits for the answer, reads it out, and never goes back to the nav app.
+  @Test
+  fun a_text_ask_starts_at_sending_and_is_read_out_without_returning() = runTest {
+    val h = Harness(this, answers = listOf(done(transcript = null)))
+    h.askText("右手に見える山は何？")
+    assertEquals(listOf("svc:start", "loc:latest", "post", "cue:sent", "get", "play:https://audio/1.mp3", "svc:stop"), h.log)
+    assertEquals(
+      AskBody(volumeDb = 6, text = "右手に見える山は何？", location = Point(35.6812, 139.7671), headingDegrees = 12.5, conversationId = null, rideId = "r1"),
+      h.bodies.single(),
+    )
+    assertEquals(listOf<Pair<Fix?, Long>>(HERE to 0L), h.headingAsked)
+    assertEquals(listOf(Phase.SENDING, Phase.WAITING, Phase.SPEAKING, Phase.IDLE), h.states.map { it.phase })
+    assertEquals(Source.SCREEN, h.states.first().source)
+    assertEquals(listOf(TextAskOutcome.SENT), h.outcomes)
+    // §5.4: kept as a text ask, with what was typed as its question.
+    val kept = h.kept.single()
+    assertEquals(ASK_INPUT_TEXT, kept.input)
+    assertEquals("右手に見える山は何？", kept.transcript)
+    assertEquals(AskOutcome.ANSWERED, kept.outcome)
+    assertTrue(h.metas.isEmpty())
+  }
+
+  // The conversation goes on across voice and text asks alike.
+  @Test
+  fun a_text_ask_carries_the_conversation_on() = runTest {
+    val h = Harness(this, stopAfterMs = 1_000)
+    h.controller.run(Source.HANDSFREE)
+    h.askText("その山の高さは？")
+    assertEquals(listOf(null, "c1"), h.bodies.map { it.conversationId })
+  }
+
+  // §5.3: without a network nothing is sent, nothing is kept (no unreached ask) and SC-03 shows no failure.
+  @Test
+  fun without_a_network_a_text_ask_keeps_nothing_and_tells_the_sheet() = runTest {
+    val h = Harness(this, online = false)
+    h.askText("右手に見える山は何？")
+    assertEquals(listOf(TextAskOutcome.OFFLINE), h.outcomes)
+    assertFalse("post" in h.log)
+    assertTrue(h.kept.isEmpty())
+    assertTrue(h.states.none { it.phase == Phase.FAILED })
+    assertFalse(h.log.any { it.startsWith("say:") || it == "cue:failure" })
+    assertEquals(Phase.IDLE, h.phase)
+  }
+
+  // A network failure on the way is the same: the Backend never took it.
+  @Test
+  fun a_network_failure_on_send_keeps_nothing_and_tells_the_sheet() = runTest {
+    val h = Harness(this, post = { throw ApiError(ApiErrorKind.SERVER, "HTTP 503") })
+    h.askText("右手に見える山は何？")
+    assertEquals(listOf(TextAskOutcome.OFFLINE), h.outcomes)
+    assertTrue(h.kept.isEmpty())
+    assertTrue(h.states.none { it.phase == Phase.FAILED })
+    assertEquals(listOf("svc:start", "loc:latest", "post", "svc:stop"), h.log)
+  }
+
+  // Refusals show why on SC-03 (US-B-06.004), and the sheet keeps the text.
+  @Test
+  fun a_refused_text_ask_says_why_on_screen_and_the_sheet_keeps_the_text() = runTest {
+    val cases = listOf(
+      Harness(this, ride = RideNow.NotRecording) to FailureReason.NOT_RECORDING,
+      Harness(this, ride = RideNow.Paused) to FailureReason.PAUSED,
+      Harness(this, apiKey = null) to FailureReason.NO_KEY,
+      Harness(this, post = { throw ApiError(ApiErrorKind.INVALID_KEY) }) to FailureReason.INVALID_KEY,
+      Harness(this, post = { throw ApiError(ApiErrorKind.BAD_REQUEST) }) to FailureReason.AGENT_FAILED,
+      Harness(this, serviceError = IllegalStateException("background")) to FailureReason.SERVICE,
+    )
+    for ((h, reason) in cases) {
+      h.askText("右手に見える山は何？")
+      assertEquals(listOf(TextAskOutcome.NOT_TAKEN), h.outcomes)
+      assertTrue("$reason", h.states.any { it.phase == Phase.FAILED && it.failure == reason })
+      assertFalse(h.log.any { it.startsWith("return:") })
+      assertTrue(h.kept.isEmpty())
+    }
+  }
+
+  // §5.3: cancelled while waiting for the answer, it is kept nowhere, as a voice ask.
+  @Test
+  fun a_text_ask_cancelled_while_waiting_is_not_kept() = runTest {
+    val h = Harness(this, answers = listOf(PROCESSING, PROCESSING, PROCESSING))
+    val running = launch { h.askText("右手に見える山は何？") }
+    h.until { h.phase == Phase.WAITING }
+    h.controller.cancel()
+    running.join()
+    advanceUntilIdle()
+    assertEquals(listOf(TextAskOutcome.SENT), h.outcomes)
+    assertTrue(h.kept.isEmpty())
+  }
+
+  // §4.1: without a fresh position, the text ask goes without a place, and the heading is asked without one.
+  @Test
+  fun without_a_position_a_text_ask_goes_without_a_place() = runTest {
+    val h = Harness(this, latest = null, heading = null)
+    h.askText("右手に見える山は何？")
+    assertEquals(null, h.bodies.single().location)
+    assertEquals(null, h.bodies.single().headingDegrees)
+    assertEquals(listOf<Pair<Fix?, Long>>(null to 0L), h.headingAsked)
+  }
+
+  @Test
+  fun nothing_starts_while_an_ask_runs() = runTest {
+    val h = Harness(this, stopAfterMs = null)
+    launch { h.controller.run(Source.HANDSFREE) }
+    h.until { h.phase == Phase.RECORDING }
+    h.controller.askText("右手に見える山は何？") { h.outcomes += it }
+    assertEquals(listOf(TextAskOutcome.NOT_TAKEN), h.outcomes)
+    h.controller.cancel()
+    advanceUntilIdle()
+    assertTrue(h.bodies.isEmpty())
+  }
+
+  @Test
+  fun the_sheet_takes_500_characters_and_no_blank_question() {
+    assertEquals(500, TEXT_ASK_MAX)
+    assertEquals(500, cutTextAsk("あ".repeat(600)).length)
+    val emoji = "😀".repeat(501)
+    assertEquals(500, cutTextAsk(emoji).codePointCount(0, cutTextAsk(emoji).length))
+    assertEquals(497, textAskLeft("山は何"))
+    assertEquals(null, textQuestion(" \n "))
+    assertEquals("山は何？", textQuestion("  山は何？ \n"))
+  }
+}
+
 class AskRecordTest {
   private val sent = SentAsk("a1", "c1", true, 5_000, Fix(35.0, 139.0, 4_000, 5.0), "r1")
 
@@ -772,6 +903,14 @@ class AskRecordTest {
     assertEquals(AskOutcome.FAILED, failed.outcome)
     assertEquals("agent_failed", failed.failure)
   }
+
+  // Slice 5 spec §5.4: a text ask keeps what was typed, also when it timed out without a result.
+  @Test
+  fun a_text_ask_is_kept_as_text_with_what_was_typed() {
+    val text = sent.copy(input = ASK_INPUT_TEXT, question = "山は何？")
+    assertEquals(ASK_INPUT_TEXT to "山は何？", askRecord(text, null, 9_000).let { it.input to it.transcript })
+    assertEquals(ASK_INPUT_VOICE, askRecord(sent, null, 9_000).input)
+  }
 }
 
 class RideNowTest {
diff --git a/app/src/test/java/com/touringproject/v2/ask/FlowTest.kt b/app/src/test/java/com/touringproject/v2/ask/FlowTest.kt
index c9d8972..094fa08 100644
--- a/app/src/test/java/com/touringproject/v2/ask/FlowTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/FlowTest.kt
@@ -28,6 +28,17 @@ class FlowTest {
     assertEquals(IDLE, reduce(s, FlowEvent.Spoken(5)))
   }
 
+  // Slice 5 spec §5.3: a text ask has nothing to record; it starts at sending, from the screen.
+  @Test
+  fun a_text_ask_starts_at_sending() {
+    val s = run(FlowEvent.StartText(1))
+    assertEquals(Phase.SENDING, s.phase)
+    assertEquals(Source.SCREEN, s.source)
+    assertEquals(Phase.WAITING, reduce(s, FlowEvent.Sent("a1", 2)).phase)
+    assertSame(s, reduce(s, FlowEvent.StartText(2)))
+    assertEquals(Phase.SENDING, reduce(run(FlowEvent.Start(Source.SCREEN, 1), FlowEvent.Fail(FailureReason.MIC, 2)), FlowEvent.StartText(3)).phase)
+  }
+
   @Test
   fun out_of_order_events_are_ignored() {
     assertSame(IDLE, reduce(IDLE, FlowEvent.Sent("a1", 1)))
diff --git a/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt b/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
index 0fc3ad5..fe8825b 100644
--- a/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
@@ -1,5 +1,6 @@
 package com.touringproject.v2.location
 
+import kotlinx.coroutines.test.runTest
 import org.junit.Assert.assertEquals
 import org.junit.Assert.assertNull
 import org.junit.Test
@@ -73,4 +74,25 @@ class PositionTrackerTest {
     source.onFix!!(fix(98_000))
     assertEquals(fix(99_000), tracker.end())
   }
+
+  // Slice 5 spec §4.1: a text ask is where the device last was, within 30 s; none without a fresh fix.
+  @Test
+  fun a_text_ask_takes_the_last_known_fix_when_it_is_fresh() = runTest {
+    val tracker = PositionTracker(FakeSource().apply { last = fix(90_000) })
+    assertEquals(fix(90_000), tracker.latest())
+    assertNull(PositionTracker(FakeSource().apply { last = fix(100_000 - MAX_CURRENT_AGE_MS - 1) }).latest())
+  }
+
+  @Test
+  fun no_last_known_fix_gives_none_after_a_short_wait() = runTest {
+    // Fused answers a success without a fix by never calling back.
+    assertNull(PositionTracker(FakeSource()).latest())
+    assertEquals(LATEST_WAIT_MS, testScheduler.currentTime)
+    val refused = object : PositionSource {
+      override fun now() = 100_000L
+      override fun lastKnown(onFix: (Fix) -> Unit) = throw SecurityException("no permission")
+      override fun watch(onFix: (Fix) -> Unit) = Subscription {}
+    }
+    assertNull(PositionTracker(refused).latest())
+  }
 }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TextAskTest' --tests '*FlowTest' --tests '*PositionTrackerTest'`
Expected: コンパイルで落ちる（`runText`・`TextAskOutcome`・`Positions.latest`・`FlowEvent.StartText` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index 07d3388..d27ecc1 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -79,6 +79,15 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     if (!isBusy(state)) scope.launch { run(Source.SCREEN) }
   }
 
+  /** Home's text sheet (slice 5 spec §5.3). taken is told once what became of it; nothing starts while an ask runs. */
+  fun askText(text: String, taken: (TextAskOutcome) -> Unit) {
+    if (isBusy(state)) {
+      taken(TextAskOutcome.NOT_TAKEN)
+      return
+    }
+    scope.launch { runText(text, taken) }
+  }
+
   fun stopRecording() {
     if (state.phase == Phase.RECORDING) dispatch(FlowEvent.StopRecording(deps.now()))
   }
@@ -156,6 +165,111 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     }
   }
 
+  /**
+   * A text ask (slice 5 spec §5.3): from the screen, so it never returns to the nav app. It starts as it is sent (SC-03's
+   * 送っています…) and goes on like a voice ask once the Backend has taken it. Without a network it keeps nothing and
+   * shows no failure: the sheet says so and keeps the text, as the rider has stopped and can send it again.
+   */
+  suspend fun runText(text: String, taken: (TextAskOutcome) -> Unit) {
+    val d = deps
+    if (state.phase == Phase.FAILED) d.speech.stop()
+    val run = Run(++runId, Source.SCREEN)
+    current = run
+    runsStarted += 1
+    var told = false
+    val tell = { outcome: TextAskOutcome ->
+      if (!told) {
+        told = true
+        taken(outcome)
+      }
+    }
+    dispatch(FlowEvent.StartText(d.now()))
+    try {
+      val ride = d.ride()
+      refusal(ride)?.let {
+        tell(TextAskOutcome.NOT_TAKEN)
+        fail(it, run)
+        return
+      }
+      val rideId = (ride as RideNow.Recording).rideId
+      val apiKey = d.apiKey()
+      if (apiKey == null) {
+        tell(TextAskOutcome.NOT_TAKEN)
+        fail(FailureReason.NO_KEY, run)
+        return
+      }
+      if (!d.online()) {
+        tell(TextAskOutcome.OFFLINE)
+        return
+      }
+      val settings = d.settings()
+      val api = d.api(apiKey, settings.userName)
+      try {
+        d.service.start()
+      } catch (e: Exception) {
+        d.log("service_failed", mapOf("error" to e.toString()))
+        tell(TextAskOutcome.NOT_TAKEN)
+        fail(FailureReason.SERVICE, run)
+        return
+      }
+      serviceRunning = true
+      val here = d.location.latest()
+      if (!isCurrent(run)) return
+      val sent = sendText(text, here, d.heading(here, d.now()), rideId, api, run, tell) ?: return
+      val result = waitForAnswer(sent, null, api, run) ?: return
+      speak(result, settings, run)
+    } finally {
+      // Cancelled before the Backend took it: the rider let it go, and the sheet keeps the text.
+      tell(TextAskOutcome.NOT_TAKEN)
+      if (isCurrent(run)) {
+        current = null
+        dispatch(FlowEvent.Dismiss(d.now()))
+        stopService()
+      }
+    }
+  }
+
+  private suspend fun sendText(
+    text: String,
+    here: Fix?,
+    heading: Double?,
+    rideId: String,
+    api: AskApi,
+    run: Run,
+    tell: (TextAskOutcome) -> Unit,
+  ): SentAsk? {
+    val d = deps
+    val body = AskBody(
+      volumeDb = d.settings().answerVolumeDb,
+      text = text,
+      location = here?.let { Point(it.latitude, it.longitude) },
+      headingDegrees = heading,
+      conversationId = d.conversation.current(d.now()),
+      rideId = rideId,
+    )
+    val accepted = try {
+      api.postAsk(body)
+    } catch (e: Exception) {
+      d.log("post_failed", mapOf("kind" to ((e as? ApiError)?.kind?.name ?: "unknown")))
+      when (val reason = reasonFor(e)) {
+        FailureReason.NETWORK -> tell(TextAskOutcome.OFFLINE)
+        else -> {
+          tell(TextAskOutcome.NOT_TAKEN)
+          // A refused text is no speech not heard: say that it could not be answered.
+          fail(if (reason == FailureReason.NO_SPEECH) FailureReason.AGENT_FAILED else reason, run)
+        }
+      }
+      return null
+    }
+    // The Backend has it either way: the sheet's text has gone, and the conversation goes on.
+    tell(TextAskOutcome.SENT)
+    d.conversation.update(accepted.conversationId, accepted.conversationExpiresAt)
+    if (!isCurrent(run)) return null
+    dispatch(FlowEvent.Sent(accepted.askId, d.now()))
+    d.cues.sent()
+    return SentAsk(accepted.askId, accepted.conversationId, body.conversationId == null, d.now(), here, rideId, ASK_INPUT_TEXT, text)
+  }
+
   private fun stopService() {
     if (!serviceRunning) return
     serviceRunning = false
@@ -300,7 +414,8 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     fail(FailureReason.NETWORK, run)
   }
 
-  private suspend fun waitForAnswer(sent: SentAsk, recordingName: String, api: AskApi, run: Run): AskResult? {
+  /** recordingName is the kept recording to add what was heard to; a text ask has none. */
+  private suspend fun waitForAnswer(sent: SentAsk, recordingName: String?, api: AskApi, run: Run): AskResult? {
     val d = deps
     var sinceCue = 0L
     val sleep: suspend (Long) -> Unit = { ms ->
@@ -317,8 +432,9 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       fail(reasonFor(e), run)
       return null
     }
-    if (outcome is PollOutcome.Done) outcome.result.transcript?.let { d.recordings.transcribed(recordingName, it) }
-    // Kept even when the rider has cancelled meanwhile: the Backend has the ask either way.
+    if (outcome is PollOutcome.Done && recordingName != null) outcome.result.transcript?.let { d.recordings.transcribed(recordingName, it) }
+    // A result that has already arrived is kept even if the rider cancels at the same moment; a cancel while waiting
+    // stops the poll (Cancelled) and keeps nothing (Android #30).
     when (outcome) {
       is PollOutcome.Done -> d.asks.keep(askRecord(sent, outcome.result, d.now()))
       PollOutcome.Timeout -> d.asks.keep(askRecord(sent, null, d.now()))
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
index a90bc63..b49eb48 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
@@ -53,6 +53,8 @@ interface Positions {
   fun begin()
   /** Where the ask is: the newest fix since begin(), unless it is older than 30 s. */
   fun end(): Fix?
+  /** Where a text ask is (slice 5 spec §4.1): the device's last known fix, unless it is older than 30 s. */
+  suspend fun latest(): Fix?
 }
 
 interface KeepAlive {
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt b/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
index f16bf52..6711d17 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
@@ -10,8 +10,9 @@ import java.time.OffsetDateTime
 /** OFFLINE: the ask never reached the Backend (US-C-09); only when and where it was is kept. */
 enum class AskOutcome { ANSWERED, FAILED, OFFLINE }
 
-/** Slice 2 asks only by voice; text asks come in slice 4. */
+/** How an ask was put (07b): by voice, or typed on Home (slice 5 spec §5). The Backend's inputType audio is voice. */
 const val ASK_INPUT_VOICE = "voice"
+const val ASK_INPUT_TEXT = "text"
 
 const val TIMEOUT_FAILURE = "timeout"
 
@@ -68,7 +69,7 @@ fun unreachedAsk(askId: String, at: Long, here: Fix?, headingDegrees: Double?, r
   sent = false,
 )
 
-/** What the loop knows once the Backend has taken the ask in. */
+/** What the loop knows once the Backend has taken the ask in. question is what a text ask typed. */
 data class SentAsk(
   val askId: String,
   val conversationId: String,
@@ -76,6 +77,8 @@ data class SentAsk(
   val sentAt: Long,
   val here: Fix?,
   val rideId: String?,
+  val input: String = ASK_INPUT_VOICE,
+  val question: String? = null,
 )
 
 /** An answer the rider can hear: a completed one, or text whose speech the Backend failed to make. */
@@ -88,13 +91,14 @@ fun askRecord(sent: SentAsk, result: AskResult?, now: Long): AskRecord {
     askId = sent.askId,
     askedAt = result?.askedAt?.let { runCatching { OffsetDateTime.parse(it).toInstant().toEpochMilli() }.getOrNull() } ?: sent.sentAt,
     answeredAt = if (answered) now else null,
-    transcript = result?.transcript,
+    // A text ask's question is what was typed (slice 5 spec §5.4), also when no result came.
+    transcript = result?.transcript ?: sent.question,
     answer = result?.answer,
     latitude = sent.here?.latitude,
     longitude = sent.here?.longitude,
     address = result?.address,
     headingDegrees = result?.headingDegrees,
-    input = ASK_INPUT_VOICE,
+    input = sent.input,
     conversationId = sent.conversationId,
     newConversation = sent.newConversation,
     outcome = if (answered) AskOutcome.ANSWERED else AskOutcome.FAILED,
diff --git a/app/src/main/java/com/touringproject/v2/ask/Flow.kt b/app/src/main/java/com/touringproject/v2/ask/Flow.kt
index 86e8442..5db6cdd 100644
--- a/app/src/main/java/com/touringproject/v2/ask/Flow.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/Flow.kt
@@ -37,6 +37,8 @@ sealed interface FlowEvent {
     val mediaVolume: MediaVolume? = null,
     val recordLimitMs: Long = DEFAULT_RECORD_LIMIT_MS,
   ) : FlowEvent
+  /** A text ask from Home (slice 5 spec §5.3): nothing to record, so it starts as it is sent. */
+  data class StartText(override val now: Long) : FlowEvent
   data class PhoneMic(override val now: Long) : FlowEvent
   data class StopRecording(override val now: Long) : FlowEvent
   data class Sent(val askId: String, override val now: Long) : FlowEvent
@@ -54,6 +56,8 @@ fun reduce(state: FlowState, event: FlowEvent): FlowState = when (event) {
         recordLimitMs = event.recordLimitMs,
       )
     } else state
+  is FlowEvent.StartText ->
+    if (state.phase == Phase.IDLE || state.phase == Phase.FAILED) FlowState(phase = Phase.SENDING, source = Source.SCREEN, phaseStartedAt = event.now) else state
   is FlowEvent.PhoneMic -> if (state.phase == Phase.RECORDING) state.copy(phoneMic = true) else state
   is FlowEvent.StopRecording ->
     if (state.phase == Phase.RECORDING) state.copy(phase = Phase.SENDING, phaseStartedAt = event.now) else state
diff --git a/app/src/main/java/com/touringproject/v2/ask/TextAsk.kt b/app/src/main/java/com/touringproject/v2/ask/TextAsk.kt
new file mode 100644
index 0000000..0c78180
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/ask/TextAsk.kt
@@ -0,0 +1,25 @@
+package com.touringproject.v2.ask
+
+// Asking by text from Home (slice 5 spec §5, US-A-08).
+
+/** The sheet takes up to 500 characters, counted as code points like the other texts the Backend takes. */
+const val TEXT_ASK_MAX = 500
+
+private fun String.characters() = codePointCount(0, length)
+
+/** What the sheet's field keeps of a typed or pasted text: its first 500 characters, never cutting an emoji in half. */
+fun cutTextAsk(input: String): String =
+  if (input.characters() <= TEXT_ASK_MAX) input else input.substring(0, input.offsetByCodePoints(0, TEXT_ASK_MAX))
+
+/** How many more characters the field takes. */
+fun textAskLeft(input: String): Int = TEXT_ASK_MAX - input.characters()
+
+/** The question sent: trimmed, or null when it is only blanks (「質問する」 cannot be pressed then). */
+fun textQuestion(input: String): String? = input.trim().takeIf { it.isNotEmpty() && it.characters() <= TEXT_ASK_MAX }
+
+/**
+ * What became of a text ask, for the sheet. SENT: the Backend took it, so the sheet closes and SC-03 waits for the
+ * answer. OFFLINE: it could not reach the Backend; the sheet stays with the text and says so (no unreached ask is
+ * kept). NOT_TAKEN: refused or let go before it was taken (SC-03 has said why); the sheet stays with the text.
+ */
+enum class TextAskOutcome { SENT, OFFLINE, NOT_TAKEN }
diff --git a/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt b/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt
index 98caba8..7e24283 100644
--- a/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt
+++ b/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt
@@ -1,11 +1,15 @@
 package com.touringproject.v2.location
 
 import com.touringproject.v2.ask.Positions
+import kotlinx.coroutines.suspendCancellableCoroutine
+import kotlinx.coroutines.withTimeoutOrNull
+import kotlin.coroutines.resume
 
 // Collects position fixes while a question is recorded, only to tell where it was asked: the heading comes from the
 // ride's route (slice 5 spec §4.1). A last-known point older than MAX_CURRENT_AGE_MS is not sent as the current
 // position, and callbacks that belong to an earlier begin() are ignored.
 const val MAX_CURRENT_AGE_MS = 30_000L
+const val LATEST_WAIT_MS = 2_000L
 
 fun interface Subscription {
   fun remove()
@@ -43,4 +47,17 @@ class PositionTracker(private val source: PositionSource) : Positions {
     fixes.clear()
     return latest?.takeIf { source.now() - it.timestamp <= MAX_CURRENT_AGE_MS }
   }
+
+  /**
+   * The ride's route keeps Fused's last fix fresh while a ride records (every 5 s), which is when text asks are taken.
+   * None comes when there is no fix, or no permission; the wait is cut off at LATEST_WAIT_MS.
+   */
+  override suspend fun latest(): Fix? {
+    val fix = withTimeoutOrNull(LATEST_WAIT_MS) {
+      suspendCancellableCoroutine<Fix?> { cont ->
+        runCatching { source.lastKnown { if (cont.isActive) cont.resume(it) } }.onFailure { if (cont.isActive) cont.resume(null) }
+      }
+    }
+    return fix?.takeIf { source.now() - it.timestamp <= MAX_CURRENT_AGE_MS }
+  }
 }
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun`
Expected: PASS（642件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/TextAsk.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/ask/AskRecord.kt app/src/main/java/com/touringproject/v2/ask/Flow.kt app/src/main/java/com/touringproject/v2/location/PositionTracker.kt
cd $AND && git add app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/ask/FlowTest.kt app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
git commit -m "feat: ask by text through the ask loop, without an unreached ask when offline

Fixes #30"
```

---

### Task 9: ホームの「⌨ 文字で質問」とシート

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ui/TextAskSheet.kt`
- Modify: `ui/HomeScreen.kt`・`ui/AppUi.kt`
- Test: `ui/TextAskSheetTest.kt`（新規）・`ui/ScreensTest.kt`・`ui/AppUiTest.kt`

**Interfaces:**
- Consumes: Task 8 の `AskController.askText`・`TextAskOutcome`・字数の決まり。
- Produces: `data class TextSheet(open, text, message, sending)`・`fun TextSheet.after(outcome): TextSheet`・`val TextSheetSaver`・`const val TEXT_ASK_OFFLINE_MESSAGE = "通信できません"`。`@Composable fun TextAskSheet(sheet, onText, onSend, onDismiss)`（テストの印 `textAskInput`・`textAskLeft`・`textAskMessage`・`textAskSend`）。`HomeScreen(..., onTextAsk: () -> Unit = {})`（印 `textAsk`）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
index d08d20f..21d2670 100644
--- a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
@@ -1,5 +1,6 @@
 package com.touringproject.v2.ui
 
+import androidx.compose.ui.test.assertIsNotEnabled
 import androidx.compose.ui.test.assertTextContains
 import androidx.compose.ui.test.junit4.createAndroidComposeRule
 import androidx.compose.ui.test.onNodeWithTag
@@ -128,6 +129,22 @@ class AppUiTest {
     rule.waitUntil(5_000) { !rule.onAllNodesWithTagExists("tab-HOME") }
   }
 
+  // Slice 5 spec §5.1: while a ride records, 「⌨ 文字で質問」 opens the sheet, which keeps the text over a recreation.
+  @Test
+  fun the_text_sheet_opens_while_a_ride_records_and_keeps_its_text() {
+    val graph = (rule.activity.application as TouringApp).graph
+    rule.onNodeWithTag("textAsk").assertIsNotEnabled()
+    runBlocking { graph.rides.start("箱根") }
+    rule.waitUntil(5_000) { rule.onAllNodes(androidx.compose.ui.test.hasTestTag("textAsk").and(androidx.compose.ui.test.isEnabled())).fetchSemanticsNodes().isNotEmpty() }
+    rule.onNodeWithTag("textAsk").performClick()
+    rule.onNodeWithTag("textAskInput").performTextInput("右手の山は？")
+    rule.activityRule.scenario.recreate()
+    rule.waitUntil(5_000) { rule.onAllNodesWithTagExists("textAskInput") }
+    rule.onNodeWithTag("textAskInput").assertTextContains("右手の山は？")
+    rule.onNodeWithText("やめる").performClick()
+    rule.waitUntil(5_000) { !rule.onAllNodesWithTagExists("textAskInput") }
+  }
+
   @Test
   fun the_start_sheet_stays_open_when_the_activity_is_recreated() {
     rule.onNodeWithTag("startRide").performClick()
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index e9855c1..4a319cd 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -52,6 +52,19 @@ class HomeScreenTest {
     assertEquals(1, taps)
   }
 
+  // Slice 5 spec §5.1: 「⌨ 文字で質問」 stands next to 「🎤 押して話す」 and, like it, only while asks are taken.
+  @Test
+  fun the_text_ask_button_opens_the_sheet_only_while_asks_are_taken() {
+    var hint by mutableStateOf<String?>(null)
+    var opened = 0
+    rule.setContent { HomeScreen(HomeUi("rider01", null, "新しい会話です", askHint = hint), {}, {}, {}, {}, onTextAsk = { opened++ }) }
+    rule.onNodeWithText("⌨ 文字で質問").performClick()
+    assertEquals(1, opened)
+    hint = "再開すると、インカムのボタンで話せます"
+    rule.onNodeWithTag("textAsk").assertIsNotEnabled().performClick()
+    assertEquals(1, opened)
+  }
+
   // Slice 2 spec §4.7: without a recording ride the button stays where it is but cannot be pressed, and says why.
   @Test
   fun without_a_recording_ride_tap_to_talk_cannot_be_pressed_and_the_hint_says_why() {
diff --git a/app/src/test/java/com/touringproject/v2/ui/TextAskSheetTest.kt b/app/src/test/java/com/touringproject/v2/ui/TextAskSheetTest.kt
new file mode 100644
index 0000000..8b7b24d
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/ui/TextAskSheetTest.kt
@@ -0,0 +1,74 @@
+package com.touringproject.v2.ui
+
+import androidx.compose.runtime.getValue
+import androidx.compose.runtime.mutableStateOf
+import androidx.compose.runtime.setValue
+import androidx.compose.ui.test.assertIsEnabled
+import androidx.compose.ui.test.assertIsNotEnabled
+import androidx.compose.ui.test.assertTextEquals
+import androidx.compose.ui.test.junit4.createComposeRule
+import androidx.compose.ui.test.onNodeWithTag
+import androidx.compose.ui.test.onNodeWithText
+import androidx.compose.ui.test.performClick
+import androidx.compose.ui.test.performTextInput
+import androidx.test.ext.junit.runners.AndroidJUnit4
+import com.touringproject.v2.ask.TextAskOutcome
+import org.junit.Assert.assertEquals
+import org.junit.Rule
+import org.junit.Test
+import org.junit.runner.RunWith
+
+// Slice 5 spec §5.2 and §5.3: Home's text sheet.
+@RunWith(AndroidJUnit4::class)
+class TextAskSheetTest {
+  @get:Rule val rule = createComposeRule()
+
+  private var sheet by mutableStateOf(TextSheet(open = true))
+  private val sent = mutableListOf<String>()
+  private var dismissed = 0
+
+  private fun show() = rule.setContent {
+    TextAskSheet(sheet, onText = { sheet = sheet.copy(text = it) }, onSend = { sent += it }, onDismiss = { dismissed++ })
+  }
+
+  @Test
+  fun a_blank_text_cannot_be_asked_and_a_question_goes_trimmed() {
+    show()
+    rule.onNodeWithTag("textAskLeft").assertTextEquals("残り 500字 · 回答は読み上げます")
+    rule.onNodeWithTag("textAskSend").assertIsNotEnabled()
+    rule.onNodeWithTag("textAskInput").performTextInput("  \n ")
+    rule.onNodeWithTag("textAskSend").assertIsNotEnabled()
+    rule.onNodeWithTag("textAskInput").performTextInput("右手の山は？")
+    rule.onNodeWithTag("textAskLeft").assertTextEquals("残り 490字 · 回答は読み上げます")
+    rule.onNodeWithTag("textAskSend").assertIsEnabled().performClick()
+    assertEquals(listOf("右手の山は？"), sent)
+  }
+
+  @Test
+  fun a_pasted_text_is_cut_at_500_characters() {
+    show()
+    rule.onNodeWithTag("textAskInput").performTextInput("あ".repeat(520))
+    assertEquals(500, sheet.text.length)
+    rule.onNodeWithTag("textAskLeft").assertTextEquals("残り 0字 · 回答は読み上げます")
+  }
+
+  @Test
+  fun the_sheet_says_it_cannot_reach_the_network_and_waits_while_sending() {
+    sheet = TextSheet(open = true, text = "右手の山は？", message = TEXT_ASK_OFFLINE_MESSAGE)
+    show()
+    rule.onNodeWithTag("textAskMessage").assertTextEquals("通信できません")
+    sheet = sheet.copy(sending = true)
+    rule.onNodeWithTag("textAskSend").assertIsNotEnabled()
+    rule.onNodeWithText("やめる").performClick()
+    assertEquals(1, dismissed)
+  }
+
+  // §5.3: taken, the sheet closes and forgets the text; not reached, it keeps the text and says so; refused, it keeps it.
+  @Test
+  fun what_became_of_the_text_decides_the_sheet() {
+    val sending = TextSheet(open = true, text = "右手の山は？", sending = true)
+    assertEquals(TextSheet(), sending.after(TextAskOutcome.SENT))
+    assertEquals(TextSheet(open = true, text = "右手の山は？", message = "通信できません"), sending.after(TextAskOutcome.OFFLINE))
+    assertEquals(TextSheet(open = true, text = "右手の山は？"), sending.copy(message = "通信できません").after(TextAskOutcome.NOT_TAKEN))
+  }
+}
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TextAskSheetTest' --tests '*HomeScreenTest' --tests '*AppUiTest'`
Expected: コンパイルで落ちる（`TextAskSheet`・`TextSheet`・`onTextAsk` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 768283b..0718132 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -36,6 +36,7 @@ import androidx.navigation3.ui.NavDisplay
 import com.touringproject.v2.AppGraph
 import com.touringproject.v2.BuildConfig
 import com.touringproject.v2.api.ApiClient
+import com.touringproject.v2.ask.Phase
 import com.touringproject.v2.ask.isBusy
 import com.touringproject.v2.ask.rideNow
 import com.touringproject.v2.records.NoteDraft
@@ -101,6 +102,8 @@ fun AppUi(graph: AppGraph) {
   var mapFull by remember { mutableStateOf(false) }
   // Saveable: SC-17 and SC-04 stay open when the activity is recreated, e.g. on rotation (Android #20).
   var sheet by rememberSaveable { mutableStateOf<RideSheet?>(null) }
+  // Home's text sheet (slice 5 spec §5.2); kept while SC-03 covers the screen, so a text not taken comes back.
+  var textSheet by rememberSaveable(stateSaver = TextSheetSaver) { mutableStateOf(TextSheet()) }
   val now = rememberNow(ride != null)
   val context = LocalContext.current
   val scope = rememberCoroutineScope()
@@ -176,6 +179,7 @@ fun AppUi(graph: AppGraph) {
                       }
                     }
                   },
+                  onTextAsk = { textSheet = textSheet.copy(open = true, message = null) },
                 )
               }
               entry<RecordsKey> {
@@ -372,6 +376,20 @@ fun AppUi(graph: AppGraph) {
         }
         // The ride may end elsewhere (deadline, shutdown) while SC-04 is open.
         LaunchedEffect(ride == null) { if (ride == null && sheet == RideSheet.END) sheet = null }
+        // The sheet is a window above everything, so it steps aside while SC-03 shows the ask (slice 5 spec §5.3).
+        if (textSheet.open && state.phase == Phase.IDLE) {
+          TextAskSheet(
+            textSheet,
+            onText = { textSheet = textSheet.copy(text = it) },
+            onSend = { question ->
+              if (!textSheet.sending) {
+                textSheet = textSheet.copy(sending = true, message = null)
+                graph.controller.askText(question) { outcome -> textSheet = textSheet.after(outcome) }
+              }
+            },
+            onDismiss = { textSheet = TextSheet() },
+          )
+        }
         Column(Modifier.fillMaxSize()) {
           AskOverlay(
             state, System::currentTimeMillis, graph.controller::stopRecording, graph.controller::cancel,
diff --git a/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt b/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
index c59c218..fbeb0de 100644
--- a/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
@@ -98,13 +98,22 @@ fun HomeScreen(
   ride: @Composable () -> Unit = {},
   onDismissAskFailure: () -> Unit = {},
   onNote: (() -> Unit)? = null,
+  onTextAsk: () -> Unit = {},
 ) {
   var confirming by remember { mutableStateOf(false) }
   Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
     Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
       Text(ui.userName, Modifier.clickable(onClick = onUser), fontSize = 22.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
-      // Settings is a tab now (slice 2 spec §7.1).
-      OutlinedButton(onClick = onTapToTalk, Modifier.testTag("tapToTalk"), enabled = ui.askHint == null) { Text("🎤 押して話す") }
+      // Settings is a tab now (slice 2 spec §7.1). Both asks from the screen are quiet buttons for tests and stops
+      // (US-B-05.006), taken only while a ride records (slice 5 spec §5.1).
+      Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
+        OutlinedButton(onClick = onTapToTalk, Modifier.testTag("tapToTalk"), enabled = ui.askHint == null, contentPadding = PaddingValues(horizontal = 10.dp)) {
+          Text("🎤 押して話す")
+        }
+        OutlinedButton(onClick = onTextAsk, Modifier.testTag("textAsk"), enabled = ui.askHint == null, contentPadding = PaddingValues(horizontal = 10.dp)) {
+          Text("⌨ 文字で質問")
+        }
+      }
     }
     ui.banner?.let { banner ->
       val close = when (banner) {
diff --git a/app/src/main/java/com/touringproject/v2/ui/TextAskSheet.kt b/app/src/main/java/com/touringproject/v2/ui/TextAskSheet.kt
new file mode 100644
index 0000000..761d113
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/ui/TextAskSheet.kt
@@ -0,0 +1,84 @@
+package com.touringproject.v2.ui
+
+import androidx.compose.foundation.layout.Arrangement
+import androidx.compose.foundation.layout.Column
+import androidx.compose.foundation.layout.fillMaxWidth
+import androidx.compose.foundation.layout.heightIn
+import androidx.compose.foundation.layout.padding
+import androidx.compose.material3.Button
+import androidx.compose.material3.ExperimentalMaterial3Api
+import androidx.compose.material3.FilledTonalButton
+import androidx.compose.material3.MaterialTheme
+import androidx.compose.material3.ModalBottomSheet
+import androidx.compose.material3.OutlinedTextField
+import androidx.compose.material3.Text
+import androidx.compose.runtime.Composable
+import androidx.compose.runtime.saveable.listSaver
+import androidx.compose.ui.Modifier
+import androidx.compose.ui.graphics.Color
+import androidx.compose.ui.platform.testTag
+import androidx.compose.ui.text.font.FontWeight
+import androidx.compose.ui.text.style.TextAlign
+import androidx.compose.ui.unit.dp
+import androidx.compose.ui.unit.sp
+import com.touringproject.v2.ask.TextAskOutcome
+import com.touringproject.v2.ask.cutTextAsk
+import com.touringproject.v2.ask.textAskLeft
+import com.touringproject.v2.ask.textQuestion
+
+const val TEXT_ASK_OFFLINE_MESSAGE = "通信できません"
+
+/**
+ * Home's text sheet (slice 5 spec §5.2): whether it is open, what is typed, what it says, and whether a send is under
+ * way. It lives above the sheet, so the text stays while SC-03 covers the screen and the sheet comes back with it.
+ */
+data class TextSheet(val open: Boolean = false, val text: String = "", val message: String? = null, val sending: Boolean = false)
+
+/** What the sheet becomes once the ask loop has told what became of the text (TextAskOutcome). */
+fun TextSheet.after(outcome: TextAskOutcome): TextSheet = when (outcome) {
+  TextAskOutcome.SENT -> TextSheet()
+  TextAskOutcome.OFFLINE -> copy(sending = false, message = TEXT_ASK_OFFLINE_MESSAGE)
+  TextAskOutcome.NOT_TAKEN -> copy(sending = false, message = null)
+}
+
+/** Keeps the sheet when the activity is recreated, like SC-17's name. */
+val TextSheetSaver = listSaver<TextSheet, Any?>(
+  save = { listOf(it.open, it.text, it.message) },
+  restore = { TextSheet(it[0] as Boolean, it[1] as String, it[2] as String?) },
+)
+
+/**
+ * SC-02's 「⌨ 文字で質問」 sheet (slice 5 spec §5.2): up to 500 characters with what is left, 「質問する」 only for a
+ * question that is not just blanks, and 「やめる」.
+ */
+@OptIn(ExperimentalMaterial3Api::class)
+@Composable
+fun TextAskSheet(sheet: TextSheet, onText: (String) -> Unit, onSend: (String) -> Unit, onDismiss: () -> Unit) {
+  val question = textQuestion(sheet.text)
+  ModalBottomSheet(onDismissRequest = onDismiss) {
+    Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
+      Text("文字で質問", fontSize = 20.sp, fontWeight = FontWeight.Bold)
+      OutlinedTextField(
+        value = sheet.text,
+        onValueChange = { onText(cutTextAsk(it)) },
+        placeholder = { Text("例: 右手に見える山は何？") },
+        minLines = 3,
+        modifier = Modifier.fillMaxWidth().testTag("textAskInput"),
+      )
+      Text(
+        "残り ${textAskLeft(sheet.text)}字 · 回答は読み上げます",
+        Modifier.fillMaxWidth().testTag("textAskLeft"),
+        color = MaterialTheme.colorScheme.onSurfaceVariant,
+        fontSize = 14.sp,
+        textAlign = TextAlign.End,
+      )
+      sheet.message?.let { Text(it, color = Color(0xFFD42A2A), modifier = Modifier.testTag("textAskMessage")) }
+      Button(
+        onClick = { question?.let(onSend) },
+        enabled = question != null && !sheet.sending,
+        modifier = Modifier.fillMaxWidth().heightIn(min = 60.dp).testTag("textAskSend"),
+      ) { Text("質問する", fontSize = 18.sp) }
+      FilledTonalButton(onClick = onDismiss, Modifier.fillMaxWidth()) { Text("やめる") }
+    }
+  }
+}
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun`
Expected: PASS（648件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/TextAskSheet.kt app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/test/java/com/touringproject/v2/ui/TextAskSheetTest.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
git commit -m "feat: add Home's text ask button and its sheet"
```

---

### Task 10: 録音を POST の前に残し、質問できなかった地点になったら消す（#68）

**Files:**
- Modify: `ask/AskPorts.kt`・`ask/AskController.kt`・`recordings/RecordingStore.kt`
- Test: `ask/AskControllerTest.kt`・`recordings/RecordingStoreTest.kt`

**Interfaces:**
- Produces: `RecordingSink.discarded(name: String)`。`RecordingStore.delete(name: String)`（録音の名前でなければ何もしない）。`RecordingKeeper.discarded`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index 42749c2..3b2c4cf 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -79,8 +79,10 @@ private class Harness(
   val log = mutableListOf<String>()
   val states = mutableListOf<FlowState>()
   val bodies = mutableListOf<AskBody>()
+  /** The recordings SC-12 keeps now: saved and not discarded again. */
   val metas = mutableListOf<RecordingMeta>()
   val keptPcm = mutableListOf<ByteArray>()
+  val discarded = mutableListOf<String>()
   val transcripts = mutableListOf<Pair<String, String>>()
   val kept = mutableListOf<AskRecord>()
   private val results = answers.toMutableList()
@@ -126,6 +128,11 @@ private class Harness(
     },
     recordings = object : RecordingSink {
       override fun saved(meta: RecordingMeta, pcm: ByteArray) { metas += meta; keptPcm += pcm }
+      override fun discarded(name: String) {
+        discarded += name
+        val at = metas.indexOfFirst { it.name == name }
+        if (at >= 0) { metas.removeAt(at); keptPcm.removeAt(at) }
+      }
       override fun transcribed(name: String, transcript: String) { transcripts += name to transcript }
     },
     asks = { kept += it },
@@ -683,6 +690,25 @@ class AskControllerTest {
     assertEquals(1, h.metas.size)
   }
 
+  // Android #68: the recording is kept before the POST and its retries, so a process that dies meanwhile does not lose
+  // the recording of an ask the Backend took; one whose send failed on the network goes again.
+  @Test
+  fun the_recording_is_kept_before_the_post_and_goes_again_when_the_network_fails() = runTest {
+    var keptAtPost = -1
+    lateinit var h: Harness
+    h = Harness(this, stopAfterMs = 1_000, post = { keptAtPost = h.metas.size; ACCEPTED })
+    h.controller.run(Source.HANDSFREE)
+    assertEquals(1, keptAtPost)
+    assertEquals(1, h.metas.size)
+    assertTrue(h.discarded.isEmpty())
+    val failed = Harness(this, stopAfterMs = 1_000)
+    failed.post = { keptAtPost = failed.metas.size; throw ApiError(ApiErrorKind.NETWORK) }
+    failed.controller.run(Source.HANDSFREE)
+    assertEquals(1, keptAtPost)
+    assertEquals(listOf("rec-0.pcm"), failed.discarded)
+    assertTrue(failed.metas.isEmpty())
+  }
+
   // The rider cancelled while the ask was being sent: they let it go, so it is not kept even when the send fails.
   @Test
   fun an_ask_cancelled_while_sending_is_not_kept_as_unreached() = runTest {
diff --git a/app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt b/app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt
index f88cbdd..36e9571 100644
--- a/app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt
+++ b/app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt
@@ -88,6 +88,22 @@ class RecordingStoreTest {
     assertEquals(before + 3, store.changes.value)
   }
 
+  // Android #68: the recording of an ask that never reached the Backend goes again, after its save.
+  @Test
+  fun a_recording_saved_then_discarded_is_gone_with_its_json() = runTest {
+    val keeper = RecordingKeeper(RecordingStore(dir, io = StandardTestDispatcher(testScheduler)), this) { _, _ -> }
+    keeper.saved(meta(100), byteArrayOf(1))
+    keeper.saved(meta(200), byteArrayOf(2))
+    keeper.discarded("rec-100.pcm")
+    testScheduler.advanceUntilIdle()
+    assertEquals(listOf("rec-200.json", "rec-200.pcm"), dir.list()!!.sorted())
+    // One already gone, or a name that is no recording, changes nothing.
+    val store = RecordingStore(dir)
+    store.delete("rec-100.pcm")
+    store.delete("../rec-200.pcm")
+    assertEquals(listOf(meta(200)), store.list())
+  }
+
   @Test
   fun the_keeper_never_lets_a_store_failure_reach_the_ask() = runTest {
     // A file where the directory should be: every write fails.
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*AskControllerTest' --tests '*RecordingStoreTest'`
Expected: コンパイルで落ちる（`RecordingSink.discarded` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index d27ecc1..bfe30aa 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -52,7 +52,7 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
   // Per-ask state: an older ask that is still unwinding must not read or change the newer one's.
   private class Run(val id: Int, val source: Source, var returned: Boolean = false)
 
-  // meta and pcm go to SC-12 once the ask has reached the Backend, or failed there; an unreached ask's recording goes.
+  // meta and pcm go to SC-12 as the ask is sent; an unreached ask's recording goes again (Android #68).
   // heading is worked out once, where the recording ended, for the ask sent and the unreached one alike.
   private class Recording(
     val audio: String,
@@ -377,6 +377,9 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       conversationId = d.conversation.current(d.now()),
       rideId = rideId,
     )
+    // Kept for SC-12 before the POST, which may take retries: the process may die meanwhile, and an ask the Backend took
+    // should keep its recording (Android #68). One that never reaches the Backend loses it again (US-C-09.001).
+    d.recordings.saved(recording.meta, recording.pcm)
     val accepted = try {
       api.postAsk(body)
     } catch (e: Exception) {
@@ -384,14 +387,13 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       val reason = reasonFor(e)
       // The Backend did not take the ask in (slice 4 spec §4.1); a refusal (the key, the request) is no unreached ask.
       if (reason == FailureReason.NETWORK) {
+        d.recordings.discarded(recording.name)
         keepUnreached(recording, rideId, run)
         return null
       }
-      d.recordings.saved(recording.meta, recording.pcm)
       fail(reason, run)
       return null
     }
-    d.recordings.saved(recording.meta, recording.pcm)
     // The ask exists on the Backend either way, so keep the conversation going even if it was cancelled.
     d.conversation.update(accepted.conversationId, accepted.conversationExpiresAt)
     if (!isCurrent(run)) return null
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
index b49eb48..430b49d 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
@@ -38,10 +38,12 @@ data class RecordingMeta(
   val transcript: String?,
 )
 
-/** Fire and forget: a failure here must not end the ask. */
+/** Fire and forget: a failure here must not end the ask. Each call is carried out after the ones before it. */
 interface RecordingSink {
   fun saved(meta: RecordingMeta, pcm: ByteArray)
   fun transcribed(name: String, transcript: String)
+  /** The recording saved goes again: its ask never reached the Backend (US-C-09.001). */
+  fun discarded(name: String)
 }
 
 /** Fire and forget: a failure to keep an ask must not end it. */
diff --git a/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt b/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt
index a5c0f03..e4b0780 100644
--- a/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt
+++ b/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt
@@ -74,6 +74,13 @@ class RecordingStore(private val dir: File, private val io: CoroutineDispatcher
     withContext(io) { File(dir, name).readBytes() }
   }
 
+  /** Removes one recording with its JSON; nothing happens when it is already gone. */
+  suspend fun delete(name: String) = change {
+    if (!PCM_RE.matches(name)) return@change
+    File(dir, name).delete()
+    File(dir, metaName(name)).delete()
+  }
+
   suspend fun deleteAll() = change { dir.deleteRecursively() }
 
   private suspend fun change(block: () -> Unit) {
@@ -102,6 +109,11 @@ class RecordingKeeper(
     scope.launch { guard("transcript") { store.setTranscript(name, transcript) } }
   }
 
+  // Launched after the save on the same scope; the store's lock takes them in that order.
+  override fun discarded(name: String) {
+    scope.launch { guard("discard") { store.delete(name) } }
+  }
+
   private suspend fun guard(what: String, block: suspend () -> Unit) {
     try {
       block()
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun`
Expected: PASS（650件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt
git commit -m "fix: keep an ask's recording before its POST, and drop it when the ask stays unreached

Fixes #68"
```

---

### Task 11: メディアの音量の帯（#8・#9）

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/audio/MediaVolumeWatch.kt`
- Modify: `AppGraph.kt`・`ui/HomeScreen.kt`・`ui/AppUi.kt`・`ui/Labels.kt`（`nextVolume` を消す）
- Test: `audio/MediaVolumeWatchTest.kt`（新規）・`ui/ScreensTest.kt`・`ui/LabelsTest.kt`

**Interfaces:**
- Produces: `class MediaVolumeWatch(read: () -> MediaVolume?)` の `volume: StateFlow<MediaVolume?>`・`dismissedAt: StateFlow<Int?>`・`fun refresh(): MediaVolume?`・`fun dismiss(level: Int)`。`AppGraph.mediaVolume`（`volumeDismissedAt`・`dismissVolumeWarning` は消す）。`rememberMediaVolume(readable: Boolean, watch: MediaVolumeWatch)`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/audio/MediaVolumeWatchTest.kt b/app/src/test/java/com/touringproject/v2/audio/MediaVolumeWatchTest.kt
new file mode 100644
index 0000000..07ecfe4
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/audio/MediaVolumeWatchTest.kt
@@ -0,0 +1,52 @@
+package com.touringproject.v2.audio
+
+import com.touringproject.v2.ui.volumeWarning
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertFalse
+import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
+import org.junit.Test
+
+// Slice 1 spec §5.6: the media volume Home and SC-03 warn about.
+class MediaVolumeWatchTest {
+  private val readings = ArrayDeque<MediaVolume?>()
+  private val watch = MediaVolumeWatch { readings.removeFirstOrNull() }
+
+  private fun read(vararg next: MediaVolume?): MediaVolume? {
+    readings.addAll(next)
+    var last: MediaVolume? = null
+    repeat(next.size) { last = watch.refresh() }
+    return last
+  }
+
+  // Android #9: AudioRoute.mediaVolume() is null while media still routes to the intercom's call link; the last good
+  // reading stays, for Home and for the next ask alike.
+  @Test
+  fun a_withheld_reading_keeps_the_last_good_one() {
+    assertNull(read(null))
+    assertEquals(MediaVolume(10, 15), read(MediaVolume(10, 15), null, null))
+    assertEquals(MediaVolume(10, 15), watch.volume.value)
+    assertEquals(MediaVolume(3, 15), read(MediaVolume(3, 15)))
+  }
+
+  @Test
+  fun a_reading_that_fails_keeps_the_last_good_one() {
+    read(MediaVolume(2, 15))
+    val failing = MediaVolumeWatch { error("no audio manager") }
+    assertNull(failing.refresh())
+    assertEquals(MediaVolume(2, 15), watch.refresh())
+  }
+
+  // Android #8: closed at 3, then 4, then back at 3: the band comes back.
+  @Test
+  fun a_dismissal_lasts_until_another_volume_is_read() {
+    read(MediaVolume(3, 15))
+    watch.dismiss(3)
+    assertFalse(volumeWarning(read(MediaVolume(3, 15)), watch.dismissedAt.value))
+    // A withheld reading is no change of volume.
+    assertFalse(volumeWarning(read(null), watch.dismissedAt.value))
+    read(MediaVolume(4, 15))
+    assertNull(watch.dismissedAt.value)
+    assertTrue(volumeWarning(read(MediaVolume(3, 15)), watch.dismissedAt.value))
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
index 002e863..d9b7f59 100644
--- a/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
@@ -81,13 +81,6 @@ class LabelsTest {
     assertFalse(volumeReadable(Phase.SPEAKING))
   }
 
-  @Test
-  fun a_withheld_reading_keeps_the_last_good_one() {
-    // AudioRoute.mediaVolume() is null while media still routes to the intercom's call link.
-    assertEquals(MediaVolume(10, 15), nextVolume(MediaVolume(10, 15), null))
-    assertEquals(MediaVolume(3, 15), nextVolume(MediaVolume(10, 15), MediaVolume(3, 15)))
-  }
-
   @Test
   fun a_dismissed_warning_stays_closed_until_the_volume_changes() {
     assertTrue(volumeWarning(MediaVolume(3, 15), null))
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index 4a319cd..ab12cff 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -24,6 +24,7 @@ import com.touringproject.v2.ask.Phase
 import com.touringproject.v2.ask.RecordingMeta
 import com.touringproject.v2.audio.InputDevice
 import com.touringproject.v2.audio.MediaVolume
+import com.touringproject.v2.audio.MediaVolumeWatch
 import com.touringproject.v2.recordings.TRIAL_IDLE
 import com.touringproject.v2.recordings.TrialPhase
 import com.touringproject.v2.recordings.TrialState
@@ -131,8 +132,9 @@ class HomeScreenTest {
   fun the_media_volume_is_read_while_home_is_shown_and_a_withheld_reading_keeps_the_last() {
     // 4b #2, and the carried-over rule: null (media on the call route) must not clear a low reading.
     val readings = ArrayDeque(listOf<MediaVolume?>(MediaVolume(2, 15), null))
+    val watch = MediaVolumeWatch { readings.removeFirstOrNull() }
     rule.setContent {
-      val volume = rememberMediaVolume(readable = true) { readings.removeFirstOrNull() }
+      val volume = rememberMediaVolume(readable = true, watch)
       Text(if (volumeWarning(volume, null)) "low" else "ok")
     }
     rule.onNodeWithText("low").assertIsDisplayed()
@@ -140,10 +142,29 @@ class HomeScreenTest {
     rule.onNodeWithText("low").assertIsDisplayed()
   }
 
+  // Android #9: a Home made anew (back from Settings) starts from the last good reading, though the next is withheld.
+  @Test
+  fun a_new_home_starts_from_the_last_good_reading() {
+    val readings = ArrayDeque(listOf<MediaVolume?>(MediaVolume(2, 15)))
+    val watch = MediaVolumeWatch { readings.removeFirstOrNull() }
+    watch.refresh()
+    var shown by mutableStateOf(true)
+    rule.setContent {
+      if (shown) {
+        val volume = rememberMediaVolume(readable = true, watch)
+        Text(if (volumeWarning(volume, null)) "low" else "ok")
+      }
+    }
+    shown = false
+    rule.waitForIdle()
+    shown = true
+    rule.onNodeWithText("low").assertIsDisplayed()
+  }
+
   @Test
   fun no_reading_is_taken_while_an_ask_holds_the_route() {
     var reads = 0
-    rule.setContent { rememberMediaVolume(readable = false) { reads++; MediaVolume(2, 15) } }
+    rule.setContent { rememberMediaVolume(readable = false, MediaVolumeWatch { reads++; MediaVolume(2, 15) }) }
     rule.mainClock.advanceTimeBy(VOLUME_CHECK_MS * 2)
     assertEquals(0, reads)
   }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*MediaVolumeWatchTest' --tests '*HomeScreenTest'`
Expected: コンパイルで落ちる（`MediaVolumeWatch` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 459b70a..fc0f9a4 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -17,6 +17,7 @@ import com.touringproject.v2.ask.rideNow
 import com.touringproject.v2.audio.AudioRoute
 import com.touringproject.v2.audio.AudioRouteControl
 import com.touringproject.v2.audio.ExoAnswerPlayer
+import com.touringproject.v2.audio.MediaVolumeWatch
 import com.touringproject.v2.audio.PcmPlayer
 import com.touringproject.v2.audio.PcmRecorder
 import com.touringproject.v2.audio.ToneCues
@@ -195,6 +196,9 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   val activeAskCount: StateFlow<Int> =
     activeAskCount(rides.active.map { it?.id }, database.asks()::countForRide).stateIn(scope, SharingStarted.Eagerly, 0)
 
+  /** The media volume for Home's band and SC-03's (slice 1 spec §5.6). */
+  val mediaVolume = MediaVolumeWatch { audioRoute.mediaVolume() }
+
   private val flowState = MutableStateFlow(IDLE)
   val state: StateFlow<FlowState> = flowState.asStateFlow()
 
@@ -207,7 +211,8 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       settings = settings::current,
       apiKey = { if (apiBaseUrl.isEmpty()) null else apiKeys.current() },
       micAllowed = micAllowed,
-      mediaVolume = { runCatching { audioRoute.mediaVolume() }.getOrNull() },
+      // Read before the intercom route takes the music stream over; a withheld reading keeps the last good one (Android #9).
+      mediaVolume = mediaVolume::refresh,
       api = { key, user -> ApiClient(apiBaseUrl, key, user, http) },
       conversation = conversation,
       route = AudioRouteControl(audioRoute),
@@ -284,13 +289,6 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     scope,
   )
 
-  // The media volume at which the rider closed the low-volume band; kept until the process ends (slice 1 spec §5.6).
-  private val volumeDismissed = MutableStateFlow<Int?>(null)
-  val volumeDismissedAt: StateFlow<Int?> = volumeDismissed.asStateFlow()
-
-  fun dismissVolumeWarning(level: Int) {
-    volumeDismissed.value = level
-  }
 
   private val router = PressRouter(
     trialActive = { trial.active },
diff --git a/app/src/main/java/com/touringproject/v2/audio/MediaVolumeWatch.kt b/app/src/main/java/com/touringproject/v2/audio/MediaVolumeWatch.kt
new file mode 100644
index 0000000..e61acad
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/audio/MediaVolumeWatch.kt
@@ -0,0 +1,33 @@
+package com.touringproject.v2.audio
+
+import kotlinx.coroutines.flow.MutableStateFlow
+import kotlinx.coroutines.flow.StateFlow
+import kotlinx.coroutines.flow.asStateFlow
+
+/**
+ * The media volume as Home and the ask loop know it, for the life of the process (slice 1 spec §5.6). A withheld
+ * reading (null while the intercom's call link lingers after an ask) keeps the last good one, so a screen made anew
+ * and the next ask still have it (Android #9). The rider's ✕ on the low-volume band lasts until another volume is
+ * read (Android #8). Call it from the main thread.
+ */
+class MediaVolumeWatch(private val read: () -> MediaVolume?) {
+  private val volumeState = MutableStateFlow<MediaVolume?>(null)
+  /** The last good reading; null until one has been had. */
+  val volume: StateFlow<MediaVolume?> = volumeState.asStateFlow()
+
+  private val dismissed = MutableStateFlow<Int?>(null)
+  /** The volume at which the rider closed the low-volume band; null once another one has been read. */
+  val dismissedAt: StateFlow<Int?> = dismissed.asStateFlow()
+
+  /** Reads the volume now, and returns the last good one when the reading is withheld or fails. */
+  fun refresh(): MediaVolume? {
+    val reading = runCatching { read() }.getOrNull()
+    if (reading != null && dismissed.value != null && reading.current != dismissed.value) dismissed.value = null
+    volumeState.value = reading ?: volumeState.value
+    return volumeState.value
+  }
+
+  fun dismiss(level: Int) {
+    dismissed.value = level
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 0718132..9f945c1 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -93,7 +93,7 @@ fun AppUi(graph: AppGraph) {
   val state by graph.state.collectAsStateWithLifecycle()
   val settings by graph.settings.settings.collectAsStateWithLifecycle()
   val apiKey by graph.apiKeys.apiKey.collectAsStateWithLifecycle()
-  val volumeDismissedAt by graph.volumeDismissedAt.collectAsStateWithLifecycle()
+  val volumeDismissedAt by graph.mediaVolume.dismissedAt.collectAsStateWithLifecycle()
   val ride by graph.rides.active.collectAsStateWithLifecycle()
   val storeFailed by graph.rides.storeFailed.collectAsStateWithLifecycle()
   val askStoreFailed by graph.askLog.failed.collectAsStateWithLifecycle()
@@ -132,7 +132,7 @@ fun AppUi(graph: AppGraph) {
         ) { inner ->
           val screens = entryProvider<NavKey> {
               entry<HomeKey> {
-                val volume = rememberMediaVolume(volumeReadable(state.phase)) { graph.audioRoute.mediaVolume() }
+                val volume = rememberMediaVolume(volumeReadable(state.phase), graph.mediaVolume)
                 val ui = HomeUi(
                   userName = current.userName,
                   banner = homeBanner(
@@ -152,7 +152,7 @@ fun AppUi(graph: AppGraph) {
                   onBanner = { tabs.open(Tab.SETTINGS, if (it == Banner.NO_KEY) ConnectionKey else ReturnAppKey) },
                   onNewConversation = graph.controller::resetConversation,
                   modifier = Modifier.safeDrawingPadding(),
-                  onDismissVolume = { volume?.let { graph.dismissVolumeWarning(it.current) } },
+                  onDismissVolume = { volume?.let { graph.mediaVolume.dismiss(it.current) } },
                   onDismissAskFailure = graph.askLog::dismiss,
                   ride = {
                     RideCard(
@@ -393,7 +393,7 @@ fun AppUi(graph: AppGraph) {
         Column(Modifier.fillMaxSize()) {
           AskOverlay(
             state, System::currentTimeMillis, graph.controller::stopRecording, graph.controller::cancel,
-            volumeDismissedAt = volumeDismissedAt, onDismissVolume = graph::dismissVolumeWarning,
+            volumeDismissedAt = volumeDismissedAt, onDismissVolume = graph.mediaVolume::dismiss,
           )
         }
       }
diff --git a/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt b/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
index fbeb0de..64697c9 100644
--- a/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
@@ -20,10 +20,10 @@ import androidx.compose.material3.Text
 import androidx.compose.material3.TextButton
 import androidx.compose.runtime.Composable
 import androidx.compose.runtime.LaunchedEffect
+import androidx.compose.runtime.collectAsState
 import androidx.compose.runtime.getValue
 import androidx.compose.runtime.mutableStateOf
 import androidx.compose.runtime.remember
-import androidx.compose.runtime.rememberUpdatedState
 import androidx.compose.runtime.setValue
 import androidx.compose.ui.Alignment
 import androidx.compose.ui.Modifier
@@ -37,6 +37,7 @@ import androidx.lifecycle.Lifecycle
 import androidx.lifecycle.compose.LocalLifecycleOwner
 import androidx.lifecycle.repeatOnLifecycle
 import com.touringproject.v2.audio.MediaVolume
+import com.touringproject.v2.audio.MediaVolumeWatch
 import kotlinx.coroutines.delay
 
 /** askHint is set while no ask can start (no ride recording: slice 2 spec §4.7); it says how to make one possible. */
@@ -46,18 +47,18 @@ const val VOLUME_CHECK_MS = 2_000L
 
 /**
  * The media volume, read every 2 s while the caller is on screen and the app is in front (slice 1 spec §5.6).
- * Reading stops while an ask holds the intercom route; a withheld reading keeps the last good one.
+ * Reading stops while an ask holds the intercom route. The watch keeps the last good reading for the process, so a
+ * Home made anew starts from it (Android #9).
  */
 @Composable
-fun rememberMediaVolume(readable: Boolean, read: () -> MediaVolume?): MediaVolume? {
-  var volume by remember { mutableStateOf<MediaVolume?>(null) }
-  val currentRead by rememberUpdatedState(read)
+fun rememberMediaVolume(readable: Boolean, watch: MediaVolumeWatch): MediaVolume? {
+  val volume by watch.volume.collectAsState()
   val lifecycle = LocalLifecycleOwner.current.lifecycle
-  LaunchedEffect(readable, lifecycle) {
+  LaunchedEffect(readable, lifecycle, watch) {
     if (!readable) return@LaunchedEffect
     lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
       while (true) {
-        volume = nextVolume(volume, runCatching { currentRead() }.getOrNull())
+        watch.refresh()
         delay(VOLUME_CHECK_MS)
       }
     }
diff --git a/app/src/main/java/com/touringproject/v2/ui/Labels.kt b/app/src/main/java/com/touringproject/v2/ui/Labels.kt
index e0da02d..15116c8 100644
--- a/app/src/main/java/com/touringproject/v2/ui/Labels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/Labels.kt
@@ -61,9 +61,6 @@ fun mediaVolumeLow(volume: MediaVolume?): Boolean = volume != null && volume.max
 /** While an ask holds the intercom route, the music stream reports the call device's volume, not the media one. */
 fun volumeReadable(phase: Phase): Boolean = phase == Phase.IDLE || phase == Phase.FAILED
 
-/** A null reading (media still on the intercom's call link, which lingers after an ask) keeps the last good one. */
-fun nextVolume(previous: MediaVolume?, reading: MediaVolume?): MediaVolume? = reading ?: previous
-
 /** Low, and not dismissed at this very level: a dismissal lasts until the volume changes. */
 fun volumeWarning(volume: MediaVolume?, dismissedAt: Int?): Boolean = mediaVolumeLow(volume) && volume?.current != dismissedAt
 
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun`
Expected: PASS（653件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/audio/MediaVolumeWatch.kt app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/ui/Labels.kt
cd $AND && git add app/src/test/java/com/touringproject/v2/audio/MediaVolumeWatchTest.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
git commit -m "fix: keep the last good media volume for the process, and forget a dismissal once the volume changes

Fixes #8
Fixes #9"
```

---

### Task 12: 録音をすべて消す（#10・#11）

**Files:**
- Modify: `recordings/RecordingStore.kt`・`ui/RecordingsScreen.kt`
- Test: `recordings/RecordingCheckTest.kt`・`ui/ScreensTest.kt`

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt b/app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt
index 8fe25c1..9c290af 100644
--- a/app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt
+++ b/app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt
@@ -131,6 +131,24 @@ class RecordingCheckTest {
     assertEquals(emptyList<RecordingMeta>(), w.check.items.value)
   }
 
+  // Android #10: files that cannot be deleted are told, and the list still shows them.
+  @Test
+  fun delete_all_that_cannot_delete_says_so() = runTest {
+    val w = World(this, folder.root)
+    w.store.save(meta(1), byteArrayOf(1))
+    testScheduler.advanceUntilIdle()
+    val dir = folder.root
+    dir.setWritable(false)
+    try {
+      w.check.deleteAll()
+      testScheduler.advanceUntilIdle()
+    } finally {
+      dir.setWritable(true)
+    }
+    assertEquals(DELETE_FAILED_MESSAGE, w.check.message.value)
+    assertEquals(1, w.check.items.value.size)
+  }
+
   @Test
   fun nothing_starts_while_a_question_runs() = runTest {
     val w = World(this, folder.root, askBusy = true)
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index ab12cff..adaee20 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -547,6 +547,23 @@ class RecordingsScreenTest {
     assertEquals(2, taps)
   }
 
+  // Android #11: a question that starts while DL-01 is open closes it, so 「消す」 cannot be pressed for nothing.
+  @Test
+  fun a_question_starting_closes_the_delete_all_confirmation() {
+    var busy by mutableStateOf(false)
+    var deleted = 0
+    rule.setContent { RecordingsScreen(ui(askBusy = busy), {}, {}, {}, { deleted++ }) }
+    rule.onNodeWithTag("deleteAll").performClick()
+    rule.onNodeWithText("録音をすべて消しますか？").assertExists()
+    busy = true
+    rule.waitForIdle()
+    rule.onNodeWithText("録音をすべて消しますか？").assertDoesNotExist()
+    busy = false
+    rule.waitForIdle()
+    rule.onNodeWithText("録音をすべて消しますか？").assertDoesNotExist()
+    assertEquals(0, deleted)
+  }
+
   @Test
   fun nothing_can_be_started_while_a_question_runs() {
     rule.setContent { RecordingsScreen(ui(askBusy = true), {}, {}, {}, {}) }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RecordingCheckTest' --tests '*RecordingsScreenTest'`
Expected: FAIL（`delete_all_that_cannot_delete_says_so`・`a_question_starting_closes_the_delete_all_confirmation`）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt b/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt
index e4b0780..b468781 100644
--- a/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt
+++ b/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt
@@ -16,6 +16,7 @@ import kotlinx.coroutines.sync.withLock
 import kotlinx.coroutines.withContext
 import kotlinx.serialization.json.Json
 import java.io.File
+import java.io.IOException
 
 // The newest recordings stay on the device for SC-12 (slice 1 spec §5.4): rec-<time>.pcm with rec-<time>.json beside it.
 const val KEEP_RECORDINGS = 10
@@ -81,7 +82,8 @@ class RecordingStore(private val dir: File, private val io: CoroutineDispatcher
     File(dir, metaName(name)).delete()
   }
 
-  suspend fun deleteAll() = change { dir.deleteRecursively() }
+  /** Throws when a file could not be deleted, so SC-12 can say so (Android #10); deleteRecursively only returns false. */
+  suspend fun deleteAll() = change { if (!dir.deleteRecursively()) throw IOException("recordings not all deleted") }
 
   private suspend fun change(block: () -> Unit) {
     try {
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt b/app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt
index 2d1b8ce..5ad8c36 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt
@@ -18,6 +18,7 @@ import androidx.compose.material3.HorizontalDivider
 import androidx.compose.material3.OutlinedButton
 import androidx.compose.material3.Text
 import androidx.compose.runtime.Composable
+import androidx.compose.runtime.LaunchedEffect
 import androidx.compose.runtime.getValue
 import androidx.compose.runtime.mutableStateOf
 import androidx.compose.runtime.remember
@@ -56,6 +57,8 @@ fun RecordingsScreen(
   modifier: Modifier = Modifier,
 ) {
   var confirming by remember { mutableStateOf(false) }
+  // A question started meanwhile would make 「消す」 do nothing; DL-01 goes with it (Android #11).
+  LaunchedEffect(ui.askBusy) { if (ui.askBusy) confirming = false }
   val trialActive = ui.trial.phase != TrialPhase.IDLE
   val text = trialText(ui.trial)
   Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun`
Expected: PASS（655件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt app/src/test/java/com/touringproject/v2/recordings/RecordingCheckTest.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
git commit -m "fix: tell when the recordings could not all be deleted, and close DL-01 when a question starts

Fixes #10
Fixes #11"
```

---

### Task 13: 版と文書

- [ ] **Step 1: README と版を直す**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/README.md b/README.md
index ebf08f1..07b9992 100644
--- a/README.md
+++ b/README.md
@@ -11,7 +11,7 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 | `app/src/main/java/com/touringproject/v2/ask/` | 一巡の状態機械（`Flow.kt`）・司令塔（`AskController.kt`）・外との窓口（`AskPorts.kt`）・質問の記録の組み立て（`AskRecord.kt`）・ポーリング・会話・失敗の読み上げ文 |
 | `.../api/` | Backend の API（`docs-parent/07a_openapi.yaml`）。`GET /records` で読み戻す記録の型は `Records.kt` |
 | `.../audio/` | インカムの経路・録音・再生・端末の音声・合図 |
-| `.../location/` | 質問の位置の監視と方位の材料の選び方・走行のルートの位置の頼み方と点のふるい分け（`Route.kt`） |
+| `.../location/` | 質問の位置の監視（`PositionTracker.kt`）・方位の求め方（`Heading.kt`、純粋）・走行のルートの位置の頼み方と点のふるい分け（`Route.kt`） |
 | `.../ride/` | 走行の型と計算（`Ride.kt`、純粋）・司令塔（`RideController.kt`）・外との窓口（`RidePorts.kt`） |
 | `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・質問のメモと削除（`RoomAskEdits.kt`）・地点メモ（`RoomNotes.kt`）・送信の置き場（`RoomSyncStore.kt`）・記録の画面の読み出しと未送信の数（`RoomRecords.kt`）・クラウドの記録を1つのトランザクションで入れる係（`RoomTakeover.kt`）。スキーマは `app/schemas/` に版ごとに残す |
 | `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋）・SC-14 の数（`Saving.kt`）・メモの決まり（`Memos.kt`、純粋）・地点メモの型と位置の選び方（`Notes.kt`、純粋）・質問と地点メモを変える窓口（`AskEdits.kt`・`NoteEdits.kt`） |
@@ -29,19 +29,23 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 
 - 走行の記録中と一巡のあいだは、前面サービスを動かす（無いと、画面を消したあと位置・通信・再生が止まる）。種類は、記録中は `location`、一巡のあいだは `microphone|mediaPlayback` を足す。Android 14 以降、この2つはアプリが前面にあるときにしか始められず、足せない（理由は親の `adr/0006`）。
 - 走行の状態を変えるのは `RideController` だけ。サービス・締め切りのアラーム・電源を切る知らせ・画面は、どれもこれを呼ぶ。起動したときは `load()` が先に、残っていた走行を片付ける（端末が止まっていれば終了、締め切りを過ぎていれば自動終了、それ以外は記録の再開）。最長時間を変えたときの締め切りの計算し直しも `maxRecordingChanged()` が行う（`AppGraph` が設定の変化を受けて呼ぶ）。名前の変更は `rename()`、走行のメモは `memo()`、終えた走行の削除は `delete()`（書き直し待ちの保存も捨てるので、消した走行が書き戻されない）。
-- 質問を受けるのは走行の記録中だけ。`AskController.run` の入口で `RideNow`（記録中・一時停止中・記録していない）を見て、記録中でなければ録音を始めず、理由を読み上げる。画面の「押して話す」も押せない形にする（親の spec 2 §4.7・adr/0008）。
+- 質問を受けるのは走行の記録中だけ。`AskController.run` の入口で `RideNow`（記録中・一時停止中・記録していない）を見て、記録中でなければ録音を始めず、理由を読み上げる。画面の「押して話す」「文字で質問」も押せない形にする（親の spec 2 §4.7・adr/0008）。受け付けるかどうかは `refusal(RideNow)` だけが決め、司令塔とホームの文言（`askHint`）の両方がこれを使う。
+- 進行方位は端末で求めて度数（`headingDegrees`）で送る（親の adr/0013・spec 5 §4）。材料は、記録中か一時停止中の走行の最後の区間のルートの点（`RouteHeading` が Room の `segmentTail` で新しい120点を読む）。新しい点から遡り、精度が精度の上限以内で今の位置から基準の距離以上離れた最初の点から今の位置への向きにする（`findHeading`）。基準の点が保つ上限より古い・今の位置が無いか精度が悪いときは方位なし。3つのパラメーターは設定（`Settings` の `heading*`）。質問は録音を終えたときの位置、文字の質問は送るときの端末の最後の位置（30秒以内。`Positions.latest`）、地点メモは開いたときの走行の最新の点で求める。スライス5より前に作った未送信の地点メモと質問できなかった地点は、行に残る古い材料（`sample*` の列）を `headingSample` で送る（Backend の #28 で外す）。
+- 録音の上限と開始の合図は設定（SC-11）の値を、質問の始まりに読む（SC-12 の試し録りも同じ値。SC-19 の声の入力は60秒・1.5秒のまま）。合図「なし」は 0 で、音を鳴らさない。
+- 文字の質問（ホームの「⌨ 文字で質問」のシート）は `AskController.askText` が受け、録音せずに送るところ（SC-03 の「送っています…」）から始まる。Backend が受け付けたらシートを閉じて回答待ちへ進む。通信できないとき（送る前に通信が無い・`POST` が通信の失敗）は、質問できなかった地点を作らず、シートに「通信できません」と出して文を残す。断られたとき（記録中でない・接続キー・Backend の 400 など）は SC-03 に理由を出し、シートに文を残す。シートは SC-03 のあいだ消え、終わると戻る（状態は `AppUi` が持つ）。質問の行の `input` は `text`、質問の文は打った文。
 - Room のスキーマを変えるときは、版を上げて Migration を書き、`app/schemas/` に書き出された JSON もコミットする。破壊的な作り直しは使わない。スキーマの JSON は debug のビルドの資産にも入る（Robolectric の `MigrationTestHelper` が読むため。release には入らない）。Entity や Migration を変えた直後のテストは `--rerun` で確かめる。
 - 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと・通信できるようになったとき（`reconnections`。プロセスが生きているあいだだけ）。契機では未送信を調べるだけで、送るものが無ければ通信しない。通信できないあいだは、契機が来ても通信を試さない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。
 - 1回の送信は、削除の印（`deletions`）→ 走行とルート → 地点メモ → 質問できなかった地点 → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため。質問できなかった地点のメモが、Backend で質問を見つけられるため）。記録を消すときは、同じトランザクションで削除の印を書く。送れない削除の印（知らない種類）は、ログ `sync_unsendable` に出して消す（残すと、毎回の送信がそこで止まる）。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
-- 地点メモ（SC-19）は、走行の記録中と一時停止中にホームの「📝 地点メモ」から開く。開いたときに、その走行の最後の点を位置に、質問と同じ選び方で方位の材料を決め（`noteDraft`）、保存するまで書かない。住所と方位は、最初に送ったときに Backend が決めて返し、端末はそれを行に書く（`notes.address`・`headingDegrees`）。地図のピンは緑で、質問とは別の通し番号。質問の一巡が終わったときに、その走行が消えていれば質問は書かない（`AskDao.keep`）。
-- 質問できなかった地点（US-C-09）: 録音を終えた時点で通信できないとき、または `POST /asks` が通信の失敗（試し直しのあとの 5xx・流量の制限を含む）に終わったとき、質問の一巡は日時・位置・方位の材料を `asks` に `status = offline` で残す（識別子は端末で作る。会話の識別子は無い）。録音は捨て、SC-12 にも残さない。会話の文脈は進めない。接続キーの誤りなど、断られた失敗では残さない。書けたらすぐ送信の契機を呼ぶ（通信の失敗でも、既定のネットワークは残っていることがあるため）。`PUT /asks/{askId}/offline` で送り、応答の住所と方位を行に書く。409（同じ識別子の質問が Backend にある）は断られたものとして扱う。住所を決められずに受け付けられた地点メモと質問できなかった地点は、起動ごとに一度、版を進めて送り直す（Backend は新しい版でだけ住所を求め直す）。
+- 地点メモ（SC-19）は、走行の記録中と一時停止中にホームの「📝 地点メモ」から開く。開いたときに、その走行の最後の点を位置に、質問と同じ求め方で方位を決め（`RoomNotes.draft`）、保存するまで書かない。方位は端末の値を `notes.headingDegrees` に書いて送り、住所と Backend が決めた方位は、最初に送ったときの応答で行に書く。地図のピンは緑で、質問とは別の通し番号。質問の一巡が終わったときに、その走行が消えていれば質問は書かない（`AskDao.keep`）。
+- 質問できなかった地点（US-C-09）: 録音を終えた時点で通信できないとき、または `POST /asks` が通信の失敗（試し直しのあとの 5xx・流量の制限を含む）に終わったとき、質問の一巡は日時・位置・方位を `asks` に `status = offline` で残す（識別子は端末で作る。会話の識別子は無い）。録音は `POST` の前に SC-12 へ残し（試し直しのあいだにプロセスが死んでも、受け付けられた質問の録音が残るように）、質問できなかった地点になったら消す。会話の文脈は進めない。接続キーの誤りなど、断られた失敗では残さない。書けたらすぐ送信の契機を呼ぶ（通信の失敗でも、既定のネットワークは残っていることがあるため）。`PUT /asks/{askId}/offline` で送り、応答の住所と方位を行に書く。409（同じ識別子の質問が Backend にある）は断られたものとして扱う。住所を決められずに受け付けられた地点メモと質問できなかった地点は、起動ごとに一度、版を進めて送り直す（Backend は新しい版でだけ住所を求め直す）。
 - クラウドの記録を読み込むのは、SC-18 でユーザー名を変えるときと、SC-14 の「クラウドから読み直す」だけ（親の adr/0010）。`Takeover` が `GET /records` を最後のページまで読んでから、`RoomTakeover` が1つのトランザクションで突き合わせて入れる（`Merge.kt`: `updatedAt` が新しいほうを残す・クラウドの削除の跡で消す・端末の未送信の削除はクラウドの写しを入れない・ルートは点の多いほう・記録中のまま残っていた走行は終えて入れ、送り直す）。入れたものは送り済みの印を付ける。ユーザー名を変えるときは端末の記録を消してから入れ、そのあとで名前を保存する。読み始めから名前の保存までは `RideSync.withoutPasses` の中で、送信の回が走らない。走行の記録中・一時停止中は、どちらも行わない。ユーザー名は、未送信（SC-14 が数えるもの。断られた版と記録中の走行は数えない）があるあいだも変えられない。トランザクションの中でも確かめ直す。
 - SC-19 の声の入力（`VoiceInput`）は、質問とは別の経路の切り替えと録音の部品を持つ（試し録りと同じ）。SC-19 を開いているあいだ（`attach`）は、インカムのボタンが質問を始めず、声の入力を始める・止める（質問が進んでいるときは質問のまま）。録音は60秒まで。`POST /transcriptions` に送り、質問と同じ間隔で `GET` し、120秒で打ち切る。聞き取れた文は入力欄の終わりに足す。通信できないときは画面のボタンを押せず、インカムのボタンは失敗の合図だけを鳴らす。SC-19 を離れると、録音も文字起こしの待ちも捨てる。前面サービスは使わない（SC-19 を見ながら使う前提）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
 - インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
 - 回答は音声の焦点（audio focus）を取らずに鳴らす（ナビの案内と重ねる）。
 - `MainActivity` は `singleTask`。`ActivityScenario` はこれを追えないので、エミュレーターのテストは Activity を直接起動する。
-- 録音の確認（SC-12）は、質問とは別の経路の切り替え・録音・再生を持つ。画面を離れても、読み上げ中の回答は止めない。
+- 録音の確認（SC-12）は、質問とは別の経路の切り替え・録音・再生を持つ。画面を離れても、読み上げ中の回答は止めない。試し録りはボタンを押した呼び出しの中で録音中になる（`CoroutineStart.UNDISPATCHED`）ので、直後に離れても画面の外で始まらない。「録音をすべて消す」の確認は、質問が始まると閉じる。
+- メディアの音量（SC-02・SC-03 の帯）は `MediaVolumeWatch` がプロセスのあいだ持つ。インカムの通話の経路が残っていて読めない（null）あいだは直前の値を使い、ホームを作り直しても、次の質問でも同じ値になる。✕ で閉じた帯は、違う音量が読めるまで出さない。
 - 録音は `filesDir/recordings/` に `rec-<時刻>.pcm` と `rec-<時刻>.json` の組で直近10件を残す。片方しか無い組と読めない JSON は、次に残すときに消す。
 
 ## テスト
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index 2ad5218..dbed6e7 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 11
-    versionName = "0.10.0"
+    versionCode = 12
+    versionName = "0.11.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
PATCH
```

- [ ] **Step 2: 親の文書を Android に写す**

Run: `cd $ROOT && scripts/sync-docs.sh Android && git -C Android status --short docs-parent`
Expected: この plan と、plan のコミットで直した `08a_android-design.md` が写る

- [ ] **Step 3: コミット**

```bash
cd $AND && git add README.md app/build.gradle.kts docs-parent
git commit -m "docs: describe the device's heading, text asks and SC-11, and raise the version to 0.11.0"
```

---

### Task 14: 全体の確かめ

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
cd $AND && ./gradlew assembleDebug assembleRelease && scripts/check-release-permissions.sh
```

Expected: `655 0`。`BUILD SUCCESSFUL`。`release permissions OK (15)`。`RideForegroundServiceTest` の1件がまれに落ちる（Android #59）。落ちたら単独で回し直し、全体をもう一度回す

- [ ] **Step 2: エミュレーターのテスト**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: 6件が通る

---

### Task 15: 利用者の実機の確認

走行用のビルド（版 0.11.0）を実機（Pixel 8a のメインのユーザー）に入れる。表は変えていないので、マイグレーションは走らない。

```bash
cd $AND && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

1. **SC-11**: 設定に「録音の設定　上限 20秒 · 合図 1.5秒」が「応答後に戻るアプリ」と「回答の音量」のあいだに出る。上限を 10秒・合図を「なし」にすると、行が「上限 10秒 · 合図 なし」になる。走行を始めて質問すると、SC-03 が 10 から数え、合図が鳴らず、10秒で自動で送る。SC-12 の試し録りも合図なしで10秒で止まる。合図を 3秒にすると、インカムで長い合図が聞こえる。「既定値に戻す」で「既定値に戻しました」が出て、20秒・1.5秒に戻る。
2. **文字の質問**（spec §1 の3つ目）: 走行の記録中に、ホームの「⌨ 文字で質問」を押すとシートが開く（記録していないとき・一時停止中は押せない）。空白だけでは「質問する」が押せない。「右手に見える山は何？」と送ると、シートが閉じて SC-03 の「考えています…」から始まり、回答が読み上げられ、ナビへは戻らない。SC-07 の「入力」が「⌨ 文字で質問」で、質問の文が打った文。
3. **文字の質問で通信できない**: 機内モードで送ると、シートに「通信できません」と出て文が残る。SC-06 の時系列に質問できなかった地点が増えていない。機内モードを外して「質問する」を押し直すと送れる。
4. **止まっているときの方位**（spec §1 の1つ目。まとめの判定は plan 6）: 走っているあいだに1回、信号や路肩で1分以上止まってから1回、「右手に見える〜」と質問する。どちらも左右が正しい。AI が DynamoDB でその2件の質問の `headingDegrees` に値があることを確かめる（読むだけ）。止まっているあいだに書いた地点メモにも方位が付く。
5. **音量の帯**（#8・#9。できれば）: メディアの音量を最大の1/3未満にして帯を ✕ で閉じ、音量を1つ上げて戻すと帯がまた出る。設定タブからホームへ戻っても、すぐに帯が出る。

✗ が出たら `superpowers:systematic-debugging`。
