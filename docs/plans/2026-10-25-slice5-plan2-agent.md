# スライス5 計画2: Agent（Agent の issue） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent の後回しの指摘（#2〜#5・#7）を直す。デプロイして、Agent の smoke と Backend の smoke（質問の通し）を通す。
- Web 検索の MCP の接続を質問ごとにつなぎ直さない（#2）
- ツールの周回の上限に達したら、失敗の代わりに決まった文で答える（#3）
- SSM と MCP の接続でイベントループを止めない（#4）
- 不正な半径で例外を投げない（#5）
- README を今の作りに合わせる（#7）

**Architecture:** 既存の作りのまま。
- `main.py` は組み立て、`handler.py` は1回の呼び出しの流れ、`tools/` はツール。
- MCP の接続は、新しい係 `tools/web_search.WebSearchConnection` がプロセスの中で持ち続け、質問ごとに `for_question()` で渡す。
- 上限に達したときの回答は `handler.py` で決め、`stream.done_event` に渡す。

**Tech Stack:** Python 3.14（`uv`）・Strands Agents・Bedrock AgentCore Runtime・pytest（どれも既存。足すものは無い）。

**Spec:** [docs/specs/2026-10-25-slice5-design.md](../specs/2026-10-25-slice5-design.md)（§9・§13 の plan 2）。

**範囲に入れた issue:** Agent #2・#3・#4・#5・#7（spec §2・§9）。#6 は閉じた（spec §9）。#8（AI の費用）は後に回す（spec §2）。

**計画を書くときに決めたこと（spec からの具体化）:**
- #2: spec §9 のとおり、まず質問ごとに接続をやり直しているかを確かめた。入っている Strands（`strands-agents` 1.61 系）のコードを読むと、やり直している。
  - 質問が終わってエージェントが捨てられると、`Agent.__del__` → `ToolRegistry.cleanup()` → `MCPClient.remove_consumer()` が呼ばれる。
  - 利用者が0になると `stop()` され、読み込んだツールも捨てられる。
  - 次の質問の `load_tools` で、`start()` と `list_tools` をやり直す。
- #2 の直し方: プロセスの中で利用者（`KEEPER = "trv2-process"`）を1つ持ち続け、接続を使い回す。本物の `MCPClient` で確かめたところ、つなぐのに失敗すると次の2つが起きる。
  - 失敗が残る（`_connection_failed`）。
  - `stop()` が利用者の一覧を空にする（持たせた利用者も消える）。

  そのため `for_question()` は次のように動く。
  - 質問のたびに `KEEPER` を足し直す（同じ印なので1つ）。
  - 前の接続が失敗していたら、いったん `KEEPER` を外してつなぎ直す（失敗を消す）。
  - `AGENT_MCP_MAX_IDLE_SECONDS`（既定600秒）より長く使っていなければ、つなぎ直す。ゲートウェイの側で MCP のセッションが切れているかもしれないため（切れる時間は資料で確かめられていない）。

  `_connection_failed` は Strands の内部の名前なので、`getattr` で読む（無ければ「失敗していない」）。本物の `MCPClient` を使うテストで、この前提を確かめる。
- #3: 上限に達したら決まった文 `LIMIT_ANSWER = "調べきれませんでした。"` を回答として返す。issue の案の「ツールを外してもう一度モデルを呼ぶ」は、入力のトークンが増えるのでとらない（PROJECT.md の前提）。
  - 見分けるのは「回答の文が空」かつ「`stop_reason` が `limit_` で始まる」とき。Strands は上限で例外を投げず、`stop_reason` を `limit_turns` にする。
  - 上限でないのに空のときは、今のまま `agent_failed`。
  - 履歴には、この文を回答として残す（質問と回答が交互のままになるように）。
  - `done` の `stopReason` は上限の名前のまま。Backend は `answer` だけを読むので、Backend は変えない。
- #4: `deps.model_ids.get` と `deps.agent_factory` を `asyncio.to_thread` で呼ぶ。
- #5: `radius_km` を `_number` で確かめ、有限の数でなければ既定の5km（`DEFAULT_RADIUS_KM`）を使う。
- 親の `docs/07_units_contracts.md`（UC-8 の応答）と `docs/08c_agent-design.md`（§1・§2）に、決まった回答と接続の使い回しを書いた（plan のコミットに入れてある）。

この計画のコードは、使い捨てのフォルダ（`git worktree`）でタスクの順にコミットし、次を確かめてから書いた。
- 各コミットで、`__pycache__` を消してから pytest が通る（今の77件から、最後は89件）。
- 各タスクのテストだけを1つ前のコミットに当てると落ちる（`LIMIT_ANSWER` と `WebSearchConnection` を読み込むテストは、読み込みで落ちる）。

デプロイと smoke は、実行のときに利用者の確認を取ってから行う。

## Global Constraints

