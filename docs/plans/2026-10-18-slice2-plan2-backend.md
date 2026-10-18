# スライス2 計画2: Backend（走行の受け口と質問の API の追加） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend が、走行のメタ情報（`PUT /rides/{rideId}`）とルートの点のかたまり（`PUT /rides/{rideId}/route/{seq}`）をユーザー名ごとに受け取って DynamoDB に置き、質問に走行の識別子（`rideId`）を添えられ、質問の結果に受け付けた日時・住所・方位を返す。あわせて、Agent のセッションをユーザーごとに分け、他人の会話の ID を知っても、その文脈に入れないようにする（Backend の issue #4）。デプロイして、通しの確認（smoke）を通す。

**Architecture:** 既存の作り（API Gateway＋Lambda・1つの DynamoDB テーブル・`lib/` に検証と記録、`handlers/` に受け口）を伸ばす。走行の入力の検証は `lib/rides.py`、記録は `lib/store.py` に足し、受け口は新しい Lambda `lambda-trv2-dev-rides`（`handlers/rides.py`）が2つの経路を受け持つ。走行のメタ情報は、`updatedAt`（UTC にそろえた文字列）が保存済みのものより新しいときだけ、条件付きの書き込みで上書きする。Agent のセッションの識別子は、ユーザー名と会話の識別子から作る SHA-256 の16進にする。

**Tech Stack:** Python 3.13（Lambda）・SAM・boto3・pytest・moto・openapi-spec-validator（どれも既存。足すものは無い）。

**Spec:** [docs/specs/2026-10-17-slice2-design.md](../specs/2026-10-17-slice2-design.md)（§4.6・§5.2・§5.3・§6・§9・§10）。

**範囲に入れた issue:** Backend の #4（会話の ID がユーザーと結び付いていない）。ほかの Backend の issue（#2・#3・#5〜#8）は走行の受け口と関わらないので入れない。

**計画を書くときに利用者と決めたこと:**
- #4 を入れる。直し方は、Agent のセッションの識別子をユーザー名と会話の識別子から作る値にすること。デプロイした時点で続いている会話は1回区切られる（再デプロイと同じ扱い。adr/0003 が許容している）。

**計画を書くときに決めたこと（spec からの具体化）:**
- 時刻は、ほかの API と同じくタイムゾーン付きの ISO 8601 で受け、UTC・ミリ秒の文字列にそろえて保存する（文字列のまま新旧を比べられるように）。ルートの点の時刻 `t` も同じ。
- `PUT /rides/{rideId}` の応答は `200 {"rideId", "applied"}`。古い（または同じ）`updatedAt` のときは何もせず `applied: false`（spec §6.2「古ければ何もせず 200」）。
- 走行の検証: 名前は前後の空白を落として1〜40字（SC-17）。状態は `recording`・`paused`・`ended`。区間は1〜1000個。記録中の走行だけ最後の区間が開いている（`endedAt` が null）。区間は重ならず、終わりが始まりより前にならない。`autoEnded` は終了した走行だけ true にできる。
- ルートの検証: 1かたまり1〜300点（301点以上は 400）。`seq` は0〜99999で、ソートキーは5桁にそろえる（`RIDE#<rideId>#ROUTE#00003`）。点は `t`・`lat`・`lon`・`accuracy`（0以上か null）・`segment`（0以上）。走行のメタ情報より先にかたまりが届いてもよい。
- 走行の Lambda には `dynamodb:PutItem` だけを許す（読み出しはスライス3）。
- ログには点の数・状態だけを出し、位置・名前は出さない（既存の決まり。`handlers/common.py` の `log`）。
- 不正な `rideId`（パスの値）は 400（`GET /asks` の不正な `askId` は 404 だが、書き込みでは送り手の誤りとして返す）。

この計画のコードは、使い捨てのフォルダで pytest 158件（今の134件から24件増える）と `sam validate --lint` が通ることを確かめてから書いた。デプロイと smoke は、実行のときに利用者の確認を取ってから行う。

## Global Constraints

- 作業するリポジトリは `Backend/`（`TouringProjectV2_Backend`）と親。どちらも `main` から作業ブランチ `slice2-plan2` を切る。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- **デプロイは、利用者が明示したときだけ行う。** Task 6 の最初で確認を取る。AWS は `AWS_PROFILE=touring`（使えないときは利用者に聞く）。リージョンは `ap-northeast-1`。名前には `trv2` を付ける。
- ユーザー名は英小文字と数字の3〜20文字（`x-user-name`）。他人の記録は無いものとして扱う。既存の接続キーの検査を通す（`/health` 以外）。
- 不正な入力は `400 {"error": "bad_request", "message": <理由>}`（07 UC-4）。
- LLM の入力のトークンを増やさない（この plan はプロンプトに触れない）。
- 接続キー・API の URL・アカウント ID を、コードや文書に書かない。smoke の出力に接続キーを出さない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`BE=$ROOT/Backend`。テストは `cd $BE && env/bin/pytest`（絞るときは `env/bin/pytest -q tests/test_xxx.py`）。

## Review Focus

- 同じ走行を、同じ `updatedAt` のまま送り直す（端末が送れたか分からずにもう一度送る）→ 記録は1つのまま、`applied: false` の 200。Task 3 の `test_sending_the_same_ride_again_leaves_one_record`。
- `updatedAt` のタイムゾーンが送るたびに違う（`+09:00` と `Z`）→ UTC にそろえて比べるので、文字列の並びに引きずられない。Task 3 の `test_times_with_another_zone_are_compared_in_utc`。
- ルートのかたまりが、走行のメタ情報より先に届く（電波の戻り方による）→ どちらも受け付け、あとで揃う。Task 3 の `test_a_chunk_may_arrive_before_its_ride`。
- 進行方位がちょうど真北（0度）→ null にならず 0 を返す。Task 1 の `test_due_north_is_a_heading_not_null`。
- 本文が JSON でない（壊れた送信）→ 走行の2つの受け口とも 400 で、何も書かない。Task 3 の `test_a_body_that_is_not_json_is_400`。

---

## ファイル構成（`Backend/` から）

| パス | 役割 | Task |
|---|---|---|
| `src/lib/request.py` | `POST /asks` の `rideId` の検証。本文を読む関数を `body_json` として公開する（Task 3 が使う） | 1 |
| `src/handlers/ask.py`・`src/handlers/result.py` | 質問の記録に `rideId` を残す。結果に `askedAt`・`address`・`headingDegrees` を足す | 1 |
| `src/lib/agent.py`・`src/handlers/worker.py` | セッションの識別子をユーザー名と会話の識別子から作る | 2 |
| `src/lib/rides.py`（新規） | 走行とルートのかたまりの検証 | 3 |
| `src/lib/store.py` | 走行の記録（条件付きの書き込み）とルートのかたまり | 3 |
| `src/handlers/rides.py`（新規） | `PUT /rides/{rideId}`・`PUT /rides/{rideId}/route/{seq}` | 3 |
| `template.yaml`・`openapi.yaml` | 走行の Lambda と経路・API の正本 | 4 |
| 親の `docs/07_units_contracts.md`・`adr/0003-conversation-context.md`・`Backend/README.md`・`Backend/docs-parent/` | 文書 | 5 |
| `scripts/smoke.py` | デプロイ後の通しの確認に、走行と質問の追加項目を足す | 6 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: 両方のリポジトリでブランチを切り、今のテストを回す**

```bash
cd $ROOT && git switch main && git switch -c slice2-plan2
cd $BE && git switch main && git pull --ff-only && git switch -c slice2-plan2
cd $BE && env/bin/pytest -q 2>&1 | tail -1
```

