# スライス6 計画2a: Android の移すだけの作り替え 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Android の構成の指摘 R10-05・R10-11・R10-09・R10-07・R10-08 を、振る舞いを変えずに直す。パッケージの循環 6 組を 2 組にし、Backend を呼ぶ口を1つにし、`RideDatabase.kt`（729 行）を分ける。

**Architecture:** 共有の窓口（経路・録音・合図・位置・ポーリング）を `ask` から使う側の `audio`・`recordings`・`location`・`api` へ移す（Task 2）。文字の質問のシートの状態を `ask` へ、メモの長さの決まりを `ride` へ移す（Task 3）。`TakeoverStore` が受けるクラウドの記録を `sync` の型で包み、`store` が `api` を読まないようにする（Task 4）。`BackendAccess` を `api` に作り、`AppGraph` と SC-13 の5か所が使う（Task 5）。`RideDatabase.kt` を Entity・DAO・Migration のファイルに分ける（Task 6）。

**Tech Stack:** Kotlin 2.3.20・Compose BOM 2026.03.01・Room 2.8.4（版6のまま）・Robolectric 4.16（SDK 35）。足す依存は無い。

**Spec:** [docs/specs/2026-10-29-slice6-design.md](../specs/2026-10-29-slice6-design.md) §3（plan 2a）・§4。指摘の本文は [報告 structure.md](../final-review/2026-10-28/structure.md) の R10-05・R10-11・R10-09・R10-07・R10-08。

**確かめたこと（spec §4）:** 構成の指摘で、報告のとおりだった。パッケージ間の import を数える検査で、2つ組の循環は 6 組（`(root)↔service`・`(root)↔ui`・`ask↔audio`・`ask↔location`・`audio↔recordings`・`records↔ride`）。`TextSheet` は `AppGraph` が読み、`memoFits` は `RideController` が読み、`RoomTakeover` は `api.CloudRecord` を読む。`ApiClient` を作る条件は `AppGraph` の4か所と `AppUi` の1か所。誤りではない。

**計画を書くときに決めたこと:**

- **振る舞いは変えない。** 完了の判定は、既存のテストが通ること。テストの本体は直さず、移動で変わる import と、変わった窓口を呼ぶ口（Task 4 の `RoomTakeoverTest` に1つの拡張関数、`TakeoverTest` の作り物の署名）だけを直す。
- **`(root)↔ui` は1本残る。** `MainActivity`→`AppUi`→`AppGraph` の線（`AppUi` が `AppGraph` を丸ごと受ける形）。これは R10-04 の範囲で、spec §2 のとおり後に回す。この plan で消える循環は 4 組。完了の判定は、検査が `(root)↔service` と `(root)↔ui`（1 + 2 imports）の 2 組だけを出すこと。
- **R10-09 は `CloudRecords` で包む。** 報告の案は突き合わせの関数を渡す形だったが、`TakeoverTest` の作り物が受け取ったクラウドの記録を見て確かめているので、記録と時刻を持って `mergeInto(device)` を呼べる型 `CloudRecords`（`sync`）を渡す形にした。`take` の `now` 引数は無くなる。
- **R10-07 の `BackendAccess` は `api` に置く。** `client()`（今のユーザー名）・`client(user)`（SC-18 が読む別の名前）・`clientFor(key, user)`（質問の司令塔と SC-13 の、鍵が決まっているとき）・`apiKey()`・`urlMissing`。呼び出し側ごとの「揃っていなければ null」の条件は、今のまま。`AppGraph.http` は外から使われなくなるので private にする。
- **`MEMO_MAX` と `memoFits` は `ride/MemoLimit.kt`**（`records` が `ride` を読む向きは今もあり、逆をなくす）。`memoFits` は、`records` の private な `characters()` を使わず、`codePointCount` で数える（同じ結果）。
- **パッケージの循環を数える検査を `scripts/package-cycles.py` として足す**（Task 1）。報告の「機械の検査」と同じ数え方で、完了の判定に使う。
- 計画を書くときに、使い捨ての作業ツリーで次を確かめた: 各 Task を当てるたびに `compileDebugKotlin`・`compileDebugUnitTestKotlin`・`compileDebugAndroidTestKotlin` が通り、最後に `clean` から JVM のテスト 721 件（今の 716 件 + `BackendAccessTest` の 5 件）・`assembleDebug`・`assembleRelease`・`scripts/check-release-permissions.sh` が通り、Room のスキーマ JSON（`app/schemas/`）に変更が無い。循環は 6 → 3（Task 2）→ 2（Task 3）。

## Global Constraints

- 作業するリポジトリは `Android/` と親。Android は `main` から `slice6-plan2a` を切る（Task 0）。親は `slice6-plan2` のまま（plan 2b の文書も同じブランチ）。push・マージは、利用者が明示したときだけ。push の前に `pre-push-secret-scan`。
- Room は版6のまま（表を変えない）。`app/schemas/` に差分が出たら、止めて調べる。
- 接続キー・API の URL・アカウント ID・ユーザー名を、コード・文書・コミットに書かない。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`AND=$ROOT/Android`。JVM のテストは `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*クラス名'`（Gradle のビルドキャッシュは共有されるので `--rerun` を付ける）。結果は `app/build/test-results/testDebugUnitTest/*.xml` で読む。コンパイルだけ確かめるときは `./gradlew compileDebugKotlin compileDebugUnitTestKotlin compileDebugAndroidTestKotlin`。
- エディタの編集は Edit・Write ツールで行う。例外は、Task 2 と Task 6 の、確かめた Python の手順（多くのファイルの import の付け替えと、大きなファイルの切り分け）。

## Review Focus

