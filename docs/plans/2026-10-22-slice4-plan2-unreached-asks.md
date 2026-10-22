# スライス4 計画2: Android（質問できなかった地点・通信が戻ったら送る） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 質問が Backend に届かなかったとき（録音を終えた時点で通信できない・受け付けが通信の失敗に終わった）に、その日時・位置・方位の材料を「質問できなかった地点」として端末に残し、記録の上（時系列・地図のピン・SC-07）で分かるようにして、後で Backend へ送る。アプリのプロセスが生きているあいだは、通信できるようになったことを送る契機にする。あわせて Android #28・#53・#58・#62 を直す。

**Architecture:** 質問できなかった地点は、質問の表 `asks` の行（`status = offline`、識別子は端末の UUID、会話の識別子は null）として持つ。会話の識別子を null にできるように、Room の版6で `asks` の表を作り直す。質問の司令塔（`AskController`）は、録音を終えたら `AskDeps.online` を見て、通信できなければ送らずに `unreachedAsk` を残す。`POST /asks` が通信の失敗（`reasonFor` が `NETWORK`）に終わったときも同じにする。送信の係（`RideSync`）は、地点メモの後・会話のメモの前に `PUT /asks/{askId}/offline` で送り、通信できないあいだは通信を試さない。`AppGraph` は `Connectivity.online` が戻るたびに（`reconnections`）`RideSync.request()` を呼ぶ。表示は `askText`・`askPlace`・`askDetail` で質問の並びのまま出し分ける。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版6に上げる）・Robolectric 4.16（SDK 35）・OkHttp・kotlinx.serialization。足す依存は無い。

**Spec:** [docs/specs/2026-10-22-slice4-design.md](../specs/2026-10-22-slice4-design.md)（§2・§4・§5・§7.3・§8・§9・§11）。Backend の受け口（`PUT /asks/{askId}/offline`）は plan 1 でデプロイ済み（07 の UC-7、`Backend/openapi.yaml` の `OfflineAskRequest`・`OfflineAskSaved`）。

**範囲に入れた issue（Android）:** #28（質問を書けなかった警告の帯が、次に質問するまで消えない）・#53（書き込みが失敗し続けるあいだの走行の編集と削除で、保存待ちの変更が失われる・残る）・#58（走行の行が無くて書かなかった質問がログに残らず、書けなかった帯も消える）・#62（`ACCESS_NETWORK_STATE` をアプリで宣言していない・切り替えのときに通信できないままになりうる）。spec §2 のとおり。

**前提:** Android の `main`（`a133751`。版 0.8.0）の上に作る。Backend は plan 1 がデプロイ済み（`stack-trv2-dev-backend`、smoke 39/39）。

**計画を書くときに決めたこと（spec からの具体化）:**
- 記録の形（spec §4.2）: `asks` に `updatedAt`・`sentUpdatedAt`・`rejectedUpdatedAt`（地点メモと同じ送信の印）と、方位の材料 `sampleLatitude`・`sampleLongitude`・`sampleAt` を足し、`conversationId` を null にできるようにする。SQLite は列の null の可否を変えられないので、版5→6 は `asks_new` を作って行を写し、名前を付け替える（表は小さく、外部キーも無いので、`RideController.load()` の中で走っても速い。adr/0006）。`AskOutcome` に `OFFLINE`（DB の `status` は `offline`）を足す。`AskRecord` には `sample`（`HeadingSample`）・`updatedAt`・`sent`（送れたか。Backend が作った質問はいつも true）を足す。
- 質問できなかった地点の日時は、録音を終えた時刻（`Recording.endedAt`）。`updatedAt` も同じ値で、その後は変わらない（メモは別の経路で送る）。位置は録音を終えたときの位置、方位の材料は質問と同じ `pickHeadingSample` で選ぶ。識別子は `AskDeps.newId`（`AppGraph` では UUID）。
- いつ残すか（spec §4.1）: 録音を終えた時点で `AskDeps.online()` が false なら送らずに残す。`POST /asks` の失敗は、`reasonFor` が `NETWORK` になるもの（通信の失敗・5xx・429 の試し直しのあと・作り物でない例外）で残す。接続キーの誤り（403）と 400 では残さない。送っているあいだに利用者が取り消したら、残さない（やめた質問）。知らせ方は今の `NETWORK` のまま（失敗の音と「通信できないため、質問できませんでした。」）。
- 録音（US-C-09.001）: SC-12 への録音の保存（`RecordingSink.saved`）を、`POST /asks` の結果が分かってからにする（受け付けられたとき・断られたとき）。質問できなかった地点の録音は保存しない。保存が `POST` の後になるが、保存は待たずに進むもの（US-C-06.005）なので、利用者に見える差は無い。
- 受け付けの応答が失われたとき（`POST` は届いて Backend が質問を作ったのに、端末は通信の失敗と受け取った）は、端末に質問できなかった地点が、Backend に質問が、両方残る。引き継ぎではどちらも入る。起きにくいので、この plan では扱わない。
- 送信（spec §5.1）: 1回の中で 削除の印 → 走行とルート → 地点メモ → 質問できなかった地点 → 会話のメモ の順。応答の住所と方位を行に書く（null なら今の値を残す。410 のときも残す）。400 と 409（`ApiErrorKind.CONFLICT` を足す）は断られた版として送り直さない。spec §5.1 の「地点がまだ送れていなければ、そのメモは送らない」は、この順番と「失敗したらその回を終える」で満たす（地点が断られたときは、メモも 404 で断られる）。
- 通信が戻ったら送る（spec §5.2）: `RideSync` に `online: () -> Boolean` を足し、通信できないあいだは `pass()` が通信を試さない（引数の順は `store, api, online, log`。既存の呼び出しは `log` を末尾のラムダで渡している）。`reconnections(online: Flow<Boolean>)` は、通信できない→できるの変化ごとに1回出す（始まりの状態は数えない）。`AppGraph` で `connectivity` を `sync` より前に作り、`init` で `reconnections(connectivity.online).collect { sync.request() }` を回す。
- 保存の状態（spec §5.4）: 一覧の「未送信あり」に、その走行の質問できなかった地点の未送信を数える（`RideRow.unreachedLeft`。断られた版も「未送信あり」。地点メモと同じ）。
- 表示（spec §4.3）: 番号・ピン・時系列・SC-07 の前後は、質問と同じ並び。時系列とピンのカードの文は「（通信できず、質問できなかった）」、カードの回答の位置は「質問の内容は残していません」。場所は地点メモと同じ出し方（「住所は送信後」「位置の記録なし」「場所不明」、SC-07 では「住所は送ったあとに付きます」「位置を記録できませんでした」「住所は分かりませんでした」）。時系列の行は失敗の質問と同じ見た目（`failed = true`）。SC-07 は「あなた」「AI」の吹き出しの代わりに「📵 通信できず、質問できなかった」と「質問の内容は残していません。何を聞きたかったかは、メモに書けます。」を出す。進行方向は、Backend が方位を決めるまで「停車中」。
- #62: `AndroidManifest.xml` に `ACCESS_NETWORK_STATE` を書く（`scripts/check-release-permissions.sh` の期待する一覧にはすでにある）。`Connectivity` は最後に受けた既定のネットワーク（`current`）を覚え、`onLost` はそれと同じとき（か、まだ無いとき）だけ「通信できない」にする。
- #53: 走行の削除は、消せたときだけ保存待ち（`unsaved`）を捨てる。記録中でない走行の名前とメモの変更は、保存待ちにある同じ走行を元にする（`keptRide`）。メモの書き込みに失敗したら、保存待ちをメモの前に戻す（記録中の走行は、表示のメモも変えない）。名前の変更は今のまま、失敗しても保存待ちに残す（Android #46 の決まり）。
- #28: 帯を2つに分ける。走行の書き込みの失敗は今の「記録を保存できません」（✕ なし）。質問を書けなかったときは「書けなかった質問があります」（`Banner.ASK_STORE_FAILED`）で ✕ で閉じる（`RoomAskLog.dismiss`）。並びは 走行の失敗 → 質問の失敗 → 接続キー → 戻り先 → 音量。
- #58: 走行の行が無くて質問を書かなかったときは、ログ `ask_dropped askId=… rideId=…` を出し、警告の状態を変えない（`RoomAskLog` の `log` は `(String, Throwable?)` にする）。
- `AppUi` の通しのテストは書けない（記録の画面は本物の地図を描く）。つなぎ（通信が戻ったら送る・機内モードでの質問）は Task 8 の実機で確かめる。
- 版を 0.9.0（`versionCode` 10）に上げる。

この計画のコードは、使い捨てのフォルダで、次を確かめてから書いた。

- タスクの順に一つずつコミットし、各タスクのコミットで `clean` から JVM のテストが通る（525件 → 554件）。各タスクのテストだけを1つ前のコミットに当てると、まだ無い名前を使うので、コンパイルで落ちる。
- 最後に、JVM のテスト554件・エミュレーターのテスト6件・`assembleRelease`・`scripts/check-release-permissions.sh` が通る。
- plan の差分を新しい写しへ機械的に当てると、最終形と一致する。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice4-plan2` を切る（Task 0）。親は `slice4-plan2`。push・マージはしない（利用者が明示したときだけ）。push の前に `pre-push-secret-scan`。
- 作りの決まり: 状態機械と司令塔は Android に依存させない（通信の状態は `AskDeps.online`・`RideSync` の `online` で受ける）。部品は `AppGraph` で手で組む。走行を変えるのは `RideController` だけ。
- 質問できなかった地点は、質問が Backend に届かなかったときだけ残す（spec §2「決めたこと」）。会話の文脈に入れない（US-C-09.006）。録音は捨てる（US-C-09.001）。
- 通信が戻ったときの送信は、アプリのプロセスの中で行う。WorkManager は使わない（spec §2）。
- Room のスキーマは版6。`app/schemas/.../6.json` をコミットする。破壊的な作り直しは使わない。
- ホームは全体がスクロールしない。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*クラス名'`。Gradle のビルドキャッシュはフォルダをまたいで共有されるので、テストを確かめるときは `--rerun` を付ける。Kotlin の差分コンパイルは interface の変更を見逃すことがあるので、Task 7 は `./gradlew clean` から回す。
- Room の版を足した直後の1回目のテストは「Missing file 6.json」で落ちることがある（テストの資産が先に集められるため）。そのときはもう一度回す。
- `RoomAskLogTest` の作り物の `AskDao` は、DAO にメソッドを足すたびに実装を足す（Task 3 と Task 5 の差分に入っている）。`RideSyncTest` の作り物の `RideApi`・`SyncStore` も同じ（Task 3）。
- Robolectric の決まり（SDK 35・画面の外の行は `performScrollTo` で出す・地図の部品は動かさない）。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。使い終わったら止める。
- AWS は `AWS_PROFILE=touring`・リージョン `ap-northeast-1`（Task 8 で DynamoDB を読むだけ）。

## Review Focus

