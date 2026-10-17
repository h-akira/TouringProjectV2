# スライス1 計画4b: App の残り（録音の確認・回答の音量・走行用のビルド・issue #1〜#8） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** スライス1の完了の判定（実際の走行での通し）に入れるように、App を仕上げる。録音の確認（SC-12）・回答の音量（SC-20。Backend の `volumeDb`）・メディアの音量の警告・走行用のビルドを足し、計画4a のレビューと実機の確認で見つかった App の issue #1〜#8 を直す。

**Architecture:** Backend は `POST /asks` に `volumeDb` を足し、Polly の SSML に入れる（環境変数 `POLLY_VOLUME` はやめる）。App は、これまでどおり判断を副作用のない部分（`flow.ts`・`recordings.ts`・`trial.ts`・`tracker.ts`・`press.ts`・`homeBanner.ts`）に置いて Jest で確かめ、端末にしかできないこと（音量・実際の入力デバイス・押下の受け渡し）だけをネイティブモジュールに足す。試し録りは、質問の司令塔（`AskController`）とは別の小さな司令塔（`TrialController`）にし、インカムのボタンは試し録りのあいだだけそちらへ渡す。

**Tech Stack:** Backend: Python 3.13・SAM・pytest（moto）。App: Expo SDK 58・React Native 0.88・expo-router・expo-audio・expo-file-system（`legacy` と、WAV のバイト列だけ新しい `File`）・expo-location・Jest（jest-expo）・Kotlin（Expo Modules）。

**Spec:** [docs/specs/2026-10-16-slice1-design.md](../specs/2026-10-16-slice1-design.md)（§2・§5.4〜§5.8・§6.3・§6.4・§8.1・§10）、契約 `Backend/openapi.yaml` と [docs/07_units_contracts.md](../07_units_contracts.md) UC-5、画面 [docs/mock/index.html](../mock/index.html)（SC-02・SC-09・SC-12・SC-20・DL-01）、詳細要件 [docs/04_detailed_requirements.md](../04_detailed_requirements.md)（US-B-08・US-E-03・US-C-06）、App の GitHub issue #1〜#8。

## Global Constraints

- 作業するリポジトリ: Task 1 は `Backend/`、Task 2〜11 は `App/`、Task 12 は親。どれも `main` から作業ブランチ `slice1-plan4b` を切る。push はしない。
- コミット・デプロイは利用者の許可を得てから（実行の方法を選ぶときに、計画の中のコミットの一律の許可をもらう。デプロイは Task 1 の Step 7 でその都度聞く）。
- `volumeDb` は `0`・`3`・`6`・`9`・`12` のどれか。省けば `6`、それ以外は 400。SSML は `<amazon:effect name="drc"><prosody volume="+{n}dB">`。
- 録音は PCM（16kHz・モノラル・16bit）、上限20秒、直近10件を残す。試し録りは残さない（spec §5.4・§5.5）。
- メディアの音量の警告は、最大の1/3未満で出す。アプリは音量を変えない（spec §5.6）。
- 方位の材料の精度は 20m まで。現在地として使う点は30秒まで（issue #1・#5）。
- 背面で待つ処理に `setTimeout` を使わない（`RideService.sleep`）。画面が前にあるあいだだけの表示用の `setInterval` はよい（既存の `AskOverlay` と同じ）。
- `setAudioModeAsync` を呼ぶところを増やさない（呼ぶと出力先がスマホのスピーカーに固定される。App の README）。
- キー・API の URL・アカウント ID をコードや文書に書かない。コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`APP=$ROOT/App`、`BE=$ROOT/Backend`。App のテストは `cd $APP && npx jest`、型は `npx tsc --noEmit`。Backend のテストは `cd $BE && env/bin/python -m pytest -q`。

## Review Focus

- 試し録りのあいだにインカムのボタンが押される → 質問を始めず、試し録りを止めて再生する。`AskProvider` の配線なので自動テストは無く、Task 13 の実機の確認 #4 で見る。
- SC-12 を開いたままインカムで質問し、回答の読み上げ中に SC-12 を離れる → 読み上げは止まらない（SC-12 は自分が再生しているときだけ止める）。Task 9 の `playingRef` と、Task 13 の確認 #6。
- 録音のファイルが10件を超える → 古い PCM と JSON が一緒に消え、一覧に中身の無い行が残らない。Task 7 の `an old recording's JSON goes with its PCM` と、`listRecordings` が PCM の無い JSON を出さないこと。
- `volumeDb` を持たない、デプロイ前に受け付けた質問を worker が処理する → 既定の +6dB で作る。Task 1 の `test_asks_without_volume_use_the_default`。
- 起動の途中（権限の確認中）にインカムのボタンを何度か押す → 司令塔ができてから質問が1回だけ始まる。Task 4 の `several early presses start one question`。

---

## ファイル構成

| パス | 役割 | Task |
|---|---|---|
| `Backend/src/lib/request.py` | `volumeDb` の検証（`VOLUME_DB_CHOICES`・`DEFAULT_VOLUME_DB`） | 1 |
| `Backend/src/handlers/ask.py`・`worker.py`、`src/lib/speech.py` | 記録に残し、Polly に渡す | 1 |
| `Backend/openapi.yaml`・`template.yaml` | 契約に足し、`POLLY_VOLUME` をやめる | 1 |
| `App/src/settings/store.ts` | 設定に `answerVolumeDb` | 2 |
| `App/app/settings/volume.tsx` | SC-20 回答の音量 | 2 |
| `App/src/location/heading.ts`・`tracker.ts` | 精度で除く（#5）・購読の世代と古い点（#1） | 3 |
| `App/src/handsfree/press.ts`、`modules/handsfree/.../PressStore.kt` | 起動の途中の押下の保留（#3）・渡した押下を残さない（#2） | 4 |
| `App/src/ask/flow.ts`・`failures.ts`・`controller.ts` | サービスが始まらないときの失敗（#6） | 5 |
| `App/modules/audio-route/` | 経路の結果をメインのスレッドで受ける（#4）・メディアの音量・実際の入力デバイス | 6 |
| `App/src/ask/recordings.ts`・`recordingFiles.ts` | 録音の付随情報・WAV のヘッダー・ファイルの読み書き | 7 |
| `App/src/ask/trial.ts` | 試し録りの司令塔 | 8 |
| `App/app/settings/recordings.tsx`、`src/ui/recordingLabel.ts`、`src/ask/AskProvider.tsx`・`runtime.ts` | SC-12 と、試し録り・再生の配線 | 9 |
| `App/src/ui/homeBanner.ts`、`app/index.tsx` | ホームの帯（1本だけ）と音量の警告 | 10 |
| `App/README.md` | 走行用のビルド（#8）と構成 | 11 |
| 親の `docs/`・`PROJECT.md`・submodule | 仕様 §8.1 の `service`、写し、計画の状態 | 12 |

---

### Task 1: Backend: 回答の音量（`volumeDb`）

**Files:**
- Modify: `Backend/src/lib/request.py`、`src/handlers/ask.py`、`src/handlers/worker.py`、`src/lib/speech.py`、`openapi.yaml`、`template.yaml`
- Test: `Backend/tests/test_request.py`、`tests/test_ask.py`、`tests/test_worker.py`、`tests/test_speech.py`

**Interfaces:**
- Produces: `POST /asks` の `volumeDb`（省略時 6）。記録の `volumeDb`。`speech.synthesize(ask_id: str, text: str, volume_db: int, polly=None, s3=None) -> str`。`Steps.synthesize: Callable[[str, str, int], str]`。

- [ ] **Step 1: ブランチを切り、失敗するテストを書く**

```bash
cd $BE && git switch -c slice1-plan4b
```

```diff
diff --git a/tests/test_request.py b/tests/test_request.py
--- a/tests/test_request.py
+++ b/tests/test_request.py
@@ -100,3 +100,18 @@ def test_base64_encoded_body_is_decoded():
     raw = base64.b64encode(json.dumps({"text": "Q"}).encode()).decode()
     ask = parse_ask({"headers": {"x-user-name": "rider01"}, "body": raw, "isBase64Encoded": True})
     assert ask.text == "Q"
+
+
+def test_volume_defaults_to_six():
+    assert parse_ask(event({"text": "Q"})).volume_db == 6
+
+
+@pytest.mark.parametrize("volume", [0, 3, 6, 9, 12])
+def test_volume_choices(volume):
+    assert parse_ask(event({"text": "Q", "volumeDb": volume})).volume_db == volume
+
+
+@pytest.mark.parametrize("volume", [-3, 1, 15, "6", None, True, 6.5])
+def test_volume_bad(volume):
+    with pytest.raises(BadRequest):
+        parse_ask(event({"text": "Q", "volumeDb": volume}))
```

```diff
diff --git a/tests/test_ask.py b/tests/test_ask.py
--- a/tests/test_ask.py
+++ b/tests/test_ask.py
@@ -63,3 +63,19 @@ def test_bad_request_leaves_nothing(aws):
 
 def test_bad_user_is_400(aws):
     assert call({"text": "Q"}, user="X")["statusCode"] == 400
+
+
+def test_volume_is_stored(aws):
+    body = json.loads(call({"text": "Q", "volumeDb": 9})["body"])
+    assert store.get_ask("rider01", body["askId"])["volumeDb"] == 9
+
+
+def test_volume_defaults_when_omitted(aws):
+    body = json.loads(call({"text": "Q"})["body"])
+    assert store.get_ask("rider01", body["askId"])["volumeDb"] == 6
+
+
+def test_bad_volume_is_rejected(aws):
+    result = call({"text": "Q", "volumeDb": 20})
+    assert result["statusCode"] == 400
+    assert aws.table.scan()["Items"] == []
```

```diff
diff --git a/tests/test_worker.py b/tests/test_worker.py
--- a/tests/test_worker.py
+++ b/tests/test_worker.py
@@ -39,8 +39,8 @@ class Recorder:
             raise self.agent_error
         return AgentReply(answer=self.answer, usage={"inputTokens": 5}, model_id="m", tools=["nearby_places"], first_event_at=None)
 
-    def synthesize(self, ask_id, text):
-        self.calls.append(("tts", ask_id, text))
+    def synthesize(self, ask_id, text, volume_db):
+        self.calls.append(("tts", ask_id, text, volume_db))
         if self.tts_error:
             raise self.tts_error
         return f"answers/{ask_id}.mp3"
@@ -169,3 +169,17 @@ def test_unexpected_agent_exception_marks_failed(aws):
     worker.process(USER, ASK, rec.steps())
     item = store.get_ask(USER, ASK)
     assert item["status"] == "failed" and item["error"] == "agent_failed"
+
+
+def test_answer_audio_uses_the_stored_volume(aws):
+    put(aws, volumeDb=12)
+    rec = Recorder()
+    worker.process(USER, ASK, rec.steps())
+    assert next(c for c in rec.calls if c[0] == "tts")[3] == 12
+
+
+def test_asks_without_volume_use_the_default(aws):
+    put(aws)
+    rec = Recorder()
+    worker.process(USER, ASK, rec.steps())
+    assert next(c for c in rec.calls if c[0] == "tts")[3] == 6
```

```diff
diff --git a/tests/test_speech.py b/tests/test_speech.py
--- a/tests/test_speech.py
+++ b/tests/test_speech.py
@@ -7,10 +7,15 @@ from lib import speech
 
 
 def test_ssml_is_escaped_and_louder():
-    ssml = speech.build_ssml("A&B <C>", "+6dB")
+    ssml = speech.build_ssml("A&B <C>", 6)
     assert ssml == '<speak><amazon:effect name="drc"><prosody volume="+6dB">A&amp;B &lt;C&gt;</prosody></amazon:effect></speak>'
 
 
+def test_ssml_uses_the_chosen_volume():
+    assert '<prosody volume="+0dB">' in speech.build_ssml("x", 0)
+    assert '<prosody volume="+12dB">' in speech.build_ssml("x", 12)
+
+
 class FakePolly:
     def __init__(self, error=None):
         self.error, self.calls = error, []
@@ -32,11 +37,11 @@ class FakeS3:
 
 def test_synthesize_stores_mp3(monkeypatch):
     monkeypatch.setenv("POLLY_VOICE_ID", "Kazuha")
-    monkeypatch.setenv("POLLY_VOLUME", "+6dB")
     polly, s3 = FakePolly(), FakeS3()
-    key = speech.synthesize("abc", "晴れです。", polly=polly, s3=s3)
+    key = speech.synthesize("abc", "晴れです。", 9, polly=polly, s3=s3)
     assert key == "answers/abc.mp3"
     call = polly.calls[0]
+    assert '<prosody volume="+9dB">' in call["Text"]
     assert (call["TextType"], call["Engine"], call["VoiceId"], call["OutputFormat"], call["LanguageCode"]) == ("ssml", "neural", "Kazuha", "mp3", "ja-JP")
     assert s3.puts[0]["Bucket"] == "test-audio" and s3.puts[0]["Key"] == key and s3.puts[0]["Body"] == b"mp3-bytes"
     assert s3.puts[0]["ContentType"] == "audio/mpeg"
@@ -44,4 +49,4 @@ def test_synthesize_stores_mp3(monkeypatch):
 
 def test_polly_failure_raises():
     with pytest.raises(RuntimeError):
-        speech.synthesize("abc", "x", polly=FakePolly(RuntimeError("down")), s3=FakeS3())
+        speech.synthesize("abc", "x", 6, polly=FakePolly(RuntimeError("down")), s3=FakeS3())
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $BE && env/bin/python -m pytest -q tests/test_request.py tests/test_ask.py tests/test_worker.py tests/test_speech.py`
Expected: FAIL（`volume_db` が無い・`synthesize()` の引数の数が合わない など）

- [ ] **Step 3: 実装する**

```diff
diff --git a/src/lib/request.py b/src/lib/request.py
--- a/src/lib/request.py
+++ b/src/lib/request.py
@@ -16,6 +16,8 @@ PCM_BYTES_PER_SECOND = 16000 * 2  # 16 kHz, mono, 16-bit
 MIN_AUDIO_BYTES = PCM_BYTES_PER_SECOND // 4
 MAX_AUDIO_BYTES = PCM_BYTES_PER_SECOND * 60
 MAX_TEXT_CHARS = 500
+VOLUME_DB_CHOICES = (0, 3, 6, 9, 12)
+DEFAULT_VOLUME_DB = 6
 
 
 class BadRequest(ValueError):
@@ -29,6 +31,7 @@ class AskInput:
     location: Optional[dict]
     heading_sample: Optional[dict]
     conversation_id: Optional[str]
+    volume_db: int = DEFAULT_VOLUME_DB
 
 
 def _header(event: dict, name: str) -> Optional[str]:
@@ -115,4 +118,8 @@ def parse_ask(event: dict) -> AskInput:
     if conversation_id is not None and (not isinstance(conversation_id, str) or not UUID_RE.match(conversation_id)):
         raise BadRequest("conversationId must be a lowercase UUID")
 
-    return AskInput(audio, text, _point(data.get("location")), _sample(data.get("headingSample")), conversation_id)
+    volume_db = data.get("volumeDb", DEFAULT_VOLUME_DB)
+    if isinstance(volume_db, bool) or volume_db not in VOLUME_DB_CHOICES:
+        raise BadRequest("volumeDb must be one of 0, 3, 6, 9, 12")
+
+    return AskInput(audio, text, _point(data.get("location")), _sample(data.get("headingSample")), conversation_id, int(volume_db))
```

```diff
diff --git a/src/handlers/ask.py b/src/handlers/ask.py
--- a/src/handlers/ask.py
+++ b/src/handlers/ask.py
@@ -36,6 +36,7 @@ def handler(event, context):
         "question": ask.text,
         "location": ask.location,
         "headingSample": ask.heading_sample,
+        "volumeDb": ask.volume_db,
         "timings": {"receivedAt": iso(now)},
     }
     if ask.audio is not None:
```

```diff
diff --git a/src/lib/speech.py b/src/lib/speech.py
--- a/src/lib/speech.py
+++ b/src/lib/speech.py
@@ -1,4 +1,4 @@
-"""Answer audio: Polly neural voice with compression and a volume boost, stored in S3."""
+"""Answer audio: Polly neural voice with compression and the rider's volume boost, stored in S3."""
 from __future__ import annotations
 
 import os
@@ -8,18 +8,18 @@ from xml.sax.saxutils import escape
 from lib import clients
 
 
-def build_ssml(text: str, volume: str) -> str:
+def build_ssml(text: str, volume_db: int) -> str:
     # DRC and a dB boost help the answer stand out against wind and navigation prompts.
-    return f'<speak><amazon:effect name="drc"><prosody volume="{volume}">{escape(text)}</prosody></amazon:effect></speak>'
+    return f'<speak><amazon:effect name="drc"><prosody volume="+{volume_db}dB">{escape(text)}</prosody></amazon:effect></speak>'
 
 
 def answer_key(ask_id: str) -> str:
     return f"answers/{ask_id}.mp3"
 
 
-def synthesize(ask_id: str, text: str, polly: Any = None, s3: Any = None) -> str:
+def synthesize(ask_id: str, text: str, volume_db: int, polly: Any = None, s3: Any = None) -> str:
     response = (polly or clients.polly()).synthesize_speech(
-        Text=build_ssml(text, os.environ.get("POLLY_VOLUME", "+6dB")),
+        Text=build_ssml(text, volume_db),
         TextType="ssml",
         OutputFormat="mp3",
         VoiceId=os.environ.get("POLLY_VOICE_ID", "Kazuha"),
```

