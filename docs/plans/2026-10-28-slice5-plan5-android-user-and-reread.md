# スライス5 計画5: Android（ユーザー名と読み直し） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SC-18 のユーザー名の変更と SC-14 の読み直しに残っている誤り（Android #72〜#77）を直す。名前と記録が食い違わず、止まった理由と件数が正しく出て、数える前に「保存済み」と出ないようにする。

**Architecture:** 読み込みの係（`sync/Takeover.kt`）の結果 `TakeResult.Blocked` に止まった理由（`BlockReason`）を持たせ、`TakeoverStore.take` は `TakeResult` を返す。名前の変更は、名前を先に保存し（`SettingsRepository.save` は失敗を投げる）、記録を入れられなければ元の名前に戻す。走行の書き直し待ちは `RideController.waitingToSave` で出し、SC-18 の可否と、読み込みのトランザクションの中の確かめ（`RoomTakeover` の `waitingToSave`）が使う。読み直しの件数は、走行と一緒に消える子を走行の1件として数える（`DeviceRecords.rideOf`）。Room は版6のまま（問い合わせの列を足すだけで、表は変えない）。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版6のまま）・DataStore・Robolectric 4.16（SDK 35）。足す依存は無い。

**Spec:** [docs/specs/2026-10-25-slice5-design.md](../specs/2026-10-25-slice5-design.md)（§1 の SC-05・SC-18・SC-14 の項目・§9・§13）。読み込みの作りの元は [docs/specs/2026-10-22-slice4-design.md](../specs/2026-10-22-slice4-design.md) §6・§7 と [adr/0010](../../adr/0010-read-the-cloud-only-when-taking-over.md)。

**範囲に入れた issue（Android）:** #72（名前の変更が、記録の置き換えと名前の保存を1つの成功か失敗にまとめきれていない）・#73（走行の記録中で名前の変更が止まっても「未送信の記録があるため」と出る）・#74（2回目の読み直しのあいだ、前の回の結果の文言が出たままになる）・#75（未送信の数を読む前の一瞬、「保存済み」と出て SC-18 の「変更する」も押せる）・#76（SC-18 の可否が、書き直し待ちの無い書き込みの失敗でも止まる）・#77（読み直しの件数が、走行と子の両方の削除の跡で二重に数えられる）。

**前提:** Android の `main`（`66fb270`。版 0.12.0・JVM のテスト687件）の上に作る。Backend・Agent は変えない。

**計画を書くときに決めたこと（spec からの具体化）:**

- **#72 の名前の保存の順番（利用者と決めた、2026-10-28）:** 名前（DataStore）と記録（Room）は1つのトランザクションにできないので、名前を先に保存する。
  - `SettingsRepository.save(next)` を足す。ストアに書けたときだけメモリの設定を変え、書けなければ投げる（今の `update` は失敗をログに出して握りつぶす。ほかの設定はそのまま `update` を使う）。
  - `Takeover.switchTo(peek, from, save, switched)`: 全ページを読む → `save(新しい名前)`（投げたら `Failed`、何も変わらない）→ `take`（置き換え）→ `Done` なら `switched()`（会話の文脈を切る）。`Blocked` か、`take` が投げたら `save(from)` で戻す。戻す保存も失敗したら、ログ `takeover_failed`（`op = put_back`）を出して `Failed`。食い違うのは、入れる失敗と戻す保存の失敗が重なったときだけになる。
  - 名前を保存してから戻すまでは `RideSync.withoutPasses` の中なので、送信の回は走らない（名前の変更で `credentialChanges` が頼む回は、読み込みの後に走る）。そのあいだ SC-18 の「今のユーザー名」は新しい名前を出すが、ボタンは「読み込んでいます…」で押せない。質問は記録中の走行が要り、記録中なら `take` が止めて名前を戻す。
  - `AppGraph.switchedTo(userName)` は `saveUserName(userName)`（`settings.save`）と `switched()`（`conversation.reset()`）に分ける。
- **#72 の書き直し待ち・#76:** `RideController.waitingToSave: StateFlow<Boolean>`（`unsaved != null`。`unsaved` の setter で更新）を足す。SC-18 の可否は `storeFailed` ではなくこれを見る（点の書き込みや読み出しの失敗では止めない）。`RoomTakeover(db, waitingToSave)` は、置き換え（`replace = true`）のときだけ、トランザクションの中で未送信と同じに確かめて止める（読み直しは同じ名前の記録なので止めない）。ホームの帯（`storeFailed`）の決まりは変えない（#76 の「#66 の直しが前の失敗の帯まで下ろす」は、帯の意味を変えることになり、この plan では扱わない。必要なら別の issue にする）。
- **#73:** `enum class BlockReason { RIDE, UNSENT }`・`TakeResult.Blocked(reason)`。`RoomTakeover.take` は記録中・一時停止中の走行を先に見て `RIDE`、置き換えで未送信か書き直し待ちがあれば `UNSENT`。SC-18 の文言は `RIDE` が「走行を終えてから変えられます」（SC-18 の止める文言と同じ）、`UNSENT` が今の「未送信の記録があるため、変えられませんでした」。SC-14 の読み直しは走行でしか止まらないので「走行を終えてから読み直せます」のまま。
- **#74:** `Takeover.start` は `TakeState(running = op)` から始める（前の回の `last`・`result` を残さない）。
- **#75:** `saveSummary` が null（まだ数えていない）のあいだ:
  - SC-09 の「データの保存」の行の値は空（`saveRowValue(null) == ""`）。
  - SC-14 は状態のカード（「● すべてクラウドに保存済み」か「● 未送信の記録があります」と「今すぐ保存」）を出さず、件数の「走行」「質問」の値は空。`DataUi.summary` を `SaveSummary?` にする。
  - SC-18 の「変更する」は押せず、理由の行も出さない（`UserScreen(..., counted = false)`）。
- **#77:** `DeviceRecords.rideOf`（端末の質問と地点メモの id → 走行の id）を足し、`merge` の件数は、消える質問・地点メモのうち、消える走行に属するものを数えない。`RoomTakeover` は `takeover.notes()`・`asks()` の問い合わせに `rideId` を足して埋める（表は変えない）。
- 版を 0.13.0（`versionCode` 14）に上げる。

この計画のコードは、使い捨てのフォルダで、次を確かめてから書いた。

- タスクの順に一つずつコミットし、各コミットで `clean` から JVM のテストが通る（687件 → 697件）。各タスクのテストだけを1つ前のコミットに当てると落ちる（まだ無い名前を使うのでコンパイルで落ちるか、期待が外れて落ちる）。例外は Task 8（版と文書）。
- 最後に、JVM のテスト697件・`assembleDebug`・`assembleRelease`・`scripts/check-release-permissions.sh` が通り、エミュレーターのテストのコードがコンパイルできる。
- plan の差分を新しい写しへ機械的に当てると、最終形と一致する。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice5-plan5` を切る（Task 0）。親は `slice5-plan5`。push・マージはしない（利用者が明示したときだけ）。push の前に `pre-push-secret-scan`（スキャンと push は別のコマンドにし、結果を読んでから）。
- 作りの決まり: 判断の芯（`merge`・`Takeover` の順番）は Android に依存させない。部品は `AppGraph` で手で組む。走行を変えるのは `RideController` だけ。
- Room は版6のまま（表を変えない）。破壊的な作り直しは使わない。
- ホームは全体がスクロールしない（この plan ではホームを変えない）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない（テストの作り物の名前 `rider01`・`taro01` などは除く）。端末のログ（`adb logcat`）には API の URL が出るので、書き写さない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*クラス名'`。Gradle のビルドキャッシュはフォルダをまたいで共有されるので、テストを確かめるときは `--rerun` を付ける。Kotlin の差分コンパイルは interface の変更を見逃すことがあるので、Task 9 は `./gradlew clean` から回す。
- interface・コンストラクタを変えたら、作り物にも合わせる（`TakeoverStore.take` の戻りは Task 2 の差分の中で `TakeoverTest` の作り物に、`switchTo` の引数は Task 5 の差分の中で `TakeoverTest` の `switch` に入っている）。
- Robolectric の決まり（SDK 35・画面の外の行は `performScrollTo` で出す・地図の部品は動かさない）。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。使い終わったら止める。1回目に APK を入れる途中で「device offline」で止まったら、起動し直して回す。
- この Mac はディスクの空きが少ない。Gradle のキャッシュは使うたびに増える。

## Review Focus

