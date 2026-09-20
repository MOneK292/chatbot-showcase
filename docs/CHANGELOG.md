# Changelog

Все значимые изменения проекта будут задокументированы в этом файле.

## 2026-08-11

### Added
- Инициализация проекта.
- Создана структура директорий (app, config, docs, scripts, tests).
- Настроена конфигурация `.env.example`.
- Написаны базовые файлы документации (PROJECT, ARCHITECTURE, ROADMAP, DECISIONS, PROBLEMS, SERVER_BASELINE).
- Сформирован `requirements.txt` с точными точечно зафиксированными версиями (`==`).
- Написаны базовые тесты проверки окружения (`tests/unit/test_foundation.py`).
- Базовая инициализация git-репозитория и `.gitignore`.

### Changed
- Заменен устаревший пакет `google-generativeai` на актуальный официальный `google-genai` SDK (v2.17.0).
- Зафиксированы точные версии всех зависимостей в `requirements.txt`.
