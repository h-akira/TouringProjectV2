# スライス1 計画4a: App（ハンズフリーの一巡） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** インカムのボタンで起動 → 録音 → 送信 → ナビへ戻る → 背面で回答を待って読み上げる、という一巡を、実機で走って確かめられる Android アプリを作る。

**Architecture:** Expo SDK 58（Development Build・expo-router・TypeScript）。一巡の判断は、副作用を持たない状態機械（`flow.ts`）と、副作用を差し替えられる司令塔（`AskController`）に分け、Jest で網羅する。端末にしかできないことは自前の3つのネイティブモジュールに置く: `handsfree`（インカムのボタンの合図を Activity のライフサイクルから受ける）、`audio-route`（インカムのマイクへの経路）、`ride-service`（フォアグラウンドサービス・ネイティブで待つ・ナビを開く・合図の音）。

**Tech Stack:** Expo 58・React Native 0.88・expo-router・expo-audio（AudioStream の PCM 録音・再生）・expo-location・expo-secure-store・expo-speech・expo-file-system・@react-native-async-storage/async-storage・Jest（jest-expo）・Kotlin（Expo Modules）。

**Spec:** [docs/specs/2026-10-16-slice1-design.md](../specs/2026-10-16-slice1-design.md)（§5・§8）、[adr/0002](../../adr/0002-streaming-transcription.md)・[adr/0004](../../adr/0004-background-processing.md)、契約 `Backend/openapi.yaml` と [docs/07_units_contracts.md](../07_units_contracts.md)、画面 [docs/mock/index.html](../mock/index.html)（SC-02・SC-03・SC-09・SC-10・SC-13・SC-18・DL-02）

計画4b（ホームの仕上げ・録音の確認 SC-12 など）は、この計画のあとに書く。

## Global Constraints

- 作業するリポジトリは `App/`（`TouringProjectV2_App`）。Task 14 だけ `Backend/`、Task 16 だけ親。どれも `main` から作業ブランチ `slice1-plan4a` を切る。push はしない。
- パッケージ名 `com.touringproject.v2`、アプリ名「Touring V2」、URL スキーム `trv2`。対象は Android 12 以降。
- API の URL は `App/.env` の `EXPO_PUBLIC_API_BASE_URL`（追跡しない）。接続キーは SecureStore、ほかの設定は AsyncStorage。キーと URL をコードや文書に書かない。
- 録音は PCM（16kHz・モノラル・16bit）を expo-audio の AudioStream で録り、改行なしの base64 で送る（Backend issue #6）。上限は20秒（スライス1では固定）。
- 背面で待つ処理に `setTimeout` を使わない。待ちは `RideService.sleep`（ネイティブ）で行う（adr/0004）。一巡のあいだはフォアグラウンドサービス（microphone・mediaPlayback）を動かす。
- 音声は `shouldPlayInBackground`・`playsInSilentMode`・`interruptionMode: "mixWithOthers"` を指定して鳴らす（adr/0004）。
- ポーリングは最初の10秒は1秒ごと、以後は2秒ごと、120秒で打ち切る（07 UC-5）。
- 失敗の理由と読み上げる文は spec §8.1 のとおり。失敗は音（合図）と端末の音声で知らせる。
- 戻るのはインカムのボタンで始めた応答だけ。戻るタイミングは「送ったらすぐ（既定）／回答が届いたら／読み上げが終わったら」。
- 対話の画面（SC-03）の色: 録音中 `#d42a2a`・回答待ち `#1f4fd1`・読み上げ中 `#13804a`・失敗 `#5b6170`。
- コードのコメントは英語、文書は日本語。Conventional Commits。`git add .`・`-A` は使わない。文書に、このプロジェクトより前の版への言及を書かない。
- 以下 `ROOT=<親リポジトリの絶対パス>`、`APP=$ROOT/App`、`BE=$ROOT/Backend`。テストは `cd $APP && npx jest`、型は `npx tsc --noEmit`。

## Review Focus

- 回答待ち・読み上げ中にインカムのボタンが押される → 新しい録音は始めず、「いま応答中です…」と読み上げる。Task 7 の `test_press_while_waiting_says_busy`。
- 失敗の画面（画面から始めた質問の5秒の表示）の最中に、次の質問を始める → 前の一巡の後片付けが、新しい一巡の画面の状態とフォアグラウンドサービスを止めない。Task 7 の `test_new_run_during_failed_screen_is_not_reset`。
- 同じ押下の合図が2回届く（起動時に残っていた合図とイベントの両方）・1分より前の合図が残っている → 1回だけ扱い、古いものは捨てる。Task 10 の `claimPress` のテスト。
- 方位の材料に使える点が無い（止まっている・録音が短い）→ `headingSample` を送らない。Task 5 の `test_no_sample_when_stationary`。
- 回答の音声が取れない（`tts_failed`、または再生の失敗）→ 回答の文を端末の音声で読む。Task 7 の `test_tts_failed_reads_answer_with_device_voice`・`test_player_error_falls_back_to_device_voice`。

---

## ファイル構成（`App/` から）

| パス | 役割 |
|---|---|
| `app.json`・`package.json`・`tsconfig.json` | Expo の設定・依存・Jest の設定 |
| `plugins/withHandsfree.js` | Manifest に `VOICE_COMMAND` の受け口とランチャーの問い合わせを足す |
| `app/_layout.tsx`・`app/index.tsx`・`app/settings/*.tsx` | 画面（ホーム・設定・接続・ユーザー名・戻り先アプリ） |
| `src/settings/store.ts` | 設定の読み書き（純粋な部分） |
| `src/settings/storage.ts` | AsyncStorage・SecureStore への接続 |
| `src/api/client.ts` | Backend の API（失敗の分類・試し直し） |
| `src/ask/polling.ts` | ポーリングの間隔と打ち切り |
| `src/ask/conversation.ts` | 会話の識別子と区切られる時刻 |
| `src/ask/flow.ts`・`src/ask/failures.ts` | 一巡の状態機械と、失敗の読み上げ文 |
| `src/ask/controller.ts` | 一巡の司令塔（副作用は Deps で受け取る） |
| `src/ask/recordings.ts` | 録音のファイル名と、直近10件を残す計算 |
| `src/ask/runtime.ts` | 本物の Deps を組み立てる |
| `src/ask/AskProvider.tsx`・`src/ui/AskOverlay.tsx` | 状態の配布と、対話の画面（SC-03） |
| `src/location/heading.ts` | 方位の材料の選び方 |
| `src/handsfree/press.ts` | 押下の重複・古い合図の除外 |
| `modules/ride-service/` | フォアグラウンドサービス・`sleep`・ナビを開く・アプリの一覧・合図の音 |
| `modules/audio-route/` | 音声認識としての経路・仮想通話としての経路・2回目の押下の検出 |
| `modules/handsfree/` | `VOICE_COMMAND` の受け取り（Activity のライフサイクル） |

---

### Task 1: 土台

**Files:**
- Create: `App/` の Expo プロジェクト一式、`app.json`、`tsconfig.json`、`app/_layout.tsx`（仮）、`src/__tests__/config.test.ts`
- Modify: `App/.gitignore`

**Interfaces:**
- Produces: Jest と型検査が動くプロジェクト。`app.json` の `expo.android.package = "com.touringproject.v2"`。

- [ ] **Step 1: ブランチを切り、雛形を作る**

```bash
cd $APP && git switch -c slice1-plan4a
SCRATCH=$(mktemp -d) && cd "$SCRATCH"
npx -y create-expo-app@latest app --template blank-typescript --no-install
rsync -a --exclude '.git/' --exclude '.claude/' --exclude 'README.md' --exclude 'AGENTS.md' --exclude 'LICENSE' --exclude 'App.tsx' --exclude 'index.ts' --exclude '.gitignore' app/ "$APP/"
cd $APP && cat "$SCRATCH/app/.gitignore" >> .gitignore
# expo-router's web dependencies (radix) pin a newer react-dom peer than the SDK's react
echo "legacy-peer-deps=true" > .npmrc
# The template was created with --no-install; expo itself must be present before `expo install`
npm install
npx expo install expo-router expo-dev-client expo-audio expo-location expo-secure-store expo-speech expo-file-system expo-linking expo-constants expo-status-bar react-native-safe-area-context react-native-screens @react-native-async-storage/async-storage
npx expo install -- --save-dev jest-expo jest @types/jest @react-native/jest-preset
```

- [ ] **Step 2: 設定を書く**

`package.json` の `"main"` を `"expo-router/entry"` にし、`"scripts"` に `"test": "jest"` を足し、トップレベルに次を足す:

```json
"jest": {
  "preset": "jest-expo",
  "testPathIgnorePatterns": ["/node_modules/", "/android/", "/ios/"]
}
```

`app.json`（全体を置き換える）:

```json
{
  "expo": {
    "name": "Touring V2",
    "slug": "touring-v2",
    "scheme": "trv2",
    "version": "0.1.0",
    "orientation": "portrait",
    "userInterfaceStyle": "automatic",
    "icon": "./assets/icon.png",
    "android": {
      "package": "com.touringproject.v2",
      "adaptiveIcon": {
        "backgroundColor": "#1f4fd1",
        "foregroundImage": "./assets/android-icon-foreground.png"
      },
      "permissions": [
        "android.permission.RECORD_AUDIO",
        "android.permission.BLUETOOTH_CONNECT",
        "android.permission.POST_NOTIFICATIONS",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_COARSE_LOCATION"
      ]
    },
    "plugins": [
      "expo-router",
      "expo-secure-store",
      ["expo-audio", { "microphonePermission": "質問の録音に使います", "enableBackgroundPlayback": true }],
      ["expo-location", { "locationWhenInUsePermission": "質問した場所と進行方向を伝えるために使います" }],
      "./plugins/withHandsfree"
    ]
  }
}
```

`tsconfig.json`:

```json
{
  "extends": "expo/tsconfig.base",
  "compilerOptions": { "strict": true, "types": ["jest", "node"] },
  "include": ["**/*.ts", "**/*.tsx", ".expo/types/**/*.ts", "expo-env.d.ts"]
}
```

`.gitignore` の末尾に足す:

```

# Local config (API URL) and native build output
.env
.env.*
android/
ios/
```

仮の `app/_layout.tsx`（Task 13 で置き換える）:

```tsx
import { Stack } from "expo-router";

export default function Layout() {
  return <Stack />;
}
```

仮の `plugins/withHandsfree.js`（Task 10 で置き換える）:

```js
// Placeholder; replaced by the handsfree config plugin in Task 10.
module.exports = (config) => config;
```

- [ ] **Step 3: 設定のテストを書く**

`src/__tests__/config.test.ts`:

```ts
import appJson from "../../app.json";

test("android package and scheme are fixed", () => {
  expect(appJson.expo.android.package).toBe("com.touringproject.v2");
  expect(appJson.expo.scheme).toBe("trv2");
  expect(appJson.expo.name).toBe("Touring V2");
});

test("audio plays in the background", () => {
  const audio = appJson.expo.plugins.find((p) => Array.isArray(p) && p[0] === "expo-audio") as [string, { enableBackgroundPlayback: boolean }];
  expect(audio[1].enableBackgroundPlayback).toBe(true);
});
```

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: 2 passed。型エラーなし。

- [ ] **Step 4: コミット**

```bash
cd $APP
git add .gitignore .npmrc package.json package-lock.json app.json tsconfig.json babel.config.js assets app/_layout.tsx plugins/withHandsfree.js src/__tests__/config.test.ts expo-env.d.ts 2>/dev/null; git status --short
git commit -m "feat: scaffold expo app with router and test setup"
```
`babel.config.js`・`expo-env.d.ts` が無い場合は、それを除いて `git add` する。

---

### Task 2: 設定の読み書き

**Files:**
- Create: `src/settings/store.ts`、`src/settings/storage.ts`
- Test: `src/settings/__tests__/store.test.ts`

**Interfaces:**
- Produces: `ReturnTiming = "sent" | "answered" | "spoken"`、`LaunchableApp = { packageName: string; label: string }`、`Settings = { userName: string; returnEnabled: boolean; returnApp: LaunchableApp | null; returnTiming: ReturnTiming; recentApps: LaunchableApp[] }`、`KeyValueStore`（`getItem`・`setItem`）、`USER_NAME_RE`、`randomUserName(random?) => string`、`loadSettings(store, random?) => Promise<Settings>`、`saveSettings(store, settings) => Promise<void>`、`withRecentApp(recent, app, max?) => LaunchableApp[]`、`maskKey(key) => string`。`storage.ts`: `settingsStore: KeyValueStore`（AsyncStorage）、`loadApiKey()`・`saveApiKey(key)`・`deleteApiKey()`（SecureStore）。

- [ ] **Step 1: 失敗するテストを書く**

`src/settings/__tests__/store.test.ts`:

```ts
import { KeyValueStore, loadSettings, maskKey, randomUserName, saveSettings, USER_NAME_RE, withRecentApp } from "../store";

class MemoryStore implements KeyValueStore {
  data = new Map<string, string>();
  async getItem(key: string) { return this.data.get(key) ?? null; }
  async setItem(key: string, value: string) { this.data.set(key, value); }
}

const MAPS = { packageName: "com.google.android.apps.maps", label: "マップ" };

test("random user name is 6 lowercase letters or digits", () => {
  const name = randomUserName();
  expect(name).toMatch(/^[a-z0-9]{6}$/);
  expect(USER_NAME_RE.test(name)).toBe(true);
});

test("first load creates and saves a user name with defaults", async () => {
  const store = new MemoryStore();
  const settings = await loadSettings(store, () => 0);
  expect(settings).toEqual({ userName: "aaaaaa", returnEnabled: true, returnApp: null, returnTiming: "sent", recentApps: [] });
  expect(JSON.parse(store.data.get("trv2.settings")!).userName).toBe("aaaaaa");
});

test("saved settings round trip", async () => {
  const store = new MemoryStore();
  const settings = { userName: "rider01", returnEnabled: false, returnApp: MAPS, returnTiming: "spoken" as const, recentApps: [MAPS] };
  await saveSettings(store, settings);
  expect(await loadSettings(store)).toEqual(settings);
});

test("broken values fall back to defaults", async () => {
  const store = new MemoryStore();
  store.data.set("trv2.settings", JSON.stringify({ userName: "BAD NAME", returnTiming: "later", returnApp: { label: 1 }, recentApps: "x" }));
  const settings = await loadSettings(store, () => 0.5);
  expect(settings.userName).toMatch(/^[a-z0-9]{6}$/);
  expect(settings.returnTiming).toBe("sent");
  expect(settings.returnApp).toBeNull();
  expect(settings.recentApps).toEqual([]);
});

test("not JSON falls back to defaults", async () => {
  const store = new MemoryStore();
  store.data.set("trv2.settings", "{oops");
  expect((await loadSettings(store, () => 0)).userName).toBe("aaaaaa");
});

test("recent apps keep the latest five without duplicates", () => {
  const apps = Array.from({ length: 6 }, (_, i) => ({ packageName: `p${i}`, label: `L${i}` }));
  const recent = apps.reduce((list, app) => withRecentApp(list, app), [] as typeof apps);
  expect(recent.map((a) => a.packageName)).toEqual(["p5", "p4", "p3", "p2", "p1"]);
  expect(withRecentApp(recent, apps[3]).map((a) => a.packageName)).toEqual(["p3", "p5", "p4", "p2", "p1"]);
});

test("mask shows only the last four characters", () => {
  expect(maskKey("abcdefgh1234")).toBe("••••••••1234");
  expect(maskKey("abc")).toBe("••••");
});
```

Run: `cd $APP && npx jest src/settings`
Expected: `Cannot find module '../store'`

- [ ] **Step 2: 実装する**

`src/settings/store.ts`:

```ts
// Settings kept on the device. The connection key lives separately in SecureStore (storage.ts).
export type ReturnTiming = "sent" | "answered" | "spoken";
export type LaunchableApp = { packageName: string; label: string };
export type Settings = {
  userName: string;
  returnEnabled: boolean;
  returnApp: LaunchableApp | null;
  returnTiming: ReturnTiming;
  recentApps: LaunchableApp[];
};

export interface KeyValueStore {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
}

export const SETTINGS_KEY = "trv2.settings";
export const USER_NAME_RE = /^[a-z0-9]{3,20}$/;
const ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";
const TIMINGS: ReturnTiming[] = ["sent", "answered", "spoken"];

export function randomUserName(random: () => number = Math.random): string {
  let name = "";
  for (let i = 0; i < 6; i += 1) {
    name += ALPHABET[Math.floor(random() * ALPHABET.length) % ALPHABET.length];
  }
  return name;
}

function isApp(value: unknown): value is LaunchableApp {
  const app = value as LaunchableApp;
  return typeof app === "object" && app !== null && typeof app.packageName === "string" && typeof app.label === "string";
}

function parse(raw: string | null): Record<string, unknown> {
  if (!raw) return {};
  try {
    const value = JSON.parse(raw);
    return typeof value === "object" && value !== null ? value : {};
  } catch {
    return {};
  }
}

export async function loadSettings(store: KeyValueStore, random: () => number = Math.random): Promise<Settings> {
  const raw = parse(await store.getItem(SETTINGS_KEY));
  const userName = typeof raw.userName === "string" && USER_NAME_RE.test(raw.userName) ? raw.userName : null;
  const settings: Settings = {
    userName: userName ?? randomUserName(random),
    returnEnabled: typeof raw.returnEnabled === "boolean" ? raw.returnEnabled : true,
    returnApp: isApp(raw.returnApp) ? raw.returnApp : null,
    returnTiming: TIMINGS.includes(raw.returnTiming as ReturnTiming) ? (raw.returnTiming as ReturnTiming) : "sent",
    recentApps: Array.isArray(raw.recentApps) ? raw.recentApps.filter(isApp) : [],
  };
  if (userName === null) await saveSettings(store, settings);
  return settings;
}

export async function saveSettings(store: KeyValueStore, settings: Settings): Promise<void> {
  await store.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

export function withRecentApp(recent: LaunchableApp[], app: LaunchableApp, max = 5): LaunchableApp[] {
  return [app, ...recent.filter((a) => a.packageName !== app.packageName)].slice(0, max);
}

export function maskKey(key: string): string {
  return key.length <= 4 ? "••••" : `••••••••${key.slice(-4)}`;
}
```

