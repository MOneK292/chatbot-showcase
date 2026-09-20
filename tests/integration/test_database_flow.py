import pytest
import asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.database.models.base import Base
from app.services.messages import MessageService, NormalizedMessage

async def run_flow_test():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        service = MessageService(session)
        now = datetime.now(timezone.utc)

        # 1. Out-of-order insertion: Child message arrives FIRST (replies to parent msg 100 which is not yet in DB)
        child_norm = NormalizedMessage(
            telegram_message_id=101,
            telegram_chat_id=-100123456789,
            chat_type="supergroup",
            date=now,
            telegram_user_id=222,
            first_name="Bob",
            text="Reply to non-existent parent 100",
            telegram_reply_to_message_id=100
        )
        db_child = await service.save_normalized_message(child_norm)
        await session.commit()

        assert db_child.telegram_message_id == 101
        assert db_child.telegram_reply_to_message_id == 100
        assert db_child.reply_to_message_id is None  # Not resolved yet because parent is missing!

        # 2. Parent message 100 arrives SECOND
        parent_norm = NormalizedMessage(
            telegram_message_id=100,
            telegram_chat_id=-100123456789,
            chat_type="supergroup",
            date=now,
            telegram_user_id=111,
            first_name="Alice",
            text="Original parent message 100"
        )
        db_parent = await service.save_normalized_message(parent_norm)
        await session.commit()

        assert db_parent.telegram_message_id == 100

        # 3. Verify deferred resolution: db_child should now have reply_to_message_id == db_parent.id!
        await session.refresh(db_child)
        assert db_child.reply_to_message_id == db_parent.id

    await test_engine.dispose()

async def run_dedup_test():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        service = MessageService(session)
        now = datetime.now(timezone.utc)

        msg_norm = NormalizedMessage(
            telegram_message_id=500,
            telegram_chat_id=-100999999,
            chat_type="group",
            date=now,
            telegram_user_id=333,
            first_name="Charlie",
            text="Test deduplication"
        )

        # Save once
        msg1 = await service.save_normalized_message(msg_norm)
        await session.commit()
        id1 = msg1.id

        # Save identical message again
        msg2 = await service.save_normalized_message(msg_norm)
        await session.commit()
        id2 = msg2.id

        # Primary key must be identical (no duplicate row created)
        assert id1 == id2

    await test_engine.dispose()

def test_message_service_flow_and_out_of_order_replies():
    asyncio.run(run_flow_test())

def test_message_service_deduplication():
    asyncio.run(run_dedup_test())