Expected: `134 passed`

---

### Task 1: 質問の API の追加（`rideId`・受け付けた日時・住所・方位）

**Files:**
- Modify: `src/lib/request.py`・`src/handlers/ask.py`・`src/handlers/result.py`
- Test: `tests/test_ask.py`・`tests/test_result.py`

**Interfaces:**
- Consumes: 既存の `lib.request.UUID_RE`・`BadRequest`・`AskInput`・`lib.store.get_ask`
- Produces: `AskInput.ride_id: Optional[str]`（既定 None。最後の項目）・`lib.request.body_json(event) -> dict`（今の `_body` の名前を変えたもの。Task 3 が使う）・質問の記録の項目 `rideId`（無ければ項目ごと無い）・`GET /asks/{askId}` の応答の `askedAt`・`address`・`headingDegrees`

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_ask.py b/tests/test_ask.py
index 6af81d5..3590276 100644
--- a/tests/test_ask.py
+++ b/tests/test_ask.py
@@ -7,6 +7,7 @@ from lib import store
 from lib.request import MIN_AUDIO_BYTES
 
 CID = "0b8e7c1e-3f1a-4f5e-9a51-2a0b2c6f7d10"
+RID = "5c9a1f0e-2b3d-4e5f-8a6b-7c8d9e0f1a2b"
 
 
 def call(body, user="rider01"):
@@ -79,3 +80,19 @@ def test_bad_volume_is_rejected(aws):
     result = call({"text": "Q", "volumeDb": 12})
     assert result["statusCode"] == 400
     assert aws.table.scan()["Items"] == []
+
+
+def test_the_ride_id_is_kept_with_the_ask(aws):
+    body = json.loads(call({"text": "Q", "rideId": RID})["body"])
+    assert store.get_ask("rider01", body["askId"])["rideId"] == RID
+
+
+def test_an_ask_outside_a_ride_has_no_ride_id(aws):
+    body = json.loads(call({"text": "Q"})["body"])
+    assert "rideId" not in store.get_ask("rider01", body["askId"])
+
+
+def test_a_malformed_ride_id_is_400(aws):
+    for bad in ("ride-1", RID.upper(), 12):
+        result = call({"text": "Q", "rideId": bad})
+        assert result["statusCode"] == 400 and "rideId" in json.loads(result["body"])["message"]
EOF
git apply <<'EOF'
diff --git a/tests/test_result.py b/tests/test_result.py
index 5d2d869..33845c9 100644
--- a/tests/test_result.py
+++ b/tests/test_result.py
@@ -19,7 +19,7 @@ def test_pending_is_reported_as_processing(aws):
     put(status="pending")
     body = json.loads(call()["body"])
     assert body == {"askId": ASK, "status": "processing", "transcript": None, "answer": None, "audio": [], "error": None,
-                    "timings": {"receivedAt": "2026-10-16T03:00:00.000Z"}}
+                    "timings": {"receivedAt": "2026-10-16T03:00:00.000Z"}, "askedAt": None, "address": None, "headingDegrees": None}
 
 
 def test_completed_has_presigned_audio(aws):
@@ -52,3 +52,20 @@ def test_other_user_gets_404(aws):
 def test_malformed_id_is_404_and_bad_user_is_400(aws):
     assert call(ask_id="../etc")["statusCode"] == 404
     assert call(user="X")["statusCode"] == 400
+
+
+def test_the_result_says_when_where_and_which_way(aws):
+    put(status="completed", answer="A", receivedAt="2026-10-16T03:00:00.000Z", address="静岡県御殿場市", headingDegrees=92.5)
+    body = json.loads(call()["body"])
+    assert (body["askedAt"], body["address"], body["headingDegrees"]) == ("2026-10-16T03:00:00.000Z", "静岡県御殿場市", 92.5)
+
+
+def test_a_failed_ask_without_an_address_or_heading_says_null(aws):
+    put(status="failed", error="agent_failed", receivedAt="2026-10-16T03:00:00.000Z")
+    body = json.loads(call()["body"])
+    assert body["askedAt"] == "2026-10-16T03:00:00.000Z" and body["address"] is None and body["headingDegrees"] is None
+
+
+def test_due_north_is_a_heading_not_null(aws):
+    put(status="completed", answer="A", receivedAt="2026-10-16T03:00:00.000Z", headingDegrees=0.0)
+    assert json.loads(call()["body"])["headingDegrees"] == 0
EOF
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_ask.py tests/test_result.py 2>&1 | tail -3`
Expected: 失敗が6件（`rideId` が残らない・400 にならない・結果に `askedAt` などが無い）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/lib/request.py b/src/lib/request.py
index c26b186..0a2843b 100644
--- a/src/lib/request.py
+++ b/src/lib/request.py
@@ -33,6 +33,7 @@ class AskInput:
     heading_sample: Optional[dict]
     conversation_id: Optional[str]
     volume_db: int = DEFAULT_VOLUME_DB
+    ride_id: Optional[str] = None
 
 
 def _header(event: dict, name: str) -> Optional[str]:
@@ -80,7 +81,7 @@ def _sample(value: Any) -> Optional[dict]:
     return {**point, "at": utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"}
 
 
-def _body(event: dict) -> dict:
+def body_json(event: dict) -> dict:
     raw = event.get("body") or ""
     try:
         if event.get("isBase64Encoded"):
@@ -94,7 +95,7 @@ def _body(event: dict) -> dict:
 
 
 def parse_ask(event: dict) -> AskInput:
-    data = _body(event)
+    data = body_json(event)
     audio_b64, text = data.get("audio"), data.get("text")
     if (audio_b64 is None) == (text is None):
         raise BadRequest("exactly one of audio and text is required")
@@ -123,4 +124,11 @@ def parse_ask(event: dict) -> AskInput:
     if isinstance(volume_db, bool) or volume_db not in VOLUME_DB_CHOICES:
         raise BadRequest("volumeDb must be one of 0, 3, 6")
 
-    return AskInput(audio, text, _point(data.get("location")), _sample(data.get("headingSample")), conversation_id, int(volume_db))
+    # Sent only while a ride is recording (slice 2 spec §4.6).
+    ride_id = data.get("rideId")
+    if ride_id is not None and (not isinstance(ride_id, str) or not UUID_RE.match(ride_id)):
+        raise BadRequest("rideId must be a lowercase UUID")
+
+    return AskInput(
+        audio, text, _point(data.get("location")), _sample(data.get("headingSample")), conversation_id, int(volume_db), ride_id
+    )
EOF
git apply <<'EOF'
diff --git a/src/handlers/ask.py b/src/handlers/ask.py
index a1c049c..03a30df 100644
--- a/src/handlers/ask.py
+++ b/src/handlers/ask.py
@@ -37,6 +37,7 @@ def handler(event, context):
         "location": ask.location,
         "headingSample": ask.heading_sample,
         "volumeDb": ask.volume_db,
+        "rideId": ask.ride_id,
         "timings": {"receivedAt": iso(now)},
     }
     if ask.audio is not None:
EOF
git apply <<'EOF'
diff --git a/src/handlers/result.py b/src/handlers/result.py
index 1176684..ddff9f9 100644
--- a/src/handlers/result.py
+++ b/src/handlers/result.py
@@ -37,4 +37,8 @@ def handler(event, context):
         "audio": audio,
         "error": item.get("error"),
         "timings": item.get("timings", {}),
+        # What the device keeps with the ask (slice 2 spec §5.2, §6.1).
+        "askedAt": item.get("receivedAt"),
+        "address": item.get("address"),
+        "headingDegrees": item.get("headingDegrees"),
     })
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `140 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/request.py src/handlers/ask.py src/handlers/result.py tests/test_ask.py tests/test_result.py
git commit -m "feat: tie asks to a ride and return when, where and which way they were asked"
```

---

### Task 2: Agent のセッションをユーザーごとに分ける（issue #4）

**Files:**
- Modify: `src/lib/agent.py`・`src/handlers/worker.py`
- Test: `tests/test_agent.py`・`tests/test_worker.py`

**Interfaces:**
- Consumes: 既存の `worker.process(user, ask_id, steps)`・`Steps.invoke_agent(prompt, location, session_id)`
- Produces: `lib.agent.session_id(user: str, conversation_id: str) -> str`（`sha256(f"{user}:{conversation_id}")` の16進64文字）。worker はこれを `invoke_agent` の3つ目の引数に渡す

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_agent.py b/tests/test_agent.py
index 87f829a..dbcd654 100644
--- a/tests/test_agent.py
+++ b/tests/test_agent.py
@@ -4,7 +4,7 @@ import json
 import pytest
 from botocore.exceptions import ClientError
 
-from lib.agent import AgentError, invoke, parse_events
+from lib.agent import AgentError, invoke, parse_events, session_id
 
 
 def sse(*events):
@@ -111,3 +111,15 @@ def test_agentcore_client_never_retries_on_its_own(monkeypatch):
     assert config.retries["total_max_attempts"] == 1
     assert config.read_timeout <= 90
     clients.reset()
+
+
+CONVERSATION = "0b8e7c1e-3f1a-4f5e-9a51-2a0b2c6f7d10"
+
+
+def test_the_session_belongs_to_the_user_and_the_conversation():
+    mine = session_id("rider01", CONVERSATION)
+    assert mine == session_id("rider01", CONVERSATION)
+    # Knowing someone else's conversationId does not lead into their session.
+    assert mine != session_id("rider02", CONVERSATION)
+    assert mine != CONVERSATION
+    assert 33 <= len(mine) <= 100
EOF
git apply <<'EOF'
diff --git a/tests/test_worker.py b/tests/test_worker.py
index 8e9be7e..a4877ae 100644
--- a/tests/test_worker.py
+++ b/tests/test_worker.py
@@ -4,7 +4,7 @@ from datetime import datetime, timedelta, timezone
 from handlers import worker
 from handlers.common import iso
 from lib import store
-from lib.agent import AgentError, AgentReply
+from lib.agent import AgentError, AgentReply, session_id
 
 USER, ASK, CID = "rider01", "11111111-1111-4111-8111-111111111111", "33333333-3333-4333-8333-333333333333"
 T0 = datetime(2026, 10, 16, 3, 0, tzinfo=timezone.utc)
@@ -90,7 +90,7 @@ def test_agent_gets_facts_location_and_session(aws):
     assert "現在地の住所: 東京都千代田区丸の内" in prompt
     assert "会話の最初の質問から約10分後" in prompt
     assert prompt.endswith("質問: 右手の山は？")
-    assert location["headingDegrees"] == 0.0 and session == CID
+    assert location["headingDegrees"] == 0.0 and session == session_id(USER, CID)
 
 
 def test_text_question_skips_transcription(aws):
EOF
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_agent.py tests/test_worker.py 2>&1 | tail -3`
Expected: 集める段階の失敗（`ImportError: cannot import name 'session_id'`）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/lib/agent.py b/src/lib/agent.py
index 9773568..f7d45e5 100644
--- a/src/lib/agent.py
+++ b/src/lib/agent.py
@@ -1,6 +1,7 @@
 """Invoke the agent runtime (us-east-1) and read its SSE events (07 UC-8)."""
 from __future__ import annotations
 