```diff
diff --git a/src/handlers/worker.py b/src/handlers/worker.py
--- a/src/handlers/worker.py
+++ b/src/handlers/worker.py
@@ -13,6 +13,7 @@ from lib import address, agent, clients, speech, store, transcribe
 from lib.agent import AgentError, AgentReply
 from lib.geo import heading_degrees
 from lib.prompt import agent_location, build_prompt
+from lib.request import DEFAULT_VOLUME_DB
 
 
 @dataclass
@@ -20,7 +21,7 @@ class Steps:
     transcribe: Callable[[bytes], str]
     describe_location: Callable[[float, float], Optional[str]]
     invoke_agent: Callable[[str, Optional[dict], str], AgentReply]
-    synthesize: Callable[[str, str], str]
+    synthesize: Callable[[str, str, int], str]
     now: Callable[[], datetime]
 
 
@@ -113,7 +114,8 @@ def _run(user: str, ask_id: str, item: dict, steps: Steps) -> None:
     answered = {**facts, "answer": reply.answer, "usage": reply.usage, "modelId": reply.model_id, "tools": reply.tools}
 
     try:
-        key = steps.synthesize(ask_id, reply.answer)
+        # Asks accepted before volumeDb existed have none; DynamoDB returns numbers as Decimal.
+        key = steps.synthesize(ask_id, reply.answer, int(item.get("volumeDb", DEFAULT_VOLUME_DB)))
     except Exception as error:  # noqa: BLE001 - the App reads the answer with device TTS
         mark("synthesizedAt")
         log({"event": "tts_error", "askId": ask_id, "error": type(error).__name__})
```

```diff
diff --git a/openapi.yaml b/openapi.yaml
--- a/openapi.yaml
+++ b/openapi.yaml
@@ -157,6 +157,11 @@ components:
           format: uuid
           nullable: true
           description: 会話を続けるときだけ送る（小文字）。
+        volumeDb:
+          type: integer
+          enum: [0, 3, 6, 9, 12]
+          default: 6
+          description: 回答の音声を上げる量（dB）。利用者が設定で選ぶ。
     AskAccepted:
       type: object
       required: [askId, conversationId, conversationExpiresAt]
```

```diff
diff --git a/template.yaml b/template.yaml
--- a/template.yaml
+++ b/template.yaml
@@ -128,7 +128,6 @@ Resources:
           AGENT_REGION: !Ref AgentRegion
           GEO_REGION: !Ref AWS::Region
           POLLY_VOICE_ID: Kazuha
-          POLLY_VOLUME: "+6dB"
       Policies:
         - DynamoDBCrudPolicy:
             TableName: !Ref RecordsTable
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $BE && env/bin/python -m pytest -q && grep -rn POLLY_VOLUME src tests template.yaml README.md`
Expected: 135 passed。grep は何も出ない。

- [ ] **Step 5: コミット**

```bash
cd $BE && git add src/lib/request.py src/handlers/ask.py src/handlers/worker.py src/lib/speech.py openapi.yaml template.yaml \
  tests/test_request.py tests/test_ask.py tests/test_worker.py tests/test_speech.py
git commit -m "feat: let the app choose how much the answer audio is raised"
```

- [ ] **Step 6: ビルドを確かめる**

Run: `cd $BE && sam validate --lint && sam build`
Expected: 成功。

- [ ] **Step 7: 【利用者の許可を得てから】dev にデプロイし、通しで確かめる**

デプロイしてよいか利用者に聞く。許可が出たら:

```bash
cd $BE && AWS_PROFILE=touring sam build && AWS_PROFILE=touring sam deploy
AWS_PROFILE=touring env/bin/python scripts/smoke.py
```
Expected: smoke が成功する（smoke は `volumeDb` を送らないので、既定の +6dB で通ることの確認になる）。`volumeDb` を付けた確認は、App の実機の確認（Task 13）で行う。profile `touring` が使えないときは、利用者に聞く。

---

### Task 2: App: 回答の音量の設定（SC-20）

**Files:**
- Create: `App/app/settings/volume.tsx`
- Modify: `App/src/settings/store.ts`、`src/api/client.ts`、`src/ask/controller.ts`、`app/settings/index.tsx`、`app/_layout.tsx`
- Test: `App/src/settings/__tests__/store.test.ts`、`src/ask/__tests__/controller.test.ts`、`src/ask/__tests__/flow.test.ts`

**Interfaces:**
- Produces: `VOLUME_DB_CHOICES = [0, 3, 6, 9, 12] as const`、`type VolumeDb`、`DEFAULT_VOLUME_DB = 6`、`Settings.answerVolumeDb: VolumeDb`、`AskBody.volumeDb?: number`。設定の画面の行 `/settings/volume`・`/settings/recordings`（後者の画面は Task 9）。

- [ ] **Step 1: ブランチを切り、失敗するテストを書く**

```bash
cd $APP && git switch -c slice1-plan4b
```

```diff
diff --git a/src/settings/__tests__/store.test.ts b/src/settings/__tests__/store.test.ts
--- a/src/settings/__tests__/store.test.ts
+++ b/src/settings/__tests__/store.test.ts
@@ -17,25 +17,26 @@ test("random user name is 6 lowercase letters or digits", () => {
 test("first load creates and saves a user name with defaults", async () => {
   const store = new MemoryStore();
   const settings = await loadSettings(store, () => 0);
-  expect(settings).toEqual({ userName: "aaaaaa", returnEnabled: true, returnApp: null, returnTiming: "sent", recentApps: [] });
+  expect(settings).toEqual({ userName: "aaaaaa", returnEnabled: true, returnApp: null, returnTiming: "sent", recentApps: [], answerVolumeDb: 6 });
   expect(JSON.parse(store.data.get("trv2.settings")!).userName).toBe("aaaaaa");
 });
 
 test("saved settings round trip", async () => {
   const store = new MemoryStore();
-  const settings = { userName: "rider01", returnEnabled: false, returnApp: MAPS, returnTiming: "spoken" as const, recentApps: [MAPS] };
+  const settings = { userName: "rider01", returnEnabled: false, returnApp: MAPS, returnTiming: "spoken" as const, recentApps: [MAPS], answerVolumeDb: 12 as const };
   await saveSettings(store, settings);
   expect(await loadSettings(store)).toEqual(settings);
 });
 
 test("broken values fall back to defaults", async () => {
   const store = new MemoryStore();
-  store.data.set("trv2.settings", JSON.stringify({ userName: "BAD NAME", returnTiming: "later", returnApp: { label: 1 }, recentApps: "x" }));
+  store.data.set("trv2.settings", JSON.stringify({ userName: "BAD NAME", returnTiming: "later", returnApp: { label: 1 }, recentApps: "x", answerVolumeDb: 7 }));
   const settings = await loadSettings(store, () => 0.5);
   expect(settings.userName).toMatch(/^[a-z0-9]{6}$/);
   expect(settings.returnTiming).toBe("sent");
   expect(settings.returnApp).toBeNull();
   expect(settings.recentApps).toEqual([]);
+  expect(settings.answerVolumeDb).toBe(6);
 });
 
 test("not JSON falls back to defaults", async () => {
```

```diff
diff --git a/src/ask/__tests__/controller.test.ts b/src/ask/__tests__/controller.test.ts
--- a/src/ask/__tests__/controller.test.ts
+++ b/src/ask/__tests__/controller.test.ts
@@ -5,7 +5,7 @@ import { ConversationState } from "../conversation";
 import { FlowState } from "../flow";
 
 const MAPS = { packageName: "maps", label: "マップ" };
-const SETTINGS: Settings = { userName: "rider01", returnEnabled: true, returnApp: MAPS, returnTiming: "sent", recentApps: [] };
+const SETTINGS: Settings = { userName: "rider01", returnEnabled: true, returnApp: MAPS, returnTiming: "sent", recentApps: [], answerVolumeDb: 6 };
 const ACCEPTED: AskAccepted = { askId: "a1", conversationId: "c1", conversationExpiresAt: "2999-01-01T00:00:00.000Z" };
 const done = (over: Partial<AskResult> = {}): AskResult => ({
   askId: "a1", status: "completed", transcript: "Q", answer: "愛鷹山です。", audio: [{ seq: 1, url: "https://audio/1.mp3" }], error: null, timings: {}, ...over,
@@ -70,6 +70,7 @@ test("handsfree happy path returns to nav right after sending", async () => {
     "post", "cue:sent", "return:maps", "get", "play:https://audio/1.mp3", "svc:stop",
   ]);
   expect(h.bodies[0]).toEqual({
+    volumeDb: 6,
     audio: "UENN",
     location: { latitude: 35.6812, longitude: 139.7671 },
     headingSample: { latitude: 35.6806, longitude: 139.7671, at: new Date(90_000).toISOString() },
@@ -274,3 +275,9 @@ test("an old failure does not act on the next ask", async () => {
   expect(returns).toHaveLength(1);
   expect(returns[0][1]).toBeGreaterThan(h.log.lastIndexOf("post"));
 });
+
+test("the chosen answer volume goes with every question", async () => {
+  const h = harness({ stopAfterMs: 1000, settings: { ...SETTINGS, answerVolumeDb: 12 } });
+  await h.controller.run("handsfree");
+  expect(h.bodies[0].volumeDb).toBe(12);
+});
```

```diff
diff --git a/src/ask/__tests__/flow.test.ts b/src/ask/__tests__/flow.test.ts
--- a/src/ask/__tests__/flow.test.ts
+++ b/src/ask/__tests__/flow.test.ts
@@ -3,7 +3,7 @@ import { FlowState, IDLE, isBusy, reduce, shouldReturnNow } from "../flow";
 import { Settings } from "../../settings/store";
 
 const MAPS = { packageName: "maps", label: "マップ" };
-const SETTINGS: Settings = { userName: "rider01", returnEnabled: true, returnApp: MAPS, returnTiming: "sent", recentApps: [] };
+const SETTINGS: Settings = { userName: "rider01", returnEnabled: true, returnApp: MAPS, returnTiming: "sent", recentApps: [], answerVolumeDb: 6 };
 
 function run(events: Parameters<typeof reduce>[1][]): FlowState {
   return events.reduce(reduce, IDLE);
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $APP && npx jest src/settings src/ask/__tests__/controller.test.ts`
Expected: FAIL（`answerVolumeDb` が無い・`volumeDb` が送られない）

- [ ] **Step 3: 実装する**

```diff
diff --git a/src/settings/store.ts b/src/settings/store.ts
--- a/src/settings/store.ts
+++ b/src/settings/store.ts
@@ -1,12 +1,17 @@
 // Settings kept on the device. The connection key lives separately in SecureStore (storage.ts).
 export type ReturnTiming = "sent" | "answered" | "spoken";
 export type LaunchableApp = { packageName: string; label: string };
+// How much the Backend raises the answer audio (SC-20). The Backend accepts exactly these values.
+export const VOLUME_DB_CHOICES = [0, 3, 6, 9, 12] as const;
+export type VolumeDb = (typeof VOLUME_DB_CHOICES)[number];
+export const DEFAULT_VOLUME_DB: VolumeDb = 6;
 export type Settings = {
   userName: string;
   returnEnabled: boolean;
   returnApp: LaunchableApp | null;
   returnTiming: ReturnTiming;
   recentApps: LaunchableApp[];
+  answerVolumeDb: VolumeDb;
 };
 
 export interface KeyValueStore {
@@ -51,6 +56,7 @@ export async function loadSettings(store: KeyValueStore, random: () => number =
     returnApp: isApp(raw.returnApp) ? raw.returnApp : null,
     returnTiming: TIMINGS.includes(raw.returnTiming as ReturnTiming) ? (raw.returnTiming as ReturnTiming) : "sent",
     recentApps: Array.isArray(raw.recentApps) ? raw.recentApps.filter(isApp) : [],
+    answerVolumeDb: VOLUME_DB_CHOICES.includes(raw.answerVolumeDb as VolumeDb) ? (raw.answerVolumeDb as VolumeDb) : DEFAULT_VOLUME_DB,
   };
   if (userName === null) await saveSettings(store, settings);
   return settings;
```

```diff
diff --git a/src/api/client.ts b/src/api/client.ts
--- a/src/api/client.ts
+++ b/src/api/client.ts
@@ -15,6 +15,7 @@ export type AskBody = {
   location?: Point | null;
   headingSample?: HeadingSample | null;
   conversationId?: string | null;
+  volumeDb?: number;
 };
 export type AskAccepted = { askId: string; conversationId: string; conversationExpiresAt: string };
 export type AskResult = {
```

```diff
diff --git a/src/ask/controller.ts b/src/ask/controller.ts
--- a/src/ask/controller.ts
+++ b/src/ask/controller.ts
@@ -202,6 +202,7 @@ export class AskController {
   private async send(recording: Recording, api: AskApi, run: Run): Promise<AskAccepted | null> {
     const d = this.deps;
     const body: AskBody = {
+      volumeDb: d.settings().answerVolumeDb,
       audio: recording.audio,
       location: recording.current ? { latitude: recording.current.latitude, longitude: recording.current.longitude } : null,
       headingSample: recording.current ? pickHeadingSample(recording.fixes, recording.current) : null,
```

`App/app/settings/volume.tsx` を作る:

```tsx
import { Pressable, StyleSheet, Text, View } from "react-native";

import { useAsk } from "../../src/ask/AskProvider";
import { VOLUME_DB_CHOICES } from "../../src/settings/store";

// SC-20: how much the Backend raises the answer audio. Takes effect from the next question.
export default function Volume() {
  const { settings, updateSettings } = useAsk();
  if (!settings) return null;
  return (
    <View style={styles.root}>
      <Text style={styles.title}>回答の音声を上げる量</Text>
      <Text style={styles.note}>ナビの案内や音楽より小さく聞こえるときに上げます。次の質問から変わります。</Text>
      <View style={styles.choices}>
        {VOLUME_DB_CHOICES.map((db) => (
          <Pressable key={db} style={[styles.choice, settings.answerVolumeDb === db && styles.choiceOn]} onPress={() => void updateSettings({ ...settings, answerVolumeDb: db })}>
            <Text style={settings.answerVolumeDb === db ? styles.choiceTextOn : styles.choiceText}>+{db}</Text>
          </Pressable>
        ))}
      </View>
      <Text style={styles.note}>単位は dB です。+6 でおよそ2倍、+12 でおよそ4倍の大きさです。全体が小さいときは、まずスマホのメディアの音量を上げてください。</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 16, gap: 12 },
  title: { fontSize: 18 },
  note: { fontSize: 14, color: "#666" },
  choices: { flexDirection: "row", gap: 6 },
  choice: { flex: 1, minHeight: 46, borderRadius: 12, borderWidth: 2, borderColor: "#ccc", alignItems: "center", justifyContent: "center" },
  choiceOn: { borderColor: "#1f4fd1", backgroundColor: "#e6edfb" },
  choiceText: { fontSize: 16, fontWeight: "700" },
  choiceTextOn: { fontSize: 16, fontWeight: "700", color: "#1f4fd1" },
});
```

```diff
diff --git a/app/settings/index.tsx b/app/settings/index.tsx
--- a/app/settings/index.tsx
+++ b/app/settings/index.tsx
@@ -4,7 +4,7 @@ import { Pressable, StyleSheet, Text, View } from "react-native";
 import { useAsk } from "../../src/ask/AskProvider";
 import { maskKey } from "../../src/settings/store";
 
-function Row({ title, value, href }: { title: string; value: string; href: "/settings/connection" | "/settings/user" | "/settings/return-app" }) {
+function Row({ title, value, href }: { title: string; value: string; href: "/settings/connection" | "/settings/user" | "/settings/return-app" | "/settings/volume" | "/settings/recordings" }) {
   return (
     <Pressable style={styles.row} onPress={() => router.push(href)}>
       <Text style={styles.title}>{title}</Text>
@@ -22,6 +22,8 @@ export default function SettingsIndex() {
       <Row title="接続の設定" value={apiKey ? maskKey(apiKey) : "未設定"} href="/settings/connection" />
       <Row title="ユーザー名" value={settings.userName} href="/settings/user" />
       <Row title="応答後に戻るアプリ" value={returnValue} href="/settings/return-app" />
+      <Row title="回答の音量" value={`+${settings.answerVolumeDb}dB`} href="/settings/volume" />
+      <Row title="録音の確認" value="" href="/settings/recordings" />
     </View>
   );
 }
```

```diff
diff --git a/app/_layout.tsx b/app/_layout.tsx
--- a/app/_layout.tsx
+++ b/app/_layout.tsx
@@ -12,6 +12,8 @@ export default function Layout() {
         <Stack.Screen name="settings/connection" options={{ title: "接続の設定" }} />
         <Stack.Screen name="settings/user" options={{ title: "ユーザー名" }} />
         <Stack.Screen name="settings/return-app" options={{ title: "応答後に戻るアプリ" }} />
+        <Stack.Screen name="settings/volume" options={{ title: "回答の音量" }} />
+        <Stack.Screen name="settings/recordings" options={{ title: "録音の確認" }} />
       </Stack>
       <AskOverlay />
     </AskProvider>
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: 77 passed、型のエラー 0。`/settings/recordings` の画面ファイルはまだ無いが、expo-router の型付きの経路は使っていないので型検査は通る。

- [ ] **Step 5: コミット**

```bash
cd $APP && git add src/settings/store.ts src/api/client.ts src/ask/controller.ts app/settings/volume.tsx app/settings/index.tsx app/_layout.tsx \
  src/settings/__tests__/store.test.ts src/ask/__tests__/controller.test.ts src/ask/__tests__/flow.test.ts
