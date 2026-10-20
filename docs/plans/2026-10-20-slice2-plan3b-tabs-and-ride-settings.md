# スライス2 計画3b: タブ・質問の数・走行の記録（SC-16）実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 画面の下に「ホーム・記録・設定」のタブが並び、タブごとに画面の位置が残る。ホームの走行のカードと SC-04 の要約に質問の数が出る。設定の SC-16 で最長時間（6・12・24・48時間）を選ぶと、記録中の走行の締め切りもすぐに変わる。

**Architecture:** タブとバックスタックの組は、Compose に依存しない `ui/Tabs.kt` の `TabStacks` にまとめる。`AppUi` は、タブごとに Navigation 3 のバックスタックを1本ずつ持ち、選んでいるタブのものを `NavDisplay` に渡す。最長時間は `Settings` に持つ。締め切りを計算し直すのは `RideController.maxRecordingChanged()` だけで、走行の状態を変えるのは引き続き `RideController` だけ。質問の数は、Room の `asks` の表の数を `Flow` で受けて描く。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01（Material3 の `NavigationBar`・`Scaffold`）・Navigation 3 1.0.1・Room 2.8.4・Robolectric 4.16（SDK 35）。足す依存は無い。

**Spec:** [docs/specs/2026-10-17-slice2-design.md](../specs/2026-10-17-slice2-design.md)（§4.4・§7.1・§7.2・§7.3・§7.8・§9・§11）。見た目と文言は [画面モック](../mock/index.html) の SC-02・SC-04・SC-09・SC-16 とタブ。

**範囲に入れた issue（Android）:** #15（締め切りのあとに一時停止すると、自動終了にならない）・#19（一時停止・再開のトーストが、何もしなかったときにも出る）・#20（SC-17・SC-04 を開いたまま回転すると、シートと名前が消える）。

**前提:** plan 3a（Android・親のブランチ `slice2-plan3a`。Android の PR #31・親の PR #10）の上に作る。3a の `asks` の表・`RideController` の `changed`・版 0.2.0 を使う。

**計画を書くときに決めたこと（spec からの具体化。利用者と決めたものを含む）:**
- 記録のタブは、この plan では置くだけにし、「走行と日ごとの記録の一覧は、次の版でここに出ます。」とだけ出す（`RecordsPlaceholder`）。plan 4 で SC-05 に差し替える。タブとバックスタックの組み替えを一度で済ませるため（利用者と決めた）。
- 記録中に最長時間を短くして、新しい締め切り（記録中の区間の開始＋新しい最長時間）がもう過ぎていたら、その締め切りの時刻で自動終了とし、自動終了の通知も出す（spec §4.4 の「締め切りの時刻で終える」と同じ。利用者と決めた）。過ぎていなければ、走行の締め切りとアラームを置き直す。締め切りは送らないので、`updatedAt` は進めない。一時停止中の走行は、再開したときに新しい最長時間を使う。
- 締め切りを過ぎたあと、気付く前（アラームの遅れなど）に利用者が一時停止を押したら、締め切りの時刻で自動終了にする（#15）。SC-04 の「終了して保存」を押したときも同じく締め切りの時刻で自動終了にし、SC-04 で入れた名前を残し、通知も出す（利用者と決めた）。
- 最長時間の選択肢は spec §4.4 の 6・12・24・48 時間（モックの 12・24・48・72 時間とは違う。spec のほうが新しい）。既定は24時間。保存は `Settings.maxRecordingHours`（DataStore の JSON。壊れた値・選択肢に無い値は既定に戻す）。設定を読み終える前に走行を始めることはないが、読み終える前は既定を使う。
- 質問の数は、その走行に結びついて端末に残った質問（回答あり・失敗の両方）の数。結果が届いて端末に書いた時点で増える。
- ホームの右上の「⚙ 設定」のボタンは外す（モックのホームには無い。設定はタブから開く）。ホームのユーザー名の札と警告の帯（接続キー・戻るアプリ）は、設定のタブに移り、その最初の画面の上に該当の画面を開く（`TabStacks.open`）。Back で設定の最初の画面に戻る。
- Back: タブの中で戻る。記録・設定のタブの最初の画面ではホームのタブへ移る。ホームの最初の画面ではアプリを閉じる（`activity.finish()`。今までどおり、プロセスは残る）。選んでいるタブをもう一度押すと、そのタブの最初の画面へ戻る。
- タブの帯は、質問の画面（AskOverlay）が出ているあいだ（一巡の段階が `IDLE` 以外）は隠す。地図の全画面は plan 4。
- `Scaffold` の `bottomBar` に帯を置き、`NavDisplay` に `Modifier.padding(inner).consumeWindowInsets(inner)` を渡す。各画面の `safeDrawingPadding()` は残す（使われた分は差し引かれ、二重にならない）。
- SC-17・SC-04 のどちらを開いているかと、打ち込み中の名前は `rememberSaveable` で持つ（#20）。選んでいるタブも `rememberSaveable`。バックスタックは `rememberNavBackStack` で、作り直しのあとも残る。
- `pause()`・`resume()` は状態を変えたかを `Boolean` で返し、変えたときだけトーストを出す。`start()` が false のときは「走行を開始できませんでした」をトーストで出す（#19。別の経路で前の走行が再開した、DB をまだ読めていない、など）。
- SC-16 の文言はモックのまま。設定の一覧の行は「走行の記録」「最長 N時間」で、「応答後に戻るアプリ」の上に置く。
- タブのアイコンは文字（🏠・🗺・⚙）にする。Material のアイコンの依存を足さないため。
- 版を 0.3.0（`versionCode` 3）に上げる（Android の README の決まり）。

この計画のコードは、使い捨てのフォルダで JVM のテスト320件（始める前の300件＋20件）・エミュレーターのテスト4件・`assembleDebug`・`assembleRelease`（lint を含む）・`scripts/check-release-permissions.sh`（15件）が通ることを確かめてから書いた。

## Global Constraints

