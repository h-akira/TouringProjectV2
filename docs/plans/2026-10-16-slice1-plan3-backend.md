# スライス1 計画3: Backend 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App から質問（PCM の音声か文字）と位置を受け付け、ストリーミングの文字起こし → 住所・方位・日時の確定 → Agent → Polly を1本の worker で処理し、App が回答と読み上げ音声をポーリングで受け取れる API を、東京にデプロイして通しを確かめる。

**Architecture:** API Gateway（REST・API キーと使用量プラン）の後ろに、受け付け（`POST /asks`）・結果（`GET /asks/{askId}`）・健康確認の Lambda を置き、受け付けは SQS 経由で worker を起こす。記録は DynamoDB の1つのテーブル、音声は S3（1日で消える）。AWS に触れる部分は `lib/` の小さなモジュールに分け、worker の段は差し替えられる関数として渡すので、moto とスタブで単体テストできる。

**Tech Stack:** Python 3.13（Lambda arm64）・AWS SAM・pytest・moto 5・amazon-transcribe 0.6.4・boto3、Amazon Transcribe（ストリーミング）・Location Service（geo-places）・Polly（ニューラル・SSML）・Bedrock AgentCore（us-east-1）・DynamoDB・SQS・S3・SSM。

**Spec:** [docs/specs/2026-10-16-slice1-design.md](../specs/2026-10-16-slice1-design.md)（§4・§6・§8・§9）、契約 [docs/07_units_contracts.md](../07_units_contracts.md)（UC-3〜UC-5・UC-8）、[adr/0002](../../adr/0002-streaming-transcription.md)・[adr/0003](../../adr/0003-conversation-context.md)

## Global Constraints

- 作業するリポジトリは `Backend/`（`TouringProjectV2_Backend`）。親の文書を直すのは Task 15 だけ。どちらも `main` から作業ブランチ `slice1-plan3` を切る。push はしない。
- リージョンは `ap-northeast-1`。Agent は `us-east-1`（呼ぶときにリージョンを明示する）。Agent の ARN は SSM `/trv2/dev/agent-runtime-arn`（東京）から CloudFormation が読む。
- 名前: スタック `stack-trv2-dev-backend`、API `apigw-trv2-dev-main`、Lambda `lambda-trv2-dev-{health,ask,result,worker}`、SQS `sqs-trv2-dev-ask`（DLQ `sqs-trv2-dev-ask-dlq`）、DynamoDB `dynamodb-trv2-dev-records`、S3 `s3-trv2-dev-audio-<アカウントID>`、API キー `apikey-trv2-dev-main`、使用量プラン `usageplan-trv2-dev-main`、設定値 `/trv2/dev/conversation-reset-minutes`（既定15、55を超えたら55に丸める）。
- 録音は PCM（16kHz・モノラル・16bit リトルエンディアン）を base64 で送る。0.25〜60秒。文字の質問は500字まで。
- ユーザー名はヘッダ `x-user-name`。英小文字と数字の3〜20文字。
- 失敗の理由は `no_speech`・`transcribe_failed`・`agent_failed`・`tts_failed`。`tts_failed` でも回答の文は記録して返す。
- worker の Timeout 120秒、SQS の可視性タイムアウト 180秒。受け持ちの獲得は条件付き書き込み。
- 回答の音声は Polly のニューラル音声 Kazuha。SSML で DRC（`amazon:effect name="drc"`）と `prosody volume="+6dB"` をかける。
- ログは1行の JSON。質問の本文・回答・位置・住所はログに出さない。
- コミットする文書・コードに、アカウント ID・API キーの値・ARN・実際の位置（試験に使う公共のランドマーク以外）を書かない。
- Python の外部ライブラリは `Backend/env`（`python -m venv env`）に入れる。コメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。
- 以下 `BE=<親リポジトリの絶対パス>/Backend`。テストは `cd $BE && env/bin/pytest`。

## Review Focus

- 同じ SQS のメッセージが2回届く（可視性タイムアウト切れの再配信）→ 2回目は何もしない（Agent と Polly を2回呼ばない）。Task 12 の `test_second_delivery_does_nothing`。
- 録音が奇数バイト・短すぎる・60秒を超える・base64 でない → 400 で、S3 にも DynamoDB にも何も残らない。Task 2 の `test_audio_*` と Task 10 の `test_bad_request_leaves_nothing`。
- 方位の材料が古い（2分より前）・ほとんど動いていない・未来の時刻 → 方位なしとして扱い、プロンプトは「進行方向: 不明」になる。Task 3 の `test_heading_*`。
- 別のユーザー名で他人の `askId` を取りに行く → 404（存在を明かさない）。Task 11 の `test_other_user_gets_404`。
- 文字起こしの途中で例外 → `transcribe_failed` になり、S3 の録音は消える。Task 12 の `test_transcribe_failure_deletes_audio`。

---

## ファイル構成

| パス（`Backend/` から） | 役割 |
|---|---|
| `template.yaml`・`samconfig.toml` | SAM（Task 13） |
| `openapi.yaml` | API 仕様（正本。Task 13） |
| `requirements-dev.txt`・`pytest.ini` | テストの依存と設定 |
| `src/requirements.txt` | Lambda の依存（amazon-transcribe） |
| `src/lib/clients.py` | AWS クライアント（遅延生成・テスト用の破棄） |
| `src/lib/request.py` | 入力の検証 |
| `src/lib/geo.py` | 距離・方位・16方位 |
| `src/lib/prompt.py` | 日時・方位の文と、Agent へのプロンプト |
| `src/lib/address.py` | 座標から住所（町名まで） |
| `src/lib/store.py` | DynamoDB の読み書き |
| `src/lib/conversation.py` | 会話を区切る時間（SSM） |
| `src/lib/agent.py` | Agent の呼び出しと SSE の解釈 |
| `src/lib/speech.py` | Polly（SSML）と S3 への保存 |
| `src/lib/transcribe.py` | ストリーミングの文字起こし |
| `src/handlers/common.py` | 応答・時刻の共通処理 |
| `src/handlers/{health,ask,result,worker}.py` | Lambda の入口 |
| `tests/` | 単体テスト（`conftest.py` に moto の準備） |
| `tests/fixtures/question_16k.pcm` | 合成音声の質問（通しの確認用） |
| `scripts/smoke.py` | デプロイ後の通しの確認 |

## App との約束（Task 13 の OpenAPI と Task 15 の 07 に書く）

`POST /asks`（ヘッダ `x-api-key`・`x-user-name`）

```json
{"audio": "<base64 の PCM>", "location": {"latitude": 35.6812, "longitude": 139.7671},
 "headingSample": {"latitude": 35.6807, "longitude": 139.7671, "at": "2026-10-16T03:00:00Z"},
 "conversationId": "<続けるときだけ。小文字の UUID>"}
```

`audio` の代わりに `text`（500字まで）でもよい（どちらか一方）。`location`・`headingSample` は無ければ省くか `null`。応答は 202:

```json
{"askId": "<UUID>", "conversationId": "<UUID>", "conversationExpiresAt": "2026-10-16T03:15:00.000Z"}
```

`GET /asks/{askId}`（ヘッダ `x-api-key`・`x-user-name`）は 200:

```json
{"askId": "<UUID>", "status": "processing | completed | failed", "transcript": "…", "answer": "…",
 "audio": [{"seq": 1, "url": "<署名付き URL。10分有効>"}], "error": "no_speech | transcribe_failed | agent_failed | tts_failed | null",
 "timings": {"receivedAt": "…", "transcribedAt": "…", "factsAt": "…", "agentFirstEventAt": "…", "agentDoneAt": "…", "synthesizedAt": "…"}}
```

入力が不正なら 400 `{"error": "bad_request", "message": "…"}`、無ければ 404 `{"error": "not_found"}`。

---

### Task 1: 土台・共通部品・健康確認

**Files:**
- Create: `requirements-dev.txt`、`pytest.ini`、`src/requirements.txt`、`src/lib/__init__.py`（空）、`src/handlers/__init__.py`（空）、`src/lib/clients.py`、`src/handlers/common.py`、`src/handlers/health.py`、`tests/conftest.py`
- Modify: `.gitignore`
- Test: `tests/test_common.py`

**Interfaces:**
- Produces: `lib.clients`（`table()`・`s3()`・`sqs()`・`ssm()`・`polly()`・`geo()`・`agentcore()`・`reset()`）、`handlers.common`（`utc_now() -> datetime`、`iso(dt: datetime) -> str`（UTC・ミリ秒・末尾 `Z`）、`parse_iso(text: str) -> datetime`、`response(status: int, body: dict) -> dict`、`log(record: dict) -> None`）、`tests/conftest.py` の fixture `aws`（moto の中でテーブル・バケット・キュー・設定値を作り、`SimpleNamespace(table, s3, sqs, queue_url, bucket)` を返す）。

- [ ] **Step 1: 作業ブランチと仮想環境**

```bash
cd $BE && git switch -c slice1-plan3
python3 -m venv env
```

`requirements-dev.txt`:

```
boto3>=1.43
amazon-transcribe==0.6.4
moto[dynamodb,s3,sqs,ssm]>=5.1
pytest>=8.0
openapi-spec-validator>=0.7
```

`src/requirements.txt`:

```
amazon-transcribe==0.6.4
```

`pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = src
```

`.gitignore` の末尾に足す:

```

# SAM
samconfig.local.toml
```

```bash
env/bin/pip install -q -r requirements-dev.txt
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/conftest.py`:

```python
"""Shared fixtures: fake credentials and moto-backed AWS resources."""
import os
from types import SimpleNamespace

import boto3
import pytest

os.environ.pop("AWS_PROFILE", None)
os.environ.update({
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "AWS_DEFAULT_REGION": "ap-northeast-1",
    "AWS_REGION": "ap-northeast-1",
    "TABLE_NAME": "test-records",
    "AUDIO_BUCKET": "test-audio",
    "CONVERSATION_RESET_PARAMETER": "/trv2/test/conversation-reset-minutes",
    "AGENT_ARN": "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/test",
})

REGION = "ap-northeast-1"


@pytest.fixture
def aws(monkeypatch):
    from moto import mock_aws

    from lib import clients, conversation

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        table = dynamodb.create_table(
            TableName="test-records",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket="test-audio", CreateBucketConfiguration={"LocationConstraint": REGION})
        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName="test-ask")["QueueUrl"]
        monkeypatch.setenv("QUEUE_URL", queue_url)
        boto3.client("ssm", region_name=REGION).put_parameter(
            Name="/trv2/test/conversation-reset-minutes", Value="15", Type="String"
        )
        clients.reset()
        conversation.reset_cache()
        yield SimpleNamespace(table=table, s3=s3, sqs=sqs, queue_url=queue_url, bucket="test-audio")
        clients.reset()
        conversation.reset_cache()
```

`tests/test_common.py`:

```python
"""Tests for the shared handler helpers and the health check."""
import json
from datetime import datetime, timezone

from handlers import common, health


def test_iso_is_utc_with_millis_and_z():
    dt = datetime(2026, 10, 16, 12, 0, 1, 234567, tzinfo=timezone.utc)
    assert common.iso(dt) == "2026-10-16T12:00:01.234Z"


def test_parse_iso_round_trips_and_accepts_offsets():
    assert common.parse_iso("2026-10-16T12:00:01.234Z") == datetime(2026, 10, 16, 12, 0, 1, 234000, tzinfo=timezone.utc)
    assert common.parse_iso("2026-10-16T21:00:00+09:00") == datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def test_response_is_json_utf8():
    result = common.response(400, {"message": "日本語"})
    assert result["statusCode"] == 400
    assert result["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(result["body"]) == {"message": "日本語"}
    assert "日本語" in result["body"]


def test_health():
    result = health.handler({}, None)
    assert result["statusCode"] == 200
    assert json.loads(result["body"]) == {"status": "ok"}
```

Run: `cd $BE && env/bin/pytest tests/test_common.py -q`
Expected: `ModuleNotFoundError: No module named 'handlers'`

- [ ] **Step 3: 実装する**

`src/lib/__init__.py` と `src/handlers/__init__.py` は空のファイル。

`src/lib/clients.py`:

```python
"""AWS clients, created lazily and cached per container; reset() is for tests."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config


def _region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-northeast-1"


@lru_cache(maxsize=None)
def table() -> Any:
    return boto3.resource("dynamodb", region_name=_region()).Table(os.environ["TABLE_NAME"])


@lru_cache(maxsize=None)
def s3() -> Any:
    # Regional virtual-hosted endpoint, so presigned URLs work without a redirect.
    return boto3.client("s3", region_name=_region(), config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))


@lru_cache(maxsize=None)
def sqs() -> Any:
    return boto3.client("sqs", region_name=_region())


@lru_cache(maxsize=None)
def ssm() -> Any:
    return boto3.client("ssm", region_name=_region())


@lru_cache(maxsize=None)
def polly() -> Any:
    return boto3.client("polly", region_name=_region())


@lru_cache(maxsize=None)
def geo() -> Any:
    return boto3.client("geo-places", region_name=os.environ.get("GEO_REGION", _region()))


@lru_cache(maxsize=None)
def agentcore() -> Any:
    # The agent lives in another region; its stream can take a while, so allow a long read.
    return boto3.client(
        "bedrock-agentcore",
        region_name=os.environ.get("AGENT_REGION", "us-east-1"),
        config=Config(read_timeout=110, retries={"max_attempts": 1}),
    )


def reset() -> None:
    for factory in (table, s3, sqs, ssm, polly, geo, agentcore):
        factory.cache_clear()
```

`src/handlers/common.py`:

```python
"""Helpers shared by the Lambda handlers."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

_log = logging.getLogger("trv2.backend")
_log.setLevel(logging.INFO)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """UTC, millisecond precision, trailing Z."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.astimezone(timezone.utc).microsecond // 1000:03d}Z"


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def log(record: dict) -> None:
    # One JSON line per event. Callers must not pass question text, answers or positions.
    print(json.dumps(record, ensure_ascii=False))
```