+import hashlib
 import json
 import os
 import time
@@ -15,6 +16,13 @@ from lib import clients
 _RETRYABLE = "RetryableConflictException"
 
 
+def session_id(user: str, conversation_id: str) -> str:
+    """The runtime session of one user's conversation. Another user sending the same conversationId gets a session
+    of their own, so nobody reaches someone else's context by knowing the ID (Backend issue #4). 64 hex characters,
+    inside the runtime's 33-100."""
+    return hashlib.sha256(f"{user}:{conversation_id}".encode("utf-8")).hexdigest()
+
+
 class AgentError(RuntimeError):
     """The agent did not produce an answer; reported as agent_failed."""
 
EOF
git apply <<'EOF'
diff --git a/src/handlers/worker.py b/src/handlers/worker.py
index c60ab16..d01b195 100644
--- a/src/handlers/worker.py
+++ b/src/handlers/worker.py
@@ -10,7 +10,7 @@ from typing import Optional
 
 from handlers.common import iso, log, parse_iso, utc_now
 from lib import address, agent, clients, speech, store, transcribe
-from lib.agent import AgentError, AgentReply
+from lib.agent import AgentError, AgentReply, session_id
 from lib.geo import heading_degrees
 from lib.prompt import agent_location, build_prompt
 from lib.request import DEFAULT_VOLUME_DB
@@ -101,7 +101,7 @@ def _run(user: str, ask_id: str, item: dict, steps: Steps) -> None:
     facts = {"transcript": transcript, "address": place, "headingDegrees": round(heading, 1) if heading is not None else None}
 
     try:
-        reply = steps.invoke_agent(prompt, agent_location(location, heading), item["conversationId"])
+        reply = steps.invoke_agent(prompt, agent_location(location, heading), session_id(user, item["conversationId"]))
     except Exception as error:  # noqa: BLE001 - AgentError or anything unexpected from the call
         mark("agentDoneAt")
         reason = str(error) if isinstance(error, AgentError) else type(error).__name__
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `141 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/agent.py src/handlers/worker.py tests/test_agent.py tests/test_worker.py
git commit -m "fix: give each user's conversation its own agent session" -m "The worker passed the conversationId straight to the agent runtime, so anyone
holding the shared key and someone else's conversationId could ask inside
that conversation's context. The session ID is now a SHA-256 of the user name
and the conversationId. Conversations under way at deploy time start afresh." -m "Fixes #4"
```

---

### Task 3: 走行の受け口

**Files:**
- Create: `src/lib/rides.py`・`src/handlers/rides.py`
- Modify: `src/lib/store.py`
- Test: `tests/test_rides.py`

**Interfaces:**
- Consumes: Task 1 の `lib.request.body_json(event)`・既存の `lib.request.BadRequest`・`UUID_RE`・`user_name(event)`・`handlers.common.iso`・`log`・`response`・`utc_now`・`lib.store._to_item`・`_from_item`・`_CONDITION_FAILED`
- Produces: `lib.rides.RIDE_NAME_MAX = 40`・`STATUSES = ("recording", "paused", "ended")`・`MAX_POINTS = 300`・`ride_id(event) -> str`・`chunk_seq(event) -> int`・`parse_ride(event) -> RideInput(name, status, segments, auto_ended, updated_at)`・`parse_route(event) -> list[dict]`・`lib.store.ride_key(user, ride_id)`・`route_key(user, ride_id, seq)`・`put_ride(user, ride_id, fields) -> bool`・`put_route_chunk(user, ride_id, seq, points, saved_at)`・`handlers.rides.handler(event, context)`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_rides.py`:

```python
"""Tests for PUT /rides/{rideId} and PUT /rides/{rideId}/route/{seq} (moto)."""
import json

from handlers import rides
from lib import store
from lib.store import _from_item

USER = "rider01"
RIDE = "5c9a1f0e-2b3d-4e5f-8a6b-7c8d9e0f1a2b"
T0 = "2026-10-18T09:00:00.000Z"


