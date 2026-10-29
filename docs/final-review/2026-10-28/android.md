# Android の指摘

Android（`Android/`）と、それに対応する文書（`docs/02`・`03`・`04`・`08a`・`mock` など）についての指摘。観点は A（不具合）・B（脆弱性）・C（細部）・D（文書の整合）。
件数は 42 件（High 1・Medium 7・Low 28・Info 6）。
構成（観点 S）の指摘は `structure.md` に集めてあり、ここには載せない。パス `Android/app/src/main/java/com/touringproject/v2/` は `main/`、`Android/app/src/test/java/com/touringproject/v2/` は `test/` と略す（R3 の指摘は元のパスのまま）。

## High

### R3-01 [A] [High] [確か] SC-19（地点メモ）を開いたまま背面に回すと、走行中のインカムの押下が質問にならず、ナビの上に SC-19 が出て声の入力が始まる

- 場所: `Android/app/src/main/java/com/touringproject/v2/ui/RecordsRoutes.kt` の `voiceUi()`（163〜173行）、`handsfree/PressRouter.kt` の `press()`（25〜37行）、`voice/VoiceInput.kt` の `attach()`（99〜103行）、`ui/AppUi.kt` の `NewNoteKey`・`NoteKey` の entry（232〜237行）、`AppGraph.kt` の `voiceAttached`（337行）、`MainActivity.kt` の `handleVoiceCommand()`
- 内容: 声の入力を SC-19 に「付ける」のは `DisposableEffect` で、外すのは SC-19 の composition が捨てられたとき（`RecordsRoutes.kt` 164〜173行の後始末）だけ。Activity が止まっても（ホームボタン・アプリの切り替え・画面の消灯）composition は残り、`MainActivity` に `onStop` の処理は無いので、`VoiceInput.attached` は true のまま。`PressRouter.press()` は `voiceAttached() && !askBusy()` なら質問でなく `voicePress()` へ回す。インカムのボタンの押下は `VOICE_COMMAND` として `MainActivity` を前面に出すが、`handleVoiceCommand` は画面の積み重なりを戻さず押下を渡すだけなので、ナビの代わりに SC-19 が前面に出て、開始の合図のあと声の録音（60秒まで）が始まる。質問は始まらず、回答も読み上げず、ナビへも戻らない。
- 起きる条件: 走行の記録中に停車して「📝 地点メモ」を開き（または記録タブから既存の地点メモを開き）、保存・✕ をせずにホームボタンや「最近使ったアプリ」でナビへ切り替える、または画面が消える。そのまま走り出してインカムのボタンを押す。
  1. 記録中にホームの「📝 地点メモ」を押す
  2. 何も保存せずにホームボタンでナビを開く
  3. インカムのボタンを押す → アプリが前面に出て SC-19 の「■ 止めて文字にする」になり、質問の一巡は始まらない
- 影響: 走行中に画面がナビから SC-19 に切り替わり、話した質問は答えられず地点メモの入力欄に入る。手で SC-19 を閉じてナビに戻すまで、インカムのボタンは何度押しても声の入力になる（走行中は操作できない）。停車中のメモの途中で走り出すのは普通の使い方で起きうる。
- 対応案: 声の入力を付けるのを「SC-19 が前面で操作できるあいだ」に限る。`voiceUi()` で `LocalLifecycleOwner` の lifecycle を見て、`repeatOnLifecycle(Lifecycle.State.RESUMED)` の中で `attach()`、抜けたら（`ON_PAUSE`）`detach(token)` する。`STARTED` でなく `RESUMED` にするのは、止まった Activity に `onNewIntent` と `onStart` のどちらが先に届くかの保証が弱く、`onNewIntent` のあとには必ず `onResume` が来るため。背面に回ったときに録音中なら止めて捨てる（`detach` が既にそうする）。仕様の「SC-19 を開いているあいだ」（03 §2・モックの SC-19・README）を「SC-19 を前面に表示しているあいだ」と読めるように直す。テスト: `AppUiTest` で SC-19 を開き、Activity を `moveToState` で RESUMED より下（`STARTED` か `CREATED`）に下げてから `graph.presses.offer` すると、`VoiceInput.attached` が false で質問の司令塔に届く（作り物の窓口で press を数える）。あわせて、画面の回転などの構成の変更でも SC-19 の composition が作り直され、`detach` → `cancel()` で録音中の声の入力が捨てられる（`ui/RecordsRoutes.kt` 166〜169行。マニフェストに `configChanges` も向きの固定も無い）。同じところを触るので、一緒に扱う（単独なら Low）。
- 関わる文書: `docs/03_screen_transition.md` §2 の最後の箇条、`docs/mock/index.html` の SC-19「入力」、`Android/README.md` の SC-19 の決まり

## Medium

### R1-01 [A] [Medium] [確か] 取り消した質問の後始末が、すぐ始めた次の質問の位置と経路を壊す

- 場所: `main/ask/AskController.kt` の `record()`（309〜372行。とくに 322〜326行と 343〜346行）、`cancel()`（97〜106行）。共有される `main/location/PositionTracker.kt` の `begin()`・`end()`（39〜58行）と `main/audio/AudioRoute.kt` の `startVoiceRecognition()`（110〜114行）・`stopVoiceRecognition()`（56〜60行）
- 内容: `cancel()` は `runId` を進めて状態を IDLE にするだけで、走っている `run()` の待ち（経路の準備）は止めない。その間に次の質問が始まると、次の `run()` は `d.location.begin()` で位置の監視を始め直し、`d.route.start()` を呼ぶ。そのあとで古い `run()` の `route.start()` が返ると、`!isCurrent(run)` の後始末で `d.route.stop()` と `d.location.end()` を呼ぶ。
  - 位置の監視を持つ `PositionTracker` は質問の司令塔に1つ（`AppGraph.kt` 260行）で、`end()` は呼び手を区別せずに世代を進め、監視を外し、集めた位置を捨てる。次の質問の監視が外れ、録音を終えたときの `end()` は null を返す。質問は位置なし・方位なし（`d.heading(null)` は `NO_POSITION`）で送られる。
  - 質問の司令塔の `AudioRouteControl` は1つ（`AppGraph.kt` 253行）で `source` をフィールドに持ち、古い run の `stop()` が `source = null` にするので、新しいインカムの run の最後の `stop()` が `releaseSco()` に流れる。
  - インカムのボタンの経路では、古い質問の音声認識の準備が終わっていない（`vrPending != null`）ので、次の質問の `startVoiceRecognition` は `"already starting"` で失敗し、本体のマイクで録る（`PhoneMic`）。続く古い `route.stop()` → `stopVoiceRecognition` が `MODE_NORMAL` に戻す。
  - 録音中の取り消しでも、古いループが `TICK_MS`（250ms）の眠りから覚める前に次の質問が始まれば、古い `route.stop()` が次の質問の `vrPending` を `false` で終わらせる（同じく本体のマイクになる）。
  - 試し録り（`TrialController.busy`）と声の入力（`VoiceInput.busy`）には「片付くまで次を始めない」守りがあるが、質問の司令塔自身には無い。
- 起きる条件: インカムのボタンで質問を始め、経路の準備（音声認識は最大4秒・画面からは最大3秒）のあいだに画面の大きなボタンで取り消し、その準備が終わる前にもう一度インカムのボタン（または「押して話す」）を押す。誤って押した直後に取り消して押し直す、という流れで起きうる。
- 影響: 次の質問がヘルメットの中の声を拾えない本体のマイクで録られ「聞き取れませんでした」になりやすい。聞き取れても、位置・方位なしで AI に渡り、記録にも地点が残らない（地図に出ない）。走行中に起きると、もう一度聞き直す必要がある。
- 対応案: 質問の司令塔にも「前の run が片付くまで」の印を持たせ（`TrialController.running` と同じ形）、`press()`・`tapToTalk()`・`askText()` はそのあいだ始めない（声の入力と同じく失敗の合図を鳴らす）。あわせて `Positions` を世代の札で扱う（`begin()` が札を返し、`end(token)` はその札のときだけ効く）と、取り違えが型で防げる。テスト: Harness の `routeStart` を門（`CompletableDeferred`）で止め、取り消し → 次の `press()` → 門を開ける、の順で、(1) 次の質問が始まらない（または失敗の合図）こと、(2) 札つきの `Positions` の作り物で、古い run の `end` が新しい run の位置を消さないこと、を確かめる。今の Harness の `location.end()` は定数 `HERE` を返すので、この食い違いを捉えられない。
- 確度の根拠: コードで追えた。実機では未確認。
- 同じ根: R1-03（取り消しの後始末が `AudioRoute` の中で続く点）・R10-01（利用者をまたぐ音声の経路の共有。`structure.md`）

### R1-02 [A] [Medium] [ありうる] 端末の音声合成が終わりを知らせないと、読み上げ中のまま止まり、インカムのボタンが効かなくなる