- 作業するリポジトリは `Agent/`（`TouringProjectV2_Agent`）と親。Agent は `main` から作業ブランチ `slice5-plan2` を切る（Task 0）。親の `slice5-plan2` は plan のコミットのときに切ってある。push・マージはしない（利用者が行う）。push の前に `pre-push-secret-scan`。Agent の PR の本文には `Fixes #2`・`Fixes #3`・`Fixes #4`・`Fixes #5`・`Fixes #7` を書く。
- **デプロイは、利用者が明示したときだけ行う。** Task 6 の途中で確認を取る。AWS は `AWS_PROFILE=touring`。Agent は `us-east-1`、Backend は `ap-northeast-1`。
- LLM の入力のトークンを増やさない（PROJECT.md の前提）。上限に達したときに、モデルをもう一度呼ばない。
- 調整できる値は環境変数か SSM に置く。この plan で足すのは Runtime の環境変数 `AGENT_MCP_MAX_IDLE_SECONDS`（既定600）だけ。
- ログに、プロンプトと位置を出さない（`handler._log` の決まり）。
- 接続キー・ARN・アカウント ID を、コードや文書に書かない（`agentcore/aws-targets.json` は追跡しない）。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。ファイルを消すときは `\rm`。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AG=$ROOT/Agent`、`APP=$AG/app/agentcore_trv2_dev_ask`。テストは `cd $APP && uv run pytest -q`（絞るときは `uv run pytest -q tests/test_xxx.py`）。この Mac の zsh では、変数に入れた複数のパスは分割されないので、コマンドにはパスをそのまま書く。
- 各 Task の差分は、`cd $AG && git apply` で当てられる形で書いた。差分のとおりに当て、手で書き換えない。

## Review Focus

- ゲートウェイに一度つなげなかった（瞬断）→ 次の質問では、Web 検索がまた使える（その会話のあいだずっと使えなくはならない）。Task 4 の `test_a_failed_connection_is_tried_again_on_the_next_question`・`test_a_real_client_that_failed_to_connect_connects_again`。
- 1時間近く質問しなかったあとの質問 → ゲートウェイの側で切れていても、つなぎ直して検索できる。Task 4 の `test_a_connection_left_idle_is_started_again`。
- モデルがツールを呼び続けて周回の上限に達する → 失敗の音でなく「調べきれませんでした」が読み上げられ、次の質問の文脈も壊れない。Task 2 の `test_a_question_cut_off_at_the_turn_cap_is_answered_with_a_fixed_line`。
- 上限でないのに答えが空 → 今までどおり失敗として知らせる（決まった文でごまかさない）。Task 2 の `test_an_empty_answer_that_did_not_hit_a_limit_is_still_a_failure`。
- モデルが半径に NaN・無限大を入れる → 例外でなく、既定の半径で探して答える。Task 1 の `test_a_radius_that_is_not_a_number_uses_the_default`。

---

## ファイル構成（`Agent/` から）

| パス | 役割 | Task |
|---|---|---|
| `app/agentcore_trv2_dev_ask/tools/places.py` | 半径の確かめ・`DEFAULT_RADIUS_KM`（1） | 1 |
| `app/agentcore_trv2_dev_ask/handler.py` | 上限に達したときの回答・`LIMIT_ANSWER`（2）。別のスレッドで読む・組み立てる（3） | 2・3 |
| `app/agentcore_trv2_dev_ask/stream.py` | `done_event` の `answer` の差し替え（2） | 2 |
| `app/agentcore_trv2_dev_ask/tools/web_search.py` | `WebSearchConnection`・`KEEPER`（4） | 4 |
| `app/agentcore_trv2_dev_ask/main.py`・`config.py`・`agentcore/agentcore.json` | 接続の係を使う・`mcp_max_idle_seconds`・環境変数（4） | 4 |
| `README.md`・`docs-parent/` | 文書（5） | 5 |
| `app/agentcore_trv2_dev_ask/tests/` | 各 Task のテスト | 1〜4 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Agent に作業ブランチを切る**

```bash
cd $AG && git switch main && git status --short && git switch -c slice5-plan2
cd $APP && uv run pytest -q | tail -1
cd $ROOT && git branch --show-current
```

Expected: Agent は変更なしで `slice5-plan2` に切り替わる。pytest は `77 passed`。親は `slice5-plan2`。

---

### Task 1: 不正な半径（#5）

**Files:**
- Modify: `app/agentcore_trv2_dev_ask/tools/places.py`
- Test: `app/agentcore_trv2_dev_ask/tests/test_places.py`

**Interfaces:**
- Produces: `tools.places.DEFAULT_RADIUS_KM = 5.0`。

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $AG && git apply <<'PATCH'
diff --git a/app/agentcore_trv2_dev_ask/tests/test_places.py b/app/agentcore_trv2_dev_ask/tests/test_places.py
index 98dc6e0..5f6f212 100644
--- a/app/agentcore_trv2_dev_ask/tests/test_places.py
+++ b/app/agentcore_trv2_dev_ask/tests/test_places.py
@@ -136,6 +136,14 @@ def test_radius_is_clamped(client):
     assert client.calls[0][1]["QueryRadius"] == int(places.MAX_RADIUS_KM * 1000)
 
 
+@pytest.mark.parametrize("radius", [math.nan, math.inf, -math.inf])
+def test_a_radius_that_is_not_a_number_uses_the_default(client, radius):
+    # Failures are answered as text, never raised (Agent #5).
+    answer = places.nearby_places(kind="公園", radius_km=radius, tool_context=_context(TOKYO_STATION))
+    assert isinstance(answer, str)
+    assert client.calls[0][1]["QueryRadius"] == int(places.DEFAULT_RADIUS_KM * 1000)
+
+
 def test_find_place_is_biased_to_rider_and_sorted_by_distance(client):
     client.items = [_place("遠い", 35.70, 139.77, distance=2000), _place("近い", 35.682, 139.767, distance=100)]
     answer = places.find_place(name="マクドナルド", tool_context=_context(TOKYO_STATION))
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $APP && uv run pytest -q tests/test_places.py`
Expected: 3件が FAIL（`test_a_radius_that_is_not_a_number_uses_the_default[nan]`・`[inf]`・`[-inf]`。`DEFAULT_RADIUS_KM` が無い）。

- [ ] **Step 3: 実装する**

