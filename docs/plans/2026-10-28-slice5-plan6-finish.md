# スライス5 計画6: 仕上げ（文書の突き合わせ・PROJECT.md の整理・spec §1 の判定） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 05〜08c と各ユニットの README を今の実装に合わせ、PROJECT.md を整理し、走行で spec §1 を判定してスライス5を閉じる。

**Architecture:** コードは変えない。文書の食い違い（この plan を書くときに 05〜08c・07b・各 README を実装と突き合わせて見つけたもの）を直し、PROJECT.md の「持ち越し」のうちコードの作りの決まりを各ユニットの README へ移す。最後のタスクは利用者の走行での判定。

**Tech Stack:** Markdown。各ユニットのリポジトリ（Android・Backend・Agent・CICD）と親。`scripts/sync-docs.sh`。

**Spec:** [docs/specs/2026-10-25-slice5-design.md](../specs/2026-10-25-slice5-design.md)（§1・§12・§13・§14）。

**範囲に入れた issue:** Android #13（README が走行用のビルドを「最適化され」と書いている）。Agent #7 は plan 2 で閉じている。spec §2 の後回しの指摘37件のうち、開いているのは #13 だけ（2026-10-28 に確かめた）。

**前提:** 親の `main`（`5461f61`）、Android の `main`（`4a0a1ec`）の上に作る。

**計画を書くときに決めたこと（spec §12 の具体化）:**

- **突き合わせの結果（2026-10-28 に読んだ）:** 食い違いは次の8か所。ほかの 05・07（UC-1〜UC-8）・07b・08（§1〜§5）・08b・08c・Agent の README は実装と合っていた。07a は Backend のテストが実装と合うことを確かめているので、ここでは読まない。
  1. 06 §2 の表: E-01 を「初回の準備」と書いている（SC-01 は adr/0012 で消した。E-01 は「接続の準備が欠けていたら分かる」）。
  2. 07 UC-9: Agent・Backend は CICD がデプロイすると書いている。CICD は後に回していて、今は開発者が各ユニットの README の手順で手でデプロイしている。
  3. 08 §6: 同じ。
  4. CICD の README: 「スライス1では手動でデプロイするので」と古い。
  5. Android の README の走行用のビルド: 「最適化され」（Android #13。`isMinifyEnabled = false`）。
  6. Android の README のログのタグ: `trv2.note`・`trv2.settings` が抜けている。
  7. Android の README の構成の `ui/`: SC-22 の画面（`HeadingCheckScreen.kt`）と文言（`HeadingLabels.kt`）が無い。
  8. Backend の README: Android を古い名前の「App」と書いている（10か所）。
- **PROJECT.md の整理（spec §12）:**
  - 終わったスライス（1〜4・ネイティブ移行）は、spec と plan へのリンクと結果の要点の1〜2行に縮める。plan の表は消す（plan の文書と git に残る）。スライス5は判定が済むまで今の形のまま。
  - 「持ち越し」のうち、コードの作りや開発の決まりは各ユニットの README（Android は「大事な決まり」と「テスト」、Backend と Agent は新しい「大事な決まり」）へ移す。README にもう書いてあるものは消す。もう効かないもの（Room 版7をしない決定・進行方向のカードを作るとき・`AppGraph.switchedTo`）は消す。
  - 残すのは、コードに無い前提（端末の2つのユーザー・回答の音量の上限・読み込みの所要時間・GNSS と網の時刻の基準）と、plan の進め方の決まり（「前提」の節へ）。
- 版は上げない（アプリのコードを変えないため）。

## Global Constraints

- 作業するリポジトリは親・Android・Backend・Agent・CICD。Android・Backend・Agent は `main` から `slice5-plan6` を切り、PR でマージする。CICD は README の1行なので `main` に直接コミットする（文書の写しと同じ扱い。PROJECT.md の「前提」）。親は `slice5-plan6`。push・マージは利用者が明示したときだけ。push の前に `pre-push-secret-scan`。
- 01〜08 には今の決定だけを書く。経緯（何をやめたか・いつ変えたか）は書かない（CLAUDE.md・docs/README.md）。README は開発の手順と作りの決まりを書く。
- 接続キー・API の URL・アカウント ID・ユーザー名を、文書・コミット・issue に書かない。DynamoDB を読んで確かめたことも、値（ユーザー名・座標）は書き写さない。
- 文書は日本語。コミットは英語の Conventional Commits。`git add` はファイルを個別に指定する。ファイルの編集は Read/Edit/Write で行う（sed やスクリプトで置き換えない）。
- 以下 `ROOT=<親リポジトリの絶対パス>`。AWS は `AWS_PROFILE=touring`。

