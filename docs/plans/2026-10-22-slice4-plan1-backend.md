# スライス4 計画1: Backend（質問できなかった地点・記録の読み出し・Backend の issue） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend が、Android に届かなかった質問（質問できなかった地点）を受け取って住所と方位を付けて置き、引き継ぎのためにユーザーの記録をページ送りで返す。あわせて、範囲に入れた Backend の issue（#2・#3・#16・#17・#18・#19）を直す。デプロイして、通しの確認（smoke）を通す。

**Architecture:** 既存の作り（API Gateway＋Lambda・1つの DynamoDB テーブル・`lib/` に検証と記録、`handlers/` に受け口）を伸ばす。質問できなかった地点は、`ASK#<askId>` に `status: "offline"` で置く（`askId` は Android が作る）。受け口 `PUT /asks/{askId}/offline` は会話のメモと削除と同じ `lambda-trv2-dev-ask-edit` が受け、地点メモと同じく、住所と方位を最初に受けたときに決める。書き込みは `Update` にして、会話のメモを消さない。記録の読み出し `GET /records` は新しい `lambda-trv2-dev-records` が受け、`USER#<名前>` のパーティションを強い一貫性で1回問い合わせるごとに1ページを返す。続きは、ソートキーだけを入れた `cursor` で読む。

**Tech Stack:** Python 3.13（Lambda）・SAM・boto3・pytest・moto・openapi-spec-validator（どれも既存。足すものは無い）。

**Spec:** [docs/specs/2026-10-22-slice4-design.md](../specs/2026-10-22-slice4-design.md)（§4.4・§6.2・§9・§10・§11）。決定の記録は [adr/0010](../../adr/0010-read-the-cloud-only-when-taking-over.md)。

**範囲に入れた issue:** Backend #2・#3・#16・#17・#18・#19（spec §2）。Android の issue（#28・#53・#58・#62）は plan 2 で扱う。

**計画を書くときに決めたこと（spec からの具体化）:**
- 質問できなかった地点の記録は、Backend が受け付けた質問と同じ項目名にそろえる（受け付けた日時は `receivedAt`。`GET /records` で同じ形で読めるように）。中身は `askId`・`userName`・`status: "offline"`・`rideId`・`receivedAt`（録音を終えた時刻）・`location`・`updatedAt`・`address`・`headingDegrees`・`savedAt`。会話の識別子・文字起こし・回答は持たない。
- `PUT /asks/{askId}/offline` の応答は、地点メモと同じく `200 {askId, applied, address, headingDegrees}`（古くて書かなかったときは、保存済みの住所と方位）。同じ `askId` で Backend が受け付けた質問があれば `409 {"error": "conflict"}`。質問か走行に跡があれば 410。位置が不正なら 400（Android が自分の位置から作るので、送り手の誤り）。方位の材料が不正なら、方位なし。`rideId` は必須。
- 住所と方位は、最初に受けたときに決め、あとの `PUT` では変えない。住所を確定できなかったときと、方位が無かったときは、次の `PUT` で求め直す（地点メモも同じに直す。Backend #17）。跡があれば、住所を引く前に 410 を返す（跡は強い一貫性の `get_item` で確かめ、書き込みでもトランザクションで確かめる）。
- 受け口を見分けるのは、API Gateway のイベントの `resource`（`/asks/{askId}/offline`）。会話のメモの受け口は今のまま。
- `GET /records` の応答は `{items, cursor}`。`cursor` は最後のページで `null`。1ページに返すものが無くても、`cursor` があれば続きがある（会話の記録・文字起こしの記録だけのページ）。項目の形は次のとおり（spec §6.2 の具体化。spec に追記する）。
  - `ride`: `rideId`・`name`・`status`・`segments`・`autoEnded`・`updatedAt`・`memo`
  - `route`: `rideId`・`seq`・`points`
  - `note`: `rideId`・`noteId`・`at`・`location`・`text`・`updatedAt`・`address`・`headingDegrees`
  - `ask`: `askId`・`status`（`processing` / `completed` / `failed` / `offline`）・`askedAt`・`question`・`transcript`・`answer`・`error`・`answeredAt`（聞ける回答があるときだけ。`synthesizedAt` か `agentDoneAt`）・`location`・`address`・`headingDegrees`・`inputType`・`conversationId`・`newConversation`（会話の開始時刻と受け付けた時刻が同じ）・`rideId`・`memo`・`memoUpdatedAt`・`updatedAt`（質問できなかった地点だけ）
  - `deleted`: `target`（`ask` / `ride` / `note`）・`id`・`rideId`・`deletedAt`。spec の `kind` は項目の種類と重なるので、跡の種類は `target` にした
  - 値が無い項目は省かずに `null` で返す。整数に等しい数は整数で返る（DynamoDB の数の戻し方。今の `GET /asks` と同じ）
- `cursor` は `{"sk": <続きのソートキー>}` の JSON を URL 向けの base64（`=` を落とす）にしたもの。パーティションキーは `x-user-name` から作り直し、`cursor` の中の値は使わない。読めない `cursor` は 400。
- Backend #3: SQS に積めなかった質問は、`failed` にせずに記録と録音を消し、`503 {"error": "unavailable"}` を返す（issue の対応案から変えた）。Android は 503 を通信の失敗として扱い、質問できなかった地点を残す（spec §4.1）ので、Backend に `failed` の質問が残ると、引き継ぎで同じ質問が2つ（失敗と質問できなかった地点）入ってしまうため。
- Backend #2: 会話の記録（`CONV#`）に、テーブルの TTL の `expiresAt`（始まりから24時間後の UNIX 秒）を付ける。会話は長くて55分なので足りる。
- Backend #18: 削除の跡の書き込みと、跡を見て書くトランザクションは、同じ記録のトランザクションと重なって断られたら、50ms・100ms あけて2回まで試し直す。それでも断られたら 5xx のまま（Android は送り直す）。openapi と 07 に「5xx は送り直してよい。書き込みと削除は何度送っても同じ結果」と書く。
- Backend #16: 2000字は、前後の空白を落としたあとのコードポイントで数える。openapi と 07 に書く。
- Backend #19: worker の守りのテストを足し、`ask_edit` の識別子の検証を `rides.path_id` にまとめ、smoke に削除のあとのルートの `PUT` を足す。
- `lambda-trv2-dev-ask-edit` に、住所のための `geo-places:ReverseGeocode` と `GEO_REGION` を足す。`lambda-trv2-dev-records` は `DynamoDBReadPolicy` だけ。1ページ（最大1MB）を JSON にするので、メモリは 512MB にする。
- smoke は、質問できなかった地点を smoke の走行に付けて置き、`GET /records` で全部を読んで、作った記録が読めること、走行を消したあとは跡だけが読めることを確かめる。smoke の検査は30件から39件になる。

この計画のコードは、使い捨てのフォルダでタスクの順にコミットし、各コミットで `__pycache__` を消してから pytest（今の218件から、最後は267件）が通ること、各タスクのテストだけを1つ前のコミットに当てると落ちること（守りのテスト2件を除く。各 Task の Step 2 に書いた）、`sam validate --lint` が通ることを確かめてから書いた。デプロイと smoke は、実行のときに利用者の確認を取ってから行う。

## Global Constraints

- 作業するリポジトリは `Backend/`（`TouringProjectV2_Backend`）と親。どちらも `main` から作業ブランチ `slice4-plan1` を切る。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。Backend の PR の本文には `Fixes #2`・`Fixes #3`・`Fixes #16`・`Fixes #17`・`Fixes #18`・`Fixes #19` を書く。
- **デプロイは、利用者が明示したときだけ行う。** Task 8 の途中で確認を取る。AWS は `AWS_PROFILE=touring`（使えないときは利用者に聞く）。リージョンは `ap-northeast-1`。名前には `trv2` を付ける。
- ユーザー名は英小文字と数字の3〜20文字（`x-user-name`）。他人の記録は無いものとして扱い、読み出しでも返さない。既存の接続キーの検査を通す（`/health` 以外）。
- 不正な入力は `400 {"error": "bad_request", "message": <理由>}`（07 UC-4）。削除の跡があるときは `410 {"error": "deleted"}`（adr/0009）。
- 本文の上限は2000字（前後の空白を落としたあとのコードポイント。US-D-04.003・US-D-08.003・Backend #16）。
- LLM の入力のトークンを増やさない（この plan はプロンプトに触れない）。
- ログに、質問・回答・メモ・地点メモの本文と位置を出さない（`handlers/common.py` の `log` の決まり）。
- 接続キー・API の URL・アカウント ID を、コードや文書に書かない。smoke の出力に接続キーを出さない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`BE=$ROOT/Backend`。テストは `cd $BE && env/bin/pytest -q`（絞るときは `env/bin/pytest -q tests/test_xxx.py`）。この Mac の zsh では、変数に入れた複数のパスは分割されないので、コマンドにはパスをそのまま書く。

## Review Focus

- 走行を消すのと同時に、その走行のルートや地点メモの送信が届く → トランザクションが重なって断られても試し直し、跡を見て 410 になる（5xx にならない）。Task 2 の `test_a_write_that_meets_a_deletion_in_progress_is_tried_again_and_refused`。
- 質問できなかった地点にメモを書いたあと、端末が地点の新しい版を送り直す → メモは消えず、住所と方位は最初の値のまま。Task 4 の `test_a_newer_version_keeps_the_memo_place_and_heading`。
- 他人のパーティションを指す `cursor` を作って読む → 自分の記録しか返らない。Task 5 の `test_a_cursor_never_reads_another_users_records`。
- 2000字ちょうどの本文に、末尾の改行が付く → 断らない。Task 3 の `test_a_memo_of_2000_characters_and_a_trailing_newline_is_kept`・`test_a_note_of_2000_characters_and_a_trailing_newline_is_kept`。
- 質問を受け付けたのに SQS に積めない → 処理されない `pending` の質問が残らない（引き継ぎで読み込まれない）。Task 1 の `test_an_ask_that_cannot_be_queued_is_503_and_leaves_no_ask_or_audio`。

---

## ファイル構成（`Backend/` から）

| パス | 役割 | Task |
|---|---|---|
| `src/lib/store.py` | 会話の記録の期限と一貫した読み出し・質問を捨てる（1）、跡の書き込みとトランザクションの試し直し・質問の一貫した読み出し（2）、跡の有無の確かめ（3）、質問できなかった地点の書き込み（4）、記録の1ページの問い合わせ（5） | 1〜5 |
| `src/handlers/ask.py` | SQS に積めなかった質問を消して 503（1） | 1 |
| `src/handlers/ask_edit.py` | 識別子の検証を `rides.path_id` に（2）。`PUT /asks/{askId}/offline`（4） | 2・4 |
| `src/lib/rides.py`・`src/lib/notes.py` | 前後の空白を落としてから長さを数える（3） | 3 |
| `src/handlers/rides.py` | 地点メモ: 跡を先に確かめる・方位を最初の値に固定（3） | 3 |
| `src/lib/offline.py`（新規） | 質問できなかった地点の検証 | 4 |
| `src/lib/records.py`（新規） | `cursor` の符号化と、読み出す形 | 5 |
| `src/handlers/records.py`（新規） | `GET /records` | 5 |
| `openapi.yaml`・`template.yaml` | API の正本・2つの経路と1つの Lambda・ask-edit の権限・TTL の注記 | 6 |
| `README.md`・親の `docs/07_units_contracts.md`・`docs-parent/`・親の spec | 文書 | 7 |
| `scripts/smoke.py` | デプロイ後の通しの確認 | 8 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: 両方のリポジトリでブランチを切り、今のテストを回す**

```bash
cd $ROOT && git switch main && git switch -c slice4-plan1
cd $BE && git switch main && git pull --ff-only && git switch -c slice4-plan1
cd $BE && env/bin/pytest -q 2>&1 | tail -1
```

Expected: `218 passed`

---

### Task 1: 質問の受け付けの直し（Backend #2・#3）

**Files:**
- Modify: `src/lib/store.py`・`src/handlers/ask.py`
- Test: `tests/test_store.py`・`tests/test_ask.py`

**Interfaces:**
- Consumes: 既存の `store.conversation_started_at`・`store.create_ask`・`clients.sqs()`・`clients.s3()`
- Produces:
  - `store.CONVERSATION_TTL_SECONDS = 86400`。`store.conversation_started_at(user, conversation_id, now_iso) -> str` は、会話の記録に `expiresAt`（UNIX 秒）を付け、条件付きの書き込みに負けたときは強い一貫性で読む
  - `store.discard_ask(user: str, ask_id: str) -> None`（跡を残さずに消す。処理に回せなかった質問だけに使う）
  - `POST /asks` は、SQS に積めなければ `503 {"error": "unavailable"}`。質問の記録と録音は残さない（会話の記録は残り、TTL で消える）

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_ask.py b/tests/test_ask.py
index 71fb246..7c07c13 100644
--- a/tests/test_ask.py
+++ b/tests/test_ask.py
@@ -102,3 +102,16 @@ def test_a_location_too_large_for_a_float_is_dropped_not_a_crash(aws):
     result = call({"text": "Q", "location": {"latitude": 10 ** 400, "longitude": 139.0}})
     assert result["statusCode"] == 202
     assert "location" not in store.get_ask("rider01", json.loads(result["body"])["askId"])