`src/settings/storage.ts`:

```ts
// Device storage adapters: AsyncStorage for settings, SecureStore for the connection key.
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";

import { KeyValueStore } from "./store";

const API_KEY = "trv2.apiKey";

export const settingsStore: KeyValueStore = {
  getItem: (key) => AsyncStorage.getItem(key),
  setItem: (key, value) => AsyncStorage.setItem(key, value),
};

export function loadApiKey(): Promise<string | null> {
  return SecureStore.getItemAsync(API_KEY);
}

export function saveApiKey(key: string): Promise<void> {
  return SecureStore.setItemAsync(API_KEY, key);
}

export function deleteApiKey(): Promise<void> {
  return SecureStore.deleteItemAsync(API_KEY);
}
```

- [ ] **Step 3: テストを通す**

Run: `cd $APP && npx jest src/settings && npx tsc --noEmit`
Expected: 7 passed。型エラーなし。

- [ ] **Step 4: コミット**

```bash
cd $APP && git add src/settings && git commit -m "feat: load and save app settings"
```

---

### Task 3: API クライアント

**Files:**
- Create: `src/api/client.ts`
- Test: `src/api/__tests__/client.test.ts`

**Interfaces:**
- Produces: `ApiErrorKind = "invalid_key" | "bad_request" | "not_found" | "rate_limited" | "server" | "network"`、`ApiError`（`kind`）、`Point`、`HeadingSample`、`AskBody`、`AskAccepted`、`AskResult`、`ApiClient`（`constructor({ baseUrl, apiKey, userName, fetchFn?, sleep?, maxAttempts? })`・`postAsk(body)`・`getAsk(askId)`・`checkKey()`）。`GET` は `rate_limited`・`server`・`network` を最大3回まで試し直す。`POST` は `rate_limited` だけ試し直す（二重の質問を避ける）。

- [ ] **Step 1: 失敗するテストを書く**

`src/api/__tests__/client.test.ts`:

```ts
import { ApiClient, ApiError } from "../client";

type Call = { url: string; init: RequestInit };

function fakeFetch(responses: Array<{ status: number; body?: unknown } | Error>) {
  const calls: Call[] = [];
  const fn = async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    const next = responses.shift()!;
    if (next instanceof Error) throw next;
    return { status: next.status, json: async () => next.body ?? {} } as Response;
  };
  return { fn: fn as unknown as typeof fetch, calls };
}

function client(responses: Parameters<typeof fakeFetch>[0]) {
  const fake = fakeFetch(responses);
  const sleeps: number[] = [];
  const api = new ApiClient({ baseUrl: "https://api.example/Prod/", apiKey: "k", userName: "rider01", fetchFn: fake.fn, sleep: async (ms) => { sleeps.push(ms); } });
  return { api, calls: fake.calls, sleeps };
}

const ACCEPTED = { askId: "a", conversationId: "c", conversationExpiresAt: "2026-10-16T03:15:00.000Z" };

test("postAsk sends headers and json", async () => {
  const { api, calls } = client([{ status: 202, body: ACCEPTED }]);
  expect(await api.postAsk({ text: "Q" })).toEqual(ACCEPTED);
  expect(calls[0].url).toBe("https://api.example/Prod/asks");
  expect(calls[0].init.method).toBe("POST");
  expect(calls[0].init.headers).toEqual({ "content-type": "application/json", "x-api-key": "k", "x-user-name": "rider01" });
  expect(JSON.parse(calls[0].init.body as string)).toEqual({ text: "Q" });
});

test.each([
  [403, "invalid_key"],
  [400, "bad_request"],
  [404, "not_found"],
  [500, "server"],
])("status %i is %s", async (status, kind) => {
  const { api } = client([{ status }, { status }, { status }]);
  await expect(api.getAsk("a")).rejects.toMatchObject({ kind });
});

test("get retries transient errors then succeeds", async () => {
  const { api, sleeps } = client([new TypeError("offline"), { status: 503 }, { status: 200, body: { askId: "a", status: "processing" } }]);
  expect((await api.getAsk("a")).status).toBe("processing");
  expect(sleeps).toEqual([500, 1000]);
});

test("post does not retry network errors but retries 429", async () => {
  const offline = client([new TypeError("offline")]);
  await expect(offline.api.postAsk({ text: "Q" })).rejects.toMatchObject({ kind: "network" });
  expect(offline.calls).toHaveLength(1);
  const limited = client([{ status: 429 }, { status: 202, body: ACCEPTED }]);
  expect(await limited.api.postAsk({ text: "Q" })).toEqual(ACCEPTED);
});

test("invalid key is not retried", async () => {
  const { api, calls } = client([{ status: 403 }]);
  await expect(api.getAsk("a")).rejects.toBeInstanceOf(ApiError);
  expect(calls).toHaveLength(1);
});

test("checkKey treats 404 as a working key", async () => {
  await expect(client([{ status: 404 }]).api.checkKey()).resolves.toBeUndefined();
  await expect(client([{ status: 403 }]).api.checkKey()).rejects.toMatchObject({ kind: "invalid_key" });
});
```

Run: `cd $APP && npx jest src/api`
Expected: `Cannot find module '../client'`

- [ ] **Step 2: 実装する**

`src/api/client.ts`:

```ts
// Backend API client (Backend/openapi.yaml). Errors are classified so the ask flow can pick the spoken message.
export type ApiErrorKind = "invalid_key" | "bad_request" | "not_found" | "rate_limited" | "server" | "network";

export class ApiError extends Error {
  constructor(public readonly kind: ApiErrorKind, message?: string) {
    super(message ?? kind);
  }
}

export type Point = { latitude: number; longitude: number };
export type HeadingSample = Point & { at: string };
export type AskBody = {
  audio?: string;
  text?: string;
  location?: Point | null;
  headingSample?: HeadingSample | null;
  conversationId?: string | null;
};
export type AskAccepted = { askId: string; conversationId: string; conversationExpiresAt: string };
export type AskResult = {
  askId: string;
  status: "processing" | "completed" | "failed";
  transcript: string | null;
  answer: string | null;
  audio: { seq: number; url: string }[];
  error: string | null;
  timings: Record<string, string>;
};

type Options = {
  baseUrl: string;
  apiKey: string;
  userName: string;
  fetchFn?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
  maxAttempts?: number;
};

const TRANSIENT: ApiErrorKind[] = ["rate_limited", "server", "network"];
// Any UUID works: a valid key gets 404 for an unknown ask, an invalid key gets 403.
const PROBE_ASK_ID = "00000000-0000-4000-8000-000000000000";

function kindFor(status: number): ApiErrorKind | null {
  if (status === 403) return "invalid_key";
  if (status === 400) return "bad_request";
  if (status === 404) return "not_found";
  if (status === 429) return "rate_limited";
  if (status >= 500) return "server";
  return null;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchFn: typeof fetch;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly maxAttempts: number;

  constructor(private readonly options: Options) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.fetchFn = options.fetchFn ?? fetch;
    this.sleep = options.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
    this.maxAttempts = options.maxAttempts ?? 3;
  }

  postAsk(body: AskBody): Promise<AskAccepted> {
    // Only 429 is retried for POST: a lost response may already have created an ask.
    return this.request<AskAccepted>("POST", "/asks", body, ["rate_limited"]);
  }

  getAsk(askId: string): Promise<AskResult> {
    return this.request<AskResult>("GET", `/asks/${encodeURIComponent(askId)}`, undefined, TRANSIENT);
  }

  async checkKey(): Promise<void> {
    try {
      await this.request("GET", `/asks/${PROBE_ASK_ID}`, undefined, TRANSIENT);
    } catch (error) {
      if (error instanceof ApiError && error.kind === "not_found") return;
      throw error;
    }
  }

  private async request<T>(method: string, path: string, body: unknown, retryOn: ApiErrorKind[]): Promise<T> {
    let lastError: ApiError = new ApiError("network");
    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      try {
        return await this.once<T>(method, path, body);
      } catch (error) {
        lastError = error instanceof ApiError ? error : new ApiError("network", String(error));
        if (!retryOn.includes(lastError.kind) || attempt === this.maxAttempts) throw lastError;
        await this.sleep(500 * attempt);
      }
    }
    throw lastError;
  }

  private async once<T>(method: string, path: string, body: unknown): Promise<T> {
    let response: Response;
    try {
      response = await this.fetchFn(`${this.baseUrl}${path}`, {
        method,
        headers: { "content-type": "application/json", "x-api-key": this.options.apiKey, "x-user-name": this.options.userName },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (error) {
      throw new ApiError("network", String(error));
    }
    const kind = kindFor(response.status);
    if (kind) throw new ApiError(kind, `HTTP ${response.status}`);
    return (await response.json()) as T;
  }
}
```

- [ ] **Step 3: テストを通す**

Run: `cd $APP && npx jest src/api && npx tsc --noEmit`
Expected: 9 passed。型エラーなし。

- [ ] **Step 4: コミット**

```bash
cd $APP && git add src/api && git commit -m "feat: add backend api client with error kinds and retries"
```

---

### Task 4: ポーリングと会話

**Files:**
- Create: `src/ask/polling.ts`、`src/ask/conversation.ts`
- Test: `src/ask/__tests__/polling.test.ts`、`src/ask/__tests__/conversation.test.ts`

**Interfaces:**
- Consumes: `AskResult`・`ApiError`（Task 3）
- Produces: `nextDelay(elapsedMs) => number`、`POLL_TIMEOUT_MS = 120000`、`pollUntilDone(get, { sleep, now, isCancelled }) => Promise<AskResult | "timeout" | "cancelled">`（`invalid_key`・`bad_request`・`not_found` は投げ直し、ほかの失敗は次の回に持ち越す）、`ConversationState`（`current(now) => string | null`・`update(id, expiresAtIso)`・`reset()`・`expiresAt(now) => number | null`）。

- [ ] **Step 1: 失敗するテストを書く**

`src/ask/__tests__/polling.test.ts`:

```ts
import { ApiError, AskResult } from "../../api/client";
import { nextDelay, pollUntilDone, POLL_TIMEOUT_MS } from "../polling";

const result = (status: AskResult["status"]): AskResult => ({ askId: "a", status, transcript: null, answer: null, audio: [], error: null, timings: {} });

function clock() {
  let now = 0;
  return { now: () => now, sleep: async (ms: number) => { now += ms; } };
}

test("delays are 1s for 10s then 2s", () => {
  expect(nextDelay(0)).toBe(1000);
  expect(nextDelay(9999)).toBe(1000);
  expect(nextDelay(10000)).toBe(2000);
});

test("returns the first finished result", async () => {
  const c = clock();
  const answers = [result("processing"), result("processing"), result("completed")];
  const done = await pollUntilDone(async () => answers.shift()!, { ...c, isCancelled: () => false });
  expect(done).toMatchObject({ status: "completed" });
  expect(c.now()).toBe(3000);
});

test("transient errors are skipped", async () => {
  const c = clock();
  const outcomes: Array<AskResult | Error> = [new ApiError("network"), result("failed")];
  const done = await pollUntilDone(async () => { const o = outcomes.shift()!; if (o instanceof Error) throw o; return o; }, { ...c, isCancelled: () => false });
  expect(done).toMatchObject({ status: "failed" });
});

test("invalid key stops polling", async () => {
  const c = clock();
  await expect(pollUntilDone(async () => { throw new ApiError("invalid_key"); }, { ...c, isCancelled: () => false })).rejects.toMatchObject({ kind: "invalid_key" });
});

test("gives up after two minutes", async () => {
  const c = clock();
  expect(await pollUntilDone(async () => result("processing"), { ...c, isCancelled: () => false })).toBe("timeout");
  expect(c.now()).toBeGreaterThanOrEqual(POLL_TIMEOUT_MS);
  expect(c.now()).toBeLessThan(POLL_TIMEOUT_MS + 2000);
});

test("cancellation stops polling", async () => {
  const c = clock();
  let calls = 0;
  const done = await pollUntilDone(async () => { calls += 1; return result("processing"); }, { ...c, isCancelled: () => calls >= 2 });
  expect(done).toBe("cancelled");
});
```

`src/ask/__tests__/conversation.test.ts`:

```ts
import { ConversationState } from "../conversation";

test("conversation continues until it expires", () => {
  const c = new ConversationState();
  expect(c.current(0)).toBeNull();
  c.update("abc", "1970-01-01T00:15:00.000Z");
  expect(c.current(14 * 60 * 1000)).toBe("abc");
  expect(c.expiresAt(14 * 60 * 1000)).toBe(15 * 60 * 1000);
  expect(c.current(15 * 60 * 1000)).toBeNull();
  expect(c.expiresAt(15 * 60 * 1000)).toBeNull();
});

test("reset starts a new conversation", () => {
  const c = new ConversationState();
  c.update("abc", "2999-01-01T00:00:00.000Z");
  c.reset();
  expect(c.current(0)).toBeNull();
});

test("unparseable expiry means no conversation", () => {
  const c = new ConversationState();
  c.update("abc", "not a date");
  expect(c.current(0)).toBeNull();
});
```

Run: `cd $APP && npx jest src/ask`
Expected: `Cannot find module '../polling'`・`'../conversation'`

- [ ] **Step 2: 実装する**

`src/ask/polling.ts`:

```ts
// Poll schedule from 07 UC-5: every 1 s for 10 s, then every 2 s, give up at 120 s.
import { ApiError, AskResult } from "../api/client";

export const POLL_FAST_MS = 1000;
export const POLL_SLOW_MS = 2000;
export const FAST_WINDOW_MS = 10_000;
export const POLL_TIMEOUT_MS = 120_000;
const FATAL = ["invalid_key", "bad_request", "not_found"];

export function nextDelay(elapsedMs: number): number {
  return elapsedMs < FAST_WINDOW_MS ? POLL_FAST_MS : POLL_SLOW_MS;
}

type Deps = { sleep: (ms: number) => Promise<void>; now: () => number; isCancelled: () => boolean };

export async function pollUntilDone(get: () => Promise<AskResult>, deps: Deps): Promise<AskResult | "timeout" | "cancelled"> {
  const startedAt = deps.now();
  for (;;) {
    const elapsed = deps.now() - startedAt;
    if (elapsed >= POLL_TIMEOUT_MS) return "timeout";
    await deps.sleep(nextDelay(elapsed));
    if (deps.isCancelled()) return "cancelled";
    try {
      const result = await get();
      if (result.status !== "processing") return result;
    } catch (error) {
      if (error instanceof ApiError && FATAL.includes(error.kind)) throw error;
    }
  }
}
```

`src/ask/conversation.ts`:

```ts
// The conversation id the Backend issued and when it lapses (adr/0003). Kept in memory only.
export class ConversationState {
  private id: string | null = null;
  private expiry = 0;

  current(now: number): string | null {
    if (this.id !== null && Number.isFinite(this.expiry) && now < this.expiry) return this.id;
    this.reset();
    return null;
  }

  update(id: string, expiresAtIso: string): void {
    this.id = id;
    this.expiry = Date.parse(expiresAtIso);
  }

  reset(): void {
    this.id = null;
    this.expiry = 0;
  }

  expiresAt(now: number): number | null {
    return this.current(now) === null ? null : this.expiry;
  }
}
```

- [ ] **Step 3: テストを通す**

Run: `cd $APP && npx jest src/ask && npx tsc --noEmit`
Expected: 9 passed。

- [ ] **Step 4: コミット**

```bash
cd $APP && git add src/ask/polling.ts src/ask/conversation.ts src/ask/__tests__/polling.test.ts src/ask/__tests__/conversation.test.ts
git commit -m "feat: poll for answers and track the conversation"
```

---

### Task 5: 方位の材料と録音のファイル

**Files:**
- Create: `src/location/heading.ts`、`src/ask/recordings.ts`
- Test: `src/location/__tests__/heading.test.ts`、`src/ask/__tests__/recordings.test.ts`

**Interfaces:**
- Consumes: `HeadingSample`（Task 3）
- Produces: `Fix = { latitude: number; longitude: number; timestamp: number }`、`distanceMeters(a, b) => number`、`pickHeadingSample(fixes, current) => HeadingSample | null`（現在の点より前で、60秒以内・15m 以上離れた点のうち一番新しいもの）、`recordingName(now) => string`（`rec-<ms>.pcm`）、`recordingsToDelete(names, keep?) => string[]`（新しい順に10件を残す）。

- [ ] **Step 1: 失敗するテストを書く**

`src/location/__tests__/heading.test.ts`:

```ts
import { distanceMeters, Fix, pickHeadingSample } from "../heading";

const at = (latitude: number, timestamp: number): Fix => ({ latitude, longitude: 139.7671, timestamp });
const NOW = 1_800_000_000_000;
const current = at(35.6812, NOW);

test("distance", () => {
  expect(distanceMeters(at(35.68066, 0), current)).toBeCloseTo(60, 0);
});

test("picks the newest point far enough behind", () => {
  const fixes = [at(35.6800, NOW - 30_000), at(35.6806, NOW - 10_000), at(35.6811, NOW - 2_000)];
  expect(pickHeadingSample(fixes, current)).toEqual({ latitude: 35.6806, longitude: 139.7671, at: new Date(NOW - 10_000).toISOString() });
});

test("test_no_sample_when_stationary", () => {
  const fixes = [at(35.68119, NOW - 20_000), at(35.6812, NOW - 10_000)];
  expect(pickHeadingSample(fixes, current)).toBeNull();
});

test("ignores points older than a minute and points not before the current one", () => {
  expect(pickHeadingSample([at(35.6790, NOW - 61_000)], current)).toBeNull();
  expect(pickHeadingSample([at(35.6790, NOW + 1_000)], current)).toBeNull();
  expect(pickHeadingSample([], current)).toBeNull();
});
```

