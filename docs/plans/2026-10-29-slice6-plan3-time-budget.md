# スライス6 計画3: 質問の時間の予算（Backend と Agent） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 質問にかけてよい時間を、受け付けから決めた締め切りで Backend と Agent が打ち切る形にし、同じ会話への呼び出しが重なっても履歴が消えないようにする（全体レビューの R11-01・R5-02・R4-02 の時間切れの部分・R12-01）。Backend と Agent をデプロイして、smoke を通す。

**Architecture:** Backend は受け付けで締め切り（110 秒後）を質問の記録に残す。worker は、締め切りと Lambda の残り時間の早いほうから合成の余白を引いた秒数を、Agent への本文の `deadlineSeconds` に入れる。残りが足りなければ Agent を呼ばずに失敗で終える。Agent は `deadlineSeconds` で呼び出しを `asyncio.timeout` で打ち切り、`timeout` のエラーを返して履歴を残さない。Agent は `session_id` ごとの錠の中で履歴を読み書きし、錠の待ちも締め切りに数える。決定の理由は [adr/0014](../../adr/0014-ask-time-budget-from-acceptance.md)。

**Tech Stack:** Python 3.13（Backend・moto）・Python 3.14（Agent・Strands）・pytest・AgentCore CLI 0.31.1。足す依存は無い。

**Spec:** [docs/specs/2026-10-29-slice6-design.md](../specs/2026-10-29-slice6-design.md) §3（plan 3）・§4・§5。指摘の本文は [報告](../final-review/2026-10-28/README.md) の structure.md R11-01、backend.md R4-02、agent.md R5-02、issues.md R12-01。

**確かめたこと（spec §4）:** 報告のとおりだった。Agent の `handle()` は `stream_async` を時間の上限なしで回し、履歴を最初に読んで最後に丸ごと書き戻す（錠なし）。Backend の `agentcore()` の読みの時間切れは 90 秒で、worker の Lambda は 120 秒。記録の質問に締め切りは無い。誤りではない。R4-02 のうち、メモリ切れ・実行環境の落ち（`claimedAt`）は spec のとおり plan 6。

**計画を書くときに決めたこと:**

- **時計の呼び出しを増やさない。** worker のテストは `steps.now()` が呼ぶたびに進む時計を使う。予算の計算は、すでに呼んでいる `mark("factsAt")` が返す時刻を使う（`mark` が `datetime` を返す形に変える）。
- **Agent を呼ぶ関数に4つ目の引数 `deadline_seconds` を足す。** `Steps.invoke_agent` は `(prompt, location, session_id, seconds)`。既存のテストの作り物は `deadline_seconds=None` を受ける形にする。`lib.agent.invoke` は末尾の引数 `deadline_seconds` で受ける（先頭側の引数の順は変えない）。
- **締め切りが記録に無い質問**（デプロイの時点で処理中のもの）は、`receivedAt` + 110 秒を使う。
- **文字起こしの上限は 30 秒**（`budget.TRANSCRIBE_SECONDS`）。点メモの文字起こしも同じ関数なので同じ。超えると `TimeoutError` になり、`transcribe_failed` で終わる（これまでの例外の扱いのまま）。
- **Backend の Agent への読みの時間切れは 105 秒**（`budget.AGENT_READ_TIMEOUT_SECONDS`）。Agent が打ち切る時刻より長く、Agent の `timeout` のエラーを読めるようにする。worker の Lambda（120 秒）に1回の読みが収まる。
- **失敗の値は `agent_failed` のまま。** Agent の `timeout` は、worker のログの理由（`agent_error` の `error`）に残り、記録の `error` は `agent_failed`。07a の `error` の列挙と Android は変えない。
- **Agent の既定の上限は 100 秒**（`AGENT_DEFAULT_DEADLINE_SECONDS`）。`deadlineSeconds` が来ないとき・数でないとき・0 以下か 600 を超えるときに使う。
- **Agent の錠は `Deps.locks`**（`history.SessionLocks`）。錠の待ちも `asyncio.timeout` の中で行う。呼び出しを抜けたとき（打ち切り・クライアントの切断）は錠が外れる。
- **Agent の smoke に2つの確認を足す。** 小さな `deadlineSeconds` で `timeout` のエラーが返ること、同じセッションへの2本の並列の呼び出しがどちらも答えること。Runtime が並んだ呼び出しを通すか断るか（R12-01 の末尾の「確かめられなかった点」）は、ここで実機で確かめる。
- 計画を書くときに、使い捨ての作業ツリーで次を確かめた: 各テストは実装の前に落ち（Agent は 5 件が落ち、Backend は 9 件が落ちる）、実装後に通る。Agent は 96 → 104 件、Backend は 360 → 376 件。

## Global Constraints

- 作業するリポジトリは `Agent/`・`Backend/` と親。それぞれ `main` から `slice6-plan3` を切る（Task 0）。push・マージは、利用者が明示したときだけ。push の前に `pre-push-secret-scan`。デプロイと smoke は、実行のときに利用者の確認を取ってから行う（Task 5）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。ログに質問文・回答・位置を書かない（`budget_exhausted` のログは質問の識別子と段の名前だけ）。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`BE=$ROOT/Backend`、`AG=$ROOT/Agent`、`AGAPP=$AG/app/agentcore_trv2_dev_ask`。Backend のテストは `cd $BE && env/bin/pytest -q`、Agent のテストは `cd $AGAPP && .venv/bin/python -m pytest -q`（無ければ `uv sync`）。AWS は `AWS_PROFILE=touring`。
- エディタの編集は Edit・Write ツールで行う。

## Review Focus