+
+
+def test_an_ask_that_cannot_be_queued_is_503_and_leaves_no_ask_or_audio(aws, monkeypatch):
+    # Nothing would ever take a pending ask without its message, so it is removed (Backend #3).
+    def broken(**params):
+        raise RuntimeError("queue unavailable")
+
+    monkeypatch.setattr(ask.clients.sqs(), "send_message", broken)
+    audio = b"\x01\x00" * (MIN_AUDIO_BYTES // 2)
+    result = call({"audio": base64.b64encode(audio).decode(), "rideId": RID})
+    assert result["statusCode"] == 503 and json.loads(result["body"]) == {"error": "unavailable"}
+    assert [i["sk"] for i in aws.table.scan()["Items"] if i["sk"].startswith("ASK#")] == []
+    assert aws.s3.list_objects_v2(Bucket=aws.bucket).get("KeyCount") == 0
diff --git a/tests/test_store.py b/tests/test_store.py
index 884837b..fa7ea46 100644
--- a/tests/test_store.py
+++ b/tests/test_store.py
@@ -47,6 +47,32 @@ def test_conversation_start_is_kept_from_first_question(aws):
     assert store.conversation_started_at(USER, cid, "2026-10-16T03:10:00.000Z") == "2026-10-16T03:00:00.000Z"
 
 
+def test_a_conversation_record_expires_a_day_after_it_starts(aws):
+    cid = "33333333-3333-4333-8333-333333333333"
+    store.conversation_started_at(USER, cid, "2026-10-16T03:00:00.000Z")
+    item = aws.table.get_item(Key={"pk": f"USER#{USER}", "sk": f"CONV#{cid}"})["Item"]
+    # 2026-10-16T03:00:00Z is 1792119600 in UNIX seconds.
+    assert item["expiresAt"] == 1792119600 + 24 * 60 * 60
+
+
+def test_a_conversation_started_meanwhile_is_read_consistently(aws, monkeypatch):
+    # The second of two first questions reads the record the first one just wrote; moto is always consistent.
+    from lib import clients
+    table = clients.table()
+    reads = []
+    get_item = table.get_item
+
+    def spy(**params):
+        reads.append(params)
+        return get_item(**params)
+
+    monkeypatch.setattr(table, "get_item", spy)
+    cid = "33333333-3333-4333-8333-333333333333"
+    store.conversation_started_at(USER, cid, "2026-10-16T03:00:00.000Z")
+    assert store.conversation_started_at(USER, cid, "2026-10-16T03:10:00.000Z") == "2026-10-16T03:00:00.000Z"
+    assert len(reads) == 1 and reads[0].get("ConsistentRead") is True
+
+
 def test_a_deletion_mark_is_one_record_however_often_it_is_written(aws):
     store.mark_deleted("rider01", "note", "n1", "2026-10-21T01:00:00.000Z", ride_id="r1")
     store.mark_deleted("rider01", "note", "n1", "2026-10-21T02:00:00.000Z", ride_id="r1")
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_store.py tests/test_ask.py 2>&1 | tail -1`
Expected: `3 failed, 21 passed`（`expiresAt` が無い・一貫した読み出しでない・SQS の例外がそのまま上がる）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/handlers/ask.py b/src/handlers/ask.py
index 03a30df..d048ca8 100644
--- a/src/handlers/ask.py
+++ b/src/handlers/ask.py
@@ -11,6 +11,13 @@ from lib import clients, conversation, store
 from lib.request import BadRequest, parse_ask, user_name
 
 
+def _discard_audio(key: str) -> None:
+    try:
+        clients.s3().delete_object(Bucket=os.environ["AUDIO_BUCKET"], Key=key)
+    except Exception as error:  # noqa: BLE001 - the 1-day lifecycle rule removes it anyway
+        log({"event": "audio_delete_failed", "error": type(error).__name__})
+
+
 def handler(event, context):
     try:
         user = user_name(event)
@@ -46,7 +53,15 @@ def handler(event, context):
             Bucket=os.environ["AUDIO_BUCKET"], Key=item["audioKey"], Body=ask.audio, ContentType="application/octet-stream"
         )
     store.create_ask(item)
-    clients.sqs().send_message(QueueUrl=os.environ["QUEUE_URL"], MessageBody=json.dumps({"userName": user, "askId": ask_id}))
+    try:
+        clients.sqs().send_message(QueueUrl=os.environ["QUEUE_URL"], MessageBody=json.dumps({"userName": user, "askId": ask_id}))
+    except Exception as error:  # noqa: BLE001 - reported to the app as 503, which it retries
+        # No worker would ever take the ask, so it is not left pending; the app keeps an unreached ask instead (Backend #3).
+        log({"event": "ask_queue_failed", "askId": ask_id, "error": type(error).__name__})
+        store.discard_ask(user, ask_id)
+        if ask.audio is not None:
+            _discard_audio(item["audioKey"])
+        return response(503, {"error": "unavailable"})
     log({"event": "ask_accepted", "askId": ask_id, "inputType": item["inputType"],
          "audioBytes": len(ask.audio) if ask.audio is not None else 0})
     return response(202, {"askId": ask_id, "conversationId": conversation_id, "conversationExpiresAt": iso(expires_at)})
diff --git a/src/lib/store.py b/src/lib/store.py
index 4101d31..e0564b7 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -3,6 +3,7 @@ RIDE#<id>#NOTE#<id>, DELETED#<KIND>#<id> or TRANSCRIPTION#<id>."""
 from __future__ import annotations
 
 import json
+from datetime import datetime
 from decimal import Decimal
 from typing import Any, Optional
 
@@ -11,6 +12,8 @@ from botocore.exceptions import ClientError
 from lib import clients
 
 _CONDITION_FAILED = "ConditionalCheckFailedException"
+# A conversation lasts 55 minutes at most (07 UC-5); its record only has to outlive that (Backend #2).
+CONVERSATION_TTL_SECONDS = 24 * 60 * 60
 _CANCELLED = "TransactionCanceledException"
 
 
@@ -84,19 +87,27 @@ def _conversation_key(user: str, conversation_id: str) -> dict:
 def conversation_started_at(user: str, conversation_id: str, now_iso: str) -> str:
     """When this conversation's first question arrived (recorded on first sight)."""
     key = _conversation_key(user, conversation_id)
+    expires_at = int(datetime.fromisoformat(now_iso.replace("Z", "+00:00")).timestamp()) + CONVERSATION_TTL_SECONDS
     try:
-        clients.table().put_item(Item={**key, "startedAt": now_iso}, ConditionExpression="attribute_not_exists(pk)")
+        clients.table().put_item(Item={**key, "startedAt": now_iso, "expiresAt": expires_at},
+                                 ConditionExpression="attribute_not_exists(pk)")
         return now_iso
     except ClientError as error:
         if error.response["Error"]["Code"] != _CONDITION_FAILED:
             raise
-    return clients.table().get_item(Key=key)["Item"]["startedAt"]
+    # Written by another first question a moment ago, so the read must see it.
+    return clients.table().get_item(Key=key, ConsistentRead=True)["Item"]["startedAt"]
 
 
 def create_ask(item: dict) -> None:
     clients.table().put_item(Item=_to_item(item))
 
 
+def discard_ask(user: str, ask_id: str) -> None:
+    """Removes an ask that was never queued, leaving no deletion mark: the app never learnt of it."""
+    clients.table().delete_item(Key=ask_key(user, ask_id))
+
+
 def claim_ask(user: str, ask_id: str) -> Optional[dict]:
     """pending -> processing, once. None if already claimed or missing."""
     return _claim(ask_key(user, ask_id))
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `221 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/handlers/ask.py src/lib/store.py tests/test_ask.py tests/test_store.py
git commit -m "fix: read a just-started conversation consistently, expire it, and drop an ask that cannot be queued (#2, #3)"
```

---

### Task 2: 削除と書き込みの重なり・worker の守り（Backend #18・#19）

**Files:**
- Modify: `src/lib/store.py`・`src/handlers/ask_edit.py`
- Test: `tests/test_store.py`・`tests/test_worker.py`

**Interfaces:**
- Consumes: Task 1 までの `store`
- Produces:
  - `store._sleep`（テストで差し替える待ち）・`store._retrying_conflicts(write: Callable[[], Any]) -> Any`（`TransactionConflictException`、またはトランザクションの取り消しの理由が `TransactionConflict` のとき、50ms・100ms あけて2回まで試し直す）
  - `store.mark_deleted` と `store._write_unless_deleted` は試し直しを通る。試し直したトランザクションが跡を見たら `Deleted`
  - `store.get_ask(user, ask_id, consistent: bool = False) -> Optional[dict]`。`store.delete_ask` は `consistent=True` で読む
  - `handlers.ask_edit` は `rides.path_id(event, "askId")` で識別子を確かめる（`_ask_id` は消す）

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_store.py b/tests/test_store.py
index fa7ea46..0524eb9 100644
--- a/tests/test_store.py
+++ b/tests/test_store.py
@@ -1,5 +1,8 @@
 """Tests for the DynamoDB record helpers (moto)."""
-from lib import store
+import pytest
+from botocore.exceptions import ClientError
+
+from lib import clients, store
 
 USER, ASK = "rider01", "11111111-1111-4111-8111-111111111111"
 
@@ -84,3 +87,86 @@ def test_a_deletion_mark_is_one_record_however_often_it_is_written(aws):
 def test_update_ask_does_not_create_a_missing_ask(aws):
     assert store.update_ask("rider01", "a1", {"status": "completed"}) is False
     assert aws.table.scan()["Items"] == []
+
+
+def _conflict(operation):
+    return ClientError({"Error": {"Code": "TransactionConflictException", "Message": "busy"}}, operation)
+
+
+def _cancelled(*codes):
+    reasons = [{"Code": code} for code in codes]
+    return ClientError({"Error": {"Code": "TransactionCanceledException", "Message": "cancelled"},
+                        "CancellationReasons": reasons}, "TransactWriteItems")
+
+
+@pytest.fixture
+def no_wait(monkeypatch):
+    waits = []
+    monkeypatch.setattr(store, "_sleep", waits.append)
+    return waits
+
+
+def test_a_mark_written_during_a_transaction_on_it_is_tried_again(aws, monkeypatch, no_wait):
+    # A PUT checking the same mark in a transaction makes the plain write fail for a moment (Backend #18).
+    table = clients.table()
+    put_item = table.put_item
+    failures = iter([_conflict("PutItem")])
+
+    def busy_once(**params):
+        error = next(failures, None)
+        if error:
+            raise error
+        return put_item(**params)
+
+    monkeypatch.setattr(table, "put_item", busy_once)
+    store.mark_deleted(USER, "ride", "r1", "2026-10-21T01:00:00.000Z")
+    assert [i["sk"] for i in aws.table.scan()["Items"]] == ["DELETED#RIDE#r1"]
+    assert len(no_wait) == 1
+
+
+def test_a_mark_that_stays_busy_gives_up_after_three_tries(aws, monkeypatch, no_wait):
+    table = clients.table()
+
+    def busy(**params):
+        raise _conflict("PutItem")
+
+    monkeypatch.setattr(table, "put_item", busy)
+    with pytest.raises(ClientError):
+        store.mark_deleted(USER, "ride", "r1", "2026-10-21T01:00:00.000Z")
+    assert len(no_wait) == 2
+
+
+def test_a_write_that_meets_a_deletion_in_progress_is_tried_again_and_refused(aws, monkeypatch, no_wait):
+    # The deletion's mark lands while the PUT's transaction runs: the retry sees the mark and answers Deleted.
+    client = clients.table().meta.client
+    transact = client.transact_write_items
+    state = {"first": True}
+
+    def conflict_then_mark(**params):
+        if state["first"]:
+            state["first"] = False
+            store.mark_deleted(USER, "ride", "r1", "2026-10-21T01:00:00.000Z")
+            raise _cancelled("None", "TransactionConflict")
+        return transact(**params)
+
+    monkeypatch.setattr(client, "transact_write_items", conflict_then_mark)
+    with pytest.raises(store.Deleted):
+        store.put_ride(USER, "r1", {"name": "n", "updatedAt": "2026-10-21T02:00:00.000Z"})
+    assert len(no_wait) == 1 and "RIDE#r1" not in [i["sk"] for i in aws.table.scan()["Items"]]
+
+
+def test_deleting_an_ask_reads_its_ride_consistently(aws, monkeypatch):
+    # The ask may have been written a moment ago; its mark must still name its ride (Backend #18).
+    table = clients.table()
+    reads = []
+    get_item = table.get_item
+
+    def spy(**params):
+        reads.append(params)
+        return get_item(**params)
+
+    store.create_ask(new_ask(rideId="r1"))
+    monkeypatch.setattr(table, "get_item", spy)
+    store.delete_ask(USER, ASK, "2026-10-21T01:00:00.000Z")
+    assert reads and all(r.get("ConsistentRead") is True for r in reads)
+    assert aws.table.get_item(Key=store.deleted_key(USER, "ask", ASK))["Item"]["rideId"] == "r1"
diff --git a/tests/test_worker.py b/tests/test_worker.py
index 896e7ca..e24866c 100644
--- a/tests/test_worker.py
+++ b/tests/test_worker.py
@@ -198,3 +198,17 @@ def test_an_ask_deleted_while_it_is_answered_is_not_written_back(aws):
     rec.invoke_agent = delete_then_answer
     worker.process(USER, ASK, rec.steps())
     assert store.get_ask(USER, ASK) is None
+
+
+def test_an_ask_deleted_before_a_crash_is_not_written_back_as_failed(aws):
+    # The catch-all in process marks a crashed ask failed; it must not bring back an ask deleted meanwhile (Backend #19).
+    put(aws, audio=False)
+    rec = Recorder()
+
+    def crash(lat, lon):
+        store.delete_ask(USER, ASK, iso(T0))
+        raise RuntimeError("unexpected")
+
+    rec.describe_location = crash
+    worker.process(USER, ASK, rec.steps())
+    assert store.get_ask(USER, ASK) is None
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_store.py tests/test_worker.py 2>&1 | tail -1`
Expected: `1 failed, 25 passed, 3 errors`（`store._sleep` が無い・質問を一貫して読まない）。worker の `test_an_ask_deleted_before_a_crash_is_not_written_back_as_failed` は今の作りで通る守りのテスト（Backend #19 の指摘は、これを確かめるテストが無いこと）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/handlers/ask_edit.py b/src/handlers/ask_edit.py
index 9deeee0..26f794b 100644
--- a/src/handlers/ask_edit.py
+++ b/src/handlers/ask_edit.py
@@ -3,13 +3,13 @@ from __future__ import annotations
 
 from handlers.common import deleted, iso, log, no_content, response, utc_now
 from lib import rides, store
-from lib.request import UUID_RE, BadRequest, user_name
+from lib.request import BadRequest, user_name
 
 
 def handler(event, context):
     try:
         user = user_name(event)
-        ask_id = _ask_id(event)
+        ask_id = rides.path_id(event, "askId")
         if event.get("httpMethod") == "DELETE":
             store.delete_ask(user, ask_id, iso(utc_now()))
             log({"event": "ask_deleted", "askId": ask_id})
@@ -21,13 +21,6 @@ def handler(event, context):
         return deleted()
 
 
-def _ask_id(event: dict) -> str:
-    value = (event.get("pathParameters") or {}).get("askId") or ""
-    if not UUID_RE.match(value):
-        raise BadRequest("askId must be a lowercase UUID")
-    return value
-
-
 def _memo(event: dict, user: str, ask_id: str) -> dict:
     memo, updated_at = rides.parse_ask_memo(event)
     applied = store.put_ask_memo(user, ask_id, memo, updated_at)
diff --git a/src/lib/store.py b/src/lib/store.py
index e0564b7..ccd620f 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -3,6 +3,8 @@ RIDE#<id>#NOTE#<id>, DELETED#<KIND>#<id> or TRANSCRIPTION#<id>."""
 from __future__ import annotations
 
 import json
+import time
+from collections.abc import Callable
 from datetime import datetime
 from decimal import Decimal
 from typing import Any, Optional
@@ -15,6 +17,14 @@ _CONDITION_FAILED = "ConditionalCheckFailedException"
 # A conversation lasts 55 minutes at most (07 UC-5); its record only has to outlive that (Backend #2).
 CONVERSATION_TTL_SECONDS = 24 * 60 * 60
 _CANCELLED = "TransactionCanceledException"
+_CONFLICT = "TransactionConflictException"
+# A write that meets a transaction on the same item fails at once; botocore does not retry it (Backend #18).
+_CONFLICT_TRIES = 3
+_sleep: Callable[[float], None] = time.sleep
+
+
+class _Conflict(Exception):
+    """A transaction on the same item was in progress; trying again a moment later will do."""
 
 
 class Deleted(Exception):
@@ -49,31 +59,53 @@ def deleted_key(user: str, kind: str, record_id: str) -> dict:
     return {"pk": f"USER#{user}", "sk": f"DELETED#{kind.upper()}#{record_id}"}
 
 
+def _retrying_conflicts(write: Callable[[], Any]) -> Any:
+    """Runs write, trying again twice (after 50 and 100 ms) while a transaction on the same item is in progress."""
+    for attempt in range(_CONFLICT_TRIES):
+        try:
+            return write()
+        except _Conflict:
+            if attempt == _CONFLICT_TRIES - 1:
+                raise
+        except ClientError as error:
+            if error.response["Error"]["Code"] != _CONFLICT or attempt == _CONFLICT_TRIES - 1:
+                raise
+        _sleep(0.05 * 2 ** attempt)
+
+
 def mark_deleted(user: str, kind: str, record_id: str, deleted_at: str, ride_id: Optional[str] = None) -> None:
     """Writes the deletion mark; marking again keeps one. Marks never expire (adr/0009)."""
-    clients.table().put_item(Item=_to_item({**deleted_key(user, kind, record_id), "kind": kind, "id": record_id,
-                                            "rideId": ride_id, "deletedAt": deleted_at}))
+    item = _to_item({**deleted_key(user, kind, record_id), "kind": kind, "id": record_id, "rideId": ride_id,
+                     "deletedAt": deleted_at})
+    _retrying_conflicts(lambda: clients.table().put_item(Item=item))
 
 
 def _write_unless_deleted(write: dict, marks: list) -> bool:
     """Runs one transaction write (a Put or an Update) unless one of the deletion marks exists, atomically, so that a
     deletion that lands at the same time cannot be undone. True when written; False when the write's own condition
-    failed. Raises Deleted when a mark exists. The table's client takes plain values, as the table does."""
+    failed. Raises Deleted when a mark exists. The table's client takes plain values, as the table does. A deletion
+    marking the same record at that moment cancels the transaction; it is tried again, and then sees the mark."""
     table = clients.table()
     checks = [{"ConditionCheck": {"TableName": table.name, "Key": mark, "ConditionExpression": "attribute_not_exists(pk)"}}
               for mark in marks]
-    try:
-        table.meta.client.transact_write_items(TransactItems=[write, *checks])
-    except ClientError as error:
-        if error.response["Error"]["Code"] != _CANCELLED:
+
+    def attempt() -> bool:
+        try:
+            table.meta.client.transact_write_items(TransactItems=[write, *checks])
+        except ClientError as error:
+            if error.response["Error"]["Code"] != _CANCELLED:
+                raise
+            codes = [reason.get("Code") for reason in error.response.get("CancellationReasons") or []]
+            if "ConditionalCheckFailed" in codes[1:]:
+                raise Deleted() from None
+            if codes[:1] == ["ConditionalCheckFailed"]:
+                return False
+            if "TransactionConflict" in codes:
+                raise _Conflict() from None
             raise
-        codes = [reason.get("Code") for reason in error.response.get("CancellationReasons") or []]
-        if "ConditionalCheckFailed" in codes[1:]:
-            raise Deleted() from None
-        if codes[:1] == ["ConditionalCheckFailed"]:
-            return False
-        raise
-    return True
+        return True
+
+    return _retrying_conflicts(attempt)
 
 
 def ask_key(user: str, ask_id: str) -> dict:
@@ -163,8 +195,8 @@ def put_ask_memo(user: str, ask_id: str, memo: Optional[str], updated_at: str) -
     return _write_unless_deleted(update, [deleted_key(user, "ask", ask_id)])
 
 
-def get_ask(user: str, ask_id: str) -> Optional[dict]:
-    item = clients.table().get_item(Key=ask_key(user, ask_id)).get("Item")
+def get_ask(user: str, ask_id: str, consistent: bool = False) -> Optional[dict]:
+    item = clients.table().get_item(Key=ask_key(user, ask_id), ConsistentRead=consistent).get("Item")
     return _from_item(item) if item else None
 
 
@@ -238,7 +270,8 @@ def _delete_all(keys: list) -> None:
 
 def delete_ask(user: str, ask_id: str, deleted_at: str) -> None:
     """Marks the ask deleted, then removes it. Deleting a missing ask still leaves the mark (adr/0009)."""
-    stored = get_ask(user, ask_id)
+    # The ask may have been written a moment ago; its mark must still name its ride (Backend #18).
+    stored = get_ask(user, ask_id, consistent=True)
     mark_deleted(user, "ask", ask_id, deleted_at, ride_id=(stored or {}).get("rideId"))
     clients.table().delete_item(Key=ask_key(user, ask_id))
 
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `226 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/store.py src/handlers/ask_edit.py tests/test_store.py tests/test_worker.py
git commit -m "fix: try a deletion mark or a write again when a transaction on it is in progress, and read a deleted ask's ride consistently (#18, #19)"
```

---

### Task 3: メモの文字数と、地点メモの住所・方位（Backend #16・#17）

**Files:**
- Modify: `src/lib/rides.py`・`src/lib/notes.py`・`src/lib/store.py`・`src/handlers/rides.py`
- Test: `tests/test_ask_edit.py`・`tests/test_notes.py`

**Interfaces:**
- Consumes: Task 2 までの `store`
- Produces:
  - `rides.memo_text` と `notes.parse_note` は、前後の空白を落としてから長さを数える
  - `store.has_deletion_mark(user: str, marks: list) -> bool`（`marks` は `(kind, id)` の並び。強い一貫性で読む。Task 4 も使う）
  - 地点メモの `PUT` は、地点メモか走行に跡があれば、住所を引く前に `store.Deleted`（410）。保存済みの方位があれば、それを使う

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_ask_edit.py b/tests/test_ask_edit.py
index 76de49f..6568d17 100644
--- a/tests/test_ask_edit.py
+++ b/tests/test_ask_edit.py
@@ -78,3 +78,10 @@ def test_a_memo_of_2000_emoji_is_kept(aws):
     # Android counts an emoji as two characters, so it never sends more than the Backend takes.
     put_ask()
     assert put_memo("😀" * 2000)["statusCode"] == 200
+
+
+def test_a_memo_of_2000_characters_and_a_trailing_newline_is_kept(aws):
+    # The length is counted after the surrounding blanks are dropped (Backend #16).
+    put_ask()
+    assert put_memo("あ" * 2000 + "\n")["statusCode"] == 200
+    assert store.get_ask(USER, ASK)["memo"] == "あ" * 2000
diff --git a/tests/test_notes.py b/tests/test_notes.py
index 0375c21..8b74396 100644
--- a/tests/test_notes.py
+++ b/tests/test_notes.py
@@ -131,3 +131,35 @@ def test_sending_the_same_note_again_changes_nothing(aws, places):
     again = put_note(note_body())
     assert again["statusCode"] == 200 and answer(again)["applied"] is False
     assert len(places) == 1 and len(aws.table.scan()["Items"]) == 1
+
+
+def test_a_note_of_2000_characters_and_a_trailing_newline_is_kept(aws, places):
+    # The length is counted after the surrounding blanks are dropped (Backend #16).
+    assert put_note(note_body(text="あ" * 2000 + "\n"))["statusCode"] == 200
+    assert store.get_note(USER, RIDE, NOTE)["text"] == "あ" * 2000
+
+
+def test_a_note_of_a_deleted_ride_or_note_is_refused_without_looking_up_its_place(aws, places):
+    # An old send arriving after a deletion costs no ReverseGeocode call (Backend #17).
+    store.mark_deleted(USER, "note", NOTE, "2026-10-21T02:00:00.000Z", ride_id=RIDE)
+    assert put_note(note_body())["statusCode"] == 410
+    other = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
+    ride2 = "6d0b2a1f-3c4e-4f5a-9b7c-8d9e0f1a2b3c"
+    store.mark_deleted(USER, "ride", ride2, "2026-10-21T02:00:00.000Z")
+    assert put_note(note_body(), note_id=other, ride_id=ride2)["statusCode"] == 410
+    assert places == []
+
+
+def test_an_edited_note_keeps_its_first_heading(aws, places):
+    # The heading is settled on the first PUT, like the place (slice 3 spec §6.2, Backend #17).
+    put_note(note_body())
+    west = {"latitude": 35.6812, "longitude": 139.7664, "at": "2026-10-21T00:59:50.000Z"}
+    result = put_note(note_body(text="直した", headingSample=west, updatedAt="2026-10-21T01:10:00.000Z"))
+    assert answer(result)["applied"] is True and answer(result)["headingDegrees"] == 0.0
+    assert store.get_note(USER, RIDE, NOTE)["headingDegrees"] == 0.0
+
+
+def test_a_note_first_sent_without_a_heading_gets_one_later(aws, places):
+    put_note(note_body(headingSample=None))
+    result = put_note(note_body(updatedAt="2026-10-21T01:10:00.000Z"))
+    assert answer(result)["headingDegrees"] == 0.0
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_ask_edit.py tests/test_notes.py 2>&1 | tail -1`
Expected: `4 failed, 30 passed`（2000字＋改行が 400・跡があっても住所を引く・直した版で方位が変わる）。`test_a_note_first_sent_without_a_heading_gets_one_later` は、方位が無かったときに求め直すことを守るテストで、今の作りで通る

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/handlers/rides.py b/src/handlers/rides.py
index 19248cf..b847d48 100644
--- a/src/handlers/rides.py
+++ b/src/handlers/rides.py
@@ -55,11 +55,17 @@ def _route(event: dict, user: str, ride_id: str) -> dict:
 def _note(event: dict, user: str, ride_id: str) -> dict:
     note_id = rides.path_id(event, "noteId")
     note = notes.parse_note(event)
+    # A send arriving after a deletion is refused before the place is looked up (Backend #17).
+    if store.has_deletion_mark(user, [("note", note_id), ("ride", ride_id)]):
+        raise store.Deleted()
     stored = store.get_note(user, ride_id, note_id)
     if stored is not None and stored["updatedAt"] >= note.updated_at:
         applied, kept = False, stored
     else:
-        heading = heading_degrees(note.location, note.heading_sample, parse_iso(note.at))
+        heading = (stored or {}).get("headingDegrees")
+        if heading is None:
+            # Settled on the first PUT that has one, like the place (slice 3 spec §6.2, Backend #17).
+            heading = heading_degrees(note.location, note.heading_sample, parse_iso(note.at))
         kept = {
             "at": note.at,
             "location": note.location,
diff --git a/src/lib/notes.py b/src/lib/notes.py
index f446ffe..a6b4f60 100644
--- a/src/lib/notes.py
+++ b/src/lib/notes.py
@@ -28,7 +28,9 @@ def parse_note(event: dict) -> NoteInput:
         if location is None:
             raise BadRequest("location must be a position or null")
     text = data.get("text")
-    if not isinstance(text, str) or not text.strip() or len(text) > NOTE_TEXT_MAX:
+    # Code points, counted after the surrounding blanks are dropped (Backend #16).
+    text = text.strip() if isinstance(text, str) else None
+    if not text or len(text) > NOTE_TEXT_MAX:
         raise BadRequest(f"text must be 1-{NOTE_TEXT_MAX} characters")
-    return NoteInput(utc_time(data.get("at"), "at"), location, heading_sample(data.get("headingSample")), text.strip(),
+    return NoteInput(utc_time(data.get("at"), "at"), location, heading_sample(data.get("headingSample")), text,
                      utc_time(data.get("updatedAt"), "updatedAt"))
diff --git a/src/lib/rides.py b/src/lib/rides.py
index 44a7e93..e86e250 100644
--- a/src/lib/rides.py
+++ b/src/lib/rides.py
@@ -42,10 +42,11 @@ def utc_time(value: Any, field: str) -> str:
 
 
 def memo_text(value: Any) -> Optional[str]:
-    """A memo of up to MEMO_MAX characters; null or blank is no memo (US-D-04.003)."""
+    """A memo of up to MEMO_MAX characters (code points, counted after the surrounding blanks are dropped); null or
+    blank is no memo (US-D-04.003, Backend #16)."""
     if value is None:
         return None
-    if not isinstance(value, str) or len(value) > MEMO_MAX:
+    if not isinstance(value, str) or len(value.strip()) > MEMO_MAX:
         raise BadRequest(f"memo must be up to {MEMO_MAX} characters or null")
     return value.strip() or None
 
diff --git a/src/lib/store.py b/src/lib/store.py
index ccd620f..10cec17 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -59,6 +59,13 @@ def deleted_key(user: str, kind: str, record_id: str) -> dict:
     return {"pk": f"USER#{user}", "sk": f"DELETED#{kind.upper()}#{record_id}"}
 
 
+def has_deletion_mark(user: str, marks: list) -> bool:
+    """Whether any of the (kind, id) marks exists, read consistently. Used before costly work on a write that would be
+    refused anyway; the write itself still checks the marks in its transaction."""
+    table = clients.table()
+    return any(table.get_item(Key=deleted_key(user, kind, record_id), ConsistentRead=True).get("Item") for kind, record_id in marks)
+
+
 def _retrying_conflicts(write: Callable[[], Any]) -> Any:
     """Runs write, trying again twice (after 50 and 100 ms) while a transaction on the same item is in progress."""
     for attempt in range(_CONFLICT_TRIES):
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `231 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/rides.py src/lib/notes.py src/lib/store.py src/handlers/rides.py tests/test_ask_edit.py tests/test_notes.py
git commit -m "fix: count memo length after trimming, and refuse a deleted note before looking up its place while keeping its first heading (#16, #17)"
```

---

### Task 4: 質問できなかった地点の受け口（`PUT /asks/{askId}/offline`）

**Files:**
- Create: `src/lib/offline.py`
- Modify: `src/lib/store.py`・`src/handlers/ask_edit.py`
- Test: `tests/test_offline.py`（新規）

**Interfaces:**
- Consumes: `store.has_deletion_mark`（Task 3）・`store.get_ask(..., consistent=True)`（Task 2）・`store._write_unless_deleted`・`address.describe_location`・`geo.heading_degrees`
- Produces:
  - `offline.OfflineAskInput(asked_at: str, location: Optional[dict], heading_sample: Optional[dict], ride_id: str, updated_at: str)`・`offline.parse_offline_ask(event: dict) -> OfflineAskInput`
  - `store.put_offline_ask(user: str, ask_id: str, fields: dict) -> bool`（`Update` で書く。無いか、`offline` で古いときだけ書く。`fields` には `rideId` と `updatedAt` が要る。質問か走行に跡があれば `Deleted`）
  - `handlers.ask_edit.handler` は、`event["resource"]` が `/offline` で終わるとき `_offline` へ。応答は `200 {askId, applied, address, headingDegrees}`・`409 {"error": "conflict"}`・410・400

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_offline.py b/tests/test_offline.py
new file mode 100644
index 0000000..85c32e0
--- /dev/null
+++ b/tests/test_offline.py
@@ -0,0 +1,141 @@
+"""Tests for PUT /asks/{askId}/offline: an ask that never reached the Backend (moto, the address lookup stubbed)."""
+import json
+
+import pytest
+
+from handlers import ask_edit, rides
+from lib import store
+
+USER = "rider01"
+ASK = "11111111-1111-4111-8111-111111111111"
+RIDE = "5c9a1f0e-2b3d-4e5f-8a6b-7c8d9e0f1a2b"
+HERE = {"latitude": 35.6812, "longitude": 139.7671}
+# About 60 m south of HERE, 10 s before the ask: the rider was heading north.
+SOUTH = {"latitude": 35.68066, "longitude": 139.7671, "at": "2026-10-22T00:59:50.000Z"}
+T1, T2 = "2026-10-22T01:00:00.000Z", "2026-10-22T01:10:00.000Z"
+
+
+@pytest.fixture
+def places(monkeypatch):
+    calls = []
+
+    def describe(lat, lon):
+        calls.append((lat, lon))
+        return "神奈川県足柄下郡箱根町仙石原"
+
+    monkeypatch.setattr(ask_edit.address, "describe_location", describe)
+    return calls
+
+
+def offline_body(**changes):
+    return {"askedAt": T1, "location": HERE, "headingSample": SOUTH, "rideId": RIDE, "updatedAt": T1, **changes}
+
+
+def put_offline(body, ask_id=ASK, user=USER):
+    event = {"httpMethod": "PUT", "resource": "/asks/{askId}/offline", "headers": {"x-user-name": user},
+             "pathParameters": {"askId": ask_id}, "body": json.dumps(body)}
+    return ask_edit.handler(event, None)
+
+
+def answer(result):
+    return json.loads(result["body"])
+
+
+def test_an_unreached_ask_is_kept_with_its_place_and_heading(aws, places):
+    result = put_offline(offline_body())
+    assert result["statusCode"] == 200
+    assert answer(result) == {"askId": ASK, "applied": True, "address": "神奈川県足柄下郡箱根町仙石原", "headingDegrees": 0.0}
+    item = store.get_ask(USER, ASK)
+    assert item["status"] == "offline" and item["receivedAt"] == T1 and item["rideId"] == RIDE
+    assert item["location"] == HERE and item["updatedAt"] == T1 and item["address"] == "神奈川県足柄下郡箱根町仙石原"
+    assert "headingSample" not in item and "conversationId" not in item and "question" not in item
+
+
+def test_sending_the_same_version_again_changes_nothing(aws, places):
+    put_offline(offline_body())
+    again = put_offline(offline_body())
+    assert again["statusCode"] == 200 and answer(again)["applied"] is False
+    assert answer(again)["address"] == "神奈川県足柄下郡箱根町仙石原" and len(places) == 1
+
+
+def test_an_older_version_is_ignored_and_answers_with_the_stored_place(aws, places):
+    put_offline(offline_body(updatedAt=T2))
+    result = put_offline(offline_body(updatedAt=T1))
+    assert answer(result) == {"askId": ASK, "applied": False, "address": "神奈川県足柄下郡箱根町仙石原", "headingDegrees": 0.0}
+
+
+def test_a_newer_version_keeps_the_memo_place_and_heading(aws, places):
+    # The memo is written on its own path; sending the unreached ask again must not drop it.
+    put_offline(offline_body())
+    memo = {"httpMethod": "PUT", "headers": {"x-user-name": USER}, "pathParameters": {"askId": ASK},
+            "body": json.dumps({"memo": "何の山か聞きたかった", "updatedAt": T1})}
+    assert ask_edit.handler(memo, None)["statusCode"] == 200
+    west = {"latitude": 35.6812, "longitude": 139.7664, "at": "2026-10-22T00:59:50.000Z"}
+    result = put_offline(offline_body(headingSample=west, updatedAt=T2))
+    assert answer(result)["applied"] is True and answer(result)["headingDegrees"] == 0.0
+    item = store.get_ask(USER, ASK)
+    assert item["memo"] == "何の山か聞きたかった" and item["updatedAt"] == T2 and len(places) == 1
+
+
+def test_a_place_that_could_not_be_found_is_looked_up_on_the_next_put(aws, monkeypatch):
+    found = iter([None, "東京都千代田区丸の内"])
+    monkeypatch.setattr(ask_edit.address, "describe_location", lambda lat, lon: next(found))
+    assert answer(put_offline(offline_body()))["address"] is None
+    assert answer(put_offline(offline_body(updatedAt=T2)))["address"] == "東京都千代田区丸の内"
+
+
+def test_an_unreached_ask_without_a_position_has_no_place_or_heading(aws, places):
+    result = put_offline(offline_body(location=None, headingSample=None))
+    assert answer(result) == {"askId": ASK, "applied": True, "address": None, "headingDegrees": None}
+    assert places == [] and "location" not in store.get_ask(USER, ASK)
+
+
+def test_an_unreached_ask_that_was_deleted_or_whose_ride_was_deleted_is_410(aws, places):
+    store.mark_deleted(USER, "ask", ASK, T2, ride_id=RIDE)
+    assert put_offline(offline_body())["statusCode"] == 410
+    other = "22222222-2222-4222-8222-222222222222"
+    ride2 = "6d0b2a1f-3c4e-4f5a-9b7c-8d9e0f1a2b3c"
+    store.mark_deleted(USER, "ride", ride2, T2)
+    result = put_offline(offline_body(rideId=ride2), ask_id=other)
+    assert result["statusCode"] == 410 and answer(result) == {"error": "deleted"}
+    assert places == [] and [i["sk"] for i in aws.table.scan()["Items"] if i["sk"].startswith("ASK#")] == []
+
+
+def test_the_id_of_an_ask_the_backend_took_in_is_409_and_left_alone(aws, places):
+    store.create_ask({**store.ask_key(USER, ASK), "askId": ASK, "status": "completed", "answer": "A", "rideId": RIDE})
+    result = put_offline(offline_body())
+    assert result["statusCode"] == 409 and answer(result) == {"error": "conflict"}
+    item = store.get_ask(USER, ASK)
+    assert item["status"] == "completed" and item["answer"] == "A" and places == []
+
+
+def test_unreached_asks_are_kept_apart_by_user(aws, places):
+    put_offline(offline_body())
+    assert store.get_ask("someone", ASK) is None
+
+
+def test_deleting_the_ride_removes_its_unreached_ask_and_marks_it(aws, places):
+    put_offline(offline_body())
+    event = {"httpMethod": "DELETE", "headers": {"x-user-name": USER}, "pathParameters": {"rideId": RIDE}}
+    assert rides.handler(event, None)["statusCode"] == 204
+    assert store.get_ask(USER, ASK) is None
+    assert aws.table.get_item(Key=store.deleted_key(USER, "ask", ASK))["Item"]["rideId"] == RIDE
+
+
+@pytest.mark.parametrize("changes", [
+    {"askedAt": "2026-10-22T01:00:00"}, {"askedAt": None}, {"updatedAt": None},
+    {"rideId": None}, {"rideId": "ride-1"}, {"location": {"latitude": 91, "longitude": 0}}, {"location": "here"},
+])
+def test_a_bad_unreached_ask_is_400_and_writes_nothing(aws, places, changes):
+    result = put_offline(offline_body(**changes))
+    assert result["statusCode"] == 400 and answer(result)["error"] == "bad_request"
+    assert aws.table.scan()["Items"] == []
+
+
+def test_a_bad_ask_id_is_400(aws, places):
+    assert put_offline(offline_body(), ask_id="ask-1")["statusCode"] == 400
+
+
+def test_a_broken_heading_sample_only_drops_the_heading(aws, places):
+    result = put_offline(offline_body(headingSample={"latitude": "x"}))
+    assert result["statusCode"] == 200 and answer(result)["headingDegrees"] is None
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_offline.py 2>&1 | tail -1`
Expected: `1 failed, 18 errors`（`ask_edit.address` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/handlers/ask_edit.py b/src/handlers/ask_edit.py
index 26f794b..3493234 100644
--- a/src/handlers/ask_edit.py
+++ b/src/handlers/ask_edit.py
@@ -1,8 +1,10 @@
-"""PUT /asks/{askId}/memo and DELETE /asks/{askId}: the app's changes to an ask it keeps (slice 3 spec §6.2)."""
+"""PUT /asks/{askId}/memo and DELETE /asks/{askId}: the app's changes to an ask it keeps (slice 3 spec §6.2).
+PUT /asks/{askId}/offline: an ask that never reached the Backend, kept by the app (slice 4 spec §4.4)."""
 from __future__ import annotations
 
-from handlers.common import deleted, iso, log, no_content, response, utc_now
-from lib import rides, store
+from handlers.common import deleted, iso, log, no_content, parse_iso, response, utc_now
+from lib import address, offline, rides, store
+from lib.geo import heading_degrees
 from lib.request import BadRequest, user_name
 
 
@@ -14,6 +16,8 @@ def handler(event, context):
             store.delete_ask(user, ask_id, iso(utc_now()))
             log({"event": "ask_deleted", "askId": ask_id})
             return no_content()
+        if (event.get("resource") or "").endswith("/offline"):
+            return _offline(event, user, ask_id)
         return _memo(event, user, ask_id)
     except BadRequest as error:
         return response(400, {"error": "bad_request", "message": str(error)})
@@ -28,3 +32,47 @@ def _memo(event: dict, user: str, ask_id: str) -> dict:
         return response(404, {"error": "not_found"})
     log({"event": "ask_memo_saved", "askId": ask_id, "applied": applied, "hasMemo": memo is not None})
     return response(200, {"askId": ask_id, "applied": applied})
+
+
+def _conflict() -> dict:
+    """409: the id is an ask the Backend took in; an unreached ask never overwrites it."""
+    return response(409, {"error": "conflict"})
+
+
+def _offline(event: dict, user: str, ask_id: str) -> dict:
+    unreached = offline.parse_offline_ask(event)
+    # A send arriving after a deletion is refused before the place is looked up (as for point memos, Backend #17).
+    if store.has_deletion_mark(user, [("ask", ask_id), ("ride", unreached.ride_id)]):
+        raise store.Deleted()
+    stored = store.get_ask(user, ask_id, consistent=True)
+    if stored is not None and stored.get("status") != "offline":
+        return _conflict()
+    if stored is not None and stored["updatedAt"] >= unreached.updated_at:
+        applied, kept = False, stored
+    else:
+        heading = (stored or {}).get("headingDegrees")
+        if heading is None:
+            heading = heading_degrees(unreached.location, unreached.heading_sample, parse_iso(unreached.asked_at))
+        location = unreached.location
+        kept = {
+            "userName": user,
+            "rideId": unreached.ride_id,
+            # Named as for the asks the Backend takes in, so that every ask reads back alike.
+            "receivedAt": unreached.asked_at,
+            "location": location,
+            "updatedAt": unreached.updated_at,
+            # Settled on the first PUT, like a point memo's; a failed lookup is tried again.
+            "address": (stored or {}).get("address") or (
+                address.describe_location(location["latitude"], location["longitude"]) if location else None),
+            "headingDegrees": round(heading, 1) if heading is not None else None,
+            "savedAt": iso(utc_now()),
+        }
+        applied = store.put_offline_ask(user, ask_id, kept)
+        if not applied:
+            kept = store.get_ask(user, ask_id, consistent=True) or kept
+            if kept.get("status") != "offline":
+                return _conflict()
+    log({"event": "offline_ask_saved", "askId": ask_id, "rideId": unreached.ride_id, "applied": applied,
+         "hasPlace": kept.get("address") is not None})
+    return response(200, {"askId": ask_id, "applied": applied, "address": kept.get("address"),
+                          "headingDegrees": kept.get("headingDegrees")})
diff --git a/src/lib/offline.py b/src/lib/offline.py
new file mode 100644
index 0000000..c5975f2
--- /dev/null
+++ b/src/lib/offline.py
@@ -0,0 +1,34 @@
+"""Validation of an unreached ask sent by the Android app: one that never reached the Backend (slice 4 spec §4.4,
+US-C-09)."""
+from __future__ import annotations
+
+from dataclasses import dataclass
+from typing import Optional
+
+from lib.request import UUID_RE, BadRequest, body_json, heading_sample, position
+from lib.rides import utc_time
+
+
+@dataclass(frozen=True)
+class OfflineAskInput:
+    asked_at: str
+    location: Optional[dict]
+    heading_sample: Optional[dict]
+    ride_id: str
+    updated_at: str
+
+
+def parse_offline_ask(event: dict) -> OfflineAskInput:
+    data = body_json(event)
+    location = None
+    if data.get("location") is not None:
+        # The app keeps the ask from its own fix, so a broken position is its mistake (as for a point memo).
+        location = position(data.get("location"))
+        if location is None:
+            raise BadRequest("location must be a position or null")
+    ride_id = data.get("rideId")
+    # Asks start only while a ride is recording (adr/0008), so an unreached ask always has its ride.
+    if not isinstance(ride_id, str) or not UUID_RE.match(ride_id):
+        raise BadRequest("rideId must be a lowercase UUID")
+    return OfflineAskInput(utc_time(data.get("askedAt"), "askedAt"), location, heading_sample(data.get("headingSample")),
+                           ride_id, utc_time(data.get("updatedAt"), "updatedAt"))
diff --git a/src/lib/store.py b/src/lib/store.py
index 10cec17..1d3ff1d 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -202,6 +202,24 @@ def put_ask_memo(user: str, ask_id: str, memo: Optional[str], updated_at: str) -
     return _write_unless_deleted(update, [deleted_key(user, "ask", ask_id)])
 
 
+def put_offline_ask(user: str, ask_id: str, fields: dict) -> bool:
+    """Sets an unreached ask's fields unless a newer version is stored, keeping its memo (written on its own path).
+    False when it was not newer, or when the id belongs to an ask the Backend took in. Raises Deleted when the ask or
+    its ride has been deleted (slice 4 spec §4.4)."""
+    values = _to_item({"askId": ask_id, "status": "offline", **fields})
+    names = {f"#k{i}": key for i, key in enumerate(values)}
+    update = {"Update": {
+        "TableName": clients.table().name,
+        "Key": ask_key(user, ask_id),
+        "UpdateExpression": "SET " + ", ".join(f"#k{i} = :v{i}" for i in range(len(values))),
+        "ConditionExpression": "attribute_not_exists(pk) OR (#s = :offline AND #u < :u)",
+        "ExpressionAttributeNames": {**names, "#s": "status", "#u": "updatedAt"},
+        "ExpressionAttributeValues": {**{f":v{i}": value for i, value in enumerate(values.values())},
+                                      ":offline": "offline", ":u": fields["updatedAt"]},
+    }}
+    return _write_unless_deleted(update, [deleted_key(user, "ask", ask_id), deleted_key(user, "ride", fields["rideId"])])
+
+
 def get_ask(user: str, ask_id: str, consistent: bool = False) -> Optional[dict]:
     item = clients.table().get_item(Key=ask_key(user, ask_id), ConsistentRead=consistent).get("Item")
     return _from_item(item) if item else None
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `250 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/offline.py src/lib/store.py src/handlers/ask_edit.py tests/test_offline.py
git commit -m "feat: keep an ask that never reached the Backend, with its place and heading"
```

---

### Task 5: 記録の読み出し（`GET /records`）

**Files:**
- Create: `src/lib/records.py`・`src/handlers/records.py`
- Modify: `src/lib/store.py`
- Test: `tests/test_records.py`（新規）

**Interfaces:**
- Consumes: `store._from_item`・`request.user_name`・`request.BadRequest`
- Produces:
  - `store.query_records(user: str, after: Optional[str], limit: Optional[int] = None) -> tuple`（`(items, last_sort_key)`。最後のページなら `last_sort_key` は None）
  - `records.encode_cursor(sort_key: str) -> str`・`records.decode_cursor(text: Optional[str]) -> Optional[str]`（読めなければ `BadRequest`）・`records.view(item: dict) -> Optional[dict]`（返さない記録は None）・`records._ASK_STATUS`（Task 6 のテストが読む）
  - `handlers.records.handler`・`handlers.records.PAGE_LIMIT`（テストで小さくする）。応答は `200 {items, cursor}`・400

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_records.py b/tests/test_records.py
new file mode 100644
index 0000000..9761a97
--- /dev/null
+++ b/tests/test_records.py
@@ -0,0 +1,161 @@
+"""Tests for GET /records: a user's records read back page by page (moto)."""
+import base64
+import json
+
+import pytest
+
+from handlers import records
+from lib import store
+
+USER = "rider01"
+RIDE = "5c9a1f0e-2b3d-4e5f-8a6b-7c8d9e0f1a2b"
+NOTE = "9d8c7b6a-5f4e-4d3c-8b2a-1f0e9d8c7b6a"
+ASK = "11111111-1111-4111-8111-111111111111"
+OFFLINE = "22222222-2222-4222-8222-222222222222"
+GONE = "33333333-3333-4333-8333-333333333333"
+CID = "44444444-4444-4444-8444-444444444444"
+HERE = {"latitude": 35.6812, "longitude": 139.7671}
+T0, T1, T2 = "2026-10-22T00:00:00.000Z", "2026-10-22T01:00:00.000Z", "2026-10-22T01:00:05.000Z"
+
+
+def read(cursor=None, user=USER):
+    event = {"httpMethod": "GET", "headers": {"x-user-name": user},
+             "queryStringParameters": None if cursor is None else {"cursor": cursor}}
+    return records.handler(event, None)
+
+
+def page(cursor=None, user=USER):
+    result = read(cursor, user)
+    assert result["statusCode"] == 200
+    return json.loads(result["body"])
+
+
+def read_all(user=USER):
+    items, cursor = [], None
+    while True:
+        body = page(cursor, user)
+        items += body["items"]
+        cursor = body["cursor"]
+        if cursor is None:
+            return items
+
+
+def put(item):
+    store.create_ask(item)  # a plain put of any record
+
+
+def everything(user=USER):
+    pk = f"USER#{user}"
+    put({"pk": pk, "sk": f"RIDE#{RIDE}", "rideId": RIDE, "name": "箱根", "status": "ended",
+         "segments": [{"startedAt": T0, "endedAt": T1}], "autoEnded": False, "updatedAt": T1, "memo": "また行く",
+         "savedAt": T1})
+    for seq in (0, 1):
+        put({"pk": pk, "sk": f"RIDE#{RIDE}#ROUTE#{seq:05d}", "rideId": RIDE, "seq": seq, "savedAt": T1,
+             "points": [{"t": T0, "lat": 35.0 + seq, "lon": 139.0, "accuracy": 5.0, "segment": 0}]})
+    put({"pk": pk, "sk": f"RIDE#{RIDE}#NOTE#{NOTE}", "noteId": NOTE, "rideId": RIDE, "at": T0, "location": HERE,
+         "text": "ここ", "updatedAt": T0, "address": "東京都千代田区丸の内", "headingDegrees": 0.0, "savedAt": T0})
+    put({"pk": pk, "sk": f"ASK#{ASK}", "askId": ASK, "userName": user, "conversationId": CID,
+         "conversationStartedAt": T1, "status": "completed", "receivedAt": T1, "inputType": "audio",
+         "location": HERE, "headingSample": {**HERE, "at": T0}, "volumeDb": 6, "rideId": RIDE, "transcript": "右手の山は？",
+         "answer": "愛鷹山です。", "address": "静岡県沼津市", "headingDegrees": 90.0, "answerAudioKey": f"answers/{ASK}.mp3",
+         "usage": {"inputTokens": 5}, "timings": {"receivedAt": T1, "agentDoneAt": T2, "synthesizedAt": T2},
+         "memo": "晴れていた", "memoUpdatedAt": T2})
+    put({"pk": pk, "sk": f"ASK#{OFFLINE}", "askId": OFFLINE, "userName": user, "status": "offline", "receivedAt": T0,
+         "location": HERE, "rideId": RIDE, "updatedAt": T0, "address": "東京都千代田区丸の内", "headingDegrees": None,
+         "savedAt": T0})
+    store.mark_deleted(user, "ask", GONE, T2, ride_id=RIDE)
+    put({"pk": pk, "sk": f"CONV#{CID}", "startedAt": T1, "expiresAt": 1})
+    put({"pk": pk, "sk": f"TRANSCRIPTION#{GONE}", "status": "done", "text": "声", "expiresAt": 1})
+
+
+def test_a_user_without_records_reads_one_empty_page(aws):
+    assert page() == {"items": [], "cursor": None}
+
+
+def test_every_kind_of_record_reads_back_in_the_shape_it_was_sent(aws):
+    everything()
+    assert read_all() == [
+        {"kind": "ask", "askId": ASK, "status": "completed", "askedAt": T1, "question": None, "transcript": "右手の山は？",
+         "answer": "愛鷹山です。", "error": None, "answeredAt": T2, "location": HERE, "address": "静岡県沼津市",
+         "headingDegrees": 90.0, "inputType": "audio", "conversationId": CID, "newConversation": True, "rideId": RIDE,
+         "memo": "晴れていた", "memoUpdatedAt": T2, "updatedAt": None},
+        {"kind": "ask", "askId": OFFLINE, "status": "offline", "askedAt": T0, "question": None, "transcript": None,
+         "answer": None, "error": None, "answeredAt": None, "location": HERE, "address": "東京都千代田区丸の内",
+         "headingDegrees": None, "inputType": None, "conversationId": None, "newConversation": False, "rideId": RIDE,
+         "memo": None, "memoUpdatedAt": None, "updatedAt": T0},
+        {"kind": "deleted", "target": "ask", "id": GONE, "rideId": RIDE, "deletedAt": T2},
+        {"kind": "ride", "rideId": RIDE, "name": "箱根", "status": "ended", "segments": [{"startedAt": T0, "endedAt": T1}],
+         "autoEnded": False, "updatedAt": T1, "memo": "また行く"},
+        {"kind": "note", "rideId": RIDE, "noteId": NOTE, "at": T0, "location": HERE, "text": "ここ", "updatedAt": T0,
+         "address": "東京都千代田区丸の内", "headingDegrees": 0.0},
+        {"kind": "route", "rideId": RIDE, "seq": 0, "points": [{"t": T0, "lat": 35.0, "lon": 139.0, "accuracy": 5.0, "segment": 0}]},
+        {"kind": "route", "rideId": RIDE, "seq": 1, "points": [{"t": T0, "lat": 36.0, "lon": 139.0, "accuracy": 5.0, "segment": 0}]},
+    ]
+
+
+@pytest.mark.parametrize("stored, status, answered_at", [
+    ({"status": "pending"}, "processing", None),
+    ({"status": "processing"}, "processing", None),
+    ({"status": "failed", "error": "agent_failed"}, "failed", None),
+    ({"status": "failed", "error": "tts_failed", "answer": "文だけ"}, "failed", T2),
+])
+def test_an_ask_reads_back_with_the_status_the_app_polls_for(aws, stored, status, answered_at):
+    put({"pk": f"USER#{USER}", "sk": f"ASK#{ASK}", "askId": ASK, "conversationId": CID, "conversationStartedAt": T0,
+         "receivedAt": T1, "rideId": RIDE, "timings": {"receivedAt": T1, "agentDoneAt": T2}, **stored})
+    (item,) = read_all()
+    assert item["status"] == status and item["answeredAt"] == answered_at and item["newConversation"] is False
+
+
+def test_small_pages_read_back_everything_once_in_order(aws, monkeypatch):
+    everything()
+    whole = read_all()
+    monkeypatch.setattr(records, "PAGE_LIMIT", 2)
+    pages = []
+    cursor = None
+    while True:
+        body = page(cursor)
+        pages.append(body["items"])
+        cursor = body["cursor"]
+        if cursor is None:
+            break
+    assert len(pages) > 3 and [item for items in pages for item in items] == whole
+
+
+def test_records_are_kept_apart_by_user(aws):
+    everything(user="someone")
+    assert read_all() == []
+
+
+def test_a_cursor_never_reads_another_users_records(aws):
+    # The partition always comes from x-user-name; a cursor that names another user's is not followed there.
+    everything(user="someone")
+    forged = base64.urlsafe_b64encode(json.dumps({"pk": "USER#someone", "sk": "A"}).encode()).decode().rstrip("=")
+    assert page(forged) == {"items": [], "cursor": None}
+
+
+@pytest.mark.parametrize("cursor", ["", "!!!", base64.urlsafe_b64encode(b"[1]").decode(),
+                                    base64.urlsafe_b64encode(b'{"sk": ""}').decode()])
+def test_a_bad_cursor_is_400(aws, cursor):
+    result = read(cursor)
+    assert result["statusCode"] == 400 and json.loads(result["body"])["error"] == "bad_request"
+
+
+def test_a_bad_user_is_400(aws):
+    assert read(user="BAD")["statusCode"] == 400
+
+
+def test_records_are_read_consistently(aws, monkeypatch):
+    # A record sent just before taking over must be read back; moto is always consistent, so check the request.
+    from lib import clients
+    table = clients.table()
+    queries = []
+    query = table.query
+
+    def spy(**params):
+        queries.append(params)
+        return query(**params)
+
+    monkeypatch.setattr(table, "query", spy)
+    everything()
+    read_all()
+    assert queries and all(q.get("ConsistentRead") is True for q in queries)
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_records.py 2>&1 | tail -1`
Expected: `1 error`（`handlers.records` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/handlers/records.py b/src/handlers/records.py
new file mode 100644
index 0000000..b0a3a49
--- /dev/null
+++ b/src/handlers/records.py
@@ -0,0 +1,24 @@
+"""GET /records: a user's records, one page at a time, for taking over on another device (slice 4 spec §6.2,
+adr/0010)."""
+from __future__ import annotations
+
+from typing import Optional
+
+from handlers.common import log, response
+from lib import records, store
+from lib.request import BadRequest, user_name
+
+# One DynamoDB query (at most 1 MB) per page; tests set a small limit to read many pages.
+PAGE_LIMIT: Optional[int] = None
+
+
+def handler(event, context):
+    try:
+        user = user_name(event)
+        after = records.decode_cursor((event.get("queryStringParameters") or {}).get("cursor"))
+    except BadRequest as error:
+        return response(400, {"error": "bad_request", "message": str(error)})
+    items, last = store.query_records(user, after, PAGE_LIMIT)
+    views = [view for view in map(records.view, items) if view is not None]
+    log({"event": "records_read", "items": len(views), "more": last is not None})
+    return response(200, {"items": views, "cursor": records.encode_cursor(last) if last is not None else None})
diff --git a/src/lib/records.py b/src/lib/records.py
new file mode 100644
index 0000000..c13d3b8
--- /dev/null
+++ b/src/lib/records.py
@@ -0,0 +1,83 @@
+"""A user's records as GET /records reads them back, for taking over on another device (slice 4 spec §6.2, adr/0010)."""
+from __future__ import annotations
+
+import base64
+import binascii
+import json
+from typing import Optional
+
+from lib.request import BadRequest
+
+# As GET /asks/{askId} answers, plus the unreached asks the app sent (slice 4 spec §4.4).
+_ASK_STATUS = {"pending": "processing", "processing": "processing", "completed": "completed", "failed": "failed",
+               "offline": "offline"}
+
+
+def encode_cursor(sort_key: str) -> str:
+    return base64.urlsafe_b64encode(json.dumps({"sk": sort_key}).encode("utf-8")).decode("ascii").rstrip("=")
+
+
+def decode_cursor(text: Optional[str]) -> Optional[str]:
+    """The sort key to continue after, or None for the first page. Only the sort key is taken from the cursor."""
+    if text is None:
+        return None
+    try:
+        data = json.loads(base64.urlsafe_b64decode(text.encode("ascii") + b"=" * (-len(text) % 4)))
+    except (ValueError, binascii.Error, UnicodeError):
+        raise BadRequest("cursor must be one that GET /records returned") from None
+    if not isinstance(data, dict) or not isinstance(data.get("sk"), str) or not data["sk"]:
+        raise BadRequest("cursor must be one that GET /records returned")
+    return data["sk"]
+
+
+def view(item: dict) -> Optional[dict]:
+    """The record as the app reads it back, or None for records it never sends or keeps (conversations,
+    transcriptions)."""
+    sort_key = item["sk"]
+    if sort_key.startswith("DELETED#"):
+        return {"kind": "deleted", "target": item["kind"], "id": item["id"], "rideId": item.get("rideId"),
+                "deletedAt": item["deletedAt"]}
+    if sort_key.startswith("ASK#"):
+        return _ask(item)
+    if not sort_key.startswith("RIDE#"):
+        return None
+    if "#ROUTE#" in sort_key:
+        return {"kind": "route", "rideId": item["rideId"], "seq": item["seq"], "points": item["points"]}
+    if "#NOTE#" in sort_key:
+        return {"kind": "note", "rideId": item["rideId"], "noteId": item["noteId"], "at": item["at"],
+                "location": item.get("location"), "text": item["text"], "updatedAt": item["updatedAt"],
+                "address": item.get("address"), "headingDegrees": item.get("headingDegrees")}
+    return {"kind": "ride", "rideId": item["rideId"], "name": item["name"], "status": item["status"],
+            "segments": item["segments"], "autoEnded": item["autoEnded"], "updatedAt": item["updatedAt"],
+            "memo": item.get("memo")}
+
+
+def _ask(item: dict) -> dict:
+    status = _ASK_STATUS.get(item.get("status"), "processing")
+    timings = item.get("timings") or {}
+    # An answer the rider could hear: completed, or text whose speech failed (read with the device's TTS).
+    answered = status == "completed" or (item.get("error") == "tts_failed" and bool(item.get("answer")))
+    conversation_id = item.get("conversationId")
+    return {
+        "kind": "ask",
+        "askId": item["askId"],
+        "status": status,
+        "askedAt": item.get("receivedAt"),
+        "question": item.get("question"),
+        "transcript": item.get("transcript"),
+        "answer": item.get("answer"),
+        "error": item.get("error"),
+        "answeredAt": (timings.get("synthesizedAt") or timings.get("agentDoneAt")) if answered else None,
+        "location": item.get("location"),
+        "address": item.get("address"),
+        "headingDegrees": item.get("headingDegrees"),
+        "inputType": item.get("inputType"),
+        "conversationId": conversation_id,
+        # The conversation breaks just before its first ask (US-C-03.004).
+        "newConversation": conversation_id is not None and item.get("conversationStartedAt") == item.get("receivedAt"),
+        "rideId": item.get("rideId"),
+        "memo": item.get("memo"),
+        "memoUpdatedAt": item.get("memoUpdatedAt"),
+        # Only an unreached ask carries the time the app changed it (slice 4 spec §6.1).
+        "updatedAt": item.get("updatedAt"),
+    }
diff --git a/src/lib/store.py b/src/lib/store.py
index 1d3ff1d..96684a3 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -321,6 +321,20 @@ def delete_ride(user: str, ride_id: str, deleted_at: str) -> dict:
     return {"notes": len(notes), "asks": len(asks), "chunks": sum("#ROUTE#" in k["sk"] for k in under)}
 
 
+def query_records(user: str, after: Optional[str], limit: Optional[int] = None) -> tuple:
+    """One page of the user's records in sort-key order (one query, at most 1 MB), read consistently, and the sort key
+    to continue after (None on the last page). The partition comes from the user alone (slice 4 spec §6.2)."""
+    params: dict = {"KeyConditionExpression": "pk = :p", "ExpressionAttributeValues": {":p": f"USER#{user}"},
+                    "ConsistentRead": True}
+    if after is not None:
+        params["ExclusiveStartKey"] = {"pk": f"USER#{user}", "sk": after}
+    if limit is not None:
+        params["Limit"] = limit
+    page = clients.table().query(**params)
+    last = page.get("LastEvaluatedKey")
+    return [_from_item(item) for item in page.get("Items", [])], (last["sk"] if last else None)
+
+
 def transcription_key(user: str, transcription_id: str) -> dict:
     return {"pk": f"USER#{user}", "sk": f"TRANSCRIPTION#{transcription_id}"}
 
EOF
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `265 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/records.py src/handlers/records.py src/lib/store.py tests/test_records.py
git commit -m "feat: read a user's records back page by page for taking over on another device"
```

---

### Task 6: API の正本と、経路・Lambda（`openapi.yaml`・`template.yaml`）

**Files:**
- Modify: `openapi.yaml`・`template.yaml`
- Test: `tests/test_openapi.py`

**Interfaces:**
- Consumes: `records.view`・`records._ASK_STATUS`（Task 5）
- Produces:
  - openapi: `/asks/{askId}/offline`（put）・`/records`（get）・`POST /asks` の 503・スキーマ `OfflineAskRequest`・`OfflineAskSaved`・`RecordsPage`・`RecordItem`（`kind` で分ける）・`RideRecord`・`RouteRecord`・`NoteRecord`・`AskRecord`・`DeletedRecord`。5xx の送り直しと、文字数の数え方の説明
  - template: `AskEditFunction` に経路 `PUT /asks/{askId}/offline`・`GEO_REGION`・`geo-places:ReverseGeocode`。`RecordsFunction`（`lambda-trv2-${Environment}-records`・`GET /records`・`DynamoDBReadPolicy`・512MB）

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_openapi.py b/tests/test_openapi.py
index 111ff3c..5c250d6 100644
--- a/tests/test_openapi.py
+++ b/tests/test_openapi.py
@@ -17,11 +17,13 @@ def test_routes():
         "/asks": {"post"},
         "/asks/{askId}": {"get", "delete"},
         "/asks/{askId}/memo": {"put"},
+        "/asks/{askId}/offline": {"put"},
         "/rides/{rideId}": {"put", "delete"},
         "/rides/{rideId}/route/{seq}": {"put"},
         "/rides/{rideId}/notes/{noteId}": {"put", "delete"},
         "/transcriptions": {"post"},
         "/transcriptions/{transcriptionId}": {"get"},
+        "/records": {"get"},
     }
 
 
@@ -49,3 +51,32 @@ def test_the_ride_limits_match_the_validation():
 def test_error_reasons_match_contract():
     reasons = SPEC["components"]["schemas"]["AskResult"]["properties"]["error"]["enum"]
     assert set(reasons) - {None} == {"no_speech", "transcribe_failed", "agent_failed", "tts_failed"}
+
+
+def _samples():
+    t = "2026-10-22T01:00:00.000Z"
+    return [
+        {"sk": "RIDE#r", "rideId": "r", "name": "n", "status": "ended", "segments": [], "autoEnded": False, "updatedAt": t},
+        {"sk": "RIDE#r#ROUTE#00000", "rideId": "r", "seq": 0, "points": []},
+        {"sk": "RIDE#r#NOTE#n", "rideId": "r", "noteId": "n", "at": t, "text": "x", "updatedAt": t},
+        {"sk": "ASK#a", "askId": "a", "status": "offline", "receivedAt": t, "rideId": "r", "updatedAt": t},
+        {"sk": "DELETED#RIDE#r", "kind": "ride", "id": "r", "deletedAt": t},
+    ]
+
+
+def test_the_records_schemas_name_exactly_what_the_handler_returns():
+    from lib import records
+    schemas = SPEC["components"]["schemas"]
+    by_kind = {records.view(item)["kind"]: records.view(item) for item in _samples()}
+    mapping = schemas["RecordItem"]["discriminator"]["mapping"]
+    assert set(mapping) == set(by_kind)
+    for kind, view in by_kind.items():
+        schema = schemas[mapping[kind].rsplit("/", 1)[1]]
+        assert set(schema["properties"]) == set(view) and set(schema["required"]) == set(view)
+        assert schema["properties"]["kind"]["enum"] == [kind]
+
+
+def test_the_ask_record_statuses_match_the_handler():
+    from lib import records
+    statuses = SPEC["components"]["schemas"]["AskRecord"]["properties"]["status"]["enum"]
+    assert set(statuses) == set(records._ASK_STATUS.values())
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_openapi.py 2>&1 | tail -1`
Expected: `3 failed, 5 passed`（経路とスキーマが無い）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/openapi.yaml b/openapi.yaml
index 251cd1f..127cbb1 100644
--- a/openapi.yaml
+++ b/openapi.yaml
@@ -5,6 +5,8 @@ info:
   description: >
     App ↔ Backend の約束の正本（親リポジトリ docs/07_units_contracts.md UC-4〜UC-7）。
     /health 以外は x-api-key（接続キー）と x-user-name（英小文字と数字の3〜20文字）が要る。
+    5xx（API Gateway・Lambda の一時的な失敗）は送り直してよい。PUT・DELETE は何度送っても同じ結果になる。
+    文字数の上限は、前後の空白を落としたあとの Unicode のコードポイントの数で数える。
 servers:
   - url: https://{apiId}.execute-api.ap-northeast-1.amazonaws.com/Prod
     variables:
@@ -52,6 +54,17 @@ paths:
           description: 接続キーが無効
         "429":
           description: 流量の制限
+        "503":
+          description: 受け付けたが処理に回せなかった。記録は残さない。App は通信の失敗と同じに扱う
+          content:
+            application/json:
+              schema:
+                type: object
+                required: [error]
+                properties:
+                  error:
+                    type: string
+                    enum: [unavailable]
   /asks/{askId}:
     get:
       summary: 質問の状態と回答
@@ -139,12 +152,79 @@ paths:
                     enum: [not_found]
         "410":
           $ref: "#/components/responses/Deleted"
+  /asks/{askId}/offline:
+    put:
+      summary: 質問できなかった地点を置く（Backend に届かなかった質問。最新の全体を送る）
+      description: >
+        Android が作った askId で、status が offline の質問として置く。updatedAt が保存済みのものより新しいときだけ書き、
+        古ければ何もせず 200（applied は false）で、保存済みの住所と方位を返す。会話のメモ（PUT /asks/{askId}/memo）は残す。
+        住所（町名まで）と方位は最初に受けたときに Backend が決め、あとの PUT では変えない（住所を確定できなかったときは次の PUT で求め直す）。
+        質問か走行に削除の跡があれば、書かずに 410。同じ askId で Backend が受け付けた質問があれば、書かずに 409。
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+        - $ref: "#/components/parameters/AskId"
+      requestBody:
+        required: true
+        content:
+          application/json:
+            schema:
+              $ref: "#/components/schemas/OfflineAskRequest"
+      responses:
+        "200":
+          description: 受け取った（書いたか、古いので何もしなかったか）
+          content:
+            application/json:
+              schema:
+                $ref: "#/components/schemas/OfflineAskSaved"
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
+        "409":
+          description: 同じ askId で Backend が受け付けた質問がある。書かなかった
+          content:
+            application/json:
+              schema:
+                type: object
+                required: [error]
+                properties:
+                  error:
+                    type: string
+                    enum: [conflict]
+        "410":
+          $ref: "#/components/responses/Deleted"
+  /records:
+    get:
+      summary: ユーザーの記録を、ページ送りで読む（引き継ぎのときに使う）
+      description: >
+        走行・ルートのかたまり・地点メモ・質問（質問できなかった地点を含む）・削除の跡を、記録の識別子の順に返す。
+        1ページは DynamoDB の1回の問い合わせ（最大1MB）で、items が空でも cursor があれば続きがある。
+        cursor が null なら最後のページ。強い一貫性で読む。
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+        - name: cursor
+          in: query
+          required: false
+          description: 前のページの応答の cursor。最初のページでは付けない
+          schema:
+            type: string
+      responses:
+        "200":
+          description: 1ページ
+          content:
+            application/json:
+              schema:
+                $ref: "#/components/schemas/RecordsPage"
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
   /rides/{rideId}:
     put:
       summary: 走行のメタ情報を置く（状態・名前・区間・メモが変わるたびに、最新の全体を送る）
       description: >
         updatedAt が保存済みのものより新しいときだけ上書きする。古ければ何もせず 200（applied は false）。
-        削除の跡がある走行は書かずに 410。読み出しは後のスライスで足す。
+        削除の跡がある走行は書かずに 410。読み出しは GET /records。
       parameters:
         - $ref: "#/components/parameters/UserName"
         - $ref: "#/components/parameters/RideId"
@@ -364,7 +444,7 @@ components:
       name: askId
       in: path
       required: true
-      description: Backend が質問を受け付けたときに返した UUID（小文字）
+      description: Backend が質問を受け付けたときに返した UUID（小文字）。質問できなかった地点は Android が作る UUID
       schema:
         type: string
         format: uuid
@@ -553,7 +633,7 @@ components:
           type: string
           maxLength: 2000
           nullable: true
-          description: 走行のメモ。null・省略・空白だけは「メモ無し」（保存済みのメモも消える）。前後の空白は落とす
+          description: 走行のメモ。null・省略・空白だけは「メモ無し」（保存済みのメモも消える）。前後の空白は落とし、そのあとのコードポイントで2000まで
     AskMemoRequest:
       type: object
       required: [memo, updatedAt]
@@ -562,7 +642,7 @@ components:
           type: string
           maxLength: 2000
           nullable: true
-          description: 会話のメモ。null・空白だけなら消す。前後の空白は落とす
+          description: 会話のメモ。null・空白だけなら消す。前後の空白は落とし、そのあとのコードポイントで2000まで
         updatedAt:
           type: string
           format: date-time
@@ -595,7 +675,7 @@ components:
           type: string
           minLength: 1
           maxLength: 2000
-          description: 本文。空白だけは 400。前後の空白は落とす
+          description: 本文。空白だけは 400。前後の空白は落とし、そのあとのコードポイントで2000まで
         updatedAt:
           type: string
           format: date-time
@@ -674,3 +754,264 @@ components:
                 type: integer
                 minimum: 0
                 description: 点を記録した区間の番号（segments の何番目か。0から）
+    OfflineAskRequest:
+      type: object
+      required: [askedAt, rideId, updatedAt]
+      properties:
+        askedAt:
+          type: string
+          format: date-time
+          description: 録音を終えた時刻（タイムゾーン付き）
+        location:
+          allOf:
+            - $ref: "#/components/schemas/Point"
+          nullable: true
+          description: 録音を終えたときの位置。まだ位置が無ければ null。不正な位置は 400
+        headingSample:
+          nullable: true
+          description: 方位の材料（質問と同じ）。askedAt より2分以上古いものは使わない。不正なものは無いものとして扱う
+          allOf:
+            - $ref: "#/components/schemas/Point"
+            - type: object
+              required: [at]
+              properties:
+                at:
+                  type: string
+                  format: date-time
+        rideId:
+          type: string
+          format: uuid
+          description: 記録中だった走行（小文字）
+        updatedAt:
+          type: string
+          format: date-time
+          description: Android が記録を変えた時刻（タイムゾーン付き。ミリ秒まで比べる）
+    OfflineAskSaved:
+      type: object
+      required: [askId, applied, address, headingDegrees]
+      properties:
+        askId:
+          type: string
+          format: uuid
+        applied:
+          type: boolean
+        address:
+          type: string
+          nullable: true
+          description: 地点の住所（町名まで）。位置が無いか、確定できなかったら null
+        headingDegrees:
+          type: number
+          nullable: true
+          description: 進行方位（北を0とする度）。方位なしなら null
+    RecordsPage:
+      type: object
+      required: [items, cursor]
+      properties:
+        items:
+          type: array
+          items:
+            $ref: "#/components/schemas/RecordItem"
+        cursor:
+          type: string
+          nullable: true
+          description: 続きを読むときに付ける。null なら最後のページ
+    RecordItem:
+      oneOf:
+        - $ref: "#/components/schemas/RideRecord"
+        - $ref: "#/components/schemas/RouteRecord"
+        - $ref: "#/components/schemas/NoteRecord"
+        - $ref: "#/components/schemas/AskRecord"
+        - $ref: "#/components/schemas/DeletedRecord"
+      discriminator:
+        propertyName: kind
+        mapping:
+          ride: "#/components/schemas/RideRecord"
+          route: "#/components/schemas/RouteRecord"
+          note: "#/components/schemas/NoteRecord"
+          ask: "#/components/schemas/AskRecord"
+          deleted: "#/components/schemas/DeletedRecord"
+    RideRecord:
+      type: object
+      description: PUT /rides/{rideId} で置いたもの
+      required: [kind, rideId, name, status, segments, autoEnded, updatedAt, memo]
+      properties:
+        kind:
+          type: string
+          enum: [ride]
+        rideId:
+          type: string
+          format: uuid
+        name:
+          type: string
+        status:
+          type: string
+          enum: [recording, paused, ended]
+        segments:
+          type: array
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
+        updatedAt:
+          type: string
+          format: date-time
+        memo:
+          type: string
+          nullable: true
+    RouteRecord:
+      type: object
+      description: PUT /rides/{rideId}/route/{seq} で置いたもの
+      required: [kind, rideId, seq, points]
+      properties:
+        kind:
+          type: string
+          enum: [route]
+        rideId:
+          type: string
+          format: uuid
+        seq:
+          type: integer
+        points:
+          $ref: "#/components/schemas/RouteChunk/properties/points"
+    NoteRecord:
+      type: object
+      description: PUT /rides/{rideId}/notes/{noteId} で置いたものと、Backend が決めた住所と方位
+      required: [kind, rideId, noteId, at, location, text, updatedAt, address, headingDegrees]
+      properties:
+        kind:
+          type: string
+          enum: [note]
+        rideId:
+          type: string
+          format: uuid
+        noteId:
+          type: string
+          format: uuid
+        at:
+          type: string
+          format: date-time
+        location:
+          allOf:
+            - $ref: "#/components/schemas/Point"
+          nullable: true
+        text:
+          type: string
+        updatedAt:
+          type: string
+          format: date-time
+        address:
+          type: string
+          nullable: true
+        headingDegrees:
+          type: number
+          nullable: true
+    AskRecord:
+      type: object
+      description: >
+        質問。Backend が受け付けたもの（status は GET /asks/{askId} と同じ）と、質問できなかった地点（status が offline）。
+      required: [kind, askId, status, askedAt, question, transcript, answer, error, answeredAt, location, address,
+                 headingDegrees, inputType, conversationId, newConversation, rideId, memo, memoUpdatedAt, updatedAt]
+      properties:
+        kind:
+          type: string
+          enum: [ask]
+        askId:
+          type: string
+          format: uuid
+        status:
+          type: string
+          enum: [processing, completed, failed, offline]
+        askedAt:
+          type: string
+          format: date-time
+          nullable: true
+          description: 受け付けた日時。質問できなかった地点は録音を終えた時刻
+        question:
+          type: string
+          nullable: true
+          description: 文字の質問の文
+        transcript:
+          type: string
+          nullable: true
+        answer:
+          type: string
+          nullable: true
+        error:
+          type: string
+          nullable: true
+          enum: [no_speech, transcribe_failed, agent_failed, tts_failed, null]
+        answeredAt:
+          type: string
+          format: date-time
+          nullable: true
+          description: 回答ができた時刻（聞ける回答があるときだけ）
+        location:
+          allOf:
+            - $ref: "#/components/schemas/Point"
+          nullable: true
+        address:
+          type: string
+          nullable: true
+        headingDegrees:
+          type: number
+          nullable: true
+        inputType:
+          type: string
+          nullable: true
+          enum: [audio, text, null]
+          description: 質問できなかった地点は null
+        conversationId:
+          type: string
+          format: uuid
+          nullable: true
+          description: 質問できなかった地点は null
+        newConversation:
+          type: boolean
+          description: 会話の最初の質問か（その直前で会話が区切れる）
+        rideId:
+          type: string
+          format: uuid
+          nullable: true
+        memo:
+          type: string
+          nullable: true
+        memoUpdatedAt:
+          type: string
+          format: date-time
+          nullable: true
+        updatedAt:
+          type: string
+          format: date-time
+          nullable: true
+          description: Android が変えた時刻（質問できなかった地点だけ）
+    DeletedRecord:
+      type: object
+      description: 削除の跡。target の記録は消えている（走行の跡なら、その下のルート・地点メモ・質問も）
+      required: [kind, target, id, rideId, deletedAt]
+      properties:
+        kind:
+          type: string
+          enum: [deleted]
+        target:
+          type: string
+          enum: [ask, ride, note]
+        id:
+          type: string
+          format: uuid
+        rideId:
+          type: string
+          format: uuid
+          nullable: true
+          description: 質問と地点メモの跡のとき、その走行（分かれば）
+        deletedAt:
+          type: string
+          format: date-time
diff --git a/template.yaml b/template.yaml
index 3174304..7542a39 100644
--- a/template.yaml
+++ b/template.yaml
@@ -1,6 +1,6 @@
 AWSTemplateFormatVersion: "2010-09-09"
 Transform: AWS::Serverless-2016-10-31
-Description: TouringProjectV2 backend - accept asks, process them through the agent, return answers, and keep rides, memos and point memos.
+Description: TouringProjectV2 backend - accept asks, process them through the agent, return answers, and keep rides, memos, point memos and unreached asks, reading them back for taking over.
 
 Parameters:
   Environment:
@@ -168,9 +168,17 @@ Resources:
     Properties:
       FunctionName: !Sub lambda-trv2-${Environment}-ask-edit
       Handler: handlers.ask_edit.handler
+      Environment:
+        Variables:
+          GEO_REGION: !Ref AWS::Region
       Policies:
         - DynamoDBCrudPolicy:
             TableName: !Ref RecordsTable
+        # An unreached ask gets its place on the first PUT, like a point memo (slice 4 spec §4.4).
+        - Statement:
+            - Effect: Allow
+              Action: geo-places:ReverseGeocode
+              Resource: "*"
       Events:
         Memo:
           Type: Api
@@ -184,6 +192,30 @@ Resources:
             RestApiId: !Ref RestApi
             Path: /asks/{askId}
             Method: delete
+        Offline:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /asks/{askId}/offline
+            Method: put
+
+  RecordsFunction:
+    Type: AWS::Serverless::Function
+    Properties:
+      FunctionName: !Sub lambda-trv2-${Environment}-records
+      Handler: handlers.records.handler
+      # A page is one query of up to 1 MB, turned into JSON.
+      MemorySize: 512
+      Policies:
+        - DynamoDBReadPolicy:
+            TableName: !Ref RecordsTable
+      Events:
+        Records:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /records
+            Method: get
 
   TranscriptionsFunction:
     Type: AWS::Serverless::Function
@@ -295,7 +327,8 @@ Resources:
           KeyType: RANGE
       PointInTimeRecoverySpecification:
         PointInTimeRecoveryEnabled: true
-      # Only transcriptions carry expiresAt; they are needed while the app polls (slice 3 spec §6.1).
+      # Transcriptions (needed while the app polls, slice 3 spec §6.1) and conversations (55 minutes at most, Backend #2)
+      # carry expiresAt.
       TimeToLiveSpecification:
         AttributeName: expiresAt
         Enabled: true
EOF
```

- [ ] **Step 4: 通ることと、テンプレートが正しいことを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1 && AWS_PROFILE=touring sam validate --lint 2>&1 | tail -1`
Expected: `267 passed` と `... is a valid SAM Template`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add openapi.yaml template.yaml tests/test_openapi.py
git commit -m "feat: describe and route the unreached-ask and records APIs, and give the ask-edit Lambda reverse geocoding"
```

---

### Task 7: 文書（Backend の README・親の 07・文書の写し・spec）

**Files:**
- Modify: `Backend/README.md`・`Backend/docs-parent/`（写し）・親の `docs/07_units_contracts.md`

- [ ] **Step 1: Backend の README を直す**

```bash
cd $BE && git apply <<'EOF'
diff --git a/README.md b/README.md
index 15be9d5..9e7addd 100644
--- a/README.md
+++ b/README.md
@@ -2,7 +2,7 @@
 
 TouringProjectV2 の API（API Gateway＋Lambda・Python・SAM・`ap-northeast-1`）。
 App から質問（PCM の音声か文字）と位置を受け付け、文字起こし・住所と方位の確定・Agent の呼び出し・読み上げ音声の生成を行い、結果を返す。
-走行・ルート・メモ・地点メモと、それらの削除を受け取り、ユーザー名ごとに置く。
+走行・ルート・メモ・地点メモ・質問できなかった地点と、それらの削除を受け取り、ユーザー名ごとに置く。引き継ぎのときは、ユーザーの記録をページ送りで返す。
 プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し。編集しない）。
 
 ## 構成
@@ -11,19 +11,21 @@ App から質問（PCM の音声か文字）と位置を受け付け、文字起
 |---|---|
 | `openapi.yaml` | App ↔ Backend の API 仕様（正本） |
 | `template.yaml`・`samconfig.toml` | SAM（スタック `stack-trv2-dev-backend`） |
-| `src/handlers/` | `health`・`ask`（`POST /asks`）・`result`（`GET /asks/{askId}`）・`ask_edit`（`PUT /asks/{askId}/memo`・`DELETE /asks/{askId}`）・`worker`（SQS）・`rides`（`/rides/{rideId}` の `PUT`・`DELETE`、`PUT /rides/{rideId}/route/{seq}`、`/rides/{rideId}/notes/{noteId}` の `PUT`・`DELETE`）・`transcriptions`（`POST /transcriptions`・`GET /transcriptions/{transcriptionId}`） |
-| `src/lib/` | 入力の検証（質問と音声は `request`・走行とメモは `rides`・地点メモは `notes`）・方位・プロンプト・住所・記録（削除の跡を含む）・会話の時間・Agent・音声合成・文字起こし |
+| `src/handlers/` | `health`・`ask`（`POST /asks`）・`result`（`GET /asks/{askId}`）・`ask_edit`（`PUT /asks/{askId}/memo`・`PUT /asks/{askId}/offline`・`DELETE /asks/{askId}`）・`worker`（SQS）・`rides`（`/rides/{rideId}` の `PUT`・`DELETE`、`PUT /rides/{rideId}/route/{seq}`、`/rides/{rideId}/notes/{noteId}` の `PUT`・`DELETE`）・`transcriptions`（`POST /transcriptions`・`GET /transcriptions/{transcriptionId}`）・`records`（`GET /records`） |
+| `src/lib/` | 入力の検証（質問と音声は `request`・走行とメモは `rides`・地点メモは `notes`・質問できなかった地点は `offline`）・方位・プロンプト・住所・記録（削除の跡を含む）・読み出す形（`records`）・会話の時間・Agent・音声合成・文字起こし |
 | `scripts/smoke.py` | デプロイ後の通しの確認 |
 
 ## 流れ
 
-1. `POST /asks` が入力を検証し、録音を S3（`audio/`・1日で消える）に置き、記録を `pending` で作り、SQS に積む。会話を区切る時刻を SSM `/trv2/dev/conversation-reset-minutes`（既定15・55以下）から求めて返す。
+1. `POST /asks` が入力を検証し、録音を S3（`audio/`・1日で消える）に置き、記録を `pending` で作り、SQS に積む。会話を区切る時刻を SSM `/trv2/dev/conversation-reset-minutes`（既定15・55以下）から求めて返す。SQS に積めなかったときは、記録と録音を消して 503 を返す（App は通信の失敗として扱う）。会話の記録（`CONV#`）は TTL（`expiresAt`）で1日後に消える。
 2. worker が受け持ちを獲得し（条件付き書き込み）、文字起こし（ストリーミング）→ 住所（Location Service）・方位・日時 → Agent（us-east-1・`runtimeSessionId` はユーザー名と会話の識別子から作る SHA-256）→ Polly（Kazuha・DRC と +6dB）の順に処理し、記録を `completed` か `failed` にする。
 3. App は `GET /asks/{askId}` をポーリングし、回答の文と音声の署名付き URL（10分有効）を受け取る。
-4. 走行: App は走行のメタ情報（走行のメモを含む）を `PUT /rides/{rideId}` で、ルートの点を300点までのかたまりにして `PUT /rides/{rideId}/route/{seq}` で置く。メタ情報は `updatedAt` が保存済みより新しいときだけ上書きする（古ければ `applied: false` の 200）。読み出しは後のスライス。
+4. 走行: App は走行のメタ情報（走行のメモを含む）を `PUT /rides/{rideId}` で、ルートの点を300点までのかたまりにして `PUT /rides/{rideId}/route/{seq}` で置く。メタ情報は `updatedAt` が保存済みより新しいときだけ上書きする（古ければ `applied: false` の 200）。
 5. メモと地点メモ: 会話のメモは `PUT /asks/{askId}/memo`、地点メモは `PUT /rides/{rideId}/notes/{noteId}` で置く。どちらも `updatedAt` が新しいときだけ書く。地点メモの住所と方位は、最初に受けたときに質問と同じ求め方で決めて返す。
 6. 削除: `DELETE` を受けると、先に削除の跡（`DELETED#<ASK|RIDE|NOTE>#<id>`・期限なし）を書いてから消す。走行を消すと、ルート・地点メモ・その走行の質問も消し、地点メモと質問にも跡を残す。跡のある記録（と、跡のある走行の下の記録）への `PUT` は、書き込みと跡の確かめを1つのトランザクションにして、書かずに 410 を返す。
-7. 地点メモの声: `POST /transcriptions` が録音を S3 に置いて SQS に積み、worker が文字起こしだけを行う（AI と読み上げは呼ばない）。App は `GET /transcriptions/{transcriptionId}` をポーリングする。記録は DynamoDB の TTL（`expiresAt`）で1日後に消える。
+7. 質問できなかった地点: App は、Backend に届かなかった質問の日時・位置・方位の材料を、自分で作った `askId` で `PUT /asks/{askId}/offline` に置く。`status: "offline"` の質問として、地点メモと同じく住所と方位を最初に決める。メモと削除は、ほかの質問と同じ経路を使う。
+8. 引き継ぎ: `GET /records` が、ユーザーのパーティションを強い一貫性でソートキーの順に読み、走行・ルート・地点メモ・質問・削除の跡を `kind` つきで返す。1ページは1回の問い合わせ（最大1MB）で、続きは `cursor` で読む（`cursor` には続きのソートキーだけを入れ、パーティションは `x-user-name` から作る）。
+9. 地点メモの声: `POST /transcriptions` が録音を S3 に置いて SQS に積み、worker が文字起こしだけを行う（AI と読み上げは呼ばない）。App は `GET /transcriptions/{transcriptionId}` をポーリングする。記録は DynamoDB の TTL（`expiresAt`）で1日後に消える。
 
 ## テスト
 
EOF
```

- [ ] **Step 2: 親の 07 を直す（UC-4 の失敗の扱い・UC-7 の約束・質問できなかった地点・読み込みと突き合わせ）**

```bash
cd $ROOT && python3 - docs/07_units_contracts.md <<'PYEOF'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:50]
    s = s.replace(old, new)
