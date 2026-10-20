# プロジェクトの状態と引き継ぎ

<!-- 目的（このコメントは消さない・変えない。以後の編集の指針）
- この文書の大目的は、セッションを切り替えたときに、どこにも永続されていないこと（会話の中にしか無い決定・状態・次にやること）が引き継がれずに失われるのを防ぐこと。新しいセッションが、この文書と spec だけで続きを始められれば成功。
- 以下の節や表は出発点にすぎない。目的に合うなら、節を足す・変える・消す・書き方を変えてよい。迷ったら「これが無いと、次のセッションが間違えるか・聞き直すか」で決める。
-->

<!-- 書き方（このコメントは消さない。文書の形を変えたら、それに合わせて直す）
- 全体の管理に要ることを書く: サブプロジェクトと plan の状態・次にやること・持ち越し・ほかの文書に無い前提。
- 細部（数値・API・画面）は書かず、spec などへリンクする。開発の手順は README へ。後回しの指摘の全文は issue か ISSUE.md へ。
- 終わったものは1行に縮める。
- plan の状態の語彙: 未作成／計画済み／実行中／実装済み（確認待ち: 何を）／✅ 完了／保留（理由）
-->

## 次にやること

1. スライス2 plan 3a の走行での確かめ（利用者。天気で後回しにした。3a・3b はマージ済みなので、✗ が出たら main から直す）: 版 0.3.1（plan 3b と Android #38 の修正のビルド。Android `51259c9`。3a の送信を含む。#38 はプロセスを消して戻す確かめを実機で ✓、マージ済み）が実機に入っている。走る前に端末のログの置き場を `adb logcat -G 16M` で広げる（端末の設定を変えるので、利用者に確かめる）。設定 → バージョンが 0.3.1 → 走行を開始し、ナビを前面・画面を消して25分以上（ルートの点を300より多く）→ 記録中に1回質問 → 一時停止して、一時停止中に1回質問 → 再開して少し走る → 終了。そのあと AI がユーザー名を聞き、`AWS_PROFILE=touring` で DynamoDB（`dynamodb-trv2-dev-records`、`pk = USER#<名前>`、`sk` が `RIDE#`・`ASK#` で始まるもの）を読み、走行が `ended`・かたまりが `#ROUTE#00000` から並び最後以外は300点・記録中の質問にだけその走行の `rideId` があることを確かめる。端末のログの `trv2.sync`（`sync_failed`・`sync_refused`）も見る。✗ が出たら `superpowers:systematic-debugging`。
2. スライス2の plan 4a を `superpowers:writing-plans` で書く。範囲は下の plan 表（利用者と決め済み）。`maplibre-compose` を使うかは使い捨てのフォルダで組んで決める（spec 2 §12）。
3. スライス1の完了の判定（利用者の作業）: React Native 版は端末から外したので、移行の plan 2 の走行用のビルド（ネイティブ版）で実際に走り、[spec 1](docs/specs/2026-10-16-slice1-design.md) §1 を確かめる。✗ が出たら `superpowers:systematic-debugging`（直す先はネイティブ版。振る舞いの設計に響くなら移行とスライス2の spec を見直す）。

## サブプロジェクト

**分け方**: 4ユニット（Android・Backend・Agent・CICD）を一度には作れないので、利用者に見える一続きの機能を、全ユニットに縦に通す「スライス」で切る。スライスごとに spec → plan（ユニットごとなどに分ける）→ 実装 → 実機の確認を回す。
**順番の理由**: スライス1で、最も大きなリスク（ハンズフリーの起動・インカムのマイクの経路・背面での動作・応答の待ち時間・費用）を先に実機で確かめる。ネイティブ移行は、アプリの肝がすでにネイティブにあり、つなぎ目の確認が実機に回っていたため、スライス2の前に行う（[adr/0005](adr/0005-native-android-app.md)）。スライス2は「走ったあと」の中心で、残る最大のリスク（何時間も背面で位置を取り続けること・端末の記録の作り）を持つので先に置く。同期の細かい場面（通信できないとき・端末をまたぐとき・削除）は記録の形が固まってからのほうが手戻りが少ないので、スライス3に回す。

着手する順に並べる。

### 1. スライス1: 土台と、質問の一巡（実装済み（確認待ち: 実際の走行での完了の判定））

