# スライス6 計画1: Android（SC-19 を背面に回すとインカムのボタンが効かない: R3-01） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SC-19（地点メモ）を開いたまま背面に回しても、走行中のインカムのボタンが質問になるようにする（全体レビューの R3-01、High）。版 0.14.1。

**Architecture:** 声の入力を SC-19 に付ける・外すのを、画面の破棄（`DisposableEffect`）から、Activity が前面に出ているあいだ（`RESUMED`。`LifecycleResumeEffect`）に合わせる。変えるのは `RecordsRoutes.kt` の `voiceUi()` の1か所。`PressRouter`・`VoiceInput`・`MainActivity` は変えない。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・lifecycle-runtime-compose 2.10.0（`LifecycleResumeEffect`。足す依存は無い）・Robolectric 4.16（SDK 35）。

**Spec:** [docs/specs/2026-10-29-slice6-design.md](../specs/2026-10-29-slice6-design.md) §2（R3-01 は plan 1 で単独で直す）・§3・§4（再現テストを先に書く）。指摘の本文は [報告 android.md の R3-01](../final-review/2026-10-28/android.md)。

**確かめたこと（spec §4）:** 報告のとおり、直す前のコードで再現した。SC-19 を出したまま Activity を `STARTED` より下に下げても `VoiceInput.attached` が true のままで、押下が声の入力へ回る（下のテスト2つが、直す前に時間切れで落ちる）。誤りではない。

**計画を書くときに決めたこと:**

- 付けるのは `RESUMED` のあいだだけにする。`STARTED` にしないのは、`MainActivity.onNewIntent`（インカムの押下を受ける）と `onStart` のどちらが先に届くかの保証が弱く、`onNewIntent` のあとには必ず `onResume` が来るため（報告のとおり）。押下は `onNewIntent` の時点で `attached` が false なら質問へ回る。
- 背面に回ったときに声の入力が録音中・文字にしている最中なら、`detach` が取り消して捨てる（今の `detach` の動き。`VoiceInputTest.leaving_drops_the_recording_or_the_text_still_being_made` が押さえている）。前面に戻ったときは付け直すだけで、録音は戻らない。
- 画面の回転などの構成の変更は、Activity を作り直すので、`onPause` を通る。これまでも画面の破棄で `detach` していたので、録音が捨てられる動きは変わらない。
- 文書は「SC-19 を開いているあいだ」を「前面に表示しているあいだ」に読めるよう直す（03 §2・mock・Android README）。
- 版を 0.14.1（`versionCode` 16）に上げる。この plan の実機の確認は、0.14.0 で走る PROJECT.md の「次にやること」1とは別に、停車中にできる（Task 4）。
- 計画を書くときに、使い捨ての作業ツリーで次を確かめた: テスト2つは直す前に落ち（時間切れ）、直すと `NoteRoutesTest` が3回続けて通り、全体の JVM のテストが715件通る（今の713件 + 2件）。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice6-plan1` を切る（Task 0）。親は、この plan を書いたブランチ `slice6-plan1`。push・マージはしない（利用者が明示したときだけ）。push の前に `pre-push-secret-scan`（スキャンと push は別のコマンドにし、結果を読んでから）。
- 作りの決まり: 判断の芯は Android に依存させない。部品は `AppGraph` で手で組む。この plan は画面のつなぎ（`ui/`）だけを変える。
- Room は版7のまま。ホームは全体がスクロールしない（この plan ではホームを変えない）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。端末のログ（`adb logcat`）には API の URL が出るので、書き写さない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*クラス名'`（Gradle のビルドキャッシュは共有されるので `--rerun` を付ける）。結果は `app/build/test-results/testDebugUnitTest/*.xml` で読む。
- Robolectric の決まり（SDK 35・画面の外の行は `performScrollTo` で出す・地図の部品は動かさない）。
- エディタの編集は Edit ツールで行い、heredoc や置換スクリプトで書き換えない。

## Review Focus

