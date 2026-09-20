import os
from app.importer.json_adapter import TelegramDesktopJSONAdapter

def test_telegram_desktop_json_adapter():
    fixture_path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample_telegram_export.json")
    adapter = TelegramDesktopJSONAdapter()
    messages = list(adapter.parse_messages(fixture_path))
    
    assert len(messages) == 3
    
    m1 = messages[0]
    assert m1.telegram_message_id == 101
    assert m1.first_name == "Alice"
    assert m1.last_name == "Smith"
    assert m1.telegram_user_id == 11111
    assert m1.text == "Hello group! Is anyone working on Stage 1?"
    assert m1.telegram_reply_to_message_id is None

    m2 = messages[1]
    assert m2.telegram_message_id == 102
    assert m2.first_name == "Bob"
    assert m2.last_name == "Jones"
    assert m2.telegram_user_id == 22222
    assert m2.telegram_reply_to_message_id == 101

    m3 = messages[2]
    assert m3.telegram_message_id == 103
    assert m3.telegram_reply_to_message_id == 102
