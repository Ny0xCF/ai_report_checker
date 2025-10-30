import io
import os
from pathlib import Path

import discord
from discord.ext import commands

from src.bot.ai_client import AIClient
from src.bot.sessions import UserSession
from src.bot.views import ReportView
from src.utils import logger

logger = logger.get_logger("Handlers")

START_CHANNEL_NAME = os.getenv("START_CHANNEL_NAME")
sessions = {}

base_dir = Path(__file__).resolve().parent.parent
client = AIClient(
    env_path=base_dir / ".env",
    prompt_path=base_dir / "prompts/arrest_report.txt",
)


async def setup_start_message(bot: commands.Bot):
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=START_CHANNEL_NAME)
        if not channel:
            continue

        async for msg in channel.history(limit=20):
            if msg.author == bot.user:
                await msg.delete()
                break

        view = discord.ui.View()
        start_button = discord.ui.Button(label="Начать проверку", style=discord.ButtonStyle.primary)

        async def start_callback(interaction: discord.Interaction):
            user = interaction.user
            await interaction.response.send_message("Я написал тебе в ЛС - проверь сообщения", ephemeral=True)
            await user.send(
                "Привет! Отправь сюда ТЕЛО отчета **текстом** или **.txt-файлом**\n"
                "⚠️ Только ТЕЛО, без какого-либо оформления и кода"
            )
            sessions[user.id] = UserSession(user_id=user.id)
            logger.info(f"Создана новая сессия для {user.name}")

        start_button.callback = start_callback
        view.add_item(start_button)

        embed = discord.Embed(
            title="Ассистент для проверки отчетов",
            description=(
                "Я - бот, который использует ИИ для проверки отчетов. Ты можешь использовать меня, "
                "чтобы выполнить самопроверку перед публикацией отчета. Это должно снизить количество "
                "вопросов как у твоего супервайзера, так и ОВР\n\n"

                "⚠️ Учти, что я не совершенен и иногда могу давать неправильные рекомендации. "
                "Воспринимай мои замечания как рекомендации к исправлению, а не как требования. "
                "Пользуйся принципом 'доверяй, но проверяй'\n\n"

                "⚠️ Также обрати внимание, что использование меня для проверки не снимает обязанностей "
                "с супервайзеров. Ты все так же должен опубликовать отчет в соответствующем канале, "
                "а они его проверить\n\n"

                "ℹ️ Если ты столкнулся с неправильными или странными рекомендациями, "
                "хочешь предложить улучшения или получить помощь - напиши в ЛС <@337950212016439327>\n\n"
                "Если ты все прочитал и готов начать, то нажми на кнопку ниже, чтобы приступить к проверке"
            ),
            color=0x3498db
        )
        embed.set_image(url="https://i.ibb.co/MxKqyByh/Ai-Report-Helper.png")
        await channel.send(embed=embed, view=view)


async def handle_dm(message: discord.Message):
    if message.author.bot:
        return

    session = sessions.get(message.author.id)
    if not session or not session.can_check():
        await message.channel.send("⚠️ У тебя нет активной сессии. "
                                   "Перейди в канал с интерфейсом бота и нажми на кнопку")
        return

    if session.processing:
        await message.channel.send("⏳ Отчет уже отправлен. Подожди окончания текущей проверки")
        return

    if message.attachments:
        file = message.attachments[0]
        if not file.filename.endswith(".txt"):
            await message.channel.send("❌ Пришли файл в .txt формате")
            return
        content = (await file.read()).decode("utf-8")
    else:
        content = message.content.strip()

    if not content:
        await message.channel.send("⚠️ Не удалось прочитать отчет. Попробуй еще раз")
        return

    session.processing = True
    processing_msg = await message.channel.send("Я анализирую твой отчет. Мне потребуется некоторое время. "
                                                "Я пришлю тебе сообщение, когда закончу")

    try:
        session.add_user_message(content)
        result = await client.query(content, history=session.chat_history)
        session.last_result = result
        session.add_assistant_message(result.corrected_report)
        session.checks_remaining -= 1

        file_bytes = io.BytesIO(result.corrected_report.encode("utf-8"))
        discord_file = discord.File(file_bytes, filename="corrected_report.txt")

        view = ReportView(result, session)
        embed = view.make_embed()
        await message.channel.send(embed=embed, file=discord_file, view=view)

    except Exception as e:
        logger.exception("Ошибка при проверке отчёта")
        await processing_msg.edit(content=f"❌ Ошибка при проверке: {e}")
    finally:
        session.processing = False

    if session.checks_remaining <= 0:
        session.active = False
        await message.channel.send("🚫 Лимит проверок исчерпан. Сессия завершена. "
                                   "Перейди в канал с интерфейсом бота и нажми на кнопку, чтобы начать новую")