- 作業するリポジトリは `Android/` と親。どちらも `slice2-plan3a` から `slice2-plan3b` を切る（Task 0）。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- 作りの決まり（移行の spec §5）: 状態機械と司令塔は Android に依存させない。部品は `AppGraph` で手で組む。走行の状態を変えるのは `RideController` だけ。タブとバックスタックの組は Compose に依存させない（spec §7.1）。
- 最長時間は 6・12・24・48 時間から選ぶ。既定は24時間。締め切りは「区間の開始＋最長時間」。終了の時刻は締め切りの時刻（spec §4.4）。
- ホームは全体がスクロールしない（spec §7.2）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --tests '*クラス名'`。テストを確かめるときは `--rerun` を付ける（使い捨てのフォルダで同じ入力を通したので、ビルドキャッシュから結果が返ることがある）。`ScreensTest.kt` の中のクラスは `HomeScreenTest`・`SettingsScreensTest` などなので、`--tests '*ScreensTest'` では `HomeScreenTest` が走らない。クラスの名前で指す。
- Robolectric の決まり（SDK 35・`withContext(Dispatchers.Main)` を直に呼ばない・`backgroundScope` は `advanceUntilIdle` で進まない）と、エミュレーターの決まり（`ANDROID_SERIAL=emulator-5554`・テスト中は利用者に触らないよう頼む）は plan 3a と同じ。
- 子を持つ欄（`Stat` の Column）に付けたタグの文字は、`onChildAt(0).assertTextEquals(...)` で見る（タグの付いた Column 自身は文字を持たない）。

## Review Focus

- 記録中に最長時間を何度も変える（24→6→48）→ そのたびに締め切りとアラームが今の区間の開始から計算し直され、最後の値だけが効く。過ぎた値を選んだときだけ終わる。Task 1 の `a_longer_or_shorter_limit_moves_the_recording_segments_deadline_and_its_alarm`・`a_limit_the_segment_has_already_passed_ends_the_ride_automatically_at_the_new_deadline`。
- 走行中の質問の結果が、SC-04 を開いているあいだに届く → 開いたままの要約の質問の数が増える（数は `Flow` で受ける）。Task 3 の `the_count_of_a_ride_follows_the_asks_kept_for_it`。
- SC-04 で名前を変えている途中に端末を回す → シートが開いたまま、打ち込んだ名前が残る。Task 5 の `the_names_being_typed_survive_a_recreated_activity`・Task 6 の `the_start_sheet_stays_open_when_the_activity_is_recreated`。
- 設定のタブの奥（回答の音量）にいるまま、ホームのユーザー名の札を押す → 設定のタブの最初の画面の上にユーザー名の画面が出て、Back で設定の最初の画面に戻る（音量の画面には戻らない）。Task 4 の `opening_a_screen_of_another_tab_shows_it_above_that_tabs_first_screen`・Task 6 の `the_user_chip_opens_the_user_name_in_the_settings_tab`。
- インカムで質問しているあいだ → タブの帯が隠れ、質問の画面の大きなボタンの邪魔をしない。Back はこれまでどおり質問の画面が持つ。Task 4 の `the_tabs_hide_while_an_ask_is_on_screen`。

---

## ファイル構成（`Android/app/src/` から。`...` は `com/touringproject/v2`）

| パス | 役割 | Task |
|---|---|---|
| `main/java/.../ride/RideController.kt`・`ride/Ride.kt` | 一時停止・再開が変えたかを返す・締め切りのあとの一時停止と終了・最長時間を変えたときの計算し直し | 1 |
| `main/java/.../settings/Settings.kt`・`AppGraph.kt` | 最長時間の設定と、司令塔への受け渡し | 2 |
| `main/java/.../store/RideDatabase.kt`・`ui/RideLabels.kt`・`ui/RideScreens.kt`・`AppGraph.kt`・`ui/AppUi.kt` | 質問の数 | 3 |
| `main/java/.../ui/Tabs.kt`（新規） | タブとバックスタックの組（Compose に依存しない） | 4 |
| `main/java/.../ui/TabBar.kt`（新規）・`ui/SettingsScreens.kt`・`ui/HomeScreen.kt`・`ui/RideScreens.kt` | タブの帯・記録のタブの仮の画面・SC-16・設定の行・ホームの設定ボタンを外す・シートの名前を残す | 5 |
| `main/java/.../ui/AppUi.kt` | タブの組み込み・Back・トースト・SC-16 から司令塔を呼ぶ・シートの状態を残す | 6 |
| `app/build.gradle.kts`・`README.md`（Android） | 版 0.3.0・文書 | 7 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: 両方のリポジトリで、3a のブランチから切る**

```bash
cd $ROOT && git switch slice2-plan3b
cd $AND && git switch slice2-plan3a && git pull --ff-only && git switch -c slice2-plan3b
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-base.log 2>&1; tail -3 /tmp/trv2-base.log
```

Expected: `BUILD SUCCESSFUL`（始める前の JVM のテストは300件。この plan で20件増え、320件になる）。親の `slice2-plan3b` は、この plan のコミットで作ってある。

---

### Task 1: 司令塔（#15・#19・最長時間を変えたときの計算し直し）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ride/RideController.kt`
- Test: `app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt`

**Interfaces:**
- Consumes: `RideDeps.maxRecordingMs: () -> Long`・`Ride.end(at, reason, now, name)`・`finish`・`autoEndIfDue`（既存）
- Produces: `suspend fun pause(): Boolean`（一時停止したら true。締め切りを過ぎていたら自動終了して false）・`suspend fun resume(): Boolean`・`suspend fun end(name: String): Boolean`（締め切りを過ぎていたら、締め切りの時刻で自動終了し、渡した名前を残す）・`suspend fun maxRecordingChanged()`

- [ ] **Step 1: 失敗するテストを書く**

`World` に `var max = MAX` を足し（`/** The longest recording time the rider has chosen (SC-16). */`）、`maxRecordingMs = { MAX }` を `maxRecordingMs = { max }` に替える。`class RideControllerTest` の最後に足す:

```kotlin
  @Test
  fun pause_resume_and_start_say_whether_they_changed_anything() = runTest {
    val w = World()
    w.controller.load()
    assertFalse(w.controller.pause())
    assertFalse(w.controller.resume())
    assertTrue(w.controller.start("箱根"))
    assertFalse(w.controller.resume())
    w.now = 5_000
    assertTrue(w.controller.pause())
    assertFalse(w.controller.pause())
    w.now = 9_000
    assertTrue(w.controller.resume())
  }

  @Test
  fun a_pause_after_the_deadline_ends_the_ride_automatically_at_the_deadline() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = 1_000 + MAX + 60_000
    assertFalse(w.controller.pause())
    val ended = w.stored()
    assertEquals(RideStatus.ENDED, ended.status)
    assertEquals(EndReason.AUTO, ended.endReason)
    assertEquals(1_000 + MAX, ended.endedAt())
    assertEquals(listOf(ended), w.autoEnded)
  }

  @Test
  fun an_end_after_the_deadline_is_an_automatic_end_at_the_deadline_with_the_new_name() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = 1_000 + MAX + 60_000
    assertTrue(w.controller.end("箱根から御殿場へ"))
    val ended = w.stored()
    assertEquals(EndReason.AUTO, ended.endReason)
    assertEquals(1_000 + MAX, ended.endedAt())
    assertEquals("箱根から御殿場へ", ended.name)
    assertEquals(1, w.autoEnded.size)
  }

  @Test
  fun a_longer_or_shorter_limit_moves_the_recording_segments_deadline_and_its_alarm() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.events.clear()
    val updatedAt = w.stored().updatedAt
    w.now = 2 * HOUR_MS
    w.max = 6 * HOUR_MS
    w.controller.maxRecordingChanged()
    assertEquals(1_000 + 6 * HOUR_MS, w.stored().deadline)
    assertEquals(1_000 + 6 * HOUR_MS, w.controller.active.value?.deadline)
    assertEquals(listOf("alarm:${1_000 + 6 * HOUR_MS}"), w.events)
    // The deadline is not sent, so the Backend has nothing new.
    assertEquals(updatedAt, w.stored().updatedAt)
  }

  @Test
  fun a_limit_the_segment_has_already_passed_ends_the_ride_automatically_at_the_new_deadline() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = 7 * HOUR_MS
    w.max = 6 * HOUR_MS
    w.controller.maxRecordingChanged()
    val ended = w.stored()
    assertEquals(EndReason.AUTO, ended.endReason)
    assertEquals(1_000 + 6 * HOUR_MS, ended.endedAt())
    assertEquals(1, w.autoEnded.size)
    assertNull(w.controller.active.value)
  }

  @Test
  fun a_paused_ride_takes_the_new_limit_when_it_resumes() = runTest {
    val w = World()
    w.controller.load()
    w.controller.start("箱根")
    w.now = 5_000
    w.controller.pause()
    w.max = 6 * HOUR_MS
    w.controller.maxRecordingChanged()
    assertNull(w.stored().deadline)
    w.now = 9_000
    w.controller.resume()
    assertEquals(9_000 + 6 * HOUR_MS, w.stored().deadline)
  }
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideControllerTest' > /tmp/trv2-t1.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t1.log | head -3`
Expected: コンパイルの失敗（`pause()` が `Unit` を返す・`maxRecordingChanged` が無い）

- [ ] **Step 3: 実装する**

- `pause()` は、記録中でなければ false。`autoEndIfDue(ride, now)` が true なら false を返す（自動終了した）。それ以外は今までどおり一時停止して true。
- `resume()` は、一時停止中でなければ false。再開したら true。
- `autoEndIfDue(ride, now, name: String = ride.name)` に名前を足し、`finish(ride.end(deadline, EndReason.AUTO, now, name))` にする。`end(name)` は、名前が使えれば `if (!autoEndIfDue(ride, now, clean)) finish(ride.end(now, EndReason.MANUAL, now, clean))`。
- `maxRecordingChanged()` は `locked { ... }` の中で、記録中の走行が無ければ何もしない。締め切りを `ride.segments.last().startedAt + deps.maxRecordingMs()` にし、`autoEndIfDue(ride.copy(deadline = 新しい締め切り), now)` が true ならそこで終える。そうでなければ、その締め切りの走行を `save` し、`activeRide` を置き換え、`alarm.set(id, 新しい締め切り)`。`updatedAt` は変えない。
- KDoc に、締め切りのあとの一時停止・終了の扱い（Android #15）と US-C-08.005 を書く。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideControllerTest' --rerun > /tmp/trv2-t1.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t1.log`
Expected: `BUILD SUCCESSFUL`（33件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ride/RideController.kt app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
git commit -m "feat: end a ride past its deadline automatically and follow a new longest recording time" -m "Fixes #15"
```

---

### Task 2: 最長時間の設定

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/settings/Settings.kt`・`app/src/main/java/com/touringproject/v2/AppGraph.kt`・`app/src/main/java/com/touringproject/v2/ride/Ride.kt`
- Test: `app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt`

**Interfaces:**
- Produces: `val MAX_RECORDING_HOURS_CHOICES = listOf(6, 12, 24, 48)`・`const val DEFAULT_MAX_RECORDING_HOURS = 24`・`Settings.maxRecordingHours: Int = DEFAULT_MAX_RECORDING_HOURS`（JSON の `maxRecordingHours`）。`RideDeps.maxRecordingMs` は `(settings.settings.value?.maxRecordingHours ?: DEFAULT_MAX_RECORDING_HOURS) * HOUR_MS`

- [ ] **Step 1: 失敗するテストを書く**

`SettingsTest.kt` の `saved_settings_round_trip` の `Settings(...)` に `maxRecordingHours = 6` を足す。`broken_values_fall_back_to_defaults` の JSON の最後に `,"maxRecordingHours":72` を足し、最後に `assertEquals(DEFAULT_MAX_RECORDING_HOURS, s.maxRecordingHours)` を足す。新しいテストを足す:

```kotlin
  @Test
  fun the_longest_recording_time_is_24_hours_until_chosen_from_6_12_24_48() {
    assertEquals(24, decodeSettings("""{"userName":"rider01"}""").first.maxRecordingHours)
    assertEquals(listOf(6, 12, 24, 48), MAX_RECORDING_HOURS_CHOICES)
  }
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*SettingsTest' > /tmp/trv2-t2.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t2.log | head -3`
Expected: コンパイルの失敗（`maxRecordingHours` が無い）

- [ ] **Step 3: 実装する**

- `Settings.kt` に上の2つの値（コメント `// SC-16: how long a ride may record without a pause before it ends by itself (slice 2 spec §4.4, US-C-08.003).`）と `maxRecordingHours` を足す。`decodeSettings` は `answerVolumeDb` と同じ形で、選択肢に無ければ既定。`encodeSettings`・`SavedSettings` にも足す。
- `AppGraph.kt` の `maxRecordingMs` を上の式にする（コメント `// Read at each start and resume; before the settings are loaded only the default exists.`）。import の `DEFAULT_MAX_RECORDING_MS` を `HOUR_MS` と `settings.DEFAULT_MAX_RECORDING_HOURS` に替える。
- `Ride.kt` の `DEFAULT_MAX_RECORDING_MS` とその KDoc を消す（使うところが無くなる）。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*SettingsTest' --tests '*RideTest' --rerun > /tmp/trv2-t2.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t2.log`
Expected: `BUILD SUCCESSFUL`（`SettingsTest` 9件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/settings/Settings.kt app/src/main/java/com/touringproject/v2/AppGraph.kt \
  app/src/main/java/com/touringproject/v2/ride/Ride.kt app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
git commit -m "feat: keep the longest recording time in the settings"
```

---

### Task 3: 質問の数（ホームの走行のカード・SC-04）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/store/RideDatabase.kt`（`AskDao`）・`app/src/main/java/com/touringproject/v2/ui/RideLabels.kt`・`app/src/main/java/com/touringproject/v2/ui/RideScreens.kt`・`app/src/main/java/com/touringproject/v2/AppGraph.kt`・`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`
- Test: `app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt`・`app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt`・`app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt`

**Interfaces:**
- Consumes: 3a の `asks` の表・`AskDao`・`RoomAskLog`
- Produces: `AskDao.countForRide(rideId: String): Flow<Int>`（`SELECT COUNT(*) FROM asks WHERE rideId = :rideId`）・`AppGraph.askCount(rideId: String): Flow<Int>`・`RideCardUi(name, paused, elapsed, distance, questions: String)`・`rideCard(ride, now, questions: Int)`・`EndSummaryUi(elapsed, distance, questions: String, note)`・`endSummary(ride, now, zone, questions: Int)`。走行のカードと SC-04 の要約に `Stat(questions, "質問")`（タグ `rideQuestions`・`endQuestions`）

- [ ] **Step 1: 失敗するテストを書く**

`RoomAskLogTest.kt` の import に `kotlinx.coroutines.flow.first` を足し、作り物の DAO（`a_failed_write_...` の中の `object : AskDao`）に `override fun countForRide(rideId: String) = kotlinx.coroutines.flow.flowOf(0)` を足す。`a_failed_write_...` の前に足す:

```kotlin
  @Test
  fun the_count_of_a_ride_follows_the_asks_kept_for_it() = runBlocking {
    val count = db.asks().countForRide("r1")
    assertEquals(0, count.first())
    log.save(record)
    log.save(record.copy(askId = "a2", outcome = AskOutcome.FAILED, failure = "no_speech"))
    log.save(record.copy(askId = "a3", rideId = null))
    log.save(record.copy(askId = "a4", rideId = "r2"))
    assertEquals(2, count.first())
    db.close()
  }
```

`RideLabelsTest.kt`: `endSummary(..., TOKYO)` を `endSummary(..., TOKYO, questions = 4)`、期待を `EndSummaryUi("1:30", "62.4 km", "4", "08:58〜...")` に。`rideCard(ride, 60_000)` を `rideCard(ride, 60_000, questions = 3)`、期待を `RideCardUi("箱根", false, "0:01", "0.0 km", "3")` に。`rideCard(ride.pause(60_000), 120_000)` に `questions = 0` を足す。

`RideScreensTest.kt`: import に `assertTextEquals`・`onChildAt` を足す。`RideCardUi(...)` と `EndSummaryUi(...)` の呼び出しすべてに質問の数 `"4"` を足す（`RideCardUi` は最後、`EndSummaryUi` は3つ目）。`a_recording_ride_shows_its_time_and_distance_and_can_pause_or_end` の `52.8 km` の確かめの次に足す:

```kotlin
    rule.onNodeWithTag("rideQuestions").onChildAt(0).assertTextEquals("4")
    rule.onNodeWithText("質問").assertExists()
```

`the_end_sheet_shows_the_summary_and_keeps_the_name_from_being_emptied` の要約の文の確かめの次に足す:

```kotlin
    rule.onNodeWithTag("endQuestions").onChildAt(0).assertTextEquals("4")
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RoomAskLogTest' --tests '*RideLabelsTest' --tests '*RideScreensTest' > /tmp/trv2-t3.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t3.log | head -3`
Expected: コンパイルの失敗（`countForRide`・`questions` が無い）

- [ ] **Step 3: 実装する**

