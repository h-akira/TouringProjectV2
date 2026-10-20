# スライス2 計画4a: 地図と、走行から入る振り返り（SC-05・SC-06・SC-07）実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 記録のタブに走行の一覧（保存の状態つき）が出る。走行を開くと、国土地理院の淡色地図に、ルート・一時停止の破線・出発と到着の印・質問の番号のピンが描かれる。ピンや時系列から会話の詳細（SC-07）へ進み、走行の中で前後の会話へ移れる。走行の名前を変えられる。

**Architecture:** 地図は MapLibre Native Android の `MapView` を `AndroidView` で包んだ `map/RouteMap.kt` 1つで、描くデータ（GeoJSON）は `map/MapData.kt` の純粋な関数で組み立てる。画面（`ui/RecordsScreens.kt`）は地図を差し替えられる枠（`MapSlot`）で受けるので、JVM のテストは作り物の地図で回し、MapLibre はエミュレーターで確かめる。記録の読み出しは `store/RoomRecords.kt`（Room の `Flow`）、表示の文字の組み立ては `ui/RecordLabels.kt`（純粋）、両者のつなぎは `ui/RecordsRoutes.kt`。走行の状態を変えるのは引き続き `RideController` だけで、名前の変更も `rename()` で行う。タブごとに画面の状態の置き場を分ける（`rememberDecoratedNavEntries`）。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Navigation 3 1.0.1・Room 2.8.4（版3）・Robolectric 4.16（SDK 35）。足す依存は MapLibre Native Android 13.6.1（`org.maplibre.gl:android-sdk`）と、エミュレーターのテスト用の `ui-test-junit4`。

**Spec:** [docs/specs/2026-10-17-slice2-design.md](../specs/2026-10-17-slice2-design.md)（§5.1・§5.4・§7.1・§7.3〜§7.8・§9・§11・§12）。見た目と文言は [画面モック](../mock/index.html) の SC-05・SC-06・SC-07。決定の記録は [adr/0007](../../adr/0007-stay-home-after-ending-a-ride.md)。

**範囲に入れた issue（Android）:** #27（ルートのかたまりが断られた印が下りない）・#32（ホームの最初の画面での Back の finish の枝）・#33（SC-16 で選んだ直後に画面が壊れると締め切りが変わらない）・#34（タブを切り替えると打ち込み途中の値が消える）・#35（作り直すたびに質問の数が一瞬 0）・#36（タブ・SC-16 のテストの不足）・#37（タブと設定の細かな整理）。

**前提:** Android の `main`（`23fad5f`。版 0.3.1。plan 3a・3b と #38 の修正を含む）の上に作る。親はこの plan を書いたブランチ `slice2-plan4a`。

**計画を書くときに決めたこと（spec からの具体化。利用者と決めたものを含む）:**
- plan 4 を 4a（地図の部品と、走行から入る振り返り）と 4b（日ごとの振り返り）に分けた。いちばん危うい地図を 4a で先に実機で確かめ、どちらも実機で触れる形で終えるため（利用者と決めた）。4a の SC-05 は走行の一覧だけで、「走行／日ごと」の切り替えと日の行は 4b で足す。
- 「終了して保存」のあとはホームに残る（今の動きのまま）。モックと遷移図の「その走行の SC-06 を開く」はやめ、文書を直した（利用者と決めた。adr/0007）。
- ホームの最初の画面での Back は、アプリが受けずにシステムの既定（Android 12 以降はアプリを背面に回す）に任せる。`activity?.finish()` の枝と `LocalActivity` を消す（#32。利用者と決めた）。
- 地図は `MapView` を `AndroidView` で包む。使い捨てのフォルダで組んで足りたので、`maplibre-compose` は使わない（spec §12 の答え）。MapLibre は 13.6.1（公開から約6週。13.7.1 は公開から5日だったので避けた）。ABI は `arm64-v8a` に絞る。
- 番号のピンは、Android の `Canvas` で描いた画像（番号ごと・選んだときの色ごと）を地図のスタイルに足し、`SymbolLayer` の `icon-image` で出す。文字（グリフ）を地図に同梱しないため。出発と到着は `CircleLayer`、ルートと一時停止の破線は `LineLayer`。
- 出典は、MapLibre の出典ボタンとロゴを消し、地図の右下に「地理院タイル」を出す。押すと国土地理院のタイル一覧のページを開く（国土地理院の決まり: 出典の明示とそのページへのリンク）。タイルはズーム2〜18。
- ダークモードでは、ラスタの明るさの上限を 0.55、彩度を -0.4 にして暗くする（反転はしない）。
- MapLibre が持ち込む `ACCESS_WIFI_STATE` は、マニフェストで外す（MapLibre のコードに Wi-Fi の状態を読む処理は無い）。release の権限の許す一覧は広げない。
- `queryRenderedFeatures` は、地図が一度描き終える前に呼ぶとネイティブのコードが落ちる。テストへ地図を渡す `onMap` は、描き終えて落ち着いたとき（`OnDidBecomeIdle`）に一度だけ呼ぶ。
- 地図のカメラは、最初に場所が届いたときに全体（ルートとピン）が収まる縮尺に合わせ、そのあとは利用者の動かしたまま。場所が一つも無いあいだは日本全体を出す。SC-07 は、その質問の地点に寄せて開く（`MapData.focus`）。
- 断られたかたまりは、そのかたまりの点の `route_points.refused` に持つ（Room の版3）。同じ番号で送り直して受け付けられたら下りる（#27）。版2の `rides.routeRejected` は書かなくなるが、列は残す（消すと、区間と点が参照する表を作り直すことになるため）。版2で印が立っていた走行は、送った点をすべて「断られた」として移す（どのかたまりかが分からないので、「保存済み」と誤って出さない側に倒す）。
- 保存の状態（spec §5.4）: 記録中・一時停止中は「記録中」。終わった走行は、最新の版が受け付けられていない（断られた版を含む）か、送っていない点か断られた点があれば「未送信あり」、ほかは「保存済み」。一覧は、記録中・一時停止中の走行を一番上に、ほかは始めた時刻の新しい順。始めた月ごとに見出しを入れる。
- 一覧の行: 名前・日付（泊まりがけは「10月16日〜18日（2泊）」）と時刻（記録中は「08:58〜」）・距離・走行時間・質問の数・一時停止の回数（あるときだけ）・保存の状態。一覧の上の保存の状態のまとめ（モックの SC-14 への入口）はスライス3。
- SC-06: 上に地図（高さ280dp）、下に要約と時系列。メニューは「名前を変える」だけ（ダイアログ。空にはできない。40文字まで）。自動で終了した走行は要約に「最長時間に達したため、自動で終了しました」。記録中の走行は「記録中の走行です。ルートは開いたときまでのものです。」（ルートは開いたときに一度だけ読む。点が入るたびに地図を描き直さない）。ピンの表示・非表示は設定（`Settings.showAskPins`、既定は表示）に残す。
- 時系列: 質問（番号・時刻・場所・聞き取った文。聞き取れなかったものは理由の短い文）・一時停止（「⏸ 一時停止 09:44〜10:02（18分）」。日をまたぐと「⏸ 一時停止 21:10〜10月17日 08:30」）・会話の区切り（「↻ ここから新しい会話」。最初の質問の前には出さない）。日をまたぐ走行は日付の見出しを入れる。一時停止中の走行は最後に「⏸ 一時停止中 12:00〜」。番号は質問した順で、地図のピンと同じ。場所が無い質問はピンを立てないが、番号は飛ばさない。
- SC-07: 見出しは「会話 3 / 5」、‹ › で走行の中の前後へ移る（バックスタックの一番上を入れ替えるので、Back は SC-06 へ戻る）。日時・場所・進行方向（「北東へ走行中（右手 南東・左手 北西）」。方位が無ければ「停車中」）・入力の種類・質問・回答。失敗した質問は「答えられませんでした: 理由」。場所が無い質問は小さな地図の代わりに「この質問の場所は分かりません。」。モックの「会話の文脈の何問目か」は出さない（spec §7.6 に無い）。
- 地図を全画面にしているあいだは、タブの帯を隠す（`AppUi` の `mapFull`）。全画面は ✕ か Back で戻る。
- #33: 最長時間の変化は `AppGraph` が設定の `Flow` で受けて `RideController.maxRecordingChanged()` を呼ぶ（最初に読み込んだ値では呼ばない）。SC-16 の画面は設定を保存するだけ。
- #35: 記録中の走行の質問の数は、`AppGraph` が `StateFlow`（`activeAskCount`）で持つ。
- #34: タブごとに `rememberDecoratedNavEntries` と `rememberSaveableStateHolderNavEntryDecorator` で状態の置き場を分ける。ユーザー名の欄は `rememberSaveable` にする。接続キーの欄は、保存される状態（Bundle）にキーを載せないため `remember` のまま。
- #37: `TabStacks.canGoBack` を `onAnotherTabsFirst` に置き換えて `BackHandler` で使う。README の余分な空白を消す。spec §7.8 の文言を今の設定の一覧に合わせる（親の文書。この plan を書いたコミットで直した）。
- #36: 設定の奥からユーザー名を開く画面のテスト・最長時間を 24→6→48 と続けて変えるテスト・質問のあいだにタブの帯が隠れる画面のテストを足す。
- 版を 0.4.0（`versionCode` 5）に上げる（Android の README の決まり）。

この計画のコードは、使い捨てのフォルダで、次の順に確かめてから書いた。

- タスクの順に一つずつ当てて、各タスクでテストが先に落ち、実装のあとに通ることを確かめた。
- 最後に `clean` から、次が通ることを確かめた。
  - JVM のテスト366件（始める前の325件＋41件）
  - エミュレーターのテスト5件
  - `assembleDebug`
  - `assembleRelease`（lint を含む）
  - `scripts/check-release-permissions.sh`（15件）

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice2-plan4a` を切る（Task 0）。親は `slice2-plan4a`（この plan のコミットがある）。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- 作りの決まり（移行の spec §5）: 状態機械と司令塔は Android に依存させない。部品は `AppGraph` で手で組む。走行の状態（名前を含む）を変えるのは `RideController` だけ。地図に渡すデータと画面の文字は純粋な関数で組み立てる。
- 地図: 国土地理院の淡色地図（`https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png`、ズーム2〜18）。出典の表示とタイル一覧のページへのリンクを外さない。
- Room のスキーマは版を上げて Migration を書き、`app/schemas/` の JSON をコミットする。破壊的な作り直しは使わない（spec §5.1）。
- ホームは全体がスクロールしない（spec §7.2）。この plan ではホームの見た目を変えない。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --tests '*クラス名'`。テストを確かめるときは `--rerun` を付ける（使い捨てのフォルダで同じ入力を通したので、ビルドキャッシュから結果が返ることがある）。
- **Kotlin の差分コンパイルは、interface に足したメソッドを実装していない作り物のテストを見逃すことがある**（使い捨てのフォルダで、`RoomAskLogTest` の作り物の `AskDao` がそれで通ってしまった）。Task 11 は `./gradlew clean` から回す。
- Room のスキーマの版を新しく足した直後の1回目は「Missing file 3.json」で落ち、2回目で通る（Task 1）。
- `ScreensTest.kt` の中のクラスは `HomeScreenTest`・`SettingsScreensTest` などなので、クラスの名前で指す。
- Robolectric の決まり（SDK 35・`withContext(Dispatchers.Main)` を直に呼ばない・`backgroundScope` は `advanceUntilIdle` で進まない。`runCurrent` で進める）。Robolectric の画面は小さい（地図の下の時系列は `performScrollToNode` で出す）。`@Config(qualifiers = ...)` で画面を大きくすると、ポップアップ（メニュー・ダイアログ）のテストが止まらなくなる（メモリが尽きる）ので使わない。MapLibre は Robolectric では動かない。
- エミュレーター: `$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone`（止めるときは `stop`）。実機が繋がっているときは `export ANDROID_SERIAL=emulator-5554`。テストのあいだは利用者にエミュレーターに触らないよう頼む。
- 子を持つ欄（`Stat` の Column）に付けたタグの文字は、`onChildAt(0).assertTextEquals(...)` で見る。押せる行（`clickable`）の中のタグの付いた文字は `useUnmergedTree = true` で探す。

## Review Focus

- 一時停止で送った端数のかたまりが断られ、あとで同じ番号で満ちたかたまりが受け付けられる → 一覧は「保存済み」になる（「未送信あり」のまま残らない）。Task 1 の `a_chunk_taken_under_the_seq_of_a_refused_one_clears_the_refusal`・Task 3 の `a_refused_chunk_keeps_the_ride_unsent_until_its_seq_is_taken`。
- 泊まりがけの走行（夜に一時停止して翌朝再開）や、一時停止中の走行を開く → 時系列に日付の見出しと日をまたぐ一時停止の行が出て、一時停止中なら最後に「一時停止中」が出る。Task 5 の `a_ride_over_a_night_gets_a_heading_per_day_and_a_paused_one_ends_with_its_pause`。
- 場所が取れなかった質問がある走行 → その質問はピンを立てないが、ほかのピンと時系列の番号はずれない。SC-07 は「この質問の場所は分かりません。」と出す。Task 5 の `pins_are_numbered_like_the_timeline_and_an_ask_without_a_place_has_none`・Task 7 の `the_ask_detail_moves_to_its_neighbours_and_tells_why_an_ask_failed`。
- 地図を全画面にしてから端末の Back → 全画面が閉じて走行の詳細に戻り、タブの帯も戻る（一覧へは戻らない）。Task 7 の `the_map_fills_the_screen_until_back_and_tells_so`。
- 設定のタブでユーザー名を打ちかけたまま、ほかのタブへ移って戻る → 打ちかけの文字が残る。Task 9 の `a_name_being_typed_survives_a_trip_to_another_tab`。
- 地図が描き終わる前にピンの問い合わせをする → 落ちない（地図をテストへ渡すのは描き終えてから）。Task 6 の `the_route_and_the_pins_are_drawn_and_a_tap_on_a_pin_names_its_ask`（エミュレーター）。

---

## ファイル構成（`Android/` から。`...` は `app/src/main/java/com/touringproject/v2`）

| パス | 役割 | Task |
|---|---|---|
| `.../store/RideDatabase.kt`・`.../store/RoomSyncStore.kt`・`app/schemas/.../3.json` | 断られたかたまりを点ごとに持つ（版3）（#27） | 1 |
| `.../ride/Ride.kt`・`ride/RidePorts.kt`・`ride/RideController.kt`・`store/RoomRideStore.kt` | 名前の変更（`rename`） | 2 |
| `.../records/Records.kt`（新規）・`store/RoomRecords.kt`（新規）・`store/RideDatabase.kt` | 保存の状態・一覧の並べ方・記録の読み出し | 3 |
| `.../map/MapData.kt`（新規） | 地図に描くデータと GeoJSON | 4 |
| `.../ui/RecordLabels.kt`（新規） | 一覧の行・要約・時系列・会話の詳細・ピンのカードの文字 | 5 |
| `.../map/RouteMap.kt`（新規）・`app/src/main/assets/map/gsi-pale.json`（新規）・`app/build.gradle.kts`・`gradle/libs.versions.toml`・`app/src/main/AndroidManifest.xml` | MapLibre の地図の部品 | 6 |
| `.../ui/RecordsScreens.kt`（新規） | SC-05・SC-06・SC-07 の画面 | 7 |
| `.../AppGraph.kt`・`settings/Settings.kt`・`records/Records.kt`・`ui/AppUi.kt` | 記録の読み出しの組み込み・ピンの表示の設定・#33・#35 | 8 |
| `.../ui/RecordsRoutes.kt`（新規）・`ui/AppUi.kt`・`ui/Tabs.kt`・`ui/TabBar.kt`・`ui/SettingsScreens.kt` | 記録のタブの組み込み・全画面でタブを隠す・#32・#34・#36・#37 | 9 |
| `app/build.gradle.kts`・`README.md`・`docs-parent/` | 版 0.4.0・文書・親の文書の写し | 10 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android に `slice2-plan4a` を切り、始める前のテストの件数を見る**

```bash
cd $ROOT && git branch --show-current          # slice2-plan4a
cd $AND && git switch main && git pull --ff-only && git switch -c slice2-plan4a
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-base.log 2>&1; tail -3 /tmp/trv2-base.log
```

Expected: `BUILD SUCCESSFUL`。結果のファイルの件数の合計は325件。

---
### Task 1: 断られたかたまりを点ごとに持つ（#27）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/store/RideDatabase.kt`・`app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt`
- Create（生成）: `app/schemas/com.touringproject.v2.store.RideDatabase/3.json`
- Test: `app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt`・`app/src/test/java/com/touringproject/v2/store/MigrationTest.kt`

**Interfaces:**
- Produces: `RoutePointEntity.refused: Boolean`（既定 false）・`RideDao.markChunk(rideId, seq, from, count, refused: Boolean)`・`MIGRATION_2_3`・`RideDatabase` の版3。`RideDao.markRouteRefused` は消す。

- [ ] **Step 1: 失敗するテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt b/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
index 061c647..a60eaf3 100644
--- a/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
@@ -8,7 +8,6 @@ import androidx.test.ext.junit.runners.AndroidJUnit4
 import androidx.test.platform.app.InstrumentationRegistry
 import kotlinx.coroutines.runBlocking
 import org.junit.Assert.assertEquals
-import org.junit.Assert.assertFalse
 import org.junit.Assert.assertNull
 import org.junit.Rule
 import org.junit.Test
@@ -31,17 +30,39 @@ class MigrationTest {
     }
     helper.runMigrationsAndValidate(DB, 2, true, MIGRATION_1_2).close()
     val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
-      .addMigrations(MIGRATION_1_2)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3)
       .allowMainThreadQueries()
       .build()
     runBlocking {
       val ride = db.rides().ride("r1")!!
       assertEquals(6_000L, ride.sentUpdatedAt)
       assertNull(ride.rejectedUpdatedAt)
-      assertFalse(ride.routeRejected)
       assertEquals(1, db.rides().points("r1").size)
       assertNull(db.asks().ask("a1"))
     }
     db.close()
   }