- 時間切れのとき、Agent は履歴に何も書かない（質問だけが残る事態を作らない）。Task 1 のテスト `test_a_call_past_its_deadline_is_a_timeout_and_keeps_no_history` が押さえる。
- 錠の待ちが締め切りを超えるとき、待っていた呼び出しは Agent を動かさずに `timeout` で返る（Task 1 の最後のテスト）。
- 取り消された質問の呼び出しがまだ動いているうちに言い直しが届く → 言い直しは前の呼び出しの終わりを待ち、前の往復を含む履歴から始める（Task 1 の `calls_on_one_session_go_one_by_one`）。
- 残りが 5 秒に満たない質問は、Agent を呼ばず、音声も作らずに `failed`/`agent_failed` で終わる（Task 2）。TTS の手前で 110 秒を超えるほどの遅れは、余白 10 秒で吸収する。
- 締め切りの無い古い記録（デプロイの前に受け付けたもの）が、処理中のままデプロイを跨いでも、`receivedAt` から数え直されて壊れない（Task 2 のテスト）。
- 文字起こしだけの点メモの経路（`process_transcription`）が、上限 30 秒のまま動く（既存のテストが通ること）。
- Agent の `deadlineSeconds` に変な値（文字・負・真偽値・巨大な値）が来ても、既定の 100 秒で動く（Task 1）。

---

## ファイル構成

| パス | 役割 | Task |
|---|---|---|
| `Agent/app/agentcore_trv2_dev_ask/history.py` | `SessionLocks` | 1 |
| `…/config.py` | `default_deadline_seconds` | 1 |
| `…/handler.py` | 締め切り・錠 | 1 |
| `Agent/scripts/smoke.py` | 時間の上限と並列の確認 | 1 |
| `Backend/src/lib/budget.py`（新） | 締め切りと秒数の計算 | 2 |
| `Backend/src/lib/transcribe.py`・`agent.py`・`clients.py`・`asks.py` | 上限・`deadlineSeconds`・読みの時間切れ・`deadlineAt` | 2 |
| `Backend/src/handlers/worker.py` | 予算 | 2 |
| `docs/07_units_contracts.md`・`07b_datamodel.md`・`08b_backend-design.md`・`08c_agent-design.md`・各 README | 約束と説明 | 3 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: 3つのリポジトリでブランチを切り、今のテストを回す**

```bash
cd $AG && git switch main && git pull --ff-only && git switch -c slice6-plan3
cd $BE && git switch main && git pull --ff-only && git switch -c slice6-plan3
cd $AGAPP && .venv/bin/python -m pytest -q 2>&1 | tail -1
cd $BE && env/bin/pytest -q 2>&1 | tail -1
```

Expected: `96 passed`・`360 passed`。親は `slice6-plan3`（この plan を書いたブランチ）のまま。

---

### Task 1: Agent: 締め切りと錠（R5-02・R12-01）

**Files:**
- Modify: `Agent/app/agentcore_trv2_dev_ask/config.py`・`history.py`・`handler.py`、`tests/test_history.py`・`tests/test_handler.py`、`Agent/scripts/smoke.py`

**Interfaces:**
- Produces: `config.Settings.default_deadline_seconds`（既定 100.0。環境変数 `AGENT_DEFAULT_DEADLINE_SECONDS`）。`history.SessionLocks(max_locks=256)` と `.get(session_id) -> asyncio.Lock`。`handler.Deps.locks`（既定 `SessionLocks()`）。`handler.MAX_DEADLINE_SECONDS = 600.0`。呼び出しの本文の `deadlineSeconds`（数）と、締め切りを超えたときの `{"type": "error", "code": "timeout", "message": "deadline passed"}`。

- [ ] **Step 1: 失敗するテストを書く（錠）**

`tests/test_history.py` の import を `from history import SessionLocks, SessionStore, prune_history` にし、末尾に足す。

```python
def test_a_session_gets_the_same_lock_each_time():
    locks = SessionLocks()
    assert locks.get("s1") is locks.get("s1")
    assert locks.get("s1") is not locks.get("s2")


def test_old_locks_are_dropped_beyond_the_bound_but_one_in_use_stays():
    import asyncio

    async def scenario():
        locks = SessionLocks(max_locks=2)
        held = locks.get("busy")
        await held.acquire()
        locks.get("s1")
        locks.get("s2")
        locks.get("s3")
        assert locks.get("busy") is held
        assert len(locks._locks) <= 3  # the busy one stays even though it is the oldest

    asyncio.run(scenario())
```

- [ ] **Step 2: 失敗するテストを書く（締め切りと錠の呼び出し）**

`tests/test_handler.py` の末尾に足す。

