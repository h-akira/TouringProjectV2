# スライス6 plan 6a: Backend の残りの不具合・権限（R4-02 後半・R4-01・R4-05・R4-03・R4-04・R4-06・R4-12・R4-14、Backend #37・#35）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend に残っている不具合と権限の広さを直す。worker が受け持ちを取ったあとで落ちた質問を、SQS の送り直しで `failed` にする。受け付け直後のポーリングが 404 にならないよう一貫して読む。録音を消す権限を足し、`POST /transcriptions` が積めないときは 503 にする。削除の跡を書き直さない。各 Lambda の DynamoDB の権限を、使う操作だけにする。

**Architecture:** (1) 受け持ち（`_claim`）に時刻 `claimedAt` を残し、`pending` でも受け持てなかったとき、`processing` で `claimedAt` が Lambda の時間切れより古い記録を `failed` にする `fail_stalled_*` を足す。worker はこれを SQS の送り直しで使う。(2) 読み出しの `ConsistentRead` を、ポーリングの2か所と地点メモの2か所に足す。(3) `handlers/common.py` に録音を消す共通の関数を置き、`ask.py` と `transcriptions.py` が使う。権限は template に足す。(4) `mark_deleted` を条件付きの書き込みにする。(5) DynamoDB の権限を関数ごとの Statement に書き換え、`tests/test_template.py` で関数ごとの操作の一覧と `Scan` が無いことを固定する。

**Tech Stack:** Python 3.13・boto3・moto・pytest。AWS SAM（`template.yaml`）。Backend の `env/bin/pytest`。

**Spec:** [docs/specs/2026-10-29-slice6-design.md](../specs/2026-10-29-slice6-design.md)（§3 の plan 6）。指摘の出どころは [全体レビュー](../final-review/2026-10-28/README.md) の backend.md（R4-01〜R4-06・R4-12・R4-14）。時間の予算は [adr/0014](../../adr/0014-ask-time-budget-from-acceptance.md)。

**後回しの issue**: Backend #37（plan 3 の worker テストの守り）・#35（未使用 import と空行）を入れる。Backend #28（`headingSample` の受け口を外す）は plan 9 で書き直すので入れない。

## Global Constraints

- 利用者に見える文章（ツール実行の合間の報告を含む）と文書は日本語。コード・コード中のコメント・コミットメッセージは英語。コミットメッセージは Conventional Commits。
- インデントは2スペース（Python は PEP 8 の4スペース）。型注釈を付ける。秘密情報をハードコードしない。接続キー・API の URL・アカウント ID を、コードや文書に書かない。
- `git add` はファイルを個別に指定する。コミットは許可を求めずに行ってよい。push・merge・デプロイは利用者が明示したときだけ。push の前に `pre-push-secret-scan` を回して報告する。AWS CLI は `AWS_PROFILE=touring`、リージョンは `ap-northeast-1`。
- ブランチは Backend も親も `slice6-plan6a`。コマンドは必ず絶対パスへ `cd` してから実行する。
- テストは `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest`。基準値は main で 377 件。moto は IAM を見ないので、権限の確かめは template のテストと、デプロイ後の smoke で行う。
- Android は変えない。API の形（07a）で変えるのは `POST /transcriptions` の 503 の応答を足すことだけ（既存の応答の形は変えない）。
- `docs/07a_openapi.yaml` を変えたら、`scripts/sync-docs.sh` で各ユニットに写してから Backend のテストを回す（Backend のテストは写しの 07a を読む）。
- デプロイと smoke は利用者に確認してから行う（Task 8）。

## Rulings（brainstorming で決めたこと）

- worker が落ちた質問は、**再実行せず `failed`（`agent_failed`）にする**（2026-10-30、利用者が決めた範囲の案）。Android は 120 秒であきらめているので、再実行しても使われない。
- 受け持ちが古いかは `claimedAt`（受け持ちを取った時刻。ISO 8601 の UTC・ミリ秒・`Z`）が **130 秒より前**かで決める。worker の Lambda の時間切れ（120 秒）より長く、SQS の可視性タイムアウト（180 秒）より短い。`claimedAt` の無い `processing`（この版より前に受け持たれたもの）は古いとみなさず、今までどおり何もしない。
- 文字起こしの記録（`TRANSCRIPTION#`）も、同じ仕組みで `failed`（`transcribe_failed`）にする。
- DynamoDB の権限は関数ごとの Statement にする。`Scan` はどこにも付けない。トランザクション（`TransactWriteItems`）は、中の操作ごとに `PutItem`・`UpdateItem`・`ConditionCheckItem` の権限が要る。
- R5-01（トレースに質問・位置が載る）は直さない（2026-10-30、利用者が決めた。plan 6b と [adr/0016](../../adr/0016-allow-personal-data-in-traces.md)）。この plan には関わらない。
- E（費用）の指摘と D（文書）の指摘は入れない（spec §2。D は plan 9）。ただし R4-04 の 07a の 503 は、直す内容と同じ変更なのでこの plan で書く。

## Review Focus

- 受け持ちを取ったあとで落ちた質問が、送り直しで `failed` になる。まだ処理中の質問は（古くなければ）触らない。Task 1 の `a_stalled_ask_is_failed_by_the_redelivery`・`a_claim_that_is_not_old_is_left_alone`。
- 受け付けの直後に回答を取りに行っても 404 にならない（一貫した読み）。Task 2。
- `POST /transcriptions` が積めないとき、記録も録音も残らず 503 になる。Task 3。
- 削除をもう一度送っても、跡の `rideId` と `deletedAt` が最初のまま。Task 4。
- 権限を絞っても、どの経路も `AccessDenied` にならない。Task 5 の関数ごとの操作の一覧のテストと、Task 8 の smoke。
- 送り直しの時間（130 秒）が、Lambda の時間切れと SQS の可視性タイムアウトのあいだに収まる。Task 1 の template のテスト。

---

## ファイルの構成

