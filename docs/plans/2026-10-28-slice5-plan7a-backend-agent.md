# スライス5 計画7a: Backend と Agent（途中で立てた指摘） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** スライス5の途中で立てた Backend と Agent の後回しの指摘（Backend #29〜#31・#33、Agent #9・#10）を直す。両方をデプロイして、Backend の smoke と Agent の smoke を通す。
- 受け付けた時点で方位を丸め、プロンプトの度数で 360 を 0 にする（Backend #29）
- 削除の跡の読み直しに回数の上限を付ける（Backend #30）
- 質問できなかった地点の方位の決め方にコメントを足す（Backend #31）
- README の削除の跡を確かめる書き込みに、質問できなかった地点を足す（Backend #33）
- モデルの出力のトークンの上限で止まっても、失敗でなく回答を返す（Agent #9）
- エージェントの組み立てを1つずつにし、MCP の接続の開始がぶつからないようにする（Agent #10）

**Architecture:** どちらのユニットも、今の作りのまま。
- Backend は、`handlers/ask.py` で `lib/geo.settled_heading` を通す。`lib/prompt.py` の度数に `% 360` を付ける。`lib/store.has_deletion_mark` の読み直しを `_MARK_READS`（5回）で打ち切る。
- Agent は、`handler.py` で Strands の `MaxTokensReachedException` を受け、`_settle_cut_off` で回答を決める。`main.build_agent` を `threading.Lock` で囲む。

**Tech Stack:**
- Backend: Python・AWS SAM・pytest・moto
- Agent: Python 3.14（`uv`）・Strands Agents・Bedrock AgentCore Runtime・pytest
- 足すものは無い。

**Spec:** [docs/specs/2026-10-25-slice5-design.md](../specs/2026-10-25-slice5-design.md)（§15・§13 の plan 7a）。

**範囲に入れた issue:** Backend #29・#30・#31・#33、Agent #9・#10（spec §15.1）。
- Agent #11 は spec のコミットで閉じた（spec §15.2）。
- Backend #28・Agent #8 は含めない（spec §15.1）。

**計画を書くときに決めたこと（spec からの具体化）:**
- Backend #29 のテストは `tests/test_ask.py` に置く。issue の案の `tests/test_worker.py` は、質問の記録を `POST /asks` を通さずに作るので、受け付けの丸めを確かめられない。
- Backend #30 の上限は、読み取りの回数で5回（4回目の読み直しまで）。待つのは 50・100・200・400ms で、計 750ms。
- Agent #9: Strands（1.61 系）は、出力の上限で止まると次の順に動く。
  1. 返ってきた文のうち、ツールの呼び出しを英語の決まり文句（`The selected tool <名前>'s tool use was incomplete due to maximum token limits being reached.`）に置き換える。
  2. それを履歴（`agent.messages`）の最後に足す。
  3. `MaxTokensReachedException` を投げる。`result` は来ない。

  そのため、回答は次のように決める。
  - 履歴の最後の文のうち、決まり文句を除いた文を回答にする。無ければ `LIMIT_ANSWER`。英語の決まり文句を読み上げないため。
  - 履歴の最後をその回答に置き換える（質問と回答が交互のままになるように）。
  - `done` の `stopReason` は `max_tokens`。使ったトークンは `agent.event_loop_metrics` から読む。
  - 決まり文句は Strands の文言に頼るので、本物の `Agent` に作り物のモデル（`CutOffModel`）を組んだテストで確かめる。
- Agent #9 のコメント直し: `LIMIT_ANSWER` のコメントは「周回の上限か、出力のトークンの上限」になる（#9 の直しで、出力の上限も実際に扱うようになるため）。
- Agent #10: ロックは `main.build_agent` 全体に掛ける。MCP の `start()` は `Agent(...)` の中の `load_tools` で呼ばれるので、`for_question()` だけを囲んでも足りない。テストは、遅い作り物の `ToolProvider` を2つのスレッドで同時に組み、`load_tools` の中に同時に入るのが1つだけであることを確かめる。
- 親の `docs/07_units_contracts.md`（UC-8 の応答）と `docs/08c_agent-design.md`（§1 の4）に、出力の上限のときの回答を書いた（plan のコミットに入れてある）。Backend の丸めと読み直しの上限は、01〜08 に書く粒度でないので文書は直さない。

