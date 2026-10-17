# ネイティブ移行 設計: App を Kotlin で作り直し、スライス1と同じ振る舞いに戻す

- 日付: 2026-10-17
- 状態: 承認待ち（利用者のレビュー）
- 決定の経緯: [adr/0005](../../adr/0005-native-android-app.md)
- 振る舞いの正: [スライス1の設計](2026-10-16-slice1-design.md) §5・§8、PROJECT.md の「持ち越し」

## 1. 目的と成功の判定

App を React Native から Kotlin・Jetpack Compose に移し、新しいリポジトリ `TouringProjectV2_Android` で作る。**振る舞いはスライス1の App と同じにし、新しい機能は足さない。** 配線を確かめる項目を自動のテストに移し、利用者の実機での確認を、体で確かめるしかない項目に絞る。

成功の判定:

- [ ] §8.1 の自動で確かめる項目が、`./gradlew test` か `./gradlew connectedAndroidTest` で通る
- [ ] §8.2 の利用者の確認が、実機ですべて ✓
- [ ] 親の文書（05・06・07・CLAUDE.md・PROJECT.md・ADR）が、新しいリポジトリと技術に合っている

ネイティブ版の走行用のビルドで実際に走ることは、判定に入れない（スライス2の走行で兼ねる）。

## 2. 範囲

### 含める（スライス1の App と同じ振る舞い）

| 分類 | 内容 |
|---|---|
| ハンズフリーの一巡 | インカムのボタンの合図（`VOICE_COMMAND`）で起動・2回目の押下で送る・インカムのマイクへの経路・PCM での録音と送信・ポーリング・回答の再生・ナビへ戻る・合図の音・失敗の理由ごとの知らせ（スライス1 §8.1） |
| 状況 | 会話の文脈（15分・新しい会話）、位置と方位の材料 |
| 画面 | ホーム（スライス1の最小限）・対話（SC-03）・設定（SC-09）・応答後に戻るアプリ（SC-10）・録音の確認（SC-12）・接続の設定（SC-13）・ユーザー名（SC-18）・回答の音量（SC-21）・DL-01・DL-02・メディアの音量の警告の帯 |
| ビルド | 開発用のビルドと、走行用のビルド（release） |

### 含めない

- 新しい機能（スライス2以降）
- React Native に固有の回避策（`setAudioModeAsync` がスピーカーに固定する問題・背面で `setTimeout` が止まる問題）。ネイティブ版では起きない作りにする
- React Native 版の設定・接続キー・残した録音の引き継ぎ（入れ直す）

## 3. リポジトリ

- 新しく `TouringProjectV2_Android` を作り、親の submodule `Android/` として足す（`gh repo create` まで。push は利用者）
- 旧 `App/` は移行を終えるまで submodule のまま残す（移植の元・移行のあいだのスライス1の走行での判定に使う）。移行を終えたら、親から `App/` を `git rm` で外し、GitHub のリポジトリはアーカイブする
- React Native 版の App の issue #10〜#13 は React Native の作りに固有の不具合なので、移行を終えるときに「移行で解消」として閉じる。同じことが起きないかは §8 の中で見る
- パッケージ名は `com.touringproject.v2` のまま。署名の鍵が React Native 版と違うので、ネイティブ版を入れる前に React Native 版をアンインストールする

## 4. 技術の選択

| 対象 | 採用 | React Native 版で使っていたもの |
|---|---|---|
| 言語・UI | Kotlin・Jetpack Compose・Navigation Compose | TS・React Native・expo-router |
| ビルド | Gradle（Kotlin DSL・version catalog）・Gradle 9.4.1。minSdk 29（Android 10）、targetSdk は最新の安定版 | Expo の prebuild |
| 録音 | `AudioRecord`（PCM・16kHz・モノラル・16bit） | expo-audio |
| 再生 | Media3 ExoPlayer（URL から再生・背面） | expo-audio |
| 端末の読み上げ（`tts_failed` のとき） | `TextToSpeech` | expo-speech |
| 位置 | `FusedLocationProviderClient` | expo-location |
| 設定 | DataStore | AsyncStorage |
| 接続キー | Android Keystore で暗号化して DataStore に置く | expo-secure-store |
| 通信 | OkHttp・kotlinx.serialization | fetch |
| 部品の組み立て | 手で組む（DI のライブラリは入れない） | — |
| テスト | JUnit・kotlinx-coroutines-test・MockWebServer・Robolectric・Compose の UI テスト・エミュレーター | Jest |