`src/ask/__tests__/recordings.test.ts`:

```ts
import { recordingName, recordingsToDelete } from "../recordings";

test("name carries the time", () => {
  expect(recordingName(1234)).toBe("rec-1234.pcm");
});

test("keeps the newest ten recordings", () => {
  const names = Array.from({ length: 12 }, (_, i) => recordingName(1000 + i)).concat(["notes.txt"]);
  expect(recordingsToDelete(names).sort()).toEqual(["rec-1000.pcm", "rec-1001.pcm"]);
  expect(recordingsToDelete(names.slice(0, 3))).toEqual([]);
});
```

Run: `cd $APP && npx jest src/location src/ask/__tests__/recordings.test.ts`
Expected: `Cannot find module`

- [ ] **Step 2: 実装する**

`src/location/heading.ts`:

```ts
// Picks the older point the Backend uses to work out the direction of travel (07 UC-5).
import { HeadingSample } from "../api/client";

export type Fix = { latitude: number; longitude: number; timestamp: number };

export const MIN_SAMPLE_DISTANCE_M = 15;
export const MAX_SAMPLE_AGE_MS = 60_000;

export function distanceMeters(a: Fix, b: Fix): number {
  const r = 6_371_000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.latitude - a.latitude);
  const dLon = toRad(b.longitude - a.longitude);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.latitude)) * Math.cos(toRad(b.latitude)) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}

export function pickHeadingSample(fixes: Fix[], current: Fix): HeadingSample | null {
  const candidates = fixes.filter(
    (f) =>
      f.timestamp < current.timestamp &&
      current.timestamp - f.timestamp <= MAX_SAMPLE_AGE_MS &&
      distanceMeters(f, current) >= MIN_SAMPLE_DISTANCE_M,
  );
  if (candidates.length === 0) return null;
  const newest = candidates.reduce((a, b) => (b.timestamp > a.timestamp ? b : a));
  return { latitude: newest.latitude, longitude: newest.longitude, at: new Date(newest.timestamp).toISOString() };
}
```

`src/ask/recordings.ts`:

```ts
// The last few recordings stay on the device for the recording check screen (US-C-06.001).
export const KEEP_RECORDINGS = 10;
const NAME_RE = /^rec-(\d+)\.pcm$/;

export function recordingName(now: number): string {
  return `rec-${now}.pcm`;
}

export function recordingsToDelete(names: string[], keep = KEEP_RECORDINGS): string[] {
  const recordings = names
    .map((name) => ({ name, match: NAME_RE.exec(name) }))
    .filter((r) => r.match !== null)
    .sort((a, b) => Number(b.match![1]) - Number(a.match![1]));
  return recordings.slice(keep).map((r) => r.name);
}
```

- [ ] **Step 3: テストを通す**

Run: `cd $APP && npx jest src/location src/ask/__tests__/recordings.test.ts && npx tsc --noEmit`
Expected: 6 passed。

- [ ] **Step 4: コミット**

```bash
cd $APP && git add src/location src/ask/recordings.ts src/ask/__tests__/recordings.test.ts
git commit -m "feat: choose heading samples and keep recent recordings"
```

---

### Task 6: 一巡の状態機械と失敗の文

**Files:**
- Create: `src/ask/flow.ts`、`src/ask/failures.ts`
- Test: `src/ask/__tests__/flow.test.ts`

**Interfaces:**
- Consumes: `Settings`（Task 2）
- Produces: `Source = "handsfree" | "screen"`、`Phase`、`FailureReason = "no_speech" | "transcribe_failed" | "agent_failed" | "tts_failed" | "timeout" | "network" | "invalid_key" | "no_key" | "mic"`、`FlowState = { phase; source; askId; answer; failure; phoneMic; phaseStartedAt }`、`FlowEvent`、`IDLE`、`reduce(state, event)`、`isBusy(state)`、`Moment = "sent" | "answered" | "spoken"`、`shouldReturnNow(source, settings, moment)`。`failures.ts`: `spokenMessage(reason)`、`BUSY_MESSAGE`、`failureFromServer(error: string | null) => FailureReason`。

- [ ] **Step 1: 失敗するテストを書く**

`src/ask/__tests__/flow.test.ts`:

```ts
import { BUSY_MESSAGE, failureFromServer, spokenMessage } from "../failures";
import { FlowState, IDLE, isBusy, reduce, shouldReturnNow } from "../flow";
import { Settings } from "../../settings/store";

const MAPS = { packageName: "maps", label: "マップ" };
const SETTINGS: Settings = { userName: "rider01", returnEnabled: true, returnApp: MAPS, returnTiming: "sent", recentApps: [] };

function run(events: Parameters<typeof reduce>[1][]): FlowState {
  return events.reduce(reduce, IDLE);
}

test("happy path", () => {
  const s = run([
    { type: "start", source: "handsfree", now: 1 },
    { type: "stopRecording", now: 2 },
    { type: "sent", askId: "a", now: 3 },
    { type: "answered", answer: "A", now: 4 },
  ]);
  expect(s).toMatchObject({ phase: "speaking", source: "handsfree", askId: "a", answer: "A", phaseStartedAt: 4 });
  expect(reduce(s, { type: "spoken", now: 5 })).toEqual(IDLE);
});

test("out of order events are ignored", () => {
  expect(reduce(IDLE, { type: "sent", askId: "a", now: 1 })).toEqual(IDLE);
  const recording = run([{ type: "start", source: "screen", now: 1 }]);
  expect(reduce(recording, { type: "start", source: "handsfree", now: 2 })).toBe(recording);
  expect(reduce(recording, { type: "answered", answer: "A", now: 2 })).toBe(recording);
});

test("phone mic flag only while recording", () => {
  const recording = run([{ type: "start", source: "handsfree", now: 1 }]);
  expect(reduce(recording, { type: "phoneMic", now: 2 }).phoneMic).toBe(true);
  expect(reduce(IDLE, { type: "phoneMic", now: 2 }).phoneMic).toBe(false);
});

test("failure and a new start after it", () => {
  const failed = run([{ type: "start", source: "screen", now: 1 }, { type: "fail", reason: "network", now: 2 }]);
  expect(failed).toMatchObject({ phase: "failed", failure: "network" });
  expect(isBusy(failed)).toBe(false);
  expect(reduce(failed, { type: "start", source: "handsfree", now: 3 })).toMatchObject({ phase: "recording", failure: null, source: "handsfree" });
});

test("busy phases", () => {
  expect(isBusy(IDLE)).toBe(false);
  expect(isBusy(run([{ type: "start", source: "screen", now: 1 }]))).toBe(true);
});

test("return only for handsfree at the chosen moment", () => {
  expect(shouldReturnNow("handsfree", SETTINGS, "sent")).toBe(true);
  expect(shouldReturnNow("handsfree", SETTINGS, "answered")).toBe(false);
  expect(shouldReturnNow("screen", SETTINGS, "sent")).toBe(false);
  expect(shouldReturnNow("handsfree", { ...SETTINGS, returnEnabled: false }, "sent")).toBe(false);
  expect(shouldReturnNow("handsfree", { ...SETTINGS, returnApp: null }, "sent")).toBe(false);
  expect(shouldReturnNow(null, SETTINGS, "sent")).toBe(false);
});

test("spoken messages", () => {
  expect(spokenMessage("no_speech")).toBe("聞き取れませんでした。もう一度お話しください。");
  expect(spokenMessage("agent_failed")).toBe("うまく答えられませんでした。もう一度お話しください。");
  expect(spokenMessage("transcribe_failed")).toBe(spokenMessage("agent_failed"));
  expect(spokenMessage("timeout")).toBe("時間切れです。もう一度お話しください。");
  expect(spokenMessage("network")).toBe("通信できないため、質問できませんでした。");
  expect(spokenMessage("invalid_key")).toBe("接続キーを確かめてください。");
  expect(spokenMessage("no_key")).toBe(spokenMessage("invalid_key"));
  expect(spokenMessage("mic")).toBe("録音できませんでした。");
  expect(BUSY_MESSAGE).toBe("いま応答中です。少し待ってからもう一度お話しください。");
});

test("server failure reasons", () => {
  expect(failureFromServer("no_speech")).toBe("no_speech");
  expect(failureFromServer("tts_failed")).toBe("tts_failed");
  expect(failureFromServer("something_new")).toBe("agent_failed");
  expect(failureFromServer(null)).toBe("agent_failed");
});
```

Run: `cd $APP && npx jest src/ask/__tests__/flow.test.ts`
Expected: `Cannot find module`

- [ ] **Step 2: 実装する**

`src/ask/flow.ts`:

```ts
// The ask loop as a pure state machine (spec §5.2). Screens, cues and returning to the nav app read this state.
import type { Settings } from "../settings/store";

export type Source = "handsfree" | "screen";
export type Phase = "idle" | "recording" | "sending" | "waiting" | "speaking" | "failed";
export type FailureReason =
  | "no_speech"
  | "transcribe_failed"
  | "agent_failed"
  | "tts_failed"
  | "timeout"
  | "network"
  | "invalid_key"
  | "no_key"
  | "mic";

export type FlowState = {
  phase: Phase;
  source: Source | null;
  askId: string | null;
  answer: string | null;
  failure: FailureReason | null;
  phoneMic: boolean;
  phaseStartedAt: number;
};

export type FlowEvent =
  | { type: "start"; source: Source; now: number }
  | { type: "phoneMic"; now: number }
  | { type: "stopRecording"; now: number }
  | { type: "sent"; askId: string; now: number }
  | { type: "answered"; answer: string; now: number }
  | { type: "spoken"; now: number }
  | { type: "fail"; reason: FailureReason; now: number }
  | { type: "dismiss"; now: number };

export const IDLE: FlowState = { phase: "idle", source: null, askId: null, answer: null, failure: null, phoneMic: false, phaseStartedAt: 0 };

export function reduce(state: FlowState, event: FlowEvent): FlowState {
  switch (event.type) {
    case "start":
      return state.phase === "idle" || state.phase === "failed"
        ? { ...IDLE, phase: "recording", source: event.source, phaseStartedAt: event.now }
        : state;
    case "phoneMic":
      return state.phase === "recording" ? { ...state, phoneMic: true } : state;
    case "stopRecording":
      return state.phase === "recording" ? { ...state, phase: "sending", phaseStartedAt: event.now } : state;
    case "sent":
      return state.phase === "sending" ? { ...state, phase: "waiting", askId: event.askId, phaseStartedAt: event.now } : state;
    case "answered":
      return state.phase === "waiting" ? { ...state, phase: "speaking", answer: event.answer, phaseStartedAt: event.now } : state;
    case "fail":
      return state.phase === "idle" ? state : { ...state, phase: "failed", failure: event.reason, phaseStartedAt: event.now };
    case "spoken":
    case "dismiss":
      return state.phase === "idle" ? state : IDLE;
  }
}

export function isBusy(state: FlowState): boolean {
  return state.phase !== "idle" && state.phase !== "failed";
}

export type Moment = "sent" | "answered" | "spoken";

export function shouldReturnNow(source: Source | null, settings: Settings, moment: Moment): boolean {
  return source === "handsfree" && settings.returnEnabled && settings.returnApp !== null && settings.returnTiming === moment;
}
```

`src/ask/failures.ts`:

```ts
// What the rider hears when something goes wrong (spec §8.1).
import type { FailureReason } from "./flow";

export const BUSY_MESSAGE = "いま応答中です。少し待ってからもう一度お話しください。";

const MESSAGES: Record<FailureReason, string> = {
  no_speech: "聞き取れませんでした。もう一度お話しください。",
  transcribe_failed: "うまく答えられませんでした。もう一度お話しください。",
  agent_failed: "うまく答えられませんでした。もう一度お話しください。",
  tts_failed: "うまく答えられませんでした。もう一度お話しください。",
  timeout: "時間切れです。もう一度お話しください。",
  network: "通信できないため、質問できませんでした。",
  invalid_key: "接続キーを確かめてください。",
  no_key: "接続キーを確かめてください。",
  mic: "録音できませんでした。",
};

export function spokenMessage(reason: FailureReason): string {
  return MESSAGES[reason];
}

const SERVER_REASONS: FailureReason[] = ["no_speech", "transcribe_failed", "agent_failed", "tts_failed"];

export function failureFromServer(error: string | null): FailureReason {
  return SERVER_REASONS.includes(error as FailureReason) ? (error as FailureReason) : "agent_failed";
}
```

- [ ] **Step 3: テストを通す**

Run: `cd $APP && npx jest src/ask && npx tsc --noEmit`
Expected: すべて PASS。

- [ ] **Step 4: コミット**

```bash
cd $APP && git add src/ask/flow.ts src/ask/failures.ts src/ask/__tests__/flow.test.ts
git commit -m "feat: model the ask loop as a pure state machine"
```

---

### Task 7: 一巡の司令塔

**Files:**
- Create: `src/ask/controller.ts`
- Test: `src/ask/__tests__/controller.test.ts`

**Interfaces:**
- Consumes: Task 2〜6 のすべて
- Produces: `RECORD_LIMIT_MS = 20000`・`TICK_MS = 250`・`WAITING_CUE_MS = 5000`・`FAILED_SCREEN_MS = 5000`、`AskApi`（`postAsk`・`getAsk`）、`Deps`（下のコードのとおり）、`AskController`（`state`・`press()`（インカムのボタン）・`tapToTalk()`・`stopRecording()`・`cancel()`・`resetConversation()`・`run(source) => Promise<void>`）。

- [ ] **Step 1: 失敗するテストを書く**

`src/ask/__tests__/controller.test.ts`:

```ts
import { ApiError, AskAccepted, AskBody, AskResult } from "../../api/client";
import { Settings } from "../../settings/store";
import { AskApi, AskController, Deps, RECORD_LIMIT_MS } from "../controller";
import { ConversationState } from "../conversation";
import { FlowState } from "../flow";

const MAPS = { packageName: "maps", label: "マップ" };
const SETTINGS: Settings = { userName: "rider01", returnEnabled: true, returnApp: MAPS, returnTiming: "sent", recentApps: [] };
const ACCEPTED: AskAccepted = { askId: "a1", conversationId: "c1", conversationExpiresAt: "2999-01-01T00:00:00.000Z" };
const done = (over: Partial<AskResult> = {}): AskResult => ({
  askId: "a1", status: "completed", transcript: "Q", answer: "愛鷹山です。", audio: [{ seq: 1, url: "https://audio/1.mp3" }], error: null, timings: {}, ...over,
});
const HERE = { latitude: 35.6812, longitude: 139.7671, timestamp: 100_000 };
const BEHIND = { latitude: 35.6806, longitude: 139.7671, timestamp: 90_000 };

type Options = {
  apiKey?: string | null;
  settings?: Settings;
  post?: () => Promise<AskAccepted>;
  results?: Array<AskResult | Error>;
  routeOk?: boolean;
  playError?: Error;
  stopAfterMs?: number | null;
};

function harness(options: Options = {}) {
  const log: string[] = [];
  const states: FlowState[] = [];
  const bodies: AskBody[] = [];
  let now = 0;
  const results = [...(options.results ?? [done()])];
  let controller!: AskController;
  const api: AskApi = {
    postAsk: async (body) => { bodies.push(body); log.push("post"); return options.post ? options.post() : ACCEPTED; },
    getAsk: async () => { log.push("get"); const r = results.shift() ?? done(); if (r instanceof Error) throw r; return r; },
  };
  const deps: Deps = {
    now: () => now,
    sleep: async (ms) => {
      now += ms;
      if (options.stopAfterMs != null && controller.state.phase === "recording" && now >= options.stopAfterMs) controller.stopRecording();
    },
    settings: () => options.settings ?? SETTINGS,
    apiKey: () => (options.apiKey === undefined ? "key" : options.apiKey),
    api: () => api,
    conversation: new ConversationState(),
    route: { start: async (source) => { log.push(`route:${source}`); return options.routeOk ?? true; }, stop: async () => { log.push("route:stop"); } },
    recorder: { start: async () => { log.push("rec:start"); }, stop: async () => { log.push("rec:stop"); return "UENN"; }, cancel: async () => { log.push("rec:cancel"); } },
    location: { begin: () => { log.push("loc:begin"); }, end: () => ({ current: HERE, fixes: [BEHIND, HERE] }) },
    service: { start: () => { log.push("svc:start"); }, stop: () => { log.push("svc:stop"); } },
    nav: { returnTo: async (pkg) => { log.push(`return:${pkg}`); return true; } },
    cues: { start: () => log.push("cue:start"), sent: () => log.push("cue:sent"), waiting: () => log.push("cue:waiting"), failure: () => log.push("cue:failure") },
    player: { play: async (urls) => { log.push(`play:${urls.join(",")}`); if (options.playError) throw options.playError; }, stop: () => { log.push("play:stop"); } },
    speech: { say: async (text) => { log.push(`say:${text}`); }, stop: () => { log.push("say:stop"); } },
    onState: (s) => { states.push(s); },
    log: () => undefined,
  };
  controller = new AskController(deps);
  return { controller, log, states, bodies, deps, now: () => now };
}

test("handsfree happy path returns to nav right after sending", async () => {
  const h = harness({ stopAfterMs: 3000 });
  await h.controller.run("handsfree");
  expect(h.log).toEqual([
    "svc:start", "loc:begin", "route:handsfree", "cue:start", "rec:start", "rec:stop", "route:stop",
    "post", "cue:sent", "return:maps", "get", "play:https://audio/1.mp3", "svc:stop",
  ]);
  expect(h.bodies[0]).toEqual({
    audio: "UENN",
    location: { latitude: 35.6812, longitude: 139.7671 },
    headingSample: { latitude: 35.6806, longitude: 139.7671, at: new Date(90_000).toISOString() },
    conversationId: null,
  });
  expect(h.controller.state.phase).toBe("idle");
  expect(h.states.map((s) => s.phase)).toEqual(["recording", "sending", "waiting", "speaking", "idle"]);
});

test("screen questions never return to nav", async () => {
  const h = harness({ stopAfterMs: 1000 });
  await h.controller.run("screen");
  expect(h.log).toContain("route:screen");
  expect(h.log.some((l) => l.startsWith("return:"))).toBe(false);
});

test("return after the answer is spoken when chosen", async () => {
  const h = harness({ stopAfterMs: 1000, settings: { ...SETTINGS, returnTiming: "spoken" } });
  await h.controller.run("handsfree");
  expect(h.log.indexOf("return:maps")).toBeGreaterThan(h.log.indexOf("play:https://audio/1.mp3"));
});

test("recording stops by itself at the limit", async () => {
  const h = harness({ stopAfterMs: null });
  await h.controller.run("handsfree");
  expect(h.log).toContain("post");
  expect(h.now()).toBeGreaterThanOrEqual(RECORD_LIMIT_MS);
});

test("conversation id is reused on the next question", async () => {
  const h = harness({ stopAfterMs: 1000 });
  await h.controller.run("handsfree");
  await h.controller.run("handsfree");
  expect(h.bodies[1].conversationId).toBe("c1");
  h.controller.resetConversation();
  await h.controller.run("handsfree");
  expect(h.bodies[2].conversationId).toBeNull();
});

test("phone mic is flagged when the intercom route fails", async () => {
  const h = harness({ stopAfterMs: 1000, routeOk: false });
  await h.controller.run("handsfree");
  expect(h.states.some((s) => s.phase === "recording" && s.phoneMic)).toBe(true);
  expect(h.log).toContain("post");
});

test("no key fails with a spoken message and no recording", async () => {
  const h = harness({ apiKey: null });
  await h.controller.run("handsfree");
  expect(h.log).toEqual(["cue:failure", "say:接続キーを確かめてください。", "return:maps"]);
});

test("network failure on send", async () => {
  const h = harness({ stopAfterMs: 1000, post: async () => { throw new ApiError("network"); } });
  await h.controller.run("handsfree");
  expect(h.log).toContain("say:通信できないため、質問できませんでした。");
  expect(h.log).toContain("return:maps");
  expect(h.log).not.toContain("get");
});

test("server failure is spoken", async () => {
  const h = harness({ stopAfterMs: 1000, results: [done({ status: "failed", error: "no_speech", answer: null, audio: [] })] });
  await h.controller.run("handsfree");
  expect(h.log).toContain("say:聞き取れませんでした。もう一度お話しください。");
});

test("test_tts_failed_reads_answer_with_device_voice", async () => {
  const h = harness({ stopAfterMs: 1000, results: [done({ status: "failed", error: "tts_failed", audio: [] })] });
  await h.controller.run("handsfree");
  expect(h.log).toContain("say:愛鷹山です。");
  expect(h.log).not.toContain("cue:failure");
});

test("test_player_error_falls_back_to_device_voice", async () => {
  const h = harness({ stopAfterMs: 1000, playError: new Error("decode") });
  await h.controller.run("handsfree");
  expect(h.log).toContain("say:愛鷹山です。");
});

test("timeout after two minutes of processing", async () => {
  const processing = Array.from({ length: 200 }, () => done({ status: "processing" }));
  const h = harness({ stopAfterMs: 1000, results: processing });
  await h.controller.run("handsfree");
  expect(h.log).toContain("say:時間切れです。もう一度お話しください。");
  expect(h.log.filter((l) => l === "cue:waiting").length).toBeGreaterThan(10);
});

test("test_press_while_waiting_says_busy", async () => {
  const h = harness({ stopAfterMs: 1000, results: [done({ status: "processing" }), done()] });
  const running = h.controller.run("handsfree");
  while (h.controller.state.phase !== "waiting") await Promise.resolve();
  h.controller.press();
  await running;
  expect(h.log).toContain("say:いま応答中です。少し待ってからもう一度お話しください。");
  expect(h.log.filter((l) => l === "rec:start")).toHaveLength(1);
});

test("second press stops the recording", async () => {
  const h = harness({ stopAfterMs: null });
  const running = h.controller.run("handsfree");
  while (h.controller.state.phase !== "recording") await Promise.resolve();
  h.controller.press();
  await running;
  expect(h.now()).toBeLessThan(RECORD_LIMIT_MS);
});

test("cancel while recording discards the audio", async () => {
  const h = harness({ stopAfterMs: null });
  const running = h.controller.run("screen");
  while (h.controller.state.phase !== "recording") await Promise.resolve();
  h.controller.cancel();
  await running;
  expect(h.log).toContain("rec:cancel");
  expect(h.log).not.toContain("post");
  expect(h.controller.state.phase).toBe("idle");
});

test("cancel while waiting stops polling quietly", async () => {
  const processing = Array.from({ length: 50 }, () => done({ status: "processing" }));
  const h = harness({ stopAfterMs: 1000, results: processing });
  const running = h.controller.run("screen");
  while (h.controller.state.phase !== "waiting") await Promise.resolve();
  h.controller.cancel();
  await running;
  expect(h.log).not.toContain("cue:failure");
  expect(h.controller.state.phase).toBe("idle");
});

test("test_new_run_during_failed_screen_is_not_reset", async () => {
  let failPost = true;
  const h = harness({ stopAfterMs: 1000, post: async () => { if (failPost) throw new ApiError("network"); return ACCEPTED; } });
  const phase = () => h.controller.state.phase;
  const first = h.controller.run("screen");
  while (phase() !== "failed") await Promise.resolve();
  failPost = false;
  const secondStart = h.log.length;
  const second = h.controller.run("screen");
  await Promise.all([first, second]);
  const after = h.log.slice(secondStart);
  expect(after).toContain("play:https://audio/1.mp3");
  // The first run's cleanup must not stop the service the second run is using.
  expect(after.slice(0, after.indexOf("play:https://audio/1.mp3"))).not.toContain("svc:stop");
  expect(phase()).toBe("idle");
});
```

Run: `cd $APP && npx jest src/ask/__tests__/controller.test.ts`
Expected: `Cannot find module '../controller'`

- [ ] **Step 2: 実装する**

`src/ask/controller.ts`:

```ts
// Orchestrates one ask: record -> send -> (return to nav) -> wait -> speak. All side effects come in through Deps
// so the whole loop is testable; waits use deps.sleep, which is native in the app (setTimeout stops in the background).
import { ApiError, AskAccepted, AskBody, AskResult } from "../api/client";
import type { Settings } from "../settings/store";
import { Fix, pickHeadingSample } from "../location/heading";
import { ConversationState } from "./conversation";
import { BUSY_MESSAGE, failureFromServer, spokenMessage } from "./failures";
import { FailureReason, FlowEvent, FlowState, IDLE, isBusy, Moment, reduce, shouldReturnNow, Source } from "./flow";
import { pollUntilDone } from "./polling";

export const RECORD_LIMIT_MS = 20_000;
export const TICK_MS = 250;
export const WAITING_CUE_MS = 5_000;
export const FAILED_SCREEN_MS = 5_000;

export interface AskApi {
  postAsk(body: AskBody): Promise<AskAccepted>;
  getAsk(askId: string): Promise<AskResult>;
}

export type Deps = {
  now(): number;
  sleep(ms: number): Promise<void>;
  settings(): Settings;
  apiKey(): string | null;
  api(apiKey: string, userName: string): AskApi;
  conversation: ConversationState;
  route: { start(source: Source): Promise<boolean>; stop(): Promise<void> };
  recorder: { start(): Promise<void>; stop(): Promise<string>; cancel(): Promise<void> };
  location: { begin(): void; end(): { current: Fix | null; fixes: Fix[] } };
  service: { start(): void; stop(): void };
  nav: { returnTo(packageName: string): Promise<boolean> };
  cues: { start(): void; sent(): void; waiting(): void; failure(): void };
  player: { play(urls: string[]): Promise<void>; stop(): void };
  speech: { say(text: string): Promise<void>; stop(): void };
  onState(state: FlowState): void;
  log(event: string, data?: Record<string, unknown>): void;
};

type Recording = { audio: string; current: Fix | null; fixes: Fix[] };

function reasonFor(error: unknown): FailureReason {
  if (error instanceof ApiError) {
    if (error.kind === "invalid_key") return "invalid_key";
    if (error.kind === "bad_request") return "no_speech";
  }
  return "network";
}

export class AskController {
  state: FlowState = IDLE;
  private cancelled = false;
  private returned = false;
  private runId = 0;

  constructor(private readonly deps: Deps) {}

  /** The intercom button: start, stop the recording, or say that an answer is on its way. */
  press(): void {
    if (this.state.phase === "recording") {
      this.stopRecording();
    } else if (isBusy(this.state)) {
      void this.deps.speech.say(BUSY_MESSAGE);
    } else {
      void this.run("handsfree");
    }
  }

  tapToTalk(): void {
    if (!isBusy(this.state)) void this.run("screen");
  }

  stopRecording(): void {
    if (this.state.phase === "recording") this.dispatch({ type: "stopRecording", now: this.deps.now() });
  }

  cancel(): void {
    if (this.state.phase === "idle") return;
    this.cancelled = true;
    this.deps.player.stop();
    this.deps.speech.stop();
  }

  resetConversation(): void {
    this.deps.conversation.reset();
  }

  async run(source: Source): Promise<void> {
    const d = this.deps;
    const id = ++this.runId;
    this.cancelled = false;
    this.returned = false;
    this.dispatch({ type: "start", source, now: d.now() });
    let serviceStarted = false;
    try {
      const apiKey = d.apiKey();
      if (!apiKey) {
        await this.fail("no_key", id);
        return;
      }
      const settings = d.settings();
      const api = d.api(apiKey, settings.userName);
      d.service.start();
      serviceStarted = true;
      const recording = await this.record(source, id);
      if (recording === null) return;
      const accepted = await this.send(recording, api, id);
      if (accepted === null) return;
      await this.maybeReturn("sent", settings);
      const result = await this.waitForAnswer(accepted.askId, api, id);
      if (result === null) return;
      await this.speak(result, settings);
    } finally {
      // A newer run owns the screen state and the foreground service; leave both to it.
      if (id === this.runId) {
        this.dispatch({ type: "dismiss", now: d.now() });
        if (serviceStarted) d.service.stop();
      }
    }
  }

  private dispatch(event: FlowEvent): void {
    const next = reduce(this.state, event);
    if (next === this.state) return;
    this.state = next;
    this.deps.onState(next);
  }

  private isCurrent(id: number): boolean {
    return id === this.runId && !this.cancelled;
  }

  private async record(source: Source, id: number): Promise<Recording | null> {
    const d = this.deps;
    d.location.begin();
    const routed = await d.route.start(source);
    if (!routed) this.dispatch({ type: "phoneMic", now: d.now() });
    d.cues.start();
    try {
      await d.recorder.start();
    } catch {
      await d.route.stop();
      d.location.end();
      await this.fail("mic", id);
      return null;
    }
    const startedAt = d.now();
    while (this.state.phase === "recording" && this.isCurrent(id) && d.now() - startedAt < RECORD_LIMIT_MS) {
      await d.sleep(TICK_MS);
    }
    if (!this.isCurrent(id)) {
      await d.recorder.cancel();
      await d.route.stop();
      d.location.end();
      return null;
    }
    this.stopRecording();
    let audio: string;
    try {
      audio = await d.recorder.stop();
    } catch {
      await d.route.stop();
      d.location.end();
      await this.fail("mic", id);
      return null;
    }
    await d.route.stop();
    const { current, fixes } = d.location.end();
    return { audio, current, fixes };
  }

  private async send(recording: Recording, api: AskApi, id: number): Promise<AskAccepted | null> {
    const d = this.deps;
    const body: AskBody = {
      audio: recording.audio,
      location: recording.current ? { latitude: recording.current.latitude, longitude: recording.current.longitude } : null,
      headingSample: recording.current ? pickHeadingSample(recording.fixes, recording.current) : null,
      conversationId: d.conversation.current(d.now()),
    };
    try {
      const accepted = await api.postAsk(body);
      d.conversation.update(accepted.conversationId, accepted.conversationExpiresAt);
      this.dispatch({ type: "sent", askId: accepted.askId, now: d.now() });
      d.cues.sent();
      return accepted;
    } catch (error) {
      d.log("post_failed", { kind: error instanceof ApiError ? error.kind : "unknown" });
      await this.fail(reasonFor(error), id);
      return null;
    }
  }

  private async waitForAnswer(askId: string, api: AskApi, id: number): Promise<AskResult | null> {
    const d = this.deps;
    let sinceCue = 0;
    const sleep = async (ms: number) => {
      await d.sleep(ms);
      sinceCue += ms;
      if (sinceCue >= WAITING_CUE_MS) {
        sinceCue = 0;
        d.cues.waiting();
      }
    };
    let outcome: AskResult | "timeout" | "cancelled";
    try {
      outcome = await pollUntilDone(() => api.getAsk(askId), { sleep, now: d.now, isCancelled: () => !this.isCurrent(id) });
    } catch (error) {
      await this.fail(reasonFor(error), id);
      return null;
    }
    if (outcome === "cancelled") return null;
    if (outcome === "timeout") {
      await this.fail("timeout", id);
      return null;
    }
    const readable = outcome.status === "completed" || (outcome.error === "tts_failed" && !!outcome.answer);
    if (!readable) {
      await this.fail(failureFromServer(outcome.error), id);
      return null;
    }
    return outcome;
  }

  private async speak(result: AskResult, settings: Settings): Promise<void> {
    const d = this.deps;
    this.dispatch({ type: "answered", answer: result.answer ?? "", now: d.now() });
    await this.maybeReturn("answered", settings);
    const urls = [...result.audio].sort((a, b) => a.seq - b.seq).map((a) => a.url);
    let played = false;
    if (urls.length > 0) {
      try {
        await d.player.play(urls);
        played = true;
      } catch (error) {
        d.log("play_failed", { error: String(error) });
      }
    }
    if (!played && !this.cancelled && result.answer) await d.speech.say(result.answer);
    if (!this.cancelled) await this.maybeReturn("spoken", settings);
  }

  private async maybeReturn(moment: Moment, settings: Settings): Promise<void> {
    if (this.returned || this.cancelled || !shouldReturnNow(this.state.source, settings, moment)) return;
    this.returned = true;
    await this.deps.nav.returnTo(settings.returnApp!.packageName);
  }

  private async fail(reason: FailureReason, id: number): Promise<void> {
    const d = this.deps;
    this.dispatch({ type: "fail", reason, now: d.now() });
    d.cues.failure();
    await d.speech.say(spokenMessage(reason));
    const settings = d.settings();
    if (this.state.source === "handsfree") {
      // US-B-04.006: a failed answer still ends with the nav app in front.
      if (!this.returned && settings.returnEnabled && settings.returnApp) {
        this.returned = true;
        await d.nav.returnTo(settings.returnApp.packageName);
      }
      return;
    }
    let waited = 0;
    while (waited < FAILED_SCREEN_MS && this.isCurrent(id) && this.state.phase === "failed") {
      await d.sleep(TICK_MS);
      waited += TICK_MS;
    }
  }
}
```

- [ ] **Step 3: テストを通す**

Run: `cd $APP && npx jest src/ask && npx tsc --noEmit`
Expected: すべて PASS。

- [ ] **Step 4: コミット**

```bash
cd $APP && git add src/ask/controller.ts src/ask/__tests__/controller.test.ts
git commit -m "feat: orchestrate the ask loop with injectable side effects"
```

---

### Task 8: ネイティブモジュール `ride-service`

**Files:**
- Create: `modules/ride-service/expo-module.config.json`、`modules/ride-service/package.json`、`modules/ride-service/android/build.gradle`、`modules/ride-service/android/src/main/AndroidManifest.xml`、`modules/ride-service/android/src/main/java/com/touringproject/v2/rideservice/RideServiceModule.kt`、`.../RideForegroundService.kt`、`modules/ride-service/src/index.ts`

**Interfaces:**
- Produces: JS の `RideService`（`startService(): void`・`stopService(): void`・`sleep(ms): Promise<void>`・`launchApp(packageName): Promise<boolean>`・`listLaunchableApps(): Promise<LaunchableApp[]>`・`playTone(name: "dial" | "ack" | "beep" | "error", durationMs: number, stream: "call" | "music"): boolean`）。

- [ ] **Step 1: ファイルを書く**

`modules/ride-service/expo-module.config.json`:

```json
{ "platforms": ["android"], "android": { "modules": ["com.touringproject.v2.rideservice.RideServiceModule"] } }
```

`modules/ride-service/package.json`:

```json
{ "name": "ride-service", "version": "1.0.0", "main": "src/index.ts", "private": true }
```

`modules/ride-service/android/build.gradle`:

```gradle
plugins {
  id 'com.android.library'
  id 'expo-module-gradle-plugin'
}

group = 'com.touringproject.v2.rideservice'
version = '1.0.0'

android {
  namespace "com.touringproject.v2.rideservice"
  defaultConfig {
    versionCode 1
    versionName "1.0.0"
  }
}
```