- 質問・試し録り・声の入力が、どれも同じ窓口（`RouteControl`・`Recorder`・`Source`）を、移したあとの `audio` から受ける。`AppGraph` の組み立てと `PressRouter` の振り分けは変わらない（既存の `AskControllerTest`・`TrialTest`・`VoiceInputTest`・`PressRouterTest` が通ること）。
- ポーリングの間隔と打ち切り（1秒→2秒・120秒）が変わらない。`PollingAndConversationTest` が通ること。`ask` から `api` へ移すだけで、定数の値は変えない。
- SC-13 の接続キーの確かめは、保存前の鍵を使う（`clientFor(key, userName)`）。`BackendAccess` は鍵を覚えない。
- クラウドの記録を入れる処理の `now` は、これまでと同じ時刻（`Takeover` が呼ぶ直前に読んだ値）で突き合わせる。`RoomTakeoverTest`・`TakeoverTest` が通ること。
- Room の表・索引・移行が変わらない。`app/schemas/` に差分が無い（Task 6）。

---

## ファイル構成（`Android/app/src/main/java/com/touringproject/v2/` から）

| パス | 役割 | Task |
|---|---|---|
| `Android/scripts/package-cycles.py`（新。`Android/` から） | パッケージの2つ組の循環を数える | 1 |
| `audio/AudioPorts.kt`（新） | `Source`・`TICK_MS`・`pcmDurationMs`・`RouteControl`・`Recorded`・`Recorder`・`Cues`・`AnswerPlayer`・`Speech`・`PcmPlayback` | 2 |
| `recordings/RecordingPorts.kt`（新） | `RecordingMeta`・`RecordingSink` | 2 |
| `location/Positions.kt`（新） | `Positions` | 2 |
| `api/Polling.kt`（`ask/Polling.kt` から移す） | ポーリング | 2 |
| `ask/TextAsk.kt` | `TextSheet`・`after`・`TEXT_ASK_OFFLINE_MESSAGE`（`ui/TextAskSheet.kt` から） | 3 |
| `ride/MemoLimit.kt`（新） | `MEMO_MAX`・`memoFits`（`records/Memos.kt` から） | 3 |
| `sync/Takeover.kt`・`store/RoomTakeover.kt` | `CloudRecords` | 4 |
| `api/BackendAccess.kt`（新）・`AppGraph.kt`・`ui/AppUi.kt` | Backend を呼ぶ口 | 5 |
| `store/Entities.kt`・`AskDao.kt`・`NoteDao.kt`・`RideDao.kt`・`TakeoverDao.kt`・`RideDatabase.kt`・`Migrations.kt` | `RideDatabase.kt` を分ける | 6 |
| `docs/08a_android-design.md`・`Android/README.md` | パッケージの説明 | 7 |

---

### Task 0: 作業ブランチ

- [ ] **Step 1: Android でブランチを切り、今のテストを回す**

```bash
cd $AND && git switch main && git pull --ff-only && git switch -c slice6-plan2a
cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-s6p2a-t0.log 2>&1; tail -3 /tmp/trv2-s6p2a-t0.log | head -1
```

Expected: `BUILD SUCCESSFUL`（716件）。

---

### Task 1: パッケージの循環を数える検査

**Files:**
- Create: `scripts/package-cycles.py`

- [ ] **Step 1: 検査を書く**

`scripts/package-cycles.py`:

```python
"""Lists the packages of app/src/main that import each other (two-way pairs) and counts the imports behind each."""
import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "app/src/main/java/com/touringproject/v2")
BASE = "com.touringproject.v2"
edges = collections.defaultdict(lambda: collections.defaultdict(list))
for path in sorted(ROOT.rglob("*.kt")):
    rel = path.relative_to(ROOT)
    pkg = rel.parts[0] if len(rel.parts) > 1 else "(root)"
    for line in path.read_text().splitlines():
        m = re.match(rf"import {re.escape(BASE)}\.([a-z]+)\.", line)
        target = m.group(1) if m else ("(root)" if re.match(rf"import {re.escape(BASE)}\.[A-Z]", line) else None)
        if target and target != pkg:
            edges[pkg][target].append(f"{rel}: {line[7:]}")
pairs = sorted({tuple(sorted((a, b))) for a in edges for b in edges[a] if a in edges.get(b, {})})
for a, b in pairs:
    print(f"{a} <-> {b}  ({len(edges[a][b])} + {len(edges[b][a])} imports)")
print(f"{len(pairs)} two-way pairs")
```

- [ ] **Step 2: 今の状態を測る**

Run: `cd $AND && python3 scripts/package-cycles.py`
Expected: 6 組（`(root) <-> service`・`(root) <-> ui`・`ask <-> audio`・`ask <-> location`・`audio <-> recordings`・`records <-> ride`）と `6 two-way pairs`。

- [ ] **Step 3: コミット**

```bash
cd $AND && git add scripts/package-cycles.py
cd $AND && git commit -m "chore: add a check that lists the packages importing each other"
```

---

### Task 2: 共有の窓口を使う側へ移す（R10-05）

**Files:**
- Create: `audio/AudioPorts.kt`・`recordings/RecordingPorts.kt`・`location/Positions.kt`
- Move: `ask/Polling.kt` → `api/Polling.kt`
- Modify: `ask/AskPorts.kt`・`ask/Flow.kt`・`ask/AskController.kt`・`recordings/Trial.kt` と、移した記号を import している main・test のファイル（26ファイル）

**Interfaces:**
- Produces: 次の記号は、パッケージだけが変わる（中身は変えない）。`com.touringproject.v2.audio`: `Source`・`TICK_MS`・`pcmDurationMs`・`RouteControl`・`Recorded`・`Recorder`・`Cues`・`AnswerPlayer`・`Speech`・`PcmPlayback`。`…recordings`: `RecordingMeta`・`RecordingSink`。`…location`: `Positions`。`…api`: `POLL_FAST_MS`・`POLL_SLOW_MS`・`FAST_WINDOW_MS`・`POLL_TIMEOUT_MS`・`nextDelay`・`PollOutcome`・`pollUntilDone`・`pollUntil`。

