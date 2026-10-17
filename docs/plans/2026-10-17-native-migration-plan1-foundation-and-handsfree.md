# ネイティブ移行 計画1: 土台と、ハンズフリーの一巡 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kotlin・Compose の新しいアプリ（`TouringProjectV2_Android`）で、インカムのボタンで起動 → 録音 → 送信 → ナビへ戻る → 背面で回答を待って読み上げる、という一巡を、スライス1と同じ振る舞いで実機で確かめられるところまで作る。

**Architecture:** 1つの Gradle モジュール `app` をパッケージで分ける。一巡の判断は、Android に依存しない状態機械（`ask/Flow.kt`）と司令塔（`ask/AskController.kt`）に置き、外とのやり取りはすべて `ask/AskPorts.kt` の interface を通す。テストでは作り物に差し替え、時間はコルーチンの仮想時間で進める。端末にしかできないこと（インカムの経路・録音・再生・読み上げ・合図・前面サービス・ナビを開く・位置）は、それぞれ小さなクラスにして interface を実装する。部品は `AppGraph` で手で組み立て、`Application` が持つ。

**Tech Stack:** Kotlin 2.3.20・AGP 9.0.1・Gradle 9.4.1・Jetpack Compose（BOM 2026.03.01）・Navigation 3・DataStore・Media3 ExoPlayer・OkHttp・kotlinx.serialization・Play services location・JUnit・kotlinx-coroutines-test・MockWebServer・Robolectric 4.16（SDK 35）・Compose の UI テスト・エミュレーター（Android 16・medium_phone）。

**Spec:** [docs/specs/2026-10-17-native-migration-design.md](../specs/2026-10-17-native-migration-design.md)（§2〜§8）。振る舞いの正は [スライス1の設計](../specs/2026-10-16-slice1-design.md) §5・§8 と、React Native 版の `App/src/`（移植の元）。決定の経緯は [adr/0005](../../adr/0005-native-android-app.md)。

この計画のコードは、使い捨てのフォルダで JVM のテスト114件・エミュレーターのテスト2件・`assembleDebug` が通ることを確かめてから書いた。

## Global Constraints

- 作業するリポジトリは新しい `Android/`（`TouringProjectV2_Android`、公開）。Task 1 の終わりと Task 13 だけ親。親は `main` から作業ブランチ `migration-plan1` を切る。`Android/` は Task 1 で `main` に雛形の最初のコミットを置き、以後はブランチ `migration-plan1` で作業する。push はしない（利用者が行う）。
- パッケージ名 `com.touringproject.v2`、アプリ名「Touring V2」。minSdk 29・targetSdk 36・compileSdk 36。JDK 17。
- API の URL は `Android/local.properties` の `trv2.apiBaseUrl`（追跡しない）。接続キーは Android Keystore の鍵で暗号化して DataStore に置く。キーと URL をコードや文書に書かない。
- 録音は PCM（16kHz・モノラル・16bit）。改行なしの base64 で送る。上限は20秒（スライス1と同じく固定）。
- 一巡のあいだは前面サービス（microphone・mediaPlayback）を動かす（adr/0004）。待ちはコルーチンの `delay`（前面サービスでプロセスが生きていれば背面でも止まらない）。
- ポーリングは最初の10秒は1秒ごと、以後は2秒ごと、120秒で打ち切る（07 UC-5）。
- 失敗の理由と読み上げる文はスライス1 spec §8.1 のとおり。戻るのはインカムのボタンで始めた応答だけ。戻るタイミングは「送ったらすぐ（既定）／回答が届いたら／読み上げが終わったら」。
- 対話の画面（SC-03）の色: 録音中 `#d42a2a`・回答待ち `#1f4fd1`・読み上げ中 `#13804a`・失敗 `#5b6170`。
- 移行の計画2で足すもの（この計画では作らない）: 回答の音量（SC-21）・録音の確認（SC-12）と録音を残すこと・メディアの音量の警告の帯・走行用のビルド・親の文書の 06・07 と submodule `App/` の整理。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`、`SDK=$HOME/Library/Android/sdk`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest`（1件だけなら `--tests '*クラス名'`）。

## Review Focus

- 同じ押下が2回届く（Activity が作り直される、戻るで閉じたあとに合図が来る）→ 一巡は1回だけ始まる。Task 10 の `MainActivityTest`、Task 11 の `VoiceCommandTest`。
- 回答の読み上げ中にインカムのボタンが押される → 何も言わず、録音も始めない。Task 6 の `a_press_while_the_answer_is_read_out_says_nothing_over_it`。
- 保存した設定が壊れている・接続キーが復号できない（端末の鍵が消えた）→ 既定値で動き、キーは未設定として扱う。Task 2 の `broken_values_fall_back_to_defaults`・`a_key_that_cannot_be_decrypted_reads_as_no_key`。
- サーバーが応答を返さないまま止まる → 時間で打ち切り、通信の失敗として知らせる。Task 3 の `a_stalled_request_times_out_as_a_network_error`。
- 回答の音声が途中で止まったまま進まない → 15秒で諦めて端末の音声で回答を読む。Task 7 の `StallWatchTest`（諦めたあとの読み上げは Task 6 の `test_player_error_falls_back_to_device_voice`）。

---

## ファイル構成（`Android/app/src/` から）

| パス | 役割 |
|---|---|
| `main/java/.../settings/` | 設定の形と読み書き（`Settings.kt`）・DataStore（`SettingsRepository.kt`）・接続キーの暗号化（`ApiKeyStore.kt`） |
| `main/java/.../api/ApiClient.kt` | Backend の API（失敗の分類・試し直し・時間切れ） |
| `main/java/.../ask/` | 状態機械（`Flow.kt`）・失敗の読み上げ文（`Failures.kt`）・ポーリング（`Polling.kt`）・会話（`Conversation.kt`）・外との窓口（`AskPorts.kt`）・司令塔（`AskController.kt`） |
| `main/java/.../location/` | 方位の材料の選び方（`Heading.kt`）・録音中の位置の集め方（`PositionTracker.kt`）・Fused の位置（`FusedPositionSource.kt`） |
| `main/java/.../handsfree/Press.kt` | 押下の重複・古い合図の除外・準備ができるまで押下を預かる |
| `main/java/.../audio/` | 型（`AudioTypes.kt`）・インカムの経路（`AudioRoute.kt`。React Native 版の `audio-route` の移植）・経路の切り替え（`AudioRouteControl.kt`）・録音（`PcmRecorder.kt`）・再生（`ExoAnswerPlayer.kt`）・端末の音声（`TtsSpeech.kt`）・合図（`ToneCues.kt`） |
| `main/java/.../nav/AppLauncher.kt` | ナビを開く・起動できるアプリの一覧 |
| `main/java/.../service/RideForegroundService.kt` | 前面サービスと、それを始める・止める窓口 |
| `main/java/.../ui/` | 文言と色（`Labels.kt`）・ホーム（`HomeScreen.kt`）・対話（`AskOverlay.kt`）・設定の画面（`SettingsScreens.kt`）・画面のつながり（`AppUi.kt`） |
| `main/java/.../AppGraph.kt`・`TouringApp.kt`・`MainActivity.kt` | 部品の組み立て・Application・インカムの合図の受け口と権限 |
| `test/` | JVM のテスト（JUnit・Robolectric・Compose） |
| `androidTest/` | エミュレーターのテスト |

`...` は `com/touringproject/v2`。

---

### Task 1: リポジトリと雛形

**Files:**
- Create: `Android/` 一式（`android create` の雛形）、`app/src/test/resources/robolectric.properties`、`app/src/test/java/.../ToolingTest.kt`、`README.md`
- Modify: `gradle/libs.versions.toml`、`app/build.gradle.kts`、`gradle/wrapper/gradle-wrapper.properties`、`app/src/main/java/.../MainActivity.kt`（仮）
- Delete: 雛形のサンプル（`ui/`・`data/`・`Navigation.kt`・`NavigationKeys.kt` とそのテスト）
- 親: `.gitmodules`（submodule `Android/`）

**Interfaces:**
- Produces: `./gradlew testDebugUnitTest` と `./gradlew assembleDebug` が通るプロジェクト。`BuildConfig.API_BASE_URL`（`local.properties` の `trv2.apiBaseUrl`）。Robolectric は SDK 35 で動く。

- [ ] **Step 1: リポジトリを作り、雛形を出す**

```bash
cd $ROOT && git switch -c migration-plan1
gh repo create h-akira/TouringProjectV2_Android --public --description "TouringProjectV2 Android app (Kotlin / Jetpack Compose)"
$SDK/cmdline-tools/latest/bin/android --no-metrics create empty-activity \
  --name="Touring V2" --application-id=com.touringproject.v2 --namespace=com.touringproject.v2 --min-sdk=29 --output=$AND
cd $AND && git init -b main
\rm -rf app/src/main/java/com/touringproject/v2/ui app/src/main/java/com/touringproject/v2/data \
  app/src/main/java/com/touringproject/v2/Navigation.kt app/src/main/java/com/touringproject/v2/NavigationKeys.kt \
  app/src/test/java/com/touringproject/v2/ui app/src/androidTest/java/com/touringproject/v2/ui
```

Gradle はキャッシュにある 9.4.1 を使う（`gradle-wrapper.properties` の `distributionUrl` を `gradle-9.4.1-bin.zip` にし、`distributionSha256Sum` の行を消す）:

```bash
sed -i '' 's#gradle-[0-9.]*-bin.zip#gradle-9.4.1-bin.zip#; /distributionSha256Sum/d' gradle/wrapper/gradle-wrapper.properties
```

- [ ] **Step 2: 依存とビルドの設定を書く**

`gradle/libs.versions.toml`（全体を置き換える）:

```toml
[versions]
androidGradlePlugin = "9.0.1"
androidxCore = "1.18.0"
androidxLifecycle = "2.10.0"
androidxActivity = "1.13.0"
androidxComposeBom = "2026.03.01"
androidxDatastore = "1.1.7"
androidxTest = "1.7.0"
androidxTestExt = "1.3.0"
androidxTestRunner = "1.7.0"
coroutines = "1.10.2"
junit = "4.13.2"
kotlin = "2.3.20"
kotlinxSerialization = "1.9.0"
media3 = "1.9.1"
nav3Core = "1.0.1"
okhttp = "4.12.0"
playServicesLocation = "21.3.0"
robolectric = "4.16"

[libraries]
androidx-core-ktx = { module = "androidx.core:core-ktx", version.ref = "androidxCore" }
androidx-activity-compose = { module = "androidx.activity:activity-compose", version.ref = "androidxActivity" }
androidx-compose-bom = { group = "androidx.compose", name = "compose-bom", version.ref = "androidxComposeBom" }
androidx-compose-material3 = { group = "androidx.compose.material3", name = "material3" }
androidx-compose-ui = { group = "androidx.compose.ui", name = "ui" }
androidx-compose-ui-tooling-preview = { group = "androidx.compose.ui", name = "ui-tooling-preview" }
androidx-compose-ui-tooling = { group = "androidx.compose.ui", name = "ui-tooling" }
androidx-compose-ui-test-junit4 = { group = "androidx.compose.ui", name = "ui-test-junit4" }
androidx-compose-ui-test-manifest = { group = "androidx.compose.ui", name = "ui-test-manifest" }
androidx-datastore-preferences = { module = "androidx.datastore:datastore-preferences", version.ref = "androidxDatastore" }
androidx-lifecycle-runtime-compose = { module = "androidx.lifecycle:lifecycle-runtime-compose", version.ref = "androidxLifecycle" }
androidx-lifecycle-runtime-ktx = { module = "androidx.lifecycle:lifecycle-runtime-ktx", version.ref = "androidxLifecycle" }
androidx-lifecycle-service = { module = "androidx.lifecycle:lifecycle-service", version.ref = "androidxLifecycle" }
androidx-media3-exoplayer = { module = "androidx.media3:media3-exoplayer", version.ref = "media3" }
androidx-navigation3-runtime = { module = "androidx.navigation3:navigation3-runtime", version.ref = "nav3Core" }
androidx-navigation3-ui = { module = "androidx.navigation3:navigation3-ui", version.ref = "nav3Core" }
androidx-test-core = { module = "androidx.test:core", version.ref = "androidxTest" }
androidx-test-ext-junit = { module = "androidx.test.ext:junit", version.ref = "androidxTestExt" }
androidx-test-runner = { module = "androidx.test:runner", version.ref = "androidxTestRunner" }
junit = { module = "junit:junit", version.ref = "junit" }
kotlinx-coroutines-android = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-android", version.ref = "coroutines" }
kotlinx-coroutines-test = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-test", version.ref = "coroutines" }
kotlinx-serialization-json = { module = "org.jetbrains.kotlinx:kotlinx-serialization-json", version.ref = "kotlinxSerialization" }
okhttp = { module = "com.squareup.okhttp3:okhttp", version.ref = "okhttp" }
okhttp-mockwebserver = { module = "com.squareup.okhttp3:mockwebserver", version.ref = "okhttp" }
play-services-location = { module = "com.google.android.gms:play-services-location", version.ref = "playServicesLocation" }
robolectric = { module = "org.robolectric:robolectric", version.ref = "robolectric" }

[plugins]
android-application = { id = "com.android.application", version.ref = "androidGradlePlugin" }
compose-compiler = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
kotlin-serialization = { id = "org.jetbrains.kotlin.plugin.serialization", version.ref = "kotlin" }
```

`app/build.gradle.kts`（全体を置き換える）:

```kotlin
import java.time.Duration
import java.util.Properties

plugins {
  alias(libs.plugins.android.application)
  alias(libs.plugins.compose.compiler)
  alias(libs.plugins.kotlin.serialization)
}

// The API URL lives in local.properties (not tracked): trv2.apiBaseUrl=https://<id>.execute-api.ap-northeast-1.amazonaws.com/Prod
val localProps = Properties().apply {
  val file = rootProject.file("local.properties")
  if (file.exists()) file.inputStream().use { load(it) }
}
val apiBaseUrl: String = localProps.getProperty("trv2.apiBaseUrl") ?: ""

android {
  namespace = "com.touringproject.v2"
  compileSdk = 36
  defaultConfig {
    applicationId = "com.touringproject.v2"
    minSdk = 29
    targetSdk = 36
    versionCode = 1
    versionName = "0.1.0"
    testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
  }

  buildTypes {
    release {
      isMinifyEnabled = false
      proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
  }
  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
  }
  buildFeatures {
    compose = true
    buildConfig = true
  }
  testOptions {
    unitTests.isIncludeAndroidResources = true
  }
  packaging {
    resources {
      excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
  }
}

kotlin {
  jvmToolchain(17)
}

dependencies {
  val composeBom = platform(libs.androidx.compose.bom)
  implementation(composeBom)
  testImplementation(composeBom)
  androidTestImplementation(composeBom)

  implementation(libs.androidx.core.ktx)
  implementation(libs.androidx.lifecycle.runtime.ktx)
  implementation(libs.androidx.lifecycle.runtime.compose)
  implementation(libs.androidx.lifecycle.service)
  implementation(libs.androidx.activity.compose)
  implementation(libs.androidx.compose.ui)
  implementation(libs.androidx.compose.ui.tooling.preview)
  implementation(libs.androidx.compose.material3)
  implementation(libs.androidx.navigation3.ui)
  implementation(libs.androidx.navigation3.runtime)
  implementation(libs.androidx.datastore.preferences)
  implementation(libs.androidx.media3.exoplayer)
  implementation(libs.kotlinx.coroutines.android)
  implementation(libs.kotlinx.serialization.json)
  implementation(libs.okhttp)
  implementation(libs.play.services.location)
  debugImplementation(libs.androidx.compose.ui.tooling)
  debugImplementation(libs.androidx.compose.ui.test.manifest)

  // JVM tests: plain JUnit, Robolectric for Android classes, Compose UI tests under Robolectric
  testImplementation(libs.junit)
  testImplementation(libs.kotlinx.coroutines.test)
  testImplementation(libs.okhttp.mockwebserver)
  testImplementation(libs.robolectric)
  testImplementation(libs.androidx.test.core)
  testImplementation(libs.androidx.test.ext.junit)
  testImplementation(libs.androidx.compose.ui.test.junit4)

  // Emulator tests
  androidTestImplementation(libs.androidx.test.core)
  androidTestImplementation(libs.androidx.test.ext.junit)
  androidTestImplementation(libs.androidx.test.runner)
}

// A test that deadlocks on the main thread must fail the build instead of hanging it.
tasks.withType<Test>().configureEach {
  timeout.set(Duration.ofMinutes(5))
}
```

`app/src/test/resources/robolectric.properties`:

```properties
# Robolectric needs Java 21 for SDK 36; the JVM tests run on SDK 35 with JDK 17.
sdk=35
```

`app/src/main/java/com/touringproject/v2/MainActivity.kt`（仮。Task 10 で置き換える）:

```kotlin
package com.touringproject.v2

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.Text
import com.touringproject.v2.theme.TouringV2Theme

// Placeholder until the app is wired up (Task 10 replaces it).
class MainActivity : ComponentActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    enableEdgeToEdge()
    setContent { TouringV2Theme { Text("Touring V2") } }
  }
}
```

- [ ] **Step 3: 道具が動くことを確かめるテストを書く**

`app/src/test/java/com/touringproject/v2/ToolingTest.kt`:

```kotlin
package com.touringproject.v2

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

// Proves the JVM test setup (Robolectric on SDK 35 with JDK 17) works before anything else is built on it.
@RunWith(AndroidJUnit4::class)
class ToolingTest {
  @Test
  fun robolectric_runs_with_the_app_package() {
    assertEquals("com.touringproject.v2", ApplicationProvider.getApplicationContext<Context>().packageName)
  }
}
```

- [ ] **Step 4: テストとビルドを通す**

Run: `cd $AND && ./gradlew testDebugUnitTest assembleDebug`
Expected: `BUILD SUCCESSFUL`、`ToolingTest` が 1 件通る。初回は Robolectric の SDK 35（約190MB）を取りに行くので数分かかる。
SDK 36 のまま動かすと「Android SDK 36 requires Java 21」で失敗する。`robolectric.properties` が効いているか確かめる。

- [ ] **Step 5: README を書く**

`README.md`（全体を置き換える）:

````markdown
# TouringProjectV2_Android

TouringProjectV2 の Android アプリ（Kotlin・Jetpack Compose）。
インカムのボタンで質問を始め、回答を背面で待って読み上げ、ナビのアプリへ戻る。
プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し。編集しない）。

## 構成

| 場所 | 中身 |
|---|---|
| `app/src/main/java/com/touringproject/v2/ask/` | 一巡の状態機械（`Flow.kt`）・司令塔（`AskController.kt`）・外との窓口（`AskPorts.kt`）・ポーリング・会話・失敗の読み上げ文 |
| `.../api/` | Backend の API（`Backend/openapi.yaml`） |
| `.../audio/` | インカムの経路・録音・再生・端末の音声・合図 |
| `.../location/` | 位置の監視と方位の材料の選び方 |
| `.../handsfree/` | 押下の重複・古い合図の除外 |
| `.../service/`・`.../nav/` | 前面サービス・ナビを開く |
| `.../settings/` | 設定（DataStore）と接続キー（Keystore で暗号化） |
| `.../ui/` | 画面（Compose） |

## 大事な決まり

- 一巡のあいだは前面サービスを動かす（無いと、画面を消したあと通信と再生が止まる）。
- インカムは音の出だしを落とす。合図は長さを指定できる音（`TONE_SUP_DIAL`・`TONE_DTMF_*`）で長めに鳴らし、開始の合図は録音が始まってから鳴らす。`TONE_PROP_*` は、長さを指定しても約0.16秒で止まる。
- インカムのボタンの経路では `setCommunicationDevice()` を呼ばない（`AudioRoute.kt` の冒頭のコメント）。
- 回答は音声の焦点（audio focus）を取らずに鳴らす（ナビの案内と重ねる）。
- `MainActivity` は `singleTask`。`ActivityScenario` はこれを追えないので、エミュレーターのテストは Activity を直接起動する。

## テスト

```sh
./gradlew testDebugUnitTest            # JVM（JUnit・Robolectric・Compose）。端末は要らない
./gradlew connectedDebugAndroidTest    # エミュレーター（下の「エミュレーター」）
```

Robolectric は SDK 35 で動かす（`app/src/test/resources/robolectric.properties`。SDK 36 には Java 21 が要る）。

## 実機で動かす

`local.properties`（追跡しない）に API の URL を書く。

```sh
URL=$(AWS_PROFILE=touring aws cloudformation describe-stacks --region ap-northeast-1 --stack-name stack-trv2-dev-backend \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
printf 'trv2.apiBaseUrl=%s\n' "$URL" >> local.properties
./gradlew installDebug
```

接続キーは、アプリの「設定 → 接続の設定」で入れる（Backend の README の手順で読む）。キーをどこにも表示せずに入れるときは、入力欄を開いた状態で `adb shell input text "$KEY"` で打ち込む。

ログは `adb logcat -s trv2.ask trv2.route trv2.ride`。
````

- [ ] **Step 6: コミットし、親に submodule として足す**

```bash
cd $AND && git add .gitignore app/.gitignore build.gradle.kts settings.gradle.kts gradle.properties gradlew gradlew.bat \
  gradle/libs.versions.toml gradle/wrapper/gradle-wrapper.jar gradle/wrapper/gradle-wrapper.properties \
  app/build.gradle.kts app/src/main app/src/test README.md
git status --short   # local.properties と build/ が入っていないこと
git commit -m "chore: scaffold the native Android app"
git remote add origin git@github.com:h-akira/TouringProjectV2_Android.git
git switch -c migration-plan1
cd $ROOT && git submodule add git@github.com:h-akira/TouringProjectV2_Android.git Android
git commit -m "chore: add the native Android app as a submodule"
```

`git submodule add` は、`Android/` に既にあるリポジトリをそのまま登録する（remote が空でもよい）。

---

### Task 2: 設定と接続キー

**Files:**
- Create: `app/src/main/java/.../settings/Settings.kt`、`SettingsRepository.kt`、`ApiKeyStore.kt`
- Test: `app/src/test/java/.../settings/SettingsTest.kt`

**Interfaces:**
- Produces:
  - `data class Settings(userName: String, returnEnabled: Boolean = true, returnApp: LaunchableApp? = null, returnTiming: ReturnTiming = SENT, recentApps: List<LaunchableApp> = emptyList(), answerVolumeDb: Int = 6)`、`enum class ReturnTiming { SENT, ANSWERED, SPOKEN }`、`data class LaunchableApp(packageName: String, label: String)`
  - `decodeSettings(raw: String?, random): Pair<Settings, Boolean /* needsSave */>`、`encodeSettings(Settings): String`、`withRecentApp(recent, app, max = 5)`、`maskKey(key)`、`USER_NAME_RE`
  - `interface KeyValueStore { suspend fun get(key): String?; suspend fun set(key, value: String?) }`、`DataStoreKeyValueStore(context)`
  - `SettingsRepository(store, random)`: `settings: StateFlow<Settings?>`、`suspend load()`、`current(): Settings`、`suspend update(next)`
  - `interface SecretCipher`、`KeystoreCipher`、`ApiKeyStore(store, cipher)`: `apiKey: StateFlow<String?>`、`suspend load()`、`current()`、`suspend save(key: String?)`

保存の形は React Native 版と同じ JSON（キー `trv2.settings`。`returnTiming` は小文字の `"sent"` など）。React Native 版の設定は引き継がない（端末が別のアプリになるため）。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/settings/SettingsTest.kt`:

```kotlin
package com.touringproject.v2.settings

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

class FakeStore : KeyValueStore {
  val values = mutableMapOf<String, String>()
  override suspend fun get(key: String) = values[key]
  override suspend fun set(key: String, value: String?) {
    if (value == null) values.remove(key) else values[key] = value
  }
}

class SettingsTest {
  private val maps = LaunchableApp("com.google.android.apps.maps", "マップ")

  @Test
  fun random_user_name_is_6_lowercase_letters_or_digits() {
    repeat(50) { assertTrue(Regex("^[a-z0-9]{6}$").matches(randomUserName(Random(it))) ) }
  }

  @Test
  fun first_load_creates_and_saves_a_user_name_with_defaults() = runTest {
    val store = FakeStore()
    val loaded = SettingsRepository(store, Random(1)).load()
    assertTrue(USER_NAME_RE.matches(loaded.userName))
    assertEquals(Settings(userName = loaded.userName), loaded)
    assertEquals(loaded, decodeSettings(store.values[SETTINGS_KEY]).first)
  }

  @Test
  fun saved_settings_round_trip() = runTest {
    val store = FakeStore()
    val repo = SettingsRepository(store)
    val s = Settings("rider01", returnEnabled = false, returnApp = maps, returnTiming = ReturnTiming.SPOKEN, recentApps = listOf(maps), answerVolumeDb = 3)
    repo.update(s)
    assertEquals(s, SettingsRepository(store).load())
  }

