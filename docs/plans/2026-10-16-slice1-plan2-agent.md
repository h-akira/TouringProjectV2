# スライス1 計画2: Agent 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 質問（Backend が組んだプロンプトと数値の現在地）を受け、Web 検索と周辺検索を使って読み上げ向けの回答を返す Agent を、AgentCore Runtime（us-east-1）にデプロイし、決まった質問で通しを確かめる。

**Architecture:** AgentCore の CLI（0.31.1）が作るプロジェクト（`agentcore/` の設定と CDK、`app/` の Python）を土台にする。Python 側は小さなモジュールに分け、AWS とモデルに触れない部分（履歴の整理・フック・イベントの整形・幾何計算・設定値の読み込み）は単体テストで固める。呼び出しごとに Strands の Agent を作り、セッションごとの履歴（質問と回答の文だけ）を Runtime のプロセスの中に持つ。

**Tech Stack:** Python 3.14（Runtime の `PYTHON_3_14`）・uv・pytest、strands-agents 1.61・bedrock-agentcore 1.24・mcp-proxy-for-aws 1.7・boto3、AgentCore CLI 0.31.1（`npx @aws/agentcore@0.31.1`）・CDK（TypeScript、CLI が生成）。

**Spec:** [docs/specs/2026-10-16-slice1-design.md](../specs/2026-10-16-slice1-design.md)（§4.3・§7・§8・§9）、[adr/0003](../../adr/0003-conversation-context.md)

## Global Constraints

- 作業するリポジトリは `Agent/`（`TouringProjectV2_Agent`）。親の文書を直すのは Task 9 だけ。どちらも `main` から作業ブランチ `slice1-plan2` を切って作業する。push はしない。
- リージョンは `us-east-1`。設定値 `/trv2/dev/agent-runtime-arn` だけは `ap-northeast-1` に置く（UC-3）。
- 名前: プロジェクト `trv2Agent`、Runtime `agentcore_trv2_dev_ask`（AWS 上は `trv2Agent_agentcore_trv2_dev_ask`）、Gateway `gwTrv2DevMain`、スタック `AgentCore-trv2Agent-default`。設定値 `/trv2/dev/agent-model-id`（us-east-1）。
- Runtime のアイドルの時間切れは 3600 秒（60分）に固定する。
- 最初のモデルは `us.anthropic.claude-sonnet-5-5`。モデル ID はコードに書かず、SSM から読む（60秒キャッシュ）。読めないときは失敗として返す。
- ツールの呼び出しは1回の質問につき4回まで。超えたら打ち切りのメッセージを返し、手持ちの情報で答えさせる。モデルの呼び出しの周回は8回で打ち切る（保険）。
- ツールの結果は合計3000文字までに切り詰めてから AI に渡す。
- 履歴は質問と最後の回答の文だけを残し、直近10メッセージ（5往復）まで。
- コミットする文書・コードに、AWS のアカウント ID・ARN・実際の位置（試験に使う公共のランドマーク以外）を書かない。`agentcore/aws-targets.json` と `agentcore/.cli/deployed-state.json` は追跡しない。
- ソースコードのコメントは英語、文書は日本語。コミットは Conventional Commits。文書に、このプロジェクトより前の版への言及を書かない。
- `git add .`・`git add -A` は使わない。AWS のリソースを消す前は利用者に確認する。プロファイルは `touring`。
- 以下 `AGENT=<親リポジトリの絶対パス>/Agent`、`APP=$AGENT/app/agentcore_trv2_dev_ask`。

## Review Focus

- 失敗した質問（例外・回答が空）のあとで次の質問をする → 失敗した質問は履歴に残らず、次の質問は普通に答えられる（ユーザーの発話が2つ続いた履歴を作らない）。Task 3 の `test_failed_turn_leaves_no_dangling_question`、Task 6 の `test_error_does_not_store_history`。
- 検索の結果が JSON のブロックで返る・とても長い → 文字数の上限で切り詰められ、上限以下なら元のまま渡る。Task 4 の `test_json_blocks_are_counted_and_trimmed`・`test_short_result_is_unchanged`。
- 前置き（「調べます」）を書いてからツールを呼ぶ → 回答（`done.answer`）には前置きが入らない。Task 6 の `test_answer_excludes_preface_before_tool_call`。
- 現在地が無い・値が壊れている（文字列・真偽値・NaN でない数値以外）→ 周辺検索は「現在地が分からない」と答え、例外にしない。Task 2 の `test_unusable_location_is_none`。
- SSM の読み込みに失敗した直後に、もう一度呼ばれる → 失敗はキャッシュされず、次の呼び出しで読み直す。Task 5 の `test_failure_is_not_cached`。

---

## ファイル構成

| パス（`Agent/` から） | 役割 |
|---|---|
| `agentcore/agentcore.json` | プロジェクトの設定（Runtime・Gateway・環境変数・アイドルの時間切れ） |
| `agentcore/aws-targets-sample.json` | デプロイ先の雛形（実物の `aws-targets.json` は追跡しない） |
| `agentcore/cdk/lib/cdk-stack.ts` | CLI が生成した CDK。Runtime の権限（Location・SSM）を足す |
| `app/agentcore_trv2_dev_ask/pyproject.toml` | 依存 |
| `app/agentcore_trv2_dev_ask/main.py` | エントリポイント。部品を組み立てるだけ |
| `app/agentcore_trv2_dev_ask/config.py` | 環境変数から設定を読む |
| `app/agentcore_trv2_dev_ask/model_config.py` | SSM からモデル ID を読む（キャッシュ付き） |
| `app/agentcore_trv2_dev_ask/history.py` | 履歴の整理とセッションごとの保管 |
| `app/agentcore_trv2_dev_ask/hooks.py` | ツールの呼び出し回数の上限と、結果の切り詰め |
| `app/agentcore_trv2_dev_ask/stream.py` | Strands のイベントを Backend 向けのイベントに整える |
| `app/agentcore_trv2_dev_ask/handler.py` | 1回の呼び出しの流れ（部品を差し替えてテストできる） |
| `app/agentcore_trv2_dev_ask/prompt.py` | システムプロンプト |
| `app/agentcore_trv2_dev_ask/tools/places.py` | 周辺検索（`nearby_places`・`find_place`）と幾何計算 |
| `app/agentcore_trv2_dev_ask/tools/web_search.py` | Gateway の Web 検索への MCP クライアント |
| `app/agentcore_trv2_dev_ask/tests/` | 単体テスト |
| `scripts/smoke.py` | デプロイした Runtime に決まった質問を投げる |
| `README.md` | 設計の要約とデプロイの手順 |

## Backend との約束（この計画で決め、Task 9 で 07 に書く）

呼び出しの本文（JSON）:

```json
{"prompt": "（Backend が組んだプロンプト）", "location": {"latitude": 35.6812, "longitude": 139.7671, "headingDegrees": 0.0}}
```

`location` は無ければ `null`。`headingDegrees` は方位が無ければ `null`。

応答は SSE（`text/event-stream`）。各行は `data: <JSON>`。

| `type` | 中身 | 用途 |
|---|---|---|
| `text` | `{"type": "text", "text": "<断片>"}` | 回答の文の断片（前置きも含む）。スライス1の Backend は使わない |
| `tool` | `{"type": "tool", "name": "<ツール名>"}` | ツールの呼び出しが始まった |
| `done` | `{"type": "done", "answer": "<回答>", "stopReason": "<理由>", "usage": {"inputTokens": n, "outputTokens": n, "modelCalls": n}, "modelId": "<ID>"}` | 最後に1回。`answer` は最後のツール呼び出しより後ろの回答だけ |
| `error` | `{"type": "error", "code": "bad_request" または "agent_failed", "message": "<理由>"}` | 失敗。`done` は来ない |

---

### Task 1: プロジェクトの土台

**Files:**
- Create: `Agent/agentcore/`（CLI が生成）、`Agent/app/agentcore_trv2_dev_ask/`（CLI が生成し、雛形のコードは消す）、`Agent/agentcore/aws-targets-sample.json`
- Modify: `Agent/.gitignore`、`Agent/agentcore/agentcore.json`、`Agent/agentcore/cdk/lib/cdk-stack.ts`、`Agent/app/agentcore_trv2_dev_ask/pyproject.toml`
- Test: `Agent/app/agentcore_trv2_dev_ask/tests/test_config.py`、`Agent/app/agentcore_trv2_dev_ask/config.py`

**Interfaces:**
- Produces: `config.Settings`（frozen dataclass。`model_id_parameter: str`・`region: str`・`max_tokens: int`・`max_tool_calls: int`・`max_turns: int`・`max_history_messages: int`・`max_tool_result_chars: int`・`model_cache_seconds: float`）と `config.load_settings(env: Mapping[str, str] = os.environ) -> Settings`。テストは `cd $APP && uv run pytest`。

- [ ] **Step 1: 作業ブランチを切り、CLI でスクラッチに生成する**

```bash
cd $AGENT && git switch -c slice1-plan2
SCRATCH=$(mktemp -d) && cd "$SCRATCH"
npx -y @aws/agentcore@0.31.1 create --project-name trv2Agent --name agentcore_trv2_dev_ask \
  --framework Strands --model-provider Bedrock --memory none --build CodeZip --language Python \
  --protocol HTTP --network-mode PUBLIC --idle-timeout 3600
cd trv2Agent
npx -y @aws/agentcore@0.31.1 add gateway --name gwTrv2DevMain --description "Web search gateway for the touring agent" \
  --protocol-type MCP --authorizer-type AWS_IAM --json
npx -y @aws/agentcore@0.31.1 add gateway-target --name webSearch --gateway gwTrv2DevMain --type connector --connector web-search --json
```
Expected: `Project created successfully!`、`{"success":true,"gatewayName":"gwTrv2DevMain"}`、`{"success":true,"toolName":"webSearch"}`。

- [ ] **Step 2: 生成物を `Agent/` に写し、雛形のコードを消す**

```bash
cd "$SCRATCH/trv2Agent"
rsync -a --exclude '.git/' --exclude 'node_modules/' --exclude '.venv/' --exclude 'README.md' --exclude 'AGENTS.md' agentcore app "$AGENT/"
cd $APP && rm -rf mcp_client skills model main.py README.md
ls
```
Expected: `pyproject.toml uv.lock .gitignore` が残る（`main.py` は Task 6 で書く）。

- [ ] **Step 3: 追跡しないものを `.gitignore` に足す**

`Agent/.gitignore` の末尾に足す:

```
# AgentCore: files that hold the account id or deployed ARNs
agentcore/aws-targets.json
agentcore/.cli/
agentcore/.env.local
agentcore/cdk/cdk.out/
agentcore/cdk/node_modules/
agentcore/cdk/dist/
```

`Agent/agentcore/aws-targets-sample.json`:

```json
[
  {
    "name": "default",
    "account": "<ACCOUNT_ID>",
    "region": "us-east-1"
  }
]
```

- [ ] **Step 4: Runtime の環境変数を `agentcore.json` に足す**

