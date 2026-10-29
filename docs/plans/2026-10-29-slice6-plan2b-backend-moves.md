# スライス6 計画2b: Backend の移すだけの作り替え 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend の構成の指摘 R11-12・R11-06・R11-07・R11-13（と R4-13 の C）を、振る舞いを変えずに直す。`lib` から `handlers` への逆向きの依存をなくし、「最初に受けた値を残す」手順と質問の記録の形を1か所に置き、`lib/store.py` を記録の種類ごとに分ける。デプロイして smoke を通す。

**Architecture:** 時刻とログの部品を `lib/common.py` へ、走行・地点メモ・質問できなかった地点が共有する検証（`utc_time`・`path_id`）を `lib/request.py` へ移す（Task 1）。地点メモと質問できなかった地点の「最初の値を残す」手順を `lib/placed.py` の `settle_first` に出し、違い（位置を最初の値に残すか）は引数 `keep_first_location` で今のまま残す（Task 2）。質問の記録の作り方と読み出しの形（ポーリングと引き継ぎ）を `lib/asks.py` に置く（Task 3）。`lib/store.py` を `lib/store/` に分け、`__init__.py` が今の名前を読み直す（Task 4）。

**Tech Stack:** Python 3.13・pytest・moto（`Backend/env`）。足す依存は無い。

**Spec:** [docs/specs/2026-10-29-slice6-design.md](../specs/2026-10-29-slice6-design.md) §3（plan 2b）・§4。指摘の本文は [報告 structure.md](../final-review/2026-10-28/structure.md) の R11-12・R11-06・R11-07・R11-13、[backend.md](../final-review/2026-10-28/backend.md) の R4-13。

**確かめたこと（spec §4）:** 構成の指摘で、報告のとおりだった。`lib` が `handlers.common` を読む 3 か所（`conversation.py`・`address.py`・`geo.py`）、時刻の書式 3 か所、状態の対応表が `result.py` と `records.py` に重複、更新の式の組み立て 3 か所、`store.py` 380 行。誤りではない。

**計画を書くときに決めたこと:**

- **振る舞いは変えない。** 完了の判定は、既存のテストが通ること。テストの本体は直さず、移動で変わる import と差し替え先だけを直す（Task 2・3・4 に書いた 5 か所）。
- **R11-06 は `settle_first` だけを出す。** spec §3 の設計では、違いを引数 `consistent_read` と `keep_first_location` で残すとした。計画を書くときに、保存済みの読み方（結果整合か一貫した読み出しか）は「値を決める手順」ではなく store の呼び出し方なので、ハンドラの中に残し、引数にしないと決めた。位置の扱いの違いだけを `keep_first_location` で残す。保存済みの読み方を揃える直し（R4-05）は plan 6（Backend と Agent の残りの不具合）。
- **方位を決める呼び出し**（`ask.py` の受け付けと `worker.py`）は 2 回のまま。`headingSample` を外す Backend #28 のときに 1 か所ずつ直す。
- **`store` の中の名前**: 分けたファイルは `ask_items`・`ride_items`・`conversation_items`・`transcription_items`・`listing`・`_dynamo`。`lib/asks.py`（Task 3）と取り違えないよう、`store` の中には `asks.py` を作らない。
- **テストの `store._sleep` は `store._dynamo._sleep` になる**（待つ関数は `_dynamo` の 2 つの関数が使うため）。
- 計画を書くときに、使い捨ての作業ツリーで次を確かめた: 各 Task のテストは、実装の前に落ち（Task 1・2・3・4 の RED）、実装後に通る。全体は 309 → 310（Task 1）→ 315（Task 2）→ 323（Task 3）→ 360 件（Task 4）。元の `store.py` の定義は、編集した 3 つ（`update_ask`・`put_offline_ask`・`finish_transcription`）を除いて、分けたあとのファイルに一字も変えずに入っている。

## Global Constraints

- 作業するリポジトリは `Backend/` と親。Backend は `main` から `slice6-plan2b` を切る（Task 0）。親は、`slice6-plan2` のまま（plan 2a の文書も同じブランチ）。push・マージは、利用者が明示したときだけ。push の前に `pre-push-secret-scan`。デプロイと smoke は、実行のときに利用者の確認を取ってから行う（Task 6）。
- 作りの決まり: ハンドラは出入りだけ。種類ごとの手順と検証は `lib`。`lib` は `handlers` を読まない（Task 1 のテストが守る）。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。ログに質問文・回答・位置を書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`BE=$ROOT/Backend`。テストは `cd $BE && env/bin/pytest -q`（`env` が無ければ `python3 -m venv env && env/bin/pip install -r requirements-dev.txt`）。AWS は `AWS_PROFILE=touring`。
- エディタの編集は Edit・Write ツールで行う（heredoc や置換スクリプトで書き換えない）。

## Review Focus

- ハンドラの外から見える応答は 1 バイトも変わらない（地点メモ・質問できなかった地点・ポーリング・引き継ぎ）。既存のテスト（`test_notes`・`test_offline`・`test_result`・`test_records`・`test_ask`）が通ることが証拠。Task 2・3 は、共有の関数を直接確かめるテストを足すだけ。
- 地点メモは、PUT のたびに受けた版の位置を使い、質問できなかった地点は最初の版の位置を残す。Task 2 のテスト（`keep_first_location` の 2 通り）が押さえる。引数を取り違えると、既存の `test_offline.test_a_newer_version_keeps_the_first_position` が落ちる。
- 未使用の import が残らない（Task 1〜3 で `address`・`settled_heading`・`iso`・`timezone` を外した）。Task 5 の最後の検査で確かめる。
- SAM が `src/lib/store/` の下のファイルも運ぶ（`CodeUri: src/`）。デプロイ後の smoke が通ることが証拠（Task 6）。
- 時刻の書式（UTC・ミリ秒・`Z`）が 3 か所から 1 か所になる。`updatedAt` の文字列の比べ方に効くので、`test_common`・`test_rides`・`test_notes` の時刻のテストが通ること。