  @Test
  fun broken_values_fall_back_to_defaults() {
    val raw = """{"userName":"NO","returnEnabled":"yes","returnApp":{"packageName":1},"returnTiming":"later","recentApps":[{"packageName":"a","label":"A"},3],"answerVolumeDb":12}"""
    val (s, needsSave) = decodeSettings(raw, Random(2))
    assertTrue(needsSave)
    assertTrue(s.returnEnabled)
    assertNull(s.returnApp)
    assertEquals(ReturnTiming.SENT, s.returnTiming)
    assertEquals(listOf(LaunchableApp("a", "A")), s.recentApps)
    assertEquals(DEFAULT_VOLUME_DB, s.answerVolumeDb)
  }

  @Test
  fun not_json_falls_back_to_defaults() {
    val (s, needsSave) = decodeSettings("{not json", Random(3))
    assertTrue(needsSave)
    assertEquals(Settings(userName = s.userName), s)
    assertFalse(decodeSettings(encodeSettings(s)).second)
  }

  @Test
  fun recent_apps_keep_the_latest_five_without_duplicates() {
    val apps = (1..6).map { LaunchableApp("p$it", "A$it") }
    var recent = emptyList<LaunchableApp>()
    apps.forEach { recent = withRecentApp(recent, it) }
    assertEquals(listOf("p6", "p5", "p4", "p3", "p2"), recent.map { it.packageName })
    assertEquals(listOf("p4", "p6", "p5", "p3", "p2"), withRecentApp(recent, apps[3]).map { it.packageName })
  }

  @Test
  fun mask_shows_only_the_last_four_characters() {
    assertEquals("••••••••7890", maskKey("abcdef1234567890"))
    assertEquals("••••", maskKey("abcd"))
  }
}

class ApiKeyStoreTest {
  // Reverses the bytes: enough to tell sealed from plain without the Android Keystore.
  private class FakeCipher : SecretCipher {
    override fun encrypt(plain: ByteArray) = plain.reversedArray()
    override fun decrypt(sealed: ByteArray) = sealed.reversedArray()
  }

  @Test
  fun the_key_is_stored_sealed_and_read_back() = runTest {
    val store = FakeStore()
    ApiKeyStore(store, FakeCipher()).save("secret-key")
    assertFalse(store.values[API_KEY_KEY]!!.contains("secret-key"))
    val reloaded = ApiKeyStore(store, FakeCipher())
    assertEquals("secret-key", reloaded.load())
    assertEquals("secret-key", reloaded.current())
  }

  @Test
  fun deleting_the_key_removes_it() = runTest {
    val store = FakeStore()
    val keys = ApiKeyStore(store, FakeCipher())
    keys.save("secret-key")
    keys.save(null)
    assertNull(store.values[API_KEY_KEY])
    assertNull(ApiKeyStore(store, FakeCipher()).load())
  }

  @Test
  fun a_key_that_cannot_be_decrypted_reads_as_no_key() = runTest {
    val store = FakeStore()
    store.values[API_KEY_KEY] = "AAAA"
    val broken = object : SecretCipher {
      override fun encrypt(plain: ByteArray) = plain
      override fun decrypt(sealed: ByteArray): ByteArray = throw javax.crypto.AEADBadTagException()
    }
    assertNull(ApiKeyStore(store, broken).load())
  }
}
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*settings*'`
Expected: コンパイルエラー（`Settings`・`SettingsRepository` などが無い）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/settings/Settings.kt`:

```kotlin
package com.touringproject.v2.settings

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.random.Random

// Settings kept on the device. The connection key is stored separately (ApiKeyStore).
enum class ReturnTiming { SENT, ANSWERED, SPOKEN }

@Serializable
data class LaunchableApp(val packageName: String, val label: String)

// How much the Backend raises the answer audio (SC-21). The Backend accepts exactly these values; Polly stops at +6 dB.
val VOLUME_DB_CHOICES = listOf(0, 3, 6)
const val DEFAULT_VOLUME_DB = 6

data class Settings(
  val userName: String,
  val returnEnabled: Boolean = true,
  val returnApp: LaunchableApp? = null,
  val returnTiming: ReturnTiming = ReturnTiming.SENT,
  val recentApps: List<LaunchableApp> = emptyList(),
  val answerVolumeDb: Int = DEFAULT_VOLUME_DB,
)

val USER_NAME_RE = Regex("^[a-z0-9]{3,20}$")
private const val ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
private val json = Json { ignoreUnknownKeys = true }

fun randomUserName(random: Random = Random.Default): String =
  (1..6).map { ALPHABET[random.nextInt(ALPHABET.length)] }.joinToString("")

/** Reads saved settings; anything missing or broken falls back to its default. needsSave is true when a user name was made up. */
fun decodeSettings(raw: String?, random: Random = Random.Default): Pair<Settings, Boolean> {
  val obj: JsonObject = runCatching { json.parseToJsonElement(raw ?: "").jsonObject }.getOrElse { JsonObject(emptyMap()) }
  fun string(key: String) = runCatching { obj[key]?.jsonPrimitive?.contentOrNull }.getOrNull()
  fun app(element: kotlinx.serialization.json.JsonElement?) =
    runCatching { element?.let { json.decodeFromJsonElement<LaunchableApp>(it) } }.getOrNull()
  val savedName = string("userName")?.takeIf { USER_NAME_RE.matches(it) }
  val settings = Settings(
    userName = savedName ?: randomUserName(random),
    returnEnabled = runCatching { obj["returnEnabled"]?.jsonPrimitive?.booleanOrNull }.getOrNull() ?: true,
    returnApp = app(obj["returnApp"]),
    returnTiming = ReturnTiming.entries.firstOrNull { it.name.lowercase() == string("returnTiming") } ?: ReturnTiming.SENT,
    recentApps = runCatching { obj["recentApps"]?.jsonArray?.mapNotNull { app(it) } }.getOrNull() ?: emptyList(),
    answerVolumeDb = runCatching { obj["answerVolumeDb"]?.jsonPrimitive?.intOrNull }.getOrNull()
      ?.takeIf { it in VOLUME_DB_CHOICES } ?: DEFAULT_VOLUME_DB,
  )
  return settings to (savedName == null)
}

fun encodeSettings(settings: Settings): String = json.encodeToString(
  SavedSettings.serializer(),
  SavedSettings(
    userName = settings.userName,
    returnEnabled = settings.returnEnabled,
    returnApp = settings.returnApp,
    returnTiming = settings.returnTiming.name.lowercase(),
    recentApps = settings.recentApps,
    answerVolumeDb = settings.answerVolumeDb,
  ),
)

@Serializable
private data class SavedSettings(
  val userName: String,
  val returnEnabled: Boolean,
  val returnApp: LaunchableApp?,
  val returnTiming: String,
  val recentApps: List<LaunchableApp>,
  val answerVolumeDb: Int,
)

fun withRecentApp(recent: List<LaunchableApp>, app: LaunchableApp, max: Int = 5): List<LaunchableApp> =
  (listOf(app) + recent.filter { it.packageName != app.packageName }).take(max)

fun maskKey(key: String): String = if (key.length <= 4) "••••" else "••••••••${key.takeLast(4)}"
```

`app/src/main/java/com/touringproject/v2/settings/SettingsRepository.kt`:

```kotlin
package com.touringproject.v2.settings

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlin.random.Random

interface KeyValueStore {
  suspend fun get(key: String): String?
  suspend fun set(key: String, value: String?)
}

private val Context.dataStore by preferencesDataStore(name = "trv2")

class DataStoreKeyValueStore(private val context: Context) : KeyValueStore {
  override suspend fun get(key: String): String? = context.dataStore.data.map { it[stringPreferencesKey(key)] }.first()

  override suspend fun set(key: String, value: String?) {
    context.dataStore.edit { prefs ->
      if (value == null) prefs.remove(stringPreferencesKey(key)) else prefs[stringPreferencesKey(key)] = value
    }
  }
}

const val SETTINGS_KEY = "trv2.settings"

/** Holds the settings in memory for synchronous reads by the ask loop and writes changes through to the store. */
class SettingsRepository(private val store: KeyValueStore, private val random: Random = Random.Default) {
  private val state = MutableStateFlow<Settings?>(null)
  val settings: StateFlow<Settings?> = state.asStateFlow()

  suspend fun load(): Settings {
    val (loaded, needsSave) = decodeSettings(store.get(SETTINGS_KEY), random)
    if (needsSave) store.set(SETTINGS_KEY, encodeSettings(loaded))
    state.value = loaded
    return loaded
  }

  fun current(): Settings = checkNotNull(state.value) { "settings not loaded" }

  suspend fun update(next: Settings) {
    state.value = next
    store.set(SETTINGS_KEY, encodeSettings(next))
  }
}
```

`app/src/main/java/com/touringproject/v2/settings/ApiKeyStore.kt`:

```kotlin
package com.touringproject.v2.settings

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.security.KeyStore
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

interface SecretCipher {
  fun encrypt(plain: ByteArray): ByteArray
  fun decrypt(sealed: ByteArray): ByteArray
}

/** AES-GCM with a key that never leaves the Android Keystore. Output is the 12-byte IV followed by the ciphertext. */
class KeystoreCipher(private val alias: String = "trv2.apiKey") : SecretCipher {
  private fun key(): SecretKey {
    val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    (keyStore.getKey(alias, null) as? SecretKey)?.let { return it }
    val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
    generator.init(
      KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
        .build(),
    )
    return generator.generateKey()
  }

  override fun encrypt(plain: ByteArray): ByteArray {
    val cipher = Cipher.getInstance(TRANSFORMATION).apply { init(Cipher.ENCRYPT_MODE, key()) }
    return cipher.iv + cipher.doFinal(plain)
  }

  override fun decrypt(sealed: ByteArray): ByteArray {
    val cipher = Cipher.getInstance(TRANSFORMATION)
    cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, sealed, 0, IV_BYTES))
    return cipher.doFinal(sealed, IV_BYTES, sealed.size - IV_BYTES)
  }

  private companion object {
    const val TRANSFORMATION = "AES/GCM/NoPadding"
    const val IV_BYTES = 12
  }
}

const val API_KEY_KEY = "trv2.apiKey"

/** The connection key, encrypted at rest. A value that cannot be decrypted (e.g. the Keystore key is gone) reads as no key. */
class ApiKeyStore(private val store: KeyValueStore, private val cipher: SecretCipher) {
  private val state = MutableStateFlow<String?>(null)
  val apiKey: StateFlow<String?> = state.asStateFlow()

  suspend fun load(): String? {
    val sealed = store.get(API_KEY_KEY)
    state.value = sealed?.let {
      runCatching { String(cipher.decrypt(Base64.getDecoder().decode(it)), Charsets.UTF_8) }.getOrNull()
    }
    return state.value
  }

  fun current(): String? = state.value

  suspend fun save(key: String?) {
    state.value = key
    store.set(API_KEY_KEY, key?.let { Base64.getEncoder().encodeToString(cipher.encrypt(it.toByteArray(Charsets.UTF_8))) })
  }
}
```

- [ ] **Step 4: テストを通す**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*settings*'`
Expected: PASS（`SettingsTest` 7件・`ApiKeyStoreTest` 3件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/settings app/src/test/java/com/touringproject/v2/settings
git commit -m "feat: keep settings in DataStore and the connection key encrypted"
```

---

### Task 3: Backend の API

**Files:**
- Create: `app/src/main/java/.../api/ApiClient.kt`
- Test: `app/src/test/java/.../api/ApiClientTest.kt`

**Interfaces:**
- Produces:
  - `enum class ApiErrorKind { INVALID_KEY, BAD_REQUEST, NOT_FOUND, RATE_LIMITED, SERVER, NETWORK }`、`class ApiError(kind, message)`
  - `@Serializable` の `Point`・`HeadingSample(latitude, longitude, at: String)`・`AskBody`・`AskAccepted(askId, conversationId, conversationExpiresAt)`・`AudioClip(seq, url)`・`AskResult(askId, status, transcript, answer, audio, error)`
  - `interface AskApi { suspend fun postAsk(body): AskAccepted; suspend fun getAsk(askId): AskResult }`
  - `ApiClient(baseUrl, apiKey, userName, maxAttempts = 3, timeoutMs = 15_000, retryDelay, http)`: `AskApi` と `suspend checkKey()`

POST は 429 だけ試し直す（応答が失われても質問ができている場合がある）。GET は 429・5xx・通信の失敗を試し直す。`callTimeout` で1回のやり取り全体を打ち切る。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/api/ApiClientTest.kt`:

```kotlin
package com.touringproject.v2.api

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class ApiClientTest {
  private val server = MockWebServer().apply { start() }
  private val delays = mutableListOf<Long>()

  private fun client(timeoutMs: Long = 15_000) =
    ApiClient(server.url("/Prod/").toString(), "key-1", "rider01", timeoutMs = timeoutMs, retryDelay = { delays += it })

  private fun json(code: Int, body: String = "{}") = MockResponse().setResponseCode(code).setBody(body)

  @After
  fun tearDown() = server.shutdown()

  @Test
  fun postAsk_sends_headers_and_json() = runTest {
    server.enqueue(json(202, """{"askId":"a1","conversationId":"c1","conversationExpiresAt":"2026-01-01T00:15:00Z"}"""))
    val accepted = client().postAsk(AskBody(audio = "UENN", location = Point(35.0, 139.0), volumeDb = 6))
    assertEquals(AskAccepted("a1", "c1", "2026-01-01T00:15:00Z"), accepted)
    val request = server.takeRequest()
    assertEquals("POST", request.method)
    assertEquals("/Prod/asks", request.path)
    assertEquals("key-1", request.getHeader("x-api-key"))
    assertEquals("rider01", request.getHeader("x-user-name"))
    val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
    assertEquals("UENN", body["audio"]!!.jsonPrimitive.content)
    assertEquals(6, body["volumeDb"]!!.jsonPrimitive.content.toInt())
    // Absent fields are left out rather than sent as null.
    assertFalse("conversationId" in body)
  }

  @Test
  fun getAsk_reads_the_result_and_ignores_unknown_fields() = runTest {
    server.enqueue(json(200, """{"askId":"a1","status":"completed","transcript":"Q","answer":"A","audio":[{"seq":1,"url":"u"}],"error":null,"timings":{"accepted":"t"}}"""))
    assertEquals(AskResult("a1", "completed", "Q", "A", listOf(AudioClip(1, "u")), null), client().getAsk("a1"))
  }

  @Test
  fun get_retries_transient_errors_then_succeeds() = runTest {
    server.enqueue(json(503))
    server.enqueue(json(429))
    server.enqueue(json(200, """{"askId":"a1","status":"processing"}"""))
    assertEquals("processing", client().getAsk("a1").status)
    assertEquals(listOf(500L, 1_000L), delays)
  }

  @Test
  fun post_does_not_retry_network_errors_but_retries_429() = runTest {
    server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
    val error = runCatching { client().postAsk(AskBody(text = "q")) }.exceptionOrNull() as ApiError
    assertEquals(ApiErrorKind.NETWORK, error.kind)
    assertEquals(1, server.requestCount)
    server.enqueue(json(429))
    server.enqueue(json(202, """{"askId":"a2","conversationId":"c1","conversationExpiresAt":"2026-01-01T00:15:00Z"}"""))
    assertEquals("a2", client().postAsk(AskBody(text = "q")).askId)
  }

  @Test
  fun invalid_key_is_not_retried() = runTest {
    server.enqueue(json(403))
    val error = runCatching { client().getAsk("a1") }.exceptionOrNull() as ApiError
    assertEquals(ApiErrorKind.INVALID_KEY, error.kind)
    assertEquals(1, server.requestCount)
  }

  @Test
  fun checkKey_treats_404_as_a_working_key() = runTest {
    server.enqueue(json(404))
    client().checkKey()
    server.enqueue(json(403))
    assertEquals(ApiErrorKind.INVALID_KEY, (runCatching { client().checkKey() }.exceptionOrNull() as ApiError).kind)
  }

  @Test
  fun a_stalled_request_times_out_as_a_network_error() = runTest {
    repeat(3) { server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE)) }
    val error = runCatching { client(timeoutMs = 200).getAsk("a1") }.exceptionOrNull() as ApiError
    assertEquals(ApiErrorKind.NETWORK, error.kind)
  }
}
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ApiClientTest'`
Expected: コンパイルエラー（`ApiClient` が無い）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/api/ApiClient.kt`:

```kotlin
package com.touringproject.v2.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

// Backend API (Backend/openapi.yaml). Errors are classified so the ask loop can pick the spoken message.
enum class ApiErrorKind { INVALID_KEY, BAD_REQUEST, NOT_FOUND, RATE_LIMITED, SERVER, NETWORK }

class ApiError(val kind: ApiErrorKind, message: String? = null) : Exception(message ?: kind.name)

@Serializable data class Point(val latitude: Double, val longitude: Double)

@Serializable data class HeadingSample(val latitude: Double, val longitude: Double, val at: String)

@Serializable
data class AskBody(
  val audio: String? = null,
  val text: String? = null,
  val location: Point? = null,
  val headingSample: HeadingSample? = null,
  val conversationId: String? = null,
  val volumeDb: Int? = null,
)

@Serializable data class AskAccepted(val askId: String, val conversationId: String, val conversationExpiresAt: String)

@Serializable data class AudioClip(val seq: Int, val url: String)

@Serializable
data class AskResult(
  val askId: String,
  val status: String,
  val transcript: String? = null,
  val answer: String? = null,
  val audio: List<AudioClip> = emptyList(),
  val error: String? = null,
)

interface AskApi {
  suspend fun postAsk(body: AskBody): AskAccepted
  suspend fun getAsk(askId: String): AskResult
}

private val TRANSIENT = setOf(ApiErrorKind.RATE_LIMITED, ApiErrorKind.SERVER, ApiErrorKind.NETWORK)

// Any UUID works: a valid key gets 404 for an unknown ask, an invalid key gets 403.
private const val PROBE_ASK_ID = "00000000-0000-4000-8000-000000000000"

private fun kindFor(status: Int): ApiErrorKind? = when {
  status == 403 -> ApiErrorKind.INVALID_KEY
  status == 400 -> ApiErrorKind.BAD_REQUEST
  status == 404 -> ApiErrorKind.NOT_FOUND
  status == 429 -> ApiErrorKind.RATE_LIMITED
  status >= 500 -> ApiErrorKind.SERVER
  else -> null
}

class ApiClient(
  baseUrl: String,
  private val apiKey: String,
  private val userName: String,
  private val maxAttempts: Int = 3,
  timeoutMs: Long = 15_000,
  private val retryDelay: suspend (Long) -> Unit = { delay(it) },
  http: OkHttpClient = OkHttpClient(),
) : AskApi {
  private val baseUrl = baseUrl.trimEnd('/')
  // callTimeout bounds the whole exchange, so a stalled connection cannot hang the ask.
  private val http = http.newBuilder().callTimeout(timeoutMs, TimeUnit.MILLISECONDS).build()
  private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

  // Only 429 is retried for POST: a lost response may already have created an ask.
  override suspend fun postAsk(body: AskBody): AskAccepted =
    json.decodeFromString(request("POST", "/asks", json.encodeToString(AskBody.serializer(), body), setOf(ApiErrorKind.RATE_LIMITED)))

  override suspend fun getAsk(askId: String): AskResult = json.decodeFromString(request("GET", "/asks/$askId", null, TRANSIENT))

  suspend fun checkKey() {
    try {
      request("GET", "/asks/$PROBE_ASK_ID", null, TRANSIENT)
    } catch (e: ApiError) {
      if (e.kind != ApiErrorKind.NOT_FOUND) throw e
    }
  }

  private suspend fun request(method: String, path: String, body: String?, retryOn: Set<ApiErrorKind>): String {
    var attempt = 1
    while (true) {
      try {
        return once(method, path, body)
      } catch (e: ApiError) {
        if (e.kind !in retryOn || attempt >= maxAttempts) throw e
        retryDelay(500L * attempt)
        attempt += 1
      }
    }
  }

  private suspend fun once(method: String, path: String, body: String?): String = withContext(Dispatchers.IO) {
    val request = Request.Builder()
      .url("$baseUrl$path")
      .header("x-api-key", apiKey)
      .header("x-user-name", userName)
      .method(method, body?.toRequestBody("application/json".toMediaType()))
      .build()
    try {
      http.newCall(request).execute().use { response ->
        kindFor(response.code)?.let { throw ApiError(it, "HTTP ${response.code}") }
        response.body?.string() ?: throw ApiError(ApiErrorKind.NETWORK, "empty body")
      }
    } catch (e: IOException) {
      throw ApiError(ApiErrorKind.NETWORK, e.toString())
    }
  }
}
```

- [ ] **Step 4: テストを通す**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ApiClientTest'`
Expected: PASS（7件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/api app/src/test/java/com/touringproject/v2/api
git commit -m "feat: add the Backend API client"
```

---

### Task 4: 一巡の状態機械・失敗・ポーリング・会話

**Files:**
- Create: `app/src/main/java/.../audio/AudioTypes.kt`、`ask/Flow.kt`、`ask/Failures.kt`、`ask/Polling.kt`、`ask/Conversation.kt`
- Test: `app/src/test/java/.../ask/FlowTest.kt`、`ask/PollingAndConversationTest.kt`

**Interfaces:**
- Consumes: `Settings`・`ReturnTiming`（Task 2）、`ApiError`・`AskResult`（Task 3）
- Produces:
  - `data class MediaVolume(current: Int, max: Int)`、`data class InputDevice(type: Type, name: String)`（`Type { BLUETOOTH, BUILTIN, OTHER }`）、`data class RouteResult(ok, note)`
  - `enum Source { HANDSFREE, SCREEN }`、`enum Phase { IDLE, RECORDING, SENDING, WAITING, SPEAKING, FAILED }`、`enum FailureReason`、`data class FlowState`、`IDLE`、`sealed interface FlowEvent`、`reduce(state, event)`、`isBusy(state)`、`shouldReturnNow(source, settings, moment: ReturnTiming)`
  - `BUSY_MESSAGE`、`spokenMessage(reason)`、`failureFromServer(error: String?)`
  - `nextDelay(elapsedMs)`、`sealed interface PollOutcome { Done(result); Timeout; Cancelled }`、`suspend pollUntilDone(get, sleep, now, isCancelled)`、`POLL_TIMEOUT_MS`
  - `class ConversationState { current(now); update(id, expiresAtIso); reset(); expiresAt(now) }`

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ask/FlowTest.kt`:

```kotlin
package com.touringproject.v2.ask

import com.touringproject.v2.audio.MediaVolume
import com.touringproject.v2.settings.LaunchableApp
import com.touringproject.v2.settings.ReturnTiming
import com.touringproject.v2.settings.Settings
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class FlowTest {
  private fun run(vararg events: FlowEvent) = events.fold(IDLE) { s, e -> reduce(s, e) }

  @Test
  fun happy_path() {
    val s = run(
      FlowEvent.Start(Source.HANDSFREE, 1),
      FlowEvent.StopRecording(2),
      FlowEvent.Sent("a1", 3),
      FlowEvent.Answered("答え", 4),
    )
    assertEquals(Phase.SPEAKING, s.phase)
    assertEquals("a1", s.askId)
    assertEquals("答え", s.answer)
    assertEquals(4L, s.phaseStartedAt)
    assertEquals(IDLE, reduce(s, FlowEvent.Spoken(5)))
  }

  @Test
  fun out_of_order_events_are_ignored() {
    assertSame(IDLE, reduce(IDLE, FlowEvent.Sent("a1", 1)))
    val recording = run(FlowEvent.Start(Source.SCREEN, 1))
    assertSame(recording, reduce(recording, FlowEvent.Answered("x", 2)))
    assertSame(recording, reduce(recording, FlowEvent.Start(Source.HANDSFREE, 2)))
  }

  @Test
  fun phone_mic_flag_only_while_recording() {
    assertTrue(run(FlowEvent.Start(Source.SCREEN, 1), FlowEvent.PhoneMic(2)).phoneMic)
    assertFalse(run(FlowEvent.Start(Source.SCREEN, 1), FlowEvent.StopRecording(2), FlowEvent.PhoneMic(3)).phoneMic)
  }

  @Test
  fun failure_and_a_new_start_after_it() {
    val failed = run(FlowEvent.Start(Source.SCREEN, 1), FlowEvent.Fail(FailureReason.NETWORK, 2))
    assertEquals(Phase.FAILED, failed.phase)
    assertEquals(FailureReason.NETWORK, failed.failure)
    val again = reduce(failed, FlowEvent.Start(Source.HANDSFREE, 3))
    assertEquals(Phase.RECORDING, again.phase)
    assertEquals(null, again.failure)
    assertSame(IDLE, reduce(IDLE, FlowEvent.Fail(FailureReason.NETWORK, 1)))
  }

  @Test
  fun busy_phases() {
    assertFalse(isBusy(IDLE))
    assertTrue(isBusy(run(FlowEvent.Start(Source.SCREEN, 1))))
    assertFalse(isBusy(run(FlowEvent.Start(Source.SCREEN, 1), FlowEvent.Fail(FailureReason.MIC, 2))))
  }

  @Test
  fun return_only_for_handsfree_at_the_chosen_moment() {
    val s = Settings(userName = "abc", returnApp = LaunchableApp("maps", "マップ"))
    assertTrue(shouldReturnNow(Source.HANDSFREE, s, ReturnTiming.SENT))
    assertFalse(shouldReturnNow(Source.SCREEN, s, ReturnTiming.SENT))
    assertFalse(shouldReturnNow(Source.HANDSFREE, s, ReturnTiming.SPOKEN))
    assertFalse(shouldReturnNow(Source.HANDSFREE, s.copy(returnEnabled = false), ReturnTiming.SENT))
    assertFalse(shouldReturnNow(Source.HANDSFREE, s.copy(returnApp = null), ReturnTiming.SENT))
  }

  @Test
  fun spoken_messages() {
    assertEquals("聞き取れませんでした。もう一度お話しください。", spokenMessage(FailureReason.NO_SPEECH))
    assertEquals("うまく答えられませんでした。もう一度お話しください。", spokenMessage(FailureReason.AGENT_FAILED))
    assertEquals("時間切れです。もう一度お話しください。", spokenMessage(FailureReason.TIMEOUT))
    assertEquals("通信できないため、質問できませんでした。", spokenMessage(FailureReason.NETWORK))
    assertEquals("接続キーを確かめてください。", spokenMessage(FailureReason.NO_KEY))
    assertEquals("録音できませんでした。", spokenMessage(FailureReason.MIC))
  }

  @Test
  fun server_failure_reasons() {
    assertEquals(FailureReason.NO_SPEECH, failureFromServer("no_speech"))
    assertEquals(FailureReason.TTS_FAILED, failureFromServer("tts_failed"))
    assertEquals(FailureReason.AGENT_FAILED, failureFromServer("something_new"))
    assertEquals(FailureReason.AGENT_FAILED, failureFromServer(null))
  }

  @Test
  fun the_media_volume_read_at_the_start_stays_with_the_ask() {
    val s = run(FlowEvent.Start(Source.HANDSFREE, 1, MediaVolume(3, 15)), FlowEvent.StopRecording(2))
    assertEquals(MediaVolume(3, 15), s.mediaVolume)
  }
}
```

