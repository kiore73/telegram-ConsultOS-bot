# VERSION 18: Final, simplified, and corrected seeding logic
print("---> RUNNING MAIN.PY VERSION 18 ---")
import asyncio
import logging
import sys
import time
# from urllib.parse import urlparse
# import json

# from aiogram import Bot, Dispatcher, types
# from aiogram.enums import ParseMode
# from aiogram.client.bot import DefaultBotProperties
# from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
# from aiohttp import web
# from sqlalchemy import select
# from yookassa.domain.notification import WebhookNotificationFactory, WebhookNotification

# from .config import settings
# from .database.models import Base, Questionnaire, Question, QuestionLogic, User, Payment
# from .database.session import async_engine, async_session_maker
# from .handlers import start, tariff, payment, questionnaire, booking, admin
# from .middlewares.db import DbSessionMiddleware
# from .services.questionnaire_service import questionnaire_service

logging.basicConfig(level=logging.INFO, stream=sys.stdout)


#
#
# --- ALL BOT LOGIC IS TEMPORARILY DISABLED FOR DIAGNOSTICS ---
#
#

def main() -> None:
    """
    Diagnostic main function.
    Prints a message every 10 seconds to test if the container is running.
    """
    print("--- DIAGNOSTIC MODE ---")
    print("--- If you see this, the Python interpreter is working. ---")
    
    count = 0
    while True:
        print(f"[{time.ctime()}] Hello from container! Process is alive. Loop count: {count}")
        time.sleep(10)
        count += 1


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Diagnostic script stopped.")