def ride_body(**changes):
    body = {
        "name": "箱根",
        "status": "paused",
        "segments": [{"startedAt": T0, "endedAt": "2026-10-18T10:00:00.000Z"}],
        "autoEnded": False,
        "updatedAt": "2026-10-18T10:00:00.000Z",
    }
    return {**body, **changes}


def put_ride(body, ride_id=RIDE, user=USER):
    return rides.handler({"headers": {"x-user-name": user}, "pathParameters": {"rideId": ride_id}, "body": json.dumps(body)}, None)


def put_route(points, seq="0", ride_id=RIDE, user=USER):
    event = {"headers": {"x-user-name": user}, "pathParameters": {"rideId": ride_id, "seq": seq}, "body": json.dumps({"points": points})}
    return rides.handler(event, None)


def stored(aws, key):
    item = aws.table.get_item(Key=key).get("Item")
    return _from_item(item) if item else None


def point(i, segment=0):
    return {"t": f"2026-10-18T09:00:{i:02d}.000Z", "lat": 35.0 + i * 0.001, "lon": 139.0, "accuracy": 5.0, "segment": segment}


def message(result):
    return json.loads(result["body"])["message"]


def test_a_ride_is_saved_under_its_user(aws):
    result = put_ride(ride_body())
    assert result["statusCode"] == 200
    assert json.loads(result["body"]) == {"rideId": RIDE, "applied": True}
    item = stored(aws, store.ride_key(USER, RIDE))
    assert item["name"] == "箱根" and item["status"] == "paused" and item["autoEnded"] is False
    assert item["segments"] == [{"startedAt": T0, "endedAt": "2026-10-18T10:00:00.000Z"}]
    assert item["updatedAt"] == "2026-10-18T10:00:00.000Z" and "savedAt" in item


def test_sending_the_same_ride_again_leaves_one_record(aws):
    put_ride(ride_body())
    # The same updatedAt is not newer: nothing changes, and the app treats it as sent.
    again = put_ride(ride_body())
    assert again["statusCode"] == 200 and json.loads(again["body"])["applied"] is False
    items = aws.table.scan()["Items"]
    assert [i["sk"] for i in items] == [f"RIDE#{RIDE}"]


def test_a_newer_ride_replaces_the_stored_one(aws):
    put_ride(ride_body())
    ended = ride_body(status="ended", name="箱根から御殿場へ", updatedAt="2026-10-18T11:00:00.000Z",
                      segments=[{"startedAt": T0, "endedAt": "2026-10-18T10:00:00.000Z"},
                                {"startedAt": "2026-10-18T10:30:00.000Z", "endedAt": "2026-10-18T11:00:00.000Z"}])
    assert json.loads(put_ride(ended)["body"])["applied"] is True
    item = stored(aws, store.ride_key(USER, RIDE))
    assert item["status"] == "ended" and item["name"] == "箱根から御殿場へ" and len(item["segments"]) == 2


def test_an_older_ride_is_ignored_with_200(aws):
    put_ride(ride_body(status="ended", updatedAt="2026-10-18T11:00:00.000Z"))
    result = put_ride(ride_body(name="古い名前", updatedAt="2026-10-18T10:00:00.000Z"))
    assert result["statusCode"] == 200 and json.loads(result["body"])["applied"] is False
    item = stored(aws, store.ride_key(USER, RIDE))
    assert item["status"] == "ended" and item["name"] == "箱根"


def test_times_with_another_zone_are_compared_in_utc(aws):
    put_ride(ride_body(updatedAt="2026-10-18T19:00:00.000+09:00"))
    # 10:30Z is later than 19:00+09:00 (10:00Z), though it sorts earlier as text.
    assert json.loads(put_ride(ride_body(name="新しい", updatedAt="2026-10-18T10:30:00Z"))["body"])["applied"] is True
    assert stored(aws, store.ride_key(USER, RIDE))["updatedAt"] == "2026-10-18T10:30:00.000Z"


def test_rides_are_kept_apart_by_user(aws):
    put_ride(ride_body())
    put_ride(ride_body(name="別の人"), user="rider02")
    assert stored(aws, store.ride_key(USER, RIDE))["name"] == "箱根"
    assert stored(aws, store.ride_key("rider02", RIDE))["name"] == "別の人"


def test_a_recording_ride_has_its_last_segment_open(aws):
    body = ride_body(status="recording", segments=[{"startedAt": T0, "endedAt": None}])
    assert put_ride(body)["statusCode"] == 200
    assert stored(aws, store.ride_key(USER, RIDE))["segments"] == [{"startedAt": T0}]


def test_a_bad_ride_is_400(aws):
    cases = [
        ("name must be", ride_body(name="  ")),
        ("name must be", ride_body(name="あ" * 41)),
        ("status must be", ride_body(status="stopped")),
        ("autoEnded must be", ride_body(autoEnded="no")),
        ("only an ended ride", ride_body(autoEnded=True)),
        ("updatedAt must be", ride_body(updatedAt="2026-10-18T10:00:00")),
        ("segments must be", ride_body(segments=[])),
        ("only the last segment", ride_body(segments=[{"startedAt": T0, "endedAt": None}])),
        ("must be open", ride_body(status="recording")),
        ("cannot end before", ride_body(segments=[{"startedAt": T0, "endedAt": "2026-10-18T08:00:00.000Z"}])),
        ("must not overlap", ride_body(segments=[{"startedAt": T0, "endedAt": "2026-10-18T10:00:00.000Z"},
                                                 {"startedAt": "2026-10-18T09:30:00.000Z", "endedAt": "2026-10-18T10:30:00.000Z"}])),
    ]
    for expected, body in cases:
        result = put_ride(body)
        assert result["statusCode"] == 400 and expected in message(result), (expected, message(result))
    assert aws.table.scan()["Items"] == []


def test_a_body_that_is_not_json_is_400(aws):
    event = {"headers": {"x-user-name": USER}, "pathParameters": {"rideId": RIDE}, "body": "not json"}
    assert rides.handler(event, None)["statusCode"] == 400
    event["pathParameters"]["seq"] = "0"
    assert rides.handler(event, None)["statusCode"] == 400


def test_a_bad_ride_id_or_user_is_400(aws):
    assert put_ride(ride_body(), ride_id="ride-1")["statusCode"] == 400
    assert put_ride(ride_body(), ride_id=RIDE.upper())["statusCode"] == 400
    assert put_ride(ride_body(), user="X")["statusCode"] == 400


def test_a_route_chunk_is_saved_with_its_points(aws):
    result = put_route([point(0), point(5)], seq="3")
    assert result["statusCode"] == 200 and json.loads(result["body"]) == {"rideId": RIDE, "seq": 3}
    item = stored(aws, store.route_key(USER, RIDE, 3))
    assert item["sk"] == f"RIDE#{RIDE}#ROUTE#00003"
    assert item["points"] == [point(0), point(5)]


def test_a_chunk_may_arrive_before_its_ride(aws):
    assert put_route([point(0)], seq="0")["statusCode"] == 200
    assert put_ride(ride_body())["statusCode"] == 200
    assert {i["sk"] for i in aws.table.scan()["Items"]} == {f"RIDE#{RIDE}", f"RIDE#{RIDE}#ROUTE#00000"}


def test_sending_a_chunk_again_replaces_it(aws):
    put_route([point(0)], seq="0")
    put_route([point(0), point(1)], seq="0")
    items = aws.table.scan()["Items"]
    assert len(items) == 1 and len(items[0]["points"]) == 2