| ファイル（`Backend/` からの相対） | 変更 |
|---|---|
| `src/lib/budget.py` | `STALE_CLAIM_SECONDS = 130` |
| `src/lib/store/_dynamo.py` | `_claim` が `claimedAt` を書く・`_fail_stalled`・`mark_deleted` の条件 |
| `src/lib/store/ask_items.py`・`transcription_items.py` | `claim_*(…, now_iso)`・`fail_stalled_*`・`discard_transcription`・`get_transcription(consistent)` |
| `src/lib/store/ride_items.py` | `get_note(consistent)` |
| `src/lib/store/__init__.py` | 新しい関数の再公開 |
| `src/handlers/worker.py` | 送り直しの回復 |
| `src/handlers/result.py`・`transcriptions.py`・`rides.py` | 一貫した読み・503・docstring |
| `src/handlers/common.py`・`ask.py` | `discard_audio` を共通に |
| `template.yaml` | S3 の削除の権限・DynamoDB の権限を関数ごとに |
| `tests/` | `test_worker.py`・`test_store.py`・`test_result.py`・`test_transcriptions.py`・`test_notes.py`・`test_deletes.py`・`test_template.py`・`test_openapi.py` |
| 文書 | `docs/07a_openapi.yaml`・`docs/08b_backend-design.md`・`Backend/README.md`・`PROJECT.md` |

---

### Task 0: 指摘を現在のコードで確かめる

**Files:**（捨てる作業場。リポジトリには何も残さない）

spec §4: 不具合は再現テストを先に書き、失敗すれば本物。

- [ ] **Step 1: 捨てる worktree を作る**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
git worktree add /private/tmp/claude-501/p6a-red -b scratch-p6a-red slice6-plan6a
cp -R env /private/tmp/claude-501/p6a-red/env 2>/dev/null || true
```
（`env/` が使えなければ、worktree の中で `python3 -m venv env && env/bin/pip install -r requirements-dev.txt`。）

- [ ] **Step 2: 再現テストを足す**

`/private/tmp/claude-501/p6a-red/tests/test_red.py`:

```python
"""Throwaway: each test fails while the finding is real."""
import json

import pytest

from handlers import ask, result, transcriptions, worker
from lib import clients, store
from test_worker import ASK, USER, Recorder, put

RIDE = "22222222-2222-4222-8222-222222222222"


def test_r4_02_a_stalled_processing_ask_is_never_recovered(aws):
    put(aws)
    assert store.claim_ask(USER, ASK) is not None  # the first worker took it, then died
    worker.process(USER, ASK, Recorder().steps())  # SQS delivers again
    assert store.get_ask(USER, ASK)["status"] == "failed"


def test_r4_01_polling_reads_consistently(aws, monkeypatch):
    put(aws)
    table = clients.table()
    seen = []
    original = table.get_item
    monkeypatch.setattr(table, "get_item", lambda **p: (seen.append(p), original(**p))[1])
    result.handler({"headers": {"x-user-name": USER}, "pathParameters": {"askId": ASK}}, None)
    assert seen and all(p.get("ConsistentRead") is True for p in seen)


def test_r4_06_a_second_delete_keeps_the_first_mark(aws):
    store.mark_deleted(USER, "ask", ASK, "2026-10-16T03:00:00.000Z", ride_id=RIDE)
    store.mark_deleted(USER, "ask", ASK, "2026-10-16T04:00:00.000Z", ride_id=None)
    mark = aws.table.get_item(Key=store.deleted_key(USER, "ask", ASK))["Item"]
    assert mark["deletedAt"] == "2026-10-16T03:00:00.000Z" and mark["rideId"] == RIDE
```
（`put` は `test_worker.py` のもの。`tests/` に置いて回す。）

- [ ] **Step 3: 回して失敗を見る**

Run: `cd /private/tmp/claude-501/p6a-red && env/bin/pytest tests/test_red.py -v`
Expected: 3 件とも FAIL。落ちなければ、その指摘は誤りか直っているので ledger に `Ruling:` を書き、該当のタスクを縮める。

- [ ] **Step 4: 読んで確かめる**

R4-03・R4-04・R4-12 は moto で見えないので、読んで確かめる:
`rg "DeleteObject" Backend/template.yaml`（Worker にしか無い）・`rg "send_message" -B2 -A6 Backend/src/handlers/transcriptions.py`（例外を捕まえない）・`rg "DynamoDBCrudPolicy|DynamoDBReadPolicy" Backend/template.yaml`（7か所）。結果を ledger の最初に書く。

- [ ] **Step 5: worktree を消す**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
git worktree remove --force /private/tmp/claude-501/p6a-red
git branch -D scratch-p6a-red
```

---

### Task 1: 受け持ちのあとで落ちた質問を、送り直しで `failed` にする（R4-02 後半）

**Files:**
- Modify: `src/lib/budget.py`、`src/lib/store/_dynamo.py`、`src/lib/store/ask_items.py`、`src/lib/store/transcription_items.py`、`src/lib/store/__init__.py`、`src/handlers/worker.py`
- Test: `tests/test_worker.py`、`tests/test_transcriptions.py`、`tests/test_store.py`、`tests/test_template.py`

**Interfaces:**
- Produces: `lib.budget.STALE_CLAIM_SECONDS: int`、`store.claim_ask(user, ask_id, now_iso: str) -> Optional[dict]`、`store.claim_transcription(user, transcription_id, now_iso: str) -> Optional[dict]`、`store.fail_stalled_ask(user, ask_id, stale_before_iso: str) -> bool`、`store.fail_stalled_transcription(user, transcription_id, stale_before_iso: str) -> bool`。

`claim_ask` に時刻の引数を足すので、既存の呼び出し（`worker.process`・`worker.process_transcription`・テスト）を直す。`rg "claim_ask\(|claim_transcription\(" Backend` で全部を拾う。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_worker.py` に足す（`put`・`Recorder`・`T0`・`USER`・`ASK` は同じファイルのもの）:

```python
STALE = timedelta(seconds=budget.STALE_CLAIM_SECONDS)


