# スライス6 plan 5: 記録の持ち主と未送信の条件（R10-03・R10-02・R10-10 と R2-01・R2-02、Android #99）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 端末の記録が別のユーザー名で Backend に送られる経路を塞ぐ。そのために、Room に「記録の持ち主」を持たせ、設定の名前と食い違うあいだは送信を止めて知らせる。あわせて、「未送信」の条件と「名前の変更を止める条件」を、それぞれ1か所にまとめる。

**Architecture:** (1) Room に1行の表 `owner` を足し（スキーマ 6 → 7）、名前の変更（`RoomTakeover.take`）が記録の入れ替えと持ち主の書き換えを同じトランザクションで行う。(2) 新しい `RecordOwner` が「設定の名前 == 持ち主」を確かめ、`RideSync.pass()` の入口がそれを通らないと走らない。(3) `SettingsRepository` は、設定を読めなかった起動では何も書かず、`update` は画面の古い写しでなく「変えた項目」だけを最新の設定に重ねる。ユーザー名は `save` でしか変わらない。(4) 「未送信」の SQL を `store/Unsent.kt` の定数に集め、「止める条件」を純粋な関数 `nameChangeBlock` に集める。

**Tech Stack:** Kotlin・Room 2.x（Robolectric の `AndroidJUnit4`）・Coroutines・kotlinx-serialization（`JsonObject`）・JUnit4・kotlinx-coroutines-test。Android の `./gradlew`。

**Spec:** [docs/specs/2026-10-29-slice6-design.md](../specs/2026-10-29-slice6-design.md)（§3 の plan 5）。指摘の出どころは [全体レビュー](../final-review/2026-10-28/README.md) の structure.md（R10-02・R10-03・R10-10）と android.md（R2-01・R2-02）。決定の理由は [adr/0015](../../adr/0015-record-owner-in-room.md)。

**後回しの issue**: Android #99（未使用 import 2 つと `Entities.kt` の重複コメント。`Entities.kt` に表を足すので一緒に直して閉じる）。#101・#97・#96・#94 は plan 5 に関わらないので入れない。

## Global Constraints

- 利用者に見える文章（ツール実行の合間の報告を含む）と文書は日本語。コード・コード中のコメント・コミットメッセージは英語。コミットメッセージは Conventional Commits。
- インデントは2スペース。型注釈を付ける。秘密情報をハードコードしない。
- `git add` はファイルを個別に指定する（`git add .`・`-A` は禁止）。コミットは許可を求めずに行ってよい。push・merge・デプロイは利用者が明示したときだけ。push の前に `pre-push-secret-scan` を回して報告する。
- ブランチは Android も親も `slice6-plan5`。コマンドは必ず絶対パスへ `cd` してから実行する。
- JVM のテストは `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`（約3分）。基準値は main で 734 件。クラスを絞った実行（`--tests`）は Robolectric のテストが環境の癖で落ちることがある。タスクの区切りの確かめは `clean` から全体で行う。
- Room は壊して作り直さない。スキーマの版を上げるときは Migration を書き、`app/schemas/` に出る新しい版の JSON をコミットする。
- 画面・API（07a）・Backend・Agent は変えない。変えるのは Android だけ。
- 版は 0.14.3（`versionCode` 18）。

## Rulings（brainstorming で決めたこと）

- 持ち主と設定の名前が食い違ったら、**送信を止めて知らせる**。設定の名前を自動で書き戻さない（2026-10-30、利用者が決めた）。
- 食い違ったあとに行き止まりにならないよう、**SC-18 で持ち主の名前へ戻すときは、記録を入れ替えず、未送信があっても止めない**（クラウドの記録を足すだけ）。ほかの名前へ変えるときは、今までどおり未送信で止める。「名前を戻す」ボタンは足さない。この決めは brainstorming の「既存の SC-18 に任せる」を成り立たせるために plan を書くときに足した。
- `toRecord().sent`（行の印。版を見ない）は「次の回で送るか」とは別の意味なので、`metaToSend` と1つにしない。R10-02 の Kotlin 側は、「版を取ったか」の判定だけを1つにする。
- 既存の端末（`owner` の行が無い）は、更新後の最初の送信の回で、そのときの設定の名前を持ち主に採用する。設定を読めなかった起動では採用しない（名前が未確定のため）。
- 設定を読めなかった起動では、`update` はメモリだけを変え、書かない。利用者が SC-18 で名前を変えたとき（`save`）だけ書き、そこで確定に戻る。

## Review Focus

- 更新後の最初の起動で、`owner` の行が無い端末が、記録を失わず・送信が止まらない。Task 4 の `a_device_without_an_owner_adopts_the_name_of_the_settings`。
- 設定を読めなかった起動で、乱数の名前が保存されず、送信も走らない。Task 3 の `an_unreadable_store_is_not_written_over`、Task 5 の `an_unconfirmed_name_sends_nothing`。
- 食い違い中に SC-18 で持ち主の名前へ戻すと、未送信の記録が残り、再び送れる。Task 5 の `going_back_to_the_owner_keeps_the_records_and_the_unsent`。
- 食い違い中に第三の名前へ変えようとして未送信があると、記録を失わず止まる。Task 5 の `another_name_still_stops_on_unsent_records`。
- SC-11 の「＋」の連打のように、同じ古い写しからの2回の更新が両方残る。Task 3 の `two_changes_from_the_same_stale_copy_both_stay`。

---

## ファイルの構成

| ファイル（`Android/app/src/main/java/com/touringproject/v2/` からの相対） | 変更 |
|---|---|
| `store/Unsent.kt`（新規） | 「未送信」の SQL の定数 |
| `store/AskDao.kt`・`NoteDao.kt`・`RideDao.kt` | 定数を使う |
| `sync/SyncPlan.kt`・`records/Records.kt` | `versionTaken` を1つにする |
| `sync/NameChange.kt`（新規） | `nameChangeBlock` |
| `sync/Takeover.kt` | `BlockReason` に `WAITING`・`OWNER`、`take(…, userName)` |
| `sync/RecordOwner.kt`（新規） | `OwnerStore`・`OwnerState`・`RecordOwner` |
| `sync/RideSync.kt` | `mayPass` の門 |
| `settings/Settings.kt`・`SettingsRepository.kt` | `applyChange`・読めなかった起動・`update(from, to)` |
| `store/Entities.kt`・`TakeoverDao.kt`・`Migrations.kt`・`RideDatabase.kt` | `owner` の表・版 7 |
| `store/RoomOwner.kt`（新規）・`RoomTakeover.kt` | 持ち主の読み書き・名前の変更 |
| `ui/AppUi.kt`・`SettingsScreens.kt`・`SavingLabels.kt` | `BlockReason` の表示・食い違いの知らせ・`update(current, next)` |
| `AppGraph.kt` | `RecordOwner` を作り `RideSync` に渡す |
| `ask/AskPorts.kt`・`ui/TextAskSheet.kt` | 未使用 import（#99） |
| テスト | `UnsentAgreementTest`（新規）・`NameChangeTest`（新規）・`RecordOwnerTest`（新規）・`SettingsTest`・`MigrationTest`・`RoomTakeoverTest`・`TakeoverTest`・`RideSyncTest`・UI のテスト |
| 文書 | `Android/README.md`・`docs/08a_android-design.md`（plan のコミットで書いた）・`PROJECT.md`・`app/build.gradle.kts`（版） |

---

### Task 0: 指摘を現在のコードで確かめる

**Files:**（捨てる作業場。リポジトリには何も残さない）

spec §4: 不具合は再現テストを先に書き、失敗すれば本物。

- [ ] **Step 1: 捨てる worktree を作る**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git worktree add /private/tmp/claude-501/p5-red -b scratch-p5-red main
cp local.properties /private/tmp/claude-501/p5-red/
```

- [ ] **Step 2: R2-01 の再現テストを足す**

`/private/tmp/claude-501/p5-red/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt` に足す（import は既存のものに足りなければ補う）:

```kotlin
  // R2-01: a store that cannot be read must not be written over with a made-up name.
  @Test
  fun red_an_unreadable_store_is_not_written_over() = runTest {
    val sets = mutableListOf<String?>()
    val unreadable = object : KeyValueStore {
      override suspend fun get(key: String): String? = throw java.io.IOException("busy")
      override suspend fun set(key: String, value: String?) { sets += value }
    }
    SettingsRepository(unreadable, Random(4)) { _, _ -> }.load()
    assertEquals(emptyList<String?>(), sets)
  }

  // R10-03 (3): a change made from an old copy must not undo a newer one.
  @Test
  fun red_two_changes_from_the_same_stale_copy_both_stay() = runTest {
    val repo = SettingsRepository(FakeStore(), Random(5))
    val stale = repo.load()
    repo.update(stale.copy(answerVolumeDb = 3))
    repo.update(stale.copy(recordLimitSeconds = 45))
    assertEquals(3, repo.current().answerVolumeDb)
  }
