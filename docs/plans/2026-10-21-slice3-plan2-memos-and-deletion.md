# スライス3 計画2: Android（メモと削除・送信の広げ方） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 会話と走行にメモを書き・直し・消せるようにし（SC-08）、会話と終えた走行を削除できるようにする（DL-01）。メモと削除は、削除の印を端末に溜めて Backend へ送る。メモのある走行・会話は、一覧・時系列・地図のピンで分かる。あわせて、送信の後回しの指摘（Android #23・#25・#26・#29）を直す。

**Architecture:** Room を版5に上げ、走行と質問にメモの列を、削除の印の表（`deletions`）と、plan 3 で使う地点メモの表（`notes`）を足す。走行のメモと走行の削除は `RideController`（走行を変えるのはここだけ）が、会話のメモと削除は新しい `RoomAskEdits`（`records.AskEdits`）が書く。記録を消すのと同じトランザクションで削除の印を書く。送信の係（`RideSync`）は、1回の中で 削除の印 → 走行とルート → 会話のメモ の順に送り、410 を送れたものとして扱う。画面は SC-08（`MemoScreen`）と DL-01（`DeleteDialog`）を足し、SC-02・SC-05〜SC-07 につなぐ。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版5）・Robolectric 4.16（SDK 35）・MapLibre 13.6.1・OkHttp・kotlinx.serialization。足す依存は無い。

**Spec:** [docs/specs/2026-10-21-slice3-design.md](../specs/2026-10-21-slice3-design.md)（§2・§4・§5・§7.1〜§7.7・§8・§9・§11）。決定の記録は [adr/0009](../../adr/0009-keep-deletion-marks-in-the-cloud.md)。Backend の受け口は plan 1 でデプロイ済み（07 の UC-7、`Backend/openapi.yaml`）。

**範囲に入れた issue（Android）:** #23（未送信の読み出しが1つのトランザクションでない）・#25（組み立てで必ず失敗する走行が、後ろの走行を止める）・#26（400 の理由がログに残らない）・#29（接続キーを保存しても送信が始まらない）。spec §2 の #49・#51 は、地図と時系列を触る plan 3 で直す。Backend #16（2000字の数え方）の Android 側の答えとして、メモの文字数をコードポイントで数える。

**前提:** Android の `main`（`144a687`。版 0.5.0）の上に作る。Backend は plan 1 の受け口がデプロイ済み（`stack-trv2-dev-backend`）。

**計画を書くときに決めたこと（spec からの具体化）:**
- Room の版5で、spec §4.1 の表を一度に足す（地点メモの `notes` も、使うのは plan 3 だが、スライス3のマイグレーションを1回にするため、ここで作る）。列と表を足すだけで、今の行は変えない。
- 走行のメモは `Ride.memo` に持ち、メタ情報の一部として送る（`RideBody.memo`。無いときは項目を省き、Backend はそれを「メモ無し」として保存済みのメモも消す）。書くのは `RideController.memo(rideId, memo)`。同じメモをもう一度書いても保存も送信もしない。
- 走行の削除は `RideController.delete(rideId)`。終えた走行だけを消し、記録中・一時停止中は false（spec §2）。書き直し待ちの保存（`unsaved`）が同じ走行なら捨てる。捨てないと、次の呼び出しが消した走行を書き戻す。
- 走行を消すときは、質問・地点メモ・点・区間・走行の行を、表ごとに名前で消す（外部キーに頼らない。質問には外部キーが無い）。
- 会話のメモと削除は `AskEdits`（`memo(askId, memo)`・`delete(askId)`）。`RoomAskEdits` が Room に書き、書けたら送信を頼む（`sync.request`）。書き込みの失敗はログに出して false を返し、画面が「保存できませんでした」「削除できませんでした」を出す（spec §8）。
- メモの変更の時刻 `memoUpdatedAt` は、前の値より必ず後にする（`memoTime`。端末の時計が戻っても Backend が新しい版として受ける）。
- メモは前後の空白を落とし、空白だけは「メモ無し」。2000字はコードポイントで数え、入力欄は2000字で切る（Backend と同じ数え方。Backend #16。絵文字を途中で切らない）。
- 送信の答えの扱い: 400 と、会話のメモへの 404 は「断られた」（その版は送り直さない）。410 は「送れた」。端末で中身を組み立てられない `SerializationException` も「断られた」として次へ進む（#25）。`IllegalArgumentException` は含めない（OkHttp が不正な API の URL で投げるので、含めると設定の誤りで全部が「断られた」になる）。断られた削除の印は消す（いつまでも送れないので、毎回の送信を止めないように）。
- 400 の理由: `ApiError` の message を `HTTP 400: <Backend の message>` にする（#26。読めなければ `HTTP 400`）。
- #23: `RideDao.unsentSnapshot()` を `@Transaction` にし、走行の行・区間・点の数をまとめて読む。テストは中身を確かめ、割り込めないことは Room の `@Transaction` に任せる。
- #29: `credentialChanges(key, userName)` が、接続キーとユーザー名の両方が分かったあとの変化ごとに送信を頼む（最初の読み込みは数えない。キーを消したときも頼まない）。`AppGraph` が集める。
- 保存の状態（spec §5.3）: 一覧の「未送信あり」に、その走行の質問のメモの未送信を数える（`RideRow.memosLeft`）。
- メモの印（US-D-04.005）: 一覧は名前の後ろに「 📝」、時系列は時刻と場所の後ろに「 · 📝」、地図のピンは右上に白い点（絵の名前は `pin-<番号>-memo`・`pin-sel-<番号>-memo`）。
- SC-08 は `MemoScreen(target, initial, onSave, onClose)`。上の行は「会話 3 · 09:41 箱根町仙石原」（`askMemoTarget`）か「走行のメモ · <走行の名前>」。下に「n / 2000字」。保存のあいだは保存のボタンを押せなくする。✕ と Back は、変更があれば「変更を破棄しますか？」（「破棄する」「書き続ける」）。SC-08 のあいだはタブの帯を出さない（モック）。
- DL-01 は `DeleteDialog`（「やめる」が左、赤い「削除する」が右）。今の録音と接続キーの確認も、文言はそのままでこれに置き換える。会話と走行の文言はモックの表のとおり（`DeleteKind`）。消せたら一つ前の画面へ戻る（走行は SC-05、会話は SC-06）。
- SC-06: 要約の下に走行のメモ（無ければ「＋ 走行のメモ」）。メニューに「走行のメモ」と、終えた走行だけ「この走行を削除」。SC-07: 答えの下にメモ（無ければ「＋ メモを追加」）と「この会話を削除」。ホームの走行のカードは、ボタンの列を「一時停止／再開」「📝 走行メモ」「■ 終了」にする（モック）。
- `AppUi` の中の記録の画面は本物の地図（MapLibre）を描くので、Robolectric では通しのテストを書けない。つなぎ（SC-06 から SC-08 へ、消したあとに戻る）は Task 9 の実機で確かめる。
- 版を 0.6.0（`versionCode` 7）に上げる。

この計画のコードは、使い捨てのフォルダで、次を確かめてから書いた。

- タスクの順に一つずつコミットし、各タスクのコミットで `clean` から JVM のテストが通る（381件 → 441件）。各タスクのテストだけを1つ前のコミットに当てると、まだ無い名前を使うので、コンパイルで落ちる。
- 最後に、JVM のテスト441件・エミュレーターのテスト6件・`assembleRelease`・`scripts/check-release-permissions.sh`（15件）が通る。
- plan の差分を新しい写しへ機械的に当てると、最終形と一致する。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice3-plan2` を切る（Task 0）。親は `slice3-plan2`。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- 作りの決まり: 状態機械と司令塔は Android に依存させない。部品は `AppGraph` で手で組む。走行を変えるのは `RideController` だけ（メモと削除も）。
- 削除できる走行は、終えたものだけ（spec §2）。記録を消すときは、同じトランザクションで削除の印を書く（spec §4.2）。
- メモと地点メモは2000字まで（US-D-04.003）。文字はコードポイントで数える。
- ホームは全体がスクロールしない（spec §7）。
- Room のスキーマは版を上げて Migration を書き、`app/schemas/` の JSON をコミットする。破壊的な作り直しは使わない。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --tests '*クラス名'`。テストを確かめるときは `--rerun` を付ける。Kotlin の差分コンパイルは interface の変更を見逃すことがあるので、Task 8 は `./gradlew clean` から回す。
- `RoomAskLogTest` の作り物の `AskDao` は、DAO にメソッドを足すたびに実装を足す（Task 2・Task 4 の差分に入っている）。
- Robolectric の決まり（SDK 35・`@Config(qualifiers)` で画面を大きくしない・画面の外の行は `performScrollTo`／`performScrollToNode` で出す・地図の部品は動かさない）。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。使い終わったら止める。
- AWS は `AWS_PROFILE=touring`・リージョン `ap-northeast-1`（Task 9 で DynamoDB を読むだけ）。

## Review Focus

- 名前の変更が書けずに書き直し待ちのまま、その走行を消す → 次の操作で消した走行が書き戻されない。Task 2 の `a_deleted_ride_is_not_written_back_by_a_save_still_waiting`。
- 端末の時計が戻った状態でメモを直す → 変更の時刻は前より後になり、Backend が新しい版として受ける。Task 2 の `each_change_of_the_memo_is_later_than_the_one_before`・`a_memo_moves_updated_at_on_even_with_the_clock_set_back`。
- 通信できないときに会話を消し、次の送信で削除だけが失敗する → 削除の印は残り、次の回でほかより先に送られる。Task 4 の `a_deletion_that_fails_ends_the_pass_and_goes_again_next_time`。
- 絵文字を混ぜた長いメモを貼り付ける → 入力欄は2000字（絵文字は1字）で切れ、途中で割れない。Task 2 の `the_field_keeps_2000_characters_counting_an_emoji_as_one`、Task 6 の `the_field_keeps_2000_characters_and_counts_them`。
- 保存のボタンを素早く2回押す → メモは1回だけ書かれる。Task 6 の `the_save_button_waits_for_the_save_in_progress`。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `store/RideDatabase.kt` | 版5の表と `MIGRATION_4_5`（1）、メモと削除の DAO（2）、送信の読み出し（4）、一覧の `memosLeft`（5） | 1・2・4・5 |
| `ride/Ride.kt`・`store/RoomRideStore.kt` | `Ride.memo` と `withMemo`、Room との写し、`delete` | 1・2 |
| `records/Memos.kt`（新規）・`records/AskEdits.kt`（新規） | メモの決まり（純粋）・会話を変える窓口 | 2 |
| `ride/RideController.kt`・`ride/RidePorts.kt` | `memo()`・`delete()`、`RideStore.delete` | 2 |
| `store/RoomAskEdits.kt`（新規） | 会話のメモと削除を Room に書く | 2 |
| `api/ApiClient.kt`・`sync/SyncPlan.kt` | 410・400 の理由（#26）・メモと削除の呼び出し・`RideBody.memo` | 3 |
| `sync/RideSync.kt`・`store/RoomSyncStore.kt`・`AppGraph.kt` | 送信の順番と答えの扱い（#25）・削除の印とメモの読み出し（#23）・`credentialChanges`（#29） | 4 |
| `ask/AskRecord.kt`・`store/RoomRecords.kt`・`records/Records.kt`・`ui/RecordLabels.kt`・`map/MapData.kt`・`map/RouteMap.kt`・`ui/RecordsRoutes.kt`・`ui/RecordsScreens.kt` | メモの印と保存の状態の組み立て | 5 |
| `ui/MemoScreen.kt`（新規）・`ui/DeleteDialog.kt`（新規）・`ui/RecordsScreens.kt`・`ui/RecordsRoutes.kt`・`ui/RideScreens.kt`・`ui/AppUi.kt`・`ui/RecordingsScreen.kt`・`ui/SettingsScreens.kt`・`AppGraph.kt` | SC-08・DL-01 と、SC-02・SC-05〜SC-07 へのつなぎ | 6 |
| `app/build.gradle.kts`・`README.md`・`docs-parent/` | 版 0.6.0・決まり・親の文書の写し | 7 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、今のテストを回す**

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice3-plan2
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t0.log 2>&1; tail -1 /tmp/trv2-t0.log
```

Expected: `BUILD SUCCESSFUL`（381件）。親はこの plan を書いたブランチ `slice3-plan2` のまま。

---

### Task 1: Room の版5（メモの列・削除の印・地点メモの表）

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify: `store/RideDatabase.kt`・`ride/Ride.kt`・`store/RoomRideStore.kt`
- Create: `app/schemas/com.touringproject.v2.store.RideDatabase/5.json`（Room が書き出す。差分に入っている）
- Test: `store/MigrationTest.kt`・`store/RoomRideStoreTest.kt`

**Interfaces:**
- Consumes: 今の `RideEntity`・`AskEntity`・`MIGRATION_1_2`〜`MIGRATION_3_4`
- Produces:
  - `RideEntity.memo: String?`・`AskEntity.memo`・`memoUpdatedAt`・`memoSentUpdatedAt`・`memoRejectedUpdatedAt`（どれも `Long?`／`String?`、既定 null）
  - `NoteEntity`（表 `notes`。plan 3 が使う）・`DeletionEntity(kind: String, id: String, rideId: String?, deletedAt: Long)`（表 `deletions`、主キーは kind と id）
  - `MIGRATION_4_5`。`RideDatabase` の版5
  - `Ride.memo: String? = null`。`Ride.toEntity()`・`RideEntity.toRide()` がメモを写す

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt b/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
index e3960e1..f4bac71 100644
--- a/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
@@ -30,7 +30,7 @@ class MigrationTest {
     }
     helper.runMigrationsAndValidate(DB, 2, true, MIGRATION_1_2).close()
     val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
-      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5)
       .allowMainThreadQueries()
       .build()
     runBlocking {
@@ -56,7 +56,7 @@ class MigrationTest {
     }
     helper.runMigrationsAndValidate(DB, 3, true, MIGRATION_2_3).close()
     val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
-      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5)
       .allowMainThreadQueries()
       .build()
     runBlocking {
@@ -78,7 +78,7 @@ class MigrationTest {
     }
     helper.runMigrationsAndValidate(DB, 4, true, MIGRATION_3_4).close()
     val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
-      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5)
       .allowMainThreadQueries()
       .build()
     runBlocking {
@@ -87,4 +87,31 @@ class MigrationTest {
     }
     db.close()
   }
+
+  // Slice 3 spec §4.1: memos, point memos and deletions are added; what was kept stays as it was.
+  @Test
+  fun version_4_moves_to_5_keeping_rides_and_asks_without_memos() {
+    helper.createDatabase(DB, 4).apply {
+      execSQL("INSERT INTO rides VALUES ('r1', '箱根', 'ended', 'manual', NULL, 5000, 120.0, 6000, 6000, NULL, 0)")
+      execSQL("INSERT INTO ride_segments VALUES ('r1', 0, 1000, 5000, 7)")
+      val columns = "(askId, askedAt, answeredAt, transcript, answer, latitude, longitude, address, headingDegrees, input, conversationId, newConversation, status, failure, rideId)"
+      execSQL("INSERT INTO asks $columns VALUES ('a1', 1000, 2000, 'Q', 'A', 35.0, 139.0, '箱根町', 90.0, 'voice', 'c1', 1, 'answered', NULL, 'r1')")
+      close()
+    }
+    helper.runMigrationsAndValidate(DB, 5, true, MIGRATION_4_5).close()
+    val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5)
+      .allowMainThreadQueries()
+      .build()
+    runBlocking {
+      val ride = db.rides().ride("r1")!!
+      assertEquals("箱根", ride.name)
+      assertNull(ride.memo)
+      val ask = db.asks().ask("a1")!!
+      assertEquals("Q", ask.transcript)
+      assertNull(ask.memo)
+      assertNull(ask.memoUpdatedAt)
+    }
+    db.close()
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt
index 5b42fa2..328e555 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt
@@ -73,4 +73,13 @@ class RoomRideStoreTest {
     assertTrue(saved.routeRejected)
     assertEquals(RideStatus.PAUSED, store.active()?.status)
   }
+
+  @Test
+  fun a_ride_keeps_its_memo_and_drops_it_when_saved_without_one() = runBlocking {
+    val ended = ride.end(5_000, EndReason.MANUAL, 5_000)
+    store.save(ended.copy(memo = "また来たい"))
+    assertEquals("また来たい", store.ride("r1")?.memo)
+    store.save(ended.copy(memo = null, updatedAt = 6_000))
+    assertNull(store.ride("r1")?.memo)
+  }
 }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*MigrationTest' --tests '*RoomRideStoreTest' --rerun > /tmp/trv2-t1.log 2>&1; grep -c '^e:' /tmp/trv2-t1.log`