`src/handlers/health.py`:

```python
"""GET /health: liveness check without an API key."""
from handlers.common import response


def handler(event, context):
    return response(200, {"status": "ok"})
```

- [ ] **Step 4: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_common.py -q`
Expected: 4 passed。

- [ ] **Step 5: コミット**

```bash
cd $BE
git add .gitignore requirements-dev.txt pytest.ini src/requirements.txt src/lib/__init__.py src/handlers/__init__.py src/lib/clients.py src/handlers/common.py src/handlers/health.py tests/conftest.py tests/test_common.py
git commit -m "feat: add backend scaffold, shared helpers and health check"
```

`tests/conftest.py` は `lib.conversation` を読み込むので、Task 6 までは fixture `aws` を使うテストを書かない。

---

### Task 2: 入力の検証

**Files:**
- Create: `src/lib/request.py`
- Test: `tests/test_request.py`

**Interfaces:**
- Produces: `lib.request.BadRequest(ValueError)`、`AskInput`（frozen dataclass: `audio: bytes | None`・`text: str | None`・`location: dict | None`・`heading_sample: dict | None`・`conversation_id: str | None`）、`user_name(event: dict) -> str`、`parse_ask(event: dict) -> AskInput`、`UUID_RE`、`MAX_AUDIO_BYTES`、`MIN_AUDIO_BYTES`。`location` は `{"latitude", "longitude"}`、`heading_sample` は `{"latitude", "longitude", "at"}`（`at` は UTC の ISO 文字列）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_request.py`:

```python
"""Tests for request validation."""
import base64
import json

import pytest

from lib.request import MAX_AUDIO_BYTES, MIN_AUDIO_BYTES, BadRequest, parse_ask, user_name

CID = "0b8e7c1e-3f1a-4f5e-9a51-2a0b2c6f7d10"


def event(body=None, headers=None, raw=None):
    return {"headers": headers if headers is not None else {"x-user-name": "rider01"}, "body": raw if raw is not None else json.dumps(body)}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.mark.parametrize("name", ["abc", "rider01", "a" * 20])
def test_user_name_ok(name):
    assert user_name(event({}, {"X-User-Name": name})) == name


@pytest.mark.parametrize("name", [None, "ab", "a" * 21, "Rider", "rider_01", "ライダー"])
def test_user_name_bad(name):
    headers = {} if name is None else {"x-user-name": name}
    with pytest.raises(BadRequest):
        user_name(event({}, headers))


def test_text_question():
    ask = parse_ask(event({"text": "  富士山の高さは？ "}))
    assert ask.text == "富士山の高さは？" and ask.audio is None and ask.conversation_id is None


def test_audio_question_with_location_and_sample():
    audio = b"\x01\x00" * (MIN_AUDIO_BYTES // 2)
    ask = parse_ask(event({
        "audio": b64(audio),
        "location": {"latitude": 35.6812, "longitude": 139.7671},
        "headingSample": {"latitude": 35.6807, "longitude": 139.7671, "at": "2026-10-16T12:00:00+09:00"},
        "conversationId": CID,
    }))
    assert ask.audio == audio
    assert ask.location == {"latitude": 35.6812, "longitude": 139.7671}
    assert ask.heading_sample == {"latitude": 35.6807, "longitude": 139.7671, "at": "2026-10-16T03:00:00.000Z"}
    assert ask.conversation_id == CID


@pytest.mark.parametrize("body", [{}, {"audio": "AAAA", "text": "x"}])
def test_exactly_one_of_audio_and_text(body):
    with pytest.raises(BadRequest, match="exactly one"):
        parse_ask(event(body))


@pytest.mark.parametrize("audio", [b"\x00" * (MIN_AUDIO_BYTES - 2), b"\x00" * (MAX_AUDIO_BYTES + 2), b"\x00" * (MIN_AUDIO_BYTES + 1)])
def test_audio_length_and_alignment(audio):
    with pytest.raises(BadRequest):
        parse_ask(event({"audio": b64(audio)}))


def test_audio_not_base64():
    with pytest.raises(BadRequest, match="base64"):
        parse_ask(event({"audio": "not base64!!"}))


@pytest.mark.parametrize("text", ["", "   ", "あ" * 501, 123])
def test_text_bad(text):
    with pytest.raises(BadRequest):
        parse_ask(event({"text": text}))


@pytest.mark.parametrize("raw", ["not json", "[]", ""])
def test_body_must_be_json_object(raw):
    with pytest.raises(BadRequest):
        parse_ask(event(raw=raw))


@pytest.mark.parametrize("cid", ["abc", CID.upper(), 5])
def test_conversation_id_must_be_lowercase_uuid(cid):
    with pytest.raises(BadRequest, match="conversationId"):
        parse_ask(event({"text": "Q", "conversationId": cid}))


@pytest.mark.parametrize(
    "location",
    [{"latitude": "35", "longitude": 139.0}, {"latitude": True, "longitude": 139.0}, {"latitude": 95.0, "longitude": 139.0}, "x"],
)
def test_broken_location_is_dropped(location):
    assert parse_ask(event({"text": "Q", "location": location})).location is None


@pytest.mark.parametrize("sample", [{"latitude": 35.0, "longitude": 139.0}, {"latitude": 35.0, "longitude": 139.0, "at": "yesterday"}, {"latitude": 35.0, "longitude": 139.0, "at": "2026-10-16T12:00:00"}])
def test_broken_heading_sample_is_dropped(sample):
    assert parse_ask(event({"text": "Q", "headingSample": sample})).heading_sample is None


def test_base64_encoded_body_is_decoded():
    raw = base64.b64encode(json.dumps({"text": "Q"}).encode()).decode()
    ask = parse_ask({"headers": {"x-user-name": "rider01"}, "body": raw, "isBase64Encoded": True})
    assert ask.text == "Q"
```

Run: `cd $BE && env/bin/pytest tests/test_request.py -q`
Expected: `ModuleNotFoundError: No module named 'lib.request'`

- [ ] **Step 2: 実装する**

`src/lib/request.py`:

```python
"""Validation of the App's requests (07 UC-4, UC-5)."""
from __future__ import annotations

import base64
import binascii
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

USER_NAME_RE = re.compile(r"^[a-z0-9]{3,20}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PCM_BYTES_PER_SECOND = 16000 * 2  # 16 kHz, mono, 16-bit
MIN_AUDIO_BYTES = PCM_BYTES_PER_SECOND // 4
MAX_AUDIO_BYTES = PCM_BYTES_PER_SECOND * 60
MAX_TEXT_CHARS = 500


class BadRequest(ValueError):
    """The request is malformed; reported to the App as 400."""


@dataclass(frozen=True)
class AskInput:
    audio: Optional[bytes]
    text: Optional[str]
    location: Optional[dict]
    heading_sample: Optional[dict]
    conversation_id: Optional[str]


def _header(event: dict, name: str) -> Optional[str]:
    for key, value in (event.get("headers") or {}).items():
        if key.lower() == name:
            return value
    return None


def user_name(event: dict) -> str:
    value = _header(event, "x-user-name")
    if not isinstance(value, str) or not USER_NAME_RE.match(value):
        raise BadRequest("x-user-name must be 3-20 lowercase letters or digits")
    return value


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _point(value: Any) -> Optional[dict]:
    """A position, or None when it is missing or broken (the question still goes ahead)."""
    if not isinstance(value, dict):
        return None
    lat, lon = _number(value.get("latitude")), _number(value.get("longitude"))
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return {"latitude": lat, "longitude": lon}


def _sample(value: Any) -> Optional[dict]:
    point = _point(value)
    at = value.get("at") if isinstance(value, dict) else None
    if point is None or not isinstance(at, str):
        return None
    try:
        parsed = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    utc = parsed.astimezone(timezone.utc)
    return {**point, "at": utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"}


def _body(event: dict) -> dict:
    raw = event.get("body") or ""
    try:
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        data = json.loads(raw)
    except (ValueError, binascii.Error):
        raise BadRequest("body must be a JSON object") from None
    if not isinstance(data, dict):
        raise BadRequest("body must be a JSON object")
    return data


def parse_ask(event: dict) -> AskInput:
    data = _body(event)
    audio_b64, text = data.get("audio"), data.get("text")
    if (audio_b64 is None) == (text is None):
        raise BadRequest("exactly one of audio and text is required")

    audio = None
    if audio_b64 is not None:
        if not isinstance(audio_b64, str):
            raise BadRequest("audio must be base64")
        try:
            audio = base64.b64decode(audio_b64, validate=True)
        except (binascii.Error, ValueError):
            raise BadRequest("audio must be base64") from None
        if not MIN_AUDIO_BYTES <= len(audio) <= MAX_AUDIO_BYTES or len(audio) % 2:
            raise BadRequest("audio must be 0.25-60 seconds of 16 kHz mono 16-bit PCM")

    if text is not None:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
            raise BadRequest("text must be 1-500 characters")
        text = text.strip()

    conversation_id = data.get("conversationId")
    if conversation_id is not None and (not isinstance(conversation_id, str) or not UUID_RE.match(conversation_id)):
        raise BadRequest("conversationId must be a lowercase UUID")

    return AskInput(audio, text, _point(data.get("location")), _sample(data.get("headingSample")), conversation_id)
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_request.py -q`
Expected: すべて PASS。

- [ ] **Step 4: コミット**

```bash
cd $BE
git add src/lib/request.py tests/test_request.py
git commit -m "feat: validate ask requests and user names"
```

---

### Task 3: 方位とプロンプト

**Files:**
- Create: `src/lib/geo.py`、`src/lib/prompt.py`
- Test: `tests/test_geo.py`、`tests/test_prompt.py`

**Interfaces:**
- Consumes: `handlers.common.parse_iso`（Task 1）
- Produces: `lib.geo`（`haversine_meters(a: dict, b: dict) -> float`、`bearing_degrees(a: dict, b: dict) -> float`、`compass(bearing: float) -> str`、`heading_degrees(location: dict | None, sample: dict | None, received_at: datetime) -> float | None`、`MIN_DISTANCE_METERS = 5.0`、`MAX_SAMPLE_AGE_SECONDS = 120`）、`lib.prompt`（`format_now(now: datetime) -> str`、`build_prompt(question: str, now: datetime, location: dict | None, address: str | None, heading: float | None, elapsed_seconds: float | None) -> str`、`agent_location(location: dict | None, heading: float | None) -> dict | None`）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_geo.py`:

```python
"""Tests for distance, bearing and the heading rules."""
from datetime import datetime, timedelta, timezone

import pytest

from lib import geo

NOW = datetime(2026, 10, 16, 3, 0, tzinfo=timezone.utc)
HERE = {"latitude": 35.6812, "longitude": 139.7671}
SOUTH_60M = {"latitude": 35.68066, "longitude": 139.7671}


def sample(point, seconds_ago):
    at = NOW - timedelta(seconds=seconds_ago)
    return {**point, "at": at.strftime("%Y-%m-%dT%H:%M:%S.000Z")}


def test_bearing_and_distance():
    assert geo.bearing_degrees(SOUTH_60M, HERE) == pytest.approx(0, abs=0.5)
    assert geo.haversine_meters(SOUTH_60M, HERE) == pytest.approx(60, abs=1)


@pytest.mark.parametrize("bearing, label", [(0, "北"), (90, "東"), (180, "南"), (225, "南西"), (359, "北")])
def test_compass(bearing, label):
    assert geo.compass(bearing) == label


def test_heading_from_a_recent_sample():
    assert geo.heading_degrees(HERE, sample(SOUTH_60M, 10), NOW) == pytest.approx(0, abs=0.5)


def test_heading_none_without_location_or_sample():
    assert geo.heading_degrees(None, sample(SOUTH_60M, 10), NOW) is None
    assert geo.heading_degrees(HERE, None, NOW) is None


def test_heading_none_when_barely_moved():
    near = {"latitude": 35.68118, "longitude": 139.7671}
    assert geo.heading_degrees(HERE, sample(near, 10), NOW) is None


@pytest.mark.parametrize("seconds_ago", [geo.MAX_SAMPLE_AGE_SECONDS + 1, -5])
def test_heading_none_when_sample_is_stale_or_in_future(seconds_ago):
    assert geo.heading_degrees(HERE, sample(SOUTH_60M, seconds_ago), NOW) is None
```

`tests/test_prompt.py`:

```python
"""Tests for the facts block that precedes the rider's question."""
from datetime import datetime, timezone

from lib import prompt

NOW = datetime(2026, 10, 16, 3, 5, tzinfo=timezone.utc)  # 12:05 JST, Friday
HERE = {"latitude": 35.6812, "longitude": 139.7671}


def test_format_now_is_japan_time():
    assert prompt.format_now(NOW) == "現在日時: 2026年10月16日（金）12時05分（日本時間）"


def test_full_prompt():
    text = prompt.build_prompt("右手の建物は？", NOW, HERE, "東京都千代田区丸の内", 0.0, 600)
    assert text.splitlines() == [
        "現在日時: 2026年10月16日（金）12時05分（日本時間）",
        "この質問は、会話の最初の質問から約10分後のものです",
        "現在地: 緯度 35.68120, 経度 139.76710",
        "現在地の住所: 東京都千代田区丸の内（確定した事実。座標から推測し直さないこと）",
        "進行方向: 北（真北から0度）",
        "ライダーから見て右手は東、左手は西の方角",
        "",
        "質問: 右手の建物は？",
    ]


def test_unknowns_are_stated_not_guessed():
    text = prompt.build_prompt("Q", NOW, HERE, None, None, 30)
    assert "現在地の住所: 不明" in text
    assert "進行方向: 不明（方角や左右には触れないこと）" in text
    assert "会話の最初の質問から" not in text


def test_no_location():
    text = prompt.build_prompt("Q", NOW, None, None, None, None)
    assert "現在地: 不明（位置が取れなかった）" in text
    assert "住所" not in text