```python


# Slice 6 plan 3 (adr/0014): a call is cut at the deadline the Backend sends, and calls on one session go one by one.
class SlowAgent(FakeAgent):
    def __init__(self, messages, final_text, delay):
        super().__init__(messages, [], final_text)
        self.delay = delay

    async def stream_async(self, prompt, invocation_state=None, limits=None):
        self.calls.append({"prompt": prompt})
        self.messages.append(user(prompt))
        await asyncio.sleep(self.delay)
        self.messages.append(assistant(self._final_text))
        yield {"result": make_result(self._final_text)}


def test_a_call_past_its_deadline_is_a_timeout_and_keeps_no_history():
    sessions = SessionStore()
    sessions.put("s1", [user("Q0"), assistant("A0")])
    deps, _ = make_deps(agent=SlowAgent([user("Q0"), assistant("A0")], "late", delay=5), sessions=sessions)
    events = run({"prompt": "Q1", "deadlineSeconds": 0.05}, deps)
    assert events == [{"type": "error", "code": "timeout", "message": "deadline passed"}]
    assert sessions.get("s1") == [user("Q0"), assistant("A0")]


def test_without_a_deadline_the_default_applies():
    deps, _ = make_deps(agent=SlowAgent([], "late", delay=5))
    deps.settings = load_settings({"AGENT_DEFAULT_DEADLINE_SECONDS": "0.05"})
    assert run({"prompt": "Q1"}, deps)[-1]["code"] == "timeout"


def test_a_deadline_that_is_not_a_sensible_number_is_ignored():
    for bad in ("soon", None, True, 0, -3, 100000):
        deps, _ = make_deps(agent=SlowAgent([], "late", delay=5))
        deps.settings = load_settings({"AGENT_DEFAULT_DEADLINE_SECONDS": "0.05"})
        assert run({"prompt": "Q1", "deadlineSeconds": bad}, deps)[-1]["code"] == "timeout", bad


def test_a_call_within_its_deadline_is_not_cut():
    deps, _ = make_deps(agent=SlowAgent([], "ok", delay=0.01))
    events = run({"prompt": "Q1", "deadlineSeconds": 5}, deps)
    assert events[-1]["type"] == "done" and events[-1]["answer"] == "ok"


def test_calls_on_one_session_go_one_by_one_and_keep_both_turns():
    sessions = SessionStore()
    first = SlowAgent([], "A1", delay=0.2)
    second = SlowAgent([], "A2", delay=0.0)
    seen = []

    def factory(model_id, messages):
        agent = first if not seen else second
        seen.append(list(messages))
        agent.messages = list(messages)
        return agent

    deps, _ = make_deps(sessions=sessions)
    deps.agent_factory = factory

    async def both():
        async def one(prompt):
            return [event async for event in handle({"prompt": prompt, "deadlineSeconds": 5}, "s1", deps)]

        slow = asyncio.create_task(one("Q1"))
        await asyncio.sleep(0.05)  # the first call is in the middle of its work
        fast = asyncio.create_task(one("Q2"))
        return await asyncio.gather(slow, fast)

    asyncio.run(both())
    # The second call starts from the history that already holds the first one's turn.
    assert seen == [[], [user("Q1"), assistant("A1")]]
    assert sessions.get("s1") == [user("Q1"), assistant("A1"), user("Q2"), assistant("A2")]


def test_the_wait_for_a_busy_session_counts_against_the_deadline():
    sessions = SessionStore()
    busy = SlowAgent([], "A1", delay=0.3)
    other = SlowAgent([], "A2", delay=0.0)
    deps, _ = make_deps(agent=busy, sessions=sessions)
    deps.agent_factory = lambda model_id, messages: busy if not busy.calls else other

    async def both():
        async def one(payload):
            return [event async for event in handle(payload, "s1", deps)]

        slow = asyncio.create_task(one({"prompt": "Q1", "deadlineSeconds": 5}))
        await asyncio.sleep(0.05)
        impatient = await one({"prompt": "Q2", "deadlineSeconds": 0.05})
        return impatient, await slow

    impatient, slow = asyncio.run(both())
    assert impatient == [{"type": "error", "code": "timeout", "message": "deadline passed"}]
    assert other.calls == [] and slow[-1]["type"] == "done"
```

- [ ] **Step 3: 落ちることを確かめる**

Run: `cd $AGAPP && .venv/bin/python -m pytest -q tests/test_history.py tests/test_handler.py 2>&1 | tail -9`
Expected: `7 failed`（`SessionLocks` が無い 2 件、締め切りと錠の 5 件。`test_a_call_within_its_deadline_is_not_cut` は今のコードでも通る）。時間切れのテストは、上限が無いので 5 秒眠って落ちる。

- [ ] **Step 4: 設定・錠・呼び出しを実装する**

`config.py`: `Settings` の `mcp_max_idle_seconds: float = 600.0` の次に足す。

```python
    # How long a call may take when the Backend sends no deadline (adr/0014); the Backend's own is shorter.
    default_deadline_seconds: float = 100.0
```

`load_settings` の `mcp_max_idle_seconds=...` の次の行に足す。

```python
        default_deadline_seconds=float(env.get("AGENT_DEFAULT_DEADLINE_SECONDS", "100")),
```

`history.py`: import に `import asyncio` を足し（`import copy` の上）、末尾に足す。

```python


class SessionLocks:
    """One lock per runtime session, so that calls on one session go one by one: each starts from the history the one
    before it left (Agent #6, adr/0014). Bounded like the histories; a lock in use is never dropped."""

    def __init__(self, max_locks: int = 256) -> None:
        self._max_locks = max_locks
        self._locks: OrderedDict[str, asyncio.Lock] = OrderedDict()

    def get(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = self._locks[session_id] = asyncio.Lock()
        self._locks.move_to_end(session_id)
        for old_id in list(self._locks):
            if len(self._locks) <= self._max_locks:
                break
            if not self._locks[old_id].locked() and old_id != session_id:
                del self._locks[old_id]
        return lock
```

`handler.py`:

- `from dataclasses import dataclass` → `from dataclasses import dataclass, field`。`from history import SessionStore, prune_history` → `from history import SessionLocks, SessionStore, prune_history`。
- `_CUT_OFF_TOOL = re.compile(...)` の行の次に足す。

```python
# The longest a call may be told to take; a longer number is taken as a mistake.
MAX_DEADLINE_SECONDS = 600.0
```

- `Deps` の `agent_factory: Callable[[str, list[dict]], Any]` の次に足す。

```python
    locks: SessionLocks = field(default_factory=SessionLocks)
```

- `_prompt` の次（`_settle_cut_off` の前）に足す。

```python
def _deadline_seconds(payload: dict, settings: Settings) -> float:
    """How long this call may take: what the Backend sent (adr/0014), or the default when it sent nothing sensible."""
    value = payload.get("deadlineSeconds")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= MAX_DEADLINE_SECONDS:
        return float(value)
    return settings.default_deadline_seconds
```