+
+  // Android #27: which chunk a version 2 ride had refused is not known, so its sent points all count as refused.
+  @Test
+  fun version_2_moves_to_3_marking_the_sent_points_of_a_ride_whose_route_was_refused() {
+    helper.createDatabase(DB, 2).apply {
+      execSQL("INSERT INTO rides VALUES ('r1', '箱根', 'ended', 'manual', NULL, 5000, 120.0, 6000, 6000, NULL, 1)")
+      execSQL("INSERT INTO rides VALUES ('r2', '御殿場', 'ended', 'manual', NULL, 5000, 80.0, 6000, 6000, NULL, 0)")
+      execSQL("INSERT INTO route_points (rideId, segment, t, lat, lon, accuracy, chunk) VALUES ('r1', 0, 2000, 35.0, 139.0, 5.0, 0)")
+      execSQL("INSERT INTO route_points (rideId, segment, t, lat, lon, accuracy, chunk) VALUES ('r1', 0, 3000, 35.0, 139.0, 5.0, NULL)")
+      execSQL("INSERT INTO route_points (rideId, segment, t, lat, lon, accuracy, chunk) VALUES ('r2', 0, 2000, 35.0, 139.0, 5.0, 0)")
+      close()
+    }
+    helper.runMigrationsAndValidate(DB, 3, true, MIGRATION_2_3).close()
+    val db = Room.databaseBuilder(ApplicationProvider.getApplicationContext(), RideDatabase::class.java, DB)
+      .addMigrations(MIGRATION_1_2, MIGRATION_2_3)
+      .allowMainThreadQueries()
+      .build()
+    runBlocking {
+      assertEquals(listOf(true, false), db.rides().points("r1").map { it.refused })
+      assertEquals(listOf(false), db.rides().points("r2").map { it.refused })
+    }
+    db.close()
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
index 26af108..af4dd55 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt
@@ -21,7 +21,6 @@ import okhttp3.mockwebserver.MockResponse
 import okhttp3.mockwebserver.MockWebServer
 import org.junit.After
 import org.junit.Assert.assertEquals
-import org.junit.Assert.assertTrue
 import org.junit.Test
 import org.junit.runner.RunWith
 
@@ -73,11 +72,24 @@ class RoomSyncStoreTest {
   }
 
   @Test
-  fun a_refused_chunk_marks_the_ride() = runBlocking {
+  fun a_refused_chunk_marks_its_points_and_is_not_sent_again() = runBlocking {
+    rides.save(ride)
+    store.rideSent("r1", ride.updatedAt)
+    addPoints(2)
+    store.chunkSent("r1", ChunkRange(0, 0, 2), refused = true)
+    assertEquals(listOf(true, true), dao.points("r1").map { it.refused })
+    assertEquals(emptyList<String>(), store.unsent().map { it.ride.id })
+  }
+
+  // Android #27: the partial chunk sent at a pause was refused, the full one under the same seq is taken later.
+  @Test
+  fun a_chunk_taken_under_the_seq_of_a_refused_one_clears_the_refusal() = runBlocking {
     rides.save(ride)
     addPoints(2)
     store.chunkSent("r1", ChunkRange(0, 0, 2), refused = true)
-    assertTrue(dao.ride("r1")!!.routeRejected)
+    addPoints(1)
+    store.chunkSent("r1", ChunkRange(0, 0, 3), refused = false)
+    assertEquals(listOf(false, false, false), dao.points("r1").map { it.refused })
   }
 
   @Test
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*.store.*'`
Expected: コンパイルの失敗（`Unresolved reference 'MIGRATION_2_3'`・`Unresolved reference 'refused'`）。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index 064bcb5..ae4ac27 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -37,7 +37,11 @@ data class RideEntity(
   val sentUpdatedAt: Long?,
   /** The updatedAt the Backend refused with 400; that version is not sent again (slice 2 spec §5.3). */
   val rejectedUpdatedAt: Long? = null,
-  /** True once the Backend has refused one of the ride's route chunks with 400. */
+  /**
+   * Version 2's mark of a refused route chunk. No longer written: a refusal is kept on the chunk's points
+   * ([RoutePointEntity.refused], Android #27). The column stays, because dropping it would rebuild the table its
+   * segments and points refer to.
+   */
   @ColumnInfo(defaultValue = "0") val routeRejected: Boolean = false,
 )
 
@@ -51,7 +55,7 @@ data class SegmentEntity(val rideId: String, val seq: Int, val startedAt: Long,
 @Entity(
   tableName = "route_points",
   // chunk first: finding the rides with points left to send reads only the unsent ones (slice 2 plan 3a).
-  indices = [Index(value = ["rideId", "segment", "t"]), Index(value = ["chunk", "rideId"])],
+  indices = [Index(value = ["rideId", "segment", "t"]), Index(value = ["chunk", "rideId"]), Index(value = ["refused", "rideId"])],
   foreignKeys = [ForeignKey(entity = RideEntity::class, parentColumns = ["id"], childColumns = ["rideId"], onDelete = ForeignKey.CASCADE)],
 )
 data class RoutePointEntity(
@@ -64,6 +68,8 @@ data class RoutePointEntity(
   val accuracy: Double?,
   /** The seq of the chunk it was sent in (slice 2 plan 3); null until then. */
   val chunk: Int?,
+  /** True while the Backend has refused that chunk with 400; it is not sent again unless the chunk grows (Android #27). */
+  @ColumnInfo(defaultValue = "0") val refused: Boolean = false,
 )
 
 /** An ask whose loop ended with an answer or a failure the Backend reported (slice 2 spec §5.2). */
@@ -158,11 +164,12 @@ interface RideDao {
   @Query("SELECT * FROM route_points WHERE rideId = :rideId ORDER BY id LIMIT :count OFFSET :from")
   suspend fun pointsFrom(rideId: String, from: Int, count: Int): List<RoutePointEntity>
 
+  /** A chunk sent again under the same seq overwrites what the Backend said of it the time before (Android #27). */
   @Query(
-    "UPDATE route_points SET chunk = :seq WHERE id IN " +
+    "UPDATE route_points SET chunk = :seq, refused = :refused WHERE id IN " +
       "(SELECT id FROM route_points WHERE rideId = :rideId ORDER BY id LIMIT :count OFFSET :from)",
   )
-  suspend fun markChunk(rideId: String, seq: Int, from: Int, count: Int)
+  suspend fun markChunk(rideId: String, seq: Int, from: Int, count: Int, refused: Boolean)
 
   /** A later save of an older version (none is made today) cannot move the marker back. */
   @Query("UPDATE rides SET sentUpdatedAt = :updatedAt WHERE id = :rideId AND (sentUpdatedAt IS NULL OR sentUpdatedAt < :updatedAt)")
@@ -171,9 +178,6 @@ interface RideDao {
   @Query("UPDATE rides SET rejectedUpdatedAt = :updatedAt WHERE id = :rideId")
   suspend fun markRefused(rideId: String, updatedAt: Long)
 
-  @Query("UPDATE rides SET routeRejected = 1 WHERE id = :rideId")
-  suspend fun markRouteRefused(rideId: String)
-
   /** Keeps the sending markers: a save never undoes what the Backend has already accepted or refused. */
   @Transaction
   suspend fun saveRide(ride: RideEntity, segments: List<SegmentEntity>) {
@@ -192,14 +196,14 @@ interface RideDao {
   }
 }
 
-@Database(entities = [RideEntity::class, SegmentEntity::class, RoutePointEntity::class, AskEntity::class], version = 2, exportSchema = true)
+@Database(entities = [RideEntity::class, SegmentEntity::class, RoutePointEntity::class, AskEntity::class], version = 3, exportSchema = true)
 abstract class RideDatabase : RoomDatabase() {
   abstract fun rides(): RideDao
   abstract fun asks(): AskDao
 
   companion object {
     fun open(context: Context): RideDatabase =
-      Room.databaseBuilder(context, RideDatabase::class.java, "rides.db").addMigrations(MIGRATION_1_2).build()
+      Room.databaseBuilder(context, RideDatabase::class.java, "rides.db").addMigrations(MIGRATION_1_2, MIGRATION_2_3).build()
   }
 }
 
@@ -223,3 +227,16 @@ val MIGRATION_1_2 = object : Migration(1, 2) {
     db.execSQL("CREATE INDEX IF NOT EXISTS `index_route_points_chunk_rideId` ON `route_points` (`chunk`, `rideId`)")
   }
 }
+
+/**
+ * 2 -> 3 (slice 2 plan 4a, Android #27): a refusal moves from the ride to the points of the refused chunk. Version 2
+ * did not keep which chunk was refused, so all the sent points of such a ride count as refused: the ride shows
+ * "未送信あり" rather than "保存済み". It only adds, like 1 -> 2.
+ */
+val MIGRATION_2_3 = object : Migration(2, 3) {
+  override fun migrate(db: SupportSQLiteDatabase) {
+    db.execSQL("ALTER TABLE `route_points` ADD COLUMN `refused` INTEGER NOT NULL DEFAULT 0")
+    db.execSQL("UPDATE `route_points` SET `refused` = 1 WHERE `chunk` IS NOT NULL AND `rideId` IN (SELECT `id` FROM `rides` WHERE `routeRejected` = 1)")
+    db.execSQL("CREATE INDEX IF NOT EXISTS `index_route_points_refused_rideId` ON `route_points` (`refused`, `rideId`)")
+  }
+}
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
index b9285c5..edbaf95 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt
@@ -17,8 +17,6 @@ class RoomSyncStore(private val dao: RideDao) : SyncStore {
 
   override suspend fun rideRefused(rideId: String, updatedAt: Long) = dao.markRefused(rideId, updatedAt)
 
-  override suspend fun chunkSent(rideId: String, chunk: ChunkRange, refused: Boolean) {
-    dao.markChunk(rideId, chunk.seq, chunk.from, chunk.until - chunk.from)
-    if (refused) dao.markRouteRefused(rideId)
-  }
+  override suspend fun chunkSent(rideId: String, chunk: ChunkRange, refused: Boolean) =
+    dao.markChunk(rideId, chunk.seq, chunk.from, chunk.until - chunk.from, refused)
 }
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*.store.*' --rerun` を2回。
Expected: 1回目は `MigrationTest` が「Missing file 3.json」で落ちる（テストの資産が先に集められるため）。2回目は `MigrationTest` 2件・`RoomSyncStoreTest` 6件を含む15件が通る。`app/schemas/com.touringproject.v2.store.RideDatabase/3.json` ができている。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/store/RideDatabase.kt app/src/main/java/com/touringproject/v2/store/RoomSyncStore.kt \
  app/schemas/com.touringproject.v2.store.RideDatabase/3.json \
  app/src/test/java/com/touringproject/v2/store/RoomSyncStoreTest.kt app/src/test/java/com/touringproject/v2/store/MigrationTest.kt
git commit -m "fix: keep a refused route chunk on its points so a later take clears it" -m "Fixes #27"
```

---
### Task 2: 走行の名前の変更（と #36 の最長時間のテスト）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/ride/Ride.kt`・`app/src/main/java/com/touringproject/v2/ride/RidePorts.kt`・`app/src/main/java/com/touringproject/v2/ride/RideController.kt`・`app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt`
- Test: `app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt`

**Interfaces:**
- Consumes: `rideName`（`Ride.kt`）・`RideController.locked`・`save`・`read`。
- Produces: `fun Ride.rename(name: String, now: Long): Ride`・`RideStore.ride(id: String): Ride?`・`suspend fun RideController.rename(rideId: String, name: String): Boolean`（使えない名前・残っていない走行は false。記録中の走行は名前だけ変わる。`updatedAt` が進み、送信の契機になる）。

- [ ] **Step 1: 失敗するテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
index ff278fd..f104858 100644
--- a/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
@@ -51,6 +51,7 @@ private class World(var now: Long = 1_000, var boot: Int? = 7) {
       }
       rides[ride.id] = ride
     }
+    override suspend fun ride(id: String): Ride? = rides[id]
     override suspend fun lastPoint(rideId: String) = points[rideId]?.lastOrNull()
     override suspend fun addPoint(rideId: String, point: RoutePoint, distanceMeters: Double, aliveAt: Long) {
       if (failWrites) throw IOException("disk full")
@@ -550,4 +551,58 @@ class RideControllerTest {
     w.controller.resume()
     assertEquals(9_000 + 6 * HOUR_MS, w.stored().deadline)
   }
+
+  // Android #36: each change works from the segment's start, and only the last one counts.
+  @Test
+  fun a_limit_changed_again_and_again_keeps_only_the_last_one() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5 * HOUR_MS
+    w.max = 6 * HOUR_MS
+    w.controller.maxRecordingChanged()
+    assertEquals(RideStatus.RECORDING, w.stored().status)
+    w.max = 48 * HOUR_MS
+    w.controller.maxRecordingChanged()
+    assertEquals(1_000 + 48 * HOUR_MS, w.stored().deadline)
+    assertEquals("alarm:${1_000 + 48 * HOUR_MS}", w.events.last())
+  }
+
+  @Test
+  fun an_ended_ride_can_be_renamed_and_the_new_name_is_sent() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    w.controller.end("箱根")
+    val before = w.stored()
+    val changes = w.changes
+    w.now = 9_000
+    assertTrue(w.controller.rename("r1", " 御殿場 "))
+    assertEquals("御殿場", w.stored().name)
+    assertEquals(9_000L, w.stored().updatedAt)
+    assertEquals(before.segments, w.stored().segments)
+    assertEquals(changes + 1, w.changes)
+  }
+
+  @Test
+  fun renaming_the_active_ride_keeps_it_recording_under_the_new_name() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    w.now = 5_000
+    assertTrue(w.controller.rename("r1", "御殿場"))
+    assertEquals("御殿場", w.controller.active.value?.name)
+    assertEquals(RideStatus.RECORDING, w.stored().status)
+  }
+
+  @Test
+  fun a_name_that_cannot_name_a_ride_or_a_ride_that_is_not_kept_is_not_renamed() = runTest {
+    val w = World()
+    w.controller.load()
+    w.controller.start("箱根")
+    assertFalse(w.controller.rename("r1", "  "))
+    assertFalse(w.controller.rename("r9", "御殿場"))
+    assertEquals("箱根", w.stored().name)
+  }
 }
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideControllerTest'`
Expected: コンパイルの失敗（`'ride' overrides nothing`・`Unresolved reference 'rename'`）。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ride/Ride.kt b/app/src/main/java/com/touringproject/v2/ride/Ride.kt
index 3999d73..034af88 100644
--- a/app/src/main/java/com/touringproject/v2/ride/Ride.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/Ride.kt
@@ -90,6 +90,9 @@ fun Ride.end(at: Long, reason: EndReason, now: Long, name: String = this.name):
   return copy(name = name, status = RideStatus.ENDED, segments = closeOpenSegment(at), endReason = reason, deadline = null, updatedAt = touched(now))
 }
 
+/** SC-04 and SC-06: a new name is a change the Backend takes, so updatedAt moves on. */
+fun Ride.rename(name: String, now: Long): Ride = copy(name = name, updatedAt = touched(now))
+
 /** The time spent recording; an open segment counts up to now (US-C-07.006). */
 fun Ride.recordedMs(now: Long): Long = segments.sumOf { (it.endedAt ?: maxOf(now, it.startedAt)) - it.startedAt }
 
diff --git a/app/src/main/java/com/touringproject/v2/ride/RideController.kt b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
index d1fcf4c..28adc97 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RideController.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RideController.kt
@@ -189,6 +189,25 @@ class RideController(private val deps: RideDeps) {
     true
   }
 
+  /**
+   * SC-06 (and SC-04 through end): gives any kept ride a new name. Returns false when the name is not usable or the
+   * ride is not kept. The active ride stays as it is but for its name.
+   */
+  suspend fun rename(rideId: String, name: String): Boolean = locked {
+    val clean = rideName(name) ?: return@locked false
+    val now = deps.now()
+    val active = activeRide.value
+    if (active?.id == rideId) {
+      val renamed = active.rename(clean, now)
+      save(renamed)
+      activeRide.value = renamed
+      return@locked true
+    }
+    val ride = read("ride") { deps.store.ride(rideId) } ?: return@locked false
+    save(ride.rename(clean, now))
+    true
+  }
+
   /**
    * SC-16: the longest recording time changed (US-C-08.005). The recording segment's deadline is worked out again from
    * its start; one already passed ends the ride automatically at that deadline. A paused ride takes the new time when
diff --git a/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt b/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt
index 0f89bcf..5b41763 100644
--- a/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt
+++ b/app/src/main/java/com/touringproject/v2/ride/RidePorts.kt
@@ -5,6 +5,8 @@ package com.touringproject.v2.ride
 interface RideStore {
   /** The ride that is recording or paused, if any (only one can be: US-C-01.005). */
   suspend fun active(): Ride?
+  /** Any kept ride, ended or not. */
+  suspend fun ride(id: String): Ride?
   /** Writes the ride and its segments. The sent marker of an earlier write is kept. */
   suspend fun save(ride: Ride)
   suspend fun lastPoint(rideId: String): RoutePoint?
