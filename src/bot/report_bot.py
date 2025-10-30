import logging
import os

import discord
from discord.ext import commands

from src.bot.handlers import setup_start_message, handle_dm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("report-bot")

intents = discord.Intents.default()
intents.messages = True
intents.dm_messages = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info(f"Бот запущен как {bot.user}")
    await setup_start_message(bot)


@bot.event
async def on_message(message: discord.Message):
    if isinstance(message.channel, discord.DMChannel):
        await handle_dm(message)
    else:
        await bot.process_commands(message)


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN не найден в .env")
    bot.run(token)