def test_agent_location():
    assert prompt.agent_location(HERE, 12.345) == {"latitude": 35.6812, "longitude": 139.7671, "headingDegrees": 12.3}
    assert prompt.agent_location(HERE, None) == {"latitude": 35.6812, "longitude": 139.7671, "headingDegrees": None}
    assert prompt.agent_location(None, 1.0) is None
```

Run: `cd $BE && env/bin/pytest tests/test_geo.py tests/test_prompt.py -q`
Expected: `ModuleNotFoundError`（`lib.geo`・`lib.prompt`）

- [ ] **Step 2: 実装する**

`src/lib/geo.py`:

```python
"""Distance, bearing and the rules for when a heading can be trusted."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from handlers.common import parse_iso

MIN_DISTANCE_METERS = 5.0  # below this, GPS noise dominates the bearing
MAX_SAMPLE_AGE_SECONDS = 120  # an older sample says little about the current direction
_EARTH_RADIUS_METERS = 6_371_000.0
_COMPASS = ("北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東",
            "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西")


def haversine_meters(a: dict, b: dict) -> float:
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dlat, dlon = lat2 - lat1, math.radians(b["longitude"] - a["longitude"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_METERS * math.asin(math.sqrt(h))


def bearing_degrees(a: dict, b: dict) -> float:
    """Initial bearing from a to b, clockwise from north, in [0, 360)."""
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dlon = math.radians(b["longitude"] - a["longitude"])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def compass(bearing: float) -> str:
    return _COMPASS[round((bearing % 360) / 22.5) % 16]


def heading_degrees(location: Optional[dict], sample: Optional[dict], received_at: datetime) -> Optional[float]:
    """Direction of travel from the older sample to the current position, or None."""
    if location is None or sample is None:
        return None
    age = (received_at - parse_iso(sample["at"])).total_seconds()
    if age < 0 or age > MAX_SAMPLE_AGE_SECONDS:
        return None
    if haversine_meters(sample, location) < MIN_DISTANCE_METERS:
        return None
    return bearing_degrees(sample, location)
```

`src/lib/prompt.py`:

```python
"""The facts block the Backend puts in front of the rider's question (07 UC-8)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from lib.geo import compass

JST = timezone(timedelta(hours=9), "JST")
_WEEKDAYS = "月火水木金土日"


def format_now(now: datetime) -> str:
    local = now.astimezone(JST)
    return f"現在日時: {local.year}年{local.month}月{local.day}日（{_WEEKDAYS[local.weekday()]}）{local.hour}時{local.minute:02d}分（日本時間）"


def _elapsed(seconds: Optional[float]) -> Optional[str]:
    if seconds is None or seconds < 60:
        return None
    return f"この質問は、会話の最初の質問から約{int(seconds // 60)}分後のものです"


def build_prompt(
    question: str,
    now: datetime,
    location: Optional[dict],
    address: Optional[str],
    heading: Optional[float],
    elapsed_seconds: Optional[float],
) -> str:
    lines = [format_now(now)]
    elapsed = _elapsed(elapsed_seconds)
    if elapsed:
        lines.append(elapsed)
    if location is None:
        lines.append("現在地: 不明（位置が取れなかった）")
    else:
        lines.append(f"現在地: 緯度 {location['latitude']:.5f}, 経度 {location['longitude']:.5f}")
        if address:
            lines.append(f"現在地の住所: {address}（確定した事実。座標から推測し直さないこと）")
        else:
            lines.append("現在地の住所: 不明")
    if heading is None:
        lines.append("進行方向: 不明（方角や左右には触れないこと）")
    else:
        lines.append(f"進行方向: {compass(heading)}（真北から{round(heading)}度）")
        lines.append(f"ライダーから見て右手は{compass(heading + 90)}、左手は{compass(heading - 90)}の方角")
    return "\n".join(lines) + f"\n\n質問: {question}"


def agent_location(location: Optional[dict], heading: Optional[float]) -> Optional[dict]:
    """Position and heading as numbers for the agent's place tools (07 UC-8)."""
    if location is None:
        return None
    return {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "headingDegrees": round(heading, 1) if heading is not None else None,
    }
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_geo.py tests/test_prompt.py -q`
Expected: すべて PASS。

- [ ] **Step 4: コミット**

```bash
cd $BE
git add src/lib/geo.py src/lib/prompt.py tests/test_geo.py tests/test_prompt.py
git commit -m "feat: compute heading and build the agent prompt from facts"
```

---

### Task 4: 座標から住所

**Files:**
- Create: `src/lib/address.py`
- Test: `tests/test_address.py`

**Interfaces:**
- Consumes: `lib.clients.geo`（Task 1）
- Produces: `lib.address.describe_location(latitude: float, longitude: float, client: Any = None) -> str | None`（都道府県＋市区町村＋区＋町名。失敗・不明は None）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_address.py`:

```python
"""Tests for reverse geocoding to a town-level address."""
from lib.address import describe_location


class FakeGeo:
    def __init__(self, items=None, error=None):
        self.items, self.error, self.calls = items or [], error, []

    def reverse_geocode(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"ResultItems": self.items}


def item(**address):
    return {"Address": address}


def test_longitude_first_and_japanese():
    fake = FakeGeo([item(Region={"Name": "東京都"}, Locality="千代田区", SubDistrict="丸の内")])
    assert describe_location(35.6812, 139.7671, fake) == "東京都千代田区丸の内"
    assert fake.calls[0]["QueryPosition"] == [139.7671, 35.6812]
    assert fake.calls[0]["Language"] == "ja"


def test_designated_city_ward_and_town():
    fake = FakeGeo([item(Region={"Name": "北海道"}, Locality="札幌市", District="北区", SubDistrict="北6条西")])
    assert describe_location(43.0, 141.3, fake) == "北海道札幌市北区北6条西"


def test_county_when_no_locality():
    fake = FakeGeo([item(Region={"Name": "神奈川県"}, SubRegion={"Name": "足柄下郡"})])
    assert describe_location(35.2, 139.0, fake) == "神奈川県足柄下郡"


def test_region_only():
    assert describe_location(35.0, 139.0, FakeGeo([item(Region={"Name": "静岡県"})])) == "静岡県"


def test_nothing_found_or_error_is_none():
    assert describe_location(30.0, 140.0, FakeGeo([])) is None
    assert describe_location(35.0, 139.0, FakeGeo(error=RuntimeError("x"))) is None
```

Run: `cd $BE && env/bin/pytest tests/test_address.py -q`
Expected: `ModuleNotFoundError: No module named 'lib.address'`

- [ ] **Step 2: 実装する**

`src/lib/address.py`:

```python
"""Coordinates to a Japanese address down to the town (no block numbers)."""
from __future__ import annotations

from typing import Any, Optional

from handlers.common import log
from lib import clients


def describe_location(latitude: float, longitude: float, client: Any = None) -> Optional[str]:
    """Prefecture + city + ward + town, or None when it cannot be resolved (never raises)."""
    try:
        result = (client or clients.geo()).reverse_geocode(
            QueryPosition=[longitude, latitude],  # longitude first
            MaxResults=1,
            Language="ja",
        )
    except Exception as error:  # noqa: BLE001 - the question goes ahead without an address
        log({"event": "reverse_geocode_failed", "error": type(error).__name__})
        return None
    items = result.get("ResultItems") or []
    if not items:
        return None
    address = items[0].get("Address") or {}
    region = (address.get("Region") or {}).get("Name") or ""
    locality = address.get("Locality") or (address.get("SubRegion") or {}).get("Name") or ""
    if not locality:
        return region or None
    place = f"{region}{locality}"
    for part in (address.get("District"), address.get("SubDistrict")):
        if part and part not in place:
            place += part
    return place
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_address.py -q`
Expected: 5 passed。

- [ ] **Step 4: コミット**

```bash
cd $BE
git add src/lib/address.py tests/test_address.py
git commit -m "feat: resolve town-level address from coordinates"
```

---

### Task 5: 記録の読み書き

**Files:**
- Create: `src/lib/store.py`、`src/lib/conversation.py`（Task 6 で中身を書く。ここでは fixture のために `reset_cache()` だけ置く）
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `lib.clients.table`（Task 1）、fixture `aws`（Task 1）
- Produces: `lib.store`（`ask_key(user: str, ask_id: str) -> dict`、`conversation_started_at(user: str, conversation_id: str, now_iso: str) -> str`、`create_ask(item: dict) -> None`、`claim_ask(user: str, ask_id: str) -> dict | None`、`update_ask(user: str, ask_id: str, fields: dict) -> None`、`get_ask(user: str, ask_id: str) -> dict | None`）。読み出した値の数値は `int` か `float` に戻す。値が `None` の項目は書かない。

- [ ] **Step 1: fixture のための仮の `conversation.py` を置く**

`src/lib/conversation.py`:

```python
"""How long a conversation lasts; filled in by Task 6."""


def reset_cache() -> None:
    pass
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_store.py`:

```python
"""Tests for the DynamoDB record helpers (moto)."""
from lib import store

USER, ASK = "rider01", "11111111-1111-4111-8111-111111111111"


def new_ask(**extra):
    return {**store.ask_key(USER, ASK), "askId": ASK, "status": "pending", "location": {"latitude": 35.6812, "longitude": 139.7671}, **extra}


def test_create_and_get_round_trips_numbers(aws):
    store.create_ask(new_ask(question="Q", transcript=None))
    item = store.get_ask(USER, ASK)
    assert item["location"] == {"latitude": 35.6812, "longitude": 139.7671}
    assert isinstance(item["location"]["latitude"], float)
    assert "transcript" not in item


def test_get_missing_and_other_user(aws):
    store.create_ask(new_ask())
    assert store.get_ask(USER, "22222222-2222-4222-8222-222222222222") is None
    assert store.get_ask("someoneelse", ASK) is None


def test_claim_only_once(aws):
    store.create_ask(new_ask())
    first = store.claim_ask(USER, ASK)
    assert first["status"] == "processing"
    assert store.claim_ask(USER, ASK) is None


def test_claim_missing_is_none(aws):
    assert store.claim_ask(USER, ASK) is None


def test_update_sets_fields_and_skips_none(aws):
    store.create_ask(new_ask())
    store.update_ask(USER, ASK, {"status": "completed", "answer": "A", "usage": {"inputTokens": 10}, "error": None})
    item = store.get_ask(USER, ASK)
    assert item["status"] == "completed" and item["answer"] == "A" and item["usage"] == {"inputTokens": 10}
    assert "error" not in item


def test_conversation_start_is_kept_from_first_question(aws):
    cid = "33333333-3333-4333-8333-333333333333"
    assert store.conversation_started_at(USER, cid, "2026-10-16T03:00:00.000Z") == "2026-10-16T03:00:00.000Z"
    assert store.conversation_started_at(USER, cid, "2026-10-16T03:10:00.000Z") == "2026-10-16T03:00:00.000Z"
```

Run: `cd $BE && env/bin/pytest tests/test_store.py -q`
Expected: `ModuleNotFoundError: No module named 'lib.store'`

- [ ] **Step 3: 実装する**

`src/lib/store.py`:

```python
"""Records in one DynamoDB table: pk USER#<name>, sk ASK#<id> or CONV#<id>."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Optional

from botocore.exceptions import ClientError

from lib import clients

_CONDITION_FAILED = "ConditionalCheckFailedException"


def _to_item(value: Any) -> Any:
    """Floats become Decimal; None values are dropped."""
    return json.loads(json.dumps(_drop_none(value)), parse_float=Decimal)


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_none(v) for v in value]
    return value


def _from_item(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _from_item(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_item(v) for v in value]
    return value


def ask_key(user: str, ask_id: str) -> dict:
    return {"pk": f"USER#{user}", "sk": f"ASK#{ask_id}"}


def _conversation_key(user: str, conversation_id: str) -> dict:
    return {"pk": f"USER#{user}", "sk": f"CONV#{conversation_id}"}


def conversation_started_at(user: str, conversation_id: str, now_iso: str) -> str:
    """When this conversation's first question arrived (recorded on first sight)."""
    key = _conversation_key(user, conversation_id)
    try:
        clients.table().put_item(Item={**key, "startedAt": now_iso}, ConditionExpression="attribute_not_exists(pk)")
        return now_iso
    except ClientError as error:
        if error.response["Error"]["Code"] != _CONDITION_FAILED:
            raise
    return clients.table().get_item(Key=key)["Item"]["startedAt"]


def create_ask(item: dict) -> None:
    clients.table().put_item(Item=_to_item(item))


def claim_ask(user: str, ask_id: str) -> Optional[dict]:
    """pending -> processing, once. None if already claimed or missing."""
    try:
        result = clients.table().update_item(
            Key=ask_key(user, ask_id),
            UpdateExpression="SET #s = :processing",
            ConditionExpression="#s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":processing": "processing", ":pending": "pending"},
            ReturnValues="ALL_NEW",
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == _CONDITION_FAILED:
            return None
        raise
    return _from_item(result["Attributes"])


def update_ask(user: str, ask_id: str, fields: dict) -> None:
    values = _to_item(fields)
    if not values:
        return
    names = {f"#k{i}": key for i, key in enumerate(values)}
    expression = "SET " + ", ".join(f"#k{i} = :v{i}" for i in range(len(values)))
    clients.table().update_item(
        Key=ask_key(user, ask_id),
        UpdateExpression=expression,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues={f":v{i}": value for i, value in enumerate(values.values())},
    )


def get_ask(user: str, ask_id: str) -> Optional[dict]:
    item = clients.table().get_item(Key=ask_key(user, ask_id)).get("Item")
    return _from_item(item) if item else None
```

