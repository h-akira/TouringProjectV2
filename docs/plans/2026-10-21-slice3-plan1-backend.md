# スライス3 計画1: Backend（メモ・地点メモ・削除と跡・文字起こし） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend が、走行のメモ・会話のメモ・地点メモを受け取って置き、会話・地点メモ・走行の削除を受けて消し、DynamoDB に削除の跡を残して、跡のある記録への古い書き込みを 410 で断る。地点メモの声を文字にするだけの依頼（AI を呼ばない）を、質問と同じ非同期の形で受ける。デプロイして、通しの確認（smoke）を通す。

**Architecture:** 既存の作り（API Gateway＋Lambda・1つの DynamoDB テーブル・`lib/` に検証と記録、`handlers/` に受け口）を伸ばす。削除の跡は `DELETED#<ASK|RIDE|NOTE>#<id>` の記録で、跡を見て書く書き込み（走行・ルート・地点メモ・会話のメモ）は、書き込みと跡の確かめを1つのトランザクション（`TransactWriteItems` の `ConditionCheck`）にして、削除と同時に来ても戻らないようにする。受け口は、走行の Lambda（`lambda-trv2-dev-rides`）に地点メモと削除を足し、会話のメモと削除は新しい `lambda-trv2-dev-ask-edit`、文字起こしは新しい `lambda-trv2-dev-transcriptions` が受ける。文字起こしの処理は、質問と同じキューと worker に、メッセージの種類（`kind`）を足して行う。

**Tech Stack:** Python 3.13（Lambda）・SAM・boto3・pytest・moto・openapi-spec-validator（どれも既存。足すものは無い）。

**Spec:** [docs/specs/2026-10-21-slice3-design.md](../specs/2026-10-21-slice3-design.md)（§5.4・§6・§9・§10・§11）。決定の記録は [adr/0009](../../adr/0009-keep-deletion-marks-in-the-cloud.md)。

**範囲に入れた issue:** 無し。spec §2 で範囲に入れたのは Android の issue だけで、Backend の開いている issue（#2・#3・#5〜#8・#12〜#14）は、この plan で触る受け口と関わらない。

**計画を書くときに決めたこと（spec からの具体化）:**
- 削除の跡の中身は `kind`（`ask` / `ride` / `note`）・`id`・`rideId`（質問と地点メモのとき）・`deletedAt`。同じものに何度書いても1つ。
- 走行を消すと、走行の跡に加えて、その走行の地点メモと質問の1件ずつにも跡を書く。会話のメモの `PUT` は質問の跡だけを見ればよくなり、次のスライスで端末をまたいで消えたものを伝えるときにも、1件ずつ分かる。
- 走行を消す順番は、走行の跡 → 子の記録の問い合わせ → 子の跡 → 消す。走行の跡を先に書けば、そのあとは子の記録が書かれない（書き込みが跡をトランザクションで確かめる）ので、問い合わせで全部が見つかる。
- 応答: 書き込みは今の走行と同じく `200 {..., "applied": <bool>}`。地点メモは `{noteId, applied, address, headingDegrees}`（古くて書かなかったときは、保存済みの住所と方位を返す）。削除は 204（本文なし）。跡があるときは `410 {"error": "deleted"}`。
- 会話のメモの `PUT` で、質問が無く跡も無いときは 404（`{"error": "not_found"}`）。跡があれば 410。
- メモ（走行・会話）は null・省略・空白だけを「メモ無し」とし、前後の空白を落とす。2000字は Python の文字数（コードポイント）で数える。Android の文字数（UTF-16）は絵文字を2と数えるので、Android が2000字以内に抑えれば Backend で断られない。
- 走行のメモは走行のメタ情報の一部なので、メモを付けずに走行を送ると、保存済みのメモも消える（最新の全体を置く決まりのまま）。
- 地点メモの位置は、不正なら 400（Android が自分の位置から作るので、送り手の誤り）。方位の材料は質問と同じく、不正なら無いものとして扱う。方位は、地点メモの時刻 `at` を基準に、質問と同じ決まり（2分より古い材料・5m 未満は方位なし）で求める。本文は前後の空白を落として1〜2000字。
- 住所は、地点メモが保存済みで住所があれば引き直さない。無ければ（初めて・前回は確定できなかった）引く。
- worker の質問の書き込み（`update_ask`）は、質問の記録があることを条件にする。消えていたら作り直さず、ログ `ask_gone` を出す。
- 文字起こしの記録は `TRANSCRIPTION#<id>`。状態は `pending` / `processing` / `done` / `failed`（API では `pending` を `processing` と返す）。`expiresAt`（受け付けから24時間後の UNIX 秒）を、テーブルの TTL で消す。録音は質問と同じ `audio/<id>.pcm` に置き、文字にしたら消す（1日のライフサイクルも効く）。
- 文字起こしの GET の不正な識別子は、質問の GET と同じく 404。書き込みと削除の不正な識別子は 400（今の走行と同じ）。
- 新しい Lambda の権限は `DynamoDBCrudPolicy`（トランザクションの `ConditionCheckItem` を含む）。走行の Lambda には住所のための `geo-places:ReverseGeocode` と `GEO_REGION` を足す。
- smoke は、すべての質問に smoke の走行の `rideId` を付け、最後にその走行を消す。回し終えると、`USER#smoketest` には削除の跡だけが残る（スライス2の「持ち越し」の、走行に結びつかない質問が増える件を直す）。

この計画のコードは、使い捨てのフォルダでタスクの順にコミットし、各コミットで pytest（今の160件から、最後は217件）が通ること、各タスクのテストだけを当てると落ちること、`sam validate --lint` が通ることを確かめてから書いた。デプロイと smoke は、実行のときに利用者の確認を取ってから行う。

## Global Constraints

- 作業するリポジトリは `Backend/`（`TouringProjectV2_Backend`）と親。どちらも `main` から作業ブランチ `slice3-plan1` を切る。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- **デプロイは、利用者が明示したときだけ行う。** Task 8 の途中で確認を取る。AWS は `AWS_PROFILE=touring`（使えないときは利用者に聞く）。リージョンは `ap-northeast-1`。名前には `trv2` を付ける。
- ユーザー名は英小文字と数字の3〜20文字（`x-user-name`）。他人の記録は無いものとして扱う。既存の接続キーの検査を通す（`/health` 以外）。
- 不正な入力は `400 {"error": "bad_request", "message": <理由>}`（07 UC-4）。削除の跡があるときは `410 {"error": "deleted"}`（spec §5.4）。
- メモと地点メモの本文は2000字まで（US-D-04.003・US-D-08.003）。音声は PCM（16kHz・モノラル・16bit）の base64 で0.25〜60秒（07 UC-5）。
- LLM の入力のトークンを増やさない（この plan はプロンプトに触れない。文字起こしは AI を呼ばない）。
- ログに、質問・回答・メモ・地点メモの本文と位置を出さない（`handlers/common.py` の `log` の決まり）。
- 接続キー・API の URL・アカウント ID を、コードや文書に書かない。smoke の出力に接続キーを出さない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`BE=$ROOT/Backend`。テストは `cd $BE && env/bin/pytest -q`（絞るときは `env/bin/pytest -q tests/test_xxx.py`）。

## Review Focus

- 走行を消した直後に、端末から古い送信（走行・ルート・地点メモ・会話のメモ）が届く → どれも 410 で、記録は戻らない。Task 4 の `test_a_deleted_ride_does_not_come_back_from_an_old_send`。
- 回答を作っているあいだに質問が消される → worker は記録を作り直さない。Task 1 の `test_an_ask_deleted_while_it_is_answered_is_not_written_back`。
- 端末が送れたか分からずに、同じ版の地点メモをもう一度送る → 記録は1つのまま、住所は引き直さず、`applied: false` の 200。Task 3 の `test_sending_the_same_note_again_changes_nothing`。
- 絵文字を含む2000字のメモ → Backend は断らない（Android の数え方のほうが厳しい）。Task 2 の `test_a_memo_of_2000_emoji_is_kept`。
- 1人の質問が多く、走行の削除の問い合わせが1ページ（1MB）に収まらない → すべてのページを読み、その走行の質問を残さない。Task 4 の `test_deleting_a_ride_with_many_asks_reads_every_page`。

---

## ファイル構成（`Backend/` から）

| パス | 役割 | Task |
|---|---|---|
| `src/lib/store.py` | 削除の跡・跡を見て書くトランザクション・質問の書き込みの条件（1）、会話のメモ（2）、地点メモ（3）、削除（4）、文字起こしの記録（5） | 1〜5 |
| `src/handlers/common.py` | 410 と 204 の応答 | 1 |
| `src/handlers/worker.py` | 消えた質問を作り直さない（1）。文字起こしの処理とメッセージの振り分け（5） | 1・5 |
| `src/lib/rides.py` | メモの検証（走行・会話）・パスの UUID の検証 | 2・3 |
| `src/handlers/ask_edit.py`（新規） | `PUT /asks/{askId}/memo`（2）・`DELETE /asks/{askId}`（4） | 2・4 |
| `src/lib/request.py` | 位置と方位の材料の検証を公開する（3）。音声の検証を切り出す（5） | 3・5 |
| `src/lib/notes.py`（新規） | 地点メモの検証 | 3 |
| `src/handlers/rides.py` | 走行のメモ（2）・地点メモの `PUT`（3）・走行と地点メモの `DELETE`（4）・410（1） | 1〜4 |
| `src/handlers/transcriptions.py`（新規） | `POST /transcriptions`・`GET /transcriptions/{transcriptionId}` | 5 |
| `openapi.yaml`・`template.yaml` | API の正本・2つの Lambda と経路・走行の Lambda の権限・テーブルの TTL | 6 |
| `README.md`・親の `docs/07_units_contracts.md`・`docs-parent/` | 文書 | 7 |
| `scripts/smoke.py` | デプロイ後の通しの確認 | 8 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: 両方のリポジトリでブランチを切り、今のテストを回す**

```bash
cd $ROOT && git switch main && git switch -c slice3-plan1
cd $BE && git switch main && git pull --ff-only && git switch -c slice3-plan1
cd $BE && env/bin/pytest -q 2>&1 | tail -1
```

Expected: `160 passed`

---

### Task 1: 削除の跡と、跡を見て書く書き込み

**Files:**
- Modify: `src/lib/store.py`・`src/handlers/common.py`・`src/handlers/rides.py`・`src/handlers/worker.py`
- Test: `tests/test_store.py`・`tests/test_rides.py`・`tests/test_worker.py`

**Interfaces:**
- Consumes: 既存の `store.put_ride`・`store.put_route_chunk`・`store.update_ask`
- Produces:
  - `store.Deleted`（例外。記録かその走行に削除の跡がある）
  - `store.deleted_key(user: str, kind: str, record_id: str) -> dict`（`kind` は `ask` / `ride` / `note`）
  - `store.mark_deleted(user: str, kind: str, record_id: str, deleted_at: str, ride_id: Optional[str] = None) -> None`
  - `store._write_unless_deleted(write: dict, marks: list) -> bool`（トランザクションの1件の `Put` か `Update` と、跡の `ConditionCheck`。書けたら True、書き込み自身の条件で書かなければ False、跡があれば `Deleted`。テーブルの resource の client なので、値は型付けせずに渡す）
  - `store.update_ask(...) -> bool`（質問が無ければ False で、作らない）
  - `store.put_ride`・`store.put_route_chunk` は、走行の跡があれば `Deleted`
  - `handlers.common.deleted() -> dict`（410）・`handlers.common.no_content() -> dict`（204）

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_rides.py b/tests/test_rides.py
index 4785795..5f82f09 100644
--- a/tests/test_rides.py
+++ b/tests/test_rides.py
@@ -185,3 +185,22 @@ def test_a_bad_chunk_is_400(aws):
 def test_a_number_too_large_for_a_float_is_400_not_a_crash(aws):
     result = put_route([{**point(0), "lat": 10 ** 400}])
     assert result["statusCode"] == 400 and "lat and lon" in message(result)
+
+
+def test_a_deleted_ride_is_not_written_back(aws):
+    store.mark_deleted(USER, "ride", RIDE, "2026-10-21T00:00:00.000Z")
+    result = put_ride(ride_body())
+    assert result["statusCode"] == 410 and json.loads(result["body"]) == {"error": "deleted"}
+    assert stored(aws, store.ride_key(USER, RIDE)) is None
+
+
+def test_a_chunk_of_a_deleted_ride_is_410(aws):
+    store.mark_deleted(USER, "ride", RIDE, "2026-10-21T00:00:00.000Z")
+    result = put_route([point(0)])
+    assert result["statusCode"] == 410
+    assert stored(aws, store.route_key(USER, RIDE, 0)) is None
+
+
+def test_another_users_deletion_mark_does_not_stop_the_ride(aws):
+    store.mark_deleted("someone", "ride", RIDE, "2026-10-21T00:00:00.000Z")
+    assert put_ride(ride_body())["statusCode"] == 200
diff --git a/tests/test_store.py b/tests/test_store.py
index 45ff4ea..884837b 100644
--- a/tests/test_store.py
+++ b/tests/test_store.py
@@ -45,3 +45,16 @@ def test_conversation_start_is_kept_from_first_question(aws):
     cid = "33333333-3333-4333-8333-333333333333"
     assert store.conversation_started_at(USER, cid, "2026-10-16T03:00:00.000Z") == "2026-10-16T03:00:00.000Z"
     assert store.conversation_started_at(USER, cid, "2026-10-16T03:10:00.000Z") == "2026-10-16T03:00:00.000Z"
+
+
+def test_a_deletion_mark_is_one_record_however_often_it_is_written(aws):
+    store.mark_deleted("rider01", "note", "n1", "2026-10-21T01:00:00.000Z", ride_id="r1")
+    store.mark_deleted("rider01", "note", "n1", "2026-10-21T02:00:00.000Z", ride_id="r1")
+    items = aws.table.scan()["Items"]
+    assert [i["sk"] for i in items] == ["DELETED#NOTE#n1"]
+    assert items[0]["kind"] == "note" and items[0]["id"] == "n1" and items[0]["rideId"] == "r1"
+
+
+def test_update_ask_does_not_create_a_missing_ask(aws):
+    assert store.update_ask("rider01", "a1", {"status": "completed"}) is False
+    assert aws.table.scan()["Items"] == []
diff --git a/tests/test_worker.py b/tests/test_worker.py
index a4877ae..896e7ca 100644
--- a/tests/test_worker.py
+++ b/tests/test_worker.py
@@ -183,3 +183,18 @@ def test_asks_without_volume_use_the_default(aws):
     rec = Recorder()
     worker.process(USER, ASK, rec.steps())
     assert next(c for c in rec.calls if c[0] == "tts")[3] == 6
