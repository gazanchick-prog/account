import os
import asyncio
import aiosqlite
import aiohttp
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from telethon import TelegramClient
from dotenv import load_dotenv

# --- НАСТРОЙКИ ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SEND_TOKEN = os.getenv("SEND_TOKEN")
SEND_API_URL = "https://pay.send.tg/api/v1"

DB_NAME = "sifon_market.db"
bot = Bot(token=TOKEN)
dp = Dispatcher()

class ShopStates(StatesGroup):
    wait_rules = State()
    wait_topup_amt = State()
    # Админка
    wait_acc_file = State()
    wait_acc_price = State()
    wait_acc_geo = State()
    wait_acc_stay = State()
    wait_acc_type = State()
    wait_bal_id = State()
    wait_bal_amount = State()
    wait_broadcast = State()
    wait_session_for_code = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, 
            referred_by INTEGER, accepted_rules INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, price REAL, 
            file_id TEXT, geo TEXT, stay INTEGER, type TEXT, is_sold INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
            phone TEXT, price REAL, date TEXT)""")
        await db.commit()

# --- ВСПОМОГАТЕЛЬНОЕ ---
async def check_valid(file_id):
    path = f"check_{time.time()}.session"
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
    kb.row(types.KeyboardButton(text="📜 Мои покупки"), types.KeyboardButton(text="🏆 Топ покупателей"))
    kb.row(types.KeyboardButton(text="🤝 Рефералы"), types.KeyboardButton(text="ℹ️ Информация"))
    kb.row(types.KeyboardButton(text="🆘 Поддержка"))
    if uid == ADMIN_ID:
        kb.row(types.KeyboardButton(text="➕ Добавить"), types.KeyboardButton(text="📢 Рассылка"), types.KeyboardButton(text="💎 Выдать баланс"))
    return kb.as_markup(resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def start(message: types.Message, command: CommandObject, state: FSMContext):
    uid = message.from_user.id
    ref_id = None
    if command.args and command.args.isdigit():
        ref_id = int(command.args) if int(command.args) != uid else None

    async with aiosqlite.connect(DB_NAME) as db:
        res = await db.execute("SELECT accepted_rules FROM users WHERE user_id = ?", (uid,))
        user = await res.fetchone()
        if not user:
            await db.execute("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (uid, ref_id))
            await db.commit()
            
    if not user or user[0] == 0:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="✅ Принимаю правила", callback_data="accept_rules"))
        rules_text = (
            "📜 **Правила SifonMarket**\n\n"
            "1. На Fish-аккаунты гарантия только на момент входа.\n"
            "2. Гарантия на валидность — 5 минут после покупки.\n"
            "3. Мы не несем ответственности за блокировки после использования.\n"
            "4. Пополнение баланса невозвратно."
        )
        await message.answer(rules_text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    else:
        await message.answer(f"👋 Добро пожаловать в SifonMarket!", reply_markup=main_kb(uid))

@dp.callback_query(F.data == "accept_rules")
async def rules_accepted(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET accepted_rules = 1 WHERE user_id = ?", (callback.from_user.id,))
        await db.commit()
    await callback.message.delete()
    await callback.message.answer("✅ Правила приняты! Приятных покупок.", reply_markup=main_kb(callback.from_user.id))

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        res = await db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
        bal = (await res.fetchone())[0]
    await message.answer(f"👤 **Профиль SifonMarket**\n\n🆔 ID: `{message.from_user.id}`\n💰 Баланс: **{bal} TON**", parse_mode="Markdown")

@dp.message(F.text == "🤝 Рефералы")
async def referral_sys(message: types.Message):
    link = f"https://t.me/{(await bot.get_me()).username}?start={message.from_user.id}"
    async with aiosqlite.connect(DB_NAME) as db:
        res = await db.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (message.from_user.id,))
        count = (await res.fetchone())[0]
    await message.answer(f"🤝 **Реферальная система**\n\nПриглашайте друзей и получайте **10%** от их покупок на ваш баланс!\n\n👥 Приглашено: {count}\n🔗 Ваша ссылка: `{link}`", parse_mode="Markdown")

@dp.message(F.text == "ℹ️ Информация")
async def info_cmd(message: types.Message):
    await message.answer("🛒 **SifonMarket** — лучший магазин аккаунтов.\n\nГлавный: @zyozp\nЗдесь только качественные автореги и отлежанные аккаунты.")

@dp.message(F.text == "🆘 Поддержка")
async def support(message: types.Message):
    await message.answer("По всем вопросам: @zyozp")

# --- ПОПОЛНЕНИЕ (CRYPTO BOT / @SEND) ---
@dp.message(F.text == "💰 Пополнить")
async def topup_start(message: types.Message, state: FSMContext):
    await message.answer("Введите сумму пополнения в TON:")
    await state.set_state(ShopStates.wait_topup_amt)

@dp.message(ShopStates.wait_topup_amt)
async def topup_create(message: types.Message, state: FSMContext):
    if not message.text.replace('.','',1).isdigit():
        return await message.answer("Введите число.")
    
    amt = float(message.text)
    headers = {"X-Token": SEND_TOKEN}
    payload = {"asset": "TON", "amount": str(amt), "description": f"SifonMarket ID {message.from_user.id}"}
    
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{SEND_API_URL}/createInvoice", json=payload, headers=headers) as r:
            res = await r.json()
            
    if res.get('ok'):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💳 Оплатить", url=res['result']['pay_url']))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить", callback_data=f"chk_{res['result']['invoice_id']}_{amt}"))
        await message.answer(f"Счет на {amt} TON создан:", reply_markup=kb.as_markup())
        await state.clear()
    else:
        await message.answer("Ошибка создания счета. Попробуйте позже.")

@dp.callback_query(F.data.startswith("chk_"))
async def check_payment(callback: types.CallbackQuery):
    _, inv_id, amt = callback.data.split("_")
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{SEND_API_URL}/getInvoices?invoice_ids={inv_id}", headers={"X-Token": SEND_TOKEN}) as r:
            res = await r.json()
            
    if res.get('ok') and res['result'][0]['status'] == 'paid':
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amt), callback.from_user.id))
            await db.commit()
        await callback.message.edit_text(f"✅ Баланс пополнен на {amt} TON!")
    else:
        await callback.answer("⏳ Оплата не найдена", show_alert=True)

# --- МАГАЗИН И ПОКУПКИ ---
@dp.message(F.text == "🛒 Купить аккаунты")
async def shop_main(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        c = await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")
        rows = await c.fetchall()
    if not rows: return await message.answer("Товара временно нет.")
    kb = InlineKeyboardBuilder()
    for geo, count in rows:
        kb.row(types.InlineKeyboardButton(text=f"📍 {geo} ({count} шт.)", callback_data=f"cat_{geo}"))
    await message.answer("Выберите ГЕО:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def shop_geo_select(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_NAME) as db:
        c = await db.execute("SELECT id, type, stay, price FROM products WHERE geo = ? AND is_sold = 0", (geo,))
        items = await c.fetchall()
    kb = InlineKeyboardBuilder()
    for i in items:
        kb.row(types.InlineKeyboardButton(text=f"{i[1]} | {i[2]}дн. | {i[3]} TON", callback_data=f"buy_{i[0]}"))
    await callback.message.edit_text(f"Аккаунты {geo}:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def buy_confirm(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    uid = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        p = await (await db.execute("SELECT price, file_id, phone FROM products WHERE id = ?", (pid,))).fetchone()
        u = await (await db.execute("SELECT balance, referred_by FROM users WHERE user_id = ?", (uid,))).fetchone()
        
        if u[0] < p[0]: return await callback.answer("❌ Недостаточно средств", show_alert=True)
        
        await callback.answer("⏳ Проверка аккаунта юзерботом...", show_alert=False)
        if not await check_valid(p[1]):
            await db.execute("UPDATE products SET is_sold = 2 WHERE id = ?", (pid,))
            await db.commit()
            return await callback.message.answer("❌ Аккаунт невалид. Выберите другой, деньги не списаны.")

        # Списание и начисление рефу
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (p[0], uid))
        if u[1]:
            ref_bonus = p[0] * 0.1
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (ref_bonus, u[1]))
            try: await bot.send_message(u[1], f"💰 Реферальный бонус: +{ref_bonus} TON!")
            except: pass
            
        await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (pid,))
        await db.execute("INSERT INTO purchases (user_id, phone, price, date) VALUES (?, ?, ?, ?)",
                        (uid, p[2], p[0], datetime.now().strftime("%Y-%m-%d %H:%M")))
        await db.commit()
        
        await callback.message.answer(f"✅ Покупка завершена!\nНомер: `{p[2]}`")
        await callback.message.answer_document(p[1], caption="Ваш файл .session")

@dp.message(F.text == "📜 Мои покупки")
async def my_purchases(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        res = await (await db.execute("SELECT phone, price, date FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 10", (message.from_user.id,))).fetchall()
    if not res: return await message.answer("У вас еще нет покупок.")
    text = "📂 **Последние покупки:**\n\n"
    for r in res:
        text += f"📱 `{r[0]}` | 💰 {r[1]} TON | 📅 {r[2]}\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🏆 Топ покупателей")
async def top_buyers(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        res = await (await db.execute("SELECT user_id, SUM(price) as total FROM purchases GROUP BY user_id ORDER BY total DESC LIMIT 5")).fetchall()
    text = "🏆 **Топ покупателей SifonMarket:**\n\n"
    for i, r in enumerate(res, 1):
        text += f"{i}. ID `{r[0]}` — {round(r[1], 2)} TON\n"
    await message.answer(text, parse_mode="Markdown")

# --- ПОЛУЧИТЬ КОД (ЮЗЕРБОТ) ---
@dp.message(F.text == "🔐 Получить код")
async def code_start(message: types.Message, state: FSMContext):
    await message.answer("Отправьте ваш .session файл для получения кода:")
    await state.set_state(ShopStates.wait_session_for_code)

@dp.message(ShopStates.wait_session_for_code, F.document)
async def code_process(message: types.Message, state: FSMContext):
    path = f"user_{message.from_user.id}.session"
    f = await bot.get_file(message.document.file_id)
    await bot.download_file(f.file_path, path)
    
    client = TelegramClient(path, API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await message.answer("❌ Сессия невалидна.")
            return
        
        me = await client.get_me()
        async for msg in client.iter_messages(777000, limit=1):
            await message.answer(f"📱 Номер: `+{me.phone}`\n💬 Код из Telegram:\n\n`{msg.text}`", parse_mode="Markdown")
            break
        else:
            await message.answer(f"📱 Номер: `+{me.phone}`\nКодов от Telegram не найдено.")
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")
    finally:
        await client.disconnect()
        if os.path.exists(path): os.remove(path)
        await state.clear()

# --- АДМИН ПАНЕЛЬ ---
@dp.message(F.text == "➕ Добавить", F.from_user.id == ADMIN_ID)
async def adm_add_st(message: types.Message, state: FSMContext):
    await message.answer("Пришлите файл .session:")
    await state.set_state(ShopStates.wait_acc_file)

@dp.message(ShopStates.wait_acc_file, F.document)
async def adm_file(message: types.Message, state: FSMContext):
    await state.update_data(fid=message.document.file_id, phone=message.document.file_name.replace(".session",""))
    await message.answer("Цена (в TON):")
    await state.set_state(ShopStates.wait_acc_price)

@dp.message(ShopStates.wait_acc_price)
async def adm_price(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await message.answer("ГЕО (например, RU, KZ, US):")
    await state.set_state(ShopStates.wait_acc_geo)

@dp.message(ShopStates.wait_acc_geo)
async def adm_geo(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text)
    await message.answer("Отлега (дней):")
    await state.set_state(ShopStates.wait_acc_stay)

@dp.message(ShopStates.wait_acc_stay)
async def adm_stay(message: types.Message, state: FSMContext):
    await state.update_data(stay=int(message.text))
    await message.answer("Вид (Авторег/Фиш):")
    await state.set_state(ShopStates.wait_acc_type)

@dp.message(ShopStates.wait_acc_type)
async def adm_final(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, file_id, geo, stay, type) VALUES (?,?,?,?,?,?)",
                        (d['phone'], d['price'], d['fid'], d['geo'], d['stay'], message.text))
        await db.commit()
    await message.answer("✅ Аккаунт успешно добавлен в магазин!")
    await state.clear()

@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
async def give_bal_1(message: types.Message, state: FSMContext):
    await message.answer("Введите ID пользователя:")
    await state.set_state(ShopStates.wait_bal_id)

@dp.message(ShopStates.wait_bal_id)
async def give_bal_2(message: types.Message, state: FSMContext):
    await state.update_data(tid=message.text)
    await message.answer("Сумма (TON):")
    await state.set_state(ShopStates.wait_bal_amount)

@dp.message(ShopStates.wait_bal_amount)
async def give_bal_3(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(message.text), d['tid']))
        await db.commit()
    await message.answer("✅ Баланс успешно начислен!")
    try: await bot.send_message(d['tid'], f"💎 Администратор начислил вам {message.text} TON!")
    except: pass
    await state.clear()

@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def broad_1(message: types.Message, state: FSMContext):
    await message.answer("Введите текст рассылки:")
    await state.set_state(ShopStates.wait_broadcast)

@dp.message(ShopStates.wait_broadcast)
async def broad_2(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        users = await (await db.execute("SELECT user_id FROM users")).fetchall()
    ok, bad = 0, 0
    for u in users:
        try:
            await bot.send_message(u[0], message.text)
            ok += 1
        except: bad += 1
    await message.answer(f"📢 Рассылка завершена!\nУспешно: {ok}\nЗаблокировали: {bad}")
    await state.clear()

async def main():
    await init_db()
    print("SifonMarket запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