def test_a_point_without_accuracy_is_kept(aws):
    put_route([{**point(0), "accuracy": None}])
    assert stored(aws, store.route_key(USER, RIDE, 0))["points"] == [{k: v for k, v in point(0).items() if k != "accuracy"}]


def test_a_chunk_of_300_points_is_accepted_and_301_is_400(aws):
    assert put_route([point(i % 60) for i in range(300)])["statusCode"] == 200
    result = put_route([point(i % 60) for i in range(301)], seq="1")
    assert result["statusCode"] == 400 and "1-300" in message(result)


def test_a_bad_chunk_is_400(aws):
    cases = {
        "points": [],
        "lat and lon": [{**point(0), "lat": 91}],
        "accuracy": [{**point(0), "accuracy": -1}],
        "segment": [{**point(0), "segment": -1}],
        "t must": [{**point(0), "t": "yesterday"}],
    }
    for expected, points in cases.items():
        result = put_route(points)
        assert result["statusCode"] == 400 and expected in message(result), (expected, message(result))
    for seq in ("-1", "abc", "100000"):
        assert put_route([point(0)], seq=seq)["statusCode"] == 400
    assert aws.table.scan()["Items"] == []
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_rides.py 2>&1 | tail -3`
Expected: 集める段階の失敗（`ImportError: cannot import name 'rides' from 'handlers'`）

- [ ] **Step 3: 検証を書く**

`src/lib/rides.py`:

```python
"""Validation of a ride and its route chunks sent by the Android app (slice 2 spec §6.2)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from lib.request import BadRequest, UUID_RE, body_json

RIDE_NAME_MAX = 40
STATUSES = ("recording", "paused", "ended")
MAX_SEGMENTS = 1000
MAX_POINTS = 300
MAX_SEQ = 99999
SEQ_RE = re.compile(r"^[0-9]{1,5}$")


@dataclass(frozen=True)
class RideInput:
    name: str
    status: str
    segments: list
    auto_ended: bool
    updated_at: str


def _iso(value: Any, field: str) -> str:
    """A time with its time zone, normalised to UTC with milliseconds so that stored values compare as text."""
    if not isinstance(value, str):
        raise BadRequest(f"{field} must be a date-time with a time zone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BadRequest(f"{field} must be a date-time with a time zone") from None
    if parsed.tzinfo is None:
        raise BadRequest(f"{field} must be a date-time with a time zone")
    utc = parsed.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def ride_id(event: dict) -> str:
    value = (event.get("pathParameters") or {}).get("rideId") or ""
    if not UUID_RE.match(value):
        raise BadRequest("rideId must be a lowercase UUID")
    return value


def chunk_seq(event: dict) -> int:
    value = (event.get("pathParameters") or {}).get("seq") or ""
    if not SEQ_RE.match(value):
        raise BadRequest(f"seq must be 0-{MAX_SEQ}")
    return int(value)


def _segments(value: Any, status: str) -> list:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_SEGMENTS:
        raise BadRequest(f"segments must be a list of 1-{MAX_SEGMENTS}")
    segments = []
    for i, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise BadRequest("each segment must be an object")
        started = _iso(raw.get("startedAt"), "startedAt")
        ended = None if raw.get("endedAt") is None else _iso(raw.get("endedAt"), "endedAt")
        last = i == len(value) - 1
        # Only a recording ride has an open segment, and only its last one.
        if ended is None and not (last and status == "recording"):
            raise BadRequest("only the last segment of a recording ride may be open")
        if ended is not None and last and status == "recording":
            raise BadRequest("a recording ride's last segment must be open")
        if ended is not None and ended < started:
            raise BadRequest("a segment cannot end before it starts")
        if segments and started < (segments[-1]["endedAt"] or ""):
            raise BadRequest("segments must not overlap")
        segments.append({"startedAt": started, "endedAt": ended})
    return segments


def parse_ride(event: dict) -> RideInput:
    data = body_json(event)
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > RIDE_NAME_MAX:
        raise BadRequest(f"name must be 1-{RIDE_NAME_MAX} characters")
    status = data.get("status")
    if status not in STATUSES:
        raise BadRequest("status must be one of recording, paused, ended")
    auto_ended = data.get("autoEnded")
    if not isinstance(auto_ended, bool):
        raise BadRequest("autoEnded must be true or false")
    if auto_ended and status != "ended":
        raise BadRequest("only an ended ride can have ended automatically")
    return RideInput(name.strip(), status, _segments(data.get("segments"), status), auto_ended, _iso(data.get("updatedAt"), "updatedAt"))


def _point(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise BadRequest("each point must be an object")
    lat, lon = _number(raw.get("lat")), _number(raw.get("lon"))
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise BadRequest("lat and lon must be a position")
    accuracy = raw.get("accuracy")
    if accuracy is not None and (_number(accuracy) is None or accuracy < 0):
        raise BadRequest("accuracy must be a non-negative number or null")
    segment = raw.get("segment")
    if isinstance(segment, bool) or not isinstance(segment, int) or not 0 <= segment < MAX_SEGMENTS:
        raise BadRequest(f"segment must be 0-{MAX_SEGMENTS - 1}")
    return {"t": _iso(raw.get("t"), "t"), "lat": lat, "lon": lon, "accuracy": _number(accuracy), "segment": segment}


def parse_route(event: dict) -> list:
    points = body_json(event).get("points")
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
        raise BadRequest(f"points must be a list of 1-{MAX_POINTS}")
    return [_point(p) for p in points]
```

- [ ] **Step 4: 記録を足す**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/lib/store.py b/src/lib/store.py
index 2de1a87..f97db28 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -1,4 +1,4 @@
-"""Records in one DynamoDB table: pk USER#<name>, sk ASK#<id> or CONV#<id>."""
+"""Records in one DynamoDB table: pk USER#<name>, sk ASK#<id>, CONV#<id>, RIDE#<id> or RIDE#<id>#ROUTE#<seq>."""
 from __future__ import annotations
 
 import json
@@ -94,3 +94,33 @@ def update_ask(user: str, ask_id: str, fields: dict) -> None:
 def get_ask(user: str, ask_id: str) -> Optional[dict]:
     item = clients.table().get_item(Key=ask_key(user, ask_id)).get("Item")
     return _from_item(item) if item else None
+
+
+def ride_key(user: str, ride_id: str) -> dict:
+    return {"pk": f"USER#{user}", "sk": f"RIDE#{ride_id}"}
+
+
+def route_key(user: str, ride_id: str, seq: int) -> dict:
+    # Zero-padded so that the chunks of a ride sort in order.
+    return {"pk": f"USER#{user}", "sk": f"RIDE#{ride_id}#ROUTE#{seq:05d}"}
+
+
+def put_ride(user: str, ride_id: str, fields: dict) -> bool:
+    """Writes the ride unless a newer one is stored (updatedAt, normalised UTC text). False when it was older."""
+    item = {**ride_key(user, ride_id), "rideId": ride_id, **fields}
+    try:
+        clients.table().put_item(
+            Item=_to_item(item),
+            ConditionExpression="attribute_not_exists(pk) OR updatedAt < :u",
+            ExpressionAttributeValues={":u": fields["updatedAt"]},
+        )
+    except ClientError as error:
+        if error.response["Error"]["Code"] == _CONDITION_FAILED:
+            return False
+        raise
+    return True
+
+
+def put_route_chunk(user: str, ride_id: str, seq: int, points: list, saved_at: str) -> None:
+    """A chunk is replaced whole: sending it again leaves one copy."""
+    clients.table().put_item(Item=_to_item({**route_key(user, ride_id, seq), "rideId": ride_id, "seq": seq, "points": points, "savedAt": saved_at}))
EOF
```

- [ ] **Step 5: 受け口を書く**

`src/handlers/rides.py`:

```python
"""PUT /rides/{rideId} and PUT /rides/{rideId}/route/{seq}: the app sends its rides (07 UC-7, slice 2 spec §6.2).
Reading them back comes with slice 3."""
from __future__ import annotations