- 場所: `main/audio/TtsSpeech.kt` の `say()`（34〜44行）、`main/ask/AskController.kt` の `speak()`（465〜482行。470行の `busySpeech?.await()` と 480行）・`press()`（69〜77行。73行）
- 内容: `TtsSpeech.say()` は `UtteranceProgressListener` の `onDone`・`onError`・`onStop` を待つだけで、上限が無い。音声合成のエンジンが落ちる（別プロセスのエンジンが終了させられる）などで知らせが来ないと、`say()` は返らない。`speak()` はすでに `Answered` を出して状態が `SPEAKING` なので、`press()` は 73行で何もしない。`isBusy` も true なので「押して話す」も始まらない。抜け出す手は画面の大きなボタン（`cancel()` が `speech.stop()` で待ちを放す）だけ。`sayBusy()` の読み上げが返らない場合も、`speak()` が 470行で待ち続けて同じになる。前面サービス（マイクと再生の種類）も止まらない。
- 起きる条件: 回答の音声（Polly）を再生できず端末の音声合成で読む（`tts_failed`・再生の失敗・止まった再生）か、回答待ちに押して「いま応答中です」を読んでいるあいだに、音声合成のエンジンが知らせを返さなくなる。エンジンの落ち方しだいで、頻度は低い。エンジンが知らせを落とす条件は確かめていない。
- 影響: ナビに戻ったあと、インカムのボタンを何度押しても何も起きず、音の合図も無い。走行中は画面に触れられないので、停車するまで質問できない（走行中にアプリが使えなくなる）。
- 対応案: `say()` に上限を設ける（文字数から見積もった長さ＋余裕、たとえば `withTimeoutOrNull(len * 300ms + 5s)`。切れたら `tts.stop()` して返る）。あわせて `TextToSpeech` の初期化が成功しなかったときに作り直す手を検討する。テスト: `Speech` の作り物が返らない `say` で、`AskController` が上限のあとに IDLE へ戻り次の `press()` が質問を始めること（上限を `AskDeps` か `TtsSpeech` の引数で短くして確かめる）。

### R2-01 [A] [Medium] [確か] 設定を読めなかった起動で、ランダムなユーザー名が保存され、端末の記録が別のユーザー名で送られる

- 場所: `Android/app/src/main/java/com/touringproject/v2/settings/SettingsRepository.kt` の `load()`（48〜53行）、`settings/Settings.kt` の `decodeSettings()`（99〜126行）
- 内容: `load()` は `guard { store.get(SETTINGS_KEY) }` で読み、読み出しが例外（DataStore の `IOException` など）で失敗すると `null` を `decodeSettings` に渡す。`decodeSettings(null)` はユーザー名を `randomUserName()` で作り、`needsSave = true` を返す。`load()` はそれを `guard { store.set(...) }` で**保存する**。読めなかっただけで書けるストアでは、保存されていた本当のユーザー名と設定がランダムな名前と既定値で上書きされる。関数の KDoc（47行）は「for this run」（この起動だけ既定値）と書いているが、実際は永続する。設定ファイルが壊れていた場合（`preferencesDataStore` の `ReplaceFileCorruptionHandler { emptyPreferences() }`、24行）も同じ経路になる。
- 起きる条件: 起動時に DataStore の読み出しが一時的に失敗する、または設定ファイルが壊れている。実機での頻度は確かめていない。
- 影響: Room の記録は前のユーザー名のもののまま、設定のユーザー名だけが黙って新しいランダムな名前に変わる。そのあとの送信（`AppGraph.sync` の `api()` は `settings.settings.value?.userName` を使う）で、未送信の記録とこれからの記録がランダムな名前のほうに送られ、ユーザー名をまたいで記録が分かれる（US-E-06.001・08a §6 が避けようとしている食い違い）。前の名前は端末から消えるので、利用者が控えていなければ戻せない。起きる頻度は低いが、起きたら気づきにくい。
- 対応案: 「値が無い（初めての起動）」と「読めなかった」を分ける。読めなかったときは保存せず、ユーザー名を未確定（`null`）にして送信の `api()` が `null` を返す（送らない）状態にし、SC-09 で知らせる。壊れたファイルへの備えとして、ユーザー名を Room 側にも持つ（記録の持ち主を Room に持つ形。`structure.md` の指摘）と、取り違えを検知できる。テスト: `get` だけが例外を投げ `set` は通る作り物のストアで `load()` を呼び、`set` が呼ばれないこと・`settings.value?.userName` が確定しないことを確かめる。いまの `SettingsTest.a_store_that_cannot_be_read_falls_back_to_defaults`（123〜135行）は `set` も例外を投げるストアなので、この上書きを捉えていない（`errors.size == 3` は load の中の保存も試していることを示している）。
- 同じ根: R2-02（記録の持ち主が Room の外の設定にあること）

### R2-02 [A] [Medium] [確か] ユーザー名の変更が `Mismatched` で終わったあとも送信が止まらず、前の名前の記録が新しい名前に送られる

- 場所: `Android/app/src/main/java/com/touringproject/v2/sync/Takeover.kt` の `switchTo()`（106〜121行）と `start()`（137〜155行）、`AppGraph.kt` の `sync` の `api`（144〜151行）
- 内容: `switchTo` は新しい名前を保存してから `store.take(replace = true)` を呼び、入れられなかったら `putBack` で戻す。戻す保存も失敗すると `TakeResult.Mismatched`（保存された名前は新しい名前、Room は前の名前の記録）になる。`start()` はどの結果でも最後に `sync.request()` を呼び、`RideSync` の `api()` はそのときの設定のユーザー名で `ApiClient` を作るので、Mismatched の状態でも送信の回がそのまま走る。`take` が `Blocked(UNSENT)` を返して戻す保存に失敗した場合は、未送信の記録（前の名前のもの）が直後の回で新しい名前に送られる。`take` が例外で終わった場合も、そのあとの編集（走行の名前・メモ・地点メモ）や新しい走行は新しい名前に送られ、前の名前の記録の一部（メタ情報だけ・メモだけ）が新しい名前のクラウドに置かれる。08a §6 は「読み始めから戻すまでは、送信の回を走らせない（…食い違った名前に届かないため）」としているが、食い違ったまま終わったあとの送信は止めていない。
- 起きる条件: SC-18 でユーザー名を変え、記録を入れられず（未送信があって止まる・Room の書き込みの失敗）、さらに DataStore への戻す保存も失敗する。DataStore の書き込みが続けて失敗する条件（ディスクの空きが無いなど）が要るので、まれ。
- 影響: 2つのユーザー名の記録が混ざる（走行のメタ情報だけが別の名前にある、など）。SC-18 には「名前は変わったが記録は前の名前のまま」と出る（`ui/SavingLabels.kt` 55行）が、送信は続く。
- 対応案: Mismatched を状態として持ち（プロセスをまたぐなら Room か DataStore の別キー）、そのあいだは `RideSync` の `api()` が `null` を返して送らない。次の起動で戻す保存を試し直す。テスト: `TakeoverTest` で `save` の2回目（戻す保存）を失敗させ、`store.take` が `Blocked(UNSENT)` を返す作り物で `switchTo` を走らせ、そのあと `RideSync.pass()` が API を呼ばないことを確かめる。
- 関わる文書: `docs/08a_android-design.md` §6（109行）
- 同じ根: R2-01

### R3-02 [A] [Medium] [確か] SC-04・SC-17 のシートや DL-02 などのダイアログを開いているあいだにインカムで質問すると、SC-03 がその下に隠れる

- 場所: `ui/AppUi.kt` の `AppUi()`（388〜434行。`StartRideSheet`・`EndRideSheet` のあとに `AskOverlay` を同じ Activity の中に描く）、`ui/HomeScreen.kt` の DL-02（153〜162行）、`ui/RecordsScreens.kt` の名前の変更と DL-01、`ui/SettingsScreens.kt` の DL-03・DL-01（接続キー）、`ui/MemoScreen.kt` の破棄の確認
- 内容: `ModalBottomSheet` と `AlertDialog` は別のウィンドウなので、Activity の中に描く `AskOverlay`（SC-03）より上に出る。文字の質問のシートは `state.phase == Phase.IDLE` のときだけ出して避け（`AppUi.kt` 415〜416行のコメントのとおり）、SC-12 の DL-01 は質問が始まると閉じる（`RecordingsScreen.kt` 61行、Android #11）が、ほかのシートとダイアログは避けない。ウィンドウの重なりは `AppUi.kt` 415行のコメントが前提にしている。
- 起きる条件: 停車中に SC-04（走行終了の確認）か DL-02（新しい会話の確認）などを開いたまま、インカムのボタンを押す。シートの外側は SC-03 の色で塗られるが、シートが画面の下半分を覆い、録音中の残り秒数・「送らずにやめる」・回答の文が隠れる。SC-04 の「終了して保存」も押せるまま残る。
- 影響: 停車中の限られた場面だが、SC-03 の「色だけで状態が分かる」（US-B-05.001）・「やめるボタン」（US-B-07）が効かなくなる。走行中に画面に目をやったとき状態が読めない。
- 対応案: SC-03 の表示中（`!tabsShown(state.phase)`）は、AppUi が持つシート（`sheet`）を閉じる（SC-04 は名前の入力を `rememberSaveable` で持つので、質問のあとに開き直す形でもよい）か、文字のシートと同じく描かない。画面ごとのダイアログは、SC-12 と同じく `askBusy` で閉じる共通の仕組み（例: `LocalAskShown` の CompositionLocal を見て `if (shown) return` する小さな包み）にまとめる。テスト: `AppUiTest` で SC-04 を開き、`graph` の質問の状態を録音中にすると `endGo` が無く `overlay` がある。

