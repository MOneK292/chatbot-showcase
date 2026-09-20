import json
from datetime import datetime, timezone
from typing import Generator, Any, Dict, Optional
from app.importer.base import HistorySourceAdapter
from app.services.messages import NormalizedMessage

class TelegramDesktopJSONAdapter(HistorySourceAdapter):
    def parse_messages(self, source_path: str) -> Generator[NormalizedMessage, None, None]:
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chat_title = data.get("name")
        chat_type = data.get("type", "group")
        raw_chat_id = data.get("id", 0)
        # Ensure negative chat_id format for Telegram group/supergroup if positive in export
        telegram_chat_id = raw_chat_id if raw_chat_id < 0 else -raw_chat_id

        messages = data.get("messages", [])
        for item in messages:
            if item.get("type") != "message":
                continue  # skip service messages

            msg_id = item.get("id")
            if not msg_id:
                continue

            # Parse date
            date_str = item.get("date")
            date_unix = item.get("date_unixtime")
            if date_unix:
                msg_date = datetime.fromtimestamp(int(date_unix), tz=timezone.utc)
            elif date_str:
                msg_date = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
            else:
                msg_date = datetime.now(timezone.utc)

            # Parse user
            from_id_str = item.get("from_id", "")
            telegram_user_id: Optional[int] = None
            if isinstance(from_id_str, str) and from_id_str.startswith("user"):
                try:
                    telegram_user_id = int(from_id_str.replace("user", ""))
                except ValueError:
                    pass
            elif isinstance(from_id_str, int):
                telegram_user_id = from_id_str

            from_name = item.get("from", "")
            first_name = from_name
            last_name = None
            if " " in from_name:
                parts = from_name.split(" ", 1)
                first_name, last_name = parts[0], parts[1]

            # Parse text (can be str or list of formatted objects)
            raw_text = item.get("text", "")
            text = ""
            if isinstance(raw_text, str):
                text = raw_text
            elif isinstance(raw_text, list):
                text_parts = []
                for part in raw_text:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                text = "".join(text_parts)

            # Reply to ID
            reply_to_id = item.get("reply_to_message_id")
            if reply_to_id == 0:
                reply_to_id = None

            # Edited
            edited_str = item.get("edited")
            is_edited = bool(edited_str)
            edited_at = None
            if edited_str:
                try:
                    edited_at = datetime.fromisoformat(edited_str).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            # Detect message type
            media_type = "text"
            if item.get("photo"):
                media_type = "photo"
            elif item.get("file"):
                media_type = "document"
            elif item.get("sticker"):
                media_type = "sticker"

            is_forward = "forwarded_from" in item

            yield NormalizedMessage(
                telegram_message_id=msg_id,
                telegram_chat_id=telegram_chat_id,
                chat_type=chat_type,
                date=msg_date,
                telegram_user_id=telegram_user_id,
                username=None,
                first_name=first_name,
                last_name=last_name,
                is_bot=False,
                chat_title=chat_title,
                chat_username=None,
                text=text,
                telegram_reply_to_message_id=reply_to_id,
                edited_at=edited_at,
                message_type=media_type,
                is_forward=is_forward,
                is_edited=is_edited,
                raw_metadata={"telegram_export_id": msg_id}
            )