`app/src/test/java/com/touringproject/v2/ask/PollingAndConversationTest.kt`:

```kotlin
package com.touringproject.v2.ask

import com.touringproject.v2.api.ApiError
import com.touringproject.v2.api.ApiErrorKind
import com.touringproject.v2.api.AskResult
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

class PollingTest {
  private val processing = AskResult("a1", "processing")
  private val completed = AskResult("a1", "completed", answer = "x")

  private class Clock {
    var now = 0L
    val sleeps = mutableListOf<Long>()
    suspend fun sleep(ms: Long) { sleeps += ms; now += ms }
  }

  private suspend fun poll(clock: Clock, cancelled: () -> Boolean = { false }, get: suspend () -> AskResult) =
    pollUntilDone(get, clock::sleep, { clock.now }, cancelled)

  @Test
  fun delays_are_1s_for_10s_then_2s() {
    assertEquals(1_000L, nextDelay(0))
    assertEquals(1_000L, nextDelay(9_999))
    assertEquals(2_000L, nextDelay(10_000))
  }

  @Test
  fun returns_the_first_finished_result() = runTest {
    val answers = mutableListOf(processing, processing, completed)
    val clock = Clock()
    assertEquals(PollOutcome.Done(completed), poll(clock) { answers.removeAt(0) })
    assertEquals(listOf(1_000L, 1_000L, 1_000L), clock.sleeps)
  }

  @Test
  fun transient_errors_are_skipped() = runTest {
    var calls = 0
    val outcome = poll(Clock()) { if (++calls == 1) throw ApiError(ApiErrorKind.SERVER) else completed }
    assertEquals(PollOutcome.Done(completed), outcome)
  }

  @Test
  fun invalid_key_stops_polling() = runTest {
    val error = runCatching { poll(Clock()) { throw ApiError(ApiErrorKind.INVALID_KEY) } }.exceptionOrNull()
    assertEquals(ApiErrorKind.INVALID_KEY, (error as ApiError).kind)
  }

  @Test
  fun gives_up_after_two_minutes() = runTest {
    val clock = Clock()
    assertEquals(PollOutcome.Timeout, poll(clock) { processing })
    assertEquals(POLL_TIMEOUT_MS, clock.now)
  }

  @Test
  fun cancellation_stops_polling() = runTest {
    var calls = 0
    assertEquals(PollOutcome.Cancelled, poll(Clock(), cancelled = { true }) { calls++; processing })
    assertEquals(0, calls)
  }
}

class ConversationTest {
  @Test
  fun conversation_continues_until_it_expires() {
    val c = ConversationState()
    c.update("c1", "2026-01-01T00:15:00Z")
    val expiry = java.time.Instant.parse("2026-01-01T00:15:00Z").toEpochMilli()
    assertEquals("c1", c.current(expiry - 1))
    assertEquals(expiry, c.expiresAt(expiry - 1))
    assertNull(c.current(expiry))
    assertNull(c.current(expiry - 1))
  }

  @Test
  fun reset_starts_a_new_conversation() {
    val c = ConversationState()
    c.update("c1", "2999-01-01T00:00:00Z")
    c.reset()
    assertNull(c.current(0))
    assertNull(c.expiresAt(0))
  }

  @Test
  fun unparseable_expiry_means_no_conversation() {
    val c = ConversationState()
    c.update("c1", "not a date")
    assertNull(c.current(0))
  }
}
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ask*'`
Expected: コンパイルエラー（`reduce`・`pollUntilDone` などが無い）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/audio/AudioTypes.kt`:

```kotlin
package com.touringproject.v2.audio

// Values the ask loop reads from the audio side; kept apart from AudioRoute so the loop compiles without it.
data class MediaVolume(val current: Int, val max: Int)

data class InputDevice(val type: Type, val name: String) {
  enum class Type { BLUETOOTH, BUILTIN, OTHER }
}

data class RouteResult(val ok: Boolean, val note: String)
```

`app/src/main/java/com/touringproject/v2/ask/Flow.kt`:

```kotlin
package com.touringproject.v2.ask

import com.touringproject.v2.audio.MediaVolume
import com.touringproject.v2.settings.ReturnTiming
import com.touringproject.v2.settings.Settings

// The ask loop as a pure state machine (slice 1 spec §5.2). Screens, cues and returning to the nav app read this state.
enum class Source { HANDSFREE, SCREEN }

enum class Phase { IDLE, RECORDING, SENDING, WAITING, SPEAKING, FAILED }

enum class FailureReason { NO_SPEECH, TRANSCRIBE_FAILED, AGENT_FAILED, TTS_FAILED, TIMEOUT, NETWORK, INVALID_KEY, NO_KEY, MIC, SERVICE }

data class FlowState(
  val phase: Phase = Phase.IDLE,
  val source: Source? = null,
  val askId: String? = null,
  val answer: String? = null,
  val failure: FailureReason? = null,
  val phoneMic: Boolean = false,
  val phaseStartedAt: Long = 0,
  // Read when the ask starts, before the intercom route switches the music stream to the call device's volume.
  val mediaVolume: MediaVolume? = null,
)

val IDLE = FlowState()

sealed interface FlowEvent {
  val now: Long
  data class Start(val source: Source, override val now: Long, val mediaVolume: MediaVolume? = null) : FlowEvent
  data class PhoneMic(override val now: Long) : FlowEvent
  data class StopRecording(override val now: Long) : FlowEvent
  data class Sent(val askId: String, override val now: Long) : FlowEvent
  data class Answered(val answer: String, override val now: Long) : FlowEvent
  data class Spoken(override val now: Long) : FlowEvent
  data class Fail(val reason: FailureReason, override val now: Long) : FlowEvent
  data class Dismiss(override val now: Long) : FlowEvent
}

fun reduce(state: FlowState, event: FlowEvent): FlowState = when (event) {
  is FlowEvent.Start ->
    if (state.phase == Phase.IDLE || state.phase == Phase.FAILED) {
      FlowState(phase = Phase.RECORDING, source = event.source, phaseStartedAt = event.now, mediaVolume = event.mediaVolume)
    } else state
  is FlowEvent.PhoneMic -> if (state.phase == Phase.RECORDING) state.copy(phoneMic = true) else state
  is FlowEvent.StopRecording ->
    if (state.phase == Phase.RECORDING) state.copy(phase = Phase.SENDING, phaseStartedAt = event.now) else state
  is FlowEvent.Sent ->
    if (state.phase == Phase.SENDING) state.copy(phase = Phase.WAITING, askId = event.askId, phaseStartedAt = event.now) else state
  is FlowEvent.Answered ->
    if (state.phase == Phase.WAITING) state.copy(phase = Phase.SPEAKING, answer = event.answer, phaseStartedAt = event.now) else state
  is FlowEvent.Fail ->
    if (state.phase == Phase.IDLE) state else state.copy(phase = Phase.FAILED, failure = event.reason, phaseStartedAt = event.now)
  is FlowEvent.Spoken, is FlowEvent.Dismiss -> if (state.phase == Phase.IDLE) state else IDLE
}

fun isBusy(state: FlowState): Boolean = state.phase != Phase.IDLE && state.phase != Phase.FAILED

fun shouldReturnNow(source: Source?, settings: Settings, moment: ReturnTiming): Boolean =
  source == Source.HANDSFREE && settings.returnEnabled && settings.returnApp != null && settings.returnTiming == moment
```

`app/src/main/java/com/touringproject/v2/ask/Failures.kt`:

```kotlin
package com.touringproject.v2.ask

// What the rider hears when something goes wrong (slice 1 spec §8.1).
const val BUSY_MESSAGE = "いま応答中です。少し待ってからもう一度お話しください。"

fun spokenMessage(reason: FailureReason): String = when (reason) {
  FailureReason.NO_SPEECH -> "聞き取れませんでした。もう一度お話しください。"
  FailureReason.TRANSCRIBE_FAILED, FailureReason.AGENT_FAILED, FailureReason.TTS_FAILED -> "うまく答えられませんでした。もう一度お話しください。"
  FailureReason.TIMEOUT -> "時間切れです。もう一度お話しください。"
  FailureReason.NETWORK -> "通信できないため、質問できませんでした。"
  FailureReason.INVALID_KEY, FailureReason.NO_KEY -> "接続キーを確かめてください。"
  FailureReason.MIC -> "録音できませんでした。"
  FailureReason.SERVICE -> "準備できなかったため、質問できませんでした。もう一度お試しください。"
}

private val SERVER_REASONS = mapOf(
  "no_speech" to FailureReason.NO_SPEECH,
  "transcribe_failed" to FailureReason.TRANSCRIBE_FAILED,
  "agent_failed" to FailureReason.AGENT_FAILED,
  "tts_failed" to FailureReason.TTS_FAILED,
)

fun failureFromServer(error: String?): FailureReason = SERVER_REASONS[error] ?: FailureReason.AGENT_FAILED
```

`app/src/main/java/com/touringproject/v2/ask/Polling.kt`:

```kotlin
package com.touringproject.v2.ask

import com.touringproject.v2.api.ApiError
import com.touringproject.v2.api.ApiErrorKind
import com.touringproject.v2.api.AskResult

// Poll schedule from 07 UC-5: every 1 s for 10 s, then every 2 s, give up at 120 s.
const val POLL_FAST_MS = 1_000L
const val POLL_SLOW_MS = 2_000L
const val FAST_WINDOW_MS = 10_000L
const val POLL_TIMEOUT_MS = 120_000L
private val FATAL = setOf(ApiErrorKind.INVALID_KEY, ApiErrorKind.BAD_REQUEST, ApiErrorKind.NOT_FOUND)

fun nextDelay(elapsedMs: Long): Long = if (elapsedMs < FAST_WINDOW_MS) POLL_FAST_MS else POLL_SLOW_MS

sealed interface PollOutcome {
  data class Done(val result: AskResult) : PollOutcome
  data object Timeout : PollOutcome
  data object Cancelled : PollOutcome
}

suspend fun pollUntilDone(
  get: suspend () -> AskResult,
  sleep: suspend (Long) -> Unit,
  now: () -> Long,
  isCancelled: () -> Boolean,
): PollOutcome {
  val startedAt = now()
  while (true) {
    val elapsed = now() - startedAt
    if (elapsed >= POLL_TIMEOUT_MS) return PollOutcome.Timeout
    sleep(nextDelay(elapsed))
    if (isCancelled()) return PollOutcome.Cancelled
    try {
      val result = get()
      if (result.status != "processing") return PollOutcome.Done(result)
    } catch (e: ApiError) {
      if (e.kind in FATAL) throw e
    }
  }
}
```

`app/src/main/java/com/touringproject/v2/ask/Conversation.kt`:

```kotlin
package com.touringproject.v2.ask

import java.time.Instant

// The conversation id the Backend issued and when it lapses (adr/0003). Kept in memory only.
class ConversationState {
  private var id: String? = null
  private var expiry = 0L

  fun current(now: Long): String? {
    if (id != null && now < expiry) return id
    reset()
    return null
  }

  fun update(id: String, expiresAtIso: String) {
    val parsed = runCatching { Instant.parse(expiresAtIso).toEpochMilli() }.getOrNull()
    if (parsed == null) {
      reset()
      return
    }
    this.id = id
    expiry = parsed
  }

  fun reset() {
    id = null
    expiry = 0
  }

  fun expiresAt(now: Long): Long? = if (current(now) == null) null else expiry
}
```

- [ ] **Step 4: テストを通す**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ask*'`
Expected: PASS（`FlowTest` 9件・`PollingTest` 6件・`ConversationTest` 3件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/audio/AudioTypes.kt app/src/main/java/com/touringproject/v2/ask \
  app/src/test/java/com/touringproject/v2/ask
git commit -m "feat: add the ask state machine, failure messages, polling and conversation"
```

---

### Task 5: 方位の材料と、押下の重複

**Files:**
- Create: `app/src/main/java/.../location/Heading.kt`、`handsfree/Press.kt`
- Test: `app/src/test/java/.../location/HeadingTest.kt`、`handsfree/PressTest.kt`

**Interfaces:**
- Consumes: `HeadingSample`（Task 3）
- Produces:
  - `data class Fix(latitude, longitude, timestamp: Long, accuracy: Double?)`、`distanceMeters(a, b)`、`pickHeadingSample(fixes, current): HeadingSample?`
  - `enum Claim { NEW, DUPLICATE, STALE }`、`PressTracker.claim(pressedAt, now)`、`PressGate(handle: () -> Unit)`: `offer(pressedAt, now)`・`openGate(now)`

React Native 版では、押下を Activity のライフサイクルとイベントの2つの道で受けていたので重複が起きた。ネイティブ版は `MainActivity` の1か所で受けるが、Activity の作り直しや、準備ができる前の押下（権限の確認中）は残るので、同じ仕組みを持つ。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/location/HeadingTest.kt`:

```kotlin
package com.touringproject.v2.location

import com.touringproject.v2.api.HeadingSample
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class HeadingTest {
  private val here = Fix(35.6812, 139.7671, 100_000, 5.0)
  private val behind = Fix(35.6806, 139.7671, 90_000, 5.0) // about 67 m south
  private val near = Fix(35.68119, 139.7671, 95_000, 5.0) // about 1 m

  @Test
  fun distance() {
    val d = distanceMeters(behind, here)
    assertTrue(d in 60.0..75.0)
  }

  @Test
  fun picks_the_newest_point_far_enough_behind() {
    val older = behind.copy(timestamp = 80_000)
    assertEquals(HeadingSample(35.6806, 139.7671, "1970-01-01T00:01:30Z"), pickHeadingSample(listOf(older, behind, near, here), here))
  }

  @Test
  fun test_no_sample_when_stationary() {
    assertNull(pickHeadingSample(listOf(near, here), here))
  }

  @Test
  fun ignores_points_older_than_a_minute_and_points_not_before_the_current_one() {
    assertNull(pickHeadingSample(listOf(behind.copy(timestamp = 30_000)), here))
    assertNull(pickHeadingSample(listOf(behind.copy(timestamp = 100_000)), here))
  }

  @Test
  fun test_no_sample_from_inaccurate_points() {
    assertNull(pickHeadingSample(listOf(behind.copy(accuracy = 30.0)), here))
  }

  @Test
  fun no_sample_when_the_current_point_itself_is_inaccurate() {
    assertNull(pickHeadingSample(listOf(behind), here.copy(accuracy = 30.0)))
  }

  @Test
  fun unknown_accuracy_is_accepted() {
    assertEquals(35.6806, pickHeadingSample(listOf(behind.copy(accuracy = null)), here.copy(accuracy = null))!!.latitude, 0.0)
  }
}
```

`app/src/test/java/com/touringproject/v2/handsfree/PressTest.kt`:

```kotlin
package com.touringproject.v2.handsfree

import org.junit.Assert.assertEquals
import org.junit.Test

class PressTest {
  @Test
  fun each_press_is_handled_once() {
    val t = PressTracker()
    assertEquals(Claim.NEW, t.claim(1_000, 1_000))
    assertEquals(Claim.DUPLICATE, t.claim(1_000, 1_500))
    assertEquals(Claim.NEW, t.claim(2_000, 2_000))
  }

  @Test
  fun old_presses_are_dropped() {
    assertEquals(Claim.STALE, PressTracker().claim(1_000, 1_000 + STALE_PRESS_MS + 1))
  }

  @Test
  fun a_press_before_the_app_is_ready_is_handled_once_it_is() {
    var handled = 0
    val gate = PressGate { handled++ }
    gate.offer(1_000, 1_000)
    assertEquals(0, handled)
    gate.openGate(2_000)
    assertEquals(1, handled)
  }

  @Test
  fun several_early_presses_start_one_question() {
    var handled = 0
    val gate = PressGate { handled++ }
    gate.offer(1_000, 1_000)
    gate.offer(1_200, 1_200)
    gate.openGate(2_000)
    gate.offer(1_200, 2_100)
    assertEquals(1, handled)
  }

  @Test
  fun an_early_press_that_went_stale_while_waiting_is_dropped() {
    var handled = 0
    val gate = PressGate { handled++ }
    gate.offer(1_000, 1_000)
    gate.openGate(1_000 + STALE_PRESS_MS + 1)
    assertEquals(0, handled)
  }

  @Test
  fun after_opening_presses_go_straight_through_and_duplicates_are_dropped() {
    var handled = 0
    val gate = PressGate { handled++ }
    gate.openGate(0)
    gate.offer(1_000, 1_000)
    gate.offer(1_000, 1_100)
    gate.offer(2_000, 2_000)
    assertEquals(2, handled)
  }
}
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*HeadingTest' --tests '*PressTest'`
Expected: コンパイルエラー（`pickHeadingSample`・`PressGate` が無い）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/location/Heading.kt`:

```kotlin
package com.touringproject.v2.location

import com.touringproject.v2.api.HeadingSample
import java.time.Instant
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

// Picks the older point the Backend uses to work out the direction of travel (07 UC-5).

/** accuracy is the radius in metres the device reports (null when unknown). */
data class Fix(val latitude: Double, val longitude: Double, val timestamp: Long, val accuracy: Double?)

const val MIN_SAMPLE_DISTANCE_M = 15.0
const val MAX_SAMPLE_AGE_MS = 60_000L
// GPS jitter of a stationary phone can exceed MIN_SAMPLE_DISTANCE_M with poor fixes.
const val MAX_ACCURACY_M = 20.0

private fun accurate(f: Fix) = f.accuracy == null || f.accuracy <= MAX_ACCURACY_M

fun distanceMeters(a: Fix, b: Fix): Double {
  val r = 6_371_000.0
  fun rad(d: Double) = Math.toRadians(d)
  val dLat = rad(b.latitude - a.latitude)
  val dLon = rad(b.longitude - a.longitude)
  val h = sin(dLat / 2).pow(2) + cos(rad(a.latitude)) * cos(rad(b.latitude)) * sin(dLon / 2).pow(2)
  return 2 * r * asin(sqrt(h))
}

fun pickHeadingSample(fixes: List<Fix>, current: Fix): HeadingSample? {
  if (!accurate(current)) return null
  val newest = fixes
    .filter {
      accurate(it) &&
        it.timestamp < current.timestamp &&
        current.timestamp - it.timestamp <= MAX_SAMPLE_AGE_MS &&
        distanceMeters(it, current) >= MIN_SAMPLE_DISTANCE_M
    }
    .maxByOrNull { it.timestamp } ?: return null
  return HeadingSample(newest.latitude, newest.longitude, Instant.ofEpochMilli(newest.timestamp).toString())
}
```

`app/src/main/java/com/touringproject/v2/handsfree/Press.kt`:

```kotlin
package com.touringproject.v2.handsfree

// The same press can arrive twice (a recreated activity, a repeated intent); a press older than a minute is stale.
const val STALE_PRESS_MS = 60_000L

enum class Claim { NEW, DUPLICATE, STALE }

class PressTracker {
  private var lastHandled = 0L

  fun claim(pressedAt: Long, now: Long): Claim {
    if (pressedAt <= lastHandled) return Claim.DUPLICATE
    if (now - pressedAt > STALE_PRESS_MS) return Claim.STALE
    lastHandled = pressedAt
    return Claim.NEW
  }
}

/**
 * Holds presses that arrive before the app is ready (settings still loading, permission prompts at first launch)
 * and hands the newest one over once it is; claiming them earlier would mark them handled with nobody to act on them.
 */
class PressGate(private val handle: () -> Unit) {
  private var held: Long? = null
  private var open = false
  private val tracker = PressTracker()

  @Synchronized
  fun offer(pressedAt: Long, now: Long) {
    if (!open) {
      held = maxOf(held ?: 0L, pressedAt)
      return
    }
    if (tracker.claim(pressedAt, now) == Claim.NEW) handle()
  }

  @Synchronized
  fun openGate(now: Long) {
    open = true
    val waiting = held
    held = null
    if (waiting != null) offer(waiting, now)
  }
}
```

- [ ] **Step 4: テストを通す**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*HeadingTest' --tests '*PressTest'`
Expected: PASS（`HeadingTest` 7件・`PressTest` 6件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/location/Heading.kt app/src/main/java/com/touringproject/v2/handsfree \
  app/src/test/java/com/touringproject/v2/location/HeadingTest.kt app/src/test/java/com/touringproject/v2/handsfree
git commit -m "feat: pick the heading sample and drop duplicate or stale presses"
```

---

### Task 6: 一巡の司令塔

**Files:**
- Create: `app/src/main/java/.../ask/AskPorts.kt`、`ask/AskController.kt`、`location/PositionTracker.kt`
- Test: `app/src/test/java/.../ask/AskControllerTest.kt`、`location/PositionTrackerTest.kt`

**Interfaces:**
- Consumes: Task 2〜5 のすべて
- Produces:
  - `AskPorts.kt` の interface: `RouteControl`・`Recorder`（`Recorded(pcm: ByteArray, name: String)`）・`RecordingSink`（`RecordingMeta`）・`Positions`・`KeepAlive`・`NavReturn`・`Cues`・`AnswerPlayer`・`Speech`、それらを束ねる `class AskDeps`
  - `AskController(deps: AskDeps, scope: CoroutineScope)`: `state: FlowState`、`runsStarted: Int`、`press()`・`tapToTalk()`・`stopRecording()`・`cancel()`・`resetConversation()`・`suspend run(source)`
  - `RECORD_LIMIT_MS = 20_000`、`pcmDurationMs(bytes)`
  - `PositionSource`・`Subscription`・`PositionTracker(source): Positions`、`MAX_CURRENT_AGE_MS`

React Native 版の `controller.ts` の振る舞いをそのまま移す。違いは2つだけ:
- 待ちは `deps.sleep`（アプリでは `delay`）。React Native 版の「ネイティブで待つ」は要らない。
- 司令塔はメインスレッド1本から呼ぶ前提で、状態をロックしない（アプリでは `MainScope` を渡す）。

`RecordingSink` は計画2（SC-12）で中身を作る。この計画では何もしない実装を渡す（Task 10）。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt`:

```kotlin
package com.touringproject.v2.ask

import com.touringproject.v2.api.ApiError
import com.touringproject.v2.api.ApiErrorKind
import com.touringproject.v2.api.AskAccepted
import com.touringproject.v2.api.AskApi
import com.touringproject.v2.api.AskBody
import com.touringproject.v2.api.AskResult
import com.touringproject.v2.api.AudioClip
import com.touringproject.v2.api.HeadingSample
import com.touringproject.v2.api.Point
import com.touringproject.v2.audio.InputDevice
import com.touringproject.v2.audio.MediaVolume
import com.touringproject.v2.location.Fix
import com.touringproject.v2.settings.LaunchableApp
import com.touringproject.v2.settings.ReturnTiming
import com.touringproject.v2.settings.Settings
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

private val MAPS = LaunchableApp("maps", "マップ")
private val SETTINGS = Settings(userName = "rider01", returnApp = MAPS)
private val ACCEPTED = AskAccepted("a1", "c1", "2999-01-01T00:00:00Z")
private const val BUSY = "say:$BUSY_MESSAGE"
private fun done(
  status: String = "completed",
  transcript: String? = "Q",
  answer: String? = "愛鷹山です。",
  audio: List<AudioClip> = listOf(AudioClip(1, "https://audio/1.mp3")),
  error: String? = null,
) = AskResult("a1", status, transcript, answer, audio, error)
private val PROCESSING = done(status = "processing")
private val HERE = Fix(35.6812, 139.7671, 100_000, 5.0)
private val BEHIND = Fix(35.6806, 139.7671, 90_000, 5.0)

/** A fake world around the controller that records what it was asked to do, in order. */
private class Harness(
  val scope: TestScope,
  var apiKey: String? = "key",
  val settings: Settings = SETTINGS,
  var post: suspend () -> AskAccepted = { ACCEPTED },
  answers: List<Any> = listOf(done()),
  val routeOk: Boolean = true,
  var play: suspend (List<String>) -> Unit = {},
  val stopAfterMs: Long? = 3_000,
  val micAllowed: Boolean = true,
  val sayGate: CompletableDeferred<Unit>? = null,
  val serviceError: Exception? = null,
  val device: InputDevice? = InputDevice(InputDevice.Type.BLUETOOTH, "M1-S PRO"),
) {
  val log = mutableListOf<String>()
  val states = mutableListOf<FlowState>()
  val bodies = mutableListOf<AskBody>()
  val metas = mutableListOf<RecordingMeta>()
  val transcripts = mutableListOf<Pair<String, String>>()
  private val results = answers.toMutableList()
  fun now() = scope.testScheduler.currentTime

  private val api = object : AskApi {
    override suspend fun postAsk(body: AskBody): AskAccepted {
      bodies += body
      log += "post"
      return post()
    }

    override suspend fun getAsk(askId: String): AskResult {
      log += "get"
      val r = if (results.isEmpty()) done() else results.removeAt(0)
      if (r is Exception) throw r
      return r as AskResult
    }
  }

  lateinit var controller: AskController
  val deps = AskDeps(
    now = ::now,
    sleep = { ms ->
      delay(ms)
      if (stopAfterMs != null && controller.state.phase == Phase.RECORDING && now() >= stopAfterMs) controller.stopRecording()
    },
    settings = { settings },
    apiKey = { apiKey },
    micAllowed = { micAllowed },
    mediaVolume = { log += "vol:read"; MediaVolume(2, 25) },
    api = { _, _ -> api },
    conversation = ConversationState(),
    route = object : RouteControl {
      override suspend fun start(source: Source): Boolean { log += "route:${source.name.lowercase()}"; return routeOk }
      override suspend fun stop() { log += "route:stop" }
      override fun inputDevice() = device
    },
    recorder = object : Recorder {
      override suspend fun start() { log += "rec:start" }
      override suspend fun stop(): Recorded { log += "rec:stop"; return Recorded(byteArrayOf(1, 2, 3), "rec-0.pcm") }
      override suspend fun cancel() { log += "rec:cancel" }
    },
    recordings = object : RecordingSink {
      override fun saved(meta: RecordingMeta) { metas += meta }
      override fun transcribed(name: String, transcript: String) { transcripts += name to transcript }
    },
    location = object : Positions {
      override fun begin() { log += "loc:begin" }
      override fun end() = HERE to listOf(BEHIND, HERE)
    },
    service = object : KeepAlive {
      override fun start() { log += "svc:start"; serviceError?.let { throw it } }
      override fun stop() { log += "svc:stop" }
    },
    nav = object : NavReturn {
      override suspend fun returnTo(packageName: String): Boolean { log += "return:$packageName"; return true }
    },
    cues = object : Cues {
      override fun start() { log += "cue:start" }
      override fun sent() { log += "cue:sent" }
      override fun waiting() { log += "cue:waiting" }
      override fun failure() { log += "cue:failure" }
    },
    player = object : AnswerPlayer {
      override suspend fun play(urls: List<String>) { log += "play:${urls.joinToString(",")}"; this@Harness.play(urls) }
      override fun stop() { log += "play:stop" }
    },
    speech = object : Speech {
      override suspend fun say(text: String) { log += "say:$text"; sayGate?.await() }
      override fun stop() { log += "say:stop" }
    },
    onState = { states += it },
    log = { _, _ -> },
  )

  init {
    controller = AskController(deps, scope)
  }

  val phase get() = controller.state.phase

  /** Advances virtual time in small steps until the condition holds. */
  fun until(condition: () -> Boolean) {
    var steps = 0
    while (!condition()) {
      scope.testScheduler.advanceTimeBy(1)
      scope.testScheduler.runCurrent()
      check(++steps < 1_000_000) { "condition never became true" }
    }
  }
}

class AskControllerTest {
  @Test
  fun handsfree_happy_path_returns_to_nav_right_after_sending() = runTest {
    val h = Harness(this)
    h.controller.run(Source.HANDSFREE)
    assertEquals(
      listOf(
        "vol:read", "svc:start", "loc:begin", "route:handsfree", "rec:start", "cue:start", "rec:stop", "route:stop",
        "post", "cue:sent", "return:maps", "get", "play:https://audio/1.mp3", "svc:stop",
      ),
      h.log,
    )
    assertEquals(
      AskBody(
        volumeDb = 6,
        audio = "AQID",
        location = Point(35.6812, 139.7671),
        headingSample = HeadingSample(35.6806, 139.7671, "1970-01-01T00:01:30Z"),
        conversationId = null,
      ),
      h.bodies[0],
    )
    assertEquals(Phase.IDLE, h.phase)
    assertEquals(listOf(Phase.RECORDING, Phase.SENDING, Phase.WAITING, Phase.SPEAKING, Phase.IDLE), h.states.map { it.phase })
  }

  @Test
  fun screen_questions_never_return_to_nav() = runTest {
    val h = Harness(this, stopAfterMs = 1_000)
    h.controller.run(Source.SCREEN)
    assertTrue("route:screen" in h.log)
    assertFalse(h.log.any { it.startsWith("return:") })
  }

  @Test
  fun return_after_the_answer_is_spoken_when_chosen() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, settings = SETTINGS.copy(returnTiming = ReturnTiming.SPOKEN))
    h.controller.run(Source.HANDSFREE)
    assertTrue(h.log.indexOf("return:maps") > h.log.indexOf("play:https://audio/1.mp3"))
  }

  @Test
  fun recording_stops_by_itself_at_the_limit() = runTest {
    val h = Harness(this, stopAfterMs = null)
    h.controller.run(Source.HANDSFREE)
    assertTrue("post" in h.log)
    assertTrue(h.now() >= RECORD_LIMIT_MS)
  }

  @Test
  fun conversation_id_is_reused_on_the_next_question() = runTest {
    val h = Harness(this, stopAfterMs = null)
    h.controller.run(Source.HANDSFREE)
    h.controller.run(Source.HANDSFREE)
    assertEquals("c1", h.bodies[1].conversationId)
    h.controller.resetConversation()
    h.controller.run(Source.HANDSFREE)
    assertEquals(null, h.bodies[2].conversationId)
  }

  @Test
  fun phone_mic_is_flagged_when_the_intercom_route_fails() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, routeOk = false)
    h.controller.run(Source.HANDSFREE)
    assertTrue(h.states.any { it.phase == Phase.RECORDING && it.phoneMic })
    assertTrue("post" in h.log)
  }

  @Test
  fun no_key_fails_with_a_spoken_message_and_no_recording() = runTest {
    val h = Harness(this, apiKey = null)
    h.controller.run(Source.HANDSFREE)
    assertEquals(listOf("vol:read", "cue:failure", "say:接続キーを確かめてください。", "return:maps"), h.log)
  }

  @Test
  fun network_failure_on_send() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, post = { throw ApiError(ApiErrorKind.NETWORK) })
    h.controller.run(Source.HANDSFREE)
    assertTrue("say:通信できないため、質問できませんでした。" in h.log)
    assertTrue("return:maps" in h.log)
    assertFalse("get" in h.log)
  }

  @Test
  fun server_failure_is_spoken() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, answers = listOf(done(status = "failed", error = "no_speech", answer = null, audio = emptyList())))
    h.controller.run(Source.HANDSFREE)
    assertTrue("say:聞き取れませんでした。もう一度お話しください。" in h.log)
  }

  @Test
  fun test_tts_failed_reads_answer_with_device_voice() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, answers = listOf(done(status = "failed", error = "tts_failed", audio = emptyList())))
    h.controller.run(Source.HANDSFREE)
    assertTrue("say:愛鷹山です。" in h.log)
    assertFalse("cue:failure" in h.log)
  }

  @Test
  fun test_player_error_falls_back_to_device_voice() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, play = { throw IllegalStateException("decode") })
    h.controller.run(Source.HANDSFREE)
    assertTrue("say:愛鷹山です。" in h.log)
  }

  @Test
  fun timeout_after_two_minutes_of_processing() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, answers = List(200) { PROCESSING })
    h.controller.run(Source.HANDSFREE)
    assertTrue("say:時間切れです。もう一度お話しください。" in h.log)
    assertTrue(h.log.count { it == "cue:waiting" } > 10)
  }

  @Test
  fun test_press_while_waiting_says_busy() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, answers = listOf(PROCESSING, done()))
    val running = launch { h.controller.run(Source.HANDSFREE) }
    h.until { h.phase == Phase.WAITING }
    h.controller.press()
    running.join()
    assertTrue(BUSY in h.log)
    assertEquals(1, h.log.count { it == "rec:start" })
  }

  @Test
  fun second_press_stops_the_recording() = runTest {
    val h = Harness(this, stopAfterMs = null)
    val running = launch { h.controller.run(Source.HANDSFREE) }
    h.until { "rec:start" in h.log }
    h.controller.press()
    running.join()
    assertTrue(h.now() < RECORD_LIMIT_MS)
  }

  @Test
  fun cancel_while_recording_discards_the_audio() = runTest {
    val h = Harness(this, stopAfterMs = null)
    val running = launch { h.controller.run(Source.SCREEN) }
    h.until { "rec:start" in h.log }
    h.controller.cancel()
    running.join()
    assertTrue("rec:cancel" in h.log)
    assertFalse("post" in h.log)
    assertEquals(Phase.IDLE, h.phase)
  }

  @Test
  fun cancel_while_waiting_stops_polling_quietly() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, answers = List(50) { PROCESSING })
    val running = launch { h.controller.run(Source.SCREEN) }
    h.until { h.phase == Phase.WAITING }
    h.controller.cancel()
    running.join()
    assertFalse("cue:failure" in h.log)
    assertEquals(Phase.IDLE, h.phase)
  }

  @Test
  fun test_new_run_during_failed_screen_is_not_reset() = runTest {
    var failPost = true
    val h = Harness(this, stopAfterMs = 1_000)
    h.post = { if (failPost) throw ApiError(ApiErrorKind.NETWORK) else ACCEPTED }
    val first = launch { h.controller.run(Source.SCREEN) }
    h.until { h.phase == Phase.FAILED }
    failPost = false
    val secondStart = h.log.size
    val second = launch { h.controller.run(Source.SCREEN) }
    first.join()
    second.join()
    val after = h.log.drop(secondStart)
    val played = after.indexOf("play:https://audio/1.mp3")
    assertTrue(played >= 0)
    // The first run's cleanup must not stop the service the second run is using.
    assertFalse("svc:stop" in after.take(played))
    assertEquals(Phase.IDLE, h.phase)
  }

  @Test
  fun cancel_clears_the_screen_and_stops_the_service_at_once() = runTest {
    val never = CompletableDeferred<AskAccepted>()
    val h = Harness(this, stopAfterMs = 1_000, post = { never.await() })
    val running = launch { h.controller.run(Source.SCREEN) }
    h.until { h.phase == Phase.SENDING && "post" in h.log }
    h.controller.cancel()
    assertEquals(Phase.IDLE, h.phase)
    assertTrue("svc:stop" in h.log)
    running.cancel()
  }

  @Test
  fun an_ask_cancelled_while_sending_plays_no_cue_and_does_not_return() = runTest {
    val accept = CompletableDeferred<AskAccepted>()
    val h = Harness(this, stopAfterMs = 1_000, post = { accept.await() })
    val running = launch { h.controller.run(Source.HANDSFREE) }
    h.until { "post" in h.log }
    h.controller.cancel()
    accept.complete(ACCEPTED)
    running.join()
    assertFalse("cue:sent" in h.log)
    assertFalse(h.log.any { it.startsWith("return:") })
    assertFalse("get" in h.log)
  }

  @Test
  fun a_busy_press_goes_back_to_the_nav_app_after_the_message() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, answers = listOf(PROCESSING, done()))
    val running = launch { h.controller.run(Source.HANDSFREE) }
    h.until { h.phase == Phase.WAITING }
    h.controller.press()
    running.join()
    testScheduler.advanceUntilIdle()
    assertEquals(2, h.log.count { it == "return:maps" })
    assertTrue(h.log.lastIndexOf("return:maps") > h.log.indexOf(BUSY))
  }

  @Test
  fun a_denied_microphone_fails_without_starting_the_service() = runTest {
    val h = Harness(this, micAllowed = false)
    h.controller.run(Source.HANDSFREE)
    assertTrue("say:録音できませんでした。" in h.log)
    assertFalse("svc:start" in h.log)
  }

  @Test
  fun an_old_failure_does_not_act_on_the_next_ask() = runTest {
    val gate = CompletableDeferred<Unit>()
    var failPost = true
    val h = Harness(this, stopAfterMs = 1_000, sayGate = gate)
    h.post = { if (failPost) throw ApiError(ApiErrorKind.NETWORK) else ACCEPTED }
    val first = launch { h.controller.run(Source.SCREEN) }
    h.until { h.phase == Phase.FAILED }
    failPost = false
    h.controller.press()
    h.until { h.phase == Phase.RECORDING }
    gate.complete(Unit)
    first.join()
    h.until { h.phase == Phase.IDLE }
    val returns = h.log.withIndex().filter { it.value == "return:maps" }
    assertEquals(1, returns.size)
    assertTrue(returns[0].index > h.log.lastIndexOf("post"))
  }

  @Test
  fun the_chosen_answer_volume_goes_with_every_question() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, settings = SETTINGS.copy(answerVolumeDb = 3))
    h.controller.run(Source.HANDSFREE)
    assertEquals(3, h.bodies[0].volumeDb)
  }

  @Test
  fun a_foreground_service_that_cannot_start_fails_out_loud() = runTest {
    val h = Harness(this, serviceError = IllegalStateException("ForegroundServiceStartNotAllowedException"))
    h.controller.run(Source.HANDSFREE)
    assertEquals(
      listOf("vol:read", "svc:start", "cue:failure", "say:準備できなかったため、質問できませんでした。もう一度お試しください。", "return:maps"),
      h.log,
    )
    assertTrue(h.states.any { it.phase == Phase.FAILED && it.failure == FailureReason.SERVICE })
    assertEquals(Phase.IDLE, h.phase)
  }

  @Test
  fun the_kept_recording_is_described_for_sc12() = runTest {
    val h = Harness(this)
    h.controller.run(Source.HANDSFREE)
    // 3 bytes of PCM is shorter than a millisecond.
    assertEquals(listOf(RecordingMeta("rec-0.pcm", 0, 0, false, InputDevice(InputDevice.Type.BLUETOOTH, "M1-S PRO"), null)), h.metas)
    assertEquals(listOf("rec-0.pcm" to "Q"), h.transcripts)
  }

  @Test
  fun a_phone_mic_recording_is_marked_so() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, routeOk = false, device = InputDevice(InputDevice.Type.BUILTIN, "Pixel"))
    h.controller.run(Source.HANDSFREE)
    assertTrue(h.metas[0].phoneMic)
    assertEquals(InputDevice(InputDevice.Type.BUILTIN, "Pixel"), h.metas[0].device)
  }

  @Test
  fun what_was_heard_is_kept_even_when_the_answer_fails() = runTest {
    val h = Harness(this, stopAfterMs = 1_000, answers = listOf(done(status = "failed", transcript = "", answer = null, audio = emptyList(), error = "no_speech")))
    h.controller.run(Source.HANDSFREE)
    assertEquals(listOf("rec-0.pcm" to ""), h.transcripts)
  }

  @Test
  fun the_answer_waits_until_the_busy_message_has_been_said() = runTest {
    val gate = CompletableDeferred<Unit>()
    val h = Harness(this, stopAfterMs = 1_000, sayGate = gate, answers = listOf(PROCESSING, done()))
    val running = launch { h.controller.run(Source.HANDSFREE) }
    h.until { h.phase == Phase.WAITING }
    h.controller.press()
    // The answer arrives while "いま応答中です…" is still being said.
    h.until { h.phase == Phase.SPEAKING }
    testScheduler.advanceTimeBy(5_000)
    testScheduler.runCurrent()
    assertFalse(h.log.any { it.startsWith("play:") })
    gate.complete(Unit)
    running.join()
    val busy = h.log.indexOf(BUSY)
    assertTrue(busy >= 0)
    assertTrue(h.log.indexOf("play:https://audio/1.mp3") > busy)
  }

  @Test
  fun a_press_while_the_answer_is_read_out_says_nothing_over_it() = runTest {
    val endPlay = CompletableDeferred<Unit>()
    val h = Harness(this, stopAfterMs = 1_000, play = { endPlay.await() })
    val running = launch { h.controller.run(Source.HANDSFREE) }
    h.until { h.phase == Phase.SPEAKING && h.log.any { it.startsWith("play:") } }
    h.controller.press()
    testScheduler.runCurrent()
    endPlay.complete(Unit)
    running.join()
    assertFalse(h.log.any { it.startsWith("say:") })
    assertEquals(1, h.log.count { it == "rec:start" })
  }

  @Test
  fun the_media_volume_is_read_before_the_intercom_route_takes_over() = runTest {
    // While SCO is up, the music stream reports the call device's volume instead.
    val h = Harness(this, stopAfterMs = 1_000)
    h.controller.run(Source.HANDSFREE)
    assertTrue(h.log.indexOf("vol:read") in 0 until h.log.indexOf("route:handsfree"))
    assertEquals(Phase.RECORDING, h.states[0].phase)
    assertEquals(MediaVolume(2, 25), h.states[0].mediaVolume)
  }

  @Test
  fun each_run_is_counted_once() = runTest {
    val h = Harness(this, apiKey = null)
    h.controller.press()
    testScheduler.advanceUntilIdle()
    assertEquals(1, h.controller.runsStarted)
  }
}
```

`app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt`:

```kotlin
package com.touringproject.v2.location

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PositionTrackerTest {
  private class FakeSource(var now: Long = 100_000) : PositionSource {
    var last: Fix? = null
    var onFix: ((Fix) -> Unit)? = null
    var lateLastKnown: ((Fix) -> Unit)? = null
    var removed = 0
    var deferLastKnown = false

    override fun now() = now
    override fun lastKnown(onFix: (Fix) -> Unit) {
      if (deferLastKnown) lateLastKnown = onFix else last?.let(onFix)
    }
    override fun watch(onFix: (Fix) -> Unit): Subscription {
      this.onFix = onFix
      return Subscription { removed++ }
    }
  }

  private fun fix(t: Long) = Fix(35.0, 139.0, t, 5.0)

  @Test
  fun end_removes_the_watch() {
    val source = FakeSource()
    val tracker = PositionTracker(source)
    tracker.begin()
    tracker.end()
    assertEquals(1, source.removed)
  }

  @Test
  fun fixes_from_an_earlier_begin_are_not_mixed_in() {
    val source = FakeSource()
    val tracker = PositionTracker(source)
    tracker.begin()
    val oldCallback = source.onFix!!
    tracker.begin()
    oldCallback(fix(99_000))
    source.onFix!!(fix(99_500))
    assertEquals(listOf(fix(99_500)), tracker.end().second)
  }

  @Test
  fun a_last_known_point_that_arrives_after_end_is_ignored() {
    val source = FakeSource().apply { deferLastKnown = true }
    val tracker = PositionTracker(source)
    tracker.begin()
    tracker.end()
    source.lateLastKnown!!(fix(99_000))
    tracker.begin()
    assertEquals(emptyList<Fix>(), tracker.end().second)
  }

  @Test
  fun a_stale_last_known_point_is_not_the_current_position() {
    val source = FakeSource().apply { last = fix(100_000 - MAX_CURRENT_AGE_MS - 1) }
    val tracker = PositionTracker(source)
    tracker.begin()
    val (current, fixes) = tracker.end()
    assertNull(current)
    assertEquals(1, fixes.size)
  }

  @Test
  fun the_newest_fresh_fix_is_the_current_position() {
    val source = FakeSource().apply { last = fix(90_000) }
    val tracker = PositionTracker(source)
    tracker.begin()
    source.onFix!!(fix(99_000))
    source.onFix!!(fix(98_000))
    val (current, fixes) = tracker.end()
    assertEquals(fix(99_000), current)
    assertEquals(listOf(fix(90_000), fix(98_000), fix(99_000)), fixes)
  }
}
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AskControllerTest' --tests '*PositionTrackerTest'`
Expected: コンパイルエラー（`AskController`・`AskDeps`・`PositionTracker` が無い）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/ask/AskPorts.kt`:

```kotlin
package com.touringproject.v2.ask

import com.touringproject.v2.api.AskApi
import com.touringproject.v2.audio.InputDevice
import com.touringproject.v2.audio.MediaVolume
import com.touringproject.v2.location.Fix
import com.touringproject.v2.settings.Settings

// Everything the ask loop does to the outside world comes in through these interfaces, so the loop is testable on the JVM.

interface RouteControl {
  /** Brings up the intercom microphone; false means the phone's own microphone will be used. */
  suspend fun start(source: Source): Boolean
  suspend fun stop()
  /** The microphone of the recording that is running right now (only visible while it runs). */
  fun inputDevice(): InputDevice?
}

data class Recorded(val pcm: ByteArray, val name: String)

interface Recorder {
  suspend fun start()
  suspend fun stop(): Recorded
  suspend fun cancel()
}

/** What SC-12 shows about each kept recording (kept from plan 2 of the migration). */
data class RecordingMeta(
  val name: String,
  val recordedAt: Long,
  val durationMs: Long,
  val phoneMic: Boolean,
  val device: InputDevice?,
  val transcript: String?,
)

/** Fire and forget: a failure here must not end the ask. */
interface RecordingSink {
  fun saved(meta: RecordingMeta)
  fun transcribed(name: String, transcript: String)
}

interface Positions {
  fun begin()
  fun end(): Pair<Fix?, List<Fix>>
}

interface KeepAlive {
  /** Throws when the foreground service cannot be started. */
  fun start()
  fun stop()
}

interface NavReturn {
  suspend fun returnTo(packageName: String): Boolean
}

interface Cues {
  fun start()
  fun sent()
  fun waiting()
  fun failure()
}

interface AnswerPlayer {
  /** Plays the clips in order; throws when a clip fails or stalls. */
  suspend fun play(urls: List<String>)
  fun stop()
}

interface Speech {
  /** Returns when the text has been said, stopped, or failed. */
  suspend fun say(text: String)
  fun stop()
}

class AskDeps(
  val now: () -> Long,
  val sleep: suspend (Long) -> Unit,
  val settings: () -> Settings,
  val apiKey: () -> String?,
  val micAllowed: () -> Boolean,
  val mediaVolume: () -> MediaVolume?,
  val api: (apiKey: String, userName: String) -> AskApi,
  val conversation: ConversationState,
  val route: RouteControl,
  val recorder: Recorder,
  val recordings: RecordingSink,
  val location: Positions,
  val service: KeepAlive,
  val nav: NavReturn,
  val cues: Cues,
  val player: AnswerPlayer,
  val speech: Speech,
  val onState: (FlowState) -> Unit,
  val log: (event: String, data: Map<String, Any?>) -> Unit,
)
```

`app/src/main/java/com/touringproject/v2/ask/AskController.kt`:

```kotlin
package com.touringproject.v2.ask

import com.touringproject.v2.api.ApiError
import com.touringproject.v2.api.ApiErrorKind
import com.touringproject.v2.api.AskAccepted
import com.touringproject.v2.api.AskApi
import com.touringproject.v2.api.AskBody
import com.touringproject.v2.api.AskResult
import com.touringproject.v2.api.Point
import com.touringproject.v2.location.Fix
import com.touringproject.v2.location.pickHeadingSample
import com.touringproject.v2.settings.ReturnTiming
import com.touringproject.v2.settings.Settings
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.async
import kotlinx.coroutines.launch
import java.util.Base64

const val RECORD_LIMIT_MS = 20_000L
const val TICK_MS = 250L
const val WAITING_CUE_MS = 5_000L
const val FAILED_SCREEN_MS = 5_000L

/** 16 kHz mono 16-bit PCM: 32 bytes per millisecond. */
fun pcmDurationMs(bytes: Int): Long = bytes / 32L

private fun reasonFor(error: Throwable): FailureReason = when ((error as? ApiError)?.kind) {
  ApiErrorKind.INVALID_KEY -> FailureReason.INVALID_KEY
  ApiErrorKind.BAD_REQUEST -> FailureReason.NO_SPEECH
  else -> FailureReason.NETWORK
}

/**
 * Orchestrates one ask: record -> send -> (return to nav) -> wait -> speak. Call it from one thread only (the main
 * thread in the app): the state is not guarded. A cancel or a newer ask does not interrupt the older one's awaits;
 * the older one notices it is no longer current when they return and does nothing more.
 */
class AskController(private val deps: AskDeps, private val scope: CoroutineScope) {
  var state: FlowState = IDLE
    private set

  /** How many asks were started; read by tests to check that one press starts exactly one ask. */
  var runsStarted = 0
    private set