+
+
+def test_an_ask_deleted_while_it_is_answered_is_not_written_back(aws):
+    put(aws, audio=False)
+    rec = Recorder()
+    agent = rec.invoke_agent
+
+    def delete_then_answer(prompt, location, session):
+        # The rider deletes the ask while the agent is answering (slice 3 spec §6.3).
+        aws.table.delete_item(Key=store.ask_key(USER, ASK))
+        return agent(prompt, location, session)
+
+    rec.invoke_agent = delete_then_answer
+    worker.process(USER, ASK, rec.steps())
+    assert store.get_ask(USER, ASK) is None
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_store.py tests/test_rides.py tests/test_worker.py 2>&1 | tail -1`
Expected: `6 failed`（`mark_deleted` が無い・410 にならず 200・`update_ask` が質問を作る・worker が消えた質問を作り直す）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/handlers/common.py b/src/handlers/common.py
index 696090f..7a1030c 100644
--- a/src/handlers/common.py
+++ b/src/handlers/common.py
@@ -30,6 +30,15 @@ def response(status: int, body: dict) -> dict:
     }
 
 
+def deleted() -> dict:
+    """410: the record, or its ride, was deleted; the app treats it as sent (slice 3 spec §5.4)."""
+    return response(410, {"error": "deleted"})
+
+
+def no_content() -> dict:
+    return {"statusCode": 204, "headers": {}, "body": ""}
+
+
 def log(record: dict) -> None:
     # One JSON line per event. Callers must not pass question text, answers or positions.
     print(json.dumps(record, ensure_ascii=False))
diff --git a/src/handlers/rides.py b/src/handlers/rides.py
index 63ee45e..a32311a 100644
--- a/src/handlers/rides.py
+++ b/src/handlers/rides.py
@@ -2,7 +2,7 @@
 Reading them back comes with slice 3."""
 from __future__ import annotations
 
-from handlers.common import iso, log, response, utc_now
+from handlers.common import deleted, iso, log, response, utc_now
 from lib import rides, store
 from lib.request import BadRequest, user_name
 
@@ -16,6 +16,8 @@ def handler(event, context):
         return _ride(event, user, ride_id)
     except BadRequest as error:
         return response(400, {"error": "bad_request", "message": str(error)})
+    except store.Deleted:
+        return deleted()
 
 
 def _ride(event: dict, user: str, ride_id: str) -> dict:
diff --git a/src/handlers/worker.py b/src/handlers/worker.py
index d01b195..b8d52ee 100644
--- a/src/handlers/worker.py
+++ b/src/handlers/worker.py
@@ -70,7 +70,9 @@ def _run(user: str, ask_id: str, item: dict, steps: Steps) -> None:
 
     def finish(status: str, error: Optional[str] = None, **fields) -> None:
         outcome.update(fields)
-        store.update_ask(user, ask_id, {"status": status, "error": error, "timings": timings, **fields})
+        if not store.update_ask(user, ask_id, {"status": status, "error": error, "timings": timings, **fields}):
+            log({"event": "ask_gone", "askId": ask_id})
+            return
         log({"event": "ask_done", "askId": ask_id, "status": status, "error": error, "inputType": item.get("inputType"),
              "durationsMs": _durations(timings), "usage": fields.get("usage"), "modelId": fields.get("modelId"),
              "tools": fields.get("tools")})
diff --git a/src/lib/store.py b/src/lib/store.py
index f97db28..9945228 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -1,4 +1,5 @@
-"""Records in one DynamoDB table: pk USER#<name>, sk ASK#<id>, CONV#<id>, RIDE#<id> or RIDE#<id>#ROUTE#<seq>."""
+"""Records in one DynamoDB table: pk USER#<name>, sk ASK#<id>, CONV#<id>, RIDE#<id>, RIDE#<id>#ROUTE#<seq>,
+RIDE#<id>#NOTE#<id>, DELETED#<KIND>#<id> or TRANSCRIPTION#<id>."""
 from __future__ import annotations
 
 import json
@@ -10,6 +11,11 @@ from botocore.exceptions import ClientError
 from lib import clients
 
 _CONDITION_FAILED = "ConditionalCheckFailedException"
+_CANCELLED = "TransactionCanceledException"
+
+
+class Deleted(Exception):
+    """The record, or the ride it belongs to, has a deletion mark (slice 3 spec §5.4, adr/0009)."""
 
 
 def _to_item(value: Any) -> Any:
@@ -35,6 +41,38 @@ def _from_item(value: Any) -> Any:
     return value
 
 
+def deleted_key(user: str, kind: str, record_id: str) -> dict:
+    """kind is ask, ride or note."""
+    return {"pk": f"USER#{user}", "sk": f"DELETED#{kind.upper()}#{record_id}"}
+
+
+def mark_deleted(user: str, kind: str, record_id: str, deleted_at: str, ride_id: Optional[str] = None) -> None:
+    """Writes the deletion mark; marking again keeps one. Marks never expire (adr/0009)."""
+    clients.table().put_item(Item=_to_item({**deleted_key(user, kind, record_id), "kind": kind, "id": record_id,
+                                            "rideId": ride_id, "deletedAt": deleted_at}))
+
+
+def _write_unless_deleted(write: dict, marks: list) -> bool:
+    """Runs one transaction write (a Put or an Update) unless one of the deletion marks exists, atomically, so that a
+    deletion that lands at the same time cannot be undone. True when written; False when the write's own condition
+    failed. Raises Deleted when a mark exists. The table's client takes plain values, as the table does."""
+    table = clients.table()
+    checks = [{"ConditionCheck": {"TableName": table.name, "Key": mark, "ConditionExpression": "attribute_not_exists(pk)"}}
+              for mark in marks]
+    try:
+        table.meta.client.transact_write_items(TransactItems=[write, *checks])
+    except ClientError as error:
+        if error.response["Error"]["Code"] != _CANCELLED:
+            raise
+        codes = [reason.get("Code") for reason in error.response.get("CancellationReasons") or []]
+        if "ConditionalCheckFailed" in codes[1:]:
+            raise Deleted() from None
+        if codes[:1] == ["ConditionalCheckFailed"]:
+            return False
+        raise
+    return True
+
+
 def ask_key(user: str, ask_id: str) -> dict:
     return {"pk": f"USER#{user}", "sk": f"ASK#{ask_id}"}
 
@@ -77,18 +115,26 @@ def claim_ask(user: str, ask_id: str) -> Optional[dict]:
     return _from_item(result["Attributes"])
 
 
-def update_ask(user: str, ask_id: str, fields: dict) -> None:
+def update_ask(user: str, ask_id: str, fields: dict) -> bool:
+    """Sets the fields on a stored ask. False when the ask is gone (deleted meanwhile): it is not written back."""
     values = _to_item(fields)
     if not values:
-        return
+        return True
     names = {f"#k{i}": key for i, key in enumerate(values)}
     expression = "SET " + ", ".join(f"#k{i} = :v{i}" for i in range(len(values)))
-    clients.table().update_item(
-        Key=ask_key(user, ask_id),
-        UpdateExpression=expression,
-        ExpressionAttributeNames=names,
-        ExpressionAttributeValues={f":v{i}": value for i, value in enumerate(values.values())},
-    )
+    try:
+        clients.table().update_item(
+            Key=ask_key(user, ask_id),
+            UpdateExpression=expression,
+            ConditionExpression="attribute_exists(pk)",
+            ExpressionAttributeNames=names,
+            ExpressionAttributeValues={f":v{i}": value for i, value in enumerate(values.values())},
+        )
+    except ClientError as error:
+        if error.response["Error"]["Code"] == _CONDITION_FAILED:
+            return False
+        raise
+    return True
 
 
 def get_ask(user: str, ask_id: str) -> Optional[dict]:
@@ -106,21 +152,16 @@ def route_key(user: str, ride_id: str, seq: int) -> dict:
 
 
 def put_ride(user: str, ride_id: str, fields: dict) -> bool:
-    """Writes the ride unless a newer one is stored (updatedAt, normalised UTC text). False when it was older."""
+    """Writes the ride unless a newer one is stored (updatedAt, normalised UTC text). False when it was older.
+    Raises Deleted when the ride has been deleted."""
     item = {**ride_key(user, ride_id), "rideId": ride_id, **fields}
-    try:
-        clients.table().put_item(
-            Item=_to_item(item),
-            ConditionExpression="attribute_not_exists(pk) OR updatedAt < :u",
-            ExpressionAttributeValues={":u": fields["updatedAt"]},
-        )
-    except ClientError as error:
-        if error.response["Error"]["Code"] == _CONDITION_FAILED:
-            return False
-        raise
-    return True
+    put = {"Put": {"TableName": clients.table().name, "Item": _to_item(item),
+                   "ConditionExpression": "attribute_not_exists(pk) OR updatedAt < :u",
+                   "ExpressionAttributeValues": {":u": fields["updatedAt"]}}}
+    return _write_unless_deleted(put, [deleted_key(user, "ride", ride_id)])
 
 
 def put_route_chunk(user: str, ride_id: str, seq: int, points: list, saved_at: str) -> None:
-    """A chunk is replaced whole: sending it again leaves one copy."""
-    clients.table().put_item(Item=_to_item({**route_key(user, ride_id, seq), "rideId": ride_id, "seq": seq, "points": points, "savedAt": saved_at}))
+    """A chunk is replaced whole: sending it again leaves one copy. Raises Deleted when the ride has been deleted."""
+    item = {**route_key(user, ride_id, seq), "rideId": ride_id, "seq": seq, "points": points, "savedAt": saved_at}
+    _write_unless_deleted({"Put": {"TableName": clients.table().name, "Item": _to_item(item)}}, [deleted_key(user, "ride", ride_id)])
EOF
```

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `166 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/store.py src/handlers/common.py src/handlers/rides.py src/handlers/worker.py tests/test_store.py tests/test_rides.py tests/test_worker.py
git commit -m "feat: keep deletion marks and refuse to write back a deleted ride"
```

---

### Task 2: 走行のメモと会話のメモ

**Files:**
- Modify: `src/lib/rides.py`・`src/lib/store.py`・`src/handlers/rides.py`
- Create: `src/handlers/ask_edit.py`
- Test: `tests/test_rides.py`・`tests/test_ask_edit.py`（新規）

**Interfaces:**
- Consumes: Task 1 の `store._write_unless_deleted`・`store.deleted_key`・`store.Deleted`・`handlers.common.deleted`
- Produces:
  - `rides.MEMO_MAX = 2000`・`rides.memo_text(value) -> Optional[str]`（null・空白は None。前後の空白を落とす）・`rides.parse_ask_memo(event) -> tuple`（`(memo, updatedAt)`）
  - `rides.utc_time(value, field) -> str`（今の `_iso` を公開の名前にしたもの。Task 3 が使う）
  - `RideInput.memo`。走行の記録の `memo`
  - `store.put_ask_memo(user, ask_id, memo: Optional[str], updated_at: str) -> bool`（質問の跡があれば `Deleted`）
  - `handlers.ask_edit.handler`（`PUT /asks/{askId}/memo`。Task 4 が `DELETE` を足す）

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_ask_edit.py b/tests/test_ask_edit.py
new file mode 100644
index 0000000..76de49f
--- /dev/null
+++ b/tests/test_ask_edit.py
@@ -0,0 +1,80 @@
+"""Tests for PUT /asks/{askId}/memo (moto)."""
+import json
+
+from handlers import ask_edit
+from lib import store
+
+USER, ASK = "rider01", "11111111-1111-4111-8111-111111111111"
+T1, T2 = "2026-10-21T01:00:00.000Z", "2026-10-21T02:00:00.000Z"
+
+
+def put_ask(**fields):
+    store.create_ask({**store.ask_key(USER, ASK), "askId": ASK, "status": "completed", "answer": "A", **fields})
+
+
+def put_memo(memo, updated_at=T1, ask_id=ASK, user=USER):
+    event = {"httpMethod": "PUT", "headers": {"x-user-name": user}, "pathParameters": {"askId": ask_id},
+             "body": json.dumps({"memo": memo, "updatedAt": updated_at})}
+    return ask_edit.handler(event, None)
+
+
+def test_a_memo_is_kept_on_the_ask(aws):
+    put_ask()
+    result = put_memo("また来たい")
+    assert result["statusCode"] == 200 and json.loads(result["body"]) == {"askId": ASK, "applied": True}
+    item = store.get_ask(USER, ASK)
+    assert item["memo"] == "また来たい" and item["memoUpdatedAt"] == T1 and item["answer"] == "A"
+
+
+def test_an_older_memo_is_ignored_with_200(aws):
+    put_ask()
+    put_memo("新しい", updated_at=T2)
+    result = put_memo("古い", updated_at=T1)
+    assert result["statusCode"] == 200 and json.loads(result["body"])["applied"] is False
+    assert store.get_ask(USER, ASK)["memo"] == "新しい"
+
+
+def test_sending_the_same_memo_again_changes_nothing(aws):
+    put_ask()
+    put_memo("同じ")
+    assert json.loads(put_memo("同じ")["body"])["applied"] is False
+
+
+def test_a_null_memo_removes_it(aws):
+    put_ask()
+    put_memo("消す前", updated_at=T1)
+    assert json.loads(put_memo(None, updated_at=T2)["body"])["applied"] is True
+    item = store.get_ask(USER, ASK)
+    assert "memo" not in item and item["memoUpdatedAt"] == T2
+
+
+def test_a_memo_for_a_missing_ask_is_404_and_writes_nothing(aws):
+    result = put_memo("どこへ")
+    assert result["statusCode"] == 404
+    assert aws.table.scan()["Items"] == []
+
+
+def test_a_memo_for_another_users_ask_is_404(aws):
+    put_ask()
+    assert put_memo("他人", user="someone")["statusCode"] == 404
+
+
+def test_a_memo_for_a_deleted_ask_is_410(aws):
+    store.mark_deleted(USER, "ask", ASK, T1)
+    result = put_memo("戻らない", updated_at=T2)
+    assert result["statusCode"] == 410 and json.loads(result["body"]) == {"error": "deleted"}
+
+
+def test_a_bad_memo_is_400(aws):
+    put_ask()
+    assert put_memo("あ" * 2001)["statusCode"] == 400
+    assert put_memo(123)["statusCode"] == 400
+    assert put_memo("ok", updated_at="2026-10-21T01:00:00")["statusCode"] == 400
+    assert put_memo("ok", ask_id="not-a-uuid")["statusCode"] == 400
+    assert "memo" not in store.get_ask(USER, ASK)
+
+
+def test_a_memo_of_2000_emoji_is_kept(aws):
+    # Android counts an emoji as two characters, so it never sends more than the Backend takes.
+    put_ask()
+    assert put_memo("😀" * 2000)["statusCode"] == 200
diff --git a/tests/test_rides.py b/tests/test_rides.py
index 5f82f09..bd363b0 100644
--- a/tests/test_rides.py
+++ b/tests/test_rides.py
@@ -204,3 +204,21 @@ def test_a_chunk_of_a_deleted_ride_is_410(aws):
 def test_another_users_deletion_mark_does_not_stop_the_ride(aws):
     store.mark_deleted("someone", "ride", RIDE, "2026-10-21T00:00:00.000Z")
     assert put_ride(ride_body())["statusCode"] == 200
