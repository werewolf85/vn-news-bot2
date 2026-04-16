import logging
import sqlite3
from datetime import datetime
from pytz import timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    JobQueue,
    filters,
)

from deep_translator import GoogleTranslator
from profanity_check import predict_prob
from config import (
    BOT_TOKEN,
    ADMIN_IDS,
    NEWS_API_KEY,
    TIMEZONE_OFFSET,
)

# ---------- Логирование ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- База данных ----------
DB_PATH = "data/bot.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_vi TEXT,
                title_ru TEXT,
                content_vi TEXT,
                content_ru TEXT,
                image_url TEXT,
                published_at TEXT,
                posted INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                image_url TEXT,
                active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                warnings INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER,
                user_id INTEGER,
                text TEXT,
                created_at TEXT,
                FOREIGN KEY(news_id) REFERENCES news(id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );
            """
        )
        conn.commit()

# ---------- Утилиты ----------
def translate_to_ru(text: str) -> str:
    if not text:
        return ""
    try:
        return GoogleTranslator(source="auto", target="ru").translate(text)
    except Exception as e:
        logger.error(f"Ошибка перевода: {e}")
        return text   # fallback

def contains_profanity(text: str) -> bool:
    prob = predict_prob([text])[0]
    return prob > 0.5

def get_user_warnings(user_id: int) -> int:
    with get_db() as conn:
        cur = conn.execute("SELECT warnings FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return row["warnings"] if row else 0

def add_warning(user_id: int):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, warnings) VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET warnings = warnings + 1
            """,
            (user_id,),
        )
        conn.commit()

def set_banned(user_id: int, banned: int = 1):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, banned) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET banned = excluded.banned
            """,
            (user_id, banned),
        )
        conn.commit()

def is_banned(user_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return bool(row["banned"]) if row else False

# ---------- Получение новостей ----------
def fetch_vietnamese_news(limit: int = 20):
    """
    Пример: GNews API (бесплатный tier). Нужно указать язык 'vi' и страну 'VN'.
    Если используешь другой источник – замени эту функцию.
    """
    import requests
    url = "https://gnews.io/api/v4/top-headlines"
    params = {
        "token": NEWS_API_KEY,
        "lang": "vi",
        "country": "VN",
        "max": limit,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        articles = data.get("articles", [])
        news_list = []
        for art in articles:
            news_list.append(
                {
                    "title_vi": art.get("title", ""),
                    "content_vi": art.get("description", ""),
                    "image_url": art.get("image", ""),
                    "published_at": art.get("publishedAt", ""),
                }
            )
        return news_list
    except Exception as e:
        logger.error(f"Не удалось получить новости: {e}")
        return []

def store_news(news_items):
    with get_db() as conn:
        for item in news_items:
            title_ru = translate_to_ru(item["title_vi"])
            content_ru = translate_to_ru(item["content_vi"])
            conn.execute(
                """
                INSERT OR IGNORE INTO news
                (title_vi, title_ru, content_vi, content_ru, image_url, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item["title_vi"],
                    title_ru,
                    item["content_vi"],
                    content_ru,
                    item["image_url"],
                    item["publishedAt"],
                ),
            )
        conn.commit()

def get_unposted_news():
    with get_db() as conn:
        cur = conn.execute(
            "SELECT * FROM news WHERE posted=0 ORDER BY id LIMIT 4"
        )
        return [dict(row) for row in cur.fetchall()]

def mark_as_posted(news_ids):
    if not news_ids:
        return
    with get_db() as conn:
        qmarks = ",".join("?" for _ in news_ids)
        conn.execute(
            f"UPDATE news SET posted=1 WHERE id IN ({qmarks})",
            news_ids,
        )
        conn.commit()

# ---------- Реклама ----------
def get_active_ads():
    with get_db() as conn:
        cur = conn.execute("SELECT * FROM ads WHERE active=1")
        return [dict(row) for row in cur.fetchall()]

def add_ad(text: str, image_url: str = None):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO ads (text, image_url, active) VALUES (?, ?, 1)",
            (text, image_url),
        )
        conn.commit()

# ---------- Обработчики ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        f"Привет, {user.mention_html()}!\n"
        "Я новостной бот. Новости публикуются автоматически.\n"
        "Команды:\n"
        "/help – справка\n"
        "/addad <текст> [ссылка_на_картинку] – добавить рекламу (только для админов)\n"
        "/mywarn – посмотреть количество предупреждений\n"
        "Просто напиши свой комментарий под последней новостью – я проверю на мат."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные команды:\n"
        "/start – начать работу\n"
        "/help – эта справка\n"
        "/addad <текст> [ссылка] – добавить рекламный блок (админ)\n"
        "/mywarn – показать твои предупреждения\n"
        "Любое другое сообщение будет считаться комментарий к последней опубликованной новости."
    )