## Review Focus

- 移した決まりが、移した先の README で読める（消しただけで、どこにも残っていないものが無い）。Task 6 の Step 2 の突き合わせ。
- 01〜08 に経緯の言い回し（「〜をやめた」「スライスNで」）を足していない。Task 1 の Step 2。
- 各ユニットの `docs-parent/` が親の `docs/` と同じ。Task 7 の Step 2。
- PROJECT.md だけで次のセッションが続けられる（「次にやること」が判定と、その後の候補を指している）。Task 6・Task 8。
- 判定で ✗ が出たら、直すものを issue か新しい plan に回し、判定の結果を PROJECT.md に書いてから閉じる。Task 8。

---

## ファイル構成

| パス | 変えること | Task |
|---|---|---|
| `docs/06_units_definition.md`・`docs/07_units_contracts.md`・`docs/08_design.md` | 食い違い 1〜3 | 1 |
| `Android/README.md` | 食い違い 5〜7・持ち越しから移す決まり | 2 |
| `Backend/README.md` | 食い違い 8・持ち越しから移す決まり | 3 |
| `Agent/README.md` | 持ち越しから移す決まり | 4 |
| `CICD/README.md` | 食い違い 4 | 5 |
| `PROJECT.md` | 整理 | 6 |
| 各ユニットの `docs-parent/` | 写し | 7 |
| `PROJECT.md` | 判定の結果 | 8 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: ブランチを切る**

```bash
cd $ROOT && git switch slice5-plan6 2>/dev/null || git switch -c slice5-plan6
for u in Android Backend Agent; do git -C $ROOT/$u switch main && git -C $ROOT/$u pull --ff-only && git -C $ROOT/$u switch -c slice5-plan6; done
git -C $ROOT/CICD switch main && git -C $ROOT/CICD pull --ff-only
```

Expected: 親は `slice5-plan6`（この plan のコミットの上）。Android・Backend・Agent は `slice5-plan6`。CICD は `main`。

---

### Task 1: 親の 06・07・08 の食い違いを直す

**Files:**
- Modify: `docs/06_units_definition.md`・`docs/07_units_contracts.md`・`docs/08_design.md`

- [ ] **Step 1: 置き換える**

`docs/06_units_definition.md` の §2 の表:

```
| 初回の準備・設定・ユーザー名 | E-01, E-02, E-04, E-05, E-06 |
```
を
```
| 準備の確認・設定・ユーザー名 | E-01, E-02, E-04, E-05, E-06 |
```

`docs/07_units_contracts.md` の UC-9 の1行目:

```
- Agent・Backend は、CICD（非公開）がデプロイする。手順は各ユニットのリポジトリに置く。
```
を
```
- Agent・Backend は、CICD（非公開）がデプロイする。この仕組みが無いあいだは、開発者が各ユニットの README の手順でデプロイする。
```

`docs/08_design.md` の §6 の1行目:

```
- Agent → Backend の順にデプロイする（Backend が Agent の ARN を読むため）。どちらも CICD（非公開）が持つ仕組みで行う。
```
を
```
- Agent → Backend の順にデプロイする（Backend が Agent の ARN を読むため）。CICD（非公開）が持つ仕組みで行う。この仕組みが無いあいだは、各ユニットの README の手順で手で行う。
```

- [ ] **Step 2: 確かめる**

Run: `cd $ROOT && grep -n '初回の準備' docs/06_units_definition.md; grep -n '仕組みが無いあいだ' docs/07_units_contracts.md docs/08_design.md; git diff docs | grep '^+' | grep -E 'やめ|スライス[0-9]'`
Expected: 1つ目は何も出ない。2つ目は 07（UC-9 の2行）と 08 の3行。3つ目は何も出ない（経緯を足していない）。

