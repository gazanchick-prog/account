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
BOT_TOKEN = "8796403308:AAGbI4AP00VVuJlUQgwweigNu58o-kdGyPM"
ADMIN_ID = 8212981789
SUPPORT_LINK = "https://t.me/zyozp"

# ДАННЫЕ TELETHON (Обязательно укажи свои из my.telegram.org)
API_ID = 1234567 
API_HASH = 'твой_хэш_здесь'

# ДАННЫЕ TON ИЗ ТВОИХ СКРИНШОТОВ
TONCENTER_API_KEY = "0e458295f7b90487efe40b089ee219a0d6faa842cba6c3dee5046de3db1532f"
MY_WALLET = "UQDlFKmdWxZqtT1ueKC58L6Kj77RLY6tGu3wW_aaZHGXt46O"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('sifon_shop.db')
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
    conn = sqlite3.connect('sifon_shop.db')
    cur = conn.cursor()
    cur.execute(sql, params)
    res = None
    if fetchone: res = cur.fetchone()
    if fetchall: res = cur.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

# --- СОСТОЯНИЯ ---
class ShopStates(StatesGroup):
    add_geo = State()
    add_type = State()
    add_age = State()
    add_price = State()
    add_file = State()
    broadcast_msg = State()
    manual_refill_id = State()
    manual_refill_amt = State()
    quiz_ans = State()
    quiz_prize = State()

quiz_active = {"ans": None, "prize": None, "active": False}

# --- КЛАВИАТУРЫ ---
def main_kb(user_id):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🛒 Купить", callback_data="catalog"),
                types.InlineKeyboardButton(text="🛍 Мои покупки", callback_data="my_orders"))
    builder.row(types.InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
                types.InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"))
    if user_id == ADMIN_ID:
        builder.row(types.InlineKeyboardButton(text="➕ Добавить", callback_data="admin_add"),
                    types.InlineKeyboardButton(text="💰 Начислить", callback_data="admin_refill"))
        builder.row(types.InlineKeyboardButton(text="🎁 Викторина", callback_data="admin_quiz"),
                    types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    return builder.as_markup()

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def start(m: types.Message):
    db_query("INSERT OR IGNORE INTO users (id) VALUES (?)", (m.from_user.id,), commit=True)
    await m.answer("👋 Добро пожаловать в **SifonShop**!", reply_markup=main_kb(m.from_user.id), parse_mode="Markdown")

# ПРОВЕРКА ВИКТОРИНЫ
@dp.message(lambda m: quiz_active["active"])
async def check_quiz(m: types.Message):
    if m.text.lower() == quiz_active["ans"]:
        quiz_active["active"] = False
        await m.answer("🎉 **ПРАВИЛЬНО!** Ты угадал. Вот твой приз:")
        await bot.send_document(m.from_user.id, quiz_active["prize"])
        await bot.send_message(ADMIN_ID, f"👤 @{m.from_user.username} (ID: {m.from_user.id}) выиграл в викторине!")

@dp.callback_query(F.data == "profile")
async def profile(c: types.CallbackQuery):
    u = db_query("SELECT balance FROM users WHERE id = ?", (c.from_user.id,), fetchone=True)
    await c.message.edit_text(f"👤 **Профиль**\n\n🆔 ID: `{c.from_user.id}`\n💰 Баланс: `{u[0]} TON`", 
                              reply_markup=main_kb(c.from_user.id), parse_mode="Markdown")

# ПОПОЛНЕНИЕ
@dp.callback_query(F.data == "deposit")
async def deposit_choose(c: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="💎 TON (Автоматически)", callback_data="dep_ton"))
    b.row(types.InlineKeyboardButton(text="⭐ Stars (Звезды)", callback_data="dep_stars"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="profile"))
    await c.message.edit_text("Выбери метод оплаты:", reply_markup=b.as_markup())

@dp.callback_query(F.data == "dep_ton")
async def dep_ton(c: types.CallbackQuery):
    msg = (f"💠 **Пополнение TON**\n\nПереведи сумму на адрес:\n`{MY_WALLET}`\n\n"
           f"⚠️ **КОММЕНТАРИЙ:** `{c.from_user.id}`\n\n"
           f"Бот проверит транзакцию автоматически в течение минуты.")
    await c.message.edit_text(msg, parse_mode="Markdown")

@dp.callback_query(F.data == "dep_stars")
async def dep_stars(c: types.CallbackQuery):
    await c.message.answer_invoice(
        title="Пополнение баланса", description="Зачисление на внутренний счет",
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
    await m.answer(f"✅ Баланс успешно пополнен на {amount} Stars!")

# АДМИНКА: ВИКТОРИНА
@dp.callback_query(F.data == "admin_quiz", F.from_user.id == ADMIN_ID)
async def q_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введите ГЕО или слово для викторины:")
    await state.set_state(ShopStates.quiz_ans)

@dp.message(ShopStates.quiz_ans)
async def q_ans(m, state):
    await state.update_data(ans=m.text.lower())
    await m.answer("Отправь .session файл для победителя:")
    await state.set_state(ShopStates.quiz_prize)

@dp.message(ShopStates.quiz_prize, F.document)
async def q_prize(m, state):
    d = await state.get_data()
    quiz_active.update({"ans": d['ans'], "prize": m.document.file_id, "active": True})
    await m.answer(f"🚀 Викторина активна! Жду ответ: {d['ans']}")
    await state.clear()

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

async def main():
    init_db()
    asyncio.create_task(ton_poller())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
