import os
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from telethon import TelegramClient
from aiocryptopay import AioCryptoPay
from dotenv import load_dotenv

# --- Конфигурация среды ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
CRYPTO_TOKEN = os.getenv("SEND_TOKEN")  # Токен от приложения Crypto Pay (@CryptoBot)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
crypto = AioCryptoPay(token=CRYPTO_TOKEN, network='mainnet')
DB_NAME = "sifon_market.db"

MAIN_MENU_LABELS = ["🛒 Купить", "👤 Профиль", "💰 Пополнить", "🛍 Мои покупки", "ℹ️ Информация", "🆘 Поддержка", "➕ Товар", "💎 Баланс", "📢 Рассылка", "🎁 Создать промо"]

# --- Состояния FSM ---
class ShopStates(StatesGroup):
    wait_bal_id = State()
    wait_bal_amount = State()
    wait_acc_file = State()
    wait_acc_price = State()
    wait_acc_geo = State()
    wait_acc_stay = State()
    wait_acc_type = State()
    wait_broadcast_text = State()
    wait_promo_name = State()
    wait_promo_reward = State()
    wait_promo_limit = State()
    wait_promo_activate = State()
    wait_topup_amount = State()  # Новое состояние для суммы пополнения

# --- Инициализация Базы Данных ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, rules_accepted INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, price REAL, session_path TEXT, geo TEXT, stay TEXT, type TEXT, is_sold INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS promocodes (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, reward REAL, max_uses INTEGER, current_uses INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS used_promos (user_id INTEGER, promo_id INTEGER)")
        await db.commit()

# --- Безопасный клиент Telethon ---
def get_safe_client(session_path):
    """Имитация реального устройства (iPhone 15 Pro) для снижения риска блокировки сессии."""
    return TelegramClient(
        session_path, API_ID, API_HASH,
        device_model="iPhone 15 Pro",
        system_version="17.5.1",
        app_version="10.14.2",
        lang_code="ru",
        system_lang_code="ru-RU"
    )

# --- Клавиатуры ---
def main_kb(user_id):
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🛒 Купить"), types.KeyboardButton(text="👤 Профиль"))
    builder.row(types.KeyboardButton(text="💰 Пополнить"), types.KeyboardButton(text="🛍 Мои покупки"))
    builder.row(types.KeyboardButton(text="ℹ️ Информация"), types.KeyboardButton(text="🆘 Поддержка"))
    if user_id == ADMIN_ID:
        builder.row(types.KeyboardButton(text="➕ Товар"), types.KeyboardButton(text="💎 Баланс"))
        builder.row(types.KeyboardButton(text="📢 Рассылка"), types.KeyboardButton(text="🎁 Создать промо"))
    return builder.as_markup(resize_keyboard=True)

# --- Глобальный перехватчик меню (Отсечение) ---
@dp.message(StateFilter("*"), F.text.in_(MAIN_MENU_LABELS))
async def cancel_state_on_menu(message: types.Message, state: FSMContext):
    """Сбрасывает любое состояние ввода, если юзер нажал на кнопку главного меню."""
    await state.clear()
    
    # Имитируем нажатие кнопки для маршрутизации
    if message.text == "🛒 Купить": await shop_cats(message)
    elif message.text == "👤 Профиль": await profile(message)
    elif message.text == "💰 Пополнить": await topup_menu(message, state)
    elif message.text == "🛍 Мои покупки": await my_purchases(message)
    elif message.text == "ℹ️ Информация": await info_menu(message)
    elif message.text == "🆘 Поддержка": await support(message)
    elif message.from_user.id == ADMIN_ID:
        if message.text == "➕ Товар": await adm_add_1(message, state)
        elif message.text == "💎 Баланс": await adm_bal_1(message, state)
        elif message.text == "📢 Рассылка": await admin_bc(message, state)
        elif message.text == "🎁 Создать промо": await adm_pr_1(message, state)

# --- Старт и Правила ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT rules_accepted FROM users WHERE user_id = ?", (message.from_user.id,))
        user = await cursor.fetchone()
        if not user:
            await db.execute("INSERT INTO users (user_id) VALUES (?)", (message.from_user.id,))
            await db.commit()
            user = (0,)
        if user[0] == 0:
            kb = InlineKeyboardBuilder()
            kb.row(types.InlineKeyboardButton(text="📖 Ознакомиться с правилами", url="https://telegra.ph/Pravila-servisa-04-26"))
            kb.row(types.InlineKeyboardButton(text="✅ Принять", callback_data="accept_rules"))
            return await message.answer("Для доступа к функционалу SifonMarket необходимо подтвердить согласие с регламентом.", reply_markup=kb.as_markup())
    
    await message.answer("Главное меню информационной панели:", reply_markup=main_kb(message.from_user.id))