- [ ] **Step 3: コミット**

```bash
cd $ROOT && git add docs/06_units_definition.md docs/07_units_contracts.md docs/08_design.md
git commit -m "docs: match 06, 07 and 08 to the setup without SC-01 and to deploying by hand until CICD"
```

---

### Task 2: Android の README

**Files:**
- Modify: `Android/README.md`

- [ ] **Step 1: 食い違いを直す**

構成の表の `.../ui/` の行の終わり:

```
削除の確認（DL-01）は `DeleteDialog.kt` |
```
を
```
削除の確認（DL-01）は `DeleteDialog.kt`、位置と方位の確認（SC-22）は `HeadingCheckScreen.kt`、その文言は `HeadingLabels.kt`（純粋） |
```

「実機で動かす」のログの行:

```
ログは `adb logcat -s trv2.ask trv2.route trv2.ride trv2.sync trv2.recordings`。
```
を
```
ログは `adb logcat -s trv2.ask trv2.route trv2.ride trv2.sync trv2.note trv2.recordings trv2.settings`。
```

「走行用のビルド」の1文目（Android #13）:

```
開発用のビルドも USB を外して動くが、走行では release を入れる（最適化され、デバッグの印が付かない）。
```
を
```
開発用のビルドも USB を外して動くが、走行では release を入れる（デバッグの印が付かない。縮める・最適化はしない）。
```

- [ ] **Step 2: PROJECT.md の「持ち越し」から決まりを移す**

「大事な決まり」の `- 走行の状態を変えるのは` の行の直前に、次の2行を足す:

```
- minSdk は 29。Android 12 より前は、画面から始めた質問を本体のマイクで録る（通信の機器を選ぶ API が 12 以降のため。インカムのボタンの経路は試す）。minSdk を上げるなら、親の spec を直す。
- 押下は、Activity の復元（プロセスが死んだ後）と「最近使ったアプリ」からの再表示では数えない。
```

`- 走行の状態を変えるのは` の行の直後に、次の2行を足す:

```
- サービスは `onStartCommand` で `rides.load()` を待ってから `startForeground` を呼ぶ。`load()` が遅いと前面サービスの開始の時間切れ（約10秒）にかかるので、重い処理（大きなマイグレーションなど）を入れない。
- 走行の `updatedAt` は、状態・名前・区間・メモが変わったときだけ進む。点の追加と生きていた時刻の書き込み（`addPoint`・`markAlive`）では進まない（距離は送らない）。
```

`- 走行とルートは \`RideSync\` が送る。` で始まる行の終わりに、次の文を足す:

```
 接続キーとユーザー名の変化（`credentialChanges`）は、設定を読み込んだあとに集め、読み込んだ時点の値は数えない。送信で「断られた」と同じに扱う例外は `SerializationException` だけ（`IllegalArgumentException` は、OkHttp が不正な API の URL で投げるので含めない）。
```

`- SC-19 の声の入力（\`VoiceInput\`）は` で始まる行の終わりに、次の文を足す:

```
 その下の `AudioRoute` はアプリに1つなので、SC-19 を離れたら待っている処理を取り消してすぐ経路を返し、返しきるまで（音声認識の経路の準備は最大4秒で、取り消せない）は `busy` で、押下の行き先は質問を始めない。`attach` は札を返し、`detach` はその札のときだけ効く（閉じていく画面の後始末が、新しく開いた画面からインカムのボタンを取り上げないように）。
```

`- 録音の確認（SC-12）は` で始まる行の終わりに、次の文を足す:

```
 SC-12 を離れた試し録りが片付くまで（経路の準備で最大3秒）、インカムの押下と「押して話す」は何も始めない（片付けの経路の解放が質問の経路を壊すため）。試し録りは `voice.busy` を見ていない。
```

`- 回答は音声の焦点（audio focus）を取らずに鳴らす` の行の直後に、次の1行を足す:

```
- MapLibre の呼び出し（スタイル・ソース・カメラ）は UI スレッドだけで行う。`withContext(Dispatchers.Default)` から戻った先は UI スレッドとは限らないので、`RouteMap` は地図に触る処理を `withContext(Dispatchers.Main)` に置く。
```

「テスト」の節の `Robolectric は SDK 35 で動かす` の段落を、次に置き換える:

```
Robolectric は SDK 35 で動かす（`app/src/test/resources/robolectric.properties`。SDK 36 には Java 21 が要る）。テストの実行には5分の上限がある。

- Gradle のビルドキャッシュはフォルダをまたいで共有されるので、テストを確かめるときは `--rerun` を付ける。Kotlin の差分コンパイルは、interface に足したメソッドを作り物が実装していなくても通すことがあるので、区切りの確かめは `./gradlew clean` から回す。Room のスキーマの版を足した直後の1回目は「Missing file N.json」で落ち、2回目で通る（テストの資産が先に集められるため）。
- `withContext(Dispatchers.Main)` に切り替えるコードを Robolectric のテストから直に呼ぶと、メインスレッドの待ち合いで止まる。別スレッドから呼んでメインのルーパーを回す（`AudioTest`）。Robolectric の AudioTrack は書いた分をすぐ再生済みにするので、再生を途中で止めることは実機で確かめる。
- Robolectric で `@Config(qualifiers = ...)` で画面を大きくすると、ポップアップ（メニュー・ダイアログ）のテストが止まらなくなる。画面の外の行は `performScrollTo`・`performScrollToNode` で出す。入力欄にフォーカスがあるあいだの最初の Back は入力欄が受けるので、破棄の確認は ✕ で確かめる。閉じた Room への最初の問い合わせは取り消しの例外（`JobCancellationException`）になるので、読み出しの失敗は DAO を委譲で包んで作る（`RoomNotesTest`）。
- `AppUi` の中の記録の画面（SC-05〜SC-07）は本物の地図を描くので、Robolectric でアプリ全体を通すテストは書けない。画面ごとのテストに作り物の地図を渡し、つなぎは実機で確かめる。
- エミュレーターのテストで Back を押す前に、`onBackPressedDispatcher.hasEnabledCallbacks()` が false になるのを待つ（対話の画面の `BackHandler` は、状態が `IDLE` になってから1回描き直すまで残る）。
```

- [ ] **Step 3: 確かめる**

Run: `cd $ROOT/Android && grep -c '最適化され' README.md; grep -c 'trv2.settings' README.md; grep -c 'HeadingCheckScreen' README.md; grep -c 'minSdk は 29' README.md; grep -c 'performScrollToNode' README.md`
Expected: `0`・`1`・`1`・`1`・`1`

- [ ] **Step 4: コミット**

```bash
cd $ROOT/Android && git add README.md
git commit -m "docs: correct the README on the release build, logs and SC-22, and take in the rules kept in the parent's notes (Fixes #13)"
```

---

### Task 3: Backend の README

**Files:**
- Modify: `Backend/README.md`

- [ ] **Step 1: 「App」を「Android」に直す**

「App」（10か所: 冒頭の2行目に2つ・「流れ」の1〜5・7・9・「デプロイ」の `App の設定に入れる値`）を、すべて「Android」にする。

- [ ] **Step 2: PROJECT.md の「持ち越し」から決まりを移す**

「テスト」の節の直前に、次の節を足す:

```
## 大事な決まり

- 記録に残す方位を決めるのは `lib/geo.py` の `settled_heading` だけ（Android の `headingDegrees` を先に、無ければ古い形の `headingSample` から）。
- 削除の跡を見て書く書き込み（走行・ルート・地点メモ・会話のメモ）は、書き込みと跡の確かめを1つのトランザクションにする（`store._write_unless_deleted`）。テーブルの resource の `meta.client` は値の型付けを自分で行うので、トランザクションには素の値を渡す（型付けした値を渡すと、取り消しの理由が `TypeError` になる）。走行の削除で子の記録を集める問い合わせは、一貫した読み出しにする（moto はいつも一貫しているので、テストでは引数を確かめる）。
- `GET /records` の項目は、値が無ければ `null` で返す（入れ子の区間の `endedAt`・点の `accuracy` も）。整数に等しい数は整数で返る（`5.0` が `5`）ので、Android は数を Double として読む。質問の `status` は `pending` と `processing` を見分けず `processing`。
```

