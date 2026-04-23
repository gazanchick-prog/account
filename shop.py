import os
import asyncio
import aiosqlite
import aiohttp
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery, FSInputFile
from telethon import TelegramClient
from dotenv import load_dotenv

# --- ИНИЦИАЛИЗАЦИЯ ---
load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
DB_NAME = "sifon_ultimate.db"

ADMIN_ID = int(os.getenv("ADMIN_ID"))
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SEND_TOKEN = os.getenv("SEND_TOKEN")
SEND_API_URL = "https://pay.send.tg/api/v1"
STAR_RATE = 0.005 # Сколько TON давать за 1 Звезду

# Хранилище активных сессий для получения кодов
user_clients = {}

class ShopStates(StatesGroup):
    wait_topup_ton = State()
    wait_topup_stars = State()
    wait_acc_file = State()
    wait_acc_price = State()
    wait_acc_geo = State()
    wait_acc_stay = State()
    wait_acc_type = State()
    edit_select_prod = State()
    edit_field = State()
    edit_value = State()
    wait_broadcast = State()
    wait_session_for_code = State()
    wait_bal_id = State()
    wait_bal_amount = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)")
        await db.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, price REAL, 
            file_id TEXT, geo TEXT, base_stay INTEGER, date_added TEXT, 
            type TEXT, is_sold INTEGER DEFAULT 0)""")
        await db.commit()

# --- ВСПОМОГАТЕЛЬНОЕ ---
def get_current_stay(base_stay, date_added_str):
    added_dt = datetime.strptime(date_added_str, "%Y-%m-%d")
    return base_stay + (datetime.now() - added_dt).days

async def check_valid(file_id):
    path = f"tmp_{time.time()}.session"
    try:
        f = await bot.get_file(file_id)
        await bot.download_file(f.file_path, path)
        client = TelegramClient(path, API_ID, API_HASH)
        await client.connect()
        valid = await client.is_user_authorized()
        await client.disconnect()
        return valid
    except: return False
    finally:
        if os.path.exists(path): os.remove(path)

# --- КЛАВИАТУРЫ ---
def main_kb(uid):
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="🛒 Купить аккаунты"), types.KeyboardButton(text="👤 Профиль"))
    kb.row(types.KeyboardButton(text="💰 Пополнить"), types.KeyboardButton(text="🔐 Получить код"))
    kb.row(types.KeyboardButton(text="🆘 Поддержка"))
    if uid == ADMIN_ID:
        kb.row(types.KeyboardButton(text="➕ Добавить"), types.KeyboardButton(text="⚙️ Редактор"), types.KeyboardButton(text="📢 Рассылка"))
        kb.row(types.KeyboardButton(text="💎 Начислить баланс"))
    return kb.as_markup(resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---
@dp.message(CommandStart())
async def start(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()
    await message.answer("👋 Добро пожаловать в магазин аккаунтов!", reply_markup=main_kb(message.from_user.id))

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        res = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        bal = (await res.fetchone())[0]
    await message.answer(f"👤 **Профиль**\n🆔 ID: `{message.from_user.id}`\n💰 Баланс: **{bal} TON**", parse_mode="Markdown")

# --- ПОПОЛНЕНИЕ ---
@dp.message(F.text == "💰 Пополнить")
async def topup_menu(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="💎 TON (Send App)", callback_data="pay_ton"))
    kb.row(types.InlineKeyboardButton(text="🌟 Stars (Звёзды)", callback_data="pay_stars"))
    await message.answer("Выберите способ оплаты:", reply_markup=kb.as_markup())

# Звёзды (Автоматически + Уведомление админу)
@dp.callback_query(F.data == "pay_stars")
async def pay_stars_cmd(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите количество звёзд (XTR):")
    await state.set_state(ShopStates.wait_topup_stars)

@dp.message(ShopStates.wait_topup_stars)
async def stars_invoice(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        await message.answer_invoice(
            title="Пополнение баланса", description=f"Зачисление {amount * STAR_RATE} TON",
            prices=[LabeledPrice(label="XTR", amount=amount)],
            provider_token="", payload=f"stars_{message.from_user.id}", currency="XTR"
        )
        await state.clear()
    except: await message.answer("Введите целое число.")

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(message: types.Message):
    stars = message.successful_payment.total_amount
    ton = stars * STAR_RATE
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (ton, message.from_user.id))
        await db.commit()
    await message.answer(f"✅ Баланс пополнен на {ton} TON (через Stars)!")
    await bot.send_message(ADMIN_ID, f"🔔 **Оплата Звёздами!**\nЮзер: `{message.from_user.id}`\nСумма: {stars} XTR ({ton} TON).")

# TON (Send App)
@dp.callback_query(F.data == "pay_ton")
async def pay_ton_cmd(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите сумму в TON:")
    await state.set_state(ShopStates.wait_topup_ton)

@dp.message(ShopStates.wait_topup_ton)
async def ton_invoice(message: types.Message, state: FSMContext):
    amount = float(message.text)
    headers = {"X-Token": SEND_TOKEN}
    payload = {"asset": "TON", "amount": str(amount), "description": f"ID {message.from_user.id}"}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{SEND_API_URL}/createInvoice", json=payload, headers=headers) as r:
            res = await r.json()
    if res.get('ok'):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💳 Оплатить", url=res['result']['pay_url']))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить", callback_data=f"chk_{res['result']['invoice_id']}_{amount}"))
        await message.answer(f"Счет на {amount} TON создан:", reply_markup=kb.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("chk_"))
async def chk_ton(callback: types.CallbackQuery):
    _, inv_id, amt = callback.data.split("_")
    headers = {"X-Token": SEND_TOKEN}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{SEND_API_URL}/getInvoices?invoice_ids={inv_id}", headers=headers) as r:
            res = await r.json()
    if res.get('ok') and res['result'][0]['status'] == 'paid':
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amt), callback.from_user.id))
            await db.commit()
        await callback.message.edit_text(f"✅ Зачислено {amt} TON!")
        await bot.send_message(ADMIN_ID, f"💰 Пополнение TON: {amt} от `{callback.from_user.id}`")
    else: await callback.answer("⏳ Оплата не найдена", show_alert=True)

# --- МАГАЗИН ---
@dp.message(F.text == "🛒 Купить аккаунты")
async def shop_geo(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        c = await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")
        rows = await c.fetchall()
    if not rows: return await message.answer("Пусто.")
    kb = InlineKeyboardBuilder()
    for geo, count in rows:
        kb.row(types.InlineKeyboardButton(text=f"📍 {geo} ({count} шт.)", callback_data=f"cat_{geo}"))
    await message.answer("Выберите локацию:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def shop_items(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_NAME) as db:
        c = await db.execute("SELECT id, type, base_stay, date_added, price FROM products WHERE geo = ? AND is_sold = 0", (geo,))
        items = await c.fetchall()
    kb = InlineKeyboardBuilder()
    for i in items:
        stay = get_current_stay(i[2], i[3])
        kb.row(types.InlineKeyboardButton(text=f"⚙️ {i[1]} | ⏳ {stay} дн. | {i[4]} TON", callback_data=f"buy_{i[0]}"))
    await callback.message.edit_text(f"Аккаунты {geo}:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def buy_proc(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    uid = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        p = await (await db.execute("SELECT price, file_id, phone FROM products WHERE id = ?", (pid,))).fetchone()
        u = await (await db.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))).fetchone()

        if u[0] < p[0]: return await callback.answer("❌ Недостаточно TON", show_alert=True)
        
        await callback.answer("⏳ Проверка аккаунта...")
        if not await check_valid(p[1]):
            await db.execute("UPDATE products SET is_sold = 2 WHERE id = ?", (pid,))
            await db.commit()
            await bot.send_message(ADMIN_ID, f"⚠️ Аккаунт {p[2]} сдох. Снят с продажи автоматически.")
            return await callback.message.answer("❌ Этот аккаунт только что был заморожен. Деньги не списаны. Выберите другой.")

        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (p[0], uid))
        await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (pid,))
        await db.commit()
        await callback.message.answer(f"✅ Успешно! Номер: `{p[2]}`")
        await callback.message.answer_document(p[1])

# --- ПОЛУЧИТЬ КОД ---
@dp.message(F.text == "🔐 Получить код")
async def code_st(message: types.Message, state: FSMContext):
    await message.answer("Отправьте файл .session для входа:")
    await state.set_state(ShopStates.wait_session_for_code)

@dp.message(ShopStates.wait_session_for_code, F.document)
async def code_work(message: types.Message, state: FSMContext):
    path = f"u_{message.from_user.id}.session"
    f = await bot.get_file(message.document.file_id)
    await bot.download_file(f.file_path, path)
    
    client = TelegramClient(path, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        await message.answer("❌ Сессия невалидна.")
        await client.disconnect()
        return
    
    user_clients[message.from_user.id] = client
    me = await client.get_me()
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📩 Показать последний код", callback_data="get_last_msg"))
    await message.answer(f"✅ Вход выполнен: `+{me.phone}`", reply_markup=kb.as_markup())
    await state.clear()

@dp.callback_query(F.data == "get_last_msg")
async def show_code(callback: types.CallbackQuery):
    client = user_clients.get(callback.from_user.id)
    if not client: return await callback.answer("Перезайдите в меню.")
    async for msg in client.iter_messages(777000, limit=1):
        await callback.message.answer(f"💬 Сообщение от Telegram:\n\n`{msg.text}`")
        return
    await callback.answer("Кодов нет.")

# --- АДМИН ПАНЕЛЬ ---
@dp.message(F.text == "➕ Добавить", F.from_user.id == ADMIN_ID)
async def adm_add(message: types.Message, state: FSMContext):
    await message.answer("Скинь .session:")
    await state.set_state(ShopStates.wait_acc_file)

@dp.message(ShopStates.wait_acc_file, F.document)
async def adm_f(message: types.Message, state: FSMContext):
    await state.update_data(fid=message.document.file_id, phone=message.document.file_name.replace(".session",""))
    await message.answer("Цена (TON):")
    await state.set_state(ShopStates.wait_acc_price)

@dp.message(ShopStates.wait_acc_price)
async def adm_p(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await message.answer("ГЕО:")
    await state.set_state(ShopStates.wait_acc_geo)

@dp.message(ShopStates.wait_acc_geo)
async def adm_g(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text)
    await message.answer("Базовая отлега (дней):")
    await state.set_state(ShopStates.wait_acc_stay)

@dp.message(ShopStates.wait_acc_stay)
async def adm_s(message: types.Message, state: FSMContext):
    await state.update_data(stay=int(message.text))
    await message.answer("Тип (Авторег/Фиш):")
    await state.set_state(ShopStates.wait_acc_type)

@dp.message(ShopStates.wait_acc_type)
async def adm_end(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, file_id, geo, base_stay, date_added, type) VALUES (?,?,?,?,?,?,?)",
                        (d['phone'], d['price'], d['fid'], d['geo'], d['stay'], datetime.now().strftime("%Y-%m-%d"), message.text))
        await db.commit()
    await message.answer("✅ Товар добавлен!")
    await state.clear()

@dp.message(F.text == "⚙️ Редактор", F.from_user.id == ADMIN_ID)
async def edit_list(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        items = await (await db.execute("SELECT id, phone, price FROM products WHERE is_sold = 0 LIMIT 10")).fetchall()
    kb = InlineKeyboardBuilder()
    for i in items: kb.row(types.InlineKeyboardButton(text=f"ID {i[0]} | {i[1]}", callback_data=f"edit_{i[0]}"))
    await message.answer("Выберите товар:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("edit_"))
async def edit_fields(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(eid=callback.data.split("_")[1])
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="Цена", callback_data="ef_price"), types.InlineKeyboardButton(text="ГЕО", callback_data="ef_geo"))
    await callback.message.edit_text("Что изменить?", reply_markup=kb.as_markup())
    await state.set_state(ShopStates.edit_field)

@dp.callback_query(ShopStates.edit_field)
async def edit_val_st(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(field=callback.data.replace("ef_",""))
    await callback.message.answer("Введите новое значение:")
    await state.set_state(ShopStates.edit_value)

@dp.message(ShopStates.edit_value)
async def edit_final(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE products SET {d['field']} = ? WHERE id = ?", (message.text, d['eid']))
        await db.commit()
    await message.answer("✅ Обновлено!")
    await state.clear()

@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def broad_st(message: types.Message, state: FSMContext):
    await message.answer("Введите текст рассылки:")
    await state.set_state(ShopStates.wait_broadcast)

@dp.message(ShopStates.wait_broadcast)
async def broad_fn(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        users = await (await db.execute("SELECT user_id FROM users")).fetchall()
    ok, err = 0, 0
    for u in users:
        try:
            await bot.send_message(u[0], message.text)
            ok += 1
        except: err += 1
    await message.answer(f"📢 Итог: {ok} получили, {err} заблокировали.")
    await state.clear()

@dp.message(F.text == "💎 Начислить баланс", F.from_user.id == ADMIN_ID)
async def give_bal_st(message: types.Message, state: FSMContext):
    await message.answer("Введите ID пользователя:")
    await state.set_state(ShopStates.wait_bal_id)

@dp.message(ShopStates.wait_bal_id)
async def give_bal_id(message: types.Message, state: FSMContext):
    await state.update_data(target_id=message.text)
    await message.answer("Сколько начислить (TON):")
    await state.set_state(ShopStates.wait_bal_amount)

@dp.message(ShopStates.wait_bal_amount)
async def give_bal_fn(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(message.text), d['target_id']))
        await db.commit()
    await message.answer("✅ Баланс выдан!")
    await state.clear()

@dp.message(F.text == "🆘 Поддержка")
async def support(message: types.Message):
    await message.answer("По всем вопросам: @zyozp")

async def main():
    await init_db()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
