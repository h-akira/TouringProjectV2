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