def claimed_at(when):
    """The ask as a worker that then died left it: processing, taken at when."""
    assert store.claim_ask(USER, ASK, iso(when)) is not None


def test_a_stalled_ask_is_failed_by_the_redelivery(aws):
    put(aws)
    claimed_at(T0 - STALE - timedelta(seconds=1))
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())  # the clock of the steps is T0 + n seconds
    item = store.get_ask(USER, ASK)
    assert item["status"] == "failed" and item["error"] == "agent_failed"
    assert kinds(rec) == []  # nothing is run again


def test_a_claim_that_is_not_old_is_left_alone(aws):
    put(aws)
    claimed_at(T0 - timedelta(seconds=30))
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())
    assert store.get_ask(USER, ASK)["status"] == "processing" and kinds(rec) == []


def test_a_processing_ask_without_a_claim_time_is_left_alone(aws):
    # Taken by a worker of the version before claimedAt existed.
    put(aws, status="processing")
    worker.process(USER, ASK, Recorder().steps())
    assert store.get_ask(USER, ASK)["status"] == "processing"


def test_a_finished_ask_is_not_touched_by_a_redelivery(aws):
    put(aws)
    worker.process(USER, ASK, Recorder().steps())
    before = store.get_ask(USER, ASK)
    worker.process(USER, ASK, Recorder().steps())
    assert store.get_ask(USER, ASK) == before


def test_the_claim_time_is_not_shown_to_the_app(aws):
    from handlers import result
    put(aws)
    claimed_at(T0)
    body = json.loads(result.handler({"headers": {"x-user-name": USER}, "pathParameters": {"askId": ASK}}, None)["body"])
    assert "claimedAt" not in json.dumps(body)
```
`tests/test_worker.py` の import に `from lib import budget` を足す。`kinds`・`iso` は同じファイルにある。

`tests/test_transcriptions.py` に足す:

```python
def test_a_stalled_transcription_is_failed_by_the_redelivery(aws):
    transcription_id = accepted(aws)
    # Taken long before the steps' clock (T0 + a few seconds): the worker that took it is gone.
    assert store.claim_transcription(USER, transcription_id, "2026-10-16T02:50:00.000Z") is not None
    worker.process_transcription(USER, transcription_id, Recorder().steps())
    item = store.get_transcription(USER, transcription_id)
    assert item["status"] == "failed" and item["failure"] == "transcribe_failed"
```

`tests/test_template.py` に足す:

```python
def test_the_stale_claim_time_fits_between_the_lambda_timeout_and_the_queue_visibility():
    # A claim older than STALE_CLAIM_SECONDS belongs to a worker that is gone (its Lambda timed out), and the queue
    # delivers again only after its visibility timeout.
    from lib import budget
    template = _template()["Resources"]
    timeout = template["WorkerFunction"]["Properties"]["Timeout"]
    visibility = template["AskQueue"]["Properties"]["VisibilityTimeout"]
    assert timeout < budget.STALE_CLAIM_SECONDS < visibility
```
（`tests/` から `lib` を import できるか、`tests/conftest.py` の既存の import の仕方に合わせる。他のテストが `from lib import ...` している。）

- [ ] **Step 2: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest tests/test_worker.py tests/test_transcriptions.py tests/test_template.py -q`
Expected: コンパイル／AttributeError（`STALE_CLAIM_SECONDS`・`claim_ask` の引数が無い）で FAIL。

- [ ] **Step 3: 実装**

`src/lib/budget.py`（`TRANSCRIBE_SECONDS` の近く）:

```python
# A claim older than this belongs to a worker that is gone: longer than the worker Lambda's own time (120 s), shorter
# than the queue's visibility timeout (180 s), after which the message is delivered again.
STALE_CLAIM_SECONDS = 130
```

`src/lib/store/_dynamo.py` の `_claim` を置き換え、`_fail_stalled` を足す:

```python
def _claim(key: dict, now_iso: str) -> Optional[dict]:
    """pending -> processing, once, noting when (claimedAt). None when it is not pending or missing."""
    try:
        result = clients.table().update_item(
            Key=key,
            UpdateExpression="SET #s = :processing, claimedAt = :now",
            ConditionExpression="#s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":processing": "processing", ":pending": "pending", ":now": now_iso},
            ReturnValues="ALL_NEW",
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == _CONDITION_FAILED:
            return None
        raise
    return _from_item(result["Attributes"])


def _fail_stalled(key: dict, fields: dict, stale_before_iso: str) -> bool:
    """processing -> failed (with fields) when it was taken before stale_before_iso: the worker that took it is gone.
    False when it is not processing, was taken since, or has no claim time (taken before claimedAt existed)."""
    values = _to_item(fields)
    expression, names, placeholders = _set_clause(values)
    try:
        clients.table().update_item(
            Key=key,
            UpdateExpression=expression,
            ConditionExpression="#s = :processing AND attribute_exists(claimedAt) AND claimedAt < :stale",
            ExpressionAttributeNames={**names, "#s": "status"},
            ExpressionAttributeValues={**placeholders, ":processing": "processing", ":stale": stale_before_iso},
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == _CONDITION_FAILED:
            return False
        raise
    return True
```
`_set_clause` は `#k0` 形の名前を使うので、`#s` と衝突しない。`fields` に `status` を含めるので、`SET #k0 = :v0` は `status` を `failed` に書き、条件の `#s` は書き込み前の値を見る（DynamoDB は条件を書き込み前の項目に当てる）。

`src/lib/store/ask_items.py`:

```python
def claim_ask(user: str, ask_id: str, now_iso: str) -> Optional[dict]:
    """pending -> processing, once. None if already claimed or missing."""
    return _claim(ask_key(user, ask_id), now_iso)


def fail_stalled_ask(user: str, ask_id: str, stale_before_iso: str) -> bool:
    """A worker took the ask before stale_before_iso and never finished: it is failed, as agent_failed. False when it
    is not in that state."""
    return _fail_stalled(ask_key(user, ask_id), {"status": "failed", "error": "agent_failed"}, stale_before_iso)
```
（`_fail_stalled` を `from lib.store._dynamo import …` に足す。）