- SC-19 を出したまま背面に回し、インカムのボタンを押す → 質問が始まる（Task 1 のテスト2）。押下を受けるのが `onNewIntent`（`onResume` の前）でも、`attached` は背面に回った時点で false になっているので質問へ回る。
- 背面から前面に戻る → 声の入力が付け直され、SC-19 のボタンとインカムのボタンが声の入力に戻る（Task 1 のテスト1）。
- 背面に回したとき録音中だった声の入力 → 捨てられる。前面に戻っても録音は戻らない（`VoiceInputTest` が `detach` の取り消しを押さえている。この plan のテストは付け外しの時機だけを見る）。
- 質問が進んでいるときの押下 → 今までどおり質問のまま（`PressRouterTest.an_ask_under_way_keeps_the_button_even_on_sc19`）。
- 閉じていく画面の `detach` が新しく開いた画面を外さない（札。`NoteRoutesTest.sc19_takes_the_intercom_button_while_it_is_shown` と `VoiceInputTest`）。この plan は札の仕組みを変えない。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `ui/RecordsRoutes.kt` | `voiceUi()` が `LifecycleResumeEffect` で付け外しする | 1 |
| `handsfree/PressRouter.kt` | クラスの説明の「While SC-19 is shown」を「in front」に（挙動は変えない） | 1 |
| `app/src/test/.../ui/NoteRoutesTest.kt` | 付け外しの時機と、押下の行き先のテスト | 1 |
| `docs/03_screen_transition.md`・`docs/mock/index.html`・`Android/README.md` | 「開いているあいだ」を「前面に表示しているあいだ」に | 2 |
| `app/build.gradle.kts` | 版 0.14.1 | 3 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、今のテストを回す**

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice6-plan1
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-s6p1-t0.log 2>&1; tail -3 /tmp/trv2-s6p1-t0.log | head -1
```

Expected: `BUILD SUCCESSFUL`（713件）。

---

### Task 1: 声の入力を、前面に出ているあいだだけ SC-19 に付ける

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt`（`voiceUi()`）
- Modify: `app/src/main/java/com/touringproject/v2/handsfree/PressRouter.kt`（クラスの説明）
- Test: `app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt`

**Interfaces:**
- Produces: SC-19 を出しているあいだ、`VoiceInput.attached` は Activity が `RESUMED` のときだけ true。背面に回る（`ON_PAUSE`）と `detach(token)`、前面に戻る（`ON_RESUME`）と `attach()`。

- [ ] **Step 1: 失敗するテストを書く**

`NoteRoutesTest.kt` の import に次の2行を足す（`import androidx.compose.ui.test.assertTextEquals` の下）。

```kotlin
import androidx.lifecycle.Lifecycle
import com.touringproject.v2.handsfree.PressRouter
```

`a_memo_not_found_says_so_and_can_be_closed` の直前（`// Android #57: ...` のコメントの前）に、次の2つを足す。

```kotlin
  // Review R3-01: the voice input is attached only while SC-19 is in front. An Activity that is stopped (home, app
  // switch, screen off) gives the intercom button back to the ask; coming back to the front attaches it again.
  @Test
  fun sc19_gives_the_intercom_button_back_while_the_app_is_in_the_background() {
    keepRide()
    var shown by mutableStateOf(true)
    rule.setContent {
      if (shown) NewNoteRoute(records, notes, draft, onClose = {}, voice = NoteVoice(input, MutableStateFlow(VOICE_IDLE), MutableStateFlow(true)))
    }
    waitFor("voice")
    assertTrue(input.attached)
    rule.activityRule.scenario.moveToState(Lifecycle.State.CREATED)
    rule.waitUntil(5_000) { !input.attached }
    rule.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
    rule.waitUntil(5_000) { input.attached }
    // Leave the screen before the database closes: the records are read again once it is back in front.
    shown = false
    rule.waitForIdle()
    assertFalse(input.attached)
  }

  // Review R3-01: a press while SC-19 is behind the navigation app starts an ask, not a voice input.
  @Test
  fun an_intercom_press_while_sc19_is_in_the_background_starts_an_ask() {
    keepRide()
    var asks = 0
    var voicePresses = 0
    val router = PressRouter(
      trialActive = { false }, trialBusy = { false }, stopTrial = {}, stopCheckPlayback = {},
      askPress = { asks++ }, askStopRecording = {}, askTap = {},
      voiceAttached = { input.attached }, voicePress = { voicePresses++ },
    )
    rule.setContent {
      NewNoteRoute(records, notes, draft, onClose = {}, voice = NoteVoice(input, MutableStateFlow(VOICE_IDLE), MutableStateFlow(true)))
    }
    waitFor("voice")
    router.press()
    assertEquals(1, voicePresses)
    rule.activityRule.scenario.moveToState(Lifecycle.State.CREATED)
    rule.waitUntil(5_000) { !input.attached }
    router.press()
    assertEquals(1, asks)
    assertEquals(1, voicePresses)
  }

```