- `handle` を次のように分ける。今の `async def handle(...)` の `if not prompt: ... return` までを残し、その次の `try:` から最後までを `_run` に移す。

```python
async def handle(payload: dict, session_id: str, deps: Deps) -> AsyncIterator[dict]:
    prompt = _prompt(payload)
    if not prompt:
        yield error_event("bad_request", "prompt is required")
        return
    try:
        # The wait for the session's lock counts against the deadline too. A cut call keeps no history (adr/0014).
        async with asyncio.timeout(_deadline_seconds(payload, deps.settings)):
            async with deps.locks.get(session_id):
                async for event in _run(payload, prompt, session_id, deps):
                    yield event
    except TimeoutError:
        _log({"event": "invoke_failed", "session": session_id, "reason": "timeout"})
        yield error_event("timeout", "deadline passed")


async def _run(payload: dict, prompt: str, session_id: str, deps: Deps) -> AsyncIterator[dict]:
    try:
        # Blocking (SSM); a worker thread keeps the event loop, and /ping, answering (Agent #4).
        （ここから後ろは、今の `handle` の `try:` の中身と、それ以降をそのまま）
```

- [ ] **Step 5: 通ることを確かめる**

Run: `cd $AGAPP && .venv/bin/python -m pytest -q 2>&1 | tail -2`
Expected: `104 passed`。

- [ ] **Step 6: smoke に2つの確認を足す**

`Agent/scripts/smoke.py`:

- `import sys` の次に `import threading` を足す。
- `invoke` の定義を次にする（`deadline` が増える）。

```python
def invoke(client, arn: str, session_id: str, question: str, location: dict | None, deadline: float | None = None) -> list[dict]:
    payload = {"prompt": FACTS + "質問: " + question, "location": location}
    if deadline is not None:
        payload["deadlineSeconds"] = deadline
```

（続く `response = client.invoke_agent_runtime(...)` 以下は今のまま。）

- `check` の次（`main` の前）に足す。

```python
def check_timeout(client, arn: str) -> bool:
    """A call told it has 2 seconds is cut and says so (adr/0014): an error "timeout", no answer."""
    events = invoke(client, arn, f"smoke-{uuid.uuid4()}", "今日の東京の天気は？", TOKYO_STATION, deadline=2)
    errors = [e for e in events if e.get("type") == "error"]
    ok = bool(errors) and errors[-1].get("code") == "timeout" and not any(e.get("type") == "done" for e in events)
    print(f"[{'OK' if ok else 'NG'}] 時間の上限: events={[e.get('type') for e in events]} errors={errors}")
    return ok


def check_one_by_one(client, arn: str) -> bool:
    """Two calls on one session at the same time both get answered, one after the other (Agent #6, adr/0014)."""
    session = f"smoke-{uuid.uuid4()}"
    got: dict[str, list[dict]] = {}

    def ask(name: str, question: str) -> None:
        try:
            got[name] = invoke(client, arn, session, question, TOKYO_STATION)
        except Exception as error:  # noqa: BLE001 - e.g. the Runtime turning the second call away
            got[name] = [{"type": "error", "code": type(error).__name__}]

    threads = [threading.Thread(target=ask, args=("a", "富士山の高さは？")), threading.Thread(target=ask, args=("b", "東京タワーの高さは？"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    ok = len(got) == 2 and all(any(e.get("type") == "done" for e in events) and not any(e.get("type") == "error" for e in events) for events in got.values())
    types = {name: [e.get("type") for e in events] for name, events in got.items()}
    print(f"[{'OK' if ok else 'NG'}] 同じセッションの2本: {types}")
    return ok
```

- `main` の `results = [...]` の最後（`check("現在地なし", ...)` の次の行）に足す。

```python
        check_timeout(client, arn),
        check_one_by_one(client, arn),
```

Run: `cd $AG && python3 -m py_compile scripts/smoke.py && echo compiled`
Expected: `compiled`（実機での確認は Task 5）。

- [ ] **Step 7: コミット**

```bash
cd $AG && git add app/agentcore_trv2_dev_ask/config.py app/agentcore_trv2_dev_ask/history.py app/agentcore_trv2_dev_ask/handler.py app/agentcore_trv2_dev_ask/tests/test_history.py app/agentcore_trv2_dev_ask/tests/test_handler.py scripts/smoke.py
cd $AG && git commit -m "feat: cut an agent call at the deadline the Backend sends and run the calls of one session one by one (adr/0014)"
```

---

### Task 2: Backend: 締め切りと予算（R11-01・R4-02 の時間切れ）

**Files:**
- Create: `src/lib/budget.py`、`tests/test_budget.py`
- Modify: `src/lib/transcribe.py`・`agent.py`・`clients.py`・`asks.py`、`src/handlers/worker.py`、`tests/test_transcribe.py`・`test_agent.py`・`test_ask.py`・`test_worker.py`

**Interfaces:**
- Produces: `budget.DEADLINE_SECONDS = 110`・`SYNTHESIS_MARGIN_SECONDS = 10`・`LAMBDA_MARGIN_SECONDS = 5`・`MIN_AGENT_SECONDS = 5`・`TRANSCRIBE_SECONDS = 30`・`AGENT_READ_TIMEOUT_SECONDS = 105`、`budget.deadline_for(received_at) -> datetime`、`budget.agent_seconds(deadline, now, lambda_ms=None) -> float`。質問の記録の `deadlineAt`（ISO 文字列）。`transcribe.transcribe_pcm(audio, timeout=30)`（超えたら `TimeoutError`）。`agent.invoke(..., deadline_seconds=None)`（本文に `deadlineSeconds`）。`worker.process(user, ask_id, steps, remaining_ms=None)`、`Steps.invoke_agent(prompt, location, session_id, seconds)`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_budget.py`:

```python
"""The time one ask may take, from the moment it is accepted (adr/0014)."""
from datetime import datetime, timedelta, timezone