### R3-03 [A] [Medium] [ありうる] 許可が1つでも足りないと、インカムのボタンでアプリを冷えた状態から起こしたときに許可のダイアログが出て、質問がその答えを待つ

- 場所: `MainActivity.kt` の `onCreate()`（20〜36行）、`AppGraph.kt` の `takePermissionPrompt()`（395〜399行）・`readiness`（350行）、`Readiness.kt` の `openWhenReady()`（34〜38行）、`handsfree/Press.kt` の `PressGate`（23〜44行）
- 内容: プロセスで最初の Activity は、起動の理由にかかわらず5つの許可（マイク・位置2つ・Bluetooth・通知）を求める。全部許可済みならダイアログは出ずにすぐ答えが返るが、1つでも「次回も確認」の状態（1回だけ拒否した・ダイアログを Back で閉じた・「今回のみ」で取り消された）だと、システムのダイアログが出る。押下は `PressGate` が `Readiness` の開くまで預かるので、ダイアログに答えるまで録音が始まらない（60秒を過ぎると押下は古いとして捨てられる）。質問に要るのはマイク（と位置）だけで、通知や Bluetooth の答えを待つ理由は無い。
- 起きる条件: 通知か Bluetooth の許可を1回だけ断っている（または「今回のみ」で許可している）状態で、プロセスが終わっている（端末の再起動のあと・利用者がアプリを閉じた・システムが終了させた）ときに、走行中にインカムのボタンを押す。走行の記録中はサービスがプロセスを保つので、記録中は起きにくい（記録していない・始める前に押したときに起きる）。ダイアログが出る条件は Android の許可の仕組みによるもので、実機では確かめていない。
- 影響: ナビの上に許可のダイアログが出て、手で答えるまでアプリが質問できない。走行の記録中でなければ質問はもともと断られるが、その断りの読み上げもダイアログの答えまで遅れる。
- 対応案: `VOICE_COMMAND` で起きた Activity では許可を求めない（`handleVoiceCommand` が押下を受けたら `permissionsAnswered()` を即座に呼び、ダイアログはランチャーから開いたときだけにする）。足りない許可はホームの帯で知らせる（R3-06）。テスト: `MainActivityTest` で `VOICE_COMMAND` の Intent で起動し、`ShadowApplication` で許可を拒否にしておいても、押下が `PressGate` を通って司令塔に届く。
- 同じ根: R3-06（許可の不足をアプリが知らせないこと）

### R3-04 [A] [Medium] [ありうる] ホームが「スクロールしない・小さめの画面（360×640）で帯が1本出ても収まる」ことを確かめるテストが無く、一時停止中に2行の帯が出ると「新しい会話を始める」が最小の高さを割って切れうる

- 場所: `ui/HomeScreen.kt` の `HomeScreen()`（104〜152行）、`ui/RideScreens.kt` の `RideCard()`（36〜64行）、テスト `ui/ScreensTest.kt`（`@Config(qualifiers = "w412dp-h915dp")` の1か所だけ）
- 内容: ホームは `Column(fillMaxSize)` で詰めて並べ、「新しい会話を始める」だけが `heightIn(min = 76.dp, max = 140.dp)`。足りないときは Column の残りの高さに合わせて 76dp より縮み、26sp の文字が切れる。概算（dp）: 上の余白16＋上のバー48＋帯（「メディアの音量が低く、回答が聞こえないかもしれません」は幅328で2行）70＋走行のカード（一時停止中は説明が2行）約210＋待機の行48＋会話のボタン76＋間隔12×5＋下の余白16 ≈ 544。360×640 の端末で、ステータスバー24・3ボタンのナビゲーションバー48・タブ80 を引いた残りは約488 で、足りない。上のバーも、ユーザー名（等幅22sp・最大20字で約264dp）に重みが無く、2つのボタン（約210dp）が後から残りの幅で測られるので、ユーザー名が長いと「⌨ 文字で質問」が潰れて見えなくなる。文字の大きさの設定を上げると、さらに起きやすい。
- 起きる条件: 小さめの画面か大きめの文字の設定で、走行を一時停止し、音量の帯か「書けなかった質問があります」の帯が出ているとき。ユーザー名が10字ほどを超えると、幅360の画面で上のバーのボタンが潰れる。高さは概算で、実機・テストでは測っていない。
- 影響: 「ホームでいちばん大きな操作」（US-A-04.002）が小さくなり、文字が切れる。ホームは走行中に見る画面（US-B-05.005）。
- 対応案: 走行のカードの一時停止の説明を1行に縮める・帯を1行に収める（文言を短くするか `maxLines = 1` と省略）・ユーザー名に `Modifier.weight(1f, fill = false)` と `maxLines = 1`・`overflow = Ellipsis` を付ける。テスト: `@Config(qualifiers = "w360dp-h640dp")`（帯あり・一時停止中・20字のユーザー名）と、`fontScale` を上げた条件で、`newConversation` の高さが 76dp 以上で、`textAsk` が表示されていること。

## Low

### R1-03 [A] [Low] [ありうる] SC-19 を離れると声の入力の経路の準備がすぐ取り消され、`busy` の守りが効かない（テストは取り消せない前提の作り物）

- 場所: `main/voice/VoiceInput.kt` の `press()`（130〜142行）・`detach()` → `cancel()`（157〜161行）、`main/audio/AudioRoute.kt` の `onMain()`（88〜98行）・`acquireSco()`（287〜324行）・`releaseSco()`（64〜67行）。テストは `test/voice/VoiceInputTest.kt` の作り物の `RouteControl.start`（65〜69行）と `a_press_while_the_run_before_still_unwinds_gets_the_failure_cue`（292〜308行）
- 内容: `cancel()` は `job.cancel()` を呼ぶ。本物の `AudioRouteControl.start` → `AudioRoute.onMain` は `suspendCancellableCoroutine` で、取り消しにすぐ応じる（`NonCancellable` でも `invokeOnCancellation` での後始末でもない）。そのため `finally` の `stopRoute()` がすぐ走り、`running` はすぐ false に戻る。一方、`AudioRoute` の中では準備が続く: 画面のボタン（`Source.SCREEN`）の `acquireSco` は、`releaseSco()` で外されない聞き手と3秒の時間切れ（`onTimeout`）を残し、時間切れで `clearCommunicationDevice()` と `MODE_NORMAL` を実行する。README の「返しきるまで（音声認識の経路の準備は最大4秒で、取り消せない）は `busy`」は本物の振る舞いと違い、テストは作り物の `start` を `NonCancellable` で待たせて「取り消せない」前提を作っているので、本体の振る舞いを確かめていない。
- 起きる条件: SC-19 で「🎤 声で入力」を押し、インカムへの経路が張れるまで（最大3秒）に SC-19 を離れ、その3秒のうちに質問を始める（インカムのボタンか「押して話す」）。古い `acquireSco` の時間切れが、新しい質問の経路を張ったあとで来たとき。インカムの音声認識の経路（`HANDSFREE`）でも、ヘッドセットの窓口を待つ（初回最大1.5秒）・前の SCO が下りるのを待つ（最大1秒）あいだに取り消されると、取り消しのあとで `startVoiceRecognition` が呼ばれ、SCO と `MODE_IN_COMMUNICATION` が誰にも返されずに残る。ただし、次の質問も画面のボタンなら、取り残された `acquireSco` の聞き手は新しい質問の SCO への切り替えで先に落ち着き、時間切れも外れて自然に治る。害が出るのは次の質問がインカムの音声認識の経路のときだけで、取り残される窓も最大1.5秒と最大1秒に限られる。
- 影響: 新しい質問の録音中にインカムのマイクの経路が外れ、本体のマイクに落ちて「聞き取れませんでした」になりうる。後者では、次の質問まで通話の経路が張られたまま残る。条件が重なるので頻度は低い。確かなのは、取り消しがすぐ効くこと・時間切れが残ること・README とテストの前提が本物と食い違うこと。新しい質問が実際に壊れるかは実機で未確認。
- 対応案: どちらかに揃える。(a) 経路の準備を本当に取り消せるようにする: `acquireSco` の聞き手と時間切れを `AudioRoute` のフィールドに持ち、`releaseSco()` で外す。`withHeadset`・`waitAudioOff` の待ちも、取り消されたら `begin` に進まないようにする（`invokeOnCancellation` で印を立てる）。(b) 取り消せない前提を守る: `VoiceInput` は `job.cancel()` でなく `session` を進めるだけにし、`route.start` が返るのを待ってから `stopRoute()` する（試し録りと同じ形）。README の文はどちらかに合わせて直す。テスト: 作り物の `start` を取り消せる門にして、離れた直後の `busy` と、門が開いた（または取り消された）あとに `route:stop` が1回だけ・それより後に経路に触れないことを確かめる。`AudioRoute` 側は Robolectric で、`releaseSco` のあとに時間切れが来ても `clearCommunicationDevice` が呼ばれないこと。札を返すだけの対応（R10-01 の対応案）ではこの件は閉じない。取り消された準備は札を返したあとも `AudioRoute` の中で動き続けるので、`AudioRoute` 側の待ちを本当に取り消せるようにする。
- 関わる文書: `Android/README.md` の「大事な決まり」の SC-19 の声の入力の項（48行）
- 同じ根: R1-01・R10-01（`structure.md`）