diff --git a/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt b/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt
index f33676c..89b5d6a 100644
--- a/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt
@@ -29,6 +29,8 @@ fun RoutePointEntity.toPoint() = RoutePoint(segment, t, lat, lon, accuracy)
 class RoomRideStore(private val dao: RideDao) : RideStore {
   override suspend fun active(): Ride? = dao.active()?.let { it.toRide(dao.segments(it.id)) }
 
+  override suspend fun ride(id: String): Ride? = dao.ride(id)?.let { it.toRide(dao.segments(it.id)) }
+
   override suspend fun save(ride: Ride) =
     dao.saveRide(ride.toEntity(), ride.segments.map { SegmentEntity(ride.id, it.seq, it.startedAt, it.endedAt, it.bootCount) })
 
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RideControllerTest' --tests '*RoomRideStoreTest' --rerun`
Expected: `RideControllerTest` 37件（始める前の33件＋4件）・`RoomRideStoreTest` 4件が通る。`a_limit_changed_again_and_again_keeps_only_the_last_one` は実装の前から通る振る舞いを固めるもの（#36）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ride/Ride.kt app/src/main/java/com/touringproject/v2/ride/RidePorts.kt \
  app/src/main/java/com/touringproject/v2/ride/RideController.kt app/src/main/java/com/touringproject/v2/store/RoomRideStore.kt \
  app/src/test/java/com/touringproject/v2/ride/RideControllerTest.kt
git commit -m "feat: rename a kept ride through the ride controller"
```

---
### Task 3: 記録の読み出し（一覧と詳細）

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/records/Records.kt`・`app/src/main/java/com/touringproject/v2/store/RoomRecords.kt`
- Modify: `app/src/main/java/com/touringproject/v2/store/RideDatabase.kt`
- Test: `app/src/test/java/com/touringproject/v2/records/RecordsTest.kt`（新規）・`app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt`（新規）・`app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt`

**Interfaces:**
- Consumes: Task 1 の `refused`・Task 2 の `toRide`。
- Produces: `enum class SaveState { RECORDING, UNSENT, SAVED }`・`fun saveState(status: RideStatus, updatedAt: Long, sentUpdatedAt: Long?, pointsLeft: Boolean): SaveState`・`data class RideListItem(val ride: Ride, val questions: Int, val saveState: SaveState)`・`fun orderRides(items: List<RideListItem>): List<RideListItem>`・`RideDao.rows(): Flow<List<RideRow>>`・`RideDao.watch(id): Flow<RideWithSegments?>`・`AskDao.forRide(rideId): Flow<List<AskEntity>>`・`fun AskEntity.toRecord(): AskRecord`・`class RoomRecords(rides: RideDao, asks: AskDao)` の `val list: Flow<List<RideListItem>>`・`fun ride(id): Flow<Ride?>`・`fun asks(rideId): Flow<List<AskRecord>>`・`suspend fun route(rideId): List<RoutePoint>`。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/records/RecordsTest.kt`（新規）:

````kotlin
package com.touringproject.v2.records

import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.HOUR_MS
import com.touringproject.v2.ride.RideStatus
import com.touringproject.v2.ride.end
import com.touringproject.v2.ride.newRide
import org.junit.Assert.assertEquals
import org.junit.Test

class RecordsTest {
  @Test
  fun a_ride_recording_or_paused_is_recording_whatever_has_been_sent() {
    assertEquals(SaveState.RECORDING, saveState(RideStatus.RECORDING, 5, 5, pointsLeft = false))
    assertEquals(SaveState.RECORDING, saveState(RideStatus.PAUSED, 5, null, pointsLeft = true))
  }

  @Test
  fun an_ended_ride_is_saved_only_once_its_newest_version_and_every_point_have_been_taken() {
    assertEquals(SaveState.SAVED, saveState(RideStatus.ENDED, 5, 5, pointsLeft = false))
    assertEquals(SaveState.UNSENT, saveState(RideStatus.ENDED, 5, null, pointsLeft = false))
    assertEquals(SaveState.UNSENT, saveState(RideStatus.ENDED, 6, 5, pointsLeft = false))
    assertEquals(SaveState.UNSENT, saveState(RideStatus.ENDED, 5, 5, pointsLeft = true))
  }

  @Test
  fun the_active_ride_comes_first_then_the_newest() {
    val old = newRide("old", "箱根", 1_000, 7, 24 * HOUR_MS).end(2_000, EndReason.MANUAL, 2_000)
    val new = newRide("new", "御殿場", 5_000, 7, 24 * HOUR_MS).end(6_000, EndReason.MANUAL, 6_000)
    val active = newRide("active", "富士", 3_000, 7, 24 * HOUR_MS)
    val items = listOf(old, active, new).map { RideListItem(it, 0, SaveState.SAVED) }
    assertEquals(listOf("active", "new", "old"), orderRides(items).map { it.ride.id })
  }
}
````

`app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt`（新規）:

````kotlin
package com.touringproject.v2.store

import android.app.Application
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.touringproject.v2.ask.AskOutcome
import com.touringproject.v2.ask.AskRecord
import com.touringproject.v2.records.SaveState
import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.HOUR_MS
import com.touringproject.v2.ride.RoutePoint
import com.touringproject.v2.ride.end
import com.touringproject.v2.ride.newRide
import com.touringproject.v2.ride.pause
import com.touringproject.v2.ride.resume
import com.touringproject.v2.sync.ChunkRange
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RoomRecordsTest {
  private val db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext<Application>(), RideDatabase::class.java)
    .allowMainThreadQueries()
    .build()
  private val rides = RoomRideStore(db.rides())
  private val sync = RoomSyncStore(db.rides())
  private val log = RoomAskLog(db.asks(), MainScope()) { _, _ -> }
  private val records = RoomRecords(db.rides(), db.asks())

  @After
  fun close() = db.close()

  private fun ask(id: String, at: Long, rideId: String?) = AskRecord(
    id, at, at + 1, "右手の山は？", "金時山です。", 35.2, 139.0, "神奈川県箱根町", 45.0, "voice", "c1", false, AskOutcome.ANSWERED, null, rideId,
  )

  @Test
  fun the_list_counts_each_rides_asks_and_tells_how_far_it_was_sent() = runBlocking {
    val ended = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).pause(2_000).resume(3_000, 7, 24 * HOUR_MS).end(4_000, EndReason.MANUAL, 4_000)
    rides.save(ended)
    rides.addPoint("r1", RoutePoint(0, 1_500, 35.0, 139.0, 5.0), 0.0, 1_500)
    log.save(ask("a1", 1_200, "r1"))
    log.save(ask("a2", 3_500, "r1"))
    log.save(ask("a3", 2_500, null))
    val active = newRide("r2", "御殿場", 5_000, 7, 24 * HOUR_MS)
    rides.save(active)
    var list = records.list.first()
    assertEquals(listOf("r2", "r1"), list.map { it.ride.id })
    assertEquals(listOf(0, 2), list.map { it.questions })
    assertEquals(listOf(SaveState.RECORDING, SaveState.UNSENT), list.map { it.saveState })
    assertEquals(2, list[1].ride.segments.size)
    sync.rideSent("r1", ended.updatedAt)
    sync.chunkSent("r1", ChunkRange(0, 0, 1), refused = false)
    list = records.list.first()
    assertEquals(SaveState.SAVED, list[1].saveState)
  }

  // Android #27: a refused chunk keeps the ride "未送信あり" until the same seq is taken.
  @Test
  fun a_refused_chunk_keeps_the_ride_unsent_until_its_seq_is_taken() = runBlocking {
    val ended = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(4_000, EndReason.MANUAL, 4_000)
    rides.save(ended)
    sync.rideSent("r1", ended.updatedAt)
    rides.addPoint("r1", RoutePoint(0, 1_500, 35.0, 139.0, 5.0), 0.0, 1_500)
    sync.chunkSent("r1", ChunkRange(0, 0, 1), refused = true)
    assertEquals(SaveState.UNSENT, records.list.first().single().saveState)
    sync.chunkSent("r1", ChunkRange(0, 0, 1), refused = false)
    assertEquals(SaveState.SAVED, records.list.first().single().saveState)
  }

  @Test
  fun a_ride_its_asks_and_its_route_are_read_for_the_detail() = runBlocking {
    val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS)
    rides.save(ride)
    rides.addPoint("r1", RoutePoint(0, 1_500, 35.0, 139.0, 5.0), 0.0, 1_500)
    log.save(ask("a2", 3_500, "r1"))
    log.save(ask("a1", 1_200, "r1"))
    assertEquals(ride.copy(lastAliveAt = 1_500), records.ride("r1").first())
    assertEquals(listOf("a1", "a2"), records.asks("r1").first().map { it.askId })
    assertEquals(listOf(1_500L), records.route("r1").map { it.t })
    assertNull(records.ride("r9").first())
  }
}
````

`AskDao` に `forRide` を足すので、`RoomAskLogTest` の作り物の `AskDao` にも足す（足さないと、差分コンパイルでは通ってしまい、`clean` から回すと落ちる）:

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
index bf7bda3..ef06a34 100644
--- a/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
+++ b/app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
@@ -57,6 +57,7 @@ class RoomAskLogTest {
       override suspend fun upsert(ask: AskEntity) = if (full) throw IOException("disk full") else Unit
       override suspend fun ask(askId: String): AskEntity? = null
       override fun countForRide(rideId: String) = kotlinx.coroutines.flow.flowOf(0)
+      override fun forRide(rideId: String) = kotlinx.coroutines.flow.flowOf(emptyList<AskEntity>())
     }
     val failing = RoomAskLog(dao, kotlinx.coroutines.MainScope()) { message, _ -> errors += message }
     failing.save(record)
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*.RecordsTest' --tests '*RoomRecordsTest'`
Expected: コンパイルの失敗（`Unresolved reference 'saveState'`・`'RoomRecords'`・`'forRide'`）。

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/records/Records.kt`（新規）:

````kotlin
package com.touringproject.v2.records

import com.touringproject.v2.ride.Ride
import com.touringproject.v2.ride.RideStatus
import com.touringproject.v2.ride.startedAt

// What SC-05 lists: the kept rides and how far each has reached the Backend (slice 2 spec §5.4, §7.4).

enum class SaveState { RECORDING, UNSENT, SAVED }

/**
 * "記録中" while the ride records or is paused; "未送信あり" while its newest version has not been taken (a refused one
 * included) or a point has not gone or was refused; "保存済み" otherwise (slice 2 spec §5.4).
 */
fun saveState(status: RideStatus, updatedAt: Long, sentUpdatedAt: Long?, pointsLeft: Boolean): SaveState = when {
  status != RideStatus.ENDED -> SaveState.RECORDING
  pointsLeft || sentUpdatedAt == null || sentUpdatedAt < updatedAt -> SaveState.UNSENT
  else -> SaveState.SAVED
}

/** questions counts the asks kept for the ride, answered or failed. */
data class RideListItem(val ride: Ride, val questions: Int, val saveState: SaveState)

/** The ride recording or paused comes first, then the others, newest first (SC-05). */
fun orderRides(items: List<RideListItem>): List<RideListItem> =
  items.sortedWith(compareBy<RideListItem> { it.ride.status == RideStatus.ENDED }.thenByDescending { it.ride.startedAt() })
````

`app/src/main/java/com/touringproject/v2/store/RoomRecords.kt`（新規）:

````kotlin
package com.touringproject.v2.store

import com.touringproject.v2.ask.AskOutcome
import com.touringproject.v2.ask.AskRecord
import com.touringproject.v2.records.RideListItem
import com.touringproject.v2.records.orderRides
import com.touringproject.v2.records.saveState
import com.touringproject.v2.ride.Ride
import com.touringproject.v2.ride.RoutePoint
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

fun AskEntity.toRecord() = AskRecord(
  askId = askId,
  askedAt = askedAt,
  answeredAt = answeredAt,
  transcript = transcript,
  answer = answer,
  latitude = latitude,
  longitude = longitude,
  address = address,
  headingDegrees = headingDegrees,
  input = input,
  conversationId = conversationId,
  newConversation = newConversation,
  outcome = AskOutcome.valueOf(status.uppercase()),
  failure = failure,
  rideId = rideId,
)

/** What the records screens read (SC-05, SC-06, SC-07). Each Flow follows the database as it changes. */
class RoomRecords(private val rides: RideDao, private val asks: AskDao) {
  val list: Flow<List<RideListItem>> = rides.rows().map { rows ->
    orderRides(
      rows.map { row ->
        val ride = row.ride.toRide(row.segments.sortedBy { it.seq })
        RideListItem(ride, row.questions, saveState(ride.status, ride.updatedAt, row.ride.sentUpdatedAt, row.pointsLeft))
      },
    )
  }

  fun ride(id: String): Flow<Ride?> = rides.watch(id).map { it?.ride?.toRide(it.segments.sortedBy { s -> s.seq }) }

  fun asks(rideId: String): Flow<List<AskRecord>> = asks.forRide(rideId).map { list -> list.map { it.toRecord() } }

  /** Read once when the ride is opened: the route of a ride still recording does not follow it. */
  suspend fun route(rideId: String): List<RoutePoint> = rides.points(rideId).map { it.toPoint() }
}
````

`RideDatabase.kt` に読み出しの問い合わせを足す:

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
index ae4ac27..800a19b 100644
--- a/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
+++ b/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt
@@ -3,6 +3,7 @@ package com.touringproject.v2.store
 import android.content.Context
 import androidx.room.ColumnInfo
 import androidx.room.Dao
+import androidx.room.Embedded
 import androidx.room.Database
 import androidx.room.Entity
 import androidx.room.ForeignKey
@@ -10,6 +11,7 @@ import androidx.room.Index
 import androidx.room.Insert
 import androidx.room.PrimaryKey
 import androidx.room.Query
+import androidx.room.Relation
 import androidx.room.Room
 import androidx.room.RoomDatabase
 import androidx.room.Transaction
@@ -109,8 +111,25 @@ interface AskDao {
   /** How many of the ride's asks are kept, answered or failed; follows every new one (SC-02, SC-04). */
   @Query("SELECT COUNT(*) FROM asks WHERE rideId = :rideId")
   fun countForRide(rideId: String): Flow<Int>
+
+  /** The ride's asks in the order they were asked (SC-06, SC-07). */
+  @Query("SELECT * FROM asks WHERE rideId = :rideId ORDER BY askedAt")
+  fun forRide(rideId: String): Flow<List<AskEntity>>
 }
 
+data class RideWithSegments(
+  @Embedded val ride: RideEntity,
+  @Relation(parentColumn = "id", entityColumn = "rideId") val segments: List<SegmentEntity>,
+)
+
+/** A ride as SC-05 lists it. pointsLeft is true while one of its points has not been taken (unsent or refused). */
+data class RideRow(
+  @Embedded val ride: RideEntity,
+  @Relation(parentColumn = "id", entityColumn = "rideId") val segments: List<SegmentEntity>,
+  val questions: Int,
+  val pointsLeft: Boolean,
+)
+
 @Dao
 interface RideDao {
   @Query("SELECT * FROM rides WHERE status != 'ended' LIMIT 1")
@@ -122,6 +141,19 @@ interface RideDao {
   @Query("SELECT * FROM ride_segments WHERE rideId = :rideId ORDER BY seq")
   suspend fun segments(rideId: String): List<SegmentEntity>
 
+  // Records (SC-05, SC-06). Each EXISTS reads one index of route_points, so the list stays quick while a ride records.
+  @Transaction
+  @Query(
+    "SELECT *, (SELECT COUNT(*) FROM asks WHERE asks.rideId = rides.id) AS questions, " +
+      "(EXISTS (SELECT 1 FROM route_points WHERE chunk IS NULL AND route_points.rideId = rides.id) OR " +
+      "EXISTS (SELECT 1 FROM route_points WHERE refused = 1 AND route_points.rideId = rides.id)) AS pointsLeft FROM rides",
+  )
+  fun rows(): Flow<List<RideRow>>
+
+  @Transaction
+  @Query("SELECT * FROM rides WHERE id = :id")
+  fun watch(id: String): Flow<RideWithSegments?>
+
   @Upsert
   suspend fun upsertRide(ride: RideEntity)
 
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*.RecordsTest' --tests '*RoomRecordsTest' --tests '*RoomAskLogTest' --rerun`
Expected: `RecordsTest` 3件・`RoomRecordsTest` 3件・`RoomAskLogTest` 3件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/records/Records.kt app/src/main/java/com/touringproject/v2/store/RoomRecords.kt \
  app/src/main/java/com/touringproject/v2/store/RideDatabase.kt \
  app/src/test/java/com/touringproject/v2/records/RecordsTest.kt app/src/test/java/com/touringproject/v2/store/RoomRecordsTest.kt \
  app/src/test/java/com/touringproject/v2/store/RoomAskLogTest.kt
git commit -m "feat: read the rides, their asks and their routes for the records screens"
```

---
### Task 4: 地図に描くデータ

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/map/MapData.kt`
- Test: `app/src/test/java/com/touringproject/v2/map/MapDataTest.kt`（新規）

**Interfaces:**
- Produces: `data class LatLon(lat, lon)`・`data class MapPin(askId: String, number: Int, at: LatLon)`・`data class MapData(routes, pauses, start, end, pins, faint = false, focus: LatLon? = null)` と `extent`・`fun rideMap(points: List<RoutePoint>, ended: Boolean, pins: List<MapPin>, faint: Boolean = false, focus: LatLon? = null): MapData`・`routesJson`・`pausesJson`・`endsJson`（`kind` が `start`/`end`）・`pinsJson(data, selected: String?)`（`askId` と `icon`）・`fun pinIcon(number: Int, selected: Boolean): String`。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/map/MapDataTest.kt`（新規）:

````kotlin
package com.touringproject.v2.map

import com.touringproject.v2.ride.RoutePoint
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MapDataTest {
  private fun p(segment: Int, lat: Double, lon: Double) = RoutePoint(segment, 0, lat, lon, 5.0)

  private val points = listOf(p(0, 35.0, 139.0), p(0, 35.1, 139.1), p(2, 35.5, 139.5), p(2, 35.6, 139.6))

  @Test
  fun each_segment_is_a_line_and_a_pause_joins_where_one_stopped_to_where_the_next_started() {
    val map = rideMap(points, ended = true, pins = emptyList())
    assertEquals(listOf(listOf(LatLon(35.0, 139.0), LatLon(35.1, 139.1)), listOf(LatLon(35.5, 139.5), LatLon(35.6, 139.6))), map.routes)
    assertEquals(listOf(listOf(LatLon(35.1, 139.1), LatLon(35.5, 139.5))), map.pauses)
    assertEquals(LatLon(35.0, 139.0), map.start)
    assertEquals(LatLon(35.6, 139.6), map.end)
  }

  @Test
  fun a_ride_not_yet_ended_has_no_end_mark_and_one_without_points_draws_nothing() {
    assertNull(rideMap(points, ended = false, pins = emptyList()).end)
    val empty = rideMap(emptyList(), ended = true, pins = emptyList())
    assertEquals(emptyList<LatLon>(), empty.extent)
    assertNull(empty.start)
  }

  @Test
  fun the_geojson_puts_longitude_first_and_drops_a_line_of_one_point() {
    val map = rideMap(listOf(p(0, 35.0, 139.0), p(1, 35.5, 139.5), p(1, 35.6, 139.6)), ended = true, pins = emptyList())
    val features = Json.parseToJsonElement(routesJson(map)).jsonObject["features"]!!.jsonArray
    assertEquals(1, features.size)
    val first = features[0].jsonObject["geometry"]!!.jsonObject["coordinates"]!!.jsonArray[0].jsonArray
    assertEquals(listOf("139.5", "35.5"), first.map { it.jsonPrimitive.content })
  }

  @Test
  fun the_selected_pin_takes_its_own_image() {
    val map = rideMap(points, ended = true, pins = listOf(MapPin("a1", 1, LatLon(35.0, 139.0)), MapPin("a2", 2, LatLon(35.1, 139.1))))
    val features = Json.parseToJsonElement(pinsJson(map, "a2")).jsonObject["features"]!!.jsonArray
    assertEquals(
      listOf("pin-1", "pin-sel-2"),
      features.map { it.jsonObject["properties"]!!.jsonObject["icon"]!!.jsonPrimitive.content },
    )
  }

  @Test
  fun a_map_with_a_focus_opens_on_it_alone() {
    val at = LatLon(35.1, 139.1)
    assertEquals(listOf(at), rideMap(points, ended = true, pins = listOf(MapPin("a1", 1, at)), faint = true, focus = at).extent)
  }
}
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*MapDataTest'`
Expected: コンパイルの失敗（`Unresolved reference 'rideMap'`）。

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/map/MapData.kt`（新規）:

````kotlin
package com.touringproject.v2.map

import com.touringproject.v2.ride.RoutePoint
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

// What a map draws, worked out without MapLibre so it is tested on the JVM (slice 2 spec §7.7).

data class LatLon(val lat: Double, val lon: Double)

/** A numbered ask on the map; number is the ask's place in the ride's timeline. */
data class MapPin(val askId: String, val number: Int, val at: LatLon)

/**
 * routes has one line per recorded segment that has points; pauses joins the last point of a segment to the first
 * of the next one (slice 2 spec §7.5). end is set only once the ride has ended. faint draws the route lightly, under
 * one ask's pin, and focus is where the camera opens instead of the whole route (SC-07).
 */
data class MapData(
  val routes: List<List<LatLon>>,
  val pauses: List<List<LatLon>>,
  val start: LatLon?,
  val end: LatLon?,
  val pins: List<MapPin>,
  val faint: Boolean = false,
  val focus: LatLon? = null,
) {
  /** Everything the camera should take in when the map opens. */
  val extent: List<LatLon> get() = focus?.let { listOf(it) } ?: (routes.flatten() + pins.map { it.at })
}

fun rideMap(points: List<RoutePoint>, ended: Boolean, pins: List<MapPin>, faint: Boolean = false, focus: LatLon? = null): MapData {
  val routes = points.groupBy { it.segment }.toSortedMap().values.map { segment -> segment.map { LatLon(it.lat, it.lon) } }
  val pauses = routes.zipWithNext { a, b -> listOf(a.last(), b.first()) }
  return MapData(
    routes = routes,
    pauses = pauses,
    start = routes.firstOrNull()?.first(),
    end = if (ended) routes.lastOrNull()?.last() else null,
    pins = pins,
    faint = faint,
    focus = focus,
  )
}

private fun LatLon.coordinates() = buildJsonArray {
  add(JsonPrimitive(lon))
  add(JsonPrimitive(lat))
}

private fun feature(geometry: JsonObject, properties: JsonObject = JsonObject(emptyMap())) = buildJsonObject {
  put("type", "Feature")
  put("geometry", geometry)
  put("properties", properties)
}

private fun collection(features: List<JsonObject>) = buildJsonObject {
  put("type", "FeatureCollection")
  put("features", JsonArray(features))
}.toString()

private fun line(points: List<LatLon>) = buildJsonObject {
  put("type", "LineString")
  put("coordinates", JsonArray(points.map { it.coordinates() }))
}

private fun point(at: LatLon) = buildJsonObject {
  put("type", "Point")
  put("coordinates", at.coordinates())
}

/** A line of a single point draws nothing, so only lines of two or more go. */
fun routesJson(data: MapData): String = collection(data.routes.filter { it.size > 1 }.map { feature(line(it)) })

fun pausesJson(data: MapData): String = collection(data.pauses.map { feature(line(it)) })

/** kind is "start" or "end". */
fun endsJson(data: MapData): String = collection(
  listOfNotNull(data.start?.let { "start" to it }, data.end?.let { "end" to it }).map { (kind, at) ->
    feature(point(at), buildJsonObject { put("kind", kind) })
  },
)

/** icon names the pin's image: its number, and whether it is the selected one. */
fun pinsJson(data: MapData, selected: String?): String = collection(
  data.pins.map { pin ->
    feature(
      point(pin.at),
      buildJsonObject {
        put("askId", pin.askId)
        put("icon", pinIcon(pin.number, pin.askId == selected))
      },
    )
  },
)

fun pinIcon(number: Int, selected: Boolean): String = if (selected) "pin-sel-$number" else "pin-$number"
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*MapDataTest' --rerun`
Expected: 5件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/map/MapData.kt app/src/test/java/com/touringproject/v2/map/MapDataTest.kt
git commit -m "feat: work out what a ride's map draws as GeoJSON"
```

---
### Task 5: 一覧・時系列・会話の詳細の文字

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt`（新規）

**Interfaces:**
- Consumes: Task 3 の `RideListItem`・`SaveState`、Task 4 の `LatLon`・`MapPin`、既存の `distanceLabel`・`elapsedLabel`・`pausesLabel`（`RideLabels.kt`）。
- Produces: `dayLabel`・`rideDateLabel(ride, now, zone)`・`rideSpanLabel(ride, zone)`・`saveLabel`・`data class RideRowUi(id, name, date, stats, state, saved)`・`rideRow`・`data class RideSection(month, rows)`・`rideSections(items, now, zone)`・`data class RideSummaryUi(date, span, elapsed, distance, questions, pauses, autoEnded)`・`rideSummary(ride, questions, now, zone)`・`askNumbers(asks): Map<String, Int>`・`askPins(asks): List<MapPin>`・`shortPlace`・`askText`・`sealed interface TimelineRow`（`Day`・`Ask(askId, number, time, place, text, failed)`・`Pause(label)`・`NewConversation`）・`pauseLabel`・`rideTimeline(ride, asks, zone)`・`compass`・`directionLabel(heading: Double?)`・`failureLabel`・`data class AskDetailUi(title, time, place, direction, input, question, answer, failure, previous, next)`・`askDetail(asks, askId, zone): AskDetailUi?`・`data class PinCardUi(askId, heading, question, answer)`・`pinCard(asks, askId, zone): PinCardUi?`。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt`（新規）:

````kotlin
package com.touringproject.v2.ui

import com.touringproject.v2.ask.AskOutcome
import com.touringproject.v2.ask.AskRecord
import com.touringproject.v2.records.RideListItem
import com.touringproject.v2.records.SaveState
import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.HOUR_MS
import com.touringproject.v2.ride.end
import com.touringproject.v2.ride.newRide
import com.touringproject.v2.ride.pause
import com.touringproject.v2.ride.resume
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.ZoneId
import java.time.ZonedDateTime

class RecordLabelsTest {
  private val zone = ZoneId.of("Asia/Tokyo")

  private fun ms(day: Int, hour: Int, minute: Int, month: Int = 10) = ZonedDateTime.of(2026, month, day, hour, minute, 0, 0, zone).toInstant().toEpochMilli()

  private fun ask(id: String, at: Long, transcript: String? = "右手の山は？", newConversation: Boolean = false, failure: String? = null) = AskRecord(
    askId = id, askedAt = at, answeredAt = at + 5_000, transcript = transcript, answer = "金時山です。",
    latitude = 35.2, longitude = 139.0, address = "神奈川県足柄下郡箱根町仙石原", headingDegrees = 45.0, input = "voice",
    conversationId = "c1", newConversation = newConversation,
    outcome = if (failure == null) AskOutcome.ANSWERED else AskOutcome.FAILED, failure = failure, rideId = "r1",
  )

  // 16 Oct 08:58 – 09:44, paused until 10:02, then 10:02 – 10:46.
  private val ride = newRide("r1", "箱根", ms(16, 8, 58), 7, 24 * HOUR_MS)
    .pause(ms(16, 9, 44)).resume(ms(16, 10, 2), 7, 24 * HOUR_MS).end(ms(16, 10, 46), EndReason.MANUAL, ms(16, 10, 46))
    .copy(distanceMeters = 52_800.0)

  @Test
  fun a_ride_row_says_when_how_far_and_how_it_was_kept() {
    val row = rideRow(RideListItem(ride, 4, SaveState.SAVED), ms(17, 0, 0), zone)
    assertEquals("10月16日（金） · 08:58〜10:46", row.date)
    assertEquals("52.8 km · 1:30 · 質問 4 · ⏸ 1", row.stats)
    assertEquals("保存済み", row.state)
  }

  @Test
  fun a_ride_over_nights_shows_its_days_and_one_still_recording_has_no_end() {
    val overnight = newRide("r2", "伊豆", ms(16, 9, 0), 7, 48 * HOUR_MS).end(ms(18, 15, 0), EndReason.MANUAL, ms(18, 15, 0))
    assertEquals("10月16日〜18日（2泊）", rideDateLabel(overnight, 0, zone))
    val acrossMonths = newRide("r3", "信州", ms(31, 9, 0), 7, 48 * HOUR_MS).end(ms(1, 15, 0, month = 11), EndReason.MANUAL, ms(1, 15, 0, month = 11))
    assertEquals("10月31日〜11月1日（1泊）", rideDateLabel(acrossMonths, 0, zone))
    val recording = newRide("r4", "富士", ms(16, 9, 0), 7, 24 * HOUR_MS)
    assertEquals("09:00〜", rideSpanLabel(recording, zone))
    assertEquals("● 記録中", rideRow(RideListItem(recording, 0, SaveState.RECORDING), ms(16, 10, 0), zone).state)
  }

  @Test
  fun rides_are_grouped_under_the_month_they_started() {
    val september = newRide("r0", "秩父", ms(20, 9, 0, month = 9), 7, 24 * HOUR_MS).end(ms(20, 12, 0, month = 9), EndReason.MANUAL, ms(20, 12, 0, month = 9))
    val sections = rideSections(listOf(ride, september).map { RideListItem(it, 0, SaveState.UNSENT) }, 0, zone)
    assertEquals(listOf("2026年10月", "2026年9月"), sections.map { it.month })
    assertEquals("未送信あり", sections[0].rows.single().state)
  }

  @Test
  fun the_timeline_puts_asks_pauses_and_new_conversations_in_time_order() {
    val asks = listOf(
      ask("a2", ms(16, 10, 30), newConversation = true),
      ask("a1", ms(16, 9, 41), newConversation = true),
      ask("a3", ms(16, 10, 40), transcript = null, failure = "no_speech"),
    )
    assertEquals(
      listOf(
        TimelineRow.Ask("a1", 1, "09:41", "足柄下郡箱根町仙石原", "右手の山は？", false),
        TimelineRow.Pause("⏸ 一時停止 09:44〜10:02（18分）"),
        TimelineRow.NewConversation,
        TimelineRow.Ask("a2", 2, "10:30", "足柄下郡箱根町仙石原", "右手の山は？", false),
        TimelineRow.Ask("a3", 3, "10:40", "足柄下郡箱根町仙石原", "（聞き取れませんでした）", true),
      ),
      rideTimeline(ride, asks, zone),
    )
  }

  @Test
  fun a_ride_over_a_night_gets_a_heading_per_day_and_a_paused_one_ends_with_its_pause() {
    val overnight = newRide("r2", "伊豆", ms(16, 15, 0), 7, 48 * HOUR_MS).pause(ms(16, 21, 10)).resume(ms(17, 8, 30), 7, 48 * HOUR_MS).pause(ms(17, 12, 0))
    assertEquals(
      listOf(
        TimelineRow.Day("10月16日（金）"),
        TimelineRow.Ask("a1", 1, "16:00", "足柄下郡箱根町仙石原", "右手の山は？", false),
        TimelineRow.Pause("⏸ 一時停止 21:10〜10月17日 08:30"),
        TimelineRow.Day("10月17日（土）"),
        TimelineRow.Ask("a2", 2, "09:00", "足柄下郡箱根町仙石原", "右手の山は？", false),
        TimelineRow.Pause("⏸ 一時停止中 12:00〜"),
      ),
      rideTimeline(overnight, listOf(ask("a1", ms(16, 16, 0)), ask("a2", ms(17, 9, 0))), zone),
    )
  }

  @Test
  fun pins_are_numbered_like_the_timeline_and_an_ask_without_a_place_has_none() {
    val asks = listOf(ask("a2", ms(16, 10, 30)), ask("a1", ms(16, 9, 41)).copy(latitude = null, longitude = null))
    assertEquals(listOf("a2" to 2), askPins(asks).map { it.askId to it.number })
  }

  @Test
  fun the_direction_names_the_way_and_both_hands_and_no_heading_means_stopped() {
    assertEquals("北東へ走行中（右手 南東・左手 北西）", directionLabel(45.0))
    assertEquals("北へ走行中（右手 東・左手 西）", directionLabel(350.0))
    assertEquals("停車中", directionLabel(null))
  }

  @Test
  fun the_detail_says_its_place_among_the_rides_asks_and_why_an_ask_failed() {
    val asks = listOf(ask("a1", ms(16, 9, 41)), ask("a2", ms(16, 10, 30), transcript = null, failure = "timeout"), ask("a3", ms(16, 10, 40)))
    val detail = askDetail(asks, "a2", zone)!!
    assertEquals("会話 2 / 3", detail.title)
    assertEquals("10月16日（金） 10:30", detail.time)
    assertEquals("神奈川県足柄下郡箱根町仙石原", detail.place)
    assertEquals("🎤 声で質問", detail.input)
    assertNull(detail.question)
    assertEquals("時間内に答えが届きませんでした", detail.failure)
    assertEquals("a1" to "a3", detail.previous to detail.next)
    assertNull(askDetail(asks, "a1", zone)!!.previous)
    assertNull(askDetail(asks, "a9", zone))
  }

  @Test
  fun a_pin_card_shows_the_number_the_time_and_the_short_place() {
    val card = pinCard(listOf(ask("a1", ms(16, 9, 41))), "a1", zone)!!
    assertEquals("1 · 09:41 · 足柄下郡箱根町仙石原", card.heading)
    assertEquals("金時山です。", card.answer)
  }
}
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordLabelsTest'`
Expected: コンパイルの失敗（`Unresolved reference 'rideRow'`）。

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt`（新規）:

````kotlin
package com.touringproject.v2.ui

import com.touringproject.v2.ask.AskOutcome
import com.touringproject.v2.ask.AskRecord
import com.touringproject.v2.map.LatLon
import com.touringproject.v2.map.MapPin
import com.touringproject.v2.records.RideListItem
import com.touringproject.v2.records.SaveState
import com.touringproject.v2.ride.EndReason
import com.touringproject.v2.ride.Ride
import com.touringproject.v2.ride.RideStatus
import com.touringproject.v2.ride.pauses
import com.touringproject.v2.ride.recordedMs
import com.touringproject.v2.ride.startedAt
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

// How SC-05, SC-06 and SC-07 describe rides and asks (the mock's records screens, slice 2 spec §7.4–§7.6).

private val TIME = DateTimeFormatter.ofPattern("HH:mm")
private const val WEEKDAYS = "月火水木金土日"

private fun at(ms: Long, zone: ZoneId): ZonedDateTime = Instant.ofEpochMilli(ms).atZone(zone)

/** 10月16日（金）; without the weekday, 10月16日. */
fun dayLabel(date: LocalDate, weekday: Boolean = true): String {
  val day = "${date.monthValue}月${date.dayOfMonth}日"
  return if (weekday) "$day（${WEEKDAYS[date.dayOfWeek.value - 1]}）" else day
}

private fun Ride.lastMs(now: Long) = segments.last().endedAt ?: now

/** 10月16日（金）; over nights, 10月16日〜18日（2泊）, or 10月31日〜11月1日（1泊） across a month. */
fun rideDateLabel(ride: Ride, now: Long, zone: ZoneId): String {
  val from = at(ride.startedAt(), zone).toLocalDate()
  val to = at(ride.lastMs(now), zone).toLocalDate()
  if (from == to) return dayLabel(from)
  val nights = ChronoUnit.DAYS.between(from, to)
  val end = if (from.monthValue == to.monthValue) "${to.dayOfMonth}日" else dayLabel(to, weekday = false)
  return "${dayLabel(from, weekday = false)}〜$end（${nights}泊）"
}

/** 08:58〜16:20; a ride still recording or paused has no end yet: 08:58〜. */
fun rideSpanLabel(ride: Ride, zone: ZoneId): String {
  val start = TIME.format(at(ride.startedAt(), zone))
  val end = if (ride.status == RideStatus.ENDED) ride.segments.last().endedAt?.let { TIME.format(at(it, zone)) } ?: "" else ""
  return "$start〜$end"
}

fun saveLabel(item: RideListItem): String = when (item.saveState) {
  SaveState.RECORDING -> if (item.ride.status == RideStatus.PAUSED) "⏸ 一時停止中" else "● 記録中"
  SaveState.UNSENT -> "未送信あり"
  SaveState.SAVED -> "保存済み"
}

data class RideRowUi(val id: String, val name: String, val date: String, val stats: String, val state: String, val saved: Boolean)

/** One ride of SC-05: 52.8 km · 1:26 · 質問 4 · ⏸ 1 (the pauses only when there were some). */
fun rideRow(item: RideListItem, now: Long, zone: ZoneId): RideRowUi {
  val ride = item.ride
  val pauses = ride.pauses().count
  val stats = listOfNotNull(
    distanceLabel(ride.distanceMeters),
    elapsedLabel(ride.recordedMs(now)),
    "質問 ${item.questions}",
    if (pauses > 0) "⏸ $pauses" else null,
  ).joinToString(" · ")
  return RideRowUi(
    ride.id, ride.name, "${rideDateLabel(ride, now, zone)} · ${rideSpanLabel(ride, zone)}", stats, saveLabel(item),
    item.saveState == SaveState.SAVED,
  )
}

data class RideSection(val month: String, val rows: List<RideRowUi>)

/** The ordered rides under a heading per month of their start: 2026年10月. */
fun rideSections(items: List<RideListItem>, now: Long, zone: ZoneId): List<RideSection> {
  val sections = mutableListOf<RideSection>()
  items.forEach { item ->
    val start = at(item.ride.startedAt(), zone)
    val month = "${start.year}年${start.monthValue}月"
    val row = rideRow(item, now, zone)
    if (sections.lastOrNull()?.month == month) sections[sections.lastIndex] = sections.last().let { it.copy(rows = it.rows + row) }
    else sections += RideSection(month, listOf(row))
  }
  return sections
}

/** SC-06's summary. pauses is null without one; autoEnded says the longest recording time ended the ride. */
data class RideSummaryUi(
  val date: String,
  val span: String,
  val elapsed: String,
  val distance: String,
  val questions: String,
  val pauses: String?,
  val autoEnded: Boolean,
)

fun rideSummary(ride: Ride, questions: Int, now: Long, zone: ZoneId) = RideSummaryUi(
  date = rideDateLabel(ride, now, zone),
  span = rideSpanLabel(ride, zone),
  elapsed = elapsedLabel(ride.recordedMs(now)),
  distance = distanceLabel(ride.distanceMeters),
  questions = questions.toString(),
  pauses = pausesLabel(ride.pauses()),
  autoEnded = ride.endReason == EndReason.AUTO,
)

/** The asks in the order they were asked, numbered from 1: the numbers of the pins and the timeline. */
fun askNumbers(asks: List<AskRecord>): Map<String, Int> =
  asks.sortedBy { it.askedAt }.mapIndexed { i, ask -> ask.askId to i + 1 }.toMap()

/** The ride's asks that know where they were asked, as numbered pins. */
fun askPins(asks: List<AskRecord>): List<MapPin> {
  val numbers = askNumbers(asks)
  return asks.sortedBy { it.askedAt }.mapNotNull { ask ->
    val lat = ask.latitude ?: return@mapNotNull null
    val lon = ask.longitude ?: return@mapNotNull null
    MapPin(ask.askId, numbers.getValue(ask.askId), LatLon(lat, lon))
  }
}

/** The mock's short place: the address without its prefecture. */
fun shortPlace(address: String?): String = address?.replace(Regex("^(東京都|.+?[県府道])"), "")?.ifBlank { null } ?: "場所不明"

/** What a list shows of an ask: what was heard, or why nothing was. */
fun askText(ask: AskRecord): String = ask.transcript?.takeIf { it.isNotBlank() } ?: when {
  ask.outcome == AskOutcome.ANSWERED -> "（聞き取った文がありません）"
  ask.failure == "no_speech" -> "（聞き取れませんでした）"
  ask.failure == "timeout" -> "（時間内に答えが届きませんでした）"
  else -> "（うまく答えられませんでした）"
}

sealed interface TimelineRow {
  data class Day(val label: String) : TimelineRow
  data class Ask(val askId: String, val number: Int, val time: String, val place: String, val text: String, val failed: Boolean) : TimelineRow
  data class Pause(val label: String) : TimelineRow
  data object NewConversation : TimelineRow
}

/** ⏸ 一時停止 09:44〜10:02（18分）; over midnight, ⏸ 一時停止 21:10〜10月17日 08:30. */
fun pauseLabel(from: Long, to: Long, zone: ZoneId): String {
  val a = at(from, zone)
  val b = at(to, zone)
  if (a.toLocalDate() == b.toLocalDate()) return "⏸ 一時停止 ${TIME.format(a)}〜${TIME.format(b)}（${(to - from) / 60_000}分）"
  return "⏸ 一時停止 ${TIME.format(a)}〜${dayLabel(b.toLocalDate(), weekday = false)} ${TIME.format(b)}"
}

private sealed interface Event {
  val t: Long
  data class AskAt(override val t: Long, val ask: AskRecord) : Event
  data class PauseAt(override val t: Long, val until: Long?) : Event
}

/**
 * SC-06's timeline: the ride's asks, its pauses and the breaks between conversations, in time order. A ride over
 * more than one day gets a heading for each day (slice 2 spec §7.5). A paused ride ends with its pause so far.
 */
fun rideTimeline(ride: Ride, asks: List<AskRecord>, zone: ZoneId): List<TimelineRow> {
  val numbers = askNumbers(asks)
  val pauses = ride.segments.zipWithNext { a, b -> Event.PauseAt(a.endedAt ?: b.startedAt, b.startedAt) }
  val open = if (ride.status == RideStatus.PAUSED) listOfNotNull(ride.segments.last().endedAt?.let { Event.PauseAt(it, null) }) else emptyList()
  // An ask comes before a pause that starts at the same moment.
  val events = (asks.map { Event.AskAt(it.askedAt, it) } + pauses + open).sortedWith(compareBy<Event> { it.t }.thenBy { if (it is Event.AskAt) 0 else 1 })
  val days = (events.map { it.t } + ride.startedAt()).map { at(it, zone).toLocalDate() }.toSet()
  val rows = mutableListOf<TimelineRow>()
  var day: LocalDate? = null
  var asked = false
  events.forEach { event ->
    val date = at(event.t, zone).toLocalDate()
    if (days.size > 1 && date != day) rows += TimelineRow.Day(dayLabel(date))
    day = date
    when (event) {
      is Event.AskAt -> {
        val ask = event.ask
        if (ask.newConversation && asked) rows += TimelineRow.NewConversation
        asked = true
        rows += TimelineRow.Ask(
          ask.askId, numbers.getValue(ask.askId), TIME.format(at(ask.askedAt, zone)), shortPlace(ask.address), askText(ask),
          ask.outcome == AskOutcome.FAILED,
        )
      }
      is Event.PauseAt -> rows += TimelineRow.Pause(
        event.until?.let { pauseLabel(event.t, it, zone) } ?: "⏸ 一時停止中 ${TIME.format(at(event.t, zone))}〜",
      )
    }
  }
  return rows
}

private val COMPASS = listOf("北", "北東", "東", "南東", "南", "南西", "西", "北西")

/** The nearest of the eight points of the compass. */
fun compass(degrees: Double): String = COMPASS[((((degrees % 360) + 360) % 360 + 22.5) / 45).toInt() % 8]

/** SC-07: 北東へ走行中（右手 南東・左手 北西）; without a heading, 停車中. */
fun directionLabel(heading: Double?): String =
  heading?.let { "${compass(it)}へ走行中（右手 ${compass(it + 90)}・左手 ${compass(it - 90)}）" } ?: "停車中"

/** Why an ask got no answer (SC-07). */
fun failureLabel(failure: String?): String = when (failure) {
  "no_speech" -> "声が聞き取れませんでした"
  "transcribe_failed" -> "声を文字にできませんでした"
  "timeout" -> "時間内に答えが届きませんでした"
  else -> "AI が答えられませんでした"
}

/** SC-07. question is null when nothing was heard; failure is set for an ask that got no answer. */
data class AskDetailUi(
  val title: String,
  val time: String,
  val place: String,
  val direction: String,
  val input: String,
  val question: String?,
  val answer: String?,
  val failure: String?,
  val previous: String?,
  val next: String?,
)

/** askId's place among the asks it was opened from (the ride's): 会話 3 / 5, and the asks before and after it. */
fun askDetail(asks: List<AskRecord>, askId: String, zone: ZoneId): AskDetailUi? {
  val ordered = asks.sortedBy { it.askedAt }
  val i = ordered.indexOfFirst { it.askId == askId }
  if (i < 0) return null
  val ask = ordered[i]
  val time = at(ask.askedAt, zone)
  return AskDetailUi(
    title = "会話 ${i + 1} / ${ordered.size}",
    time = "${dayLabel(time.toLocalDate())} ${TIME.format(time)}",
    place = ask.address?.ifBlank { null } ?: "場所不明",
    direction = directionLabel(ask.headingDegrees),
    input = if (ask.input == "text") "⌨ 文字で質問" else "🎤 声で質問",
    question = ask.transcript?.ifBlank { null },
    answer = ask.answer?.ifBlank { null },
    failure = if (ask.outcome == AskOutcome.FAILED) failureLabel(ask.failure) else null,
    previous = ordered.getOrNull(i - 1)?.askId,
    next = ordered.getOrNull(i + 1)?.askId,
  )
}

/** The card of a tapped pin: 3 · 09:41 · 仙石原, then the question and the start of the answer. */
data class PinCardUi(val askId: String, val heading: String, val question: String, val answer: String?)

fun pinCard(asks: List<AskRecord>, askId: String, zone: ZoneId): PinCardUi? {
  val ask = asks.firstOrNull { it.askId == askId } ?: return null
  val number = askNumbers(asks).getValue(askId)
  return PinCardUi(askId, "$number · ${TIME.format(at(ask.askedAt, zone))} · ${shortPlace(ask.address)}", askText(ask), ask.answer?.ifBlank { null })
}
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordLabelsTest' --rerun`
Expected: 9件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RecordLabels.kt app/src/test/java/com/touringproject/v2/ui/RecordLabelsTest.kt
git commit -m "feat: describe rides and asks for the list, the ride detail and the ask detail"
```

---
### Task 6: MapLibre の地図の部品

**Files:**
- Modify: `gradle/libs.versions.toml`・`app/build.gradle.kts`・`app/src/main/AndroidManifest.xml`
- Create: `app/src/main/assets/map/gsi-pale.json`・`app/src/main/java/com/touringproject/v2/map/RouteMap.kt`
- Test: `app/src/androidTest/java/com/touringproject/v2/map/RouteMapTest.kt`（新規・エミュレーター）

**Interfaces:**
- Consumes: Task 4 の `MapData`・`routesJson`・`pausesJson`・`endsJson`・`pinsJson`・`pinIcon`。
- Produces: `@Composable fun RouteMap(data: MapData, selected: String?, onPin: (String?) -> Unit, modifier: Modifier = Modifier, onMap: (MapLibreMap) -> Unit = {})`・`const val PINS_LAYER = "pins"`・`const val GSI_TILES_URL`・`fun pinBitmap(number, selected, density): Bitmap`。レイヤーの名前は `routes`・`pauses`・`ends`・`pins`。

- [ ] **Step 1: 依存と ABI を足す**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index 62729ab..38d0a8a 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -27,6 +27,8 @@ android {
     versionCode = 4
     versionName = "0.3.1"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
+    // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
+    ndk { abiFilters += "arm64-v8a" }
     buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
   }
 
@@ -93,6 +95,7 @@ dependencies {
   implementation(libs.kotlinx.serialization.json)
   implementation(libs.okhttp)
   implementation(libs.play.services.location)
+  implementation(libs.maplibre.android)
   implementation(libs.androidx.room.runtime)
   implementation(libs.androidx.room.ktx)
   ksp(libs.androidx.room.compiler)
@@ -115,6 +118,7 @@ dependencies {
   androidTestImplementation(libs.androidx.test.core)
   androidTestImplementation(libs.androidx.test.ext.junit)
   androidTestImplementation(libs.androidx.test.runner)
+  androidTestImplementation(libs.androidx.compose.ui.test.junit4)
 }
 
 // A test that deadlocks on the main thread must fail the build instead of hanging it.
diff --git a/gradle/libs.versions.toml b/gradle/libs.versions.toml
index 15946e7..9ef88ee 100644
--- a/gradle/libs.versions.toml
+++ b/gradle/libs.versions.toml
@@ -12,6 +12,7 @@ androidxTestRunner = "1.7.0"
 coroutines = "1.10.2"
 junit = "4.13.2"
 kotlin = "2.3.20"
+maplibre = "13.6.1"
 kotlinxSerialization = "1.9.0"
 media3 = "1.9.1"
 nav3Core = "1.0.1"
@@ -48,6 +49,7 @@ kotlinx-coroutines-test = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-t
 kotlinx-serialization-json = { module = "org.jetbrains.kotlinx:kotlinx-serialization-json", version.ref = "kotlinxSerialization" }
 okhttp = { module = "com.squareup.okhttp3:okhttp", version.ref = "okhttp" }
 okhttp-mockwebserver = { module = "com.squareup.okhttp3:mockwebserver", version.ref = "okhttp" }
+maplibre-android = { module = "org.maplibre.gl:android-sdk", version.ref = "maplibre" }
 play-services-location = { module = "com.google.android.gms:play-services-location", version.ref = "playServicesLocation" }
 robolectric = { module = "org.robolectric:robolectric", version.ref = "robolectric" }
 androidx-room-runtime = { module = "androidx.room:room-runtime", version.ref = "room" }
PATCH
````

- [ ] **Step 2: エミュレーターのテストを書く**

`app/src/androidTest/java/com/touringproject/v2/map/RouteMapTest.kt`（新規）:

````kotlin
package com.touringproject.v2.map

import android.graphics.RectF
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.click
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performTouchInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.touringproject.v2.ride.RoutePoint
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap

// On the emulator: MapLibre draws the route and the numbered asks, and a tap on a pin names its ask
// (slice 2 spec §9). The tiles need not load: the layers are drawn without them.
@RunWith(AndroidJUnit4::class)
class RouteMapTest {
  @get:Rule val rule = createComposeRule()

  private val instrumentation = InstrumentationRegistry.getInstrumentation()

  private fun <T> onMain(block: () -> T): T {
    var result: T? = null
    instrumentation.runOnMainSync { result = block() }
    @Suppress("UNCHECKED_CAST")
    return result as T
  }

  private val points = listOf(
    RoutePoint(0, 0, 35.20, 139.00, 5.0), RoutePoint(0, 0, 35.22, 139.03, 5.0),
    RoutePoint(1, 0, 35.25, 139.06, 5.0), RoutePoint(1, 0, 35.28, 139.10, 5.0),
  )
  private val pins = listOf(MapPin("a1", 1, LatLon(35.21, 139.01)), MapPin("a2", 2, LatLon(35.27, 139.09)))

  @Test
  fun the_route_and_the_pins_are_drawn_and_a_tap_on_a_pin_names_its_ask() {
    var map: MapLibreMap? = null
    val tapped = mutableListOf<String?>()
    rule.setContent { RouteMap(rideMap(points, ended = true, pins = pins), null, { tapped += it }, Modifier.fillMaxSize(), onMap = { map = it }) }
    rule.waitUntil(30_000) { map != null }
    val everywhere = onMain { RectF(0f, 0f, map!!.width, map!!.height) }
    rule.waitUntil(30_000) { onMain { map!!.queryRenderedFeatures(everywhere, PINS_LAYER).size } == 2 }
    check(onMain { map!!.queryRenderedFeatures(everywhere, "routes").isNotEmpty() }) { "the route is not drawn" }
    check(onMain { map!!.queryRenderedFeatures(everywhere, "pauses").isNotEmpty() }) { "the pause is not drawn" }
    // The pin stands on its place: tap its head, above the tip.
    val tip = onMain { map!!.projection.toScreenLocation(LatLng(35.27, 139.09)) }
    val density = instrumentation.targetContext.resources.displayMetrics.density
    rule.onRoot().performTouchInput { click(Offset(tip.x, tip.y - 16 * density)) }
    rule.waitUntil(10_000) { tapped.isNotEmpty() }
    check(tapped.last() == "a2") { "tapped ${tapped.last()}" }
  }
}
````

- [ ] **Step 3: スタイルと地図の部品を書く**

`app/src/main/assets/map/gsi-pale.json`（新規）:

````json
{
  "version": 8,
  "name": "gsi-pale",
  "sources": {
    "gsi": {
      "type": "raster",
      "tiles": ["https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png"],
      "tileSize": 256,
      "minzoom": 2,
      "maxzoom": 18,
      "attribution": "<a href=\"https://maps.gsi.go.jp/development/ichiran.html\">地理院タイル</a>"
    }
  },
  "layers": [{ "id": "gsi", "type": "raster", "source": "gsi" }]
}
````

`app/src/main/java/com/touringproject/v2/map/RouteMap.kt`（新規）:

````kotlin
package com.touringproject.v2.map

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.layers.RasterLayer
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource

// The map of SC-06 and SC-07: GSI's pale tiles with the route, the pauses, the ends and the numbered asks drawn from
// GeoJSON (slice 2 spec §7.7). MapLibre's MapView is wrapped in an AndroidView and follows the screen's lifecycle.

const val GSI_TILES_URL = "https://maps.gsi.go.jp/development/ichiran.html"
private const val STYLE_ASSET = "map/gsi-pale.json"
private const val ROUTE_COLOR = "#F06D1A"
private const val PAUSE_COLOR = "#8A929C"
private const val PIN_COLOR = 0xFFE8600F.toInt()
private const val PIN_SELECTED_COLOR = 0xFF1F4FD1.toInt()
/** The layer a tap on a pin is looked up in (slice 2 spec §7.7). */
const val PINS_LAYER = "pins"
// Japan as a whole, for a ride that has nothing to show yet.
private val JAPAN = LatLng(36.2, 138.25)

private fun styleJson(context: Context) = context.assets.open(STYLE_ASSET).bufferedReader().use { it.readText() }

/** A teardrop pin with its number, the tip at the bottom, as in the mock. */
fun pinBitmap(number: Int, selected: Boolean, density: Float): Bitmap {
  val radius = (if (selected) 16f else 13f) * density
  val stroke = 2f * density
  val tail = radius * 0.8f
  val width = (2 * (radius + stroke)).toInt()
  val height = (2 * (radius + stroke) + tail).toInt()
  val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
  val canvas = Canvas(bitmap)
  val cx = width / 2f
  val cy = radius + stroke
  val shape = Path().apply {
    addCircle(cx, cy, radius, Path.Direction.CW)
    moveTo(cx - radius * 0.6f, cy + radius * 0.7f)
    lineTo(cx, height - stroke)
    lineTo(cx + radius * 0.6f, cy + radius * 0.7f)
    close()
  }
  canvas.drawPath(shape, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = if (selected) PIN_SELECTED_COLOR else PIN_COLOR })
  canvas.drawPath(shape, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = android.graphics.Color.WHITE; style = Paint.Style.STROKE; strokeWidth = stroke })
  val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
    color = android.graphics.Color.WHITE
    textSize = 13f * density
    typeface = Typeface.DEFAULT_BOLD
    textAlign = Paint.Align.CENTER
  }
  canvas.drawText(number.toString(), cx, cy - (text.descent() + text.ascent()) / 2, text)
  return bitmap
}

private fun addLayers(style: Style, faint: Boolean, dark: Boolean) {
  // Dark mode dims the tiles instead of turning them over, so the colours of the land stay readable (slice 2 spec §7.7).
  if (dark) (style.getLayer("gsi") as? RasterLayer)?.setProperties(PropertyFactory.rasterBrightnessMax(0.55f), PropertyFactory.rasterSaturation(-0.4f))
  listOf("routes", "pauses", "ends", PINS_LAYER).forEach { style.addSource(GeoJsonSource(it)) }
  style.addLayer(
    LineLayer("pauses", "pauses").withProperties(
      PropertyFactory.lineColor(PAUSE_COLOR),
      PropertyFactory.lineWidth(3f),
      PropertyFactory.lineDasharray(arrayOf(1.3f, 2.3f)),
    ),
  )
  style.addLayer(
    LineLayer("routes", "routes").withProperties(
      PropertyFactory.lineColor(ROUTE_COLOR),
      PropertyFactory.lineWidth(if (faint) 4f else 5f),
      PropertyFactory.lineOpacity(if (faint) 0.45f else 0.92f),
      PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
      PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
    ),
  )
  style.addLayer(
    CircleLayer("ends", "ends").withProperties(
      PropertyFactory.circleRadius(7f),
      PropertyFactory.circleColor(Expression.match(Expression.get("kind"), Expression.literal("start"), Expression.color(0xFF13804A.toInt()), Expression.color(0xFF15181D.toInt()))),
      PropertyFactory.circleStrokeColor("#FFFFFF"),
      PropertyFactory.circleStrokeWidth(3f),
    ),
  )
  style.addLayer(
    SymbolLayer(PINS_LAYER, PINS_LAYER).withProperties(
      PropertyFactory.iconImage(Expression.get("icon")),
      PropertyFactory.iconAnchor(Property.ICON_ANCHOR_BOTTOM),
      PropertyFactory.iconAllowOverlap(true),
      PropertyFactory.iconIgnorePlacement(true),
    ),
  )
}

private fun draw(style: Style, data: MapData, selected: String?, density: Float) {
  data.pins.forEach { pin ->
    listOf(false, true).forEach { sel ->
      val name = pinIcon(pin.number, sel)
      if (style.getImage(name) == null) style.addImage(name, pinBitmap(pin.number, sel, density))
    }
  }
  style.getSourceAs<GeoJsonSource>("routes")?.setGeoJson(routesJson(data))
  style.getSourceAs<GeoJsonSource>("pauses")?.setGeoJson(pausesJson(data))
  style.getSourceAs<GeoJsonSource>("ends")?.setGeoJson(endsJson(data))
  style.getSourceAs<GeoJsonSource>(PINS_LAYER)?.setGeoJson(pinsJson(data, selected))
}

/** Takes in the whole route and every pin; a single place is shown close up (slice 2 spec §7.5). */
private fun fit(map: MapLibreMap, extent: List<LatLon>, padding: Int) {
  val places = extent.distinct()
  when {
    places.isEmpty() -> map.moveCamera(CameraUpdateFactory.newLatLngZoom(JAPAN, 4.5))
    places.size == 1 -> map.moveCamera(CameraUpdateFactory.newLatLngZoom(LatLng(places[0].lat, places[0].lon), 14.0))
    else -> map.moveCamera(
      CameraUpdateFactory.newLatLngBounds(LatLngBounds.Builder().includes(places.map { LatLng(it.lat, it.lon) }).build(), padding),
    )
  }
}

/**
 * onPin gets the askId of a tapped pin, or null for a tap elsewhere. The camera takes in data once its first places
 * arrive, and then stays where the rider moves it. onMap hands the map to the emulator tests once it has drawn.
 */
@Composable
fun RouteMap(
  data: MapData,
  selected: String?,
  onPin: (String?) -> Unit,
  modifier: Modifier = Modifier,
  onMap: (MapLibreMap) -> Unit = {},
) {
  val context = LocalContext.current
  val dark = isSystemInDarkTheme()
  val density = context.resources.displayMetrics.density
  val lifecycle = LocalLifecycleOwner.current.lifecycle
  val tapped by rememberUpdatedState(onPin)
  val ready by rememberUpdatedState(onMap)
  var loaded by remember { mutableStateOf<Pair<MapLibreMap, Style>?>(null) }
  var fitted by remember { mutableStateOf(false) }
  val view = remember {
    MapLibre.getInstance(context)
    MapView(context).apply { onCreate(null) }
  }
  DisposableEffect(lifecycle) {
    var state = Lifecycle.Event.ON_CREATE
    val observer = LifecycleEventObserver { _, event ->
      when (event) {
        Lifecycle.Event.ON_START -> view.onStart()
        Lifecycle.Event.ON_RESUME -> view.onResume()
        Lifecycle.Event.ON_PAUSE -> view.onPause()
        Lifecycle.Event.ON_STOP -> view.onStop()
        else -> Unit
      }
      state = event
    }
    lifecycle.addObserver(observer)
    onDispose {
      lifecycle.removeObserver(observer)
      if (state == Lifecycle.Event.ON_RESUME) view.onPause()
      if (state == Lifecycle.Event.ON_RESUME || state == Lifecycle.Event.ON_START || state == Lifecycle.Event.ON_PAUSE) view.onStop()
      view.onDestroy()
    }
  }
  LaunchedEffect(view) {
    view.getMapAsync { map ->
      map.uiSettings.isAttributionEnabled = false
      map.uiSettings.isLogoEnabled = false
      map.uiSettings.isCompassEnabled = false
      map.uiSettings.isRotateGesturesEnabled = false
      map.uiSettings.isTiltGesturesEnabled = false
      map.addOnMapClickListener { at ->
        val point = map.projection.toScreenLocation(at)
        val reach = 20f * density
        val hit = map.queryRenderedFeatures(RectF(point.x - reach, point.y - reach, point.x + reach, point.y + reach), PINS_LAYER)
        tapped(hit.firstOrNull()?.getStringProperty("askId"))
        true
      }
      map.setStyle(Style.Builder().fromJson(styleJson(context))) { style ->
        addLayers(style, data.faint, dark)
        loaded = map to style
        // Rendered features can be asked for only once the renderer has drawn: before that MapLibre crashes.
        var told = false
        view.addOnDidBecomeIdleListener {
          if (!told) {
            told = true
            ready(map)
          }
        }
      }
    }
  }
  LaunchedEffect(loaded, data, selected) {
    val (map, style) = loaded ?: return@LaunchedEffect
    draw(style, data, selected, density)
    // Until the first places arrive the map shows Japan, and the camera fits again once they do.
    if (!fitted) {
      fit(map, data.extent, (48 * density).toInt())
      fitted = data.extent.isNotEmpty()
    }
  }
  Box(modifier) {
    AndroidView({ view }, Modifier.matchParentSize())
    val uri = LocalUriHandler.current
    Text(
      "地理院タイル",
      fontSize = 10.sp,
      color = Color(0xFF333333),
      modifier = Modifier.align(Alignment.BottomEnd).background(Color(0xCCFFFFFF)).clickable { uri.openUri(GSI_TILES_URL) }.padding(horizontal = 4.dp, vertical = 1.dp),
    )
  }
}
````

- [ ] **Step 4: release の権限の検査が落ちるのを見る**

Run: `cd $AND && ./gradlew assembleRelease && scripts/check-release-permissions.sh`
Expected: 検査が `unexpected permissions ... android.permission.ACCESS_WIFI_STATE` で落ちる（MapLibre のマニフェストが持ち込む）。

- [ ] **Step 5: マニフェストで外す**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/AndroidManifest.xml b/app/src/main/AndroidManifest.xml
index b94f212..a2edda8 100644
--- a/app/src/main/AndroidManifest.xml
+++ b/app/src/main/AndroidManifest.xml
@@ -1,5 +1,6 @@
 <?xml version="1.0" encoding="utf-8"?>
-<manifest xmlns:android="http://schemas.android.com/apk/res/android">
+<manifest xmlns:android="http://schemas.android.com/apk/res/android"
+  xmlns:tools="http://schemas.android.com/tools">
 
   <uses-permission android:name="android.permission.INTERNET" />
   <uses-permission android:name="android.permission.RECORD_AUDIO" />
@@ -14,6 +15,8 @@
   <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
   <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />
   <uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION" />
+  <!-- MapLibre asks for it, but none of its code reads the Wi-Fi state (slice 2 plan 4a). -->
+  <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" tools:node="remove" />
 
   <!-- The return-app list (SC-10) and launching the nav app need to see launcher activities. -->
   <queries>
PATCH
````

Run: `cd $AND && ./gradlew assembleRelease && scripts/check-release-permissions.sh`
Expected: `release permissions OK (15)`。

- [ ] **Step 6: エミュレーターで地図のテストを通す**

エミュレーターを起こし、利用者にテストのあいだ触らないよう頼む。

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=com.touringproject.v2.map.RouteMapTest
```

Expected: 1件が通る（ルート・一時停止の破線・2つのピンが描かれ、2番のピンを押すと `a2` が返る）。描き終える前に問い合わせると、プロセスが落ちて「Process crashed」になる。`onMap` を描き終えてから呼んでいるかを見る。

- [ ] **Step 7: コミット**

```bash
cd $AND && git add gradle/libs.versions.toml app/build.gradle.kts app/src/main/AndroidManifest.xml app/src/main/assets/map/gsi-pale.json \
  app/src/main/java/com/touringproject/v2/map/RouteMap.kt app/src/androidTest/java/com/touringproject/v2/map/RouteMapTest.kt
git commit -m "feat: draw rides on GSI's pale map with MapLibre"
```

---
### Task 7: 記録の画面（SC-05・SC-06・SC-07）

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt`（新規）

**Interfaces:**
- Consumes: Task 4 の `MapData`、Task 5 の `RideSection`・`RideRowUi`・`RideSummaryUi`・`TimelineRow`・`PinCardUi`・`AskDetailUi`、既存の `cutRideName`・`rideName`。
- Produces: `typealias MapSlot = @Composable (data: MapData, selected: String?, onPin: (String?) -> Unit, modifier: Modifier) -> Unit`・`@Composable fun RideListScreen(sections: List<RideSection>?, onRide: (String) -> Unit, modifier)`（null は読み込み中）・`data class RideDetailUi(name, summary, recording, timeline, map, cards: Map<String, PinCardUi>)`・`@Composable fun RideDetailScreen(ui: RideDetailUi?, map: MapSlot, showPins, onShowPins, onBack, onAsk, onRename, onFullMap, modifier)`（null は「この走行は見つかりません。」）・`@Composable fun AskDetailScreen(detail: AskDetailUi?, map: MapData?, mapSlot: MapSlot, askId: String, onBack, onMove: (String) -> Unit, modifier)`。テストのタグ: `ride-<id>`・`state-<id>`・`rideList`・`timeline`・`ask-<id>`・`fullMap`・`pinToggle`・`pinCard`・`rideMenu`・`renameRide`・`renameInput`・`renameGo`・`summaryQuestions`・`autoEnded`・`askPrev`・`askNext`・`askQuestion`・`askAnswer`・`askFailure`・`askMap`・`back`。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt`（新規）:

````kotlin
package com.touringproject.v2.ui

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onChildAt
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextReplacement
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.touringproject.v2.map.LatLon
import com.touringproject.v2.map.MapData
import com.touringproject.v2.map.MapPin
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RecordsScreensTest {
  @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()

  /** Stands in for MapLibre: shows how many pins it was given and offers a button per pin. */
  private val fakeMap: MapSlot = { data, selected, onPin, modifier ->
    Column(modifier.testTag("map")) {
      Text("pins ${data.pins.size} selected $selected", Modifier.testTag("mapState"))
      data.pins.forEach { pin -> Button(onClick = { onPin(pin.askId) }, Modifier.testTag("pin-${pin.askId}")) { Text("${pin.number}") } }
    }
  }

  private val row = RideRowUi("r1", "箱根", "10月16日（金） · 08:58〜10:46", "52.8 km · 1:30 · 質問 2 · ⏸ 1", "保存済み", true)

  private fun detail(autoEnded: Boolean = false) = RideDetailUi(
    name = "箱根",
    summary = RideSummaryUi("10月16日（金）", "08:58〜10:46", "1:30", "52.8 km", "2", "一時停止 1回（18分）は走行時間に含めません", autoEnded),
    recording = false,
    timeline = listOf(
      TimelineRow.Ask("a1", 1, "09:41", "箱根町仙石原", "右手の山は？", false),
      TimelineRow.Pause("⏸ 一時停止 09:44〜10:02（18分）"),
      TimelineRow.NewConversation,
      TimelineRow.Ask("a2", 2, "10:30", "御殿場市", "（聞き取れませんでした）", true),
    ),
    map = MapData(emptyList(), emptyList(), null, null, listOf(MapPin("a1", 1, LatLon(35.2, 139.0)), MapPin("a2", 2, LatLon(35.3, 138.9)))),
    cards = mapOf("a1" to PinCardUi("a1", "1 · 09:41 · 箱根町仙石原", "右手の山は？", "金時山です。")),
  )

  private fun back() = rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }

  @Test
  fun the_list_shows_each_ride_under_its_month_and_opens_it() {
    val opened = mutableListOf<String>()
    rule.setContent { RideListScreen(listOf(RideSection("2026年10月", listOf(row))), { opened += it }) }
    rule.onNodeWithText("2026年10月").assertExists()
    rule.onNodeWithText("52.8 km · 1:30 · 質問 2 · ⏸ 1").assertExists()
    rule.onNodeWithTag("state-r1", useUnmergedTree = true).assertTextEquals("保存済み")
    rule.onNodeWithTag("ride-r1").performClick()
    assertEquals(listOf("r1"), opened)
  }

  @Test
  fun without_rides_the_list_says_how_to_record_one() {
    rule.setContent { RideListScreen(emptyList(), {}) }
    rule.onNodeWithText("まだ走行の記録がありません。ホームの「▶ 走行を開始」で記録します。").assertExists()
  }

  @Test
  fun the_detail_shows_the_summary_and_the_timeline_and_a_row_opens_its_ask() {
    val asked = mutableListOf<String>()
    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, { asked += it }, {}, {}) }
    rule.onNodeWithTag("summaryQuestions").onChildAt(0).assertTextEquals("2")
    // Robolectric's screen is small: the timeline under the map is scrolled to each row.
    val timeline = rule.onNodeWithTag("timeline")
    timeline.performScrollToNode(hasText("⏸ 一時停止 09:44〜10:02（18分）"))
    timeline.performScrollToNode(hasText("↻ ここから新しい会話"))
    timeline.performScrollToNode(hasTestTag("ask-a2"))
    rule.onNodeWithTag("ask-a2").performClick()
    assertEquals(listOf("a2"), asked)
  }

  @Test
  fun a_tapped_pin_shows_its_card_which_opens_the_ask() {
    val asked = mutableListOf<String>()
    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, { asked += it }, {}, {}) }
    rule.onNodeWithTag("pin-a1").performClick()
    rule.onNodeWithTag("mapState").assertTextEquals("pins 2 selected a1")
    rule.onNodeWithText("金時山です。").assertExists()
    rule.onNodeWithTag("pinCard").performClick()
    assertEquals(listOf("a1"), asked)
  }

  @Test
  fun the_pins_can_be_hidden_and_the_choice_goes_to_the_settings() {
    var shown by mutableStateOf(true)
    rule.setContent { RideDetailScreen(detail(), fakeMap, shown, { shown = it }, {}, {}, {}, {}) }
    rule.onNodeWithTag("pin-a1").performClick()
    rule.onNodeWithTag("pinToggle").performClick()
    rule.onNodeWithTag("mapState").assertTextEquals("pins 0 selected null")
    rule.onNodeWithTag("pinCard").assertDoesNotExist()
  }

  @Test
  fun the_map_fills_the_screen_until_back_and_tells_so() {
    val full = mutableListOf<Boolean>()
    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, {}, { full += it }) }
    rule.onNodeWithTag("fullMap").performClick()
    rule.waitForIdle()
    rule.onNodeWithTag("timeline").assertDoesNotExist()
    rule.onNodeWithTag("map").assertExists()
    back()
    rule.waitForIdle()
    rule.onNodeWithTag("timeline").assertExists()
    assertEquals(listOf(false, true, false), full)
  }

  @Test
  fun the_menu_renames_the_ride_but_not_to_an_empty_name() {
    val names = mutableListOf<String>()
    rule.setContent { RideDetailScreen(detail(), fakeMap, true, {}, {}, {}, { names += it }, {}) }
    rule.onNodeWithTag("rideMenu").performClick()
    rule.onNodeWithTag("renameRide").performClick()
    rule.onNodeWithTag("renameInput").performTextReplacement("  ")
    rule.onNodeWithTag("renameGo").assertIsNotEnabled()
    rule.onNodeWithTag("renameInput").performTextReplacement(" 御殿場 ")
    rule.onNodeWithTag("renameGo").performClick()
    assertEquals(listOf("御殿場"), names)
  }

  @Test
  fun a_ride_ended_by_its_longest_time_says_so() {
    rule.setContent { RideDetailScreen(detail(autoEnded = true), fakeMap, true, {}, {}, {}, {}, {}) }
    rule.onNodeWithTag("autoEnded").assertExists()
  }

  @Test
  fun the_ask_detail_moves_to_its_neighbours_and_tells_why_an_ask_failed() {
    val moves = mutableListOf<String>()
    val failed = AskDetailUi("会話 2 / 2", "10月16日（金） 10:30", "静岡県御殿場市", "停車中", "🎤 声で質問", null, null, "時間内に答えが届きませんでした", "a1", null)
    rule.setContent { AskDetailScreen(failed, null, fakeMap, "a2", {}, { moves += it }) }
    rule.onNodeWithText("会話 2 / 2").assertExists()
    rule.onNodeWithTag("askFailure").assertTextEquals("答えられませんでした: 時間内に答えが届きませんでした")
    rule.onNodeWithText("この質問の場所は分かりません。").assertExists()
    rule.onNodeWithTag("askNext").assertIsNotEnabled()
    rule.onNodeWithTag("askPrev").assertIsEnabled().performClick()
    assertEquals(listOf("a1"), moves)
  }

  @Test
  fun the_ask_detail_shows_the_question_and_answer_with_the_asks_place_on_the_map() {
    val answered = AskDetailUi("会話 1 / 2", "10月16日（金） 09:41", "神奈川県箱根町仙石原", "北東へ走行中（右手 南東・左手 北西）", "🎤 声で質問", "右手の山は？", "金時山です。", null, null, "a2")
    val map = MapData(emptyList(), emptyList(), null, null, listOf(MapPin("a1", 1, LatLon(35.2, 139.0))), faint = true, focus = LatLon(35.2, 139.0))
    rule.setContent { AskDetailScreen(answered, map, fakeMap, "a1", {}, {}) }
    rule.onNodeWithTag("askQuestion").assertTextEquals("右手の山は？")
    rule.onNodeWithTag("askAnswer").assertTextEquals("金時山です。")
    rule.onNodeWithTag("mapState").assertTextEquals("pins 1 selected a1")
    rule.onNodeWithText("北東へ走行中（右手 南東・左手 北西）").assertExists()
  }
}
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordsScreensTest'`
Expected: コンパイルの失敗（`Unresolved reference 'MapSlot'`）。

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt`（新規）:

````kotlin
package com.touringproject.v2.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.touringproject.v2.map.MapData
import com.touringproject.v2.ride.cutRideName
import com.touringproject.v2.ride.rideName

// SC-05, SC-06 and SC-07 (slice 2 spec §7.4–§7.6). The map comes in as a slot, so these screens are tested without
// MapLibre, which needs a real device.

/** Draws data; selected is the askId of the highlighted pin, and onPin gets a tapped pin's askId (null off the pins). */
typealias MapSlot = @Composable (data: MapData, selected: String?, onPin: (String?) -> Unit, modifier: Modifier) -> Unit

private val Accent = Color(0xFFE8600F)
private val Rec = Color(0xFFD42A2A)

@Composable
private fun TopBar(title: String, onBack: () -> Unit, actions: @Composable () -> Unit = {}) {
  Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
    TextButton(onClick = onBack, modifier = Modifier.testTag("back")) { Text("←", fontSize = 22.sp) }
    Text(title, Modifier.weight(1f), fontSize = 20.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
    actions()
  }
}

@Composable
private fun Muted(text: String, modifier: Modifier = Modifier, size: Int = 14) =
  Text(text, modifier, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = size.sp)

/** SC-05's rides, the one recording or paused first. The switch to the days comes with plan 4b. */
@Composable
fun RideListScreen(sections: List<RideSection>?, onRide: (String) -> Unit, modifier: Modifier = Modifier) {
  Column(modifier.fillMaxSize()) {
    Text("記録", Modifier.padding(16.dp), fontSize = 22.sp, fontWeight = FontWeight.Bold)
    when {
      sections == null -> Unit
      sections.isEmpty() -> Muted("まだ走行の記録がありません。ホームの「▶ 走行を開始」で記録します。", Modifier.padding(horizontal = 16.dp), 16)
      else -> LazyColumn(Modifier.fillMaxSize().testTag("rideList")) {
        sections.forEach { section ->
          item(key = section.month) { Muted(section.month, Modifier.padding(start = 16.dp, top = 12.dp, bottom = 4.dp)) }
          items(section.rows, key = { it.id }) { row -> RideRow(row, onRide) }
        }
      }
    }
  }
}

@Composable
private fun RideRow(row: RideRowUi, onRide: (String) -> Unit) {
  Column(Modifier.fillMaxWidth().clickable { onRide(row.id) }.padding(horizontal = 16.dp, vertical = 10.dp).testTag("ride-${row.id}")) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
      Text(row.name, Modifier.weight(1f), fontSize = 17.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
      Text(
        row.state, Modifier.padding(start = 8.dp).testTag("state-${row.id}"), fontSize = 13.sp,
        color = if (row.saved) MaterialTheme.colorScheme.onSurfaceVariant else Accent,
      )
    }
    Muted(row.date)
    Muted(row.stats)
  }
}

/** SC-06 as it is drawn. cards holds the card of each pin that can be tapped. */
data class RideDetailUi(
  val name: String,
  val summary: RideSummaryUi,
  val recording: Boolean,
  val timeline: List<TimelineRow>,
  val map: MapData,
  val cards: Map<String, PinCardUi>,
)

/**
 * SC-06. The map can fill the screen (onFullMap tells AppUi to hide the tabs), its pins can be hidden (showPins is
 * kept in the settings), and a tapped pin shows its card above the map's bottom edge.
 */
@Composable
fun RideDetailScreen(
  ui: RideDetailUi?,
  map: MapSlot,
  showPins: Boolean,
  onShowPins: (Boolean) -> Unit,
  onBack: () -> Unit,
  onAsk: (String) -> Unit,
  onRename: (String) -> Unit,
  onFullMap: (Boolean) -> Unit,
  modifier: Modifier = Modifier,
) {
  if (ui == null) {
    Column(modifier.fillMaxSize()) {
      TopBar("走行", onBack)
      Muted("この走行は見つかりません。", Modifier.padding(16.dp), 16)
    }
    return
  }
  var selected by rememberSaveable { mutableStateOf<String?>(null) }
  var full by rememberSaveable { mutableStateOf(false) }
  var menu by rememberSaveable { mutableStateOf(false) }
  var renaming by rememberSaveable { mutableStateOf<String?>(null) }
  LaunchedEffect(full) { onFullMap(full) }
  DisposableEffect(Unit) { onDispose { onFullMap(false) } }
  BackHandler(enabled = full) { full = false }
  val shown = if (showPins) ui.map else ui.map.copy(pins = emptyList())
  val card = selected?.takeIf { showPins }?.let { ui.cards[it] }
  val mapArea: @Composable (Modifier) -> Unit = { area ->
    Box(area) {
      map(shown, selected.takeIf { showPins }, { selected = it }, Modifier.fillMaxSize())
      TextButton(
        onClick = { full = !full },
        modifier = Modifier.align(Alignment.TopStart).padding(6.dp).background(MaterialTheme.colorScheme.surface, RoundedCornerShape(8.dp)).testTag("fullMap"),
      ) { Text(if (full) "✕" else "⛶", fontSize = 18.sp) }
      FilterChip(
        selected = showPins,
        onClick = { onShowPins(!showPins) },
        label = { Text("💬 質問") },
        modifier = Modifier.align(Alignment.TopEnd).padding(6.dp).testTag("pinToggle"),
      )
      card?.let { PinCard(it, { onAsk(it.askId) }, Modifier.align(Alignment.BottomCenter).padding(8.dp)) }
    }
  }
  if (full) {
    mapArea(modifier.fillMaxSize())
  } else {
    Column(modifier.fillMaxSize()) {
      TopBar(ui.name, onBack) {
        Box {
          TextButton(onClick = { menu = true }, modifier = Modifier.testTag("rideMenu")) { Text("⋮", fontSize = 22.sp) }
          DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
            DropdownMenuItem(text = { Text("名前を変える") }, onClick = {
              menu = false
              renaming = ui.name
            }, modifier = Modifier.testTag("renameRide"))
          }
        }
      }
      mapArea(Modifier.fillMaxWidth().height(280.dp))
      LazyColumn(Modifier.fillMaxSize().testTag("timeline")) {
        item { Summary(ui.summary, ui.recording) }
        item { Muted("時系列", Modifier.padding(start = 16.dp, top = 12.dp, bottom = 4.dp)) }
        if (ui.timeline.isEmpty()) item { Muted("この走行の記録中にした質問はありません。", Modifier.padding(horizontal = 16.dp)) }
        items(ui.timeline) { row -> TimelineItem(row, onAsk) }
      }
    }
  }
  renaming?.let { name ->
    AlertDialog(
      onDismissRequest = { renaming = null },
      title = { Text("名前を変える") },
      text = {
        OutlinedTextField(name, { renaming = cutRideName(it) }, Modifier.fillMaxWidth().testTag("renameInput"), label = { Text("この走行の名前") }, singleLine = true)
      },
      confirmButton = {
        TextButton(
          onClick = { rideName(name)?.let(onRename); renaming = null },
          enabled = rideName(name) != null,
          modifier = Modifier.testTag("renameGo"),
        ) { Text("変える") }
      },
      dismissButton = { TextButton(onClick = { renaming = null }) { Text("やめる") } },
    )
  }
}

@Composable
private fun PinCard(card: PinCardUi, onOpen: () -> Unit, modifier: Modifier = Modifier) {
  Column(
    modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp)).clickable(onClick = onOpen)
      .padding(12.dp).testTag("pinCard"),
  ) {
    Muted(card.heading, size = 13)
    Text(card.question, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
    card.answer?.let { Text(it, maxLines = 2, overflow = TextOverflow.Ellipsis, fontSize = 14.sp) }
    Text("詳しく見る ›", color = Accent, fontWeight = FontWeight.Bold, fontSize = 14.sp)
  }
}

@Composable
private fun Summary(summary: RideSummaryUi, recording: Boolean) {
  Column(
    Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(16.dp))
      .padding(14.dp),
    verticalArrangement = Arrangement.spacedBy(6.dp),
  ) {
    Muted("${summary.date} · ${summary.span}")
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround) {
      SummaryStat(summary.elapsed, "走行時間")
      SummaryStat(summary.distance, "距離")
      SummaryStat(summary.questions, "質問", Modifier.testTag("summaryQuestions"))
    }
    summary.pauses?.let { Muted(it) }
    if (summary.autoEnded) Text("最長時間に達したため、自動で終了しました", color = Rec, fontSize = 14.sp, modifier = Modifier.testTag("autoEnded"))
    if (recording) Muted("記録中の走行です。ルートは開いたときまでのものです。")
  }
}

@Composable
private fun SummaryStat(value: String, label: String, modifier: Modifier = Modifier) {
  Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
    Text(value, fontSize = 22.sp, fontWeight = FontWeight.Bold)
    Muted(label, size = 13)
  }
}

@Composable
private fun TimelineItem(row: TimelineRow, onAsk: (String) -> Unit) {
  when (row) {
    is TimelineRow.Day -> Text(row.label, Modifier.padding(start = 16.dp, top = 12.dp, bottom = 4.dp), fontWeight = FontWeight.Bold)
    is TimelineRow.Pause -> Muted(row.label, Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
    TimelineRow.NewConversation -> Muted("↻ ここから新しい会話", Modifier.padding(horizontal = 16.dp, vertical = 6.dp), 13)
    is TimelineRow.Ask -> Row(
      Modifier.fillMaxWidth().clickable { onAsk(row.askId) }.padding(horizontal = 16.dp, vertical = 8.dp).testTag("ask-${row.askId}"),
      horizontalArrangement = Arrangement.spacedBy(12.dp),
      verticalAlignment = Alignment.CenterVertically,
    ) {
      Box(Modifier.size(28.dp).background(Accent, CircleShape), contentAlignment = Alignment.Center) {
        Text(row.number.toString(), color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
      }
      Column(Modifier.weight(1f)) {
        Muted("${row.time} · ${row.place}", size = 13)
        Text(
          row.text, maxLines = 2, overflow = TextOverflow.Ellipsis,
          fontWeight = if (row.failed) FontWeight.Normal else FontWeight.Bold,
          color = if (row.failed) MaterialTheme.colorScheme.onSurfaceVariant else Color.Unspecified,
        )
      }
    }
  }
}

/**
 * SC-07. map is the ask's place on the faint route of its ride (null when the ask has no place). ‹ › move among the
 * ride's asks; the map is made again for each ask, so it opens on that ask.
 */
@Composable
fun AskDetailScreen(detail: AskDetailUi?, map: MapData?, mapSlot: MapSlot, askId: String, onBack: () -> Unit, onMove: (String) -> Unit, modifier: Modifier = Modifier) {
  Column(modifier.fillMaxSize()) {
    TopBar(detail?.title ?: "会話", onBack) {
      TextButton(onClick = { detail?.previous?.let(onMove) }, enabled = detail?.previous != null, modifier = Modifier.testTag("askPrev")) { Text("‹", fontSize = 24.sp) }
      TextButton(onClick = { detail?.next?.let(onMove) }, enabled = detail?.next != null, modifier = Modifier.testTag("askNext")) { Text("›", fontSize = 24.sp) }
    }
    if (detail == null) {
      Muted("この会話は見つかりません。", Modifier.padding(16.dp), 16)
      return
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
      if (map != null) key(askId) { mapSlot(map, askId, {}, Modifier.fillMaxWidth().height(160.dp).testTag("askMap")) }
      else Muted("この質問の場所は分かりません。")
      Column(
        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp)).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
      ) {
        Meta("日時", detail.time)
        Meta("場所", detail.place)
        Meta("進行方向", detail.direction)
        Meta("入力", detail.input)
      }
      Muted("あなた", Modifier.align(Alignment.End), 13)
      Text(
        detail.question ?: "（聞き取れませんでした）",
        Modifier.align(Alignment.End).background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(12.dp)).padding(12.dp).testTag("askQuestion"),
      )
      Muted("AI", size = 13)
      if (detail.failure != null) {
        Text("答えられませんでした: ${detail.failure}", color = Rec, modifier = Modifier.testTag("askFailure"))
      } else {
        Text(
          detail.answer ?: "",
          Modifier.background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp)).padding(12.dp).testTag("askAnswer"),
        )
      }
    }
  }
}

@Composable
private fun Meta(label: String, value: String) {
  Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
    Muted(label, Modifier.padding(top = 1.dp), 13)
    Text(value, fontSize = 15.sp)
  }
}
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*RecordsScreensTest' --rerun`
Expected: 10件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RecordsScreens.kt app/src/test/java/com/touringproject/v2/ui/RecordsScreensTest.kt
git commit -m "feat: add the ride list, the ride detail and the ask detail screens"
```

---
### Task 8: AppGraph の組み込み（#33・#35・ピンの表示の設定）

**Files:**
- Modify: `app/src/main/java/com/touringproject/v2/settings/Settings.kt`・`app/src/main/java/com/touringproject/v2/records/Records.kt`・`app/src/main/java/com/touringproject/v2/AppGraph.kt`・`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`
- Test: `app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt`・`app/src/test/java/com/touringproject/v2/records/RecordsTest.kt`

**Interfaces:**
- Consumes: Task 3 の `RoomRecords`・`AskDao.countForRide`。
- Produces: `Settings.showAskPins: Boolean = true`（DataStore の JSON。壊れた値は既定）・`fun maxRecordingChanges(settings: Flow<Settings?>): Flow<Int>`（最初に読み込んだ値は流さない）・`fun activeAskCount(activeId: Flow<String?>, count: (String) -> Flow<Int>): Flow<Int>`・`AppGraph.records: RoomRecords`・`AppGraph.activeAskCount: StateFlow<Int>`。`AppGraph.askCount` は消す。

- [ ] **Step 1: 失敗するテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/records/RecordsTest.kt b/app/src/test/java/com/touringproject/v2/records/RecordsTest.kt
index 591383d..4d22cf4 100644
--- a/app/src/test/java/com/touringproject/v2/records/RecordsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/records/RecordsTest.kt
@@ -5,6 +5,10 @@ import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.RideStatus
 import com.touringproject.v2.ride.end
 import com.touringproject.v2.ride.newRide
+import kotlinx.coroutines.flow.MutableStateFlow
+import kotlinx.coroutines.launch
+import kotlinx.coroutines.test.runCurrent
+import kotlinx.coroutines.test.runTest
 import org.junit.Assert.assertEquals
 import org.junit.Test
 
@@ -31,4 +35,23 @@ class RecordsTest {
     val items = listOf(old, active, new).map { RideListItem(it, 0, SaveState.SAVED) }
     assertEquals(listOf("active", "new", "old"), orderRides(items).map { it.ride.id })
   }
+
+  @Test
+  fun the_active_rides_count_follows_the_ride_and_is_0_without_one() = runTest {
+    val active = MutableStateFlow<String?>(null)
+    val counts = mapOf("r1" to MutableStateFlow(2), "r2" to MutableStateFlow(5))
+    val seen = mutableListOf<Int>()
+    val job = backgroundScope.launch { activeAskCount(active) { counts.getValue(it) }.collect { seen += it } }
+    runCurrent()
+    active.value = "r1"
+    runCurrent()
+    counts.getValue("r1").value = 3
+    runCurrent()
+    active.value = "r2"
+    runCurrent()
+    active.value = null
+    runCurrent()
+    assertEquals(listOf(0, 2, 3, 5, 0), seen)
+    job.cancel()
+  }
 }
diff --git a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
index 962f025..11a608b 100644
--- a/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt
@@ -1,5 +1,7 @@
 package com.touringproject.v2.settings
 
+import kotlinx.coroutines.flow.MutableStateFlow
+import kotlinx.coroutines.launch
 import kotlinx.coroutines.test.runTest
 import org.junit.Assert.assertEquals
 import org.junit.Assert.assertFalse
@@ -37,14 +39,14 @@ class SettingsTest {
   fun saved_settings_round_trip() = runTest {
     val store = FakeStore()
     val repo = SettingsRepository(store)
-    val s = Settings("rider01", returnEnabled = false, returnApp = maps, returnTiming = ReturnTiming.SPOKEN, recentApps = listOf(maps), answerVolumeDb = 3, maxRecordingHours = 6)
+    val s = Settings("rider01", returnEnabled = false, returnApp = maps, returnTiming = ReturnTiming.SPOKEN, recentApps = listOf(maps), answerVolumeDb = 3, maxRecordingHours = 6, showAskPins = false)
     repo.update(s)
     assertEquals(s, SettingsRepository(store).load())
   }
 
   @Test
   fun broken_values_fall_back_to_defaults() {
-    val raw = """{"userName":"NO","returnEnabled":"yes","returnApp":{"packageName":1},"returnTiming":"later","recentApps":[{"packageName":"a","label":"A"},3],"answerVolumeDb":12,"maxRecordingHours":72}"""
+    val raw = """{"userName":"NO","returnEnabled":"yes","returnApp":{"packageName":1},"returnTiming":"later","recentApps":[{"packageName":"a","label":"A"},3],"answerVolumeDb":12,"maxRecordingHours":72,"showAskPins":"no"}"""
     val (s, needsSave) = decodeSettings(raw, Random(2))
     assertTrue(needsSave)
     assertTrue(s.returnEnabled)
@@ -53,6 +55,7 @@ class SettingsTest {
     assertEquals(listOf(LaunchableApp("a", "A")), s.recentApps)
     assertEquals(DEFAULT_VOLUME_DB, s.answerVolumeDb)
     assertEquals(DEFAULT_MAX_RECORDING_HOURS, s.maxRecordingHours)
+    assertTrue(s.showAskPins)
   }
 
   @Test
@@ -98,6 +101,25 @@ class SettingsTest {
     assertEquals("••••••••7890", maskKey("abcdef1234567890"))
     assertEquals("••••", maskKey("abcd"))
   }
+
+  // Android #33: AppGraph moves the recording ride's deadline on each change, not on the first load.
+  @Test
+  fun only_a_changed_longest_recording_time_is_passed_on() = runTest {
+    val settings = MutableStateFlow<Settings?>(null)
+    val seen = mutableListOf<Int>()
+    val job = backgroundScope.launch { maxRecordingChanges(settings).collect { seen += it } }
+    testScheduler.runCurrent()
+    settings.value = Settings("rider01")
+    testScheduler.runCurrent()
+    settings.value = Settings("rider01", answerVolumeDb = 3)
+    testScheduler.runCurrent()
+    settings.value = Settings("rider01", maxRecordingHours = 6)
+    testScheduler.runCurrent()
+    settings.value = Settings("rider01", maxRecordingHours = 48)
+    testScheduler.runCurrent()
+    assertEquals(listOf(6, 48), seen)
+    job.cancel()
+  }
 }
 
 class ApiKeyStoreTest {
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*SettingsTest' --tests '*.RecordsTest'`
Expected: コンパイルの失敗（`No parameter with name 'showAskPins'`・`Unresolved reference 'activeAskCount'`）。

