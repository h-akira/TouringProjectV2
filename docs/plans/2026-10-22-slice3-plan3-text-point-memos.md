# スライス3 計画3: Android（文字の地点メモ） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 走行の記録中と一時停止中に、ホームの「📝 地点メモ」から文字の地点メモを書けるようにする（SC-19）。走行の詳細（SC-06）に緑のピン（質問とは別の通し番号）と時系列で出し、直す・消す（DL-01）ことができるようにする。地点メモとその削除を Backend へ送り、Backend が決めた住所と方位を端末に持つ。あわせて Android #49・#51・#54・#55 を直す。

**Architecture:** Room の版5で作ってある表 `notes` に `NoteDao` を足す（マイグレーションは要らない）。地点メモを書く窓口 `NoteEdits`（`RoomNotes`）が、開いたときの位置（走行の最後の点と方位の材料）を下書き（`NoteDraft`）にし、保存で行を書き、消すときは削除の印を同じトランザクションで書く。送信の係（`RideSync`）は、1回の中で 削除の印 → 走行とルート → 地点メモ → 会話のメモ の順に送り、地点メモの応答の住所と方位を行に書く。地図のピンは種類（`PinKind`）を持ち、「💬 質問」「📝 地点メモ」で別々に出し隠しする。画面は SC-08 と共通の編集部品 `MemoEditor` の上に SC-19（`NoteScreen`）を作り、ホームと SC-06 につなぐ。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版5のまま）・Robolectric 4.16（SDK 35）・MapLibre 13.6.1・OkHttp・kotlinx.serialization。足す依存は無い。

**Spec:** [docs/specs/2026-10-21-slice3-design.md](../specs/2026-10-21-slice3-design.md)（§2・§4.2・§4.3・§5・§7.1・§7.3・§7.4・§7.6・§8・§9・§11・§12）。決定の記録は [adr/0009](../../adr/0009-keep-deletion-marks-in-the-cloud.md)。Backend の受け口（`PUT`・`DELETE /rides/{rideId}/notes/{noteId}`）は plan 1 でデプロイ済み（07 の UC-7、`Backend/openapi.yaml` の `NoteRequest`・`NoteSaved`）。

**範囲に入れた issue（Android）:** #49（ピンを選ぶたびにルートの GeoJSON を組み直し、一覧へ戻ると一瞬空になる）・#51（泊まりがけで翌日に出来事の無い走行は、時系列の見出しが最初の日だけになる）・#54（知らない種類の削除の印が送信を止め続け、走行を消したあとに届いた質問が端末に残る）・#55（SC-08 の保存のあいだに閉じると二度閉じうる・カーソルが先頭に出る）。#53 などほかの issue は入れない（利用者と決めた、2026-10-22）。

**前提:** Android の `main`（`f505225`。版 0.6.0）の上に作る。Backend は plan 1 の受け口がデプロイ済み（`stack-trv2-dev-backend`）。

**計画を書くときに決めたこと（spec からの具体化）:**
- SC-19 の住所の文言（spec §12。利用者と決めた、2026-10-22）: 新規で開いたときと、まだ送れていないときは「📍 住所は送ったあとに付きます」。位置を記録できなかった（走行にまだ点が無かった）ときは「📍 位置を記録できませんでした」。送っても Backend が住所を確定できなかったときは「📍 住所は分かりませんでした」。時系列とピンのカードでは、それぞれ「住所は送信後」「位置の記録なし」「場所不明」。モックの SC-19 に、この plan のコミットで反映した。
- 声の入力（「🎤 声で入力」と「声は文字にするためだけに…」の注記）は、plan 3 では出さない（利用者と決めた）。plan 4 で足す。インカムのボタンは、SC-19 のあいだも今までどおり質問を始める（SC-19 での扱いは plan 4）。
- ホームの「📝 地点メモ」: spec §7.1 は「進行方向のカードの右」だが、今のホームには進行方向のカードが無い（スライス1の最小限）。そこで「インカムのボタンで話せます」の行の右に、緑のボタンで置く。記録中と一時停止中だけ出す。進行方向のカードを作るときに、その右へ移す。
- 位置（spec §4.3）: ボタンを押したときに、その走行の最後の30点（ルートは5秒ごとなので、方位の材料の1分を覆う）を読み、最新の点を位置に、ほかの点から質問と同じ `pickHeadingSample` で方位の材料を選ぶ（`noteDraft`）。点の読み出しに失敗したら、位置なしで開く。押した時刻を `at` にする。下書き（`NoteDraft`）は画面の鍵（`NewNoteKey`）に持たせ、画面を作り直しても同じ地点メモのままにする。DB には保存するまで書かない。
- 保存: 走行が端末に残っていれば保存する（SC-19 を開いたあとに走行が自動で終わっても、開いた走行に入れる）。走行が消えていれば false。空白だけは保存できない（保存のボタンを押せない）。2000字はコードポイントで数える。本文を直した時刻 `updatedAt` は、前の値より必ず後にする（`memoTime`）。同じ本文をもう一度保存しても書かない。
- 送信（spec §5.1・§5.2）: 地点メモは走行の後、会話のメモの前に、変わった版を `PUT /rides/{rideId}/notes/{noteId}` で全体を置く。位置が無ければ `location` は null、方位の材料はそろっているときだけ送る。応答の住所と方位を行に書く（応答が null なら今の値を残す。410 のときも残す）。400 は断られた版として送り直さない。地点メモの削除は `DELETE /rides/{rideId}/notes/{noteId}`。送れない削除の印（知らない種類と、`rideId` の無い地点メモ）は、ログ `sync_unsendable` に出して消す（#54 の前半）。
- #54 の後半: 質問の一巡の終わりに質問を書くとき、その走行の行が無ければ書かない（`AskDao.keep`）。走行の最初の保存に失敗して行がまだ無いあいだの質問も書かれなくなるが、そのときは端末の書き込みそのものが失敗していることがほとんどなので、消えた走行を指す見えない行を残さないほうを選ぶ（`AskEntity.rideId` のコメントを直す）。
- 保存の状態（spec §5.3）: 一覧の「未送信あり」に、その走行の地点メモの未送信を数える（`RideRow.notesLeft`。会話のメモと同じく、断られた版も「未送信あり」）。
- 地図: `MapPin` の `askId` を `id` にし、種類 `kind`（`ASK`・`NOTE`）を足す。地点メモのピンは緑（モックの `--memo`、`#13804A`）で、絵の名前は `note-<番号>`・`note-sel-<番号>`。選んだピンは質問と同じ青。GeoJSON の項目は `askId` から `id` に変わる（押したピンの名前を読む）。切り替えの状態は設定 `showNotePins`（既定は出す。今の設定の JSON に無ければ出す）。選んだピンの種類を隠すと、カードも消える。
- #49: `RouteMap` は、ルート・一時停止・端の GeoJSON を `data` が変わったときだけ組み、ピンの GeoJSON は `selected` でも組み直す。記録の一覧は `AppGraph.recordsList`（`stateIn(scope, WhileSubscribed(5_000), null)`）で共有し、詳細から戻ったときに前の値から出す。
- #51: 区間の始まり（走行の開始と再開）を時系列の出来事として扱う。行は出さず、日をまたぐ走行で、その日の見出しだけを出す。同じ時刻の出来事は 区間の始まり → 質問 → 地点メモ → 一時停止 の順。
- SC-06: 要約に「📝 地点メモ n件」（モック。無ければ出さない）。地点メモのピンのカードは「n · 時刻 · 場所 · 📝 地点メモ」と本文、緑の「開く ›」で SC-19。時系列の地点メモの行は、緑の番号・「時刻 · 場所 · 📝 地点メモ」・本文2行まで。時系列が空のときの文言を「この走行の記録中にした質問と地点メモはありません。」にする。
- SC-19: SC-08 と共通の `MemoEditor`（✕・題・保存・上部・入力欄と字数・下部）。上部のカードに いつ・どこで・どの走行（新規は「走行「…」に入ります」、記録から開いたときは「走行「…」で書いたメモ」）。保存のボタンは緑。記録から開いたときだけ「この地点メモを削除」（DL-01 の `DeleteKind.NOTE`。文言はモックの表のとおり）。消せたら開いた元（SC-06）へ戻る。消したあとも最後に読んだ地点メモを出し続け、消す処理が画面とともに取り消されないようにする。SC-19 のあいだタブの帯を出さない（モック）。「📝 地点メモ」を素早く2回押しても、SC-19 は1つだけ開く。
- #55: 保存のあいだは、保存・✕・Back・「破棄する」を受けない（`if (saving) return@Button`）。入力欄は `TextFieldValue` にし、カーソルを末尾に置いて始める。`AskRecord.toEntity()` に、メモを写さない理由のコメントを足す。SC-08 と SC-19 の両方に効く。
- `AppUi` の通しのテストは書けない（記録の画面は本物の地図を描き、走行を始めるとサービスが動く）。SC-19 の route は Robolectric で DB と通して確かめ（`NoteRoutesTest`）、ホーム → SC-19、SC-06 → SC-19 → SC-06 のつなぎは Task 10 の実機で確かめる。
- 版を 0.7.0（`versionCode` 8）に上げる。

この計画のコードは、使い捨てのフォルダで、次を確かめてから書いた。

- タスクの順に一つずつコミットし、各タスクのコミットで `clean` から JVM のテストが通る（443件 → 493件）。各タスクのテストだけを1つ前のコミットに当てると、まだ無い名前を使うので、コンパイルで落ちる。
- 最後に、JVM のテスト493件・エミュレーターのテスト6件・`assembleRelease`・`scripts/check-release-permissions.sh`（15件）が通る。
- plan の差分を新しい写しへ機械的に当てると、最終形と一致する。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice3-plan3` を切る（Task 0）。親は `slice3-plan3`。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- 作りの決まり: 状態機械と司令塔は Android に依存させない。部品は `AppGraph` で手で組む。走行を変えるのは `RideController` だけ（地点メモは走行を変えない。`notes` の表だけを書く）。
- 地点メモは走行の記録中と一時停止中だけ書ける（spec §2。ホームの入口を、その間だけ出す）。記録を消すときは、同じトランザクションで削除の印を書く（spec §4.2）。
- 地点メモは1〜2000字（US-D-08.003。空白だけは無し）。文字はコードポイントで数える。
- ホームは全体がスクロールしない（spec §7）。
- Room のスキーマは変えない（版5のまま。`app/schemas/` も変わらない）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --tests '*クラス名'`。テストを確かめるときは `--rerun` を付ける。Kotlin の差分コンパイルは interface の変更を見逃すことがあるので、Task 9 は `./gradlew clean` から回す。
- `RoomAskLogTest` の作り物の `AskDao` は、DAO にメソッドを足すたびに実装を足す（Task 1 の差分に入っている）。`RideSyncTest` の作り物の `RideApi`・`SyncStore` も同じ（Task 2・Task 3）。
- Robolectric の決まり（SDK 35・`@Config(qualifiers)` で画面を大きくしない・画面の外の行は `performScrollTo`／`performScrollToNode` で出す・地図の部品は動かさない）。入力欄にフォーカスがあるあいだの最初の Back は入力欄が受けるので、SC-19 の破棄の確認は ✕ で確かめる。閉じた DB への最初の素の問い合わせは取り消しの例外になるので、読み出しの失敗は `RideDao` を委譲で包んで作る（Task 1 の `a_draft_whose_points_cannot_be_read_has_no_place`）。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。使い終わったら止める。
- AWS は `AWS_PROFILE=touring`・リージョン `ap-northeast-1`（Task 10 で DynamoDB を読むだけ）。

## Review Focus

- SC-19 を開いたまま走行が自動で終わり（または SC-04 で終えて）、そのあと保存する → 開いた走行に入る。Task 1 の `a_memo_opened_before_its_ride_ended_is_still_kept_in_it`。
- 走行を始めた直後、まだ点が無いうちに地点メモを書く → 位置なしで保存され、時系列に「位置の記録なし」で出てピンは無く、送るときは `location` が null。Task 4 の `point_memos_are_numbered_apart_from_the_asks_and_mixed_into_the_timeline`、Task 3 の `a_point_memo_goes_with_its_place_and_sample_in_utc`、Task 2 の `a_memo_without_a_place_sends_it_as_null_and_gets_no_address`。
- 送って住所が付いた地点メモの本文を直して送る → 住所は消えない。Task 3 の `a_point_memo_is_unsent_until_its_version_is_taken_and_keeps_its_address`。
- 端末の時計が戻った状態で本文を直す → 変更の時刻は前より後になり、Backend が新しい版として受ける。Task 1 の `each_change_of_the_text_is_later_than_the_one_before_and_the_same_text_changes_nothing`。
- 保存を押してすぐ ✕ か Back を押す → 画面は一度だけ閉じ、下の画面まで閉じない。Task 6 の `closing_while_the_save_runs_does_nothing`。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `store/RideDatabase.kt` | `NoteDao`（書く・直す・消す（1）、送信の読み書き（3））・`AskDao.keep`（#54）・`RideDao.lastPoints`・一覧の `notesLeft`（3） | 1・3 |
| `records/Notes.kt`（新規）・`records/NoteEdits.kt`（新規）・`store/RoomNotes.kt`（新規） | 地点メモの型と位置の選び方（純粋）・地点メモを変える窓口・Room への書き込み | 1・7 |
| `store/RoomAskLog.kt`・`store/RoomRecords.kt` | 消えた走行の質問を書かない（#54）・地点メモの読み出しと保存の状態・`toEntity()` のコメント（#55） | 1・3・6 |
| `api/ApiClient.kt` | `NoteBody`・`NoteSaved`・`putNote`・`deleteNote` | 2 |
| `sync/RideSync.kt`・`sync/SyncPlan.kt`・`store/RoomSyncStore.kt`・`records/Records.kt` | 送信の順番・地点メモの送信と削除・送れない印（#54）・`UnsentNote.toBody()` | 3 |
| `map/MapData.kt`・`map/RouteMap.kt` | ピンの種類と `id`・緑のピン（4）・`showing`・ルートとピンを分けて組む（#49）（5） | 4・5 |
| `ui/RecordLabels.kt`・`ui/RecordsScreens.kt`・`ui/RecordsRoutes.kt` | 番号・時系列・#51・カード・SC-19 の上部の文言（4）・SC-06 の切り替えとカード（5）・SC-19 の route（7） | 4・5・7 |
| `settings/Settings.kt`・`AppGraph.kt`・`ui/AppUi.kt` | `showNotePins`・一覧の共有（#49）（5）・`notes`・SC-19 へのつなぎ（7） | 1・3・5・7 |
| `ui/MemoScreen.kt`・`ui/NoteScreen.kt`（新規）・`ui/DeleteDialog.kt` | 共通の編集部品・#55・SC-19・`DeleteKind.NOTE` | 6 |
| `ui/HomeScreen.kt` | 「📝 地点メモ」 | 7 |
| `app/build.gradle.kts`・`README.md`・`docs-parent/` | 版 0.7.0・決まり・親の文書の写し | 8 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、今のテストを回す**

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice3-plan3
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t0.log 2>&1; tail -1 /tmp/trv2-t0.log
```

Expected: `BUILD SUCCESSFUL`（443件）。親はこの plan を書いたブランチ `slice3-plan3` のまま。

---
### Task 1: 地点メモの置き場と、消えた走行の質問を書かない（#54 の後半）

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `AppGraph.kt`・`records/NoteEdits.kt`（新規）・`records/Notes.kt`（新規）・`store/RideDatabase.kt`・`store/RoomAskLog.kt`・`store/RoomNotes.kt`（新規）・`store/RoomRecords.kt`
- Test: `records/NotesTest.kt`（新規）・`store/RoomAskLogTest.kt`・`store/RoomNotesTest.kt`（新規）・`store/RoomRecordsTest.kt`

**Interfaces:**
- Consumes: 版5の `NoteEntity`・`DeletionEntity`・`RideDao.deleteEnded`（`notes` も消す）・`memoTime`・`memoFits`・`memoText`（`records/Memos.kt`）・`pickHeadingSample`・`Fix`（`location/Heading.kt`）
- Produces:
  - `NoteRecord(id, rideId, at, latitude: Double?, longitude: Double?, text, address: String?, sent: Boolean)`・`NoteDraft(id, rideId, at, latitude?, longitude?, sampleLatitude?, sampleLongitude?, sampleAt: Long?)`・`noteText(input): String?`・`NOTE_RECENT_POINTS = 30`・`noteDraft(id, rideId, at, recent: List<RoutePoint>): NoteDraft`（`records/Notes.kt`）
  - `interface NoteEdits { suspend fun draft(rideId): NoteDraft; suspend fun create(draft, text): Boolean; suspend fun text(noteId, text): Boolean; suspend fun delete(noteId): Boolean }`（`records/NoteEdits.kt`）
  - `RoomNotes(notes: NoteDao, rides: RideDao, now, newId, changed, log)`（`store/RoomNotes.kt`）
  - `NoteDao`（`insert`・`note`・`forRide(rideId): Flow<List<NoteEntity>>`・`rideKept`・`create`・`setText`・`writeText`・`deleteRow`・`markDeleted`・`delete`）・`RideDatabase.notes()`・`RideDao.lastPoints(rideId, count)`（新しい順）
  - `AskDao.rideKept(rideId)`・`AskDao.keep(ask): Boolean`。`RoomAskLog.save` は `keep` で書く
  - `RoomRecords(rides, asks, notes: NoteDao)`・`RoomRecords.notes(rideId): Flow<List<NoteRecord>>`・`NoteEntity.toRecord()`

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/records/NotesTest.kt b/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
new file mode 100644
index 0000000..1e7956f
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/records/NotesTest.kt
@@ -0,0 +1,40 @@
+package com.touringproject.v2.records
+
+import com.touringproject.v2.ride.RoutePoint
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertNull
+import org.junit.Test
+
+class NotesTest {
+  private fun p(t: Long, lat: Double, lon: Double, accuracy: Double? = 5.0) = RoutePoint(0, t, lat, lon, accuracy)
+
+  // Slice 3 spec §4.3: the newest point is the place, and an older one far enough back is the heading's sample.
+  @Test
+  fun a_memo_is_at_the_newest_point_with_an_older_one_for_the_heading() {
+    val recent = listOf(p(1_000, 35.000, 139.000), p(30_000, 35.001, 139.000), p(55_000, 35.002, 139.000), p(60_000, 35.0201, 139.000))
+    val draft = noteDraft("n1", "r1", 70_000, recent)
+    assertEquals(NoteDraft("n1", "r1", 70_000, 35.0201, 139.000, 35.002, 139.000, 55_000), draft)
+  }
+
+  @Test
+  fun without_a_point_the_memo_has_no_place() {
+    assertEquals(NoteDraft("n1", "r1", 70_000, null, null, null, null, null), noteDraft("n1", "r1", 70_000, emptyList()))
+  }
+
+  // The same rules as an ask's sample: none closer than 15 m, older than a minute, or from a poor fix.
+  @Test
+  fun the_heading_sample_is_left_out_when_no_older_point_will_do() {
+    val near = listOf(p(50_000, 35.0000, 139.0), p(60_000, 35.0001, 139.0))
+    assertNull(noteDraft("n1", "r1", 70_000, near).sampleAt)
+    val old = listOf(p(1_000, 35.0, 139.0), p(90_000, 35.01, 139.0))
+    assertNull(noteDraft("n1", "r1", 95_000, old).sampleAt)
+    val poor = listOf(p(50_000, 35.0, 139.0, accuracy = 80.0), p(60_000, 35.01, 139.0))
+    assertNull(noteDraft("n1", "r1", 70_000, poor).sampleAt)
+  }
+
+  @Test
+  fun a_memo_keeps_its_text_trimmed_and_a_blank_one_is_none() {
+    assertEquals("展望スペース", noteText("  展望スペース \n"))
+    assertNull(noteText(" \n "))
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
index 7953ae7..cb9722a 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
@@ -7,10 +7,15 @@ import androidx.test.ext.junit.runners.AndroidJUnit4
 import com.touringproject.v2.ask.ASK_INPUT_VOICE
 import com.touringproject.v2.ask.AskOutcome
 import com.touringproject.v2.ask.AskRecord
+import com.touringproject.v2.ride.EndReason
+import com.touringproject.v2.ride.HOUR_MS
+import com.touringproject.v2.ride.end
+import com.touringproject.v2.ride.newRide
 import kotlinx.coroutines.flow.first
 import kotlinx.coroutines.runBlocking
 import org.junit.Assert.assertEquals
 import org.junit.Assert.assertFalse
+import org.junit.Assert.assertNull
 import org.junit.Assert.assertTrue
 import org.junit.Test
 import org.junit.runner.RunWith
@@ -27,8 +32,11 @@ class RoomAskLogTest {
     "a1", 1_000, 9_000, "Q", "A", 35.0, 139.0, "御殿場市", 90.0, ASK_INPUT_VOICE, "c1", true, AskOutcome.ANSWERED, null, "r1",
   )
 
+  private fun keepRide(id: String = "r1") = runBlocking { RoomRideStore(db.rides()).save(newRide(id, "箱根", 500, 7, 24 * HOUR_MS)) }
+
   @Test
   fun a_kept_ask_is_stored_with_its_ride_and_outcome() = runBlocking {
+    keepRide()
     log.save(record)
     val stored = db.asks().ask("a1")!!
     assertEquals("answered", stored.status)
@@ -40,6 +48,8 @@ class RoomAskLogTest {
 
   @Test
   fun the_count_of_a_ride_follows_the_asks_kept_for_it() = runBlocking {
+    keepRide()
+    keepRide("r2")
     val count = db.asks().countForRide("r1")
     assertEquals(0, count.first())
     log.save(record)
@@ -56,6 +66,7 @@ class RoomAskLogTest {
     val dao = object : AskDao {
       override suspend fun upsert(ask: AskEntity) = if (full) throw IOException("disk full") else Unit
       override suspend fun ask(askId: String): AskEntity? = null
+      override suspend fun rideKept(rideId: String) = true
       override fun countForRide(rideId: String) = kotlinx.coroutines.flow.flowOf(0)
       override fun forRide(rideId: String) = kotlinx.coroutines.flow.flowOf(emptyList<AskEntity>())
       override suspend fun setMemo(askId: String, memo: String?, at: Long) = error("not used")
@@ -74,4 +85,16 @@ class RoomAskLogTest {
     assertFalse(failing.failed.value)
     db.close()
   }
+
+  // Android #54: the ride was deleted while its ask waited for the answer; the ask is not kept for a ride that is gone.
+  @Test
+  fun an_ask_whose_ride_was_deleted_meanwhile_is_not_kept() = runBlocking {
+    val rides = RoomRideStore(db.rides())
+    rides.save(newRide("r1", "箱根", 500, 7, 24 * HOUR_MS).end(800, EndReason.MANUAL, 800))
+    rides.delete("r1", 900)
+    log.save(record)
+    assertNull(db.asks().ask("a1"))
+    assertFalse(log.failed.value)
+    db.close()
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
new file mode 100644
index 0000000..55688d3
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt
@@ -0,0 +1,147 @@
+package com.touringproject.v2.store
+
+import android.app.Application
+import androidx.room.Room
+import androidx.test.core.app.ApplicationProvider
+import androidx.test.ext.junit.runners.AndroidJUnit4
+import com.touringproject.v2.records.NoteDraft
+import com.touringproject.v2.records.NoteRecord
+import com.touringproject.v2.ride.EndReason
+import com.touringproject.v2.ride.HOUR_MS
+import com.touringproject.v2.ride.RoutePoint
+import com.touringproject.v2.ride.end
+import com.touringproject.v2.ride.newRide
+import kotlinx.coroutines.flow.first
+import kotlinx.coroutines.runBlocking
+import org.junit.After
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertFalse
+import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
+import org.junit.Test
+import org.junit.runner.RunWith
+import java.io.IOException
+
+@RunWith(AndroidJUnit4::class)
+class RoomNotesTest {
+  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
+    .allowMainThreadQueries()
+    .build()
+  private val rides = RoomRideStore(db.rides())
+  private var now = 5_000L
+  private var changes = 0
+  private val errors = mutableListOf<String>()
+  private val notes = RoomNotes(db.notes(), db.rides(), { now }, { "n1" }, { changes += 1 }) { message, _ -> errors += message }
+  private val records = RoomRecords(db.rides(), db.asks(), db.notes())
+  private val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)
+
+  @After
+  fun close() = db.close()
+
+  private fun deletions(): List<DeletionEntity> = db.query("SELECT * FROM deletions", null).use { c ->
+    buildList { while (c.moveToNext()) add(DeletionEntity(c.getString(0), c.getString(1), c.getString(2), c.getLong(3))) }
+  }
+
+  private val draft = NoteDraft("n1", "r1", 4_000, 35.02, 139.0, 35.0, 139.0, 3_000)
+
+  // Slice 3 spec §4.3: the memo opened now is at the ride's newest point; nothing is written until it is saved.
+  @Test
+  fun a_draft_is_at_the_rides_newest_point_and_writes_nothing() = runBlocking {
+    rides.save(ride)
+    rides.addPoint("r1", RoutePoint(0, 2_000, 35.0, 139.0, 5.0), 0.0, 2_000)
+    rides.addPoint("r1", RoutePoint(0, 3_000, 35.01, 139.0, 5.0), 0.0, 3_000)
+    assertEquals(NoteDraft("n1", "r1", 5_000, 35.01, 139.0, 35.0, 139.0, 2_000), notes.draft("r1"))
+    assertEquals(emptyList<NoteRecord>(), records.notes("r1").first())
+  }
+
+  @Test
+  fun a_saved_memo_keeps_its_place_and_time_and_is_something_to_send() = runBlocking {
+    rides.save(ride)
+    assertTrue(notes.create(draft, "展望スペース"))
+    val kept = db.notes().note("n1")!!
+    assertEquals(listOf(4_000L, 5_000L), listOf(kept.at, kept.updatedAt))
+    assertEquals(listOf(35.02, 139.0, 35.0, 139.0), listOf(kept.latitude, kept.longitude, kept.sampleLatitude, kept.sampleLongitude))
+    assertEquals(3_000L, kept.sampleAt)
+    assertNull(kept.sentUpdatedAt)
+    assertEquals(1, changes)
+    assertEquals(listOf(NoteRecord("n1", "r1", 4_000, 35.02, 139.0, "展望スペース", null, sent = false)), records.notes("r1").first())
+  }
+
+  // SC-19: an empty memo is not saved, nor one for a ride not kept (deleted meanwhile).
+  @Test
+  fun an_empty_or_too_long_memo_or_one_for_a_ride_not_kept_is_refused() = runBlocking {
+    assertFalse(notes.create(draft, "どこ"))
+    rides.save(ride)
+    assertFalse(notes.create(draft, " "))
+    assertFalse(notes.create(draft, "あ".repeat(2001)))
+    assertNull(db.notes().note("n1"))
+    assertEquals(0, changes)
+  }
+
+  // The ride ended by its longest time while SC-19 was open: the memo still goes into the ride it was opened in.
+  @Test
+  fun a_memo_opened_before_its_ride_ended_is_still_kept_in_it() = runBlocking {
+    rides.save(ride.end(4_500, EndReason.AUTO, 4_500))
+    assertTrue(notes.create(draft, "終わったあとに保存"))
+    assertEquals("r1", db.notes().note("n1")?.rideId)
+  }
+
+  // The Backend keeps only a newer version, so a change made with the clock set back still comes after.
+  @Test
+  fun each_change_of_the_text_is_later_than_the_one_before_and_the_same_text_changes_nothing() = runBlocking {
+    rides.save(ride)
+    notes.create(draft, "一つ目")
+    now = 3_000
+    assertTrue(notes.text("n1", "二つ目"))
+    assertEquals("二つ目" to 5_001L, db.notes().note("n1")!!.let { it.text to it.updatedAt })
+    assertEquals(2, changes)
+    now = 9_000
+    assertTrue(notes.text("n1", "二つ目"))
+    assertEquals(5_001L, db.notes().note("n1")!!.updatedAt)
+    assertFalse(notes.text("n9", "どこ"))
+    assertFalse(notes.text("n1", " "))
+  }
+
+  @Test
+  fun deleting_a_memo_marks_it_with_its_ride() = runBlocking {
+    rides.save(ride)
+    notes.create(draft, "消す")
+    assertTrue(notes.delete("n1"))
+    assertNull(db.notes().note("n1"))
+    assertEquals(listOf(DeletionEntity("note", "n1", "r1", 5_000)), deletions())
+    assertFalse(notes.delete("n1"))
+  }
+
+  // A deleted ride takes its point memos with it (slice 3 spec §4.2).
+  @Test
+  fun deleting_the_ride_removes_its_memos() = runBlocking {
+    rides.save(ride.end(4_500, EndReason.MANUAL, 4_500))
+    notes.create(draft, "走行ごと消える")
+    rides.delete("r1", 6_000)
+    assertNull(db.notes().note("n1"))
+    assertEquals(listOf("ride"), deletions().map { it.kind })
+  }
+
+  // Slice 3 spec §8: a write that fails is reported, so SC-19 keeps what was typed.
+  @Test
+  fun a_write_that_fails_is_logged_and_reported() = runBlocking {
+    rides.save(ride)
+    db.close()
+    assertFalse(notes.create(draft, "書けない"))
+    assertFalse(notes.text("n1", "書けない"))
+    assertFalse(notes.delete("n1"))
+    assertEquals(3, errors.size)
+    assertEquals(0, changes)
+  }
+
+  // A draft whose points cannot be read is opened without a place rather than not at all.
+  @Test
+  fun a_draft_whose_points_cannot_be_read_has_no_place() = runBlocking {
+    val failing = object : RideDao by db.rides() {
+      override suspend fun lastPoints(rideId: String, count: Int): List<RoutePointEntity> = throw IOException("disk")
+    }
+    val notes = RoomNotes(db.notes(), failing, { now }, { "n1" }, { changes += 1 }) { message, _ -> errors += message }
+    assertEquals(NoteDraft("n1", "r1", 5_000, null, null, null, null, null), notes.draft("r1"))
+    assertEquals(1, errors.size)
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
index 06dd572..30ebe42 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
@@ -32,7 +32,7 @@ class RoomRecordsTest {
   private val rides = RoomRideStore(db.rides())
   private val sync = RoomSyncStore(db.rides(), db.asks())
   private val log = RoomAskLog(db.asks(), MainScope()) { _, _ -> }
-  private val records = RoomRecords(db.rides(), db.asks())
+  private val records = RoomRecords(db.rides(), db.asks(), db.notes())
 
   @After
   fun close() = db.close()
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*NotesTest' --tests '*RoomNotesTest' --tests '*RoomAskLogTest' --tests '*RoomRecordsTest' > /tmp/trv2-t1.log 2>&1; grep -c '^e: ' /tmp/trv2-t1.log
```