`src/lib/store/transcription_items.py`:

```python
def claim_transcription(user: str, transcription_id: str, now_iso: str) -> Optional[dict]:
    """pending -> processing, once. None if already claimed or missing."""
    return _claim(transcription_key(user, transcription_id), now_iso)


def fail_stalled_transcription(user: str, transcription_id: str, stale_before_iso: str) -> bool:
    return _fail_stalled(transcription_key(user, transcription_id), {"status": "failed", "failure": "transcribe_failed"},
                         stale_before_iso)
```
`src/lib/store/__init__.py` の再公開に `fail_stalled_ask`・`fail_stalled_transcription` を足す。

`src/handlers/worker.py`:

```python
def _stale_before(steps: Steps) -> str:
    return iso(steps.now() - timedelta(seconds=budget.STALE_CLAIM_SECONDS))
```
（`from datetime import datetime, timedelta, timezone`。）`process` の先頭を:

```python
    item = store.claim_ask(user, ask_id, iso(steps.now()))
    if item is None:
        # Delivered again after a worker took the ask and died (timed out, out of memory): no one will finish it.
        if store.fail_stalled_ask(user, ask_id, _stale_before(steps)):
            log({"event": "ask_recovered", "askId": ask_id})
        else:
            log({"event": "ask_skipped", "askId": ask_id})
        return
```
`process_transcription` も同じ形:

```python
    item = store.claim_transcription(user, transcription_id, iso(steps.now()))
    if item is None:
        if store.fail_stalled_transcription(user, transcription_id, _stale_before(steps)):
            log({"event": "transcription_recovered", "transcriptionId": transcription_id})
        else:
            log({"event": "transcription_skipped", "transcriptionId": transcription_id})
        return
```
既存のテストの `store.claim_ask(USER, ASK)` の呼び出しは、`store.claim_ask(USER, ASK, "2026-10-16T03:00:00.000Z")` のように時刻を渡す形に直す。

- [ ] **Step 4: 全体を回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest -q`
Expected: 全件 PASS（377 + 新しい 7 件前後）。`test_the_claim_time_is_not_shown_to_the_app` と、`test_pending_is_reported_as_processing` の完全一致（`claimedAt` を漏らさない）が通ること。

- [ ] **Step 5: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
git add src/lib/budget.py src/lib/store/_dynamo.py src/lib/store/ask_items.py src/lib/store/transcription_items.py src/lib/store/__init__.py src/handlers/worker.py tests/test_worker.py tests/test_transcriptions.py tests/test_template.py
git add -u tests
git commit -m "fix: fail an ask whose worker died after taking it, when the queue delivers it again (R4-02)"
```
（`git add -u tests` は、このタスクで直した既存のテストだけが変わっているときに限る。他の変更が混ざるなら個別に指定する。）

---

### Task 2: 受け付けの直後のポーリングと地点メモを一貫して読む（R4-01・R4-05）

**Files:**
- Modify: `src/lib/store/transcription_items.py`、`src/lib/store/ride_items.py`、`src/handlers/result.py`、`src/handlers/transcriptions.py`、`src/handlers/rides.py`
- Test: `tests/test_result.py`、`tests/test_transcriptions.py`、`tests/test_notes.py`

**Interfaces:**
- Produces: `store.get_transcription(user, transcription_id, consistent: bool = False)`、`store.get_note(user, ride_id, note_id, consistent: bool = False)`。

- [ ] **Step 1: 失敗するテストを書く**

moto はいつも一貫しているので、`get_item` に渡る引数を見る（`tests/test_deletes.py` の `test_deleting_a_ride_reads_its_records_with_consistent_reads` と同じ形）。`tests/test_result.py`:

```python
def spy_get_item(monkeypatch):
    from lib import clients
    table = clients.table()
    seen = []
    original = table.get_item

    def spy(**params):
        seen.append(params)
        return original(**params)

    monkeypatch.setattr(table, "get_item", spy)
    return seen


def test_the_answer_is_read_consistently(aws, monkeypatch):
    # The app asks about 1 s after the ask was written; a replica that has not got it yet would say 404 (R4-01).
    put(status="pending")
    seen = spy_get_item(monkeypatch)
    call()
    assert seen and all(p.get("ConsistentRead") is True for p in seen)
```
`tests/test_transcriptions.py`:

```python
def test_a_transcription_is_read_consistently(aws, monkeypatch):
    from lib import clients
    transcription_id = accepted(aws)
    table = clients.table()
    seen = []
    original = table.get_item
    monkeypatch.setattr(table, "get_item", lambda **p: (seen.append(p), original(**p))[1])
    get(transcription_id)
    assert seen and all(p.get("ConsistentRead") is True for p in seen)
```
`tests/test_notes.py`（`places` は同じファイルの fixture、`put_note`・`note_body` も同じファイルのもの）:

```python
def test_a_stored_point_memo_is_read_consistently(aws, places, monkeypatch):
    # A second send right after the first must see it, or it would settle the place and heading again (R4-05).
    from lib import clients
    assert put_note(note_body())["statusCode"] == 200
    table = clients.table()
    seen = []
    original = table.get_item

    def spy(**params):
        seen.append(params)
        return original(**params)

    monkeypatch.setattr(table, "get_item", spy)
    put_note(note_body(updatedAt="2026-10-21T02:00:00.000Z"))
    note_reads = [p for p in seen if "#NOTE#" in p["Key"]["sk"]]
    assert note_reads and all(p.get("ConsistentRead") is True for p in note_reads)
```

- [ ] **Step 2: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest tests/test_result.py tests/test_transcriptions.py tests/test_notes.py -q`
Expected: 3 件 FAIL（`ConsistentRead` が False／無い）。

- [ ] **Step 3: 実装**

`src/lib/store/transcription_items.py`:

```python
def get_transcription(user: str, transcription_id: str, consistent: bool = False) -> Optional[dict]:
    item = clients.table().get_item(Key=transcription_key(user, transcription_id), ConsistentRead=consistent).get("Item")
    return _from_item(item) if item else None