この計画のコードは、使い捨てのフォルダ（`git worktree`）で当てて、次を確かめてから書いた。
- Backend の pytest が通る（今の305件から308件）。
- Agent の pytest が通る（今の92件から95件）。
- 新しいテストは、直す前のコードに当てると落ちる。
  - Backend: 360 度・`OverflowError`（読み直しが止まらず、待つ時間が溢れる）で落ちる。
  - Agent: `agent_failed`・`most == 2` で落ちる。

デプロイと smoke は、実行のときに利用者の確認を取ってから行う。

## Global Constraints

- 作業するリポジトリは `Backend/`・`Agent/` と親。
  - Backend と Agent は、`main` から作業ブランチ `slice5-plan7a` を切る（Task 0）。
  - 親の `slice5-plan7a` は、plan のコミットのときに切ってある。
  - push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。
- コミットに `Fixes #N` を書く（spec §15.3）。
  - Backend: #29・#30・#31・#33
  - Agent: #9・#10
- **デプロイは、利用者が明示したときだけ行う。** Task 7 の初めに確認を取る。AWS は `AWS_PROFILE=touring`。Backend は `ap-northeast-1`、Agent は `us-east-1`。
- LLM の入力のトークンを増やさない（PROJECT.md の前提）。出力の上限で止まったときに、モデルをもう一度呼ばない。
- ログに、プロンプトと位置を出さない（Agent の `handler._log` の決まり）。
- 接続キー・ARN・アカウント ID を、コードや文書に書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。
- 以下のパスの略記:
  - `ROOT=<親リポジトリの絶対パス>`
  - `BE=$ROOT/Backend`
  - `AG=$ROOT/Agent`
  - `APP=$AG/app/agentcore_trv2_dev_ask`
- テストのコマンド:
  - Backend: `cd $BE && env/bin/python -m pytest -q`
  - Agent: `cd $APP && uv run pytest -q`
- この Mac の zsh では、変数に入れた複数のパスは分割されないので、コマンドにはパスをそのまま書く。

## Review Focus

- 359.96 度で受けた声の質問が、文字起こしで失敗する（`no_speech`）。記録と `GET /records` の方位は 0（359.96 でも 360 でもない）。Task 1 の `test_the_apps_heading_is_rounded_when_the_ask_is_taken`。
- 古い版の Android が `headingSample` だけを送る。受け付けでは方位なしのまま置き、worker が今までどおり材料から求める（丸めを足しても、材料から求める経路を壊さない）。既存の `tests/test_worker.py` の材料のテストが通り続けること（Task 1 の Step 4）。
- DynamoDB が絞られ続けて、削除の跡を読み残し続ける。地点メモの `PUT` は時間切れで 5xx にならず、決まった回数で先へ進む。跡があれば書き込みのトランザクションで 410 になる。Task 2 の `test_marks_left_unread_every_time_are_given_up_on`。
- モデルがツールの呼び出しの途中で出力の上限に達する。ライダーには英語の決まり文句ではなく「調べきれませんでした。」が読み上げられ、次の質問の履歴にも英語の文が残らない。Task 4 の `test_a_reply_cut_off_in_a_tool_call_is_answered_with_the_fixed_line`。
- 起動直後のプロセスに、2つの会話の最初の質問が同時に届く。どちらも Web 検索つきで答える（片方の MCP の開始が失敗しない）。Task 5 の `test_agents_built_at_once_load_the_web_search_one_at_a_time`。

---

## ファイル構成

| パス | 役割 | Task |
|---|---|---|
| `Backend/src/handlers/ask.py` | 受け付けた時点で方位を丸める | 1 |
| `Backend/src/lib/prompt.py` | プロンプトの度数の 360 を 0 に | 1 |
| `Backend/src/lib/store.py` | `_MARK_READS`・`has_deletion_mark` の打ち切り | 2 |
| `Backend/src/handlers/ask_edit.py` | `_offline` の方位のコメント | 3 |
| `Backend/README.md`・`Backend/docs-parent/` | 削除の跡の並び・文書の写し | 3 |
| `Backend/tests/test_ask.py`・`test_prompt.py`・`test_store.py` | 各 Task のテスト | 1・2 |
| `Agent/app/agentcore_trv2_dev_ask/handler.py` | 出力の上限の受け止め・`_settle_cut_off` | 4 |
| `Agent/app/agentcore_trv2_dev_ask/main.py` | `_BUILD_LOCK` | 5 |
| `Agent/app/agentcore_trv2_dev_ask/tests/test_handler.py`・`test_main.py` | 各 Task のテスト | 4・5 |
| `Agent/README.md`・`Agent/docs-parent/` | 振る舞い・文書の写し | 6 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Backend と Agent に作業ブランチを切る**