from handlers.common import iso, log, response, utc_now
from lib import rides, store
from lib.request import BadRequest, user_name


def handler(event, context):
    try:
        user = user_name(event)
        ride_id = rides.ride_id(event)
        if (event.get("pathParameters") or {}).get("seq") is not None:
            return _route(event, user, ride_id)
        return _ride(event, user, ride_id)
    except BadRequest as error:
        return response(400, {"error": "bad_request", "message": str(error)})


def _ride(event: dict, user: str, ride_id: str) -> dict:
    ride = rides.parse_ride(event)
    applied = store.put_ride(user, ride_id, {
        "name": ride.name,
        "status": ride.status,
        "segments": ride.segments,
        "autoEnded": ride.auto_ended,
        "updatedAt": ride.updated_at,
        "savedAt": iso(utc_now()),
    })
    log({"event": "ride_saved", "rideId": ride_id, "status": ride.status, "applied": applied})
    # An older copy is not an error: the app has nothing to resend (slice 2 spec §6.2).
    return response(200, {"rideId": ride_id, "applied": applied})


def _route(event: dict, user: str, ride_id: str) -> dict:
    seq = rides.chunk_seq(event)
    points = rides.parse_route(event)
    store.put_route_chunk(user, ride_id, seq, points, iso(utc_now()))
    log({"event": "route_saved", "rideId": ride_id, "seq": seq, "points": len(points)})
    return response(200, {"rideId": ride_id, "seq": seq})
```

- [ ] **Step 6: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `157 passed`（`tests/test_rides.py` が16件）

- [ ] **Step 7: コミット**

```bash
cd $BE && git add src/lib/rides.py src/lib/store.py src/handlers/rides.py tests/test_rides.py
git commit -m "feat: accept rides and their route chunks"
```

---

### Task 4: テンプレートと API の正本

**Files:**
- Modify: `template.yaml`・`openapi.yaml`
- Test: `tests/test_openapi.py`

**Interfaces:**
- Consumes: Task 3 の `handlers.rides.handler`・`lib.rides.RIDE_NAME_MAX`・`STATUSES`・`MAX_POINTS`
- Produces: Lambda `lambda-trv2-dev-rides` と経路 `PUT /rides/{rideId}`・`PUT /rides/{rideId}/route/{seq}`。`openapi.yaml` の `RideRequest`・`RouteChunk`・`AskRequest.rideId`・`AskResult.askedAt`・`address`・`headingDegrees`

- [ ] **Step 1: 失敗するテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_openapi.py b/tests/test_openapi.py
index 18e1a1a..82edacf 100644
--- a/tests/test_openapi.py
+++ b/tests/test_openapi.py
@@ -12,9 +12,19 @@ def test_is_valid_openapi():
 
 
 def test_routes():
-    assert set(SPEC["paths"]) == {"/health", "/asks", "/asks/{askId}"}
+    assert set(SPEC["paths"]) == {"/health", "/asks", "/asks/{askId}", "/rides/{rideId}", "/rides/{rideId}/route/{seq}"}
     assert set(SPEC["paths"]["/asks"]) == {"post"}
     assert set(SPEC["paths"]["/asks/{askId}"]) == {"get"}
+    assert set(SPEC["paths"]["/rides/{rideId}"]) == {"put"}
+    assert set(SPEC["paths"]["/rides/{rideId}/route/{seq}"]) == {"put"}
+
+
+def test_the_ride_limits_match_the_validation():
+    from lib import rides
+    schemas = SPEC["components"]["schemas"]
+    assert schemas["RideRequest"]["properties"]["name"]["maxLength"] == rides.RIDE_NAME_MAX
+    assert schemas["RideRequest"]["properties"]["status"]["enum"] == list(rides.STATUSES)
+    assert schemas["RouteChunk"]["properties"]["points"]["maxItems"] == rides.MAX_POINTS
 
 
 def test_error_reasons_match_contract():
EOF
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_openapi.py 2>&1 | tail -3`
Expected: 失敗が2件（経路の集合が違う・`RideRequest` が無い）

- [ ] **Step 3: テンプレートと API の正本を直す**

```bash
cd $BE && git apply <<'EOF'
diff --git a/template.yaml b/template.yaml
index b1a5e3a..09e8257 100644
--- a/template.yaml
+++ b/template.yaml
@@ -1,6 +1,6 @@
 AWSTemplateFormatVersion: "2010-09-09"
 Transform: AWS::Serverless-2016-10-31
-Description: TouringProjectV2 backend (slice 1) - accept asks, process them through the agent, return answers.
+Description: TouringProjectV2 backend - accept asks, process them through the agent, return answers, and keep rides.
 
 Parameters:
   Environment:
@@ -115,6 +115,30 @@ Resources:
             Path: /asks/{askId}
             Method: get
 
+  RidesFunction:
+    Type: AWS::Serverless::Function
+    Properties:
+      FunctionName: !Sub lambda-trv2-${Environment}-rides
+      Handler: handlers.rides.handler
+      Policies:
+        - Statement:
+            - Effect: Allow
+              Action: dynamodb:PutItem
+              Resource: !GetAtt RecordsTable.Arn
+      Events:
+        Ride:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /rides/{rideId}
+            Method: put
+        Route:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /rides/{rideId}/route/{seq}
+            Method: put
+
   WorkerFunction:
     Type: AWS::Serverless::Function
     Properties:
EOF
git apply <<'EOF'
diff --git a/openapi.yaml b/openapi.yaml
index 287c872..5a0fb2e 100644
--- a/openapi.yaml
+++ b/openapi.yaml
@@ -84,6 +84,76 @@ paths:
                   error:
                     type: string
                     enum: [not_found]
+  /rides/{rideId}:
+    put:
+      summary: 走行のメタ情報を置く（状態・名前・区間が変わるたびに、最新の全体を送る）
+      description: >
+        updatedAt が保存済みのものより新しいときだけ上書きする。古ければ何もせず 200（applied は false）。
+        読み出しはスライス3で足す。
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+        - $ref: "#/components/parameters/RideId"
+      requestBody:
+        required: true
+        content:
+          application/json:
+            schema:
+              $ref: "#/components/schemas/RideRequest"
+      responses:
+        "200":
+          description: 受け取った（保存したか、古いので何もしなかったか）
+          content:
+            application/json:
+              schema:
+                type: object
+                required: [rideId, applied]
+                properties:
+                  rideId:
+                    type: string
+                    format: uuid
+                  applied:
+                    type: boolean
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
+  /rides/{rideId}/route/{seq}:
+    put:
+      summary: ルートの点のかたまりを置く（同じ seq は丸ごと上書き）
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+        - $ref: "#/components/parameters/RideId"
+        - name: seq
+          in: path
+          required: true
+          schema:
+            type: integer
+            minimum: 0
+            maximum: 99999
+      requestBody:
+        required: true
+        content:
+          application/json:
+            schema:
+              $ref: "#/components/schemas/RouteChunk"
+      responses:
+        "200":
+          description: 保存した
+          content:
+            application/json:
+              schema:
+                type: object
+                required: [rideId, seq]
+                properties:
+                  rideId:
+                    type: string
+                    format: uuid
+                  seq:
+                    type: integer
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
 components:
   securitySchemes:
     ApiKey:
@@ -98,6 +168,14 @@ components:
       schema:
         type: string
         pattern: "^[a-z0-9]{3,20}$"
+    RideId:
+      name: rideId
+      in: path
+      required: true
+      description: Android が作る UUID（小文字）
+      schema:
+        type: string
+        format: uuid
   responses:
     BadRequest:
       description: 入力が不正
@@ -162,6 +240,11 @@ components:
           enum: [0, 3, 6]
           default: 6
           description: 回答の音声を上げる量（dB）。利用者が設定で選ぶ。Polly は +6dB で頭打ちになるので、6 が最大。
+        rideId:
+          type: string
+          format: uuid
+          nullable: true
+          description: 走行の記録中に始めた質問だけに付ける（小文字）。一時停止中・記録していないときは付けない。
     AskAccepted:
       type: object
       required: [askId, conversationId, conversationExpiresAt]
@@ -214,3 +297,81 @@ components:
           additionalProperties:
             type: string
             format: date-time
+        askedAt:
+          type: string
+          format: date-time
+          nullable: true
+          description: 受け付けた日時（UTC）
+        address:
+          type: string
+          nullable: true
+          description: 質問した地点の住所。確定できなかったら null
+        headingDegrees:
+          type: number
+          nullable: true
+          description: 進行方位（北を0とする度）。方位なしなら null
+    RideRequest:
+      type: object
+      required: [name, status, segments, autoEnded, updatedAt]
+      properties:
+        name:
+          type: string
+          minLength: 1
+          maxLength: 40
+        status:
+          type: string
+          enum: [recording, paused, ended]
+        segments:
+          type: array
+          minItems: 1
+          maxItems: 1000
+          description: 記録した区間の並び。記録中の走行だけ、最後の区間の endedAt が null。重なってはいけない。
+          items:
+            type: object
+            required: [startedAt, endedAt]
+            properties:
+              startedAt:
+                type: string
+                format: date-time
+              endedAt:
+                type: string
+                format: date-time
+                nullable: true
+        autoEnded:
+          type: boolean
+          description: 最長時間で自動で終了したか（終了した走行だけ true にできる）
+        updatedAt:
+          type: string
+          format: date-time
+          description: Android が変更した時刻（タイムゾーン付き）
+    RouteChunk:
+      type: object
+      required: [points]
+      properties:
+        points:
+          type: array
+          minItems: 1
+          maxItems: 300
+          items:
+            type: object
+            required: [t, lat, lon, accuracy, segment]
+            properties:
+              t:
+                type: string
+                format: date-time
+              lat:
+                type: number
+                minimum: -90
+                maximum: 90
+              lon:
+                type: number
+                minimum: -180
+                maximum: 180
+              accuracy:
+                type: number
+                minimum: 0
+                nullable: true
+              segment:
+                type: integer
+                minimum: 0
+                description: 点を記録した区間の番号（segments の何番目か。0から）
EOF
```