Expected: コンパイルで落ちる（`MIGRATION_4_5` と `Ride.memo` が無い）

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/schemas/com.touringproject.v2.store.RideDatabase/5.json b/app/schemas/com.touringproject.v2.store.RideDatabase/5.json
new file mode 100644
index 0000000..b6cebc8
--- /dev/null
+++ b/app/schemas/com.touringproject.v2.store.RideDatabase/5.json
@@ -0,0 +1,537 @@
+{
+  "formatVersion": 1,
+  "database": {
+    "version": 5,
+    "identityHash": "4194cefd7bb25db361d2002586ce23e4",
+    "entities": [
+      {
+        "tableName": "rides",
+        "createSql": "CREATE TABLE IF NOT EXISTS `${TABLE_NAME}` (`id` TEXT NOT NULL, `name` TEXT NOT NULL, `status` TEXT NOT NULL, `endReason` TEXT, `deadline` INTEGER, `lastAliveAt` INTEGER, `distanceMeters` REAL NOT NULL, `updatedAt` INTEGER NOT NULL, `sentUpdatedAt` INTEGER, `rejectedUpdatedAt` INTEGER, `routeRejected` INTEGER NOT NULL DEFAULT 0, `memo` TEXT, PRIMARY KEY(`id`))",
+        "fields": [
+          {
+            "fieldPath": "id",
+            "columnName": "id",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "name",
+            "columnName": "name",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "status",
+            "columnName": "status",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "endReason",
+            "columnName": "endReason",
+            "affinity": "TEXT"
+          },
+          {
+            "fieldPath": "deadline",
+            "columnName": "deadline",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "lastAliveAt",
+            "columnName": "lastAliveAt",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "distanceMeters",
+            "columnName": "distanceMeters",
+            "affinity": "REAL",
+            "notNull": true
+          },
+          {
+            "fieldPath": "updatedAt",
+            "columnName": "updatedAt",
+            "affinity": "INTEGER",
+            "notNull": true
+          },
+          {
+            "fieldPath": "sentUpdatedAt",
+            "columnName": "sentUpdatedAt",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "rejectedUpdatedAt",
+            "columnName": "rejectedUpdatedAt",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "routeRejected",
+            "columnName": "routeRejected",
+            "affinity": "INTEGER",
+            "notNull": true,
+            "defaultValue": "0"
+          },
+          {
+            "fieldPath": "memo",
+            "columnName": "memo",
+            "affinity": "TEXT"
+          }
+        ],
+        "primaryKey": {
+          "autoGenerate": false,
+          "columnNames": [
+            "id"
+          ]
+        }
+      },
+      {
+        "tableName": "ride_segments",
+        "createSql": "CREATE TABLE IF NOT EXISTS `${TABLE_NAME}` (`rideId` TEXT NOT NULL, `seq` INTEGER NOT NULL, `startedAt` INTEGER NOT NULL, `endedAt` INTEGER, `bootCount` INTEGER, PRIMARY KEY(`rideId`, `seq`), FOREIGN KEY(`rideId`) REFERENCES `rides`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE )",
+        "fields": [
+          {
+            "fieldPath": "rideId",
+            "columnName": "rideId",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "seq",
+            "columnName": "seq",
+            "affinity": "INTEGER",
+            "notNull": true
+          },
+          {
+            "fieldPath": "startedAt",
+            "columnName": "startedAt",
+            "affinity": "INTEGER",
+            "notNull": true
+          },
+          {
+            "fieldPath": "endedAt",
+            "columnName": "endedAt",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "bootCount",
+            "columnName": "bootCount",
+            "affinity": "INTEGER"
+          }
+        ],
+        "primaryKey": {
+          "autoGenerate": false,
+          "columnNames": [
+            "rideId",
+            "seq"
+          ]
+        },
+        "foreignKeys": [
+          {
+            "table": "rides",
+            "onDelete": "CASCADE",
+            "onUpdate": "NO ACTION",
+            "columns": [
+              "rideId"
+            ],
+            "referencedColumns": [
+              "id"
+            ]
+          }
+        ]
+      },
+      {
+        "tableName": "route_points",
+        "createSql": "CREATE TABLE IF NOT EXISTS `${TABLE_NAME}` (`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, `rideId` TEXT NOT NULL, `segment` INTEGER NOT NULL, `t` INTEGER NOT NULL, `lat` REAL NOT NULL, `lon` REAL NOT NULL, `accuracy` REAL, `chunk` INTEGER, `refused` INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(`rideId`) REFERENCES `rides`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE )",
+        "fields": [
+          {
+            "fieldPath": "id",
+            "columnName": "id",
+            "affinity": "INTEGER",
+            "notNull": true
+          },
+          {
+            "fieldPath": "rideId",
+            "columnName": "rideId",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "segment",
+            "columnName": "segment",
+            "affinity": "INTEGER",
+            "notNull": true
+          },
+          {
+            "fieldPath": "t",
+            "columnName": "t",
+            "affinity": "INTEGER",
+            "notNull": true
+          },
+          {
+            "fieldPath": "lat",
+            "columnName": "lat",
+            "affinity": "REAL",
+            "notNull": true
+          },
+          {
+            "fieldPath": "lon",
+            "columnName": "lon",
+            "affinity": "REAL",
+            "notNull": true
+          },
+          {
+            "fieldPath": "accuracy",
+            "columnName": "accuracy",
+            "affinity": "REAL"
+          },
+          {
+            "fieldPath": "chunk",
+            "columnName": "chunk",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "refused",
+            "columnName": "refused",
+            "affinity": "INTEGER",
+            "notNull": true,
+            "defaultValue": "0"
+          }
+        ],
+        "primaryKey": {
+          "autoGenerate": true,
+          "columnNames": [
+            "id"
+          ]
+        },
+        "indices": [
+          {
+            "name": "index_route_points_rideId_segment_t",
+            "unique": false,
+            "columnNames": [
+              "rideId",
+              "segment",
+              "t"
+            ],
+            "orders": [],
+            "createSql": "CREATE INDEX IF NOT EXISTS `index_route_points_rideId_segment_t` ON `${TABLE_NAME}` (`rideId`, `segment`, `t`)"
+          },
+          {
+            "name": "index_route_points_chunk_rideId",
+            "unique": false,
+            "columnNames": [
+              "chunk",
+              "rideId"
+            ],
+            "orders": [],
+            "createSql": "CREATE INDEX IF NOT EXISTS `index_route_points_chunk_rideId` ON `${TABLE_NAME}` (`chunk`, `rideId`)"
+          },
+          {
+            "name": "index_route_points_refused_rideId",
+            "unique": false,
+            "columnNames": [
+              "refused",
+              "rideId"
+            ],
+            "orders": [],
+            "createSql": "CREATE INDEX IF NOT EXISTS `index_route_points_refused_rideId` ON `${TABLE_NAME}` (`refused`, `rideId`)"
+          }
+        ],
+        "foreignKeys": [
+          {
+            "table": "rides",
+            "onDelete": "CASCADE",
+            "onUpdate": "NO ACTION",
+            "columns": [
+              "rideId"
+            ],
+            "referencedColumns": [
+              "id"
+            ]
+          }
+        ]
+      },
+      {
+        "tableName": "asks",
+        "createSql": "CREATE TABLE IF NOT EXISTS `${TABLE_NAME}` (`askId` TEXT NOT NULL, `askedAt` INTEGER NOT NULL, `answeredAt` INTEGER, `transcript` TEXT, `answer` TEXT, `latitude` REAL, `longitude` REAL, `address` TEXT, `headingDegrees` REAL, `input` TEXT NOT NULL, `conversationId` TEXT NOT NULL, `newConversation` INTEGER NOT NULL, `status` TEXT NOT NULL, `failure` TEXT, `rideId` TEXT, `memo` TEXT, `memoUpdatedAt` INTEGER, `memoSentUpdatedAt` INTEGER, `memoRejectedUpdatedAt` INTEGER, PRIMARY KEY(`askId`))",
+        "fields": [
+          {
+            "fieldPath": "askId",
+            "columnName": "askId",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "askedAt",
+            "columnName": "askedAt",
+            "affinity": "INTEGER",
+            "notNull": true
+          },
+          {
+            "fieldPath": "answeredAt",
+            "columnName": "answeredAt",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "transcript",
+            "columnName": "transcript",
+            "affinity": "TEXT"
+          },
+          {
+            "fieldPath": "answer",
+            "columnName": "answer",
+            "affinity": "TEXT"
+          },
+          {
+            "fieldPath": "latitude",
+            "columnName": "latitude",
+            "affinity": "REAL"
+          },
+          {
+            "fieldPath": "longitude",
+            "columnName": "longitude",
+            "affinity": "REAL"
+          },
+          {
+            "fieldPath": "address",
+            "columnName": "address",
+            "affinity": "TEXT"
+          },
+          {
+            "fieldPath": "headingDegrees",
+            "columnName": "headingDegrees",
+            "affinity": "REAL"
+          },
+          {
+            "fieldPath": "input",
+            "columnName": "input",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "conversationId",
+            "columnName": "conversationId",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "newConversation",
+            "columnName": "newConversation",
+            "affinity": "INTEGER",
+            "notNull": true
+          },
+          {
+            "fieldPath": "status",
+            "columnName": "status",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "failure",
+            "columnName": "failure",
+            "affinity": "TEXT"
+          },
+          {
+            "fieldPath": "rideId",
+            "columnName": "rideId",
+            "affinity": "TEXT"
+          },
+          {
+            "fieldPath": "memo",
+            "columnName": "memo",
+            "affinity": "TEXT"
+          },
+          {
+            "fieldPath": "memoUpdatedAt",
+            "columnName": "memoUpdatedAt",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "memoSentUpdatedAt",
+            "columnName": "memoSentUpdatedAt",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "memoRejectedUpdatedAt",
+            "columnName": "memoRejectedUpdatedAt",
+            "affinity": "INTEGER"
+          }
+        ],
+        "primaryKey": {
+          "autoGenerate": false,
+          "columnNames": [
+            "askId"
+          ]
+        },
+        "indices": [
+          {
+            "name": "index_asks_rideId",
+            "unique": false,
+            "columnNames": [
+              "rideId"
+            ],
+            "orders": [],
+            "createSql": "CREATE INDEX IF NOT EXISTS `index_asks_rideId` ON `${TABLE_NAME}` (`rideId`)"
+          },
+          {
+            "name": "index_asks_askedAt",
+            "unique": false,
+            "columnNames": [
+              "askedAt"
+            ],
+            "orders": [],
+            "createSql": "CREATE INDEX IF NOT EXISTS `index_asks_askedAt` ON `${TABLE_NAME}` (`askedAt`)"
+          }
+        ]
+      },
+      {
+        "tableName": "notes",
+        "createSql": "CREATE TABLE IF NOT EXISTS `${TABLE_NAME}` (`id` TEXT NOT NULL, `rideId` TEXT NOT NULL, `at` INTEGER NOT NULL, `latitude` REAL, `longitude` REAL, `sampleLatitude` REAL, `sampleLongitude` REAL, `sampleAt` INTEGER, `text` TEXT NOT NULL, `updatedAt` INTEGER NOT NULL, `sentUpdatedAt` INTEGER, `rejectedUpdatedAt` INTEGER, `address` TEXT, `headingDegrees` REAL, PRIMARY KEY(`id`), FOREIGN KEY(`rideId`) REFERENCES `rides`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE )",
+        "fields": [
+          {
+            "fieldPath": "id",
+            "columnName": "id",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "rideId",
+            "columnName": "rideId",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "at",
+            "columnName": "at",
+            "affinity": "INTEGER",
+            "notNull": true
+          },
+          {
+            "fieldPath": "latitude",
+            "columnName": "latitude",
+            "affinity": "REAL"
+          },
+          {
+            "fieldPath": "longitude",
+            "columnName": "longitude",
+            "affinity": "REAL"
+          },
+          {
+            "fieldPath": "sampleLatitude",
+            "columnName": "sampleLatitude",
+            "affinity": "REAL"
+          },
+          {
+            "fieldPath": "sampleLongitude",
+            "columnName": "sampleLongitude",
+            "affinity": "REAL"
+          },
+          {
+            "fieldPath": "sampleAt",
+            "columnName": "sampleAt",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "text",
+            "columnName": "text",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "updatedAt",
+            "columnName": "updatedAt",
+            "affinity": "INTEGER",
+            "notNull": true
+          },
+          {
+            "fieldPath": "sentUpdatedAt",
+            "columnName": "sentUpdatedAt",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "rejectedUpdatedAt",
+            "columnName": "rejectedUpdatedAt",
+            "affinity": "INTEGER"
+          },
+          {
+            "fieldPath": "address",
+            "columnName": "address",
+            "affinity": "TEXT"
+          },
+          {
+            "fieldPath": "headingDegrees",
+            "columnName": "headingDegrees",
+            "affinity": "REAL"
+          }
+        ],
+        "primaryKey": {
+          "autoGenerate": false,
+          "columnNames": [
+            "id"
+          ]
+        },
+        "indices": [
+          {
+            "name": "index_notes_rideId",
+            "unique": false,
+            "columnNames": [
+              "rideId"
+            ],
+            "orders": [],
+            "createSql": "CREATE INDEX IF NOT EXISTS `index_notes_rideId` ON `${TABLE_NAME}` (`rideId`)"
+          }
+        ],
+        "foreignKeys": [
+          {
+            "table": "rides",
+            "onDelete": "CASCADE",
+            "onUpdate": "NO ACTION",
+            "columns": [
+              "rideId"
+            ],
+            "referencedColumns": [
+              "id"
+            ]
+          }
+        ]
+      },
+      {
+        "tableName": "deletions",
+        "createSql": "CREATE TABLE IF NOT EXISTS `${TABLE_NAME}` (`kind` TEXT NOT NULL, `id` TEXT NOT NULL, `rideId` TEXT, `deletedAt` INTEGER NOT NULL, PRIMARY KEY(`kind`, `id`))",
+        "fields": [
+          {
+            "fieldPath": "kind",
+            "columnName": "kind",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "id",
+            "columnName": "id",
+            "affinity": "TEXT",
+            "notNull": true
+          },
+          {
+            "fieldPath": "rideId",
+            "columnName": "rideId",
+            "affinity": "TEXT"
+          },
+          {
+            "fieldPath": "deletedAt",
+            "columnName": "deletedAt",
+            "affinity": "INTEGER",
+            "notNull": true
+          }
+        ],
+        "primaryKey": {
+          "autoGenerate": false,
+          "columnNames": [
+            "kind",
+            "id"
+          ]
+        }
+      }
+    ],
+    "setupQueries": [
+      "CREATE TABLE IF NOT EXISTS room_master_table (id INTEGER PRIMARY KEY,identity_hash TEXT)",
+      "INSERT OR REPLACE INTO room_master_table (id,identity_hash) VALUES(42, '4194cefd7bb25db361d2002586ce23e4')"
+    ]
+  }
+}
\ No newline at end of file
diff --git a/app/src/main/java/com/touringproject/v2/ride/Ride.kt b/app/src/main/java/com/touringproject/v2/ride/Ride.kt
index 034af88..8ea414f 100644
--- a/app/src/main/java/com/touringproject/v2/ride/Ride.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/Ride.kt
@@ -33,6 +33,8 @@ data class Ride(
   val lastAliveAt: Long?,
   val distanceMeters: Double,
   val updatedAt: Long,
+  /** The ride's memo (US-D-04.002); null when there is none. */
+  val memo: String? = null,
 )
 
 /** One stored route point. segment is the seq of the segment it was recorded in. */
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index dea6b9a..36cfc3d 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -45,6 +45,8 @@ data class RideEntity(
    * segments and points refer to.
    */
   @ColumnInfo(defaultValue = "0") val routeRejected: Boolean = false,
+  /** The ride's memo (US-D-04.002); null when there is none. Part of the meta that is sent (slice 3 spec §4.1). */
+  val memo: String? = null,
 )
 
 @Entity(
@@ -102,8 +104,47 @@ data class AskEntity(
    * missing for a while after a failed save.
    */
   val rideId: String?,
+  /** The conversation's memo (US-D-04.001); null when there is none. */
+  val memo: String? = null,
+  /** When the memo last changed; null while it has never had one. */
+  val memoUpdatedAt: Long? = null,
+  /** The memoUpdatedAt the Backend last accepted; null until then. */
+  val memoSentUpdatedAt: Long? = null,
+  /** The memoUpdatedAt the Backend refused (400 or 404); that version is not sent again (slice 3 spec §5.2). */
+  val memoRejectedUpdatedAt: Long? = null,
 )
 
+/**
+ * A point memo (slice 3 spec §4.1, US-D-08). Written while its ride records or is paused, and gone with the ride. The
+ * place it was written at is null when the ride had no point yet; the sample is the older point the Backend takes the
+ * heading from. address and headingDegrees are what the Backend answered; null until it has.
+ */
+@Entity(
+  tableName = "notes",
+  indices = [Index(value = ["rideId"])],
+  foreignKeys = [ForeignKey(entity = RideEntity::class, parentColumns = ["id"], childColumns = ["rideId"], onDelete = ForeignKey.CASCADE)],
+)
+data class NoteEntity(
+  @PrimaryKey val id: String,
+  val rideId: String,
+  val at: Long,
+  val latitude: Double?,
+  val longitude: Double?,
+  val sampleLatitude: Double?,
+  val sampleLongitude: Double?,
+  val sampleAt: Long?,
+  val text: String,
+  val updatedAt: Long,
+  val sentUpdatedAt: Long?,
+  val rejectedUpdatedAt: Long?,
+  val address: String?,
+  val headingDegrees: Double?,
+)
+
+/** A record deleted on the device whose deletion has not reached the Backend yet (slice 3 spec §4.2). kind: ask / ride / note. */
+@Entity(tableName = "deletions", primaryKeys = ["kind", "id"])
+data class DeletionEntity(val kind: String, val id: String, val rideId: String?, val deletedAt: Long)
+
 @Dao
 interface AskDao {
   @Upsert
@@ -232,14 +273,18 @@ interface RideDao {
   }
 }
 
-@Database(entities = [RideEntity::class, SegmentEntity::class, RoutePointEntity::class, AskEntity::class], version = 4, exportSchema = true)
+@Database(
+  entities = [RideEntity::class, SegmentEntity::class, RoutePointEntity::class, AskEntity::class, NoteEntity::class, DeletionEntity::class],
+  version = 5,
+  exportSchema = true,
+)
 abstract class RideDatabase : RoomDatabase() {
   abstract fun rides(): RideDao
   abstract fun asks(): AskDao
 
   companion object {
     fun open(context: Context): RideDatabase =
-      Room.databaseBuilder(context, RideDatabase::class.java, "rides.db").addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4).build()
+      Room.databaseBuilder(context, RideDatabase::class.java, "rides.db").addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5).build()
   }
 }
 
@@ -286,3 +331,28 @@ val MIGRATION_3_4 = object : Migration(3, 4) {
     db.execSQL("DELETE FROM `asks` WHERE `rideId` IS NULL")
   }
 }
+
+/**
+ * 4 -> 5 (slice 3 spec §4.1): memos on rides and asks, the point memos and the deletions waiting to be sent. It only
+ * adds, like 1 -> 2, so it stays quick inside RideController.load() (adr/0006).
+ */
+val MIGRATION_4_5 = object : Migration(4, 5) {
+  override fun migrate(db: SupportSQLiteDatabase) {
+    db.execSQL("ALTER TABLE `rides` ADD COLUMN `memo` TEXT")
+    db.execSQL("ALTER TABLE `asks` ADD COLUMN `memo` TEXT")
+    db.execSQL("ALTER TABLE `asks` ADD COLUMN `memoUpdatedAt` INTEGER")
+    db.execSQL("ALTER TABLE `asks` ADD COLUMN `memoSentUpdatedAt` INTEGER")
+    db.execSQL("ALTER TABLE `asks` ADD COLUMN `memoRejectedUpdatedAt` INTEGER")
+    db.execSQL(
+      "CREATE TABLE IF NOT EXISTS `notes` (`id` TEXT NOT NULL, `rideId` TEXT NOT NULL, `at` INTEGER NOT NULL, `latitude` REAL, " +
+        "`longitude` REAL, `sampleLatitude` REAL, `sampleLongitude` REAL, `sampleAt` INTEGER, `text` TEXT NOT NULL, " +
+        "`updatedAt` INTEGER NOT NULL, `sentUpdatedAt` INTEGER, `rejectedUpdatedAt` INTEGER, `address` TEXT, `headingDegrees` REAL, " +
+        "PRIMARY KEY(`id`), FOREIGN KEY(`rideId`) REFERENCES `rides`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE )",
+    )
+    db.execSQL("CREATE INDEX IF NOT EXISTS `index_notes_rideId` ON `notes` (`rideId`)")
+    db.execSQL(
+      "CREATE TABLE IF NOT EXISTS `deletions` (`kind` TEXT NOT NULL, `id` TEXT NOT NULL, `rideId` TEXT, `deletedAt` INTEGER NOT NULL, " +
+        "PRIMARY KEY(`kind`, `id`))",
+    )
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt b/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt
index 89b5d6a..cb95137 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt
@@ -10,7 +10,7 @@ import com.touringproject.v2.ride.Segment
 private fun RideStatus.column() = name.lowercase()
 private fun EndReason.column() = name.lowercase()
 
-fun Ride.toEntity() = RideEntity(id, name, status.column(), endReason?.column(), deadline, lastAliveAt, distanceMeters, updatedAt, null)
+fun Ride.toEntity() = RideEntity(id, name, status.column(), endReason?.column(), deadline, lastAliveAt, distanceMeters, updatedAt, null, memo = memo)
 
 fun RideEntity.toRide(segments: List<SegmentEntity>) = Ride(
   id = id,
@@ -22,6 +22,7 @@ fun RideEntity.toRide(segments: List<SegmentEntity>) = Ride(
   lastAliveAt = lastAliveAt,
   distanceMeters = distanceMeters,
   updatedAt = updatedAt,
+  memo = memo,
 )
 
 fun RoutePointEntity.toPoint() = RoutePoint(segment, t, lat, lon, accuracy)
PATCH
````

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t1.log 2>&1; tail -1 /tmp/trv2-t1.log`
Expected: `BUILD SUCCESSFUL`（`383` 件（381＋2）。数は Task 8 の数え方で見る）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/schemas/com.touringproject.v2.store.RideDatabase/5.json app/src/main/java/com/touringproject/v2/ride/Ride.kt app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt app/src/test/java/com/touringproject/v2/store/MigrationTest.kt app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt
git commit -m "feat: add memos, point memos and pending deletions to the device's records (Room version 5)"
```

---

### Task 2: メモを書く・消す、会話と終えた走行を消す

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Create: `records/Memos.kt`・`records/AskEdits.kt`・`store/RoomAskEdits.kt`
- Modify: `ride/Ride.kt`・`ride/RideController.kt`・`ride/RidePorts.kt`・`store/RideDatabase.kt`・`store/RoomRideStore.kt`
- Test: `records/MemosTest.kt`（新規）・`store/RoomAskEditsTest.kt`（新規）・`ride/RideControllerTest.kt`・`ride/RideTest.kt`・`store/RoomRideStoreTest.kt`・`store/RoomAskLogTest.kt`（作り物の DAO）

**Interfaces:**
- Consumes: Task 1 の `DeletionEntity`・`AskEntity` のメモの列・`Ride.memo`
- Produces:
  - `records.MEMO_MAX = 2000`・`memoText(input: String): String?`・`cutMemo(input: String): String`・`memoFits(memo: String?): Boolean`・`memoTime(now: Long, previous: Long?): Long`
  - `records.AskEdits { suspend fun memo(askId: String, memo: String?): Boolean; suspend fun delete(askId: String): Boolean }`
  - `store.RoomAskEdits(dao: AskDao, now: () -> Long, changed: () -> Unit, log: (String, Throwable) -> Unit) : AskEdits`
  - `Ride.withMemo(memo: String?, now: Long): Ride`
  - `RideController.memo(rideId: String, memo: String?): Boolean`・`RideController.delete(rideId: String): Boolean`
  - `RideStore.delete(rideId: String, at: Long): Boolean`（`RoomRideStore` は `RideDao.deleteEnded`）
  - `AskDao.writeMemo(askId, memo, now): Boolean`・`AskDao.delete(askId, at): Boolean`（どちらも `@Transaction`）・`setMemo`・`deleteRow`・`markDeleted`
  - `RideDao.deleteEnded(rideId, at): Boolean`（`@Transaction`）・`deleteAsks`・`deleteNotes`・`deletePoints`・`deleteRideRow`・`markDeleted`

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/records/MemosTest.kt b/app/src/test/java/com/touringproject/v2/records/MemosTest.kt
new file mode 100644
index 0000000..26e1c12
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/records/MemosTest.kt
@@ -0,0 +1,36 @@
+package com.touringproject.v2.records
+
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertFalse
+import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
+import org.junit.Test
+
+class MemosTest {
+  @Test
+  fun a_memo_is_trimmed_and_a_blank_one_is_none() {
+    assertEquals("また来たい", memoText("  また来たい\n"))
+    assertNull(memoText(" \n "))
+  }
+
+  @Test
+  fun the_field_keeps_2000_characters_counting_an_emoji_as_one() {
+    assertEquals(2000, cutMemo("😀".repeat(2001)).codePointCount(0, cutMemo("😀".repeat(2001)).length))
+    assertEquals("😀".repeat(2000), cutMemo("😀".repeat(2000)))
+    assertEquals("あ".repeat(2000), cutMemo("あ".repeat(2500)))
+  }
+
+  @Test
+  fun a_memo_fits_up_to_2000_characters() {
+    assertTrue(memoFits(null))
+    assertTrue(memoFits("😀".repeat(2000)))
+    assertFalse(memoFits("あ".repeat(2001)))
+  }
+
+  @Test
+  fun a_memo_change_is_always_after_the_one_before() {
+    assertEquals(5_000L, memoTime(5_000, null))
+    assertEquals(5_000L, memoTime(5_000, 4_000))
+    assertEquals(9_001L, memoTime(5_000, 9_000))
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
index 94d92f9..14bdcea 100644
--- a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
@@ -28,6 +28,8 @@ private class World(var now: Long = 1_000, var boot: Int? = 7) {
   var gate: CompletableDeferred<Unit>? = null
   val events = mutableListOf<String>()
   val autoEnded = mutableListOf<Ride>()
+  val deleted = mutableListOf<String>()
+  var failDeletes = false
   var changes = 0
   /** The longest recording time the rider has chosen (SC-16). */
   var max = MAX
@@ -64,6 +66,14 @@ private class World(var now: Long = 1_000, var boot: Int? = 7) {
       if (failWrites) throw IOException("disk full")
       rides[rideId]?.let { rides[rideId] = it.copy(lastAliveAt = at) }
     }
+    override suspend fun delete(rideId: String, at: Long): Boolean {
+      if (failDeletes) throw IOException("disk full")
+      if (rides[rideId]?.status != RideStatus.ENDED) return false
+      rides.remove(rideId)
+      points.remove(rideId)
+      deleted += rideId
+      return true
+    }
   }
 
   val controller = RideController(
@@ -628,4 +638,114 @@ class RideControllerTest {
     assertFalse(w.controller.rename("r1", "御殿場"))
     assertEquals("御殿場", w.controller.active.value?.name)
   }
+
+  // Slice 3 spec §7.2: the memo goes with the ride's meta, so a new one is sent.
+  @Test
+  fun an_ended_rides_memo_is_saved_and_sent() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    w.controller.end("箱根")
+    val changes = w.changes
+    w.now = 9_000
+    assertTrue(w.controller.memo("r1", "また来たい"))
+    assertEquals("また来たい", w.stored().memo)
+    assertEquals(9_000L, w.stored().updatedAt)
+    assertEquals(changes + 1, w.changes)
+    assertTrue(w.controller.memo("r1", null))
+    assertNull(w.stored().memo)
+  }
+
+  @Test
+  fun the_active_rides_memo_changes_only_its_memo() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    assertTrue(w.controller.memo("r1", "峠の手前で給油"))
+    assertEquals("峠の手前で給油", w.controller.active.value?.memo)
+    assertEquals(RideStatus.RECORDING, w.stored().status)
+    assertEquals("峠の手前で給油", w.stored().memo)
+  }
+
+  @Test
+  fun the_same_memo_again_saves_nothing_and_a_memo_too_long_or_of_no_ride_is_refused() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.controller.memo("r1", "同じ")
+    val changes = w.changes
+    assertTrue(w.controller.memo("r1", "同じ"))
+    assertEquals(changes, w.changes)
+    assertFalse(w.controller.memo("r1", "あ".repeat(2001)))
+    assertFalse(w.controller.memo("r9", "どこ"))
+    assertEquals("同じ", w.stored().memo)
+  }
+
+  @Test
+  fun a_memo_whose_save_fails_reports_it() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    w.controller.end("箱根")
+    w.failSaves = 1
+    assertFalse(w.controller.memo("r1", "書けない"))
+    assertNull(w.stored().memo)
+  }
+
+  // US-D-06.002: an ended ride goes with everything of it, and the deletion is something new to send.
+  @Test
+  fun an_ended_ride_can_be_deleted() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    w.controller.end("箱根")
+    val changes = w.changes
+    assertTrue(w.controller.delete("r1"))
+    assertEquals(listOf("r1"), w.deleted)
+    assertTrue(w.rides.isEmpty())
+    assertEquals(changes + 1, w.changes)
+  }
+
+  // Slice 3 spec §2: the ride recording or paused is ended first.
+  @Test
+  fun the_ride_recording_or_paused_cannot_be_deleted() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    assertFalse(w.controller.delete("r1"))
+    w.controller.pause()
+    assertFalse(w.controller.delete("r1"))
+    assertFalse(w.controller.delete("r9"))
+    assertTrue(w.deleted.isEmpty())
+  }
+
+  @Test
+  fun a_deletion_that_fails_is_reported() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.controller.end("箱根")
+    w.failDeletes = true
+    assertFalse(w.controller.delete("r1"))
+    assertEquals(1, w.rides.size)
+  }
+
+  // A rename that could not be written waits to be written again; deleting the ride drops it, so it does not come back.
+  @Test
+  fun a_deleted_ride_is_not_written_back_by_a_save_still_waiting() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    w.controller.end("箱根")
+    w.failSaves = 1
+    assertFalse(w.controller.rename("r1", "御殿場"))
+    assertTrue(w.controller.delete("r1"))
+    w.controller.start("次の走行")
+    assertEquals(listOf("次の走行"), w.rides.values.map { it.name })
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ride/RideTest.kt b/app/src/test/java/com/touringproject/v2/ride/RideTest.kt
index 4d5a617..439dd9d 100644
--- a/app/src/test/java/com/touringproject/v2/ride/RideTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ride/RideTest.kt
@@ -130,4 +130,12 @@ class ReconcileTest {
     assertEquals(Reconcile.KeepPaused, reconcile(recording.pause(90_000), 120_000, 7))
     assertEquals(Reconcile.Resume, reconcile(recording, 120_000, null))
   }