- [ ] **Step 4: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_store.py -q`
Expected: 6 passed。

- [ ] **Step 5: コミット**

```bash
cd $BE
git add src/lib/store.py src/lib/conversation.py tests/test_store.py
git commit -m "feat: store asks and conversations in dynamodb"
```

---

### Task 6: 会話を区切る時間

**Files:**
- Modify: `src/lib/conversation.py`（Task 5 の仮のものを置き換える）
- Test: `tests/test_conversation.py`

**Interfaces:**
- Consumes: `lib.clients.ssm`（Task 1）
- Produces: `lib.conversation`（`reset_minutes(clock: Callable[[], float] = time.monotonic) -> int`、`reset_cache() -> None`、`DEFAULT_MINUTES = 15`、`MAX_MINUTES = 55`、`CACHE_SECONDS = 60`）。読めない・不正な値なら既定の15分（質問は止めない）。55を超えたら55、1未満なら1。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_conversation.py`:

```python
"""Tests for the conversation reset minutes read from SSM."""
import boto3
import pytest

from lib import conversation

PARAM = "/trv2/test/conversation-reset-minutes"


def put(value):
    boto3.client("ssm", region_name="ap-northeast-1").put_parameter(Name=PARAM, Value=value, Type="String", Overwrite=True)


def test_reads_value(aws):
    assert conversation.reset_minutes() == 15


@pytest.mark.parametrize("value, expected", [("30", 30), ("90", 55), ("0", 1), ("abc", 15), (" 20 ", 20)])
def test_clamps_and_defaults(aws, value, expected):
    put(value)
    assert conversation.reset_minutes() == expected


def test_cached_for_a_minute(aws):
    now = [0.0]
    assert conversation.reset_minutes(clock=lambda: now[0]) == 15
    put("30")
    now[0] = 59
    assert conversation.reset_minutes(clock=lambda: now[0]) == 15
    now[0] = 61
    assert conversation.reset_minutes(clock=lambda: now[0]) == 30


def test_missing_parameter_falls_back(aws, monkeypatch):
    monkeypatch.setenv("CONVERSATION_RESET_PARAMETER", "/trv2/test/missing")
    assert conversation.reset_minutes() == conversation.DEFAULT_MINUTES
```

Run: `cd $BE && env/bin/pytest tests/test_conversation.py -q`
Expected: `AttributeError: module 'lib.conversation' has no attribute 'reset_minutes'`

- [ ] **Step 2: 実装する**

`src/lib/conversation.py`:

```python
"""How long a conversation lasts before the App starts a new one (adr/0003).

Read from SSM so an admin can change it without a deploy; capped below the
agent runtime's idle timeout (60 min) so the App always resets first.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Optional

from handlers.common import log
from lib import clients

DEFAULT_MINUTES = 15
MAX_MINUTES = 55
CACHE_SECONDS = 60

_cache: Optional[tuple[int, float]] = None


def reset_cache() -> None:
    global _cache
    _cache = None


def _read() -> int:
    name = os.environ["CONVERSATION_RESET_PARAMETER"]
    try:
        raw = clients.ssm().get_parameter(Name=name)["Parameter"]["Value"]
        minutes = int(raw.strip())
    except Exception as error:  # noqa: BLE001 - never fail a question over this setting
        log({"event": "conversation_reset_default", "reason": type(error).__name__})
        return DEFAULT_MINUTES
    clamped = min(max(minutes, 1), MAX_MINUTES)
    if clamped != minutes:
        log({"event": "conversation_reset_clamped", "value": minutes, "used": clamped})
    return clamped


def reset_minutes(clock: Callable[[], float] = time.monotonic) -> int:
    global _cache
    now = clock()
    if _cache is not None and now - _cache[1] < CACHE_SECONDS:
        return _cache[0]
    minutes = _read()
    _cache = (minutes, now)
    return minutes
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_conversation.py tests/test_store.py -q`
Expected: すべて PASS。

- [ ] **Step 4: コミット**

```bash
cd $BE
git add src/lib/conversation.py tests/test_conversation.py
git commit -m "feat: read conversation reset minutes from ssm"
```

---

### Task 7: Agent の呼び出し

**Files:**
- Create: `src/lib/agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `lib.clients.agentcore`（Task 1）、Agent の SSE（07 UC-8: `text`・`tool`・`done`・`error`）
- Produces: `lib.agent.AgentError(RuntimeError)`、`AgentReply`（dataclass: `answer: str`・`usage: dict`・`model_id: str`・`tools: list[str]`・`first_event_at: float | None`（UNIX 秒））、`parse_events(lines: Iterable[bytes | str], clock: Callable[[], float] = time.time) -> AgentReply`、`invoke(prompt: str, location: dict | None, session_id: str, client: Any = None, attempts: int = 3, sleep: Callable[[float], None] = time.sleep) -> AgentReply`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_agent.py`:

```python
"""Tests for invoking the agent runtime and reading its SSE events."""
import json

import pytest
from botocore.exceptions import ClientError

from lib.agent import AgentError, invoke, parse_events


def sse(*events):
    return [f"data: {json.dumps(e, ensure_ascii=False)}".encode() for e in events] + [b""]


DONE = {"type": "done", "answer": " 晴れです。 ", "stopReason": "end_turn",
        "usage": {"inputTokens": 100, "outputTokens": 10, "modelCalls": 2}, "modelId": "m"}


def test_parse_collects_tools_and_done():
    reply = parse_events(sse({"type": "text", "text": "調べます。"}, {"type": "tool", "name": "webSearch___WebSearch"}, DONE), clock=lambda: 42.0)
    assert reply.answer == "晴れです。"
    assert reply.tools == ["webSearch___WebSearch"]
    assert reply.usage == {"inputTokens": 100, "outputTokens": 10, "modelCalls": 2}
    assert reply.model_id == "m"
    assert reply.first_event_at == 42.0


def test_parse_ignores_noise_lines():
    reply = parse_events([b"", b": keep-alive", b"data: not json", "data: " + json.dumps(DONE)])
    assert reply.answer == "晴れです。"


def test_error_event_raises():
    with pytest.raises(AgentError, match="agent_failed: empty answer"):
        parse_events(sse({"type": "error", "code": "agent_failed", "message": "empty answer"}))


def test_runtime_level_error_shape_raises():
    with pytest.raises(AgentError, match="boom"):
        parse_events(sse({"error": "boom", "error_type": "RuntimeError"}))


def test_missing_or_empty_done_raises():
    with pytest.raises(AgentError, match="no answer"):
        parse_events(sse({"type": "text", "text": "x"}))
    with pytest.raises(AgentError, match="no answer"):
        parse_events(sse({**DONE, "answer": "  "}))


class Body:
    def __init__(self, lines):
        self.lines = lines

    def iter_lines(self):
        return iter(self.lines)


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def invoke_agent_runtime(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return {"response": Body(outcome)}


def conflict():
    return ClientError({"Error": {"Code": "RetryableConflictException", "Message": "retry"}}, "InvokeAgentRuntime")


def test_invoke_sends_payload_and_session():
    client = FakeClient([sse(DONE)])
    reply = invoke("P", {"latitude": 1.0, "longitude": 2.0, "headingDegrees": None}, "s" * 36, client=client)
    call = client.calls[0]
    assert reply.answer == "晴れです。"
    assert call["runtimeSessionId"] == "s" * 36
    assert call["qualifier"] == "DEFAULT"
    assert json.loads(call["payload"]) == {"prompt": "P", "location": {"latitude": 1.0, "longitude": 2.0, "headingDegrees": None}}


def test_invoke_retries_conflicts():
    sleeps = []
    client = FakeClient([conflict(), conflict(), sse(DONE)])
    assert invoke("P", None, "s" * 36, client=client, sleep=sleeps.append).answer == "晴れです。"
    assert sleeps == [0.5, 1.0]


def test_invoke_gives_up_after_attempts_and_on_other_errors():
    with pytest.raises(AgentError, match="RetryableConflictException"):
        invoke("P", None, "s" * 36, client=FakeClient([conflict()] * 3), sleep=lambda s: None)
    denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "InvokeAgentRuntime")
    with pytest.raises(AgentError, match="AccessDeniedException"):
        invoke("P", None, "s" * 36, client=FakeClient([denied]), sleep=lambda s: None)
```

Run: `cd $BE && env/bin/pytest tests/test_agent.py -q`
Expected: `ModuleNotFoundError: No module named 'lib.agent'`

- [ ] **Step 2: 実装する**

`src/lib/agent.py`:

```python
"""Invoke the agent runtime (us-east-1) and read its SSE events (07 UC-8)."""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Optional

from botocore.exceptions import ClientError

from lib import clients

_RETRYABLE = "RetryableConflictException"


class AgentError(RuntimeError):
    """The agent did not produce an answer; reported as agent_failed."""


@dataclass
class AgentReply:
    answer: str
    usage: dict
    model_id: str
    tools: list[str] = field(default_factory=list)
    first_event_at: Optional[float] = None


def parse_events(lines: Iterable[Any], clock: Callable[[], float] = time.time) -> AgentReply:
    tools: list[str] = []
    first: Optional[float] = None
    done: Optional[dict] = None
    for raw in lines:
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not line or not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[len("data:"):].strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if first is None:
            first = clock()
        kind = event.get("type")
        if kind == "tool":
            tools.append(str(event.get("name", "")))
        elif kind == "done":
            done = event
        elif kind == "error":
            raise AgentError(f"{event.get('code')}: {event.get('message')}")
        elif kind is None and "error" in event:
            # The runtime's own error shape when the entrypoint raised.
            raise AgentError(str(event["error"]))
    if done is None or not str(done.get("answer", "")).strip():
        raise AgentError("no answer")
    return AgentReply(
        answer=str(done["answer"]).strip(),
        usage=done.get("usage") or {},
        model_id=str(done.get("modelId", "")),
        tools=tools,
        first_event_at=first,
    )


def invoke(
    prompt: str,
    location: Optional[dict],
    session_id: str,
    client: Any = None,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> AgentReply:
    client = client or clients.agentcore()
    payload = json.dumps({"prompt": prompt, "location": location}, ensure_ascii=False).encode("utf-8")
    for attempt in range(attempts):
        try:
            response = client.invoke_agent_runtime(
                agentRuntimeArn=os.environ["AGENT_ARN"],
                runtimeSessionId=session_id,
                qualifier="DEFAULT",
                payload=payload,
            )
            return parse_events(response["response"].iter_lines())
        except ClientError as error:
            code = error.response["Error"]["Code"]
            if code == _RETRYABLE and attempt < attempts - 1:
                sleep(0.5 * (attempt + 1))
                continue
            raise AgentError(code) from error
    raise AgentError("no attempts")
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_agent.py -q`
Expected: 9 passed。

- [ ] **Step 4: コミット**

```bash
cd $BE
git add src/lib/agent.py tests/test_agent.py
git commit -m "feat: invoke agent runtime and parse its events"
```

---

### Task 8: 回答の音声

**Files:**
- Create: `src/lib/speech.py`
- Test: `tests/test_speech.py`

**Interfaces:**
- Consumes: `lib.clients.polly`・`lib.clients.s3`（Task 1）
- Produces: `lib.speech`（`build_ssml(text: str, volume: str) -> str`、`answer_key(ask_id: str) -> str`（`answers/<id>.mp3`）、`synthesize(ask_id: str, text: str, polly: Any = None, s3: Any = None) -> str`（S3 のキーを返す。失敗は例外））。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_speech.py`:

```python
"""Tests for Polly SSML and storing the answer audio."""
import io

import pytest

from lib import speech


def test_ssml_is_escaped_and_louder():
    ssml = speech.build_ssml("A&B <C>", "+6dB")
    assert ssml == '<speak><amazon:effect name="drc"><prosody volume="+6dB">A&amp;B &lt;C&gt;</prosody></amazon:effect></speak>'


class FakePolly:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"AudioStream": io.BytesIO(b"mp3-bytes")}


class FakeS3:
    def __init__(self):
        self.puts = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)


def test_synthesize_stores_mp3(monkeypatch):
    monkeypatch.setenv("POLLY_VOICE_ID", "Kazuha")
    monkeypatch.setenv("POLLY_VOLUME", "+6dB")
    polly, s3 = FakePolly(), FakeS3()
    key = speech.synthesize("abc", "晴れです。", polly=polly, s3=s3)
    assert key == "answers/abc.mp3"
    call = polly.calls[0]
    assert (call["TextType"], call["Engine"], call["VoiceId"], call["OutputFormat"], call["LanguageCode"]) == ("ssml", "neural", "Kazuha", "mp3", "ja-JP")
    assert s3.puts[0]["Bucket"] == "test-audio" and s3.puts[0]["Key"] == key and s3.puts[0]["Body"] == b"mp3-bytes"
    assert s3.puts[0]["ContentType"] == "audio/mpeg"


def test_polly_failure_raises():
    with pytest.raises(RuntimeError):
        speech.synthesize("abc", "x", polly=FakePolly(RuntimeError("down")), s3=FakeS3())
```

Run: `cd $BE && env/bin/pytest tests/test_speech.py -q`
Expected: `ModuleNotFoundError: No module named 'lib.speech'`

- [ ] **Step 2: 実装する**

`src/lib/speech.py`:

```python
"""Answer audio: Polly neural voice with compression and a volume boost, stored in S3."""
from __future__ import annotations

import os
from typing import Any
from xml.sax.saxutils import escape

from lib import clients


def build_ssml(text: str, volume: str) -> str:
    # DRC and a dB boost help the answer stand out against wind and navigation prompts.
    return f'<speak><amazon:effect name="drc"><prosody volume="{volume}">{escape(text)}</prosody></amazon:effect></speak>'


def answer_key(ask_id: str) -> str:
    return f"answers/{ask_id}.mp3"