```bash
cd $BE && git switch main && git status --short && git switch -c slice5-plan7a && env/bin/python -m pytest -q | tail -1
cd $AG && git switch main && git status --short && git switch -c slice5-plan7a
cd $APP && uv run pytest -q | tail -1
cd $ROOT && git branch --show-current
```

Expected:
- Backend と Agent は、変更なしで `slice5-plan7a` に切り替わる。
- Backend は `305 passed`、Agent は `92 passed`。
- 親は `slice5-plan7a`。

---

### Task 1: 方位の丸め（Backend #29）

**Files:**
- Modify: `Backend/src/handlers/ask.py`・`Backend/src/lib/prompt.py`
- Test: `Backend/tests/test_ask.py`・`Backend/tests/test_prompt.py`

**Interfaces:**
- Consumes: `lib.geo.settled_heading(degrees, location, sample, at) -> Optional[float]`（既存。0.1度に丸め、360 を 0 にする。`degrees` も材料も無ければ None）

- [ ] **Step 1: 落ちるテストを書く**

`tests/test_ask.py` の `test_a_heading_out_of_range_is_not_kept` の前に足す。`store.get_ask` は数を float で返す。

```python
def test_the_apps_heading_is_rounded_when_the_ask_is_taken(aws):
    # An ask that fails before the agent keeps the heading it was taken with, so it is settled here (Backend #29).
    for sent, kept in [(359.96, 0), (12.3456789, 12.3)]:
        body = json.loads(call({"text": "Q", "headingDegrees": sent})["body"])
        assert store.get_ask("rider01", body["askId"])["headingDegrees"] == kept
```

`tests/test_prompt.py` の `test_unknowns_are_stated_not_guessed` の前に足す。

```python
def test_a_heading_just_short_of_north_is_written_as_0_degrees():
    # round() alone would write 360 for 359.5 and above (Backend #29).
    text = prompt.build_prompt("Q", NOW, HERE, None, 359.6, None)
    assert "進行方向: 北（真北から0度）" in text
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/python -m pytest -q tests/test_ask.py tests/test_prompt.py`
Expected: 2 failed。`359.96 == 0` が偽になる。「真北から360度」が出る。

- [ ] **Step 3: 直す**

`src/handlers/ask.py`:
- `from lib.geo import settled_heading` を足す。
- 質問の記録の `"headingDegrees"` を `settled_heading(ask.heading, None, None, now)` にする。材料（`headingSample`）は渡さない。材料から求めるのは今までどおり worker。
- その行の上に `# Settled now: an ask that fails before the agent never gets the worker's settled heading (Backend #29).` を置く。

`src/lib/prompt.py` の `build_prompt`:
- `（真北から{round(heading)}度）` を `（真北から{round(heading) % 360}度）` にする。

- [ ] **Step 4: 全体のテストを回す**

