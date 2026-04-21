import os
import json
import asyncio
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import FSInputFile
from telethon import TelegramClient
from dotenv import load_dotenv

# --- НАСТРОЙКИ ИЗ .ENV ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
TON_WALLET = os.getenv("TON_WALLET")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DATA_FILE = "data.json"

# Хранилище запущенных клиентов (Session -> Client)
active_sessions = {}

class ShopStates(StatesGroup):
    wait_bal_id = State()
    wait_bal_amount = State()
    wait_acc_file = State()
    wait_acc_price = State()
    wait_acc_geo = State()
    wait_acc_stay = State()
    wait_acc_type = State()
    wait_broadcast_text = State()

# --- СИСТЕМА ХРАНЕНИЯ (JSON) ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "products": [], "purchases": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- КЛАВИАТУРЫ ---
def main_kb(user_id):
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🛒 Купить аккаунты"), types.KeyboardButton(text="👤 Профиль"))
    builder.row(types.KeyboardButton(text="💰 Пополнить баланс"), types.KeyboardButton(text="🛍 Мои покупки"))
    builder.row(types.KeyboardButton(text="👥 Реферальная система"), types.KeyboardButton(text="📜 История операций"))
    builder.row(types.KeyboardButton(text="🏆 Топ покупателей"), types.KeyboardButton(text="📋 Информация"))
    builder.row(types.KeyboardButton(text="🆘 Поддержка"))
    
    if user_id == ADMIN_ID:
        builder.row(types.KeyboardButton(text="➕ Добавить товар"), types.KeyboardButton(text="💎 Выдать баланс"))
        builder.row(types.KeyboardButton(text="📢 Рассылка"))
    return builder.as_markup(resize_keyboard=True)

# --- ЛОГИКА ЮЗЕРБОТА (5 МИНУТ) ---
async def manage_session(session_path):
    if session_path in active_sessions:
        return active_sessions[session_path]
    
    client = TelegramClient(session_path, API_ID, API_HASH)
    await client.connect()
    active_sessions[session_path] = client
    
    # Таймер на 5 минут для экономии памяти хоста
    async def auto_disconnect():
        await asyncio.sleep(300)
        if session_path in active_sessions:
            await active_sessions[session_path].disconnect()
            del active_sessions[session_path]
            
    asyncio.create_task(auto_disconnect())
    return client