rep('''- 流量の制限と一時的な通信の失敗は、Android が間隔を空けて試し直す。
- 通信できないときに質問は送らない（[04_detailed_requirements.md](04_detailed_requirements.md) US-C-09）。''',
'''- 流量の制限と一時的な通信の失敗（5xx を含む）は、Android が間隔を空けて試し直す。書き込みと削除は、何度送っても同じ結果になる。
- 質問を受け付けたが処理に回せなかったときは、記録を残さずに 503 を返す。Android は通信の失敗と同じに扱う。
- 通信できないときに質問は送らない。Android は「質問できなかった地点」として残し、後で送る（[04_detailed_requirements.md](04_detailed_requirements.md) US-C-09、UC-7）。
- 文字数の上限は、前後の空白を落としたあとの Unicode のコードポイントの数で数える。''')
rep('''- 別の端末で同じユーザー名を設定したときは、Android がクラウドの記録を読み込む。
- 端末とクラウドで同じ記録が別々に変えられたときの扱いは、[05_technical_policies.md](05_technical_policies.md) §9 で決め、決まったらここに書く。''',
'''- 別の端末や入れ直したあとに同じユーザー名を設定したとき（ユーザー名を変えるとき）と、利用者が読み直すときに、Android がクラウドの記録を読み込む（下の「読み込みと突き合わせ」）。''')
rep('''### 走行の送り方（スライス2の暫定）

- 走行のメタ情報（名前・状態・記録した区間・自動終了したか・走行のメモ・Android が変更した時刻）は、変わるたびに最新の全体を置く。Backend は、Android が変更した時刻が保存済みのものより新しいときだけ上書きし、古ければ何もせずに受け取ったと返す。端末が1台だけのあいだはこれで足りる。端末をまたいだ突き合わせは [05_technical_policies.md](05_technical_policies.md) §9 で決める（同期の仕上げのスライス）。''',
'''### 走行の送り方

- 走行のメタ情報（名前・状態・記録した区間・自動終了したか・走行のメモ・Android が変更した時刻）は、変わるたびに最新の全体を置く。Backend は、Android が変更した時刻が保存済みのものより新しいときだけ上書きし、古ければ何もせずに受け取ったと返す。''')
rep('''- 入力が不正（400）なものは送り直さない。
- 読み出しは後のスライスで足す。
''', '''- 入力が不正（400）なものは送り直さない。
''')
rep('''- 跡には期限が無い。端末をまたいで削除を伝えるのに使う（読み込みは後のスライス）。''',
'''- 跡には期限が無い。読み込みで、端末をまたいで削除を伝えるのに使う。

### 質問できなかった地点の送り方

- 質問が Backend に届かなかったとき（録音を終えた時点で通信できない・受け付けが通信の失敗に終わった）は、Android がその日時・位置・方位の材料・走行を、自分で作った質問の識別子で残し、通信できるときに置く。
- Backend は「質問できなかった」状態の質問として置き、住所と方位を地点メモと同じく最初に受けたときに決めて返す。Android が変更した時刻が新しいときだけ書く。会話のメモは残す。
- メモと削除は、ほかの質問と同じ送り方。Backend が受け付けた質問と同じ識別子なら、書かずに「重なっている」（409）と返す。

### 読み込みと突き合わせ

- Android はユーザーの記録（走行・ルート・地点メモ・質問・質問できなかった地点・削除の跡）を、ページ送りで最後まで読む。Backend は記録の識別子の順に強い一貫性で返す。項目の名前と型の正本は Backend の `openapi.yaml`（`GET /records`）。
- 同じ記録が端末とクラウドの両方にあれば、Android が変更した時刻が新しいほうを残す。クラウドに削除の跡があれば、端末から消す。端末にだけある未送信の記録は残して送る（[adr/0010](../adr/0010-read-the-cloud-only-when-taking-over.md)）。
- 読み込みは引き継ぎのとき（ユーザー名を変えるとき）と利用者が読み直すときだけ。2台を同時に使っても、一方の変更はもう一方で読み直すまで届かない。''')
p.write_text(s)
PYEOF
git diff --stat docs/07_units_contracts.md
```

Expected: `docs/07_units_contracts.md | ...` の1ファイル（Python の `assert` で止まらない）

- [ ] **Step 3: 文書の写しを Backend に写す**

Run: `cd $ROOT && scripts/sync-docs.sh Backend && git -C Backend status --short docs-parent`
Expected: `M docs-parent/07_units_contracts.md`（スライス4の spec と ADR で直した `05_technical_policies.md`・`mock/index.html` も写る）

- [ ] **Step 4: コミット（Backend と親）**

```bash
cd $BE && git add README.md docs-parent
git commit -m "docs: describe unreached asks and reading records back"
cd $ROOT && git add docs/07_units_contracts.md
git commit -m "docs: add unreached asks and reading records back to the unit contracts"
```

---

### Task 8: smoke・デプロイ（Backend #19 の smoke）

**Files:**
- Modify: `scripts/smoke.py`

- [ ] **Step 1: smoke に確かめを足す**

```bash
cd $BE && git apply <<'EOF'
diff --git a/scripts/smoke.py b/scripts/smoke.py
index eea98fd..c996ebc 100644
--- a/scripts/smoke.py
+++ b/scripts/smoke.py
@@ -1,5 +1,6 @@
 """End-to-end check of the deployed API. Positions are public landmarks only.
-Every ask is sent with the smoke ride, and the ride is deleted at the end, so a run leaves only deletion marks.
+Every ask (and the unreached ask) is sent with the smoke ride, and the ride is deleted at the end, so a run leaves only
+deletion marks.
 
 Usage: AWS_PROFILE=touring env/bin/python scripts/smoke.py
 """