- [ ] **Step 3: 実装する**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/AppGraph.kt b/app/src/main/java/com/touringproject/v2/AppGraph.kt
index dddd620..8fe6ae3 100644
--- a/app/src/main/java/com/touringproject/v2/AppGraph.kt
+++ b/app/src/main/java/com/touringproject/v2/AppGraph.kt
@@ -33,6 +33,7 @@ import com.touringproject.v2.recordings.TRIAL_IDLE
 import com.touringproject.v2.recordings.TrialController
 import com.touringproject.v2.recordings.TrialDeps
 import com.touringproject.v2.recordings.TrialState
+import com.touringproject.v2.records.activeAskCount
 import com.touringproject.v2.ride.HOUR_MS
 import com.touringproject.v2.ride.RideController
 import com.touringproject.v2.ride.RideDeps
@@ -46,18 +47,22 @@ import com.touringproject.v2.settings.DEFAULT_MAX_RECORDING_HOURS
 import com.touringproject.v2.settings.DataStoreKeyValueStore
 import com.touringproject.v2.settings.KeystoreCipher
 import com.touringproject.v2.settings.SettingsRepository
+import com.touringproject.v2.settings.maxRecordingChanges
 import com.touringproject.v2.store.RideDatabase
 import com.touringproject.v2.store.RoomAskLog