- [ ] **Step 1: 移動の手順を書く（Python。一度だけ使う）**

`$TMP/r1005.py`（`$TMP` はスクラッチ。リポジトリに入れない）:

```python
import pathlib, re, subprocess, sys
ROOT = pathlib.Path(sys.argv[1])
SRC = ROOT / "app/src"
MAIN = SRC / "main/java/com/touringproject/v2"
B = "com.touringproject.v2"

def read(p): return p.read_text()
def write(p, s): p.write_text(s)

ports = read(MAIN / "ask/AskPorts.kt")

def cut(text, start, end_exclusive_marker):
    a = text.index(start); b = text.index(end_exclusive_marker, a)
    return text[:a] + text[b:], text[a:b]

# --- blocks leaving AskPorts.kt
ports, route_block = cut(ports, "interface RouteControl {", "/** What SC-12 shows about each kept recording")
ports, rec_block = cut(ports, "/** What SC-12 shows about each kept recording", "/** Fire and forget: a failure to keep an ask")
ports, pos_block = cut(ports, "interface Positions {", "interface KeepAlive {")
ports, cues_block = cut(ports, "interface Cues {", "/** Where the rider's ride stands")
ports = ports.replace("import com.touringproject.v2.audio.InputDevice\n", "")
write(MAIN / "ask/AskPorts.kt", ports)

meta_a = rec_block.index("/** What SC-12 shows")
meta_b = rec_block.index("/** Fire and forget: a failure here must not end the ask")
meta_block, sink_block = rec_block[meta_a:meta_b], rec_block[meta_b:]
(MAIN / "audio/AudioPorts.kt").write_text(
    "package com.touringproject.v2.audio\n\n"
    "// What the ask loop, SC-12's trial recording and SC-19's voice input use of the audio side: they come in through\n"
    "// these interfaces, so each is testable on the JVM.\n\n"
    "enum class Source { HANDSFREE, SCREEN }\n\n"
    "const val TICK_MS = 250L\n\n"
    "/** 16 kHz mono 16-bit PCM: 32 bytes per millisecond. */\n"
    "fun pcmDurationMs(bytes: Int): Long = bytes / 32L\n\n"
    + "interface RouteControl {" + route_block.split("interface RouteControl {", 1)[1].rstrip() + "\n\n"
    + cues_block.rstrip() + "\n\n"
    "/** Plays recorded PCM; returns when it has been heard or stopped, throws when it cannot be played. */\n"
    "interface PcmPlayback {\n  suspend fun play(pcm: ByteArray)\n  fun stop()\n}\n"
)
(MAIN / "recordings/RecordingPorts.kt").write_text(
    "package com.touringproject.v2.recordings\n\nimport com.touringproject.v2.audio.InputDevice\nimport kotlinx.serialization.Serializable\n\n"
    + meta_block + sink_block.rstrip() + "\n"
)
(MAIN / "location/Positions.kt").write_text("package com.touringproject.v2.location\n\n" + pos_block.rstrip() + "\n")
subprocess.check_call(["git", "mv", str(MAIN / "ask/Polling.kt"), str(MAIN / "api/Polling.kt")], cwd=ROOT)
polling = read(MAIN / "api/Polling.kt")
polling = polling.replace("package com.touringproject.v2.ask\n", "package com.touringproject.v2.api\n")
polling = polling.replace("import com.touringproject.v2.api.ApiError\nimport com.touringproject.v2.api.ApiErrorKind\nimport com.touringproject.v2.api.AskResult\n", "")
write(MAIN / "api/Polling.kt", polling)

# --- remove from old homes
flow = read(MAIN / "ask/Flow.kt"); flow = flow.replace("enum class Source { HANDSFREE, SCREEN }\n\n", ""); write(MAIN / "ask/Flow.kt", flow)
ac = read(MAIN / "ask/AskController.kt")
ac = ac.replace("const val TICK_MS = 250L\n", "").replace("/** 16 kHz mono 16-bit PCM: 32 bytes per millisecond. */\nfun pcmDurationMs(bytes: Int): Long = bytes / 32L\n\n", "")
write(MAIN / "ask/AskController.kt", ac)
tr = read(MAIN / "recordings/Trial.kt")
tr = tr.replace("/** Plays recorded PCM; returns when it has been heard or stopped, throws when it cannot be played. */\ninterface PcmPlayback {\n  suspend fun play(pcm: ByteArray)\n  fun stop()\n}\n\n", "")
write(MAIN / "recordings/Trial.kt", tr)

# --- symbols and their new packages: (new package, old package)
NEW = {}
for s in ["Source", "RouteControl", "Recorder", "Recorded", "Cues", "AnswerPlayer", "Speech", "TICK_MS", "pcmDurationMs"]: NEW[s] = ("audio", "ask")
NEW["PcmPlayback"] = ("audio", "recordings")
for s in ["RecordingMeta", "RecordingSink"]: NEW[s] = ("recordings", "ask")
NEW["Positions"] = ("location", "ask")
for s in ["PollOutcome", "pollUntil", "pollUntilDone", "nextDelay", "POLL_FAST_MS", "POLL_SLOW_MS", "FAST_WINDOW_MS", "POLL_TIMEOUT_MS"]: NEW[s] = ("api", "ask")

def pkg_of(text):
    return re.search(r"^package ([\w.]+)", text, re.M).group(1)

def add_import(text, line):
    if line in text: return text
    lines = text.split("\n")
    idx = [i for i, l in enumerate(lines) if l.startswith("import ")]
    if not idx:
        k = next(i for i, l in enumerate(lines) if l.startswith("package "))
        lines[k + 1:k + 1] = ["", line]
        return "\n".join(lines)
    pos = None
    for i in idx:
        if lines[i] > line:
            pos = i; break
    if pos is None: pos = idx[-1] + 1
    lines.insert(pos, line)
    return "\n".join(lines)

changed = []
for p in sorted(SRC.rglob("*.kt")):
    text = read(p); orig = text
    pkg = pkg_of(text)
    for sym, (newpkg, oldpkg) in NEW.items():          # explicit imports follow the symbol
        old = f"import {B}.{oldpkg}.{sym}\n"
        if old in text:
            text = text.replace(old, f"import {B}.{newpkg}.{sym}\n")
    for sym, (newpkg, oldpkg) in NEW.items():          # a file in the new package needs no import
        if pkg == f"{B}.{newpkg}":
            text = text.replace(f"import {B}.{newpkg}.{sym}\n", "")
    body = "\n".join(l for l in text.split("\n") if not l.startswith("import ") and not l.startswith("package "))
    for sym, (newpkg, oldpkg) in NEW.items():          # a file of the old package used it without an import
        if pkg == f"{B}.{oldpkg}" and re.search(rf"(?<![\w.]){re.escape(sym)}(?![\w])", body) and pkg != f"{B}.{newpkg}":
            text = add_import(text, f"import {B}.{newpkg}.{sym}")
    if text != orig:
        write(p, text); changed.append(str(p.relative_to(ROOT)))
print(len(changed), "files changed")
```