from lib import budget, clients

T0 = datetime(2026, 10, 16, 3, 0, tzinfo=timezone.utc)


def test_the_deadline_is_110_seconds_after_the_acceptance():
    assert budget.deadline_for(T0) == T0 + timedelta(seconds=110)


def test_the_agent_gets_what_is_left_less_the_margin_for_the_speech():
    # 100 s left to the deadline, 10 s kept for Polly and the writes.
    assert budget.agent_seconds(T0 + timedelta(seconds=110), T0 + timedelta(seconds=10)) == 90


def test_the_lambdas_own_time_limits_it_too():
    deadline = T0 + timedelta(seconds=110)
    # 40 s left in the Lambda, 5 s kept: 35 s, less 10 s for the speech.
    assert budget.agent_seconds(deadline, T0, lambda_ms=40_000) == 25
    # A Lambda with more time left than the deadline does not stretch the deadline.
    assert budget.agent_seconds(deadline, T0, lambda_ms=500_000) == 100


def test_nothing_is_left_after_the_deadline():
    assert budget.agent_seconds(T0, T0 + timedelta(seconds=30)) < budget.MIN_AGENT_SECONDS


def test_the_agent_is_read_for_longer_than_it_may_run():
    assert budget.AGENT_READ_TIMEOUT_SECONDS > budget.DEADLINE_SECONDS - budget.SYNTHESIS_MARGIN_SECONDS


def test_the_agent_client_waits_for_the_agents_own_timeout_error(aws):
    assert clients.agentcore().meta.config.read_timeout == budget.AGENT_READ_TIMEOUT_SECONDS
```

`tests/test_transcribe.py` の末尾に足す。

```python


def test_a_transcription_that_takes_too_long_is_cut(monkeypatch):
    import asyncio

    import pytest

    async def slow(audio):
        await asyncio.sleep(5)
        return "never"

    monkeypatch.setattr(transcribe, "_transcribe", slow)
    with pytest.raises(TimeoutError):
        transcribe.transcribe_pcm(b"\x00\x00", timeout=0.05)
```

`tests/test_agent.py` の末尾に足し、`test_agentcore_client_never_retries_on_its_own` の `assert config.read_timeout <= 90` を次の2行に替える。

```python


def test_invoke_sends_the_deadline_when_it_has_one():
    client = FakeClient([sse(DONE)])
    invoke("P", None, "s" * 36, client=client, deadline_seconds=84.5)
    assert json.loads(client.calls[0]["payload"])["deadlineSeconds"] == 84.5


def test_invoke_sends_no_deadline_when_it_has_none():
    client = FakeClient([sse(DONE)])
    invoke("P", None, "s" * 36, client=client)
    assert "deadlineSeconds" not in json.loads(client.calls[0]["payload"])
```

```python
    # One long read still fits the worker's 120 s Lambda (adr/0014).
    assert config.read_timeout < 120
```

`tests/test_ask.py` の末尾に足す。

```python


def test_the_record_keeps_the_deadline_110_seconds_after_the_acceptance(aws):
    from datetime import timedelta

    from handlers.common import parse_iso

    body = json.loads(call({"text": "富士山の高さは？"})["body"])
    item = store.get_ask("rider01", body["askId"])
    assert parse_iso(item["deadlineAt"]) - parse_iso(item["receivedAt"]) == timedelta(seconds=110)
```

`tests/test_worker.py`:

- `Recorder.__init__` の `self.calls = []` の次の行に `self.deadlines = []` を足す。
- `Recorder.invoke_agent` を次にする（呼び出しの記録 `calls` の形は変えない）。

```python
    def invoke_agent(self, prompt, location, session_id, deadline_seconds=None):
        self.calls.append(("agent", prompt, location, session_id))
        self.deadlines.append(deadline_seconds)
```

（続く `if self.agent_error: raise ...` 以下は今のまま。）
- `test_an_ask_deleted_while_it_is_answered_is_not_written_back` の作り物を次にする。

```python
    def delete_then_answer(prompt, location, session, deadline_seconds=None):
        # The rider deletes the ask while the agent is answering (slice 3 spec §6.3).
        aws.table.delete_item(Key=store.ask_key(USER, ASK))
        return agent(prompt, location, session, deadline_seconds)
```

- 末尾に足す。

```python


# adr/0014: the ask has until its deadline, and the agent is told how long it has.
def test_the_agent_is_told_how_long_it_has(aws):
    put(aws)
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())
    # Accepted at T0, deadline T0 + 110 s; the fake clock has moved a few seconds by the time the agent is called.
    assert rec.deadlines and 85 <= rec.deadlines[0] <= 100


def test_a_deadline_on_the_record_is_the_one_that_counts(aws):
    put(aws, receivedAt=iso(T0 - timedelta(seconds=500)), deadlineAt=iso(T0 + timedelta(seconds=60)))
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())
    assert 35 <= rec.deadlines[0] <= 50  # 60 s left less the 10 s for the speech, a few seconds gone


def test_a_record_without_a_deadline_gets_one_from_its_acceptance(aws):
    # An ask accepted before the deadline was kept: 110 s after its receipt, which was 20 s ago.
    put(aws, receivedAt=iso(T0 - timedelta(seconds=20)))
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())
    assert 60 <= rec.deadlines[0] <= 80


def test_an_ask_with_no_time_left_fails_without_calling_the_agent(aws):
    put(aws, receivedAt=iso(T0 - timedelta(seconds=100)))
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())
    item = store.get_ask(USER, ASK)
    assert "agent" not in kinds(rec) and "tts" not in kinds(rec)
    assert item["status"] == "failed" and item["error"] == "agent_failed"