- **目的**: インカムのボタンで質問してから、回答の読み上げを聞き、ナビへ戻るまでを全ユニットに通す。
- **範囲の要点**: 質問の一巡、現在地・住所・進行方位の確定、Web 検索と周辺検索での回答、15分の会話の文脈、回答の音量、録音の確認、最小限の画面、クラウドへの記録と段ごとの時間・トークン数の計測（詳しくは [spec](docs/specs/2026-10-16-slice1-design.md) §2）
- **完了の判定**: spec §1 の成功の判定（走りながらの通し・「右手の〜」が正しい・周辺の施設を向きと距離で答える・失敗が音で分かる・時間とトークン数を集計できる・15分の文脈）。
- **計画**:

| plan | 中身 | 状態 |
|---|---|---|
| [1](docs/plans/2026-10-16-slice1-plan1-foundation-and-spikes.md) | 土台と、スパイク（ストリーミングの文字起こし・背面での動作） | ✅ 完了 |
| [2](docs/plans/2026-10-16-slice1-plan2-agent.md) | Agent | ✅ 完了 |
| [3](docs/plans/2026-10-16-slice1-plan3-backend.md) | Backend | ✅ 完了 |
| [4a](docs/plans/2026-10-16-slice1-plan4a-app-handsfree.md) | App のハンズフリーの一巡 | ✅ 完了 |
| [4b](docs/plans/2026-10-16-slice1-plan4b-app-finish.md) | App の残り（録音の確認 SC-12・回答の音量 SC-21・音量の警告・走行用のビルド・App の issue #1〜#8） | ✅ 完了（実機の確認まで。マージ済み） |
| — | 完了の判定（実際の走行） | 未実施 |

### 2. ネイティブ移行: App を Kotlin で作り直す（✅ 完了）

[spec](docs/specs/2026-10-17-native-migration-design.md)・plan [1](docs/plans/2026-10-17-native-migration-plan1-foundation-and-handsfree.md)・[2](docs/plans/2026-10-17-native-migration-plan2-finish.md)。App は `Android/`（`TouringProjectV2_Android`）に移り、React Native 版の `TouringProjectV2_App` はアーカイブ済み。実機の確認は ✓（回答の音量の差だけ聞き取れず、既知の制約として通した。持ち越しを参照）。後回しは Android の issue #7〜#13。

### 3. スライス2: 走行の記録と、地図での振り返り（plan 1・2 完了・plan 3a 実装済み（確認待ち）・plan 3b 完了）

- **目的**: 走行の始まりから終わりまでのルートと、その間の質問を記録し、走ったあとに地図で振り返るまでを全ユニットに通す。
- **範囲の要点**: 開始・一時停止・再開・終了・自動終了、背面でのルートの記録（前面サービスの中で Fused）、端末の DB（Room）、走行とルートの送信（送るだけ。読み込みはスライス3）、タブ、記録一覧・走行の詳細・日ごと・会話の詳細の地図（MapLibre と国土地理院のタイル）。端末の停止で走行を終える。メモ・削除・地点メモは入れない（詳しくは [spec](docs/specs/2026-10-17-slice2-design.md) §2）
- **完了の判定**: spec §1（ルートが地図に引かれる・一時停止と再開・自動終了・ピンから質問を読める・日ごと・保存済み・電池の減りの計測）。
- **計画**:

| plan | 中身 | 状態 |
|---|---|---|
| [1](docs/plans/2026-10-18-slice2-plan1-ride-recording-core.md) | Android: 走行の記録の芯（Room・状態機械・サービス・位置・自動終了・落ちたときと端末の停止・SC-17・SC-04）。ADR 0006。終わりに短い走行で確かめる | ✅ 完了（実機で ✓。ログでの裏付けの2点は adr/0006 の「確かめていないこと」。後回しは Android の issue #15〜#20） |
| [2](docs/plans/2026-10-18-slice2-plan2-backend.md) | Backend（`rideId`・`GET /asks` の追加項目・走行の `PUT`・Backend の issue #4 Agent のセッションをユーザーごとに分ける）。デプロイと smoke まで | ✅ 完了（デプロイ済み・smoke 17/17。後回しは Backend #12〜#14・Agent #7・Android #22） |
| [3a](docs/plans/2026-10-18-slice2-plan3a-sync-and-asks.md) | Android: 送信の待ち行列（プロセスの中で spec §5.3 の契機に送る）・質問の保存（Room 版2）と `rideId`・設定の版の表示（spec §7.9。実行中に利用者が足した）・issue #12・#16・#18・#22 | 実装済み（確認待ち: 実際の走行で、300点のかたまり・画面を消して長く走ったときの送信・一時停止中の質問に `rideId` が付かないこと。家の中の短い走行では、plan 1 の走行の送信・端数のかたまり・記録中の質問の `rideId` が ✓。マージ済み。後回しは Android #23〜#30） |
| [3b](docs/plans/2026-10-20-slice2-plan3b-tabs-and-ride-settings.md) | Android: タブ（記録のタブは仮の画面）・ホームの走行のカードと SC-04 の質問の数・SC-16 と最長時間を変えたときの締め切りの計算し直し・issue #15・#19・#20（3a の `asks` の表を読むので後に置く） | ✅ 完了（実機で ✓。マージ済み。後回しは Android #32〜#38） |
| 4a | Android: 地図の部品（MapLibre・国土地理院のタイル）と、走行から入る振り返り（SC-05 の走行の一覧と保存の状態・SC-06・SC-07 の走行の中での前後）。SC-05 の保存の状態は `rides.sentUpdatedAt`・`rejectedUpdatedAt`・`routeRejected` と `route_points.chunk` から出す。issue: Android #27・#32〜#37 | 未作成 |
| 4b | Android: 日ごとの振り返り（SC-05 の「日ごと」の切り替え・SC-15・SC-07 の日の中での前後） | 未作成 |

使い捨てのスパイクは置かない（理由は spec §11）。plan 4 を 4a・4b に分けたのは、最も危うい地図を 4a で先に実機で確かめ、どちらの plan も実機で触れる形で終えるため（2026-10-20、利用者と決めた）。

### 4. 以降の候補（スライス2の終わりに見直す）

| 候補 | 出どころ |
|---|---|
| スライス3: 同期の仕上げと書き足し（通信できないときの後送・質問できなかった地点・クラウドからの読み込みと引き継ぎ・突き合わせの決まり・SC-14・メモ・削除・地点メモ） | spec 2 §2 |
| スライス4: 準備と入力の補い（SC-01・SC-11・文字での質問・文ごとの読み上げ・やめた質問の記録） | 同上 |
| CICD による自動デプロイ（随時） | 同上 |
| 後回しの指摘（関わるスライスで直す） | 各ユニットの GitHub issue |

## 持ち越し

前の plan の Ruling と、実装で分かったことのうち、後の plan・サブプロジェクトに効くもの。spec に入れたら消す。

- Android: Robolectric は SDK 35 で動かす（SDK 36 は Java 21 が要る。`robolectric.properties`）。`withContext(Dispatchers.Main)` に切り替えるコードを Robolectric のテストから直に呼ぶと、メインスレッドの待ち合いで止まる（別スレッドから呼んでメインのルーパーを回す。`AudioTest` の例）。テストの実行には5分の上限がある（移行 plan 1）。
- Android: `MainActivity` は `singleTask` で、`ActivityScenario` は追えない。エミュレーターのテストは Activity を直接起動する（移行 plan 1）。
- Android: minSdk 29 のまま、Android 12 より前は画面から始めた質問を本体のマイクで録る（通信の機器の API が 12 以降のため。インカムのボタンの経路は試す）。minSdk を上げるなら spec を直す（TouringProjectV2_Android の PR #6）。
- Android: 押下は、Activity の復元（プロセスが死んだ後）と「最近使ったアプリ」からの再表示では数えない（TouringProjectV2_Android の PR #6）。
- 端末（Pixel 8a）には2つのユーザー（メインと「サブ」）がある。署名の違うアプリを入れ直すときは、両方から外す（`adb uninstall --user 10 ...`）。スライス1のスパイクのアプリ `com.touringproject.v2spike` が両方に残っている（移行 plan 1）。