「デプロイ」の節の `AWS_PROFILE=touring env/bin/python scripts/smoke.py` のコードブロックの直後に、次の段落を足す:

```
デプロイの直後の数秒は、新しい経路が 403（`Missing Authentication Token`）になることがある。smoke で新しい経路だけが 403 なら、1分ほど待って回し直す。
```

- [ ] **Step 3: 確かめる**

Run: `cd $ROOT/Backend && grep -nw 'App' README.md; grep -c 'settled_heading' README.md; grep -c 'Missing Authentication Token' README.md`
Expected: 1つ目は何も出ない。`1`・`1`

- [ ] **Step 4: コミット**

```bash
cd $ROOT/Backend && git add README.md
git commit -m "docs: call the app Android in the README and take in the rules kept in the parent's notes"
```

---

### Task 4: Agent の README

**Files:**
- Modify: `Agent/README.md`

- [ ] **Step 1: PROJECT.md の「持ち越し」から決まりを移す**

「振る舞い」の `- Web 検索の MCP の接続は、` で始まる行の終わりに、次の文を足す:

```
 接続は `tools/web_search.WebSearchConnection` がプロセスの中で持ち続ける（Strands は、質問ごとのエージェントが捨てられると接続を止めるため）。つなぎ直しの判断は Strands の内部の名前（`_connection_failed`・`_tool_provider_started`・`_is_session_active`）を読むので、Strands の版を上げたら `tests/test_web_search.py` の本物の `MCPClient` のテストで確かめる。`AGENT_MCP_MAX_IDLE_SECONDS=0` にすると、質問ごとにつなぎ直す。
```

- [ ] **Step 2: 確かめる**

Run: `cd $ROOT/Agent && grep -c 'WebSearchConnection' README.md`
Expected: `1`

- [ ] **Step 3: コミット**

```bash
cd $ROOT/Agent && git add README.md
git commit -m "docs: note in the README how the web search connection is kept and checked"
```

---

### Task 5: CICD の README

**Files:**
- Modify: `CICD/README.md`

- [ ] **Step 1: 置き換える**

```
TouringProjectV2 の Agent・Backend のデプロイの仕組み（非公開）。スライス1では手動でデプロイするので、まだ中身は無い。
```
を
```
TouringProjectV2 の Agent・Backend のデプロイの仕組み（非公開）。まだ中身は無い。仕組みができるまでは、各ユニットの README の手順で手でデプロイする。
```

- [ ] **Step 2: 確かめてコミットする**

Run: `cd $ROOT/CICD && grep -c 'スライス1' README.md`
Expected: `0`

```bash
cd $ROOT/CICD && git add README.md
git commit -m "docs: say the deploys are by hand until this unit has its pipeline"
```

---

### Task 6: PROJECT.md を整理する

**Files:**
- Modify: `PROJECT.md`

- [ ] **Step 1: 終わったスライスを縮める**

「### 1. スライス1」から「### 5. スライス4」の節の終わり（「### 6. スライス5」の直前）までを、次に置き換える:

```
### 1. スライス1: 土台と、質問の一巡（✅ 完了。2026-10-21 の走行で spec §1 を確かめた）

[spec](docs/specs/2026-10-16-slice1-design.md)・plan [1](docs/plans/2026-10-16-slice1-plan1-foundation-and-spikes.md)・[2](docs/plans/2026-10-16-slice1-plan2-agent.md)・[3](docs/plans/2026-10-16-slice1-plan3-backend.md)・[4a](docs/plans/2026-10-16-slice1-plan4a-app-handsfree.md)・[4b](docs/plans/2026-10-16-slice1-plan4b-app-finish.md)。走行での判定で、受け付けから音声まで中央値12.6秒・最大18.6秒、入力のトークンは1問あたり中央値3909・最大10590だった。

### 2. ネイティブ移行: App を Kotlin で作り直す（✅ 完了）

[spec](docs/specs/2026-10-17-native-migration-design.md)・plan [1](docs/plans/2026-10-17-native-migration-plan1-foundation-and-handsfree.md)・[2](docs/plans/2026-10-17-native-migration-plan2-finish.md)。App は `Android/`（`TouringProjectV2_Android`）に移り、React Native 版の `TouringProjectV2_App` はアーカイブ済み。

### 3. スライス2: 走行の記録と、地図での振り返り（✅ 完了。2026-10-21 の走行で spec §1 を確かめた。結果は adr/0006 の追記）

[spec](docs/specs/2026-10-17-slice2-design.md)・plan [1](docs/plans/2026-10-18-slice2-plan1-ride-recording-core.md)・[2](docs/plans/2026-10-18-slice2-plan2-backend.md)・[3a](docs/plans/2026-10-18-slice2-plan3a-sync-and-asks.md)・[3b](docs/plans/2026-10-20-slice2-plan3b-tabs-and-ride-settings.md)・[4a](docs/plans/2026-10-20-slice2-plan4a-records-and-map.md)・[4b](docs/plans/2026-10-20-slice2-plan4b-ask-only-while-recording.md)。

### 4. スライス3: メモ・地点メモ・削除（✅ 完了。2026-10-22 に spec §1 を確かめた）

[spec](docs/specs/2026-10-21-slice3-design.md)・plan [1](docs/plans/2026-10-21-slice3-plan1-backend.md)・[2](docs/plans/2026-10-21-slice3-plan2-memos-and-deletion.md)・[3](docs/plans/2026-10-22-slice3-plan3-text-point-memos.md)・[4](docs/plans/2026-10-22-slice3-plan4-voice-point-memos.md)。

### 5. スライス4: 同期の仕上げ（✅ 完了。2026-10-23 の実機で spec §1 を確かめた）

[spec](docs/specs/2026-10-22-slice4-design.md)・plan [1](docs/plans/2026-10-22-slice4-plan1-backend.md)・[2](docs/plans/2026-10-22-slice4-plan2-unreached-asks.md)・[3](docs/plans/2026-10-23-slice4-plan3-takeover.md)。
```

- [ ] **Step 2: 「持ち越し」を整理する**

「## 持ち越し」の節の本文（見出しの次の行から「## 前提」の直前まで）を、次に置き換える:

```
後の plan・サブプロジェクトに効くことのうち、コードと各ユニットの README に無いもの。コードの作りの決まりは各ユニットの README の「大事な決まり」・「テスト」に置く。

- 端末（Pixel 8a）には2つのユーザー（メインと「サブ」）がある。走行用のビルドは `adb install --user 0` でメインに入れる。署名の違うアプリを入れ直すときは、両方から外す（`adb uninstall --user 10 ...`）。スライス1のスパイクのアプリ `com.touringproject.v2spike` が両方に残っている。
- 回答の音量は +6dB が上限。Polly の `prosody volume` は +6dB で頭打ちで、増幅とリミッターで上げてもインカムで差が聞き取れず、ネイティブ版でも +0・+3・+6 の差は聞き取れなかった（既知の制約として通した）。音量の要望が出たら、この経緯を前提に Backend で考える。
- インカムの通話の経路（SCO）が張られているあいだと、切れた直後しばらくは、メディアの音量として通話の機器の値が返る（Android は `MediaVolumeWatch` で直前の値を使う）。音量を扱う機能を足すときに効く。
- クラウドの読み込み（SC-18・SC-14）は、今の記録（走行20本ほど）で1〜2秒なので、進み具合の件数は出していない。記録が大きく増えたら測り直す。
- 位置の時刻が、GNSS の位置と網の位置で同じ基準かは実機でしか分からない（Android の `GpsClock` は受けた位置から位置の時刻と経過時間の差を覚える。差が位置ごとに飛ぶなら、止まったあとの方位の保ち方がずれる）。
```

「## 前提（ほかの文書に無いもの）」の「- plan のコードは、使い捨てのフォルダに展開して、」の行の直後に、次の1行を足す:

```
- executing-plans の `task-start`・`task-done` は親のリポジトリの git を読むので、ユニットのコミットの範囲は ledger に手で書く。
```