def test_the_lambdas_own_time_can_be_what_runs_out(aws):
    put(aws)
    rec = Recorder()
    worker.process(USER, ASK, rec.steps(), remaining_ms=lambda: 12_000)
    item = store.get_ask(USER, ASK)
    assert "agent" not in kinds(rec) and item["status"] == "failed" and item["error"] == "agent_failed"


def test_the_agents_own_timeout_is_a_failed_ask(aws):
    put(aws)
    rec = Recorder(agent_error=AgentError("timeout"))
    worker.process(USER, ASK, rec.steps())
    item = store.get_ask(USER, ASK)
    assert item["status"] == "failed" and item["error"] == "agent_failed"
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q --continue-on-collection-errors 2>&1 | tail -14`
Expected: `tests/test_budget.py` の収集で `ImportError`（`lib.budget` が無い）と、ほかに 8 件の失敗（`deadlineAt` が無い・`remaining_ms` を受けない・`deadline_seconds` を受けない・`timeout` を受けない など）。

- [ ] **Step 3: `lib/budget.py` を書く**

```python
"""The time one ask may take, from the moment it is accepted (adr/0014). Android waits 120 s for the answer; the
Backend and the agent stop earlier, so that a cut-off ask is told to the rider as a failure, not left running."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

# From the acceptance to the written answer.
DEADLINE_SECONDS = 110
# Kept for Polly and the writes after the agent has answered.
SYNTHESIS_MARGIN_SECONDS = 10
# Kept from the worker Lambda's own remaining time.
LAMBDA_MARGIN_SECONDS = 5
# An agent call with less than this is not worth starting.
MIN_AGENT_SECONDS = 5
# The most a transcription may take; a memo or a question is at most a minute of speech.
TRANSCRIBE_SECONDS = 30
# One read from the agent's stream. Longer than the agent may run, so that the agent's own timeout error is what the
# worker reads, not a socket timeout.
AGENT_READ_TIMEOUT_SECONDS = 105


def deadline_for(received_at: datetime) -> datetime:
    return received_at + timedelta(seconds=DEADLINE_SECONDS)


def agent_seconds(deadline: datetime, now: datetime, lambda_ms: Optional[int] = None) -> float:
    """How long the agent may take: what is left to the deadline, or of the Lambda's time, less the margin for the
    speech. Below MIN_AGENT_SECONDS there is no time for it."""
    left = (deadline - now).total_seconds()
    if lambda_ms is not None:
        left = min(left, lambda_ms / 1000 - LAMBDA_MARGIN_SECONDS)
    return left - SYNTHESIS_MARGIN_SECONDS
```

- [ ] **Step 4: 上限・本文・読みの時間切れ・記録を直す**

`src/lib/transcribe.py`: import の `from amazon_transcribe.model import TranscriptEvent` の次に空行を挟んで `from lib import budget` を足し、`transcribe_pcm` を次にする。

```python
def transcribe_pcm(audio: bytes, timeout: float = budget.TRANSCRIBE_SECONDS) -> str:
    """Raises TimeoutError when the transcription takes longer than timeout seconds (adr/0014)."""
    return asyncio.run(asyncio.wait_for(_transcribe(audio), timeout))
```

`src/lib/agent.py` の `invoke` を次の形にする（引数は末尾に `deadline_seconds` を足す。`for attempt in range(attempts):` 以下は今のまま）。

```python
def invoke(
    prompt: str,
    location: Optional[dict],
    session_id: str,
    client: Any = None,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    deadline_seconds: Optional[float] = None,
) -> AgentReply:
    """deadline_seconds is how long the agent may take (adr/0014); it cuts the call there and says so with a
    "timeout" error."""
    client = client or clients.agentcore()
    body: dict = {"prompt": prompt, "location": location}
    if deadline_seconds is not None:
        body["deadlineSeconds"] = deadline_seconds
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
```

`src/lib/clients.py`: `from botocore.config import Config` の次に空行を挟んで `from lib import budget` を足し、`agentcore()` の説明と設定を次にする。

```python
    # The agent lives in another region; its stream can take a while, so allow a long read (longer than the agent
    # may run, so that its own timeout error is what is read, adr/0014), but never let botocore resend on its own: a
    # second call would repeat the question in the conversation, and two long reads would outlive the worker's 120 s
    # timeout.
    return boto3.client(
        "bedrock-agentcore",
        region_name=os.environ.get("AGENT_REGION", "us-east-1"),
        config=Config(read_timeout=budget.AGENT_READ_TIMEOUT_SECONDS, retries={"total_max_attempts": 1}),
    )
```

`src/lib/asks.py`: `from lib import store` → `from lib import budget, store`。`new_ask` の `"receivedAt": iso(now),` の次に足す。

```python
        # The time the ask has to be answered by; the worker and the agent stop there (adr/0014).
        "deadlineAt": iso(budget.deadline_for(now)),
```

- [ ] **Step 5: worker を直す**

`src/handlers/worker.py`:

- `from lib import address, agent, clients, speech, store, transcribe` → `from lib import address, agent, budget, clients, speech, store, transcribe`。
- `Steps` の `invoke_agent: Callable[[str, Optional[dict], str], AgentReply]` → `invoke_agent: Callable[[str, Optional[dict], str, float], AgentReply]`。
- `DEFAULT_STEPS = ...` の行を次の4行に替える。

```python
def _invoke_agent(prompt: str, location: Optional[dict], session: str, seconds: float) -> AgentReply:
    return agent.invoke(prompt, location, session, deadline_seconds=seconds)


DEFAULT_STEPS = Steps(transcribe.transcribe_pcm, address.describe_location, _invoke_agent, speech.synthesize, utc_now)
```

- `def process(user: str, ask_id: str, steps: Steps) -> None:` → `def process(user: str, ask_id: str, steps: Steps, remaining_ms: Optional[Callable[[], int]] = None) -> None:`。`_run(user, ask_id, item, steps)` → `_run(user, ask_id, item, steps, remaining_ms)`。
- `def _run(user: str, ask_id: str, item: dict, steps: Steps) -> None:` → `def _run(user: str, ask_id: str, item: dict, steps: Steps, remaining_ms: Optional[Callable[[], int]] = None) -> None:`。`mark` を次にする（呼ぶ時計の回数は同じ）。

```python
    def mark(name: str) -> datetime:
        at = steps.now()
        timings[name] = iso(at)
        return at
```

- `mark("factsAt")` から `reply = steps.invoke_agent(...)` の行までを、次に替える。

```python
    facts_at = mark("factsAt")
    facts = {"transcript": transcript, "address": place, "headingDegrees": heading}

    # The ask has until its deadline (adr/0014); the agent is told how long it has, and is not called with none left.
    deadline = parse_iso(item["deadlineAt"]) if item.get("deadlineAt") else budget.deadline_for(received_at)
    seconds = budget.agent_seconds(deadline, facts_at, remaining_ms() if remaining_ms else None)
    if seconds < budget.MIN_AGENT_SECONDS:
        mark("agentDoneAt")
        log({"event": "budget_exhausted", "askId": ask_id, "stage": "agent"})
        finish("failed", "agent_failed", **facts)
        return

    try:
        reply = steps.invoke_agent(prompt, agent_location(location, heading), session_id(user, item["conversationId"]), seconds)
```

（`except Exception as error:` 以下は今のまま。）

- `handler` の `process(message["userName"], message["askId"], DEFAULT_STEPS)` を次にする。

```python
            process(message["userName"], message["askId"], DEFAULT_STEPS,
                    getattr(context, "get_remaining_time_in_millis", None))
```

- [ ] **Step 6: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -2`
Expected: `376 passed`。

- [ ] **Step 7: コミット**

```bash
cd $BE && git add src/lib/budget.py src/lib/transcribe.py src/lib/agent.py src/lib/clients.py src/lib/asks.py src/handlers/worker.py tests/test_budget.py tests/test_transcribe.py tests/test_agent.py tests/test_ask.py tests/test_worker.py
cd $BE && git commit -m "feat: give an ask a deadline from its acceptance, and have the worker and the agent stop there (adr/0014)"
```

---

### Task 3: 文書と issue

**Files:**
- Modify: `docs/07_units_contracts.md`・`docs/07b_datamodel.md`・`docs/08b_backend-design.md`・`docs/08c_agent-design.md`（親）、`Backend/README.md`・`Agent/README.md`

- [ ] **Step 1: 07 の約束を直す**

`docs/07_units_contracts.md`:

- UC-5 の「取りに行く処理は必ず止まるように作る。…打ち切りや取り消しの後も、Backend の処理は続いてよい。」の最後の一文を、次にする。

```
Backend と Agent は、受け付けから決めた締め切り（110秒後）で打ち切り、質問を失敗（`agent_failed`）として終える。Android が取り消したあとも、締め切りまでは処理が続く（[adr/0014](../adr/0014-ask-time-budget-from-acceptance.md)）。
```

- UC-8 の「渡すもの」の「呼び出しの本文は JSON の …」の文を、`"deadlineSeconds": <数値>` を足した形にし、その段落の次に次の箇条を足す。

```
- `deadlineSeconds` は、Agent が回答を出すまでにかけてよい秒数（受け付けの締め切りから、音声の合成の余白を引いた残り）。Agent はこの時間で打ち切る。来ない・数でないときは Agent の既定（100秒）を使う。Backend の読みの時間切れ（105秒）は、これより長くする。
```

- UC-8 の「応答」の「失敗のときは `done` の代わりに `error` が来る。…」の文を、次にする。

```
- 失敗のときは `done` の代わりに `error` が来る。`code` は `bad_request`（本文が不正）・`agent_failed`（モデル ID が読めない・モデルの失敗・上限でないのに回答が空）・`timeout`（`deadlineSeconds` を超えた。履歴は残さない）。Backend はどれも `agent_failed` として扱う。
```

- UC-8 の「呼び出し」の「Agent は同じ識別子が来るあいだ文脈を続ける。」の文の次に、次を足す。

```
同じ識別子への呼び出しが重なったときは、Agent が1つずつ処理する（後の呼び出しは前の呼び出しの往復を含む履歴から始める）。
```

`docs/07b_datamodel.md` の質問の行の列（「日時・位置・住所・…」）に「締め切りの日時」を足す。

`docs/08b_backend-design.md` §5 の「Agent の呼び出しは自動で送り直さない」の箇条の次に足す。

```
- 質問は受け付けの締め切り（110秒後）まで。worker は文字起こしと Agent の呼び出しを残りの時間で包み、尽きたら `agent_failed` で終える（[adr/0014](../adr/0014-ask-time-budget-from-acceptance.md)）。
```

`docs/08c_agent-design.md` §3 に足す。

```
- 同じセッションへの呼び出しは、錠で1つずつ処理する。呼び出しは、Backend が渡す秒数（無ければ既定）で打ち切り、打ち切った呼び出しは履歴を残さない（[adr/0014](../adr/0014-ask-time-budget-from-acceptance.md)）。
```

`Agent/README.md` の「振る舞い」に、同じ2点を1項目で足す（`AGENT_DEFAULT_DEADLINE_SECONDS`・`timeout` のエラー・錠）。`Backend/README.md` の「流れ」2に「質問の記録に締め切りを残し、Agent に残りの秒数を渡す」を足す。

- [ ] **Step 2: 写してコミットする**

```bash
cd $ROOT && ./scripts/sync-docs.sh Android Backend Agent CICD
cd $BE && git add README.md docs-parent && git commit -m "docs: describe the ask deadline in the README and sync the parent's docs"
cd $AG && git add README.md docs-parent && git commit -m "docs: describe the deadline and the session lock in the README and sync the parent's docs"
cd $ROOT && git status --short
cd $ROOT && git add docs/07_units_contracts.md docs/07b_datamodel.md docs/08b_backend-design.md docs/08c_agent-design.md && git commit -m "docs: write the ask deadline, the timeout error and the session lock into the contracts (adr/0014)"
```

Android・CICD の `docs-parent/` が変わっていたら、それぞれの `main` に直接コミットする（PROJECT.md の「前提」）。`scripts/check_links.py` のリンク切れは `Backend/env/` の中の1件だけ（既知）。

- [ ] **Step 3: Agent #6 を開き直す**

```bash
cd $AG && gh issue reopen 6 --comment "Reopened: the premise it was closed on (no next ask while one is waiting) does not hold once Android cancels or times out and the rider asks again (docs/final-review/2026-10-28/issues.md R12-01). Fixed by the session lock and the deadline in slice 6 plan 3 (adr/0014)."
```

Agent #6 は、Agent の PR の本文に `Fixes #6` を書いて、マージで閉じる（Task 6）。

---

### Task 4: 全体の確かめ・PROJECT.md

- [ ] **Step 1: 全体のテスト**

```bash
cd $AGAPP && .venv/bin/python -m pytest -q 2>&1 | tail -1
cd $BE && env/bin/pytest -q 2>&1 | tail -1
cd $BE && (cfn-lint template.yaml && echo "cfn-lint OK")
```

Expected: `104 passed`・`376 passed`・`cfn-lint OK`。

- [ ] **Step 2: PROJECT.md を更新して親でコミットする**

plan 表の 3 の行を「実装済み（確認待ち: デプロイと smoke。Agent pytest 104件・Backend pytest 376件）」にし、「次にやること」の2を「plan 3 のデプロイと smoke（Task 5。利用者の確認を取ってから）」にする。親の submodule の指す先は、各ブランチの先頭に進める。

```bash
cd $ROOT && git add PROJECT.md Agent Backend && git commit -m "docs: record slice 6 plan 3 as implemented, awaiting the deploy and smoke"
```

---

### Task 5: デプロイと smoke（利用者の確認を取ってから）

デプロイは AWS に触れ、smoke は LLM を数回呼ぶ。実行のときに利用者に確認する。**Agent を先に、Backend をあとにデプロイする**（Backend が `deadlineSeconds` を送っても、古い Agent は読み飛ばすだけで害は無いが、新しい Agent を先に置くと Backend の新しい動きがすぐ実機に効く）。

- [ ] **Step 1: 利用者の確認を取る**

「Agent と Backend をデプロイして、smoke を回します（Agent の smoke は LLM を 8 回、Backend の smoke は質問の通しで数回、呼びます）。よいですか」と聞く。

- [ ] **Step 2: Agent をデプロイする**

```bash
cd $AG && AWS_PROFILE=touring AWS_REGION=us-east-1 npx -y @aws/agentcore@0.31.1 deploy -y
ARN=$(AWS_PROFILE=touring aws bedrock-agentcore-control list-agent-runtimes --region us-east-1 \
  --query "agentRuntimes[?agentRuntimeName=='trv2Agent_agentcore_trv2_dev_ask'].agentRuntimeArn" --output text)
echo "$ARN" | sed 's/[0-9]\{12\}/<account>/'
```

Expected: デプロイが成功し、ARN が1つ出る（アカウント ID は書き写さない）。

- [ ] **Step 3: Agent の smoke を回す（時間の上限と並列を含む）**

```bash
cd $AG && AWS_PROFILE=touring uv run --project app/agentcore_trv2_dev_ask python scripts/smoke.py "$ARN" 2>&1 | tail -12
```

Expected: `7/7 passed`。**「同じセッションの2本」が NG のとき**は、出力の `types` を読む。Runtime が2本目を断る作り（`RetryableConflictException` など）なら、Agent の錠は働かず、Backend の試し直し（0.5 秒・1 秒）が頼りになる。その場合は止まって利用者に報告する（Backend の `agent.invoke` の試し直しの間隔を、ツールを使う質問の長さに合わせて見直す、が次の手）。

- [ ] **Step 4: Backend をデプロイして smoke を回す**

```bash
cd $BE && AWS_PROFILE=touring sam build && AWS_PROFILE=touring sam deploy --no-confirm-changeset
cd $BE && AWS_PROFILE=touring env/bin/python scripts/smoke.py 2>&1 | tail -4
```

Expected: `40/40 passed`。デプロイの直後に新しい経路だけが 403 なら、1分ほど待って回し直す。

- [ ] **Step 5: PROJECT.md を更新して親でコミットする**

plan 表の 3 の行を「✅ 完了（デプロイ済み・Agent の smoke 7/7・Backend の smoke 40/40。Agent #6 は PR のマージで閉じる）」にする。

```bash
cd $ROOT && git add PROJECT.md && git commit -m "docs: record slice 6 plan 3 as deployed with the smoke runs passing"
```

---

### Task 6: PR とマージ（利用者が指示したときだけ）

- [ ] **Step 1: 利用者の指示を待つ**

指示があったら、`pre-push-secret-scan` をかけて報告し、承認を取ってから push する。順は Agent → Backend → 親（親は submodule の指す先をマージ後の `main` に進める）。Agent の PR の本文に `Fixes #6` を書く。
