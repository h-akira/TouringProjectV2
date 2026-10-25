# スライス5 計画1: Backend（Android が求めた進行方位を受ける・Backend の issue） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend が、Android の走行のルートから求めた進行方位（`headingDegrees`）を、質問・質問できなかった地点・地点メモの3つの経路で受けて使う。端末に残った古い未送信のために、古い形の方位の材料（`headingSample`）も受け続ける。あわせて、範囲に入れた Backend の issue（#6〜#8・#12〜#14・#21〜#25）を直す。デプロイして、通しの確認（smoke）を通す。

**Architecture:** 既存の作り（API Gateway＋Lambda・1つの DynamoDB テーブル・`lib/` に検証と記録、`handlers/` に受け口）のまま。
- 方位の値の検証は `lib/request.py` の `heading_value` に置く。記録に残す方位を決めるのは `lib/geo.py` の `settled_heading` だけにする: Android の値があればそれ、無ければ古い形の材料から求め、0.1度に丸めて360を0にする。
- 4つの受け口（`POST /asks` の記録・worker・地点メモ・質問できなかった地点）は、どれも `settled_heading` を通す。
- 削除の跡の読み取りは、BatchGetItem の1回にまとめる。
- SSM の設定値の名前は、テンプレートの既定値をやめ、`samconfig.toml` の環境ごとの設定で渡す。

**Tech Stack:** Python 3.13（Lambda）・SAM・boto3・pytest・moto・openapi-spec-validator・PyYAML（どれも既存。足すものは無い）。

**Spec:** [docs/specs/2026-10-25-slice5-design.md](../specs/2026-10-25-slice5-design.md)（§4.4・§9・§13 の plan 1）。決定の記録は [adr/0013](../../adr/0013-heading-on-android-held-while-stopped.md)。

**範囲に入れた issue:** Backend #6・#7・#8・#12・#13・#14・#21・#22・#23・#24・#25（spec §2・§9）。#5 は閉じた（spec §9）。#28（`headingSample` の受け口を外す）は、Android の新しい版を入れたあとで扱う。

**計画を書くときに決めたこと（spec からの具体化）:**
- `headingDegrees` は、0以上360未満の有限の数だけを受ける。範囲の外・文字列・真偽値・null は方位なしとして扱い、質問は続ける（今の `headingSample` の「不正なものは無いものとして扱う」と同じ。400 にはしない）。
- `headingDegrees` と `headingSample` の両方があれば、`headingDegrees` を使う。`headingDegrees` が無いときだけ、今の決まり（2分より古い点・5m 未満の点では方位なし）で `headingSample` から求める。
- `POST /asks` は、受けた `headingDegrees` を質問の記録にそのまま置く。worker はそれを `settled_heading` に通し、丸めた値で上書きする（`GET /asks/{askId}` は、worker が終わる前は Android の値を返す）。
- 地点メモと質問できなかった地点の方位は、今と同じく、最初に方位を受けたときに決め、あとの版では変えない（Android の値でも同じ）。
- 方位の丸めは `round(x, 1) % 360` で、359.95度以上を0度にする（#12）。Android の値にも同じ丸めを通す。
- #21: 質問できなかった地点の位置は、住所・方位と同じく、最初に位置を受けたときに決め、あとの版では変えない（位置なしで置き直しても消えない。別の位置で置き直しても変わらない）。最初の版に位置が無ければ、あとの版の位置を使う。issue の対応案の「REMOVE に回す」はとらない（位置を消しても住所が残り、食い違うため）。openapi と 07 に書く。
- #25: `GET /asks/{askId}` は、質問できなかった地点に `status: "offline"` を返す。openapi の `AskResult.status` の enum に `offline` を足す（`GET /records` はもう `offline` を返している）。
- #23: 質問と地点メモの `delete_item` を `_retrying_conflicts` で包む。走行の削除の `BatchWriteItem` は、boto3 の `batch_writer` が処理されなかった項目（`UnprocessedItems`）を送り直すので変えない（理由をコメントに書く）。
- #24: `has_deletion_mark` を、テーブルの `meta.client.batch_get_item`（`ConsistentRead: True`・`ProjectionExpression: "pk"`）の1回にまとめる。読み残し（`UnprocessedKeys`）は、50ms・100ms…あけて読み直す。テーブルの resource の `meta.client` は値の型付けを自分で行うので、キーは素の値で渡す（PROJECT.md の持ち越しの Backend の項）。
- #6: 音声の base64 は、改行と空白を取り除いてから `validate=True` で読む。`POST /asks` と `POST /transcriptions` の両方に効く。
- #22: `cursor` のソートキーが UTF-8 で1024バイトを超えたら 400。
- #8: `AgentError` の文は、Agent のエラーの `code`（無ければ `agent_error`）、ランタイムの `error_type`（無ければ `runtime_error`）、AWS のエラーの符号、例外の型名のどれかだけにする。Agent の `message` は持たない。worker のログ（`agent_error`）は今のまま `str(error)` を出す。
- #14: `runtimeSessionId` の長さは、InvokeAgentRuntime の API の資料で33〜256文字と確かめた。説明を直すだけ。
- #7: `AgentRuntimeArn`（SSM の値の型の引数）は既定値に `!Sub` を使えないので、issue の対応案のもう1つ「samconfig の環境ごとの設定で上書きする」をとる。`AgentRuntimeArn` と `ConversationResetParameter` の既定値を外し、`samconfig.toml` の `parameter_overrides` で `/trv2/dev/...` を渡す。別の環境で渡し忘れると、デプロイがエラーで止まる。
- #13: テストの最後に、何も書かれていないことの確かめを足すだけ。
- smoke は、文字の質問と地点メモを `headingDegrees` で、声の質問と質問できなかった地点を古い形の `headingSample` で送り、両方の経路を確かめる。質問できなかった地点を `GET /asks` で問い合わせると `offline` になること、文字起こしだけの依頼の音声を76文字ごとに改行した base64 で送っても通ることも確かめる。smoke の検査は39件から40件になる。

この計画のコードは、使い捨てのフォルダ（`git worktree`）でタスクの順にコミットし、次を確かめてから書いた。
- 各コミットで、`__pycache__` を消してから pytest が通る（今の268件から、最後は305件）。
- 各タスクのテストだけを1つ前のコミットに当てると落ちる。守りのテストは除く（各 Task の Step 2 に書いた）。
- `sam validate --lint` が通る。

デプロイと smoke は、実行のときに利用者の確認を取ってから行う。

## Global Constraints

- 作業するリポジトリは `Backend/`（`TouringProjectV2_Backend`）と親。どちらも作業ブランチ `slice5-plan1` は spec のコミットのときに切ってある。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。Backend の PR の本文には `Fixes #6`・`Fixes #7`・`Fixes #8`・`Fixes #12`・`Fixes #13`・`Fixes #14`・`Fixes #21`・`Fixes #22`・`Fixes #23`・`Fixes #24`・`Fixes #25` を書く。
- **デプロイは、利用者が明示したときだけ行う。** Task 9 の途中で確認を取る。AWS は `AWS_PROFILE=touring`（使えないときは利用者に聞く）。リージョンは `ap-northeast-1`。名前には `trv2` を付ける。
- 進行方位は「真北から時計回りの度数（0以上360未満）。方位なしなら null。Android が走行のルートから求める。Backend は0以上360未満の数でなければ方位なしとして扱う」（spec §4.4・07 UC-5）。
- `headingSample` も今のまま受ける。両方あれば `headingDegrees` を使う（spec §4.4）。
- 不正な入力は `400 {"error": "bad_request", "message": <理由>}`（07 UC-4）。削除の跡があるときは `410 {"error": "deleted"}`（adr/0009）。
- LLM の入力のトークンを増やさない（この plan はプロンプトの形を変えない）。
- ログに、質問・回答・メモ・地点メモの本文と位置を出さない（`handlers/common.py` の `log` の決まり）。Agent のエラーの文も出さない（#8）。
- 接続キー・API の URL・アカウント ID を、コードや文書に書かない。smoke の出力に接続キーを出さない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`BE=$ROOT/Backend`。テストは `cd $BE && env/bin/pytest -q`（絞るときは `env/bin/pytest -q tests/test_xxx.py`）。この Mac の zsh では、変数に入れた複数のパスは分割されないので、コマンドにはパスをそのまま書く。
- 各 Task の差分は、`cd $BE && git apply` で当てられる形で書いた（`docs-parent/` の差分は親の `docs/` に当ててから写す）。差分のとおりに当て、手で書き換えない。

## Review Focus

- 版を上げる前の Android が残した未送信の質問できなかった地点・地点メモ（`headingSample` だけ）が、版を上げたあとで届く → 今までどおり方位が付く。Task 1 の `test_settled_heading_falls_back_to_an_older_apps_sample` と、既存の `tests/test_notes.py`・`tests/test_offline.py` の方位のテスト。smoke の「unreached ask saved with its place」。
- Android が範囲の外の方位（360・負の数・文字列）を送る → 400 にせず、方位なしで質問を続ける。Task 1 の `test_heading_degrees_out_of_range_is_dropped`・`test_a_heading_out_of_range_is_not_kept`。
- 両方の形が届く → Android の値を使う（標本の向きで上書きしない）。Task 1 の `test_the_apps_heading_wins_over_the_sample`・`test_a_note_keeps_the_apps_heading`・`test_an_unreached_ask_keeps_the_apps_heading`。
- 質問できなかった地点にメモを書いたあと、端末が位置や方位の違う新しい版を送る → 位置・住所・方位は最初の値のまま。Task 1 の `test_a_newer_version_keeps_the_apps_first_heading`、Task 2 の `test_a_newer_version_keeps_the_first_position`。
- 会話のメモの送信と削除がほぼ同時に届く → 削除が 5xx にならず消える。Task 3 の `test_deleting_an_ask_during_a_transaction_on_it_is_tried_again`。

---

## ファイル構成（`Backend/` から）