`modules/ride-service/android/src/main/AndroidManifest.xml`:

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />
  <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
  <queries>
    <intent>
      <action android:name="android.intent.action.MAIN" />
      <category android:name="android.intent.category.LAUNCHER" />
    </intent>
  </queries>
  <application>
    <service
      android:name="com.touringproject.v2.rideservice.RideForegroundService"
      android:exported="false"
      android:foregroundServiceType="microphone|mediaPlayback" />
  </application>
</manifest>
```

`.../rideservice/RideForegroundService.kt`:

```kotlin
package com.touringproject.v2.rideservice

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder

// Keeps the process alive while an answer is awaited and read out in the background (adr/0004).
class RideForegroundService : Service() {
  override fun onBind(intent: Intent?): IBinder? = null

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    val manager = getSystemService(NotificationManager::class.java)
    manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "応答", NotificationManager.IMPORTANCE_LOW))
    val notification = Notification.Builder(this, CHANNEL_ID)
      .setContentTitle("Touring V2")
      .setContentText("応答中")
      .setSmallIcon(android.R.drawable.ic_btn_speak_now)
      .setOngoing(true)
      .build()
    startForeground(
      NOTIFICATION_ID,
      notification,
      ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
    )
    return START_NOT_STICKY
  }

  companion object {
    private const val CHANNEL_ID = "trv2_answer"
    private const val NOTIFICATION_ID = 1
  }
}
```

`.../rideservice/RideServiceModule.kt`:

```kotlin
package com.touringproject.v2.rideservice

import android.content.Intent
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Handler
import android.os.Looper
import android.util.Log
import expo.modules.kotlin.Promise
import expo.modules.kotlin.functions.Queues
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.text.Collator
import java.util.Locale

class RideServiceModule : Module() {
  private val context
    get() = requireNotNull(appContext.reactContext) { "reactContext is null" }
  private val main = Handler(Looper.getMainLooper())

  override fun definition() = ModuleDefinition {
    Name("RideService")

    Function("startService") {
      context.startForegroundService(Intent(context, RideForegroundService::class.java))
    }

    Function("stopService") {
      context.stopService(Intent(context, RideForegroundService::class.java))
    }

    // JS timers stop while the app is in the background; this one does not (adr/0004).
    AsyncFunction("sleep") { ms: Int, promise: Promise ->
      main.postDelayed({ promise.resolve(null) }, ms.toLong())
    }

    // Opens the nav app with its launcher intent, which resumes the existing task (the route survives).
    AsyncFunction("launchApp") { packageName: String ->
      val intent = context.packageManager.getLaunchIntentForPackage(packageName) ?: return@AsyncFunction false
      intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      try {
        context.startActivity(intent)
        true
      } catch (e: Exception) {
        Log.w(TAG, "failed to launch $packageName", e)
        false
      }
    }.runOnQueue(Queues.MAIN)

    AsyncFunction("listLaunchableApps") {
      val pm = context.packageManager
      val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
      pm.queryIntentActivities(intent, 0)
        .map { mapOf("packageName" to it.activityInfo.packageName, "label" to it.loadLabel(pm).toString()) }
        .distinctBy { it["packageName"] }
        .filter { it["packageName"] != context.packageName }
        .sortedWith(compareBy(Collator.getInstance(Locale.JAPANESE)) { it["label"] ?: "" })
    }

    // Short cues. "call" plays on the voice-call stream (heard on the intercom while SCO is up);
    // "music" plays on the media stream (heard over the intercom's A2DP after returning to the nav app).
    Function("playTone") { name: String, durationMs: Int, stream: String ->
      val tone = when (name) {
        "dial" -> ToneGenerator.TONE_SUP_DIAL
        "ack" -> ToneGenerator.TONE_PROP_ACK
        "beep" -> ToneGenerator.TONE_PROP_BEEP
        else -> ToneGenerator.TONE_SUP_ERROR
      }
      val streamType = if (stream == "call") AudioManager.STREAM_VOICE_CALL else AudioManager.STREAM_MUSIC
      val generator = try {
        ToneGenerator(streamType, VOLUME)
      } catch (e: RuntimeException) {
        Log.w(TAG, "ToneGenerator failed", e)
        return@Function false
      }
      val started = generator.startTone(tone, durationMs)
      main.postDelayed({ generator.release() }, durationMs + 200L)
      started
    }
  }

  private companion object {
    const val TAG = "trv2.ride"
    const val VOLUME = 90
  }
}
```

`modules/ride-service/src/index.ts`:

```ts
import { requireNativeModule } from "expo-modules-core";

export type LaunchableApp = { packageName: string; label: string };
export type ToneName = "dial" | "ack" | "beep" | "error";

declare class RideServiceModule {
  startService(): void;
  stopService(): void;
  sleep(ms: number): Promise<void>;
  launchApp(packageName: string): Promise<boolean>;
  listLaunchableApps(): Promise<LaunchableApp[]>;
  playTone(name: ToneName, durationMs: number, stream: "call" | "music"): boolean;
}

export default requireNativeModule<RideServiceModule>("RideService");
```

- [ ] **Step 2: 型と Kotlin のコンパイルを確かめる**

```bash
cd $APP && npx tsc --noEmit
npx expo prebuild --platform android --no-install > /tmp/trv2-prebuild.log 2>&1 && (cd android && ./gradlew :ride-service:compileDebugKotlin -q)
```
Expected: 型エラーなし。Kotlin のコンパイルが成功する。

- [ ] **Step 3: コミット**

```bash
cd $APP && git add modules/ride-service && git commit -m "feat: add ride-service native module"
```

---

### Task 9: ネイティブモジュール `audio-route`

**Files:**
- Create: `modules/audio-route/expo-module.config.json`、`modules/audio-route/package.json`、`modules/audio-route/android/build.gradle`、`modules/audio-route/android/src/main/AndroidManifest.xml`、`modules/audio-route/android/src/main/java/com/touringproject/v2/audioroute/AudioRouteModule.kt`、`modules/audio-route/src/index.ts`

**Interfaces:**
- Produces: JS の `AudioRoute`（`startVoiceRecognition(timeoutMs): Promise<RouteResult>`・`stopVoiceRecognition(reason): Promise<void>`・`acquireSco(timeoutMs): Promise<RouteResult>`・`releaseSco(): Promise<void>`・イベント `onVoiceRecognitionEnded`）、`RouteResult = { ok: boolean; note: string }`。

背景（コードのコメントにも書く）:
- インカムのボタンは「音声認識を始めて」（AT+BVRA）として届き、端末の返事を約5秒待つ。`BluetoothHeadset.startVoiceRecognition()` で正式に返事をすると、Bluetooth のスタックが SCO（通話の経路）を張る。このとき `setCommunicationDevice()` は呼ばない（外部で張られた SCO を AudioService が覚え、切れたあと仮想通話で張り直してしまうため）。
- 2回目の押下はアプリへの Intent としては届かず、スタックが SCO を切るだけ。SCO が切れたことを「2回目の押下」として JS に知らせる。別の機器の切断は無視する。
- 画面から始めたときは、仮想通話として張る（`setCommunicationDevice()` に SCO の**出力**を渡し、戻り値を必ず見る）。

- [ ] **Step 1: ファイルを書く**

`modules/audio-route/expo-module.config.json`:

```json
{ "platforms": ["android"], "android": { "modules": ["com.touringproject.v2.audioroute.AudioRouteModule"] } }
```

`modules/audio-route/package.json`:

```json
{ "name": "audio-route", "version": "1.0.0", "main": "src/index.ts", "private": true }
```

`modules/audio-route/android/build.gradle`:

```gradle
plugins {
  id 'com.android.library'
  id 'expo-module-gradle-plugin'
}

group = 'com.touringproject.v2.audioroute'
version = '1.0.0'

android {
  namespace "com.touringproject.v2.audioroute"
  defaultConfig {
    versionCode 1
    versionName "1.0.0"
  }
}
```

`modules/audio-route/android/src/main/AndroidManifest.xml`:

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
  <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
  <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />
</manifest>
```

`.../audioroute/AudioRouteModule.kt`:

```kotlin
package com.touringproject.v2.audioroute

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothHeadset
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import expo.modules.kotlin.Promise
import expo.modules.kotlin.functions.Queues
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

// Routes the intercom microphone (Bluetooth SCO).
//
// Intercom button: the headset sends "start voice recognition" (AT+BVRA) and waits about 5 s for the phone.
// We answer with BluetoothHeadset.startVoiceRecognition(), which makes the Bluetooth stack bring up SCO itself.
// setCommunicationDevice() must NOT be called then: AudioService would remember the external SCO and re-open it
// as a virtual call after the headset drops it. The second press reaches us only as SCO going down, so a remote
// SCO loss during a session is reported to JS as onVoiceRecognitionEnded. Another HFP device dropping is ignored.
//
// Screen button: there is no request from the headset, so SCO is opened as a virtual call by naming the SCO
// *output* (sink) in setCommunicationDevice(); the return value is checked because a false is otherwise silent.
@SuppressLint("MissingPermission") // BLUETOOTH_CONNECT is requested at runtime by the app
class AudioRouteModule : Module() {
  private val context: Context
    get() = requireNotNull(appContext.reactContext) { "reactContext is null" }
  private val audioManager: AudioManager
    get() = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
  private val main = Handler(Looper.getMainLooper())

  private var headset: BluetoothHeadset? = null
  private var proxyRequested = false
  private val proxyWaiters = mutableListOf<(BluetoothHeadset?) -> Unit>()
  private var receiver: BroadcastReceiver? = null

  // Voice-recognition session; the counter invalidates callbacks of earlier sessions.
  private var vrDevice: BluetoothDevice? = null
  private var vrSession = 0
  private var vrPending: ((Boolean, String) -> Unit)? = null

  override fun definition() = ModuleDefinition {
    Name("AudioRoute")
    Events("onVoiceRecognitionEnded")

    OnDestroy {
      runCatching {
        vrPending = null
        headset?.let { endSession(it, "module destroyed") }
        audioManager.mode = AudioManager.MODE_NORMAL
      }
      main.removeCallbacksAndMessages(null)
      receiver?.let { runCatching { context.unregisterReceiver(it) } }
      receiver = null
      headset?.let { h ->
        runCatching { context.getSystemService(BluetoothManager::class.java)?.adapter?.closeProfileProxy(BluetoothProfile.HEADSET, h) }
      }
      headset = null
    }

    AsyncFunction("startVoiceRecognition") { timeoutMs: Int, promise: Promise ->
      startVoiceRecognition(timeoutMs) { ok, note -> promise.resolve(mapOf("ok" to ok, "note" to note)) }
    }.runOnQueue(Queues.MAIN)

    AsyncFunction("stopVoiceRecognition") { reason: String ->
      vrPending?.invoke(false, "stopped: $reason")
      headset?.let { endSession(it, reason) }
      audioManager.mode = AudioManager.MODE_NORMAL
    }.runOnQueue(Queues.MAIN)

    AsyncFunction("acquireSco") { timeoutMs: Int, promise: Promise ->
      acquireSco(timeoutMs) { ok, note -> promise.resolve(mapOf("ok" to ok, "note" to note)) }
    }.runOnQueue(Queues.MAIN)

    AsyncFunction("releaseSco") {
      runCatching { audioManager.clearCommunicationDevice() }
      audioManager.mode = AudioManager.MODE_NORMAL
    }.runOnQueue(Queues.MAIN)
  }

  // ---------------- intercom button: voice recognition ----------------

  private fun startVoiceRecognition(timeoutMs: Int, done: (Boolean, String) -> Unit) {
    if (vrPending != null) {
      done(false, "already starting")
      return
    }
    ensureReceiver()
    withHeadset { h ->
      if (h == null) {
        done(false, "no headset proxy")
        return@withHeadset
      }
      val device = pickDevice(h)
      if (device == null) {
        done(false, "no HFP device connected")
        return@withHeadset
      }
      if (vrDevice != null) endSession(h, "superseded")
      waitAudioOff(h, device) { begin(h, device, timeoutMs, done) }
    }
  }

  private fun begin(h: BluetoothHeadset, device: BluetoothDevice, timeoutMs: Int, done: (Boolean, String) -> Unit) {
    val session = ++vrSession
    vrDevice = device
    val onTimeout = Runnable { if (vrSession == session) vrPending?.invoke(false, "SCO timeout") }
    // Wait for SCO by broadcast and by polling, whichever comes first.
    val poll = object : Runnable {
      override fun run() {
        if (vrSession != session || vrPending == null) return
        val d = vrDevice ?: return
        if (runCatching { h.isAudioConnected(d) }.getOrDefault(false)) vrPending?.invoke(true, "connected (poll)")
        else main.postDelayed(this, POLL_MS)
      }
    }
    vrPending = { ok, note ->
      vrPending = null
      main.removeCallbacks(onTimeout)
      main.removeCallbacks(poll)
      if (ok && vrSession == session) {
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        startSessionMonitor(h, session)
      } else if (vrSession == session) {
        endSession(h, "start failed: $note")
      }
      done(ok && vrSession == session, note)
    }
    main.postDelayed(onTimeout, timeoutMs.toLong())
    val accepted = runCatching { h.startVoiceRecognition(device) }
    if (accepted.getOrDefault(false) != true) {
      vrPending?.invoke(false, "startVoiceRecognition returned ${accepted.exceptionOrNull()?.javaClass?.simpleName ?: "false"}")
      return
    }
    main.post(poll)
  }

  private fun startSessionMonitor(h: BluetoothHeadset, session: Int) {
    val monitor = object : Runnable {
      override fun run() {
        if (vrSession != session) return
        val d = vrDevice ?: return
        if (!runCatching { h.isAudioConnected(d) }.getOrDefault(false)) onScoLost(session)
        else main.postDelayed(this, POLL_MS)
      }
    }
    main.postDelayed(monitor, POLL_MS)
  }

  // SCO went down during a session we did not end ourselves: the intercom's second press.
  private fun onScoLost(session: Int) {
    if (vrSession != session || vrDevice == null) return
    vrDevice = null
    vrSession++
    runCatching { audioManager.mode = AudioManager.MODE_NORMAL }
    sendEvent("onVoiceRecognitionEnded", mapOf("reason" to "sco-lost"))
  }

  private fun endSession(h: BluetoothHeadset, reason: String) {
    val device = vrDevice
    vrSession++
    vrDevice = null
    if (device != null) {
      val r = runCatching { h.stopVoiceRecognition(device) }
      Log.i(TAG, "stopVoiceRecognition -> ${r.getOrNull()} ($reason)")
    }
  }

  private fun waitAudioOff(h: BluetoothHeadset, device: BluetoothDevice, then: () -> Unit) {
    val deadline = System.currentTimeMillis() + AUDIO_OFF_WAIT_MS
    val check = object : Runnable {
      override fun run() {
        val on = runCatching { h.isAudioConnected(device) }.getOrDefault(false)
        if (!on || System.currentTimeMillis() >= deadline) then() else main.postDelayed(this, POLL_MS)
      }
    }
    check.run()
  }

  // Prefer the HFP device that is the current SCO sink when several are connected.
  private fun pickDevice(h: BluetoothHeadset): BluetoothDevice? {
    val devices = h.connectedDevices
    val activeAddress = audioManager.availableCommunicationDevices.firstOrNull { it.type == SCO_TYPE }?.address
    return devices.firstOrNull { it.address == activeAddress } ?: devices.firstOrNull()
  }

  private fun withHeadset(block: (BluetoothHeadset?) -> Unit) {
    headset?.let { block(it); return }
    var done = false
    val once: (BluetoothHeadset?) -> Unit = { h -> if (!done) { done = true; block(h) } }
    proxyWaiters.add(once)
    main.postDelayed({ if (!done) { proxyWaiters.remove(once); once(null) } }, PROXY_TIMEOUT_MS)
    if (proxyRequested) return
    proxyRequested = true
    val adapter = context.getSystemService(BluetoothManager::class.java)?.adapter
    val requested = adapter?.getProfileProxy(
      context,
      object : BluetoothProfile.ServiceListener {
        override fun onServiceConnected(profile: Int, proxy: BluetoothProfile) {
          main.post {
            headset = proxy as BluetoothHeadset
            val waiters = proxyWaiters.toList()
            proxyWaiters.clear()
            waiters.forEach { it(headset) }
          }
        }

        override fun onServiceDisconnected(profile: Int) {
          main.post {
            headset = null
            proxyRequested = false
          }
        }
      },
      BluetoothProfile.HEADSET,
    ) ?: false
    if (!requested) proxyRequested = false
  }

  private fun ensureReceiver() {
    if (receiver != null) return
    val r = object : BroadcastReceiver() {
      override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.action != BluetoothHeadset.ACTION_AUDIO_STATE_CHANGED) return
        val state = intent.getIntExtra(BluetoothProfile.EXTRA_STATE, -1)
        val device = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
          intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
        } else {
          @Suppress("DEPRECATION") intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE)
        }
        val current = vrDevice ?: return
        if (state == BluetoothHeadset.STATE_AUDIO_CONNECTED && vrPending != null) {
          if (device != null && device != current) vrDevice = device
          vrPending?.invoke(true, "connected (broadcast)")
        } else if (state == BluetoothHeadset.STATE_AUDIO_DISCONNECTED && vrPending == null) {
          if (device != null && device != current) return // another HFP device, not our second press
          onScoLost(vrSession)
        }
      }
    }
    val filter = IntentFilter(BluetoothHeadset.ACTION_AUDIO_STATE_CHANGED)
    // EXPORTED: the broadcast comes from the Bluetooth app (another uid); it is a protected broadcast.
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      context.registerReceiver(r, filter, Context.RECEIVER_EXPORTED)
    } else {
      context.registerReceiver(r, filter)
    }
    receiver = r
  }

  // ---------------- screen button: virtual call ----------------

  private fun acquireSco(timeoutMs: Int, done: (Boolean, String) -> Unit) {
    val am = audioManager
    am.communicationDevice?.let { if (it.type == SCO_TYPE) { done(true, "already SCO"); return } }
    am.mode = AudioManager.MODE_IN_COMMUNICATION
    val sink = am.availableCommunicationDevices.firstOrNull { it.type == SCO_TYPE }
    if (sink == null) {
      am.mode = AudioManager.MODE_NORMAL
      done(false, "no SCO output")
      return
    }
    var settled = false
    lateinit var listener: AudioManager.OnCommunicationDeviceChangedListener
    lateinit var onTimeout: Runnable
    fun finish(ok: Boolean, note: String) {
      if (settled) return
      settled = true
      main.removeCallbacks(onTimeout)
      runCatching { am.removeOnCommunicationDeviceChangedListener(listener) }
      if (!ok) runCatching { am.clearCommunicationDevice(); am.mode = AudioManager.MODE_NORMAL }
      done(ok, note)
    }
    listener = AudioManager.OnCommunicationDeviceChangedListener { device -> if (device?.type == SCO_TYPE) finish(true, "connected") }
    am.addOnCommunicationDeviceChangedListener({ it.run() }, listener)
    onTimeout = Runnable { finish(false, "SCO timeout") }
    main.postDelayed(onTimeout, timeoutMs.toLong())
    val accepted = runCatching { am.setCommunicationDevice(sink) }.getOrDefault(false)
    if (!accepted) {
      finish(false, "setCommunicationDevice returned false")
      return
    }
    am.communicationDevice?.let { if (it.type == SCO_TYPE) finish(true, "connected (immediate)") }
  }

  private companion object {
    const val TAG = "trv2.route"
    const val SCO_TYPE = AudioDeviceInfo.TYPE_BLUETOOTH_SCO
    const val PROXY_TIMEOUT_MS = 1_500L
    const val POLL_MS = 100L
    const val AUDIO_OFF_WAIT_MS = 1_000L
  }
}
```

