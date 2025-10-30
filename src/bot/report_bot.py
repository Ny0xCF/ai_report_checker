import discord
from discord.ext import commands

from src.bot.handlers import setup_start_message, handle_dm
from src.utils import logger

logger = logger.get_logger("Bot")

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