- 端末の空きが尽きて、ユーザー名を保存できない → 記録は変わらず「読み込めませんでした。ユーザー名は変えていません」と出て、名前も元のまま。Task 5 の `a_name_that_cannot_be_saved_changes_nothing`・`a_write_that_fails_after_the_name_puts_the_name_back`。
- DL-03 で「変更する」を押した直後に、ホームで走行を始める → 名前は元に戻り、SC-18 に「走行を終えてから変えられます」と出る。Task 2 の `nothing_changes_while_something_is_left_to_send_or_a_ride_records`・`what_a_read_came_to_is_told_on_its_screen`、Task 5 の `a_blocked_switch_puts_the_name_back`。
- 終えた走行のメモの書き込みが失敗して書き直し待ちのまま、ユーザー名を変える → SC-18 で止まり、画面を開いたあとに書き直し待ちになってもトランザクションの中で止まる。点の書き込みの失敗だけなら止まらない。Task 3 の `only_a_change_waiting_to_be_written_again_is_told_as_waiting`、Task 4 の `a_rides_change_waiting_to_be_written_keeps_the_name`。
- 設定タブ・SC-14・SC-18 を開いた直後（未送信を数える前）→ 「保存済み」と出ず、「変更する」も押せない。Task 6 の `the_name_cannot_change_before_what_is_left_is_counted`・`sc14_says_nothing_of_what_is_saved_before_it_is_counted`。
- 別の端末で質問と地点メモを消してから走行を消し、この端末で読み直す → 「1件の記録を読み込みました」。Task 7 の `what_goes_with_its_ride_is_counted_once`・`a_ride_removed_with_its_childrens_marks_counts_once`。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `sync/Takeover.kt` | 読み始めの状態（1）・`BlockReason`・`TakeResult.Blocked(reason)`（2）・名前を先に保存して戻す `switchTo`（5） | 1・2・5 |
| `store/RoomTakeover.kt` | 理由つきの結果（2）・書き直し待ちの確かめ（4）・`rideOf` を埋める（7） | 2・4・7 |
| `ui/SavingLabels.kt` | 理由ごとの文言（2）・数える前の行の値（6） | 2・6 |
| `ride/RideController.kt` | `waitingToSave` | 3 |
| `settings/SettingsRepository.kt` | 失敗を投げる `save` | 5 |
| `ui/SettingsScreens.kt` | SC-14・SC-18 の数える前 | 6 |
| `sync/Merge.kt`・`store/RideDatabase.kt` | `DeviceRecords.rideOf`・問い合わせの `rideId` | 7 |
| `ui/AppUi.kt` | SC-18 の可否（3）・`switchTo` の呼び方（5）・数える前（6） | 3・5・6 |
| `AppGraph.kt` | `RoomTakeover` に書き直し待ち（4）・`saveUserName`・`switched`（5） | 4・5 |
| `app/build.gradle.kts`・`README.md` | 版と説明 | 8 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、今のテストを回す**

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice5-plan5
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t0.log 2>&1; tail -1 /tmp/trv2-t0.log
```

Expected: `BUILD SUCCESSFUL`（687件）。親はこの plan を書いたブランチ `slice5-plan5` のまま。

---

### Task 1: 読み始めに前の回の結果を消す（#74）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/sync/Takeover.kt`
- Test: `app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt`

**Interfaces:**
- Produces: `Takeover.start` は `TakeState(running = op)` から始める（`state.value` の `last`・`result` は読み終えるまで null）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
index 58ee253..db37048 100644
--- a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
@@ -175,4 +175,18 @@ class TakeoverTest {
     c.takeover.seen()
     assertEquals(TakeState(), c.takeover.state.value)
   }
+
+  // Android #74: a second read on the same screen does not show the first one's result while it reads.
+  @Test
+  fun a_new_read_starts_without_the_last_result() = runTest {
+    val c = Cloud(this)
+    c.pages["rider01"] = mapOf(null to CloudPage(emptyList(), null))
+    c.takeover.reread("rider01")
+    runCurrent()
+    c.gate = CompletableDeferred()
+    c.takeover.reread("rider01")
+    assertEquals(TakeState(running = TakeOp.REREAD), c.takeover.state.value)
+    c.gate!!.complete(Unit)
+    runCurrent()
+  }
 }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TakeoverTest'`