`modules/audio-route/src/index.ts`:

```ts
import { NativeModule, requireNativeModule } from "expo-modules-core";

export type RouteResult = { ok: boolean; note: string };

type Events = { onVoiceRecognitionEnded: (event: { reason: string }) => void };

declare class AudioRouteModule extends NativeModule<Events> {
  startVoiceRecognition(timeoutMs: number): Promise<RouteResult>;
  stopVoiceRecognition(reason: string): Promise<void>;
  acquireSco(timeoutMs: number): Promise<RouteResult>;
  releaseSco(): Promise<void>;
}

export default requireNativeModule<AudioRouteModule>("AudioRoute");
```

- [ ] **Step 2: 型と Kotlin のコンパイルを確かめる**

```bash
cd $APP && npx tsc --noEmit
npx expo prebuild --platform android --no-install > /tmp/trv2-prebuild.log 2>&1 && (cd android && ./gradlew :audio-route:compileDebugKotlin -q)
```
Expected: 型エラーなし。コンパイルが成功する。

- [ ] **Step 3: コミット**

```bash
cd $APP && git add modules/audio-route && git commit -m "feat: add audio-route native module for the intercom microphone"
```

---

### Task 10: インカムのボタンの受け取り（`handsfree`）

**Files:**
- Create: `modules/handsfree/expo-module.config.json`、`modules/handsfree/package.json`、`modules/handsfree/android/build.gradle`、`modules/handsfree/android/src/main/AndroidManifest.xml`、`.../handsfree/PressStore.kt`、`.../handsfree/HandsfreePackage.kt`、`.../handsfree/HandsfreeModule.kt`、`modules/handsfree/src/index.ts`、`src/handsfree/press.ts`
- Modify: `plugins/withHandsfree.js`（Task 1 の仮のものを置き換える）
- Test: `src/handsfree/__tests__/press.test.ts`、`src/handsfree/__tests__/plugin.test.ts`

**Interfaces:**
- Produces: JS の `Handsfree`（`takePendingPress(): number | null`・イベント `onPress({ pressedAt })`）、`PressTracker`（`claim(pressedAt, now) => "new" | "duplicate" | "stale"`）、`STALE_PRESS_MS = 60000`。Manifest の MainActivity に `android.intent.action.VOICE_COMMAND` の受け口。

ネイティブの考え方: `HandsfreePackage`（名前が `Package.kt` で終わり、`expo.modules.core.interfaces.Package` を読み込むファイルは自動で登録される）が Activity の `onCreate`・`onNewIntent` を受け、`VOICE_COMMAND` なら押下の時刻を `PressStore` に記録して、Intent を `MAIN` に書き換える（作り直しで二重に扱わないため）。`HandsfreeModule` は記録をイベントで JS に渡し、起動直後の分は `takePendingPress()` で渡す。

- [ ] **Step 1: 失敗するテストを書く**

`src/handsfree/__tests__/press.test.ts`:

```ts
import { PressTracker, STALE_PRESS_MS } from "../press";

test("each press is handled once", () => {
  const t = new PressTracker();
  expect(t.claim(1000, 1500)).toBe("new");
  expect(t.claim(1000, 1600)).toBe("duplicate");
  expect(t.claim(900, 1600)).toBe("duplicate");
  expect(t.claim(2000, 2100)).toBe("new");
});

test("old presses are dropped", () => {
  const t = new PressTracker();
  expect(t.claim(1000, 1000 + STALE_PRESS_MS + 1)).toBe("stale");
  expect(t.claim(1010, 1020)).toBe("new");
});
```

`src/handsfree/__tests__/plugin.test.ts`:

```ts
const withHandsfree = require("../../../plugins/withHandsfree");

test("adds the VOICE_COMMAND intent filter once", () => {
  const manifest = {
    manifest: {
      application: [{ activity: [{ $: { "android:name": ".MainActivity" }, "intent-filter": [] }] }],
    },
  };
  const once = withHandsfree.addVoiceCommandFilter(manifest);
  const twice = withHandsfree.addVoiceCommandFilter(once);
  const filters = twice.manifest.application[0].activity[0]["intent-filter"];
  expect(filters).toHaveLength(1);
  expect(filters[0].action[0].$["android:name"]).toBe("android.intent.action.VOICE_COMMAND");
  expect(filters[0].category[0].$["android:name"]).toBe("android.intent.category.DEFAULT");
});
```

Run: `cd $APP && npx jest src/handsfree`
Expected: `Cannot find module '../press'`、`addVoiceCommandFilter is not a function`

- [ ] **Step 2: JS を実装する**

`src/handsfree/press.ts`:

```ts
// The same press can arrive twice (pending at launch and as an event); a press older than a minute is stale.
export const STALE_PRESS_MS = 60_000;

export class PressTracker {
  private lastHandled = 0;

  claim(pressedAt: number, now: number): "new" | "duplicate" | "stale" {
    if (pressedAt <= this.lastHandled) return "duplicate";
    if (now - pressedAt > STALE_PRESS_MS) return "stale";
    this.lastHandled = pressedAt;
    return "new";
  }
}
```

`plugins/withHandsfree.js`:

```js
// Lets the intercom's assistant button (VOICE_COMMAND) open the app. The press itself is read by the
// handsfree module from the activity lifecycle, so MainActivity does not need to be rewritten.
const { withAndroidManifest, AndroidConfig } = require("@expo/config-plugins");

const VOICE_COMMAND = "android.intent.action.VOICE_COMMAND";

function addVoiceCommandFilter(androidManifest) {
  const activity = AndroidConfig.Manifest.getMainActivityOrThrow(androidManifest);
  activity["intent-filter"] = activity["intent-filter"] || [];
  const present = activity["intent-filter"].some((f) => (f.action || []).some((a) => a.$["android:name"] === VOICE_COMMAND));
  if (!present) {
    activity["intent-filter"].push({
      action: [{ $: { "android:name": VOICE_COMMAND } }],
      category: [{ $: { "android:name": "android.intent.category.DEFAULT" } }],
    });
  }
  return androidManifest;
}

const withHandsfree = (config) =>
  withAndroidManifest(config, (c) => {
    c.modResults = addVoiceCommandFilter(c.modResults);
    return c;
  });

module.exports = withHandsfree;
module.exports.addVoiceCommandFilter = addVoiceCommandFilter;
```

Run: `cd $APP && npx jest src/handsfree`
Expected: 3 passed。

- [ ] **Step 3: ネイティブを書く**

`modules/handsfree/expo-module.config.json`:

```json
{ "platforms": ["android"], "android": { "modules": ["com.touringproject.v2.handsfree.HandsfreeModule"] } }
```

`modules/handsfree/package.json`:

```json
{ "name": "handsfree", "version": "1.0.0", "main": "src/index.ts", "private": true }
```

`modules/handsfree/android/build.gradle`:

```gradle
plugins {
  id 'com.android.library'
  id 'expo-module-gradle-plugin'
}

group = 'com.touringproject.v2.handsfree'
version = '1.0.0'

android {
  namespace "com.touringproject.v2.handsfree"
  defaultConfig {
    versionCode 1
    versionName "1.0.0"
  }
}
```

`modules/handsfree/android/src/main/AndroidManifest.xml`:

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android" />
```

`.../handsfree/PressStore.kt`:

```kotlin
package com.touringproject.v2.handsfree

// Shared between the activity lifecycle listener and the module, which may not exist yet at cold start.
object PressStore {
  @Volatile private var pending: Long? = null
  @Volatile var listener: ((Long) -> Unit)? = null

  fun record(pressedAt: Long) {
    pending = pressedAt
    listener?.invoke(pressedAt)
  }

  fun take(): Long? {
    val value = pending
    pending = null
    return value
  }
}
```

`.../handsfree/HandsfreePackage.kt`:

```kotlin
package com.touringproject.v2.handsfree

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Bundle
import expo.modules.core.interfaces.Package
import expo.modules.core.interfaces.ReactActivityLifecycleListener

// Picked up by Expo autolinking (file name ends with Package.kt and imports Package).
class HandsfreePackage : Package {
  override fun createReactActivityLifecycleListeners(activityContext: Context): List<ReactActivityLifecycleListener> =
    listOf(VoiceCommandListener())
}

class VoiceCommandListener : ReactActivityLifecycleListener {
  override fun onCreate(activity: Activity, savedInstanceState: Bundle?) {
    handle(activity.intent)
  }

  override fun onNewIntent(intent: Intent): Boolean {
    handle(intent)
    return false
  }

  private fun handle(intent: Intent?) {
    if (intent?.action != Intent.ACTION_VOICE_COMMAND) return
    // Rewrite the action so a recreated activity does not count the same press again.
    intent.action = Intent.ACTION_MAIN
    PressStore.record(System.currentTimeMillis())
  }
}
```

`.../handsfree/HandsfreeModule.kt`:

```kotlin
package com.touringproject.v2.handsfree

import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class HandsfreeModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("Handsfree")
    Events("onPress")

    OnCreate {
      PressStore.listener = { pressedAt -> sendEvent("onPress", mapOf("pressedAt" to pressedAt.toDouble())) }
    }

    OnDestroy {
      PressStore.listener = null
    }

    // A press that arrived before JS was listening (cold start from the intercom button).
    Function("takePendingPress") {
      PressStore.take()?.toDouble()
    }
  }
}
```

`modules/handsfree/src/index.ts`:

```ts
import { NativeModule, requireNativeModule } from "expo-modules-core";

type Events = { onPress: (event: { pressedAt: number }) => void };

declare class HandsfreeModule extends NativeModule<Events> {
  takePendingPress(): number | null;
}

export default requireNativeModule<HandsfreeModule>("Handsfree");
```

- [ ] **Step 4: Manifest と Kotlin を確かめる**

```bash
cd $APP && npx tsc --noEmit
npx expo prebuild --platform android --no-install --clean > /tmp/trv2-prebuild.log 2>&1
grep -c "android.intent.action.VOICE_COMMAND" android/app/src/main/AndroidManifest.xml
grep -rn "HandsfreePackage" android/app/build/generated 2>/dev/null | head -1 || true
(cd android && ./gradlew :handsfree:compileDebugKotlin -q)
```
Expected: `1`。コンパイルが成功する（`HandsfreePackage` の登録は Task 15 の通しのビルドで確かめる）。

- [ ] **Step 5: コミット**

```bash
cd $APP && git add modules/handsfree src/handsfree plugins/withHandsfree.js
git commit -m "feat: receive intercom button presses through the activity lifecycle"
```

---

### Task 11: 本物の部品をつなぐ（`runtime.ts`）

**Files:**
- Create: `src/config.ts`、`src/ask/runtime.ts`

**Interfaces:**
- Consumes: Task 2〜10 のすべて
- Produces: `API_BASE_URL: string`、`createRuntimeDeps(options: { settings(): Settings; apiKey(): string | null; onState(state): void }) => { deps: Deps; dispose(): void }`、`requestPermissions() => Promise<void>`。

録音は expo-audio の AudioStream（16kHz・int16）でファイルに書き、`expo-file-system/legacy` の `readAsStringAsync(..., { encoding: "base64" })` で改行なしの base64 にする（Backend issue #6）。直近10件だけ `documentDirectory/recordings/` に残す。

- [ ] **Step 1: 書く**

`src/config.ts`:

```ts
// Set in App/.env (not tracked): EXPO_PUBLIC_API_BASE_URL=https://<id>.execute-api.ap-northeast-1.amazonaws.com/Prod
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "";
```

`src/ask/runtime.ts`:

```ts
// Real implementations of the controller's Deps. Kept thin: the decisions live in controller.ts.
import { createAudioPlayer, requestRecordingPermissionsAsync, setAudioModeAsync } from "expo-audio";
import AudioModule from "expo-audio/build/AudioModule";
import { deleteAsync, documentDirectory, makeDirectoryAsync, readAsStringAsync, readDirectoryAsync } from "expo-file-system/legacy";
import * as Location from "expo-location";
import * as Speech from "expo-speech";
import { PermissionsAndroid } from "react-native";

import AudioRoute from "../../modules/audio-route/src";
import RideService from "../../modules/ride-service/src";
import { ApiClient } from "../api/client";
import { API_BASE_URL } from "../config";
import { Fix } from "../location/heading";
import type { Settings } from "../settings/store";
import { Deps } from "./controller";
import { ConversationState } from "./conversation";
import { FlowState, Source } from "./flow";
import { recordingName, recordingsToDelete } from "./recordings";

const RECORDINGS_DIR = `${documentDirectory}recordings/`;
const VR_TIMEOUT_MS = 4000;
const SCO_TIMEOUT_MS = 3000;

export async function requestPermissions(): Promise<void> {
  await requestRecordingPermissionsAsync();
  await Location.requestForegroundPermissionsAsync();
  await PermissionsAndroid.requestMultiple([
    "android.permission.BLUETOOTH_CONNECT",
    "android.permission.POST_NOTIFICATIONS",
  ] as Parameters<typeof PermissionsAndroid.requestMultiple>[0]);
}

class PcmRecorder {
  private stream: InstanceType<typeof AudioModule.AudioStream> | null = null;

  async start(): Promise<void> {
    await makeDirectoryAsync(RECORDINGS_DIR, { intermediates: true });
    const stream = new AudioModule.AudioStream({ sampleRate: 16000, channels: 1, encoding: "int16" });
    await stream.start();
    await stream.startFileRecordingAsync({ uri: `${RECORDINGS_DIR}${recordingName(Date.now())}`, format: "pcm" });
    this.stream = stream;
  }

  async stop(): Promise<string> {
    const stream = this.stream;
    this.stream = null;
    if (!stream) throw new Error("not recording");
    const file = await stream.stopFileRecordingAsync();
    stream.stop();
    const base64 = await readAsStringAsync(file.uri, { encoding: "base64" });
    await this.prune();
    return base64;
  }

  async cancel(): Promise<void> {
    const stream = this.stream;
    this.stream = null;
    if (!stream) return;
    const file = await stream.stopFileRecordingAsync().catch(() => null);
    stream.stop();
    if (file) await deleteAsync(file.uri, { idempotent: true });
  }

  private async prune(): Promise<void> {
    const names = await readDirectoryAsync(RECORDINGS_DIR);
    await Promise.all(recordingsToDelete(names).map((name) => deleteAsync(`${RECORDINGS_DIR}${name}`, { idempotent: true })));
  }
}

class PositionTracker {
  private fixes: Fix[] = [];
  private subscription: Location.LocationSubscription | null = null;

  begin(): void {
    this.fixes = [];
    void Location.getLastKnownPositionAsync().then((p) => p && this.add(p));
    void Location.watchPositionAsync({ accuracy: Location.Accuracy.High, timeInterval: 1000, distanceInterval: 0 }, (p) => this.add(p))
      .then((s) => { this.subscription = s; })
      .catch(() => undefined);
  }

  end(): { current: Fix | null; fixes: Fix[] } {
    this.subscription?.remove();
    this.subscription = null;
    const fixes = [...this.fixes].sort((a, b) => a.timestamp - b.timestamp);
    return { current: fixes.length > 0 ? fixes[fixes.length - 1] : null, fixes };
  }

  private add(p: Location.LocationObject): void {
    this.fixes.push({ latitude: p.coords.latitude, longitude: p.coords.longitude, timestamp: p.timestamp });
  }
}

