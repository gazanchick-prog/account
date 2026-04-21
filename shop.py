import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from telethon import TelegramClient
from telethon.errors import UserDeactivatedError, AuthKeyUnregisteredError
from dotenv import load_dotenv

# --- ЗАГРУЗКА КОНФИГА ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TON_WALLET = os.getenv("TON_WALLET", "Кошелек не указан")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_NAME = "sifon_market.db"

# --- СОСТОЯНИЯ (FSM) ---
class ShopStates(StatesGroup):
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
    builder.row(types.KeyboardButton(text="🛒 Купить аккаунты"), types.KeyboardButton(text="👤 Профиль"))
    builder.row(types.KeyboardButton(text="💰 Пополнить баланс"), types.KeyboardButton(text="🛍 Мои покупки"))
    builder.row(types.KeyboardButton(text="🆘 Поддержка"))
    if user_id == ADMIN_ID:
        builder.row(types.KeyboardButton(text="➕ Добавить товар"), types.KeyboardButton(text="💎 Выдать баланс"))
    return builder.as_markup(resize_keyboard=True)

# --- ОСНОВНЫЕ ХЕНДЛЕРЫ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()
    
    text = (
        "👋 **Добро пожаловать в SifonMarket!**\n\n"
        "⚡️ Мгновенная выдача после оплаты\n"
        "🛡 Гарантия на все аккаунты\n"
        "💳 Пополнение через TON\n\n"
        "Выбери нужное действие в меню ниже:"
    )
    await message.answer(text, reply_markup=main_kb(message.from_user.id), parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def support(message: types.Message):
    await message.answer("🆘 По всем вопросам обратитесь к @zyozp")

@dp.message(F.text == "💰 Пополнить баланс")
async def topup(message: types.Message):
    text = (
        "💎 **Пополнение баланса (TON)**\n\n"
        "Отправьте любую сумму на кошелек ниже.\n"
        "Средства зачислятся после подтверждения.\n\n"
        f"📍 **Адрес (нажми для копирования):**\n`{TON_WALLET}`\n\n"
        f"💬 **Комментарий (обязательно):**\n`{message.from_user.id}`\n\n"
        "⚠️ Если не укажете комментарий — баланс не придет!"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        row = await cursor.fetchone()
        balance = row[0] if row else 0
    
    text = (
        "👤 **Ваш профиль**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: `{message.from_user.id}`\n"
        f"💰 Баланс: **{balance} TON**\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await message.answer(text, parse_mode="Markdown")

# --- МАГАЗИН (ЛОГИКА ПОКУПКИ) ---
@dp.message(F.text == "🛒 Купить аккаунты")
async def shop_categories(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")
        categories = await cursor.fetchall()
    
    if not categories: return await message.answer("📦 На данный момент товаров нет.")
    
    kb = InlineKeyboardBuilder()
    for geo, count in categories:
        kb.row(types.InlineKeyboardButton(text=f"📍 {geo} — {count} шт.", callback_data=f"cat_{geo}"))
    await message.answer("📁 **Выберите категорию:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def show_items(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, type, stay, price FROM products WHERE geo = ? AND is_sold = 0", (geo,))
        items = await cursor.fetchall()
    
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.row(types.InlineKeyboardButton(text=f"⚙️ {item[1]} | ⏳ {item[2]} | 💵 {item[3]} TON", callback_data=f"buy_{item[0]}"))
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_cats"))
    await callback.message.edit_text(f"📱 **Аккаунты в категории {geo}:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_cats")
async def back_to_cats(callback: types.CallbackQuery):
    await shop_categories(callback.message)

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT price, session_path, phone FROM products WHERE id = ?", (pid,))
        prod = await cursor.fetchone()
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (callback.from_user.id,))
        user = await cursor.fetchone()

        if user and user[0] >= prod[0]:
            # ПРОВЕРКА СЕССИИ ПЕРЕД ПРОДАЖЕЙ
            try:
                client = TelegramClient(prod[1], API_ID, API_HASH)
                await client.connect()
                if not await client.is_user_authorized():
                    await client.disconnect()
                    raise Exception("Dead")
                await client.disconnect()
            except:
                return await callback.answer("ошибка сессии - обратитесь к администратору за заменой", show_alert=True)

            await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (prod[0], callback.from_user.id))
            await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (pid,))
            await db.execute("INSERT INTO purchases (user_id, product_id) VALUES (?, ?)", (callback.from_user.id, pid))
            await db.commit()
            
            await callback.message.answer(f"✅ **Успешно куплено!**\n📱 Номер: `{prod[2]}`\n\nАккаунт доступен в разделе 'Мои покупки'.", parse_mode="Markdown")
        else:
            await callback.answer("❌ Недостаточно средств на балансе!", show_alert=True)

# --- МОИ ПОКУПКИ И КОДЫ ---
@dp.message(F.text == "🛍 Мои покупки")
async def my_purchases(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""SELECT p.id, pr.phone FROM purchases p 
                                  JOIN products pr ON p.product_id = pr.id 
                                  WHERE p.user_id = ?""", (message.from_user.id,))
        rows = await cursor.fetchall()
    
    if not rows: return await message.answer("🛍 У вас пока нет покупок.")
    
    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.row(types.InlineKeyboardButton(text=f"📱 {row[1]}", callback_data=f"view_{row[0]}"))
    await message.answer("📦 **История ваших покупок:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("view_"))
async def view_item(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT pr.phone FROM purchases p JOIN products pr ON p.product_id = pr.id WHERE p.id = ?", (pid,))
        row = await cursor.fetchone()
    
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📩 Получить код", callback_data=f"get_{pid}"))
    await callback.message.answer(f"📱 Аккаунт: `{row[0]}`\nНажмите на кнопку ниже, чтобы запросить код входа.", parse_mode="Markdown", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("get_"))
async def get_login_code(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT pr.session_path FROM purchases p JOIN products pr ON p.product_id = pr.id WHERE p.id = ?", (pid,))
        row = await cursor.fetchone()
    
    await callback.answer("⏳ Запрашиваю код...")
    client = TelegramClient(row[0], API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return await callback.message.answer("❌ **ошибка сессии - обратитесь к администратору за заменой**", parse_mode="Markdown")
        
        msgs = await client.get_messages(777000, limit=1)
        if msgs:
            await callback.message.answer(f"📩 **Код из Telegram:**\n`{msgs[0].message}`", parse_mode="Markdown")
        else:
            await callback.message.answer("📫 Код пока не поступил. Попробуйте еще раз через 10 секунд.")
        await client.disconnect()
    except (UserDeactivatedError, AuthKeyUnregisteredError):
        await callback.message.answer("❌ **ошибка сессии - обратитесь к администратору за заменой**", parse_mode="Markdown")
    except Exception:
        await callback.message.answer("❌ **ошибка сессии - обратитесь к администратору за заменой**", parse_mode="Markdown")

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(F.text == "➕ Добавить товар", F.from_user.id == ADMIN_ID)
async def add_1(message: types.Message, state: FSMContext):
    await message.answer("📎 Отправьте файл `.session`:")
    await state.set_state(ShopStates.wait_acc_file)

@dp.message(ShopStates.wait_acc_file, F.document)
async def add_2(message: types.Message, state: FSMContext):
    path = f"sessions/{message.document.file_name}"
    await bot.download(message.document, destination=path)
    await state.update_data(path=path, phone=message.document.file_name.replace(".session", ""))
    await message.answer("💰 Введите цену (только число):")
    await state.set_state(ShopStates.wait_acc_price)

@dp.message(ShopStates.wait_acc_price)
async def add_3(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await message.answer("🌍 Введите локацию (например, Россия +7):")
    await state.set_state(ShopStates.wait_acc_geo)

@dp.message(ShopStates.wait_acc_geo)
async def add_4(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text)
    await message.answer("⏳ Укажите отлегу (например, 1 год):")
    await state.set_state(ShopStates.wait_acc_stay)

@dp.message(ShopStates.wait_acc_stay)
async def add_5(message: types.Message, state: FSMContext):
    await state.update_data(stay=message.text)
    await message.answer("🛠 Тип (например, Авторег):")
    await state.set_state(ShopStates.wait_acc_type)

@dp.message(ShopStates.wait_acc_type)
async def add_6(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, session_path, geo, stay, type) VALUES (?, ?, ?, ?, ?, ?)",
                         (d['phone'], d['price'], d['path'], d['geo'], d['stay'], message.text))
        await db.commit()
    await message.answer("✅ Товар успешно добавлен в магазин!", reply_markup=main_kb(ADMIN_ID))
    await state.clear()

@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
async def give_1(message: types.Message, state: FSMContext):
    await message.answer("👤 Введите ID пользователя:")
    await state.set_state(ShopStates.wait_bal_id)

@dp.message(ShopStates.wait_bal_id)
async def give_2(message: types.Message, state: FSMContext):
    await state.update_data(uid=message.text)
    await message.answer("💎 Сумма пополнения:")
    await state.set_state(ShopStates.wait_bal_amount)

@dp.message(ShopStates.wait_bal_amount)
async def give_3(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(message.text), d['uid']))
        await db.commit()
    await message.answer(f"✅ Баланс пользователя `{d['uid']}` пополнен на {message.text} TON.")
    await bot.send_message(d['uid'], f"💰 Ваш баланс пополнен на **{message.text} TON**!", parse_mode="Markdown")
    await state.clear()

# --- ЗАПУСК ---
async def main():
    if not os.path.exists("sessions"): os.makedirs("sessions")
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