+
+
+def test_a_ride_memo_is_kept_with_the_ride_and_dropped_when_sent_without_one(aws):
+    put_ride(ride_body(memo="  また来たい  "))
+    assert stored(aws, store.ride_key(USER, RIDE))["memo"] == "また来たい"
+    put_ride(ride_body(updatedAt="2026-10-18T10:05:00.000Z"))
+    assert "memo" not in stored(aws, store.ride_key(USER, RIDE))
+
+
+def test_a_ride_memo_of_2000_characters_is_kept_and_2001_is_400(aws):
+    assert put_ride(ride_body(memo="あ" * 2000))["statusCode"] == 200
+    result = put_ride(ride_body(memo="あ" * 2001, updatedAt="2026-10-18T10:05:00.000Z"))
+    assert result["statusCode"] == 400 and "memo" in message(result)
+
+
+def test_a_blank_ride_memo_is_no_memo(aws):
+    put_ride(ride_body(memo="   "))
+    assert "memo" not in stored(aws, store.ride_key(USER, RIDE))
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_rides.py tests/test_ask_edit.py 2>&1 | tail -1`
Expected: `1 error`（`handlers.ask_edit` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/handlers/ask_edit.py b/src/handlers/ask_edit.py
new file mode 100644
index 0000000..b713263
--- /dev/null
+++ b/src/handlers/ask_edit.py
@@ -0,0 +1,33 @@
+"""PUT /asks/{askId}/memo: the app's changes to an ask it keeps (slice 3 spec §6.2)."""
+from __future__ import annotations
+
+from handlers.common import deleted, log, response
+from lib import rides, store
+from lib.request import UUID_RE, BadRequest, user_name
+
+
+def handler(event, context):
+    try:
+        user = user_name(event)
+        ask_id = _ask_id(event)
+        return _memo(event, user, ask_id)
+    except BadRequest as error:
+        return response(400, {"error": "bad_request", "message": str(error)})
+    except store.Deleted:
+        return deleted()
+
+
+def _ask_id(event: dict) -> str:
+    value = (event.get("pathParameters") or {}).get("askId") or ""
+    if not UUID_RE.match(value):
+        raise BadRequest("askId must be a lowercase UUID")
+    return value
+
+
+def _memo(event: dict, user: str, ask_id: str) -> dict:
+    memo, updated_at = rides.parse_ask_memo(event)
+    applied = store.put_ask_memo(user, ask_id, memo, updated_at)
+    if not applied and store.get_ask(user, ask_id) is None:
+        return response(404, {"error": "not_found"})
+    log({"event": "ask_memo_saved", "askId": ask_id, "applied": applied, "hasMemo": memo is not None})
+    return response(200, {"askId": ask_id, "applied": applied})
diff --git a/src/handlers/rides.py b/src/handlers/rides.py
index a32311a..0d5270b 100644
--- a/src/handlers/rides.py
+++ b/src/handlers/rides.py
@@ -28,6 +28,8 @@ def _ride(event: dict, user: str, ride_id: str) -> dict:
         "segments": ride.segments,
         "autoEnded": ride.auto_ended,
         "updatedAt": ride.updated_at,
+        # Sent whole with the ride: a ride without a memo drops the stored one (slice 3 spec §6.2).
+        "memo": ride.memo,
         "savedAt": iso(utc_now()),
     })
     log({"event": "ride_saved", "rideId": ride_id, "status": ride.status, "applied": applied})
diff --git a/src/lib/rides.py b/src/lib/rides.py
index 74dbe75..94d4850 100644
--- a/src/lib/rides.py
+++ b/src/lib/rides.py
@@ -1,10 +1,10 @@
-"""Validation of a ride and its route chunks sent by the Android app (slice 2 spec §6.2)."""
+"""Validation of a ride, its route chunks and the memos sent by the Android app (slice 2 spec §6.2, slice 3 spec §6.2)."""
 from __future__ import annotations
 
 import re
 from dataclasses import dataclass
 from datetime import datetime, timezone
-from typing import Any
+from typing import Any, Optional
 
 from lib.request import BadRequest, UUID_RE, body_json, finite_number
 
@@ -14,6 +14,7 @@ MAX_SEGMENTS = 1000
 MAX_POINTS = 300
 MAX_SEQ = 99999
 SEQ_RE = re.compile(r"^[0-9]{1,5}$")
+MEMO_MAX = 2000
 
 
 @dataclass(frozen=True)
@@ -23,9 +24,10 @@ class RideInput:
     segments: list
     auto_ended: bool
     updated_at: str
+    memo: Optional[str] = None
 
 
-def _iso(value: Any, field: str) -> str:
+def utc_time(value: Any, field: str) -> str:
     """A time with its time zone, normalised to UTC with milliseconds so that stored values compare as text."""
     if not isinstance(value, str):
         raise BadRequest(f"{field} must be a date-time with a time zone")
@@ -39,6 +41,21 @@ def _iso(value: Any, field: str) -> str:
     return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"
 
 
+def memo_text(value: Any) -> Optional[str]:
+    """A memo of up to MEMO_MAX characters; null or blank is no memo (US-D-04.003)."""
+    if value is None:
+        return None
+    if not isinstance(value, str) or len(value) > MEMO_MAX:
+        raise BadRequest(f"memo must be up to {MEMO_MAX} characters or null")
+    return value.strip() or None
+
+
+def parse_ask_memo(event: dict) -> tuple:
+    """(memo, updatedAt) for PUT /asks/{askId}/memo."""
+    data = body_json(event)
+    return memo_text(data.get("memo")), utc_time(data.get("updatedAt"), "updatedAt")
+
+
 def ride_id(event: dict) -> str:
     value = (event.get("pathParameters") or {}).get("rideId") or ""
     if not UUID_RE.match(value):
@@ -60,8 +77,8 @@ def _segments(value: Any, status: str) -> list:
     for i, raw in enumerate(value):
         if not isinstance(raw, dict):
             raise BadRequest("each segment must be an object")
-        started = _iso(raw.get("startedAt"), "startedAt")
-        ended = None if raw.get("endedAt") is None else _iso(raw.get("endedAt"), "endedAt")
+        started = utc_time(raw.get("startedAt"), "startedAt")
+        ended = None if raw.get("endedAt") is None else utc_time(raw.get("endedAt"), "endedAt")
         last = i == len(value) - 1
         # Only a recording ride has an open segment, and only its last one.
         if ended is None and not (last and status == "recording"):
@@ -89,7 +106,8 @@ def parse_ride(event: dict) -> RideInput:
         raise BadRequest("autoEnded must be true or false")
     if auto_ended and status != "ended":
         raise BadRequest("only an ended ride can have ended automatically")
-    return RideInput(name.strip(), status, _segments(data.get("segments"), status), auto_ended, _iso(data.get("updatedAt"), "updatedAt"))
+    return RideInput(name.strip(), status, _segments(data.get("segments"), status), auto_ended,
+                     utc_time(data.get("updatedAt"), "updatedAt"), memo_text(data.get("memo")))
 
 
 def _point(raw: Any) -> dict:
@@ -104,7 +122,7 @@ def _point(raw: Any) -> dict:
     segment = raw.get("segment")
     if isinstance(segment, bool) or not isinstance(segment, int) or not 0 <= segment < MAX_SEGMENTS:
         raise BadRequest(f"segment must be 0-{MAX_SEGMENTS - 1}")
-    return {"t": _iso(raw.get("t"), "t"), "lat": lat, "lon": lon, "accuracy": finite_number(accuracy), "segment": segment}
+    return {"t": utc_time(raw.get("t"), "t"), "lat": lat, "lon": lon, "accuracy": finite_number(accuracy), "segment": segment}
 
 
 def parse_route(event: dict) -> list:
diff --git a/src/lib/store.py b/src/lib/store.py
index 9945228..2aaaf5a 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -137,6 +137,17 @@ def update_ask(user: str, ask_id: str, fields: dict) -> bool:
     return True
 
 
+def put_ask_memo(user: str, ask_id: str, memo: Optional[str], updated_at: str) -> bool:
+    """Sets (or, for None, removes) the ask's memo unless a newer one is stored. False when the ask is missing or the
+    memo is not newer. Raises Deleted when the ask has been deleted."""
+    expression = "SET memoUpdatedAt = :u" + (", memo = :m" if memo is not None else " REMOVE memo")
+    values = {":u": updated_at, **({":m": memo} if memo is not None else {})}
+    update = {"Update": {"TableName": clients.table().name, "Key": ask_key(user, ask_id), "UpdateExpression": expression,
+                         "ConditionExpression": "attribute_exists(pk) AND (attribute_not_exists(memoUpdatedAt) OR memoUpdatedAt < :u)",
+                         "ExpressionAttributeValues": values}}
+    return _write_unless_deleted(update, [deleted_key(user, "ask", ask_id)])
+
+
 def get_ask(user: str, ask_id: str) -> Optional[dict]:
     item = clients.table().get_item(Key=ask_key(user, ask_id)).get("Item")
     return _from_item(item) if item else None
EOF
```

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `178 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/rides.py src/lib/store.py src/handlers/rides.py src/handlers/ask_edit.py tests/test_rides.py tests/test_ask_edit.py
git commit -m "feat: keep a memo on a ride and on an ask"
```

---

### Task 3: 地点メモの `PUT`

**Files:**
- Modify: `src/lib/request.py`・`src/lib/rides.py`・`src/lib/store.py`・`src/handlers/rides.py`
- Create: `src/lib/notes.py`
- Test: `tests/test_notes.py`（新規）

**Interfaces:**
- Consumes: Task 1 の `store._write_unless_deleted`。Task 2 の `rides.utc_time`。既存の `address.describe_location`・`geo.heading_degrees`
- Produces:
  - `request.position(value) -> Optional[dict]`・`request.heading_sample(value) -> Optional[dict]`（今の `_point`・`_sample` を公開の名前にしたもの）
  - `rides.path_id(event, name) -> str`（パスの UUID。不正なら 400。Task 4 が使う）
  - `notes.NOTE_TEXT_MAX = 2000`・`notes.NoteInput`・`notes.parse_note(event) -> NoteInput`
  - `store.note_key(user, ride_id, note_id) -> dict`（`RIDE#<rideId>#NOTE#<noteId>`）・`store.get_note(...) -> Optional[dict]`・`store.put_note(user, ride_id, note_id, fields) -> bool`（地点メモか走行の跡があれば `Deleted`）
  - `PUT /rides/{rideId}/notes/{noteId}` の応答 `{noteId, applied, address, headingDegrees}`

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_notes.py b/tests/test_notes.py
new file mode 100644
index 0000000..0375c21
--- /dev/null
+++ b/tests/test_notes.py
@@ -0,0 +1,133 @@
+"""Tests for PUT /rides/{rideId}/notes/{noteId} (moto, the address lookup stubbed)."""
+import json
+
+import pytest
+
+from handlers import rides
+from lib import store
+
+USER = "rider01"
+RIDE = "5c9a1f0e-2b3d-4e5f-8a6b-7c8d9e0f1a2b"
+NOTE = "9d8c7b6a-5f4e-4d3c-8b2a-1f0e9d8c7b6a"
+HERE = {"latitude": 35.6812, "longitude": 139.7671}
+# About 60 m south of HERE, 10 s before the note: the rider was heading north.
+SOUTH = {"latitude": 35.68066, "longitude": 139.7671, "at": "2026-10-21T00:59:50.000Z"}
+
+
+@pytest.fixture
+def places(monkeypatch):
+    calls = []
+
+    def describe(lat, lon):
+        calls.append((lat, lon))
+        return "東京都千代田区丸の内"
+
+    monkeypatch.setattr(rides.address, "describe_location", describe)
+    return calls
+
+
+def note_body(**changes):
+    body = {"at": "2026-10-21T01:00:00.000Z", "location": HERE, "headingSample": SOUTH, "text": "ここ、また来たい",
+            "updatedAt": "2026-10-21T01:00:00.000Z"}
+    return {**body, **changes}
+
+
+def put_note(body, note_id=NOTE, ride_id=RIDE, user=USER):
+    event = {"httpMethod": "PUT", "headers": {"x-user-name": user}, "pathParameters": {"rideId": ride_id, "noteId": note_id},
+             "body": json.dumps(body)}
+    return rides.handler(event, None)
+
+
+def answer(result):
+    return json.loads(result["body"])
+
+
+def test_a_note_is_kept_under_its_ride_with_its_place_and_heading(aws, places):
+    result = put_note(note_body())
+    assert result["statusCode"] == 200
+    assert answer(result) == {"noteId": NOTE, "applied": True, "address": "東京都千代田区丸の内", "headingDegrees": 0.0}
+    item = store.get_note(USER, RIDE, NOTE)
+    assert item["text"] == "ここ、また来たい" and item["location"] == HERE and item["at"] == "2026-10-21T01:00:00.000Z"
+    assert item["rideId"] == RIDE and item["address"] == "東京都千代田区丸の内" and "headingSample" not in item
+    assert aws.table.scan()["Items"][0]["sk"] == f"RIDE#{RIDE}#NOTE#{NOTE}"
+
+
+def test_an_edited_note_keeps_its_place_without_looking_it_up_again(aws, places):
+    put_note(note_body())
+    result = put_note(note_body(text="直した", updatedAt="2026-10-21T01:10:00.000Z"))
+    assert answer(result)["applied"] is True and answer(result)["address"] == "東京都千代田区丸の内"
+    assert store.get_note(USER, RIDE, NOTE)["text"] == "直した"
+    assert len(places) == 1
+
+
+def test_a_place_that_could_not_be_found_is_looked_up_on_the_next_put(aws, monkeypatch):
+    found = iter([None, "神奈川県足柄下郡箱根町仙石原"])
+    monkeypatch.setattr(rides.address, "describe_location", lambda lat, lon: next(found))
+    assert answer(put_note(note_body()))["address"] is None
+    result = put_note(note_body(updatedAt="2026-10-21T01:10:00.000Z"))
+    assert answer(result)["address"] == "神奈川県足柄下郡箱根町仙石原"
+
+
+def test_an_older_note_is_ignored_and_answers_with_the_stored_place(aws, places):
+    put_note(note_body(text="新しい", updatedAt="2026-10-21T01:10:00.000Z"))
+    result = put_note(note_body(text="古い"))
+    assert result["statusCode"] == 200
+    assert answer(result) == {"noteId": NOTE, "applied": False, "address": "東京都千代田区丸の内", "headingDegrees": 0.0}
+    assert store.get_note(USER, RIDE, NOTE)["text"] == "新しい"
+
+
+def test_a_note_without_a_position_has_no_place_or_heading(aws, places):
+    result = put_note(note_body(location=None, headingSample=None))
+    assert answer(result) == {"noteId": NOTE, "applied": True, "address": None, "headingDegrees": None}
+    assert places == [] and "location" not in store.get_note(USER, RIDE, NOTE)
+
+
+def test_a_note_may_arrive_before_its_ride(aws, places):
+    # Notes go after rides in a pass, but a ride refused or still failing must not hold its notes back.
+    assert put_note(note_body())["statusCode"] == 200
+    assert aws.table.get_item(Key=store.ride_key(USER, RIDE)).get("Item") is None
+
+
+def test_a_note_of_a_deleted_ride_or_a_deleted_note_is_410(aws, places):
+    store.mark_deleted(USER, "ride", RIDE, "2026-10-21T02:00:00.000Z")
+    assert put_note(note_body())["statusCode"] == 410
+    other = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
+    store.mark_deleted(USER, "note", other, "2026-10-21T02:00:00.000Z", ride_id="6d0b2a1f-3c4e-4f5a-9b7c-8d9e0f1a2b3c")
+    assert put_note(note_body(), note_id=other, ride_id="6d0b2a1f-3c4e-4f5a-9b7c-8d9e0f1a2b3c")["statusCode"] == 410
+    assert aws.table.scan(FilterExpression="begins_with(sk, :r)", ExpressionAttributeValues={":r": "RIDE#"})["Items"] == []
+
+
+def test_notes_are_kept_apart_by_user(aws, places):
+    put_note(note_body())
+    assert store.get_note("someone", RIDE, NOTE) is None
+
+
+@pytest.mark.parametrize("changes", [
+    {"text": ""}, {"text": "   "}, {"text": "あ" * 2001}, {"text": None},
+    {"at": "2026-10-21T01:00:00"}, {"updatedAt": None},
+    {"location": {"latitude": 91, "longitude": 0}}, {"location": "here"},
+])
+def test_a_bad_note_is_400_and_writes_nothing(aws, places, changes):
+    result = put_note(note_body(**changes))
+    assert result["statusCode"] == 400 and json.loads(result["body"])["error"] == "bad_request"
+    assert aws.table.scan()["Items"] == []
+
+
+def test_a_note_of_2000_characters_is_kept(aws, places):
+    assert put_note(note_body(text="あ" * 2000))["statusCode"] == 200
+
+
+def test_a_broken_heading_sample_only_drops_the_heading(aws, places):
+    result = put_note(note_body(headingSample={"latitude": "x"}))
+    assert result["statusCode"] == 200 and answer(result)["headingDegrees"] is None
+
+
+def test_a_bad_note_id_is_400(aws, places):
+    assert put_note(note_body(), note_id="note-1")["statusCode"] == 400
+
+
+def test_sending_the_same_note_again_changes_nothing(aws, places):
+    put_note(note_body())
+    again = put_note(note_body())
+    assert again["statusCode"] == 200 and answer(again)["applied"] is False
+    assert len(places) == 1 and len(aws.table.scan()["Items"]) == 1
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_notes.py 2>&1 | tail -1`
Expected: `1 failed, 19 errors`（`rides.address` が無く、住所の作り物を差し込めない）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/handlers/rides.py b/src/handlers/rides.py
index 0d5270b..0754485 100644
--- a/src/handlers/rides.py
+++ b/src/handlers/rides.py
@@ -1,9 +1,10 @@
-"""PUT /rides/{rideId} and PUT /rides/{rideId}/route/{seq}: the app sends its rides (07 UC-7, slice 2 spec §6.2).
-Reading them back comes with slice 3."""
+"""PUT /rides/{rideId}, PUT /rides/{rideId}/route/{seq} and PUT /rides/{rideId}/notes/{noteId}: the app sends its
+rides, their routes and their point memos (07 UC-7, slice 2 spec §6.2, slice 3 spec §6.2). Reading them back comes later."""
 from __future__ import annotations
 
-from handlers.common import deleted, iso, log, response, utc_now
-from lib import rides, store
+from handlers.common import deleted, iso, log, parse_iso, response, utc_now
+from lib import address, notes, rides, store
+from lib.geo import heading_degrees
 from lib.request import BadRequest, user_name
 
 
@@ -11,7 +12,10 @@ def handler(event, context):
     try:
         user = user_name(event)
         ride_id = rides.ride_id(event)
-        if (event.get("pathParameters") or {}).get("seq") is not None:
+        path = event.get("pathParameters") or {}
+        if path.get("noteId") is not None:
+            return _note(event, user, ride_id)
+        if path.get("seq") is not None:
             return _route(event, user, ride_id)
         return _ride(event, user, ride_id)
     except BadRequest as error:
@@ -43,3 +47,30 @@ def _route(event: dict, user: str, ride_id: str) -> dict:
     store.put_route_chunk(user, ride_id, seq, points, iso(utc_now()))
     log({"event": "route_saved", "rideId": ride_id, "seq": seq, "points": len(points)})
     return response(200, {"rideId": ride_id, "seq": seq})
+
+
+def _note(event: dict, user: str, ride_id: str) -> dict:
+    note_id = rides.path_id(event, "noteId")
+    note = notes.parse_note(event)
+    stored = store.get_note(user, ride_id, note_id)
+    if stored is not None and stored["updatedAt"] >= note.updated_at:
+        applied, kept = False, stored
+    else:
+        heading = heading_degrees(note.location, note.heading_sample, parse_iso(note.at))
+        kept = {
+            "at": note.at,
+            "location": note.location,
+            "text": note.text,
+            "updatedAt": note.updated_at,
+            # The position never changes, so the place is looked up once; a failed lookup is tried again (§6.2).
+            "address": (stored or {}).get("address") or (
+                address.describe_location(note.location["latitude"], note.location["longitude"]) if note.location else None),
+            "headingDegrees": round(heading, 1) if heading is not None else None,
+            "savedAt": iso(utc_now()),
+        }
+        applied = store.put_note(user, ride_id, note_id, kept)
+        if not applied:
+            kept = store.get_note(user, ride_id, note_id) or kept
+    log({"event": "note_saved", "rideId": ride_id, "noteId": note_id, "applied": applied, "hasPlace": kept.get("address") is not None})
+    return response(200, {"noteId": note_id, "applied": applied, "address": kept.get("address"),
+                          "headingDegrees": kept.get("headingDegrees")})
diff --git a/src/lib/notes.py b/src/lib/notes.py
new file mode 100644
index 0000000..f446ffe
--- /dev/null
+++ b/src/lib/notes.py
@@ -0,0 +1,34 @@
+"""Validation of a point memo sent by the Android app (slice 3 spec §6.2, US-D-08)."""
+from __future__ import annotations
+
+from dataclasses import dataclass
+from typing import Optional
+
+from lib.request import BadRequest, body_json, heading_sample, position
+from lib.rides import utc_time
+
+NOTE_TEXT_MAX = 2000
+
+
+@dataclass(frozen=True)
+class NoteInput:
+    at: str
+    location: Optional[dict]
+    heading_sample: Optional[dict]
+    text: str
+    updated_at: str
+
+
+def parse_note(event: dict) -> NoteInput:
+    data = body_json(event)
+    location = None
+    if data.get("location") is not None:
+        # The app writes the note from its own fix, so a broken position is its mistake (unlike an ask's).
+        location = position(data.get("location"))
+        if location is None:
+            raise BadRequest("location must be a position or null")
+    text = data.get("text")
+    if not isinstance(text, str) or not text.strip() or len(text) > NOTE_TEXT_MAX:
+        raise BadRequest(f"text must be 1-{NOTE_TEXT_MAX} characters")
+    return NoteInput(utc_time(data.get("at"), "at"), location, heading_sample(data.get("headingSample")), text.strip(),
+                     utc_time(data.get("updatedAt"), "updatedAt"))
diff --git a/src/lib/request.py b/src/lib/request.py
index a2aa2b5..a3467f5 100644
--- a/src/lib/request.py
+++ b/src/lib/request.py
@@ -61,7 +61,7 @@ def finite_number(value: Any) -> Optional[float]:
     return number if math.isfinite(number) else None
 
 
-def _point(value: Any) -> Optional[dict]:
+def position(value: Any) -> Optional[dict]:
     """A position, or None when it is missing or broken (the question still goes ahead)."""
     if not isinstance(value, dict):
         return None
@@ -71,8 +71,9 @@ def _point(value: Any) -> Optional[dict]:
     return {"latitude": lat, "longitude": lon}
 
 
-def _sample(value: Any) -> Optional[dict]:
-    point = _point(value)
+def heading_sample(value: Any) -> Optional[dict]:
+    """The older position the heading is taken from, or None when it is missing or broken."""
+    point = position(value)
     at = value.get("at") if isinstance(value, dict) else None
     if point is None or not isinstance(at, str):
         return None
@@ -135,5 +136,5 @@ def parse_ask(event: dict) -> AskInput:
         raise BadRequest("rideId must be a lowercase UUID")
 
     return AskInput(
-        audio, text, _point(data.get("location")), _sample(data.get("headingSample")), conversation_id, int(volume_db), ride_id
+        audio, text, position(data.get("location")), heading_sample(data.get("headingSample")), conversation_id, int(volume_db), ride_id
     )
diff --git a/src/lib/rides.py b/src/lib/rides.py
index 94d4850..44a7e93 100644
--- a/src/lib/rides.py
+++ b/src/lib/rides.py
@@ -56,13 +56,18 @@ def parse_ask_memo(event: dict) -> tuple:
     return memo_text(data.get("memo")), utc_time(data.get("updatedAt"), "updatedAt")
 
 
-def ride_id(event: dict) -> str:
-    value = (event.get("pathParameters") or {}).get("rideId") or ""
+def path_id(event: dict, name: str) -> str:
+    """A UUID from the path (rideId, noteId, askId); a bad one is the sender's mistake, so 400."""
+    value = (event.get("pathParameters") or {}).get(name) or ""
     if not UUID_RE.match(value):
-        raise BadRequest("rideId must be a lowercase UUID")
+        raise BadRequest(f"{name} must be a lowercase UUID")
     return value
 
 
+def ride_id(event: dict) -> str:
+    return path_id(event, "rideId")
+
+
 def chunk_seq(event: dict) -> int:
     value = (event.get("pathParameters") or {}).get("seq") or ""
     if not SEQ_RE.match(value):
diff --git a/src/lib/store.py b/src/lib/store.py
index 2aaaf5a..00ad4ae 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -162,6 +162,26 @@ def route_key(user: str, ride_id: str, seq: int) -> dict:
     return {"pk": f"USER#{user}", "sk": f"RIDE#{ride_id}#ROUTE#{seq:05d}"}
 
 
+def note_key(user: str, ride_id: str, note_id: str) -> dict:
+    # Under the ride, so that deleting the ride finds its notes with its route (slice 3 spec §6.1).
+    return {"pk": f"USER#{user}", "sk": f"RIDE#{ride_id}#NOTE#{note_id}"}
+
+
+def get_note(user: str, ride_id: str, note_id: str) -> Optional[dict]:
+    item = clients.table().get_item(Key=note_key(user, ride_id, note_id)).get("Item")
+    return _from_item(item) if item else None
+
+
+def put_note(user: str, ride_id: str, note_id: str, fields: dict) -> bool:
+    """Writes the note unless a newer one is stored. False when it was not newer. Raises Deleted when the note or its
+    ride has been deleted."""
+    item = {**note_key(user, ride_id, note_id), "noteId": note_id, "rideId": ride_id, **fields}
+    put = {"Put": {"TableName": clients.table().name, "Item": _to_item(item),
+                   "ConditionExpression": "attribute_not_exists(pk) OR updatedAt < :u",
+                   "ExpressionAttributeValues": {":u": fields["updatedAt"]}}}
+    return _write_unless_deleted(put, [deleted_key(user, "note", note_id), deleted_key(user, "ride", ride_id)])
+
+
 def put_ride(user: str, ride_id: str, fields: dict) -> bool:
     """Writes the ride unless a newer one is stored (updatedAt, normalised UTC text). False when it was older.
     Raises Deleted when the ride has been deleted."""
EOF
```

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `198 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/request.py src/lib/rides.py src/lib/notes.py src/lib/store.py src/handlers/rides.py tests/test_notes.py
git commit -m "feat: keep point memos with their place and heading"
```

