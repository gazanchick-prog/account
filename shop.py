import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, UserDeactivatedError, AuthKeyUnregisteredError
from dotenv import load_dotenv

# --- НАСТРОЙКИ ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TON_WALLET = os.getenv("TON_WALLET", "Кошелек не указан")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_NAME = "sifon_market.db"

class AdminStates(StatesGroup):
    wait_bal_id = State()
    wait_bal_amount = State()
    wait_acc_file = State()
    wait_acc_price = State()
    wait_acc_geo = State()
    wait_acc_stay = State()
    wait_acc_type = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)")
        await db.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            phone TEXT, price REAL, session_path TEXT, 
            geo TEXT, stay TEXT, type TEXT, is_sold INTEGER DEFAULT 0)""")
        await db.execute("CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER)")
        await db.commit()

# --- КЛАВИАТУРЫ ---
def main_kb(user_id):
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="Купить"), types.KeyboardButton(text="Мои покупки"))
    builder.row(types.KeyboardButton(text="Профиль"), types.KeyboardButton(text="Пополнить"))
    builder.row(types.KeyboardButton(text="Поддержка"))
    if user_id == ADMIN_ID:
        builder.row(types.KeyboardButton(text="Добавить товар"), types.KeyboardButton(text="Выдать баланс"))
    return builder.as_markup(resize_keyboard=True)

# --- ЛОГИКА ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()
    await message.answer("SifonMarket запущен.", reply_markup=main_kb(message.from_user.id))

@dp.message(F.text == "Поддержка")
async def support(message: types.Message):
    await message.answer("обратитесь к @zyozp")

@dp.message(F.text == "Пополнить")
async def topup(message: types.Message):
    await message.answer(
        f"Пополнение TON\n\nАдрес (нажми для копирования):\n`{TON_WALLET}`\n\n"
        f"Комментарий (обязательно):\n`{message.from_user.id}`", 
        parse_mode="Markdown"
    )

@dp.message(F.text == "Профиль")
async def profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0
    await message.answer(f"ID: {message.from_user.id}\nБаланс: {balance} TON")

# --- МАГАЗИН ---
@dp.message(F.text == "Купить")
async def shop_categories(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")
        categories = await cursor.fetchall()
    
    if not categories: return await message.answer("Товаров нет.")
    
    kb = InlineKeyboardBuilder()
    for geo, count in categories:
        kb.row(types.InlineKeyboardButton(text=f"{geo} ({count} шт.)", callback_data=f"cat_{geo}"))
    await message.answer("Выберите локацию:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def show_items(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, type, stay, price FROM products WHERE geo = ? AND is_sold = 0", (geo,))
        items = await cursor.fetchall()
    
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.row(types.InlineKeyboardButton(text=f"{item[1]} | {item[2]} | {item[3]} TON", callback_data=f"buy_{item[0]}"))
    await callback.message.edit_text(f"Аккаунты {geo}:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT price, session_path, phone FROM products WHERE id = ?", (prod_id,))
        prod = await cursor.fetchone()
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (callback.from_user.id,))
        user = await cursor.fetchone()

        if user and user[0] >= prod[0]:
            # Проверка сессии перед продажей
            try:
                client = TelegramClient(prod[1], API_ID, API_HASH)
                await client.connect()
                if not await client.is_user_authorized():
                    await client.disconnect()
                    raise Exception("Unauthorized")
                await client.disconnect()
            except:
                return await callback.answer("Этот аккаунт недоступен, обратитесь к администратору за заменой", show_alert=True)

            await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (prod[0], callback.from_user.id))
            await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (prod_id,))
            await db.execute("INSERT INTO purchases (user_id, product_id) VALUES (?, ?)", (callback.from_user.id, prod_id))
            await db.commit()
            await callback.message.answer(f"Куплено! Номер: {prod[2]}\nДоступен в 'Мои покупки'")
        else:
            await callback.answer("Недостаточно средств", show_alert=True)

# --- ВЫДАЧА КОДА ---
@dp.message(F.text == "Мои покупки")
async def my_purchases(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""SELECT p.id, pr.phone FROM purchases p 
                                  JOIN products pr ON p.product_id = pr.id 
                                  WHERE p.user_id = ?""", (message.from_user.id,))
        rows = await cursor.fetchall()
    
    if not rows: return await message.answer("Покупок нет.")
    
    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.row(types.InlineKeyboardButton(text=f"Номер: {row[1]}", callback_data=f"view_{row[0]}"))
    await message.answer("Ваши покупки:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("view_"))
async def view_purchase(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT pr.phone FROM purchases p JOIN products pr ON p.product_id = pr.id WHERE p.id = ?", (pid,))
        row = await cursor.fetchone()
    
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="Запросить код", callback_data=f"getcode_{pid}"))
    await callback.message.answer(f"Номер: `{row[0]}`", parse_mode="Markdown", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("getcode_"))