- [ ] **Step 2: 落ちることを確かめる（報告の再現）**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*NoteRoutesTest' > /tmp/trv2-s6p1-t1a.log 2>&1; tail -3 /tmp/trv2-s6p1-t1a.log | head -1
cd $AND && grep -o 'testcase name="[^"]*"\|<failure message="[^"]\{0,90\}' app/build/test-results/testDebugUnitTest/*NoteRoutesTest.xml
```

Expected: `BUILD FAILED`。上の2つのテストが `ComposeTimeoutException: Condition still not satisfied after 5000 ms` で落ち、ほかの4つは通る。**この2つが落ちなかったら、R3-01 は再現していない。止まって報告する**（spec §4: 誤りか、すでに直っている）。

- [ ] **Step 3: 直す**

`RecordsRoutes.kt` の import で、`import androidx.compose.runtime.DisposableEffect` の行を消し、`import androidx.lifecycle.compose.collectAsStateWithLifecycle` の上に次を足す。

```kotlin
import androidx.lifecycle.compose.LifecycleResumeEffect
```

`voiceUi()` を次のようにする（説明と、付け外しの2行）。

```kotlin
/**
 * The voice input while SC-19 is in front: attached, the intercom button goes to it (slice 3 spec §7.3). Going to the
 * back (home, app switch, screen off) or leaving SC-19 detaches it and drops whatever it was doing, so a ride's
 * intercom press while the navigation app is in front starts an ask (review R3-01). The pause, not the stop, is the
 * edge: an intercom press arrives in onNewIntent, which an onResume always follows.
 */
@Composable
private fun voiceUi(voice: NoteVoice?): NoteVoiceUi? {
  voice ?: return null
  LifecycleResumeEffect(voice) {
    val token = voice.input.attach()
    onPauseOrDispose { voice.input.detach(token) }
  }
  val state by voice.state.collectAsStateWithLifecycle()
  val online by voice.online.collectAsStateWithLifecycle()
  return NoteVoiceUi(state.phase, state.failure?.message, state.heard, online)
}
```

`PressRouter.kt` のクラスの説明で、`While SC-19 is shown, its voice input takes it` を `While SC-19 is in front, its voice input takes it` に直す（挙動は変えない）。

- [ ] **Step 4: 通ることを確かめる**

```bash
cd $AND && for i in 1 2 3; do ./gradlew testDebugUnitTest --rerun --tests '*NoteRoutesTest' --tests '*PressRouterTest' --tests '*VoiceInputTest' --tests '*AppUiTest' > /tmp/trv2-s6p1-t1b.log 2>&1; tail -3 /tmp/trv2-s6p1-t1b.log | head -1; done
```

Expected: 3回とも `BUILD SUCCESSFUL`。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt app/src/main/java/com/touringproject/v2/handsfree/PressRouter.kt app/src/test/java/com/touringproject/v2/ui/NoteRoutesTest.kt
cd $AND && git commit -m "fix: attach SC-19's voice input only while the activity is in front, so an intercom press in the navigation app starts an ask"
```

---

### Task 2: 文書: 「開いているあいだ」を「前面に表示しているあいだ」に

**Files:**
- Modify: `docs/03_screen_transition.md`（親。116行）、`docs/mock/index.html`（親。1182行）
- Modify: `Android/README.md`（20行・48行）

- [ ] **Step 1: 03 の文を直す**

`docs/03_screen_transition.md` の次の行を、

```
- SC-19（地点メモ）を開いているあいだは、インカムのボタンで質問を始めず、声の入力の開始と停止に使う（停車中に手袋のままでも書けるように）。
```

次のようにする。

```
- SC-19（地点メモ）を前面に表示しているあいだは、インカムのボタンで質問を始めず、声の入力の開始と停止に使う（停車中に手袋のままでも書けるように）。SC-19 を開いたままナビなどの別のアプリに切り替えたり、画面を消したりしたあいだは、声の入力を外し、インカムのボタンは質問を始める。
```

- [ ] **Step 2: mock の文を直す**

`docs/mock/index.html` の SC-19 の箇条で、`この画面を開いているあいだ、インカムのボタンは質問を始めない。` を `この画面を前面に表示しているあいだ、インカムのボタンは質問を始めない（別のアプリに切り替えているあいだは質問を始める）。` に直す。

- [ ] **Step 3: Android の README を直す**

20行（`handsfree/` の行）の `SC-19 を開いているあいだは声の入力へ` を `SC-19 を前面に表示しているあいだは声の入力へ` に直す。

48行の次の2か所を直す。

- `SC-19 を開いているあいだ（`attach`）は、インカムのボタンが` → `SC-19 を前面に表示しているあいだ（`attach`。Activity が `RESUMED` のあいだだけ付き、ホームボタン・アプリの切り替え・画面の消灯で外れ、前面に戻ると付け直す）は、インカムのボタンが`
- `SC-19 を離れると、録音も文字起こしの待ちも捨てる。` → `SC-19 を離れる・背面に回すと、録音も文字起こしの待ちも捨てる（前面に戻っても録音は戻らない）。`