---

### Task 4: 削除（会話・地点メモ・走行）

**Files:**
- Modify: `src/lib/store.py`・`src/handlers/rides.py`・`src/handlers/ask_edit.py`
- Test: `tests/test_deletes.py`（新規）

**Interfaces:**
- Consumes: Task 1 の `store.mark_deleted`・`handlers.common.no_content`。Task 3 の `store.note_key`・`rides.path_id`
- Produces:
  - `store.delete_ask(user, ask_id, deleted_at) -> None`（跡の `rideId` は質問の記録から取る）
  - `store.delete_note(user, ride_id, note_id, deleted_at) -> None`
  - `store.delete_ride(user, ride_id, deleted_at) -> dict`（`{"notes", "asks", "chunks"}` の数。ログに使う）
  - `DELETE /asks/{askId}`・`DELETE /rides/{rideId}`・`DELETE /rides/{rideId}/notes/{noteId}` は、`httpMethod` で振り分ける。どれも 204

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_deletes.py b/tests/test_deletes.py
new file mode 100644
index 0000000..ecf0a40
--- /dev/null
+++ b/tests/test_deletes.py
@@ -0,0 +1,118 @@
+"""Tests for DELETE /asks/{askId}, /rides/{rideId} and /rides/{rideId}/notes/{noteId} (moto)."""
+import json
+
+from handlers import ask_edit, rides
+from lib import store
+
+USER = "rider01"
+RIDE = "5c9a1f0e-2b3d-4e5f-8a6b-7c8d9e0f1a2b"
+OTHER_RIDE = "6d0b2a1f-3c4e-4f5a-9b7c-8d9e0f1a2b3c"
+NOTE = "9d8c7b6a-5f4e-4d3c-8b2a-1f0e9d8c7b6a"
+ASK = "11111111-1111-4111-8111-111111111111"
+ASK2 = "22222222-2222-4222-8222-222222222222"
+T = "2026-10-21T01:00:00.000Z"
+
+
+def call(handler, method, user=USER, body=None, **path):
+    event = {"httpMethod": method, "headers": {"x-user-name": user}, "pathParameters": path}
+    if body is not None:
+        event["body"] = json.dumps(body)
+    return handler.handler(event, None)
+
+
+def sks(aws, prefix=""):
+    return sorted(i["sk"] for i in aws.table.scan()["Items"] if i["sk"].startswith(prefix))
+
+
+def ride_body(updated_at=T):
+    return {"name": "箱根", "status": "ended", "segments": [{"startedAt": "2026-10-21T00:00:00.000Z", "endedAt": T}],
+            "autoEnded": False, "updatedAt": updated_at}
+
+
+def note_body(updated_at=T):
+    return {"at": T, "location": None, "text": "メモ", "updatedAt": updated_at}
+
+
+def ask(ask_id, ride_id, user=USER):
+    store.create_ask({**store.ask_key(user, ask_id), "askId": ask_id, "status": "completed", "rideId": ride_id})
+
+
+def a_ride_with_everything(aws, user=USER):
+    call(rides, "PUT", user=user, body=ride_body(), rideId=RIDE)
+    for seq in ("0", "1"):
+        point = {"t": T, "lat": 35.0, "lon": 139.0, "accuracy": 5.0, "segment": 0}
+        call(rides, "PUT", user=user, body={"points": [point]}, rideId=RIDE, seq=seq)
+    call(rides, "PUT", user=user, body=note_body(), rideId=RIDE, noteId=NOTE)
+    ask(ASK, RIDE, user)
+    ask(ASK2, OTHER_RIDE, user)
+
+
+def test_deleting_a_ride_removes_its_route_notes_and_asks_and_marks_them(aws):
+    a_ride_with_everything(aws)
+    result = call(rides, "DELETE", rideId=RIDE)
+    assert result["statusCode"] == 204 and result["body"] == ""
+    assert sks(aws) == sorted([f"ASK#{ASK2}", f"DELETED#ASK#{ASK}", f"DELETED#NOTE#{NOTE}", f"DELETED#RIDE#{RIDE}"])
+    mark = aws.table.get_item(Key=store.deleted_key(USER, "ask", ASK))["Item"]
+    assert mark["kind"] == "ask" and mark["rideId"] == RIDE and mark["deletedAt"].endswith("Z")
+
+
+def test_a_deleted_ride_does_not_come_back_from_an_old_send(aws):
+    a_ride_with_everything(aws)
+    call(rides, "DELETE", rideId=RIDE)
+    assert call(rides, "PUT", body=ride_body("2026-10-21T09:00:00.000Z"), rideId=RIDE)["statusCode"] == 410
+    point = {"t": T, "lat": 35.0, "lon": 139.0, "accuracy": 5.0, "segment": 0}
+    assert call(rides, "PUT", body={"points": [point]}, rideId=RIDE, seq="0")["statusCode"] == 410
+    assert call(rides, "PUT", body=note_body("2026-10-21T09:00:00.000Z"), rideId=RIDE, noteId=NOTE)["statusCode"] == 410
+    memo = {"memo": "戻らない", "updatedAt": "2026-10-21T09:00:00.000Z"}
+    assert call(ask_edit, "PUT", body=memo, askId=ASK)["statusCode"] == 410
+    assert sks(aws, "RIDE#") == [] and sks(aws, "ASK#") == [f"ASK#{ASK2}"]
+
+
+def test_deleting_a_ride_leaves_another_users_records(aws):
+    a_ride_with_everything(aws, user="someone")
+    call(rides, "DELETE", rideId=RIDE)
+    assert len([k for k in sks(aws, "RIDE#")]) == 4
+    assert call(rides, "PUT", user="someone", body=ride_body("2026-10-21T09:00:00.000Z"), rideId=RIDE)["statusCode"] == 200
+
+
+def test_deleting_a_ride_with_many_asks_reads_every_page(aws):
+    call(rides, "PUT", body=ride_body(), rideId=RIDE)
+    asks = [f"{i:08x}-0000-4000-8000-000000000000" for i in range(60)]
+    with aws.table.batch_writer() as batch:
+        for ask_id in asks:
+            batch.put_item(Item={**store.ask_key(USER, ask_id), "askId": ask_id, "rideId": RIDE, "answer": "あ" * 20000})
+    call(rides, "DELETE", rideId=RIDE)
+    assert sks(aws, "ASK#") == []
+
+
+def test_deleting_twice_or_deleting_what_never_arrived_is_204(aws):
+    assert call(rides, "DELETE", rideId=RIDE)["statusCode"] == 204
+    assert call(rides, "DELETE", rideId=RIDE)["statusCode"] == 204
+    assert call(rides, "DELETE", rideId=RIDE, noteId=NOTE)["statusCode"] == 204
+    assert call(ask_edit, "DELETE", askId=ASK)["statusCode"] == 204
+    assert sks(aws) == sorted([f"DELETED#ASK#{ASK}", f"DELETED#NOTE#{NOTE}", f"DELETED#RIDE#{RIDE}"])
+
+
+def test_deleting_a_note_keeps_the_ride_and_stops_the_note_coming_back(aws):
+    call(rides, "PUT", body=ride_body(), rideId=RIDE)
+    call(rides, "PUT", body=note_body(), rideId=RIDE, noteId=NOTE)
+    assert call(rides, "DELETE", rideId=RIDE, noteId=NOTE)["statusCode"] == 204
+    assert sks(aws) == sorted([f"DELETED#NOTE#{NOTE}", f"RIDE#{RIDE}"])
+    assert call(rides, "PUT", body=note_body("2026-10-21T09:00:00.000Z"), rideId=RIDE, noteId=NOTE)["statusCode"] == 410
+    assert call(rides, "PUT", body=ride_body("2026-10-21T09:00:00.000Z"), rideId=RIDE)["statusCode"] == 200
+
+
+def test_deleting_an_ask_keeps_its_ride_and_marks_it_with_the_ride(aws):
+    call(rides, "PUT", body=ride_body(), rideId=RIDE)
+    ask(ASK, RIDE)
+    assert call(ask_edit, "DELETE", askId=ASK)["statusCode"] == 204
+    assert sks(aws) == sorted([f"DELETED#ASK#{ASK}", f"RIDE#{RIDE}"])
+    assert aws.table.get_item(Key=store.deleted_key(USER, "ask", ASK))["Item"]["rideId"] == RIDE
+
+
+def test_a_bad_id_to_delete_is_400(aws):
+    assert call(rides, "DELETE", rideId="ride-1")["statusCode"] == 400
+    assert call(rides, "DELETE", rideId=RIDE, noteId="note-1")["statusCode"] == 400
+    assert call(ask_edit, "DELETE", askId="ask-1")["statusCode"] == 400
+    assert call(ask_edit, "DELETE", user="BAD", askId=ASK)["statusCode"] == 400
+    assert sks(aws) == []
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_deletes.py 2>&1 | tail -1`
Expected: `6 failed, 2 passed`（`DELETE` が `PUT` として扱われ、400 になる）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/handlers/ask_edit.py b/src/handlers/ask_edit.py
index b713263..9deeee0 100644
--- a/src/handlers/ask_edit.py
+++ b/src/handlers/ask_edit.py
@@ -1,7 +1,7 @@
-"""PUT /asks/{askId}/memo: the app's changes to an ask it keeps (slice 3 spec §6.2)."""
+"""PUT /asks/{askId}/memo and DELETE /asks/{askId}: the app's changes to an ask it keeps (slice 3 spec §6.2)."""
 from __future__ import annotations
 
-from handlers.common import deleted, log, response
+from handlers.common import deleted, iso, log, no_content, response, utc_now
 from lib import rides, store
 from lib.request import UUID_RE, BadRequest, user_name
 
@@ -10,6 +10,10 @@ def handler(event, context):
     try:
         user = user_name(event)
         ask_id = _ask_id(event)
+        if event.get("httpMethod") == "DELETE":
+            store.delete_ask(user, ask_id, iso(utc_now()))
+            log({"event": "ask_deleted", "askId": ask_id})
+            return no_content()
         return _memo(event, user, ask_id)
     except BadRequest as error:
         return response(400, {"error": "bad_request", "message": str(error)})
diff --git a/src/handlers/rides.py b/src/handlers/rides.py
index 0754485..19248cf 100644
--- a/src/handlers/rides.py
+++ b/src/handlers/rides.py
@@ -1,8 +1,9 @@
 """PUT /rides/{rideId}, PUT /rides/{rideId}/route/{seq} and PUT /rides/{rideId}/notes/{noteId}: the app sends its
-rides, their routes and their point memos (07 UC-7, slice 2 spec §6.2, slice 3 spec §6.2). Reading them back comes later."""
+rides, their routes and their point memos (07 UC-7, slice 2 spec §6.2, slice 3 spec §6.2). DELETE /rides/{rideId} and
+DELETE /rides/{rideId}/notes/{noteId} remove them and leave deletion marks (adr/0009). Reading them back comes later."""
 from __future__ import annotations
 
-from handlers.common import deleted, iso, log, parse_iso, response, utc_now
+from handlers.common import deleted, iso, log, no_content, parse_iso, response, utc_now
 from lib import address, notes, rides, store
 from lib.geo import heading_degrees
 from lib.request import BadRequest, user_name
@@ -13,6 +14,8 @@ def handler(event, context):
         user = user_name(event)
         ride_id = rides.ride_id(event)
         path = event.get("pathParameters") or {}
+        if event.get("httpMethod") == "DELETE":
+            return _delete(event, user, ride_id)
         if path.get("noteId") is not None:
             return _note(event, user, ride_id)
         if path.get("seq") is not None:
@@ -74,3 +77,15 @@ def _note(event: dict, user: str, ride_id: str) -> dict:
     log({"event": "note_saved", "rideId": ride_id, "noteId": note_id, "applied": applied, "hasPlace": kept.get("address") is not None})
     return response(200, {"noteId": note_id, "applied": applied, "address": kept.get("address"),
                           "headingDegrees": kept.get("headingDegrees")})
+
+
+def _delete(event: dict, user: str, ride_id: str) -> dict:
+    # Deleting twice, or deleting what never arrived, is the same as deleting once (slice 3 spec §6.2).
+    if (event.get("pathParameters") or {}).get("noteId") is not None:
+        note_id = rides.path_id(event, "noteId")
+        store.delete_note(user, ride_id, note_id, iso(utc_now()))
+        log({"event": "note_deleted", "rideId": ride_id, "noteId": note_id})
+        return no_content()
+    removed = store.delete_ride(user, ride_id, iso(utc_now()))
+    log({"event": "ride_deleted", "rideId": ride_id, **removed})
+    return no_content()
diff --git a/src/lib/store.py b/src/lib/store.py
index 00ad4ae..b16f980 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -196,3 +196,52 @@ def put_route_chunk(user: str, ride_id: str, seq: int, points: list, saved_at: s
     """A chunk is replaced whole: sending it again leaves one copy. Raises Deleted when the ride has been deleted."""
     item = {**route_key(user, ride_id, seq), "rideId": ride_id, "seq": seq, "points": points, "savedAt": saved_at}
     _write_unless_deleted({"Put": {"TableName": clients.table().name, "Item": _to_item(item)}}, [deleted_key(user, "ride", ride_id)])
+
+
+def _query_keys(user: str, prefix: str, ride_id: Optional[str] = None) -> list:
+    """The records whose sort key starts with prefix (all pages); with ride_id, only those of that ride."""
+    params: dict = {"KeyConditionExpression": "pk = :p AND begins_with(sk, :s)", "ProjectionExpression": "pk, sk",
+                    "ExpressionAttributeValues": {":p": f"USER#{user}", ":s": prefix}}
+    if ride_id is not None:
+        params["FilterExpression"] = "rideId = :r"
+        params["ExpressionAttributeValues"][":r"] = ride_id
+    keys = []
+    while True:
+        page = clients.table().query(**params)
+        keys += page.get("Items", [])
+        if "LastEvaluatedKey" not in page:
+            return keys
+        params["ExclusiveStartKey"] = page["LastEvaluatedKey"]
+
+
+def _delete_all(keys: list) -> None:
+    with clients.table().batch_writer() as batch:
+        for key in keys:
+            batch.delete_item(Key={"pk": key["pk"], "sk": key["sk"]})
+
+
+def delete_ask(user: str, ask_id: str, deleted_at: str) -> None:
+    """Marks the ask deleted, then removes it. Deleting a missing ask still leaves the mark (adr/0009)."""
+    stored = get_ask(user, ask_id)
+    mark_deleted(user, "ask", ask_id, deleted_at, ride_id=(stored or {}).get("rideId"))
+    clients.table().delete_item(Key=ask_key(user, ask_id))
+
+
+def delete_note(user: str, ride_id: str, note_id: str, deleted_at: str) -> None:
+    mark_deleted(user, "note", note_id, deleted_at, ride_id=ride_id)
+    clients.table().delete_item(Key=note_key(user, ride_id, note_id))
+
+
+def delete_ride(user: str, ride_id: str, deleted_at: str) -> dict:
+    """Marks the ride deleted, then removes it with its route, its notes and its asks, marking each note and ask too.
+    The ride's mark goes first: from then on no note or chunk of it can be written, so the query below sees them all."""
+    mark_deleted(user, "ride", ride_id, deleted_at)
+    under = _query_keys(user, f"RIDE#{ride_id}")
+    notes = [k for k in under if "#NOTE#" in k["sk"]]
+    asks = _query_keys(user, "ASK#", ride_id=ride_id)
+    for key in notes:
+        mark_deleted(user, "note", key["sk"].rsplit("#", 1)[1], deleted_at, ride_id=ride_id)
+    for key in asks:
+        mark_deleted(user, "ask", key["sk"].split("#", 1)[1], deleted_at, ride_id=ride_id)
+    _delete_all(under + asks)
+    return {"notes": len(notes), "asks": len(asks), "chunks": sum("#ROUTE#" in k["sk"] for k in under)}
EOF
```

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `206 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/store.py src/handlers/rides.py src/handlers/ask_edit.py tests/test_deletes.py
git commit -m "feat: delete asks, point memos and rides, leaving deletion marks"
```