```

- [ ] **Step 3: 回して失敗を見る**

Run: `cd /private/tmp/claude-501/p5-red && ./gradlew testDebugUnitTest --tests '*SettingsTest'`
Expected: `red_*` の2つが FAIL（`sets` に値が入る・音量が 3 でなく既定値に戻る）。落ちなければ、その指摘は誤りなので ledger に `Ruling:` を書いて、該当のタスクを縮める。

- [ ] **Step 4: R2-02 を読んで確かめる**

`sync/Takeover.kt` の `start()` が結果に関わらず `sync.request()` を呼ぶこと、`AppGraph.kt` の `backend` が `settings.settings.value?.userName` をそのまま使うこと、`RideSync.pass()` に持ち主を確かめる門が無いことを、`rg "sync.request\(\)" Android/app/src/main` と `rg "mayPass\|owner" Android/app/src/main` で確かめる（門が無ければ本物）。結果を ledger の最初に書く。

- [ ] **Step 5: worktree を消す**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git worktree remove --force /private/tmp/claude-501/p5-red
git branch -D scratch-p5-red
```

---

### Task 1: 「未送信」の SQL を1か所に集める（R10-02）

**Files:**
- Create: `store/Unsent.kt`
- Modify: `store/AskDao.kt:74-77`・`store/NoteDao.kt:70-73`・`store/RideDao.kt`（`SUMMARY`・`rows()`・`unsentRides()`）、`sync/SyncPlan.kt:44-46`、`records/Records.kt:21-26`
- Test: `app/src/test/java/com/touringproject/v2/store/UnsentAgreementTest.kt`（新規）

**Interfaces:**
- Produces: `store/Unsent.kt` の `const val` 群（下）と、`sync/SyncPlan.kt` の `fun versionTaken(sentUpdatedAt: Long?, updatedAt: Long): Boolean`。

振る舞いは変えない。既存のテストが変更なく通ることと、新しい「送る数＝数える数」のテストが通ることが完了の判定。

- [ ] **Step 1: 一致のテストを先に書く**

`app/src/test/java/com/touringproject/v2/store/UnsentAgreementTest.kt`（import は `RoomSyncStoreTest`・`RoomAskLogTest` と同じものを使う。`unreachedAsk` は `RoomAskLogTest` が使う既存のテスト用の関数）:

```kotlin
package com.touringproject.v2.store

// What the next pass sends and what SC-14 counts are the same set (08a §6); the ride recording is the one difference.
@RunWith(AndroidJUnit4::class)
class UnsentAgreementTest {
  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
    .allowMainThreadQueries()
    .build()
  private val rides = RoomRideStore(db.rides())
  private val sync = RoomSyncStore(db.rides(), db.asks(), db.notes())
  private val records = RoomRecords(db.rides(), db.asks(), db.notes())
  private val log = RoomAskLog(db.asks(), kotlinx.coroutines.MainScope()) { _, _ -> }

  @After
  fun close() = db.close()

  private fun note(id: String, updatedAt: Long, sent: Long?, rejected: Long?) = NoteEntity(
    id, "r1", 1_500, 35.0, 139.0, null, null, null, "text", updatedAt,
    sentUpdatedAt = sent, rejectedUpdatedAt = rejected, address = null, headingDegrees = null,
  )

  @Test
  fun what_the_pass_sends_is_what_sc14_counts() = runBlocking {
    val ended = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(5_000, EndReason.MANUAL, 5_000)
    rides.save(ended)
    rides.save(newRide("r2", "御殿場", 1_000, 7, 24 * HOUR_MS).end(5_000, EndReason.MANUAL, 5_000))
    rides.save(newRide("r3", "伊豆", 1_000, 7, 24 * HOUR_MS))
    sync.rideSent("r1", ended.updatedAt)
    sync.rideRefused("r2", 5_000)
    db.takeover().upsertNote(note("n1", 2_000, sent = null, rejected = null))
    db.takeover().upsertNote(note("n2", 2_000, sent = 2_000, rejected = null))
    db.takeover().upsertNote(note("n3", 2_000, sent = null, rejected = 2_000))
    log.save(unreachedAsk("u1", 2_000, null, null, "r1"))

    val summary = records.summary.first()
    assertEquals(sync.unsent().count { it.ride.status != RideStatus.RECORDING }, summary.unsentRides)
    assertEquals(sync.unsentNotes().size, summary.notes)
    assertEquals(sync.unsentUnreached().size, summary.unreached)
    assertEquals(sync.unsentAskMemos().size, summary.memos)
    assertEquals(1, summary.notes)
    assertEquals(1, summary.unreached)
  }
}
```

- [ ] **Step 2: 回して、いまの実装で通ることを見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest --tests '*UnsentAgreementTest'`
Expected: PASS（この作り替えの前から一致している。このテストは、まとめたあとに離れないための固定）。

- [ ] **Step 3: 定数を置く**

`store/Unsent.kt`:

```kotlin
package com.touringproject.v2.store

// The one place that says what is "not sent yet" in SQL (08a §6, slice 6 plan 5). The columns are the unprefixed ones of
// the table a query reads, so a correlated subquery finds its own table's first.

/** The version in the row has not been taken by the Backend. */
internal const val VERSION_NOT_TAKEN = "(sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt)"

/** The Backend did not refuse this very version (a refused one is never sent again). */
internal const val VERSION_NOT_REFUSED = "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt)"

/** What the next pass sends and what SC-14 counts: not taken, and not refused. */
internal const val UNSENT = "$VERSION_NOT_TAKEN AND $VERSION_NOT_REFUSED"

/** An ask that never reached the Backend and is not sent yet (slice 4 spec §5.1). */
internal const val UNREACHED_UNSENT = "status = 'offline' AND $UNSENT"

/** An ask's memo that is not sent yet. */
internal const val MEMO_UNSENT =
  "memoUpdatedAt IS NOT NULL AND (memoSentUpdatedAt IS NULL OR memoSentUpdatedAt < memoUpdatedAt) AND " +
    "(memoRejectedUpdatedAt IS NULL OR memoRejectedUpdatedAt != memoUpdatedAt)"

/** A ride's route points waiting for a chunk to go. */
internal const val POINTS_UNSENT = "EXISTS (SELECT 1 FROM route_points WHERE chunk IS NULL AND route_points.rideId = rides.id)"

// SC-05's list marks are a different question, "is something of it not taken": a refused version counts there, since the
// rider has not got it saved (slice 2 spec §5.4). They use VERSION_NOT_TAKEN alone, under names that say so.
internal const val NOTE_LEFT = VERSION_NOT_TAKEN
internal const val UNREACHED_LEFT = "status = 'offline' AND $VERSION_NOT_TAKEN"
internal const val MEMO_LEFT = "memoUpdatedAt IS NOT NULL AND (memoSentUpdatedAt IS NULL OR memoSentUpdatedAt < memoUpdatedAt)"
```

- [ ] **Step 4: DAO の問い合わせを定数に置き換える**

`AskDao.kt`（`unsentUnreached`）:

```kotlin
  @Query("SELECT * FROM asks WHERE $UNREACHED_UNSENT ORDER BY updatedAt")
  suspend fun unsentUnreached(): List<AskEntity>
```

`NoteDao.kt`（`unsent`）:

```kotlin
  @Query("SELECT * FROM notes WHERE $UNSENT ORDER BY updatedAt")
  suspend fun unsent(): List<NoteEntity>
```

`AskDao.kt` の `unsentMemos` の問い合わせも、いまの `memoUpdatedAt IS NOT NULL AND …` の本文を `$MEMO_UNSENT` に置き換える（本文を読み、条件が `MEMO_UNSENT` と同じことを確かめてから）。

`RideDao.kt`:

```kotlin
private const val SUMMARY = "SELECT (SELECT COUNT(*) FROM asks WHERE $UNREACHED_UNSENT) AS unreached, " +
  "(SELECT COUNT(*) FROM rides WHERE status != 'recording' AND ($UNSENT OR $POINTS_UNSENT)) AS unsentRides, " +
  "(SELECT COUNT(*) FROM notes WHERE $UNSENT) AS notes, " +
  "(SELECT COUNT(*) FROM asks WHERE $MEMO_UNSENT) AS memos, " +
  "(SELECT COUNT(*) FROM deletions) AS deletions, (SELECT COUNT(*) FROM rides) AS rides, (SELECT COUNT(*) FROM asks) AS asks"