`agentcore/agentcore.json` の `runtimes[0]` に、`"lifecycleConfiguration"` の直前へ次を足す（`idleRuntimeSessionTimeout: 3600` が入っていることも確かめる）:

```json
      "envVars": [
        { "name": "MODEL_ID_PARAMETER", "value": "/trv2/dev/agent-model-id" },
        { "name": "BEDROCK_MAX_TOKENS", "value": "800" },
        { "name": "AGENT_MAX_TOOL_CALLS", "value": "4" },
        { "name": "AGENT_MAX_TURNS", "value": "8" },
        { "name": "AGENT_MAX_HISTORY_MESSAGES", "value": "10" },
        { "name": "AGENT_MAX_TOOL_RESULT_CHARS", "value": "3000" }
      ],
```

- [ ] **Step 5: Runtime の権限を CDK に足す**

`agentcore/cdk/lib/cdk-stack.ts` の `this.application = new AgentCoreApplication(this, 'Application', appProps as any);` の直後に足す:

```ts
    // Project addition, not CLI output: agentcore.json has no field that grants a
    // runtime extra permissions. Keep this block if cdk/ is ever regenerated.
    // - geo-places: the place tools call Amazon Location directly (no per-resource ARN for search).
    // - ssm: the model id is read from a parameter so it can change without a deploy.
    for (const env of this.application.environments.values()) {
      env.runtime.role.addToPrincipalPolicy(
        new iam.PolicyStatement({
          actions: ['geo-places:SearchNearby', 'geo-places:SearchText'],
          resources: ['*'],
        })
      );
      env.runtime.role.addToPrincipalPolicy(
        new iam.PolicyStatement({
          actions: ['ssm:GetParameter'],
          resources: [`arn:aws:ssm:${this.region}:${this.account}:parameter/trv2/*`],
        })
      );
    }
```

- [ ] **Step 6: 依存を決める**

`app/agentcore_trv2_dev_ask/pyproject.toml` の `dependencies` を次に置き換え、テスト用の依存を足す:

```toml
dependencies = [
    "aws-opentelemetry-distro ~= 0.18.0",
    "bedrock-agentcore[strands-agents] >= 1.24.1",
    "boto3 >= 1.43.0",
    "botocore[crt] >= 1.35.0",
    "mcp-proxy-for-aws >= 1.7.0",
    "strands-agents >= 1.61.1",
]

[dependency-groups]
# Test-only; `uv sync --no-dev` (used for packaging) leaves it out.
dev = ["pytest >= 8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Run: `cd $APP && uv sync`
Expected: 依存が入る（`uv.lock` が更新される）。

- [ ] **Step 7: 設定の読み込みのテストを書く（失敗を確かめる）**

`tests/test_config.py`:

```python
"""Tests for config.load_settings."""
from config import load_settings


def test_defaults():
    settings = load_settings({})
    assert settings.model_id_parameter == "/trv2/dev/agent-model-id"
    assert settings.region == "us-east-1"
    assert settings.max_tokens == 800
    assert settings.max_tool_calls == 4
    assert settings.max_turns == 8
    assert settings.max_history_messages == 10
    assert settings.max_tool_result_chars == 3000
    assert settings.model_cache_seconds == 60.0


def test_environment_overrides():
    settings = load_settings({
        "MODEL_ID_PARAMETER": "/trv2/prod/agent-model-id",
        "AWS_REGION": "us-west-2",
        "BEDROCK_MAX_TOKENS": "500",
        "AGENT_MAX_TOOL_CALLS": "2",
        "AGENT_MAX_TURNS": "5",
        "AGENT_MAX_HISTORY_MESSAGES": "6",
        "AGENT_MAX_TOOL_RESULT_CHARS": "1000",
        "MODEL_ID_CACHE_SECONDS": "5",
    })
    assert settings.model_id_parameter == "/trv2/prod/agent-model-id"
    assert settings.region == "us-west-2"
    assert (settings.max_tokens, settings.max_tool_calls, settings.max_turns) == (500, 2, 5)
    assert (settings.max_history_messages, settings.max_tool_result_chars) == (6, 1000)
    assert settings.model_cache_seconds == 5.0
```

Run: `cd $APP && uv run pytest tests/test_config.py -v`
Expected: `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 8: 設定の読み込みを書く**

`config.py`:

```python
"""Runtime settings, read from environment variables set in agentcore.json."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    model_id_parameter: str
    region: str
    max_tokens: int
    max_tool_calls: int
    max_turns: int
    max_history_messages: int
    max_tool_result_chars: int
    model_cache_seconds: float


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    """Build settings from the environment, falling back to the slice-1 defaults."""
    return Settings(
        model_id_parameter=env.get("MODEL_ID_PARAMETER", "/trv2/dev/agent-model-id"),
        region=env.get("AWS_REGION", "us-east-1"),
        max_tokens=int(env.get("BEDROCK_MAX_TOKENS", "800")),
        max_tool_calls=int(env.get("AGENT_MAX_TOOL_CALLS", "4")),
        max_turns=int(env.get("AGENT_MAX_TURNS", "8")),
        max_history_messages=int(env.get("AGENT_MAX_HISTORY_MESSAGES", "10")),
        max_tool_result_chars=int(env.get("AGENT_MAX_TOOL_RESULT_CHARS", "3000")),
        model_cache_seconds=float(env.get("MODEL_ID_CACHE_SECONDS", "60")),
    )
```

- [ ] **Step 9: テストと設定の検査を通す**

```bash
cd $APP && uv run pytest tests/test_config.py -v
cd $AGENT && npx -y @aws/agentcore@0.31.1 validate
cd $AGENT/agentcore/cdk && npm ci && npx tsc --noEmit
```
Expected: 2 passed。`validate` が成功する。`tsc` がエラーなし。

- [ ] **Step 10: コミット**

```bash
cd $AGENT
git add .gitignore agentcore/agentcore.json agentcore/aws-targets-sample.json agentcore/.gitignore agentcore/.llm-context agentcore/cdk/bin agentcore/cdk/lib agentcore/cdk/test agentcore/cdk/package.json agentcore/cdk/package-lock.json agentcore/cdk/cdk.json agentcore/cdk/tsconfig.json agentcore/cdk/jest.config.js agentcore/cdk/.gitignore agentcore/cdk/.npmignore agentcore/cdk/.prettierrc agentcore/cdk/README.md app/agentcore_trv2_dev_ask/pyproject.toml app/agentcore_trv2_dev_ask/uv.lock app/agentcore_trv2_dev_ask/.gitignore app/agentcore_trv2_dev_ask/config.py app/agentcore_trv2_dev_ask/tests/test_config.py
git status --short
git commit -m "feat: scaffold agentcore project with gateway and runtime settings"
```
`git status --short` に `aws-targets.json`・`.cli/` が出ないこと。

---

### Task 2: 周辺検索のツール

**Files:**
- Create: `app/agentcore_trv2_dev_ask/tools/__init__.py`（空）、`app/agentcore_trv2_dev_ask/tools/places.py`
- Test: `app/agentcore_trv2_dev_ask/tests/test_places.py`

**Interfaces:**
- Produces: `tools.places.LOCATION_KEY = "location"`、`read_location(invocation_state: dict | None) -> dict | None`（`{"latitude", "longitude", "heading"}`）、ツール `nearby_places(kind, tool_context, side=None, radius_km=5.0) -> str` と `find_place(name, tool_context, side=None) -> str`。位置は `tool_context.invocation_state["location"]`（`{"latitude", "longitude", "headingDegrees"}`）から読む。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_places.py`:

```python
"""Tests for the place tools: geometry, payload handling and failure paths."""
import math
from types import SimpleNamespace

import pytest

from tools import places

TOKYO_STATION = {"latitude": 35.6812, "longitude": 139.7671}


def _context(location=None) -> SimpleNamespace:
    state = {} if location is None else {places.LOCATION_KEY: location}
    return SimpleNamespace(invocation_state=state)


def _place(title: str, lat: float, lon: float, distance: int = 0) -> dict:
    return {"Title": title, "Position": [lon, lat], "Distance": distance}


class _Client:
    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def _reply(self, name: str, kwargs: dict) -> dict:
        self.calls.append((name, kwargs))
        if self.error is not None:
            raise self.error
        return {"ResultItems": self.items}

    def search_nearby(self, **kwargs):
        return self._reply("search_nearby", kwargs)

    def search_text(self, **kwargs):
        return self._reply("search_text", kwargs)


@pytest.fixture
def client(monkeypatch):
    stub = _Client()
    monkeypatch.setattr(places, "_client", stub)
    return stub


@pytest.mark.parametrize(
    "bearing, heading, expected",
    [(0, 0, "前方"), (90, 0, "右手"), (180, 0, "後方"), (270, 0, "左手"), (45, 0, "右前方"), (10, 350, "前方"), (0, 90, "左手")],
)
def test_side_of(bearing, heading, expected):
    assert places.side_of(bearing, heading) == expected


def test_bearing_points_the_right_way():
    assert places.bearing_degrees(35.0, 139.0, 36.0, 139.0) == pytest.approx(0, abs=0.5)
    assert places.bearing_degrees(35.0, 139.0, 35.0, 140.0) == pytest.approx(90, abs=1)


@pytest.mark.parametrize("bearing, expected", [(0, "北"), (90, "東"), (225, "南西"), (359, "北")])
def test_compass(bearing, expected):
    assert places.compass(bearing) == expected


@pytest.mark.parametrize("meters, expected", [(3, "約10m"), (240, "約240m"), (1234, "約1.2km")])
def test_format_distance(meters, expected):
    assert places.format_distance(meters) == expected


@pytest.mark.parametrize(
    "state",
    [
        None,
        {},
        {places.LOCATION_KEY: None},
        {places.LOCATION_KEY: {"latitude": "35", "longitude": 139.0}},
        {places.LOCATION_KEY: {"latitude": True, "longitude": 139.0}},
        {places.LOCATION_KEY: {"latitude": math.nan, "longitude": 139.0}},
        {places.LOCATION_KEY: {"latitude": 95.0, "longitude": 139.0}},
    ],
)
def test_unusable_location_is_none(state):
    assert places.read_location(state) is None


def test_heading_is_optional_and_validated():
    loc = places.read_location({places.LOCATION_KEY: {**TOKYO_STATION, "headingDegrees": "north"}})
    assert loc == {"latitude": 35.6812, "longitude": 139.7671, "heading": None}
    loc = places.read_location({places.LOCATION_KEY: {**TOKYO_STATION, "headingDegrees": 90}})
    assert loc["heading"] == 90.0


def test_nearby_uses_payload_position_longitude_first(client):
    places.nearby_places(kind="公園", tool_context=_context(TOKYO_STATION))
    name, kwargs = client.calls[0]
    assert name == "search_nearby"
    assert kwargs["QueryPosition"] == [139.7671, 35.6812]
    assert kwargs["Filter"] == {"IncludeCategories": ["park-recreation_area", "garden"]}
    assert kwargs["Language"] == "ja"


def test_nearby_states_side_direction_and_distance(client):
    client.items = [_place("東の公園", 35.6812, 139.7771)]
    answer = places.nearby_places(kind="公園", tool_context=_context({**TOKYO_STATION, "headingDegrees": 0}))
    assert "東の公園（右手・東の方角 約900m）" in answer


def test_side_filter_keeps_only_that_side(client):
    client.items = [_place("東", 35.6812, 139.7771), _place("西", 35.6812, 139.7571)]
    answer = places.nearby_places(kind="公園", side="右手", tool_context=_context({**TOKYO_STATION, "headingDegrees": 0}))
    assert "東" in answer and "西（" not in answer


def test_side_filter_without_heading_says_why(client):
    client.items = [_place("東", 35.6812, 139.7771)]
    answer = places.nearby_places(kind="公園", side="右手", tool_context=_context(TOKYO_STATION))
    assert answer == "進行方向が分からないため、左右では絞り込めませんでした。"


def test_no_side_without_heading(client):
    client.items = [_place("東", 35.6812, 139.7771)]
    answer = places.nearby_places(kind="公園", tool_context=_context(TOKYO_STATION))
    assert "東（東の方角 約900m）" in answer
    assert "左右は付けていません" in answer


def test_duplicates_listed_once_and_capped(client):
    client.items = [_place("同じ", 35.6813, 139.7672)] * 2 + [_place(f"店{i}", 35.68 + i / 1000, 139.767) for i in range(10)]
    answer = places.nearby_places(kind="公園", tool_context=_context(TOKYO_STATION))
    assert answer.count("同じ（") == 1
    assert answer.count("\n- ") == places.MAX_RETURNED


def test_radius_is_clamped(client):
    places.nearby_places(kind="山・自然", radius_km=500, tool_context=_context(TOKYO_STATION))
    assert client.calls[0][1]["QueryRadius"] == int(places.MAX_RADIUS_KM * 1000)


def test_find_place_is_biased_to_rider_and_sorted_by_distance(client):
    client.items = [_place("遠い", 35.70, 139.77, distance=2000), _place("近い", 35.682, 139.767, distance=100)]
    answer = places.find_place(name="マクドナルド", tool_context=_context(TOKYO_STATION))
    assert client.calls[0][1]["BiasPosition"] == [139.7671, 35.6812]
    assert answer.index("近い") < answer.index("遠い")


def test_no_location_means_no_search(client):
    assert places.find_place(name="マクドナルド", tool_context=_context()) == "現在地が分からないため、周辺を探せません。"
    assert client.calls == []


def test_aws_error_is_a_sentence(client):
    client.error = RuntimeError("boom")
    assert places.nearby_places(kind="公園", tool_context=_context(TOKYO_STATION)) == "周辺の検索に失敗しました。"


def test_nothing_found(client):
    assert places.find_place(name="存在しない店", tool_context=_context(TOKYO_STATION)) == "該当する場所は見つかりませんでした。"


def test_every_kind_has_categories():
    assert set(places.KINDS) == set(places.Kind.__args__)
    assert all(places.KINDS[kind] for kind in places.KINDS)
```

Run: `cd $APP && uv run pytest tests/test_places.py -v`
Expected: `ModuleNotFoundError: No module named 'tools'`

- [ ] **Step 2: 実装する**

`tools/__init__.py` は空のファイル。`tools/places.py`:

```python
"""Places around the rider, via Amazon Location Service (geo-places).

The geometry (distance, compass direction, left/right) is computed here so the
model never works it out itself, and the position comes from the payload via
invocation_state rather than from the model's arguments.
A failed lookup returns a sentence, not an exception, so the model can still answer.
"""
from __future__ import annotations

import math
import os
from typing import Any, Literal, Optional

import boto3
from strands import ToolContext, tool

PLACES_REGION = os.environ.get("PLACES_REGION", "us-east-1")
LOCATION_KEY = "location"

Kind = Literal[
    "公園", "山・自然", "観光地", "景色のよい場所", "神社・寺", "温泉", "ガソリンスタンド", "EV充電",
    "コンビニ", "道の駅・休憩所", "トイレ", "駐車場", "カフェ", "飲食店", "病院",
]
Side = Literal["右手", "左手", "前方", "後方"]

# Amazon Location category ids (case-sensitive ids, not display names).
KINDS: dict[str, list[str]] = {
    "公園": ["park-recreation_area", "garden"],
    "山・自然": ["natural_and_geographical", "mountain_or_hill"],
    "観光地": ["tourist_attraction"],
    "景色のよい場所": ["scenic_point"],
    "神社・寺": ["shrine", "temple"],
    "温泉": ["hot_spring"],
    "ガソリンスタンド": ["petrol-gasoline_station"],
    "EV充電": ["ev_charging_station"],
    "コンビニ": ["convenience_store"],
    "道の駅・休憩所": ["roadside_station", "rest_area", "parking_and_restroom_only_rest_area"],
    "トイレ": ["public_restroom-toilets"],
    "駐車場": ["parking"],
    "カフェ": ["coffee_shop"],
    "飲食店": ["restaurant", "casual_dining", "family_restaurant", "fast_food"],
    "病院": ["hospital"],
}

# Eight 45-degree sectors clockwise from straight ahead.
_SECTORS = ("前方", "右前方", "右手", "右後方", "後方", "左後方", "左手", "左前方")
# Diagonals belong to both neighbouring sides.
_SIDE_SECTORS: dict[str, set[str]] = {
    "右手": {"右前方", "右手", "右後方"},
    "左手": {"左前方", "左手", "左後方"},
    "前方": {"左前方", "前方", "右前方"},
    "後方": {"左後方", "後方", "右後方"},
}
_COMPASS_POINTS = (
    "北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東",
    "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西",
)

MAX_RETURNED = 5
MAX_FETCHED = 20
MIN_RADIUS_KM = 0.2
MAX_RADIUS_KM = 50.0

_NO_LOCATION = "現在地が分からないため、周辺を探せません。"
_FAILED = "周辺の検索に失敗しました。"

_client: Any = None


def _get_client() -> Any:
    """Build the client lazily so importing this module needs no credentials."""
    global _client
    if _client is None:
        _client = boto3.client("geo-places", region_name=PLACES_REGION)
    return _client


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, clockwise from north."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360


def compass(bearing: float) -> str:
    """16-point compass name for a bearing."""
    return _COMPASS_POINTS[int((bearing % 360) / 22.5 + 0.5) % 16]


def side_of(bearing: float, heading: float) -> str:
    """Sector of a bearing for a rider travelling along heading."""
    relative = (bearing - heading) % 360
    return _SECTORS[int(relative / 45 + 0.5) % 8]


def format_distance(meters: float) -> str:
    """Distance as it should be read aloud."""
    if meters < 1000:
        return f"約{max(10, round(meters, -1)):.0f}m"
    return f"約{meters / 1000:.1f}km"


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def read_location(invocation_state: Optional[dict]) -> Optional[dict]:
    """The rider's position and heading from the payload, or None if unusable."""
    location = (invocation_state or {}).get(LOCATION_KEY)
    if not isinstance(location, dict):
        return None
    lat, lon = _number(location.get("latitude")), _number(location.get("longitude"))
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return {"latitude": lat, "longitude": lon, "heading": _number(location.get("headingDegrees"))}


def describe_places(items: list[dict], location: dict, side: Optional[str] = None) -> list[str]:
    """Lines the model can read out as fact; distance and side come from each Position."""
    lat, lon, heading = location["latitude"], location["longitude"], location["heading"]
    lines: list[str] = []
    seen: set[str] = set()
    for item in items:
        title, position = item.get("Title"), item.get("Position")
        if not title or not isinstance(position, list) or len(position) != 2 or title in seen:
            continue
        place_lon, place_lat = position
        bearing = bearing_degrees(lat, lon, place_lat, place_lon)
        place_side = side_of(bearing, heading) if heading is not None else None
        if side is not None and place_side not in _SIDE_SECTORS[side]:
            continue
        seen.add(title)
        where = f"{compass(bearing)}の方角 {format_distance(_distance_meters(lat, lon, place_lat, place_lon))}"
        if place_side is not None:
            where = f"{place_side}・{where}"
        lines.append(f"{title}（{where}）")
        if len(lines) >= MAX_RETURNED:
            break
    return lines


def _answer(lines: list[str], location: dict, side: Optional[str]) -> str:
    if not lines:
        if side is not None and location["heading"] is None:
            return "進行方向が分からないため、左右では絞り込めませんでした。"
        return "該当する場所は見つかりませんでした。"
    header = "現在地から近い順（距離と方角は計算済み。言い換えずにそのまま使うこと）:"
    if location["heading"] is None:
        header += "\n進行方向が分からないため、左右は付けていません。"
    return header + "\n" + "\n".join(f"- {line}" for line in lines)


@tool(context=True)
def nearby_places(kind: Kind, tool_context: ToolContext, side: Optional[Side] = None, radius_km: float = 5.0) -> str:
    """現在地の周辺にある場所を種類で探し、近い順に距離・方角・左右を返す。

    「右手に見える山は？」「近くのコンビニは？」のように種類で探すときに使う。
    店やチェーンの名前は find_place を使う。現在地はシステムが渡すので、座標は指定しない。

    Args:
        kind: 探す場所の種類。
        side: 「右手に見える」「左手の」のように向きを言われたときだけ指定する。
        radius_km: 探す半径（km）。目に見えるものなら3〜5、道の駅やガソリンスタンドなら20程度、山なら15程度。
    """
    location = read_location(tool_context.invocation_state)
    if location is None:
        return _NO_LOCATION
    categories = KINDS.get(kind)
    if not categories:
        return f"「{kind}」という種類では探せません。"
    radius_m = int(min(max(radius_km, MIN_RADIUS_KM), MAX_RADIUS_KM) * 1000)
    try:
        result = _get_client().search_nearby(
            QueryPosition=[location["longitude"], location["latitude"]],
            QueryRadius=radius_m,
            MaxResults=MAX_FETCHED if side else MAX_RETURNED * 2,
            Language="ja",
            Filter={"IncludeCategories": categories},
        )
    except Exception as error:  # noqa: BLE001 - the model answers without it
        print(f"search_nearby failed: {type(error).__name__}")
        return _FAILED
    return _answer(describe_places(result.get("ResultItems") or [], location, side), location, side)


@tool(context=True)
def find_place(name: str, tool_context: ToolContext, side: Optional[Side] = None) -> str:
    """店・チェーン・施設・地名を名前で探し、現在地から近い順に距離・方角・左右を返す。

    「一番近いマクドナルドは？」「芦ノ湖までどのくらい？」のように名前が分かっているときに使う。
    現在地はシステムが渡すので、座標は指定しない。

    Args:
        name: 探す名前（例: マクドナルド、ENEOS、芦ノ湖）。地名や「近くの」は付けない。
        side: 「右手の」「左手の」のように向きを言われたときだけ指定する。
    """
    location = read_location(tool_context.invocation_state)
    if location is None:
        return _NO_LOCATION
    if not name.strip():
        return "探す名前が空です。"
    try:
        result = _get_client().search_text(
            QueryText=name.strip(),
            BiasPosition=[location["longitude"], location["latitude"]],
            MaxResults=MAX_FETCHED if side else MAX_RETURNED * 2,
            Language="ja",
        )
    except Exception as error:  # noqa: BLE001 - the model answers without it
        print(f"search_text failed: {type(error).__name__}")
        return _FAILED
    items = sorted(result.get("ResultItems") or [], key=lambda item: item.get("Distance", float("inf")))
    return _answer(describe_places(items, location, side), location, side)
```

- [ ] **Step 3: テストを通す**

Run: `cd $APP && uv run pytest tests/test_places.py -v`
Expected: すべて PASS。

- [ ] **Step 4: コミット**

```bash
cd $AGENT
git add app/agentcore_trv2_dev_ask/tools/__init__.py app/agentcore_trv2_dev_ask/tools/places.py app/agentcore_trv2_dev_ask/tests/test_places.py
git commit -m "feat: add nearby_places and find_place tools"
```

---

### Task 3: 履歴の整理と保管

**Files:**
- Create: `app/agentcore_trv2_dev_ask/history.py`
- Test: `app/agentcore_trv2_dev_ask/tests/test_history.py`

**Interfaces:**
- Produces: `history.prune_history(messages: list[dict], max_messages: int) -> list[dict]`、`history.SessionStore(max_sessions: int = 128)`（`get(session_id: str) -> list[dict]` は写しを返す、`put(session_id: str, messages: list[dict]) -> None`）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_history.py`:

```python
"""Tests for history pruning and the per-session store."""
from history import SessionStore, prune_history


def user(text):
    return {"role": "user", "content": [{"text": text}]}


def assistant(text):
    return {"role": "assistant", "content": [{"text": text}]}


TOOL_TURN = [
    user("Q1"),
    {"role": "assistant", "content": [{"text": "調べます。"}, {"toolUse": {"toolUseId": "t1", "name": "web", "input": {}}}]},
    {"role": "user", "content": [{"toolResult": {"toolUseId": "t1", "content": [{"text": "長い検索結果"}]}}]},
    assistant("A1"),
]


def test_tool_turn_keeps_question_and_final_answer_only():
    assert prune_history(TOOL_TURN, 10) == [user("Q1"), assistant("A1")]


def test_non_text_blocks_are_dropped():
    message = {"role": "assistant", "content": [{"reasoningContent": {"reasoningText": {"text": "x"}}}, {"text": "A"}]}
    assert prune_history([user("Q"), message], 10) == [user("Q"), assistant("A")]


def test_window_keeps_latest_and_starts_with_user():
    messages = []
    for i in range(6):
        messages += [user(f"Q{i}"), assistant(f"A{i}")]
    pruned = prune_history(messages, 5)
    assert pruned[0] == user("Q4")
    assert pruned == [user("Q4"), assistant("A4"), user("Q5"), assistant("A5")]


def test_failed_turn_leaves_no_dangling_question():
    messages = [user("Q1"), assistant("A1"), user("Q2 failed"), user("Q3"), assistant("A3")]
    assert prune_history(messages, 10) == [user("Q1"), assistant("A1"), user("Q3"), assistant("A3")]


def test_trailing_question_without_answer_is_dropped():
    assert prune_history([user("Q1"), assistant("A1"), user("Q2")], 10) == [user("Q1"), assistant("A1")]


def test_empty_text_is_dropped():
    assert prune_history([user("Q"), assistant("  ")], 10) == []


def test_store_returns_copies():
    store = SessionStore()
    store.put("s", [user("Q"), assistant("A")])
    got = store.get("s")
    got.append(user("mutated"))
    assert store.get("s") == [user("Q"), assistant("A")]
    assert store.get("unknown") == []


def test_store_evicts_least_recently_used():
    store = SessionStore(max_sessions=2)
    store.put("a", [user("a")])
    store.put("b", [user("b")])
    store.get("a")
    store.put("c", [user("c")])
    assert store.get("b") == []
    assert store.get("a") == [user("a")]
```

Run: `cd $APP && uv run pytest tests/test_history.py -v`
Expected: `ModuleNotFoundError: No module named 'history'`

- [ ] **Step 2: 実装する**

`history.py`:

```python
"""Conversation history per session: only the questions and the final answers.

Tool calls and their (large) results are dropped after each turn so the next
question does not resend them to the model.
"""
from __future__ import annotations

import copy
from collections import OrderedDict
from typing import Any

Message = dict[str, Any]


def _has_tool_block(message: Message) -> bool:
    return any("toolUse" in block or "toolResult" in block for block in message.get("content", []))


def _text_only(message: Message) -> Message | None:
    blocks = [
        {"text": block["text"]}
        for block in message.get("content", [])
        if isinstance(block.get("text"), str) and block["text"].strip()
    ]
    return {"role": message["role"], "content": blocks} if blocks else None


def prune_history(messages: list[Message], max_messages: int) -> list[Message]:
    """Keep alternating user/assistant text messages, latest first, ending with an answer."""
    kept: list[Message] = []
    for message in messages:
        if _has_tool_block(message):
            continue
        text = _text_only(message)
        if text is None:
            continue
        if kept and kept[-1]["role"] == text["role"]:
            kept[-1] = text  # keep the later one so roles alternate
        else:
            kept.append(text)
    if kept and kept[-1]["role"] == "user":
        kept.pop()  # a question without an answer (failed turn)
    kept = kept[-max_messages:] if max_messages > 0 else []
    while kept and kept[0]["role"] != "user":
        kept.pop(0)
    return kept


class SessionStore:
    """In-process history per runtime session, bounded by least-recently-used eviction."""

    def __init__(self, max_sessions: int = 128) -> None:
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, list[Message]] = OrderedDict()

    def get(self, session_id: str) -> list[Message]:
        if session_id not in self._sessions:
            return []
        self._sessions.move_to_end(session_id)
        return copy.deepcopy(self._sessions[session_id])

    def put(self, session_id: str, messages: list[Message]) -> None:
        self._sessions[session_id] = copy.deepcopy(messages)
        self._sessions.move_to_end(session_id)
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)
```

- [ ] **Step 3: テストを通す**

Run: `cd $APP && uv run pytest tests/test_history.py -v`
Expected: 8 passed。

- [ ] **Step 4: コミット**

```bash
cd $AGENT
git add app/agentcore_trv2_dev_ask/history.py app/agentcore_trv2_dev_ask/tests/test_history.py
git commit -m "feat: keep only questions and final answers in session history"
```

---

### Task 4: ツールの呼び出し回数の上限と、結果の切り詰め

**Files:**
- Create: `app/agentcore_trv2_dev_ask/hooks.py`
- Test: `app/agentcore_trv2_dev_ask/tests/test_hooks.py`

**Interfaces:**
- Produces: `hooks.LIMIT_MESSAGE: str`、`hooks.ToolCallLimit(max_calls: int)`（`HookProvider`。`on_before_tool_call(event)` は `event.cancel_tool` を設定する）、`hooks.trim_tool_result(result: dict, max_chars: int) -> dict`、`hooks.ToolResultTrimmer(max_chars: int)`（`HookProvider`。`on_after_tool_call(event)` は `event.result` を置き換える）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_hooks.py`:

```python
"""Tests for the tool-call limit and the tool-result trimming hooks."""
from types import SimpleNamespace

from strands.hooks import HookRegistry

from hooks import LIMIT_MESSAGE, TRUNCATED_SUFFIX, ToolCallLimit, ToolResultTrimmer, trim_tool_result


def before_event():
    return SimpleNamespace(cancel_tool=False, tool_use={"name": "web", "toolUseId": "t"})


def test_calls_within_limit_run():
    limit = ToolCallLimit(max_calls=2)
    events = [before_event() for _ in range(2)]
    for event in events:
        limit.on_before_tool_call(event)
    assert [e.cancel_tool for e in events] == [False, False]


def test_calls_over_limit_are_cancelled_with_message():
    limit = ToolCallLimit(max_calls=1)
    first, second, third = before_event(), before_event(), before_event()
    for event in (first, second, third):
        limit.on_before_tool_call(event)
    assert first.cancel_tool is False
    assert second.cancel_tool == LIMIT_MESSAGE
    assert third.cancel_tool == LIMIT_MESSAGE


def test_hooks_register_callbacks():
    registry = HookRegistry()
    ToolCallLimit(1).register_hooks(registry)
    ToolResultTrimmer(10).register_hooks(registry)
    assert registry.has_callbacks()


def test_short_result_is_unchanged():
    result = {"toolUseId": "t", "status": "success", "content": [{"text": "abc"}, {"json": {"k": 1}}]}
    assert trim_tool_result(result, 100) == result


def test_long_text_is_cut_at_budget():
    result = {"toolUseId": "t", "status": "success", "content": [{"text": "a" * 10}, {"text": "b" * 10}]}
    trimmed = trim_tool_result(result, 15)
    assert trimmed["content"] == [{"text": "a" * 10}, {"text": "b" * 5 + TRUNCATED_SUFFIX}]
    assert trimmed["toolUseId"] == "t" and trimmed["status"] == "success"


def test_json_blocks_are_counted_and_trimmed():
    result = {"toolUseId": "t", "status": "success", "content": [{"json": {"results": ["x" * 50]}}]}
    trimmed = trim_tool_result(result, 20)
    assert len(trimmed["content"]) == 1
    assert trimmed["content"][0]["text"].endswith(TRUNCATED_SUFFIX)
    assert len(trimmed["content"][0]["text"]) == 20 + len(TRUNCATED_SUFFIX)


def test_trimmer_replaces_event_result():
    event = SimpleNamespace(result={"toolUseId": "t", "status": "success", "content": [{"text": "a" * 30}]})
    ToolResultTrimmer(max_chars=10).on_after_tool_call(event)
    assert event.result["content"] == [{"text": "a" * 10 + TRUNCATED_SUFFIX}]


def test_trimmer_ignores_non_dict_results():
    error = RuntimeError("x")
    event = SimpleNamespace(result=error)
    ToolResultTrimmer(max_chars=10).on_after_tool_call(event)
    assert event.result is error
```

Run: `cd $APP && uv run pytest tests/test_hooks.py -v`
Expected: `ModuleNotFoundError: No module named 'hooks'`

- [ ] **Step 2: 実装する**

`hooks.py`:

```python
"""Hooks that bound the cost of one question: a tool-call cap and tool-result trimming."""
from __future__ import annotations

import json
from typing import Any

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry

LIMIT_MESSAGE = "ツールの呼び出し回数の上限に達しました。これ以上は調べずに、手持ちの情報で答えてください。"
TRUNCATED_SUFFIX = "…（以下省略）"


class ToolCallLimit(HookProvider):
    """Cancel tool calls past max_calls so the model answers with what it has."""

    def __init__(self, max_calls: int) -> None:
        self.max_calls = max_calls
        self.calls = 0

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.on_before_tool_call)

    def on_before_tool_call(self, event: Any) -> None:
        self.calls += 1
        if self.calls > self.max_calls:
            event.cancel_tool = LIMIT_MESSAGE


def _block_text(block: dict) -> str | None:
    if isinstance(block.get("text"), str):
        return block["text"]
    if "json" in block:
        return json.dumps(block["json"], ensure_ascii=False)
    return None


def trim_tool_result(result: dict, max_chars: int) -> dict:
    """Return the result with its text cut to max_chars in total; unchanged if it already fits."""
    texts = [text for text in (_block_text(block) for block in result.get("content", [])) if text is not None]
    if sum(len(text) for text in texts) <= max_chars:
        return result
    remaining = max_chars
    blocks: list[dict] = []
    for text in texts:
        if remaining <= 0:
            break
        if len(text) > remaining:
            blocks.append({"text": text[:remaining] + TRUNCATED_SUFFIX})
            remaining = 0
        else:
            blocks.append({"text": text})
            remaining -= len(text)
    return {**result, "content": blocks}


class ToolResultTrimmer(HookProvider):
    """Trim every tool result before it reaches the model (search results dominate input tokens)."""

    def __init__(self, max_chars: int) -> None:
        self.max_chars = max_chars

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self.on_after_tool_call)

    def on_after_tool_call(self, event: Any) -> None:
        if isinstance(event.result, dict):
            event.result = trim_tool_result(event.result, self.max_chars)
```

- [ ] **Step 3: テストを通す**

Run: `cd $APP && uv run pytest tests/test_hooks.py -v`
Expected: 8 passed。`has_callbacks` が無いというエラーなら、`HookRegistry` の公開メソッドを `uv run python -c "from strands.hooks import HookRegistry; print([m for m in dir(HookRegistry) if not m.startswith('_')])"` で確かめ、登録の有無を判定できるメソッドに置き換える（置き換えは ledger に記録）。

- [ ] **Step 4: コミット**

```bash
cd $AGENT
git add app/agentcore_trv2_dev_ask/hooks.py app/agentcore_trv2_dev_ask/tests/test_hooks.py
git commit -m "feat: cap tool calls and trim tool results per question"
```

---

### Task 5: モデル ID を SSM から読む

**Files:**
- Create: `app/agentcore_trv2_dev_ask/model_config.py`
- Test: `app/agentcore_trv2_dev_ask/tests/test_model_config.py`

**Interfaces:**
- Produces: `model_config.ModelIdError(RuntimeError)`、`model_config.ModelIdSource(parameter_name: str, ssm_client: Any, cache_seconds: float, clock: Callable[[], float] = time.monotonic)`（`get() -> str`。失敗は `ModelIdError`）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_model_config.py`:

```python
"""Tests for reading the model id from SSM with a short cache."""
import pytest

from model_config import ModelIdError, ModelIdSource


class FakeSsm:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def get_parameter(self, Name):
        self.calls += 1
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return {"Parameter": {"Name": Name, "Value": value}}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_reads_once_within_cache_window():
    ssm, clock = FakeSsm(["model-a"]), Clock()
    source = ModelIdSource("/p", ssm, cache_seconds=60, clock=clock)
    assert source.get() == "model-a"
    clock.now = 59
    assert source.get() == "model-a"
    assert ssm.calls == 1


def test_rereads_after_cache_expires():
    ssm, clock = FakeSsm(["model-a", "model-b"]), Clock()
    source = ModelIdSource("/p", ssm, cache_seconds=60, clock=clock)
    source.get()
    clock.now = 61
    assert source.get() == "model-b"


def test_value_is_stripped_and_empty_is_an_error():
    assert ModelIdSource("/p", FakeSsm([" model-a \n"]), 60, Clock()).get() == "model-a"
    with pytest.raises(ModelIdError, match="/p is empty"):
        ModelIdSource("/p", FakeSsm(["  "]), 60, Clock()).get()


def test_client_error_is_wrapped():
    with pytest.raises(ModelIdError, match="failed to read /p: RuntimeError"):
        ModelIdSource("/p", FakeSsm([RuntimeError("denied")]), 60, Clock()).get()


def test_failure_is_not_cached():
    ssm = FakeSsm([RuntimeError("denied"), "model-a"])
    source = ModelIdSource("/p", ssm, 60, Clock())
    with pytest.raises(ModelIdError):
        source.get()
    assert source.get() == "model-a"
```

Run: `cd $APP && uv run pytest tests/test_model_config.py -v`
Expected: `ModuleNotFoundError: No module named 'model_config'`

- [ ] **Step 2: 実装する**

`model_config.py`:

```python
"""The model id lives in SSM so an admin can switch models without a deploy."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class ModelIdError(RuntimeError):
    """The model id could not be read; the question fails instead of guessing a model."""


class ModelIdSource:
    def __init__(
        self,
        parameter_name: str,
        ssm_client: Any,
        cache_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._name = parameter_name
        self._ssm = ssm_client
        self._cache_seconds = cache_seconds
        self._clock = clock
        self._cached: tuple[str, float] | None = None

    def get(self) -> str:
        now = self._clock()
        if self._cached is not None and now - self._cached[1] < self._cache_seconds:
            return self._cached[0]
        try:
            value = self._ssm.get_parameter(Name=self._name)["Parameter"]["Value"].strip()
        except Exception as error:
            raise ModelIdError(f"failed to read {self._name}: {type(error).__name__}") from error
        if not value:
            raise ModelIdError(f"{self._name} is empty")
        self._cached = (value, now)
        return value
```

- [ ] **Step 3: テストを通す**

Run: `cd $APP && uv run pytest tests/test_model_config.py -v`
Expected: 5 passed。

- [ ] **Step 4: コミット**

```bash
cd $AGENT
git add app/agentcore_trv2_dev_ask/model_config.py app/agentcore_trv2_dev_ask/tests/test_model_config.py
git commit -m "feat: read model id from ssm with a short cache"
```

---

### Task 6: 1回の呼び出しの流れとイベントの整形

**Files:**
- Create: `app/agentcore_trv2_dev_ask/stream.py`、`app/agentcore_trv2_dev_ask/handler.py`
- Test: `app/agentcore_trv2_dev_ask/tests/test_stream.py`、`app/agentcore_trv2_dev_ask/tests/test_handler.py`

**Interfaces:**
- Consumes: `history.prune_history`・`history.SessionStore`（Task 3）、`model_config.ModelIdError`（Task 5）、`config.Settings`（Task 1）、`tools.places.LOCATION_KEY`（Task 2）。
- Produces: `stream.final_answer(message: dict) -> str`、`stream.EventShaper`（`shape(event: dict) -> list[dict]`）、`stream.done_event(result: Any, model_id: str) -> dict`、`stream.error_event(code: str, message: str) -> dict`、`handler.Deps`（dataclass: `settings`・`model_ids`（`get() -> str` を持つ）・`sessions`（`SessionStore`）・`agent_factory: Callable[[str, list[dict]], Any]`）、`async handler.handle(payload: dict, session_id: str, deps: Deps) -> AsyncIterator[dict]`。

- [ ] **Step 1: 整形のテストを書く**

`tests/test_stream.py`:

```python
"""Tests for shaping Strands events into the events sent to the Backend."""
from types import SimpleNamespace

from stream import EventShaper, done_event, error_event, final_answer


def test_text_delta_becomes_text_event():
    assert EventShaper().shape({"data": "こん", "delta": {}}) == [{"type": "text", "text": "こん"}]


def test_tool_use_is_reported_once_per_call():
    shaper = EventShaper()
    event = {"type": "tool_use_stream", "current_tool_use": {"toolUseId": "t1", "name": "nearby_places", "input": ""}}
    assert shaper.shape(event) == [{"type": "tool", "name": "nearby_places"}]
    assert shaper.shape(event) == []


def test_other_events_are_dropped():
    assert EventShaper().shape({"init_event_loop": True}) == []
    assert EventShaper().shape({"data": ""}) == []


def test_final_answer_joins_text_blocks():
    message = {"role": "assistant", "content": [{"text": "A"}, {"toolUse": {}}, {"text": "B "}]}
    assert final_answer(message) == "AB"


def test_done_event_carries_answer_usage_and_model():
    result = SimpleNamespace(
        message={"role": "assistant", "content": [{"text": "愛鷹山です。"}]},
        stop_reason="end_turn",
        metrics=SimpleNamespace(accumulated_usage={"inputTokens": 1200, "outputTokens": 80, "totalTokens": 1280}, cycle_count=2),
    )
    assert done_event(result, "model-a") == {
        "type": "done",
        "answer": "愛鷹山です。",
        "stopReason": "end_turn",
        "usage": {"inputTokens": 1200, "outputTokens": 80, "modelCalls": 2},
        "modelId": "model-a",
    }


def test_error_event_shape():
    assert error_event("agent_failed", "x") == {"type": "error", "code": "agent_failed", "message": "x"}
```

Run: `cd $APP && uv run pytest tests/test_stream.py -v`
Expected: `ModuleNotFoundError: No module named 'stream'`

- [ ] **Step 2: 整形を実装する**

`stream.py`:

```python
"""Shape Strands stream events into the small set of events the Backend consumes."""
from __future__ import annotations

from typing import Any


def final_answer(message: dict) -> str:
    """Text of the last assistant message: the answer after the last tool call, without preface."""
    return "".join(block["text"] for block in message.get("content", []) if isinstance(block.get("text"), str)).strip()


def error_event(code: str, message: str) -> dict:
    return {"type": "error", "code": code, "message": message}


def done_event(result: Any, model_id: str) -> dict:
    usage = result.metrics.accumulated_usage
    return {
        "type": "done",
        "answer": final_answer(result.message),
        "stopReason": str(result.stop_reason),
        "usage": {
            "inputTokens": usage.get("inputTokens", 0),
            "outputTokens": usage.get("outputTokens", 0),
            "modelCalls": result.metrics.cycle_count,
        },
        "modelId": model_id,
    }


class EventShaper:
    """Emit text deltas and one event per tool call; drop Strands bookkeeping events."""

    def __init__(self) -> None:
        self._seen_tool_ids: set[str] = set()

    def shape(self, event: dict) -> list[dict]:
        text = event.get("data")
        if isinstance(text, str) and text:
            return [{"type": "text", "text": text}]
        tool = event.get("current_tool_use")
        if isinstance(tool, dict) and tool.get("toolUseId") and tool["toolUseId"] not in self._seen_tool_ids:
            self._seen_tool_ids.add(tool["toolUseId"])
            return [{"type": "tool", "name": tool.get("name", "")}]
        return []
```

Run: `cd $APP && uv run pytest tests/test_stream.py -v`
Expected: 6 passed。

- [ ] **Step 3: 流れのテストを書く**

`tests/test_handler.py`:

```python
"""Tests for one invocation: payload checks, model id, streaming, history and errors."""
import asyncio
from types import SimpleNamespace

from config import load_settings
from handler import Deps, handle
from history import SessionStore
from model_config import ModelIdError


def user(text):
    return {"role": "user", "content": [{"text": text}]}


def assistant(text):
    return {"role": "assistant", "content": [{"text": text}]}


def make_result(text, usage=None):
    return SimpleNamespace(
        message=assistant(text),
        stop_reason="end_turn",
        metrics=SimpleNamespace(accumulated_usage=usage or {"inputTokens": 10, "outputTokens": 5}, cycle_count=1),
    )


class FakeAgent:
    def __init__(self, messages, events, final_text, raise_after=None):
        self.messages = list(messages)
        self._events = events
        self._final_text = final_text
        self._raise_after = raise_after
        self.calls = []

    async def stream_async(self, prompt, invocation_state=None, limits=None):
        self.calls.append({"prompt": prompt, "invocation_state": invocation_state, "limits": limits})
        self.messages.append(user(prompt))
        for index, event in enumerate(self._events):
            if self._raise_after is not None and index == self._raise_after:
                raise RuntimeError("model failed")
            yield event
        self.messages.append(assistant(self._final_text))
        yield {"result": make_result(self._final_text)}


class FixedModelIds:
    def __init__(self, value=None, error=None):
        self.value, self.error = value, error

    def get(self):
        if self.error:
            raise self.error
        return self.value


def run(payload, deps, session_id="s1"):
    async def collect():
        return [event async for event in handle(payload, session_id, deps)]

    return asyncio.run(collect())


def make_deps(agent=None, model_ids=None, sessions=None):
    created = []

    def factory(model_id, messages):
        created.append((model_id, messages))
        return agent

    deps = Deps(
        settings=load_settings({}),
        model_ids=model_ids or FixedModelIds("model-a"),
        sessions=sessions or SessionStore(),
        agent_factory=factory,
    )
    return deps, created


def test_missing_prompt_is_bad_request():
    deps, created = make_deps()
    assert run({"location": None}, deps) == [{"type": "error", "code": "bad_request", "message": "prompt is required"}]
    assert created == []


def test_model_id_error_is_agent_failed():
    deps, created = make_deps(model_ids=FixedModelIds(error=ModelIdError("failed to read /p: RuntimeError")))
    events = run({"prompt": "Q"}, deps)
    assert events == [{"type": "error", "code": "agent_failed", "message": "failed to read /p: RuntimeError"}]
    assert created == []


def test_normal_flow_streams_and_ends_with_done():
    agent = FakeAgent([], [{"data": "愛鷹"}, {"data": "山です。"}], "愛鷹山です。")
    deps, created = make_deps(agent=agent)
    location = {"latitude": 35.1, "longitude": 138.8, "headingDegrees": 90}
    events = run({"prompt": "右手の山は？", "location": location}, deps)
    assert events[:2] == [{"type": "text", "text": "愛鷹"}, {"type": "text", "text": "山です。"}]
    assert events[-1]["type"] == "done" and events[-1]["answer"] == "愛鷹山です。" and events[-1]["modelId"] == "model-a"
    assert created == [("model-a", [])]
    assert agent.calls[0]["invocation_state"] == {"location": location}
    assert agent.calls[0]["limits"] == {"turns": 8}


def test_answer_excludes_preface_before_tool_call():
    agent = FakeAgent(
        [],
        [{"data": "調べます。"}, {"current_tool_use": {"toolUseId": "t1", "name": "web_search"}}, {"data": "晴れです。"}],
        "晴れです。",
    )
    deps, _ = make_deps(agent=agent)
    events = run({"prompt": "天気は？"}, deps)
    assert {"type": "tool", "name": "web_search"} in events
    assert events[-1]["answer"] == "晴れです。"


def test_history_is_stored_pruned_and_reused():
    sessions = SessionStore()
    sessions.put("s1", [user("Q0"), assistant("A0")])
    agent = FakeAgent([user("Q0"), assistant("A0")], [], "A1")
    deps, created = make_deps(agent=agent, sessions=sessions)
    run({"prompt": "Q1"}, deps)
    assert created[0][1] == [user("Q0"), assistant("A0")]
    assert sessions.get("s1") == [user("Q0"), assistant("A0"), user("Q1"), assistant("A1")]


def test_error_does_not_store_history():
    sessions = SessionStore()
    sessions.put("s1", [user("Q0"), assistant("A0")])
    agent = FakeAgent([user("Q0"), assistant("A0")], [{"data": "x"}, {"data": "y"}], "never", raise_after=1)
    deps, _ = make_deps(agent=agent, sessions=sessions)
    events = run({"prompt": "Q1"}, deps)
    assert events[-1] == {"type": "error", "code": "agent_failed", "message": "RuntimeError"}
    assert sessions.get("s1") == [user("Q0"), assistant("A0")]


def test_empty_answer_is_agent_failed():
    agent = FakeAgent([], [], "   ")
    deps, _ = make_deps(agent=agent)
    assert run({"prompt": "Q"}, deps)[-1] == {"type": "error", "code": "agent_failed", "message": "empty answer"}
```

Run: `cd $APP && uv run pytest tests/test_handler.py -v`
Expected: `ModuleNotFoundError: No module named 'handler'`

- [ ] **Step 4: 流れを実装する**

`handler.py`:

```python
"""One invocation: read the model id, run the agent, stream events, and keep history on success."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from config import Settings
from history import SessionStore, prune_history
from model_config import ModelIdError
from stream import EventShaper, done_event, error_event, final_answer
from tools.places import LOCATION_KEY

log = logging.getLogger("trv2.agent")


@dataclass
class Deps:
    settings: Settings
    model_ids: Any
    sessions: SessionStore
    agent_factory: Callable[[str, list[dict]], Any]


def _prompt(payload: dict) -> str:
    value = payload.get("prompt")
    return value.strip() if isinstance(value, str) else ""


def _log(record: dict) -> None:
    # One JSON line per invocation; never the prompt or the position (personal data).
    log.info(json.dumps(record, ensure_ascii=False))


async def handle(payload: dict, session_id: str, deps: Deps) -> AsyncIterator[dict]:
    prompt = _prompt(payload)
    if not prompt:
        yield error_event("bad_request", "prompt is required")
        return
    try:
        model_id = deps.model_ids.get()
    except ModelIdError as error:
        _log({"event": "invoke_failed", "session": session_id, "reason": str(error)})
        yield error_event("agent_failed", str(error))
        return

    agent = deps.agent_factory(model_id, deps.sessions.get(session_id))
    shaper = EventShaper()
    tools: list[str] = []
    result = None
    try:
        async for event in agent.stream_async(
            prompt,
            invocation_state={LOCATION_KEY: payload.get("location")},
            limits={"turns": deps.settings.max_turns},
        ):
            if "result" in event:
                result = event["result"]
                continue
            for shaped in shaper.shape(event):
                if shaped["type"] == "tool":
                    tools.append(shaped["name"])
                yield shaped
    except Exception as error:  # noqa: BLE001 - reported to the Backend as a failure
        _log({"event": "invoke_failed", "session": session_id, "modelId": model_id, "reason": type(error).__name__})
        yield error_event("agent_failed", type(error).__name__)
        return

    if result is None or not final_answer(result.message):
        _log({"event": "invoke_failed", "session": session_id, "modelId": model_id, "reason": "empty answer"})
        yield error_event("agent_failed", "empty answer")
        return

    deps.sessions.put(session_id, prune_history(agent.messages, deps.settings.max_history_messages))
    done = done_event(result, model_id)
    _log({"event": "invoke_done", "session": session_id, "modelId": model_id, "tools": tools,
          "usage": done["usage"], "stopReason": done["stopReason"]})
    yield done
```

- [ ] **Step 5: テストを通す**

Run: `cd $APP && uv run pytest -v`
Expected: Task 1〜6 のテストがすべて PASS。

- [ ] **Step 6: コミット**

```bash
cd $AGENT
git add app/agentcore_trv2_dev_ask/stream.py app/agentcore_trv2_dev_ask/handler.py app/agentcore_trv2_dev_ask/tests/test_stream.py app/agentcore_trv2_dev_ask/tests/test_handler.py
git commit -m "feat: stream answer events and keep history only on success"
```

---

### Task 7: エントリポイント・Web 検索・プロンプト

**Files:**
- Create: `app/agentcore_trv2_dev_ask/main.py`、`app/agentcore_trv2_dev_ask/prompt.py`、`app/agentcore_trv2_dev_ask/tools/web_search.py`
- Test: `app/agentcore_trv2_dev_ask/tests/test_web_search.py`、`app/agentcore_trv2_dev_ask/tests/test_main.py`

**Interfaces:**
- Consumes: Task 1〜6 のすべて。
- Produces: `main.app`（`BedrockAgentCoreApp`）、`main.build_agent(model_id: str, messages: list[dict]) -> Agent`、`tools.web_search.find_gateway_url(env: Mapping[str, str]) -> str | None`、`tools.web_search.load_web_search() -> MCPClient | None`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_web_search.py`:

```python
"""Tests for finding the gateway url injected by the AgentCore CLI."""
from tools.web_search import find_gateway_url


def test_override_wins():
    env = {"GATEWAY_URL": "https://override", "AGENTCORE_GATEWAY_GWTRV2DEVMAIN_URL": "https://injected"}
    assert find_gateway_url(env) == "https://override"


def test_injected_url_is_found_by_prefix():
    assert find_gateway_url({"AGENTCORE_GATEWAY_GWTRV2DEVMAIN_URL": "https://injected"}) == "https://injected"


def test_no_gateway():
    assert find_gateway_url({"PATH": "/bin"}) is None
```

`tests/test_main.py`:

```python
"""Smoke test that main wires the agent without calling AWS."""
import main


def test_build_agent_wires_model_tools_hooks_and_history():
    history = [{"role": "user", "content": [{"text": "Q"}]}, {"role": "assistant", "content": [{"text": "A"}]}]
    agent = main.build_agent("us.anthropic.claude-sonnet-5-5", history)
    assert agent.model.config["model_id"] == "us.anthropic.claude-sonnet-5-5"
    assert agent.messages == history
    assert {"nearby_places", "find_place"} <= set(agent.tool_names)
    assert "ライダー" in agent.system_prompt
```

Run: `cd $APP && AWS_REGION=us-east-1 uv run pytest tests/test_web_search.py tests/test_main.py -v`
Expected: `ModuleNotFoundError`（`tools.web_search`・`main`）

- [ ] **Step 2: Web 検索のクライアントを書く**

`tools/web_search.py`:

```python
"""Web search through the AgentCore Gateway's managed web-search connector (MCP, IAM-signed)."""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Optional

from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient

_AWS_SERVICE = "bedrock-agentcore"
_PREFIX = "AGENTCORE_GATEWAY_"
_SUFFIX = "_URL"


def find_gateway_url(env: Mapping[str, str] = os.environ) -> Optional[str]:
    """The gateway endpoint: GATEWAY_URL for local runs, else the CLI-injected AGENTCORE_GATEWAY_<NAME>_URL."""
    if env.get("GATEWAY_URL"):
        return env["GATEWAY_URL"]
    for name in sorted(env):
        if name.startswith(_PREFIX) and name.endswith(_SUFFIX):
            return env[name]
    return None


def load_web_search() -> Optional[MCPClient]:
    """An MCP client for the gateway, or None so the agent still answers without search."""
    endpoint = find_gateway_url()
    if not endpoint:
        return None
    region = os.environ.get("GATEWAY_REGION", "us-east-1")
    return MCPClient(lambda: aws_iam_streamablehttp_client(endpoint=endpoint, aws_region=region, aws_service=_AWS_SERVICE))
```

- [ ] **Step 3: システムプロンプトを書く**

`prompt.py`:

```python
"""System prompt. Kept apart from the model id so either can change on its own."""

SYSTEM_PROMPT = """\
あなたはバイクでツーリング中のライダーを支援するAIです。
回答は音声で読み上げられ、ライダーは走行中で画面を見られません。

回答のルール:
- 2〜3文程度で簡潔に答える。前置きや質問の復唱はしない。
- Markdown 記法・記号・URL・箇条書きは使わない。読み上げると不自然になる。
- ツールを呼ぶ前に文章を書かない（「調べます」などの前置きは読み上げられない）。
- 確実でないことは「たぶん」「〜と思われます」と正直に伝える。推測を事実のように言わない。
- 今日の日付と現在時刻は、質問に添えられた現在日時を正とする。
- 直前までの会話を踏まえ、「それ」「さっきの」のような指示語を文脈から解釈する。
- 質問は音声認識の文字起こしなので、誤変換や聞き間違いが混じることがある。
  文脈に合わない語は、読みが同じか似ていて意味の通る語として解釈する。

位置と進行方向:
- 質問に添えられた住所・進行方向・右手と左手の方角は確定した事実なので、そのまま使い、計算し直さない。
- 「いま右手に見える」なら最新の位置を、「さっきの山」ならその話題が出たときの位置を使う。
- 進行方向が無いときは、方角や左右に触れずに位置だけで答える。

調べ方:
- ライダーはスマホを操作できない。「アプリで確認してください」「検索してみてください」とは答えず、自分で調べる。
- 天気・道路状況・営業時間・イベントなど、その日その時の情報は web 検索で調べる。
- 山や地域の由来のように変わらない知識は、調べずに答える。
- web 検索では、添えられた住所から都道府県名と市町村名を補って具体的に検索する。
- 調べても分からなければ、分からないと短く答える。

周辺の場所:
- 「右手に見える公園」「一番近いコンビニ」のような周辺の場所は、nearby_places（種類で探す）か
  find_place（名前で探す）を使う。現在地は自動で渡されるので、座標は書かない。
- 特定の場所の方角や距離を聞かれたら、有名な場所でも find_place で調べる。
- ツールが返す距離・方角・左右は計算済みの事実なので、そのまま使う。
- 候補が複数あれば一番近いものを答え、地図のずれがありうるので断定しすぎない。
"""
```

- [ ] **Step 4: エントリポイントを書く**

`main.py`:

```python
"""AgentCore entrypoint for the touring agent. Wiring only; the logic lives in handler.py."""
from __future__ import annotations

import logging

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.agent.conversation_manager import NullConversationManager
from strands.models.bedrock import BedrockModel

from config import load_settings
from handler import Deps, handle
from history import SessionStore
from hooks import ToolCallLimit, ToolResultTrimmer
from model_config import ModelIdSource
from prompt import SYSTEM_PROMPT
from tools.places import find_place, nearby_places
from tools.web_search import load_web_search

logging.getLogger("trv2.agent").setLevel(logging.INFO)

app = BedrockAgentCoreApp()
SETTINGS = load_settings()
WEB_SEARCH = load_web_search()
if WEB_SEARCH is None:
    app.logger.warning("no gateway url in env - answering without web search")


def build_agent(model_id: str, messages: list[dict]) -> Agent:
    """A fresh agent per question: the model id may change, and the hooks count per question."""
    return Agent(
        model=BedrockModel(model_id=model_id, region_name=SETTINGS.region, max_tokens=SETTINGS.max_tokens),
        messages=messages,
        system_prompt=SYSTEM_PROMPT,
        tools=[nearby_places, find_place] + ([WEB_SEARCH] if WEB_SEARCH else []),
        hooks=[ToolCallLimit(SETTINGS.max_tool_calls), ToolResultTrimmer(SETTINGS.max_tool_result_chars)],
        # History is pruned by handler.py after each successful turn.
        conversation_manager=NullConversationManager(),
        callback_handler=None,
    )


DEPS = Deps(
    settings=SETTINGS,
    model_ids=ModelIdSource(
        SETTINGS.model_id_parameter,
        boto3.client("ssm", region_name=SETTINGS.region),
        SETTINGS.model_cache_seconds,
    ),
    sessions=SessionStore(),
    agent_factory=build_agent,
)


@app.entrypoint
async def invoke(payload: dict, context):
    # runtimeSessionId is the conversation id; the same id continues the conversation.
    session_id = getattr(context, "session_id", None) or "default-session"
    async for event in handle(payload, session_id, DEPS):
        yield event


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 5: テストを通す**

Run: `cd $APP && AWS_REGION=us-east-1 uv run pytest -v`
Expected: すべて PASS。`agent.model.config` や `agent.tool_names` の名前が違って失敗したら、`uv run python -c "import main; a=main.build_agent('m', []); print(type(a.model).__name__, a.model.get_config(), a.tool_names)"` で実際の属性を確かめてテストを合わせる（合わせた内容は ledger に記録）。

- [ ] **Step 6: 手元で起動して1問だけ通す（本物の Bedrock を使う）**

```bash
cd $APP
aws ssm get-parameter --name /trv2/dev/agent-model-id --region us-east-1 --profile touring >/dev/null 2>&1 || echo "parameter not yet created (Task 8 creates it)"
eval "$(aws configure export-credentials --profile touring --format env)"
AWS_REGION=us-east-1 uv run python -c "
import asyncio, main
from types import SimpleNamespace
from model_config import ModelIdSource
class Fixed:
    def get(self): return 'us.anthropic.claude-sonnet-5-5'
main.DEPS.model_ids = Fixed()
async def go():
    async for e in main.invoke({'prompt': '現在日時: 2026-10-16 12:00\n質問: 富士山の高さは？'}, SimpleNamespace(session_id='local-test-session-0000000000000001')):
        if e['type'] != 'text': print(e)
asyncio.run(go())
"
```
Expected: 最後に `{'type': 'done', 'answer': '...3776...', ...}`。Markdown の記号が無い。`AccessDeniedException` ならモデルの利用が有効になっているかを利用者に確かめる。

- [ ] **Step 7: コミット**

```bash
cd $AGENT
git add app/agentcore_trv2_dev_ask/main.py app/agentcore_trv2_dev_ask/prompt.py app/agentcore_trv2_dev_ask/tools/web_search.py app/agentcore_trv2_dev_ask/tests/test_web_search.py app/agentcore_trv2_dev_ask/tests/test_main.py
git commit -m "feat: wire agentcore entrypoint with web search and system prompt"
```

---

### Task 8: デプロイと通しの確認

**Files:**
- Create: `Agent/scripts/smoke.py`、`Agent/agentcore/aws-targets.json`（追跡しない）

**Interfaces:**
- Consumes: Task 1〜7 のプロジェクト一式。
- Produces: デプロイ済みの Runtime `trv2Agent_agentcore_trv2_dev_ask`、SSM `/trv2/dev/agent-model-id`（us-east-1）、SSM `/trv2/dev/agent-runtime-arn`（ap-northeast-1）。計画3（Backend）はこの ARN と、上の「Backend との約束」を使う。

- [ ] **Step 1: 名前の衝突が無いことを確かめる**

```bash
export AWS_PROFILE=touring
aws cloudformation describe-stacks --region us-east-1 --stack-name AgentCore-trv2Agent-default 2>&1 | tail -1
aws ssm get-parameter --region us-east-1 --name /trv2/dev/agent-model-id 2>&1 | tail -1
aws ssm get-parameter --region ap-northeast-1 --name /trv2/dev/agent-runtime-arn 2>&1 | tail -1
aws bedrock-agentcore-control list-agent-runtimes --region us-east-1 --query "agentRuntimes[?agentRuntimeName=='trv2Agent_agentcore_trv2_dev_ask'].agentRuntimeArn" --output text
```
Expected: スタックと設定値は `does not exist` / `ParameterNotFound`、ランタイムは空。

- [ ] **Step 2: モデルの設定値とデプロイ先を用意する**

```bash
aws ssm put-parameter --region us-east-1 --name /trv2/dev/agent-model-id --type String --value us.anthropic.claude-sonnet-5-5
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
sed "s/<ACCOUNT_ID>/$ACCOUNT/" $AGENT/agentcore/aws-targets-sample.json > $AGENT/agentcore/aws-targets.json
cd $AGENT && git status --short | grep -c aws-targets.json || true
```
Expected: `Version: 1`。最後の行が `0`（追跡されない）。

- [ ] **Step 3: デプロイする**

```bash
cd $AGENT
AWS_REGION=us-east-1 npx -y @aws/agentcore@0.31.1 deploy -y 2>&1 | tee /tmp/trv2-agent-deploy.log | tail -20
```
Expected: 成功の表示。失敗したら、ログのエラーを調べてから直す（同じコマンドを繰り返さない）。

- [ ] **Step 4: 作られたものを確かめる**

```bash
ARN=$(aws bedrock-agentcore-control list-agent-runtimes --region us-east-1 --query "agentRuntimes[?agentRuntimeName=='trv2Agent_agentcore_trv2_dev_ask'].agentRuntimeArn" --output text)
RID=${ARN##*/}
aws bedrock-agentcore-control get-agent-runtime --region us-east-1 --agent-runtime-id "$RID" \
  --query '{idle: lifecycleConfiguration.idleRuntimeSessionTimeout, env: environmentVariables, role: roleArn}'