| パス | 役割 | Task |
|---|---|---|
| `src/lib/request.py` | 方位の値の検証 `heading_value`・`AskInput.heading`（1）。改行入りの base64（4） | 1・4 |
| `src/lib/geo.py` | 記録に残す方位 `settled_heading`（1） | 1 |
| `src/lib/notes.py`・`src/lib/offline.py` | `NoteInput.heading`・`OfflineAskInput.heading`（1） | 1 |
| `src/handlers/ask.py`・`src/handlers/worker.py` | 質問の方位を置く・使う（1） | 1 |
| `src/handlers/rides.py`・`src/handlers/ask_edit.py` | 地点メモ・質問できなかった地点の方位（1）。質問できなかった地点の位置を最初の値に（2） | 1・2 |
| `src/handlers/result.py` | `offline` の状態（2） | 2 |
| `src/lib/store.py` | 削除の試し直し・跡の読み取りをまとめる（3） | 3 |
| `src/lib/records.py` | `cursor` のソートキーの長さ（4） | 4 |
| `src/lib/agent.py` | `AgentError` の文・セッションの識別子の説明（5） | 5 |
| `template.yaml`・`samconfig.toml` | SSM の設定値の名前を環境ごとに渡す（6） | 6 |
| `docs-parent/07a_openapi.yaml`・`docs-parent/07_units_contracts.md` | 親の文書の写し（`offline` の状態・base64・質問できなかった地点の位置。親は plan のコミットで直してある）（6） | 6 |
| `scripts/smoke.py` | 新しい検査（7） | 7 |
| `README.md` | 文書（8） | 8 |
| `tests/` | 各 Task のテスト。`tests/test_template.py` は新規（6） | 1〜6 |

---

### Task 0: 作業ブランチを確かめる

- [ ] **Step 1: ブランチと状態を確かめる**

```bash
cd $ROOT && git branch --show-current && git status --short
cd $BE && git branch --show-current && git status --short && env/bin/pytest -q | tail -1
```

Expected: どちらも `slice5-plan1` で、変更なし。pytest は `268 passed`。

---

### Task 1: Android が求めた方位を受ける（#12）

**Files:**
- Modify: `src/lib/request.py`・`src/lib/geo.py`・`src/lib/notes.py`・`src/lib/offline.py`・`src/handlers/ask.py`・`src/handlers/worker.py`・`src/handlers/rides.py`・`src/handlers/ask_edit.py`
- Test: `tests/test_geo.py`・`tests/test_request.py`・`tests/test_ask.py`・`tests/test_worker.py`・`tests/test_notes.py`・`tests/test_offline.py`