```

`rows()` の `memosLeft`・`notesLeft`・`unreachedLeft` を、prefix を外した定数に:

```kotlin
      "EXISTS (SELECT 1 FROM asks WHERE asks.rideId = rides.id AND $MEMO_LEFT) AS memosLeft, " +
      "EXISTS (SELECT 1 FROM notes WHERE notes.rideId = rides.id AND $NOTE_LEFT) AS notesLeft, " +
      "EXISTS (SELECT 1 FROM asks WHERE asks.rideId = rides.id AND $UNREACHED_LEFT) AS unreachedLeft FROM rides",
```

`unsentRides()`:

```kotlin
    "SELECT * FROM rides WHERE ($UNSENT) " +
      "OR id IN (SELECT rideId FROM route_points WHERE chunk IS NULL) ORDER BY updatedAt",
```

Room の `@Query` は `const val` の文字列テンプレートを受ける。コンパイルで通らなければ `+` で連結する形にする。

- [ ] **Step 5: Kotlin 側の「版を取ったか」を1つにする**

`sync/SyncPlan.kt`:

```kotlin
/** The Backend has taken this version of the row (or a newer one). */
fun versionTaken(sentUpdatedAt: Long?, updatedAt: Long): Boolean = sentUpdatedAt != null && sentUpdatedAt >= updatedAt

/** The ride's meta goes when it has changed since the Backend last took it, unless the Backend refused this very version. */
fun metaToSend(updatedAt: Long, sentUpdatedAt: Long?, rejectedUpdatedAt: Long?): Boolean =
  !versionTaken(sentUpdatedAt, updatedAt) && rejectedUpdatedAt != updatedAt
```

`records/Records.kt` の `saveState`:

```kotlin
  pointsLeft || !versionTaken(sentUpdatedAt, updatedAt) -> SaveState.UNSENT
```
（`import com.touringproject.v2.sync.versionTaken` を足す。`records` から `sync` への依存が既にあるかを確かめ、無ければ `versionTaken` を `records/Records.kt` に置いて `SyncPlan.kt` が読む形にする。どちらでも依存の向きが循環しないほうにする。）

- [ ] **Step 6: 全体を回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`
Expected: 735 件が PASS（734 + 新しい1件）。既存のテストを1行も変えていないこと。

- [ ] **Step 7: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/store/Unsent.kt app/src/main/java/com/touringproject/v2/store/AskDao.kt app/src/main/java/com/touringproject/v2/store/NoteDao.kt app/src/main/java/com/touringproject/v2/store/RideDao.kt app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt app/src/main/java/com/touringproject/v2/records/Records.kt app/src/test/java/com/touringproject/v2/store/UnsentAgreementTest.kt
git commit -m "refactor: keep the SQL for what is not sent yet in one place (R10-02)"
```

---

### Task 2: 名前の変更を止める条件を1つの関数にする（R10-10）

**Files:**
- Create: `sync/NameChange.kt`
- Modify: `sync/Takeover.kt:37-44`（`BlockReason`）、`store/RoomTakeover.kt:27-36`、`ui/AppUi.kt:348-358`、`ui/SettingsScreens.kt:361-368`（`UserBlock` を消す）、`ui/SavingLabels.kt`
- Test: `app/src/test/java/com/touringproject/v2/sync/NameChangeTest.kt`（新規）、`RoomTakeoverTest`・UI のテスト（`UserBlock` を使うもの）

**Interfaces:**
- Produces: `fun nameChangeBlock(rideActive: Boolean, unsent: Int, waitingToSave: Boolean): BlockReason?`。`BlockReason` は `RIDE`・`UNSENT`・`WAITING`・`OWNER`（`OWNER` は Task 5 が使う）。`fun blockMessage(reason: BlockReason): String`（`ui/SavingLabels.kt`）。

- [ ] **Step 1: 表のテストを書く**

`sync/NameChangeTest.kt`:

```kotlin
package com.touringproject.v2.sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NameChangeTest {
  @Test
  fun a_ride_stops_it_before_anything_else() {
    assertEquals(BlockReason.RIDE, nameChangeBlock(rideActive = true, unsent = 3, waitingToSave = true))
  }

  @Test
  fun what_is_left_to_send_stops_it_before_a_save_waiting() {
    assertEquals(BlockReason.UNSENT, nameChangeBlock(rideActive = false, unsent = 1, waitingToSave = true))
  }

  @Test
  fun a_save_waiting_stops_it_alone() {
    assertEquals(BlockReason.WAITING, nameChangeBlock(rideActive = false, unsent = 0, waitingToSave = true))
  }

  @Test
  fun nothing_in_the_way_lets_it_go() {
    assertNull(nameChangeBlock(rideActive = false, unsent = 0, waitingToSave = false))
  }
}
```

- [ ] **Step 2: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest --tests '*NameChangeTest'`
Expected: コンパイルエラー（`nameChangeBlock` が無い）。

- [ ] **Step 3: 関数と理由を足す**

`sync/NameChange.kt`:

```kotlin
package com.touringproject.v2.sync

/**
 * What stops the user name from changing now, in the order the rider is told (08a §6, US-E-06.008); null when nothing
 * does. The screen and the write inside RoomTakeover's transaction both ask here, so they never part.
 */
fun nameChangeBlock(rideActive: Boolean, unsent: Int, waitingToSave: Boolean): BlockReason? = when {
  rideActive -> BlockReason.RIDE
  unsent > 0 -> BlockReason.UNSENT
  waitingToSave -> BlockReason.WAITING
  else -> null
}
```

`sync/Takeover.kt` の `BlockReason`:

```kotlin
enum class BlockReason {
  /** A ride is recording or paused. */
  RIDE,

  /** Something is left to send (a change of user name only). */
  UNSENT,

  /** A ride's change waits to be written to the device (RideController.waitingToSave); sending does not help. */
  WAITING,

  /** The records are another user name's than the one asked for (a read again only; slice 6 plan 5). */
  OWNER,
}
```

- [ ] **Step 4: トランザクションと画面が関数を呼ぶ**

`store/RoomTakeover.kt` の `take` の中（`replace` の分岐）:

```kotlin
    if (replace) {
      nameChangeBlock(rideActive = false, unsent = rides.summaryNow().unsent, waitingToSave = waitingToSave())
        ?.let { return@withTransaction TakeResult.Blocked(it) }
      takeover.clearAll()
    }
```
（走行の確かめは直前の `activeRides()` のまま。`import com.touringproject.v2.sync.nameChangeBlock` を足す。）

`ui/AppUi.kt` の `val block = when {…}` を:

```kotlin
                val block = nameChangeBlock(ride != null, summary?.unsent ?: 0, waitingToSave)
```

`ui/SettingsScreens.kt` の `enum class UserBlock` を消し、`UserScreen` の `block: UserBlock?` を `block: BlockReason?` に、`if (block == UserBlock.UNSENT)` を `if (block == BlockReason.UNSENT)` に、`Text(it.message …)` を `Text(blockMessage(it) …)` にする。

`ui/SavingLabels.kt`:

```kotlin
/** Why the user name cannot change now (SC-18, US-E-06.008). */
fun blockMessage(reason: BlockReason): String = when (reason) {
  BlockReason.RIDE -> "走行を終えてから変えられます"
  BlockReason.UNSENT -> "未送信の記録があります。先に「データの保存」で送ってください"
  BlockReason.WAITING -> "走行の変更を端末に書き込めていません。端末の空き容量を確かめてください"
  BlockReason.OWNER -> "ユーザー名と端末の記録が合っていません。ユーザー名の変更から直してください"
}
```

`switchMessage` の `is TakeResult.Blocked` の中は、`BlockReason.RIDE` と `UNSENT` に加えて:

```kotlin
    BlockReason.WAITING -> "走行の変更を端末に書き込めていないため、変えられませんでした"
    BlockReason.OWNER -> "変えられませんでした"
```
`rereadMessage` の `is TakeResult.Blocked` は理由で分ける:

```kotlin
  is TakeResult.Blocked -> when (result.reason) {
    BlockReason.OWNER -> "ユーザー名と端末の記録が合っていません。ユーザー名の変更から直してください"
    else -> "走行を終えてから読み直せます"
  }
```
`UserBlock` を参照している既存のテスト（`rg "UserBlock" Android/app/src`）を `BlockReason` に直す。`RoomTakeoverTest` の「書き直し待ちの走行があると名前の変更が止まる」（`waiting.take(cloud, replace = true…)`）の期待値を `BlockReason.UNSENT` から `BlockReason.WAITING` に直す（止める理由を正確に分けたため）。

- [ ] **Step 5: 全体を回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`
Expected: 739 件が PASS。

- [ ] **Step 6: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/sync/NameChange.kt app/src/main/java/com/touringproject/v2/sync/Takeover.kt app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt app/src/test/java/com/touringproject/v2/sync/NameChangeTest.kt
git add -u app/src/test
git commit -m "refactor: decide what stops a change of user name in one function (R10-10)"
```
（`git add -u app/src/test` は、このタスクで直したテストだけが変わっているときに限る。他の変更が混ざるなら個別に指定する。）

---

### Task 3: 設定を読めなかった起動と、設定の更新（R2-01・R10-03 の(3)）

**Files:**
- Modify: `settings/Settings.kt`（`applyChange` を足す）、`settings/SettingsRepository.kt`、`ui/AppUi.kt`（7 か所）
- Test: `app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt`

**Interfaces:**
- Produces: `fun applyChange(from: Settings, to: Settings, latest: Settings): Settings`、`SettingsRepository.nameConfirmed: Boolean`、`suspend fun SettingsRepository.update(from: Settings, to: Settings)`（古い `update(next)` は消す）。

- [ ] **Step 1: 失敗するテストを書く**

`SettingsTest.kt` の `a_store_that_cannot_be_read_falls_back_to_defaults`（`errors.size == 3`）は、読めなかったときに書かない決まりに合わせて直し、新しいテストを足す:

```kotlin
  @Test
  fun a_store_that_cannot_be_read_falls_back_to_defaults() = runTest {
    val broken = object : KeyValueStore {
      override suspend fun get(key: String): String? = throw java.io.IOException("corrupt")
      override suspend fun set(key: String, value: String?) = throw java.io.IOException("read-only")
    }
    val errors = mutableListOf<String>()
    val repo = SettingsRepository(broken, Random(4)) { message, _ -> errors += message }
    val loaded = repo.load()
    assertEquals(Settings(userName = loaded.userName), loaded)
    val stale = repo.current()
    repo.update(stale, stale.copy(returnEnabled = false))
    assertFalse(repo.current().returnEnabled)
    assertEquals(1, errors.size)
  }

  // R2-01: a store that cannot be read is not written over with a made-up name.
  @Test
  fun an_unreadable_store_is_not_written_over() = runTest {
    val sets = mutableListOf<String?>()
    val unreadable = object : KeyValueStore {
      override suspend fun get(key: String): String? = throw java.io.IOException("busy")
      override suspend fun set(key: String, value: String?) { sets += value }
    }
    val repo = SettingsRepository(unreadable, Random(4)) { _, _ -> }
    val loaded = repo.load()
    repo.update(loaded, loaded.copy(showAskPins = false))
    assertEquals(emptyList<String?>(), sets)
    assertFalse(repo.nameConfirmed)
  }

  // The rider choosing a name is the one write that goes through, and it confirms the name.
  @Test
  fun saving_a_name_writes_an_unreadable_store_and_confirms_it() = runTest {
    val sets = mutableListOf<String?>()
    val unreadable = object : KeyValueStore {
      override suspend fun get(key: String): String? = throw java.io.IOException("busy")
      override suspend fun set(key: String, value: String?) { sets += value }
    }
    val repo = SettingsRepository(unreadable, Random(4)) { _, _ -> }
    repo.save(repo.load().copy(userName = "taro01"))
    assertEquals(1, sets.size)
    assertTrue(repo.nameConfirmed)
  }

  // A store with nothing in it is a first launch: the made-up name is kept, and the name is the rider's.
  @Test
  fun an_empty_store_is_a_first_launch_with_a_confirmed_name() = runTest {
    val store = FakeStore()
    val repo = SettingsRepository(store, Random(4))
    val loaded = repo.load()
    assertTrue(repo.nameConfirmed)
    assertEquals(loaded.userName, SettingsRepository(store).load().userName)
  }

  // R10-03 (3): a change made from an old copy must not undo a newer one, and the name is not changed by it.
  @Test
  fun two_changes_from_the_same_stale_copy_both_stay() = runTest {
    val repo = SettingsRepository(FakeStore(), Random(5))
    val stale = repo.load()
    repo.update(stale, stale.copy(answerVolumeDb = 3))
    repo.update(stale, stale.copy(recordLimitSeconds = 45))
    assertEquals(3, repo.current().answerVolumeDb)
    assertEquals(45, repo.current().recordLimitSeconds)
  }

  @Test
  fun a_change_from_an_old_copy_does_not_put_the_old_name_back() = runTest {
    val repo = SettingsRepository(FakeStore(), Random(5))
    val stale = repo.load()
    repo.save(stale.copy(userName = "taro01"))
    repo.update(stale, stale.copy(showAskPins = false))
    assertEquals("taro01", repo.current().userName)
    assertFalse(repo.current().showAskPins)
  }

  @Test
  fun a_change_cannot_carry_a_new_name() = runTest {
    val repo = SettingsRepository(FakeStore(), Random(5))
    val stale = repo.load()
    repo.update(stale, stale.copy(userName = "other99", showNotePins = false))
    assertEquals(stale.userName, repo.current().userName)
    assertFalse(repo.current().showNotePins)
  }
```
（`FakeStore` は同じファイルに既にある。無ければ `mutableMapOf` を包む `KeyValueStore` を同じファイルに足す。）

- [ ] **Step 2: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest --tests '*SettingsTest'`
Expected: コンパイルエラー（`update(from, to)`・`nameConfirmed` が無い）。

- [ ] **Step 3: 最小の実装**

`settings/Settings.kt` に足す（`kotlinx.serialization.json` の `buildJsonObject`・`put` を import）:

```kotlin
/**
 * The fields to changed from from, laid onto latest: a screen holds a copy that may be old, so what it did not touch
 * is the newest value, not the copy's. The user name is always latest's: it changes through the repository's save only
 * (slice 6 plan 5, R10-03).
 */
fun applyChange(from: Settings, to: Settings, latest: Settings): Settings {
  fun fields(s: Settings): JsonObject = json.parseToJsonElement(encodeSettings(s)).jsonObject
  val before = fields(from)
  val after = fields(to)
  val merged = buildJsonObject {
    for ((key, value) in fields(latest)) {
      put(key, if (key != "userName" && after[key] != before[key]) after.getValue(key) else value)
    }
  }
  return decodeSettings(merged.toString()).first
}
```

`settings/SettingsRepository.kt`:

```kotlin
  private val state = MutableStateFlow<Settings?>(null)
  val settings: StateFlow<Settings?> = state.asStateFlow()
  private val writes = Mutex()

  // True when the saved settings could not be read: the name in memory is made up for this run, and nothing is written.
  private var unreadable = false

  /** False while the user name is made up because the settings could not be read; true once it is the rider's. */
  val nameConfirmed: Boolean get() = !unreadable

  /**
   * A store that cannot be read leaves the app on its defaults for this run and writes nothing, so the name and the
   * settings it holds are not written over (R2-01). A store with nothing in it is a first launch and is written.
   */
  suspend fun load(): Settings {
    val raw = try {
      store.get(SETTINGS_KEY).also { unreadable = false }
    } catch (e: CancellationException) {
      throw e
    } catch (e: Exception) {
      logError("settings store failed", e)
      unreadable = true
      null
    }
    val (loaded, needsSave) = decodeSettings(raw, random)
    if (needsSave && !unreadable) guard { store.set(SETTINGS_KEY, encodeSettings(loaded)) }
    state.value = loaded
    return loaded
  }

  fun current(): Settings = checkNotNull(state.value) { "settings not loaded" }

  /**
   * Lays what to changed from from onto the newest settings and keeps it (applyChange); nothing is written while the
   * settings could not be read.
   */
  suspend fun update(from: Settings, to: Settings) = writes.withLock {
    val next = applyChange(from, to, current())
    state.value = next
    if (!unreadable) guard { store.set(SETTINGS_KEY, encodeSettings(next)) }
  }

  /**
   * Writes next, and only then holds it; throws when the store cannot write it, leaving the settings as they were. For
   * the change of user name, which must not go on with a name that was not saved (Android #72). The rider's own choice
   * of a name makes it confirmed.
   */
  suspend fun save(next: Settings) = writes.withLock {
    store.set(SETTINGS_KEY, encodeSettings(next))
    state.value = next
    unreadable = false
  }