### R1-04 [A] [Low] [確か] Backend が受け付けた質問が、回答待ちの 403・404 で終わると、記録が端末に残らない（テストも無い）

- 場所: `main/ask/AskController.kt` の `waitForAnswer()`（438〜443行）、`main/ask/Polling.kt` の `FATAL`（15行）と `pollUntilDone()`（58行）
- 内容: `GET /asks/{askId}` が `INVALID_KEY`・`BAD_REQUEST`・`NOT_FOUND` を返すと `pollUntil` が投げ、`waitForAnswer` は `fail()` して `null` を返す。`d.asks.keep(...)` を通らないので、端末に質問の行が作られない。時間切れ（`PollOutcome.Timeout`）では `askRecord(sent, null, ...)` で「失敗」として残すのと食い違う。
- 起きる条件: 質問を送ったあと回答待ちのあいだに、接続キーが無効にされる（管理者が鍵を替えた）か、Backend がその質問を見つけられない。
- 影響: Backend には質問がある（受け付け済み）のに、端末の記録（端末の DB が記録の正。08a §5）から抜け、走行の地図・一覧に出ない。US-C-03.002（失敗した質問も分かる形で残す）に反する。SC-14 の読み直しまで戻らない。頻度は低い。
- 対応案: 受け付け済みの質問は、回答待ちがどう終わっても `askRecord(sent, null, now)` で残す（失敗の理由は `failure` に `agent_failed` か専用の値）。テスト: Harness の `answers` に `ApiError(ApiErrorKind.INVALID_KEY)` と `NOT_FOUND` を入れ、`h.kept` に1件、`outcome = FAILED` で残ることを確かめる。
- 同じ根: R4-01（Backend の結果整合の読み出しで 404 になる件。`backend.md`）が起きると、この経路で質問が失敗として扱われる

### R1-05 [A] [Low] [確か] 押下の重複の判定を端末の時計で行うので、時計が戻るとインカムの押下が黙って捨てられる

- 場所: `main/MainActivity.kt` の `handleVoiceCommand()`（56〜57行の `System.currentTimeMillis()`）、`main/handsfree/Press.kt` の `PressTracker.claim()`（11〜16行）
- 内容: 押下の時刻に `System.currentTimeMillis()` を使い、`pressedAt <= lastHandled` を重複とみなす。押下の時刻はいつも「今」なので、この判定が働くのは同じミリ秒の押下か、時計が戻ったときだけ。時計が Δ だけ戻ると、その後 Δ のあいだの押下はすべて `DUPLICATE` になり、何も起きない（合図も無い）。プロジェクトでは位置の時刻について「端末の時計で比べない」（#17・#24）と決めているが、押下は端末の時計に頼っている。
- 起きる条件: 自動の時刻合わせ（ネットワーク・GNSS による補正）や手動の変更で端末の時計が戻ったあと。補正の幅はふつう小さいので、頻度・影響は小さい。
- 影響: 戻った幅のあいだ、インカムのボタンで質問を始められない。
- 対応案: 押下の時刻を `SystemClock.elapsedRealtime()` にする（`PressGate.offer`・`openGate` に渡す `now` も同じ時計）。テスト: `PressTracker` は時計に依らないので、`MainActivity` 側で使う時計を差し込めるようにするか、時計の選択を `PressGate` に持たせて、時計が戻っても押下が通ることを確かめる。

### R1-06 [A] [Low] [確か] 録音の開始・停止の失敗（マイクが他のアプリに取られた・無音にされた）の分岐を確かめるテストが無い

- 場所: `main/ask/AskController.kt` の `record()` の 328〜335行（`recorder.start()` の失敗）と 352〜359行（`recorder.stop()` の失敗。`PcmRecorder.stop` が「無音にされた」で投げる経路）。テストは `test/ask/AskControllerTest.kt` の Harness の `recorder`（127〜131行。投げる手段が無い）
- 内容: この2つの分岐は、経路を返し・位置の監視を止め・`MIC` で失敗する。閉じた Android #1（他のアプリがマイクを持つと空の音声を送る）の直しの中心だが、司令塔の水準では空の PCM の場合（`a_recording_with_nothing_in_it_fails_as_a_microphone_problem`）しか確かめていない。後始末の漏れ（`route.stop` や `location.end` を呼ばない・サービスを止めない）が入っても落ちるテストが無い。
- 影響: いまの不具合ではない。次の改修で後始末を崩しても気づけない。
- 対応案: Harness に `recorderStartError`・`recorderStopError` を足し、それぞれで `route:stop`・`svc:stop` が log にあり、`post` が無く、`FailureReason.MIC` で失敗することを確かめる。

### R1-07 [A] [Low] [確か] `AudioRecord.startRecording()` が投げると、作った `AudioRecord` を解放しない

- 場所: `main/audio/PcmRecorder.kt` の `start()`（23〜34行）
- 内容: `ar.startRecording()` は `IllegalStateException` を投げうるが、その場合 `ar.release()` を通らずに抜ける（32行の解放は「始まらなかった」場合だけ）。ネイティブの資源が GC まで残る。
- 起きる条件: 録音を始めるときに、システムがその場で録音を断る（別のアプリが通話中など）。
- 影響: 失敗の扱い（`MIC`）は正しく進む。資源が少しのあいだ残るだけで、影響は小さい。
- 対応案: `startRecording()` から 34行までを `try { ... } catch (e: Exception) { ar.release(); throw e }` で包む。

### R2-03 [A] [Low] [確か] `ApiClient` が分類しない HTTP の状態（401・405・408・413・3xx など）を成功として扱い、送信が「送れた」と記録する

- 場所: `Android/app/src/main/java/com/touringproject/v2/api/ApiClient.kt` の `kindFor()`（161〜170行）と `once()`（287〜295行）
- 内容: `kindFor` は 400・403・404・409・410・429・5xx だけを `ApiError` にし、それ以外の状態は `null` を返す。`once()` は `null` のとき本文を返して成功にする。`putRide`・`putRoute`・`putAskMemo`・削除は本文を読まないので、`RideSync` はその記録を送れたもの（`rideSent`・`chunkSent`・`deletionSent` など）として印を付け、二度と送らない。
- 起きる条件: API Gateway や途中の網が 07a に無い状態を返したとき（本文の大きさの上限の 413、認証の設定を変えたときの 401、プロキシのリダイレクトなど）。いまの Backend の作りでは起きにくい。API Gateway・途中の網がそうした状態を実際に返す経路があるかは確かめていない（Backend の template と API Gateway の設定は読んでいない）。
- 影響: 起きると、端末では「保存済み」、クラウドには無い記録ができ、利用者は気づけない（機種変更で失われる）。
- 対応案: 2xx 以外はすべて `ApiError` にする（未知の 4xx は送り直さない種類、3xx・未知のものは一時的な失敗として回を終える、など）。テスト: `ApiClientTest` で 401・413・302 を返し、`putRide` が例外を投げることを確かめる。

### R2-04 [A] [Low] [ありうる] 端末の未保存の走行の書き込みが、読み直しでクラウドの削除の跡に従って消した走行を作り直す