@dp.callback_query(F.data == "accept_rules")
async def accept_rules(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET rules_accepted = 1 WHERE user_id = ?", (callback.from_user.id,))
        await db.commit()
    await callback.message.delete()
    await callback.message.answer("Удачных покупок", reply_markup=main_kb(callback.from_user.id))

# --- Информация ---
@dp.message(F.text == "ℹ️ Информация")
async def info_menu(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📜 Правила", url="https://telegra.ph/Pravila-servisa-04-26"))
    kb.row(types.InlineKeyboardButton(text="🔐 Политика", url="https://telegra.ph/Politika-konfidencialnosti-04-26-19"))
    kb.row(types.InlineKeyboardButton(text="🤝 Соглашение", url="https://telegra.ph/Polzovatelskoe-soglashenie-04-26-22"))
    
    msg = (
        "💎 **SifonMarket** — профессиональный агрегатор цифровых активов.\n\n"
        "Мы обеспечиваем высокий стандарт качества и стабильно низкий ценовой порог. "
        "Все реализуемые позиции проходят предварительную техническую проверку. "
        "Автоматизация процессов гарантирует получение товара в течение нескольких секунд."
    )
    await message.answer(msg, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def support(message: types.Message):
    await message.answer("🆘 Технический отдел: @zyozp")

# --- Профиль и Промокоды ---
@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        row = await cursor.fetchone()
    kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="🎁 Активировать промокод", callback_data="act_promo"))
    await message.answer(f"👤 **Профиль**\n🆔 ID: `{message.from_user.id}`\n💰 Баланс: **{row[0]} TON**", 
                         reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "act_promo")
async def promo_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Введите промокод:")
    await state.set_state(ShopStates.wait_promo_activate)

@dp.message(ShopStates.wait_promo_activate)
async def promo_activate(message: types.Message, state: FSMContext):
    code = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, reward, max_uses, current_uses FROM promocodes WHERE code = ?", (code,))
        promo = await cursor.fetchone()
        if not promo: return await message.answer("❌ Промокод не найден.")
        
        cursor = await db.execute("SELECT 1 FROM used_promos WHERE user_id = ? AND promo_id = ?", (message.from_user.id, promo[0]))
        if await cursor.fetchone(): return await message.answer("❌ Промокод уже был активирован ранее.")
        
        if promo[3] >= promo[2]: return await message.answer("❌ Лимит активаций исчерпан.")

        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (promo[1], message.from_user.id))
        await db.execute("UPDATE promocodes SET current_uses = current_uses + 1 WHERE id = ?", (promo[0],))
        await db.execute("INSERT INTO used_promos (user_id, promo_id) VALUES (?, ?)", (message.from_user.id, promo[0]))
        await db.commit()
        await message.answer(f"✅ Успешно! Начислено: **{promo[1]} TON**.", parse_mode="Markdown")
    await state.clear()

# --- Пополнение (CryptoPay / @send) ---
@dp.message(F.text == "💰 Пополнить")
async def topup_menu(message: types.Message, state: FSMContext):
    await message.answer("Введите сумму пополнения в TON (например, 0.5):")
    await state.set_state(ShopStates.wait_topup_amount)

@dp.message(ShopStates.wait_topup_amount)
async def process_topup_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0: raise ValueError
    except ValueError:
        return await message.answer("❌ Пожалуйста, введите корректное число (например, 1.5).")

    # Создание счета через Crypto Pay API
    invoice = await crypto.create_invoice(asset='TON', amount=amount)
    
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="💳 Оплатить (CryptoBot)", url=invoice.bot_invoice_url))
    kb.row(types.InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_inv_{invoice.invoice_id}_{amount}"))
    
    await message.answer(f"🧾 Сформирован счет на **{amount} TON**.\nПосле оплаты нажмите кнопку проверки.", 
                         reply_markup=kb.as_markup(), parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data.startswith("check_inv_"))
async def check_invoice(callback: types.CallbackQuery):
    data = callback.data.split("_")
    inv_id = int(data[2])
    amount = float(data[3])
    
    invoices = await crypto.get_invoices(invoice_ids=inv_id)
    if invoices and invoices.status == 'paid':
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, callback.from_user.id))
            await db.commit()
        await callback.message.edit_text(f"✅ Баланс успешно пополнен на **{amount} TON**.", parse_mode="Markdown")
    else:
        await callback.answer("Оплата еще не поступила. Транзакция может занимать несколько минут.", show_alert=True)