```
`src/lib/store/ride_items.py`:

```python
def get_note(user: str, ride_id: str, note_id: str, consistent: bool = False) -> Optional[dict]:
    item = clients.table().get_item(Key=note_key(user, ride_id, note_id), ConsistentRead=consistent).get("Item")
    return _from_item(item) if item else None
```
`src/handlers/result.py`: `store.get_ask(user, ask_id, consistent=True)`。
`src/handlers/transcriptions.py` の `_get`: `store.get_transcription(user, transcription_id, consistent=True)`。
`src/handlers/rides.py` の `_note()`: `store.get_note(user, ride_id, note_id, consistent=True)`（2か所）。あわせて、そこにあるコメント「a stored copy is read eventually consistently (review R4-05)」を「a stored copy is read consistently, as ask_edit does」に直す。

- [ ] **Step 4: 全体を回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest -q`
Expected: 全件 PASS。

- [ ] **Step 5: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
git add src/lib/store/transcription_items.py src/lib/store/ride_items.py src/handlers/result.py src/handlers/transcriptions.py src/handlers/rides.py tests/test_result.py tests/test_transcriptions.py tests/test_notes.py
git commit -m "fix: read the polled ask, the transcription and a stored point memo consistently (R4-01, R4-05)"
```

---

### Task 3: 録音を消す権限と、`POST /transcriptions` が積めないときの 503（R4-03・R4-04）

**Files:**
- Modify: `src/handlers/common.py`、`src/handlers/ask.py`、`src/handlers/transcriptions.py`、`src/lib/store/transcription_items.py`、`src/lib/store/__init__.py`、`template.yaml`、`docs/07a_openapi.yaml`（親）、`src/handlers/rides.py`（docstring。R4-14）
- Test: `tests/test_transcriptions.py`、`tests/test_template.py`、`tests/test_ask.py`（既存のテストが通ること）

**Interfaces:**
- Produces: `handlers.common.discard_audio(key: str) -> None`、`store.discard_transcription(user, transcription_id) -> None`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_transcriptions.py`（`test_an_ask_that_cannot_be_queued_is_503_and_leaves_no_ask_or_audio` と同じ形）:

```python
def test_a_recording_that_cannot_be_queued_is_503_and_leaves_no_record_or_audio(aws, monkeypatch):
    # Nothing would ever take the record, so it is not left pending, and the recording is not kept (R4-04).
    def broken(**params):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(transcriptions.clients.sqs(), "send_message", broken)
    result = post({"audio": base64.b64encode(AUDIO).decode()})
    assert result["statusCode"] == 503 and json.loads(result["body"]) == {"error": "unavailable"}
    assert [i["sk"] for i in aws.table.scan()["Items"] if i["sk"].startswith("TRANSCRIPTION#")] == []
    assert audio_keys(aws) == []
```
`tests/test_template.py`:

```python
def _functions() -> dict:
    return {name: r["Properties"] for name, r in _template()["Resources"].items() if r["Type"] == "AWS::Serverless::Function"}


def _actions(properties: dict) -> set:
    found = set()
    for policy in properties.get("Policies", []):
        for statement in (policy or {}).get("Statement", []) if isinstance(policy, dict) else []:
            action = statement["Action"]
            found |= set(action if isinstance(action, list) else [action])
    return found


def test_a_function_that_deletes_a_recording_may_delete_one():
    # moto does not check IAM, so a missing s3:DeleteObject only shows after the deploy (R4-03, R4-04).
    import re
    for name, properties in _functions().items():
        module = properties["Handler"].rsplit(".", 1)[0].replace(".", "/")
        source = (ROOT / "src" / f"{module}.py").read_text(encoding="utf-8")
        if re.search(r"\.delete_object\(", source):
            assert "s3:DeleteObject" in _actions(properties), name
```
（`_template()` は `!Sub` などをタグごと `None` に読む。`Statement` の `Action` は文字列か一覧なので、上のように扱う。`Policies` の要素は `DynamoDBCrudPolicy` などの辞書も含むので `isinstance(policy, dict)` と `"Statement"` の有無で絞る。）

- [ ] **Step 2: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest tests/test_transcriptions.py tests/test_template.py -q`
Expected: 2 件 FAIL（502 相当の例外で落ちる・`AskFunction`／`TranscriptionsFunction` に `s3:DeleteObject` が無い）。

- [ ] **Step 3: 実装**

`src/handlers/common.py`（`import os` と `from lib import clients` を足す）:

```python
def discard_audio(key: str) -> None:
    """Removes a recording that was not kept; the 1-day lifecycle rule would remove it anyway."""
    try:
        clients.s3().delete_object(Bucket=os.environ["AUDIO_BUCKET"], Key=key)
    except Exception as error:  # noqa: BLE001
        log({"event": "audio_delete_failed", "error": type(error).__name__})
```
`src/handlers/ask.py`: 自前の `_discard_audio` を消し、`from handlers.common import discard_audio, iso, log, response, utc_now` にして `discard_audio(item["audioKey"])` を呼ぶ。`os`・`clients` の import が他で使われているかを確かめて、使われていなければ消す（`clients.s3().put_object`・`os.environ` は `ask.py` の他の行で使うので残る）。

`src/lib/store/transcription_items.py`:

```python
def discard_transcription(user: str, transcription_id: str) -> None:
    """Removes a transcription that was never queued: no worker would take it."""
    clients.table().delete_item(Key=transcription_key(user, transcription_id))
```
`src/lib/store/__init__.py` の再公開に足す。

`src/handlers/transcriptions.py` の `_accept` の `send_message` を:

```python
    try:
        clients.sqs().send_message(QueueUrl=os.environ["QUEUE_URL"], MessageBody=json.dumps(
            {"kind": "transcription", "userName": user, "transcriptionId": transcription_id}))
    except Exception as error:  # noqa: BLE001 - reported to the app as 503, which it retries
        # No worker would ever take it, so it is not left pending, and the recording is not kept (R4-04).
        log({"event": "transcription_queue_failed", "transcriptionId": transcription_id, "error": type(error).__name__})
        store.discard_transcription(user, transcription_id)
        discard_audio(audio_key)
        return response(503, {"error": "unavailable"})