```bash
cd $AG && git apply <<'PATCH'
diff --git a/app/agentcore_trv2_dev_ask/tools/places.py b/app/agentcore_trv2_dev_ask/tools/places.py
index 52b4891..5d6c824 100644
--- a/app/agentcore_trv2_dev_ask/tools/places.py
+++ b/app/agentcore_trv2_dev_ask/tools/places.py
@@ -60,6 +60,7 @@ MAX_RETURNED = 5
 MAX_FETCHED = 20
 MIN_RADIUS_KM = 0.2
 MAX_RADIUS_KM = 50.0
+DEFAULT_RADIUS_KM = 5.0
 
 _NO_LOCATION = "現在地が分からないため、周辺を探せません。"
 _FAILED = "周辺の検索に失敗しました。"
@@ -162,7 +163,8 @@ def _answer(lines: list[str], location: dict, side: Optional[str]) -> str:
 
 
 @tool(context=True)
-def nearby_places(kind: Kind, tool_context: ToolContext, side: Optional[Side] = None, radius_km: float = 5.0) -> str:
+def nearby_places(kind: Kind, tool_context: ToolContext, side: Optional[Side] = None,
+                  radius_km: float = DEFAULT_RADIUS_KM) -> str:
     """現在地の周辺にある場所を種類で探し、近い順に距離・方角・左右を返す。
 
     「右手に見える山は？」「近くのコンビニは？」のように種類で探すときに使う。
@@ -179,7 +181,9 @@ def nearby_places(kind: Kind, tool_context: ToolContext, side: Optional[Side] =
     categories = KINDS.get(kind)
     if not categories:
         return f"「{kind}」という種類では探せません。"
-    radius_m = int(min(max(radius_km, MIN_RADIUS_KM), MAX_RADIUS_KM) * 1000)
+    # A radius that is not a finite number falls back to the default instead of raising (Agent #5).
+    radius = _number(radius_km)
+    radius_m = int(min(max(radius if radius is not None else DEFAULT_RADIUS_KM, MIN_RADIUS_KM), MAX_RADIUS_KM) * 1000)
     try:
         result = _get_client().search_nearby(
             QueryPosition=[location["longitude"], location["latitude"]],
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && find . -name __pycache__ -prune -exec \rm -rf {} + && uv run pytest -q | tail -1`
Expected: `80 passed`

- [ ] **Step 5: コミット**

```bash
cd $APP && git add tools/places.py tests/test_places.py
git commit -m "fix: fall back to the default radius when the model sends one that is not a finite number (#5)"
```

---

### Task 2: 上限に達したときの回答（#3）

**Files:**
- Modify: `app/agentcore_trv2_dev_ask/handler.py`・`app/agentcore_trv2_dev_ask/stream.py`
- Test: `app/agentcore_trv2_dev_ask/tests/test_handler.py`

**Interfaces:**
- Produces: `handler.LIMIT_ANSWER = "調べきれませんでした。"`。`stream.done_event(result, model_id, answer: str | None = None) -> dict`（`answer` があれば、モデルの回答の代わりに使う）。

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $AG && git apply <<'PATCH'
diff --git a/app/agentcore_trv2_dev_ask/tests/test_handler.py b/app/agentcore_trv2_dev_ask/tests/test_handler.py
index df59696..433e2c5 100644
--- a/app/agentcore_trv2_dev_ask/tests/test_handler.py
+++ b/app/agentcore_trv2_dev_ask/tests/test_handler.py
@@ -3,7 +3,7 @@ import asyncio
 from types import SimpleNamespace
 
 from config import load_settings
-from handler import Deps, handle
+from handler import LIMIT_ANSWER, Deps, handle
 from history import SessionStore
 from model_config import ModelIdError
 
@@ -139,6 +139,39 @@ def test_empty_answer_is_agent_failed():
     assert run({"prompt": "Q"}, deps)[-1] == {"type": "error", "code": "agent_failed", "message": "empty answer"}
 
 
+class LimitedAgent(FakeAgent):
+    """The model kept calling tools until the turn cap; the last message is a tool result, not an answer."""
+
+    def __init__(self, messages, stop_reason="limit_turns"):
+        super().__init__(messages, [], "")
+        self._stop_reason = stop_reason
+
+    async def stream_async(self, prompt, invocation_state=None, limits=None):
+        self.calls.append({"prompt": prompt, "invocation_state": invocation_state, "limits": limits})
+        self.messages.append(user(prompt))
+        self.messages.append({"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": "web_search", "input": {}}}]})
+        tool_result = {"role": "user", "content": [{"toolResult": {"toolUseId": "t1", "content": [{"text": "上限"}]}}]}
+        self.messages.append(tool_result)
+        yield {"current_tool_use": {"toolUseId": "t1", "name": "web_search"}}
+        yield {"result": SimpleNamespace(message=tool_result, stop_reason=self._stop_reason,
+                                         metrics=SimpleNamespace(accumulated_usage={"inputTokens": 10}, cycle_count=8))}
+
+
+def test_a_question_cut_off_at_the_turn_cap_is_answered_with_a_fixed_line():
+    # The rider hears that it could not be looked up, not the failure tone (Agent #3).
+    sessions = SessionStore()
+    deps, _ = make_deps(agent=LimitedAgent([]), sessions=sessions)
+    events = run({"prompt": "Q1"}, deps)
+    assert events[-1]["type"] == "done"
+    assert events[-1]["answer"] == LIMIT_ANSWER and events[-1]["stopReason"] == "limit_turns"
+    assert sessions.get("s1") == [user("Q1"), assistant(LIMIT_ANSWER)]
+
+
+def test_an_empty_answer_that_did_not_hit_a_limit_is_still_a_failure():
+    deps, _ = make_deps(agent=LimitedAgent([], stop_reason="end_turn"))
+    assert run({"prompt": "Q"}, deps)[-1] == {"type": "error", "code": "agent_failed", "message": "empty answer"}
+
+
 def test_agent_creation_error_is_agent_failed():
     def failing_factory(model_id, messages):
         raise RuntimeError("gateway unreachable")
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $APP && uv run pytest -q tests/test_handler.py`
Expected: 読み込みで ERROR（`LIMIT_ANSWER` が `handler` に無い）。

- [ ] **Step 3: 実装する**

```bash
cd $AG && git apply <<'PATCH'
diff --git a/app/agentcore_trv2_dev_ask/handler.py b/app/agentcore_trv2_dev_ask/handler.py
index 11ca51c..3eaad36 100644
--- a/app/agentcore_trv2_dev_ask/handler.py
+++ b/app/agentcore_trv2_dev_ask/handler.py
@@ -15,6 +15,11 @@ from tools.places import LOCATION_KEY
 
 log = logging.getLogger("trv2.agent")
 