突き合わせ: 消した「持ち越し」の各項が、次のどれかにあることを確かめる。

| 消した項（持ち越しの書き出し） | 移した先・消した理由 |
|---|---|
| Robolectric は SDK 35・`Dispatchers.Main`・5分 | Android の README「テスト」 |
| `MainActivity` は `singleTask` | Android の README「大事な決まり」に既にある |
| minSdk 29・押下を数えない場合 | Android の README「大事な決まり」 |
| Room 版7で `inputType` を足さない | もう効かない（plan 3 で決めて実装済み。spec と plan に残る） |
| 方位の部品の場所・`textSheet` | Android の README「大事な決まり」に既にある |
| 位置の時刻を端末の時計と比べない | Android の README に既にある。基準の未判定だけ残した |
| SC-12 を離れた試し録り | Android の README「大事な決まり」 |
| 走行の `updatedAt` | Android の README「大事な決まり」 |
| サービスの `load()` と `startForeground` | Android の README「大事な決まり」 |
| Back を押す前に待つ | Android の README「テスト」 |
| plan の実行の `--rerun`・Missing N.json・`task-start` | Android の README「テスト」と、親の「前提」 |
| 版の上げ方 | Android の README に既にある |
| Backend のデプロイ直後の 403 | Backend の README「デプロイ」 |
| Backend の削除の跡のトランザクション | Backend の README「大事な決まり」 |
| Backend の `GET /records` の null と数 | Backend の README「大事な決まり」 |
| 差分コンパイルと `clean` | Android の README「テスト」 |
| `@Config(qualifiers)`・`performScrollToNode` | Android の README「テスト」 |
| MapLibre の `queryRenderedFeatures` | Android の README「エミュレーター」に既にある |
| MapLibre は UI スレッド | Android の README「大事な決まり」 |
| テストの決まり・AudioTrack | Android の README「テスト」 |
| 地点メモの入口の位置・進行方向のカード | もう効かない（進行方向のカードは adr/0012 で消した）。`MemoEditor` と `AskDao.keep` は Android の README に既にある |
| Robolectric の Back・閉じた Room・#59 | Android の README「テスト」。#59 は plan 4 で直した |
| SC-19 の声の入力の経路と札 | Android の README「大事な決まり」 |
| 断られたと同じに扱う例外 | Android の README「大事な決まり」 |
| `credentialChanges` は読み込みのあと | Android の README「大事な決まり」 |
| 質問できなかった地点の行の形・`RideSync` の引数の順 | Android の README「大事な決まり」に既にある（引数の順はコードで分かる） |
| 読み込みの係・`switchedTo` | Android の README に既にある（`switchedTo` は plan 5 で無くなった）。所要時間だけ残した |
| Backend の `settled_heading`・#28 | Backend の README「大事な決まり」。#28 は issue にある |
| Agent の MCP の接続 | Agent の README「振る舞い」 |
| `AppUi` の記録の画面のテスト | Android の README「テスト」 |

- [ ] **Step 3: 確かめる**

Run: `cd $ROOT && wc -l PROJECT.md; grep -c 'switchedTo\|Room 版7\|進行方向のカードを作る' PROJECT.md; grep -c '^| \[' PROJECT.md`
Expected: 1つ目は100行前後（173行から減る）。2つ目は `0`。3つ目はスライス5の plan の表の行だけ（`6`）。

- [ ] **Step 4: コミット**

```bash
cd $ROOT && git add PROJECT.md
git commit -m "docs: shrink the finished slices and move the coding rules out of PROJECT.md into the units' READMEs"
```

---

### Task 7: 文書を写す

- [ ] **Step 1: 写す**

```bash
cd $ROOT && scripts/sync-docs.sh Android Backend Agent CICD
for u in Android Backend Agent CICD; do echo "== $u"; git -C $u status --short docs-parent; done
```

Expected: 各ユニットで `docs-parent/06_units_definition.md`・`07_units_contracts.md`・`08_design.md` が変わる。

- [ ] **Step 2: 写しが同じことを確かめてコミットする**

Run: `cd $ROOT && for u in Android Backend Agent CICD; do diff -rq docs $u/docs-parent | grep -v 'Only in docs: \(specs\|plans\|init\)\|COPIED.md'; done`
Expected: 何も出ない

