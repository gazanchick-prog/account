import os
import asyncio
import aiosqlite
import aiohttp
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
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

SEND_API_URL = "https://pay.crypt.bot/api"
SEND_HEADERS = {"Crypto-Pay-API-Token": SEND_TOKEN}
DB_NAME = "sifon_ultimate.db"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Данные для красивого вывода стран
GEO_DATA = {
    "RU": "🇷🇺 Россия (+7)",
    "KZ": "🇰🇿 Казахстан (+7)",
    "UA": "🇺🇦 Украина (+380)",
    "US": "🇺🇸 США (+1)",
    "DE": "🇩🇪 Германия (+49)",
    "UK": "🇬🇧 Англия (+44)"
}

class ShopStates(StatesGroup):
    wait_topup_amt = State()
    wait_session_for_code = State()
    # Админка
    wait_acc_file = State()
    wait_acc_price = State()
    wait_acc_geo = State()
    wait_acc_stay = State()
    wait_acc_type = State()
    wait_bal_id = State()
    wait_bal_amount = State()
    wait_broadcast = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, 
            referred_by INTEGER, ref_count INTEGER DEFAULT 0, 
            ref_earned REAL DEFAULT 0, accepted_rules INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, price REAL, 
            file_id TEXT, geo TEXT, stay INTEGER, type TEXT, is_sold INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
            phone TEXT, price REAL, date TEXT)""")
        await db.commit()

# --- КЛАВИАТУРЫ ---
def main_kb(uid):
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="🛒 Купить аккаунты"), types.KeyboardButton(text="👤 Профиль"))
    kb.row(types.KeyboardButton(text="💰 Пополнить"), types.KeyboardButton(text="🔐 Получить код"))
    kb.row(types.KeyboardButton(text="📜 Мои покупки"), types.KeyboardButton(text="🏆 Топ покупателей"))
    kb.row(types.KeyboardButton(text="ℹ️ Информация"), types.KeyboardButton(text="🆘 Поддержка"))
    if uid == ADMIN_ID:
        kb.row(types.KeyboardButton(text="➕ Добавить"), types.KeyboardButton(text="📢 Рассылка"), types.KeyboardButton(text="💎 Выдать баланс"))
    return kb.as_markup(resize_keyboard=True)

# --- ПРОВЕРКА СЕССИИ ---
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

# --- ОБРАБОТЧИКИ ---

@dp.message(F.text == "/start")
@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    uid = message.from_user.id
    ref_id = None
    if command and command.args and command.args.isdigit():
        ref_id = int(command.args) if int(command.args) != uid else None

    async with aiosqlite.connect(DB_NAME) as db:
        user = await (await db.execute("SELECT accepted_rules FROM users WHERE user_id = ?", (uid,))).fetchone()
        if not user:
            await db.execute("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (uid, ref_id))
            if ref_id:
                await db.execute("UPDATE users SET ref_count = ref_count + 1 WHERE user_id = ?", (ref_id,))
            await db.commit()
            
    if not user or user[0] == 0:
        rules_text = (
            "**Правила SifonMarket**\n\n"
            "1. Администрация вправе изменять правила без предварительного уведомления.\n"
            "2. Гарантия на валидность фиш аккаунтов – 5 минут после покупки.\n"
            "3. Мы делаем всё легально, на наши сим-карты.\n"
            "4. Пополнение баланса не подлежит возврату."
        )
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="✅ Принимаю правила", callback_data="accept_rules"))
        await message.answer(rules_text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    else:
        await message.answer("👋 Добро пожаловать в SifonMarket!", reply_markup=main_kb(uid))

@dp.callback_query(F.data == "accept_rules")
async def rules_accepted(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET accepted_rules = 1 WHERE user_id = ?", (callback.from_user.id,))
        await db.commit()
    await callback.message.delete()
    await callback.message.answer("✅ Регистрация завершена! Приятных покупок.", reply_markup=main_kb(callback.from_user.id))

# --- ИНФОРМАЦИЯ И ПОДДЕРЖКА ---
@dp.message(F.text == "ℹ️ Информация")
async def info_cmd(message: types.Message):
    text = (
        "🛒 **SifonMarket** — это автоматизированный магазин по продаже Telegram аккаунтов.\n\n"
        "Мы обеспечиваем быструю выдачу товара и автоматическую проверку каждой позиции перед покупкой. "
        "Все средства за невалидный товар остаются на вашем балансе.\n\n"
        "📍 Актуальные новости: @sifon_news"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def support_cmd(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="👨‍💻 Связаться с владельцем", url="https://t.me/zyozp"))
    await message.answer("Если у вас возникли вопросы по товару или пополнению, нажмите кнопку ниже:", reply_markup=kb.as_markup())

# --- ПРОФИЛЬ И РЕФЕРАЛЫ ---
@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        u = await (await db.execute("SELECT balance, ref_count, ref_earned FROM users WHERE user_id = ?", (message.from_user.id,))).fetchone()
    
    text = (
        f"👤 **Мой профиль**\n\n"
        f"🆔 Ваш ID: `{message.from_user.id}`\n"
        f"💰 Баланс: **{round(u[0], 2)} TON**\n\n"
        f"🤝 **Реферальная программа:**\n"
        f"— Приглашено: {u[1]} чел.\n"
        f"— Заработано: {round(u[2], 2)} TON"
    )
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="get_ref_link"))
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "get_ref_link")
async def ref_link_callback(callback: types.CallbackQuery):
    link = f"https://t.me/{(await bot.get_me()).username}?start={callback.from_user.id}"
    await callback.message.answer(f"Приглашайте друзей и получайте **10%** от суммы их покупок на свой баланс!\n\nВаша ссылка:\n{link}")
    await callback.answer()

# --- ПОПОЛНЕНИЕ ---
@dp.message(F.text == "💰 Пополнить")
async def topup_start(message: types.Message, state: FSMContext):
    await state.set_state(ShopStates.wait_topup_amt)
    await message.answer("Введите сумму пополнения в **TON**:")

@dp.message(ShopStates.wait_topup_amt)
async def topup_create(message: types.Message, state: FSMContext):
    # Выход из цикла по нажатию кнопок меню
    if message.text in ["🛒 Купить аккаунты", "👤 Профиль", "💰 Пополнить", "🔐 Получить код", "📜 Мои покупки", "🏆 Топ покупателей", "ℹ️ Информация", "🆘 Поддержка"]:
        await state.clear()
        return await message.answer("Пополнение отменено.", reply_markup=main_kb(message.from_user.id))

    if not message.text.replace('.','',1).isdigit():
        return await message.answer("Пожалуйста, введите число (например: 0.5)")
    
    amt = float(message.text)
    payload = {"asset": "TON", "amount": str(amt), "description": f"Top-up SifonMarket ID {message.from_user.id}"}
    
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{SEND_API_URL}/createInvoice", json=payload, headers=SEND_HEADERS) as r:
            res = await r.json()
            
    if res.get('ok'):
        inv = res['result']
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💳 Оплатить", url=inv['pay_url']))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить", callback_data=f"chk_{inv['invoice_id']}_{amt}"))
        
        await message.answer(
            f"Для пополнения баланса на **{amt} TON** перейдите по ссылке ниже.\n\n"
            f"После оплаты обязательно нажмите кнопку проверки.\n\n"
            f"https://t.me/CryptoBot?start={inv['hash']}",
            reply_markup=kb.as_markup()
        )
        await state.clear()
    else:
        await message.answer("Ошибка создания счета. Попробуйте позже.")

@dp.callback_query(F.data.startswith("chk_"))
async def check_payment(callback: types.CallbackQuery):
    _, inv_id, amt = callback.data.split("_")
    params = {"invoice_ids": inv_id}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{SEND_API_URL}/getInvoices", params=params, headers=SEND_HEADERS) as r:
            res = await r.json()
            
    if res.get('ok') and res['result']['items']:
        inv = res['result']['items'][0]
        if inv['status'] == 'paid':
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amt), callback.from_user.id))
                await db.commit()
            
            await callback.message.edit_text(f"✅ Баланс успешно пополнен на **{amt} TON**!")
            # Уведомление админу
            await bot.send_message(ADMIN_ID, f"💰 **Новое пополнение!**\nID: `{callback.from_user.id}`\nСумма: `{amt} TON`", parse_mode="Markdown")
        else:
            await callback.answer(f"⏳ Оплата не найдена. Статус: {inv['status']}", show_alert=True)

# --- МАГАЗИН ---
@dp.message(F.text == "🛒 Купить аккаунты")
async def shop_main(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        rows = await (await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")).fetchall()
    if not rows: return await message.answer("📦 К сожалению, на данный момент товаров нет в наличии.")
    
    kb = InlineKeyboardBuilder()
    for geo, count in rows:
        label = GEO_DATA.get(geo, f"📍 {geo}")
        kb.row(types.InlineKeyboardButton(text=f"{label} ({count} шт.)", callback_data=f"cat_{geo}"))
    await message.answer("🌍 **Выберите страну:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def shop_geo_select(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_NAME) as db:
        items = await (await db.execute("SELECT id, type, stay, price FROM products WHERE geo = ? AND is_sold = 0", (geo,))).fetchall()
    kb = InlineKeyboardBuilder()
    for i in items:
        kb.row(types.InlineKeyboardButton(text=f"{i[1]} | {i[2]}дн | {i[3]} TON", callback_data=f"buy_{i[0]}"))
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_shop"))
    await callback.message.edit_text(f"📍 Список товаров: {GEO_DATA.get(geo, geo)}", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "back_to_shop")
async def back_to_shop(callback: types.CallbackQuery):
    await callback.message.delete()
    await shop_main(callback.message)

@dp.callback_query(F.data.startswith("buy_"))
async def buy_process(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    uid = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        p = await (await db.execute("SELECT price, file_id, phone FROM products WHERE id = ?", (pid,))).fetchone()
        u = await (await db.execute("SELECT balance, referred_by FROM users WHERE user_id = ?", (uid,))).fetchone()
        
        if u[0] < p[0]: return await callback.answer("❌ На вашем балансе недостаточно средств!", show_alert=True)
        
        await callback.answer("⏳ Проверяем аккаунт на валидность...", show_alert=False)
        if not await check_valid(p[1]):
            await db.execute("UPDATE products SET is_sold = 2 WHERE id = ?", (pid,))
            await db.commit()
            return await callback.message.answer("❌ Аккаунт не прошел проверку и был снят с продажи. Ваши средства не списаны. Пожалуйста, выберите другой аккаунт.")

        # Успешная покупка
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (p[0], uid))
        if u[1]:
            bonus = p[0] * 0.1
            await db.execute("UPDATE users SET balance = balance + ?, ref_earned = ref_earned + ? WHERE user_id = ?", (bonus, bonus, u[1]))
            try: await bot.send_message(u[1], f"💰 **Реферальное начисление!**\nВаш друг совершил покупку, вам начислено +{round(bonus, 2)} TON!")
            except: pass
            
        await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (pid,))
        await db.execute("INSERT INTO purchases (user_id, phone, price, date) VALUES (?, ?, ?, ?)",
                        (uid, p[2], p[0], datetime.now().strftime("%d.%m.%Y %H:%M")))
        await db.commit()
        
        await callback.message.answer(f"✅ **Покупка завершена!**\n\nНомер: `+{p[2]}`\nЦена: {p[0]} TON\n\nФайл сессии отправлен ниже.")
        await callback.message.answer_document(p[1], caption="🔐 Ваша покупка. Не передавайте файл третьим лицам!")

# --- СТАТИСТИКА (РЕАЛЬНАЯ) ---
@dp.message(F.text == "📜 Мои покупки")
async def my_purchases(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        res = await (await db.execute("SELECT phone, price, date FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 10", (message.from_user.id,))).fetchall()
    if not res: return await message.answer("📦 У вас пока нет совершенных покупок.")
    
    text = "📂 **История ваших покупок:**\n\n"
    for r in res:
        text += f"📱 `+{r[0]}` | {r[1]} TON | {r[2]}\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🏆 Топ покупателей")
async def top_buyers(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        res = await (await db.execute("SELECT user_id, SUM(price) as total FROM purchases GROUP BY user_id ORDER BY total DESC LIMIT 5")).fetchall()
    if not res:
        return await message.answer("🏆 **Топ пока пуст!**\n\nСтаньте первым покупателем, чтобы попасть в список лидеров.")
    
    text = "🏆 **Лидеры SifonMarket:**\n\n"
    for i, r in enumerate(res, 1):
        text += f"{i}. ID `{r[0]}` — потрачено **{round(r[1], 2)} TON**\n"
    await message.answer(text, parse_mode="Markdown")

# --- ПОЛУЧИТЬ КОД ---
@dp.message(F.text == "🔐 Получить код")
async def code_start(message: types.Message, state: FSMContext):
    await state.set_state(ShopStates.wait_session_for_code)
    await message.answer("Отправьте файл **.session**, чтобы получить код из аккаунта:")

@dp.message(ShopStates.wait_session_for_code, F.document)
async def code_process(message: types.Message, state: FSMContext):
    path = f"u_{message.from_user.id}.session"
    f = await bot.get_file(message.document.file_id)
    await bot.download_file(f.file_path, path)
    client = TelegramClient(path, API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return await message.answer("❌ **Сессия невалидна!**\n\nЭто означает, что аккаунт был деавторизован или заблокирован Telegram. Использовать этот файл больше нельзя.")
        
        me = await client.get_me()
        async for m in client.iter_messages(777000, limit=1):
            await message.answer(f"📱 Аккаунт: `+{me.phone}`\n\n💬 **Последнее сообщение:**\n`{m.text}`", parse_mode="Markdown")
            break
    except Exception as e:
        await message.answer(f"Ошибка доступа: `{e}`")
    finally:
        await client.disconnect()
        if os.path.exists(path): os.remove(path)
        await state.clear()

# --- АДМИНКА ---
@dp.message(F.text == "➕ Добавить", F.from_user.id == ADMIN_ID)
async def adm_add_st(message: types.Message, state: FSMContext):
    await state.set_state(ShopStates.wait_acc_file)
    await message.answer("Пришлите .session файл:")

@dp.message(ShopStates.wait_acc_file, F.document)
async def adm_file(message: types.Message, state: FSMContext):
    phone = message.document.file_name.split('.')[0].replace("+", "")
    await state.update_data(fid=message.document.file_id, phone=phone)
    await state.set_state(ShopStates.wait_acc_price)
    await message.answer(f"Номер: {phone}\nВведите цену (TON):")

@dp.message(ShopStates.wait_acc_price)
async def adm_price(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await state.set_state(ShopStates.wait_acc_geo)
    await message.answer("Введите ГЕО (RU, KZ, UA, US, DE):")

@dp.message(ShopStates.wait_acc_geo)
async def adm_geo(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text.upper())
    await state.set_state(ShopStates.wait_acc_stay)
    await message.answer("Введите отлегу (дней):")

@dp.message(ShopStates.wait_acc_stay)
async def adm_stay(message: types.Message, state: FSMContext):
    await state.update_data(stay=int(message.text))
    await state.set_state(ShopStates.wait_acc_type)
    await message.answer("Введите тип (например, Авторег):")

@dp.message(ShopStates.wait_acc_type)
async def adm_final(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, file_id, geo, stay, type) VALUES (?,?,?,?,?,?)",
                        (d['phone'], d['price'], d['fid'], d['geo'], d['stay'], message.text))
        await db.commit()
    await message.answer("✅ Аккаунт добавлен в магазин!")
    await state.clear()

@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
async def give_bal_st(message: types.Message, state: FSMContext):
    await state.set_state(ShopStates.wait_bal_id)
    await message.answer("Введите ID пользователя:")

@dp.message(ShopStates.wait_bal_id)
async def give_bal_id(message: types.Message, state: FSMContext):
    await state.update_data(tid=message.text)
    await state.set_state(ShopStates.wait_bal_amount)
    await message.answer("Сколько начислить TON?")

@dp.message(ShopStates.wait_bal_amount)
async def give_bal_fn(message: types.Message, state: FSMContext):
    d = await state.get_data()
    amt = float(message.text)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, d['tid']))
        await db.commit()
    await message.answer(f"✅ Выдано {amt} TON пользователю `{d['tid']}`")
    try:
        await bot.send_message(d['tid'], f"💎 **Баланс пополнен!**\nАдминистратор начислил вам **{amt} TON**.")
    except: pass
    await state.clear()

@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def broad_st(message: types.Message, state: FSMContext):
    await state.set_state(ShopStates.wait_broadcast)
    await message.answer("Введите текст рассылки:")

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
    await message.answer(f"📢 Рассылка завершена!\nДоставлено: {ok}\nОшибок: {err}")
    await state.clear()

# --- ЗАПУСК ---
async def main():
    await init_db()
    print("SifonMarket Online!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
