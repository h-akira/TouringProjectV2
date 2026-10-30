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

1. 0.14.0（実機に入れてある）で走るときに、plan 3 と plan 4 の残りの確認と、spec §1 の判定（[plan 6](docs/plans/2026-10-28-slice5-plan6-finish.md) の Task 8。走る前に Backend の smoke）をする。結果は Task 8 の Step 4 のとおり PROJECT.md に書く。✗ が出たら `superpowers:systematic-debugging`。
   - plan 3: 走りながら1回・1分以上止まってから1回「右手に見える〜」と質問して左右が正しいこと、止まっているあいだの地点メモ。AI が DynamoDB でその質問と地点メモの `headingDegrees` を確かめる（読むだけ）。
   - plan 4（plan の Task 14 のうち動かすもの）: SC-22 で動くと方位が出て向きと合う・止まると30秒を過ぎて「保っています」が添えられる・保つ上限を超えると方位なし（2の後半・3の前半）、走行の開始・一時停止で出どころが切り替わる（4）、SC-19 の声の入力の文字にしているあいだの押下で失敗の合図（6）。
2. スライス6の plan 6a のデプロイと smoke（利用者の確認を取ってから。`sam build && sam deploy` のあと `scripts/smoke.py`。IAM を絞ったので、`AccessDenied` が出たら template と `tests/test_template.py` の一覧の両方に足して再デプロイする。デプロイ後は CloudWatch で `AccessDenied` と、`ask_recovered` に伴う `ValidationException` を見る）。smoke が通らない経路（`DELETE /asks/{id}`・`DELETE /rides/{r}/notes/{n}`。Backend #40）は、smoke に足すか端末から消して確かめる。そのあと plan 6a のマージ（親と Backend の `slice6-plan6a`）→ plan 6b（Agent の残り。R5-06〜R5-12 と Agent #14。R5-01 は直さない: [adr/0016](adr/0016-allow-personal-data-in-traces.md)）の plan を書く。

## サブプロジェクト

**分け方**: 4ユニット（Android・Backend・Agent・CICD）を一度には作れないので、利用者に見える一続きの機能を、全ユニットに縦に通す「スライス」で切る。スライスごとに spec → plan（ユニットごとなどに分ける）→ 実装 → 実機の確認を回す。
**順番の理由**: スライス1で、最も大きなリスク（ハンズフリーの起動・インカムのマイクの経路・背面での動作・応答の待ち時間・費用）を先に実機で確かめる。ネイティブ移行は、アプリの肝がすでにネイティブにあり、つなぎ目の確認が実機に回っていたため、スライス2の前に行う（[adr/0005](adr/0005-native-android-app.md)）。スライス2は「走ったあと」の中心で、残る最大のリスク（何時間も背面で位置を取り続けること・端末の記録の作り）を持つので先に置く。同期の細かい場面（通信できないとき・端末をまたぐとき・削除）は記録の形が固まってからのほうが手戻りが少ないので、スライス3に回す。

着手する順に並べる。

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

### 6. スライス5: 入力と方位の補い・要件の整理・後回しの指摘の片付け（実行中）

- **目的**: CICD と、当面やらないと決めたもの（[adr/0012](adr/0012-narrow-the-requirements.md)）を除いて、残っている要件と後回しの指摘をすべて片付け、文書を実装に合わせる。
- **範囲の要点**: 止まっているときも進行方位を出す（Android が走行のルートから求める。[adr/0013](adr/0013-heading-on-android-held-while-stopped.md)）・SC-22 位置と方位の確認・文字での質問・SC-11（上限と合図）・SC-05 のユーザー名・後回しの指摘37件（Backend #5・Agent #6 は閉じる）と途中で立てた指摘（spec §15。Backend #28・Agent #8 を除く）・05〜08c と README の突き合わせ・PROJECT.md の整理（詳しくは [spec](docs/specs/2026-10-25-slice5-design.md) §2）
- **完了の判定**: spec §1（長めの信号待ちでも左右が正しい・SC-22 で止まっていても方位が出る・文字で質問できる・SC-11 が効く・SC-05 のユーザー名・指摘が閉じている・文書が実装と合う）。
- **計画**:

| plan | 中身 | 状態 |
|---|---|---|
| [1](docs/plans/2026-10-25-slice5-plan1-backend.md) | Backend: `headingDegrees`（spec §4.4）・Backend #6〜#8・#12〜#14・#21〜#25・smoke・07。デプロイと smoke まで | ✅ 完了（デプロイ済み・smoke 40/40。後回しは Backend #29〜#31） |
| [2](docs/plans/2026-10-25-slice5-plan2-agent.md) | Agent: Agent #2〜#5・#7。デプロイと質問の通しの確認まで | ✅ 完了（最終レビューの直しまでデプロイ済み・Agent の smoke 5/5・Backend の smoke 40/40。後回しは Agent #9〜#11） |
| [3](docs/plans/2026-10-26-slice5-plan3-android-asks.md) | Android: 質問と録音（方位の計算・文字での質問・SC-11・#30・#48・#7〜#11・#68）。版 0.11.0 | 実装済み（確認待ち: 走行での方位。2026-10-28 の実機で SC-11・文字の質問（DynamoDB に `inputType = text` で届いた）・機内モード・音量の帯は ✓。後回しは Android #79〜#81） |
| [4](docs/plans/2026-10-28-slice5-plan4-android-screens.md) | Android: 画面と記録（SC-22・SC-05 のユーザー名・位置の新しさを起動からの経過時間で比べる #17・#24・#50・#61・#59・#69）。版 0.12.0 | 実装済み（確認待ち: 走行での SC-22 と #61。2026-10-28 の実機で SC-22・SC-05 の画面は ✓。マージ済み。後回しは Android #83〜#86） |
| [5](docs/plans/2026-10-28-slice5-plan5-android-user-and-reread.md) | Android: ユーザー名と読み直し（#72〜#77。名前を先に保存して入れられなければ戻す・止まった理由・数える前の表示・件数）。版 0.13.0 | ✅ 完了（2026-10-28 の実機の確認 ✓。マージ済み。JVM 699件・エミュレーター6件。最終レビューで、書き直し待ちの SC-18 の行き止まりを直した（開いたときに書き直す・専用の文言）。後回しは Android #88〜#91） |
| [6](docs/plans/2026-10-28-slice5-plan6-finish.md) | 仕上げ: 05〜08c と README の突き合わせ（食い違い8か所・Android #13）・PROJECT.md の整理（持ち越しの作りの決まりを各ユニットの README へ）・走行での spec §1 の判定 | 実装済み（確認待ち: Task 8 の走行での spec §1 の判定。Task 0〜7 は最終レビューの直しまで済み、マージ済み。後回しは Android #93・Backend #33） |
| [7a](docs/plans/2026-10-28-slice5-plan7a-backend-agent.md) | Backend と Agent: スライス5の途中で立てた指摘（spec §15。Backend #29〜#31・#33、Agent #9・#10。Agent #11 は閉じた）。デプロイと smoke まで | ✅ 完了（デプロイ済み・Agent の smoke 5/5・Backend の smoke 40/40。最終レビューで、出力の上限で切れたツールの呼び出しの前置きを回答にしないよう直した。後回しは無し） |
| [7b](docs/plans/2026-10-28-slice5-plan7b-android.md) | Android: スライス5の途中で立てた指摘（spec §15。#79〜#81・#83〜#86・#88〜#91・#93）。版 0.14.0。この版で plan 6 の Task 8 の走行 | ✅ 完了（2026-10-28 の実機の確認 ✓（文字の質問の音量の帯・送っているあいだの取り消し・SC-22）。方位は 0.14.0 での走行で plan 6 の Task 8 と一緒に確かめる。JVM 713件・エミュレーター6件。最終レビューの Minor 4件は直した（取り消した文字の質問が始めた会話を、次の質問が続けない・README の崩れと文言）。後回しは無し。計画を書くときの全体のテストで揺れた別のテストは Android #94 に書いた） |

候補の「準備と入力の補い」の SC-01・やめた質問の記録・文ごとの読み上げは、使い方に合わせて要件から消した（adr/0012。2026-10-25、利用者と決めた）。そのうえで、CICD 以外の残りを1つのスライスで終える。plan の順番の理由は spec §13。

### 7. スライス6: 全体レビューの指摘の確認と片付け（計画中）

