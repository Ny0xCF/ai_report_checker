import os

from src.bot.report_bot import bot

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN не найден в .env")
    bot.run(token)