@@ -10,6 +11,7 @@ import json
 import sys
 import time
 import urllib.error
+import urllib.parse
 import urllib.request
 import uuid
 from datetime import datetime, timedelta, timezone
@@ -139,6 +141,57 @@ def transcription_check(api: str, key: str, audio_b64: str) -> bool:
     return check("point memo voice transcribed", ok, f"{elapsed:.1f}s text={body.get('text')} failure={body.get('failure')}")
 
 
+def offline_checks(api: str, key: str, ride_id: str, offline_id: str, taken_id: str) -> list[bool]:
+    url = f"{api}/asks/{offline_id}/offline"
+    unreached = {"askedAt": minutes_ago(12), "location": TOKYO_STATION, "headingSample": {**SOUTH_60M, "at": minutes_ago(12)},
+                 "rideId": ride_id, "updatedAt": minutes_ago(12)}
+    status, body = request("PUT", url, key, USER, unreached)
+    results = [check("unreached ask saved with its place", status == 200 and body.get("applied") is True and bool(body.get("address")),
+                     f"{status} address={body.get('address')} heading={body.get('headingDegrees')}")]
+    status, body = request("PUT", url, key, USER, {**unreached, "updatedAt": minutes_ago(13)})
+    results.append(check("older unreached ask ignored", status == 200 and body.get("applied") is False, str(status)))
+    status, body = request("PUT", f"{api}/asks/{offline_id}/memo", key, USER, {"memo": "何を聞きたかったか", "updatedAt": minutes_ago(1)})
+    results.append(check("memo on an unreached ask", status == 200 and body.get("applied") is True, str(status)))
+    status, body = request("PUT", f"{api}/asks/{taken_id}/offline", key, USER, unreached)
+    results.append(check("unreached ask over a taken ask is 409", status == 409 and body == {"error": "conflict"}, str(status)))
+    return results
+
+
+def read_records(api: str, key: str) -> tuple[list[dict], int]:
+    items, cursor, pages = [], None, 0
+    while True:
+        url = f"{api}/records" + (f"?cursor={urllib.parse.quote(cursor)}" if cursor else "")
+        status, body = request("GET", url, key, USER)
+        if status != 200:
+            return items, -status
+        items += body["items"]
+        pages += 1
+        cursor = body.get("cursor")
+        if not cursor:
+            return items, pages
+
+
+def records_check(api: str, key: str, ride_id: str, note_id: str, ask_ids: list[str], offline_id: str) -> bool:
+    items, pages = read_records(api, key)
+    mine = [i for i in items if i.get("rideId") == ride_id and i["kind"] != "deleted"]
+    kinds = sorted(i["kind"] for i in mine)
+    offline = next((i for i in mine if i.get("askId") == offline_id), {})
+    ok = (kinds == sorted(["ride", "route", "note"] + ["ask"] * (len(ask_ids) + 1))
+          and {i["askId"] for i in mine if i["kind"] == "ask"} == {*ask_ids, offline_id}
+          and any(i["kind"] == "note" and i["noteId"] == note_id for i in mine)
+          and offline.get("status") == "offline" and offline.get("memo") == "何を聞きたかったか")
+    return check("records read back", ok, f"pages={pages} kinds={kinds}")
+
+
+def records_after_delete_check(api: str, key: str, ride_id: str, note_id: str, ask_ids: list[str], offline_id: str) -> bool:
+    items, pages = read_records(api, key)
+    left = [i for i in items if i.get("rideId") == ride_id and i["kind"] != "deleted"]
+    marks = {(i["target"], i["id"]) for i in items if i["kind"] == "deleted"}
+    wanted = {("ride", ride_id), ("note", note_id), ("ask", offline_id), *(("ask", a) for a in ask_ids)}
+    return check("records after delete are marks only", pages > 0 and left == [] and wanted <= marks,
+                 f"pages={pages} left={len(left)} missing={sorted(wanted - marks)}")
+
+
 def delete_checks(api: str, key: str, ride_id: str, note_id: str, ask_id: str) -> list[bool]:
     status, _ = request("DELETE", f"{api}/rides/{ride_id}", key, USER)
     results = [check("ride deleted", status == 204, str(status))]