# --- ОБРАБОТЧИКИ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    data = load_data()
    uid = str(message.from_user.id)
    
    if uid not in data["users"]:
        ref_id = command.args if (command.args and command.args.isdigit() and command.args != uid) else None
        data["users"][uid] = {"balance": 0, "referrer": ref_id}
        save_data(data)

    text = (
        "👋 **Добро пожаловать в Sifon Market!**\n\n"
        "🛒 Магазин качественных аккаунтов с автоматической выдачей.\n"
        "⚡️ Получение кода прямо в боте.\n"
        "👥 Приглашайте друзей и получайте **10%** с их покупок!"
    )
    await message.answer(text, reply_markup=main_kb(message.from_user.id), parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    data = load_data()
    user = data["users"].get(str(message.from_user.id), {"balance": 0})
    text = (
        f"👤 **Ваш профиль в Sifon Market**\n\n"
        f"🆔 Ваш ID: `{message.from_user.id}`\n"
        f"💰 Баланс: **{user['balance']} TON**\n"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💰 Пополнить баланс")
async def topup(message: types.Message):
    text = (
        "💎 **Пополнение (TON)**\n\n"
        f"📍 Адрес:\n`{TON_WALLET}`\n\n"
        f"💬 Комментарий (ВАЖНО):\n`{message.from_user.id}`\n\n"
        "⚠️ Без комментария средства не зачислятся!"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👥 Реферальная система")
async def referral(message: types.Message):
    bot_user = await bot.get_me()
    link = f"https://t.me/{bot_user.username}?start={message.from_user.id}"
    await message.answer(f"👥 **Ваша ссылка (10% профита):**\n`{link}`", parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def support(message: types.Message):
    await message.answer("🆘 По всем вопросам обращаться: @zyozp")

# --- МАГАЗИН И ПОКУПКИ ---
@dp.message(F.text == "🛒 Купить аккаунты")
async def shop(message: types.Message):
    data = load_data()
    geos = {}
    for p in data["products"]:
        if not p.get("is_sold"):
            geos[p["geo"]] = geos.get(p["geo"], 0) + 1
    
    if not geos: return await message.answer("📦 Товаров нет.")
    
    kb = InlineKeyboardBuilder()
    for geo, count in geos.items():
        kb.row(types.InlineKeyboardButton(text=f"📍 {geo} ({count} шт.)", callback_data=f"cat_{geo}"))
    await message.answer("📁 **Выберите локацию:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def show_geo(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    data = load_data()
    kb = InlineKeyboardBuilder()
    for i, p in enumerate(data["products"]):
        if p["geo"] == geo and not p.get("is_sold"):
            kb.row(types.InlineKeyboardButton(text=f"⚙️ {p['type']} | {p['price']} TON", callback_data=f"buy_{i}"))
    await callback.message.edit_text(f"📱 **Аккаунты {geo}:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    uid = str(callback.from_user.id)
    data = load_data()
    prod = data["products"][idx]
    user = data["users"][uid]

    if user["balance"] >= prod["price"]:
        user["balance"] -= prod["price"]
        prod["is_sold"] = True
        data["purchases"].append({"uid": uid, "prod_idx": idx, "time": time.time()})
        
        # Реферальные 10%
        if user["referrer"] and user["referrer"] in data["users"]:
            data["users"][user["referrer"]]["balance"] += prod["price"] * 0.1
            
        save_data(data)
        await callback.message.answer(f"✅ **Куплено!**\nНомер: `{prod['phone']}`\n\nФайл сессии ниже. Код запрашивайте в 'Мои покупки'.", parse_mode="Markdown")
        await callback.message.answer_document(FSInputFile(prod["session_path"]))
    else:
        await callback.answer("❌ Недостаточно средств", show_alert=True)

# --- МОИ ПОКУПКИ И ПОЛУЧЕНИЕ КОДА ---
@dp.message(F.text == "🛍 Мои покупки")
async def my_purchases(message: types.Message):
    data = load_data()
    uid = str(message.from_user.id)
    my_prods = [p for p in data["purchases"] if p["uid"] == uid]
    
    if not my_prods: return await message.answer("🛍 У вас пока нет покупок.")
    
    kb = InlineKeyboardBuilder()
    for i, p in enumerate(my_prods):
        prod = data["products"][p["prod_idx"]]
        kb.row(types.InlineKeyboardButton(text=f"📱 {prod['phone']}", callback_data=f"view_{i}"))
    await message.answer("🛍 **Ваши купленные аккаунты:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("view_"))
async def view_purchase(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    data = load_data()
    uid = str(callback.from_user.id)
    purchase = [p for p in data["purchases"] if p["uid"] == uid][idx]
    prod = data["products"][purchase["prod_idx"]]
    
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🔐 Получить код", callback_data=f"getcode_{purchase['prod_idx']}"))
    await callback.message.answer(f"📱 Аккаунт: `{prod['phone']}`\n🌍 Гео: {prod['geo']}\n🛠 Тип: {prod['type']}", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("getcode_"))
async def get_code(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    data = load_data()
    prod = data["products"][idx]
    
    await callback.answer("⏳ Запускаю юзербота на 5 минут...", show_alert=False)
    try:
        client = await manage_session(prod["session_path"])
        msgs = await client.get_messages(777000, limit=1)
        if msgs:
            await callback.message.answer(f"📩 **Код для {prod['phone']}:**\n`{msgs[0].message}`", parse_mode="Markdown")
        else:
            await callback.message.answer("⚠️ Код еще не пришел.")
    except Exception as e:
        await callback.message.answer("❌ Ошибка сессии. Обратитесь к @zyozp")

# --- АДМИНКА ---
@dp.message(F.text == "➕ Добавить товар", F.from_user.id == ADMIN_ID)
async def add_start(message: types.Message, state: FSMContext):
    await message.answer("📎 Скиньте .session файл:")
    await state.set_state(ShopStates.wait_acc_file)

@dp.message(ShopStates.wait_acc_file, F.document)
async def add_file(message: types.Message, state: FSMContext):
    path = f"sessions/{message.document.file_name}"
    await bot.download(message.document, destination=path)
    await state.update_data(path=path, phone=message.document.file_name.replace(".session", ""))
    await message.answer("💰 Цена (TON):")
    await state.set_state(ShopStates.wait_acc_price)

@dp.message(ShopStates.wait_acc_price)
async def add_price(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await message.answer("🌍 Гео:")
    await state.set_state(ShopStates.wait_acc_geo)

@dp.message(ShopStates.wait_acc_geo)
async def add_geo(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text)
    await message.answer("🛠 Тип (tdata/session):")
    await state.set_state(ShopStates.wait_acc_type)

@dp.message(ShopStates.wait_acc_type)
async def add_finish(message: types.Message, state: FSMContext):
    d = await state.get_data()
    data = load_data()
    data["products"].append({
        "phone": d["phone"], "price": d["price"], "session_path": d["path"],
        "geo": d["geo"], "type": message.text, "is_sold": False
    })
    save_data(data)
    await message.answer("✅ Добавлено в JSON!")
    await state.clear()

@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def broad_1(message: types.Message, state: FSMContext):
    await message.answer("📝 Текст рассылки:")
    await state.set_state(ShopStates.wait_broadcast_text)

@dp.message(ShopStates.wait_broadcast_text)
async def broad_2(message: types.Message, state: FSMContext):
    data = load_data()
    for uid in data["users"]:
        try: await bot.send_message(int(uid), message.text)
        except: pass
    await message.answer("✅ Рассылка завершена.")
    await state.clear()

@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
async def give_bal(message: types.Message, state: FSMContext):
    await message.answer("Введите ID:")
    await state.set_state(ShopStates.wait_bal_id)

@dp.message(ShopStates.wait_bal_id)
async def give_bal_2(message: types.Message, state: FSMContext):
    await state.update_data(uid=message.text)
    await message.answer("Сколько TON:")
    await state.set_state(ShopStates.wait_bal_amount)

@dp.message(ShopStates.wait_bal_amount)
async def give_bal_3(message: types.Message, state: FSMContext):
    d = await state.get_data()
    data = load_data()
    if d["uid"] in data["users"]:
        data["users"][d["uid"]]["balance"] += float(message.text)
        save_data(data)
        await message.answer("✅ Баланс выдан!")
    await state.clear()

# --- ЗАПУСК ---
async def main():
    if not os.path.exists("sessions"): os.makedirs("sessions")
    print("Sifon Market запущен без БД!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
