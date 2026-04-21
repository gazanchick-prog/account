import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from telethon import TelegramClient
from dotenv import load_dotenv

# --- 1. НАСТРОЙКИ ---
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

# Состояния для кнопок админа и юзера
class AdminStates(StatesGroup):
    waiting_for_balance_id = State()
    waiting_for_balance_amount = State()
    waiting_for_broadcast = State()
    waiting_for_acc_file = State()
    waiting_for_acc_price = State()

# --- 2. БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, referrer_id INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, price REAL, session_path TEXT, is_sold INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER)")
        await db.commit()

# --- 3. ГЛАВНОЕ МЕНЮ ---
def main_kb(user_id):
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🛒 Купить"), types.KeyboardButton(text="🛍 Мои покупки"))
    builder.row(types.KeyboardButton(text="👤 Профиль"), types.KeyboardButton(text="💳 Пополнить"))
    builder.row(types.KeyboardButton(text="🆘 Поддержка"))
    if user_id == ADMIN_ID:
        builder.row(types.KeyboardButton(text="➕ Аккаунт"), types.KeyboardButton(text="💰 Выдать баланс"))
        builder.row(types.KeyboardButton(text="📢 Рассылка"))
    return builder.as_markup(resize_keyboard=True)

# --- 4. ЛОГИКА ПОЛЬЗОВАТЕЛЯ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    ref_id = int(command.args) if command.args and command.args.isdigit() else None
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, referrer_id) VALUES (?, ?)", (message.from_user.id, ref_id))
        await db.commit()
    await message.answer("🔥 Добро пожаловать в SifonMarket!", reply_markup=main_kb(message.from_user.id))

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0
    
    bot_info = await bot.get_me()
    text = (f"👤 **Профиль**\n\n🆔 ID: `{message.from_user.id}`\n💰 Баланс: **{balance} TON**\n\n"
            f"🔗 Реф. ссылка: `https://t.me/{bot_info.username}?start={message.from_user.id}`")
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💳 Пополнить")
async def topup(message: types.Message):
    await message.answer(f"💎 **Пополнение TON**\n\nАдрес:\n`{TON_WALLET}`\n\nКомментарий:\n`{message.from_user.id}`\n\nПосле оплаты пиши: {SUPPORT}")

# --- 5. ЛОГИКА ПОКУПОК И СЕССИЙ ---

@dp.message(F.text == "🛒 Купить")
async def shop_list(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, phone, price FROM products WHERE is_sold = 0")
        items = await cursor.fetchall()
    
    if not items:
        return await message.answer("Пока нет аккаунтов в наличии.")
    
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.row(InlineKeyboardButton(text=f"📱 {item[1]} | {item[2]} TON", callback_data=f"buy_{item[0]}"))
    await message.answer("Выберите номер для покупки:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT price, session_path FROM products WHERE id = ?", (prod_id,))
        prod = await cursor.fetchone()
        cursor = await db.execute("SELECT balance, referrer_id FROM users WHERE user_id = ?", (callback.from_user.id,))
        user = await cursor.fetchone()

        if user[0] >= prod[0]:
            # Покупка
            await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (prod[0], callback.from_user.id))
            await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (prod_id,))
            await db.execute("INSERT INTO purchases (user_id, product_id) VALUES (?, ?)", (callback.from_user.id, prod_id))
            
            # Рефералка 10%
            if user[1]:
                bonus = prod[0] * 0.1
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus, user[1]))
                try: await bot.send_message(user[1], f"🎁 Реф. бонус: +{bonus} TON!")
                except: pass
            
            await db.commit()
            await callback.message.edit_text("✅ Успешно куплено! Перейдите в 'Мои покупки'.")
        else:
            await callback.answer("Недостаточно средств!", show_alert=True)

@dp.message(F.text == "🛍 Мои покупки")
async def my_purchases(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT p.id, pr.phone FROM purchases p 
            JOIN products pr ON p.product_id = pr.id 
            WHERE p.user_id = ?""", (message.from_user.id,))
        items = await cursor.fetchall()
    
    if not items: return await message.answer("У вас еще нет покупок.")
    
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.row(InlineKeyboardButton(text=f"📟 {item[1]} (Код)", callback_data=f"getcode_{item[0]}"))
    await message.answer("Ваши купленные номера (нажми для кода):", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("getcode_"))
async def get_session_code(callback: types.CallbackQuery):
    purchase_id = int(callback.data.split("_")[1])
    await callback.answer("Подключаюсь к сессии...")
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT pr.session_path FROM purchases p 
            JOIN products pr ON p.product_id = pr.id 
            WHERE p.id = ?""", (purchase_id,))
        row = await cursor.fetchone()
        
    if row:
        try:
            client = TelegramClient(row[0], API_ID, API_HASH)
            await client.connect()
            messages = await client.get_messages(777000, limit=1)
            code = messages[0].message
            await callback.message.answer(f"📩 Последнее сообщение от Telegram:\n`{code}`", parse_mode="Markdown")
            await client.disconnect()
        except Exception as e:
            await callback.message.answer(f"❌ Ошибка: {e}")

# --- 6. АДМИН ПАНЕЛЬ (FSM КНОПКИ) ---

@dp.message(F.text == "💰 Выдать баланс", F.from_user.id == ADMIN_ID)
async def admin_balance_step1(message: types.Message, state: FSMContext):
    await message.answer("Введите ID пользователя:")
    await state.set_state(AdminStates.waiting_for_balance_id)

@dp.message(AdminStates.waiting_for_balance_id)
async def admin_balance_step2(message: types.Message, state: FSMContext):
    await state.update_data(target_id=message.text)
    await message.answer("Введите сумму (напр. 10.5):")
    await state.set_state(AdminStates.waiting_for_balance_amount)

@dp.message(AdminStates.waiting_for_balance_amount)
async def admin_balance_step3(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = float(message.text)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, data['target_id']))
        await db.commit()
    await message.answer(f"✅ Выдано {amount} пользователю {data['target_id']}")
    await bot.send_message(data['target_id'], f"💰 Ваш баланс пополнен на {amount} TON!")
    await state.clear()

@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def broadcast_step1(message: types.Message, state: FSMContext):
    await message.answer("Введите текст рассылки:")
    await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(AdminStates.waiting_for_broadcast)
async def broadcast_step2(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        users = await cursor.fetchall()
    
    count = 0
    for user in users:
        try:
            await bot.send_message(user[0], message.text)
            count += 1
        except: pass
    await message.answer(f"📢 Рассылка завершена. Получили {count} чел.")
    await state.clear()

@dp.message(F.text == "➕ Аккаунт", F.from_user.id == ADMIN_ID)
async def add_acc_step1(message: types.Message, state: FSMContext):
    await message.answer("Отправь файл .session")
    await state.set_state(AdminStates.waiting_for_acc_file)

@dp.message(AdminStates.waiting_for_acc_file, F.document)
async def add_acc_step2(message: types.Message, state: FSMContext):
    file_name = f"sessions/{message.document.file_name}"
    await bot.download(message.document, destination=file_name)
    await state.update_data(path=file_name, phone=message.document.file_name.replace(".session", ""))
    await message.answer("Введи цену (TON):")
    await state.set_state(AdminStates.waiting_for_acc_price)

@dp.message(AdminStates.waiting_for_acc_price)
async def add_acc_step3(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, session_path) VALUES (?, ?, ?)", (data['phone'], float(message.text), data['path']))
        await db.commit()
    await message.answer("✅ Аккаунт добавлен!")
    await state.clear()

async def main():
    if not os.path.exists("sessions"): os.makedirs("sessions")
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
