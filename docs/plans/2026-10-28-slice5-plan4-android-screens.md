# スライス5 計画4: Android（画面と記録） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 停車中に GPS と進行方位を確かめて方位の求め方を変えられる画面（SC-22）と、記録一覧（SC-05）のユーザー名を足し、位置の新しさを端末の時計ではなく起動からの経過時間で比べる形にそろえる。あわせて Android #17・#24・#50・#59・#61・#69 を直す。

**Architecture:** 位置（`Fix`）に起動からの経過時間（`elapsedMs`）を持たせ、今の位置の新しさ（`isFresh`）と走行の区間より前の点の判定（`isSince`）はそれで比べる。Room の点は経過時間を持たないので、方位の保つ上限は `GpsClock`（受けた位置から「位置の時刻と経過時間の差」を覚え、今を位置の時刻で数える）と比べる。SC-22 の芯は `HeadingCheck`（`location/`）で、1秒ごとに質問と同じ `findHeading` を通して `HeadingView` を出す。材料は、走行の記録中は `RouteHeading`、それ以外は走行のルートと同じ頼み方・ふるい分けで画面を開いてから集めた点（メモリだけ）。文言は `headingCheckUi`（`ui/HeadingLabels.kt`、純粋）が組み、`HeadingCheckScreen` が描く。Room は版6のまま。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版6のまま。表を変えない）・Robolectric 4.16（SDK 35）・kotlinx.coroutines の `repeatOnLifecycle`。足す依存は無い。

**Spec:** [docs/specs/2026-10-25-slice5-design.md](../specs/2026-10-25-slice5-design.md)（§4.2・§4.3・§4.5・§7・§9・§10・§11・§14）。決定の記録は [adr/0013](../../adr/0013-heading-on-android-held-while-stopped.md)。方位の計算（`findHeading`・`RouteHeading`）とパラメーターの保存（`Settings` の `heading*`）は plan 3 で入っている。

**範囲に入れた issue（Android）:** #17（古い点のふるい分けが、点の時刻と端末の時計を比べている）・#24（一時停止中に端末の時計が戻ると、再開のあとしばらくルートの点が捨てられる）・#50（短い場所の正規表現が、県の名前でない「〇〇県」まで外しうる）・#59（`RideForegroundServiceTest` の自動終了の通知のテストが、まれに落ちる）・#61（SC-19 の声の入力: 文字にしている間の押下に合図が無い・絵文字の境目・入りきらない文が黙って捨てられる）・#69（ごく短い通信の切断は、送信の契機を取りこぼしうる）。

**前提:** Android の `main`（`596d437`。版 0.11.0・JVM のテスト656件）の上に作る。Backend・Agent は変えない。

**計画を書くときに決めたこと（spec からの具体化）:**

- **位置の新しさ（#17・#24。利用者と決めた、2026-10-28）:** `Fix` に `elapsedMs`（`Location.elapsedRealtimeNanos` をミリ秒にしたもの。DB から読んだ点は null）を足す。
  - 今の位置の30秒の新しさは `Fix.isFresh(now, elapsed)` で、経過時間があればそれで比べる（`PositionSource` に `elapsed()` を足す）。
  - 走行の区間より前の点を捨てる判定は `Fix.isSince(sinceElapsed, sinceClock)`。`RideController` は、区間を始めた・再開した・プロセスが走行を引き継いだ（`load()` の再開）ときの経過時間（`takingSince`）を覚えて比べる。経過時間が分からないとき（テストの作り物の点など）は、今までどおり点の時刻と区間の開始を比べる。端末の時計を進めても戻しても、区間のあとの点は捨てられない。
  - 方位の保つ上限は、Room の点が経過時間を持たないので、`GpsClock.now()`（位置の時刻で数えた今）と点の時刻を比べる。`GpsClock` は、アプリが受ける位置（走行のルートと1秒ごとの監視）を `seenBy` で見て覚える。まだ位置を受けていないプロセスでは端末の時計を使う。表は変えない。
  - そのため `RouteHeading.find(here)` は `now` を受けず、`AskDeps.heading`・`RoomNotes` の `heading` も `(here) -> Double?` になる（「今」は `GpsClock` の1か所で決まる）。
  - #24 の「締め切りも同じだけ延びる」は直さない。区間の開始を前の区間の終わりより前にしない決まり（#22）は残し、ずれは最長時間（既定24時間）に比べて小さいため。点が捨てられることだけを直す。
- **SC-22 の材料（利用者と決めた、2026-10-28）:** 「走行とまったく同じ扱い」にする。
  - 今の位置は、質問の録音と同じ1秒ごとの監視（`PositionSource.watch`）の最新で、30秒以内のもの。
  - 走行の記録中は `RouteHeading.find`（質問と同じ）。記録していないとき・一時停止中（走行のルートの監視が止まっている）は、走行のルートと同じ頼み方（`RouteSource`。5秒・10m）で点を集め、同じふるい分け（`acceptRoutePoint`・集め始めた時点より前の点を `isSince` で捨てる）をして、`findHeading` に渡す。集めた点はメモリだけに持つ（DB に書かない・送らない）。
  - 画面を開いたまま走行が記録中になれば集めた点を捨ててルートに切り替え、記録中でなくなれば集め直す。
  - 画面を離れるか、アプリが背面に回ると（`repeatOnLifecycle(STARTED)`）、監視を両方止めて集めた点を捨てる。走行のルートの監視（前面サービス）は止めない。
  - 1秒ごとに計算し直す（`HEADING_CHECK_TICK_MS`）。
- **SC-22 の並びと文言（利用者と決めた、2026-10-28。モックの並びのまま足りない文言を足した案）:**
  - 方位: 「北西へ（315°）」。16方位（Backend が AI に渡す名前）・四捨五入した整数の度数（360 は 0）。右手と左手: 「右手 北東 ／ 左手 南西」（16方位）。
  - 材料: 「位置の精度 6m · 基準の点 18m 手前（12秒前）」。60秒以上は「N分前」。基準の点が30秒より古いとき（`HELD_AFTER_MS`）は「（2分前。止まる直前の向きを保っています）」。精度が分からない位置は「位置の精度 不明」。
  - 出どころ: 記録中「走行のルートから求めています。いま質問すると、この方位を AI に渡します。」、それ以外「この画面を開いてから集めた位置で、走行中と同じに求めています。画面を離れると、集めた位置は捨てます。」
  - 方位なし: 「方位なし」と理由。「位置が取れていません」「位置の精度が悪いため使いません（精度 35m・上限 20m）」「まだ基準の距離（15m）ほど動いていません」「止まってから、向きを保つ上限（10分）を超えました」。今の位置があれば「位置の精度 Nm」も出す。
  - パラメーターの見出しと説明はモックのとおり（基準の距離・精度の上限・向きを保つ上限）。「既定値に戻す」は3項目を既定に戻し、確認なしでトースト「既定値に戻しました」。
  - SC-09 の行は「録音の確認」のすぐ下に「位置と方位の確認」（右の値なし）。
- **SC-05:** 見出し「記録」の右に「👤 ユーザー名」のボタン（`listUser`）。押すと SC-18 を、設定タブの最初の画面の上に開く（ホームと同じ `tabs.open`）。
- **#61:** 文字にしているあいだの押下は `cueFailure` を鳴らす。2000字で切るときは画面の上の1文字を割らない（`cutMemo` の `characterEnd`）。issue の対応案は `BreakIterator` だが、JDK 17 の `java.text.BreakIterator` は ZWJ でつないだ絵文字をまとめない（Java 20 から）ので、JVM のテストと実機で同じに動くよう、つなぐ文字（ZWJ・異体字セレクター・肌の色・キーキャップ・タグ・結合文字）と国旗の対を自分で見る。声で足した文が入りきらなかったら（`Appended.whole` が false）、入力欄の下に「入りきらなかった分は足せませんでした」を、次に文を変えるまで出す。
- **#69:** issue の対応案（送信の係が見送ったことを覚える）ではなく、`Connectivity` が、システムの知らせを受けたところで「戻った回数」（`comebacks`）を数え、`reconnections` はその数の増えを契機にする。状態（true/false）を集める形では、短い false を集め手が見ないと何も起きないが、数は集め手が見落としても増えたまま残るため。
- **#59:** テストの待ちに「通知が出たこと」を足すだけ（コードは変えない）。まれにしか落ちないので、直す前に落ちることは示せない。
- 版を 0.12.0（`versionCode` 13）に上げる。

この計画のコードは、使い捨てのフォルダで、次を確かめてから書いた。

- タスクの順に一つずつコミットし、各コミットで `clean` から JVM のテストが通る（656件 → 687件）。各タスクのテストだけを1つ前のコミットに当てると落ちる（まだ無い名前を使うのでコンパイルで落ちるか、期待が外れて落ちる）。例外は Task 11（#59。まれにしか落ちないテストの待ちを直すだけ）と Task 12（版と文書）。
- 最後に、JVM のテスト687件・`assembleDebug`・`assembleRelease`・`scripts/check-release-permissions.sh` が通り、エミュレーターのテストのコードがコンパイルできる。
- plan の差分を新しい写しへ機械的に当てると、最終形と一致する。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice5-plan4` を切る（Task 0）。親は `slice5-plan4`。push・マージはしない（利用者が明示したときだけ）。push の前に `pre-push-secret-scan`（スキャンと push は別のコマンドにし、結果を読んでから）。
- 作りの決まり: 判断の芯（`isFresh`・`isSince`・`GpsClock`・`HeadingCheck`・`headingCheckUi`・`cutMemo`・`reconnections`）は Android に依存させない。部品は `AppGraph` で手で組む。走行を変えるのは `RideController` だけ（SC-22 は読むだけ）。
- Room は版6のまま（表を変えない）。破壊的な作り直しは使わない。
- ホームは全体がスクロールしない（この plan ではホームを変えない）。
- 方位のパラメーターは端末の設定（DataStore）に置く。SSM には置かない（spec §4.3）。
- SC-22 が集めた点は DB に書かず、送らない（spec §4.5）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない（テストの作り物の名前 `rider01` などは除く）。端末のログ（`adb logcat`）には API の URL が出るので、書き写さない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*クラス名'`。Gradle のビルドキャッシュはフォルダをまたいで共有されるので、テストを確かめるときは `--rerun` を付ける。Kotlin の差分コンパイルは interface の変更を見逃すことがあるので、Task 13 は `./gradlew clean` から回す。
- interface にメソッドを足したら、作り物にも足す（`PositionSource.elapsed` は Task 1 の差分の中で `PositionTrackerTest` の作り物に、`RideDeps.elapsed` は Task 2 の差分の中で `RideControllerTest` の `World` に入っている）。
- Robolectric の決まり（SDK 35・画面の外の行は `performScrollTo` で出す・地図の部品は動かさない）。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。使い終わったら止める。1回目に APK を入れる途中で「device offline」で止まったら、起動し直して回す。
- `RideForegroundServiceTest` の1件がまれに落ちる（Android #59）のは Task 11 で直る。それまでに落ちたら単独で回し直し、全体をもう一度回す。
- この Mac はディスクの空きが少ない。Gradle のキャッシュは使うたびに増える。

## Review Focus

- 端末の時計を手で数分進めた（または一時停止中に時計が後ろへ直った）まま走る → 区間の始めや再開のあとのルートの点が捨てられない。Task 2 の `a_clock_set_ahead_drops_no_point_of_the_segment_and_a_cached_fix_still_goes`・`a_clock_set_back_during_a_pause_drops_no_point_after_the_resume`。
- 端末の時計がずれた端末で、信号待ちで止まってから質問する・SC-22 を見る → 保つ上限は位置の時刻で数え、時計のずれで方位が早く消えたり残り続けたりしない。Task 3 の `after_a_fix_the_present_runs_on_the_fixes_time_by_the_time_since_boot`。
- 位置の許可が無い（または GPS が切れている）まま SC-22 を開く → 落ちずに「位置が取れていません」が出る。Task 4 の `without_the_location_permission_there_is_no_position_and_nothing_breaks`。
- SC-22 を開いたまま走行を一時停止・再開する → 材料が集めた点と走行のルートのあいだで切り替わり、一時停止の前の点を集めた点に混ぜない。Task 4 の `a_ride_that_pauses_starts_a_new_gathering_and_one_that_resumes_ends_it`。
- 2000字近い地点メモに声で足す → 足せなかったことが入力欄の下に出て、絵文字が割れない。Task 9 の `what_was_heard_that_did_not_fit_is_told`・`the_cut_splits_no_emoji_made_of_several_code_points`。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `location/Heading.kt` | `Fix.elapsedMs` | 1 |
| `location/PositionTracker.kt`・`location/FusedPositionSource.kt` | `PositionSource.elapsed`・`isFresh`・`toFix` の経過時間 | 1 |
| `location/Route.kt`・`ride/RidePorts.kt`・`ride/RideController.kt` | `isSince`・`RideDeps.elapsed`・`takingSince` | 2 |
| `location/GpsClock.kt` | 位置の時刻で数える今・`seenBy` | 3 |
| `ride/RouteHeading.kt`・`ask/AskPorts.kt`・`ask/AskController.kt`・`store/RoomNotes.kt` | 方位の「今」を `GpsClock` に寄せる | 3 |
| `location/HeadingCheck.kt` | SC-22 の芯（1秒ごとの方位・点を集める） | 4 |
| `ui/HeadingLabels.kt` | 16方位と SC-22 の文言 | 5 |
| `ui/HeadingCheckScreen.kt`・`ui/SettingsScreens.kt`・`ui/AppUi.kt`・`settings/Settings.kt` | SC-22 の画面・設定の行・`withHeadingDefaults` | 6 |
| `ui/RecordsScreens.kt`・`ui/AppUi.kt` | SC-05 のユーザー名 | 7 |
| `ui/RecordLabels.kt` | #50 | 8 |
| `records/Memos.kt`・`records/Notes.kt`・`ui/MemoScreen.kt`・`voice/VoiceInput.kt` | #61 | 9 |
| `net/Connectivity.kt`・`sync/RideSync.kt` | #69 | 10 |
| `AppGraph.kt` | `elapsed`（2）、`gpsClock`・`positionSource`（3）、`headingCheck()`（6）、`comebacks`（10） | 2・3・6・10 |
| テストの `service/RideForegroundServiceTest.kt` | #59 | 11 |
| `app/build.gradle.kts`・`README.md` | 版と説明 | 12 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、今のテストを回す**

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice5-plan4
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t0.log 2>&1; tail -1 /tmp/trv2-t0.log
```

Expected: `BUILD SUCCESSFUL`（656件）。親はこの plan を書いたブランチ `slice5-plan4` のまま。

---

### Task 1: 今の位置の新しさを経過時間で比べる（#17）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/location/Heading.kt`・`location/PositionTracker.kt`・`location/FusedPositionSource.kt`
- Test: `app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt`