  private var runId = 0
  private var current: Run? = null
  private var serviceRunning = false
  // "いま応答中です…" being said; the answer waits for it so the two never overlap.
  private var busySpeech: Deferred<Unit>? = null

  // Per-ask state: an older ask that is still unwinding must not read or change the newer one's.
  private class Run(val id: Int, val source: Source, var returned: Boolean = false)

  private class Recording(val audio: String, val name: String, val current: Fix?, val fixes: List<Fix>)

  /** The intercom button: start, stop the recording, or say that an answer is on its way. */
  fun press() {
    when {
      state.phase == Phase.RECORDING -> stopRecording()
      // The answer is already being heard; a spoken notice would only talk over it.
      state.phase == Phase.SPEAKING -> Unit
      isBusy(state) -> sayBusy()
      else -> scope.launch { run(Source.HANDSFREE) }
    }
  }

  fun tapToTalk() {
    if (!isBusy(state)) scope.launch { run(Source.SCREEN) }
  }

  fun stopRecording() {
    if (state.phase == Phase.RECORDING) dispatch(FlowEvent.StopRecording(deps.now()))
  }

  /** The big button: end the current ask now; whatever it is awaiting is ignored when it returns. */
  fun cancel() {
    if (state.phase == Phase.IDLE) return
    runId += 1
    current = null
    deps.player.stop()
    deps.speech.stop()
    dispatch(FlowEvent.Dismiss(deps.now()))
    stopService()
  }

  fun resetConversation() = deps.conversation.reset()

  suspend fun run(source: Source) {
    val d = deps
    // A previous ask may still be reading its failure message; the new ask takes over the audio.
    if (state.phase == Phase.FAILED) d.speech.stop()
    val run = Run(++runId, source)
    current = run
    runsStarted += 1
    dispatch(FlowEvent.Start(source, d.now(), d.mediaVolume()))
    try {
      val apiKey = d.apiKey()
      if (apiKey == null) {
        fail(FailureReason.NO_KEY, run)
        return
      }
      if (!d.micAllowed()) {
        fail(FailureReason.MIC, run)
        return
      }
      if (!isCurrent(run)) return
      val settings = d.settings()
      val api = d.api(apiKey, settings.userName)
      try {
        d.service.start()
      } catch (e: Exception) {
        // Without the foreground service the ask would stall once the screen is off; say so instead.
        d.log("service_failed", mapOf("error" to e.toString()))
        fail(FailureReason.SERVICE, run)
        return
      }
      serviceRunning = true
      val recording = record(run) ?: return
      val accepted = send(recording, api, run) ?: return
      maybeReturn(ReturnTiming.SENT, settings, run)
      val result = waitForAnswer(accepted.askId, recording.name, api, run) ?: return
      speak(result, settings, run)
    } finally {
      // A newer ask (or a cancel) owns the screen state and the foreground service; leave both to it.
      if (isCurrent(run)) {
        current = null
        dispatch(FlowEvent.Dismiss(d.now()))
        stopService()
      }
    }
  }

  private fun stopService() {
    if (!serviceRunning) return
    serviceRunning = false
    deps.service.stop()
  }

  private fun dispatch(event: FlowEvent) {
    val next = reduce(state, event)
    if (next == state) return
    state = next
    deps.onState(next)
  }

  private fun isCurrent(run: Run) = run.id == runId

  // The press itself brought this app over the nav app, so go back once the rider has heard the message.
  private fun sayBusy() {
    val d = deps
    val run = current
    val said = scope.async { d.speech.say(BUSY_MESSAGE) }
    busySpeech = said
    scope.launch {
      said.await()
      if (busySpeech === said) busySpeech = null
      if (run == null || !isCurrent(run) || run.source != Source.HANDSFREE || !run.returned) return@launch
      val settings = d.settings()
      val app = settings.returnApp
      if (settings.returnEnabled && app != null) d.nav.returnTo(app.packageName)
    }
  }

  private suspend fun record(run: Run): Recording? {
    val d = deps
    d.location.begin()
    val routed = d.route.start(run.source)
    if (!routed) dispatch(FlowEvent.PhoneMic(d.now()))
    try {
      d.recorder.start()
    } catch (e: Exception) {
      d.route.stop()
      d.location.end()
      fail(FailureReason.MIC, run)
      return null
    }
    // After the recorder is running: the rider starts talking on this cue, so nothing said after it is lost.
    d.cues.start()
    val startedAt = d.now()
    while (state.phase == Phase.RECORDING && isCurrent(run) && d.now() - startedAt < RECORD_LIMIT_MS) {
      d.sleep(TICK_MS)
    }
    if (!isCurrent(run)) {
      d.recorder.cancel()
      d.route.stop()
      d.location.end()
      return null
    }
    // Read while the recorder still runs: the system only reports the input device of an active recording.
    val device = d.route.inputDevice()
    val phoneMic = state.phoneMic
    stopRecording()
    val stopped = try {
      d.recorder.stop()
    } catch (e: Exception) {
      d.route.stop()
      d.location.end()
      fail(FailureReason.MIC, run)
      return null
    }
    d.route.stop()
    d.recordings.saved(RecordingMeta(stopped.name, startedAt, pcmDurationMs(stopped.pcm.size), phoneMic, device, null))
    val (currentFix, fixes) = d.location.end()
    return Recording(Base64.getEncoder().encodeToString(stopped.pcm), stopped.name, currentFix, fixes)
  }

  private suspend fun send(recording: Recording, api: AskApi, run: Run): AskAccepted? {
    val d = deps
    val here = recording.current
    val body = AskBody(
      volumeDb = d.settings().answerVolumeDb,
      audio = recording.audio,
      location = here?.let { Point(it.latitude, it.longitude) },
      headingSample = here?.let { pickHeadingSample(recording.fixes, it) },
      conversationId = d.conversation.current(d.now()),
    )
    val accepted = try {
      api.postAsk(body)
    } catch (e: Exception) {
      d.log("post_failed", mapOf("kind" to ((e as? ApiError)?.kind?.name ?: "unknown")))
      fail(reasonFor(e), run)
      return null
    }
    // The ask exists on the Backend either way, so keep the conversation going even if it was cancelled.
    d.conversation.update(accepted.conversationId, accepted.conversationExpiresAt)
    if (!isCurrent(run)) return null
    dispatch(FlowEvent.Sent(accepted.askId, d.now()))
    d.cues.sent()
    return accepted
  }

  private suspend fun waitForAnswer(askId: String, recordingName: String, api: AskApi, run: Run): AskResult? {
    val d = deps
    var sinceCue = 0L
    val sleep: suspend (Long) -> Unit = { ms ->
      d.sleep(ms)
      sinceCue += ms
      if (sinceCue >= WAITING_CUE_MS && isCurrent(run)) {
        sinceCue = 0
        d.cues.waiting()
      }
    }
    val outcome = try {
      pollUntilDone({ api.getAsk(askId) }, sleep, d.now) { !isCurrent(run) }
    } catch (e: Exception) {
      fail(reasonFor(e), run)
      return null
    }
    if (outcome is PollOutcome.Done) outcome.result.transcript?.let { d.recordings.transcribed(recordingName, it) }
    if (outcome is PollOutcome.Cancelled || !isCurrent(run)) return null
    if (outcome is PollOutcome.Timeout) {
      fail(FailureReason.TIMEOUT, run)
      return null
    }
    val result = (outcome as PollOutcome.Done).result
    val readable = result.status == "completed" || (result.error == "tts_failed" && !result.answer.isNullOrEmpty())
    if (!readable) {
      fail(failureFromServer(result.error), run)
      return null
    }
    return result
  }

  private suspend fun speak(result: AskResult, settings: Settings, run: Run) {
    val d = deps
    dispatch(FlowEvent.Answered(result.answer ?: "", d.now()))
    maybeReturn(ReturnTiming.ANSWERED, settings, run)
    val urls = result.audio.sortedBy { it.seq }.map { it.url }
    busySpeech?.await()
    var played = false
    if (urls.isNotEmpty() && isCurrent(run)) {
      try {
        d.player.play(urls)
        played = true
      } catch (e: Exception) {
        d.log("play_failed", mapOf("error" to e.toString()))
      }
    }
    if (!played && isCurrent(run) && !result.answer.isNullOrEmpty()) d.speech.say(result.answer)
    maybeReturn(ReturnTiming.SPOKEN, settings, run)
  }

  private suspend fun maybeReturn(moment: ReturnTiming, settings: Settings, run: Run) {
    if (run.returned || !isCurrent(run) || !shouldReturnNow(run.source, settings, moment)) return
    run.returned = true
    deps.nav.returnTo(settings.returnApp!!.packageName)
  }

  private suspend fun fail(reason: FailureReason, run: Run) {
    val d = deps
    if (!isCurrent(run)) return
    dispatch(FlowEvent.Fail(reason, d.now()))
    d.cues.failure()
    d.speech.say(spokenMessage(reason))
    if (!isCurrent(run)) return
    val settings = d.settings()
    if (run.source == Source.HANDSFREE) {
      // US-B-04.006: a failed answer still ends with the nav app in front.
      val app = settings.returnApp
      if (!run.returned && settings.returnEnabled && app != null) {
        run.returned = true
        d.nav.returnTo(app.packageName)
      }
      return
    }
    var waited = 0L
    while (waited < FAILED_SCREEN_MS && isCurrent(run) && state.phase == Phase.FAILED) {
      d.sleep(TICK_MS)
      waited += TICK_MS
    }
  }
}
```

`app/src/main/java/com/touringproject/v2/location/PositionTracker.kt`:

```kotlin
package com.touringproject.v2.location

import com.touringproject.v2.ask.Positions

// Collects position fixes while a question is recorded. A last-known point older than MAX_CURRENT_AGE_MS is not
// sent as the current position, and callbacks that belong to an earlier begin() are ignored.
const val MAX_CURRENT_AGE_MS = 30_000L

fun interface Subscription {
  fun remove()
}

interface PositionSource {
  fun now(): Long
  fun lastKnown(onFix: (Fix) -> Unit)
  fun watch(onFix: (Fix) -> Unit): Subscription
}

class PositionTracker(private val source: PositionSource) : Positions {
  private val fixes = mutableListOf<Fix>()
  private var subscription: Subscription? = null
  // Bumped by begin() and end(); callbacks of an earlier generation are ignored.
  private var generation = 0

  @Synchronized
  override fun begin() {
    subscription?.remove()
    subscription = null
    fixes.clear()
    val gen = ++generation
    val add: (Fix) -> Unit = { fix -> synchronized(this) { if (gen == generation) fixes.add(fix) } }
    runCatching { source.lastKnown(add) }
    subscription = runCatching { source.watch(add) }.getOrNull()
  }

  @Synchronized
  override fun end(): Pair<Fix?, List<Fix>> {
    generation += 1
    subscription?.remove()
    subscription = null
    val sorted = fixes.sortedBy { it.timestamp }
    fixes.clear()
    val latest = sorted.lastOrNull()
    val current = latest?.takeIf { source.now() - it.timestamp <= MAX_CURRENT_AGE_MS }
    return current to sorted
  }
}
```

- [ ] **Step 4: テストを通す**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AskControllerTest' --tests '*PositionTrackerTest'`
Expected: PASS（`AskControllerTest` 31件・`PositionTrackerTest` 5件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ask/AskPorts.kt app/src/main/java/com/touringproject/v2/ask/AskController.kt \
  app/src/main/java/com/touringproject/v2/location/PositionTracker.kt \
  app/src/test/java/com/touringproject/v2/ask/AskControllerTest.kt app/src/test/java/com/touringproject/v2/location/PositionTrackerTest.kt
git commit -m "feat: orchestrate the hands-free ask loop"
```

---

### Task 7: 音声の部品（経路・録音・再生・端末の音声・合図）

**Files:**
- Create: `app/src/main/java/.../audio/AudioRoute.kt`、`AudioRouteControl.kt`、`PcmRecorder.kt`、`ExoAnswerPlayer.kt`、`TtsSpeech.kt`、`ToneCues.kt`
- Test: `app/src/test/java/.../audio/AudioTest.kt`

**Interfaces:**
- Consumes: `RouteControl`・`Recorder`・`AnswerPlayer`・`Speech`・`Cues`（Task 6）、`MediaVolume`・`InputDevice`・`RouteResult`（Task 4）
- Produces:
  - `AudioRoute(context)`: `suspend startVoiceRecognition(timeoutMs)`・`suspend stopVoiceRecognition(reason)`・`suspend acquireSco(timeoutMs)`・`suspend releaseSco()`・`mediaVolume(): MediaVolume?`・`activeInputDevice()`・`onVoiceRecognitionEnded: (() -> Unit)?`
  - `AudioRouteControl(route): RouteControl`、`PcmRecorder(): Recorder`、`ExoAnswerPlayer(context): AnswerPlayer`、`StallWatch`、`TtsSpeech(context): Speech`、`ToneCues(): Cues`、`enum Cue`

`AudioRoute.kt` は React Native 版の `App/modules/audio-route/.../AudioRouteModule.kt` から、Expo Modules の定義（`ModuleDefinition`・`Promise`・`sendEvent`）を外して移したもの。Bluetooth と AudioManager の判断の中身は変えない。

実際の音・インカムの経路は JVM では確かめられない（Task 12 の実機の確認で見る）。ここでテストするのは、止まった音声を諦める判断・合図の音の選び方・メディアの音量の読み方だけ。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/audio/AudioTest.kt`:

```kotlin
package com.touringproject.v2.audio

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

class StallWatchTest {
  @Test
  fun a_clip_that_never_progresses_is_given_up() {
    val watch = StallWatch(stallMs = 3_000)
    assertFalse(watch.tick(0, 1_000)) // first reading
    assertFalse(watch.tick(0, 1_000))
    assertFalse(watch.tick(0, 1_000))
    assertTrue(watch.tick(0, 1_000))
  }

  @Test
  fun progress_keeps_the_watchdog_quiet() {
    val watch = StallWatch(stallMs = 3_000)
    (0L..20L).forEach { assertFalse(watch.tick(it * 1_000, 1_000)) }
  }
}

class CueTest {
  @Test
  fun the_start_cue_is_long_and_heard_on_the_call_stream() {
    assertEquals(AudioManager.STREAM_VOICE_CALL, Cue.START.stream)
    assertTrue(Cue.START.durationMs >= 1_500)
    // TONE_PROP_* tones stop after about 0.16 s whatever duration is asked for.
    val propTones = setOf(ToneGenerator.TONE_PROP_ACK, ToneGenerator.TONE_PROP_BEEP, ToneGenerator.TONE_PROP_NACK, ToneGenerator.TONE_PROP_PROMPT)
    assertTrue(Cue.entries.none { it.tone in propTones })
    assertTrue(Cue.entries.filter { it != Cue.START }.all { it.stream == AudioManager.STREAM_MUSIC })
  }
}

@RunWith(AndroidJUnit4::class)
class AudioRouteTest {
  private val context = ApplicationProvider.getApplicationContext<Context>()
  private val audioManager = context.getSystemService(AudioManager::class.java)

  @Test
  fun media_volume_is_read_from_the_music_stream() {
    audioManager.mode = AudioManager.MODE_NORMAL
    audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, 4, 0)
    val volume = AudioRoute(context).mediaVolume()!!
    assertEquals(4, volume.current)
    assertEquals(audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC), volume.max)
  }

  @Test
  fun media_volume_is_withheld_while_the_call_route_is_up() {
    audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
    assertNull(AudioRoute(context).mediaVolume())
    audioManager.mode = AudioManager.MODE_NORMAL
  }
}
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*audio*'`
Expected: コンパイルエラー（`StallWatch`・`Cue`・`AudioRoute` が無い）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/audio/AudioRoute.kt`:

```kotlin
package com.touringproject.v2.audio

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothHeadset
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume

// Routes the intercom microphone (Bluetooth SCO).
//
// Intercom button: the headset sends "start voice recognition" (AT+BVRA) and waits about 5 s for the phone.
// We answer with BluetoothHeadset.startVoiceRecognition(), which makes the Bluetooth stack bring up SCO itself.
// setCommunicationDevice() must NOT be called then: AudioService would remember the external SCO and re-open it
// as a virtual call after the headset drops it. The second press reaches us only as SCO going down, so a remote
// SCO loss during a session is reported as onVoiceRecognitionEnded. Another HFP device dropping is ignored.
//
// Screen button: there is no request from the headset, so SCO is opened as a virtual call by naming the SCO
// *output* (sink) in setCommunicationDevice(); the return value is checked because a false is otherwise silent.
//
// All Bluetooth and AudioManager work runs on the main thread.
@SuppressLint("MissingPermission") // BLUETOOTH_CONNECT is requested at runtime by the app
class AudioRoute(private val context: Context) {
  private val audioManager = context.getSystemService(AudioManager::class.java)
  private val main = Handler(Looper.getMainLooper())

  /** Called on the main thread when the intercom drops SCO during a voice-recognition session (the second press). */
  @Volatile var onVoiceRecognitionEnded: (() -> Unit)? = null

  private var headset: BluetoothHeadset? = null
  private var proxyRequested = false
  private val proxyWaiters = mutableListOf<(BluetoothHeadset?) -> Unit>()
  private var receiver: BroadcastReceiver? = null

  // Voice-recognition session; the counter invalidates callbacks of earlier sessions.
  private var vrDevice: BluetoothDevice? = null
  private var vrSession = 0
  private var vrPending: ((Boolean, String) -> Unit)? = null

  suspend fun startVoiceRecognition(timeoutMs: Long): RouteResult = onMain { done -> startVoiceRecognition(timeoutMs, done) }

  suspend fun stopVoiceRecognition(reason: String) = withContext(Dispatchers.Main) {
    vrPending?.invoke(false, "stopped: $reason")
    headset?.let { endSession(it, reason) }
    audioManager.mode = AudioManager.MODE_NORMAL
  }

  suspend fun acquireSco(timeoutMs: Long): RouteResult = onMain { done -> acquireSco(timeoutMs, done) }

  suspend fun releaseSco() = withContext(Dispatchers.Main) {
    runCatching { audioManager.clearCommunicationDevice() }
    audioManager.mode = AudioManager.MODE_NORMAL
  }

  // Answers and cues play on the media stream; the intercom follows the phone's media volume. While media still
  // routes to the intercom's call link (SCO, which lingers after an ask), STREAM_MUSIC reports that link's volume
  // instead, so the reading is withheld (null).
  fun mediaVolume(): MediaVolume? {
    if (mediaOnCallRoute()) return null
    return MediaVolume(audioManager.getStreamVolume(AudioManager.STREAM_MUSIC), audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC))
  }

  /** The microphone this app is recording from right now (only our own recordings are visible to us). */
  fun activeInputDevice(): InputDevice? {
    val device = audioManager.activeRecordingConfigurations.firstNotNullOfOrNull { it.audioDevice } ?: return null
    val type = when (device.type) {
      AudioDeviceInfo.TYPE_BLUETOOTH_SCO -> InputDevice.Type.BLUETOOTH
      AudioDeviceInfo.TYPE_BUILTIN_MIC -> InputDevice.Type.BUILTIN
      else -> InputDevice.Type.OTHER
    }
    return InputDevice(type, device.productName.toString())
  }

  private suspend fun onMain(block: (done: (Boolean, String) -> Unit) -> Unit): RouteResult = withContext(Dispatchers.Main) {
    suspendCancellableCoroutine { cont ->
      var resumed = false
      block { ok, note ->
        if (!resumed) {
          resumed = true
          cont.resume(RouteResult(ok, note))
        }
      }
    }
  }

  private fun mediaOnCallRoute(): Boolean {
    val am = audioManager
    if (am.mode == AudioManager.MODE_IN_COMMUNICATION || am.mode == AudioManager.MODE_IN_CALL) return true
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return false
    val media = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).build()
    return am.getAudioDevicesForAttributes(media).any { it.type == SCO_TYPE }
  }

  // ---------------- intercom button: voice recognition ----------------

  private fun startVoiceRecognition(timeoutMs: Long, done: (Boolean, String) -> Unit) {
    if (vrPending != null) {
      done(false, "already starting")
      return
    }
    ensureReceiver()
    withHeadset { h ->
      if (h == null) {
        done(false, "no headset proxy")
        return@withHeadset
      }
      val device = pickDevice(h)
      if (device == null) {
        done(false, "no HFP device connected")
        return@withHeadset
      }
      if (vrDevice != null) endSession(h, "superseded")
      waitAudioOff(h, device) { begin(h, device, timeoutMs, done) }
    }
  }

  private fun begin(h: BluetoothHeadset, device: BluetoothDevice, timeoutMs: Long, done: (Boolean, String) -> Unit) {
    val session = ++vrSession
    vrDevice = device
    val onTimeout = Runnable { if (vrSession == session) vrPending?.invoke(false, "SCO timeout") }
    // Wait for SCO by broadcast and by polling, whichever comes first.
    val poll = object : Runnable {
      override fun run() {
        if (vrSession != session || vrPending == null) return
        val d = vrDevice ?: return
        if (runCatching { h.isAudioConnected(d) }.getOrDefault(false)) vrPending?.invoke(true, "connected (poll)")
        else main.postDelayed(this, POLL_MS)
      }
    }
    vrPending = { ok, note ->
      vrPending = null
      main.removeCallbacks(onTimeout)
      main.removeCallbacks(poll)
      if (ok && vrSession == session) {
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        startSessionMonitor(h, session)
      } else if (vrSession == session) {
        endSession(h, "start failed: $note")
      }
      done(ok && vrSession == session, note)
    }
    main.postDelayed(onTimeout, timeoutMs)
    val accepted = runCatching { h.startVoiceRecognition(device) }
    if (accepted.getOrDefault(false) != true) {
      vrPending?.invoke(false, "startVoiceRecognition returned ${accepted.exceptionOrNull()?.javaClass?.simpleName ?: "false"}")
      return
    }
    main.post(poll)
  }

  private fun startSessionMonitor(h: BluetoothHeadset, session: Int) {
    val monitor = object : Runnable {
      override fun run() {
        if (vrSession != session) return
        val d = vrDevice ?: return
        if (!runCatching { h.isAudioConnected(d) }.getOrDefault(false)) onScoLost(session)
        else main.postDelayed(this, POLL_MS)
      }
    }
    main.postDelayed(monitor, POLL_MS)
  }

  // SCO went down during a session we did not end ourselves: the intercom's second press.
  private fun onScoLost(session: Int) {
    if (vrSession != session || vrDevice == null) return
    vrDevice = null
    vrSession++
    runCatching { audioManager.mode = AudioManager.MODE_NORMAL }
    onVoiceRecognitionEnded?.invoke()
  }

  private fun endSession(h: BluetoothHeadset, reason: String) {
    val device = vrDevice
    vrSession++
    vrDevice = null
    if (device != null) {
      val r = runCatching { h.stopVoiceRecognition(device) }
      Log.i(TAG, "stopVoiceRecognition -> ${r.getOrNull()} ($reason)")
    }
  }

  private fun waitAudioOff(h: BluetoothHeadset, device: BluetoothDevice, then: () -> Unit) {
    val deadline = System.currentTimeMillis() + AUDIO_OFF_WAIT_MS
    val check = object : Runnable {
      override fun run() {
        val on = runCatching { h.isAudioConnected(device) }.getOrDefault(false)
        if (!on || System.currentTimeMillis() >= deadline) then() else main.postDelayed(this, POLL_MS)
      }
    }
    check.run()
  }

  // Prefer the HFP device that is the current SCO sink when several are connected.
  private fun pickDevice(h: BluetoothHeadset): BluetoothDevice? {
    val devices = h.connectedDevices
    val activeAddress = audioManager.availableCommunicationDevices.firstOrNull { it.type == SCO_TYPE }?.address
    return devices.firstOrNull { it.address == activeAddress } ?: devices.firstOrNull()
  }

  private fun withHeadset(block: (BluetoothHeadset?) -> Unit) {
    headset?.let { block(it); return }
    var done = false
    val once: (BluetoothHeadset?) -> Unit = { h -> if (!done) { done = true; block(h) } }
    proxyWaiters.add(once)
    main.postDelayed({ if (!done) { proxyWaiters.remove(once); once(null) } }, PROXY_TIMEOUT_MS)
    if (proxyRequested) return
    proxyRequested = true
    val adapter = context.getSystemService(BluetoothManager::class.java)?.adapter
    val requested = adapter?.getProfileProxy(
      context,
      object : BluetoothProfile.ServiceListener {
        override fun onServiceConnected(profile: Int, proxy: BluetoothProfile) {
          main.post {
            headset = proxy as BluetoothHeadset
            val waiters = proxyWaiters.toList()
            proxyWaiters.clear()
            waiters.forEach { it(headset) }
          }
        }

        override fun onServiceDisconnected(profile: Int) {
          main.post {
            headset = null
            proxyRequested = false
          }
        }
      },
      BluetoothProfile.HEADSET,
    ) ?: false
    if (!requested) proxyRequested = false
  }

  private fun ensureReceiver() {
    if (receiver != null) return
    val r = object : BroadcastReceiver() {
      override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.action != BluetoothHeadset.ACTION_AUDIO_STATE_CHANGED) return
        val state = intent.getIntExtra(BluetoothProfile.EXTRA_STATE, -1)
        val device = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
          intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
        } else {
          @Suppress("DEPRECATION") intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE)
        }
        val current = vrDevice ?: return
        if (state == BluetoothHeadset.STATE_AUDIO_CONNECTED && vrPending != null) {
          if (device != null && device != current) vrDevice = device
          vrPending?.invoke(true, "connected (broadcast)")
        } else if (state == BluetoothHeadset.STATE_AUDIO_DISCONNECTED && vrPending == null) {
          if (device != null && device != current) return // another HFP device, not our second press
          onScoLost(vrSession)
        }
      }
    }
    val filter = IntentFilter(BluetoothHeadset.ACTION_AUDIO_STATE_CHANGED)
    // EXPORTED: the broadcast comes from the Bluetooth app (another uid); it is a protected broadcast.
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      context.registerReceiver(r, filter, Context.RECEIVER_EXPORTED)
    } else {
      context.registerReceiver(r, filter)
    }
    receiver = r
  }

  // ---------------- screen button: virtual call ----------------

  private fun acquireSco(timeoutMs: Long, done: (Boolean, String) -> Unit) {
    val am = audioManager
    am.communicationDevice?.let { if (it.type == SCO_TYPE) { done(true, "already SCO"); return } }
    am.mode = AudioManager.MODE_IN_COMMUNICATION
    val sink = am.availableCommunicationDevices.firstOrNull { it.type == SCO_TYPE }
    if (sink == null) {
      am.mode = AudioManager.MODE_NORMAL
      done(false, "no SCO output")
      return
    }
    var settled = false
    lateinit var listener: AudioManager.OnCommunicationDeviceChangedListener
    lateinit var onTimeout: Runnable
    fun finish(ok: Boolean, note: String) {
      if (settled) return
      settled = true
      main.removeCallbacks(onTimeout)
      runCatching { am.removeOnCommunicationDeviceChangedListener(listener) }
      if (!ok) runCatching { am.clearCommunicationDevice(); am.mode = AudioManager.MODE_NORMAL }
      done(ok, note)
    }
    listener = AudioManager.OnCommunicationDeviceChangedListener { device -> if (device?.type == SCO_TYPE) finish(true, "connected") }
    // On the main thread like the timeout, so finish() is never entered from two threads at once.
    am.addOnCommunicationDeviceChangedListener(context.mainExecutor, listener)
    onTimeout = Runnable { finish(false, "SCO timeout") }
    main.postDelayed(onTimeout, timeoutMs)
    val accepted = runCatching { am.setCommunicationDevice(sink) }.getOrDefault(false)
    if (!accepted) {
      finish(false, "setCommunicationDevice returned false")
      return
    }
    am.communicationDevice?.let { if (it.type == SCO_TYPE) finish(true, "connected (immediate)") }
  }

  private companion object {
    const val TAG = "trv2.route"
    const val SCO_TYPE = AudioDeviceInfo.TYPE_BLUETOOTH_SCO
    const val PROXY_TIMEOUT_MS = 1_500L
    const val POLL_MS = 100L
    const val AUDIO_OFF_WAIT_MS = 1_000L
  }
}
```

`app/src/main/java/com/touringproject/v2/audio/AudioRouteControl.kt`:

```kotlin
package com.touringproject.v2.audio