+# Said when the model ran into a limit (turns, tokens) before answering: the rider hears that it could not be
+# looked up instead of the failure tone (Agent #3, US-A-05.003). No second model call, so no extra input tokens.
+LIMIT_ANSWER = "調べきれませんでした。"
+_LIMIT_PREFIX = "limit_"
+
 
 @dataclass
 class Deps:
@@ -69,13 +74,18 @@ async def handle(payload: dict, session_id: str, deps: Deps) -> AsyncIterator[di
         yield error_event("agent_failed", type(error).__name__)
         return
 
-    if result is None or not final_answer(result.message):
+    answer = None
+    if result is not None and not final_answer(result.message) and str(result.stop_reason).startswith(_LIMIT_PREFIX):
+        answer = LIMIT_ANSWER
+        # Kept as the turn's answer, so the history still alternates question and answer.
+        agent.messages.append({"role": "assistant", "content": [{"text": LIMIT_ANSWER}]})
+    elif result is None or not final_answer(result.message):
         _log({"event": "invoke_failed", "session": session_id, "modelId": model_id, "reason": "empty answer"})
         yield error_event("agent_failed", "empty answer")
         return
 
     deps.sessions.put(session_id, prune_history(agent.messages, deps.settings.max_history_messages))
-    done = done_event(result, model_id)
+    done = done_event(result, model_id, answer)
     _log({"event": "invoke_done", "session": session_id, "modelId": model_id, "tools": tools,
           "usage": done["usage"], "stopReason": done["stopReason"]})
     yield done
diff --git a/app/agentcore_trv2_dev_ask/stream.py b/app/agentcore_trv2_dev_ask/stream.py
index 7e4a146..7ac4a3b 100644
--- a/app/agentcore_trv2_dev_ask/stream.py
+++ b/app/agentcore_trv2_dev_ask/stream.py
@@ -13,11 +13,12 @@ def error_event(code: str, message: str) -> dict:
     return {"type": "error", "code": code, "message": message}
 
 
-def done_event(result: Any, model_id: str) -> dict:
+def done_event(result: Any, model_id: str, answer: str | None = None) -> dict:
+    """The last event; answer replaces the model's own when the handler had to supply one."""
     usage = result.metrics.accumulated_usage
     return {
         "type": "done",
-        "answer": final_answer(result.message),
+        "answer": answer if answer is not None else final_answer(result.message),
         "stopReason": str(result.stop_reason),
         "usage": {
             "inputTokens": usage.get("inputTokens", 0),
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && find . -name __pycache__ -prune -exec \rm -rf {} + && uv run pytest -q | tail -1`
Expected: `82 passed`

- [ ] **Step 5: コミット**

```bash
cd $APP && git add handler.py stream.py tests/test_handler.py
git commit -m "fix: answer that it could not be looked up when the model hits a limit before answering (#3)"
```

---

### Task 3: イベントループを止めない（#4）

**Files:**
- Modify: `app/agentcore_trv2_dev_ask/handler.py`
- Test: `app/agentcore_trv2_dev_ask/tests/test_handler.py`

**Interfaces:**
- Consumes: Task 2 の `handler.py`（同じ関数 `handle` を直す）。

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $AG && git apply <<'PATCH'
diff --git a/app/agentcore_trv2_dev_ask/tests/test_handler.py b/app/agentcore_trv2_dev_ask/tests/test_handler.py
index 433e2c5..ea1fe8c 100644
--- a/app/agentcore_trv2_dev_ask/tests/test_handler.py
+++ b/app/agentcore_trv2_dev_ask/tests/test_handler.py
@@ -1,5 +1,6 @@
 """Tests for one invocation: payload checks, model id, streaming, history and errors."""
 import asyncio
+import threading
 from types import SimpleNamespace
 
 from config import load_settings
@@ -172,6 +173,28 @@ def test_an_empty_answer_that_did_not_hit_a_limit_is_still_a_failure():
     assert run({"prompt": "Q"}, deps)[-1] == {"type": "error", "code": "agent_failed", "message": "empty answer"}
 
 
+def test_reading_the_model_id_and_building_the_agent_do_not_block_the_event_loop():
+    # SSM and the MCP connection are blocking calls; they run in a worker thread so /ping keeps answering (Agent #4).
+    threads = {}
+
+    class RecordingModelIds:
+        def get(self):
+            threads["model_id"] = threading.get_ident()
+            return "model-a"
+
+    agent = FakeAgent([], [], "A")
+    deps, _ = make_deps(model_ids=RecordingModelIds())
+
+    def factory(model_id, messages):
+        threads["factory"] = threading.get_ident()
+        return agent
+
+    deps.agent_factory = factory
+    assert run({"prompt": "Q"}, deps)[-1]["type"] == "done"
+    loop_thread = threading.get_ident()
+    assert threads["model_id"] != loop_thread and threads["factory"] != loop_thread
+
+
 def test_agent_creation_error_is_agent_failed():
     def failing_factory(model_id, messages):
         raise RuntimeError("gateway unreachable")
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $APP && uv run pytest -q tests/test_handler.py`
Expected: 1件が FAIL（`test_reading_the_model_id_and_building_the_agent_do_not_block_the_event_loop`。イベントループのスレッドで呼ばれている）。

- [ ] **Step 3: 実装する**

```bash
cd $AG && git apply <<'PATCH'
diff --git a/app/agentcore_trv2_dev_ask/handler.py b/app/agentcore_trv2_dev_ask/handler.py
index 3eaad36..34a0028 100644
--- a/app/agentcore_trv2_dev_ask/handler.py
+++ b/app/agentcore_trv2_dev_ask/handler.py
@@ -1,6 +1,7 @@
 """One invocation: read the model id, run the agent, stream events, and keep history on success."""
 from __future__ import annotations
 
+import asyncio
 import json
 import logging
 from collections.abc import AsyncIterator, Callable
@@ -45,7 +46,8 @@ async def handle(payload: dict, session_id: str, deps: Deps) -> AsyncIterator[di
         yield error_event("bad_request", "prompt is required")
         return
     try:
-        model_id = deps.model_ids.get()
+        # Blocking (SSM); a worker thread keeps the event loop, and /ping, answering (Agent #4).
+        model_id = await asyncio.to_thread(deps.model_ids.get)
     except ModelIdError as error:
         _log({"event": "invoke_failed", "session": session_id, "reason": str(error)})
         yield error_event("agent_failed", str(error))
@@ -55,8 +57,8 @@ async def handle(payload: dict, session_id: str, deps: Deps) -> AsyncIterator[di
     tools: list[str] = []
     result = None
     try:
-        # Inside the try: building the agent loads MCP tools and can fail on its own.
-        agent = deps.agent_factory(model_id, deps.sessions.get(session_id))
+        # Inside the try: building the agent loads MCP tools and can fail on its own. Blocking too, so off the loop.
+        agent = await asyncio.to_thread(deps.agent_factory, model_id, deps.sessions.get(session_id))
         async for event in agent.stream_async(
             prompt,
             invocation_state={LOCATION_KEY: payload.get("location")},
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && find . -name __pycache__ -prune -exec \rm -rf {} + && uv run pytest -q | tail -1`
Expected: `83 passed`

- [ ] **Step 5: コミット**

```bash
cd $APP && git add handler.py tests/test_handler.py
git commit -m "fix: read the model id and build the agent in a worker thread, off the event loop (#4)"
```

---

### Task 4: MCP の接続を使い回す（#2）

**Files:**
- Modify: `app/agentcore_trv2_dev_ask/tools/web_search.py`・`app/agentcore_trv2_dev_ask/main.py`・`app/agentcore_trv2_dev_ask/config.py`・`agentcore/agentcore.json`
- Test: `app/agentcore_trv2_dev_ask/tests/test_web_search.py`・`tests/test_main.py`・`tests/test_config.py`

**Interfaces:**
- Produces: `tools.web_search.KEEPER = "trv2-process"`。`tools.web_search.WebSearchConnection(client, max_idle_seconds: float, clock: Callable[[], float] = time.monotonic)`、`.for_question() -> MCPClient`。`config.Settings.mcp_max_idle_seconds: float = 600.0`（環境変数 `AGENT_MCP_MAX_IDLE_SECONDS`）。`main.WEB_SEARCH` は `WebSearchConnection` か None。

- [ ] **Step 1: 落ちるテストを書く**

```bash
cd $AG && git apply <<'PATCH'
diff --git a/app/agentcore_trv2_dev_ask/tests/test_config.py b/app/agentcore_trv2_dev_ask/tests/test_config.py
index 1ae8a24..13edac2 100644
--- a/app/agentcore_trv2_dev_ask/tests/test_config.py
+++ b/app/agentcore_trv2_dev_ask/tests/test_config.py
@@ -12,6 +12,11 @@ def test_defaults():
     assert settings.max_history_messages == 10
     assert settings.max_tool_result_chars == 3000
     assert settings.model_cache_seconds == 60.0
+    assert settings.mcp_max_idle_seconds == 600.0
+
+
+def test_the_mcp_idle_time_can_be_set():
+    assert load_settings({"AGENT_MCP_MAX_IDLE_SECONDS": "120"}).mcp_max_idle_seconds == 120.0
 
 
 def test_environment_overrides():
diff --git a/app/agentcore_trv2_dev_ask/tests/test_main.py b/app/agentcore_trv2_dev_ask/tests/test_main.py
index 952e0b6..4d30f9f 100644
--- a/app/agentcore_trv2_dev_ask/tests/test_main.py
+++ b/app/agentcore_trv2_dev_ask/tests/test_main.py
@@ -9,3 +9,23 @@ def test_build_agent_wires_model_tools_hooks_and_history():
     assert agent.messages == history
     assert {"nearby_places", "find_place"} <= set(agent.tool_names)
     assert "ライダー" in agent.system_prompt
+
+
+def test_each_agent_takes_the_web_search_from_the_held_connection(monkeypatch):
+    # The connection, not a bare client, hands the MCP client to each question's agent (Agent #2).
+    from strands.tools.mcp import MCPClient
+
+    def unreachable():
+        raise ConnectionError("no gateway")
+
+    taken = []
+
+    class Connection:
+        def for_question(self):
+            taken.append(True)
+            return MCPClient(unreachable, continue_on_error=True)
+
+    monkeypatch.setattr(main, "WEB_SEARCH", Connection())
+    main.build_agent("model-a", [])
+    main.build_agent("model-a", [])
+    assert taken == [True, True]
diff --git a/app/agentcore_trv2_dev_ask/tests/test_web_search.py b/app/agentcore_trv2_dev_ask/tests/test_web_search.py
index 55e155f..8180e90 100644
--- a/app/agentcore_trv2_dev_ask/tests/test_web_search.py
+++ b/app/agentcore_trv2_dev_ask/tests/test_web_search.py
@@ -1,5 +1,78 @@
-"""Tests for finding the gateway url injected by the AgentCore CLI."""
-from tools.web_search import find_gateway_url
+"""Tests for finding the gateway url injected by the AgentCore CLI, and for keeping its connection."""
+import asyncio
+
+from strands.tools.mcp import MCPClient
+
+from tools.web_search import KEEPER, WebSearchConnection, find_gateway_url
+
+
+class FakeClient:
+    def __init__(self):
+        self.consumers = set()
+        self.removed = []
+        self._connection_failed = False
+
+    def add_consumer(self, consumer_id, **kwargs):
+        self.consumers.add(consumer_id)
+
+    def remove_consumer(self, consumer_id, **kwargs):
+        self.removed.append(consumer_id)
+        self.consumers.discard(consumer_id)
+        if not self.consumers:
+            self._connection_failed = False
+
+
+class Clock:
+    def __init__(self):
+        self.now = 1000.0
+
+    def __call__(self):
+        return self.now
+
+
+def test_the_connection_is_held_across_questions():
+    # Each question's agent is a consumer of the client; with one held for the process, the client is not
+    # stopped and started again for every question (Agent #2).
+    client = FakeClient()
+    connection = WebSearchConnection(client, max_idle_seconds=600, clock=Clock())
+    assert connection.for_question() is client and KEEPER in client.consumers
+    connection.for_question()
+    assert client.removed == []
+
+
+def test_a_failed_connection_is_tried_again_on_the_next_question():
+    client, clock = FakeClient(), Clock()
+    connection = WebSearchConnection(client, max_idle_seconds=600, clock=clock)
+    connection.for_question()
+    client._connection_failed = True
+    connection.for_question()
+    assert client.removed == [KEEPER] and KEEPER in client.consumers and client._connection_failed is False
+
+
+def test_a_connection_left_idle_is_started_again():
+    # The gateway's session may have gone while nobody asked.
+    client, clock = FakeClient(), Clock()
+    connection = WebSearchConnection(client, max_idle_seconds=600, clock=clock)
+    connection.for_question()
+    clock.now += 600
+    connection.for_question()
+    assert client.removed == []
+    clock.now += 601
+    connection.for_question()
+    assert client.removed == [KEEPER] and KEEPER in client.consumers
+
+
+def test_a_real_client_that_failed_to_connect_connects_again():
+    # Strands keeps a swallowed start failure, and its stop() empties the consumers; both are undone here.
+    def unreachable():
+        raise ConnectionError("no gateway")
+
+    client = MCPClient(unreachable, continue_on_error=True)
+    connection = WebSearchConnection(client, max_idle_seconds=600)
+    connection.for_question()
+    assert asyncio.run(client.load_tools()) == [] and client._connection_failed is True
+    connection.for_question()
+    assert client._connection_failed is False and KEEPER in client._consumers
 
 
 def test_override_wins():
PATCH
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $APP && uv run pytest -q tests/test_web_search.py; uv run pytest -q tests/test_config.py tests/test_main.py`
Expected: 1つ目は読み込みで ERROR（`WebSearchConnection` が無い）。2つ目は3件が FAIL（`test_defaults`・`test_the_mcp_idle_time_can_be_set`・`test_each_agent_takes_the_web_search_from_the_held_connection`）。

- [ ] **Step 3: 実装する**

```bash
cd $AG && git apply <<'PATCH'
diff --git a/agentcore/agentcore.json b/agentcore/agentcore.json
index 85df916..68c1596 100644
--- a/agentcore/agentcore.json
+++ b/agentcore/agentcore.json
@@ -40,6 +40,10 @@
         {
           "name": "AGENT_MAX_TOOL_RESULT_CHARS",
           "value": "3000"
+        },
+        {
+          "name": "AGENT_MCP_MAX_IDLE_SECONDS",
+          "value": "600"
         }
       ],
       "lifecycleConfiguration": {
diff --git a/app/agentcore_trv2_dev_ask/config.py b/app/agentcore_trv2_dev_ask/config.py
index 78a83ea..32959e4 100644
--- a/app/agentcore_trv2_dev_ask/config.py
+++ b/app/agentcore_trv2_dev_ask/config.py
@@ -16,6 +16,8 @@ class Settings:
     max_history_messages: int
     max_tool_result_chars: int
     model_cache_seconds: float
+    # How long the web search's MCP connection may sit unused before it is started again (Agent #2).
+    mcp_max_idle_seconds: float = 600.0
 
 
 def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
@@ -29,4 +31,5 @@ def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
         max_history_messages=int(env.get("AGENT_MAX_HISTORY_MESSAGES", "10")),
         max_tool_result_chars=int(env.get("AGENT_MAX_TOOL_RESULT_CHARS", "3000")),
         model_cache_seconds=float(env.get("MODEL_ID_CACHE_SECONDS", "60")),
+        mcp_max_idle_seconds=float(env.get("AGENT_MCP_MAX_IDLE_SECONDS", "600")),
     )
diff --git a/app/agentcore_trv2_dev_ask/main.py b/app/agentcore_trv2_dev_ask/main.py
index 4f7e7e9..f5c640d 100644
--- a/app/agentcore_trv2_dev_ask/main.py
+++ b/app/agentcore_trv2_dev_ask/main.py
@@ -16,13 +16,15 @@ from hooks import ToolCallLimit, ToolResultTrimmer
 from model_config import ModelIdSource
 from prompt import SYSTEM_PROMPT
 from tools.places import find_place, nearby_places
-from tools.web_search import load_web_search
+from tools.web_search import WebSearchConnection, load_web_search
 
 logging.getLogger("trv2.agent").setLevel(logging.INFO)
 
 app = BedrockAgentCoreApp()
 SETTINGS = load_settings()
-WEB_SEARCH = load_web_search()
+_WEB_SEARCH_CLIENT = load_web_search()
+# Held for the process, so the gateway connection is not made again for every question (Agent #2).
+WEB_SEARCH = WebSearchConnection(_WEB_SEARCH_CLIENT, SETTINGS.mcp_max_idle_seconds) if _WEB_SEARCH_CLIENT else None
 if WEB_SEARCH is None:
     app.logger.warning("no gateway url in env - answering without web search")
 
@@ -33,7 +35,7 @@ def build_agent(model_id: str, messages: list[dict]) -> Agent:
         model=BedrockModel(model_id=model_id, region_name=SETTINGS.region, max_tokens=SETTINGS.max_tokens),
         messages=messages,
         system_prompt=SYSTEM_PROMPT,
-        tools=[nearby_places, find_place] + ([WEB_SEARCH] if WEB_SEARCH else []),
+        tools=[nearby_places, find_place] + ([WEB_SEARCH.for_question()] if WEB_SEARCH else []),
         hooks=[ToolCallLimit(SETTINGS.max_tool_calls), ToolResultTrimmer(SETTINGS.max_tool_result_chars)],
         # History is pruned by handler.py after each successful turn.
         conversation_manager=NullConversationManager(),
diff --git a/app/agentcore_trv2_dev_ask/tools/web_search.py b/app/agentcore_trv2_dev_ask/tools/web_search.py
index 27a9c38..14ed1e6 100644
--- a/app/agentcore_trv2_dev_ask/tools/web_search.py
+++ b/app/agentcore_trv2_dev_ask/tools/web_search.py
@@ -1,9 +1,11 @@
 """Web search through the AgentCore Gateway's managed web-search connector (MCP, IAM-signed)."""
 from __future__ import annotations
 
+import logging
 import os
-from collections.abc import Mapping
-from typing import Optional
+import time
+from collections.abc import Callable, Mapping
+from typing import Any, Optional
 
 from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
 from strands.tools.mcp import MCPClient
@@ -11,6 +13,10 @@ from strands.tools.mcp import MCPClient
 _AWS_SERVICE = "bedrock-agentcore"
 _PREFIX = "AGENTCORE_GATEWAY_"
 _SUFFIX = "_URL"
+# The consumer this process holds on the MCP client, so the client outlives each question's agent.
+KEEPER = "trv2-process"
+
+log = logging.getLogger("trv2.agent")
 
 
 def find_gateway_url(env: Mapping[str, str] = os.environ) -> Optional[str]:
@@ -35,3 +41,33 @@ def load_web_search() -> Optional[MCPClient]:
         lambda: aws_iam_streamablehttp_client(endpoint=endpoint, aws_region=region, aws_service=_AWS_SERVICE),
         continue_on_error=True,
     )
+
+
+class WebSearchConnection:
+    """Keeps the gateway's MCP connection across questions (Agent #2).
+
+    Each question builds a fresh agent, which becomes a consumer of the MCP client. When the agent is collected,
+    Strands removes it, and a client with no consumer left stops and starts again, listing its tools, on the next
+    question. Holding one consumer for the process keeps the connection. It is started again before a question
+    when the last start failed (Strands keeps a swallowed failure, and its stop() drops every consumer) or when it
+    has not been used for max_idle_seconds, as the gateway's session may have gone meanwhile."""
+
+    def __init__(self, client: Any, max_idle_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
+        self._client = client
+        self._max_idle_seconds = max_idle_seconds
+        self._clock = clock
+        self._last_used: Optional[float] = None
+
+    def for_question(self) -> Any:
+        now = self._clock()
+        failed = bool(getattr(self._client, "_connection_failed", False))
+        idle = self._last_used is not None and now - self._last_used > self._max_idle_seconds
+        if failed or idle:
+            try:
+                # With no other consumer, this stops the client and clears the kept failure.
+                self._client.remove_consumer(KEEPER)
+            except Exception as error:  # noqa: BLE001 - the question still goes ahead with the old client
+                log.warning("mcp reset failed: %s", type(error).__name__)
+        self._client.add_consumer(KEEPER)
+        self._last_used = now
+        return self._client
PATCH
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && find . -name __pycache__ -prune -exec \rm -rf {} + && uv run pytest -q | tail -1`
Expected: `89 passed`（Strands の `MCPClient` の後片付けの RuntimeWarning が出るが、テストは通る）

- [ ] **Step 5: コミット**

```bash
cd $APP && git add tools/web_search.py main.py config.py ../../agentcore/agentcore.json tests/test_web_search.py tests/test_main.py tests/test_config.py
git commit -m "fix: keep the web search's MCP connection across questions, connecting again after a failure or a long idle (#2)"
```

---

### Task 5: 文書（Agent の README・文書の写し・PROJECT.md）

**Files:**
- Modify: `README.md`・`docs-parent/`（写し）・親の `PROJECT.md`

親の 07（UC-8 の応答）と 08c（§1・§2）は、この plan のコミットで直してある。

- [ ] **Step 1: README を直す**

```bash
cd $AG && git apply <<'PATCH'
diff --git a/README.md b/README.md
index a4f9346..4e2374e 100644
--- a/README.md
+++ b/README.md
@@ -15,9 +15,11 @@ Backend から質問（プロンプトと数値の現在地）を受け、Web 
 
 ## 振る舞い
 
-- 会話の文脈は `runtimeSessionId`（Backend が渡す会話の識別子）ごとに、Runtime のプロセスの中に持つ。回答のあと、ツールの呼び出しと結果を取り除き、質問と回答の文だけを直近10メッセージまで残す。
+- 会話の文脈は `runtimeSessionId`（Backend が渡すセッションの識別子。ユーザー名と会話の識別子から作る値。親の `docs/07_units_contracts.md` UC-8）ごとに、Runtime のプロセスの中に持つ。回答のあと、ツールの呼び出しと結果を取り除き、質問と回答の文だけを直近10メッセージまで残す。
 - モデル ID は SSM `/trv2/dev/agent-model-id`（us-east-1）から読む（60秒キャッシュ）。読めないときは失敗を返す。
-- ツールは1回の質問につき4回まで。ツールの結果は合計3000文字までに切り詰める。
+- モデル ID の読み込みとエージェントの組み立て（MCP の接続）は、イベントループを止めないよう別のスレッドで行う。
+- ツールは1回の質問につき4回まで。ツールの結果は合計3000文字までに切り詰める。周回の上限（8）に達して回答の文が無いときは、「調べきれませんでした。」を回答として返す。
+- Web 検索の MCP の接続は、質問ごとに作り直すエージェントをまたいで使い回す。つなげなかったときと、`AGENT_MCP_MAX_IDLE_SECONDS`（既定600秒）より長く使わなかったときは、次の質問の前につなぎ直す。
 - 応答は SSE で `text`・`tool`・`done`・`error` のイベントを返す（親の `docs/07_units_contracts.md` UC-8）。
 
 ## テスト
PATCH
```

- [ ] **Step 2: 親の文書を写す**

```bash
cd $ROOT && scripts/sync-docs.sh Agent && cd $AG && git status --short
```

Expected: `synced: Agent`。`README.md`・`docs-parent/07_units_contracts.md`・`docs-parent/08c_agent-design.md` だけが変わる。

- [ ] **Step 3: テストを回して、Agent にコミット**

```bash
cd $APP && uv run pytest -q | tail -1
cd $AG && git add README.md docs-parent/07_units_contracts.md docs-parent/08c_agent-design.md
git commit -m "docs: describe the held MCP connection, the limit answer and the session id in the README (#7)"
```

Expected: `89 passed`

- [ ] **Step 4: 親の PROJECT.md を直して、親にコミット**

`$ROOT/PROJECT.md` の「スライス5」の plan 表の2の行の状態を「実装済み（確認待ち: デプロイと smoke）」にする。「次にやること」は「plan 2 のデプロイと smoke（Task 6）」にする。

```bash
cd $ROOT && git add PROJECT.md Agent
git commit -m "docs: record slice 5 plan 2 as implemented, awaiting the deploy and smoke"
```

---

### Task 6: デプロイと smoke

- [ ] **Step 1: 利用者に、デプロイしてよいかを確かめる**

デプロイの中身（Agent の Runtime の差し替えと、環境変数 `AGENT_MCP_MAX_IDLE_SECONDS` の追加）と、smoke で Agent に質問を投げる費用がかかることを伝え、明示の了承を得る。了承が無ければここで止まる。

- [ ] **Step 2: Agent をデプロイする**

Agent の README の「デプロイ」のとおり。

```bash
cd $AG && AWS_PROFILE=touring AWS_REGION=us-east-1 npx -y @aws/agentcore@0.31.1 deploy -y
```

Expected: デプロイが成功する。資格情報の誤りなら、利用者に直してもらってから回し直す。

- [ ] **Step 3: Agent の smoke を回す**

```bash
cd $AG && ARN=$(AWS_PROFILE=touring aws bedrock-agentcore-control list-agent-runtimes --region us-east-1 \
  --query "agentRuntimes[?agentRuntimeName=='trv2Agent_agentcore_trv2_dev_ask'].agentRuntimeArn" --output text)
AWS_PROFILE=touring uv run --project app/agentcore_trv2_dev_ask python scripts/smoke.py "$ARN"
AWS_PROFILE=touring aws ssm get-parameter --region ap-northeast-1 --name /trv2/dev/agent-runtime-arn --query Parameter.Value --output text | cmp -s - <(echo "$ARN") && echo "ARN unchanged"
```

Expected: smoke が通る。`ARN unchanged`（変わっていたら、README のとおり SSM を書き直し、Backend をデプロイし直す）。ARN は画面にもチャットにも出さない。

- [ ] **Step 4: Backend の smoke で質問の通しを確かめる**

Run: `cd $ROOT/Backend && AWS_PROFILE=touring env/bin/python scripts/smoke.py`
Expected: `40/40 passed`（文字・声・続けての質問が、新しい Agent で答えられる）

- [ ] **Step 5: 結果を PROJECT.md に書いて、親にコミット**

`$ROOT/PROJECT.md` の plan 表の2の行を「✅ 完了（デプロイ済み・Agent の smoke と Backend の smoke 40/40）」にし、「次にやること」を plan 3（Android: 質問と録音）の writing-plans にする。

```bash
cd $ROOT && git add PROJECT.md && git commit -m "docs: record slice 5 plan 2 as deployed with the smoke runs passing"
```

最終レビュー・後回しの指摘の書き出し・finishing は、CLAUDE.md の区切り点のとおりに行う。