+import com.touringproject.v2.store.RoomRecords
 import com.touringproject.v2.store.RoomRideStore
 import com.touringproject.v2.store.RoomSyncStore
 import com.touringproject.v2.sync.RideSync
 import kotlinx.coroutines.CoroutineScope
 import kotlinx.coroutines.MainScope
 import kotlinx.coroutines.delay
-import kotlinx.coroutines.flow.Flow
 import kotlinx.coroutines.flow.MutableStateFlow
+import kotlinx.coroutines.flow.SharingStarted
 import kotlinx.coroutines.flow.StateFlow
 import kotlinx.coroutines.flow.asStateFlow
+import kotlinx.coroutines.flow.map
+import kotlinx.coroutines.flow.stateIn
 import kotlinx.coroutines.launch
 import okhttp3.OkHttpClient
 import java.io.File
@@ -83,9 +88,8 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
   private val database = RideDatabase.open(context)
   val rideStore = RoomRideStore(database.rides())
   val askLog = RoomAskLog(database.asks(), scope) { message, e -> Log.w("trv2.ask", message, e) }
-
-  /** How many asks the device keeps for the ride (SC-02, SC-04). */
-  fun askCount(rideId: String): Flow<Int> = database.asks().countForRide(rideId)
+  /** What the Records tab reads (SC-05, SC-06, SC-07). */
+  val records = RoomRecords(database.rides(), database.asks())
   private val notices = RideNotices(context)
 
   /** Sends rides and routes; a pass runs on each trigger (slice 2 spec §5.3). */