+
+  @Test
+  fun a_memo_moves_updated_at_on_even_with_the_clock_set_back() {
+    val ended = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(5_000, EndReason.MANUAL, 5_000)
+    val memo = ended.withMemo("また来たい", 3_000)
+    assertEquals("また来たい", memo.memo)
+    assertEquals(5_001L, memo.updatedAt)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomAskEditsTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomAskEditsTest.kt
new file mode 100644
index 0000000..e1ba52d
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/store/RoomAskEditsTest.kt
@@ -0,0 +1,99 @@
+package com.touringproject.v2.store
+
+import android.app.Application
+import androidx.room.Room
+import androidx.test.core.app.ApplicationProvider
+import androidx.test.ext.junit.runners.AndroidJUnit4
+import kotlinx.coroutines.runBlocking
+import org.junit.After
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertFalse
+import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
+import org.junit.Test
+import org.junit.runner.RunWith
+
+@RunWith(AndroidJUnit4::class)
+class RoomAskEditsTest {
+  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
+    .allowMainThreadQueries()
+    .build()
+  private var now = 5_000L
+  private var changes = 0
+  private val errors = mutableListOf<String>()
+  private val edits = RoomAskEdits(db.asks(), { now }, { changes += 1 }) { message, _ -> errors += message }
+
+  private fun keep(askId: String = "a1", rideId: String = "r1") = runBlocking {
+    db.asks().upsert(AskEntity(askId, 1_000, 2_000, "Q", "A", 35.0, 139.0, null, null, "voice", "c1", true, "answered", null, rideId))
+  }
+
+  private fun deletions(): List<DeletionEntity> = db.query("SELECT * FROM deletions", null).use { c ->
+    buildList { while (c.moveToNext()) add(DeletionEntity(c.getString(0), c.getString(1), c.getString(2), c.getLong(3))) }
+  }
+
+  @After
+  fun close() = db.close()
+
+  @Test
+  fun a_memo_is_kept_with_when_it_changed_and_is_something_to_send() = runBlocking {
+    keep()
+    assertTrue(edits.memo("a1", "また来たい"))
+    val ask = db.asks().ask("a1")!!
+    assertEquals("また来たい", ask.memo)
+    assertEquals(5_000L, ask.memoUpdatedAt)
+    assertEquals(1, changes)
+  }
+
+  // The Backend keeps only a newer memo, so a change made with the clock set back still comes after (slice 3 spec §6.2).
+  @Test
+  fun each_change_of_the_memo_is_later_than_the_one_before() = runBlocking {
+    keep()
+    edits.memo("a1", "一つ目")
+    now = 3_000
+    edits.memo("a1", null)
+    val ask = db.asks().ask("a1")!!
+    assertNull(ask.memo)
+    assertEquals(5_001L, ask.memoUpdatedAt)
+  }
+
+  @Test
+  fun the_same_memo_again_does_not_change_when_it_changed() = runBlocking {
+    keep()
+    edits.memo("a1", "同じ")
+    now = 9_000
+    assertTrue(edits.memo("a1", "同じ"))
+    assertEquals(5_000L, db.asks().ask("a1")?.memoUpdatedAt)
+  }
+
+  @Test
+  fun a_memo_for_an_ask_not_kept_or_too_long_is_refused() = runBlocking {
+    keep()
+    assertFalse(edits.memo("a9", "どこ"))
+    assertFalse(edits.memo("a1", "あ".repeat(2001)))
+    assertNull(db.asks().ask("a1")?.memo)
+    assertEquals(0, changes)
+  }
+
+  @Test
+  fun deleting_an_ask_marks_it_with_its_ride() = runBlocking {
+    keep()
+    keep("a2")
+    assertTrue(edits.delete("a1"))
+    assertNull(db.asks().ask("a1"))
+    assertEquals("a2", db.asks().ask("a2")?.askId)
+    assertEquals(listOf(DeletionEntity("ask", "a1", "r1", 5_000)), deletions())
+    assertEquals(1, changes)
+    assertFalse(edits.delete("a1"))
+  }
+
+  // Slice 3 spec §8: a write that fails is reported, so SC-08 keeps what was typed.
+  @Test
+  fun a_write_that_fails_is_logged_and_reported() = runBlocking {
+    keep()
+    db.close()
+    assertFalse(edits.memo("a1", "書けない"))
+    assertFalse(edits.delete("a1"))
+    assertEquals(2, errors.size)
+    assertEquals(0, changes)
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
index ef06a34..93258c6 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
@@ -58,6 +58,9 @@ class RoomAskLogTest {
       override suspend fun ask(askId: String): AskEntity? = null
       override fun countForRide(rideId: String) = kotlinx.coroutines.flow.flowOf(0)
       override fun forRide(rideId: String) = kotlinx.coroutines.flow.flowOf(emptyList<AskEntity>())
+      override suspend fun setMemo(askId: String, memo: String?, at: Long) = error("not used")
+      override suspend fun deleteRow(askId: String) = error("not used")
+      override suspend fun markDeleted(deletion: DeletionEntity) = error("not used")
     }
     val failing = RoomAskLog(dao, kotlinx.coroutines.MainScope()) { message, _ -> errors += message }
     failing.save(record)
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt
index 328e555..c88f2c3 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt
@@ -15,6 +15,7 @@ import com.touringproject.v2.ride.resume
 import kotlinx.coroutines.runBlocking
 import org.junit.After
 import org.junit.Assert.assertEquals
+import org.junit.Assert.assertFalse
 import org.junit.Assert.assertNull
 import org.junit.Assert.assertTrue
 import org.junit.Test
@@ -82,4 +83,31 @@ class RoomRideStoreTest {
     store.save(ended.copy(memo = null, updatedAt = 6_000))
     assertNull(store.ride("r1")?.memo)
   }
+
+  // Slice 3 spec §4.2: the ride goes with its segments, points and asks, and its deletion waits to be sent.
+  @Test
+  fun deleting_an_ended_ride_removes_all_of_it_and_marks_it() = runBlocking {
+    val ended = ride.end(5_000, EndReason.MANUAL, 5_000)
+    store.save(ended)
+    store.addPoint("r1", RoutePoint(0, 2_000, 35.0, 139.0, 5.0), 0.0, 2_000)
+    db.asks().upsert(AskEntity("a1", 2_000, 3_000, "Q", "A", 35.0, 139.0, null, null, "voice", "c1", true, "answered", null, "r1"))
+    db.asks().upsert(AskEntity("a2", 2_000, 3_000, "Q", "A", 35.0, 139.0, null, null, "voice", "c1", true, "answered", null, "r2"))
+    assertTrue(store.delete("r1", 9_000))
+    assertNull(store.ride("r1"))
+    assertTrue(dao.points("r1").isEmpty())
+    assertTrue(dao.segments("r1").isEmpty())
+    assertNull(db.asks().ask("a1"))
+    assertEquals("r2", db.asks().ask("a2")?.rideId)
+    assertEquals(listOf(DeletionEntity("ride", "r1", null, 9_000)), db.query("SELECT * FROM deletions", null).use { c ->
+      buildList { while (c.moveToNext()) add(DeletionEntity(c.getString(0), c.getString(1), c.getString(2), c.getLong(3))) }
+    })
+  }
+
+  @Test
+  fun a_ride_still_recording_or_not_kept_is_not_deleted() = runBlocking {
+    store.save(ride)
+    assertFalse(store.delete("r1", 9_000))
+    assertFalse(store.delete("r9", 9_000))
+    assertEquals(ride, store.ride("r1"))
+  }
 }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*MemosTest' --tests '*RideControllerTest' --tests '*RideTest' --tests '*RoomRideStoreTest' --tests '*RoomAskEditsTest' --tests '*RoomAskLogTest' --rerun > /tmp/trv2-t2.log 2>&1; grep -c '^e:' /tmp/trv2-t2.log`
Expected: コンパイルで落ちる（`memoText`・`withMemo`・`RoomAskEdits` などが無い）

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/records/AskEdits.kt b/app/src/main/java/com/touringproject/v2/records/AskEdits.kt
new file mode 100644
index 0000000..5cc6bda
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/records/AskEdits.kt
@@ -0,0 +1,9 @@
+package com.touringproject.v2.records
+
+/** What SC-07 and SC-08 change of a kept ask (US-D-04.001, US-D-06.001). Each returns false when nothing was written. */
+interface AskEdits {
+  /** memo is the cleaned memo (memoText), or null to remove it. */
+  suspend fun memo(askId: String, memo: String?): Boolean
+  /** Removes the ask and marks it to be deleted on the Backend too (slice 3 spec §4.2). */
+  suspend fun delete(askId: String): Boolean
+}
diff --git a/app/src/main/java/com/touringproject/v2/records/Memos.kt b/app/src/main/java/com/touringproject/v2/records/Memos.kt
new file mode 100644
index 0000000..ef16180
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/records/Memos.kt
@@ -0,0 +1,25 @@
+package com.touringproject.v2.records
+
+// Memos on rides and asks (US-D-04, SC-08). Characters are counted as code points, as the Backend counts them, so an
+// emoji is never cut in half (Backend #16).
+
+/** US-D-04.003. */
+const val MEMO_MAX = 2000
+
+private fun String.characters() = codePointCount(0, length)
+
+/** The memo a typed text keeps: trimmed, and none when it is blank (SC-08: saving an empty memo removes it). */
+fun memoText(input: String): String? = input.trim().ifEmpty { null }
+
+/** What the memo field keeps of a typed or pasted text: its first 2000 characters. */
+fun cutMemo(input: String): String =
+  if (input.characters() <= MEMO_MAX) input else input.substring(0, input.offsetByCodePoints(0, MEMO_MAX))
+
+/** True when memo can be kept: none, or up to MEMO_MAX characters. */
+fun memoFits(memo: String?): Boolean = memo == null || memo.characters() <= MEMO_MAX
+
+/**
+ * When a memo changes: now, but always after the change before it, so the Backend, which keeps only a newer version,
+ * takes it even when the device's clock has been set back.
+ */
+fun memoTime(now: Long, previous: Long?): Long = if (previous == null) now else maxOf(now, previous + 1)
diff --git a/app/src/main/java/com/touringproject/v2/ride/Ride.kt b/app/src/main/java/com/touringproject/v2/ride/Ride.kt
index 8ea414f..4eba965 100644
--- a/app/src/main/java/com/touringproject/v2/ride/Ride.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/Ride.kt
@@ -95,6 +95,9 @@ fun Ride.end(at: Long, reason: EndReason, now: Long, name: String = this.name):
 /** SC-04 and SC-06: a new name is a change the Backend takes, so updatedAt moves on. */
 fun Ride.rename(name: String, now: Long): Ride = copy(name = name, updatedAt = touched(now))
 
+/** SC-08: the memo goes with the ride's meta, so updatedAt moves on too (slice 3 spec §4.1). */
+fun Ride.withMemo(memo: String?, now: Long): Ride = copy(memo = memo, updatedAt = touched(now))
+
 /** The time spent recording; an open segment counts up to now (US-C-07.006). */
 fun Ride.recordedMs(now: Long): Long = segments.sumOf { (it.endedAt ?: maxOf(now, it.startedAt)) - it.startedAt }
 
diff --git a/app/src/main/java/com/touringproject/v2/ride/RideController.kt b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
index 8b3831c..3c8636f 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RideController.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
@@ -2,6 +2,7 @@ package com.touringproject.v2.ride
 
 import com.touringproject.v2.location.Fix
 import com.touringproject.v2.location.acceptRoutePoint
+import com.touringproject.v2.records.memoFits
 import kotlinx.coroutines.CancellationException
 import kotlinx.coroutines.CompletableDeferred
 import kotlinx.coroutines.NonCancellable
@@ -210,6 +211,39 @@ class RideController(private val deps: RideDeps) {
     save(ride.rename(clean, now))
   }
 
+  /**
+   * SC-08 (and SC-02's 走行メモ): sets or, for null, removes any kept ride's memo. Returns false when the memo is too
+   * long, the ride is not kept, or the memo could not be written now. The same memo again changes nothing.
+   */
+  suspend fun memo(rideId: String, memo: String?): Boolean = locked {
+    if (!memoFits(memo)) return@locked false
+    val now = deps.now()
+    val active = activeRide.value
+    if (active?.id == rideId) {
+      if (active.memo == memo) return@locked true
+      val changed = active.withMemo(memo, now)
+      val saved = save(changed)
+      activeRide.value = changed
+      return@locked saved
+    }
+    val ride = read("ride") { deps.store.ride(rideId) } ?: return@locked false
+    if (ride.memo == memo) return@locked true
+    save(ride.withMemo(memo, now))
+  }
+
+  /**
+   * DL-01: removes an ended ride and all that belongs to it (US-D-06.002). The ride recording or paused cannot be
+   * deleted (slice 3 spec §2). A save of this ride still waiting is dropped, so it does not write the ride back.
+   */
+  suspend fun delete(rideId: String): Boolean = locked {
+    if (activeRide.value?.id == rideId) return@locked false
+    if (unsaved?.id == rideId) unsaved = null
+    var deleted = false
+    val written = write("delete") { deleted = deps.store.delete(rideId, deps.now()) }
+    if (written && deleted) deps.changed()
+    written && deleted
+  }
+
   /**
    * SC-16: the longest recording time changed (US-C-08.005). The recording segment's deadline is worked out again from
    * its start; one already passed ends the ride automatically at that deadline. A paused ride takes the new time when
diff --git a/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt b/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt
index 5b41763..be800a4 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt
@@ -13,6 +13,11 @@ interface RideStore {
   /** Adds a point and, in the same transaction, the ride's new distance and the time it was seen alive. */
   suspend fun addPoint(rideId: String, point: RoutePoint, distanceMeters: Double, aliveAt: Long)
   suspend fun markAlive(rideId: String, at: Long)
+  /**
+   * Removes an ended ride with its segments, points, point memos and asks, and marks it to be deleted on the Backend,
+   * all in one transaction (slice 3 spec §4.2). False when the ride is not kept or has not ended.
+   */
+  suspend fun delete(rideId: String, at: Long): Boolean
 }
 
 /** Wakes the app at a ride's deadline even when the process has died (slice 2 spec §4.4). */
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 36cfc3d..932369a 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -9,6 +9,7 @@ import androidx.room.Entity
 import androidx.room.ForeignKey
 import androidx.room.Index
 import androidx.room.Insert
+import androidx.room.OnConflictStrategy
 import androidx.room.PrimaryKey
 import androidx.room.Query
 import androidx.room.Relation
@@ -18,6 +19,7 @@ import androidx.room.Transaction
 import androidx.room.Upsert
 import androidx.room.migration.Migration
 import androidx.sqlite.db.SupportSQLiteDatabase
+import com.touringproject.v2.records.memoTime
 import kotlinx.coroutines.flow.Flow
 
 // The device's record of rides (slice 2 spec §5.1). Every schema version is exported to app/schemas and is moved
@@ -160,6 +162,33 @@ interface AskDao {
   /** The ride's asks in the order they were asked (SC-06, SC-07). */
   @Query("SELECT * FROM asks WHERE rideId = :rideId ORDER BY askedAt")
   fun forRide(rideId: String): Flow<List<AskEntity>>
+
+  @Query("UPDATE asks SET memo = :memo, memoUpdatedAt = :at WHERE askId = :askId")
+  suspend fun setMemo(askId: String, memo: String?, at: Long)
+
+  /** SC-08. False when the ask is not kept; the same memo again changes nothing. */
+  @Transaction
+  suspend fun writeMemo(askId: String, memo: String?, now: Long): Boolean {
+    val ask = ask(askId) ?: return false
+    if (ask.memo == memo) return true
+    setMemo(askId, memo, memoTime(now, ask.memoUpdatedAt))
+    return true
+  }
+
+  @Query("DELETE FROM asks WHERE askId = :askId")
+  suspend fun deleteRow(askId: String)
+
+  @Insert(onConflict = OnConflictStrategy.REPLACE)
+  suspend fun markDeleted(deletion: DeletionEntity)
+
+  /** DL-01: removes the ask and marks it for the Backend, together (slice 3 spec §4.2). False when it is not kept. */
+  @Transaction
+  suspend fun delete(askId: String, at: Long): Boolean {
+    val ask = ask(askId) ?: return false
+    deleteRow(askId)
+    markDeleted(DeletionEntity("ask", askId, ask.rideId, at))
+    return true
+  }
 }
 
 data class RideWithSegments(
@@ -271,6 +300,37 @@ interface RideDao {
     insertPoint(point)
     updateDistance(point.rideId, distanceMeters, aliveAt)
   }
+
+  // Deleting a ride (slice 3 spec §4.2). Each table is cleared by name rather than through the foreign keys, and the
+  // asks have none.
+  @Query("DELETE FROM asks WHERE rideId = :rideId")
+  suspend fun deleteAsks(rideId: String)
+
+  @Query("DELETE FROM notes WHERE rideId = :rideId")
+  suspend fun deleteNotes(rideId: String)
+
+  @Query("DELETE FROM route_points WHERE rideId = :rideId")
+  suspend fun deletePoints(rideId: String)
+
+  @Query("DELETE FROM rides WHERE id = :rideId")
+  suspend fun deleteRideRow(rideId: String)
+
+  @Insert(onConflict = OnConflictStrategy.REPLACE)
+  suspend fun markDeleted(deletion: DeletionEntity)
+
+  /** Removes an ended ride and everything of it, and marks it for the Backend. False when it is not kept or not ended. */
+  @Transaction
+  suspend fun deleteEnded(rideId: String, at: Long): Boolean {
+    val ride = ride(rideId) ?: return false
+    if (ride.status != "ended") return false
+    deleteAsks(rideId)
+    deleteNotes(rideId)
+    deletePoints(rideId)
+    deleteSegments(rideId)
+    deleteRideRow(rideId)
+    markDeleted(DeletionEntity("ride", rideId, null, at))
+    return true
+  }
 }
 
 @Database(
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomAskEdits.kt b/app/src/main/java/com/touringproject/v2/store/RoomAskEdits.kt
new file mode 100644
index 0000000..3cd81d8
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/store/RoomAskEdits.kt
@@ -0,0 +1,34 @@
+package com.touringproject.v2.store
+
+import com.touringproject.v2.records.AskEdits
+import com.touringproject.v2.records.memoFits
+import kotlinx.coroutines.CancellationException
+
+/**
+ * Changes kept asks in Room. A change that was written is something new to send (changed). A failed write is logged
+ * and reported as false, so the screen can say so and keep what was typed (slice 3 spec §8).
+ */
+class RoomAskEdits(
+  private val dao: AskDao,
+  private val now: () -> Long,
+  private val changed: () -> Unit,
+  private val log: (String, Throwable) -> Unit,
+) : AskEdits {
+  override suspend fun memo(askId: String, memo: String?): Boolean =
+    memoFits(memo) && attempt("ask_memo_failed askId=$askId") { dao.writeMemo(askId, memo, now()) }
+
+  override suspend fun delete(askId: String): Boolean = attempt("ask_delete_failed askId=$askId") { dao.delete(askId, now()) }
+
+  private suspend fun attempt(failure: String, write: suspend () -> Boolean): Boolean {
+    val written = try {
+      write()
+    } catch (e: CancellationException) {
+      throw e
+    } catch (e: Exception) {
+      log(failure, e)
+      false
+    }
+    if (written) changed()
+    return written
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt b/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt
index cb95137..8d50d22 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt
@@ -41,4 +41,6 @@ class RoomRideStore(private val dao: RideDao) : RideStore {
     dao.addPoint(RoutePointEntity(rideId = rideId, segment = point.segment, t = point.t, lat = point.lat, lon = point.lon, accuracy = point.accuracy, chunk = null), distanceMeters, aliveAt)
 
   override suspend fun markAlive(rideId: String, at: Long) = dao.markAlive(rideId, at)
+
+  override suspend fun delete(rideId: String, at: Long): Boolean = dao.deleteEnded(rideId, at)
 }
PATCH
````

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t2.log 2>&1; tail -1 /tmp/trv2-t2.log`
Expected: `BUILD SUCCESSFUL`（`404` 件。数は Task 8 の数え方で見る）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/records/AskEdits.kt app/src/main/java/com/touringproject/v2/records/Memos.kt app/src/main/java/com/touringproject/v2/ride/Ride.kt app/src/main/java/com/touringproject/v2/ride/RideController.kt app/src/main/java/com/touringproject/v2/ride/RidePorts.kt app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomAskEdits.kt app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt app/src/test/java/com/touringproject/v2/records/MemosTest.kt app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt app/src/test/java/com/touringproject/v2/ride/RideTest.kt app/src/test/java/com/touringproject/v2/store/RoomAskEditsTest.kt app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt app/src/test/java/com/touringproject/v2/store/RoomRideStoreTest.kt
git commit -m "feat: write and remove memos, and delete asks and ended rides with a mark for the Backend"
```

---

### Task 3: API: メモと削除の呼び出し・410・400 の理由（#26）

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify: `api/ApiClient.kt`・`sync/SyncPlan.kt`
- Test: `api/ApiClientTest.kt`・`sync/RideSyncTest.kt`（作り物の `RideApi` に新しい呼び出しを足す）

**Interfaces:**
- Consumes: Task 1 の `Ride.memo`
- Produces:
  - `ApiErrorKind.GONE`（410）。400 の `ApiError.message` は `HTTP 400: <message>`
  - `RideBody.memo: String? = null`（null は送らない）・`AskMemoBody(memo: String?, updatedAt: String)`（memo の null は送る）
  - `RideApi.putAskMemo(askId: String, body: AskMemoBody)`・`deleteRide(rideId: String)`・`deleteAsk(askId: String)`（どれも一時的な失敗は試し直す）
  - `Ride.toBody()` が `memo` を入れる

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
index da3a312..2ccfa80 100644
--- a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
+++ b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
@@ -173,4 +173,62 @@ class ApiClientTest {
     assertEquals(ApiErrorKind.BAD_REQUEST, error.kind)
     assertEquals(3, server.requestCount)
   }
+
+  // Android #26: the log of a refused send says why the Backend refused it.
+  @Test
+  fun a_refusal_carries_the_backends_message() = runTest {
+    server.enqueue(json(400, """{"error":"bad_request","message":"segments must not overlap"}"""))
+    val error = runCatching { client().putRoute("r1", 0, RouteBody(emptyList())) }.exceptionOrNull() as ApiError
+    assertEquals(ApiErrorKind.BAD_REQUEST, error.kind)
+    assertEquals("HTTP 400: segments must not overlap", error.message)
+    server.enqueue(json(400, "not json"))
+    val plain = runCatching { client().putRoute("r1", 0, RouteBody(emptyList())) }.exceptionOrNull() as ApiError
+    assertEquals("HTTP 400", plain.message)
+  }
+
+  // Slice 3 spec §5.4: a send to what was deleted is answered 410.
+  @Test
+  fun a_send_to_a_deleted_record_is_gone_and_not_retried() = runTest {
+    server.enqueue(json(410, """{"error":"deleted"}"""))
+    val error = runCatching { client().putAskMemo("a1", AskMemoBody("x", "2026-10-21T01:00:00Z")) }.exceptionOrNull() as ApiError
+    assertEquals(ApiErrorKind.GONE, error.kind)
+    assertEquals(1, server.requestCount)
+  }
+
+  @Test
+  fun putRide_sends_the_memo_and_leaves_it_out_when_there_is_none() = runTest {
+    server.enqueue(json(200, """{"rideId":"r1","applied":true}"""))
+    server.enqueue(json(200, """{"rideId":"r1","applied":true}"""))
+    val segments = listOf(SegmentBody("2026-10-18T01:00:00Z", "2026-10-18T02:00:00Z"))
+    client().putRide("r1", RideBody("箱根", "ended", segments, false, "2026-10-18T02:00:00Z", memo = "また来たい"))
+    client().putRide("r1", RideBody("箱根", "ended", segments, false, "2026-10-18T02:00:01Z"))
+    assertEquals("また来たい", Json.parseToJsonElement(server.takeRequest().body.readUtf8()).jsonObject["memo"]!!.jsonPrimitive.content)
+    // The Backend takes a ride without memo as one with none, and drops the memo it had.
+    assertFalse("memo" in Json.parseToJsonElement(server.takeRequest().body.readUtf8()).jsonObject)
+  }
+
+  @Test
+  fun putAskMemo_sends_the_memo_or_null_to_remove_it() = runTest {
+    server.enqueue(json(200, """{"askId":"a1","applied":true}"""))
+    client().putAskMemo("a1", AskMemoBody(null, "2026-10-21T01:00:00Z"))
+    val request = server.takeRequest()
+    assertEquals("PUT", request.method)
+    assertEquals("/Prod/asks/a1/memo", request.path)
+    val sent = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
+    assertEquals(JsonNull, sent["memo"])
+    assertEquals("2026-10-21T01:00:00Z", sent["updatedAt"]!!.jsonPrimitive.content)
+  }
+
+  // A deletion is answered 204 with no body, and is the same however often it is sent.
+  @Test
+  fun deletions_go_to_their_record_and_are_retried_when_the_server_fails() = runTest {
+    server.enqueue(MockResponse().setResponseCode(204))
+    server.enqueue(json(503))
+    server.enqueue(MockResponse().setResponseCode(204))
+    client().deleteAsk("a1")
+    client().deleteRide("r1")
+    assertEquals("DELETE /Prod/asks/a1", server.takeRequest().let { "${it.method} ${it.path}" })
+    assertEquals("DELETE /Prod/rides/r1", server.takeRequest().let { "${it.method} ${it.path}" })
+    assertEquals(3, server.requestCount)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
index b47afcc..ec6a96e 100644
--- a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
@@ -2,6 +2,7 @@ package com.touringproject.v2.sync
 
 import com.touringproject.v2.api.ApiError
 import com.touringproject.v2.api.ApiErrorKind
+import com.touringproject.v2.api.AskMemoBody
 import com.touringproject.v2.api.RideApi
 import com.touringproject.v2.api.RideBody
 import com.touringproject.v2.api.RouteBody
@@ -65,6 +66,9 @@ private class World {
   val api = object : RideApi {
     override suspend fun putRide(rideId: String, body: RideBody) = call("ride/$rideId:${body.status}")
     override suspend fun putRoute(rideId: String, seq: Int, body: RouteBody) = call("route/$rideId/$seq:${body.points.size}")
+    override suspend fun putAskMemo(askId: String, body: AskMemoBody) = call("memo/$askId:${body.memo}")
+    override suspend fun deleteRide(rideId: String) = call("delete/ride/$rideId")
+    override suspend fun deleteAsk(askId: String) = call("delete/ask/$askId")
   }
 
   val sync = RideSync(store, { if (hasKey) api else null }) { _, _ -> }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ApiClientTest' --tests '*RideSyncTest' --rerun > /tmp/trv2-t3.log 2>&1; grep -c '^e:' /tmp/trv2-t3.log`
Expected: コンパイルで落ちる（`AskMemoBody`・`GONE` が無い）

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
index 9499d85..cee0046 100644
--- a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
+++ b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
@@ -4,6 +4,8 @@ import kotlinx.coroutines.delay
 import kotlinx.coroutines.suspendCancellableCoroutine
 import kotlinx.serialization.Serializable
 import kotlinx.serialization.json.Json
+import kotlinx.serialization.json.jsonObject
+import kotlinx.serialization.json.jsonPrimitive
 import okhttp3.Call
 import okhttp3.Callback
 import okhttp3.MediaType.Companion.toMediaType
@@ -16,7 +18,8 @@ import java.util.concurrent.TimeUnit
 import kotlin.coroutines.resumeWithException
 
 // Backend API (Backend/openapi.yaml). Errors are classified so the ask loop can pick the spoken message.
-enum class ApiErrorKind { INVALID_KEY, BAD_REQUEST, NOT_FOUND, RATE_LIMITED, SERVER, NETWORK }
+// GONE is 410: the record, or its ride, was deleted (slice 3 spec §5.4); the sync treats it as sent.
+enum class ApiErrorKind { INVALID_KEY, BAD_REQUEST, NOT_FOUND, GONE, RATE_LIMITED, SERVER, NETWORK }
 
 class ApiError(val kind: ApiErrorKind, message: String? = null) : Exception(message ?: kind.name)
 
@@ -62,17 +65,34 @@ interface AskApi {
 // A ride and its route (slice 2 spec §6.2). Times are ISO 8601 with their time zone.
 @Serializable data class SegmentBody(val startedAt: String, val endedAt: String?)
 
+/** memo goes with the ride as a whole: a ride without one (memo left out) drops the memo the Backend has (slice 3 spec §6.2). */
 @Serializable
-data class RideBody(val name: String, val status: String, val segments: List<SegmentBody>, val autoEnded: Boolean, val updatedAt: String)
+data class RideBody(
+  val name: String,
+  val status: String,
+  val segments: List<SegmentBody>,
+  val autoEnded: Boolean,
+  val updatedAt: String,
+  val memo: String? = null,
+)
 
 @Serializable data class PointBody(val t: String, val lat: Double, val lon: Double, val accuracy: Double?, val segment: Int)
 
 @Serializable data class RouteBody(val points: List<PointBody>)
 
-/** Both calls may be sent again and again: the Backend keeps one copy of each. A 400 throws BAD_REQUEST. */
+/** A conversation's memo (slice 3 spec §6.2); null removes it. */
+@Serializable data class AskMemoBody(val memo: String?, val updatedAt: String)
+
+/**
+ * Every call may be sent again and again: the Backend keeps one copy of each, and a deletion is the same however often
+ * it comes. A 400 throws BAD_REQUEST, a 404 NOT_FOUND and a 410 (deleted) GONE.
+ */
 interface RideApi {
   suspend fun putRide(rideId: String, body: RideBody)
   suspend fun putRoute(rideId: String, seq: Int, body: RouteBody)
+  suspend fun putAskMemo(askId: String, body: AskMemoBody)
+  suspend fun deleteRide(rideId: String)
+  suspend fun deleteAsk(askId: String)
 }
 
 private val TRANSIENT = setOf(ApiErrorKind.RATE_LIMITED, ApiErrorKind.SERVER, ApiErrorKind.NETWORK)
@@ -84,11 +104,22 @@ private fun kindFor(status: Int): ApiErrorKind? = when {
   status == 403 -> ApiErrorKind.INVALID_KEY
   status == 400 -> ApiErrorKind.BAD_REQUEST
   status == 404 -> ApiErrorKind.NOT_FOUND
+  status == 410 -> ApiErrorKind.GONE
   status == 429 -> ApiErrorKind.RATE_LIMITED
   status >= 500 -> ApiErrorKind.SERVER
   else -> null
 }
 
+/** A refusal (400) carries the Backend's message, so the sync's log tells why it is not sent again (Android #26). */
+private fun reason(code: Int, kind: ApiErrorKind, body: String?): String {
+  val message = if (kind == ApiErrorKind.BAD_REQUEST && body != null) {
+    runCatching { Json.parseToJsonElement(body).jsonObject["message"]?.jsonPrimitive?.content }.getOrNull()
+  } else {
+    null
+  }
+  return message?.let { "HTTP $code: $it" } ?: "HTTP $code"
+}
+
 /** http is the app's one OkHttpClient, so every client shares its connections and threads (Android #12). */
 class ApiClient(
   baseUrl: String,
@@ -120,6 +151,18 @@ class ApiClient(
     request("PUT", "/rides/$rideId/route/$seq", rideJson.encodeToString(RouteBody.serializer(), body), TRANSIENT)
   }
 
+  override suspend fun putAskMemo(askId: String, body: AskMemoBody) {
+    request("PUT", "/asks/$askId/memo", rideJson.encodeToString(AskMemoBody.serializer(), body), TRANSIENT)
+  }
+
+  override suspend fun deleteRide(rideId: String) {
+    request("DELETE", "/rides/$rideId", null, TRANSIENT)
+  }
+
+  override suspend fun deleteAsk(askId: String) {
+    request("DELETE", "/asks/$askId", null, TRANSIENT)
+  }
+
   suspend fun checkKey() {
     try {
       request("GET", "/asks/$PROBE_ASK_ID", null, TRANSIENT)
@@ -159,7 +202,7 @@ class ApiClient(
       override fun onResponse(call: Call, response: Response) {
         val outcome = runCatching {
           response.use {
-            kindFor(it.code)?.let { kind -> throw ApiError(kind, "HTTP ${it.code}") }
+            kindFor(it.code)?.let { kind -> throw ApiError(kind, reason(it.code, kind, it.body?.string())) }
             it.body?.string() ?: throw ApiError(ApiErrorKind.NETWORK, "empty body")
           }
         }.recoverCatching { e -> throw if (e is IOException) ApiError(ApiErrorKind.NETWORK, e.toString()) else e }
diff --git a/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt b/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
index 9619c85..37f8fdf 100644
--- a/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
@@ -51,6 +51,7 @@ fun Ride.toBody() = RideBody(
   segments = segments.map { SegmentBody(iso(it.startedAt), it.endedAt?.let(::iso)) },
   autoEnded = endReason == EndReason.AUTO,
   updatedAt = iso(updatedAt),
+  memo = memo,
 )
 
 fun RoutePoint.toBody() = PointBody(iso(t), lat, lon, accuracy, segment)
PATCH
````

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t3.log 2>&1; tail -1 /tmp/trv2-t3.log`
Expected: `BUILD SUCCESSFUL`（`409` 件。数は Task 8 の数え方で見る）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/api/ApiClient.kt app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
git commit -m "feat: send memos and deletions to the Backend, and keep the reason of a refusal"
```

---

### Task 4: 送信の係: 削除 → 走行 → メモの順・410・組み立ての失敗（#23・#25・#29）

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify: `sync/RideSync.kt`・`store/RoomSyncStore.kt`・`store/RideDatabase.kt`・`AppGraph.kt`
- Test: `sync/RideSyncTest.kt`・`sync/CredentialChangesTest.kt`（新規）・`store/RoomSyncStoreTest.kt`・`store/RoomRecordsTest.kt`・`store/RoomAskLogTest.kt`（作り物の DAO）

**Interfaces:**
- Consumes: Task 2 の `DeletionEntity` の書き込み・`AskDao.writeMemo`。Task 3 の `RideApi`・`AskMemoBody`・`ApiErrorKind.GONE`
- Produces:
  - `sync.PendingDeletion(kind: String, id: String, rideId: String?)`・`sync.UnsentAskMemo(askId: String, memo: String?, updatedAt: Long)`
  - `SyncStore` に `deletions()`・`deletionSent(deletion)`・`unsentAskMemos()`・`askMemoSent(askId, updatedAt)`・`askMemoRefused(askId, updatedAt)`
  - `RoomSyncStore(dao: RideDao, asks: AskDao)`（引数が2つになる）
  - `RideDao.unsentSnapshot(): List<UnsentRow>`（`@Transaction`）・`deletions()`・`deletionSent(kind, id)`。`AskDao.unsentMemos(): List<AskMemoRow>`・`markMemoSent`・`markMemoRefused`
  - `sync.credentialChanges(key: Flow<String?>, userName: Flow<String?>): Flow<Unit>`

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
index 93258c6..7953ae7 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
@@ -61,6 +61,9 @@ class RoomAskLogTest {
       override suspend fun setMemo(askId: String, memo: String?, at: Long) = error("not used")
       override suspend fun deleteRow(askId: String) = error("not used")
       override suspend fun markDeleted(deletion: DeletionEntity) = error("not used")
+      override suspend fun unsentMemos(): List<AskMemoRow> = error("not used")
+      override suspend fun markMemoSent(askId: String, updatedAt: Long) = error("not used")
+      override suspend fun markMemoRefused(askId: String, updatedAt: Long) = error("not used")
     }
     val failing = RoomAskLog(dao, kotlinx.coroutines.MainScope()) { message, _ -> errors += message }
     failing.save(record)
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
index 3fe7702..fd222b8 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
@@ -30,7 +30,7 @@ class RoomRecordsTest {
     .allowMainThreadQueries()
     .build()
   private val rides = RoomRideStore(db.rides())
-  private val sync = RoomSyncStore(db.rides())
+  private val sync = RoomSyncStore(db.rides(), db.asks())
   private val log = RoomAskLog(db.asks(), MainScope()) { _, _ -> }
   private val records = RoomRecords(db.rides(), db.asks())
 
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
index af4dd55..7b071fd 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
@@ -10,7 +10,10 @@ import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.RoutePoint
 import com.touringproject.v2.ride.end
 import com.touringproject.v2.ride.newRide
+import com.touringproject.v2.ride.pause
 import com.touringproject.v2.sync.ChunkRange
+import com.touringproject.v2.sync.PendingDeletion
+import com.touringproject.v2.sync.UnsentAskMemo
 import com.touringproject.v2.sync.RideSync
 import kotlinx.coroutines.runBlocking
 import kotlinx.serialization.json.Json
@@ -31,7 +34,7 @@ class RoomSyncStoreTest {
     .build()
   private val dao = db.rides()
   private val rides = RoomRideStore(dao)
-  private val store = RoomSyncStore(dao)
+  private val store = RoomSyncStore(dao, db.asks())
   private val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)
 
   @After
@@ -109,4 +112,47 @@ class RoomSyncStoreTest {
     assertEquals(3, server.requestCount)
     server.shutdown()
   }
+
+  private suspend fun keepAsk(askId: String) =
+    db.asks().upsert(AskEntity(askId, 1_000, 2_000, "Q", "A", 35.0, 139.0, null, null, "voice", "c1", true, "answered", null, "r1"))
+
+  @Test
+  fun a_deletion_waits_until_it_is_sent() = runBlocking {
+    rides.save(ride.end(5_000, EndReason.MANUAL, 5_000))
+    keepAsk("a1")
+    db.asks().delete("a1", 6_000)
+    rides.delete("r1", 7_000)
+    assertEquals(listOf(PendingDeletion("ask", "a1", "r1"), PendingDeletion("ride", "r1", null)), store.deletions())
+    store.deletionSent(PendingDeletion("ask", "a1", "r1"))
+    assertEquals(listOf("r1"), store.deletions().map { it.id })
+  }
+
+  @Test
+  fun a_memo_is_unsent_until_its_version_is_taken_or_refused() = runBlocking {
+    keepAsk("a1")
+    keepAsk("a2")
+    assertEquals(emptyList<UnsentAskMemo>(), store.unsentAskMemos())
+    db.asks().writeMemo("a1", "また来たい", 5_000)
+    db.asks().writeMemo("a2", "給油", 6_000)
+    assertEquals(listOf(UnsentAskMemo("a1", "また来たい", 5_000), UnsentAskMemo("a2", "給油", 6_000)), store.unsentAskMemos())
+    store.askMemoSent("a1", 5_000)
+    store.askMemoRefused("a2", 6_000)
+    assertEquals(emptyList<UnsentAskMemo>(), store.unsentAskMemos())
+    db.asks().writeMemo("a1", null, 7_000)
+    assertEquals(listOf(UnsentAskMemo("a1", null, 7_000)), store.unsentAskMemos())
+  }
+
+  // Android #23: the ride and its segments come from one read, so they are of one version.
+  @Test
+  fun an_unsent_ride_comes_with_its_segments_and_counts_read_together() = runBlocking {
+    val paused = ride.pause(5_000)
+    rides.save(paused)
+    addPoints(3)
+    store.chunkSent("r1", ChunkRange(0, 0, 2), refused = false)
+    val unsent = store.unsent().single()
+    assertEquals(paused.status, unsent.ride.status)
+    assertEquals(paused.segments, unsent.ride.segments)
+    assertEquals(2, unsent.sentPoints)
+    assertEquals(3, unsent.totalPoints)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/sync/CredentialChangesTest.kt b/app/src/test/java/com/touringproject/v2/sync/CredentialChangesTest.kt
new file mode 100644
index 0000000..e086e75
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/sync/CredentialChangesTest.kt
@@ -0,0 +1,42 @@
+package com.touringproject.v2.sync
+
+import kotlinx.coroutines.flow.MutableStateFlow
+import kotlinx.coroutines.flow.toList
+import kotlinx.coroutines.launch
+import kotlinx.coroutines.test.runCurrent
+import kotlinx.coroutines.test.runTest
+import org.junit.Assert.assertEquals
+import org.junit.Test
+
+// Android #29: saving the key or the user name lets the rides waiting on the device go without reopening the app.
+class CredentialChangesTest {
+  @Test
+  fun a_change_of_the_key_or_the_user_name_is_a_trigger_but_loading_them_is_not() = runTest {
+    val key = MutableStateFlow<String?>(null)
+    val user = MutableStateFlow<String?>(null)
+    val triggers = mutableListOf<Unit>()
+    val job = launch { credentialChanges(key, user).toList(triggers) }
+    runCurrent()
+    user.value = "rider01"
+    runCurrent()
+    key.value = "key-1"
+    runCurrent()
+    assertEquals(0, triggers.size)
+    key.value = "key-2"
+    runCurrent()
+    user.value = "rider02"
+    runCurrent()
+    assertEquals(2, triggers.size)
+    // Removing the key sends nothing; putting it back is a change.
+    key.value = null
+    runCurrent()
+    assertEquals(2, triggers.size)
+    key.value = "key-2"
+    runCurrent()
+    assertEquals(2, triggers.size)
+    key.value = "key-3"
+    runCurrent()
+    assertEquals(3, triggers.size)
+    job.cancel()
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
index ec6a96e..6f3a401 100644
--- a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
@@ -31,6 +31,12 @@ private class World {
   val calls = mutableListOf<String>()
   /** Fails the call whose name (e.g. "route/r1/1") it is given, with the given kind. */
   val fail = mutableMapOf<String, ApiErrorKind>()
+  /** Throws the given exception from the call whose name it is given, before anything is sent (Android #25). */
+  val unbuildable = mutableMapOf<String, Exception>()
+  val deletions = mutableListOf<PendingDeletion>()
+  /** askId to (memo, updatedAt, sent, refused). */
+  val memos = linkedMapOf<String, MemoRow>()
+  class MemoRow(val memo: String?, val updatedAt: Long, var sent: Long? = null, var refused: Long? = null)
   var hasKey = true
   var gate: CompletableDeferred<Unit>? = null
   var passes = 0
@@ -56,9 +62,21 @@ private class World {
       for (i in chunk.from until chunk.until) chunks[i] = chunk.seq
       if (refused) calls += "refused:route/$rideId/${chunk.seq}"
     }
+    override suspend fun deletions() = deletions.toList()
+    override suspend fun deletionSent(deletion: PendingDeletion) {
+      deletions.remove(deletion)
+    }
+    override suspend fun unsentAskMemos() = memos.filter { (_, m) -> (m.sent ?: -1) < m.updatedAt && m.refused != m.updatedAt }
+      .map { (id, m) -> UnsentAskMemo(id, m.memo, m.updatedAt) }
+    override suspend fun askMemoSent(askId: String, updatedAt: Long) { memos.getValue(askId).sent = updatedAt }
+    override suspend fun askMemoRefused(askId: String, updatedAt: Long) {
+      memos.getValue(askId).refused = updatedAt
+      calls += "refused:memo/$askId"
+    }
   }
 
   private fun call(name: String) {
+    unbuildable[name]?.let { throw it }
     calls += name
     fail[name]?.let { throw ApiError(it) }
   }
@@ -197,4 +215,103 @@ class RideSyncTest {
     assertTrue(w.calls.isEmpty())
     job.cancel()
   }
+
+  // Slice 3 spec §5.1: deletions go first, then rides, then memos.
+  @Test
+  fun a_pass_sends_deletions_then_rides_then_memos() = runTest {
+    val w = World()
+    w.add(recording)
+    w.memos["a1"] = World.MemoRow("また来たい", 2_000)
+    w.deletions += PendingDeletion("ride", "r0", null)
+    w.deletions += PendingDeletion("ask", "a0", "r1")
+    w.sync.pass()
+    assertEquals(listOf("delete/ride/r0", "delete/ask/a0", "ride/r1:recording", "memo/a1:また来たい"), w.calls)
+    assertTrue(w.deletions.isEmpty())
+    assertEquals(2_000L, w.memos.getValue("a1").sent)
+    w.calls.clear()
+    w.sync.pass()
+    assertEquals(emptyList<String>(), w.calls)
+  }
+
+  // A failed deletion stays and goes first in the next pass, so the deleted record is never put back before it.
+  @Test
+  fun a_deletion_that_fails_ends_the_pass_and_goes_again_next_time() = runTest {
+    val w = World()
+    w.add(recording)
+    w.deletions += PendingDeletion("ask", "a0", "r1")
+    w.fail["delete/ask/a0"] = ApiErrorKind.NETWORK
+    w.sync.pass()
+    assertEquals(listOf("delete/ask/a0"), w.calls)
+    assertEquals(1, w.deletions.size)
+    w.fail.clear()
+    w.sync.pass()
+    assertEquals(listOf("delete/ask/a0", "delete/ask/a0", "ride/r1:recording"), w.calls)
+    assertTrue(w.deletions.isEmpty())
+  }
+
+  // Slice 3 spec §5.2: 410 means the record (or its ride) was deleted on the Backend; it is not sent again.
+  @Test
+  fun what_the_backend_has_deleted_is_taken_as_sent() = runTest {
+    val w = World()
+    val ended = recording.end(5_000, EndReason.MANUAL, 5_000)
+    w.add(ended, points = 2)
+    w.memos["a1"] = World.MemoRow("x", 2_000)
+    w.fail["ride/r1:ended"] = ApiErrorKind.GONE
+    w.fail["route/r1/0:2"] = ApiErrorKind.GONE
+    w.fail["memo/a1:x"] = ApiErrorKind.GONE
+    w.sync.pass()
+    val row = w.rows.getValue("r1")
+    assertEquals(ended.updatedAt, row.sent)
+    assertEquals(null, row.rejected)
+    assertEquals(listOf(0, 0), row.chunks)
+    assertEquals(2_000L, w.memos.getValue("a1").sent)
+    w.calls.clear()
+    w.sync.pass()
+    assertEquals(emptyList<String>(), w.calls)
+  }
+
+  // Slice 3 spec §5.2: a memo of an ask the Backend does not have (404), or one it refused (400), is not sent again.
+  @Test
+  fun a_memo_refused_or_of_an_unknown_ask_is_not_sent_again_until_it_changes() = runTest {
+    val w = World()
+    w.memos["a1"] = World.MemoRow("x", 2_000)
+    w.memos["a2"] = World.MemoRow("y", 2_100)
+    w.fail["memo/a1:x"] = ApiErrorKind.NOT_FOUND
+    w.fail["memo/a2:y"] = ApiErrorKind.BAD_REQUEST
+    w.sync.pass()
+    assertEquals(listOf("memo/a1:x", "refused:memo/a1", "memo/a2:y", "refused:memo/a2"), w.calls)
+    w.calls.clear()
+    w.sync.pass()
+    assertEquals(emptyList<String>(), w.calls)
+  }
+
+  // Android #25: a ride the device cannot even build is set aside, and the rides after it still go.
+  @Test
+  fun a_ride_that_cannot_be_built_does_not_hold_back_the_others() = runTest {
+    val w = World()
+    w.add(recording)
+    w.add(newRide("r2", "御殿場", 2_000, 7, MAX))
+    w.unbuildable["ride/r1:recording"] = kotlinx.serialization.SerializationException("NaN is not a valid double")
+    w.sync.pass()
+    assertEquals(listOf("ride/r2:recording"), w.calls)
+    assertEquals(recording.updatedAt, w.rows.getValue("r1").rejected)
+  }
+
+  // A deletion the Backend refuses can never go; its mark goes rather than block every pass.
+  @Test
+  fun a_refused_deletion_is_dropped() = runTest {
+    val w = World()
+    w.deletions += PendingDeletion("ask", "a0", null)
+    w.fail["delete/ask/a0"] = ApiErrorKind.BAD_REQUEST
+    w.sync.pass()
+    assertTrue(w.deletions.isEmpty())
+  }
+
+  @Test
+  fun a_memo_removed_is_sent_as_null() = runTest {
+    val w = World()
+    w.memos["a1"] = World.MemoRow(null, 2_000)
+    w.sync.pass()
+    assertEquals(listOf("memo/a1:null"), w.calls)
+  }
 }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideSyncTest' --tests '*CredentialChangesTest' --tests '*RoomSyncStoreTest' --tests '*RoomRecordsTest' --tests '*RoomAskLogTest' --rerun > /tmp/trv2-t4.log 2>&1; grep -c '^e:' /tmp/trv2-t4.log`
Expected: コンパイルで落ちる（`PendingDeletion`・`credentialChanges` などが無い）

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index b346413..a2d4c9b 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -55,6 +55,7 @@ import com.touringproject.v2.store.RoomRecords
 import com.touringproject.v2.store.RoomRideStore
 import com.touringproject.v2.store.RoomSyncStore
 import com.touringproject.v2.sync.RideSync
+import com.touringproject.v2.sync.credentialChanges
 import kotlinx.coroutines.CoroutineScope
 import kotlinx.coroutines.MainScope
 import kotlinx.coroutines.delay
@@ -95,7 +96,7 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
 
   /** Sends rides and routes; a pass runs on each trigger (slice 2 spec §5.3). */
   val sync = RideSync(
-    RoomSyncStore(database.rides()),
+    RoomSyncStore(database.rides(), database.asks()),
     api = {
       val key = apiKeys.current()
       val user = settings.settings.value?.userName
@@ -219,6 +220,8 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     scope.launch { sync.run() }
     // SC-16: the recording ride's deadline follows the longest recording time, wherever it was changed (Android #33).
     scope.launch { maxRecordingChanges(settings.settings).collect { rides.maxRecordingChanged() } }
+    // A key or user name saved may let rides waiting on the device go at last (Android #29).
+    scope.launch { credentialChanges(apiKeys.apiKey, settings.settings.map { it?.userName }).collect { sync.request() } }
     scope.launch {
       settings.load()
       apiKeys.load()
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 932369a..da55667 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -178,6 +178,22 @@ interface AskDao {
   @Query("DELETE FROM asks WHERE askId = :askId")
   suspend fun deleteRow(askId: String)
 
+  // Sending memos (slice 3 spec §5.1): the asks whose memo changed since it was taken, unless that version was refused.
+  @Query(
+    "SELECT askId, memo, memoUpdatedAt FROM asks WHERE memoUpdatedAt IS NOT NULL AND " +
+      "(memoSentUpdatedAt IS NULL OR memoSentUpdatedAt < memoUpdatedAt) AND " +
+      "(memoRejectedUpdatedAt IS NULL OR memoRejectedUpdatedAt != memoUpdatedAt) ORDER BY memoUpdatedAt",
+  )
+  suspend fun unsentMemos(): List<AskMemoRow>
+
+  @Query(
+    "UPDATE asks SET memoSentUpdatedAt = :updatedAt WHERE askId = :askId AND (memoSentUpdatedAt IS NULL OR memoSentUpdatedAt < :updatedAt)",
+  )
+  suspend fun markMemoSent(askId: String, updatedAt: Long)
+
+  @Query("UPDATE asks SET memoRejectedUpdatedAt = :updatedAt WHERE askId = :askId")
+  suspend fun markMemoRefused(askId: String, updatedAt: Long)
+
   @Insert(onConflict = OnConflictStrategy.REPLACE)
   suspend fun markDeleted(deletion: DeletionEntity)
 
@@ -191,6 +207,11 @@ interface AskDao {
   }
 }
 
+data class AskMemoRow(val askId: String, val memo: String?, val memoUpdatedAt: Long)
+
+/** What one ride has left to send, read together (Android #23). */
+data class UnsentRow(val ride: RideEntity, val segments: List<SegmentEntity>, val sentPoints: Int, val totalPoints: Int)
+
 data class RideWithSegments(
   @Embedded val ride: RideEntity,
   @Relation(parentColumn = "id", entityColumn = "rideId") val segments: List<SegmentEntity>,
@@ -318,6 +339,20 @@ interface RideDao {
   @Insert(onConflict = OnConflictStrategy.REPLACE)
   suspend fun markDeleted(deletion: DeletionEntity)
 
+  @Query("SELECT * FROM deletions ORDER BY deletedAt")
+  suspend fun deletions(): List<DeletionEntity>
+
+  @Query("DELETE FROM deletions WHERE kind = :kind AND id = :id")
+  suspend fun deletionSent(kind: String, id: String)
+
+  /**
+   * The rides with something left to send, each with its segments and point counts, in one transaction: a save that
+   * lands meanwhile cannot pair an old status with new segments (Android #23).
+   */
+  @Transaction
+  suspend fun unsentSnapshot(): List<UnsentRow> =
+    unsentRides().map { UnsentRow(it, segments(it.id), sentPointCount(it.id), pointCount(it.id)) }
+
   /** Removes an ended ride and everything of it, and marks it for the Backend. False when it is not kept or not ended. */
   @Transaction
   suspend fun deleteEnded(rideId: String, at: Long): Boolean {
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
index edbaf95..e97110d 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
@@ -2,12 +2,14 @@ package com.touringproject.v2.store
 
 import com.touringproject.v2.ride.RoutePoint
 import com.touringproject.v2.sync.ChunkRange
+import com.touringproject.v2.sync.PendingDeletion
 import com.touringproject.v2.sync.SyncStore
 import com.touringproject.v2.sync.Unsent
+import com.touringproject.v2.sync.UnsentAskMemo
 
-class RoomSyncStore(private val dao: RideDao) : SyncStore {
-  override suspend fun unsent(): List<Unsent> = dao.unsentRides().map {
-    Unsent(it.toRide(dao.segments(it.id)), it.sentUpdatedAt, it.rejectedUpdatedAt, dao.sentPointCount(it.id), dao.pointCount(it.id))
+class RoomSyncStore(private val dao: RideDao, private val asks: AskDao) : SyncStore {
+  override suspend fun unsent(): List<Unsent> = dao.unsentSnapshot().map {
+    Unsent(it.ride.toRide(it.segments), it.ride.sentUpdatedAt, it.ride.rejectedUpdatedAt, it.sentPoints, it.totalPoints)
   }
 
   override suspend fun points(rideId: String, from: Int, until: Int): List<RoutePoint> =
@@ -19,4 +21,15 @@ class RoomSyncStore(private val dao: RideDao) : SyncStore {
 
   override suspend fun chunkSent(rideId: String, chunk: ChunkRange, refused: Boolean) =
     dao.markChunk(rideId, chunk.seq, chunk.from, chunk.until - chunk.from, refused)
+
+  override suspend fun deletions(): List<PendingDeletion> = dao.deletions().map { PendingDeletion(it.kind, it.id, it.rideId) }
+
+  override suspend fun deletionSent(deletion: PendingDeletion) = dao.deletionSent(deletion.kind, deletion.id)
+
+  override suspend fun unsentAskMemos(): List<UnsentAskMemo> =
+    asks.unsentMemos().map { UnsentAskMemo(it.askId, it.memo, it.memoUpdatedAt) }
+
+  override suspend fun askMemoSent(askId: String, updatedAt: Long) = asks.markMemoSent(askId, updatedAt)
+
+  override suspend fun askMemoRefused(askId: String, updatedAt: Long) = asks.markMemoRefused(askId, updatedAt)
 }
diff --git a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
index 8ad4723..ca8b290 100644
--- a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
@@ -2,6 +2,7 @@ package com.touringproject.v2.sync
 
 import com.touringproject.v2.api.ApiError
 import com.touringproject.v2.api.ApiErrorKind
+import com.touringproject.v2.api.AskMemoBody
 import com.touringproject.v2.api.RideApi
 import com.touringproject.v2.api.RouteBody
 import com.touringproject.v2.ride.Ride
@@ -9,12 +10,28 @@ import com.touringproject.v2.ride.RideStatus
 import com.touringproject.v2.ride.RoutePoint
 import kotlinx.coroutines.CancellationException
 import kotlinx.coroutines.channels.Channel
+import kotlinx.coroutines.flow.Flow
+import kotlinx.coroutines.flow.combine
+import kotlinx.coroutines.flow.distinctUntilChanged
+import kotlinx.coroutines.flow.drop
+import kotlinx.coroutines.flow.filter
+import kotlinx.coroutines.flow.map
+import kotlinx.serialization.SerializationException
 
 /** A ride that may have something left to send, with what the Backend already has of it. */
 data class Unsent(val ride: Ride, val sentUpdatedAt: Long?, val rejectedUpdatedAt: Long?, val sentPoints: Int, val totalPoints: Int)
 
+/** A record deleted on the device whose deletion has not reached the Backend (slice 3 spec §4.2). kind: ask / ride / note. */
+data class PendingDeletion(val kind: String, val id: String, val rideId: String?)
+
+/** A conversation's memo that has changed since the Backend last took it; memo null removes it. */
+data class UnsentAskMemo(val askId: String, val memo: String?, val updatedAt: Long)
+
 interface SyncStore {
-  /** Rides whose meta has changed since it was sent (and was not refused), or that have points not yet sent. */
+  /**
+   * Rides whose meta has changed since it was sent (and was not refused), or that have points not yet sent. Read in
+   * one transaction, so a ride and its segments are always of the same version (Android #23).
+   */
   suspend fun unsent(): List<Unsent>
   /** The ride's points from index from to until, in the order they were recorded. */
   suspend fun points(rideId: String, from: Int, until: Int): List<RoutePoint>
@@ -24,12 +41,24 @@ interface SyncStore {
   suspend fun rideRefused(rideId: String, updatedAt: Long)
   /** The chunk's points have gone; refused when the Backend refused them (400), so they are not sent again either. */
   suspend fun chunkSent(rideId: String, chunk: ChunkRange, refused: Boolean)
+  suspend fun deletions(): List<PendingDeletion>
+  /** The deletion reached the Backend (or can never be sent): its mark goes. */
+  suspend fun deletionSent(deletion: PendingDeletion)
+  suspend fun unsentAskMemos(): List<UnsentAskMemo>
+  suspend fun askMemoSent(askId: String, updatedAt: Long)
+  /** The Backend refused the memo as of updatedAt (400, or 404 for an ask it does not have); it is not sent again. */
+  suspend fun askMemoRefused(askId: String, updatedAt: Long)
 }
 
+/** How the Backend answered a send that did not fail on the way. */
+private enum class Reply { TAKEN, REFUSED, GONE }
+
 /**
- * Sends rides and their routes to the Backend (slice 2 spec §5.3). A pass reads what is left to send and sends it; with
- * nothing left it makes no request at all. Passes run one at a time; the ones asked for while a pass runs fold into one
- * more. A failure other than a refusal ends the pass, and the next trigger tries again; there is no timer of its own.
+ * Sends rides, their routes, memos and deletions to the Backend (slice 2 spec §5.3, slice 3 spec §5). A pass reads
+ * what is left to send and sends it, deletions first, so a deleted record's old version is never put back in the same
+ * pass; with nothing left it makes no request at all. Passes run one at a time; the ones asked for while a pass runs
+ * fold into one more. A failure other than a refusal ends the pass, and the next trigger tries again; there is no
+ * timer of its own.
  */
 class RideSync(
   private val store: SyncStore,
@@ -40,7 +69,7 @@ class RideSync(
   private val requests = Channel<Unit>(Channel.CONFLATED)
   private var points = 0
 
-  /** A trigger: the ride changed, the app came to the front, or it started. Safe from any thread. */
+  /** A trigger: something changed, the app came to the front, it started, or the key or user name changed. Safe from any thread. */
   fun request() {
     requests.trySend(Unit)
   }
@@ -58,51 +87,110 @@ class RideSync(
 
   suspend fun pass() {
     val client = api() ?: return
-    val rides = try {
-      store.unsent()
-    } catch (e: CancellationException) {
-      throw e
-    } catch (e: Exception) {
-      log("sync_failed", mapOf("op" to "unsent", "error" to e.toString()))
-      return
+    val deletions = read("deletions") { store.deletions() } ?: return
+    for (deletion in deletions) {
+      if (!attempt(deletion.id) { sendDeletion(client, deletion) }) return
     }
+    val rides = read("unsent") { store.unsent() } ?: return
     for (unsent in rides) {
-      if (!send(client, unsent)) return
+      if (!attempt(unsent.ride.id) { sendRide(client, unsent) }) return
+    }
+    val memos = read("ask_memos") { store.unsentAskMemos() } ?: return
+    for (memo in memos) {
+      if (!attempt(memo.askId) { sendAskMemo(client, memo) }) return
     }
   }
 
+  private suspend fun <T> read(op: String, block: suspend () -> T): T? = try {
+    block()
+  } catch (e: CancellationException) {
+    throw e
+  } catch (e: Exception) {
+    log("sync_failed", mapOf("op" to op, "error" to e.toString()))
+    null
+  }
+
   // False ends the pass: the network, the key or the database failed, and the next trigger tries again.
-  private suspend fun send(client: RideApi, unsent: Unsent): Boolean {
-    val ride = unsent.ride
-    try {
-      if (metaToSend(ride.updatedAt, unsent.sentUpdatedAt, unsent.rejectedUpdatedAt)) {
-        if (accepted(ride.id, "ride") { client.putRide(ride.id, ride.toBody()) }) {
-          store.rideSent(ride.id, ride.updatedAt)
-        } else {
-          store.rideRefused(ride.id, ride.updatedAt)
-        }
+  private suspend fun attempt(id: String, send: suspend () -> Unit): Boolean = try {
+    send()
+    true
+  } catch (e: CancellationException) {
+    throw e
+  } catch (e: Exception) {
+    log("sync_failed", mapOf("id" to id, "error" to e.toString()))
+    false
+  }
+
+  // A deletion that is refused can never go either; its mark goes, and the log tells.
+  private suspend fun sendDeletion(client: RideApi, deletion: PendingDeletion) {
+    reply(deletion.id, "delete/${deletion.kind}") {
+      when (deletion.kind) {
+        "ride" -> client.deleteRide(deletion.id)
+        "ask" -> client.deleteAsk(deletion.id)
+        else -> throw IllegalStateException("unknown deletion kind ${deletion.kind}")
       }
-      for (chunk in chunksToSend(unsent.sentPoints, unsent.totalPoints, ride.status != RideStatus.RECORDING)) {
-        val points = store.points(ride.id, chunk.from, chunk.until)
-        val ok = accepted(ride.id, "route/${chunk.seq}") { client.putRoute(ride.id, chunk.seq, RouteBody(points.map { it.toBody() })) }
-        store.chunkSent(ride.id, chunk, refused = !ok)
+    }
+    store.deletionSent(deletion)
+  }
+
+  private suspend fun sendRide(client: RideApi, unsent: Unsent) {
+    val ride = unsent.ride
+    if (metaToSend(ride.updatedAt, unsent.sentUpdatedAt, unsent.rejectedUpdatedAt)) {
+      // GONE: the ride was deleted on the Backend; the device has nothing left to tell it (slice 3 spec §5.2).
+      if (reply(ride.id, "ride") { client.putRide(ride.id, ride.toBody()) } == Reply.REFUSED) {
+        store.rideRefused(ride.id, ride.updatedAt)
+      } else {
+        store.rideSent(ride.id, ride.updatedAt)
       }
-      return true
-    } catch (e: CancellationException) {
-      throw e
-    } catch (e: Exception) {
-      log("sync_failed", mapOf("ride" to ride.id, "error" to e.toString()))
-      return false
+    }
+    for (chunk in chunksToSend(unsent.sentPoints, unsent.totalPoints, ride.status != RideStatus.RECORDING)) {
+      val points = store.points(ride.id, chunk.from, chunk.until)
+      val answer = reply(ride.id, "route/${chunk.seq}") { client.putRoute(ride.id, chunk.seq, RouteBody(points.map { it.toBody() })) }
+      store.chunkSent(ride.id, chunk, refused = answer == Reply.REFUSED)
     }
   }
 
-  // True when the Backend took it, false when it refused it (400: logged, never sent again). Other failures throw.
-  private suspend fun accepted(rideId: String, what: String, put: suspend () -> Unit): Boolean = try {
-    put()
-    true
+  private suspend fun sendAskMemo(client: RideApi, memo: UnsentAskMemo) {
+    if (reply(memo.askId, "memo") { client.putAskMemo(memo.askId, AskMemoBody(memo.memo, iso(memo.updatedAt))) } == Reply.REFUSED) {
+      store.askMemoRefused(memo.askId, memo.updatedAt)
+    } else {
+      store.askMemoSent(memo.askId, memo.updatedAt)
+    }
+  }
+
+  /**
+   * TAKEN when the Backend took it; REFUSED when it refused it (400, or 404 for a memo of an ask it does not have) or
+   * the device could not even build it (a value that cannot be written as JSON, Android #25); GONE when it was deleted
+   * there (410). Refusals and GONE are logged. Other failures throw and end the pass.
+   */
+  private suspend fun reply(id: String, what: String, call: suspend () -> Unit): Reply = try {
+    call()
+    Reply.TAKEN
   } catch (e: ApiError) {
-    if (e.kind != ApiErrorKind.BAD_REQUEST) throw e
-    log("sync_refused", mapOf("ride" to rideId, "what" to what, "error" to e.message))
-    false
+    when (e.kind) {
+      ApiErrorKind.BAD_REQUEST, ApiErrorKind.NOT_FOUND -> {
+        log("sync_refused", mapOf("id" to id, "what" to what, "error" to e.message))
+        Reply.REFUSED
+      }
+      ApiErrorKind.GONE -> {
+        log("sync_gone", mapOf("id" to id, "what" to what))
+        Reply.GONE
+      }
+      else -> throw e
+    }
+  } catch (e: SerializationException) {
+    log("sync_unsendable", mapOf("id" to id, "what" to what, "error" to e.toString()))
+    Reply.REFUSED
   }
 }
+
+/**
+ * A trigger each time the key or the user name changes once both are known (Android #29). The first pair, read when
+ * the app starts, is not one: the start has its own trigger. A key removed is no trigger either.
+ */
+fun credentialChanges(key: Flow<String?>, userName: Flow<String?>): Flow<Unit> =
+  combine(key, userName) { k, u -> if (k == null || u == null) null else k to u }
+    .filter { it != null }
+    .distinctUntilChanged()
+    .drop(1)
+    .map { }
PATCH
````

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t4.log 2>&1; tail -1 /tmp/trv2-t4.log`
Expected: `BUILD SUCCESSFUL`（`420` 件。数は Task 8 の数え方で見る）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt app/src/main/java/com/touringproject/v2/sync/RideSync.kt app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt app/src/test/java/com/touringproject/v2/sync/CredentialChangesTest.kt app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
git commit -m "feat: send deletions first, take 410 as sent, and set aside what cannot be built (Android #23, #25, #29)"
```

---

### Task 5: メモの印と、メモの未送信を数える保存の状態

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify: `ask/AskRecord.kt`・`store/RoomRecords.kt`・`store/RideDatabase.kt`・`records/Records.kt`・`ui/RecordLabels.kt`・`map/MapData.kt`・`map/RouteMap.kt`・`ui/RecordsRoutes.kt`・`ui/RecordsScreens.kt`
- Test: `ui/RecordLabelsTest.kt`・`map/MapDataTest.kt`・`store/RoomRecordsTest.kt`

**Interfaces:**
- Consumes: Task 1 のメモの列。Task 4 の `RoomSyncStore.askMemoSent`（テスト）
- Produces:
  - `AskRecord.memo: String? = null`（`toRecord` が写す。`toEntity` は写さない＝一巡が保存してもメモを上書きしない）
  - `RideRow.memosLeft`。`saveState` の `pointsLeft` に `memosLeft` を足して渡す
  - `RideRowUi.memo: Boolean = false`・`TimelineRow.Ask.memo: Boolean = false`・`AskDetailUi.memo: String? = null`・`RideDetailUi.memo: String? = null`・`MapPin.memo: Boolean = false`
  - `pinIcon(number, selected, memo = false)`・`pinBitmap(number, selected, density, memo = false)`
  - `askMemoTarget(asks: List<AskRecord>, askId: String, zone: ZoneId): String?`

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt b/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt
index bbdf41d..58d7cad 100644
--- a/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt
+++ b/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt
@@ -55,4 +55,16 @@ class MapDataTest {
     val at = LatLon(35.1, 139.1)
     assertEquals(listOf(at), rideMap(points, ended = true, pins = listOf(MapPin("a1", 1, at)), faint = true, focus = at).extent)
   }
+
+  // US-D-04.005: a pin whose ask has a memo takes an image of its own, selected or not.
+  @Test
+  fun a_pin_with_a_memo_takes_its_own_image() {
+    val map = rideMap(points, ended = true, pins = listOf(MapPin("a1", 1, LatLon(35.0, 139.0), memo = true), MapPin("a2", 2, LatLon(35.1, 139.1))))
+    val icons = { selected: String? ->
+      Json.parseToJsonElement(pinsJson(map, selected)).jsonObject["features"]!!.jsonArray
+        .map { it.jsonObject["properties"]!!.jsonObject["icon"]!!.jsonPrimitive.content }
+    }
+    assertEquals(listOf("pin-1-memo", "pin-2"), icons(null))
+    assertEquals(listOf("pin-sel-1-memo", "pin-2"), icons("a1"))
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
index fd222b8..06dd572 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
@@ -87,4 +87,19 @@ class RoomRecordsTest {
     assertEquals(listOf(1_500L), records.route("r1").map { it.t })
     assertNull(records.ride("r9").first())
   }
+
+  // Slice 3 spec §5.3: a memo of one of the ride's asks not yet taken leaves the ride "未送信あり".
+  @Test
+  fun a_memo_not_yet_sent_leaves_the_ride_unsent() = runBlocking {
+    val ended = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(4_000, EndReason.MANUAL, 4_000)
+    rides.save(ended)
+    log.save(ask("a1", 1_200, "r1"))
+    sync.rideSent("r1", ended.updatedAt)
+    assertEquals(SaveState.SAVED, records.list.first().single().saveState)
+    db.asks().writeMemo("a1", "また来たい", 5_000)
+    assertEquals(SaveState.UNSENT, records.list.first().single().saveState)
+    assertEquals("また来たい", records.asks("r1").first().single().memo)
+    sync.askMemoSent("a1", 5_000)
+    assertEquals(SaveState.SAVED, records.list.first().single().saveState)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
index 823b98c..7e835de 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
@@ -21,11 +21,11 @@ class RecordLabelsTest {
 
   private fun ms(day: Int, hour: Int, minute: Int, month: Int = 10) = ZonedDateTime.of(2026, month, day, hour, minute, 0, 0, zone).toInstant().toEpochMilli()
 
-  private fun ask(id: String, at: Long, transcript: String? = "右手の山は？", newConversation: Boolean = false, failure: String? = null) = AskRecord(
+  private fun ask(id: String, at: Long, transcript: String? = "右手の山は？", newConversation: Boolean = false, failure: String? = null, memo: String? = null) = AskRecord(
     askId = id, askedAt = at, answeredAt = at + 5_000, transcript = transcript, answer = "金時山です。",
     latitude = 35.2, longitude = 139.0, address = "神奈川県足柄下郡箱根町仙石原", headingDegrees = 45.0, input = "voice",
     conversationId = "c1", newConversation = newConversation,
-    outcome = if (failure == null) AskOutcome.ANSWERED else AskOutcome.FAILED, failure = failure, rideId = "r1",
+    outcome = if (failure == null) AskOutcome.ANSWERED else AskOutcome.FAILED, failure = failure, rideId = "r1", memo = memo,
   )
 
   // 16 Oct 08:58 – 09:44, paused until 10:02, then 10:02 – 10:46.
@@ -155,4 +155,24 @@ class RecordLabelsTest {
     assertEquals("国道1号線沿い", shortPlace("国道1号線沿い"))
     assertEquals("場所不明", shortPlace(null))
   }
+
+  // US-D-04.005: the memos show in the list, the timeline, the pins and SC-07.
+  @Test
+  fun memos_are_marked_where_the_rider_looks_for_them() {
+    val ride = newRide("r1", "箱根", ms(16, 8, 58), 7, 24 * HOUR_MS).end(ms(16, 10, 46), EndReason.MANUAL, ms(16, 10, 46))
+    assertEquals(false, rideRow(RideListItem(ride, 0, SaveState.SAVED), ms(17, 0, 0), zone).memo)
+    assertEquals(true, rideRow(RideListItem(ride.copy(memo = "また来たい"), 0, SaveState.SAVED), ms(17, 0, 0), zone).memo)
+    val asks = listOf(ask("a1", ms(16, 9, 41), memo = "給油した"), ask("a2", ms(16, 10, 30)))
+    assertEquals(listOf(true, false), rideTimeline(ride, asks, zone).filterIsInstance<TimelineRow.Ask>().map { it.memo })
+    assertEquals(listOf(true, false), askPins(asks).map { it.memo })
+    assertEquals("給油した", askDetail(asks, "a1", zone)?.memo)
+    assertNull(askDetail(asks, "a2", zone)?.memo)
+  }
+
+  @Test
+  fun sc_08_names_the_conversation_it_writes_for() {
+    val asks = listOf(ask("a1", ms(16, 9, 41)), ask("a2", ms(16, 10, 30)))
+    assertEquals("会話 2 · 10:30 足柄下郡箱根町仙石原", askMemoTarget(asks, "a2", zone))
+    assertNull(askMemoTarget(asks, "a9", zone))
+  }
 }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordLabelsTest' --tests '*MapDataTest' --tests '*RoomRecordsTest' --rerun > /tmp/trv2-t5.log 2>&1; grep -c '^e:' /tmp/trv2-t5.log`
Expected: コンパイルで落ちる（`memo` の項目と `askMemoTarget` が無い）

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt b/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
index 184bcc7..5cea002 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
@@ -34,6 +34,8 @@ data class AskRecord(
   val failure: String?,
   /** The ride that was recording when the ask started (slice 2 spec §4.6). */
   val rideId: String?,
+  /** The conversation's memo (US-D-04.001). The ask loop never sets it; only SC-08 does, through AskEdits. */
+  val memo: String? = null,
 )
 
 /** What the loop knows once the Backend has taken the ask in. */
diff --git a/app/src/main/java/com/touringproject/v2/map/MapData.kt b/app/src/main/java/com/touringproject/v2/map/MapData.kt
index 7dbbca2..7aa3b9c 100644
--- a/app/src/main/java/com/touringproject/v2/map/MapData.kt
+++ b/app/src/main/java/com/touringproject/v2/map/MapData.kt
@@ -12,8 +12,8 @@ import kotlinx.serialization.json.put
 
 data class LatLon(val lat: Double, val lon: Double)
 
-/** A numbered ask on the map; number is the ask's place in the ride's timeline. */
-data class MapPin(val askId: String, val number: Int, val at: LatLon)
+/** A numbered ask on the map; number is the ask's place in the ride's timeline. memo: the ask has a memo (US-D-04.005). */
+data class MapPin(val askId: String, val number: Int, val at: LatLon, val memo: Boolean = false)
 
 /**
  * routes has one line per recorded segment that has points; pauses joins the last point of a segment to the first
@@ -92,10 +92,11 @@ fun pinsJson(data: MapData, selected: String?): String = collection(
       point(pin.at),
       buildJsonObject {
         put("askId", pin.askId)
-        put("icon", pinIcon(pin.number, pin.askId == selected))
+        put("icon", pinIcon(pin.number, pin.askId == selected, pin.memo))
       },
     )
   },
 )
 
-fun pinIcon(number: Int, selected: Boolean): String = if (selected) "pin-sel-$number" else "pin-$number"
+fun pinIcon(number: Int, selected: Boolean, memo: Boolean = false): String =
+  (if (selected) "pin-sel-$number" else "pin-$number") + if (memo) "-memo" else ""
diff --git a/app/src/main/java/com/touringproject/v2/map/RouteMap.kt b/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
index ddcb5cf..fdc5959 100644
--- a/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
+++ b/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
@@ -66,8 +66,11 @@ private val JAPAN = LatLng(36.2, 138.25)
 
 private fun styleJson(context: Context) = context.assets.open(STYLE_ASSET).bufferedReader().use { it.readText() }
 
-/** A teardrop pin with its number, the tip at the bottom, as in the mock. */
-fun pinBitmap(number: Int, selected: Boolean, density: Float): Bitmap {
+/**
+ * A teardrop pin with its number, the tip at the bottom, as in the mock. memo adds a small white dot at its top right:
+ * the ask has a memo (US-D-04.005).
+ */
+fun pinBitmap(number: Int, selected: Boolean, density: Float, memo: Boolean = false): Bitmap {
   val radius = (if (selected) 16f else 13f) * density
   val stroke = 2f * density
   val tail = radius * 0.8f
@@ -93,6 +96,13 @@ fun pinBitmap(number: Int, selected: Boolean, density: Float): Bitmap {
     textAlign = Paint.Align.CENTER
   }
   canvas.drawText(number.toString(), cx, cy - (text.descent() + text.ascent()) / 2, text)
+  if (memo) {
+    val dot = radius * 0.32f
+    val dx = cx + radius * 0.7f
+    val dy = cy - radius * 0.7f
+    canvas.drawCircle(dx, dy, dot + stroke, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = if (selected) PIN_SELECTED_COLOR else PIN_COLOR })
+    canvas.drawCircle(dx, dy, dot, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = android.graphics.Color.WHITE })
+  }
   return bitmap
 }
 
@@ -142,8 +152,8 @@ private fun mapJson(data: MapData, selected: String?) = MapJson(routesJson(data)
 private fun draw(style: Style, data: MapData, json: MapJson, density: Float) {
   data.pins.forEach { pin ->
     listOf(false, true).forEach { sel ->
-      val name = pinIcon(pin.number, sel)
-      if (style.getImage(name) == null) style.addImage(name, pinBitmap(pin.number, sel, density))
+      val name = pinIcon(pin.number, sel, pin.memo)
+      if (style.getImage(name) == null) style.addImage(name, pinBitmap(pin.number, sel, density, pin.memo))
     }
   }
   style.getSourceAs<GeoJsonSource>("routes")?.setGeoJson(json.routes)
diff --git a/app/src/main/java/com/touringproject/v2/records/Records.kt b/app/src/main/java/com/touringproject/v2/records/Records.kt
index aab72e3..3197785 100644
--- a/app/src/main/java/com/touringproject/v2/records/Records.kt
+++ b/app/src/main/java/com/touringproject/v2/records/Records.kt
@@ -15,7 +15,8 @@ enum class SaveState { RECORDING, UNSENT, SAVED }
 
 /**
  * "記録中" while the ride records or is paused; "未送信あり" while its newest version has not been taken (a refused one
- * included) or a point has not gone or was refused; "保存済み" otherwise (slice 2 spec §5.4).
+ * included) or something of it has not gone or was refused (pointsLeft: a point, or the memo of one of its asks;
+ * slice 3 spec §5.3); "保存済み" otherwise (slice 2 spec §5.4).
  */
 fun saveState(status: RideStatus, updatedAt: Long, sentUpdatedAt: Long?, pointsLeft: Boolean): SaveState = when {
   status != RideStatus.ENDED -> SaveState.RECORDING
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index da55667..dc21d36 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -217,12 +217,16 @@ data class RideWithSegments(
   @Relation(parentColumn = "id", entityColumn = "rideId") val segments: List<SegmentEntity>,
 )
 
-/** A ride as SC-05 lists it. pointsLeft is true while one of its points has not been taken (unsent or refused). */
+/**
+ * A ride as SC-05 lists it. pointsLeft is true while one of its points has not been taken (unsent or refused);
+ * memosLeft while the memo of one of its asks has not been taken (slice 3 spec §5.3).
+ */
 data class RideRow(
   @Embedded val ride: RideEntity,
   @Relation(parentColumn = "id", entityColumn = "rideId") val segments: List<SegmentEntity>,
   val questions: Int,
   val pointsLeft: Boolean,
+  val memosLeft: Boolean,
 )
 
 @Dao
@@ -241,7 +245,9 @@ interface RideDao {
   @Query(
     "SELECT *, (SELECT COUNT(*) FROM asks WHERE asks.rideId = rides.id) AS questions, " +
       "(EXISTS (SELECT 1 FROM route_points WHERE chunk IS NULL AND route_points.rideId = rides.id) OR " +
-      "EXISTS (SELECT 1 FROM route_points WHERE refused = 1 AND route_points.rideId = rides.id)) AS pointsLeft FROM rides",
+      "EXISTS (SELECT 1 FROM route_points WHERE refused = 1 AND route_points.rideId = rides.id)) AS pointsLeft, " +
+      "EXISTS (SELECT 1 FROM asks WHERE asks.rideId = rides.id AND asks.memoUpdatedAt IS NOT NULL AND " +
+      "(asks.memoSentUpdatedAt IS NULL OR asks.memoSentUpdatedAt < asks.memoUpdatedAt)) AS memosLeft FROM rides",
   )
   fun rows(): Flow<List<RideRow>>
 
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
index 06a5f3b..9e972fe 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
@@ -26,6 +26,7 @@ fun AskEntity.toRecord() = AskRecord(
   outcome = AskOutcome.valueOf(status.uppercase()),
   failure = failure,
   rideId = rideId,
+  memo = memo,
 )
 
 /** What the records screens read (SC-05, SC-06, SC-07). Each Flow follows the database as it changes. */
@@ -34,7 +35,7 @@ class RoomRecords(private val rides: RideDao, private val asks: AskDao) {
     orderRides(
       rows.map { row ->
         val ride = row.ride.toRide(row.segments.sortedBy { it.seq })
-        RideListItem(ride, row.questions, saveState(ride.status, ride.updatedAt, row.ride.sentUpdatedAt, row.pointsLeft))
+        RideListItem(ride, row.questions, saveState(ride.status, ride.updatedAt, row.ride.sentUpdatedAt, row.pointsLeft || row.memosLeft))
       },
     )
   }
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
index 7569a9b..763a078 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
@@ -57,7 +57,16 @@ fun saveLabel(item: RideListItem): String = when (item.saveState) {
   SaveState.SAVED -> "保存済み"
 }
 
-data class RideRowUi(val id: String, val name: String, val date: String, val stats: String, val state: String, val saved: Boolean)
+/** memo: the ride has a memo (US-D-04.005). */
+data class RideRowUi(
+  val id: String,
+  val name: String,
+  val date: String,
+  val stats: String,
+  val state: String,
+  val saved: Boolean,
+  val memo: Boolean = false,
+)
 
 /** One ride of SC-05: 52.8 km · 1:26 · 質問 4 · ⏸ 1 (the pauses only when there were some). */
 fun rideRow(item: RideListItem, now: Long, zone: ZoneId): RideRowUi {
@@ -72,6 +81,7 @@ fun rideRow(item: RideListItem, now: Long, zone: ZoneId): RideRowUi {
   return RideRowUi(
     ride.id, ride.name, "${rideDateLabel(ride, now, zone)} · ${rideSpanLabel(ride, zone)}", stats, saveLabel(item),
     item.saveState == SaveState.SAVED,
+    memo = ride.memo != null,
   )
 }
 
@@ -121,7 +131,7 @@ fun askPins(asks: List<AskRecord>): List<MapPin> {
   return asks.sortedBy { it.askedAt }.mapNotNull { ask ->
     val lat = ask.latitude ?: return@mapNotNull null
     val lon = ask.longitude ?: return@mapNotNull null
-    MapPin(ask.askId, numbers.getValue(ask.askId), LatLon(lat, lon))
+    MapPin(ask.askId, numbers.getValue(ask.askId), LatLon(lat, lon), memo = ask.memo != null)
   }
 }
 
@@ -140,7 +150,16 @@ fun askText(ask: AskRecord): String = ask.transcript?.takeIf { it.isNotBlank() }
 
 sealed interface TimelineRow {
   data class Day(val label: String) : TimelineRow
-  data class Ask(val askId: String, val number: Int, val time: String, val place: String, val text: String, val failed: Boolean) : TimelineRow
+  /** memo: the ask has a memo (US-D-04.005). */
+  data class Ask(
+    val askId: String,
+    val number: Int,
+    val time: String,
+    val place: String,
+    val text: String,
+    val failed: Boolean,
+    val memo: Boolean = false,
+  ) : TimelineRow
   data class Pause(val label: String) : TimelineRow
   data object NewConversation : TimelineRow
 }
@@ -186,7 +205,7 @@ fun rideTimeline(ride: Ride, asks: List<AskRecord>, zone: ZoneId): List<Timeline
         asked = true
         rows += TimelineRow.Ask(
           ask.askId, numbers.getValue(ask.askId), TIME.format(at(ask.askedAt, zone)), shortPlace(ask.address), askText(ask),
-          ask.outcome == AskOutcome.FAILED,
+          ask.outcome == AskOutcome.FAILED, memo = ask.memo != null,
         )
       }
       is Event.PauseAt -> rows += TimelineRow.Pause(
@@ -226,6 +245,8 @@ data class AskDetailUi(
   val failure: String?,
   val previous: String?,
   val next: String?,
+  /** The conversation's memo (SC-07); null when it has none. */
+  val memo: String? = null,
 )
 
 /** askId's place among the asks it was opened from (the ride's): 会話 3 / 5, and the asks before and after it. */
@@ -246,6 +267,7 @@ fun askDetail(asks: List<AskRecord>, askId: String, zone: ZoneId): AskDetailUi?
     failure = if (ask.outcome == AskOutcome.FAILED) failureLabel(ask.failure) else null,
     previous = ordered.getOrNull(i - 1)?.askId,
     next = ordered.getOrNull(i + 1)?.askId,
+    memo = ask.memo,
   )
 }
 
@@ -257,3 +279,9 @@ fun pinCard(asks: List<AskRecord>, askId: String, zone: ZoneId): PinCardUi? {
   val number = askNumbers(asks).getValue(askId)
   return PinCardUi(askId, "$number · ${TIME.format(at(ask.askedAt, zone))} · ${shortPlace(ask.address)}", askText(ask), ask.answer?.ifBlank { null })
 }
+
+/** What SC-08 says it is writing for an ask: 会話 3 · 09:41 箱根町仙石原 (the mock). null when the ask is not among them. */
+fun askMemoTarget(asks: List<AskRecord>, askId: String, zone: ZoneId): String? {
+  val ask = asks.firstOrNull { it.askId == askId } ?: return null
+  return "会話 ${askNumbers(asks).getValue(askId)} · ${TIME.format(at(ask.askedAt, zone))} ${shortPlace(ask.address)}"
+}
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
index 3267da7..f85b61f 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
@@ -50,6 +50,7 @@ fun rideDetailUi(ride: Ride, asks: List<AskRecord>, route: List<RoutePoint>, now
   timeline = rideTimeline(ride, asks, zone),
   map = rideMap(route, ride.status == RideStatus.ENDED, askPins(asks)),
   cards = asks.mapNotNull { pinCard(asks, it.askId, zone) }.associateBy { it.askId },
+  memo = ride.memo,
 )
 
 @Composable
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
index 57aec7a..0f639cd 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
@@ -113,6 +113,8 @@ data class RideDetailUi(
   val timeline: List<TimelineRow>,
   val map: MapData,
   val cards: Map<String, PinCardUi>,
+  /** The ride's memo (SC-06); null when it has none. */
+  val memo: String? = null,
 )
 
 /**
PATCH
````

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t5.log 2>&1; tail -1 /tmp/trv2-t5.log`
Expected: `BUILD SUCCESSFUL`（`424` 件。数は Task 8 の数え方で見る）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskRecord.kt app/src/main/java/com/touringproject/v2/map/MapData.kt app/src/main/java/com/touringproject/v2/map/RouteMap.kt app/src/main/java/com/touringproject/v2/records/Records.kt app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomRecords.kt app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt app/src/test/java/com/touringproject/v2/map/MapDataTest.kt app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
git commit -m "feat: mark the rides, asks and pins that have a memo, and count unsent memos"
```

---

### Task 6: 画面: SC-08・DL-01 と、SC-02・SC-05〜SC-07 へのつなぎ

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Create: `ui/MemoScreen.kt`・`ui/DeleteDialog.kt`
- Modify: `ui/RecordsScreens.kt`・`ui/RecordsRoutes.kt`・`ui/RideScreens.kt`・`ui/AppUi.kt`・`ui/RecordingsScreen.kt`・`ui/SettingsScreens.kt`・`AppGraph.kt`
- Test: `ui/MemoScreenTest.kt`（新規）・`ui/RecordsScreensTest.kt`・`ui/RideScreensTest.kt`

**Interfaces:**
- Consumes: Task 2 の `RideController.memo`・`delete`・`AskEdits`・`RoomAskEdits`・`cutMemo`・`memoText`・`MEMO_MAX`。Task 5 の `askMemoTarget` と `memo` の項目
- Produces:
  - `MemoScreen(target: String, initial: String?, onSave: suspend (String?) -> Boolean, onClose: () -> Unit, modifier)`
  - `DeleteDialog(title, text, confirm, onConfirm, onDismiss)`・`DeleteDialog(kind: DeleteKind, ...)`・`DeleteKind.ASK`・`RIDE`（plan 3 が地点メモを足す）
  - `RideDetailScreen(..., onMemo = {}, onDelete = { false })`・`AskDetailScreen(..., onMemo = {}, onDelete = { false })`・`RideCard(..., onMemo = {})`
  - `RideMemoRoute`・`AskMemoRoute`。`AskDetailRoute` は `edits: AskEdits` と `onMemo` を、`RideDetailRoute` は `onMemo` を受ける
  - `AppGraph.askEdits`。`AppUi` の `RideMemoKey(rideId)`・`AskMemoKey(rideId, askId)`

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/MemoScreenTest.kt b/app/src/test/java/com/touringproject/v2/ui/MemoScreenTest.kt
new file mode 100644
index 0000000..b8ab41e
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/ui/MemoScreenTest.kt
@@ -0,0 +1,106 @@
+package com.touringproject.v2.ui
+
+import androidx.activity.ComponentActivity
+import androidx.compose.ui.test.assertTextEquals
+import androidx.compose.ui.test.junit4.createAndroidComposeRule
+import androidx.compose.ui.test.onNodeWithTag
+import androidx.compose.ui.test.onNodeWithText
+import androidx.compose.ui.test.performClick
+import androidx.compose.ui.test.performTextReplacement
+import androidx.test.ext.junit.runners.AndroidJUnit4
+import kotlinx.coroutines.CompletableDeferred
+import org.junit.Assert.assertEquals
+import org.junit.Rule
+import org.junit.Test
+import org.junit.runner.RunWith
+import org.robolectric.shadows.ShadowToast
+
+// SC-08 (slice 3 spec §7.2).
+@RunWith(AndroidJUnit4::class)
+class MemoScreenTest {
+  @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()
+
+  private val saved = mutableListOf<String?>()
+  private var closed = 0
+
+  private fun show(initial: String? = null, result: Boolean = true) = rule.setContent {
+    MemoScreen("会話 3 · 09:41 箱根町仙石原", initial, { saved += it; result }, { closed++ })
+  }
+
+  private fun back() = rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
+
+  @Test
+  fun a_memo_is_saved_trimmed_and_the_screen_closes() {
+    show()
+    rule.onNodeWithTag("memoTarget").assertTextEquals("会話 3 · 09:41 箱根町仙石原")
+    rule.onNodeWithTag("memoInput").performTextReplacement("  また来たい  ")
+    rule.onNodeWithTag("memoSave").performClick()
+    rule.waitForIdle()
+    assertEquals(listOf<String?>("また来たい"), saved)
+    assertEquals(1, closed)
+  }
+
+  @Test
+  fun saving_an_empty_memo_removes_it() {
+    show(initial = "消す前")
+    rule.onNodeWithTag("memoInput").performTextReplacement(" ")
+    rule.onNodeWithTag("memoSave").performClick()
+    rule.waitForIdle()
+    assertEquals(listOf<String?>(null), saved)
+  }
+
+  @Test
+  fun the_field_keeps_2000_characters_and_counts_them() {
+    show()
+    rule.onNodeWithTag("memoInput").performTextReplacement("あ".repeat(2100))
+    rule.onNodeWithTag("memoCount").assertTextEquals("2000 / 2000字")
+  }
+
+  @Test
+  fun closing_without_a_change_does_not_ask() {
+    show(initial = "そのまま")
+    rule.onNodeWithTag("memoClose").performClick()
+    assertEquals(1, closed)
+    rule.onNodeWithText("変更を破棄しますか？").assertDoesNotExist()
+  }
+
+  // US-D-04.004: a change is not thrown away without asking, by ✕ or by Back.
+  @Test
+  fun closing_with_a_change_asks_first_and_can_go_on_writing() {
+    show(initial = "前のメモ")
+    rule.onNodeWithTag("memoInput").performTextReplacement("書きかけ")
+    rule.onNodeWithTag("memoClose").performClick()
+    rule.onNodeWithText("変更を破棄しますか？").assertExists()
+    rule.onNodeWithText("書き続ける").performClick()
+    assertEquals(0, closed)
+    back()
+    rule.waitForIdle()
+    rule.onNodeWithTag("memoDiscard").performClick()
+    assertEquals(1, closed)
+    assertEquals(emptyList<String?>(), saved)
+  }
+
+  // Slice 3 spec §8: a memo that could not be written is told, and what was typed stays.
+  @Test
+  fun a_memo_that_cannot_be_saved_is_told_and_kept() {
+    show(result = false)
+    rule.onNodeWithTag("memoInput").performTextReplacement("書けない")
+    rule.onNodeWithTag("memoSave").performClick()
+    rule.waitForIdle()
+    assertEquals(0, closed)
+    assertEquals("保存できませんでした", ShadowToast.getTextOfLatestToast())
+    rule.onNodeWithText("書けない").assertExists()
+  }
+
+  @Test
+  fun the_save_button_waits_for_the_save_in_progress() {
+    val gate = CompletableDeferred<Boolean>()
+    rule.setContent { MemoScreen("走行のメモ", null, { saved += it; gate.await() }, { closed++ }) }
+    rule.onNodeWithTag("memoInput").performTextReplacement("一度だけ")
+    rule.onNodeWithTag("memoSave").performClick()
+    rule.onNodeWithTag("memoSave").performClick()
+    gate.complete(true)
+    rule.waitForIdle()
+    assertEquals(listOf<String?>("一度だけ"), saved)
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
index 3635f17..9fe2aa7 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
@@ -21,6 +21,7 @@ import androidx.compose.ui.test.onChildAt
 import androidx.compose.ui.test.onNodeWithTag
 import androidx.compose.ui.test.onNodeWithText
 import androidx.compose.ui.test.performClick
+import androidx.compose.ui.test.performScrollTo
 import androidx.compose.ui.test.performScrollToNode
 import androidx.compose.ui.test.performTextReplacement
 import androidx.navigation3.runtime.NavEntry
@@ -49,10 +50,10 @@ class RecordsScreensTest {
 
   private val row = RideRowUi("r1", "箱根", "10月16日（金） · 08:58〜10:46", "52.8 km · 1:30 · 質問 2 · ⏸ 1", "保存済み", true)
 
-  private fun detail(autoEnded: Boolean = false) = RideDetailUi(
+  private fun detail(autoEnded: Boolean = false, recording: Boolean = false, memo: String? = null) = RideDetailUi(
     name = "箱根",
     summary = RideSummaryUi("10月16日（金）", "08:58〜10:46", "1:30", "52.8 km", "2", "一時停止 1回（18分）は走行時間に含めません", autoEnded),
-    recording = false,
+    recording = recording,
     timeline = listOf(
       TimelineRow.Ask("a1", 1, "09:41", "箱根町仙石原", "右手の山は？", false),
       TimelineRow.Pause("⏸ 一時停止 09:44〜10:02（18分）"),
@@ -61,6 +62,7 @@ class RecordsScreensTest {
     ),
     map = MapData(emptyList(), emptyList(), null, null, listOf(MapPin("a1", 1, LatLon(35.2, 139.0)), MapPin("a2", 2, LatLon(35.3, 138.9)))),
     cards = mapOf("a1" to PinCardUi("a1", "1 · 09:41 · 箱根町仙石原", "右手の山は？", "金時山です。")),
+    memo = memo,
   )
 
   private fun back() = rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
@@ -228,4 +230,104 @@ class RecordsScreensTest {
     assertEquals(listOf("list", "ride"), stack.toList())
     rule.onNodeWithTag("timeline").assertExists()
   }
+
+  // US-D-04.005: SC-05 marks a ride that has a memo.
+  @Test
+  fun the_list_marks_a_ride_with_a_memo() {
+    rule.setContent { RideListScreen(listOf(RideSection("2026年10月", listOf(row, row.copy(id = "r2", memo = true)))), {}) }
+    rule.onNodeWithTag("rideMemoMark-r2", useUnmergedTree = true).assertExists()
+    rule.onNodeWithTag("rideMemoMark-r1", useUnmergedTree = true).assertDoesNotExist()
+  }
+
+  @Test
+  fun the_ride_shows_its_memo_which_opens_sc_08_and_without_one_offers_to_write_it() {
+    var memos = 0
+    var memo by mutableStateOf<String?>(null)
+    rule.setContent { RideDetailScreen(detail(memo = memo), fakeMap, true, {}, {}, {}, { true }, {}, onMemo = { memos++ }) }
+    rule.onNodeWithTag("timeline").performScrollToNode(hasTestTag("rideMemoAdd"))
+    rule.onNodeWithTag("rideMemoAdd").performClick()
+    memo = "峠の茶屋が良かった"
+    rule.waitForIdle()
+    rule.onNodeWithTag("timeline").performScrollToNode(hasTestTag("rideMemo"))
+    rule.onNodeWithTag("rideMemo").performClick()
+    rule.onNodeWithTag("rideMenu").performClick()
+    rule.onNodeWithTag("rideMemoMenu").performClick()
+    assertEquals(3, memos)
+    rule.onNodeWithText("峠の茶屋が良かった").assertExists()
+  }
+
+  @Test
+  fun the_timeline_marks_an_ask_with_a_memo() {
+    val withMemo = detail().let { it.copy(timeline = listOf(TimelineRow.Ask("a1", 1, "09:41", "箱根町仙石原", "右手の山は？", false, memo = true))) }
+    rule.setContent { RideDetailScreen(withMemo, fakeMap, true, {}, {}, {}, { true }, {}) }
+    rule.onNodeWithTag("timeline").performScrollToNode(hasTestTag("ask-a1"))
+    rule.onNodeWithText("09:41 · 箱根町仙石原 · 📝").assertExists()
+  }
+
+  // US-D-06.002, US-D-06.003: an ended ride is deleted after DL-01 says what goes.
+  @Test
+  fun an_ended_ride_is_deleted_after_the_confirmation() {
+    var deletes = 0
+    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, { true }, {}, onDelete = { deletes++; true }) }
+    rule.onNodeWithTag("rideMenu").performClick()
+    rule.onNodeWithTag("deleteRide").performClick()
+    rule.onNodeWithText("ルート・走行のメモと、その走行の質問・地点メモが削除されます。元に戻せません。").assertExists()
+    rule.onNodeWithTag("deleteCancel").performClick()
+    assertEquals(0, deletes)
+    rule.onNodeWithTag("rideMenu").performClick()
+    rule.onNodeWithTag("deleteRide").performClick()
+    rule.onNodeWithTag("deleteGo").performClick()
+    rule.waitForIdle()
+    assertEquals(1, deletes)
+  }
+
+  // Slice 3 spec §2: the ride recording or paused is ended first.
+  @Test
+  fun the_ride_recording_cannot_be_deleted() {
+    rule.setContent { RideDetailScreen(detail(recording = true), fakeMap, true, {}, {}, {}, { true }, {}) }
+    rule.onNodeWithTag("rideMenu").performClick()
+    rule.onNodeWithTag("renameRide").assertExists()
+    rule.onNodeWithTag("deleteRide").assertDoesNotExist()
+  }
+
+  @Test
+  fun a_ride_that_could_not_be_deleted_is_told() {
+    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, { true }, {}, onDelete = { false }) }
+    rule.onNodeWithTag("rideMenu").performClick()
+    rule.onNodeWithTag("deleteRide").performClick()
+    rule.onNodeWithTag("deleteGo").performClick()
+    rule.waitForIdle()
+    assertEquals("削除できませんでした", ShadowToast.getTextOfLatestToast())
+  }
+
+  private val answered = AskDetailUi("会話 1 / 2", "10月16日（金） 09:41", "神奈川県箱根町仙石原", "停車中", "🎤 声で質問", "右手の山は？", "金時山です。", null, null, "a2")
+
+  @Test
+  fun the_ask_shows_its_memo_and_opens_sc_08() {
+    var memos = 0
+    rule.setContent { AskDetailScreen(answered.copy(memo = "給油した"), null, fakeMap, "a1", {}, {}, onMemo = { memos++ }) }
+    rule.onNodeWithText("給油した").assertExists()
+    rule.onNodeWithTag("askMemo").performScrollTo().performClick()
+    assertEquals(1, memos)
+  }
+
+  @Test
+  fun an_ask_without_a_memo_offers_to_write_one() {
+    var memos = 0
+    rule.setContent { AskDetailScreen(answered, null, fakeMap, "a1", {}, {}, onMemo = { memos++ }) }
+    rule.onNodeWithTag("askMemoAdd").performScrollTo().performClick()
+    assertEquals(1, memos)
+  }
+
+  // US-D-06.001: an ask is deleted after DL-01.
+  @Test
+  fun an_ask_is_deleted_after_the_confirmation() {
+    var deletes = 0
+    rule.setContent { AskDetailScreen(answered, null, fakeMap, "a1", {}, {}, onDelete = { deletes++; true }) }
+    rule.onNodeWithTag("deleteAsk").performScrollTo().performClick()
+    rule.onNodeWithText("質問・回答・メモが削除されます。元に戻せません。").assertExists()
+    rule.onNodeWithTag("deleteGo").performClick()
+    rule.waitForIdle()
+    assertEquals(1, deletes)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt
index 301ddab..d39bc48 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt
@@ -147,4 +147,13 @@ class RideScreensTest {
     rule.onNodeWithText("走行を続ける").performClick()
     assertEquals(1, dismissed)
   }
+
+  // Slice 3 spec §7.1: the ride's memo opens from the card while it records or is paused.
+  @Test
+  fun the_card_opens_the_rides_memo() {
+    var memos = 0
+    rule.setContent { RideCard(RideCardUi("箱根", true, "1:26", "52.8 km", "4"), {}, {}, {}, {}, onMemo = { memos++ }) }
+    rule.onNodeWithTag("rideMemo").performClick()
+    assertEquals(1, memos)
+  }
 }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*MemoScreenTest' --tests '*RecordsScreensTest' --tests '*RideScreensTest' --rerun > /tmp/trv2-t6.log 2>&1; grep -c '^e:' /tmp/trv2-t6.log`
Expected: コンパイルで落ちる（`MemoScreen` と新しい引数が無い）

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index a2d4c9b..b4115ee 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -50,6 +50,7 @@ import com.touringproject.v2.settings.KeystoreCipher
 import com.touringproject.v2.settings.SettingsRepository
 import com.touringproject.v2.settings.maxRecordingChanges
 import com.touringproject.v2.store.RideDatabase
+import com.touringproject.v2.store.RoomAskEdits
 import com.touringproject.v2.store.RoomAskLog
 import com.touringproject.v2.store.RoomRecords
 import com.touringproject.v2.store.RoomRideStore
@@ -105,6 +106,9 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     log = { event, data -> Log.i("trv2.sync", "$event $data") },
   )
 
+  /** SC-07 and SC-08 change kept asks through here; each change is something new to send (slice 3 spec §5.1). */
+  val askEdits = RoomAskEdits(database.asks(), System::currentTimeMillis, sync::request) { message, e -> Log.w("trv2.ask", message, e) }
+
   val rides = RideController(
     RideDeps(
       now = System::currentTimeMillis,
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 722bad3..40bcfab 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -54,6 +54,11 @@ import kotlinx.serialization.Serializable
 @Serializable data object RecordsKey : NavKey
 @Serializable data class RideKey(val rideId: String) : NavKey
 @Serializable data class AskKey(val rideId: String, val askId: String) : NavKey
+@Serializable data class RideMemoKey(val rideId: String) : NavKey
+@Serializable data class AskMemoKey(val rideId: String, val askId: String) : NavKey
+
+/** SC-08 covers the tabs, as the mock draws it. */
+private fun coversTabs(key: NavKey?) = key is RideMemoKey || key is AskMemoKey
 
 private enum class RideSheet { START, END }
 
@@ -108,7 +113,7 @@ fun AppUi(graph: AppGraph) {
         BackHandler(enabled = tabs.onAnotherTabsFirst) { tabs.back() }
         Scaffold(
           containerColor = MaterialTheme.colorScheme.background,
-          bottomBar = { if (tabsShown(state.phase) && !mapFull) TabBar(tabs.tab, tabs::press) },
+          bottomBar = { if (tabsShown(state.phase) && !mapFull && !coversTabs(tabs.current.lastOrNull())) TabBar(tabs.tab, tabs::press) },
         ) { inner ->
           val screens = entryProvider<NavKey> {
               entry<HomeKey> {
@@ -144,6 +149,7 @@ fun AppUi(graph: AppGraph) {
                         scope.launch { if (graph.rides.resume()) Toast.makeText(context, "再開しました", Toast.LENGTH_SHORT).show() }
                       },
                       onEnd = { sheet = RideSheet.END },
+                      onMemo = { ride?.let { tabs.push(RideMemoKey(it.id)) } },
                     )
                   },
                 )
@@ -165,18 +171,26 @@ fun AppUi(graph: AppGraph) {
                   onBack = { tabs.back() },
                   onAsk = { tabs.push(AskKey(key.rideId, it)) },
                   onFullMap = { mapFull = it },
+                  onMemo = { tabs.push(RideMemoKey(key.rideId)) },
                   modifier = Modifier.safeDrawingPadding(),
                 )
               }
               entry<AskKey> { key ->
                 AskDetailRoute(
-                  graph.records, key.rideId, key.askId,
+                  graph.records, graph.askEdits, key.rideId, key.askId,
                   onBack = { tabs.back() },
                   // ‹ › stay within the ride's asks: the shown ask is swapped, so Back still goes to SC-06.
                   onMove = { other -> tabs.current[tabs.current.lastIndex] = AskKey(key.rideId, other) },
+                  onMemo = { tabs.push(AskMemoKey(key.rideId, key.askId)) },
                   modifier = Modifier.safeDrawingPadding(),
                 )
               }
+              entry<RideMemoKey> { key ->
+                RideMemoRoute(graph.records, graph.rides, key.rideId, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding())
+              }
+              entry<AskMemoKey> { key ->
+                AskMemoRoute(graph.records, graph.askEdits, key.rideId, key.askId, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding())
+              }
               entry<SettingsKey> {
                 SettingsScreen(
                   current, apiKey,
diff --git a/app/src/main/java/com/touringproject/v2/ui/DeleteDialog.kt b/app/src/main/java/com/touringproject/v2/ui/DeleteDialog.kt
new file mode 100644
index 0000000..e54034b
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/ui/DeleteDialog.kt
@@ -0,0 +1,39 @@
+package com.touringproject.v2.ui
+
+import androidx.compose.material3.AlertDialog
+import androidx.compose.material3.Text
+import androidx.compose.material3.TextButton
+import androidx.compose.runtime.Composable
+import androidx.compose.ui.Modifier
+import androidx.compose.ui.graphics.Color
+import androidx.compose.ui.platform.testTag
+import androidx.compose.ui.text.font.FontWeight
+
+private val Danger = Color(0xFFD42A2A)
+
+/** DL-01's wording for what SC-06 and SC-07 delete (the mock's table). */
+enum class DeleteKind(val title: String, val text: String) {
+  ASK("この会話を削除しますか？", "質問・回答・メモが削除されます。元に戻せません。"),
+  RIDE("この走行を削除しますか？", "ルート・走行のメモと、その走行の質問・地点メモが削除されます。元に戻せません。"),
+}
+
+/**
+ * DL-01, the one confirmation before anything is deleted (recordings, the connection key, an ask, a ride). "やめる" is
+ * on the left and the red delete on the right (the mock).
+ */
+@Composable
+fun DeleteDialog(title: String, text: String?, confirm: String, onConfirm: () -> Unit, onDismiss: () -> Unit) {
+  AlertDialog(
+    onDismissRequest = onDismiss,
+    title = { Text(title) },
+    text = text?.let { { Text(it) } },
+    confirmButton = {
+      TextButton(onClick = onConfirm, modifier = Modifier.testTag("deleteGo")) { Text(confirm, color = Danger, fontWeight = FontWeight.Bold) }
+    },
+    dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.testTag("deleteCancel")) { Text("やめる") } },
+  )
+}
+
+@Composable
+fun DeleteDialog(kind: DeleteKind, onConfirm: () -> Unit, onDismiss: () -> Unit) =
+  DeleteDialog(kind.title, kind.text, "削除する", onConfirm, onDismiss)
diff --git a/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt b/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
new file mode 100644
index 0000000..cae0cad
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
@@ -0,0 +1,96 @@
+package com.touringproject.v2.ui
+
+import android.widget.Toast
+import androidx.activity.compose.BackHandler
+import androidx.compose.foundation.layout.Arrangement
+import androidx.compose.foundation.layout.Column
+import androidx.compose.foundation.layout.Row
+import androidx.compose.foundation.layout.fillMaxSize
+import androidx.compose.foundation.layout.fillMaxWidth
+import androidx.compose.foundation.layout.padding
+import androidx.compose.material3.AlertDialog
+import androidx.compose.material3.Button
+import androidx.compose.material3.MaterialTheme
+import androidx.compose.material3.OutlinedTextField
+import androidx.compose.material3.Text
+import androidx.compose.material3.TextButton
+import androidx.compose.runtime.Composable
+import androidx.compose.runtime.LaunchedEffect
+import androidx.compose.runtime.getValue
+import androidx.compose.runtime.mutableStateOf
+import androidx.compose.runtime.remember
+import androidx.compose.runtime.rememberCoroutineScope
+import androidx.compose.runtime.saveable.rememberSaveable
+import androidx.compose.runtime.setValue
+import androidx.compose.ui.Alignment
+import androidx.compose.ui.Modifier
+import androidx.compose.ui.focus.FocusRequester
+import androidx.compose.ui.focus.focusRequester
+import androidx.compose.ui.platform.LocalContext
+import androidx.compose.ui.platform.testTag
+import androidx.compose.ui.text.font.FontWeight
+import androidx.compose.ui.unit.dp
+import androidx.compose.ui.unit.sp
+import com.touringproject.v2.records.MEMO_MAX
+import com.touringproject.v2.records.cutMemo
+import com.touringproject.v2.records.memoText
+import kotlinx.coroutines.launch
+
+/**
+ * SC-08 (slice 3 spec §7.2). target says what the memo is for (会話 3 · 09:41 箱根町仙石原, 走行のメモ); initial is the
+ * memo kept now. onSave gets the cleaned memo, or null to remove it, and says whether it was written: a memo that was
+ * not is told and the screen stays, so nothing typed is lost (spec §8). ✕ and Back ask before throwing a change away.
+ */
+@Composable
+fun MemoScreen(target: String, initial: String?, onSave: suspend (String?) -> Boolean, onClose: () -> Unit, modifier: Modifier = Modifier) {
+  var input by rememberSaveable { mutableStateOf(initial ?: "") }
+  var discarding by rememberSaveable { mutableStateOf(false) }
+  var saving by remember { mutableStateOf(false) }
+  val changed = memoText(input) != initial
+  val scope = rememberCoroutineScope()
+  val context = LocalContext.current
+  val focus = remember { FocusRequester() }
+  LaunchedEffect(Unit) { focus.requestFocus() }
+  val close = { if (changed) discarding = true else onClose() }
+  BackHandler(onBack = close)
+  Column(modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
+    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
+      TextButton(onClick = close, modifier = Modifier.testTag("memoClose")) { Text("✕", fontSize = 22.sp) }
+      Text("メモ", Modifier.weight(1f), fontSize = 20.sp, fontWeight = FontWeight.Bold)
+      Button(
+        onClick = {
+          saving = true
+          scope.launch {
+            if (onSave(memoText(input))) onClose() else Toast.makeText(context, "保存できませんでした", Toast.LENGTH_SHORT).show()
+            saving = false
+          }
+        },
+        enabled = !saving,
+        modifier = Modifier.testTag("memoSave"),
+      ) { Text("保存") }
+    }
+    Text(target, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, modifier = Modifier.testTag("memoTarget"))
+    OutlinedTextField(
+      input,
+      { input = cutMemo(it) },
+      Modifier.fillMaxWidth().weight(1f).focusRequester(focus).testTag("memoInput"),
+      placeholder = { Text("感じたこと、また行きたい場所など") },
+    )
+    Text(
+      "${input.codePointCount(0, input.length)} / ${MEMO_MAX}字",
+      Modifier.align(Alignment.End).testTag("memoCount"),
+      color = MaterialTheme.colorScheme.onSurfaceVariant,
+      fontSize = 13.sp,
+    )
+  }
+  if (discarding) {
+    AlertDialog(
+      onDismissRequest = { discarding = false },
+      title = { Text("変更を破棄しますか？") },
+      confirmButton = {
+        TextButton(onClick = { discarding = false; onClose() }, modifier = Modifier.testTag("memoDiscard")) { Text("破棄する") }
+      },
+      dismissButton = { TextButton(onClick = { discarding = false }) { Text("書き続ける") } },
+    )
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt b/app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt
index 848c684..2d1b8ce 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt
@@ -12,13 +12,11 @@ import androidx.compose.foundation.lazy.LazyColumn
 import androidx.compose.foundation.lazy.items
 import androidx.compose.foundation.shape.CircleShape
 import androidx.compose.foundation.shape.RoundedCornerShape
-import androidx.compose.material3.AlertDialog
 import androidx.compose.material3.Button
 import androidx.compose.material3.ButtonDefaults
 import androidx.compose.material3.HorizontalDivider
 import androidx.compose.material3.OutlinedButton
 import androidx.compose.material3.Text
-import androidx.compose.material3.TextButton
 import androidx.compose.runtime.Composable
 import androidx.compose.runtime.getValue
 import androidx.compose.runtime.mutableStateOf
@@ -103,12 +101,10 @@ fun RecordingsScreen(
   }
   // DL-01 (recordings)
   if (confirming) {
-    AlertDialog(
-      onDismissRequest = { confirming = false },
-      title = { Text("録音をすべて消しますか？") },
-      text = { Text("端末に残した質問の音声を消します。質問と回答の記録は消えません。") },
-      confirmButton = { TextButton(onClick = { confirming = false; onDeleteAll() }) { Text("消す") } },
-      dismissButton = { TextButton(onClick = { confirming = false }) { Text("やめる") } },
+    DeleteDialog(
+      "録音をすべて消しますか？", "端末に残した質問の音声を消します。質問と回答の記録は消えません。", "消す",
+      onConfirm = { confirming = false; onDeleteAll() },
+      onDismiss = { confirming = false },
     )
   }
 }
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
index f85b61f..186de71 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
@@ -11,6 +11,7 @@ import com.touringproject.v2.map.LatLon
 import com.touringproject.v2.map.MapPin
 import com.touringproject.v2.map.RouteMap
 import com.touringproject.v2.map.rideMap
+import com.touringproject.v2.records.AskEdits
 import com.touringproject.v2.ride.Ride
 import com.touringproject.v2.ride.RideController
 import com.touringproject.v2.ride.RideStatus
@@ -63,6 +64,7 @@ fun RideDetailRoute(
   onBack: () -> Unit,
   onAsk: (String) -> Unit,
   onFullMap: (Boolean) -> Unit,
+  onMemo: () -> Unit,
   modifier: Modifier = Modifier,
 ) {
   val ride = readRide(records, rideId) ?: return
@@ -81,6 +83,8 @@ fun RideDetailRoute(
     onRename = { name -> rides.rename(rideId, name) },
     onFullMap = onFullMap,
     modifier = modifier,
+    onMemo = onMemo,
+    onDelete = { rides.delete(rideId).also { if (it) onBack() } },
   )
 }
 
@@ -93,12 +97,38 @@ fun askMap(ask: AskRecord?, asks: List<AskRecord>, route: List<RoutePoint>, ende
 }
 
 @Composable
-fun AskDetailRoute(records: RoomRecords, rideId: String, askId: String, onBack: () -> Unit, onMove: (String) -> Unit, modifier: Modifier = Modifier) {
+fun AskDetailRoute(
+  records: RoomRecords,
+  edits: AskEdits,
+  rideId: String,
+  askId: String,
+  onBack: () -> Unit,
+  onMove: (String) -> Unit,
+  onMemo: () -> Unit,
+  modifier: Modifier = Modifier,
+) {
   val ride = readRide(records, rideId) ?: return
   val asks = readAsks(records, rideId) ?: return
   val route = readRoute(records, rideId) ?: return
   val zone = ZoneId.systemDefault()
   val detail = remember(asks, askId) { askDetail(asks, askId, zone) }
   val map = remember(asks, route, askId, ride) { askMap(asks.firstOrNull { it.askId == askId }, asks, route, ride.value?.status == RideStatus.ENDED) }
-  AskDetailScreen(detail, map, routeMap, askId, onBack, onMove, modifier)
+  AskDetailScreen(detail, map, routeMap, askId, onBack, onMove, modifier, onMemo, onDelete = { edits.delete(askId).also { if (it) onBack() } })
+}
+
+/** SC-08 for a ride's memo, from SC-02 or SC-06. Nothing is drawn until the ride has been read, nor for a ride not kept. */
+@Composable
+fun RideMemoRoute(records: RoomRecords, rides: RideController, rideId: String, onClose: () -> Unit, modifier: Modifier = Modifier) {
+  val ride = readRide(records, rideId) ?: return
+  val kept = ride.value ?: return
+  MemoScreen("走行のメモ · ${kept.name}", kept.memo, { rides.memo(rideId, it) }, onClose, modifier)
+}
+
+/** SC-08 for an ask's memo, from SC-07. */
+@Composable
+fun AskMemoRoute(records: RoomRecords, edits: AskEdits, rideId: String, askId: String, onClose: () -> Unit, modifier: Modifier = Modifier) {
+  val asks = readAsks(records, rideId) ?: return
+  val ask = asks.firstOrNull { it.askId == askId } ?: return
+  val target = remember(asks, askId) { askMemoTarget(asks, askId, ZoneId.systemDefault()) } ?: return
+  MemoScreen(target, ask.memo, { edits.memo(askId, it) }, onClose, modifier)
 }
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
index 0f639cd..17c67b9 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
@@ -2,6 +2,7 @@ package com.touringproject.v2.ui
 
 import android.widget.Toast
 import androidx.activity.compose.BackHandler
+import androidx.compose.foundation.BorderStroke
 import androidx.compose.foundation.background
 import androidx.compose.foundation.clickable
 import androidx.compose.foundation.layout.Arrangement
@@ -12,6 +13,7 @@ import androidx.compose.foundation.layout.fillMaxSize
 import androidx.compose.foundation.layout.fillMaxWidth
 import androidx.compose.foundation.layout.height
 import androidx.compose.foundation.layout.padding
+import androidx.compose.foundation.layout.Spacer
 import androidx.compose.foundation.layout.size
 import androidx.compose.foundation.lazy.LazyColumn
 import androidx.compose.foundation.lazy.items
@@ -22,8 +24,10 @@ import androidx.compose.foundation.verticalScroll
 import androidx.compose.material3.AlertDialog
 import androidx.compose.material3.DropdownMenu
 import androidx.compose.material3.DropdownMenuItem
+import androidx.compose.material3.FilledTonalButton
 import androidx.compose.material3.FilterChip
 import androidx.compose.material3.MaterialTheme
+import androidx.compose.material3.OutlinedButton
 import androidx.compose.material3.OutlinedTextField
 import androidx.compose.material3.Text
 import androidx.compose.material3.TextButton
@@ -94,7 +98,8 @@ fun RideListScreen(sections: List<RideSection>?, onRide: (String) -> Unit, modif
 private fun RideRow(row: RideRowUi, onRide: (String) -> Unit) {
   Column(Modifier.fillMaxWidth().clickable { onRide(row.id) }.padding(horizontal = 16.dp, vertical = 10.dp).testTag("ride-${row.id}")) {
     Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
-      Text(row.name, Modifier.weight(1f), fontSize = 17.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
+      Text(row.name, Modifier.weight(1f, fill = false), fontSize = 17.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
+      if (row.memo) Text(" 📝", Modifier.weight(1f).testTag("rideMemoMark-${row.id}"), fontSize = 15.sp) else Spacer(Modifier.weight(1f))
       Text(
         row.state, Modifier.padding(start = 8.dp).testTag("state-${row.id}"), fontSize = 13.sp,
         color = if (row.saved) MaterialTheme.colorScheme.onSurfaceVariant else Accent,
@@ -120,7 +125,8 @@ data class RideDetailUi(
 /**
  * SC-06. The map can fill the screen (onFullMap tells AppUi to hide the tabs), its pins can be hidden (showPins is
  * kept in the settings), and a tapped pin shows its card above the map's bottom edge. onRename says whether the new
- * name was saved; one that was not is told (Android #46).
+ * name was saved; one that was not is told (Android #46). onMemo opens SC-08 for the ride's memo. An ended ride can be
+ * deleted after DL-01; onDelete says whether it was (slice 3 spec §7.4), and AppUi then goes back to SC-05.
  */
 @Composable
 fun RideDetailScreen(
@@ -133,6 +139,8 @@ fun RideDetailScreen(
   onRename: suspend (String) -> Boolean,
   onFullMap: (Boolean) -> Unit,
   modifier: Modifier = Modifier,
+  onMemo: () -> Unit = {},
+  onDelete: suspend () -> Boolean = { false },
 ) {
   if (ui == null) {
     Column(modifier.fillMaxSize()) {
@@ -145,6 +153,7 @@ fun RideDetailScreen(
   var full by rememberSaveable { mutableStateOf(false) }
   var menu by rememberSaveable { mutableStateOf(false) }
   var renaming by rememberSaveable { mutableStateOf<String?>(null) }
+  var deleting by rememberSaveable { mutableStateOf(false) }
   val scope = rememberCoroutineScope()
   val context = LocalContext.current
   LaunchedEffect(full) { onFullMap(full) }
@@ -179,6 +188,17 @@ fun RideDetailScreen(
               menu = false
               renaming = ui.name
             }, modifier = Modifier.testTag("renameRide"))
+            DropdownMenuItem(text = { Text("走行のメモ") }, onClick = {
+              menu = false
+              onMemo()
+            }, modifier = Modifier.testTag("rideMemoMenu"))
+            // The ride recording or paused is ended before it can be deleted (slice 3 spec §2).
+            if (!ui.recording) {
+              DropdownMenuItem(text = { Text("この走行を削除", color = Rec) }, onClick = {
+                menu = false
+                deleting = true
+              }, modifier = Modifier.testTag("deleteRide"))
+            }
           }
         }
       }
@@ -187,6 +207,7 @@ fun RideDetailScreen(
     if (!full) {
       LazyColumn(Modifier.fillMaxSize().testTag("timeline")) {
         item { Summary(ui.summary, ui.recording) }
+        item { MemoBox("走行のメモ", ui.memo, "＋ 走行のメモ", onMemo, "rideMemo") }
         item { Muted("時系列", Modifier.padding(start = 16.dp, top = 12.dp, bottom = 4.dp)) }
         if (ui.timeline.isEmpty()) item { Muted("この走行の記録中にした質問はありません。", Modifier.padding(horizontal = 16.dp)) }
         items(ui.timeline) { row -> TimelineItem(row, onAsk) }
@@ -215,6 +236,36 @@ fun RideDetailScreen(
       dismissButton = { TextButton(onClick = { renaming = null }) { Text("やめる") } },
     )
   }
+  if (deleting) {
+    DeleteDialog(
+      DeleteKind.RIDE,
+      onConfirm = {
+        deleting = false
+        scope.launch { if (!onDelete()) Toast.makeText(context, "削除できませんでした", Toast.LENGTH_SHORT).show() }
+      },
+      onDismiss = { deleting = false },
+    )
+  }
+}
+
+/** A memo in SC-06 and SC-07: its text under a heading, opening SC-08; without one, a button to write it (the mock). */
+@Composable
+private fun MemoBox(heading: String, memo: String?, add: String, onMemo: () -> Unit, tag: String) {
+  if (memo == null) {
+    FilledTonalButton(onClick = onMemo, modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp).testTag("${tag}Add")) { Text(add) }
+    return
+  }
+  Column(
+    Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp))
+      .clickable(onClick = onMemo).padding(12.dp).testTag(tag),
+    verticalArrangement = Arrangement.spacedBy(4.dp),
+  ) {
+    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
+      Muted("📝 $heading", size = 13)
+      Text("編集", color = Accent, fontSize = 13.sp, fontWeight = FontWeight.Bold)
+    }
+    Text(memo, fontSize = 15.sp)
+  }
 }
 
 @Composable
@@ -272,7 +323,7 @@ private fun TimelineItem(row: TimelineRow, onAsk: (String) -> Unit) {
         Text(row.number.toString(), color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
       }
       Column(Modifier.weight(1f)) {
-        Muted("${row.time} · ${row.place}", size = 13)
+        Muted("${row.time} · ${row.place}" + if (row.memo) " · 📝" else "", size = 13)
         Text(
           row.text, maxLines = 2, overflow = TextOverflow.Ellipsis,
           fontWeight = if (row.failed) FontWeight.Normal else FontWeight.Bold,
@@ -285,10 +336,24 @@ private fun TimelineItem(row: TimelineRow, onAsk: (String) -> Unit) {
 
 /**
  * SC-07. map is the ask's place on the faint route of its ride (null when the ask has no place). ‹ › move among the
- * ride's asks; the map is made again for each ask, so it opens on that ask.
+ * ride's asks; the map is made again for each ask, so it opens on that ask. onMemo opens SC-08 for its memo. The ask
+ * can be deleted after DL-01; onDelete says whether it was, and AppUi then goes back to SC-06 (slice 3 spec §7.4).
  */
 @Composable
-fun AskDetailScreen(detail: AskDetailUi?, map: MapData?, mapSlot: MapSlot, askId: String, onBack: () -> Unit, onMove: (String) -> Unit, modifier: Modifier = Modifier) {
+fun AskDetailScreen(
+  detail: AskDetailUi?,
+  map: MapData?,
+  mapSlot: MapSlot,
+  askId: String,
+  onBack: () -> Unit,
+  onMove: (String) -> Unit,
+  modifier: Modifier = Modifier,
+  onMemo: () -> Unit = {},
+  onDelete: suspend () -> Boolean = { false },
+) {
+  var deleting by rememberSaveable { mutableStateOf(false) }
+  val scope = rememberCoroutineScope()
+  val context = LocalContext.current
   Column(modifier.fillMaxSize()) {
     TopBar(detail?.title ?: "会話", onBack) {
       TextButton(onClick = { detail?.previous?.let(onMove) }, enabled = detail?.previous != null, modifier = Modifier.testTag("askPrev")) { Text("‹", fontSize = 24.sp) }
@@ -324,8 +389,24 @@ fun AskDetailScreen(detail: AskDetailUi?, map: MapData?, mapSlot: MapSlot, askId
           Modifier.background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp)).padding(12.dp).testTag("askAnswer"),
         )
       }
+      MemoBox("メモ", detail.memo, "＋ メモを追加", onMemo, "askMemo")
+      OutlinedButton(
+        onClick = { deleting = true },
+        modifier = Modifier.fillMaxWidth().testTag("deleteAsk"),
+        border = BorderStroke(1.dp, Rec),
+      ) { Text("この会話を削除", color = Rec, fontWeight = FontWeight.Bold) }
     }
   }
+  if (deleting) {
+    DeleteDialog(
+      DeleteKind.ASK,
+      onConfirm = {
+        deleting = false
+        scope.launch { if (!onDelete()) Toast.makeText(context, "削除できませんでした", Toast.LENGTH_SHORT).show() }
+      },
+      onDismiss = { deleting = false },
+    )
+  }
 }
 
 @Composable
diff --git a/app/src/main/java/com/touringproject/v2/ui/RideScreens.kt b/app/src/main/java/com/touringproject/v2/ui/RideScreens.kt
index c4b44e0..4deb887 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RideScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RideScreens.kt
@@ -31,9 +31,9 @@ import androidx.compose.ui.unit.sp
 import com.touringproject.v2.ride.cutRideName
 import com.touringproject.v2.ride.rideName
 
-/** SC-02's ride card (slice 2 spec §7.2). Memo buttons wait for slice 3. */
+/** SC-02's ride card (slice 2 spec §7.2). onMemo opens SC-08 for the ride's memo (slice 3 spec §7.1). */
 @Composable
-fun RideCard(ride: RideCardUi?, onStart: () -> Unit, onPause: () -> Unit, onResume: () -> Unit, onEnd: () -> Unit) {
+fun RideCard(ride: RideCardUi?, onStart: () -> Unit, onPause: () -> Unit, onResume: () -> Unit, onEnd: () -> Unit, onMemo: () -> Unit = {}) {
   val card = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp)).padding(14.dp)
   if (ride == null) {
     Column(card, verticalArrangement = Arrangement.spacedBy(8.dp)) {
@@ -57,6 +57,7 @@ fun RideCard(ride: RideCardUi?, onStart: () -> Unit, onPause: () -> Unit, onResu
     Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
       if (ride.paused) Button(onClick = onResume, Modifier.weight(1f)) { Text("▶ 再開") }
       else OutlinedButton(onClick = onPause, Modifier.weight(1f)) { Text("⏸ 一時停止") }
+      OutlinedButton(onClick = onMemo, Modifier.weight(1f).testTag("rideMemo")) { Text("📝 走行メモ") }
       OutlinedButton(onClick = onEnd, Modifier.weight(1f).testTag("endRide")) { Text("■ 終了") }
     }
   }
diff --git a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
index 2fb92f5..173c8ca 100644
--- a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
@@ -218,11 +218,10 @@ fun ConnectionScreen(
   }
   // DL-01 (connection key)
   if (confirmingDelete) {
-    AlertDialog(
-      onDismissRequest = { confirmingDelete = false },
-      title = { Text("接続キーを削除しますか？") },
-      confirmButton = { TextButton(onClick = { confirmingDelete = false; scope.launch { save(null) } }) { Text("削除する") } },
-      dismissButton = { TextButton(onClick = { confirmingDelete = false }) { Text("やめる") } },
+    DeleteDialog(
+      "接続キーを削除しますか？", null, "削除する",
+      onConfirm = { confirmingDelete = false; scope.launch { save(null) } },
+      onDismiss = { confirmingDelete = false },
     )
   }
 }
PATCH
````

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t6.log 2>&1; tail -1 /tmp/trv2-t6.log`
Expected: `BUILD SUCCESSFUL`（`441` 件。数は Task 8 の数え方で見る）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/ui/DeleteDialog.kt app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt app/src/main/java/com/touringproject/v2/ui/RecordingsScreen.kt app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt app/src/main/java/com/touringproject/v2/ui/RideScreens.kt app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt app/src/test/java/com/touringproject/v2/ui/MemoScreenTest.kt app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt
git commit -m "feat: write memos on SC-08 and delete asks and rides after DL-01"
```

---

### Task 7: 版と文書

**Files:**
- Modify: `app/build.gradle.kts`（版 0.6.0）・`README.md`（Android）・`docs-parent/`

- [ ] **Step 1: 版を上げ、README を直す**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/README.md b/README.md
index 3cf896f..811e736 100644
--- a/README.md
+++ b/README.md
@@ -13,23 +13,24 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 | `.../audio/` | インカムの経路・録音・再生・端末の音声・合図 |
 | `.../location/` | 質問の位置の監視と方位の材料の選び方・走行のルートの位置の頼み方と点のふるい分け（`Route.kt`） |
 | `.../ride/` | 走行の型と計算（`Ride.kt`、純粋）・司令塔（`RideController.kt`）・外との窓口（`RidePorts.kt`） |
-| `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・送信の置き場（`RoomSyncStore.kt`）・記録の画面の読み出し（`RoomRecords.kt`）。スキーマは `app/schemas/` に版ごとに残す |
-| `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋） |
+| `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・質問のメモと削除（`RoomAskEdits.kt`）・送信の置き場（`RoomSyncStore.kt`）・記録の画面の読み出し（`RoomRecords.kt`）。スキーマは `app/schemas/` に版ごとに残す |
+| `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋）・メモの決まり（`Memos.kt`、純粋）・質問を変える窓口（`AskEdits.kt`） |
 | `.../map/` | 地図（MapLibre と国土地理院の淡色地図）。描くデータの組み立ては `MapData.kt`（純粋）、地図の部品は `RouteMap.kt`、スタイルは `app/src/main/assets/map/gsi-pale.json` |
-| `.../sync/` | 走行とルートの送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`） |
+| `.../sync/` | 走行・ルート・メモ・削除の送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`） |
 | `.../handsfree/` | 押下の重複・古い合図の除外・押下の行き先（試し録り中は試し録りへ） |
 | `.../recordings/` | 録音の置き場（直近10件と付随情報）・試し録りの司令塔・録音の確認（SC-12）の状態 |
 | `.../service/`・`.../nav/` | 前面サービス（走行の記録と一巡で1つ。種類の取りまとめは `ServiceCoordinator.kt`）・締め切りのアラームと自動終了の通知（`RideAlarms.kt`）・ナビを開く |
 | `.../settings/` | 設定（DataStore）と接続キー（Keystore で暗号化） |
-| `.../ui/` | 画面（Compose）。タブとバックスタックの組は `Tabs.kt`（Compose に依存しない）、タブの帯は `TabBar.kt`。記録の画面は `RecordsScreens.kt`（地図は差し替えられる枠で受ける）、その表示の組み立ては `RecordLabels.kt`（純粋）、読み出しとのつなぎは `RecordsRoutes.kt` |
+| `.../ui/` | 画面（Compose）。タブとバックスタックの組は `Tabs.kt`（Compose に依存しない）、タブの帯は `TabBar.kt`。記録の画面は `RecordsScreens.kt`（地図は差し替えられる枠で受ける）、その表示の組み立ては `RecordLabels.kt`（純粋）、読み出しとのつなぎは `RecordsRoutes.kt`。メモの編集（SC-08）は `MemoScreen.kt`、削除の確認（DL-01）は `DeleteDialog.kt` |
 
 ## 大事な決まり
 
 - 走行の記録中と一巡のあいだは、前面サービスを動かす（無いと、画面を消したあと位置・通信・再生が止まる）。種類は、記録中は `location`、一巡のあいだは `microphone|mediaPlayback` を足す。Android 14 以降、この2つはアプリが前面にあるときにしか始められず、足せない（理由は親の `adr/0006`）。
-- 走行の状態を変えるのは `RideController` だけ。サービス・締め切りのアラーム・電源を切る知らせ・画面は、どれもこれを呼ぶ。起動したときは `load()` が先に、残っていた走行を片付ける（端末が止まっていれば終了、締め切りを過ぎていれば自動終了、それ以外は記録の再開）。最長時間を変えたときの締め切りの計算し直しも `maxRecordingChanged()` が行う（`AppGraph` が設定の変化を受けて呼ぶ）。名前の変更は `rename()`。
+- 走行の状態を変えるのは `RideController` だけ。サービス・締め切りのアラーム・電源を切る知らせ・画面は、どれもこれを呼ぶ。起動したときは `load()` が先に、残っていた走行を片付ける（端末が止まっていれば終了、締め切りを過ぎていれば自動終了、それ以外は記録の再開）。最長時間を変えたときの締め切りの計算し直しも `maxRecordingChanged()` が行う（`AppGraph` が設定の変化を受けて呼ぶ）。名前の変更は `rename()`、走行のメモは `memo()`、終えた走行の削除は `delete()`（書き直し待ちの保存も捨てるので、消した走行が書き戻されない）。
 - 質問を受けるのは走行の記録中だけ。`AskController.run` の入口で `RideNow`（記録中・一時停止中・記録していない）を見て、記録中でなければ録音を始めず、理由を読み上げる。画面の「押して話す」も押せない形にする（親の spec 2 §4.7・adr/0008）。
 - Room のスキーマを変えるときは、版を上げて Migration を書き、`app/schemas/` に書き出された JSON もコミットする。破壊的な作り直しは使わない。スキーマの JSON は debug のビルドの資産にも入る（Robolectric の `MigrationTestHelper` が読むため。release には入らない）。Entity や Migration を変えた直後のテストは `--rerun` で確かめる。
-- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと。契機では未送信を調べるだけで、送るものが無ければ通信しない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。
+- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと。契機では未送信を調べるだけで、送るものが無ければ通信しない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。
+- 1回の送信は、削除の印（`deletions`）→ 走行とルート → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため）。記録を消すときは、同じトランザクションで削除の印を書く。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
 - インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
 - 回答は音声の焦点（audio focus）を取らずに鳴らす（ナビの案内と重ねる）。
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index aa5c05b..eb48958 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 6
-    versionName = "0.5.0"
+    versionCode = 7
+    versionName = "0.6.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
PATCH
````

- [ ] **Step 2: 親の文書を写す**

親の 03・05・モック（スライス3の spec のコミット）と 07（plan 1）が直っているので、Android の `docs-parent/` に写す。

```bash
cd $ROOT && scripts/sync-docs.sh Android
cd $AND && git status --short docs-parent
```

Expected: `docs-parent/` の `03_screen_transition.md`・`05_technical_policies.md`・`07_units_contracts.md`・`mock/index.html` が変わっている。

- [ ] **Step 3: コミット**

```bash
cd $AND && git add app/build.gradle.kts README.md docs-parent/03_screen_transition.md docs-parent/05_technical_policies.md \
  docs-parent/07_units_contracts.md docs-parent/mock/index.html
git commit -m "chore: raise the version to 0.6.0 and describe memos and deletions"
```

---

### Task 8: 全体の確かめ

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

Expected: `441 0`。`BUILD SUCCESSFUL`。`release permissions OK (15)`。

- [ ] **Step 2: エミュレーターのテスト**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: 6件が通る（地図のピンの絵は、メモの無いものは今までどおり）。

---

### Task 9: 利用者の実機の確認

走行用のビルド（版 0.6.0）を実機に入れる。入れたときに版5の Migration が一度だけ走る。

```bash
cd $AND && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

1. 設定 → バージョンが 0.6.0。これまでの走行と質問が、記録のタブにそのまま出る。
2. 走行を始めると、ホームの走行のカードのボタンが「⏸ 一時停止」「📝 走行メモ」「■ 終了」の3つになり、ホームはスクロールしない。「📝 走行メモ」で SC-08 が開き、タブの帯が消える。書いて保存するとホームに戻る。
3. 記録中にインカムで1つ質問してから、走行を終える。記録の一覧で、その走行の名前の後ろに 📝 が付く。走行の詳細の要約の下にメモが出て、押すと SC-08 で直せる。直して ✕ を押すと「変更を破棄しますか？」が出る。
4. 会話の詳細（SC-07）で「＋ メモを追加」からメモを書く。走行の詳細に戻ると、その質問の時系列の行に「 · 📝」、地図のピンの右上に白い点が付く。
5. 会話の詳細で「この会話を削除」→ 確認の文が出て、「削除する」で走行の詳細に戻る。時系列とピンからその質問が消え、番号が詰まる。
6. 走行の詳細のメニュー（⋮）で、記録中の走行には「この走行を削除」が出ない。終えた走行では出て、「削除する」で記録の一覧に戻り、その走行が消える。
7. 機内モードにして、別の終えた走行にメモを書く → 一覧で「未送信あり」。機内モードを外してアプリを前面に出し直すと「保存済み」になる。
8. AI が DynamoDB を読んで確かめる（読むだけ）: 手順 3 の走行の `RIDE#<rideId>` に `memo`、手順 7 の走行にも `memo`、消した会話と走行の `DELETED#ASK#<id>`・`DELETED#RIDE#<id>` があり、消した走行の `RIDE#<rideId>`・`RIDE#<rideId>#ROUTE#…`・その質問の `ASK#…` が無い。ユーザー名と識別子はチャットにだけ出す。

✗ が出たら `superpowers:systematic-debugging`。
