import unittest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# We will test the handle_incoming_message logic. We need to mock Bot, MessageService, ContextBuilder, GeminiService.
from aiogram.types import Message, Chat, User
from app.bot.handlers.messages import handle_incoming_message, active_generations
from datetime import datetime, timezone

class TestParallelMessages(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Clear active_generations before each test
        active_generations.clear()
        
        self.bot_mock = AsyncMock()
        
        # Mocks
        self.message_service_mock = AsyncMock()
        self.message_service_mock.process_aiogram_message.return_value = MagicMock(id=1)
        
        self.context_builder_mock = AsyncMock()
        self.context_builder_mock.build_context.return_value = MagicMock()
        
        self.gemini_service_mock = AsyncMock()
        self.gemini_service_mock.generate.return_value = "Mocked Response"
        
        # Patching
        self.patcher_session = patch('app.bot.handlers.messages.AsyncSessionLocal')
        self.mock_session_local = self.patcher_session.start()
        
        self.mock_session = AsyncMock()
        self.mock_session.commit = AsyncMock()
        self.mock_session_local.return_value.__aenter__.return_value = self.mock_session
        
        self.patcher_ms = patch('app.bot.handlers.messages.MessageService', return_value=self.message_service_mock)
        self.patcher_ms.start()
        
        self.patcher_cb = patch('app.bot.handlers.messages.ContextBuilder', return_value=self.context_builder_mock)
        self.patcher_cb.start()
        
        self.patcher_gs = patch('app.bot.handlers.messages.GeminiService', return_value=self.gemini_service_mock)
        self.patcher_gs.start()
        
        # Patch Bot context
        self.patcher_bc = patch('app.bot.handlers.messages.bot_context')
        self.mock_bc = self.patcher_bc.start()
        self.mock_bc.bot_username = "test_bot"
        self.mock_bc.bot_id = 123
        
        # Instead of mocking sleep completely, mock it to sleep for a tiny amount
        # so the typing loop doesn't spin infinitely and freeze the event loop.
        self.original_sleep = asyncio.sleep
        async def fast_sleep(delay, result=None):
            if delay == 4: # typer loop delay
                await self.original_sleep(0.01)
            else:
                await self.original_sleep(delay)
        
        self.patcher_sleep = patch('asyncio.sleep', side_effect=fast_sleep)
        self.patcher_sleep.start()

    async def asyncTearDown(self):
        self.patcher_session.stop()
        self.patcher_ms.stop()
        self.patcher_cb.stop()
        self.patcher_gs.stop()
        self.patcher_bc.stop()
        self.patcher_sleep.stop()
        
        # Cancel any pending tasks to avoid asyncio warnings
        for t in list(active_generations):
            if isinstance(t, asyncio.Task):
                t.cancel()

    def _create_message(self, text, message_id=1, chat_id=1, user_id=1):
        return Message(
            message_id=message_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=chat_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="Test"),
            text=text,
        )

    async def test_1_single_message(self):
        msg = self._create_message("Hello")
        await handle_incoming_message(msg, self.bot_mock)
        
        # Wait for tasks to finish
        tasks = list(active_generations)
        if tasks:
            await asyncio.gather(*tasks)
            
        self.bot_mock.send_message.assert_called_once()
        self.assertEqual(len(active_generations), 0)

    async def test_2_two_simultaneous_messages(self):
        msg1 = self._create_message("Message 1", message_id=1)
        msg2 = self._create_message("Message 2", message_id=2)
        
        # Both are handled sequentially in the aiogram loop but rapidly
        await handle_incoming_message(msg1, self.bot_mock)
        await handle_incoming_message(msg2, self.bot_mock)
        
        # Wait for whatever is active
        tasks = [t for t in active_generations if isinstance(t, asyncio.Task)]
        # We need to catch cancelled exceptions if they occur
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
                
        # We expect bot to have sent 2 messages if they run in parallel
        # Currently, msg1 will be cancelled, so only 1 message sent.
        self.assertEqual(self.bot_mock.send_message.call_count, 2, "Should have sent 2 responses")

    async def test_3_slow_and_fast_request(self):
        msg1 = self._create_message("Slow", message_id=1)
        msg2 = self._create_message("Fast", message_id=2)
        
        # Mock generate to be slow for msg1 and fast for msg2
        async def slow_fast_generate(session, chat_id, user_id, model, context):
            if context.user_query == "Slow":
                await asyncio.sleep(0.5)
                return "Slow Response"
            else:
                return "Fast Response"
                
        self.gemini_service_mock.generate.side_effect = slow_fast_generate
        
        await handle_incoming_message(msg1, self.bot_mock)
        await handle_incoming_message(msg2, self.bot_mock)
        
        tasks = [t for t in active_generations if isinstance(t, asyncio.Task)]
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
                
        # Expect bot.send_message to be called twice
        self.assertEqual(self.bot_mock.send_message.call_count, 2)
        
    async def test_4_exception_isolation(self):
        msg1 = self._create_message("Fail", message_id=1)
        msg2 = self._create_message("Pass", message_id=2)
        
        async def fail_pass_generate(session, chat_id, user_id, model, context):
            if context.user_query == "Fail":
                raise Exception("Test Failure")
            else:
                return "Pass Response"
                
        self.gemini_service_mock.generate.side_effect = fail_pass_generate
        
        await handle_incoming_message(msg1, self.bot_mock)
        await handle_incoming_message(msg2, self.bot_mock)
        
        tasks = [t for t in active_generations if isinstance(t, asyncio.Task)]
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
                
        # First one should send error message, second one normal message. Total 2.
        self.assertEqual(self.bot_mock.send_message.call_count, 2)

    async def test_6_ten_messages(self):
        msgs = [self._create_message(f"Message {i}", message_id=i) for i in range(10)]
        for msg in msgs:
            await handle_incoming_message(msg, self.bot_mock)
            
        tasks = [t for t in active_generations if isinstance(t, asyncio.Task)]
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
                
        self.assertEqual(self.bot_mock.send_message.call_count, 10)

if __name__ == '__main__':
    unittest.main()