async def mywarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    warns = get_user_warnings(uid)
    await update.message.reply_text(f"У тебя {warns} предупреждение(й). При 2 – бан.")

async def add_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Эту команду могут использовать только администраторы.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /addad <текст> [ссылка_на_картинку]")
        return
    # если последний аргумент выглядит как URL – считаем его картинкой
    image_url = None
    if len(context.args) >= 2 and (context.args[-1].startswith("http")):
        image_url = context.args[-1]
        text = " ".join(context.args[:-1])
    else:
        text = " ".join(context.args)
    add_ad(text, image_url)
    await update.message.reply_text("Рекламный блок добавлен.")

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    if is_banned(uid):
        await update.message.reply_text("Вы забанены и не можете писать комментарии.")
        return
    text = update.message.text.strip()
    if not text:
        return
    if contains_profanity(text):
        warns = get_user_warnings(uid) + 1
        add_warning(uid)
        if warns >= 2:
            set_banned(uid, 1)
            await update.message.reply_text(
                "Обнаружен нецензурный язык. Это ваш второй предупреждение – вы забанены."
            )
        else:
            await update.message.reply_text(
                f"Обнаружен нецензурный язык. Это предупреждение #{warns}. При втором – бан."
            )
        return
    # иначе сохраняем комментарий к последней новости
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM news WHERE posted=1 ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            await update.message.reply_text("Пока нет опубликованных новостей для комментариев.")
            return
        news_id = row["id"]
        conn.execute(
            """
            INSERT INTO comments (news_id, user_id, text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (news_id, uid, text, datetime.now().isoformat()),
        )
        conn.commit()
    await update.message.reply_text("Комментарий сохранён. Спасибо!")

# ---------- Запланированная рассылка новостей ----------
async def post_news_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    tz = timezone(f"Etc/GMT-{TIMEZONE_OFFSET}")  # 주의: Etc/GMT-7 = UTC+7
    now = datetime.now(tz)
    # проверяем, что сейчас время рассылки (09:00, 12:00, 15:00, 18:00)
    allowed_hours = {9, 12, 15, 18}
    if now.hour not in allowed_hours:
        return  # выходим, если не время

    try:
        # 1) подтягиваем свежие новости и сохраняем в БД
        fresh = fetch_vietnamese_news(limit=30)
        if fresh:
            store_news(fresh)

        # 2) берем до 4 непопубликованных новостей
        to_post = get_unposted_news()
        if not to_post:
            logger.info("Нет новых новостей для публикации.")
            return

        ads = get_active_ads()
        chat_id = job.data.get("chat_id")
        if not chat_id:
            logger.warning("Chat ID не передан в job – публикация пропущена.")
            return

        for idx, news in enumerate(to_post):
            # формируем текст сообщения
            msg = f"<b>{news['title_ru']}</b>\n\n{news['content_ru']}"
            if news["image_url"]:
                msg += f"\n\n<a href='{news[\"image_url\"]}'>🖼️</a>"
            # после каждой новости, кроме последней, вставляем рекламу (если есть)
            if ads and idx < len(to_post) - 1:
                ad = ads[idx % len(ads)]
                ad_text = f"\n\n――― Реклама ―――\n{ad['text']}"
                if ad["image_url"]:
                    ad_text += f"\n<a href='{ad[\"image_url\"]}'>🖼️</a>"
                msg += ad_text

            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
        # помечаем как опубликованные
        posted_ids = [n["id"] for n in to_post]
        mark_as_posted(posted_ids)
        logger.info(f"Опубликовано {len(posted_ids)} новостей.")
    except Exception as e:
        logger.error(f"Ошибка в post_news_job: {e}")

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("mywarn", mywarn))
    application.add_handler(CommandHandler("addad", add_ad))

    # комментарии (любое текстовое сообщение, не являющееся командой)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment))

    # планировщик новостей
    job_queue: JobQueue = application.job_queue
    # передаём chat_id – будем брать его из первой команды /start или можно задать в .env
    # Для простоты сохраняем его в job.data после первого /start
    def store_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        # перезаписываем данные всех существующих_jobs
        for job in job_queue.get_jobs_by_name("news_post"):
            job.data = {"chat_id": chat_id}
        # если job ещё нет – создадим ниже с этим data
        application.bot_data["chat_id"] = chat_id

    # перехватываем любое сообщение, чтобы сохранить chat_id (простой способ)
    application.add_handler(MessageHandler(filters.ALL, store_chat_id))

    # создаём повторяющийся job, который будет проверять время каждый час
    job_queue.run_repeating(
        post_news_job,
        interval=3600,  # каждый час
        first=10,       # старт через 10 сек после запуска
        name="news_post",
        data={"chat_id": None},  # будет заполнено после первого сообщения
    )

    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    init_db()
    main()