async def get_login_code(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT pr.session_path FROM purchases p JOIN products pr ON p.product_id = pr.id WHERE p.id = ?", (pid,))
        row = await cursor.fetchone()
    
    client = TelegramClient(row[0], API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return await callback.message.answer("ошибка сессии - обратитесь к администратору за заменой")
        
        msgs = await client.get_messages(777000, limit=1)
        if msgs:
            await callback.message.answer(f"Код из Telegram: `{msgs[0].message}`", parse_mode="Markdown")
        else:
            await callback.message.answer("Код еще не пришел.")
        await client.disconnect()
    except (UserDeactivatedError, AuthKeyUnregisteredError):
        await callback.message.answer("ошибка сессии - обратитесь к администратору за заменой")
    except Exception as e:
        await callback.message.answer(f"Системная ошибка: {e}")

# --- АДМИНКА ---
@dp.message(F.text == "Добавить товар", F.from_user.id == ADMIN_ID)
async def add_1(message: types.Message, state: FSMContext):
    await message.answer("Пришли файл .session")
    await state.set_state(AdminStates.wait_acc_file)

@dp.message(AdminStates.wait_acc_file, F.document)
async def add_2(message: types.Message, state: FSMContext):
    path = f"sessions/{message.document.file_name}"
    await bot.download(message.document, destination=path)
    await state.update_data(path=path, phone=message.document.file_name.replace(".session", ""))
    await message.answer("Цена (TON):")
    await state.set_state(AdminStates.wait_acc_price)

@dp.message(AdminStates.wait_acc_price)
async def add_3(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await message.answer("Геолокация (название):")
    await state.set_state(AdminStates.wait_acc_geo)

@dp.message(AdminStates.wait_acc_geo)
async def add_4(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text)
    await message.answer("Отлега:")
    await state.set_state(AdminStates.wait_acc_stay)

@dp.message(AdminStates.wait_acc_stay)
async def add_5(message: types.Message, state: FSMContext):
    await state.update_data(stay=message.text)
    await message.answer("Тип аккаунта:")
    await state.set_state(AdminStates.wait_acc_type)

@dp.message(AdminStates.wait_acc_type)
async def add_6(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, session_path, geo, stay, type) VALUES (?, ?, ?, ?, ?, ?)",
                         (d['phone'], d['price'], d['path'], d['geo'], d['stay'], message.text))
        await db.commit()
    await message.answer("Товар добавлен.")
    await state.clear()

@dp.message(F.text == "Выдать баланс", F.from_user.id == ADMIN_ID)
async def give_1(message: types.Message, state: FSMContext):
    await message.answer("ID пользователя:")
    await state.set_state(AdminStates.wait_bal_id)

@dp.message(AdminStates.wait_bal_id)
async def give_2(message: types.Message, state: FSMContext):
    await state.update_data(uid=message.text)
    await message.answer("Сумма TON:")
    await state.set_state(AdminStates.wait_bal_amount)

@dp.message(AdminStates.wait_bal_amount)
async def give_3(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(message.text), d['uid']))
        await db.commit()
    await message.answer("Баланс обновлен.")
    await state.clear()

async def main():
    if not os.path.exists("sessions"): os.makedirs("sessions")
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