- [ ] **Step 2: 実行して、コンパイルを確かめる**

```bash
cd $AND && python3 $TMP/r1005.py $AND
cd $AND && ./gradlew compileDebugKotlin compileDebugUnitTestKotlin compileDebugAndroidTestKotlin > /tmp/trv2-s6p2a-t2.log 2>&1; tail -3 /tmp/trv2-s6p2a-t2.log | head -1
cd $AND && python3 scripts/package-cycles.py
```

Expected: `26 files changed`・`BUILD SUCCESSFUL`・3 組（`(root) <-> service`・`(root) <-> ui`・`records <-> ride`）。`git status` が、新しいファイル 3 つ（`AudioPorts.kt`・`RecordingPorts.kt`・`Positions.kt`）、`ask/Polling.kt` → `api/Polling.kt` の移動、と 25 ほどの変更を示す。

- [ ] **Step 3: テストを回す**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun > /tmp/trv2-s6p2a-t2t.log 2>&1; tail -3 /tmp/trv2-s6p2a-t2t.log | head -1`
Expected: `BUILD SUCCESSFUL`（716件）。

- [ ] **Step 4: コミット**

```bash
cd $AND && git add app/src
cd $AND && git commit -m "refactor: move the shared audio, recording, position and polling interfaces out of ask into the packages that own them"
```

（`git add app/src` は、この Task で変えたものだけがある状態で使う。`git status` で、`app/src` の外に変更が無いことを先に確かめる。）

---

### Task 3: 文字の質問のシートの状態を `ask` へ、メモの長さの決まりを `ride` へ（R10-11）

**Files:**
- Modify: `ui/TextAskSheet.kt`・`ask/TextAsk.kt`・`AppGraph.kt`・`ui/AppUi.kt`・`test/.../ui/TextAskSheetTest.kt`・`test/.../ui/AppUiTest.kt`
- Create: `ride/MemoLimit.kt`
- Modify: `records/Memos.kt`・`ride/RideController.kt`・`store/RoomAskEdits.kt`・`store/RoomNotes.kt`・`ui/MemoScreen.kt`・`test/.../records/MemosTest.kt`

**Interfaces:**
- Produces: `com.touringproject.v2.ask.TextSheet`・`TextSheet.after(outcome)`・`TEXT_ASK_OFFLINE_MESSAGE`（`ui` から）。`com.touringproject.v2.ride.MEMO_MAX`・`memoFits(memo)`（`records` から）。

- [ ] **Step 1: `TextSheet` を `ask/TextAsk.kt` へ**

`ui/TextAskSheet.kt` の次のブロック（`const val TEXT_ASK_OFFLINE_MESSAGE = ...` の行から、`TextSheet.after` の関数の閉じ `}` まで。3つの定義と、`TextSheet` の説明のコメント）を切り取り、`ask/TextAsk.kt` の末尾に貼る。

```kotlin
const val TEXT_ASK_OFFLINE_MESSAGE = "通信できません"

/**
 * Home's text sheet (slice 5 spec §5.2): whether it is open, what is typed, what it says, and whether a send is under
 * way. AppGraph holds it for the process, so the text stays while SC-03 covers the screen and the sheet comes back with
 * it, and an outcome after the activity was recreated still reaches it.
 */
data class TextSheet(val open: Boolean = false, val text: String = "", val message: String? = null, val sending: Boolean = false)

/** What the sheet becomes once the ask loop has told what became of the text (TextAskOutcome). */
fun TextSheet.after(outcome: TextAskOutcome): TextSheet = when (outcome) {
  TextAskOutcome.SENT -> TextSheet()
  TextAskOutcome.OFFLINE -> copy(sending = false, message = TEXT_ASK_OFFLINE_MESSAGE)
  TextAskOutcome.NOT_TAKEN -> copy(sending = false, message = null)
}
```

import を直す。

- `ui/TextAskSheet.kt`: `import com.touringproject.v2.ask.TextSheet` を足す（`import com.touringproject.v2.ask.TextAskOutcome` の下）。
- `AppGraph.kt`: `import com.touringproject.v2.ui.TextSheet` → `import com.touringproject.v2.ask.TextSheet`（位置は `ask.` の import の並びに合わせる）。
- `ui/AppUi.kt`: `import com.touringproject.v2.ask.TextSheet` と `import com.touringproject.v2.ask.after` を足す。
- `test/.../ui/TextAskSheetTest.kt`: `import com.touringproject.v2.ask.TEXT_ASK_OFFLINE_MESSAGE`・`TextSheet`・`after` を足す。
- `test/.../ui/AppUiTest.kt`: `import com.touringproject.v2.ask.after` を足す。

- [ ] **Step 2: `MEMO_MAX` と `memoFits` を `ride/MemoLimit.kt` へ**

`ride/MemoLimit.kt`:

```kotlin
package com.touringproject.v2.ride