```
（`import kotlinx.coroutines.sync.Mutex`・`withLock` を足す。`guard` は残す。）

`ui/AppUi.kt` の `graph.settings.update(next)` 6 か所（207・268・279・314・317・374 行）は `graph.settings.update(current, next)`、`graph.settings.update(current.withHeadingDefaults())` は `graph.settings.update(current, current.withHeadingDefaults())`、`withRecordingDefaults` も同じ形にする（`rg "settings.update" Android/app/src` で全部を拾う。`current` はその entry で使っている画面の写しのまま）。

既存の `SettingsTest.kt` の2本（`saved_settings_round_trip`・`recording_and_heading_values_round_trip_and_odd_ones_fall_back`）は、読み込む前の `SettingsRepository` に `update(s)` を呼んで丸ごと書いている。`update` は最新の設定に重ねる形になり、読み込み前は使えないので、この2本の `update(s)` は `save(s)` に直す（丸ごと書く点は同じ）。

- [ ] **Step 4: 全体を回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`
Expected: 全件 PASS（739 + 新しい 6 件前後）。

- [ ] **Step 5: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/settings/Settings.kt app/src/main/java/com/touringproject/v2/settings/SettingsRepository.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
git commit -m "fix: do not write over settings that could not be read, and lay a change onto the newest settings (R2-01, R10-03)"
```

---

### Task 4: Room に記録の持ち主を持たせる（スキーマ 6 → 7）

**Files:**
- Modify: `store/Entities.kt`（`OwnerEntity`。先頭のコメントを「Room の表」を述べる1行にする。#99）、`store/TakeoverDao.kt`、`store/Migrations.kt`、`store/RideDatabase.kt`
- Create: `store/RoomOwner.kt`、`app/schemas/<パッケージ>/RideDatabase/7.json`（ビルドが出す）
- Test: `MigrationTest.kt`・`RoomOwnerTest.kt`（新規）

**Interfaces:**
- Produces: `interface OwnerStore { suspend fun owner(): String?; suspend fun adopt(userName: String) }`（`sync/RecordOwner.kt` に置く。Task 5 で作る。このタスクでは `RoomOwner` が実装するため、先にこの interface だけ `sync/RecordOwner.kt` に置く）。`TakeoverDao.owner(): String?`・`TakeoverDao.setOwner(OwnerEntity)`。`MIGRATION_6_7`。

- [ ] **Step 1: 失敗するテストを書く**

`RoomOwnerTest.kt`:

```kotlin
package com.touringproject.v2.store

@RunWith(AndroidJUnit4::class)
class RoomOwnerTest {
  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
    .allowMainThreadQueries()
    .build()
  private val owner = RoomOwner(db.takeover())

  @After
  fun close() = db.close()

  @Test
  fun a_new_device_has_no_owner() = runBlocking {
    assertNull(owner.owner())
  }

  @Test
  fun the_owner_is_kept_and_replaced() = runBlocking {
    owner.adopt("rider01")
    assertEquals("rider01", owner.owner())
    owner.adopt("taro01")
    assertEquals("taro01", owner.owner())
  }
}
```

`MigrationTest.kt` に足す（既存の各テストの `.addMigrations(...5_6)` の並びには `MIGRATION_6_7` を足す）:

```kotlin
  // Slice 6 plan 5 (adr/0015): the owner of the records. The table is new and empty, and nothing else moves.
  @Test
  fun version_6_moves_to_7_adding_an_empty_owner_and_keeping_the_rides() {
    helper.createDatabase(DB, 6).apply {
      execSQL("INSERT INTO rides VALUES ('r1', '箱根', 'ended', 'manual', NULL, 5000, 120.0, 6000, 6000, NULL, 0, NULL)")
      close()
    }
    helper.runMigrationsAndValidate(DB, 7, true, MIGRATION_6_7).close()
    val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6, MIGRATION_6_7)
      .allowMainThreadQueries()
      .build()
    runBlocking {
      assertEquals("箱根", db.rides().ride("r1")!!.name)
      assertNull(db.takeover().owner())
    }
    db.close()
  }
```
（`rides` の列の数は、同じファイルの 5 → 6 のテストが入れている `INSERT INTO rides VALUES (…)` に合わせる。）

- [ ] **Step 2: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest --tests '*RoomOwnerTest' --tests '*MigrationTest'`
Expected: コンパイルエラー（`RoomOwner`・`MIGRATION_6_7` が無い）。

- [ ] **Step 3: 表と Migration**

`store/Entities.kt` の先頭のコメントを、`RideDatabase.kt` の先頭のコメントと重ならない1行に直し（#99）、末尾に足す:

```kotlin
/** The one row that says whose records the device keeps: the user name they were kept and sent under (adr/0015). */
@Entity(tableName = "owner")
data class OwnerEntity(@PrimaryKey val id: Int = 0, val userName: String)
```

`store/TakeoverDao.kt`:

```kotlin
  @Query("SELECT userName FROM owner WHERE id = 0")
  suspend fun owner(): String?

  @Upsert
  suspend fun setOwner(owner: OwnerEntity)
```

`store/Migrations.kt`:

```kotlin
/**
 * 6 -> 7 (slice 6 plan 5, adr/0015): the owner of the records, one row. It only adds, so it stays quick inside
 * RideController.load() (adr/0006). The row is empty; the first pass of the sync after this version takes the user
 * name of the settings as the owner (RecordOwner).
 */
val MIGRATION_6_7 = object : Migration(6, 7) {
  override fun migrate(db: SupportSQLiteDatabase) {
    db.execSQL("CREATE TABLE IF NOT EXISTS `owner` (`id` INTEGER NOT NULL, `userName` TEXT NOT NULL, PRIMARY KEY(`id`))")
  }
}
```

`store/RideDatabase.kt`: `entities` に `OwnerEntity::class`、`version = 7`、`addMigrations(…, MIGRATION_5_6, MIGRATION_6_7)`。

`store/RoomOwner.kt`:

```kotlin
package com.touringproject.v2.store

import com.touringproject.v2.sync.OwnerStore

/** The owner of the records, kept in Room beside them (adr/0015). */
class RoomOwner(private val dao: TakeoverDao) : OwnerStore {
  override suspend fun owner(): String? = dao.owner()

  override suspend fun adopt(userName: String) = dao.setOwner(OwnerEntity(userName = userName))
}
```

`sync/RecordOwner.kt`（このタスクでは interface だけ。Task 5 が続きを足す）:

```kotlin
package com.touringproject.v2.sync

/** Whose records the device keeps (adr/0015). */
interface OwnerStore {
  /** The user name the records are kept under; null before any was taken. */
  suspend fun owner(): String?

  /** Takes userName as the owner. */
  suspend fun adopt(userName: String)
}
```

- [ ] **Step 4: 全体を回す**

先に `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest` を `clean` なしで回す。版を上げた最初の実行は、ビルドが `app/schemas/com.touringproject.v2.store.RideDatabase/7.json` を作るのと同じ実行の中で `MigrationTest` が読もうとして、`FileNotFoundException` で落ちる（作業場で確かめた）。2回目は通る。そのあとで:

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`
Expected: 全件 PASS。`git status` で `7.json` が出ていて、版 6 までの JSON が変わっていないこと。

- [ ] **Step 5: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/store/Entities.kt app/src/main/java/com/touringproject/v2/store/TakeoverDao.kt app/src/main/java/com/touringproject/v2/store/Migrations.kt app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomOwner.kt app/src/main/java/com/touringproject/v2/sync/RecordOwner.kt app/src/test/java/com/touringproject/v2/store/RoomOwnerTest.kt app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
git add app/schemas
git commit -m "feat: keep the owner of the records in Room (schema 7, R10-03)"
```

---

### Task 5: 食い違うあいだは送らず、名前の変更が持ち主を書き換える（R10-03・R2-02）

