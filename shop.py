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
# Исправленный URL и заголовок для Crypto Pay
SEND_API_URL = "https://pay.crypt.bot/api"
SEND_HEADERS = {"Crypto-Pay-API-Token": SEND_TOKEN}

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

# --- ПРОВЕРКА ВАЛИДНОСТИ (БЕЗОПАСНАЯ) ---
async def check_valid(file_id):
    path = f"check_{time.time()}.session"
    try:
        f = await bot.get_file(file_id)
        await bot.download_file(f.file_path, path)
        # Использование Telethon для быстрой проверки без лишних входов
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
            "1. Администрация не несёт ответственности за действия третьих лиц, включая утерю доступа к аккаунту по вине покупателя.\n"
            "2. Гарантия на валидность фиш-аккаунтов составляет 5 минут с момента покупки. После этого времени претензии не принимаются.\n"
            "3. Запрещено создавать множественные аккаунты для получения бонусов или накрутки реферальной системы. Все дубликаты будут заблокированы.\n"
            "4. "Пополнение внутреннего баланса сервиса не подлежит возврату и обмену на денежные средства."
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
    await message.answer(f"👤 **Профиль SifonMarket**\n\n🆔 ID: `{message.from_user.id}`\n💰 Баланс: **{round(bal, 2)} TON**", parse_mode="Markdown")

# --- ПОПОЛНЕНИЕ (CRYPTO BOT / @SEND) ---
@dp.message(F.text == "💰 Пополнить")
async def topup_start(message: types.Message, state: FSMContext):
    await message.answer("Введите сумму пополнения в TON (например: 0.5):")
    await state.set_state(ShopStates.wait_topup_amt)

@dp.message(ShopStates.wait_topup_amt)
async def topup_create(message: types.Message, state: FSMContext):
    if not message.text.replace('.','',1).isdigit():
        return await message.answer("Пожалуйста, введите корректное число.")
    
    amt = float(message.text)
    payload = {"asset": "TON", "amount": str(amt), "description": f"SifonMarket User {message.from_user.id}"}
    
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{SEND_API_URL}/createInvoice", json=payload, headers=SEND_HEADERS) as r:
            res = await r.json()
            
    if res.get('ok'):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💳 Оплатить в Crypto Bot", url=res['result']['pay_url']))
        kb.row(types.InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"chk_{res['result']['invoice_id']}_{amt}"))
        await message.answer(f"Счет на {amt} TON сформирован. Оплатите его в боте и нажмите кнопку проверки:", reply_markup=kb.as_markup())
        await state.clear()
    else:
        await message.answer("Ошибка связи с Crypto Bot. Проверьте SEND_TOKEN в .env")

@dp.callback_query(F.data.startswith("chk_"))
async def check_payment(callback: types.CallbackQuery):
    _, inv_id, amt = callback.data.split("_")
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{SEND_API_URL}/getInvoices?invoice_ids={inv_id}", headers=SEND_HEADERS) as r:
            res = await r.json()
            
    if res.get('ok') and any(i['invoice_id'] == int(inv_id) and i['status'] == 'paid' for i in res['result']):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(amt), callback.from_user.id))
            await db.commit()
        await callback.message.edit_text(f"✅ Оплата подтверждена! На ваш баланс зачислено {amt} TON.")
    else:
        await callback.answer("⏳ Оплата еще не поступила", show_alert=True)