- 場所: `Android/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt` の `RideDao.saveRide()`（477〜485行）、`store/RoomTakeover.kt` の `write()`（52〜59行）
- 内容: 読み直し（`replace = false`）は、クラウドに削除の跡がある走行を端末から消す（`merged.gone.rides`）。一方 `saveRide` は `@Upsert` なので、行が無ければ作る。`RideController` が書き直し待ち（`unsaved`）を持っている走行、または名前・メモの書き込みが読み直しのトランザクションと前後した走行が、読み直しで消されたあとに書かれると、その走行が（ルート・質問・地点メモ無しで）端末に戻る。ユーザー名の変更（`replace = true`）は `waitingToSave` で止めているが、読み直しは止めていない（`RoomTakeover.take` 240行は `replace` のときだけ確かめる）。
- 起きる条件: 終えた走行の書き込みが失敗して書き直し待ちのまま、別の端末でその走行を消し、この端末で SC-14 の「クラウドから読み直す」をする。または読み直しの最中に SC-06 で同じ走行の名前を変える。`RideController` の書き直し待ちが読み直しの後のどの呼び出しで書かれるか（`locked` の中の順番）は追いきれていない。
- 影響: 消した走行が空の形で一覧に戻り、送ると 410 で「保存済み」になって残り続ける。まれ。
- 対応案: `saveRide` を「状態が ended の走行は、行があるときだけ書く」にする（走行を始めるときの最初の書き込みは recording なので影響しない）か、`RoomTakeover.write` で消した走行の id を `RideController` に知らせて `unsaved` を捨てる。テスト: `RoomTakeoverTest` で、クラウドの削除の跡で走行を消したあとに `RoomRideStore.save(ended の同じ走行)` を呼び、行ができないことを確かめる。

### R2-05 [A] [Low] [確か] Backend で消された（410）地点メモと質問できなかった地点が、起動のたびに送り直される

- 場所: `Android/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt` の `RideDao.retryNotePlaces()`・`retryUnreachedPlaces()`（515〜531行）、`sync/RideSync.kt` の `sendNote()`・`sendUnreached()`（255〜272行）
- 内容: 410（GONE）は送れたものとして `noteSent(..., address = null, ...)` を呼ぶので、行は `address IS NULL`・`sentUpdatedAt >= updatedAt` になる。`retryPlaces` は起動ごとに、位置があって住所の無い送り済みの行の版を進めるので、410 の行も毎回選ばれ、毎回 PUT して 410 が返る。
- 起きる条件: 同じユーザー名の別の端末（または入れ直す前）でその走行・地点メモを消し、この端末にはまだ残っている。
- 影響: 起動ごとに1件1リクエストの無駄と、そのあいだ SC-05・SC-14 が「未送信あり」になる。読み直すまで続く。
- 対応案: 410 を受けた行に印を付ける（例: `sentUpdatedAt` と別に gone の列、またはその場で端末からも消す）か、`retryPlaces` の条件から 410 の行を外す。テスト: `RideSyncTest` で 410 を返したあと `retryPlaces` → `unsentNotes()` が空であることを確かめる。

### R2-06 [A] [Low] [ありうる] `POST /asks` の応答だけが失われると、Backend の質問と、端末の「質問できなかった地点」の2つが残る

- 場所: `Android/app/src/main/java/com/touringproject/v2/ask/AskController.kt`（393〜423行）、`api/ApiClient.kt` の `postAsk()`（200〜201行）と `callTimeout`（194行）
- 内容: `POST /asks` が通信の失敗（15秒の `callTimeout` を含む）に終わると、端末は自分で作った新しい識別子で質問できなかった地点を作る。Backend が受け付けたあとで応答だけが失われた場合、Backend には `askId` の違う本物の質問（回答まで作られる）が残り、端末はそれを知らない。409 の検出（同じ識別子のとき）は識別子が違うので効かない。POST を試し直さない作り（`ApiClient.postAsk` のコメント）を選んだ結果で、設計どおりかは spec を読んでおらず判断していない。
- 起きる条件: トンネル・山間部などで、送信の直後に通信が切れる。応答だけが失われる頻度は確かめていない。
- 影響: 読み直し・引き継ぎのあとに、同じ時刻・地点に「回答のある質問」と「質問できなかった地点」が並ぶ（記録の二重）。AI の費用もかかっている。
- 対応案: 質問の識別子（または冪等の鍵）を端末で作って `POST /asks` に付け、Backend が同じ鍵を一度だけ受ける形にすると、質問できなかった地点を同じ識別子で置け、409 で重なりを検出できる（07a・07 UC-5 の変更が要り、Backend の `POST /asks` の設計と重なる）。

### R3-06 [A] [Low] [確か] マイクの許可が無くても、ホームは緑の「インカムのボタンで話せます」を出す（足りない許可を知らせる帯が無い）

- 場所: `ui/Labels.kt` の `homeBanner()`（43〜56行）、`ui/HomeScreen.kt` 128〜134行、`AppGraph.kt` の `micAllowed`（115行）
- 内容: 帯は保存の失敗・書けなかった質問・接続キー・戻り先・音量だけ。マイクの許可が無いと、インカムのボタンで録音せずに「録音できませんでした。」と読み上げるが、ホームは「話せます」と出す。許可を求めるのはプロセスで最初の Activity だけ（`takePermissionPrompt`）で、アプリの中から許可の設定へ導く道が無い。モックの SC-02 の帯の表には「位置の許可が不足」がある（条件は「常に許可でない」で、今の作り（前面サービスで位置を取る）とも合わない）。
- 起きる条件: 最初の起動でマイクの許可を断ったとき、または端末の設定で取り消したとき。
- 影響: 走り出してから初めて質問できないと分かる。
- 対応案: `homeBanner` に「マイクの許可がありません（押して設定）」を足し、押すと `Settings.ACTION_APPLICATION_DETAILS_SETTINGS` を開く。許可は `onStart` で読み直す。モックの帯の表の「位置の許可が不足」をこれに置き換え、04 の US-E-01.005 の「欠けている準備」に許可を足すかを決める。テスト: `LabelsTest` で、マイクの許可が無いときにその帯が選ばれる順。
- 関わる文書: `docs/mock/index.html` の SC-02「帯（警告）」、`docs/04_detailed_requirements.md` US-E-01.005
- 同じ根: R3-03

### R1-09 [D] [Low] [確か] 08a は「戻るのは送った時点」と書くが、実装と 04 は戻る時点を選べる

- 場所: `docs/08a_android-design.md` §3「戻る設定のときは、送った時点でナビを前面に出し、残りは背面で進める。」。実装は `main/settings/Settings.kt` の `ReturnTiming { SENT, ANSWERED, SPOKEN }`（24行）と `main/ask/AskController.kt` の `maybeReturn()`（484〜488行）
- 内容: 04 の US-B-04.007 は戻る時点を「送ったらすぐ（既定）／回答が届いたら／読み上げが終わったら」から選べると書き、実装もそうなっている。08a は送った時点だけを書いている。
- 影響: 08a を読んだ人が、回答待ち・読み上げを前面で行う場合を考えずに設計を変えうる。
- 対応案: 08a §3 を「戻る設定のときは、選んだ時点（既定は送った時点）でナビを前面に出し、残りは背面で進める」に直す。
- 関わる文書: `docs/08a_android-design.md` §3、`docs/04_detailed_requirements.md` US-B-04.007

### R1-10 [D] [Low] [確か] 04 の US-C-09.003「画面を出さずにすぐ戻る」と、実装（失敗の画面を出し、読み上げてから戻る）が食い違う

- 場所: `docs/04_detailed_requirements.md` US-C-09.003。実装は `main/ask/AskController.kt` の `fail()`（490〜506行）、`main/ui/AskOverlay.kt` の 43行（`Phase.FAILED` の表示はインカムからの質問でも出る）
- 内容: US-C-09.003 は、インカムのボタンで始めて戻り先があるときは「画面を出さずにすぐ戻る」と書く。実装は `Fail` を出して SC-03 に失敗を表示し、合図と読み上げ（`speech.say` を待つ）のあとでナビに戻る。これは同じ 04 の US-B-04.006「戻る前ならそのあとに戻る」とは合っている。04 の中で2つの書き方が食い違い、実装は片方に従っている。
- 影響: 04 を信じて「通信できないときは画面を出さない」前提で画面や戻り方を変えると、US-B-04.006 を破る。
- 対応案: 実装（音で知らせてから戻る）が正と読めるので、US-C-09.003 を「インカムのボタンで始め、戻り先があるときは、読み上げたあとに戻る（US-B-04.006）」に直す。
- 関わる文書: `docs/04_detailed_requirements.md` US-C-09.003・US-B-04.006

### R2-07 [D] [Low] [確か] ユーザー名を変えると、Backend に断られた記録が端末から消え、どこにも残らない（US-C-03.003 と食い違う）