// What a memo may hold, for the ride's own memo and for the memos of asks and point memos (US-D-04.003). Characters are
// counted as code points, as the Backend counts them (Backend #16).

/** US-D-04.003. */
const val MEMO_MAX = 2000

/** True when memo can be kept: none, or up to MEMO_MAX characters. */
fun memoFits(memo: String?): Boolean = memo == null || memo.codePointCount(0, memo.length) <= MEMO_MAX
```

`records/Memos.kt`: `/** US-D-04.003. */` と `const val MEMO_MAX = 2000` の 2 行（と続く空行）、`/** True when memo can be kept ... */` と `fun memoFits(...)` の 2 行（と続く空行）を消し、ファイルの先頭（`package` の次）に `import com.touringproject.v2.ride.MEMO_MAX` を足す（`cutMemo` が使う）。

import を直す。

- `ride/RideController.kt`・`store/RoomAskEdits.kt`・`store/RoomNotes.kt`: `import com.touringproject.v2.records.memoFits` を消す。`RoomAskEdits.kt`・`RoomNotes.kt` には `import com.touringproject.v2.ride.memoFits` を足す（`ride/RideController.kt` は同じパッケージ）。
- `ui/MemoScreen.kt`: `import com.touringproject.v2.records.MEMO_MAX` → `import com.touringproject.v2.ride.MEMO_MAX`。
- `test/.../records/MemosTest.kt`: `import com.touringproject.v2.ride.memoFits` を足す。

- [ ] **Step 3: コンパイルと循環を確かめる**

```bash
cd $AND && ./gradlew compileDebugKotlin compileDebugUnitTestKotlin compileDebugAndroidTestKotlin > /tmp/trv2-s6p2a-t3.log 2>&1; tail -3 /tmp/trv2-s6p2a-t3.log | head -1
cd $AND && python3 scripts/package-cycles.py
```

Expected: `BUILD SUCCESSFUL`・2 組（`(root) <-> service  (4 + 4 imports)`・`(root) <-> ui  (1 + 2 imports)`）。

- [ ] **Step 4: テストを回す**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*MemosTest' --tests '*TextAskSheetTest' --tests '*AppUiTest' --tests '*RideControllerTest' --tests '*RoomNotesTest' --tests '*RoomAskEditsTest' > /tmp/trv2-s6p2a-t3t.log 2>&1; tail -3 /tmp/trv2-s6p2a-t3t.log | head -1`
Expected: `BUILD SUCCESSFUL`。テストのクラス名が無くて `No tests found` になったら、その名前を外して回す。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src
cd $AND && git commit -m "refactor: move the text sheet's state into ask and the memo length rule into ride, so the graph does not read ui and ride does not read records"
```

---

### Task 4: `store` が `api` を読まないようにする（R10-09）

**Files:**
- Modify: `sync/Takeover.kt`・`store/RoomTakeover.kt`・`test/.../sync/TakeoverTest.kt`・`test/.../store/RoomTakeoverTest.kt`

**Interfaces:**
- Produces: `sync.CloudRecords(records: List<CloudRecord>, now: Long)` と `fun mergeInto(device: DeviceRecords): Merge`。`TakeoverStore.take(cloud: CloudRecords, replace: Boolean): TakeResult`（`now` 引数は無くなる）。

- [ ] **Step 1: `sync/Takeover.kt` を直す**

`interface TakeoverStore` の `suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): TakeResult` を `suspend fun take(cloud: CloudRecords, replace: Boolean): TakeResult` にし、`interface TakeoverStore { ... }` の閉じ `}` の次に、次を足す。

```kotlin
/**
 * What the cloud holds, as the store takes it in: it merges it into the device's records inside its transaction, so the
 * store needs none of the cloud's types (slice 4 spec §6.1).
 */