**Files:**
- Modify: `sync/RecordOwner.kt`、`sync/RideSync.kt:123-135`・`pass()`、`sync/Takeover.kt`（`take` の引数）、`store/RoomTakeover.kt`、`AppGraph.kt`
- Test: `sync/RecordOwnerTest.kt`（新規）、`sync/RideSyncTest.kt`、`sync/TakeoverTest.kt`、`store/RoomTakeoverTest.kt`

**Interfaces:**
- Consumes: Task 2 の `nameChangeBlock`・`BlockReason.OWNER`、Task 3 の `SettingsRepository.nameConfirmed`、Task 4 の `OwnerStore`・`RoomOwner`・`TakeoverDao.owner/setOwner`。
- Produces: `enum class OwnerState { UNKNOWN, MATCH, MISMATCH, UNCONFIRMED }`、`class RecordOwner(store: OwnerStore, name: () -> String?, confirmed: () -> Boolean, log: (String, Throwable) -> Unit)` の `val state: StateFlow<OwnerState>` と `suspend fun check(): Boolean`。`RideSync` の引数 `mayPass: suspend () -> Boolean = { true }`。`TakeoverStore.take(cloud: CloudRecords, replace: Boolean, userName: String): TakeResult`。

- [ ] **Step 1: RecordOwner の失敗するテストを書く**

`sync/RecordOwnerTest.kt`:

```kotlin
package com.touringproject.v2.sync

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

private class FakeOwner(var owner: String? = null) : OwnerStore {
  val adopted = mutableListOf<String>()
  var failRead = false
  override suspend fun owner(): String? {
    if (failRead) throw java.io.IOException("room")
    return owner
  }
  override suspend fun adopt(userName: String) {
    adopted += userName
    owner = userName
  }
}

class RecordOwnerTest {
  private fun owner(store: OwnerStore, name: String? = "rider01", confirmed: Boolean = true) =
    RecordOwner(store, { name }, { confirmed }) { _, _ -> }

  @Test
  fun the_name_of_the_owner_may_send() = runTest {
    val owner = owner(FakeOwner("rider01"))
    assertTrue(owner.check())
    assertEquals(OwnerState.MATCH, owner.state.value)
  }

  // Review Focus 1: a device from before the owner was kept takes the name of the settings, and goes on sending.
  @Test
  fun a_device_without_an_owner_adopts_the_name_of_the_settings() = runTest {
    val store = FakeOwner(null)
    val owner = owner(store)
    assertTrue(owner.check())
    assertEquals(listOf("rider01"), store.adopted)
  }

  // R2-02: a name that is not the owner's sends nothing.
  @Test
  fun another_name_than_the_owners_sends_nothing() = runTest {
    val owner = owner(FakeOwner("taro01"))
    assertFalse(owner.check())
    assertEquals(OwnerState.MISMATCH, owner.state.value)
  }

  // R2-01, Review Focus 2: a name made up because the settings could not be read is neither adopted nor sent under.
  @Test
  fun an_unconfirmed_name_sends_nothing() = runTest {
    val store = FakeOwner(null)
    val owner = owner(store, confirmed = false)
    assertFalse(owner.check())
    assertEquals(OwnerState.UNCONFIRMED, owner.state.value)
    assertEquals(emptyList<String>(), store.adopted)
  }

  @Test
  fun the_settings_not_yet_loaded_send_nothing() = runTest {
    val owner = owner(FakeOwner("rider01"), name = null)
    assertFalse(owner.check())
    assertEquals(OwnerState.UNKNOWN, owner.state.value)
  }

  @Test
  fun an_owner_that_cannot_be_read_sends_nothing() = runTest {
    val store = FakeOwner("rider01").apply { failRead = true }
    val owner = owner(store)
    assertFalse(owner.check())
    assertEquals(OwnerState.UNKNOWN, owner.state.value)
  }

  @Test
  fun the_state_follows_the_name() = runTest {
    var name: String? = "taro01"
    val owner = RecordOwner(FakeOwner("rider01"), { name }, { true }) { _, _ -> }
    assertFalse(owner.check())
    name = "rider01"
    assertTrue(owner.check())
    assertEquals(OwnerState.MATCH, owner.state.value)
  }
}
```

- [ ] **Step 2: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest --tests '*RecordOwnerTest'`
Expected: コンパイルエラー（`RecordOwner`・`OwnerState` が無い）。

- [ ] **Step 3: RecordOwner を実装する**

`sync/RecordOwner.kt` に足す:

```kotlin
/** MATCH is the only state in which records are sent. UNKNOWN is before it could be told. */
enum class OwnerState { UNKNOWN, MATCH, MISMATCH, UNCONFIRMED }

/**
 * Tells whether the records may be sent under the user name of the settings: only when that name is the owner's
 * (adr/0015). A pass of the sync asks first, and what it finds is what SC-14 and SC-18 tell. A device with no owner yet
 * takes the name of the settings, unless that name is made up (the settings could not be read).
 */
class RecordOwner(
  private val store: OwnerStore,
  /** The user name of the settings, or null before they are loaded. */
  private val name: () -> String?,
  /** False while the name is made up because the settings could not be read. */
  private val confirmed: () -> Boolean,
  private val log: (String, Throwable) -> Unit,
) {
  private val now = MutableStateFlow(OwnerState.UNKNOWN)
  val state: StateFlow<OwnerState> = now.asStateFlow()

  suspend fun check(): Boolean {
    val name = name()
    val result = when {
      name == null -> OwnerState.UNKNOWN
      !confirmed() -> OwnerState.UNCONFIRMED
      else -> try {
        val owner = store.owner()
        when {
          owner == null -> { store.adopt(name); OwnerState.MATCH }
          owner == name -> OwnerState.MATCH
          else -> OwnerState.MISMATCH
        }
      } catch (e: CancellationException) {
        throw e
      } catch (e: Exception) {
        log("owner check failed", e)
        OwnerState.UNKNOWN
      }
    }
    now.value = result
    return result == OwnerState.MATCH
  }
}
```
（import: `kotlinx.coroutines.CancellationException`・`MutableStateFlow`・`StateFlow`・`asStateFlow`。）

- [ ] **Step 4: RideSync の門の失敗するテストを書く**

`sync/RideSyncTest.kt` に足す（既存のテストの作り方に合わせる。`store`・`api` は同じファイルの作り物）:

```kotlin
  // R2-02: a pass that may not go makes no request, and does not ask for the client.
  @Test
  fun a_pass_that_may_not_go_asks_for_nothing() = runTest {
    var asked = 0
    val sync = RideSync(nothingToSend, { asked += 1; null }, mayPass = { false }) { _, _ -> }
    sync.pass()
    assertEquals(0, asked)
  }

  @Test
  fun a_pass_that_may_go_asks_for_the_client() = runTest {
    var asked = 0
    val sync = RideSync(nothingToSend, { asked += 1; null }, mayPass = { true }) { _, _ -> }
    sync.pass()
    assertEquals(1, asked)
  }
```
（`nothingToSend` が `RideSyncTest.kt` に無ければ、`TakeoverTest.kt` のそれと同じ `SyncStore` の作り物を `RideSyncTest.kt` の中に作る。）

- [ ] **Step 5: 門を足す**

`sync/RideSync.kt` のコンストラクターの `saved` の次に:

```kotlin
  /** Whether the records may be sent under the current user name (RecordOwner.check); a pass that may not go does not start. */
  private val mayPass: suspend () -> Boolean = { true },