今の Kotlin（`handsfree`・`audio-route`・`ride-service`）は、Expo Modules の定義を外して普通のクラスとして移す。App の README の「大事な決まり」のうち Android に関わるもの（インカムは音の出だしを落とすので合図は長さを指定できる音で長めに鳴らす・`TONE_PROP_*` は約0.16秒で止まる・開始の合図は録音が始まってから鳴らす・前面サービスで生かす・マナーモードでも鳴らす）は引き継ぐ。

## 5. 構成

1つの Gradle モジュール `app` の中で、パッケージに分ける。

| パッケージ | 役割 | テスト |
|---|---|---|
| `ask` | 一巡の状態機械（純粋な Kotlin）・司令塔・ポーリング・会話の区切り・失敗の理由から読み上げる文 | JUnit |
| `api` | Backend の API（`Backend/openapi.yaml`） | MockWebServer |
| `audio` | 録音・再生・インカムへの経路・合図の音・メディアの音量 | Robolectric（作り物の AudioManager）。実際の音は実機 |
| `handsfree` | `VOICE_COMMAND` の受け口・押下の受け渡し | Robolectric で Intent を送る |
| `service` | 前面サービス（一巡のあいだ生かす）・ナビを開く | Robolectric |
| `location` | 位置の監視・方位の材料の選び方 | JUnit・Robolectric |
| `settings` | DataStore・接続キー | Robolectric |
| `ui` | Compose の画面 | Compose の UI テスト |

作りの決まり:

- 状態機械は Android に依存しない。録音・通信・再生・時間は interface を通して受け取り、テストでは作り物に差し替える（React Native 版の `flow.ts` と `controller.ts` の分け方を引き継ぐ）
- 時間はコルーチンの `delay` を使い、テストでは仮想の時間で進める（120秒の打ち切りも一瞬で確かめる）
- 一巡は前面サービスの中のコルーチンのスコープで動かす。画面は状態を `StateFlow` で受けて描くだけ
- React Native 版の Jest のテストは、確かめていた振る舞いの一覧として使い、同じ振る舞いを Kotlin のテストで書き直す

## 6. 開発環境

- Android Studio・SDK・JDK 17・Command-line Tools（`android` CLI）は入っている
- エミュレーター（`system-images;android-36;google_apis;arm64-v8a`。データの領域は小さめ）は plan 1 で作る。ディスクの空きが少ないので、作る前に空きを確かめる
- AI は `./gradlew test`（端末は要らない）と `./gradlew connectedAndroidTest`（エミュレーター）を自分で回す。利用者に実機を頼むのは §8.2 と各 plan の終わりの確認だけ

## 7. 進める順番

| plan | 中身 |
|---|---|
| 1 | 土台と、ハンズフリーの一巡。リポジトリと雛形・テストの道具・エミュレーター・今の Kotlin の移植・一巡の状態機械・API・前面サービス・最小限のホームと SC-03・接続の設定。最後に、インカムでの一巡を利用者が実機で確かめる |
| 2 | 残りの画面と仕上げ。設定の各画面・SC-12・SC-21・音量の警告・DL・走行用のビルド・親の文書と submodule の整理。最後に、残りの利用者の確認 |

## 8. 完了の判定の振り分け

スライス1の利用者の確認リスト（plan 4a Task 15 の #1〜#9、plan 4b Task 13 の #1〜#10 と走行用のビルド）と「持ち越し」を、自動で確かめるものと、利用者が確かめるものに分ける。