---

### Task 5: 文字起こしだけの依頼（UC-6）

**Files:**
- Modify: `src/lib/request.py`・`src/lib/store.py`・`src/handlers/worker.py`
- Create: `src/handlers/transcriptions.py`
- Test: `tests/test_transcriptions.py`（新規。`tests/test_worker.py` の `Recorder` を使う）

**Interfaces:**
- Consumes: 既存の `worker._take_audio`・`worker.Steps`・`clients.s3`・`clients.sqs`
- Produces:
  - `request.pcm_audio(audio_b64) -> bytes`（`parse_ask` から切り出す）・`request.parse_transcription(event) -> bytes`
  - `store.transcription_key`・`store.create_transcription`・`store.claim_transcription`・`store.finish_transcription`・`store.get_transcription`（`claim_ask` と共通の `store._claim(key)`）
  - `handlers.transcriptions.handler`（`POST` は 202 `{transcriptionId}`、`GET` は `{transcriptionId, status, text, failure}`）
  - SQS のメッセージ `{"kind": "transcription", "userName", "transcriptionId"}`。`kind` の無いメッセージは今までどおり質問
  - `worker.process_transcription(user, transcription_id, steps) -> None`

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_transcriptions.py b/tests/test_transcriptions.py
new file mode 100644
index 0000000..2f025b6
--- /dev/null
+++ b/tests/test_transcriptions.py
@@ -0,0 +1,109 @@
+"""Tests for POST /transcriptions, GET /transcriptions/{transcriptionId} and the worker's part (moto)."""
+import base64
+import json
+
+from handlers import transcriptions, worker
+from handlers.common import parse_iso
+from lib import store
+from lib.request import MAX_AUDIO_BYTES, MIN_AUDIO_BYTES
+from test_worker import Recorder
+
+USER = "rider01"
+AUDIO = b"\x00\x00" * (MIN_AUDIO_BYTES // 2 * 4)
+
+
+def post(body, user=USER):
+    return transcriptions.handler({"httpMethod": "POST", "headers": {"x-user-name": user}, "body": json.dumps(body)}, None)
+
+
+def get(transcription_id, user=USER):
+    event = {"httpMethod": "GET", "headers": {"x-user-name": user}, "pathParameters": {"transcriptionId": transcription_id}}
+    return transcriptions.handler(event, None)
+
+
+def accepted(aws, audio=AUDIO):
+    result = post({"audio": base64.b64encode(audio).decode()})
+    assert result["statusCode"] == 202
+    return json.loads(result["body"])["transcriptionId"]
+
+
+def messages(aws):
+    got = aws.sqs.receive_message(QueueUrl=aws.queue_url, MaxNumberOfMessages=10).get("Messages", [])
+    return [json.loads(m["Body"]) for m in got]
+
+
+def audio_keys(aws):
+    return [o["Key"] for o in aws.s3.list_objects_v2(Bucket=aws.bucket, Prefix="audio/").get("Contents", [])]
+
+
+def test_a_recording_is_accepted_queued_and_kept_for_a_day(aws):
+    transcription_id = accepted(aws)
+    item = store.get_transcription(USER, transcription_id)
+    assert item["status"] == "pending" and item["audioKey"] == f"audio/{transcription_id}.pcm"
+    assert item["expiresAt"] - int(parse_iso(item["receivedAt"]).timestamp()) == 86400
+    assert audio_keys(aws) == [f"audio/{transcription_id}.pcm"]
+    assert messages(aws) == [{"kind": "transcription", "userName": USER, "transcriptionId": transcription_id}]
+
+
+def test_while_it_waits_it_is_processing(aws):
+    transcription_id = accepted(aws)
+    body = json.loads(get(transcription_id)["body"])
+    assert body == {"transcriptionId": transcription_id, "status": "processing", "text": None, "failure": None}
+
+
+def test_the_worker_turns_it_into_text_without_the_agent_and_drops_the_audio(aws):
+    transcription_id = accepted(aws)
+    rec = Recorder(transcript="道の駅の先に眺めのいい駐車場")
+    worker.process_transcription(USER, transcription_id, rec.steps())
+    assert [c[0] for c in rec.calls] == ["transcribe"]
+    assert json.loads(get(transcription_id)["body"]) == {"transcriptionId": transcription_id, "status": "done",
+                                                         "text": "道の駅の先に眺めのいい駐車場", "failure": None}
+    assert audio_keys(aws) == []
+
+
+def test_silence_is_no_speech(aws):
+    transcription_id = accepted(aws)
+    worker.process_transcription(USER, transcription_id, Recorder(transcript="").steps())
+    body = json.loads(get(transcription_id)["body"])
+    assert body["status"] == "failed" and body["failure"] == "no_speech" and body["text"] is None
+
+
+def test_a_failed_transcription_is_reported_and_drops_the_audio(aws):
+    transcription_id = accepted(aws)
+    worker.process_transcription(USER, transcription_id, Recorder(stt_error=RuntimeError("stream broke")).steps())
+    body = json.loads(get(transcription_id)["body"])
+    assert body["status"] == "failed" and body["failure"] == "transcribe_failed"
+    assert audio_keys(aws) == []
+
+
+def test_a_second_delivery_does_nothing(aws):
+    transcription_id = accepted(aws)
+    rec = Recorder()
+    worker.process_transcription(USER, transcription_id, rec.steps())
+    worker.process_transcription(USER, transcription_id, rec.steps())
+    assert [c[0] for c in rec.calls] == ["transcribe"]
+
+
+def test_the_worker_handler_tells_a_transcription_from_an_ask(aws, monkeypatch):
+    transcription_id = accepted(aws)
+    rec = Recorder(transcript="メモ")
+    monkeypatch.setattr(worker, "DEFAULT_STEPS", rec.steps())
+    body = json.dumps({"kind": "transcription", "userName": USER, "transcriptionId": transcription_id})
+    worker.handler({"Records": [{"body": body}]}, None)
+    assert store.get_transcription(USER, transcription_id)["text"] == "メモ"
+
+
+def test_unknown_or_another_users_transcription_is_404(aws):
+    transcription_id = accepted(aws)
+    assert get(transcription_id, user="someone")["statusCode"] == 404
+    assert get("00000000-0000-4000-8000-000000000000")["statusCode"] == 404
+    assert get("not-a-uuid")["statusCode"] == 404
+
+
+def test_bad_audio_is_400_and_queues_nothing(aws):
+    for body in ({}, {"audio": "@@@"}, {"audio": base64.b64encode(b"\x00" * (MIN_AUDIO_BYTES - 2)).decode()},
+                 {"audio": base64.b64encode(b"\x00" * (MAX_AUDIO_BYTES + 2)).decode()}, {"text": "文字は受けない"}):
+        result = post(body)
+        assert result["statusCode"] == 400 and json.loads(result["body"])["error"] == "bad_request"
+    assert messages(aws) == [] and audio_keys(aws) == []
+    assert post({"audio": base64.b64encode(AUDIO).decode()}, user="BAD")["statusCode"] == 400
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_transcriptions.py 2>&1 | tail -1`
Expected: `1 error`（`handlers.transcriptions` が無い）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/src/handlers/transcriptions.py b/src/handlers/transcriptions.py
new file mode 100644
index 0000000..4e1770b
--- /dev/null
+++ b/src/handlers/transcriptions.py
@@ -0,0 +1,54 @@
+"""POST /transcriptions and GET /transcriptions/{transcriptionId}: turn a point memo's recording into text, without
+the agent (07 UC-6, slice 3 spec §6.2). Accepted and polled like an ask; the worker does the work."""
+from __future__ import annotations
+
+import json
+import os
+import uuid
+from datetime import timedelta
+
+from handlers.common import iso, log, response, utc_now
+from lib import clients, store
+from lib.request import UUID_RE, BadRequest, parse_transcription, user_name
+
+KEEP_SECONDS = 24 * 60 * 60  # the record of a transcription is only needed while the app polls (DynamoDB TTL)
+_STATUS = {"pending": "processing", "processing": "processing", "done": "done", "failed": "failed"}
+
+
+def handler(event, context):
+    try:
+        user = user_name(event)
+        if event.get("httpMethod") == "GET":
+            return _get(event, user)
+        return _accept(event, user)
+    except BadRequest as error:
+        return response(400, {"error": "bad_request", "message": str(error)})
+
+
+def _accept(event: dict, user: str) -> dict:
+    audio = parse_transcription(event)
+    now = utc_now()
+    transcription_id = str(uuid.uuid4())
+    audio_key = f"audio/{transcription_id}.pcm"
+    clients.s3().put_object(Bucket=os.environ["AUDIO_BUCKET"], Key=audio_key, Body=audio, ContentType="application/octet-stream")
+    store.create_transcription({
+        **store.transcription_key(user, transcription_id),
+        "transcriptionId": transcription_id,
+        "status": "pending",
+        "receivedAt": iso(now),
+        "audioKey": audio_key,
+        "expiresAt": int((now + timedelta(seconds=KEEP_SECONDS)).timestamp()),
+    })
+    clients.sqs().send_message(QueueUrl=os.environ["QUEUE_URL"], MessageBody=json.dumps(
+        {"kind": "transcription", "userName": user, "transcriptionId": transcription_id}))
+    log({"event": "transcription_accepted", "transcriptionId": transcription_id, "audioBytes": len(audio)})
+    return response(202, {"transcriptionId": transcription_id})
+
+
+def _get(event: dict, user: str) -> dict:
+    transcription_id = (event.get("pathParameters") or {}).get("transcriptionId") or ""
+    item = store.get_transcription(user, transcription_id) if UUID_RE.match(transcription_id) else None
+    if item is None:
+        return response(404, {"error": "not_found"})
+    return response(200, {"transcriptionId": transcription_id, "status": _STATUS.get(item.get("status"), "processing"),
+                          "text": item.get("text"), "failure": item.get("failure")})
diff --git a/src/handlers/worker.py b/src/handlers/worker.py
index b8d52ee..ff12429 100644
--- a/src/handlers/worker.py
+++ b/src/handlers/worker.py
@@ -1,4 +1,5 @@
-"""SQS worker: transcribe -> settle facts -> agent -> speech, one ask at a time (spec §6.2)."""
+"""SQS worker: transcribe -> settle facts -> agent -> speech, one ask at a time (spec §6.2). A point memo's recording
+is only transcribed (07 UC-6)."""
 from __future__ import annotations
 
 import json
@@ -127,7 +128,26 @@ def _run(user: str, ask_id: str, item: dict, steps: Steps) -> None:
     finish("completed", None, answerAudioKey=key, **answered)
 
 
+def process_transcription(user: str, transcription_id: str, steps: Steps) -> None:
+    item = store.claim_transcription(user, transcription_id)
+    if item is None:
+        log({"event": "transcription_skipped", "transcriptionId": transcription_id})
+        return
+    try:
+        text = steps.transcribe(_take_audio(item["audioKey"]))
+    except Exception as error:  # noqa: BLE001 - reported as transcribe_failed
+        log({"event": "transcribe_error", "transcriptionId": transcription_id, "error": type(error).__name__})
+        store.finish_transcription(user, transcription_id, {"status": "failed", "failure": "transcribe_failed"})
+        return
+    fields = {"status": "done", "text": text} if text else {"status": "failed", "failure": "no_speech"}
+    store.finish_transcription(user, transcription_id, fields)
+    log({"event": "transcription_done", "transcriptionId": transcription_id, "status": fields["status"]})
+
+
 def handler(event, context):
     for record in event.get("Records", []):
         message = json.loads(record["body"])
-        process(message["userName"], message["askId"], DEFAULT_STEPS)
+        if message.get("kind") == "transcription":
+            process_transcription(message["userName"], message["transcriptionId"], DEFAULT_STEPS)
+        else:
+            process(message["userName"], message["askId"], DEFAULT_STEPS)
diff --git a/src/lib/request.py b/src/lib/request.py
index a3467f5..2747462 100644
--- a/src/lib/request.py
+++ b/src/lib/request.py
@@ -1,4 +1,4 @@
-"""Validation of the App's requests (07 UC-4, UC-5)."""
+"""Validation of the App's requests (07 UC-4, UC-5, UC-6)."""
 from __future__ import annotations
 
 import base64
@@ -100,22 +100,34 @@ def body_json(event: dict) -> dict:
     return data
 
 
+def pcm_audio(audio_b64: Any) -> bytes:
+    """0.25-60 seconds of 16 kHz mono 16-bit PCM, sent as base64 (adr/0002)."""
+    if not isinstance(audio_b64, str):
+        raise BadRequest("audio must be base64")
+    try:
+        audio = base64.b64decode(audio_b64, validate=True)
+    except (binascii.Error, ValueError):
+        raise BadRequest("audio must be base64") from None
+    if not MIN_AUDIO_BYTES <= len(audio) <= MAX_AUDIO_BYTES or len(audio) % 2:
+        raise BadRequest("audio must be 0.25-60 seconds of 16 kHz mono 16-bit PCM")
+    return audio
+
+
+def parse_transcription(event: dict) -> bytes:
+    """POST /transcriptions: the recording of a point memo, to be turned into text only (07 UC-6)."""
+    audio_b64 = body_json(event).get("audio")
+    if audio_b64 is None:
+        raise BadRequest("audio is required")
+    return pcm_audio(audio_b64)
+
+
 def parse_ask(event: dict) -> AskInput:
     data = body_json(event)
     audio_b64, text = data.get("audio"), data.get("text")
     if (audio_b64 is None) == (text is None):
         raise BadRequest("exactly one of audio and text is required")
 
-    audio = None
-    if audio_b64 is not None:
-        if not isinstance(audio_b64, str):
-            raise BadRequest("audio must be base64")
-        try:
-            audio = base64.b64decode(audio_b64, validate=True)
-        except (binascii.Error, ValueError):
-            raise BadRequest("audio must be base64") from None
-        if not MIN_AUDIO_BYTES <= len(audio) <= MAX_AUDIO_BYTES or len(audio) % 2:
-            raise BadRequest("audio must be 0.25-60 seconds of 16 kHz mono 16-bit PCM")
+    audio = pcm_audio(audio_b64) if audio_b64 is not None else None
 
     if text is not None:
         if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
diff --git a/src/lib/store.py b/src/lib/store.py
index b16f980..ef71b02 100644
--- a/src/lib/store.py
+++ b/src/lib/store.py
@@ -99,9 +99,13 @@ def create_ask(item: dict) -> None:
 
 def claim_ask(user: str, ask_id: str) -> Optional[dict]:
     """pending -> processing, once. None if already claimed or missing."""
+    return _claim(ask_key(user, ask_id))
+
+
+def _claim(key: dict) -> Optional[dict]:
     try:
         result = clients.table().update_item(
-            Key=ask_key(user, ask_id),
+            Key=key,
             UpdateExpression="SET #s = :processing",
             ConditionExpression="#s = :pending",
             ExpressionAttributeNames={"#s": "status"},
@@ -245,3 +249,32 @@ def delete_ride(user: str, ride_id: str, deleted_at: str) -> dict:
         mark_deleted(user, "ask", key["sk"].split("#", 1)[1], deleted_at, ride_id=ride_id)
     _delete_all(under + asks)
     return {"notes": len(notes), "asks": len(asks), "chunks": sum("#ROUTE#" in k["sk"] for k in under)}
+
+
+def transcription_key(user: str, transcription_id: str) -> dict:
+    return {"pk": f"USER#{user}", "sk": f"TRANSCRIPTION#{transcription_id}"}
+
+
+def create_transcription(item: dict) -> None:
+    clients.table().put_item(Item=_to_item(item))
+
+
+def claim_transcription(user: str, transcription_id: str) -> Optional[dict]:
+    """pending -> processing, once. None if already claimed or missing."""
+    return _claim(transcription_key(user, transcription_id))
+
+
+def finish_transcription(user: str, transcription_id: str, fields: dict) -> None:
+    values = _to_item(fields)
+    names = {f"#k{i}": key for i, key in enumerate(values)}
+    clients.table().update_item(
+        Key=transcription_key(user, transcription_id),
+        UpdateExpression="SET " + ", ".join(f"#k{i} = :v{i}" for i in range(len(values))),
+        ExpressionAttributeNames=names,
+        ExpressionAttributeValues={f":v{i}": value for i, value in enumerate(values.values())},
+    )
+
+
+def get_transcription(user: str, transcription_id: str) -> Optional[dict]:
+    item = clients.table().get_item(Key=transcription_key(user, transcription_id)).get("Item")
+    return _from_item(item) if item else None
EOF
```

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `215 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/request.py src/lib/store.py src/handlers/transcriptions.py src/handlers/worker.py tests/test_transcriptions.py
git commit -m "feat: turn a point memo's recording into text without the agent"
```

---

### Task 6: テンプレートと API の正本

**Files:**
- Modify: `openapi.yaml`・`template.yaml`
- Test: `tests/test_openapi.py`

**Interfaces:**
- Consumes: Task 2〜5 の受け口と、`rides.MEMO_MAX`・`notes.NOTE_TEXT_MAX`
- Produces: Lambda `lambda-trv2-dev-ask-edit`・`lambda-trv2-dev-transcriptions`、走行の Lambda の5つの経路、テーブルの TTL（`expiresAt`）。Task 8 のデプロイが使う

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $BE && git apply <<'EOF'
diff --git a/tests/test_openapi.py b/tests/test_openapi.py
index 82edacf..111ff3c 100644
--- a/tests/test_openapi.py
+++ b/tests/test_openapi.py
@@ -12,11 +12,30 @@ def test_is_valid_openapi():
 
 
 def test_routes():
-    assert set(SPEC["paths"]) == {"/health", "/asks", "/asks/{askId}", "/rides/{rideId}", "/rides/{rideId}/route/{seq}"}
-    assert set(SPEC["paths"]["/asks"]) == {"post"}
-    assert set(SPEC["paths"]["/asks/{askId}"]) == {"get"}
-    assert set(SPEC["paths"]["/rides/{rideId}"]) == {"put"}
-    assert set(SPEC["paths"]["/rides/{rideId}/route/{seq}"]) == {"put"}
+    assert {path: set(methods) for path, methods in SPEC["paths"].items()} == {
+        "/health": {"get"},
+        "/asks": {"post"},
+        "/asks/{askId}": {"get", "delete"},
+        "/asks/{askId}/memo": {"put"},
+        "/rides/{rideId}": {"put", "delete"},
+        "/rides/{rideId}/route/{seq}": {"put"},
+        "/rides/{rideId}/notes/{noteId}": {"put", "delete"},
+        "/transcriptions": {"post"},
+        "/transcriptions/{transcriptionId}": {"get"},
+    }
+
+
+def test_the_memo_and_note_limits_match_the_validation():
+    from lib import notes, rides
+    schemas = SPEC["components"]["schemas"]
+    assert schemas["RideRequest"]["properties"]["memo"]["maxLength"] == rides.MEMO_MAX
+    assert schemas["AskMemoRequest"]["properties"]["memo"]["maxLength"] == rides.MEMO_MAX
+    assert schemas["NoteRequest"]["properties"]["text"]["maxLength"] == notes.NOTE_TEXT_MAX
+
+
+def test_transcription_failures_match_the_worker():
+    failures = SPEC["components"]["schemas"]["TranscriptionResult"]["properties"]["failure"]["enum"]
+    assert set(failures) - {None} == {"no_speech", "transcribe_failed"}
 
 
 def test_the_ride_limits_match_the_validation():
EOF
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_openapi.py 2>&1 | tail -1`
Expected: `3 failed, 3 passed`（経路・上限・失敗の理由が openapi に無い）

- [ ] **Step 3: 実装する**

```bash
cd $BE && git apply <<'EOF'
diff --git a/openapi.yaml b/openapi.yaml
index 50f5f25..251cd1f 100644
--- a/openapi.yaml
+++ b/openapi.yaml
@@ -3,7 +3,7 @@ info:
   title: TouringProjectV2 Backend API
   version: 1.0.0
   description: >
-    App ↔ Backend の約束の正本（親リポジトリ docs/07_units_contracts.md UC-4・UC-5）。
+    App ↔ Backend の約束の正本（親リポジトリ docs/07_units_contracts.md UC-4〜UC-7）。
     /health 以外は x-api-key（接続キー）と x-user-name（英小文字と数字の3〜20文字）が要る。
 servers:
   - url: https://{apiId}.execute-api.ap-northeast-1.amazonaws.com/Prod
@@ -84,12 +84,67 @@ paths:
                   error:
                     type: string
                     enum: [not_found]
+    delete:
+      summary: 質問を消し、削除の跡を残す（何度呼んでも、無い質問でも 204）
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+        - $ref: "#/components/parameters/AskId"
+      responses:
+        "204":
+          description: 消した
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
+  /asks/{askId}/memo:
+    put:
+      summary: 会話のメモを置く（memo が null なら消す）
+      description: updatedAt が保存済みの memoUpdatedAt より新しいときだけ書く。古ければ何もせず 200（applied は false）。
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+        - $ref: "#/components/parameters/AskId"
+      requestBody:
+        required: true
+        content:
+          application/json:
+            schema:
+              $ref: "#/components/schemas/AskMemoRequest"
+      responses:
+        "200":
+          description: 受け取った（書いたか、古いので何もしなかったか）
+          content:
+            application/json:
+              schema:
+                type: object
+                required: [askId, applied]
+                properties:
+                  askId:
+                    type: string
+                    format: uuid
+                  applied:
+                    type: boolean
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
+        "404":
+          description: 質問が無い（他のユーザーの質問も無いものとして扱う）
+          content:
+            application/json:
+              schema:
+                type: object
+                properties:
+                  error:
+                    type: string
+                    enum: [not_found]
+        "410":
+          $ref: "#/components/responses/Deleted"
   /rides/{rideId}:
     put:
-      summary: 走行のメタ情報を置く（状態・名前・区間が変わるたびに、最新の全体を送る）
+      summary: 走行のメタ情報を置く（状態・名前・区間・メモが変わるたびに、最新の全体を送る）
       description: >
         updatedAt が保存済みのものより新しいときだけ上書きする。古ければ何もせず 200（applied は false）。
-        読み出しはスライス3で足す。
+        削除の跡がある走行は書かずに 410。読み出しは後のスライスで足す。
       parameters:
         - $ref: "#/components/parameters/UserName"
         - $ref: "#/components/parameters/RideId"
@@ -117,9 +172,24 @@ paths:
           $ref: "#/components/responses/BadRequest"
         "403":
           description: 接続キーが無効
+        "410":
+          $ref: "#/components/responses/Deleted"
+    delete:
+      summary: 走行を消し、削除の跡を残す（ルート・地点メモ・その走行の質問も消し、地点メモと質問にも跡を残す）
+      description: 何度呼んでも、無い走行でも 204。
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+        - $ref: "#/components/parameters/RideId"
+      responses:
+        "204":
+          description: 消した
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
   /rides/{rideId}/route/{seq}:
     put:
-      summary: ルートの点のかたまりを置く（同じ seq は丸ごと上書き）
+      summary: ルートの点のかたまりを置く（同じ seq は丸ごと上書き。削除の跡がある走行は 410）
       parameters:
         - $ref: "#/components/parameters/UserName"
         - $ref: "#/components/parameters/RideId"
@@ -154,6 +224,112 @@ paths:
           $ref: "#/components/responses/BadRequest"
         "403":
           description: 接続キーが無効
+        "410":
+          $ref: "#/components/responses/Deleted"
+  /rides/{rideId}/notes/{noteId}:
+    put:
+      summary: 地点メモを置く（最新の全体を送る）
+      description: >
+        updatedAt が保存済みのものより新しいときだけ書く。古ければ何もせず 200（applied は false）で、保存済みの住所と方位を返す。
+        住所（町名まで）と方位は最初に受けたときに Backend が決め、あとの PUT では変えない（住所を確定できなかったときは次の PUT で求め直す）。
+        地点メモか走行に削除の跡があれば、書かずに 410。走行のメタ情報より先に届いてもよい。
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+        - $ref: "#/components/parameters/RideId"
+        - $ref: "#/components/parameters/NoteId"
+      requestBody:
+        required: true
+        content:
+          application/json:
+            schema:
+              $ref: "#/components/schemas/NoteRequest"
+      responses:
+        "200":
+          description: 受け取った（書いたか、古いので何もしなかったか）
+          content:
+            application/json:
+              schema:
+                $ref: "#/components/schemas/NoteSaved"
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
+        "410":
+          $ref: "#/components/responses/Deleted"
+    delete:
+      summary: 地点メモを消し、削除の跡を残す（何度呼んでも、無い地点メモでも 204）
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+        - $ref: "#/components/parameters/RideId"
+        - $ref: "#/components/parameters/NoteId"
+      responses:
+        "204":
+          description: 消した
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
+  /transcriptions:
+    post:
+      summary: 地点メモの声を文字にするだけの依頼を受け付ける（AI は呼ばない。結果は GET /transcriptions/{transcriptionId}）
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+      requestBody:
+        required: true
+        content:
+          application/json:
+            schema:
+              $ref: "#/components/schemas/TranscriptionRequest"
+      responses:
+        "202":
+          description: 受け付けた
+          content:
+            application/json:
+              schema:
+                type: object
+                required: [transcriptionId]
+                properties:
+                  transcriptionId:
+                    type: string
+                    format: uuid
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
+        "429":
+          description: 流量の制限
+  /transcriptions/{transcriptionId}:
+    get:
+      summary: 文字起こしの状態と結果（受け付けてから1日で消える）
+      parameters:
+        - $ref: "#/components/parameters/UserName"
+        - name: transcriptionId
+          in: path
+          required: true
+          schema:
+            type: string
+            format: uuid
+      responses:
+        "200":
+          description: 状態
+          content:
+            application/json:
+              schema:
+                $ref: "#/components/schemas/TranscriptionResult"
+        "400":
+          $ref: "#/components/responses/BadRequest"
+        "403":
+          description: 接続キーが無効
+        "404":
+          description: 無い（他のユーザーのもの・1日を過ぎたものも無いものとして扱う）
+          content:
+            application/json:
+              schema:
+                type: object
+                properties:
+                  error:
+                    type: string
+                    enum: [not_found]
 components:
   securitySchemes:
     ApiKey:
@@ -176,7 +352,34 @@ components:
       schema:
         type: string
         format: uuid
+    NoteId:
+      name: noteId
+      in: path
+      required: true
+      description: Android が作る UUID（小文字）
+      schema:
+        type: string
+        format: uuid
+    AskId:
+      name: askId
+      in: path
+      required: true
+      description: Backend が質問を受け付けたときに返した UUID（小文字）
+      schema:
+        type: string
+        format: uuid
   responses:
+    Deleted:
+      description: 削除の跡がある（記録か、その走行が消されている）。書かなかった。App は送れたものとして扱い、送り直さない
+      content:
+        application/json:
+          schema:
+            type: object
+            required: [error]
+            properties:
+              error:
+                type: string
+                enum: [deleted]
     BadRequest:
       description: 入力が不正
       content:
@@ -346,6 +549,100 @@ components:
           description: >
             Android が変更した時刻（タイムゾーン付き）。ミリ秒まで比べ、それより細かい部分は切り捨てる。
             保存済みと同じミリ秒の版は新しいとみなさない（Android は端末のミリ秒の時刻を送るので、それより細かい差は来ない）。
+        memo:
+          type: string
+          maxLength: 2000
+          nullable: true
+          description: 走行のメモ。null・省略・空白だけは「メモ無し」（保存済みのメモも消える）。前後の空白は落とす
+    AskMemoRequest:
+      type: object
+      required: [memo, updatedAt]
+      properties:
+        memo:
+          type: string
+          maxLength: 2000
+          nullable: true
+          description: 会話のメモ。null・空白だけなら消す。前後の空白は落とす
+        updatedAt:
+          type: string
+          format: date-time
+          description: Android がメモを変えた時刻（タイムゾーン付き。ミリ秒まで比べる）
+    NoteRequest:
+      type: object
+      required: [at, text, updatedAt]
+      properties:
+        at:
+          type: string
+          format: date-time
+          description: 地点メモを開いた時刻（タイムゾーン付き）
+        location:
+          allOf:
+            - $ref: "#/components/schemas/Point"
+          nullable: true
+          description: 開いたときの位置。まだ位置が無ければ null。不正な位置は 400
+        headingSample:
+          nullable: true
+          description: 方位の材料（質問と同じ）。at より2分以上古いものは使わない。不正なものは無いものとして扱う
+          allOf:
+            - $ref: "#/components/schemas/Point"
+            - type: object
+              required: [at]
+              properties:
+                at:
+                  type: string
+                  format: date-time
+        text:
+          type: string
+          minLength: 1
+          maxLength: 2000
+          description: 本文。空白だけは 400。前後の空白は落とす
+        updatedAt:
+          type: string
+          format: date-time
+          description: Android が地点メモを変えた時刻（タイムゾーン付き。ミリ秒まで比べる）
+    NoteSaved:
+      type: object
+      required: [noteId, applied, address, headingDegrees]
+      properties:
+        noteId:
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
+    TranscriptionRequest:
+      type: object
+      required: [audio]
+      properties:
+        audio:
+          type: string
+          format: byte
+          description: PCM（16kHz・モノラル・16bit リトルエンディアン）の base64。0.25〜60秒。文字にしたら消す
+    TranscriptionResult:
+      type: object
+      required: [transcriptionId, status, text, failure]
+      properties:
+        transcriptionId:
+          type: string
+          format: uuid
+        status:
+          type: string
+          enum: [processing, done, failed]
+        text:
+          type: string
+          nullable: true
+          description: 聞き取った文（done のときだけ）
+        failure:
+          type: string
+          nullable: true
+          enum: [no_speech, transcribe_failed, null]
     RouteChunk:
       type: object
       required: [points]
diff --git a/template.yaml b/template.yaml
index 09e8257..3174304 100644
--- a/template.yaml
+++ b/template.yaml
@@ -1,6 +1,6 @@
 AWSTemplateFormatVersion: "2010-09-09"
 Transform: AWS::Serverless-2016-10-31
-Description: TouringProjectV2 backend - accept asks, process them through the agent, return answers, and keep rides.
+Description: TouringProjectV2 backend - accept asks, process them through the agent, return answers, and keep rides, memos and point memos.
 
 Parameters:
   Environment:
@@ -120,11 +120,17 @@ Resources:
     Properties:
       FunctionName: !Sub lambda-trv2-${Environment}-rides
       Handler: handlers.rides.handler
+      Environment:
+        Variables:
+          GEO_REGION: !Ref AWS::Region
       Policies:
+        # Writes check deletion marks in a transaction; deleting a ride reads and removes its records (slice 3 spec §6).
+        - DynamoDBCrudPolicy:
+            TableName: !Ref RecordsTable
         - Statement:
             - Effect: Allow
-              Action: dynamodb:PutItem
-              Resource: !GetAtt RecordsTable.Arn
+              Action: geo-places:ReverseGeocode
+              Resource: "*"
       Events:
         Ride:
           Type: Api
@@ -138,6 +144,79 @@ Resources:
             RestApiId: !Ref RestApi
             Path: /rides/{rideId}/route/{seq}
             Method: put
+        RideDelete:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /rides/{rideId}
+            Method: delete
+        Note:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /rides/{rideId}/notes/{noteId}
+            Method: put
+        NoteDelete:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /rides/{rideId}/notes/{noteId}
+            Method: delete
+
+  AskEditFunction:
+    Type: AWS::Serverless::Function
+    Properties:
+      FunctionName: !Sub lambda-trv2-${Environment}-ask-edit
+      Handler: handlers.ask_edit.handler
+      Policies:
+        - DynamoDBCrudPolicy:
+            TableName: !Ref RecordsTable
+      Events:
+        Memo:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /asks/{askId}/memo
+            Method: put
+        AskDelete:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /asks/{askId}
+            Method: delete
+
+  TranscriptionsFunction:
+    Type: AWS::Serverless::Function
+    Properties:
+      FunctionName: !Sub lambda-trv2-${Environment}-transcriptions
+      Handler: handlers.transcriptions.handler
+      MemorySize: 512
+      Timeout: 15
+      Environment:
+        Variables:
+          QUEUE_URL: !Ref AskQueue
+      Policies:
+        - DynamoDBCrudPolicy:
+            TableName: !Ref RecordsTable
+        - SQSSendMessagePolicy:
+            QueueName: !GetAtt AskQueue.QueueName
+        - Statement:
+            - Effect: Allow
+              Action: s3:PutObject
+              Resource: !Sub ${AudioBucket.Arn}/audio/*
+      Events:
+        Accept:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /transcriptions
+            Method: post
+        Result:
+          Type: Api
+          Properties:
+            RestApiId: !Ref RestApi
+            Path: /transcriptions/{transcriptionId}
+            Method: get
 
   WorkerFunction:
     Type: AWS::Serverless::Function
@@ -216,6 +295,10 @@ Resources:
           KeyType: RANGE
       PointInTimeRecoverySpecification:
         PointInTimeRecoveryEnabled: true
+      # Only transcriptions carry expiresAt; they are needed while the app polls (slice 3 spec §6.1).
+      TimeToLiveSpecification:
+        AttributeName: expiresAt
+        Enabled: true
 
   AudioBucket:
     Type: AWS::S3::Bucket
EOF
```

- [ ] **Step 4: 全体が通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -1`
Expected: `217 passed`

`cd $BE && sam validate --lint 2>&1 | tail -1` も回す。Expected: `... is a valid SAM Template`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add openapi.yaml template.yaml tests/test_openapi.py
git commit -m "feat: route the memo, point memo, deletion and transcription endpoints"
```

---

### Task 7: 文書

**Files:**
- Modify: 親の `docs/07_units_contracts.md`、`Backend/README.md`・`Backend/docs-parent/`（写し）

- [ ] **Step 1: 07 の UC-6・UC-7 を直す**

```bash
cd $ROOT && git apply <<'EOF'
diff --git a/docs/07_units_contracts.md b/docs/07_units_contracts.md
index 5dba958..009cad7 100644
--- a/docs/07_units_contracts.md
+++ b/docs/07_units_contracts.md
@@ -110,8 +110,10 @@
 地点メモを声で書くときに使う。
 
 - Android は音声を送り、Backend は聞き取った文だけを返す。AI は呼ばない。
-- 受け付けと受け取りの形は UC-5 と同じ（非同期）。
-- 音声は文字にしたら消す。記録には残さない。
+- 受け付けと受け取りの形は UC-5 と同じ（非同期）。項目の名前と型の正本は Backend の `openapi.yaml`。`POST /transcriptions` で受け付け（202）、`GET /transcriptions/{transcriptionId}` で取りに行く。
+- 音声の形と長さは、質問の音声と同じ（UC-5「送るもの」）。
+- 状態は「処理中」「完了」「失敗」の3つ。完了なら聞き取った文、失敗なら理由（`no_speech`（聞き取れた文が空）・`transcribe_failed`）を返す。取りに行く間隔と打ち切りは UC-5 と同じ。
+- 音声は文字にしたら消す。記録には残さない。結果は受け付けてから1日で消える。
 
 ## UC-7 Android ↔ Backend: 記録の同期
 
@@ -131,11 +133,19 @@
 
 ### 走行の送り方（スライス2の暫定）
 
-- 走行のメタ情報（名前・状態・記録した区間・自動終了したか・Android が変更した時刻）は、変わるたびに最新の全体を置く。Backend は、Android が変更した時刻が保存済みのものより新しいときだけ上書きし、古ければ何もせずに受け取ったと返す。端末が1台だけのスライス2ではこれで足りる。端末をまたいだ突き合わせは [05_technical_policies.md](05_technical_policies.md) §9 で決める（スライス3）。
+- 走行のメタ情報（名前・状態・記録した区間・自動終了したか・走行のメモ・Android が変更した時刻）は、変わるたびに最新の全体を置く。Backend は、Android が変更した時刻が保存済みのものより新しいときだけ上書きし、古ければ何もせずに受け取ったと返す。端末が1台だけのあいだはこれで足りる。端末をまたいだ突き合わせは [05_technical_policies.md](05_technical_policies.md) §9 で決める（同期の仕上げのスライス）。
 - ルートの点は、300点までのかたまりに番号を付けて置く。同じ番号は丸ごと上書きする。かたまりは走行のメタ情報より先に届いてもよい。
 - かたまりの番号は、Android が走行の点を記録した順に300点ずつ区切った順番（0から）。記録中は満ちたかたまりだけを置き、一時停止と終了では満ちていない最後のかたまりも置く。あとで点が増えたら、同じ番号で置き直す。
 - 入力が不正（400）なものは送り直さない。
-- 読み出しはスライス3で足す。
+- 読み出しは後のスライスで足す。
+
+### 書き足しと削除の送り方（スライス3）
+
+- 会話のメモは質問ごとに、地点メモは1件ごとに、最新の全体を置く。どちらも、Android が変更した時刻が保存済みのものより新しいときだけ書き、古ければ何もせずに受け取ったと返す。会話のメモは、Backend に無い質問には置けない（無いものとして返す）。
+- 地点メモの住所（町名まで）と進行方位は、Backend が最初に受けたときに、質問と同じ求め方で決めて返す。あとから置き直しても変えない（住所を確定できなかったときは、次に置いたときに求め直す）。地点メモは、その走行のメタ情報より先に届いてもよい。
+- 削除は記録ごとに送る。Backend は先に削除の跡を残してから消す。走行を消すと、そのルート・地点メモ・質問も消え、地点メモと質問にも跡が残る。何度送っても、無いものを消しても、同じ結果になる。
+- 跡のある記録と、跡のある走行の下の記録（ルート・地点メモ）への書き込みは、書かずに「消されている」（410）と返す。Android は送れたものと同じに扱い、送り直さない（[adr/0009](../adr/0009-keep-deletion-marks-in-the-cloud.md)）。
+- 跡には期限が無い。端末をまたいで削除を伝えるのに使う（読み込みは後のスライス）。
 
 ## UC-8 Backend → Agent: 呼び出し
 
EOF
```

- [ ] **Step 2: Backend の README を直す**

```bash
cd $BE && git apply <<'EOF'
diff --git a/README.md b/README.md
index 736a76f..15be9d5 100644
--- a/README.md
+++ b/README.md
@@ -2,6 +2,7 @@
 
 TouringProjectV2 の API（API Gateway＋Lambda・Python・SAM・`ap-northeast-1`）。
 App から質問（PCM の音声か文字）と位置を受け付け、文字起こし・住所と方位の確定・Agent の呼び出し・読み上げ音声の生成を行い、結果を返す。
+走行・ルート・メモ・地点メモと、それらの削除を受け取り、ユーザー名ごとに置く。
 プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し。編集しない）。
 
 ## 構成
@@ -10,8 +11,8 @@ App から質問（PCM の音声か文字）と位置を受け付け、文字起
 |---|---|
 | `openapi.yaml` | App ↔ Backend の API 仕様（正本） |
 | `template.yaml`・`samconfig.toml` | SAM（スタック `stack-trv2-dev-backend`） |
-| `src/handlers/` | `health`・`ask`（`POST /asks`）・`result`（`GET /asks/{askId}`）・`worker`（SQS）・`rides`（`PUT /rides/{rideId}`・`PUT /rides/{rideId}/route/{seq}`） |
-| `src/lib/` | 入力の検証（質問は `request`・走行は `rides`）・方位・プロンプト・住所・記録・会話の時間・Agent・音声合成・文字起こし |
+| `src/handlers/` | `health`・`ask`（`POST /asks`）・`result`（`GET /asks/{askId}`）・`ask_edit`（`PUT /asks/{askId}/memo`・`DELETE /asks/{askId}`）・`worker`（SQS）・`rides`（`/rides/{rideId}` の `PUT`・`DELETE`、`PUT /rides/{rideId}/route/{seq}`、`/rides/{rideId}/notes/{noteId}` の `PUT`・`DELETE`）・`transcriptions`（`POST /transcriptions`・`GET /transcriptions/{transcriptionId}`） |
+| `src/lib/` | 入力の検証（質問と音声は `request`・走行とメモは `rides`・地点メモは `notes`）・方位・プロンプト・住所・記録（削除の跡を含む）・会話の時間・Agent・音声合成・文字起こし |
 | `scripts/smoke.py` | デプロイ後の通しの確認 |
 
 ## 流れ
@@ -19,7 +20,10 @@ App から質問（PCM の音声か文字）と位置を受け付け、文字起
 1. `POST /asks` が入力を検証し、録音を S3（`audio/`・1日で消える）に置き、記録を `pending` で作り、SQS に積む。会話を区切る時刻を SSM `/trv2/dev/conversation-reset-minutes`（既定15・55以下）から求めて返す。
 2. worker が受け持ちを獲得し（条件付き書き込み）、文字起こし（ストリーミング）→ 住所（Location Service）・方位・日時 → Agent（us-east-1・`runtimeSessionId` はユーザー名と会話の識別子から作る SHA-256）→ Polly（Kazuha・DRC と +6dB）の順に処理し、記録を `completed` か `failed` にする。
 3. App は `GET /asks/{askId}` をポーリングし、回答の文と音声の署名付き URL（10分有効）を受け取る。
-4. 走行: App は走行のメタ情報を `PUT /rides/{rideId}` で、ルートの点を300点までのかたまりにして `PUT /rides/{rideId}/route/{seq}` で置く。メタ情報は `updatedAt` が保存済みより新しいときだけ上書きする（古ければ `applied: false` の 200）。読み出しはスライス3。
+4. 走行: App は走行のメタ情報（走行のメモを含む）を `PUT /rides/{rideId}` で、ルートの点を300点までのかたまりにして `PUT /rides/{rideId}/route/{seq}` で置く。メタ情報は `updatedAt` が保存済みより新しいときだけ上書きする（古ければ `applied: false` の 200）。読み出しは後のスライス。
+5. メモと地点メモ: 会話のメモは `PUT /asks/{askId}/memo`、地点メモは `PUT /rides/{rideId}/notes/{noteId}` で置く。どちらも `updatedAt` が新しいときだけ書く。地点メモの住所と方位は、最初に受けたときに質問と同じ求め方で決めて返す。
+6. 削除: `DELETE` を受けると、先に削除の跡（`DELETED#<ASK|RIDE|NOTE>#<id>`・期限なし）を書いてから消す。走行を消すと、ルート・地点メモ・その走行の質問も消し、地点メモと質問にも跡を残す。跡のある記録（と、跡のある走行の下の記録）への `PUT` は、書き込みと跡の確かめを1つのトランザクションにして、書かずに 410 を返す。
+7. 地点メモの声: `POST /transcriptions` が録音を S3 に置いて SQS に積み、worker が文字起こしだけを行う（AI と読み上げは呼ばない）。App は `GET /transcriptions/{transcriptionId}` をポーリングする。記録は DynamoDB の TTL（`expiresAt`）で1日後に消える。
 
 ## テスト
 
EOF
```

- [ ] **Step 3: 親の文書をユニットに写す**

```bash
cd $ROOT && scripts/sync-docs.sh Backend
cd $BE && git status --short docs-parent/
```

Expected: `docs-parent/` の `01_requirements.md`・`02_screen_list.md`・`03_screen_transition.md`・`04_detailed_requirements.md`・`05_technical_policies.md`・`07_units_contracts.md`・`mock/index.html` が変わっている（07 のほかは、スライス2 plan 4b と、このスライスの spec のコミットで親を直した分が、まだ写されていなかったもの）

- [ ] **Step 4: コミット**

```bash
cd $ROOT && git add docs/07_units_contracts.md
git commit -m "docs: record the memo, point memo, deletion and transcription contracts"
cd $BE && git add README.md docs-parent/
git commit -m "docs: describe the memo, point memo, deletion and transcription endpoints"
cd $BE && env/bin/pytest -q 2>&1 | tail -1
```

Expected: 最後の行が `217 passed`

---

### Task 8: デプロイと通しの確認

**Files:**
- Modify: `scripts/smoke.py`

**Interfaces:**
- Consumes: Task 1〜6 の API。デプロイ済みのスタック `stack-trv2-dev-backend`（出力 `ApiUrl`・`ApiKeyId`）
- Produces: デプロイ済みの受け口。スライス3 plan 2〜4（Android）が使う

- [ ] **Step 1: smoke にメモ・地点メモ・文字起こし・削除を足す**

```bash
cd $BE && git apply <<'EOF'
diff --git a/scripts/smoke.py b/scripts/smoke.py
index 9194b78..eea98fd 100644
--- a/scripts/smoke.py
+++ b/scripts/smoke.py
@@ -1,4 +1,5 @@
 """End-to-end check of the deployed API. Positions are public landmarks only.
+Every ask is sent with the smoke ride, and the ride is deleted at the end, so a run leaves only deletion marks.
 
 Usage: AWS_PROFILE=touring env/bin/python scripts/smoke.py
 """
@@ -74,10 +75,14 @@ def minutes_ago(minutes: int) -> str:
     return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
 
 
+def smoke_ride() -> dict:
+    return {"name": "smoke", "status": "paused", "segments": [{"startedAt": minutes_ago(30), "endedAt": minutes_ago(10)}],
+            "autoEnded": False, "updatedAt": minutes_ago(10), "memo": "smoke の走行のメモ"}
+
+
 def ride_checks(api: str, key: str, ride_id: str) -> list[bool]:
     results = []
-    ride = {"name": "smoke", "status": "paused", "segments": [{"startedAt": minutes_ago(30), "endedAt": minutes_ago(10)}],
-            "autoEnded": False, "updatedAt": minutes_ago(10)}
+    ride = smoke_ride()
     status, body = request("PUT", f"{api}/rides/{ride_id}", key, USER, ride)
     results.append(check("ride saved", status == 200 and body == {"rideId": ride_id, "applied": True}, str(status)))
     status, body = request("PUT", f"{api}/rides/{ride_id}", key, USER, {**ride, "name": "older", "updatedAt": minutes_ago(20)})
@@ -93,6 +98,65 @@ def ride_checks(api: str, key: str, ride_id: str) -> list[bool]:
     return results
 
 
+def note_checks(api: str, key: str, ride_id: str, note_id: str) -> list[bool]:
+    results = []
+    note = {"at": minutes_ago(15), "location": TOKYO_STATION, "headingSample": {**SOUTH_60M, "at": minutes_ago(15)},
+            "text": "smoke の地点メモ", "updatedAt": minutes_ago(15)}
+    url = f"{api}/rides/{ride_id}/notes/{note_id}"
+    status, body = request("PUT", url, key, USER, note)
+    results.append(check("note saved with its place", status == 200 and body.get("applied") is True and bool(body.get("address")),
+                         f"{status} address={body.get('address')} heading={body.get('headingDegrees')}"))
+    status, body = request("PUT", url, key, USER, {**note, "text": "older", "updatedAt": minutes_ago(20)})
+    results.append(check("older note ignored", status == 200 and body.get("applied") is False and bool(body.get("address")), str(status)))
+    status, body = request("PUT", url, key, USER, {**note, "text": " "})
+    results.append(check("bad note is 400", status == 400 and body.get("error") == "bad_request", str(status)))
+    return results
+
+
+def memo_checks(api: str, key: str, ask_id: str) -> list[bool]:
+    url = f"{api}/asks/{ask_id}/memo"
+    status, body = request("PUT", url, key, USER, {"memo": "smoke の会話のメモ", "updatedAt": minutes_ago(1)})
+    results = [check("ask memo saved", status == 200 and body == {"askId": ask_id, "applied": True}, str(status))]
+    status, body = request("PUT", url, key, USER, {"memo": "older", "updatedAt": minutes_ago(2)})
+    results.append(check("older ask memo ignored", status == 200 and body.get("applied") is False, str(status)))
+    status, body = request("PUT", f"{api}/asks/{uuid.uuid4()}/memo", key, USER, {"memo": "x", "updatedAt": minutes_ago(1)})
+    results.append(check("memo for an unknown ask is 404", status == 404, str(status)))
+    return results
+
+
+def transcription_check(api: str, key: str, audio_b64: str) -> bool:
+    status, accepted = request("POST", f"{api}/transcriptions", key, USER, {"audio": audio_b64})
+    if status != 202:
+        return check("point memo voice transcribed", False, str(status))
+    start = time.monotonic()
+    while True:
+        elapsed = time.monotonic() - start
+        status, body = request("GET", f"{api}/transcriptions/{accepted['transcriptionId']}", key, USER)
+        if (status == 200 and body["status"] != "processing") or elapsed > 120:
+            break
+        time.sleep(1 if elapsed < 10 else 2)
+    ok = body.get("status") == "done" and "山" in (body.get("text") or "")
+    return check("point memo voice transcribed", ok, f"{elapsed:.1f}s text={body.get('text')} failure={body.get('failure')}")
+
+
+def delete_checks(api: str, key: str, ride_id: str, note_id: str, ask_id: str) -> list[bool]:
+    status, _ = request("DELETE", f"{api}/rides/{ride_id}", key, USER)
+    results = [check("ride deleted", status == 204, str(status))]
+    later = minutes_ago(-1)
+    status, body = request("PUT", f"{api}/rides/{ride_id}", key, USER, {**smoke_ride(), "updatedAt": later})
+    results.append(check("deleted ride does not come back", status == 410 and body == {"error": "deleted"}, str(status)))
+    note = {"at": minutes_ago(15), "location": TOKYO_STATION, "text": "late", "updatedAt": later}
+    status, _ = request("PUT", f"{api}/rides/{ride_id}/notes/{note_id}", key, USER, note)
+    results.append(check("deleted note does not come back", status == 410, str(status)))
+    status, _ = request("PUT", f"{api}/asks/{ask_id}/memo", key, USER, {"memo": "late", "updatedAt": later})
+    results.append(check("memo of a deleted ask is 410", status == 410, str(status)))
+    status, _ = request("GET", f"{api}/asks/{ask_id}", key, USER)
+    results.append(check("ask of a deleted ride is gone", status == 404, str(status)))
+    status, _ = request("DELETE", f"{api}/rides/{ride_id}", key, USER)
+    results.append(check("deleting again is 204", status == 204, str(status)))
+    return results
+
+
 def ask_and_wait(api: str, key: str, body: dict) -> tuple[dict, dict, float]:
     status, accepted = request("POST", f"{api}/asks", key, USER, body)
     if status != 202:
@@ -114,8 +178,9 @@ def main() -> int:
     status, body = request("POST", f"{api}/asks", key, "BAD", {"text": "Q"})
     results.append(check("bad user is 400", status == 400 and body.get("error") == "bad_request", str(status)))
 
-    ride_id = str(uuid.uuid4())
+    ride_id, note_id = str(uuid.uuid4()), str(uuid.uuid4())
     results.extend(ride_checks(api, key, ride_id))
+    results.extend(note_checks(api, key, ride_id, note_id))
 
     accepted, result, elapsed = ask_and_wait(
         api, key, {"text": "富士山の高さは？", "location": TOKYO_STATION, "headingSample": sample(10), "rideId": ride_id}
@@ -135,13 +200,15 @@ def main() -> int:
     results.append(check("conversation expiry returned", bool(expires), str(expires)))
 
     audio_b64 = base64.b64encode(FIXTURE.read_bytes()).decode()
-    accepted2, result2, elapsed2 = ask_and_wait(api, key, {"audio": audio_b64, "location": TOKYO_STATION, "headingSample": sample(10), "conversationId": conversation_id})
+    accepted2, result2, elapsed2 = ask_and_wait(api, key, {"audio": audio_b64, "location": TOKYO_STATION, "headingSample": sample(10),
+                                                           "conversationId": conversation_id, "rideId": ride_id})
     ok = result2.get("status") == "completed" and "山" in (result2.get("transcript") or "")
     results.append(check("audio question", ok, f"{elapsed2:.1f}s transcript={result2.get('transcript')} answer={result2.get('answer')}"))
     print("      timings:", json.dumps(result2.get("timings"), ensure_ascii=False))
     results.append(check("same conversation", accepted2.get("conversationId") == conversation_id))
 
-    _, result3, elapsed3 = ask_and_wait(api, key, {"text": "最初に聞いた山の名前をもう一度言って", "location": TOKYO_STATION, "conversationId": conversation_id})
+    _, result3, elapsed3 = ask_and_wait(api, key, {"text": "最初に聞いた山の名前をもう一度言って", "location": TOKYO_STATION,
+                                                   "conversationId": conversation_id, "rideId": ride_id})
     results.append(check("follow-up answered", result3.get("status") == "completed", f"{elapsed3:.1f}s answer={result3.get('answer')}"))
 
     status, body = request("GET", f"{api}/asks/{uuid.uuid4()}", key, USER)
@@ -149,6 +216,10 @@ def main() -> int:
     status, _ = request("GET", f"{api}/asks/{accepted.get('askId')}", key, "someoneelse")
     results.append(check("other user's ask is 404", status == 404))
 
+    results.extend(memo_checks(api, key, accepted.get("askId")))
+    results.append(transcription_check(api, key, audio_b64))
+    results.extend(delete_checks(api, key, ride_id, note_id, accepted.get("askId")))
+
     print(f"{sum(results)}/{len(results)} passed")
     return 0 if all(results) else 1
 
EOF
```

```bash
cd $BE && env/bin/python -m py_compile scripts/smoke.py && \rm -rf scripts/__pycache__
```

Expected: エラーなし

- [ ] **Step 2: コミット**

```bash
cd $BE && git add scripts/smoke.py
git commit -m "test: check memos, point memos, transcription and deletion after a deploy"
```

- [ ] **Step 3: 利用者にデプロイの確認を取る**

利用者に「Backend を `stack-trv2-dev-backend` にデプロイし、smoke を回してよいか」を聞き、明示の了承を待つ。了承がなければ、ここで止めて ledger に残す（デプロイは利用者が明示したときだけ）。

- [ ] **Step 4: 前提を確かめてデプロイする**

```bash
export AWS_PROFILE=touring AWS_REGION=ap-northeast-1
aws cloudformation describe-stacks --stack-name stack-trv2-dev-backend --query "Stacks[0].StackStatus" --output text
aws dynamodb describe-time-to-live --table-name dynamodb-trv2-dev-records --query "TimeToLiveDescription.TimeToLiveStatus" --output text
cd $BE && sam build 2>&1 | tail -2 && sam deploy --no-confirm-changeset 2>&1 | tail -15
```

Expected: 1行目が `UPDATE_COMPLETE`、2行目が `DISABLED`（TTL はまだ無い）、最後に `Successfully created/updated stack - stack-trv2-dev-backend`。失敗したら、エラーを調べてから直す（同じ操作を繰り返さない）。

- [ ] **Step 5: 通しの確認を回す**

```bash
cd $BE && AWS_PROFILE=touring env/bin/python scripts/smoke.py
```

Expected: 最後の行が `N/N passed`（すべて OK）。`note saved with its place`・`older note ignored`・`bad note is 400`・`ask memo saved`・`older ask memo ignored`・`memo for an unknown ask is 404`・`point memo voice transcribed`・`ride deleted`・`deleted ride does not come back`・`deleted note does not come back`・`memo of a deleted ask is 410`・`ask of a deleted ride is gone`・`deleting again is 204` を含む。新しい経路だけが 403 になったら、1分ほど待って回し直す（デプロイの直後の数秒に起きることがある。PROJECT.md の「持ち越し」）。

- [ ] **Step 6: 記録を見る**

```bash
aws dynamodb describe-time-to-live --table-name dynamodb-trv2-dev-records --query "TimeToLiveDescription.TimeToLiveStatus" --output text
aws dynamodb query --table-name dynamodb-trv2-dev-records --key-condition-expression "pk = :p AND begins_with(sk, :s)" \
  --expression-attribute-values '{":p":{"S":"USER#smoketest"},":s":{"S":"DELETED#"}}' --query "Items[].sk.S" --output text | tr '\t' '\n' | tail -6
```

Expected: 1行目が `ENABLED`（か `ENABLING`）。2つ目は、今回の smoke が残した `DELETED#ASK#<id>`（3件）・`DELETED#NOTE#<id>`・`DELETED#RIDE#<id>` を含む。今回の走行の `RIDE#<id>` と、その質問の `ASK#<id>` は残っていない（`begins_with(sk, "RIDE#<id>")` と `begins_with(sk, "ASK#")` の問い合わせで、今回の識別子が出ないこと）。
