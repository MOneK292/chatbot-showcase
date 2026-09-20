def test_foundation_environment():
    """Проверка базовой корректности окружения и импорта ключевых пакетов."""
    import aiogram
    import sqlalchemy
    import alembic
    import redis
    import google.genai
    import pydantic

    assert aiogram.__version__ is not None
    assert sqlalchemy.__version__ is not None
    assert alembic.__version__ is not None
    assert redis.__version__ is not None
    assert pydantic.__version__ is not None