```bash
cd $ROOT && for u in Android Backend Agent; do git -C $u add docs-parent/06_units_definition.md docs-parent/07_units_contracts.md docs-parent/08_design.md && git -C $u commit -m "docs: sync the parent docs for slice 5 plan 6"; done
git -C CICD add docs-parent/06_units_definition.md docs-parent/07_units_contracts.md docs-parent/08_design.md && git -C CICD commit -m "docs: sync the parent docs for slice 5 plan 6"
```

---

### Task 8: 走行で spec §1 を判定する（利用者）

Android は 0.13.0（plan 5）のまま。plan 3・4 の残りの確認と同じ走行で行う。

- [ ] **Step 1: 走る前に Backend の smoke を回す**

```bash
cd $ROOT/Backend && AWS_PROFILE=touring env/bin/python scripts/smoke.py
```

Expected: すべて通る（40/40）。新しい経路だけ 403 なら1分待って回し直す。

- [ ] **Step 2: 利用者が走って確かめる**（spec §1 と、plan 3・4 の残り）

1. 走りながら1回、1分以上止まってから1回、「右手に見える〜」と質問する。どちらも左右が正しい（spec §1 の1つ目・plan 3）。止まっているあいだに地点メモを1件書く。
2. SC-22 を開いて止まる。方位が出続け、30秒を過ぎると「止まる直前の向きを保っています」が添えられる。走り出して曲がると新しい向きに変わる（spec §1 の2つ目・plan 4 の2）。走行を一時停止すると出どころが「この画面を開いてから集めた位置で…」に、再開すると「走行のルートから…」に変わる（plan 4 の4）。
3. 「向きを保つ上限」を2分にして2分を超えて止まると、「止まってから、向きを保つ上限（2分）を超えました」になる。既定値に戻す（plan 4 の3）。
4. 止まって、文字で質問すると回答が読み上げられ、SC-07 に「⌨ 文字で質問」と出る（spec §1 の3つ目。plan 3 の実機で ✓ 済みなら省いてよい）。
5. SC-19 の声の入力で、「文字にしています…」のあいだにインカムのボタンを押すと、失敗の合図が鳴る（plan 4 の6）。
6. 方位の既定値（基準の距離15m・精度の上限20m・保つ上限10分）で、走行中と信号待ちの方位がおかしくないか（spec §14）。合わなければ、どう変えるかを利用者と決める。

- [ ] **Step 3: DynamoDB で方位を確かめる（読むだけ）**

1 の質問2件と地点メモに `headingDegrees` が入っていて、走った向きと合う。テーブルは `dynamodb-trv2-dev-records`（`ap-northeast-1`）。ユーザー名と座標は、会話にも文書にも書き写さない。

```bash
AWS_PROFILE=touring aws dynamodb query --region ap-northeast-1 --table-name dynamodb-trv2-dev-records \
  --key-condition-expression "pk = :p AND begins_with(sk, :s)" \
  --expression-attribute-values '{":p":{"S":"USER#<ユーザー名>"},":s":{"S":"ASK#"}}' \
  --projection-expression "sk, headingDegrees, askedAt" --output table | tail -20
```

（キーの名前が違えば `aws dynamodb describe-table` で確かめる。）

- [ ] **Step 4: 結果を書く**

- ✓ なら: PROJECT.md のスライス5の見出しを「✅ 完了。<日付>の走行で spec §1 を確かめた」にし、plan 3・4・6 の行を「✅ 完了（…）」にし、spec §1 のチェックを付けた結果（数・気づいたこと）を1〜2行で書く。「次にやること」を「以降の候補」から選ぶ（利用者に聞く）にする。spec §14 の既定値を変えたなら、その値と理由を書き、変えるための plan か issue を立てる。
- ✗ なら: `superpowers:systematic-debugging` で原因を調べ、直すものを issue か新しい plan にし、PROJECT.md の「次にやること」をそれにする。スライス5は「実行中」のまま。

```bash
cd $ROOT && git add PROJECT.md
git commit -m "docs: record the ride that judged slice 5"
```