**Interfaces:**
- Produces: `lib.request.heading_value(value: Any) -> Optional[float]`（0以上360未満の有限の数、それ以外は None）。`AskInput.heading: Optional[float] = None`・`NoteInput.heading: Optional[float] = None`・`OfflineAskInput.heading: Optional[float] = None`（どれも最後の引数）。`lib.geo.settled_heading(degrees: Optional[float], location: Optional[dict], sample: Optional[dict], at: datetime) -> Optional[float]`（0.1度に丸め、360を0にする）。質問の記録の項目 `headingDegrees`（`POST /asks` が置き、worker が上書きする）。

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/tests/test_ask.py b/tests/test_ask.py
index 7c07c13..f2160a5 100644
--- a/tests/test_ask.py
+++ b/tests/test_ask.py
@@ -115,3 +115,15 @@ def test_an_ask_that_cannot_be_queued_is_503_and_leaves_no_ask_or_audio(aws, mon
     assert result["statusCode"] == 503 and json.loads(result["body"]) == {"error": "unavailable"}
     assert [i["sk"] for i in aws.table.scan()["Items"] if i["sk"].startswith("ASK#")] == []
     assert aws.s3.list_objects_v2(Bucket=aws.bucket).get("KeyCount") == 0
+
+
+def test_the_apps_heading_is_kept_with_the_ask(aws):
+    body = json.loads(call({"text": "右手の山は？", "location": {"latitude": 35.6812, "longitude": 139.7671},
+                            "headingDegrees": 45.5})["body"])
+    assert store.get_ask("rider01", body["askId"])["headingDegrees"] == 45.5
+
+
+def test_a_heading_out_of_range_is_not_kept(aws):
+    result = call({"text": "Q", "headingDegrees": 400})
+    assert result["statusCode"] == 202
+    assert "headingDegrees" not in store.get_ask("rider01", json.loads(result["body"])["askId"])
diff --git a/tests/test_geo.py b/tests/test_geo.py
index 4be9b76..c62c4ae 100644
--- a/tests/test_geo.py
+++ b/tests/test_geo.py
@@ -46,3 +46,21 @@ def test_heading_none_when_sample_is_stale_or_in_future(seconds_ago):
 
 def test_small_device_clock_skew_is_tolerated():
     assert geo.heading_degrees(HERE, sample(SOUTH_60M, -5), NOW) == pytest.approx(0, abs=0.5)
+
+
+def test_settled_heading_takes_the_apps_degrees():
+    # The app works the heading out from the ride's route (adr/0013); its sample is not used then.
+    assert geo.settled_heading(123.44, HERE, sample(SOUTH_60M, 10), NOW) == 123.4
+
+
+def test_settled_heading_falls_back_to_an_older_apps_sample():
+    assert geo.settled_heading(None, HERE, sample(SOUTH_60M, 10), NOW) == pytest.approx(0, abs=0.1)
+
+
+def test_settled_heading_reads_almost_north_as_zero():
+    # 359.96 rounds to 360.0, which is north (Backend #12).
+    assert geo.settled_heading(359.96, HERE, None, NOW) == 0.0
+
+
+def test_settled_heading_is_none_without_degrees_or_sample():
+    assert geo.settled_heading(None, HERE, None, NOW) is None
diff --git a/tests/test_notes.py b/tests/test_notes.py
index 8b74396..2d43827 100644
--- a/tests/test_notes.py
+++ b/tests/test_notes.py
@@ -163,3 +163,16 @@ def test_a_note_first_sent_without_a_heading_gets_one_later(aws, places):
     put_note(note_body(headingSample=None))
     result = put_note(note_body(updatedAt="2026-10-21T01:10:00.000Z"))
     assert answer(result)["headingDegrees"] == 0.0
+
+
+def test_a_note_keeps_the_apps_heading(aws, places):
+    # The sample says north; the app's own heading (adr/0013) is the one kept.
+    result = put_note(note_body(headingDegrees=270.0))
+    assert answer(result)["headingDegrees"] == 270.0
+    assert store.get_note(USER, RIDE, NOTE)["headingDegrees"] == 270.0
+
+
+def test_an_edited_note_keeps_the_apps_first_heading(aws, places):
+    put_note(note_body(headingDegrees=270.0))
+    result = put_note(note_body(text="直した", headingDegrees=90.0, updatedAt="2026-10-21T01:10:00.000Z"))
+    assert answer(result)["applied"] is True and answer(result)["headingDegrees"] == 270.0
diff --git a/tests/test_offline.py b/tests/test_offline.py
index 85c32e0..7da0f33 100644
--- a/tests/test_offline.py
+++ b/tests/test_offline.py
@@ -139,3 +139,16 @@ def test_a_bad_ask_id_is_400(aws, places):
 def test_a_broken_heading_sample_only_drops_the_heading(aws, places):
     result = put_offline(offline_body(headingSample={"latitude": "x"}))
     assert result["statusCode"] == 200 and answer(result)["headingDegrees"] is None
+
+
+def test_an_unreached_ask_keeps_the_apps_heading(aws, places):
+    # The sample says north; the app's own heading (adr/0013) is the one kept.
+    result = put_offline(offline_body(headingDegrees=270.0))
+    assert answer(result)["headingDegrees"] == 270.0
+    assert store.get_ask(USER, ASK)["headingDegrees"] == 270.0
+
+
+def test_a_newer_version_keeps_the_apps_first_heading(aws, places):
+    put_offline(offline_body(headingDegrees=270.0))
+    result = put_offline(offline_body(headingDegrees=90.0, updatedAt=T2))
+    assert answer(result)["applied"] is True and answer(result)["headingDegrees"] == 270.0
diff --git a/tests/test_request.py b/tests/test_request.py
index 4fcad5b..50ab0f7 100644
--- a/tests/test_request.py
+++ b/tests/test_request.py
@@ -116,3 +116,14 @@ def test_volume_choices(volume):
 def test_volume_bad(volume):
     with pytest.raises(BadRequest):
         parse_ask(event({"text": "Q", "volumeDb": volume}))
+
+
+@pytest.mark.parametrize("value, heading", [(0, 0.0), (90.5, 90.5), (359.9, 359.9)])
+def test_heading_degrees_in_range(value, heading):
+    assert parse_ask(event({"text": "Q", "headingDegrees": value})).heading == heading
+
+
+@pytest.mark.parametrize("value", [360, -0.1, 1e9, "90", True, None, [90]])
+def test_heading_degrees_out_of_range_is_dropped(value):
+    # Like a broken sample: the question still goes ahead, without a heading.
+    assert parse_ask(event({"text": "Q", "headingDegrees": value})).heading is None
diff --git a/tests/test_worker.py b/tests/test_worker.py
index e24866c..44cbc6c 100644
--- a/tests/test_worker.py
+++ b/tests/test_worker.py
@@ -93,6 +93,22 @@ def test_agent_gets_facts_location_and_session(aws):
     assert location["headingDegrees"] == 0.0 and session == session_id(USER, CID)
 
 
+def test_the_apps_heading_wins_over_the_sample(aws):
+    # The sample says north; the app's own heading (adr/0013) is the one used.
+    put(aws, headingDegrees=90.0)
+    rec = Recorder()
+    worker.process(USER, ASK, rec.steps())
+    _, prompt, location, _ = next(c for c in rec.calls if c[0] == "agent")
+    assert "真北から90度" in prompt and location["headingDegrees"] == 90.0
+    assert store.get_ask(USER, ASK)["headingDegrees"] == 90.0
+
+
+def test_almost_north_is_kept_as_zero(aws):
+    put(aws, headingDegrees=359.96, headingSample=None)
+    worker.process(USER, ASK, Recorder().steps())
+    assert store.get_ask(USER, ASK)["headingDegrees"] == 0
+
+
 def test_text_question_skips_transcription(aws):
     put(aws, audio=False)
     rec = Recorder()
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_geo.py tests/test_request.py tests/test_ask.py tests/test_worker.py tests/test_notes.py tests/test_offline.py`
Expected: 21件が FAIL（`settled_heading` が無い・`AskInput` に `heading` が無い・方位が標本の向き（0度）になる）。`test_a_heading_out_of_range_is_not_kept` は守りのテストで、前から通る。

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/src/handlers/ask.py b/src/handlers/ask.py
index d048ca8..417bde4 100644
--- a/src/handlers/ask.py
+++ b/src/handlers/ask.py
@@ -43,6 +43,7 @@ def handler(event, context):
         "question": ask.text,
         "location": ask.location,
         "headingSample": ask.heading_sample,
+        "headingDegrees": ask.heading,
         "volumeDb": ask.volume_db,
         "rideId": ask.ride_id,
         "timings": {"receivedAt": iso(now)},
diff --git a/src/handlers/ask_edit.py b/src/handlers/ask_edit.py
index 3493234..5b18882 100644
--- a/src/handlers/ask_edit.py
+++ b/src/handlers/ask_edit.py
@@ -4,7 +4,7 @@ from __future__ import annotations
 
 from handlers.common import deleted, iso, log, no_content, parse_iso, response, utc_now
 from lib import address, offline, rides, store
-from lib.geo import heading_degrees
+from lib.geo import settled_heading
 from lib.request import BadRequest, user_name
 
 
@@ -52,7 +52,8 @@ def _offline(event: dict, user: str, ask_id: str) -> dict:
     else:
         heading = (stored or {}).get("headingDegrees")
         if heading is None:
-            heading = heading_degrees(unreached.location, unreached.heading_sample, parse_iso(unreached.asked_at))
+            heading = settled_heading(unreached.heading, unreached.location, unreached.heading_sample,
+                                      parse_iso(unreached.asked_at))
         location = unreached.location
         kept = {
             "userName": user,
@@ -64,7 +65,7 @@ def _offline(event: dict, user: str, ask_id: str) -> dict:
             # Settled on the first PUT, like a point memo's; a failed lookup is tried again.
             "address": (stored or {}).get("address") or (
                 address.describe_location(location["latitude"], location["longitude"]) if location else None),
-            "headingDegrees": round(heading, 1) if heading is not None else None,
+            "headingDegrees": heading,
             "savedAt": iso(utc_now()),
         }
         applied = store.put_offline_ask(user, ask_id, kept)
diff --git a/src/handlers/rides.py b/src/handlers/rides.py
index b847d48..d9e9c4a 100644
--- a/src/handlers/rides.py
+++ b/src/handlers/rides.py
@@ -5,7 +5,7 @@ from __future__ import annotations
 
 from handlers.common import deleted, iso, log, no_content, parse_iso, response, utc_now
 from lib import address, notes, rides, store
-from lib.geo import heading_degrees
+from lib.geo import settled_heading
 from lib.request import BadRequest, user_name
 
 
@@ -65,7 +65,7 @@ def _note(event: dict, user: str, ride_id: str) -> dict:
         heading = (stored or {}).get("headingDegrees")
         if heading is None:
             # Settled on the first PUT that has one, like the place (slice 3 spec §6.2, Backend #17).
-            heading = heading_degrees(note.location, note.heading_sample, parse_iso(note.at))
+            heading = settled_heading(note.heading, note.location, note.heading_sample, parse_iso(note.at))
         kept = {
             "at": note.at,
             "location": note.location,
@@ -74,7 +74,7 @@ def _note(event: dict, user: str, ride_id: str) -> dict:
             # The position never changes, so the place is looked up once; a failed lookup is tried again (§6.2).
             "address": (stored or {}).get("address") or (
                 address.describe_location(note.location["latitude"], note.location["longitude"]) if note.location else None),
-            "headingDegrees": round(heading, 1) if heading is not None else None,
+            "headingDegrees": heading,
             "savedAt": iso(utc_now()),
         }
         applied = store.put_note(user, ride_id, note_id, kept)
diff --git a/src/handlers/worker.py b/src/handlers/worker.py
index ff12429..322cd36 100644
--- a/src/handlers/worker.py
+++ b/src/handlers/worker.py
@@ -12,7 +12,7 @@ from typing import Optional
 from handlers.common import iso, log, parse_iso, utc_now
 from lib import address, agent, clients, speech, store, transcribe
 from lib.agent import AgentError, AgentReply, session_id
-from lib.geo import heading_degrees
+from lib.geo import settled_heading
 from lib.prompt import agent_location, build_prompt
 from lib.request import DEFAULT_VOLUME_DB
 
@@ -96,12 +96,12 @@ def _run(user: str, ask_id: str, item: dict, steps: Steps) -> None:
 
     received_at = parse_iso(item["receivedAt"])
     location = item.get("location")
-    heading = heading_degrees(location, item.get("headingSample"), received_at)
+    heading = settled_heading(item.get("headingDegrees"), location, item.get("headingSample"), received_at)
     place = steps.describe_location(location["latitude"], location["longitude"]) if location else None
     elapsed = (received_at - parse_iso(item["conversationStartedAt"])).total_seconds() if item.get("conversationStartedAt") else None
     prompt = build_prompt(question, received_at, location, place, heading, elapsed)
     mark("factsAt")
-    facts = {"transcript": transcript, "address": place, "headingDegrees": round(heading, 1) if heading is not None else None}
+    facts = {"transcript": transcript, "address": place, "headingDegrees": heading}
 
     try:
         reply = steps.invoke_agent(prompt, agent_location(location, heading), session_id(user, item["conversationId"]))
diff --git a/src/lib/geo.py b/src/lib/geo.py
index 139538b..1fb7612 100644
--- a/src/lib/geo.py
+++ b/src/lib/geo.py
@@ -35,6 +35,14 @@ def compass(bearing: float) -> str:
     return _COMPASS[round((bearing % 360) / 22.5) % 16]
 
 
+def settled_heading(degrees: Optional[float], location: Optional[dict], sample: Optional[dict],
+                    at: datetime) -> Optional[float]:
+    """The heading kept with a record: the app's own (adr/0013), or, from an app older than that, the one taken from
+    its sample. Rounded to a tenth of a degree, with 360 read as 0 (Backend #12)."""
+    heading = degrees if degrees is not None else heading_degrees(location, sample, at)
+    return round(heading, 1) % 360 if heading is not None else None
+
+
 def heading_degrees(location: Optional[dict], sample: Optional[dict], received_at: datetime) -> Optional[float]:
     """Direction of travel from the older sample to the current position, or None."""
     if location is None or sample is None:
diff --git a/src/lib/notes.py b/src/lib/notes.py
index a6b4f60..72d17e9 100644
--- a/src/lib/notes.py
+++ b/src/lib/notes.py
@@ -4,7 +4,7 @@ from __future__ import annotations
 from dataclasses import dataclass
 from typing import Optional
 
-from lib.request import BadRequest, body_json, heading_sample, position
+from lib.request import BadRequest, body_json, heading_sample, heading_value, position
 from lib.rides import utc_time
 
 NOTE_TEXT_MAX = 2000
@@ -17,6 +17,7 @@ class NoteInput:
     heading_sample: Optional[dict]
     text: str
     updated_at: str
+    heading: Optional[float] = None
 
 
 def parse_note(event: dict) -> NoteInput:
@@ -33,4 +34,4 @@ def parse_note(event: dict) -> NoteInput:
     if not text or len(text) > NOTE_TEXT_MAX:
         raise BadRequest(f"text must be 1-{NOTE_TEXT_MAX} characters")
     return NoteInput(utc_time(data.get("at"), "at"), location, heading_sample(data.get("headingSample")), text,
-                     utc_time(data.get("updatedAt"), "updatedAt"))
+                     utc_time(data.get("updatedAt"), "updatedAt"), heading_value(data.get("headingDegrees")))
diff --git a/src/lib/offline.py b/src/lib/offline.py
index c5975f2..c659f36 100644
--- a/src/lib/offline.py
+++ b/src/lib/offline.py
@@ -5,7 +5,7 @@ from __future__ import annotations
 from dataclasses import dataclass
 from typing import Optional
 
-from lib.request import UUID_RE, BadRequest, body_json, heading_sample, position
+from lib.request import UUID_RE, BadRequest, body_json, heading_sample, heading_value, position
 from lib.rides import utc_time
 
 
@@ -16,6 +16,7 @@ class OfflineAskInput:
     heading_sample: Optional[dict]
     ride_id: str
     updated_at: str
+    heading: Optional[float] = None
 
 
 def parse_offline_ask(event: dict) -> OfflineAskInput:
@@ -31,4 +32,5 @@ def parse_offline_ask(event: dict) -> OfflineAskInput:
     if not isinstance(ride_id, str) or not UUID_RE.match(ride_id):
         raise BadRequest("rideId must be a lowercase UUID")
     return OfflineAskInput(utc_time(data.get("askedAt"), "askedAt"), location, heading_sample(data.get("headingSample")),
-                           ride_id, utc_time(data.get("updatedAt"), "updatedAt"))
+                           ride_id, utc_time(data.get("updatedAt"), "updatedAt"),
+                           heading_value(data.get("headingDegrees")))
diff --git a/src/lib/request.py b/src/lib/request.py
index 2747462..d17acce 100644
--- a/src/lib/request.py
+++ b/src/lib/request.py
@@ -34,6 +34,7 @@ class AskInput:
     conversation_id: Optional[str]
     volume_db: int = DEFAULT_VOLUME_DB
     ride_id: Optional[str] = None
+    heading: Optional[float] = None
 
 
 def _header(event: dict, name: str) -> Optional[str]:
@@ -71,6 +72,13 @@ def position(value: Any) -> Optional[dict]:
     return {"latitude": lat, "longitude": lon}
 
 
+def heading_value(value: Any) -> Optional[float]:
+    """The heading the app worked out from the ride's route, in degrees clockwise from north (adr/0013), or None
+    when it is missing or not in [0, 360) (the question still goes ahead without one)."""
+    number = finite_number(value)
+    return number if number is not None and 0 <= number < 360 else None
+
+
 def heading_sample(value: Any) -> Optional[dict]:
     """The older position the heading is taken from, or None when it is missing or broken."""
     point = position(value)
@@ -148,5 +156,6 @@ def parse_ask(event: dict) -> AskInput:
         raise BadRequest("rideId must be a lowercase UUID")
 
     return AskInput(
-        audio, text, position(data.get("location")), heading_sample(data.get("headingSample")), conversation_id, int(volume_db), ride_id
+        audio, text, position(data.get("location")), heading_sample(data.get("headingSample")), conversation_id, int(volume_db), ride_id,
+        heading_value(data.get("headingDegrees")),
     )
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && find . -name __pycache__ -prune -exec \rm -rf {} + && env/bin/pytest -q | tail -1`
Expected: `290 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/request.py src/lib/geo.py src/lib/notes.py src/lib/offline.py src/handlers/ask.py src/handlers/worker.py src/handlers/rides.py src/handlers/ask_edit.py tests/test_geo.py tests/test_request.py tests/test_ask.py tests/test_worker.py tests/test_notes.py tests/test_offline.py
git commit -m "feat: take the heading the app works out from the ride's route, keeping almost north as 0 (#12)"
```

---

### Task 2: 質問できなかった地点の位置と、問い合わせたときの状態（#21・#25）

**Files:**
- Modify: `src/handlers/ask_edit.py`・`src/handlers/result.py`
- Test: `tests/test_offline.py`・`tests/test_result.py`

**Interfaces:**
- Consumes: Task 1 の `settled_heading`（`ask_edit._offline` の中）。
- Produces: `GET /asks/{askId}` の `status` に `offline`（`handlers.result._STATUS` の値）。Task 6 の openapi のテストがこの値の集まりを読む。

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/tests/test_offline.py b/tests/test_offline.py
index 7da0f33..fc50711 100644
--- a/tests/test_offline.py
+++ b/tests/test_offline.py
@@ -152,3 +152,20 @@ def test_a_newer_version_keeps_the_apps_first_heading(aws, places):
     put_offline(offline_body(headingDegrees=270.0))
     result = put_offline(offline_body(headingDegrees=90.0, updatedAt=T2))
     assert answer(result)["applied"] is True and answer(result)["headingDegrees"] == 270.0
+
+
+def test_a_newer_version_keeps_the_first_position(aws, places):
+    # The position is settled on the first PUT, like the place and the heading (Backend #21).
+    put_offline(offline_body())
+    put_offline(offline_body(location=None, headingSample=None, updatedAt=T2))
+    assert store.get_ask(USER, ASK)["location"] == HERE
+    elsewhere = {"latitude": 35.0, "longitude": 139.0}
+    result = put_offline(offline_body(location=elsewhere, updatedAt="2026-10-22T01:20:00.000Z"))
+    assert answer(result)["applied"] is True and answer(result)["address"] == "神奈川県足柄下郡箱根町仙石原"
+    assert store.get_ask(USER, ASK)["location"] == HERE and places == [(HERE["latitude"], HERE["longitude"])]
+
+
+def test_a_position_given_later_is_taken_when_the_first_had_none(aws, places):
+    put_offline(offline_body(location=None, headingSample=None))
+    result = put_offline(offline_body(updatedAt=T2))
+    assert store.get_ask(USER, ASK)["location"] == HERE and answer(result)["address"] == "神奈川県足柄下郡箱根町仙石原"
diff --git a/tests/test_result.py b/tests/test_result.py
index 33845c9..db37beb 100644
--- a/tests/test_result.py
+++ b/tests/test_result.py
@@ -69,3 +69,10 @@ def test_a_failed_ask_without_an_address_or_heading_says_null(aws):
 def test_due_north_is_a_heading_not_null(aws):
     put(status="completed", answer="A", receivedAt="2026-10-16T03:00:00.000Z", headingDegrees=0.0)
     assert json.loads(call()["body"])["headingDegrees"] == 0
+
+
+def test_an_unreached_ask_is_reported_as_offline(aws):
+    # An ask that never reached the Backend is never processed, so it must not look as if it were (Backend #25).
+    put(status="offline", receivedAt="2026-10-16T03:00:00.000Z")
+    body = json.loads(call()["body"])
+    assert body["status"] == "offline" and body["answer"] is None and body["audio"] == []
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_offline.py tests/test_result.py`
Expected: 2件が FAIL（`test_a_newer_version_keeps_the_first_position`・`test_an_unreached_ask_is_reported_as_offline`）。`test_a_position_given_later_is_taken_when_the_first_had_none` は守りのテストで、前から通る。

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/src/handlers/ask_edit.py b/src/handlers/ask_edit.py
index 5b18882..ba44160 100644
--- a/src/handlers/ask_edit.py
+++ b/src/handlers/ask_edit.py
@@ -54,7 +54,8 @@ def _offline(event: dict, user: str, ask_id: str) -> dict:
         if heading is None:
             heading = settled_heading(unreached.heading, unreached.location, unreached.heading_sample,
                                       parse_iso(unreached.asked_at))
-        location = unreached.location
+        # Settled on the first PUT that has one, like the place and the heading (Backend #21).
+        location = (stored or {}).get("location") or unreached.location
         kept = {
             "userName": user,
             "rideId": unreached.ride_id,
diff --git a/src/handlers/result.py b/src/handlers/result.py
index ddff9f9..639904e 100644
--- a/src/handlers/result.py
+++ b/src/handlers/result.py
@@ -8,7 +8,9 @@ from lib import clients, store
 from lib.request import UUID_RE, BadRequest, user_name
 
 PRESIGN_SECONDS = 600
-_STATUS = {"pending": "processing", "processing": "processing", "completed": "completed", "failed": "failed"}
+# An unreached ask is never processed (slice 4 spec §4.4); it is reported as such (Backend #25).
+_STATUS = {"pending": "processing", "processing": "processing", "completed": "completed", "failed": "failed",
+           "offline": "offline"}
 
 
 def handler(event, context):
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && find . -name __pycache__ -prune -exec \rm -rf {} + && env/bin/pytest -q | tail -1`
Expected: `293 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/handlers/result.py src/handlers/ask_edit.py tests/test_result.py tests/test_offline.py
git commit -m "fix: keep an unreached ask's first position, and report it as offline when polled (#21, #25)"
```

---

### Task 3: 削除の試し直しと、跡の読み取り（#23・#24）

**Files:**
- Modify: `src/lib/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: 既存の `store._retrying_conflicts`・`store._sleep`・`store.deleted_key`。
- Produces: `store.has_deletion_mark(user, marks)` の形は変えない（中身を BatchGetItem の1回に）。

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/tests/test_store.py b/tests/test_store.py
index 0524eb9..6bfcab2 100644
--- a/tests/test_store.py
+++ b/tests/test_store.py
@@ -170,3 +170,79 @@ def test_deleting_an_ask_reads_its_ride_consistently(aws, monkeypatch):
     store.delete_ask(USER, ASK, "2026-10-21T01:00:00.000Z")
     assert reads and all(r.get("ConsistentRead") is True for r in reads)
     assert aws.table.get_item(Key=store.deleted_key(USER, "ask", ASK))["Item"]["rideId"] == "r1"
+
+
+def _busy_once(monkeypatch, table, name):
+    real = getattr(table, name)
+    failures = iter([_conflict(name)])
+
+    def busy_once(**params):
+        error = next(failures, None)
+        if error:
+            raise error
+        return real(**params)
+
+    monkeypatch.setattr(table, name, busy_once)
+
+
+def test_deleting_an_ask_during_a_transaction_on_it_is_tried_again(aws, monkeypatch, no_wait):
+    # A memo PUT's transaction on the same ask makes the plain delete fail for a moment (Backend #23).
+    store.create_ask(new_ask(rideId="r1"))
+    _busy_once(monkeypatch, clients.table(), "delete_item")
+    store.delete_ask(USER, ASK, "2026-10-21T01:00:00.000Z")
+    assert store.get_ask(USER, ASK) is None and len(no_wait) == 1
+
+
+def test_deleting_a_note_during_a_transaction_on_it_is_tried_again(aws, monkeypatch, no_wait):
+    aws.table.put_item(Item={**store.note_key(USER, "r1", "n1"), "noteId": "n1", "rideId": "r1"})
+    _busy_once(monkeypatch, clients.table(), "delete_item")
+    store.delete_note(USER, "r1", "n1", "2026-10-21T01:00:00.000Z")
+    assert store.get_note(USER, "r1", "n1") is None and len(no_wait) == 1
+
+
+def _spy_reads(monkeypatch):
+    table = clients.table()
+    client = table.meta.client
+    calls = {"batch": [], "get": []}
+    batch_get_item, get_item = client.batch_get_item, table.get_item
+
+    def batch(**params):
+        calls["batch"].append(params)
+        return batch_get_item(**params)
+
+    def get(**params):
+        calls["get"].append(params)
+        return get_item(**params)
+
+    monkeypatch.setattr(client, "batch_get_item", batch)
+    monkeypatch.setattr(table, "get_item", get)
+    return calls
+
+
+def test_the_marks_are_read_in_one_consistent_batch(aws, monkeypatch):
+    # One read for the record's mark and its ride's, instead of two in turn (Backend #24).
+    calls = _spy_reads(monkeypatch)
+    marks = [("note", "n1"), ("ride", "r1")]
+    assert store.has_deletion_mark(USER, marks) is False
+    store.mark_deleted(USER, "ride", "r1", "2026-10-21T01:00:00.000Z")
+    assert store.has_deletion_mark(USER, marks) is True
+    assert len(calls["batch"]) == 2 and calls["get"] == []
+    request = calls["batch"][0]["RequestItems"][clients.table().name]
+    assert request["ConsistentRead"] is True and len(request["Keys"]) == 2
+
+
+def test_marks_left_unread_are_read_again(aws, monkeypatch, no_wait):
+    client = clients.table().meta.client
+    batch_get_item = client.batch_get_item
+    first = {"done": False}
+
+    def unprocessed_once(**params):
+        if not first["done"]:
+            first["done"] = True
+            return {"Responses": {}, "UnprocessedKeys": params["RequestItems"]}
+        return batch_get_item(**params)
+
+    store.mark_deleted(USER, "note", "n1", "2026-10-21T01:00:00.000Z")
+    monkeypatch.setattr(client, "batch_get_item", unprocessed_once)
+    assert store.has_deletion_mark(USER, [("note", "n1"), ("ride", "r1")]) is True
+    assert len(no_wait) == 1
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_store.py`
Expected: 4件が FAIL（削除が試し直されない・`batch_get_item` が呼ばれない）。

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/src/lib/store.py b/src/lib/store.py
index 96684a3..54f9931 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -60,10 +60,21 @@ def deleted_key(user: str, kind: str, record_id: str) -> dict:
 
 
 def has_deletion_mark(user: str, marks: list) -> bool:
-    """Whether any of the (kind, id) marks exists, read consistently. Used before costly work on a write that would be
-    refused anyway; the write itself still checks the marks in its transaction."""
+    """Whether any of the (kind, id) marks exists, read consistently in one batch (Backend #24). Used before costly
+    work on a write that would be refused anyway; the write itself still checks the marks in its transaction."""
     table = clients.table()
-    return any(table.get_item(Key=deleted_key(user, kind, record_id), ConsistentRead=True).get("Item") for kind, record_id in marks)
+    keys = [deleted_key(user, kind, record_id) for kind, record_id in marks]
+    request = {table.name: {"Keys": keys, "ConsistentRead": True, "ProjectionExpression": "pk"}} if keys else {}
+    attempt = 0
+    while request:
+        if attempt:
+            _sleep(0.05 * 2 ** (attempt - 1))
+        page = table.meta.client.batch_get_item(RequestItems=request)
+        if page.get("Responses", {}).get(table.name):
+            return True
+        request = page.get("UnprocessedKeys") or {}
+        attempt += 1
+    return False
 
 
 def _retrying_conflicts(write: Callable[[], Any]) -> Any:
@@ -288,6 +299,7 @@ def _query_keys(user: str, prefix: str, ride_id: Optional[str] = None) -> list:
 
 
 def _delete_all(keys: list) -> None:
+    # The batch writer sends again what DynamoDB leaves unprocessed (UnprocessedItems), so no retry is added here.
     with clients.table().batch_writer() as batch:
         for key in keys:
             batch.delete_item(Key={"pk": key["pk"], "sk": key["sk"]})
@@ -298,12 +310,13 @@ def delete_ask(user: str, ask_id: str, deleted_at: str) -> None:
     # The ask may have been written a moment ago; its mark must still name its ride (Backend #18).
     stored = get_ask(user, ask_id, consistent=True)
     mark_deleted(user, "ask", ask_id, deleted_at, ride_id=(stored or {}).get("rideId"))
-    clients.table().delete_item(Key=ask_key(user, ask_id))
+    # A memo PUT's transaction on the ask makes the delete fail for a moment (Backend #23).
+    _retrying_conflicts(lambda: clients.table().delete_item(Key=ask_key(user, ask_id)))
 
 
 def delete_note(user: str, ride_id: str, note_id: str, deleted_at: str) -> None:
     mark_deleted(user, "note", note_id, deleted_at, ride_id=ride_id)
-    clients.table().delete_item(Key=note_key(user, ride_id, note_id))
+    _retrying_conflicts(lambda: clients.table().delete_item(Key=note_key(user, ride_id, note_id)))
 
 
 def delete_ride(user: str, ride_id: str, deleted_at: str) -> dict:
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && find . -name __pycache__ -prune -exec \rm -rf {} + && env/bin/pytest -q | tail -1`
Expected: `297 passed`（地点メモと質問できなかった地点の跡のテストも、そのまま通る）

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/store.py tests/test_store.py
git commit -m "fix: try a delete again when a transaction on the record is in progress, and read deletion marks in one batch (#23, #24)"
```

---

### Task 4: 改行入りの base64・長すぎる cursor・JSON でない本文のテスト（#6・#22・#13）

**Files:**
- Modify: `src/lib/request.py`・`src/lib/records.py`
- Test: `tests/test_request.py`・`tests/test_records.py`・`tests/test_rides.py`

**Interfaces:**
- Produces: `lib.records.MAX_SORT_KEY_BYTES = 1024`。

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/tests/test_records.py b/tests/test_records.py
index de05b12..cbac59e 100644
--- a/tests/test_records.py
+++ b/tests/test_records.py
@@ -134,7 +134,10 @@ def test_a_cursor_never_reads_another_users_records(aws):
 
 
 @pytest.mark.parametrize("cursor", ["", "!!!", base64.urlsafe_b64encode(b"[1]").decode(),
-                                    base64.urlsafe_b64encode(b'{"sk": ""}').decode()])
+                                    base64.urlsafe_b64encode(b'{"sk": ""}').decode(),
+                                    # DynamoDB refuses a sort key over 1024 bytes as a start key (Backend #22).
+                                    base64.urlsafe_b64encode(json.dumps({"sk": "A" * 1025}).encode()).decode()],
+                         ids=["empty", "not base64", "not an object", "empty key", "key too long"])
 def test_a_bad_cursor_is_400(aws, cursor):
     result = read(cursor)
     assert result["statusCode"] == 400 and json.loads(result["body"])["error"] == "bad_request"
