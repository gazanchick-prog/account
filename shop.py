import asyncio
import sqlite3
import logging
import os
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from telethon import TelegramClient

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8773069226:AAG9a5O7COF4eben7TEzwO6yHg79dDEakRU" # Обязательно смени потом!
ADMIN_ID = 8212981789
SUPPORT_LINK = "https://t.me/zyozp"

# ОБЯЗАТЕЛЬНО ПОЛУЧИ НА my.telegram.org
API_ID = 1234567 # ЗАМЕНИ НА СВОЕ
API_HASH = 'твой_хэш' # ЗАМЕНИ НА СВОЕ

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
class AddAccount(StatesGroup):
    geo = State()
    type = State()
    age = State()
    price = State()
    file = State()

class ManualDeposit(StatesGroup):
    user_id = State()
    amount = State()

class Broadcast(StatesGroup):
    msg = State()

# --- ЛОГИКА TELETHON ---
async def get_acc_info(session_path):
    client = TelegramClient(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        me = await client.get_me()
        return f"+{me.phone}" if me else "Неизвестно"
    except: 
        return "Ошибка доступа (возможно сессия мертва)"
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
                messages.append(f"🔢 Код: `{code[0]}` (Получен: {msg_date})")
            else:
                messages.append(f"📩 Сообщение без кода ({msg_date})")
        return "\n".join(messages) if messages else "Сообщений от Telegram нет."
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
        builder.row(types.InlineKeyboardButton(text="➕ Добавить", callback_data="admin_add"),
                    types.InlineKeyboardButton(text="💰 Начислить", callback_data="admin_refill"))
        builder.row(types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    return builder.as_markup()

# --- ХЕНДЛЕРЫ ЮЗЕРА ---
@dp.message(Command("start"))
async def start(m: types.Message):
    db_query("INSERT OR IGNORE INTO users (id) VALUES (?)", (m.from_user.id,), commit=True)
    await m.answer("👋 Добро пожаловать в **SifonShop**!", reply_markup=main_kb(m.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "profile")
async def profile(c: types.CallbackQuery):
    u = db_query("SELECT balance, total_spent FROM users WHERE id = ?", (c.from_user.id,), fetchone=True)
    await c.message.edit_text(f"👤 **Профиль**\n\n🆔 ID: `{c.from_user.id}`\n💰 Баланс: `{u[0]} TON`\n🛒 Потрачено: `{u[1]} TON`", 
                              reply_markup=main_kb(c.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "catalog")
async def catalog(c: types.CallbackQuery):
    accs = db_query("SELECT geo, type, age, price, COUNT(*) FROM accounts WHERE is_sold = 0 GROUP BY geo, type, age, price", fetchall=True)
    if not accs: 
        return await c.answer("Товаров нет", show_alert=True)
    
    b = InlineKeyboardBuilder()
    for a in accs:
        b.row(types.InlineKeyboardButton(text=f"{a[0]} | {a[1]} | {a[3]} TON ({a[4]}шт)", callback_data=f"buy_{a[0]}_{a[3]}"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="profile"))
    await c.message.edit_text("📦 **Каталог:**", reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("buy_"))
async def buy(c: types.CallbackQuery):
    _, geo, price = c.data.split("_")
    bal = db_query("SELECT balance FROM users WHERE id = ?", (c.from_user.id,), fetchone=True)[0]
    
    if bal < float(price): 
        return await c.answer("Недостаточно средств!", show_alert=True)
    
    acc = db_query("SELECT id, file_id, geo, type FROM accounts WHERE geo = ? AND price = ? AND is_sold = 0 LIMIT 1", (geo, price), fetchone=True)
    if acc:
        db_query("UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE id = ?", (price, price, c.from_user.id), commit=True)
        db_query("UPDATE accounts SET is_sold = 1 WHERE id = ?", (acc[0],), commit=True)
        db_query("INSERT INTO purchases (user_id, file_id, info) VALUES (?, ?, ?)", (c.from_user.id, acc[1], f"{acc[2]} | {acc[3]}"), commit=True)
        
        await bot.send_document(c.from_user.id, acc[1], caption="✅ Успешная покупка!\nФайл сессии выше. Для получения кодов перейдите в 'Мои покупки'.")
        await c.answer("Куплено!")
    else:
        await c.answer("Товар закончился.")

# --- ПОПОЛНЕНИЕ (РУЧНОЕ) ---
@dp.callback_query(F.data == "deposit")
async def dep_manual(c: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="👨‍💻 Написать в поддержку", url=SUPPORT_LINK))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="profile"))
    
    text = (f"💳 **Пополнение баланса**\n\n"
            f"В данный момент автоматическое пополнение отключено.\n"
            f"Для пополнения свяжитесь с поддержкой и укажите ваш ID.\n\n"
            f"Ваш ID: `{c.from_user.id}`")
    
    await c.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="Markdown")