### 8.1 自動で確かめる

| 元の項目 | 確かめ方 |
|---|---|
| 4a #1・4b #9 閉じた状態・戻るで閉じた状態からの起動で、質問が1回だけ始まる | エミュレーターで `VOICE_COMMAND` の Intent を送る |
| 4a #2 送ったあとナビへ戻る | Robolectric（ナビを開く Intent が出る） |
| 4a #3 画面を離れても回答を待ち、再生する | Robolectric（サービスの中で一巡が続く） |
| 4a #4 続けての質問で `conversationId` を送る | JUnit・MockWebServer（文脈そのものは Backend の smoke で確かめ済み） |
| 4a #5 回答待ちの押下で「いま応答中です」 | JUnit（状態機械） |
| 4a #6 画面の「押して話す」 | Compose の UI テスト |
| 4a #7 録音中に「送らずにやめる」で何も送らない | JUnit・MockWebServer |
| 4a #8 通信できないときの失敗の知らせ | JUnit・MockWebServer |
| 4a #9 新しい会話で `conversationId` を捨てる | JUnit |
| 4b #2 メディアの音量が低いと帯が出る | Robolectric（作り物の AudioManager）・Compose の UI テスト |
| 4b #4 試し録り中の押下で質問を始めない | JUnit |
| 4b #5 送った録音の一覧 | JUnit・Compose の UI テスト |
| 4b #6 SC-12 を離れても読み上げが続く | Robolectric |
| 4b #7 録音をすべて消す | JUnit・Compose の UI テスト |
| 4b #10 録音の再生中の押下で再生を止めて質問を始める | JUnit |
| 持ち越し: release の権限 | `aapt2 dump permissions` で、要らない権限が入っていないことを確かめる |

### 8.2 利用者が実機で確かめる

| 元の項目 | 操作と期待 |
|---|---|
| 4a #1〜#3 | ナビを出した状態で、アプリを閉じてインカムのボタンを押す → 赤い画面と開始の合図、インカムのマイクで録れている → 話してもう一度押す → 送った合図とナビへ戻る → 回答がインカムから聞こえる（画面を消しても） |
| 4b #1 | 回答の音量を +0・+3・+6 で聞き比べ、差が分かる。+6 がナビの案内と比べて聞き劣りしない |
| 4b #3 | 試し録りで、話した声がインカムから聞こえ、録ったマイクが「インカム」と出る |
| 持ち越し: SCO 中のメディアの音量 | インカムで質問した直後にホームへ戻っても、メディアの音量の警告が誤って出ない |
| 走行用のビルド | USB を外して、4a #1〜#3 をもう一度通す |

## 9. 文書とほかのユニット

各 plan で、関わる変更と同じコミットで直す。

- 05 §6（App の技術）・§9（背面での動作）
- 06・07: ユニットの名前を App から Android に替える。UC-9 の配布の書き方
- 親の CLAUDE.md・PROJECT.md・README・`scripts/sync-docs.sh` を使う手順: submodule `Android/` を足し、移行を終えたら `App/` を外す
- Backend・Agent・CICD は変更しない（API は同じ）

## 10. スライス2との関係

- 本書のレビューが済んだら、[スライス2の設計](2026-10-17-slice2-design.md) の技術の節（§3・§4.2〜4.5・§5.1・§7.1・§9・§11）をネイティブ前提に直し、改めてレビューを受ける（前面サービスの中で位置を受けて Room に書く・AlarmManager で締め切りを判定する、など）
- スライス2の位置の確かめ（長時間の点の抜け・電池）は、スライス2の plan 1 にスパイクとして残す

## 11. 未確定事項

| 論点 | 決め方 |
|---|---|
| targetSdk の具体的な版 | plan 1 で、入っている SDK（platform 36・37）と依存のライブラリの対応を見て決める |
| 走行用のビルドの署名の鍵 | plan 2 で決める（開発用の鍵のままにするか、release の鍵を作るか。鍵はリポジトリに入れない） |
