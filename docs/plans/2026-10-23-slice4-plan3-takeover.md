# スライス4 計画3: Android（引き継ぎの読み込み・SC-14） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** クラウドの記録を端末へ読み込めるようにする。SC-18 でユーザー名を変えるときは、端末の記録を消して新しい名前の記録を入れてから名前を保存し、SC-14 の「クラウドから読み直す」では今の名前のまま突き合わせる。SC-14（保存の状態・未送信の内訳・最後に保存した時刻・今すぐ保存・件数）を作る。あわせて Android #64・#65・#66・#67 を直し、最後に spec §1 の判定（残りの3項目）を実機で行う。

**Architecture:** `GET /records` の受け口（`api/Records.kt`・`ApiClient.records`）がページを読み、突き合わせの決まりは純粋な関数 `merge`（`sync/Merge.kt`）にする。`RoomTakeover`（`store/`）が、端末の記録を読み・`merge` し・書くまでを1つのトランザクション（`withTransaction`）で行い、記録中の走行と（名前の変更なら）未送信をその中で確かめ直す。読み込みの係 `Takeover`（`sync/`）は、全ページを読んでから書き、名前の変更ならそのあとで名前を保存する。読み始めから保存までは `RideSync.withoutPasses` の中に置き、送信の回を走らせない。SC-14・SC-18 は `AppGraph` の `takeover`・`saveSummary`・`lastSaved` を読む。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版6のまま。DAO を足すだけで表は変えない。`room-ktx` の `withTransaction`）・Robolectric 4.16（SDK 35）・OkHttp・kotlinx.serialization。足す依存は無い。

**Spec:** [docs/specs/2026-10-22-slice4-design.md](../specs/2026-10-22-slice4-design.md)（§1・§6・§7・§8・§9・§11・§12）。`GET /records` の形の正本は `docs/07a_openapi.yaml`（`RecordsPage`・`RecordItem`）で、plan 1 でデプロイ済み。決定の記録は [adr/0010](../../adr/0010-read-the-cloud-only-when-taking-over.md)。

**範囲に入れた issue（Android）:** #64（通信できるままの失敗で残した質問できなかった地点が、次の契機まで送られない）・#65（SC-06 の時系列の質問できなかった地点の行に「 · 📵」が無い）・#66（走行のメモの書き込みに失敗したあと、「記録を保存できません」の帯が残る）・#67（最初の送信で住所を確定できなかった地点メモ・質問できなかった地点が、住所を求め直されない）。plan を書くときに利用者と決めた（2026-10-23）。

**前提:** Android の `main`（`0a656ab`。版 0.9.0・JVM のテスト554件）の上に作る。Backend は plan 1 がデプロイ済み（`GET /records`・smoke 39/39）。

**計画を書くときに決めたこと（spec からの具体化）:**

- `GET /records` の受け口（spec §6.2）: `RecordsApi.records(cursor)` が1ページを `CloudPage(items, cursor)` で返す。項目は `kind` で `CloudRide`・`CloudRoute`・`CloudNote`・`CloudAsk`・`CloudDeleted` に読む。知らない `kind` は読み飛ばし（Backend が後で種類を足しても壊れない）、知っている種類で読めない項目はページごと失敗にする（spec §8 の「不正な応答」）。数は Double で読む。`cursor` は不透明な文字列なので URL に符号化して返す。`GET` なので一時的な失敗（5xx・429・通信）は試し直す。
- 突き合わせ（spec §6.1）は `merge(device, cloud, now)`。決めたこと:
  - 走行はメタ情報の `updatedAt`、地点メモは `updatedAt`、質問できなかった地点は `updatedAt`、会話のメモは `memoUpdatedAt` を比べ、クラウドが新しいときだけ入れる。Backend の質問は、中身（文字起こし・回答・結果）をいつもクラウドの値で書き、メモだけを比べる。
  - ルートは、走行ごとに点の数が多いほうを残す（クラウドのほうが多ければ、その走行の点を全部クラウドのものに入れ替える）。走行は1台の端末でしか記録されず、かたまりは点を足していくだけなので、走行の点の数を比べることは、かたまりごとに比べることと同じになる。
  - クラウドに削除の跡があれば端末から消す（走行なら子の記録と質問も。削除の印は作らない）。端末にまだ送っていない削除の印がある記録（とその走行の子）は、クラウドの写しを入れない（消したものが戻らないように）。
  - 記録中・一時停止中のままクラウドにある走行は、最後の点の時刻（点が無ければ最後の区間の始まり）で、`EndReason.SHUTDOWN` で終えて入れる。送り済みの印はクラウドの版にし、終えた版を未送信にする。
  - 受け付けたまま結果の出ていない質問（`processing`）は、失敗の理由 `timeout`（「時間内に答えが届きませんでした」）で入れる。`tts_failed` でも回答の文があれば、質問の一巡と同じく「答えた」にする。文字の質問は `question` を文字起こしに入れる。`askedAt` の無い質問は入れない。
  - 走行の無い記録（`rideId` が無い・その走行がクラウドにも端末にも無い）は入れない。
  - 入れた件数（SC-14 で出す）は、入れたか入れ替えた走行・地点メモ・質問できなかった地点・新しい質問・新しいメモと、消した記録の数。Backend の質問を同じ中身で書き直したものは数えない。
- 書き込み（spec §6.3）: `RoomTakeover.take(cloud, replace, now)` は1つのトランザクションで、(1) 記録中・一時停止中の走行があれば何もせず null、(2) `replace`（名前の変更）なら未送信があれば何もせず null、無ければ端末の記録（削除の印も）を全部消す、(3) 端末を読んで `merge` し、書く。入れたものには送り済みの印を付ける（走行の `sentUpdatedAt`、点の `chunk`、地点メモの `sentUpdatedAt`、質問の `memoSentUpdatedAt`・`sentUpdatedAt`）。距離は、点を書いた走行について点から計算し直す。途中で例外が出れば（クラウドの項目が読めないときを含む）何も変わらない。表は変えないので Room は版6のまま。
- 「未送信」（spec §7.1・US-E-06.008）: 次の送信の回が送るもの、つまり質問できなかった地点・走行（メタ情報かルート）・地点メモ・会話のメモ・削除の印の数（`SaveSummary`）。Backend に断られた版は二度と送らないので数えない。記録中の走行も数えない（端数のかたまりは一時停止か終了で送るため）。この数を SC-14・設定の行・SC-18 の可否・`RoomTakeover` の確かめ直しで共通に使う。SC-18 は、走行の書き込みが失敗して書き直し待ちがあるとき（`RideController.storeFailed`）も変えられないにする（待っている変更が、名前を変えたあとに新しい名前の記録へ書かれないように）。
- 送信を止める（spec §6.3）: `RideSync` に `Mutex` を持たせ、`pass()` と `withoutPasses { }` を同じ鍵で回す。読み込みの係は、読み始めから書き込みと名前の保存までを `withoutPasses` の中で行う（名前を保存する前に送信が走ると、入れた走行の「終えた」版が古い名前で送られるため）。終わったら `RideSync.request()` を呼ぶ。`RideSync` の引数は `store, api, online, saved, log` の順（`saved` は既定値つき。`log` は末尾のラムダのまま）。
- 最後に保存した時刻（spec §7.1）: 送信の回が最後まで失敗せずに終わったとき（送るものが無かった回を含む。通信できない・接続キーが無いために試さなかった回は含めない）に `saved` を呼び、`LastSaved` が DataStore の別のキー `trv2.lastSavedAt` に端末の時刻で書く。
- 読み込みの係 `Takeover`: アプリの scope で走らせ、画面を離れても続ける（spec §7.2）。一度に1つだけ。状態 `TakeState(running, last, result)` を画面が読み、結果はそれを始めた画面（SC-18 は `SWITCH`、SC-14 は `REREAD`）だけが出す。画面を離れたら `seen()` で結果を消す（読み込み中なら残す）。`peek(name)` は DL-03 の前に1ページ目を読み、記録があるか（項目があるか、続きがあるか）を返す。読めた1ページ目は、名前の変更で読み直さずに使う。接続キーが無いときは「読み込めませんでした」と同じにする。
- SC-14 の文言と並べ方（spec §12。利用者と決めた、2026-10-23）: モックの形のまま、内訳は件数のある種類だけを「・」でつないだ1文（「質問できなかった地点 1件・走行 2本・地点メモ 3件・メモ 1件・削除 1件。通信できるようになると自動で送ります。」）。記録中は、別の行に「記録中の走行は、一時停止か終了で残りを送ります。」。保存済みは「● すべてクラウドに保存済み」と「最終保存 10:22」（今日でなければ「最終保存 10月21日 23:05」、まだ一度も無ければ「まだ保存していません」）。「今すぐ保存」は送っているあいだ「送っています…」で押せない。
- 「クラウドから読み直す」は、走行の記録中・一時停止中は押せず、「走行を終えてから読み直せます」と出す（利用者と決めた、2026-10-23）。読んでいるあいだは「読み込んでいます…」で押せない。結果は「N件の記録を読み込みました」「新しい記録はありませんでした」「読み込めませんでした」。
- SC-18・DL-03（spec §6.4）: 「変更する」は、走行の記録中・一時停止中（「走行を終えてから変えられます」）、未送信があるとき（「未送信の記録があります。先に「データの保存」で送ってください」と「データの保存へ」）、読み込み中は押せない。今と同じ名前は「今のユーザー名と同じです」。押すと1ページ目を読み、読めなければ「読み込めませんでした」。DL-03 の文言はモックの2つの状態のまま（記録がある: 「既にあるユーザー名です」・「切り替える」。無い: 「ユーザー名を変えますか？」・「変更する」）。名前を保存したら会話の文脈を切る（`ConversationState.reset()`）。SC-12 の録音は残す。結果は「ユーザー名を変えました」「未送信の記録があるため、変えられませんでした」「読み込めませんでした。ユーザー名は変えていません」。画面の説明はモックの文に合わせる。
- 設定の一覧（SC-09）に「☁️ データの保存」の行（値は「保存済み」か「未送信あり」）をユーザー名の下に足す。行が増えて小さな画面に入りきらないので、一覧をスクロールできるようにする。
- #64: 質問できなかった地点を DB に書けたら、`RoomAskLog` が送信の契機（`unreachedKept`、`AppGraph` で `sync.request()`）を呼ぶ。issue の対応案は `AskDeps` に契機を足すことだが、`AskLog.keep` は書き込みを裏で走らせるので、司令塔から呼ぶと、書き終える前に送信の回が未送信を読んでしまう。書けたあとに呼ぶ。
- #65: 時系列の行に `unreached` を持たせ、上段を「時刻 · 場所 · 📝 · 📵」の順にする（モックの `qRow`）。
- #66: 帯「記録を保存できません」の意味を「書き直し待ちの変更がある」にそろえる。走行のメモの失敗で書き直し待ちをメモの前に戻したときに、帯もそれに合わせる。
- #67: Backend は新しい版のときだけ住所を求め直すので、端末が版を進める。送り済みで、位置があり、住所が null の地点メモと質問できなかった地点を、起動ごとに一度（`RideSync.run()` の初め）`updatedAt` を進めて未送信に戻す。本当に住所の無い場所（山中など）では起動ごとに1回送るが、費用は小さい。
- `AppUi` の通しのテストは、SC-14 を開くところまで（記録の画面と違い地図が無い）。名前の変更と読み直しの通しは、Backend に繋ぐので Task 11 の実機で確かめる。
- 読み込みにかかる時間が長いときの見せ方（spec §12）は、Task 11 の実機で、今ある記録で測ってから決める。今は「読み込んでいます…」だけを出す。
- 版を 0.10.0（`versionCode` 11）に上げる。

この計画のコードは、使い捨てのフォルダで、次を確かめてから書いた。

- タスクの順に一つずつコミットし（Task 8 は issue ごとに4つ）、各コミットで `clean` から JVM のテストが通る（554件 → 605件）。各コミットのテストだけを1つ前のコミットに当てると落ちる（まだ無い名前を使うのでコンパイルで落ちるか、#66 は期待が外れて落ちる）。
- 最後に、JVM のテスト605件・エミュレーターのテスト6件・`assembleRelease`・`scripts/check-release-permissions.sh` が通る。
- plan の差分を新しい写しへ機械的に当てると、最終形と一致する。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice4-plan3` を切る（Task 0）。親は `slice4-plan3`。push・マージはしない（利用者が明示したときだけ）。push の前に `pre-push-secret-scan`。
- 作りの決まり: 判断の芯（`merge`・`SaveSummary` の意味・文言）は Android に依存させない。部品は `AppGraph` で手で組む。走行を変えるのは `RideController` だけ（読み込みは、走行が記録中・一時停止中でないときだけ表を書き換える）。
- 読み込むのは、ユーザー名を変えるときと SC-14 の「クラウドから読み直す」だけ。前面に来たときなどには読まない（adr/0010）。
- 読み込みは全ページを読んでから1つのトランザクションで書く。途中で失敗したら、端末の記録もユーザー名も変えない（spec §6.3・§6.4・§8）。
- Room は版6のまま（表を変えない）。破壊的な作り直しは使わない。
- ホームは全体がスクロールしない（この plan ではホームを変えない）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない（テストの作り物の名前 `rider01`・`taro01` などは除く）。端末のログ（`adb logcat`）には API の URL が出るので、書き写さない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*クラス名'`。Gradle のビルドキャッシュはフォルダをまたいで共有されるので、テストを確かめるときは `--rerun` を付ける。Kotlin の差分コンパイルは interface の変更を見逃すことがあるので、Task 10 は `./gradlew clean` から回す。
- `SyncStore` にメソッドを足したら、作り物（`RideSyncTest` の `World.store`・`TakeoverTest` の `nothingToSend`）にも足す（Task 8 の #67 の差分に入っている）。
- Robolectric の決まり（SDK 35・画面の外の行は `performScrollTo` で出す・地図の部品は動かさない）。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。使い終わったら止める。1回目に APK を入れる途中で「device offline」で止まったら、起動し直して回す。
- `RideForegroundServiceTest` の1件がまれに落ちる（Android #59）。落ちたら単独で回し直し、全体をもう一度回す。
- AWS は `AWS_PROFILE=touring`・リージョン `ap-northeast-1`（Task 11 で DynamoDB を読むだけ。消すときは利用者の了承を取る）。

## Review Focus

- ユーザー名を変える途中（記録を入れたあと、名前を保存する前）に送信の契機が来る → 入れた走行の「終えた」版が古い名前で送られない。名前を保存し終えてから送信の回が走る。Task 5 の `no_pass_runs_during_a_read_and_one_runs_after`・`no_pass_runs_while_records_are_read_in` と、`Takeover.switchTo` が `switched` を `withoutPasses` の中で呼ぶこと（Task 5 の差分）。
- DL-03 を開いているあいだに、SC-08 でメモを書き換える（未送信ができる）→ 「切り替える」を押しても名前も記録も変わらず「未送信の記録があるため、変えられませんでした」。Task 4 の `nothing_changes_while_something_is_left_to_send_or_a_ride_records`・Task 5 の `a_blocked_switch_keeps_the_name`。
- 端末の記録を消したあとで、クラウドの項目の1つが読めない・書けない → 消した記録が戻り、名前も変わらない。Task 4 の `a_failure_midway_leaves_the_device_as_it_was`・Task 5 の `a_page_that_cannot_be_read_changes_nothing`。
- アプリを入れ直したら、前の端末で記録中のまま残っていた走行がクラウドにある → 終えた走行として入り（サービスの動いていない記録中の走行を作らない）、次の回で「終えた」状態がクラウドへ届く。Task 2 の `a_ride_left_recording_ends_at_its_last_point_and_is_left_to_send`・Task 4 の `a_ride_left_recording_comes_in_ended_and_goes_back_ended`。
- 通信できないあいだに端末で記録を消し、その削除がまだ届かないうちに SC-14 で読み直す → 消した記録が戻らない。Task 2 の `the_devices_own_deletions_keep_the_cloud_copy_out`。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `api/Records.kt`・`api/ApiClient.kt` | `GET /records` の型（`CloudRecord`・`CloudPage`・`RecordsApi`）と `ApiClient.records` | 1 |
| `sync/Merge.kt` | 突き合わせの決まり `merge`・クラウドの質問の写し方 `CloudAsk.toRecord`・`epochMs` | 2 |
| `records/Saving.kt`・`store/RideDatabase.kt`・`store/RoomRecords.kt` | 未送信と件数 `SaveSummary`（3）、`TakeoverDao`・`summaryNow`（4）、`retryPlaces`（8） | 3・4・8 |
| `store/RoomTakeover.kt`・`sync/Takeover.kt` | 1つのトランザクションでの書き込み（4）、読み込みの係・`TakeResult`・`TakeState`・`Peek`（5・7） | 4・5・7 |
| `sync/RideSync.kt` | `withoutPasses`・`sending`・`saved`（5）、`retryPlaces` を起動ごとに一度（8） | 5・8 |
| `settings/LastSaved.kt` | 最後に保存した時刻 | 5 |
| `ui/SavingLabels.kt`・`ui/SettingsScreens.kt` | SC-14 の文言と画面・設定の行（6）、SC-18・DL-03（7） | 6・7 |
| `AppGraph.kt`・`ui/AppUi.kt` | `lastSaved`・`saveSummary`・`takeover`・SC-14 の入口（6）、SC-18 のつなぎ・`switchedTo`（7）、#64 の契機（8） | 6・7・8 |
| `store/RoomAskLog.kt` | #64 | 8 |
| `ui/RecordLabels.kt`・`ui/RecordsScreens.kt` | #65 | 8 |
| `ride/RideController.kt` | #66 | 8 |
| `store/RoomSyncStore.kt` | #67 | 8 |
| `app/build.gradle.kts`・`README.md` | 版と説明 | 9 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、今のテストを回す**

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice4-plan3
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t0.log 2>&1; tail -1 /tmp/trv2-t0.log
```

Expected: `BUILD SUCCESSFUL`（554件）。親はこの plan を書いたブランチ `slice4-plan3` のまま。

---

### Task 1: `GET /records` の受け口

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/api/Records.kt`
- Modify: `app/src/main/java/com/touringproject/v2/api/ApiClient.kt`
- Test: `app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt`

**Interfaces:**
- Produces: `sealed interface CloudRecord`。`CloudRide(rideId, name, status, segments: List<SegmentBody>, autoEnded, updatedAt, memo)`・`CloudRoute(rideId, seq, points: List<PointBody>)`・`CloudNote(rideId, noteId, at, location: Point?, text, updatedAt, address, headingDegrees)`・`CloudAsk(askId, status, askedAt, question, transcript, answer, error, answeredAt, location, address, headingDegrees, inputType, conversationId, newConversation, rideId, memo, memoUpdatedAt, updatedAt)`・`CloudDeleted(target, id, rideId, deletedAt)`（時刻はどれも ISO 8601 の文字列）。`data class CloudPage(items: List<CloudRecord>, cursor: String?)`。`interface RecordsApi { suspend fun records(cursor: String?): CloudPage }`（`ApiClient` が実装する）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
index 75e8175..2aa805b 100644
--- a/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
+++ b/app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
@@ -318,4 +318,68 @@ class ApiClientTest {
     assertEquals(ApiErrorKind.CONFLICT, error.kind)
     assertEquals(1, server.requestCount)
   }
+
+  // Slice 4 spec §6.2: every kind of record, values the Backend has not got as null, and whole numbers as numbers.
+  @Test
+  fun records_reads_each_kind_of_record() = runTest {
+    server.enqueue(
+      json(
+        200,
+        """{"items":[
+          {"kind":"ride","rideId":"r1","name":"箱根","status":"ended","segments":[{"startedAt":"2026-10-22T01:00:00Z","endedAt":"2026-10-22T02:00:00Z"}],"autoEnded":false,"updatedAt":"2026-10-22T02:00:00.123Z","memo":null},
+          {"kind":"route","rideId":"r1","seq":0,"points":[{"t":"2026-10-22T01:00:05Z","lat":35,"lon":139.5,"accuracy":null,"segment":0}]},
+          {"kind":"note","rideId":"r1","noteId":"n1","at":"2026-10-22T01:10:00Z","location":{"latitude":35.1,"longitude":139},"text":"展望","updatedAt":"2026-10-22T01:10:00Z","address":null,"headingDegrees":90},
+          {"kind":"ask","askId":"a1","status":"completed","askedAt":"2026-10-22T01:20:00Z","question":null,"transcript":"右手の山は","answer":"金時山です","error":null,"answeredAt":"2026-10-22T01:20:12Z","location":null,"address":"箱根町仙石原","headingDegrees":12.5,"inputType":"audio","conversationId":"c1","newConversation":true,"rideId":"r1","memo":null,"memoUpdatedAt":null,"updatedAt":null},
+          {"kind":"deleted","target":"note","id":"n2","rideId":"r1","deletedAt":"2026-10-22T03:00:00Z"}
+        ],"cursor":null}""",
+      ),
+    )
+    val page = client().records(null)
+    assertEquals(null, page.cursor)
+    assertEquals(
+      listOf(
+        CloudRide("r1", "箱根", "ended", listOf(SegmentBody("2026-10-22T01:00:00Z", "2026-10-22T02:00:00Z")), false, "2026-10-22T02:00:00.123Z", null),
+        CloudRoute("r1", 0, listOf(PointBody("2026-10-22T01:00:05Z", 35.0, 139.5, null, 0))),
+        CloudNote("r1", "n1", "2026-10-22T01:10:00Z", Point(35.1, 139.0), "展望", "2026-10-22T01:10:00Z", null, 90.0),
+        CloudAsk(
+          "a1", "completed", "2026-10-22T01:20:00Z", null, "右手の山は", "金時山です", null, "2026-10-22T01:20:12Z", null, "箱根町仙石原", 12.5,
+          "audio", "c1", true, "r1", null, null, null,
+        ),
+        CloudDeleted("note", "n2", "r1", "2026-10-22T03:00:00Z"),
+      ),
+      page.items,
+    )
+    val request = server.takeRequest()
+    assertEquals("GET /Prod/records", "${request.method} ${request.path}")
+    assertEquals("rider01", request.getHeader("x-user-name"))
+  }
+
+  // The cursor is opaque: it goes back as it came, whatever characters it has.
+  @Test
+  fun records_sends_the_cursor_back_and_tells_there_is_more() = runTest {
+    server.enqueue(json(200, """{"items":[],"cursor":"eyJw+IjoiIn0="}"""))
+    server.enqueue(json(200, """{"items":[],"cursor":null}"""))
+    val first = client().records(null)
+    assertEquals("eyJw+IjoiIn0=", first.cursor)
+    client().records(first.cursor)
+    server.takeRequest()
+    assertEquals("/Prod/records?cursor=eyJw%2BIjoiIn0%3D", server.takeRequest().path)
+  }
+
+  // A kind the device does not know yet is left out; a record of a known kind it cannot read fails the whole page.
+  @Test
+  fun records_leaves_out_unknown_kinds_and_fails_on_a_broken_record() = runTest {
+    server.enqueue(json(200, """{"items":[{"kind":"transcription","id":"t1"}],"cursor":null}"""))
+    server.enqueue(json(200, """{"items":[{"kind":"ride","rideId":"r1"}],"cursor":null}"""))
+    assertEquals(emptyList<CloudRecord>(), client().records(null).items)
+    assertTrue(runCatching { client().records(null) }.exceptionOrNull() is kotlinx.serialization.SerializationException)
+  }
+
+  @Test
+  fun records_retries_a_server_failure() = runTest {
+    server.enqueue(json(503))
+    server.enqueue(json(200, """{"items":[],"cursor":null}"""))
+    assertEquals(CloudPage(emptyList(), null), client().records(null))
+    assertEquals(2, server.requestCount)
+  }
 }
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ApiClientTest'`
Expected: コンパイルで落ちる（`CloudRide`・`records` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
index b366337..9d0f813 100644
--- a/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
+++ b/app/src/main/java/com/touringproject/v2/api/ApiClient.kt
@@ -14,6 +14,7 @@ import okhttp3.Request
 import okhttp3.RequestBody.Companion.toRequestBody
 import okhttp3.Response
 import java.io.IOException