git commit -m "feat: choose how loud answers are (SC-20)"
```

---

### Task 3: App: 位置の購読と精度（issue #1・#5）

**Files:**
- Create: `App/src/location/tracker.ts`、`src/location/__tests__/tracker.test.ts`
- Modify: `App/src/location/heading.ts`、`src/ask/runtime.ts`
- Test: `App/src/location/__tests__/heading.test.ts`、`src/ask/__tests__/controller.test.ts`

**Interfaces:**
- Produces: `Fix = { latitude; longitude; timestamp; accuracy: number | null }`、`MAX_ACCURACY_M = 20`、`MAX_CURRENT_AGE_MS = 30_000`、`PositionSource = { now(); lastKnown(): Promise<Fix | null>; watch(onFix): Promise<Subscription> }`、`class PositionTracker { constructor(source); begin(): void; end(): { current: Fix | null; fixes: Fix[] } }`。

- [ ] **Step 1: 失敗するテストを書く**

```diff
diff --git a/src/location/__tests__/heading.test.ts b/src/location/__tests__/heading.test.ts
--- a/src/location/__tests__/heading.test.ts
+++ b/src/location/__tests__/heading.test.ts
@@ -1,6 +1,6 @@
 import { distanceMeters, Fix, pickHeadingSample } from "../heading";
 
-const at = (latitude: number, timestamp: number): Fix => ({ latitude, longitude: 139.7671, timestamp });
+const at = (latitude: number, timestamp: number, accuracy: number | null = 5): Fix => ({ latitude, longitude: 139.7671, timestamp, accuracy });
 const NOW = 1_800_000_000_000;
 const current = at(35.6812, NOW);
 
@@ -23,3 +23,19 @@ test("ignores points older than a minute and points not before the current one",
   expect(pickHeadingSample([at(35.6790, NOW + 1_000)], current)).toBeNull();
   expect(pickHeadingSample([], current)).toBeNull();
 });