- **目的**: [全体レビュー 2026-10-28](docs/final-review/2026-10-28/README.md) の153件のうち、CICD に回すものと今は直さないものを除いて、**現在のコードで確かめたうえで**直し、文書を実装に合わせる。誤りだった指摘は直さない。
- **範囲の要点・完了の判定**: [spec](docs/specs/2026-10-29-slice6-design.md) §1・§2。
- **計画**: 各 plan の範囲は、その plan を書くとき（brainstorming）に決める。

| plan | 中身 | 状態 |
|---|---|---|
| [1](docs/plans/2026-10-29-slice6-plan1-sc19-voice-attach.md) | Android: R3-01（SC-19 を背面に回すとインカムのボタンが効かない）を単独で直す。版 0.14.1 | ✅ 完了（2026-10-29 の実機の確認 ✓（背面で質問が始まる・前面で声の入力に戻る・録音中は画面が消えない）。JVM 716件。最終レビューで、背面に回すと録音を捨てることに合わせて、声の入力が動いているあいだ画面を点けたままにした。後回しは Android #96・#97） |
| [2a](docs/plans/2026-10-29-slice6-plan2a-android-moves.md) | Android の移すだけの作り替え（R10-05・11・09・07・08）。振る舞いは変えない | 実装済み（JVM 721件。最終レビューまで済み。後回しは Android #99） |
| [2b](docs/plans/2026-10-29-slice6-plan2b-backend-moves.md) | Backend の移すだけの作り替え（R11-12・06・07・13）。振る舞いは変えない。デプロイと smoke まで | ✅ 完了（2026-10-29 にデプロイ済み・Backend の smoke 40/40。pytest 360件。振る舞いは変えていない。最終レビューまで済み。後回しは Backend #35） |
| [3](docs/plans/2026-10-29-slice6-plan3-time-budget.md) | 時間の予算（R11-01。Backend・Agent。[adr/0014](adr/0014-ask-time-budget-from-acceptance.md)）と関連の不具合（R4-02 の時間切れの部分・R5-02・R12-01 の錠）。Agent #6 を開き直して閉じる。デプロイと smoke まで | ✅ 完了（2026-10-30 デプロイ済み。Agent smoke 7/7・Backend smoke 40/40。Agent pytest 104件・Backend pytest 377件。実機で Runtime は同じセッションの 2 本目を 502 で断ると分かり、錠は二重の守り（adr/0014 の追記）。後回しは Agent #14・Backend #37。マージ済み） |
| [4](docs/plans/2026-10-30-slice6-plan4-audio-route-lease.md) | Android: 音声の経路の札（R10-01・R10-06）と関連の不具合（R1-01・R1-02・R1-03）。版 0.14.2。実機の確かめまで | ✅ 完了（マージ済み。2026-10-30 の実機（Pixel 8a）で、取り消してすぐ押し直した質問・SC-19 や SC-12 を離れた直後の質問は ✓。インカムの音声認識の経路の準備中の取り消しは、個別には確かめていない。版 0.14.2・JVM 734件。最終レビューまで済み。後回しは Android #101） |
| [5](docs/plans/2026-10-30-slice6-plan5-record-owner.md) | Android: 記録の持ち主と未送信の条件（R10-03・R10-02・R10-10）と関連の不具合（R2-01・R2-02）、Android #99。Room の版 7。版 0.14.3。実機の確かめまで | ✅ 完了（2026-10-30 の実機（Pixel 8a）で ✓: 0.14.2 からの上書きで Room 6→7 が通り、走行27件・質問24件が残り、`owner` に設定の名前が入った。名前の変更・未送信で止まる・SC-11 の連打も利用者が ✓。DynamoDB（`USER#sit4ix` の走行27件が端末と一致し、別の名前の領域は増えていない）も ✓。設定の名前を書き換えた食い違いの再現は個別には行っていない。ブランチ `slice6-plan5`、JVM 772件。最終レビューまで済み。#99 はこのブランチで直した（マージで閉じる）。後回しは Android #103（質問ループが持ち主の門を通らない）・#104（Minor 9件）。`toRecord().sent` は意味が違うので1つにしない） |
| [6a](docs/plans/2026-10-30-slice6-plan6a-backend.md) | Backend: 残りの不具合・権限（R4-02 の実行環境の落ち＝`claimedAt`・R4-01・R4-05・R4-03・R4-04・R4-06・R4-12・R4-14）、Backend #37・#35。デプロイと smoke まで | 実装済み（確認待ち: デプロイと smoke。ブランチ `slice6-plan6a`、pytest 392件。最終レビューまで済み。後回しは Backend #40。Backend #37・#35 はこのブランチで直した（マージで閉じる）） |
| 6b | Agent: 残りの不具合（R5-06〜R5-12）、Agent #14。デプロイと smoke まで。R5-01（トレースの個人情報）は直さない（[adr/0016](adr/0016-allow-personal-data-in-traces.md)） | 未作成 |
| 7 | Android: 残りの不具合・細部 | 未作成 |
| 8 | 契約（R11-08〜R11-11）。07a・Backend・Android | 未作成 |
| 9 | 文書の整合・issue の整理・仕上げ | 未作成 |