ROLE=$(aws bedrock-agentcore-control get-agent-runtime --region us-east-1 --agent-runtime-id "$RID" --query roleArn --output text)
for p in $(aws iam list-role-policies --role-name "${ROLE##*/}" --query 'PolicyNames' --output text); do
  aws iam get-role-policy --role-name "${ROLE##*/}" --policy-name "$p" --query 'PolicyDocument.Statement[].Action' --output text
done | tr '\t' '\n' | grep -E "geo-places|ssm:GetParameter|InvokeGateway" | sort -u
```
Expected: `idle` が `3600`、`env` に `MODEL_ID_PARAMETER` と `AGENTCORE_GATEWAY_..._URL`、権限に `geo-places:SearchNearby`・`geo-places:SearchText`・`ssm:GetParameter`・`bedrock-agentcore:InvokeGateway`。

- [ ] **Step 5: 通しの確認のスクリプトを書く**

`Agent/scripts/smoke.py`:

```python
"""Invoke the deployed runtime with fixed questions and check the event stream.

Usage: AWS_PROFILE=touring python3 scripts/smoke.py <runtime-arn>
Positions are public landmarks only.
"""
from __future__ import annotations

import json
import re
import sys
import uuid

import boto3

TOKYO_STATION = {"latitude": 35.6812, "longitude": 139.7671, "headingDegrees": 0.0}
FACTS = "現在日時: 2026-10-16 12:00（日本時間）\n現在地: 東京都千代田区丸の内（緯度35.6812 経度139.7671）\n進行方位: 北（右手は東、左手は西）\n"
MARKDOWN = re.compile(r"[*#`]|^\s*[-・]\s", re.MULTILINE)