def synthesize(ask_id: str, text: str, polly: Any = None, s3: Any = None) -> str:
    response = (polly or clients.polly()).synthesize_speech(
        Text=build_ssml(text, os.environ.get("POLLY_VOLUME", "+6dB")),
        TextType="ssml",
        OutputFormat="mp3",
        VoiceId=os.environ.get("POLLY_VOICE_ID", "Kazuha"),
        Engine="neural",
        LanguageCode="ja-JP",
    )
    key = answer_key(ask_id)
    (s3 or clients.s3()).put_object(
        Bucket=os.environ["AUDIO_BUCKET"], Key=key, Body=response["AudioStream"].read(), ContentType="audio/mpeg"
    )
    return key
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_speech.py -q`
Expected: 3 passed。

- [ ] **Step 4: コミット**

```bash
cd $BE
git add src/lib/speech.py tests/test_speech.py
git commit -m "feat: synthesize louder answer audio with polly"
```

---

### Task 9: ストリーミングの文字起こし

**Files:**
- Create: `src/lib/transcribe.py`
- Test: `tests/test_transcribe.py`

**Interfaces:**
- Produces: `lib.transcribe.transcribe_pcm(audio: bytes) -> str`（ja-JP・16kHz・PCM を一気に流し込み、確定した文をつないで返す。空なら `""`。失敗は例外）、`join_finals(finals: list[str]) -> str`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_transcribe.py`:

```python
"""Tests for the transcription helpers (the streaming call itself is checked by the smoke test)."""
from lib import transcribe


def test_join_finals():
    assert transcribe.join_finals(["右手に見える", "山は何？ "]) == "右手に見える山は何？"
    assert transcribe.join_finals([]) == ""
    assert transcribe.join_finals(["  "]) == ""


def test_chunks_cover_the_audio():
    audio = bytes(range(256)) * 100
    chunks = list(transcribe.chunks(audio))
    assert b"".join(chunks) == audio
    assert all(len(c) <= transcribe.CHUNK_BYTES for c in chunks)
```

Run: `cd $BE && env/bin/pytest tests/test_transcribe.py -q`
Expected: `ModuleNotFoundError: No module named 'lib.transcribe'`

- [ ] **Step 2: 実装する**

`src/lib/transcribe.py`:

```python
"""Streaming transcription of a finished PCM recording (adr/0002: sent all at once, not paced)."""
from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

CHUNK_BYTES = 8 * 1024
SAMPLE_RATE = 16000


def chunks(audio: bytes) -> Iterator[bytes]:
    for start in range(0, len(audio), CHUNK_BYTES):
        yield audio[start:start + CHUNK_BYTES]


def join_finals(finals: list[str]) -> str:
    return "".join(finals).strip()


class _Collector(TranscriptResultStreamHandler):
    def __init__(self, stream) -> None:
        super().__init__(stream)
        self.finals: list[str] = []

    async def handle_transcript_event(self, transcript_event: TranscriptEvent) -> None:
        for result in transcript_event.transcript.results:
            if not result.is_partial and result.alternatives:
                self.finals.append(result.alternatives[0].transcript)


async def _transcribe(audio: bytes) -> str:
    client = TranscribeStreamingClient(region=os.environ.get("AWS_REGION", "ap-northeast-1"))
    stream = await client.start_stream_transcription(
        language_code="ja-JP", media_sample_rate_hz=SAMPLE_RATE, media_encoding="pcm"
    )
    collector = _Collector(stream.output_stream)

    async def send() -> None:
        for chunk in chunks(audio):
            await stream.input_stream.send_audio_event(audio_chunk=chunk)
        await stream.input_stream.end_stream()

    await asyncio.gather(send(), collector.handle_events())
    return join_finals(collector.finals)


def transcribe_pcm(audio: bytes) -> str:
    return asyncio.run(_transcribe(audio))
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_transcribe.py -q`
Expected: 2 passed。

- [ ] **Step 4: コミット**

```bash
cd $BE
git add src/lib/transcribe.py tests/test_transcribe.py
git commit -m "feat: transcribe pcm recordings with streaming transcribe"
```

---

### Task 10: 質問の受け付け（`POST /asks`）

**Files:**
- Create: `src/handlers/ask.py`
- Test: `tests/test_ask.py`

**Interfaces:**
- Consumes: `lib.request`（Task 2）、`lib.store`（Task 5）、`lib.conversation`（Task 6）、`handlers.common`（Task 1）、fixture `aws`
- Produces: `handlers.ask.handler(event, context) -> dict`。DynamoDB の ask の項目（`askId`・`userName`・`conversationId`・`conversationStartedAt`・`status="pending"`・`receivedAt`・`inputType`（`audio`/`text`）・`audioKey`（`audio/<id>.pcm`）か `question`・`location`・`headingSample`・`timings={"receivedAt": …}`）。SQS の本文 `{"userName": …, "askId": …}`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_ask.py`:

```python
"""Tests for POST /asks (moto)."""
import base64
import json

from handlers import ask
from lib import store
from lib.request import MIN_AUDIO_BYTES

CID = "0b8e7c1e-3f1a-4f5e-9a51-2a0b2c6f7d10"


def call(body, user="rider01"):
    return ask.handler({"headers": {"x-user-name": user}, "body": json.dumps(body)}, None)


def messages(aws):
    got = aws.sqs.receive_message(QueueUrl=aws.queue_url, MaxNumberOfMessages=10).get("Messages", [])
    return [json.loads(m["Body"]) for m in got]


def test_text_question_is_accepted(aws):
    result = call({"text": "富士山の高さは？", "location": {"latitude": 35.6812, "longitude": 139.7671}})
    assert result["statusCode"] == 202
    body = json.loads(result["body"])
    item = store.get_ask("rider01", body["askId"])
    assert item["status"] == "pending" and item["inputType"] == "text" and item["question"] == "富士山の高さは？"
    assert item["conversationId"] == body["conversationId"]
    assert item["timings"]["receivedAt"] == item["receivedAt"]
    assert messages(aws) == [{"userName": "rider01", "askId": body["askId"]}]


def test_expiry_is_reset_minutes_after_receipt(aws):
    body = json.loads(call({"text": "Q"})["body"])
    item = store.get_ask("rider01", body["askId"])
    from handlers.common import parse_iso
    assert (parse_iso(body["conversationExpiresAt"]) - parse_iso(item["receivedAt"])).total_seconds() == 15 * 60