+
+test("test_no_sample_from_inaccurate_points", () => {
+  // Stationary, but a 40 m fix 60 m away would otherwise look like movement.
+  expect(pickHeadingSample([at(35.68066, NOW - 10_000, 40)], current)).toBeNull();
+  expect(pickHeadingSample([at(35.68066, NOW - 10_000, 5), at(35.6809, NOW - 5_000, 40)], current)).toEqual({
+    latitude: 35.68066, longitude: 139.7671, at: new Date(NOW - 10_000).toISOString(),
+  });
+});
+
+test("no sample when the current point itself is inaccurate", () => {
+  expect(pickHeadingSample([at(35.68066, NOW - 10_000)], at(35.6812, NOW, 50))).toBeNull();
+});
+
+test("unknown accuracy is accepted", () => {
+  expect(pickHeadingSample([at(35.68066, NOW - 10_000, null)], at(35.6812, NOW, null))).not.toBeNull();
+});
```

```diff
diff --git a/src/ask/__tests__/controller.test.ts b/src/ask/__tests__/controller.test.ts
--- a/src/ask/__tests__/controller.test.ts
+++ b/src/ask/__tests__/controller.test.ts
@@ -10,8 +10,8 @@ const ACCEPTED: AskAccepted = { askId: "a1", conversationId: "c1", conversationE
 const done = (over: Partial<AskResult> = {}): AskResult => ({
   askId: "a1", status: "completed", transcript: "Q", answer: "愛鷹山です。", audio: [{ seq: 1, url: "https://audio/1.mp3" }], error: null, timings: {}, ...over,
 });
-const HERE = { latitude: 35.6812, longitude: 139.7671, timestamp: 100_000 };
-const BEHIND = { latitude: 35.6806, longitude: 139.7671, timestamp: 90_000 };
+const HERE = { latitude: 35.6812, longitude: 139.7671, timestamp: 100_000, accuracy: 5 };
+const BEHIND = { latitude: 35.6806, longitude: 139.7671, timestamp: 90_000, accuracy: 5 };
 
 type Options = {
   apiKey?: string | null;
```

`App/src/location/__tests__/tracker.test.ts` を作る:

```ts
import { Fix } from "../heading";
import { MAX_CURRENT_AGE_MS, PositionSource, PositionTracker } from "../tracker";

const NOW = 1_800_000_000_000;
const fix = (timestamp: number): Fix => ({ latitude: 35.68, longitude: 139.76, timestamp, accuracy: 5 });
const flush = () => new Promise((resolve) => setImmediate(resolve));

function source(options: { lastKnown?: Fix | null } = {}) {
  let resolveWatch!: (s: { remove(): void }) => void;
  const watchers: ((f: Fix) => void)[] = [];
  const removed: string[] = [];
  const src: PositionSource = {
    now: () => NOW,
    lastKnown: async () => options.lastKnown ?? null,
    watch: (cb) => {
      watchers.push(cb);
      return new Promise((resolve) => { resolveWatch = resolve; });
    },
  };
  return {
    src,
    removed,
    deliverWatch: (name = "w") => resolveWatch({ remove: () => removed.push(name) }),
    // Delivers a fix to the newest watch, or to the given one (0 = the first begin()).
    emit: (f: Fix, watch = watchers.length - 1) => watchers[watch](f),
  };
}

test("a watch that arrives after end() is removed at once", async () => {
  const s = source();
  const t = new PositionTracker(s.src);
  t.begin();
  t.end();
  s.deliverWatch("late");
  await flush();
  expect(s.removed).toEqual(["late"]);
});

test("end() removes a watch that is already set up", async () => {
  const s = source();
  const t = new PositionTracker(s.src);
  t.begin();
  s.deliverWatch("w");
  await flush();
  t.end();
  expect(s.removed).toEqual(["w"]);
});

test("fixes from an earlier begin() are not mixed in", async () => {
  const s = source();
  const t = new PositionTracker(s.src);
  t.begin();
  t.end();
  t.begin();
  s.emit(fix(NOW - 1_000), 0);
  s.emit(fix(NOW - 500), 1);
  expect(t.end().fixes).toEqual([fix(NOW - 500)]);
});

test("a stale last-known point is not the current position", async () => {
  const s = source({ lastKnown: fix(NOW - MAX_CURRENT_AGE_MS - 1) });
  const t = new PositionTracker(s.src);
  t.begin();
  await flush();
  const { current, fixes } = t.end();
  expect(current).toBeNull();
  expect(fixes).toHaveLength(1);
});

test("the newest fresh fix is the current position", async () => {
  const s = source({ lastKnown: fix(NOW - 5_000) });
  const t = new PositionTracker(s.src);
  t.begin();
  await flush();
  s.emit(fix(NOW - 1_000));
  expect(t.end().current).toEqual(fix(NOW - 1_000));
});
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $APP && npx jest src/location`
Expected: FAIL（`../tracker` が無い・精度の悪い点から方位の材料を選ぶ）

- [ ] **Step 3: 実装する**

```diff
diff --git a/src/location/heading.ts b/src/location/heading.ts
--- a/src/location/heading.ts
+++ b/src/location/heading.ts
@@ -1,10 +1,17 @@
 // Picks the older point the Backend uses to work out the direction of travel (07 UC-5).
 import { HeadingSample } from "../api/client";
 
-export type Fix = { latitude: number; longitude: number; timestamp: number };
+// accuracy is the radius in metres the device reports (null when unknown).
+export type Fix = { latitude: number; longitude: number; timestamp: number; accuracy: number | null };
 
 export const MIN_SAMPLE_DISTANCE_M = 15;
 export const MAX_SAMPLE_AGE_MS = 60_000;
+// GPS jitter of a stationary phone can exceed MIN_SAMPLE_DISTANCE_M with poor fixes (issue #5).
+export const MAX_ACCURACY_M = 20;
+
+function accurate(f: Fix): boolean {
+  return f.accuracy === null || f.accuracy <= MAX_ACCURACY_M;
+}
 
 export function distanceMeters(a: Fix, b: Fix): number {
   const r = 6_371_000;
@@ -16,8 +23,10 @@ export function distanceMeters(a: Fix, b: Fix): number {
 }
 
 export function pickHeadingSample(fixes: Fix[], current: Fix): HeadingSample | null {
+  if (!accurate(current)) return null;
   const candidates = fixes.filter(
     (f) =>
+      accurate(f) &&
       f.timestamp < current.timestamp &&
       current.timestamp - f.timestamp <= MAX_SAMPLE_AGE_MS &&
       distanceMeters(f, current) >= MIN_SAMPLE_DISTANCE_M,
```

`App/src/location/tracker.ts` を作る:

```ts
// Collects position fixes while a question is recorded. A watch that is set up only after end() is removed at once,
// and a last-known point older than MAX_CURRENT_AGE_MS is not sent as the current position (issue #1).
import { Fix } from "./heading";

export const MAX_CURRENT_AGE_MS = 30_000;

export type Subscription = { remove(): void };
export type PositionSource = {
  now(): number;
  lastKnown(): Promise<Fix | null>;
  watch(onFix: (fix: Fix) => void): Promise<Subscription>;
};

export class PositionTracker {
  private fixes: Fix[] = [];
  private subscription: Subscription | null = null;
  // Bumped by begin() and end(); callbacks of an earlier generation are ignored.
  private generation = 0;

  constructor(private readonly source: PositionSource) {}

  begin(): void {
    this.subscription?.remove();
    this.subscription = null;
    this.fixes = [];
    const generation = ++this.generation;
    const add = (fix: Fix) => {
      if (generation === this.generation) this.fixes.push(fix);
    };
    void this.source.lastKnown().then((fix) => fix && add(fix)).catch(() => undefined);
    void this.source
      .watch(add)
      .then((subscription) => {
        if (generation === this.generation) this.subscription = subscription;
        else subscription.remove();
      })
      .catch(() => undefined);
  }

  end(): { current: Fix | null; fixes: Fix[] } {
    this.generation += 1;
    this.subscription?.remove();
    this.subscription = null;
    const fixes = [...this.fixes].sort((a, b) => a.timestamp - b.timestamp);
    this.fixes = [];
    const latest = fixes.length > 0 ? fixes[fixes.length - 1] : null;
    const current = latest && this.source.now() - latest.timestamp <= MAX_CURRENT_AGE_MS ? latest : null;
    return { current, fixes };
  }
}
```

`runtime.ts` の中の古い `PositionTracker` を、`tracker.ts` を使う形に置き換える:

```diff
diff --git a/src/ask/runtime.ts b/src/ask/runtime.ts
--- a/src/ask/runtime.ts
+++ b/src/ask/runtime.ts
@@ -11,6 +11,7 @@ import RideService from "../../modules/ride-service/src";
 import { ApiClient } from "../api/client";
 import { API_BASE_URL } from "../config";
 import { Fix } from "../location/heading";
+import { PositionTracker } from "../location/tracker";
 import type { Settings } from "../settings/store";
 import { Deps } from "./controller";
 import { ConversationState } from "./conversation";
@@ -70,28 +71,20 @@ class PcmRecorder {
   }
 }
 
-class PositionTracker {
-  private fixes: Fix[] = [];
-  private subscription: Location.LocationSubscription | null = null;
-
-  begin(): void {
-    this.fixes = [];
-    void Location.getLastKnownPositionAsync().then((p) => p && this.add(p));
-    void Location.watchPositionAsync({ accuracy: Location.Accuracy.High, timeInterval: 1000, distanceInterval: 0 }, (p) => this.add(p))
-      .then((s) => { this.subscription = s; })
-      .catch(() => undefined);
-  }
-
-  end(): { current: Fix | null; fixes: Fix[] } {
-    this.subscription?.remove();
-    this.subscription = null;
-    const fixes = [...this.fixes].sort((a, b) => a.timestamp - b.timestamp);
-    return { current: fixes.length > 0 ? fixes[fixes.length - 1] : null, fixes };
-  }
+function toFix(p: Location.LocationObject): Fix {
+  return { latitude: p.coords.latitude, longitude: p.coords.longitude, timestamp: p.timestamp, accuracy: p.coords.accuracy ?? null };
+}
 
-  private add(p: Location.LocationObject): void {
-    this.fixes.push({ latitude: p.coords.latitude, longitude: p.coords.longitude, timestamp: p.timestamp });
-  }
+function createPositionTracker(): PositionTracker {
+  return new PositionTracker({
+    now: () => Date.now(),
+    lastKnown: async () => {
+      const p = await Location.getLastKnownPositionAsync();
+      return p ? toFix(p) : null;
+    },
+    watch: (onFix) =>
+      Location.watchPositionAsync({ accuracy: Location.Accuracy.High, timeInterval: 1000, distanceInterval: 0 }, (p) => onFix(toFix(p))),
+  });
 }
 
 export function createRuntimeDeps(options: {
@@ -105,7 +98,7 @@ export function createRuntimeDeps(options: {
     AudioRoute.releaseSco(),
   );
   const recorder = new PcmRecorder();
-  const positions = new PositionTracker();
+  const positions = createPositionTracker();
   const playback: { stop: (() => void) | null } = { stop: null };
   let routeSource: Source | null = null;
 
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: 85 passed、型のエラー 0。

- [ ] **Step 5: コミット**

```bash
cd $APP && git add src/location/heading.ts src/location/tracker.ts src/ask/runtime.ts \
  src/location/__tests__/heading.test.ts src/location/__tests__/tracker.test.ts src/ask/__tests__/controller.test.ts
git commit -m "fix: drop late location watches, stale fixes and inaccurate heading samples"
```

---

### Task 4: App: インカムの押下の重複と取りこぼし（issue #2・#3）

**Files:**
- Modify: `App/src/handsfree/press.ts`、`src/ask/AskProvider.tsx`、`modules/handsfree/android/src/main/java/com/touringproject/v2/handsfree/PressStore.kt`
- Test: `App/src/handsfree/__tests__/press.test.ts`

**Interfaces:**
- Produces: `class PressGate { constructor(handle: () => void); offer(pressedAt: number, now: number): void; openGate(now: number): void }`。`AskProvider` は `presses` を `PressGate` にする（Task 9 で、渡す先を試し録りと分ける）。

- [ ] **Step 1: 失敗するテストを書く**

```diff
diff --git a/src/handsfree/__tests__/press.test.ts b/src/handsfree/__tests__/press.test.ts
--- a/src/handsfree/__tests__/press.test.ts
+++ b/src/handsfree/__tests__/press.test.ts
@@ -1,4 +1,4 @@
-import { PressTracker, STALE_PRESS_MS } from "../press";
+import { PressGate, PressTracker, STALE_PRESS_MS } from "../press";
 
 test("each press is handled once", () => {
   const t = new PressTracker();
@@ -13,3 +13,42 @@ test("old presses are dropped", () => {
   expect(t.claim(1000, 1000 + STALE_PRESS_MS + 1)).toBe("stale");
   expect(t.claim(1010, 1020)).toBe("new");
 });
+
+describe("PressGate", () => {
+  test("a press before the controller exists is handled once it does", () => {
+    const handled: number[] = [];
+    const gate = new PressGate(() => handled.push(1));
+    gate.offer(1000, 1000);
+    expect(handled).toHaveLength(0);
+    gate.openGate(3000);
+    expect(handled).toHaveLength(1);
+  });
+
+  test("several early presses start one question", () => {
+    let count = 0;
+    const gate = new PressGate(() => { count += 1; });
+    gate.offer(1000, 1000);
+    gate.offer(1500, 1500);
+    gate.openGate(2000);
+    gate.offer(1500, 2100); // the same press again as the pending one at launch
+    expect(count).toBe(1);
+  });
+
+  test("an early press that went stale while waiting is dropped", () => {
+    let count = 0;
+    const gate = new PressGate(() => { count += 1; });
+    gate.offer(1000, 1000);
+    gate.openGate(1000 + STALE_PRESS_MS + 1);
+    expect(count).toBe(0);
+  });
+
+  test("after opening, presses go straight through and duplicates are dropped", () => {
+    let count = 0;
+    const gate = new PressGate(() => { count += 1; });
+    gate.openGate(0);
+    gate.offer(1000, 1000);
+    gate.offer(1000, 1100);
+    gate.offer(2000, 2000);
+    expect(count).toBe(2);
+  });
+});
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $APP && npx jest src/handsfree`
Expected: FAIL（`PressGate` が無い）

- [ ] **Step 3: 実装する**

```diff
diff --git a/src/handsfree/press.ts b/src/handsfree/press.ts
--- a/src/handsfree/press.ts
+++ b/src/handsfree/press.ts
@@ -11,3 +11,29 @@ export class PressTracker {
     return "new";
   }
 }
+
+// Holds presses that arrive before the ask controller exists (permission prompts at first launch) and hands them
+// over once it does; claiming them earlier would mark them handled with nobody to act on them (issue #3).
+export class PressGate {
+  private held: number | null = null;
+  private open = false;
+  private readonly tracker = new PressTracker();
+
+  constructor(private readonly handle: () => void) {}
+
+  offer(pressedAt: number, now: number): void {
+    if (!this.open) {
+      this.held = Math.max(this.held ?? 0, pressedAt);
+      return;
+    }
+    if (this.tracker.claim(pressedAt, now) === "new") this.handle();
+  }
+
+  /** The controller is ready: handle the newest press that waited for it, if it is not stale. */
+  openGate(now: number): void {
+    this.open = true;
+    const held = this.held;
+    this.held = null;
+    if (held !== null) this.offer(held, now);
+  }
+}
```

```diff
diff --git a/src/ask/AskProvider.tsx b/src/ask/AskProvider.tsx
--- a/src/ask/AskProvider.tsx
+++ b/src/ask/AskProvider.tsx
@@ -2,7 +2,7 @@ import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo,
 
 import AudioRoute from "../../modules/audio-route/src";
 import Handsfree from "../../modules/handsfree/src";
-import { PressTracker } from "../handsfree/press";
+import { PressGate } from "../handsfree/press";
 import { loadApiKey, deleteApiKey, saveApiKey, settingsStore } from "../settings/storage";
 import { loadSettings, saveSettings, Settings } from "../settings/store";
 import { AskController } from "./controller";
@@ -37,11 +37,9 @@ export function AskProvider({ children }: { children: ReactNode }) {
   const keyRef = useRef<string | null>(null);
   const controllerRef = useRef<AskController | null>(null);
   const runtimeRef = useRef<ReturnType<typeof createRuntimeDeps> | null>(null);
-  const presses = useRef(new PressTracker());
+  const presses = useRef(new PressGate(() => controllerRef.current?.press()));
 
-  const handlePress = useCallback((pressedAt: number) => {
-    if (presses.current.claim(pressedAt, Date.now()) === "new") controllerRef.current?.press();
-  }, []);
+  const handlePress = useCallback((pressedAt: number) => presses.current.offer(pressedAt, Date.now()), []);
 
   useEffect(() => {
     let mounted = true;
@@ -64,6 +62,7 @@ export function AskProvider({ children }: { children: ReactNode }) {
       setReady(true);
       const pending = Handsfree.takePendingPress();
       if (pending !== null) handlePress(pending);
+      presses.current.openGate(Date.now());
     })();
     const pressSub = Handsfree.addListener("onPress", (e) => handlePress(e.pressedAt));
     // The headset dropping SCO during a voice-recognition session is the second press.
```

`PressStore.kt` は、リスナーに渡した押下を `pending` に残さない（#2）:

```diff
diff --git a/modules/handsfree/android/src/main/java/com/touringproject/v2/handsfree/PressStore.kt b/modules/handsfree/android/src/main/java/com/touringproject/v2/handsfree/PressStore.kt
--- a/modules/handsfree/android/src/main/java/com/touringproject/v2/handsfree/PressStore.kt
+++ b/modules/handsfree/android/src/main/java/com/touringproject/v2/handsfree/PressStore.kt
@@ -1,15 +1,19 @@
 package com.touringproject.v2.handsfree
 
 // Shared between the activity lifecycle listener and the module, which may not exist yet at cold start.
+// A press goes either to the listener or into pending, never both: a press kept after it was delivered would be
+// handed out again by takePendingPress() when the React tree is recreated (issue #2).
 object PressStore {
-  @Volatile private var pending: Long? = null
+  private var pending: Long? = null
   @Volatile var listener: ((Long) -> Unit)? = null
 
   fun record(pressedAt: Long) {
-    pending = pressedAt
-    listener?.invoke(pressedAt)
+    val current = listener
+    synchronized(this) { pending = if (current == null) pressedAt else null }
+    current?.invoke(pressedAt)
   }
 
+  @Synchronized
   fun take(): Long? {
     val value = pending
     pending = null
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: 89 passed、型のエラー 0。Kotlin は Task 11 のビルドで確かめる。

- [ ] **Step 5: コミット**

```bash
cd $APP && git add src/handsfree/press.ts src/ask/AskProvider.tsx src/handsfree/__tests__/press.test.ts \
  modules/handsfree/android/src/main/java/com/touringproject/v2/handsfree/PressStore.kt
git commit -m "fix: hold intercom presses until the controller exists and never replay a delivered one"
```

---

### Task 5: App: フォアグラウンドサービスが始まらないとき（issue #6）

**Files:**
- Modify: `App/src/ask/flow.ts`、`src/ask/failures.ts`、`src/ask/controller.ts`
- Test: `App/src/ask/__tests__/controller.test.ts`、`src/ask/__tests__/flow.test.ts`

**Interfaces:**
- Produces: `FailureReason` に `"service"`。読み上げる文「準備できなかったため、質問できませんでした。もう一度お試しください。」

- [ ] **Step 1: 失敗するテストを書く**

```diff
diff --git a/src/ask/__tests__/controller.test.ts b/src/ask/__tests__/controller.test.ts
--- a/src/ask/__tests__/controller.test.ts
+++ b/src/ask/__tests__/controller.test.ts
@@ -23,6 +23,7 @@ type Options = {
   stopAfterMs?: number | null;
   micAllowed?: boolean;
   sayGate?: Promise<void>;
+  serviceError?: Error;
 };
 
 function harness(options: Options = {}) {
@@ -50,7 +51,7 @@ function harness(options: Options = {}) {
     route: { start: async (source) => { log.push(`route:${source}`); return options.routeOk ?? true; }, stop: async () => { log.push("route:stop"); } },
     recorder: { start: async () => { log.push("rec:start"); }, stop: async () => { log.push("rec:stop"); return "UENN"; }, cancel: async () => { log.push("rec:cancel"); } },
     location: { begin: () => { log.push("loc:begin"); }, end: () => ({ current: HERE, fixes: [BEHIND, HERE] }) },
-    service: { start: () => { log.push("svc:start"); }, stop: () => { log.push("svc:stop"); } },
+    service: { start: () => { log.push("svc:start"); if (options.serviceError) throw options.serviceError; }, stop: () => { log.push("svc:stop"); } },
     nav: { returnTo: async (pkg) => { log.push(`return:${pkg}`); return true; } },
     cues: { start: () => log.push("cue:start"), sent: () => log.push("cue:sent"), waiting: () => log.push("cue:waiting"), failure: () => log.push("cue:failure") },
     player: { play: async (urls) => { log.push(`play:${urls.join(",")}`); if (options.playError) throw options.playError; }, stop: () => { log.push("play:stop"); } },
@@ -281,3 +282,13 @@ test("the chosen answer volume goes with every question", async () => {
   await h.controller.run("handsfree");
   expect(h.bodies[0].volumeDb).toBe(12);
 });
+
+test("a foreground service that cannot start fails out loud", async () => {
+  const h = harness({ serviceError: new Error("ForegroundServiceStartNotAllowedException") });
+  await h.controller.run("handsfree");
+  expect(h.log).toEqual([
+    "svc:start", "cue:failure", "say:準備できなかったため、質問できませんでした。もう一度お試しください。", "return:maps",
+  ]);
+  expect(h.states.some((s) => s.phase === "failed" && s.failure === "service")).toBe(true);
+  expect(h.controller.state.phase).toBe("idle");
+});
```

```diff
diff --git a/src/ask/__tests__/flow.test.ts b/src/ask/__tests__/flow.test.ts
--- a/src/ask/__tests__/flow.test.ts
+++ b/src/ask/__tests__/flow.test.ts
@@ -63,6 +63,7 @@ test("spoken messages", () => {
   expect(spokenMessage("invalid_key")).toBe("接続キーを確かめてください。");
   expect(spokenMessage("no_key")).toBe(spokenMessage("invalid_key"));
   expect(spokenMessage("mic")).toBe("録音できませんでした。");
+  expect(spokenMessage("service")).toBe("準備できなかったため、質問できませんでした。もう一度お試しください。");
   expect(BUSY_MESSAGE).toBe("いま応答中です。少し待ってからもう一度お話しください。");
 });
 
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $APP && npx jest src/ask`
Expected: FAIL（例外がそのまま投げられる・`service` の文が無い）

- [ ] **Step 3: 実装する**

```diff
diff --git a/src/ask/flow.ts b/src/ask/flow.ts
--- a/src/ask/flow.ts
+++ b/src/ask/flow.ts
@@ -12,7 +12,8 @@ export type FailureReason =
   | "network"
   | "invalid_key"
   | "no_key"
-  | "mic";
+  | "mic"
+  | "service";
 
 export type FlowState = {
   phase: Phase;
```

```diff
diff --git a/src/ask/failures.ts b/src/ask/failures.ts
--- a/src/ask/failures.ts
+++ b/src/ask/failures.ts
@@ -13,6 +13,7 @@ const MESSAGES: Record<FailureReason, string> = {
   invalid_key: "接続キーを確かめてください。",
   no_key: "接続キーを確かめてください。",
   mic: "録音できませんでした。",
+  service: "準備できなかったため、質問できませんでした。もう一度お試しください。",
 };
 
 export function spokenMessage(reason: FailureReason): string {
```

```diff
diff --git a/src/ask/controller.ts b/src/ask/controller.ts
--- a/src/ask/controller.ts
+++ b/src/ask/controller.ts
@@ -112,7 +112,14 @@ export class AskController {
       if (!this.isCurrent(run)) return;
       const settings = d.settings();
       const api = d.api(apiKey, settings.userName);
-      d.service.start();
+      try {
+        d.service.start();
+      } catch (error) {
+        // Without the foreground service the ask would stall once the screen is off; say so instead (issue #6).
+        d.log("service_failed", { error: String(error) });
+        await this.fail("service", run);
+        return;
+      }
       this.serviceRunning = true;
       const recording = await this.record(run);
       if (recording === null) return;
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: 90 passed、型のエラー 0。

- [ ] **Step 5: コミット**

```bash
cd $APP && git add src/ask/flow.ts src/ask/failures.ts src/ask/controller.ts src/ask/__tests__/controller.test.ts src/ask/__tests__/flow.test.ts
git commit -m "fix: say so when the foreground service cannot start"
```

---

### Task 6: App: 音声経路のネイティブ（issue #4・メディアの音量・実際の入力デバイス）

**Files:**
- Modify: `App/modules/audio-route/android/src/main/java/com/touringproject/v2/audioroute/AudioRouteModule.kt`、`modules/audio-route/src/index.ts`

**Interfaces:**
- Produces: `MediaVolume = { current: number; max: number }`、`InputDevice = { type: "bluetooth" | "builtin" | "other"; name: string }`、`AudioRoute.getMediaVolume(): MediaVolume`、`AudioRoute.activeInputDevice(): InputDevice | null`（録音中にだけ値が返る）。

ネイティブの関数は Jest で試せないので、ここでは型と実装だけを入れ、ビルドは Task 11、動きは Task 13 で確かめる。

- [ ] **Step 1: 実装する**

```diff
diff --git a/modules/audio-route/android/src/main/java/com/touringproject/v2/audioroute/AudioRouteModule.kt b/modules/audio-route/android/src/main/java/com/touringproject/v2/audioroute/AudioRouteModule.kt
--- a/modules/audio-route/android/src/main/java/com/touringproject/v2/audioroute/AudioRouteModule.kt
+++ b/modules/audio-route/android/src/main/java/com/touringproject/v2/audioroute/AudioRouteModule.kt
@@ -85,6 +85,26 @@ class AudioRouteModule : Module() {
       runCatching { audioManager.clearCommunicationDevice() }
       audioManager.mode = AudioManager.MODE_NORMAL
     }.runOnQueue(Queues.MAIN)
+
+    // Answers and cues play on the media stream; the intercom follows the phone's media volume.
+    Function("getMediaVolume") {
+      mapOf(
+        "current" to audioManager.getStreamVolume(AudioManager.STREAM_MUSIC),
+        "max" to audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC),
+      )
+    }
+
+    // The microphone this app is recording from right now (only our own recordings are visible to us).
+    Function("activeInputDevice") {
+      val device = audioManager.activeRecordingConfigurations.firstNotNullOfOrNull { it.audioDevice }
+        ?: return@Function null
+      val type = when (device.type) {
+        AudioDeviceInfo.TYPE_BLUETOOTH_SCO -> "bluetooth"
+        AudioDeviceInfo.TYPE_BUILTIN_MIC -> "builtin"
+        else -> "other"
+      }
+      mapOf("type" to type, "name" to device.productName.toString())
+    }
   }
 
   // ---------------- intercom button: voice recognition ----------------
@@ -281,7 +301,8 @@ class AudioRouteModule : Module() {
       done(ok, note)
     }
     listener = AudioManager.OnCommunicationDeviceChangedListener { device -> if (device?.type == SCO_TYPE) finish(true, "connected") }
-    am.addOnCommunicationDeviceChangedListener({ it.run() }, listener)
+    // On the main thread like the timeout, so finish() is never entered from two threads at once (issue #4).
+    am.addOnCommunicationDeviceChangedListener(context.mainExecutor, listener)
     onTimeout = Runnable { finish(false, "SCO timeout") }
     main.postDelayed(onTimeout, timeoutMs.toLong())
     val accepted = runCatching { am.setCommunicationDevice(sink) }.getOrDefault(false)
```

```diff
diff --git a/modules/audio-route/src/index.ts b/modules/audio-route/src/index.ts
--- a/modules/audio-route/src/index.ts
+++ b/modules/audio-route/src/index.ts
@@ -1,6 +1,8 @@
 import { NativeModule, requireNativeModule } from "expo-modules-core";
 
 export type RouteResult = { ok: boolean; note: string };
+export type MediaVolume = { current: number; max: number };
+export type InputDevice = { type: "bluetooth" | "builtin" | "other"; name: string };
 
 type Events = { onVoiceRecognitionEnded: (event: { reason: string }) => void };
 
@@ -9,6 +11,8 @@ declare class AudioRouteModule extends NativeModule<Events> {
   stopVoiceRecognition(reason: string): Promise<void>;
   acquireSco(timeoutMs: number): Promise<RouteResult>;
   releaseSco(): Promise<void>;
+  getMediaVolume(): MediaVolume;
+  activeInputDevice(): InputDevice | null;
 }
 
 export default requireNativeModule<AudioRouteModule>("AudioRoute");
```

- [ ] **Step 2: 型を確かめる**

Run: `cd $APP && npx tsc --noEmit && npx jest`
Expected: 型のエラー 0、90 passed。

- [ ] **Step 3: コミット**

```bash
cd $APP && git add modules/audio-route/android/src/main/java/com/touringproject/v2/audioroute/AudioRouteModule.kt modules/audio-route/src/index.ts
git commit -m "feat: read the media volume and the active input device; settle SCO on the main thread"
```

---

### Task 7: App: 録音の付随情報（spec §5.4）

**Files:**
- Create: `App/src/ask/recordingFiles.ts`
- Modify: `App/src/ask/recordings.ts`、`src/ask/controller.ts`、`src/ask/runtime.ts`
- Test: `App/src/ask/__tests__/recordings.test.ts`、`src/ask/__tests__/controller.test.ts`

**Interfaces:**
- Consumes: `InputDevice`（Task 6）、`AudioRoute.activeInputDevice()`。
- Produces:
  - `recordings.ts`: `RecordingMeta = { name; recordedAt; durationMs; phoneMic; device: InputDevice | null; transcript: string | null }`、`metaName(pcmName)`、`recordingsToDelete(names, keep?)`（PCM と JSON を組で）、`base64Bytes(b64)`、`pcmDurationMs(bytes)`、`parseMeta(text)`、`newestFirst(metas)`、`wavHeader(pcmBytes): Uint8Array`、`micLabel({ phoneMic, device })`。
  - `recordingFiles.ts`: `RECORDINGS_DIR`、`newRecordingUri(now)`、`pruneRecordings()`、`saveMeta(meta)`、`setTranscript(name, transcript)`、`listRecordings()`、`deleteAllRecordings()`、`recordingUri(name)`、`wavFromPcm(pcmUri, wavName): Promise<string>`。
  - `Deps`: `route.inputDevice()`、`recorder.stop(): Promise<{ audio; name }>`、`recordings: { saved(meta); transcribed(name, transcript) }`。
  - `runtime.ts`: `export class PcmStream { start(uri); stop(): Promise<string>; cancel() }`（Task 9 の試し録りでも使う）。

- [ ] **Step 1: 失敗するテストを書く**

`App/src/ask/__tests__/recordings.test.ts` を置き換える:

```ts
import {
  base64Bytes, metaName, micLabel, newestFirst, parseMeta, pcmDurationMs, recordingName, recordingsToDelete, RecordingMeta, wavHeader,
} from "../recordings";

const META: RecordingMeta = {
  name: "rec-1000.pcm", recordedAt: 1000, durationMs: 3000, phoneMic: false, device: { type: "bluetooth", name: "M1-S PRO" }, transcript: null,
};

test("name carries the time", () => {
  expect(recordingName(1234)).toBe("rec-1234.pcm");
  expect(metaName("rec-1234.pcm")).toBe("rec-1234.json");
});

test("keeps the newest ten recordings", () => {
  const names = Array.from({ length: 12 }, (_, i) => recordingName(1000 + i)).concat(["notes.txt"]);
  expect(recordingsToDelete(names).sort()).toEqual(["rec-1000.pcm", "rec-1001.pcm"]);
  expect(recordingsToDelete(names.slice(0, 3))).toEqual([]);
});

test("an old recording's JSON goes with its PCM", () => {
  const names = Array.from({ length: 11 }, (_, i) => [recordingName(1000 + i), metaName(recordingName(1000 + i))]).flat();
  expect(recordingsToDelete(names).sort()).toEqual(["rec-1000.json", "rec-1000.pcm"]);
});

test("PCM size to duration", () => {
  expect(base64Bytes("AAAA")).toBe(3);
  expect(base64Bytes("AAA=")).toBe(2);
  expect(base64Bytes("AA==")).toBe(1);
  expect(pcmDurationMs(32_000 * 3)).toBe(3000);
  expect(pcmDurationMs(16_000)).toBe(500);
});

test("meta round trips and broken meta is rejected", () => {
  expect(parseMeta(JSON.stringify(META))).toEqual(META);
  expect(parseMeta(JSON.stringify({ ...META, device: { type: "x" }, transcript: 3 }))).toEqual({ ...META, device: null, transcript: null });
  expect(parseMeta("{oops")).toBeNull();
  expect(parseMeta("null")).toBeNull();
  expect(parseMeta(JSON.stringify({ ...META, name: "../x" }))).toBeNull();
  expect(parseMeta(JSON.stringify({ ...META, durationMs: "3" }))).toBeNull();
});

test("newest first", () => {
  const older = { ...META, name: "rec-1.pcm", recordedAt: 1 };
  expect(newestFirst([older, META]).map((m) => m.name)).toEqual(["rec-1000.pcm", "rec-1.pcm"]);
});

test("WAV header for 16 kHz mono 16-bit", () => {
  const h = wavHeader(32_000);
  const view = new DataView(h.buffer);
  const text = (from: number) => String.fromCharCode(...h.slice(from, from + 4));
  expect(h).toHaveLength(44);
  expect([text(0), text(8), text(12), text(36)]).toEqual(["RIFF", "WAVE", "fmt ", "data"]);
  expect(view.getUint32(4, true)).toBe(36 + 32_000);
  expect(view.getUint16(20, true)).toBe(1);
  expect(view.getUint16(22, true)).toBe(1);
  expect(view.getUint32(24, true)).toBe(16_000);
  expect(view.getUint32(28, true)).toBe(32_000);
  expect(view.getUint16(32, true)).toBe(2);
  expect(view.getUint16(34, true)).toBe(16);
  expect(view.getUint32(40, true)).toBe(32_000);
});

test("mic label", () => {
  expect(micLabel(META)).toBe("インカム（M1-S PRO）");
  expect(micLabel({ phoneMic: true, device: null })).toBe("本体のマイク");
});
```

```diff
diff --git a/src/ask/__tests__/controller.test.ts b/src/ask/__tests__/controller.test.ts
--- a/src/ask/__tests__/controller.test.ts
+++ b/src/ask/__tests__/controller.test.ts
@@ -3,6 +3,7 @@ import { Settings } from "../../settings/store";
 import { AskApi, AskController, Deps, RECORD_LIMIT_MS } from "../controller";
 import { ConversationState } from "../conversation";
 import { FlowState } from "../flow";
+import { RecordingMeta } from "../recordings";
 
 const MAPS = { packageName: "maps", label: "マップ" };
 const SETTINGS: Settings = { userName: "rider01", returnEnabled: true, returnApp: MAPS, returnTiming: "sent", recentApps: [], answerVolumeDb: 6 };
@@ -24,12 +25,15 @@ type Options = {
   micAllowed?: boolean;
   sayGate?: Promise<void>;
   serviceError?: Error;
+  device?: { type: "bluetooth" | "builtin" | "other"; name: string } | null;
 };
 
 function harness(options: Options = {}) {
   const log: string[] = [];
   const states: FlowState[] = [];
   const bodies: AskBody[] = [];
+  const metas: RecordingMeta[] = [];
+  const transcripts: [string, string][] = [];
   let now = 0;
   const results = [...(options.results ?? [done()])];
   let controller!: AskController;
@@ -48,8 +52,17 @@ function harness(options: Options = {}) {
     micAllowed: async () => options.micAllowed ?? true,
     api: () => api,
     conversation: new ConversationState(),
-    route: { start: async (source) => { log.push(`route:${source}`); return options.routeOk ?? true; }, stop: async () => { log.push("route:stop"); } },
-    recorder: { start: async () => { log.push("rec:start"); }, stop: async () => { log.push("rec:stop"); return "UENN"; }, cancel: async () => { log.push("rec:cancel"); } },
+    route: {
+      start: async (source) => { log.push(`route:${source}`); return options.routeOk ?? true; },
+      stop: async () => { log.push("route:stop"); },
+      inputDevice: () => (options.device === undefined ? { type: "bluetooth", name: "M1-S PRO" } : options.device),
+    },
+    recorder: {
+      start: async () => { log.push("rec:start"); },
+      stop: async () => { log.push("rec:stop"); return { audio: "UENN", name: "rec-0.pcm" }; },
+      cancel: async () => { log.push("rec:cancel"); },
+    },
+    recordings: { saved: (meta) => { metas.push(meta); }, transcribed: (name, text) => { transcripts.push([name, text]); } },
     location: { begin: () => { log.push("loc:begin"); }, end: () => ({ current: HERE, fixes: [BEHIND, HERE] }) },
     service: { start: () => { log.push("svc:start"); if (options.serviceError) throw options.serviceError; }, stop: () => { log.push("svc:stop"); } },
     nav: { returnTo: async (pkg) => { log.push(`return:${pkg}`); return true; } },
@@ -60,7 +73,7 @@ function harness(options: Options = {}) {
     log: () => undefined,
   };
   controller = new AskController(deps);
-  return { controller, log, states, bodies, deps, now: () => now };
+  return { controller, log, states, bodies, metas, transcripts, deps, now: () => now };
 }
 
 test("handsfree happy path returns to nav right after sending", async () => {
@@ -292,3 +305,25 @@ test("a foreground service that cannot start fails out loud", async () => {
   expect(h.states.some((s) => s.phase === "failed" && s.failure === "service")).toBe(true);
   expect(h.controller.state.phase).toBe("idle");
 });
+
+test("the kept recording is described for SC-12", async () => {
+  const h = harness({ stopAfterMs: 3000 });
+  await h.controller.run("handsfree");
+  // "UENN" is 3 bytes of PCM.
+  expect(h.metas).toEqual([
+    { name: "rec-0.pcm", recordedAt: 0, durationMs: 0, phoneMic: false, device: { type: "bluetooth", name: "M1-S PRO" }, transcript: null },
+  ]);
+  expect(h.transcripts).toEqual([["rec-0.pcm", "Q"]]);
+});
+
+test("a phone-mic recording is marked so", async () => {
+  const h = harness({ stopAfterMs: 1000, routeOk: false, device: { type: "builtin", name: "Pixel" } });
+  await h.controller.run("handsfree");
+  expect(h.metas[0]).toMatchObject({ phoneMic: true, device: { type: "builtin", name: "Pixel" } });
+});
+
+test("what was heard is kept even when the answer fails", async () => {
+  const h = harness({ stopAfterMs: 1000, results: [done({ status: "failed", transcript: "", answer: null, audio: [], error: "no_speech" })] });
+  await h.controller.run("handsfree");
+  expect(h.transcripts).toEqual([["rec-0.pcm", ""]]);
+});
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $APP && npx jest src/ask`
Expected: FAIL（`metaName` などが無い・`recordings` が Deps に無い）

- [ ] **Step 3: 実装する**

`App/src/ask/recordings.ts` を置き換える:

```ts
// The last few recordings stay on the device for the recording check screen (US-C-06.001). Each PCM file has a
// JSON file of the same name beside it with what SC-12 shows (spec §5.4).
import type { InputDevice } from "../../modules/audio-route/src";

export const KEEP_RECORDINGS = 10;
export const PCM_BYTES_PER_SECOND = 16_000 * 2; // 16 kHz, mono, 16-bit
const NAME_RE = /^rec-(\d+)\.(pcm|json)$/;

export type RecordingMeta = {
  name: string; // the PCM file name
  recordedAt: number;
  durationMs: number;
  phoneMic: boolean;
  device: InputDevice | null;
  transcript: string | null;
};

export function recordingName(now: number): string {
  return `rec-${now}.pcm`;
}

export function metaName(pcmName: string): string {
  return pcmName.replace(/\.pcm$/, ".json");
}

/** Files of all but the newest `keep` recordings: the PCM and its JSON go together. */
export function recordingsToDelete(names: string[], keep = KEEP_RECORDINGS): string[] {
  const parsed = names.map((name) => ({ name, match: NAME_RE.exec(name) })).filter((r) => r.match !== null);
  const times = [...new Set(parsed.map((r) => Number(r.match![1])))].sort((a, b) => b - a);
  const old = new Set(times.slice(keep));
  return parsed.filter((r) => old.has(Number(r.match![1]))).map((r) => r.name);
}

export function base64Bytes(base64: string): number {
  const padding = base64.endsWith("==") ? 2 : base64.endsWith("=") ? 1 : 0;
  return (base64.length / 4) * 3 - padding;
}

export function pcmDurationMs(bytes: number): number {
  return Math.round((bytes / PCM_BYTES_PER_SECOND) * 1000);
}

function isDevice(value: unknown): value is InputDevice {
  const d = value as InputDevice;
  return typeof d === "object" && d !== null && ["bluetooth", "builtin", "other"].includes(d.type) && typeof d.name === "string";
}

export function parseMeta(text: string): RecordingMeta | null {
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof raw !== "object" || raw === null) return null;
  if (typeof raw.name !== "string" || !NAME_RE.test(raw.name)) return null;
  if (typeof raw.recordedAt !== "number" || typeof raw.durationMs !== "number" || typeof raw.phoneMic !== "boolean") return null;
  return {
    name: raw.name,
    recordedAt: raw.recordedAt,
    durationMs: raw.durationMs,
    phoneMic: raw.phoneMic,
    device: isDevice(raw.device) ? raw.device : null,
    transcript: typeof raw.transcript === "string" ? raw.transcript : null,
  };
}

export function newestFirst(metas: RecordingMeta[]): RecordingMeta[] {
  return [...metas].sort((a, b) => b.recordedAt - a.recordedAt);
}

/** A 44-byte RIFF/WAVE header for 16 kHz mono 16-bit PCM; expo-audio cannot play raw PCM. */
export function wavHeader(pcmBytes: number): Uint8Array {
  const header = new Uint8Array(44);
  const view = new DataView(header.buffer);
  const ascii = (offset: number, text: string) => [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  ascii(0, "RIFF");
  view.setUint32(4, 36 + pcmBytes, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, 16_000, true); // sample rate
  view.setUint32(28, PCM_BYTES_PER_SECOND, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  ascii(36, "data");
  view.setUint32(40, pcmBytes, true);
  return header;
}

/** One-line label of the microphone for SC-12. */
export function micLabel(meta: Pick<RecordingMeta, "phoneMic" | "device">): string {
  const kind = meta.phoneMic ? "本体のマイク" : "インカム";
  return meta.device ? `${kind}（${meta.device.name}）` : kind;
}
```

```diff
diff --git a/src/ask/controller.ts b/src/ask/controller.ts
--- a/src/ask/controller.ts
+++ b/src/ask/controller.ts
@@ -1,5 +1,6 @@
 // Orchestrates one ask: record -> send -> (return to nav) -> wait -> speak. All side effects come in through Deps
 // so the whole loop is testable; waits use deps.sleep, which is native in the app (setTimeout stops in the background).
+import type { InputDevice } from "../../modules/audio-route/src";
 import { ApiError, AskAccepted, AskBody, AskResult } from "../api/client";
 import type { Settings } from "../settings/store";
 import { Fix, pickHeadingSample } from "../location/heading";
@@ -7,6 +8,7 @@ import { ConversationState } from "./conversation";
 import { BUSY_MESSAGE, failureFromServer, spokenMessage } from "./failures";
 import { FailureReason, FlowEvent, FlowState, IDLE, isBusy, Moment, reduce, shouldReturnNow, Source } from "./flow";
 import { pollUntilDone } from "./polling";
+import { base64Bytes, pcmDurationMs, RecordingMeta } from "./recordings";
 
 export const RECORD_LIMIT_MS = 20_000;
 export const TICK_MS = 250;
@@ -26,8 +28,11 @@ export type Deps = {
   micAllowed(): Promise<boolean>;
   api(apiKey: string, userName: string): AskApi;
   conversation: ConversationState;
-  route: { start(source: Source): Promise<boolean>; stop(): Promise<void> };
-  recorder: { start(): Promise<void>; stop(): Promise<string>; cancel(): Promise<void> };
+  route: { start(source: Source): Promise<boolean>; stop(): Promise<void>; inputDevice(): InputDevice | null };
+  // stop() returns the PCM as base64 and the name of the file it stays in (spec §5.4).
+  recorder: { start(): Promise<void>; stop(): Promise<{ audio: string; name: string }>; cancel(): Promise<void> };
+  // What SC-12 shows about each kept recording. Fire and forget: a failure here must not end the ask.
+  recordings: { saved(meta: RecordingMeta): void; transcribed(name: string, transcript: string): void };
   location: { begin(): void; end(): { current: Fix | null; fixes: Fix[] } };
   service: { start(): void; stop(): void };
   nav: { returnTo(packageName: string): Promise<boolean> };
@@ -38,7 +43,7 @@ export type Deps = {
   log(event: string, data?: Record<string, unknown>): void;
 };
 
-type Recording = { audio: string; current: Fix | null; fixes: Fix[] };
+type Recording = { audio: string; name: string; current: Fix | null; fixes: Fix[] };
 // Per-ask state: an older ask that is still unwinding must not read or change the newer one's.
 type Run = { id: number; source: Source; returned: boolean };
 
@@ -126,7 +131,7 @@ export class AskController {
       const accepted = await this.send(recording, api, run);
       if (accepted === null) return;
       await this.maybeReturn("sent", settings, run);
-      const result = await this.waitForAnswer(accepted.askId, api, run);
+      const result = await this.waitForAnswer(accepted.askId, recording.name, api, run);
       if (result === null) return;
       await this.speak(result, settings, run);
     } finally {
@@ -191,10 +196,13 @@ export class AskController {
       d.location.end();
       return null;
     }
+    // Read while the recorder still runs: the system only reports the input device of an active recording.
+    const device = d.route.inputDevice();
+    const phoneMic = this.state.phoneMic;
     this.stopRecording();
-    let audio: string;
+    let stopped: { audio: string; name: string };
     try {
-      audio = await d.recorder.stop();
+      stopped = await d.recorder.stop();
     } catch {
       await d.route.stop();
       d.location.end();
@@ -202,8 +210,11 @@ export class AskController {
       return null;
     }
     await d.route.stop();
+    d.recordings.saved({
+      name: stopped.name, recordedAt: startedAt, durationMs: pcmDurationMs(base64Bytes(stopped.audio)), phoneMic, device, transcript: null,
+    });
     const { current, fixes } = d.location.end();
-    return { audio, current, fixes };
+    return { audio: stopped.audio, name: stopped.name, current, fixes };
   }
 
   private async send(recording: Recording, api: AskApi, run: Run): Promise<AskAccepted | null> {
@@ -231,7 +242,7 @@ export class AskController {
     return accepted;
   }
 
-  private async waitForAnswer(askId: string, api: AskApi, run: Run): Promise<AskResult | null> {
+  private async waitForAnswer(askId: string, recordingName: string, api: AskApi, run: Run): Promise<AskResult | null> {
     const d = this.deps;
     let sinceCue = 0;
     const sleep = async (ms: number) => {
@@ -249,6 +260,7 @@ export class AskController {
       await this.fail(reasonFor(error), run);
       return null;
     }
+    if (typeof outcome === "object" && outcome.transcript !== null) d.recordings.transcribed(recordingName, outcome.transcript);
     if (outcome === "cancelled" || !this.isCurrent(run)) return null;
     if (outcome === "timeout") {
       await this.fail("timeout", run);
```

`App/src/ask/recordingFiles.ts` を作る（ディレクトリは録音がすでに使っている `legacy` の API で扱い、WAV のバイト列だけ新しい `File` を使う）:

```ts
// The kept recordings on disk (spec §5.4): rec-<time>.pcm with rec-<time>.json beside it. Thin on purpose; the
// decisions are in recordings.ts. Directories use the legacy API the recorder already uses; WAV needs raw bytes.
import { File, Paths } from "expo-file-system";
import {
  deleteAsync, documentDirectory, getInfoAsync, makeDirectoryAsync, readAsStringAsync, readDirectoryAsync, writeAsStringAsync,
} from "expo-file-system/legacy";

import { metaName, newestFirst, parseMeta, recordingName, RecordingMeta, recordingsToDelete, wavHeader } from "./recordings";

export const RECORDINGS_DIR = `${documentDirectory}recordings/`;

export async function newRecordingUri(now: number): Promise<{ uri: string; name: string }> {
  await makeDirectoryAsync(RECORDINGS_DIR, { intermediates: true });
  const name = recordingName(now);
  return { uri: `${RECORDINGS_DIR}${name}`, name };
}

export async function pruneRecordings(): Promise<void> {
  const names = await readDirectoryAsync(RECORDINGS_DIR);
  await Promise.all(recordingsToDelete(names).map((name) => deleteAsync(`${RECORDINGS_DIR}${name}`, { idempotent: true })));
}

export async function saveMeta(meta: RecordingMeta): Promise<void> {
  await writeAsStringAsync(`${RECORDINGS_DIR}${metaName(meta.name)}`, JSON.stringify(meta));
}

export async function setTranscript(name: string, transcript: string): Promise<void> {
  const uri = `${RECORDINGS_DIR}${metaName(name)}`;
  if (!(await getInfoAsync(uri)).exists) return;
  const meta = parseMeta(await readAsStringAsync(uri));
  if (meta) await writeAsStringAsync(uri, JSON.stringify({ ...meta, transcript }));
}

export async function listRecordings(): Promise<RecordingMeta[]> {
  if (!(await getInfoAsync(RECORDINGS_DIR)).exists) return [];
  const names = new Set(await readDirectoryAsync(RECORDINGS_DIR));
  const metas: RecordingMeta[] = [];
  for (const name of names) {
    if (!name.endsWith(".json")) continue;
    const meta = parseMeta(await readAsStringAsync(`${RECORDINGS_DIR}${name}`).catch(() => ""));
    if (meta && names.has(meta.name)) metas.push(meta);
  }
  return newestFirst(metas);
}

export async function deleteAllRecordings(): Promise<void> {
  await deleteAsync(RECORDINGS_DIR, { idempotent: true });
}

export function recordingUri(name: string): string {
  return `${RECORDINGS_DIR}${name}`;
}

/** Copies a PCM file into a playable WAV file in the cache and returns its URI. */
export async function wavFromPcm(pcmUri: string, wavName: string): Promise<string> {
  const pcm = await new File(pcmUri).bytes();
  const wav = new Uint8Array(44 + pcm.length);
  wav.set(wavHeader(pcm.length), 0);
  wav.set(pcm, 44);
  const out = new File(Paths.cache, wavName);
  await out.write(wav);
  return out.uri;
}
```

`runtime.ts` の録音を、ファイルの扱いを `recordingFiles.ts` に任せる形に組み替える:

```diff
diff --git a/src/ask/runtime.ts b/src/ask/runtime.ts
--- a/src/ask/runtime.ts
+++ b/src/ask/runtime.ts
@@ -1,7 +1,7 @@
 // Real implementations of the controller's Deps. Kept thin: the decisions live in controller.ts.
 import { createAudioPlayer, getRecordingPermissionsAsync, requestRecordingPermissionsAsync, setAudioModeAsync } from "expo-audio";
 import AudioModule from "expo-audio/build/AudioModule";
-import { deleteAsync, documentDirectory, makeDirectoryAsync, readAsStringAsync, readDirectoryAsync } from "expo-file-system/legacy";
+import { deleteAsync, readAsStringAsync } from "expo-file-system/legacy";
 import * as Location from "expo-location";
 import * as Speech from "expo-speech";
 import { PermissionsAndroid } from "react-native";
@@ -17,9 +17,7 @@ import { Deps } from "./controller";
 import { ConversationState } from "./conversation";
 import { FlowState, Source } from "./flow";
 import { ClipPlayer, playClips } from "./playback";
-import { recordingName, recordingsToDelete } from "./recordings";
-
-const RECORDINGS_DIR = `${documentDirectory}recordings/`;
+import { newRecordingUri, pruneRecordings, saveMeta, setTranscript } from "./recordingFiles";
 const VR_TIMEOUT_MS = 4000;
 const SCO_TIMEOUT_MS = 3000;
 // Intercoms drop the first part of a sound: a 1 s tone is heard as a short blip, so the start cue is longer.
@@ -34,26 +32,25 @@ export async function requestPermissions(): Promise<void> {
   ] as Parameters<typeof PermissionsAndroid.requestMultiple>[0]);
 }
 
-class PcmRecorder {
+// 16 kHz mono 16-bit PCM into a file (adr/0002). Shared by questions and the trial recording on SC-12.
+export class PcmStream {
   private stream: InstanceType<typeof AudioModule.AudioStream> | null = null;
 
-  async start(): Promise<void> {
-    await makeDirectoryAsync(RECORDINGS_DIR, { intermediates: true });
+  async start(uri: string): Promise<void> {
     const stream = new AudioModule.AudioStream({ sampleRate: 16000, channels: 1, encoding: "int16" });
     await stream.start();
-    await stream.startFileRecordingAsync({ uri: `${RECORDINGS_DIR}${recordingName(Date.now())}`, format: "pcm" });
+    await stream.startFileRecordingAsync({ uri, format: "pcm" });
     this.stream = stream;
   }
 
+  /** Stops and returns the file's URI. */
   async stop(): Promise<string> {
     const stream = this.stream;
     this.stream = null;
     if (!stream) throw new Error("not recording");
     const file = await stream.stopFileRecordingAsync();
     stream.stop();
-    const base64 = await readAsStringAsync(file.uri, { encoding: "base64" });
-    await this.prune();
-    return base64;
+    return file.uri;
   }
 
   async cancel(): Promise<void> {
@@ -64,10 +61,31 @@ class PcmRecorder {
     stream.stop();
     if (file) await deleteAsync(file.uri, { idempotent: true });
   }
+}
+
+// Questions are kept (the newest ten) for SC-12.
+class AskRecorder {
+  private readonly stream = new PcmStream();
+  private name: string | null = null;
+
+  async start(): Promise<void> {
+    const target = await newRecordingUri(Date.now());
+    await this.stream.start(target.uri);
+    this.name = target.name;
+  }
+
+  async stop(): Promise<{ audio: string; name: string }> {
+    const uri = await this.stream.stop();
+    const name = this.name!;
+    this.name = null;
+    const audio = await readAsStringAsync(uri, { encoding: "base64" });
+    await pruneRecordings();
+    return { audio, name };
+  }
 
-  private async prune(): Promise<void> {
-    const names = await readDirectoryAsync(RECORDINGS_DIR);
-    await Promise.all(recordingsToDelete(names).map((name) => deleteAsync(`${RECORDINGS_DIR}${name}`, { idempotent: true })));
+  async cancel(): Promise<void> {
+    this.name = null;
+    await this.stream.cancel();
   }
 }
 
@@ -97,7 +115,7 @@ export function createRuntimeDeps(options: {
   void setAudioModeAsync({ shouldPlayInBackground: true, playsInSilentMode: true, interruptionMode: "mixWithOthers" }).then(() =>
     AudioRoute.releaseSco(),
   );
-  const recorder = new PcmRecorder();
+  const recorder = new AskRecorder();
   const positions = createPositionTracker();
   const playback: { stop: (() => void) | null } = { stop: null };
   let routeSource: Source | null = null;
@@ -123,8 +141,15 @@ export function createRuntimeDeps(options: {
         else await AudioRoute.releaseSco();
         routeSource = null;
       },
+      inputDevice: () => AudioRoute.activeInputDevice(),
     },
     recorder,
+    recordings: {
+      saved: (meta) => { void saveMeta(meta).catch((e) => console.log(JSON.stringify({ event: "meta_failed", error: String(e) }))); },
+      transcribed: (name, transcript) => {
+        void setTranscript(name, transcript).catch((e) => console.log(JSON.stringify({ event: "meta_failed", error: String(e) })));
+      },
+    },
     location: positions,
     service: { start: () => RideService.startService(), stop: () => RideService.stopService() },
     nav: { returnTo: (packageName) => RideService.launchApp(packageName) },
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: 99 passed、型のエラー 0。

- [ ] **Step 5: コミット**

```bash
cd $APP && git add src/ask/recordings.ts src/ask/recordingFiles.ts src/ask/controller.ts src/ask/runtime.ts \
  src/ask/__tests__/recordings.test.ts src/ask/__tests__/controller.test.ts
git commit -m "feat: describe each kept recording for the recording check screen"
```

---

### Task 8: App: 試し録りの司令塔（spec §5.5）

**Files:**
- Create: `App/src/ask/trial.ts`、`src/ask/__tests__/trial.test.ts`

**Interfaces:**
- Consumes: `RECORD_LIMIT_MS`・`TICK_MS`（`controller.ts`）、`InputDevice`。
- Produces: `TrialState = { phase: "idle" | "recording" | "playing"; phoneMic; device; error }`、`TRIAL_IDLE`、`TRIAL_MESSAGES`、`TrialDeps`、`class TrialController { state; active; start(); stop(); cancel() }`。

- [ ] **Step 1: 失敗するテストを書く**

`App/src/ask/__tests__/trial.test.ts` を作る:

```ts
import { RECORD_LIMIT_MS } from "../controller";
import { TRIAL_MESSAGES, TrialController, TrialDeps, TrialState } from "../trial";

type Options = {
  routeOk?: boolean;
  micAllowed?: boolean;
  recorderError?: boolean;
  playError?: boolean;
  stopAfterMs?: number | null;
  holdPlayback?: boolean; // playback lasts until stopPlayback()
};

function harness(options: Options = {}) {
  const log: string[] = [];
  const states: TrialState[] = [];
  let now = 0;
  let trial!: TrialController;
  let endPlayback: (() => void) | null = null;
  const deps: TrialDeps = {
    now: () => now,
    sleep: async (ms) => {
      now += ms;
      if (options.stopAfterMs != null && now >= options.stopAfterMs) trial.stop();
    },
    micAllowed: async () => options.micAllowed ?? true,
    route: {
      start: async () => { log.push("route:start"); return options.routeOk ?? true; },
      stop: async () => { log.push("route:stop"); },
      inputDevice: () => ({ type: "bluetooth", name: "M1-S PRO" }),
    },
    recorder: {
      start: async () => { log.push("rec:start"); if (options.recorderError) throw new Error("busy"); },
      stop: async () => { log.push("rec:stop"); return "file:///trial.pcm"; },
      cancel: async () => { log.push("rec:cancel"); },
    },
    cueStart: () => log.push("cue:start"),
    play: async (uri) => {
      log.push(`play:${uri}`);
      if (options.playError) throw new Error("bad");
      if (options.holdPlayback) await new Promise<void>((resolve) => { endPlayback = resolve; });
    },
    stopPlayback: () => { log.push("play:stop"); endPlayback?.(); },
    discard: async (uri) => { log.push(`discard:${uri}`); },
    onState: (s) => states.push(s),
  };
  trial = new TrialController(deps);
  return { trial, log, states, now: () => now };
}

test("records, plays back at once and throws the file away", async () => {
  const h = harness({ stopAfterMs: 3000 });
  await h.trial.start();
  expect(h.log).toEqual(["route:start", "rec:start", "cue:start", "rec:stop", "route:stop", "play:file:///trial.pcm", "discard:file:///trial.pcm"]);
  expect(h.states.map((s) => s.phase)).toEqual(["recording", "recording", "playing", "idle"]);
  expect(h.trial.state).toEqual({ phase: "idle", phoneMic: false, device: { type: "bluetooth", name: "M1-S PRO" }, error: null });
});

test("stops by itself at the question limit", async () => {
  const h = harness({ stopAfterMs: null });
  await h.trial.start();
  expect(h.now()).toBeGreaterThanOrEqual(RECORD_LIMIT_MS);
  expect(h.log).toContain("play:file:///trial.pcm");
});

test("shows that the phone microphone was used when the intercom route fails", async () => {
  const h = harness({ stopAfterMs: 1000, routeOk: false });
  await h.trial.start();
  expect(h.trial.state.phoneMic).toBe(true);
});

test("a denied microphone is said on screen and nothing is recorded", async () => {
  const h = harness({ micAllowed: false });
  await h.trial.start();
  expect(h.log).toEqual([]);
  expect(h.trial.state).toMatchObject({ phase: "idle", error: TRIAL_MESSAGES.mic });
});

test("a recorder that cannot start releases the route", async () => {
  const h = harness({ recorderError: true });
  await h.trial.start();
  expect(h.log).toEqual(["route:start", "rec:start", "route:stop"]);
  expect(h.trial.state).toMatchObject({ phase: "idle", error: TRIAL_MESSAGES.record });
});

test("a playback failure is said and the file is still discarded", async () => {
  const h = harness({ stopAfterMs: 1000, playError: true });
  await h.trial.start();
  expect(h.log).toContain("discard:file:///trial.pcm");
  expect(h.trial.state).toMatchObject({ phase: "idle", error: TRIAL_MESSAGES.play });
});

test("leaving the screen while recording cancels without playing", async () => {
  const h = harness({ stopAfterMs: null });
  const running = h.trial.start();
  while (h.trial.state.phase !== "recording" || !h.log.includes("cue:start")) await Promise.resolve();
  h.trial.cancel();
  await running;
  expect(h.log).toContain("rec:cancel");
  expect(h.log).toContain("route:stop");
  expect(h.log.some((l) => l.startsWith("play:file"))).toBe(false);
  expect(h.trial.state.phase).toBe("idle");
});

test("a second start while one runs is ignored", async () => {
  const h = harness({ stopAfterMs: 1000 });
  const first = h.trial.start();
  void h.trial.start();
  await first;
  expect(h.log.filter((l) => l === "rec:start")).toHaveLength(1);
});

test("stop during playback stops the playback", async () => {
  const h = harness({ stopAfterMs: 1000, holdPlayback: true });
  const running = h.trial.start();
  while (h.trial.state.phase !== "playing") await Promise.resolve();
  h.trial.stop();
  await running;
  expect(h.log).toContain("play:stop");
  expect(h.trial.state.phase).toBe("idle");
});
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $APP && npx jest src/ask/__tests__/trial.test.ts`
Expected: FAIL（`../trial` が無い）

- [ ] **Step 3: 実装する**

`App/src/ask/trial.ts` を作る:

```ts
// The trial recording on SC-12 (spec §5.5): recorded over the same route as a question started from the screen,
// played back at once on the media stream, sent nowhere and not kept.
import type { InputDevice } from "../../modules/audio-route/src";
import { RECORD_LIMIT_MS, TICK_MS } from "./controller";

export type TrialPhase = "idle" | "recording" | "playing";
export type TrialState = { phase: TrialPhase; phoneMic: boolean; device: InputDevice | null; error: string | null };
export const TRIAL_IDLE: TrialState = { phase: "idle", phoneMic: false, device: null, error: null };

export type TrialDeps = {
  now(): number;
  sleep(ms: number): Promise<void>;
  micAllowed(): Promise<boolean>;
  route: { start(): Promise<boolean>; stop(): Promise<void>; inputDevice(): InputDevice | null };
  // stop() returns the URI of the recorded PCM file.
  recorder: { start(): Promise<void>; stop(): Promise<string>; cancel(): Promise<void> };
  cueStart(): void;
  play(pcmUri: string): Promise<void>;
  stopPlayback(): void;
  discard(pcmUri: string): Promise<void>;
  onState(state: TrialState): void;
};

export const TRIAL_MESSAGES = {
  mic: "マイクの使用が許可されていません。",
  record: "録音できませんでした。",
  play: "再生できませんでした。",
} as const;

export class TrialController {
  state: TrialState = TRIAL_IDLE;
  private session = 0;
  private stopRequested = false;

  constructor(private readonly deps: TrialDeps) {}

  get active(): boolean {
    return this.state.phase !== "idle";
  }

  /** The screen button or the intercom button while a trial runs: end the recording, or the playback. */
  stop(): void {
    if (this.state.phase === "recording") this.stopRequested = true;
    else if (this.state.phase === "playing") this.deps.stopPlayback();
  }

  /** Leaving SC-12: drop whatever is going on. */
  cancel(): void {
    if (!this.active) return;
    this.session += 1;
    this.deps.stopPlayback();
    this.set(TRIAL_IDLE);
  }

  async start(): Promise<void> {
    if (this.active) return;
    const d = this.deps;
    const session = ++this.session;
    this.stopRequested = false;
    this.set({ ...TRIAL_IDLE, phase: "recording" });
    if (!(await d.micAllowed())) {
      this.finish(session, { ...TRIAL_IDLE, error: TRIAL_MESSAGES.mic });
      return;
    }
    const routed = await d.route.start();
    try {
      await d.recorder.start();
    } catch {
      await d.route.stop();
      this.finish(session, { ...TRIAL_IDLE, phoneMic: !routed, error: TRIAL_MESSAGES.record });
      return;
    }
    if (session === this.session) this.set({ ...this.state, phoneMic: !routed });
    d.cueStart();
    const startedAt = d.now();
    while (session === this.session && !this.stopRequested && d.now() - startedAt < RECORD_LIMIT_MS) {
      await d.sleep(TICK_MS);
    }
    if (session !== this.session) {
      await d.recorder.cancel();
      await d.route.stop();
      return;
    }
    const device = d.route.inputDevice();
    let uri: string;
    try {
      uri = await d.recorder.stop();
    } catch {
      await d.route.stop();
      this.finish(session, { ...TRIAL_IDLE, phoneMic: !routed, error: TRIAL_MESSAGES.record });
      return;
    }
    await d.route.stop();
    if (session !== this.session) {
      await d.discard(uri);
      return;
    }
    this.set({ ...this.state, phase: "playing", device });
    let error: string | null = null;
    try {
      await d.play(uri);
    } catch {
      error = TRIAL_MESSAGES.play;
    } finally {
      await d.discard(uri);
    }
    // Keep showing which microphone was used after the playback.
    this.finish(session, { ...this.state, phase: "idle", error });
  }

  private finish(session: number, state: TrialState): void {
    if (session === this.session) this.set(state);
  }

  private set(state: TrialState): void {
    this.state = state;
    this.deps.onState(state);
  }
}
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: 108 passed、型のエラー 0。

- [ ] **Step 5: コミット**

```bash
cd $APP && git add src/ask/trial.ts src/ask/__tests__/trial.test.ts
git commit -m "feat: add the trial recording controller"
```

---

### Task 9: App: 録音の確認の画面（SC-12）と配線

**Files:**
- Create: `App/app/settings/recordings.tsx`、`src/ui/recordingLabel.ts`、`src/ui/__tests__/recordingLabel.test.ts`
- Modify: `App/src/ask/runtime.ts`、`src/ask/AskProvider.tsx`

**Interfaces:**
- Consumes: Task 7・8 のすべて。
- Produces: `createRuntimeDeps()` が `{ deps, trialDeps(onState), playRecording(name), stopPlayback(), dispose() }` を返す。`useAsk()` に `trial: TrialController | null`・`trialState`・`playRecording(name)`・`stopPlayback()`。`recordedAtLabel(ms)`・`durationLabel(ms)`・`transcriptLabel(t)`。

- [ ] **Step 1: 失敗するテストを書く**

`App/src/ui/__tests__/recordingLabel.test.ts` を作る:

```ts
import { durationLabel, recordedAtLabel, transcriptLabel } from "../recordingLabel";

test("recorded time in Japan time", () => {
  expect(recordedAtLabel(Date.parse("2026-10-16T23:05:09Z"))).toBe("10/17 08:05:09");
});

test("duration in seconds", () => {
  expect(durationLabel(3240)).toBe("3.2秒");
  expect(durationLabel(0)).toBe("0.0秒");
});

test("transcript: not yet, nothing heard, or the text", () => {
  expect(transcriptLabel(null)).toEqual({ text: "（聞き取られた文はまだありません）", failed: false });
  expect(transcriptLabel("")).toEqual({ text: "聞き取れませんでした", failed: true });
  expect(transcriptLabel("右手の山は？")).toEqual({ text: "右手の山は？", failed: false });
});
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $APP && npx jest src/ui`
Expected: FAIL（`../recordingLabel` が無い）

- [ ] **Step 3: 実装する**

`App/src/ui/recordingLabel.ts` を作る:

```ts
// SC-12: how a kept recording is described, in Japan time.
export function recordedAtLabel(ms: number): string {
  const jst = new Date(ms + 9 * 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${jst.getUTCMonth() + 1}/${jst.getUTCDate()} ${pad(jst.getUTCHours())}:${pad(jst.getUTCMinutes())}:${pad(jst.getUTCSeconds())}`;
}

export function durationLabel(ms: number): string {
  return `${(ms / 1000).toFixed(1)}秒`;
}

export function transcriptLabel(transcript: string | null): { text: string; failed: boolean } {
  if (transcript === null) return { text: "（聞き取られた文はまだありません）", failed: false };
  if (transcript === "") return { text: "聞き取れませんでした", failed: true };
  return { text: transcript, failed: false };
}
```

試し録りの本物の部品と、SC-12 から録音を再生する口を `runtime.ts` に足す。試し録りの経路は、画面から始めた質問と同じ（仮想通話）:

```diff
diff --git a/src/ask/runtime.ts b/src/ask/runtime.ts
--- a/src/ask/runtime.ts
+++ b/src/ask/runtime.ts
@@ -1,7 +1,7 @@
 // Real implementations of the controller's Deps. Kept thin: the decisions live in controller.ts.
 import { createAudioPlayer, getRecordingPermissionsAsync, requestRecordingPermissionsAsync, setAudioModeAsync } from "expo-audio";
 import AudioModule from "expo-audio/build/AudioModule";
-import { deleteAsync, readAsStringAsync } from "expo-file-system/legacy";
+import { cacheDirectory, deleteAsync, readAsStringAsync } from "expo-file-system/legacy";
 import * as Location from "expo-location";
 import * as Speech from "expo-speech";
 import { PermissionsAndroid } from "react-native";
@@ -17,7 +17,8 @@ import { Deps } from "./controller";
 import { ConversationState } from "./conversation";
 import { FlowState, Source } from "./flow";
 import { ClipPlayer, playClips } from "./playback";
-import { newRecordingUri, pruneRecordings, saveMeta, setTranscript } from "./recordingFiles";
+import { newRecordingUri, pruneRecordings, recordingUri, saveMeta, setTranscript, wavFromPcm } from "./recordingFiles";
+import { TrialDeps, TrialState } from "./trial";
 const VR_TIMEOUT_MS = 4000;
 const SCO_TIMEOUT_MS = 3000;
 // Intercoms drop the first part of a sound: a 1 s tone is heard as a short blip, so the start cue is longer.
@@ -109,7 +110,13 @@ export function createRuntimeDeps(options: {
   settings(): Settings;
   apiKey(): string | null;
   onState(state: FlowState): void;
-}): { deps: Deps; dispose(): void } {
+}): {
+  deps: Deps;
+  trialDeps(onState: (state: TrialState) => void): TrialDeps;
+  playRecording(name: string): Promise<void>;
+  stopPlayback(): void;
+  dispose(): void;
+} {
   // setAudioModeAsync also calls setSpeakerphoneOn(), which pins this app's output to the phone speaker and keeps
   // answers off the intercom; clear that right after (releaseSco clears the communication device and the mode).
   void setAudioModeAsync({ shouldPlayInBackground: true, playsInSilentMode: true, interruptionMode: "mixWithOthers" }).then(() =>
@@ -177,5 +184,26 @@ export function createRuntimeDeps(options: {
     },
     log: (event, data) => { console.log(JSON.stringify({ event, ...data })); },
   };
-  return { deps, dispose: () => { positions.end(); playback.stop?.(); } };
+  // SC-12 plays WAV copies; expo-audio cannot play the raw PCM that is kept and sent.
+  const playPcm = async (pcmUri: string, wavName: string) => deps.player.play([await wavFromPcm(pcmUri, wavName)]);
+  const trialStream = new PcmStream();
+  const trialDeps = (onState: (state: TrialState) => void): TrialDeps => ({
+    now: deps.now,
+    sleep: deps.sleep,
+    micAllowed: deps.micAllowed,
+    route: { start: () => deps.route.start("screen"), stop: () => deps.route.stop(), inputDevice: deps.route.inputDevice },
+    recorder: { start: () => trialStream.start(`${cacheDirectory}trial.pcm`), stop: () => trialStream.stop(), cancel: () => trialStream.cancel() },
+    cueStart: deps.cues.start,
+    play: (uri) => playPcm(uri, "trial.wav"),
+    stopPlayback: deps.player.stop,
+    discard: (uri) => deleteAsync(uri, { idempotent: true }),
+    onState,
+  });
+  return {
+    deps,
+    trialDeps,
+    playRecording: (name) => playPcm(recordingUri(name), "recording.wav"),
+    stopPlayback: deps.player.stop,
+    dispose: () => { positions.end(); playback.stop?.(); },
+  };
 }
```

`AskProvider.tsx` で試し録りの司令塔を作り、試し録りのあいだはインカムのボタン（押下と、音声認識の終わり）を試し録りへ渡す（US-E-03.002）:

```diff
diff --git a/src/ask/AskProvider.tsx b/src/ask/AskProvider.tsx
--- a/src/ask/AskProvider.tsx
+++ b/src/ask/AskProvider.tsx
@@ -8,6 +8,7 @@ import { loadSettings, saveSettings, Settings } from "../settings/store";
 import { AskController } from "./controller";
 import { FlowState, IDLE } from "./flow";
 import { createRuntimeDeps, requestPermissions } from "./runtime";
+import { TRIAL_IDLE, TrialController, TrialState } from "./trial";
 
 type AskContext = {
   ready: boolean;
@@ -18,6 +19,11 @@ type AskContext = {
   apiKey: string | null;
   setApiKey(key: string | null): Promise<void>;
   conversationExpiresAt: number | null;
+  // SC-12
+  trial: TrialController | null;
+  trialState: TrialState;
+  playRecording(name: string): Promise<void>;
+  stopPlayback(): void;
 };
 
 const Context = createContext<AskContext | null>(null);
@@ -33,11 +39,19 @@ export function AskProvider({ children }: { children: ReactNode }) {
   const [settings, setSettings] = useState<Settings | null>(null);
   const [apiKey, setApiKeyState] = useState<string | null>(null);
   const [ready, setReady] = useState(false);
+  const [trialState, setTrialState] = useState<TrialState>(TRIAL_IDLE);
+  const trialRef = useRef<TrialController | null>(null);
   const settingsRef = useRef<Settings | null>(null);
   const keyRef = useRef<string | null>(null);
   const controllerRef = useRef<AskController | null>(null);
   const runtimeRef = useRef<ReturnType<typeof createRuntimeDeps> | null>(null);
-  const presses = useRef(new PressGate(() => controllerRef.current?.press()));
+  // While a trial recording runs, the intercom button ends it instead of starting a question (US-E-03.002).
+  const presses = useRef(
+    new PressGate(() => {
+      if (trialRef.current?.active) trialRef.current.stop();
+      else controllerRef.current?.press();
+    }),
+  );
 
   const handlePress = useCallback((pressedAt: number) => presses.current.offer(pressedAt, Date.now()), []);
 
@@ -59,6 +73,7 @@ export function AskProvider({ children }: { children: ReactNode }) {
       });
       runtimeRef.current = runtime;
       controllerRef.current = new AskController(runtime.deps);
+      trialRef.current = new TrialController(runtime.trialDeps(setTrialState));
       setReady(true);
       const pending = Handsfree.takePendingPress();
       if (pending !== null) handlePress(pending);
@@ -66,7 +81,10 @@ export function AskProvider({ children }: { children: ReactNode }) {
     })();
     const pressSub = Handsfree.addListener("onPress", (e) => handlePress(e.pressedAt));
     // The headset dropping SCO during a voice-recognition session is the second press.
-    const endSub = AudioRoute.addListener("onVoiceRecognitionEnded", () => controllerRef.current?.stopRecording());
+    const endSub = AudioRoute.addListener("onVoiceRecognitionEnded", () => {
+      if (trialRef.current?.active) trialRef.current.stop();
+      else controllerRef.current?.stopRecording();
+    });
     return () => {
       mounted = false;
       pressSub.remove();
@@ -88,10 +106,16 @@ export function AskProvider({ children }: { children: ReactNode }) {
     else await deleteApiKey();
   }, []);
 
+  const playRecording = useCallback(async (name: string) => { await runtimeRef.current?.playRecording(name); }, []);
+  const stopPlayback = useCallback(() => runtimeRef.current?.stopPlayback(), []);
+
   const conversationExpiresAt = runtimeRef.current?.deps.conversation.expiresAt(Date.now()) ?? null;
   const value = useMemo(
-    () => ({ ready, state, controller: controllerRef.current, settings, updateSettings, apiKey, setApiKey, conversationExpiresAt }),
-    [ready, state, settings, updateSettings, apiKey, setApiKey, conversationExpiresAt],
+    () => ({
+      ready, state, controller: controllerRef.current, settings, updateSettings, apiKey, setApiKey, conversationExpiresAt,
+      trial: trialRef.current, trialState, playRecording, stopPlayback,
+    }),
+    [ready, state, settings, updateSettings, apiKey, setApiKey, conversationExpiresAt, trialState, playRecording, stopPlayback],
   );
   return <Context.Provider value={value}>{children}</Context.Provider>;
 }
```

`App/app/settings/recordings.tsx` を作る。再生の部品は質問の一巡と共有しているので、画面を離れるときは自分が再生しているときだけ止める（`playingRef`）。「録音をすべて消す」は DL-01:

```tsx
import { useFocusEffect } from "expo-router";
import { useCallback, useRef, useState } from "react";
import { Alert, FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { useAsk } from "../../src/ask/AskProvider";
import { isBusy } from "../../src/ask/flow";
import { deleteAllRecordings, listRecordings } from "../../src/ask/recordingFiles";
import { micLabel, RecordingMeta } from "../../src/ask/recordings";
import { durationLabel, recordedAtLabel, transcriptLabel } from "../../src/ui/recordingLabel";

// SC-12: the trial recording, and the kept recordings of questions with what was heard (spec §5.5).
export default function Recordings() {
  const { state, trial, trialState, playRecording, stopPlayback } = useAsk();
  const [items, setItems] = useState<RecordingMeta[]>([]);
  const [playing, setPlaying] = useState<string | null>(null);
  // The player is shared with the ask loop: on leaving, stop it only if this screen is the one playing.
  const playingRef = useRef(false);

  const reload = useCallback(() => { void listRecordings().then(setItems).catch(() => setItems([])); }, []);
  useFocusEffect(
    useCallback(() => {
      reload();
      return () => {
        trial?.cancel();
        if (playingRef.current) stopPlayback();
      };
    }, [reload, trial, stopPlayback]),
  );
  if (!trial) return null;

  const busy = isBusy(state) || playing !== null;
  const play = async (name: string) => {
    setPlaying(name);
    playingRef.current = true;
    try {
      await playRecording(name);
    } catch {
      Alert.alert("再生できませんでした");
    } finally {
      playingRef.current = false;
      setPlaying(null);
    }
  };
  const confirmDeleteAll = () =>
    Alert.alert("録音をすべて消しますか？", "端末に残した質問の音声を消します。質問と回答の記録は消えません。", [
      { text: "やめる", style: "cancel" },
      { text: "消す", style: "destructive", onPress: () => void deleteAllRecordings().then(reload) },
    ]);

  let trialButton = "試し録り";
  let trialStatus = "質問と同じマイクで録って、すぐに再生します。送りません。";
  if (trialState.phase === "recording") {
    trialButton = "止めて聞く";
    trialStatus = "録音中です。話してください（インカムのボタンでも止められます）";
  } else if (trialState.phase === "playing") {
    trialButton = "再生を止める";
    trialStatus = `再生中: ${micLabel(trialState)}`;
  } else if (trialState.device || trialState.phoneMic) {
    trialStatus = `録ったマイク: ${micLabel(trialState)}`;
  }

  return (
    <View style={styles.root}>
      <View style={styles.card}>
        <Pressable
          style={[styles.trialButton, trialState.phase === "recording" && styles.trialButtonRecording, busy && !trial.active && styles.disabled]}
          disabled={busy && !trial.active}
          onPress={() => (trial.active ? trial.stop() : void trial.start())}
        >
          <Text style={styles.trialButtonText}>{trialButton}</Text>
        </Pressable>
        <Text style={styles.note}>{trialStatus}</Text>
        {trialState.error ? <Text style={styles.error}>{trialState.error}</Text> : null}
      </View>
      <Text style={styles.section}>送った録音（直近10件）</Text>
      <FlatList
        data={items}
        keyExtractor={(m) => m.name}
        ListEmptyComponent={<Text style={styles.note}>まだありません</Text>}
        renderItem={({ item }) => {
          const heard = transcriptLabel(item.transcript);
          return (
            <View style={styles.row}>
              <View style={styles.rowMain}>
                <Text style={styles.rowTitle}>{recordedAtLabel(item.recordedAt)}　{durationLabel(item.durationMs)}</Text>
                <Text style={styles.note}>{micLabel(item)}</Text>
                <Text style={heard.failed ? styles.error : styles.heard}>{heard.text}</Text>
              </View>
              <Pressable
                style={[styles.play, (busy || trial.active) && playing !== item.name && styles.disabled]}
                disabled={(busy || trial.active) && playing !== item.name}
                onPress={() => (playing === item.name ? stopPlayback() : void play(item.name))}
              >
                <Text style={styles.playText}>{playing === item.name ? "■" : "▶"}</Text>
              </Pressable>
            </View>
          );
        }}
      />
      <Pressable style={[styles.deleteAll, (busy || trial.active) && styles.disabled]} disabled={busy || trial.active} onPress={confirmDeleteAll}>
        <Text style={styles.deleteAllText}>録音をすべて消す</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 16, gap: 12 },
  card: { gap: 8 },
  trialButton: { backgroundColor: "#1f4fd1", padding: 18, borderRadius: 12, alignItems: "center" },
  trialButtonRecording: { backgroundColor: "#d42a2a" },
  trialButtonText: { color: "#fff", fontSize: 20, fontWeight: "700" },
  disabled: { opacity: 0.4 },
  note: { fontSize: 14, color: "#666" },
  error: { fontSize: 14, color: "#d42a2a" },
  section: { fontSize: 16, fontWeight: "700", marginTop: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: "#eee" },
  rowMain: { flex: 1, gap: 2 },
  rowTitle: { fontSize: 16 },
  heard: { fontSize: 15 },
  play: { width: 48, height: 48, borderRadius: 24, borderWidth: 1, borderColor: "#999", alignItems: "center", justifyContent: "center" },
  playText: { fontSize: 20 },
  deleteAll: { padding: 14, borderRadius: 12, borderWidth: 1, borderColor: "#d42a2a", alignItems: "center" },
  deleteAllText: { color: "#d42a2a", fontSize: 16, fontWeight: "700" },
});
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: 111 passed、型のエラー 0。

- [ ] **Step 5: コミット**

```bash
cd $APP && git add app/settings/recordings.tsx src/ui/recordingLabel.ts src/ui/__tests__/recordingLabel.test.ts src/ask/runtime.ts src/ask/AskProvider.tsx
git commit -m "feat: add the recording check screen (SC-12)"
```

---

### Task 10: App: ホームの帯と、メディアの音量の警告（issue #7）

**Files:**
- Create: `App/src/ui/homeBanner.ts`、`src/ui/__tests__/homeBanner.test.ts`
- Modify: `App/app/index.tsx`

**Interfaces:**
- Consumes: `AudioRoute.getMediaVolume()`（Task 6）。
- Produces: `type Banner = "no_key" | "no_return_app" | "low_volume"`、`BANNER_TEXT`、`mediaVolumeLow(volume)`、`homeBanner({ hasKey, returnAppMissing, volumeLow })`。

- [ ] **Step 1: 失敗するテストを書く**

`App/src/ui/__tests__/homeBanner.test.ts` を作る:

```ts
import { homeBanner, mediaVolumeLow } from "../homeBanner";

test("media volume below a third of the maximum is low", () => {
  expect(mediaVolumeLow({ current: 2, max: 25 })).toBe(true);
  expect(mediaVolumeLow({ current: 8, max: 25 })).toBe(true);
  expect(mediaVolumeLow({ current: 9, max: 25 })).toBe(false);
  expect(mediaVolumeLow({ current: 5, max: 15 })).toBe(false);
  expect(mediaVolumeLow({ current: 0, max: 0 })).toBe(false);
  expect(mediaVolumeLow(null)).toBe(false);
});

test("one band at a time, the most important first", () => {
  expect(homeBanner({ hasKey: false, returnAppMissing: true, volumeLow: true })).toBe("no_key");
  expect(homeBanner({ hasKey: true, returnAppMissing: true, volumeLow: true })).toBe("no_return_app");
  expect(homeBanner({ hasKey: true, returnAppMissing: false, volumeLow: true })).toBe("low_volume");
  expect(homeBanner({ hasKey: true, returnAppMissing: false, volumeLow: false })).toBeNull();
});
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $APP && npx jest src/ui`
Expected: FAIL（`../homeBanner` が無い）

- [ ] **Step 3: 実装する**

`App/src/ui/homeBanner.ts` を作る:

```ts
// SC-02 shows one warning band at a time, the most important first (mock: 帯（警告）).
import type { MediaVolume } from "../../modules/audio-route/src";

export type Banner = "no_key" | "no_return_app" | "low_volume";

export const BANNER_TEXT: Record<Banner, string> = {
  no_key: "接続キーが未設定です（押して設定）",
  no_return_app: "戻り先のアプリが未設定です（押して選ぶ）",
  low_volume: "メディアの音量が低く、回答が聞こえないかもしれません",
};

/** Answers and cues play on the media stream; below a third of the maximum they get lost on the intercom. */
export function mediaVolumeLow(volume: MediaVolume | null): boolean {
  return volume !== null && volume.max > 0 && volume.current * 3 < volume.max;
}

export function homeBanner(status: { hasKey: boolean; returnAppMissing: boolean; volumeLow: boolean }): Banner | null {
  if (!status.hasKey) return "no_key";
  if (status.returnAppMissing) return "no_return_app";
  if (status.volumeLow) return "low_volume";
  return null;
}
```

`App/app/index.tsx` を置き換える（帯は重要な順に1本だけ。音量はホームが前にあるあいだ2秒ごとに読む）:

```tsx
import { Link, router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";

import AudioRoute, { MediaVolume } from "../modules/audio-route/src";
import { useAsk } from "../src/ask/AskProvider";
import { conversationLabel } from "../src/ui/conversationLabel";
import { Banner, BANNER_TEXT, homeBanner, mediaVolumeLow } from "../src/ui/homeBanner";

const VOLUME_CHECK_MS = 2_000;

// The rider may turn the volume down at any time; check while the home screen is in front (foreground-only timer).
function useMediaVolume(): MediaVolume | null {
  const [volume, setVolume] = useState<MediaVolume | null>(null);
  useFocusEffect(
    useCallback(() => {
      const read = () => setVolume(AudioRoute.getMediaVolume());
      read();
      const id = setInterval(read, VOLUME_CHECK_MS);
      return () => clearInterval(id);
    }, []),
  );
  return volume;
}

const BANNER_TARGET: Record<Banner, "/settings/connection" | "/settings/return-app" | null> = {
  no_key: "/settings/connection",
  no_return_app: "/settings/return-app",
  low_volume: null,
};

export default function Home() {
  const { ready, controller, settings, apiKey, conversationExpiresAt } = useAsk();
  const volume = useMediaVolume();
  if (!ready || !settings || !controller) return <View style={styles.root}><Text>準備中…</Text></View>;

  const confirmNewConversation = () =>
    Alert.alert("新しい会話を始めますか？", "次の質問から、これまでの会話を踏まえずに答えます。", [
      { text: "やめる", style: "cancel" },
      { text: "新しい会話にする", onPress: () => controller.resetConversation() },
    ]);
  const banner = homeBanner({
    hasKey: !!apiKey,
    returnAppMissing: settings.returnEnabled && !settings.returnApp,
    volumeLow: mediaVolumeLow(volume),
  });
  const target = banner ? BANNER_TARGET[banner] : null;

  return (
    <View style={styles.root}>
      <View style={styles.top}>
        <Pressable onPress={() => router.push("/settings/user")}>
          <Text style={styles.user}>{settings.userName}</Text>
        </Pressable>
        <View style={styles.row}>
          <Pressable style={styles.small} onPress={() => controller.tapToTalk()}>
            <Text style={styles.smallText}>🎤 押して話す</Text>
          </Pressable>
          <Link href="/settings" style={styles.small}>
            <Text style={styles.smallText}>⚙ 設定</Text>
          </Link>
        </View>
      </View>
      {banner ? (
        <Pressable style={styles.banner} disabled={!target} onPress={() => target && router.push(target)}>
          <Text style={styles.bannerText}>{BANNER_TEXT[banner]}</Text>
        </Pressable>
      ) : null}
      <Text style={styles.ready}>インカムのボタンで話せます</Text>
      <Pressable style={styles.newConversation} onPress={confirmNewConversation}>
        <Text style={styles.newStatus}>{conversationLabel(conversationExpiresAt, Date.now())}</Text>
        <Text style={styles.newText}>新しい会話を始める</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 16, gap: 12 },
  top: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  user: { fontSize: 22, fontWeight: "700", fontFamily: "monospace" },
  row: { flexDirection: "row", gap: 8 },
  small: { paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: "#999" },
  smallText: { fontSize: 14 },
  banner: { backgroundColor: "#f5c518", padding: 12, borderRadius: 8 },
  bannerText: { fontSize: 16, color: "#000" },
  ready: { fontSize: 16, color: "#13804a" },
  newConversation: { minHeight: 76, maxHeight: 140, borderRadius: 16, backgroundColor: "#1f4fd1", padding: 16, justifyContent: "center" },
  newStatus: { color: "#fff", fontSize: 16 },
  newText: { color: "#fff", fontSize: 26, fontWeight: "700", marginTop: 6 },
});
```

- [ ] **Step 4: 通ることを確かめる**

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: 113 passed、型のエラー 0。

- [ ] **Step 5: コミット**

```bash
cd $APP && git add src/ui/homeBanner.ts src/ui/__tests__/homeBanner.test.ts app/index.tsx
git commit -m "feat: warn on the home screen when the media volume is low"
```

---

### Task 11: App: 走行用のビルド（issue #8）と README

**Files:**
- Modify: `App/README.md`

**Interfaces:**
- Consumes: すべて（ビルドで Kotlin を含めて確かめる）。

- [ ] **Step 1: release をビルドし、権限を確かめる**

```bash
cd $APP && npx expo prebuild --platform android --clean > /tmp/trv2-prebuild.log 2>&1
cd android && ./gradlew assembleRelease > /tmp/trv2-release.log 2>&1; tail -3 /tmp/trv2-release.log
grep -nE "compileReleaseKotlin|^e: " /tmp/trv2-release.log | grep -E "handsfree|audio-route|ride-service|^.*e: "
cd $APP && "$ANDROID_HOME"/build-tools/$(ls "$ANDROID_HOME"/build-tools | sort -V | tail -1)/aapt2 dump permissions \
  android/app/build/outputs/apk/release/app-release.apk
```
Expected: `BUILD SUCCESSFUL`（4分ほど）。自前の3つのモジュールの `compileReleaseKotlin` が出て、`e: ` の行が無い。権限に `ACCESS_LOCAL_NETWORK` が無い。`SYSTEM_ALERT_WINDOW`・`READ/WRITE_EXTERNAL_STORAGE`・`VIBRATE` は Expo の雛形が本体の Manifest に入れるもので、外さない（計画を書くときに利用者と決めた）。ビルドが失敗したら、ログの最初のエラーを調べてから直す。

- [ ] **Step 2: README を直す**

````diff
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -8,11 +8,12 @@ TouringProjectV2 の Android アプリ（Expo SDK 58・Development Build・expo-
 
 | 場所 | 中身 |
 |---|---|
-| `app/` | 画面（ホーム・設定・接続・ユーザー名・応答後に戻るアプリ） |
-| `src/ask/` | 一巡の状態機械（`flow.ts`）・司令塔（`controller.ts`）・本物の部品（`runtime.ts`）・ポーリング・会話 |
+| `app/` | 画面（ホーム・設定・接続・ユーザー名・応答後に戻るアプリ・回答の音量・録音の確認） |
+| `src/ask/` | 一巡の状態機械（`flow.ts`）・司令塔（`controller.ts`）・本物の部品（`runtime.ts`）・ポーリング・会話・試し録り（`trial.ts`）・残した録音（`recordings.ts`・`recordingFiles.ts`） |
+| `src/location/` | 位置の監視（`tracker.ts`）と方位の材料の選び方（`heading.ts`） |
 | `src/api/` | Backend の API（`Backend/openapi.yaml`） |
 | `modules/handsfree/` | インカムのボタンの合図（`VOICE_COMMAND`）を Activity のライフサイクルから受ける |
-| `modules/audio-route/` | インカムのマイクへの経路（音声認識として・仮想通話として）と、2回目の押下の検出 |
+| `modules/audio-route/` | インカムのマイクへの経路（音声認識として・仮想通話として）・2回目の押下の検出・メディアの音量・録音中の入力デバイス |
 | `modules/ride-service/` | フォアグラウンドサービス・ネイティブで待つ `sleep`・ナビを開く・合図の音 |
 | `plugins/withHandsfree.js` | Manifest に `VOICE_COMMAND` の受け口を足す |
 
@@ -54,3 +55,22 @@ adb shell am start -a android.intent.action.VIEW \
 ```
 
 一巡の状態・合図・経路の結果は、`console.log` の JSON として Metro のログに出る。
+
+## 走行用のビルド
+
+開発用のビルドは、JS を USB 越しに Mac の Metro から読むので、USB を外すと動かない。走行で使うときは、JS を組み込んだ release のビルドを入れる。
+
+```sh
+npx expo prebuild --platform android --clean
+npx expo run:android --variant release --device
+```
+
+- 署名は開発用と同じ鍵（`debug.keystore`）なので、開発用のビルドの上に入り、接続キー・設定・残した録音はそのまま残る。開発用に戻すときは `npx expo run:android --device` をもう一度実行する。
+- API の URL（`.env`）は、ビルドのときに JS に組み込まれる。URL を変えたら作り直す。
+- ログは Metro ではなく `adb logcat -s ReactNativeJS trv2.route trv2.ride` で見る。
+- 開発用にだけ入る権限（`ACCESS_LOCAL_NETWORK`）が入っていないことを確かめる。`SYSTEM_ALERT_WINDOW`・`READ/WRITE_EXTERNAL_STORAGE`・`VIBRATE` は Expo の雛形が本体にも入れるもので、App は使わない（`SYSTEM_ALERT_WINDOW` は、利用者が「他のアプリの上に重ねて表示」を許可しない限り効果が無い）。
+
+```sh
+"$ANDROID_HOME"/build-tools/$(ls "$ANDROID_HOME"/build-tools | sort -V | tail -1)/aapt2 dump permissions \
+  android/app/build/outputs/apk/release/app-release.apk
+```
````

- [ ] **Step 3: コミット**

```bash
cd $APP && git add README.md
git commit -m "docs: how to build the ride build and what the new screens are"
```

---

### Task 12: 文書（親）

**Files:**
- Modify（親）: `docs/specs/2026-10-16-slice1-design.md`（§8.1 に `service`、状態）、`PROJECT.md`、submodule の指す先（`App`・`Backend`）、各ユニットの `docs-parent/`

- [ ] **Step 1: 親でブランチを切り、仕様の §8.1 に `service` を足す**

```bash
cd $ROOT && git switch -c slice1-plan4b
```

`docs/specs/2026-10-16-slice1-design.md` §8.1 の表の `invalid_key` の行の下に足す:

```markdown
| `service` | App（フォアグラウンドサービスが始まらない） | 失敗の音＋「準備できなかったため、質問できませんでした」 |
```

§5.7 の最後から2つ目の文を直す（release の APK を確かめて分かったこと）:
旧: `開発用にだけ入る権限（`SYSTEM_ALERT_WINDOW`・`ACCESS_LOCAL_NETWORK` など）が入っていないことを確かめる。`
新: `開発用にだけ入る権限（`ACCESS_LOCAL_NETWORK`）が入っていないことを確かめる。`SYSTEM_ALERT_WINDOW`・`READ/WRITE_EXTERNAL_STORAGE`・`VIBRATE` は Expo の雛形が本体にも入れるもので、App は使わないが外さない（`SYSTEM_ALERT_WINDOW` は利用者が許可しない限り効果が無い）。`

- [ ] **Step 2: `PROJECT.md` の計画の表を直す**

`| [4b](...) | ... | **次**（計画済み。実行待ち） |` の行を、次に置き換える:

```markdown
| [4b](docs/plans/2026-10-16-slice1-plan4b-app-finish.md) | App の残り: 録音の確認（SC-12）・回答の音量（SC-20・Backend の `volumeDb`）・メディアの音量の警告・走行用のビルド・issue #1〜#8 | 実装済み（実機の確認待ち） |
```

「次にやること」の 1（`計画4b を実行する…`）を「計画4b の実機の確認（Task 13）をする。」に直す。

- [ ] **Step 3: 写して submodule を進める**

```bash
cd $ROOT
python3 scripts/check_links.py docs adr README.md PROJECT.md
scripts/sync-docs.sh App Backend Agent CICD
for u in App Backend Agent CICD; do git -C "$u" add docs-parent && git -C "$u" commit -m "docs: sync parent docs" || true; done
git add docs/specs/2026-10-16-slice1-design.md PROJECT.md Agent App Backend CICD
git commit -m "docs: record plan 4b and the service failure reason"
```
Expected: リンクの切れ 0件。Agent・CICD は `docs-parent` だけが進む（ブランチは切らずに `main` のままでよい。これまでの写しと同じ）。

---

### Task 13: 実機の確認

**前提:** Task 1 のデプロイが済んでいる。利用者の Android 端末を USB でつなぎ、インカムをペアリングし、ナビを入れておく。

- [ ] **Step 1: 開発用のビルドで入れる**

```bash
cd $APP && npx expo prebuild --platform android --clean > /tmp/trv2-prebuild.log 2>&1 && npx expo run:android --device
```

- [ ] **Step 2: 【利用者の作業】確認リスト（開発用のビルド・停車中）**

| # | 操作 | 期待 |
|---|---|---|
| 1 | 設定 → 回答の音量 → +12 を選び、インカムのボタンで質問する | 回答が +6 のときより大きく聞こえる。+0・+6 とも聞き比べ、ナビの案内と比べて聞き劣りしない段を選ぶ |
| 2 | スマホのメディアの音量を下げる（最大の1/3未満）→ ホームに戻る | 2秒ほどで「メディアの音量が低く…」の帯が出る。上げると消える |
| 3 | 設定 → 録音の確認 →「試し録り」→ 話す →「止めて聞く」 | 話した声がインカムから聞こえる。「録ったマイク: インカム（機器の名前）」と出る |
| 4 | 「試し録り」→ 話す → インカムのボタンを押す | 質問は始まらず、試し録りが止まって再生される |
| 5 | 送った録音の一覧 | 1〜2 の質問が新しい順に並び、時刻・長さ・マイク・聞き取られた文が出る。▶ で聞ける |
| 6 | SC-12 を開いたままインカムで質問し、読み上げ中に戻るボタンで SC-12 を離れる | 読み上げは最後まで続く |
| 7 | 「録音をすべて消す」→ 確認 | 一覧が空になる |
| 8 | 計画4a の確認 #1・#5・#9（アプリを閉じた状態からの起動・回答待ちの押下・新しい会話） | 計画4a と同じく動く（押下の配線を変えたため） |

- [ ] **Step 3: 【利用者の作業】走行用のビルドで確かめる**

README の「走行用のビルド」の手順で入れ、USB を外して、計画4a の確認 #1〜#3（アプリを閉じた状態からインカムのボタンで質問 → マップへ戻る → 回答が聞こえる）を行う。

✗ があれば、`adb logcat -s trv2.route trv2.ride ReactNativeJS` の出力と合わせて原因を調べる。結果は利用者に報告する（コミットはしない）。終わったら、`superpowers:finishing-a-development-branch` でブランチを仕上げる（マージはユニット → 親の順）。マージのあと、利用者の許可を得て App の issue #1〜#8 を閉じる（`gh issue close <番号> --comment "slice1 plan 4b"`）。