+import java.net.URLEncoder
 import java.util.concurrent.TimeUnit
 import kotlin.coroutines.resumeWithException
 
@@ -162,7 +163,7 @@ class ApiClient(
   private val maxAttempts: Int = 3,
   timeoutMs: Long = 15_000,
   private val retryDelay: suspend (Long) -> Unit = { delay(it) },
-) : AskApi, RideApi, TranscriptionApi {
+) : AskApi, RideApi, TranscriptionApi, RecordsApi {
   private val baseUrl = baseUrl.trimEnd('/')
   // callTimeout bounds the whole exchange, so a stalled connection cannot hang the ask.
   private val http = http.newBuilder().callTimeout(timeoutMs, TimeUnit.MILLISECONDS).build()
@@ -216,6 +217,12 @@ class ApiClient(
     request("DELETE", "/rides/$rideId/notes/$noteId", null, TRANSIENT)
   }
 
+  override suspend fun records(cursor: String?): CloudPage {
+    val query = cursor?.let { "?cursor=" + URLEncoder.encode(it, "UTF-8") } ?: ""
+    val page = json.decodeFromString(RecordsPageBody.serializer(), request("GET", "/records$query", null, TRANSIENT))
+    return CloudPage(page.items.mapNotNull { cloudRecord(json, it) }, page.cursor)
+  }
+
   suspend fun checkKey() {
     try {
       request("GET", "/asks/$PROBE_ASK_ID", null, TRANSIENT)
diff --git a/app/src/main/java/com/touringproject/v2/api/Records.kt b/app/src/main/java/com/touringproject/v2/api/Records.kt
new file mode 100644
index 0000000..e501085
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/api/Records.kt
@@ -0,0 +1,89 @@
+package com.touringproject.v2.api
+
+import kotlinx.serialization.Serializable
+import kotlinx.serialization.json.Json
+import kotlinx.serialization.json.JsonObject
+import kotlinx.serialization.json.contentOrNull
+import kotlinx.serialization.json.jsonPrimitive
+
+// The user's records as GET /records reads them back (slice 4 spec §6.2, docs-parent/07a_openapi.yaml RecordItem). The
+// Backend writes a value it has not got as null and a whole number without its fraction, so numbers are read as Double.
+
+sealed interface CloudRecord
+
+/** A ride as it was last put: its meta, without its route. */
+@Serializable
+data class CloudRide(
+  val rideId: String,
+  val name: String,
+  val status: String,
+  val segments: List<SegmentBody>,
+  val autoEnded: Boolean,
+  val updatedAt: String,
+  val memo: String? = null,
+) : CloudRecord
+
+/** One route chunk of a ride as it was last put. */
+@Serializable data class CloudRoute(val rideId: String, val seq: Int, val points: List<PointBody>) : CloudRecord
+
+/** A point memo with the place and heading the Backend settled. */
+@Serializable
+data class CloudNote(
+  val rideId: String,
+  val noteId: String,
+  val at: String,
+  val location: Point? = null,
+  val text: String,
+  val updatedAt: String,
+  val address: String? = null,
+  val headingDegrees: Double? = null,
+) : CloudRecord
+
+/**
+ * An ask: one the Backend took in (status processing / completed / failed) or an unreached one (offline). question is a
+ * text ask's question; updatedAt is set only for an unreached ask.
+ */
+@Serializable
+data class CloudAsk(
+  val askId: String,
+  val status: String,
+  val askedAt: String? = null,
+  val question: String? = null,
+  val transcript: String? = null,
+  val answer: String? = null,
+  val error: String? = null,
+  val answeredAt: String? = null,
+  val location: Point? = null,
+  val address: String? = null,
+  val headingDegrees: Double? = null,
+  val inputType: String? = null,
+  val conversationId: String? = null,
+  val newConversation: Boolean = false,
+  val rideId: String? = null,
+  val memo: String? = null,
+  val memoUpdatedAt: String? = null,
+  val updatedAt: String? = null,
+) : CloudRecord
+
+/** A deletion's mark: the target (ask / ride / note) is gone, and a ride with all that was under it. */
+@Serializable data class CloudDeleted(val target: String, val id: String, val rideId: String? = null, val deletedAt: String) : CloudRecord
+
+/** One page; cursor is null on the last one. */
+data class CloudPage(val items: List<CloudRecord>, val cursor: String?)
+
+interface RecordsApi {
+  /** The page after cursor, or the first one for null. A record of a known kind that cannot be read throws. */
+  suspend fun records(cursor: String?): CloudPage
+}
+
+@Serializable internal data class RecordsPageBody(val items: List<JsonObject>, val cursor: String? = null)
+
+/** A kind the device does not know (one the Backend may add later) is left out rather than failing the page. */
+internal fun cloudRecord(json: Json, item: JsonObject): CloudRecord? = when (item["kind"]?.jsonPrimitive?.contentOrNull) {
+  "ride" -> json.decodeFromJsonElement(CloudRide.serializer(), item)
+  "route" -> json.decodeFromJsonElement(CloudRoute.serializer(), item)
+  "note" -> json.decodeFromJsonElement(CloudNote.serializer(), item)
+  "ask" -> json.decodeFromJsonElement(CloudAsk.serializer(), item)
+  "deleted" -> json.decodeFromJsonElement(CloudDeleted.serializer(), item)
+  else -> null
+}
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ApiClientTest'`
Expected: 30件が通る

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/api/Records.kt app/src/main/java/com/touringproject/v2/api/ApiClient.kt app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt
git commit -m "feat: read the user's records back page by page with GET /records"
```

---

### Task 2: 突き合わせの決まり

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/sync/Merge.kt`
- Test: `app/src/test/java/com/touringproject/v2/sync/MergeTest.kt`

**Interfaces:**
- Consumes: Task 1 の `CloudRecord` の型。
- Produces: `data class KeptRide(updatedAt: Long, points: Int)`・`KeptAsk(updatedAt: Long?, memoUpdatedAt: Long?)`・`DeviceRecords(rides: Map<String, KeptRide>, notes: Map<String, Long>, asks: Map<String, KeptAsk>, deletions: Set<Pair<String, String>>)`（どれも既定値は空）。`TakenRide(ride: Ride, sentUpdatedAt: Long)`・`TakenPoint(chunk: Int, point: RoutePoint)`・`TakenRoute(rideId, points: List<TakenPoint>)`・`TakenNote(id, rideId, at, latitude, longitude, text, updatedAt, address, headingDegrees)`・`TakenAsk(ask: AskRecord, memoUpdatedAt: Long?, content: Boolean, memo: Boolean)`・`GoneRecords(rides, asks, notes: Set<String>)`・`Merge(rides, routes, notes, asks, gone, count: Int)`。`fun merge(device: DeviceRecords, cloud: List<CloudRecord>, now: Long): Merge`・`fun CloudAsk.toRecord(): AskRecord?`・`fun epochMs(iso: String): Long`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/sync/MergeTest.kt b/app/src/test/java/com/touringproject/v2/sync/MergeTest.kt
new file mode 100644
index 0000000..97793bc
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/sync/MergeTest.kt
@@ -0,0 +1,185 @@
+package com.touringproject.v2.sync
+
+import com.touringproject.v2.api.CloudAsk
+import com.touringproject.v2.api.CloudDeleted
+import com.touringproject.v2.api.CloudNote
+import com.touringproject.v2.api.CloudRide
+import com.touringproject.v2.api.CloudRoute
+import com.touringproject.v2.api.Point
+import com.touringproject.v2.api.PointBody
+import com.touringproject.v2.api.SegmentBody
+import com.touringproject.v2.ask.AskOutcome
+import com.touringproject.v2.ride.EndReason
+import com.touringproject.v2.ride.RideStatus
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
+import org.junit.Test
+
+private const val T0 = "2026-10-22T01:00:00Z"
+private val T0_MS = epochMs(T0)
+private const val NOW = 1_800_000_000_000L
+
+private fun iso(offsetMs: Long) = java.time.Instant.ofEpochMilli(T0_MS + offsetMs).toString()
+
+private fun ride(id: String = "r1", status: String = "ended", updated: Long = 3_600_000, ended: Long? = 3_600_000) =
+  CloudRide(id, "箱根", status, listOf(SegmentBody(T0, ended?.let(::iso))), false, iso(updated), null)
+
+private fun route(rideId: String = "r1", seq: Int = 0, count: Int = 3, from: Long = 1_000) =
+  CloudRoute(rideId, seq, (0 until count).map { PointBody(iso(from + it * 1_000L), 35.0, 139.0, 5.0, 0) })
+
+private fun note(id: String = "n1", rideId: String = "r1", updated: Long = 600_000) =
+  CloudNote(rideId, id, iso(600_000), Point(35.1, 139.1), "展望", iso(updated), "箱根町仙石原", 90.0)
+
+private fun ask(
+  id: String = "a1",
+  rideId: String? = "r1",
+  status: String = "completed",
+  memoUpdated: Long? = null,
+  updated: Long? = null,
+  error: String? = null,
+  answer: String? = "金時山です",
+) = CloudAsk(
+  id, status, iso(1_200_000), null, "右手の山は", answer, error, null, Point(35.2, 139.2), "箱根町", 12.5, "audio",
+  if (status == "offline") null else "c1", true, rideId, memoUpdated?.let { "メモ" }, memoUpdated?.let(::iso), updated?.let(::iso),
+)
+
+class MergeTest {
+  // Slice 4 spec §6.1: what only the cloud has comes in, marked as what the Backend already has.
+  @Test
+  fun what_only_the_cloud_has_comes_in_as_sent() {
+    val merged = merge(DeviceRecords(), listOf(ride(), route(), note(), ask()), NOW)
+    val taken = merged.rides.single()
+    assertEquals(T0_MS + 3_600_000, taken.ride.updatedAt)
+    assertEquals(taken.ride.updatedAt, taken.sentUpdatedAt)
+    assertEquals(EndReason.MANUAL, taken.ride.endReason)
+    assertEquals(listOf(0, 0, 0), merged.routes.single().points.map { it.chunk })
+    assertEquals(T0_MS + 1_000, merged.routes.single().points.first().point.t)
+    assertEquals("箱根町仙石原", merged.notes.single().address)
+    assertEquals(AskOutcome.ANSWERED, merged.asks.single().ask.outcome)
+    assertEquals(3, merged.count)
+  }
+
+  @Test
+  fun the_newer_version_wins() {
+    val device = DeviceRecords(
+      rides = mapOf("r1" to KeptRide(T0_MS + 9_000_000, 3)),
+      notes = mapOf("n1" to T0_MS + 100_000),
+      asks = mapOf("u1" to KeptAsk(T0_MS + 9_000_000, null), "u2" to KeptAsk(T0_MS + 100_000, null)),
+    )
+    val cloud = listOf(ride(), route(), note(), ask("u1", status = "offline", updated = 1_200_000), ask("u2", status = "offline", updated = 1_200_000))
+    val merged = merge(device, cloud, NOW)
+    assertEquals(emptyList<TakenRide>(), merged.rides)
+    assertEquals(emptyList<TakenRoute>(), merged.routes)
+    assertEquals(listOf("n1"), merged.notes.map { it.id })
+    assertEquals(listOf("u2"), merged.asks.map { it.ask.askId })
+    assertEquals(2, merged.count)
+  }
+
+  // A Backend's ask always takes the cloud's answer; its memo goes by its own time.
+  @Test
+  fun a_memo_is_compared_on_its_own() {
+    val device = DeviceRecords(
+      rides = mapOf("r1" to KeptRide(T0_MS, 0)),
+      asks = mapOf("a1" to KeptAsk(null, T0_MS + 9_000_000), "a2" to KeptAsk(null, T0_MS)),
+    )
+    val merged = merge(device, listOf(ask("a1", memoUpdated = 1_500_000), ask("a2", memoUpdated = 1_500_000), ask("a3")), NOW)
+    assertEquals(
+      listOf(Triple("a1", true, false), Triple("a2", true, true), Triple("a3", true, false)),
+      merged.asks.map { Triple(it.ask.askId, it.content, it.memo) },
+    )
+    assertEquals(T0_MS + 1_500_000, merged.asks[1].memoUpdatedAt)
+    assertEquals(2, merged.count)
+  }
+
+  // Slice 3 spec §4.2: a deletion's mark removes the record, and a ride all that is under it.
+  @Test
+  fun a_mark_in_the_cloud_removes_what_the_device_keeps() {
+    val device = DeviceRecords(
+      rides = mapOf("r1" to KeptRide(T0_MS, 3), "r2" to KeptRide(T0_MS, 0)),
+      notes = mapOf("n1" to T0_MS),
+      asks = mapOf("a1" to KeptAsk(null, null)),
+    )
+    val cloud = listOf(
+      CloudDeleted("ride", "r1", null, iso(5_000_000)),
+      CloudDeleted("note", "n1", "r2", iso(5_000_000)),
+      CloudDeleted("ask", "a1", "r2", iso(5_000_000)),
+      CloudDeleted("ask", "a9", "r2", iso(5_000_000)),
+      ride("r1"), route("r1"), note("n5", "r1"), ask("a5", "r1"),
+    )
+    val merged = merge(device, cloud, NOW)
+    assertEquals(GoneRecords(setOf("r1"), setOf("a1"), setOf("n1")), merged.gone)
+    assertTrue(merged.rides.isEmpty() && merged.routes.isEmpty() && merged.notes.isEmpty() && merged.asks.isEmpty())
+    assertEquals(3, merged.count)
+  }
+
+  // A record deleted on the device, its deletion not yet sent, stays deleted.
+  @Test
+  fun the_devices_own_deletions_keep_the_cloud_copy_out() {
+    val device = DeviceRecords(deletions = setOf("ride" to "r1", "note" to "n2", "ask" to "a2"))
+    val cloud = listOf(ride("r1"), route("r1"), note("n1", "r1"), ask("a1", "r1"), ride("r2"), note("n2", "r2"), ask("a2", "r2"))
+    val merged = merge(device, cloud, NOW)
+    assertEquals(listOf("r2"), merged.rides.map { it.ride.id })
+    assertEquals(emptyList<TakenRoute>(), merged.routes)
+    assertEquals(emptyList<TakenNote>(), merged.notes)
+    assertEquals(emptyList<TakenAsk>(), merged.asks)
+  }
+
+  // Slice 4 spec §6.1: a ride left recording ends at its last point, and its end is left for the next pass to send.
+  @Test
+  fun a_ride_left_recording_ends_at_its_last_point_and_is_left_to_send() {
+    val merged = merge(DeviceRecords(), listOf(ride(status = "recording", updated = 2_000, ended = null), route(count = 3, from = 1_000)), NOW)
+    val taken = merged.rides.single()
+    assertEquals(RideStatus.ENDED, taken.ride.status)
+    assertEquals(EndReason.SHUTDOWN, taken.ride.endReason)
+    assertEquals(T0_MS + 3_000, taken.ride.segments.single().endedAt)
+    assertEquals(T0_MS + 2_000, taken.sentUpdatedAt)
+    assertTrue(taken.ride.updatedAt > taken.sentUpdatedAt)
+  }
+
+  @Test
+  fun a_ride_left_recording_without_a_point_ends_where_its_segment_started() {
+    val taken = merge(DeviceRecords(), listOf(ride(status = "recording", updated = 0, ended = null)), NOW).rides.single()
+    assertEquals(T0_MS, taken.ride.segments.single().endedAt)
+  }
+
+  // adr/0008: no record comes in without its ride, in the cloud or on the device.
+  @Test
+  fun records_without_their_ride_are_left_out() {
+    val device = DeviceRecords(rides = mapOf("r2" to KeptRide(T0_MS + 9_000_000, 0)))
+    val cloud = listOf(route("r9"), note("n1", "r9"), ask("a1", "r9"), ask("a2", null), note("n2", "r2"), ask("a3", "r2"))
+    val merged = merge(device, cloud, NOW)
+    assertEquals(emptyList<TakenRoute>(), merged.routes)
+    assertEquals(listOf("n2"), merged.notes.map { it.id })
+    assertEquals(listOf("a3"), merged.asks.map { it.ask.askId })
+  }
+
+  // A route only grows: the cloud's goes in only when it has more points, in chunk order.
+  @Test
+  fun the_longer_route_wins() {
+    val cloud = listOf(ride(), route(seq = 1, count = 2, from = 400_000), route(seq = 0, count = 300))
+    val shorter = merge(DeviceRecords(rides = mapOf("r1" to KeptRide(T0_MS + 9_000_000, 100))), cloud, NOW)
+    assertEquals(listOf(0 to 300, 1 to 2), shorter.routes.single().points.groupBy { it.chunk }.map { (k, v) -> k to v.size })
+    val longer = merge(DeviceRecords(rides = mapOf("r1" to KeptRide(T0_MS + 9_000_000, 302))), cloud, NOW)
+    assertEquals(emptyList<TakenRoute>(), longer.routes)
+  }
+
+  @Test
+  fun an_ask_comes_in_as_the_ask_loop_keeps_it() {
+    val heard = ask(status = "failed", error = "tts_failed").toRecord()!!
+    assertEquals(AskOutcome.ANSWERED to null, heard.outcome to heard.failure)
+    val unheard = ask(status = "failed", error = "no_speech", answer = null).toRecord()!!
+    assertEquals(AskOutcome.FAILED to "no_speech", unheard.outcome to unheard.failure)
+    // Slice 4 spec §6.1 (2026-10-22): an ask still waiting has no result, and comes in as a failure without one.
+    val waiting = ask(status = "processing", answer = null).toRecord()!!
+    assertEquals(AskOutcome.FAILED to "timeout", waiting.outcome to waiting.failure)
+    val text = ask().copy(inputType = "text", question = "近くのカフェ", transcript = null).toRecord()!!
+    assertEquals("text" to "近くのカフェ", text.input to text.transcript)
+    val unreached = ask(status = "offline", updated = 1_300_000, answer = null).toRecord()!!
+    assertEquals(AskOutcome.OFFLINE, unreached.outcome)
+    assertNull(unreached.conversationId)
+    assertEquals(T0_MS + 1_300_000, unreached.updatedAt)
+    assertTrue(unreached.sent)
+    assertNull(ask().copy(askedAt = null).toRecord())
+  }
+}
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*MergeTest'`
Expected: コンパイルで落ちる（`merge` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/sync/Merge.kt b/app/src/main/java/com/touringproject/v2/sync/Merge.kt
new file mode 100644
index 0000000..2c31143
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/sync/Merge.kt
@@ -0,0 +1,204 @@
+package com.touringproject.v2.sync
+
+import com.touringproject.v2.api.CloudAsk
+import com.touringproject.v2.api.CloudDeleted
+import com.touringproject.v2.api.CloudNote
+import com.touringproject.v2.api.CloudRecord
+import com.touringproject.v2.api.CloudRide
+import com.touringproject.v2.api.CloudRoute
+import com.touringproject.v2.ask.ASK_INPUT_VOICE
+import com.touringproject.v2.ask.AskOutcome
+import com.touringproject.v2.ask.AskRecord
+import com.touringproject.v2.ask.TIMEOUT_FAILURE
+import com.touringproject.v2.ride.EndReason
+import com.touringproject.v2.ride.Ride
+import com.touringproject.v2.ride.RideStatus
+import com.touringproject.v2.ride.RoutePoint
+import com.touringproject.v2.ride.Segment
+import com.touringproject.v2.ride.end
+import java.time.OffsetDateTime
+
+// Which of the cloud's records the device takes in (slice 4 spec §6.1, adr/0010), decided without touching either.
+
+/** What the device keeps of a ride, as far as the merge needs it. */
+data class KeptRide(val updatedAt: Long, val points: Int)
+
+/** What the device keeps of an ask: an unreached ask's version (null for the Backend's own) and its memo's. */
+data class KeptAsk(val updatedAt: Long?, val memoUpdatedAt: Long?)
+
+/** The device's records by id; deletions are its own deletions not yet sent, as kind (ask / ride / note) to id. */
+data class DeviceRecords(
+  val rides: Map<String, KeptRide> = emptyMap(),
+  val notes: Map<String, Long> = emptyMap(),
+  val asks: Map<String, KeptAsk> = emptyMap(),
+  val deletions: Set<Pair<String, String>> = emptySet(),
+)
+
+/** A ride's meta to write. sentUpdatedAt is the version the Backend has: behind updatedAt for a ride that ends here. */
+data class TakenRide(val ride: Ride, val sentUpdatedAt: Long)
+
+/** A route point with the chunk it was sent in. */
+data class TakenPoint(val chunk: Int, val point: RoutePoint)
+
+/** A ride's whole route as the cloud has it; it replaces the device's. */
+data class TakenRoute(val rideId: String, val points: List<TakenPoint>)
+
+data class TakenNote(
+  val id: String,
+  val rideId: String,
+  val at: Long,
+  val latitude: Double?,
+  val longitude: Double?,
+  val text: String,
+  val updatedAt: Long,
+  val address: String?,
+  val headingDegrees: Double?,
+)
+
+/**
+ * An ask from the cloud. For an ask the device keeps, content says to write what the cloud says of the ask itself (the
+ * Backend's own asks always; an unreached ask when the cloud's version is newer) and memo to write the cloud's memo
+ * (when it is newer). An ask the device does not keep is written whole.
+ */
+data class TakenAsk(val ask: AskRecord, val memoUpdatedAt: Long?, val content: Boolean, val memo: Boolean)
+
+/** What the device keeps no longer: the cloud has the deletion's mark. A ride goes with all that is under it. */
+data class GoneRecords(val rides: Set<String> = emptySet(), val asks: Set<String> = emptySet(), val notes: Set<String> = emptySet())
+
+/**
+ * What to write. count is how many records the device takes in or loses (SC-14 tells it); a Backend's ask written again
+ * as the device had it is not counted, nor a route apart from its ride.
+ */
+data class Merge(
+  val rides: List<TakenRide>,
+  val routes: List<TakenRoute>,
+  val notes: List<TakenNote>,
+  val asks: List<TakenAsk>,
+  val gone: GoneRecords,
+  val count: Int,
+)
+
+/** The Backend's times are ISO 8601 with their zone; one that cannot be read throws, and the read fails as a whole. */
+fun epochMs(iso: String): Long = OffsetDateTime.parse(iso).toInstant().toEpochMilli()
+
+/**
+ * The newer version wins: the cloud's when it is newer, the device's otherwise (it goes on the next pass). A deletion's
+ * mark in the cloud removes the device's record; one of the device's own deletions keeps the cloud's copy out. What only
+ * the device has stays. Rides compare their meta, point memos and unreached asks their updatedAt, and memos their
+ * memoUpdatedAt; a route only grows, so the longer one wins. Nothing comes in without its ride.
+ */
+fun merge(device: DeviceRecords, cloud: List<CloudRecord>, now: Long): Merge {
+  val marks = cloud.filterIsInstance<CloudDeleted>()
+  fun marked(target: String) = marks.filter { it.target == target }.map { it.id }.toSet()
+  val goneRides = marked("ride")
+  val goneAsks = marked("ask")
+  val goneNotes = marked("note")
+  fun heldBack(kind: String, id: String, rideId: String?) =
+    (kind to id) in device.deletions || (rideId != null && (rideId in goneRides || ("ride" to rideId) in device.deletions))
+
+  val chunks = cloud.filterIsInstance<CloudRoute>().groupBy { it.rideId }
+  val cloudRides = cloud.filterIsInstance<CloudRide>().filter { !heldBack("ride", it.rideId, it.rideId) }
+  val rides = mutableListOf<TakenRide>()
+  val routes = mutableListOf<TakenRoute>()
+  for (c in cloudRides) {
+    val updatedAt = epochMs(c.updatedAt)
+    val mine = device.rides[c.rideId]
+    val points = chunks[c.rideId].orEmpty().sortedBy { it.seq }.flatMap { chunk ->
+      chunk.points.map { TakenPoint(chunk.seq, RoutePoint(it.segment, epochMs(it.t), it.lat, it.lon, it.accuracy)) }
+    }
+    if (mine == null || mine.updatedAt < updatedAt) rides += TakenRide(c.toRide(updatedAt, points, now), updatedAt)
+    if (points.size > (mine?.points ?: 0)) routes += TakenRoute(c.rideId, points)
+  }
+  val present = (device.rides.keys - goneRides) + cloudRides.map { it.rideId }
+
+  val notes = cloud.filterIsInstance<CloudNote>()
+    .filter { !heldBack("note", it.noteId, it.rideId) && it.noteId !in goneNotes && it.rideId in present }
+    .mapNotNull { c ->
+      val updatedAt = epochMs(c.updatedAt)
+      val mine = device.notes[c.noteId]
+      if (mine != null && mine >= updatedAt) return@mapNotNull null
+      TakenNote(c.noteId, c.rideId, epochMs(c.at), c.location?.latitude, c.location?.longitude, c.text, updatedAt, c.address, c.headingDegrees)
+    }
+
+  var counted = 0
+  val asks = cloud.filterIsInstance<CloudAsk>().mapNotNull { c ->
+    val rideId = c.rideId ?: return@mapNotNull null
+    if (heldBack("ask", c.askId, rideId) || c.askId in goneAsks || rideId !in present) return@mapNotNull null
+    val ask = c.toRecord() ?: return@mapNotNull null
+    val memoUpdatedAt = c.memoUpdatedAt?.let(::epochMs)
+    val mine = device.asks[c.askId]
+    val unreached = ask.outcome == AskOutcome.OFFLINE
+    val content = mine == null || !unreached || (mine.updatedAt ?: Long.MIN_VALUE) < (ask.updatedAt ?: Long.MIN_VALUE)
+    val memo = memoUpdatedAt != null && (mine?.memoUpdatedAt ?: Long.MIN_VALUE) < memoUpdatedAt
+    if (mine == null || memo || (unreached && content)) counted += 1
+    if (mine != null && !content && !memo) return@mapNotNull null
+    TakenAsk(ask, memoUpdatedAt, content, memo)
+  }
+
+  val gone = GoneRecords(goneRides intersect device.rides.keys, goneAsks intersect device.asks.keys, goneNotes intersect device.notes.keys)
+  val count = rides.size + notes.size + counted + gone.rides.size + gone.asks.size + gone.notes.size
+  return Merge(rides, routes, notes, asks, gone, count)
+}
+
+/**
+ * A ride left recording or paused in the cloud (one recorded before the app was put in again) ends here at its last
+ * point, or at the start of its last segment without one, as one the device stopped: no service records it now.
+ */
+private fun CloudRide.toRide(updatedAt: Long, points: List<TakenPoint>, now: Long): Ride {
+  val status = RideStatus.valueOf(status.uppercase())
+  val kept = Ride(
+    id = rideId,
+    name = name,
+    status = status,
+    segments = segments.mapIndexed { i, s -> Segment(i, epochMs(s.startedAt), s.endedAt?.let(::epochMs), null) },
+    endReason = if (status != RideStatus.ENDED) null else if (autoEnded) EndReason.AUTO else EndReason.MANUAL,
+    deadline = null,
+    lastAliveAt = null,
+    distanceMeters = 0.0,
+    updatedAt = updatedAt,
+    memo = memo,
+  )
+  if (status == RideStatus.ENDED) return kept
+  val last = maxOf(points.maxOfOrNull { it.point.t } ?: Long.MIN_VALUE, kept.segments.last().startedAt)
+  return kept.end(last, EndReason.SHUTDOWN, now)
+}
+
+/**
+ * The device's copy of a cloud ask. An answer the rider could hear counts as answered, as the ask loop keeps it; one
+ * still waiting for its result (processing) has none now and comes in as a failure without one, a time-out. null when
+ * it has no time to place it at.
+ */
+fun CloudAsk.toRecord(): AskRecord? {
+  val askedAt = askedAt?.let(::epochMs) ?: return null
+  val unreached = status == "offline"
+  val heard = status == "completed" || (error == "tts_failed" && !answer.isNullOrEmpty())
+  val outcome = when {
+    unreached -> AskOutcome.OFFLINE
+    heard -> AskOutcome.ANSWERED
+    else -> AskOutcome.FAILED
+  }
+  return AskRecord(
+    askId = askId,
+    askedAt = askedAt,
+    answeredAt = answeredAt?.let(::epochMs),
+    transcript = question ?: transcript,
+    answer = answer,
+    latitude = location?.latitude,
+    longitude = location?.longitude,
+    address = address,
+    headingDegrees = headingDegrees,
+    input = if (inputType == "text") "text" else ASK_INPUT_VOICE,
+    conversationId = conversationId,
+    newConversation = newConversation,
+    outcome = outcome,
+    failure = when {
+      outcome != AskOutcome.FAILED -> null
+      status == "processing" -> TIMEOUT_FAILURE
+      else -> error ?: "agent_failed"
+    },
+    rideId = rideId,
+    memo = memo,
+    updatedAt = if (unreached) updatedAt?.let(::epochMs) ?: askedAt else null,
+    sent = true,
+  )
+}
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*MergeTest'`
Expected: 10件が通る

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/sync/Merge.kt app/src/test/java/com/touringproject/v2/sync/MergeTest.kt
git commit -m "feat: decide which of the cloud's records the device takes in"
```

---

### Task 3: 未送信と件数の数え方

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/records/Saving.kt`
- Modify: `app/src/main/java/com/touringproject/v2/store/RideDatabase.kt`（`RideDao.summary`）・`app/src/main/java/com/touringproject/v2/store/RoomRecords.kt`
- Test: `app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt`

**Interfaces:**
- Produces: `data class SaveSummary(unreached, unsentRides, notes, memos, deletions, rides, asks: Int)`（既定値は0）と `val unsent: Int`（先の5つの和）。`RideDao.summary(): Flow<SaveSummary>`。`RoomRecords.summary: Flow<SaveSummary>`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
index 45b3960..8e1800a 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
@@ -6,7 +6,9 @@ import androidx.test.core.app.ApplicationProvider
 import androidx.test.ext.junit.runners.AndroidJUnit4
 import com.touringproject.v2.ask.AskOutcome
 import com.touringproject.v2.ask.AskRecord
+import com.touringproject.v2.ask.unreachedAsk
 import com.touringproject.v2.records.SaveState
+import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.ride.EndReason
 import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.RoutePoint
@@ -15,6 +17,7 @@ import com.touringproject.v2.ride.newRide
 import com.touringproject.v2.ride.pause
 import com.touringproject.v2.ride.resume
 import com.touringproject.v2.sync.ChunkRange
+import com.touringproject.v2.sync.PendingDeletion
 import kotlinx.coroutines.MainScope
 import kotlinx.coroutines.flow.first
 import kotlinx.coroutines.runBlocking
@@ -121,7 +124,7 @@ class RoomRecordsTest {
     val ended = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(4_000, EndReason.MANUAL, 4_000)
     rides.save(ended)
     sync.rideSent("r1", ended.updatedAt)
-    log.save(com.touringproject.v2.ask.unreachedAsk("u1", 1_500, null, null, "r1"))
+    log.save(unreachedAsk("u1", 1_500, null, null, "r1"))
     assertEquals(SaveState.UNSENT, records.list.first().single().saveState)
     val kept = records.asks("r1").first().single()
     assertEquals(AskOutcome.OFFLINE, kept.outcome)
@@ -130,4 +133,33 @@ class RoomRecordsTest {
     assertEquals(SaveState.SAVED, records.list.first().single().saveState)
     assertEquals(true, records.asks("r1").first().single().sent)
   }
+
+  // Slice 4 spec §7.1: SC-14 counts what the next pass would send, leaving out refused versions and the ride recording.
+  @Test
+  fun the_summary_counts_what_is_left_to_send() = runBlocking {
+    val ended = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(4_000, EndReason.MANUAL, 4_000)
+    rides.save(ended)
+    rides.addPoint("r1", RoutePoint(0, 1_500, 35.0, 139.0, 5.0), 0.0, 1_500)
+    val refused = newRide("r3", "伊豆", 1_000, 7, 24 * HOUR_MS).end(2_000, EndReason.MANUAL, 2_000)
+    rides.save(refused)
+    sync.rideRefused("r3", refused.updatedAt)
+    rides.save(newRide("r2", "御殿場", 5_000, 7, 24 * HOUR_MS))
+    rides.addPoint("r2", RoutePoint(0, 5_500, 35.0, 139.0, 5.0), 0.0, 5_500)
+    log.save(ask("a1", 1_200, "r1"))
+    db.asks().writeMemo("a1", "景色", 3_000)
+    log.save(unreachedAsk("u1", 5_600, null, null, "r2"))
+    db.notes().insert(NoteEntity("n1", "r2", 5_700, null, null, null, null, null, "展望", 5_700, null, null, null, null))
+    db.rides().markDeleted(DeletionEntity("ride", "r9", null, 6_000))
+    assertEquals(
+      SaveSummary(unreached = 1, unsentRides = 1, notes = 1, memos = 1, deletions = 1, rides = 3, asks = 2),
+      records.summary.first(),
+    )
+    sync.rideSent("r1", ended.updatedAt)
+    sync.chunkSent("r1", ChunkRange(0, 0, 1), refused = false)
+    sync.unreachedSent("u1", 5_600, null, null)
+    sync.noteSent("n1", 5_700, null, null)
+    sync.askMemoRefused("a1", db.asks().ask("a1")!!.memoUpdatedAt!!)
+    sync.deletionSent(PendingDeletion("ride", "r9", null))
+    assertEquals(0, records.summary.first().unsent)
+  }
 }
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RoomRecordsTest'`
Expected: コンパイルで落ちる（`SaveSummary` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/records/Saving.kt b/app/src/main/java/com/touringproject/v2/records/Saving.kt
new file mode 100644
index 0000000..5712447
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/records/Saving.kt
@@ -0,0 +1,19 @@
+package com.touringproject.v2.records
+
+/**
+ * What SC-14 tells of the device's records (slice 4 spec §7.1). The first five count what the next pass would send:
+ * unreached asks, rides (their meta or route), point memos, conversation memos and deletions; a version the Backend
+ * refused is not counted, since it is never sent again. The ride recording now is left out: its last, partial chunk
+ * goes only at its pause or end (slice 2 spec §5.3). rides and asks count all the device keeps.
+ */
+data class SaveSummary(
+  val unreached: Int = 0,
+  val unsentRides: Int = 0,
+  val notes: Int = 0,
+  val memos: Int = 0,
+  val deletions: Int = 0,
+  val rides: Int = 0,
+  val asks: Int = 0,
+) {
+  val unsent: Int get() = unreached + unsentRides + notes + memos + deletions
+}
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index f99c759..d82e3cd 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -19,6 +19,7 @@ import androidx.room.Transaction
 import androidx.room.Upsert
 import androidx.room.migration.Migration
 import androidx.sqlite.db.SupportSQLiteDatabase
+import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.records.memoTime
 import kotlinx.coroutines.flow.Flow
 
@@ -384,6 +385,20 @@ interface RideDao {
   @Query("SELECT * FROM rides WHERE id = :id")
   fun watch(id: String): Flow<RideWithSegments?>
 
+  @Query(
+    "SELECT (SELECT COUNT(*) FROM asks WHERE status = 'offline' AND (sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
+      "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt)) AS unreached, " +
+      "(SELECT COUNT(*) FROM rides WHERE status != 'recording' AND ((sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
+      "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt) OR " +
+      "EXISTS (SELECT 1 FROM route_points WHERE chunk IS NULL AND route_points.rideId = rides.id))) AS unsentRides, " +
+      "(SELECT COUNT(*) FROM notes WHERE (sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
+      "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt)) AS notes, " +
+      "(SELECT COUNT(*) FROM asks WHERE memoUpdatedAt IS NOT NULL AND (memoSentUpdatedAt IS NULL OR memoSentUpdatedAt < memoUpdatedAt) AND " +
+      "(memoRejectedUpdatedAt IS NULL OR memoRejectedUpdatedAt != memoUpdatedAt)) AS memos, " +
+      "(SELECT COUNT(*) FROM deletions) AS deletions, (SELECT COUNT(*) FROM rides) AS rides, (SELECT COUNT(*) FROM asks) AS asks",
+  )
+  fun summary(): Flow<SaveSummary>
+
   @Upsert
   suspend fun upsertRide(ride: RideEntity)
 
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
index 253bb89..ac79714 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomRecords.kt
@@ -5,6 +5,7 @@ import com.touringproject.v2.ask.AskRecord
 import com.touringproject.v2.api.HeadingSample
 import com.touringproject.v2.records.NoteRecord
 import com.touringproject.v2.records.RideListItem
+import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.records.orderRides
 import com.touringproject.v2.records.saveState
 import com.touringproject.v2.ride.Ride
@@ -52,6 +53,9 @@ class RoomRecords(private val rides: RideDao, private val asks: AskDao, private
     )
   }
 
+  /** SC-14 and SC-18: what is left to send and how much is kept. Room reads it again for every route point. */
+  val summary: Flow<SaveSummary> = rides.summary()
+
   fun ride(id: String): Flow<Ride?> = rides.watch(id).map { it?.ride?.toRide(it.segments.sortedBy { s -> s.seq }) }
 
   fun asks(rideId: String): Flow<List<AskRecord>> = asks.forRide(rideId).map { list -> list.map { it.toRecord() } }
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RoomRecordsTest'`
Expected: 7件が通る

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/records/Saving.kt app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomRecords.kt app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt
git commit -m "feat: count what is left to send for SC-14"
```

---

### Task 4: クラウドの記録を1つのトランザクションで入れる

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt`・`app/src/main/java/com/touringproject/v2/sync/Takeover.kt`（この Task では `TakeoverStore` だけ）
- Modify: `app/src/main/java/com/touringproject/v2/store/RideDatabase.kt`（集計の SQL を定数 `SUMMARY` に移す・`summaryNow`・`TakeoverDao`）
- Test: `app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt`

**Interfaces:**
- Consumes: Task 2 の `merge` とその型、Task 3 の `SaveSummary`。
- Produces: `interface TakeoverStore { suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): Int? }`（null は「記録中の走行がある」か「`replace` で未送信がある」で何もしなかった）。`class RoomTakeover(db: RideDatabase) : TakeoverStore`。`RideDatabase.takeover(): TakeoverDao`。`RideDao.summaryNow(): SaveSummary`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
new file mode 100644
index 0000000..f661f76
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
@@ -0,0 +1,166 @@
+package com.touringproject.v2.store
+
+import android.app.Application
+import androidx.room.Room
+import androidx.test.core.app.ApplicationProvider
+import androidx.test.ext.junit.runners.AndroidJUnit4
+import com.touringproject.v2.api.CloudAsk
+import com.touringproject.v2.api.CloudDeleted
+import com.touringproject.v2.api.CloudNote
+import com.touringproject.v2.api.CloudRide
+import com.touringproject.v2.api.CloudRoute
+import com.touringproject.v2.api.Point
+import com.touringproject.v2.api.PointBody
+import com.touringproject.v2.api.SegmentBody
+import com.touringproject.v2.ask.AskOutcome
+import com.touringproject.v2.ask.AskRecord
+import com.touringproject.v2.records.SaveState
+import com.touringproject.v2.ride.EndReason
+import com.touringproject.v2.ride.HOUR_MS
+import com.touringproject.v2.ride.RideStatus
+import com.touringproject.v2.ride.RoutePoint
+import com.touringproject.v2.ride.end
+import com.touringproject.v2.ride.newRide
+import com.touringproject.v2.ride.withMemo
+import com.touringproject.v2.sync.ChunkRange
+import com.touringproject.v2.sync.epochMs
+import kotlinx.coroutines.MainScope
+import kotlinx.coroutines.flow.first
+import kotlinx.coroutines.runBlocking
+import org.junit.After
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
+import org.junit.Test
+import org.junit.runner.RunWith
+
+private const val T0 = "2026-10-22T01:00:00Z"
+private val T0_MS = epochMs(T0)
+private const val NOW = 1_800_000_000_000L
+
+private fun iso(offsetMs: Long) = java.time.Instant.ofEpochMilli(T0_MS + offsetMs).toString()
+
+@RunWith(AndroidJUnit4::class)
+class RoomTakeoverTest {
+  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
+    .allowMainThreadQueries()
+    .build()
+  private val rides = RoomRideStore(db.rides())
+  private val sync = RoomSyncStore(db.rides(), db.asks(), db.notes())
+  private val log = RoomAskLog(db.asks(), MainScope()) { _, _ -> }
+  private val records = RoomRecords(db.rides(), db.asks(), db.notes())
+  private val takeover = RoomTakeover(db)
+
+  @After
+  fun close() = db.close()
+
+  private fun cloudRide(id: String = "r1", status: String = "ended", ended: String? = iso(3_600_000)) =
+    CloudRide(id, "箱根", status, listOf(SegmentBody(T0, ended)), false, iso(3_600_000), null)
+
+  private fun cloudRoute(id: String = "r1") =
+    CloudRoute(id, 0, (0 until 3).map { PointBody(iso(1_000L + it * 60_000), 35.0 + it * 0.01, 139.0, 5.0, 0) })
+
+  private fun cloudAsk(id: String = "a1", rideId: String = "r1", memoUpdated: Long? = null) = CloudAsk(
+    id, "completed", iso(1_200_000), null, "右手の山は", "金時山です", null, iso(1_210_000), Point(35.2, 139.2), "箱根町", 12.5,
+    "audio", "c1", true, rideId, memoUpdated?.let { "クラウドのメモ" }, memoUpdated?.let(::iso), null,
+  )
+
+  private val cloud = listOf(
+    cloudRide(), cloudRoute(),
+    CloudNote("r1", "n1", iso(600_000), Point(35.1, 139.1), "展望", iso(600_000), "箱根町仙石原", 90.0),
+    cloudAsk(),
+    CloudAsk("u1", "offline", iso(1_300_000), rideId = "r1", updatedAt = iso(1_300_000)),
+  )
+
+  private fun deviceAsk(id: String, rideId: String) =
+    AskRecord(id, 1_200, 1_201, "質問", "回答", 35.0, 139.0, "箱根町", 45.0, "voice", "c0", false, AskOutcome.ANSWERED, null, rideId)
+
+  /** A ride the device recorded and sent whole: nothing of it is left to send. */
+  private suspend fun sentRide(id: String) {
+    val ride = newRide(id, "御殿場", 1_000, 7, 24 * HOUR_MS).end(4_000, EndReason.MANUAL, 4_000)
+    rides.save(ride)
+    rides.addPoint(id, RoutePoint(0, 1_500, 35.0, 139.0, 5.0), 0.0, 1_500)
+    sync.rideSent(id, ride.updatedAt)
+    sync.chunkSent(id, ChunkRange(0, 0, 1), refused = false)
+  }
+
+  // Slice 4 spec §6.1: what comes in is marked as sent, so none of it is sent back.
+  @Test
+  fun the_clouds_records_come_in_and_are_not_sent_back() = runBlocking {
+    assertEquals(4, takeover.take(cloud, replace = false, now = NOW))
+    assertEquals(0, records.summary.first().unsent)
+    assertEquals(SaveState.SAVED, records.list.first().single().saveState)
+    assertEquals(emptyList<String>(), sync.unsent().map { it.ride.id })
+    assertTrue(records.ride("r1").first()!!.distanceMeters > 2_000)
+    assertEquals(listOf("a1", "u1"), records.asks("r1").first().map { it.askId })
+    assertEquals("箱根町仙石原", records.notes("r1").first().single().address)
+    assertEquals(3, records.route("r1").size)
+  }
+
+  @Test
+  fun a_ride_left_recording_comes_in_ended_and_goes_back_ended() = runBlocking {
+    takeover.take(listOf(cloudRide(status = "recording", ended = null), cloudRoute()), replace = false, now = NOW)
+    val unsent = sync.unsent().single()
+    assertEquals(RideStatus.ENDED, unsent.ride.status)
+    assertEquals(EndReason.SHUTDOWN, unsent.ride.endReason)
+    assertEquals(3 to 3, unsent.sentPoints to unsent.totalPoints)
+    assertNull(rides.active())
+  }
+
+  // Slice 4 spec §6.4: another user name's records replace all the device keeps.
+  @Test
+  fun replacing_removes_the_devices_records_first() = runBlocking {
+    sentRide("r0")
+    log.save(deviceAsk("a0", "r0"))
+    assertEquals(4, takeover.take(cloud, replace = true, now = NOW))
+    assertEquals(listOf("r1"), records.list.first().map { it.ride.id })
+    assertEquals(emptyList<AskRecord>(), records.asks("r0").first())
+    assertEquals(2, records.summary.first().asks)
+  }
+
+  // US-E-06.008: with something left to send, or a ride recording, nothing changes.
+  @Test
+  fun nothing_changes_while_something_is_left_to_send_or_a_ride_records() = runBlocking {
+    rides.save(newRide("r0", "御殿場", 1_000, 7, 24 * HOUR_MS).end(4_000, EndReason.MANUAL, 4_000))
+    assertNull(takeover.take(cloud, replace = true, now = NOW))
+    assertEquals(listOf("r0"), records.list.first().map { it.ride.id })
+    rides.save(newRide("r2", "伊豆", 5_000, 7, 24 * HOUR_MS))
+    assertNull(takeover.take(cloud, replace = false, now = NOW))
+    assertEquals(setOf("r0", "r2"), records.list.first().map { it.ride.id }.toSet())
+  }
+
+  // Slice 4 spec §8: a record that cannot be read fails the whole take, after the device's records were cleared.
+  @Test
+  fun a_failure_midway_leaves_the_device_as_it_was() = runBlocking {
+    sentRide("r0")
+    val broken = cloud + cloudRide("r5", status = "flying")
+    assertTrue(runCatching { takeover.take(broken, replace = true, now = NOW) }.isFailure)
+    assertEquals(listOf("r0"), records.list.first().map { it.ride.id })
+    assertEquals(1, records.route("r0").size)
+  }
+
+  // SC-14's read again: the device's newer edits stay, waiting to be sent, and the cloud's marks remove records.
+  @Test
+  fun reading_again_keeps_the_devices_newer_edits_and_follows_the_clouds_marks() = runBlocking {
+    takeover.take(cloud, replace = false, now = NOW)
+    val kept = rides.ride("r1")!!
+    rides.save(kept.withMemo("端末のメモ", NOW))
+    db.asks().writeMemo("a1", "端末の会話メモ", NOW)
+    val again = listOf(cloudRide(), cloudRoute(), cloudAsk(memoUpdated = 1_500_000), CloudDeleted("note", "n1", "r1", iso(5_000_000)))
+    assertEquals(1, takeover.take(again, replace = false, now = NOW + 1_000))
+    assertEquals("端末のメモ", records.ride("r1").first()!!.memo)
+    assertEquals("端末の会話メモ", records.asks("r1").first().first { it.askId == "a1" }.memo)
+    assertEquals(emptyList<Any>(), records.notes("r1").first())
+    assertEquals(1, records.summary.first().unsentRides)
+    assertEquals(1, records.summary.first().memos)
+  }
+
+  @Test
+  fun a_newer_memo_in_the_cloud_replaces_the_devices() = runBlocking {
+    takeover.take(listOf(cloudRide(), cloudAsk()), replace = false, now = NOW)
+    takeover.take(listOf(cloudRide(), cloudAsk(memoUpdated = 1_500_000)), replace = false, now = NOW)
+    val ask = records.asks("r1").first().single()
+    assertEquals("クラウドのメモ", ask.memo)
+    assertEquals(0, records.summary.first().memos)
+  }
+}
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RoomTakeoverTest'`
Expected: コンパイルで落ちる（`RoomTakeover` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index d82e3cd..9a90da2 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -355,6 +355,18 @@ data class RideRow(
   val unreachedLeft: Boolean,
 )
 
+// What SC-14 counts (SaveSummary): what the next pass would send, but the recording ride's, and all that is kept.
+private const val SUMMARY = "SELECT (SELECT COUNT(*) FROM asks WHERE status = 'offline' AND (sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
+  "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt)) AS unreached, " +
+  "(SELECT COUNT(*) FROM rides WHERE status != 'recording' AND ((sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
+  "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt) OR " +
+  "EXISTS (SELECT 1 FROM route_points WHERE chunk IS NULL AND route_points.rideId = rides.id))) AS unsentRides, " +
+  "(SELECT COUNT(*) FROM notes WHERE (sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
+  "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt)) AS notes, " +
+  "(SELECT COUNT(*) FROM asks WHERE memoUpdatedAt IS NOT NULL AND (memoSentUpdatedAt IS NULL OR memoSentUpdatedAt < memoUpdatedAt) AND " +
+  "(memoRejectedUpdatedAt IS NULL OR memoRejectedUpdatedAt != memoUpdatedAt)) AS memos, " +
+  "(SELECT COUNT(*) FROM deletions) AS deletions, (SELECT COUNT(*) FROM rides) AS rides, (SELECT COUNT(*) FROM asks) AS asks"
+
 @Dao
 interface RideDao {
   @Query("SELECT * FROM rides WHERE status != 'ended' LIMIT 1")
@@ -385,20 +397,14 @@ interface RideDao {
   @Query("SELECT * FROM rides WHERE id = :id")
   fun watch(id: String): Flow<RideWithSegments?>
 
-  @Query(
-    "SELECT (SELECT COUNT(*) FROM asks WHERE status = 'offline' AND (sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
-      "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt)) AS unreached, " +
-      "(SELECT COUNT(*) FROM rides WHERE status != 'recording' AND ((sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
-      "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt) OR " +
-      "EXISTS (SELECT 1 FROM route_points WHERE chunk IS NULL AND route_points.rideId = rides.id))) AS unsentRides, " +
-      "(SELECT COUNT(*) FROM notes WHERE (sentUpdatedAt IS NULL OR sentUpdatedAt < updatedAt) AND " +
-      "(rejectedUpdatedAt IS NULL OR rejectedUpdatedAt != updatedAt)) AS notes, " +
-      "(SELECT COUNT(*) FROM asks WHERE memoUpdatedAt IS NOT NULL AND (memoSentUpdatedAt IS NULL OR memoSentUpdatedAt < memoUpdatedAt) AND " +
-      "(memoRejectedUpdatedAt IS NULL OR memoRejectedUpdatedAt != memoUpdatedAt)) AS memos, " +
-      "(SELECT COUNT(*) FROM deletions) AS deletions, (SELECT COUNT(*) FROM rides) AS rides, (SELECT COUNT(*) FROM asks) AS asks",
-  )
+  /** SC-14 (slice 4 spec §7.1). */
+  @Query(SUMMARY)
   fun summary(): Flow<SaveSummary>
 
+  /** What is left to send now, read once: a user name is not changed while there is any (US-E-06.008). */
+  @Query(SUMMARY)
+  suspend fun summaryNow(): SaveSummary
+
   @Upsert
   suspend fun upsertRide(ride: RideEntity)
 
@@ -522,6 +528,66 @@ interface RideDao {
   }
 }
 
+data class KeptRideRow(val id: String, val updatedAt: Long, val points: Int)
+
+data class NoteVersion(val id: String, val updatedAt: Long)
+
+data class AskVersion(val askId: String, val updatedAt: Long?, val memoUpdatedAt: Long?)
+
+/** Reading the cloud's records in (slice 4 spec §6.3): what the merge reads of the device, and what it writes. */
+@Dao
+interface TakeoverDao {
+  @Query("SELECT COUNT(*) FROM rides WHERE status != 'ended'")
+  suspend fun activeRides(): Int
+
+  @Query("SELECT id, updatedAt, (SELECT COUNT(*) FROM route_points WHERE route_points.rideId = rides.id) AS points FROM rides")
+  suspend fun rides(): List<KeptRideRow>
+
+  @Query("SELECT id, updatedAt FROM notes")
+  suspend fun notes(): List<NoteVersion>
+
+  @Query("SELECT askId, updatedAt, memoUpdatedAt FROM asks")
+  suspend fun asks(): List<AskVersion>
+
+  @Query("DELETE FROM route_points")
+  suspend fun clearPoints()
+
+  @Query("DELETE FROM ride_segments")
+  suspend fun clearSegments()
+
+  @Query("DELETE FROM notes")
+  suspend fun clearNotes()
+
+  @Query("DELETE FROM asks")
+  suspend fun clearAsks()
+
+  @Query("DELETE FROM deletions")
+  suspend fun clearDeletions()
+
+  @Query("DELETE FROM rides")
+  suspend fun clearRides()
+
+  /** Another user's records: nothing of this one's stays, its deletions not yet sent included. */
+  @Transaction
+  suspend fun clearAll() {
+    clearPoints()
+    clearSegments()
+    clearNotes()
+    clearAsks()
+    clearDeletions()
+    clearRides()
+  }
+
+  @Insert
+  suspend fun insertPoints(points: List<RoutePointEntity>)
+
+  @Query("UPDATE rides SET distanceMeters = :distanceMeters WHERE id = :rideId")
+  suspend fun setDistance(rideId: String, distanceMeters: Double)
+
+  @Upsert
+  suspend fun upsertNote(note: NoteEntity)
+}
+
 @Database(
   entities = [RideEntity::class, SegmentEntity::class, RoutePointEntity::class, AskEntity::class, NoteEntity::class, DeletionEntity::class],
   version = 6,
@@ -531,6 +597,7 @@ abstract class RideDatabase : RoomDatabase() {
   abstract fun rides(): RideDao
   abstract fun asks(): AskDao
   abstract fun notes(): NoteDao
+  abstract fun takeover(): TakeoverDao
 
   companion object {
     fun open(context: Context): RideDatabase =
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt b/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
new file mode 100644
index 0000000..4a005e6
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt
@@ -0,0 +1,104 @@
+package com.touringproject.v2.store
+
+import androidx.room.withTransaction
+import com.touringproject.v2.api.CloudRecord
+import com.touringproject.v2.ride.RoutePoint
+import com.touringproject.v2.ride.stepMeters
+import com.touringproject.v2.sync.DeviceRecords
+import com.touringproject.v2.sync.KeptAsk
+import com.touringproject.v2.sync.KeptRide
+import com.touringproject.v2.sync.Merge
+import com.touringproject.v2.sync.TakenAsk
+import com.touringproject.v2.sync.TakeoverStore
+import com.touringproject.v2.sync.merge
+
+/**
+ * Takes the cloud's records in (slice 4 spec §6.3). The device is read, merged with the cloud and written in one
+ * transaction, so a write that fails, or a cloud record that cannot be read, leaves the device as it was. What comes in
+ * is marked as sent, so it is not sent back.
+ */
+class RoomTakeover(private val db: RideDatabase) : TakeoverStore {
+  private val takeover = db.takeover()
+  private val rides = db.rides()
+  private val asks = db.asks()
+
+  override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): Int? = db.withTransaction {
+    if (takeover.activeRides() > 0) return@withTransaction null
+    if (replace) {
+      if (rides.summaryNow().unsent > 0) return@withTransaction null
+      takeover.clearAll()
+    }
+    val merged = merge(device(), cloud, now)
+    write(merged)
+    merged.count
+  }
+
+  private suspend fun device() = DeviceRecords(
+    rides = takeover.rides().associate { it.id to KeptRide(it.updatedAt, it.points) },
+    notes = takeover.notes().associate { it.id to it.updatedAt },
+    asks = takeover.asks().associate { it.askId to KeptAsk(it.updatedAt, it.memoUpdatedAt) },
+    deletions = rides.deletions().map { it.kind to it.id }.toSet(),
+  )
+
+  // A ride the cloud removed goes with all of it, as a deletion on the device does, but leaves no mark to send.
+  private suspend fun write(merged: Merge) {
+    for (rideId in merged.gone.rides) {
+      rides.deleteAsks(rideId)
+      rides.deleteNotes(rideId)
+      rides.deletePoints(rideId)
+      rides.deleteSegments(rideId)
+      rides.deleteRideRow(rideId)
+    }
+    merged.gone.asks.forEach { asks.deleteRow(it) }
+    merged.gone.notes.forEach { db.notes().deleteRow(it) }
+    for (taken in merged.rides) {
+      val ride = taken.ride
+      val saved = rides.ride(ride.id)
+      rides.upsertRide(ride.toEntity().copy(sentUpdatedAt = taken.sentUpdatedAt, distanceMeters = saved?.distanceMeters ?: 0.0))
+      rides.deleteSegments(ride.id)
+      rides.insertSegments(ride.segments.map { SegmentEntity(ride.id, it.seq, it.startedAt, it.endedAt, it.bootCount) })
+    }
+    for (route in merged.routes) {
+      rides.deletePoints(route.rideId)
+      takeover.insertPoints(
+        route.points.map {
+          val p = it.point
+          RoutePointEntity(rideId = route.rideId, segment = p.segment, t = p.t, lat = p.lat, lon = p.lon, accuracy = p.accuracy, chunk = it.chunk)
+        },
+      )
+      takeover.setDistance(route.rideId, distance(rides.points(route.rideId).map { it.toPoint() }))
+    }
+    for (note in merged.notes) {
+      takeover.upsertNote(
+        NoteEntity(
+          note.id, note.rideId, note.at, note.latitude, note.longitude, null, null, null, note.text, note.updatedAt,
+          sentUpdatedAt = note.updatedAt, rejectedUpdatedAt = null, address = note.address, headingDegrees = note.headingDegrees,
+        ),
+      )
+    }
+    merged.asks.forEach { asks.upsert(row(it, asks.ask(it.ask.askId))) }
+  }
+
+  /**
+   * The ask as it is written: whole when the device does not keep it; otherwise the cloud's ask itself (content) and
+   * the cloud's memo (memo), each in place of the device's only when the merge took it.
+   */
+  private fun row(taken: TakenAsk, kept: AskEntity?): AskEntity {
+    val cloud = taken.ask.toEntity().copy(
+      memo = taken.ask.memo,
+      memoUpdatedAt = taken.memoUpdatedAt,
+      memoSentUpdatedAt = taken.memoUpdatedAt,
+      sentUpdatedAt = taken.ask.updatedAt,
+    )
+    if (kept == null) return cloud
+    val asked = if (taken.content) {
+      cloud.copy(memo = kept.memo, memoUpdatedAt = kept.memoUpdatedAt, memoSentUpdatedAt = kept.memoSentUpdatedAt, memoRejectedUpdatedAt = kept.memoRejectedUpdatedAt)
+    } else {
+      kept
+    }
+    if (!taken.memo) return asked
+    return asked.copy(memo = cloud.memo, memoUpdatedAt = cloud.memoUpdatedAt, memoSentUpdatedAt = cloud.memoSentUpdatedAt, memoRejectedUpdatedAt = null)
+  }
+}
+
+private fun distance(points: List<RoutePoint>): Double = points.zipWithNext { a, b -> stepMeters(a, b) }.sum()
diff --git a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
new file mode 100644
index 0000000..2011312
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
@@ -0,0 +1,16 @@
+package com.touringproject.v2.sync
+
+import com.touringproject.v2.api.CloudRecord
+
+// Reading the user's records back from the cloud (slice 4 spec §6, adr/0010): when the user name changes, and when SC-14
+// reads them again.
+
+interface TakeoverStore {
+  /**
+   * Merges the cloud's records into the device's (slice 4 spec §6.1) in one transaction; with replace, all the device
+   * keeps goes first (§6.4: another user name). Returns how many records came in or went, or null when nothing was done
+   * because a ride is recording or paused or, with replace, something is left to send (US-E-06.008). A failure throws
+   * and changes nothing.
+   */
+  suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): Int?
+}
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RoomTakeoverTest' --tests '*RoomRecordsTest'`
Expected: 7件・7件が通る

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/sync/Takeover.kt app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/test/java/com/touringproject/v2/store/RoomTakeoverTest.kt
git commit -m "feat: take the cloud's records into the device in one transaction"
```

---

### Task 5: 読み込みの係・読み込みのあいだ送信を止める・最後に保存した時刻

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/settings/LastSaved.kt`・`app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt`
- Modify: `app/src/main/java/com/touringproject/v2/sync/Takeover.kt`・`app/src/main/java/com/touringproject/v2/sync/RideSync.kt`
- Test: `app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt`・`app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt`（`LastSavedTest`）

**Interfaces:**
- Consumes: Task 1 の `RecordsApi`・`CloudPage`、Task 4 の `TakeoverStore`。
- Produces: `RideSync(store, api, online = { true }, saved: suspend () -> Unit = {}, log)`・`RideSync.sending: StateFlow<Boolean>`・`suspend fun <T> RideSync.withoutPasses(block: suspend () -> T): T`。`sealed interface TakeResult { Done(count: Int); Blocked; Failed }`・`enum class TakeOp { SWITCH, REREAD }`・`data class TakeState(running: TakeOp?, last: TakeOp?, result: TakeResult?)`・`data class Peek(userName: String, first: CloudPage)` と `val exists: Boolean`。`class Takeover(api: (String) -> RecordsApi?, store: TakeoverStore, sync: RideSync, now: () -> Long, scope: CoroutineScope, log)` の `state: StateFlow<TakeState>`・`suspend fun peek(userName): Peek?`・`fun switchTo(peek: Peek, switched: suspend (String) -> Unit)`・`fun reread(userName: String)`。`class LastSaved(store: KeyValueStore, logError = …)` の `at: StateFlow<Long?>`・`load()`・`mark(at: Long)`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
index fbf5dbc..a979411 100644
--- a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
@@ -183,3 +183,28 @@ class ApiKeyStoreTest {
     assertEquals("old-key", ApiKeyStore(store, cipher).load())
   }
 }
+
+class LastSavedTest {
+  @Test
+  fun the_last_save_is_kept_beside_the_settings() = runTest {
+    val store = FakeStore()
+    LastSaved(store).mark(1_700_000_000_000)
+    val again = LastSaved(store)
+    assertEquals(null, again.at.value)
+    again.load()
+    assertEquals(1_700_000_000_000, again.at.value)
+  }
+
+  @Test
+  fun a_store_that_cannot_be_read_leaves_it_unknown() = runTest {
+    val broken = object : KeyValueStore {
+      override suspend fun get(key: String): String? = throw java.io.IOException("corrupt")
+      override suspend fun set(key: String, value: String?) = throw java.io.IOException("read-only")
+    }
+    val saved = LastSaved(broken) { _, _ -> }
+    saved.load()
+    assertEquals(null, saved.at.value)
+    saved.mark(5)
+    assertEquals(5L, saved.at.value)
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
index 86149a7..67f3ba1 100644
--- a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
@@ -134,7 +134,8 @@ private class World {
     }
   }
 
-  val sync = RideSync(store, { if (hasKey) api else null }, { online }) { _, _ -> }
+  var saves = 0
+  val sync = RideSync(store, { if (hasKey) api else null }, { online }, saved = { saves += 1 }) { _, _ -> }
 }
 
 class RideSyncTest {
@@ -476,4 +477,52 @@ class RideSyncTest {
     w.sync.pass()
     assertEquals(listOf("ride/r1:recording", "route/r1/0:300", "unreached/u1:r1"), w.calls)
   }
+
+  // Slice 4 spec §7.1: a pass that ran to its end is SC-14's last save, even with nothing to send; one cut short is not.
+  @Test
+  fun only_a_pass_that_ran_to_its_end_counts_as_saved() = runTest {
+    val w = World()
+    w.sync.pass()
+    assertEquals(1, w.saves)
+    w.add(recording.end(5_000, EndReason.MANUAL, 5_000), points = 10)
+    w.fail["route/r1/0:10"] = ApiErrorKind.NETWORK
+    w.sync.pass()
+    w.online = false
+    w.sync.pass()
+    w.online = true
+    w.hasKey = false
+    w.sync.pass()
+    assertEquals(1, w.saves)
+  }
+
+  @Test
+  fun sending_is_told_while_a_pass_talks_to_the_backend() = runTest {
+    val w = World()
+    w.gate = CompletableDeferred()
+    val job = launch { w.sync.pass() }
+    runCurrent()
+    assertTrue(w.sync.sending.value)
+    w.gate!!.complete(Unit)
+    runCurrent()
+    assertEquals(false, w.sync.sending.value)
+    job.cancel()
+  }
+
+  // Slice 4 spec §6.3: while the cloud's records are read in, no pass runs; the triggers meanwhile make one after.
+  @Test
+  fun no_pass_runs_while_records_are_read_in() = runTest {
+    val w = World()
+    val job = launch { w.sync.run() }
+    val reading = CompletableDeferred<Unit>()
+    val read = launch { w.sync.withoutPasses { reading.await() } }
+    runCurrent()
+    w.sync.request()
+    runCurrent()
+    assertEquals(0, w.passes)
+    reading.complete(Unit)
+    runCurrent()
+    assertEquals(1, w.passes)
+    read.cancel()
+    job.cancel()
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
new file mode 100644
index 0000000..47059b5
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
@@ -0,0 +1,162 @@
+package com.touringproject.v2.sync
+
+import com.touringproject.v2.api.ApiError
+import com.touringproject.v2.api.ApiErrorKind
+import com.touringproject.v2.api.CloudDeleted
+import com.touringproject.v2.api.CloudPage
+import com.touringproject.v2.api.CloudRecord
+import com.touringproject.v2.api.RecordsApi
+import com.touringproject.v2.ride.RoutePoint
+import kotlinx.coroutines.CompletableDeferred
+import kotlinx.coroutines.launch
+import kotlinx.coroutines.test.TestScope
+import kotlinx.coroutines.test.runCurrent
+import kotlinx.coroutines.test.runTest
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertFalse
+import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
+import org.junit.Test
+
+private fun mark(id: String) = CloudDeleted("note", id, "r1", "2026-10-22T03:00:00Z")
+
+/** A sync with nothing to send whose passes are counted as it asks for its client. */
+private val nothingToSend = object : SyncStore {
+  override suspend fun unsent() = emptyList<Unsent>()
+  override suspend fun points(rideId: String, from: Int, until: Int) = emptyList<RoutePoint>()
+  override suspend fun rideSent(rideId: String, updatedAt: Long) = Unit
+  override suspend fun rideRefused(rideId: String, updatedAt: Long) = Unit
+  override suspend fun chunkSent(rideId: String, chunk: ChunkRange, refused: Boolean) = Unit
+  override suspend fun deletions() = emptyList<PendingDeletion>()
+  override suspend fun deletionSent(deletion: PendingDeletion) = Unit
+  override suspend fun unsentAskMemos() = emptyList<UnsentAskMemo>()
+  override suspend fun askMemoSent(askId: String, updatedAt: Long) = Unit
+  override suspend fun askMemoRefused(askId: String, updatedAt: Long) = Unit
+  override suspend fun unsentNotes() = emptyList<UnsentNote>()
+  override suspend fun noteSent(noteId: String, updatedAt: Long, address: String?, headingDegrees: Double?) = Unit
+  override suspend fun noteRefused(noteId: String, updatedAt: Long) = Unit
+  override suspend fun unsentUnreached() = emptyList<UnsentUnreached>()
+  override suspend fun unreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?) = Unit
+  override suspend fun unreachedRefused(askId: String, updatedAt: Long) = Unit
+}
+
+private class Cloud(val scope: TestScope) {
+  /** Pages by user name, then by cursor (null for the first). */
+  val pages = mutableMapOf<String, Map<String?, CloudPage>>()
+  val reads = mutableListOf<String>()
+  /** The cursors whose page fails (null for the first page). */
+  var failOn = setOf<String?>()
+  var gate: CompletableDeferred<Unit>? = null
+  val taken = mutableListOf<Pair<List<CloudRecord>, Boolean>>()
+  var takes: Int? = 2
+  val switched = mutableListOf<String>()
+  var passes = 0
+
+  val store = object : TakeoverStore {
+    override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): Int? {
+      taken += cloud to replace
+      return takes
+    }
+  }
+
+  fun api(user: String) = object : RecordsApi {
+    override suspend fun records(cursor: String?): CloudPage {
+      reads += "$user:$cursor"
+      gate?.await()
+      if (cursor in failOn) throw ApiError(ApiErrorKind.NETWORK)
+      return pages.getValue(user).getValue(cursor)
+    }
+  }
+
+  var hasKey = true
+  val sync = RideSync(nothingToSend, { passes += 1; null }) { _, _ -> }
+  val takeover = Takeover({ if (hasKey) api(it) else null }, store, sync, { 1_000L }, scope) { _, _ -> }
+}
+
+class TakeoverTest {
+  @Test
+  fun a_peek_tells_whether_the_name_has_records() = runTest {
+    val c = Cloud(this)
+    c.pages["empty"] = mapOf(null to CloudPage(emptyList(), null))
+    c.pages["taro01"] = mapOf(null to CloudPage(listOf(mark("n1")), null))
+    c.pages["more"] = mapOf(null to CloudPage(emptyList(), "c2"))
+    assertFalse(c.takeover.peek("empty")!!.exists)
+    assertTrue(c.takeover.peek("taro01")!!.exists)
+    assertTrue(c.takeover.peek("more")!!.exists)
+    c.failOn = setOf(null)
+    assertNull(c.takeover.peek("taro01"))
+    c.failOn = emptySet()
+    c.hasKey = false
+    assertNull(c.takeover.peek("taro01"))
+  }
+
+  // Slice 4 spec §6.4: every page is read, the device's records are replaced with them, and then the name is saved.
+  @Test
+  fun a_switch_reads_every_page_then_replaces_the_records_and_saves_the_name() = runTest {
+    val c = Cloud(this)
+    c.pages["taro01"] = mapOf(null to CloudPage(listOf(mark("n1")), "c2"), "c2" to CloudPage(listOf(mark("n2")), null))
+    val peek = c.takeover.peek("taro01")!!
+    c.takeover.switchTo(peek) { c.switched += it }
+    assertEquals(TakeOp.SWITCH, c.takeover.state.value.running)
+    runCurrent()
+    assertEquals(listOf("taro01:null", "taro01:c2"), c.reads)
+    assertEquals(listOf(listOf(mark("n1"), mark("n2")) to true), c.taken)
+    assertEquals(listOf("taro01"), c.switched)
+    assertEquals(TakeState(null, TakeOp.SWITCH, TakeResult.Done(2)), c.takeover.state.value)
+  }
+
+  @Test
+  fun a_page_that_cannot_be_read_changes_nothing() = runTest {
+    val c = Cloud(this)
+    c.pages["taro01"] = mapOf(null to CloudPage(listOf(mark("n1")), "c2"))
+    c.failOn = setOf("c2")
+    c.takeover.switchTo(c.takeover.peek("taro01")!!) { c.switched += it }
+    runCurrent()
+    assertEquals(emptyList<Any>(), c.taken)
+    assertEquals(emptyList<String>(), c.switched)
+    assertEquals(TakeResult.Failed, c.takeover.state.value.result)
+  }
+
+  // US-E-06.008: something left to send (found in the write's own transaction) keeps the name as it was.
+  @Test
+  fun a_blocked_switch_keeps_the_name() = runTest {
+    val c = Cloud(this)
+    c.pages["taro01"] = mapOf(null to CloudPage(emptyList(), null))
+    c.takes = null
+    c.takeover.switchTo(c.takeover.peek("taro01")!!) { c.switched += it }
+    runCurrent()
+    assertEquals(emptyList<String>(), c.switched)
+    assertEquals(TakeResult.Blocked, c.takeover.state.value.result)
+  }
+
+  @Test
+  fun a_reread_merges_the_current_names_records() = runTest {
+    val c = Cloud(this)
+    c.pages["rider01"] = mapOf(null to CloudPage(listOf(mark("n1")), null))
+    c.takeover.reread("rider01")
+    runCurrent()
+    assertEquals(listOf(listOf(mark("n1")) to false), c.taken)
+    assertEquals(TakeState(null, TakeOp.REREAD, TakeResult.Done(2)), c.takeover.state.value)
+  }
+
+  // Slice 4 spec §6.3: no pass runs while the records are read in; one runs after, for what came in to be sent.
+  @Test
+  fun no_pass_runs_during_a_read_and_one_runs_after() = runTest {
+    val c = Cloud(this)
+    c.pages["rider01"] = mapOf(null to CloudPage(emptyList(), null))
+    val passes = launch { c.sync.run() }
+    c.gate = CompletableDeferred()
+    c.takeover.reread("rider01")
+    runCurrent()
+    c.sync.request()
+    runCurrent()
+    assertEquals(0, c.passes)
+    c.takeover.reread("rider01")
+    c.gate!!.complete(Unit)
+    runCurrent()
+    // The pass asked for during the read, then the one the read asks for.
+    assertEquals(2, c.passes)
+    assertEquals(1, c.taken.size)
+    passes.cancel()
+  }
+}
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TakeoverTest' --tests '*RideSyncTest' --tests '*LastSavedTest'`
Expected: コンパイルで落ちる（`Takeover`・`withoutPasses`・`LastSaved` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/settings/LastSaved.kt b/app/src/main/java/com/touringproject/v2/settings/LastSaved.kt
new file mode 100644
index 0000000..085dd66
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/settings/LastSaved.kt
@@ -0,0 +1,39 @@
+package com.touringproject.v2.settings
+
+import android.util.Log
+import kotlinx.coroutines.CancellationException
+import kotlinx.coroutines.flow.MutableStateFlow
+import kotlinx.coroutines.flow.StateFlow
+import kotlinx.coroutines.flow.asStateFlow
+
+const val LAST_SAVED_KEY = "trv2.lastSavedAt"
+
+/**
+ * When a pass of the sync last ran to its end (SC-14's 最終保存, slice 4 spec §7.1), kept beside the settings in the
+ * device's time. A store that cannot be read or written leaves it unknown, as a fresh install has it.
+ */
+class LastSaved(
+  private val store: KeyValueStore,
+  private val logError: (String, Throwable) -> Unit = { message, e -> Log.w("trv2.settings", message, e) },
+) {
+  private val state = MutableStateFlow<Long?>(null)
+  val at: StateFlow<Long?> = state.asStateFlow()
+
+  suspend fun load() {
+    state.value = guard { store.get(LAST_SAVED_KEY) }?.toLongOrNull()
+  }
+
+  suspend fun mark(at: Long) {
+    state.value = at
+    guard { store.set(LAST_SAVED_KEY, at.toString()) }
+  }
+
+  private suspend fun <T> guard(block: suspend () -> T): T? = try {
+    block()
+  } catch (e: CancellationException) {
+    throw e
+  } catch (e: Exception) {
+    logError("last saved store failed", e)
+    null
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
index 33d97b0..304c009 100644
--- a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
@@ -13,12 +13,17 @@ import com.touringproject.v2.ride.RoutePoint
 import kotlinx.coroutines.CancellationException
 import kotlinx.coroutines.channels.Channel
 import kotlinx.coroutines.flow.Flow
+import kotlinx.coroutines.flow.MutableStateFlow
+import kotlinx.coroutines.flow.StateFlow
+import kotlinx.coroutines.flow.asStateFlow
 import kotlinx.coroutines.flow.combine
 import kotlinx.coroutines.flow.distinctUntilChanged
 import kotlinx.coroutines.flow.drop
 import kotlinx.coroutines.flow.filter
 import kotlinx.coroutines.flow.flow
 import kotlinx.coroutines.flow.map
+import kotlinx.coroutines.sync.Mutex
+import kotlinx.coroutines.sync.withLock
 import kotlinx.serialization.SerializationException
 
 /** A ride that may have something left to send, with what the Backend already has of it. */
@@ -100,6 +105,7 @@ private enum class Reply { TAKEN, REFUSED, GONE }
  * before the memos, so a memo on one finds its ask at the Backend. Passes run one at a time; the ones asked for while
  * a pass runs fold into one more. A failure other than a refusal ends the pass, and the next trigger tries again;
  * there is no timer of its own. Without a network a pass does not try at all: the network coming back is a trigger.
+ * While the cloud's records are read in, no pass runs (slice 4 spec §6.3).
  */
 class RideSync(
   private val store: SyncStore,
@@ -107,10 +113,17 @@ class RideSync(
   private val api: () -> RideApi?,
   /** Whether the device has a network now (slice 4 spec §5.2). */
   private val online: () -> Boolean = { true },
+  /** A pass ran to its end, nothing it tried having failed: SC-14's 最後に保存した時刻 (slice 4 spec §7.1). */
+  private val saved: suspend () -> Unit = {},
   private val log: (event: String, data: Map<String, Any?>) -> Unit,
 ) {
   private val requests = Channel<Unit>(Channel.CONFLATED)
   private var points = 0
+  private val passing = Mutex()
+  private val sendingNow = MutableStateFlow(false)
+
+  /** True while a pass talks to the Backend (SC-14's 今すぐ保存 waits for it). */
+  val sending: StateFlow<Boolean> = sendingNow.asStateFlow()
 
   /** A trigger: something changed, the app came to the front, it started, or the key or user name changed. Safe from any thread. */
   fun request() {
@@ -128,29 +141,47 @@ class RideSync(
     for (request in requests) pass()
   }
 
-  suspend fun pass() {
-    if (!online()) return
-    val client = api() ?: return
-    val deletions = read("deletions") { store.deletions() } ?: return
+  suspend fun pass() = passing.withLock {
+    if (!online()) return@withLock
+    val client = api() ?: return@withLock
+    sendingNow.value = true
+    val done = try {
+      send(client)
+    } finally {
+      sendingNow.value = false
+    }
+    if (done) saved()
+  }
+
+  /**
+   * Runs block with no pass under way or begun meanwhile (slice 4 spec §6.3): one under way finishes first, and the
+   * triggers that come meanwhile wait until block is done.
+   */
+  suspend fun <T> withoutPasses(block: suspend () -> T): T = passing.withLock { block() }
+
+  // False when something failed and the pass ended early.
+  private suspend fun send(client: RideApi): Boolean {
+    val deletions = read("deletions") { store.deletions() } ?: return false
     for (deletion in deletions) {
-      if (!attempt(deletion.id) { sendDeletion(client, deletion) }) return
+      if (!attempt(deletion.id) { sendDeletion(client, deletion) }) return false
     }
-    val rides = read("unsent") { store.unsent() } ?: return
+    val rides = read("unsent") { store.unsent() } ?: return false
     for (unsent in rides) {
-      if (!attempt(unsent.ride.id) { sendRide(client, unsent) }) return
+      if (!attempt(unsent.ride.id) { sendRide(client, unsent) }) return false
     }
-    val notes = read("notes") { store.unsentNotes() } ?: return
+    val notes = read("notes") { store.unsentNotes() } ?: return false
     for (note in notes) {
-      if (!attempt(note.id) { sendNote(client, note) }) return
+      if (!attempt(note.id) { sendNote(client, note) }) return false
     }
-    val unreached = read("unreached") { store.unsentUnreached() } ?: return
+    val unreached = read("unreached") { store.unsentUnreached() } ?: return false
     for (ask in unreached) {
-      if (!attempt(ask.askId) { sendUnreached(client, ask) }) return
+      if (!attempt(ask.askId) { sendUnreached(client, ask) }) return false
     }
-    val memos = read("ask_memos") { store.unsentAskMemos() } ?: return
+    val memos = read("ask_memos") { store.unsentAskMemos() } ?: return false
     for (memo in memos) {
-      if (!attempt(memo.askId) { sendAskMemo(client, memo) }) return
+      if (!attempt(memo.askId) { sendAskMemo(client, memo) }) return false
     }
+    return true
   }
 
   private suspend fun <T> read(op: String, block: suspend () -> T): T? = try {
diff --git a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
index 2011312..553b0f1 100644
--- a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
@@ -1,6 +1,14 @@
 package com.touringproject.v2.sync
 
+import com.touringproject.v2.api.CloudPage
 import com.touringproject.v2.api.CloudRecord
+import com.touringproject.v2.api.RecordsApi
+import kotlinx.coroutines.CancellationException
+import kotlinx.coroutines.CoroutineScope
+import kotlinx.coroutines.flow.MutableStateFlow
+import kotlinx.coroutines.flow.StateFlow
+import kotlinx.coroutines.flow.asStateFlow
+import kotlinx.coroutines.launch
 
 // Reading the user's records back from the cloud (slice 4 spec §6, adr/0010): when the user name changes, and when SC-14
 // reads them again.
@@ -14,3 +22,99 @@ interface TakeoverStore {
    */
   suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): Int?
 }
+
+/** What a read of the cloud came to. */
+sealed interface TakeResult {
+  /** The records are in: count came in or went. A user name changed is saved. */
+  data class Done(val count: Int) : TakeResult
+
+  /** Nothing changed: a ride is recording or paused, or something is left to send. */
+  data object Blocked : TakeResult
+
+  /** Nothing changed: the cloud could not be read whole, or what it said could not be written. */
+  data object Failed : TakeResult
+}
+
+enum class TakeOp { SWITCH, REREAD }
+
+/** running is the read under way; last and result the one before, for the screen that started it to tell. */
+data class TakeState(val running: TakeOp? = null, val last: TakeOp? = null, val result: TakeResult? = null)
+
+/** The first page for a user name, read before DL-03 asks (slice 4 spec §6.4); exists picks which of its texts. */
+data class Peek(val userName: String, val first: CloudPage) {
+  val exists: Boolean get() = first.items.isNotEmpty() || first.cursor != null
+}
+
+/**
+ * Reads the cloud's records in. Every page is read before anything is written, and no pass of the sync runs from the
+ * first read to the last write, so what came in and its sent markers never part (slice 4 spec §6.3). A read runs in
+ * scope, so it goes on when its screen goes away (§7.2); one at a time.
+ */
+class Takeover(
+  /** The client for a user name with the current key, or null while there is no key or no API URL. */
+  private val api: (userName: String) -> RecordsApi?,
+  private val store: TakeoverStore,
+  private val sync: RideSync,
+  private val now: () -> Long,
+  private val scope: CoroutineScope,
+  private val log: (event: String, data: Map<String, Any?>) -> Unit,
+) {
+  private val stateNow = MutableStateFlow(TakeState())
+  val state: StateFlow<TakeState> = stateNow.asStateFlow()
+
+  /** null when the page could not be read. */
+  suspend fun peek(userName: String): Peek? = try {
+    api(userName)?.let { Peek(userName, it.records(null)) }
+  } catch (e: CancellationException) {
+    throw e
+  } catch (e: Exception) {
+    log("takeover_failed", mapOf("op" to "peek", "error" to e.toString()))
+    null
+  }
+
+  /**
+   * SC-18 after DL-03: the device's records go and the name's come in (§6.4), then switched saves the name; nothing
+   * changes when the read or the write fails.
+   */
+  fun switchTo(peek: Peek, switched: suspend (userName: String) -> Unit) = start(TakeOp.SWITCH) {
+    val records = readAll(peek.userName, peek.first)
+    val count = store.take(records, replace = true, now()) ?: return@start TakeResult.Blocked
+    switched(peek.userName)
+    TakeResult.Done(count)
+  }
+
+  /** SC-14's クラウドから読み直す: the current name's records, merged with the device's. */
+  fun reread(userName: String) = start(TakeOp.REREAD) {
+    store.take(readAll(userName, null), replace = false, now())?.let { TakeResult.Done(it) } ?: TakeResult.Blocked
+  }
+
+  private fun start(op: TakeOp, block: suspend () -> TakeResult) {
+    if (stateNow.value.running != null) return
+    stateNow.value = stateNow.value.copy(running = op)
+    scope.launch {
+      val result = try {
+        sync.withoutPasses { block() }
+      } catch (e: CancellationException) {
+        throw e
+      } catch (e: Exception) {
+        log("takeover_failed", mapOf("op" to op.name, "error" to e.toString()))
+        TakeResult.Failed
+      }
+      log("takeover_done", mapOf("op" to op.name, "result" to result.toString()))
+      stateNow.value = TakeState(running = null, last = op, result = result)
+      // What came in to be sent (a ride that ended here) goes now.
+      sync.request()
+    }
+  }
+
+  private suspend fun readAll(userName: String, first: CloudPage?): List<CloudRecord> {
+    val client = api(userName) ?: throw IllegalStateException("no key or API URL")
+    var page = first ?: client.records(null)
+    val items = page.items.toMutableList()
+    while (true) {
+      val cursor = page.cursor ?: return items
+      page = client.records(cursor)
+      items += page.items
+    }
+  }
+}
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TakeoverTest' --tests '*RideSyncTest' --tests '*LastSavedTest'`
Expected: 6件・28件・2件が通る

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/sync/Takeover.kt app/src/main/java/com/touringproject/v2/sync/RideSync.kt app/src/main/java/com/touringproject/v2/settings/LastSaved.kt app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
git commit -m "feat: read the cloud's records in with no pass between, and keep the last save"
```

---

### Task 6: SC-14 と設定の行

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt`・`app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt`
- Modify: `app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt`（`DataUi`・`DataScreen`・設定の行・一覧のスクロール）・`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`（`DataKey`）・`app/src/main/java/com/touringproject/v2/AppGraph.kt`（`lastSaved`・`saveSummary`・`takeover`）
- Test: `app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt`（`SettingsScreensTest`）・`app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt`

**Interfaces:**
- Consumes: Task 3 の `SaveSummary`、Task 5 の `Takeover`・`TakeResult`・`TakeOp`・`RideSync.sending`・`LastSaved`。
- Produces: `fun unsentBreakdown(summary: SaveSummary): String`・`fun lastSavedLabel(at: Long?, now: Long, zone: ZoneId): String`・`fun saveRowValue(summary: SaveSummary): String`・`fun rereadMessage(result: TakeResult): String`・`fun switchMessage(result: TakeResult): String`。`data class DataUi(summary, lastSaved, sending, recording, active, reading, userName, message, recordings)`・`@Composable fun DataScreen(ui, onSave, onUser, onReread, modifier)`。`SettingsScreen(…, version, modifier, saved: String = "", onData: () -> Unit = {})`。`AppGraph.lastSaved`・`AppGraph.saveSummary: StateFlow<SaveSummary?>`・`AppGraph.takeover`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
index 2fbaad5..6588c5f 100644
--- a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
@@ -5,6 +5,7 @@ import androidx.compose.ui.test.junit4.createAndroidComposeRule
 import androidx.compose.ui.test.onNodeWithTag
 import androidx.compose.ui.test.onNodeWithText
 import androidx.compose.ui.test.performClick
+import androidx.compose.ui.test.performScrollTo
 import androidx.compose.ui.test.performTextInput
 import androidx.test.ext.junit.runners.AndroidJUnit4
 import com.touringproject.v2.MainActivity
@@ -35,7 +36,7 @@ class AppUiTest {
   @Test
   fun back_goes_back_within_settings_then_to_home() {
     rule.onNodeWithTag("tab-SETTINGS").performClick()
-    rule.onNodeWithText("回答の音量").performClick()
+    rule.onNodeWithText("回答の音量").performScrollTo().performClick()
     rule.onNodeWithText("回答の音声を上げる量").assertExists()
     back()
     rule.onNodeWithText("走行の記録").assertExists()
@@ -43,6 +44,16 @@ class AppUiTest {
     rule.onNodeWithTag("tapToTalk").assertExists()
   }
 
+  // Slice 4 spec §7.1: SC-14 opens from the settings, and with nothing kept all is saved.
+  @Test
+  fun the_data_screen_opens_from_the_settings() {
+    rule.onNodeWithTag("tab-SETTINGS").performClick()
+    rule.waitUntil(5_000) { rule.onAllNodes(androidx.compose.ui.test.hasText("保存済み")).fetchSemanticsNodes().isNotEmpty() }
+    rule.onNodeWithText("☁️ データの保存").performClick()
+    rule.onNodeWithTag("saveState").assertExists()
+    rule.onNodeWithText("クラウドから読み直す").assertExists()
+  }
+
   @Test
   fun the_records_tab_lists_the_kept_rides_and_home_keeps_its_place() {
     val graph = (rule.activity.application as TouringApp).graph
diff --git a/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
new file mode 100644
index 0000000..fe9521b
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
@@ -0,0 +1,48 @@
+package com.touringproject.v2.ui
+
+import com.touringproject.v2.records.SaveSummary
+import com.touringproject.v2.sync.TakeResult
+import org.junit.Assert.assertEquals
+import org.junit.Test
+import java.time.ZoneId
+import java.time.ZonedDateTime
+
+private val TOKYO = ZoneId.of("Asia/Tokyo")
+
+private fun ms(day: Int, hour: Int, minute: Int) = ZonedDateTime.of(2026, 10, day, hour, minute, 0, 0, TOKYO).toInstant().toEpochMilli()
+
+class SavingLabelsTest {
+  // Slice 4 spec §7.1 (the breakdown settled in plan 3): only the kinds with any, in one line.
+  @Test
+  fun the_breakdown_names_the_kinds_left_to_send() {
+    assertEquals(
+      "質問できなかった地点 1件・走行 2本・地点メモ 3件・メモ 1件・削除 1件",
+      unsentBreakdown(SaveSummary(unreached = 1, unsentRides = 2, notes = 3, memos = 1, deletions = 1)),
+    )
+    assertEquals("走行 1本・削除 2件", unsentBreakdown(SaveSummary(unsentRides = 1, deletions = 2, rides = 5)))
+  }
+
+  @Test
+  fun the_last_save_shows_its_day_unless_it_was_today() {
+    assertEquals("最終保存 10:22", lastSavedLabel(ms(22, 10, 22), ms(22, 18, 0), TOKYO))
+    assertEquals("最終保存 10月21日 23:05", lastSavedLabel(ms(21, 23, 5), ms(22, 8, 0), TOKYO))
+    assertEquals("まだ保存していません", lastSavedLabel(null, ms(22, 8, 0), TOKYO))
+  }
+
+  @Test
+  fun the_settings_row_tells_whether_anything_is_left() {
+    assertEquals("保存済み", saveRowValue(SaveSummary(rides = 3, asks = 9)))
+    assertEquals("未送信あり", saveRowValue(SaveSummary(memos = 1)))
+  }
+
+  @Test
+  fun what_a_read_came_to_is_told_on_its_screen() {
+    assertEquals("12件の記録を読み込みました", rereadMessage(TakeResult.Done(12)))
+    assertEquals("新しい記録はありませんでした", rereadMessage(TakeResult.Done(0)))
+    assertEquals("走行を終えてから読み直せます", rereadMessage(TakeResult.Blocked))
+    assertEquals("読み込めませんでした", rereadMessage(TakeResult.Failed))
+    assertEquals("ユーザー名を変えました", switchMessage(TakeResult.Done(0)))
+    assertEquals("未送信の記録があるため、変えられませんでした", switchMessage(TakeResult.Blocked))
+    assertEquals("読み込めませんでした。ユーザー名は変えていません", switchMessage(TakeResult.Failed))
+  }
+}
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index 5a3b462..79948f0 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -13,6 +13,7 @@ import androidx.compose.ui.test.junit4.createComposeRule
 import androidx.compose.ui.test.onNodeWithTag
 import androidx.compose.ui.test.onNodeWithText
 import androidx.compose.ui.test.performClick
+import androidx.compose.ui.test.performScrollTo
 import androidx.compose.ui.test.performTextClearance
 import androidx.compose.ui.test.performTextInput
 import androidx.test.ext.junit.runners.AndroidJUnit4
@@ -24,10 +25,12 @@ import com.touringproject.v2.audio.MediaVolume
 import com.touringproject.v2.recordings.TRIAL_IDLE
 import com.touringproject.v2.recordings.TrialPhase
 import com.touringproject.v2.recordings.TrialState
+import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.settings.LaunchableApp
 import com.touringproject.v2.settings.Settings
 import org.junit.Assert.assertEquals
 import org.junit.Assert.assertNull
+import org.junit.Assert.assertTrue
 import org.junit.Rule
 import org.junit.Test
 import org.junit.runner.RunWith
@@ -216,6 +219,59 @@ class SettingsScreensTest {
     assertEquals(listOf("rider02"), changed)
   }
 
+  private val data = DataUi(SaveSummary(rides = 3, asks = 19), "最終保存 10:22", false, false, false, false, "rider01", null, 10)
+
+  // Slice 4 spec §7.1: saved, with the last save, and the counts.
+  @Test
+  fun sc14_tells_all_is_saved_and_what_is_kept() {
+    rule.setContent { DataScreen(data, {}, {}, {}) }
+    rule.onNodeWithTag("saveState").assertTextEquals("● すべてクラウドに保存済み")
+    rule.onNodeWithText("最終保存 10:22").assertExists()
+    rule.onNodeWithTag("saveNow").assertDoesNotExist()
+    rule.onNodeWithText("19").assertExists()
+    rule.onNodeWithText("10 / 10").performScrollTo().assertExists()
+  }
+
+  @Test
+  fun sc14_tells_what_is_left_and_sends_it_now() {
+    var saves = 0
+    var sending by mutableStateOf(false)
+    rule.setContent { DataScreen(data.copy(summary = SaveSummary(unreached = 1, unsentRides = 2), sending = sending), { saves += 1 }, {}, {}) }
+    rule.onNodeWithTag("saveState").assertTextEquals("● 未送信の記録があります")
+    rule.onNodeWithTag("unsentBreakdown").assertTextEquals("質問できなかった地点 1件・走行 2本。通信できるようになると自動で送ります。")
+    rule.onNodeWithTag("saveNow").performClick()
+    assertEquals(1, saves)
+    sending = true
+    rule.onNodeWithTag("saveNow").assertIsNotEnabled()
+    rule.onNodeWithText("送っています…").assertExists()
+  }
+
+  // Reading again waits for the ride's end (decided in plan 3), and for a read under way.
+  @Test
+  fun sc14_reads_the_cloud_again_unless_a_ride_records_or_a_read_runs() {
+    var rereads = 0
+    var ui by mutableStateOf(data)
+    rule.setContent { DataScreen(ui, {}, {}, { rereads += 1 }) }
+    rule.onNodeWithTag("reread").performClick()
+    assertEquals(1, rereads)
+    ui = data.copy(reading = true)
+    rule.onNodeWithTag("reread").assertIsNotEnabled()
+    rule.onNodeWithText("読み込んでいます…").assertExists()
+    ui = data.copy(active = true, recording = true, message = "12件の記録を読み込みました")
+    rule.onNodeWithTag("reread").assertIsNotEnabled()
+    rule.onNodeWithText("走行を終えてから読み直せます").assertExists()
+    rule.onNodeWithTag("recordingNote").assertExists()
+    rule.onNodeWithTag("dataMessage").assertTextEquals("12件の記録を読み込みました")
+  }
+
+  @Test
+  fun the_settings_list_leads_to_the_data_screen() {
+    var opened = false
+    rule.setContent { SettingsScreen(Settings("rider01"), null, {}, {}, {}, {}, {}, {}, "0.2.0", saved = "未送信あり", onData = { opened = true }) }
+    rule.onNodeWithText("未送信あり").performClick()
+    assertTrue(opened)
+  }
+
   @Test
   fun choosing_a_return_app_also_remembers_it() {
     var updated: Settings? = null
@@ -235,7 +291,7 @@ class SettingsScreensTest {
     }
     rule.onNodeWithText("最長 12時間").performClick()
     rule.onNodeWithText("+3dB").performClick()
-    rule.onNodeWithText("録音の確認").performClick()
+    rule.onNodeWithText("録音の確認").performScrollTo().performClick()
     assertEquals(listOf("ride", "volume", "recordings"), opened)
   }
 
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SettingsScreensTest' --tests '*SavingLabelsTest' --tests '*AppUiTest'`
Expected: コンパイルで落ちる（`DataScreen`・`unsentBreakdown` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 04ac060..a901445 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -37,6 +37,7 @@ import com.touringproject.v2.recordings.TrialController
 import com.touringproject.v2.recordings.TrialDeps
 import com.touringproject.v2.recordings.TrialState
 import com.touringproject.v2.records.RideListItem
+import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.records.activeAskCount
 import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.RideController
@@ -50,6 +51,7 @@ import com.touringproject.v2.settings.ApiKeyStore
 import com.touringproject.v2.settings.DEFAULT_MAX_RECORDING_HOURS
 import com.touringproject.v2.settings.DataStoreKeyValueStore
 import com.touringproject.v2.settings.KeystoreCipher
+import com.touringproject.v2.settings.LastSaved
 import com.touringproject.v2.settings.SettingsRepository
 import com.touringproject.v2.settings.maxRecordingChanges
 import com.touringproject.v2.store.RideDatabase
@@ -59,7 +61,9 @@ import com.touringproject.v2.store.RoomNotes
 import com.touringproject.v2.store.RoomRecords
 import com.touringproject.v2.store.RoomRideStore
 import com.touringproject.v2.store.RoomSyncStore
+import com.touringproject.v2.store.RoomTakeover
 import com.touringproject.v2.sync.RideSync
+import com.touringproject.v2.sync.Takeover
 import com.touringproject.v2.sync.credentialChanges
 import com.touringproject.v2.sync.reconnections
 import com.touringproject.v2.voice.VOICE_IDLE
@@ -113,6 +117,9 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   /** Whether the device has a network now: SC-19's voice input, the ask loop and the sync follow it. */
   val connectivity = Connectivity(context)
 
+  /** When a pass of the sync last ran to its end (SC-14). */
+  val lastSaved = LastSaved(store)
+
   /** Sends rides, routes, memos, point memos, unreached asks and deletions; a pass runs on each trigger (slice 2 spec §5.3). */
   val sync = RideSync(
     RoomSyncStore(database.rides(), database.asks(), database.notes()),
@@ -121,8 +128,25 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       val user = settings.settings.value?.userName
       if (apiBaseUrl.isEmpty() || key == null || user == null) null else ApiClient(apiBaseUrl, key, user, http)
     },
-    log = { event, data -> Log.i("trv2.sync", "$event $data") },
     online = { connectivity.online.value },
+    saved = { lastSaved.mark(System.currentTimeMillis()) },
+    log = { event, data -> Log.i("trv2.sync", "$event $data") },
+  )
+
+  /** SC-14 and SC-18: what is left to send, and how much is kept (slice 4 spec §7.1). */
+  val saveSummary: StateFlow<SaveSummary?> = records.summary.stateIn(scope, SharingStarted.WhileSubscribed(5_000), null)
+
+  /** Reads the user's records in from the cloud: SC-18's change of user name and SC-14's read again (slice 4 spec §6). */
+  val takeover = Takeover(
+    api = { user ->
+      val key = apiKeys.current()
+      if (apiBaseUrl.isEmpty() || key == null) null else ApiClient(apiBaseUrl, key, user, http)
+    },
+    store = RoomTakeover(database),
+    sync = sync,
+    now = System::currentTimeMillis,
+    scope = scope,
+    log = { event, data -> Log.i("trv2.sync", "$event $data") },
   )
 
   /** SC-07 and SC-08 change kept asks through here; each change is something new to send (slice 3 spec §5.1). */
@@ -287,6 +311,7 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     scope.launch {
       settings.load()
       apiKeys.load()
+      lastSaved.load()
       readiness.settingsLoaded()
       // The start of the app is a trigger; before this the key and the user name are not known.
       sync.request()
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 22ac80e..6b2551f 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -38,7 +38,10 @@ import com.touringproject.v2.BuildConfig
 import com.touringproject.v2.api.ApiClient
 import com.touringproject.v2.ask.isBusy
 import com.touringproject.v2.records.NoteDraft
+import com.touringproject.v2.records.SaveSummary
+import com.touringproject.v2.ride.RideStatus
 import com.touringproject.v2.settings.LaunchableApp
+import com.touringproject.v2.sync.TakeOp
 import kotlinx.coroutines.delay
 import kotlinx.coroutines.launch
 import java.time.ZoneId
@@ -52,6 +55,7 @@ import kotlinx.serialization.Serializable
 @Serializable data object VolumeKey : NavKey
 @Serializable data object RecordingsKey : NavKey
 @Serializable data object RideRecordingKey : NavKey
+@Serializable data object DataKey : NavKey
 @Serializable data object RecordsKey : NavKey
 @Serializable data class RideKey(val rideId: String) : NavKey
 @Serializable data class AskKey(val rideId: String, val askId: String) : NavKey
@@ -215,6 +219,7 @@ fun AppUi(graph: AppGraph) {
                 NoteRoute(graph.records, graph.notes, key.rideId, key.noteId, onClose = { tabs.back() }, modifier = Modifier.safeDrawingPadding(), voice = noteVoice)
               }
               entry<SettingsKey> {
+                val summary by graph.saveSummary.collectAsStateWithLifecycle()
                 SettingsScreen(
                   current, apiKey,
                   onConnection = { tabs.push(ConnectionKey) },
@@ -225,6 +230,32 @@ fun AppUi(graph: AppGraph) {
                   onRecordings = { tabs.push(RecordingsKey) },
                   version = BuildConfig.VERSION_NAME,
                   modifier = Modifier.safeDrawingPadding(),
+                  saved = saveRowValue(summary ?: SaveSummary()),
+                  onData = { tabs.push(DataKey) },
+                )
+              }
+              entry<DataKey> {
+                val summary by graph.saveSummary.collectAsStateWithLifecycle()
+                val lastSaved by graph.lastSaved.at.collectAsStateWithLifecycle()
+                val sending by graph.sync.sending.collectAsStateWithLifecycle()
+                val take by graph.takeover.state.collectAsStateWithLifecycle()
+                val recordings by graph.recordingCheck.items.collectAsStateWithLifecycle()
+                DataScreen(
+                  DataUi(
+                    summary = summary ?: SaveSummary(),
+                    lastSaved = lastSavedLabel(lastSaved, System.currentTimeMillis(), ZoneId.systemDefault()),
+                    sending = sending,
+                    recording = ride?.status == RideStatus.RECORDING,
+                    active = ride != null,
+                    reading = take.running != null,
+                    userName = current.userName,
+                    message = take.result?.takeIf { take.last == TakeOp.REREAD }?.let(::rereadMessage),
+                    recordings = recordings.size,
+                  ),
+                  onSave = graph.sync::request,
+                  onUser = { tabs.push(UserKey) },
+                  onReread = { graph.takeover.reread(current.userName) },
+                  modifier = Modifier.safeDrawingPadding(),
                 )
               }
               entry<RideRecordingKey> {
diff --git a/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt b/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
new file mode 100644
index 0000000..3938a7b
--- /dev/null
+++ b/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
@@ -0,0 +1,45 @@
+package com.touringproject.v2.ui
+
+import com.touringproject.v2.records.SaveSummary
+import com.touringproject.v2.sync.TakeResult
+import java.time.Instant
+import java.time.ZoneId
+import java.time.format.DateTimeFormatter
+
+// How SC-14, SC-09's データの保存 and SC-18 tell what is saved and what a read of the cloud came to (slice 4 spec §7).
+
+private val CLOCK = DateTimeFormatter.ofPattern("HH:mm")
+
+/** SC-14's 内訳, the kinds with any in one line: 質問できなかった地点 1件・走行 2本・地点メモ 3件・メモ 1件・削除 1件. */
+fun unsentBreakdown(summary: SaveSummary): String = listOf(
+  summary.unreached to { n: Int -> "質問できなかった地点 ${n}件" },
+  summary.unsentRides to { n: Int -> "走行 ${n}本" },
+  summary.notes to { n: Int -> "地点メモ ${n}件" },
+  summary.memos to { n: Int -> "メモ ${n}件" },
+  summary.deletions to { n: Int -> "削除 ${n}件" },
+).filter { it.first > 0 }.joinToString("・") { (n, label) -> label(n) }
+
+/** 最終保存 10:22, with the day when it was not today; まだ保存していません before the first save. */
+fun lastSavedLabel(at: Long?, now: Long, zone: ZoneId): String {
+  if (at == null) return "まだ保存していません"
+  val saved = Instant.ofEpochMilli(at).atZone(zone)
+  val time = CLOCK.format(saved)
+  return if (saved.toLocalDate() == Instant.ofEpochMilli(now).atZone(zone).toLocalDate()) "最終保存 $time" else "最終保存 ${dayLabel(saved.toLocalDate(), weekday = false)} $time"
+}
+
+/** SC-09's データの保存 row. */
+fun saveRowValue(summary: SaveSummary): String = if (summary.unsent > 0) "未送信あり" else "保存済み"
+
+/** SC-14 after クラウドから読み直す. */
+fun rereadMessage(result: TakeResult): String = when (result) {
+  is TakeResult.Done -> if (result.count == 0) "新しい記録はありませんでした" else "${result.count}件の記録を読み込みました"
+  TakeResult.Blocked -> "走行を終えてから読み直せます"
+  TakeResult.Failed -> "読み込めませんでした"
+}
+
+/** SC-18 after DL-03. */
+fun switchMessage(result: TakeResult): String = when (result) {
+  is TakeResult.Done -> "ユーザー名を変えました"
+  TakeResult.Blocked -> "未送信の記録があるため、変えられませんでした"
+  TakeResult.Failed -> "読み込めませんでした。ユーザー名は変えていません"
+}
diff --git a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
index 173c8ca..864e792 100644
--- a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
@@ -10,6 +10,8 @@ import androidx.compose.foundation.layout.fillMaxWidth
 import androidx.compose.foundation.layout.padding
 import androidx.compose.foundation.lazy.LazyColumn
 import androidx.compose.foundation.lazy.items
+import androidx.compose.foundation.rememberScrollState
+import androidx.compose.foundation.verticalScroll
 import androidx.compose.foundation.shape.RoundedCornerShape
 import androidx.compose.material3.AlertDialog
 import androidx.compose.material3.Button
@@ -37,6 +39,8 @@ import androidx.compose.ui.unit.dp
 import androidx.compose.ui.unit.sp
 import com.touringproject.v2.api.ApiError
 import com.touringproject.v2.api.ApiErrorKind
+import com.touringproject.v2.records.SaveSummary
+import com.touringproject.v2.recordings.KEEP_RECORDINGS
 import com.touringproject.v2.settings.LaunchableApp
 import com.touringproject.v2.settings.MAX_RECORDING_HOURS_CHOICES
 import com.touringproject.v2.settings.ReturnTiming
@@ -79,11 +83,16 @@ fun SettingsScreen(
   /** The app's version, raised by hand for every new build put on the phones. */
   version: String,
   modifier: Modifier = Modifier,
+  /** SC-14's row: 保存済み or 未送信あり (slice 4 spec §7.1). */
+  saved: String = "",
+  onData: () -> Unit = {},
 ) {
   val returnValue = if (!settings.returnEnabled) "戻らない" else settings.returnApp?.label ?: "未設定"
-  Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
+  // Scrolls: the list outgrows a small screen.
+  Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
     SettingsRow("接続の設定", apiKey?.let(::maskKey) ?: "未設定", onConnection)
     SettingsRow("ユーザー名", settings.userName, onUser)
+    SettingsRow("☁️ データの保存", saved, onData)
     SettingsRow("走行の記録", "最長 ${settings.maxRecordingHours}時間", onRideRecording)
     SettingsRow("応答後に戻るアプリ", returnValue, onReturnApp)
     SettingsRow("回答の音量", "+${settings.answerVolumeDb}dB", onVolume)
@@ -92,6 +101,76 @@ fun SettingsScreen(
   }
 }
 
+/**
+ * SC-14 (slice 4 spec §7.1). recording: a ride records now, and its last points go at its pause or end. active: a ride
+ * records or is paused, so reading the cloud again waits for its end. reading: a read of the cloud is under way.
+ */
+data class DataUi(
+  val summary: SaveSummary,
+  val lastSaved: String,
+  val sending: Boolean,
+  val recording: Boolean,
+  val active: Boolean,
+  val reading: Boolean,
+  val userName: String,
+  /** What the last クラウドから読み直す came to; null before one. */
+  val message: String?,
+  /** The recordings kept on the device for SC-12. */
+  val recordings: Int,
+)
+
+@Composable
+private fun DataRow(title: String, value: String) {
+  Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
+    Text(title, Modifier.weight(1f), fontSize = 16.sp)
+    Text(value, color = Color(0xFF666666), fontSize = 16.sp)
+  }
+}
+
+// SC-14
+@Composable
+fun DataScreen(ui: DataUi, onSave: () -> Unit, onUser: () -> Unit, onReread: () -> Unit, modifier: Modifier = Modifier) {
+  val muted = Color(0xFF666666)
+  Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
+    Surface(Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Color(0xFFCCCCCC))) {
+      Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
+        if (ui.summary.unsent == 0) {
+          Text("● すべてクラウドに保存済み", fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("saveState"))
+          Text(ui.lastSaved, color = muted, fontSize = 14.sp)
+        } else {
+          Text("● 未送信の記録があります", fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("saveState"))
+          Text("${unsentBreakdown(ui.summary)}。通信できるようになると自動で送ります。", color = muted, fontSize = 14.sp, modifier = Modifier.testTag("unsentBreakdown"))
+          Button(onClick = onSave, enabled = !ui.sending, modifier = Modifier.fillMaxWidth().testTag("saveNow")) {
+            Text(if (ui.sending) "送っています…" else "今すぐ保存", fontSize = 16.sp)
+          }
+        }
+        if (ui.recording) Text("記録中の走行は、一時停止か終了で残りを送ります。", color = muted, fontSize = 14.sp, modifier = Modifier.testTag("recordingNote"))
+      }
+    }
+    SettingsRow("ユーザー名", ui.userName, onUser)
+    Button(
+      onClick = onReread,
+      enabled = !ui.active && !ui.reading,
+      modifier = Modifier.fillMaxWidth().testTag("reread"),
+      colors = ButtonDefaults.buttonColors(containerColor = Blue),
+    ) { Text(if (ui.reading) "読み込んでいます…" else "クラウドから読み直す", fontSize = 16.sp) }
+    if (ui.active) Text("走行を終えてから読み直せます", color = muted, fontSize = 14.sp)
+    ui.message?.let { Text(it, modifier = Modifier.testTag("dataMessage")) }
+    Text("保存している内容", fontWeight = FontWeight.Bold, fontSize = 16.sp)
+    DataRow("会話の文字・ルート・メモ・地点メモ", "端末＋クラウド · すべて")
+    DataRow("録音の音声", "端末のみ · 直近${KEEP_RECORDINGS}件")
+    Text(
+      "録音の音声は 設定 > 録音の確認 でだけ聞けます。機種を変えても、同じユーザー名を設定すれば記録が戻ります。音声はクラウドに残さないため戻りません。",
+      color = muted,
+      fontSize = 14.sp,
+    )
+    Text("件数", fontWeight = FontWeight.Bold, fontSize = 16.sp)
+    DataRow("走行", ui.summary.rides.toString())
+    DataRow("質問", ui.summary.asks.toString())
+    DataRow("端末の音声", "${ui.recordings} / $KEEP_RECORDINGS")
+  }
+}
+
 // SC-21: how much the Backend raises the answer audio. Takes effect from the next question.
 @Composable
 fun VolumeScreen(settings: Settings, onUpdate: (Settings) -> Unit, modifier: Modifier = Modifier) {
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SettingsScreensTest' --tests '*SavingLabelsTest' --tests '*AppUiTest'`
Expected: 13件・4件・8件が通る（設定の一覧はスクロールするようになったので、既存の2件も画面の外の行を `performScrollTo` で出してから押す）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
git commit -m "feat: add SC-14, which tells what is saved, sends now and reads the cloud again"
```

---

### Task 7: SC-18・DL-03（ユーザー名の変更で記録を切り替える）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt`（`UserBlock`・`UserScreen`）・`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`・`app/src/main/java/com/touringproject/v2/AppGraph.kt`（`switchedTo`）・`app/src/main/java/com/touringproject/v2/sync/Takeover.kt`（`seen`）
- Test: `app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt`・`app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt`

**Interfaces:**
- Consumes: Task 5 の `Peek`・`Takeover.peek`・`switchTo`、Task 6 の `switchMessage`・`DataKey`。
- Produces: `enum class UserBlock(message) { RIDE, UNSENT }`・`@Composable fun UserScreen(userName, block: UserBlock?, reading: Boolean, message: String?, peek: suspend (String) -> Peek?, onChange: (Peek) -> Unit, onData: () -> Unit, modifier)`。`suspend fun AppGraph.switchedTo(userName: String)`。`fun Takeover.seen()`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
index 47059b5..209e6e3 100644
--- a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
@@ -159,4 +159,19 @@ class TakeoverTest {
     assertEquals(1, c.taken.size)
     passes.cancel()
   }
+
+  @Test
+  fun a_result_seen_goes_but_a_read_under_way_stays() = runTest {
+    val c = Cloud(this)
+    c.pages["rider01"] = mapOf(null to CloudPage(emptyList(), null))
+    c.gate = CompletableDeferred()
+    c.takeover.reread("rider01")
+    c.takeover.seen()
+    assertEquals(TakeOp.REREAD, c.takeover.state.value.running)
+    c.gate!!.complete(Unit)
+    runCurrent()
+    assertEquals(TakeResult.Done(2), c.takeover.state.value.result)
+    c.takeover.seen()
+    assertEquals(TakeState(), c.takeover.state.value)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index 79948f0..951df2c 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -17,6 +17,8 @@ import androidx.compose.ui.test.performScrollTo
 import androidx.compose.ui.test.performTextClearance
 import androidx.compose.ui.test.performTextInput
 import androidx.test.ext.junit.runners.AndroidJUnit4
+import com.touringproject.v2.api.CloudDeleted
+import com.touringproject.v2.api.CloudPage
 import com.touringproject.v2.ask.FlowState
 import com.touringproject.v2.ask.Phase
 import com.touringproject.v2.ask.RecordingMeta
@@ -28,6 +30,7 @@ import com.touringproject.v2.recordings.TrialState
 import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.settings.LaunchableApp
 import com.touringproject.v2.settings.Settings
+import com.touringproject.v2.sync.Peek
 import org.junit.Assert.assertEquals
 import org.junit.Assert.assertNull
 import org.junit.Assert.assertTrue
@@ -205,18 +208,72 @@ class SettingsScreensTest {
   @get:Rule val rule = createComposeRule()
   private val maps = LaunchableApp("com.google.android.apps.maps", "マップ")
 
+  private fun peeked(name: String, exists: Boolean) =
+    Peek(name, CloudPage(if (exists) listOf(CloudDeleted("note", "n1", "r1", "2026-10-22T03:00:00Z")) else emptyList(), null))
+
   @Test
-  fun an_invalid_user_name_is_refused_and_a_valid_one_is_confirmed() {
-    val changed = mutableListOf<String>()
-    rule.setContent { UserScreen("rider01", { changed += it }) }
+  fun an_unusable_user_name_is_refused_before_anything_is_read() {
+    val peeks = mutableListOf<String>()
+    rule.setContent { UserScreen("rider01", null, false, null, { peeks += it; null }, {}, {}) }
     rule.onNodeWithTag("userInput").performTextInput("No!")
     rule.onNodeWithTag("changeUser").performClick()
-    rule.onNodeWithTag("userError").assertIsDisplayed()
+    rule.onNodeWithTag("userError").assertTextEquals("英小文字と数字の3〜20文字にしてください")
     rule.onNodeWithTag("userInput").performTextClearance()
-    rule.onNodeWithTag("userInput").performTextInput("rider02")
+    rule.onNodeWithTag("userInput").performTextInput("rider01")
     rule.onNodeWithTag("changeUser").performClick()
-    rule.onNodeWithText("変える").performClick()
-    assertEquals(listOf("rider02"), changed)
+    rule.onNodeWithTag("userError").assertTextEquals("今のユーザー名と同じです")
+    assertEquals(emptyList<String>(), peeks)
+  }
+
+  // Slice 4 spec §6.4: DL-03 is worded by whether the new name has records, and the change starts once confirmed.
+  @Test
+  fun dl03_tells_a_new_name_from_one_with_records() {
+    val changed = mutableListOf<Peek>()
+    rule.setContent { UserScreen("rider01", null, false, null, { peeked(it, exists = it == "taro01") }, { changed += it }, {}) }
+    rule.onNodeWithTag("userInput").performTextInput("hanako2")
+    rule.onNodeWithTag("changeUser").performClick()
+    rule.onNodeWithText("ユーザー名を変えますか？").assertExists()
+    rule.onNodeWithTag("userDialogText").assertTextEquals(
+      "「hanako2」は新しいユーザー名です。今の「rider01」の記録は引き継がれず、記録が空の状態から始まります。元のユーザー名に戻せば、今の記録はまた見られます。",
+    )
+    rule.onNodeWithText("やめる").performClick()
+    rule.onNodeWithTag("userInput").performTextClearance()
+    rule.onNodeWithTag("userInput").performTextInput("taro01")
+    rule.onNodeWithTag("changeUser").performClick()
+    rule.onNodeWithText("既にあるユーザー名です").assertExists()
+    rule.onNodeWithTag("confirmUser").assertTextEquals("切り替える")
+    rule.onNodeWithTag("confirmUser").performClick()
+    assertEquals(listOf("taro01"), changed.map { it.userName })
+  }
+
+  @Test
+  fun a_name_that_cannot_be_read_is_not_changed_to() {
+    rule.setContent { UserScreen("rider01", null, false, null, { null }, {}, {}) }
+    rule.onNodeWithTag("userInput").performTextInput("taro01")
+    rule.onNodeWithTag("changeUser").performClick()
+    rule.onNodeWithTag("userError").assertTextEquals("読み込めませんでした")
+    rule.onNodeWithText("既にあるユーザー名です").assertDoesNotExist()
+  }
+
+  // US-E-06.008: not while a ride records or something is left to send, nor during a read; SC-14 is a tap away.
+  @Test
+  fun the_name_cannot_change_while_blocked_or_reading() {
+    var block by mutableStateOf<UserBlock?>(UserBlock.UNSENT)
+    var reading by mutableStateOf(false)
+    var toData = 0
+    rule.setContent { UserScreen("rider01", block, reading, "ユーザー名を変えました", { null }, {}, { toData += 1 }) }
+    rule.onNodeWithTag("changeUser").assertIsNotEnabled()
+    rule.onNodeWithTag("userBlock").assertTextEquals("未送信の記録があります。先に「データの保存」で送ってください")
+    rule.onNodeWithTag("toData").performClick()
+    assertEquals(1, toData)
+    block = UserBlock.RIDE
+    rule.onNodeWithTag("userBlock").assertTextEquals("走行を終えてから変えられます")
+    rule.onNodeWithTag("toData").assertDoesNotExist()
+    block = null
+    reading = true
+    rule.onNodeWithTag("changeUser").assertIsNotEnabled()
+    rule.onNodeWithText("読み込んでいます…").assertExists()
+    rule.onNodeWithTag("userMessage").assertTextEquals("ユーザー名を変えました")
   }
 
   private val data = DataUi(SaveSummary(rides = 3, asks = 19), "最終保存 10:22", false, false, false, false, "rider01", null, 10)
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SettingsScreensTest' --tests '*TakeoverTest'`
Expected: コンパイルで落ちる（`UserBlock`・`seen` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index a901445..acbe898 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -320,6 +320,15 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     }
   }
 
+  /**
+   * A change of user name has read the new name's records in (slice 4 spec §6.4): the name is saved, and the
+   * conversation ends, since the Agent keeps one per user name. SC-12's recordings are the device's and stay.
+   */
+  suspend fun switchedTo(userName: String) {
+    settings.update(settings.current().copy(userName = userName))
+    conversation.reset()
+  }
+
   /**
    * True once per process: the first activity of this process asks for permissions, whether it starts fresh or is
    * restored after process death (Android #38). An activity recreated in the same process does not ask again.
diff --git a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
index 553b0f1..d1b737a 100644
--- a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
@@ -8,6 +8,7 @@ import kotlinx.coroutines.CoroutineScope
 import kotlinx.coroutines.flow.MutableStateFlow
 import kotlinx.coroutines.flow.StateFlow
 import kotlinx.coroutines.flow.asStateFlow
+import kotlinx.coroutines.flow.update
 import kotlinx.coroutines.launch
 
 // Reading the user's records back from the cloud (slice 4 spec §6, adr/0010): when the user name changes, and when SC-14
@@ -62,6 +63,11 @@ class Takeover(
   private val stateNow = MutableStateFlow(TakeState())
   val state: StateFlow<TakeState> = stateNow.asStateFlow()
 
+  /** The screen that told the last result has gone, so the next visit starts without it; a read under way is kept. */
+  fun seen() {
+    stateNow.update { if (it.running == null) TakeState() else it }
+  }
+
   /** null when the page could not be read. */
   suspend fun peek(userName: String): Peek? = try {
     api(userName)?.let { Peek(userName, it.records(null)) }
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index 6b2551f..e415d3c 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -240,6 +240,7 @@ fun AppUi(graph: AppGraph) {
                 val sending by graph.sync.sending.collectAsStateWithLifecycle()
                 val take by graph.takeover.state.collectAsStateWithLifecycle()
                 val recordings by graph.recordingCheck.items.collectAsStateWithLifecycle()
+                DisposableEffect(Unit) { onDispose { graph.takeover.seen() } }
                 DataScreen(
                   DataUi(
                     summary = summary ?: SaveSummary(),
@@ -292,7 +293,24 @@ fun AppUi(graph: AppGraph) {
                 )
               }
               entry<UserKey> {
-                UserScreen(current.userName, { name -> scope.launch { graph.settings.update(current.copy(userName = name)) } }, Modifier.safeDrawingPadding())
+                val summary by graph.saveSummary.collectAsStateWithLifecycle()
+                val take by graph.takeover.state.collectAsStateWithLifecycle()
+                DisposableEffect(Unit) { onDispose { graph.takeover.seen() } }
+                // The write checks again in its own transaction (US-E-06.008); a change still waiting to be written counts.
+                val block = when {
+                  ride != null -> UserBlock.RIDE
+                  (summary?.unsent ?: 0) > 0 || storeFailed -> UserBlock.UNSENT
+                  else -> null
+                }
+                UserScreen(
+                  current.userName, block,
+                  reading = take.running != null,
+                  message = take.result?.takeIf { take.last == TakeOp.SWITCH }?.let(::switchMessage),
+                  peek = graph.takeover::peek,
+                  onChange = { peek -> graph.takeover.switchTo(peek, graph::switchedTo) },
+                  onData = { tabs.push(DataKey) },
+                  modifier = Modifier.safeDrawingPadding(),
+                )
               }
               entry<ReturnAppKey> {
                 var apps by remember { mutableStateOf<List<LaunchableApp>>(emptyList()) }
diff --git a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
index 864e792..27ffd32 100644
--- a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
@@ -49,6 +49,7 @@ import com.touringproject.v2.settings.USER_NAME_RE
 import com.touringproject.v2.settings.VOLUME_DB_CHOICES
 import com.touringproject.v2.settings.maskKey
 import com.touringproject.v2.settings.withRecentApp
+import com.touringproject.v2.sync.Peek
 import kotlinx.coroutines.launch
 
 private val Blue = Color(0xFF1F4FD1)
@@ -305,36 +306,90 @@ fun ConnectionScreen(
   }
 }
 
-// SC-18
+/** Why the user name cannot change now (slice 4 spec §6.4, US-E-06.008). */
+enum class UserBlock(val message: String) {
+  RIDE("走行を終えてから変えられます"),
+  UNSENT("未送信の記録があります。先に「データの保存」で送ってください"),
+}
+
+/**
+ * SC-18. peek reads the new name's first page (null when it cannot), and DL-03 tells from it whether the name has
+ * records (slice 4 spec §6.4). onChange starts the change after DL-03; reading is true while a read of the cloud is under
+ * way, and message is what the last change came to.
+ */
 @Composable
-fun UserScreen(userName: String, onChange: (String) -> Unit, modifier: Modifier = Modifier) {
+fun UserScreen(
+  userName: String,
+  block: UserBlock?,
+  reading: Boolean,
+  message: String?,
+  peek: suspend (String) -> Peek?,
+  onChange: (Peek) -> Unit,
+  onData: () -> Unit,
+  modifier: Modifier = Modifier,
+) {
+  val scope = rememberCoroutineScope()
   // Saveable, so a name being typed survives a trip to another tab (Android #34).
   var input by rememberSaveable { mutableStateOf("") }
-  var error by remember { mutableStateOf(false) }
-  var confirming by remember { mutableStateOf<String?>(null) }
-  Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
+  var error by remember { mutableStateOf<String?>(null) }
+  var checking by remember { mutableStateOf(false) }
+  var confirming by remember { mutableStateOf<Peek?>(null) }
+  Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
     Text("今のユーザー名", color = Color(0xFF666666), fontSize = 16.sp)
     Text(userName, fontSize = 32.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
-    Text("別の端末に記録を引き継ぐときに使います。控えておいてください。", color = Color(0xFF666666), fontSize = 14.sp)
+    Text("記録はユーザー名ごとに分かれます。別の端末で同じユーザー名を設定すると、記録を引き継げます。控えておいてください。", color = Color(0xFF666666), fontSize = 14.sp)
     OutlinedTextField(input, { input = it }, Modifier.fillMaxWidth().testTag("userInput"), placeholder = { Text("新しいユーザー名") }, singleLine = true)
-    if (error) Text("英小文字と数字の3〜20文字にしてください", color = Red, modifier = Modifier.testTag("userError"))
+    error?.let { Text(it, color = Red, modifier = Modifier.testTag("userError")) }
     Button(
       onClick = {
         val name = input.trim()
-        error = !USER_NAME_RE.matches(name)
-        if (!error) confirming = name
+        error = when {
+          !USER_NAME_RE.matches(name) -> "英小文字と数字の3〜20文字にしてください"
+          name == userName -> "今のユーザー名と同じです"
+          else -> null
+        }
+        if (error != null) return@Button
+        checking = true
+        scope.launch {
+          val peeked = peek(name)
+          checking = false
+          if (peeked == null) error = "読み込めませんでした" else confirming = peeked
+        }
       },
+      enabled = block == null && !reading && !checking,
       modifier = Modifier.fillMaxWidth().testTag("changeUser"),
       colors = ButtonDefaults.buttonColors(containerColor = Blue),
-    ) { Text("変更する", fontSize = 18.sp) }
+    ) { Text(if (reading || checking) "読み込んでいます…" else "変更する", fontSize = 18.sp) }
+    block?.let { Text(it.message, modifier = Modifier.testTag("userBlock")) }
+    if (block == UserBlock.UNSENT) TextButton(onClick = onData, modifier = Modifier.testTag("toData")) { Text("データの保存へ") }
+    message?.let { Text(it, modifier = Modifier.testTag("userMessage")) }
+    Text(
+      "変えると、今の記録は引き継がれず、新しいユーザー名の記録が表示されます。今の記録は消えず、元のユーザー名に戻せばまた見られます。",
+      color = Color(0xFF666666),
+      fontSize = 14.sp,
+    )
   }
-  // DL-03
-  confirming?.let { name ->
+  // DL-03: worded by whether the new name has records (the mock's two states).
+  confirming?.let { peeked ->
+    val name = peeked.userName
     AlertDialog(
       onDismissRequest = { confirming = null },
-      title = { Text("「$name」に変えますか？") },
-      text = { Text("今の記録は引き継ぎません。元の名前に戻せば、また見られます。同じ名前の記録が既にあれば、その記録に切り替わります。") },
-      confirmButton = { TextButton(onClick = { confirming = null; input = ""; onChange(name) }) { Text("変える") } },
+      title = { Text(if (peeked.exists) "既にあるユーザー名です" else "ユーザー名を変えますか？") },
+      text = {
+        Text(
+          if (peeked.exists) {
+            "「$name」の記録が既にあります。このユーザー名に切り替えると、その記録が表示されます。今の「$userName」の記録は引き継がれません。元のユーザー名に戻せば、また見られます。"
+          } else {
+            "「$name」は新しいユーザー名です。今の「$userName」の記録は引き継がれず、記録が空の状態から始まります。元のユーザー名に戻せば、今の記録はまた見られます。"
+          },
+          modifier = Modifier.testTag("userDialogText"),
+        )
+      },
+      confirmButton = {
+        TextButton(onClick = { confirming = null; input = ""; onChange(peeked) }, Modifier.testTag("confirmUser")) {
+          Text(if (peeked.exists) "切り替える" else "変更する")
+        }
+      },
       dismissButton = { TextButton(onClick = { confirming = null }) { Text("やめる") } },
     )
   }
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SettingsScreensTest' --tests '*TakeoverTest' --tests '*AppUiTest'`
Expected: 16件・7件・8件が通る

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/sync/Takeover.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
git commit -m "feat: change the user name by reading the new name's records in, worded by whether it has any"
```

---

### Task 8: 後回しの指摘 #64・#65・#66・#67

issue ごとに、テスト → 落ちることの確かめ → 実装 → 通ることの確かめ → コミット を回す。

#### #64: 質問できなかった地点を書けたら、すぐ送る

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
index f2995f3..40e06b9 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
@@ -49,6 +49,21 @@ class RoomAskLogTest {
     db.close()
   }
 
+  // Android #64: an unreached ask written asks for a pass at once, since the network may still be there.
+  @Test
+  fun an_unreached_ask_written_asks_for_a_pass() = runBlocking {
+    keepRide()
+    var kicks = 0
+    val kicking = RoomAskLog(db.asks(), kotlinx.coroutines.MainScope(), unreachedKept = { kicks += 1 }) { message, _ -> errors += message }
+    kicking.save(record)
+    assertEquals(0, kicks)
+    kicking.save(unreachedAsk("u1", 2_000, null, null, "r1"))
+    assertEquals(1, kicks)
+    kicking.save(unreachedAsk("u2", 2_000, null, null, "r9"))
+    assertEquals(1, kicks)
+    db.close()
+  }
+
   @Test
   fun the_count_of_a_ride_follows_the_asks_kept_for_it() = runBlocking {
     keepRide()
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RoomAskLogTest'`
Expected: コンパイルで落ちる（`unreachedKept` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index acbe898..f767039 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -103,7 +103,8 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   val routeSource: RouteSource = FusedRouteSource(context)
   private val database = RideDatabase.open(context)
   val rideStore = RoomRideStore(database.rides())
-  val askLog = RoomAskLog(database.asks(), scope) { message, e -> Log.w("trv2.ask", message, e) }
+  // sync is made below; it is read only when an unreached ask has been written.
+  val askLog = RoomAskLog(database.asks(), scope, unreachedKept = { sync.request() }) { message, e -> Log.w("trv2.ask", message, e) }
   /** What the Records tab reads (SC-05, SC-06, SC-07). */
   val records = RoomRecords(database.rides(), database.asks(), database.notes())
 
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
index c7417b8..51870cf 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt
@@ -39,9 +39,15 @@ fun AskRecord.toEntity() = AskEntity(
 
 /**
  * Keeps asks in Room without holding up the ask loop. A failed write is logged and shown, like a ride's (slice 2 spec
- * §8); so is an ask dropped because its ride is not kept, without a throwable (Android #58).
+ * §8); so is an ask dropped because its ride is not kept, without a throwable (Android #58). An unreached ask written
+ * is something new to send (unreachedKept): the network may still be there, the Backend having failed (Android #64).
  */
-class RoomAskLog(private val dao: AskDao, private val scope: CoroutineScope, private val log: (String, Throwable?) -> Unit) : AskLog {
+class RoomAskLog(
+  private val dao: AskDao,
+  private val scope: CoroutineScope,
+  private val unreachedKept: () -> Unit = {},
+  private val log: (String, Throwable?) -> Unit,
+) : AskLog {
   private val failing = MutableStateFlow(false)
   /** True once an ask could not be written, until the rider closes the band or the next ask is written (Android #28). */
   val failed: StateFlow<Boolean> = failing.asStateFlow()
@@ -66,6 +72,7 @@ class RoomAskLog(private val dao: AskDao, private val scope: CoroutineScope, pri
         return
       }
       failing.value = false
+      if (record.outcome == AskOutcome.OFFLINE) unreachedKept()
     } catch (e: CancellationException) {
       throw e
     } catch (e: Exception) {
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RoomAskLogTest'`
Expected: 8件が通る

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/store/RoomAskLog.kt app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
git commit -m "fix: send an unreached ask as soon as it is written, the network still being there" -m "Fixes #64"
```

#### #65: 時系列の行に「 · 📵」

- [ ] **Step 6: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
index d343d32..908181f 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
@@ -275,6 +275,7 @@ class RecordLabelsTest {
     assertEquals(listOf("右手の山は？", UNREACHED_TEXT, UNREACHED_TEXT), rows.map { it.text })
     assertEquals(listOf("足柄下郡箱根町仙石原", "住所は送信後", "位置の記録なし"), rows.map { it.place })
     assertEquals(listOf(false, true, true), rows.map { it.failed })
+    assertEquals(listOf(false, true, true), rows.map { it.unreached })
     assertEquals("足柄下郡箱根町仙石原", askPlace(unreached("u1", 0, address = "神奈川県足柄下郡箱根町仙石原", sent = true)))
     assertEquals("場所不明", askPlace(unreached("u1", 0, sent = true)))
   }
diff --git a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
index fc433a2..798ddf2 100644
--- a/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
@@ -265,6 +265,15 @@ class RecordsScreensTest {
     rule.onNodeWithText("09:41 · 箱根町仙石原 · 📝").assertExists()
   }
 
+  // Android #65: as the mock draws it, an unreached ask's row is marked after its memo's mark.
+  @Test
+  fun the_timeline_marks_an_unreached_ask() {
+    val row = TimelineRow.Ask("u1", 1, "10:05", "住所は送信後", UNREACHED_TEXT, true, memo = true, unreached = true)
+    rule.setContent { RideDetailScreen(detail().copy(timeline = listOf(row)), fakeMap, true, {}, {}, {}, { true }, {}) }
+    rule.onNodeWithTag("timeline").performScrollToNode(hasTestTag("ask-u1"))
+    rule.onNodeWithText("10:05 · 住所は送信後 · 📝 · 📵").assertExists()
+  }
+
   // US-D-06.002, US-D-06.003: an ended ride is deleted after DL-01 says what goes.
   @Test
   fun an_ended_ride_is_deleted_after_the_confirmation() {
EOF
```

- [ ] **Step 7: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RecordLabelsTest' --tests '*RecordsScreensTest'`
Expected: コンパイルで落ちる（`TimelineRow.Ask.unreached` が無い）

- [ ] **Step 8: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
index 78a9dc5..35896f8 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt
@@ -201,7 +201,7 @@ fun askText(ask: AskRecord): String = if (ask.outcome == AskOutcome.OFFLINE) UNR
 
 sealed interface TimelineRow {
   data class Day(val label: String) : TimelineRow
-  /** memo: the ask has a memo (US-D-04.005). */
+  /** memo: the ask has a memo (US-D-04.005). unreached: it never reached the Backend (slice 4 spec §4.3, Android #65). */
   data class Ask(
     val askId: String,
     val number: Int,
@@ -210,6 +210,7 @@ sealed interface TimelineRow {
     val text: String,
     val failed: Boolean,
     val memo: Boolean = false,
+    val unreached: Boolean = false,
   ) : TimelineRow
   /** A point memo: its green number, when, where and the start of its text (the mock). */
   data class Note(val noteId: String, val number: Int, val time: String, val place: String, val text: String) : TimelineRow
@@ -271,7 +272,7 @@ fun rideTimeline(ride: Ride, asks: List<AskRecord>, zone: ZoneId, notes: List<No
         asked = true
         rows += TimelineRow.Ask(
           ask.askId, numbers.getValue(ask.askId), TIME.format(at(ask.askedAt, zone)), askPlace(ask), askText(ask),
-          ask.outcome != AskOutcome.ANSWERED, memo = ask.memo != null,
+          ask.outcome != AskOutcome.ANSWERED, memo = ask.memo != null, unreached = ask.outcome == AskOutcome.OFFLINE,
         )
       }
       is Event.PauseAt -> rows += TimelineRow.Pause(
diff --git a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
index d537ea3..1346933 100644
--- a/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt
@@ -349,7 +349,8 @@ private fun TimelineItem(row: TimelineRow, onAsk: (String) -> Unit, onNote: (Str
         Text(row.number.toString(), color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
       }
       Column(Modifier.weight(1f)) {
-        Muted("${row.time} · ${row.place}" + if (row.memo) " · 📝" else "", size = 13)
+        // As the mock's timeline marks them: a memo, then an ask that never reached the Backend.
+        Muted("${row.time} · ${row.place}" + (if (row.memo) " · 📝" else "") + (if (row.unreached) " · 📵" else ""), size = 13)
         Text(
           row.text, maxLines = 2, overflow = TextOverflow.Ellipsis,
           fontWeight = if (row.failed) FontWeight.Normal else FontWeight.Bold,
EOF
```

- [ ] **Step 9: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RecordLabelsTest' --tests '*RecordsScreensTest'`
Expected: 21件・28件が通る

- [ ] **Step 10: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
git commit -m "fix: mark an unreached ask in SC-06's timeline as the mock does" -m "Fixes #65"
```

#### #66: 走行のメモの失敗のあとの帯

- [ ] **Step 11: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
index fb07bfd..a04888a 100644
--- a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
@@ -797,6 +797,24 @@ class RideControllerTest {
     assertNull(w.stored().memo)
   }
 
+  // Android #66: with the failed memo dropped, nothing waits to be written, so the home band goes; a waiting change keeps it.
+  @Test
+  fun the_band_goes_with_the_failed_memo_unless_a_change_still_waits() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    w.controller.end("箱根")
+    w.failSaves = 1
+    assertFalse(w.controller.memo("r1", "書けない"))
+    assertFalse(w.controller.storeFailed.value)
+    w.failSaves = 1
+    assertFalse(w.controller.rename("r1", "御殿場"))
+    w.failSaves = 2
+    assertFalse(w.controller.memo("r1", "これも書けない"))
+    assertTrue(w.controller.storeFailed.value)
+  }
+
   @Test
   fun the_active_rides_memo_that_could_not_be_written_is_neither_shown_nor_written_later() = runTest {
     val w = World()
EOF
```

- [ ] **Step 12: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RideControllerTest'`
Expected: `the_band_goes_with_the_failed_memo_unless_a_change_still_waits` が落ちる（帯が true のまま）

- [ ] **Step 13: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/ride/RideController.kt b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
index 67cb6ef..512219f 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RideController.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
@@ -221,7 +221,7 @@ class RideController(private val deps: RideDeps) {
    * SC-08 (and SC-02's 走行メモ): sets or, for null, removes any kept ride's memo. Returns false when the memo is too
    * long, the ride is not kept, or the memo could not be written now. The same memo again changes nothing. A memo
    * that could not be written is not kept to be written later: SC-08 has said it was not saved, and the rider may
-   * discard it (Android #53).
+   * discard it (Android #53). With it, the home band goes unless a change is still waiting to be written (Android #66).
    */
   suspend fun memo(rideId: String, memo: String?): Boolean = locked {
     if (!memoFits(memo)) return@locked false
@@ -232,7 +232,7 @@ class RideController(private val deps: RideDeps) {
       if (active.memo == memo) return@locked true
       val changed = active.withMemo(memo, now)
       if (!save(changed)) {
-        unsaved = waiting
+        dropUnsavedMemo(waiting)
         return@locked false
       }
       activeRide.value = changed
@@ -241,10 +241,16 @@ class RideController(private val deps: RideDeps) {
     val ride = keptRide(rideId) ?: return@locked false
     if (ride.memo == memo) return@locked true
     if (save(ride.withMemo(memo, now))) return@locked true
-    unsaved = waiting
+    dropUnsavedMemo(waiting)
     false
   }
 
+  // The memo that failed is not kept to be written; what waited before it still is.
+  private fun dropUnsavedMemo(waiting: Ride?) {
+    unsaved = waiting
+    storeFailing.value = unsaved != null
+  }
+
   /**
    * DL-01: removes an ended ride and all that belongs to it (US-D-06.002). The ride recording or paused cannot be
    * deleted (slice 3 spec §2). A save of this ride still waiting is dropped, so it does not write the ride back.
EOF
```

- [ ] **Step 14: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RideControllerTest'`
Expected: 52件が通る

- [ ] **Step 15: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ride/RideController.kt app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
git commit -m "fix: let the home band go with a ride memo that could not be written" -m "Fixes #66"
```

#### #67: 住所が付かなかった地点を、起動ごとに一度送り直す

- [ ] **Step 16: 失敗するテストを書く**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
index d232c02..f208808 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
@@ -223,4 +223,23 @@ class RoomSyncStoreTest {
     db.asks().upsert(db.asks().ask("u1")!!.copy(askId = "a1", status = "answered", updatedAt = null, sentUpdatedAt = null))
     assertEquals(emptyList<UnsentUnreached>(), store.unsentUnreached())
   }
+
+  // Android #67: what the Backend took without a place gets a newer version and goes again; the others stay as they are.
+  @Test
+  fun a_place_the_backend_could_not_tell_is_asked_for_again() = runBlocking {
+    val store = RoomSyncStore(dao, db.asks(), db.notes()) { 9_000 }
+    rides.save(ride)
+    keepNote("n1", "住所なし", 5_000)
+    keepNote("n2", "住所あり", 5_000)
+    db.notes().create(NoteEntity("n3", "r1", 1_500, null, null, null, null, null, "位置なし", 5_000, null, null, null, null))
+    keepNote("n4", "未送信", 5_000)
+    listOf("n1", "n3").forEach { store.noteSent(it, 5_000, null, null) }
+    store.noteSent("n2", 5_000, "静岡県御殿場市新橋", 90.0)
+    val log = RoomAskLog(db.asks(), MainScope()) { _, _ -> }
+    log.save(unreachedAsk("u1", 1_400, Fix(35.0, 139.0, 1_400, 5.0), null, "r1"))
+    store.unreachedSent("u1", 1_400, null, null)
+    store.retryPlaces()
+    assertEquals(listOf("n4" to 5_000L, "n1" to 9_000L), store.unsentNotes().map { it.id to it.updatedAt })
+    assertEquals(listOf("u1" to 9_000L), store.unsentUnreached().map { it.askId to it.updatedAt })
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
index 67f3ba1..52c4743 100644
--- a/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt
@@ -57,6 +57,7 @@ private class World {
   }
   var online = true
   var hasKey = true
+  var retries = 0
   var gate: CompletableDeferred<Unit>? = null
   var passes = 0
 
@@ -100,6 +101,9 @@ private class World {
       notes.getValue(noteId).refused = updatedAt
       calls += "refused:note/$noteId"
     }
+    override suspend fun retryPlaces() {
+      retries += 1
+    }
     override suspend fun unsentUnreached() =
       unreached.values.filter { (it.sent ?: -1) < it.ask.updatedAt && it.refused != it.ask.updatedAt }.map { it.ask }
     override suspend fun unreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?) {
@@ -525,4 +529,18 @@ class RideSyncTest {
     read.cancel()
     job.cancel()
   }
+
+  // Android #67: the places the Backend could not tell are asked for again once per start, not on every pass.
+  @Test
+  fun places_left_unknown_are_asked_for_again_once_per_start() = runTest {
+    val w = World()
+    val job = launch { w.sync.run() }
+    runCurrent()
+    repeat(3) {
+      w.sync.request()
+      runCurrent()
+    }
+    assertEquals(1, w.retries)
+    job.cancel()
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
index 209e6e3..58ee253 100644
--- a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
@@ -35,6 +35,7 @@ private val nothingToSend = object : SyncStore {
   override suspend fun unsentNotes() = emptyList<UnsentNote>()
   override suspend fun noteSent(noteId: String, updatedAt: Long, address: String?, headingDegrees: Double?) = Unit
   override suspend fun noteRefused(noteId: String, updatedAt: Long) = Unit
+  override suspend fun retryPlaces() = Unit
   override suspend fun unsentUnreached() = emptyList<UnsentUnreached>()
   override suspend fun unreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?) = Unit
   override suspend fun unreachedRefused(askId: String, updatedAt: Long) = Unit
EOF
```

- [ ] **Step 17: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RoomSyncStoreTest' --tests '*RideSyncTest' --tests '*TakeoverTest'`
Expected: コンパイルで落ちる（`retryPlaces` が無い）

- [ ] **Step 18: 実装する**

```bash
cd $AND && git apply <<'EOF'
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 9a90da2..34e71a9 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -502,6 +502,26 @@ interface RideDao {
   @Query("SELECT * FROM deletions ORDER BY deletedAt")
   suspend fun deletions(): List<DeletionEntity>
 
+  // Android #67: the Backend looks a place up again only for a newer version, so a point memo or an unreached ask it took
+  // without one is given a new version, and goes again.
+  @Query(
+    "UPDATE notes SET updatedAt = MAX(:now, updatedAt + 1) WHERE address IS NULL AND latitude IS NOT NULL AND " +
+      "sentUpdatedAt IS NOT NULL AND sentUpdatedAt >= updatedAt",
+  )
+  suspend fun retryNotePlaces(now: Long)
+
+  @Query(
+    "UPDATE asks SET updatedAt = MAX(:now, updatedAt + 1) WHERE status = 'offline' AND address IS NULL AND latitude IS NOT NULL AND " +
+      "sentUpdatedAt IS NOT NULL AND sentUpdatedAt >= updatedAt",
+  )
+  suspend fun retryUnreachedPlaces(now: Long)
+
+  @Transaction
+  suspend fun retryPlaces(now: Long) {
+    retryNotePlaces(now)
+    retryUnreachedPlaces(now)
+  }
+
   @Query("DELETE FROM deletions WHERE kind = :kind AND id = :id")
   suspend fun deletionSent(kind: String, id: String)
 
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
index 998361c..d402527 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
@@ -9,7 +9,12 @@ import com.touringproject.v2.sync.UnsentAskMemo
 import com.touringproject.v2.sync.UnsentNote
 import com.touringproject.v2.sync.UnsentUnreached
 
-class RoomSyncStore(private val dao: RideDao, private val asks: AskDao, private val notes: NoteDao) : SyncStore {
+class RoomSyncStore(
+  private val dao: RideDao,
+  private val asks: AskDao,
+  private val notes: NoteDao,
+  private val now: () -> Long = System::currentTimeMillis,
+) : SyncStore {
   override suspend fun unsent(): List<Unsent> = dao.unsentSnapshot().map {
     Unsent(it.ride.toRide(it.segments), it.ride.sentUpdatedAt, it.ride.rejectedUpdatedAt, it.sentPoints, it.totalPoints)
   }
@@ -55,4 +60,6 @@ class RoomSyncStore(private val dao: RideDao, private val asks: AskDao, private
     asks.markUnreachedSent(askId, updatedAt, address, headingDegrees)
 
   override suspend fun unreachedRefused(askId: String, updatedAt: Long) = asks.markUnreachedRefused(askId, updatedAt)
+
+  override suspend fun retryPlaces() = dao.retryPlaces(now())
 }
diff --git a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
index 304c009..cd510c7 100644
--- a/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/RideSync.kt
@@ -88,6 +88,11 @@ interface SyncStore {
   suspend fun noteSent(noteId: String, updatedAt: Long, address: String?, headingDegrees: Double?)
   /** The Backend refused the point memo as of updatedAt (400); that version is not sent again. */
   suspend fun noteRefused(noteId: String, updatedAt: Long)
+  /**
+   * Gives the point memos and unreached asks the Backend took without a place a new version, so they go again and the
+   * Backend looks their place up again (Android #67).
+   */
+  suspend fun retryPlaces()
   suspend fun unsentUnreached(): List<UnsentUnreached>
   /** The Backend took the unreached ask as of updatedAt; address and headingDegrees are what it settled, null when it did not say. */
   suspend fun unreachedSent(askId: String, updatedAt: Long, address: String?, headingDegrees: Double?)
@@ -136,8 +141,12 @@ class RideSync(
     if (points % ROUTE_CHUNK_POINTS == 0) request()
   }
 
-  /** Runs the passes, one after another, until cancelled. */
+  /**
+   * Runs the passes, one after another, until cancelled. A place the Backend could not tell is asked for again once per
+   * start: often it was a lookup that failed for a while (Android #67); a place with no address at all costs one request.
+   */
   suspend fun run() {
+    read("retry_places") { store.retryPlaces() }
     for (request in requests) pass()
   }
 
EOF
```

- [ ] **Step 19: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RoomSyncStoreTest' --tests '*RideSyncTest' --tests '*TakeoverTest'`
Expected: 13件・29件・7件が通る

- [ ] **Step 20: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt app/src/main/java/com/touringproject/v2/sync/RideSync.kt app/src/test/java/com/touringproject/v2/sync/RideSyncTest.kt app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
git commit -m "fix: ask the Backend again once per start for a place it could not tell" -m "Fixes #67"
```

---

### Task 9: 版と文書

- [ ] **Step 1: README と版を直す**

```bash
cd $AND && git apply <<'EOF'
diff --git a/README.md b/README.md
index f36d502..ebf08f1 100644
--- a/README.md
+++ b/README.md
@@ -9,20 +9,20 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 | 場所 | 中身 |
 |---|---|
 | `app/src/main/java/com/touringproject/v2/ask/` | 一巡の状態機械（`Flow.kt`）・司令塔（`AskController.kt`）・外との窓口（`AskPorts.kt`）・質問の記録の組み立て（`AskRecord.kt`）・ポーリング・会話・失敗の読み上げ文 |
-| `.../api/` | Backend の API（`docs-parent/07a_openapi.yaml`） |
+| `.../api/` | Backend の API（`docs-parent/07a_openapi.yaml`）。`GET /records` で読み戻す記録の型は `Records.kt` |
 | `.../audio/` | インカムの経路・録音・再生・端末の音声・合図 |
 | `.../location/` | 質問の位置の監視と方位の材料の選び方・走行のルートの位置の頼み方と点のふるい分け（`Route.kt`） |
 | `.../ride/` | 走行の型と計算（`Ride.kt`、純粋）・司令塔（`RideController.kt`）・外との窓口（`RidePorts.kt`） |
-| `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・質問のメモと削除（`RoomAskEdits.kt`）・地点メモ（`RoomNotes.kt`）・送信の置き場（`RoomSyncStore.kt`）・記録の画面の読み出し（`RoomRecords.kt`）。スキーマは `app/schemas/` に版ごとに残す |
-| `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋）・メモの決まり（`Memos.kt`、純粋）・地点メモの型と位置の選び方（`Notes.kt`、純粋）・質問と地点メモを変える窓口（`AskEdits.kt`・`NoteEdits.kt`） |
+| `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・質問のメモと削除（`RoomAskEdits.kt`）・地点メモ（`RoomNotes.kt`）・送信の置き場（`RoomSyncStore.kt`）・記録の画面の読み出しと未送信の数（`RoomRecords.kt`）・クラウドの記録を1つのトランザクションで入れる係（`RoomTakeover.kt`）。スキーマは `app/schemas/` に版ごとに残す |
+| `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋）・SC-14 の数（`Saving.kt`）・メモの決まり（`Memos.kt`、純粋）・地点メモの型と位置の選び方（`Notes.kt`、純粋）・質問と地点メモを変える窓口（`AskEdits.kt`・`NoteEdits.kt`） |
 | `.../map/` | 地図（MapLibre と国土地理院の淡色地図）。描くデータの組み立ては `MapData.kt`（純粋）、地図の部品は `RouteMap.kt`、スタイルは `app/src/main/assets/map/gsi-pale.json` |
-| `.../sync/` | 走行・ルート・地点メモ・質問できなかった地点・メモ・削除の送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`） |
+| `.../sync/` | 走行・ルート・地点メモ・質問できなかった地点・メモ・削除の送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`）。クラウドの記録の読み込み: 突き合わせの決まり（`Merge.kt`、純粋）と読み込みの係（`Takeover.kt`） |
 | `.../handsfree/` | 押下の重複・古い合図の除外・押下の行き先（試し録り中は試し録りへ、SC-19 を開いているあいだは声の入力へ） |
 | `.../voice/` | SC-19 の声の入力（`VoiceInput.kt`）。録音・文字起こしの依頼・取りに行く処理・失敗の理由 |
 | `.../net/` | 端末が通信できるか（`Connectivity.kt`。SC-19 の声の入力・質問の一巡・送信が使う） |
 | `.../recordings/` | 録音の置き場（直近10件と付随情報）・試し録りの司令塔・録音の確認（SC-12）の状態 |
 | `.../service/`・`.../nav/` | 前面サービス（走行の記録と一巡で1つ。種類の取りまとめは `ServiceCoordinator.kt`）・締め切りのアラームと自動終了の通知（`RideAlarms.kt`）・ナビを開く |
-| `.../settings/` | 設定（DataStore）と接続キー（Keystore で暗号化） |
+| `.../settings/` | 設定（DataStore）と接続キー（Keystore で暗号化）・最後に保存した時刻（`LastSaved.kt`） |
 | `.../ui/` | 画面（Compose）。タブとバックスタックの組は `Tabs.kt`（Compose に依存しない）、タブの帯は `TabBar.kt`。記録の画面は `RecordsScreens.kt`（地図は差し替えられる枠で受ける）、その表示の組み立ては `RecordLabels.kt`（純粋）、読み出しとのつなぎは `RecordsRoutes.kt`。メモの編集（SC-08）は `MemoScreen.kt`（SC-19 と共通の編集部品 `MemoEditor` を含む）、地点メモ（SC-19）は `NoteScreen.kt`、削除の確認（DL-01）は `DeleteDialog.kt` |
 
 ## 大事な決まり
@@ -34,7 +34,8 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 - 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと・通信できるようになったとき（`reconnections`。プロセスが生きているあいだだけ）。契機では未送信を調べるだけで、送るものが無ければ通信しない。通信できないあいだは、契機が来ても通信を試さない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。
 - 1回の送信は、削除の印（`deletions`）→ 走行とルート → 地点メモ → 質問できなかった地点 → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため。質問できなかった地点のメモが、Backend で質問を見つけられるため）。記録を消すときは、同じトランザクションで削除の印を書く。送れない削除の印（知らない種類）は、ログ `sync_unsendable` に出して消す（残すと、毎回の送信がそこで止まる）。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
 - 地点メモ（SC-19）は、走行の記録中と一時停止中にホームの「📝 地点メモ」から開く。開いたときに、その走行の最後の点を位置に、質問と同じ選び方で方位の材料を決め（`noteDraft`）、保存するまで書かない。住所と方位は、最初に送ったときに Backend が決めて返し、端末はそれを行に書く（`notes.address`・`headingDegrees`）。地図のピンは緑で、質問とは別の通し番号。質問の一巡が終わったときに、その走行が消えていれば質問は書かない（`AskDao.keep`）。
-- 質問できなかった地点（US-C-09）: 録音を終えた時点で通信できないとき、または `POST /asks` が通信の失敗（試し直しのあとの 5xx・流量の制限を含む）に終わったとき、質問の一巡は日時・位置・方位の材料を `asks` に `status = offline` で残す（識別子は端末で作る。会話の識別子は無い）。録音は捨て、SC-12 にも残さない。会話の文脈は進めない。接続キーの誤りなど、断られた失敗では残さない。`PUT /asks/{askId}/offline` で送り、応答の住所と方位を行に書く。409（同じ識別子の質問が Backend にある）は断られたものとして扱う。
+- 質問できなかった地点（US-C-09）: 録音を終えた時点で通信できないとき、または `POST /asks` が通信の失敗（試し直しのあとの 5xx・流量の制限を含む）に終わったとき、質問の一巡は日時・位置・方位の材料を `asks` に `status = offline` で残す（識別子は端末で作る。会話の識別子は無い）。録音は捨て、SC-12 にも残さない。会話の文脈は進めない。接続キーの誤りなど、断られた失敗では残さない。書けたらすぐ送信の契機を呼ぶ（通信の失敗でも、既定のネットワークは残っていることがあるため）。`PUT /asks/{askId}/offline` で送り、応答の住所と方位を行に書く。409（同じ識別子の質問が Backend にある）は断られたものとして扱う。住所を決められずに受け付けられた地点メモと質問できなかった地点は、起動ごとに一度、版を進めて送り直す（Backend は新しい版でだけ住所を求め直す）。
+- クラウドの記録を読み込むのは、SC-18 でユーザー名を変えるときと、SC-14 の「クラウドから読み直す」だけ（親の adr/0010）。`Takeover` が `GET /records` を最後のページまで読んでから、`RoomTakeover` が1つのトランザクションで突き合わせて入れる（`Merge.kt`: `updatedAt` が新しいほうを残す・クラウドの削除の跡で消す・端末の未送信の削除はクラウドの写しを入れない・ルートは点の多いほう・記録中のまま残っていた走行は終えて入れ、送り直す）。入れたものは送り済みの印を付ける。ユーザー名を変えるときは端末の記録を消してから入れ、そのあとで名前を保存する。読み始めから名前の保存までは `RideSync.withoutPasses` の中で、送信の回が走らない。走行の記録中・一時停止中は、どちらも行わない。ユーザー名は、未送信（SC-14 が数えるもの。断られた版と記録中の走行は数えない）があるあいだも変えられない。トランザクションの中でも確かめ直す。
 - SC-19 の声の入力（`VoiceInput`）は、質問とは別の経路の切り替えと録音の部品を持つ（試し録りと同じ）。SC-19 を開いているあいだ（`attach`）は、インカムのボタンが質問を始めず、声の入力を始める・止める（質問が進んでいるときは質問のまま）。録音は60秒まで。`POST /transcriptions` に送り、質問と同じ間隔で `GET` し、120秒で打ち切る。聞き取れた文は入力欄の終わりに足す。通信できないときは画面のボタンを押せず、インカムのボタンは失敗の合図だけを鳴らす。SC-19 を離れると、録音も文字起こしの待ちも捨てる。前面サービスは使わない（SC-19 を見ながら使う前提）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
 - インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index d1810fd..2ad5218 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 10
-    versionName = "0.9.0"
+    versionCode = 11
+    versionName = "0.10.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
EOF
```

- [ ] **Step 2: 親の文書を Android に写す**

Run: `cd $ROOT && scripts/sync-docs.sh Android && git -C Android status --short docs-parent`
Expected: この plan と、plan のコミットで直した `08a_android-design.md`・`mock/index.html` などが写る

- [ ] **Step 3: コミット**

```bash
cd $AND && git add README.md app/build.gradle.kts docs-parent
git commit -m "docs: describe reading the cloud's records in, and raise the version to 0.10.0"
```

---

### Task 10: 全体の確かめ

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

Expected: `605 0`。`BUILD SUCCESSFUL`。`release permissions OK (15)`。`RideForegroundServiceTest` の1件がまれに落ちる（Android #59）。落ちたら単独で回し直し、全体をもう一度回す

- [ ] **Step 2: エミュレーターのテスト**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: 6件が通る

---

### Task 11: 利用者の実機の確認と spec §1 の判定

走行用のビルド（版 0.10.0）を実機（Pixel 8a のメインのユーザー）に入れる。表は変えていないので、マイグレーションは走らない。

```bash
cd $AND && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

確かめる前に、AI が DynamoDB の今のユーザー名のパーティションの件数を種類ごとに数えておく（読むだけ。ユーザー名はチャットにだけ出す）。

1. **SC-14**（spec §1 の3つ目）: 設定に「☁️ データの保存」と「保存済み」が出る。開くと「● すべてクラウドに保存済み」と最終保存の時刻、件数（走行・質問・端末の音声 n / 10）。走行を始め、機内モードで地点メモを書くと「未送信の記録があります」と内訳（「地点メモ 1件」）と「記録中の走行は、一時停止か終了で残りを送ります。」が出て、設定の行が「未送信あり」になる。機内モードを外して「今すぐ保存」を押すと、送っているあいだ押せず、終わると「保存済み」になり、最終保存の時刻が進む。記録中は「クラウドから読み直す」が押せず「走行を終えてから読み直せます」。走行を終える。
2. **読み直す**: 「クラウドから読み直す」を押す → 「読み込んでいます…」のあと「新しい記録はありませんでした」（か、入れた件数）。記録の一覧は変わらない。**読み込みにかかった時間を測る**（押してから結果が出るまで。今ある記録の件数と一緒に、チャットに書く）。
3. **変えられないとき**: SC-08 で会話のメモを書き、機内モードのまま SC-18 を開く → 「変更する」が押せず「未送信の記録があります。先に「データの保存」で送ってください」と「データの保存へ」。機内モードを外して送り、押せるようになる。走行の記録中も押せない（「走行を終えてから変えられます」）。
4. **ユーザー名の切り替え**（spec §1 の5つ目）: 控えた今の名前を A とする。SC-18 で、使ったことのない名前 B にする → DL-03 が「ユーザー名を変えますか？」「「B」は新しいユーザー名です。…」と「変更する」。変更すると「読み込んでいます…」のあと「ユーザー名を変えました」。記録の一覧が空になる。SC-14 の件数が 0。もう一度 SC-18 で A に戻す → DL-03 が「既にあるユーザー名です」「「A」の記録が既にあります。…」と「切り替える」。切り替えると A の記録（走行・ルート・質問・メモ・地点メモ・質問できなかった地点）がすべて戻る。消した記録は戻らない。名前を変えた直後の質問は、新しい会話として始まる（ホームの会話の表示）。SC-12 の録音は残っている。
5. **入れ直し**（spec §1 の4つ目）: アプリを外して入れ直す（`adb uninstall --user 0 com.touringproject.v2` のあと `adb install --user 0 ...`。接続キーを入れ直す）。既定のランダムな名前で開き、記録は空。SC-18 で A に変える → DL-03「既にあるユーザー名です」→ 切り替えると、走行・ルート（地図）・質問・メモ・地点メモ・質問できなかった地点（「（通信できず、質問できなかった）」の行と、住所）が戻る。消した記録は戻らない。録音は戻らない（SC-12 が空）。SC-14 が「保存済み」。AI が、読み込みのあとにユーザー A のパーティションの件数が手順の前と同じ（増えていない・送り返していない）ことを DynamoDB で確かめる（読むだけ）。
6. **#64**（できれば）: 電波の弱い所などで、通信できるのに `POST /asks` が失敗して質問できなかった地点が残ったときに、前面に出さずに送られることを、AI が DynamoDB で確かめる（起こせなければ、自動テストで確かめたとして通す）。

✗ が出たら `superpowers:systematic-debugging`。手順 2 の時間が長ければ（目安: 10秒を超える）、spec §12 のとおり、進み具合の件数を出すかを利用者と決める。