# --- МОИ ПОКУПКИ И КОДЫ ---
@dp.callback_query(F.data == "my_orders")
async def my_orders(c: types.CallbackQuery):
    orders = db_query("SELECT id, info FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 5", (c.from_user.id,), fetchall=True)
    if not orders: 
        return await c.answer("У вас нет покупок", show_alert=True)
    
    b = InlineKeyboardBuilder()
    for o in orders:
        b.row(types.InlineKeyboardButton(text=f"📦 {o[1]}", callback_data=f"show_acc_{o[0]}"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="profile"))
    await c.message.edit_text("🛍 **Ваши последние покупки:**", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("show_acc_"))
async def show_account_info(c: types.CallbackQuery):
    order_id = c.data.split("_")[2]
    file_id = db_query("SELECT file_id FROM purchases WHERE id = ?", (order_id,), fetchone=True)[0]
    
    wait = await c.message.answer("⏳ Подключаюсь к аккаунту...")
    path = f"info_{order_id}.session"
    f = await bot.get_file(file_id)
    await bot.download_file(f.file_path, path)
    
    phone = await get_acc_info(path)
    if os.path.exists(path): 
        os.remove(path)
    
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="📩 Посмотреть коды", callback_data=f"view_codes_{order_id}"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="my_orders"))
    
    await wait.edit_text(f"📱 **Аккаунт:**\n\n**Номер:** `{phone}`\n\nВводите номер в Telegram, затем жмите 'Посмотреть коды'.", 
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
    if os.path.exists(path): 
        os.remove(path)
    
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="🔄 Обновить", callback_data=f"view_codes_{order_id}"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"show_acc_{order_id}"))
    
    await wait.edit_text(f"📜 **История кодов:**\n\n{codes_history}", reply_markup=b.as_markup(), parse_mode="Markdown")

# --- АДМИНКА ---
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
    await m.answer("Цена TON:")
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
    await m.answer("✅ Добавлено!")
    await state.clear()

@dp.callback_query(F.data == "admin_refill", F.from_user.id == ADMIN_ID)
async def ad_ref(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("ID юзера:")
    await state.set_state(ManualDeposit.user_id)

@dp.message(ManualDeposit.user_id)
async def ad_ref_id(m, state):
    await state.update_data(uid=m.text)
    await m.answer("Сумма:")
    await state.set_state(ManualDeposit.amount)

@dp.message(ManualDeposit.amount)
async def ad_ref_fin(m: types.Message, state: FSMContext):
    d = await state.get_data()
    amt = float(m.text)
    db_query("UPDATE users SET balance = balance + ? WHERE id = ?", (amt, d['uid']), commit=True)
    await m.answer(f"✅ Начислено {amt} TON")
    try: 
        await bot.send_message(d['uid'], f"💰 **Баланс пополнен!**\nАдмин начислил вам `{amt} TON`.", parse_mode="Markdown")
    except: 
        pass
    await state.clear()

# --- АДМИНКА: РАССЫЛКА ---
@dp.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def ad_broadcast_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("📣 Отправьте сообщение для рассылки (текст, фото или видео):")
    await state.set_state(Broadcast.msg)

@dp.message(Broadcast.msg, F.from_user.id == ADMIN_ID)
async def ad_broadcast_send(m: types.Message, state: FSMContext):
    users = db_query("SELECT id FROM users", fetchall=True)
    count = 0
    await m.answer(f"⏳ Рассылка началась для {len(users)} пользователей...")
    
    for user in users:
        try:
            await m.copy_to(user[0])
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass
            
    await m.answer(f"✅ Рассылка завершена!\nУспешно доставлено: {count} чел.")
    await state.clear()

# --- ЗАПУСК ---
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