- [ ] **Step 4: 写して、コミットする**

```bash
cd $ROOT && ./scripts/sync-docs.sh
cd $ROOT && git status --short
cd $AND && git add docs-parent README.md
cd $AND && git commit -m "docs: say that SC-19 holds the intercom button only while it is in front"
cd $ROOT && git add docs/03_screen_transition.md docs/mock/index.html
cd $ROOT && git commit -m "docs: say that SC-19 holds the intercom button only while it is in front"
```

Expected: `sync-docs.sh` が各ユニットの `docs-parent/` に写す。Android 以外（Backend・Agent・CICD）の `docs-parent/` が変わっていたら、各ユニットの `main` に直接コミットする（PROJECT.md の「前提」）。変わっていなければ何もしない。`scripts/check_links.py` のリンク切れは、`Backend/env/` の中の1件だけ（既知）。

```bash
cd $ROOT && python3 scripts/check_links.py | tail -2
```

---

### Task 3: 版と全体の確かめ・PROJECT.md

**Files:**
- Modify: `app/build.gradle.kts`（`versionCode`・`versionName`）
- Modify: `PROJECT.md`（親）

- [ ] **Step 1: 版を上げる**

`app/build.gradle.kts` の `versionCode = 15` を `versionCode = 16` に、`versionName = "0.14.0"` を `versionName = "0.14.1"` に直す。

```bash
cd $AND && git add app/build.gradle.kts
cd $AND && git commit -m "chore: raise the version to 0.14.1"
```

- [ ] **Step 2: `clean` から JVM のテスト・ビルド・権限・エミュレーターのテストのコンパイル**

```bash
cd $AND && ./gradlew clean > /dev/null && ./gradlew testDebugUnitTest assembleDebug assembleRelease compileDebugAndroidTestKotlin > /tmp/trv2-s6p1-t3.log 2>&1; tail -3 /tmp/trv2-s6p1-t3.log | head -1
cd $AND && ./scripts/check-release-permissions.sh
cd $AND && python3 -c "
import glob,re
t=f=0
for p in glob.glob('app/build/test-results/testDebugUnitTest/*.xml'):
    m=re.search(r'tests=\"(\d+)\" skipped=\"\d+\" failures=\"(\d+)\" errors=\"(\d+)\"',open(p).read())
    t+=int(m[1]); f+=int(m[2])+int(m[3])
print(t,f)"
```

Expected: `BUILD SUCCESSFUL`・`release permissions OK (15)`・`715 0`。`RideForegroundServiceTest.the_ask_keep_alive_reaches_the_running_service` だけが落ちたら、単独で回して通ることを確かめ、Android #94 にその日の発生を追記する（この plan では直さない）。

- [ ] **Step 3: PROJECT.md を更新して親でコミットする**

スライス6の plan 表の 1 の行を「実装済み（確認待ち: 実機で SC-19 を開いたまま背面に回してインカムのボタンを押す。JVM 715件。版 0.14.1）」にする。「次にやること」の2を、この plan の実機の確認（Task 4）にし、plan 2 の計画（`superpowers:brainstorming` で範囲を決めてから `superpowers:writing-plans`）を3にする。親の submodule の指す先は、Android のブランチの先頭に進める。

```bash
cd $ROOT && git add PROJECT.md Android
cd $ROOT && git commit -m "docs: record slice 6 plan 1 as implemented, awaiting the device check on 0.14.1"
```

---

### Task 4: 実機で確かめる（利用者と）

- [ ] **Step 1: 0.14.1 の release を実機に入れる**

```bash
cd $AND && ./gradlew assembleRelease && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
```

Expected: 「設定 → バージョン」が 0.14.1。

- [ ] **Step 2: 利用者に確かめてもらう（走行を記録中にして、停車中に）**

1. ホームの「📝 地点メモ」を押して SC-19 を開く。何も保存せず、ホームボタンで別のアプリ（ナビなど）に切り替える。
2. インカムのボタンを押す → アプリが前面に出て、**質問の一巡が始まる**（開始の合図 → 録音）。SC-19 の「■ 止めて文字にする」にならない。
3. 質問が終わったあと、SC-19 が前面にあれば、インカムのボタンで声の入力が始まる（前面に戻ると付け直されている）。
4. SC-19 を開いたまま画面を消し、点けて、SC-19 のボタン「🎤 声で入力」が使える。

結果は PROJECT.md の plan 表の 1 の行に書く（✗ が出たら `superpowers:systematic-debugging`）。✓ なら、行を「✅ 完了」にし、Android と親のブランチのマージを利用者に確かめる（マージは利用者が明示したときだけ）。
