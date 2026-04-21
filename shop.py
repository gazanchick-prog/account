import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from telethon import TelegramClient
from dotenv import load_dotenv

# --- НАСТРОЙКИ ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TON_WALLET = os.getenv("TON_WALLET", "Кошелек не указан")
SUPPORT = "@zyozp"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_NAME = "sifon_market.db"

# --- СОСТОЯНИЯ ---
class AdminStates(StatesGroup):
    waiting_for_balance_id = State()
    waiting_for_balance_amount = State()
    waiting_for_broadcast = State()
    # Состояния добавления товара
    waiting_for_acc_file = State()
    waiting_for_acc_price = State()
    waiting_for_acc_geo = State()
    waiting_for_acc_stay = State()
    waiting_for_acc_type = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_flag(country_code):
    """Превращает 'RU' в 🇷🇺"""
    if not country_code or len(country_code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, referrer_id INTEGER)")
        await db.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            phone TEXT, price REAL, session_path TEXT, 
            geo TEXT, stay TEXT, type TEXT, is_sold INTEGER DEFAULT 0)""")
        await db.execute("CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER)")
        await db.commit()

# --- КЛАВИАТУРЫ ---
def main_kb(user_id):
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🛒 Купить"), types.KeyboardButton(text="🛍 Мои покупки"))
    builder.row(types.KeyboardButton(text="👤 Профиль"), types.KeyboardButton(text="💳 Пополнить"))
    builder.row(types.KeyboardButton(text="🆘 Поддержка"))
    if user_id == ADMIN_ID:
        builder.row(types.KeyboardButton(text="➕ Аккаунт"), types.KeyboardButton(text="💰 Выдать баланс"))
        builder.row(types.KeyboardButton(text="📢 Рассылка"))
    return builder.as_markup(resize_keyboard=True)

# --- ЛОГИКА ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    ref_id = int(command.args) if command.args and command.args.isdigit() else None
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, referrer_id) VALUES (?, ?)", (message.from_user.id, ref_id))
        await db.commit()
    await message.answer("👋 Добро пожаловать в SifonMarket!", reply_markup=main_kb(message.from_user.id))

@dp.message(F.text == "💳 Пополнить")
async def topup(message: types.Message):
    text = (
        f"💎 **Пополнение TON**\n\n"
        f"Переведите TON на адрес ниже.\n"
        f"Нажмите на адрес или комментарий, чтобы скопировать.\n\n"
        f"📍 Адрес:\n`{TON_WALLET}`\n\n"
        f"💬 Комментарий:\n`{message.from_user.id}`\n\n"
        f"⚠️ Без комментария баланс не зачислится!"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0
    bot_info = await bot.get_me()
    await message.answer(f"👤 **Профиль**\n🆔 ID: `{message.from_user.id}`\n💰 Баланс: **{balance} TON**\n\n🔗 Рефка: `https://t.me/{bot_info.username}?start={message.from_user.id}`", parse_mode="Markdown")

# --- ПОКУПКА ---
@dp.message(F.text == "🛒 Купить")
async def shop_list(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, geo, type, stay, price FROM products WHERE is_sold = 0")
        items = await cursor.fetchall()
    if not items: return await message.answer("Товаров нет 🫙")
    
    kb = InlineKeyboardBuilder()
    for item in items:
        flag = get_flag(item[1])
        btn_text = f"{flag} {item[2]} | {item[3]} | {item[4]} TON"
        kb.row(types.InlineKeyboardButton(text=btn_text, callback_data=f"buy_{item[0]}"))
    await message.answer("Выберите аккаунт:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT price, session_path, phone FROM products WHERE id = ?", (prod_id,))
        prod = await cursor.fetchone()
        cursor = await db.execute("SELECT balance, referrer_id FROM users WHERE user_id = ?", (callback.from_user.id,))
        user = await cursor.fetchone()

        if user[0] >= prod[0]:
            await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (prod[0], callback.from_user.id))
            await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (prod_id,))
            await db.execute("INSERT INTO purchases (user_id, product_id) VALUES (?, ?)", (callback.from_user.id, prod_id))
            await db.commit()
            
            # Выдача файла
            file = types.FSInputFile(prod[1])
            await callback.message.answer_document(file, caption=f"✅ Покупка завершена!\n📱 Номер: `{prod[2]}`")
        else:
            await callback.answer("Недостаточно TON!", show_alert=True)

# --- МОИ ПОКУПКИ (С ВЫДАЧЕЙ КОДА) ---
@dp.message(F.text == "🛍 Мои покупки")
async def my_purchases(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT p.id, pr.phone FROM purchases p JOIN products pr ON p.product_id = pr.id WHERE p.user_id = ?", (message.from_user.id,))
        items = await cursor.fetchall()
    if not items: return await message.answer("Пусто 🕸")
    
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.row(types.InlineKeyboardButton(text=f"📱 {item[1]} (Код)", callback_data=f"getcode_{item[0]}"))
    await message.answer("Твои аккаунты:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("getcode_"))
async def get_code(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT pr.session_path FROM purchases p JOIN products pr ON p.product_id = pr.id WHERE p.id = ?", (int(callback.data.split("_")[1]),))
        row = await cursor.fetchone()
    if row:
        await callback.answer("Запрашиваю код...")
        try:
            client = TelegramClient(row[0], API_ID, API_HASH)
            await client.connect()
            msgs = await client.get_messages(777000, limit=1)
            await callback.message.answer(f"📩 Код: `{msgs[0].message}`", parse_mode="Markdown")
            await client.disconnect()
        except Exception as e: await callback.message.answer(f"Ошибка сессии: {e}")

# --- АДМИНКА (ДОБАВЛЕНИЕ ПО ШАГАМ) ---
@dp.message(F.text == "➕ Аккаунт", F.from_user.id == ADMIN_ID)
async def add_acc_1(message: types.Message, state: FSMContext):
    await message.answer("Скинь файл .session")
    await state.set_state(AdminStates.waiting_for_acc_file)

@dp.message(AdminStates.waiting_for_acc_file, F.document)
async def add_acc_2(message: types.Message, state: FSMContext):
    path = f"sessions/{message.document.file_name}"
    await bot.download(message.document, destination=path)
    await state.update_data(path=path, phone=message.document.file_name.replace(".session", ""))
    await message.answer("Цена (TON):")
    await state.set_state(AdminStates.waiting_for_acc_price)

@dp.message(AdminStates.waiting_for_acc_price)
async def add_acc_3(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await message.answer("ГЕО (две буквы, напр. RU, US, UA):")
    await state.set_state(AdminStates.waiting_for_acc_geo)

@dp.message(AdminStates.waiting_for_acc_geo)
async def add_acc_4(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text.upper())
    await message.answer("Отлёга (напр. 30 дней):")
    await state.set_state(AdminStates.waiting_for_acc_stay)

@dp.message(AdminStates.waiting_for_acc_stay)
async def add_acc_5(message: types.Message, state: FSMContext):
    await state.update_data(stay=message.text)
    await message.answer("Тип (напр. Авторег / Фишинг):")
    await state.set_state(AdminStates.waiting_for_acc_type)

@dp.message(AdminStates.waiting_for_acc_type)
async def add_acc_6(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, session_path, geo, stay, type) VALUES (?, ?, ?, ?, ?, ?)",
                         (d['phone'], d['price'], d['path'], d['geo'], d['stay'], message.text))
        await db.commit()
    await message.answer("✅ Аккаунт в продаже!", reply_markup=main_kb(ADMIN_ID))
    await state.clear()

# --- ВЫДАЧА БАЛАНСА И РАССЫЛКА (КНОПКИ) ---
@dp.message(F.text == "💰 Выдать баланс", F.from_user.id == ADMIN_ID)
async def adm_give_1(message: types.Message, state: FSMContext):
    await message.answer("ID юзера:")
    await state.set_state(AdminStates.waiting_for_balance_id)

@dp.message(AdminStates.waiting_for_balance_id)
async def adm_give_2(message: types.Message, state: FSMContext):
    await state.update_data(tid=message.text)
    await message.answer("Сумма:")
    await state.set_state(AdminStates.waiting_for_balance_amount)

@dp.message(AdminStates.waiting_for_balance_amount)
async def adm_give_3(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(message.text), d['tid']))
        await db.commit()
    await message.answer("Готово!")
    await bot.send_message(d['tid'], f"💰 Баланс пополнен на {message.text} TON!")
    await state.clear()

@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def mass_1(message: types.Message, state: FSMContext):
    await message.answer("Текст рассылки:")
    await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(AdminStates.waiting_for_broadcast)
async def mass_2(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        users = await cursor.fetchall()
    for u in users:
        try: await bot.send_message(u[0], message.text)
        except: pass
    await message.answer("Разослано!")
    await state.clear()

async def main():
    if not os.path.exists("sessions"): os.makedirs("sessions")
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