# --- МАГАЗИН ---
@dp.message(F.text == "🛒 Купить аккаунты")
async def shop_main(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        c = await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")
        rows = await c.fetchall()
    if not rows: return await message.answer("В данный момент товаров нет в наличии.")
    kb = InlineKeyboardBuilder()
    for geo, count in rows:
        kb.row(types.InlineKeyboardButton(text=f"📍 {geo} ({count} шт.)", callback_data=f"cat_{geo}"))
    await message.answer("Выберите интересующее ГЕО:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def shop_geo_select(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    async with aiosqlite.connect(DB_NAME) as db:
        c = await db.execute("SELECT id, type, stay, price FROM products WHERE geo = ? AND is_sold = 0", (geo,))
        items = await c.fetchall()
    kb = InlineKeyboardBuilder()
    for i in items:
        kb.row(types.InlineKeyboardButton(text=f"{i[1]} | {i[2]}дн. | {i[3]} TON", callback_data=f"buy_{i[0]}"))
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_cats"))
    await callback.message.edit_text(f"Доступные аккаунты ({geo}):", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "back_to_cats")
async def back_cats(callback: types.CallbackQuery):
    await callback.message.delete()
    await shop_main(callback.message)

@dp.callback_query(F.data.startswith("buy_"))
async def buy_process(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    uid = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        p = await (await db.execute("SELECT price, file_id, phone FROM products WHERE id = ?", (pid,))).fetchone()
        u = await (await db.execute("SELECT balance, referred_by FROM users WHERE user_id = ?", (uid,))).fetchone()
        
        if u[0] < p[0]: return await callback.answer("❌ На балансе недостаточно средств", show_alert=True)
        
        await callback.answer("⏳ Проверяем аккаунт на валидность...", show_alert=False)
        if not await check_valid(p[1]):
            await db.execute("UPDATE products SET is_sold = 2 WHERE id = ?", (pid,))
            await db.commit()
            return await callback.message.answer("❌ К сожалению, аккаунт оказался невалидным. Деньги не списаны. Попробуйте другой.")

        # Списание и реферальные 10%
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (p[0], uid))
        if u[1]:
            bonus = p[0] * 0.1
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus, u[1]))
            try: await bot.send_message(u[1], f"💰 Вам начислен реферальный бонус +{round(bonus, 2)} TON!")
            except: pass
            
        await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (pid,))
        await db.execute("INSERT INTO purchases (user_id, phone, price, date) VALUES (?, ?, ?, ?)",
                        (uid, p[2], p[0], datetime.now().strftime("%H:%M %d.%m.%Y")))
        await db.commit()
        
        await callback.message.answer(f"✅ Успешная покупка!\n\nНомер: `{p[2]}`\nДля получения кода используйте кнопку в меню.")
        await callback.message.answer_document(p[1], caption="Ваш файл .session. Не передавайте его третьим лицам.")

# --- ПОЛУЧИТЬ КОД ---
@dp.message(F.text == "🔐 Получить код")
async def code_start(message: types.Message, state: FSMContext):
    await message.answer("Пришлите ваш файл .session для получения кода авторизации:")
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
            return await message.answer("❌ Сессия недействительна или слетела.")
        
        me = await client.get_me()
        async for msg in client.iter_messages(777000, limit=1):
            await message.answer(f"📱 Номер: `+{me.phone}`\n\n💬 Текст последнего сообщения от Telegram:\n`{msg.text}`", parse_mode="Markdown")
            break
        else:
            await message.answer(f"📱 Номер: `+{me.phone}`\nСообщений от сервиса не найдено.")
    except Exception as e:
        await message.answer(f"Ошибка при получении кода: {e}")
    finally:
        await client.disconnect()
        if os.path.exists(path): os.remove(path)
        await state.clear()

# --- ДОПОЛНИТЕЛЬНОЕ ---
@dp.message(F.text == "📜 Мои покупки")
async def my_purchases(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        res = await (await db.execute("SELECT phone, price, date FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 10", (message.from_user.id,))).fetchall()
    if not res: return await message.answer("История покупок пуста.")
    text = "📂 **Ваши последние покупки:**\n\n"
    for r in res:
        text += f"📱 `{r[0]}` | {r[1]} TON | {r[2]}\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🤝 Рефералы")