def test_audio_goes_to_s3(aws):
    audio = b"\x01\x00" * (MIN_AUDIO_BYTES // 2)
    body = json.loads(call({"audio": base64.b64encode(audio).decode()})["body"])
    item = store.get_ask("rider01", body["askId"])
    assert item["inputType"] == "audio" and item["audioKey"] == f"audio/{body['askId']}.pcm"
    assert aws.s3.get_object(Bucket=aws.bucket, Key=item["audioKey"])["Body"].read() == audio


def test_conversation_continues_and_keeps_start(aws):
    first = json.loads(call({"text": "Q1", "conversationId": CID})["body"])
    second = json.loads(call({"text": "Q2", "conversationId": CID})["body"])
    assert first["conversationId"] == second["conversationId"] == CID
    a, b = store.get_ask("rider01", first["askId"]), store.get_ask("rider01", second["askId"])
    assert a["conversationStartedAt"] == b["conversationStartedAt"] == a["receivedAt"]


def test_bad_request_leaves_nothing(aws):
    result = call({"audio": "AAA="})
    assert result["statusCode"] == 400
    assert json.loads(result["body"])["error"] == "bad_request"
    assert aws.table.scan()["Items"] == []
    assert aws.s3.list_objects_v2(Bucket=aws.bucket).get("KeyCount", 0) == 0
    assert messages(aws) == []


def test_bad_user_is_400(aws):
    assert call({"text": "Q"}, user="X")["statusCode"] == 400
```

Run: `cd $BE && env/bin/pytest tests/test_ask.py -q`
Expected: `ImportError: cannot import name 'ask' from 'handlers'`

- [ ] **Step 2: 実装する**

`src/handlers/ask.py`:

```python
"""POST /asks: accept a question, store it, and queue it for the worker (07 UC-5)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import timedelta

from handlers.common import iso, log, response, utc_now
from lib import clients, conversation, store
from lib.request import BadRequest, parse_ask, user_name


def handler(event, context):
    try:
        user = user_name(event)
        ask = parse_ask(event)
    except BadRequest as error:
        return response(400, {"error": "bad_request", "message": str(error)})

    now = utc_now()
    ask_id = str(uuid.uuid4())
    conversation_id = ask.conversation_id or str(uuid.uuid4())
    expires_at = now + timedelta(minutes=conversation.reset_minutes())
    started_at = store.conversation_started_at(user, conversation_id, iso(now))

    item = {
        **store.ask_key(user, ask_id),
        "askId": ask_id,
        "userName": user,
        "conversationId": conversation_id,
        "conversationStartedAt": started_at,
        "status": "pending",
        "receivedAt": iso(now),
        "inputType": "audio" if ask.audio is not None else "text",
        "question": ask.text,
        "location": ask.location,
        "headingSample": ask.heading_sample,
        "timings": {"receivedAt": iso(now)},
    }
    if ask.audio is not None:
        item["audioKey"] = f"audio/{ask_id}.pcm"
        clients.s3().put_object(
            Bucket=os.environ["AUDIO_BUCKET"], Key=item["audioKey"], Body=ask.audio, ContentType="application/octet-stream"
        )
    store.create_ask(item)
    clients.sqs().send_message(QueueUrl=os.environ["QUEUE_URL"], MessageBody=json.dumps({"userName": user, "askId": ask_id}))
    log({"event": "ask_accepted", "askId": ask_id, "inputType": item["inputType"],
         "audioBytes": len(ask.audio) if ask.audio is not None else 0})
    return response(202, {"askId": ask_id, "conversationId": conversation_id, "conversationExpiresAt": iso(expires_at)})
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_ask.py -q`
Expected: 6 passed。

- [ ] **Step 4: コミット**

```bash
cd $BE
git add src/handlers/ask.py tests/test_ask.py
git commit -m "feat: accept asks and queue them for the worker"
```

---

### Task 11: 結果の受け取り（`GET /asks/{askId}`）

**Files:**
- Create: `src/handlers/result.py`
- Test: `tests/test_result.py`

**Interfaces:**
- Consumes: `lib.store`（Task 5）、`lib.request.user_name`・`UUID_RE`（Task 2）、`lib.clients.s3`
- Produces: `handlers.result.handler(event, context) -> dict`。`status` は `pending`/`processing` を `processing` として返す。`audio` は `answerAudioKey` があれば `[{"seq": 1, "url": <10分有効の署名付き URL>}]`、無ければ `[]`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_result.py`:

```python
"""Tests for GET /asks/{askId} (moto)."""
import json

from handlers import result
from lib import store

USER, ASK = "rider01", "11111111-1111-4111-8111-111111111111"


def call(ask_id=ASK, user=USER):
    return result.handler({"headers": {"x-user-name": user}, "pathParameters": {"askId": ask_id}}, None)


def put(**fields):
    store.create_ask({**store.ask_key(USER, ASK), "askId": ASK, "timings": {"receivedAt": "2026-10-16T03:00:00.000Z"}, **fields})


def test_pending_is_reported_as_processing(aws):
    put(status="pending")
    body = json.loads(call()["body"])
    assert body == {"askId": ASK, "status": "processing", "transcript": None, "answer": None, "audio": [], "error": None,
                    "timings": {"receivedAt": "2026-10-16T03:00:00.000Z"}}


def test_completed_has_presigned_audio(aws):
    aws.s3.put_object(Bucket=aws.bucket, Key=f"answers/{ASK}.mp3", Body=b"mp3")
    put(status="completed", transcript="T", answer="A", answerAudioKey=f"answers/{ASK}.mp3")
    body = json.loads(call()["body"])
    assert body["status"] == "completed" and body["answer"] == "A" and body["transcript"] == "T"
    assert body["audio"][0]["seq"] == 1
    url = body["audio"][0]["url"]
    assert f"answers/{ASK}.mp3" in url and "X-Amz-Expires=600" in url


def test_failed_keeps_answer_for_device_tts(aws):
    put(status="failed", error="tts_failed", answer="A")
    body = json.loads(call()["body"])
    assert body["status"] == "failed" and body["error"] == "tts_failed" and body["answer"] == "A" and body["audio"] == []


def test_missing_is_404(aws):
    assert call()["statusCode"] == 404


def test_other_user_gets_404(aws):
    put(status="completed", answer="A")
    response = call(user="someoneelse")
    assert response["statusCode"] == 404
    assert json.loads(response["body"]) == {"error": "not_found"}


def test_malformed_id_is_404_and_bad_user_is_400(aws):
    assert call(ask_id="../etc")["statusCode"] == 404
    assert call(user="X")["statusCode"] == 400
```

Run: `cd $BE && env/bin/pytest tests/test_result.py -q`
Expected: `ImportError: cannot import name 'result' from 'handlers'`

- [ ] **Step 2: 実装する**

`src/handlers/result.py`:

```python
"""GET /asks/{askId}: the App polls this for the answer (07 UC-5)."""
from __future__ import annotations

import os

from handlers.common import response
from lib import clients, store
from lib.request import UUID_RE, BadRequest, user_name

PRESIGN_SECONDS = 600
_STATUS = {"pending": "processing", "processing": "processing", "completed": "completed", "failed": "failed"}


def handler(event, context):
    try:
        user = user_name(event)
    except BadRequest as error:
        return response(400, {"error": "bad_request", "message": str(error)})
    ask_id = (event.get("pathParameters") or {}).get("askId") or ""
    item = store.get_ask(user, ask_id) if UUID_RE.match(ask_id) else None
    if item is None:
        return response(404, {"error": "not_found"})

    audio = []
    if item.get("answerAudioKey"):
        url = clients.s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": os.environ["AUDIO_BUCKET"], "Key": item["answerAudioKey"]},
            ExpiresIn=PRESIGN_SECONDS,
        )
        audio = [{"seq": 1, "url": url}]
    return response(200, {
        "askId": ask_id,
        "status": _STATUS.get(item.get("status"), "processing"),
        "transcript": item.get("transcript"),
        "answer": item.get("answer"),
        "audio": audio,
        "error": item.get("error"),
        "timings": item.get("timings", {}),
    })
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_result.py -q`
Expected: 6 passed。

- [ ] **Step 4: コミット**

```bash
cd $BE
git add src/handlers/result.py tests/test_result.py
git commit -m "feat: return ask status, answer and presigned audio"
```

---

### Task 12: worker

**Files:**
- Create: `src/handlers/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `lib.store`・`lib.geo.heading_degrees`・`lib.prompt.build_prompt`/`agent_location`・`lib.agent.AgentError`/`AgentReply`/`invoke`・`lib.speech.synthesize`・`lib.transcribe.transcribe_pcm`・`lib.address.describe_location`・`handlers.common`
- Produces: `handlers.worker.Steps`（dataclass: `transcribe: Callable[[bytes], str]`・`describe_location: Callable[[float, float], str | None]`・`invoke_agent: Callable[[str, dict | None, str], AgentReply]`・`synthesize: Callable[[str, str], str]`・`now: Callable[[], datetime]`）、`process(user: str, ask_id: str, steps: Steps) -> None`、`handler(event, context) -> None`。完了したら `status="completed"`・`transcript`（音声のときだけ）・`answer`・`answerAudioKey`・`address`・`headingDegrees`・`usage`・`modelId`・`tools`・`timings`（`transcribedAt`（音声のときだけ）・`factsAt`・`agentFirstEventAt`・`agentDoneAt`・`synthesizedAt`）を書く。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_worker.py`:

```python
"""Tests for the worker pipeline with stubbed steps and moto storage."""
from datetime import datetime, timedelta, timezone

from handlers import worker
from handlers.common import iso
from lib import store
from lib.agent import AgentError, AgentReply

USER, ASK, CID = "rider01", "11111111-1111-4111-8111-111111111111", "33333333-3333-4333-8333-333333333333"
T0 = datetime(2026, 10, 16, 3, 0, tzinfo=timezone.utc)
HERE = {"latitude": 35.6812, "longitude": 139.7671}
SOUTH = {"latitude": 35.68066, "longitude": 139.7671, "at": "2026-10-16T02:59:50.000Z"}


class Recorder:
    def __init__(self, transcript="右手の山は？", answer="愛鷹山です。", agent_error=None, tts_error=None, stt_error=None):
        self.calls = []
        self.transcript, self.answer = transcript, answer
        self.agent_error, self.tts_error, self.stt_error = agent_error, tts_error, stt_error
        self.clock = T0

    def now(self):
        self.clock += timedelta(seconds=1)
        return self.clock

    def transcribe(self, audio):
        self.calls.append(("transcribe", len(audio)))
        if self.stt_error:
            raise self.stt_error
        return self.transcript

    def describe_location(self, lat, lon):
        self.calls.append(("address", lat, lon))
        return "東京都千代田区丸の内"

    def invoke_agent(self, prompt, location, session_id):
        self.calls.append(("agent", prompt, location, session_id))
        if self.agent_error:
            raise self.agent_error
        return AgentReply(answer=self.answer, usage={"inputTokens": 5}, model_id="m", tools=["nearby_places"], first_event_at=None)

    def synthesize(self, ask_id, text):
        self.calls.append(("tts", ask_id, text))
        if self.tts_error:
            raise self.tts_error
        return f"answers/{ask_id}.mp3"

    def steps(self):
        return worker.Steps(self.transcribe, self.describe_location, self.invoke_agent, self.synthesize, self.now)


def put(aws, audio=True, **extra):
    item = {**store.ask_key(USER, ASK), "askId": ASK, "userName": USER, "conversationId": CID,
            "conversationStartedAt": iso(T0 - timedelta(minutes=10)), "status": "pending", "receivedAt": iso(T0),
            "inputType": "audio" if audio else "text", "location": HERE, "headingSample": SOUTH, "timings": {"receivedAt": iso(T0)}, **extra}
    if audio:
        item["audioKey"] = f"audio/{ASK}.pcm"
        aws.s3.put_object(Bucket=aws.bucket, Key=item["audioKey"], Body=b"\x00\x00" * 8000)
    else:
        item.setdefault("question", "富士山の高さは？")
    store.create_ask(item)


def kinds(rec):
    return [c[0] for c in rec.calls]


def audio_exists(aws):
    return aws.s3.list_objects_v2(Bucket=aws.bucket, Prefix="audio/").get("KeyCount", 0) > 0


def test_audio_happy_path(aws):
    put(aws)
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())
    item = store.get_ask(USER, ASK)
    assert kinds(rec) == ["transcribe", "address", "agent", "tts"]
    assert item["status"] == "completed" and item["transcript"] == "右手の山は？" and item["answer"] == "愛鷹山です。"
    assert item["answerAudioKey"] == f"answers/{ASK}.mp3" and item["usage"] == {"inputTokens": 5} and item["modelId"] == "m"
    assert item["address"] == "東京都千代田区丸の内" and round(item["headingDegrees"]) == 0
    assert set(item["timings"]) >= {"receivedAt", "transcribedAt", "factsAt", "agentDoneAt", "synthesizedAt"}
    assert not audio_exists(aws)


def test_agent_gets_facts_location_and_session(aws):
    put(aws)
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())
    _, prompt, location, session = next(c for c in rec.calls if c[0] == "agent")
    assert "現在地の住所: 東京都千代田区丸の内" in prompt
    assert "会話の最初の質問から約10分後" in prompt
    assert prompt.endswith("質問: 右手の山は？")
    assert location["headingDegrees"] == 0.0 and session == CID


def test_text_question_skips_transcription(aws):
    put(aws, audio=False)
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())
    item = store.get_ask(USER, ASK)
    assert kinds(rec) == ["address", "agent", "tts"]
    assert item["status"] == "completed" and "transcript" not in item and "transcribedAt" not in item["timings"]


def test_no_speech(aws):
    put(aws)
    rec = Recorder(transcript="")
    worker.process(USER, ASK, rec.steps())
    item = store.get_ask(USER, ASK)
    assert item["status"] == "failed" and item["error"] == "no_speech" and item["transcript"] == ""
    assert kinds(rec) == ["transcribe"]
    assert not audio_exists(aws)


def test_transcribe_failure_deletes_audio(aws):
    put(aws)
    rec = Recorder(stt_error=RuntimeError("stream broke"))
    worker.process(USER, ASK, rec.steps())
    item = store.get_ask(USER, ASK)
    assert item["status"] == "failed" and item["error"] == "transcribe_failed"
    assert not audio_exists(aws)


def test_agent_failure(aws):
    put(aws)
    rec = Recorder(agent_error=AgentError("agent_failed: empty answer"))
    worker.process(USER, ASK, rec.steps())
    item = store.get_ask(USER, ASK)
    assert item["status"] == "failed" and item["error"] == "agent_failed" and item["transcript"] == "右手の山は？"
    assert "tts" not in kinds(rec)


def test_tts_failure_keeps_answer(aws):
    put(aws)
    rec = Recorder(tts_error=RuntimeError("polly down"))
    worker.process(USER, ASK, rec.steps())
    item = store.get_ask(USER, ASK)
    assert item["status"] == "failed" and item["error"] == "tts_failed" and item["answer"] == "愛鷹山です。"
    assert "answerAudioKey" not in item


def test_no_location_means_no_address_lookup(aws):
    put(aws, audio=False, location=None, headingSample=None)
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())
    _, prompt, location, _ = next(c for c in rec.calls if c[0] == "agent")
    assert "address" not in kinds(rec) and location is None and "現在地: 不明" in prompt


def test_second_delivery_does_nothing(aws):
    put(aws, audio=False)
    rec = Recorder()
    worker.process(USER, ASK, rec.steps())
    worker.process(USER, ASK, rec.steps())
    assert kinds(rec).count("agent") == 1 and kinds(rec).count("tts") == 1


def test_handler_reads_sqs_records(aws, monkeypatch):
    put(aws, audio=False)
    rec = Recorder()
    monkeypatch.setattr(worker, "DEFAULT_STEPS", rec.steps())
    worker.handler({"Records": [{"body": f'{{"userName": "{USER}", "askId": "{ASK}"}}'}]}, None)
    assert store.get_ask(USER, ASK)["status"] == "completed"
```

Run: `cd $BE && env/bin/pytest tests/test_worker.py -q`
Expected: `ImportError: cannot import name 'worker' from 'handlers'`

- [ ] **Step 2: 実装する**

`src/handlers/worker.py`:

```python
"""SQS worker: transcribe -> settle facts -> agent -> speech, one ask at a time (spec §6.2)."""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from handlers.common import iso, log, parse_iso, utc_now
from lib import address, agent, clients, speech, store, transcribe
from lib.agent import AgentError, AgentReply
from lib.geo import heading_degrees
from lib.prompt import agent_location, build_prompt


@dataclass
class Steps:
    transcribe: Callable[[bytes], str]
    describe_location: Callable[[float, float], Optional[str]]
    invoke_agent: Callable[[str, Optional[dict], str], AgentReply]
    synthesize: Callable[[str, str], str]
    now: Callable[[], datetime]


DEFAULT_STEPS = Steps(transcribe.transcribe_pcm, address.describe_location, agent.invoke, speech.synthesize, utc_now)


def _durations(timings: dict) -> dict:
    order = ["receivedAt", "transcribedAt", "factsAt", "agentDoneAt", "synthesizedAt"]
    present = [(k, parse_iso(timings[k])) for k in order if timings.get(k)]
    result = {f"{a}->{b}": int((tb - ta).total_seconds() * 1000) for (a, ta), (b, tb) in zip(present, present[1:])}
    if len(present) > 1:
        result["total"] = int((present[-1][1] - present[0][1]).total_seconds() * 1000)
    return result


def _take_audio(key: str) -> bytes:
    bucket = os.environ["AUDIO_BUCKET"]
    try:
        return clients.s3().get_object(Bucket=bucket, Key=key)["Body"].read()
    finally:
        # The recording is only kept long enough to transcribe it (US-C-06.003).
        try:
            clients.s3().delete_object(Bucket=bucket, Key=key)
        except Exception as error:  # noqa: BLE001 - the 1-day lifecycle rule removes it anyway
            log({"event": "audio_delete_failed", "error": type(error).__name__})


def process(user: str, ask_id: str, steps: Steps) -> None:
    item = store.claim_ask(user, ask_id)
    if item is None:
        log({"event": "ask_skipped", "askId": ask_id})
        return
    timings = dict(item.get("timings") or {})
    outcome: dict = {}

    def mark(name: str) -> None:
        timings[name] = iso(steps.now())

    def finish(status: str, error: Optional[str] = None, **fields) -> None:
        outcome.update(fields)
        store.update_ask(user, ask_id, {"status": status, "error": error, "timings": timings, **fields})
        log({"event": "ask_done", "askId": ask_id, "status": status, "error": error, "inputType": item.get("inputType"),
             "durationsMs": _durations(timings), "usage": fields.get("usage"), "modelId": fields.get("modelId"),
             "tools": fields.get("tools")})

    question = item.get("question")
    transcript: Optional[str] = None
    if item.get("audioKey"):
        try:
            transcript = steps.transcribe(_take_audio(item["audioKey"]))
        except Exception as error:  # noqa: BLE001 - reported as transcribe_failed
            mark("transcribedAt")
            log({"event": "transcribe_error", "askId": ask_id, "error": type(error).__name__})
            finish("failed", "transcribe_failed")
            return
        mark("transcribedAt")
        if not transcript:
            finish("failed", "no_speech", transcript="")
            return
        question = transcript

    received_at = parse_iso(item["receivedAt"])
    location = item.get("location")
    heading = heading_degrees(location, item.get("headingSample"), received_at)
    place = steps.describe_location(location["latitude"], location["longitude"]) if location else None
    elapsed = (received_at - parse_iso(item["conversationStartedAt"])).total_seconds() if item.get("conversationStartedAt") else None
    prompt = build_prompt(question, received_at, location, place, heading, elapsed)
    mark("factsAt")
    facts = {"transcript": transcript, "address": place, "headingDegrees": round(heading, 1) if heading is not None else None}

    try:
        reply = steps.invoke_agent(prompt, agent_location(location, heading), item["conversationId"])
    except AgentError as error:
        mark("agentDoneAt")
        log({"event": "agent_error", "askId": ask_id, "error": str(error)})
        finish("failed", "agent_failed", **facts)
        return
    if reply.first_event_at is not None:
        timings["agentFirstEventAt"] = iso(datetime.fromtimestamp(reply.first_event_at, timezone.utc))
    mark("agentDoneAt")
    answered = {**facts, "answer": reply.answer, "usage": reply.usage, "modelId": reply.model_id, "tools": reply.tools}

    try:
        key = steps.synthesize(ask_id, reply.answer)
    except Exception as error:  # noqa: BLE001 - the App reads the answer with device TTS
        mark("synthesizedAt")
        log({"event": "tts_error", "askId": ask_id, "error": type(error).__name__})
        finish("failed", "tts_failed", **answered)
        return
    mark("synthesizedAt")
    finish("completed", None, answerAudioKey=key, **answered)


def handler(event, context):
    for record in event.get("Records", []):
        message = json.loads(record["body"])
        process(message["userName"], message["askId"], DEFAULT_STEPS)
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest -q`
Expected: Task 1〜12 のすべてが PASS。

- [ ] **Step 4: コミット**

```bash
cd $BE
git add src/handlers/worker.py tests/test_worker.py
git commit -m "feat: process asks through transcription, facts, agent and speech"
```

---

### Task 13: SAM テンプレートと API 仕様

**Files:**
- Create: `template.yaml`、`samconfig.toml`、`openapi.yaml`
- Test: `tests/test_openapi.py`

**Interfaces:**
- Consumes: Task 1〜12 のハンドラ（`handlers.health.handler`・`handlers.ask.handler`・`handlers.result.handler`・`handlers.worker.handler`）
- Produces: スタック `stack-trv2-dev-backend` の定義。出力 `ApiUrl`・`ApiKeyId`。`openapi.yaml`（App ↔ Backend の正本）。

- [ ] **Step 1: API 仕様のテストを書く**

`tests/test_openapi.py`:

```python
"""The OpenAPI document is valid and covers the implemented routes."""
from pathlib import Path

import yaml
from openapi_spec_validator import validate

SPEC = yaml.safe_load((Path(__file__).parent.parent / "openapi.yaml").read_text(encoding="utf-8"))


def test_is_valid_openapi():
    validate(SPEC)


def test_routes():
    assert set(SPEC["paths"]) == {"/health", "/asks", "/asks/{askId}"}
    assert set(SPEC["paths"]["/asks"]) == {"post"}
    assert set(SPEC["paths"]["/asks/{askId}"]) == {"get"}


def test_error_reasons_match_contract():
    reasons = SPEC["components"]["schemas"]["AskResult"]["properties"]["error"]["enum"]
    assert set(reasons) - {None} == {"no_speech", "transcribe_failed", "agent_failed", "tts_failed"}
```

Run: `cd $BE && env/bin/pytest tests/test_openapi.py -q`
Expected: `FileNotFoundError`（`openapi.yaml`）

- [ ] **Step 2: API 仕様を書く**

`openapi.yaml`:

```yaml
openapi: 3.0.3
info:
  title: TouringProjectV2 Backend API
  version: 1.0.0
  description: >
    App ↔ Backend の約束の正本（親リポジトリ docs/07_units_contracts.md UC-4・UC-5）。
    /health 以外は x-api-key（接続キー）と x-user-name（英小文字と数字の3〜20文字）が要る。
servers:
  - url: https://{apiId}.execute-api.ap-northeast-1.amazonaws.com/Prod
    variables:
      apiId:
        default: example
security:
  - ApiKey: []
paths:
  /health:
    get:
      summary: 死活の確認
      security: []
      responses:
        "200":
          description: 動いている
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [ok]
  /asks:
    post:
      summary: 質問を受け付ける（回答は GET /asks/{askId} で取りに行く）
      parameters:
        - $ref: "#/components/parameters/UserName"
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/AskRequest"
      responses:
        "202":
          description: 受け付けた
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/AskAccepted"
        "400":
          $ref: "#/components/responses/BadRequest"
        "403":
          description: 接続キーが無効
        "429":
          description: 流量の制限
  /asks/{askId}:
    get:
      summary: 質問の状態と回答
      parameters:
        - $ref: "#/components/parameters/UserName"
        - name: askId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: 状態
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/AskResult"
        "400":
          $ref: "#/components/responses/BadRequest"
        "403":
          description: 接続キーが無効
        "404":
          description: 無い（他のユーザーの質問も無いものとして扱う）
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
                    enum: [not_found]
components:
  securitySchemes:
    ApiKey:
      type: apiKey
      in: header
      name: x-api-key
  parameters:
    UserName:
      name: x-user-name
      in: header
      required: true
      schema:
        type: string
        pattern: "^[a-z0-9]{3,20}$"
  responses:
    BadRequest:
      description: 入力が不正
      content:
        application/json:
          schema:
            type: object
            required: [error, message]
            properties:
              error:
                type: string
                enum: [bad_request]
              message:
                type: string
  schemas:
    Point:
      type: object
      required: [latitude, longitude]
      properties:
        latitude:
          type: number
          minimum: -90
          maximum: 90
        longitude:
          type: number
          minimum: -180
          maximum: 180
    AskRequest:
      type: object
      description: audio と text はどちらか一方。不正な location・headingSample は無いものとして扱う。
      properties:
        audio:
          type: string
          format: byte
          description: PCM（16kHz・モノラル・16bit リトルエンディアン）の base64。0.25〜60秒。
        text:
          type: string
          minLength: 1
          maxLength: 500
        location:
          allOf:
            - $ref: "#/components/schemas/Point"
          nullable: true
        headingSample:
          nullable: true
          description: 方位の材料。少し前の位置と、その時刻（タイムゾーン付き）。2分より古いものは使わない。
          allOf:
            - $ref: "#/components/schemas/Point"
            - type: object
              required: [at]
              properties:
                at:
                  type: string
                  format: date-time
        conversationId:
          type: string
          format: uuid
          nullable: true
          description: 会話を続けるときだけ送る（小文字）。
    AskAccepted:
      type: object
      required: [askId, conversationId, conversationExpiresAt]
      properties:
        askId:
          type: string
          format: uuid
        conversationId:
          type: string
          format: uuid
        conversationExpiresAt:
          type: string
          format: date-time
          description: この時刻を過ぎたら App は conversationId を捨てる。
    AskResult:
      type: object
      required: [askId, status, audio, timings]
      properties:
        askId:
          type: string
          format: uuid
        status:
          type: string
          enum: [processing, completed, failed]
        transcript:
          type: string
          nullable: true
        answer:
          type: string
          nullable: true
          description: tts_failed のときも入る（端末の音声合成で読む）。
        audio:
          type: array
          description: 読み上げ音声。seq の順に鳴らす。URL は10分有効。
          items:
            type: object
            required: [seq, url]
            properties:
              seq:
                type: integer
              url:
                type: string
                format: uri
        error:
          type: string
          nullable: true
          enum: [no_speech, transcribe_failed, agent_failed, tts_failed, null]
        timings:
          type: object
          additionalProperties:
            type: string
            format: date-time
```

- [ ] **Step 3: テストを通す**

Run: `cd $BE && env/bin/pytest tests/test_openapi.py -q`
Expected: 3 passed。

- [ ] **Step 4: SAM テンプレートと設定を書く**

`template.yaml`:

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Transform: AWS::Serverless-2016-10-31
Description: TouringProjectV2 backend (slice 1) - accept asks, process them through the agent, return answers.

Parameters:
  Environment:
    Type: String
    Default: dev
    AllowedValues: [dev, prod]
  AgentRuntimeArn:
    Type: AWS::SSM::Parameter::Value<String>
    Default: /trv2/dev/agent-runtime-arn
    Description: Name of the SSM parameter (Tokyo) holding the agent runtime ARN; written by the Agent deploy.
  AgentRegion:
    Type: String
    Default: us-east-1
  ConversationResetParameter:
    Type: String
    Default: /trv2/dev/conversation-reset-minutes
  DailyQuota:
    Type: Number
    Default: 3000
    Description: Requests per key per day. One question is one POST plus up to about 70 polls.
  ThrottleRate:
    Type: Number
    Default: 5
  ThrottleBurst:
    Type: Number
    Default: 10

Globals:
  Function:
    Runtime: python3.13
    Architectures: [arm64]
    CodeUri: src/
    MemorySize: 256
    Timeout: 10
    Environment:
      Variables:
        TABLE_NAME: !Ref RecordsTable
        AUDIO_BUCKET: !Ref AudioBucket

Resources:
  RestApi:
    Type: AWS::Serverless::Api
    Properties:
      Name: !Sub apigw-trv2-${Environment}-main
      StageName: Prod
      Auth:
        ApiKeyRequired: true

  HealthFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub lambda-trv2-${Environment}-health
      Handler: handlers.health.handler
      Events:
        Health:
          Type: Api
          Properties:
            RestApiId: !Ref RestApi
            Path: /health
            Method: get
            Auth:
              ApiKeyRequired: false

  AskFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub lambda-trv2-${Environment}-ask
      Handler: handlers.ask.handler
      MemorySize: 512
      Timeout: 15
      Environment:
        Variables:
          QUEUE_URL: !Ref AskQueue
          CONVERSATION_RESET_PARAMETER: !Ref ConversationResetParameter
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref RecordsTable
        - SQSSendMessagePolicy:
            QueueName: !GetAtt AskQueue.QueueName
        - Statement:
            - Effect: Allow
              Action: s3:PutObject
              Resource: !Sub ${AudioBucket.Arn}/audio/*
            - Effect: Allow
              Action: ssm:GetParameter
              Resource: !Sub arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter${ConversationResetParameter}
      Events:
        Ask:
          Type: Api
          Properties:
            RestApiId: !Ref RestApi
            Path: /asks
            Method: post

  ResultFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub lambda-trv2-${Environment}-result
      Handler: handlers.result.handler
      Policies:
        - DynamoDBReadPolicy:
            TableName: !Ref RecordsTable
        - Statement:
            - Effect: Allow
              Action: s3:GetObject
              Resource: !Sub ${AudioBucket.Arn}/answers/*
      Events:
        Result:
          Type: Api
          Properties:
            RestApiId: !Ref RestApi
            Path: /asks/{askId}
            Method: get

  WorkerFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub lambda-trv2-${Environment}-worker
      Handler: handlers.worker.handler
      MemorySize: 512
      Timeout: 120
      Environment:
        Variables:
          AGENT_ARN: !Ref AgentRuntimeArn
          AGENT_REGION: !Ref AgentRegion
          GEO_REGION: !Ref AWS::Region
          POLLY_VOICE_ID: Kazuha
          POLLY_VOLUME: "+6dB"
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref RecordsTable
        - Statement:
            - Effect: Allow
              Action: [s3:GetObject, s3:DeleteObject]
              Resource: !Sub ${AudioBucket.Arn}/audio/*
            - Effect: Allow
              Action: s3:PutObject
              Resource: !Sub ${AudioBucket.Arn}/answers/*
            - Effect: Allow
              Action: transcribe:StartStreamTranscription
              Resource: "*"
            - Effect: Allow
              Action: geo-places:ReverseGeocode
              Resource: "*"
            - Effect: Allow
              Action: polly:SynthesizeSpeech
              Resource: "*"
            - Effect: Allow
              Action: bedrock-agentcore:InvokeAgentRuntime
              Resource:
                - !Ref AgentRuntimeArn
                - !Sub ${AgentRuntimeArn}/*
      Events:
        Queue:
          Type: SQS
          Properties:
            Queue: !GetAtt AskQueue.Arn
            BatchSize: 1

  AskQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: !Sub sqs-trv2-${Environment}-ask
      VisibilityTimeout: 180
      MessageRetentionPeriod: 3600
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt AskDeadLetterQueue.Arn
        maxReceiveCount: 2

  AskDeadLetterQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: !Sub sqs-trv2-${Environment}-ask-dlq
      MessageRetentionPeriod: 1209600

  RecordsTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: !Sub dynamodb-trv2-${Environment}-records
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: pk
          AttributeType: S
        - AttributeName: sk
          AttributeType: S
      KeySchema:
        - AttributeName: pk
          KeyType: HASH
        - AttributeName: sk
          KeyType: RANGE
      PointInTimeRecoverySpecification:
        PointInTimeRecoveryEnabled: true

  AudioBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub s3-trv2-${Environment}-audio-${AWS::AccountId}
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      LifecycleConfiguration:
        Rules:
          - Id: DeleteAudioAfterOneDay
            Status: Enabled
            ExpirationInDays: 1

  ApiUsagePlan:
    Type: AWS::ApiGateway::UsagePlan
    DependsOn: RestApiProdStage
    Properties:
      UsagePlanName: !Sub usageplan-trv2-${Environment}-main
      ApiStages:
        - ApiId: !Ref RestApi
          Stage: Prod
      Quota:
        Limit: !Ref DailyQuota
        Period: DAY
      Throttle:
        RateLimit: !Ref ThrottleRate
        BurstLimit: !Ref ThrottleBurst

  ApiKey:
    Type: AWS::ApiGateway::ApiKey
    DependsOn: RestApiProdStage
    Properties:
      Name: !Sub apikey-trv2-${Environment}-main
      Description: The shared connection key typed into the App. Read its value with the command in README.md.
      Enabled: true

  ApiUsagePlanKey:
    Type: AWS::ApiGateway::UsagePlanKey
    Properties:
      KeyId: !Ref ApiKey
      KeyType: API_KEY
      UsagePlanId: !Ref ApiUsagePlan

Outputs:
  ApiUrl:
    Value: !Sub https://${RestApi}.execute-api.${AWS::Region}.amazonaws.com/Prod
  ApiKeyId:
    Value: !Ref ApiKey
```

`samconfig.toml`:

```toml
version = 0.1

[default.global.parameters]
stack_name = "stack-trv2-dev-backend"

[default.build.parameters]
cached = true

[default.deploy.parameters]
region = "ap-northeast-1"
capabilities = "CAPABILITY_IAM"
resolve_s3 = true
s3_prefix = "stack-trv2-dev-backend"
confirm_changeset = false
fail_on_empty_changeset = false
parameter_overrides = "Environment=dev"
```

- [ ] **Step 5: テンプレートを検査する**

```bash
cd $BE && AWS_PROFILE=touring sam validate --lint --region ap-northeast-1
env/bin/pytest -q
```
Expected: `template.yaml is a valid SAM Template`。テストはすべて PASS。

- [ ] **Step 6: コミット**

```bash
cd $BE
git add template.yaml samconfig.toml openapi.yaml tests/test_openapi.py
git commit -m "feat: add sam template and openapi document"
```

---

### Task 14: デプロイと通しの確認

**Files:**
- Create: `scripts/smoke.py`、`tests/fixtures/question_16k.pcm`

**Interfaces:**
- Consumes: Task 13 のスタック、Agent（デプロイ済み・SSM `/trv2/dev/agent-runtime-arn`）
- Produces: デプロイ済みの API。計画4（App）は `ApiUrl` と API キーの値を使う。

- [ ] **Step 1: 名前の衝突と前提を確かめる**

```bash
export AWS_PROFILE=touring AWS_REGION=ap-northeast-1
aws cloudformation describe-stacks --stack-name stack-trv2-dev-backend 2>&1 | tail -1
aws ssm get-parameter --name /trv2/dev/agent-runtime-arn --query Parameter.Name --output text
aws ssm get-parameter --name /trv2/dev/conversation-reset-minutes 2>&1 | tail -1
for n in health ask result worker; do aws lambda get-function --function-name lambda-trv2-dev-$n 2>&1 | tail -1; done
aws dynamodb describe-table --table-name dynamodb-trv2-dev-records 2>&1 | tail -1
```
Expected: スタック・会話の設定値・Lambda・テーブルは「無い」、Agent の ARN の設定値は `/trv2/dev/agent-runtime-arn`。

- [ ] **Step 2: 会話の設定値を作り、デプロイする**

```bash
aws ssm put-parameter --name /trv2/dev/conversation-reset-minutes --type String --value 15
cd $BE && sam build 2>&1 | tail -2 && sam deploy 2>&1 | tail -15
```
Expected: `Successfully created/updated stack - stack-trv2-dev-backend`。失敗したら、エラーを調べてから直す。

- [ ] **Step 3: 見本の質問の音声を作る**

```bash
cd $BE && mkdir -p tests/fixtures
aws polly synthesize-speech --region ap-northeast-1 --engine neural --voice-id Kazuha --language-code ja-JP \
  --output-format pcm --sample-rate 16000 --text "右手に見える山は何という山ですか" tests/fixtures/question_16k.pcm >/dev/null
ls -l tests/fixtures/question_16k.pcm
```
Expected: 数十 KB の偶数バイトのファイル。

- [ ] **Step 4: 通しの確認のスクリプトを書く**

`scripts/smoke.py`:

```python
"""End-to-end check of the deployed API. Positions are public landmarks only.

Usage: AWS_PROFILE=touring env/bin/python scripts/smoke.py
"""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3

REGION = "ap-northeast-1"
STACK = "stack-trv2-dev-backend"
USER = "smoketest"
TOKYO_STATION = {"latitude": 35.6812, "longitude": 139.7671}
SOUTH_60M = {"latitude": 35.68066, "longitude": 139.7671}
FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "question_16k.pcm"


def stack_outputs() -> dict:
    stack = boto3.client("cloudformation", region_name=REGION).describe_stacks(StackName=STACK)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}


def request(method: str, url: str, key: str | None, user: str | None, body: dict | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["x-api-key"] = key
    if user:
        headers["x-user-name"] = user
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return error.code, {"raw": raw.decode(errors="replace")}


def wait(api: str, key: str, ask_id: str) -> tuple[dict, float]:
    start = time.monotonic()
    while True:
        elapsed = time.monotonic() - start
        status, body = request("GET", f"{api}/asks/{ask_id}", key, USER)
        if status == 200 and body["status"] != "processing":
            return body, elapsed
        if elapsed > 120:
            return body, elapsed
        time.sleep(1 if elapsed < 10 else 2)


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'OK' if ok else 'NG'}] {name} {detail}")
    return ok


def sample(seconds_ago: int) -> dict:
    at = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return {**SOUTH_60M, "at": at.strftime("%Y-%m-%dT%H:%M:%SZ")}


def ask_and_wait(api: str, key: str, body: dict) -> tuple[dict, dict, float]:
    status, accepted = request("POST", f"{api}/asks", key, USER, body)
    if status != 202:
        return accepted, {"status": "post_failed", "http": status}, 0.0
    result, elapsed = wait(api, key, accepted["askId"])
    return accepted, result, elapsed


def main() -> int:
    outputs = stack_outputs()
    api = outputs["ApiUrl"]
    key = boto3.client("apigateway", region_name=REGION).get_api_key(apiKey=outputs["ApiKeyId"], includeValue=True)["value"]
    results = []

    status, body = request("GET", f"{api}/health", None, None)
    results.append(check("health without key", status == 200 and body == {"status": "ok"}))
    status, _ = request("POST", f"{api}/asks", None, USER, {"text": "Q"})
    results.append(check("no key is 403", status == 403, str(status)))
    status, body = request("POST", f"{api}/asks", key, "BAD", {"text": "Q"})
    results.append(check("bad user is 400", status == 400 and body.get("error") == "bad_request", str(status)))

    accepted, result, elapsed = ask_and_wait(api, key, {"text": "富士山の高さは？", "location": TOKYO_STATION, "headingSample": sample(10)})
    ok = result.get("status") == "completed" and bool(result.get("answer")) and len(result.get("audio", [])) == 1
    results.append(check("text question", ok, f"{elapsed:.1f}s answer={result.get('answer')} error={result.get('error')}"))
    if ok:
        with urllib.request.urlopen(result["audio"][0]["url"], timeout=30) as res:
            audio_ok = res.status == 200 and res.headers.get("Content-Type") == "audio/mpeg" and len(res.read()) > 1000
        results.append(check("answer audio download", audio_ok))
    print("      timings:", json.dumps(result.get("timings"), ensure_ascii=False))
    conversation_id = accepted.get("conversationId")
    expires = accepted.get("conversationExpiresAt")
    results.append(check("conversation expiry returned", bool(expires), str(expires)))

    audio_b64 = base64.b64encode(FIXTURE.read_bytes()).decode()
    accepted2, result2, elapsed2 = ask_and_wait(api, key, {"audio": audio_b64, "location": TOKYO_STATION, "headingSample": sample(10), "conversationId": conversation_id})
    ok = result2.get("status") == "completed" and "山" in (result2.get("transcript") or "")
    results.append(check("audio question", ok, f"{elapsed2:.1f}s transcript={result2.get('transcript')} answer={result2.get('answer')}"))
    print("      timings:", json.dumps(result2.get("timings"), ensure_ascii=False))
    results.append(check("same conversation", accepted2.get("conversationId") == conversation_id))

    _, result3, elapsed3 = ask_and_wait(api, key, {"text": "最初に聞いた山の名前をもう一度言って", "location": TOKYO_STATION, "conversationId": conversation_id})
    results.append(check("follow-up answered", result3.get("status") == "completed", f"{elapsed3:.1f}s answer={result3.get('answer')}"))

    status, body = request("GET", f"{api}/asks/{uuid.uuid4()}", key, USER)
    results.append(check("unknown ask is 404", status == 404 and body == {"error": "not_found"}))
    status, _ = request("GET", f"{api}/asks/{accepted.get('askId')}", key, "someoneelse")
    results.append(check("other user's ask is 404", status == 404))

    print(f"{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 通しを確かめる**

```bash
cd $BE && AWS_PROFILE=touring env/bin/python scripts/smoke.py
```
Expected: `12/12 passed`。「follow-up answered」の答えが富士山に触れていることを目で確かめる。音声の質問の `timings` で、`receivedAt` から `synthesizedAt` までが30秒以内であることを確かめる。NG なら CloudWatch の `/aws/lambda/lambda-trv2-dev-worker` の `ask_done`・`*_error` を調べてから直す。

- [ ] **Step 6: ログを確かめる**

```bash
aws logs filter-log-events --log-group-name /aws/lambda/lambda-trv2-dev-worker --filter-pattern '"ask_done"' \
  --query 'events[-3:].message' --output text
```
Expected: `durationsMs`・`usage`・`modelId` を含む1行の JSON が出ている。質問の本文・回答・位置・住所が含まれていない。

- [ ] **Step 7: コミット**

```bash
cd $BE
git add scripts/smoke.py tests/fixtures/question_16k.pcm
git commit -m "test: add smoke check for the deployed backend"
```

---

### Task 15: 文書と契約

**Files:**
- Modify: `Backend/README.md`
- Modify（親）: `docs/07_units_contracts.md`（UC-4・UC-5）、`docs/specs/2026-10-16-slice1-design.md`（§6.3）、submodule の指す先（`Agent`・`Backend`）、各ユニットの `docs-parent/`

**Interfaces:**
- Produces: 計画4（App）が読む契約（`Backend/openapi.yaml` と 07）。

- [ ] **Step 1: `Backend/README.md` を書き直す**

````markdown
# TouringProjectV2_Backend

TouringProjectV2 の API（API Gateway＋Lambda・Python・SAM・`ap-northeast-1`）。
App から質問（PCM の音声か文字）と位置を受け付け、文字起こし・住所と方位の確定・Agent の呼び出し・読み上げ音声の生成を行い、結果を返す。
プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し。編集しない）。

## 構成

| 場所 | 中身 |
|---|---|
| `openapi.yaml` | App ↔ Backend の API 仕様（正本） |
| `template.yaml`・`samconfig.toml` | SAM（スタック `stack-trv2-dev-backend`） |
| `src/handlers/` | `health`・`ask`（`POST /asks`）・`result`（`GET /asks/{askId}`）・`worker`（SQS） |
| `src/lib/` | 入力の検証・方位・プロンプト・住所・記録・会話の時間・Agent・音声合成・文字起こし |
| `scripts/smoke.py` | デプロイ後の通しの確認 |

## 流れ

1. `POST /asks` が入力を検証し、録音を S3（`audio/`・1日で消える）に置き、記録を `pending` で作り、SQS に積む。会話を区切る時刻を SSM `/trv2/dev/conversation-reset-minutes`（既定15・55以下）から求めて返す。
2. worker が受け持ちを獲得し（条件付き書き込み）、文字起こし（ストリーミング）→ 住所（Location Service）・方位・日時 → Agent（us-east-1・`runtimeSessionId` は会話の識別子）→ Polly（Kazuha・DRC と +6dB）の順に処理し、記録を `completed` か `failed` にする。
3. App は `GET /asks/{askId}` をポーリングし、回答の文と音声の署名付き URL（10分有効）を受け取る。

## テスト

```sh
python3 -m venv env && env/bin/pip install -r requirements-dev.txt
env/bin/pytest
```

## デプロイ

前提: Agent がデプロイ済みで、SSM `/trv2/dev/agent-runtime-arn`（東京）がある。

```sh
AWS_PROFILE=touring sam build && AWS_PROFILE=touring sam deploy
AWS_PROFILE=touring env/bin/python scripts/smoke.py
```

接続キー（App の設定に入れる値）は次で読む。表示された値はコミットしない。

```sh
KEY_ID=$(AWS_PROFILE=touring aws cloudformation describe-stacks --region ap-northeast-1 --stack-name stack-trv2-dev-backend \
  --query "Stacks[0].Outputs[?OutputKey=='ApiKeyId'].OutputValue" --output text)
AWS_PROFILE=touring aws apigateway get-api-key --region ap-northeast-1 --api-key "$KEY_ID" --include-value --query value --output text
```

## 運用

- 会話を区切る時間を変える: `aws ssm put-parameter --name /trv2/dev/conversation-reset-minutes --type String --overwrite --value <分>`（60秒以内に反映）
- 段ごとの所要時間: CloudWatch の `/aws/lambda/lambda-trv2-dev-worker` の `ask_done` の行（`durationsMs`）
````

```bash
cd $BE && git add README.md && git commit -m "docs: describe backend structure, flow and deployment"
```

- [ ] **Step 2: 親で作業ブランチを切り、07 を直す**

```bash
cd <親リポジトリ> && git switch -c slice1-plan3
```

`docs/07_units_contracts.md` を Edit する。

- 旧: `- 記録と質問に関わる呼び出しには、ユーザー名を付ける。Backend はユーザー名ごとに記録を分ける。接続キーとユーザー名は独立している。`
  新: `- 記録と質問に関わる呼び出しには、ユーザー名をヘッダ `x-user-name` で付ける（接続キーはヘッダ `x-api-key`）。Backend はユーザー名ごとに記録を分ける。接続キーとユーザー名は独立している。別のユーザー名の記録を求められたら、無いもの（404）として返す。`
- 旧: `- 接続キーが無効なときは、App はすぐに諦めて利用者に知らせる（繰り返さない）。`
  新:
  ```
  - 接続キーが無効なとき（403）は、App はすぐに諦めて利用者に知らせる（繰り返さない）。
  - 入力が不正なときは 400 と `{"error": "bad_request", "message": <理由>}` を返す。
  ```
- 旧: `### 受け付けと回答の受け取り`
  新:
  ```
  ### 受け付けと回答の受け取り

  項目の名前と型の正本は Backend の `openapi.yaml`。`POST /asks` で受け付け（202）、`GET /asks/{askId}` で取りに行く。
  ```
- 旧: `| 質問 | 音声か文字。文字は500字まで。音声は録音の上限の時間（最長60秒）に収まる大きさまで |`
  新: `| 質問 | 音声か文字のどちらか一方。文字は500字まで。音声は PCM（16kHz・モノラル・16bit）の base64 で、0.25〜60秒 |`
- 旧: `| 方位の材料 | 位置の履歴から選んだ過去の1点と、その時刻（方位は Backend が求める） |`
  新: `| 方位の材料 | 位置の履歴から選んだ過去の1点と、その時刻（タイムゾーン付き）。方位は Backend が求める。2分より古い点・5m 未満しか離れていない点では方位なしとする |`

- [ ] **Step 3: 仕様書 §6.3 を直す**

`docs/specs/2026-10-16-slice1-design.md` を Edit する。

- 旧: `### 6.3 API（要点。正本は Backend の OpenAPI）`
  新: `### 6.3 API（要点。正本は Backend の openapi.yaml）`
- 表の `audio` の行の下に `text` の行を足す。旧: `| `audio` | base64 の PCM（16kHz・モノラル・16bit。60秒で約2.6MB まで） |` 新:
  ```
  | `audio` | base64 の PCM（16kHz・モノラル・16bit。60秒で約2.6MB まで） |
  | `text` | 文字の質問（500字まで）。`audio` とどちらか一方。スライス1の App は使わないが、通しの確認に使う |
  ```

- [ ] **Step 4: 検査して写し、submodule を進める**

```bash
cd <親リポジトリ>
python3 scripts/check_links.py docs adr README.md
git diff --exit-code HEAD -- docs/init && echo "docs/init unchanged"
tests/test_sync_docs.sh
scripts/sync-docs.sh App Backend Agent CICD
for u in App Agent CICD; do git -C "$u" add docs-parent && git -C "$u" commit -m "docs: sync parent docs" || true; done
git -C Backend add docs-parent && git -C Backend commit -m "docs: sync parent docs" || true
git add docs/plans/2026-10-16-slice1-plan3-backend.md docs/07_units_contracts.md docs/specs/2026-10-16-slice1-design.md Agent App Backend CICD
git commit -m "docs: define app-backend api details for slice 1"
```
Expected: リンクの切れ 0件、`docs/init unchanged`、`OK: sync-docs`。`Agent` の指す先は Agent の `main`（マージコミット）、`Backend` は `slice1-plan3` の先頭。push はしない。
