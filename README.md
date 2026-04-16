# Vietnam News Telegram Bot

This bot fetches Vietnamese news, translates them to Russian, and posts them to a Telegram channel/chat on a schedule (09:00, 12:00, 15:00, 18:00 GMT+7). It also allows admins to add advertising blocks between news items and lets users comment on news with profanity filtering (warning/ban system).

## Features

- Fetch Vietnamese news from a news API (e.g., GNews)
- Translate titles and content to Russian using Google Translate (free)
- Post up to 4 news items per scheduled time
- Advertising blocks (admin-only) inserted between news
- User comments with profanity detection (first warning, second ban)
- SQLite database for persistence
- Dockerized for easy deployment

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/werewolf85/vn-news-bot2.git
   cd vn-news-bot2
   ```

2. Create a `.env` file with the following variables:
   ```
   BOT_TOKEN=your_telegram_bot_token
   ADMIN_IDS=123456789,987654321   # comma-separated list of Telegram user IDs
   NEWS_API_KEY=your_news_api_key  # e.g., GNews API key
   TIMEZONE_OFFSET=7               # GMT+7 for Vietnam
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the bot:
   ```bash
   python bot.py
   ```

   Or using Docker:
   ```bash
   docker compose up --build -d
   ```

## Usage

- After the bot starts, send any message (e.g., `/start`) so it can store your chat ID.
- The bot will automatically post news at the scheduled times.
- Admins can add advertising blocks with the command:
  ```
  /addad <текст> [ссылка_на_картинку]
  ```
- Users can comment on the latest news by sending a message; the bot checks for profanity.
- Use `/mywarn` to check your warning count.

## License

MIT