```
（`from handlers.common import discard_audio, iso, log, response, utc_now`。）

`template.yaml` の `AskFunction` の `Statement` の `Action: s3:PutObject` を `Action: [s3:PutObject, s3:DeleteObject]` に、`TranscriptionsFunction` も同じにする（Resource は `${AudioBucket.Arn}/audio/*` のまま）。

`docs/07a_openapi.yaml` の `/transcriptions` の `post` の `"429"` の次に、`/asks` の `post` の `"503"` と同じ形を足す:

```yaml
        "503":
          description: 受け付けたが処理に回せなかった。記録は残さない。App は通信の失敗と同じに扱う
          content:
            application/json:
              schema:
                type: object
                required: [error]
                properties:
                  error:
                    type: string
                    enum: [unavailable]
```
（`/asks` の `"503"` の実際の本文（`07a` の 50〜70 行）を読み、`properties` の中身を同じにする。）

`src/handlers/rides.py` の先頭の docstring の「Reading them back comes later.」を「Reading them back is GET /records (handlers/records.py).」に直す（R4-14）。

- [ ] **Step 4: 07a を写して全体を回す**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2 && scripts/sync-docs.sh Backend
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest -q
```
Expected: 全件 PASS。`tests/test_openapi.py` が `/transcriptions` の 503 を含めて通ること。

- [ ] **Step 5: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
git add src/handlers/common.py src/handlers/ask.py src/handlers/transcriptions.py src/handlers/rides.py src/lib/store/transcription_items.py src/lib/store/__init__.py template.yaml tests/test_transcriptions.py tests/test_template.py docs-parent/07a_openapi.yaml
git commit -m "fix: delete the recording when a request cannot be queued, and answer 503 for a transcription too (R4-03, R4-04)"
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2
git add docs/07a_openapi.yaml
git commit -m "docs: add the 503 of POST /transcriptions to the API spec (R4-04)"
```
（07a は親の `docs/` が正本。Backend の `docs-parent/` は写し。親のコミットは plan のブランチ `slice6-plan6a` に入れる。）

---

### Task 4: 削除をもう一度送っても、跡を書き直さない（R4-06）

**Files:**
- Modify: `src/lib/store/_dynamo.py`
- Test: `tests/test_deletes.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_deletes.py`（`ASK`・`RIDE`・`NOTE`・`call` などは同じファイルのもの。`store.deleted_key` を使う）:

```python
def mark_of(aws, kind, record_id):
    return aws.table.get_item(Key=store.deleted_key(USER, kind, record_id))["Item"]


def test_a_second_delete_keeps_the_first_mark(aws):
    # A mark written again would lose the ride of the ask and move deletedAt later (R4-06).
    store.mark_deleted(USER, "ask", ASK, "2026-10-16T03:00:00.000Z", ride_id=RIDE)
    store.mark_deleted(USER, "ask", ASK, "2026-10-16T04:00:00.000Z", ride_id=None)
    mark = mark_of(aws, "ask", ASK)
    assert mark["deletedAt"] == "2026-10-16T03:00:00.000Z" and mark["rideId"] == RIDE


def test_an_ask_deleted_after_its_ride_keeps_the_ride_in_its_mark(aws):
    # The ride's deletion removes the ask and marks it with the ride; the app's own delete of that ask arrives later,
    # finds nothing to read the ride from, and must not write the mark again.
    call(rides, "PUT", body=ride_body(), rideId=RIDE)
    ask(ASK, RIDE)
    assert call(rides, "DELETE", rideId=RIDE)["statusCode"] == 204
    assert call(ask_edit, "DELETE", askId=ASK)["statusCode"] == 204
    assert mark_of(aws, "ask", ASK)["rideId"] == RIDE
```

- [ ] **Step 2: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest tests/test_deletes.py -q`
Expected: 2 件 FAIL（`deletedAt` が 04:00 に変わる・`rideId` が消える）。

- [ ] **Step 3: 実装**

`src/lib/store/_dynamo.py` の `mark_deleted`:

```python
def mark_deleted(user: str, kind: str, record_id: str, deleted_at: str, ride_id: Optional[str] = None) -> None:
    """Writes the deletion mark unless one is there: marking again keeps the first, with its ride and its time
    (07 UC-4: the same request, sent again, has the same result). Marks never expire (adr/0009)."""
    item = _to_item({**deleted_key(user, kind, record_id), "kind": kind, "id": record_id, "rideId": ride_id,
                     "deletedAt": deleted_at})

    def write() -> None:
        try:
            clients.table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
        except ClientError as error:
            if error.response["Error"]["Code"] != _CONDITION_FAILED:
                raise

    _retrying_conflicts(write)
```

- [ ] **Step 4: 全体を回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest -q`
Expected: 全件 PASS。

- [ ] **Step 5: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
git add src/lib/store/_dynamo.py tests/test_deletes.py
git commit -m "fix: keep the first deletion mark when the same delete is sent again (R4-06)"
```

---

### Task 5: DynamoDB の権限を関数ごとに絞る（R4-12）

**Files:**
- Modify: `template.yaml`
- Test: `tests/test_template.py`

関数ごとの操作の一覧（コードを読んで決めた。Task 1 の `_fail_stalled` は `UpdateItem`、Task 3 の `discard_transcription` は `DeleteItem`）:

| 関数 | 操作 | 使う場所 |
|---|---|---|
| Ask | `GetItem`・`PutItem`・`DeleteItem` | 会話の最初の時刻（条件付きの Put と Get）・質問の作成・積めなかったときの削除 |
| Result | `GetItem` | ポーリング |
| Rides | `GetItem`・`PutItem`・`DeleteItem`・`Query`・`BatchGetItem`・`BatchWriteItem`・`ConditionCheckItem` | 地点メモの読み・走行／ルート／地点メモ（トランザクションの Put と確かめ）・跡と削除・削除の跡の確かめ・走行の下の問い合わせとまとめて消す |
| AskEdit | `GetItem`・`PutItem`・`DeleteItem`・`UpdateItem`・`BatchGetItem`・`ConditionCheckItem` | 質問の削除・メモと質問できなかった地点のトランザクション・跡の確かめ |
| Records | `Query` | 引き継ぎ |
| Transcriptions | `GetItem`・`PutItem`・`DeleteItem` | ポーリング・作成・積めなかったときの削除 |
| Worker | `UpdateItem` | 受け持ち・結果の書き込み・送り直しでの回復 |

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_template.py`（Task 3 の `_functions`・`_actions` を使う。`Policies` の `DynamoDBCrudPolicy`／`DynamoDBReadPolicy` は SAM が `Scan` を含む形に展開するので、使わない）:

```python
EXPECTED_DYNAMODB = {
    "AskFunction": {"GetItem", "PutItem", "DeleteItem"},
    "ResultFunction": {"GetItem"},
    "RidesFunction": {"GetItem", "PutItem", "DeleteItem", "Query", "BatchGetItem", "BatchWriteItem", "ConditionCheckItem"},
    "AskEditFunction": {"GetItem", "PutItem", "DeleteItem", "UpdateItem", "BatchGetItem", "ConditionCheckItem"},
    "RecordsFunction": {"Query"},
    "TranscriptionsFunction": {"GetItem", "PutItem", "DeleteItem"},
    "WorkerFunction": {"UpdateItem"},
}


def test_no_function_uses_the_broad_dynamodb_policy_templates():
    # SAM expands DynamoDBCrudPolicy and DynamoDBReadPolicy with Scan and more (R4-12).
    for name, properties in _functions().items():
        for policy in properties.get("Policies", []):
            assert not (isinstance(policy, dict) and {"DynamoDBCrudPolicy", "DynamoDBReadPolicy"} & set(policy)), name


def test_each_function_may_use_the_dynamodb_operations_it_uses_and_no_scan():
    for name, expected in EXPECTED_DYNAMODB.items():
        granted = {a.split(":", 1)[1] for a in _actions(_functions()[name]) if a.startswith("dynamodb:")}
        assert granted == expected, name
    assert all("dynamodb:Scan" not in _actions(p) for p in _functions().values())
```

- [ ] **Step 2: 失敗を見る**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest tests/test_template.py -q`
Expected: 2 件 FAIL（まだテンプレートの雛形を使っている）。

- [ ] **Step 3: template を書き換える**

7つの関数の `DynamoDBCrudPolicy`／`DynamoDBReadPolicy` の項目を消し、それぞれの `Statement` の先頭に足す（Statement が無い関数 `ResultFunction`（S3 の Statement はある）・`RecordsFunction` は新しく `- Statement:` を作る）。例（`RidesFunction`）:

```yaml
        - Statement:
            - Effect: Allow
              Action:
                - dynamodb:GetItem
                - dynamodb:PutItem
                - dynamodb:DeleteItem
                - dynamodb:Query
                - dynamodb:BatchGetItem
                - dynamodb:BatchWriteItem
                - dynamodb:ConditionCheckItem
              Resource: !GetAtt RecordsTable.Arn
```
他の関数も上の表のとおり。既に `Statement:` を持つ関数（Ask・Result・Rides・AskEdit・Transcriptions・Worker）は、その Statement の一覧の先頭に `Effect: Allow`／`Action`／`Resource: !GetAtt RecordsTable.Arn` の項目を足す。`RecordsFunction` は `Policies:` を次にする:

```yaml
      Policies:
        - Statement:
            - Effect: Allow
              Action: dynamodb:Query
              Resource: !GetAtt RecordsTable.Arn
```
トランザクションと条件付き書き込みは、同じ表の ARN に対する `PutItem`／`UpdateItem`／`ConditionCheckItem` で足りる（インデックスは無い）。

- [ ] **Step 4: 全体を回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest -q`
Expected: 全件 PASS。`sam validate` が使えるなら `AWS_PROFILE=touring sam validate --lint` も通ること（使えなければ、Task 8 のデプロイの前の `sam build` で確かめる）。

- [ ] **Step 5: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
git add template.yaml tests/test_template.py
git commit -m "fix: give each function only the DynamoDB operations it uses, and no Scan (R4-12)"
```

---

### Task 6: 後回しの issue の後始末（Backend #37・#35）

**Files:**
- Modify: `tests/test_worker.py`、`tests/test_openapi.py`、`src/lib/records.py`

- [ ] **Step 1: #37 のテストを強くする**

`tests/test_worker.py` の `test_the_agents_own_timeout_is_a_failed_ask` を、Agent の `timeout` のコードがログに残ることまで確かめる形にする（`capsys` で `agent_error` の行の `error` が `timeout` であること。`test_the_agent_error_log_has_the_code_only` と同じ作り）:

```python
def test_the_agents_own_timeout_is_a_failed_ask_and_its_code_is_logged(aws, capsys):
    put(aws)
    rec = Recorder(agent_error=AgentError("timeout"))
    worker.process(USER, ASK, rec.steps())
    item = store.get_ask(USER, ASK)
    assert item["status"] == "failed" and item["error"] == "agent_failed"
    logged = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert {"event": "agent_error", "askId": ASK, "error": "timeout"} in logged
```
`test_an_ask_with_no_time_left_fails_without_calling_the_agent` に、書かれた事実を足す:

```python
    assert item["transcript"] == "右手の山は？" and item["address"] == "東京都千代田区丸の内" and "headingDegrees" in item
```
（この質問は音声なので `transcript` は `Recorder` の既定の「右手の山は？」。`headingDegrees` は `HERE`／`SOUTH` から決まる値が入る。実際の値を一度出して確かめ、`in item` ではなく値で固定する。）

- [ ] **Step 2: #35 を直す**

`tests/test_openapi.py`: 未使用の `from handlers import result` と `from lib import records`（使われていなければ）を消し、同じものを確かめる2本（`test_the_ask_statuses_match_the_result`・`test_the_ask_record_statuses_match_the_handler`）を1本にまとめる:

```python
def test_the_ask_statuses_in_the_spec_match_the_handlers():
    schemas = SPEC["components"]["schemas"]
    for schema in ("AskResult", "AskRecord"):
        assert set(schemas[schema]["properties"]["status"]["enum"]) == set(asks.STATUS.values()), schema
```
`src/lib/records.py` の `MAX_SORT_KEY_BYTES = 1024` と `def encode_cursor` のあいだの空行を2行にする。

- [ ] **Step 3: 全体を回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest -q`
Expected: 全件 PASS。

- [ ] **Step 4: Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
git add tests/test_worker.py tests/test_openapi.py src/lib/records.py
git commit -m "test: guard the agent timeout and the unanswered ask, and tidy test_openapi (Backend #37, #35)"
```

---

### Task 7: README と 08b を実装に合わせ、版を整える

**Files:**
- Modify: `Backend/README.md`、`docs/08b_backend-design.md`（親）、`PROJECT.md`（親）

- [ ] **Step 1: README**

`Backend/README.md` の「流れ」2 に「受け持ちを取った時刻（`claimedAt`）を残す。worker が落ちて SQS が送り直したとき、130 秒より古い受け持ちは `failed` にする（再実行はしない）」を、9 に「SQS に積めなかったときは、記録と録音を消して 503 を返す」を足す。「大事な決まり」に「どの Lambda も DynamoDB の権限は使う操作だけ。`tests/test_template.py` の一覧を、コードが使う操作を足したときに直す（moto は IAM を見ないので、足し忘れはデプロイ後に `AccessDenied` で出る。smoke で気づく）」を書く。

- [ ] **Step 2: 08b**

`docs/08b_backend-design.md` §5 の「worker が落ちたメッセージは SQS が送り直し、2回失敗したら DLQ に移す。」の次に「受け持ちを取った後で落ちた（時間切れ・メモリ切れ）質問と文字起こしは、送り直しで失敗にする（受け持ちの時刻が130秒より古いとき。再実行はしない）。」を足す。§2 の `POST /transcriptions` に触れる文があれば、「積めなかったときは記録と録音を消して 503」と揃える（`rg "transcriptions" docs/08b_backend-design.md` で探す）。経緯（「直した」）は書かず、いまの決まりだけを書く。

- [ ] **Step 3: 写して Commit**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2 && scripts/sync-docs.sh Android Backend Agent CICD
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
git add README.md docs-parent/08b_backend-design.md docs-parent/07a_openapi.yaml
git commit -m "docs: describe the recovery of a stalled claim and the 503 of a transcription"
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2
git add docs/08b_backend-design.md
git commit -m "docs: say a stalled claim is failed by the redelivery (08b)"
```
Android・Agent・CICD の `docs-parent/` の写しは、変わるものがあれば各ユニットの `main` に直接コミットする（変わらなければ何もしない。`git -C <unit> status --short` で確かめる）。

---

### Task 8: デプロイと smoke（利用者に確認してから）

**Files:**（なし）

- [ ] **Step 1: 全体のテストを回す**

Run: `cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend && env/bin/pytest -q`
Expected: 全件 PASS。件数を ledger に書く。

- [ ] **Step 2: 利用者に確認する**

デプロイは利用者の確認を取ってから行う。確認では次を伝える: IAM の権限を絞るので、足りない操作があると smoke で `AccessDenied` になる（その場合は template に足して再デプロイする）。

- [ ] **Step 3: ビルドとデプロイ**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
AWS_PROFILE=touring sam build && AWS_PROFILE=touring sam deploy
```
Expected: スタックの更新が成功する。

- [ ] **Step 4: smoke**

```bash
cd /Users/hakira/Programs/000_Uncategorized/TouringProjectV2/Backend
AWS_PROFILE=touring env/bin/python scripts/smoke.py
```
Expected: 40/40。新しい経路が 403（`Missing Authentication Token`）になるときは、1分ほど待って回し直す。`AccessDenied` で落ちたら、CloudWatch のログ（関数のログ群）で操作名を見て、template と `EXPECTED_DYNAMODB` の両方に足す。

- [ ] **Step 5: 回復の確かめ（任意）**

`claimedAt` が古い `processing` の質問を DynamoDB に置き、SQS にメッセージを積んで `failed` になることを見るのは、本番の表を触るので行わない（単体のテストで固定してある）。

- [ ] **Step 6: 結果を PROJECT.md に書く**

smoke の結果とテストの件数を、plan 表の plan 6a の行に書く。

---

## Self-Review

- **Spec coverage**: spec §3 の plan 6 のうち Backend の分（R4-02 の実行環境の落ちの部分・R4-01・R4-03・R4-04・R4-05・R4-06・R4-12・R4-14）は Task 1〜5、後回しの issue（Backend #37・#35）は Task 6。デプロイと smoke は Task 8。Agent の分は plan 6b。
- **R4-02 の範囲**: 時間切れの部分は plan 3 で閉じた。ここは「受け持ちを取ったあとで実行環境ごと落ちた」場合だけを閉じる。
- **型の一貫**: `claim_ask(user, ask_id, now_iso)`（Task 1）を `worker.process` が `iso(steps.now())` で呼ぶ。`fail_stalled_ask(user, ask_id, stale_before_iso)` は `_stale_before(steps)` が作る。`discard_transcription`（Task 3）と `EXPECTED_DYNAMODB` の `TranscriptionsFunction` の `DeleteItem` が対応する。
- **使い捨てのフォルダで通していないもの**: この plan のコードは、書いた時点では通していない（PROJECT.md の前提）。実行のときは、各タスクの「失敗を見る」で、名前と引数が合うかを先に確かめる。特に、(1) Task 6 の `headingDegrees` の値（実際の値を一度出して固定する）、(2) `07a` の 503 の `properties`（`/asks` の 503 を読んで同じにする）、(3) Task 5 の template の書き換え（`sam build` で確かめる）。
