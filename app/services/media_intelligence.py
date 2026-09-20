import logging
import io
import asyncio
from typing import Optional, Dict, Any
from aiogram import Bot
from google import genai
from google.genai import types
import os
import time

logger = logging.getLogger(__name__)

# Global semaphore to limit concurrent transcriptions
_media_semaphore = asyncio.Semaphore(3)

class MediaIntelligenceService:
    def __init__(self, api_key: Optional[str] = None):
        self.client = genai.Client(api_key=api_key)
        self.model_name = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-lite")
        self.semaphore = _media_semaphore
        self.MAX_MEDIA_SIZE_MB = 20

    async def process_media_single_shot(self, bot: Bot, file_id: str, mime_type: str, file_size: Optional[int] = None) -> str:
        """
        Downloads a media file and performs BOTH STT and Summary in a single Gemini call.
        Returns ready-to-send formatted text with expandable blockquote and summary.
        """
        if file_size and file_size > self.MAX_MEDIA_SIZE_MB * 1024 * 1024:
            raise ValueError(f"Файл слишком большой. Максимальный размер: {self.MAX_MEDIA_SIZE_MB} МБ.")

        if self.semaphore.locked():
            raise RuntimeError("Сейчас выполняется слишком много расшифровок. Попробуйте через минуту.")

        async with self.semaphore:
            logger.info(f"[MEDIA_SINGLE_SHOT_START] file_id={file_id}")
            start_time = time.time()
            
            try:
                file_info = await bot.get_file(file_id)
                if getattr(file_info, "file_size", 0) > self.MAX_MEDIA_SIZE_MB * 1024 * 1024:
                    raise ValueError(f"Файл слишком большой. Максимальный размер: {self.MAX_MEDIA_SIZE_MB} МБ.")
                
                file_bytes = io.BytesIO()
                await bot.download_file(file_info.file_path, destination=file_bytes)
                file_data = file_bytes.getvalue()
            except ValueError:
                raise
            except Exception as e:
                logger.error(f"[MEDIA_ERROR] Failed to download file_id={file_id}: {e}")
                raise

            try:
                system_instruction = """Ты — модуль транскрибации и анализа голосовых и видеосообщений для Telegram.
ЗАДАЧА:
1. Сделай краткую выжимку переданного аудио/видео (тезисы, договоренности, задачи, важные факты, вопросы).
2. Выполни полную и точную расшифровку речи без цензуры, сохранив разговорный стиль.
3. Верни ответ СТРОГО в следующем формате:

📌 Кратко

• [Пункт 1]
• [Пункт 2]

📝 Расшифровка

<blockquote expandable>
[Полный текст расшифровки]
</blockquote>

ПРАВИЛА:
- Не используй markdown-кодовые блоки.
- Если в сообщении нет задач/дат/сумм, не выдумывай их.
- Если речь неразборчива, помечай как [неразборчиво].
- Не пиши никаких вступлений или пояснений от себя."""

                async def _call():
                    return await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=[
                            types.Part.from_bytes(data=file_data, mime_type=mime_type),
                            "Расшифруй и проанализируй это сообщение."
                        ],
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.3
                        )
                    )
                
                response = await asyncio.wait_for(_call(), timeout=120.0)
                text = response.text or ""
                latency = int((time.time() - start_time) * 1000)
                logger.info(f"[MEDIA_SINGLE_SHOT_DONE] file_id={file_id} length={len(text)} latency={latency}ms")
                return text.strip()
            except asyncio.TimeoutError:
                logger.error(f"[MEDIA_ERROR] Single shot timeout for file_id={file_id}")
                raise TimeoutError("Таймаут при обработке медиа (превышено 120 секунд).")
            except Exception as e:
                logger.error(f"[MEDIA_ERROR] Failed single-shot processing for file_id={file_id}: {e}")
                raise

    async def transcribe_media(self, bot: Bot, file_id: str, mime_type: str, file_size: Optional[int] = None) -> Dict[str, Any]:
        """
        Downloads a media file from Telegram and uses Gemini to transcribe it.
        """
        if file_size and file_size > self.MAX_MEDIA_SIZE_MB * 1024 * 1024:
            raise ValueError(f"Файл слишком большой. Максимальный размер: {self.MAX_MEDIA_SIZE_MB} МБ.")

        if self.semaphore.locked():
            raise RuntimeError("Сейчас выполняется слишком много расшифровок. Попробуйте через минуту.")

        async with self.semaphore:
            logger.info(f"[MEDIA_TRANSCRIBE_START] file_id={file_id}")
            start_time = time.time()
            
            # Download from Telegram
            try:
                file_info = await bot.get_file(file_id)
                # Fallback check if file_size wasn't provided directly
                if getattr(file_info, "file_size", 0) > self.MAX_MEDIA_SIZE_MB * 1024 * 1024:
                    raise ValueError(f"Файл слишком большой. Максимальный размер: {self.MAX_MEDIA_SIZE_MB} МБ.")
                
                file_bytes = io.BytesIO()
                await bot.download_file(file_info.file_path, destination=file_bytes)
                file_data = file_bytes.getvalue()
            except ValueError:
                raise
            except Exception as e:
                logger.error(f"[MEDIA_ERROR] Failed to download file_id={file_id}: {e}")
                raise

            # Transcribe with Gemini
            try:
                prompt = """Максимально точно расшифруй речь. 
Сохрани разговорный стиль, но убери явные ошибки распознавания.
Не используй markdown-кодовые блоки. Не используй обратные кавычки.
Не пиши пояснений от себя. Не пиши "Вот расшифровка".
Если речь эмоциональная или содержит мат, передавай смысл без цензуры.
Если речь неразборчива, помечай фрагмент как "[неразборчиво]"."""
                
                async def _call():
                    return await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=[
                            types.Part.from_bytes(data=file_data, mime_type=mime_type),
                            prompt
                        ]
                    )
                
                response = await asyncio.wait_for(_call(), timeout=120.0)
                text = response.text or ""
                
                latency = int((time.time() - start_time) * 1000)
                logger.info(f"[MEDIA_TRANSCRIBE_DONE] file_id={file_id} length={len(text)} latency={latency}ms size={len(file_data)}")
                return {
                    "text": text.strip(),
                    "duration_sec": 0
                }
            except asyncio.TimeoutError:
                logger.error(f"[MEDIA_ERROR] Transcription timeout for file_id={file_id}")
                raise TimeoutError("Таймаут при транскрибации (превышено 120 секунд).")
            except Exception as e:
                logger.error(f"[MEDIA_ERROR] Failed to transcribe file_id={file_id}: {e}")
                raise

    async def summarize_transcript(self, transcript: str, mode: str = "normal") -> str:
        """
        Generates a summary of the transcription.
        mode can be 'normal' or 'tasks'
        """
        if not transcript:
            return "Текст не распознан."
            
        logger_start = "[MEDIA_SUMMARY_START]" if mode == "normal" else "[MEDIA_TASKS_START]"
        logger_done = "[MEDIA_SUMMARY_DONE]" if mode == "normal" else "[MEDIA_TASKS_DONE]"
        
        logger.info(logger_start)
        start_time = time.time()
        
        try:
            if mode == "tasks":
                system_prompt = "Сделай выжимку только задач и договоренностей.\nФормат ответа строго:\n✅ Задачи\n- ...\n📅 Дедлайны\n- ...\n💰 Суммы\n- ...\n🤝 Договоренности\n- ...\n\nНичего лишнего. Если пункта нет, не выводи его заголовок."
            else:
                system_prompt = """Сделай краткую выжимку переданного текста.
Формат ответа СТРОГО:
• Основные мысли
• Договоренности
• Важные факты
• Вопросы
• Следующие действия

Если в сообщении нет задач, договоренностей, дат или сумм — просто не добавляй эти пункты.
Если текст в основном эмоциональный, бытовой или не содержит задач, не пиши фразы вроде "отсутствует конструктивная информация", "данные отсутствуют". Вместо этого кратко опиши смысл разговора обычным языком.
Не используй markdown-кодовые блоки. Не используй обратные кавычки. Не пиши пояснений от себя."""

            async def _call():
                return await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=transcript,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.3
                    )
                )

            response = await asyncio.wait_for(_call(), timeout=60.0)
            summary = response.text or "Не удалось сформировать резюме."
            
            latency = int((time.time() - start_time) * 1000)
            logger.info(f"{logger_done} latency={latency}ms")
            return summary.strip()
            
        except asyncio.TimeoutError:
            logger.error("[MEDIA_ERROR] Summary timeout")
            raise TimeoutError("Таймаут при суммаризации (превышено 60 секунд).")
        except Exception as e:
            logger.error(f"[MEDIA_ERROR] Failed to summarize transcript: {e}")
            raise
