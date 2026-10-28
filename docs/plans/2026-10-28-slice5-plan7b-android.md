# スライス5 計画7b: Android（スライス5の途中で立てた指摘） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** スライス5の plan 3〜6 の最終レビューで立てた Android の指摘12件（#79〜#81・#83〜#86・#88〜#91・#93）を直し、版 0.14.0 にする。この版で、plan 6 の Task 8 の走行（spec §1 の判定）と plan 3・4 の残りの確かめを行う。

**Architecture:** 指摘ごとに小さく直す。文字の質問は、取り消しをシートへすぐ知らせ（`AskController` の `Run.cancelled`）、取り消したあとの `POST` の成功を「受け付けなかった」とする。文字の質問も始めにメディアの音量を読み、SC-03 の帯を出すかは `FlowState.tellsVolume` が決める。録音の刈り込みは、録音が残ると分かったとき（`RecordingSink.kept`）にだけ行う。SC-22 は集める点を `HEADING_POINTS` までにし、`GpsClock` は起動時に端末の最後の位置から覚える。名前の変更は、名前の保存から戻すまでを取り消しで止めず、戻せなければ `TakeResult.Mismatched` を返す。走行の書き直し待ちの印は書き込みのあとで立て、保存の集計は画面が読まなくなったら捨てる（`whileShown`）。Room は版7のまま。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版7のまま）・DataStore・Robolectric 4.16（SDK 35）。足す依存は無い。

**Spec:** [docs/specs/2026-10-25-slice5-design.md](../specs/2026-10-25-slice5-design.md) §15（範囲は §15.1、決めたことは §15.2、進め方は §15.3）。

**範囲に入れた issue（Android）:** #79（文字の質問を送っているあいだに取り消すと、押せないシートが出て、受け付けられていればそのまま閉じる）・#80（録音を POST の前に残すため、10件あると質問できなかった地点になったときに一番古い録音が無駄に消える）・#81（文字の質問では SC-03 にメディアの音量の警告の帯が出ない）・#83（SC-22 で記録していないあいだに集める点に上限が無い）・#84（位置をまだ受けていないプロセスでは、方位の保つ上限を端末の時計で数える）・#85（SC-22 を離れたときに監視が外れることを、画面の水準で確かめるテストが無い）・#86（SC-22 の基準の点の古さが負のとき、0に揃えていない）・#88（ユーザー名の変更で名前を戻す処理が、取り消しと戻す保存の失敗に備えていない）・#89（走行の書き直し待ちの印が、成功する保存のあいだも一瞬立つ）・#90（保存の集計が、画面に戻った直後に古い値を一瞬出す）・#91（ScreensTest で assertIsEnabled の import が重なっている）・#93（README の送信の決まりの重なりと、MapLibre の理由の書き方）。

**前提:** Android の `main`（`3ab3851`。版 0.13.0・JVM のテスト699件）の上に作る。Backend・Agent は変えない（plan 7a でデプロイ済み）。

**計画を書くときに決めたこと（spec からの具体化）:**

- **#79:** `AskController` の1回の質問（`Run`）に、取り消されたときに呼ぶ `cancelled` を持たせる。文字の質問は、ここでシートに `NOT_TAKEN` を知らせる（シートは `sending` でなくなり、すぐ打ち直せる）。`POST` が通ったときは、会話の文脈を進めたうえで、今の質問でなければ何も知らせずに終える（シートには取り消しのときに `NOT_TAKEN` が届いている）。`SENT` は今の質問のときだけ知らせる。
- **#81:** `FlowEvent.StartText(now, mediaVolume)`・`FlowState.typed`（文字の質問か）を足す。SC-03 の帯を出すかは `FlowState.tellsVolume`（録音中、または文字の質問の送っているあいだ・回答待ち）。声の質問は今のまま録音中だけ（録音のあとはインカムの経路がメディアの音を持つため）。
- **#80:** `RecordingSink.kept()`（残した録音が残ると分かった。古い録音を刈り込む）を足す。質問の一巡は、`POST` が通ったときと、通信の失敗でない失敗（断られた）ときに呼び、通信の失敗では呼ばない（`discarded` で消す）。`RecordingStore.save(meta, pcm, prune = true)`・`prune()` にし、`RecordingKeeper.saved` は `prune = false` で書く。残ると分かるまでのあいだ（プロセスがそこで死んだときを含む）は11件になりうるのを受け入れる。
- **#83:** `HEADING_POINTS`（120）を `ride/RouteHeading.kt` から `location/Heading.kt` へ移し、`HeadingCheck` が集める点も、超えたら古いものから捨てる（`location` が `ride` に依存しないため）。
- **#84:** `GpsClock.learnFrom(positions)`（`lastKnown` の位置で覚える。権限が無く投げても何もしない）を足し、`AppGraph` で `positionSource` を作ったところで1回呼ぶ。
- **#85:** `AppGraph.headingCheck` を関数から関数の型のプロパティ（`var headingCheck: () -> HeadingCheck`）にし、`AppUiTest` が作り物の窓口の `HeadingCheck` に差し替えて、SC-22 を開く・別のタブ・戻る・背面で監視の数を確かめる（呼び出し側の `graph.headingCheck()` は変わらない）。このテストは、計画を書くときに、入口から `repeatOnLifecycle` を外すと落ちることを確かめた。
- **#86:** `headingCheckUi` で古さを `coerceAtLeast(0)` してから文言にする。テストは、整数の割り算で「0秒前」に丸まらない -1500ms で落ちることを見る。
- **#88:** `Takeover.switchTo` の、名前の保存（`save(新しい名前)`）から記録の書き込み・戻す保存までを `withContext(NonCancellable)` で囲む（読み込み `readAll` は取り消せるまま）。`putBack` は `Boolean` を返し、戻せなかったら `TakeResult.Mismatched` を返す（記録の書き込みが投げたときも同じ）。SC-18 の文言は「ユーザー名は変わりましたが、記録を入れられませんでした。端末の記録は前の名前のままです」。読み直し（SC-14）は名前を変えないので `Mismatched` にならないが、`when` を尽くすため「読み込めませんでした」に寄せる。
- **#89:** `RideController.unsaved` の setter で印を更新するのをやめ、書き込みのあと（`save` の最後・`dropUnsavedMemo`・`delete`）に `told()` で更新する。
- **#90:** `records/Saving.kt` に `Flow<SaveSummary>.whileShown(scope)`（`WhileSubscribed(5_000, replayExpirationMillis = 0)`）を足し、`AppGraph.saveSummary` に使う。SC-05 の一覧（`recordsList`）は戻ったときにすぐ出す（Android #49）ので、今のままにする。
- **#91・#93:** 対応案のとおり。README は、この plan の直しの説明も足す（Task 11）。
- 版を 0.14.0（`versionCode` 15）に上げる。
- 計画を書くときの全体のテストで、`RideForegroundServiceTest.the_ask_keep_alive_reaches_the_running_service` が1回だけ落ちた（単独では3回とも通り、全体を回し直すと通った）。この plan の変更はサービスに触れないので、範囲の外とし、Android #94 に書いた。

この計画のコードは、使い捨てのフォルダで、次を確かめてから書いた。

- タスクの順に一つずつコミットし、各タスクのテストだけを当てると落ちる（まだ無い名前を使うのでコンパイルで落ちるか、期待が外れて落ちる）。例外は Task 11（import と文書と版）。
- 最後に、`clean` から JVM のテスト712件・`assembleDebug`・`assembleRelease`・`scripts/check-release-permissions.sh`・エミュレーターのテストのコンパイルが通る。
- 各タスクの差分は、前のタスクまでを当てた写しにそのまま当たる。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice5-plan7b` を切る（Task 0）。親は、この plan を書いたブランチ `slice5-plan7b`。push・マージはしない（利用者が明示したときだけ）。push の前に `pre-push-secret-scan`（スキャンと push は別のコマンドにし、結果を読んでから）。
- 作りの決まり: 判断の芯（`Takeover` の順番・`findHeading`）は Android に依存させない。部品は `AppGraph` で手で組む。走行を変えるのは `RideController` だけ。
- Room は版7のまま（表を変えない）。破壊的な作り直しは使わない。
- ホームは全体がスクロールしない（この plan ではホームを変えない）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない（テストの作り物の名前 `rider01`・`taro01` などは除く）。端末のログ（`adb logcat`）には API の URL が出るので、書き写さない。
- コードのコメントは英語、文書は日本語。Conventional Commits。直したコミットに `Fixes #N`。`git add .`・`-A` は使わない。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*クラス名'`。Gradle のビルドキャッシュはフォルダをまたいで共有されるので、テストを確かめるときは `--rerun` を付ける。Kotlin の差分コンパイルは interface の変更を見逃すことがあるので、Task 12 は `./gradlew clean` から回す。
- テストの結果は `app/build/test-results/testDebugUnitTest/*.xml` で読む（失敗の行と期待の値が出る）。
- Robolectric の決まり（SDK 35・画面の外の行は `performScrollTo` で出す・地図の部品は動かさない）。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。使い終わったら止める。1回目に APK を入れる途中で「device offline」で止まったら、起動し直して回す。
- この Mac はディスクの空きが少ない。Gradle のキャッシュは使うたびに増える。

## Review Focus

- 文字の質問を送っているあいだに取り消し、すぐ「質問する」をもう一度押す（前の `POST` はまだ終わっていない）→ 新しい質問が始まり、前の `POST` が通っても新しい質問の画面とシートを動かさない。Task 1 のテストは取り消しまでを見るので、押し直しは `isCurrent` と `told` の組で守られているかを読む。
- メディアの音量が低いまま帯を ✕ で閉じたあと、同じ音量で文字の質問をする → SC-03 にも帯を出さない（`volumeWarning` の閉じた音量）。Task 2 は出る場面だけを見る。
- 質問の録音を残したあと、`POST` の前にプロセスが死ぬ → SC-12 に11件が並び、次の質問の `kept` で10件に戻る。Task 3 は刈り込みの呼び方だけを見る。
- 名前の変更が `Mismatched` になったあと → SC-18 の「今のユーザー名」は新しい名前で、文言は実際を出す。次の送信で、古い名前の未送信が新しい名前に送られうる（spec §15.2 は出すことまでを決めた）。Task 8 は結果と文言を見る。
- 一時停止中にプロセスが作り直され、位置の権限が無い → 起動で落ちず、端末の時計で数える。Task 5 は `learnFrom` の単体で見る。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `ask/AskController.kt` | 取り消しをシートへ知らせる（1）・文字の質問の音量（2）・録音の刈り込みを頼む（3） | 1・2・3 |
| `ask/Flow.kt` | `StartText` の音量・`typed`・`tellsVolume` | 2 |
| `ui/AskOverlay.kt` | 帯を `tellsVolume` で出す | 2 |
| `ask/AskPorts.kt`・`recordings/RecordingStore.kt` | `RecordingSink.kept`・刈り込みを分ける | 3 |
| `location/Heading.kt`・`location/HeadingCheck.kt`・`ride/RouteHeading.kt` | `HEADING_POINTS` を移し、集める点に使う | 4 |
| `location/GpsClock.kt`・`AppGraph.kt` | `learnFrom`（5）・`headingCheck` の差し替え（7）・`whileShown`（10） | 5・7・10 |
| `ui/HeadingLabels.kt` | 古さを0に揃える | 6 |
| `sync/Takeover.kt`・`ui/SavingLabels.kt` | `NonCancellable`・`Mismatched`・文言 | 8 |
| `ride/RideController.kt` | `told()` | 9 |
| `records/Saving.kt` | `whileShown` | 10 |
| `app/build.gradle.kts`・`README.md` | 版と説明 | 11 |

---

### Task 0: 作業ブランチと文書の写し

- [ ] **Step 1: Android でブランチを切り、文書の写しをコミットして、今のテストを回す**

親の plan のコミットで `scripts/sync-docs.sh` を回し、Android の `docs-parent/` が変わっている。Android の写しはこのブランチに、ほかのユニット（Backend・Agent・CICD）の写しはそれぞれの `main` に直接コミットしてある（親の plan のコミットの前提）。

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice5-plan7b
cd $AND && git add docs-parent && git commit -m "docs: sync the parent's docs for slice 5 plan 7b"
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-t0.log 2>&1; tail -1 /tmp/trv2-t0.log
```

Expected: `BUILD SUCCESSFUL`（699件）。写しの差分が無ければ、コミットは飛ばす。

---

### Task 1: 送っているあいだに取り消した文字の質問を、シートに残す（#79）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ask/AskController.kt`
- Test: `app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt`（`TextAskTest`）