function playUrls(urls: string[], stopRef: { stop: (() => void) | null }): Promise<void> {
  return urls.reduce(
    (chain, url) =>
      chain.then(
        () =>
          new Promise<void>((resolve, reject) => {
            const player = createAudioPlayer({ uri: url });
            const finish = (error?: Error) => {
              sub.remove();
              player.remove();
              stopRef.stop = null;
              if (error) reject(error);
              else resolve();
            };
            const sub = player.addListener("playbackStatusUpdate", (status) => {
              if (status.didJustFinish) finish();
            });
            stopRef.stop = () => { player.pause(); finish(); };
            player.play();
          }),
      ),
    Promise.resolve(),
  );
}

export function createRuntimeDeps(options: {
  settings(): Settings;
  apiKey(): string | null;
  onState(state: FlowState): void;
}): { deps: Deps; dispose(): void } {
  void setAudioModeAsync({ shouldPlayInBackground: true, playsInSilentMode: true, interruptionMode: "mixWithOthers" });
  const recorder = new PcmRecorder();
  const positions = new PositionTracker();
  const playback: { stop: (() => void) | null } = { stop: null };
  let routeSource: Source | null = null;

  const deps: Deps = {
    now: () => Date.now(),
    sleep: (ms) => RideService.sleep(ms),
    settings: options.settings,
    apiKey: () => (API_BASE_URL ? options.apiKey() : null),
    api: (apiKey, userName) => new ApiClient({ baseUrl: API_BASE_URL, apiKey, userName, sleep: (ms) => RideService.sleep(ms) }),
    conversation: new ConversationState(),
    route: {
      start: async (source) => {
        routeSource = source;
        const result = source === "handsfree" ? await AudioRoute.startVoiceRecognition(VR_TIMEOUT_MS) : await AudioRoute.acquireSco(SCO_TIMEOUT_MS);
        return result.ok;
      },
      stop: async () => {
        if (routeSource === "handsfree") await AudioRoute.stopVoiceRecognition("done");
        else await AudioRoute.releaseSco();
        routeSource = null;
      },
    },
    recorder,
    location: positions,
    service: { start: () => RideService.startService(), stop: () => RideService.stopService() },
    nav: { returnTo: (packageName) => RideService.launchApp(packageName) },
    cues: {
      start: () => { RideService.playTone("dial", 1000, "call"); },
      sent: () => { RideService.playTone("ack", 200, "music"); },
      waiting: () => { RideService.playTone("beep", 120, "music"); },
      failure: () => { RideService.playTone("error", 600, "music"); },
    },
    player: { play: (urls) => playUrls(urls, playback), stop: () => playback.stop?.() },
    speech: {
      say: (text) =>
        new Promise<void>((resolve) => {
          Speech.speak(text, { language: "ja-JP", onDone: () => resolve(), onStopped: () => resolve(), onError: () => resolve() });
        }),
      stop: () => { void Speech.stop(); },
    },
    onState: options.onState,
    log: (event, data) => { console.log(JSON.stringify({ event, ...data })); },
  };
  return { deps, dispose: () => { positions.end(); playback.stop?.(); } };
}
```

- [ ] **Step 2: 型を確かめる**

Run: `cd $APP && npx tsc --noEmit && npx jest`
Expected: 型エラーなし。テストはすべて PASS。`AudioModule.AudioStream` の型が見つからないなど、expo-audio の内部の型で失敗したら、`node_modules/expo-audio/build/AudioModule.d.ts` の宣言に合わせ、合わない部分は `as unknown as { new (o: object): AudioStreamLike }` の形で局所的に型を付ける（ledger に記録）。

- [ ] **Step 3: コミット**

```bash
cd $APP && git add src/config.ts src/ask/runtime.ts && git commit -m "feat: wire real recorder, location, playback and native modules"
```

---

### Task 12: 対話の画面（SC-03）と状態の配布

**Files:**
- Create: `src/ask/AskProvider.tsx`、`src/ui/AskOverlay.tsx`、`src/ui/colors.ts`
- Test: `src/ui/__tests__/colors.test.ts`

**Interfaces:**
- Consumes: `AskController`（Task 7）、`createRuntimeDeps`・`requestPermissions`（Task 11）、`Handsfree`（Task 10）、`AudioRoute`（Task 9）、設定（Task 2）
- Produces: `AskProvider`、`useAsk() => { state; controller; settings; updateSettings(next); apiKey; setApiKey(key | null); conversationExpiresAt: number | null; ready }`、`AskOverlay`、`phaseColor(phase) => string`。

- [ ] **Step 1: 失敗するテストを書く**

`src/ui/__tests__/colors.test.ts`:

```ts
import { phaseColor } from "../colors";

test("each phase has its own full-screen color", () => {
  expect(phaseColor("recording")).toBe("#d42a2a");
  expect(phaseColor("sending")).toBe("#d42a2a");
  expect(phaseColor("waiting")).toBe("#1f4fd1");
  expect(phaseColor("speaking")).toBe("#13804a");
  expect(phaseColor("failed")).toBe("#5b6170");
});
```

Run: `cd $APP && npx jest src/ui`
Expected: `Cannot find module '../colors'`

- [ ] **Step 2: 実装する**

`src/ui/colors.ts`:

```ts
import type { Phase } from "../ask/flow";

// SC-03: the state must be readable from color alone.
const COLORS: Record<Phase, string> = {
  idle: "#000000",
  recording: "#d42a2a",
  sending: "#d42a2a",
  waiting: "#1f4fd1",
  speaking: "#13804a",
  failed: "#5b6170",
};

export function phaseColor(phase: Phase): string {
  return COLORS[phase];
}
```

`src/ask/AskProvider.tsx`:

```tsx
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import AudioRoute from "../../modules/audio-route/src";
import Handsfree from "../../modules/handsfree/src";
import { PressTracker } from "../handsfree/press";
import { loadApiKey, deleteApiKey, saveApiKey, settingsStore } from "../settings/storage";
import { loadSettings, saveSettings, Settings } from "../settings/store";
import { AskController } from "./controller";
import { FlowState, IDLE } from "./flow";
import { createRuntimeDeps, requestPermissions } from "./runtime";

type AskContext = {
  ready: boolean;
  state: FlowState;
  controller: AskController | null;
  settings: Settings | null;
  updateSettings(next: Settings): Promise<void>;
  apiKey: string | null;
  setApiKey(key: string | null): Promise<void>;
  conversationExpiresAt: number | null;
};

const Context = createContext<AskContext | null>(null);

export function useAsk(): AskContext {
  const value = useContext(Context);
  if (!value) throw new Error("useAsk outside AskProvider");
  return value;
}

export function AskProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<FlowState>(IDLE);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [apiKey, setApiKeyState] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const settingsRef = useRef<Settings | null>(null);
  const keyRef = useRef<string | null>(null);
  const controllerRef = useRef<AskController | null>(null);
  const runtimeRef = useRef<ReturnType<typeof createRuntimeDeps> | null>(null);
  const presses = useRef(new PressTracker());

  const handlePress = useCallback((pressedAt: number) => {
    if (presses.current.claim(pressedAt, Date.now()) === "new") controllerRef.current?.press();
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      await requestPermissions();
      const loaded = await loadSettings(settingsStore);
      const key = await loadApiKey();
      if (!mounted) return;
      settingsRef.current = loaded;
      keyRef.current = key;
      setSettings(loaded);
      setApiKeyState(key);
      const runtime = createRuntimeDeps({
        settings: () => settingsRef.current!,
        apiKey: () => keyRef.current,
        onState: setState,
      });
      runtimeRef.current = runtime;
      controllerRef.current = new AskController(runtime.deps);
      setReady(true);
      const pending = Handsfree.takePendingPress();
      if (pending !== null) handlePress(pending);
    })();
    const pressSub = Handsfree.addListener("onPress", (e) => handlePress(e.pressedAt));
    // The headset dropping SCO during a voice-recognition session is the second press.
    const endSub = AudioRoute.addListener("onVoiceRecognitionEnded", () => controllerRef.current?.stopRecording());
    return () => {
      mounted = false;
      pressSub.remove();
      endSub.remove();
      runtimeRef.current?.dispose();
    };
  }, [handlePress]);

  const updateSettings = useCallback(async (next: Settings) => {
    settingsRef.current = next;
    setSettings(next);
    await saveSettings(settingsStore, next);
  }, []);

  const setApiKey = useCallback(async (key: string | null) => {
    keyRef.current = key;
    setApiKeyState(key);
    if (key) await saveApiKey(key);
    else await deleteApiKey();
  }, []);

  const conversationExpiresAt = runtimeRef.current?.deps.conversation.expiresAt(Date.now()) ?? null;
  const value = useMemo(
    () => ({ ready, state, controller: controllerRef.current, settings, updateSettings, apiKey, setApiKey, conversationExpiresAt }),
    [ready, state, settings, updateSettings, apiKey, setApiKey, conversationExpiresAt],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
```

`src/ui/AskOverlay.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";

import { useAsk } from "../ask/AskProvider";
import { RECORD_LIMIT_MS } from "../ask/controller";
import { spokenMessage } from "../ask/failures";
import { phaseColor } from "./colors";

function useSecondsSince(startedAt: number): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    // Foreground-only display timer; the ask loop itself never relies on JS timers.
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [startedAt]);
  return Math.max(0, Math.floor((now - startedAt) / 1000));
}

export function AskOverlay() {
  const { state, controller } = useAsk();
  const seconds = useSecondsSince(state.phaseStartedAt);
  if (state.phase === "idle" || !controller) return null;

  let title = "";
  let big = "";
  let detail = "";
  let button = "";
  let onMain: () => void = () => undefined;
  switch (state.phase) {
    case "recording":
      title = "話してください";
      big = String(Math.max(0, Math.ceil(RECORD_LIMIT_MS / 1000) - seconds));
      detail = "もう一度ボタンを押すか、ここを押すと送ります";
      button = "送らずにやめる";
      onMain = () => controller.stopRecording();
      break;
    case "sending":
      title = "送っています…";
      button = "送らずにやめる";
      break;
    case "waiting":
      title = "考えています…";
      big = String(seconds);
      detail = "最初の質問は10秒ほど";
      button = "待つのをやめる";
      break;
    case "speaking":
      title = "回答中";
      detail = state.answer ?? "";
      button = "読み上げを止める";
      onMain = () => controller.cancel();
      break;
    case "failed":
      title = state.failure ? spokenMessage(state.failure) : "失敗しました";
      button = "閉じる";
      break;
  }

  return (
    <Modal visible animationType="none" statusBarTranslucent>
      <View style={[styles.root, { backgroundColor: phaseColor(state.phase) }]}>
        {state.phoneMic && state.phase === "recording" ? (
          <Text style={styles.warning}>インカムのマイクに繋がっていません（本体のマイクで録音中）</Text>
        ) : null}
        <Pressable style={styles.main} onPress={onMain}>
          <Text style={styles.title}>{title}</Text>
          {big ? <Text style={styles.big}>{big}</Text> : null}
          {detail ? <Text style={styles.detail} numberOfLines={8}>{detail}</Text> : null}
        </Pressable>
        <Pressable style={styles.button} onPress={() => controller.cancel()}>
          <Text style={styles.buttonText}>{button}</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 24, paddingTop: 48 },
  warning: { backgroundColor: "#f5c518", color: "#000", fontSize: 18, padding: 12, borderRadius: 8, marginBottom: 12 },
  main: { flex: 1, justifyContent: "center", alignItems: "center" },
  title: { color: "#fff", fontSize: 36, fontWeight: "700", textAlign: "center" },
  big: { color: "#fff", fontSize: 140, fontWeight: "800" },
  detail: { color: "#fff", fontSize: 22, textAlign: "center", marginTop: 16 },
  button: { borderColor: "#fff", borderWidth: 4, borderRadius: 16, paddingVertical: 22, alignItems: "center" },
  buttonText: { color: "#fff", fontSize: 26, fontWeight: "700" },
});
```

- [ ] **Step 3: テストと型を通す**

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: すべて PASS。型エラーなし。

- [ ] **Step 4: コミット**

```bash
cd $APP && git add src/ask/AskProvider.tsx src/ui && git commit -m "feat: add full-screen ask overlay and provider"
```

---

### Task 13: ホームと設定の画面

**Files:**
- Modify: `app/_layout.tsx`（置き換える）
- Create: `app/index.tsx`、`app/settings/index.tsx`、`app/settings/connection.tsx`、`app/settings/user.tsx`、`app/settings/return-app.tsx`、`src/ui/conversationLabel.ts`
- Test: `src/ui/__tests__/conversationLabel.test.ts`

**Interfaces:**
- Consumes: `useAsk`（Task 12）、`ApiClient.checkKey`（Task 3）、`RideService.listLaunchableApps`（Task 8）、`USER_NAME_RE`・`withRecentApp`・`maskKey`（Task 2）
- Produces: `conversationLabel(expiresAt: number | null, now: number) => string`。

- [ ] **Step 1: 失敗するテストを書く**

`src/ui/__tests__/conversationLabel.test.ts`:

```ts
import { conversationLabel } from "../conversationLabel";

test("no conversation", () => {
  expect(conversationLabel(null, 0)).toBe("新しい会話です");
});

test("shows when it will be reset in Japan time", () => {
  const expiresAt = Date.parse("2026-10-16T03:15:00Z");
  expect(conversationLabel(expiresAt, expiresAt - 60_000)).toBe("12:15 まで質問がなければ自動で区切ります");
});
```

Run: `cd $APP && npx jest src/ui/__tests__/conversationLabel.test.ts`
Expected: `Cannot find module`

- [ ] **Step 2: 実装する**

`src/ui/conversationLabel.ts`:

```ts
// SC-02: when the current conversation lapses, shown in Japan time.
export function conversationLabel(expiresAt: number | null, now: number): string {
  if (expiresAt === null || expiresAt <= now) return "新しい会話です";
  const jst = new Date(expiresAt + 9 * 60 * 60 * 1000);
  const hh = String(jst.getUTCHours()).padStart(2, "0");
  const mm = String(jst.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm} まで質問がなければ自動で区切ります`;
}
```

`app/_layout.tsx`:

```tsx
import { Stack } from "expo-router";

import { AskProvider } from "../src/ask/AskProvider";
import { AskOverlay } from "../src/ui/AskOverlay";

export default function Layout() {
  return (
    <AskProvider>
      <Stack>
        <Stack.Screen name="index" options={{ title: "Touring V2" }} />
        <Stack.Screen name="settings/index" options={{ title: "設定" }} />
        <Stack.Screen name="settings/connection" options={{ title: "接続の設定" }} />
        <Stack.Screen name="settings/user" options={{ title: "ユーザー名" }} />
        <Stack.Screen name="settings/return-app" options={{ title: "応答後に戻るアプリ" }} />
      </Stack>
      <AskOverlay />
    </AskProvider>
  );
}
```

`app/index.tsx`:

```tsx
import { Link, router } from "expo-router";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { useAsk } from "../src/ask/AskProvider";
import { conversationLabel } from "../src/ui/conversationLabel";

export default function Home() {
  const { ready, controller, settings, apiKey, conversationExpiresAt } = useAsk();
  if (!ready || !settings || !controller) return <View style={styles.root}><Text>準備中…</Text></View>;

  const confirmNewConversation = () =>
    Alert.alert("新しい会話を始めますか？", "次の質問から、これまでの会話を踏まえずに答えます。", [
      { text: "やめる", style: "cancel" },
      { text: "新しい会話にする", onPress: () => controller.resetConversation() },
    ]);

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
      {!apiKey ? (
        <Pressable style={styles.banner} onPress={() => router.push("/settings/connection")}>
          <Text style={styles.bannerText}>接続キーが未設定です（押して設定）</Text>
        </Pressable>
      ) : null}
      {settings.returnEnabled && !settings.returnApp ? (
        <Pressable style={styles.banner} onPress={() => router.push("/settings/return-app")}>
          <Text style={styles.bannerText}>戻り先のアプリが未設定です（押して選ぶ）</Text>
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

`app/settings/index.tsx`:

```tsx
import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { useAsk } from "../../src/ask/AskProvider";
import { maskKey } from "../../src/settings/store";

function Row({ title, value, href }: { title: string; value: string; href: "/settings/connection" | "/settings/user" | "/settings/return-app" }) {
  return (
    <Pressable style={styles.row} onPress={() => router.push(href)}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.value}>{value}</Text>
    </Pressable>
  );
}

export default function SettingsIndex() {
  const { settings, apiKey } = useAsk();
  if (!settings) return null;
  const returnValue = !settings.returnEnabled ? "戻らない" : settings.returnApp?.label ?? "未設定";
  return (
    <View style={styles.root}>
      <Row title="接続の設定" value={apiKey ? maskKey(apiKey) : "未設定"} href="/settings/connection" />
      <Row title="ユーザー名" value={settings.userName} href="/settings/user" />
      <Row title="応答後に戻るアプリ" value={returnValue} href="/settings/return-app" />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 16, gap: 8 },
  row: { padding: 18, borderRadius: 12, borderWidth: 1, borderColor: "#ccc", flexDirection: "row", justifyContent: "space-between" },
  title: { fontSize: 18 },
  value: { fontSize: 18, color: "#666" },
});
```

`app/settings/connection.tsx`:

```tsx
import { useState } from "react";
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiClient, ApiError } from "../../src/api/client";
import { useAsk } from "../../src/ask/AskProvider";
import { API_BASE_URL } from "../../src/config";
import { maskKey } from "../../src/settings/store";

