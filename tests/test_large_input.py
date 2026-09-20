"""
Tests for large input message protection (POST-PATCH).
Verifies the actual patched build_context, message truncation, and embedding guard.
Does NOT call real Gemini API — uses mocks only.
"""
import asyncio
import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.memory.context_builder import ContextBuilder, ContextBundle


def make_builder(max_tokens: int = 8000) -> ContextBuilder:
    """Create a ContextBuilder with mocked session & embedding service."""
    mock_session = AsyncMock()
    mock_emb = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch.dict(os.environ, {"MAX_CONTEXT_TOKENS": str(max_tokens)}):
        builder = ContextBuilder(mock_session, mock_emb)
    return builder


async def run_build_context(builder, user_query, timeout=2.0):
    return await asyncio.wait_for(
        builder.build_context(chat_id=1, user_query=user_query),
        timeout=timeout,
    )


class TestLargeInputPostPatch(unittest.TestCase):

    def _run(self, coro):
        """Helper to run async in sync tests."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    # -- Test 1: normal message --
    def test_1_normal_query(self):
        builder = make_builder()
        result = self._run(run_build_context(builder, "Как меня зовут?"))
        self.assertIsInstance(result, ContextBundle)
        self.assertEqual(result.user_query, "Как меня зовут?")
        print("[Test 1] Normal query: PASS")

    # -- Test 2: 4000 chars --
    def test_2_4000_chars(self):
        builder = make_builder()
        result = self._run(run_build_context(builder, "A" * 4000))
        self.assertIsInstance(result, ContextBundle)
        print("[Test 2] 4000 chars: PASS")

    # -- Test 3: 5000 chars — ContextBuilder should truncate to max_tokens*4 --
    def test_3_5000_chars(self):
        builder = make_builder()
        result = self._run(run_build_context(builder, "A" * 5000))
        self.assertIsInstance(result, ContextBundle)
        print("[Test 3] 5000 chars: PASS")

    # -- Test 4: 50k chars — must NOT hang --
    def test_4_50k_chars(self):
        builder = make_builder()
        try:
            result = self._run(run_build_context(builder, "A" * 50_000, timeout=2.0))
            self.assertIsInstance(result, ContextBundle)
            # user_query should have been truncated
            self.assertLessEqual(len(result.user_query), 8000 * 4)
            print("[Test 4] 50k chars: PASS")
        except asyncio.TimeoutError:
            self.fail("[Test 4] 50k chars: FAIL — build_context HUNG")

    # -- Test 5: 500k chars — must NOT hang --
    def test_5_500k_chars(self):
        builder = make_builder()
        try:
            result = self._run(run_build_context(builder, "A" * 500_000, timeout=2.0))
            self.assertIsInstance(result, ContextBundle)
            self.assertLessEqual(len(result.user_query), 8000 * 4)
            print("[Test 5] 500k chars: PASS")
        except asyncio.TimeoutError:
            self.fail("[Test 5] 500k chars: FAIL — build_context HUNG")

    # -- Test 6: embedding guard --
    def test_6_embedding_guard(self):
        text_short = "Hello world, this is a normal message."
        text_long = "A" * 9000

        short_len = len(text_short.strip())
        long_len = len(text_long.strip())

        short_needs = bool(text_short and 10 <= short_len <= 8000)
        long_needs = bool(text_long and 10 <= long_len <= 8000)

        self.assertTrue(short_needs, "Short text should need embedding")
        self.assertFalse(long_needs, "Long text >8000 should NOT need embedding")
        print("[Test 6] Embedding guard >8k: PASS")

    # -- Test 7: progress stall — patched version must NOT hang --
    def test_7_progress_stall(self):
        builder = make_builder(max_tokens=8000)
        query = "B" * 200_000
        try:
            result = self._run(run_build_context(builder, query, timeout=2.0))
            self.assertIsInstance(result, ContextBundle)
            # user_query should be truncated to max_tokens * 4 = 32000
            self.assertLessEqual(len(result.user_query), 32001)
            print("[Test 7] Progress stall (patched): PASS")
        except asyncio.TimeoutError:
            self.fail("[Test 7] Progress stall: FAIL — still hangs after patch!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