import android.util.Log
import com.touringproject.v2.ask.RouteControl
import com.touringproject.v2.ask.Source

private const val VR_TIMEOUT_MS = 4_000L
private const val SCO_TIMEOUT_MS = 3_000L

// The intercom button arrives as a voice-recognition request from the headset; the screen button opens a virtual call.
class AudioRouteControl(private val route: AudioRoute) : RouteControl {
  private var source: Source? = null

  override suspend fun start(source: Source): Boolean {
    this.source = source
    val result = if (source == Source.HANDSFREE) route.startVoiceRecognition(VR_TIMEOUT_MS) else route.acquireSco(SCO_TIMEOUT_MS)
    Log.i("trv2.route", "route source=$source ok=${result.ok} note=${result.note}")
    return result.ok
  }

  override suspend fun stop() {
    if (source == Source.HANDSFREE) route.stopVoiceRecognition("done") else route.releaseSco()
    source = null
  }

  override fun inputDevice(): InputDevice? = route.activeInputDevice()
}
```

`app/src/main/java/com/touringproject/v2/audio/PcmRecorder.kt`:

```kotlin
package com.touringproject.v2.audio

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.touringproject.v2.ask.Recorded
import com.touringproject.v2.ask.Recorder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

// 16 kHz mono 16-bit PCM in memory (adr/0002). 20 s is about 640 KB.
@SuppressLint("MissingPermission") // RECORD_AUDIO is checked by the ask loop before it starts recording
class PcmRecorder(private val now: () -> Long = System::currentTimeMillis) : Recorder {
  private var record: AudioRecord? = null
  private var reader: Thread? = null
  private var buffer = ByteArrayOutputStream()
  private var name: String? = null

  override suspend fun start() = withContext(Dispatchers.IO) {
    val minSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
    val ar = AudioRecord(MediaRecorder.AudioSource.MIC, SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, minSize * 4)
    if (ar.state != AudioRecord.STATE_INITIALIZED) {
      ar.release()
      error("AudioRecord not initialized")
    }
    val out = ByteArrayOutputStream()
    ar.startRecording()
    val thread = Thread {
      val chunk = ByteArray(minSize)
      while (ar.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
        val n = ar.read(chunk, 0, chunk.size)
        if (n > 0) synchronized(out) { out.write(chunk, 0, n) } else if (n < 0) break
      }
    }
    thread.start()
    record = ar
    reader = thread
    buffer = out
    name = "rec-${now()}.pcm"
  }

  override suspend fun stop(): Recorded = withContext(Dispatchers.IO) {
    val ar = checkNotNull(record) { "not recording" }
    finish(ar)
    val pcm = synchronized(buffer) { buffer.toByteArray() }
    Recorded(pcm, checkNotNull(name)).also { name = null }
  }

  override suspend fun cancel() = withContext(Dispatchers.IO) {
    record?.let { finish(it) }
    name = null
  }

  private fun finish(ar: AudioRecord) {
    runCatching { ar.stop() }
    reader?.join(1_000)
    ar.release()
    record = null
    reader = null
  }

  private companion object {
    const val SAMPLE_RATE = 16_000
  }
}
```

`app/src/main/java/com/touringproject/v2/audio/ExoAnswerPlayer.kt`:

```kotlin
package com.touringproject.v2.audio

import android.content.Context
import android.os.Handler
import android.os.Looper
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.touringproject.v2.ask.AnswerPlayer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

const val CLIP_STALL_MS = 15_000L
const val STALL_CHECK_MS = 1_000L

/** Gives up on a clip whose position has not moved for CLIP_STALL_MS (a stalled stream reports nothing on its own). */
class StallWatch(private val stallMs: Long = CLIP_STALL_MS) {
  private var lastPosition = -1L
  private var idleMs = 0L

  /** Called every [elapsedMs] with the current position; true once the clip counts as stalled. */
  fun tick(positionMs: Long, elapsedMs: Long): Boolean {
    if (positionMs != lastPosition) {
      lastPosition = positionMs
      idleMs = 0
      return false
    }
    idleMs += elapsedMs
    return idleMs >= stallMs
  }
}

// Plays the answer clips one after another on the media stream, without taking audio focus (mix with the nav app).
class ExoAnswerPlayer(private val context: Context) : AnswerPlayer {
  private val main = Handler(Looper.getMainLooper())
  private var stopCurrent: (() -> Unit)? = null

  private class Session {
    var stopped = false
  }

  override suspend fun play(urls: List<String>) = withContext(Dispatchers.Main) {
    val session = Session()
    for (url in urls) {
      if (session.stopped) return@withContext
      playOne(url, session)
    }
  }

  override fun stop() {
    main.post { stopCurrent?.invoke() }
  }

  private suspend fun playOne(url: String, session: Session) = suspendCancellableCoroutine { cont ->
    val attributes = AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_SPEECH).build()
    val player = ExoPlayer.Builder(context).setAudioAttributes(attributes, false).build()
    val watch = StallWatch()
    var settled = false
    lateinit var stop: () -> Unit
    lateinit var check: Runnable
    fun finish(error: Throwable?) {
      if (settled) return
      settled = true
      main.removeCallbacks(check)
      player.release()
      // Another playback may have taken over stopCurrent meanwhile; its stop must stay reachable.
      if (stopCurrent === stop) stopCurrent = null
      if (error != null) cont.resumeWithException(error) else cont.resume(Unit)
    }
    check = Runnable {
      if (watch.tick(player.currentPosition, STALL_CHECK_MS)) finish(IllegalStateException("stalled")) else main.postDelayed(check, STALL_CHECK_MS)
    }
    stop = {
      session.stopped = true
      finish(null)
    }
    player.addListener(object : Player.Listener {
      override fun onPlaybackStateChanged(playbackState: Int) {
        if (playbackState == Player.STATE_ENDED) finish(null)
      }

      override fun onPlayerError(error: PlaybackException) = finish(error)
    })
    stopCurrent = stop
    cont.invokeOnCancellation { main.post { finish(null) } }
    player.setMediaItem(MediaItem.fromUri(url))
    player.prepare()
    player.play()
    main.postDelayed(check, STALL_CHECK_MS)
  }
}
```

`app/src/main/java/com/touringproject/v2/audio/TtsSpeech.kt`:

```kotlin
package com.touringproject.v2.audio

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import com.touringproject.v2.ask.Speech
import kotlinx.coroutines.CompletableDeferred
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

// The device voice: failure messages, "いま応答中です…", and the answer text when its audio cannot be played.
class TtsSpeech(context: Context) : Speech {
  private val ready = CompletableDeferred<Boolean>()
  private val pending = ConcurrentHashMap<String, CompletableDeferred<Unit>>()
  private val ids = AtomicInteger()
  private val tts: TextToSpeech = TextToSpeech(context.applicationContext) { status -> ready.complete(status == TextToSpeech.SUCCESS) }

  init {
    tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
      override fun onStart(utteranceId: String) = Unit
      override fun onDone(utteranceId: String) = settle(utteranceId)
      @Deprecated("Deprecated in Java")
      override fun onError(utteranceId: String) = settle(utteranceId)
      override fun onError(utteranceId: String, errorCode: Int) = settle(utteranceId)
      override fun onStop(utteranceId: String, interrupted: Boolean) = settle(utteranceId)
    })
  }

  private fun settle(id: String) {
    pending.remove(id)?.complete(Unit)
  }

  override suspend fun say(text: String) {
    if (!ready.await()) return
    tts.language = Locale.JAPAN
    val id = "u${ids.incrementAndGet()}"
    val done = CompletableDeferred<Unit>()
    pending[id] = done
    if (tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, id) != TextToSpeech.SUCCESS) settle(id)
    done.await()
  }

  override fun stop() {
    tts.stop()
    // Some engines do not report onStop for a flushed utterance; nothing may stay waiting.
    pending.keys.toList().forEach { settle(it) }
  }
}
```

`app/src/main/java/com/touringproject/v2/audio/ToneCues.kt`:

```kotlin
package com.touringproject.v2.audio

import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.touringproject.v2.ask.Cues

enum class Cue(val tone: Int, val durationMs: Int, val stream: Int) {
  // Intercoms drop the first part of a sound: a 1 s tone is heard as a short blip, so the start cue is longer.
  // It plays on the voice-call stream, which is what the intercom hears while SCO is up.
  START(ToneGenerator.TONE_SUP_DIAL, 1_500, AudioManager.STREAM_VOICE_CALL),
  // The rest play on the media stream: heard over the intercom's A2DP after returning to the nav app.
  SENT(ToneGenerator.TONE_DTMF_D, 800, AudioManager.STREAM_MUSIC),
  WAITING(ToneGenerator.TONE_DTMF_1, 600, AudioManager.STREAM_MUSIC),
  FAILURE(ToneGenerator.TONE_SUP_BUSY, 1_200, AudioManager.STREAM_MUSIC),
}

// Continuous tones only: the TONE_PROP_* tones have a built-in length (~0.16 s) that the duration cannot extend.
class ToneCues(private val makeGenerator: (stream: Int) -> ToneGenerator = { ToneGenerator(it, VOLUME) }) : Cues {
  private val main = Handler(Looper.getMainLooper())

  fun play(cue: Cue): Boolean {
    val generator = try {
      makeGenerator(cue.stream)
    } catch (e: RuntimeException) {
      Log.w(TAG, "ToneGenerator failed", e)
      return false
    }
    val started = generator.startTone(cue.tone, cue.durationMs)
    main.postDelayed({ generator.release() }, cue.durationMs + 200L)
    Log.i(TAG, "cue ${cue.name} started=$started")
    return started
  }

  override fun start() { play(Cue.START) }
  override fun sent() { play(Cue.SENT) }
  override fun waiting() { play(Cue.WAITING) }
  override fun failure() { play(Cue.FAILURE) }

  private companion object {
    const val TAG = "trv2.ride"
    const val VOLUME = 90
  }
}
```

- [ ] **Step 4: テストを通す**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*audio*'`
Expected: PASS（`StallWatchTest` 2件・`CueTest` 1件・`AudioRouteTest` 2件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/audio app/src/test/java/com/touringproject/v2/audio
git commit -m "feat: port the intercom route and add recording, playback, device voice and cues"
```

---

### Task 8: ナビを開く・前面サービス・位置の取得

**Files:**
- Create: `app/src/main/java/.../nav/AppLauncher.kt`、`service/RideForegroundService.kt`、`location/FusedPositionSource.kt`
- Test: `app/src/test/java/.../nav/AppLauncherTest.kt`、`service/RideForegroundServiceTest.kt`

**Interfaces:**
- Consumes: `NavReturn`・`KeepAlive`（Task 6）、`PositionSource`・`Subscription`・`Fix`（Task 5・6）、`LaunchableApp`（Task 2）
- Produces: `AppLauncher(context)`（`NavReturn` と `suspend launchableApps()`）、`RideForegroundService`、`ServiceKeepAlive(context): KeepAlive`、`FusedPositionSource(context): PositionSource`

`returnTo` はメインスレッドに切り替えない（`startActivity` はどのスレッドからでも呼べる。切り替えると Robolectric のテストがメインスレッドの待ち合いで止まる）。`RideForegroundService` は Task 10 の Manifest に登録する（Robolectric は Manifest に無いサービスも動かせるので、このタスクのテストは通る）。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/nav/AppLauncherTest.kt`:

```kotlin
package com.touringproject.v2.nav

import android.app.Application
import android.content.ComponentName
import android.content.Intent
import android.content.IntentFilter
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.touringproject.v2.settings.LaunchableApp
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf

@RunWith(AndroidJUnit4::class)
class AppLauncherTest {
  private val app = ApplicationProvider.getApplicationContext<Application>()

  private fun installLauncherApp(packageName: String, label: String) {
    val pm = shadowOf(app.packageManager)
    val component = ComponentName(packageName, "$packageName.Main")
    pm.addActivityIfNotPresent(component)
    pm.addIntentFilterForActivity(component, IntentFilter(Intent.ACTION_MAIN).apply { addCategory(Intent.CATEGORY_LAUNCHER) })
    pm.getInternalMutablePackageInfo(packageName).applicationInfo!!.nonLocalizedLabel = label
    pm.getInternalMutablePackageInfo(packageName).activities!!.first().nonLocalizedLabel = label
  }

  @Before
  fun setUp() {
    installLauncherApp("com.google.android.apps.maps", "マップ")
    installLauncherApp("jp.co.yahoo.carnavi", "カーナビ")
  }

  @Test
  fun returning_opens_the_nav_app_with_its_launcher_intent() = runTest {
    assertTrue(AppLauncher(app).returnTo("com.google.android.apps.maps"))
    val started = shadowOf(app).nextStartedActivity
    assertEquals("com.google.android.apps.maps", started.component?.packageName)
    assertTrue(started.flags and Intent.FLAG_ACTIVITY_NEW_TASK != 0)
  }

  @Test
  fun returning_to_an_app_that_is_not_installed_fails_quietly() = runTest {
    assertFalse(AppLauncher(app).returnTo("not.installed"))
  }

  @Test
  fun launchable_apps_are_listed_without_this_app() = runTest {
    val apps = AppLauncher(app).launchableApps()
    assertTrue(LaunchableApp("com.google.android.apps.maps", "マップ") in apps)
    assertTrue(apps.none { it.packageName == app.packageName })
  }
}
```

`app/src/test/java/com/touringproject/v2/service/RideForegroundServiceTest.kt`:

```kotlin
package com.touringproject.v2.service

import android.app.Application
import android.content.pm.ServiceInfo
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.Shadows.shadowOf

@RunWith(AndroidJUnit4::class)
class RideForegroundServiceTest {
  private val app = ApplicationProvider.getApplicationContext<Application>()

  @Test
  fun keep_alive_starts_and_stops_the_service() {
    val keepAlive = ServiceKeepAlive(app)
    keepAlive.start()
    assertEquals(RideForegroundService::class.java.name, shadowOf(app).nextStartedService.component?.className)
    keepAlive.stop()
    assertEquals(RideForegroundService::class.java.name, shadowOf(app).nextStoppedService.component?.className)
  }

  @Test
  fun the_service_runs_in_the_foreground_for_the_microphone_and_playback() {
    val controller = Robolectric.buildService(RideForegroundService::class.java).create().startCommand(0, 1)
    val shadow = shadowOf(controller.get())
    assertNotNull(shadow.lastForegroundNotification)
    assertEquals(
      ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
      controller.get().foregroundServiceType,
    )
  }
}
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AppLauncherTest' --tests '*RideForegroundServiceTest'`
Expected: コンパイルエラー（`AppLauncher`・`ServiceKeepAlive` が無い）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/nav/AppLauncher.kt`:

```kotlin
package com.touringproject.v2.nav

import android.content.Context
import android.content.Intent
import android.util.Log
import com.touringproject.v2.ask.NavReturn
import com.touringproject.v2.settings.LaunchableApp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.Collator
import java.util.Locale

class AppLauncher(private val context: Context) : NavReturn {
  // Opens the nav app with its launcher intent, which resumes the existing task (the route survives).
  // startActivity may be called from any thread, so this does not switch to the main thread.
  override suspend fun returnTo(packageName: String): Boolean {
    val intent = context.packageManager.getLaunchIntentForPackage(packageName) ?: return false
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    return try {
      context.startActivity(intent)
      true
    } catch (e: Exception) {
      Log.w("trv2.ride", "failed to launch $packageName", e)
      false
    }
  }

  suspend fun launchableApps(): List<LaunchableApp> = withContext(Dispatchers.IO) {
    val pm = context.packageManager
    val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
    val collator = Collator.getInstance(Locale.JAPANESE)
    pm.queryIntentActivities(intent, 0)
      .map { LaunchableApp(it.activityInfo.packageName, it.loadLabel(pm).toString()) }
      .distinctBy { it.packageName }
      .filter { it.packageName != context.packageName }
      .sortedWith(compareBy(collator) { it.label })
  }
}
```

`app/src/main/java/com/touringproject/v2/service/RideForegroundService.kt`:

```kotlin
package com.touringproject.v2.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.util.Log
import com.touringproject.v2.ask.KeepAlive

// Keeps the process alive while an answer is awaited and read out in the background (adr/0004, adr/0005).
class RideForegroundService : Service() {
  override fun onBind(intent: Intent?): IBinder? = null

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    val manager = getSystemService(NotificationManager::class.java)
    manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "応答", NotificationManager.IMPORTANCE_LOW))
    val notification = Notification.Builder(this, CHANNEL_ID)
      .setContentTitle("Touring V2")
      .setContentText("応答中")
      .setSmallIcon(android.R.drawable.ic_btn_speak_now)
      .setOngoing(true)
      .build()
    try {
      startForeground(
        NOTIFICATION_ID,
        notification,
        ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
      )
    } catch (e: RuntimeException) {
      // Android 14+ throws when the microphone permission is missing; the ask then fails on its own instead of crashing.
      Log.w("trv2.ride", "startForeground failed", e)
      stopSelf()
    }
    return START_NOT_STICKY
  }

  companion object {
    const val CHANNEL_ID = "trv2_answer"
    const val NOTIFICATION_ID = 1
  }
}

class ServiceKeepAlive(private val context: Context) : KeepAlive {
  override fun start() {
    context.startForegroundService(Intent(context, RideForegroundService::class.java))
  }

  override fun stop() {
    context.stopService(Intent(context, RideForegroundService::class.java))
  }
}
```

`app/src/main/java/com/touringproject/v2/location/FusedPositionSource.kt`:

```kotlin
package com.touringproject.v2.location

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.os.Looper
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority

fun Location.toFix() = Fix(latitude, longitude, time, if (hasAccuracy()) accuracy.toDouble() else null)

// Without the location permission both calls throw SecurityException; PositionTracker then simply has no fixes.
@SuppressLint("MissingPermission")
class FusedPositionSource(context: Context) : PositionSource {
  private val client = LocationServices.getFusedLocationProviderClient(context)

  override fun now() = System.currentTimeMillis()

  override fun lastKnown(onFix: (Fix) -> Unit) {
    client.lastLocation.addOnSuccessListener { it?.let { location -> onFix(location.toFix()) } }
  }

  override fun watch(onFix: (Fix) -> Unit): Subscription {
    val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 1_000).setMinUpdateIntervalMillis(1_000).build()
    val callback = object : LocationCallback() {
      override fun onLocationResult(result: LocationResult) = result.locations.forEach { onFix(it.toFix()) }
    }
    client.requestLocationUpdates(request, callback, Looper.getMainLooper())
    return Subscription { client.removeLocationUpdates(callback) }
  }
}
```

- [ ] **Step 4: テストを通す**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*AppLauncherTest' --tests '*RideForegroundServiceTest'`
Expected: PASS（`AppLauncherTest` 3件・`RideForegroundServiceTest` 2件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/nav app/src/main/java/com/touringproject/v2/service \
  app/src/main/java/com/touringproject/v2/location/FusedPositionSource.kt \
  app/src/test/java/com/touringproject/v2/nav app/src/test/java/com/touringproject/v2/service
git commit -m "feat: open the nav app, keep the process alive and read positions"
```

---

### Task 9: 画面（ホーム・対話・設定）

**Files:**
- Create: `app/src/main/java/.../ui/Labels.kt`、`HomeScreen.kt`、`AskOverlay.kt`、`SettingsScreens.kt`
- Test: `app/src/test/java/.../ui/LabelsTest.kt`、`ui/ScreensTest.kt`

**Interfaces:**
- Consumes: `FlowState`・`Phase`・`spokenMessage`・`RECORD_LIMIT_MS`（Task 4・6）、`Settings`・`maskKey`・`withRecentApp`・`USER_NAME_RE`（Task 2）、`ApiError`（Task 3）
- Produces:
  - `phaseColor(phase)`、`conversationLabel(expiresAt, now)`、`enum Banner(text) { NO_KEY, NO_RETURN_APP }`、`homeBanner(hasKey, returnAppMissing)`
  - `HomeUi(userName, banner, conversation)`、`@Composable HomeScreen(ui, onTapToTalk, onSettings, onUser, onBanner, onNewConversation, modifier)`
  - `overlayText(state, seconds)`、`@Composable AskOverlay(state, now, onStopRecording, onCancel)`
  - `@Composable SettingsScreen(...)`・`ConnectionScreen(apiKey, urlMissing, check, save)`・`UserScreen(userName, onChange)`・`ReturnAppScreen(settings, apps, onUpdate)`、`checkAndSave(key, check, save): KeyCheck`、`filterApps(apps, query)`

画面は状態を引数で受けて描くだけにし、テストでは引数を渡して確かめる。文言は React Native 版の画面と同じ。設定の一覧はこの計画では3行（接続・ユーザー名・戻るアプリ）。回答の音量と録音の確認の行は計画2で足す。ホームの警告の帯は、メディアの音量の警告を計画2で足す。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/ui/LabelsTest.kt`:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.ui.graphics.Color
import com.touringproject.v2.api.ApiError
import com.touringproject.v2.api.ApiErrorKind
import com.touringproject.v2.ask.FailureReason
import com.touringproject.v2.ask.FlowState
import com.touringproject.v2.ask.Phase
import com.touringproject.v2.settings.LaunchableApp
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant

class LabelsTest {
  @Test
  fun each_phase_has_its_colour() {
    assertEquals(Color(0xFFD42A2A), phaseColor(Phase.RECORDING))
    assertEquals(Color(0xFFD42A2A), phaseColor(Phase.SENDING))
    assertEquals(Color(0xFF1F4FD1), phaseColor(Phase.WAITING))
    assertEquals(Color(0xFF13804A), phaseColor(Phase.SPEAKING))
    assertEquals(Color(0xFF5B6170), phaseColor(Phase.FAILED))
  }

  @Test
  fun no_conversation() {
    assertEquals("新しい会話です", conversationLabel(null, 0))
    assertEquals("新しい会話です", conversationLabel(1_000, 1_000))
  }

  @Test
  fun shows_when_it_will_be_reset_in_japan_time() {
    val expiresAt = Instant.parse("2026-10-17T01:35:00Z").toEpochMilli()
    assertEquals("10:35 まで質問がなければ自動で区切ります", conversationLabel(expiresAt, expiresAt - 1))
  }

