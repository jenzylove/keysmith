import unittest

from keysmith import llm
from keysmith.llm import VultrInference, LLMError, LLMResult


class FakeHTTPError(Exception):
    def __init__(self, code, body):
        self.code = code
        self._body = body.encode()
        self.fp = True

    def read(self):
        return self._body


class TestLLMClient(unittest.TestCase):
    def test_not_configured_raises(self):
        c = VultrInference(api_key="")
        self.assertFalse(c.configured)
        with self.assertRaises(LLMError):
            c.chat("sys", "user")

    def test_configured_true_with_key(self):
        self.assertTrue(VultrInference(api_key="abc").configured)

    def test_fallback_on_empty_then_success(self):
        c = VultrInference(api_key="k", model="m1", fallback="m2")
        calls = []

        def fake_one(model, system, user, temperature, max_tokens):
            calls.append(model)
            if model == "m1":
                return "", 10          # empty -> triggers fallback
            return '{"words":["Rocky"]}', 20

        c._one_call = fake_one  # type: ignore
        res = c.chat("sys", "u")
        self.assertIsInstance(res, LLMResult)
        self.assertEqual(res.model, "m2")
        self.assertEqual(calls, ["m1", "m2"])
        self.assertEqual(res.attempts, ["m1", "m2"])

    def test_all_fail_raises(self):
        c = VultrInference(api_key="k", model="m1", fallback="m2")

        def fake_one(*a, **k):
            raise LLMError("boom")

        c._one_call = fake_one  # type: ignore
        with self.assertRaises(LLMError):
            c.chat("sys", "u")

    def test_safe_read_extracts_error_message(self):
        err = FakeHTTPError(401, '{"error":{"message":"Invalid API key"}}')
        self.assertEqual(llm._safe_read(err), "Invalid API key")


if __name__ == "__main__":
    unittest.main()
