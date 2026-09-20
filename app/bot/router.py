from aiogram import Router
from app.bot.handlers.messages import router as messages_router
from app.bot.handlers.admin import router as admin_router

main_router = Router()
main_router.include_router(admin_router)
main_router.include_router(messages_router)