Run: `cd $BE && env/bin/python -m pytest -q | tail -1`
Expected: `307 passed`（`tests/test_worker.py` の材料から方位を求めるテストも通る）

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/handlers/ask.py src/lib/prompt.py tests/test_ask.py tests/test_prompt.py
git commit -m "fix: round the app's heading when the ask is taken, and write almost north as 0 degrees in the prompt (Fixes #29)"
```

---

### Task 2: 削除の跡の読み直しの上限（Backend #30）

**Files:**
- Modify: `Backend/src/lib/store.py`
- Test: `Backend/tests/test_store.py`

**Interfaces:**
- Produces: `store._MARK_READS: int = 5`（テストが読む）

- [ ] **Step 1: 落ちるテストを書く**

`tests/test_store.py` の `test_marks_left_unread_are_read_again` の後に足す。`no_wait` は既存の fixture で、`_sleep` の呼び出しを集める。

```python
def test_marks_left_unread_every_time_are_given_up_on(aws, monkeypatch, no_wait):
    # A bounded wait instead of one until the Lambda times out; the write's transaction still checks (Backend #30).
    client = clients.table().meta.client
    calls = []

    def always_unprocessed(**params):
        calls.append(params)
        return {"Responses": {}, "UnprocessedKeys": params["RequestItems"]}

    monkeypatch.setattr(client, "batch_get_item", always_unprocessed)
    assert store.has_deletion_mark(USER, [("note", "n1"), ("ride", "r1")]) is False
    assert len(calls) == store._MARK_READS and len(no_wait) == store._MARK_READS - 1
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/python -m pytest -q tests/test_store.py -k given_up`
Expected: FAIL。`_MARK_READS` が無いので、`AttributeError` か、読み直しが止まらず待つ時間の計算が `OverflowError` になる。

- [ ] **Step 3: 直す**

`src/lib/store.py`:
- `_CONFLICT_TRIES = 3` の次に、定数とコメントを足す。

  ```python
  # Reads of deletion marks left unprocessed are tried again up to this many reads in all (Backend #30).
  _MARK_READS = 5
  ```

- `has_deletion_mark` の `while request:` のループを、`for attempt in range(_MARK_READS):` にする。
  - ループの初めで、`request` が空なら抜ける。
  - 2回目からは、今と同じく `_sleep(0.05 * 2 ** (attempt - 1))`。
  - 読み終えても残っていたら `False`。
- docstring に、`_MARK_READS` 回読んでも残る跡は「無い」と数えることを足す（書き込みのトランザクションで確かめ直すため）。

- [ ] **Step 4: テストを回す**

Run: `cd $BE && env/bin/python -m pytest -q | tail -1`
Expected: `308 passed`

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/store.py tests/test_store.py
git commit -m "fix: stop reading deletion marks again after five reads, leaving the check to the write's transaction (Fixes #30)"
```

---

### Task 3: 方位のコメントと README（Backend #31・#33）

**Files:**
- Modify: `Backend/src/handlers/ask_edit.py`・`Backend/README.md`・`Backend/docs-parent/`（写し）

- [ ] **Step 1: `_offline` にコメントを足す**

`src/handlers/ask_edit.py` の `_offline` で、`heading = (stored or {}).get("headingDegrees")` の直前に置く。

```python
        # Taken from the first PUT that has a heading, apart from the position (Backend #31): a first PUT with a
        # position but no heading keeps its position, and a later one gives the heading, as the place does.
```

- [ ] **Step 2: README を直す**

`README.md` の「大事な決まり」の、`削除の跡を見て書く書き込み（走行・ルート・地点メモ・会話のメモ）は` を、`削除の跡を見て書く書き込み（走行・ルート・地点メモ・会話のメモ・質問できなかった地点）は` にする。

- [ ] **Step 3: 親の文書を写して、テストを回す**

```bash
cd $ROOT && scripts/sync-docs.sh Backend && cd $BE && git status --short && env/bin/python -m pytest -q | tail -1
```

Expected:
- `synced: Backend`
- 変わるのは `README.md`・`src/handlers/ask_edit.py`・`docs-parent/07_units_contracts.md`・`docs-parent/08c_agent-design.md` だけ
- `308 passed`

- [ ] **Step 4: コミット**

```bash
cd $BE && git add src/handlers/ask_edit.py README.md docs-parent/07_units_contracts.md docs-parent/08c_agent-design.md
git commit -m "docs: say why an unreached ask's heading may come from a later PUT, and list it among the writes that check deletion marks (Fixes #31, Fixes #33)"
```

---

### Task 4: 出力のトークンの上限（Agent #9）

**Files:**
- Modify: `Agent/app/agentcore_trv2_dev_ask/handler.py`
- Test: `Agent/app/agentcore_trv2_dev_ask/tests/test_handler.py`

**Interfaces:**
- Consumes:
  - `strands.types.exceptions.MaxTokensReachedException`
  - `stream.done_event(result, model_id, answer)`（既存。`result.message`・`result.stop_reason`・`result.metrics.accumulated_usage`・`result.metrics.cycle_count` を読む）
- Produces: `handler._settle_cut_off(messages: list[dict]) -> str`。回答を返し、`messages` の最後をその回答に置き換える。