diff --git a/tests/test_request.py b/tests/test_request.py
index 50ab0f7..8d7fde7 100644
--- a/tests/test_request.py
+++ b/tests/test_request.py
@@ -60,6 +60,13 @@ def test_audio_length_and_alignment(audio):
         parse_ask(event({"audio": b64(audio)}))
 
 
+def test_audio_base64_with_line_breaks_is_read():
+    # Some encoders break base64 into lines of 76 characters (Backend #6).
+    text = b64(b"\x01\x02" * MIN_AUDIO_BYTES)
+    wrapped = "\n".join(text[i:i + 76] for i in range(0, len(text), 76)) + "\n"
+    assert parse_ask(event({"audio": wrapped})).audio == b"\x01\x02" * MIN_AUDIO_BYTES
+
+
 def test_audio_not_base64():
     with pytest.raises(BadRequest, match="base64"):
         parse_ask(event({"audio": "not base64!!"}))
diff --git a/tests/test_rides.py b/tests/test_rides.py
index bd363b0..0ff6d2c 100644
--- a/tests/test_rides.py
+++ b/tests/test_rides.py
@@ -126,6 +126,8 @@ def test_a_body_that_is_not_json_is_400(aws):
     assert rides.handler(event, None)["statusCode"] == 400
     event["pathParameters"]["seq"] = "0"
     assert rides.handler(event, None)["statusCode"] == 400
