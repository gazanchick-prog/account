import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

# --- БЕЗОПАСНОСТЬ: Подгружаем скрытые токены ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_NAME = "sifon_market.db"

# --- БАЗА ДАННЫХ ---
async def init_db():
    """Создаем таблицы, если их нет"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0,
                referrer_id INTEGER
            )
        """)
        await db.commit()

async def add_user(user_id: int, referrer_id: int = None):
    """Регистрация нового пользователя с учетом реферала"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if await cursor.fetchone() is None:
            # Юзер новый, добавляем
            await db.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
            await db.commit()
            
            # Если есть реферал, уведомляем его
            if referrer_id and referrer_id != user_id:
                try:
                    await bot.send_message(referrer_id, "🎉 По вашей ссылке зарегистрировался новый пользователь! Вы будете получать 10% от его пополнений.")
                except Exception:
                    pass # Реферал мог заблокировать бота

async def add_balance_and_reward_referrer(user_id: int, amount: float):
    """Начисление баланса и выдача 10% рефералу (например, при оплате TON или Stars)"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Пополняем баланс самому юзеру
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        
        # Ищем, кто его пригласил
        cursor = await db.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        
        if row and row[0]:
            referrer_id = row[0]
            reward = amount * 0.10 # Те самые 10%
            # Начисляем 10% рефералу
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, referrer_id))
            try:
                await bot.send_message(referrer_id, f"💸 Ваш реферал совершил покупку! Вам начислено 10%: **{reward:.2f}** на баланс.")
            except Exception:
                pass
        await db.commit()

# --- ЛОГИКА БОТА ---

@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    # Ловим реферальный ID из ссылки (например: t.me/bot?start=123456)
    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)
    
    # Регистрируем пользователя
    await add_user(message.from_user.id, referrer_id)
    
    # Клавиатура
    kb = [
        [types.KeyboardButton(text="🛒 Каталог аккаунтов"), types.KeyboardButton(text="👤 Мой профиль")],
        [types.KeyboardButton(text="💎 Пополнить TON"), types.KeyboardButton(text="🌟 Пополнить Stars")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    
    await message.answer(
        f"Добро пожаловать в **SifonMarket**! 🚀\n\n"
        f"Здесь лучшие Telegram-аккаунты и сессии.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.message(F.text == "👤 Мой профиль")
async def profile_handler(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"

    text = (
        f"👤 **Ваш профиль:**\n\n"
        f"💰 **Баланс:** {balance:.2f} руб/TON/Stars\n"
        f"🔗 **Ваша реферальная ссылка:**\n`{ref_link}`\n\n"
        f"_(Делитесь ссылкой с друзьями и получайте 10% от их пополнений прямо на свой баланс!)_"
    )
    await message.answer(text, parse_mode="Markdown")

# --- Имитация пополнения для теста рефералки ---
@dp.message(F.text == "💎 Пополнить TON")
async def test_replenish(message: types.Message):
    # В реальном проекте здесь будет интеграция с Toncenter или CryptoBot
    # Для теста просто имитируем успешное пополнение на 100 единиц
    amount = 100.0 
    await add_balance_and_reward_referrer(message.from_user.id, amount)
    await message.answer(f"✅ Баланс успешно пополнен на {amount}! (Тестовый режим)")

async def main():
    await init_db()
    print("Бот запущен, БД инициализирована!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())





BOT_TOKEN=123456789:ABCDefGHIjklMNOPQrsTUVwxyz
ADMIN_ID=123456789
API_ID=123456
API_HASH=abcdef1234567890
python
import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

# --- БЕЗОПАСНОСТЬ: Подгружаем скрытые токены ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_NAME = "sifon_market.db"

# --- БАЗА ДАННЫХ ---
async def init_db():
    """Создаем таблицы, если их нет"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0,
                referrer_id INTEGER
            )
        """)
        await db.commit()

async def add_user(user_id: int, referrer_id: int = None):
    """Регистрация нового пользователя с учетом реферала"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if await cursor.fetchone() is None:
            # Юзер новый, добавляем
            await db.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
            await db.commit()
            
            # Если есть реферал, уведомляем его
            if referrer_id and referrer_id != user_id:
                try:
                    await bot.send_message(referrer_id, "🎉 По вашей ссылке зарегистрировался новый пользователь! Вы будете получать 10% от его пополнений.")
                except Exception:
                    pass # Реферал мог заблокировать бота

async def add_balance_and_reward_referrer(user_id: int, amount: float):
    """Начисление баланса и выдача 10% рефералу (например, при оплате TON или Stars)"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Пополняем баланс самому юзеру
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        
        # Ищем, кто его пригласил
        cursor = await db.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        
        if row and row[0]:
            referrer_id = row[0]
            reward = amount * 0.10 # Те самые 10%
            # Начисляем 10% рефералу
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, referrer_id))
            try:
                await bot.send_message(referrer_id, f"💸 Ваш реферал совершил покупку! Вам начислено 10%: **{reward:.2f}** на баланс.")
            except Exception:
                pass
        await db.commit()

# --- ЛОГИКА БОТА ---

@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    # Ловим реферальный ID из ссылки (например: t.me/bot?start=123456)
    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)
    
    # Регистрируем пользователя
    await add_user(message.from_user.id, referrer_id)
    
    # Клавиатура
    kb = [
        [types.KeyboardButton(text="🛒 Каталог аккаунтов"), types.KeyboardButton(text="👤 Мой профиль")],
        [types.KeyboardButton(text="💎 Пополнить TON"), types.KeyboardButton(text="🌟 Пополнить Stars")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    
    await message.answer(
        f"Добро пожаловать в **SifonMarket**! 🚀\n\n"
        f"Здесь лучшие Telegram-аккаунты и сессии.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.message(F.text == "👤 Мой профиль")
async def profile_handler(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"

    text = (
        f"👤 **Ваш профиль:**\n\n"
        f"💰 **Баланс:** {balance:.2f} руб/TON/Stars\n"
        f"🔗 **Ваша реферальная ссылка:**\n`{ref_link}`\n\n"
        f"_(Делитесь ссылкой с друзьями и получайте 10% от их пополнений прямо на свой баланс!)_"
    )
    await message.answer(text, parse_mode="Markdown")

# --- Имитация пополнения для теста рефералки ---
@dp.message(F.text == "💎 Пополнить TON")
async def test_replenish(message: types.Message):
    # В реальном проекте здесь будет интеграция с Toncenter или CryptoBot
    # Для теста просто имитируем успешное пополнение на 100 единиц
    amount = 100.0 
    await add_balance_and_reward_referrer(message.from_user.id, amount)
    await message.answer(f"✅ Баланс успешно пополнен на {amount}! (Тестовый режим)")

async def main():
    await init_db()
    print("Бот запущен, БД инициализирована!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