- [ ] **Step 4: 通ることと、テンプレートが正しいことを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1 && AWS_PROFILE=touring sam validate --lint --region ap-northeast-1 2>&1 | tail -1`
Expected: `158 passed` と `... is a valid SAM Template`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add template.yaml openapi.yaml tests/test_openapi.py
git commit -m "feat: route the ride endpoints and describe them in the API document"
```

---

### Task 5: 文書

**Files:**
- Modify: 親の `docs/07_units_contracts.md`・`adr/0003-conversation-context.md`・`Backend/README.md`・`Backend/docs-parent/`（写し）

- [ ] **Step 1: 07 UC-5 を直す**

`$ROOT/docs/07_units_contracts.md` の UC-5「受け付けと回答の受け取り」の箇条の最後（`- Android が背面にあるあいだも、…`の行）の下に足す:

```markdown
- 結果には、受け付けた日時（UTC）・質問した地点の住所（確定できなかったら無し）・進行方位（方位なしなら無し）も入る。Android はこれを端末の記録に残す（質問の記録は Backend が作るので、Android から送り返さない。UC-7）。
```

同じ UC-5「送るもの」の表の下の箇条 `- 走行の記録中かどうか・どの走行かは、質問の記録を走行に結びつけるために送る。` を、次に置き換える:

```markdown
- 走行の記録中に始めた質問には、その走行の識別子を添える。一時停止中・記録していないときは添えない。Backend は質問の記録に残す。
```

- [ ] **Step 2: 07 UC-7 と UC-8 を直す**

UC-7 の「約束」の箇条の最後（`- 音声は同期しない。`）の下に、節を足す:

```markdown

### 走行の送り方（スライス2の暫定）

- 走行のメタ情報（名前・状態・記録した区間・自動終了したか・Android が変更した時刻）は、変わるたびに最新の全体を置く。Backend は、Android が変更した時刻が保存済みのものより新しいときだけ上書きし、古ければ何もせずに受け取ったと返す。端末が1台だけのスライス2ではこれで足りる。端末をまたいだ突き合わせは [05_technical_policies.md](05_technical_policies.md) §9 で決める（スライス3）。
- ルートの点は、300点までのかたまりに番号を付けて置く。同じ番号は丸ごと上書きする。かたまりは走行のメタ情報より先に届いてもよい。
- 入力が不正（400）なものは送り直さない。
- 読み出しはスライス3で足す。
```

UC-8「呼び出し」の箇条 `- 会話の文脈の識別子を、AI の実行環境のセッションの識別子としてそのまま渡す。Agent は同じ識別子が来るあいだ文脈を続ける。区切るかどうかは Android が決める（UC-5）。` を、次に置き換える:

```markdown
- AI の実行環境のセッションの識別子には、ユーザー名と会話の文脈の識別子から作った値（SHA-256 の16進）を渡す。同じ会話の識別子を別のユーザー名で送っても、別のセッションになる。Agent は同じ識別子が来るあいだ文脈を続ける。区切るかどうかは Android が決める（UC-5）。
```

- [ ] **Step 3: adr/0003 に追記する**

`$ROOT/adr/0003-conversation-context.md` の「決定」の `- 会話の文脈の識別子を、実行環境のセッションの識別子として使う。` を、次に置き換える:

```markdown
- 会話の文脈の識別子を、実行環境のセッションの識別子として使う。（2026-10-18 追記: 他人の会話の識別子を知ればその文脈に入れたので、ユーザー名と会話の識別子から作った値に変えた。Backend の issue #4。いまの約束は [07](../docs/07_units_contracts.md) UC-8）
```

- [ ] **Step 4: Backend の README を直す**

`$BE/README.md` の「構成」の表の `src/handlers/` の行を、次に置き換える:

```markdown
| `src/handlers/` | `health`・`ask`（`POST /asks`）・`result`（`GET /asks/{askId}`）・`worker`（SQS）・`rides`（`PUT /rides/{rideId}`・`PUT /rides/{rideId}/route/{seq}`） |
```

同じ表の `src/lib/` の行を、次に置き換える:

```markdown
| `src/lib/` | 入力の検証（質問は `request`・走行は `rides`）・方位・プロンプト・住所・記録・会話の時間・Agent・音声合成・文字起こし |
```

「流れ」の 2. の `Agent（us-east-1・`runtimeSessionId` は会話の識別子）` を `Agent（us-east-1・`runtimeSessionId` はユーザー名と会話の識別子から作る SHA-256）` に置き換え、「流れ」の最後（3. の下）に足す:

```markdown
4. 走行: App は走行のメタ情報を `PUT /rides/{rideId}` で、ルートの点を300点までのかたまりにして `PUT /rides/{rideId}/route/{seq}` で置く。メタ情報は `updatedAt` が保存済みより新しいときだけ上書きする（古ければ `applied: false` の 200）。読み出しはスライス3。
```

