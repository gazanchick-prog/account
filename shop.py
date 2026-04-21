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

# Кэш для запущенных клиентов Telethon (чтобы не заходить/выходить постоянно)
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
    builder.row(types.KeyboardButton(text="🏆 Топ покупателей"), types.KeyboardButton(text="ℹ️ Информация"))
    builder.row(types.KeyboardButton(text="🆘 Поддержка"))
    
    if user_id == ADMIN_ID:
        builder.row(types.KeyboardButton(text="➕ Добавить товар"), types.KeyboardButton(text="💎 Выдать баланс"))
        builder.row(types.KeyboardButton(text="📢 Рассылка"))
    return builder.as_markup(resize_keyboard=True)

# --- ОСНОВНЫЕ ФУНКЦИИ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)
        if referrer_id == message.from_user.id:
            referrer_id = None

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (message.from_user.id,))
        user_exists = await cursor.fetchone()
        
        if not user_exists:
            await db.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (message.from_user.id, referrer_id))
            await db.commit()

    text = (
        "👋 **Добро пожаловать в Sifon Market!**\n\n"
        "🛒 Покупайте качественные аккаунты по лучшим ценам!\n"
        "⚡️ Мгновенная выдача товара после покупки.\n"
        "💰 Пополнение баланса: CryptoBOT, TON.\n"
        "🔐 Автоматическое получение кода.\n"
        "👥 Реферальная система: зарабатывайте вместе с нами.\n"
        "🆘 Круглосуточная поддержка.\n\n"
        "👇 Выберите действие на клавиатуре ниже:"
    )
    await message.answer(text, reply_markup=main_kb(message.from_user.id), parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        row = await cursor.fetchone()
        
        cursor = await db.execute("SELECT COUNT(*) FROM purchases WHERE user_id = ?", (message.from_user.id,))
        purchases_count = await cursor.fetchone()

    text = (
        "👤 **Ваш профиль в Sifon Market**\n\n"
        f"🆔 Ваш ID: `{message.from_user.id}`\n"
        f"💰 Текущий баланс: **{round(row[0], 2)} TON**\n"
        f"🛍 Всего покупок: **{purchases_count[0]} шт.**"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💰 Пополнить баланс")
async def topup(message: types.Message):
    text = (
        "💎 **Пополнение баланса (TON)**\n\n"
        "Для пополнения баланса переведите TON на указанный адрес.\n"
        "❗️ **ВАЖНО:** Обязательно укажите свой ID в комментарии к переводу, иначе средства не зачислятся!\n\n"
        f"📍 **Адрес кошелька:**\n`{TON_WALLET}`\n\n"
        f"💬 **Комментарий (ВАШ ID):**\n`{message.from_user.id}`"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👥 Реферальная система")
async def ref_system(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (message.from_user.id,))
        refs_count = await cursor.fetchone()

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    
    text = (
        "👥 **Реферальная система**\n\n"
        "Приглашайте друзей и получайте **10%** от суммы всех их покупок на свой баланс!\n\n"
        f"🔗 **Ваша реферальная ссылка:**\n`{ref_link}`\n\n"
        f"👤 Приглашено друзей: **{refs_count[0]} чел.**"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def support(message: types.Message):
    await message.answer("🆘 По всем вопросам, заменам и сотрудничеству обращайтесь к: @zyozp")

# --- ЛОГИКА МАГАЗИНА ---
@dp.message(F.text == "🛒 Купить аккаунты")
async def shop_cats(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")
        cats = await cursor.fetchall()
    
    if not cats:
        return await message.answer("📦 В данный момент товаров нет в наличии.")
    
    kb = InlineKeyboardBuilder()
    for geo, count in cats:
        kb.row(types.InlineKeyboardButton(text=f"📍 {geo} ({count} шт.)", callback_data=f"cat_{geo}"))
    await message.answer("📁 **Выберите локацию:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def show_items(callback: types.CallbackQuery):
    geo = callback.data.split("_", 1)[1]
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, type, stay, price FROM products WHERE geo = ? AND is_sold = 0 LIMIT 20", (geo,))
        items = await cursor.fetchall()
    
    kb = InlineKeyboardBuilder()
    for i in items:
        kb.row(types.InlineKeyboardButton(text=f"⚙️ {i[1]} | ⏳ {i[2]} | 💵 {i[3]} TON", callback_data=f"buy_{i[0]}"))
    
    await callback.message.edit_text(f"📱 **Аккаунты {geo}:**\nВыберите нужный товар:", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT price, session_path, phone FROM products WHERE id = ? AND is_sold = 0", (pid,))
        prod = await cursor.fetchone()
        
        if not prod:
            return await callback.answer("❌ Товар уже куплен или не существует.", show_alert=True)

        cursor = await db.execute("SELECT balance, referrer_id FROM users WHERE user_id = ?", (callback.from_user.id,))
        user = await cursor.fetchone()

        if user[0] >= prod[0]:
            # Проверка сессии перед продажей
            try:
                client = TelegramClient(prod[1], API_ID, API_HASH)
                await client.connect()
                is_auth = await client.is_user_authorized()
                await client.disconnect()
                if not is_auth:
                    raise Exception()
            except Exception:
                await db.execute("DELETE FROM products WHERE id = ?", (pid,))
                await db.commit()
                return await callback.answer("❌ Ошибка сессии (аккаунт невалид). Обратитесь к администратору.", show_alert=True)

            # Списываем баланс
            await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (prod[0], callback.from_user.id))
            
            # Начисление рефералу (10%)
            if user[1]:
                ref_bonus = prod[0] * 0.10
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (ref_bonus, user[1]))
            
            # Обновляем статус
            await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (pid,))
            await db.execute("INSERT INTO purchases (user_id, product_id) VALUES (?, ?)", (callback.from_user.id, pid))
            await db.commit()
            
            # Выдача
            await callback.message.delete()
            await callback.message.answer(
                f"✅ **Успешная покупка!**\n\n📱 Номер: `{prod[2]}`\n💵 Списано: {prod[0]} TON\n\nФайл сессии прикреплен ниже. Код для входа вы можете запросить в меню «🔐 Получить код».", 
                parse_mode="Markdown"
            )
            # Отправка файла сессии пользователю
            await callback.message.answer_document(FSInputFile(prod[1]))
        else:
            await callback.answer("❌ Недостаточно средств на балансе. Пополните счет.", show_alert=True)

# --- РАБОТА С СЕССИЯМИ (ПОЛУЧИТЬ КОД) ---
@dp.message(F.text == "🔐 Получить код")
async def get_code_menu(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT pr.id, pr.phone 
            FROM purchases p 
            JOIN products pr ON p.product_id = pr.id 
            WHERE p.user_id = ?
        """, (message.from_user.id,))
        rows = await cursor.fetchall()
    
    if not rows:
        return await message.answer("🛒 У вас еще нет купленных аккаунтов.")
    
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.row(types.InlineKeyboardButton(text=f"📱 {r[1]}", callback_data=f"code_{r[0]}"))
    
    await message.answer("🔐 **Выберите аккаунт для получения кода:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("code_"))
async def fetch_code(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    await callback.answer("⏳ Запрашиваю код...", show_alert=False)
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT session_path FROM products WHERE id = ?", (pid,))
        row = await cursor.fetchone()
    
    if not row:
        return await callback.message.answer("❌ Аккаунт не найден.")
    
    session_path = row[0]
    
    # Использование кэшированного клиента (чтобы не заходить/выходить постоянно)
    if session_path not in active_clients:
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()
        active_clients[session_path] = client
    else:
        client = active_clients[session_path]

    try:
        if not await client.is_user_authorized():
             await callback.message.answer("❌ Сессия мертва. Обратитесь к @zyozp за заменой.")
             return

        msgs = await client.get_messages(777000, limit=1)
        if msgs and msgs[0].message:
            await callback.message.answer(f"📩 **Последнее сообщение от Telegram:**\n\n`{msgs[0].message}`", parse_mode="Markdown")
        else:
            await callback.message.answer("⚠️ Код еще не пришел. Подождите пару минут и попробуйте снова.")
    except Exception as e:
        await callback.message.answer("❌ **Ошибка сессии — обратитесь к администратору за заменой**")


# --- АДМИН ПАНЕЛЬ ---
@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def broadcast_1(message: types.Message, state: FSMContext):
    await message.answer("📝 Введите текст для рассылки всем пользователям:")
    await state.set_state(ShopStates.wait_broadcast_text)

@dp.message(ShopStates.wait_broadcast_text)
async def broadcast_2(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        users = await cursor.fetchall()
    
    count = 0
    for u in users:
        try:
            await bot.send_message(u[0], message.text)
            count += 1
            await asyncio.sleep(0.05) # Защита от флуда
        except:
            pass
    
    await message.answer(f"✅ Рассылка успешно завершена.\nДоставлено: {count} пользователям.")
    await state.clear()

@dp.message(F.text == "➕ Добавить товар", F.from_user.id == ADMIN_ID)
async def add_1(message: types.Message, state: FSMContext):
    await message.answer("📎 Отправьте `.session` файл аккаунта:")
    await state.set_state(ShopStates.wait_acc_file)

@dp.message(ShopStates.wait_acc_file, F.document)
async def add_2(message: types.Message, state: FSMContext):
    if not message.document.file_name.endswith(".session"):
        return await message.answer("❌ Пожалуйста, отправьте файл с расширением .session")
        
    path = f"sessions/{message.document.file_name}"
    await bot.download(message.document, destination=path)
    await state.update_data(path=path, phone=message.document.file_name.replace(".session", ""))
    await message.answer("💰 Укажите цену (в TON, например 1.5):")
    await state.set_state(ShopStates.wait_acc_price)

@dp.message(ShopStates.wait_acc_price)
async def add_3(message: types.Message, state: FSMContext):
    try:
        await state.update_data(price=float(message.text))
        await message.answer("🌍 Укажите гео (например, Индонезия):")
        await state.set_state(ShopStates.wait_acc_geo)
    except ValueError:
        await message.answer("❌ Цена должна быть числом!")

@dp.message(ShopStates.wait_acc_geo)
async def add_4(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text)
    await message.answer("⏳ Укажите отлегу (например, 7 дней):")
    await state.set_state(ShopStates.wait_acc_stay)

@dp.message(ShopStates.wait_acc_stay)
async def add_5(message: types.Message, state: FSMContext):
    await state.update_data(stay=message.text)
    await message.answer("🛠 Укажите тип (например, Tdata/Session):")
    await state.set_state(ShopStates.wait_acc_type)

@dp.message(ShopStates.wait_acc_type)
async def add_6(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, session_path, geo, stay, type) VALUES (?, ?, ?, ?, ?, ?)",
                         (d['phone'], d['price'], d['path'], d['geo'], d['stay'], message.text))
        await db.commit()
    await message.answer(f"✅ Товар успешно добавлен.\nГео: {d['geo']}\nЦена: {d['price']} TON")
    await state.clear()

@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
async def give_bal(message: types.Message, state: FSMContext):
    await message.answer("Введите ID пользователя:")
    await state.set_state(ShopStates.wait_bal_id)

@dp.message(ShopStates.wait_bal_id)
async def give_bal_2(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ ID должен быть числом!")
    await state.update_data(uid=int(message.text))
    await message.answer("Укажите сумму пополнения (в TON):")
    await state.set_state(ShopStates.wait_bal_amount)

@dp.message(ShopStates.wait_bal_amount)
async def give_bal_3(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        d = await state.get_data()
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, d['uid']))
            await db.commit()
        await message.answer(f"✅ Баланс пользователя `{d['uid']}` успешно пополнен на {amount} TON.", parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await message.answer("❌ Сумма должна быть числом!")

# --- ЗАПУСК ---
async def main():
    if not os.path.exists("sessions"):
        os.makedirs("sessions")
    await init_db()
    print("Sifon Market Bot запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