  @Test
  fun the_missing_key_comes_before_the_missing_return_app() {
    assertEquals(Banner.NO_KEY, homeBanner(hasKey = false, returnAppMissing = true))
    assertEquals(Banner.NO_RETURN_APP, homeBanner(hasKey = true, returnAppMissing = true))
    assertNull(homeBanner(hasKey = true, returnAppMissing = false))
  }

  @Test
  fun overlay_text_per_phase() {
    val recording = overlayText(FlowState(phase = Phase.RECORDING), seconds = 3)
    assertEquals("17", recording.big)
    assertEquals("送らずにやめる", recording.button)
    assertEquals("0", overlayText(FlowState(phase = Phase.RECORDING), seconds = 25).big)
    assertEquals("12", overlayText(FlowState(phase = Phase.WAITING), seconds = 12).big)
    assertEquals("愛鷹山です。", overlayText(FlowState(phase = Phase.SPEAKING, answer = "愛鷹山です。"), 0).detail)
    assertEquals("時間切れです。もう一度お話しください。", overlayText(FlowState(phase = Phase.FAILED, failure = FailureReason.TIMEOUT), 0).title)
  }

  @Test
  fun a_key_is_saved_only_after_the_backend_accepts_it() = runTest {
    val saved = mutableListOf<String>()
    assertEquals(KeyCheck.SAVED, checkAndSave("good", {}, { saved += it }))
    assertEquals(KeyCheck.INVALID, checkAndSave("bad", { throw ApiError(ApiErrorKind.INVALID_KEY) }, { saved += it }))
    assertEquals(KeyCheck.UNREACHABLE, checkAndSave("x", { throw ApiError(ApiErrorKind.NETWORK) }, { saved += it }))
    assertEquals(listOf("good"), saved)
  }

  @Test
  fun apps_are_filtered_by_label_or_package_name() {
    val apps = listOf(LaunchableApp("com.google.android.apps.maps", "マップ"), LaunchableApp("jp.co.yahoo.carnavi", "カーナビ"))
    assertEquals(apps, filterApps(apps, "  "))
    assertEquals(listOf(apps[0]), filterApps(apps, "MAPS"))
    assertEquals(listOf(apps[1]), filterApps(apps, "ナビ"))
  }
}
```

`app/src/test/java/com/touringproject/v2/ui/ScreensTest.kt`:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.touringproject.v2.ask.FlowState
import com.touringproject.v2.ask.Phase
import com.touringproject.v2.settings.LaunchableApp
import com.touringproject.v2.settings.Settings
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class HomeScreenTest {
  @get:Rule val rule = createComposeRule()

  @Test
  fun tap_to_talk_starts_a_screen_question() {
    var taps = 0
    rule.setContent { HomeScreen(HomeUi("rider01", null, "新しい会話です"), { taps++ }, {}, {}, {}, {}) }
    rule.onNodeWithTag("tapToTalk").performClick()
    assertEquals(1, taps)
  }

  @Test
  fun the_banner_leads_to_its_setting() {
    var opened: Banner? = null
    rule.setContent { HomeScreen(HomeUi("rider01", Banner.NO_KEY, "新しい会話です"), {}, {}, {}, { opened = it }, {}) }
    rule.onNodeWithText(Banner.NO_KEY.text).performClick()
    assertEquals(Banner.NO_KEY, opened)
  }

  @Test
  fun a_new_conversation_is_confirmed_first() {
    var resets = 0
    rule.setContent { HomeScreen(HomeUi("rider01", null, "新しい会話です"), {}, {}, {}, {}, { resets++ }) }
    rule.onNodeWithTag("newConversation").performClick()
    assertEquals(0, resets)
    rule.onNodeWithText("やめる").performClick()
    rule.onNodeWithTag("newConversation").performClick()
    rule.onNodeWithText("新しい会話にする").performClick()
    assertEquals(1, resets)
  }
}

@RunWith(AndroidJUnit4::class)
class AskOverlayTest {
  @get:Rule val rule = createComposeRule()

  @Test
  fun nothing_is_shown_while_idle() {
    rule.setContent { AskOverlay(FlowState(), { 0L }, {}, {}) }
    rule.onNodeWithTag("overlay").assertDoesNotExist()
  }

  @Test
  fun while_recording_the_big_area_sends_and_the_button_cancels() {
    var sent = 0
    var cancelled = 0
    rule.setContent { AskOverlay(FlowState(phase = Phase.RECORDING), { 0L }, { sent++ }, { cancelled++ }) }
    rule.onNodeWithText("話してください").assertIsDisplayed()
    rule.onNodeWithTag("overlayMain").performClick()
    rule.onNodeWithText("送らずにやめる").performClick()
    assertEquals(1, sent)
    assertEquals(1, cancelled)
  }

  @Test
  fun the_phone_mic_warning_shows_while_recording() {
    rule.setContent { AskOverlay(FlowState(phase = Phase.RECORDING, phoneMic = true), { 0L }, {}, {}) }
    rule.onNodeWithText("インカムのマイクに繋がっていません（本体のマイクで録音中）").assertIsDisplayed()
  }

  @Test
  fun while_speaking_the_answer_is_shown_and_tapping_stops_it() {
    var cancelled = 0
    rule.setContent { AskOverlay(FlowState(phase = Phase.SPEAKING, answer = "愛鷹山です。"), { 0L }, {}, { cancelled++ }) }
    rule.onNodeWithText("愛鷹山です。").assertIsDisplayed()
    rule.onNodeWithTag("overlayMain").performClick()
    assertEquals(1, cancelled)
  }
}

@RunWith(AndroidJUnit4::class)
class SettingsScreensTest {
  @get:Rule val rule = createComposeRule()
  private val maps = LaunchableApp("com.google.android.apps.maps", "マップ")

  @Test
  fun an_invalid_user_name_is_refused_and_a_valid_one_is_confirmed() {
    val changed = mutableListOf<String>()
    rule.setContent { UserScreen("rider01", { changed += it }) }
    rule.onNodeWithTag("userInput").performTextInput("No!")
    rule.onNodeWithTag("changeUser").performClick()
    rule.onNodeWithTag("userError").assertIsDisplayed()
    rule.onNodeWithTag("userInput").performTextClearance()
    rule.onNodeWithTag("userInput").performTextInput("rider02")
    rule.onNodeWithTag("changeUser").performClick()
    rule.onNodeWithText("変える").performClick()
    assertEquals(listOf("rider02"), changed)
  }

  @Test
  fun choosing_a_return_app_also_remembers_it() {
    var updated: Settings? = null
    rule.setContent { ReturnAppScreen(Settings("rider01"), listOf(maps), { updated = it }) }
    rule.onNodeWithTag("app-${maps.packageName}").performClick()
    assertEquals(maps, updated!!.returnApp)
    assertEquals(listOf(maps), updated!!.recentApps)
  }

  @Test
  fun a_saved_key_is_shown_masked() {
    rule.setContent { ConnectionScreen("abcdef1234567890", urlMissing = false, check = {}, save = {}) }
    rule.onNodeWithTag("currentKey").assertIsDisplayed()
    rule.onNodeWithText("••••••••7890").assertIsDisplayed()
  }

  @Test
  fun a_new_key_is_checked_then_saved() {
    val saved = mutableListOf<String?>()
    rule.setContent { ConnectionScreen(null, urlMissing = false, check = {}, save = { saved += it }) }
    rule.onNodeWithTag("keyInput").performTextInput(" new-key ")
    rule.onNodeWithTag("saveKey").performClick()
    rule.waitUntil { saved.isNotEmpty() }
    assertEquals(listOf<String?>("new-key"), saved)
    rule.onNodeWithText("保存しました").assertIsDisplayed()
  }
}
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ui*'`
Expected: コンパイルエラー（`HomeScreen`・`overlayText` などが無い）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/ui/Labels.kt`:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.ui.graphics.Color
import com.touringproject.v2.ask.Phase
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

// SC-03: the state must be readable from color alone.
fun phaseColor(phase: Phase): Color = when (phase) {
  Phase.IDLE -> Color(0xFF000000)
  Phase.RECORDING, Phase.SENDING -> Color(0xFFD42A2A)
  Phase.WAITING -> Color(0xFF1F4FD1)
  Phase.SPEAKING -> Color(0xFF13804A)
  Phase.FAILED -> Color(0xFF5B6170)
}

private val HHMM = DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.of("Asia/Tokyo"))

// SC-02: when the current conversation lapses, shown in Japan time.
fun conversationLabel(expiresAt: Long?, now: Long): String =
  if (expiresAt == null || expiresAt <= now) "新しい会話です"
  else "${HHMM.format(Instant.ofEpochMilli(expiresAt))} まで質問がなければ自動で区切ります"

enum class Banner(val text: String) {
  NO_KEY("接続キーが未設定です（押して設定）"),
  NO_RETURN_APP("戻り先のアプリが未設定です（押して選ぶ）"),
}

/** SC-02 shows at most one warning band, the most urgent first. */
fun homeBanner(hasKey: Boolean, returnAppMissing: Boolean): Banner? = when {
  !hasKey -> Banner.NO_KEY
  returnAppMissing -> Banner.NO_RETURN_APP
  else -> null
}
```

`app/src/main/java/com/touringproject/v2/ui/HomeScreen.kt`:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

data class HomeUi(val userName: String, val banner: Banner?, val conversation: String)

// SC-02 (slice 1 minimum). Glanced at while riding: it never scrolls.
@Composable
fun HomeScreen(
  ui: HomeUi,
  onTapToTalk: () -> Unit,
  onSettings: () -> Unit,
  onUser: () -> Unit,
  onBanner: (Banner) -> Unit,
  onNewConversation: () -> Unit,
  modifier: Modifier = Modifier,
) {
  var confirming by remember { mutableStateOf(false) }
  Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
      Text(ui.userName, Modifier.clickable(onClick = onUser), fontSize = 22.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
      Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = onTapToTalk, Modifier.testTag("tapToTalk")) { Text("🎤 押して話す") }
        OutlinedButton(onClick = onSettings) { Text("⚙ 設定") }
      }
    }
    ui.banner?.let { banner ->
      Text(
        banner.text,
        Modifier.fillMaxWidth().background(Color(0xFFF5C518), RoundedCornerShape(8.dp)).clickable { onBanner(banner) }.padding(12.dp).testTag("banner"),
        color = Color.Black,
        fontSize = 16.sp,
      )
    }
    Text("インカムのボタンで話せます", color = Color(0xFF13804A), fontSize = 16.sp)
    Column(
      Modifier.fillMaxWidth().heightIn(min = 76.dp, max = 140.dp).background(Color(0xFF1F4FD1), RoundedCornerShape(16.dp))
        .clickable { confirming = true }.padding(16.dp).testTag("newConversation"),
      verticalArrangement = Arrangement.Center,
    ) {
      Text(ui.conversation, color = Color.White, fontSize = 16.sp)
      Text("新しい会話を始める", color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold)
    }
  }
  // DL-02
  if (confirming) {
    AlertDialog(
      onDismissRequest = { confirming = false },
      title = { Text("新しい会話を始めますか？") },
      text = { Text("次の質問から、これまでの会話を踏まえずに答えます。") },
      confirmButton = { TextButton(onClick = { confirming = false; onNewConversation() }) { Text("新しい会話にする") } },
      dismissButton = { TextButton(onClick = { confirming = false }) { Text("やめる") } },
    )
  }
}
```

`app/src/main/java/com/touringproject/v2/ui/AskOverlay.kt`:

```kotlin
package com.touringproject.v2.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.touringproject.v2.ask.FlowState
import com.touringproject.v2.ask.Phase
import com.touringproject.v2.ask.RECORD_LIMIT_MS
import com.touringproject.v2.ask.spokenMessage
import kotlinx.coroutines.delay

data class OverlayText(val title: String, val big: String, val detail: String, val button: String)

fun overlayText(state: FlowState, seconds: Long): OverlayText = when (state.phase) {
  Phase.RECORDING -> OverlayText("話してください", (RECORD_LIMIT_MS / 1000 - seconds).coerceAtLeast(0).toString(), "もう一度ボタンを押すか、ここを押すと送ります", "送らずにやめる")
  Phase.SENDING -> OverlayText("送っています…", "", "", "送らずにやめる")
  Phase.WAITING -> OverlayText("考えています…", seconds.toString(), "最初の質問は10秒ほど", "待つのをやめる")
  Phase.SPEAKING -> OverlayText("回答中", "", state.answer ?: "", "読み上げを止める")
  Phase.FAILED -> OverlayText(state.failure?.let(::spokenMessage) ?: "失敗しました", "", "", "閉じる")
  Phase.IDLE -> OverlayText("", "", "", "")
}