- 場所: `Android/app/src/main/java/com/touringproject/v2/store/RoomTakeover.kt` の `take()`（28〜31行）、`store/RideDatabase.kt` の `SUMMARY`（363〜372行）
- 内容: 名前の変更が止まる「未送信」は SC-14 の数（断られた版を数えない）で、断られた走行の版・ルートのかたまり（`refused = 1`）・地点メモ・会話のメモがあっても `clearAll()` で消える。それらはクラウドに無いので、元の名前に戻しても戻らない。SC-05 はそれらを「未送信あり」と出す（`saveState` の `pointsLeft`）が、SC-14・SC-18 は「すべて保存済み」と出すので、利用者は消えることに気づけない。08a §6 の決まりどおりだが、04 の US-C-03.003（文字の記録は利用者が削除したときだけ消える）・US-E-06.004（変える前の記録はクラウドに残る）と合わない。
- 起きる条件: 断られた記録（400・Android #25 の組み立てられない値など）がある状態で SC-18 から名前を変える。
- 影響: まれだが、起きると記録が戻せない形で失われる。
- 対応案: どちらかに揃える。(a) 断られた記録があるときも名前の変更を止めるか、DL-03 で「クラウドに保存できなかった記録 N 件は消える」と示す（実装を直す）。(b) 決まりとして受け入れるなら、04 の US-E-06.008 にその例外を書く。
- 関わる文書: `docs/04_detailed_requirements.md` US-C-03.003・US-E-06.004・US-E-06.008、`docs/08a_android-design.md` §6（110行）

### R2-08 [D] [Low] [確か] 08a のパッケージの表に `api` が無い

- 場所: `docs/08a_android-design.md` §1 の表（45〜60行）
- 内容: 実装には `com.touringproject.v2.api`（`ApiClient`・`Records.kt`。Backend の API の窓口と受け渡しの型）があるが、表に行が無い。ほかのパッケージ（ask〜theme）はすべて載っている。
- 影響: 08a を読んで API の窓口がどこにあるか分からない。
- 対応案: 表に「`api` | Backend の API の窓口（送る・受ける形と失敗の分類）・クラウドの記録の読み出しの形」を足す。
- 関わる文書: `docs/08a_android-design.md` §1

### R2-09 [D] [Low] [確か] 07b は住所を「あとから変えない」とするが、07・07a・08a と Android は確定できなかったときに求め直す

- 場所: `docs/07b_datamodel.md` §3 の表（41行）
- 内容: 07b は「地点メモと質問できなかった地点は、最初に受けたときに決めて返し、あとから変えない」。07 UC-7（147行）と 07a（161・314行）は「住所を確定できなかったときは次の PUT で求め直す」、08a §6（107行）と `RideDao.retryPlaces` は起動ごとに版を進めて送り直す。
- 影響: 07b だけを読むと、住所の無い地点メモが後から住所を持つことを想定できない。
- 対応案: 07b の行に「（確定できなかったときは、次に受けたときに求め直す）」を足す。
- 関わる文書: `docs/07b_datamodel.md` §3

### R3-07 [D] [Low] [確か] 端末の通知（EX-03）をタップしても SC-02 には行かず、最後に見ていた画面が出る

- 場所: `service/RideForegroundService.kt` 122行（`PendingIntent` は素の `MainActivity` の Intent）、`MainActivity.kt` の `onNewIntent()`（46〜49行。`VOICE_COMMAND` 以外は何もしない）
- 内容: 02 の EX-03 は「タップで SC-02 を開く」、03 の図も `EX03 --> SC02`、モックも「タップでこの画面」。実装は `singleTask` の Activity を前面に出すだけで、記録タブの SC-06 などを見ていればそのまま。
- 起きる条件: 記録タブや設定タブを開いたまま背面に回し、通知をタップする。
- 影響: 小さい（タブを押せばホームに行ける）。文書と実装が合わない。
- 対応案: 実装が正とするなら、02・03・モックを「アプリを開く（最後の画面）」に直す。SC-02 に行かせるなら、通知の Intent に印を付け、`onNewIntent` で AppUi の選ぶタブを `Tab.HOME` にする（AppGraph に「ホームへ」の合図を置く）。
- 関わる文書: `docs/02_screen_list.md` §4 EX-03、`docs/03_screen_transition.md` §1、`docs/mock/index.html` の SC-02「走行の状態」の最後の箇条

### R3-08 [D] [Low] [確か] SC-05 の上部に保存の状態が無く、SC-05 から SC-14 へ行けない

- 場所: `ui/RecordsScreens.kt` の `RideListScreen()`（89〜117行）
- 内容: 02 の SC-05 の主な要素に「保存の状態」、03 の図に `SC05 -.->|"保存の状態"| SC14`、モックに「上部に保存の状態（未送信の記録があればその旨）。タップで SC-14」。実装は行ごとに「未送信あり／保存済み」を出すだけで、一覧全体の状態と SC-14 への入口が無い。
- 起きる条件: 常に。
- 影響: 小さい（設定タブから SC-14 に行ける）。
- 対応案: 実装を正とするなら 02・03・モックから SC-05 の「保存の状態」と SC-14 への矢印を消す。足すなら `RideListScreen` に `saveRowValue(summary)` の行を置き、タップで `tabs.open(Tab.SETTINGS, DataKey)`。
- 関わる文書: `docs/02_screen_list.md` SC-05、`docs/03_screen_transition.md` §1、`docs/mock/index.html` の SC-05

### R3-09 [D] [Low] [確か] モックの SC-02・SC-03・DL-02 の文言・状態が実装より古い（DL-02 の「一言」は 02 とも食い違う）

- 場所: `docs/mock/index.html` の SC-02（520〜567行）・SC-03（569〜603行）・仕様メモ（1059〜1198行）と、`ui/HomeScreen.kt`・`ui/AskOverlay.kt`・`ui/Labels.kt`・`ui/AppUi.kt`
- 内容（実装が正として、モックを直す対象）:
  - SC-03 に「送っています…」（`Phase.SENDING`、録音中と同じ赤）の状態が無い。文字の質問は「回答待ちから始まる」とあるが、実装は送っているあいだから始まる（03 §2 も「回答待ちから始まる」）。
  - SC-03 の文言: 録音中「インカムのボタンか、この赤い部分を押すとすぐ送信します」「あと 20」→ 実装「もう一度ボタンを押すか、ここを押すと送ります」「20」。回答待ち「回答を待っています（最初の質問は10秒ほど）」→「最初の質問は10秒ほど」。読み上げ中の「この緑の部分を押すと読み上げを止めます」は実装に無い。通信できない「📵 通信できません」「質問できませんでした。この地点を記録しました。」「閉じる（◯秒で自動で閉じます）」→ 実装は読み上げと同じ文（`spokenMessage`）を見出しに出し、ボタンは「閉じる」。
  - SC-02 の帯: モックの「失敗しました（15秒で消える）」「位置の許可が不足」は実装に無く、実装の「記録を保存できません」「書けなかった質問があります」はモックに無い。戻り先の帯の文言も違う（「戻るアプリが未設定です／タップして選ぶ」→「戻り先のアプリが未設定です（押して選ぶ）」）。画面から始めた質問の失敗は、実装では SC-03 の灰色を5秒出して閉じる（04 US-B-06.004 は SC-02 を挙げている）。
  - SC-02 の「新しい会話を始める」: モックは「新しい会話です」のときボタンを押せない見た目にし、上段にボタンの文・下段に時刻。実装はいつも押せ、上段に時刻・下段にボタンの文。
  - DL-02: モック「AI はこれまでの会話を踏まえずに答えます。記録は残ります。」「始める」・トースト「新しい会話を始めました」→ 実装「次の質問から、これまでの会話を踏まえずに答えます。」「新しい会話にする」・トースト無し。02 の DL-02 は「区切ったことが分かるように一言添える」で、実装はホームの文が「新しい会話です」に変わるだけ。
  - トースト: モックの「走行の記録を始めました」「走行を保存しました」は実装に無く、「一時停止しました（ルートを記録しません）」「走行の記録を再開しました」は実装では「一時停止しました」「再開しました」。
- 起きる条件: モックで見た目・文言を確かめるとき。
- 影響: モックを見て画面を直す人が、古い文言に戻しうる。
- 対応案: 上の各項をモックの実装に合わせる。DL-02 の「一言」は、ホームの「新しい会話です」で足りるとするなら 02 の DL-02 の括弧書きを直し、足りないならトーストを足す（`HomeScreen` の `onNewConversation` のあと）。04 US-B-06.004 の画面に SC-03 を足すか決める。
- 関わる文書: `docs/mock/index.html`、`docs/02_screen_list.md` DL-02、`docs/03_screen_transition.md` §2、`docs/04_detailed_requirements.md` US-B-06.004
- 関連: R6-02（SC-03 に走行の記録の状態が出ない件。SC-03 のモックを直すときに一緒に決める。`docs.md`）

### R3-10 [D] [Low] [確か] モックの SC-09 の分類・並び順と、設定の各画面の上のバー（題と戻る）が実装と違う