順番の理由は spec §3。

### 8. 以降の候補

| 候補 | 出どころ |
|---|---|
| CICD による自動デプロイ（アプリを仕上げてから）。最初の plan で、環境の名前の焼き込みと手作業の受け渡し（R11-02〜R11-05・R11-17〜R11-19）を片付ける | spec 2 §2・全体レビュー structure.md §2 の順 4 |
| `AppUi`・`AppGraph` の分割（R10-04）。新しい画面を足すスライスの直前に | 全体レビュー structure.md §2 の順 6 |
| 当面やらないと決めたもの（要望が出たら、新しい ADR で戻す） | adr/0012 |
| 後回しの指摘（関わるスライスで直す） | 各ユニットの GitHub issue |

## 持ち越し

後の plan・サブプロジェクトに効くことのうち、コードと各ユニットの README に無いもの。コードの作りの決まりは各ユニットの README の「大事な決まり」・「テスト」に置く。

- 端末（Pixel 8a）には2つのユーザー（メインと「サブ」）がある。走行用のビルドは `adb install --user 0` でメインに入れる。署名の違うアプリを入れ直すときは、両方から外す（`adb uninstall --user 10 ...`）。スライス1のスパイクのアプリ `com.touringproject.v2spike` が両方に残っている。
- 回答の音量は +6dB が上限。Polly の `prosody volume` は +6dB で頭打ちで、増幅とリミッターで上げてもインカムで差が聞き取れず、ネイティブ版でも +0・+3・+6 の差は聞き取れなかった（既知の制約として通した）。音量の要望が出たら、この経緯を前提に Backend で考える。
- インカムの通話の経路（SCO）が張られているあいだと、切れた直後しばらくは、メディアの音量として通話の機器の値が返る（Android は `MediaVolumeWatch` で直前の値を使う）。音量を扱う機能を足すときに効く。
- クラウドの読み込み（SC-18・SC-14）は、今の記録（走行20本ほど）で1〜2秒なので、進み具合の件数は出していない。記録が大きく増えたら測り直す。
- 位置の時刻が、GNSS の位置と網の位置で同じ基準かは実機でしか分からない（Android の `GpsClock` は受けた位置から位置の時刻と経過時間の差を覚える。差が位置ごとに飛ぶなら、止まったあとの方位の保ち方がずれる）。

## 前提（ほかの文書に無いもの）

- 後回しの指摘は、各ユニットのリポジトリ（Android・Backend・Agent・CICD）の GitHub issue。
- plan のコードは、使い捨てのフォルダに展開して、テストとビルドが通ることを確かめてから plan に書く。
- executing-plans の `task-start`・`task-done` は親のリポジトリの git を読むので、ユニットのコミットの範囲は ledger に手で書く。
- ブランチは plan ごとに、関わるユニットと親に切る。マージはユニット → 親の順で、親は submodule の指す先をユニットのマージ後の main に進める。文書の写し（`scripts/sync-docs.sh`）は、関わらないユニット（Agent・CICD など）では main に直接コミットする。
- push の前に `pre-push-secret-scan` をかけて報告する。
- LLM の入力のトークンを増やす設計は避ける。調整できる値は SSM のパラメーターにする。
- AWS はほかのプロジェクトと同じアカウント。名前に `trv2` を付けて重複を避ける。profile は `touring`（いつも使えるとは限らない。使えないときは利用者に聞く）。
- 接続キー・API の URL・アカウント ID を、コードや文書に書かない。