@@ -116,6 +120,10 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
     ),
   )
 
+  /** How many asks the device keeps for the ride recording or paused (SC-02, SC-04; Android #35). */
+  val activeAskCount: StateFlow<Int> =
+    activeAskCount(rides.active.map { it?.id }, database.asks()::countForRide).stateIn(scope, SharingStarted.Eagerly, 0)
+
   private val flowState = MutableStateFlow(IDLE)
   val state: StateFlow<FlowState> = flowState.asStateFlow()
 
@@ -208,6 +216,8 @@ class AppGraph(private val context: Context, val scope: CoroutineScope = MainSco
       readiness.ridesLoaded()
     }
     scope.launch { sync.run() }
+    // SC-16: the recording ride's deadline follows the longest recording time, wherever it was changed (Android #33).
+    scope.launch { maxRecordingChanges(settings.settings).collect { rides.maxRecordingChanged() } }
     scope.launch {
       settings.load()
       apiKeys.load()
diff --git a/app/src/main/java/com/touringproject/v2/records/Records.kt b/app/src/main/java/com/touringproject/v2/records/Records.kt
index 2669ee0..aab72e3 100644
--- a/app/src/main/java/com/touringproject/v2/records/Records.kt
+++ b/app/src/main/java/com/touringproject/v2/records/Records.kt
@@ -3,6 +3,11 @@ package com.touringproject.v2.records
 import com.touringproject.v2.ride.Ride
 import com.touringproject.v2.ride.RideStatus
 import com.touringproject.v2.ride.startedAt
+import kotlinx.coroutines.ExperimentalCoroutinesApi
+import kotlinx.coroutines.flow.Flow
+import kotlinx.coroutines.flow.distinctUntilChanged
+import kotlinx.coroutines.flow.flatMapLatest
+import kotlinx.coroutines.flow.flowOf
 
 // What SC-05 lists: the kept rides and how far each has reached the Backend (slice 2 spec §5.4, §7.4).
 
@@ -21,6 +26,14 @@ fun saveState(status: RideStatus, updatedAt: Long, sentUpdatedAt: Long?, pointsL
 /** questions counts the asks kept for the ride, answered or failed. */
 data class RideListItem(val ride: Ride, val questions: Int, val saveState: SaveState)
 
+/**
+ * How many asks the active ride has kept, following the ride (SC-02, SC-04). AppGraph holds it as a StateFlow, so a
+ * screen made again shows the count at once instead of 0 (Android #35).
+ */
+@OptIn(ExperimentalCoroutinesApi::class)
+fun activeAskCount(activeId: Flow<String?>, count: (String) -> Flow<Int>): Flow<Int> =
+  activeId.distinctUntilChanged().flatMapLatest { id -> id?.let(count) ?: flowOf(0) }
+
 /** The ride recording or paused comes first, then the others, newest first (SC-05). */
 fun orderRides(items: List<RideListItem>): List<RideListItem> =
   items.sortedWith(compareBy<RideListItem> { it.ride.status == RideStatus.ENDED }.thenByDescending { it.ride.startedAt() })
diff --git a/app/src/main/java/com/touringproject/v2/settings/Settings.kt b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
index 1d77277..63d9f12 100644
--- a/app/src/main/java/com/touringproject/v2/settings/Settings.kt
+++ b/app/src/main/java/com/touringproject/v2/settings/Settings.kt
@@ -1,5 +1,9 @@
 package com.touringproject.v2.settings
 
+import kotlinx.coroutines.flow.Flow
+import kotlinx.coroutines.flow.distinctUntilChanged
+import kotlinx.coroutines.flow.drop
+import kotlinx.coroutines.flow.mapNotNull
 import kotlinx.serialization.Serializable
 import kotlinx.serialization.json.Json
 import kotlinx.serialization.json.JsonObject
@@ -34,8 +38,17 @@ data class Settings(
   val recentApps: List<LaunchableApp> = emptyList(),
   val answerVolumeDb: Int = DEFAULT_VOLUME_DB,
   val maxRecordingHours: Int = DEFAULT_MAX_RECORDING_HOURS,
+  /** SC-06: whether the map shows the asks' pins; kept for the next time a ride is opened (slice 2 spec §7.5). */
+  val showAskPins: Boolean = true,
 )
 
+/**
+ * The longest recording time each time the rider changes it, but not the value first loaded (US-C-08.005). AppGraph
+ * follows it, so the recording ride's deadline moves even when SC-16 goes away mid-save (Android #33).
+ */
+fun maxRecordingChanges(settings: Flow<Settings?>): Flow<Int> =
+  settings.mapNotNull { it?.maxRecordingHours }.distinctUntilChanged().drop(1)
+
 val USER_NAME_RE = Regex("^[a-z0-9]{3,20}$")
 private const val ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
 private val json = Json { ignoreUnknownKeys = true }
@@ -60,6 +73,7 @@ fun decodeSettings(raw: String?, random: Random = Random.Default): Pair<Settings
       ?.takeIf { it in VOLUME_DB_CHOICES } ?: DEFAULT_VOLUME_DB,
     maxRecordingHours = runCatching { obj["maxRecordingHours"]?.jsonPrimitive?.intOrNull }.getOrNull()
       ?.takeIf { it in MAX_RECORDING_HOURS_CHOICES } ?: DEFAULT_MAX_RECORDING_HOURS,
+    showAskPins = runCatching { obj["showAskPins"]?.jsonPrimitive?.booleanOrNull }.getOrNull() ?: true,
   )
   return settings to (savedName == null)
 }