async def ref_info(message: types.Message):
    link = f"https://t.me/{(await bot.get_me()).username}?start={message.from_user.id}"
    async with aiosqlite.connect(DB_NAME) as db:
        cnt = (await (await db.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (message.from_user.id,))).fetchone())[0]
    await message.answer(f"🤝 **Реферальная система**\n\nПолучайте **10%** с каждой покупки вашего друга!\n\n👥 Приглашено: {cnt}\n🔗 Ссылка: `{link}`", parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def support(message: types.Message):
    await message.answer("🆘 По всем техническим вопросам и гарантии:\nОбращайтесь к @zyozp")

@dp.message(F.text == "🏆 Топ покупателей")
async def top_buyers(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as db:
        res = await (await db.execute("SELECT user_id, SUM(price) as total FROM purchases GROUP BY user_id ORDER BY total DESC LIMIT 5")).fetchall()
    text = "🏆 **Лидеры покупок SifonMarket:**\n\n"
    for i, r in enumerate(res, 1):
        text += f"{i}. ID `{r[0]}` — {round(r[1], 2)} TON\n"
    await message.answer(text, parse_mode="Markdown")

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(F.text == "➕ Добавить", F.from_user.id == ADMIN_ID)
async def adm_add_1(message: types.Message, state: FSMContext):
    await message.answer("Пришлите файл .session для продажи:")
    await state.set_state(ShopStates.wait_acc_file)

@dp.message(ShopStates.wait_acc_file, F.document)
async def adm_add_2(message: types.Message, state: FSMContext):
    await state.update_data(fid=message.document.file_id, phone=message.document.file_name.split('.')[0])
    await message.answer("Укажите стоимость в TON (число):")
    await state.set_state(ShopStates.wait_acc_price)

@dp.message(ShopStates.wait_acc_price)
async def adm_add_3(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await message.answer("Укажите ГЕО (например, RU):")
    await state.set_state(ShopStates.wait_acc_geo)

@dp.message(ShopStates.wait_acc_geo)
async def adm_add_4(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text)
    await message.answer("Укажите отлегу (количество дней):")
    await state.set_state(ShopStates.wait_acc_stay)

@dp.message(ShopStates.wait_acc_stay)
async def adm_add_5(message: types.Message, state: FSMContext):
    await state.update_data(stay=int(message.text))
    await message.answer("Укажите вид (например, Авторег):")
    await state.set_state(ShopStates.wait_acc_type)

@dp.message(ShopStates.wait_acc_type)
async def adm_add_final(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO products (phone, price, file_id, geo, stay, type) VALUES (?,?,?,?,?,?)",
                        (d['phone'], d['price'], d['fid'], d['geo'], d['stay'], message.text))
        await db.commit()
    await message.answer("✅ Товар успешно добавлен в магазин.")
    await state.clear()

@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
async def adm_give_1(message: types.Message, state: FSMContext):
    await message.answer("Введите ID пользователя:")
    await state.set_state(ShopStates.wait_bal_id)

@dp.message(ShopStates.wait_bal_id)
async def adm_give_2(message: types.Message, state: FSMContext):
    await state.update_data(tid=message.text)
    await message.answer("Сумма начисления (TON):")
    await state.set_state(ShopStates.wait_bal_amount)

@dp.message(ShopStates.wait_bal_amount)
async def adm_give_3(message: types.Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(message.text), d['tid']))
        await db.commit()
    await message.answer(f"✅ Баланс пользователя {d['tid']} пополнен!")
    try: await bot.send_message(d['tid'], f"💎 Администратор начислил вам {message.text} TON!")
    except: pass
    await state.clear()

@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def adm_broad_1(message: types.Message, state: FSMContext):
    await message.answer("Введите текст сообщения для всех пользователей:")
    await state.set_state(ShopStates.wait_broadcast)

@dp.message(ShopStates.wait_broadcast)
async def adm_broad_2(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        users = await (await db.execute("SELECT user_id FROM users")).fetchall()
    ok, err = 0, 0
    for u in users:
        try:
            await bot.send_message(u[0], message.text)
            ok += 1
        except: err += 1
    await message.answer(f"📢 Рассылка завершена!\nДоставлено: {ok}\nНе удалось: {err}")
    await state.clear()

async def main():
    await init_db()
    print("Бот SifonMarket запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