- 場所: `ui/SettingsScreens.kt` の `SettingsScreen()`（78〜111行）と、`VolumeScreen`・`RideRecordingScreen`・`RecordingSettingsScreen`・`ConnectionScreen`・`UserScreen`・`ReturnAppScreen`・`DataScreen`、`ui/HeadingCheckScreen.kt`、`ui/RecordingsScreen.kt`
- 内容: モックの SC-09 は「走行中の動作」「確認」「ユーザー・接続・データ」「その他」の分類と、各画面の上に題と戻るボタンのバーがある。実装の SC-09 は分類なしで、接続→ユーザー名→データ→走行の記録→戻るアプリ→録音の設定→音量→録音の確認→位置と方位の順。設定の各画面には題も戻るボタンも無い（端末の戻る操作だけ）。SettingsScreen のコメント（98行・106行）は「モックの並びに合わせた」と書くが、合っているのは隣どうしの関係だけ。
- 起きる条件: 常に。
- 影響: 小さい。題が無いので、どの設定の画面かが本文の1行目でしか分からない。
- 対応案: 実装を正とするなら、モックの SC-09 を実装の並びにし、設定の画面の上のバーを消す。題と戻るを足すなら、記録タブの `TopBar`（`RecordsScreens.kt` 72〜79行）を共通にして各設定の画面に置く。
- 関わる文書: `docs/mock/index.html` の SC-09（656〜682行）ほか設定の各画面

### R3-11 [D] [Low] [確か] 08a §1 の構成図に、画面が API・送信と読み込み・位置へ直接触る線が無い

- 場所: `docs/08a_android-design.md` §1、`ui/AppUi.kt` 339行（`ApiClient(...).checkKey()` を画面で作る）・289〜307行（`graph.sync`・`graph.takeover`）・256〜263行（`graph.headingCheck()`）・`RecordsRoutes.kt` の `VoiceInput`
- 内容: 図の画面（UI）からの矢印は「質問の司令塔・走行の司令塔・DB・設定」だけ。実装の画面は、SC-13 で `ApiClient` を作って Backend を直に呼び、SC-14・SC-18 で送信の係と読み込みの係（`RideSync`・`Takeover`）を呼び、SC-22 で位置の監視（`HeadingCheck`）を動かし、SC-19 で声の入力、SC-12 で試し録りを呼ぶ。§5 の「画面はこの DB だけを読む」は記録について正しいが、図からは画面がどこまで触るかが読めない。
- 起きる条件: 08a を読んで画面の依存を掴むとき。
- 影響: 小さい。画面からの依存を変えるときに見落としうる。
- 対応案: 図に `UI --> API`（接続キーの確認）・`UI --> SY`（送信・読み込み）・`UI --> LO`（SC-22）・`UI -.-> VI & TR` を足す。あるいは SC-13 の接続キーの確認で画面が `ApiClient` を作る点を `AppGraph` の中に移し（`AppGraph.checkKey(key)`）、図は今のままにする。
- 関わる文書: `docs/08a_android-design.md` §1

### R1-11 [C] [Low] [確か] `RideController` の `rename()` の説明が `retrySave()` の上に置かれ、どちらの関数の説明か読み違える

- 場所: `main/ride/RideController.kt` の 220〜231行
- 内容: `rename()` の KDoc（220〜224行「SC-06 (and SC-04 through end): gives any kept ride a new name...」）のすぐ後に `retrySave()` の KDoc（225〜228行）が続き、その下に `retrySave()`、さらに `rename()` が来る。前の KDoc はどの宣言にも付かず、`rename()` には説明が無い。
- 対応案: 220〜224行の KDoc を `rename()`（231行）の直前に移す。

### R1-12 [C] [Low] [確か] 声の質問と文字の質問で、入口の確かめ・送信の組み立てが二重になっている

- 場所: `main/ask/AskController.kt` の `run()`（110〜168行）と `runText()`（175〜233行）、`send()`（374〜410行）と `sendText()`（235〜276行）
- 内容: 走行の確かめ → 接続キー → API の組み立て → 前面サービスの開始と失敗の扱い（`service_failed` のログと `FailureReason.SERVICE`）、`finally` の後始末、`AskBody` の組み立てと `post_failed` のログが、ほぼ同じ形で2か所にある。どちらかだけ直す取りこぼしを招く（実際、`runText` は `micAllowed` を見ない・`online` を見る位置が違う、などの違いが意図か偶然かを読み分ける必要がある）。
- 対応案: 入口の確かめ（`refusal`・鍵・サービス）を1つの関数にし、違い（マイクの確かめの有無、シートへの知らせ）を引数で渡す。`AskBody` の組み立ても1つに。テストは既存の `AskControllerTest` がそのまま守る。

### R1-13 [C] [Low] [確か] `record()` の後始末（経路を返す・位置の監視を止める）が4か所に手で書かれている

- 場所: `main/ask/AskController.kt` の `record()`（322〜326・330〜334・342〜346・354〜358・360〜365行）
- 内容: 失敗と取り消しの分岐ごとに `d.route.stop()`・`d.location.end()`（・`d.recorder.cancel()`）を並べている（数えると `route.stop()` が5か所、`location.end()` が6か所）。`d.route.start` が `CancellationException` を投げたとき（314〜315行）は `location.end()` が呼ばれない。後始末の漏れが分岐ごとに起きやすい。
- 対応案: `try/finally` で経路と位置の監視を必ず返す形にする（成功のときに使う `here` は `end()` の戻り値で受ける）。R1-06 のテストで守る。
- 同じ根: R1-01（後始末が取り消しを待たない件）

### R2-10 [C] [Low] [確か] 走行を消す手順が `RideDao.deleteEnded` と `RoomTakeover.write` に重複している

- 場所: `Android/app/src/main/java/com/touringproject/v2/store/RideDatabase.kt` の `deleteEnded()`（549〜553行）、`store/RoomTakeover.kt` の `write()`（52〜59行）
- 内容: 走行の下の表を消す5つの呼び出し（質問・地点メモ・点・区間・走行の行）が2か所に同じ順で書かれている。表を足したとき（例えば走行に紐づく新しい記録）に片方だけ直すと、消した走行の子が残る。
- 対応案: `RideDao` に `removeRide(rideId)`（`@Transaction`）を置き、`deleteEnded` はそれと `markDeleted`、`RoomTakeover` はそれだけを呼ぶ。

### R3-12 [C] [Low] [確か] ホームの KDoc が古いモックを指している

- 場所: `ui/HomeScreen.kt` 85〜89行
- 内容: 「the mock puts it on the card of the heading, which this screen does not have yet」。今のモックは「インカムのボタンで話せます」の行の右に「📝 地点メモ」を置き、「進行方向はホームに出さない」と書く。実装はモックどおりで、コメントだけが古い。
- 対応案: 「"📝 地点メモ" stands at the right of the intercom's line, as the mock puts it」に直す。

### R3-13 [C] [Low] [確か] 色が画面ごとに別の名前で書き直され、暗い外観で灰色の文字が読みにくい（テーマはテンプレートのまま）

- 場所: `ui/SettingsScreens.kt`（`Color(0xFF666666)` が16か所・`Blue`・`Red`）、`ui/RecordingsScreen.kt` 45〜47行（`Blue`・`Red`・`Grey`）、`ui/RecordsScreens.kt` 66〜69行（`Accent`・`Memo`・`Rec`）、`ui/NoteScreen.kt` 38〜39行（`Memo`・`Danger`）、`ui/DeleteDialog.kt` 12行（`Danger`）、`ui/HeadingCheckScreen.kt` 29行（`Muted`）、`theme/Theme.kt`・`theme/Color.kt`（Purple のテンプレート・コメントアウトした既定）、`res/values/themes.xml`（親が `Theme.Material.Light`）
- 内容: 同じ赤（`0xFFD42A2A`）が `Red`・`Danger`・`Rec` として5ファイルに、同じ灰色が `Grey`・`Muted`・`muted`・直書きで並ぶ。テーマは端末の壁紙の色（dynamic color）と暗い外観に従うのに、本文の灰色 `#666666` は固定なので、暗い外観の背景では対比が約3:1になる（色の値から計算）。ホームの「インカムのボタンで話せます」の緑 `#13804A` も暗い背景では約3.5:1。ウィンドウの親テーマは明るいので、暗い外観では起動の一瞬白く光る。
- 対応案: `theme/` にアプリの色（録音中の赤・回答待ちの青・地点メモの緑・質問の橙・灰色の文字）を1か所で定め、灰色の文字は `MaterialTheme.colorScheme.onSurfaceVariant` に寄せる。テンプレートの Purple とコメントを消す。親テーマを `Theme.Material.NoActionBar`（DayNight 相当）にする。

### R3-14 [C] [Low] [確か] 時刻の表示のタイムゾーンが、画面によって `Asia/Tokyo` 固定と端末の設定で分かれる