class CloudRecords(val records: List<CloudRecord>, val now: Long) {
  fun mergeInto(device: DeviceRecords): Merge = merge(device, records, now)
}
```

呼び出し側を直す。

- `store.take(records, replace = true, now())` → `store.take(CloudRecords(records, now()), replace = true)`
- `store.take(readAll(userName, null), replace = false, now())` → `store.take(CloudRecords(readAll(userName, null), now()), replace = false)`

- [ ] **Step 2: `store/RoomTakeover.kt` を直す**

- `import com.touringproject.v2.api.CloudRecord` と `import com.touringproject.v2.sync.merge` を消し、`import com.touringproject.v2.sync.CloudRecords` を足す（`BlockReason` の次）。
- `override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): TakeResult` → `override suspend fun take(cloud: CloudRecords, replace: Boolean): TakeResult`。
- `val merged = merge(device(), cloud, now)` → `val merged = cloud.mergeInto(device())`。

- [ ] **Step 3: テストの呼び出し口を直す**

- `test/.../sync/TakeoverTest.kt`: 作り物の `override suspend fun take(cloud: List<CloudRecord>, replace: Boolean, now: Long): TakeResult {` を `override suspend fun take(cloud: CloudRecords, replace: Boolean): TakeResult {` に、`taken += cloud to replace` を `taken += cloud.records to replace` に。
- `test/.../store/RoomTakeoverTest.kt`: `import com.touringproject.v2.api.CloudRecord`（`CloudRoute` の次）と `import com.touringproject.v2.sync.CloudRecords`（`ChunkRange` の次）を足し、`private const val T0 = ...` の直前に次を足す（15 か所の呼び出しは変えない）。

```kotlin
// The calls below give the cloud's records and the time apart, as the store was once called.
private suspend fun RoomTakeover.take(cloud: List<CloudRecord>, replace: Boolean, now: Long) = take(CloudRecords(cloud, now), replace)
```

- [ ] **Step 4: コンパイルとテスト**

```bash
cd $AND && ./gradlew compileDebugKotlin compileDebugUnitTestKotlin compileDebugAndroidTestKotlin > /tmp/trv2-s6p2a-t4.log 2>&1; tail -3 /tmp/trv2-s6p2a-t4.log | head -1
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*TakeoverTest' --tests '*RoomTakeoverTest' > /tmp/trv2-s6p2a-t4t.log 2>&1; tail -3 /tmp/trv2-s6p2a-t4t.log | head -1
cd $AND && grep -rn "import com.touringproject.v2.api" app/src/main/java/com/touringproject/v2/store || echo "store reads no api"
```

Expected: `BUILD SUCCESSFUL` が 2 回・`store reads no api`。

- [ ] **Step 5: コミット**

```bash
cd $AND && git add app/src
cd $AND && git commit -m "refactor: hand the store the cloud's records in a sync type, so store no longer reads api"
```

---

### Task 5: Backend を呼ぶ口を1つにする（R10-07）

**Files:**
- Create: `api/BackendAccess.kt`、`test/.../api/BackendAccessTest.kt`
- Modify: `AppGraph.kt`・`ui/AppUi.kt`

**Interfaces:**
- Produces: `api.BackendAccess(baseUrl: String, http: OkHttpClient, key: () -> String?, userName: () -> String?)`。`val urlMissing: Boolean`・`fun apiKey(): String?`・`fun client(): ApiClient?`・`fun client(user: String?): ApiClient?`・`fun clientFor(key: String, user: String): ApiClient`。`AppGraph.backend`。

- [ ] **Step 1: 失敗するテストを書く**

`app/src/test/java/com/touringproject/v2/api/BackendAccessTest.kt`:

```kotlin
package com.touringproject.v2.api

import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

// The one place a Backend client is made (slice 6 plan 2a): every caller gets none, in the same cases.
class BackendAccessTest {
  private val http = OkHttpClient()

  private fun access(url: String = "https://example.test/Prod/", key: String? = "key-1", user: String? = "rider01") =
    BackendAccess(url, http, { key }, { user })

  @Test
  fun a_client_for_the_current_user_needs_the_url_the_key_and_the_name() {
    assertNotNull(access().client())
    assertNull(access(url = "").client())
    assertNull(access(key = null).client())
    assertNull(access(user = null).client())
  }

  @Test
  fun a_client_for_another_user_needs_only_the_url_and_the_key() {
    assertNotNull(access(user = null).client("rider02"))
    assertNull(access(url = "").client("rider02"))
    assertNull(access(key = null).client("rider02"))
    assertNull(access().client(null))
  }

  @Test
  fun the_key_is_none_without_the_url() {
    assertEquals("key-1", access().apiKey())
    assertNull(access(url = "").apiKey())
    assertNull(access(key = null).apiKey())
  }

  @Test
  fun a_typed_key_is_tried_without_being_saved() {
    assertNotNull(access(key = null, user = null).clientFor("typed-key", "rider01"))
  }

  @Test
  fun the_url_is_missing_when_it_is_empty() {
    assertEquals(true, access(url = "").urlMissing)
    assertEquals(false, access().urlMissing)
  }
}
```

- [ ] **Step 2: 落ちることを確かめる**

Run: `cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*BackendAccessTest' > /tmp/trv2-s6p2a-t5a.log 2>&1; tail -3 /tmp/trv2-s6p2a-t5a.log | head -1; grep "^e: " /tmp/trv2-s6p2a-t5a.log | head -2`
Expected: `BUILD FAILED`・`Unresolved reference 'BackendAccess'`。

- [ ] **Step 3: `BackendAccess` を書く**

`app/src/main/java/com/touringproject/v2/api/BackendAccess.kt`:

```kotlin
package com.touringproject.v2.api

import okhttp3.OkHttpClient

/**
 * The one place a Backend client is made: from the API's URL, the connection key and a user name (07a). Without the URL
 * or the key (or, for the current user, the name) there is none, and each caller tells the rider as it did before.
 */
class BackendAccess(
  private val baseUrl: String,
  private val http: OkHttpClient,
  private val key: () -> String?,
  private val userName: () -> String?,
) {
  /** The API's URL is not set (SC-13 says so). */
  val urlMissing: Boolean get() = baseUrl.isEmpty()

  /** The connection key, or null when there is none or no URL (the ask loop tells NO_KEY then). */
  fun apiKey(): String? = if (baseUrl.isEmpty()) null else key()

  /** A client for the current user name, or null when the URL, the key or the name is missing. */
  fun client(): ApiClient? = client(userName())

  /** A client for the given user name (SC-18 reads another name's records), or null without the URL or the key. */
  fun client(user: String?): ApiClient? {
    val key = key()
    return if (baseUrl.isEmpty() || key == null || user == null) null else ApiClient(baseUrl, key, user, http)
  }

  /** A client for a key that is given: the ask loop's, which has checked it, and SC-13's, typed and not yet saved. */
  fun clientFor(key: String, user: String): ApiClient = ApiClient(baseUrl, key, user, http)
}
```

- [ ] **Step 4: `AppGraph` と `AppUi` の5か所を付け替える**

`AppGraph.kt`:

- `val apiKeys = ApiKeyStore(store, KeystoreCipher())` の次の行に、次を足す。

```kotlin
  /** The one place a Backend client is made, from the URL, the connection key and the user name (slice 6 plan 2a). */
  val backend = BackendAccess(apiBaseUrl, http, apiKeys::current) { settings.settings.value?.userName }
```

- `val http = OkHttpClient()` を `private val http = OkHttpClient()` にする。
- `sync` の `api = { ... }`（`val key = apiKeys.current()` から `ApiClient(apiBaseUrl, key, user, http)` の行までのブロック）を `api = { backend.client() },` にする。
- `takeover` の `api = { user -> ... }` のブロックを `api = { user -> backend.client(user) },` にする。
- `controller` の `apiKey = { if (apiBaseUrl.isEmpty()) null else apiKeys.current() },` を `apiKey = backend::apiKey,` に、`api = { key, user -> ApiClient(apiBaseUrl, key, user, http) },` を `api = backend::clientFor,` にする。
- `voice` の `api = { ... }` のブロックを `api = { backend.client() },` にする。
- import: `import com.touringproject.v2.api.ApiClient` → `import com.touringproject.v2.api.BackendAccess`（使われなくなった import を残さない）。

`ui/AppUi.kt`:

- `urlMissing = graph.apiBaseUrl.isEmpty(),` → `urlMissing = graph.backend.urlMissing,`。
- `check = { key -> ApiClient(graph.apiBaseUrl, key, current.userName, graph.http).checkKey() },` → `check = { key -> graph.backend.clientFor(key, current.userName).checkKey() },`。
- `import com.touringproject.v2.api.ApiClient` を消す。

（`graph.apiBaseUrl` は androidTest の `RideRecordingTest` が読むので、public のまま残す。）

- [ ] **Step 5: 通ることを確かめる**

```bash
cd $AND && ./gradlew compileDebugKotlin compileDebugUnitTestKotlin compileDebugAndroidTestKotlin > /tmp/trv2-s6p2a-t5.log 2>&1; tail -3 /tmp/trv2-s6p2a-t5.log | head -1
cd $AND && ./gradlew testDebugUnitTest --rerun --tests '*BackendAccessTest' --tests '*AppUiTest' > /tmp/trv2-s6p2a-t5t.log 2>&1; tail -3 /tmp/trv2-s6p2a-t5t.log | head -1
cd $AND && grep -n "ApiClient(" app/src/main/java/com/touringproject/v2/AppGraph.kt app/src/main/java/com/touringproject/v2/ui/AppUi.kt || echo "no ApiClient( in graph or ui"
```

Expected: `BUILD SUCCESSFUL` が 2 回・`no ApiClient( in graph or ui`。

- [ ] **Step 6: コミット**

```bash
cd $AND && git add app/src
cd $AND && git commit -m "refactor: make every Backend client in one place, BackendAccess, so graph and SC-13 share the rule for when there is none"
```

---

### Task 6: `RideDatabase.kt` を分ける（R10-08）

**Files:**
- Create: `store/Entities.kt`・`AskDao.kt`・`NoteDao.kt`・`RideDao.kt`・`TakeoverDao.kt`・`Migrations.kt`
- Modify: `store/RideDatabase.kt`（`@Database` と `open()` だけにする）

- [ ] **Step 1: 切り分けの手順を書く（Python。一度だけ使う）**

`$TMP/r1008.py`:

```python
import pathlib, re, sys
D = pathlib.Path(sys.argv[1]) / "app/src/main/java/com/touringproject/v2/store"
src = (D / "RideDatabase.kt").read_text()
imports = [l for l in src.split("\n") if l.startswith("import ")]

def seg(a, b=None):
    i = src.index(a)
    j = src.index(b, i) if b else len(src)
    return src[i:j].rstrip() + "\n"

entities = seg('@Entity(tableName = "rides")', "@Dao\ninterface AskDao {")
askdao = seg("@Dao\ninterface AskDao {", "@Dao\ninterface NoteDao {")
notedao = seg("@Dao\ninterface NoteDao {", "/** What one ride has left to send")
ridedao = seg("/** What one ride has left to send", "data class KeptRideRow")
takeover = seg("data class KeptRideRow", "@Database(")
database = seg("@Database(", "/**\n * 1 -> 2")
migrations = seg("/**\n * 1 -> 2")
head = ("// The device's record of rides (slice 2 spec §5.1). Every schema version is exported to app/schemas and is moved\n"
        "// forward by a Migration; the database is never rebuilt destructively.\n")

def write(name, body, comment=""):
    used = [i for i in imports if re.search(r"(?<![\w])" + re.escape(i.split(".")[-1].strip()) + r"(?![\w])", body)]
    text = "package com.touringproject.v2.store\n\n" + ("\n".join(used) + "\n\n" if used else "") + (comment + "\n" if comment else "") + body
    (D / name).write_text(text)

write("Entities.kt", entities, head)
write("AskDao.kt", askdao)
write("NoteDao.kt", notedao)
write("RideDao.kt", ridedao)
write("TakeoverDao.kt", takeover)
write("RideDatabase.kt", database, head)
write("Migrations.kt", migrations)
```

- [ ] **Step 2: 実行して、元のコードが一字も変わっていないことを確かめる**

```bash
cd $AND && cp app/src/main/java/com/touringproject/v2/store/RideDatabase.kt $TMP/RideDatabase.orig.kt
cd $AND && python3 $TMP/r1008.py $AND
cd $AND && python3 - <<EOF
import glob
orig = open("$TMP/RideDatabase.orig.kt").read()
new = "\n".join(open(p).read() for p in glob.glob("app/src/main/java/com/touringproject/v2/store/*.kt"))
# every top-level declaration block of the original (split at blank lines between declarations) is in the new files
import re
blocks = [b for b in re.split(r"\n\n(?=@|/\*\*|data class|private const|val |abstract class|interface )", orig.split("\n\n", 1)[1])
          if b.strip() and not b.startswith("import ")]
missing = [b[:60] for b in blocks if b.strip() not in new]
print("missing blocks:", missing)
EOF
```

Expected: `missing blocks: []`（分けたあとのファイルのどれかに、元の宣言のかたまりが一字も変わらずに入っている）。

- [ ] **Step 3: コンパイルと全体のテスト、スキーマの確認**

```bash
cd $AND && ./gradlew clean > /dev/null 2>&1; ./gradlew testDebugUnitTest compileDebugAndroidTestKotlin > /tmp/trv2-s6p2a-t6.log 2>&1; tail -3 /tmp/trv2-s6p2a-t6.log | head -1
cd $AND && git status --short | grep -v "app/src/" || echo "nothing outside app/src (schemas unchanged)"
cd $AND && python3 scripts/package-cycles.py
```

Expected: `BUILD SUCCESSFUL`（721件）・`nothing outside app/src (schemas unchanged)`・2 組。

- [ ] **Step 4: コミット**

```bash
cd $AND && git add app/src
cd $AND && git commit -m "refactor: split RideDatabase.kt into the entities, the DAOs, the migrations and the database"
```

---

### Task 7: 文書と全体の確かめ

**Files:**
- Modify: `docs/08a_android-design.md`（親）、`Android/README.md`

- [ ] **Step 1: 08a §1 のパッケージの表と §3 を直す**

`docs/08a_android-design.md` の §1 の表の行を、次のように直す。

| 今 | 直し |
|---|---|
| `ask` の行（「質問の一巡の状態機械と司令塔・回答を取りに行く処理・会話の識別子・失敗の読み上げ文」） | 「質問の一巡の状態機械と司令塔・文字の質問のシートの状態・会話の識別子・失敗の読み上げ文」 |
| `location` の行の末尾 | 「…・位置と方位の確認（SC-22）の計算・質問の位置の窓口（`Positions`）」 |
| `audio` の行 | 「インカムへの音声の経路・録音（PCM）・回答の再生・端末の音声合成・合図の音と、質問・試し録り・声の入力が使う窓口（`RouteControl`・`Recorder`・`Cues` など）」 |
| `recordings` の行 | 「録音の確認（直近の録音と試し録り）と、録音を残す窓口（`RecordingSink`）」 |
| `ride` の行 | 「走行の状態と計算・走行の司令塔・メモの長さの決まり」 |
| `store` の行 | 「Room の表と読み書き（Entity・DAO・移行はファイルを分けて置く）」 |

§1 の表に `api` の行が無ければ、`ask` の行の次に次を足す: `| \`api\` | Backend の API の呼び出し・回答を取りに行く処理（ポーリング）・Backend を呼ぶ口（\`BackendAccess\`） |`。

§3 の「押下の行き先は、試し録り中なら試し録り、地点メモを開いているなら声の入力、それ以外は質問。」の「開いている」を「前面に表示している」にする。

- [ ] **Step 2: Android の README を直す**

`Android/README.md` の構成の表を、同じ内容に合わせる。

- `ask/` の行の「ポーリング・」を消し、「文字の質問のシートの状態（`TextAsk.kt`）」を足す。
- `api/` の行に「ポーリング（`Polling.kt`）・Backend を呼ぶ口（`BackendAccess.kt`）」を足す。
- `audio/` の行に「質問・試し録り・声の入力が使う窓口（`AudioPorts.kt`）」を足す。
- `location/` の行に「質問の位置の窓口（`Positions.kt`）」を足す。
- `recordings/` の行に「録音を残す窓口（`RecordingPorts.kt`）」を足す。
- `ride/` の行に「メモの長さの決まり（`MemoLimit.kt`）」を足す。
- `store/` の行に「Entity・DAO・移行は `Entities.kt`・`AskDao.kt`・`NoteDao.kt`・`RideDao.kt`・`TakeoverDao.kt`・`Migrations.kt`、`@Database` は `RideDatabase.kt`」を足す。

「大事な決まり」の節に、次の1項目を足す。

```
- パッケージは、窓口を使う側に置く。質問・試し録り・声の入力が共有する窓口は `audio`・`recordings`・`location`・`api` にあり、`ask` が他へ向かう（逆はしない）。パッケージの2つ組の循環は `python3 scripts/package-cycles.py` で数える（今は `(root)↔service` と `(root)↔ui` の2組だけ）。
```

- [ ] **Step 3: 写してコミットする**

```bash
cd $ROOT && ./scripts/sync-docs.sh Android Backend Agent CICD
cd $ROOT && git status --short
cd $AND && git add README.md docs-parent && git commit -m "docs: describe where the shared interfaces, the text sheet, the memo limit and the Backend access now live"
cd $ROOT && git add docs/08a_android-design.md && git commit -m "docs: describe the Android packages after the moves of slice 6 plan 2a"
```

Backend・Agent・CICD の `docs-parent/` が変わっていたら、それぞれの `main` に直接コミットする（PROJECT.md の「前提」）。plan 2b が先に済んでいれば、変わらない。

- [ ] **Step 4: 全体の確かめ**

```bash
cd $AND && ./gradlew clean > /dev/null && ./gradlew testDebugUnitTest assembleDebug assembleRelease compileDebugAndroidTestKotlin > /tmp/trv2-s6p2a-t7.log 2>&1; tail -3 /tmp/trv2-s6p2a-t7.log | head -1
cd $AND && ./scripts/check-release-permissions.sh
cd $AND && python3 scripts/package-cycles.py
```

Expected: `BUILD SUCCESSFUL`・JVM 721 件・`release permissions OK (15)`・2 組。`RideForegroundServiceTest.the_ask_keep_alive_reaches_the_running_service` だけが落ちたら、単独で回して通ることを確かめ、Android #94 にその日の発生を追記する（この plan では直さない）。

- [ ] **Step 5: PROJECT.md を更新して親でコミットする**

plan 表の 2a の行を「実装済み（確認待ち: 無し。振る舞いは変えていない。JVM 721件）」にし、最終レビューの後で「✅ 完了」にする（実機の確認は要らない。ビルドとテストで足りる）。親の submodule の指す先は、Android のブランチの先頭に進める。

```bash
cd $ROOT && git add PROJECT.md Android && git commit -m "docs: record slice 6 plan 2a as implemented"
```
