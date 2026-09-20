import sys
import argparse
import asyncio
import os
from datetime import datetime
from typing import Set, Optional

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.importer.json_adapter import TelegramDesktopJSONAdapter
from app.services.messages import MessageService
from app.database.session import AsyncSessionLocal, init_db

async def run_import(file_path: str, dry_run: bool = False, batch_size: int = 100):
    if not os.path.exists(file_path):
        print(f"Error: File not found at '{file_path}'")
        sys.exit(1)

    adapter = TelegramDesktopJSONAdapter()
    fetched_count = 0
    inserted_count = 0
    skipped_count = 0
    error_count = 0
    users_seen: Set[int] = set()
    min_date: Optional[datetime] = None
    max_date: Optional[datetime] = None

    print(f"Starting history import from: {file_path}")
    if dry_run:
        print("=== DRY RUN MODE ACTIVE (No database changes will be saved) ===")

    messages_to_process = list(adapter.parse_messages(file_path))
    fetched_count = len(messages_to_process)

    if dry_run:
        for norm in messages_to_process:
            if norm.telegram_user_id:
                users_seen.add(norm.telegram_user_id)
            if min_date is None or norm.date < min_date:
                min_date = norm.date
            if max_date is None or norm.date > max_date:
                max_date = norm.date
            inserted_count += 1

        print("\n--- Dry Run Statistics ---")
        print(f"Fetched messages : {fetched_count}")
        print(f"Would insert     : {inserted_count}")
        print(f"Unique users     : {len(users_seen)}")
        print(f"Date range       : {min_date} -> {max_date}")
        return

    # Real DB import
    await init_db()
    async with AsyncSessionLocal() as session:
        service = MessageService(session)
        batch_processed = 0

        for norm in messages_to_process:
            try:
                if norm.telegram_user_id:
                    users_seen.add(norm.telegram_user_id)
                if min_date is None or norm.date < min_date:
                    min_date = norm.date
                if max_date is None or norm.date > max_date:
                    max_date = norm.date

                # Check if message already exists
                existing = await service.msg_repo.get_by_telegram_id(
                    chat_db_id=(await service.chat_repo.upsert_chat(
                        telegram_chat_id=norm.telegram_chat_id,
                        chat_type=norm.chat_type,
                        title=norm.chat_title
                    )).id,
                    telegram_message_id=norm.telegram_message_id
                )

                if existing:
                    skipped_count += 1
                else:
                    await service.save_normalized_message(norm)
                    inserted_count += 1

                batch_processed += 1
                if batch_processed >= batch_size:
                    await session.commit()
                    batch_processed = 0

            except Exception as e:
                error_count += 1
                print(f"Error processing message ID {norm.telegram_message_id}: {e}")

        await session.commit()

    print("\n--- Import Summary ---")
    print(f"Total fetched    : {fetched_count}")
    print(f"Total inserted   : {inserted_count}")
    print(f"Total skipped    : {skipped_count} (duplicates)")
    print(f"Total errors     : {error_count}")
    print(f"Unique users     : {len(users_seen)}")
    print(f"Date range       : {min_date} -> {max_date}")

def main():
    parser = argparse.ArgumentParser(description="Import Telegram Desktop JSON export history.")
    parser.add_argument("--file", required=True, help="Path to result.json export file")
    parser.add_argument("--dry-run", action="store_true", help="Run without persisting to DB")
    parser.add_argument("--batch-size", type=int, default=100, help="Commit batch size")
    args = parser.parse_args()

    asyncio.run(run_import(args.file, dry_run=args.dry_run, batch_size=args.batch_size))

if __name__ == "__main__":
    main()