- [ ] **Step 1: 落ちるテストを書く**

`tests/test_handler.py` の先頭の import に、`from strands import Agent` と `from strands.models import Model` を足す（`from config import load_settings` の前の段）。ファイルの最後に足す。

```python
class CutOffModel(Model):
    """A model whose reply stops at its output token cap (Agent #9), after the given content blocks."""

    def __init__(self, blocks):
        self._blocks = blocks

    def update_config(self, **model_config):
        pass

    def get_config(self):
        return {}

    def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        raise NotImplementedError

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        yield {"messageStart": {"role": "assistant"}}
        for block in self._blocks:
            if "text" in block:
                yield {"contentBlockStart": {"start": {}}}
                yield {"contentBlockDelta": {"delta": {"text": block["text"]}}}
            else:
                yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "t1", "name": block["tool"]}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": '{"query": "'}}}}
            yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "max_tokens"}}
        yield {"metadata": {"usage": {"inputTokens": 30, "outputTokens": 800, "totalTokens": 830},
                            "metrics": {"latencyMs": 1}}}


def cut_off_deps(blocks, sessions):
    deps, _ = make_deps(sessions=sessions)
    deps.agent_factory = lambda model_id, messages: Agent(model=CutOffModel(blocks), messages=messages,
                                                          callback_handler=None)
    return deps


def test_an_answer_cut_off_at_the_output_token_cap_is_read_as_far_as_it_goes():
    # Strands raises MaxTokensReachedException instead of returning; the partial answer is still an answer (Agent #9).
    sessions = SessionStore()
    events = run({"prompt": "Q1"}, cut_off_deps([{"text": "右手の山は筑波山で、"}], sessions))
    assert events[-1]["type"] == "done"
    assert events[-1]["answer"] == "右手の山は筑波山で、" and events[-1]["stopReason"] == "max_tokens"
    assert events[-1]["usage"]["outputTokens"] == 800
    assert sessions.get("s1") == [user("Q1"), assistant("右手の山は筑波山で、")]


def test_a_reply_cut_off_in_a_tool_call_is_answered_with_the_fixed_line():
    # Strands puts an English notice where the cut-off tool call was; the rider must not hear it.
    sessions = SessionStore()
    events = run({"prompt": "Q1"}, cut_off_deps([{"tool": "web_search"}], sessions))
    assert events[-1]["type"] == "done" and events[-1]["answer"] == LIMIT_ANSWER
    assert sessions.get("s1") == [user("Q1"), assistant(LIMIT_ANSWER)]
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $APP && uv run pytest -q tests/test_handler.py`
Expected: 2 failed（`'error' == 'done'`。今は `agent_failed` になる）

- [ ] **Step 3: 直す**

`handler.py`:
- import を足す: `re`・`types.SimpleNamespace`・`strands.types.exceptions.MaxTokensReachedException`。
- `LIMIT_ANSWER` のコメントを次にする。

  ```python
  # Said when the model ran into the turn cap, or its output token cap, before answering: the rider hears that it
  # could not be looked up instead of the failure tone (Agent #3, #9, US-A-05.003). No second model call, so no extra
  # input tokens.
  ```

- `_LIMIT_PREFIX` の次に、Strands の決まり文句を足す。

  ```python
  # What Strands puts in place of a tool call cut off at the output token cap (recover_message_on_max_tokens_reached).
  _CUT_OFF_TOOL = re.compile(r"The selected tool .*'s tool use was incomplete due to maximum token limits being reached\.")
  ```

- `_settle_cut_off(messages: list[dict]) -> str` を `_log` の前に足す。
  - 最後の文が `assistant` なら、その `text` のブロックのうち `_CUT_OFF_TOOL.fullmatch` に当たらないものをつなぎ、`strip()` する。
  - 空なら `LIMIT_ANSWER`。
  - 最後の `assistant` の文を `{"role": "assistant", "content": [{"text": answer}]}` に置き換える（最後が `assistant` でなければ足す）。
  - 回答を返す。