Expected: FAIL（`a_new_read_starts_without_the_last_result` が `AssertionError`。前の回の結果が残っている）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
index d1b737a..90eabeb 100644
--- a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
@@ -38,7 +38,7 @@ sealed interface TakeResult {
 
 enum class TakeOp { SWITCH, REREAD }
 
-/** running is the read under way; last and result the one before, for the screen that started it to tell. */
+/** running is the read under way; last and result the one that ended, for the screen that started it to tell. */
 data class TakeState(val running: TakeOp? = null, val last: TakeOp? = null, val result: TakeResult? = null)
 
 /** The first page for a user name, read before DL-03 asks (slice 4 spec §6.4); exists picks which of its texts. */
@@ -96,7 +96,8 @@ class Takeover(
 
   private fun start(op: TakeOp, block: suspend () -> TakeResult) {
     if (stateNow.value.running != null) return
-    stateNow.value = stateNow.value.copy(running = op)
+    // The last read's result goes, so the screen does not tell it while this one reads (Android #74).
+    stateNow.value = TakeState(running = op)
     scope.launch {
       val result = try {
         sync.withoutPasses { block() }
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TakeoverTest'`
Expected: PASS（全体で688件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/sync/Takeover.kt app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
git commit -m "fix: start a read of the cloud without the last one's result, so SC-14 does not tell it while reading (#74)"
```

---

### Task 2: 止まった理由を分ける（#73）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/sync/Takeover.kt`・`store/RoomTakeover.kt`・`ui/SavingLabels.kt`
- Test: `sync/TakeoverTest.kt`・`store/RoomTakeoverTest.kt`・`ui/SavingLabelsTest.kt`

**Interfaces:**
- Produces: `enum class BlockReason { RIDE, UNSENT }`。`TakeResult.Blocked(val reason: BlockReason)`（`data object` から `data class` に）。`TakeoverStore.take(cloud, replace, now): TakeResult`（`Done` か `Blocked`。失敗は投げる）。`switchMessage(Blocked(RIDE)) == "走行を終えてから変えられます"`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
index f661f76..6019803 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
@@ -22,7 +22,9 @@ import com.touringproject.v2.ride.RoutePoint
 import com.touringproject.v2.ride.end
 import com.touringproject.v2.ride.newRide
 import com.touringproject.v2.ride.withMemo
+import com.touringproject.v2.sync.BlockReason
 import com.touringproject.v2.sync.ChunkRange
+import com.touringproject.v2.sync.TakeResult
 import com.touringproject.v2.sync.epochMs
 import kotlinx.coroutines.MainScope
 import kotlinx.coroutines.flow.first
@@ -87,7 +89,7 @@ class RoomTakeoverTest {
   // Slice 4 spec §6.1: what comes in is marked as sent, so none of it is sent back.
   @Test
   fun the_clouds_records_come_in_and_are_not_sent_back() = runBlocking {
-    assertEquals(4, takeover.take(cloud, replace = false, now = NOW))
+    assertEquals(TakeResult.Done(4), takeover.take(cloud, replace = false, now = NOW))
     assertEquals(0, records.summary.first().unsent)
     assertEquals(SaveState.SAVED, records.list.first().single().saveState)
     assertEquals(emptyList<String>(), sync.unsent().map { it.ride.id })
@@ -112,20 +114,21 @@ class RoomTakeoverTest {
   fun replacing_removes_the_devices_records_first() = runBlocking {
     sentRide("r0")
     log.save(deviceAsk("a0", "r0"))
-    assertEquals(4, takeover.take(cloud, replace = true, now = NOW))
+    assertEquals(TakeResult.Done(4), takeover.take(cloud, replace = true, now = NOW))
     assertEquals(listOf("r1"), records.list.first().map { it.ride.id })
     assertEquals(emptyList<AskRecord>(), records.asks("r0").first())
     assertEquals(2, records.summary.first().asks)
   }
 
-  // US-E-06.008: with something left to send, or a ride recording, nothing changes.
+  // US-E-06.008: with something left to send, or a ride recording, nothing changes; the ride is told first (Android #73).
   @Test
   fun nothing_changes_while_something_is_left_to_send_or_a_ride_records() = runBlocking {
     rides.save(newRide("r0", "御殿場", 1_000, 7, 24 * HOUR_MS).end(4_000, EndReason.MANUAL, 4_000))
-    assertNull(takeover.take(cloud, replace = true, now = NOW))
+    assertEquals(TakeResult.Blocked(BlockReason.UNSENT), takeover.take(cloud, replace = true, now = NOW))
     assertEquals(listOf("r0"), records.list.first().map { it.ride.id })
     rides.save(newRide("r2", "伊豆", 5_000, 7, 24 * HOUR_MS))
-    assertNull(takeover.take(cloud, replace = false, now = NOW))
+    assertEquals(TakeResult.Blocked(BlockReason.RIDE), takeover.take(cloud, replace = false, now = NOW))
+    assertEquals(TakeResult.Blocked(BlockReason.RIDE), takeover.take(cloud, replace = true, now = NOW))
     assertEquals(setOf("r0", "r2"), records.list.first().map { it.ride.id }.toSet())
   }
 
@@ -147,7 +150,7 @@ class RoomTakeoverTest {
     rides.save(kept.withMemo("端末のメモ", NOW))
     db.asks().writeMemo("a1", "端末の会話メモ", NOW)
     val again = listOf(cloudRide(), cloudRoute(), cloudAsk(memoUpdated = 1_500_000), CloudDeleted("note", "n1", "r1", iso(5_000_000)))
-    assertEquals(1, takeover.take(again, replace = false, now = NOW + 1_000))
+    assertEquals(TakeResult.Done(1), takeover.take(again, replace = false, now = NOW + 1_000))
     assertEquals("端末のメモ", records.ride("r1").first()!!.memo)
     assertEquals("端末の会話メモ", records.asks("r1").first().first { it.askId == "a1" }.memo)
     assertEquals(emptyList<Any>(), records.notes("r1").first())
diff --git a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
index db37048..6a1bc73 100644
--- a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
@@ -49,12 +49,12 @@ private class Cloud(val scope: TestScope) {
   var failOn = setOf<String?>()
   var gate: CompletableDeferred<Unit>? = null
   val taken = mutableListOf<Pair<List<CloudRecord>, Boolean>>()
-  var takes: Int? = 2
+  var takes: TakeResult = TakeResult.Done(2)
   val switched = mutableListOf<String>()
   var passes = 0
 
   val store = object : TakeoverStore {
-    override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): Int? {
+    override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): TakeResult {
       taken += cloud to replace
       return takes
     }
@@ -123,11 +123,11 @@ class TakeoverTest {
   fun a_blocked_switch_keeps_the_name() = runTest {
     val c = Cloud(this)
     c.pages["taro01"] = mapOf(null to CloudPage(emptyList(), null))
-    c.takes = null
+    c.takes = TakeResult.Blocked(BlockReason.UNSENT)
     c.takeover.switchTo(c.takeover.peek("taro01")!!) { c.switched += it }
     runCurrent()
     assertEquals(emptyList<String>(), c.switched)
-    assertEquals(TakeResult.Blocked, c.takeover.state.value.result)
+    assertEquals(TakeResult.Blocked(BlockReason.UNSENT), c.takeover.state.value.result)
   }
 
   @Test
diff --git a/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
index fe9521b..b6adc9d 100644
--- a/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
@@ -1,6 +1,7 @@
 package com.touringproject.v2.ui
 
 import com.touringproject.v2.records.SaveSummary
+import com.touringproject.v2.sync.BlockReason
 import com.touringproject.v2.sync.TakeResult
 import org.junit.Assert.assertEquals
 import org.junit.Test
@@ -39,10 +40,12 @@ class SavingLabelsTest {
   fun what_a_read_came_to_is_told_on_its_screen() {
     assertEquals("12件の記録を読み込みました", rereadMessage(TakeResult.Done(12)))
     assertEquals("新しい記録はありませんでした", rereadMessage(TakeResult.Done(0)))
-    assertEquals("走行を終えてから読み直せます", rereadMessage(TakeResult.Blocked))
+    assertEquals("走行を終えてから読み直せます", rereadMessage(TakeResult.Blocked(BlockReason.RIDE)))
     assertEquals("読み込めませんでした", rereadMessage(TakeResult.Failed))
     assertEquals("ユーザー名を変えました", switchMessage(TakeResult.Done(0)))
-    assertEquals("未送信の記録があるため、変えられませんでした", switchMessage(TakeResult.Blocked))
+    // Android #73: a ride that began after DL-03 is told as the ride, not as something left to send.
+    assertEquals("走行を終えてから変えられます", switchMessage(TakeResult.Blocked(BlockReason.RIDE)))
+    assertEquals("未送信の記録があるため、変えられませんでした", switchMessage(TakeResult.Blocked(BlockReason.UNSENT)))
     assertEquals("読み込めませんでした。ユーザー名は変えていません", switchMessage(TakeResult.Failed))
   }
 }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TakeoverTest' --tests '*RoomTakeoverTest' --tests '*SavingLabelsTest'`
Expected: コンパイルで落ちる（`BlockReason` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt b/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
index 4a005e6..af72ac3 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
@@ -4,10 +4,12 @@ import androidx.room.withTransaction
 import com.touringproject.v2.api.CloudRecord
 import com.touringproject.v2.ride.RoutePoint
 import com.touringproject.v2.ride.stepMeters
+import com.touringproject.v2.sync.BlockReason
 import com.touringproject.v2.sync.DeviceRecords
 import com.touringproject.v2.sync.KeptAsk
 import com.touringproject.v2.sync.KeptRide
 import com.touringproject.v2.sync.Merge
+import com.touringproject.v2.sync.TakeResult
 import com.touringproject.v2.sync.TakenAsk
 import com.touringproject.v2.sync.TakeoverStore
 import com.touringproject.v2.sync.merge
@@ -22,15 +24,15 @@ class RoomTakeover(private val db: RideDatabase) : TakeoverStore {
   private val rides = db.rides()
   private val asks = db.asks()
 
-  override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): Int? = db.withTransaction {
-    if (takeover.activeRides() > 0) return@withTransaction null
+  override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): TakeResult = db.withTransaction {
+    if (takeover.activeRides() > 0) return@withTransaction TakeResult.Blocked(BlockReason.RIDE)
     if (replace) {
-      if (rides.summaryNow().unsent > 0) return@withTransaction null
+      if (rides.summaryNow().unsent > 0) return@withTransaction TakeResult.Blocked(BlockReason.UNSENT)
       takeover.clearAll()
     }
     val merged = merge(device(), cloud, now)
     write(merged)
-    merged.count
+    TakeResult.Done(merged.count)
   }
 
   private suspend fun device() = DeviceRecords(
diff --git a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
index 90eabeb..7ceb662 100644
--- a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
@@ -17,11 +17,20 @@ import kotlinx.coroutines.launch
 interface TakeoverStore {
   /**
    * Merges the cloud's records into the device's (slice 4 spec §6.1) in one transaction; with replace, all the device
-   * keeps goes first (§6.4: another user name). Returns how many records came in or went, or null when nothing was done
-   * because a ride is recording or paused or, with replace, something is left to send (US-E-06.008). A failure throws
-   * and changes nothing.
+   * keeps goes first (§6.4: another user name). Returns Done with how many records came in or went, or Blocked when
+   * nothing was done because a ride is recording or paused or, with replace, something is left to send (US-E-06.008).
+   * A failure throws and changes nothing.
    */
-  suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): Int?
+  suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): TakeResult
+}
+
+/** Why a read of the cloud changed nothing (Android #73). */
+enum class BlockReason {
+  /** A ride is recording or paused. */
+  RIDE,
+
+  /** Something is left to send (a change of user name only). */
+  UNSENT,
 }
 
 /** What a read of the cloud came to. */
@@ -29,8 +38,8 @@ sealed interface TakeResult {
   /** The records are in: count came in or went. A user name changed is saved. */
   data class Done(val count: Int) : TakeResult
 
-  /** Nothing changed: a ride is recording or paused, or something is left to send. */
-  data object Blocked : TakeResult
+  /** Nothing changed, for reason. */
+  data class Blocked(val reason: BlockReason) : TakeResult
 
   /** Nothing changed: the cloud could not be read whole, or what it said could not be written. */
   data object Failed : TakeResult
@@ -84,14 +93,14 @@ class Takeover(
    */
   fun switchTo(peek: Peek, switched: suspend (userName: String) -> Unit) = start(TakeOp.SWITCH) {
     val records = readAll(peek.userName, peek.first)
-    val count = store.take(records, replace = true, now()) ?: return@start TakeResult.Blocked
-    switched(peek.userName)
-    TakeResult.Done(count)
+    val result = store.take(records, replace = true, now())
+    if (result is TakeResult.Done) switched(peek.userName)
+    result
   }
 
   /** SC-14's クラウドから読み直す: the current name's records, merged with the device's. */
   fun reread(userName: String) = start(TakeOp.REREAD) {
-    store.take(readAll(userName, null), replace = false, now())?.let { TakeResult.Done(it) } ?: TakeResult.Blocked
+    store.take(readAll(userName, null), replace = false, now())
   }
 
   private fun start(op: TakeOp, block: suspend () -> TakeResult) {
diff --git a/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt b/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
index 3938a7b..135cde6 100644
--- a/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
@@ -1,6 +1,7 @@
 package com.touringproject.v2.ui
 
 import com.touringproject.v2.records.SaveSummary
+import com.touringproject.v2.sync.BlockReason
 import com.touringproject.v2.sync.TakeResult
 import java.time.Instant
 import java.time.ZoneId
@@ -33,13 +34,17 @@ fun saveRowValue(summary: SaveSummary): String = if (summary.unsent > 0) "未送
 /** SC-14 after クラウドから読み直す. */
 fun rereadMessage(result: TakeResult): String = when (result) {
   is TakeResult.Done -> if (result.count == 0) "新しい記録はありませんでした" else "${result.count}件の記録を読み込みました"
-  TakeResult.Blocked -> "走行を終えてから読み直せます"
+  // Reading again is held back by a ride only.
+  is TakeResult.Blocked -> "走行を終えてから読み直せます"
   TakeResult.Failed -> "読み込めませんでした"
 }
 
 /** SC-18 after DL-03. */
 fun switchMessage(result: TakeResult): String = when (result) {
   is TakeResult.Done -> "ユーザー名を変えました"
-  TakeResult.Blocked -> "未送信の記録があるため、変えられませんでした"
+  is TakeResult.Blocked -> when (result.reason) {
+    BlockReason.RIDE -> "走行を終えてから変えられます"
+    BlockReason.UNSENT -> "未送信の記録があるため、変えられませんでした"
+  }
   TakeResult.Failed -> "読み込めませんでした。ユーザー名は変えていません"
 }
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TakeoverTest' --tests '*RoomTakeoverTest' --tests '*SavingLabelsTest'`
Expected: PASS（全体で688件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt app/src/main/java/com/touringproject/v2/sync/Takeover.kt app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
git commit -m "fix: tell why a read of the cloud changed nothing, so SC-18 says a ride when a ride held it back (#73)"
```

---

### Task 3: 走行の書き直し待ちを出す（#76）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ride/RideController.kt`・`ui/AppUi.kt`
- Test: `ride/RideControllerTest.kt`

**Interfaces:**
- Produces: `RideController.waitingToSave: StateFlow<Boolean>`（走行の変更が書き直し待ちのあいだ true。点の書き込みや読み出しの失敗では true にならない）。SC-18 の `UserBlock.UNSENT` は `summary.unsent > 0 || waitingToSave`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
index 0dcc479..320e9c7 100644
--- a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
@@ -380,6 +380,25 @@ class RideControllerTest {
     assertFalse(w.controller.storeFailed.value)
   }
 
+  // Android #76: only a ride's change waiting to be written again holds SC-18 back; a point that could not be written
+  // shows the band but leaves nothing waiting.
+  @Test
+  fun only_a_change_waiting_to_be_written_again_is_told_as_waiting() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.failWrites = true
+    w.controller.onFix(fix(2_000, 35.0))
+    assertTrue(w.controller.storeFailed.value)
+    assertFalse(w.controller.waitingToSave.value)
+    w.controller.pause()
+    assertTrue(w.controller.waitingToSave.value)
+    w.failWrites = false
+    w.controller.resume()
+    assertFalse(w.controller.waitingToSave.value)
+    assertFalse(w.controller.storeFailed.value)
+  }
+
   @Test
   fun the_warning_stays_while_the_ride_is_still_unsaved() = runTest {
     val w = World()
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RideControllerTest'`
Expected: コンパイルで落ちる（`waitingToSave` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ride/RideController.kt b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
index 209e9c3..e243171 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RideController.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
@@ -37,8 +37,18 @@ class RideController(private val deps: RideDeps) {
   // The time since boot when this process began to take the open segment's points (its start or resume, or load()).
   // A fix made before it is not on the segment's route, whatever the clock says (Android #17, #24).
   private var takingSince: Long? = null
+  private val waiting = MutableStateFlow(false)
+  /**
+   * True while a ride's change waits to be written again (Android #76). Unlike storeFailed, a point or a read that
+   * failed leaves nothing waiting; SC-18 holds back a change of user name only for this.
+   */
+  val waitingToSave: StateFlow<Boolean> = waiting.asStateFlow()
   // A ride whose save failed; it is written again first by every later call.
   private var unsaved: Ride? = null
+    set(value) {
+      field = value
+      waiting.value = value != null
+    }
   // False until the ride left over from before this process has been read; until then no new ride may start.
   private var reconciled = false
 
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 0697130..4fc9a74 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -345,11 +345,13 @@ fun AppUi(graph: AppGraph) {
               entry<UserKey> {
                 val summary by graph.saveSummary.collectAsStateWithLifecycle()
                 val take by graph.takeover.state.collectAsStateWithLifecycle()
+                val waitingToSave by graph.rides.waitingToSave.collectAsStateWithLifecycle()
                 DisposableEffect(Unit) { onDispose { graph.takeover.seen() } }
-                // The write checks again in its own transaction (US-E-06.008); a change still waiting to be written counts.
+                // The write checks again in its own transaction (US-E-06.008); a ride's change still waiting to be
+                // written counts (Android #76).
                 val block = when {
                   ride != null -> UserBlock.RIDE
-                  (summary?.unsent ?: 0) > 0 || storeFailed -> UserBlock.UNSENT
+                  (summary?.unsent ?: 0) > 0 || waitingToSave -> UserBlock.UNSENT
                   else -> null
                 }
                 UserScreen(
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RideControllerTest'`
Expected: PASS（全体で689件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ride/RideController.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
git commit -m "fix: hold SC-18 back only for a ride's change waiting to be written, not for any failed write (#76)"
```

---

### Task 4: 名前の変更のトランザクションで書き直し待ちを確かめる（#72）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt`・`AppGraph.kt`
- Test: `store/RoomTakeoverTest.kt`

**Interfaces:**
- Consumes: `RideController.waitingToSave`（Task 3）・`BlockReason`（Task 2）
- Produces: `RoomTakeover(db: RideDatabase, waitingToSave: () -> Boolean = { false })`。置き換えのときだけ、書き直し待ちを未送信と同じに `Blocked(UNSENT)` にする。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
index 6019803..310937c 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
@@ -132,6 +132,17 @@ class RoomTakeoverTest {
     assertEquals(setOf("r0", "r2"), records.list.first().map { it.ride.id }.toSet())
   }
 
+  // Android #72: a ride's change waiting to be written again counts as left to send, checked in the transaction, so
+  // it is not written into another name's records; reading the same name's records again is not held back by it.
+  @Test
+  fun a_rides_change_waiting_to_be_written_keeps_the_name() = runBlocking {
+    val waiting = RoomTakeover(db) { true }
+    sentRide("r0")
+    assertEquals(TakeResult.Blocked(BlockReason.UNSENT), waiting.take(cloud, replace = true, now = NOW))
+    assertEquals(listOf("r0"), records.list.first().map { it.ride.id })
+    assertEquals(TakeResult.Done(4), waiting.take(cloud, replace = false, now = NOW))
+  }
+
   // Slice 4 spec §8: a record that cannot be read fails the whole take, after the device's records were cleared.
   @Test
   fun a_failure_midway_leaves_the_device_as_it_was() = runBlocking {
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RoomTakeoverTest'`
Expected: コンパイルで落ちる（`RoomTakeover` が2つ目の引数を受けない）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index fb3b411..1bb7869 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -161,7 +161,8 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       val key = apiKeys.current()
       if (apiBaseUrl.isEmpty() || key == null) null else ApiClient(apiBaseUrl, key, user, http)
     },
-    store = RoomTakeover(database),
+    // Read at the take, long after rides below is built.
+    store = RoomTakeover(database) { rides.waitingToSave.value },
     sync = sync,
     now = System::currentTimeMillis,
     scope = scope,
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt b/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
index af72ac3..0a68cbc 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
@@ -17,9 +17,10 @@ import com.touringproject.v2.sync.merge
 /**
  * Takes the cloud's records in (slice 4 spec §6.3). The device is read, merged with the cloud and written in one
  * transaction, so a write that fails, or a cloud record that cannot be read, leaves the device as it was. What comes in
- * is marked as sent, so it is not sent back.
+ * is marked as sent, so it is not sent back. waitingToSave tells whether a ride's change waits in memory to be written
+ * again (RideController); for a change of user name it counts as left to send (Android #72).
  */
-class RoomTakeover(private val db: RideDatabase) : TakeoverStore {
+class RoomTakeover(private val db: RideDatabase, private val waitingToSave: () -> Boolean = { false }) : TakeoverStore {
   private val takeover = db.takeover()
   private val rides = db.rides()
   private val asks = db.asks()
@@ -27,7 +28,7 @@ class RoomTakeover(private val db: RideDatabase) : TakeoverStore {
   override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): TakeResult = db.withTransaction {
     if (takeover.activeRides() > 0) return@withTransaction TakeResult.Blocked(BlockReason.RIDE)
     if (replace) {
-      if (rides.summaryNow().unsent > 0) return@withTransaction TakeResult.Blocked(BlockReason.UNSENT)
+      if (rides.summaryNow().unsent > 0 || waitingToSave()) return@withTransaction TakeResult.Blocked(BlockReason.UNSENT)
       takeover.clearAll()
     }
     val merged = merge(device(), cloud, now)
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RoomTakeoverTest'`
Expected: PASS（全体で690件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
git commit -m "fix: check in the takeover's transaction for a ride's change waiting to be written before another name's records come in (#72)"
```

---

### Task 5: 名前を先に保存し、入れられなければ戻す（#72）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/settings/SettingsRepository.kt`・`sync/Takeover.kt`・`AppGraph.kt`・`ui/AppUi.kt`
- Test: `sync/TakeoverTest.kt`・`settings/SettingsTest.kt`

**Interfaces:**
- Consumes: `TakeResult.Blocked(reason)`（Task 2）
- Produces: `suspend fun SettingsRepository.save(next: Settings)`（書けなければ投げ、設定は変えない）。`Takeover.switchTo(peek: Peek, from: String, save: suspend (userName: String) -> Unit, switched: suspend () -> Unit)`。`AppGraph.saveUserName(userName: String)`・`AppGraph.switched()`（`switchedTo` は無くなる）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
index 8b8ec5d..b85d5d1 100644
--- a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
@@ -134,6 +134,23 @@ class SettingsTest {
     assertEquals(3, errors.size)
   }
 
+  // Android #72: the change of user name must know its save failed; the settings stay as they were.
+  @Test
+  fun a_save_that_cannot_be_written_throws_and_keeps_the_settings() = runTest {
+    val store = FakeStore()
+    val repo = SettingsRepository(store, Random(5))
+    val loaded = repo.load()
+    repo.save(loaded.copy(userName = "taro01"))
+    assertEquals("taro01", SettingsRepository(store).load().userName)
+    val readOnly = object : KeyValueStore {
+      override suspend fun get(key: String): String? = store.get(key)
+      override suspend fun set(key: String, value: String?) = throw java.io.IOException("disk full")
+    }
+    val stuck = SettingsRepository(readOnly).apply { load() }
+    assertTrue(runCatching { stuck.save(stuck.current().copy(userName = "hanako02")) }.isFailure)
+    assertEquals("taro01", stuck.current().userName)
+  }
+
   @Test
   fun recent_apps_keep_the_latest_five_without_duplicates() {
     val apps = (1..6).map { LaunchableApp("p$it", "A$it") }
diff --git a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
index 6a1bc73..96ad545 100644
--- a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
@@ -17,6 +17,7 @@ import org.junit.Assert.assertFalse
 import org.junit.Assert.assertNull
 import org.junit.Assert.assertTrue
 import org.junit.Test
+import java.io.IOException
 
 private fun mark(id: String) = CloudDeleted("note", id, "r1", "2026-10-22T03:00:00Z")
 
@@ -50,16 +51,29 @@ private class Cloud(val scope: TestScope) {
   var gate: CompletableDeferred<Unit>? = null
   val taken = mutableListOf<Pair<List<CloudRecord>, Boolean>>()
   var takes: TakeResult = TakeResult.Done(2)
-  val switched = mutableListOf<String>()
+  var failTake = false
+  /** The user names saved, in order; a name in failSave cannot be saved. */
+  val saved = mutableListOf<String>()
+  var failSave = setOf<String>()
+  var switched = 0
   var passes = 0
 
   val store = object : TakeoverStore {
     override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): TakeResult {
+      if (failTake) throw IOException("disk full")
       taken += cloud to replace
       return takes
     }
   }
 
+  /** SC-18's change from rider01. */
+  fun switch(peek: Peek) = takeover.switchTo(
+    peek,
+    from = "rider01",
+    save = { if (it in failSave) throw IOException("disk full") else saved += it },
+    switched = { switched += 1 },
+  )
+
   fun api(user: String) = object : RecordsApi {
     override suspend fun records(cursor: String?): CloudPage {
       reads += "$user:$cursor"
@@ -91,18 +105,20 @@ class TakeoverTest {
     assertNull(c.takeover.peek("taro01"))
   }
 
-  // Slice 4 spec §6.4: every page is read, the device's records are replaced with them, and then the name is saved.
+  // Slice 4 spec §6.4: every page is read, then the name is saved and the device's records are replaced with them
+  // (the name first: Android #72).
   @Test
-  fun a_switch_reads_every_page_then_replaces_the_records_and_saves_the_name() = runTest {
+  fun a_switch_reads_every_page_then_saves_the_name_and_replaces_the_records() = runTest {
     val c = Cloud(this)
     c.pages["taro01"] = mapOf(null to CloudPage(listOf(mark("n1")), "c2"), "c2" to CloudPage(listOf(mark("n2")), null))
     val peek = c.takeover.peek("taro01")!!
-    c.takeover.switchTo(peek) { c.switched += it }
+    c.switch(peek)
     assertEquals(TakeOp.SWITCH, c.takeover.state.value.running)
     runCurrent()
     assertEquals(listOf("taro01:null", "taro01:c2"), c.reads)
     assertEquals(listOf(listOf(mark("n1"), mark("n2")) to true), c.taken)
-    assertEquals(listOf("taro01"), c.switched)
+    assertEquals(listOf("taro01"), c.saved)
+    assertEquals(1, c.switched)
     assertEquals(TakeState(null, TakeOp.SWITCH, TakeResult.Done(2)), c.takeover.state.value)
   }
 
@@ -111,25 +127,52 @@ class TakeoverTest {
     val c = Cloud(this)
     c.pages["taro01"] = mapOf(null to CloudPage(listOf(mark("n1")), "c2"))
     c.failOn = setOf("c2")
-    c.takeover.switchTo(c.takeover.peek("taro01")!!) { c.switched += it }
+    c.switch(c.takeover.peek("taro01")!!)
     runCurrent()
     assertEquals(emptyList<Any>(), c.taken)
-    assertEquals(emptyList<String>(), c.switched)
+    assertEquals(emptyList<String>(), c.saved)
+    assertEquals(0, c.switched)
     assertEquals(TakeResult.Failed, c.takeover.state.value.result)
   }
 
-  // US-E-06.008: something left to send (found in the write's own transaction) keeps the name as it was.
+  // US-E-06.008: something left to send (found in the write's own transaction) puts the name back as it was.
   @Test
-  fun a_blocked_switch_keeps_the_name() = runTest {
+  fun a_blocked_switch_puts_the_name_back() = runTest {
     val c = Cloud(this)
     c.pages["taro01"] = mapOf(null to CloudPage(emptyList(), null))
     c.takes = TakeResult.Blocked(BlockReason.UNSENT)
-    c.takeover.switchTo(c.takeover.peek("taro01")!!) { c.switched += it }
+    c.switch(c.takeover.peek("taro01")!!)
     runCurrent()
-    assertEquals(emptyList<String>(), c.switched)
+    assertEquals(listOf("taro01", "rider01"), c.saved)
+    assertEquals(0, c.switched)
     assertEquals(TakeResult.Blocked(BlockReason.UNSENT), c.takeover.state.value.result)
   }
 
+  // Android #72: a name that cannot be saved leaves the records as they were, and so does a write that fails after it.
+  @Test
+  fun a_name_that_cannot_be_saved_changes_nothing() = runTest {
+    val c = Cloud(this)
+    c.pages["taro01"] = mapOf(null to CloudPage(emptyList(), null))
+    c.failSave = setOf("taro01")
+    c.switch(c.takeover.peek("taro01")!!)
+    runCurrent()
+    assertEquals(emptyList<Any>(), c.taken)
+    assertEquals(0, c.switched)
+    assertEquals(TakeResult.Failed, c.takeover.state.value.result)
+  }
+
+  @Test
+  fun a_write_that_fails_after_the_name_puts_the_name_back() = runTest {
+    val c = Cloud(this)
+    c.pages["taro01"] = mapOf(null to CloudPage(emptyList(), null))
+    c.failTake = true
+    c.switch(c.takeover.peek("taro01")!!)
+    runCurrent()
+    assertEquals(listOf("taro01", "rider01"), c.saved)
+    assertEquals(0, c.switched)
+    assertEquals(TakeResult.Failed, c.takeover.state.value.result)
+  }
+
   @Test
   fun a_reread_merges_the_current_names_records() = runTest {
     val c = Cloud(this)
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TakeoverTest' --tests '*SettingsTest'`
Expected: コンパイルで落ちる（`save` が無い・`switchTo` が `from` を受けない）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 1bb7869..2a85cda 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -372,12 +372,16 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     }
   }
 
+  /** A change of user name saves the name before the records come in, and throws when it cannot (Android #72). */
+  suspend fun saveUserName(userName: String) {
+    settings.save(settings.current().copy(userName = userName))
+  }
+
   /**
-   * A change of user name has read the new name's records in (slice 4 spec §6.4): the name is saved, and the
-   * conversation ends, since the Agent keeps one per user name. SC-12's recordings are the device's and stay.
+   * A change of user name has read the new name's records in (slice 4 spec §6.4): the conversation ends, since the
+   * Agent keeps one per user name. SC-12's recordings are the device's and stay.
    */
-  suspend fun switchedTo(userName: String) {
-    settings.update(settings.current().copy(userName = userName))
+  fun switched() {
     conversation.reset()
   }
 
diff --git a/app/src/main/java/com/touringproject/v2/settings/SettingsRepository.kt b/app/src/main/java/com/touringproject/v2/settings/SettingsRepository.kt
index d50ca53..3e9f2a6 100644
--- a/app/src/main/java/com/touringproject/v2/settings/SettingsRepository.kt
+++ b/app/src/main/java/com/touringproject/v2/settings/SettingsRepository.kt
@@ -59,6 +59,15 @@ class SettingsRepository(
     guard { store.set(SETTINGS_KEY, encodeSettings(next)) }
   }
 
+  /**
+   * Writes next, and only then holds it; throws when the store cannot write it, leaving the settings as they were. For
+   * the change of user name, which must not go on with a name that was not saved (Android #72).
+   */
+  suspend fun save(next: Settings) {
+    store.set(SETTINGS_KEY, encodeSettings(next))
+    state.value = next
+  }
+
   private suspend fun <T> guard(block: suspend () -> T): T? = try {
     block()
   } catch (e: CancellationException) {
diff --git a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
index 7ceb662..c08e4fc 100644
--- a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
@@ -88,14 +88,40 @@ class Takeover(
   }
 
   /**
-   * SC-18 after DL-03: the device's records go and the name's come in (§6.4), then switched saves the name; nothing
-   * changes when the read or the write fails.
+   * SC-18 after DL-03: the device's records go and the name's come in (§6.4). The name and the records cannot be
+   * written in one transaction, so the name is saved first (save throws when it cannot be) and put back to from when
+   * the records do not come in; nothing changes when the read, the name or the write fails (Android #72). No pass of
+   * the sync runs meanwhile, so nothing goes out under the new name before its records are in. switched follows a
+   * change that is done.
    */
-  fun switchTo(peek: Peek, switched: suspend (userName: String) -> Unit) = start(TakeOp.SWITCH) {
-    val records = readAll(peek.userName, peek.first)
-    val result = store.take(records, replace = true, now())
-    if (result is TakeResult.Done) switched(peek.userName)
-    result
+  fun switchTo(peek: Peek, from: String, save: suspend (userName: String) -> Unit, switched: suspend () -> Unit) =
+    start(TakeOp.SWITCH) {
+      val records = readAll(peek.userName, peek.first)
+      save(peek.userName)
+      val result = try {
+        store.take(records, replace = true, now())
+      } catch (e: Exception) {
+        putBack(from, save)
+        throw e
+      }
+      if (result !is TakeResult.Done) {
+        putBack(from, save)
+        return@start result
+      }
+      switched()
+      result
+    }
+
+  // A name that cannot be put back is logged: the records are the old name's, the saved name the new one.
+  private suspend fun putBack(from: String, save: suspend (userName: String) -> Unit) {
+    try {
+      save(from)
+    } catch (e: CancellationException) {
+      throw e
+    } catch (e: Exception) {
+      log("takeover_failed", mapOf("op" to "put_back", "error" to e.toString()))
+      throw e
+    }
   }
 
   /** SC-14's クラウドから読み直す: the current name's records, merged with the device's. */
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 4fc9a74..880ca34 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -359,7 +359,7 @@ fun AppUi(graph: AppGraph) {
                   reading = take.running != null,
                   message = take.result?.takeIf { take.last == TakeOp.SWITCH }?.let(::switchMessage),
                   peek = graph.takeover::peek,
-                  onChange = { peek -> graph.takeover.switchTo(peek, graph::switchedTo) },
+                  onChange = { peek -> graph.takeover.switchTo(peek, current.userName, graph::saveUserName, graph::switched) },
                   onData = { tabs.push(DataKey) },
                   modifier = Modifier.safeDrawingPadding(),
                 )
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TakeoverTest' --tests '*SettingsTest'`
Expected: PASS（全体で693件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/settings/SettingsRepository.kt app/src/main/java/com/touringproject/v2/sync/Takeover.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
git commit -m "fix: save the new user name before its records come in and put it back when they do not, so the two never part (#72)"
```

---

### Task 6: 未送信を数える前は保存の状態を出さない（#75）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt`・`ui/SettingsScreens.kt`・`ui/AppUi.kt`
- Test: `ui/ScreensTest.kt`・`ui/SavingLabelsTest.kt`

**Interfaces:**
- Produces: `fun saveRowValue(summary: SaveSummary?): String`（null で空）。`DataUi.summary: SaveSummary?`。`UserScreen(..., modifier, counted: Boolean = true)`（false のあいだ「変更する」を押せない）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
index b6adc9d..eda1de1 100644
--- a/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
@@ -34,6 +34,8 @@ class SavingLabelsTest {
   fun the_settings_row_tells_whether_anything_is_left() {
     assertEquals("保存済み", saveRowValue(SaveSummary(rides = 3, asks = 9)))
     assertEquals("未送信あり", saveRowValue(SaveSummary(memos = 1)))
+    // Android #75: nothing before the first count.
+    assertEquals("", saveRowValue(null))
   }
 
   @Test
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index 96798da..39dbba0 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -6,6 +6,7 @@ import androidx.compose.runtime.mutableStateOf
 import androidx.compose.runtime.setValue
 import androidx.compose.ui.test.assertHasNoClickAction
 import androidx.compose.ui.test.assertIsDisplayed
+import androidx.compose.ui.test.assertIsEnabled
 import androidx.compose.ui.test.assertIsNotEnabled
 import androidx.compose.ui.test.assertIsEnabled
 import androidx.compose.ui.test.assertTextEquals
@@ -310,6 +311,26 @@ class SettingsScreensTest {
     rule.onNodeWithTag("userMessage").assertTextEquals("ユーザー名を変えました")
   }
 
+  // Android #75: until what is left to send has been counted, the name cannot change, and nothing is said of why.
+  @Test
+  fun the_name_cannot_change_before_what_is_left_is_counted() {
+    var counted by mutableStateOf(false)
+    rule.setContent { UserScreen("rider01", null, false, null, { null }, {}, {}, counted = counted) }
+    rule.onNodeWithTag("changeUser").assertIsNotEnabled()
+    rule.onNodeWithTag("userBlock").assertDoesNotExist()
+    counted = true
+    rule.onNodeWithTag("changeUser").assertIsEnabled()
+  }
+
+  // Android #75: before the first count, SC-14 says neither saved nor left to send.
+  @Test
+  fun sc14_says_nothing_of_what_is_saved_before_it_is_counted() {
+    rule.setContent { DataScreen(data.copy(summary = null), {}, {}, {}) }
+    rule.onNodeWithTag("saveState").assertDoesNotExist()
+    rule.onNodeWithTag("saveNow").assertDoesNotExist()
+    rule.onNodeWithText("19").assertDoesNotExist()
+  }
+
   private val data = DataUi(SaveSummary(rides = 3, asks = 19), "最終保存 10:22", false, false, false, false, "rider01", null, 10)
 
   // Slice 4 spec §7.1: saved, with the last save, and the counts.
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ScreensTest' --tests '*SavingLabelsTest'`
Expected: コンパイルで落ちる（`counted` が無い・`SaveSummary` に null を渡せない）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 880ca34..780766b 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -44,7 +44,6 @@ import com.touringproject.v2.ask.isBusy
 import com.touringproject.v2.ask.rideNow
 import com.touringproject.v2.location.HeadingView
 import com.touringproject.v2.records.NoteDraft
-import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.ride.RideStatus
 import com.touringproject.v2.settings.LaunchableApp
 import com.touringproject.v2.settings.headingParams
@@ -248,7 +247,7 @@ fun AppUi(graph: AppGraph) {
                   onRecordings = { tabs.push(RecordingsKey) },
                   version = BuildConfig.VERSION_NAME,
                   modifier = Modifier.safeDrawingPadding(),
-                  saved = saveRowValue(summary ?: SaveSummary()),
+                  saved = saveRowValue(summary),
                   onData = { tabs.push(DataKey) },
                   onRecordingSettings = { tabs.push(RecordingSettingsKey) },
                   onHeadingCheck = { tabs.push(HeadingCheckKey) },
@@ -293,7 +292,7 @@ fun AppUi(graph: AppGraph) {
                 DisposableEffect(Unit) { onDispose { graph.takeover.seen() } }
                 DataScreen(
                   DataUi(
-                    summary = summary ?: SaveSummary(),
+                    summary = summary,
                     lastSaved = lastSavedLabel(lastSaved, System.currentTimeMillis(), ZoneId.systemDefault()),
                     sending = sending,
                     recording = ride?.status == RideStatus.RECORDING,
@@ -362,6 +361,7 @@ fun AppUi(graph: AppGraph) {
                   onChange = { peek -> graph.takeover.switchTo(peek, current.userName, graph::saveUserName, graph::switched) },
                   onData = { tabs.push(DataKey) },
                   modifier = Modifier.safeDrawingPadding(),
+                  counted = summary != null,
                 )
               }
               entry<ReturnAppKey> {
diff --git a/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt b/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
index 135cde6..cfe74b0 100644
--- a/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
@@ -28,8 +28,12 @@ fun lastSavedLabel(at: Long?, now: Long, zone: ZoneId): String {
   return if (saved.toLocalDate() == Instant.ofEpochMilli(now).atZone(zone).toLocalDate()) "最終保存 $time" else "最終保存 ${dayLabel(saved.toLocalDate(), weekday = false)} $time"
 }
 
-/** SC-09's データの保存 row. */
-fun saveRowValue(summary: SaveSummary): String = if (summary.unsent > 0) "未送信あり" else "保存済み"
+/** SC-09's データの保存 row; empty until what is left has been counted (Android #75). */
+fun saveRowValue(summary: SaveSummary?): String = when {
+  summary == null -> ""
+  summary.unsent > 0 -> "未送信あり"
+  else -> "保存済み"
+}
 
 /** SC-14 after クラウドから読み直す. */
 fun rereadMessage(result: TakeResult): String = when (result) {
diff --git a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
index ca1ba5f..1bfff20 100644
--- a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
@@ -116,7 +116,8 @@ fun SettingsScreen(
  * records or is paused, so reading the cloud again waits for its end. reading: a read of the cloud is under way.
  */
 data class DataUi(
-  val summary: SaveSummary,
+  /** null until what is left has been counted: nothing is said of what is saved meanwhile (Android #75). */
+  val summary: SaveSummary?,
   val lastSaved: String,
   val sending: Boolean,
   val recording: Boolean,
@@ -141,15 +142,16 @@ private fun DataRow(title: String, value: String) {
 @Composable
 fun DataScreen(ui: DataUi, onSave: () -> Unit, onUser: () -> Unit, onReread: () -> Unit, modifier: Modifier = Modifier) {
   val muted = Color(0xFF666666)
+  val summary = ui.summary
   Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
-    Surface(Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Color(0xFFCCCCCC))) {
+    if (summary != null) Surface(Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Color(0xFFCCCCCC))) {
       Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
-        if (ui.summary.unsent == 0) {
+        if (summary.unsent == 0) {
           Text("● すべてクラウドに保存済み", fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("saveState"))
           Text(ui.lastSaved, color = muted, fontSize = 14.sp)
         } else {
           Text("● 未送信の記録があります", fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("saveState"))
-          Text("${unsentBreakdown(ui.summary)}。通信できるようになると自動で送ります。", color = muted, fontSize = 14.sp, modifier = Modifier.testTag("unsentBreakdown"))
+          Text("${unsentBreakdown(summary)}。通信できるようになると自動で送ります。", color = muted, fontSize = 14.sp, modifier = Modifier.testTag("unsentBreakdown"))
           Button(onClick = onSave, enabled = !ui.sending, modifier = Modifier.fillMaxWidth().testTag("saveNow")) {
             Text(if (ui.sending) "送っています…" else "今すぐ保存", fontSize = 16.sp)
           }
@@ -175,8 +177,8 @@ fun DataScreen(ui: DataUi, onSave: () -> Unit, onUser: () -> Unit, onReread: ()
       fontSize = 14.sp,
     )
     Text("件数", fontWeight = FontWeight.Bold, fontSize = 16.sp)
-    DataRow("走行", ui.summary.rides.toString())
-    DataRow("質問", ui.summary.asks.toString())
+    DataRow("走行", summary?.rides?.toString().orEmpty())
+    DataRow("質問", summary?.asks?.toString().orEmpty())
     DataRow("端末の音声", "${ui.recordings} / $KEEP_RECORDINGS")
   }
 }
@@ -365,7 +367,8 @@ enum class UserBlock(val message: String) {
 /**
  * SC-18. peek reads the new name's first page (null when it cannot), and DL-03 tells from it whether the name has
  * records (slice 4 spec §6.4). onChange starts the change after DL-03; reading is true while a read of the cloud is under
- * way, and message is what the last change came to.
+ * way, and message is what the last change came to. counted is false until what is left to send has been counted, and
+ * the name cannot change meanwhile (Android #75).
  */
 @Composable
 fun UserScreen(
@@ -377,6 +380,7 @@ fun UserScreen(
   onChange: (Peek) -> Unit,
   onData: () -> Unit,
   modifier: Modifier = Modifier,
+  counted: Boolean = true,
 ) {
   val scope = rememberCoroutineScope()
   // Saveable, so a name being typed survives a trip to another tab (Android #34).
@@ -406,7 +410,7 @@ fun UserScreen(
           if (peeked == null) error = "読み込めませんでした" else confirming = peeked
         }
       },
-      enabled = block == null && !reading && !checking,
+      enabled = counted && block == null && !reading && !checking,
       modifier = Modifier.fillMaxWidth().testTag("changeUser"),
       colors = ButtonDefaults.buttonColors(containerColor = Blue),
     ) { Text(if (reading || checking) "読み込んでいます…" else "変更する", fontSize = 18.sp) }
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ScreensTest' --tests '*SavingLabelsTest'`
Expected: PASS（全体で695件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
git commit -m "fix: say nothing of what is saved, and keep SC-18 from changing the name, until what is left is counted (#75)"
```

---

### Task 7: 走行と一緒に消える子を1件と数える（#77）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/sync/Merge.kt`・`store/RoomTakeover.kt`・`store/RideDatabase.kt`
- Test: `sync/MergeTest.kt`・`store/RoomTakeoverTest.kt`

**Interfaces:**
- Produces: `DeviceRecords(..., rideOf: Map<String, String> = emptyMap())`（端末の質問・地点メモの id → 走行の id）。`NoteVersion(id, rideId, updatedAt)`・`AskVersion(askId, rideId, updatedAt, memoUpdatedAt)`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
index 310937c..1a65ea6 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
@@ -169,6 +169,19 @@ class RoomTakeoverTest {
     assertEquals(1, records.summary.first().memos)
   }
 
+  // Android #77: a ride removed with marks on its ask and point memo too is one record gone.
+  @Test
+  fun a_ride_removed_with_its_childrens_marks_counts_once() = runBlocking {
+    takeover.take(cloud, replace = false, now = NOW)
+    val marks = listOf(
+      CloudDeleted("ask", "a1", "r1", iso(4_000_000)),
+      CloudDeleted("note", "n1", "r1", iso(4_000_000)),
+      CloudDeleted("ride", "r1", null, iso(5_000_000)),
+    )
+    assertEquals(TakeResult.Done(1), takeover.take(marks, replace = false, now = NOW + 1_000))
+    assertEquals(emptyList<Any>(), records.list.first())
+  }
+
   @Test
   fun a_newer_memo_in_the_cloud_replaces_the_devices() = runBlocking {
     takeover.take(listOf(cloudRide(), cloudAsk()), replace = false, now = NOW)
diff --git a/app/src/test/java/com/touringproject/v2/sync/MergeTest.kt b/app/src/test/java/com/touringproject/v2/sync/MergeTest.kt
index 97793bc..e761a54 100644
--- a/app/src/test/java/com/touringproject/v2/sync/MergeTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/MergeTest.kt
@@ -113,6 +113,26 @@ class MergeTest {
     assertEquals(3, merged.count)
   }
 
+  // Android #77: an ask or point memo marked with its ride goes with the ride, and is counted once, as the ride.
+  @Test
+  fun what_goes_with_its_ride_is_counted_once() {
+    val device = DeviceRecords(
+      rides = mapOf("r1" to KeptRide(T0_MS, 3), "r2" to KeptRide(T0_MS, 0)),
+      notes = mapOf("n1" to T0_MS, "n2" to T0_MS),
+      asks = mapOf("a1" to KeptAsk(null, null)),
+      rideOf = mapOf("n1" to "r1", "a1" to "r1", "n2" to "r2"),
+    )
+    val cloud = listOf(
+      CloudDeleted("ask", "a1", "r1", iso(4_000_000)),
+      CloudDeleted("note", "n1", "r1", iso(4_000_000)),
+      CloudDeleted("ride", "r1", null, iso(5_000_000)),
+      CloudDeleted("note", "n2", "r2", iso(5_000_000)),
+    )
+    val merged = merge(device, cloud, NOW)
+    assertEquals(GoneRecords(setOf("r1"), setOf("a1"), setOf("n1", "n2")), merged.gone)
+    assertEquals(2, merged.count)
+  }
+
   // A record deleted on the device, its deletion not yet sent, stays deleted.
   @Test
   fun the_devices_own_deletions_keep_the_cloud_copy_out() {
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*MergeTest' --tests '*RoomTakeoverTest'`
Expected: コンパイルで落ちる（`rideOf` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 5ff91ec..91ff896 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -558,9 +558,9 @@ interface RideDao {
 
 data class KeptRideRow(val id: String, val updatedAt: Long, val points: Int)
 
-data class NoteVersion(val id: String, val updatedAt: Long)
+data class NoteVersion(val id: String, val rideId: String, val updatedAt: Long)
 
-data class AskVersion(val askId: String, val updatedAt: Long?, val memoUpdatedAt: Long?)
+data class AskVersion(val askId: String, val rideId: String?, val updatedAt: Long?, val memoUpdatedAt: Long?)
 
 /** Reading the cloud's records in (slice 4 spec §6.3): what the merge reads of the device, and what it writes. */
 @Dao
@@ -571,10 +571,10 @@ interface TakeoverDao {
   @Query("SELECT id, updatedAt, (SELECT COUNT(*) FROM route_points WHERE route_points.rideId = rides.id) AS points FROM rides")
   suspend fun rides(): List<KeptRideRow>
 
-  @Query("SELECT id, updatedAt FROM notes")
+  @Query("SELECT id, rideId, updatedAt FROM notes")
   suspend fun notes(): List<NoteVersion>
 
-  @Query("SELECT askId, updatedAt, memoUpdatedAt FROM asks")
+  @Query("SELECT askId, rideId, updatedAt, memoUpdatedAt FROM asks")
   suspend fun asks(): List<AskVersion>
 
   @Query("DELETE FROM route_points")
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt b/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
index 0a68cbc..5e6de02 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
@@ -36,12 +36,17 @@ class RoomTakeover(private val db: RideDatabase, private val waitingToSave: () -
     TakeResult.Done(merged.count)
   }
 
-  private suspend fun device() = DeviceRecords(
-    rides = takeover.rides().associate { it.id to KeptRide(it.updatedAt, it.points) },
-    notes = takeover.notes().associate { it.id to it.updatedAt },
-    asks = takeover.asks().associate { it.askId to KeptAsk(it.updatedAt, it.memoUpdatedAt) },
-    deletions = rides.deletions().map { it.kind to it.id }.toSet(),
-  )
+  private suspend fun device(): DeviceRecords {
+    val notes = takeover.notes()
+    val asks = takeover.asks()
+    return DeviceRecords(
+      rides = takeover.rides().associate { it.id to KeptRide(it.updatedAt, it.points) },
+      notes = notes.associate { it.id to it.updatedAt },
+      asks = asks.associate { it.askId to KeptAsk(it.updatedAt, it.memoUpdatedAt) },
+      deletions = rides.deletions().map { it.kind to it.id }.toSet(),
+      rideOf = notes.associate { it.id to it.rideId } + asks.mapNotNull { a -> a.rideId?.let { a.askId to it } },
+    )
+  }
 
   // A ride the cloud removed goes with all of it, as a deletion on the device does, but leaves no mark to send.
   private suspend fun write(merged: Merge) {
diff --git a/app/src/main/java/com/touringproject/v2/sync/Merge.kt b/app/src/main/java/com/touringproject/v2/sync/Merge.kt
index 2c31143..ab88554 100644
--- a/app/src/main/java/com/touringproject/v2/sync/Merge.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/Merge.kt
@@ -26,12 +26,16 @@ data class KeptRide(val updatedAt: Long, val points: Int)
 /** What the device keeps of an ask: an unreached ask's version (null for the Backend's own) and its memo's. */
 data class KeptAsk(val updatedAt: Long?, val memoUpdatedAt: Long?)
 
-/** The device's records by id; deletions are its own deletions not yet sent, as kind (ask / ride / note) to id. */
+/**
+ * The device's records by id; deletions are its own deletions not yet sent, as kind (ask / ride / note) to id. rideOf
+ * is the ride each kept ask and point memo belongs to.
+ */
 data class DeviceRecords(
   val rides: Map<String, KeptRide> = emptyMap(),
   val notes: Map<String, Long> = emptyMap(),
   val asks: Map<String, KeptAsk> = emptyMap(),
   val deletions: Set<Pair<String, String>> = emptySet(),
+  val rideOf: Map<String, String> = emptyMap(),
 )
 
 /** A ride's meta to write. sentUpdatedAt is the version the Backend has: behind updatedAt for a ride that ends here. */
@@ -136,7 +140,9 @@ fun merge(device: DeviceRecords, cloud: List<CloudRecord>, now: Long): Merge {
   }
 
   val gone = GoneRecords(goneRides intersect device.rides.keys, goneAsks intersect device.asks.keys, goneNotes intersect device.notes.keys)
-  val count = rides.size + notes.size + counted + gone.rides.size + gone.asks.size + gone.notes.size
+  // An ask or point memo that goes with its ride is counted as the ride (Android #77).
+  val apart = (gone.asks + gone.notes).count { device.rideOf[it] !in gone.rides }
+  val count = rides.size + notes.size + counted + gone.rides.size + apart
   return Merge(rides, routes, notes, asks, gone, count)
 }
 
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*MergeTest' --tests '*RoomTakeoverTest'`
Expected: PASS（全体で697件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt app/src/main/java/com/touringproject/v2/sync/Merge.kt app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt app/src/test/java/com/touringproject/v2/sync/MergeTest.kt
git commit -m "fix: count an ask or point memo that goes with its ride once, as the ride, when reading the cloud again (#77)"
```

---

### Task 8: 版と文書

**Files:**
- Modify: `app/build.gradle.kts`・`README.md`

- [ ] **Step 1: 版を 0.13.0 に上げ、README の読み込みの決まりを今の作りに合わせる**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/README.md b/README.md
index f55b253..012f168 100644
--- a/README.md
+++ b/README.md
@@ -40,7 +40,7 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 - 1回の送信は、削除の印（`deletions`）→ 走行とルート → 地点メモ → 質問できなかった地点 → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため。質問できなかった地点のメモが、Backend で質問を見つけられるため）。記録を消すときは、同じトランザクションで削除の印を書く。送れない削除の印（知らない種類）は、ログ `sync_unsendable` に出して消す（残すと、毎回の送信がそこで止まる）。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
 - 地点メモ（SC-19）は、走行の記録中と一時停止中にホームの「📝 地点メモ」から開く。開いたときに、その走行の最後の点を位置に、質問と同じ求め方で方位を決め（`RoomNotes.draft`）、保存するまで書かない。方位は端末の値を `notes.headingDegrees` に書いて送り、住所と Backend が決めた方位は、最初に送ったときの応答で行に書く。地図のピンは緑で、質問とは別の通し番号。質問の一巡が終わったときに、その走行が消えていれば質問は書かない（`AskDao.keep`）。
 - 質問できなかった地点（US-C-09）: 録音を終えた時点で通信できないとき、または `POST /asks` が通信の失敗（試し直しのあとの 5xx・流量の制限を含む）に終わったとき、質問の一巡は日時・位置・方位を `asks` に `status = offline` で残す（識別子は端末で作る。会話の識別子は無い）。録音は `POST` の前に SC-12 へ残し（試し直しのあいだにプロセスが死んでも、受け付けられた質問の録音が残るように）、質問できなかった地点になったら消す。会話の文脈は進めない。接続キーの誤りなど、断られた失敗では残さない。書けたらすぐ送信の契機を呼ぶ（通信の失敗でも、既定のネットワークは残っていることがあるため）。`PUT /asks/{askId}/offline` で送り、応答の住所と方位を行に書く。409（同じ識別子の質問が Backend にある）は断られたものとして扱う。住所を決められずに受け付けられた地点メモと質問できなかった地点は、起動ごとに一度、版を進めて送り直す（Backend は新しい版でだけ住所を求め直す）。
-- クラウドの記録を読み込むのは、SC-18 でユーザー名を変えるときと、SC-14 の「クラウドから読み直す」だけ（親の adr/0010）。`Takeover` が `GET /records` を最後のページまで読んでから、`RoomTakeover` が1つのトランザクションで突き合わせて入れる（`Merge.kt`: `updatedAt` が新しいほうを残す・クラウドの削除の跡で消す・端末の未送信の削除はクラウドの写しを入れない・ルートは点の多いほう・記録中のまま残っていた走行は終えて入れ、送り直す）。入れたものは送り済みの印を付ける。ユーザー名を変えるときは端末の記録を消してから入れ、そのあとで名前を保存する。読み始めから名前の保存までは `RideSync.withoutPasses` の中で、送信の回が走らない。走行の記録中・一時停止中は、どちらも行わない。ユーザー名は、未送信（SC-14 が数えるもの。断られた版と記録中の走行は数えない）があるあいだも変えられない。トランザクションの中でも確かめ直す。
+- クラウドの記録を読み込むのは、SC-18 でユーザー名を変えるときと、SC-14 の「クラウドから読み直す」だけ（親の adr/0010）。`Takeover` が `GET /records` を最後のページまで読んでから、`RoomTakeover` が1つのトランザクションで突き合わせて入れる（`Merge.kt`: `updatedAt` が新しいほうを残す・クラウドの削除の跡で消す・端末の未送信の削除はクラウドの写しを入れない・ルートは点の多いほう・記録中のまま残っていた走行は終えて入れ、送り直す）。入れたものは送り済みの印を付ける。ユーザー名を変えるときは、先に名前を保存し（保存できなければ何も変えない）、端末の記録を消してから入れる。入れられなかった（止まった・失敗した）ら名前を元に戻す（名前の保存と Room は1つのトランザクションにできないため）。読み始めから名前の保存・記録の書き込み・戻すまでは `RideSync.withoutPasses` の中で、送信の回が走らない。走行の記録中・一時停止中は、どちらも行わない。ユーザー名は、未送信（SC-14 が数えるもの。断られた版と記録中の走行は数えない）と、走行の書き直し待ち（`RideController.waitingToSave`）があるあいだも変えられない。トランザクションの中でも確かめ直す。止まった理由（走行か未送信か）は `TakeResult.Blocked` が持つ。SC-14・SC-18 は、未送信を数え終えるまで保存の状態を出さず、名前の変更を押せない。
 - SC-19 の声の入力（`VoiceInput`）は、質問とは別の経路の切り替えと録音の部品を持つ（試し録りと同じ）。SC-19 を開いているあいだ（`attach`）は、インカムのボタンが質問を始めず、声の入力を始める・止める（質問が進んでいるときは質問のまま）。録音は60秒まで。`POST /transcriptions` に送り、質問と同じ間隔で `GET` し、120秒で打ち切る。聞き取れた文は入力欄の終わりに足し、2000字に入りきらなかったときは入力欄の下にそう出す。2000字で切るときは、画面の上の1文字（ZWJ でつないだ絵文字・国旗・肌の色）を割らない（`cutMemo`）。文字にしているあいだの押下は、何も始めず失敗の合図を鳴らす。通信できないときは画面のボタンを押せず、インカムのボタンは失敗の合図だけを鳴らす。SC-19 を離れると、録音も文字起こしの待ちも捨てる。前面サービスは使わない（SC-19 を見ながら使う前提）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
 - インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index b801a58..cf2757d 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 13
-    versionName = "0.12.0"
+    versionCode = 14
+    versionName = "0.13.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
PATCH
```

- [ ] **Step 2: 親の文書を Android に写す**

Run: `cd $ROOT && scripts/sync-docs.sh Android && git -C Android status --short docs-parent`
Expected: plan のコミットで直した `08a_android-design.md` が写る

- [ ] **Step 3: コミット**

```bash
cd $AND && git add README.md app/build.gradle.kts docs-parent/08a_android-design.md
git commit -m "chore: raise the version to 0.13.0 and describe the change of user name in the README"
```

---

### Task 9: 全体の確かめ

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

Expected: `697 0`。`BUILD SUCCESSFUL`。`release permissions OK (15)`

- [ ] **Step 2: エミュレーターのテスト**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: 6件が通る

---

### Task 10: 利用者の実機の確認

走行用のビルド（版 0.13.0）を実機（Pixel 8a のメインのユーザー）に入れる。表は変えていないので、マイグレーションは走らない。

```bash
cd $AND && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

1. **SC-18 で名前を変えて戻す**（spec §1 の SC-18 の項目）: 未送信が無い状態で、SC-18 で新しい名前（記録の無い名前）に変える。DL-03 が「ユーザー名を変えますか？」で、変えると記録が空になり「ユーザー名を変えました」。元の名前に戻すと DL-03 が「既にあるユーザー名です」で、前の記録が戻る。記録タブの「👤 ユーザー名」も変わる。
2. **SC-14 の読み直し**: SC-14 で「クラウドから読み直す」を2回続けて押す。2回目の「読み込んでいます…」のあいだ、1回目の結果の文言が出ない。終わると「新しい記録はありませんでした」。
3. **開いた直後**: 設定タブ・SC-14 を開いた直後に「保存済み」がちらつかない（気づける範囲で）。
4. **走行中**: 走行を始めると、SC-18 に「走行を終えてから変えられます」が出て「変更する」が押せない（今までどおり）。

✗ が出たら `superpowers:systematic-debugging`。