+    # Refused before anything is written (Backend #13).
+    assert aws.table.scan()["Items"] == []
 
 
 def test_a_bad_ride_id_or_user_is_400(aws):
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_request.py tests/test_records.py tests/test_rides.py`
Expected: 2件が FAIL（`test_audio_base64_with_line_breaks_is_read`・`test_a_bad_cursor_is_400[key too long]`）。`test_a_body_that_is_not_json_is_400` に足した確かめ（#13）は守りのテストで、前から通る。

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/src/lib/records.py b/src/lib/records.py
index 6b95967..0b799df 100644
--- a/src/lib/records.py
+++ b/src/lib/records.py
@@ -8,6 +8,9 @@ from typing import Optional
 
 from lib.request import BadRequest
 
+# DynamoDB refuses a longer sort key in ExclusiveStartKey (Backend #22).
+MAX_SORT_KEY_BYTES = 1024
+
 # As GET /asks/{askId} answers, plus the unreached asks the app sent (slice 4 spec §4.4).
 _ASK_STATUS = {"pending": "processing", "processing": "processing", "completed": "completed", "failed": "failed",
                "offline": "offline"}
@@ -25,7 +28,8 @@ def decode_cursor(text: Optional[str]) -> Optional[str]:
         data = json.loads(base64.urlsafe_b64decode(text.encode("ascii") + b"=" * (-len(text) % 4)))
     except (ValueError, binascii.Error, UnicodeError):
         raise BadRequest("cursor must be one that GET /records returned") from None
-    if not isinstance(data, dict) or not isinstance(data.get("sk"), str) or not data["sk"]:
+    if not isinstance(data, dict) or not isinstance(data.get("sk"), str) or not data["sk"] \
+            or len(data["sk"].encode("utf-8")) > MAX_SORT_KEY_BYTES:
         raise BadRequest("cursor must be one that GET /records returned")
     return data["sk"]
 
diff --git a/src/lib/request.py b/src/lib/request.py
index d17acce..3c0e349 100644
--- a/src/lib/request.py
+++ b/src/lib/request.py
@@ -113,7 +113,8 @@ def pcm_audio(audio_b64: Any) -> bytes:
     if not isinstance(audio_b64, str):
         raise BadRequest("audio must be base64")
     try:
-        audio = base64.b64decode(audio_b64, validate=True)
+        # Line breaks and spaces are dropped first: some encoders wrap base64 at 76 characters (Backend #6).
+        audio = base64.b64decode("".join(audio_b64.split()), validate=True)
     except (binascii.Error, ValueError):
         raise BadRequest("audio must be base64") from None
     if not MIN_AUDIO_BYTES <= len(audio) <= MAX_AUDIO_BYTES or len(audio) % 2:
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && find . -name __pycache__ -prune -exec \rm -rf {} + && env/bin/pytest -q | tail -1`
Expected: `299 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/records.py src/lib/request.py tests/test_records.py tests/test_rides.py tests/test_request.py
git commit -m "fix: read base64 audio with line breaks, refuse a cursor whose key is too long, and check nothing is written for a body that is not JSON (#6, #22, #13)"
```