- `handle`:
  - `result = None` の次に `cut_off = False`。
  - `except Exception` の前に `except MaxTokensReachedException:` を置き、`cut_off = True` とする（コメント `# Raised, not returned, at the output token cap (Agent #9).`）。
  - 回答を決める `if` の先頭に、次の枝を足す。今の上限の枝は `elif` にする。

  ```python
      if cut_off:
          answer = _settle_cut_off(agent.messages)
          result = SimpleNamespace(message=agent.messages[-1], stop_reason="max_tokens", metrics=agent.event_loop_metrics)
  ```

- [ ] **Step 4: テストを回す**

Run: `cd $APP && uv run pytest -q | tail -1`
Expected: `94 passed`

- [ ] **Step 5: コミット**

```bash
cd $AG && git add app/agentcore_trv2_dev_ask/handler.py app/agentcore_trv2_dev_ask/tests/test_handler.py
git commit -m "fix: answer with the text so far, or that it could not be looked up, when the model hits its output token cap (Fixes #9)"
```

---

### Task 5: エージェントの組み立てを1つずつ（Agent #10）

**Files:**
- Modify: `Agent/app/agentcore_trv2_dev_ask/main.py`
- Test: `Agent/app/agentcore_trv2_dev_ask/tests/test_main.py`

**Interfaces:**
- Produces: `main._BUILD_LOCK: threading.Lock`

- [ ] **Step 1: 落ちるテストを書く**

`tests/test_main.py` の最後に足す。

```python
def test_agents_built_at_once_load_the_web_search_one_at_a_time(monkeypatch):
    # Two first questions at once would both start the MCP client, and the second start fails (Agent #10).
    import threading
    import time

    from strands.hooks import HookProvider
    from strands.tools import ToolProvider

    inside, most, built = [0], [0], []

    class SlowProvider(ToolProvider):
        async def load_tools(self, **kwargs):
            inside[0] += 1
            most[0] = max(most[0], inside[0])
            time.sleep(0.05)
            inside[0] -= 1
            return []

        def add_consumer(self, consumer_id, **kwargs):
            pass

        def remove_consumer(self, consumer_id, **kwargs):
            pass

    class Connection:
        def for_question(self):
            return SlowProvider()

        def failure_watch(self):
            return NoWatch()

    class NoWatch(HookProvider):
        def register_hooks(self, registry, **kwargs):
            pass

    monkeypatch.setattr(main, "WEB_SEARCH", Connection())
    threads = [threading.Thread(target=lambda: built.append(main.build_agent("model-a", []))) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(built) == 2 and most[0] == 1
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $APP && uv run pytest -q tests/test_main.py`
Expected: 1 failed（`most[0]` が 2）

- [ ] **Step 3: 直す**

`main.py`:
- `import threading` を足す。
- `WEB_SEARCH` の警告の次に、ロックとコメントを置く。

  ```python
  # Agents are built in worker threads (Agent #4). Building one may start the MCP client; two at once would both start
  # it, and the second start fails, leaving that question without web search (Agent #10).
  _BUILD_LOCK = threading.Lock()
  ```

- `build_agent` の `return Agent(...)` 全体を `with _BUILD_LOCK:` の中に入れる。

- [ ] **Step 4: テストを回す**

Run: `cd $APP && uv run pytest -q | tail -1`
Expected: `95 passed`

- [ ] **Step 5: コミット**

```bash
cd $AG && git add app/agentcore_trv2_dev_ask/main.py app/agentcore_trv2_dev_ask/tests/test_main.py
git commit -m "fix: build one agent at a time, so two first questions do not both start the web search connection (Fixes #10)"
```

---

### Task 6: 文書（Agent の README・文書の写し・PROJECT.md）

**Files:**
- Modify: `Agent/README.md`・`Agent/docs-parent/`（写し）・親の `PROJECT.md`

親の 07（UC-8 の応答）と 08c（§1 の4）は、この plan のコミットで直してある。

- [ ] **Step 1: README を直す**

`README.md` の「振る舞い」の、`周回の上限（8）に達して回答の文が無いときは、「調べきれませんでした。」を回答として返す。` の直後に、次の文を足す（同じ行に続ける）。

```
モデルの出力のトークンの上限（`BEDROCK_MAX_TOKENS`）で止まったときは、途中までの文を回答とし、文が無ければ（ツールの呼び出しの途中で止まったときを含む）同じ決まった文を返す。エージェントの組み立ては、MCP の接続の開始がぶつからないよう1つずつ行う。
```