- 場所: `ui/Labels.kt` 25行（`HHMM`）・74行（`RECORDED_AT`）と、`ui/AppUi.kt` 196・296・402行、`ui/RecordsRoutes.kt` 92・133・152・180・207行（`ZoneId.systemDefault()`）
- 内容: ホームの「◯:◯◯ まで…自動で区切ります」と SC-12 の録音の時刻は日本時間固定、記録・SC-04・SC-14・SC-19 は端末のタイムゾーン。端末が日本時間なら同じだが、決め方が2つある。
- 対応案: どちらかに揃える（日本国内の利用が前提なら、すべて端末のタイムゾーンでよい）。`Labels.kt` の2つも `zone` を受け取る形にする。

### R3-16 [C] [Low] [確か] 「API の URL・接続キー・ユーザー名が揃えば ApiClient、欠ければ null」が4か所に書かれている

- 場所: `AppGraph.kt` 146〜150行（送信）・161〜164行（読み込み）・247〜251行（質問）・311〜315行（声の入力）、`ui/AppUi.kt` 339行（SC-13 の確認）
- 内容: 同じ判断と組み立てが少しずつ違う形で並ぶ（質問は `apiKey` と `api` に分け、読み込みはユーザー名を引数で受ける）。条件を足す（例: URL の形を確かめる）ときに直し漏れやすい。`ui/AppUi.kt` の `{ next -> scope.launch { graph.settings.update(next) } }` も6か所、`Modifier.safeDrawingPadding()` は全 entry に繰り返される。
- 対応案: `AppGraph` に `private fun apiFor(user: String?): ApiClient?` を置いて4か所から呼ぶ。SC-13 の確認は `graph.checkKey(key)` にする。AppUi の設定の更新は1つの `val update: (Settings) -> Unit` に、`safeDrawingPadding` は `NavDisplay` の modifier に1回だけ付ける。

## Info

### R1-08 [A] [Info] [確か] 機械の検査の lint Error（`AudioRoute.kt:65` の `clearCommunicationDevice`、API 31）は実害が無い

- 場所: `main/audio/AudioRoute.kt` の `releaseSco()`（64〜67行）
- 内容: minSdk 29 で API 31 のメソッドを呼んでいる。判断: 実害は無い。理由は次のとおり。
  - Android 10・11 では `clearCommunicationDevice` が無く、呼ぶと `NoSuchMethodError`（`Error`）になるが、Kotlin の `runCatching` は `Throwable` を捕まえるので落ちない。続く `audioManager.mode = MODE_NORMAL` も走る。
  - ART は、無いメソッドを指す呼び出しを含むクラスを読み込み時に拒まない（その呼び出しの時点で投げる）ので、`AudioRoute` の読み込みは壊れない。`acquireSco` 側の API 31 の呼び出しは `SDK_INT < S` で先に返っているので通らない。
  - `releaseSco` が呼ばれるのは `AudioRouteControl.stop` で `source == SCREEN` のときだけ（画面からの質問・試し録り・SC-19 の画面のボタン）。Android 12 未満では `acquireSco` が `MODE_IN_COMMUNICATION` にせずに返るので、`MODE_NORMAL` に戻しても変わらない。
  - 実機（Pixel 8a）は API 31 以上なので、そもそも通らない。
- 対応案: lint を通すために `if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)` で包み、`Error` を `runCatching` で握る形をやめる。`test/audio/AudioTest.kt` の `before_android_12_the_screen_route_reports_no_intercom_instead_of_crashing`（`@Config(sdk = [30])`）の隣に、`releaseSco()` が API 30 で落ちないことのテストを足すと、判断を固定できる。

### R3-17 [B] [Info] [確か] `VOICE_COMMAND` を受ける Activity は公開されているので、端末のほかのアプリから録音を始めさせられる

- 場所: `AndroidManifest.xml` の `MainActivity`（`exported="true"` と `VOICE_COMMAND` の intent-filter）、`MainActivity.kt` の `handleVoiceCommand()`
- 内容: インカムのボタンを受けるには公開が要る（システムが送る）。そのため、同じ端末のどのアプリも明示の Intent で質問の一巡を始められる（走行の記録中・マイクの許可ありのとき、録音して Backend に送る）。送り手を確かめる手段は無い。
- 影響: 端末に悪意のあるアプリが入っている前提でのみ。録音の開始の合図と SC-03 の全面の色で利用者には分かる。
- 対応案: 対応は要らない（身内で使う前提。US-E-06.009 と同じ考え）。気にするなら、`VOICE_COMMAND` のときに `referrer` や `Intent.EXTRA_*` を記録し、ログで追えるようにする程度。

### R1-14 [C] [Info] [確か] 文字の質問の 500 字の切り方は、地点メモ（`cutMemo`）と違い、ZWJ でつないだ絵文字・国旗を割る

- 場所: `main/ask/TextAsk.kt` の `cutTextAsk()`（10〜12行）とそのコメント「never cutting an emoji in half」
- 内容: コードポイントで切るので、サロゲートの組は割らないが、ZWJ でつないだ絵文字・国旗・肌の色の途中で切れうる。README は SC-19 では画面の上の1文字を割らない（`cutMemo`）と書いており、同じアプリで揃っていない。コメントも実際より強く言っている。
- 対応案: `cutMemo` と同じ書記素の境目で切る関数を共有するか、コメントを「サロゲートの組は割らない」に直す。

### R1-15 [C] [Info] [確か] 合図の音のログのタグが走行のもの（`trv2.ride`）

- 場所: `main/audio/ToneCues.kt` の 48行 `TAG = "trv2.ride"`（`AppLauncher` の失敗も `trv2.ride`、`main/nav/AppLauncher.kt` の 23行）
- 内容: 合図・ナビを開く処理のログが走行のタグに混ざり、`trv2.ask`・`trv2.route` と分かれていない。実機のログで質問の一巡を追うときに拾いにくい。
- 対応案: `trv2.ask`（または `trv2.cue`）に揃える。

### R2-11 [C] [Info] [確か] 細かな重複と読みにくさ

- `sync/SyncPlan.kt` の `UnsentNote.toBody()`（67〜71行）と `UnsentUnreached.toBody()`（77〜81行）が、位置と古い材料（`HeadingSample`）の組み立てを同じ形で重ねている（Backend #28 で材料を外すときに2か所直す）。
- `store/RideDatabase.kt` で `markDeleted` が `AskDao`・`NoteDao`・`RideDao` の3か所、`rideKept` が `AskDao`・`NoteDao` の2か所に同じ SQL で定義されている。
- `sync/RideSync.kt` の `reply()` の KDoc（282〜287行）が文の途中（「or」）で改行され、読みにくい。
- `sync/Merge.kt` の `heldBack("ride", it.rideId, it.rideId)`（104行）は、走行自身を「走行の下の記録」としても調べる呼び方で、意図が読み取りにくい。

### R3-15 [C] [Info] [確か] 使っていないテンプレートの資源と、ほぼ空の設定

- 場所: `res/xml/backup_rules.xml`・`res/xml/data_extraction_rules.xml`（マニフェストから参照されず、`allowBackup="false"`）、`gradle.properties` のテンプレートのコメント、`theme/Type.kt`
- 内容: Android Studio のテンプレートの残り。lint の UnusedResources に出ているものと見られる。
- 対応案: 2つの XML を消す。

## 確かめられなかった点

実機でしか分からないもの、利用者が知っておくべきものだけを挙げる。

- プロセスが背面で死んだあと（`START_STICKY` での作り直しや、締め切りのアラームでの起動）に、`RideController.load()` の `Resume` → `ServiceCoordinator.setRecording(true)` → `startForeground`（位置の種類）が Android 14 で通るか。通らないと `RideForegroundService.onStartCommand` の `catch` → `stop()` で前面サービスが止まり、アプリを前面に出す（`MainActivity.onStart` の `refresh()`）までルートが記録されない（US-C-01.007「アプリだけが落ちたときは記録を続ける」）。コードでは追えるが、システムの例外の条件は実機でしか分からない。
- `ReturnTiming.ANSWERED`・`SPOKEN` で、回答待ちのあいだに画面が消えたとき、`AppLauncher.returnTo` の `startActivity` が背面からの起動の制限で黙って止められないか（前面サービスだけでは制限が外れない版がある）。
- 画面が消えている（ロック中）ときにインカムのボタンで `VOICE_COMMAND` が届いた場合に、Activity が「前面」と見なされて前面サービス（マイクの種類）を始められるか。`setShowWhenLocked` は使っていない。
- `RideForegroundService` で、記録中の質問のあいだに締め切りで走行が自動で終わる（背面）と、`apply({MICROPHONE, MEDIA_PLAYBACK})` を背面から呼ぶ。Android 14 で投げると `applyQuietly` がログに残すだけで、前の種類（位置を含む）のままになる。影響は質問が終わるまでの短いあいだに留まると読んだが、実機では確かめていない。
- 音声合成のエンジンが落ちたときに `UtteranceProgressListener` が `onError`・`onStop` を返すか（R1-02 の起きやすさ）。