- `AskDao.countForRide`（KDoc `/** How many of the ride's asks are kept, answered or failed; follows every new one (SC-02, SC-04). */`。import `kotlinx.coroutines.flow.Flow`）。
- `RideLabels.kt` の2つの型と関数に `questions` を足す（数を `toString()` して持つ）。`RideCardUi` の KDoc に「answered or failed; slice 2 spec §7.2」と書く。
- `RideScreens.kt`: `RideCard` の `距離` の次に `Stat(ride.questions, "質問", Modifier.testTag("rideQuestions"))`、`EndRideSheet` の `距離` の次に `Stat(summary.questions, "質問", Modifier.testTag("endQuestions"))`。`RideCard` の KDoc から「the question count waits for plan 3」を消す。
- `AppGraph.askCount(rideId) = database.asks().countForRide(rideId)`。
- `AppUi.kt`: `val questions by remember(ride?.id) { ride?.id?.let(graph::askCount) ?: flowOf(0) }.collectAsStateWithLifecycle(0)` を置き、`rideCard(it, now, questions)`・`endSummary(active, now, ZoneId.systemDefault(), questions)` にする。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RoomAskLogTest' --tests '*RideLabelsTest' --tests '*RideScreensTest' --rerun > /tmp/trv2-t3.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t3.log`
Expected: `BUILD SUCCESSFUL`（`RoomAskLogTest` 3件・`RideLabelsTest` 5件・`RideScreensTest` 9件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/ui/RideLabels.kt \
  app/src/main/java/com/touringproject/v2/ui/RideScreens.kt app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt app/src/test/java/com/touringproject/v2/ui/RideLabelsTest.kt app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt
git commit -m "feat: show the ride's question count on the home card and in the end summary"
```

---

### Task 4: タブとバックスタックの組

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ui/Tabs.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/TabsTest.kt`（新規）

**Interfaces:**
- Consumes: `ask.Phase`（既存）
- Produces: `enum class Tab { HOME, RECORDS, SETTINGS }`・`class TabStacks<K>(stacks: Map<Tab, MutableList<K>>, selected: () -> Tab, select: (Tab) -> Unit)`（`val tab: Tab`・`val current: MutableList<K>`・`val canGoBack: Boolean`・`fun press(pressed: Tab)`・`fun back(): Boolean`・`fun open(tab: Tab, key: K)`）・`fun tabsShown(phase: Phase): Boolean`（`phase == Phase.IDLE`）

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ui/TabsTest.kt`:

```kotlin
package com.touringproject.v2.ui

import com.touringproject.v2.ask.Phase
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TabsTest {
  private var selected = Tab.HOME
  private val home = mutableListOf("home")
  private val records = mutableListOf("records")
  private val settings = mutableListOf("settings")
  private val tabs = TabStacks(mapOf(Tab.HOME to home, Tab.RECORDS to records, Tab.SETTINGS to settings), { selected }, { selected = it })

  @Test
  fun each_tab_keeps_where_it_was_left() {
    tabs.press(Tab.SETTINGS)
    tabs.current += "volume"
    tabs.press(Tab.HOME)
    assertEquals(listOf("home"), tabs.current)
    tabs.press(Tab.SETTINGS)
    assertEquals(listOf("settings", "volume"), tabs.current)
  }

  @Test
  fun pressing_the_shown_tab_goes_back_to_its_first_screen() {
    tabs.press(Tab.SETTINGS)
    tabs.current += "volume"
    tabs.current += "recordings"
    tabs.press(Tab.SETTINGS)
    assertEquals(listOf("settings"), tabs.current)
    assertEquals(Tab.SETTINGS, selected)
  }

  @Test
  fun back_goes_back_within_the_tab_then_to_home_then_leaves_the_app() {
    tabs.press(Tab.SETTINGS)
    tabs.current += "volume"
    assertTrue(tabs.canGoBack)
    assertTrue(tabs.back())
    assertEquals(listOf("settings"), tabs.current)
    assertTrue(tabs.back())
    assertEquals(Tab.HOME, selected)
    assertFalse(tabs.canGoBack)
    assertFalse(tabs.back())
    assertEquals(Tab.HOME, selected)
  }

  @Test
  fun opening_a_screen_of_another_tab_shows_it_above_that_tabs_first_screen() {
    tabs.press(Tab.SETTINGS)
    tabs.current += "volume"
    tabs.press(Tab.HOME)
    tabs.open(Tab.SETTINGS, "user")
    assertEquals(Tab.SETTINGS, selected)
    assertEquals(listOf("settings", "user"), tabs.current)
    tabs.back()
    assertEquals(listOf("settings"), tabs.current)
  }

  @Test
  fun the_tabs_hide_while_an_ask_is_on_screen() {
    assertTrue(tabsShown(Phase.IDLE))
    for (phase in Phase.entries - Phase.IDLE) assertFalse(phase.name, tabsShown(phase))
  }
}
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*TabsTest' > /tmp/trv2-t4.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t4.log | head -3`
Expected: コンパイルの失敗（`TabStacks` が無い）

- [ ] **Step 3: 実装する**

テストの振る舞いのとおり。`press` は、押したのが今のタブならその最初の画面まで戻し、ほかのタブなら選ぶだけ。`back` は、今のスタックが2つ以上なら1つ戻して true、ホーム以外の最初の画面ならホームを選んで true、ホームの最初の画面なら false。`open(tab, key)` は、そのタブのスタックを最初の画面まで戻してから `key` を積み、そのタブを選ぶ。ファイルの冒頭のコメントに「Compose から離して JVM で試すため」と、`TabStacks` の KDoc に「スタックは Navigation 3 の NavBackStack を渡す。選んでいるタブは、画面が saveable な状態に持てるよう関数で読み書きする」と書く。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*TabsTest' --rerun > /tmp/trv2-t4.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t4.log`
Expected: `BUILD SUCCESSFUL`（5件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/Tabs.kt app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
git commit -m "feat: keep one back stack per tab outside Compose"
```

---

### Task 5: 画面の部品（タブの帯・記録のタブ・SC-16・設定の行・ホーム・シートの名前）

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ui/TabBar.kt`
- Modify: `app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt`・`app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt`・`app/src/main/java/com/touringproject/v2/ui/RideScreens.kt`・`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`（呼び出しを合わせるだけ。組み込みは Task 6）
- Test: `app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt`・`app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt`

