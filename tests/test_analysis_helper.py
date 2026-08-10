from __future__ import annotations

import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.workers import analysis_helper


class AnalysisHelperTests(unittest.TestCase):
    def test_response_is_safe_for_a_cp1250_stdout(self) -> None:
        response = {
            "ok": True,
            "result": {"title": "Cena 20₪ 🎬"},
        }
        stdin = SimpleNamespace(buffer=io.BytesIO(b"{}"))
        raw_stdout = io.BytesIO()
        stdout = io.TextIOWrapper(raw_stdout, encoding="cp1250")

        with (
            patch.object(analysis_helper.sys, "stdin", stdin),
            patch.object(analysis_helper.sys, "stdout", stdout),
            patch.object(analysis_helper, "run_request", return_value=response),
        ):
            exit_code = analysis_helper.main()
            stdout.flush()

        encoded_response = raw_stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertTrue(encoded_response.isascii())
        self.assertEqual(json.loads(encoded_response.decode("utf-8")), response)


if __name__ == "__main__":
    unittest.main()