- 録音を終えたときは通信できたのに、`POST /asks` の途中で通信が切れる → 質問できなかった地点が1つだけ残り、録音は SC-12 に残らない。Task 2 の `an_ask_the_backend_never_took_in_is_kept_as_unreached_without_its_recording`。
- 質問できなかった地点のあとに、通信できる状態で続けて質問する → 前の会話の文脈のまま続き、会話の区切りは入らない。Task 2 の `an_unreached_ask_leaves_the_conversation_as_it_was`。
- 走行の記録中にトンネルを抜けて通信が戻る（アプリは背面・画面は消えている）→ 前面に出さなくても、ルートと質問できなかった地点が送られる。通信できないあいだの契機では通信を試さない。Task 3 の `without_a_network_a_pass_makes_no_request`・`only_a_change_from_no_network_to_one_is_a_trigger`（つなぎは Task 8 の実機）。
- Wi-Fi からモバイル通信へ切り替わり、古いネットワークの切断が後から届く → 通信できる状態のまま。Task 3 の `losing_the_old_network_after_a_switch_leaves_it_online`。
- 質問できなかった地点にメモを書き、地点がまだ送れないうちに送信が走る → メモは地点の後にしか送られず、地点が送れなければ待つ。Task 3 の `the_memo_of_an_unreached_ask_that_failed_to_go_waits_for_it`。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `store/RideDatabase.kt`・`app/schemas/.../6.json` | `asks` の列と版6の `MIGRATION_5_6`・一覧の `unreachedLeft`（1）、送信の読み書き `unsentUnreached`・`markUnreachedSent`・`markUnreachedRefused`（3） | 1・3 |
| `ask/AskRecord.kt` | `AskOutcome.OFFLINE`・`AskRecord` の `sample`・`updatedAt`・`sent`・`unreachedAsk` | 1 |
| `store/RoomAskLog.kt`・`store/RoomRecords.kt` | 行への変換・#58（1）、帯を閉じる `dismiss`（5）、読み出しと保存の状態（1） | 1・5 |
| `ask/AskController.kt`・`ask/AskPorts.kt` | 届かなかった質問を残す分岐・録音の保存を `POST` の後に・`AskDeps.online`・`newId` | 2 |
| `api/ApiClient.kt` | `ApiErrorKind.CONFLICT`・`OfflineAskBody`・`OfflineAskSaved`・`putOfflineAsk` | 3 |
| `sync/RideSync.kt`・`sync/SyncPlan.kt`・`store/RoomSyncStore.kt` | 送る順番・`online`・`reconnections`・`UnsentUnreached.toBody()` | 3 |
| `net/Connectivity.kt`・`AndroidManifest.xml` | #62 | 3 |
| `AppGraph.kt` | `online`・`newId` を司令塔へ（2）、`connectivity` を前に・送信の `online`・`reconnections`（3） | 2・3 |
| `ui/RecordLabels.kt`・`ui/RecordsScreens.kt` | 時系列・ピン・SC-07 の出し分け | 4 |
| `ride/RideController.kt` | #53 | 5 |
| `ui/Labels.kt`・`ui/HomeScreen.kt`・`ui/AppUi.kt` | #28 の帯 | 5 |
| `Android/README.md`・`app/build.gradle.kts` | 文書と版 | 6 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、今のテストを回す**

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice4-plan2
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t0.log 2>&1; tail -1 /tmp/trv2-t0.log
```

Expected: `BUILD SUCCESSFUL`（525件）。親はこの plan を書いたブランチ `slice4-plan2` のまま。

---

### Task 1: 記録の形（Room の版6）と、質問の保存（#58）

**Files:**
- Modify: `store/RideDatabase.kt`・`ask/AskRecord.kt`・`store/RoomAskLog.kt`・`store/RoomRecords.kt`
- Create: `app/schemas/com.touringproject.v2.store.RideDatabase/6.json`（Room が書き出す。差分に入っている）
- Test: `store/MigrationTest.kt`・`store/RoomAskLogTest.kt`・`store/RoomRecordsTest.kt`

**Interfaces:**
- Consumes: 既存の `AskDao.keep`・`HeadingSample`（`api/ApiClient.kt`）・`Fix`（`location/Heading.kt`）
- Produces:
  - `AskEntity` の `conversationId: String?` と、`updatedAt`・`sentUpdatedAt`・`rejectedUpdatedAt`・`sampleLatitude`・`sampleLongitude`・`sampleAt`（どれも `= null`）。`status` は `answered / failed / offline`
  - `MIGRATION_5_6`（`RideDatabase.open` に足す）・`RideRow.unreachedLeft: Boolean`
  - `enum class AskOutcome { ANSWERED, FAILED, OFFLINE }`・`AskRecord.conversationId: String?`・`AskRecord.sample: HeadingSample? = null`・`AskRecord.updatedAt: Long? = null`・`AskRecord.sent: Boolean = true`
  - `fun unreachedAsk(askId: String, at: Long, here: Fix?, sample: HeadingSample?, rideId: String): AskRecord`
  - `RoomAskLog(dao: AskDao, scope: CoroutineScope, log: (String, Throwable?) -> Unit)`。走行の行が無くて書かなかったときは `log("ask_dropped askId=… rideId=…", null)`

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt b/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
index f4bac71..373f388 100644
--- a/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
@@ -30,7 +30,7 @@ class MigrationTest {
     }
     helper.runMigrationsAndValidate(DB, 2, true, MIGRATION_1_2).close()
     val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
-      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6)
       .allowMainThreadQueries()
       .build()
     runBlocking {
@@ -56,7 +56,7 @@ class MigrationTest {
     }
     helper.runMigrationsAndValidate(DB, 3, true, MIGRATION_2_3).close()
     val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
-      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6)
       .allowMainThreadQueries()
       .build()
     runBlocking {
@@ -78,7 +78,7 @@ class MigrationTest {
     }
     helper.runMigrationsAndValidate(DB, 4, true, MIGRATION_3_4).close()
     val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
-      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6)
       .allowMainThreadQueries()
       .build()
     runBlocking {
@@ -100,7 +100,7 @@ class MigrationTest {
     }
     helper.runMigrationsAndValidate(DB, 5, true, MIGRATION_4_5).close()
     val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
-      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6)
       .allowMainThreadQueries()
       .build()
     runBlocking {
@@ -114,4 +114,32 @@ class MigrationTest {
     }
     db.close()
   }
+
+  // Slice 4 spec §4.2: the asks table is made again so that an unreached ask can have no conversation; what was kept
+  // stays as it was, memos and their markers included.
+  @Test
+  fun version_5_moves_to_6_keeping_asks_and_letting_an_ask_have_no_conversation() {
+    helper.createDatabase(DB, 5).apply {
+      execSQL("INSERT INTO rides VALUES ('r1', '箱根', 'ended', 'manual', NULL, 5000, 120.0, 6000, 6000, NULL, 0, NULL)")
+      val columns = "(askId, askedAt, answeredAt, transcript, answer, latitude, longitude, address, headingDegrees, input, conversationId, " +
+        "newConversation, status, failure, rideId, memo, memoUpdatedAt, memoSentUpdatedAt, memoRejectedUpdatedAt)"
+      execSQL("INSERT INTO asks $columns VALUES ('a1', 1000, 2000, 'Q', 'A', 35.0, 139.0, '箱根町', 90.0, 'voice', 'c1', 1, 'answered', NULL, 'r1', '晴れ', 3000, 3000, NULL)")
+      close()
+    }
+    helper.runMigrationsAndValidate(DB, 6, true, MIGRATION_5_6).close()
+    val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6)
+      .allowMainThreadQueries()
+      .build()
+    runBlocking {
+      val ask = db.asks().ask("a1")!!
+      assertEquals("c1", ask.conversationId)
+      assertEquals("晴れ", ask.memo)
+      assertEquals(3000L, ask.memoSentUpdatedAt)
+      assertNull(ask.updatedAt)
+      db.asks().upsert(ask.copy(askId = "a2", conversationId = null, status = "offline", updatedAt = 4000))
+      assertNull(db.asks().ask("a2")!!.conversationId)
+    }
+    db.close()
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
index cb9722a..75bcc37 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
@@ -7,6 +7,9 @@ import androidx.test.ext.junit.runners.AndroidJUnit4
 import com.touringproject.v2.ask.ASK_INPUT_VOICE
 import com.touringproject.v2.ask.AskOutcome
 import com.touringproject.v2.ask.AskRecord
+import com.touringproject.v2.ask.unreachedAsk
+import com.touringproject.v2.api.HeadingSample
+import com.touringproject.v2.location.Fix
 import com.touringproject.v2.ride.EndReason
 import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.end
@@ -97,4 +100,53 @@ class RoomAskLogTest {
     assertFalse(log.failed.value)
     db.close()
   }
+
+  // Slice 4 spec §4.2: an ask that never reached the Backend keeps when and where it was, and the heading's sample.
+  @Test
+  fun an_unreached_ask_is_kept_without_a_conversation_and_with_its_sample() = runBlocking {
+    keepRide()
+    val sample = HeadingSample(35.0, 138.999, "1970-01-01T00:00:00.500Z")
+    log.save(unreachedAsk("u1", 1_000, Fix(35.001, 139.0, 1_000, 5.0), sample, "r1"))
+    val stored = db.asks().ask("u1")!!
+    assertEquals("offline", stored.status)
+    assertNull(stored.conversationId)
+    assertEquals(1_000L, stored.updatedAt)
+    assertNull(stored.sentUpdatedAt)
+    assertEquals(500L, stored.sampleAt)
+    val record = stored.toRecord()
+    assertEquals(AskOutcome.OFFLINE, record.outcome)
+    assertEquals(sample, record.sample)
+    assertFalse(record.sent)
+    assertEquals(1, db.asks().countForRide("r1").first())
+    db.close()
+  }
+
+  // Android #58: an ask dropped because its ride is not kept is logged, and the warning stays as it was.
+  @Test
+  fun an_ask_without_its_ride_is_logged_and_leaves_the_warning_as_it_was() = runBlocking {
+    var full = true
+    var rideKept = true
+    val dao = object : AskDao {
+      override suspend fun upsert(ask: AskEntity) = if (full) throw IOException("disk full") else Unit
+      override suspend fun ask(askId: String): AskEntity? = null
+      override suspend fun rideKept(rideId: String) = rideKept
+      override fun countForRide(rideId: String) = kotlinx.coroutines.flow.flowOf(0)
+      override fun forRide(rideId: String) = kotlinx.coroutines.flow.flowOf(emptyList<AskEntity>())
+      override suspend fun setMemo(askId: String, memo: String?, at: Long) = error("not used")
+      override suspend fun deleteRow(askId: String) = error("not used")
+      override suspend fun markDeleted(deletion: DeletionEntity) = error("not used")
+      override suspend fun unsentMemos(): List<AskMemoRow> = error("not used")
+      override suspend fun markMemoSent(askId: String, updatedAt: Long) = error("not used")
+      override suspend fun markMemoRefused(askId: String, updatedAt: Long) = error("not used")
+    }
+    val dropping = RoomAskLog(dao, kotlinx.coroutines.MainScope()) { message, _ -> errors += message }
+    dropping.save(record)
+    assertTrue(dropping.failed.value)
+    full = false
+    rideKept = false
+    dropping.save(record.copy(askId = "a2"))
+    assertTrue(dropping.failed.value)
+    assertEquals("ask_dropped askId=a2 rideId=r1", errors.last())
+    db.close()
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
index 6a18a9d..45b3960 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
@@ -114,4 +114,20 @@ class RoomRecordsTest {
     sync.noteSent("n1", 5_000, null, null)
     assertEquals(SaveState.SAVED, records.list.first().single().saveState)
   }
+
+  // Slice 4 spec §5.4: an unreached ask not yet taken leaves its ride "未送信あり", and reads back as unreached.
+  @Test
+  fun an_unreached_ask_not_yet_sent_leaves_the_ride_unsent() = runBlocking {
+    val ended = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(4_000, EndReason.MANUAL, 4_000)
+    rides.save(ended)
+    sync.rideSent("r1", ended.updatedAt)
+    log.save(com.touringproject.v2.ask.unreachedAsk("u1", 1_500, null, null, "r1"))
+    assertEquals(SaveState.UNSENT, records.list.first().single().saveState)
+    val kept = records.asks("r1").first().single()
+    assertEquals(AskOutcome.OFFLINE, kept.outcome)
+    assertEquals(false, kept.sent)
+    db.openHelper.writableDatabase.execSQL("UPDATE asks SET sentUpdatedAt = 1500 WHERE askId = 'u1'")
+    assertEquals(SaveState.SAVED, records.list.first().single().saveState)
+    assertEquals(true, records.asks("r1").first().single().sent)
+  }
 }
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*MigrationTest' --tests '*RoomAskLogTest' --tests '*RoomRecordsTest' 2>&1 | grep -E "^e: " | head -3`
Expected: コンパイルで落ちる（`unreachedAsk`・`MIGRATION_5_6`・`AskOutcome.OFFLINE` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/schemas/com.touringproject.v2.store.RideDatabase/6.json b/app/schemas/com.touringproject.v2.store.RideDatabase/6.json
new file mode 100644
index 0000000..c274800
--- /dev/null
+++ b/app/schemas/com.touringproject.v2.store.RideDatabase/6.json
@@ -0,0 +1,566 @@
+{
+  "formatVersion": 1,
+  "database": {
+    "version": 6,
+    "identityHash": "75eed1552aab37f70c75b4611f942889",
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
+        "createSql": "CREATE TABLE IF NOT EXISTS `${TABLE_NAME}` (`askId` TEXT NOT NULL, `askedAt` INTEGER NOT NULL, `answeredAt` INTEGER, `transcript` TEXT, `answer` TEXT, `latitude` REAL, `longitude` REAL, `address` TEXT, `headingDegrees` REAL, `input` TEXT NOT NULL, `conversationId` TEXT, `newConversation` INTEGER NOT NULL, `status` TEXT NOT NULL, `failure` TEXT, `rideId` TEXT, `memo` TEXT, `memoUpdatedAt` INTEGER, `memoSentUpdatedAt` INTEGER, `memoRejectedUpdatedAt` INTEGER, `updatedAt` INTEGER, `sentUpdatedAt` INTEGER, `rejectedUpdatedAt` INTEGER, `sampleLatitude` REAL, `sampleLongitude` REAL, `sampleAt` INTEGER, PRIMARY KEY(`askId`))",
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
+            "affinity": "TEXT"
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
+          },
+          {
+            "fieldPath": "updatedAt",
+            "columnName": "updatedAt",
+            "affinity": "INTEGER"
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
+      "INSERT OR REPLACE INTO room_master_table (id,identity_hash) VALUES(42, '75eed1552aab37f70c75b4611f942889')"
+    ]
+  }
+}
\ No newline at end of file
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt b/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
index 5cea002..7d2e64e 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskRecord.kt
@@ -1,13 +1,15 @@
 package com.touringproject.v2.ask
 
 import com.touringproject.v2.api.AskResult
+import com.touringproject.v2.api.HeadingSample
 import com.touringproject.v2.location.Fix
 import java.time.OffsetDateTime
 
 // What the device keeps of an ask (slice 2 spec §5.2). The Backend makes the record; the app keeps its own copy and
 // never sends it back (07 UC-7).
 
-enum class AskOutcome { ANSWERED, FAILED }
+/** OFFLINE: the ask never reached the Backend (US-C-09); only when and where it was is kept. */
+enum class AskOutcome { ANSWERED, FAILED, OFFLINE }
 
 /** Slice 2 asks only by voice; text asks come in slice 4. */
 const val ASK_INPUT_VOICE = "voice"