**Interfaces:**
- Consumes: `Tab`（Task 4）・`MAX_RECORDING_HOURS_CHOICES`・`Settings.maxRecordingHours`（Task 2）
- Produces: `@Composable fun TabBar(selected: Tab, onPress: (Tab) -> Unit)`（Material3 の `NavigationBar`。項目は 🏠 ホーム・🗺 記録・⚙ 設定、タグ `tab-HOME`・`tab-RECORDS`・`tab-SETTINGS`）・`@Composable fun RecordsPlaceholder(modifier: Modifier = Modifier)`（`TabBar.kt` に置く。文言「走行と日ごとの記録の一覧は、次の版でここに出ます。」）・`@Composable fun RideRecordingScreen(settings: Settings, onUpdate: (Settings) -> Unit, modifier: Modifier = Modifier)`（`SettingsScreens.kt`。選択肢のタグ `maxHours-N`）・`SettingsScreen(settings, apiKey, onConnection, onUser, onRideRecording, onReturnApp, onVolume, onRecordings, version, modifier)`（`onRideRecording` を `onUser` の次に足す）・`HomeScreen(ui, onTapToTalk, onUser, onBanner, onNewConversation, modifier, onDismissVolume, ride)`（`onSettings` を外す）

- [ ] **Step 1: 失敗するテストを書く**

`ScreensTest.kt` の `HomeScreen(...)` の呼び出し4つから、3つ目の引数（`onSettings` の `{}`）を消す。`the_settings_list_leads_to_the_volume_and_the_recordings` を、次に置き換える:

```kotlin
  @Test
  fun the_settings_list_leads_to_the_volume_and_the_recordings() {
    val opened = mutableListOf<String>()
    rule.setContent {
      SettingsScreen(
        Settings("rider01", answerVolumeDb = 3, maxRecordingHours = 12), null, {}, {}, { opened += "ride" }, {}, { opened += "volume" }, { opened += "recordings" }, "0.2.0",
      )
    }
    rule.onNodeWithText("最長 12時間").performClick()
    rule.onNodeWithText("+3dB").performClick()
    rule.onNodeWithText("録音の確認").performClick()
    assertEquals(listOf("ride", "volume", "recordings"), opened)
  }
```

`the_settings_list_shows_the_app_version_as_a_row_that_leads_nowhere` の `SettingsScreen(...)` に `{}` を1つ足す（`onRideRecording`）。`the_answer_volume_is_chosen_from_three_steps` の前に足す:

```kotlin
  @Test
  fun the_longest_recording_time_is_chosen_from_four_steps() {
    var updated: Settings? = null
    rule.setContent { RideRecordingScreen(Settings("rider01"), { updated = it }) }
    rule.onNodeWithText("連続して記録できる最長時間").assertExists()
    for (hours in listOf(6, 12, 24, 48)) rule.onNodeWithTag("maxHours-$hours").assertExists()
    rule.onNodeWithTag("maxHours-6").performClick()
    assertEquals(6, updated!!.maxRecordingHours)
  }

  @Test
  fun the_tab_bar_names_the_three_tabs_and_tells_which_was_pressed() {
    val pressed = mutableListOf<Tab>()
    rule.setContent { TabBar(Tab.HOME) { pressed += it } }
    rule.onNodeWithText("ホーム").assertExists()
    rule.onNodeWithText("記録").performClick()
    rule.onNodeWithText("設定").performClick()
    assertEquals(listOf(Tab.RECORDS, Tab.SETTINGS), pressed)
  }
```

`RideScreensTest.kt` の import に `assertTextContains`・`junit4.StateRestorationTester`・`performTextReplacement`・`runtime.getValue`・`runtime.mutableStateOf`・`runtime.setValue` を足し、`the_start_sheet_says_why_without_the_location_permission` の前に足す（終了のシートは入力の位置が先頭なので、打ち込みではなく置き換えで入れる）:

```kotlin
  @Test
  fun the_names_being_typed_survive_a_recreated_activity() {
    val restore = StateRestorationTester(rule)
    var ending by mutableStateOf(false)
    restore.setContent {
      if (ending) EndRideSheet(EndSummaryUi("1:30", "62.4 km", "4", ""), "箱根", {}, {})
      else StartRideSheet(locationAllowed = true, onStart = {}, onDismiss = {})
    }
    rule.onNodeWithTag("rideName").performTextInput("箱根")
    restore.emulateSavedInstanceStateRestore()
    rule.onNodeWithTag("rideName").assertTextContains("箱根")
    ending = true
    rule.waitForIdle()
    rule.onNodeWithTag("rideName").performTextReplacement("箱根から御殿場へ")
    restore.emulateSavedInstanceStateRestore()
    rule.onNodeWithTag("rideName").assertTextContains("箱根から御殿場へ")
  }
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*HomeScreenTest' --tests '*SettingsScreensTest' --tests '*RideScreensTest' > /tmp/trv2-t5.log 2>&1; grep -E "FAILED|BUILD|e: " /tmp/trv2-t5.log | head -3`
Expected: コンパイルの失敗（`RideRecordingScreen`・`TabBar`・`onRideRecording` が無い）

- [ ] **Step 3: 実装する**

- `TabBar.kt`: 上の Produces のとおり。アイコンは `Text(絵文字, fontSize = 20.sp)`。冒頭のコメントに 02 §1・spec §7.1。`RecordsPlaceholder` の KDoc に「plan 4 で SC-05 に差し替える」。
- `RideRecordingScreen`: モックの SC-16 の文言をそのまま使う（見出し「連続して記録できる最長時間」、説明「開始または再開してから一時停止せずに記録し続けた時間がこれを超えると、終了し忘れとみなして自動で終了・保存します。一時停止して再開すると数え直します」、選択肢「N時間」、注「泊まりがけでも、休憩や宿泊で一時停止していれば数え直すので、ふだんは変える必要はありません。記録中の走行にも、変更はすぐに反映されます。」）。選択肢は `VolumeScreen` と同じ `FilterChip` の並び。
- `SettingsScreen`: 「応答後に戻るアプリ」の行の前に `SettingsRow("走行の記録", "最長 ${settings.maxRecordingHours}時間", onRideRecording)`。
- `HomeScreen`: `onSettings` と「⚙ 設定」のボタンを外し、右上は「🎤 押して話す」だけにする（コメント `// Settings is a tab now (slice 2 spec §7.1).`）。
- `RideScreens.kt`: `StartRideSheet` と `EndRideSheet` の `name` を `rememberSaveable` にする（#20）。
- `AppUi.kt`: コンパイルが通るよう、`HomeScreen` の `onSettings` を消し、`SettingsScreen` に `onRideRecording = { backStack.add(RideRecordingKey) }` を足し、`@Serializable data object RideRecordingKey : NavKey` を置く（Task 6 で書き直す）。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*HomeScreenTest' --tests '*SettingsScreensTest' --tests '*RideScreensTest' --rerun > /tmp/trv2-t5.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t5.log`
Expected: `BUILD SUCCESSFUL`（`SettingsScreensTest` 9件・`RideScreensTest` 10件・`HomeScreenTest` は件数が変わらない）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/TabBar.kt app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt \
  app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt app/src/main/java/com/touringproject/v2/ui/RideScreens.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt app/src/test/java/com/touringproject/v2/ui/RideScreensTest.kt