---

### Task 5: Agent のエラーの文と、セッションの識別子の説明（#8・#14）

**Files:**
- Modify: `src/lib/agent.py`
- Test: `tests/test_agent.py`・`tests/test_worker.py`

**Interfaces:**
- Produces: `AgentError` の `str()` は短い符号だけ（`agent_failed` など。無ければ `agent_error`・`runtime_error`）。

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/tests/test_agent.py b/tests/test_agent.py
index dbcd654..23cf0b4 100644
--- a/tests/test_agent.py
+++ b/tests/test_agent.py
@@ -29,14 +29,26 @@ def test_parse_ignores_noise_lines():
     assert reply.answer == "晴れです。"
 
 
-def test_error_event_raises():
-    with pytest.raises(AgentError, match="agent_failed: empty answer"):
-        parse_events(sse({"type": "error", "code": "agent_failed", "message": "empty answer"}))
-
-
-def test_runtime_level_error_shape_raises():
-    with pytest.raises(AgentError, match="boom"):
-        parse_events(sse({"error": "boom", "error_type": "RuntimeError"}))
+def test_error_event_raises_with_its_code_only():
+    # The message may carry part of the input, so it is not kept for the log (Backend #8).
+    with pytest.raises(AgentError) as raised:
+        parse_events(sse({"type": "error", "code": "agent_failed", "message": "右手の山は？ was too long"}))
+    assert str(raised.value) == "agent_failed"
+
+
+def test_runtime_level_error_shape_raises_with_its_type_only():
+    with pytest.raises(AgentError) as raised:
+        parse_events(sse({"error": "boom near 東京駅", "error_type": "RuntimeError"}))
+    assert str(raised.value) == "RuntimeError"
+
+
+def test_an_error_without_a_code_or_type_says_so():
+    with pytest.raises(AgentError) as raised:
+        parse_events(sse({"type": "error", "message": "x"}))
+    assert str(raised.value) == "agent_error"
+    with pytest.raises(AgentError) as raised:
+        parse_events(sse({"error": "x"}))
+    assert str(raised.value) == "runtime_error"
 
 
 def test_missing_or_empty_done_raises():
diff --git a/tests/test_worker.py b/tests/test_worker.py
index 44cbc6c..16923e8 100644
--- a/tests/test_worker.py
+++ b/tests/test_worker.py
@@ -1,10 +1,11 @@
 """Tests for the worker pipeline with stubbed steps and moto storage."""
+import json
 from datetime import datetime, timedelta, timezone
 
 from handlers import worker
 from handlers.common import iso
 from lib import store
-from lib.agent import AgentError, AgentReply, session_id
+from lib.agent import AgentError, AgentReply, parse_events, session_id
 
 USER, ASK, CID = "rider01", "11111111-1111-4111-8111-111111111111", "33333333-3333-4333-8333-333333333333"
 T0 = datetime(2026, 10, 16, 3, 0, tzinfo=timezone.utc)
@@ -139,13 +140,25 @@ def test_transcribe_failure_deletes_audio(aws):
 
 def test_agent_failure(aws):
     put(aws)
-    rec = Recorder(agent_error=AgentError("agent_failed: empty answer"))
+    rec = Recorder(agent_error=AgentError("agent_failed"))
     worker.process(USER, ASK, rec.steps())
     item = store.get_ask(USER, ASK)
     assert item["status"] == "failed" and item["error"] == "agent_failed" and item["transcript"] == "右手の山は？"
     assert "tts" not in kinds(rec)
 
 