@@ -148,6 +201,12 @@ def delete_checks(api: str, key: str, ride_id: str, note_id: str, ask_id: str) -
     note = {"at": minutes_ago(15), "location": TOKYO_STATION, "text": "late", "updatedAt": later}
     status, _ = request("PUT", f"{api}/rides/{ride_id}/notes/{note_id}", key, USER, note)
     results.append(check("deleted note does not come back", status == 410, str(status)))
+    point = {"t": minutes_ago(30), "lat": TOKYO_STATION["latitude"], "lon": TOKYO_STATION["longitude"], "accuracy": 5.0, "segment": 0}
+    status, _ = request("PUT", f"{api}/rides/{ride_id}/route/0", key, USER, {"points": [point]})
+    results.append(check("deleted route does not come back", status == 410, str(status)))
+    status, _ = request("PUT", f"{api}/asks/{uuid.uuid4()}/offline", key, USER,
+                        {"askedAt": minutes_ago(12), "location": TOKYO_STATION, "rideId": ride_id, "updatedAt": later})
+    results.append(check("unreached ask of a deleted ride is 410", status == 410, str(status)))
     status, _ = request("PUT", f"{api}/asks/{ask_id}/memo", key, USER, {"memo": "late", "updatedAt": later})
     results.append(check("memo of a deleted ask is 410", status == 410, str(status)))
     status, _ = request("GET", f"{api}/asks/{ask_id}", key, USER)
