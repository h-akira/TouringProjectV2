# スライス1 計画1: 土台とスパイク 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 親リポジトリの現行版の文書・ADR・写しの仕組み・5つのリポジトリを用意し、スパイク A（ストリーミングの文字起こし）と B（背面での待ち受けと再生）で、スライス1の2つの大きな不確定要素に答えを出す。

**Architecture:** 親リポジトリ（このディレクトリ）が文書と決定を持ち、ユニット（App・Backend・Agent・CICD）は親の中に置いた別の git リポジトリにする（submodule の登録は初回の push の許可後）。スパイクのコードはすべて `tmp/spikes/`（追跡しない）に置く使い捨てで、結果だけを ADR と仕様書に残す。

**Tech Stack:** Python 3.13（標準ライブラリ・`amazon-transcribe`）、bash・rsync、AWS SAM、Expo SDK 58（expo-audio 58）、Kotlin（Expo Modules）、`gh` CLI。

**Spec:** [docs/specs/2026-10-16-slice1-design.md](../specs/2026-10-16-slice1-design.md)

この計画のあと、スパイクの結果を踏まえて 計画2（Agent）→ 計画3（Backend）→ 計画4（App）を書く。

## Global Constraints

- `docs/init/` は一切変えない（凍結した初期スナップショット）。各タスクの最後に `git diff --exit-code HEAD -- docs/init` が通ること。
- 文書（`docs/`・`adr/`・README）は日本語。ソースコードのコメントとコミットメッセージは英語。コミットは Conventional Commits。
- 文書に、このプロジェクトより前の版への言及・リンク・示唆を書かない。
- `git add .`・`git add -A` は使わない。ファイルを個別に指定する。
- `git push` はしない。GitHub のリポジトリは作るだけ（`gh repo create`）。
- AWS のプロファイルは `touring`。使えないときは利用者に頼む。リソース名は `<type>-trv2-dev-<id>`、スタック名は `stack-trv2-dev-<id>`。同じアカウントの既存のリソースと名前を衝突させない。
- AWS のリソースや GitHub のリポジトリを消す前は、利用者に確認する。
- コミットする文書に、AWS のアカウント ID・API キー・実際の位置（地名・座標）を書かない。
- Python で外部ライブラリを使うときは、使う場所に `python -m venv env` で仮想環境を作る（既にあればそれを使う）。
- コマンドは、絶対パスで `cd` してから実行する。以下 `ROOT=<このリポジトリを置いた絶対パス>`。

## Review Focus

- `docs/init/` のファイルが1バイトでも変わる → 変えてはならない。Task 2・Task 3 の確認手順で `git diff --exit-code HEAD -- docs/init` を必ず通す。
- Mermaid のコードブロックの中の `["..."]` や、インラインコードの中の `[x](y)` → リンクとして検査してはならない（誤検出で検査が使えなくなる）。Task 1 のテスト `test_ignores_links_in_code`。
- 日本語やスペースを URL エンコードしたファイル名へのリンク → 実在すれば通す。Task 1 のテスト `test_percent_encoded_target`。
- 写しのスクリプトに、ユニットの `docs-parent/` の外のファイルが巻き込まれる → 消えても上書きされてもならない。Task 3 のテスト「外のファイルが残る」。
- スパイクの結果の文書に、アカウント ID や実際の位置が混ざる → 混ぜない。Task 9 の確認手順で grep する。

---

## ファイル構成（この計画で作るもの）

| パス | 役割 | 追跡 |
|---|---|---|
| `scripts/check_links.py` | Markdown の相対リンクの切れを検査する | 親 |
| `tests/test_check_links.py` | 上のテスト（unittest） | 親 |
| `scripts/sync-docs.sh` | 親の `docs/` をユニットの `docs-parent/` に写す | 親 |
| `tests/test_sync_docs.sh` | 上のテスト（bash） | 親 |
| `README.md` | 親の入口 | 親 |
| `docs/README.md`・`docs/01_…`〜`docs/07_…`・`docs/mock/index.html` | 現行版の文書 | 親 |
| `adr/README.md`・`adr/0001-…`〜`adr/0004-…` | 決定の記録 | 親 |
| `App/`・`Backend/`・`Agent/`・`CICD/` | 各ユニットのリポジトリ（README・.gitignore・docs-parent） | 各ユニット |
| `tmp/spikes/stt/` | スパイク A の計測スクリプトと見本の音声 | 追跡しない |
| `tmp/spikes/stt-lambda/` | スパイク A の Lambda 版 | 追跡しない |
| `tmp/spikes/spike-app/` | スパイク A（実機の録音）と B の Android アプリ | 追跡しない |

---

### Task 1: Markdown のリンク検査

**Files:**
- Create: `scripts/check_links.py`
- Test: `tests/test_check_links.py`