+def test_the_agent_error_log_has_the_code_only(aws, capsys):
+    # The agent's message may carry part of the question; only its code is logged (Backend #8).
+    put(aws)
+    try:
+        parse_events([b'data: {"type": "error", "code": "agent_failed", "message": "\\u53f3\\u624b"}'])
+    except AgentError as error:
+        raised = error
+    worker.process(USER, ASK, Recorder(agent_error=raised).steps())
+    logged = [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"agent_error"' in line]
+    assert logged and logged[0]["error"] == "agent_failed"
+
+
 def test_tts_failure_keeps_answer(aws):
     put(aws)
     rec = Recorder(tts_error=RuntimeError("polly down"))
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_agent.py tests/test_worker.py`
Expected: 4件が FAIL（文が `agent_failed: 右手の山は？ was too long` のように Agent の `message` を含む）。

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/src/lib/agent.py b/src/lib/agent.py
index f7d45e5..d97c391 100644
--- a/src/lib/agent.py
+++ b/src/lib/agent.py
@@ -19,12 +19,14 @@ _RETRYABLE = "RetryableConflictException"
 def session_id(user: str, conversation_id: str) -> str:
     """The runtime session of one user's conversation. Another user sending the same conversationId gets a session
     of their own, so nobody reaches someone else's context by knowing the ID (Backend issue #4). 64 hex characters,
-    inside the runtime's 33-100."""
+    inside the 33-256 that InvokeAgentRuntime takes for runtimeSessionId (Backend #14)."""
     return hashlib.sha256(f"{user}:{conversation_id}".encode("utf-8")).hexdigest()
 
 
 class AgentError(RuntimeError):
-    """The agent did not produce an answer; reported as agent_failed."""
+    """The agent did not produce an answer; reported as agent_failed. Its text is a short code (the agent's error
+    code, an AWS error code or an exception's type name), never the agent's message, which may carry part of the
+    input and is logged as is (Backend #8)."""
 
 
 @dataclass
@@ -58,10 +60,10 @@ def parse_events(lines: Iterable[Any], clock: Callable[[], float] = time.time) -
         elif kind == "done":
             done = event
         elif kind == "error":
-            raise AgentError(f"{event.get('code')}: {event.get('message')}")
+            raise AgentError(str(event.get("code") or "agent_error"))
         elif kind is None and "error" in event:
             # The runtime's own error shape when the entrypoint raised.
-            raise AgentError(str(event["error"]))
+            raise AgentError(str(event.get("error_type") or "runtime_error"))
     if done is None or not str(done.get("answer", "")).strip():
         raise AgentError("no answer")
     return AgentReply(
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && find . -name __pycache__ -prune -exec \rm -rf {} + && env/bin/pytest -q | tail -1`
Expected: `301 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/agent.py tests/test_agent.py tests/test_worker.py
git commit -m "fix: log only the agent's error code, and state the runtime session id limits from the API reference (#8, #14)"
```

---

### Task 6: SSM の設定値の名前と、API の正本（#7）

**Files:**
- Modify: `template.yaml`・`samconfig.toml`・親の `docs/07a_openapi.yaml`（`docs-parent/` へ写す）
- Create: `tests/test_template.py`
- Test: `tests/test_openapi.py`・`tests/test_template.py`

**Interfaces:**
- Consumes: Task 2 の `handlers.result._STATUS`。

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/tests/test_openapi.py b/tests/test_openapi.py
index cbaffb9..f289b63 100644
--- a/tests/test_openapi.py
+++ b/tests/test_openapi.py
@@ -48,6 +48,20 @@ def test_the_ride_limits_match_the_validation():
     assert schemas["RouteChunk"]["properties"]["points"]["maxItems"] == rides.MAX_POINTS
 
 
+def test_the_ask_statuses_match_the_result():
+    from handlers import result
+    statuses = SPEC["components"]["schemas"]["AskResult"]["properties"]["status"]["enum"]
+    assert set(statuses) == set(result._STATUS.values())
+
+
+def test_the_heading_is_taken_on_every_path_that_takes_a_sample():
+    # adr/0013: the app sends the heading it worked out wherever it used to send a sample.
+    schemas = SPEC["components"]["schemas"]
+    for name in ("AskRequest", "NoteRequest", "OfflineAskRequest"):
+        properties = schemas[name]["properties"]
+        assert "headingSample" in properties and properties["headingDegrees"]["type"] == "number"
+
+
 def test_error_reasons_match_contract():
     reasons = SPEC["components"]["schemas"]["AskResult"]["properties"]["error"]["enum"]
     assert set(reasons) - {None} == {"no_speech", "transcribe_failed", "agent_failed", "tts_failed"}
diff --git a/tests/test_template.py b/tests/test_template.py
new file mode 100644
index 0000000..a151bde
--- /dev/null
+++ b/tests/test_template.py
@@ -0,0 +1,38 @@
+"""The stack's settings are chosen per environment (Backend #7)."""
+import tomllib
+from pathlib import Path
+
+import yaml
+
+ROOT = Path(__file__).parent.parent
+SSM_NAMES = ("AgentRuntimeArn", "ConversationResetParameter")
+
+
+class _CfnLoader(yaml.SafeLoader):
+    """Reads CloudFormation's short tags (!Ref, !Sub, ...) as plain values."""
+
+
+_CfnLoader.add_multi_constructor("!", lambda loader, suffix, node: None)
+
+
+def _template() -> dict:
+    return yaml.load((ROOT / "template.yaml").read_text(encoding="utf-8"), Loader=_CfnLoader)
+
+
+def _overrides() -> dict:
+    config = tomllib.loads((ROOT / "samconfig.toml").read_text(encoding="utf-8"))
+    pairs = config["default"]["deploy"]["parameters"]["parameter_overrides"].split()
+    return dict(pair.split("=", 1) for pair in pairs)
+
+
+def test_the_ssm_names_have_no_default():
+    # A default names one environment's parameters; another environment would silently use them.
+    parameters = _template()["Parameters"]
+    assert all("Default" not in parameters[name] for name in SSM_NAMES)
+
+
+def test_the_dev_deploy_names_the_dev_parameters():
+    overrides = _overrides()
+    assert overrides["Environment"] == "dev"
+    assert overrides["AgentRuntimeArn"] == "/trv2/dev/agent-runtime-arn"
+    assert overrides["ConversationResetParameter"] == "/trv2/dev/conversation-reset-minutes"
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_template.py tests/test_openapi.py`
Expected: 2件が FAIL（`test_the_ssm_names_have_no_default`・`test_the_dev_deploy_names_the_dev_parameters`）。openapi に足した2件は守りのテストで、前から通る（`headingDegrees` は spec のコミットで 07a に足してある。`offline` は Task 2 で足し、下の Step 3 で 07a にも書く）。

- [ ] **Step 3: テンプレートと samconfig を直す**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/samconfig.toml b/samconfig.toml
index a8c7179..30f52f3 100644
--- a/samconfig.toml
+++ b/samconfig.toml
@@ -13,4 +13,4 @@ resolve_s3 = true
 s3_prefix = "stack-trv2-dev-backend"
 confirm_changeset = false
 fail_on_empty_changeset = false
-parameter_overrides = "Environment=dev"
+parameter_overrides = "Environment=dev AgentRuntimeArn=/trv2/dev/agent-runtime-arn ConversationResetParameter=/trv2/dev/conversation-reset-minutes"
diff --git a/template.yaml b/template.yaml
index 7542a39..2dd493c 100644
--- a/template.yaml
+++ b/template.yaml
@@ -7,16 +7,17 @@ Parameters:
     Type: String
     Default: dev
     AllowedValues: [dev, prod]
+  # No defaults: each environment names its own parameters in samconfig.toml, so that a new environment cannot
+  # silently use another's (Backend #7).
   AgentRuntimeArn:
     Type: AWS::SSM::Parameter::Value<String>
-    Default: /trv2/dev/agent-runtime-arn
-    Description: Name of the SSM parameter (Tokyo) holding the agent runtime ARN; written by the Agent deploy.
+    Description: Name of the SSM parameter (Tokyo) holding the agent runtime ARN, /trv2/<env>/agent-runtime-arn; written by the Agent deploy.
   AgentRegion:
     Type: String
     Default: us-east-1
   ConversationResetParameter:
     Type: String
-    Default: /trv2/dev/conversation-reset-minutes
+    Description: Name of the SSM parameter (Tokyo) holding the conversation reset minutes, /trv2/<env>/conversation-reset-minutes.
   DailyQuota:
     Type: Number
     Default: 3000
PATCH
```

- [ ] **Step 4: 親の文書を写す**

親の `docs/07a_openapi.yaml`（`offline` の enum と説明・base64 の2か所・質問できなかった地点の位置）と `docs/07_units_contracts.md`（同じ3点）は、この plan のコミットで直してある。Backend へ写す。

```bash
cd $ROOT && scripts/sync-docs.sh Backend && cd $BE && git status --short docs-parent
```

Expected: `synced: Backend`。`docs-parent/07a_openapi.yaml` と `docs-parent/07_units_contracts.md` だけが変わる。写した 07a の差分は次のとおり（確かめ用。当てるのではない）。

```diff
diff --git a/docs-parent/07a_openapi.yaml b/docs-parent/07a_openapi.yaml
index dbadd4f..d992b39 100644
--- a/docs-parent/07a_openapi.yaml
+++ b/docs-parent/07a_openapi.yaml
@@ -493,7 +493,7 @@ components:
         audio:
           type: string
           format: byte
-          description: PCM（16kHz・モノラル・16bit リトルエンディアン）の base64。0.25〜60秒。
+          description: PCM（16kHz・モノラル・16bit リトルエンディアン）の base64（改行と空白は無視する）。0.25〜60秒。
         text:
           type: string
           minLength: 1
@@ -555,7 +555,8 @@ components:
           format: uuid
         status:
           type: string
-          enum: [processing, completed, failed]
+          enum: [processing, completed, failed, offline]
+          description: offline は質問できなかった地点（PUT /asks/{askId}/offline で置いたもの）。処理されないので、回答は来ない
         transcript:
           type: string
           nullable: true
@@ -712,7 +713,7 @@ components:
         audio:
           type: string
           format: byte
-          description: PCM（16kHz・モノラル・16bit リトルエンディアン）の base64。0.25〜60秒。文字にしたら消す
+          description: PCM（16kHz・モノラル・16bit リトルエンディアン）の base64（改行と空白は無視する）。0.25〜60秒。文字にしたら消す
     TranscriptionResult:
       type: object
       required: [transcriptionId, status, text, failure]
@@ -774,7 +775,7 @@ components:
           allOf:
             - $ref: "#/components/schemas/Point"
           nullable: true
-          description: 録音を終えたときの位置。まだ位置が無ければ null。不正な位置は 400
+          description: 録音を終えたときの位置。まだ位置が無ければ null。不正な位置は 400。最初に位置を受けたあとは、あとの版の位置を使わない（住所・方位と同じ）
         headingDegrees:
           type: number
           nullable: true
```

- [ ] **Step 5: 通ることを確かめる**

Run: `cd $BE && find . -name __pycache__ -prune -exec \rm -rf {} + && env/bin/pytest -q | tail -1 && sam validate --lint`
Expected: `305 passed`、`template.yaml is a valid SAM Template`

- [ ] **Step 6: コミット**

```bash
cd $BE && git add template.yaml samconfig.toml tests/test_template.py tests/test_openapi.py docs-parent/07a_openapi.yaml docs-parent/07_units_contracts.md
git commit -m "fix: name each environment's SSM parameters in its deploy settings, and describe offline asks and wrapped base64 in the API (#7)"
```

---

### Task 7: smoke

**Files:**
- Modify: `scripts/smoke.py`

- [ ] **Step 1: smoke を直す**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/scripts/smoke.py b/scripts/smoke.py
index c996ebc..0077459 100644
--- a/scripts/smoke.py
+++ b/scripts/smoke.py
@@ -102,11 +102,13 @@ def ride_checks(api: str, key: str, ride_id: str) -> list[bool]:
 
 def note_checks(api: str, key: str, ride_id: str, note_id: str) -> list[bool]:
     results = []
-    note = {"at": minutes_ago(15), "location": TOKYO_STATION, "headingSample": {**SOUTH_60M, "at": minutes_ago(15)},
+    # The heading the app works out from the ride's route (adr/0013).
+    note = {"at": minutes_ago(15), "location": TOKYO_STATION, "headingDegrees": 270.0,
             "text": "smoke の地点メモ", "updatedAt": minutes_ago(15)}
     url = f"{api}/rides/{ride_id}/notes/{note_id}"
     status, body = request("PUT", url, key, USER, note)
-    results.append(check("note saved with its place", status == 200 and body.get("applied") is True and bool(body.get("address")),
+    ok = status == 200 and body.get("applied") is True and bool(body.get("address")) and body.get("headingDegrees") == 270.0
+    results.append(check("note saved with its place and the app's heading", ok,
                          f"{status} address={body.get('address')} heading={body.get('headingDegrees')}"))
     status, body = request("PUT", url, key, USER, {**note, "text": "older", "updatedAt": minutes_ago(20)})
     results.append(check("older note ignored", status == 200 and body.get("applied") is False and bool(body.get("address")), str(status)))
@@ -127,7 +129,9 @@ def memo_checks(api: str, key: str, ask_id: str) -> list[bool]:
 
 
 def transcription_check(api: str, key: str, audio_b64: str) -> bool:
-    status, accepted = request("POST", f"{api}/transcriptions", key, USER, {"audio": audio_b64})
+    # Wrapped at 76 characters, as some encoders do (Backend #6).
+    wrapped = "\n".join(audio_b64[i:i + 76] for i in range(0, len(audio_b64), 76))
+    status, accepted = request("POST", f"{api}/transcriptions", key, USER, {"audio": wrapped})
     if status != 202:
         return check("point memo voice transcribed", False, str(status))
     start = time.monotonic()
@@ -143,6 +147,7 @@ def transcription_check(api: str, key: str, audio_b64: str) -> bool:
 
 def offline_checks(api: str, key: str, ride_id: str, offline_id: str, taken_id: str) -> list[bool]:
     url = f"{api}/asks/{offline_id}/offline"
+    # The older form of the heading, as an app before adr/0013 left it unsent.
     unreached = {"askedAt": minutes_ago(12), "location": TOKYO_STATION, "headingSample": {**SOUTH_60M, "at": minutes_ago(12)},
                  "rideId": ride_id, "updatedAt": minutes_ago(12)}
     status, body = request("PUT", url, key, USER, unreached)
@@ -154,6 +159,9 @@ def offline_checks(api: str, key: str, ride_id: str, offline_id: str, taken_id:
     results.append(check("memo on an unreached ask", status == 200 and body.get("applied") is True, str(status)))
     status, body = request("PUT", f"{api}/asks/{taken_id}/offline", key, USER, unreached)
     results.append(check("unreached ask over a taken ask is 409", status == 409 and body == {"error": "conflict"}, str(status)))
+    status, body = request("GET", f"{api}/asks/{offline_id}", key, USER)
+    results.append(check("polled unreached ask is offline", status == 200 and body.get("status") == "offline",
+                         f"{status} status={body.get('status')}"))
     return results
 
 
@@ -242,7 +250,7 @@ def main() -> int:
     results.extend(note_checks(api, key, ride_id, note_id))
 
     accepted, result, elapsed = ask_and_wait(
-        api, key, {"text": "富士山の高さは？", "location": TOKYO_STATION, "headingSample": sample(10), "rideId": ride_id}
+        api, key, {"text": "富士山の高さは？", "location": TOKYO_STATION, "headingDegrees": 123.4, "rideId": ride_id}
     )
     ok = result.get("status") == "completed" and bool(result.get("answer")) and len(result.get("audio", [])) == 1
     results.append(check("text question", ok, f"{elapsed:.1f}s answer={result.get('answer')} error={result.get('error')}"))
@@ -251,8 +259,8 @@ def main() -> int:
             audio_ok = res.status == 200 and res.headers.get("Content-Type") == "audio/mpeg" and len(res.read()) > 1000
         results.append(check("answer audio download", audio_ok))
     print("      timings:", json.dumps(result.get("timings"), ensure_ascii=False))
-    ok = bool(result.get("askedAt")) and bool(result.get("address")) and result.get("headingDegrees") is not None
-    results.append(check("ask has when, where and heading", ok,
+    ok = bool(result.get("askedAt")) and bool(result.get("address")) and result.get("headingDegrees") == 123.4
+    results.append(check("ask has when, where and the app's heading", ok,
                          f"askedAt={result.get('askedAt')} address={result.get('address')} heading={result.get('headingDegrees')}"))
     conversation_id = accepted.get("conversationId")
     expires = accepted.get("conversationExpiresAt")
PATCH
```

- [ ] **Step 2: 構文を確かめる**

Run: `cd $BE && env/bin/python -m py_compile scripts/smoke.py && env/bin/pytest -q | tail -1`
Expected: エラー無し。`305 passed`（smoke はデプロイしたあとの Task 9 で回す）

- [ ] **Step 3: コミット**

```bash
cd $BE && git add scripts/smoke.py
git commit -m "test: check the app's heading, offline polling and wrapped base64 in the smoke run"
```

---

### Task 8: 文書（Backend の README・PROJECT.md）

**Files:**
- Modify: `README.md`・親の `PROJECT.md`

親の 07・07a は、この plan のコミットで直してあり、Task 6 で写した。

- [ ] **Step 1: Backend の README を直す**

```bash
cd $BE && git apply <<'PATCH'
diff --git a/README.md b/README.md
index f1034dc..318e165 100644
--- a/README.md
+++ b/README.md
@@ -1,7 +1,7 @@
 # TouringProjectV2_Backend
 
 TouringProjectV2 の API（API Gateway＋Lambda・Python・SAM・`ap-northeast-1`）。
-App から質問（PCM の音声か文字）と位置を受け付け、文字起こし・住所と方位の確定・Agent の呼び出し・読み上げ音声の生成を行い、結果を返す。
+App から質問（PCM の音声か文字）と位置と進行方位を受け付け、文字起こし・住所の確定・Agent の呼び出し・読み上げ音声の生成を行い、結果を返す。進行方位は App が走行のルートから求めて送る（親の adr/0013）。
 走行・ルート・メモ・地点メモ・質問できなかった地点と、それらの削除を受け取り、ユーザー名ごとに置く。引き継ぎのときは、ユーザーの記録をページ送りで返す。
 プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し。編集しない）。
 
@@ -18,12 +18,12 @@ App から質問（PCM の音声か文字）と位置を受け付け、文字起
 ## 流れ
 
 1. `POST /asks` が入力を検証し、録音を S3（`audio/`・1日で消える）に置き、記録を `pending` で作り、SQS に積む。会話を区切る時刻を SSM `/trv2/dev/conversation-reset-minutes`（既定15・55以下）から求めて返す。SQS に積めなかったときは、記録と録音を消して 503 を返す（App は通信の失敗として扱う）。会話の記録（`CONV#`）は TTL（`expiresAt`）で1日後に消える。
-2. worker が受け持ちを獲得し（条件付き書き込み）、文字起こし（ストリーミング）→ 住所（Location Service）・方位・日時 → Agent（us-east-1・`runtimeSessionId` はユーザー名と会話の識別子から作る SHA-256）→ Polly（Kazuha・DRC と +6dB）の順に処理し、記録を `completed` か `failed` にする。
-3. App は `GET /asks/{askId}` をポーリングし、回答の文と音声の署名付き URL（10分有効）を受け取る。
+2. worker が受け持ちを獲得し（条件付き書き込み）、文字起こし（ストリーミング）→ 住所（Location Service）・方位（App の `headingDegrees`。無ければ古い形の `headingSample` から求める。0.1度に丸め、360は0）・日時 → Agent（us-east-1・`runtimeSessionId` はユーザー名と会話の識別子から作る SHA-256）→ Polly（Kazuha・DRC と +6dB）の順に処理し、記録を `completed` か `failed` にする。
+3. App は `GET /asks/{askId}` をポーリングし、回答の文と音声の署名付き URL（10分有効）を受け取る。質問できなかった地点を問い合わせると、状態は `offline` になる。
 4. 走行: App は走行のメタ情報（走行のメモを含む）を `PUT /rides/{rideId}` で、ルートの点を300点までのかたまりにして `PUT /rides/{rideId}/route/{seq}` で置く。メタ情報は `updatedAt` が保存済みより新しいときだけ上書きする（古ければ `applied: false` の 200）。
-5. メモと地点メモ: 会話のメモは `PUT /asks/{askId}/memo`、地点メモは `PUT /rides/{rideId}/notes/{noteId}` で置く。どちらも `updatedAt` が新しいときだけ書く。地点メモの住所と方位は、最初に受けたときに質問と同じ求め方で決めて返す。
+5. メモと地点メモ: 会話のメモは `PUT /asks/{askId}/memo`、地点メモは `PUT /rides/{rideId}/notes/{noteId}` で置く。どちらも `updatedAt` が新しいときだけ書く。地点メモの住所は最初に受けたときに質問と同じ求め方で決め、方位は最初に受けた App の値を残して返す。
 6. 削除: `DELETE` を受けると、先に削除の跡（`DELETED#<ASK|RIDE|NOTE>#<id>`・期限なし）を書いてから消す。走行を消すと、ルート・地点メモ・その走行の質問も消し、地点メモと質問にも跡を残す。跡のある記録（と、跡のある走行の下の記録）への `PUT` は、書き込みと跡の確かめを1つのトランザクションにして、書かずに 410 を返す。
-7. 質問できなかった地点: App は、Backend に届かなかった質問の日時・位置・方位の材料を、自分で作った `askId` で `PUT /asks/{askId}/offline` に置く。`status: "offline"` の質問として、地点メモと同じく住所と方位を最初に決める。メモと削除は、ほかの質問と同じ経路を使う。
+7. 質問できなかった地点: App は、Backend に届かなかった質問の日時・位置・方位を、自分で作った `askId` で `PUT /asks/{askId}/offline` に置く。`status: "offline"` の質問として、地点メモと同じく位置・住所・方位を最初に決め、あとの版では変えない。メモと削除は、ほかの質問と同じ経路を使う。
 8. 引き継ぎ: `GET /records` が、ユーザーのパーティションを強い一貫性でソートキーの順に読み、走行・ルート・地点メモ・質問・削除の跡を `kind` つきで返す。1ページは1回の問い合わせ（最大1MB）で、続きは `cursor` で読む（`cursor` には続きのソートキーだけを入れ、パーティションは `x-user-name` から作る）。
 9. 地点メモの声: `POST /transcriptions` が録音を S3 に置いて SQS に積み、worker が文字起こしだけを行う（AI と読み上げは呼ばない）。App は `GET /transcriptions/{transcriptionId}` をポーリングする。記録は DynamoDB の TTL（`expiresAt`）で1日後に消える。
 
@@ -38,6 +38,8 @@ env/bin/pytest
 
 前提: Agent がデプロイ済みで、SSM `/trv2/dev/agent-runtime-arn`（東京）がある。
 
+SSM のパラメーターの名前（`AgentRuntimeArn`・`ConversationResetParameter`）は、テンプレートに既定値を持たせず、`samconfig.toml` の環境ごとの `parameter_overrides` で渡す。別の環境を作るときは、その環境の名前（`/trv2/<環境>/...`）を書いた設定を足す。渡し忘れると、デプロイがエラーで止まる。
+
 ```sh
 AWS_PROFILE=touring sam build && AWS_PROFILE=touring sam deploy
 AWS_PROFILE=touring env/bin/python scripts/smoke.py
PATCH
```

- [ ] **Step 2: テストを回して、Backend にコミット**

```bash
cd $BE && env/bin/pytest -q | tail -1
git add README.md
git commit -m "docs: describe the app's heading, offline polling and per-environment SSM names in the README"
```

Expected: `305 passed`

- [ ] **Step 3: 親の PROJECT.md を直して、親にコミット**

`$ROOT/PROJECT.md` の「スライス5」の plan 表の1の行の状態を「実装済み（確認待ち: デプロイと smoke）」にする。「次にやること」は「plan 1 のデプロイと smoke（Task 9）」にする。

```bash
cd $ROOT && git add PROJECT.md Backend
git commit -m "docs: record slice 5 plan 1 as implemented, awaiting the deploy and smoke"
```

---

### Task 9: デプロイと smoke

- [ ] **Step 1: 利用者に、デプロイしてよいかを確かめる**

デプロイの中身（Lambda のコードの差し替えと、テンプレートの引数を samconfig から渡すこと）を伝え、明示の了承を得る。了承が無ければここで止まる。

- [ ] **Step 2: デプロイする**

Run: `cd $BE && AWS_PROFILE=touring sam build && AWS_PROFILE=touring sam deploy`
Expected: `Successfully created/updated stack - stack-trv2-dev-backend`。資格情報の誤り（`The security token included in the request is invalid`）なら、利用者に直してもらってから回し直す。

- [ ] **Step 3: smoke を回す**

Run: `cd $BE && AWS_PROFILE=touring env/bin/python scripts/smoke.py`
Expected: `40/40 passed`。デプロイの直後に新しい経路だけが 403 なら、1分ほど待って回し直す（PROJECT.md の持ち越し）。

- [ ] **Step 4: 結果を PROJECT.md に書いて、親にコミット**

`$ROOT/PROJECT.md` の plan 表の1の行を「✅ 完了（デプロイ済み・smoke 40/40）」にし、「次にやること」を plan 2（Agent）の writing-plans にする。

```bash
cd $ROOT && git add PROJECT.md && git commit -m "docs: record slice 5 plan 1 as deployed with smoke 40/40"
```

最終レビュー・後回しの指摘の書き出し・finishing は、CLAUDE.md の区切り点のとおりに行う。