git commit -m "feat: add the tab bar, the ride recording setting and keep typed ride names"
```

---

### Task 6: タブの組み込み（AppUi）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ui/AppUi.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt`（新規）

**Interfaces:**
- Consumes: `TabStacks`・`Tab`・`tabsShown`（Task 4）・`TabBar`・`RecordsPlaceholder`・`RideRecordingScreen`（Task 5）・`RideController.pause/resume/start/maxRecordingChanged`（Task 1）
- Produces: `@Serializable data object RecordsKey : NavKey`。画面の振る舞い（spec §7.1・計画の「決めたこと」）

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt`:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.touringproject.v2.MainActivity
import com.touringproject.v2.TouringApp
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AppUiTest {
  @get:Rule val rule = createAndroidComposeRule<MainActivity>()

  @Before
  fun ready() {
    (rule.activity.application as TouringApp).graph.permissionsAnswered()
    rule.waitUntil(5_000) { rule.onAllNodesWithTagExists("tab-HOME") }
  }

  private fun back() = rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }

  @Test
  fun back_goes_back_within_settings_then_to_home() {
    rule.onNodeWithTag("tab-SETTINGS").performClick()
    rule.onNodeWithText("回答の音量").performClick()
    rule.onNodeWithText("回答の音声を上げる量").assertExists()
    back()
    rule.onNodeWithText("走行の記録").assertExists()
    back()
    rule.onNodeWithTag("tapToTalk").assertExists()
  }

  @Test
  fun the_records_tab_says_its_list_comes_later_and_home_keeps_its_place() {
    rule.onNodeWithTag("tab-RECORDS").performClick()
    rule.onNodeWithText("走行と日ごとの記録の一覧は、次の版でここに出ます。").assertExists()
    rule.onNodeWithTag("tab-HOME").performClick()
    rule.onNodeWithTag("tapToTalk").assertExists()
  }

  @Test
  fun the_user_chip_opens_the_user_name_in_the_settings_tab() {
    val graph = (rule.activity.application as TouringApp).graph
    rule.onNodeWithText(graph.settings.current().userName).performClick()
    rule.onNodeWithTag("tab-SETTINGS").assertExists()
    back()
    rule.onNodeWithText("走行の記録").assertExists()
  }

  @Test
  fun the_start_sheet_stays_open_when_the_activity_is_recreated() {
    rule.onNodeWithTag("startRide").performClick()
    rule.onNodeWithTag("startGo").assertExists()
    rule.activityRule.scenario.recreate()
    rule.waitUntil(5_000) { rule.onAllNodesWithTagExists("startGo") }
  }
}

private fun androidx.compose.ui.test.junit4.AndroidComposeTestRule<*, *>.onAllNodesWithTagExists(tag: String) =
  onAllNodes(androidx.compose.ui.test.hasTestTag(tag)).fetchSemanticsNodes().isNotEmpty()
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AppUiTest' > /tmp/trv2-t6.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t6.log | head -6`
Expected: 4件とも失敗（`tab-HOME` が無いので `@Before` の待ちが時間切れになる）

- [ ] **Step 3: 実装する**

`AppUi` を次のとおりにする。

- バックスタックを3本（`rememberNavBackStack(HomeKey)`・`(RecordsKey)`・`(SettingsKey)`）と、`var selectedTab by rememberSaveable { mutableStateOf(Tab.HOME) }` を持ち、`remember(3本) { TabStacks(mapOf(...), { selectedTab }, { selectedTab = it }) }` を作る。
- `BackHandler(enabled = tabs.current.size == 1 && tabs.tab != Tab.HOME) { tabs.back() }` を `NavDisplay` より前に置く（スタックの中の Back は `NavDisplay` が持ち、最初の画面では `NavDisplay` の受け口が外れるので、こちらが受ける。ホームの最初の画面ではどちらも外れ、エミュレーターのテストの `hasEnabledCallbacks()` の待ちも今までどおり false になる）。
- `Scaffold(containerColor = MaterialTheme.colorScheme.background, bottomBar = { if (tabsShown(state.phase)) TabBar(tabs.tab, tabs::press) }) { inner -> NavDisplay(backStack = tabs.current, onBack = { if (!tabs.back()) activity?.finish() }, modifier = Modifier.padding(inner).consumeWindowInsets(inner), ...) }`。`activity` は `LocalActivity.current`。中身は1段字下げする。
- ホーム: `onUser = { tabs.open(Tab.SETTINGS, UserKey) }`・`onBanner = { tabs.open(Tab.SETTINGS, if (it == Banner.NO_KEY) ConnectionKey else ReturnAppKey) }`。
- 一時停止・再開: `scope.launch { if (graph.rides.pause()) Toast(...「一時停止しました」) }`、再開も同じ（コメント `// Only a change that happened is told (Android #19).`）。SC-17 の開始: `if (!graph.rides.start(name)) Toast(...「走行を開始できませんでした」)`。
- `entry<RecordsKey> { RecordsPlaceholder(Modifier.safeDrawingPadding()) }`。設定の一覧の各行は `tabs.current.add(...)`。`entry<RideRecordingKey>` は `RideRecordingScreen(current, { next -> scope.launch { graph.settings.update(next); graph.rides.maxRecordingChanged() } }, Modifier.safeDrawingPadding())`（コメント `// The recording ride's deadline follows at once (US-C-08.005).`）。
- `var sheet by rememberSaveable { mutableStateOf<RideSheet?>(null) }`（コメント `// Saveable: SC-17 and SC-04 stay open when the activity is recreated, e.g. on rotation (Android #20).`）。
- シートと `AskOverlay` は、今までどおり `Scaffold` の外（`Box` の中）に置く。

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AppUiTest' --tests '*MainActivityTest' --rerun > /tmp/trv2-t6.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-t6.log`
Expected: `BUILD SUCCESSFUL`（`AppUiTest` 4件・`MainActivityTest` 2件）