@@ -74,6 +88,7 @@ fun encodeSettings(settings: Settings): String = json.encodeToString(
     recentApps = settings.recentApps,
     answerVolumeDb = settings.answerVolumeDb,
     maxRecordingHours = settings.maxRecordingHours,
+    showAskPins = settings.showAskPins,
   ),
 )
 
@@ -86,6 +101,7 @@ private data class SavedSettings(
   val recentApps: List<LaunchableApp>,
   val answerVolumeDb: Int,
   val maxRecordingHours: Int,
+  val showAskPins: Boolean,
 )
 
 fun withRecentApp(recent: List<LaunchableApp>, app: LaunchableApp, max: Int = 5): List<LaunchableApp> =
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index f1d2210..abc5252 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -38,7 +38,6 @@ import com.touringproject.v2.api.ApiClient
 import com.touringproject.v2.ask.isBusy
 import com.touringproject.v2.settings.LaunchableApp
 import kotlinx.coroutines.delay
-import kotlinx.coroutines.flow.flowOf
 import kotlinx.coroutines.launch
 import java.time.ZoneId
 import kotlinx.serialization.Serializable
@@ -78,7 +77,7 @@ fun AppUi(graph: AppGraph) {
   val ride by graph.rides.active.collectAsStateWithLifecycle()
   val storeFailed by graph.rides.storeFailed.collectAsStateWithLifecycle()
   val askStoreFailed by graph.askLog.failed.collectAsStateWithLifecycle()
-  val questions by remember(ride?.id) { ride?.id?.let(graph::askCount) ?: flowOf(0) }.collectAsStateWithLifecycle(0)
+  val questions by graph.activeAskCount.collectAsStateWithLifecycle()
   // Saveable: SC-17 and SC-04 stay open when the activity is recreated, e.g. on rotation (Android #20).
   var sheet by rememberSaveable { mutableStateOf<RideSheet?>(null) }
   val now = rememberNow(ride != null)
@@ -162,17 +161,8 @@ fun AppUi(graph: AppGraph) {
                 )
               }
               entry<RideRecordingKey> {
-                RideRecordingScreen(
-                  current,
-                  { next ->
-                    scope.launch {
-                      graph.settings.update(next)
-                      // The recording ride's deadline follows at once (US-C-08.005).
-                      graph.rides.maxRecordingChanged()
-                    }
-                  },
-                  Modifier.safeDrawingPadding(),
-                )
+                // AppGraph moves the recording ride's deadline when the setting changes (US-C-08.005, Android #33).
+                RideRecordingScreen(current, { next -> scope.launch { graph.settings.update(next) } }, Modifier.safeDrawingPadding())
               }
               entry<VolumeKey> {
                 VolumeScreen(current, { next -> scope.launch { graph.settings.update(next) } }, Modifier.safeDrawingPadding())
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*SettingsTest' --tests '*.RecordsTest' --tests '*AppUiTest' --tests '*MainActivityTest' --rerun`
Expected: `SettingsTest` 10件・`RecordsTest` 4件・`AppUiTest` 4件・`MainActivityTest` 4件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/settings/Settings.kt app/src/main/java/com/touringproject/v2/records/Records.kt \
  app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt app/src/test/java/com/touringproject/v2/records/RecordsTest.kt
git commit -m "fix: follow the longest recording time and the active ride's ask count in AppGraph" -m "Fixes #33" -m "Fixes #35"
```

---
### Task 9: 記録のタブの組み込みとタブの整理（#32・#34・#36・#37）

**Files:**
- Create: `app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt`
- Modify: `app/src/main/java/com/touringproject/v2/ui/AppUi.kt`・`app/src/main/java/com/touringproject/v2/ui/Tabs.kt`・`app/src/main/java/com/touringproject/v2/ui/TabBar.kt`・`app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt`
- Test: `app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt`・`app/src/test/java/com/touringproject/v2/ui/TabsTest.kt`

**Interfaces:**
- Consumes: Task 2 の `RideController.rename`、Task 3 の `RoomRecords`、Task 5 の表示の関数、Task 6 の `RouteMap`、Task 7 の画面、Task 8 の `AppGraph.records`・`Settings.showAskPins`。
- Produces: `@Serializable data class RideKey(val rideId: String) : NavKey`・`@Serializable data class AskKey(val rideId: String, val askId: String) : NavKey`・`val routeMap: MapSlot`・`fun rideDetailUi(ride, asks, route, now, zone): RideDetailUi`・`fun askMap(ask, asks, route, ended): MapData?`・`@Composable fun RideDetailRoute(...)`・`@Composable fun AskDetailRoute(...)`・`TabStacks.onAnotherTabsFirst`（`canGoBack` は消す）。`RecordsPlaceholder` は消す。

- [ ] **Step 1: 失敗するテストを書く**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
index bd87e9a..6cfd172 100644
--- a/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt
@@ -1,12 +1,20 @@
 package com.touringproject.v2.ui
 
+import androidx.compose.ui.test.assertTextContains
 import androidx.compose.ui.test.junit4.createAndroidComposeRule
 import androidx.compose.ui.test.onNodeWithTag
 import androidx.compose.ui.test.onNodeWithText
 import androidx.compose.ui.test.performClick
+import androidx.compose.ui.test.performTextInput
 import androidx.test.ext.junit.runners.AndroidJUnit4
 import com.touringproject.v2.MainActivity
 import com.touringproject.v2.TouringApp
+import com.touringproject.v2.ride.EndReason
+import com.touringproject.v2.ride.HOUR_MS
+import com.touringproject.v2.ride.end
+import com.touringproject.v2.ride.newRide
+import kotlinx.coroutines.runBlocking
+import org.junit.Assert.assertFalse
 import org.junit.Before
 import org.junit.Rule
 import org.junit.Test
@@ -36,22 +44,56 @@ class AppUiTest {
   }
 
   @Test
-  fun the_records_tab_says_its_list_comes_later_and_home_keeps_its_place() {
+  fun the_records_tab_lists_the_kept_rides_and_home_keeps_its_place() {
+    val graph = (rule.activity.application as TouringApp).graph
     rule.onNodeWithTag("tab-RECORDS").performClick()
-    rule.onNodeWithText("走行と日ごとの記録の一覧は、次の版でここに出ます。").assertExists()
+    rule.onNodeWithText("まだ走行の記録がありません。ホームの「▶ 走行を開始」で記録します。").assertExists()
+    val ride = newRide("r1", "箱根", 1_000, 7, 24 * HOUR_MS).end(5_000, EndReason.MANUAL, 5_000)
+    runBlocking { graph.rideStore.save(ride) }
+    rule.waitUntil(5_000) { rule.onAllNodesWithTagExists("ride-r1") }
+    rule.onNodeWithText("箱根").assertExists()
     rule.onNodeWithTag("tab-HOME").performClick()
     rule.onNodeWithTag("tapToTalk").assertExists()
   }
 
+  // Android #36: from deep in Settings, the user chip opens the user name above Settings' first screen.
   @Test
-  fun the_user_chip_opens_the_user_name_in_the_settings_tab() {
+  fun the_user_chip_opens_the_user_name_above_the_first_settings_screen() {
     val graph = (rule.activity.application as TouringApp).graph
+    rule.onNodeWithTag("tab-SETTINGS").performClick()
+    rule.onNodeWithText("回答の音量").performClick()
+    rule.onNodeWithTag("tab-HOME").performClick()
     rule.onNodeWithText(graph.settings.current().userName).performClick()
-    rule.onNodeWithTag("tab-SETTINGS").assertExists()
+    rule.onNodeWithTag("userInput").assertExists()
     back()
     rule.onNodeWithText("走行の記録").assertExists()
   }
 
+  // Android #34
+  @Test
+  fun a_name_being_typed_survives_a_trip_to_another_tab() {
+    rule.onNodeWithTag("tab-SETTINGS").performClick()
+    rule.onNodeWithText("ユーザー名").performClick()
+    rule.onNodeWithTag("userInput").performTextInput("rider02")
+    rule.onNodeWithTag("tab-HOME").performClick()
+    rule.onNodeWithTag("tab-SETTINGS").performClick()
+    rule.onNodeWithTag("userInput").assertTextContains("rider02")
+  }
+
+  // Android #32: on Home's first screen the app takes no Back; the system moves the app to the back.
+  @Test
+  fun the_app_leaves_back_on_homes_first_screen_to_the_system() {
+    rule.onNodeWithTag("tapToTalk").assertExists()
+    assertFalse(rule.activity.onBackPressedDispatcher.hasEnabledCallbacks())
+  }
+
+  // Android #36: the ask screen covers the tabs. Without a connection key the ask fails at once and says so.
+  @Test
+  fun the_tabs_hide_while_an_ask_is_on_screen() {
+    rule.onNodeWithTag("tapToTalk").performClick()
+    rule.waitUntil(5_000) { !rule.onAllNodesWithTagExists("tab-HOME") }
+  }
+
   @Test
   fun the_start_sheet_stays_open_when_the_activity_is_recreated() {
     rule.onNodeWithTag("startRide").performClick()
diff --git a/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt b/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
index f100410..68fc9ca 100644
--- a/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
+++ b/app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
@@ -37,12 +37,13 @@ class TabsTest {
   fun back_goes_back_within_the_tab_then_to_home_then_leaves_the_app() {
     tabs.press(Tab.SETTINGS)
     tabs.current += "volume"
-    assertTrue(tabs.canGoBack)
+    assertFalse(tabs.onAnotherTabsFirst)
     assertTrue(tabs.back())
     assertEquals(listOf("settings"), tabs.current)
+    assertTrue(tabs.onAnotherTabsFirst)
     assertTrue(tabs.back())
     assertEquals(Tab.HOME, selected)
-    assertFalse(tabs.canGoBack)
+    assertFalse(tabs.onAnotherTabsFirst)
     assertFalse(tabs.back())
     assertEquals(Tab.HOME, selected)
   }
PATCH
````

- [ ] **Step 2: 走らせて落ちるのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*TabsTest'`
Expected: コンパイルの失敗（`Unresolved reference 'onAnotherTabsFirst'`）。

`TabsTest` の変更をいったん外して（`git stash push app/src/test/java/com/touringproject/v2/ui/TabsTest.kt`）`--tests '*AppUiTest' --rerun` を回すと、7件のうち `the_records_tab_lists_the_kept_rides_and_home_keeps_its_place`（一覧が無い）と `a_name_being_typed_survives_a_trip_to_another_tab`（打ち込んだ文字が消える）の2件が落ちる。ほかの3件の新しいテスト（`the_user_chip_opens_the_user_name_above_the_first_settings_screen`・`the_app_leaves_back_on_homes_first_screen_to_the_system`・`the_tabs_hide_while_an_ask_is_on_screen`）は、今の振る舞いを固めるもので、直す前から通る（#36・#32）。見終えたら `git stash pop`。

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt`（新規）:

````kotlin
package com.touringproject.v2.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.touringproject.v2.ask.AskRecord
import com.touringproject.v2.map.LatLon
import com.touringproject.v2.map.MapPin
import com.touringproject.v2.map.RouteMap
import com.touringproject.v2.map.rideMap
import com.touringproject.v2.ride.Ride
import com.touringproject.v2.ride.RideController
import com.touringproject.v2.ride.RideStatus
import com.touringproject.v2.ride.RoutePoint
import com.touringproject.v2.settings.Settings
import com.touringproject.v2.store.RoomRecords
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import java.time.ZoneId

// Reads what SC-06 and SC-07 show from the device's records and hands it to the screens. Nothing is drawn until the
// ride, its asks and its route have all been read, so a screen never flashes "not found" while loading.

/** MapLibre, for the app. The screen tests pass a stand-in. */
val routeMap: MapSlot = { data, selected, onPin, modifier -> RouteMap(data, selected, onPin, modifier) }

/** A value that has been read, which may be null (a ride that is not kept); null itself means "not read yet". */
private data class Read<T>(val value: T)

@Composable
private fun readRide(records: RoomRecords, rideId: String): Read<Ride?>? =
  remember(rideId) { records.ride(rideId).map { Read(it) } }.collectAsStateWithLifecycle(null).value

@Composable
private fun readAsks(records: RoomRecords, rideId: String): List<AskRecord>? =
  remember(rideId) { records.asks(rideId) }.collectAsStateWithLifecycle(null).value

@Composable
private fun readRoute(records: RoomRecords, rideId: String): List<RoutePoint>? =
  produceState<List<RoutePoint>?>(null, rideId) { value = records.route(rideId) }.value

fun rideDetailUi(ride: Ride, asks: List<AskRecord>, route: List<RoutePoint>, now: Long, zone: ZoneId) = RideDetailUi(
  name = ride.name,
  summary = rideSummary(ride, asks.size, now, zone),
  recording = ride.status != RideStatus.ENDED,
  timeline = rideTimeline(ride, asks, zone),
  map = rideMap(route, ride.status == RideStatus.ENDED, askPins(asks)),
  cards = asks.mapNotNull { pinCard(asks, it.askId, zone) }.associateBy { it.askId },
)

@Composable
fun RideDetailRoute(
  records: RoomRecords,
  rides: RideController,
  settings: Settings,
  updateSettings: (Settings) -> Unit,
  rideId: String,
  onBack: () -> Unit,
  onAsk: (String) -> Unit,
  onFullMap: (Boolean) -> Unit,
  modifier: Modifier = Modifier,
) {
  val ride = readRide(records, rideId) ?: return
  val asks = readAsks(records, rideId) ?: return
  val route = readRoute(records, rideId) ?: return
  val scope = rememberCoroutineScope()
  val ui = remember(ride, asks, route) {
    ride.value?.let { rideDetailUi(it, asks, route, System.currentTimeMillis(), ZoneId.systemDefault()) }
  }
  RideDetailScreen(
    ui, routeMap,
    showPins = settings.showAskPins,
    onShowPins = { updateSettings(settings.copy(showAskPins = it)) },
    onBack = onBack,
    onAsk = onAsk,
    onRename = { name -> scope.launch { rides.rename(rideId, name) } },
    onFullMap = onFullMap,
    modifier = modifier,
  )
}

/** SC-07's map: the ask's numbered pin on its ride's faint route, opened close up on the pin. */
fun askMap(ask: AskRecord?, asks: List<AskRecord>, route: List<RoutePoint>, ended: Boolean) = ask?.let { a ->
  val lat = a.latitude ?: return@let null
  val lon = a.longitude ?: return@let null
  val at = LatLon(lat, lon)
  rideMap(route, ended, listOf(MapPin(a.askId, askNumbers(asks).getValue(a.askId), at)), faint = true, focus = at)
}

@Composable
fun AskDetailRoute(records: RoomRecords, rideId: String, askId: String, onBack: () -> Unit, onMove: (String) -> Unit, modifier: Modifier = Modifier) {
  val ride = readRide(records, rideId) ?: return
  val asks = readAsks(records, rideId) ?: return
  val route = readRoute(records, rideId) ?: return
  val zone = ZoneId.systemDefault()
  val detail = remember(asks, askId) { askDetail(asks, askId, zone) }
  val map = remember(asks, route, askId, ride) { askMap(asks.firstOrNull { it.askId == askId }, asks, route, ride.value?.status == RideStatus.ENDED) }
  AskDetailScreen(detail, map, routeMap, askId, onBack, onMove, modifier)
}
````

````bash
cd $AND && git apply <<'PATCH'
diff --git a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
index abc5252..fb7652d 100644
--- a/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/AppUi.kt
@@ -4,7 +4,6 @@ import android.Manifest
 import android.content.pm.PackageManager
 import android.widget.Toast
 import androidx.activity.compose.BackHandler
-import androidx.activity.compose.LocalActivity
 import androidx.compose.foundation.layout.Box
 import androidx.compose.foundation.layout.Column
 import androidx.compose.foundation.layout.consumeWindowInsets
@@ -30,7 +29,9 @@ import androidx.compose.ui.platform.LocalContext
 import androidx.lifecycle.compose.collectAsStateWithLifecycle
 import androidx.navigation3.runtime.NavKey
 import androidx.navigation3.runtime.entryProvider
+import androidx.navigation3.runtime.rememberDecoratedNavEntries
 import androidx.navigation3.runtime.rememberNavBackStack
+import androidx.navigation3.runtime.rememberSaveableStateHolderNavEntryDecorator
 import androidx.navigation3.ui.NavDisplay
 import com.touringproject.v2.AppGraph
 import com.touringproject.v2.BuildConfig
@@ -51,6 +52,8 @@ import kotlinx.serialization.Serializable
 @Serializable data object RecordingsKey : NavKey
 @Serializable data object RideRecordingKey : NavKey
 @Serializable data object RecordsKey : NavKey
+@Serializable data class RideKey(val rideId: String) : NavKey
+@Serializable data class AskKey(val rideId: String, val askId: String) : NavKey
 
 private enum class RideSheet { START, END }
 
@@ -78,6 +81,9 @@ fun AppUi(graph: AppGraph) {
   val storeFailed by graph.rides.storeFailed.collectAsStateWithLifecycle()
   val askStoreFailed by graph.askLog.failed.collectAsStateWithLifecycle()
   val questions by graph.activeAskCount.collectAsStateWithLifecycle()
+  val rideList by graph.records.list.collectAsStateWithLifecycle(null)
+  // SC-06 tells while its map fills the screen; the tabs go with it (slice 2 spec §7.1).
+  var mapFull by remember { mutableStateOf(false) }
   // Saveable: SC-17 and SC-04 stay open when the activity is recreated, e.g. on rotation (Android #20).
   var sheet by rememberSaveable { mutableStateOf<RideSheet?>(null) }
   val now = rememberNow(ride != null)
@@ -90,7 +96,6 @@ fun AppUi(graph: AppGraph) {
   val tabs = remember(homeStack, recordsStack, settingsStack) {
     TabStacks(mapOf(Tab.HOME to homeStack, Tab.RECORDS to recordsStack, Tab.SETTINGS to settingsStack), { selectedTab }, { selectedTab = it })
   }
-  val activity = LocalActivity.current
   val current = settings
   // Re-read on every phase change, so the label updates once an ask has renewed the conversation.
   val expiresAt = remember(state) { graph.conversation.expiresAt(System.currentTimeMillis()) }
@@ -99,17 +104,14 @@ fun AppUi(graph: AppGraph) {
       if (!ready || current == null) {
         Text("準備中…", Modifier.safeDrawingPadding())
       } else {
-        // NavDisplay handles Back within a stack; on the first screen of Records or Settings, Back goes to Home.
-        BackHandler(enabled = tabs.current.size == 1 && tabs.tab != Tab.HOME) { tabs.back() }
+        // NavDisplay handles Back within a stack; on the first screen of Records or Settings, Back goes to Home. On
+        // Home's first screen nothing takes it, and the system moves the app to the back (Android #32).
+        BackHandler(enabled = tabs.onAnotherTabsFirst) { tabs.back() }
         Scaffold(
           containerColor = MaterialTheme.colorScheme.background,
-          bottomBar = { if (tabsShown(state.phase)) TabBar(tabs.tab, tabs::press) },
+          bottomBar = { if (tabsShown(state.phase) && !mapFull) TabBar(tabs.tab, tabs::press) },
         ) { inner ->
-          NavDisplay(
-            backStack = tabs.current,
-            onBack = { if (!tabs.back()) activity?.finish() },
-            modifier = Modifier.padding(inner).consumeWindowInsets(inner),
-            entryProvider = entryProvider {
+          val screens = entryProvider<NavKey> {
               entry<HomeKey> {
                 val volume = rememberMediaVolume(volumeReadable(state.phase)) { graph.audioRoute.mediaVolume() }
                 val ui = HomeUi(
@@ -146,7 +148,33 @@ fun AppUi(graph: AppGraph) {
                   },
                 )
               }
-              entry<RecordsKey> { RecordsPlaceholder(Modifier.safeDrawingPadding()) }
+              entry<RecordsKey> {
+                RideListScreen(
+                  rideList?.let { rideSections(it, System.currentTimeMillis(), ZoneId.systemDefault()) },
+                  onRide = { tabs.current.add(RideKey(it)) },
+                  modifier = Modifier.safeDrawingPadding(),
+                )
+              }
+              entry<RideKey> { key ->
+                RideDetailRoute(
+                  graph.records, graph.rides, current,
+                  updateSettings = { next -> scope.launch { graph.settings.update(next) } },
+                  rideId = key.rideId,
+                  onBack = { tabs.back() },
+                  onAsk = { tabs.current.add(AskKey(key.rideId, it)) },
+                  onFullMap = { mapFull = it },
+                  modifier = Modifier.safeDrawingPadding(),
+                )
+              }
+              entry<AskKey> { key ->
+                AskDetailRoute(
+                  graph.records, key.rideId, key.askId,
+                  onBack = { tabs.back() },
+                  // ‹ › stay within the ride's asks: the shown ask is swapped, so Back still goes to SC-06.
+                  onMove = { other -> tabs.current[tabs.current.lastIndex] = AskKey(key.rideId, other) },
+                  modifier = Modifier.safeDrawingPadding(),
+                )
+              }
               entry<SettingsKey> {
                 SettingsScreen(
                   current, apiKey,
@@ -201,7 +229,17 @@ fun AppUi(graph: AppGraph) {
                 LaunchedEffect(Unit) { apps = graph.launcher.launchableApps() }
                 ReturnAppScreen(current, apps, { next -> scope.launch { graph.settings.update(next) } }, Modifier.safeDrawingPadding())
               }
-            },
+            }
+          // Each tab keeps the saved state of its screens (typed text, scroll) while another tab is shown (Android #34).
+          val entries = mapOf(
+            Tab.HOME to rememberDecoratedNavEntries(homeStack, listOf(rememberSaveableStateHolderNavEntryDecorator()), screens),
+            Tab.RECORDS to rememberDecoratedNavEntries(recordsStack, listOf(rememberSaveableStateHolderNavEntryDecorator()), screens),
+            Tab.SETTINGS to rememberDecoratedNavEntries(settingsStack, listOf(rememberSaveableStateHolderNavEntryDecorator()), screens),
+          )
+          NavDisplay(
+            entries = entries.getValue(tabs.tab),
+            modifier = Modifier.padding(inner).consumeWindowInsets(inner),
+            onBack = { tabs.back() },
           )
         }
         when (sheet) {
diff --git a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
index 7d6b6f7..2fb92f5 100644
--- a/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt
@@ -25,6 +25,7 @@ import androidx.compose.runtime.getValue
 import androidx.compose.runtime.mutableStateOf
 import androidx.compose.runtime.remember
 import androidx.compose.runtime.rememberCoroutineScope
+import androidx.compose.runtime.saveable.rememberSaveable
 import androidx.compose.runtime.setValue
 import androidx.compose.ui.Alignment
 import androidx.compose.ui.Modifier
@@ -181,6 +182,7 @@ fun ConnectionScreen(
   modifier: Modifier = Modifier,
 ) {
   val scope = rememberCoroutineScope()
+  // Not saveable: the key being typed is not put into the saved state, which the system may write out.
   var input by remember { mutableStateOf("") }
   var checking by remember { mutableStateOf(false) }
   var message by remember { mutableStateOf<String?>(null) }
@@ -228,7 +230,8 @@ fun ConnectionScreen(
 // SC-18
 @Composable
 fun UserScreen(userName: String, onChange: (String) -> Unit, modifier: Modifier = Modifier) {
-  var input by remember { mutableStateOf("") }
+  // Saveable, so a name being typed survives a trip to another tab (Android #34).
+  var input by rememberSaveable { mutableStateOf("") }
   var error by remember { mutableStateOf(false) }
   var confirming by remember { mutableStateOf<String?>(null) }
   Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
diff --git a/app/src/main/java/com/touringproject/v2/ui/TabBar.kt b/app/src/main/java/com/touringproject/v2/ui/TabBar.kt
index 8b7f5e7..ec0e9e9 100644
--- a/app/src/main/java/com/touringproject/v2/ui/TabBar.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/TabBar.kt
@@ -1,16 +1,11 @@
 package com.touringproject.v2.ui
 
-import androidx.compose.foundation.layout.Column
-import androidx.compose.foundation.layout.fillMaxSize
-import androidx.compose.foundation.layout.padding
-import androidx.compose.material3.MaterialTheme
 import androidx.compose.material3.NavigationBar
 import androidx.compose.material3.NavigationBarItem
 import androidx.compose.material3.Text
 import androidx.compose.runtime.Composable
 import androidx.compose.ui.Modifier
 import androidx.compose.ui.platform.testTag
-import androidx.compose.ui.unit.dp
 import androidx.compose.ui.unit.sp
 
 // The tabs of the app (02 §1, slice 2 spec §7.1). The icons are text, so no icon library is added.
@@ -31,11 +26,3 @@ fun TabBar(selected: Tab, onPress: (Tab) -> Unit) {
     }
   }
 }
-
-/** The Records tab until slice 2 plan 4 puts the list of rides and days (SC-05) here. */
-@Composable
-fun RecordsPlaceholder(modifier: Modifier = Modifier) {
-  Column(modifier.fillMaxSize().padding(16.dp)) {
-    Text("走行と日ごとの記録の一覧は、次の版でここに出ます。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 16.sp)
-  }
-}
diff --git a/app/src/main/java/com/touringproject/v2/ui/Tabs.kt b/app/src/main/java/com/touringproject/v2/ui/Tabs.kt
index dfe2b8d..29badc9 100644
--- a/app/src/main/java/com/touringproject/v2/ui/Tabs.kt
+++ b/app/src/main/java/com/touringproject/v2/ui/Tabs.kt
@@ -19,15 +19,18 @@ class TabStacks<K>(
 
   val current: MutableList<K> get() = stacks.getValue(selected())
 
-  /** False only on Home's first screen, where Back leaves the app. */
-  val canGoBack: Boolean get() = current.size > 1 || tab != Tab.HOME
+  /** On the first screen of Records or Settings, where Back goes to Home rather than within the tab. */
+  val onAnotherTabsFirst: Boolean get() = current.size == 1 && tab != Tab.HOME
 
   /** Another tab shows as it was left; the tab already shown goes back to its first screen. */
   fun press(pressed: Tab) {
     if (pressed == tab) toFirst(current) else select(pressed)
   }
 
-  /** Back within the tab; from another tab's first screen, to Home. Returns false when the app should close. */
+  /**
+   * Back within the tab; from another tab's first screen, to Home. Returns false on Home's first screen, where Back is
+   * left to the system (Android #32).
+   */
   fun back(): Boolean {
     val stack = current
     if (stack.size > 1) {
PATCH
````

- [ ] **Step 4: 通るのを見る**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AppUiTest' --tests '*TabsTest' --tests '*RecordsScreensTest' --tests '*HomeScreenTest' --tests '*SettingsScreensTest' --tests '*RideScreensTest' --rerun`
Expected: `AppUiTest` 7件・`TabsTest` 5件・`RecordsScreensTest` 10件・`HomeScreenTest` 6件・`SettingsScreensTest` 9件・`RideScreensTest` 10件が通る。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/main/java/com/touringproject/v2/ui/Tabs.kt app/src/main/java/com/touringproject/v2/ui/TabBar.kt \
  app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt \
  app/src/test/java/com/touringproject/v2/ui/AppUiTest.kt app/src/test/java/com/touringproject/v2/ui/TabsTest.kt
git commit -m "feat: put the records screens in the Records tab and keep each tab's state" -m "Fixes #32" -m "Fixes #34" -m "Fixes #36"
```

---
### Task 10: 版と文書

**Files:**
- Modify: `app/build.gradle.kts`（版 0.4.0）・`README.md`（Android）・`docs-parent/`（親の文書の写し）

- [ ] **Step 1: 版を上げ、README を直す**

````bash
cd $AND && git apply <<'PATCH'
diff --git a/README.md b/README.md
index b377820..a7ffe21 100644
--- a/README.md
+++ b/README.md
@@ -13,20 +13,22 @@ TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
 | `.../audio/` | インカムの経路・録音・再生・端末の音声・合図 |
 | `.../location/` | 質問の位置の監視と方位の材料の選び方・走行のルートの位置の頼み方と点のふるい分け（`Route.kt`） |
 | `.../ride/` | 走行の型と計算（`Ride.kt`、純粋）・司令塔（`RideController.kt`）・外との窓口（`RidePorts.kt`） |
-| `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・送信の置き場（`RoomSyncStore.kt`）。スキーマは `app/schemas/` に版ごとに残す |
+| `.../store/` | 端末の DB（Room）・質問の置き場（`RoomAskLog.kt`）・送信の置き場（`RoomSyncStore.kt`）・記録の画面の読み出し（`RoomRecords.kt`）。スキーマは `app/schemas/` に版ごとに残す |
+| `.../records/` | 記録一覧の並べ方と保存の状態（`Records.kt`、純粋） |
+| `.../map/` | 地図（MapLibre と国土地理院の淡色地図）。描くデータの組み立ては `MapData.kt`（純粋）、地図の部品は `RouteMap.kt`、スタイルは `app/src/main/assets/map/gsi-pale.json` |
 | `.../sync/` | 走行とルートの送信。何を送るかの判断（`SyncPlan.kt`、純粋）と送信の係（`RideSync.kt`） |
 | `.../handsfree/` | 押下の重複・古い合図の除外・押下の行き先（試し録り中は試し録りへ） |
 | `.../recordings/` | 録音の置き場（直近10件と付随情報）・試し録りの司令塔・録音の確認（SC-12）の状態 |
 | `.../service/`・`.../nav/` | 前面サービス（走行の記録と一巡で1つ。種類の取りまとめは `ServiceCoordinator.kt`）・締め切りのアラームと自動終了の通知（`RideAlarms.kt`）・ナビを開く |
 | `.../settings/` | 設定（DataStore）と接続キー（Keystore で暗号化） |
-| `.../ui/` | 画面（Compose）。タブとバックスタックの組は `Tabs.kt`（Compose に依存しない）、タブの帯は `TabBar.kt` |
+| `.../ui/` | 画面（Compose）。タブとバックスタックの組は `Tabs.kt`（Compose に依存しない）、タブの帯は `TabBar.kt`。記録の画面は `RecordsScreens.kt`（地図は差し替えられる枠で受ける）、その表示の組み立ては `RecordLabels.kt`（純粋）、読み出しとのつなぎは `RecordsRoutes.kt` |
 
 ## 大事な決まり
 
 - 走行の記録中と一巡のあいだは、前面サービスを動かす（無いと、画面を消したあと位置・通信・再生が止まる）。種類は、記録中は `location`、一巡のあいだは `microphone|mediaPlayback` を足す。Android 14 以降、この2つはアプリが前面にあるときにしか始められず、足せない（理由は親の `adr/0006`）。
-- 走行の状態を変えるのは `RideController` だけ。サービス・締め切りのアラーム・電源を切る知らせ・画面は、どれもこれを呼ぶ。起動したときは `load()` が先に、残っていた走行を片付ける（端末が止まっていれば終了、締め切りを過ぎていれば自動終了、それ以外は記録の再開）。 最長時間を変えたときの締め切りの計算し直しも `maxRecordingChanged()` が行う（設定の画面が呼ぶ）。
+- 走行の状態を変えるのは `RideController` だけ。サービス・締め切りのアラーム・電源を切る知らせ・画面は、どれもこれを呼ぶ。起動したときは `load()` が先に、残っていた走行を片付ける（端末が止まっていれば終了、締め切りを過ぎていれば自動終了、それ以外は記録の再開）。最長時間を変えたときの締め切りの計算し直しも `maxRecordingChanged()` が行う（`AppGraph` が設定の変化を受けて呼ぶ）。名前の変更は `rename()`。
 - Room のスキーマを変えるときは、版を上げて Migration を書き、`app/schemas/` に書き出された JSON もコミットする。破壊的な作り直しは使わない。スキーマの JSON は debug のビルドの資産にも入る（Robolectric の `MigrationTestHelper` が読むため。release には入らない）。Entity や Migration を変えた直後のテストは `--rerun` で確かめる。
-- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと。契機では未送信を調べるだけで、送るものが無ければ通信しない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（`rides.rejectedUpdatedAt`・`rides.routeRejected` に残す）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。
+- 走行とルートは `RideSync` が送る。契機は、走行の変更を書けたとき・このプロセスで点を300書くごと・アプリが前面に来たとき（`MainActivity.onStart`）・起動して設定を読んだあと。契機では未送信を調べるだけで、送るものが無ければ通信しない。ルートは記録した順に300点ずつのかたまりで送り、番号 k には 300k 番目からの点が入る。記録中は満ちたかたまりだけ、一時停止と終了では端数も送り、点が増えたら同じ番号で送り直す。400 は送り直さない（走行は `rides.rejectedUpdatedAt`、ルートはそのかたまりの点の `route_points.refused` に残す。同じ番号のかたまりが受け付けられたら下りる。`rides.routeRejected` は版2の名残りで、もう書かない）。走行の `updatedAt` は変わるたびに必ず進める（Backend は新しい版だけを残す）。
 - インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
 - インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
 - 回答は音声の焦点（audio focus）を取らずに鳴らす（ナビの案内と重ねる）。
@@ -57,6 +59,8 @@ $SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
 
 インカムの合図は `adb shell am start -a android.intent.action.VOICE_COMMAND -n com.touringproject.v2/.MainActivity` で送れる。
 
+MapLibre は Robolectric では動かない（ネイティブのライブラリが要る）。地図の見た目とピンのタップは、エミュレーターの `RouteMapTest` で確かめる。記録の画面は地図を枠で受けるので、JVM のテストでは作り物の地図を渡す。`queryRenderedFeatures` は、地図が一度描き終える前に呼ぶとネイティブのコードが落ちる（`RouteMap` の `onMap` は描き終えてから渡す）。
+
 `RideRecordingTest` は、Fused の mock mode で作り物の位置を流す（テストが自分で、アプリを位置の作り物を出すアプリにする）。記録中の質問のテストは、`local.properties` に `trv2.apiBaseUrl` が無いと飛ばす。接続キーを入れて録音の途中で取り消し、最後にキーを消す。
 
 ## 実機で動かす
diff --git a/app/build.gradle.kts b/app/build.gradle.kts
index 38d0a8a..0022394 100644
--- a/app/build.gradle.kts
+++ b/app/build.gradle.kts
@@ -24,8 +24,8 @@ android {
     minSdk = 29
     targetSdk = 36
     // Raised by hand for every new build put on the phones (Android README), so Settings shows which one is installed.
-    versionCode = 4
-    versionName = "0.3.1"
+    versionCode = 5
+    versionName = "0.4.0"
     testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
     // The phone and the emulator are both arm64; MapLibre's native code for other ABIs only makes the app bigger (slice 2 spec §7.7).
     ndk { abiFilters += "arm64-v8a" }
PATCH
````

- [ ] **Step 2: 親の文書を写す**

この plan を書いた親のコミットで、遷移図（`docs/03_screen_transition.md`）とモック（`docs/mock/index.html`）を adr/0007 に合わせて直したので、Android の `docs-parent/` に写す。

```bash
cd $ROOT && scripts/sync-docs.sh Android
cd $AND && git status --short docs-parent
```

Expected: `docs-parent/03_screen_transition.md` と `docs-parent/mock/index.html` が変わっている。

- [ ] **Step 3: コミット**

```bash
cd $AND && git add app/build.gradle.kts README.md docs-parent/03_screen_transition.md docs-parent/mock/index.html
git commit -m "chore: raise the version to 0.4.0 and describe the records screens" -m "Fixes #37"
```

---

### Task 11: 全体の確かめ

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

Expected: `366 0`。`BUILD SUCCESSFUL`。`release permissions OK (15)`。

- [ ] **Step 2: エミュレーターのテスト**

```bash
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
cd $AND && export ANDROID_SERIAL=emulator-5554 && ./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

Expected: 5件が通る（`RideRecordingTest` 2件・`VoiceCommandTest` 2件・`RouteMapTest` 1件）。

---

### Task 12: 利用者の実機の確認

走行用のビルド（版 0.4.0）を実機に入れ、利用者に次を確かめてもらう。

```bash
cd $AND && adb install --user 0 -r app/build/outputs/apk/release/app-release.apk
adb shell dumpsys package com.touringproject.v2 | grep -E "versionName|lastUpdateTime"
```

1. 設定 → バージョンが 0.4.0。
2. 記録のタブに、これまでの走行が月の見出しの下に新しい順で並ぶ。行に名前・日付と時刻・距離・走行時間・質問の数（・一時停止の回数）・保存の状態が出る。送った走行は「保存済み」。
3. 走行を開くと、淡色地図にルート（オレンジ）・出発（緑）・到着（黒）・一時停止の破線・番号のピンが出て、全体が収まる縮尺で開く。
4. 地図の右下の「地理院タイル」を押すと、国土地理院のタイル一覧のページが開く。
5. ピンを押すと青くなり、下にカード（番号・時刻・場所・質問・回答の冒頭）が出る。カードを押すと会話の詳細が開く。地図の何も無いところを押すとカードが消える。
6. 「💬 質問」でピンを隠せる。いったん戻って開き直しても隠れたまま。もう一度押すと出る。
7. ⛶ で地図が全画面になり、タブの帯が隠れる。✕ でも端末の Back でも元に戻り、タブの帯も戻る。全画面でもピンのカードは使える。
8. 時系列に、質問（番号・時刻・場所・文）・一時停止（時刻と分）・会話の区切りが出る。行を押すと会話の詳細。
9. 会話の詳細に、日時・場所・進行方向（右手・左手）・入力・質問・回答と、その地点の小さな地図（ルートが淡く）が出る。‹ › で走行の中の前後へ移り、Back で走行の詳細に戻る。
10. ⋮ → 名前を変える で名前を変えると、詳細と一覧に出る。そのあと AI がユーザー名を聞き、`AWS_PROFILE=touring` で DynamoDB の走行の名前が変わったことを確かめる。
11. 端末をダークモードにすると、地図が暗くなり、ルートとピンが読める。
12. 設定 → ユーザー名に打ちかけたまま、ホームのタブへ移って戻ると、打ちかけが残る。記録の一覧をスクロールして、ほかのタブへ移って戻ると、位置が残る。
13. ホームの最初の画面で Back を押すと、今までどおりアプリが背面に回る。
14. 走行を記録しながら記録のタブを開くと、一番上に「● 記録中」で出る。開くと「記録中の走行です。ルートは開いたときまでのものです。」と出る。

✗ が出たら `superpowers:systematic-debugging`。