```
`pass()` の先頭に:

```kotlin
  suspend fun pass() = passing.withLock {
    if (!mayPass()) return@withLock
    if (!online()) return@withLock
```

- [ ] **Step 6: 名前の変更の失敗するテストを書く**

`store/RoomTakeoverTest.kt` の先頭の補助 `RoomTakeover.take(cloud, replace, now)` に `userName: String = "rider01"` を足し、`take(CloudRecords(cloud, now), replace, userName)` を呼ぶ形にする。次を足す:

```kotlin
  // The owner is written with the records, in one transaction (adr/0015).
  @Test
  fun a_change_of_name_writes_the_owner_with_the_records() = runBlocking {
    takeover.take(cloud, replace = true, now = NOW, userName = "taro01")
    assertEquals("taro01", db.takeover().owner())
  }

  @Test
  fun a_blocked_change_leaves_the_owner_as_it_was() = runBlocking {
    db.takeover().setOwner(OwnerEntity(userName = "rider01"))
    rides.save(newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(5_000, EndReason.MANUAL, 5_000))
    assertEquals(TakeResult.Blocked(BlockReason.UNSENT), takeover.take(cloud, replace = true, now = NOW, userName = "taro01"))
    assertEquals("rider01", db.takeover().owner())
  }

  // Review Focus 3: going back to the owner's name keeps the records and what is left to send.
  @Test
  fun going_back_to_the_owner_keeps_the_records_and_the_unsent() = runBlocking {
    db.takeover().setOwner(OwnerEntity(userName = "rider01"))
    rides.save(newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(5_000, EndReason.MANUAL, 5_000))
    assertTrue(takeover.take(cloud, replace = true, now = NOW, userName = "rider01") is TakeResult.Done)
    assertEquals("rider01", db.takeover().owner())
    assertEquals(1, sync.unsent().count { it.ride.id == "r1" })
  }

  // Review Focus 4: another name than the owner's replaces the records, so unsent ones still stop it.
  @Test
  fun another_name_still_stops_on_unsent_records() = runBlocking {
    db.takeover().setOwner(OwnerEntity(userName = "rider01"))
    rides.save(newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(5_000, EndReason.MANUAL, 5_000))
    assertEquals(TakeResult.Blocked(BlockReason.UNSENT), takeover.take(cloud, replace = true, now = NOW, userName = "hanako02"))
    assertEquals(1, sync.unsent().size)
  }

  // A read again under a name that the records are not of would put another name's records among them.
  @Test
  fun a_read_again_under_another_name_is_blocked() = runBlocking {
    db.takeover().setOwner(OwnerEntity(userName = "rider01"))
    assertEquals(TakeResult.Blocked(BlockReason.OWNER), takeover.take(cloud, replace = false, now = NOW, userName = "taro01"))
  }

  @Test
  fun a_read_again_on_a_device_without_an_owner_takes_the_name_as_the_owner() = runBlocking {
    assertTrue(takeover.take(cloud, replace = false, now = NOW, userName = "rider01") is TakeResult.Done)
    assertEquals("rider01", db.takeover().owner())
  }
```
（`cloud` はそのファイルの既存の値。無ければ `listOf(cloudRide(), cloudRoute())`。`sync` は同じファイルの `RoomSyncStore`。）

`sync/TakeoverTest.kt` の `Cloud` の作り物 `TakeoverStore` は `take(cloud, replace, userName)` を受ける。既存のテストが見ている `taken`（`records to replace` の組）は変えず、別の記録 `takenUnder` を足す:

```kotlin
  /** The user name each take was asked for, in order. */
  val takenUnder = mutableListOf<String>()

  val store = object : TakeoverStore {
    override suspend fun take(cloud: CloudRecords, replace: Boolean, userName: String): TakeResult {
      takeGate?.await()
      if (failTake) throw IOException("disk full")
      taken += cloud.records to replace
      takenUnder += userName
      return takes
    }
  }
```
そして1本足す:

```kotlin
  // The records come in under the name that was read: the new name for a switch, the current one for a read again.
  @Test
  fun a_switch_takes_under_the_new_name_and_a_read_again_under_the_current_one() = runTest {
    val c = Cloud(this)
    c.pages["taro01"] = mapOf(null to CloudPage(emptyList(), null))
    c.pages["rider01"] = mapOf(null to CloudPage(emptyList(), null))
    c.switch(c.takeover.peek("taro01")!!)
    runCurrent()
    c.takeover.reread("rider01")
    runCurrent()
    assertEquals(listOf("taro01", "rider01"), c.takenUnder)
    assertEquals(listOf(true, false), c.taken.map { it.second })
  }
```

- [ ] **Step 7: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest --tests '*RoomTakeoverTest' --tests '*TakeoverTest'`
Expected: コンパイルエラー（`take` に `userName` が無い）。

- [ ] **Step 8: take に名前を渡す**

`sync/Takeover.kt`:

```kotlin
interface TakeoverStore {
  /**
   * … (the existing text), and userName is the name the records are read under: it becomes the owner of the device's
   * records in the same transaction (adr/0015). With replace, going back to the owner's own name keeps the records and
   * what is left to send; a read again (no replace) under a name that is not the owner's is Blocked(OWNER).
   */
  suspend fun take(cloud: CloudRecords, replace: Boolean, userName: String): TakeResult
}
```
`switchTo` の `store.take(CloudRecords(records, now()), replace = true)` を `store.take(CloudRecords(records, now()), replace = true, userName = peek.userName)` に、`reread` を `store.take(CloudRecords(readAll(userName, null), now()), replace = false, userName = userName)` にする。

`store/RoomTakeover.kt` の `take`:

```kotlin
  override suspend fun take(cloud: CloudRecords, replace: Boolean, userName: String): TakeResult = db.withTransaction {
    if (takeover.activeRides() > 0) return@withTransaction TakeResult.Blocked(BlockReason.RIDE)
    val owner = takeover.owner()
    if (replace) {
      // Going back to the owner's own name keeps the records, so what is left to send is theirs to send (adr/0015).
      if (owner != userName) {
        nameChangeBlock(rideActive = false, unsent = rides.summaryNow().unsent, waitingToSave = waitingToSave())
          ?.let { return@withTransaction TakeResult.Blocked(it) }
        takeover.clearAll()
      }
    } else if (owner != null && owner != userName) {
      return@withTransaction TakeResult.Blocked(BlockReason.OWNER)
    }
    val merged = cloud.mergeInto(device())
    write(merged)
    takeover.setOwner(OwnerEntity(userName = userName))
    TakeResult.Done(merged.count)
  }
```
クラスの KDoc に「持ち主は記録と同じトランザクションで書く」を1文足す。

- [ ] **Step 9: AppGraph に配線する**

`AppGraph.kt`（`database` と `settings` の後、`sync` の前）:

```kotlin
  /** Whose records the device keeps; a pass of the sync goes only when the name of the settings is the owner's (adr/0015). */
  val owner = RecordOwner(
    store = RoomOwner(database.takeover()),
    name = { settings.settings.value?.userName },
    confirmed = { settings.nameConfirmed },
    log = { message, e -> Log.w("trv2.sync", message, e) },
  )
```
`RideSync(` の引数に `mayPass = owner::check,` を足す。import は `com.touringproject.v2.store.RoomOwner`・`com.touringproject.v2.sync.RecordOwner`。

- [ ] **Step 10: 全体を回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`
Expected: 全件 PASS。

- [ ] **Step 11: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/sync/RecordOwner.kt app/src/main/java/com/touringproject/v2/sync/RideSync.kt app/src/main/java/com/touringproject/v2/sync/Takeover.kt app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/test/java/com/touringproject/v2/sync/RecordOwnerTest.kt app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
git commit -m "feat: send only when the user name is the owner of the records (R10-03, R2-02)"
```

---

### Task 6: 食い違いを SC-14・SC-18 で知らせ、SC-18 で直せるようにする

**Files:**
- Modify: `ui/AppUi.kt`（`UserKey`・`DataKey` の entry）、`ui/SettingsScreens.kt`（`UserScreen`・`DataScreen`・`DataUi`）、`ui/SavingLabels.kt`
- Test: UI のテスト（`SettingsScreensTest` など、`UserScreen`・`DataScreen` を描くもの。`rg "UserScreen\(\|DataScreen\(" Android/app/src/test` で探す）、`SavingLabelsTest`

**Interfaces:**
- Consumes: `RecordOwner.state`、`nameChangeBlock`、`blockMessage`。
- Produces: `fun ownerNotice(state: OwnerState): String?`（`ui/SavingLabels.kt`）。`UserScreen(…, ownerNotice: String? = null)`、`DataUi.ownerNotice: String? = null`。

- [ ] **Step 1: 失敗するテストを書く**

`ui/SavingLabelsTest.kt`（あれば追記、無ければ新規）:

```kotlin
  @Test
  fun a_mismatch_and_an_unconfirmed_name_are_told_and_the_rest_are_not() {
    assertEquals("ユーザー名と端末の記録が合っていません。記録は送られていません", ownerNotice(OwnerState.MISMATCH))
    assertEquals("ユーザー名を確かめられていません。記録は送られていません", ownerNotice(OwnerState.UNCONFIRMED))
    assertNull(ownerNotice(OwnerState.MATCH))
    assertNull(ownerNotice(OwnerState.UNKNOWN))
  }
```
`ui/ScreensTest.kt` の `UserScreen` のテスト（261〜295行）の隣に足す（`rule` は同じファイルの `createComposeRule()`）:

```kotlin
  // A mismatch is told on SC-18, and the change stays possible: it is how the rider mends it (adr/0015).
  @Test
  fun the_notice_of_a_mismatch_is_shown_and_the_change_is_still_possible() {
    rule.setContent {
      UserScreen("rider01", null, false, null, { null }, {}, {}, ownerNotice = "ユーザー名と端末の記録が合っていません。記録は送られていません")
    }
    rule.onNodeWithTag("ownerNotice").assertExists()
    rule.onNodeWithTag("userInput").performTextInput("taro01")
    rule.onNodeWithTag("changeUser").assertIsEnabled()
  }

  @Test
  fun no_notice_is_shown_when_the_name_matches() {
    rule.setContent { UserScreen("rider01", null, false, null, { null }, {}, {}) }
    rule.onNodeWithTag("ownerNotice").assertDoesNotExist()
  }
```
`DataScreen` にも同じ知らせが出るテストを `ScreensTest.kt` の `DataScreen` のテストの隣に1本足す（`DataUi(…, ownerNotice = "…")` を渡し、`onNodeWithTag("ownerNotice").assertExists()`。`DataUi` の他の引数は隣のテストが渡しているものをそのまま使う）。

- [ ] **Step 2: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew testDebugUnitTest --tests '*SavingLabelsTest' --tests '*SettingsScreens*'`
Expected: コンパイルエラー（`ownerNotice` が無い）。

- [ ] **Step 3: 実装**

`ui/SavingLabels.kt`:

```kotlin
/** What SC-14 and SC-18 tell when the records are not sent for the owner's sake (adr/0015); null when nothing is wrong. */
fun ownerNotice(state: OwnerState): String? = when (state) {
  OwnerState.MISMATCH -> "ユーザー名と端末の記録が合っていません。記録は送られていません"
  OwnerState.UNCONFIRMED -> "ユーザー名を確かめられていません。記録は送られていません"
  OwnerState.MATCH, OwnerState.UNKNOWN -> null
}
```
`ui/SettingsScreens.kt`: `UserScreen` に `ownerNotice: String? = null` を足し、「今のユーザー名」の下に `ownerNotice?.let { Text(it, color = Red, modifier = Modifier.testTag("ownerNotice")) }`。`DataUi` に `val ownerNotice: String? = null` を足し、`DataScreen` の保存の状態の近くに同じ `Text`（タグ `ownerNotice`）。

`ui/AppUi.kt`:

```kotlin
                val ownerState by graph.owner.state.collectAsStateWithLifecycle()
```
を `UserKey` と `DataKey` の entry に置き、`UserScreen(…, ownerNotice = ownerNotice(ownerState))`、`DataUi(…, ownerNotice = ownerNotice(ownerState))` を渡す。`UserKey` の `block` は、食い違いのあいだ、未送信を数えない（その記録は持ち主のもので、名前を戻すなら残るため。ほかの名前への変更は、トランザクションが未送信で止める）:

```kotlin
                val block = nameChangeBlock(
                  ride != null,
                  unsent = if (ownerState == OwnerState.MISMATCH) 0 else summary?.unsent ?: 0,
                  waitingToSave = waitingToSave,
                )
```
SC-18 を開いたとき `graph.owner` の状態が古くならないよう、`LaunchedEffect(Unit) { graph.sync.request() }` を `UserKey` の entry に足す（`pass()` の入口が `check()` を呼ぶ）。

- [ ] **Step 4: 全体を回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest`
Expected: 全件 PASS。

- [ ] **Step 5: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
git add -u app/src/test
git commit -m "feat: tell the rider when the user name and the records do not match (R2-02)"
```

---

### Task 7: 後始末・文書・版（Android #99）

**Files:**
- Modify: `ask/AskPorts.kt`・`ui/TextAskSheet.kt`（未使用 import）、`Android/README.md`、`app/build.gradle.kts`

- [ ] **Step 1: 未使用 import を消す**

`ask/AskPorts.kt` の `import kotlinx.serialization.Serializable` と、`ui/TextAskSheet.kt` の `import com.touringproject.v2.ask.TextAskOutcome` を消す（`rg "Serializable" ask/AskPorts.kt`・`rg "TextAskOutcome" ui/TextAskSheet.kt` で使われていないことを先に確かめる）。`Entities.kt` の先頭のコメントは Task 4 で直した。

- [ ] **Step 2: README と版**

`Android/README.md` の「大事な決まり」に、次の2点を書く: 記録の持ち主は Room の `owner` にあり、送信の回は設定の名前と持ち主が合うときだけ走る／「未送信」の SQL は `store/Unsent.kt` に置き、画面の「止める条件」は `nameChangeBlock` を通す。テストの節の件数を、全体を回した件数に直す。`app/build.gradle.kts` の `versionCode = 18`・`versionName = "0.14.3"`。

- [ ] **Step 3: 全体を回し、ビルドする**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android && ./gradlew clean testDebugUnitTest assembleDebug`
Expected: 全件 PASS。`app/build/outputs/apk/debug/app-debug.apk` ができる。件数を ledger に書く。

- [ ] **Step 4: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Android
git add app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/ui/TextAskSheet.kt README.md app/build.gradle.kts
git commit -m "chore: raise the version to 0.14.3 and describe the record owner in the README"
```

---

### Task 8: 実機の確かめ

実機の確かめは利用者が行う。`app-debug.apk` を `adb install --user 0 -r` で入れる（既存の Room の版 6 から 7 への更新になる）。

- [ ] **Step 1: 更新後の最初の起動** — 記録（走行・メモ）が全部見える。SC-14 に食い違いの知らせが出ない。DynamoDB で、更新の前後に送った記録のユーザー名が同じ。
- [ ] **Step 2: 名前の変更（記録なしの名前）** — SC-18 で、未送信が無いときに別の名前へ変える。変えたあと、SC-05 が空になり、元の名前に戻すと記録が戻る。
- [ ] **Step 3: 未送信があるとき** — 機内モードで走行を終え、SC-18 で名前を変えようとすると「未送信の記録があります」で止まる。
- [ ] **Step 4: 設定の連打** — SC-11 の「＋」を素早く何度も押し、押した回数だけ値が増える。そのあとユーザー名が変わっていない。
- [ ] **Step 5: 食い違い（任意。デバッグ用に作る）** — `adb shell run-as` で設定のユーザー名だけを書き換えて起動すると、SC-14 と SC-18 に知らせが出て、記録が送られない。SC-18 で元の名前を入れると、記録が残ったまま知らせが消え、送られる。
- [ ] **Step 6: 結果を PROJECT.md に書く** — 確かめられたものと、確かめなかったものを分けて書く。

---

## Self-Review

- **Spec coverage**: spec §3 の plan 5（R10-03・R10-02・R10-10、関連 R2-01・R2-02、スキーマの版を1つ上げる）は Task 1〜5。§1 の「端末の記録が別のユーザー名で送られる経路がテストで塞がっている（R2-01・R2-02・R10-03）」は Task 3（読めなかった起動）・Task 5（食い違い）のテスト。実機は §7 のとおり Task 8。
- **R10-02 の一部は見送った**: `toRecord().sent` は意味が違うので1つにしない（Rulings）。
- **型の一貫**: `nameChangeBlock`（Task 2）→ `RoomTakeover`・`AppUi`（Task 2・5・6）、`OwnerStore`（Task 4）→ `RecordOwner`（Task 5）、`take(cloud, replace, userName)`（Task 5）→ `Takeover`・テストの作り物。`update(from, to)`（Task 3）→ `AppUi` の呼び出し。
- **使い捨てのフォルダで通したもの**（PROJECT.md の前提）: Task 2 の `nameChangeBlock` とそのテスト、Task 3 の `applyChange`・`SettingsRepository`・`SettingsTest` の全部、Task 4 の `owner` の表・Migration・`RoomOwner`・`MigrationTest`・`RoomOwnerTest`、Task 5 の `RecordOwner` とそのテスト（`AppUi` の呼び出しの書き換えを含めてコンパイルした）。
- **通していないもの**: Task 1 の `Unsent.kt` の置き換えと `UnsentAgreementTest`、Task 5 の `RideSync` の門・`take(…, userName)`・`RoomTakeoverTest` の新しい6本・`AppGraph` の配線、Task 6 の画面。実行のときは、各タスクの「失敗を見る」で、名前と引数が合うかをまず確かめる。`UnsentAgreementTest` は `RoomSyncStoreTest` の組み立てに合わせて書いたが、`unreachedAsk` の引数と `NoteEntity` の位置引数は実際のファイルで確かめる。