- [ ] **Step 5: シートの直しが効いていることを確かめる**

`var sheet by rememberSaveable` を一時的に `remember` に戻して `AppUiTest` を回し、`the_start_sheet_stays_open_when_the_activity_is_recreated` だけが落ちることを見てから、`rememberSaveable` に戻す。

- [ ] **Step 6: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/AppUi.kt app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
git commit -m "feat: give Home, Records and Settings their own tabs and back stacks" -m "Fixes #19" -m "Fixes #20"
```

---

### Task 7: 版と文書

**Files:**
- Modify: `app/build.gradle.kts`・Android の `README.md`

- [ ] **Step 1: 版を上げる**

`versionCode = 3`・`versionName = "0.3.0"`。

- [ ] **Step 2: README を直す**

「構成」の表の `.../ui/` の行を、次に置き換える:

```markdown
| `.../ui/` | 画面（Compose）。タブとバックスタックの組は `Tabs.kt`（Compose に依存しない）、タブの帯は `TabBar.kt` |
```

「大事な決まり」の `RideController` の行の最後に足す: 「最長時間を変えたときの締め切りの計算し直しも `maxRecordingChanged()` が行う（設定の画面が呼ぶ）。」

- [ ] **Step 3: コミット**

```bash
cd $AND && git add app/build.gradle.kts README.md
git commit -m "chore: raise the version to 0.3.0 and describe the tabs"
```

---

### Task 8: 全体の確かめ

- [ ] **Step 1: JVM のテスト・ビルド・権限**

```bash
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-full.log 2>&1; grep -E "FAILED|BUILD" /tmp/trv2-full.log
grep -ho 'tests="[0-9]*"' app/build/test-results/testDebugUnitTest/*.xml | grep -o '[0-9]*' | paste -sd+ - | bc
./gradlew assembleDebug assembleRelease > /tmp/trv2-build.log 2>&1; grep -E "BUILD|FAILED" /tmp/trv2-build.log
scripts/check-release-permissions.sh
```

Expected: `BUILD SUCCESSFUL`・320件・`BUILD SUCCESSFUL`・`release permissions OK (15)`

- [ ] **Step 2: エミュレーターのテスト**

利用者に触らないよう頼んでから:

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
export ANDROID_SERIAL=emulator-5554
cd $AND && ./gradlew connectedDebugAndroidTest > /tmp/trv2-emu.log 2>&1; grep -E "BUILD|FAILED" /tmp/trv2-emu.log
grep -ho 'tests="[0-9]*" failures="[0-9]*" errors="[0-9]*" skipped="[0-9]*"' app/build/outputs/androidTest-results/connected/debug/*.xml
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: `tests="4" failures="0" errors="0" skipped="0"`

---

### Task 9: 利用者の実機の確認

AI はこの Task を自分で通さない。

- [ ] **Step 1: 走行用のビルドを入れる（AI が行う。実機を USB で繋いでもらう）**

```bash
unset ANDROID_SERIAL
cd $AND && ./gradlew assembleRelease > /tmp/trv2-rel.log 2>&1; tail -1 /tmp/trv2-rel.log
scripts/check-release-permissions.sh
adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

Expected: `Success`・`versionName=0.3.0`

- [ ] **Step 2: 利用者に確かめてもらう（走らなくてよい。家の中で）**

| # | 操作 | 期待 |
|---|---|---|
| 1 | アプリを開く | 下に「ホーム・記録・設定」のタブ。ホームの右上に「⚙ 設定」が無い。ホームがスクロールせず、新しい会話の大きなボタンまで見える |
| 2 | 設定 → バージョン | `0.3.0` |
| 3 | 設定 → 回答の音量 → ホームのタブ → 設定のタブ | 回答の音量の画面のまま。もう一度設定のタブを押すと、設定の一覧に戻る |
| 4 | 設定の一覧で Back | ホームのタブに移る。ホームで Back を押すとアプリが閉じる |
| 5 | 記録のタブ | 「走行と日ごとの記録の一覧は、次の版でここに出ます。」 |
| 6 | ホームのユーザー名を押す | 設定のタブでユーザー名の画面が出る。Back で設定の一覧 |
| 7 | 設定 → 走行の記録 | 「連続して記録できる最長時間」と 6・12・24・48 時間。24時間が選ばれている。12時間を選んで戻ると、一覧に「最長 12時間」 |
| 8 | 走行を開始し、1回質問する（家の中でよい） | 質問のあいだはタブが隠れる。回答のあと、カードの「質問」が 1 になる |
| 9 | 「⏸ 一時停止」→「▶ 再開」 | それぞれトーストが1回だけ出る |
| 10 | 「■ 終了」を押し、名前を少し変えてから端末を横にする | シートが開いたまま、変えた名前が残る。要約に質問の数が出る |
| 11 | 「終了して保存」 | ホームに戻る |
| 12 | 設定 → 走行の記録を 24時間に戻す | 一覧に「最長 24時間」 |

締め切りを過ぎたときの扱い（最長時間を短くして過ぎた・締め切りのあとの一時停止と終了）は、最短でも6時間かかるので実機では確かめない（Task 1 の JVM のテストで確かめた）。

- [ ] **Step 3: 結果を記録する**

✗ があれば `superpowers:systematic-debugging`。✓ になったら、PROJECT.md の区切り点の作業に進む。