export default function Connection() {
  const { apiKey, setApiKey, settings } = useAsk();
  const [input, setInput] = useState("");
  const [checking, setChecking] = useState(false);

  const save = async () => {
    const key = input.trim();
    if (!key || !settings) return;
    setChecking(true);
    try {
      await new ApiClient({ baseUrl: API_BASE_URL, apiKey: key, userName: settings.userName }).checkKey();
      await setApiKey(key);
      setInput("");
      Alert.alert("保存しました");
    } catch (error) {
      const kind = error instanceof ApiError ? error.kind : "network";
      Alert.alert(kind === "invalid_key" ? "キーが正しくありません" : "サーバーに繋がりません", "元のキーのままです。");
    } finally {
      setChecking(false);
    }
  };

  const remove = () =>
    Alert.alert("接続キーを削除しますか？", "", [
      { text: "やめる", style: "cancel" },
      { text: "削除する", style: "destructive", onPress: () => void setApiKey(null) },
    ]);

  return (
    <View style={styles.root}>
      <Text style={styles.label}>接続キー</Text>
      <Text style={styles.current}>{apiKey ? maskKey(apiKey) : "未設定"}</Text>
      <Text style={styles.note}>身内で共通のキーを使ってかまいません。記録はユーザー名で分かれます。</Text>
      <TextInput style={styles.input} value={input} onChangeText={setInput} placeholder="キーを貼り付け" autoCapitalize="none" autoCorrect={false} />
      <Pressable style={styles.button} onPress={save} disabled={checking}>
        <Text style={styles.buttonText}>{checking ? "確かめています…" : "確かめて保存"}</Text>
      </Pressable>
      {apiKey ? (
        <Pressable style={styles.danger} onPress={remove}>
          <Text style={styles.buttonText}>キーを削除</Text>
        </Pressable>
      ) : null}
      {!API_BASE_URL ? <Text style={styles.warn}>API の URL が設定されていません（.env の EXPO_PUBLIC_API_BASE_URL）</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 16, gap: 12 },
  label: { fontSize: 16, color: "#666" },
  current: { fontSize: 20, fontFamily: "monospace" },
  note: { fontSize: 14, color: "#666" },
  input: { borderWidth: 1, borderColor: "#999", borderRadius: 8, padding: 12, fontSize: 16 },
  button: { backgroundColor: "#1f4fd1", padding: 16, borderRadius: 12, alignItems: "center" },
  danger: { backgroundColor: "#d42a2a", padding: 16, borderRadius: 12, alignItems: "center" },
  buttonText: { color: "#fff", fontSize: 18, fontWeight: "700" },
  warn: { color: "#d42a2a" },
});
```

`app/settings/user.tsx`:

```tsx
import { useState } from "react";
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { useAsk } from "../../src/ask/AskProvider";
import { USER_NAME_RE } from "../../src/settings/store";

export default function User() {
  const { settings, updateSettings } = useAsk();
  const [input, setInput] = useState("");
  if (!settings) return null;

  const change = () => {
    const name = input.trim();
    if (!USER_NAME_RE.test(name)) {
      Alert.alert("英小文字と数字の3〜20文字にしてください");
      return;
    }
    Alert.alert(
      `「${name}」に変えますか？`,
      "今の記録は引き継ぎません。元の名前に戻せば、また見られます。同じ名前の記録が既にあれば、その記録に切り替わります。",
      [
        { text: "やめる", style: "cancel" },
        { text: "変える", onPress: () => { void updateSettings({ ...settings, userName: name }); setInput(""); } },
      ],
    );
  };

  return (
    <View style={styles.root}>
      <Text style={styles.label}>今のユーザー名</Text>
      <Text style={styles.name}>{settings.userName}</Text>
      <Text style={styles.note}>別の端末に記録を引き継ぐときに使います。控えておいてください。</Text>
      <TextInput style={styles.input} value={input} onChangeText={setInput} placeholder="新しいユーザー名" autoCapitalize="none" autoCorrect={false} />
      <Pressable style={styles.button} onPress={change}>
        <Text style={styles.buttonText}>変更する</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 16, gap: 12 },
  label: { fontSize: 16, color: "#666" },
  name: { fontSize: 32, fontFamily: "monospace", fontWeight: "700" },
  note: { fontSize: 14, color: "#666" },
  input: { borderWidth: 1, borderColor: "#999", borderRadius: 8, padding: 12, fontSize: 16 },
  button: { backgroundColor: "#1f4fd1", padding: 16, borderRadius: 12, alignItems: "center" },
  buttonText: { color: "#fff", fontSize: 18, fontWeight: "700" },
});
```

`app/settings/return-app.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Switch, Text, TextInput, View } from "react-native";

import RideService, { LaunchableApp } from "../../modules/ride-service/src";
import { useAsk } from "../../src/ask/AskProvider";
import { ReturnTiming, withRecentApp } from "../../src/settings/store";

const TIMINGS: { value: ReturnTiming; label: string }[] = [
  { value: "sent", label: "送ったらすぐ" },
  { value: "answered", label: "回答が届いたら" },
  { value: "spoken", label: "読み上げが終わったら" },
];

export default function ReturnApp() {
  const { settings, updateSettings } = useAsk();
  const [apps, setApps] = useState<LaunchableApp[]>([]);
  const [filter, setFilter] = useState("");
  useEffect(() => { void RideService.listLaunchableApps().then(setApps); }, []);
  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? apps.filter((a) => a.label.toLowerCase().includes(q) || a.packageName.toLowerCase().includes(q)) : apps;
  }, [apps, filter]);
  if (!settings) return null;

  const choose = (app: LaunchableApp) => void updateSettings({ ...settings, returnApp: app, recentApps: withRecentApp(settings.recentApps, app) });
  const forget = (app: LaunchableApp) => void updateSettings({ ...settings, recentApps: settings.recentApps.filter((a) => a.packageName !== app.packageName) });

  return (
    <View style={styles.root}>
      <View style={styles.switchRow}>
        <Text style={styles.title}>応答後にアプリへ戻る</Text>
        <Switch value={settings.returnEnabled} onValueChange={(v) => void updateSettings({ ...settings, returnEnabled: v })} />
      </View>
      <Text style={styles.note}>戻るのはインカムのボタンで始めた応答だけです（画面から質問したときは戻りません）。</Text>
      {settings.returnEnabled ? (
        <>
          <View style={styles.timings}>
            {TIMINGS.map((t) => (
              <Pressable key={t.value} style={[styles.timing, settings.returnTiming === t.value && styles.timingOn]} onPress={() => void updateSettings({ ...settings, returnTiming: t.value })}>
                <Text style={settings.returnTiming === t.value ? styles.timingTextOn : styles.timingText}>{t.label}</Text>
              </Pressable>
            ))}
          </View>
          <Text style={styles.current}>現在の戻り先: {settings.returnApp?.label ?? "未設定"}</Text>
          {settings.recentApps.map((app) => (
            <View key={app.packageName} style={styles.recent}>
              <Pressable style={styles.recentMain} onPress={() => choose(app)}><Text style={styles.appLabel}>{app.label}</Text></Pressable>
              <Pressable onPress={() => forget(app)}><Text style={styles.forget}>✕</Text></Pressable>
            </View>
          ))}
          <TextInput style={styles.input} value={filter} onChangeText={setFilter} placeholder="アプリを絞り込む" autoCapitalize="none" />
          <FlatList
            data={filtered}
            keyExtractor={(a) => a.packageName}
            renderItem={({ item }) => (
              <Pressable style={styles.app} onPress={() => choose(item)}>
                <Text style={styles.appLabel}>{item.label}</Text>
                <Text style={styles.appPackage}>{item.packageName}</Text>
              </Pressable>
            )}
          />
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 16, gap: 10 },
  switchRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { fontSize: 18 },
  note: { fontSize: 13, color: "#666" },
  timings: { flexDirection: "row", gap: 6 },
  timing: { flex: 1, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: "#1f4fd1", alignItems: "center" },
  timingOn: { backgroundColor: "#1f4fd1" },
  timingText: { color: "#1f4fd1", fontSize: 13 },
  timingTextOn: { color: "#fff", fontSize: 13 },
  current: { fontSize: 18, fontWeight: "700" },
  recent: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: "#ddd", borderRadius: 8 },
  recentMain: { flex: 1, padding: 12 },
  forget: { fontSize: 18, padding: 12 },
  input: { borderWidth: 1, borderColor: "#999", borderRadius: 8, padding: 10, fontSize: 16 },
  app: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: "#eee" },
  appLabel: { fontSize: 16 },
  appPackage: { fontSize: 12, color: "#888" },
});
```

- [ ] **Step 3: テストと型を通す**

Run: `cd $APP && npx jest && npx tsc --noEmit`
Expected: すべて PASS。型エラーなし。

- [ ] **Step 4: コミット**

```bash
cd $APP && git add app src/ui/conversationLabel.ts src/ui/__tests__/conversationLabel.test.ts
git commit -m "feat: add home and settings screens"
```

---

### Task 14: Backend の時計のずれ（issue #9）

**Files（`Backend/`）:**
- Modify: `src/lib/geo.py`、`tests/test_geo.py`

**Interfaces:**
- Produces: `MAX_FUTURE_SKEW_SECONDS = 30`。方位の材料の時刻が受け付けた時刻より30秒以内の未来なら許す。

- [ ] **Step 1: 失敗するテストを書く**

`cd $BE && git switch -c slice1-plan4a` で作業ブランチを切り、`tests/test_geo.py` の

```python
@pytest.mark.parametrize("seconds_ago", [geo.MAX_SAMPLE_AGE_SECONDS + 1, -5])
def test_heading_none_when_sample_is_stale_or_in_future(seconds_ago):
```

を

```python
@pytest.mark.parametrize("seconds_ago", [geo.MAX_SAMPLE_AGE_SECONDS + 1, -(geo.MAX_FUTURE_SKEW_SECONDS + 10)])
def test_heading_none_when_sample_is_stale_or_in_future(seconds_ago):
```

に置き換え、末尾に足す:

```python


def test_small_device_clock_skew_is_tolerated():
    assert geo.heading_degrees(HERE, sample(SOUTH_60M, -5), NOW) == pytest.approx(0, abs=0.5)
```

Run: `cd $BE && env/bin/pytest tests/test_geo.py -q`
Expected: `AttributeError: module 'lib.geo' has no attribute 'MAX_FUTURE_SKEW_SECONDS'`

- [ ] **Step 2: 実装する**

`src/lib/geo.py` の `MAX_SAMPLE_AGE_SECONDS = 120 ...` の行の下に足す:

```python
MAX_FUTURE_SKEW_SECONDS = 30  # the sample time comes from the phone's clock, which may run a little ahead
```

`heading_degrees` の `if age < 0 or age > MAX_SAMPLE_AGE_SECONDS:` を `if age < -MAX_FUTURE_SKEW_SECONDS or age > MAX_SAMPLE_AGE_SECONDS:` に置き換える。

- [ ] **Step 3: テストを通してデプロイする**

```bash
cd $BE && env/bin/pytest -q
AWS_PROFILE=touring sam build >/dev/null && AWS_PROFILE=touring sam deploy 2>&1 | grep -E "Successfully|Error"
AWS_PROFILE=touring env/bin/python scripts/smoke.py | tail -1
```
Expected: すべて PASS、`Successfully created/updated stack`、`11/11 passed`。

- [ ] **Step 4: コミット**

```bash
cd $BE && git add src/lib/geo.py tests/test_geo.py && git commit -m "fix: tolerate a little device clock skew in heading samples"
```

---

### Task 15: 実機での通しの確認

**Files:**
- Create: `App/.env`（追跡しない）

**Interfaces:**
- Consumes: すべて。

**前提:** 利用者の Android 端末（Android 12 以降）を USB でつなぎ、インカムをペアリングし、Google マップなどのナビを入れておく。

- [ ] **Step 1: `.env` を作り、ビルドして入れる**

```bash
cd $APP
URL=$(AWS_PROFILE=touring aws cloudformation describe-stacks --region ap-northeast-1 --stack-name stack-trv2-dev-backend --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
printf 'EXPO_PUBLIC_API_BASE_URL=%s\n' "$URL" > .env
git status --short | grep -c "\.env" || true
npx expo prebuild --platform android --clean > /tmp/trv2-prebuild.log 2>&1
npx expo run:android --device
```
Expected: `.env` は追跡されない（`0`）。アプリが端末に入り、起動して権限の確認が出る。ビルドが失敗したら、エラーを調べてから直す。

- [ ] **Step 2: 【利用者の作業】初期の設定**

1. 権限（マイク・位置・近くのデバイス・通知）をすべて許可する
2. 設定 → 接続の設定 → 接続キーを貼り付けて「確かめて保存」（キーは Backend の README の手順で読む。私が読んで、チャットには出さずに伝える方法を相談する）
3. 設定 → 応答後に戻るアプリ → ナビのアプリを選ぶ（戻るタイミングは「送ったらすぐ」）

- [ ] **Step 3: 【利用者の作業】確認リスト**

停車した状態で、マップでナビを始めてから行う。結果を ✓/✗ で教えてもらう。

| # | 操作 | 期待 |
|---|---|---|
| 1 | アプリを閉じた状態でインカムのボタンを押す | アプリが開き、赤い画面と開始の合図。インカムのマイクで録れている（黄色の警告が出ない） |
| 2 | 「右手に見える山は何？」と話し、もう一度ボタンを押す | 送った合図が鳴り、すぐマップに戻る |
| 3 | そのまま待つ（画面を消してもよい） | 数秒ごとに待っている合図。回答がインカムから聞こえる |
| 4 | 続けてボタンを押し「さっきの質問をもう一度短く」 | 前の話を踏まえて答える |
| 5 | 回答を待っているあいだにボタンを押す | 「いま応答中です…」と聞こえ、録音は始まらない |
| 6 | アプリのホームで「🎤 押して話す」→ 話す → 赤い画面を押す | 青 → 緑の画面で回答。マップには戻らない |
| 7 | 録音中に「送らずにやめる」 | ホームに戻り、何も送られない |
| 8 | 機内モードでボタンを押して話す | 失敗の合図と「通信できないため、質問できませんでした。」、マップに戻る |
| 9 | ホームで「新しい会話を始める」→ 確認 → 次の質問 | 前の話を踏まえない |

✗ があれば、`adb logcat -s trv2.route trv2.ride ReactNativeJS` の出力と合わせて原因を調べる。

- [ ] **Step 4: 記録する**

結果の表を ledger に残す（コミットはしない）。

---

### Task 16: 文書

**Files:**
- Modify: `App/README.md`
- Modify（親）: `docs/specs/2026-10-16-slice1-design.md`（§11 に 計画4a/4b を書く）、submodule の指す先（`App`・`Backend`）、各ユニットの `docs-parent/`

- [ ] **Step 1: `App/README.md` を書き直す**

````markdown
# TouringProjectV2_App

TouringProjectV2 の Android アプリ（Expo SDK 58・Development Build・expo-router）。
インカムのボタンで質問を始め、回答を背面で待って読み上げ、ナビのアプリへ戻る。
プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し。編集しない）。

## 構成

| 場所 | 中身 |
|---|---|
| `app/` | 画面（ホーム・設定・接続・ユーザー名・応答後に戻るアプリ） |
| `src/ask/` | 一巡の状態機械（`flow.ts`）・司令塔（`controller.ts`）・本物の部品（`runtime.ts`）・ポーリング・会話 |
| `src/api/` | Backend の API（`Backend/openapi.yaml`） |
| `modules/handsfree/` | インカムのボタンの合図（`VOICE_COMMAND`）を Activity のライフサイクルから受ける |
| `modules/audio-route/` | インカムのマイクへの経路（音声認識として・仮想通話として）と、2回目の押下の検出 |
| `modules/ride-service/` | フォアグラウンドサービス・ネイティブで待つ `sleep`・ナビを開く・合図の音 |
| `plugins/withHandsfree.js` | Manifest に `VOICE_COMMAND` の受け口を足す |

## 大事な決まり

- 背面で待つ処理に `setTimeout` を使わない（React Native が背面で止める）。`RideService.sleep` を使う。
- 一巡のあいだはフォアグラウンドサービスを動かす（無いと、画面を消したあと通信と再生が止まる）。
- 音声は `playsInSilentMode` を指定して鳴らす（指定しないと、マナーモードで再生が黙って無視される）。

## テスト

```sh
npm ci && npx jest && npx tsc --noEmit
```

## 実機で動かす

`.env`（追跡しない）に API の URL を書く。

```sh
URL=$(AWS_PROFILE=touring aws cloudformation describe-stacks --region ap-northeast-1 --stack-name stack-trv2-dev-backend \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
printf 'EXPO_PUBLIC_API_BASE_URL=%s\n' "$URL" > .env
npx expo prebuild --platform android --clean
npx expo run:android --device
```

接続キーは、アプリの「設定 → 接続の設定」で入れる（Backend の README の手順で読む）。
````

```bash
cd $APP && git add README.md && git commit -m "docs: describe app structure and how to run it"
```

- [ ] **Step 2: 親で仕様書 §11 を直し、写して submodule を進める**

```bash
cd $ROOT && git switch -c slice1-plan4a
```

`docs/specs/2026-10-16-slice1-design.md` の
旧: `5. Agent → Backend → App の順に作る`
新: `5. Agent → Backend → App の順に作る。App は、ハンズフリーの一巡（計画4a）と、残りの画面の仕上げ（計画4b）に分ける`

```bash
python3 scripts/check_links.py docs adr README.md
git diff --exit-code HEAD -- docs/init && echo "docs/init unchanged"
scripts/sync-docs.sh App Backend Agent CICD
for u in Agent CICD; do git -C "$u" add docs-parent && git -C "$u" commit -m "docs: sync parent docs" || true; done
for u in App Backend; do git -C "$u" add docs-parent && git -C "$u" commit -m "docs: sync parent docs" || true; done
git add docs/plans/2026-10-16-slice1-plan4a-app-handsfree.md docs/specs/2026-10-16-slice1-design.md Agent App Backend CICD
git commit -m "docs: split the app plan and record plan 4a"
```
Expected: リンクの切れ 0件、`docs/init unchanged`。push はしない。
