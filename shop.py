import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import FSInputFile
from telethon import TelegramClient
from dotenv import load_dotenv

# --- КОНФИГУРАЦИЯ ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
TON_WALLET = os.getenv("TON_WALLET")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_NAME = "sifon_market.db"

# Хранилище для активных сессий юзерботов (чтобы не перезаходить)
active_clients = {}

class ShopStates(StatesGroup):
    wait_bal_id = State()
    wait_bal_amount = State()
    wait_acc_file = State()
    wait_acc_price = State()
    wait_acc_geo = State()
    wait_acc_stay = State()
    wait_acc_type = State()
    wait_broadcast_text = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            balance REAL DEFAULT 0,
            referrer_id INTEGER DEFAULT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            phone TEXT, price REAL, session_path TEXT, 
            geo TEXT, stay TEXT, type TEXT, is_sold INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, product_id INTEGER)""")
        await db.commit()

# --- КЛАВИАТУРЫ ---
def main_kb(user_id):
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🛒 Купить аккаунты"), types.KeyboardButton(text="👤 Профиль"))
    builder.row(types.KeyboardButton(text="💰 Пополнить баланс"), types.KeyboardButton(text="🔐 Получить код"))
    builder.row(types.KeyboardButton(text="👥 Реферальная система"), types.KeyboardButton(text="📜 История операций"))
    builder.row(types.KeyboardButton(text="🏆 Топ покупателей"), types.KeyboardButton(text="📋 Информация"))
    builder.row(types.KeyboardButton(text="🆘 Поддержка"))
    
    if user_id == ADMIN_ID:
        builder.row(types.KeyboardButton(text="➕ Добавить товар"), types.KeyboardButton(text="💎 Выдать баланс"))
        builder.row(types.KeyboardButton(text="📢 Рассылка"))
    return builder.as_markup(resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    ref_id = None
    if command.args and command.args.isdigit():
        ref_id = int(command.args)
        if ref_id == message.from_user.id: ref_id = None

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (message.from_user.id,))
        if not await cursor.fetchone():
            await db.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (message.from_user.id, ref_id))
            await db.commit()

    welcome_text = (
        "👋 **Добро пожаловать в Sifon Market!**\n\n"
        "🛒 Покупайте качественные аккаунты.\n"
        "💰 Пополнение баланса: TON.\n"
        "👥 Реферальная система: 10% с покупок друзей.\n\n"
        "Выберите действие ниже:"
    )
    await message.answer(welcome_text, reply_markup=main_kb(message.from_user.id), parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        row = await cursor.fetchone()
    await message.answer(f"👤 **Ваш профиль**\n\n🆔 ID: `{message.from_user.id}`\n💰 Баланс: **{row[0]} TON**", parse_mode="Markdown")

@dp.message(F.text == "💰 Пополнить баланс")
async def topup(message: types.Message):
    text = (
        "💎 **Пополнение через TON**\n\n"
        f"📍 Адрес кошелька:\n`{TON_WALLET}`\n\n"
        f"💬 **ОБЯЗАТЕЛЬНЫЙ комментарий:**\n`{message.from_user.id}`\n\n"
        "⚠️ Если не указать ID в комментарии, баланс не начислится!"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👥 Реферальная система")
async def referral(message: types.Message):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={message.from_user.id}"
    await message.answer(f"👥 **Ваша ссылка:**\n`{link}`\n\n🎁 Вы получаете 10% от каждой покупки вашего друга!", parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def support(message: types.Message):
    await message.answer("🆘 По всем вопросам: @zyozp")

# --- ПОКУПКА ---
@dp.message(F.text == "🛒 Купить аккаунты")
async def shop(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")
        cats = await cursor.fetchall()
    
    if not cats: return await message.answer("📦 Товаров нет в наличии.")
    
    kb = InlineKeyboardBuilder()
    for geo, count in cats:
        kb.row(types.InlineKeyboardButton(text=f"📍 {geo} ({count} шт.)", callback_data=f"cat_{geo}"))
    await message.answer("📁 **Выберите локацию:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def show_items(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, type, stay, price FROM products WHERE geo = ? AND is_sold = 0", (geo,))
        items = await cursor.fetchall()
    
    kb = InlineKeyboardBuilder()
    for i in items:
        kb.row(types.InlineKeyboardButton(text=f"⚙️ {i[1]} | ⏳ {i[2]} | 💵 {i[3]} TON", callback_data=f"buy_{i[0]}"))
    await callback.message.edit_text(f"📱 **Аккаунты {geo}:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT price, session_path, phone FROM products WHERE id = ?", (pid,))
        prod = await cursor.fetchone()
        cursor = await db.execute("SELECT balance, referrer_id FROM users WHERE user_id = ?", (callback.from_user.id,))
        user = await cursor.fetchone()

        if user[0] >= prod[0]:
            # Списание и начисление реферальных
            await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (prod[0], callback.from_user.id))
            if user[1]: # Если есть реферер
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (prod[0] * 0.1, user[1]))
            
            await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (pid,))
            await db.execute("INSERT INTO purchases (user_id, product_id) VALUES (?, ?)", (callback.from_user.id, pid))
            await db.commit()
            
            await callback.message.answer(f"✅ **Успешная покупка!**\n📱 Номер: `{prod[2]}`\nФайл выдан ниже.", parse_mode="Markdown")
            await callback.message.answer_document(FSInputFile(prod[1]))
        else:
            await callback.answer("❌ Недостаточно TON на балансе.", show_alert=True)

# --- ЛОГИКА КОДОВ (ЮЗЕРБОТ) ---
@dp.message(F.text == "🔐 Получить код")
async def get_code_list(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT pr.id, pr.phone FROM purchases p 
            JOIN products pr ON p.product_id = pr.id 
            WHERE p.user_id = ?""", (message.from_user.id,))
        rows = await cursor.fetchall()
    
    if not rows: return await message.answer("🛍 У вас еще нет покупок.")
    
    kb = InlineKeyboardBuilder()
    for r in rows: kb.row(types.InlineKeyboardButton(text=f"📱 {r[1]}", callback_data=f"getcode_{r[0]}"))
    await message.answer("🔐 **Выберите аккаунт для получения кода:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("getcode_"))
async def fetch_code(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT session_path, phone FROM products WHERE id = ?", (pid,))
        prod = await cursor.fetchone()
    
    path = prod[0]
    if path not in active_clients:
        client = TelegramClient(path, API_ID, API_HASH)
        await client.connect()
        active_clients[path] = client
    else:
        client = active_clients[path]

    try:
        msgs = await client.get_messages(777000, limit=1)
        if msgs:
            await callback.message.answer(f"📩 **Код для {prod[1]}:**\n`{msgs[0].message}`", parse_mode="Markdown")
        else:
            await callback.answer("⏳ Код еще не пришел...", show_alert=True)
    except:
        await callback.message.answer("❌ Ошибка сессии — обратитесь к @zyozp")

# --- АДМИНКА ---
@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def broadcast(message: types.Message, state: FSMContext):
    await message.answer("📝 Введите текст рассылки:")
    await state.set_state(ShopStates.wait_broadcast_text)

@dp.message(ShopStates.wait_broadcast_text)
async def broadcast_send(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        users = await cursor.fetchall()
    for u in users:
        try: await bot.send_message(u[0], message.text)
        except: pass
    await message.answer("✅ Готово!")
    await state.clear()

@dp.message(F.text == "➕ Добавить товар", F.from_user.id == ADMIN_ID)
async def add_item(message: types.Message, state: FSMContext):
    await message.answer("📎 Отправьте .session файл:")
    await state.set_state(ShopStates.wait_acc_file)

@dp.message(ShopStates.wait_acc_file, F.document)
async def add_file(message: types.Message, state: FSMContext):
    path = f"sessions/{message.document.file_name}"
    await bot.download(message.document, destination=path)
    await state.update_data(path=path, phone=message.document.file_name.replace(".session", ""))
    await message.answer("💰 Цена (TON):")
    await state.set_state(ShopStates.wait_acc_price)

@dp.message(ShopStates.wait_acc_price)
async def add_price(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await message.answer("🌍 Гео (например: Индонезия):")
    await state.set_state(ShopStates.wait_acc_geo)

@dp.message(ShopStates.wait_acc_geo)
async def add_geo(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text)
    await message.answer("⏳ Отлега:")
    await state.set_state(ShopStates.wait_acc_stay)

@dp.message(ShopStates.wait_acc_stay)
async def add_stay(message: types.Message, state: FSMContext):
    await state.update_data(stay=message.text)
    await message.answer("🛠 Тип:")
    await state.set_state(ShopStates.wait_acc_type)

@dp.message(ShopStates.wait_acc_type)
async def add_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, session_path, geo, stay, type) VALUES (?, ?, ?, ?, ?, ?)",
                         (data['phone'], data['price'], data['path'], data['geo'], data['stay'], message.text))
        await db.commit()
    await message.answer("✅ Товар добавлен!")
    await state.clear()

@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
async def give_bal(message: types.Message, state: FSMContext):
    await message.answer("Введите ID пользователя:")
    await state.set_state(ShopStates.wait_bal_id)

@dp.message(ShopStates.wait_bal_id)
async def bal_id(message: types.Message, state: FSMContext):
    await state.update_data(uid=message.text)
    await message.answer("Сколько TON начислить?")
    await state.set_state(ShopStates.wait_bal_amount)

@dp.message(ShopStates.wait_bal_amount)
async def bal_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(message.text), data['uid']))
        await db.commit()
    await message.answer("✅ Баланс пополнен!")
    await state.clear()

async def main():
    if not os.path.exists("sessions"): os.makedirs("sessions")
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