- [ ] **Step 2: 親の文書を写して、テストを回す**

```bash
cd $ROOT && scripts/sync-docs.sh Agent && cd $AG && git status --short
cd $APP && uv run pytest -q | tail -1
```

Expected:
- `synced: Agent`
- 変わるのは `README.md`・`docs-parent/07_units_contracts.md`・`docs-parent/08c_agent-design.md` だけ
- `95 passed`

- [ ] **Step 3: Agent にコミット**

```bash
cd $AG && git add README.md docs-parent/07_units_contracts.md docs-parent/08c_agent-design.md
git commit -m "docs: describe the answer at the output token cap and the one-at-a-time agent build in the README"
```

- [ ] **Step 4: 親の PROJECT.md を直して、親にコミット**

`$ROOT/PROJECT.md` を次のように直す。
- 「スライス5」の plan 表の 7a の行の状態を、「実装済み（確認待ち: デプロイと smoke）」にする。
- 「次にやること」の1を、「plan 7a のデプロイと smoke（Task 7）。そのあと plan 7b（Android、0.14.0）を `superpowers:writing-plans` で書いて実行する」にする。

```bash
cd $ROOT && git add PROJECT.md Backend Agent
git commit -m "docs: record slice 5 plan 7a as implemented, awaiting the deploy and smoke"
```

---

### Task 7: デプロイと smoke

- [ ] **Step 1: 利用者に、デプロイしてよいかを確かめる**

次の3つを伝え、明示の了承を得る。了承が無ければここで止まる。
- Backend の Lambda のコードの差し替え
- Agent の Runtime の差し替え
- smoke で Agent に質問を投げる費用がかかること

- [ ] **Step 2: Backend をデプロイする**

Run: `cd $BE && AWS_PROFILE=touring sam build && AWS_PROFILE=touring sam deploy`
Expected:
- `Successfully created/updated stack - stack-trv2-dev-backend`
- 資格情報の誤り（`The security token included in the request is invalid`）なら、利用者に直してもらってから回し直す。

- [ ] **Step 3: Agent をデプロイする**

Agent の README の「デプロイ」のとおり。

```bash
cd $AG && AWS_PROFILE=touring AWS_REGION=us-east-1 npx -y @aws/agentcore@0.31.1 deploy -y
```

Expected: デプロイが成功する。

- [ ] **Step 4: Agent の smoke を回す**

```bash
cd $AG && ARN=$(AWS_PROFILE=touring aws bedrock-agentcore-control list-agent-runtimes --region us-east-1 \
  --query "agentRuntimes[?agentRuntimeName=='trv2Agent_agentcore_trv2_dev_ask'].agentRuntimeArn" --output text)
AWS_PROFILE=touring uv run --project app/agentcore_trv2_dev_ask python scripts/smoke.py "$ARN"
AWS_PROFILE=touring aws ssm get-parameter --region ap-northeast-1 --name /trv2/dev/agent-runtime-arn --query Parameter.Value --output text | cmp -s - <(echo "$ARN") && echo "ARN unchanged"
```

Expected:
- smoke が通る。
- `ARN unchanged`。変わっていたら、README のとおり SSM を書き直し、Backend をデプロイし直す。
- ARN は画面にもチャットにも出さない。

- [ ] **Step 5: Backend の smoke を回す（質問の通しを含む）**

Run: `cd $BE && AWS_PROFILE=touring env/bin/python scripts/smoke.py`
Expected:
- `40/40 passed`
- デプロイの直後に新しい経路だけが 403 なら、1分ほど待って回し直す（Backend の README）。

- [ ] **Step 6: 結果を PROJECT.md に書いて、親にコミット**

`$ROOT/PROJECT.md` を次のように直す。
- plan 表の 7a の行を、「✅ 完了（デプロイ済み・Agent の smoke・Backend の smoke 40/40）」にする。
- 「次にやること」の1を、「plan 7b（Android、0.14.0）を `superpowers:writing-plans` で書いて実行する」にする。

```bash
cd $ROOT && git add PROJECT.md && git commit -m "docs: record slice 5 plan 7a as deployed with the smoke runs passing"
```

最終レビュー・後回しの指摘の書き出し・finishing は、CLAUDE.md の区切り点のとおりに行う。