**Interfaces:**
- Produces: `python3 scripts/check_links.py [path ...]` — 引数のディレクトリ以下（既定は `.`）の `*.md` の相対リンクを検査し、切れていれば1件ずつ `<file>:<line>: broken link -> <target>` を出して終了コード1。`node_modules`・`tmp`・`.git`・`docs-parent` は対象外。関数 `iter_links(text: str) -> list[tuple[int, str]]`、`check_file(path: Path) -> list[str]`、`main(argv: list[str]) -> int`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_check_links.py`:

```python
"""Tests for scripts/check_links.py."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_links  # noqa: E402


class CheckLinksTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "exists.md").write_text("# ok\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, name: str, body: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_valid_relative_link(self) -> None:
        path = self.write("a.md", "[x](exists.md)\n")
        self.assertEqual(check_links.check_file(path), [])

    def test_broken_link_is_reported_with_line(self) -> None:
        path = self.write("a.md", "line1\n[x](missing.md)\n")
        errors = check_links.check_file(path)
        self.assertEqual(len(errors), 1)
        self.assertIn(":2: broken link -> missing.md", errors[0])

    def test_external_and_anchor_links_are_ignored(self) -> None:
        path = self.write("a.md", "[a](https://example.com) [b](#top) [c](mailto:x@example.com)\n")
        self.assertEqual(check_links.check_file(path), [])

    def test_anchor_on_existing_file_is_ok(self) -> None:
        path = self.write("a.md", "[x](exists.md#section)\n")
        self.assertEqual(check_links.check_file(path), [])

    def test_ignores_links_in_code(self) -> None:
        body = "```mermaid\nA[\"x\"](missing.md)\n```\n`[y](missing2.md)`\n"
        path = self.write("a.md", body)
        self.assertEqual(check_links.check_file(path), [])

    def test_nested_fences_stay_code_until_matching_close(self) -> None:
        body = "````markdown\n```sh\n[x](missing.md)\n```\n[y](missing2.md)\n````\n[z](exists.md)\n"
        path = self.write("a.md", body)
        self.assertEqual(check_links.check_file(path), [])

    def test_directory_link_is_ok(self) -> None:
        (self.root / "sub").mkdir()
        path = self.write("a.md", "[d](sub/)\n")
        self.assertEqual(check_links.check_file(path), [])

    def test_percent_encoded_target(self) -> None:
        (self.root / "日本 語.md").write_text("x\n", encoding="utf-8")
        path = self.write("a.md", "[j](%E6%97%A5%E6%9C%AC%20%E8%AA%9E.md)\n")
        self.assertEqual(check_links.check_file(path), [])

    def test_main_returns_1_on_broken_and_skips_excluded_dirs(self) -> None:
        self.write("tmp/skip.md", "[x](missing.md)\n")
        self.write("u/docs-parent/skip.md", "[x](missing.md)\n")
        self.assertEqual(check_links.main(["check_links.py", str(self.root)]), 0)
        self.write("bad.md", "[x](missing.md)\n")
        self.assertEqual(check_links.main(["check_links.py", str(self.root)]), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $ROOT && python3 -m unittest tests/test_check_links.py -v`
Expected: `ModuleNotFoundError: No module named 'check_links'`

- [ ] **Step 3: 実装する**

`scripts/check_links.py`:

```python
#!/usr/bin/env python3
"""Check that relative links in Markdown files point to existing files or directories."""
from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
EXCLUDED_DIRS = {"node_modules", "tmp", ".git", "docs-parent"}


def iter_links(text: str) -> list[tuple[int, str]]:
    """Return (line number, target) for every Markdown link outside code."""
    links: list[tuple[int, str]] = []
    fence: str | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and line.strip() == marker:
                fence = None
            continue
        if fence is not None:
            continue
        for match in LINK_RE.finditer(INLINE_CODE_RE.sub("", line)):
            links.append((lineno, match.group(1)))
    return links


def _is_external(target: str) -> bool:
    return bool(SCHEME_RE.match(target)) or target.startswith("#")


def check_file(path: Path) -> list[str]:
    """Return one error string per broken relative link in the file."""
    errors: list[str] = []
    for lineno, target in iter_links(path.read_text(encoding="utf-8")):
        if _is_external(target):
            continue
        file_part = target.split("#", 1)[0]
        if not file_part:
            continue
        resolved = (path.parent / urllib.parse.unquote(file_part)).resolve()
        if not resolved.exists():
            errors.append(f"{path}:{lineno}: broken link -> {target}")
    return errors


def _collect(roots: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in roots:
        candidates = [root] if root.is_file() else root.rglob("*.md")
        for path in candidates:
            relative_parts = path.relative_to(root).parts if root.is_dir() else ()
            if any(part in EXCLUDED_DIRS for part in relative_parts):
                continue
            files.add(path)
    return sorted(files)


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv[1:]] or [Path(".")]
    files = _collect(roots)
    errors = [error for path in files for error in check_file(path)]
    for error in errors:
        print(error)
    print(f"checked {len(files)} files, {len(errors)} broken links")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `cd $ROOT && python3 -m unittest tests/test_check_links.py -v`
Expected: 9 tests, `OK`

- [ ] **Step 5: 今ある文書に使ってみる**

Run: `cd $ROOT && python3 scripts/check_links.py docs`
Expected: `adr` がまだ無いので、仕様書の `../../adr/` が切れとして1件出て終了コード1（Task 2 で直る）。それ以外の切れが出たら、その原因を調べてから進む。

- [ ] **Step 6: コミット**

```bash
cd $ROOT
chmod +x scripts/check_links.py
git add scripts/check_links.py tests/test_check_links.py
git commit -m "chore: add markdown link checker"
```

---

### Task 2: 現行版の文書・ADR・親の README

仕様書 §9 の変更を、`docs/init/` の写しに反映する。あわせて、計画の調査で分かった「expo-audio は Ogg/Opus で録れない」を仕様書に書き足す。

**Files:**
- Create: `docs/README.md`, `docs/01_requirements.md`〜`docs/07_units_contracts.md`, `docs/mock/index.html`（`docs/init/` からの写しを直す）
- Create: `adr/README.md`, `adr/0001-response-time-target.md`, `adr/0002-streaming-transcription.md`, `adr/0003-conversation-context.md`
- Create: `README.md`
- Modify: `docs/specs/2026-10-16-slice1-design.md`（§5.4）

**Interfaces:**
- Consumes: Task 1 の `scripts/check_links.py`
- Produces: `docs/` の現行版（Task 3 の写しの元）、`adr/0002`（Task 9 で結果を追記する）

- [ ] **Step 1: 初期検討を写す**

```bash
cd $ROOT
cp docs/init/0*.md docs/
mkdir -p docs/mock && cp docs/init/mock/index.html docs/mock/index.html
```

- [ ] **Step 2: `docs/README.md` を書く**

```markdown
# docs

TouringProjectV2 の要件定義と基本設計の現行版。

## 位置づけ

- ここにあるのが、いまの正。変えるときはここを直し、なぜ変えたかを [adr/](../adr/README.md) に書く。
- [init/](init/README.md) は初期検討のスナップショットで、編集しない。最初からどう変わったかは、ここと比べれば分かる。
- スライスごとの設計は [specs/](specs/)、実装計画は [plans/](plans/) に置く。

## 概要

バイクでツーリング中のライダーが、インカムのボタンと声だけで AI に質問できる Android アプリ。
AI は現在地と進行方向を踏まえて答え、質問と回答は走ったルートとともに記録に残り、あとで地図で振り返れる。

## 目次

| 文書 | 中身 |
|---|---|
| [01_requirements.md](01_requirements.md) | 要件定義（利用者・ユーザーストーリー・機能／非機能要件・やらないこと・未確定事項） |
| [02_screen_list.md](02_screen_list.md) | 画面一覧 |
| [03_screen_transition.md](03_screen_transition.md) | 画面遷移図 |
| [04_detailed_requirements.md](04_detailed_requirements.md) | 詳細要件（`US-A-01.001` 形式の、判定できる条件） |
| [05_technical_policies.md](05_technical_policies.md) | 技術方針（全体構成・各レイヤーの方針・技術選定） |
| [06_units_definition.md](06_units_definition.md) | ユニットの定義（App・Backend・Agent・CICD の責務） |
| [07_units_contracts.md](07_units_contracts.md) | ユニット間の契約 |
| [mock/index.html](mock/index.html) | 画面モック（見た目・文言と、画面ごとの仕様メモ） |

## 書き分け

- 01・05 は方針の粒度にとどめ、数値や細部は書かない。
- 条件と数値は 04、画面の見た目と振る舞いはモック、ユニット間で揃える値は 07 に書く。

## モック

`mock/index.html` をブラウザで開く。地図の表示にはインターネット接続が要る。左の画面一覧と上の状態の切り替えで各画面を見られ、右に仕様メモが出る。データはすべて架空のもの。
```

- [ ] **Step 3: `docs/01_requirements.md` を直す**

Edit で次の3か所を置き換える。

- 旧: `区切るのは、利用者が区切る操作をしたときと、最後の質問から一定の時間（設定で変えられる。区切らない設定もできる）が経ったときだけ。`
  新: `区切るのは、利用者が区切る操作をしたときと、最後の質問から一定の時間（既定15分。管理者が設定で変える）が経ったときだけ。`
- 旧: `| 設定 | 会話を自動で区切るまでの時間・連続して記録できる最長時間・`
  新: `| 設定 | 連続して記録できる最長時間・`
- 旧: `ふだんは20秒以内を目安にする。待っている間は止まっていないことが分かる`
  新: `ふだんは30秒以内を目安にする。検索などで長引いても、待っている間は止まっていないことが分かる`

- [ ] **Step 4: `docs/02_screen_list.md` と `docs/03_screen_transition.md` から SC-20 を除く**

- `docs/02_screen_list.md`: `| SC-20 | 会話 | 停車中 | 会話を自動で区切るまでの時間を変える | 時間の選択 | A-04 |` の行を削除する。
- `docs/03_screen_transition.md`: `        SC20["SC-20 会話"]` の行と、`    SC09 --> SC20` の行を削除する。

- [ ] **Step 5: `docs/04_detailed_requirements.md` を直す**

- 旧: `| US-A-04.005 | 最後の質問から一定の時間が経つと、自動で区切る。既定は15分 | SC-02 |`
  新: `| US-A-04.005 | 最後の質問から一定の時間が経つと、自動で区切る。既定は15分。時間は管理者が設定で変える（利用者の設定は無い） | SC-02 |`
- 旧: `| US-A-04.006 | 自動で区切るまでの時間を利用者が変えられる（5分・15分・30分・1時間・区切らない） | SC-20 |`
  新: `| US-A-04.006 | （廃止）自動で区切るまでの時間を利用者が変えられる | — |`

- [ ] **Step 6: `docs/05_technical_policies.md` を直す**

- 旧: `- 門番: 接続キーの確認・流量の制限・入力の検証を、AI を呼ぶ前に行う。`
  新:
  ```
  - 門番: 接続キーの確認・流量の制限・入力の検証を、AI を呼ぶ前に行う。
  - 音声の質問は、ストリーミングの文字起こしで文字にする。バッチの文字起こしは待ち時間の揺れが大きい（[adr/0002](../adr/0002-streaming-transcription.md)）。
  ```
- 旧: `- 会話の文脈は、利用者が設定した時間（区切らない設定もある）まで続けられるようにする。実行環境の寿命に依存せずに保てる方法を選ぶ（方法はユニットの設計で決める）。`
  新: `- 会話の文脈は、同じ会話の識別子で呼ばれるあいだ、AI の実行環境のセッションの中に保つ。会話は最後の質問から一定の時間で区切るので、セッションの寿命の内に収まる。過去のツールの結果は次の質問に持ち越さず、入力を小さく保つ（[adr/0003](../adr/0003-conversation-context.md)）。`
- 旧: `（質問を送ってから読み上げまで、数秒から十数秒）`
  新: `（質問を送ってから読み上げまで、ふつう十数秒。検索を伴うと30秒前後）`
- 旧: `| 会話の文脈の保持 | 設定した時間（最大で「区切らない」）まで文脈を保つ方法と、保てる量の上限 |`
  新: `| 会話の文脈の保持 | 決定済み（[adr/0003](../adr/0003-conversation-context.md)） |`
- 旧: `| モデルの設定値の置き場所 | 設定値をどこに置き、Agent がどの時点で読み直すか |`
  新: `| モデルの設定値の置き場所 | 決定済み（[07_units_contracts.md](07_units_contracts.md) UC-2） |`

- [ ] **Step 7: `docs/07_units_contracts.md` を直す**

- 旧: `置き場所は同 §9 で決め、決まったらここに書く。`
  新: `置き場所は設定値 `/trv2/<env>/agent-model-id`（Agent のリージョン）。Agent は呼ばれるたびに読む（60秒までキャッシュしてよい）。`
- 旧: `- 質問（音声か文字）は、受け付けた時点で質問の識別子と会話の文脈の識別子を返す。回答はその場では返さない。`
  新:
  ```
  - 質問（音声か文字）は、受け付けた時点で質問の識別子・会話の文脈の識別子・その会話が区切られる時刻を返す。回答はその場では返さない。
  - 会話が区切られる時刻は、Backend が受け付けた時刻に設定値 `/trv2/<env>/conversation-reset-minutes`（`ap-northeast-1`。既定15。55以下）の分数を足して求める。App はその時刻を過ぎたら会話の文脈の識別子を捨てる。
  ```
- 旧: `- 完了すると、回答の文・読み上げ音声の取り先・聞き取った文（音声の質問のとき）が返る。聞き取った文は、失敗のときも分かる範囲で返す。`
  新:
  ```
  - 完了すると、回答の文・読み上げ音声の取り先の一覧・聞き取った文（音声の質問のとき）が返る。聞き取った文は、失敗のときも分かる範囲で返す。
  - 読み上げ音声の取り先は、順番つきの一覧で返す。App は順番どおりに続けて鳴らす（1件だけのこともある）。
  - 失敗のときは、次の理由のどれかを返す: `no_speech`（聞き取れた文が空）・`transcribe_failed`・`agent_failed`・`tts_failed`。App は自分で判断した `timeout`・`network`・`invalid_key` と合わせて、利用者に知らせる文を選ぶ。
  ```
- 旧: `- 取りに行く処理は必ず止まるように作る（時間の経過で間隔を延ばし、上限で打ち切る）。打ち切りや取り消しの後も、Backend の処理は続いてよい。`
  新: `- 取りに行く処理は必ず止まるように作る。最初の10秒は1秒ごと、以後は2秒ごとに取りに行き、120秒で打ち切る。打ち切りや取り消しの後も、Backend の処理は続いてよい。`
- 旧: `| 会話の文脈の識別子 | 続けるときだけ。区切るとき（利用者の操作・設定した時間の経過）は App が捨て、送らない |`
  新: `| 会話の文脈の識別子 | 続けるときだけ。区切るとき（利用者の操作・区切られる時刻の経過）は App が捨て、送らない |`
- 旧: `- 録音の形式は、Android が変換なしで出せて、文字起こしのサービスが受け付ける形式にそろえる。`
  新: `- 録音の形式は、Android が変換なしで出せて、ストリーミングの文字起こしが受け付ける形式にそろえる（Ogg/Opus か PCM。どちらにするかはスパイクの結果で決め、ここに書く）。`
- 旧: `- 会話の文脈の識別子をそのまま渡す。Agent は同じ識別子が来るあいだ文脈を続ける。区切るかどうかは App が決める（UC-5）。`
  新:
  ```
  - 会話の文脈の識別子を、AI の実行環境のセッションの識別子としてそのまま渡す。Agent は同じ識別子が来るあいだ文脈を続ける。区切るかどうかは App が決める（UC-5）。
  - Agent は回答のあと、文脈からツールの呼び出しと結果を取り除き、質問と回答の文だけを残す。
  - 実行環境のセッションのアイドルの時間切れ（60分）は、会話を区切る時間の上限（55分）より長くする。
  ```
- 旧: `- Agent は回答を順に返す。Backend はそれをつないで回答の文にする。`
  新: `- Agent は回答を順に返し、最後に使ったトークン数（入力・出力・モデルの呼び出し回数）を返す。Backend はそれをつないで回答の文にし、トークン数を記録に残す。`

- [ ] **Step 8: `docs/mock/index.html` から SC-20 を除く**

Edit で次を行う。

- `<button class="list-item" data-go="SC-20">` で始まる1行（設定の一覧の「会話」）を削除する。
- `<!-- SC-20 Conversation settings -->` の行から、その直後の `<section class="screen" data-id="SC-20">` を閉じる `</section>` の行までを削除する（次の `<!-- SC-12 Recording check -->` は残す）。
- 旧: `items: ["SC-09", "SC-20", "SC-16",` 新: `items: ["SC-09", "SC-16",`
- 旧: `"SC-09": "SC-09", "SC-20": "SC-09", "SC-16": "SC-09",` 新: `"SC-09": "SC-09", "SC-16": "SC-09",`
- 旧: `<li>最後の質問から一定の時間（既定15分、SC-20 で変更）が経つと自動で区切る。ボタンの下段に「◯:◯◯ まで質問がなければ自動で区切ります」と出す。「区切らない」設定のときは出さない。</li></ul>`
  新: `<li>最後の質問から一定の時間（既定15分。管理者が設定で変える）が経つと自動で区切る。ボタンの下段に「◯:◯◯ まで質問がなければ自動で区切ります」と出す。</li></ul>`
- `  "SC-20": { name: "会話",` で始まる仕様メモのオブジェクトを、その `` </ul>` }, `` の行まで削除する（次の `"SC-16"` は残す）。

確認: `grep -n "SC-20" docs/mock/index.html` が何も出さないこと。ブラウザで `docs/mock/index.html` を開き、設定の一覧に「会話」が無く、他の画面が今までどおり切り替わること。

- [ ] **Step 9: ADR を書く**

`adr/README.md`:

```markdown
# adr

決定の記録（Architecture Decision Record）。何をなぜ決めたかを残す。番号は詰め直さない。
いまの姿は [docs/](../docs/README.md) に書き、ここには経緯と理由を書く。

| 番号 | 決定 | 状態 |
|---|---|---|
| [0001](0001-response-time-target.md) | 応答時間の目安を30秒に緩める | 採用 |
| [0002](0002-streaming-transcription.md) | 音声の質問はストリーミングで文字にする | 採用（スパイクで確認中） |
| [0003](0003-conversation-context.md) | 会話の文脈は実行環境のセッションに持ち、15分で区切る | 採用 |
```

`adr/0001-response-time-target.md`:

```markdown
# 0001. 応答時間の目安を30秒に緩める

- 日付: 2026-10-16
- 状態: 採用

## 背景

初期検討では「声の質問から読み上げ開始まで、ふだんは20秒以内」を目安にしていた。
実際のツーリングで音声の質問214件の所要時間を測ったところ、中央値18.3秒・90%で32.9秒・最大230秒だった。
検索を伴う質問は、回答の生成だけで十数秒から25秒ほどかかる。

## 決定

- 目安を「ふだんは30秒以内」に緩める。
- 長引いても、待っている間は止まっていないことが分かるようにする（待っているあいだの合図の音・画面の経過秒数）。
- 大きく外れる原因（最大230秒）は文字起こしの方式にあったので、そちらで対処する（[0002](0002-streaming-transcription.md)）。

## 影響

- [01_requirements.md](../docs/01_requirements.md) §7 の応答時間を直した。
- 段ごとの所要時間を記録とログに残し、目安を守れているかを測れるようにする。
```

`adr/0002-streaming-transcription.md`:

```markdown
# 0002. 音声の質問はストリーミングで文字にする

- 日付: 2026-10-16
- 状態: 採用（スパイクで確認中）

## 背景

音声の質問214件の計測で、段ごとの所要時間は次のとおりだった。

| 段 | 中央値 | 90% | 最大 |
|---|---|---|---|
| 文字起こし（バッチのジョブ。受け付けから完了の通知まで） | 9.2秒 | 26.6秒 | 219.9秒 |
| 回答の生成と音声合成 | 7.3秒 | 14.4秒 | 25.1秒 |

60秒を超えた10件は、どれも文字起こしだけで47〜220秒かかっていた。録音の大きさ（平均92〜105KB）とは関係が無く、バッチのジョブの待ちと揺れが原因と考えられる。

## 選択肢

| 案 | 判断 |
|---|---|
| A. バッチの文字起こし（S3 に置いてジョブを投げ、完了の通知を待つ） | 却下。上の揺れがそのまま残る |
| B. ストリーミングの文字起こしを、サーバー側（worker）から録音のファイルを流し込んで呼ぶ | 採用。ジョブの待ちが無い。App は AWS の認証情報を持たずに済み、門番も保てる |
| C. App からストリーミングの文字起こしを直接呼ぶ | 却下。App に AWS の認証情報が要る |

## 決定

- worker が、受け取った録音のファイルを Transcribe のストリーミング（`ja-JP`）に流し込んで文字にする。
- ストリーミングが受け付ける形式は PCM・FLAC・Ogg/Opus。録音は Ogg/Opus を第一の候補にし、だめなら PCM にする。
- expo-audio（58）は Ogg/Opus で録れないので、Ogg/Opus は自前のネイティブモジュール（MediaRecorder）で録る。PCM なら expo-audio の AudioStream で録れる。

## 確かめること（スパイク A）

- Lambda から録音のファイルを一気に流し込めるか（実時間に合わせて送る必要があるか）。
- 文字起こしの所要時間と、日本語の聞き取りの質。
- 実機で、インカムのマイクから Ogg/Opus と PCM のどちらが録れ、どちらがよく聞き取られるか。

## 結果

（スパイク A の結果をここに追記する）
```

`adr/0003-conversation-context.md`:

```markdown
# 0003. 会話の文脈は実行環境のセッションに持ち、15分で区切る

- 日付: 2026-10-16
- 状態: 採用

## 背景

初期検討では、会話を自動で区切るまでの時間を利用者が選べ（5分〜1時間・区切らない）、文脈は実行環境の寿命に依存せずに保つことにしていた。

- AI の実行環境（AgentCore Runtime）のセッションは、アイドルの時間切れ（60秒〜8時間）か寿命（最長8時間）で止まり、メモリ上の文脈は消える。停止しても残る保存領域（session storage）はプレビューで、バージョンを更新すると消える。確実に残す仕組みは AgentCore Memory だけ。
- 費用の大半は AI への入力で、その大半は検索の結果だった（検索した質問は1件で2万〜7万トークン。質問と回答の文だけなら1往復200〜300トークン）。どの方式でも文脈は毎回入力に入れ直すので、過去の検索の結果を文脈に残すと、次の質問でも数万トークンを持ち越す。
- 利用者にとって、15分で区切られて困ることは無い。

## 選択肢

| 案 | 判断 |
|---|---|
| A. 実行環境のセッションに文脈を持つ。区切る時間を寿命の内に収める | 採用。作るものが最も少ない |
| B. Backend が記録から直近の往復を組み立てて渡す | 不採用。区切らない設定を無くせば A で足りる |
| C. AgentCore Memory | 不採用。サービスが1つ増える |

## 決定

- 会話の文脈の識別子を、実行環境のセッションの識別子として使う。
- 会話は最後の質問から一定の時間で区切る。時間は設定値 `/trv2/<env>/conversation-reset-minutes`（既定15分・55分以下）で管理者が変える。利用者の設定（SC-20）と「区切らない」は無くす。
- 区切る時刻は Backend が受け付けのたびに求めて App に返し、App がその時刻を過ぎたら識別子を捨てる。実行環境のアイドルの時間切れは60分に固定し、必ず App の側が先に区切る。
- 回答のあと、文脈からツールの呼び出しと結果を取り除き、質問と回答の文だけを残す。直近の数往復に限る。

## 影響

- 再デプロイ・実行環境の異常・連続8時間の利用では、文脈が途中で消える。区切られたのと同じ扱いとして許容する。
- 使われなくなったセッションが最長60分残り、そのあいだ実行環境のメモリの費用がかかる。身内の利用の規模では小さい。
- [01](../docs/01_requirements.md)・[02](../docs/02_screen_list.md)・[03](../docs/03_screen_transition.md)・[04](../docs/04_detailed_requirements.md)・[05](../docs/05_technical_policies.md)・[07](../docs/07_units_contracts.md)・[モック](../docs/mock/index.html)を直した。
```

- [ ] **Step 10: 親の `README.md` を書く**

````markdown
# TouringProjectV2

バイクでツーリング中のライダーが、インカムのボタンと声だけで AI に質問できる Android アプリ。
AI は現在地と進行方向を踏まえて答え、質問と回答は走ったルートとともに記録に残る。

## 構成

このリポジトリはプロジェクト全体の要件・方針・契約・決定を持ち、各ユニットを束ねる。

| パス | 中身 | リポジトリ |
|---|---|---|
| `App/` | Android アプリ（React Native／Expo） | `TouringProjectV2_App` |
| `Backend/` | API（API Gateway＋Lambda・SAM・東京） | `TouringProjectV2_Backend` |
| `Agent/` | エージェント（Bedrock AgentCore・Strands・us-east-1） | `TouringProjectV2_Agent` |
| `CICD/` | Agent・Backend のデプロイ（非公開） | `TouringProjectV2_CICD` |
| [docs/](docs/README.md) | 要件・方針・契約の現行版。[docs/init/](docs/init/README.md) は初期検討のスナップショット | — |
| [adr/](adr/README.md) | 決定の記録 | — |

## 文書の検査と写し

```sh
python3 scripts/check_links.py docs adr README.md   # 相対リンクの切れを検査する
scripts/sync-docs.sh App Backend Agent CICD         # docs/ を各ユニットの docs-parent/ に写す
```
````

- [ ] **Step 11: 仕様書 §5.4 に追記する**

`docs/specs/2026-10-16-slice1-design.md` の
旧: `- 形式は Ogg/Opus（Android 10 以降の MediaRecorder が変換なしで出せ、Transcribe のストリーミングが受け付ける）。スパイク A で確かめ、だめなら PCM（WAV）にする。`
新:
```
- 形式は Ogg/Opus（Android 10 以降の MediaRecorder が変換なしで出せ、Transcribe のストリーミングが受け付ける）。スパイク A で確かめ、だめなら PCM にする。
- expo-audio（58）は Ogg/Opus で録れない（出力形式とエンコーダーに無い）。Ogg/Opus は自前のネイティブモジュール（MediaRecorder）で録る。PCM なら expo-audio の AudioStream（16kHz・int16）で録れる。
```

- [ ] **Step 12: 検査する**

```bash
cd $ROOT
python3 scripts/check_links.py docs adr README.md
git diff --exit-code HEAD -- docs/init && echo "docs/init unchanged"
grep -rn "SC-20\|区切らない設定\|20秒以内" docs/0*.md docs/mock/index.html
```
Expected: リンクの切れ 0件で終了コード0、`docs/init unchanged`、grep は何も出さない（`docs/04` の「（廃止）」の行は SC-20 を含まないこと）。

- [ ] **Step 13: コミット**

```bash
cd $ROOT
git add README.md docs/README.md docs/01_requirements.md docs/02_screen_list.md docs/03_screen_transition.md docs/04_detailed_requirements.md docs/05_technical_policies.md docs/06_units_definition.md docs/07_units_contracts.md docs/mock/index.html docs/specs/2026-10-16-slice1-design.md adr/README.md adr/0001-response-time-target.md adr/0002-streaming-transcription.md adr/0003-conversation-context.md
git commit -m "docs: add living docs and ADRs for slice 1 decisions"
```

---

### Task 3: 親の文書をユニットへ写すスクリプト

**Files:**
- Create: `scripts/sync-docs.sh`
- Test: `tests/test_sync_docs.sh`

**Interfaces:**
- Consumes: Task 2 の `docs/`
- Produces: `scripts/sync-docs.sh <unit-dir>...` — 各ユニットの `<unit-dir>/docs-parent/` を、親の `docs/`（`init/`・`specs/`・`plans/` を除く）と同じ中身にし、`COPIED.md` を置く。`docs-parent/` の外には触れない。ディレクトリでない引数があれば終了コード1、引数なしは2。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_sync_docs.sh`:

```bash
#!/usr/bin/env bash
# Tests for scripts/sync-docs.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/sync-docs.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "FAIL: $1" >&2; exit 1; }

unit="$WORK/Unit"
mkdir -p "$unit/docs-parent" "$unit/src"
echo "keep" > "$unit/README.md"
echo "keep" > "$unit/src/main.py"
echo "stale" > "$unit/docs-parent/stale.md"

"$SCRIPT" "$unit"

[ -f "$unit/docs-parent/01_requirements.md" ] || fail "01_requirements.md copied"
[ -f "$unit/docs-parent/mock/index.html" ] || fail "mock copied"
[ -f "$unit/docs-parent/COPIED.md" ] || fail "COPIED.md written"
[ ! -e "$unit/docs-parent/init" ] || fail "init excluded"
[ ! -e "$unit/docs-parent/specs" ] || fail "specs excluded"
[ ! -e "$unit/docs-parent/plans" ] || fail "plans excluded"
[ ! -e "$unit/docs-parent/stale.md" ] || fail "stale file removed"
[ "$(cat "$unit/README.md")" = "keep" ] || fail "README outside docs-parent kept"
[ "$(cat "$unit/src/main.py")" = "keep" ] || fail "src outside docs-parent kept"
cmp -s "$ROOT/docs/07_units_contracts.md" "$unit/docs-parent/07_units_contracts.md" || fail "content identical"

set +e
"$SCRIPT" "$WORK/missing" 2>/dev/null; code=$?
"$SCRIPT" 2>/dev/null; code_noargs=$?
set -e
[ "$code" -eq 1 ] || fail "missing dir exits 1 (got $code)"
[ "$code_noargs" -eq 2 ] || fail "no args exits 2 (got $code_noargs)"

echo "OK: sync-docs"
```

- [ ] **Step 2: 失敗を確かめる**

Run: `cd $ROOT && chmod +x tests/test_sync_docs.sh && tests/test_sync_docs.sh`
Expected: `scripts/sync-docs.sh: No such file or directory` で失敗する

- [ ] **Step 3: 実装する**

`scripts/sync-docs.sh`:

```bash
#!/usr/bin/env bash
# Copy the parent's current docs into each unit's docs-parent/ as a read-only copy.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <unit-dir>..." >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/docs/"

for unit in "$@"; do
  if [ ! -d "$unit" ]; then
    echo "not a directory: $unit" >&2
    exit 1
  fi
  dest="$unit/docs-parent/"
  mkdir -p "$dest"
  rsync -a --delete --exclude 'init/' --exclude 'specs/' --exclude 'plans/' "$SRC" "$dest"
  cat > "${dest}COPIED.md" <<'EOF'
# docs-parent

親リポジトリ（TouringProjectV2）の `docs/` の写し。ここは編集しない。
直すときは親の `docs/` を直し、親で `scripts/sync-docs.sh` を実行して写し直す。
EOF
  echo "synced: $unit"
done
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `cd $ROOT && chmod +x scripts/sync-docs.sh && tests/test_sync_docs.sh`
Expected: `OK: sync-docs`

- [ ] **Step 5: コミット**

```bash
cd $ROOT
git diff --exit-code HEAD -- docs/init
git add scripts/sync-docs.sh tests/test_sync_docs.sh
git commit -m "chore: add script to copy parent docs into units"
```

---

### Task 4: ユニットのリポジトリと GitHub のリポジトリ

**Files:**
- Create: `App/README.md`, `App/.gitignore`, `Backend/README.md`, `Backend/.gitignore`, `Agent/README.md`, `Agent/.gitignore`, `CICD/README.md`, `CICD/.gitignore`（各ユニットのリポジトリ）、各 `docs-parent/`（Task 3 で写す）

**Interfaces:**
- Consumes: Task 3 の `scripts/sync-docs.sh`
- Produces: 4つのローカルのリポジトリ（ブランチ `main`、初回コミット済み、`origin` を設定済み・未 push）と、GitHub の空のリポジトリ5つ。計画2〜4 はこの中で作業する。

- [ ] **Step 1: 名前が空いていることを確かめる**

```bash
for r in TouringProjectV2 TouringProjectV2_App TouringProjectV2_Backend TouringProjectV2_Agent TouringProjectV2_CICD; do
  gh repo view "h-akira/$r" >/dev/null 2>&1 && echo "EXISTS: $r" || echo "free: $r"
done
```
Expected: 5つとも `free`。`EXISTS` があれば止めて利用者に聞く。

- [ ] **Step 2: 4つのユニットを作る**

```bash
cd $ROOT
for u in App Backend Agent CICD; do mkdir -p "$u" && git -C "$u" init -b main; done
```

各ユニットの README と .gitignore を Write で作る。

`App/README.md`:
```markdown
# TouringProjectV2_App

TouringProjectV2 の Android アプリ（React Native／Expo の Development Build）。
プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し）。
```

`App/.gitignore`:
```
node_modules/
.expo/
android/
ios/
dist/
*.keystore
*.jks
.env
.env.*
.DS_Store
```

`Backend/README.md`:
```markdown
# TouringProjectV2_Backend

TouringProjectV2 の API（API Gateway＋Lambda・Python・SAM・`ap-northeast-1`）。
プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し）。
```

`Backend/.gitignore`:
```
.aws-sam/
env/
__pycache__/
*.pyc
.pytest_cache/
.env
.env.*
.DS_Store
```

`Agent/README.md`:
```markdown
# TouringProjectV2_Agent

TouringProjectV2 のエージェント（Bedrock AgentCore Runtime＋Strands・`us-east-1`）。
プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し）。
```

`Agent/.gitignore`:
```
env/
.venv/
__pycache__/
*.pyc
.pytest_cache/
node_modules/
cdk.out/
.env
.env.*
.DS_Store
```

`CICD/README.md`:
```markdown
# TouringProjectV2_CICD

TouringProjectV2 の Agent・Backend のデプロイの仕組み（非公開）。スライス1では手動でデプロイするので、まだ中身は無い。
プロジェクト全体の要件・方針・契約は [docs-parent/](docs-parent/README.md)（親リポジトリの写し）。
```

`CICD/.gitignore`:
```
.env
.env.*
.DS_Store
```

- [ ] **Step 3: 親の文書を写して検査する**

```bash
cd $ROOT
scripts/sync-docs.sh App Backend Agent CICD
python3 scripts/check_links.py App/README.md Backend/README.md Agent/README.md CICD/README.md
```
Expected: `synced:` が4行、リンクの切れ 0件。

- [ ] **Step 4: 各ユニットで初回コミットする**

```bash
cd $ROOT
for u in App Backend Agent CICD; do
  git -C "$u" add README.md .gitignore docs-parent
  git -C "$u" commit -m "chore: initialize repository with parent docs copy"
done
```

- [ ] **Step 5: GitHub のリポジトリを作る（push はしない）**

```bash
gh repo create h-akira/TouringProjectV2 --public --description "Hands-free AI touring assistant for motorcycle riders (parent: requirements, design, ADRs)"
gh repo create h-akira/TouringProjectV2_App --public --description "TouringProjectV2 Android app (React Native / Expo)"
gh repo create h-akira/TouringProjectV2_Backend --public --description "TouringProjectV2 backend (API Gateway, Lambda, SAM)"
gh repo create h-akira/TouringProjectV2_Agent --public --description "TouringProjectV2 agent (Bedrock AgentCore, Strands)"
gh repo create h-akira/TouringProjectV2_CICD --private --description "TouringProjectV2 deployment pipelines"
```

`gh repo create` にローカルのディレクトリを渡さないこと（渡すと `--push` の確認が出る）。

- [ ] **Step 6: リモートを設定する**

```bash
cd $ROOT
git remote add origin git@github.com:h-akira/TouringProjectV2.git
for u in App Backend Agent CICD; do git -C "$u" remote add origin "git@github.com:h-akira/TouringProjectV2_$u.git"; done
git remote -v; for u in App Backend Agent CICD; do git -C "$u" remote -v; done
gh repo view h-akira/TouringProjectV2_CICD --json visibility -q .visibility
```
Expected: 5つの `origin`、CICD は `PRIVATE`。push はしない（利用者の許可後。submodule の登録もそのときに行う）。

---

### Task 5: スパイク A-1 — 手元でストリーミングの文字起こしを測る（使い捨て）

**問い:** 録音のファイルを Transcribe のストリーミング（`ja-JP`）へ一気に流し込めるか。Ogg/Opus と PCM で、所要時間と聞き取りの質はどうか。

**Files（すべて追跡しない）:**
- Create: `tmp/spikes/stt/stt_probe.py`, `tmp/spikes/stt/make_samples.sh`, `tmp/spikes/stt/samples/*`, `tmp/spikes/stt/results.md`

**Interfaces:**
- Produces: `async probe(path: Path, encoding: str, rate: int, pace: str, region: str) -> dict`（キー: `file`・`encoding`・`pace`・`audio_seconds`・`t_stream_started`・`t_all_sent`・`t_done`・`t_first_result`・`transcript`）。Task 6・Task 7 で使う。

- [ ] **Step 1: 仮想環境を作る**

```bash
mkdir -p $ROOT/tmp/spikes/stt/samples && cd $ROOT/tmp/spikes/stt
python3 -m venv env && env/bin/pip install amazon-transcribe==0.6.4
ffmpeg -hide_banner -encoders 2>/dev/null | grep -i opus
```
Expected: `libopus` が出る（出なければ `brew reinstall ffmpeg` を利用者に頼む）。

- [ ] **Step 2: 見本の音声を作る**

`tmp/spikes/stt/make_samples.sh`:

```bash
#!/usr/bin/env bash
# Throwaway: synthesize Japanese questions with Polly and convert them to streaming formats.
set -euo pipefail
cd "$(dirname "$0")/samples"
synth() {
  aws polly synthesize-speech --profile touring --region ap-northeast-1 \
    --engine neural --voice-id Kazuha --language-code ja-JP \
    --output-format mp3 --text "$2" "$1.mp3" >/dev/null
}
synth q1 "右手に見える山は何という山ですか"
synth q2 "この先で給油できるところはありますか。できれば国道沿いで、十キロ以内だと助かります"
synth answer "愛鷹山です。富士山の南東にある火山で、標高は千五百メートルほどあります。"
for q in q1 q2; do
  ffmpeg -y -loglevel error -i "$q.mp3" -ar 16000 -ac 1 -c:a libopus -b:a 32k "$q.ogg"
  ffmpeg -y -loglevel error -i "$q.mp3" -ar 16000 -ac 1 -f s16le "$q.pcm"
  ffmpeg -y -loglevel error -i "$q.mp3" -f lavfi -i "anoisesrc=color=pink:amplitude=0.15" \
    -filter_complex "[0:a]aresample=16000,aformat=channel_layouts=mono[v];[1:a]aresample=16000,aformat=channel_layouts=mono[n];[v][n]amix=inputs=2:duration=first" \
    -c:a libopus -b:a 32k "${q}_noise.ogg"
done
ls -l
```

Run: `cd $ROOT/tmp/spikes/stt && chmod +x make_samples.sh && ./make_samples.sh`
Expected: `q1.ogg q1.pcm q1_noise.ogg q2.ogg q2.pcm q2_noise.ogg answer.mp3` ができる。

- [ ] **Step 3: 計測スクリプトを書く**

`tmp/spikes/stt/stt_probe.py`:

```python
"""Throwaway probe: stream an audio file to Transcribe Streaming (ja-JP) and time each stage."""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from pathlib import Path

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

CHUNK_BYTES = 8 * 1024


def audio_seconds(path: Path, encoding: str, rate: int) -> float:
    if encoding == "pcm":
        return path.stat().st_size / (rate * 2)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


class Collector(TranscriptResultStreamHandler):
    def __init__(self, stream, t0: float) -> None:
        super().__init__(stream)
        self.t0 = t0
        self.finals: list[str] = []
        self.first_result: float | None = None

    async def handle_transcript_event(self, transcript_event: TranscriptEvent) -> None:
        for result in transcript_event.transcript.results:
            if self.first_result is None:
                self.first_result = time.monotonic() - self.t0
            if not result.is_partial and result.alternatives:
                self.finals.append(result.alternatives[0].transcript)


async def probe(path: Path, encoding: str, rate: int, pace: str, region: str) -> dict:
    data = path.read_bytes()
    seconds = audio_seconds(path, encoding, rate) if pace == "realtime" else None
    client = TranscribeStreamingClient(region=region)
    t0 = time.monotonic()
    stream = await client.start_stream_transcription(
        language_code="ja-JP", media_sample_rate_hz=rate, media_encoding=encoding,
    )
    t_stream_started = time.monotonic() - t0
    handler = Collector(stream.output_stream, t0)

    async def write() -> float:
        delay = seconds * CHUNK_BYTES / len(data) if seconds else 0.0
        for start in range(0, len(data), CHUNK_BYTES):
            await stream.input_stream.send_audio_event(audio_chunk=data[start:start + CHUNK_BYTES])
            if delay:
                await asyncio.sleep(delay)
        await stream.input_stream.end_stream()
        return time.monotonic() - t0

    t_all_sent, _ = await asyncio.gather(write(), handler.handle_events())
    return {
        "file": path.name,
        "encoding": encoding,
        "pace": pace,
        "audio_seconds": round(seconds, 2) if seconds else None,
        "t_stream_started": round(t_stream_started, 2),
        "t_all_sent": round(t_all_sent, 2),
        "t_done": round(time.monotonic() - t0, 2),
        "t_first_result": round(handler.first_result, 2) if handler.first_result else None,
        "transcript": "".join(handler.finals),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--pace", choices=["fast", "realtime"], default="fast")
    parser.add_argument("--rate", type=int, default=16000)
    parser.add_argument("--region", default="ap-northeast-1")
    args = parser.parse_args()
    for path in args.files:
        encoding = "pcm" if path.suffix == ".pcm" else "ogg-opus"
        try:
            result = asyncio.run(probe(path, encoding, args.rate, args.pace, args.region))
        except Exception as error:  # noqa: BLE001 - throwaway probe reports every failure
            result = {"file": path.name, "encoding": encoding, "pace": args.pace, "error": repr(error)}
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 一気に流し込んで測る**

Run: `cd $ROOT/tmp/spikes/stt && AWS_PROFILE=touring env/bin/python stt_probe.py samples/*.ogg samples/*.pcm --pace fast`
Expected: 6行の JSON。`error` が無く、`transcript` が読み上げた文に近い。`t_done` を記録する。
`error` が出たら、その内容（例: 送る速さの制限）を記録し、Step 5 の結果と比べる。

- [ ] **Step 5: 実時間に合わせて流し込んで測る（比較の基準）**

Run: `cd $ROOT/tmp/spikes/stt && AWS_PROFILE=touring env/bin/python stt_probe.py samples/q1.ogg samples/q2.ogg samples/q1.pcm --pace realtime`
Expected: 3行の JSON。`t_done` は `audio_seconds` より少し長い。

- [ ] **Step 6: 結果を書き留める**

`tmp/spikes/stt/results.md` に、Step 4・5 の JSON をそのまま貼り、次をまとめる: 一気に流し込めたか、形式ごとの `t_done`、雑音入りの聞き取り、バッチとの比較（中央値9.2秒）。

---

### Task 6: スパイク A-2 — Lambda から測る（使い捨て）

**問い:** Lambda（Python 3.13・arm64・東京）からも同じように動くか（`awscrt` が動くか、所要時間は手元と変わらないか）。

**Files（すべて追跡しない）:**
- Create: `tmp/spikes/stt-lambda/template.yaml`, `tmp/spikes/stt-lambda/src/handler.py`, `tmp/spikes/stt-lambda/src/requirements.txt`, `tmp/spikes/stt-lambda/src/stt_probe.py`（Task 5 の写し）, `tmp/spikes/stt-lambda/src/samples/`

**Interfaces:**
- Consumes: Task 5 の `probe()` と見本の音声

- [ ] **Step 1: ファイルを用意する**

```bash
mkdir -p $ROOT/tmp/spikes/stt-lambda/src/samples && cd $ROOT/tmp/spikes/stt-lambda
cp ../stt/stt_probe.py src/
cp ../stt/samples/q1.ogg ../stt/samples/q2.ogg ../stt/samples/q1_noise.ogg ../stt/samples/q1.pcm src/samples/
echo "amazon-transcribe==0.6.4" > src/requirements.txt
```

`tmp/spikes/stt-lambda/src/handler.py`:

```python
"""Throwaway Lambda: run the streaming transcription probe on bundled samples."""
from __future__ import annotations

import asyncio
from pathlib import Path

from stt_probe import probe

SAMPLES = Path(__file__).parent / "samples"


def handler(event: dict, context: object) -> list[dict]:
    results: list[dict] = []
    for path in sorted(SAMPLES.iterdir()):
        encoding = "pcm" if path.suffix == ".pcm" else "ogg-opus"
        try:
            results.append(asyncio.run(probe(path, encoding, 16000, "fast", "ap-northeast-1")))
        except Exception as error:  # noqa: BLE001 - throwaway probe reports every failure
            results.append({"file": path.name, "error": repr(error)})
    return results
```

`tmp/spikes/stt-lambda/template.yaml`:

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Transform: AWS::Serverless-2016-10-31
Description: Throwaway spike for streaming transcription from Lambda (trv2)

Resources:
  SpikeSttFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: lambda-trv2-dev-spike-stt
      Runtime: python3.13
      Architectures: [arm64]
      Handler: handler.handler
      CodeUri: src/
      MemorySize: 512
      Timeout: 120
      Policies:
        - Statement:
            - Effect: Allow
              Action: transcribe:StartStreamTranscription
              Resource: "*"
```

- [ ] **Step 2: 名前の衝突が無いことを確かめる**

```bash
aws cloudformation describe-stacks --profile touring --region ap-northeast-1 --stack-name stack-trv2-dev-spike-stt 2>&1 | head -1
aws lambda get-function --profile touring --region ap-northeast-1 --function-name lambda-trv2-dev-spike-stt 2>&1 | head -1
```
Expected: どちらも `does not exist` / `ResourceNotFoundException`。

- [ ] **Step 3: デプロイする**

```bash
cd $ROOT/tmp/spikes/stt-lambda
sam build
sam deploy --stack-name stack-trv2-dev-spike-stt --region ap-northeast-1 --profile touring \
  --capabilities CAPABILITY_IAM --resolve-s3 --no-confirm-changeset --no-fail-on-empty-changeset
```
Expected: `Successfully created/updated stack - stack-trv2-dev-spike-stt`。`sam build` がネイティブの wheel（`awscrt`）で失敗したら `sam build --use-container` を試す（Docker が要る。無ければ利用者に聞く）。

- [ ] **Step 4: 5回呼んで測る（1回目はコールドスタート）**

```bash
cd $ROOT/tmp/spikes/stt-lambda
for i in 1 2 3 4 5; do
  aws lambda invoke --profile touring --region ap-northeast-1 --function-name lambda-trv2-dev-spike-stt \
    --cli-binary-format raw-in-base64-out --payload '{}' "out-$i.json" >/dev/null && cat "out-$i.json" && echo
done
```
Expected: 各回に4件の結果。`error` が無く、`t_done` が手元（Task 5 Step 4）と同じ程度。結果を `tmp/spikes/stt/results.md` に追記する。

- [ ] **Step 5: 片付ける（利用者に確認してから）**

利用者に「スパイク用のスタック `stack-trv2-dev-spike-stt` を削除してよいか」を確認し、許可を得たら:

```bash
cd $ROOT/tmp/spikes/stt-lambda
sam delete --stack-name stack-trv2-dev-spike-stt --region ap-northeast-1 --profile touring --no-prompts
```
Expected: `Deleted successfully`。`aws-sam-cli-managed-default` のスタック（SAM が共用する置き場）は消さない。

---

### Task 7: スパイク A-3 — 実機のインカムで録る（使い捨て）

**問い:** インカムのマイク（SCO）から、MediaRecorder の Ogg/Opus と expo-audio の AudioStream の PCM のどちらが録れるか。それぞれの聞き取りの質はどうか。

**Files（すべて追跡しない）:** `tmp/spikes/spike-app/` 以下。

**Interfaces:**
- Consumes: Task 5 の `stt_probe.py`、見本の `answer.mp3`
- Produces: スパイク用アプリ `com.touringproject.v2spike`（Task 8 でも使う）、`SpikeNative` モジュール（`startOgg(name: string, audioSource: number): Promise<string>`・`stopOgg(): Promise<{path: string; bytes: number; durationMs: number}>`・`startKeepAlive(): void`・`stopKeepAlive(): void`・`filesDir(): string`）

**前提:** 利用者の Android 端末（Android 12 以降）を USB でつなぎ、USB デバッグを有効にし、インカムをペアリングしておく。`adb devices` に端末が出ること。

- [ ] **Step 1: アプリを作る**

```bash
mkdir -p $ROOT/tmp/spikes && cd $ROOT/tmp/spikes
npx create-expo-app@latest spike-app --template blank-typescript
cd spike-app && npx expo install expo-dev-client expo-audio
```

`app.json` の `expo` に次を足す（既存のキーは残す）:

```json
"android": { "package": "com.touringproject.v2spike" },
"plugins": [["expo-audio", { "microphonePermission": "質問の録音に使います", "enableBackgroundPlayback": true }]]
```

- [ ] **Step 2: 経路と前面化のモジュールを持ち込む**

スパイクは使い捨てなので、インカムの経路と前面化は、検証済みのモジュールを写して使う（計画4 では書き直す）。写す元は環境変数 `SPIKE_MODULES_SRC` で指す。

```bash
cd $ROOT/tmp/spikes/spike-app && mkdir -p modules
cp -R "$SPIKE_MODULES_SRC"/bt-audio-route modules/
cp -R "$SPIKE_MODULES_SRC"/app-foreground modules/
rm -rf modules/*/android/build
```

- [ ] **Step 3: `SpikeNative` モジュールを書く**

`modules/spike-native/expo-module.config.json`:
```json
{ "platforms": ["android"], "android": { "modules": ["com.touringproject.v2spike.SpikeNativeModule"] } }
```

`modules/spike-native/package.json`:
```json
{ "name": "spike-native", "version": "1.0.0", "main": "src/index.ts", "private": true }
```

`modules/spike-native/android/build.gradle`:
```gradle
plugins {
  id 'com.android.library'
  id 'expo-module-gradle-plugin'
}

group = 'com.touringproject.v2spike'
version = '1.0.0'

android {
  namespace "com.touringproject.v2spike"
  defaultConfig {
    versionCode 1
    versionName "1.0.0"
  }
}
```

`modules/spike-native/android/src/main/AndroidManifest.xml`:
```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
  <uses-permission android:name="android.permission.RECORD_AUDIO" />
  <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />
  <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
  <queries>
    <package android:name="com.google.android.apps.maps" />
  </queries>
  <application>
    <service
      android:name="com.touringproject.v2spike.KeepAliveService"
      android:exported="false"
      android:foregroundServiceType="microphone|mediaPlayback" />
  </application>
</manifest>
```

`modules/spike-native/android/src/main/java/com/touringproject/v2spike/SpikeNativeModule.kt`:
```kotlin
package com.touringproject.v2spike

import android.content.Intent
import android.media.MediaRecorder
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.io.File

// Throwaway spike module: Ogg/Opus recording and a keep-alive foreground service.
class SpikeNativeModule : Module() {
  private val context
    get() = requireNotNull(appContext.reactContext) { "reactContext is null" }

  private var recorder: MediaRecorder? = null
  private var recordingFile: File? = null
  private var startedAt = 0L

  private fun outputDir(): File = requireNotNull(context.getExternalFilesDir(null)) { "no external files dir" }

  override fun definition() = ModuleDefinition {
    Name("SpikeNative")

    Function("filesDir") { outputDir().absolutePath }

    AsyncFunction("startOgg") { name: String, audioSource: Int ->
      check(recorder == null) { "already recording" }
      val file = File(outputDir(), name)
      val r = MediaRecorder(context)
      r.setAudioSource(audioSource)
      r.setOutputFormat(MediaRecorder.OutputFormat.OGG)
      r.setAudioEncoder(MediaRecorder.AudioEncoder.OPUS)
      r.setAudioSamplingRate(16000)
      r.setAudioChannels(1)
      r.setAudioEncodingBitRate(32000)
      r.setOutputFile(file.absolutePath)
      r.prepare()
      r.start()
      recorder = r
      recordingFile = file
      startedAt = System.currentTimeMillis()
      file.absolutePath
    }

    AsyncFunction("stopOgg") {
      val r = checkNotNull(recorder) { "not recording" }
      val file = checkNotNull(recordingFile)
      runCatching { r.stop() }
      r.release()
      recorder = null
      recordingFile = null
      mapOf(
        "path" to file.absolutePath,
        "bytes" to file.length(),
        "durationMs" to (System.currentTimeMillis() - startedAt),
      )
    }

    Function("startKeepAlive") {
      context.startForegroundService(Intent(context, KeepAliveService::class.java))
    }

    Function("stopKeepAlive") {
      context.stopService(Intent(context, KeepAliveService::class.java))
    }
  }
}
```

`modules/spike-native/android/src/main/java/com/touringproject/v2spike/KeepAliveService.kt`:
```kotlin
package com.touringproject.v2spike

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder

// Throwaway spike service: keeps the process alive while the app is in the background.
class KeepAliveService : Service() {
  override fun onBind(intent: Intent?): IBinder? = null

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    val manager = getSystemService(NotificationManager::class.java)
    manager.createNotificationChannel(
      NotificationChannel(CHANNEL_ID, "Spike keep-alive", NotificationManager.IMPORTANCE_LOW),
    )
    val notification = Notification.Builder(this, CHANNEL_ID)
      .setContentTitle("Spike: keeping alive")
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
    private const val CHANNEL_ID = "spike_keep_alive"
    private const val NOTIFICATION_ID = 1
  }
}
```

`modules/spike-native/src/index.ts`:
```ts
import { NativeModule, requireNativeModule } from "expo-modules-core";

export type StopResult = { path: string; bytes: number; durationMs: number };

declare class SpikeNativeModule extends NativeModule {
  filesDir(): string;
  startOgg(name: string, audioSource: number): Promise<string>;
  stopOgg(): Promise<StopResult>;
  startKeepAlive(): void;
  stopKeepAlive(): void;
}

export default requireNativeModule<SpikeNativeModule>("SpikeNative");
```

- [ ] **Step 4: 録音の画面を書く**

`App.tsx`（create-expo-app が作ったものを置き換える）:

```tsx
import { useRef, useState } from "react";
import { Button, PermissionsAndroid, ScrollView, Text, View } from "react-native";
import { requestRecordingPermissionsAsync, useAudioStream } from "expo-audio";
import BtAudioRoute from "./modules/bt-audio-route/src";
import SpikeNative from "./modules/spike-native/src";
import { BackgroundTest } from "./BackgroundTest";

// MediaRecorder.AudioSource values.
const SOURCES: Record<string, number> = { MIC: 1, VOICE_RECOGNITION: 6, VOICE_COMMUNICATION: 7 };

export default function App() {
  const [log, setLog] = useState<string[]>([]);
  const [source, setSource] = useState("VOICE_RECOGNITION");
  const seq = useRef(0);
  const { stream } = useAudioStream({ sampleRate: 16000, channels: 1, encoding: "int16" });

  const add = (line: string) => {
    const stamped = `${new Date().toISOString()} ${line}`;
    BtAudioRoute.appendTrace(stamped);
    setLog((prev) => [stamped, ...prev].slice(0, 40));
  };

  const prepare = async () => {
    await requestRecordingPermissionsAsync();
    await PermissionsAndroid.requestMultiple([
      "android.permission.BLUETOOTH_CONNECT",
      "android.permission.POST_NOTIFICATIONS",
    ]);
    const result = await BtAudioRoute.acquireSco(3000);
    add(`acquireSco ok=${result.ok} ${JSON.stringify(result)}`);
  };

  const startOgg = async () => {
    seq.current += 1;
    const name = `rec-${seq.current}-${source}.ogg`;
    add(`startOgg ${await SpikeNative.startOgg(name, SOURCES[source])}`);
  };

  const stopOgg = async () => add(`stopOgg ${JSON.stringify(await SpikeNative.stopOgg())}`);

  const startPcm = async () => {
    seq.current += 1;
    await stream.start();
    const uri = `file://${SpikeNative.filesDir()}/rec-${seq.current}-stream.pcm`;
    add(`startPcm ${JSON.stringify(await stream.startFileRecordingAsync({ uri, format: "pcm" }))} rate=${stream.sampleRate}`);
  };

  const stopPcm = async () => {
    add(`stopPcm ${JSON.stringify(await stream.stopFileRecordingAsync())}`);
    stream.stop();
  };

  const release = async () => {
    await BtAudioRoute.releaseSco();
    add("releaseSco");
  };

  return (
    <ScrollView contentContainerStyle={{ padding: 24, gap: 8 }}>
      <Text>trace: {BtAudioRoute.tracePath()}</Text>
      <Text>files: {SpikeNative.filesDir()}</Text>
      <Button title="1. 許可と SCO を張る" onPress={prepare} />
      <View style={{ flexDirection: "row", gap: 8 }}>
        {Object.keys(SOURCES).map((name) => (
          <Button key={name} title={name === source ? `[${name}]` : name} onPress={() => setSource(name)} />
        ))}
      </View>
      <Button title="2a. Ogg 録音開始" onPress={startOgg} />
      <Button title="2b. Ogg 録音停止" onPress={stopOgg} />
      <Button title="3a. PCM 録音開始（AudioStream）" onPress={startPcm} />
      <Button title="3b. PCM 録音停止" onPress={stopPcm} />
      <Button title="4. SCO を解放" onPress={release} />
      <BackgroundTest onLog={add} />
      {log.map((line, i) => (
        <Text key={i} style={{ fontSize: 11 }}>{line}</Text>
      ))}
    </ScrollView>
  );
}
```

`BackgroundTest.tsx`（Task 8 で使う。ここで先に作っておく）:

```tsx
import { useRef } from "react";
import { AppState, Button } from "react-native";
import { createAudioPlayer, setAudioModeAsync } from "expo-audio";
import AppForeground from "./modules/app-foreground/src";
import SpikeNative from "./modules/spike-native/src";

const NAV_PACKAGE = "com.google.android.apps.maps";
const PROBE_URL = "https://www.google.com/generate_204";
const TOTAL_SECONDS = 90;
const PLAY_AT_SECONDS = [20, 60];

type Props = { onLog: (line: string) => void };

// Throwaway: after switching to the nav app, keep polling and play audio from the background.
export function BackgroundTest({ onLog }: Props) {
  const running = useRef(false);

  const run = async (keepAlive: boolean) => {
    if (running.current) return;
    running.current = true;
    await setAudioModeAsync({ shouldPlayInBackground: true, interruptionMode: "mixWithOthers" });
    const player = createAudioPlayer(require("./assets/answer.mp3"));
    if (keepAlive) SpikeNative.startKeepAlive();
    onLog(`bg start keepAlive=${keepAlive}`);
    setTimeout(async () => onLog(`launch nav ok=${await AppForeground.launchApp(NAV_PACKAGE)}`), 1500);

    const t0 = Date.now();
    for (let second = 1; second <= TOTAL_SECONDS; second += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const lag = Date.now() - t0 - second * 1000;
      let status = "ng";
      try {
        status = String((await fetch(PROBE_URL)).status);
      } catch (error) {
        status = `error ${String(error)}`;
      }
      onLog(`bg t=${second}s lag=${lag}ms fetch=${status} appState=${AppState.currentState}`);
      if (PLAY_AT_SECONDS.includes(second)) {
        player.seekTo(0);
        player.play();
        onLog(`bg play at ${second}s`);
      }
    }
    if (keepAlive) SpikeNative.stopKeepAlive();
    player.remove();
    onLog("bg done");
    running.current = false;
  };

  return (
    <>
      <Button title="5a. 背面テスト（常駐あり）" onPress={() => run(true)} />
      <Button title="5b. 背面テスト（常駐なし）" onPress={() => run(false)} />
    </>
  );
}
```

```bash
cp $ROOT/tmp/spikes/stt/samples/answer.mp3 $ROOT/tmp/spikes/spike-app/assets/answer.mp3
```

- [ ] **Step 5: ビルドして入れる**

```bash
cd $ROOT/tmp/spikes/spike-app
npx tsc --noEmit
npx expo run:android --device
```
Expected: 型エラーが無い。端末にアプリが入って起動する。ビルドが失敗したら、エラーの内容を調べてから直す（同じコマンドを繰り返さない）。`interruptionMode` の値が型エラーになるときは、`node_modules/expo-audio/build/Audio.types.d.ts` の `InterruptionMode` の定義に合わせる。

- [ ] **Step 6: 【利用者の作業】インカムで録る**

インカムをつないだ状態で、利用者に次を頼む（静かな場所で1組、エンジンをかけるか走行音を流した状態で1組）:

1. 「1. 許可と SCO を張る」→ ログに `acquireSco ok=true` が出ることを確かめる
2. 3つの音源（MIC・VOICE_RECOGNITION・VOICE_COMMUNICATION）それぞれで、「2a」→「右手に見える山は何という山ですか」と話す→「2b」
3. 「3a」→ 同じ文を話す →「3b」
4. 「4. SCO を解放」

- [ ] **Step 7: 録音を取り出して文字にする**

```bash
mkdir -p $ROOT/tmp/spikes/stt/device && cd $ROOT/tmp/spikes/stt/device
adb pull /sdcard/Android/data/com.touringproject.v2spike/files/ .
ls -l files/
cd $ROOT/tmp/spikes/stt
AWS_PROFILE=touring env/bin/python stt_probe.py device/files/*.ogg device/files/*.pcm --pace fast
```
Expected: 録音ごとに1行の JSON。`transcript` を話した文と比べる。全サンプルが0で無音の録音（`transcript` が空・ファイルが極端に小さい）があれば、その音源の組み合わせを「録れない」として記録する。PCM の `rate` が 16000 でなければ（ログの `rate=`）、その値を `--rate` に渡して測り直す。

- [ ] **Step 8: 結果を書き留める**

`tmp/spikes/stt/results.md` に追記する: 形式×音源ごとの「録れたか」「聞き取りの正しさ（話した文との違い）」「`t_done`」、静かな場所と騒音下の差。

---

### Task 8: スパイク B — ナビに切り替えたあとの背面での動作（使い捨て）

**問い:** ナビ（Google マップ）へ切り替えたあとも、JS のポーリングと回答の再生が続くか。フォアグラウンドサービスは要るか。画面が消えていても続くか。

**Files:** Task 7 のスパイク用アプリ（`BackgroundTest.tsx` は作成済み）

**Interfaces:**
- Consumes: Task 7 のアプリ（`SpikeNative.startKeepAlive`・`AppForeground.launchApp`・`BtAudioRoute.appendTrace`）

- [ ] **Step 1: 【利用者の作業】背面テストを4通り行う**

Google マップでナビを始めておき（目的地はどこでもよい）、スパイク用アプリに戻って、次を順に行ってもらう。1回ごとに90秒待つ。

1. 「5a. 背面テスト（常駐あり）」→ マップに切り替わる → 画面は点けたまま
2. 「5a」→ マップに切り替わったら、電源ボタンで画面を消す
3. 「5b. 背面テスト（常駐なし）」→ 画面は点けたまま
4. 「5b」→ 画面を消す

各回で、20秒後と60秒後に回答の音声がインカムかスピーカーから聞こえたか、マップの案内の音声と重なっても両方聞こえたかを、利用者に記録してもらう。

- [ ] **Step 2: 記録を取り出す**

```bash
mkdir -p $ROOT/tmp/spikes/bg && cd $ROOT/tmp/spikes/bg
adb shell run-as com.touringproject.v2spike ls files 2>/dev/null || true
```
`App.tsx` の画面上部に出ている `trace:` のパスを使って取り出す:
```bash
adb pull "<trace のパス>" trace.log
grep "bg " trace.log | awk '{print $0}' | tail -400 > bg.log
```
（`run-as` で読めない場所なら、`trace:` のパスが `/sdcard/Android/data/...` の下であることを確かめてから `adb pull` する。）

- [ ] **Step 3: 判定する**

`bg.log` から、4通りそれぞれについて次を読む:
- `t=` の行が 90 まで続いたか（途中で止まっていないか）
- `lag=` の最大値（タイマーの遅れ。数秒以上なら、背面で間引かれている）
- `fetch=204` が続いたか
- `bg play at 20s`・`60s` の行と、利用者が実際に聞こえたかの記録

判定の基準: 「常駐あり・画面を消す」で、t=90 まで止まらず、`lag` が最大3秒以内、2回とも音が聞こえれば、仕様書 §5.3 の案（JS に置く＋フォアグラウンドサービス）を採用する。そうでなければ、ポーリングと再生をネイティブのサービスに移す案に切り替える。

- [ ] **Step 4: 結果を書き留める**

`tmp/spikes/bg/results.md` に、4通りの結果の表と判定を書く。

---

### Task 9: スパイクの結果を反映する

**Files:**
- Modify: `adr/0002-streaming-transcription.md`（「結果」の節）
- Create: `adr/0004-background-processing.md`
- Modify: `adr/README.md`（表に0004を足す。0002の状態を更新する）
- Modify: `docs/07_units_contracts.md`（UC-5 の録音の形式）
- Modify: `docs/specs/2026-10-16-slice1-design.md`（§5.3・§5.4・§12）

**Interfaces:**
- Consumes: `tmp/spikes/stt/results.md`、`tmp/spikes/bg/results.md`
- Produces: 計画2〜4 の前提になる決定（録音の形式・音源・背面での処理の置き場所）

- [ ] **Step 1: ADR 0002 に結果を書く**

`adr/0002-streaming-transcription.md` の `（スパイク A の結果をここに追記する）` を、次の形の結果で置き換える（数値は results.md から写す）。状態を「採用」に変える（ストリーミングがだめだった場合は「却下」にし、案A に戻す理由を書く）。

```markdown
## 結果（2026-10-xx のスパイク）

| 条件 | 一気に流し込めたか | 所要時間（t_done） | 聞き取り |
|---|---|---|---|
| 手元・Ogg/Opus・見本 | （値） | （値） | （値） |
| 手元・PCM・見本 | （値） | （値） | （値） |
| Lambda・Ogg/Opus（コールド／ウォーム） | （値） | （値） | （値） |
| 実機・Ogg/Opus・（音源） | （値） | （値） | （値） |
| 実機・PCM・AudioStream | （値） | （値） | （値） |

決定: 録音の形式は（Ogg/Opus か PCM）、音源の既定は（音源）。
```

表の「（値）」は、すべて実測の値で埋める。埋められない行は、その理由（例: 録れなかった）を書く。

- [ ] **Step 2: ADR 0004 を書く**

`adr/0004-background-processing.md` を、Task 8 の判定に合わせて書く。構成は 0001〜0003 と同じ（日付・状態・背景・選択肢・決定・影響）。選択肢は「A. 一巡の処理を JS に置き、フォアグラウンドサービスでプロセスを生かす」「B. ポーリングと再生をネイティブのサービスに置く」の2つ。背景に4通りの結果の表を入れる。

- [ ] **Step 3: 現行版と仕様書を直す**

- `docs/07_units_contracts.md`: 旧 `（Ogg/Opus か PCM。どちらにするかはスパイクの結果で決め、ここに書く）` を、決めた形式（例: `（Ogg/Opus・16kHz・モノラル）`）に置き換える。
- `docs/specs/2026-10-16-slice1-design.md`: §5.3・§5.4 を決定に合わせて直し、§12 の「スパイク A」「スパイク B」の行を「決定済み（adr/0002・adr/0004）」にする。
- `adr/README.md`: 0002 の状態を更新し、0004 の行を足す。

- [ ] **Step 4: 検査する**

```bash
cd $ROOT
python3 scripts/check_links.py docs adr README.md
git diff --exit-code HEAD -- docs/init && echo "docs/init unchanged"
grep -rnE "[0-9]{12}|（値）|2026-10-xx" adr docs/0*.md docs/specs || echo "clean"
tests/test_sync_docs.sh
```
Expected: リンクの切れ 0件、`docs/init unchanged`、grep は `clean`（アカウント ID・埋め残し・仮の日付が無い）、`OK: sync-docs`。ADR に地名や座標を書いていないことも目で確かめる。

- [ ] **Step 5: 写し直してコミットする**

```bash
cd $ROOT
git add adr/README.md adr/0002-streaming-transcription.md adr/0004-background-processing.md docs/07_units_contracts.md docs/specs/2026-10-16-slice1-design.md
git commit -m "docs: record spike results for transcription and background processing"
scripts/sync-docs.sh App Backend Agent CICD
for u in App Backend Agent CICD; do
  git -C "$u" add docs-parent && git -C "$u" commit -m "docs: sync parent docs" || true
done
```

- [ ] **Step 6: 利用者に報告する**

スパイク A・B の結論（録音の形式・音源・背面での処理の置き場所）と、計画2（Agent）を書き始めてよいかを利用者に聞く。スパイクのコード（`tmp/spikes/`）は追跡しないので残しておいてよい。消すときは利用者に確認する。