- 回答の音量は +6dB が上限。Polly の `prosody volume` は +6dB で頭打ちになり、増幅とリミッターで上げてもインカムで差が聞き取れなかった（plan 4b。spec §6.3・§12 に記録済み）。ネイティブ版でも +0・+3・+6 の差は聞き取れなかった（Backend には選んだ値が届いている。移行 plan 2 の実機の確認で、既知の制約として通した）。音量の要望が出たら、この経緯を前提に Backend で考える。
- インカムの通話の経路（SCO）が張られているあいだと、切れた直後しばらくは、メディアの音量として通話の機器の値が返る。ネイティブ版の `AudioRoute.mediaVolume()` はそのあいだ `null` を返し、画面は直前の値を使う（`ui/Labels.kt` の `nextVolume`。音量を扱う機能を足すときに効く）。
- Android: SC-12 を離れた試し録りが片付くまで（経路の準備で最大3秒）、インカムの押下と「押して話す」は何も始めない（片付けの経路の解放が質問の経路を壊すため。TouringProjectV2_Android のコミット 5a59440。押下が無視されて困るなら、片付けを待って始める作りにする）。
- Android: 走行の `updatedAt` は、状態・名前・区間が変わったときだけ進む。点の追加と生きていた時刻の書き込み（`addPoint`・`markAlive`）では進まない（距離は送らない前提。plan 3 の送信で距離を送るなら、別の印を足す。Android のコミット 46eea83）。
- Android: サービスは `onStartCommand` で `rides.load()` を待ってから `startForeground` を呼ぶ。plan 3 でマイグレーションを足すとき、`load()` が遅くなると前面サービスの開始の時間切れ（約10秒）にかかるので、重い処理を入れない（スライス2 plan 1 の最終レビュー。adr/0006）。
- Android: エミュレーターのテストで Back を押す前に、`onBackPressedDispatcher.hasEnabledCallbacks()` が false になるのを待つ。対話の画面の `BackHandler` は、状態が `IDLE` になってから1回描き直すまで残る（Android のコミット b7d6cba）。
- Android の plan の実行: 使い捨てのフォルダで確かめたコードを本物のリポジトリで回すと、Gradle のビルドキャッシュ（フォルダをまたいで共有される）からテストの結果が返り、1秒ほどで終わる。テストを確かめるときは `--rerun` を付ける。Room のスキーマの版を新しく足した直後の1回目は「Missing file N.json」で落ち、2回目で通る（テストの資産が先に集められるため）。executing-plans の `task-start`・`task-done` は親のリポジトリの git を読むので、Android のコミットの範囲は ledger に手で書く（スライス2 plan 3a）。
- Android: 版（`versionName`・`versionCode`）は、新しい plan の走行用のビルドを実機に入れる前に手で上げる（plan 4a は 0.4.0）。plan の外の修正を入れるときは3つ目の数を上げる（0.3.0 → 0.3.1）。コミットの番号はアプリに出さない（利用者の決定。Android の README・spec 2 §7.9）。
- Backend: ルートのかたまりのソートキーは `RIDE#<rideId>#ROUTE#<seq>` で、走行の `RIDE#<rideId>` と頭がそろう。スライス3で走行の一覧を読むとき、`begins_with(sk, "RIDE#")` だとかたまりも全部読むので、絞り込みか別の頭を考える（spec 2 §6.3）。
- Backend: デプロイの直後の数秒は、新しい経路が 403（`Missing Authentication Token`）になることがある。smoke で新しい経路だけが 403 なら、1分ほど待って回し直す（スライス2 plan 2 で一度あった）。
- Android のテストの決まり（`backgroundScope` は `advanceUntilIdle` で進まない・実機が繋がっているときは `ANDROID_SERIAL` でエミュレーターを指す）は Android の README。Robolectric の AudioTrack は書いた分を即座に再生済みにするので、再生を途中で止めることは実機で確かめる（`AudioTest` の `PcmPlayerTest`。移行 plan 2）。

## 前提（ほかの文書に無いもの）

- 後回しの指摘は、各ユニットのリポジトリ（Android・Backend・Agent・CICD）の GitHub issue。
- plan のコードは、使い捨てのフォルダに展開して、テストとビルドが通ることを確かめてから plan に書く。
- ブランチは plan ごとに、関わるユニットと親に切る。マージはユニット → 親の順で、親は submodule の指す先をユニットのマージ後の main に進める。文書の写し（`scripts/sync-docs.sh`）は、関わらないユニット（Agent・CICD など）では main に直接コミットする。
- push の前に `pre-push-secret-scan` をかけて報告する。
- LLM の入力のトークンを増やす設計は避ける。調整できる値は SSM のパラメーターにする。
- AWS はほかのプロジェクトと同じアカウント。名前に `trv2` を付けて重複を避ける。profile は `touring`（いつも使えるとは限らない。使えないときは利用者に聞く）。
- 接続キー・API の URL・アカウント ID を、コードや文書に書かない。