---

## ファイル構成（`Backend/` から）

| パス | 役割 | Task |
|---|---|---|
| `src/lib/common.py`（新） | `utc_now`・`iso`・`parse_iso`・`log` | 1 |
| `src/handlers/common.py` | 応答の形（`response`・`deleted`・`no_content`）。時刻とログは `lib.common` から読み直す | 1 |
| `src/lib/request.py` | `utc_time`・`path_id` を受ける（`rides.py` から） | 1 |
| `src/lib/placed.py`（新） | `settle_first`・`Placed` | 2 |
| `src/lib/asks.py`（新） | `STATUS`・`status`・`new_ask`・`poll_view`・`record_view` | 3 |
| `src/lib/store/`（`store.py` を置き換え） | `_dynamo`・`ask_items`・`ride_items`・`conversation_items`・`transcription_items`・`listing`・`__init__` | 4 |
| `tests/test_layers.py`・`test_placed.py`・`test_asks.py`・`test_store_layout.py`（新） | Task 1〜4 の RED | 1〜4 |
| `docs/08b_backend-design.md`・`Backend/README.md` | 作りの説明 | 5 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Backend でブランチを切り、今のテストを回す**

```bash
cd $BE && git switch main && git pull --ff-only && git switch -c slice6-plan2b
cd $BE && env/bin/pytest -q 2>&1 | tail -1
```

Expected: `309 passed`。

---

### Task 1: 時刻とログを `lib/common.py` へ、共有の検証を `lib/request.py` へ（R11-12・R4-13 の C）

**Files:**
- Create: `src/lib/common.py`、`tests/test_layers.py`
- Modify: `src/handlers/common.py`、`src/lib/conversation.py`・`address.py`・`geo.py`・`request.py`・`rides.py`・`notes.py`・`offline.py`、`src/handlers/rides.py`・`ask_edit.py`

**Interfaces:**
- Produces: `lib.common.utc_now() -> datetime`・`iso(dt) -> str`・`parse_iso(text) -> datetime`・`log(record) -> None`（`handlers.common` から読み直しても同じ関数）。`lib.request.utc_time(value, field) -> str`・`lib.request.path_id(event, name) -> str`（`lib.rides` からは無くなる）。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_layers.py`:

```python
"""The layers point one way: handlers use lib, never the reverse."""
import pathlib

LIB = pathlib.Path(__file__).resolve().parent.parent / "src" / "lib"


def test_lib_never_imports_handlers():
    offenders = [
        f"{path.name}:{number}"
        for path in sorted(LIB.rglob("*.py"))
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if line.lstrip().startswith(("from handlers", "import handlers"))
    ]
    assert offenders == []
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_layers.py 2>&1 | tail -3`
Expected: `1 failed`（`conversation.py:13`・`address.py:6`・`geo.py:8` が挙がる）。

- [ ] **Step 3: `lib/common.py` を作る**

```python
"""Time and log helpers shared by the handlers and the libraries."""
from __future__ import annotations

import json
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """UTC, millisecond precision, trailing Z."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.astimezone(timezone.utc).microsecond // 1000:03d}Z"


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def log(record: dict) -> None:
    # One JSON line per event. Callers must not pass question text, answers or positions.
    print(json.dumps(record, ensure_ascii=False))
```

`src/handlers/common.py` を、次の全文に置き換える（時刻とログは読み直す。ハンドラの import は変えない）。

```python
"""Helpers shared by the Lambda handlers: the shapes of their responses. Time and log helpers are in lib.common."""
from __future__ import annotations

import json

from lib.common import iso, log, parse_iso, utc_now  # noqa: F401 - handlers import them from here


def response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def deleted() -> dict:
    """410: the record, or its ride, was deleted; the app treats it as sent (slice 3 spec §5.4)."""
    return response(410, {"error": "deleted"})


def no_content() -> dict:
    return {"statusCode": 204, "headers": {}, "body": ""}
```

`lib` の 3 つの import を直す。

- `src/lib/conversation.py` と `src/lib/address.py`: `from handlers.common import log` と `from lib import clients` の 2 行を、`from lib import clients` と `from lib.common import log`（この順）にする。
- `src/lib/geo.py`: `from handlers.common import parse_iso` → `from lib.common import parse_iso`。

- [ ] **Step 4: `utc_time`・`path_id` を `lib/request.py` へ移す**

`src/lib/request.py`:

- import に `from lib.common import iso` を足す（`from typing import Any, Optional` の下に空行を挟んで）。`from datetime import datetime, timezone` は `from datetime import datetime` にする（`timezone` はもう使わない）。
- `heading_sample` の最後の 2 行（`utc = parsed.astimezone(timezone.utc)` と `return {**point, "at": utc.strftime(...)}`）を、`return {**point, "at": iso(parsed)}` の 1 行にする。
- `heading_sample` と `body_json` のあいだに、次の 2 つを足す。

```python
def utc_time(value: Any, field: str) -> str:
    """A time with its time zone, normalised to UTC with milliseconds so that stored values compare as text."""
    if not isinstance(value, str):
        raise BadRequest(f"{field} must be a date-time with a time zone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BadRequest(f"{field} must be a date-time with a time zone") from None
    if parsed.tzinfo is None:
        raise BadRequest(f"{field} must be a date-time with a time zone")
    return iso(parsed)


def path_id(event: dict, name: str) -> str:
    """A UUID from the path (rideId, noteId, askId); a bad one is the sender's mistake, so 400."""
    value = (event.get("pathParameters") or {}).get(name) or ""
    if not UUID_RE.match(value):
        raise BadRequest(f"{name} must be a lowercase UUID")
    return value