- [ ] **Step 5: 親の文書をユニットに写す**

```bash
cd $ROOT && scripts/sync-docs.sh Backend
cd $BE && git status --short docs-parent/
```

Expected: `docs-parent/07_units_contracts.md` が変わっている

- [ ] **Step 6: コミット**

```bash
cd $ROOT && git add docs/07_units_contracts.md adr/0003-conversation-context.md
git commit -m "docs: record the ride endpoints and the per-user agent session"
cd $BE && git add README.md docs-parent/07_units_contracts.md
git commit -m "docs: describe the ride endpoints and the agent session ID"
```

---

### Task 6: デプロイと通しの確認

**Files:**
- Modify: `scripts/smoke.py`

**Interfaces:**
- Consumes: Task 1〜4 の API。デプロイ済みのスタック `stack-trv2-dev-backend`（出力 `ApiUrl`・`ApiKeyId`）
- Produces: デプロイ済みの走行の受け口。スライス2 plan 3（Android の送信）が使う

- [ ] **Step 1: smoke に走行と質問の追加項目を足す**

```bash
cd $BE && git apply <<'EOF'
diff --git a/scripts/smoke.py b/scripts/smoke.py
index f6919ea..9194b78 100644
--- a/scripts/smoke.py
+++ b/scripts/smoke.py
@@ -70,6 +70,29 @@ def sample(seconds_ago: int) -> dict:
     return {**SOUTH_60M, "at": at.strftime("%Y-%m-%dT%H:%M:%SZ")}
 
 
+def minutes_ago(minutes: int) -> str:
+    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
+
+
+def ride_checks(api: str, key: str, ride_id: str) -> list[bool]:
+    results = []
+    ride = {"name": "smoke", "status": "paused", "segments": [{"startedAt": minutes_ago(30), "endedAt": minutes_ago(10)}],
+            "autoEnded": False, "updatedAt": minutes_ago(10)}
+    status, body = request("PUT", f"{api}/rides/{ride_id}", key, USER, ride)
+    results.append(check("ride saved", status == 200 and body == {"rideId": ride_id, "applied": True}, str(status)))
+    status, body = request("PUT", f"{api}/rides/{ride_id}", key, USER, {**ride, "name": "older", "updatedAt": minutes_ago(20)})
+    results.append(check("older ride ignored", status == 200 and body.get("applied") is False, str(status)))
+    status, body = request("PUT", f"{api}/rides/{ride_id}", key, USER, {**ride, "name": " "})
+    results.append(check("bad ride is 400", status == 400 and body.get("error") == "bad_request", str(status)))
+    points = [{"t": minutes_ago(30 - i), "lat": TOKYO_STATION["latitude"] + i * 0.0005, "lon": TOKYO_STATION["longitude"],
+               "accuracy": 5.0, "segment": 0} for i in range(5)]
+    status, body = request("PUT", f"{api}/rides/{ride_id}/route/0", key, USER, {"points": points})
+    results.append(check("route chunk saved", status == 200 and body == {"rideId": ride_id, "seq": 0}, str(status)))
+    status, _ = request("PUT", f"{api}/rides/{ride_id}/route/0", None, USER, {"points": points})
+    results.append(check("ride without key is 403", status == 403, str(status)))
+    return results
+
+
 def ask_and_wait(api: str, key: str, body: dict) -> tuple[dict, dict, float]:
     status, accepted = request("POST", f"{api}/asks", key, USER, body)
     if status != 202:
@@ -91,7 +114,12 @@ def main() -> int:
     status, body = request("POST", f"{api}/asks", key, "BAD", {"text": "Q"})
     results.append(check("bad user is 400", status == 400 and body.get("error") == "bad_request", str(status)))
 
-    accepted, result, elapsed = ask_and_wait(api, key, {"text": "富士山の高さは？", "location": TOKYO_STATION, "headingSample": sample(10)})
+    ride_id = str(uuid.uuid4())
+    results.extend(ride_checks(api, key, ride_id))
+
+    accepted, result, elapsed = ask_and_wait(
+        api, key, {"text": "富士山の高さは？", "location": TOKYO_STATION, "headingSample": sample(10), "rideId": ride_id}
+    )
     ok = result.get("status") == "completed" and bool(result.get("answer")) and len(result.get("audio", [])) == 1
     results.append(check("text question", ok, f"{elapsed:.1f}s answer={result.get('answer')} error={result.get('error')}"))
     if ok:
@@ -99,6 +127,9 @@ def main() -> int:
             audio_ok = res.status == 200 and res.headers.get("Content-Type") == "audio/mpeg" and len(res.read()) > 1000
         results.append(check("answer audio download", audio_ok))
     print("      timings:", json.dumps(result.get("timings"), ensure_ascii=False))
+    ok = bool(result.get("askedAt")) and bool(result.get("address")) and result.get("headingDegrees") is not None
+    results.append(check("ask has when, where and heading", ok,
+                         f"askedAt={result.get('askedAt')} address={result.get('address')} heading={result.get('headingDegrees')}"))
     conversation_id = accepted.get("conversationId")
     expires = accepted.get("conversationExpiresAt")
     results.append(check("conversation expiry returned", bool(expires), str(expires)))
EOF
env/bin/python -m py_compile scripts/smoke.py && \rm -rf scripts/__pycache__
```

Expected: エラーなし

- [ ] **Step 2: コミット**

```bash
cd $BE && git add scripts/smoke.py
git commit -m "test: check the ride endpoints and the new ask fields after a deploy"
```

- [ ] **Step 3: 利用者にデプロイの確認を取る**

利用者に「Backend を `stack-trv2-dev-backend` にデプロイし、smoke を回してよいか」を聞き、明示の了承を待つ。了承がなければ、ここで止めて ledger に残す（デプロイは利用者が明示したときだけ）。

- [ ] **Step 4: 前提を確かめてデプロイする**

```bash
export AWS_PROFILE=touring AWS_REGION=ap-northeast-1
aws cloudformation describe-stacks --stack-name stack-trv2-dev-backend --query "Stacks[0].StackStatus" --output text
aws lambda get-function --function-name lambda-trv2-dev-rides 2>&1 | tail -1
cd $BE && sam build 2>&1 | tail -2 && sam deploy --no-confirm-changeset 2>&1 | tail -15
```

Expected: 1行目が `UPDATE_COMPLETE`（か `CREATE_COMPLETE`）、2行目が「無い」（`ResourceNotFoundException`）、最後に `Successfully created/updated stack - stack-trv2-dev-backend`。失敗したら、エラーを調べてから直す（同じ操作を繰り返さない）。

- [ ] **Step 5: 通しの確認を回す**

```bash
cd $BE && AWS_PROFILE=touring env/bin/python scripts/smoke.py
```

Expected: 最後の行が `N/N passed`（すべて OK）。`ride saved`・`older ride ignored`・`bad ride is 400`・`route chunk saved`・`ride without key is 403`・`ask has when, where and heading` を含む。質問の確かめ（`same conversation`・`follow-up answered`）が通ることで、セッションの識別子を変えても会話が続くことも確かめる。

- [ ] **Step 6: 記録を見る（任意）**

```bash
aws dynamodb query --table-name dynamodb-trv2-dev-records --key-condition-expression "pk = :p AND begins_with(sk, :s)" \
  --expression-attribute-values '{":p":{"S":"USER#smoketest"},":s":{"S":"RIDE#"}}' --query "Items[].sk.S" --output text | tr '\t' '\n' | tail -4
```

Expected: smoke が置いた `RIDE#<id>` と `RIDE#<id>#ROUTE#00000`
