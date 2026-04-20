import asyncio
import sqlite3
import logging
import os
import re
import requests
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import LabeledPrice
from telethon import TelegramClient

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8773069226:AAG9a5O7COF4eben7TEzwO6yHg79dDEakRU"
ADMIN_ID = 8212981789
SUPPORT_LINK = "https://t.me/zyozp"

# TELETHON (ОБЯЗАТЕЛЬНО ВПИШИ СВОИ ДАННЫЕ)
API_ID = 37668790 
API_HASH = '84a0450f9bbf15d1e1d09b47ee25cb49'

# TON (ИЗ ТВОИХ ДАННЫХ)
TONCENTER_API_KEY = "0e458295f7b90487efe40b089ee219a0d6faa842cba6c3dee5046de3db1532f"
MY_WALLET = "UQDlFKmdWxZqtT1ueKC58L6Kj77RLY6tGu3wW_aaZHGXt46O"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('sifonmarket.db') # ИЗМЕНЕНО НА sifonmarket
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, total_spent REAL DEFAULT 0)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS accounts 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, geo TEXT, type TEXT, age TEXT, price REAL, file_id TEXT, is_sold INTEGER DEFAULT 0)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS purchases 
                   (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, file_id TEXT, info TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS processed_tx (tx_hash TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()

def db_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('sifonmarket.db')
    cur = conn.cursor()
    cur.execute(sql, params)
    res = None
    if fetchone: res = cur.fetchone()
    if fetchall: res = cur.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

# --- СОСТОЯНИЯ ---
class AddAccount(StatesGroup):
    geo = State()
    type = State()
    age = State()
    price = State()
    file = State()

class ManualDeposit(StatesGroup):
    uid = State()
    amount = State()

class Broadcast(StatesGroup):
    msg = State()

class QuizState(StatesGroup):
    ans = State()
    prize = State()

quiz_data = {"ans": None, "prize": None, "active": False}

# --- ЛОГИКА TELETHON ---
async def get_acc_info(session_path):
    client = TelegramClient(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        me = await client.get_me()
        return f"+{me.phone}" if me else "Неизвестно"
    except: 
        return "Ошибка доступа (сессия мертва или нужен API_ID)"
    finally: 
        await client.disconnect()

async def get_last_codes(session_path):
    client = TelegramClient(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        messages = []
        async for message in client.iter_messages(777000, limit=2):
            code = re.findall(r'\b\d{5}\b', message.text)
            msg_date = message.date.strftime("%d.%m %H:%M")
            if code:
                messages.append(f"🔢 Код: `{code[0]}` ({msg_date})")
            else:
                messages.append(f"📩 Сообщение без кода ({msg_date})")
        return "\n".join(messages) if messages else "Сообщений с кодами нет."
    except Exception as e:
        return f"Ошибка при чтении: {e}"
    finally: 
        await client.disconnect()

# --- КЛАВИАТУРЫ ---
def main_kb(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🛒 Купить", callback_data="catalog"),
                types.InlineKeyboardButton(text="🛍 Мои покупки", callback_data="my_orders"))
    builder.row(types.InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
                types.InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"))
    builder.row(types.InlineKeyboardButton(text="🆘 Поддержка", url=SUPPORT_LINK))
    if user_id == ADMIN_ID:
        builder.row(types.InlineKeyboardButton(text="➕ Аккаунт", callback_data="admin_add"),
                    types.InlineKeyboardButton(text="💰 Выдать баланс", callback_data="admin_refill"))
        builder.row(types.InlineKeyboardButton(text="🎁 Викторина", callback_data="admin_quiz"),
                    types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    return builder.as_markup()

# --- ОСНОВНЫЕ ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def start(m: types.Message):
    db_query("INSERT OR IGNORE INTO users (id) VALUES (?)", (m.from_user.id,), commit=True)
    await m.answer("👋 Добро пожаловать в **SifonMarket**!", reply_markup=main_kb(m.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "profile")
async def profile(c: types.CallbackQuery):
    u = db_query("SELECT balance, total_spent FROM users WHERE id = ?", (c.from_user.id,), fetchone=True)
    await c.message.edit_text(f"👤 **Профиль**\n\n🆔 ID: `{c.from_user.id}`\n💰 Баланс: `{u[0]} TON`\n🛒 Потрачено: `{u[1]} TON`", 
                              reply_markup=main_kb(c.from_user.id), parse_mode="Markdown")

# --- КАТАЛОГ И ПОКУПКА ---
@dp.callback_query(F.data == "catalog")
async def catalog(c: types.CallbackQuery):
    accs = db_query("SELECT geo, type, age, price, COUNT(*) FROM accounts WHERE is_sold = 0 GROUP BY geo, type, age, price", fetchall=True)
    if not accs: 
        return await c.answer("Товаров пока нет 😔", show_alert=True)
    
    b = InlineKeyboardBuilder()
    for a in accs:
        b.row(types.InlineKeyboardButton(text=f"{a[0]} | {a[1]} | {a[3]} TON ({a[4]}шт)", callback_data=f"buy_{a[0]}_{a[3]}"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="profile"))
    await c.message.edit_text("📦 **Каталог аккаунтов:**", reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("buy_"))
async def buy(c: types.CallbackQuery):
    _, geo, price = c.data.split("_")
    price = float(price)
    bal = db_query("SELECT balance FROM users WHERE id = ?", (c.from_user.id,), fetchone=True)[0]
    
    if bal < price: 
        return await c.answer("Недостаточно средств! Пополните баланс.", show_alert=True)
    
    acc = db_query("SELECT id, file_id, geo, type FROM accounts WHERE geo = ? AND price = ? AND is_sold = 0 LIMIT 1", (geo, price), fetchone=True)
    if acc:
        db_query("UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE id = ?", (price, price, c.from_user.id), commit=True)
        db_query("UPDATE accounts SET is_sold = 1 WHERE id = ?", (acc[0],), commit=True)
        db_query("INSERT INTO purchases (user_id, file_id, info) VALUES (?, ?, ?)", (c.from_user.id, acc[1], f"{acc[2]} | {acc[3]}"), commit=True)
        
        await bot.send_document(c.from_user.id, acc[1], caption="✅ Успешная покупка!\nФайл сессии выше. Для получения кодов перейдите в 'Мои покупки'.")
        await c.answer("Успешно куплено!")
    else:
        await c.answer("Этот товар только что закончился 😔", show_alert=True)

# --- МОИ ПОКУПКИ (С КОДАМИ TELETHON) ---
@dp.callback_query(F.data == "my_orders")
async def my_orders(c: types.CallbackQuery):
    orders = db_query("SELECT id, info FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 5", (c.from_user.id,), fetchall=True)
    if not orders: 
        return await c.answer("У вас еще нет покупок", show_alert=True)
    
    b = InlineKeyboardBuilder()
    for o in orders:
        b.row(types.InlineKeyboardButton(text=f"📦 {o[1]}", callback_data=f"show_acc_{o[0]}"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="profile"))
    await c.message.edit_text("🛍 **Ваши последние покупки:**", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("show_acc_"))
async def show_account_info(c: types.CallbackQuery):
    order_id = c.data.split("_")[2]
    file_id = db_query("SELECT file_id FROM purchases WHERE id = ?", (order_id,), fetchone=True)[0]
    
    wait = await c.message.answer("⏳ Читаю данные аккаунта...")
    path = f"info_{order_id}.session"
    f = await bot.get_file(file_id)
    await bot.download_file(f.file_path, path)
    
    phone = await get_acc_info(path)
    if os.path.exists(path): os.remove(path)
    
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="📩 Получить код", callback_data=f"view_codes_{order_id}"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="my_orders"))
    await wait.edit_text(f"📱 **Аккаунт:**\n\n**Номер:** `{phone}`\n\nВведите номер в Telegram и нажмите 'Получить код'.", 
                         reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("view_codes_"))
async def view_codes_call(c: types.CallbackQuery):
    order_id = c.data.split("_")[2]
    file_id = db_query("SELECT file_id FROM purchases WHERE id = ?", (order_id,), fetchone=True)[0]
    
    wait = await c.message.answer("⏳ Читаю сообщения...")
    path = f"code_{order_id}.session"
    f = await bot.get_file(file_id)
    await bot.download_file(f.file_path, path)
    
    codes_history = await get_last_codes(path)
    if os.path.exists(path): os.remove(path)
    
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🔄 Обновить", callback_data=f"view_codes_{order_id}"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"show_acc_{order_id}"))
    await wait.edit_text(f"📜 **Коды:**\n\n{codes_history}", reply_markup=b.as_markup(), parse_mode="Markdown")

# --- ПОПОЛНЕНИЕ (TON + STARS) ---
@dp.callback_query(F.data == "deposit")
async def deposit_choose(c: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="💎 TON (Кошелек)", callback_data="dep_ton"))
    b.row(types.InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="dep_stars"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="profile"))
    await c.message.edit_text("Выбери метод оплаты:", reply_markup=b.as_markup())

@dp.callback_query(F.data == "dep_ton")
async def dep_ton(c: types.CallbackQuery):
    msg = (f"💠 **Пополнение TON**\n\nПереведи TON на адрес:\n`{MY_WALLET}`\n\n"
           f"⚠️ **В КОММЕНТАРИЙ К ПЛАТЕЖУ ВПИШИ СВОЙ ID:** `{c.from_user.id}`\n\n"
           f"Бот проверит перевод и зачислит баланс в течение 1 минуты.")
    await c.message.edit_text(msg, parse_mode="Markdown")

@dp.callback_query(F.data == "dep_stars")
async def dep_stars(c: types.CallbackQuery):
    await c.message.answer_invoice(
        title="Пополнение баланса", description="Зачисление звезд на баланс",
        prices=[LabeledPrice(label="⭐ 50 Stars", amount=50)],
        provider_token="", payload=f"stars_{c.from_user.id}", currency="XTR"
    )

@dp.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: types.Message):
    amount = m.successful_payment.total_amount
    db_query("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, m.from_user.id), commit=True)
    await m.answer(f"✅ Баланс пополнен на {amount} Stars!")

# --- АДМИНКА ---

# 1. ДОБАВЛЕНИЕ АККАУНТА
@dp.callback_query(F.data == "admin_add", F.from_user.id == ADMIN_ID)
async def ad_add(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("ГЕО:")
    await state.set_state(AddAccount.geo)

@dp.message(AddAccount.geo)
async def ad_geo(m, state):
    await state.update_data(geo=m.text)
    await m.answer("Тип:")
    await state.set_state(AddAccount.type)

@dp.message(AddAccount.type)
async def ad_type(m, state):
    await state.update_data(type=m.text)
    await m.answer("Отлега:")
    await state.set_state(AddAccount.age)

@dp.message(AddAccount.age)
async def ad_age(m, state):
    await state.update_data(age=m.text)
    await m.answer("Цена (TON):")
    await state.set_state(AddAccount.price)

@dp.message(AddAccount.price)
async def ad_pr(m, state):
    await state.update_data(price=float(m.text))
    await m.answer("Скинь .session файл:")
    await state.set_state(AddAccount.file)

@dp.message(AddAccount.file, F.document)
async def ad_file(m: types.Message, state: FSMContext):
    d = await state.get_data()
    db_query("INSERT INTO accounts (geo, type, age, price, file_id) VALUES (?, ?, ?, ?, ?)", 
             (d['geo'], d['type'], d['age'], d['price'], m.document.file_id), commit=True)
    await m.answer("✅ Аккаунт добавлен в каталог!")
    await state.clear()

# 2. РУЧНОЕ ПОПОЛНЕНИЕ
@dp.callback_query(F.data == "admin_refill", F.from_user.id == ADMIN_ID)
async def ad_ref(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("ID юзера:")
    await state.set_state(ManualDeposit.uid)

@dp.message(ManualDeposit.uid)
async def ad_ref_id(m, state):
    await state.update_data(uid=m.text)
    await m.answer("Сумма TON:")
    await state.set_state(ManualDeposit.amount)

@dp.message(ManualDeposit.amount)
async def ad_ref_fin(m: types.Message, state: FSMContext):
    d = await state.get_data()
    amt = float(m.text)
    db_query("UPDATE users SET balance = balance + ? WHERE id = ?", (amt, d['uid']), commit=True)
    await m.answer(f"✅ Выдано {amt} TON")
    try: await bot.send_message(d['uid'], f"💰 Админ зачислил вам `{amt} TON`.", parse_mode="Markdown")
    except: pass
    await state.clear()

# 3. РАССЫЛКА
@dp.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def ad_broad(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("📣 Отправь текст/фото для рассылки:")
    await state.set_state(Broadcast.msg)

@dp.message(Broadcast.msg, F.from_user.id == ADMIN_ID)
async def ad_broad_send(m: types.Message, state: FSMContext):
    users = db_query("SELECT id FROM users", fetchall=True)
    count = 0
    await m.answer(f"⏳ Начинаю рассылку ({len(users)} чел)...")
    for u in users:
        try:
            await m.copy_to(u[0])
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await m.answer(f"✅ Рассылка завершена!\nДоставлено: {count}")
    await state.clear()

# 4. ВИКТОРИНА
@dp.callback_query(F.data == "admin_quiz", F.from_user.id == ADMIN_ID)
async def q_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введите правильный ответ на викторину (ГЕО/Слово):")
    await state.set_state(QuizState.ans)

@dp.message(QuizState.ans)
async def q_ans(m, state):
    await state.update_data(ans=m.text.lower())
    await m.answer("Скинь .session файл, который получит победитель:")
    await state.set_state(QuizState.prize)

@dp.message(QuizState.prize, F.document)
async def q_prize(m, state):
    d = await state.get_data()
    quiz_data.update({"ans": d['ans'], "prize": m.document.file_id, "active": True})
    await m.answer(f"🚀 Викторина запущена! Жду в чате: {d['ans']}")
    await state.clear()

# --- ОБРАБОТЧИК ВИКТОРИНЫ (ПЕРЕХВАТ ТЕКСТА) ---
@dp.message(lambda m: quiz_data["active"])
async def check_quiz_guess(m: types.Message):
    if m.text and m.text.lower() == quiz_data["ans"]:
        quiz_data["active"] = False
        await m.answer("🎉 **ПРАВИЛЬНО!** Ты угадал. Вот твой приз:")
        await bot.send_document(m.from_user.id, quiz_data["prize"])
        await bot.send_message(ADMIN_ID, f"👤 @{m.from_user.username} (ID: {m.from_user.id}) выиграл в викторине!")

# --- ФОНОВАЯ ПРОВЕРКА TON ---
async def ton_poller():
    while True:
        try:
            url = f"https://toncenter.com/api/v2/getTransactions?address={MY_WALLET}&limit=15&api_key={TONCENTER_API_KEY}"
            res = requests.get(url).json()
            if res.get("ok"):
                for tx in res["result"]:
                    tx_hash = tx.get("transaction_id", {}).get("hash")
                    msg = tx.get("in_msg", {}).get("message", "")
                    value = int(tx.get("in_msg", {}).get("value", 0)) / 10**9
                    
                    if msg.isdigit() and value > 0:
                        uid = int(msg)
                        exists = db_query("SELECT 1 FROM processed_tx WHERE tx_hash = ?", (tx_hash,), fetchone=True)
                        if not exists:
                            db_query("UPDATE users SET balance = balance + ? WHERE id = ?", (value, uid), commit=True)
                            db_query("INSERT INTO processed_tx (tx_hash) VALUES (?)", (tx_hash,), commit=True)
                            try: await bot.send_message(uid, f"💎 На ваш баланс зачислено {value} TON!")
                            except: pass
        except Exception as e:
            logging.error(f"TON Poller error: {e}")
        await asyncio.sleep(45)

# --- ЗАПУСК ---
async def main():
    init_db()
    asyncio.create_task(ton_poller())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