**Interfaces:**
- Produces: 文字の質問を取り消すと、その場で `taken(TextAskOutcome.NOT_TAKEN)` が1回だけ呼ばれる。そのあと `POST` が通っても `SENT` は呼ばれず、回答を待たない。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index 01f8c97..447276d 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -875,6 +875,24 @@ class TextAskTest {
     assertTrue(h.kept.isEmpty())
   }
 
+  // Android #79: cancelled while it is sent, the sheet can send again at once, and a POST that goes through afterwards
+  // is still a text not taken: the sheet keeps it and no answer is waited for.
+  @Test
+  fun a_text_ask_cancelled_while_it_is_sent_is_not_taken_even_when_the_post_goes_through() = runTest {
+    val posted = CompletableDeferred<Unit>()
+    val h = Harness(this, post = { posted.await(); ACCEPTED })
+    val running = launch { h.askText("右手に見える山は何？") }
+    h.until { "post" in h.log }
+    h.controller.cancel()
+    assertEquals(listOf(TextAskOutcome.NOT_TAKEN), h.outcomes)
+    posted.complete(Unit)
+    running.join()
+    assertEquals(listOf(TextAskOutcome.NOT_TAKEN), h.outcomes)
+    assertFalse("get" in h.log)
+    assertTrue(h.kept.isEmpty())
+    assertEquals(Phase.IDLE, h.phase)
+  }
+
   // §4.1: without a fresh position, the text ask goes without a place, and the heading is asked without one.
   @Test
   fun without_a_position_a_text_ask_goes_without_a_place() = runTest {
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TextAskTest'`
Expected: `a_text_ask_cancelled_while_it_is_sent_is_not_taken_even_when_the_post_goes_through` が、取り消した直後の `outcomes` の確かめ（`[NOT_TAKEN]` のはずが空）で落ちる。

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index cf51353..df0b362 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -50,7 +50,8 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
   private var busySpeech: Deferred<Unit>? = null
 
   // Per-ask state: an older ask that is still unwinding must not read or change the newer one's.
-  private class Run(val id: Int, val source: Source, var returned: Boolean = false)
+  // cancelled is told when the rider ends the ask with the big button (a text ask's sheet: Android #79).
+  private class Run(val id: Int, val source: Source, var returned: Boolean = false, val cancelled: () -> Unit = {})
 
   // meta and pcm go to SC-12 as the ask is sent; an unreached ask's recording goes again (Android #68).
   // heading is worked out once, where the recording ended, for the ask sent and the unreached one alike.
@@ -95,6 +96,7 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
   /** The big button: end the current ask now; whatever it is awaiting is ignored when it returns. */
   fun cancel() {
     if (state.phase == Phase.IDLE) return
+    current?.cancelled?.invoke()
     runId += 1
     current = null
     deps.player.stop()
@@ -173,9 +175,6 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
   suspend fun runText(text: String, taken: (TextAskOutcome) -> Unit) {
     val d = deps
     if (state.phase == Phase.FAILED) d.speech.stop()
-    val run = Run(++runId, Source.SCREEN)
-    current = run
-    runsStarted += 1
     var told = false
     val tell = { outcome: TextAskOutcome ->
       if (!told) {
@@ -183,6 +182,10 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
         taken(outcome)
       }
     }
+    // Cancelled before the Backend took it, the sheet can send again at once, without waiting for the POST.
+    val run = Run(++runId, Source.SCREEN, cancelled = { tell(TextAskOutcome.NOT_TAKEN) })
+    current = run
+    runsStarted += 1
     dispatch(FlowEvent.StartText(d.now()))
     try {
       val ride = d.ride()
@@ -261,10 +264,11 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
       }
       return null
     }
-    // The Backend has it either way: the sheet's text has gone, and the conversation goes on.
-    tell(TextAskOutcome.SENT)
+    // The Backend has it either way, so the conversation goes on. A text cancelled meanwhile stays not taken, and the sheet
+    // keeps it (Android #79); the ask left on the Backend is taken as a voice ask's is.
     d.conversation.update(accepted.conversationId, accepted.conversationExpiresAt)
     if (!isCurrent(run)) return null
+    tell(TextAskOutcome.SENT)
     dispatch(FlowEvent.Sent(accepted.askId, d.now()))
     d.cues.sent()
     return SentAsk(accepted.askId, accepted.conversationId, body.conversationId == null, d.now(), here, rideId, ASK_INPUT_TEXT, text)
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests 'com.touringproject.v2.ask.*'`
Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
cd $AND && git commit -m "fix: leave a text ask cancelled while it is sent with the sheet, even when its POST goes through (Fixes #79)"
```

---

### Task 2: 文字の質問でも音量を読み、SC-03 に低い音量の帯を出す（#81）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ask/Flow.kt`・`ask/AskController.kt`・`ui/AskOverlay.kt`
- Test: `app/src/test/java/com/touringproject/v2/ask/FlowTest.kt`・`ask/AskControllerTest.kt`（文字の質問の手順の記録に `vol:read` が先頭に入る）・`ui/ScreensTest.kt`

**Interfaces:**
- Produces: `FlowEvent.StartText(now: Long, mediaVolume: MediaVolume? = null)`・`FlowState.typed: Boolean`・`val FlowState.tellsVolume: Boolean`（`Flow.kt` の最上位）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index 447276d..08ebfbb 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -792,7 +792,9 @@ class TextAskTest {
   fun a_text_ask_starts_at_sending_and_is_read_out_without_returning() = runTest {
     val h = Harness(this, answers = listOf(done(transcript = null)))
     h.askText("右手に見える山は何？")
-    assertEquals(listOf("svc:start", "loc:latest", "post", "cue:sent", "get", "play:https://audio/1.mp3", "svc:stop"), h.log)
+    assertEquals(listOf("vol:read", "svc:start", "loc:latest", "post", "cue:sent", "get", "play:https://audio/1.mp3", "svc:stop"), h.log)
+    // Android #81: the volume is read as the ask starts, for SC-03's band.
+    assertEquals(MediaVolume(2, 25), h.states.first().mediaVolume)
     assertEquals(
       AskBody(volumeDb = 6, text = "右手に見える山は何？", location = Point(35.6812, 139.7671), headingDegrees = 12.5, conversationId = null, rideId = "r1"),
       h.bodies.single(),
@@ -839,7 +841,7 @@ class TextAskTest {
     assertEquals(listOf(TextAskOutcome.OFFLINE), h.outcomes)
     assertTrue(h.kept.isEmpty())
     assertTrue(h.states.none { it.phase == Phase.FAILED })
-    assertEquals(listOf("svc:start", "loc:latest", "post", "svc:stop"), h.log)
+    assertEquals(listOf("vol:read", "svc:start", "loc:latest", "post", "svc:stop"), h.log)
   }
 
   // Refusals show why on SC-03 (US-B-06.004), and the sheet keeps the text.
diff --git a/app/src/test/java/com/touringproject/v2/ask/FlowTest.kt b/app/src/test/java/com/touringproject/v2/ask/FlowTest.kt
index 094fa08..cd7f131 100644
--- a/app/src/test/java/com/touringproject/v2/ask/FlowTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/FlowTest.kt
@@ -104,4 +104,19 @@ class FlowTest {
     val s = run(FlowEvent.Start(Source.HANDSFREE, 1, MediaVolume(3, 15)), FlowEvent.StopRecording(2))
     assertEquals(MediaVolume(3, 15), s.mediaVolume)
   }
+
+  // Android #81: a text ask carries the volume read at its start, and SC-03 tells a low one while the text is sent and
+  // the answer waited for, as the answer is read out on the media stream; a voice ask tells it only while recording.
+  @Test
+  fun a_text_ask_tells_the_volume_while_it_is_sent_and_waited_for() {
+    val text = run(FlowEvent.StartText(1, MediaVolume(3, 15)))
+    assertEquals(MediaVolume(3, 15), text.mediaVolume)
+    assertTrue(text.tellsVolume)
+    val waiting = reduce(text, FlowEvent.Sent("a1", 2))
+    assertTrue(waiting.tellsVolume)
+    assertFalse(reduce(waiting, FlowEvent.Answered("x", 3)).tellsVolume)
+    val voice = run(FlowEvent.Start(Source.SCREEN, 1, MediaVolume(3, 15)))
+    assertTrue(voice.tellsVolume)
+    assertFalse(reduce(voice, FlowEvent.StopRecording(2)).tellsVolume)
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index 244f0e1..8c97caf 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -221,6 +221,16 @@ class AskOverlayTest {
     assertEquals(2, dismissed)
   }
 
+  // Android #81: a text ask's answer is read out on the media stream too, so the band shows while it is sent.
+  @Test
+  fun the_low_volume_band_shows_while_a_text_ask_is_sent_but_not_a_voice_one() {
+    var state by mutableStateOf(FlowState(phase = Phase.SENDING, typed = true, mediaVolume = MediaVolume(2, 15)))
+    rule.setContent { AskOverlay(state, { 0L }, {}, {}) }
+    rule.onNodeWithTag("overlayVolume").assertIsDisplayed()
+    state = FlowState(phase = Phase.SENDING, mediaVolume = MediaVolume(2, 15))
+    rule.onNodeWithTag("overlayVolume").assertDoesNotExist()
+  }
+
   @Test
   fun a_band_closed_at_this_volume_stays_closed() {
     val state = FlowState(phase = Phase.RECORDING, mediaVolume = MediaVolume(2, 15))
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*FlowTest' --tests '*TextAskTest' --tests '*ScreensTest'`
Expected: コンパイルで落ちる（`StartText` の引数が多い・`tellsVolume` と `typed` が無い）。

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index df0b362..c74ca5c 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -186,7 +186,7 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
     val run = Run(++runId, Source.SCREEN, cancelled = { tell(TextAskOutcome.NOT_TAKEN) })
     current = run
     runsStarted += 1
-    dispatch(FlowEvent.StartText(d.now()))
+    dispatch(FlowEvent.StartText(d.now(), d.mediaVolume()))
     try {
       val ride = d.ride()
       refusal(ride)?.let {
diff --git a/app/src/main/java/com/touringproject/v2/ask/Flow.kt b/app/src/main/java/com/touringproject/v2/ask/Flow.kt
index 5db6cdd..10a9f3a 100644
--- a/app/src/main/java/com/touringproject/v2/ask/Flow.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/Flow.kt
@@ -25,8 +25,17 @@ data class FlowState(
   val mediaVolume: MediaVolume? = null,
   /** How long this ask may record (SC-11), for SC-03's countdown. */
   val recordLimitMs: Long = DEFAULT_RECORD_LIMIT_MS,
+  /** A text ask (slice 5 spec §5.3). */
+  val typed: Boolean = false,
 )
 
+/**
+ * Whether SC-03 tells a low media volume now: while recording, and for a text ask while it is sent and its answer waited
+ * for, as the answer is read out on the media stream (Android #81). A voice ask's route has taken the stream over then.
+ */
+val FlowState.tellsVolume: Boolean
+  get() = phase == Phase.RECORDING || (typed && (phase == Phase.SENDING || phase == Phase.WAITING))
+
 val IDLE = FlowState()
 
 sealed interface FlowEvent {
@@ -38,7 +47,7 @@ sealed interface FlowEvent {
     val recordLimitMs: Long = DEFAULT_RECORD_LIMIT_MS,
   ) : FlowEvent
   /** A text ask from Home (slice 5 spec §5.3): nothing to record, so it starts as it is sent. */
-  data class StartText(override val now: Long) : FlowEvent
+  data class StartText(override val now: Long, val mediaVolume: MediaVolume? = null) : FlowEvent
   data class PhoneMic(override val now: Long) : FlowEvent
   data class StopRecording(override val now: Long) : FlowEvent
   data class Sent(val askId: String, override val now: Long) : FlowEvent
@@ -57,7 +66,9 @@ fun reduce(state: FlowState, event: FlowEvent): FlowState = when (event) {
       )
     } else state
   is FlowEvent.StartText ->
-    if (state.phase == Phase.IDLE || state.phase == Phase.FAILED) FlowState(phase = Phase.SENDING, source = Source.SCREEN, phaseStartedAt = event.now) else state
+    if (state.phase == Phase.IDLE || state.phase == Phase.FAILED) {
+      FlowState(phase = Phase.SENDING, source = Source.SCREEN, phaseStartedAt = event.now, mediaVolume = event.mediaVolume, typed = true)
+    } else state
   is FlowEvent.PhoneMic -> if (state.phase == Phase.RECORDING) state.copy(phoneMic = true) else state
   is FlowEvent.StopRecording ->
     if (state.phase == Phase.RECORDING) state.copy(phase = Phase.SENDING, phaseStartedAt = event.now) else state
diff --git a/app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt b/app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt
index 5af76db..ccb9ca7 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt
@@ -30,6 +30,7 @@ import androidx.compose.ui.unit.sp
 import com.touringproject.v2.ask.FlowState
 import com.touringproject.v2.ask.Phase
 import com.touringproject.v2.ask.spokenMessage
+import com.touringproject.v2.ask.tellsVolume
 import kotlinx.coroutines.delay
 
 data class OverlayText(val title: String, val big: String, val detail: String, val button: String)
@@ -85,7 +86,7 @@ fun AskOverlay(
     }
     // The volume was read when the ask started, before the intercom route took over the music stream.
     val volume = state.mediaVolume
-    if (state.phase == Phase.RECORDING && volume != null && volumeWarning(volume, volumeDismissedAt)) {
+    if (state.tellsVolume && volume != null && volumeWarning(volume, volumeDismissedAt)) {
       WarningBand(Banner.LOW_VOLUME.text, null, { onDismissVolume(volume.current) }, Modifier.testTag("overlayVolume"))
     }
     Column(
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests 'com.touringproject.v2.ask.*' --tests '*ScreensTest'`
Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/Flow.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt app/src/test/java/com/touringproject/v2/ask/FlowTest.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
cd $AND && git commit -m "fix: read the media volume for a text ask and tell a low one on SC-03 while it is sent and answered (Fixes #81)"
```

---

### Task 3: 古い録音の刈り込みを、録音が残ると分かったときだけにする（#80）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ask/AskPorts.kt`・`recordings/RecordingStore.kt`・`ask/AskController.kt`
- Test: `app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt`・`ask/AskControllerTest.kt`（作り物の `RecordingSink` に `kept` を足す）

**Interfaces:**
- Produces: `RecordingSink.kept()`・`RecordingStore.save(meta: RecordingMeta, pcm: ByteArray, prune: Boolean = true)`・`RecordingStore.prune()`。`RecordingSink` を実装する作り物は `kept` を持つ（`AskControllerTest` の `Harness` だけ）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
index 08ebfbb..7db0755 100644
--- a/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt
@@ -83,6 +83,8 @@ private class Harness(
   val metas = mutableListOf<RecordingMeta>()
   val keptPcm = mutableListOf<ByteArray>()
   val discarded = mutableListOf<String>()
+  /** How many times the older recordings were asked to be pruned. */
+  var prunes = 0
   val transcripts = mutableListOf<Pair<String, String>>()
   val kept = mutableListOf<AskRecord>()
   private val results = answers.toMutableList()
@@ -134,6 +136,7 @@ private class Harness(
         if (at >= 0) { metas.removeAt(at); keptPcm.removeAt(at) }
       }
       override fun transcribed(name: String, transcript: String) { transcripts += name to transcript }
+      override fun kept() { prunes += 1 }
     },
     asks = { kept += it },
     online = { online },
@@ -709,6 +712,18 @@ class AskControllerTest {
     assertTrue(failed.metas.isEmpty())
   }
 
+  // Android #80: the older recordings are pruned only for a recording that stays: its ask was taken, or refused.
+  @Test
+  fun older_recordings_are_pruned_only_for_a_recording_that_stays() = runTest {
+    // What the POST fails with (null: it goes through), and how many prunes follow.
+    val cases = listOf(null to 1, ApiErrorKind.INVALID_KEY to 1, ApiErrorKind.NETWORK to 0)
+    for ((error, prunes) in cases) {
+      val h = Harness(this, stopAfterMs = 1_000, post = { error?.let { throw ApiError(it) } ?: ACCEPTED })
+      h.controller.run(Source.HANDSFREE)
+      assertEquals(prunes, h.prunes)
+    }
+  }
+
   // The rider cancelled while the ask was being sent: they let it go, so it is not kept even when the send fails.
   @Test
   fun an_ask_cancelled_while_sending_is_not_kept_as_unreached() = runTest {
diff --git a/app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt b/app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt
index 36e9571..fcc4b3b 100644
--- a/app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt
+++ b/app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt
@@ -104,6 +104,22 @@ class RecordingStoreTest {
     assertEquals(listOf(meta(200)), store.list())
   }
 
+  // Android #80: a recording kept before its POST leaves the ten before it alone; only one that stays prunes them.
+  @Test
+  fun a_recording_saved_then_discarded_leaves_the_ten_before_it() = runTest {
+    val store = RecordingStore(dir, io = StandardTestDispatcher(testScheduler))
+    val keeper = RecordingKeeper(store, this) { _, _ -> }
+    (1L..10L).forEach { store.save(meta(it), byteArrayOf(1)) }
+    keeper.saved(meta(11), byteArrayOf(1))
+    keeper.discarded("rec-11.pcm")
+    testScheduler.advanceUntilIdle()
+    assertEquals((10L downTo 1L).toList(), store.list().map { it.recordedAt })
+    keeper.saved(meta(12), byteArrayOf(1))
+    keeper.kept()
+    testScheduler.advanceUntilIdle()
+    assertEquals(listOf(12L) + (10L downTo 2L), store.list().map { it.recordedAt })
+  }
+
   @Test
   fun the_keeper_never_lets_a_store_failure_reach_the_ask() = runTest {
     // A file where the directory should be: every write fails.
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*AskControllerTest' --tests '*RecordingStoreTest'`
Expected: コンパイルで落ちる（`kept` が無い）。

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskController.kt b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
index c74ca5c..fdcce46 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskController.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskController.kt
@@ -395,9 +395,11 @@ class AskController(private val deps: AskDeps, private val scope: CoroutineScope
         keepUnreached(recording, rideId, run)
         return null
       }
+      d.recordings.kept()
       fail(reason, run)
       return null
     }
+    d.recordings.kept()
     // The ask exists on the Backend either way, so keep the conversation going even if it was cancelled.
     d.conversation.update(accepted.conversationId, accepted.conversationExpiresAt)
     if (!isCurrent(run)) return null
diff --git a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
index 5dd3d14..b2d3c22 100644
--- a/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ask/AskPorts.kt
@@ -44,6 +44,8 @@ interface RecordingSink {
   fun transcribed(name: String, transcript: String)
   /** The recording saved goes again: its ask never reached the Backend (US-C-09.001). */
   fun discarded(name: String)
+  /** The recording saved stays (its ask was taken or refused): only the newest ones are kept now (Android #80). */
+  fun kept()
 }
 
 /** Fire and forget: a failure to keep an ask must not end it. */
diff --git a/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt b/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt
index b468781..010661c 100644
--- a/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt
+++ b/app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt
@@ -42,11 +42,22 @@ class RecordingStore(private val dir: File, private val io: CoroutineDispatcher
   /** Bumped after every change, so SC-12 can reload its list. */
   val changes: StateFlow<Int> = changeCount.asStateFlow()
 
-  suspend fun save(meta: RecordingMeta, pcm: ByteArray) = change {
+  /**
+   * Without prune, the older recordings are left until prune() (an ask's recording, which may go again: Android #80), so
+   * there may be one over the newest [keep] meanwhile.
+   */
+  suspend fun save(meta: RecordingMeta, pcm: ByteArray, prune: Boolean = true) = change {
     require(PCM_RE.matches(meta.name)) { "bad recording name" }
     dir.mkdirs()
     File(dir, meta.name).writeBytes(pcm)
     File(dir, metaName(meta.name)).writeText(json.encodeToString(RecordingMeta.serializer(), meta))
+    if (prune) pruneNow()
+  }
+
+  /** Leaves only the newest [keep] recordings. */
+  suspend fun prune() = change { pruneNow() }
+
+  private fun pruneNow() {
     // A JSON that cannot be read would hold a slot without ever being listed.
     dir.listFiles { file -> file.name.endsWith(".json") }?.filter { parse(it) == null }?.forEach { it.delete() }
     recordingsToDelete(dir.list()?.toList() ?: emptyList(), keep).forEach { File(dir, it).delete() }
@@ -103,8 +114,13 @@ class RecordingKeeper(
   private val scope: CoroutineScope,
   private val logError: (String, Throwable) -> Unit,
 ) : RecordingSink {
+  // Kept before its POST: the older recordings are pruned only once it is known to stay (kept).
   override fun saved(meta: RecordingMeta, pcm: ByteArray) {
-    scope.launch { guard("save") { store.save(meta, pcm) } }
+    scope.launch { guard("save") { store.save(meta, pcm, prune = false) } }
+  }
+
+  override fun kept() {
+    scope.launch { guard("prune") { store.prune() } }
   }
 
   override fun transcribed(name: String, transcript: String) {
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests 'com.touringproject.v2.ask.*' --tests 'com.touringproject.v2.recordings.*'`
Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskController.kt app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/recordings/RecordingStore.kt app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/recordings/RecordingStoreTest.kt
cd $AND && git commit -m "fix: prune the older recordings only once an ask's recording is known to stay (Fixes #80)"
```

---

### Task 4: SC-22 が集める点を、新しい `HEADING_POINTS` 点までにする（#83）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/location/Heading.kt`・`location/HeadingCheck.kt`・`ride/RouteHeading.kt`
- Test: `app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt`

**Interfaces:**
- Produces: `com.touringproject.v2.location.HEADING_POINTS`（120。`ride` から移す）。

- [ ] **Step 1: 失敗するテストを書く**

テストは `location` のパッケージから `HEADING_POINTS` を読む。今は `ride` にあるので、Step 2 で落ちることを見るあいだだけ、テストの先頭に `import com.touringproject.v2.ride.HEADING_POINTS` を足す（Step 3 の前に消す）。

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt b/app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt
index 45898fa..cee8342 100644
--- a/app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt
+++ b/app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt
@@ -148,6 +148,24 @@ class HeadingCheckTest {
     assertTrue(w.views.last().result is HeadingResult.Found)
   }
 
+  // Android #83: only the newest HEADING_POINTS points gathered are kept, as a ride's route reads no more. A point 30 m
+  // back, then points at a stop: the reference is found while it is among the newest, and gone once it is not.
+  @Test
+  fun only_the_newest_points_gathered_are_kept() = runTest {
+    fun TestScope.after(atStop: Int): HeadingResult {
+      val w = World()
+      open(w)
+      w.elapsed += 200_000
+      w.onRoute!!(w.fix(-30.0, ageMs = 150_000))
+      (atStop downTo 1).forEach { w.onRoute!!(w.fix(0.0, ageMs = it * 1_000L)) }
+      w.onPosition!!(w.fix(0.0))
+      w.tick(this)
+      return w.views.last().result
+    }
+    assertTrue(after(HEADING_POINTS - 1) is HeadingResult.Found)
+    assertEquals(HeadingResult.None(NoHeading.NOT_MOVED), after(HEADING_POINTS))
+  }
+
   @Test
   fun leaving_removes_both_watches() = runTest {
     val w = World()
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*HeadingCheckTest'`
Expected: `only_the_newest_points_gathered_are_kept` が、2つ目の確かめ（`None(NOT_MOVED)` のはずが `Found`）で落ちる。そのあと、Step 1 で足した import を消す。

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/location/Heading.kt b/app/src/main/java/com/touringproject/v2/location/Heading.kt
index 313494b..cf08bfe 100644
--- a/app/src/main/java/com/touringproject/v2/location/Heading.kt
+++ b/app/src/main/java/com/touringproject/v2/location/Heading.kt
@@ -31,6 +31,13 @@ data class HeadingParams(
   val holdMinutes: Int = DEFAULT_HEADING_HOLD_MINUTES,
 )
 
+/**
+ * How many of the route's last points the heading is worked out from (a ride's segment, or what SC-22 gathers). Points
+ * are 10 m apart at least, so a reference 30 m back is a few points away; the rest only covers points jittering at a
+ * stop.
+ */
+const val HEADING_POINTS = 120
+
 /** Why there is no heading (SC-22 tells the rider). */
 enum class NoHeading { NO_POSITION, POOR_ACCURACY, NOT_MOVED, HELD_TOO_LONG }
 
diff --git a/app/src/main/java/com/touringproject/v2/location/HeadingCheck.kt b/app/src/main/java/com/touringproject/v2/location/HeadingCheck.kt
index 5112df2..62264a6 100644
--- a/app/src/main/java/com/touringproject/v2/location/HeadingCheck.kt
+++ b/app/src/main/java/com/touringproject/v2/location/HeadingCheck.kt
@@ -16,8 +16,8 @@ data class HeadingView(val result: HeadingResult, val here: Fix?, val fromRide:
  * SC-22's heading, worked out as an ask's is (findHeading), every HEADING_CHECK_TICK_MS while run() runs. The current
  * position is the newest fresh fix of a 1 s watch, as an ask's recording takes it. While a ride records, the material is
  * its route (rideHeading, which is RouteHeading). Otherwise (no ride, or a paused one, whose route is not watched) the
- * points are gathered here, asked for and sifted as a ride's route is (acceptRoutePoint, isSince), and kept only in
- * memory; they are dropped when a ride starts recording, when one stops (gathering starts again) and when run() ends.
+ * points are gathered here, asked for and sifted as a ride's route is (acceptRoutePoint, isSince), and the newest
+ * HEADING_POINTS kept only in memory; they are dropped when a ride starts recording, when one stops (gathering starts again) and when run() ends.
  * Cancelling run() removes both watches; a recording ride's own route watch is the service's and goes on.
  */
 class HeadingCheck(
@@ -76,7 +76,11 @@ class HeadingCheck(
     return runCatching {
       route.watch { fix ->
         synchronized(lock) {
-          if (gen == gathering && acceptRoutePoint(fix) && fix.isSince(since, sinceClock)) points += fix
+          if (gen == gathering && acceptRoutePoint(fix) && fix.isSince(since, sinceClock)) {
+            points += fix
+            // As many as a ride's route is read for, the newest (Android #83).
+            if (points.size > HEADING_POINTS) points.removeAt(0)
+          }
         }
       }
     }.getOrNull()
diff --git a/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt b/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt
index 2ead9ce..6f02184 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt
@@ -1,17 +1,12 @@
 package com.touringproject.v2.ride
 
 import com.touringproject.v2.location.Fix
+import com.touringproject.v2.location.HEADING_POINTS
 import com.touringproject.v2.location.HeadingParams
 import com.touringproject.v2.location.HeadingResult
 import com.touringproject.v2.location.findHeading
 import kotlinx.coroutines.CancellationException
 
-/**
- * How many of the segment's last points are read. Points are 10 m apart at least, so a reference 30 m back is a few
- * points away; the rest only covers points jittering at a stop.
- */
-const val HEADING_POINTS = 120
-
 /**
  * The heading of the ride recording or paused (slice 5 spec §4.1): from the points of its last segment only, since a
  * ride may resume far from where it paused (a ferry). Asks, unreached asks and point memos all go through here, so
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && grep -rn 'ride.HEADING_POINTS' app/src; ./gradlew testDebugUnitTest --rerun --tests 'com.touringproject.v2.location.*' --tests 'com.touringproject.v2.ride.*'`
Expected: grep は何も出さず、`BUILD SUCCESSFUL`

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/location/HeadingCheck.kt app/src/main/java/com/touringproject/v2/location/Heading.kt app/src/main/java/com/touringproject/v2/ride/RouteHeading.kt app/src/test/java/com/touringproject/v2/location/HeadingCheckTest.kt
cd $AND && git commit -m "fix: keep only the newest points SC-22 gathers, as many as a ride's route is read for (Fixes #83)"
```

---

### Task 5: 起動時に、端末の最後の位置から位置の時刻を覚える（#84）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/location/GpsClock.kt`・`AppGraph.kt`
- Test: `app/src/test/java/com/touringproject/v2/location/GpsClockTest.kt`

**Interfaces:**
- Produces: `GpsClock.learnFrom(positions: PositionSource)`。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/location/GpsClockTest.kt b/app/src/test/java/com/touringproject/v2/location/GpsClockTest.kt
index 3c59369..5a9da47 100644
--- a/app/src/test/java/com/touringproject/v2/location/GpsClockTest.kt
+++ b/app/src/test/java/com/touringproject/v2/location/GpsClockTest.kt
@@ -41,4 +41,20 @@ class GpsClockTest {
     positions.lastKnown { got += it }
     assertEquals(3_000_000L, gps.now())
   }
+
+  // Android #84: the last known fix teaches the clock before any watch, so a process made again while a ride is paused
+  // tells a point's age on the fixes' time; without the permission the device's clock stands in, and nothing breaks.
+  @Test
+  fun the_last_known_fix_teaches_the_clock_before_any_watch() {
+    fun positions(lastKnown: ((Fix) -> Unit) -> Unit) = object : PositionSource {
+      override fun now() = clock
+      override fun elapsed() = elapsed
+      override fun lastKnown(onFix: (Fix) -> Unit) = lastKnown(onFix)
+      override fun watch(onFix: (Fix) -> Unit) = Subscription {}
+    }
+    gps.learnFrom(positions { throw SecurityException("no permission") })
+    assertEquals(clock, gps.now())
+    gps.learnFrom(positions { onFix -> onFix(Fix(35.0, 139.0, 1_000_000, 5.0, elapsedMs = 9_000)) })
+    assertEquals(1_001_000L, gps.now())
+  }
 }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*GpsClockTest'`
Expected: コンパイルで落ちる（`learnFrom` が無い）。

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index 2a85cda..f052537 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -118,7 +118,7 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   val gpsClock = GpsClock(SystemClock::elapsedRealtime, System::currentTimeMillis)
   val routeSource: RouteSource = FusedRouteSource(context).seenBy(gpsClock)
   /** The 1 s positions of an ask's recording and of SC-22. */
-  val positionSource: PositionSource = FusedPositionSource(context).seenBy(gpsClock)
+  val positionSource: PositionSource = FusedPositionSource(context).seenBy(gpsClock).also { gpsClock.learnFrom(it) }
   private val database = RideDatabase.open(context)
   val rideStore = RoomRideStore(database.rides())
   // sync is made below; it is read only when an unreached ask has been written.
diff --git a/app/src/main/java/com/touringproject/v2/location/GpsClock.kt b/app/src/main/java/com/touringproject/v2/location/GpsClock.kt
index 0fba1c4..4fd26c1 100644
--- a/app/src/main/java/com/touringproject/v2/location/GpsClock.kt
+++ b/app/src/main/java/com/touringproject/v2/location/GpsClock.kt
@@ -14,6 +14,14 @@ class GpsClock(private val elapsed: () -> Long, private val clock: () -> Long) {
   }
 
   fun now(): Long = offset?.let { elapsed() + it } ?: clock()
+
+  /**
+   * Learns from positions' last known fix, so a process that has not had a fix yet (made again while a ride is paused,
+   * whose route is not watched) tells ages on the fixes' time (Android #84). Without the permission nothing is learnt.
+   */
+  fun learnFrom(positions: PositionSource) {
+    runCatching { positions.lastKnown(::seen) }
+  }
 }
 
 /** The same route, each fix shown to clock on the way. */
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*GpsClockTest' --tests '*AppUiTest' --tests '*MainActivityTest'`
Expected: `BUILD SUCCESSFUL`（`AppGraph` を組むテストも、Robolectric の Fused で落ちない）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/location/GpsClock.kt app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/test/java/com/touringproject/v2/location/GpsClockTest.kt
cd $AND && git commit -m "fix: learn the fixes' time from the last known fix when the app starts, before any watch (Fixes #84)"
```

---

### Task 6: SC-22 の基準の点の古さを0に揃える（#86）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt`

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt
index 4f7afaa..5613f6e 100644
--- a/app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt
@@ -48,6 +48,14 @@ class HeadingLabelsTest {
     assertEquals("位置の精度 6m · 基準の点 18m 手前（30秒前）", recent.detail)
   }
 
+  // Android #86: a reference point a moment after the present (each fix's time stands a little differently to the time
+  // since boot) is 0 seconds old, never less.
+  @Test
+  fun a_reference_after_the_present_is_0_seconds_old() {
+    val ui = headingCheckUi(HeadingView(HeadingResult.Found(0.0, reference, 15.0), here, true, -1_500), HeadingParams())
+    assertEquals("位置の精度 6m · 基準の点 15m 手前（0秒前）", ui.detail)
+  }
+
   @Test
   fun degrees_that_round_to_360_are_0_and_an_unknown_accuracy_says_so() {
     val ui = headingCheckUi(HeadingView(HeadingResult.Found(359.7, reference, 15.0), here.copy(accuracy = null), false, 5_000), HeadingParams())
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*HeadingLabelsTest'`
Expected: `a_reference_after_the_present_is_0_seconds_old` が「0秒前」のはずが「-1秒前」で落ちる。

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt b/app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt
index 10cec6f..50aece9 100644
--- a/app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt
@@ -35,7 +35,8 @@ fun headingCheckUi(view: HeadingView, params: HeadingParams): HeadingCheckUi {
   return when (val result = view.result) {
     is HeadingResult.Found -> {
       val degrees = result.degrees
-      val age = view.referenceAgeMs ?: 0
+      // A reference a moment after the present (each fix's time stands a little differently) is new (Android #86).
+      val age = (view.referenceAgeMs ?: 0).coerceAtLeast(0)
       val held = if (age > HELD_AFTER_MS) "。止まる直前の向きを保っています" else ""
       HeadingCheckUi(
         title = "${compass16(degrees)}へ（${degrees.roundToInt() % 360}°）",
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*HeadingLabelsTest'`
Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/HeadingLabels.kt app/src/test/java/com/touringproject/v2/ui/HeadingLabelsTest.kt
cd $AND && git commit -m "fix: tell a reference point a moment after the present as 0 seconds old on SC-22 (Fixes #86)"
```

---

### Task 7: SC-22 を離れると監視が外れることを、画面の水準で確かめる（#85）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/AppGraph.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt`

**Interfaces:**
- Produces: `AppGraph.headingCheck: () -> HeadingCheck`（`var`。呼び出し側の `graph.headingCheck()` は変えない）。

- [ ] **Step 1: 失敗するテストを書く**

最初の数え上げの前に `headingTitle` を待つ（画面が組み上がる前に監視の数だけを待つと、時間切れになる）。

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
index 8cbf575..c18b4d2 100644
--- a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
@@ -8,10 +8,19 @@ import androidx.compose.ui.test.onNodeWithText
 import androidx.compose.ui.test.performClick
 import androidx.compose.ui.test.performScrollTo
 import androidx.compose.ui.test.performTextInput
+import androidx.lifecycle.Lifecycle
 import androidx.test.ext.junit.runners.AndroidJUnit4
 import com.touringproject.v2.MainActivity
 import com.touringproject.v2.TouringApp
 import com.touringproject.v2.ask.TextAskOutcome
+import com.touringproject.v2.location.Fix
+import com.touringproject.v2.location.HeadingCheck
+import com.touringproject.v2.location.HeadingParams
+import com.touringproject.v2.location.HeadingResult
+import com.touringproject.v2.location.NoHeading
+import com.touringproject.v2.location.PositionSource
+import com.touringproject.v2.location.RouteSource
+import com.touringproject.v2.location.Subscription
 import com.touringproject.v2.ride.EndReason
 import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.end
@@ -89,6 +98,41 @@ class AppUiTest {
     assertEquals("既定値に戻しました", ShadowToast.getTextOfLatestToast())
   }
 
+  // Android #85: SC-22's watches run only while it shows: another tab, or the app going to the back, removes both.
+  @Test
+  fun leaving_the_heading_check_removes_its_watches() {
+    val graph = (rule.activity.application as TouringApp).graph
+    var watches = 0
+    var removed = 0
+    val positions = object : PositionSource {
+      override fun now() = 0L
+      override fun elapsed() = 0L
+      override fun lastKnown(onFix: (Fix) -> Unit) = Unit
+      override fun watch(onFix: (Fix) -> Unit): Subscription {
+        watches += 1
+        return Subscription { removed += 1 }
+      }
+    }
+    val route = RouteSource {
+      watches += 1
+      Subscription { removed += 1 }
+    }
+    graph.headingCheck = {
+      HeadingCheck(positions, route, { false }, { HeadingResult.None(NoHeading.NO_POSITION) }, { HeadingParams() }, { 0L })
+    }
+    rule.onNodeWithTag("tab-SETTINGS").performClick()
+    rule.onNodeWithText("位置と方位の確認").performScrollTo().performClick()
+    rule.waitUntil(5_000) { rule.onAllNodesWithTagExists("headingTitle") }
+    rule.waitUntil(5_000) { watches == 2 }
+    rule.onNodeWithTag("tab-HOME").performClick()
+    rule.waitUntil(5_000) { removed == 2 }
+    // Back on the settings tab, SC-22 shows again and watches again; the app going to the back removes them.
+    rule.onNodeWithTag("tab-SETTINGS").performClick()
+    rule.waitUntil(5_000) { watches == 4 }
+    rule.activityRule.scenario.moveToState(Lifecycle.State.CREATED)
+    rule.waitUntil(5_000) { removed == 4 }
+  }
+
   @Test
   fun the_records_tab_lists_the_kept_rides_and_home_keeps_its_place() {
     val graph = (rule.activity.application as TouringApp).graph
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*AppUiTest'`
Expected: コンパイルで落ちる（`headingCheck` は関数なので代入できない）。

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index f052537..b09a5e2 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -201,16 +201,18 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
 
   /**
    * SC-22's heading, a new one each time the screen shows (slice 5 spec §4.5): the ride's route while it records, and
-   * points gathered the same way otherwise.
+   * points gathered the same way otherwise. A test puts one on fake sources here, to count the watches (Android #85).
    */
-  fun headingCheck() = HeadingCheck(
-    positionSource,
-    routeSource,
-    recording = { rides.active.value?.status == RideStatus.RECORDING },
-    rideHeading = routeHeading::find,
-    params = { settings.settings.value?.headingParams ?: HeadingParams() },
-    gpsNow = gpsClock::now,
-  )
+  var headingCheck: () -> HeadingCheck = {
+    HeadingCheck(
+      positionSource,
+      routeSource,
+      recording = { rides.active.value?.status == RideStatus.RECORDING },
+      rideHeading = routeHeading::find,
+      params = { settings.settings.value?.headingParams ?: HeadingParams() },
+      gpsNow = gpsClock::now,
+    )
+  }
 
   /** SC-19 writes point memos through here; each change is something new to send (slice 3 spec §5.1). */
   val notes = RoomNotes(
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*AppUiTest'`
Expected: `BUILD SUCCESSFUL`。このテストは今の振る舞いを押さえるもの（指摘は「今は起きていない」）。入口（`ui/AppUi.kt` の `entry<HeadingCheckKey>`）の `repeatOnLifecycle` を外すと落ちることを、計画を書くときに確かめてある。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
cd $AND && git commit -m "test: check that leaving SC-22, by another tab or to the back, removes both of its watches (Fixes #85)"
```

---

### Task 8: 名前を戻す処理を取り消しで止めず、戻せなければ実際を出す（#88）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/sync/Takeover.kt`・`ui/SavingLabels.kt`
- Test: `app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt`・`ui/SavingLabelsTest.kt`

**Interfaces:**
- Produces: `TakeResult.Mismatched`（`data object`）。`switchMessage(Mismatched)` は「ユーザー名は変わりましたが、記録を入れられませんでした。端末の記録は前の名前のままです」、`rereadMessage(Mismatched)` は「読み込めませんでした」。
- テストの作り物: `Cloud(scope, runIn = scope)`（読み込みを回す scope を分けて取り消せる）・`takeGate`・`save` は DataStore と同じく取り消された中で投げる（`ensureActive`）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
index 96ad545..4cc7c8f 100644
--- a/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
+++ b/app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt
@@ -8,6 +8,10 @@ import com.touringproject.v2.api.CloudRecord
 import com.touringproject.v2.api.RecordsApi
 import com.touringproject.v2.ride.RoutePoint
 import kotlinx.coroutines.CompletableDeferred
+import kotlinx.coroutines.CoroutineScope
+import kotlinx.coroutines.Job
+import kotlinx.coroutines.currentCoroutineContext
+import kotlinx.coroutines.ensureActive
 import kotlinx.coroutines.launch
 import kotlinx.coroutines.test.TestScope
 import kotlinx.coroutines.test.runCurrent
@@ -42,7 +46,8 @@ private val nothingToSend = object : SyncStore {
   override suspend fun unreachedRefused(askId: String, updatedAt: Long) = Unit
 }
 
-private class Cloud(val scope: TestScope) {
+/** runIn is where a read runs: a test cancels it apart from the test's own scope. */
+private class Cloud(val scope: TestScope, val runIn: CoroutineScope = scope) {
   /** Pages by user name, then by cursor (null for the first). */
   val pages = mutableMapOf<String, Map<String?, CloudPage>>()
   val reads = mutableListOf<String>()
@@ -52,6 +57,8 @@ private class Cloud(val scope: TestScope) {
   val taken = mutableListOf<Pair<List<CloudRecord>, Boolean>>()
   var takes: TakeResult = TakeResult.Done(2)
   var failTake = false
+  /** When set, a take waits for it. */
+  var takeGate: CompletableDeferred<Unit>? = null
   /** The user names saved, in order; a name in failSave cannot be saved. */
   val saved = mutableListOf<String>()
   var failSave = setOf<String>()
@@ -60,17 +67,21 @@ private class Cloud(val scope: TestScope) {
 
   val store = object : TakeoverStore {
     override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): TakeResult {
+      takeGate?.await()
       if (failTake) throw IOException("disk full")
       taken += cloud to replace
       return takes
     }
   }
 
-  /** SC-18's change from rider01. */
+  /** SC-18's change from rider01. A save, as DataStore's, throws when its coroutine has been cancelled. */
   fun switch(peek: Peek) = takeover.switchTo(
     peek,
     from = "rider01",
-    save = { if (it in failSave) throw IOException("disk full") else saved += it },
+    save = {
+      currentCoroutineContext().ensureActive()
+      if (it in failSave) throw IOException("disk full") else saved += it
+    },
     switched = { switched += 1 },
   )
 
@@ -85,7 +96,7 @@ private class Cloud(val scope: TestScope) {
 
   var hasKey = true
   val sync = RideSync(nothingToSend, { passes += 1; null }) { _, _ -> }
-  val takeover = Takeover({ if (hasKey) api(it) else null }, store, sync, { 1_000L }, scope) { _, _ -> }
+  val takeover = Takeover({ if (hasKey) api(it) else null }, store, sync, { 1_000L }, runIn) { _, _ -> }
 }
 
 class TakeoverTest {
@@ -173,6 +184,39 @@ class TakeoverTest {
     assertEquals(TakeResult.Failed, c.takeover.state.value.result)
   }
 
+  // Android #88: a read cancelled while the records go in still puts the name back, so the two never part.
+  @Test
+  fun a_switch_cancelled_while_the_records_go_in_still_puts_the_name_back() = runTest {
+    val reads = Job()
+    val c = Cloud(this, runIn = CoroutineScope(coroutineContext + reads))
+    c.pages["taro01"] = mapOf(null to CloudPage(emptyList(), null))
+    c.takes = TakeResult.Blocked(BlockReason.UNSENT)
+    c.takeGate = CompletableDeferred()
+    c.switch(c.takeover.peek("taro01")!!)
+    runCurrent()
+    reads.cancel()
+    c.takeGate!!.complete(Unit)
+    runCurrent()
+    assertEquals(listOf("taro01", "rider01"), c.saved)
+  }
+
+  // Android #88: a name that cannot be put back is told as it is: the new name is saved, the records are the old one's.
+  @Test
+  fun a_name_that_cannot_be_put_back_is_told_as_mismatched() = runTest {
+    for (failTake in listOf(false, true)) {
+      val c = Cloud(this)
+      c.pages["taro01"] = mapOf(null to CloudPage(emptyList(), null))
+      c.takes = TakeResult.Blocked(BlockReason.UNSENT)
+      c.failTake = failTake
+      c.failSave = setOf("rider01")
+      c.switch(c.takeover.peek("taro01")!!)
+      runCurrent()
+      assertEquals(listOf("taro01"), c.saved)
+      assertEquals(0, c.switched)
+      assertEquals(TakeResult.Mismatched, c.takeover.state.value.result)
+    }
+  }
+
   @Test
   fun a_reread_merges_the_current_names_records() = runTest {
     val c = Cloud(this)
diff --git a/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt b/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
index eda1de1..14d5de3 100644
--- a/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
@@ -49,5 +49,7 @@ class SavingLabelsTest {
     assertEquals("走行を終えてから変えられます", switchMessage(TakeResult.Blocked(BlockReason.RIDE)))
     assertEquals("未送信の記録があるため、変えられませんでした", switchMessage(TakeResult.Blocked(BlockReason.UNSENT)))
     assertEquals("読み込めませんでした。ユーザー名は変えていません", switchMessage(TakeResult.Failed))
+    // Android #88: the name could not be put back, so SC-18 tells what is so.
+    assertEquals("ユーザー名は変わりましたが、記録を入れられませんでした。端末の記録は前の名前のままです", switchMessage(TakeResult.Mismatched))
   }
 }
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TakeoverTest' --tests '*SavingLabelsTest'`
Expected: コンパイルで落ちる（`Mismatched` が無い）。計画を書くときに、`NonCancellable` だけを外した実装で `a_switch_cancelled_while_the_records_go_in_still_puts_the_name_back` が落ちる（`saved` が `[taro01]` のまま）ことも確かめてある。

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
index c08e4fc..089537b 100644
--- a/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
+++ b/app/src/main/java/com/touringproject/v2/sync/Takeover.kt
@@ -5,11 +5,13 @@ import com.touringproject.v2.api.CloudRecord
 import com.touringproject.v2.api.RecordsApi
 import kotlinx.coroutines.CancellationException
 import kotlinx.coroutines.CoroutineScope
+import kotlinx.coroutines.NonCancellable
 import kotlinx.coroutines.flow.MutableStateFlow
 import kotlinx.coroutines.flow.StateFlow
 import kotlinx.coroutines.flow.asStateFlow
 import kotlinx.coroutines.flow.update
 import kotlinx.coroutines.launch
+import kotlinx.coroutines.withContext
 
 // Reading the user's records back from the cloud (slice 4 spec §6, adr/0010): when the user name changes, and when SC-14
 // reads them again.
@@ -43,6 +45,12 @@ sealed interface TakeResult {
 
   /** Nothing changed: the cloud could not be read whole, or what it said could not be written. */
   data object Failed : TakeResult
+
+  /**
+   * A change of user name whose records did not come in, and whose name could not be put back: the saved name is the
+   * new one, the device's records the old name's (Android #88).
+   */
+  data object Mismatched : TakeResult
 }
 
 enum class TakeOp { SWITCH, REREAD }
@@ -90,38 +98,35 @@ class Takeover(
   /**
    * SC-18 after DL-03: the device's records go and the name's come in (§6.4). The name and the records cannot be
    * written in one transaction, so the name is saved first (save throws when it cannot be) and put back to from when
-   * the records do not come in; nothing changes when the read, the name or the write fails (Android #72). No pass of
-   * the sync runs meanwhile, so nothing goes out under the new name before its records are in. switched follows a
-   * change that is done.
+   * the records do not come in; nothing changes when the read, the name or the write fails (Android #72). From the
+   * name saved to the name put back, a cancel does not stop it, and a name that cannot be put back is Mismatched
+   * (Android #88). No pass of the sync runs meanwhile, so nothing goes out under the new name before its records are
+   * in. switched follows a change that is done.
    */
   fun switchTo(peek: Peek, from: String, save: suspend (userName: String) -> Unit, switched: suspend () -> Unit) =
     start(TakeOp.SWITCH) {
       val records = readAll(peek.userName, peek.first)
-      save(peek.userName)
-      val result = try {
-        store.take(records, replace = true, now())
-      } catch (e: Exception) {
-        putBack(from, save)
-        throw e
-      }
-      if (result !is TakeResult.Done) {
-        putBack(from, save)
-        return@start result
+      withContext(NonCancellable) {
+        save(peek.userName)
+        val result = try {
+          store.take(records, replace = true, now())
+        } catch (e: Exception) {
+          if (!putBack(from, save)) return@withContext TakeResult.Mismatched
+          throw e
+        }
+        if (result !is TakeResult.Done) return@withContext if (putBack(from, save)) result else TakeResult.Mismatched
+        switched()
+        result
       }
-      switched()
-      result
     }
 
-  // A name that cannot be put back is logged: the records are the old name's, the saved name the new one.
-  private suspend fun putBack(from: String, save: suspend (userName: String) -> Unit) {
-    try {
-      save(from)
-    } catch (e: CancellationException) {
-      throw e
-    } catch (e: Exception) {
-      log("takeover_failed", mapOf("op" to "put_back", "error" to e.toString()))
-      throw e
-    }
+  // False when the name cannot be put back (logged): the records are the old name's, the saved name the new one.
+  private suspend fun putBack(from: String, save: suspend (userName: String) -> Unit): Boolean = try {
+    save(from)
+    true
+  } catch (e: Exception) {
+    log("takeover_failed", mapOf("op" to "put_back", "error" to e.toString()))
+    false
   }
 
   /** SC-14's クラウドから読み直す: the current name's records, merged with the device's. */
diff --git a/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt b/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
index cfe74b0..aeb781c 100644
--- a/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt
@@ -40,7 +40,8 @@ fun rereadMessage(result: TakeResult): String = when (result) {
   is TakeResult.Done -> if (result.count == 0) "新しい記録はありませんでした" else "${result.count}件の記録を読み込みました"
   // Reading again is held back by a ride only.
   is TakeResult.Blocked -> "走行を終えてから読み直せます"
-  TakeResult.Failed -> "読み込めませんでした"
+  // A read again changes no name, so it never comes to Mismatched.
+  TakeResult.Failed, TakeResult.Mismatched -> "読み込めませんでした"
 }
 
 /** SC-18 after DL-03. */
@@ -51,4 +52,5 @@ fun switchMessage(result: TakeResult): String = when (result) {
     BlockReason.UNSENT -> "未送信の記録があるため、変えられませんでした"
   }
   TakeResult.Failed -> "読み込めませんでした。ユーザー名は変えていません"
+  TakeResult.Mismatched -> "ユーザー名は変わりましたが、記録を入れられませんでした。端末の記録は前の名前のままです"
 }
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests 'com.touringproject.v2.sync.*' --tests '*SavingLabelsTest' --tests '*ScreensTest'`
Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/sync/Takeover.kt app/src/main/java/com/touringproject/v2/ui/SavingLabels.kt app/src/test/java/com/touringproject/v2/sync/TakeoverTest.kt app/src/test/java/com/touringproject/v2/ui/SavingLabelsTest.kt
cd $AND && git commit -m "fix: put a user name back even when its read is cancelled, and tell SC-18 when it cannot be put back (Fixes #88)"
```

---

### Task 9: 走行の書き直し待ちの印を、書き込みが失敗したあとだけ立てる（#89）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ride/RideController.kt`
- Test: `app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt`

- [ ] **Step 1: 失敗するテストを書く**

保存を `gate` で止めているあいだの値は、門を開ける前に読んでおく（確かめが落ちたまま門を開けないと、`NonCancellable` の中の保存が待ち続け、テストが Gradle の時間切れ（5分）まで止まる）。

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
index 8e3865c..8c9e28f 100644
--- a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
@@ -399,6 +399,24 @@ class RideControllerTest {
     assertFalse(w.controller.storeFailed.value)
   }
 
+  // Android #89: a save under way is not a change waiting to be written again, so SC-18 is not held back while it writes.
+  @Test
+  fun a_save_under_way_is_not_told_as_waiting() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.gate = CompletableDeferred()
+    val pausing = launch { w.controller.pause() }
+    runCurrent()
+    // Read before the save is let go, so a failing check does not leave it waiting for ever.
+    val whileWriting = w.controller.waitingToSave.value
+    w.gate!!.complete(Unit)
+    pausing.join()
+    assertFalse(whileWriting)
+    assertFalse(w.controller.waitingToSave.value)
+    assertEquals(RideStatus.PAUSED, w.stored().status)
+  }
+
   // A rename of an ended ride that could not be written waits with no ride running to write it again; SC-18 tries it
   // again when it opens, so a change of user name is not held back for good (plan 5's final review).
   @Test
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*RideControllerTest'`
Expected: `a_save_under_way_is_not_told_as_waiting` が `assertFalse(whileWriting)` で落ちる。

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ride/RideController.kt b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
index 1a9cc0a..6ec0718 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RideController.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
@@ -43,12 +43,9 @@ class RideController(private val deps: RideDeps) {
    * failed leaves nothing waiting; SC-18 holds back a change of user name only for this.
    */
   val waitingToSave: StateFlow<Boolean> = waiting.asStateFlow()
-  // A ride whose save failed; it is written again first by every later call.
+  // A ride whose save failed; it is written again first by every later call. waitingToSave follows it once a write is
+  // over (told()), so a save that goes through is never seen as waiting while it writes (Android #89).
   private var unsaved: Ride? = null
-    set(value) {
-      field = value
-      waiting.value = value != null
-    }
   // False until the ride left over from before this process has been read; until then no new ride may start.
   private var reconciled = false
 
@@ -119,6 +116,10 @@ class RideController(private val deps: RideDeps) {
     storeFailing.value = true
   }
 
+  private fun told() {
+    waiting.value = unsaved != null
+  }
+
   /** False when the write failed: the ride stays unsaved and the next call writes it again first. */
   private suspend fun save(ride: Ride): Boolean {
     unsaved = ride
@@ -126,6 +127,7 @@ class RideController(private val deps: RideDeps) {
       deps.store.save(ride)
       unsaved = null
     }
+    told()
     if (saved) deps.changed()
     return saved
   }
@@ -272,6 +274,7 @@ class RideController(private val deps: RideDeps) {
   private fun dropUnsavedMemo(waiting: Ride?) {
     unsaved = waiting
     storeFailing.value = unsaved != null
+    told()
   }
 
   /**
@@ -286,6 +289,7 @@ class RideController(private val deps: RideDeps) {
     // Only once the ride is gone: a deletion that failed leaves its waiting change to be written (Android #53).
     if (unsaved?.id == rideId) unsaved = null
     storeFailing.value = unsaved != null
+    told()
     deps.changed()
     true
   }
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests 'com.touringproject.v2.ride.*' --tests 'com.touringproject.v2.store.*'`
Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ride/RideController.kt app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
cd $AND && git commit -m "fix: tell a ride's change as waiting only once its write has failed, not while a save goes through (Fixes #89)"
```

---

### Task 10: 保存の集計を、画面が読まなくなったら捨てる（#90）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/records/Saving.kt`・`AppGraph.kt`
- Create: `app/src/test/java/com/touringproject/v2/records/SavingTest.kt`

**Interfaces:**
- Produces: `fun Flow<SaveSummary>.whileShown(scope: CoroutineScope): StateFlow<SaveSummary?>`（`records/Saving.kt`）。

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/records/SavingTest.kt b/app/src/test/java/com/touringproject/v2/records/SavingTest.kt
new file mode 100644
index 0000000..e3f7c98
--- /dev/null
+++ b/app/src/test/java/com/touringproject/v2/records/SavingTest.kt
@@ -0,0 +1,30 @@
+package com.touringproject.v2.records
+
+import kotlinx.coroutines.flow.MutableStateFlow
+import kotlinx.coroutines.launch
+import kotlinx.coroutines.test.advanceTimeBy
+import kotlinx.coroutines.test.runCurrent
+import kotlinx.coroutines.test.runTest
+import org.junit.Assert.assertEquals
+import org.junit.Assert.assertNull
+import org.junit.Test
+
+class SavingTest {
+  // Android #90: a summary no longer shown starts from nothing again, so coming back to SC-14 or SC-18 never shows an
+  // old count; while it is still shown, or within 5 s of leaving, it stays.
+  @Test
+  fun a_summary_no_longer_shown_starts_from_nothing_again() = runTest {
+    val counted = MutableStateFlow(SaveSummary(unreached = 1))
+    val shared = counted.whileShown(backgroundScope)
+    val shown = backgroundScope.launch { shared.collect {} }
+    runCurrent()
+    assertEquals(SaveSummary(unreached = 1), shared.value)
+    shown.cancel()
+    advanceTimeBy(4_000)
+    runCurrent()
+    assertEquals(SaveSummary(unreached = 1), shared.value)
+    advanceTimeBy(1_001)
+    runCurrent()
+    assertNull(shared.value)
+  }
+}
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SavingTest'`
Expected: コンパイルで落ちる（`whileShown` が無い）。計画を書くときに、`replayExpirationMillis` を付けない `whileShown` では `assertNull` で落ちることも確かめてある。

- [ ] **Step 3: 実装する**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index b09a5e2..3b6a7db 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -47,6 +47,7 @@ import com.touringproject.v2.recordings.TrialState
 import com.touringproject.v2.records.RideListItem
 import com.touringproject.v2.records.SaveSummary
 import com.touringproject.v2.records.activeAskCount
+import com.touringproject.v2.records.whileShown
 import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.RideController
 import com.touringproject.v2.ride.RideDeps
@@ -153,7 +154,7 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   )
 
   /** SC-14 and SC-18: what is left to send, and how much is kept (slice 4 spec §7.1). */
-  val saveSummary: StateFlow<SaveSummary?> = records.summary.stateIn(scope, SharingStarted.WhileSubscribed(5_000), null)
+  val saveSummary: StateFlow<SaveSummary?> = records.summary.whileShown(scope)
 
   /** Reads the user's records in from the cloud: SC-18's change of user name and SC-14's read again (slice 4 spec §6). */
   val takeover = Takeover(
diff --git a/app/src/main/java/com/touringproject/v2/records/Saving.kt b/app/src/main/java/com/touringproject/v2/records/Saving.kt
index 5712447..3433ac0 100644
--- a/app/src/main/java/com/touringproject/v2/records/Saving.kt
+++ b/app/src/main/java/com/touringproject/v2/records/Saving.kt
@@ -1,5 +1,11 @@
 package com.touringproject.v2.records
 
+import kotlinx.coroutines.CoroutineScope
+import kotlinx.coroutines.flow.Flow
+import kotlinx.coroutines.flow.SharingStarted
+import kotlinx.coroutines.flow.StateFlow
+import kotlinx.coroutines.flow.stateIn
+
 /**
  * What SC-14 tells of the device's records (slice 4 spec §7.1). The first five count what the next pass would send:
  * unreached asks, rides (their meta or route), point memos, conversation memos and deletions; a version the Backend
@@ -17,3 +23,10 @@ data class SaveSummary(
 ) {
   val unsent: Int get() = unreached + unsentRides + notes + memos + deletions
 }
+
+/**
+ * SC-14's and SC-18's summary, counted while a screen shows it and for 5 s after; null until it is counted. Once it is
+ * no longer counted it is null again, so a screen coming back never shows an old count (Android #90).
+ */
+fun Flow<SaveSummary>.whileShown(scope: CoroutineScope): StateFlow<SaveSummary?> =
+  stateIn(scope, SharingStarted.WhileSubscribed(5_000, replayExpirationMillis = 0), null)
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*SavingTest' --tests '*AppUiTest'`
Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/records/Saving.kt app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/test/java/com/touringproject/v2/records/SavingTest.kt
cd $AND && git commit -m "fix: start the save summary from nothing again once no screen counts it, so no old count shows (Fixes #90)"
```

---

### Task 11: 重なった import・README・版（#91・#93）

**Files:**
- Modify: `app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt`・`README.md`・`app/build.gradle.kts`

- [ ] **Step 1: 重なった import を消してコミットする（#91）**

```bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
index 8c97caf..c739ca4 100644
--- a/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
@@ -8,7 +8,6 @@ import androidx.compose.ui.test.assertHasNoClickAction
 import androidx.compose.ui.test.assertIsDisplayed
 import androidx.compose.ui.test.assertIsEnabled
 import androidx.compose.ui.test.assertIsNotEnabled
-import androidx.compose.ui.test.assertIsEnabled
 import androidx.compose.ui.test.assertTextEquals
 import androidx.compose.ui.test.junit4.createComposeRule
 import androidx.compose.ui.test.onNodeWithTag
PATCH
```

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*ScreensTest' > /tmp/trv2-t11.log 2>&1; tail -1 /tmp/trv2-t11.log
cd $AND && git add app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt
cd $AND && git commit -m "test: drop the second import of assertIsEnabled in ScreensTest (Fixes #91)"
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 2: README と版を直してコミットする（#93）**

README は、#93 の2点（送信の決まりの重なりを次の行へ寄せる・MapLibre の理由に「テストの仕組みの下では」を足す）と、この plan の直し（文字の質問の取り消し・SC-03 の帯・録音の刈り込み・SC-22 の点の上限とテスト・`learnFrom`・名前を戻す処理と `Mismatched`・書き直し待ちの印・`whileShown`）の説明を足す。

```bash
cd $AND && git apply <<'PATCH'
diff --git a/README.md b/README.md
index dfa55e6..19bb3d5 100644
--- a/README.md
+++ b/README.md
@@ -35,25 +35,24 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 - 走行の `updatedAt` は、状態・名前・区間・メモが変わったときだけ進む。点の追加と生きていた時刻の書き込み（`addPoint`・`markAlive`）では進まない（距離は送らない）。
 - 質問を受けるのは走行の記録中だけ。`AskController.run` の入口で `RideNow`（記録中・一時停止中・記録していない）を見て、記録中でなければ録音を始めず、理由を読み上げる。画面の「押して話す」「文字で質問」も押せない形にする（親の spec 2 §4.7・adr/0008）。受け付けるかどうかは `refusal(RideNow)` だけが決め、司令塔とホームの文言（`askHint`）の両方がこれを使う。
 - 進行方位は端末で求めて度数（`headingDegrees`）で送る（親の adr/0013・spec 5 §4）。材料は、記録中か一時停止中の走行の最後の区間のルートの点（`RouteHeading` が Room の `segmentTail` で新しい120点を読む）。新しい点から遡り、精度が精度の上限以内で今の位置から基準の距離以上離れた最初の点から今の位置への向きにする（`findHeading`）。基準の点が保つ上限より古い・今の位置が無いか精度が悪いときは方位なし。3つのパラメーターは設定（`Settings` の `heading*`）。質問は録音を終えたときの位置、文字の質問は送るときの端末の最後の位置（30秒以内。`Positions.latest`）、地点メモは開いたときの走行の最新の点で求める。スライス5より前に作った未送信の地点メモと質問できなかった地点は、行に残る古い材料（`sample*` の列）を `headingSample` で送る（Backend の #28 で外す）。
-- 位置の時刻（`Location.time`。GNSS の時刻のことがある）は端末の時計とずれうるので、位置がどれだけ古いかは端末の時計で比べない（#17・#24）。`Fix.elapsedMs`（起動からの経過時間）を持たせ、今の位置の30秒の新しさ（`isFresh`）と、走行の区間より前の点を捨てる判定（`isSince`。区間の開始・再開・プロセスが引き継いだときの経過時間と比べる）はそれで比べる。Room の点は経過時間を持たないので、方位の保つ上限は `GpsClock`（受けた位置から、位置の時刻と経過時間の差を覚える）の今と比べる。位置を受ける新しい窓口（`RouteSource`・`PositionSource`）は `seenBy(gpsClock)` で包む（`AppGraph`）。包まないと、その窓口の位置が `GpsClock` に届かず、方位の保つ上限が古い今と比べられる。
-- 位置と方位の確認（SC-22）は `HeadingCheck` が1秒ごとに求める。今の位置は質問の録音と同じ1秒ごとの監視の最新。走行の記録中は `RouteHeading`（質問と同じ）、記録していないとき・一時停止中は、ルートと同じ頼み方とふるい分けで画面を開いてから集めた点（メモリだけ）を材料にする。画面を離れるか、アプリが背面に回ると、監視を止めて集めた点を捨てる（記録中の走行のルートの監視は止めない）。
+- 位置の時刻（`Location.time`。GNSS の時刻のことがある）は端末の時計とずれうるので、位置がどれだけ古いかは端末の時計で比べない（#17・#24）。`Fix.elapsedMs`（起動からの経過時間）を持たせ、今の位置の30秒の新しさ（`isFresh`）と、走行の区間より前の点を捨てる判定（`isSince`。区間の開始・再開・プロセスが引き継いだときの経過時間と比べる）はそれで比べる。Room の点は経過時間を持たないので、方位の保つ上限は `GpsClock`（受けた位置から、位置の時刻と経過時間の差を覚える）の今と比べる。起動時に端末の最後の位置（`lastKnown`）からも覚える（`GpsClock.learnFrom`。一時停止中に作り直されたプロセスは、ルートを監視しないので位置が来ない）。覚えるまでは端末の時計を使う。位置を受ける新しい窓口（`RouteSource`・`PositionSource`）は `seenBy(gpsClock)` で包む（`AppGraph`）。包まないと、その窓口の位置が `GpsClock` に届かず、方位の保つ上限が古い今と比べられる。
+- 位置と方位の確認（SC-22）は `HeadingCheck` が1秒ごとに求める。今の位置は質問の録音と同じ1秒ごとの監視の最新。走行の記録中は `RouteHeading`（質問と同じ）、記録していないとき・一時停止中は、ルートと同じ頼み方とふるい分けで画面を開いてから集めた点（メモリだけ。走行のルートと同じく新しい120点まで）を材料にする。画面を離れるか、アプリが背面に回ると、監視を止めて集めた点を捨てる（記録中の走行のルートの監視は止めない）。止めるのは画面の入口（`repeatOnLifecycle`）で、`AppUiTest` が `AppGraph.headingCheck` を作り物の窓口のものに差し替えて、監視の数で確かめる。
 - 録音の上限と開始の合図は設定（SC-11）の値を、質問の始まりに読む（SC-12 の試し録りも同じ値。SC-19 の声の入力は60秒・1.5秒のまま）。合図「なし」は 0 で、音を鳴らさない。
-- 文字の質問（ホームの「⌨ 文字で質問」のシート）は `AskController.askText` が受け、録音せずに送るところ（SC-03 の「送っています…」）から始まる。Backend が受け付けたらシートを閉じて回答待ちへ進む。通信できないとき（送る前に通信が無い・`POST` が通信の失敗）は、質問できなかった地点を作らず、シートに「通信できません」と出して文を残す。断られたとき（記録中でない・接続キー・Backend の 400 など）は SC-03 に理由を出し、シートに文を残す。シートは SC-03 のあいだ消え、終わると戻る（状態は `AppGraph.textSheet` がプロセスのあいだ持つ。画面を回して Activity が作り直されても、結果がシートに届く）。質問の行の `input` は `text`、質問の文は打った文。
+- 文字の質問（ホームの「⌨ 文字で質問」のシート）は `AskController.askText` が受け、録音せずに送るところ（SC-03 の「送っています…」）から始まる。Backend が受け付けたらシートを閉じて回答待ちへ進む。通信できないとき（送る前に通信が無い・`POST` が通信の失敗）は、質問できなかった地点を作らず、シートに「通信できません」と出して文を残す。断られたとき（記録中でない・接続キー・Backend の 400 など）は SC-03 に理由を出し、シートに文を残す。送っているあいだに取り消すと、シートはすぐ打ち直せる形に戻り、そのあと `POST` が通っても受け付けなかったものとして文を残す（Backend に残った質問は、声の質問と同じく受け入れる）。シートは SC-03 のあいだ消え、終わると戻る（状態は `AppGraph.textSheet` がプロセスのあいだ持つ。画面を回して Activity が作り直されても、結果がシートに届く）。質問の行の `input` は `text`、質問の文は打った文。
 - Room のスキーマを変えるときは、版を上げて Migration を書き、`app/schemas/` に書き出された JSON もコミットする。破壊的な作り直しは使わない。スキーマの JSON は debug のビルドの資産にも入る（Robolectric の `MigrationTestHelper` が読むため。release には入らない）。Entity や Migration を変えた直後のテストは `--rerun` で確かめる。
-- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと・通信できるようになったとき（`reconnections`。プロセスが生きているあいだだけ。`Connectivity.comebacks` が、システムの知らせを受けたところで戻った回数を数えるので、ごく短い切断も取りこぼさない）。契機では未送信を調べるだけで、送るものが無ければ通信しない。通信できないあいだは、契機が来ても通信を試さない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。接続キーとユーザー名の変化（`credentialChanges`）は、設定を読み込んだあとに集め、読み込んだ時点の値は数えない。送信で「断られた」と同じに扱う例外は `SerializationException` だけ（`IllegalArgumentException` は、OkHttp が不正な API の URL で投げるので含めない）。
-- 1回の送信は、削除の印（`deletions`）→ 走行とルート → 地点メモ → 質問できなかった地点 → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため。質問できなかった地点のメモが、Backend で質問を見つけられるため）。記録を消すときは、同じトランザクションで削除の印を書く。送れない削除の印（知らない種類）は、ログ `sync_unsendable` に出して消す（残すと、毎回の送信がそこで止まる）。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`）。
+- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと・通信できるようになったとき（`reconnections`。プロセスが生きているあいだだけ。`Connectivity.comebacks` が、システムの知らせを受けたところで戻った回数を数えるので、ごく短い切断も取りこぼさない）。契機では未送信を調べるだけで、送るものが無ければ通信しない。通信できないあいだは、契機が来ても通信を試さない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。走行のメモはメタ情報の一部として送る。- 1回の送信は、削除の印（`deletions`）→ 走行とルート → 地点メモ → 質問できなかった地点 → 会話のメモの順に送る（消したものの古い版を同じ回で置き直さないため。質問できなかった地点のメモが、Backend で質問を見つけられるため）。記録を消すときは、同じトランザクションで削除の印を書く。送れない削除の印（知らない種類）は、ログ `sync_unsendable` に出して消す（残すと、毎回の送信がそこで止まる）。410（Backend で消されている）は送れたものとして扱い、送り直さない。会話のメモへの 404 は断られたものとして扱う。端末で送る中身を組み立てられない（`SerializationException`）ものは、断られたものと同じに扱って次へ進む（そう扱う例外はこれだけ。`IllegalArgumentException` は、OkHttp が不正な API の URL で投げるので含めない）。断られた理由（Backend の `message`）はログ `sync_refused` に出る。接続キーかユーザー名を保存したときも送る（`credentialChanges`。設定を読み込んだあとに集め、読み込んだ時点の値は数えない）。
 - 地点メモ（SC-19）は、走行の記録中と一時停止中にホームの「📝 地点メモ」から開く。開いたときに、その走行の最後の点を位置に、質問と同じ求め方で方位を決め（`RoomNotes.draft`）、保存するまで書かない。方位は端末の値を `notes.headingDegrees` に書いて送り、住所と Backend が決めた方位は、最初に送ったときの応答で行に書く。地図のピンは緑で、質問とは別の通し番号。質問の一巡が終わったときに、その走行が消えていれば質問は書かない（`AskDao.keep`）。
-- 質問できなかった地点（US-C-09）: 録音を終えた時点で通信できないとき、または `POST /asks` が通信の失敗（試し直しのあとの 5xx・流量の制限を含む）に終わったとき、質問の一巡は日時・位置・方位を `asks` に `status = offline` で残す（識別子は端末で作る。会話の識別子は無い）。録音は `POST` の前に SC-12 へ残し（試し直しのあいだにプロセスが死んでも、受け付けられた質問の録音が残るように）、質問できなかった地点になったら消す。会話の文脈は進めない。接続キーの誤りなど、断られた失敗では残さない。書けたらすぐ送信の契機を呼ぶ（通信の失敗でも、既定のネットワークは残っていることがあるため）。`PUT /asks/{askId}/offline` で送り、応答の住所と方位を行に書く。409（同じ識別子の質問が Backend にある）は断られたものとして扱う。住所を決められずに受け付けられた地点メモと質問できなかった地点は、起動ごとに一度、版を進めて送り直す（Backend は新しい版でだけ住所を求め直す）。
-- クラウドの記録を読み込むのは、SC-18 でユーザー名を変えるときと、SC-14 の「クラウドから読み直す」だけ（親の adr/0010）。`Takeover` が `GET /records` を最後のページまで読んでから、`RoomTakeover` が1つのトランザクションで突き合わせて入れる（`Merge.kt`: `updatedAt` が新しいほうを残す・クラウドの削除の跡で消す・端末の未送信の削除はクラウドの写しを入れない・ルートは点の多いほう・記録中のまま残っていた走行は終えて入れ、送り直す）。入れたものは送り済みの印を付ける。ユーザー名を変えるときは、先に名前を保存し（保存できなければ何も変えない）、端末の記録を消してから入れる。入れられなかった（止まった・失敗した）ら名前を元に戻す（名前の保存と Room は1つのトランザクションにできないため）。読み始めから名前の保存・記録の書き込み・戻すまでは `RideSync.withoutPasses` の中で、送信の回が走らない。走行の記録中・一時停止中は、どちらも行わない。ユーザー名は、未送信（SC-14 が数えるもの。断られた版と記録中の走行は数えない）と、走行の書き直し待ち（`RideController.waitingToSave`）があるあいだも変えられない。書き直し待ちは SC-18 を開いたときに書き直しを試し（`retrySave`）、残れば書き込めていないことを出す（SC-14 へは案内しない）。トランザクションの中でも確かめ直す。止まった理由（走行か未送信か）は `TakeResult.Blocked` が持つ。SC-14・SC-18 は、未送信を数え終えるまで保存の状態を出さず、名前の変更を押せない。
+- 質問できなかった地点（US-C-09）: 録音を終えた時点で通信できないとき、または `POST /asks` が通信の失敗（試し直しのあとの 5xx・流量の制限を含む）に終わったとき、質問の一巡は日時・位置・方位を `asks` に `status = offline` で残す（識別子は端末で作る。会話の識別子は無い）。録音は `POST` の前に SC-12 へ残し（試し直しのあいだにプロセスが死んでも、受け付けられた質問の録音が残るように）、質問できなかった地点になったら消す。直近10件への刈り込みは、録音が残ると分かったとき（受け付けられた・断られた）にだけ行う（`RecordingSink.kept`。消える録音のために古い録音を消さない）。会話の文脈は進めない。接続キーの誤りなど、断られた失敗では残さない。書けたらすぐ送信の契機を呼ぶ（通信の失敗でも、既定のネットワークは残っていることがあるため）。`PUT /asks/{askId}/offline` で送り、応答の住所と方位を行に書く。409（同じ識別子の質問が Backend にある）は断られたものとして扱う。住所を決められずに受け付けられた地点メモと質問できなかった地点は、起動ごとに一度、版を進めて送り直す（Backend は新しい版でだけ住所を求め直す）。
+- クラウドの記録を読み込むのは、SC-18 でユーザー名を変えるときと、SC-14 の「クラウドから読み直す」だけ（親の adr/0010）。`Takeover` が `GET /records` を最後のページまで読んでから、`RoomTakeover` が1つのトランザクションで突き合わせて入れる（`Merge.kt`: `updatedAt` が新しいほうを残す・クラウドの削除の跡で消す・端末の未送信の削除はクラウドの写しを入れない・ルートは点の多いほう・記録中のまま残っていた走行は終えて入れ、送り直す）。入れたものは送り済みの印を付ける。ユーザー名を変えるときは、先に名前を保存し（保存できなければ何も変えない）、端末の記録を消してから入れる。入れられなかった（止まった・失敗した）ら名前を元に戻す（名前の保存と Room は1つのトランザクションにできないため）。名前の保存から戻すまでは、取り消されても止めない（`NonCancellable`）。戻す保存も失敗したら `TakeResult.Mismatched` で、SC-18 は名前が変わって記録が入っていないことを出す。読み始めから名前の保存・記録の書き込み・戻すまでは `RideSync.withoutPasses` の中で、送信の回が走らない。走行の記録中・一時停止中は、どちらも行わない。ユーザー名は、未送信（SC-14 が数えるもの。断られた版と記録中の走行は数えない）と、走行の書き直し待ち（`RideController.waitingToSave`。書き込みが失敗したあとだけ立ち、書いているあいだは立たない）があるあいだも変えられない。書き直し待ちは SC-18 を開いたときに書き直しを試し（`retrySave`）、残れば書き込めていないことを出す（SC-14 へは案内しない）。トランザクションの中でも確かめ直す。止まった理由（走行か未送信か）は `TakeResult.Blocked` が持つ。SC-14・SC-18 は、未送信を数え終えるまで保存の状態を出さず、名前の変更を押せない。数えた値（`AppGraph.saveSummary`）は、どの画面も読まなくなって5秒で捨て、戻ったときは数え直す（`whileShown`。古い数を一瞬出さないため）。
 - SC-19 の声の入力（`VoiceInput`）は、質問とは別の経路の切り替えと録音の部品を持つ（試し録りと同じ）。SC-19 を開いているあいだ（`attach`）は、インカムのボタンが質問を始めず、声の入力を始める・止める（質問が進んでいるときは質問のまま）。録音は60秒まで。`POST /transcriptions` に送り、質問と同じ間隔で `GET` し、120秒で打ち切る。聞き取れた文は入力欄の終わりに足し、2000字に入りきらなかったときは入力欄の下にそう出す。2000字で切るときは、画面の上の1文字（ZWJ でつないだ絵文字・国旗・肌の色）を割らない（`cutMemo`）。文字にしているあいだの押下は、何も始めず失敗の合図を鳴らす。通信できないときは画面のボタンを押せず、インカムのボタンは失敗の合図だけを鳴らす。SC-19 を離れると、録音も文字起こしの待ちも捨てる。前面サービスは使わない（SC-19 を見ながら使う前提）。その下の `AudioRoute` はアプリに1つなので、SC-19 を離れたら待っている処理を取り消してすぐ経路を返し、返しきるまで（音声認識の経路の準備は最大4秒で、取り消せない）は `busy` で、押下の行き先は質問を始めない。`attach` は札を返し、`detach` はその札のときだけ効く（閉じていく画面の後始末が、新しく開いた画面からインカムのボタンを取り上げないように）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
 - インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
 - 回答は音声の焦点（audio focus）を取らずに鳴らす（ナビの案内と重ねる）。
-- MapLibre の呼び出し（スタイル・ソース・カメラ）は UI スレッドだけで行う。`withContext(Dispatchers.Default)` から戻った先は UI スレッドとは限らないので、`RouteMap` は地図に触る処理を `withContext(Dispatchers.Main)` に置く。
+- MapLibre の呼び出し（スタイル・ソース・カメラ）は UI スレッドだけで行う。`withContext(Dispatchers.Default)` から戻った先は（テストの仕組みの下では）UI スレッドとは限らないので、`RouteMap` は地図に触る処理を `withContext(Dispatchers.Main)` に置く。
 - `MainActivity` は `singleTask`。`ActivityScenario` はこれを追えないので、エミュレーターのテストは Activity を直接起動する。
 - 録音の確認（SC-12）は、質問とは別の経路の切り替え・録音・再生を持つ。画面を離れても、読み上げ中の回答は止めない。試し録りはボタンを押した呼び出しの中で録音中になる（`CoroutineStart.UNDISPATCHED`）ので、直後に離れても画面の外で始まらない。「録音をすべて消す」の確認は、質問が始まると閉じる。SC-12 を離れた試し録りが片付くまで（経路の準備で最大3秒）、インカムの押下と「押して話す」は何も始めない（片付けの経路の解放が質問の経路を壊すため）。試し録りは `voice.busy` を見ていない。
-- メディアの音量（SC-02・SC-03 の帯）は `MediaVolumeWatch` がプロセスのあいだ持つ。インカムの通話の経路が残っていて読めない（null）あいだは直前の値を使い、ホームを作り直しても、次の質問でも同じ値になる。✕ で閉じた帯は、違う音量が読めるまで出さない。
-- 録音は `filesDir/recordings/` に `rec-<時刻>.pcm` と `rec-<時刻>.json` の組で直近10件を残す。片方しか無い組と読めない JSON は、次に残すときに消す。
+- メディアの音量（SC-02・SC-03 の帯）は `MediaVolumeWatch` がプロセスのあいだ持つ。SC-03 の帯は、録音中と、文字の質問の送っているあいだと回答待ちに出す（`FlowState.tellsVolume`。回答はメディアの音で読み上げるため。声の質問は録音のあとインカムの経路が音を持つ）。インカムの通話の経路が残っていて読めない（null）あいだは直前の値を使い、ホームを作り直しても、次の質問でも同じ値になる。✕ で閉じた帯は、違う音量が読めるまで出さない。
+- 録音は `filesDir/recordings/` に `rec-<時刻>.pcm` と `rec-<時刻>.json` の組で直近10件を残す（質問の録音は、残ると分かるまでのあいだ11件になりうる）。片方しか無い組と読めない JSON は、刈り込むときに消す。
 
 ## テスト
 
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index cf2757d..8ae395d 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 14
-    versionName = "0.13.0"
+    versionCode = 15
+    versionName = "0.14.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
PATCH
```

```bash
cd $AND && git add README.md app/build.gradle.kts
cd $AND && git commit -m "docs: describe plan 7b's fixes in the README, take the overlap out of the sync rules and narrow MapLibre's reason, and raise the version to 0.14.0 (Fixes #93)"
```

---

### Task 12: 全体の確かめと PROJECT.md

- [ ] **Step 1: `clean` から JVM のテスト・ビルド・権限・エミュレーターのテストのコンパイル**

```bash
cd $AND && ./gradlew clean > /dev/null && ./gradlew testDebugUnitTest assembleDebug assembleRelease compileDebugAndroidTestKotlin > /tmp/trv2-t12.log 2>&1; tail -1 /tmp/trv2-t12.log
cd $AND && ./scripts/check-release-permissions.sh
```

Expected: `BUILD SUCCESSFUL`（JVM 712件）・`release permissions OK (15)`。`RideForegroundServiceTest.the_ask_keep_alive_reaches_the_running_service` だけが落ちたら、そのテストを単独で回して通ることを確かめ、Android #94 にその日の発生を追記する（この plan では直さない）。

- [ ] **Step 2: エミュレーターのテスト**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && ./gradlew connectedDebugAndroidTest > /tmp/trv2-t12e.log 2>&1; tail -1 /tmp/trv2-t12e.log
```

Expected: `BUILD SUCCESSFUL`（`local.properties` に API の URL が無ければ、記録中の質問のテストは飛ばす）。終わったらエミュレーターを止める。

- [ ] **Step 3: PROJECT.md を更新して親でコミットする**

plan 表の 7b を「実装済み（確認待ち: 実機。0.14.0 を入れての走行で、plan 6 の Task 8 と plan 3・4 の残りと一緒に確かめる）」にし、「次にやること」はそのまま（1を消し、2の走行を1にする）。親の submodule の指す先は、Android のブランチの先頭に進める。

```bash
cd $ROOT && git add PROJECT.md Android && git commit -m "docs: record slice 5 plan 7b as implemented, awaiting the device check on 0.14.0"
```

---

### Task 13: 実機で確かめる（利用者と）

走行の前に、停車中にできるものをここで確かめる。走行でしか分からないもの（方位）は、PROJECT.md の「次にやること」の走行で確かめる。

- [ ] **Step 1: 0.14.0 の release を実機に入れる**

```bash
cd $AND && ./gradlew assembleRelease && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
```

Expected: 「設定 → バージョン」が 0.14.0。

- [ ] **Step 2: 利用者に確かめてもらう（走行を記録中にして、停車中に）**

1. メディアの音量を最大の1/3未満にして「⌨ 文字で質問」で送る → SC-03 の「送っています…」と「考えています…」に低い音量の帯が出る（#81）。
2. 機内モードを切ったまま、送った直後に「送らずにやめる」を押す → シートが打った文のまま戻り、すぐ「質問する」を押せる（#79。間に合わなければ、ここは飛ばしてよい。JVM のテストで押さえてある）。
3. 設定 → 位置と方位の確認（SC-22）を開いて別のタブに移る・戻る → 画面が今までどおり出る（#85・#83 の見た目に変わりが無いこと）。

結果は PROJECT.md の 7b の行に書く（✗ が出たら `superpowers:systematic-debugging`）。
