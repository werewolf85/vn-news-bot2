import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = set(int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x)
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "7"))