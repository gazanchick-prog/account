import os
import asyncio
import aiosqlite
import aiohttp
import uuid
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery
from telethon import TelegramClient
from dotenv import load_dotenv

# --- НАСТРОЙКИ И КЛЮЧИ ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

SEND_TOKEN = os.getenv("SEND_TOKEN")         # CryptoBot API Token
CACTUS_TOKEN = os.getenv("CACTUS_TOKEN")     # Твой токен CactusPay (3d47a7f2...)

DB_NAME = "sifon_market.db"
RUB_RATE = 100    # 1 TON = 100 рублей
STARS_RATE = 140  # 1 TON = 140 звезд

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- СОСТОЯНИЯ (FSM) ---
class Shop(StatesGroup):
    wait_amt = State()
    wait_session_code = State()
    # Админка
    wait_fmt = State()
    wait_file = State()
    wait_price = State()
    wait_geo = State()
    wait_nuance_choice = State()
    wait_nuance_text = State()
    wait_broadcast = State()
    wait_give_balance_uid = State()
    wait_give_balance_amt = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, total_spent REAL DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, price REAL, 
            file_id TEXT, geo TEXT, format TEXT, nuances TEXT, is_sold INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
            phone TEXT, price REAL, date TEXT)""")
        await db.commit()

# --- КЛАВИАТУРА ИЗ СКРИНШОТА ---
def main_kb(uid):
    kb = ReplyKeyboardBuilder()
    # Ряд 1
    kb.row(types.KeyboardButton(text="🛒 Купить аккаунты"), types.KeyboardButton(text="👤 Профиль"))
    # Ряд 2
    kb.row(types.KeyboardButton(text="💰 Пополнить"), types.KeyboardButton(text="🔐 Получить код"))
    # Ряд 3
    kb.row(types.KeyboardButton(text="📜 Мои покупки"), types.KeyboardButton(text="🏆 Топ покупателей"))
    # Ряд 4
    kb.row(types.KeyboardButton(text="ℹ️ Информация"), types.KeyboardButton(text="🆘 Поддержка"))
    # Ряд 5 (Только для админа)
    if uid == ADMIN_ID:
        kb.row(types.KeyboardButton(text="➕ Добавить"), 
               types.KeyboardButton(text="📢 Рассылка"),
               types.KeyboardButton(text="💎 Выдать баланс"))
    return kb.as_markup(resize_keyboard=True)

# --- ИНФОРМАЦИЯ И ПОДДЕРЖКА ---
@dp.message(F.text == "ℹ️ Информация")
async def info_block(message: types.Message):
    await message.answer("💎 **SifonMarket - магазин telegram аккаунтов**\n⚡️ Мгновенная выдача\n📢 Новости: @sifonnews", parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def support_block(message: types.Message):
    await message.answer("👨‍💻 По всем вопросам и проблемам с аккаунтами писать: @zyozp")

# --- ПРОФИЛЬ И ТОП ---
@dp.message(F.text == "👤 Профиль")
async def profile_block(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        res = await (await db.execute("SELECT balance, total_spent FROM users WHERE user_id = ?", (message.from_user.id,))).fetchone()
    await message.answer(f"🆔 Ваш ID: `{message.from_user.id}`\n💰 Баланс: **{round(res[0], 2)} TON**\n💸 Всего потрачено: **{round(res[1], 2)} TON**", parse_mode="Markdown")

@dp.message(F.text == "🏆 Топ покупателей")
async def top_buyers(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        top = await (await db.execute("SELECT user_id, total_spent FROM users WHERE total_spent > 0 ORDER BY total_spent DESC LIMIT 5")).fetchall()
    if not top: return await message.answer("Топ пока пуст.")
    text = "🏆 **Топ-5 покупателей:**\n\n"
    for i, (uid, spent) in enumerate(top, 1):
        text += f"{i}. ID: `{uid}` — {round(spent, 2)} TON\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📜 Мои покупки")
async def my_purchases(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        purchases = await (await db.execute("SELECT phone, price, date FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 5", (message.from_user.id,))).fetchall()
    if not purchases: return await message.answer("Вы еще ничего не купили.")
    text = "📜 **Последние 5 покупок:**\n\n"
    for p in purchases:
        text += f"📱 `+{p[0]}` | {p[1]} TON | 📅 {p[2]}\n"
    await message.answer(text, parse_mode="Markdown")

# --- ПОПОЛНЕНИЕ БАЛАНСА ---
@dp.message(F.text == "💰 Пополнить")
async def topup_init(message: types.Message, state: FSMContext):
    await state.set_state(Shop.wait_amt)
    await message.answer("Введите сумму в **TON**, на которую хотите пополнить:")

@dp.message(Shop.wait_amt)
async def topup_methods(message: types.Message, state: FSMContext):
    if not message.text.replace('.', '', 1).isdigit(): return await message.answer("Введите число.")
    amt = float(message.text)
    await state.update_data(amt=amt)
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🇷🇺 RUB (Банковская карта)", callback_data="p_rub"))
    kb.row(types.InlineKeyboardButton(text="💎 TON (CryptoBot)", callback_data="p_ton"))
    kb.row(types.InlineKeyboardButton(text=f"⭐️ Stars ({int(amt*STARS_RATE)})", callback_data="p_stars"))
    await message.answer(f"Способ оплаты для пополнения на {amt} TON:", reply_markup=kb.as_markup())

# 1. Оплата RUB (CactusPay - Обновленное API)
@dp.callback_query(F.data == "p_rub")
async def pay_rub(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    rub_sum = data['amt'] * RUB_RATE
    order_id = str(uuid.uuid4())
    
    # Новый формат запроса по документации CactusPay
    payload = {
        "token": CACTUS_TOKEN, 
        "amount": str(rub_sum), 
        "order_id": order_id
    }
    
    async with aiohttp.ClientSession() as s:
        async with s.post("https://lk.cactuspay.pro/api/?method=create", json=payload) as r:
            res = await r.json()
            # Пытаемся достать ссылку (зависит от точного ответа API, обычно это 'url' или 'payment_url')
            pay_url = res.get('url') or res.get('payment_url') or res.get('data', {}).get('url')
            
            if pay_url:
                kb = InlineKeyboardBuilder()
                kb.row(types.InlineKeyboardButton(text="💳 Оплатить RUB", url=pay_url))
                kb.row(types.InlineKeyboardButton(text="✅ Проверить", callback_data=f"chk_k_{order_id}_{data['amt']}"))
                await callback.message.edit_text(f"Счет на {rub_sum} RUB создан:", reply_markup=kb.as_markup())
            else:
                await callback.message.edit_text(f"Ошибка создания платежа. Ответ API: {res}")
    await callback.answer()

@dp.callback_query(F.data.startswith("chk_k_"))
async def check_kaktus(callback: types.CallbackQuery):
    _, _, order_id, amt = callback.data.split("_")
    # Эндпоинт проверки статуса (примерный, нужно сверить с доками CactusPay "Информация по платежу")
    payload = {"token": CACTUS_TOKEN, "order_id": order_id}
    
    async with aiohttp.ClientSession() as s:
        async with s.post("https://lk.cactuspay.pro/api/?method=info", json=payload) as r:
            res = await r.json()
            status = res.get('status') or res.get('data', {}).get('status')
            if status in ['paid', 'success', 1]: # Успешные статусы
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amt), callback.from_user.id))
                    await db.commit()
                await callback.message.edit_text("✅ Баланс успешно пополнен через RUB!")
            else:
                await callback.answer("Счет еще не оплачен", show_alert=True)

# 2. Оплата TON
@dp.callback_query(F.data == "p_ton")
async def pay_ton(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    headers = {"Crypto-Pay-API-Token": SEND_TOKEN}
    payload = {"asset": "TON", "amount": str(data['amt'])}
    async with aiohttp.ClientSession() as s:
        async with s.post("https://pay.crypt.bot/api/createInvoice", json=payload, headers=headers) as r:
            res = await r.json()
            if res.get('ok'):
                kb = InlineKeyboardBuilder()
                kb.row(types.InlineKeyboardButton(text="💎 Оплатить TON", url=res['result']['pay_url']))
                kb.row(types.InlineKeyboardButton(text="✅ Проверить", callback_data=f"chk_t_{res['result']['invoice_id']}_{data['amt']}"))
                await callback.message.edit_text(f"Счет на {data['amt']} TON создан:", reply_markup=kb.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("chk_t_"))
async def check_ton(callback: types.CallbackQuery):
    _, _, inv_id, amt = callback.data.split("_")
    headers = {"Crypto-Pay-API-Token": SEND_TOKEN}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://pay.crypt.bot/api/getInvoices?invoice_ids={inv_id}", headers=headers) as r:
            res = await r.json()
            if res.get('ok') and res['result']['items'][0]['status'] == 'paid':
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amt), callback.from_user.id))
                    await db.commit()
                await callback.message.edit_text("✅ Баланс успешно пополнен!")
            else:
                await callback.answer("Счет еще не оплачен", show_alert=True)

# 3. Оплата Stars
@dp.callback_query(F.data == "p_stars")
async def pay_stars(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    stars_amt = int(data['amt'] * STARS_RATE)
    await bot.send_invoice(chat_id=callback.from_user.id, title="Пополнение баланса TON",
                           description=f"{stars_amt} звезд = {data['amt']} TON",
                           payload=f"stars_{data['amt']}", provider_token="", currency="XTR",
                           prices=[LabeledPrice(label="Пополнение", amount=stars_amt)])
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout_stars(pre_checkout: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)

@dp.message(F.successful_payment)
async def success_stars(message: types.Message):
    amt = float(message.successful_payment.invoice_payload.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, message.from_user.id))
        await db.commit()
    await message.answer(f"✅ Баланс пополнен на {amt} TON за Звезды!")

# --- МАГАЗИН И ПОКУПКА ---
@dp.message(F.text == "🛒 Купить аккаунты")
async def shop_browse(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        geos = await (await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")).fetchall()
    if not geos: return await message.answer("📦 Товара пока нет в наличии.")
    kb = InlineKeyboardBuilder()
    for g, c in geos: kb.row(types.InlineKeyboardButton(text=f"📍 {g} ({c} шт.)", callback_data=f"geo_{g}"))
    await message.answer("🌍 Выберите страну:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("geo_"))
async def shop_items(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_NAME) as db:
        items = await (await db.execute("SELECT id, price, format FROM products WHERE geo = ? AND is_sold = 0 LIMIT 10", (geo,))).fetchall()
    kb = InlineKeyboardBuilder()
    for i in items: kb.row(types.InlineKeyboardButton(text=f"[{i[2]}] Цена: {i[1]} TON", callback_data=f"pre_{i[0]}"))
    await callback.message.edit_text(f"Доступные аккаунты ГЕО {geo}:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("pre_"))
async def buy_confirm(callback: types.CallbackQuery):
    pid = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_NAME) as db:
        p = await (await db.execute("SELECT price, nuances, format FROM products WHERE id = ?", (pid,))).fetchone()
    text = f"🛒 **Покупка товара**\n\nФормат: {p[2]}\nЦена: {p[0]} TON\n"
    if p[1]: text += f"\n⚠️ **Нюансы аккаунта:**\n{p[1]}"
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Купить", callback_data=f"buy_{pid}"))
    kb.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_buy"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "cancel_buy")
async def cancel_buy(callback: types.CallbackQuery):
    await callback.message.delete()

@dp.callback_query(F.data.startswith("buy_"))
async def buy_final(callback: types.CallbackQuery):
    pid = callback.data.split("_")[1]
    uid = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        p = await (await db.execute("SELECT price, file_id, phone FROM products WHERE id = ? AND is_sold = 0", (pid,))).fetchone()
        if not p: return await callback.message.edit_text("❌ Этот товар уже купили или он снят с продажи.")
        
        u = await (await db.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))).fetchone()
        if u[0] < p[0]: return await callback.answer("Недостаточно средств на балансе!", show_alert=True)
        
        # Списываем баланс и увеличиваем total_spent для Топа
        await db.execute("UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE user_id = ?", (p[0], p[0], uid))
        await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (pid,))
        await db.execute("INSERT INTO purchases (user_id, phone, price, date) VALUES (?,?,?,?)", (uid, p[2], p[0], datetime.now().strftime("%d.%m %H:%M")))
        await db.commit()
        
        await callback.message.answer(f"✅ Покупка успешна! Номер: `+{p[2]}`", parse_mode="Markdown")
        await callback.message.answer_document(p[1])
        await callback.message.delete()

# --- СЕРВИС: ПОЛУЧЕНИЕ КОДА ---
@dp.message(F.text == "🔐 Получить код")
async def code_start(message: types.Message, state: FSMContext):
    await state.set_state(Shop.wait_session_code)
    await message.answer("Пришлите купленный `.session` файл, чтобы я вытащил код для входа:")

@dp.message(Shop.wait_session_code, F.document)
async def code_proc(message: types.Message, state: FSMContext):
    path = f"{message.from_user.id}_{message.document.file_name}"
    f = await bot.get_file(message.document.file_id)
    await bot.download_file(f.file_path, path)
    client = TelegramClient(path, API_ID, API_HASH)
    try:
        await client.connect()
        async for m in client.iter_messages(777000, limit=1):
            await message.answer(f"📩 Последнее сервисное сообщение:\n\n`{m.text}`", parse_mode="Markdown")
            break
        else:
            await message.answer("Пусто. Сообщений от Telegram нет.")
    except Exception: 
        await message.answer("❌ Ошибка входа в сессию. Аккаунт мертв или файл поврежден.")
    finally:
        await client.disconnect()
        if os.path.exists(path): os.remove(path)
        await state.clear()

# --- АДМИНКА ---
@dp.message(F.text == "➕ Добавить", F.from_user.id == ADMIN_ID)
async def adm_start(message: types.Message, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text=".session", callback_data="f_session"), types.InlineKeyboardButton(text="tdata", callback_data="f_tdata"))
    await message.answer("Формат аккаунта:", reply_markup=kb.as_markup())
    await state.set_state(Shop.wait_fmt)

@dp.callback_query(Shop.wait_fmt)
async def adm_file(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(format=callback.data.split("_")[1])
    await callback.message.answer("Отправьте файл в бот (название = номер телефона):")
    await state.set_state(Shop.wait_file)

@dp.message(Shop.wait_file, F.document)
async def adm_price(message: types.Message, state: FSMContext):
    phone = message.document.file_name.split('.')[0].replace("+", "")
    await state.update_data(fid=message.document.file_id, phone=phone)
    await message.answer("Цена в TON:")
    await state.set_state(Shop.wait_price)

@dp.message(Shop.wait_price)
async def adm_geo(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await message.answer("ГЕО (например: RU, KZ):")
    await state.set_state(Shop.wait_geo)

@dp.message(Shop.wait_geo)
async def adm_nuance_ask(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text.upper())
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="Есть", callback_data="n_yes"), types.InlineKeyboardButton(text="Нет", callback_data="n_no"))
    await message.answer("Есть нюансы?", reply_markup=kb.as_markup())
    await state.set_state(Shop.wait_nuance_choice)

@dp.callback_query(Shop.wait_nuance_choice)
async def adm_nuance_logic(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "n_yes":
        await callback.message.answer("Напишите текст нюанса:")
        await state.set_state(Shop.wait_nuance_text)
    else:
        await save_product(callback.message, state, None)
    await callback.answer()

@dp.message(Shop.wait_nuance_text)
async def adm_nuance_final(message: types.Message, state: FSMContext):
    await save_product(message, state, message.text)

async def save_product(message, state, nuance_text):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, file_id, geo, format, nuances) VALUES (?,?,?,?,?,?)",
                        (d['phone'], d['price'], d['fid'], d['geo'], d['format'], nuance_text))
        await db.commit()
    await message.answer("✅ Товар добавлен!")
    await state.clear()

# --- АДМИНКА: РАССЫЛКА И БАЛАНС ---
@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def adm_broadcast(message: types.Message, state: FSMContext):
    await message.answer("Отправьте сообщение для рассылки всем пользователям:")
    await state.set_state(Shop.wait_broadcast)

@dp.message(Shop.wait_broadcast)
async def send_broadcast(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        users = await (await db.execute("SELECT user_id FROM users")).fetchall()
    count = 0
    for u in users:
        try:
            await bot.send_message(u[0], message.text, parse_mode="Markdown")
            count += 1
        except: pass
    await message.answer(f"✅ Рассылка завершена. Доставлено: {count} пользователям.")
    await state.clear()

@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
async def adm_give_bal(message: types.Message, state: FSMContext):
    await message.answer("Введите ID пользователя:")
    await state.set_state(Shop.wait_give_balance_uid)

@dp.message(Shop.wait_give_balance_uid)
async def adm_give_bal_uid(message: types.Message, state: FSMContext):
    await state.update_data(target_uid=int(message.text))
    await message.answer("Введите сумму в TON для выдачи:")
    await state.set_state(Shop.wait_give_balance_amt)

@dp.message(Shop.wait_give_balance_amt)
async def adm_give_bal_final(message: types.Message, state: FSMContext):
    amt = float(message.text)
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, data['target_uid']))
        await db.commit()
    await message.answer(f"✅ Выдано {amt} TON пользователю {data['target_uid']}.")
    try:
        await bot.send_message(data['target_uid'], f"🎁 пополнение от администрации: **{amt} TON**", parse_mode="Markdown")
    except: pass
    await state.clear()

# --- СТАРТ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()
    await message.answer("👋 Добро пожаловать в SifonMarket!", reply_markup=main_kb(message.from_user.id))

async def main():
    await init_db()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