@@ -207,7 +266,7 @@ def main() -> int:
     print("      timings:", json.dumps(result2.get("timings"), ensure_ascii=False))
     results.append(check("same conversation", accepted2.get("conversationId") == conversation_id))
 
-    _, result3, elapsed3 = ask_and_wait(api, key, {"text": "最初に聞いた山の名前をもう一度言って", "location": TOKYO_STATION,
+    accepted3, result3, elapsed3 = ask_and_wait(api, key, {"text": "最初に聞いた山の名前をもう一度言って", "location": TOKYO_STATION,
                                                    "conversationId": conversation_id, "rideId": ride_id})
     results.append(check("follow-up answered", result3.get("status") == "completed", f"{elapsed3:.1f}s answer={result3.get('answer')}"))
 
@@ -218,7 +277,14 @@ def main() -> int:
 
     results.extend(memo_checks(api, key, accepted.get("askId")))
     results.append(transcription_check(api, key, audio_b64))
+    offline_id = str(uuid.uuid4())
+    results.extend(offline_checks(api, key, ride_id, offline_id, accepted.get("askId")))
+    ask_ids = [a for a in (accepted.get("askId"), accepted2.get("askId"), accepted3.get("askId")) if a]
+    results.append(records_check(api, key, ride_id, note_id, ask_ids, offline_id))
+    status, _ = request("GET", f"{api}/records?cursor=nope", key, USER)
+    results.append(check("bad records cursor is 400", status == 400, str(status)))
     results.extend(delete_checks(api, key, ride_id, note_id, accepted.get("askId")))
+    results.append(records_after_delete_check(api, key, ride_id, note_id, ask_ids, offline_id))
 
     print(f"{sum(results)}/{len(results)} passed")
     return 0 if all(results) else 1
EOF
cd $BE && env/bin/python -c "import ast; ast.parse(open('scripts/smoke.py').read())" && env/bin/pytest -q 2>&1 | tail -1
```

Expected: `267 passed`（smoke は pytest の対象外。構文だけ確かめる）

- [ ] **Step 2: コミット**

```bash
cd $BE && git add scripts/smoke.py
git commit -m "test: check unreached asks and reading records back after a deploy, and that a deleted route does not come back (#19)"
```

- [ ] **Step 3: 利用者にデプロイの確認を取る**

「Backend を `stack-trv2-dev-backend` にデプロイし、smoke を回してよいですか」と聞く。了承が無ければ、ここで止まる（PROJECT.md の plan 1 を「実装済み（確認待ち: デプロイと smoke）」にする）。

- [ ] **Step 4: デプロイする**

Run: `cd $BE && AWS_PROFILE=touring sam build && AWS_PROFILE=touring sam deploy`
Expected: `Successfully created/updated stack - stack-trv2-dev-backend`。変更に `RecordsFunction` とその経路、`AskEditFunction` の経路と権限が出る

- [ ] **Step 5: smoke を回す**

Run: `cd $BE && AWS_PROFILE=touring env/bin/python scripts/smoke.py`
Expected: `39/39 passed`。デプロイの直後に新しい経路（`/asks/{askId}/offline`・`/records`）だけが 403 になったら、1分ほど待って回し直す（PROJECT.md の「持ち越し」）。出力に API の URL や接続キーは出ないが、文書・コミットに写さない