**Interfaces:**
- Produces: `data class Fix(latitude, longitude, timestamp, accuracy, elapsedMs: Long? = null)`。`PositionSource.elapsed(): Long`。`fun Fix.isFresh(now: Long, elapsed: Long): Boolean`（経過時間があればそれで、無ければ端末の時計で30秒以内）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt b/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
index fe8825b..e4599ac 100644
--- a/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
@@ -6,7 +6,7 @@ import org.junit.Assert.assertNull
 import org.junit.Test
 
 class PositionTrackerTest {
-  private class FakeSource(var now: Long = 100_000) : PositionSource {
+  private class FakeSource(var now: Long = 100_000, var elapsed: Long = 50_000) : PositionSource {
     var last: Fix? = null
     var onFix: ((Fix) -> Unit)? = null
     var lateLastKnown: ((Fix) -> Unit)? = null
@@ -14,6 +14,7 @@ class PositionTrackerTest {
     var deferLastKnown = false
 
     override fun now() = now
+    override fun elapsed() = elapsed
     override fun lastKnown(onFix: (Fix) -> Unit) {
       if (deferLastKnown) lateLastKnown = onFix else last?.let(onFix)
     }
@@ -90,9 +91,24 @@ class PositionTrackerTest {
     assertEquals(LATEST_WAIT_MS, testScheduler.currentTime)
     val refused = object : PositionSource {
       override fun now() = 100_000L
+      override fun elapsed() = 50_000L
       override fun lastKnown(onFix: (Fix) -> Unit) = throw SecurityException("no permission")
       override fun watch(onFix: (Fix) -> Unit) = Subscription {}
     }
     assertNull(PositionTracker(refused).latest())
   }
+
+  // Android #17: the device's clock may be minutes off a fix's own (GNSS) time; the time since boot tells its age.
+  @Test
+  fun a_fix_is_as_old_as_the_time_since_boot_says_whatever_the_clock_says() = runTest {
+    val ahead = FakeSource(now = 100_000 + 5 * 60_000, elapsed = 50_000)
+    val tracker = PositionTracker(ahead)
+    tracker.begin()
+    ahead.onFix!!(Fix(35.0, 139.0, 100_000, 5.0, elapsedMs = 45_000))
+    assertEquals(100_000L, tracker.end()?.timestamp)
+    val stale = FakeSource(now = 100_000, elapsed = 50_000).apply {
+      last = Fix(35.0, 139.0, 99_000, 5.0, elapsedMs = 50_000 - MAX_CURRENT_AGE_MS - 1)
+    }
+    assertNull(PositionTracker(stale).latest())
+  }
 }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*PositionTrackerTest'`
Expected: コンパイルで落ちる（`elapsed`・`elapsedMs` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/location/FusedPositionSource.kt b/app/src/main/java/com/touringproject/v2/location/FusedPositionSource.kt
index d6bc2bd..2b90a97 100644
--- a/app/src/main/java/com/touringproject/v2/location/FusedPositionSource.kt
+++ b/app/src/main/java/com/touringproject/v2/location/FusedPositionSource.kt
@@ -4,13 +4,15 @@ import android.annotation.SuppressLint
 import android.content.Context
 import android.location.Location
 import android.os.Looper
+import android.os.SystemClock
 import com.google.android.gms.location.LocationCallback
 import com.google.android.gms.location.LocationRequest
 import com.google.android.gms.location.LocationResult
 import com.google.android.gms.location.LocationServices
 import com.google.android.gms.location.Priority
 
-fun Location.toFix() = Fix(latitude, longitude, time, if (hasAccuracy()) accuracy.toDouble() else null)
+fun Location.toFix() =
+  Fix(latitude, longitude, time, if (hasAccuracy()) accuracy.toDouble() else null, elapsedRealtimeNanos / 1_000_000)
 
 // Without the location permission both calls throw SecurityException; PositionTracker then simply has no fixes.
 @SuppressLint("MissingPermission")
@@ -19,6 +21,8 @@ class FusedPositionSource(context: Context) : PositionSource {
 
   override fun now() = System.currentTimeMillis()
 
+  override fun elapsed() = SystemClock.elapsedRealtime()
+
   override fun lastKnown(onFix: (Fix) -> Unit) {
     client.lastLocation.addOnSuccessListener { it?.let { location -> onFix(location.toFix()) } }
   }
diff --git a/app/src/main/java/com/touringproject/v2/location/Heading.kt b/app/src/main/java/com/touringproject/v2/location/Heading.kt
index c37248f..313494b 100644
--- a/app/src/main/java/com/touringproject/v2/location/Heading.kt
+++ b/app/src/main/java/com/touringproject/v2/location/Heading.kt
@@ -9,8 +9,12 @@ import kotlin.math.sqrt
 
 // The direction of travel, worked out on the device from the ride's route (slice 5 spec §4, adr/0013).
 
-/** accuracy is the radius in metres the device reports (null when unknown). */
-data class Fix(val latitude: Double, val longitude: Double, val timestamp: Long, val accuracy: Double?)
+/**
+ * accuracy is the radius in metres the device reports (null when unknown). timestamp is the fix's own time (often the
+ * GNSS time), which may be off the device's clock; elapsedMs is the time since boot when the fix was made, which is
+ * what tells how old it is (Android #17). A point read back from the database has none.
+ */
+data class Fix(val latitude: Double, val longitude: Double, val timestamp: Long, val accuracy: Double?, val elapsedMs: Long? = null)
 
 // Slice 5 spec §4.3: the rider changes these (SC-22); the defaults hold the heading through a long red light.
 const val DEFAULT_HEADING_REFERENCE_M = 15
diff --git a/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt b/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt
index 7e24283..15ae981 100644
--- a/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt
+++ b/app/src/main/java/com/touringproject/v2/location/PositionTracker.kt
@@ -16,11 +16,20 @@ fun interface Subscription {
 }
 
 interface PositionSource {
+  /** The device's clock. */
   fun now(): Long
+  /** The time since boot (SystemClock.elapsedRealtime). */
+  fun elapsed(): Long
   fun lastKnown(onFix: (Fix) -> Unit)
   fun watch(onFix: (Fix) -> Unit): Subscription
 }
 
+/**
+ * Whether the fix is at most MAX_CURRENT_AGE_MS old: by the time since boot when the fix tells it, since the fix's own
+ * time may be off the device's clock (Android #17); otherwise by the clock.
+ */
+fun Fix.isFresh(now: Long, elapsed: Long): Boolean = (elapsedMs?.let { elapsed - it } ?: (now - timestamp)) <= MAX_CURRENT_AGE_MS
+
 class PositionTracker(private val source: PositionSource) : Positions {
   private val fixes = mutableListOf<Fix>()
   private var subscription: Subscription? = null
@@ -45,7 +54,7 @@ class PositionTracker(private val source: PositionSource) : Positions {
     subscription = null
     val latest = fixes.maxByOrNull { it.timestamp }
     fixes.clear()
-    return latest?.takeIf { source.now() - it.timestamp <= MAX_CURRENT_AGE_MS }
+    return latest?.takeIf { it.isFresh(source.now(), source.elapsed()) }
   }
 
   /**
@@ -58,6 +67,6 @@ class PositionTracker(private val source: PositionSource) : Positions {
         runCatching { source.lastKnown { if (cont.isActive) cont.resume(it) } }.onFailure { if (cont.isActive) cont.resume(null) }
       }
     }
-    return fix?.takeIf { source.now() - it.timestamp <= MAX_CURRENT_AGE_MS }
+    return fix?.takeIf { it.isFresh(source.now(), source.elapsed()) }
   }
 }
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*PositionTrackerTest'`
Expected: PASS（全体で657件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/location/FusedPositionSource.kt app/src/main/java/com/touringproject/v2/location/Heading.kt app/src/main/java/com/touringproject/v2/location/PositionTracker.kt app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
git commit -m "fix: tell a position's age by the time since boot, not the clock (#17)"
```

---

### Task 2: 走行の区間より前の点を経過時間で見分ける（#17・#24）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/location/Route.kt`・`ride/RidePorts.kt`・`ride/RideController.kt`・`AppGraph.kt`
- Test: `app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt`

**Interfaces:**
- Consumes: `Fix.elapsedMs`（Task 1）
- Produces: `fun Fix.isSince(sinceElapsed: Long?, sinceClock: Long): Boolean`（`location/Route.kt`。両方の経過時間があればそれで、無ければ点の時刻と `sinceClock` で比べる）。`RideDeps(now, elapsed: () -> Long, bootCount, ...)`（`elapsed` は2つ目）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
index a04888a..0dcc479 100644
--- a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
@@ -16,7 +16,7 @@ import java.io.IOException
 private const val MAX = 24 * HOUR_MS
 
 /** An in-memory store that can be told to fail, and a world that records what the controller asked of it. */
-private class World(var now: Long = 1_000, var boot: Int? = 7) {
+private class World(var now: Long = 1_000, var boot: Int? = 7, var elapsed: Long = 500) {
   val rides = mutableMapOf<String, Ride>()
   val points = mutableMapOf<String, MutableList<RoutePoint>>()
   var failWrites = false
@@ -79,6 +79,7 @@ private class World(var now: Long = 1_000, var boot: Int? = 7) {
   val controller = RideController(
     RideDeps(
       now = { now },
+      elapsed = { elapsed },
       bootCount = { boot },
       newId = { "r${++ids}" },
       maxRecordingMs = { max },
@@ -165,6 +166,53 @@ class RideControllerTest {
     assertNull(w.points["r1"])
   }
 
+  // Android #17: with the clock set 5 minutes ahead, the segment starts "later" than the fixes' own (GNSS) time; the
+  // time since boot tells which fixes came after the start, and a cached one from before is still dropped.
+  @Test
+  fun a_clock_set_ahead_drops_no_point_of_the_segment_and_a_cached_fix_still_goes() = runTest {
+    val w = World(now = 1_000 + 5 * 60_000, elapsed = 500)
+    w.controller.load()
+    w.controller.start("箱根")
+    w.controller.onFix(Fix(35.000, 139.0, 900, 5.0, elapsedMs = 400))
+    w.controller.onFix(Fix(35.001, 139.0, 2_000, 5.0, elapsedMs = 1_500))
+    w.controller.onFix(Fix(35.002, 139.0, 7_000, 5.0, elapsedMs = 6_500))
+    assertEquals(listOf(2_000L, 7_000L), w.points.getValue("r1").map { it.t })
+  }
+
+  // Android #24: the clock was set back 30 minutes while paused, so the new segment starts "in the future" (Android #22);
+  // the points after the resume are kept all the same.
+  @Test
+  fun a_clock_set_back_during_a_pause_drops_no_point_after_the_resume() = runTest {
+    val w = World(now = 2_000_000, elapsed = 500)
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 2_600_000
+    w.elapsed = 600_500
+    w.controller.pause()
+    w.now = 1_000_000
+    w.elapsed = 700_500
+    w.controller.resume()
+    assertEquals(2_600_000L, w.stored().segments.last().startedAt)
+    w.controller.onFix(Fix(35.0, 139.0, 1_005_000, 5.0, elapsedMs = 705_500))
+    assertEquals(listOf(1_005_000L), w.points.getValue("r1").map { it.t })
+  }
+
+  // A process that takes over a recording ride (load) takes its points from then on, by the time since boot.
+  @Test
+  fun a_ride_taken_over_by_a_new_process_takes_points_made_after_it() = runTest {
+    val before = World()
+    before.controller.load()
+    before.controller.start("箱根")
+    val after = World(now = 30_000, elapsed = 29_500).apply {
+      rides += before.rides
+      points += before.points
+    }
+    after.controller.load()
+    after.controller.onFix(Fix(35.000, 139.0, 29_000, 5.0, elapsedMs = 29_000))
+    after.controller.onFix(Fix(35.001, 139.0, 31_000, 5.0, elapsedMs = 31_000))
+    assertEquals(listOf(31_000L), after.points.getValue("r1").map { it.t })
+  }
+
   @Test
   fun the_first_call_at_or_past_the_deadline_ends_the_ride_at_the_deadline_and_says_so() = runTest {
     val w = World()
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RideControllerTest'`
Expected: コンパイルで落ちる（`RideDeps` に `elapsed` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index fedfc37..3c016b9 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -3,6 +3,7 @@ package com.touringproject.v2
 import android.Manifest
 import android.content.Context
 import android.content.pm.PackageManager
+import android.os.SystemClock
 import android.provider.Settings as SystemSettings
 import android.util.Log
 import com.touringproject.v2.api.ApiClient
@@ -165,6 +166,7 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   val rides = RideController(
     RideDeps(
       now = System::currentTimeMillis,
+      elapsed = SystemClock::elapsedRealtime,
       bootCount = { runCatching { SystemSettings.Global.getInt(context.contentResolver, SystemSettings.Global.BOOT_COUNT) }.getOrNull() },
       newId = { UUID.randomUUID().toString() },
       // Read at each start and resume; before the settings are loaded only the default exists.
diff --git a/app/src/main/java/com/touringproject/v2/location/Route.kt b/app/src/main/java/com/touringproject/v2/location/Route.kt
index 05733bc..8e1471e 100644
--- a/app/src/main/java/com/touringproject/v2/location/Route.kt
+++ b/app/src/main/java/com/touringproject/v2/location/Route.kt
@@ -17,6 +17,14 @@ const val ROUTE_MAX_ACCURACY_M = 50.0
 /** US-C-02.005: a point less accurate than 50 m is dropped. A point without an accuracy is kept. */
 fun acceptRoutePoint(fix: Fix): Boolean = fix.accuracy == null || fix.accuracy <= ROUTE_MAX_ACCURACY_M
 
+/**
+ * Whether the fix was made after a stretch of route began: Fused may hand over a cached fix from before when a watch
+ * starts. Compared on the time since boot (sinceElapsed) when both sides tell it, so a clock set forward or back
+ * drops nothing (Android #17, #24); otherwise the fix's time against the clock's (sinceClock).
+ */
+fun Fix.isSince(sinceElapsed: Long?, sinceClock: Long): Boolean =
+  if (elapsedMs != null && sinceElapsed != null) elapsedMs >= sinceElapsed else timestamp >= sinceClock
+
 fun interface RouteSource {
   fun watch(onFix: (Fix) -> Unit): Subscription
 }
diff --git a/app/src/main/java/com/touringproject/v2/ride/RideController.kt b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
index 512219f..209e9c3 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RideController.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
@@ -2,6 +2,7 @@ package com.touringproject.v2.ride
 
 import com.touringproject.v2.location.Fix
 import com.touringproject.v2.location.acceptRoutePoint
+import com.touringproject.v2.location.isSince
 import com.touringproject.v2.records.memoFits
 import kotlinx.coroutines.CancellationException
 import kotlinx.coroutines.CompletableDeferred
@@ -33,6 +34,9 @@ class RideController(private val deps: RideDeps) {
   val storeFailed: StateFlow<Boolean> = storeFailing.asStateFlow()
   // The last stored point of the active ride, for the distance of the next one.
   private var lastPoint: RoutePoint? = null
+  // The time since boot when this process began to take the open segment's points (its start or resume, or load()).
+  // A fix made before it is not on the segment's route, whatever the clock says (Android #17, #24).
+  private var takingSince: Long? = null
   // A ride whose save failed; it is written again first by every later call.
   private var unsaved: Ride? = null
   // False until the ride left over from before this process has been read; until then no new ride may start.
@@ -70,6 +74,7 @@ class RideController(private val deps: RideDeps) {
       Reconcile.Resume -> {
         activeRide.value = ride
         lastPoint = read("last_point") { d.store.lastPoint(ride!!.id) }
+        takingSince = d.elapsed()
         d.alarm.set(ride!!.id, ride.deadline!!)
         d.recording(true)
       }
@@ -144,6 +149,7 @@ class RideController(private val deps: RideDeps) {
     save(ride)
     activeRide.value = ride
     lastPoint = null
+    takingSince = d.elapsed()
     d.alarm.set(ride.id, ride.deadline!!)
     d.recording(true)
     d.log("ride_start", mapOf("ride" to ride.id))
@@ -175,6 +181,7 @@ class RideController(private val deps: RideDeps) {
     save(resumed)
     activeRide.value = resumed
     lastPoint = null
+    takingSince = d.elapsed()
     d.alarm.set(resumed.id, resumed.deadline!!)
     d.recording(true)
     true
@@ -288,7 +295,7 @@ class RideController(private val deps: RideDeps) {
     val now = d.now()
     if (autoEndIfDue(ride, now)) return@locked
     // Fused may hand over a cached fix when the watch starts again: one from before this segment is not on its route.
-    if (!acceptRoutePoint(fix) || fix.timestamp < ride.segments.last().startedAt) {
+    if (!acceptRoutePoint(fix) || !fix.isSince(takingSince, ride.segments.last().startedAt)) {
       write("alive") { d.store.markAlive(ride.id, now) }
       activeRide.value = ride.copy(lastAliveAt = now)
       return@locked
diff --git a/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt b/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt
index be800a4..157ddef 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt
@@ -28,6 +28,8 @@ interface DeadlineAlarm {
 
 class RideDeps(
   val now: () -> Long,
+  /** The time since boot (SystemClock.elapsedRealtime): what a route point's age is told by (Android #17). */
+  val elapsed: () -> Long,
   /** The device's boot count, or null when the system does not tell. */
   val bootCount: () -> Int?,
   val newId: () -> String,
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RideControllerTest'`
Expected: PASS（全体で660件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/location/Route.kt app/src/main/java/com/touringproject/v2/ride/RideController.kt app/src/main/java/com/touringproject/v2/ride/RidePorts.kt app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
git commit -m "fix: keep a segment's route points by the time since boot, so a clock set forward or back drops none (#17, #24)"
```

---

### Task 3: 方位の保つ上限を位置の時刻で数える（#17）

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/location/GpsClock.kt`
- Modify: `ride/RouteHeading.kt`・`ask/AskPorts.kt`・`ask/AskController.kt`・`store/RoomNotes.kt`・`AppGraph.kt`
- Test: `location/GpsClockTest.kt`（新規）・`ride/RouteHeadingTest.kt`・`ask/AskControllerTest.kt`・`store/RoomNotesTest.kt`

**Interfaces:**
- Consumes: `Fix.elapsedMs`・`PositionSource.elapsed`（Task 1）
- Produces: `class GpsClock(elapsed: () -> Long, clock: () -> Long) { fun seen(fix: Fix); fun now(): Long }`。`fun RouteSource.seenBy(clock: GpsClock): RouteSource`・`fun PositionSource.seenBy(clock: GpsClock): PositionSource`。`RouteHeading(ride, points, params, now: () -> Long, log)` と `suspend fun find(here: Fix?): HeadingResult`。`AskDeps.heading: suspend (here: Fix?) -> Double?`。`RoomNotes(..., heading: suspend (here: Fix?) -> Double? = { null }, log)`。`AppGraph.gpsClock`・`AppGraph.positionSource`（1秒ごとの位置。Task 6 の SC-22 も使う）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index 3b2c4cf..01f8c97 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -144,7 +144,7 @@ private class Harness(
       override fun end() = HERE
       override suspend fun latest(): Fix? { log += "loc:latest"; return latest }
     },
-    heading = { here, at -> headingAsked += here to at; heading },
+    heading = { here -> headingAsked += here to now(); heading },
     service = object : KeepAlive {
       override fun start() { log += "svc:start"; serviceError?.let { throw it } }
       override fun stop() { log += "svc:stop" }
diff --git a/app/src/test/java/com/touringproject/v2/location/GpsClockTest.kt b/app/src/test/java/com/touringproject/v2/location/GpsClockTest.kt
new file mode 100644
index 0000000..3c59369
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/location/GpsClockTest.kt
@@ -0,0 +1,44 @@
+package com.touringproject.v2.location
+
+import org.junit.Assert.assertEquals
+import org.junit.Test
+
+// Android #17: a route point's age is told on the fixes' own time, which the device's clock may be minutes off.
+class GpsClockTest {
+  private var elapsed = 10_000L
+  private var clock = 1_000_000L + 5 * 60_000
+  private val gps = GpsClock({ elapsed }, { clock })
+
+  @Test
+  fun the_clock_stands_in_until_a_fix_has_been_seen() {
+    assertEquals(clock, gps.now())
+    gps.seen(Fix(35.0, 139.0, 990_000, 5.0))
+    assertEquals(clock, gps.now())
+  }
+
+  @Test
+  fun after_a_fix_the_present_runs_on_the_fixes_time_by_the_time_since_boot() {
+    gps.seen(Fix(35.0, 139.0, 1_000_000, 5.0, elapsedMs = 9_000))
+    assertEquals(1_001_000L, gps.now())
+    elapsed += 120_000
+    assertEquals(1_121_000L, gps.now())
+  }
+
+  @Test
+  fun the_sources_show_every_fix_to_the_clock() {
+    val fix = Fix(35.0, 139.0, 2_000_000, 5.0, elapsedMs = 10_000)
+    val route = RouteSource { onFix -> onFix(fix); Subscription {} }.seenBy(gps)
+    val got = mutableListOf<Fix>()
+    route.watch { got += it }
+    assertEquals(listOf(fix), got)
+    assertEquals(2_000_000L, gps.now())
+    val positions = object : PositionSource {
+      override fun now() = clock
+      override fun elapsed() = elapsed
+      override fun lastKnown(onFix: (Fix) -> Unit) = onFix(fix.copy(timestamp = 3_000_000))
+      override fun watch(onFix: (Fix) -> Unit) = Subscription {}
+    }.seenBy(gps)
+    positions.lastKnown { got += it }
+    assertEquals(3_000_000L, gps.now())
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/ride/RouteHeadingTest.kt b/app/src/test/java/com/touringproject/v2/ride/RouteHeadingTest.kt
index c7c2f6e..895ad3e 100644
--- a/app/src/test/java/com/touringproject/v2/ride/RouteHeadingTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ride/RouteHeadingTest.kt
@@ -29,14 +29,22 @@ class RouteHeadingTest {
   private val store = RoomRideStore(db.rides())
   private var ride: Ride? = null
   private var params = HeadingParams()
+  private var now = 0L
   private val failures = mutableListOf<String>()
   private val heading = RouteHeading(
     ride = { ride },
     points = { rideId, segment, count -> db.rides().segmentTail(rideId, segment, count).map { it.toPoint() } },
     params = { params },
+    now = { now },
     log = { message, _ -> failures += message },
   )
 
+  /** The heading at here, the present being at (on the points' own time). */
+  private suspend fun RouteHeading.find(here: Fix, at: Long): HeadingResult {
+    now = at
+    return find(here)
+  }
+
   @After
   fun close() = db.close()
 
@@ -84,7 +92,7 @@ class RouteHeadingTest {
   @Test
   fun without_a_ride_or_its_points_there_is_no_route() = runBlocking {
     assertEquals(HeadingResult.None(NoHeading.NOT_MOVED), heading.find(here(0, 0), 0))
-    val broken = RouteHeading({ newRide("r1", "箱根", 0, 7, HOUR_MS) }, { _, _, _ -> error("closed") }, { params }) { message, _ -> failures += message }
+    val broken = RouteHeading({ newRide("r1", "箱根", 0, 7, HOUR_MS) }, { _, _, _ -> error("closed") }, { params }, { now }) { message, _ -> failures += message }
     assertNull(broken.find(here(0, 0), 0).degrees)
     assertEquals(listOf("heading_points_failed rideId=r1"), failures)
   }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
index 8c12902..b8dae5e 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
@@ -35,7 +35,7 @@ class RoomNotesTest {
   private val headingAsked = mutableListOf<Pair<Fix?, Long>>()
   private val notes = RoomNotes(
     db.notes(), db.rides(), { now }, { "n1" }, { changes += 1 },
-    heading = { here, at -> headingAsked += here to at; 271.5 },
+    heading = { here -> headingAsked += here to now; 271.5 },
   ) { message, _ -> errors += message }
   private val records = RoomRecords(db.rides(), db.asks(), db.notes())
   private val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*GpsClockTest' --tests '*RouteHeadingTest' --tests '*AskControllerTest' --tests '*RoomNotesTest'`
Expected: コンパイルで落ちる（`GpsClock` が無い・`heading` の形が違う）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 3c016b9..abd1e13 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -27,10 +27,13 @@ import com.touringproject.v2.handsfree.PressGate
 import com.touringproject.v2.handsfree.PressRouter
 import com.touringproject.v2.location.FusedPositionSource
 import com.touringproject.v2.location.FusedRouteSource
+import com.touringproject.v2.location.GpsClock
 import com.touringproject.v2.location.HeadingParams
+import com.touringproject.v2.location.PositionSource
 import com.touringproject.v2.location.PositionTracker
 import com.touringproject.v2.location.RouteSource
 import com.touringproject.v2.location.degrees
+import com.touringproject.v2.location.seenBy
 import com.touringproject.v2.nav.AppLauncher
 import com.touringproject.v2.net.Connectivity
 import com.touringproject.v2.recordings.RecordingCheck
@@ -110,7 +113,11 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   private val micAllowed = { context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED }
 
   val serviceCoordinator = ServiceCoordinator(ContextServiceLauncher(context)) { message, e -> Log.w("trv2.ride", message, e) }
-  val routeSource: RouteSource = FusedRouteSource(context)
+  /** The present on the fixes' own time, learnt from every fix the app gets (Android #17). */
+  val gpsClock = GpsClock(SystemClock::elapsedRealtime, System::currentTimeMillis)
+  val routeSource: RouteSource = FusedRouteSource(context).seenBy(gpsClock)
+  /** The 1 s positions of an ask's recording and of SC-22. */
+  val positionSource: PositionSource = FusedPositionSource(context).seenBy(gpsClock)
   private val database = RideDatabase.open(context)
   val rideStore = RoomRideStore(database.rides())
   // sync is made below; it is read only when an unreached ask has been written.
@@ -186,13 +193,14 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     ride = { rides.active.value },
     points = { rideId, segment, count -> database.rides().segmentTail(rideId, segment, count).map { it.toPoint() } },
     params = { settings.settings.value?.headingParams ?: HeadingParams() },
+    now = gpsClock::now,
     log = { message, e -> Log.w("trv2.ride", message, e) },
   )
 
   /** SC-19 writes point memos through here; each change is something new to send (slice 3 spec §5.1). */
   val notes = RoomNotes(
     database.notes(), database.rides(), System::currentTimeMillis, { UUID.randomUUID().toString() }, sync::request,
-    heading = { here, now -> routeHeading.find(here, now).degrees },
+    heading = { here -> routeHeading.find(here).degrees },
   ) { message, e -> Log.w("trv2.note", message, e) }
 
   /** How many asks the device keeps for the ride recording or paused (SC-02, SC-04; Android #35). */
@@ -231,8 +239,8 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       online = { connectivity.online.value },
       newId = { UUID.randomUUID().toString() },
       ride = { rideNow(rides.active.value) },
-      location = PositionTracker(FusedPositionSource(context)),
-      heading = { here, now -> routeHeading.find(here, now).degrees },
+      location = PositionTracker(positionSource),
+      heading = { here -> routeHeading.find(here).degrees },
       service = serviceCoordinator.keepAlive,
       nav = launcher,
       cues = cues,
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index bfe30aa..cf51353 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -215,7 +215,7 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       serviceRunning = true
       val here = d.location.latest()
       if (!isCurrent(run)) return
-      val sent = sendText(text, here, d.heading(here, d.now()), rideId, api, run, tell) ?: return
+      val sent = sendText(text, here, d.heading(here), rideId, api, run, tell) ?: return
       val result = waitForAnswer(sent, null, api, run) ?: return
       speak(result, settings, run)
     } finally {
@@ -362,7 +362,7 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     val endedAt = d.now()
     val meta = RecordingMeta(stopped.name, startedAt, pcmDurationMs(stopped.pcm.size), phoneMic, device, null)
     val here = d.location.end()
-    val heading = d.heading(here, endedAt)
+    val heading = d.heading(here)
     return Recording(Base64.getEncoder().encodeToString(stopped.pcm), stopped.name, here, heading, endedAt, meta, stopped.pcm)
   }
 
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
index 430b49d..5dd3d14 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
@@ -133,8 +133,11 @@ class AskDeps(
   /** Whether a ride is recording now: an ask starts only then (slice 2 spec §4.7). */
   val ride: () -> RideNow,
   val location: Positions,
-  /** The heading at here, as of now, from the recording ride's route (slice 5 spec §4); null when there is none. */
-  val heading: suspend (here: Fix?, now: Long) -> Double?,
+  /**
+   * The heading at here, as of the moment it is asked, from the recording ride's route (slice 5 spec §4); null when
+   * there is none.
+   */
+  val heading: suspend (here: Fix?) -> Double?,
   val service: KeepAlive,
   val nav: NavReturn,
   val cues: Cues,
diff --git a/app/src/main/java/com/touringproject/v2/location/GpsClock.kt b/app/src/main/java/com/touringproject/v2/location/GpsClock.kt
new file mode 100644
index 0000000..0fba1c4
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/location/GpsClock.kt
@@ -0,0 +1,34 @@
+package com.touringproject.v2.location
+
+/**
+ * The present on the fixes' own (often GNSS) time, which may be off the device's clock. Route points read back from the
+ * database keep only that time, so how old one is (the heading's hold, slice 5 spec §4.2) is told against this clock,
+ * not the device's (Android #17). Each fix seen tells how its time stands to the time since boot; until one has been
+ * seen in this process, the device's clock stands in.
+ */
+class GpsClock(private val elapsed: () -> Long, private val clock: () -> Long) {
+  @Volatile private var offset: Long? = null
+
+  fun seen(fix: Fix) {
+    fix.elapsedMs?.let { offset = fix.timestamp - it }
+  }
+
+  fun now(): Long = offset?.let { elapsed() + it } ?: clock()
+}
+
+/** The same route, each fix shown to clock on the way. */
+fun RouteSource.seenBy(clock: GpsClock): RouteSource {
+  val source = this
+  return RouteSource { onFix -> source.watch { clock.seen(it); onFix(it) } }
+}
+
+/** The same positions, each fix shown to clock on the way. */
+fun PositionSource.seenBy(clock: GpsClock): PositionSource {
+  val source = this
+  return object : PositionSource {
+    override fun now() = source.now()
+    override fun elapsed() = source.elapsed()
+    override fun lastKnown(onFix: (Fix) -> Unit) = source.lastKnown { clock.seen(it); onFix(it) }
+    override fun watch(onFix: (Fix) -> Unit) = source.watch { clock.seen(it); onFix(it) }
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt b/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt
index 0dfe14a..2ead9ce 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt
@@ -15,15 +15,18 @@ const val HEADING_POINTS = 120
 /**
  * The heading of the ride recording or paused (slice 5 spec §4.1): from the points of its last segment only, since a
  * ride may resume far from where it paused (a ferry). Asks, unreached asks and point memos all go through here, so
- * each takes its heading the same way. Without a ride, or when its points cannot be read, there is no route.
+ * each takes its heading the same way, as does SC-22 while the ride records. Without a ride, or when its points cannot
+ * be read, there is no route. now is the present on the points' own time (GpsClock), which the hold is measured
+ * against (Android #17).
  */
 class RouteHeading(
   private val ride: () -> Ride?,
   private val points: suspend (rideId: String, segment: Int, count: Int) -> List<RoutePoint>,
   private val params: () -> HeadingParams,
+  private val now: () -> Long,
   private val log: (String, Throwable) -> Unit,
 ) {
-  suspend fun find(here: Fix?, now: Long): HeadingResult {
+  suspend fun find(here: Fix?): HeadingResult {
     val active = ride()
     val route = if (active == null) {
       emptyList()
@@ -37,6 +40,6 @@ class RouteHeading(
         emptyList()
       }
     }
-    return findHeading(route, here, now, params())
+    return findHeading(route, here, now(), params())
   }
 }
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt b/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt
index 2aab933..8de0db5 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt
@@ -19,7 +19,7 @@ class RoomNotes(
   private val now: () -> Long,
   private val newId: () -> String,
   private val changed: () -> Unit,
-  private val heading: suspend (here: Fix?, now: Long) -> Double? = { _, _ -> null },
+  private val heading: suspend (here: Fix?) -> Double? = { null },
   private val log: (String, Throwable) -> Unit,
 ) : NoteEdits {
   override suspend fun draft(rideId: String): NoteDraft {
@@ -33,7 +33,7 @@ class RoomNotes(
       log("note_points_failed rideId=$rideId", e)
       null
     }
-    return noteDraft(newId(), rideId, at, newest, heading(newest?.toFix(), at))
+    return noteDraft(newId(), rideId, at, newest, heading(newest?.toFix()))
   }
 
   override suspend fun create(draft: NoteDraft, text: String): Boolean =
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*GpsClockTest' --tests '*RouteHeadingTest' --tests '*AskControllerTest' --tests '*RoomNotesTest'`
Expected: PASS（全体で663件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/location/GpsClock.kt app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt app/src/main/java/com/touringproject/v2/store/RoomNotes.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/location/GpsClockTest.kt app/src/test/java/com/touringproject/v2/ride/RouteHeadingTest.kt app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
git commit -m "fix: measure the heading's hold on the fixes' own time, not the device's clock (#17)"
```

---

### Task 4: SC-22 の方位を1秒ごとに求める

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/location/HeadingCheck.kt`
- Test: `app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt`（新規）

**Interfaces:**
- Consumes: `isFresh`（Task 1）・`isSince`・`acceptRoutePoint`（Task 2）・`findHeading`・`HeadingResult`・`HeadingParams`（plan 3）
- Produces: `const val HEADING_CHECK_TICK_MS = 1_000L`。`data class HeadingView(result: HeadingResult, here: Fix?, fromRide: Boolean, referenceAgeMs: Long?)`。`class HeadingCheck(positions: PositionSource, route: RouteSource, recording: () -> Boolean, rideHeading: suspend (Fix?) -> HeadingResult, params: () -> HeadingParams, gpsNow: () -> Long) { suspend fun run(show: (HeadingView) -> Unit) }`（取り消されるまで回り、取り消されたら監視を外す）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt b/app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt
new file mode 100644
index 0000000..45898fa
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt
@@ -0,0 +1,185 @@
+package com.touringproject.v2.location
+
+import kotlinx.coroutines.launch
+import kotlinx.coroutines.test.TestScope
+import kotlinx.coroutines.test.advanceTimeBy
+import kotlinx.coroutines.test.runCurrent
+import kotlinx.coroutines.test.runTest
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertFalse
+import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
+import org.junit.Test
+
+// Slice 5 spec §4.5: SC-22 works the heading out as an ask does, from the ride's route while it records and from points
+// gathered as a route's are otherwise; leaving the screen stops its watches.
+class HeadingCheckTest {
+  /** The fixes' own time runs with the time since boot, offset by a day; the device's clock is 5 minutes ahead. */
+  private class World {
+    var elapsed = 100_000L
+    val gpsNow get() = elapsed + 86_400_000
+    var recording = false
+    var params = HeadingParams()
+    var positionWatches = 0
+    var positionRemoved = 0
+    var routeWatches = 0
+    var routeRemoved = 0
+    var onPosition: ((Fix) -> Unit)? = null
+    var onRoute: ((Fix) -> Unit)? = null
+    val asked = mutableListOf<Fix?>()
+    val views = mutableListOf<HeadingView>()
+
+    val positions = object : PositionSource {
+      override fun now() = gpsNow + 5 * 60_000
+      override fun elapsed() = elapsed
+      override fun lastKnown(onFix: (Fix) -> Unit) = Unit
+      override fun watch(onFix: (Fix) -> Unit): Subscription {
+        positionWatches += 1
+        onPosition = onFix
+        return Subscription { positionRemoved += 1 }
+      }
+    }
+    val route = RouteSource { onFix ->
+      routeWatches += 1
+      onRoute = onFix
+      Subscription { routeRemoved += 1 }
+    }
+    val check = HeadingCheck(
+      positions, route, { recording },
+      rideHeading = { here -> asked += here; HeadingResult.Found(90.0, Fix(35.0, 139.0, gpsNow - 3_000, 5.0), 20.0) },
+      params = { params },
+      gpsNow = { gpsNow },
+    )
+
+    /** A fix made now, north metres north of one place. */
+    fun fix(north: Double, accuracy: Double? = 5.0, ageMs: Long = 0) =
+      Fix(35.0 + north / 111_195.0, 139.0, gpsNow - ageMs, accuracy, elapsedMs = elapsed - ageMs)
+
+    fun tick(scope: TestScope) {
+      elapsed += HEADING_CHECK_TICK_MS
+      scope.advanceTimeBy(HEADING_CHECK_TICK_MS)
+      scope.runCurrent()
+    }
+  }
+
+  private fun TestScope.open(w: World) = backgroundScope.launch { w.check.run { w.views += it } }.also { runCurrent() }
+
+  @Test
+  fun without_a_recording_ride_points_are_gathered_as_a_route_and_give_the_heading() = runTest {
+    val w = World()
+    open(w)
+    assertEquals(HeadingResult.None(NoHeading.NO_POSITION), w.views.last().result)
+    (0..3).forEach { step ->
+      w.onRoute!!(w.fix(step * 10.0))
+      w.onPosition!!(w.fix(step * 10.0, accuracy = 6.0))
+      repeat(5) { w.tick(this) }
+    }
+    val view = w.views.last()
+    val found = view.result as HeadingResult.Found
+    assertEquals(0.0, found.degrees, 0.5)
+    assertEquals(20.0, found.meters, 0.5)
+    assertFalse(view.fromRide)
+    assertEquals(6.0, view.here?.accuracy)
+    // The reference is the point 20 m back, gathered 15 s ago.
+    assertEquals(15_000L, view.referenceAgeMs)
+  }
+
+  @Test
+  fun a_cached_fix_from_before_opening_and_an_inaccurate_one_are_not_gathered() = runTest {
+    val w = World()
+    open(w)
+    w.onRoute!!(w.fix(-30.0, ageMs = 60_000))
+    w.onRoute!!(w.fix(-20.0, accuracy = 80.0))
+    w.onPosition!!(w.fix(0.0))
+    w.tick(this)
+    assertEquals(HeadingResult.None(NoHeading.NOT_MOVED), w.views.last().result)
+  }
+
+  @Test
+  fun a_stale_position_is_no_position() = runTest {
+    val w = World()
+    open(w)
+    w.onPosition!!(w.fix(0.0))
+    repeat(31) { w.tick(this) }
+    assertNull(w.views.last().here)
+    assertEquals(HeadingResult.None(NoHeading.NO_POSITION), w.views.last().result)
+  }
+
+  @Test
+  fun while_a_ride_records_its_route_gives_the_heading_and_nothing_is_gathered() = runTest {
+    val w = World().apply { recording = true }
+    open(w)
+    w.onPosition!!(w.fix(0.0))
+    w.tick(this)
+    assertEquals(0, w.routeWatches)
+    val view = w.views.last()
+    assertTrue(view.fromRide)
+    assertEquals(90.0, (view.result as HeadingResult.Found).degrees, 0.0)
+    assertEquals(3_000L, view.referenceAgeMs)
+    // The ride's route is asked with the current position, as an ask asks it.
+    assertEquals(35.0, w.asked.last()!!.latitude, 0.0)
+  }
+
+  @Test
+  fun a_ride_that_pauses_starts_a_new_gathering_and_one_that_resumes_ends_it() = runTest {
+    val w = World().apply { recording = true }
+    open(w)
+    w.recording = false
+    w.tick(this)
+    assertEquals(1, w.routeWatches)
+    assertFalse(w.views.last().fromRide)
+    w.recording = true
+    w.tick(this)
+    assertEquals(1, w.routeRemoved)
+    assertTrue(w.views.last().fromRide)
+  }
+
+  @Test
+  fun the_parameters_of_the_moment_are_used() = runTest {
+    val w = World()
+    open(w)
+    w.onRoute!!(w.fix(0.0))
+    w.tick(this)
+    w.onPosition!!(w.fix(12.0))
+    w.tick(this)
+    assertEquals(HeadingResult.None(NoHeading.NOT_MOVED), w.views.last().result)
+    w.params = HeadingParams(referenceMeters = 10)
+    w.tick(this)
+    assertTrue(w.views.last().result is HeadingResult.Found)
+  }
+
+  @Test
+  fun leaving_removes_both_watches() = runTest {
+    val w = World()
+    val job = open(w)
+    assertEquals(1, w.positionWatches)
+    assertEquals(1, w.routeWatches)
+    job.cancel()
+    runCurrent()
+    assertEquals(1, w.positionRemoved)
+    assertEquals(1, w.routeRemoved)
+  }
+
+  // Without the location permission Fused throws: the screen still opens and says there is no position.
+  @Test
+  fun without_the_location_permission_there_is_no_position_and_nothing_breaks() = runTest {
+    val refused = object : PositionSource {
+      override fun now() = 0L
+      override fun elapsed() = 0L
+      override fun lastKnown(onFix: (Fix) -> Unit) = throw SecurityException("no permission")
+      override fun watch(onFix: (Fix) -> Unit): Subscription = throw SecurityException("no permission")
+    }
+    val check = HeadingCheck(
+      refused, { throw SecurityException("no permission") }, { false },
+      rideHeading = { HeadingResult.None(NoHeading.NO_POSITION) }, params = { HeadingParams() }, gpsNow = { 0L },
+    )
+    val views = mutableListOf<HeadingView>()
+    val job = backgroundScope.launch { check.run { views += it } }
+    runCurrent()
+    advanceTimeBy(HEADING_CHECK_TICK_MS)
+    runCurrent()
+    assertEquals(HeadingView(HeadingResult.None(NoHeading.NO_POSITION), null, false, null), views.last())
+    job.cancel()
+    runCurrent()
+  }
+}
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*HeadingCheckTest'`
Expected: コンパイルで落ちる（`HeadingCheck` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/location/HeadingCheck.kt b/app/src/main/java/com/touringproject/v2/location/HeadingCheck.kt
new file mode 100644
index 0000000..5112df2
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/location/HeadingCheck.kt
@@ -0,0 +1,91 @@
+package com.touringproject.v2.location
+
+import kotlinx.coroutines.delay
+
+/** How often SC-22 works the heading out again: the current position comes every second. */
+const val HEADING_CHECK_TICK_MS = 1_000L
+
+/**
+ * What SC-22 shows at one moment (slice 5 spec §4.5). here is the current position (null when there is no fresh one);
+ * fromRide tells whether the recording ride's route was the material; referenceAgeMs is how old the reference point is,
+ * on the points' own time (null without a heading).
+ */
+data class HeadingView(val result: HeadingResult, val here: Fix?, val fromRide: Boolean, val referenceAgeMs: Long?)
+
+/**
+ * SC-22's heading, worked out as an ask's is (findHeading), every HEADING_CHECK_TICK_MS while run() runs. The current
+ * position is the newest fresh fix of a 1 s watch, as an ask's recording takes it. While a ride records, the material is
+ * its route (rideHeading, which is RouteHeading). Otherwise (no ride, or a paused one, whose route is not watched) the
+ * points are gathered here, asked for and sifted as a ride's route is (acceptRoutePoint, isSince), and kept only in
+ * memory; they are dropped when a ride starts recording, when one stops (gathering starts again) and when run() ends.
+ * Cancelling run() removes both watches; a recording ride's own route watch is the service's and goes on.
+ */
+class HeadingCheck(
+  private val positions: PositionSource,
+  private val route: RouteSource,
+  private val recording: () -> Boolean,
+  private val rideHeading: suspend (here: Fix?) -> HeadingResult,
+  private val params: () -> HeadingParams,
+  /** The present on the fixes' own time (GpsClock). */
+  private val gpsNow: () -> Long,
+) {
+  private val lock = Any()
+  private var latest: Fix? = null
+  private val points = mutableListOf<Fix>()
+  // The generation of the gathering under way; a fix of an earlier one is not taken.
+  private var gathering = 0
+
+  suspend fun run(show: (HeadingView) -> Unit) {
+    val watch = runCatching { positions.watch(::seen) }.getOrNull()
+    runCatching { positions.lastKnown(::seen) }
+    var routeWatch: Subscription? = null
+    var wasRecording: Boolean? = null
+    try {
+      while (true) {
+        val nowRecording = recording()
+        if (nowRecording != wasRecording) {
+          routeWatch?.remove()
+          routeWatch = if (nowRecording) {
+            synchronized(lock) { points.clear(); gathering += 1 }
+            null
+          } else {
+            gather()
+          }
+          wasRecording = nowRecording
+        }
+        show(view(nowRecording))
+        delay(HEADING_CHECK_TICK_MS)
+      }
+    } finally {
+      routeWatch?.remove()
+      watch?.remove()
+      synchronized(lock) { points.clear(); latest = null; gathering += 1 }
+    }
+  }
+
+  private fun seen(fix: Fix) = synchronized(lock) {
+    val last = latest
+    if (last == null || (fix.elapsedMs ?: fix.timestamp) >= (last.elapsedMs ?: last.timestamp)) latest = fix
+  }
+
+  // Starts gathering anew: only fixes made from now on, as a segment's route takes them (RideController.onFix).
+  private fun gather(): Subscription? {
+    val since = positions.elapsed()
+    val sinceClock = positions.now()
+    val gen = synchronized(lock) { points.clear(); ++gathering }
+    return runCatching {
+      route.watch { fix ->
+        synchronized(lock) {
+          if (gen == gathering && acceptRoutePoint(fix) && fix.isSince(since, sinceClock)) points += fix
+        }
+      }
+    }.getOrNull()
+  }
+
+  private suspend fun view(fromRide: Boolean): HeadingView {
+    val (here, route) = synchronized(lock) { latest?.takeIf { it.isFresh(positions.now(), positions.elapsed()) } to points.toList() }
+    val result = if (fromRide) rideHeading(here) else findHeading(route, here, gpsNow(), params())
+    val age = (result as? HeadingResult.Found)?.let { gpsNow() - it.reference.timestamp }
+    return HeadingView(result, here, fromRide, age)
+  }
+}
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*HeadingCheckTest'`
Expected: PASS（全体で671件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/location/HeadingCheck.kt app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt
git commit -m "feat: work SC-22's heading out every second, from the ride's route or from points gathered like one"
```

---

### Task 5: SC-22 の文言

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt`（新規）

**Interfaces:**
- Consumes: `HeadingView`（Task 4）
- Produces: `fun compass16(degrees: Double): String`。`const val HELD_AFTER_MS = 30_000L`。`data class HeadingCheckUi(title: String, sides: String?, detail: String?, reason: String?, source: String)`。`fun headingCheckUi(view: HeadingView, params: HeadingParams): HeadingCheckUi`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt
new file mode 100644
index 0000000..4f7afaa
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt
@@ -0,0 +1,69 @@
+package com.touringproject.v2.ui
+
+import com.touringproject.v2.location.Fix
+import com.touringproject.v2.location.HeadingParams
+import com.touringproject.v2.location.HeadingResult
+import com.touringproject.v2.location.HeadingView
+import com.touringproject.v2.location.NoHeading
+import org.junit.Assert.assertEquals
+import org.junit.Test
+
+// Slice 5 spec §4.5 and the wording settled for plan 4: SC-22's card.
+class HeadingLabelsTest {
+  private val here = Fix(35.0, 139.0, 0, 6.2)
+  private val reference = Fix(35.0, 139.0, 0, 5.0)
+
+  @Test
+  fun the_sixteen_points_are_the_backends() {
+    assertEquals("北", compass16(0.0))
+    assertEquals("北", compass16(11.2))
+    assertEquals("北北東", compass16(11.3))
+    assertEquals("北西", compass16(315.0))
+    assertEquals("北北西", compass16(348.7))
+    assertEquals("北", compass16(359.9))
+    assertEquals("南西", compass16(-135.0))
+  }
+
+  @Test
+  fun a_heading_tells_its_direction_sides_and_material() {
+    val ui = headingCheckUi(HeadingView(HeadingResult.Found(337.6, reference, 16.4), here, fromRide = true, referenceAgeMs = 3_400), HeadingParams())
+    assertEquals(
+      HeadingCheckUi(
+        "北北西へ（338°）",
+        "右手 東北東 ／ 左手 西南西",
+        "位置の精度 6m · 基準の点 16m 手前（3秒前）",
+        null,
+        "走行のルートから求めています。いま質問すると、この方位を AI に渡します。",
+      ),
+      ui,
+    )
+  }
+
+  @Test
+  fun a_reference_older_than_30_seconds_says_the_heading_is_held() {
+    val held = headingCheckUi(HeadingView(HeadingResult.Found(315.0, reference, 18.0), here, true, 150_000), HeadingParams())
+    assertEquals("位置の精度 6m · 基準の点 18m 手前（2分前。止まる直前の向きを保っています）", held.detail)
+    assertEquals("右手 北東 ／ 左手 南西", held.sides)
+    val recent = headingCheckUi(HeadingView(HeadingResult.Found(315.0, reference, 18.0), here, true, 30_000), HeadingParams())
+    assertEquals("位置の精度 6m · 基準の点 18m 手前（30秒前）", recent.detail)
+  }
+
+  @Test
+  fun degrees_that_round_to_360_are_0_and_an_unknown_accuracy_says_so() {
+    val ui = headingCheckUi(HeadingView(HeadingResult.Found(359.7, reference, 15.0), here.copy(accuracy = null), false, 5_000), HeadingParams())
+    assertEquals("北へ（0°）", ui.title)
+    assertEquals("位置の精度 不明 · 基準の点 15m 手前（5秒前）", ui.detail)
+    assertEquals("この画面を開いてから集めた位置で、走行中と同じに求めています。画面を離れると、集めた位置は捨てます。", ui.source)
+  }
+
+  @Test
+  fun no_heading_tells_why_with_the_parameters_of_the_moment() {
+    val params = HeadingParams(referenceMeters = 15, accuracyMeters = 20, holdMinutes = 10)
+    fun reason(why: NoHeading, at: Fix? = here) = headingCheckUi(HeadingView(HeadingResult.None(why), at, false, null), params)
+    assertEquals(HeadingCheckUi("方位なし", null, null, "位置が取れていません", reason(NoHeading.NO_POSITION, null).source), reason(NoHeading.NO_POSITION, null))
+    assertEquals("位置の精度が悪いため使いません（精度 35m・上限 20m）", reason(NoHeading.POOR_ACCURACY, here.copy(accuracy = 35.0)).reason)
+    assertEquals("位置の精度 35m", reason(NoHeading.POOR_ACCURACY, here.copy(accuracy = 35.0)).detail)
+    assertEquals("まだ基準の距離（15m）ほど動いていません", reason(NoHeading.NOT_MOVED).reason)
+    assertEquals("止まってから、向きを保つ上限（10分）を超えました", reason(NoHeading.HELD_TOO_LONG).reason)
+  }
+}
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*HeadingLabelsTest'`
Expected: コンパイルで落ちる（`headingCheckUi` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt b/app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt
new file mode 100644
index 0000000..10cec6f
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt
@@ -0,0 +1,62 @@
+package com.touringproject.v2.ui
+
+import com.touringproject.v2.location.HeadingParams
+import com.touringproject.v2.location.HeadingResult
+import com.touringproject.v2.location.HeadingView
+import com.touringproject.v2.location.NoHeading
+import kotlin.math.roundToInt
+
+// How SC-22 tells the heading (slice 5 spec §4.5). The names of the directions are the Backend's, which it gives the AI.
+
+private val COMPASS_16 = listOf(
+  "北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西",
+)
+
+/** The nearest of the sixteen points of the compass. */
+fun compass16(degrees: Double): String = COMPASS_16[((((degrees % 360) + 360) % 360 + 11.25) / 22.5).toInt() % 16]
+
+/** A reference point older than this means the bike has stood still: no point is added while it does. */
+const val HELD_AFTER_MS = 30_000L
+
+/** SC-22's card. sides is null without a heading; reason is null with one. */
+data class HeadingCheckUi(val title: String, val sides: String?, val detail: String?, val reason: String?, val source: String)
+
+private fun metres(value: Double) = "${value.roundToInt()}m"
+
+private fun ago(ms: Long): String = if (ms < 60_000) "${ms / 1_000}秒前" else "${ms / 60_000}分前"
+
+fun headingCheckUi(view: HeadingView, params: HeadingParams): HeadingCheckUi {
+  val accuracy = view.here?.let { here -> "位置の精度 ${here.accuracy?.let(::metres) ?: "不明"}" }
+  val source = if (view.fromRide) {
+    "走行のルートから求めています。いま質問すると、この方位を AI に渡します。"
+  } else {
+    "この画面を開いてから集めた位置で、走行中と同じに求めています。画面を離れると、集めた位置は捨てます。"
+  }
+  return when (val result = view.result) {
+    is HeadingResult.Found -> {
+      val degrees = result.degrees
+      val age = view.referenceAgeMs ?: 0
+      val held = if (age > HELD_AFTER_MS) "。止まる直前の向きを保っています" else ""
+      HeadingCheckUi(
+        title = "${compass16(degrees)}へ（${degrees.roundToInt() % 360}°）",
+        sides = "右手 ${compass16(degrees + 90)} ／ 左手 ${compass16(degrees - 90)}",
+        detail = "$accuracy · 基準の点 ${metres(result.meters)} 手前（${ago(age)}$held）",
+        reason = null,
+        source = source,
+      )
+    }
+    is HeadingResult.None -> HeadingCheckUi(
+      title = "方位なし",
+      sides = null,
+      detail = accuracy,
+      reason = when (result.reason) {
+        NoHeading.NO_POSITION -> "位置が取れていません"
+        NoHeading.POOR_ACCURACY ->
+          "位置の精度が悪いため使いません（精度 ${view.here?.accuracy?.let(::metres) ?: "不明"}・上限 ${params.accuracyMeters}m）"
+        NoHeading.NOT_MOVED -> "まだ基準の距離（${params.referenceMeters}m）ほど動いていません"
+        NoHeading.HELD_TOO_LONG -> "止まってから、向きを保つ上限（${params.holdMinutes}分）を超えました"
+      },
+      source = source,
+    )
+  }
+}
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*HeadingLabelsTest'`
Expected: PASS（全体で676件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt
git commit -m "feat: word SC-22's heading in the sixteen points the AI is given, with its material or why there is none"
```

---

### Task 6: SC-22 の画面と設定の行

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ui/HeadingCheckScreen.kt`
- Modify: `settings/Settings.kt`・`ui/SettingsScreens.kt`・`ui/AppUi.kt`・`AppGraph.kt`
- Test: `settings/SettingsTest.kt`・`ui/ScreensTest.kt`・`ui/AppUiTest.kt`

**Interfaces:**
- Consumes: `HeadingCheck`・`HeadingView`（Task 4）・`HeadingCheckUi`・`headingCheckUi`（Task 5）・`AppGraph.positionSource`・`gpsClock`・`routeHeading`（Task 3）
- Produces: `fun Settings.withHeadingDefaults(): Settings`。`SettingsScreen(..., onHeadingCheck: () -> Unit = {})`。`HeadingCheckScreen(ui: HeadingCheckUi?, settings: Settings, onUpdate: (Settings) -> Unit, onReset: () -> Unit, modifier)`。テストの印は `headingTitle`・`headingSides`・`headingReason`・`headingDetail`・`headingSource`・`headingReference-<m>`・`headingAccuracy-<m>`・`headingHold-<分>`・`headingDefaults`。`AppGraph.headingCheck(): HeadingCheck`。`HeadingCheckKey`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
index 74e4852..8b8ec5d 100644
--- a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
@@ -104,6 +104,13 @@ class SettingsTest {
     assertEquals(s.copy(recordLimitSeconds = 20, startCueMs = 1_500), s.withRecordingDefaults())
   }
 
+  // SC-22's 「既定値に戻す」 puts back its three values only.
+  @Test
+  fun the_heading_defaults_leave_the_other_settings_as_they_are() {
+    val s = Settings("rider01", startCueMs = 0, headingReferenceMeters = 30, headingAccuracyMeters = 50, headingHoldMinutes = 2)
+    assertEquals(s.copy(headingReferenceMeters = 15, headingAccuracyMeters = 20, headingHoldMinutes = 10), s.withHeadingDefaults())
+  }
+
   @Test
   fun not_json_falls_back_to_defaults() {
     val (s, needsSave) = decodeSettings("{not json", Random(3))
diff --git a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
index 6870174..2cf8881 100644
--- a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
@@ -74,6 +74,21 @@ class AppUiTest {
     rule.onNodeWithText("上限 20秒 · 合図 1.5秒").assertExists()
   }
 
+  // Slice 5 spec §4.5: SC-22 opens from the settings, tells a heading or why there is none, saves each parameter at once
+  // and puts the three back with a toast.
+  @Test
+  fun the_heading_check_saves_at_once_and_goes_back_to_its_defaults() {
+    val graph = (rule.activity.application as TouringApp).graph
+    rule.onNodeWithTag("tab-SETTINGS").performClick()
+    rule.onNodeWithText("位置と方位の確認").performScrollTo().performClick()
+    rule.waitUntil(5_000) { rule.onAllNodesWithTagExists("headingTitle") }
+    rule.onNodeWithTag("headingReference-30").performClick()
+    rule.waitUntil(5_000) { graph.settings.current().headingReferenceMeters == 30 }
+    rule.onNodeWithTag("headingDefaults").performScrollTo().performClick()
+    rule.waitUntil(5_000) { graph.settings.current().headingReferenceMeters == 15 }
+    assertEquals("既定値に戻しました", ShadowToast.getTextOfLatestToast())
+  }
+
   @Test
   fun the_records_tab_lists_the_kept_rides_and_home_keeps_its_place() {
     val graph = (rule.activity.application as TouringApp).graph
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index adaee20..96798da 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -421,6 +421,41 @@ class SettingsScreensTest {
     assertEquals(1, resets)
   }
 
+  // Slice 5 spec §4.5 and §14: SC-22 opens from the row under 「録音の確認」.
+  @Test
+  fun the_settings_list_leads_to_the_heading_check() {
+    var opened = false
+    rule.setContent { SettingsScreen(Settings("rider01"), null, {}, {}, {}, {}, {}, {}, "0.2.0", onHeadingCheck = { opened = true }) }
+    rule.onNodeWithText("位置と方位の確認").performScrollTo().performClick()
+    assertTrue(opened)
+  }
+
+  // SC-22: the card tells the heading of the moment, and each parameter is one of four values.
+  @Test
+  fun the_heading_check_shows_the_heading_and_changes_its_parameters() {
+    var settings by mutableStateOf(Settings("rider01"))
+    var ui by mutableStateOf<HeadingCheckUi?>(null)
+    var resets = 0
+    rule.setContent { HeadingCheckScreen(ui, settings, { settings = it }, { resets++ }) }
+    rule.onNodeWithText("位置を確かめています…").assertExists()
+    ui = HeadingCheckUi("北西へ（315°）", "右手 北東 ／ 左手 南西", "位置の精度 6m · 基準の点 18m 手前（3秒前）", null, "走行のルートから求めています。")
+    rule.onNodeWithTag("headingTitle").assertTextEquals("北西へ（315°）")
+    rule.onNodeWithTag("headingSides").assertTextEquals("右手 北東 ／ 左手 南西")
+    rule.onNodeWithTag("headingReason").assertDoesNotExist()
+    ui = HeadingCheckUi("方位なし", null, "位置の精度 8m", "まだ基準の距離（15m）ほど動いていません", "この画面を開いてから集めた位置で")
+    rule.onNodeWithTag("headingReason").assertTextEquals("まだ基準の距離（15m）ほど動いていません")
+    rule.onNodeWithTag("headingSides").assertDoesNotExist()
+    for (m in listOf(10, 15, 20, 30)) rule.onNodeWithTag("headingReference-$m").assertTextEquals("${m}m")
+    for (m in listOf(10, 20, 30, 50)) rule.onNodeWithTag("headingAccuracy-$m").assertTextEquals("${m}m")
+    for (min in listOf(2, 5, 10, 30)) rule.onNodeWithTag("headingHold-$min").assertTextEquals("${min}分")
+    rule.onNodeWithTag("headingReference-30").performClick()
+    rule.onNodeWithTag("headingAccuracy-50").performScrollTo().performClick()
+    rule.onNodeWithTag("headingHold-2").performScrollTo().performClick()
+    assertEquals(listOf(30, 50, 2), listOf(settings.headingReferenceMeters, settings.headingAccuracyMeters, settings.headingHoldMinutes))
+    rule.onNodeWithTag("headingDefaults").performScrollTo().performClick()
+    assertEquals(1, resets)
+  }
+
   @Test
   fun the_settings_list_shows_the_app_version_as_a_row_that_leads_nowhere() {
     rule.setContent { SettingsScreen(Settings("rider01"), null, {}, {}, {}, {}, {}, {}, "0.2.0") }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SettingsTest' --tests '*ScreensTest' --tests '*AppUiTest'`
Expected: コンパイルで落ちる（`withHeadingDefaults`・`HeadingCheckScreen` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index abd1e13..8701965 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -28,6 +28,7 @@ import com.touringproject.v2.handsfree.PressRouter
 import com.touringproject.v2.location.FusedPositionSource
 import com.touringproject.v2.location.FusedRouteSource
 import com.touringproject.v2.location.GpsClock
+import com.touringproject.v2.location.HeadingCheck
 import com.touringproject.v2.location.HeadingParams
 import com.touringproject.v2.location.PositionSource
 import com.touringproject.v2.location.PositionTracker
@@ -197,6 +198,19 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     log = { message, e -> Log.w("trv2.ride", message, e) },
   )
 
+  /**
+   * SC-22's heading, a new one each time the screen shows (slice 5 spec §4.5): the ride's route while it records, and
+   * points gathered the same way otherwise.
+   */
+  fun headingCheck() = HeadingCheck(
+    positionSource,
+    routeSource,
+    recording = { rides.active.value?.status == RideStatus.RECORDING },
+    rideHeading = routeHeading::find,
+    params = { settings.settings.value?.headingParams ?: HeadingParams() },
+    gpsNow = gpsClock::now,
+  )
+
   /** SC-19 writes point memos through here; each change is something new to send (slice 3 spec §5.1). */
   val notes = RoomNotes(
     database.notes(), database.rides(), System::currentTimeMillis, { UUID.randomUUID().toString() }, sync::request,
diff --git a/app/src/main/java/com/touringproject/v2/settings/Settings.kt b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
index 2e72bed..a687d31 100644
--- a/app/src/main/java/com/touringproject/v2/settings/Settings.kt
+++ b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
@@ -74,6 +74,13 @@ fun Settings.withRecordingDefaults(): Settings = copy(recordLimitSeconds = DEFAU
 
 val Settings.headingParams: HeadingParams get() = HeadingParams(headingReferenceMeters, headingAccuracyMeters, headingHoldMinutes)
 
+/** SC-22's 「既定値に戻す」: its three values, and nothing else. */
+fun Settings.withHeadingDefaults(): Settings = copy(
+  headingReferenceMeters = DEFAULT_HEADING_REFERENCE_M,
+  headingAccuracyMeters = DEFAULT_HEADING_ACCURACY_M,
+  headingHoldMinutes = DEFAULT_HEADING_HOLD_MINUTES,
+)
+
 /**
  * The longest recording time each time the rider changes it, but not the value first loaded (US-C-08.005). AppGraph
  * follows it, so the recording ride's deadline moves even when SC-16 goes away mid-save (Android #33).
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index e9a10e3..ca29aea 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -26,7 +26,10 @@ import androidx.compose.runtime.saveable.rememberSaveable
 import androidx.compose.runtime.setValue
 import androidx.compose.ui.Modifier
 import androidx.compose.ui.platform.LocalContext
+import androidx.lifecycle.Lifecycle
+import androidx.lifecycle.compose.LocalLifecycleOwner
 import androidx.lifecycle.compose.collectAsStateWithLifecycle
+import androidx.lifecycle.repeatOnLifecycle
 import androidx.navigation3.runtime.NavKey
 import androidx.navigation3.runtime.entryProvider
 import androidx.navigation3.runtime.rememberDecoratedNavEntries
@@ -39,10 +42,13 @@ import com.touringproject.v2.api.ApiClient
 import com.touringproject.v2.ask.Phase
 import com.touringproject.v2.ask.isBusy
 import com.touringproject.v2.ask.rideNow
+import com.touringproject.v2.location.HeadingView
 import com.touringproject.v2.records.NoteDraft
 import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.ride.RideStatus
 import com.touringproject.v2.settings.LaunchableApp
+import com.touringproject.v2.settings.headingParams
+import com.touringproject.v2.settings.withHeadingDefaults
 import com.touringproject.v2.settings.withRecordingDefaults
 import com.touringproject.v2.sync.TakeOp
 import kotlinx.coroutines.delay
@@ -59,6 +65,7 @@ import kotlinx.serialization.Serializable
 @Serializable data object VolumeKey : NavKey
 @Serializable data object RecordingsKey : NavKey
 @Serializable data object RecordingSettingsKey : NavKey
+@Serializable data object HeadingCheckKey : NavKey
 @Serializable data object RideRecordingKey : NavKey
 @Serializable data object DataKey : NavKey
 @Serializable data object RecordsKey : NavKey
@@ -242,6 +249,26 @@ fun AppUi(graph: AppGraph) {
                   saved = saveRowValue(summary ?: SaveSummary()),
                   onData = { tabs.push(DataKey) },
                   onRecordingSettings = { tabs.push(RecordingSettingsKey) },
+                  onHeadingCheck = { tabs.push(HeadingCheckKey) },
+                )
+              }
+              entry<HeadingCheckKey> {
+                var view by remember { mutableStateOf<HeadingView?>(null) }
+                val lifecycle = LocalLifecycleOwner.current.lifecycle
+                // Its watches run only while SC-22 shows; leaving it, or the app going to the back, drops what it
+                // gathered (slice 5 spec §4.5).
+                LaunchedEffect(lifecycle) {
+                  lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) { graph.headingCheck().run { view = it } }
+                }
+                HeadingCheckScreen(
+                  view?.let { headingCheckUi(it, current.headingParams) },
+                  current,
+                  { next -> scope.launch { graph.settings.update(next) } },
+                  onReset = {
+                    scope.launch { graph.settings.update(current.withHeadingDefaults()) }
+                    Toast.makeText(context, "既定値に戻しました", Toast.LENGTH_SHORT).show()
+                  },
+                  modifier = Modifier.safeDrawingPadding(),
                 )
               }
               entry<RecordingSettingsKey> {
diff --git a/app/src/main/java/com/touringproject/v2/ui/HeadingCheckScreen.kt b/app/src/main/java/com/touringproject/v2/ui/HeadingCheckScreen.kt
new file mode 100644
index 0000000..04c0aa3
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/ui/HeadingCheckScreen.kt
@@ -0,0 +1,79 @@
+package com.touringproject.v2.ui
+
+import androidx.compose.foundation.BorderStroke
+import androidx.compose.foundation.layout.Arrangement
+import androidx.compose.foundation.layout.Column
+import androidx.compose.foundation.layout.Row
+import androidx.compose.foundation.layout.fillMaxSize
+import androidx.compose.foundation.layout.fillMaxWidth
+import androidx.compose.foundation.layout.padding
+import androidx.compose.foundation.rememberScrollState
+import androidx.compose.foundation.shape.RoundedCornerShape
+import androidx.compose.foundation.verticalScroll
+import androidx.compose.material3.Button
+import androidx.compose.material3.FilterChip
+import androidx.compose.material3.Surface
+import androidx.compose.material3.Text
+import androidx.compose.runtime.Composable
+import androidx.compose.ui.Modifier
+import androidx.compose.ui.graphics.Color
+import androidx.compose.ui.platform.testTag
+import androidx.compose.ui.text.font.FontWeight
+import androidx.compose.ui.unit.dp
+import androidx.compose.ui.unit.sp
+import com.touringproject.v2.settings.HEADING_ACCURACY_M_CHOICES
+import com.touringproject.v2.settings.HEADING_HOLD_MINUTES_CHOICES
+import com.touringproject.v2.settings.HEADING_REFERENCE_M_CHOICES
+import com.touringproject.v2.settings.Settings
+
+private val Muted = Color(0xFF666666)
+
+@Composable
+private fun Choices(title: String, note: String, choices: List<Int>, chosen: Int, unit: String, tag: String, onChoose: (Int) -> Unit) {
+  Text(title, fontSize = 18.sp)
+  Text(note, color = Muted, fontSize = 14.sp)
+  Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
+    choices.forEach { value ->
+      FilterChip(
+        selected = chosen == value,
+        onClick = { onChoose(value) },
+        label = { Text("$value$unit", fontSize = 16.sp, fontWeight = FontWeight.Bold) },
+        modifier = Modifier.weight(1f).testTag("$tag-$value"),
+      )
+    }
+  }
+}
+
+/**
+ * SC-22 (slice 5 spec §4.5): a check made while stopped. ui is the heading of the moment (null until the first one is
+ * worked out). Each parameter is saved at once and takes effect from the next working-out; onReset puts the three back
+ * (「既定値に戻す」, told by a toast).
+ */
+@Composable
+fun HeadingCheckScreen(ui: HeadingCheckUi?, settings: Settings, onUpdate: (Settings) -> Unit, onReset: () -> Unit, modifier: Modifier = Modifier) {
+  Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
+    Surface(Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Color(0xFFCCCCCC))) {
+      Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
+        if (ui == null) {
+          Text("位置を確かめています…", fontSize = 16.sp)
+        } else {
+          Text(ui.title, fontSize = 22.sp, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("headingTitle"))
+          ui.sides?.let { Text(it, color = Muted, fontSize = 16.sp, modifier = Modifier.testTag("headingSides")) }
+          ui.reason?.let { Text(it, fontSize = 16.sp, modifier = Modifier.testTag("headingReason")) }
+          ui.detail?.let { Text(it, color = Muted, fontSize = 14.sp, modifier = Modifier.testTag("headingDetail")) }
+          Text(ui.source, color = Muted, fontSize = 14.sp, modifier = Modifier.testTag("headingSource"))
+        }
+      }
+    }
+    Choices("基準の距離", "今の位置からこれだけ離れた点との向きを方位にします", HEADING_REFERENCE_M_CHOICES, settings.headingReferenceMeters, "m", "headingReference") {
+      onUpdate(settings.copy(headingReferenceMeters = it))
+    }
+    Choices("精度の上限", "これより精度の悪い位置は使いません", HEADING_ACCURACY_M_CHOICES, settings.headingAccuracyMeters, "m", "headingAccuracy") {
+      onUpdate(settings.copy(headingAccuracyMeters = it))
+    }
+    Choices("向きを保つ上限", "止まっているあいだ、止まる直前の向きを使い続ける長さ", HEADING_HOLD_MINUTES_CHOICES, settings.headingHoldMinutes, "分", "headingHold") {
+      onUpdate(settings.copy(headingHoldMinutes = it))
+    }
+    Button(onClick = onReset, modifier = Modifier.fillMaxWidth().testTag("headingDefaults")) { Text("既定値に戻す", fontSize = 16.sp) }
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
index 95ec282..ca1ba5f 100644
--- a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
@@ -91,6 +91,7 @@ fun SettingsScreen(
   saved: String = "",
   onData: () -> Unit = {},
   onRecordingSettings: () -> Unit = {},
+  onHeadingCheck: () -> Unit = {},
 ) {
   val returnValue = if (!settings.returnEnabled) "戻らない" else settings.returnApp?.label ?: "未設定"
   // Scrolls: the list outgrows a small screen.
@@ -104,6 +105,8 @@ fun SettingsScreen(
     SettingsRow("録音の設定", recordingRowValue(settings), onRecordingSettings)
     SettingsRow("回答の音量", "+${settings.answerVolumeDb}dB", onVolume)
     SettingsRow("録音の確認", "", onRecordings)
+    // Under the other check, as the mock's 確認 section has them (slice 5 spec §14).
+    SettingsRow("位置と方位の確認", "", onHeadingCheck)
     SettingsRow("バージョン", version, null, Modifier.testTag("versionRow"))
   }
 }
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SettingsTest' --tests '*ScreensTest' --tests '*AppUiTest'`
Expected: PASS（全体で680件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/settings/Settings.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/ui/HeadingCheckScreen.kt app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
git commit -m "feat: add SC-22, the check of the position and heading, under the recording check in the settings"
```

---

### Task 7: SC-05 のユーザー名

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt`・`ui/AppUi.kt`
- Test: `ui/RecordsScreensTest.kt`・`ui/AppUiTest.kt`

**Interfaces:**
- Produces: `RideListScreen(sections, onRide, modifier, userName: String? = null, onUser: () -> Unit = {})`。テストの印 `listUser`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
index 2cf8881..8cbf575 100644
--- a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
@@ -118,6 +118,18 @@ class AppUiTest {
     rule.onNodeWithText("走行の記録").assertExists()
   }
 
+  // Slice 5 spec §7: SC-05's user name opens SC-18 above Settings' first screen, as Home's does.
+  @Test
+  fun the_records_user_name_opens_the_user_name_screen() {
+    val graph = (rule.activity.application as TouringApp).graph
+    rule.onNodeWithTag("tab-RECORDS").performClick()
+    rule.onNodeWithTag("listUser").assertTextContains(graph.settings.current().userName, substring = true)
+    rule.onNodeWithTag("listUser").performClick()
+    rule.onNodeWithTag("userInput").assertExists()
+    back()
+    rule.onNodeWithText("走行の記録").assertExists()
+  }
+
   // Android #34
   @Test
   fun a_name_being_typed_survives_a_trip_to_another_tab() {
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
index 798ddf2..a42b4aa 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
@@ -79,6 +79,16 @@ class RecordsScreensTest {
     assertEquals(listOf("r1"), opened)
   }
 
+  // Slice 5 spec §7: the list says whose records these are, and the name opens SC-18.
+  @Test
+  fun the_list_shows_the_user_name_which_opens_the_user_screen() {
+    var opened = 0
+    rule.setContent { RideListScreen(emptyList(), {}, userName = "rider01", onUser = { opened++ }) }
+    rule.onNodeWithTag("listUser").assertTextEquals("👤 rider01")
+    rule.onNodeWithTag("listUser").performClick()
+    assertEquals(1, opened)
+  }
+
   @Test
   fun without_rides_the_list_says_how_to_record_one() {
     rule.setContent { RideListScreen(emptyList(), {}) }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RecordsScreensTest' --tests '*AppUiTest'`
Expected: コンパイルで落ちる（`userName` の引数が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index ca29aea..0697130 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -197,6 +197,8 @@ fun AppUi(graph: AppGraph) {
                   rideList?.let { rideSections(it, System.currentTimeMillis(), ZoneId.systemDefault()) },
                   onRide = { tabs.push(RideKey(it)) },
                   modifier = Modifier.safeDrawingPadding(),
+                  userName = current.userName,
+                  onUser = { tabs.open(Tab.SETTINGS, UserKey) },
                 )
               }
               entry<RideKey> { key ->
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
index 1346933..ba40c60 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
@@ -46,6 +46,7 @@ import androidx.compose.ui.Modifier
 import androidx.compose.ui.graphics.Color
 import androidx.compose.ui.platform.LocalContext
 import androidx.compose.ui.platform.testTag
+import androidx.compose.ui.text.font.FontFamily
 import androidx.compose.ui.text.font.FontWeight
 import androidx.compose.ui.text.style.TextOverflow
 import androidx.compose.ui.unit.dp
@@ -80,11 +81,27 @@ private fun TopBar(title: String, onBack: () -> Unit, actions: @Composable () ->
 private fun Muted(text: String, modifier: Modifier = Modifier, size: Int = 14) =
   Text(text, modifier, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = size.sp)
 
-/** SC-05's rides, the one recording or paused first. The switch to the days comes with plan 4b. */
+/**
+ * SC-05's rides, the one recording or paused first. userName is the user whose records these are, shown by the title
+ * (US-E-06.010); pressing it opens SC-18, as Home's does (slice 5 spec §7).
+ */
 @Composable
-fun RideListScreen(sections: List<RideSection>?, onRide: (String) -> Unit, modifier: Modifier = Modifier) {
+fun RideListScreen(
+  sections: List<RideSection>?,
+  onRide: (String) -> Unit,
+  modifier: Modifier = Modifier,
+  userName: String? = null,
+  onUser: () -> Unit = {},
+) {
   Column(modifier.fillMaxSize()) {
-    Text("記録", Modifier.padding(16.dp), fontSize = 22.sp, fontWeight = FontWeight.Bold)
+    Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
+      Text("記録", fontSize = 22.sp, fontWeight = FontWeight.Bold)
+      userName?.let {
+        OutlinedButton(onClick = onUser, modifier = Modifier.testTag("listUser")) {
+          Text("👤 $it", fontFamily = FontFamily.Monospace)
+        }
+      }
+    }
     when {
       sections == null -> Unit
       sections.isEmpty() -> Muted("まだ走行の記録がありません。ホームの「▶ 走行を開始」で記録します。", Modifier.padding(horizontal = 16.dp), 16)
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RecordsScreensTest' --tests '*AppUiTest'`
Expected: PASS（全体で682件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
git commit -m "feat: show the user name on the records list and open SC-18 from it"
```

---

### Task 8: 短い場所は県の名前だけを外す（#50）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt`
- Test: `ui/RecordLabelsTest.kt`

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
index 5f7c532..b050c52 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
@@ -163,6 +163,16 @@ class RecordLabelsTest {
     assertEquals("場所不明", shortPlace(null))
   }
 
+  // Android #50: only a prefecture's own name goes, of whichever length.
+  @Test
+  fun the_short_place_keeps_a_place_that_only_has_ken_in_it() {
+    assertEquals("西区県庁前", shortPlace("西区県庁前"))
+    assertEquals("箱根町", shortPlace("神奈川県箱根町"))
+    assertEquals("鹿児島市", shortPlace("鹿児島県鹿児島市"))
+    assertEquals("那覇市", shortPlace("沖縄県那覇市"))
+    assertEquals("大阪市北区", shortPlace("大阪府大阪市北区"))
+  }
+
   // US-D-04.005: the memos show in the list, the timeline, the pins and SC-07.
   @Test
   fun memos_are_marked_where_the_rider_looks_for_them() {
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RecordLabelsTest'`
Expected: FAIL（「西区県庁前」が「庁前」になる）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
index 35896f8..1a97d6a 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
@@ -157,7 +157,13 @@ fun notePins(notes: List<NoteRecord>): List<MapPin> {
   }
 }
 
-private val PREFECTURE = Regex("^(東京都|北海道|(京都|大阪)府|.{2,3}県)")
+// The 43 prefectures named 〜県, by name: "two or three characters and 県" also matched an address like 西区県庁前 (Android #50).
+private val KEN = listOf(
+  "青森", "岩手", "宮城", "秋田", "山形", "福島", "茨城", "栃木", "群馬", "埼玉", "千葉", "神奈川", "新潟", "富山", "石川",
+  "福井", "山梨", "長野", "岐阜", "静岡", "愛知", "三重", "滋賀", "兵庫", "奈良", "和歌山", "鳥取", "島根", "岡山", "広島",
+  "山口", "徳島", "香川", "愛媛", "高知", "福岡", "佐賀", "長崎", "熊本", "大分", "宮崎", "鹿児島", "沖縄",
+)
+private val PREFECTURE = Regex("^(東京都|北海道|(京都|大阪)府|(${KEN.joinToString("|")})県)")
 
 /** The mock's short place: the address without its prefecture; an address that starts otherwise is kept whole (Android #45). */
 fun shortPlace(address: String?): String = address?.replace(PREFECTURE, "")?.ifBlank { null } ?: "場所不明"
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RecordLabelsTest'`
Expected: PASS（全体で683件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
git commit -m "fix: drop only a prefecture's own name from the short place (#50)"
```

---

### Task 9: SC-19 の声の入力の隙（#61）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/records/Memos.kt`・`records/Notes.kt`・`ui/MemoScreen.kt`・`voice/VoiceInput.kt`
- Test: `records/MemosTest.kt`・`records/NotesTest.kt`・`ui/NoteScreenTest.kt`・`voice/VoiceInputTest.kt`

**Interfaces:**
- Produces: `data class Appended(text: String, whole: Boolean)`・`fun appendHeard(current: String, heard: String): Appended`（今までは `String`）。テストの印 `heardCut`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/records/MemosTest.kt b/app/src/test/java/com/touringproject/v2/records/MemosTest.kt
index 26e1c12..81684c7 100644
--- a/app/src/test/java/com/touringproject/v2/records/MemosTest.kt
+++ b/app/src/test/java/com/touringproject/v2/records/MemosTest.kt
@@ -20,6 +20,18 @@ class MemosTest {
     assertEquals("あ".repeat(2000), cutMemo("あ".repeat(2500)))
   }
 
+  // Android #61: an emoji made of several code points is kept whole or left out whole at the 2000th character.
+  @Test
+  fun the_cut_splits_no_emoji_made_of_several_code_points() {
+    val family = "👨‍👩‍👧"
+    assertEquals("あ".repeat(1997), cutMemo("あ".repeat(1997) + family))
+    assertEquals("あ".repeat(1995) + family, cutMemo("あ".repeat(1995) + family + "い"))
+    assertEquals("あ".repeat(1999), cutMemo("あ".repeat(1999) + "🇯🇵"))
+    assertEquals("あ".repeat(1997) + "🇯🇵", cutMemo("あ".repeat(1997) + "🇯🇵🇯🇵"))
+    assertEquals("あ".repeat(1999), cutMemo("あ".repeat(1999) + "👍🏽"))
+    assertEquals("あ".repeat(1999), cutMemo("あ".repeat(1999) + "❤️"))
+  }
+
   @Test
   fun a_memo_fits_up_to_2000_characters() {
     assertTrue(memoFits(null))
diff --git a/app/src/test/java/com/touringproject/v2/records/NotesTest.kt b/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
index c3b144b..f69b588 100644
--- a/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
+++ b/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
@@ -27,10 +27,13 @@ class NotesTest {
   // Slice 3 spec §7.3: what was heard goes at the end of what is written, on a line of its own, within 2000 characters.
   @Test
   fun what_was_heard_goes_at_the_end_on_a_line_of_its_own() {
-    assertEquals("展望スペース", appendHeard("", "展望スペース"))
-    assertEquals("料金所の手前\n展望スペース", appendHeard("料金所の手前", "展望スペース"))
-    assertEquals("料金所の手前\n展望スペース", appendHeard("料金所の手前\n", "展望スペース"))
+    assertEquals(Appended("展望スペース", true), appendHeard("", "展望スペース"))
+    assertEquals(Appended("料金所の手前\n展望スペース", true), appendHeard("料金所の手前", "展望スペース"))
+    assertEquals(Appended("料金所の手前\n展望スペース", true), appendHeard("料金所の手前\n", "展望スペース"))
     val full = appendHeard("あ".repeat(1998), "いうえ")
-    assertEquals(2000, full.codePointCount(0, full.length))
+    assertEquals(2000, full.text.codePointCount(0, full.text.length))
+    // Android #61: what did not fit is told, so it is not dropped without a word.
+    assertEquals(false, full.whole)
+    assertEquals(Appended("あ".repeat(1999) + "\n", false), appendHeard("あ".repeat(1999), "いうえ"))
   }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt b/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
index b1f6dff..c150d2f 100644
--- a/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
@@ -176,6 +176,21 @@ class NoteScreenTest {
     assertEquals(listOf("料金所の手前\n展望スペース"), saved)
   }
 
+  // Android #61: what was heard that did not fit in 2000 characters is told under the field, until the text changes.
+  @Test
+  fun what_was_heard_that_did_not_fit_is_told() {
+    var heard by mutableStateOf<Heard?>(null)
+    rule.setContent {
+      NoteScreen(header, "あ".repeat(1999), { true }, {}, voice = NoteVoiceUi(VoicePhase.IDLE, null, heard, online = true), onHeard = { heard = null })
+    }
+    rule.onNodeWithTag("heardCut").assertDoesNotExist()
+    heard = Heard(1, "展望スペース")
+    rule.waitForIdle()
+    rule.onNodeWithTag("heardCut").assertTextEquals("入りきらなかった分は足せませんでした")
+    rule.onNodeWithTag("memoInput").performTextReplacement("料金所の手前")
+    rule.onNodeWithTag("heardCut").assertDoesNotExist()
+  }
+
   // Android #57: while the memo is being deleted, ✕, Back and a second delete do nothing; the screen closes once.
   @Test
   fun while_the_memo_is_being_deleted_nothing_else_closes_it() {
diff --git a/app/src/test/java/com/touringproject/v2/voice/VoiceInputTest.kt b/app/src/test/java/com/touringproject/v2/voice/VoiceInputTest.kt
index f88cb57..932871e 100644
--- a/app/src/test/java/com/touringproject/v2/voice/VoiceInputTest.kt
+++ b/app/src/test/java/com/touringproject/v2/voice/VoiceInputTest.kt
@@ -150,17 +150,19 @@ class VoiceInputTest {
     assertEquals(VOICE_IDLE, h.voice.state)
   }
 
+  // Android #61: the press starts nothing, and the failure cue tells it was not taken.
   @Test
-  fun a_press_while_the_text_is_being_made_does_nothing() = runTest {
+  fun a_press_while_the_text_is_being_made_starts_nothing_and_gets_the_failure_cue() = runTest {
     val h = VoiceHarness(this, getGate = CompletableDeferred())
     h.voice.press(Source.SCREEN)
     runCurrent()
     h.voice.press(Source.SCREEN)
     advanceTimeBy(1_500)
     assertEquals(VoicePhase.TRANSCRIBING, h.voice.state.phase)
-    h.voice.press(Source.SCREEN)
+    h.voice.press(Source.HANDSFREE)
     runCurrent()
     assertEquals(1, h.log.count { it == "rec:start" })
+    assertEquals("cue:failure", h.log.last())
     h.getGate!!.complete(Unit)
     advanceUntilIdle()
     assertEquals("展望スペース", h.voice.state.heard?.text)
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*MemosTest' --tests '*NotesTest' --tests '*NoteScreenTest' --tests '*VoiceInputTest'`
Expected: コンパイルで落ちる（`Appended` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/records/Memos.kt b/app/src/main/java/com/touringproject/v2/records/Memos.kt
index ef16180..6c3134e 100644
--- a/app/src/main/java/com/touringproject/v2/records/Memos.kt
+++ b/app/src/main/java/com/touringproject/v2/records/Memos.kt
@@ -11,9 +11,45 @@ private fun String.characters() = codePointCount(0, length)
 /** The memo a typed text keeps: trimmed, and none when it is blank (SC-08: saving an empty memo removes it). */
 fun memoText(input: String): String? = input.trim().ifEmpty { null }
 
-/** What the memo field keeps of a typed or pasted text: its first 2000 characters. */
+/**
+ * What the memo field keeps of a typed or pasted text: its first 2000 characters, cut where no character on screen is
+ * split (Android #61).
+ */
 fun cutMemo(input: String): String =
-  if (input.characters() <= MEMO_MAX) input else input.substring(0, input.offsetByCodePoints(0, MEMO_MAX))
+  if (input.characters() <= MEMO_MAX) input else input.substring(0, characterEnd(input, input.offsetByCodePoints(0, MEMO_MAX)))
+
+// A code point that belongs with the one before it on screen: a joiner, a variation selector, a skin tone, a keycap, a
+// tag, a combining mark. Written out because the JDK's BreakIterator joins emoji only from Java 20 on.
+private fun joinsBefore(cp: Int): Boolean =
+  cp == ZWJ || cp in 0xFE00..0xFE0F || cp in 0x1F3FB..0x1F3FF || cp == 0x20E3 || cp in 0xE0020..0xE007F ||
+    Character.getType(cp).let { it == Character.NON_SPACING_MARK.toInt() || it == Character.ENCLOSING_MARK.toInt() || it == Character.COMBINING_SPACING_MARK.toInt() }
+
+private const val ZWJ = 0x200D
+
+private fun isRegional(cp: Int) = cp in 0x1F1E6..0x1F1FF
+
+private fun regionalsBefore(s: String, end: Int): Int {
+  var count = 0
+  var i = end
+  while (i > 0 && isRegional(s.codePointBefore(i))) {
+    count += 1
+    i = s.offsetByCodePoints(i, -1)
+  }
+  return count
+}
+
+/** The end at or before end that splits no character on screen: an emoji joined with ZWJ, a flag, a skin tone. */
+private fun characterEnd(s: String, end: Int): Int {
+  var e = end
+  while (e in 1 until s.length) {
+    val next = s.codePointAt(e)
+    val before = s.codePointBefore(e)
+    val splits = joinsBefore(next) || before == ZWJ || (isRegional(next) && regionalsBefore(s, e) % 2 == 1)
+    if (!splits) break
+    e = s.offsetByCodePoints(e, -1)
+  }
+  return e
+}
 
 /** True when memo can be kept: none, or up to MEMO_MAX characters. */
 fun memoFits(memo: String?): Boolean = memo == null || memo.characters() <= MEMO_MAX
diff --git a/app/src/main/java/com/touringproject/v2/records/Notes.kt b/app/src/main/java/com/touringproject/v2/records/Notes.kt
index 6fb33ca..7a656fe 100644
--- a/app/src/main/java/com/touringproject/v2/records/Notes.kt
+++ b/app/src/main/java/com/touringproject/v2/records/Notes.kt
@@ -48,6 +48,12 @@ fun RoutePoint.toFix() = Fix(lat, lon, t, accuracy)
 fun noteDraft(id: String, rideId: String, at: Long, newest: RoutePoint?, headingDegrees: Double?) =
   NoteDraft(id, rideId, at, newest?.lat, newest?.lon, headingDegrees)
 
+/** The text with what was heard added; whole is false when some of it did not fit (Android #61). */
+data class Appended(val text: String, val whole: Boolean)
+
 /** SC-19's voice input: what was heard goes at the end of what is written, on a line of its own, within 2000 characters. */
-fun appendHeard(current: String, heard: String): String =
-  cutMemo(if (current.isEmpty() || current.endsWith("\n")) current + heard else current + "\n" + heard)
+fun appendHeard(current: String, heard: String): Appended {
+  val joined = if (current.isEmpty() || current.endsWith("\n")) current + heard else current + "\n" + heard
+  val kept = cutMemo(joined)
+  return Appended(kept, kept.length == joined.length)
+}
diff --git a/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt b/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
index f501cbf..c1a3252 100644
--- a/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
@@ -79,10 +79,13 @@ fun MemoEditor(
   val context = LocalContext.current
   val focus = remember { FocusRequester() }
   LaunchedEffect(Unit) { focus.requestFocus() }
+  // What was heard did not all fit; told until the text is changed (Android #61).
+  var heardCut by rememberSaveable { mutableStateOf(false) }
   LaunchedEffect(heard?.seq) {
     val next = heard ?: return@LaunchedEffect
-    val text = appendHeard(field.text, next.text)
-    field = TextFieldValue(text, TextRange(text.length))
+    val appended = appendHeard(field.text, next.text)
+    field = TextFieldValue(appended.text, TextRange(appended.text.length))
+    heardCut = !appended.whole
     onHeard(next.seq)
   }
   val close = {
@@ -113,7 +116,10 @@ fun MemoEditor(
     header()
     OutlinedTextField(
       field,
-      { field = it.copy(text = cutMemo(it.text)) },
+      {
+        if (it.text != field.text) heardCut = false
+        field = it.copy(text = cutMemo(it.text))
+      },
       Modifier.fillMaxWidth().weight(1f).focusRequester(focus).testTag("memoInput"),
       placeholder = { Text(placeholder) },
     )
@@ -123,6 +129,7 @@ fun MemoEditor(
       color = MaterialTheme.colorScheme.onSurfaceVariant,
       fontSize = 13.sp,
     )
+    if (heardCut) Text("入りきらなかった分は足せませんでした", color = MaterialTheme.colorScheme.error, fontSize = 14.sp, modifier = Modifier.testTag("heardCut"))
     footer()
   }
   if (discarding) {
diff --git a/app/src/main/java/com/touringproject/v2/voice/VoiceInput.kt b/app/src/main/java/com/touringproject/v2/voice/VoiceInput.kt
index 1c56b82..77e3b60 100644
--- a/app/src/main/java/com/touringproject/v2/voice/VoiceInput.kt
+++ b/app/src/main/java/com/touringproject/v2/voice/VoiceInput.kt
@@ -108,11 +108,14 @@ class VoiceInput(private val deps: VoiceDeps, private val scope: CoroutineScope)
     cancel()
   }
 
-  /** "🎤 声で入力" and the intercom button: start, or stop and send. Nothing while the text is being made. */
+  /**
+   * "🎤 声で入力" and the intercom button: start, or stop and send. While the text is being made a press starts nothing
+   * and gets the failure cue, so the rider knows it was not taken (Android #61).
+   */
   fun press(source: Source) {
     when (state.phase) {
       VoicePhase.RECORDING -> stop()
-      VoicePhase.TRANSCRIBING -> Unit
+      VoicePhase.TRANSCRIBING -> deps.cueFailure()
       VoicePhase.IDLE -> {
         // The run before is still unwinding: the press is told it was not taken.
         if (running) {
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*MemosTest' --tests '*NotesTest' --tests '*NoteScreenTest' --tests '*VoiceInputTest' --tests '*MemoScreenTest'`
Expected: PASS（全体で685件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/records/Memos.kt app/src/main/java/com/touringproject/v2/records/Notes.kt app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt app/src/main/java/com/touringproject/v2/voice/VoiceInput.kt app/src/test/java/com/touringproject/v2/records/MemosTest.kt app/src/test/java/com/touringproject/v2/records/NotesTest.kt app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt app/src/test/java/com/touringproject/v2/voice/VoiceInputTest.kt
git commit -m "fix: cue a press while SC-19 makes the text, cut a memo between emoji and tell what was heard that did not fit (#61)"
```

---

### Task 10: 通信が戻った回数を、知らせを受けたところで数える（#69）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/net/Connectivity.kt`・`sync/RideSync.kt`・`AppGraph.kt`
- Test: `net/ConnectivityTest.kt`・`sync/ReconnectionsTest.kt`

**Interfaces:**
- Produces: `Connectivity.comebacks: StateFlow<Int>`。`fun reconnections(comebacks: Flow<Int>): Flow<Unit>`（今までは `Flow<Boolean>` を受けた）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt b/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt
index d73f0db..716add7 100644
--- a/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt
+++ b/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt
@@ -5,6 +5,7 @@ import android.net.ConnectivityManager
 import android.net.NetworkCapabilities
 import androidx.test.core.app.ApplicationProvider
 import androidx.test.ext.junit.runners.AndroidJUnit4
+import org.junit.Assert.assertEquals
 import org.junit.Assert.assertFalse
 import org.junit.Assert.assertTrue
 import org.junit.Test
@@ -50,4 +51,22 @@ class ConnectivityTest {
     callback.onLost(new)
     assertFalse(connectivity.online.value)
   }
+
+  // Android #69: each comeback is counted as the system reports it, so a short drop no one saw still counts.
+  @Test
+  fun each_comeback_is_counted_where_it_is_reported() {
+    val before = shadowOf(manager).networkCallbacks.toSet()
+    val connectivity = Connectivity(app)
+    val callback = (shadowOf(manager).networkCallbacks - before).single()
+    val network = manager.activeNetwork!!
+    val caps = ShadowNetworkCapabilities.newInstance().also { shadowOf(it).addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) }
+    assertEquals(0, connectivity.comebacks.value)
+    callback.onLost(network)
+    callback.onCapabilitiesChanged(network, caps)
+    assertTrue(connectivity.online.value)
+    assertEquals(1, connectivity.comebacks.value)
+    // Capabilities reported again while online are not a comeback.
+    callback.onCapabilitiesChanged(network, caps)
+    assertEquals(1, connectivity.comebacks.value)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/sync/ReconnectionsTest.kt b/app/src/test/java/com/touringproject/v2/sync/ReconnectionsTest.kt
index 6eb6ebb..035fa40 100644
--- a/app/src/test/java/com/touringproject/v2/sync/ReconnectionsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/ReconnectionsTest.kt
@@ -1,7 +1,10 @@
 package com.touringproject.v2.sync
 
+import kotlinx.coroutines.flow.MutableStateFlow
 import kotlinx.coroutines.flow.flowOf
 import kotlinx.coroutines.flow.toList
+import kotlinx.coroutines.launch
+import kotlinx.coroutines.test.runCurrent
 import kotlinx.coroutines.test.runTest
 import org.junit.Assert.assertEquals
 import org.junit.Test
@@ -9,15 +12,31 @@ import org.junit.Test
 // Slice 4 spec §5.2: the network coming back is a trigger, so what waited for it goes without the app in front.
 class ReconnectionsTest {
   @Test
-  fun only_a_change_from_no_network_to_one_is_a_trigger() = runTest {
-    assertEquals(2, reconnections(flowOf(true, false, true, true, false, false, true)).toList().size)
+  fun each_rise_of_the_count_of_comebacks_is_a_trigger() = runTest {
+    assertEquals(2, reconnections(flowOf(0, 1, 1, 2)).toList().size)
   }
 
-  // The state the app starts in is not a change, even when it starts without a network and stays so.
+  // The count the app starts with is not a comeback, whatever it is.
   @Test
-  fun the_state_at_the_start_is_not_a_trigger() = runTest {
-    assertEquals(0, reconnections(flowOf(true)).toList().size)
-    assertEquals(0, reconnections(flowOf(false)).toList().size)
-    assertEquals(1, reconnections(flowOf(false, true)).toList().size)
+  fun the_count_at_the_start_is_not_a_trigger() = runTest {
+    assertEquals(0, reconnections(flowOf(0)).toList().size)
+    assertEquals(0, reconnections(flowOf(3)).toList().size)
+    assertEquals(1, reconnections(flowOf(3, 4)).toList().size)
+  }
+
+  // Android #69: a drop and comeback before the collector runs still triggers once; two of them are one trigger.
+  @Test
+  fun comebacks_the_collector_did_not_see_happen_still_trigger() = runTest {
+    val count = MutableStateFlow(0)
+    var triggers = 0
+    backgroundScope.launch { reconnections(count).collect { triggers += 1 } }
+    runCurrent()
+    count.value = 1
+    count.value = 2
+    runCurrent()
+    assertEquals(1, triggers)
+    count.value = 3
+    runCurrent()
+    assertEquals(2, triggers)
   }
 }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ConnectivityTest' --tests '*ReconnectionsTest'`
Expected: コンパイルで落ちる（`comebacks` が無い・`reconnections` が数を受けない）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 8701965..fb3b411 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -356,7 +356,7 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     }
     scope.launch { sync.run() }
     // The network coming back lets what waited for it go, while the process lives (slice 4 spec §5.2).
-    scope.launch { reconnections(connectivity.online).collect { sync.request() } }
+    scope.launch { reconnections(connectivity.comebacks).collect { sync.request() } }
     // SC-16: the recording ride's deadline follows the longest recording time, wherever it was changed (Android #33).
     scope.launch { maxRecordingChanges(settings.settings).collect { rides.maxRecordingChanged() } }
     scope.launch {
diff --git a/app/src/main/java/com/touringproject/v2/net/Connectivity.kt b/app/src/main/java/com/touringproject/v2/net/Connectivity.kt
index ee3da6e..e3dfc5a 100644
--- a/app/src/main/java/com/touringproject/v2/net/Connectivity.kt
+++ b/app/src/main/java/com/touringproject/v2/net/Connectivity.kt
@@ -20,23 +20,36 @@ class Connectivity(context: Context) {
   // The default network the last report was about. Losing another one (the old network, reported late after a switch
   // from Wi-Fi to mobile data) leaves the state alone (Android #62).
   @Volatile private var current: Network? = manager.activeNetwork
+  private val comebackCount = MutableStateFlow(0)
+
+  /**
+   * How many times the network has come back (from none to one) in this process. Counted where the system reports it,
+   * so a drop too short for a collector of online to see still counts (Android #69).
+   */
+  val comebacks: StateFlow<Int> = comebackCount.asStateFlow()
 
   init {
     manager.registerDefaultNetworkCallback(
       object : ConnectivityManager.NetworkCallback() {
         override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) {
           current = network
-          state.value = capabilities.reaches()
+          report(capabilities.reaches())
         }
 
         override fun onLost(network: Network) {
           if (current != null && network != current) return
           current = null
-          state.value = false
+          report(false)
         }
       },
     )
   }
+
+  @Synchronized
+  private fun report(reaches: Boolean) {
+    if (reaches && !state.value) comebackCount.value += 1
+    state.value = reaches
+  }
 }
 
 private fun NetworkCapabilities?.reaches() = this?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
diff --git a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
index fedab71..6abf2cd 100644
--- a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
@@ -20,7 +20,6 @@ import kotlinx.coroutines.flow.combine
 import kotlinx.coroutines.flow.distinctUntilChanged
 import kotlinx.coroutines.flow.drop
 import kotlinx.coroutines.flow.filter
-import kotlinx.coroutines.flow.flow
 import kotlinx.coroutines.flow.map
 import kotlinx.coroutines.sync.Mutex
 import kotlinx.coroutines.sync.withLock
@@ -320,13 +319,9 @@ fun credentialChanges(key: Flow<String?>, userName: Flow<String?>): Flow<Unit> =
     .map { }
 
 /**
- * A trigger each time the device's network comes back (slice 4 spec §5.2): a change from none to one, not the state it
- * starts in. While the process lives, what waited for the network then goes without the app coming to the front.
+ * A trigger each time the device's network comes back (slice 4 spec §5.2), from the count of comebacks
+ * (Connectivity.comebacks): any rise of it, not the count it starts at. A count conflates, so two comebacks before the
+ * collector runs are one trigger, but none is missed (Android #69). While the process lives, what waited for the
+ * network then goes without the app coming to the front.
  */
-fun reconnections(online: Flow<Boolean>): Flow<Unit> = flow {
-  var before: Boolean? = null
-  online.collect { now ->
-    if (before == false && now) emit(Unit)
-    before = now
-  }
-}
+fun reconnections(comebacks: Flow<Int>): Flow<Unit> = comebacks.distinctUntilChanged().drop(1).map { }
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ConnectivityTest' --tests '*ReconnectionsTest' --tests '*RideSyncTest'`
Expected: PASS（全体で687件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/net/Connectivity.kt app/src/main/java/com/touringproject/v2/sync/RideSync.kt app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt app/src/test/java/com/touringproject/v2/sync/ReconnectionsTest.kt
git commit -m "fix: count the network's comebacks where they are reported, so a short drop still triggers a send (#69)"
```

---

### Task 11: 自動終了の通知のテストの待ち（#59）

**Files:**
- Test: `app/src/test/java/com/touringproject/v2/service/RideForegroundServiceTest.kt`

まれにしか落ちないので、直す前に落ちることは確かめない。

- [ ] **Step 1: テストの待ちを直す**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/service/RideForegroundServiceTest.kt b/app/src/test/java/com/touringproject/v2/service/RideForegroundServiceTest.kt
index a3fc863..452a280 100644
--- a/app/src/test/java/com/touringproject/v2/service/RideForegroundServiceTest.kt
+++ b/app/src/test/java/com/touringproject/v2/service/RideForegroundServiceTest.kt
@@ -120,8 +120,12 @@ class RideForegroundServiceTest {
     // Saved before the app's own load runs, as if the process had died while recording.
     runBlocking { app.graph.rideStore.save(newRide("r1", "箱根", 0, null, 1_000)) }
     app.sendBroadcast(Intent(app, DeadlineReceiver::class.java))
-    waitUntil { app.graph.rides.active.value == null && runBlocking { app.graph.rideStore.active() } == null }
-    val posted = shadowOf(app.getSystemService(NotificationManager::class.java)).allNotifications.single()
+    // The notice comes after the ride is saved as ended, so it is waited for too (Android #59).
+    val notices = shadowOf(app.getSystemService(NotificationManager::class.java))
+    waitUntil {
+      app.graph.rides.active.value == null && runBlocking { app.graph.rideStore.active() } == null && notices.allNotifications.isNotEmpty()
+    }
+    val posted = notices.allNotifications.single()
     assertEquals("走行を自動で終了しました", shadowOf(posted).contentTitle)
   }
 
PATCH
```

- [ ] **Step 2: 続けて3回通ることを確かめる**

Run: `cd $AND && for i in 1 2 3; do ./gradlew testDebugUnitTest --rerun --tests '*RideForegroundServiceTest' | tail -1; done`
Expected: 3回とも `BUILD SUCCESSFUL`（全体で687件）

- [ ] **Step 3: コミット**

```bash
cd $AND && git add app/src/test/java/com/touringproject/v2/service/RideForegroundServiceTest.kt
git commit -m "test: wait for the auto-end notice too, so the deadline test no longer fails now and then (#59)"
```

---

### Task 12: 版と文書

**Files:**
- Modify: `app/build.gradle.kts`・`README.md`

- [ ] **Step 1: 版を 0.12.0 に上げ、README の決まりを今の作りに合わせる**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/README.md b/README.md
index 9da1ca7..f55b253 100644
--- a/README.md
+++ b/README.md
@@ -11,7 +11,7 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 | `app/src/main/java/com/touringproject/v2/ask/` | 一巡の状態機械（`Flow.kt`）・司令塔（`AskController.kt`）・外との窓口（`AskPorts.kt`）・質問の記録の組み立て（`AskRecord.kt`）・ポーリング・会話・失敗の読み上げ文 |
 | `.../api/` | Backend の API（`docs-parent/07a_openapi.yaml`）。`GET /records` で読み戻す記録の型は `Records.kt` |
 | `.../audio/` | インカムの経路・録音・再生・端末の音声・合図 |
-| `.../location/` | 質問の位置の監視（`PositionTracker.kt`）・方位の求め方（`Heading.kt`、純粋）・走行のルートの位置の頼み方と点のふるい分け（`Route.kt`） |
+| `.../location/` | 質問の位置の監視（`PositionTracker.kt`）・方位の求め方（`Heading.kt`、純粋）・走行のルートの位置の頼み方と点のふるい分け（`Route.kt`）・位置の時刻で数える今（`GpsClock.kt`）・SC-22 の方位（`HeadingCheck.kt`） |
 | `.../ride/` | 走行の型と計算（`Ride.kt`、純粋）・司令塔（`RideController.kt`）・外との窓口（`RidePorts.kt`） |
 | `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・質問のメモと削除（`RoomAskEdits.kt`）・地点メモ（`RoomNotes.kt`）・送信の置き場（`RoomSyncStore.kt`）・記録の画面の読み出しと未送信の数（`RoomRecords.kt`）・クラウドの記録を1つのトランザクションで入れる係（`RoomTakeover.kt`）。スキーマは `app/schemas/` に版ごとに残す |
 | `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋）・SC-14 の数（`Saving.kt`）・メモの決まり（`Memos.kt`、純粋）・地点メモの型と位置の選び方（`Notes.kt`、純粋）・質問と地点メモを変える窓口（`AskEdits.kt`・`NoteEdits.kt`） |
@@ -31,15 +31,17 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 - 走行の状態を変えるのは `RideController` だけ。サービス・締め切りのアラーム・電源を切る知らせ・画面は、どれもこれを呼ぶ。起動したときは `load()` が先に、残っていた走行を片付ける（端末が止まっていれば終了、締め切りを過ぎていれば自動終了、それ以外は記録の再開）。最長時間を変えたときの締め切りの計算し直しも `maxRecordingChanged()` が行う（`AppGraph` が設定の変化を受けて呼ぶ）。名前の変更は `rename()`、走行のメモは `memo()`、終えた走行の削除は `delete()`（書き直し待ちの保存も捨てるので、消した走行が書き戻されない）。
 - 質問を受けるのは走行の記録中だけ。`AskController.run` の入口で `RideNow`（記録中・一時停止中・記録していない）を見て、記録中でなければ録音を始めず、理由を読み上げる。画面の「押して話す」「文字で質問」も押せない形にする（親の spec 2 §4.7・adr/0008）。受け付けるかどうかは `refusal(RideNow)` だけが決め、司令塔とホームの文言（`askHint`）の両方がこれを使う。
 - 進行方位は端末で求めて度数（`headingDegrees`）で送る（親の adr/0013・spec 5 §4）。材料は、記録中か一時停止中の走行の最後の区間のルートの点（`RouteHeading` が Room の `segmentTail` で新しい120点を読む）。新しい点から遡り、精度が精度の上限以内で今の位置から基準の距離以上離れた最初の点から今の位置への向きにする（`findHeading`）。基準の点が保つ上限より古い・今の位置が無いか精度が悪いときは方位なし。3つのパラメーターは設定（`Settings` の `heading*`）。質問は録音を終えたときの位置、文字の質問は送るときの端末の最後の位置（30秒以内。`Positions.latest`）、地点メモは開いたときの走行の最新の点で求める。スライス5より前に作った未送信の地点メモと質問できなかった地点は、行に残る古い材料（`sample*` の列）を `headingSample` で送る（Backend の #28 で外す）。
+- 位置の時刻（`Location.time`。GNSS の時刻のことがある）は端末の時計とずれうるので、位置がどれだけ古いかは端末の時計で比べない（#17・#24）。`Fix.elapsedMs`（起動からの経過時間）を持たせ、今の位置の30秒の新しさ（`isFresh`）と、走行の区間より前の点を捨てる判定（`isSince`。区間の開始・再開・プロセスが引き継いだときの経過時間と比べる）はそれで比べる。Room の点は経過時間を持たないので、方位の保つ上限は `GpsClock`（受けた位置から、位置の時刻と経過時間の差を覚える）の今と比べる。
+- 位置と方位の確認（SC-22）は `HeadingCheck` が1秒ごとに求める。今の位置は質問の録音と同じ1秒ごとの監視の最新。走行の記録中は `RouteHeading`（質問と同じ）、記録していないとき・一時停止中は、ルートと同じ頼み方とふるい分けで画面を開いてから集めた点（メモリだけ）を材料にする。画面を離れるか、アプリが背面に回ると、監視を止めて集めた点を捨てる（記録中の走行のルートの監視は止めない）。
 - 録音の上限と開始の合図は設定（SC-11）の値を、質問の始まりに読む（SC-12 の試し録りも同じ値。SC-19 の声の入力は60秒・1.5秒のまま）。合図「なし」は 0 で、音を鳴らさない。
 - 文字の質問（ホームの「⌨ 文字で質問」のシート）は `AskController.askText` が受け、録音せずに送るところ（SC-03 の「送っています…」）から始まる。Backend が受け付けたらシートを閉じて回答待ちへ進む。通信できないとき（送る前に通信が無い・`POST` が通信の失敗）は、質問できなかった地点を作らず、シートに「通信できません」と出して文を残す。断られたとき（記録中でない・接続キー・Backend の 400 など）は SC-03 に理由を出し、シートに文を残す。シートは SC-03 のあいだ消え、終わると戻る（状態は `AppGraph.textSheet` がプロセスのあいだ持つ。画面を回して Activity が作り直されても、結果がシートに届く）。質問の行の `input` は `text`、質問の文は打った文。
 - Room のスキーマを変えるときは、版を上げて Migration を書き、`app/schemas/` に書き出された JSON もコミットする。破壊的な作り直しは使わない。スキーマの JSON は debug のビルドの資産にも入る（Robolectric の `MigrationTestHelper` が読むため。release には入らない）。Entity や Migration を変えた直後のテストは `--rerun` で確かめる。
-- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと・通信できるようになったとき（`reconnections`。プロセスが生きているあいだだけ）。契機では未送信を調べるだけで、送るものが無ければ通信しない。通信できないあいだは、契機が来ても通信を試さない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。
+- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと・通信できるようになったとき（`reconnections`。プロセスが生きているあいだだけ。`Connectivity.comebacks` が、システムの知らせを受けたところで戻った回数を数えるので、ごく短い切断も取りこぼさない）。契機では未送信を調べるだけで、送るものが無ければ通信しない。通信できないあいだは、契機が来ても通信を試さない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。
 - 1回の送信は、削除の印（`deletions`）→ 走行とルート → 地点メモ → 質問できなかった地点 → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため。質問できなかった地点のメモが、Backend で質問を見つけられるため）。記録を消すときは、同じトランザクションで削除の印を書く。送れない削除の印（知らない種類）は、ログ `sync_unsendable` に出して消す（残すと、毎回の送信がそこで止まる）。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
 - 地点メモ（SC-19）は、走行の記録中と一時停止中にホームの「📝 地点メモ」から開く。開いたときに、その走行の最後の点を位置に、質問と同じ求め方で方位を決め（`RoomNotes.draft`）、保存するまで書かない。方位は端末の値を `notes.headingDegrees` に書いて送り、住所と Backend が決めた方位は、最初に送ったときの応答で行に書く。地図のピンは緑で、質問とは別の通し番号。質問の一巡が終わったときに、その走行が消えていれば質問は書かない（`AskDao.keep`）。
 - 質問できなかった地点（US-C-09）: 録音を終えた時点で通信できないとき、または `POST /asks` が通信の失敗（試し直しのあとの 5xx・流量の制限を含む）に終わったとき、質問の一巡は日時・位置・方位を `asks` に `status = offline` で残す（識別子は端末で作る。会話の識別子は無い）。録音は `POST` の前に SC-12 へ残し（試し直しのあいだにプロセスが死んでも、受け付けられた質問の録音が残るように）、質問できなかった地点になったら消す。会話の文脈は進めない。接続キーの誤りなど、断られた失敗では残さない。書けたらすぐ送信の契機を呼ぶ（通信の失敗でも、既定のネットワークは残っていることがあるため）。`PUT /asks/{askId}/offline` で送り、応答の住所と方位を行に書く。409（同じ識別子の質問が Backend にある）は断られたものとして扱う。住所を決められずに受け付けられた地点メモと質問できなかった地点は、起動ごとに一度、版を進めて送り直す（Backend は新しい版でだけ住所を求め直す）。
 - クラウドの記録を読み込むのは、SC-18 でユーザー名を変えるときと、SC-14 の「クラウドから読み直す」だけ（親の adr/0010）。`Takeover` が `GET /records` を最後のページまで読んでから、`RoomTakeover` が1つのトランザクションで突き合わせて入れる（`Merge.kt`: `updatedAt` が新しいほうを残す・クラウドの削除の跡で消す・端末の未送信の削除はクラウドの写しを入れない・ルートは点の多いほう・記録中のまま残っていた走行は終えて入れ、送り直す）。入れたものは送り済みの印を付ける。ユーザー名を変えるときは端末の記録を消してから入れ、そのあとで名前を保存する。読み始めから名前の保存までは `RideSync.withoutPasses` の中で、送信の回が走らない。走行の記録中・一時停止中は、どちらも行わない。ユーザー名は、未送信（SC-14 が数えるもの。断られた版と記録中の走行は数えない）があるあいだも変えられない。トランザクションの中でも確かめ直す。
-- SC-19 の声の入力（`VoiceInput`）は、質問とは別の経路の切り替えと録音の部品を持つ（試し録りと同じ）。SC-19 を開いているあいだ（`attach`）は、インカムのボタンが質問を始めず、声の入力を始める・止める（質問が進んでいるときは質問のまま）。録音は60秒まで。`POST /transcriptions` に送り、質問と同じ間隔で `GET` し、120秒で打ち切る。聞き取れた文は入力欄の終わりに足す。通信できないときは画面のボタンを押せず、インカムのボタンは失敗の合図だけを鳴らす。SC-19 を離れると、録音も文字起こしの待ちも捨てる。前面サービスは使わない（SC-19 を見ながら使う前提）。
+- SC-19 の声の入力（`VoiceInput`）は、質問とは別の経路の切り替えと録音の部品を持つ（試し録りと同じ）。SC-19 を開いているあいだ（`attach`）は、インカムのボタンが質問を始めず、声の入力を始める・止める（質問が進んでいるときは質問のまま）。録音は60秒まで。`POST /transcriptions` に送り、質問と同じ間隔で `GET` し、120秒で打ち切る。聞き取れた文は入力欄の終わりに足し、2000字に入りきらなかったときは入力欄の下にそう出す。2000字で切るときは、画面の上の1文字（ZWJ でつないだ絵文字・国旗・肌の色）を割らない（`cutMemo`）。文字にしているあいだの押下は、何も始めず失敗の合図を鳴らす。通信できないときは画面のボタンを押せず、インカムのボタンは失敗の合図だけを鳴らす。SC-19 を離れると、録音も文字起こしの待ちも捨てる。前面サービスは使わない（SC-19 を見ながら使う前提）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
 - インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
 - 回答は音声の焦点（audio focus）を取らずに鳴らす（ナビの案内と重ねる）。
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index dbed6e7..b801a58 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 12
-    versionName = "0.11.0"
+    versionCode = 13
+    versionName = "0.12.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
PATCH
```

- [ ] **Step 2: 親の文書を Android に写す**

Run: `cd $ROOT && scripts/sync-docs.sh Android && git -C Android status --short docs-parent`
Expected: plan のコミットで直した `08a_android-design.md` と `mock/index.html` が写る

- [ ] **Step 3: コミット**

```bash
cd $AND && git add README.md app/build.gradle.kts docs-parent
git commit -m "chore: raise the version to 0.12.0 and describe SC-22 and the times of fixes in the README"
```

---

### Task 13: 全体の確かめ

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

Expected: `687 0`。`BUILD SUCCESSFUL`。`release permissions OK (15)`

- [ ] **Step 2: エミュレーターのテスト**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: 6件が通る

---

### Task 14: 利用者の実機の確認

走行用のビルド（版 0.12.0）を実機（Pixel 8a のメインのユーザー）に入れる。表は変えていないので、マイグレーションは走らない。

```bash
cd $AND && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

1. **SC-22 の入口と止まっているとき**: 設定の「録音の確認」のすぐ下に「位置と方位の確認」がある。走行していない状態で開くと、「方位なし」「まだ基準の距離（15m）ほど動いていません」と位置の精度が出て、出どころが「この画面を開いてから集めた位置で…」になる。
2. **SC-22 で歩く**（spec §1 の2つ目の前半。まとめの判定は plan 6）: 開いたまま20mほど歩くと方位が出て、歩く向きと「北西へ（315°）」のような16方位と度数・右手と左手が合う。立ち止まると、30秒を過ぎたころから「止まる直前の向きを保っています」が添えられ、方位は変わらない。向きを変えて歩き出すと、新しい向きになる。
3. **SC-22 のパラメーター**: 「向きを保つ上限」を2分にして2分を超えて立ち止まると、「止まってから、向きを保つ上限（2分）を超えました」になる。「既定値に戻す」で「既定値に戻しました」が出て、15m・20m・10分に戻る。
4. **SC-22 と走行**: 走行を始めると、出どころが「走行のルートから求めています。…」に変わる。一時停止すると「この画面を開いてから集めた位置で…」に戻る。画面を離れて戻ると、集めた点は捨てられて「まだ基準の距離…」から始まる。
5. **SC-05**: 記録タブの「記録」の右に「👤 ユーザー名」が出て、押すとユーザー名の画面が開き、戻ると設定の一覧になる。
6. **#61（できれば）**: 地点メモの声の入力で、文字にしているあいだ（「文字にしています…」）にインカムのボタンを押すと、失敗の合図が鳴る。

✗ が出たら `superpowers:systematic-debugging`。