# --- Магазин (Покупка) ---
@dp.message(F.text == "🛒 Купить")
async def shop_cats(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")
        cats = await cursor.fetchall()
    if not cats: return await message.answer("Товары временно отсутствуют в системе.")
    kb = InlineKeyboardBuilder()
    for geo, count in cats: kb.row(types.InlineKeyboardButton(text=f"📍 {geo} ({count} шт.)", callback_data=f"cat_{geo}"))
    await message.answer("Выберите локацию:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def show_items(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, type, stay, price FROM products WHERE geo = ? AND is_sold = 0", (geo,))
        items = await cursor.fetchall()
    kb = InlineKeyboardBuilder()
    for i in items: kb.row(types.InlineKeyboardButton(text=f"⚙️ {i[1]} | {i[2]} | {i[3]} TON", callback_data=f"buy_{i[0]}"))
    await callback.message.edit_text(f"Доступные позиции ({geo}):", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT price, session_path, phone FROM products WHERE id = ? AND is_sold = 0", (pid,))
        prod = await cursor.fetchone()
        
        if not prod:
            return await callback.answer("Товар уже продан или недоступен.", show_alert=True)

        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (callback.from_user.id,))
        user = await cursor.fetchone()

        if user[0] >= prod[0]:
            # Валидация сессии перед списанием
            client = get_safe_client(prod[1])
            try:
                await client.connect()
                is_authorized = await client.is_user_authorized()
                await client.disconnect()
                if not is_authorized: raise Exception()
            except:
                # Помечаем бракованный аккаунт, чтобы не висел в продаже
                await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (pid,))
                await db.commit()
                return await callback.answer("Техническая ошибка сессии. Товар снят с продажи. Попробуйте другой.", show_alert=True)

            await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (prod[0], callback.from_user.id))
            await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (pid,))
            await db.execute("INSERT INTO purchases (user_id, product_id) VALUES (?, ?)", (callback.from_user.id, pid))
            await db.commit()
            
            await callback.message.answer(f"✅ Покупка завершена!\n📱 Номер: `{prod[2]}`\nЗапросите код в разделе 'Мои покупки'.", parse_mode="Markdown")
        else:
            await callback.answer("Недостаточный баланс.", show_alert=True)