// SC-03: covers the whole screen in the phase's colour while an ask runs.
@Composable
fun AskOverlay(state: FlowState, now: () -> Long, onStopRecording: () -> Unit, onCancel: () -> Unit) {
  if (state.phase == Phase.IDLE) return
  var clock by remember { mutableLongStateOf(now()) }
  // Display-only timer; the ask loop does not depend on it.
  LaunchedEffect(state.phaseStartedAt) {
    while (true) {
      clock = now()
      delay(250)
    }
  }
  // The overlay is not a screen of its own: Back must not reveal the screen under it mid-ask.
  BackHandler {}
  val seconds = ((clock - state.phaseStartedAt) / 1000).coerceAtLeast(0)
  val text = overlayText(state, seconds)
  val onMain: () -> Unit = when (state.phase) {
    Phase.RECORDING -> onStopRecording
    Phase.SPEAKING -> onCancel
    else -> ({})
  }
  Column(
    Modifier.fillMaxSize().background(phaseColor(state.phase)).safeDrawingPadding().padding(24.dp).testTag("overlay"),
    verticalArrangement = Arrangement.spacedBy(12.dp),
  ) {
    if (state.phoneMic && state.phase == Phase.RECORDING) {
      Text(
        "インカムのマイクに繋がっていません（本体のマイクで録音中）",
        Modifier.fillMaxWidth().background(Color(0xFFF5C518), RoundedCornerShape(8.dp)).padding(12.dp),
        color = Color.Black,
        fontSize = 18.sp,
      )
    }
    Column(
      Modifier.weight(1f).fillMaxWidth().clickable(onClick = onMain).testTag("overlayMain"),
      verticalArrangement = Arrangement.Center,
      horizontalAlignment = Alignment.CenterHorizontally,
    ) {
      Text(text.title, color = Color.White, fontSize = 36.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
      if (text.big.isNotEmpty()) Text(text.big, color = Color.White, fontSize = 140.sp, fontWeight = FontWeight.ExtraBold)
      if (text.detail.isNotEmpty()) Text(text.detail, color = Color.White, fontSize = 22.sp, textAlign = TextAlign.Center, maxLines = 8)
    }
    OutlinedButton(
      onClick = onCancel,
      modifier = Modifier.fillMaxWidth().testTag("overlayCancel"),
      border = BorderStroke(4.dp, Color.White),
      shape = RoundedCornerShape(16.dp),
    ) {
      Text(text.button, color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(vertical = 10.dp))
    }
  }
}
```

`app/src/main/java/com/touringproject/v2/ui/SettingsScreens.kt`:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.touringproject.v2.api.ApiError
import com.touringproject.v2.api.ApiErrorKind
import com.touringproject.v2.settings.LaunchableApp
import com.touringproject.v2.settings.ReturnTiming
import com.touringproject.v2.settings.Settings
import com.touringproject.v2.settings.USER_NAME_RE
import com.touringproject.v2.settings.maskKey
import com.touringproject.v2.settings.withRecentApp
import kotlinx.coroutines.launch

private val Blue = Color(0xFF1F4FD1)
private val Red = Color(0xFFD42A2A)

@Composable
private fun SettingsRow(title: String, value: String, onClick: () -> Unit) {
  Surface(
    Modifier.fillMaxWidth().clickable(onClick = onClick),
    shape = RoundedCornerShape(12.dp),
    border = BorderStroke(1.dp, Color(0xFFCCCCCC)),
  ) {
    Row(Modifier.padding(18.dp), horizontalArrangement = Arrangement.SpaceBetween) {
      Text(title, Modifier.weight(1f), fontSize = 18.sp)
      Text(value, color = Color(0xFF666666), fontSize = 18.sp)
    }
  }
}

// SC-09 (plan 1: the screens the hands-free loop needs; the others are added in plan 2).
@Composable
fun SettingsScreen(settings: Settings, apiKey: String?, onConnection: () -> Unit, onUser: () -> Unit, onReturnApp: () -> Unit, modifier: Modifier = Modifier) {
  val returnValue = if (!settings.returnEnabled) "戻らない" else settings.returnApp?.label ?: "未設定"
  Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
    SettingsRow("接続の設定", apiKey?.let(::maskKey) ?: "未設定", onConnection)
    SettingsRow("ユーザー名", settings.userName, onUser)
    SettingsRow("応答後に戻るアプリ", returnValue, onReturnApp)
  }
}

enum class KeyCheck { SAVED, INVALID, UNREACHABLE }

/** Checks the key against the Backend; the old key stays when the new one does not work. */
suspend fun checkAndSave(key: String, check: suspend (String) -> Unit, save: suspend (String) -> Unit): KeyCheck = try {
  check(key)
  save(key)
  KeyCheck.SAVED
} catch (e: ApiError) {
  if (e.kind == ApiErrorKind.INVALID_KEY) KeyCheck.INVALID else KeyCheck.UNREACHABLE
}

// SC-13
@Composable
fun ConnectionScreen(
  apiKey: String?,
  urlMissing: Boolean,
  check: suspend (String) -> Unit,
  save: suspend (String?) -> Unit,
  modifier: Modifier = Modifier,
) {
  val scope = rememberCoroutineScope()
  var input by remember { mutableStateOf("") }
  var checking by remember { mutableStateOf(false) }
  var message by remember { mutableStateOf<String?>(null) }
  var confirmingDelete by remember { mutableStateOf(false) }
  Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
    Text("接続キー", color = Color(0xFF666666), fontSize = 16.sp)
    Text(apiKey?.let(::maskKey) ?: "未設定", fontSize = 20.sp, fontFamily = FontFamily.Monospace, modifier = Modifier.testTag("currentKey"))
    Text("身内で共通のキーを使ってかまいません。記録はユーザー名で分かれます。", color = Color(0xFF666666), fontSize = 14.sp)
    OutlinedTextField(input, { input = it }, Modifier.fillMaxWidth().testTag("keyInput"), placeholder = { Text("キーを貼り付け") }, singleLine = true)
    Button(
      onClick = {
        val key = input.trim()
        if (key.isEmpty()) return@Button
        checking = true
        scope.launch {
          message = when (checkAndSave(key, check, save)) {
            KeyCheck.SAVED -> { input = ""; "保存しました" }
            KeyCheck.INVALID -> "キーが正しくありません。元のキーのままです。"
            KeyCheck.UNREACHABLE -> "サーバーに繋がりません。元のキーのままです。"
          }
          checking = false
        }
      },
      enabled = !checking,
      modifier = Modifier.fillMaxWidth().testTag("saveKey"),
      colors = ButtonDefaults.buttonColors(containerColor = Blue),
    ) { Text(if (checking) "確かめています…" else "確かめて保存", fontSize = 18.sp) }
    if (apiKey != null) {
      Button(onClick = { confirmingDelete = true }, Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Red)) {
        Text("キーを削除", fontSize = 18.sp)
      }
    }
    message?.let { Text(it, Modifier.testTag("keyMessage")) }
    if (urlMissing) Text("API の URL が設定されていません（local.properties の trv2.apiBaseUrl）", color = Red)
  }
  // DL-01 (connection key)
  if (confirmingDelete) {
    AlertDialog(
      onDismissRequest = { confirmingDelete = false },
      title = { Text("接続キーを削除しますか？") },
      confirmButton = { TextButton(onClick = { confirmingDelete = false; scope.launch { save(null) } }) { Text("削除する") } },
      dismissButton = { TextButton(onClick = { confirmingDelete = false }) { Text("やめる") } },
    )
  }
}

// SC-18
@Composable
fun UserScreen(userName: String, onChange: (String) -> Unit, modifier: Modifier = Modifier) {
  var input by remember { mutableStateOf("") }
  var error by remember { mutableStateOf(false) }
  var confirming by remember { mutableStateOf<String?>(null) }
  Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
    Text("今のユーザー名", color = Color(0xFF666666), fontSize = 16.sp)
    Text(userName, fontSize = 32.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace)
    Text("別の端末に記録を引き継ぐときに使います。控えておいてください。", color = Color(0xFF666666), fontSize = 14.sp)
    OutlinedTextField(input, { input = it }, Modifier.fillMaxWidth().testTag("userInput"), placeholder = { Text("新しいユーザー名") }, singleLine = true)
    if (error) Text("英小文字と数字の3〜20文字にしてください", color = Red, modifier = Modifier.testTag("userError"))
    Button(
      onClick = {
        val name = input.trim()
        error = !USER_NAME_RE.matches(name)
        if (!error) confirming = name
      },
      modifier = Modifier.fillMaxWidth().testTag("changeUser"),
      colors = ButtonDefaults.buttonColors(containerColor = Blue),
    ) { Text("変更する", fontSize = 18.sp) }
  }
  // DL-03
  confirming?.let { name ->
    AlertDialog(
      onDismissRequest = { confirming = null },
      title = { Text("「$name」に変えますか？") },
      text = { Text("今の記録は引き継ぎません。元の名前に戻せば、また見られます。同じ名前の記録が既にあれば、その記録に切り替わります。") },
      confirmButton = { TextButton(onClick = { confirming = null; input = ""; onChange(name) }) { Text("変える") } },
      dismissButton = { TextButton(onClick = { confirming = null }) { Text("やめる") } },
    )
  }
}

private val TIMINGS = listOf(ReturnTiming.SENT to "送ったらすぐ", ReturnTiming.ANSWERED to "回答が届いたら", ReturnTiming.SPOKEN to "読み上げが終わったら")

fun filterApps(apps: List<LaunchableApp>, query: String): List<LaunchableApp> {
  val q = query.trim().lowercase()
  return if (q.isEmpty()) apps else apps.filter { q in it.label.lowercase() || q in it.packageName.lowercase() }
}

// SC-10
@Composable
fun ReturnAppScreen(settings: Settings, apps: List<LaunchableApp>, onUpdate: (Settings) -> Unit, modifier: Modifier = Modifier) {
  var filter by remember { mutableStateOf("") }
  val choose = { app: LaunchableApp -> onUpdate(settings.copy(returnApp = app, recentApps = withRecentApp(settings.recentApps, app))) }
  LazyColumn(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
    item {
      Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Text("応答後にアプリへ戻る", fontSize = 18.sp)
        Switch(settings.returnEnabled, { onUpdate(settings.copy(returnEnabled = it)) }, Modifier.testTag("returnSwitch"))
      }
      Text("戻るのはインカムのボタンで始めた応答だけです（画面から質問したときは戻りません）。", color = Color(0xFF666666), fontSize = 13.sp)
    }
    if (settings.returnEnabled) {
      item {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
          TIMINGS.forEach { (timing, label) ->
            FilterChip(settings.returnTiming == timing, { onUpdate(settings.copy(returnTiming = timing)) }, { Text(label, fontSize = 13.sp) })
          }
        }
        Text("現在の戻り先: ${settings.returnApp?.label ?: "未設定"}", fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("currentReturnApp"))
      }
      items(settings.recentApps, key = { "recent-" + it.packageName }) { app ->
        Row(verticalAlignment = Alignment.CenterVertically) {
          Text(app.label, Modifier.weight(1f).clickable { choose(app) }.padding(12.dp), fontSize = 16.sp)
          Text("✕", Modifier.clickable { onUpdate(settings.copy(recentApps = settings.recentApps.filter { it.packageName != app.packageName })) }.padding(12.dp), fontSize = 18.sp)
        }
      }
      item {
        OutlinedTextField(filter, { filter = it }, Modifier.fillMaxWidth().testTag("appFilter"), placeholder = { Text("アプリを絞り込む") }, singleLine = true)
      }
      items(filterApps(apps, filter), key = { it.packageName }) { app ->
        Column(Modifier.fillMaxWidth().clickable { choose(app) }.padding(vertical = 10.dp).testTag("app-${app.packageName}")) {
          Text(app.label, fontSize = 16.sp)
          Text(app.packageName, color = Color(0xFF888888), fontSize = 12.sp)
        }
      }
    }
  }
}
```

- [ ] **Step 4: テストを通す**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*ui*'`
Expected: PASS（`LabelsTest` 7件・`HomeScreenTest` 3件・`AskOverlayTest` 4件・`SettingsScreensTest` 4件）

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/ui app/src/test/java/com/touringproject/v2/ui
git commit -m "feat: add the home, ask and settings screens"
```

---

### Task 10: 組み立てと、インカムの合図の受け口

**Files:**
- Create: `app/src/main/java/.../AppGraph.kt`、`TouringApp.kt`、`ui/AppUi.kt`
- Modify: `app/src/main/java/.../MainActivity.kt`（Task 1 の仮を置き換える）、`app/src/main/AndroidManifest.xml`（全体を置き換える）
- Test: `app/src/test/java/.../MainActivityTest.kt`

**Interfaces:**
- Consumes: Task 2〜9 のすべて
- Produces:
  - `AppGraph(context, scope = MainScope())`: `controller`・`presses: PressGate`・`state: StateFlow<FlowState>`・`isReady: StateFlow<Boolean>`・`settings`・`apiKeys`・`launcher`・`conversation`・`apiBaseUrl`・`permissionsAnswered()`
  - `TouringApp.graph`
  - `MainActivity`: `VOICE_COMMAND` を受けて `graph.presses.offer(...)` に渡し、action を `MAIN` に書き換える（作り直しで数え直さない）。起動のたびに権限をまとめて求め、答えが出たら `graph.permissionsAnswered()`

押下は、設定と接続キーを読み終え、かつ権限の確認に答えが出るまで `PressGate` が預かる（React Native 版の「権限を求めてから受け付けを開く」と同じ）。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/MainActivityTest.kt`:

```kotlin
package com.touringproject.v2

import android.content.Intent
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf
import android.os.Looper

@RunWith(AndroidJUnit4::class)
class MainActivityTest {
  private val app = ApplicationProvider.getApplicationContext<TouringApp>()

  private fun voiceCommand() = Intent(app, MainActivity::class.java).setAction(Intent.ACTION_VOICE_COMMAND)

  private fun waitUntil(condition: () -> Boolean) {
    repeat(200) {
      if (condition()) return
      shadowOf(Looper.getMainLooper()).idle()
      Thread.sleep(10)
    }
    error("condition never became true")
  }

  @Test
  fun the_intercom_button_starts_one_ask_even_when_the_activity_is_recreated() {
    val graph = app.graph
    ActivityScenario.launch<MainActivity>(voiceCommand()).use { scenario ->
      // The press waits until the permission prompt has been answered and the settings are loaded.
      assertEquals(0, graph.controller.runsStarted)
      graph.permissionsAnswered()
      waitUntil { graph.controller.runsStarted == 1 }
      scenario.recreate()
      shadowOf(Looper.getMainLooper()).idle()
      assertEquals(1, graph.controller.runsStarted)
    }
  }
}
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --tests '*MainActivityTest'`
Expected: コンパイルエラー（`TouringApp`・`graph` が無い）

- [ ] **Step 3: 実装する**

`app/src/main/java/com/touringproject/v2/AppGraph.kt`:

```kotlin
package com.touringproject.v2

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.util.Log
import com.touringproject.v2.api.ApiClient
import com.touringproject.v2.ask.AskController
import com.touringproject.v2.ask.AskDeps
import com.touringproject.v2.ask.ConversationState
import com.touringproject.v2.ask.FlowState
import com.touringproject.v2.ask.IDLE
import com.touringproject.v2.ask.RecordingMeta
import com.touringproject.v2.ask.RecordingSink
import com.touringproject.v2.audio.AudioRoute
import com.touringproject.v2.audio.AudioRouteControl
import com.touringproject.v2.audio.ExoAnswerPlayer
import com.touringproject.v2.audio.PcmRecorder
import com.touringproject.v2.audio.ToneCues
import com.touringproject.v2.audio.TtsSpeech
import com.touringproject.v2.handsfree.PressGate
import com.touringproject.v2.location.FusedPositionSource
import com.touringproject.v2.location.PositionTracker
import com.touringproject.v2.nav.AppLauncher
import com.touringproject.v2.service.ServiceKeepAlive
import com.touringproject.v2.settings.ApiKeyStore
import com.touringproject.v2.settings.DataStoreKeyValueStore
import com.touringproject.v2.settings.KeystoreCipher
import com.touringproject.v2.settings.SettingsRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Builds the app's parts by hand (no DI library) and owns them for the life of the process. */
class AppGraph(private val context: Context, val scope: CoroutineScope = MainScope()) {
  val apiBaseUrl: String = BuildConfig.API_BASE_URL
  private val store = DataStoreKeyValueStore(context)
  val settings = SettingsRepository(store)
  val apiKeys = ApiKeyStore(store, KeystoreCipher())
  val launcher = AppLauncher(context)
  val audioRoute = AudioRoute(context)
  val conversation = ConversationState()

  private val flowState = MutableStateFlow(IDLE)
  val state: StateFlow<FlowState> = flowState.asStateFlow()

  private val ready = MutableStateFlow(false)
  val isReady: StateFlow<Boolean> = ready.asStateFlow()
  private var loaded = false
  private var permissionsAsked = false

  val controller: AskController = AskController(
    AskDeps(
      now = System::currentTimeMillis,
      sleep = { delay(it) },
      settings = settings::current,
      apiKey = { if (apiBaseUrl.isEmpty()) null else apiKeys.current() },
      micAllowed = { context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED },
      mediaVolume = { runCatching { audioRoute.mediaVolume() }.getOrNull() },
      api = { key, user -> ApiClient(apiBaseUrl, key, user) },
      conversation = conversation,
      route = AudioRouteControl(audioRoute),
      recorder = PcmRecorder(),
      // Recordings are kept for SC-12 from plan 2 of the migration.
      recordings = object : RecordingSink {
        override fun saved(meta: RecordingMeta) = Unit
        override fun transcribed(name: String, transcript: String) = Unit
      },
      location = PositionTracker(FusedPositionSource(context)),
      service = ServiceKeepAlive(context),
      nav = launcher,
      cues = ToneCues(),
      player = ExoAnswerPlayer(context),
      speech = TtsSpeech(context),
      onState = {
        Log.i("trv2.ask", "phase=${it.phase} source=${it.source} failure=${it.failure} phoneMic=${it.phoneMic}")
        flowState.value = it
      },
      log = { event, data -> Log.i("trv2.ask", "$event $data") },
    ),
    scope,
  )

  /** The intercom button presses wait here until settings are loaded and the permission prompt has been answered. */
  val presses = PressGate { controller.press() }

  init {
    // The headset dropping SCO during a voice-recognition session is the second press.
    audioRoute.onVoiceRecognitionEnded = { controller.stopRecording() }
    scope.launch {
      settings.load()
      apiKeys.load()
      loaded = true
      openWhenReady()
    }
  }

  fun permissionsAnswered() {
    permissionsAsked = true
    openWhenReady()
  }

  private fun openWhenReady() {
    if (!loaded || !permissionsAsked || ready.value) return
    ready.value = true
    presses.openGate(System.currentTimeMillis())
  }
}
```

`app/src/main/java/com/touringproject/v2/TouringApp.kt`:

```kotlin
package com.touringproject.v2

import android.app.Application

class TouringApp : Application() {
  lateinit var graph: AppGraph
    private set

  override fun onCreate() {
    super.onCreate()
    graph = AppGraph(this)
  }
}
```

`app/src/main/java/com/touringproject/v2/MainActivity.kt`（全体を置き換える）:

```kotlin
package com.touringproject.v2

import android.Manifest
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import com.touringproject.v2.theme.TouringV2Theme
import com.touringproject.v2.ui.AppUi

class MainActivity : ComponentActivity() {
  private val graph get() = (application as TouringApp).graph

  private val permissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
    graph.permissionsAnswered()
  }

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    handleVoiceCommand(intent)
    if (savedInstanceState == null) {
      permissions.launch(
        arrayOf(
          Manifest.permission.RECORD_AUDIO,
          Manifest.permission.ACCESS_FINE_LOCATION,
          Manifest.permission.ACCESS_COARSE_LOCATION,
          Manifest.permission.BLUETOOTH_CONNECT,
          Manifest.permission.POST_NOTIFICATIONS,
        ),
      )
    }
    enableEdgeToEdge()
    setContent { TouringV2Theme { AppUi(graph) } }
  }

  override fun onNewIntent(intent: Intent) {
    super.onNewIntent(intent)
    handleVoiceCommand(intent)
  }

  // The intercom's assistant button. The action is rewritten so a recreated activity does not count the same press again.
  private fun handleVoiceCommand(intent: Intent?) {
    if (intent?.action != Intent.ACTION_VOICE_COMMAND) return
    intent.action = Intent.ACTION_MAIN
    val now = System.currentTimeMillis()
    graph.presses.offer(now, now)
  }
}
```

`app/src/main/java/com/touringproject/v2/ui/AppUi.kt`:

```kotlin
package com.touringproject.v2.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation3.runtime.NavKey
import androidx.navigation3.runtime.entryProvider
import androidx.navigation3.runtime.rememberNavBackStack
import androidx.navigation3.ui.NavDisplay
import com.touringproject.v2.AppGraph
import com.touringproject.v2.api.ApiClient
import com.touringproject.v2.settings.LaunchableApp
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable data object HomeKey : NavKey
@Serializable data object SettingsKey : NavKey
@Serializable data object ConnectionKey : NavKey
@Serializable data object UserKey : NavKey
@Serializable data object ReturnAppKey : NavKey

@Composable
fun AppUi(graph: AppGraph) {
  val ready by graph.isReady.collectAsStateWithLifecycle()
  val state by graph.state.collectAsStateWithLifecycle()
  val settings by graph.settings.settings.collectAsStateWithLifecycle()
  val apiKey by graph.apiKeys.apiKey.collectAsStateWithLifecycle()
  val scope = rememberCoroutineScope()
  val backStack = rememberNavBackStack(HomeKey)
  val current = settings
  // Re-read on every phase change, so the label updates once an ask has renewed the conversation.
  val expiresAt = remember(state) { graph.conversation.expiresAt(System.currentTimeMillis()) }
  Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
    Box(Modifier.fillMaxSize()) {
      if (!ready || current == null) {
        Text("準備中…", Modifier.safeDrawingPadding())
      } else {
        NavDisplay(
          backStack = backStack,
          onBack = { backStack.removeLastOrNull() },
          entryProvider = entryProvider {
            entry<HomeKey> {
              val ui = HomeUi(
                userName = current.userName,
                banner = homeBanner(hasKey = apiKey != null, returnAppMissing = current.returnEnabled && current.returnApp == null),
                conversation = conversationLabel(expiresAt, System.currentTimeMillis()),
              )
              HomeScreen(
                ui = ui,
                onTapToTalk = graph.controller::tapToTalk,
                onSettings = { backStack.add(SettingsKey) },
                onUser = { backStack.add(UserKey) },
                onBanner = { backStack.add(if (it == Banner.NO_KEY) ConnectionKey else ReturnAppKey) },
                onNewConversation = graph.controller::resetConversation,
                modifier = Modifier.safeDrawingPadding(),
              )
            }
            entry<SettingsKey> {
              SettingsScreen(
                current, apiKey,
                onConnection = { backStack.add(ConnectionKey) },
                onUser = { backStack.add(UserKey) },
                onReturnApp = { backStack.add(ReturnAppKey) },
                modifier = Modifier.safeDrawingPadding(),
              )
            }
            entry<ConnectionKey> {
              ConnectionScreen(
                apiKey = apiKey,
                urlMissing = graph.apiBaseUrl.isEmpty(),
                check = { key -> ApiClient(graph.apiBaseUrl, key, current.userName).checkKey() },
                save = { graph.apiKeys.save(it) },
                modifier = Modifier.safeDrawingPadding(),
              )
            }
            entry<UserKey> {
              UserScreen(current.userName, { name -> scope.launch { graph.settings.update(current.copy(userName = name)) } }, Modifier.safeDrawingPadding())
            }
            entry<ReturnAppKey> {
              var apps by remember { mutableStateOf<List<LaunchableApp>>(emptyList()) }
              LaunchedEffect(Unit) { apps = graph.launcher.launchableApps() }
              ReturnAppScreen(current, apps, { next -> scope.launch { graph.settings.update(next) } }, Modifier.safeDrawingPadding())
            }
          },
        )
        Column(Modifier.fillMaxSize()) {
          AskOverlay(state, System::currentTimeMillis, graph.controller::stopRecording, graph.controller::cancel)
        }
      }
    }
  }
}
```

`app/src/main/AndroidManifest.xml`（全体を置き換える）:

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

  <uses-permission android:name="android.permission.INTERNET" />
  <uses-permission android:name="android.permission.RECORD_AUDIO" />
  <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />
  <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
  <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
  <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
  <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />

  <!-- The return-app list (SC-10) and launching the nav app need to see launcher activities. -->
  <queries>
    <intent>
      <action android:name="android.intent.action.MAIN" />
      <category android:name="android.intent.category.LAUNCHER" />
    </intent>
  </queries>

  <application
    android:name=".TouringApp"
    android:allowBackup="false"
    android:icon="@mipmap/ic_launcher"
    android:label="@string/app_name"
    android:roundIcon="@mipmap/ic_launcher_round"
    android:supportsRtl="true"
    android:theme="@style/Theme.TouringV2">
    <activity
      android:name=".MainActivity"
      android:exported="true"
      android:launchMode="singleTask"
      android:windowSoftInputMode="adjustResize">
      <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
      </intent-filter>
      <!-- The intercom's assistant button (adr/0005 keeps the slice 1 hands-free entry). -->
      <intent-filter>
        <action android:name="android.intent.action.VOICE_COMMAND" />
        <category android:name="android.intent.category.DEFAULT" />
      </intent-filter>
    </activity>
    <service
      android:name=".service.RideForegroundService"
      android:exported="false"
      android:foregroundServiceType="microphone|mediaPlayback" />
  </application>

</manifest>
```

- [ ] **Step 4: すべての JVM テストとビルドを通す**

Run: `cd $AND && ./gradlew testDebugUnitTest assembleDebug`
Expected: `BUILD SUCCESSFUL`。JVM のテストは合わせて114件（`ToolingTest` 1件を含む）。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/TouringApp.kt \
  app/src/main/java/com/touringproject/v2/MainActivity.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt \
  app/src/main/AndroidManifest.xml app/src/test/java/com/touringproject/v2/MainActivityTest.kt
git commit -m "feat: wire the app together and receive the intercom button"
```

---

### Task 11: エミュレーターでの通し

**Files:**
- Create: `app/src/androidTest/java/.../VoiceCommandTest.kt`
- Modify: `README.md`（「エミュレーター」の節を足す）

**Interfaces:**
- Consumes: `TouringApp.graph`・`controller.runsStarted`・`state`（Task 10）

確かめること（spec §8.1 の 4a #1・4b #9）: アプリを閉じた状態からインカムの合図（`VOICE_COMMAND`）で起動すると一巡が1回だけ始まり、Activity を作り直しても増えない。戻るで閉じたあとの合図で、もう1回だけ始まる。接続キーが無いので、一巡は「接続キーを確かめてください」ですぐ終わる。

- [ ] **Step 1: エミュレーターを用意する**

```bash
df -h /   # 空きが 5GB 以上あること（端末イメージ約 2.3GB）
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator list
# medium_phone が無ければ作る（Android 36 の Google Play 入りの端末イメージを取りに行く）
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator create medium_phone
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
$SDK/platform-tools/adb devices   # emulator-5554 device
```

- [ ] **Step 2: 失敗するテストを書く**

`app/src/androidTest/java/com/touringproject/v2/VoiceCommandTest.kt`:

```kotlin
package com.touringproject.v2

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.os.SystemClock
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import com.touringproject.v2.ask.Phase
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

// On the emulator: the intercom's assistant button arrives as VOICE_COMMAND and starts exactly one ask
// (4a #1 and 4b #9 of the slice 1 checklist). Without an API key the ask ends at once with "no key".
// MainActivity is singleTask, which ActivityScenario cannot follow, so the activity is started directly.
@RunWith(AndroidJUnit4::class)
class VoiceCommandTest {
  private val instrumentation = InstrumentationRegistry.getInstrumentation()
  private val app = ApplicationProvider.getApplicationContext<TouringApp>()

  @Before
  fun grantPermissions() {
    listOf(
      Manifest.permission.RECORD_AUDIO,
      Manifest.permission.ACCESS_FINE_LOCATION,
      Manifest.permission.ACCESS_COARSE_LOCATION,
      Manifest.permission.BLUETOOTH_CONNECT,
      Manifest.permission.POST_NOTIFICATIONS,
    ).forEach { instrumentation.uiAutomation.grantRuntimePermission(app.packageName, it) }
  }

  @After
  fun closeActivity() {
    resumed()?.let { activity -> instrumentation.runOnMainSync { activity.finish() } }
  }

  private fun voiceCommand() = Intent(app, MainActivity::class.java)
    .setAction(Intent.ACTION_VOICE_COMMAND)
    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

  private fun waitUntil(timeoutMs: Long = 20_000, condition: () -> Boolean) {
    val deadline = SystemClock.uptimeMillis() + timeoutMs
    while (!condition()) {
      check(SystemClock.uptimeMillis() < deadline) { "condition never became true" }
      SystemClock.sleep(50)
    }
  }

  private fun runs(): Int {
    var n = 0
    instrumentation.runOnMainSync { n = app.graph.controller.runsStarted }
    return n
  }

  private fun resumed(): Activity? {
    var activity: Activity? = null
    instrumentation.runOnMainSync {
      activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).firstOrNull()
    }
    return activity
  }

  @Test
  fun one_press_starts_one_ask_even_when_the_activity_is_recreated() {
    val before = runs()
    app.startActivity(voiceCommand())
    waitUntil { runs() == before + 1 }
    waitUntil { resumed() is MainActivity }
    val activity = resumed()!!
    instrumentation.runOnMainSync { activity.recreate() }
    waitUntil { resumed().let { it is MainActivity && it !== activity } }
    SystemClock.sleep(1_000)
    assertEquals(before + 1, runs())
  }

  @Test
  fun a_press_after_back_starts_one_more_ask() {
    val before = runs()
    app.startActivity(voiceCommand())
    waitUntil { runs() == before + 1 }
    waitUntil { resumed() is MainActivity }
    // The ask screen swallows Back, so wait for the "no key" message to end first.
    waitUntil { app.graph.state.value.phase == Phase.IDLE }
    // Back closes the activity but the process stays (4b #9).
    val activity = resumed() as MainActivity
    instrumentation.runOnMainSync { activity.onBackPressedDispatcher.onBackPressed() }
    waitUntil { activity.isDestroyed || activity.isFinishing }
    app.startActivity(voiceCommand())
    waitUntil { runs() == before + 2 }
    SystemClock.sleep(1_000)
    assertEquals(before + 2, runs())
  }
}
```

- [ ] **Step 3: テストを通す**

Run: `cd $AND && ./gradlew connectedDebugAndroidTest`
Expected: `BUILD SUCCESSFUL`、2件通る（結果は `app/build/outputs/androidTest-results/connected/debug/`）。
`ActivityScenario` で書くと「Activity never becomes requested state」で失敗する（`singleTask` を追えない）。このテストは Activity を直接起動している。
手でも確かめられる:

```bash
$SDK/platform-tools/adb install -r -g app/build/outputs/apk/debug/app-debug.apk
$SDK/platform-tools/adb logcat -c
$SDK/platform-tools/adb shell am start -W -a android.intent.action.VOICE_COMMAND -n com.touringproject.v2/.MainActivity
$SDK/platform-tools/adb logcat -d -s trv2.ask   # RECORDING → FAILED(NO_KEY) → IDLE が1回ずつ
```

- [ ] **Step 4: README に足してコミットし、エミュレーターを止める**

`README.md` の「テスト」の節の後ろに足す:

````markdown
## エミュレーター

```sh
SDK=$HOME/Library/Android/sdk
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator create medium_phone   # 初回だけ
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator start medium_phone
./gradlew connectedDebugAndroidTest
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

インカムの合図は `adb shell am start -a android.intent.action.VOICE_COMMAND -n com.touringproject.v2/.MainActivity` で送れる。
````

```bash
cd $AND && git add app/src/androidTest/java/com/touringproject/v2/VoiceCommandTest.kt README.md
git commit -m "test: start one ask per intercom press on the emulator"
$SDK/cmdline-tools/latest/bin/android --no-metrics emulator stop medium_phone
```

---

### Task 12: 実機の確認（インカムでの一巡）

**Files:** なし（結果は ledger に残す）

spec §8.2 の「4a #1〜#3」を、ネイティブ版で確かめる。音量の聞き比べ・試し録り・SCO 中の警告・走行用のビルドは計画2で確かめる。

- [ ] **Step 1: API の URL を入れてビルドする**

```bash
cd $AND
URL=$(AWS_PROFILE=touring aws cloudformation describe-stacks --region ap-northeast-1 --stack-name stack-trv2-dev-backend \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
grep -q '^trv2.apiBaseUrl=' local.properties || printf 'trv2.apiBaseUrl=%s\n' "$URL" >> local.properties
./gradlew assembleDebug
```

`AWS_PROFILE=touring` が使えないときは、利用者に URL の入れ方を聞く（URL をチャットに出さない）。

- [ ] **Step 2: 【利用者の作業】React Native 版を外し、ネイティブ版を入れる**

React Native 版とネイティブ版は署名の鍵が違うので、上書きできない。React Native 版の設定（接続キー・ユーザー名・戻り先）は消える。スライス1の走行での判定を React Native 版で済ませたいときは、先に済ませてから進める（利用者に確かめる）。

```bash
$SDK/platform-tools/adb uninstall com.touringproject.v2
cd $AND && ./gradlew installDebug
```

- [ ] **Step 3: 【利用者の作業】初期の設定**

1. アプリを開き、権限（マイク・位置・近くのデバイス・通知）をすべて許可する
2. ホームの黄色い帯 → 接続の設定 → 接続キーを入れて「確かめて保存」（キーは Backend の README の手順で読む。チャットに出さずに `adb shell input text` で入れる方法を相談する）
3. 帯 → 応答後に戻るアプリ → ナビのアプリを選ぶ（戻るタイミングは「送ったらすぐ」）

- [ ] **Step 4: 【利用者の作業】確認リスト**

停車した状態で、マップでナビを始めてから行う。結果を ✓/✗ で教えてもらう。

| # | 操作 | 期待 |
|---|---|---|
| 1 | アプリを閉じた状態でインカムのボタンを押す | アプリが開き、赤い画面と開始の合図。インカムのマイクで録れている（黄色の警告が出ない） |
| 2 | 「右手に見える山は何？」と話し、もう一度ボタンを押す | 送った合図が鳴り、すぐマップに戻る |
| 3 | そのまま待つ（画面を消してもよい） | 数秒ごとに待っている合図。回答がインカムから聞こえる |
| 4 | 続けてボタンを押し「さっきの質問をもう一度短く」 | 前の話を踏まえて答える（自動のテストでも確かめているが、通しで一度見る） |

✗ があれば `adb logcat -s trv2.ask trv2.route trv2.ride` の出力と合わせて、`superpowers:systematic-debugging` で原因を調べる。

- [ ] **Step 5: 記録する**

結果の表を ledger に残す（コミットはしない）。

---

### Task 13: 親の文書と写し

**Files:**
- Modify（親）: `docs/05_technical_policies.md`（§6 の App の行・§9 の背面での動作の行）、`README.md`（ユニットの表・submodule の手順・写す手順）、`CLAUDE.md` は変えない
- Create（Android）: `docs-parent/`（`scripts/sync-docs.sh` で写す）

06・07 のユニットの名前（App → Android）と、submodule `App/` を外すことは、計画2で行う（React Native 版を移行の終わりまで残すため）。

- [ ] **Step 1: 05 を直す**

`docs/05_technical_policies.md` §6 の App の行を置き換える:

```markdown
| App | Kotlin・Jetpack Compose（Android ネイティブ）。リポジトリは `TouringProjectV2_Android` | インカムの経路・常駐・ナビへの復帰がネイティブの機能で、つなぎ目の無い一つの言語のほうが自動のテストで確かめやすい（[adr/0005](../adr/0005-native-android-app.md)） |
```

§9 の背面での動作の行を置き換える:

```markdown
| 背面での動作 | 回答の待ち受け・読み上げは決定済み（[adr/0004](../adr/0004-background-processing.md)。ネイティブ版では一巡をコルーチンで動かし、前面サービスでプロセスを生かす。[adr/0005](../adr/0005-native-android-app.md)）。ルートの記録を背面で続けられるかは、走行の記録を作るときに実機で確かめる |
```

- [ ] **Step 2: 親の README を直す**

ユニットの表に行を足す（`App/` の行の下）:

```markdown
| `Android/` | Android アプリ（Kotlin・Jetpack Compose）。`App/` からの移行中（[adr/0005](adr/0005-native-android-app.md)） | `TouringProjectV2_Android` |
```

`git submodule update --init` と `scripts/sync-docs.sh` の例の行に `Android` を足す。

- [ ] **Step 3: 文書を写してコミットする**

Android はこの計画のブランチに、関わらないユニット（App・Backend・Agent・CICD）は main に直接コミットする（PROJECT.md の「前提」）。

```bash
cd $ROOT && git add docs/05_technical_policies.md README.md
git commit -m "docs: record the native app in the technical policies"
scripts/sync-docs.sh Android App Backend Agent CICD
cd $AND && git add docs-parent && git commit -m "docs: sync parent docs"
for u in App Backend Agent CICD; do
  (cd $ROOT/$u && git switch main && git add docs-parent && git commit -m "docs: sync parent docs")
done
cd $ROOT && git add Android App Backend Agent CICD && git commit -m "chore: bump units for synced parent docs"
```

ユニットの main への写しの push は、ほかの push と一緒に利用者が行う。