Expected: `BUILD FAILED`。まだ無い `NoteDraft`・`RoomNotes`・`db.notes()`・`rideKept` を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index ed97525..6868c4f 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -92,7 +92,7 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   val rideStore = RoomRideStore(database.rides())
   val askLog = RoomAskLog(database.asks(), scope) { message, e -> Log.w("trv2.ask", message, e) }
   /** What the Records tab reads (SC-05, SC-06, SC-07). */
-  val records = RoomRecords(database.rides(), database.asks())
+  val records = RoomRecords(database.rides(), database.asks(), database.notes())
   private val notices = RideNotices(context)
 
   /** Sends rides and routes; a pass runs on each trigger (slice 2 spec §5.3). */
diff --git a/app/src/main/java/com/touringproject/v2/records/NoteEdits.kt b/app/src/main/java/com/touringproject/v2/records/NoteEdits.kt
new file mode 100644
index 0000000..3a0f572
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/records/NoteEdits.kt
@@ -0,0 +1,13 @@
+package com.touringproject.v2.records
+
+/** What SC-19 does with point memos (US-D-08). Each write returns false when nothing was written. */
+interface NoteEdits {
+  /** A memo opened now for the ride: where the ride is and when (slice 3 spec §4.3). Nothing is written yet. */
+  suspend fun draft(rideId: String): NoteDraft
+  /** Keeps the drafted memo with its first text, the cleaned text (noteText). */
+  suspend fun create(draft: NoteDraft, text: String): Boolean
+  /** Changes a kept memo's text. */
+  suspend fun text(noteId: String, text: String): Boolean
+  /** Removes the memo and marks it to be deleted on the Backend too (slice 3 spec §4.2). */
+  suspend fun delete(noteId: String): Boolean
+}
diff --git a/app/src/main/java/com/touringproject/v2/records/Notes.kt b/app/src/main/java/com/touringproject/v2/records/Notes.kt
new file mode 100644
index 0000000..f9303ab
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/records/Notes.kt
@@ -0,0 +1,57 @@
+package com.touringproject.v2.records
+
+import com.touringproject.v2.location.Fix
+import com.touringproject.v2.location.pickHeadingSample
+import com.touringproject.v2.ride.RoutePoint
+import java.time.Instant
+
+// Point memos (US-D-08, SC-19). One is written while a ride records or is paused, at the place the ride has reached,
+// and belongs to that ride. Its text follows the memos' rules (Memos.kt), but it cannot be empty.
+
+/**
+ * A kept point memo as the records screens and SC-19 read it. The place is null when the ride had no point yet;
+ * address is what the Backend answered (null until then, or when it could not tell); sent says the Backend has taken
+ * a version of it.
+ */
+data class NoteRecord(
+  val id: String,
+  val rideId: String,
+  val at: Long,
+  val latitude: Double?,
+  val longitude: Double?,
+  val text: String,
+  val address: String?,
+  val sent: Boolean,
+)
+
+/**
+ * A point memo opened from Home and not yet saved: when it was opened and where the ride was then, with the older
+ * point the Backend works the heading out from (slice 3 spec §4.3). Nothing is written until it is saved.
+ */
+data class NoteDraft(
+  val id: String,
+  val rideId: String,
+  val at: Long,
+  val latitude: Double?,
+  val longitude: Double?,
+  val sampleLatitude: Double?,
+  val sampleLongitude: Double?,
+  val sampleAt: Long?,
+)
+
+/** The text a point memo keeps: trimmed, and none when it is blank (SC-19 does not save an empty one). */
+fun noteText(input: String): String? = memoText(input)
+
+/** How many of the ride's last points are read for a memo's place: 30 at the route's 5 s cover the sample's minute. */
+const val NOTE_RECENT_POINTS = 30
+
+/**
+ * A memo opened at at, given the ride's last points (oldest first): the newest point is its place, and its heading
+ * sample is picked from the others as an ask's is (07 UC-5). Without a point it has no place.
+ */
+fun noteDraft(id: String, rideId: String, at: Long, recent: List<RoutePoint>): NoteDraft {
+  val newest = recent.maxByOrNull { it.t } ?: return NoteDraft(id, rideId, at, null, null, null, null, null)
+  val fixes = recent.map { Fix(it.lat, it.lon, it.t, it.accuracy) }
+  val sample = pickHeadingSample(fixes, Fix(newest.lat, newest.lon, newest.t, newest.accuracy))
+  return NoteDraft(id, rideId, at, newest.lat, newest.lon, sample?.latitude, sample?.longitude, sample?.let { Instant.parse(it.at).toEpochMilli() })
+}
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index dc21d36..613d2fe 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -102,8 +102,8 @@ data class AskEntity(
   val failure: String?,
   /**
    * The ride that was recording when the ask started. Asks need a recording ride since version 4 (slice 2 spec §4.7), so
-   * it is set on every ask; the column stays nullable for the API's sake. Not a foreign key: a ride's row may be
-   * missing for a while after a failed save.
+   * it is set on every ask; the column stays nullable for the API's sake. Not a foreign key, but an ask is kept only
+   * while its ride is ([AskDao.keep]).
    */
   val rideId: String?,
   /** The conversation's memo (US-D-04.001); null when there is none. */
@@ -152,6 +152,20 @@ interface AskDao {
   @Upsert
   suspend fun upsert(ask: AskEntity)
 
+  @Query("SELECT EXISTS (SELECT 1 FROM rides WHERE id = :rideId)")
+  suspend fun rideKept(rideId: String): Boolean
+
+  /**
+   * Writes an ask at the end of its loop, unless its ride is no longer kept: it was deleted while the ask waited for the
+   * answer (Android #54). False when it was not written.
+   */
+  @Transaction
+  suspend fun keep(ask: AskEntity): Boolean {
+    if (ask.rideId != null && !rideKept(ask.rideId)) return false
+    upsert(ask)
+    return true
+  }
+
   @Query("SELECT * FROM asks WHERE askId = :askId")
   suspend fun ask(askId: String): AskEntity?
 
@@ -209,6 +223,57 @@ interface AskDao {
 
 data class AskMemoRow(val askId: String, val memo: String?, val memoUpdatedAt: Long)
 
+@Dao
+interface NoteDao {
+  @Insert
+  suspend fun insert(note: NoteEntity)
+
+  @Query("SELECT * FROM notes WHERE id = :id")
+  suspend fun note(id: String): NoteEntity?
+
+  /** The ride's point memos in the order they were opened (SC-06). */
+  @Query("SELECT * FROM notes WHERE rideId = :rideId ORDER BY at")
+  fun forRide(rideId: String): Flow<List<NoteEntity>>
+
+  @Query("SELECT EXISTS (SELECT 1 FROM rides WHERE id = :rideId)")
+  suspend fun rideKept(rideId: String): Boolean
+
+  /** SC-19 from Home. False when the memo's ride is no longer kept. */
+  @Transaction
+  suspend fun create(note: NoteEntity): Boolean {
+    if (!rideKept(note.rideId)) return false
+    insert(note)
+    return true
+  }
+
+  @Query("UPDATE notes SET text = :text, updatedAt = :at WHERE id = :id")
+  suspend fun setText(id: String, text: String, at: Long)
+
+  /** SC-19 from the records. False when the memo is not kept; the same text again changes nothing. */
+  @Transaction
+  suspend fun writeText(id: String, text: String, now: Long): Boolean {
+    val note = note(id) ?: return false
+    if (note.text == text) return true
+    setText(id, text, memoTime(now, note.updatedAt))
+    return true
+  }
+
+  @Query("DELETE FROM notes WHERE id = :id")
+  suspend fun deleteRow(id: String)
+
+  @Insert(onConflict = OnConflictStrategy.REPLACE)
+  suspend fun markDeleted(deletion: DeletionEntity)
+
+  /** DL-01: removes the memo and marks it for the Backend, together (slice 3 spec §4.2). False when it is not kept. */
+  @Transaction
+  suspend fun delete(id: String, at: Long): Boolean {
+    val note = note(id) ?: return false
+    deleteRow(id)
+    markDeleted(DeletionEntity("note", id, note.rideId, at))
+    return true
+  }
+}
+
 /** What one ride has left to send, read together (Android #23). */
 data class UnsentRow(val ride: RideEntity, val segments: List<SegmentEntity>, val sentPoints: Int, val totalPoints: Int)
 
@@ -273,6 +338,10 @@ interface RideDao {
   @Query("SELECT * FROM route_points WHERE rideId = :rideId ORDER BY id")
   suspend fun points(rideId: String): List<RoutePointEntity>
 
+  /** The ride's last count points, newest first: where a point memo opened now is (slice 3 spec §4.3). */
+  @Query("SELECT * FROM route_points WHERE rideId = :rideId ORDER BY id DESC LIMIT :count")
+  suspend fun lastPoints(rideId: String, count: Int): List<RoutePointEntity>
+
   @Query("UPDATE rides SET distanceMeters = :distanceMeters, lastAliveAt = :aliveAt WHERE id = :rideId")
   suspend fun updateDistance(rideId: String, distanceMeters: Double, aliveAt: Long)
 
@@ -382,6 +451,7 @@ interface RideDao {
 abstract class RideDatabase : RoomDatabase() {
   abstract fun rides(): RideDao
   abstract fun asks(): AskDao
+  abstract fun notes(): NoteDao
 
   companion object {
     fun open(context: Context): RideDatabase =
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
index cd848bd..f4026b6 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
@@ -38,9 +38,10 @@ class RoomAskLog(private val dao: AskDao, private val scope: CoroutineScope, pri
     scope.launch { save(record) }
   }
 
+  /** An ask whose ride was deleted meanwhile is dropped (Android #54). */
   suspend fun save(record: AskRecord) {
     try {
-      dao.upsert(record.toEntity())
+      dao.keep(record.toEntity())
       failing.value = false
     } catch (e: CancellationException) {
       throw e
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt b/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt
new file mode 100644
index 0000000..78a4641
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/store/RoomNotes.kt
@@ -0,0 +1,75 @@
+package com.touringproject.v2.store
+
+import com.touringproject.v2.records.NOTE_RECENT_POINTS
+import com.touringproject.v2.records.NoteDraft
+import com.touringproject.v2.records.NoteEdits
+import com.touringproject.v2.records.memoFits
+import com.touringproject.v2.records.noteDraft
+import kotlinx.coroutines.CancellationException
+
+/**
+ * Point memos in Room. Like RoomAskEdits, a change that was written is something new to send (changed), and a failed
+ * write is logged and reported as false, so SC-19 can say so and keep what was typed (slice 3 spec §8).
+ */
+class RoomNotes(
+  private val notes: NoteDao,
+  private val rides: RideDao,
+  private val now: () -> Long,
+  private val newId: () -> String,
+  private val changed: () -> Unit,
+  private val log: (String, Throwable) -> Unit,
+) : NoteEdits {
+  override suspend fun draft(rideId: String): NoteDraft {
+    val at = now()
+    // A memo whose points cannot be read is still opened, without a place.
+    val recent = try {
+      rides.lastPoints(rideId, NOTE_RECENT_POINTS).map { it.toPoint() }
+    } catch (e: CancellationException) {
+      throw e
+    } catch (e: Exception) {
+      log("note_points_failed rideId=$rideId", e)
+      emptyList()
+    }
+    return noteDraft(newId(), rideId, at, recent)
+  }
+
+  override suspend fun create(draft: NoteDraft, text: String): Boolean =
+    usable(text) && attempt("note_create_failed noteId=${draft.id}") { notes.create(draft.toEntity(text, now())) }
+
+  override suspend fun text(noteId: String, text: String): Boolean =
+    usable(text) && attempt("note_text_failed noteId=$noteId") { notes.writeText(noteId, text, now()) }
+
+  override suspend fun delete(noteId: String): Boolean = attempt("note_delete_failed noteId=$noteId") { notes.delete(noteId, now()) }
+
+  private fun usable(text: String) = text.isNotBlank() && memoFits(text)
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
+
+private fun NoteDraft.toEntity(text: String, at: Long) = NoteEntity(
+  id = id,
+  rideId = rideId,
+  at = this.at,
+  latitude = latitude,
+  longitude = longitude,
+  sampleLatitude = sampleLatitude,
+  sampleLongitude = sampleLongitude,
+  sampleAt = sampleAt,
+  text = text,
+  updatedAt = at,
+  sentUpdatedAt = null,
+  rejectedUpdatedAt = null,
+  address = null,
+  headingDegrees = null,
+)
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
index 9e972fe..5ff23c9 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
@@ -2,6 +2,7 @@ package com.touringproject.v2.store
 
 import com.touringproject.v2.ask.AskOutcome
 import com.touringproject.v2.ask.AskRecord
+import com.touringproject.v2.records.NoteRecord
 import com.touringproject.v2.records.RideListItem
 import com.touringproject.v2.records.orderRides
 import com.touringproject.v2.records.saveState
@@ -29,8 +30,10 @@ fun AskEntity.toRecord() = AskRecord(
   memo = memo,
 )
 
-/** What the records screens read (SC-05, SC-06, SC-07). Each Flow follows the database as it changes. */
-class RoomRecords(private val rides: RideDao, private val asks: AskDao) {
+fun NoteEntity.toRecord() = NoteRecord(id, rideId, at, latitude, longitude, text, address, sent = sentUpdatedAt != null)
+
+/** What the records screens read (SC-05, SC-06, SC-07, SC-19). Each Flow follows the database as it changes. */
+class RoomRecords(private val rides: RideDao, private val asks: AskDao, private val notes: NoteDao) {
   val list: Flow<List<RideListItem>> = rides.rows().map { rows ->
     orderRides(
       rows.map { row ->
@@ -44,6 +47,8 @@ class RoomRecords(private val rides: RideDao, private val asks: AskDao) {
 
   fun asks(rideId: String): Flow<List<AskRecord>> = asks.forRide(rideId).map { list -> list.map { it.toRecord() } }
 
+  fun notes(rideId: String): Flow<List<NoteRecord>> = notes.forRide(rideId).map { list -> list.map { it.toRecord() } }
+
   /** Read once when the ride is opened: the route of a ride still recording does not follow it. */
   suspend fun route(rideId: String): List<RoutePoint> = rides.points(rideId).map { it.toPoint() }
 }
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t1.log 2>&1; tail -1 /tmp/trv2-t1.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト457件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt \
  app/src/main/java/com/touringproject/v2/records/NoteEdits.kt \
  app/src/main/java/com/touringproject/v2/records/Notes.kt \
  app/src/main/java/com/touringproject/v2/store/RideDatabase.kt \
  app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt \
  app/src/main/java/com/touringproject/v2/store/RoomNotes.kt \
  app/src/main/java/com/touringproject/v2/store/RoomRecords.kt \
  app/src/test/java/com/touringproject/v2/records/NotesTest.kt \
  app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt \
  app/src/test/java/com/touringproject/v2/store/RoomNotesTest.kt \
  app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
git commit -m "feat: keep point memos at the ride's newest point, and drop an ask whose ride was deleted (Android #54)"
```

---

### Task 2: API: 地点メモの `PUT` と `DELETE`

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `api/ApiClient.kt`
- Test: `api/ApiClientTest.kt`・`sync/RideSyncTest.kt`

**Interfaces:**
- Consumes: `Point`・`HeadingSample`（`api/ApiClient.kt`）
- Produces:
  - `NoteBody(at: String, location: Point?, headingSample: HeadingSample?, text: String, updatedAt: String)`・`NoteSaved(address: String? = null, headingDegrees: Double? = null)`
  - `RideApi.putNote(rideId, noteId, body): NoteSaved`・`RideApi.deleteNote(rideId, noteId)`（`ApiClient` が実装。`location` と `headingSample` は null も送る）

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
index 2ccfa80..791b753 100644
--- a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
+++ b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
@@ -231,4 +231,41 @@ class ApiClientTest {
     assertEquals("DELETE /Prod/rides/r1", server.takeRequest().let { "${it.method} ${it.path}" })
     assertEquals(3, server.requestCount)
   }
+
+  @Test
+  fun putNote_sends_the_whole_memo_and_reads_the_address_and_heading() = runTest {
+    server.enqueue(json(200, """{"noteId":"n1","applied":true,"address":"静岡県御殿場市新橋","headingDegrees":45.5}"""))
+    val body = NoteBody(
+      at = "2026-10-22T01:24:00Z",
+      location = Point(35.3, 138.9),
+      headingSample = HeadingSample(35.29, 138.89, "2026-10-22T01:23:40Z"),
+      text = "展望スペース",
+      updatedAt = "2026-10-22T01:25:00Z",
+    )
+    assertEquals(NoteSaved("静岡県御殿場市新橋", 45.5), client().putNote("r1", "n1", body))
+    val request = server.takeRequest()
+    assertEquals("PUT /Prod/rides/r1/notes/n1", "${request.method} ${request.path}")
+    val sent = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
+    assertEquals("展望スペース", sent["text"]!!.jsonPrimitive.content)
+    assertEquals("35.3", sent["location"]!!.jsonObject["latitude"]!!.jsonPrimitive.content)
+    assertEquals("2026-10-22T01:23:40Z", sent["headingSample"]!!.jsonObject["at"]!!.jsonPrimitive.content)
+    assertEquals("2026-10-22T01:24:00Z", sent["at"]!!.jsonPrimitive.content)
+  }
+
+  // A memo opened before the ride had a point has no place; the Backend then has no address for it.
+  @Test
+  fun a_memo_without_a_place_sends_it_as_null_and_gets_no_address() = runTest {
+    server.enqueue(json(200, """{"noteId":"n1","applied":false,"address":null,"headingDegrees":null}"""))
+    assertEquals(NoteSaved(null, null), client().putNote("r1", "n1", NoteBody("2026-10-22T01:24:00Z", null, null, "x", "2026-10-22T01:25:00Z")))
+    val sent = Json.parseToJsonElement(server.takeRequest().body.readUtf8()).jsonObject
+    assertEquals(JsonNull, sent["location"])
+    assertEquals(JsonNull, sent["headingSample"])
+  }
+
+  @Test
+  fun deleteNote_goes_to_the_memo_under_its_ride() = runTest {
+    server.enqueue(MockResponse().setResponseCode(204))
+    client().deleteNote("r1", "n1")
+    assertEquals("DELETE /Prod/rides/r1/notes/n1", server.takeRequest().let { "${it.method} ${it.path}" })
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
index 6f3a401..7d9d645 100644
--- a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
@@ -3,6 +3,8 @@ package com.touringproject.v2.sync
 import com.touringproject.v2.api.ApiError
 import com.touringproject.v2.api.ApiErrorKind
 import com.touringproject.v2.api.AskMemoBody
+import com.touringproject.v2.api.NoteBody
+import com.touringproject.v2.api.NoteSaved
 import com.touringproject.v2.api.RideApi
 import com.touringproject.v2.api.RideBody
 import com.touringproject.v2.api.RouteBody
@@ -87,6 +89,11 @@ private class World {
     override suspend fun putAskMemo(askId: String, body: AskMemoBody) = call("memo/$askId:${body.memo}")
     override suspend fun deleteRide(rideId: String) = call("delete/ride/$rideId")
     override suspend fun deleteAsk(askId: String) = call("delete/ask/$askId")
+    override suspend fun putNote(rideId: String, noteId: String, body: NoteBody): NoteSaved {
+      call("note/$rideId/$noteId:${body.text}")
+      return NoteSaved()
+    }
+    override suspend fun deleteNote(rideId: String, noteId: String) = call("delete/note/$rideId/$noteId")
   }
 
   val sync = RideSync(store, { if (hasKey) api else null }) { _, _ -> }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ApiClientTest' --tests '*RideSyncTest' > /tmp/trv2-t2.log 2>&1; grep -c '^e: ' /tmp/trv2-t2.log
```

Expected: `BUILD FAILED`。まだ無い `NoteBody`・`putNote`・`deleteNote` を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
index cee0046..66889c2 100644
--- a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
+++ b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
@@ -83,6 +83,13 @@ data class RideBody(
 /** A conversation's memo (slice 3 spec §6.2); null removes it. */
 @Serializable data class AskMemoBody(val memo: String?, val updatedAt: String)
 
+/** A point memo as a whole (slice 3 spec §6.2). location is null for one opened before its ride had a point. */
+@Serializable
+data class NoteBody(val at: String, val location: Point?, val headingSample: HeadingSample?, val text: String, val updatedAt: String)
+
+/** What the Backend settled for a point memo when it first took it; null when it could not tell (no place, no heading). */
+@Serializable data class NoteSaved(val address: String? = null, val headingDegrees: Double? = null)
+
 /**
  * Every call may be sent again and again: the Backend keeps one copy of each, and a deletion is the same however often
  * it comes. A 400 throws BAD_REQUEST, a 404 NOT_FOUND and a 410 (deleted) GONE.
@@ -91,8 +98,10 @@ interface RideApi {
   suspend fun putRide(rideId: String, body: RideBody)
   suspend fun putRoute(rideId: String, seq: Int, body: RouteBody)
   suspend fun putAskMemo(askId: String, body: AskMemoBody)
+  suspend fun putNote(rideId: String, noteId: String, body: NoteBody): NoteSaved
   suspend fun deleteRide(rideId: String)
   suspend fun deleteAsk(askId: String)
+  suspend fun deleteNote(rideId: String, noteId: String)
 }
 
 private val TRANSIENT = setOf(ApiErrorKind.RATE_LIMITED, ApiErrorKind.SERVER, ApiErrorKind.NETWORK)
@@ -155,6 +164,9 @@ class ApiClient(
     request("PUT", "/asks/$askId/memo", rideJson.encodeToString(AskMemoBody.serializer(), body), TRANSIENT)
   }
 
+  override suspend fun putNote(rideId: String, noteId: String, body: NoteBody): NoteSaved =
+    json.decodeFromString(NoteSaved.serializer(), request("PUT", "/rides/$rideId/notes/$noteId", rideJson.encodeToString(NoteBody.serializer(), body), TRANSIENT))
+
   override suspend fun deleteRide(rideId: String) {
     request("DELETE", "/rides/$rideId", null, TRANSIENT)
   }
@@ -163,6 +175,10 @@ class ApiClient(
     request("DELETE", "/asks/$askId", null, TRANSIENT)
   }
 
+  override suspend fun deleteNote(rideId: String, noteId: String) {
+    request("DELETE", "/rides/$rideId/notes/$noteId", null, TRANSIENT)
+  }
+
   suspend fun checkKey() {
     try {
       request("GET", "/asks/$PROBE_ASK_ID", null, TRANSIENT)
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t2.log 2>&1; tail -1 /tmp/trv2-t2.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト460件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/api/ApiClient.kt \
  app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt \
  app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
git commit -m "feat: put and delete point memos on the Backend"
```

---

### Task 3: 送信: 地点メモを走行の後に送る・地点メモの削除・送れない印（#54 の前半）・保存の状態

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `AppGraph.kt`・`records/Records.kt`・`store/RideDatabase.kt`・`store/RoomRecords.kt`・`store/RoomSyncStore.kt`・`sync/RideSync.kt`・`sync/SyncPlan.kt`
- Test: `store/RoomRecordsTest.kt`・`store/RoomSyncStoreTest.kt`・`sync/RideSyncTest.kt`・`sync/SyncPlanTest.kt`

**Interfaces:**
- Consumes: Task 1 の `NoteDao`・Task 2 の `putNote`・`deleteNote`・`NoteSaved`
- Produces:
  - `UnsentNote(id, rideId, at, latitude?, longitude?, sampleLatitude?, sampleLongitude?, sampleAt?, text, updatedAt)`・`SyncStore.unsentNotes()`・`SyncStore.noteSent(noteId, updatedAt, address?, headingDegrees?)`・`SyncStore.noteRefused(noteId, updatedAt)`（`sync/RideSync.kt`）
  - `UnsentNote.toBody(): NoteBody`（`sync/SyncPlan.kt`）
  - `NoteDao.unsent()`・`NoteDao.markSent(id, updatedAt, address?, headingDegrees?)`・`NoteDao.markRefused(id, updatedAt)`・`RideRow.notesLeft`
  - `RoomSyncStore(dao, asks, notes: NoteDao)`

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
index 30ebe42..6a18a9d 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
@@ -30,7 +30,7 @@ class RoomRecordsTest {
     .allowMainThreadQueries()
     .build()
   private val rides = RoomRideStore(db.rides())
-  private val sync = RoomSyncStore(db.rides(), db.asks())
+  private val sync = RoomSyncStore(db.rides(), db.asks(), db.notes())
   private val log = RoomAskLog(db.asks(), MainScope()) { _, _ -> }
   private val records = RoomRecords(db.rides(), db.asks(), db.notes())
 
@@ -102,4 +102,16 @@ class RoomRecordsTest {
     sync.askMemoSent("a1", 5_000)
     assertEquals(SaveState.SAVED, records.list.first().single().saveState)
   }
+
+  // Slice 3 spec §5.3: a point memo not yet taken leaves its ride "未送信あり".
+  @Test
+  fun a_point_memo_not_yet_sent_leaves_the_ride_unsent() = runBlocking {
+    val ended = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(4_000, EndReason.MANUAL, 4_000)
+    rides.save(ended)
+    sync.rideSent("r1", ended.updatedAt)
+    db.notes().create(NoteEntity("n1", "r1", 1_500, null, null, null, null, null, "展望", 5_000, null, null, null, null))
+    assertEquals(SaveState.UNSENT, records.list.first().single().saveState)
+    sync.noteSent("n1", 5_000, null, null)
+    assertEquals(SaveState.SAVED, records.list.first().single().saveState)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
index 7b071fd..beb60d3 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
@@ -14,6 +14,7 @@ import com.touringproject.v2.ride.pause
 import com.touringproject.v2.sync.ChunkRange
 import com.touringproject.v2.sync.PendingDeletion
 import com.touringproject.v2.sync.UnsentAskMemo
+import com.touringproject.v2.sync.UnsentNote
 import com.touringproject.v2.sync.RideSync
 import kotlinx.coroutines.runBlocking
 import kotlinx.serialization.json.Json
@@ -34,7 +35,7 @@ class RoomSyncStoreTest {
     .build()
   private val dao = db.rides()
   private val rides = RoomRideStore(dao)
-  private val store = RoomSyncStore(dao, db.asks())
+  private val store = RoomSyncStore(dao, db.asks(), db.notes())
   private val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)
 
   @After
@@ -155,4 +156,43 @@ class RoomSyncStoreTest {
     assertEquals(2, unsent.sentPoints)
     assertEquals(3, unsent.totalPoints)
   }
+
+  private suspend fun keepNote(id: String, text: String, at: Long) = db.notes().create(
+    NoteEntity(id, "r1", 1_500, 35.0, 139.0, 34.99, 139.0, 1_400, text, at, null, null, null, null),
+  )
+
+  @Test
+  fun a_point_memo_is_unsent_until_its_version_is_taken_and_keeps_its_address() = runBlocking {
+    rides.save(ride)
+    keepNote("n1", "展望", 5_000)
+    keepNote("n2", "給油", 6_000)
+    assertEquals(
+      listOf(UnsentNote("n1", "r1", 1_500, 35.0, 139.0, 34.99, 139.0, 1_400, "展望", 5_000), UnsentNote("n2", "r1", 1_500, 35.0, 139.0, 34.99, 139.0, 1_400, "給油", 6_000)),
+      store.unsentNotes(),
+    )
+    store.noteSent("n1", 5_000, "静岡県御殿場市新橋", 45.5)
+    store.noteRefused("n2", 6_000)
+    assertEquals(emptyList<UnsentNote>(), store.unsentNotes())
+    assertEquals("静岡県御殿場市新橋" to 45.5, db.notes().note("n1")!!.let { it.address to it.headingDegrees })
+    // A later send that is not answered with an address keeps the one settled before.
+    db.notes().writeText("n1", "展望スペース", 7_000)
+    store.noteSent("n1", 7_000, null, null)
+    assertEquals("静岡県御殿場市新橋" to 7_000L, db.notes().note("n1")!!.let { it.address to it.sentUpdatedAt })
+  }
+
+  @Test
+  fun a_point_memo_reaches_the_backend_after_its_ride_and_keeps_the_address() = runBlocking {
+    val server = MockWebServer().apply { start() }
+    server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))
+    server.enqueue(MockResponse().setResponseCode(200).setBody("""{"noteId":"n1","applied":true,"address":"静岡県御殿場市新橋","headingDegrees":45.5}"""))
+    val sync = RideSync(store, { ApiClient(server.url("/Prod/").toString(), "key-1", "rider01", OkHttpClient()) }) { _, _ -> }
+    rides.save(ride)
+    keepNote("n1", "展望", 5_000)
+    sync.pass()
+    assertEquals(listOf("/Prod/rides/r1", "/Prod/rides/r1/notes/n1"), (1..2).map { server.takeRequest().path })
+    assertEquals("静岡県御殿場市新橋", db.notes().note("n1")!!.address)
+    sync.pass()
+    assertEquals(2, server.requestCount)
+    server.shutdown()
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
index 7d9d645..d117438 100644
--- a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
@@ -39,6 +39,14 @@ private class World {
   /** askId to (memo, updatedAt, sent, refused). */
   val memos = linkedMapOf<String, MemoRow>()
   class MemoRow(val memo: String?, val updatedAt: Long, var sent: Long? = null, var refused: Long? = null)
+  class NoteRow(val note: UnsentNote, var sent: Long? = null, var refused: Long? = null, var address: String? = null, var heading: Double? = null)
+  val notes = linkedMapOf<String, NoteRow>()
+  /** What the Backend answers for a point memo, by noteId. */
+  val saved = mutableMapOf<String, NoteSaved>()
+
+  fun note(id: String, updatedAt: Long, text: String = "展望", rideId: String = "r1") {
+    notes[id] = NoteRow(UnsentNote(id, rideId, 1_500, 35.0, 139.0, null, null, null, text, updatedAt))
+  }
   var hasKey = true
   var gate: CompletableDeferred<Unit>? = null
   var passes = 0
@@ -75,6 +83,14 @@ private class World {
       memos.getValue(askId).refused = updatedAt
       calls += "refused:memo/$askId"
     }
+    override suspend fun unsentNotes() = notes.values.filter { (it.sent ?: -1) < it.note.updatedAt && it.refused != it.note.updatedAt }.map { it.note }
+    override suspend fun noteSent(noteId: String, updatedAt: Long, address: String?, headingDegrees: Double?) {
+      notes.getValue(noteId).also { it.sent = updatedAt; it.address = address; it.heading = headingDegrees }
+    }
+    override suspend fun noteRefused(noteId: String, updatedAt: Long) {
+      notes.getValue(noteId).refused = updatedAt
+      calls += "refused:note/$noteId"
+    }
   }
 
   private fun call(name: String) {
@@ -91,7 +107,7 @@ private class World {
     override suspend fun deleteAsk(askId: String) = call("delete/ask/$askId")
     override suspend fun putNote(rideId: String, noteId: String, body: NoteBody): NoteSaved {
       call("note/$rideId/$noteId:${body.text}")
-      return NoteSaved()
+      return saved[noteId] ?: NoteSaved()
     }
     override suspend fun deleteNote(rideId: String, noteId: String) = call("delete/note/$rideId/$noteId")
   }
@@ -223,18 +239,24 @@ class RideSyncTest {
     job.cancel()
   }
 
-  // Slice 3 spec §5.1: deletions go first, then rides, then memos.
+  // Slice 3 spec §5.1: deletions go first, then rides, then point memos, then memos.
   @Test
-  fun a_pass_sends_deletions_then_rides_then_memos() = runTest {
+  fun a_pass_sends_deletions_then_rides_then_point_memos_then_memos() = runTest {
     val w = World()
     w.add(recording)
     w.memos["a1"] = World.MemoRow("また来たい", 2_000)
+    w.note("n1", 1_900)
     w.deletions += PendingDeletion("ride", "r0", null)
     w.deletions += PendingDeletion("ask", "a0", "r1")
+    w.deletions += PendingDeletion("note", "n0", "r1")
     w.sync.pass()
-    assertEquals(listOf("delete/ride/r0", "delete/ask/a0", "ride/r1:recording", "memo/a1:また来たい"), w.calls)
+    assertEquals(
+      listOf("delete/ride/r0", "delete/ask/a0", "delete/note/r1/n0", "ride/r1:recording", "note/r1/n1:展望", "memo/a1:また来たい"),
+      w.calls,
+    )
     assertTrue(w.deletions.isEmpty())
     assertEquals(2_000L, w.memos.getValue("a1").sent)
+    assertEquals(1_900L, w.notes.getValue("n1").sent)
     w.calls.clear()
     w.sync.pass()
     assertEquals(emptyList<String>(), w.calls)
@@ -321,4 +343,60 @@ class RideSyncTest {
     w.sync.pass()
     assertEquals(listOf("memo/a1:null"), w.calls)
   }
+
+  // Slice 3 spec §5.1: the address and heading the Backend settled are kept with the memo.
+  @Test
+  fun a_point_memo_keeps_the_address_and_heading_the_backend_settled() = runTest {
+    val w = World()
+    w.note("n1", 2_000)
+    w.saved["n1"] = NoteSaved("静岡県御殿場市新橋", 45.5)
+    w.sync.pass()
+    val row = w.notes.getValue("n1")
+    assertEquals(Triple(2_000L, "静岡県御殿場市新橋", 45.5), Triple(row.sent, row.address, row.heading))
+    w.calls.clear()
+    w.sync.pass()
+    assertEquals(emptyList<String>(), w.calls)
+  }
+
+  @Test
+  fun a_refused_point_memo_is_not_sent_again_until_it_changes_and_a_gone_one_is_taken_as_sent() = runTest {
+    val w = World()
+    w.note("n1", 2_000, text = "x")
+    w.note("n2", 2_100, text = "y")
+    w.fail["note/r1/n1:x"] = ApiErrorKind.BAD_REQUEST
+    w.fail["note/r1/n2:y"] = ApiErrorKind.GONE
+    w.sync.pass()
+    assertEquals(listOf("note/r1/n1:x", "refused:note/n1", "note/r1/n2:y"), w.calls)
+    assertEquals(2_100L, w.notes.getValue("n2").sent)
+    w.calls.clear()
+    w.sync.pass()
+    assertEquals(emptyList<String>(), w.calls)
+    w.note("n1", 2_200, text = "z")
+    w.sync.pass()
+    assertEquals(listOf("note/r1/n1:z"), w.calls)
+  }
+
+  // A failed point memo ends the pass before the memos, and goes again first in the next one.
+  @Test
+  fun a_point_memo_that_fails_ends_the_pass() = runTest {
+    val w = World()
+    w.note("n1", 2_000)
+    w.memos["a1"] = World.MemoRow("x", 2_000)
+    w.fail["note/r1/n1:展望"] = ApiErrorKind.NETWORK
+    w.sync.pass()
+    assertEquals(listOf("note/r1/n1:展望"), w.calls)
+    assertEquals(null, w.notes.getValue("n1").sent)
+  }
+
+  // Android #54: a mark of a kind the device cannot send is dropped, and what comes after it still goes.
+  @Test
+  fun a_deletion_of_an_unknown_kind_is_dropped_and_the_rest_still_goes() = runTest {
+    val w = World()
+    w.add(recording)
+    w.deletions += PendingDeletion("photo", "p0", "r1")
+    w.deletions += PendingDeletion("note", "n0", null)
+    w.sync.pass()
+    assertEquals(listOf("ride/r1:recording"), w.calls)
+    assertTrue(w.deletions.isEmpty())
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt b/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
index 37be6d1..a030759 100644
--- a/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
@@ -1,5 +1,7 @@
 package com.touringproject.v2.sync
 
+import com.touringproject.v2.api.HeadingSample
+import com.touringproject.v2.api.Point
 import com.touringproject.v2.api.SegmentBody
 import com.touringproject.v2.ride.EndReason
 import com.touringproject.v2.ride.HOUR_MS
@@ -9,6 +11,7 @@ import com.touringproject.v2.ride.newRide
 import com.touringproject.v2.ride.pause
 import org.junit.Assert.assertEquals
 import org.junit.Assert.assertFalse
+import org.junit.Assert.assertNull
 import org.junit.Assert.assertTrue
 import org.junit.Test
 
@@ -63,4 +66,18 @@ class SyncPlanTest {
     assertEquals("1970-01-01T00:00:01.234Z", body.t)
     assertEquals(2, body.segment)
   }
+
+  // Slice 3 spec §6.2: a memo without a place goes without one, and a heading sample goes only when it is whole.
+  @Test
+  fun a_point_memo_goes_with_its_place_and_sample_in_utc() {
+    val note = UnsentNote("n1", "r1", 1_000, 35.3, 138.9, 35.29, 138.89, 500, "展望スペース", 2_000)
+    val body = note.toBody()
+    assertEquals("1970-01-01T00:00:01Z", body.at)
+    assertEquals(Point(35.3, 138.9), body.location)
+    assertEquals(HeadingSample(35.29, 138.89, "1970-01-01T00:00:00.500Z"), body.headingSample)
+    assertEquals("展望スペース" to "1970-01-01T00:00:02Z", body.text to body.updatedAt)
+    val bare = note.copy(latitude = null, longitude = null, sampleAt = null).toBody()
+    assertNull(bare.location)
+    assertNull(bare.headingSample)
+  }
 }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SyncPlanTest' --tests '*RideSyncTest' --tests '*RoomSyncStoreTest' --tests '*RoomRecordsTest' > /tmp/trv2-t3.log 2>&1; grep -c '^e: ' /tmp/trv2-t3.log
```

Expected: `BUILD FAILED`。まだ無い `UnsentNote`・`unsentNotes`・`noteSent`・`RoomSyncStore` の3つ目の引数を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 6868c4f..e32909b 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -95,9 +95,9 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   val records = RoomRecords(database.rides(), database.asks(), database.notes())
   private val notices = RideNotices(context)
 
-  /** Sends rides and routes; a pass runs on each trigger (slice 2 spec §5.3). */
+  /** Sends rides, routes, memos, point memos and deletions; a pass runs on each trigger (slice 2 spec §5.3). */
   val sync = RideSync(
-    RoomSyncStore(database.rides(), database.asks()),
+    RoomSyncStore(database.rides(), database.asks(), database.notes()),
     api = {
       val key = apiKeys.current()
       val user = settings.settings.value?.userName
diff --git a/app/src/main/java/com/touringproject/v2/records/Records.kt b/app/src/main/java/com/touringproject/v2/records/Records.kt
index 3197785..ed51cd3 100644
--- a/app/src/main/java/com/touringproject/v2/records/Records.kt
+++ b/app/src/main/java/com/touringproject/v2/records/Records.kt
@@ -15,8 +15,8 @@ enum class SaveState { RECORDING, UNSENT, SAVED }
 
 /**
  * "記録中" while the ride records or is paused; "未送信あり" while its newest version has not been taken (a refused one
- * included) or something of it has not gone or was refused (pointsLeft: a point, or the memo of one of its asks;
- * slice 3 spec §5.3); "保存済み" otherwise (slice 2 spec §5.4).
+ * included) or something of it has not gone or was refused (pointsLeft: a point, the memo of one of its asks or
+ * one of its point memos; slice 3 spec §5.3); "保存済み" otherwise (slice 2 spec §5.4).
  */
 fun saveState(status: RideStatus, updatedAt: Long, sentUpdatedAt: Long?, pointsLeft: Boolean): SaveState = when {
   status != RideStatus.ENDED -> SaveState.RECORDING
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 613d2fe..04bca6e 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -272,6 +272,26 @@ interface NoteDao {
     markDeleted(DeletionEntity("note", id, note.rideId, at))
     return true
   }
+
+  // Sending (slice 3 spec §5.1): the memos changed since they were taken, unless that version was refused.
+  @Query(
+    "SELECT * FROM notes WHERE (sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
+      "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt) ORDER BY updatedAt",
+  )
+  suspend fun unsent(): List<NoteEntity>
+
+  /**
+   * The marker never moves back. The address and heading are settled by the Backend once; a send it answers without
+   * them (410: deleted there) keeps what the memo has.
+   */
+  @Query(
+    "UPDATE notes SET sentUpdatedAt = MAX(IFNULL(sentUpdatedAt, :updatedAt), :updatedAt), address = IFNULL(:address, address), " +
+      "headingDegrees = IFNULL(:headingDegrees, headingDegrees) WHERE id = :id",
+  )
+  suspend fun markSent(id: String, updatedAt: Long, address: String?, headingDegrees: Double?)
+
+  @Query("UPDATE notes SET rejectedUpdatedAt = :updatedAt WHERE id = :id")
+  suspend fun markRefused(id: String, updatedAt: Long)
 }
 
 /** What one ride has left to send, read together (Android #23). */
@@ -284,7 +304,8 @@ data class RideWithSegments(
 
 /**
  * A ride as SC-05 lists it. pointsLeft is true while one of its points has not been taken (unsent or refused);
- * memosLeft while the memo of one of its asks has not been taken (slice 3 spec §5.3).
+ * memosLeft while the memo of one of its asks has not been taken, and notesLeft one of its point memos (slice 3 spec
+ * §5.3).
  */
 data class RideRow(
   @Embedded val ride: RideEntity,
@@ -292,6 +313,7 @@ data class RideRow(
   val questions: Int,
   val pointsLeft: Boolean,
   val memosLeft: Boolean,
+  val notesLeft: Boolean,
 )
 
 @Dao
@@ -312,7 +334,9 @@ interface RideDao {
       "(EXISTS (SELECT 1 FROM route_points WHERE chunk IS NULL AND route_points.rideId = rides.id) OR " +
       "EXISTS (SELECT 1 FROM route_points WHERE refused = 1 AND route_points.rideId = rides.id)) AS pointsLeft, " +
       "EXISTS (SELECT 1 FROM asks WHERE asks.rideId = rides.id AND asks.memoUpdatedAt IS NOT NULL AND " +
-      "(asks.memoSentUpdatedAt IS NULL OR asks.memoSentUpdatedAt < asks.memoUpdatedAt)) AS memosLeft FROM rides",
+      "(asks.memoSentUpdatedAt IS NULL OR asks.memoSentUpdatedAt < asks.memoUpdatedAt)) AS memosLeft, " +
+      "EXISTS (SELECT 1 FROM notes WHERE notes.rideId = rides.id AND " +
+      "(notes.sentUpdatedAt IS NULL OR notes.sentUpdatedAt < notes.updatedAt)) AS notesLeft FROM rides",
   )
   fun rows(): Flow<List<RideRow>>
 
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
index 5ff23c9..5d92429 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
@@ -38,7 +38,7 @@ class RoomRecords(private val rides: RideDao, private val asks: AskDao, private
     orderRides(
       rows.map { row ->
         val ride = row.ride.toRide(row.segments.sortedBy { it.seq })
-        RideListItem(ride, row.questions, saveState(ride.status, ride.updatedAt, row.ride.sentUpdatedAt, row.pointsLeft || row.memosLeft))
+        RideListItem(ride, row.questions, saveState(ride.status, ride.updatedAt, row.ride.sentUpdatedAt, row.pointsLeft || row.memosLeft || row.notesLeft))
       },
     )
   }
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
index e97110d..0ff4511 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
@@ -6,8 +6,9 @@ import com.touringproject.v2.sync.PendingDeletion
 import com.touringproject.v2.sync.SyncStore
 import com.touringproject.v2.sync.Unsent
 import com.touringproject.v2.sync.UnsentAskMemo
+import com.touringproject.v2.sync.UnsentNote
 
-class RoomSyncStore(private val dao: RideDao, private val asks: AskDao) : SyncStore {
+class RoomSyncStore(private val dao: RideDao, private val asks: AskDao, private val notes: NoteDao) : SyncStore {
   override suspend fun unsent(): List<Unsent> = dao.unsentSnapshot().map {
     Unsent(it.ride.toRide(it.segments), it.ride.sentUpdatedAt, it.ride.rejectedUpdatedAt, it.sentPoints, it.totalPoints)
   }
@@ -32,4 +33,13 @@ class RoomSyncStore(private val dao: RideDao, private val asks: AskDao) : SyncSt
   override suspend fun askMemoSent(askId: String, updatedAt: Long) = asks.markMemoSent(askId, updatedAt)
 
   override suspend fun askMemoRefused(askId: String, updatedAt: Long) = asks.markMemoRefused(askId, updatedAt)
+
+  override suspend fun unsentNotes(): List<UnsentNote> = notes.unsent().map {
+    UnsentNote(it.id, it.rideId, it.at, it.latitude, it.longitude, it.sampleLatitude, it.sampleLongitude, it.sampleAt, it.text, it.updatedAt)
+  }
+
+  override suspend fun noteSent(noteId: String, updatedAt: Long, address: String?, headingDegrees: Double?) =
+    notes.markSent(noteId, updatedAt, address, headingDegrees)
+
+  override suspend fun noteRefused(noteId: String, updatedAt: Long) = notes.markRefused(noteId, updatedAt)
 }
diff --git a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
index 65d55a1..a9bdd28 100644
--- a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
@@ -3,6 +3,7 @@ package com.touringproject.v2.sync
 import com.touringproject.v2.api.ApiError
 import com.touringproject.v2.api.ApiErrorKind
 import com.touringproject.v2.api.AskMemoBody
+import com.touringproject.v2.api.NoteSaved
 import com.touringproject.v2.api.RideApi
 import com.touringproject.v2.api.RouteBody
 import com.touringproject.v2.ride.Ride
@@ -27,6 +28,20 @@ data class PendingDeletion(val kind: String, val id: String, val rideId: String?
 /** A conversation's memo that has changed since the Backend last took it; memo null removes it. */
 data class UnsentAskMemo(val askId: String, val memo: String?, val updatedAt: Long)
 
+/** A point memo that has changed since the Backend last took it, as a whole; it goes as it is now (slice 3 spec §5.1). */
+data class UnsentNote(
+  val id: String,
+  val rideId: String,
+  val at: Long,
+  val latitude: Double?,
+  val longitude: Double?,
+  val sampleLatitude: Double?,
+  val sampleLongitude: Double?,
+  val sampleAt: Long?,
+  val text: String,
+  val updatedAt: Long,
+)
+
 interface SyncStore {
   /**
    * Rides whose meta has changed since it was sent (and was not refused), or that have points not yet sent. Read in
@@ -48,6 +63,11 @@ interface SyncStore {
   suspend fun askMemoSent(askId: String, updatedAt: Long)
   /** The Backend refused the memo as of updatedAt (400, or 404 for an ask it does not have); it is not sent again. */
   suspend fun askMemoRefused(askId: String, updatedAt: Long)
+  suspend fun unsentNotes(): List<UnsentNote>
+  /** The Backend took the point memo as of updatedAt; address and headingDegrees are what it settled, null when it did not say. */
+  suspend fun noteSent(noteId: String, updatedAt: Long, address: String?, headingDegrees: Double?)
+  /** The Backend refused the point memo as of updatedAt (400); that version is not sent again. */
+  suspend fun noteRefused(noteId: String, updatedAt: Long)
 }
 
 /** How the Backend answered a send that did not fail on the way. */
@@ -95,6 +115,10 @@ class RideSync(
     for (unsent in rides) {
       if (!attempt(unsent.ride.id) { sendRide(client, unsent) }) return
     }
+    val notes = read("notes") { store.unsentNotes() } ?: return
+    for (note in notes) {
+      if (!attempt(note.id) { sendNote(client, note) }) return
+    }
     val memos = read("ask_memos") { store.unsentAskMemos() } ?: return
     for (memo in memos) {
       if (!attempt(memo.askId) { sendAskMemo(client, memo) }) return
@@ -121,14 +145,16 @@ class RideSync(
     false
   }
 
-  // A deletion that is refused can never go either; its mark goes, and the log tells.
+  // A deletion that is refused can never go either; its mark goes, and the log tells. So does a mark the device cannot
+  // send at all (a kind it does not know, a point memo without its ride): kept, it would hold back every pass (Android #54).
   private suspend fun sendDeletion(client: RideApi, deletion: PendingDeletion) {
-    reply(deletion.id, "delete/${deletion.kind}") {
-      when (deletion.kind) {
-        "ride" -> client.deleteRide(deletion.id)
-        "ask" -> client.deleteAsk(deletion.id)
-        else -> throw IllegalStateException("unknown deletion kind ${deletion.kind}")
-      }
+    val what = "delete/${deletion.kind}"
+    val rideId = deletion.rideId
+    when {
+      deletion.kind == "ride" -> reply(deletion.id, what) { client.deleteRide(deletion.id) }
+      deletion.kind == "ask" -> reply(deletion.id, what) { client.deleteAsk(deletion.id) }
+      deletion.kind == "note" && rideId != null -> reply(deletion.id, what) { client.deleteNote(rideId, deletion.id) }
+      else -> log("sync_unsendable", mapOf("id" to deletion.id, "what" to what))
     }
     store.deletionSent(deletion)
   }
@@ -150,6 +176,16 @@ class RideSync(
     }
   }
 
+  // GONE: the memo or its ride was deleted on the Backend; it has no address to give.
+  private suspend fun sendNote(client: RideApi, note: UnsentNote) {
+    var saved: NoteSaved? = null
+    if (reply(note.id, "note") { saved = client.putNote(note.rideId, note.id, note.toBody()) } == Reply.REFUSED) {
+      store.noteRefused(note.id, note.updatedAt)
+    } else {
+      store.noteSent(note.id, note.updatedAt, saved?.address, saved?.headingDegrees)
+    }
+  }
+
   private suspend fun sendAskMemo(client: RideApi, memo: UnsentAskMemo) {
     if (reply(memo.askId, "memo") { client.putAskMemo(memo.askId, AskMemoBody(memo.memo, iso(memo.updatedAt))) } == Reply.REFUSED) {
       store.askMemoRefused(memo.askId, memo.updatedAt)
diff --git a/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt b/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
index 37f8fdf..dbdb216 100644
--- a/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt
@@ -1,5 +1,8 @@
 package com.touringproject.v2.sync
 
+import com.touringproject.v2.api.HeadingSample
+import com.touringproject.v2.api.NoteBody
+import com.touringproject.v2.api.Point
 import com.touringproject.v2.api.PointBody
 import com.touringproject.v2.api.RideBody
 import com.touringproject.v2.api.SegmentBody
@@ -55,3 +58,10 @@ fun Ride.toBody() = RideBody(
 )
 
 fun RoutePoint.toBody() = PointBody(iso(t), lat, lon, accuracy, segment)
+
+/** A memo opened before its ride had a point goes without a place; the sample goes only when it is whole. */
+fun UnsentNote.toBody(): NoteBody {
+  val location = if (latitude != null && longitude != null) Point(latitude, longitude) else null
+  val sample = if (sampleLatitude != null && sampleLongitude != null && sampleAt != null) HeadingSample(sampleLatitude, sampleLongitude, iso(sampleAt)) else null
+  return NoteBody(iso(at), location, sample, text, iso(updatedAt))
+}
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t3.log 2>&1; tail -1 /tmp/trv2-t3.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト468件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt \
  app/src/main/java/com/touringproject/v2/records/Records.kt \
  app/src/main/java/com/touringproject/v2/store/RideDatabase.kt \
  app/src/main/java/com/touringproject/v2/store/RoomRecords.kt \
  app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt \
  app/src/main/java/com/touringproject/v2/sync/RideSync.kt \
  app/src/main/java/com/touringproject/v2/sync/SyncPlan.kt \
  app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt \
  app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt \
  app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt \
  app/src/test/java/com/touringproject/v2/sync/SyncPlanTest.kt
git commit -m "feat: send point memos after the rides and their deletions, and drop a mark that cannot be sent (Android #54)"
```

---

### Task 4: 表示の組み立て: 地点メモの番号・時系列・#51・ピンとカード・SC-19 の上部

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `map/MapData.kt`・`map/RouteMap.kt`・`ui/RecordLabels.kt`・`ui/RecordsRoutes.kt`・`ui/RecordsScreens.kt`
- Test: `map/MapDataTest.kt`・`ui/RecordLabelsTest.kt`・`ui/RecordsScreensTest.kt`

**Interfaces:**
- Consumes: Task 1 の `NoteRecord`・`NoteDraft`
- Produces:
  - `enum class PinKind { ASK, NOTE }`・`MapPin(id, number, at, memo = false, kind = PinKind.ASK)`（`askId` は `id` に変わる）・`pinIcon(number, selected, memo = false, kind = PinKind.ASK)`。GeoJSON のピンの項目は `id`（`map/MapData.kt`）
  - `pinBitmap(number, selected, density, memo = false, kind = PinKind.ASK)`（緑）・押したピンの `id` を返す（`map/RouteMap.kt`）
  - `noteNumbers(notes)`・`notePins(notes)`・`notePlace(note)`・`TimelineRow.Note(noteId, number, time, place, text)`・`rideTimeline(ride, asks, zone, notes = emptyList())`・`PinCardUi(id, heading, question, answer, kind = PinKind.ASK)`（`askId` は `id` に変わる）・`noteCard(notes, noteId, zone)`・`NoteHeaderUi(time, where, ride)`・`newNoteHeader(draft, rideName, zone)`・`noteHeader(note, rideName, zone)`・`RideSummaryUi.notes: String?`・`rideSummary(..., notes: Int = 0)`（`ui/RecordLabels.kt`）
  - `RideDetailScreen(..., onNote: (String) -> Unit = {})`。時系列の地点メモの行（タグ `note-<noteId>`）

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt b/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt
index 58d7cad..a207071 100644
--- a/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt
+++ b/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt
@@ -67,4 +67,16 @@ class MapDataTest {
     assertEquals(listOf("pin-1-memo", "pin-2"), icons(null))
     assertEquals(listOf("pin-sel-1-memo", "pin-2"), icons("a1"))
   }
+
+  // US-D-08: a point memo's pin is green and numbered apart from the asks; a tap names it by its id.
+  @Test
+  fun a_point_memos_pin_takes_an_image_of_its_own_and_names_its_id() {
+    val map = rideMap(points, ended = true, pins = listOf(MapPin("a1", 1, LatLon(35.0, 139.0)), MapPin("n1", 1, LatLon(35.1, 139.1), kind = PinKind.NOTE)))
+    val properties = { selected: String? ->
+      Json.parseToJsonElement(pinsJson(map, selected)).jsonObject["features"]!!.jsonArray
+        .map { it.jsonObject["properties"]!!.jsonObject.let { p -> p["id"]!!.jsonPrimitive.content to p["icon"]!!.jsonPrimitive.content } }
+    }
+    assertEquals(listOf("a1" to "pin-1", "n1" to "note-1"), properties(null))
+    assertEquals(listOf("a1" to "pin-1", "n1" to "note-sel-1"), properties("n1"))
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
index 7e835de..514113c 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
@@ -2,6 +2,10 @@ package com.touringproject.v2.ui
 
 import com.touringproject.v2.ask.AskOutcome
 import com.touringproject.v2.ask.AskRecord
+import com.touringproject.v2.map.LatLon
+import com.touringproject.v2.map.PinKind
+import com.touringproject.v2.records.NoteDraft
+import com.touringproject.v2.records.NoteRecord
 import com.touringproject.v2.records.RideListItem
 import com.touringproject.v2.records.SaveState
 import com.touringproject.v2.ride.EndReason
@@ -98,7 +102,7 @@ class RecordLabelsTest {
   @Test
   fun pins_are_numbered_like_the_timeline_and_an_ask_without_a_place_has_none() {
     val asks = listOf(ask("a2", ms(16, 10, 30)), ask("a1", ms(16, 9, 41)).copy(latitude = null, longitude = null))
-    assertEquals(listOf("a2" to 2), askPins(asks).map { it.askId to it.number })
+    assertEquals(listOf("a2" to 2), askPins(asks).map { it.id to it.number })
   }
 
   @Test
@@ -130,7 +134,8 @@ class RecordLabelsTest {
     assertEquals("金時山です。", card.answer)
   }
 
-  // Android #41: the day after the night has no ask, yet the ride runs over two days.
+  // Android #41, #51: the day after the night has no ask, yet the ride runs over two days, and the day it resumed on
+  // gets its heading.
   @Test
   fun an_overnight_ride_without_asks_after_midnight_still_gets_its_day_headings() {
     val overnight = newRide("r2", "伊豆", ms(16, 15, 0), 7, 48 * HOUR_MS).pause(ms(16, 21, 10)).resume(ms(17, 8, 30), 7, 48 * HOUR_MS)
@@ -140,6 +145,7 @@ class RecordLabelsTest {
         TimelineRow.Day("10月16日（金）"),
         TimelineRow.Ask("a1", 1, "16:00", "足柄下郡箱根町仙石原", "右手の山は？", false),
         TimelineRow.Pause("⏸ 一時停止 21:10〜10月17日 08:30"),
+        TimelineRow.Day("10月17日（土）"),
       ),
       rideTimeline(overnight, listOf(ask("a1", ms(16, 16, 0))), zone),
     )
@@ -175,4 +181,70 @@ class RecordLabelsTest {
     assertEquals("会話 2 · 10:30 足柄下郡箱根町仙石原", askMemoTarget(asks, "a2", zone))
     assertNull(askMemoTarget(asks, "a9", zone))
   }
+
+  private fun note(id: String, at: Long, address: String? = "静岡県御殿場市新橋", sent: Boolean = true, placed: Boolean = true) =
+    NoteRecord(id, "r1", at, if (placed) 35.3 else null, if (placed) 138.9 else null, "料金所の手前の展望スペース", address, sent)
+
+  // US-D-08: point memos have numbers of their own and mix with the asks in time order.
+  @Test
+  fun point_memos_are_numbered_apart_from_the_asks_and_mixed_into_the_timeline() {
+    val asks = listOf(ask("a1", ms(16, 9, 41)), ask("a2", ms(16, 10, 30)))
+    val notes = listOf(note("n2", ms(16, 10, 40), address = null, sent = false), note("n1", ms(16, 9, 50)), note("n0", ms(16, 9, 0), address = null, placed = false))
+    assertEquals(
+      listOf(
+        TimelineRow.Note("n0", 1, "09:00", "位置の記録なし", "料金所の手前の展望スペース"),
+        TimelineRow.Ask("a1", 1, "09:41", "足柄下郡箱根町仙石原", "右手の山は？", false),
+        TimelineRow.Pause("⏸ 一時停止 09:44〜10:02（18分）"),
+        TimelineRow.Note("n1", 2, "09:50", "御殿場市新橋", "料金所の手前の展望スペース"),
+        TimelineRow.Ask("a2", 2, "10:30", "足柄下郡箱根町仙石原", "右手の山は？", false),
+        TimelineRow.Note("n2", 3, "10:40", "住所は送信後", "料金所の手前の展望スペース"),
+      ),
+      rideTimeline(ride, asks, zone, notes),
+    )
+    // A memo without a place keeps its number but has no pin.
+    assertEquals(listOf(Triple("n1", 2, PinKind.NOTE), Triple("n2", 3, PinKind.NOTE)), notePins(notes).map { Triple(it.id, it.number, it.kind) })
+    assertEquals(LatLon(35.3, 138.9), notePins(notes).first().at)
+  }
+
+  @Test
+  fun a_point_memo_without_an_address_says_why() {
+    assertEquals("御殿場市新橋", notePlace(note("n1", 0)))
+    assertEquals("住所は送信後", notePlace(note("n1", 0, address = null, sent = false)))
+    assertEquals("場所不明", notePlace(note("n1", 0, address = null, sent = true)))
+    assertEquals("位置の記録なし", notePlace(note("n1", 0, address = null, sent = false, placed = false)))
+  }
+
+  @Test
+  fun a_point_memos_card_shows_its_green_number_the_time_and_the_place() {
+    val notes = listOf(note("n1", ms(16, 9, 50)), note("n2", ms(16, 10, 40)))
+    assertEquals(
+      PinCardUi("n2", "2 · 10:40 · 御殿場市新橋 · 📝 地点メモ", "料金所の手前の展望スペース", null, PinKind.NOTE),
+      noteCard(notes, "n2", zone),
+    )
+    assertNull(noteCard(notes, "n9", zone))
+  }
+
+  // SC-19: when, where and which ride; the address comes from the Backend once the memo has gone (slice 3 spec §7.3).
+  @Test
+  fun sc_19_says_when_where_and_for_which_ride() {
+    val draft = NoteDraft("n1", "r1", ms(22, 10, 24), 35.3, 138.9, null, null, null)
+    assertEquals(
+      NoteHeaderUi("10月22日（木） 10:24 · 今いる地点", "📍 住所は送ったあとに付きます", "走行「箱根」に入ります"),
+      newNoteHeader(draft, "箱根", zone),
+    )
+    assertEquals("📍 位置を記録できませんでした", newNoteHeader(draft.copy(latitude = null, longitude = null), "箱根", zone).where)
+    assertEquals(
+      NoteHeaderUi("10月16日（金） 09:50", "📍 静岡県御殿場市新橋", "走行「箱根」で書いたメモ"),
+      noteHeader(note("n1", ms(16, 9, 50)), "箱根", zone),
+    )
+    assertEquals("📍 住所は送ったあとに付きます", noteHeader(note("n1", 0, address = null, sent = false), "箱根", zone).where)
+    assertEquals("📍 住所は分かりませんでした", noteHeader(note("n1", 0, address = null, sent = true), "箱根", zone).where)
+    assertEquals("📍 位置を記録できませんでした", noteHeader(note("n1", 0, address = null, placed = false), "箱根", zone).where)
+  }
+
+  @Test
+  fun the_summary_counts_the_point_memos_only_when_there_are_some() {
+    assertEquals("📝 地点メモ 2件", rideSummary(ride, 4, ms(17, 0, 0), zone, notes = 2).notes)
+    assertNull(rideSummary(ride, 4, ms(17, 0, 0), zone).notes)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
index 5753bed..5e9a4fd 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
@@ -44,7 +44,7 @@ class RecordsScreensTest {
   private val fakeMap: MapSlot = { data, selected, onPin, modifier ->
     Column(modifier.testTag("map")) {
       Text("pins ${data.pins.size} selected $selected", Modifier.testTag("mapState"))
-      data.pins.forEach { pin -> Button(onClick = { onPin(pin.askId) }, Modifier.testTag("pin-${pin.askId}")) { Text("${pin.number}") } }
+      data.pins.forEach { pin -> Button(onClick = { onPin(pin.id) }, Modifier.testTag("pin-${pin.id}")) { Text("${pin.number}") } }
     }
   }
 
@@ -352,4 +352,16 @@ class RecordsScreensTest {
     rule.waitForIdle()
     assertEquals(1, finished)
   }
+
+  // US-D-08: a point memo's row in the timeline opens it in SC-19.
+  @Test
+  fun a_point_memo_in_the_timeline_opens_it() {
+    val opened = mutableListOf<String>()
+    val ui = detail().copy(timeline = listOf(TimelineRow.Note("n1", 1, "09:50", "御殿場市新橋", "展望スペース")))
+    rule.setContent { RideDetailScreen(ui, fakeMap, true, {}, {}, {}, { true }, {}, onNote = { opened += it }) }
+    rule.onNodeWithTag("timeline").performScrollToNode(hasTestTag("note-n1"))
+    rule.onNodeWithText("09:50 · 御殿場市新橋 · 📝 地点メモ").assertExists()
+    rule.onNodeWithTag("note-n1").performClick()
+    assertEquals(listOf("n1"), opened)
+  }
 }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RecordLabelsTest' --tests '*MapDataTest' --tests '*RecordsScreensTest' > /tmp/trv2-t4.log 2>&1; grep -c '^e: ' /tmp/trv2-t4.log
```

Expected: `BUILD FAILED`。まだ無い `PinKind`・`NoteRecord` を受ける `rideTimeline`・`TimelineRow.Note` を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/map/MapData.kt b/app/src/main/java/com/touringproject/v2/map/MapData.kt
index 7aa3b9c..58090aa 100644
--- a/app/src/main/java/com/touringproject/v2/map/MapData.kt
+++ b/app/src/main/java/com/touringproject/v2/map/MapData.kt
@@ -12,8 +12,14 @@ import kotlinx.serialization.json.put
 
 data class LatLon(val lat: Double, val lon: Double)
 
-/** A numbered ask on the map; number is the ask's place in the ride's timeline. memo: the ask has a memo (US-D-04.005). */
-data class MapPin(val askId: String, val number: Int, val at: LatLon, val memo: Boolean = false)
+/** Asks are orange pins, point memos green ones, each numbered on its own (US-D-08). */
+enum class PinKind { ASK, NOTE }
+
+/**
+ * A numbered ask or point memo on the map; id is its askId or noteId, and number its place among the ride's of its
+ * kind. memo: the ask has a memo (US-D-04.005).
+ */
+data class MapPin(val id: String, val number: Int, val at: LatLon, val memo: Boolean = false, val kind: PinKind = PinKind.ASK)
 
 /**
  * routes has one line per recorded segment that has points; pauses joins the last point of a segment to the first
@@ -85,18 +91,20 @@ fun endsJson(data: MapData): String = collection(
   },
 )
 
-/** icon names the pin's image: its number, and whether it is the selected one. */
+/** id is what a tap on the pin names; icon names the pin's image: its kind, its number, and whether it is the selected one. */
 fun pinsJson(data: MapData, selected: String?): String = collection(
   data.pins.map { pin ->
     feature(
       point(pin.at),
       buildJsonObject {
-        put("askId", pin.askId)
-        put("icon", pinIcon(pin.number, pin.askId == selected, pin.memo))
+        put("id", pin.id)
+        put("icon", pinIcon(pin.number, pin.id == selected, pin.memo, pin.kind))
       },
     )
   },
 )
 
-fun pinIcon(number: Int, selected: Boolean, memo: Boolean = false): String =
-  (if (selected) "pin-sel-$number" else "pin-$number") + if (memo) "-memo" else ""
+fun pinIcon(number: Int, selected: Boolean, memo: Boolean = false, kind: PinKind = PinKind.ASK): String {
+  val name = if (kind == PinKind.NOTE) "note" else "pin"
+  return (if (selected) "$name-sel-$number" else "$name-$number") + if (memo) "-memo" else ""
+}
diff --git a/app/src/main/java/com/touringproject/v2/map/RouteMap.kt b/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
index fdc5959..435f09c 100644
--- a/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
+++ b/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
@@ -58,6 +58,8 @@ private const val STYLE_ASSET = "map/gsi-pale.json"
 private const val ROUTE_COLOR = "#F06D1A"
 private const val PAUSE_COLOR = "#8A929C"
 private const val PIN_COLOR = 0xFFE8600F.toInt()
+// The mock's --memo: point memos are green, apart from the asks (US-D-08).
+private const val NOTE_PIN_COLOR = 0xFF13804A.toInt()
 private const val PIN_SELECTED_COLOR = 0xFF1F4FD1.toInt()
 /** The layer a tap on a pin is looked up in (slice 2 spec §7.7). */
 const val PINS_LAYER = "pins"
@@ -67,10 +69,15 @@ private val JAPAN = LatLng(36.2, 138.25)
 private fun styleJson(context: Context) = context.assets.open(STYLE_ASSET).bufferedReader().use { it.readText() }
 
 /**
- * A teardrop pin with its number, the tip at the bottom, as in the mock. memo adds a small white dot at its top right:
- * the ask has a memo (US-D-04.005).
+ * A teardrop pin with its number, the tip at the bottom, as in the mock: orange for an ask, green for a point memo.
+ * memo adds a small white dot at its top right: the ask has a memo (US-D-04.005).
  */
-fun pinBitmap(number: Int, selected: Boolean, density: Float, memo: Boolean = false): Bitmap {
+fun pinBitmap(number: Int, selected: Boolean, density: Float, memo: Boolean = false, kind: PinKind = PinKind.ASK): Bitmap {
+  val fill = when {
+    selected -> PIN_SELECTED_COLOR
+    kind == PinKind.NOTE -> NOTE_PIN_COLOR
+    else -> PIN_COLOR
+  }
   val radius = (if (selected) 16f else 13f) * density
   val stroke = 2f * density
   val tail = radius * 0.8f
@@ -87,7 +94,7 @@ fun pinBitmap(number: Int, selected: Boolean, density: Float, memo: Boolean = fa
     lineTo(cx + radius * 0.6f, cy + radius * 0.7f)
     close()
   }
-  canvas.drawPath(shape, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = if (selected) PIN_SELECTED_COLOR else PIN_COLOR })
+  canvas.drawPath(shape, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = fill })
   canvas.drawPath(shape, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = android.graphics.Color.WHITE; style = Paint.Style.STROKE; strokeWidth = stroke })
   val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
     color = android.graphics.Color.WHITE
@@ -100,7 +107,7 @@ fun pinBitmap(number: Int, selected: Boolean, density: Float, memo: Boolean = fa
     val dot = radius * 0.32f
     val dx = cx + radius * 0.7f
     val dy = cy - radius * 0.7f
-    canvas.drawCircle(dx, dy, dot + stroke, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = if (selected) PIN_SELECTED_COLOR else PIN_COLOR })
+    canvas.drawCircle(dx, dy, dot + stroke, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = fill })
     canvas.drawCircle(dx, dy, dot, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = android.graphics.Color.WHITE })
   }
   return bitmap
@@ -152,8 +159,8 @@ private fun mapJson(data: MapData, selected: String?) = MapJson(routesJson(data)
 private fun draw(style: Style, data: MapData, json: MapJson, density: Float) {
   data.pins.forEach { pin ->
     listOf(false, true).forEach { sel ->
-      val name = pinIcon(pin.number, sel, pin.memo)
-      if (style.getImage(name) == null) style.addImage(name, pinBitmap(pin.number, sel, density, pin.memo))
+      val name = pinIcon(pin.number, sel, pin.memo, pin.kind)
+      if (style.getImage(name) == null) style.addImage(name, pinBitmap(pin.number, sel, density, pin.memo, pin.kind))
     }
   }
   style.getSourceAs<GeoJsonSource>("routes")?.setGeoJson(json.routes)
@@ -175,7 +182,7 @@ private fun fit(map: MapLibreMap, extent: List<LatLon>, padding: Int) {
 }
 
 /**
- * onPin gets the askId of a tapped pin, or null for a tap elsewhere. The camera takes in data once its first places
+ * onPin gets the id of a tapped pin (an askId or a noteId), or null for a tap elsewhere. The camera takes in data once its first places
  * arrive, and then stays where the rider moves it. onMap hands the map to the emulator tests once it has drawn.
  */
 @Composable
@@ -238,7 +245,7 @@ fun RouteMap(
               val point = map.projection.toScreenLocation(at)
               val reach = 20f * density
               val hit = map.queryRenderedFeatures(RectF(point.x - reach, point.y - reach, point.x + reach, point.y + reach), PINS_LAYER)
-              tapped(hit.firstOrNull()?.getStringProperty("askId"))
+              tapped(hit.firstOrNull()?.getStringProperty("id"))
               true
             }
             ready(map)
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
index 763a078..c4c7541 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
@@ -4,6 +4,9 @@ import com.touringproject.v2.ask.AskOutcome
 import com.touringproject.v2.ask.AskRecord
 import com.touringproject.v2.map.LatLon
 import com.touringproject.v2.map.MapPin
+import com.touringproject.v2.map.PinKind
+import com.touringproject.v2.records.NoteDraft
+import com.touringproject.v2.records.NoteRecord
 import com.touringproject.v2.records.RideListItem
 import com.touringproject.v2.records.SaveState
 import com.touringproject.v2.ride.EndReason
@@ -100,7 +103,10 @@ fun rideSections(items: List<RideListItem>, now: Long, zone: ZoneId): List<RideS
   return sections
 }
 
-/** SC-06's summary. pauses is null without one; autoEnded says the longest recording time ended the ride. */
+/**
+ * SC-06's summary. pauses is null without one; autoEnded says the longest recording time ended the ride; notes counts
+ * its point memos, null without one (the mock).
+ */
 data class RideSummaryUi(
   val date: String,
   val span: String,
@@ -109,9 +115,10 @@ data class RideSummaryUi(
   val questions: String,
   val pauses: String?,
   val autoEnded: Boolean,
+  val notes: String? = null,
 )
 
-fun rideSummary(ride: Ride, questions: Int, now: Long, zone: ZoneId) = RideSummaryUi(
+fun rideSummary(ride: Ride, questions: Int, now: Long, zone: ZoneId, notes: Int = 0) = RideSummaryUi(
   date = rideDateLabel(ride, now, zone),
   span = rideSpanLabel(ride, zone),
   elapsed = elapsedLabel(ride.recordedMs(now)),
@@ -119,6 +126,7 @@ fun rideSummary(ride: Ride, questions: Int, now: Long, zone: ZoneId) = RideSumma
   questions = questions.toString(),
   pauses = pausesLabel(ride.pauses()),
   autoEnded = ride.endReason == EndReason.AUTO,
+  notes = if (notes > 0) "📝 地点メモ ${notes}件" else null,
 )
 
 /** The asks in the order they were asked, numbered from 1: the numbers of the pins and the timeline. */
@@ -135,11 +143,36 @@ fun askPins(asks: List<AskRecord>): List<MapPin> {
   }
 }
 
+/** The point memos in the order they were opened, numbered from 1 apart from the asks (US-D-08). */
+fun noteNumbers(notes: List<NoteRecord>): Map<String, Int> =
+  notes.sortedBy { it.at }.mapIndexed { i, note -> note.id to i + 1 }.toMap()
+
+/** The ride's point memos that have a place, as green numbered pins. */
+fun notePins(notes: List<NoteRecord>): List<MapPin> {
+  val numbers = noteNumbers(notes)
+  return notes.sortedBy { it.at }.mapNotNull { note ->
+    val lat = note.latitude ?: return@mapNotNull null
+    val lon = note.longitude ?: return@mapNotNull null
+    MapPin(note.id, numbers.getValue(note.id), LatLon(lat, lon), kind = PinKind.NOTE)
+  }
+}
+
 private val PREFECTURE = Regex("^(東京都|北海道|(京都|大阪)府|.{2,3}県)")
 
 /** The mock's short place: the address without its prefecture; an address that starts otherwise is kept whole (Android #45). */
 fun shortPlace(address: String?): String = address?.replace(PREFECTURE, "")?.ifBlank { null } ?: "場所不明"
 
+/**
+ * Where a point memo is, in short: its address once the Backend has settled it. Until it has gone, the address is
+ * still to come; one that has gone without one could not be told (slice 3 spec §6.2).
+ */
+fun notePlace(note: NoteRecord): String = when {
+  note.latitude == null -> "位置の記録なし"
+  note.address != null -> shortPlace(note.address)
+  note.sent -> "場所不明"
+  else -> "住所は送信後"
+}
+
 /** What a list shows of an ask: what was heard, or why nothing was. */
 fun askText(ask: AskRecord): String = ask.transcript?.takeIf { it.isNotBlank() } ?: when {
   ask.outcome == AskOutcome.ANSWERED -> "（聞き取った文がありません）"
@@ -160,6 +193,8 @@ sealed interface TimelineRow {
     val failed: Boolean,
     val memo: Boolean = false,
   ) : TimelineRow
+  /** A point memo: its green number, when, where and the start of its text (the mock). */
+  data class Note(val noteId: String, val number: Int, val time: String, val place: String, val text: String) : TimelineRow
   data class Pause(val label: String) : TimelineRow
   data object NewConversation : TimelineRow
 }
@@ -172,22 +207,30 @@ fun pauseLabel(from: Long, to: Long, zone: ZoneId): String {
   return "⏸ 一時停止 ${TIME.format(a)}〜${dayLabel(b.toLocalDate(), weekday = false)} ${TIME.format(b)}"
 }
 
+/** order puts events of the same moment in a fixed order: a segment's start, then an ask, a point memo, a pause. */
 private sealed interface Event {
   val t: Long
-  data class AskAt(override val t: Long, val ask: AskRecord) : Event
-  data class PauseAt(override val t: Long, val until: Long?) : Event
+  val order: Int
+  /** Shows nothing of itself, but a day the ride started or resumed on gets its heading (Android #51). */
+  data class StartAt(override val t: Long, override val order: Int = 0) : Event
+  data class AskAt(override val t: Long, val ask: AskRecord, override val order: Int = 1) : Event
+  data class NoteAt(override val t: Long, val note: NoteRecord, override val order: Int = 2) : Event
+  data class PauseAt(override val t: Long, val until: Long?, override val order: Int = 3) : Event
 }
 
 /**
- * SC-06's timeline: the ride's asks, its pauses and the breaks between conversations, in time order. A ride over
- * more than one day gets a heading for each day (slice 2 spec §7.5). A paused ride ends with its pause so far.
+ * SC-06's timeline: the ride's asks, its point memos, its pauses and the breaks between conversations, in time order.
+ * A ride over more than one day gets a heading for each day, including a day it only resumed on (slice 2 spec §7.5,
+ * Android #51). A paused ride ends with its pause so far.
  */
-fun rideTimeline(ride: Ride, asks: List<AskRecord>, zone: ZoneId): List<TimelineRow> {
+fun rideTimeline(ride: Ride, asks: List<AskRecord>, zone: ZoneId, notes: List<NoteRecord> = emptyList()): List<TimelineRow> {
   val numbers = askNumbers(asks)
+  val noteNumbers = noteNumbers(notes)
+  val starts = ride.segments.map { Event.StartAt(it.startedAt) }
   val pauses = ride.segments.zipWithNext { a, b -> Event.PauseAt(a.endedAt ?: b.startedAt, b.startedAt) }
   val open = if (ride.status == RideStatus.PAUSED) listOfNotNull(ride.segments.last().endedAt?.let { Event.PauseAt(it, null) }) else emptyList()
-  // An ask comes before a pause that starts at the same moment.
-  val events = (asks.map { Event.AskAt(it.askedAt, it) } + pauses + open).sortedWith(compareBy<Event> { it.t }.thenBy { if (it is Event.AskAt) 0 else 1 })
+  val events = (starts + asks.map { Event.AskAt(it.askedAt, it) } + notes.map { Event.NoteAt(it.at, it) } + pauses + open)
+    .sortedWith(compareBy<Event> { it.t }.thenBy { it.order })
   // Every day the ride recorded on counts, not only the days with an ask or a pause (Android #41).
   val recorded = ride.segments.flatMap { listOfNotNull(it.startedAt, it.endedAt) }
   val days = (events.map { it.t } + recorded).map { at(it, zone).toLocalDate() }.toSet()
@@ -199,6 +242,11 @@ fun rideTimeline(ride: Ride, asks: List<AskRecord>, zone: ZoneId): List<Timeline
     if (days.size > 1 && date != day) rows += TimelineRow.Day(dayLabel(date))
     day = date
     when (event) {
+      is Event.StartAt -> Unit
+      is Event.NoteAt -> {
+        val note = event.note
+        rows += TimelineRow.Note(note.id, noteNumbers.getValue(note.id), TIME.format(at(note.at, zone)), notePlace(note), note.text)
+      }
       is Event.AskAt -> {
         val ask = event.ask
         if (ask.newConversation && asked) rows += TimelineRow.NewConversation
@@ -271,8 +319,11 @@ fun askDetail(asks: List<AskRecord>, askId: String, zone: ZoneId): AskDetailUi?
   )
 }
 
-/** The card of a tapped pin: 3 · 09:41 · 仙石原, then the question and the start of the answer. */
-data class PinCardUi(val askId: String, val heading: String, val question: String, val answer: String?)
+/**
+ * The card of a tapped pin: 3 · 09:41 · 仙石原, then the question and the start of the answer; for a point memo, its
+ * text. id is the askId or noteId the card opens.
+ */
+data class PinCardUi(val id: String, val heading: String, val question: String, val answer: String?, val kind: PinKind = PinKind.ASK)
 
 fun pinCard(asks: List<AskRecord>, askId: String, zone: ZoneId): PinCardUi? {
   val ask = asks.firstOrNull { it.askId == askId } ?: return null
@@ -280,6 +331,41 @@ fun pinCard(asks: List<AskRecord>, askId: String, zone: ZoneId): PinCardUi? {
   return PinCardUi(askId, "$number · ${TIME.format(at(ask.askedAt, zone))} · ${shortPlace(ask.address)}", askText(ask), ask.answer?.ifBlank { null })
 }
 
+/** A point memo's card: 2 · 10:24 · 新橋 · 📝 地点メモ, then its text (the mock). */
+fun noteCard(notes: List<NoteRecord>, noteId: String, zone: ZoneId): PinCardUi? {
+  val note = notes.firstOrNull { it.id == noteId } ?: return null
+  val number = noteNumbers(notes).getValue(noteId)
+  return PinCardUi(noteId, "$number · ${TIME.format(at(note.at, zone))} · ${notePlace(note)} · 📝 地点メモ", note.text, null, PinKind.NOTE)
+}
+
+/** SC-19's top: when, where and which ride the memo is in (slice 3 spec §7.3). */
+data class NoteHeaderUi(val time: String, val where: String, val ride: String)
+
+private const val NO_PLACE = "📍 位置を記録できませんでした"
+private const val ADDRESS_TO_COME = "📍 住所は送ったあとに付きます"
+
+/** A memo opened from Home: its address comes once it has been sent, as the Backend settles it (slice 3 spec §6.2). */
+fun newNoteHeader(draft: NoteDraft, rideName: String, zone: ZoneId): NoteHeaderUi {
+  val time = at(draft.at, zone)
+  return NoteHeaderUi(
+    "${dayLabel(time.toLocalDate())} ${TIME.format(time)} · 今いる地点",
+    if (draft.latitude == null) NO_PLACE else ADDRESS_TO_COME,
+    "走行「$rideName」に入ります",
+  )
+}
+
+/** A kept memo opened from SC-06. One that has gone without an address is one the Backend could not tell. */
+fun noteHeader(note: NoteRecord, rideName: String, zone: ZoneId): NoteHeaderUi {
+  val time = at(note.at, zone)
+  val where = when {
+    note.latitude == null -> NO_PLACE
+    note.address != null -> "📍 ${note.address}"
+    note.sent -> "📍 住所は分かりませんでした"
+    else -> ADDRESS_TO_COME
+  }
+  return NoteHeaderUi("${dayLabel(time.toLocalDate())} ${TIME.format(time)}", where, "走行「$rideName」で書いたメモ")
+}
+
 /** What SC-08 says it is writing for an ask: 会話 3 · 09:41 箱根町仙石原 (the mock). null when the ask is not among them. */
 fun askMemoTarget(asks: List<AskRecord>, askId: String, zone: ZoneId): String? {
   val ask = asks.firstOrNull { it.askId == askId } ?: return null
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
index 186de71..a5f3e60 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
@@ -50,7 +50,7 @@ fun rideDetailUi(ride: Ride, asks: List<AskRecord>, route: List<RoutePoint>, now
   recording = ride.status != RideStatus.ENDED,
   timeline = rideTimeline(ride, asks, zone),
   map = rideMap(route, ride.status == RideStatus.ENDED, askPins(asks)),
-  cards = asks.mapNotNull { pinCard(asks, it.askId, zone) }.associateBy { it.askId },
+  cards = asks.mapNotNull { pinCard(asks, it.askId, zone) }.associateBy { it.id },
   memo = ride.memo,
 )
 
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
index 16a0758..7424466 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
@@ -57,10 +57,12 @@ import kotlinx.coroutines.launch
 // SC-05, SC-06 and SC-07 (slice 2 spec §7.4–§7.6). The map comes in as a slot, so these screens are tested without
 // MapLibre, which needs a real device.
 
-/** Draws data; selected is the askId of the highlighted pin, and onPin gets a tapped pin's askId (null off the pins). */
+/** Draws data; selected is the id of the highlighted pin, and onPin gets a tapped pin's id (null off the pins). */
 typealias MapSlot = @Composable (data: MapData, selected: String?, onPin: (String?) -> Unit, modifier: Modifier) -> Unit
 
 private val Accent = Color(0xFFE8600F)
+// The mock's --memo: point memos are green, apart from the asks (US-D-08).
+private val Memo = Color(0xFF13804A)
 private val Rec = Color(0xFFD42A2A)
 
 @Composable
@@ -125,7 +127,8 @@ data class RideDetailUi(
 /**
  * SC-06. The map can fill the screen (onFullMap tells AppUi to hide the tabs), its pins can be hidden (showPins is
  * kept in the settings), and a tapped pin shows its card above the map's bottom edge. onRename says whether the new
- * name was saved; one that was not is told (Android #46). onMemo opens SC-08 for the ride's memo. An ended ride can be
+ * name was saved; one that was not is told (Android #46). onMemo opens SC-08 for the ride's memo, and onNote SC-19 for
+ * a point memo. An ended ride can be
  * deleted after DL-01; onDelete says whether it was (slice 3 spec §7.4), and AppUi then goes back to SC-05.
  */
 @Composable
@@ -141,6 +144,7 @@ fun RideDetailScreen(
   modifier: Modifier = Modifier,
   onMemo: () -> Unit = {},
   onDelete: suspend () -> Boolean = { false },
+  onNote: (String) -> Unit = {},
 ) {
   // Above the early return: a deletion in progress outlives the ride turning "not found" on screen (final review).
   val scope = rememberCoroutineScope()
@@ -175,7 +179,7 @@ fun RideDetailScreen(
         label = { Text("💬 質問") },
         modifier = Modifier.align(Alignment.TopEnd).padding(6.dp).testTag("pinToggle"),
       )
-      card?.let { PinCard(it, { onAsk(it.askId) }, Modifier.align(Alignment.BottomCenter).padding(8.dp)) }
+      card?.let { PinCard(it, { onAsk(it.id) }, Modifier.align(Alignment.BottomCenter).padding(8.dp)) }
     }
   }
   // The map keeps one place in the composition and only changes size, so full screen keeps the rider's pan and zoom.
@@ -211,7 +215,7 @@ fun RideDetailScreen(
         item { MemoBox("走行のメモ", ui.memo, "＋ 走行のメモ", onMemo, "rideMemo") }
         item { Muted("時系列", Modifier.padding(start = 16.dp, top = 12.dp, bottom = 4.dp)) }
         if (ui.timeline.isEmpty()) item { Muted("この走行の記録中にした質問はありません。", Modifier.padding(horizontal = 16.dp)) }
-        items(ui.timeline) { row -> TimelineItem(row, onAsk) }
+        items(ui.timeline) { row -> TimelineItem(row, onAsk, onNote) }
       }
     }
   }
@@ -310,8 +314,21 @@ private fun SummaryStat(value: String, label: String, modifier: Modifier = Modif
 }
 
 @Composable
-private fun TimelineItem(row: TimelineRow, onAsk: (String) -> Unit) {
+private fun TimelineItem(row: TimelineRow, onAsk: (String) -> Unit, onNote: (String) -> Unit) {
   when (row) {
+    is TimelineRow.Note -> Row(
+      Modifier.fillMaxWidth().clickable { onNote(row.noteId) }.padding(horizontal = 16.dp, vertical = 8.dp).testTag("note-${row.noteId}"),
+      horizontalArrangement = Arrangement.spacedBy(12.dp),
+      verticalAlignment = Alignment.CenterVertically,
+    ) {
+      Box(Modifier.size(28.dp).background(Memo, CircleShape), contentAlignment = Alignment.Center) {
+        Text(row.number.toString(), color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
+      }
+      Column(Modifier.weight(1f)) {
+        Muted("${row.time} · ${row.place} · 📝 地点メモ", size = 13)
+        Text(row.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
+      }
+    }
     is TimelineRow.Day -> Text(row.label, Modifier.padding(start = 16.dp, top = 12.dp, bottom = 4.dp), fontWeight = FontWeight.Bold)
     is TimelineRow.Pause -> Muted(row.label, Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
     TimelineRow.NewConversation -> Muted("↻ ここから新しい会話", Modifier.padding(horizontal = 16.dp, vertical = 6.dp), 13)
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t4.log 2>&1; tail -1 /tmp/trv2-t4.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト475件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/map/MapData.kt \
  app/src/main/java/com/touringproject/v2/map/RouteMap.kt \
  app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt \
  app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt \
  app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt \
  app/src/test/java/com/touringproject/v2/map/MapDataTest.kt \
  app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt \
  app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
git commit -m "feat: number point memos apart from the asks, mix them into the timeline and give each day the ride resumed on its heading (Android #51)"
```

---

### Task 5: SC-06: 地点メモのピンとカード・「💬 質問」「📝 地点メモ」の切り替え・#49

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `AppGraph.kt`・`map/MapData.kt`・`map/RouteMap.kt`・`settings/Settings.kt`・`ui/AppUi.kt`・`ui/RecordsRoutes.kt`・`ui/RecordsScreens.kt`
- Test: `map/MapDataTest.kt`・`settings/SettingsTest.kt`・`ui/AppUiTest.kt`・`ui/RecordLabelsTest.kt`・`ui/RecordsScreensTest.kt`・`app/src/androidTest/java/com/touringproject/v2/map/RouteMapTest.kt`

**Interfaces:**
- Consumes: Task 4 の `PinKind`・`notePins`・`noteCard`・`rideSummary(..., notes)`・Task 1 の `RoomRecords.notes`
- Produces:
  - `MapData.showing(asks: Boolean, notes: Boolean): MapData`
  - `Settings.showNotePins: Boolean = true`（保存の JSON に `showNotePins`）
  - `rideDetailUi(ride, asks, notes, route, now, zone)`・`RideDetailRoute(..., onNote: (String) -> Unit = {})`
  - `RideDetailScreen(..., showNotes: Boolean = true, onShowNotes: (Boolean) -> Unit = {})`（タグ `notePinToggle`）。地点メモのカードは `onNote` で開く
  - `AppGraph.recordsList: StateFlow<List<RideListItem>?>`（#49）

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/androidTest/java/com/touringproject/v2/map/RouteMapTest.kt b/app/src/androidTest/java/com/touringproject/v2/map/RouteMapTest.kt
index 1f80713..114cf6f 100644
--- a/app/src/androidTest/java/com/touringproject/v2/map/RouteMapTest.kt
+++ b/app/src/androidTest/java/com/touringproject/v2/map/RouteMapTest.kt
@@ -17,8 +17,8 @@ import org.junit.runner.RunWith
 import org.maplibre.android.geometry.LatLng
 import org.maplibre.android.maps.MapLibreMap
 
-// On the emulator: MapLibre draws the route and the numbered asks, and a tap on a pin names its ask
-// (slice 2 spec §9). The tiles need not load: the layers are drawn without them.
+// On the emulator: MapLibre draws the route, the numbered asks and the point memos, and a tap on a pin names its ask or
+// memo (slice 2 spec §9, slice 3 spec §7.6). The tiles need not load: the layers are drawn without them.
 @RunWith(AndroidJUnit4::class)
 class RouteMapTest {
   @get:Rule val rule = createComposeRule()
@@ -36,16 +36,18 @@ class RouteMapTest {
     RoutePoint(0, 0, 35.20, 139.00, 5.0), RoutePoint(0, 0, 35.22, 139.03, 5.0),
     RoutePoint(1, 0, 35.25, 139.06, 5.0), RoutePoint(1, 0, 35.28, 139.10, 5.0),
   )
-  private val pins = listOf(MapPin("a1", 1, LatLon(35.21, 139.01)), MapPin("a2", 2, LatLon(35.27, 139.09)))
+  private val pins = listOf(
+    MapPin("a1", 1, LatLon(35.21, 139.01)), MapPin("a2", 2, LatLon(35.27, 139.09)), MapPin("n1", 1, LatLon(35.235, 139.045), kind = PinKind.NOTE),
+  )
 
   @Test
-  fun the_route_and_the_pins_are_drawn_and_a_tap_on_a_pin_names_its_ask() {
+  fun the_route_and_the_pins_are_drawn_and_a_tap_on_a_pin_names_its_ask_or_memo() {
     var map: MapLibreMap? = null
     val tapped = mutableListOf<String?>()
     rule.setContent { RouteMap(rideMap(points, ended = true, pins = pins), null, { tapped += it }, Modifier.fillMaxSize(), onMap = { map = it }) }
     rule.waitUntil(30_000) { map != null }
     val everywhere = onMain { RectF(0f, 0f, map!!.width, map!!.height) }
-    rule.waitUntil(30_000) { onMain { map!!.queryRenderedFeatures(everywhere, PINS_LAYER).size } == 2 }
+    rule.waitUntil(30_000) { onMain { map!!.queryRenderedFeatures(everywhere, PINS_LAYER).size } == 3 }
     check(onMain { map!!.queryRenderedFeatures(everywhere, "routes").isNotEmpty() }) { "the route is not drawn" }
     check(onMain { map!!.queryRenderedFeatures(everywhere, "pauses").isNotEmpty() }) { "the pause is not drawn" }
     // The pin stands on its place: tap its head, above the tip.
@@ -54,6 +56,9 @@ class RouteMapTest {
     rule.onRoot().performTouchInput { click(Offset(tip.x, tip.y - 16 * density)) }
     rule.waitUntil(10_000) { tapped.isNotEmpty() }
     check(tapped.last() == "a2") { "tapped ${tapped.last()}" }
+    val memo = onMain { map!!.projection.toScreenLocation(LatLng(35.235, 139.045)) }
+    rule.onRoot().performTouchInput { click(Offset(memo.x, memo.y - 16 * density)) }
+    rule.waitUntil(10_000) { tapped.last() == "n1" }
   }
 
   // Final review: a tap while the map is still being drawn must not ask for rendered features (MapLibre would crash).
diff --git a/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt b/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt
index a207071..ea37df9 100644
--- a/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt
+++ b/app/src/test/java/com/touringproject/v2/map/MapDataTest.kt
@@ -79,4 +79,16 @@ class MapDataTest {
     assertEquals(listOf("a1" to "pin-1", "n1" to "note-1"), properties(null))
     assertEquals(listOf("a1" to "pin-1", "n1" to "note-sel-1"), properties("n1"))
   }
+
+  // SC-06: the asks' and the point memos' pins are shown or hidden apart; with both hidden only the route is left.
+  @Test
+  fun each_kind_of_pin_is_shown_or_hidden_on_its_own() {
+    val map = rideMap(points, ended = true, pins = listOf(MapPin("a1", 1, LatLon(35.0, 139.0)), MapPin("n1", 1, LatLon(35.1, 139.1), kind = PinKind.NOTE)))
+    assertEquals(listOf("a1", "n1"), map.showing(asks = true, notes = true).pins.map { it.id })
+    assertEquals(listOf("n1"), map.showing(asks = false, notes = true).pins.map { it.id })
+    assertEquals(listOf("a1"), map.showing(asks = true, notes = false).pins.map { it.id })
+    val bare = map.showing(asks = false, notes = false)
+    assertEquals(emptyList<MapPin>(), bare.pins)
+    assertEquals(map.routes, bare.routes)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
index 11a608b..fbf5dbc 100644
--- a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
@@ -39,14 +39,14 @@ class SettingsTest {
   fun saved_settings_round_trip() = runTest {
     val store = FakeStore()
     val repo = SettingsRepository(store)
-    val s = Settings("rider01", returnEnabled = false, returnApp = maps, returnTiming = ReturnTiming.SPOKEN, recentApps = listOf(maps), answerVolumeDb = 3, maxRecordingHours = 6, showAskPins = false)
+    val s = Settings("rider01", returnEnabled = false, returnApp = maps, returnTiming = ReturnTiming.SPOKEN, recentApps = listOf(maps), answerVolumeDb = 3, maxRecordingHours = 6, showAskPins = false, showNotePins = false)
     repo.update(s)
     assertEquals(s, SettingsRepository(store).load())
   }
 
   @Test
   fun broken_values_fall_back_to_defaults() {
-    val raw = """{"userName":"NO","returnEnabled":"yes","returnApp":{"packageName":1},"returnTiming":"later","recentApps":[{"packageName":"a","label":"A"},3],"answerVolumeDb":12,"maxRecordingHours":72,"showAskPins":"no"}"""
+    val raw = """{"userName":"NO","returnEnabled":"yes","returnApp":{"packageName":1},"returnTiming":"later","recentApps":[{"packageName":"a","label":"A"},3],"answerVolumeDb":12,"maxRecordingHours":72,"showAskPins":"no","showNotePins":0}"""
     val (s, needsSave) = decodeSettings(raw, Random(2))
     assertTrue(needsSave)
     assertTrue(s.returnEnabled)
@@ -56,6 +56,13 @@ class SettingsTest {
     assertEquals(DEFAULT_VOLUME_DB, s.answerVolumeDb)
     assertEquals(DEFAULT_MAX_RECORDING_HOURS, s.maxRecordingHours)
     assertTrue(s.showAskPins)
+    assertTrue(s.showNotePins)
+  }
+
+  // Settings saved before slice 3 have no choice for the point memos' pins: they are shown.
+  @Test
+  fun the_point_memos_pins_are_shown_until_hidden() {
+    assertTrue(decodeSettings("""{"userName":"rider01","showAskPins":false}""").first.showNotePins)
   }
 
   @Test
diff --git a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
index 3f7395b..2fbaad5 100644
--- a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
@@ -47,7 +47,10 @@ class AppUiTest {
   fun the_records_tab_lists_the_kept_rides_and_home_keeps_its_place() {
     val graph = (rule.activity.application as TouringApp).graph
     rule.onNodeWithTag("tab-RECORDS").performClick()
-    rule.onNodeWithText("まだ走行の記録がありません。ホームの「▶ 走行を開始」で記録します。").assertExists()
+    // The list is read off the main thread and shared by AppGraph (Android #49): it comes a moment later.
+    rule.waitUntil(5_000) {
+      rule.onAllNodes(androidx.compose.ui.test.hasText("まだ走行の記録がありません。ホームの「▶ 走行を開始」で記録します。")).fetchSemanticsNodes().isNotEmpty()
+    }
     val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(5_000, EndReason.MANUAL, 5_000)
     runBlocking { graph.rideStore.save(ride) }
     rule.waitUntil(5_000) { rule.onAllNodesWithTagExists("ride-r1") }
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
index 514113c..861bf85 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
@@ -14,6 +14,7 @@ import com.touringproject.v2.ride.end
 import com.touringproject.v2.ride.newRide
 import com.touringproject.v2.ride.pause
 import com.touringproject.v2.ride.resume
+import com.touringproject.v2.ride.RoutePoint
 import org.junit.Assert.assertEquals
 import org.junit.Assert.assertNull
 import org.junit.Test
@@ -247,4 +248,16 @@ class RecordLabelsTest {
     assertEquals("📝 地点メモ 2件", rideSummary(ride, 4, ms(17, 0, 0), zone, notes = 2).notes)
     assertNull(rideSummary(ride, 4, ms(17, 0, 0), zone).notes)
   }
+
+  // SC-06 puts the asks' and the point memos' pins on one map, and a tap on either opens its own card.
+  @Test
+  fun the_detail_has_the_pins_and_the_cards_of_both_asks_and_point_memos() {
+    val asks = listOf(ask("a1", ms(16, 9, 41)))
+    val notes = listOf(note("n1", ms(16, 9, 50)))
+    val ui = rideDetailUi(ride, asks, notes, listOf(RoutePoint(0, ms(16, 9, 0), 35.2, 139.0, 5.0)), ms(17, 0, 0), zone)
+    assertEquals(listOf("a1" to PinKind.ASK, "n1" to PinKind.NOTE), ui.map.pins.map { it.id to it.kind })
+    assertEquals(PinKind.NOTE, ui.cards.getValue("n1").kind)
+    assertEquals("📝 地点メモ 1件", ui.summary.notes)
+    assertEquals(1, ui.timeline.filterIsInstance<TimelineRow.Note>().size)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
index 5e9a4fd..894be01 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
@@ -30,6 +30,7 @@ import androidx.test.ext.junit.runners.AndroidJUnit4
 import com.touringproject.v2.map.LatLon
 import com.touringproject.v2.map.MapData
 import com.touringproject.v2.map.MapPin
+import com.touringproject.v2.map.PinKind
 import org.junit.Assert.assertEquals
 import org.junit.Rule
 import org.junit.Test
@@ -364,4 +365,47 @@ class RecordsScreensTest {
     rule.onNodeWithTag("note-n1").performClick()
     assertEquals(listOf("n1"), opened)
   }
+
+  private fun withNote() = detail().let { d ->
+    d.copy(
+      map = d.map.copy(pins = d.map.pins + MapPin("n1", 1, LatLon(35.25, 138.95), kind = PinKind.NOTE)),
+      cards = d.cards + ("n1" to PinCardUi("n1", "1 · 09:50 · 御殿場市新橋 · 📝 地点メモ", "展望スペース", null, PinKind.NOTE)),
+      summary = d.summary.copy(notes = "📝 地点メモ 1件"),
+    )
+  }
+
+  // US-D-08: a point memo's green pin shows its card, and the card opens SC-19.
+  @Test
+  fun a_point_memos_pin_shows_its_card_which_opens_the_memo() {
+    val opened = mutableListOf<String>()
+    val asked = mutableListOf<String>()
+    rule.setContent { RideDetailScreen(withNote(), fakeMap, true, {}, {}, { asked += it }, { true }, {}, onNote = { opened += it }) }
+    rule.onNodeWithText("📝 地点メモ 1件").assertExists()
+    rule.onNodeWithTag("pin-n1").performClick()
+    rule.onNodeWithText("展望スペース").assertExists()
+    rule.onNodeWithText("開く ›").assertExists()
+    rule.onNodeWithTag("pinCard").performClick()
+    assertEquals(listOf("n1"), opened)
+    assertEquals(emptyList<String>(), asked)
+  }
+
+  // US-D-02: "💬 質問" and "📝 地点メモ" show or hide their own pins; each choice goes to the settings.
+  @Test
+  fun the_asks_and_the_point_memos_pins_are_shown_or_hidden_apart() {
+    var asks by mutableStateOf(true)
+    var notes by mutableStateOf(true)
+    rule.setContent {
+      RideDetailScreen(withNote(), fakeMap, asks, { asks = it }, {}, {}, { true }, {}, showNotes = notes, onShowNotes = { notes = it })
+    }
+    rule.onNodeWithTag("mapState").assertTextEquals("pins 3 selected null")
+    rule.onNodeWithTag("pin-n1").performClick()
+    rule.onNodeWithTag("notePinToggle").performClick()
+    rule.onNodeWithTag("mapState").assertTextEquals("pins 2 selected null")
+    rule.onNodeWithTag("pinCard").assertDoesNotExist()
+    rule.onNodeWithTag("pinToggle").performClick()
+    rule.onNodeWithTag("mapState").assertTextEquals("pins 0 selected null")
+    // The timeline is shown whatever the map shows.
+    rule.onNodeWithTag("timeline").performScrollToNode(hasTestTag("ask-a1"))
+    assertEquals(false to false, asks to notes)
+  }
 }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SettingsTest' --tests '*MapDataTest' --tests '*RecordLabelsTest' --tests '*RecordsScreensTest' --tests '*AppUiTest' > /tmp/trv2-t5.log 2>&1; grep -c '^e: ' /tmp/trv2-t5.log
```

Expected: `BUILD FAILED`。まだ無い `showNotePins`・`showing`・`rideDetailUi` の `notes`・`showNotes` を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index e32909b..4ce4331 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -34,6 +34,7 @@ import com.touringproject.v2.recordings.TRIAL_IDLE
 import com.touringproject.v2.recordings.TrialController
 import com.touringproject.v2.recordings.TrialDeps
 import com.touringproject.v2.recordings.TrialState
+import com.touringproject.v2.records.RideListItem
 import com.touringproject.v2.records.activeAskCount
 import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.RideController
@@ -93,6 +94,12 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   val askLog = RoomAskLog(database.asks(), scope) { message, e -> Log.w("trv2.ask", message, e) }
   /** What the Records tab reads (SC-05, SC-06, SC-07). */
   val records = RoomRecords(database.rides(), database.asks(), database.notes())
+
+  /**
+   * SC-05's list, shared so that coming back from a ride shows the list it left at once (Android #49). It is read only
+   * while the list is shown and for 5 s after: Room runs the query again for every route point (Android #42).
+   */
+  val recordsList: StateFlow<List<RideListItem>?> = records.list.stateIn(scope, SharingStarted.WhileSubscribed(5_000), null)
   private val notices = RideNotices(context)
 
   /** Sends rides, routes, memos, point memos and deletions; a pass runs on each trigger (slice 2 spec §5.3). */
diff --git a/app/src/main/java/com/touringproject/v2/map/MapData.kt b/app/src/main/java/com/touringproject/v2/map/MapData.kt
index 58090aa..780c76c 100644
--- a/app/src/main/java/com/touringproject/v2/map/MapData.kt
+++ b/app/src/main/java/com/touringproject/v2/map/MapData.kt
@@ -37,6 +37,10 @@ data class MapData(
 ) {
   /** Everything the camera should take in when the map opens. */
   val extent: List<LatLon> get() = focus?.let { listOf(it) } ?: (routes.flatten() + pins.map { it.at })
+
+  /** SC-06's switches: the asks' and the point memos' pins shown or hidden apart; with both hidden only the route is left. */
+  fun showing(asks: Boolean, notes: Boolean): MapData =
+    copy(pins = pins.filter { if (it.kind == PinKind.NOTE) notes else asks })
 }
 
 fun rideMap(points: List<RoutePoint>, ended: Boolean, pins: List<MapPin>, faint: Boolean = false, focus: LatLon? = null): MapData {
diff --git a/app/src/main/java/com/touringproject/v2/map/RouteMap.kt b/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
index 435f09c..0dc09f4 100644
--- a/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
+++ b/app/src/main/java/com/touringproject/v2/map/RouteMap.kt
@@ -151,22 +151,25 @@ private fun addLayers(style: Style, faint: Boolean, dark: Boolean) {
   )
 }
 
-/** The GeoJSON of each source, made off the main thread (Android #42). */
-private class MapJson(val routes: String, val pauses: String, val ends: String, val pins: String)
+/** The GeoJSON of the route's sources, made off the main thread (Android #42). The pins are made apart (Android #49). */
+private class RouteJson(val routes: String, val pauses: String, val ends: String)
 
-private fun mapJson(data: MapData, selected: String?) = MapJson(routesJson(data), pausesJson(data), endsJson(data), pinsJson(data, selected))
+private fun routeJson(data: MapData) = RouteJson(routesJson(data), pausesJson(data), endsJson(data))
 
-private fun draw(style: Style, data: MapData, json: MapJson, density: Float) {
+private fun drawRoute(style: Style, json: RouteJson) {
+  style.getSourceAs<GeoJsonSource>("routes")?.setGeoJson(json.routes)
+  style.getSourceAs<GeoJsonSource>("pauses")?.setGeoJson(json.pauses)
+  style.getSourceAs<GeoJsonSource>("ends")?.setGeoJson(json.ends)
+}
+
+private fun drawPins(style: Style, data: MapData, json: String, density: Float) {
   data.pins.forEach { pin ->
     listOf(false, true).forEach { sel ->
       val name = pinIcon(pin.number, sel, pin.memo, pin.kind)
       if (style.getImage(name) == null) style.addImage(name, pinBitmap(pin.number, sel, density, pin.memo, pin.kind))
     }
   }
-  style.getSourceAs<GeoJsonSource>("routes")?.setGeoJson(json.routes)
-  style.getSourceAs<GeoJsonSource>("pauses")?.setGeoJson(json.pauses)
-  style.getSourceAs<GeoJsonSource>("ends")?.setGeoJson(json.ends)
-  style.getSourceAs<GeoJsonSource>(PINS_LAYER)?.setGeoJson(json.pins)
+  style.getSourceAs<GeoJsonSource>(PINS_LAYER)?.setGeoJson(json)
 }
 
 /** Takes in the whole route and every pin; a single place is shown close up (slice 2 spec §7.5). */
@@ -254,12 +257,12 @@ fun RouteMap(
       }
     }
   }
-  LaunchedEffect(loaded, data, selected) {
+  LaunchedEffect(loaded, data) {
     val (map, style) = loaded ?: return@LaunchedEffect
-    val json = withContext(Dispatchers.Default) { mapJson(data, selected) }
+    val json = withContext(Dispatchers.Default) { routeJson(data) }
     // MapLibre is touched only on the UI thread; where the effect resumes is not left to chance.
     withContext(Dispatchers.Main) {
-      draw(style, data, json, density)
+      drawRoute(style, json)
       // Until the first places arrive the map shows Japan, and the camera fits again once they do.
       if (!fitted) {
         fit(map, data.extent, (48 * density).toInt())
@@ -267,6 +270,12 @@ fun RouteMap(
       }
     }
   }
+  // Selecting a pin makes only the pins again, not the route of tens of thousands of points (Android #49).
+  LaunchedEffect(loaded, data, selected) {
+    val (_, style) = loaded ?: return@LaunchedEffect
+    val json = withContext(Dispatchers.Default) { pinsJson(data, selected) }
+    withContext(Dispatchers.Main) { drawPins(style, data, json, density) }
+  }
   Box(modifier) {
     AndroidView({ view }, Modifier.matchParentSize())
     val uri = LocalUriHandler.current
diff --git a/app/src/main/java/com/touringproject/v2/settings/Settings.kt b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
index 63d9f12..cbb440c 100644
--- a/app/src/main/java/com/touringproject/v2/settings/Settings.kt
+++ b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
@@ -40,6 +40,8 @@ data class Settings(
   val maxRecordingHours: Int = DEFAULT_MAX_RECORDING_HOURS,
   /** SC-06: whether the map shows the asks' pins; kept for the next time a ride is opened (slice 2 spec §7.5). */
   val showAskPins: Boolean = true,
+  /** SC-06: whether the map shows the point memos' pins, kept like showAskPins (slice 3 spec §7.6). */
+  val showNotePins: Boolean = true,
 )
 
 /**
@@ -74,6 +76,7 @@ fun decodeSettings(raw: String?, random: Random = Random.Default): Pair<Settings
     maxRecordingHours = runCatching { obj["maxRecordingHours"]?.jsonPrimitive?.intOrNull }.getOrNull()
       ?.takeIf { it in MAX_RECORDING_HOURS_CHOICES } ?: DEFAULT_MAX_RECORDING_HOURS,
     showAskPins = runCatching { obj["showAskPins"]?.jsonPrimitive?.booleanOrNull }.getOrNull() ?: true,
+    showNotePins = runCatching { obj["showNotePins"]?.jsonPrimitive?.booleanOrNull }.getOrNull() ?: true,
   )
   return settings to (savedName == null)
 }
@@ -89,6 +92,7 @@ fun encodeSettings(settings: Settings): String = json.encodeToString(
     answerVolumeDb = settings.answerVolumeDb,
     maxRecordingHours = settings.maxRecordingHours,
     showAskPins = settings.showAskPins,
+    showNotePins = settings.showNotePins,
   ),
 )
 
@@ -102,6 +106,7 @@ private data class SavedSettings(
   val answerVolumeDb: Int,
   val maxRecordingHours: Int,
   val showAskPins: Boolean,
+  val showNotePins: Boolean,
 )
 
 fun withRecentApp(recent: List<LaunchableApp>, app: LaunchableApp, max: Int = 5): List<LaunchableApp> =
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 40bcfab..d28768d 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -155,8 +155,7 @@ fun AppUi(graph: AppGraph) {
                 )
               }
               entry<RecordsKey> {
-                // Read only while the list is shown: Room runs the query again for every route point (Android #42).
-                val rideList by graph.records.list.collectAsStateWithLifecycle(null)
+                val rideList by graph.recordsList.collectAsStateWithLifecycle()
                 RideListScreen(
                   rideList?.let { rideSections(it, System.currentTimeMillis(), ZoneId.systemDefault()) },
                   onRide = { tabs.push(RideKey(it)) },
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
index a5f3e60..f2816e5 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
@@ -12,6 +12,7 @@ import com.touringproject.v2.map.MapPin
 import com.touringproject.v2.map.RouteMap
 import com.touringproject.v2.map.rideMap
 import com.touringproject.v2.records.AskEdits
+import com.touringproject.v2.records.NoteRecord
 import com.touringproject.v2.ride.Ride
 import com.touringproject.v2.ride.RideController
 import com.touringproject.v2.ride.RideStatus
@@ -40,17 +41,22 @@ private fun readRide(records: RoomRecords, rideId: String): Read<Ride?>? =
 private fun readAsks(records: RoomRecords, rideId: String): List<AskRecord>? =
   remember(rideId) { records.asks(rideId) }.collectAsStateWithLifecycle(null).value
 
+@Composable
+private fun readNotes(records: RoomRecords, rideId: String): List<NoteRecord>? =
+  remember(rideId) { records.notes(rideId) }.collectAsStateWithLifecycle(null).value
+
 @Composable
 private fun readRoute(records: RoomRecords, rideId: String): List<RoutePoint>? =
   produceState<List<RoutePoint>?>(null, rideId) { value = records.route(rideId) }.value
 
-fun rideDetailUi(ride: Ride, asks: List<AskRecord>, route: List<RoutePoint>, now: Long, zone: ZoneId) = RideDetailUi(
+/** The asks' and the point memos' cards share one map: their ids are UUIDs, so they never meet. */
+fun rideDetailUi(ride: Ride, asks: List<AskRecord>, notes: List<NoteRecord>, route: List<RoutePoint>, now: Long, zone: ZoneId) = RideDetailUi(
   name = ride.name,
-  summary = rideSummary(ride, asks.size, now, zone),
+  summary = rideSummary(ride, asks.size, now, zone, notes.size),
   recording = ride.status != RideStatus.ENDED,
-  timeline = rideTimeline(ride, asks, zone),
-  map = rideMap(route, ride.status == RideStatus.ENDED, askPins(asks)),
-  cards = asks.mapNotNull { pinCard(asks, it.askId, zone) }.associateBy { it.id },
+  timeline = rideTimeline(ride, asks, zone, notes),
+  map = rideMap(route, ride.status == RideStatus.ENDED, askPins(asks) + notePins(notes)),
+  cards = (asks.mapNotNull { pinCard(asks, it.askId, zone) } + notes.mapNotNull { noteCard(notes, it.id, zone) }).associateBy { it.id },
   memo = ride.memo,
 )
 
@@ -66,13 +72,15 @@ fun RideDetailRoute(
   onFullMap: (Boolean) -> Unit,
   onMemo: () -> Unit,
   modifier: Modifier = Modifier,
+  onNote: (String) -> Unit = {},
 ) {
   val ride = readRide(records, rideId) ?: return
   val asks = readAsks(records, rideId) ?: return
+  val notes = readNotes(records, rideId) ?: return
   val route = readRoute(records, rideId) ?: return
   // A long ride has tens of thousands of points: the map's data is made off the main thread (Android #42).
-  val ui = produceState<Read<RideDetailUi?>?>(null, ride, asks, route) {
-    value = Read(withContext(Dispatchers.Default) { ride.value?.let { rideDetailUi(it, asks, route, System.currentTimeMillis(), ZoneId.systemDefault()) } })
+  val ui = produceState<Read<RideDetailUi?>?>(null, ride, asks, notes, route) {
+    value = Read(withContext(Dispatchers.Default) { ride.value?.let { rideDetailUi(it, asks, notes, route, System.currentTimeMillis(), ZoneId.systemDefault()) } })
   }.value ?: return
   RideDetailScreen(
     ui.value, routeMap,
@@ -85,6 +93,9 @@ fun RideDetailRoute(
     modifier = modifier,
     onMemo = onMemo,
     onDelete = { rides.delete(rideId).also { if (it) onBack() } },
+    onNote = onNote,
+    showNotes = settings.showNotePins,
+    onShowNotes = { updateSettings(settings.copy(showNotePins = it)) },
   )
 }
 
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
index 7424466..02c6171 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
@@ -50,6 +50,7 @@ import androidx.compose.ui.text.style.TextOverflow
 import androidx.compose.ui.unit.dp
 import androidx.compose.ui.unit.sp
 import com.touringproject.v2.map.MapData
+import com.touringproject.v2.map.PinKind
 import com.touringproject.v2.ride.cutRideName
 import com.touringproject.v2.ride.rideName
 import kotlinx.coroutines.launch
@@ -125,11 +126,11 @@ data class RideDetailUi(
 )
 
 /**
- * SC-06. The map can fill the screen (onFullMap tells AppUi to hide the tabs), its pins can be hidden (showPins is
- * kept in the settings), and a tapped pin shows its card above the map's bottom edge. onRename says whether the new
- * name was saved; one that was not is told (Android #46). onMemo opens SC-08 for the ride's memo, and onNote SC-19 for
- * a point memo. An ended ride can be
- * deleted after DL-01; onDelete says whether it was (slice 3 spec §7.4), and AppUi then goes back to SC-05.
+ * SC-06. The map can fill the screen (onFullMap tells AppUi to hide the tabs), the asks' and the point memos' pins can
+ * be hidden apart (showPins and showNotes are kept in the settings), and a tapped pin shows its card above the map's
+ * bottom edge. onRename says whether the new name was saved; one that was not is told (Android #46). onMemo opens SC-08
+ * for the ride's memo, and onNote SC-19 for a point memo. An ended ride can be deleted after DL-01; onDelete says
+ * whether it was (slice 3 spec §7.4), and AppUi then goes back to SC-05.
  */
 @Composable
 fun RideDetailScreen(
@@ -145,6 +146,8 @@ fun RideDetailScreen(
   onMemo: () -> Unit = {},
   onDelete: suspend () -> Boolean = { false },
   onNote: (String) -> Unit = {},
+  showNotes: Boolean = true,
+  onShowNotes: (Boolean) -> Unit = {},
 ) {
   // Above the early return: a deletion in progress outlives the ride turning "not found" on screen (final review).
   val scope = rememberCoroutineScope()
@@ -164,22 +167,24 @@ fun RideDetailScreen(
   LaunchedEffect(full) { onFullMap(full) }
   DisposableEffect(Unit) { onDispose { onFullMap(false) } }
   BackHandler(enabled = full) { full = false }
-  val shown = if (showPins) ui.map else ui.map.copy(pins = emptyList())
-  val card = selected?.takeIf { showPins }?.let { ui.cards[it] }
+  val shown = ui.map.showing(asks = showPins, notes = showNotes)
+  // A card goes with its pin when that kind is hidden.
+  val visible = selected?.takeIf { id -> shown.pins.any { it.id == id } }
+  val card = visible?.let { ui.cards[it] }
   val mapArea: @Composable (Modifier) -> Unit = { area ->
     Box(area) {
-      map(shown, selected.takeIf { showPins }, { selected = it }, Modifier.fillMaxSize())
+      map(shown, visible, { selected = it }, Modifier.fillMaxSize())
       TextButton(
         onClick = { full = !full },
         modifier = Modifier.align(Alignment.TopStart).padding(6.dp).background(MaterialTheme.colorScheme.surface, RoundedCornerShape(8.dp)).testTag("fullMap"),
       ) { Text(if (full) "✕" else "⛶", fontSize = 18.sp) }
-      FilterChip(
-        selected = showPins,
-        onClick = { onShowPins(!showPins) },
-        label = { Text("💬 質問") },
-        modifier = Modifier.align(Alignment.TopEnd).padding(6.dp).testTag("pinToggle"),
-      )
-      card?.let { PinCard(it, { onAsk(it.id) }, Modifier.align(Alignment.BottomCenter).padding(8.dp)) }
+      Row(Modifier.align(Alignment.TopEnd).padding(6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
+        FilterChip(selected = showPins, onClick = { onShowPins(!showPins) }, label = { Text("💬 質問") }, modifier = Modifier.testTag("pinToggle"))
+        FilterChip(selected = showNotes, onClick = { onShowNotes(!showNotes) }, label = { Text("📝 地点メモ") }, modifier = Modifier.testTag("notePinToggle"))
+      }
+      card?.let {
+        PinCard(it, { if (it.kind == PinKind.NOTE) onNote(it.id) else onAsk(it.id) }, Modifier.align(Alignment.BottomCenter).padding(8.dp))
+      }
     }
   }
   // The map keeps one place in the composition and only changes size, so full screen keeps the rider's pan and zoom.
@@ -214,7 +219,7 @@ fun RideDetailScreen(
         item { Summary(ui.summary, ui.recording) }
         item { MemoBox("走行のメモ", ui.memo, "＋ 走行のメモ", onMemo, "rideMemo") }
         item { Muted("時系列", Modifier.padding(start = 16.dp, top = 12.dp, bottom = 4.dp)) }
-        if (ui.timeline.isEmpty()) item { Muted("この走行の記録中にした質問はありません。", Modifier.padding(horizontal = 16.dp)) }
+        if (ui.timeline.isEmpty()) item { Muted("この走行の記録中にした質問と地点メモはありません。", Modifier.padding(horizontal = 16.dp)) }
         items(ui.timeline) { row -> TimelineItem(row, onAsk, onNote) }
       }
     }
@@ -280,9 +285,10 @@ private fun PinCard(card: PinCardUi, onOpen: () -> Unit, modifier: Modifier = Mo
       .padding(12.dp).testTag("pinCard"),
   ) {
     Muted(card.heading, size = 13)
-    Text(card.question, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
+    val note = card.kind == PinKind.NOTE
+    Text(card.question, fontWeight = if (note) FontWeight.Normal else FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
     card.answer?.let { Text(it, maxLines = 2, overflow = TextOverflow.Ellipsis, fontSize = 14.sp) }
-    Text("詳しく見る ›", color = Accent, fontWeight = FontWeight.Bold, fontSize = 14.sp)
+    Text(if (note) "開く ›" else "詳しく見る ›", color = if (note) Memo else Accent, fontWeight = FontWeight.Bold, fontSize = 14.sp)
   }
 }
 
@@ -300,6 +306,7 @@ private fun Summary(summary: RideSummaryUi, recording: Boolean) {
       SummaryStat(summary.questions, "質問", Modifier.testTag("summaryQuestions"))
     }
     summary.pauses?.let { Muted(it) }
+    summary.notes?.let { Muted(it) }
     if (summary.autoEnded) Text("最長時間に達したため、自動で終了しました", color = Rec, fontSize = 14.sp, modifier = Modifier.testTag("autoEnded"))
     if (recording) Muted("記録中の走行です。ルートは開いたときまでのものです。")
   }
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t5.log 2>&1; tail -1 /tmp/trv2-t5.log
cd $AND && ./gradlew compileDebugAndroidTestKotlin -q
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト480件）。エミュレーターのテストはコンパイルだけ確かめ、走らせるのは Task 9。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt \
  app/src/main/java/com/touringproject/v2/map/MapData.kt \
  app/src/main/java/com/touringproject/v2/map/RouteMap.kt \
  app/src/main/java/com/touringproject/v2/settings/Settings.kt \
  app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt \
  app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt \
  app/src/test/java/com/touringproject/v2/map/MapDataTest.kt \
  app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt \
  app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt \
  app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt \
  app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt \
  app/src/androidTest/java/com/touringproject/v2/map/RouteMapTest.kt
git commit -m "feat: show the point memos' green pins and cards on SC-06 with a switch of their own, and redraw only the pins on a tap (Android #49)"
```

---

### Task 6: SC-19 の画面・SC-08 との共通の編集部品・#55・DL-01 の地点メモ

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `store/RoomAskLog.kt`・`ui/DeleteDialog.kt`・`ui/MemoScreen.kt`・`ui/NoteScreen.kt`（新規）
- Test: `ui/MemoScreenTest.kt`・`ui/NoteScreenTest.kt`（新規）

**Interfaces:**
- Consumes: Task 4 の `NoteHeaderUi`・`cutMemo`・`memoText`・`MEMO_MAX`・`DeleteDialog`
- Produces:
  - `MemoEditor(title, initial, placeholder, onSave: suspend (String?) -> Boolean, onClose, modifier, canSave = { true }, saveColor: Color? = null, header = {}, footer = {})`（タグは SC-08 と同じ `memoClose`・`memoSave`・`memoInput`・`memoCount`・`memoDiscard`）。`MemoScreen` はこの上に作り直す（引数は今のまま）
  - `NoteScreen(header: NoteHeaderUi, initial: String?, onSave: suspend (String) -> Boolean, onClose, modifier, onDelete: (suspend () -> Boolean)? = null)`（タグ `noteTime`・`notePlace`・`noteRide`・`deleteNote`）
  - `DeleteKind.NOTE`

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/MemoScreenTest.kt b/app/src/test/java/com/touringproject/v2/ui/MemoScreenTest.kt
index b8ab41e..e05fcf4 100644
--- a/app/src/test/java/com/touringproject/v2/ui/MemoScreenTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/MemoScreenTest.kt
@@ -1,12 +1,16 @@
 package com.touringproject.v2.ui
 
 import androidx.activity.ComponentActivity
+import androidx.compose.ui.semantics.SemanticsProperties
+import androidx.compose.ui.test.SemanticsMatcher
+import androidx.compose.ui.test.assert
 import androidx.compose.ui.test.assertTextEquals
 import androidx.compose.ui.test.junit4.createAndroidComposeRule
 import androidx.compose.ui.test.onNodeWithTag
 import androidx.compose.ui.test.onNodeWithText
 import androidx.compose.ui.test.performClick
 import androidx.compose.ui.test.performTextReplacement
+import androidx.compose.ui.text.TextRange
 import androidx.test.ext.junit.runners.AndroidJUnit4
 import kotlinx.coroutines.CompletableDeferred
 import org.junit.Assert.assertEquals
@@ -103,4 +107,27 @@ class MemoScreenTest {
     rule.waitForIdle()
     assertEquals(listOf<String?>("一度だけ"), saved)
   }
+
+  // Android #55: while the save runs, ✕ and Back do nothing, so the screen under SC-08 is never closed with it.
+  @Test
+  fun closing_while_the_save_runs_does_nothing() {
+    val gate = CompletableDeferred<Boolean>()
+    rule.setContent { MemoScreen("走行のメモ", null, { saved += it; gate.await() }, { closed++ }) }
+    rule.onNodeWithTag("memoInput").performTextReplacement("一度だけ")
+    rule.onNodeWithTag("memoSave").performClick()
+    rule.onNodeWithTag("memoClose").performClick()
+    back()
+    rule.waitForIdle()
+    rule.onNodeWithText("変更を破棄しますか？").assertDoesNotExist()
+    gate.complete(true)
+    rule.waitForIdle()
+    assertEquals(1, closed)
+  }
+
+  // Android #55: a kept memo opens with the cursor at its end, ready to write on.
+  @Test
+  fun a_kept_memo_opens_with_the_cursor_at_its_end() {
+    show(initial = "前のメモ")
+    rule.onNodeWithTag("memoInput").assert(SemanticsMatcher.expectValue(SemanticsProperties.TextSelectionRange, TextRange(4)))
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt b/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
new file mode 100644
index 0000000..e92e329
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
@@ -0,0 +1,117 @@
+package com.touringproject.v2.ui
+
+import androidx.activity.ComponentActivity
+import androidx.compose.ui.test.assertIsEnabled
+import androidx.compose.ui.test.assertIsNotEnabled
+import androidx.compose.ui.test.assertTextEquals
+import androidx.compose.ui.test.junit4.createAndroidComposeRule
+import androidx.compose.ui.test.onNodeWithTag
+import androidx.compose.ui.test.onNodeWithText
+import androidx.compose.ui.test.performClick
+import androidx.compose.ui.test.performTextReplacement
+import androidx.test.ext.junit.runners.AndroidJUnit4
+import org.junit.Assert.assertEquals
+import org.junit.Rule
+import org.junit.Test
+import org.junit.runner.RunWith
+import org.robolectric.shadows.ShadowToast
+
+// SC-19 with text only (slice 3 spec §7.3); voice input comes with plan 4.
+@RunWith(AndroidJUnit4::class)
+class NoteScreenTest {
+  @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()
+
+  private val header = NoteHeaderUi("10月22日（木） 10:24 · 今いる地点", "📍 住所は送ったあとに付きます", "走行「箱根」に入ります")
+  private val saved = mutableListOf<String>()
+  private var closed = 0
+  private var deletes = 0
+
+  private fun show(initial: String? = null, result: Boolean = true, deleted: Boolean? = null) = rule.setContent {
+    NoteScreen(header, initial, { saved += it; result }, { closed++ }, onDelete = deleted?.let { d -> { deletes++; d } })
+  }
+
+  @Test
+  fun the_top_says_when_where_and_for_which_ride_and_there_is_no_voice_input_yet() {
+    show()
+    rule.onNodeWithTag("noteTime").assertTextEquals("10月22日（木） 10:24 · 今いる地点")
+    rule.onNodeWithTag("notePlace").assertTextEquals("📍 住所は送ったあとに付きます")
+    rule.onNodeWithTag("noteRide").assertTextEquals("走行「箱根」に入ります")
+    rule.onNodeWithText("🎤 声で入力").assertDoesNotExist()
+  }
+
+  // SC-19: an empty memo cannot be saved.
+  @Test
+  fun an_empty_memo_cannot_be_saved_and_a_written_one_is_saved_trimmed() {
+    show()
+    rule.onNodeWithTag("memoSave").assertIsNotEnabled()
+    rule.onNodeWithTag("memoInput").performTextReplacement("  ")
+    rule.onNodeWithTag("memoSave").assertIsNotEnabled()
+    rule.onNodeWithTag("memoInput").performTextReplacement(" 展望スペース ")
+    rule.onNodeWithTag("memoSave").assertIsEnabled().performClick()
+    rule.waitForIdle()
+    assertEquals(listOf("展望スペース"), saved)
+    assertEquals(1, closed)
+  }
+
+  @Test
+  fun the_field_keeps_2000_characters() {
+    show()
+    rule.onNodeWithTag("memoInput").performTextReplacement("あ".repeat(2100))
+    rule.onNodeWithTag("memoCount").assertTextEquals("2000 / 2000字")
+  }
+
+  @Test
+  fun closing_with_a_change_asks_first() {
+    show(initial = "前のメモ", deleted = true)
+    rule.onNodeWithTag("memoInput").performTextReplacement("書きかけ")
+    rule.onNodeWithTag("memoClose").performClick()
+    rule.onNodeWithText("変更を破棄しますか？").assertExists()
+    rule.onNodeWithTag("memoDiscard").performClick()
+    assertEquals(1, closed)
+    assertEquals(emptyList<String>(), saved)
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
+  }
+
+  // A memo opened from Home is not kept yet, so there is nothing to delete.
+  @Test
+  fun a_new_memo_has_no_delete() {
+    show()
+    rule.onNodeWithTag("deleteNote").assertDoesNotExist()
+  }
+
+  // DL-01: a kept memo is deleted after the confirmation, and the screen goes back to where it was opened from.
+  @Test
+  fun a_kept_memo_is_deleted_after_the_confirmation() {
+    show(initial = "消すメモ", deleted = true)
+    rule.onNodeWithTag("deleteNote").performClick()
+    rule.onNodeWithText("この地点メモを削除しますか？").assertExists()
+    rule.onNodeWithText("メモが削除されます。元に戻せません。").assertExists()
+    rule.onNodeWithTag("deleteCancel").performClick()
+    assertEquals(0, deletes)
+    rule.onNodeWithTag("deleteNote").performClick()
+    rule.onNodeWithTag("deleteGo").performClick()
+    rule.waitForIdle()
+    assertEquals(1, deletes)
+    assertEquals(1, closed)
+  }
+
+  @Test
+  fun a_memo_that_could_not_be_deleted_is_told_and_stays() {
+    show(initial = "消えないメモ", deleted = false)
+    rule.onNodeWithTag("deleteNote").performClick()
+    rule.onNodeWithTag("deleteGo").performClick()
+    rule.waitForIdle()
+    assertEquals(0, closed)
+    assertEquals("削除できませんでした", ShadowToast.getTextOfLatestToast())
+  }
+}
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*MemoScreenTest' --tests '*NoteScreenTest' > /tmp/trv2-t6.log 2>&1; grep -c '^e: ' /tmp/trv2-t6.log
```

Expected: `BUILD FAILED`。まだ無い `NoteScreen`・`NoteHeaderUi` を受ける画面を使うので、コンパイルで落ちる（`MemoScreenTest` の2件も、今の SC-08 では落ちる）。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
index f4026b6..90b2924 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
@@ -10,6 +10,10 @@ import kotlinx.coroutines.flow.StateFlow
 import kotlinx.coroutines.flow.asStateFlow
 import kotlinx.coroutines.launch
 
+/**
+ * The memo is not copied: the loop writes an ask once, at its end, and SC-08 changes its memo apart (AskDao.writeMemo),
+ * so the row starts without one (Android #55).
+ */
 fun AskRecord.toEntity() = AskEntity(
   askId = askId,
   askedAt = askedAt,
diff --git a/app/src/main/java/com/touringproject/v2/ui/DeleteDialog.kt b/app/src/main/java/com/touringproject/v2/ui/DeleteDialog.kt
index e54034b..141e6a4 100644
--- a/app/src/main/java/com/touringproject/v2/ui/DeleteDialog.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/DeleteDialog.kt
@@ -11,15 +11,16 @@ import androidx.compose.ui.text.font.FontWeight
 
 private val Danger = Color(0xFFD42A2A)
 
-/** DL-01's wording for what SC-06 and SC-07 delete (the mock's table). */
+/** DL-01's wording for what SC-06, SC-07 and SC-19 delete (the mock's table). */
 enum class DeleteKind(val title: String, val text: String) {
   ASK("この会話を削除しますか？", "質問・回答・メモが削除されます。元に戻せません。"),
   RIDE("この走行を削除しますか？", "ルート・走行のメモと、その走行の質問・地点メモが削除されます。元に戻せません。"),
+  NOTE("この地点メモを削除しますか？", "メモが削除されます。元に戻せません。"),
 }
 
 /**
- * DL-01, the one confirmation before anything is deleted (recordings, the connection key, an ask, a ride). "やめる" is
- * on the left and the red delete on the right (the mock).
+ * DL-01, the one confirmation before anything is deleted (recordings, the connection key, an ask, a ride, a point
+ * memo). "やめる" is on the left and the red delete on the right (the mock).
  */
 @Composable
 fun DeleteDialog(title: String, text: String?, confirm: String, onConfirm: () -> Unit, onDismiss: () -> Unit) {
diff --git a/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt b/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
index cae0cad..93e87a8 100644
--- a/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt
@@ -4,12 +4,14 @@ import android.widget.Toast
 import androidx.activity.compose.BackHandler
 import androidx.compose.foundation.layout.Arrangement
 import androidx.compose.foundation.layout.Column
+import androidx.compose.foundation.layout.ColumnScope
 import androidx.compose.foundation.layout.Row
 import androidx.compose.foundation.layout.fillMaxSize
 import androidx.compose.foundation.layout.fillMaxWidth
 import androidx.compose.foundation.layout.padding
 import androidx.compose.material3.AlertDialog
 import androidx.compose.material3.Button
+import androidx.compose.material3.ButtonDefaults
 import androidx.compose.material3.MaterialTheme
 import androidx.compose.material3.OutlinedTextField
 import androidx.compose.material3.Text
@@ -26,9 +28,12 @@ import androidx.compose.ui.Alignment
 import androidx.compose.ui.Modifier
 import androidx.compose.ui.focus.FocusRequester
 import androidx.compose.ui.focus.focusRequester
+import androidx.compose.ui.graphics.Color
 import androidx.compose.ui.platform.LocalContext
 import androidx.compose.ui.platform.testTag
+import androidx.compose.ui.text.TextRange
 import androidx.compose.ui.text.font.FontWeight
+import androidx.compose.ui.text.input.TextFieldValue
 import androidx.compose.ui.unit.dp
 import androidx.compose.ui.unit.sp
 import com.touringproject.v2.records.MEMO_MAX
@@ -37,51 +42,75 @@ import com.touringproject.v2.records.memoText
 import kotlinx.coroutines.launch
 
 /**
- * SC-08 (slice 3 spec §7.2). target says what the memo is for (会話 3 · 09:41 箱根町仙石原, 走行のメモ); initial is the
- * memo kept now. onSave gets the cleaned memo, or null to remove it, and says whether it was written: a memo that was
- * not is told and the screen stays, so nothing typed is lost (spec §8). ✕ and Back ask before throwing a change away.
+ * What SC-08 and SC-19 share: ✕, the title and 保存 on top, header under them, the field with its count, and footer
+ * below. initial is the text kept now; onSave gets the cleaned text (memoText: null when blank) and says whether it was
+ * written: a text that was not is told and the screen stays, so nothing typed is lost (slice 3 spec §8). canSave says
+ * whether a cleaned text may be saved. ✕ and Back ask before throwing a change away. While a save runs, 保存, ✕ and
+ * Back take nothing, so the screen is closed once (Android #55). The field opens with the cursor at the end.
  */
 @Composable
-fun MemoScreen(target: String, initial: String?, onSave: suspend (String?) -> Boolean, onClose: () -> Unit, modifier: Modifier = Modifier) {
-  var input by rememberSaveable { mutableStateOf(initial ?: "") }
+fun MemoEditor(
+  title: String,
+  initial: String?,
+  placeholder: String,
+  onSave: suspend (String?) -> Boolean,
+  onClose: () -> Unit,
+  modifier: Modifier = Modifier,
+  canSave: (String?) -> Boolean = { true },
+  saveColor: Color? = null,
+  header: @Composable () -> Unit = {},
+  footer: @Composable ColumnScope.() -> Unit = {},
+) {
+  var field by rememberSaveable(stateSaver = TextFieldValue.Saver) {
+    mutableStateOf((initial ?: "").let { TextFieldValue(it, TextRange(it.length)) })
+  }
   var discarding by rememberSaveable { mutableStateOf(false) }
   var saving by remember { mutableStateOf(false) }
-  val changed = memoText(input) != initial
+  val clean = memoText(field.text)
+  val changed = clean != initial
   val scope = rememberCoroutineScope()
   val context = LocalContext.current
   val focus = remember { FocusRequester() }
   LaunchedEffect(Unit) { focus.requestFocus() }
-  val close = { if (changed) discarding = true else onClose() }
+  val close = {
+    if (!saving) {
+      if (changed) discarding = true else onClose()
+    }
+  }
   BackHandler(onBack = close)
   Column(modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
     Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
       TextButton(onClick = close, modifier = Modifier.testTag("memoClose")) { Text("✕", fontSize = 22.sp) }
-      Text("メモ", Modifier.weight(1f), fontSize = 20.sp, fontWeight = FontWeight.Bold)
+      Text(title, Modifier.weight(1f), fontSize = 20.sp, fontWeight = FontWeight.Bold)
       Button(
         onClick = {
+          // Two presses in one frame both get here before the button is redrawn as disabled (Android #55).
+          if (saving) return@Button
           saving = true
           scope.launch {
-            if (onSave(memoText(input))) onClose() else Toast.makeText(context, "保存できませんでした", Toast.LENGTH_SHORT).show()
+            if (onSave(clean)) onClose() else Toast.makeText(context, "保存できませんでした", Toast.LENGTH_SHORT).show()
             saving = false
           }
         },
-        enabled = !saving,
+        enabled = !saving && canSave(clean),
+        colors = saveColor?.let { ButtonDefaults.buttonColors(containerColor = it, contentColor = Color.White) } ?: ButtonDefaults.buttonColors(),
         modifier = Modifier.testTag("memoSave"),
       ) { Text("保存") }
     }
-    Text(target, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, modifier = Modifier.testTag("memoTarget"))
+    header()
     OutlinedTextField(
-      input,
-      { input = cutMemo(it) },
+      field,
+      { field = it.copy(text = cutMemo(it.text)) },
       Modifier.fillMaxWidth().weight(1f).focusRequester(focus).testTag("memoInput"),
-      placeholder = { Text("感じたこと、また行きたい場所など") },
+      placeholder = { Text(placeholder) },
     )
     Text(
-      "${input.codePointCount(0, input.length)} / ${MEMO_MAX}字",
+      "${field.text.codePointCount(0, field.text.length)} / ${MEMO_MAX}字",
       Modifier.align(Alignment.End).testTag("memoCount"),
       color = MaterialTheme.colorScheme.onSurfaceVariant,
       fontSize = 13.sp,
     )
+    footer()
   }
   if (discarding) {
     AlertDialog(
@@ -94,3 +123,13 @@ fun MemoScreen(target: String, initial: String?, onSave: suspend (String?) -> Bo
     )
   }
 }
+
+/**
+ * SC-08 (slice 3 spec §7.2). target says what the memo is for (会話 3 · 09:41 箱根町仙石原, 走行のメモ); initial is the
+ * memo kept now. onSave gets the cleaned memo, or null to remove it (saving an empty memo removes it).
+ */
+@Composable
+fun MemoScreen(target: String, initial: String?, onSave: suspend (String?) -> Boolean, onClose: () -> Unit, modifier: Modifier = Modifier) =
+  MemoEditor("メモ", initial, "感じたこと、また行きたい場所など", onSave, onClose, modifier, header = {
+    Text(target, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, modifier = Modifier.testTag("memoTarget"))
+  })
diff --git a/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt b/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt
new file mode 100644
index 0000000..f7ee606
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt
@@ -0,0 +1,83 @@
+package com.touringproject.v2.ui
+
+import android.widget.Toast
+import androidx.compose.foundation.BorderStroke
+import androidx.compose.foundation.background
+import androidx.compose.foundation.layout.Arrangement
+import androidx.compose.foundation.layout.Column
+import androidx.compose.foundation.layout.fillMaxWidth
+import androidx.compose.foundation.layout.padding
+import androidx.compose.foundation.shape.RoundedCornerShape
+import androidx.compose.material3.MaterialTheme
+import androidx.compose.material3.OutlinedButton
+import androidx.compose.material3.Text
+import androidx.compose.runtime.Composable
+import androidx.compose.runtime.getValue
+import androidx.compose.runtime.mutableStateOf
+import androidx.compose.runtime.rememberCoroutineScope
+import androidx.compose.runtime.saveable.rememberSaveable
+import androidx.compose.runtime.setValue
+import androidx.compose.ui.Modifier
+import androidx.compose.ui.graphics.Color
+import androidx.compose.ui.platform.LocalContext
+import androidx.compose.ui.platform.testTag
+import androidx.compose.ui.text.font.FontWeight
+import androidx.compose.ui.unit.dp
+import androidx.compose.ui.unit.sp
+import kotlinx.coroutines.launch
+
+// The mock's --memo and --danger.
+private val Memo = Color(0xFF13804A)
+private val Danger = Color(0xFFD42A2A)
+
+/**
+ * SC-19 (slice 3 spec §7.3), with text only: voice input comes with plan 4. header says when, where and for which ride
+ * the memo is; initial is its text kept now (null for one opened from Home). An empty memo cannot be saved. onDelete is
+ * given for a kept memo: "この地点メモを削除" asks first (DL-01), and once the memo is deleted the screen closes, back to
+ * where it was opened from.
+ */
+@Composable
+fun NoteScreen(
+  header: NoteHeaderUi,
+  initial: String?,
+  onSave: suspend (String) -> Boolean,
+  onClose: () -> Unit,
+  modifier: Modifier = Modifier,
+  onDelete: (suspend () -> Boolean)? = null,
+) {
+  var deleting by rememberSaveable { mutableStateOf(false) }
+  val scope = rememberCoroutineScope()
+  val context = LocalContext.current
+  MemoEditor(
+    "地点メモ", initial, "気づいたこと、また来たい理由など", { text -> text != null && onSave(text) }, onClose, modifier,
+    canSave = { it != null },
+    saveColor = Memo,
+    header = {
+      Column(
+        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp)).padding(horizontal = 14.dp, vertical = 10.dp),
+        verticalArrangement = Arrangement.spacedBy(2.dp),
+      ) {
+        Text(header.time, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp, modifier = Modifier.testTag("noteTime"))
+        Text(header.where, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("notePlace"))
+        Text(header.ride, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp, modifier = Modifier.testTag("noteRide"))
+      }
+    },
+    footer = {
+      if (onDelete != null) {
+        OutlinedButton(onClick = { deleting = true }, modifier = Modifier.fillMaxWidth().testTag("deleteNote"), border = BorderStroke(1.dp, Danger)) {
+          Text("この地点メモを削除", color = Danger, fontWeight = FontWeight.Bold)
+        }
+      }
+    },
+  )
+  if (deleting && onDelete != null) {
+    DeleteDialog(
+      DeleteKind.NOTE,
+      onConfirm = {
+        deleting = false
+        scope.launch { if (onDelete()) onClose() else Toast.makeText(context, "削除できませんでした", Toast.LENGTH_SHORT).show() }
+      },
+      onDismiss = { deleting = false },
+    )
+  }
+}
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t6.log 2>&1; tail -1 /tmp/trv2-t6.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト490件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt \
  app/src/main/java/com/touringproject/v2/ui/DeleteDialog.kt \
  app/src/main/java/com/touringproject/v2/ui/MemoScreen.kt \
  app/src/main/java/com/touringproject/v2/ui/NoteScreen.kt \
  app/src/test/java/com/touringproject/v2/ui/MemoScreenTest.kt \
  app/src/test/java/com/touringproject/v2/ui/NoteScreenTest.kt
git commit -m "feat: write point memos on SC-19 on the editor SC-08 shares, which a save in progress keeps from closing twice (Android #55)"
```

---

### Task 7: つなぎ: ホームの「📝 地点メモ」・SC-19 の入口と戻り先

**Files:**（`app/src/main/java/com/touringproject/v2/`・`app/src/test/java/com/touringproject/v2/` から）
- Modify / Create: `AppGraph.kt`・`records/Notes.kt`・`ui/AppUi.kt`・`ui/HomeScreen.kt`・`ui/RecordsRoutes.kt`
- Test: `ui/NoteRoutesTest.kt`（新規）・`ui/ScreensTest.kt`

**Interfaces:**
- Consumes: Task 1 の `NoteEdits`・`RoomNotes`・`NoteDraft`・Task 4 の `newNoteHeader`・`noteHeader`・Task 6 の `NoteScreen`・Task 5 の `RideDetailRoute(onNote)`
- Produces:
  - `HomeScreen(..., onNote: (() -> Unit)? = null)`（タグ `newNote`。null のときは出さない）
  - `NoteDraft` は `@Serializable`
  - `NewNoteRoute(records, notes: NoteEdits, draft, onClose, modifier)`・`NoteRoute(records, notes, rideId, noteId, onClose, modifier)`（`ui/RecordsRoutes.kt`）
  - `NewNoteKey(draft: NoteDraft)`・`NoteKey(rideId, noteId)`（どちらもタブの帯を隠す）
  - `AppGraph.notes: RoomNotes`

- [ ] **Step 1: 落ちるテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt b/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
new file mode 100644
index 0000000..3f8b650
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
@@ -0,0 +1,77 @@
+package com.touringproject.v2.ui
+
+import android.app.Application
+import androidx.activity.ComponentActivity
+import androidx.compose.ui.test.assertTextEquals
+import androidx.compose.ui.test.junit4.createAndroidComposeRule
+import androidx.compose.ui.test.onNodeWithTag
+import androidx.compose.ui.test.performClick
+import androidx.compose.ui.test.performTextReplacement
+import androidx.room.Room
+import androidx.test.core.app.ApplicationProvider
+import androidx.test.ext.junit.runners.AndroidJUnit4
+import com.touringproject.v2.records.NoteDraft
+import com.touringproject.v2.ride.HOUR_MS
+import com.touringproject.v2.ride.newRide
+import com.touringproject.v2.store.RideDatabase
+import com.touringproject.v2.store.RoomNotes
+import com.touringproject.v2.store.RoomRecords
+import com.touringproject.v2.store.RoomRideStore
+import kotlinx.coroutines.runBlocking
+import org.junit.After
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertNull
+import org.junit.Rule
+import org.junit.Test
+import org.junit.runner.RunWith
+
+// SC-19 on the device's records: a memo from Home is kept for its ride, and one from SC-06 is changed or deleted.
+@RunWith(AndroidJUnit4::class)
+class NoteRoutesTest {
+  @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()
+
+  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
+    .allowMainThreadQueries()
+    .build()
+  private val records = RoomRecords(db.rides(), db.asks(), db.notes())
+  private val notes = RoomNotes(db.notes(), db.rides(), { 5_000 }, { "n1" }, {}) { _, _ -> }
+  private var closed = 0
+  private val draft = NoteDraft("n1", "r1", 4_000, 35.3, 138.9, null, null, null)
+
+  @After
+  fun close() = db.close()
+
+  private fun keepRide() = runBlocking { RoomRideStore(db.rides()).save(newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)) }
+
+  private fun waitFor(tag: String) = rule.waitUntil(5_000) {
+    rule.onAllNodes(androidx.compose.ui.test.hasTestTag(tag)).fetchSemanticsNodes().isNotEmpty()
+  }
+
+  @Test
+  fun a_memo_from_home_is_kept_for_its_ride() {
+    keepRide()
+    rule.setContent { NewNoteRoute(records, notes, draft, onClose = { closed++ }) }
+    waitFor("noteRide")
+    rule.onNodeWithTag("noteRide").assertTextEquals("走行「箱根」に入ります")
+    rule.onNodeWithTag("memoInput").performTextReplacement("展望スペース")
+    rule.onNodeWithTag("memoSave").performClick()
+    rule.waitUntil(5_000) { closed == 1 }
+    assertEquals("展望スペース", runBlocking { db.notes().note("n1")?.text })
+  }
+
+  // The memo turns "not kept" on screen as soon as it is deleted; the screen still closes, once.
+  @Test
+  fun a_kept_memo_is_changed_or_deleted_and_the_screen_closes_once() {
+    keepRide()
+    runBlocking { notes.create(draft, "前のメモ") }
+    rule.setContent { NoteRoute(records, notes, "r1", "n1", onClose = { closed++ }) }
+    waitFor("noteRide")
+    rule.onNodeWithTag("noteRide").assertTextEquals("走行「箱根」で書いたメモ")
+    rule.onNodeWithTag("deleteNote").performClick()
+    rule.onNodeWithTag("deleteGo").performClick()
+    rule.waitUntil(5_000) { closed == 1 }
+    rule.waitForIdle()
+    assertEquals(1, closed)
+    assertNull(runBlocking { db.notes().note("n1") })
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index 143c8e8..725f6f7 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -56,6 +56,18 @@ class HomeScreenTest {
     rule.onNodeWithTag("askHint").assertTextEquals("再開すると、インカムのボタンで話せます")
   }
 
+  // Slice 3 spec §7.1: "📝 地点メモ" is there only while a ride records or is paused, and opens SC-19 at once.
+  @Test
+  fun the_point_memo_button_is_there_only_while_a_ride_records_or_is_paused() {
+    var notes = 0
+    var riding by mutableStateOf(false)
+    rule.setContent { HomeScreen(HomeUi("rider01", null, "新しい会話です"), {}, {}, {}, {}, onNote = if (riding) ({ notes++ }) else null) }
+    rule.onNodeWithTag("newNote").assertDoesNotExist()
+    riding = true
+    rule.onNodeWithTag("newNote").performClick()
+    assertEquals(1, notes)
+  }
+
   @Test
   fun while_a_ride_records_the_hint_says_the_intercom_is_ready() {
     rule.setContent { HomeScreen(HomeUi("rider01", null, "新しい会話です"), {}, {}, {}, {}) }
PATCH
````

- [ ] **Step 2: 落ちることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ScreensTest' --tests '*NoteRoutesTest' > /tmp/trv2-t7.log 2>&1; grep -c '^e: ' /tmp/trv2-t7.log
```

Expected: `BUILD FAILED`。まだ無い `HomeScreen` の `onNote`・`NewNoteRoute`・`NoteRoute` を使うので、コンパイルで落ちる。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 4ce4331..18bd73f 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -53,6 +53,7 @@ import com.touringproject.v2.settings.maxRecordingChanges
 import com.touringproject.v2.store.RideDatabase
 import com.touringproject.v2.store.RoomAskEdits
 import com.touringproject.v2.store.RoomAskLog
+import com.touringproject.v2.store.RoomNotes
 import com.touringproject.v2.store.RoomRecords
 import com.touringproject.v2.store.RoomRideStore
 import com.touringproject.v2.store.RoomSyncStore
@@ -116,6 +117,11 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   /** SC-07 and SC-08 change kept asks through here; each change is something new to send (slice 3 spec §5.1). */
   val askEdits = RoomAskEdits(database.asks(), System::currentTimeMillis, sync::request) { message, e -> Log.w("trv2.ask", message, e) }
 
+  /** SC-19 writes point memos through here; each change is something new to send (slice 3 spec §5.1). */
+  val notes = RoomNotes(database.notes(), database.rides(), System::currentTimeMillis, { UUID.randomUUID().toString() }, sync::request) { message, e ->
+    Log.w("trv2.note", message, e)
+  }
+
   val rides = RideController(
     RideDeps(
       now = System::currentTimeMillis,
diff --git a/app/src/main/java/com/touringproject/v2/records/Notes.kt b/app/src/main/java/com/touringproject/v2/records/Notes.kt
index f9303ab..b65757a 100644
--- a/app/src/main/java/com/touringproject/v2/records/Notes.kt
+++ b/app/src/main/java/com/touringproject/v2/records/Notes.kt
@@ -3,6 +3,7 @@ package com.touringproject.v2.records
 import com.touringproject.v2.location.Fix
 import com.touringproject.v2.location.pickHeadingSample
 import com.touringproject.v2.ride.RoutePoint
+import kotlinx.serialization.Serializable
 import java.time.Instant
 
 // Point memos (US-D-08, SC-19). One is written while a ride records or is paused, at the place the ride has reached,
@@ -26,8 +27,10 @@ data class NoteRecord(
 
 /**
  * A point memo opened from Home and not yet saved: when it was opened and where the ride was then, with the older
- * point the Backend works the heading out from (slice 3 spec §4.3). Nothing is written until it is saved.
+ * point the Backend works the heading out from (slice 3 spec §4.3). Nothing is written until it is saved. Serializable:
+ * SC-19 keeps it in its key, so the memo stays where it was opened when the activity is recreated.
  */
+@Serializable
 data class NoteDraft(
   val id: String,
   val rideId: String,
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index d28768d..f967d46 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -37,6 +37,7 @@ import com.touringproject.v2.AppGraph
 import com.touringproject.v2.BuildConfig
 import com.touringproject.v2.api.ApiClient
 import com.touringproject.v2.ask.isBusy
+import com.touringproject.v2.records.NoteDraft
 import com.touringproject.v2.settings.LaunchableApp
 import kotlinx.coroutines.delay
 import kotlinx.coroutines.launch
@@ -56,9 +57,12 @@ import kotlinx.serialization.Serializable
 @Serializable data class AskKey(val rideId: String, val askId: String) : NavKey
 @Serializable data class RideMemoKey(val rideId: String) : NavKey
 @Serializable data class AskMemoKey(val rideId: String, val askId: String) : NavKey
+/** SC-19 opened from Home; the draft says where and when, so it stays the same when the activity is recreated. */
+@Serializable data class NewNoteKey(val draft: NoteDraft) : NavKey
+@Serializable data class NoteKey(val rideId: String, val noteId: String) : NavKey
 
-/** SC-08 covers the tabs, as the mock draws it. */
-private fun coversTabs(key: NavKey?) = key is RideMemoKey || key is AskMemoKey
+/** SC-08 and SC-19 cover the tabs, as the mock draws them. */
+private fun coversTabs(key: NavKey?) = key is RideMemoKey || key is AskMemoKey || key is NewNoteKey || key is NoteKey
 
 private enum class RideSheet { START, END }
 
@@ -152,6 +156,15 @@ fun AppUi(graph: AppGraph) {
                       onMemo = { ride?.let { tabs.push(RideMemoKey(it.id)) } },
                     )
                   },
+                  // The place is read when the button is pressed (slice 3 spec §4.3); a second press while it is read adds nothing.
+                  onNote = ride?.let { active ->
+                    {
+                      scope.launch {
+                        val draft = graph.notes.draft(active.id)
+                        if (tabs.current.lastOrNull() !is NewNoteKey) tabs.push(NewNoteKey(draft))
+                      }
+                    }
+                  },
                 )
               }
               entry<RecordsKey> {
@@ -172,6 +185,7 @@ fun AppUi(graph: AppGraph) {
                   onFullMap = { mapFull = it },
                   onMemo = { tabs.push(RideMemoKey(key.rideId)) },
                   modifier = Modifier.safeDrawingPadding(),
+                  onNote = { tabs.push(NoteKey(key.rideId, it)) },
                 )
               }
               entry<AskKey> { key ->
@@ -190,6 +204,12 @@ fun AppUi(graph: AppGraph) {
               entry<AskMemoKey> { key ->
                 AskMemoRoute(graph.records, graph.askEdits, key.rideId, key.askId, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding())
               }
+              entry<NewNoteKey> { key ->
+                NewNoteRoute(graph.records, graph.notes, key.draft, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding())
+              }
+              entry<NoteKey> { key ->
+                NoteRoute(graph.records, graph.notes, key.rideId, key.noteId, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding())
+              }
               entry<SettingsKey> {
                 SettingsScreen(
                   current, apiKey,
diff --git a/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt b/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
index e325983..72bb128 100644
--- a/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt
@@ -7,10 +7,13 @@ import androidx.compose.foundation.layout.Column
 import androidx.compose.foundation.layout.Row
 import androidx.compose.foundation.layout.fillMaxSize
 import androidx.compose.foundation.layout.fillMaxWidth
+import androidx.compose.foundation.layout.PaddingValues
 import androidx.compose.foundation.layout.heightIn
 import androidx.compose.foundation.layout.padding
 import androidx.compose.foundation.shape.RoundedCornerShape
 import androidx.compose.material3.AlertDialog
+import androidx.compose.material3.Button
+import androidx.compose.material3.ButtonDefaults
 import androidx.compose.material3.MaterialTheme
 import androidx.compose.material3.OutlinedButton
 import androidx.compose.material3.Text
@@ -78,7 +81,11 @@ fun WarningBand(text: String, onClick: (() -> Unit)?, onClose: (() -> Unit)?, mo
   }
 }
 
-// SC-02 (slice 1 minimum). Glanced at while riding: it never scrolls.
+/**
+ * SC-02 (slice 1 minimum). Glanced at while riding: it never scrolls. onNote is set while a ride records or is paused:
+ * "📝 地点メモ" then stands at the right of the intercom's line and opens SC-19 at once (slice 3 spec §7.1; the mock puts
+ * it on the card of the heading, which this screen does not have yet).
+ */
 @Composable
 fun HomeScreen(
   ui: HomeUi,
@@ -89,6 +96,7 @@ fun HomeScreen(
   modifier: Modifier = Modifier,
   onDismissVolume: () -> Unit = {},
   ride: @Composable () -> Unit = {},
+  onNote: (() -> Unit)? = null,
 ) {
   var confirming by remember { mutableStateOf(false) }
   Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
@@ -102,12 +110,22 @@ fun HomeScreen(
       WarningBand(banner.text, if (banner.leads) ({ onBanner(banner) }) else null, if (low) onDismissVolume else null, Modifier.testTag("banner"))
     }
     ride()
-    Text(
-      ui.askHint ?: "インカムのボタンで話せます",
-      Modifier.testTag("askHint"),
-      color = if (ui.askHint == null) Color(0xFF13804A) else MaterialTheme.colorScheme.onSurfaceVariant,
-      fontSize = 16.sp,
-    )
+    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
+      Text(
+        ui.askHint ?: "インカムのボタンで話せます",
+        Modifier.weight(1f).testTag("askHint"),
+        color = if (ui.askHint == null) Color(0xFF13804A) else MaterialTheme.colorScheme.onSurfaceVariant,
+        fontSize = 16.sp,
+      )
+      if (onNote != null) {
+        Button(
+          onClick = onNote,
+          Modifier.heightIn(min = 48.dp).testTag("newNote"),
+          colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF13804A), contentColor = Color.White),
+          contentPadding = PaddingValues(horizontal = 12.dp, vertical = 2.dp),
+        ) { Text("📝 地点メモ", fontSize = 14.sp, fontWeight = FontWeight.Bold) }
+      }
+    }
     Column(
       Modifier.fillMaxWidth().heightIn(min = 76.dp, max = 140.dp).background(Color(0xFF1F4FD1), RoundedCornerShape(16.dp))
         .clickable { confirming = true }.padding(16.dp).testTag("newConversation"),
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
index f2816e5..f383e79 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt
@@ -2,6 +2,8 @@ package com.touringproject.v2.ui
 
 import androidx.compose.runtime.Composable
 import androidx.compose.runtime.getValue
+import androidx.compose.runtime.mutableStateOf
+import androidx.compose.runtime.setValue
 import androidx.compose.runtime.produceState
 import androidx.compose.runtime.remember
 import androidx.compose.ui.Modifier
@@ -12,6 +14,8 @@ import com.touringproject.v2.map.MapPin
 import com.touringproject.v2.map.RouteMap
 import com.touringproject.v2.map.rideMap
 import com.touringproject.v2.records.AskEdits
+import com.touringproject.v2.records.NoteDraft
+import com.touringproject.v2.records.NoteEdits
 import com.touringproject.v2.records.NoteRecord
 import com.touringproject.v2.ride.Ride
 import com.touringproject.v2.ride.RideController
@@ -143,3 +147,28 @@ fun AskMemoRoute(records: RoomRecords, edits: AskEdits, rideId: String, askId: S
   val target = remember(asks, askId) { askMemoTarget(asks, askId, ZoneId.systemDefault()) } ?: return
   MemoScreen(target, ask.memo, { edits.memo(askId, it) }, onClose, modifier)
 }
+
+/** SC-19 opened from Home: the memo is kept for the ride it was opened in when it is first saved (slice 3 spec §7.3). */
+@Composable
+fun NewNoteRoute(records: RoomRecords, notes: NoteEdits, draft: NoteDraft, onClose: () -> Unit, modifier: Modifier = Modifier) {
+  val ride = readRide(records, draft.rideId) ?: return
+  val kept = ride.value ?: return
+  val header = remember(draft, kept.name) { newNoteHeader(draft, kept.name, ZoneId.systemDefault()) }
+  NoteScreen(header, null, { notes.create(draft, it) }, onClose, modifier)
+}
+
+/**
+ * SC-19 opened from SC-06, to change or delete a kept memo. The memo last read stays on screen once it is deleted, so
+ * the deletion in progress is not cancelled with the screen and closes it once.
+ */
+@Composable
+fun NoteRoute(records: RoomRecords, notes: NoteEdits, rideId: String, noteId: String, onClose: () -> Unit, modifier: Modifier = Modifier) {
+  val ride = readRide(records, rideId) ?: return
+  val list = readNotes(records, rideId) ?: return
+  var shown by remember(noteId) { mutableStateOf(list.firstOrNull { it.id == noteId }) }
+  list.firstOrNull { it.id == noteId }?.let { shown = it }
+  val note = shown ?: return
+  val name = ride.value?.name ?: return
+  val header = remember(note, name) { noteHeader(note, name, ZoneId.systemDefault()) }
+  NoteScreen(header, note.text, { notes.text(noteId, it) }, onClose, modifier, onDelete = { notes.delete(noteId) })
+}
PATCH
````

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t7.log 2>&1; tail -1 /tmp/trv2-t7.log
```

Expected: `BUILD SUCCESSFUL`（JVM のテスト493件）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt \
  app/src/main/java/com/touringproject/v2/records/Notes.kt \
  app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt \
  app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt \
  app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt \
  app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
git commit -m "feat: open SC-19 from Home while a ride records or is paused, and from SC-06 to change or delete a memo"
```

---

### Task 8: 版と文書

**Files:**
- Modify: `app/build.gradle.kts`（版 0.7.0）・`README.md`（Android）・`docs-parent/mock/index.html`

- [ ] **Step 1: 版を上げ、README を直す**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/README.md b/README.md
index 811e736..1d75b10 100644
--- a/README.md
+++ b/README.md
@@ -13,15 +13,15 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 | `.../audio/` | インカムの経路・録音・再生・端末の音声・合図 |
 | `.../location/` | 質問の位置の監視と方位の材料の選び方・走行のルートの位置の頼み方と点のふるい分け（`Route.kt`） |
 | `.../ride/` | 走行の型と計算（`Ride.kt`、純粋）・司令塔（`RideController.kt`）・外との窓口（`RidePorts.kt`） |
-| `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・質問のメモと削除（`RoomAskEdits.kt`）・送信の置き場（`RoomSyncStore.kt`）・記録の画面の読み出し（`RoomRecords.kt`）。スキーマは `app/schemas/` に版ごとに残す |
-| `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋）・メモの決まり（`Memos.kt`、純粋）・質問を変える窓口（`AskEdits.kt`） |
+| `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・質問のメモと削除（`RoomAskEdits.kt`）・地点メモ（`RoomNotes.kt`）・送信の置き場（`RoomSyncStore.kt`）・記録の画面の読み出し（`RoomRecords.kt`）。スキーマは `app/schemas/` に版ごとに残す |
+| `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋）・メモの決まり（`Memos.kt`、純粋）・地点メモの型と位置の選び方（`Notes.kt`、純粋）・質問と地点メモを変える窓口（`AskEdits.kt`・`NoteEdits.kt`） |
 | `.../map/` | 地図（MapLibre と国土地理院の淡色地図）。描くデータの組み立ては `MapData.kt`（純粋）、地図の部品は `RouteMap.kt`、スタイルは `app/src/main/assets/map/gsi-pale.json` |
-| `.../sync/` | 走行・ルート・メモ・削除の送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`） |
+| `.../sync/` | 走行・ルート・地点メモ・メモ・削除の送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`） |
 | `.../handsfree/` | 押下の重複・古い合図の除外・押下の行き先（試し録り中は試し録りへ） |
 | `.../recordings/` | 録音の置き場（直近10件と付随情報）・試し録りの司令塔・録音の確認（SC-12）の状態 |
 | `.../service/`・`.../nav/` | 前面サービス（走行の記録と一巡で1つ。種類の取りまとめは `ServiceCoordinator.kt`）・締め切りのアラームと自動終了の通知（`RideAlarms.kt`）・ナビを開く |
 | `.../settings/` | 設定（DataStore）と接続キー（Keystore で暗号化） |
-| `.../ui/` | 画面（Compose）。タブとバックスタックの組は `Tabs.kt`（Compose に依存しない）、タブの帯は `TabBar.kt`。記録の画面は `RecordsScreens.kt`（地図は差し替えられる枠で受ける）、その表示の組み立ては `RecordLabels.kt`（純粋）、読み出しとのつなぎは `RecordsRoutes.kt`。メモの編集（SC-08）は `MemoScreen.kt`、削除の確認（DL-01）は `DeleteDialog.kt` |
+| `.../ui/` | 画面（Compose）。タブとバックスタックの組は `Tabs.kt`（Compose に依存しない）、タブの帯は `TabBar.kt`。記録の画面は `RecordsScreens.kt`（地図は差し替えられる枠で受ける）、その表示の組み立ては `RecordLabels.kt`（純粋）、読み出しとのつなぎは `RecordsRoutes.kt`。メモの編集（SC-08）は `MemoScreen.kt`（SC-19 と共通の編集部品 `MemoEditor` を含む）、地点メモ（SC-19）は `NoteScreen.kt`、削除の確認（DL-01）は `DeleteDialog.kt` |
 
 ## 大事な決まり
 
@@ -30,7 +30,8 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 - 質問を受けるのは走行の記録中だけ。`AskController.run` の入口で `RideNow`（記録中・一時停止中・記録していない）を見て、記録中でなければ録音を始めず、理由を読み上げる。画面の「押して話す」も押せない形にする（親の spec 2 §4.7・adr/0008）。
 - Room のスキーマを変えるときは、版を上げて Migration を書き、`app/schemas/` に書き出された JSON もコミットする。破壊的な作り直しは使わない。スキーマの JSON は debug のビルドの資産にも入る（Robolectric の `MigrationTestHelper` が読むため。release には入らない）。Entity や Migration を変えた直後のテストは `--rerun` で確かめる。
 - 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと。契機では未送信を調べるだけで、送るものが無ければ通信しない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。
-- 1回の送信は、削除の印（`deletions`）→ 走行とルート → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため）。記録を消すときは、同じトランザクションで削除の印を書く。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
+- 1回の送信は、削除の印（`deletions`）→ 走行とルート → 地点メモ → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため）。記録を消すときは、同じトランザクションで削除の印を書く。送れない削除の印（知らない種類）は、ログ `sync_unsendable` に出して消す（残すと、毎回の送信がそこで止まる）。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
+- 地点メモ（SC-19）は、走行の記録中と一時停止中にホームの「📝 地点メモ」から開く。開いたときに、その走行の最後の点を位置に、質問と同じ選び方で方位の材料を決め（`noteDraft`）、保存するまで書かない。住所と方位は、最初に送ったときに Backend が決めて返し、端末はそれを行に書く（`notes.address`・`headingDegrees`）。地図のピンは緑で、質問とは別の通し番号。質問の一巡が終わったときに、その走行が消えていれば質問は書かない（`AskDao.keep`）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
 - インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
 - 回答は音声の焦点（audio focus）を取らずに鳴らす（ナビの案内と重ねる）。
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index eb48958..24c1105 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 7
-    versionName = "0.6.0"
+    versionCode = 8
+    versionName = "0.7.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
PATCH
````

- [ ] **Step 2: 親の文書を写す**

親のモックの SC-19（住所の文言）を、この plan のコミットで直してあるので、Android の `docs-parent/` に写す。

```bash
cd $ROOT && scripts/sync-docs.sh Android
cd $AND && git status --short docs-parent
```

Expected: `docs-parent/mock/index.html` だけが変わっている。

- [ ] **Step 3: コミット**

```bash
cd $AND && git add app/build.gradle.kts README.md docs-parent/mock/index.html
git commit -m "chore: raise the version to 0.7.0 and describe point memos"
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

Expected: `493 0`。`BUILD SUCCESSFUL`。`release permissions OK (15)`。

- [ ] **Step 2: エミュレーターのテスト**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: 6件が通る（`RouteMapTest` は、緑のピンも描かれ、押すと地点メモの id が返る）。

---

### Task 10: 利用者の実機の確認

走行用のビルド（版 0.7.0）を実機に入れる。Room の版は変わらないので、Migration は走らない。

```bash
cd $AND && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

1. 設定 → バージョンが 0.7.0。これまでの走行・質問・メモが、記録のタブにそのまま出る。走行を記録していないとき、ホームに「📝 地点メモ」は無い。
2. 走行を始めると、ホームの「インカムのボタンで話せます」の右に緑の「📝 地点メモ」が出て、ホームはスクロールしない。
3. 停車して「📝 地点メモ」→ SC-19 がすぐ開き、タブの帯が消え、キーボードが出る。上部は「<日付> <時刻> · 今いる地点」「📍 住所は送ったあとに付きます」「走行「<名前>」に入ります」。「🎤 声で入力」は無い。空のままでは「保存」を押せない。書いて「保存」でホームに戻る。
4. 「📝 地点メモ」を素早く2回押す → SC-19 は1つだけ開き、✕ で閉じるとホームに戻る。書きかけで ✕ を押すと「変更を破棄しますか？」が出る。
5. 一時停止中にも「📝 地点メモ」が出て、地点メモを書ける。
6. インカムで1つ質問してから、走行を終える。記録の一覧 → その走行の詳細（SC-06）: 地図に緑のピン（質問とは別の番号 1・2）、要約に「📝 地点メモ 2件」、時系列に質問と時刻の順で混ざって出る（緑の番号・「時刻 · 場所 · 📝 地点メモ」・本文）。送れたあとなので、場所は住所になっている。
7. 緑のピンを押す → カード「1 · <時刻> · <場所> · 📝 地点メモ」と本文と「開く ›」→ SC-19。上部は「走行「<名前>」で書いたメモ」と住所。本文を直して保存すると、SC-06 の時系列が変わる。
8. 地図の右上の「💬 質問」「📝 地点メモ」で、それぞれのピンを出す・隠す。両方隠すとルートだけになり、時系列はそのまま出る。詳細を閉じて開き直しても、選んだ状態のまま。
9. SC-19 の「この地点メモを削除」→「この地点メモを削除しますか？」「メモが削除されます。元に戻せません。」→「削除する」で SC-06 に戻る。ピンと時系列の行が消え、地点メモの番号が詰まる。
10. 機内モードにして、別の走行の記録中に地点メモを書き、走行を終える → 一覧で「未送信あり」。その地点メモを開くと「📍 住所は送ったあとに付きます」。機内モードを外してアプリを前面に出し直すと「保存済み」になり、地点メモに住所が付く。
11. #49（見た目）: 長い走行でピンを押したとき、色が変わるのが遅れない。走行の詳細から一覧へ戻ったとき、一覧が一瞬空にならない。
12. AI が DynamoDB を読んで確かめる（読むだけ）: 手順 6・10 の地点メモの `RIDE#<rideId>#NOTE#<noteId>` に `text`・`address`・`headingDegrees` があり、手順 9 で消した地点メモは記録が無く、`DELETED#NOTE#<noteId>` がある。ユーザー名と識別子はチャットにだけ出す。

✗ が出たら `superpowers:systematic-debugging`。