# --- Мои покупки (Выдача кода) ---
@dp.message(F.text == "🛍 Мои покупки")
async def my_purchases(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""SELECT p.id, pr.phone FROM purchases p 
                                     JOIN products pr ON p.product_id = pr.id 
                                     WHERE p.user_id = ?""", (message.from_user.id,))
        rows = await cursor.fetchall()
    if not rows: return await message.answer("История приобретений пуста.")
    kb = InlineKeyboardBuilder()
    for r in rows: kb.row(types.InlineKeyboardButton(text=f"📱 {r[1]}", callback_data=f"view_{r[0]}"))
    await message.answer("Ваши активные позиции:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("view_"))
async def view_item(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT pr.phone FROM purchases p JOIN products pr ON p.product_id = pr.id WHERE p.id = ?", (pid,))
        row = await cursor.fetchone()
    
    kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="📩 ПОЛУЧИТЬ КОД", callback_data=f"get_{pid}"))
    await callback.message.answer(f"📱 Панель управления аккаунтом:\nНомер: `{row[0]}`", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("get_"))
async def get_code(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT pr.session_path FROM purchases p JOIN products pr ON p.product_id = pr.id WHERE p.id = ?", (pid,))
        row = await cursor.fetchone()
    
    client = get_safe_client(row[0])
    try:
        await client.connect()
        msgs = await client.get_messages(777000, limit=1)
        if msgs:
            await callback.message.answer(f"📩 **Данные авторизации (Telegram):**\n`{msgs[0].message}`", parse_mode="Markdown")
        else:
            await callback.message.answer("📫 Системное сообщение с кодом еще не поступило. Обновите запрос позже.")
        await client.disconnect()
    except:
        await callback.message.answer("❌ Ошибка доступа к сессии. Возможно, аккаунт был деактивирован Telegram.")

# --- Админ Панель ---
@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def admin_bc(message: types.Message, state: FSMContext):
    await message.answer("📝 Введите текст уведомления:")
    await state.set_state(ShopStates.wait_broadcast_text)

@dp.message(ShopStates.wait_broadcast_text)
async def bc_process(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        users = await cursor.fetchall()
    for u in users:
        try: await bot.send_message(u[0], message.text)
        except: pass
    await message.answer("✅ Рассылка успешно завершена.")
    await state.clear()

@dp.message(F.text == "🎁 Создать промо", F.from_user.id == ADMIN_ID)
async def adm_pr_1(message: types.Message, state: FSMContext):
    await message.answer("Укажите код (например: BONUS):")
    await state.set_state(ShopStates.wait_promo_name)

@dp.message(ShopStates.wait_promo_name)
async def adm_pr_2(message: types.Message, state: FSMContext):
    await state.update_data(n=message.text)
    await message.answer("Сумма начисления (TON):")
    await state.set_state(ShopStates.wait_promo_reward)

@dp.message(ShopStates.wait_promo_reward)
async def adm_pr_3(message: types.Message, state: FSMContext):
    await state.update_data(r=float(message.text))
    await message.answer("Количество активаций:")
    await state.set_state(ShopStates.wait_promo_limit)

@dp.message(ShopStates.wait_promo_limit)
async def adm_pr_4(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO promocodes (code, reward, max_uses) VALUES (?, ?, ?)", (d['n'], d['r'], int(message.text)))
        await db.commit()
    await message.answer(f"✅ Промокод `{d['n']}` на {d['r']} TON успешно сгенерирован.")
    await state.clear()

@dp.message(F.text == "➕ Товар", F.from_user.id == ADMIN_ID)
async def adm_add_1(message: types.Message, state: FSMContext):
    await message.answer("Загрузите файл `.session`:")
    await state.set_state(ShopStates.wait_acc_file)

@dp.message(ShopStates.wait_acc_file, F.document)
async def adm_add_2(message: types.Message, state: FSMContext):
    path = f"sessions/{message.document.file_name}"
    await bot.download(message.document, destination=path)
    await state.update_data(p=path, ph=message.document.file_name.replace(".session", ""))
    await message.answer("Стоимость (TON):")
    await state.set_state(ShopStates.wait_acc_price)

@dp.message(ShopStates.wait_acc_price)
async def adm_add_3(message: types.Message, state: FSMContext):
    await state.update_data(pr=float(message.text))
    await message.answer("Геопозиция (например: RU):")
    await state.set_state(ShopStates.wait_acc_geo)

@dp.message(ShopStates.wait_acc_geo)
async def adm_add_4(message: types.Message, state: FSMContext):
    await state.update_data(g=message.text)
    await message.answer("Отлежка (например: 30 дней):")
    await state.set_state(ShopStates.wait_acc_stay)

@dp.message(ShopStates.wait_acc_stay)
async def adm_add_5(message: types.Message, state: FSMContext):
    await state.update_data(s=message.text)
    await message.answer("Тип аккаунта (например: Premium):")
    await state.set_state(ShopStates.wait_acc_type)

@dp.message(ShopStates.wait_acc_type)
async def adm_add_6(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, session_path, geo, stay, type) VALUES (?, ?, ?, ?, ?, ?)",
                         (d['ph'], d['pr'], d['p'], d['g'], d['s'], message.text))
        await db.commit()
    await message.answer("✅ Товар загружен и доступен для покупки.")
    await state.clear()

@dp.message(F.text == "💎 Баланс", F.from_user.id == ADMIN_ID)
async def adm_bal_1(message: types.Message, state: FSMContext):
    await message.answer("ID клиента:")
    await state.set_state(ShopStates.wait_bal_id)

@dp.message(ShopStates.wait_bal_id)
async def adm_bal_2(message: types.Message, state: FSMContext):
    await state.update_data(u=message.text)
    await message.answer("Сумма начисления:")
    await state.set_state(ShopStates.wait_bal_amount)

@dp.message(ShopStates.wait_bal_amount)
async def adm_bal_3(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(message.text), d['u']))
        await db.commit()
    await message.answer("✅ Ручное пополнение проведено.")
    await state.clear()

# --- Системный запуск ---
async def main():
    if not os.path.exists("sessions"): 
        os.makedirs("sessions")
    await init_db()
    
    # Запускаем бота, по завершению закрываем сессию crypto
    try:
        await dp.start_polling(bot)
    finally:
        await crypto.close()

if __name__ == "__main__":
    asyncio.run(main())