```

`src/lib/rides.py`: `utc_time` と `path_id` の定義（docstring ごと）を消し、`from datetime import datetime, timezone` の行を消し、`from lib.request import BadRequest, UUID_RE, body_json, finite_number` を `from lib.request import BadRequest, body_json, finite_number, path_id, utc_time` にする（`ride_id`・`_segments` などがこの 2 つを使い続ける）。

呼び出し側を直す。

- `src/lib/notes.py`: `from lib.request import BadRequest, body_json, heading_sample, heading_value, position` の末尾に `, utc_time` を足し、`from lib.rides import utc_time` の行を消す。
- `src/lib/offline.py`: `from lib.request import UUID_RE, BadRequest, body_json, heading_sample, heading_value, position` の末尾に `, utc_time` を足し、`from lib.rides import utc_time` の行を消す。
- `src/handlers/rides.py`: `from lib import address, notes, rides, store` → `from lib import address, notes, request, rides, store`。`rides.path_id(` を `request.path_id(` に（2 か所）。
- `src/handlers/ask_edit.py`: `from lib import address, offline, rides, store` → `from lib import address, offline, request, rides, store`。`rides.path_id(` を `request.path_id(` に（1 か所）。

- [ ] **Step 5: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -2`
Expected: `310 passed`。

- [ ] **Step 6: コミット**

```bash
cd $BE && git add src/lib/common.py src/handlers/common.py src/lib/conversation.py src/lib/address.py src/lib/geo.py src/lib/request.py src/lib/rides.py src/lib/notes.py src/lib/offline.py src/handlers/rides.py src/handlers/ask_edit.py tests/test_layers.py
cd $BE && git commit -m "refactor: move the time and log helpers to lib.common and the shared validation to lib.request, so lib no longer imports handlers"
```

---

### Task 2: 「最初に受けた値を残す」手順を `lib/placed.py` へ（R11-06）

**Files:**
- Create: `src/lib/placed.py`、`tests/test_placed.py`
- Modify: `src/handlers/rides.py`（`_note`）、`src/handlers/ask_edit.py`（`_offline`）、`tests/test_offline.py`・`tests/test_notes.py`（差し替え先）

**Interfaces:**
- Consumes: Task 1 の `lib.common.parse_iso`（ハンドラが `at` に使う）。
- Produces: `placed.Placed(location, heading, address)`（`frozen` の dataclass）、`placed.settle_first(stored, location, degrees, sample, at, *, keep_first_location) -> Placed`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_placed.py`:

```python
"""What a record keeps from the first version that had a value (slice 3 spec §6.2, Backend #17, #21, #31)."""
from datetime import datetime, timezone

from lib import address, placed

AT = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
HERE = {"latitude": 35.0, "longitude": 139.0}
THERE = {"latitude": 36.0, "longitude": 140.0}


def _describe(monkeypatch, calls):
    monkeypatch.setattr(address, "describe_location", lambda lat, lon: calls.append((lat, lon)) or f"{lat},{lon}")


def test_a_new_record_takes_everything_from_the_version_it_gets(monkeypatch):
    calls = []
    _describe(monkeypatch, calls)
    got = placed.settle_first(None, HERE, 90.04, None, AT, keep_first_location=True)
    assert got == placed.Placed(HERE, 90.0, "35.0,139.0")
    assert calls == [(35.0, 139.0)]


def test_a_heading_and_a_place_that_are_stored_are_kept(monkeypatch):
    calls = []
    _describe(monkeypatch, calls)
    stored = {"location": HERE, "headingDegrees": 10.0, "address": "stored place"}
    got = placed.settle_first(stored, THERE, 200.0, None, AT, keep_first_location=False)
    assert got == placed.Placed(THERE, 10.0, "stored place")
    assert calls == []


def test_the_position_is_kept_only_when_asked_to(monkeypatch):
    _describe(monkeypatch, [])
    stored = {"location": HERE, "address": "stored place"}
    assert placed.settle_first(stored, THERE, None, None, AT, keep_first_location=True).location == HERE
    assert placed.settle_first(stored, THERE, None, None, AT, keep_first_location=False).location == THERE
    # A first version without a position gives it up to a later one, as the heading does.
    assert placed.settle_first({}, THERE, None, None, AT, keep_first_location=True).location == THERE


def test_the_place_is_looked_up_for_the_position_that_is_kept(monkeypatch):
    calls = []
    _describe(monkeypatch, calls)
    stored = {"location": HERE}
    got = placed.settle_first(stored, THERE, None, None, AT, keep_first_location=True)
    assert got.address == "35.0,139.0" and calls == [(35.0, 139.0)]


def test_no_position_means_no_place_and_no_heading_from_a_sample(monkeypatch):
    _describe(monkeypatch, [])
    assert placed.settle_first(None, None, None, None, AT, keep_first_location=False) == placed.Placed(None, None, None)
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_placed.py 2>&1 | tail -3`
Expected: 収集で `ImportError`（`lib.placed` が無い）。

- [ ] **Step 3: `lib/placed.py` を作る**

```python
"""What a record keeps from the first version of it that had a value: the heading, the place and, for an unreached
ask, the position (slice 3 spec §6.2, Backend #17, #21, #31). Point memos and unreached asks both settle these."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from lib import address
from lib.geo import settled_heading


@dataclass(frozen=True)
class Placed:
    location: Optional[dict]
    heading: Optional[float]
    address: Optional[str]


def settle_first(stored: Optional[dict], location: Optional[dict], degrees: Optional[float], sample: Optional[dict],
                 at: datetime, *, keep_first_location: bool) -> Placed:
    """The heading and the place of the stored record are kept; they are worked out only while it has none (a failed
    place lookup, or a first version without a heading, is tried again by a later one). The position is kept the same
    way for an unreached ask; a point memo takes the one it is sent with. The heading is worked out from the position
    of the version at hand, the place from the position that is kept."""
    kept = stored or {}
    heading = kept.get("headingDegrees")
    if heading is None:
        heading = settled_heading(degrees, location, sample, at)
    where = (kept.get("location") or location) if keep_first_location else location
    place = kept.get("address") or (address.describe_location(where["latitude"], where["longitude"]) if where else None)
    return Placed(where, heading, place)
```

- [ ] **Step 4: 2 つのハンドラを付け替える**

`src/handlers/rides.py` の `_note`: `else:` の中の、`heading = (stored or {}).get("headingDegrees")` から `kept = {...}` の閉じ `}` までを、次に置き換える。

```python
        # The heading and the place are settled on the first PUT that has one (slice 3 spec §6.2, Backend #17). A
        # point memo takes the position it is sent with; a stored copy is read eventually consistently (review R4-05).
        got = placed.settle_first(stored, note.location, note.heading, note.heading_sample, parse_iso(note.at),
                                  keep_first_location=False)
        kept = {
            "at": note.at,
            "location": got.location,
            "text": note.text,
            "updatedAt": note.updated_at,
            "address": got.address,
            "headingDegrees": got.heading,
            "savedAt": iso(utc_now()),
        }
```

import は `from lib import address, notes, request, rides, store` → `from lib import notes, placed, request, rides, store`、`from lib.geo import settled_heading` の行を消す。

`src/handlers/ask_edit.py` の `_offline`: `else:` の中の、最初のコメント（`# Taken from the first PUT that has a heading, apart from the position (Backend #31) ...`）から `kept = {...}` の閉じ `}` までを、次に置き換える。

```python
        # The heading, the position and the place are each taken from the first PUT that has one (Backend #21, #31): a
        # first PUT with a position but no heading keeps its position, and a later one gives the heading.
        got = placed.settle_first(stored, unreached.location, unreached.heading, unreached.heading_sample,
                                  parse_iso(unreached.asked_at), keep_first_location=True)
        kept = {
            "userName": user,
            "rideId": unreached.ride_id,
            # Named as for the asks the Backend takes in, so that every ask reads back alike.
            "receivedAt": unreached.asked_at,
            "location": got.location,
            "updatedAt": unreached.updated_at,
            "address": got.address,
            "headingDegrees": got.heading,
            "savedAt": iso(utc_now()),
        }
```

import は `from lib import address, offline, request, rides, store` → `from lib import offline, placed, request, rides, store`、`from lib.geo import settled_heading` の行を消す。

テストの差し替え先（住所の引き当ての関数。どちらも同じ `lib.address` のモジュールを指す）を直す。

- `tests/test_offline.py`: `from lib import store` → `from lib import address, store`。`monkeypatch.setattr(ask_edit.address, "describe_location", ...)` の 2 か所を `monkeypatch.setattr(address, "describe_location", ...)` に。
- `tests/test_notes.py`: `from lib import store` → `from lib import address, store`。`monkeypatch.setattr(rides.address, "describe_location", ...)` の 2 か所を `monkeypatch.setattr(address, "describe_location", ...)` に。

- [ ] **Step 5: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -2`
Expected: `315 passed`。

- [ ] **Step 6: コミット**

```bash
cd $BE && git add src/lib/placed.py src/handlers/rides.py src/handlers/ask_edit.py tests/test_placed.py tests/test_offline.py tests/test_notes.py
cd $BE && git commit -m "refactor: settle a point memo's and an unreached ask's first-seen heading, position and place in one place"
```

---

### Task 3: 質問の記録の形を `lib/asks.py` へ（R11-07・R4-13 の C）

**Files:**
- Create: `src/lib/asks.py`、`tests/test_asks.py`
- Modify: `src/handlers/ask.py`・`result.py`、`src/lib/records.py`、`tests/test_openapi.py`

**Interfaces:**
- Consumes: Task 1 の `lib.common.iso`。
- Produces: `asks.STATUS`（保存した状態 → 返す状態の対応表）、`asks.status(item) -> str`、`asks.new_ask(user, ask_id, ask, conversation_id, started_at, now) -> dict`（`audioKey` は含まない）、`asks.poll_view(item, ask_id, audio) -> dict`、`asks.record_view(item) -> dict`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_asks.py`:

```python
"""One ask record, read back two ways: by polling and by taking over (07 UC-5, UC-7)."""
import pytest

from lib import asks

ITEM = {
    "askId": "11111111-1111-4111-8111-111111111111",
    "status": "completed",
    "receivedAt": "2026-10-16T12:00:00.000Z",
    "address": "東京都千代田区",
    "headingDegrees": 90.0,
    "transcript": "ここはどこ",
    "answer": "千代田区です。",
}


@pytest.mark.parametrize("stored", ["pending", "processing", "completed", "failed", "offline", "unknown"])
def test_both_reads_give_the_same_status_for_the_same_record(stored):
    item = {**ITEM, "status": stored}
    assert asks.poll_view(item, ITEM["askId"], [])["status"] == asks.record_view(item)["status"] == asks.status(item)


def test_both_reads_agree_on_what_the_device_keeps():
    poll, record = asks.poll_view(ITEM, ITEM["askId"], []), asks.record_view(ITEM)
    for field in ["askedAt", "address", "headingDegrees", "transcript", "answer", "error"]:
        assert poll[field] == record[field], field


def test_an_unknown_stored_status_reads_as_processing():
    assert asks.status({"status": "unknown"}) == "processing"
    assert asks.status({}) == "processing"
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_asks.py 2>&1 | tail -3`
Expected: 収集で `ImportError`（`lib.asks` が無い）。

- [ ] **Step 3: `lib/asks.py` を作る**

```python
"""An ask record: how it is made when the question is accepted (POST /asks) and how it is read back, by polling
(GET /asks/{askId}) and by taking over (GET /records). The shape of the record is settled here (07 UC-5, UC-7)."""
from __future__ import annotations

from datetime import datetime

from lib import store
from lib.common import iso
from lib.geo import settled_heading
from lib.request import AskInput

# An unreached ask is never processed (slice 4 spec §4.4); it is reported as such (Backend #25).
STATUS = {"pending": "processing", "processing": "processing", "completed": "completed", "failed": "failed",
          "offline": "offline"}


def status(item: dict) -> str:
    return STATUS.get(item.get("status"), "processing")


def new_ask(user: str, ask_id: str, ask: AskInput, conversation_id: str, started_at: str, now: datetime) -> dict:
    """The record of an ask that has just been accepted, before it is queued."""
    return {
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
        # Settled now: an ask that fails before the agent never gets the worker's settled heading (Backend #29).
        "headingDegrees": settled_heading(ask.heading, None, None, now),
        "volumeDb": ask.volume_db,
        "rideId": ask.ride_id,
        "timings": {"receivedAt": iso(now)},
    }


def poll_view(item: dict, ask_id: str, audio: list) -> dict:
    """The ask as the app polls it; audio is the presigned answer, already made."""
    return {
        "askId": ask_id,
        "status": status(item),
        "transcript": item.get("transcript"),
        "answer": item.get("answer"),
        "audio": audio,
        "error": item.get("error"),
        "timings": item.get("timings", {}),
        # What the device keeps with the ask (slice 2 spec §5.2, §6.1).
        "askedAt": item.get("receivedAt"),
        "address": item.get("address"),
        "headingDegrees": item.get("headingDegrees"),
    }


def record_view(item: dict) -> dict:
    """The ask as GET /records reads it back, for taking over on another device."""
    timings = item.get("timings") or {}
    # An answer the rider could hear: completed, or text whose speech failed (read with the device's TTS).
    answered = status(item) == "completed" or (item.get("error") == "tts_failed" and bool(item.get("answer")))
    conversation_id = item.get("conversationId")
    return {
        "kind": "ask",
        "askId": item["askId"],
        "status": status(item),
        "askedAt": item.get("receivedAt"),
        "question": item.get("question"),
        "transcript": item.get("transcript"),
        "answer": item.get("answer"),
        "error": item.get("error"),
        "answeredAt": (timings.get("synthesizedAt") or timings.get("agentDoneAt")) if answered else None,
        "location": item.get("location"),
        "address": item.get("address"),
        "headingDegrees": item.get("headingDegrees"),
        "inputType": item.get("inputType"),
        "conversationId": conversation_id,
        # The conversation breaks just before its first ask (US-C-03.004).
        "newConversation": conversation_id is not None and item.get("conversationStartedAt") == item.get("receivedAt"),
        "rideId": item.get("rideId"),
        "memo": item.get("memo"),
        "memoUpdatedAt": item.get("memoUpdatedAt"),
        # Only an unreached ask carries the time the app changed it (slice 4 spec §6.1).
        "updatedAt": item.get("updatedAt"),
    }
```

- [ ] **Step 4: 3 つのファイルを付け替える**

`src/handlers/result.py`:

- `from lib import clients, store` → `from lib import asks, clients, store`。
- `# An unreached ask is never processed ...` のコメントと `_STATUS = {...}`（3 行）を消す。
- 最後の `return response(200, {...})` の全体（`"askId"` から `"headingDegrees"` までの辞書）を、`return response(200, asks.poll_view(item, ask_id, audio))` の 1 行にする。

`src/lib/records.py`:

- `from lib.request import BadRequest` の上に `from lib import asks` を足す。
- `# As GET /asks/{askId} answers ...` のコメントと `_ASK_STATUS = {...}`（3 行）を消す。
- `view()` の `return _ask(item)` を `return asks.record_view(item)` にする。
- 末尾の `def _ask(item: dict) -> dict:` の全体を消す。

`src/handlers/ask.py`:

- `from lib import clients, conversation, store` → `from lib import asks, clients, conversation, store`。`from lib.geo import settled_heading` の行を消す。
- `item = {` から閉じの `}` までの辞書（`**store.ask_key(user, ask_id)` から `"timings": {"receivedAt": iso(now)},` まで）を、次の 1 行にする。

```python
    item = asks.new_ask(user, ask_id, ask, conversation_id, started_at, now)
```

`tests/test_openapi.py`: `import yaml` と `from openapi_spec_validator import validate` の下に空行を挟んで `from lib import asks` を足し、`result._STATUS.values()` と `records._ASK_STATUS.values()` を `asks.STATUS.values()` に（2 か所）。

- [ ] **Step 5: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -2`
Expected: `323 passed`。

- [ ] **Step 6: コミット**

```bash
cd $BE && git add src/lib/asks.py src/handlers/ask.py src/handlers/result.py src/lib/records.py tests/test_asks.py tests/test_openapi.py
cd $BE && git commit -m "refactor: make an ask record, and read it back for polling and for taking over, in one place"
```

---

### Task 4: `lib/store.py` を記録の種類ごとに分ける（R11-13・R4-13 の C）

**Files:**
- Create: `src/lib/store/__init__.py`・`_dynamo.py`・`ask_items.py`・`ride_items.py`・`conversation_items.py`・`transcription_items.py`・`listing.py`、`tests/test_store_layout.py`
- Delete: `src/lib/store.py`（`git rm`）
- Modify: `tests/test_rides.py`・`tests/test_store.py`（差し替え先）

**Interfaces:**
- Consumes: なし（Task 1〜3 と独立）。
- Produces: `lib.store` は今の名前をすべて読み直す（`NAMES`。下のテストが一覧）。`lib.store._dynamo._sleep`（待つ関数）・`_dynamo._MARK_READS`・`_dynamo._set_clause(values) -> (expression, names, placeholders)`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_store_layout.py`:

```python
"""lib.store keeps the names the handlers and tests use, and keeps DynamoDB's mechanics apart from the records."""
import importlib

import pytest

from lib import store

NAMES = [
    "Deleted", "ask_key", "claim_ask", "claim_transcription", "conversation_started_at", "create_ask",
    "create_transcription", "delete_ask", "delete_note", "delete_ride", "deleted_key", "discard_ask",
    "finish_transcription", "get_ask", "get_note", "get_transcription", "has_deletion_mark", "mark_deleted",
    "note_key", "put_ask_memo", "put_note", "put_offline_ask", "put_ride", "put_route_chunk", "query_records",
    "ride_key", "route_key", "transcription_key", "update_ask",
]


@pytest.mark.parametrize("name", NAMES)
def test_the_store_keeps_its_names(name):
    assert hasattr(store, name)


@pytest.mark.parametrize("module", ["_dynamo", "ask_items", "ride_items", "conversation_items", "transcription_items",
                                    "listing"])
def test_the_store_is_split_by_kind_of_record(module):
    importlib.import_module(f"lib.store.{module}")


def test_the_retry_waits_live_with_the_dynamodb_mechanics():
    from lib.store import _dynamo

    assert store._MARK_READS == _dynamo._MARK_READS and callable(_dynamo._sleep)


def test_the_set_clause_names_and_numbers_every_field():
    from lib.store._dynamo import _set_clause

    expression, names, values = _set_clause({"status": "done", "text": "こんにちは"})
    assert expression == "SET #k0 = :v0, #k1 = :v1"
    assert names == {"#k0": "status", "#k1": "text"}
    assert values == {":v0": "done", ":v1": "こんにちは"}
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $BE && env/bin/pytest -q tests/test_store_layout.py 2>&1 | tail -3`
Expected: 失敗（`lib.store.<module>` が無い 6 件・`_dynamo` が無い 2 件。名前を保つ 29 件は今の `store.py` で通る）。

- [ ] **Step 3: 元の `store.py` を分ける**

`git rm` はまだ打たない（元の行番号を読むため）。次の 7 ファイルを作り、`src/lib/store.py`（元は 380 行）の定義を、**一字も変えずに**写す。行範囲は元の `store.py` のもの。

**`src/lib/store/_dynamo.py`** — 先頭は次のとおり。

```python
"""DynamoDB's mechanics under the records: values in and out of items, the deletion marks, the transactions that
refuse a write to a deleted record, and the retries on a transaction in progress."""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Optional

from botocore.exceptions import ClientError

from lib import clients

_CONDITION_FAILED = "ConditionalCheckFailedException"
_CANCELLED = "TransactionCanceledException"
_CONFLICT = "TransactionConflictException"
# A write that meets a transaction on the same item fails at once; botocore does not retry it (Backend #18).
_CONFLICT_TRIES = 3
# Reads of deletion marks left unprocessed are tried again up to this many reads in all (Backend #30).
_MARK_READS = 5
_sleep: Callable[[float], None] = time.sleep
```

そのあとに、元の `_Conflict`（28〜29）・`Deleted`（32〜33）・`_to_item`（36〜38）・`_drop_none`（41〜46）・`_from_item`（49〜56）を、続けて写し、次の新しい関数を置き、`deleted_key`（59〜61）・`has_deletion_mark`（64〜80）・`_retrying_conflicts`（83〜94）・`mark_deleted`（97〜101）・`_write_unless_deleted`（104〜129）・`_claim`（169〜183）を写す。定義のあいだは空行 2 つ。

```python
def _set_clause(values: dict) -> tuple:
    """(expression, names, values) for SET #k0 = :v0, ... over the converted item values."""
    names = {f"#k{i}": key for i, key in enumerate(values)}
    expression = "SET " + ", ".join(f"#k{i} = :v{i}" for i in range(len(values)))
    return expression, names, {f":v{i}": value for i, value in enumerate(values.values())}
```

**`src/lib/store/conversation_items.py`**

```python
"""Conversations: when the first question of one arrived."""
from __future__ import annotations

from datetime import datetime

from botocore.exceptions import ClientError

from lib import clients
from lib.store._dynamo import _CONDITION_FAILED

# A conversation lasts 55 minutes at most (07 UC-5); its record only has to outlive that (Backend #2).
CONVERSATION_TTL_SECONDS = 24 * 60 * 60
```

続けて `_conversation_key`（136〜137）・`conversation_started_at`（140〜152）。

**`src/lib/store/ask_items.py`**

```python
"""Asks: a question taken in, worked on by the worker, read back, given a memo, or kept by the app unreached."""
from __future__ import annotations

from typing import Optional

from botocore.exceptions import ClientError

from lib import clients
from lib.store._dynamo import (_CONDITION_FAILED, _claim, _from_item, _retrying_conflicts, _set_clause, _to_item,
                               _write_unless_deleted, deleted_key, mark_deleted)
```

続けて `ask_key`（132〜133）・`create_ask`（155〜156）・`discard_ask`（159〜161）・`claim_ask`（164〜166）・`update_ask`（186〜205。下の編集あり）・`put_ask_memo`（208〜216）・`put_offline_ask`（219〜234。下の編集あり）・`get_ask`（237〜239）・`delete_ask`（311〜317）。

編集 1（`update_ask`）: `names = {...}` と `expression = "SET " + ...` の 2 行を `expression, names, placeholders = _set_clause(values)` の 1 行にし、`update_item(...)` の `ExpressionAttributeValues={f":v{i}": value for ...}` を `ExpressionAttributeValues=placeholders,` にする。

編集 2（`put_offline_ask`）: `names = {...}` の行を `expression, names, placeholders = _set_clause(values)` にし、`"UpdateExpression": "SET " + ", ".join(...)` を `"UpdateExpression": expression,` に、`"ExpressionAttributeValues": {**{f":v{i}": ...}, ":offline": "offline", ":u": fields["updatedAt"]},`（2 行）を `"ExpressionAttributeValues": {**placeholders, ":offline": "offline", ":u": fields["updatedAt"]},` にする。

**`src/lib/store/ride_items.py`**

```python
"""Rides with their route chunks and point memos, and the deletion of a ride with everything under it."""
from __future__ import annotations

from typing import Optional

from lib import clients
from lib.store._dynamo import _from_item, _retrying_conflicts, _to_item, _write_unless_deleted, deleted_key, mark_deleted
```

続けて `ride_key`（242〜243）・`route_key`（246〜248）・`note_key`（251〜253）・`get_note`（256〜258）・`put_note`（261〜268）・`put_ride`（271〜278）・`put_route_chunk`（281〜284）・`_query_keys`（287〜301）・`_delete_all`（304〜308）・`delete_note`（320〜322）・`delete_ride`（325〜337）。

**`src/lib/store/transcription_items.py`**

```python
"""Transcriptions: the recording of a point memo, turned into text only (07 UC-6)."""
from __future__ import annotations

from typing import Optional

from lib import clients
from lib.store._dynamo import _claim, _from_item, _set_clause, _to_item
```

続けて `transcription_key`（354〜355）・`create_transcription`（358〜359）・`claim_transcription`（362〜364）・`finish_transcription`（367〜375。編集: `names = {...}` の行を `expression, names, placeholders = _set_clause(values)` にし、`UpdateExpression="SET " + ...` を `UpdateExpression=expression,` に、`ExpressionAttributeValues={f":v{i}": ...}` を `ExpressionAttributeValues=placeholders,` にする）・`get_transcription`（378〜380）。

**`src/lib/store/listing.py`**

```python
"""A page of a user's records, for taking over on another device."""
from __future__ import annotations

from typing import Optional

from lib import clients
from lib.store._dynamo import _from_item
```

続けて `query_records`（340〜351）。

**`src/lib/store/__init__.py`**

```python
"""Records in one DynamoDB table: pk USER#<name>, sk ASK#<id>, CONV#<id>, RIDE#<id>, RIDE#<id>#ROUTE#<seq>,
RIDE#<id>#NOTE#<id>, DELETED#<KIND>#<id> or TRANSCRIPTION#<id>. The handlers use these names; where they live is
split by kind of record, and DynamoDB's mechanics are in _dynamo."""
from lib.store._dynamo import _MARK_READS, Deleted, deleted_key, has_deletion_mark, mark_deleted  # noqa: F401
from lib.store.ask_items import (ask_key, claim_ask, create_ask, delete_ask, discard_ask, get_ask,  # noqa: F401
                                 put_ask_memo, put_offline_ask, update_ask)
from lib.store.conversation_items import CONVERSATION_TTL_SECONDS, conversation_started_at  # noqa: F401
from lib.store.listing import query_records  # noqa: F401
from lib.store.ride_items import (delete_note, delete_ride, get_note, note_key, put_note, put_ride,  # noqa: F401
                                  put_route_chunk, ride_key, route_key)
from lib.store.transcription_items import (claim_transcription, create_transcription, finish_transcription,  # noqa: F401
                                            get_transcription, transcription_key)
```

写し終えたら、元を外す: `cd $BE && git rm -q src/lib/store.py`。

- [ ] **Step 4: 移したコードが変わっていないことを確かめる（読むだけ）**

元の `store.py`（`git show main:src/lib/store.py`）の定義それぞれが、新しいファイルのどれかに、編集した 3 つ（`update_ask`・`put_offline_ask`・`finish_transcription`）を除いて、一字も変えずに入っていることを確かめる。

```bash
cd $BE && git show main:src/lib/store.py > /tmp/trv2-store-orig.py && env/bin/python - <<'EOF'
import ast, glob
orig = open("/tmp/trv2-store-orig.py").read()
lines = orig.splitlines()
new = "\n".join(open(p).read() for p in glob.glob("src/lib/store/*.py"))
edited = {"update_ask", "put_offline_ask", "finish_transcription"}
bad = []
for node in ast.parse(orig).body:
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name not in edited:
        text = "\n".join(lines[node.lineno - 1:node.end_lineno])
        if text not in new:
            bad.append(node.name)
print("missing or changed:", bad)
EOF
```

Expected: `missing or changed: []`。

- [ ] **Step 5: テストの差し替え先を直す**

- `tests/test_rides.py`: `from lib.store import _from_item` → `from lib.store._dynamo import _from_item`。
- `tests/test_store.py`: `monkeypatch.setattr(store, "_sleep", waits.append)` → `monkeypatch.setattr(store._dynamo, "_sleep", waits.append)`（`no_wait` の fixture の中の 1 行）。

- [ ] **Step 6: 通ることを確かめる**

Run: `cd $BE && env/bin/pytest -q 2>&1 | tail -2`
Expected: `360 passed`。

- [ ] **Step 7: 未使用の import が残っていないことを確かめる**

```bash
cd $BE && env/bin/python - <<'EOF'
import ast, glob
for p in sorted(glob.glob("src/**/*.py", recursive=True)):
    if p.endswith("__init__.py"):
        continue
    text = open(p).read()
    tree = ast.parse(text)
    imported = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                imported[(a.asname or a.name).split(".")[0]] = n.lineno
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                imported[a.asname or a.name] = n.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for name, line in imported.items():
        if name not in used and name != "annotations" and "noqa" not in text.splitlines()[line - 1]:
            print(p, line, name)
EOF
```

Expected: 何も出ない。

- [ ] **Step 8: コミット**

```bash
cd $BE && git add src/lib/store tests/test_store_layout.py tests/test_rides.py tests/test_store.py
cd $BE && git commit -m "refactor: split lib/store.py by kind of record, with DynamoDB's mechanics in _dynamo and one helper for the SET clauses"
```

---

### Task 5: 文書と全体の確かめ

**Files:**
- Modify: `docs/08b_backend-design.md`（親）、`Backend/README.md`
- 写し: `scripts/sync-docs.sh`

- [ ] **Step 1: 08b と README の説明を直す**

`docs/08b_backend-design.md` の §1 の箇条（「経路ごとに Lambda を分け、…入力の検証と記録の読み書きは共通の部品（`src/lib/`）に置く。」）を、次にする。

```
- 経路ごとに Lambda を分け、権限をその経路に要るものだけにする。ハンドラは出入りだけにして、入力の検証・記録の読み書き・種類ごとの手順（最初に受けた値を残す・質問の記録の形と読み出し）は共通の部品（`src/lib/`）に置く。`lib` は `handlers` を読まない。
```

`Backend/README.md` の構成の表の `src/lib/` の行を、次にする。

```
| `src/lib/` | 入力の検証（質問と音声は `request`・走行とメモは `rides`・地点メモは `notes`・質問できなかった地点は `offline`。時刻の正規化 `utc_time` とパスの ID `path_id` は `request`）・時刻とログ（`common`）・方位（`geo`）・プロンプト・住所・最初に受けた値を残す手順（`placed`）・質問の記録の形と読み出し（`asks`）・記録（`store/`。DynamoDB の仕組みは `_dynamo`、種類ごとに `ask_items`・`ride_items`・`conversation_items`・`transcription_items`・`listing`）・引き継ぎで読み出す形（`records`）・会話の時間・Agent・音声合成・文字起こし |
```

- [ ] **Step 2: 写してコミットする**

```bash
cd $ROOT && ./scripts/sync-docs.sh Android Backend Agent CICD
cd $ROOT && git status --short
cd $BE && git add README.md docs-parent && git commit -m "docs: describe the new layout of lib in the README and sync the parent's docs"
cd $ROOT && git add docs/08b_backend-design.md && git commit -m "docs: describe the handlers as in-and-out only and lib as the home of the per-kind steps (slice 6 plan 2b)"
```

Android・Agent・CICD の `docs-parent/` が変わっていたら、それぞれの `main` に直接コミットする（PROJECT.md の「前提」。Android は plan 2a のブランチに入れるので、2a より先なら `main` に）。

- [ ] **Step 3: 全体の確かめ**

```bash
cd $BE && env/bin/pytest -q 2>&1 | tail -1
cd $BE && cfn-lint template.yaml && echo "cfn-lint OK"
```

Expected: `360 passed`・`cfn-lint OK`（`cfn-lint` が無ければ、飛ばしてよい。`test_template.py` が通っている）。

- [ ] **Step 4: PROJECT.md を更新して親でコミットする**

plan 表の 2b の行を「実装済み（確認待ち: デプロイと smoke）」にし、「次にやること」に 2b のデプロイと smoke（Task 6）を足す。親の submodule の指す先は、Backend のブランチの先頭に進める。

```bash
cd $ROOT && git add PROJECT.md Backend && git commit -m "docs: record slice 6 plan 2b as implemented, awaiting the deploy and smoke"
```

---

### Task 6: デプロイと smoke（利用者の確認を取ってから）

デプロイは AWS に触れ、smoke は Agent に質問を投げる費用がかかる。実行のときに利用者に確認する。

- [ ] **Step 1: 利用者の確認を取る**

「Backend をデプロイして smoke を回します（質問の通しで LLM を数回呼びます）。よいですか」と聞く。

- [ ] **Step 2: デプロイする**

Run: `cd $BE && AWS_PROFILE=touring sam build && AWS_PROFILE=touring sam deploy`
Expected: `Successfully created/updated stack`。profile が使えないときは利用者に聞く。

- [ ] **Step 3: smoke を回す**

Run: `cd $BE && AWS_PROFILE=touring env/bin/python scripts/smoke.py`
Expected: すべての項目が通る（前回は 40/40）。デプロイの直後に新しい経路だけが 403 なら、1分ほど待って回し直す。通らなかったら `superpowers:systematic-debugging`。

- [ ] **Step 4: PROJECT.md を更新して親でコミットする**

plan 表の 2b の行を「✅ 完了（デプロイ済み・Backend の smoke N/N。振る舞いは変えていない）」にする。

```bash
cd $ROOT && git add PROJECT.md && git commit -m "docs: record slice 6 plan 2b as deployed with the smoke run passing"
```
