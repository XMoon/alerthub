import json
import unittest

from app.modules.json_utils import normalize_json_body


class NormalizeJsonBodyTests(unittest.TestCase):
    def test_keeps_valid_json_unchanged(self) -> None:
        body = b'{"body":"hello\\nworld","group":"ani-rss"}'

        normalized_body, repaired = normalize_json_body(body)

        self.assertFalse(repaired)
        self.assertEqual(normalized_body, body)

    def test_repairs_raw_newlines_inside_json_strings(self) -> None:
        body = '{"body":"line 1\nline 2","group":"ani-rss"}'.encode("utf-8")

        normalized_body, repaired = normalize_json_body(body)
        payload = json.loads(normalized_body)

        self.assertTrue(repaired)
        self.assertEqual(payload["body"], "line 1\nline 2")

    def test_repairs_invalid_backslash_escapes_inside_json_strings(self) -> None:
        body = r'{"body":"D:\PT\BTAnime\Magic","group":"ani-rss"}'.encode("utf-8")

        normalized_body, repaired = normalize_json_body(body)
        payload = json.loads(normalized_body)

        self.assertTrue(repaired)
        self.assertEqual(payload["body"], r"D:\PT\BTAnime\Magic")


if __name__ == "__main__":
    unittest.main()