def invoke(client, arn: str, session_id: str, question: str, location: dict | None) -> list[dict]:
    payload = {"prompt": FACTS + "質問: " + question, "location": location}
    response = client.invoke_agent_runtime(
        agentRuntimeArn=arn, runtimeSessionId=session_id, qualifier="DEFAULT", payload=json.dumps(payload).encode()
    )
    events = []
    for raw in response["response"].iter_lines():
        line = raw.decode("utf-8").strip()
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def check(name: str, events: list[dict], expect_tool: str | None) -> bool:
    done = next((e for e in events if e.get("type") == "done"), None)
    tools = [e["name"] for e in events if e.get("type") == "tool"]
    errors = [e for e in events if e.get("type") == "error"]
    ok = done is not None and not errors and bool(done["answer"]) and not MARKDOWN.search(done["answer"])
    if expect_tool is not None:
        ok = ok and any(expect_tool in tool for tool in tools)
    print(f"[{'OK' if ok else 'NG'}] {name}: tools={tools} usage={done and done['usage']} model={done and done['modelId']}")
    print(f"      answer={done and done['answer']} errors={errors}")
    return ok


def main() -> int:
    arn = sys.argv[1]
    client = boto3.client("bedrock-agentcore", region_name="us-east-1")
    session = f"smoke-{uuid.uuid4()}"
    results = [
        check("知識だけで答える", invoke(client, arn, session, "富士山の高さは？", TOKYO_STATION), None),
        check("周辺検索", invoke(client, arn, session, "近くのコンビニはどこ？", TOKYO_STATION), "nearby_places"),
        check("Web 検索", invoke(client, arn, session, "今日の東京の天気は？", TOKYO_STATION), "earch"),
        check("会話の続き", invoke(client, arn, session, "さっきのコンビニまでの距離をもう一度教えて", TOKYO_STATION), None),
        check("現在地なし", invoke(client, arn, f"smoke-{uuid.uuid4()}", "右手に見える公園は？", None), None),
    ]
    print(f"{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: 通しを確かめる**

```bash
cd $AGENT && AWS_PROFILE=touring uv run --project app/agentcore_trv2_dev_ask python scripts/smoke.py "$ARN"
```
Expected: `5/5 passed`。「会話の続き」の答えが、前の質問のコンビニに触れている（目で確かめる）。NG があれば、CloudWatch のログ（`/aws/bedrock-agentcore/runtimes/trv2Agent_agentcore_trv2_dev_ask-*`）の `invoke_failed` を調べてから直す。

- [ ] **Step 7: モデルを切り替えても通ることを確かめる**

```bash
aws ssm put-parameter --region us-east-1 --name /trv2/dev/agent-model-id --type String --overwrite --value us.anthropic.claude-haiku-5-5
sleep 65
cd $AGENT && AWS_PROFILE=touring uv run --project app/agentcore_trv2_dev_ask python scripts/smoke.py "$ARN" | grep -E "model=|passed"
aws ssm put-parameter --region us-east-1 --name /trv2/dev/agent-model-id --type String --overwrite --value us.anthropic.claude-sonnet-5-5
```
Expected: `model=us.anthropic.claude-haiku-5-5` が出て通る（デプロイなしで切り替わる）。最後に Sonnet に戻す。

- [ ] **Step 8: Runtime の ARN を東京の設定値に書く（UC-3）**

```bash
aws ssm put-parameter --region ap-northeast-1 --name /trv2/dev/agent-runtime-arn --type String --value "$ARN"
```
Expected: `Version: 1`。

- [ ] **Step 9: コミット**

```bash
cd $AGENT
git add scripts/smoke.py
git status --short
git commit -m "test: add smoke check for the deployed runtime"
```
`git status --short` に `aws-targets.json`・`.cli/` が出ないこと。

---

### Task 9: 文書と契約

**Files:**
- Modify: `Agent/README.md`
- Modify（親）: `docs/07_units_contracts.md`（UC-8）、`docs/specs/2026-10-16-slice1-design.md`（§6.2）
- Modify（親）: `Agent` の submodule の指す先、各ユニットの `docs-parent/`

**Interfaces:**
- Produces: 計画3（Backend）が読む契約（UC-8 の呼び出しの本文と応答のイベント）。

- [ ] **Step 1: `Agent/README.md` を書き直す**

```markdown
# TouringProjectV2_Agent

TouringProjectV2 のエージェント（Bedrock AgentCore Runtime＋Strands・`us-east-1`）。
Backend から質問（プロンプトと数値の現在地）を受け、Web 検索と周辺検索を使って、読み上げ向けの回答を返す。
プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し。編集しない）。

## 構成

| 場所 | 中身 |
|---|---|
| `agentcore/agentcore.json` | Runtime（`agentcore_trv2_dev_ask`）と Gateway（`gwTrv2DevMain`・Web 検索のコネクタ）。環境変数とアイドルの時間切れ（3600秒） |
| `agentcore/cdk/` | CLI が生成した CDK。`lib/cdk-stack.ts` で Runtime に Location と SSM の権限を足している（生成し直したら足し直す） |
| `app/agentcore_trv2_dev_ask/` | エージェント本体。`main.py`（組み立て）・`handler.py`（1回の呼び出しの流れ）・`history.py`・`hooks.py`・`stream.py`・`model_config.py`・`tools/` |
| `scripts/smoke.py` | デプロイ後に決まった質問を投げて確かめる |

## 振る舞い

- 会話の文脈は `runtimeSessionId`（Backend が渡す会話の識別子）ごとに、Runtime のプロセスの中に持つ。回答のあと、ツールの呼び出しと結果を取り除き、質問と回答の文だけを直近10メッセージまで残す。
- モデル ID は SSM `/trv2/dev/agent-model-id`（us-east-1）から読む（60秒キャッシュ）。読めないときは失敗を返す。
- ツールは1回の質問につき4回まで。ツールの結果は合計3000文字までに切り詰める。
- 応答は SSE で `text`・`tool`・`done`・`error` のイベントを返す（親の `docs/07_units_contracts.md` UC-8）。

## テスト

```sh
cd app/agentcore_trv2_dev_ask && uv run pytest
```

## デプロイ

前提: `agentcore/aws-targets-sample.json` のアカウント ID を埋めて `agentcore/aws-targets.json` に置く（追跡しない）。

```sh
AWS_PROFILE=touring AWS_REGION=us-east-1 npx -y @aws/agentcore@0.31.1 deploy -y
ARN=$(AWS_PROFILE=touring aws bedrock-agentcore-control list-agent-runtimes --region us-east-1 \
  --query "agentRuntimes[?agentRuntimeName=='trv2Agent_agentcore_trv2_dev_ask'].agentRuntimeArn" --output text)
AWS_PROFILE=touring uv run --project app/agentcore_trv2_dev_ask python scripts/smoke.py "$ARN"
AWS_PROFILE=touring aws ssm put-parameter --region ap-northeast-1 --name /trv2/dev/agent-runtime-arn --type String --overwrite --value "$ARN"
```

ARN が変わったら Backend もデプロイし直す。

## モデルの切り替え

```sh
AWS_PROFILE=touring aws ssm put-parameter --region us-east-1 --name /trv2/dev/agent-model-id --type String --overwrite --value <推論プロファイルの ID>
```

60秒以内に反映される。切り替えたら `scripts/smoke.py` で通ることを確かめる。
```

コミット:

```bash
cd $AGENT && git add README.md && git commit -m "docs: describe agent structure, behavior and deployment"
```

- [ ] **Step 2: 親の 07（UC-8）を直す**

親で `main` から `slice1-plan2` を切ってから、`docs/07_units_contracts.md` を Edit する。

- 旧: `- AI への入力（プロンプト）は Backend が組み、Agent はそのまま AI に渡す。入力には次の確定した事実を添える。`
  新: `- 呼び出しの本文は JSON の `{"prompt": <文字列>, "location": {"latitude": <数値>, "longitude": <数値>, "headingDegrees": <数値または null>} または null}`。AI への入力（プロンプト）は Backend が組み、Agent はそのまま AI に渡す。入力には次の確定した事実を添える。`
- 旧:
  ```
  - Agent は回答を順に返し、最後に使ったトークン数（入力・出力・モデルの呼び出し回数）を返す。Backend はそれをつないで回答の文にし、トークン数を記録に残す。
  - ツールを呼ぶ前の前置きは回答に含めない（読み上げないため）。Backend は最後のツール呼び出しより後ろだけを回答にする。
  - Agent が受け付けられないときは、失敗であることが分かる形で返す。
  ```
  新:
  ```
  - Agent は SSE（各行 `data: <JSON>`）でイベントを返す。`type` は `text`（回答の断片。前置きを含む）・`tool`（ツールの呼び出しの開始と名前）・`done`・`error` の4つ。
  - `done` は最後に1回だけ来る。`answer` は最後のツール呼び出しより後ろの回答だけ（前置きは Agent が除く）。`usage` に入力・出力のトークン数とモデルの呼び出し回数、`modelId` に使ったモデルを入れる。Backend は `answer` を読み上げに使い、`usage` と `modelId` を記録に残す。
  - 失敗のときは `done` の代わりに `error` が来る。`code` は `bad_request`（本文が不正）か `agent_failed`（モデル ID が読めない・モデルの失敗・回答が空）。Backend は `agent_failed` として扱う。
  ```

- [ ] **Step 3: 仕様書 §6.2 を直す**

`docs/specs/2026-10-16-slice1-design.md` を Edit する。

- 旧: `  A --> P["前置きを除く<br/>Polly（SSML で音量を上げる）"]`
  新: `  A --> P["done の回答を<br/>Polly（SSML で音量を上げる）"]`
- 旧: `- 前置きの除去: Agent が流すツールの呼び出しの区切りを見て、最後のツール呼び出しより後ろだけを回答の文にする。`
  新: `- 回答の文: Agent の `done` イベントの `answer` を使う（前置きは Agent が除く。07 UC-8）。`

- [ ] **Step 4: 検査して写し、submodule を進める**

```bash
cd <親リポジトリ>
python3 scripts/check_links.py docs adr README.md
git diff --exit-code HEAD -- docs/init && echo "docs/init unchanged"
tests/test_sync_docs.sh
scripts/sync-docs.sh App Backend Agent CICD
for u in App Backend CICD; do git -C "$u" add docs-parent && git -C "$u" commit -m "docs: sync parent docs" || true; done
git -C Agent add docs-parent && git -C Agent commit -m "docs: sync parent docs" || true
git add docs/07_units_contracts.md docs/specs/2026-10-16-slice1-design.md Agent App Backend CICD
git commit -m "docs: define agent invocation payload and response events"
```
Expected: リンクの切れ 0件、`docs/init unchanged`、`OK: sync-docs`。親のコミットに `Agent` の指す先（`slice1-plan2` の先頭）が入る。push はしない。