@@ -26,7 +28,8 @@ data class AskRecord(
   val address: String?,
   val headingDegrees: Double?,
   val input: String,
-  val conversationId: String,
+  /** null for an unreached ask: it never joined a conversation (US-C-09.006). */
+  val conversationId: String?,
   /** True for the first ask of a conversation: the conversation breaks just before it (US-C-03.004). */
   val newConversation: Boolean,
   val outcome: AskOutcome,
@@ -36,6 +39,37 @@ data class AskRecord(
   val rideId: String?,
   /** The conversation's memo (US-D-04.001). The ask loop never sets it; only SC-08 does, through AskEdits. */
   val memo: String? = null,
+  /** The older point the Backend takes an unreached ask's heading from (slice 4 spec §4.2); null for the other asks. */
+  val sample: HeadingSample? = null,
+  /** When an unreached ask last changed: the version the Backend compares. null for the asks the Backend made. */
+  val updatedAt: Long? = null,
+  /** False until an unreached ask has reached the Backend; the asks the Backend made are there from the start. */
+  val sent: Boolean = true,
+)
+
+/**
+ * An ask that never reached the Backend (slice 4 spec §4): when the recording ended, where, and the sample for the
+ * heading. Its id is the device's; nothing it said is kept, and it joins no conversation.
+ */
+fun unreachedAsk(askId: String, at: Long, here: Fix?, sample: HeadingSample?, rideId: String) = AskRecord(
+  askId = askId,
+  askedAt = at,
+  answeredAt = null,
+  transcript = null,
+  answer = null,
+  latitude = here?.latitude,
+  longitude = here?.longitude,
+  address = null,
+  headingDegrees = null,
+  input = ASK_INPUT_VOICE,
+  conversationId = null,
+  newConversation = false,
+  outcome = AskOutcome.OFFLINE,
+  failure = null,
+  rideId = rideId,
+  sample = sample,
+  updatedAt = at,
+  sent = false,
 )
 
 /** What the loop knows once the Backend has taken the ask in. */
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 516f018..04316b0 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -78,7 +78,10 @@ data class RoutePointEntity(
   @ColumnInfo(defaultValue = "0") val refused: Boolean = false,
 )
 
-/** An ask whose loop ended with an answer or a failure the Backend reported (slice 2 spec §5.2). */
+/**
+ * An ask whose loop ended with an answer or a failure the Backend reported (slice 2 spec §5.2), or one that never
+ * reached the Backend (slice 4 spec §4.2: status offline). The device makes the latter's id and sends it itself.
+ */
 @Entity(tableName = "asks", indices = [Index(value = ["rideId"]), Index(value = ["askedAt"])])
 data class AskEntity(
   @PrimaryKey val askId: String,
@@ -93,10 +96,11 @@ data class AskEntity(
   val headingDegrees: Double?,
   /** voice / text */
   val input: String,
-  val conversationId: String,
+  /** null for an unreached ask: it never joined a conversation (US-C-09.006). */
+  val conversationId: String?,
   /** True for the first ask of a conversation: the conversation breaks just before it (US-C-03.004). */
   val newConversation: Boolean,
-  /** answered / failed */
+  /** answered / failed / offline */
   val status: String,
   /** no_speech / transcribe_failed / agent_failed / tts_failed / timeout; null when answered */
   val failure: String?,
@@ -114,6 +118,14 @@ data class AskEntity(
   val memoSentUpdatedAt: Long? = null,
   /** The memoUpdatedAt the Backend refused (400 or 404); that version is not sent again (slice 3 spec §5.2). */
   val memoRejectedUpdatedAt: Long? = null,
+  // An unreached ask's version and sending markers, as a point memo's (slice 4 spec §4.2); null for the other asks.
+  val updatedAt: Long? = null,
+  val sentUpdatedAt: Long? = null,
+  val rejectedUpdatedAt: Long? = null,
+  /** The older point the Backend takes an unreached ask's heading from; null when there was none. */
+  val sampleLatitude: Double? = null,
+  val sampleLongitude: Double? = null,
+  val sampleAt: Long? = null,
 )
 
 /**
@@ -312,8 +324,8 @@ data class RideWithSegments(
 
 /**
  * A ride as SC-05 lists it. pointsLeft is true while one of its points has not been taken (unsent or refused);
- * memosLeft while the memo of one of its asks has not been taken, and notesLeft one of its point memos (slice 3 spec
- * §5.3).
+ * memosLeft while the memo of one of its asks has not been taken, notesLeft one of its point memos (slice 3 spec
+ * §5.3), and unreachedLeft one of its unreached asks (slice 4 spec §5.4).
  */
 data class RideRow(
   @Embedded val ride: RideEntity,
@@ -322,6 +334,7 @@ data class RideRow(
   val pointsLeft: Boolean,
   val memosLeft: Boolean,
   val notesLeft: Boolean,
+  val unreachedLeft: Boolean,
 )
 
 @Dao
@@ -344,7 +357,9 @@ interface RideDao {
       "EXISTS (SELECT 1 FROM asks WHERE asks.rideId = rides.id AND asks.memoUpdatedAt IS NOT NULL AND " +
       "(asks.memoSentUpdatedAt IS NULL OR asks.memoSentUpdatedAt < asks.memoUpdatedAt)) AS memosLeft, " +
       "EXISTS (SELECT 1 FROM notes WHERE notes.rideId = rides.id AND " +
-      "(notes.sentUpdatedAt IS NULL OR notes.sentUpdatedAt < notes.updatedAt)) AS notesLeft FROM rides",
+      "(notes.sentUpdatedAt IS NULL OR notes.sentUpdatedAt < notes.updatedAt)) AS notesLeft, " +
+      "EXISTS (SELECT 1 FROM asks WHERE asks.rideId = rides.id AND asks.status = 'offline' AND " +
+      "(asks.sentUpdatedAt IS NULL OR asks.sentUpdatedAt < asks.updatedAt)) AS unreachedLeft FROM rides",
   )
   fun rows(): Flow<List<RideRow>>
 
@@ -477,7 +492,7 @@ interface RideDao {
 
 @Database(
   entities = [RideEntity::class, SegmentEntity::class, RoutePointEntity::class, AskEntity::class, NoteEntity::class, DeletionEntity::class],
-  version = 5,
+  version = 6,
   exportSchema = true,
 )
 abstract class RideDatabase : RoomDatabase() {
@@ -487,7 +502,7 @@ abstract class RideDatabase : RoomDatabase() {
 
   companion object {
     fun open(context: Context): RideDatabase =
-      Room.databaseBuilder(context, RideDatabase::class.java, "rides.db").addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5).build()
+      Room.databaseBuilder(context, RideDatabase::class.java, "rides.db").addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6).build()
   }
 }
 
@@ -559,3 +574,29 @@ val MIGRATION_4_5 = object : Migration(4, 5) {
     )
   }
 }
+
+/**
+ * 5 -> 6 (slice 4 spec §4.2): asks that never reached the Backend. Their conversation is null, which SQLite cannot allow
+ * on the column in place, so the asks table is made again and its rows copied over. The table is small (one row per
+ * ask) and has no foreign keys either way, so this stays quick inside RideController.load() (adr/0006).
+ */
+val MIGRATION_5_6 = object : Migration(5, 6) {
+  override fun migrate(db: SupportSQLiteDatabase) {
+    db.execSQL(
+      "CREATE TABLE IF NOT EXISTS `asks_new` (`askId` TEXT NOT NULL, `askedAt` INTEGER NOT NULL, `answeredAt` INTEGER, " +
+        "`transcript` TEXT, `answer` TEXT, `latitude` REAL, `longitude` REAL, `address` TEXT, `headingDegrees` REAL, " +
+        "`input` TEXT NOT NULL, `conversationId` TEXT, `newConversation` INTEGER NOT NULL, `status` TEXT NOT NULL, " +
+        "`failure` TEXT, `rideId` TEXT, `memo` TEXT, `memoUpdatedAt` INTEGER, `memoSentUpdatedAt` INTEGER, " +
+        "`memoRejectedUpdatedAt` INTEGER, `updatedAt` INTEGER, `sentUpdatedAt` INTEGER, `rejectedUpdatedAt` INTEGER, " +
+        "`sampleLatitude` REAL, `sampleLongitude` REAL, `sampleAt` INTEGER, PRIMARY KEY(`askId`))",
+    )
+    val kept = "`askId`, `askedAt`, `answeredAt`, `transcript`, `answer`, `latitude`, `longitude`, `address`, `headingDegrees`, " +
+      "`input`, `conversationId`, `newConversation`, `status`, `failure`, `rideId`, `memo`, `memoUpdatedAt`, " +
+      "`memoSentUpdatedAt`, `memoRejectedUpdatedAt`"
+    db.execSQL("INSERT INTO `asks_new` ($kept) SELECT $kept FROM `asks`")
+    db.execSQL("DROP TABLE `asks`")
+    db.execSQL("ALTER TABLE `asks_new` RENAME TO `asks`")
+    db.execSQL("CREATE INDEX IF NOT EXISTS `index_asks_rideId` ON `asks` (`rideId`)")
+    db.execSQL("CREATE INDEX IF NOT EXISTS `index_asks_askedAt` ON `asks` (`askedAt`)")
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
index 90b2924..e939ba0 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
@@ -9,6 +9,7 @@ import kotlinx.coroutines.flow.MutableStateFlow
 import kotlinx.coroutines.flow.StateFlow
 import kotlinx.coroutines.flow.asStateFlow
 import kotlinx.coroutines.launch
+import java.time.Instant
 
 /**
  * The memo is not copied: the loop writes an ask once, at its end, and SC-08 changes its memo apart (AskDao.writeMemo),
@@ -30,10 +31,17 @@ fun AskRecord.toEntity() = AskEntity(
   status = outcome.name.lowercase(),
   failure = failure,
   rideId = rideId,
+  updatedAt = updatedAt,
+  sampleLatitude = sample?.latitude,
+  sampleLongitude = sample?.longitude,
+  sampleAt = sample?.let { Instant.parse(it.at).toEpochMilli() },
 )
 
-/** Keeps asks in Room without holding up the ask loop. A failed write is logged and shown, like a ride's (slice 2 spec §8). */
-class RoomAskLog(private val dao: AskDao, private val scope: CoroutineScope, private val log: (String, Throwable) -> Unit) : AskLog {
+/**
+ * Keeps asks in Room without holding up the ask loop. A failed write is logged and shown, like a ride's (slice 2 spec
+ * §8); so is an ask dropped because its ride is not kept, without a throwable (Android #58).
+ */
+class RoomAskLog(private val dao: AskDao, private val scope: CoroutineScope, private val log: (String, Throwable?) -> Unit) : AskLog {
   private val failing = MutableStateFlow(false)
   /** True while the last write of an ask failed. */
   val failed: StateFlow<Boolean> = failing.asStateFlow()
@@ -42,10 +50,16 @@ class RoomAskLog(private val dao: AskDao, private val scope: CoroutineScope, pri
     scope.launch { save(record) }
   }
 
-  /** An ask whose ride was deleted meanwhile is dropped (Android #54). */
+  /**
+   * An ask whose ride is not kept is dropped (Android #54): deleted meanwhile, or never written. That leaves the warning
+   * as it was, since nothing was written either way (Android #58).
+   */
   suspend fun save(record: AskRecord) {
     try {
-      dao.keep(record.toEntity())
+      if (!dao.keep(record.toEntity())) {
+        log("ask_dropped askId=${record.askId} rideId=${record.rideId}", null)
+        return
+      }
       failing.value = false
     } catch (e: CancellationException) {
       throw e
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
index 5d92429..253bb89 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
@@ -2,6 +2,7 @@ package com.touringproject.v2.store
 
 import com.touringproject.v2.ask.AskOutcome
 import com.touringproject.v2.ask.AskRecord
+import com.touringproject.v2.api.HeadingSample
 import com.touringproject.v2.records.NoteRecord
 import com.touringproject.v2.records.RideListItem
 import com.touringproject.v2.records.orderRides
@@ -10,6 +11,7 @@ import com.touringproject.v2.ride.Ride
 import com.touringproject.v2.ride.RoutePoint
 import kotlinx.coroutines.flow.Flow
 import kotlinx.coroutines.flow.map
+import java.time.Instant
 
 fun AskEntity.toRecord() = AskRecord(
   askId = askId,
@@ -28,6 +30,13 @@ fun AskEntity.toRecord() = AskRecord(
   failure = failure,
   rideId = rideId,
   memo = memo,
+  sample = if (sampleLatitude != null && sampleLongitude != null && sampleAt != null) {
+    HeadingSample(sampleLatitude, sampleLongitude, Instant.ofEpochMilli(sampleAt).toString())
+  } else {
+    null
+  },
+  updatedAt = updatedAt,
+  sent = status != "offline" || sentUpdatedAt != null,
 )
 
 fun NoteEntity.toRecord() = NoteRecord(id, rideId, at, latitude, longitude, text, address, sent = sentUpdatedAt != null)
@@ -38,7 +47,7 @@ class RoomRecords(private val rides: RideDao, private val asks: AskDao, private
     orderRides(
       rows.map { row ->
         val ride = row.ride.toRide(row.segments.sortedBy { it.seq })
-        RideListItem(ride, row.questions, saveState(ride.status, ride.updatedAt, row.ride.sentUpdatedAt, row.pointsLeft || row.memosLeft || row.notesLeft))
+        RideListItem(ride, row.questions, saveState(ride.status, ride.updatedAt, row.ride.sentUpdatedAt, row.pointsLeft || row.memosLeft || row.notesLeft || row.unreachedLeft))
       },
     )
   }
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t1.log 2>&1; tail -1 /tmp/trv2-t1.log`
Expected: `BUILD SUCCESSFUL`（529件）。1回目が「Missing file 6.json」で落ちたら、もう一度回す

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/schemas/com.touringproject.v2.store.RideDatabase/6.json app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/ask/AskRecord.kt app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt app/src/main/java/com/touringproject/v2/store/RoomRecords.kt app/src/test/java/com/touringproject/v2/store/MigrationTest.kt app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
git commit -m "feat: keep asks that never reached the Backend in Room version 6, and log an ask dropped for want of its ride (#58)"
```

---

### Task 2: 質問の一巡: 届かなかった質問を残す

**Files:**
- Modify: `ask/AskController.kt`・`ask/AskPorts.kt`・`AppGraph.kt`
- Test: `ask/AskControllerTest.kt`

**Interfaces:**
- Consumes: `unreachedAsk`・`AskOutcome.OFFLINE`（Task 1）・`pickHeadingSample`・`Connectivity.online`
- Produces:
  - `AskDeps` に `online: () -> Boolean` と `newId: () -> String`（`asks` の直後。`AppGraph` では `{ connectivity.online.value }` と UUID）
  - 録音を終えて `online()` が false なら `POST` しない。`POST` が `NETWORK` の失敗なら、どちらも `unreachedAsk(newId(), endedAt, here, sample, rideId)` を `AskLog.keep` に渡して `fail(NETWORK)`。取り消された一巡では残さない
  - `RecordingSink.saved` は `POST` の結果が分かってから（受け付け・断られた）呼ぶ

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index b30dce8..1f3460a 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -62,6 +62,8 @@ private class Harness(
   val pcm: ByteArray = byteArrayOf(1, 2, 3),
   /** Asks start only while a ride records (slice 2 spec §4.7); most tests ride. */
   var ride: RideNow = RideNow.Recording("r1"),
+  /** Whether the device has a network when the recording ends (slice 4 spec §4.1). */
+  var online: Boolean = true,
 ) {
   val log = mutableListOf<String>()
   val states = mutableListOf<FlowState>()
@@ -116,6 +118,8 @@ private class Harness(
       override fun transcribed(name: String, transcript: String) { transcripts += name to transcript }
     },
     asks = { kept += it },
+    online = { online },
+    newId = { "u1" },
     ride = { ride },
     location = object : Positions {
       override fun begin() { log += "loc:begin" }
@@ -575,10 +579,84 @@ class AskControllerTest {
     assertEquals(TIMEOUT_FAILURE, h.kept.single().failure)
   }
 
+  // Slice 4 spec §4.1: the network failed on the way, so the Backend never took the ask in; it is kept as unreached.
   @Test
-  fun an_ask_the_backend_never_took_in_is_not_kept() = runTest {
+  fun an_ask_the_backend_never_took_in_is_kept_as_unreached_without_its_recording() = runTest {
     val h = Harness(this, stopAfterMs = 1_000, post = { throw ApiError(ApiErrorKind.NETWORK) })
     h.controller.run(Source.HANDSFREE)
+    val kept = h.kept.single()
+    assertEquals(AskOutcome.OFFLINE, kept.outcome)
+    assertEquals("u1", kept.askId)
+    assertEquals("r1", kept.rideId)
+    assertTrue(h.metas.isEmpty())
+    assertTrue("say:通信できないため、質問できませんでした。" in h.log)
+  }
+
+  // US-C-09.001: with no network when the recording ends, nothing is sent; when and where it was is kept.
+  @Test
+  fun without_a_network_the_ask_is_not_sent_and_is_kept_as_unreached() = runTest {
+    val h = Harness(this, stopAfterMs = 1_000, online = false)
+    h.controller.run(Source.HANDSFREE)
+    assertFalse("post" in h.log)
+    val kept = h.kept.single()
+    assertEquals(AskOutcome.OFFLINE, kept.outcome)
+    assertEquals(1_000L, kept.askedAt)
+    assertEquals(1_000L, kept.updatedAt)
+    assertEquals(HERE.latitude, kept.latitude!!, 0.0)
+    assertEquals(HeadingSample(BEHIND.latitude, BEHIND.longitude, "1970-01-01T00:01:30Z"), kept.sample)
+    assertEquals(null, kept.conversationId)
+    assertFalse(kept.newConversation)
+    assertFalse(kept.sent)
+    assertTrue(h.metas.isEmpty())
+    assertEquals(
+      listOf("cue:failure", "say:通信できないため、質問できませんでした。", "return:maps", "svc:stop"),
+      h.log.dropWhile { it != "route:stop" }.drop(1),
+    )
+  }
+
+  // US-C-09.006: an unreached ask joins no conversation, so the next ask carries on the one before it.
+  @Test
+  fun an_unreached_ask_leaves_the_conversation_as_it_was() = runTest {
+    val h = Harness(this, stopAfterMs = null)
+    h.controller.run(Source.HANDSFREE)
+    h.online = false
+    h.controller.run(Source.HANDSFREE)
+    h.online = true
+    h.controller.run(Source.HANDSFREE)
+    // Only the first and the third were sent; the third goes on with the first's conversation.
+    assertEquals(listOf(null, "c1"), h.bodies.map { it.conversationId })
+    assertEquals(listOf(true, false, false), h.kept.map { it.newConversation })
+  }
+
+  // A 5xx after the retries is a network failure for the rider: the Backend did not take the ask in.
+  @Test
+  fun a_server_failure_on_send_keeps_an_unreached_ask() = runTest {
+    val h = Harness(this, stopAfterMs = 1_000, post = { throw ApiError(ApiErrorKind.SERVER, "HTTP 503") })
+    h.controller.run(Source.HANDSFREE)
+    assertEquals(AskOutcome.OFFLINE, h.kept.single().outcome)
+  }
+
+  // A refusal is no unreached ask: the network worked. The recording stays for SC-12, as before.
+  @Test
+  fun a_refused_key_keeps_no_ask_but_keeps_the_recording() = runTest {
+    val h = Harness(this, stopAfterMs = 1_000, post = { throw ApiError(ApiErrorKind.INVALID_KEY) })
+    h.controller.run(Source.HANDSFREE)
+    assertTrue(h.kept.isEmpty())
+    assertEquals(1, h.metas.size)
+  }
+
+  // The rider cancelled while the ask was being sent: they let it go, so it is not kept even when the send fails.
+  @Test
+  fun an_ask_cancelled_while_sending_is_not_kept_as_unreached() = runTest {
+    val h = Harness(this, stopAfterMs = 1_000)
+    h.post = {
+      delay(5_000)
+      throw ApiError(ApiErrorKind.NETWORK)
+    }
+    val running = launch { h.controller.run(Source.SCREEN) }
+    h.until { h.phase == Phase.SENDING }
+    h.controller.cancel()
+    running.join()
     assertTrue(h.kept.isEmpty())
   }
 
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*AskControllerTest' 2>&1 | grep -E "^e: " | head -3`
Expected: コンパイルで落ちる（`AskDeps` に `online`・`newId` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 68c4f11..a1a4651 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -168,6 +168,8 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       recorder = PcmRecorder(),
       recordings = RecordingKeeper(recordingStore, scope) { message, e -> Log.w("trv2.recordings", message, e) },
       asks = askLog,
+      online = { connectivity.online.value },
+      newId = { UUID.randomUUID().toString() },
       ride = { rideNow(rides.active.value) },
       location = PositionTracker(FusedPositionSource(context)),
       service = serviceCoordinator.keepAlive,
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index f6b8cb6..a75c9a0 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -53,7 +53,16 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
   // Per-ask state: an older ask that is still unwinding must not read or change the newer one's.
   private class Run(val id: Int, val source: Source, var returned: Boolean = false)
 
-  private class Recording(val audio: String, val name: String, val current: Fix?, val fixes: List<Fix>)
+  // meta and pcm go to SC-12 once the ask has reached the Backend, or failed there; an unreached ask's recording goes.
+  private class Recording(
+    val audio: String,
+    val name: String,
+    val current: Fix?,
+    val fixes: List<Fix>,
+    val endedAt: Long,
+    val meta: RecordingMeta,
+    val pcm: ByteArray,
+  )
 
   /** The intercom button: start, stop the recording, or say that an answer is on its way. */
   fun press() {
@@ -131,6 +140,11 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       }
       serviceRunning = true
       val recording = record(run) ?: return
+      // US-C-09: without a network the ask cannot be asked; when and where it was is kept instead (slice 4 spec §4.1).
+      if (!d.online()) {
+        keepUnreached(recording, rideId, run)
+        return
+      }
       val sent = send(recording, rideId, api, run) ?: return
       maybeReturn(ReturnTiming.SENT, settings, run)
       val result = waitForAnswer(sent, recording.name, api, run) ?: return
@@ -234,12 +248,13 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       fail(FailureReason.MIC, run)
       return null
     }
-    d.recordings.saved(RecordingMeta(stopped.name, startedAt, pcmDurationMs(stopped.pcm.size), phoneMic, device, null), stopped.pcm)
+    val endedAt = d.now()
+    val meta = RecordingMeta(stopped.name, startedAt, pcmDurationMs(stopped.pcm.size), phoneMic, device, null)
     val (currentFix, fixes) = d.location.end()
-    return Recording(Base64.getEncoder().encodeToString(stopped.pcm), stopped.name, currentFix, fixes)
+    return Recording(Base64.getEncoder().encodeToString(stopped.pcm), stopped.name, currentFix, fixes, endedAt, meta, stopped.pcm)
   }
 
-  private suspend fun send(recording: Recording, rideId: String?, api: AskApi, run: Run): SentAsk? {
+  private suspend fun send(recording: Recording, rideId: String, api: AskApi, run: Run): SentAsk? {
     val d = deps
     val here = recording.current
     val body = AskBody(
@@ -254,9 +269,17 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       api.postAsk(body)
     } catch (e: Exception) {
       d.log("post_failed", mapOf("kind" to ((e as? ApiError)?.kind?.name ?: "unknown")))
-      fail(reasonFor(e), run)
+      val reason = reasonFor(e)
+      // The Backend did not take the ask in (slice 4 spec §4.1); a refusal (the key, the request) is no unreached ask.
+      if (reason == FailureReason.NETWORK) {
+        keepUnreached(recording, rideId, run)
+        return null
+      }
+      d.recordings.saved(recording.meta, recording.pcm)
+      fail(reason, run)
       return null
     }
+    d.recordings.saved(recording.meta, recording.pcm)
     // The ask exists on the Backend either way, so keep the conversation going even if it was cancelled.
     d.conversation.update(accepted.conversationId, accepted.conversationExpiresAt)
     if (!isCurrent(run)) return null
@@ -265,6 +288,21 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     return SentAsk(accepted.askId, accepted.conversationId, body.conversationId == null, d.now(), here, rideId)
   }
 
+  /**
+   * US-C-09: the ask never reached the Backend. Its time, place and heading's sample are kept as an unreached ask, which
+   * is sent later; the recording is dropped (US-C-09.001) and the conversation is left as it was (US-C-09.006). An ask
+   * the rider cancelled meanwhile is not kept: they let it go.
+   */
+  private suspend fun keepUnreached(recording: Recording, rideId: String, run: Run) {
+    val d = deps
+    if (isCurrent(run)) {
+      val here = recording.current
+      d.asks.keep(unreachedAsk(d.newId(), recording.endedAt, here, here?.let { pickHeadingSample(recording.fixes, it) }, rideId))
+      d.log("ask_unreached", mapOf("rideId" to rideId))
+    }
+    fail(FailureReason.NETWORK, run)
+  }
+
   private suspend fun waitForAnswer(sent: SentAsk, recordingName: String, api: AskApi, run: Run): AskResult? {
     val d = deps
     var sinceCue = 0L
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
index be387ee..4907dbe 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
@@ -108,8 +108,12 @@ class AskDeps(
   val route: RouteControl,
   val recorder: Recorder,
   val recordings: RecordingSink,
-  /** Where the asks that reached the Backend are kept (slice 2 spec §5.2). */
+  /** Where the asks are kept: those that reached the Backend (slice 2 spec §5.2) and those that did not (slice 4 spec §4). */
   val asks: AskLog,
+  /** Whether the device has a network now: without one the ask is not sent (US-C-09.001). */
+  val online: () -> Boolean,
+  /** A new id for an unreached ask, which the device makes (slice 4 spec §4.2). */
+  val newId: () -> String,
   /** Whether a ride is recording now: an ask starts only then (slice 2 spec §4.7). */
   val ride: () -> RideNow,
   val location: Positions,
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t2.log 2>&1; tail -1 /tmp/trv2-t2.log`
Expected: `BUILD SUCCESSFUL`（534件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
git commit -m "feat: keep an ask that cannot reach the Backend as unreached, without its recording"
```

---

### Task 3: 送信: 質問できなかった地点・通信が戻ったら送る・#62

**Files:**
- Modify: `api/ApiClient.kt`・`store/RideDatabase.kt`・`store/RoomSyncStore.kt`・`sync/RideSync.kt`・`sync/SyncPlan.kt`・`net/Connectivity.kt`・`AppGraph.kt`・`app/src/main/AndroidManifest.xml`
- Create: `sync/ReconnectionsTest.kt`（テスト）
- Test: `api/ApiClientTest.kt`・`sync/RideSyncTest.kt`・`store/RoomSyncStoreTest.kt`・`store/RoomAskLogTest.kt`（作り物の DAO）・`net/ConnectivityTest.kt`

**Interfaces:**
- Consumes: `AskEntity` の送信の列（Task 1）・`RoomAskLog`・`unreachedAsk`（テストで）
- Produces:
  - `ApiErrorKind.CONFLICT`（409）・`OfflineAskBody(askedAt: String, location: Point?, headingSample: HeadingSample?, rideId: String, updatedAt: String)`・`OfflineAskSaved(address: String? = null, headingDegrees: Double? = null)`・`RideApi.putOfflineAsk(askId: String, body: OfflineAskBody): OfflineAskSaved`
  - `AskDao.unsentUnreached(): List<AskEntity>`・`markUnreachedSent(askId, updatedAt, address, headingDegrees)`・`markUnreachedRefused(askId, updatedAt)`
  - `UnsentUnreached(askId, rideId, askedAt, latitude, longitude, sampleLatitude, sampleLongitude, sampleAt, updatedAt)`・`SyncStore.unsentUnreached()`・`unreachedSent(...)`・`unreachedRefused(...)`・`UnsentUnreached.toBody(): OfflineAskBody`
  - `RideSync(store, api, online: () -> Boolean = { true }, log)`・`fun reconnections(online: Flow<Boolean>): Flow<Unit>`
  - `AppGraph.connectivity` は `sync` より前に作る

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
index ed44309..75e8175 100644
--- a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
+++ b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
@@ -294,4 +294,28 @@ class ApiClientTest {
     assertEquals(TranscriptionResult("t2", "failed", null, "no_speech"), client().getTranscription("t2"))
     assertEquals("GET /Prod/transcriptions/t1", server.takeRequest().let { "${it.method} ${it.path}" })
   }
+
+  // Slice 4 spec §4.4: an unreached ask goes whole under the device's id, and the Backend answers its place and heading.
+  @Test
+  fun putOfflineAsk_sends_the_unreached_ask_and_reads_the_address_and_heading() = runTest {
+    server.enqueue(json(200, """{"askId":"u1","applied":true,"address":"神奈川県箱根町仙石原","headingDegrees":12.5}"""))
+    val body = OfflineAskBody("2026-10-22T01:24:00Z", null, null, "r1", "2026-10-22T01:24:00Z")
+    assertEquals(OfflineAskSaved("神奈川県箱根町仙石原", 12.5), client().putOfflineAsk("u1", body))
+    val request = server.takeRequest()
+    assertEquals("PUT /Prod/asks/u1/offline", "${request.method} ${request.path}")
+    val sent = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
+    assertEquals("r1", sent["rideId"]!!.jsonPrimitive.content)
+    assertEquals(JsonNull, sent["location"])
+    assertEquals(JsonNull, sent["headingSample"])
+  }
+
+  // 409: the id is an ask the Backend took in; it is not retried.
+  @Test
+  fun an_unreached_ask_over_a_taken_one_is_a_conflict_and_not_retried() = runTest {
+    server.enqueue(json(409, """{"error":"conflict"}"""))
+    val error = runCatching { client().putOfflineAsk("u1", OfflineAskBody("2026-10-22T01:24:00Z", null, null, "r1", "2026-10-22T01:24:00Z")) }
+      .exceptionOrNull() as ApiError
+    assertEquals(ApiErrorKind.CONFLICT, error.kind)
+    assertEquals(1, server.requestCount)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt b/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt
index 85bcfd0..d73f0db 100644
--- a/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt
+++ b/app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt
@@ -10,6 +10,7 @@ import org.junit.Assert.assertTrue
 import org.junit.Test
 import org.junit.runner.RunWith
 import org.robolectric.Shadows.shadowOf
+import org.robolectric.shadows.ShadowNetwork
 import org.robolectric.shadows.ShadowNetworkCapabilities
 
 // Slice 3 spec §7.3: SC-19 follows whether the device has a network.
@@ -33,4 +34,20 @@ class ConnectivityTest {
     callback.onCapabilitiesChanged(network, ShadowNetworkCapabilities.newInstance())
     assertFalse(connectivity.online.value)
   }
+
+  // Android #62: after a switch (Wi-Fi to mobile data), the old network's loss reported late does not leave it offline.
+  @Test
+  fun losing_the_old_network_after_a_switch_leaves_it_online() {
+    val before = shadowOf(manager).networkCallbacks.toSet()
+    val connectivity = Connectivity(app)
+    val callback = (shadowOf(manager).networkCallbacks - before).single()
+    val old = manager.activeNetwork!!
+    val new = ShadowNetwork.newInstance(1_234)
+    val caps = ShadowNetworkCapabilities.newInstance().also { shadowOf(it).addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) }
+    callback.onCapabilitiesChanged(new, caps)
+    callback.onLost(old)
+    assertTrue(connectivity.online.value)
+    callback.onLost(new)
+    assertFalse(connectivity.online.value)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
index 75bcc37..45c15b8 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
@@ -78,6 +78,9 @@ class RoomAskLogTest {
       override suspend fun unsentMemos(): List<AskMemoRow> = error("not used")
       override suspend fun markMemoSent(askId: String, updatedAt: Long) = error("not used")
       override suspend fun markMemoRefused(askId: String, updatedAt: Long) = error("not used")
+      override suspend fun unsentUnreached(): List<AskEntity> = error("not used")
+      override suspend fun markUnreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?) = error("not used")
+      override suspend fun markUnreachedRefused(askId: String, updatedAt: Long) = error("not used")
     }
     val failing = RoomAskLog(dao, kotlinx.coroutines.MainScope()) { message, _ -> errors += message }
     failing.save(record)
@@ -138,6 +141,9 @@ class RoomAskLogTest {
       override suspend fun unsentMemos(): List<AskMemoRow> = error("not used")
       override suspend fun markMemoSent(askId: String, updatedAt: Long) = error("not used")
       override suspend fun markMemoRefused(askId: String, updatedAt: Long) = error("not used")
+      override suspend fun unsentUnreached(): List<AskEntity> = error("not used")
+      override suspend fun markUnreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?) = error("not used")
+      override suspend fun markUnreachedRefused(askId: String, updatedAt: Long) = error("not used")
     }
     val dropping = RoomAskLog(dao, kotlinx.coroutines.MainScope()) { message, _ -> errors += message }
     dropping.save(record)
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
index beb60d3..d232c02 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
@@ -15,6 +15,11 @@ import com.touringproject.v2.sync.ChunkRange
 import com.touringproject.v2.sync.PendingDeletion
 import com.touringproject.v2.sync.UnsentAskMemo
 import com.touringproject.v2.sync.UnsentNote
+import com.touringproject.v2.sync.UnsentUnreached
+import com.touringproject.v2.api.HeadingSample
+import com.touringproject.v2.ask.unreachedAsk
+import com.touringproject.v2.location.Fix
+import kotlinx.coroutines.MainScope
 import com.touringproject.v2.sync.RideSync
 import kotlinx.coroutines.runBlocking
 import kotlinx.serialization.json.Json
@@ -195,4 +200,27 @@ class RoomSyncStoreTest {
     assertEquals(2, server.requestCount)
     server.shutdown()
   }
+
+  // Slice 4 spec §5.1: an unreached ask is unsent until its version is taken or refused, and keeps the address it got.
+  @Test
+  fun an_unreached_ask_is_unsent_until_its_version_is_taken_and_keeps_its_address() = runBlocking {
+    rides.save(ride)
+    val log = RoomAskLog(db.asks(), MainScope()) { _, _ -> }
+    log.save(unreachedAsk("u1", 1_400, Fix(35.0, 139.0, 1_400, 5.0), HeadingSample(34.99, 139.0, "1970-01-01T00:00:01.300Z"), "r1"))
+    log.save(unreachedAsk("u2", 1_600, null, null, "r1"))
+    assertEquals(
+      listOf(UnsentUnreached("u1", "r1", 1_400, 35.0, 139.0, 34.99, 139.0, 1_300, 1_400), UnsentUnreached("u2", "r1", 1_600, null, null, null, null, null, 1_600)),
+      store.unsentUnreached(),
+    )
+    store.unreachedSent("u1", 1_400, "神奈川県箱根町仙石原", 12.5)
+    store.unreachedRefused("u2", 1_600)
+    assertEquals(emptyList<UnsentUnreached>(), store.unsentUnreached())
+    assertEquals("神奈川県箱根町仙石原" to 12.5, db.asks().ask("u1")!!.let { it.address to it.headingDegrees })
+    // The answer to a later send without an address (410) keeps the one settled before.
+    store.unreachedSent("u1", 1_400, null, null)
+    assertEquals("神奈川県箱根町仙石原", db.asks().ask("u1")!!.address)
+    // The other asks are never unreached ones to send.
+    db.asks().upsert(db.asks().ask("u1")!!.copy(askId = "a1", status = "answered", updatedAt = null, sentUpdatedAt = null))
+    assertEquals(emptyList<UnsentUnreached>(), store.unsentUnreached())
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/sync/ReconnectionsTest.kt b/app/src/test/java/com/touringproject/v2/sync/ReconnectionsTest.kt
new file mode 100644
index 0000000..6eb6ebb
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/sync/ReconnectionsTest.kt
@@ -0,0 +1,23 @@
+package com.touringproject.v2.sync
+
+import kotlinx.coroutines.flow.flowOf
+import kotlinx.coroutines.flow.toList
+import kotlinx.coroutines.test.runTest
+import org.junit.Assert.assertEquals
+import org.junit.Test
+
+// Slice 4 spec §5.2: the network coming back is a trigger, so what waited for it goes without the app in front.
+class ReconnectionsTest {
+  @Test
+  fun only_a_change_from_no_network_to_one_is_a_trigger() = runTest {
+    assertEquals(2, reconnections(flowOf(true, false, true, true, false, false, true)).toList().size)
+  }
+
+  // The state the app starts in is not a change, even when it starts without a network and stays so.
+  @Test
+  fun the_state_at_the_start_is_not_a_trigger() = runTest {
+    assertEquals(0, reconnections(flowOf(true)).toList().size)
+    assertEquals(0, reconnections(flowOf(false)).toList().size)
+    assertEquals(1, reconnections(flowOf(false, true)).toList().size)
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
index d117438..86149a7 100644
--- a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
@@ -5,6 +5,8 @@ import com.touringproject.v2.api.ApiErrorKind
 import com.touringproject.v2.api.AskMemoBody
 import com.touringproject.v2.api.NoteBody
 import com.touringproject.v2.api.NoteSaved
+import com.touringproject.v2.api.OfflineAskBody
+import com.touringproject.v2.api.OfflineAskSaved
 import com.touringproject.v2.api.RideApi
 import com.touringproject.v2.api.RideBody
 import com.touringproject.v2.api.RouteBody
@@ -47,6 +49,13 @@ private class World {
   fun note(id: String, updatedAt: Long, text: String = "展望", rideId: String = "r1") {
     notes[id] = NoteRow(UnsentNote(id, rideId, 1_500, 35.0, 139.0, null, null, null, text, updatedAt))
   }
+  class UnreachedRow(val ask: UnsentUnreached, var sent: Long? = null, var refused: Long? = null, var address: String? = null)
+  val unreached = linkedMapOf<String, UnreachedRow>()
+
+  fun unreached(id: String, updatedAt: Long) {
+    unreached[id] = UnreachedRow(UnsentUnreached(id, "r1", 1_400, 35.0, 139.0, null, null, null, updatedAt))
+  }
+  var online = true
   var hasKey = true
   var gate: CompletableDeferred<Unit>? = null
   var passes = 0
@@ -91,6 +100,15 @@ private class World {
       notes.getValue(noteId).refused = updatedAt
       calls += "refused:note/$noteId"
     }
+    override suspend fun unsentUnreached() =
+      unreached.values.filter { (it.sent ?: -1) < it.ask.updatedAt && it.refused != it.ask.updatedAt }.map { it.ask }
+    override suspend fun unreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?) {
+      unreached.getValue(askId).also { it.sent = updatedAt; it.address = address }
+    }
+    override suspend fun unreachedRefused(askId: String, updatedAt: Long) {
+      unreached.getValue(askId).refused = updatedAt
+      calls += "refused:unreached/$askId"
+    }
   }
 
   private fun call(name: String) {
@@ -110,9 +128,13 @@ private class World {
       return saved[noteId] ?: NoteSaved()
     }
     override suspend fun deleteNote(rideId: String, noteId: String) = call("delete/note/$rideId/$noteId")
+    override suspend fun putOfflineAsk(askId: String, body: OfflineAskBody): OfflineAskSaved {
+      call("unreached/$askId:${body.rideId}")
+      return OfflineAskSaved("箱根町仙石原", 12.5)
+    }
   }
 
-  val sync = RideSync(store, { if (hasKey) api else null }) { _, _ -> }
+  val sync = RideSync(store, { if (hasKey) api else null }, { online }) { _, _ -> }
 }
 
 class RideSyncTest {
@@ -399,4 +421,59 @@ class RideSyncTest {
     assertEquals(listOf("ride/r1:recording"), w.calls)
     assertTrue(w.deletions.isEmpty())
   }
+
+  // Slice 4 spec §5.1: unreached asks go after the point memos and before the memos, so a memo finds its ask there.
+  @Test
+  fun an_unreached_ask_goes_before_the_memos_and_keeps_the_address_it_gets() = runTest {
+    val w = World()
+    w.add(recording)
+    w.rows.getValue("r1").sent = recording.updatedAt
+    w.note("n1", 5_000)
+    w.unreached("u1", 1_400)
+    w.memos["u1"] = World.MemoRow("何の山か", 6_000)
+    w.sync.pass()
+    assertEquals(listOf("note/r1/n1:展望", "unreached/u1:r1", "memo/u1:何の山か"), w.calls)
+    assertEquals("箱根町仙石原", w.unreached.getValue("u1").address)
+    w.calls.clear()
+    w.sync.pass()
+    assertEquals(emptyList<String>(), w.calls)
+  }
+
+  // A failure on the way ends the pass, so the memo of an unreached ask that did not go waits for it.
+  @Test
+  fun the_memo_of_an_unreached_ask_that_failed_to_go_waits_for_it() = runTest {
+    val w = World()
+    w.unreached("u1", 1_400)
+    w.memos["u1"] = World.MemoRow("何の山か", 6_000)
+    w.fail["unreached/u1:r1"] = ApiErrorKind.NETWORK
+    w.sync.pass()
+    assertEquals(listOf("unreached/u1:r1"), w.calls)
+  }
+
+  // 409: the Backend took in an ask under this id; the unreached one is refused, not sent again.
+  @Test
+  fun an_unreached_ask_the_backend_refuses_is_not_sent_again() = runTest {
+    val w = World()
+    w.unreached("u1", 1_400)
+    w.fail["unreached/u1:r1"] = ApiErrorKind.CONFLICT
+    w.sync.pass()
+    assertEquals(listOf("unreached/u1:r1", "refused:unreached/u1"), w.calls)
+    w.calls.clear()
+    w.sync.pass()
+    assertEquals(emptyList<String>(), w.calls)
+  }
+
+  // Slice 4 spec §5.2: without a network a pass does not try; what waits goes on the next trigger with one.
+  @Test
+  fun without_a_network_a_pass_makes_no_request() = runTest {
+    val w = World()
+    w.add(recording, points = 300)
+    w.unreached("u1", 1_400)
+    w.online = false
+    w.sync.pass()
+    assertEquals(emptyList<String>(), w.calls)
+    w.online = true
+    w.sync.pass()
+    assertEquals(listOf("ride/r1:recording", "route/r1/0:300", "unreached/u1:r1"), w.calls)
+  }
 }
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ApiClientTest' --tests '*RideSyncTest' --tests '*RoomSyncStoreTest' --tests '*ReconnectionsTest' --tests '*ConnectivityTest' 2>&1 | grep -E "^e: " | head -3`
Expected: コンパイルで落ちる（`OfflineAskBody`・`UnsentUnreached`・`reconnections` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/AndroidManifest.xml b/app/src/main/AndroidManifest.xml
index a2edda8..d31fb3e 100644
--- a/app/src/main/AndroidManifest.xml
+++ b/app/src/main/AndroidManifest.xml
@@ -3,6 +3,8 @@
   xmlns:tools="http://schemas.android.com/tools">
 
   <uses-permission android:name="android.permission.INTERNET" />
+  <!-- Connectivity follows the default network (Android #62); declared here rather than left to a library. -->
+  <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
   <uses-permission android:name="android.permission.RECORD_AUDIO" />
   <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />
   <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index a1a4651..04ac060 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -61,6 +61,7 @@ import com.touringproject.v2.store.RoomRideStore
 import com.touringproject.v2.store.RoomSyncStore
 import com.touringproject.v2.sync.RideSync
 import com.touringproject.v2.sync.credentialChanges
+import com.touringproject.v2.sync.reconnections
 import com.touringproject.v2.voice.VOICE_IDLE
 import com.touringproject.v2.voice.VoiceDeps
 import com.touringproject.v2.voice.VoiceInput
@@ -109,7 +110,10 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   val recordsList: StateFlow<List<RideListItem>?> = records.list.stateIn(scope, SharingStarted.WhileSubscribed(5_000), null)
   private val notices = RideNotices(context)
 
-  /** Sends rides, routes, memos, point memos and deletions; a pass runs on each trigger (slice 2 spec §5.3). */
+  /** Whether the device has a network now: SC-19's voice input, the ask loop and the sync follow it. */
+  val connectivity = Connectivity(context)
+
+  /** Sends rides, routes, memos, point memos, unreached asks and deletions; a pass runs on each trigger (slice 2 spec §5.3). */
   val sync = RideSync(
     RoomSyncStore(database.rides(), database.asks(), database.notes()),
     api = {
@@ -118,6 +122,7 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       if (apiBaseUrl.isEmpty() || key == null || user == null) null else ApiClient(apiBaseUrl, key, user, http)
     },
     log = { event, data -> Log.i("trv2.sync", "$event $data") },
+    online = { connectivity.online.value },
   )
 
   /** SC-07 and SC-08 change kept asks through here; each change is something new to send (slice 3 spec §5.1). */
@@ -207,9 +212,6 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     Log.w("trv2.recordings", message, e)
   }
 
-  /** Whether the device has a network now (SC-19's voice input). */
-  val connectivity = Connectivity(context)
-
   private val voiceFlow = MutableStateFlow(VOICE_IDLE)
   val voiceState: StateFlow<VoiceState> = voiceFlow.asStateFlow()
 
@@ -278,6 +280,8 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       readiness.ridesLoaded()
     }
     scope.launch { sync.run() }
+    // The network coming back lets what waited for it go, while the process lives (slice 4 spec §5.2).
+    scope.launch { reconnections(connectivity.online).collect { sync.request() } }
     // SC-16: the recording ride's deadline follows the longest recording time, wherever it was changed (Android #33).
     scope.launch { maxRecordingChanges(settings.settings).collect { rides.maxRecordingChanged() } }
     scope.launch {
diff --git a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
index 80f1256..03eb781 100644
--- a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
+++ b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
@@ -18,8 +18,9 @@ import java.util.concurrent.TimeUnit
 import kotlin.coroutines.resumeWithException
 
 // Backend API (Backend/openapi.yaml). Errors are classified so the ask loop can pick the spoken message.
-// GONE is 410: the record, or its ride, was deleted (slice 3 spec §5.4); the sync treats it as sent.
-enum class ApiErrorKind { INVALID_KEY, BAD_REQUEST, NOT_FOUND, GONE, RATE_LIMITED, SERVER, NETWORK }
+// GONE is 410: the record, or its ride, was deleted (slice 3 spec §5.4); the sync treats it as sent. CONFLICT is 409: an
+// unreached ask's id is one the Backend took in (slice 4 spec §4.4); the sync treats it as refused.
+enum class ApiErrorKind { INVALID_KEY, BAD_REQUEST, NOT_FOUND, GONE, CONFLICT, RATE_LIMITED, SERVER, NETWORK }
 
 class ApiError(val kind: ApiErrorKind, message: String? = null) : Exception(message ?: kind.name)
 
@@ -104,15 +105,23 @@ data class NoteBody(val at: String, val location: Point?, val headingSample: Hea
 /** What the Backend settled for a point memo when it first took it; null when it could not tell (no place, no heading). */
 @Serializable data class NoteSaved(val address: String? = null, val headingDegrees: Double? = null)
 
+/** An ask that never reached the Backend, as a whole (slice 4 spec §4.4). location is null when it had no place yet. */
+@Serializable
+data class OfflineAskBody(val askedAt: String, val location: Point?, val headingSample: HeadingSample?, val rideId: String, val updatedAt: String)
+
+/** What the Backend settled for an unreached ask when it first took it; null when it could not tell. */
+@Serializable data class OfflineAskSaved(val address: String? = null, val headingDegrees: Double? = null)
+
 /**
  * Every call may be sent again and again: the Backend keeps one copy of each, and a deletion is the same however often
- * it comes. A 400 throws BAD_REQUEST, a 404 NOT_FOUND and a 410 (deleted) GONE.
+ * it comes. A 400 throws BAD_REQUEST, a 404 NOT_FOUND, a 409 CONFLICT and a 410 (deleted) GONE.
  */
 interface RideApi {
   suspend fun putRide(rideId: String, body: RideBody)
   suspend fun putRoute(rideId: String, seq: Int, body: RouteBody)
   suspend fun putAskMemo(askId: String, body: AskMemoBody)
   suspend fun putNote(rideId: String, noteId: String, body: NoteBody): NoteSaved
+  suspend fun putOfflineAsk(askId: String, body: OfflineAskBody): OfflineAskSaved
   suspend fun deleteRide(rideId: String)
   suspend fun deleteAsk(askId: String)
   suspend fun deleteNote(rideId: String, noteId: String)
@@ -127,6 +136,7 @@ private fun kindFor(status: Int): ApiErrorKind? = when {
   status == 403 -> ApiErrorKind.INVALID_KEY
   status == 400 -> ApiErrorKind.BAD_REQUEST
   status == 404 -> ApiErrorKind.NOT_FOUND
+  status == 409 -> ApiErrorKind.CONFLICT
   status == 410 -> ApiErrorKind.GONE
   status == 429 -> ApiErrorKind.RATE_LIMITED
   status >= 500 -> ApiErrorKind.SERVER
@@ -189,6 +199,11 @@ class ApiClient(
   override suspend fun putNote(rideId: String, noteId: String, body: NoteBody): NoteSaved =
     json.decodeFromString(NoteSaved.serializer(), request("PUT", "/rides/$rideId/notes/$noteId", rideJson.encodeToString(NoteBody.serializer(), body), TRANSIENT))
 
+  override suspend fun putOfflineAsk(askId: String, body: OfflineAskBody): OfflineAskSaved = json.decodeFromString(
+    OfflineAskSaved.serializer(),
+    request("PUT", "/asks/$askId/offline", rideJson.encodeToString(OfflineAskBody.serializer(), body), TRANSIENT),
+  )
+
   override suspend fun deleteRide(rideId: String) {
     request("DELETE", "/rides/$rideId", null, TRANSIENT)
   }
diff --git a/app/src/main/java/com/touringproject/v2/net/Connectivity.kt b/app/src/main/java/com/touringproject/v2/net/Connectivity.kt
index add4ecb..ee3da6e 100644
--- a/app/src/main/java/com/touringproject/v2/net/Connectivity.kt
+++ b/app/src/main/java/com/touringproject/v2/net/Connectivity.kt
@@ -10,21 +10,28 @@ import kotlinx.coroutines.flow.asStateFlow
 
 /**
  * Whether the device's default network reaches the internet, followed for the life of the process (slice 3 spec §7.3:
- * SC-19 cannot send a voice without one). It says nothing of whether the Backend answers; a send can still fail.
+ * SC-19 cannot send a voice without one; slice 4 spec §4.1 and §5.2: the ask loop and the sync). It says nothing of
+ * whether the Backend answers; a send can still fail.
  */
 class Connectivity(context: Context) {
   private val manager = context.getSystemService(ConnectivityManager::class.java)
   private val state = MutableStateFlow(manager.activeNetwork?.let { manager.getNetworkCapabilities(it) }.reaches())
   val online: StateFlow<Boolean> = state.asStateFlow()
+  // The default network the last report was about. Losing another one (the old network, reported late after a switch
+  // from Wi-Fi to mobile data) leaves the state alone (Android #62).
+  @Volatile private var current: Network? = manager.activeNetwork
 
   init {
     manager.registerDefaultNetworkCallback(
       object : ConnectivityManager.NetworkCallback() {
         override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) {
+          current = network
           state.value = capabilities.reaches()
         }
 
         override fun onLost(network: Network) {
+          if (current != null && network != current) return
+          current = null
           state.value = false
         }
       },
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 04316b0..f99c759 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -220,6 +220,23 @@ interface AskDao {
   @Query("UPDATE asks SET memoRejectedUpdatedAt = :updatedAt WHERE askId = :askId")
   suspend fun markMemoRefused(askId: String, updatedAt: Long)
 
+  // Sending unreached asks (slice 4 spec §5.1): those changed since they were taken, unless that version was refused.
+  @Query(
+    "SELECT * FROM asks WHERE status = 'offline' AND (sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
+      "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt) ORDER BY updatedAt",
+  )
+  suspend fun unsentUnreached(): List<AskEntity>
+
+  /** As a point memo's: the marker never moves back, and an answer without an address or heading keeps what it has. */
+  @Query(
+    "UPDATE asks SET sentUpdatedAt = MAX(IFNULL(sentUpdatedAt, :updatedAt), :updatedAt), address = IFNULL(:address, address), " +
+      "headingDegrees = IFNULL(:headingDegrees, headingDegrees) WHERE askId = :askId",
+  )
+  suspend fun markUnreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?)
+
+  @Query("UPDATE asks SET rejectedUpdatedAt = :updatedAt WHERE askId = :askId")
+  suspend fun markUnreachedRefused(askId: String, updatedAt: Long)
+
   @Insert(onConflict = OnConflictStrategy.REPLACE)
   suspend fun markDeleted(deletion: DeletionEntity)
 
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
index 0ff4511..998361c 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
@@ -7,6 +7,7 @@ import com.touringproject.v2.sync.SyncStore
 import com.touringproject.v2.sync.Unsent
 import com.touringproject.v2.sync.UnsentAskMemo
 import com.touringproject.v2.sync.UnsentNote
+import com.touringproject.v2.sync.UnsentUnreached
 
 class RoomSyncStore(private val dao: RideDao, private val asks: AskDao, private val notes: NoteDao) : SyncStore {
   override suspend fun unsent(): List<Unsent> = dao.unsentSnapshot().map {
@@ -42,4 +43,16 @@ class RoomSyncStore(private val dao: RideDao, private val asks: AskDao, private
     notes.markSent(noteId, updatedAt, address, headingDegrees)
 
   override suspend fun noteRefused(noteId: String, updatedAt: Long) = notes.markRefused(noteId, updatedAt)
+
+  // An unreached ask always has its ride and its version (slice 4 spec §4.2); a row without them is not one to send.
+  override suspend fun unsentUnreached(): List<UnsentUnreached> = asks.unsentUnreached().mapNotNull {
+    val rideId = it.rideId ?: return@mapNotNull null
+    val updatedAt = it.updatedAt ?: return@mapNotNull null
+    UnsentUnreached(it.askId, rideId, it.askedAt, it.latitude, it.longitude, it.sampleLatitude, it.sampleLongitude, it.sampleAt, updatedAt)
+  }
+
+  override suspend fun unreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?) =
+    asks.markUnreachedSent(askId, updatedAt, address, headingDegrees)
+
+  override suspend fun unreachedRefused(askId: String, updatedAt: Long) = asks.markUnreachedRefused(askId, updatedAt)
 }
diff --git a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
index a9bdd28..33d97b0 100644
--- a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
@@ -4,6 +4,7 @@ import com.touringproject.v2.api.ApiError
 import com.touringproject.v2.api.ApiErrorKind
 import com.touringproject.v2.api.AskMemoBody
 import com.touringproject.v2.api.NoteSaved
+import com.touringproject.v2.api.OfflineAskSaved
 import com.touringproject.v2.api.RideApi
 import com.touringproject.v2.api.RouteBody
 import com.touringproject.v2.ride.Ride
@@ -16,6 +17,7 @@ import kotlinx.coroutines.flow.combine
 import kotlinx.coroutines.flow.distinctUntilChanged
 import kotlinx.coroutines.flow.drop
 import kotlinx.coroutines.flow.filter
+import kotlinx.coroutines.flow.flow
 import kotlinx.coroutines.flow.map
 import kotlinx.serialization.SerializationException
 
@@ -42,6 +44,19 @@ data class UnsentNote(
   val updatedAt: Long,
 )
 
+/** An unreached ask that has changed since the Backend last took it (slice 4 spec §5.1). */
+data class UnsentUnreached(
+  val askId: String,
+  val rideId: String,
+  val askedAt: Long,
+  val latitude: Double?,
+  val longitude: Double?,
+  val sampleLatitude: Double?,
+  val sampleLongitude: Double?,
+  val sampleAt: Long?,
+  val updatedAt: Long,
+)
+
 interface SyncStore {
   /**
    * Rides whose meta has changed since it was sent (and was not refused), or that have points not yet sent. Read in
@@ -68,22 +83,30 @@ interface SyncStore {
   suspend fun noteSent(noteId: String, updatedAt: Long, address: String?, headingDegrees: Double?)
   /** The Backend refused the point memo as of updatedAt (400); that version is not sent again. */
   suspend fun noteRefused(noteId: String, updatedAt: Long)
+  suspend fun unsentUnreached(): List<UnsentUnreached>
+  /** The Backend took the unreached ask as of updatedAt; address and headingDegrees are what it settled, null when it did not say. */
+  suspend fun unreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?)
+  /** The Backend refused the unreached ask as of updatedAt (400, or 409 for an id it took in); it is not sent again. */
+  suspend fun unreachedRefused(askId: String, updatedAt: Long)
 }
 
 /** How the Backend answered a send that did not fail on the way. */
 private enum class Reply { TAKEN, REFUSED, GONE }
 
 /**
- * Sends rides, their routes, memos and deletions to the Backend (slice 2 spec §5.3, slice 3 spec §5). A pass reads
- * what is left to send and sends it, deletions first, so a deleted record's old version is never put back in the same
- * pass; with nothing left it makes no request at all. Passes run one at a time; the ones asked for while a pass runs
- * fold into one more. A failure other than a refusal ends the pass, and the next trigger tries again; there is no
- * timer of its own.
+ * Sends rides, their routes, memos, point memos, unreached asks and deletions to the Backend (slice 2 spec §5.3, slice
+ * 3 spec §5, slice 4 spec §5). A pass reads what is left to send and sends it, deletions first, so a deleted record's
+ * old version is never put back in the same pass; with nothing left it makes no request at all. Unreached asks go
+ * before the memos, so a memo on one finds its ask at the Backend. Passes run one at a time; the ones asked for while
+ * a pass runs fold into one more. A failure other than a refusal ends the pass, and the next trigger tries again;
+ * there is no timer of its own. Without a network a pass does not try at all: the network coming back is a trigger.
  */
 class RideSync(
   private val store: SyncStore,
   /** The client for the current key and user name, or null while there is no key or no API URL. */
   private val api: () -> RideApi?,
+  /** Whether the device has a network now (slice 4 spec §5.2). */
+  private val online: () -> Boolean = { true },
   private val log: (event: String, data: Map<String, Any?>) -> Unit,
 ) {
   private val requests = Channel<Unit>(Channel.CONFLATED)
@@ -106,6 +129,7 @@ class RideSync(
   }
 
   suspend fun pass() {
+    if (!online()) return
     val client = api() ?: return
     val deletions = read("deletions") { store.deletions() } ?: return
     for (deletion in deletions) {
@@ -119,6 +143,10 @@ class RideSync(
     for (note in notes) {
       if (!attempt(note.id) { sendNote(client, note) }) return
     }
+    val unreached = read("unreached") { store.unsentUnreached() } ?: return
+    for (ask in unreached) {
+      if (!attempt(ask.askId) { sendUnreached(client, ask) }) return
+    }
     val memos = read("ask_memos") { store.unsentAskMemos() } ?: return
     for (memo in memos) {
       if (!attempt(memo.askId) { sendAskMemo(client, memo) }) return
@@ -186,6 +214,16 @@ class RideSync(
     }
   }
 
+  // GONE: the ask or its ride was deleted on the Backend; it has no address to give.
+  private suspend fun sendUnreached(client: RideApi, ask: UnsentUnreached) {
+    var saved: OfflineAskSaved? = null
+    if (reply(ask.askId, "unreached") { saved = client.putOfflineAsk(ask.askId, ask.toBody()) } == Reply.REFUSED) {
+      store.unreachedRefused(ask.askId, ask.updatedAt)
+    } else {
+      store.unreachedSent(ask.askId, ask.updatedAt, saved?.address, saved?.headingDegrees)
+    }
+  }
+
   private suspend fun sendAskMemo(client: RideApi, memo: UnsentAskMemo) {
     if (reply(memo.askId, "memo") { client.putAskMemo(memo.askId, AskMemoBody(memo.memo, iso(memo.updatedAt))) } == Reply.REFUSED) {
       store.askMemoRefused(memo.askId, memo.updatedAt)
@@ -195,7 +233,8 @@ class RideSync(
   }
 
   /**
-   * TAKEN when the Backend took it; REFUSED when it refused it (400, or 404 for a memo of an ask it does not have) or
+   * TAKEN when the Backend took it; REFUSED when it refused it (400, 404 for a memo of an ask it does not have, or 409
+   * for an unreached ask whose id it took in) or
    * the device could not even build it (a value that cannot be written as JSON, Android #25); GONE when it was deleted
    * there (410). Refusals and GONE are logged. Other failures throw and end the pass.
    */
@@ -204,7 +243,7 @@ class RideSync(
     Reply.TAKEN
   } catch (e: ApiError) {
     when (e.kind) {
-      ApiErrorKind.BAD_REQUEST, ApiErrorKind.NOT_FOUND -> {
+      ApiErrorKind.BAD_REQUEST, ApiErrorKind.NOT_FOUND, ApiErrorKind.CONFLICT -> {
         log("sync_refused", mapOf("id" to id, "what" to what, "error" to e.message))
         Reply.REFUSED
       }
@@ -231,3 +270,15 @@ fun credentialChanges(key: Flow<String?>, userName: Flow<String?>): Flow<Unit> =
     .drop(1)
     .filter { (k, u) -> k != null && u != null }
     .map { }
+
+/**
+ * A trigger each time the device's network comes back (slice 4 spec §5.2): a change from none to one, not the state it
+ * starts in. While the process lives, what waited for the network then goes without the app coming to the front.
+ */
+fun reconnections(online: Flow<Boolean>): Flow<Unit> = flow {
+  var before: Boolean? = null
+  online.collect { now ->
+    if (before == false && now) emit(Unit)
+    before = now
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt b/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
index dbdb216..06b89d7 100644
--- a/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
@@ -2,6 +2,7 @@ package com.touringproject.v2.sync
 
 import com.touringproject.v2.api.HeadingSample
 import com.touringproject.v2.api.NoteBody
+import com.touringproject.v2.api.OfflineAskBody
 import com.touringproject.v2.api.Point
 import com.touringproject.v2.api.PointBody
 import com.touringproject.v2.api.RideBody
@@ -65,3 +66,10 @@ fun UnsentNote.toBody(): NoteBody {
   val sample = if (sampleLatitude != null && sampleLongitude != null && sampleAt != null) HeadingSample(sampleLatitude, sampleLongitude, iso(sampleAt)) else null
   return NoteBody(iso(at), location, sample, text, iso(updatedAt))
 }
+
+/** An unreached ask goes with its place and sample as a point memo does: each only when it is whole. */
+fun UnsentUnreached.toBody(): OfflineAskBody {
+  val location = if (latitude != null && longitude != null) Point(latitude, longitude) else null
+  val sample = if (sampleLatitude != null && sampleLongitude != null && sampleAt != null) HeadingSample(sampleLatitude, sampleLongitude, iso(sampleAt)) else null
+  return OfflineAskBody(iso(askedAt), location, sample, rideId, iso(updatedAt))
+}
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t3.log 2>&1; tail -1 /tmp/trv2-t3.log`
Expected: `BUILD SUCCESSFUL`（544件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/AndroidManifest.xml app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/api/ApiClient.kt app/src/main/java/com/touringproject/v2/net/Connectivity.kt app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt app/src/main/java/com/touringproject/v2/sync/RideSync.kt app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt app/src/test/java/com/touringproject/v2/net/ConnectivityTest.kt app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt app/src/test/java/com/touringproject/v2/sync/ReconnectionsTest.kt
git commit -m "feat: send unreached asks, send when the network comes back, and follow the default network across a switch (#62)"
```

---

### Task 4: 表示: 時系列・ピン・SC-07

**Files:**
- Modify: `ui/RecordLabels.kt`・`ui/RecordsScreens.kt`
- Test: `ui/RecordLabelsTest.kt`・`ui/RecordsScreensTest.kt`

**Interfaces:**
- Consumes: `AskOutcome.OFFLINE`・`AskRecord.sent`（Task 1）
- Produces:
  - `const val UNREACHED_TEXT = "（通信できず、質問できなかった）"`・`const val UNREACHED_ANSWER = "質問の内容は残していません"`
  - `fun askPlace(ask: AskRecord): String`（時系列・ピンのカード・SC-08 の題で使う）
  - `AskDetailUi.unreached: Boolean = false`（最後の引数）。`AskDetailScreen` は true のとき吹き出しの代わりに `askUnreached` を出す

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
index 861bf85..d343d32 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
@@ -260,4 +260,41 @@ class RecordLabelsTest {
     assertEquals("📝 地点メモ 1件", ui.summary.notes)
     assertEquals(1, ui.timeline.filterIsInstance<TimelineRow.Note>().size)
   }
+
+  private fun unreached(id: String, at: Long, latitude: Double? = 35.2, address: String? = null, sent: Boolean = false) =
+    com.touringproject.v2.ask.unreachedAsk(id, at, latitude?.let { com.touringproject.v2.location.Fix(it, 139.0, at, 5.0) }, null, "r1")
+      .copy(address = address, sent = sent)
+
+  // Slice 4 spec §4.3: an unreached ask is numbered with the asks, says so in place of its question, and gets its place
+  // once it has been sent, as a point memo does.
+  @Test
+  fun an_unreached_ask_is_numbered_with_the_asks_and_says_it_never_reached_the_backend() {
+    val asks = listOf(ask("a1", ms(16, 9, 41)), unreached("u1", ms(16, 10, 5)), unreached("u2", ms(16, 10, 20), latitude = null))
+    val rows = rideTimeline(ride, asks, zone).filterIsInstance<TimelineRow.Ask>()
+    assertEquals(listOf(1, 2, 3), rows.map { it.number })
+    assertEquals(listOf("右手の山は？", UNREACHED_TEXT, UNREACHED_TEXT), rows.map { it.text })
+    assertEquals(listOf("足柄下郡箱根町仙石原", "住所は送信後", "位置の記録なし"), rows.map { it.place })
+    assertEquals(listOf(false, true, true), rows.map { it.failed })
+    assertEquals("足柄下郡箱根町仙石原", askPlace(unreached("u1", 0, address = "神奈川県足柄下郡箱根町仙石原", sent = true)))
+    assertEquals("場所不明", askPlace(unreached("u1", 0, sent = true)))
+  }
+
+  @Test
+  fun an_unreached_asks_pin_card_and_detail_tell_that_nothing_was_kept() {
+    val asks = listOf(ask("a1", ms(16, 9, 41)), unreached("u1", ms(16, 10, 5)))
+    val card = pinCard(asks, "u1", zone)!!
+    assertEquals("2 · 10:05 · 住所は送信後", card.heading)
+    assertEquals(UNREACHED_TEXT, card.question)
+    assertEquals(UNREACHED_ANSWER, card.answer)
+    val detail = askDetail(asks, "u1", zone)!!
+    assertEquals(true, detail.unreached)
+    assertEquals("住所は送ったあとに付きます", detail.place)
+    assertNull(detail.question)
+    assertNull(detail.failure)
+    assertEquals("停車中", detail.direction)
+    assertEquals("神奈川県足柄下郡箱根町仙石原", askDetail(listOf(unreached("u1", 0, address = "神奈川県足柄下郡箱根町仙石原", sent = true)), "u1", zone)!!.place)
+    assertEquals("位置を記録できませんでした", askDetail(listOf(unreached("u1", 0, latitude = null)), "u1", zone)!!.place)
+    assertEquals("住所は分かりませんでした", askDetail(listOf(unreached("u1", 0, sent = true)), "u1", zone)!!.place)
+    assertEquals("会話 2 · 10:05 住所は送信後", askMemoTarget(asks, "u1", zone))
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
index 894be01..fc433a2 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
@@ -408,4 +408,21 @@ class RecordsScreensTest {
     rule.onNodeWithTag("timeline").performScrollToNode(hasTestTag("ask-a1"))
     assertEquals(false to false, asks to notes)
   }
+
+  // Slice 4 spec §4.3: an unreached ask shows that it never reached the Backend instead of the question and answer,
+  // and offers its memo for what the rider wanted to know.
+  @Test
+  fun an_unreached_ask_says_so_instead_of_a_question_and_offers_its_memo() {
+    val unreached = AskDetailUi(
+      "会話 2 / 2", "10月16日（金） 10:05", "住所は送ったあとに付きます", "停車中", "🎤 声で質問", null, null, null, "a1", null, unreached = true,
+    )
+    var memos = 0
+    rule.setContent { AskDetailScreen(unreached, null, fakeMap, "u1", {}, {}, onMemo = { memos++ }) }
+    rule.onNodeWithTag("askUnreached").assertTextEquals("📵 通信できず、質問できなかった")
+    rule.onNodeWithText("質問の内容は残していません。何を聞きたかったかは、メモに書けます。").assertExists()
+    rule.onNodeWithTag("askQuestion").assertDoesNotExist()
+    rule.onNodeWithTag("askAnswer").assertDoesNotExist()
+    rule.onNodeWithText("＋ メモを追加").performScrollTo().performClick()
+    assertEquals(1, memos)
+  }
 }
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RecordLabelsTest' --tests '*RecordsScreensTest' 2>&1 | grep -E "^e: " | head -3`
Expected: コンパイルで落ちる（`UNREACHED_TEXT`・`askPlace`・`unreached` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
index c4c7541..78a9dc5 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
@@ -173,8 +173,26 @@ fun notePlace(note: NoteRecord): String = when {
   else -> "住所は送信後"
 }
 
+/** What an unreached ask shows in place of its question, in lists and on pins (the mock's SC-07). */
+const val UNREACHED_TEXT = "（通信できず、質問できなかった）"
+
+/** What an unreached ask shows in place of its answer: nothing it said was kept (US-C-09.002). */
+const val UNREACHED_ANSWER = "質問の内容は残していません"
+
+/**
+ * Where an ask was, in short. An unreached ask gets its address once it has been sent, as a point memo does (slice 4
+ * spec §4.4); the others have theirs from the Backend.
+ */
+fun askPlace(ask: AskRecord): String = when {
+  ask.outcome != AskOutcome.OFFLINE -> shortPlace(ask.address)
+  ask.latitude == null -> "位置の記録なし"
+  ask.address != null -> shortPlace(ask.address)
+  ask.sent -> "場所不明"
+  else -> "住所は送信後"
+}
+
 /** What a list shows of an ask: what was heard, or why nothing was. */
-fun askText(ask: AskRecord): String = ask.transcript?.takeIf { it.isNotBlank() } ?: when {
+fun askText(ask: AskRecord): String = if (ask.outcome == AskOutcome.OFFLINE) UNREACHED_TEXT else ask.transcript?.takeIf { it.isNotBlank() } ?: when {
   ask.outcome == AskOutcome.ANSWERED -> "（聞き取った文がありません）"
   ask.failure == "no_speech" -> "（聞き取れませんでした）"
   ask.failure == "timeout" -> "（時間内に答えが届きませんでした）"
@@ -252,8 +270,8 @@ fun rideTimeline(ride: Ride, asks: List<AskRecord>, zone: ZoneId, notes: List<No
         if (ask.newConversation && asked) rows += TimelineRow.NewConversation
         asked = true
         rows += TimelineRow.Ask(
-          ask.askId, numbers.getValue(ask.askId), TIME.format(at(ask.askedAt, zone)), shortPlace(ask.address), askText(ask),
-          ask.outcome == AskOutcome.FAILED, memo = ask.memo != null,
+          ask.askId, numbers.getValue(ask.askId), TIME.format(at(ask.askedAt, zone)), askPlace(ask), askText(ask),
+          ask.outcome != AskOutcome.ANSWERED, memo = ask.memo != null,
         )
       }
       is Event.PauseAt -> rows += TimelineRow.Pause(
@@ -281,7 +299,10 @@ fun failureLabel(failure: String?): String = when (failure) {
   else -> "AI が答えられませんでした"
 }
 
-/** SC-07. question is null when nothing was heard; failure is set for an ask that got no answer. */
+/**
+ * SC-07. question is null when nothing was heard; failure is set for an ask that got no answer. An unreached ask has
+ * neither: unreached says to show that it never reached the Backend instead (slice 4 spec §4.3).
+ */
 data class AskDetailUi(
   val title: String,
   val time: String,
@@ -295,8 +316,17 @@ data class AskDetailUi(
   val next: String?,
   /** The conversation's memo (SC-07); null when it has none. */
   val memo: String? = null,
+  val unreached: Boolean = false,
 )
 
+/** SC-07's place of an unreached ask, in full: worded as SC-19 words a point memo's (slice 4 spec §4.3). */
+private fun unreachedPlace(ask: AskRecord): String = when {
+  ask.latitude == null -> "位置を記録できませんでした"
+  ask.address != null -> ask.address
+  ask.sent -> "住所は分かりませんでした"
+  else -> "住所は送ったあとに付きます"
+}
+
 /** askId's place among the asks it was opened from (the ride's): 会話 3 / 5, and the asks before and after it. */
 fun askDetail(asks: List<AskRecord>, askId: String, zone: ZoneId): AskDetailUi? {
   val ordered = asks.sortedBy { it.askedAt }
@@ -304,10 +334,11 @@ fun askDetail(asks: List<AskRecord>, askId: String, zone: ZoneId): AskDetailUi?
   if (i < 0) return null
   val ask = ordered[i]
   val time = at(ask.askedAt, zone)
+  val unreached = ask.outcome == AskOutcome.OFFLINE
   return AskDetailUi(
     title = "会話 ${i + 1} / ${ordered.size}",
     time = "${dayLabel(time.toLocalDate())} ${TIME.format(time)}",
-    place = ask.address?.ifBlank { null } ?: "場所不明",
+    place = if (unreached) unreachedPlace(ask) else ask.address?.ifBlank { null } ?: "場所不明",
     direction = directionLabel(ask.headingDegrees),
     input = if (ask.input == "text") "⌨ 文字で質問" else "🎤 声で質問",
     question = ask.transcript?.ifBlank { null },
@@ -316,6 +347,7 @@ fun askDetail(asks: List<AskRecord>, askId: String, zone: ZoneId): AskDetailUi?
     previous = ordered.getOrNull(i - 1)?.askId,
     next = ordered.getOrNull(i + 1)?.askId,
     memo = ask.memo,
+    unreached = unreached,
   )
 }
 
@@ -328,7 +360,8 @@ data class PinCardUi(val id: String, val heading: String, val question: String,
 fun pinCard(asks: List<AskRecord>, askId: String, zone: ZoneId): PinCardUi? {
   val ask = asks.firstOrNull { it.askId == askId } ?: return null
   val number = askNumbers(asks).getValue(askId)
-  return PinCardUi(askId, "$number · ${TIME.format(at(ask.askedAt, zone))} · ${shortPlace(ask.address)}", askText(ask), ask.answer?.ifBlank { null })
+  val answer = if (ask.outcome == AskOutcome.OFFLINE) UNREACHED_ANSWER else ask.answer?.ifBlank { null }
+  return PinCardUi(askId, "$number · ${TIME.format(at(ask.askedAt, zone))} · ${askPlace(ask)}", askText(ask), answer)
 }
 
 /** A point memo's card: 2 · 10:24 · 新橋 · 📝 地点メモ, then its text (the mock). */
@@ -369,5 +402,5 @@ fun noteHeader(note: NoteRecord, rideName: String, zone: ZoneId): NoteHeaderUi {
 /** What SC-08 says it is writing for an ask: 会話 3 · 09:41 箱根町仙石原 (the mock). null when the ask is not among them. */
 fun askMemoTarget(asks: List<AskRecord>, askId: String, zone: ZoneId): String? {
   val ask = asks.firstOrNull { it.askId == askId } ?: return null
-  return "会話 ${askNumbers(asks).getValue(askId)} · ${TIME.format(at(ask.askedAt, zone))} ${shortPlace(ask.address)}"
+  return "会話 ${askNumbers(asks).getValue(askId)} · ${TIME.format(at(ask.askedAt, zone))} ${askPlace(ask)}"
 }
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
index 02c6171..d537ea3 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
@@ -8,6 +8,7 @@ import androidx.compose.foundation.clickable
 import androidx.compose.foundation.layout.Arrangement
 import androidx.compose.foundation.layout.Box
 import androidx.compose.foundation.layout.Column
+import androidx.compose.foundation.layout.ColumnScope
 import androidx.compose.foundation.layout.Row
 import androidx.compose.foundation.layout.fillMaxSize
 import androidx.compose.foundation.layout.fillMaxWidth
@@ -400,19 +401,12 @@ fun AskDetailScreen(
         Meta("進行方向", detail.direction)
         Meta("入力", detail.input)
       }
-      Muted("あなた", Modifier.align(Alignment.End), 13)
-      Text(
-        detail.question ?: "（聞き取れませんでした）",
-        Modifier.align(Alignment.End).background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(12.dp)).padding(12.dp).testTag("askQuestion"),
-      )
-      Muted("AI", size = 13)
-      if (detail.failure != null) {
-        Text("答えられませんでした: ${detail.failure}", color = Rec, modifier = Modifier.testTag("askFailure"))
+      if (detail.unreached) {
+        // Slice 4 spec §4.3: nothing the rider said was kept; the memo is where to write what they wanted to know.
+        Text("📵 通信できず、質問できなかった", color = Rec, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("askUnreached"))
+        Muted("$UNREACHED_ANSWER。何を聞きたかったかは、メモに書けます。", size = 14)
       } else {
-        Text(
-          detail.answer ?: "",
-          Modifier.background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp)).padding(12.dp).testTag("askAnswer"),
-        )
+        AskExchange(detail)
       }
       MemoBox("メモ", detail.memo, "＋ メモを追加", onMemo, "askMemo")
       OutlinedButton(
@@ -434,6 +428,25 @@ fun AskDetailScreen(
   }
 }
 
+/** The question as heard and the answer, or why there was none. */
+@Composable
+private fun ColumnScope.AskExchange(detail: AskDetailUi) {
+  Muted("あなた", Modifier.align(Alignment.End), 13)
+  Text(
+    detail.question ?: "（聞き取れませんでした）",
+    Modifier.align(Alignment.End).background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(12.dp)).padding(12.dp).testTag("askQuestion"),
+  )
+  Muted("AI", size = 13)
+  if (detail.failure != null) {
+    Text("答えられませんでした: ${detail.failure}", color = Rec, modifier = Modifier.testTag("askFailure"))
+  } else {
+    Text(
+      detail.answer ?: "",
+      Modifier.background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp)).padding(12.dp).testTag("askAnswer"),
+    )
+  }
+}
+
 @Composable
 private fun Meta(label: String, value: String) {
   Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t4.log 2>&1; tail -1 /tmp/trv2-t4.log`
Expected: `BUILD SUCCESSFUL`（547件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
git commit -m "feat: show unreached asks in the timeline, on the map and in SC-07"
```

---

### Task 5: #53（走行の保存待ち）と #28（警告の帯）

**Files:**
- Modify: `ride/RideController.kt`・`store/RoomAskLog.kt`・`ui/Labels.kt`・`ui/HomeScreen.kt`・`ui/AppUi.kt`
- Test: `ride/RideControllerTest.kt`・`store/RoomAskLogTest.kt`・`ui/LabelsTest.kt`・`ui/ScreensTest.kt`

**Interfaces:**
- Consumes: 既存の `RideController.unsaved`・`save`・`write`
- Produces:
  - `RideController.keptRide(rideId): Ride?`（private）。`rename`・`memo` が使う
  - `Banner.ASK_STORE_FAILED`（「書けなかった質問があります」・`leads = false`）・`homeBanner(..., storeFailed: Boolean = false, askStoreFailed: Boolean = false)`
  - `HomeScreen(..., onDismissAskFailure: () -> Unit = {})`（`ride` の直後）・`RoomAskLog.dismiss()`

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
index 14bdcea..fb07bfd 100644
--- a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
@@ -748,4 +748,65 @@ class RideControllerTest {
     w.controller.start("次の走行")
     assertEquals(listOf("次の走行"), w.rides.values.map { it.name })
   }
+
+  // Android #53: a deletion that fails does not drop the change still waiting to be written.
+  @Test
+  fun a_ride_whose_deletion_fails_keeps_its_waiting_rename() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    w.controller.end("箱根")
+    w.failSaves = 2
+    w.failDeletes = true
+    assertFalse(w.controller.rename("r1", "御殿場"))
+    assertFalse(w.controller.delete("r1"))
+    w.failDeletes = false
+    assertTrue(w.controller.memo("r1", "また来たい"))
+    assertEquals("御殿場" to "また来たい", w.stored().let { it.name to it.memo })
+  }
+
+  // Android #53: an edit of a ride whose change is still waiting starts from that change, so it does not undo it.
+  @Test
+  fun an_edit_of_a_ride_waiting_to_be_written_keeps_the_waiting_change() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    w.controller.end("箱根")
+    w.failSaves = 1
+    assertFalse(w.controller.rename("r1", "御殿場"))
+    // The waiting rename fails once more when the memo comes, then the memo's own save works.
+    w.failSaves = 1
+    assertTrue(w.controller.memo("r1", "また来たい"))
+    assertEquals("御殿場" to "また来たい", w.stored().let { it.name to it.memo })
+  }
+
+  // Android #53: SC-08 said the memo was not saved, so it is not written later behind the rider's back.
+  @Test
+  fun a_memo_that_could_not_be_written_is_not_written_later() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    w.controller.end("箱根")
+    w.failSaves = 1
+    assertFalse(w.controller.memo("r1", "書けない"))
+    assertTrue(w.controller.rename("r1", "御殿場"))
+    assertEquals("御殿場", w.stored().name)
+    assertNull(w.stored().memo)
+  }
+
+  @Test
+  fun the_active_rides_memo_that_could_not_be_written_is_neither_shown_nor_written_later() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.failSaves = 1
+    assertFalse(w.controller.memo("r1", "書けない"))
+    assertNull(w.controller.active.value?.memo)
+    w.controller.pause()
+    assertNull(w.stored().memo)
+    assertEquals(RideStatus.PAUSED, w.stored().status)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
index 45c15b8..f2995f3 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
@@ -92,6 +92,35 @@ class RoomAskLogTest {
     db.close()
   }
 
+  // Android #28: the rider closes the band; the warning goes until another ask cannot be written.
+  @Test
+  fun the_warning_goes_when_the_rider_closes_it() = runBlocking {
+    val dao = object : AskDao {
+      override suspend fun upsert(ask: AskEntity) = throw IOException("disk full")
+      override suspend fun ask(askId: String): AskEntity? = null
+      override suspend fun rideKept(rideId: String) = true
+      override fun countForRide(rideId: String) = kotlinx.coroutines.flow.flowOf(0)
+      override fun forRide(rideId: String) = kotlinx.coroutines.flow.flowOf(emptyList<AskEntity>())
+      override suspend fun setMemo(askId: String, memo: String?, at: Long) = error("not used")
+      override suspend fun deleteRow(askId: String) = error("not used")
+      override suspend fun markDeleted(deletion: DeletionEntity) = error("not used")
+      override suspend fun unsentMemos(): List<AskMemoRow> = error("not used")
+      override suspend fun markMemoSent(askId: String, updatedAt: Long) = error("not used")
+      override suspend fun markMemoRefused(askId: String, updatedAt: Long) = error("not used")
+      override suspend fun unsentUnreached(): List<AskEntity> = error("not used")
+      override suspend fun markUnreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?) = error("not used")
+      override suspend fun markUnreachedRefused(askId: String, updatedAt: Long) = error("not used")
+    }
+    val failing = RoomAskLog(dao, kotlinx.coroutines.MainScope()) { message, _ -> errors += message }
+    failing.save(record)
+    assertTrue(failing.failed.value)
+    failing.dismiss()
+    assertFalse(failing.failed.value)
+    failing.save(record)
+    assertTrue(failing.failed.value)
+    db.close()
+  }
+
   // Android #54: the ride was deleted while its ask waited for the answer; the ask is not kept for a ride that is gone.
   @Test
   fun an_ask_whose_ride_was_deleted_meanwhile_is_not_kept() = runBlocking {
diff --git a/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
index 67be8c4..bf0675f 100644
--- a/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt
@@ -57,6 +57,13 @@ class LabelsTest {
     assertEquals(Banner.STORE_FAILED, homeBanner(hasKey = false, returnAppMissing = true, volumeLow = true, storeFailed = true))
   }
 
+  // Android #28: an ask that could not be written comes after a failing ride store, before the settings that are missing.
+  @Test
+  fun an_ask_that_could_not_be_written_comes_after_the_ride_store() {
+    assertEquals(Banner.ASK_STORE_FAILED, homeBanner(hasKey = false, returnAppMissing = true, askStoreFailed = true))
+    assertEquals(Banner.STORE_FAILED, homeBanner(hasKey = true, returnAppMissing = false, storeFailed = true, askStoreFailed = true))
+  }
+
   @Test
   fun the_media_volume_is_low_below_a_third_of_the_maximum() {
     assertTrue(mediaVolumeLow(MediaVolume(4, 15)))
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index 725f6f7..5a3b462 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -94,6 +94,20 @@ class HomeScreenTest {
     assertEquals(1, dismissed)
   }
 
+  // Android #28: the ask is lost either way, so the band closes once the rider has seen it.
+  @Test
+  fun the_band_of_an_ask_that_could_not_be_written_closes_with_its_cross() {
+    var opened: Banner? = null
+    var dismissed = 0
+    rule.setContent {
+      HomeScreen(HomeUi("rider01", Banner.ASK_STORE_FAILED, "新しい会話です"), {}, {}, { opened = it }, {}, onDismissAskFailure = { dismissed++ })
+    }
+    rule.onNodeWithText("書けなかった質問があります").performClick()
+    rule.onNodeWithTag("bandClose").performClick()
+    assertNull(opened)
+    assertEquals(1, dismissed)
+  }
+
   @Test
   fun the_media_volume_is_read_while_home_is_shown_and_a_withheld_reading_keeps_the_last() {
     // 4b #2, and the carried-over rule: null (media on the call route) must not clear a low reading.
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RideControllerTest' --tests '*LabelsTest' --tests '*ScreensTest' --tests '*RoomAskLogTest' 2>&1 | grep -E "^e: " | head -3`
Expected: コンパイルで落ちる（`Banner.ASK_STORE_FAILED`・`onDismissAskFailure`・`dismiss` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/ride/RideController.kt b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
index 3c8636f..67cb6ef 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RideController.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
@@ -192,6 +192,12 @@ class RideController(private val deps: RideDeps) {
     true
   }
 
+  /**
+   * The kept ride an edit starts from: the version still waiting to be written if this is that ride (its write failed
+   * again just now, in flush), so that one edit does not undo the other (Android #53); otherwise the stored one.
+   */
+  private suspend fun keptRide(rideId: String): Ride? = unsaved?.takeIf { it.id == rideId } ?: read("ride") { deps.store.ride(rideId) }
+
   /**
    * SC-06 (and SC-04 through end): gives any kept ride a new name. Returns false when the name is not usable, the
    * ride is not kept, or the new name could not be written now (it is written again with the next call; Android #46).
@@ -207,28 +213,36 @@ class RideController(private val deps: RideDeps) {
       activeRide.value = renamed
       return@locked saved
     }
-    val ride = read("ride") { deps.store.ride(rideId) } ?: return@locked false
+    val ride = keptRide(rideId) ?: return@locked false
     save(ride.rename(clean, now))
   }
 
   /**
    * SC-08 (and SC-02's 走行メモ): sets or, for null, removes any kept ride's memo. Returns false when the memo is too
-   * long, the ride is not kept, or the memo could not be written now. The same memo again changes nothing.
+   * long, the ride is not kept, or the memo could not be written now. The same memo again changes nothing. A memo
+   * that could not be written is not kept to be written later: SC-08 has said it was not saved, and the rider may
+   * discard it (Android #53).
    */
   suspend fun memo(rideId: String, memo: String?): Boolean = locked {
     if (!memoFits(memo)) return@locked false
     val now = deps.now()
+    val waiting = unsaved
     val active = activeRide.value
     if (active?.id == rideId) {
       if (active.memo == memo) return@locked true
       val changed = active.withMemo(memo, now)
-      val saved = save(changed)
+      if (!save(changed)) {
+        unsaved = waiting
+        return@locked false
+      }
       activeRide.value = changed
-      return@locked saved
+      return@locked true
     }
-    val ride = read("ride") { deps.store.ride(rideId) } ?: return@locked false
+    val ride = keptRide(rideId) ?: return@locked false
     if (ride.memo == memo) return@locked true
-    save(ride.withMemo(memo, now))
+    if (save(ride.withMemo(memo, now))) return@locked true
+    unsaved = waiting
+    false
   }
 
   /**
@@ -237,11 +251,14 @@ class RideController(private val deps: RideDeps) {
    */
   suspend fun delete(rideId: String): Boolean = locked {
     if (activeRide.value?.id == rideId) return@locked false
-    if (unsaved?.id == rideId) unsaved = null
     var deleted = false
     val written = write("delete") { deleted = deps.store.delete(rideId, deps.now()) }
-    if (written && deleted) deps.changed()
-    written && deleted
+    if (!written || !deleted) return@locked false
+    // Only once the ride is gone: a deletion that failed leaves its waiting change to be written (Android #53).
+    if (unsaved?.id == rideId) unsaved = null
+    storeFailing.value = unsaved != null
+    deps.changed()
+    true
   }
 
   /**
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
index e939ba0..c7417b8 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
@@ -43,9 +43,14 @@ fun AskRecord.toEntity() = AskEntity(
  */
 class RoomAskLog(private val dao: AskDao, private val scope: CoroutineScope, private val log: (String, Throwable?) -> Unit) : AskLog {
   private val failing = MutableStateFlow(false)
-  /** True while the last write of an ask failed. */
+  /** True once an ask could not be written, until the rider closes the band or the next ask is written (Android #28). */
   val failed: StateFlow<Boolean> = failing.asStateFlow()
 
+  /** SC-02's ✕ on the band: the ask is lost either way, and the rider has seen it (Android #28). */
+  fun dismiss() {
+    failing.value = false
+  }
+
   override fun keep(record: AskRecord) {
     scope.launch { save(record) }
   }
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 1f14c18..22ac80e 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -129,7 +129,8 @@ fun AppUi(graph: AppGraph) {
                     hasKey = apiKey != null,
                     returnAppMissing = current.returnEnabled && current.returnApp == null,
                     volumeLow = volumeWarning(volume, volumeDismissedAt),
-                    storeFailed = storeFailed || askStoreFailed,
+                    storeFailed = storeFailed,
+                    askStoreFailed = askStoreFailed,
                   ),
                   conversation = conversationLabel(expiresAt, System.currentTimeMillis()),
                   askHint = askHint(ride),
@@ -142,6 +143,7 @@ fun AppUi(graph: AppGraph) {
                   onNewConversation = graph.controller::resetConversation,
                   modifier = Modifier.safeDrawingPadding(),
                   onDismissVolume = { volume?.let { graph.dismissVolumeWarning(it.current) } },
+                  onDismissAskFailure = graph.askLog::dismiss,
                   ride = {
                     RideCard(
                       ride?.let { rideCard(it, now, questions) },
diff --git a/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt b/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
index 72bb128..c59c218 100644
--- a/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
@@ -96,6 +96,7 @@ fun HomeScreen(
   modifier: Modifier = Modifier,
   onDismissVolume: () -> Unit = {},
   ride: @Composable () -> Unit = {},
+  onDismissAskFailure: () -> Unit = {},
   onNote: (() -> Unit)? = null,
 ) {
   var confirming by remember { mutableStateOf(false) }
@@ -106,8 +107,12 @@ fun HomeScreen(
       OutlinedButton(onClick = onTapToTalk, Modifier.testTag("tapToTalk"), enabled = ui.askHint == null) { Text("🎤 押して話す") }
     }
     ui.banner?.let { banner ->
-      val low = banner == Banner.LOW_VOLUME
-      WarningBand(banner.text, if (banner.leads) ({ onBanner(banner) }) else null, if (low) onDismissVolume else null, Modifier.testTag("banner"))
+      val close = when (banner) {
+        Banner.LOW_VOLUME -> onDismissVolume
+        Banner.ASK_STORE_FAILED -> onDismissAskFailure
+        else -> null
+      }
+      WarningBand(banner.text, if (banner.leads) ({ onBanner(banner) }) else null, close, Modifier.testTag("banner"))
     }
     ride()
     Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
diff --git a/app/src/main/java/com/touringproject/v2/ui/Labels.kt b/app/src/main/java/com/touringproject/v2/ui/Labels.kt
index e4bb61a..02912e8 100644
--- a/app/src/main/java/com/touringproject/v2/ui/Labels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/Labels.kt
@@ -30,14 +30,23 @@ fun conversationLabel(expiresAt: Long?, now: Long): String =
 /** leads is true when tapping the band opens the setting that fixes it. */
 enum class Banner(val text: String, val leads: Boolean = true) {
   STORE_FAILED("記録を保存できません", leads = false),
+  /** An ask could not be written; it cannot be had back, so the rider closes the band once they have seen it (Android #28). */
+  ASK_STORE_FAILED("書けなかった質問があります", leads = false),
   NO_KEY("接続キーが未設定です（押して設定）"),
   NO_RETURN_APP("戻り先のアプリが未設定です（押して選ぶ）"),
   LOW_VOLUME("メディアの音量が低く、回答が聞こえないかもしれません", leads = false),
 }
 
 /** SC-02 shows at most one warning band, the most urgent first. */
-fun homeBanner(hasKey: Boolean, returnAppMissing: Boolean, volumeLow: Boolean = false, storeFailed: Boolean = false): Banner? = when {
+fun homeBanner(
+  hasKey: Boolean,
+  returnAppMissing: Boolean,
+  volumeLow: Boolean = false,
+  storeFailed: Boolean = false,
+  askStoreFailed: Boolean = false,
+): Banner? = when {
   storeFailed -> Banner.STORE_FAILED
+  askStoreFailed -> Banner.ASK_STORE_FAILED
   !hasKey -> Banner.NO_KEY
   returnAppMissing -> Banner.NO_RETURN_APP
   volumeLow -> Banner.LOW_VOLUME
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t5.log 2>&1; tail -1 /tmp/trv2-t5.log`
Expected: `BUILD SUCCESSFUL`（554件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ride/RideController.kt app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt app/src/main/java/com/touringproject/v2/ui/Labels.kt app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
git commit -m "fix: keep a ride's waiting change across a failed deletion or another edit, drop an unsaved memo, and let the lost-ask band close (#53, #28)"
```

---

### Task 6: 版と文書

- [ ] **Step 1: README と版を直す**

```bash
cd $AND && git apply <<'EOF'
diff --git a/README.md b/README.md
index 815ebb3..881ec08 100644
--- a/README.md
+++ b/README.md
@@ -16,10 +16,10 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 | `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・質問のメモと削除（`RoomAskEdits.kt`）・地点メモ（`RoomNotes.kt`）・送信の置き場（`RoomSyncStore.kt`）・記録の画面の読み出し（`RoomRecords.kt`）。スキーマは `app/schemas/` に版ごとに残す |
 | `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋）・メモの決まり（`Memos.kt`、純粋）・地点メモの型と位置の選び方（`Notes.kt`、純粋）・質問と地点メモを変える窓口（`AskEdits.kt`・`NoteEdits.kt`） |
 | `.../map/` | 地図（MapLibre と国土地理院の淡色地図）。描くデータの組み立ては `MapData.kt`（純粋）、地図の部品は `RouteMap.kt`、スタイルは `app/src/main/assets/map/gsi-pale.json` |
-| `.../sync/` | 走行・ルート・地点メモ・メモ・削除の送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`） |
+| `.../sync/` | 走行・ルート・地点メモ・質問できなかった地点・メモ・削除の送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`） |
 | `.../handsfree/` | 押下の重複・古い合図の除外・押下の行き先（試し録り中は試し録りへ、SC-19 を開いているあいだは声の入力へ） |
 | `.../voice/` | SC-19 の声の入力（`VoiceInput.kt`）。録音・文字起こしの依頼・取りに行く処理・失敗の理由 |
-| `.../net/` | 端末が通信できるか（`Connectivity.kt`。SC-19 の声の入力が使う） |
+| `.../net/` | 端末が通信できるか（`Connectivity.kt`。SC-19 の声の入力・質問の一巡・送信が使う） |
 | `.../recordings/` | 録音の置き場（直近10件と付随情報）・試し録りの司令塔・録音の確認（SC-12）の状態 |
 | `.../service/`・`.../nav/` | 前面サービス（走行の記録と一巡で1つ。種類の取りまとめは `ServiceCoordinator.kt`）・締め切りのアラームと自動終了の通知（`RideAlarms.kt`）・ナビを開く |
 | `.../settings/` | 設定（DataStore）と接続キー（Keystore で暗号化） |
@@ -31,9 +31,10 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 - 走行の状態を変えるのは `RideController` だけ。サービス・締め切りのアラーム・電源を切る知らせ・画面は、どれもこれを呼ぶ。起動したときは `load()` が先に、残っていた走行を片付ける（端末が止まっていれば終了、締め切りを過ぎていれば自動終了、それ以外は記録の再開）。最長時間を変えたときの締め切りの計算し直しも `maxRecordingChanged()` が行う（`AppGraph` が設定の変化を受けて呼ぶ）。名前の変更は `rename()`、走行のメモは `memo()`、終えた走行の削除は `delete()`（書き直し待ちの保存も捨てるので、消した走行が書き戻されない）。
 - 質問を受けるのは走行の記録中だけ。`AskController.run` の入口で `RideNow`（記録中・一時停止中・記録していない）を見て、記録中でなければ録音を始めず、理由を読み上げる。画面の「押して話す」も押せない形にする（親の spec 2 §4.7・adr/0008）。
 - Room のスキーマを変えるときは、版を上げて Migration を書き、`app/schemas/` に書き出された JSON もコミットする。破壊的な作り直しは使わない。スキーマの JSON は debug のビルドの資産にも入る（Robolectric の `MigrationTestHelper` が読むため。release には入らない）。Entity や Migration を変えた直後のテストは `--rerun` で確かめる。
-- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと。契機では未送信を調べるだけで、送るものが無ければ通信しない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。
-- 1回の送信は、削除の印（`deletions`）→ 走行とルート → 地点メモ → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため）。記録を消すときは、同じトランザクションで削除の印を書く。送れない削除の印（知らない種類）は、ログ `sync_unsendable` に出して消す（残すと、毎回の送信がそこで止まる）。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
+- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと・通信できるようになったとき（`reconnections`。プロセスが生きているあいだだけ）。契機では未送信を調べるだけで、送るものが無ければ通信しない。通信できないあいだは、契機が来ても通信を試さない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。
+- 1回の送信は、削除の印（`deletions`）→ 走行とルート → 地点メモ → 質問できなかった地点 → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため。質問できなかった地点のメモが、Backend で質問を見つけられるため）。記録を消すときは、同じトランザクションで削除の印を書く。送れない削除の印（知らない種類）は、ログ `sync_unsendable` に出して消す（残すと、毎回の送信がそこで止まる）。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
 - 地点メモ（SC-19）は、走行の記録中と一時停止中にホームの「📝 地点メモ」から開く。開いたときに、その走行の最後の点を位置に、質問と同じ選び方で方位の材料を決め（`noteDraft`）、保存するまで書かない。住所と方位は、最初に送ったときに Backend が決めて返し、端末はそれを行に書く（`notes.address`・`headingDegrees`）。地図のピンは緑で、質問とは別の通し番号。質問の一巡が終わったときに、その走行が消えていれば質問は書かない（`AskDao.keep`）。
+- 質問できなかった地点（US-C-09）: 録音を終えた時点で通信できないとき、または `POST /asks` が通信の失敗（試し直しのあとの 5xx・流量の制限を含む）に終わったとき、質問の一巡は日時・位置・方位の材料を `asks` に `status = offline` で残す（識別子は端末で作る。会話の識別子は無い）。録音は捨て、SC-12 にも残さない。会話の文脈は進めない。接続キーの誤りなど、断られた失敗では残さない。`PUT /asks/{askId}/offline` で送り、応答の住所と方位を行に書く。409（同じ識別子の質問が Backend にある）は断られたものとして扱う。
 - SC-19 の声の入力（`VoiceInput`）は、質問とは別の経路の切り替えと録音の部品を持つ（試し録りと同じ）。SC-19 を開いているあいだ（`attach`）は、インカムのボタンが質問を始めず、声の入力を始める・止める（質問が進んでいるときは質問のまま）。録音は60秒まで。`POST /transcriptions` に送り、質問と同じ間隔で `GET` し、120秒で打ち切る。聞き取れた文は入力欄の終わりに足す。通信できないときは画面のボタンを押せず、インカムのボタンは失敗の合図だけを鳴らす。SC-19 を離れると、録音も文字起こしの待ちも捨てる。前面サービスは使わない（SC-19 を見ながら使う前提）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
 - インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index 2d15875..d1810fd 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 9
-    versionName = "0.8.0"
+    versionCode = 10
+    versionName = "0.9.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
EOF
```

- [ ] **Step 2: 親の文書を Android に写す**

Run: `cd $ROOT && scripts/sync-docs.sh Android && git -C Android status --short docs-parent`
Expected: スライス4の spec・ADR と plan 1 で直した `05_technical_policies.md`・`07_units_contracts.md`・`mock/index.html` が写る

- [ ] **Step 3: コミット**

```bash
cd $AND && git add README.md app/build.gradle.kts docs-parent
git commit -m "docs: describe unreached asks and sending when the network comes back, and set the version to 0.9.0"
```

---

### Task 7: 全体の確かめ

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

Expected: `554 0`。`BUILD SUCCESSFUL`。`release permissions OK (15)`（`ACCESS_NETWORK_STATE` はライブラリの manifest からも入っていたので、件数は変わらない）。`RideForegroundServiceTest` の1件がまれに落ちる（Android #59）。落ちたら単独で回し直し、全体をもう一度回す

- [ ] **Step 2: エミュレーターのテスト**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: 6件が通る

---

### Task 8: 利用者の実機の確認

走行用のビルド（版 0.9.0）を実機に入れる。Room の版5→6 のマイグレーションが、起動して最初に走行の記録を読むときに走る。

```bash
cd $AND && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

1. 設定 → バージョンが 0.9.0。これまでの走行・質問・メモ・地点メモが、記録のタブにそのまま出る（版6のマイグレーション）。
2. 走行を始め、機内モードにしてインカムのボタンで質問する → 録音のあと、待たずに失敗の音と「通信できないため、質問できませんでした。」が流れ、ナビへ戻る。
3. もう一つ、機内モードのまま質問する。走行の詳細（SC-06）: 質問と同じ番号のピンと時系列の行が出て、文は「（通信できず、質問できなかった）」、場所は「住所は送信後」。一覧はこの走行を「記録中」と出す。
4. その行を開く（SC-07）: 「📵 通信できず、質問できなかった」と「質問の内容は残していません。何を聞きたかったかは、メモに書けます。」。場所は「住所は送ったあとに付きます」、進行方向は「停車中」。メモを書ける。
5. 設定 → 録音の確認（SC-12）に、手順 2・3 の録音が無い。
6. 走行の記録を続けたまま、画面を消して（アプリは背面のまま）機内モードを外す。1分ほど待ってから、アプリを前面に出さずに、AI が DynamoDB を読んで確かめる（読むだけ）: 手順 2・3 の `ASK#<askId>` が `status: offline` で `address`・`headingDegrees` を持ち、手順 4 のメモがある。機内モードのあいだのルートのかたまりも届いている。ユーザー名と識別子はチャットにだけ出す。
7. アプリを前面に出す → 手順 3 の行の場所が住所になり、SC-07 の進行方向が方位になる。走行を終えると、一覧で「保存済み」になる。
8. 通信できる状態で質問すると、ふつうに答えが返る（質問できなかった地点のあとも、会話の文脈が続いている）。

✗ が出たら `superpowers:systematic-debugging`。
