import os
import json
import asyncio
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from telethon import TelegramClient
from dotenv import load_dotenv

# --- ИНИЦИАЛИЗАЦИЯ ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
TON_WALLET = os.getenv("TON_WALLET")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DATA_FILE = "market_data.json"

class ShopStates(StatesGroup):
    wait_bal_id = State()
    wait_bal_amount = State()
    wait_acc_file = State()
    wait_acc_price = State()
    wait_acc_geo = State()
    wait_acc_stay = State()
    wait_acc_type = State()
    wait_broadcast_text = State()

# --- РАБОТА С ДАННЫМИ (JSON) ---
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
    builder.row(types.KeyboardButton(text="💰 Пополнить баланс"), types.KeyboardButton(text="🔐 Получить код"))
    builder.row(types.KeyboardButton(text="🛍 Мои покупки"), types.KeyboardButton(text="📜 История операций"))
    builder.row(types.KeyboardButton(text="🏆 Топ покупателей"), types.KeyboardButton(text="📋 Информация"))
    builder.row(types.KeyboardButton(text="🆘 Поддержка"))
    
    if user_id == ADMIN_ID:
        builder.row(types.KeyboardButton(text="➕ Добавить товар"), types.KeyboardButton(text="💎 Выдать баланс"))
        builder.row(types.KeyboardButton(text="📢 Рассылка"))
    return builder.as_markup(resize_keyboard=True)

# --- ЛОГИКА ТЕЛЕТОНА (БЕЗ СОХРАНЕНИЯ ФАЙЛОВ НАВСЕГДА) ---
async def fetch_telethon_data(file_id, file_name, action):
    """Скачивает файл на 2 секунды, берет данные и удаляет без следа."""
    temp_path = f"temp_{int(time.time())}_{file_name}"
    try:
        # Скачиваем файл из серверов ТГ временно
        tg_file = await bot.get_file(file_id)
        await bot.download_file(tg_file.file_path, destination=temp_path)

        # Подключаемся
        client = TelegramClient(temp_path, API_ID, API_HASH)
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            return "❌ Сессия мертва (выкинуло). Обратитесь в поддержку."

        if action == "number":
            me = await client.get_me()
            res = f"📱 **Номер аккаунта:** `+{me.phone}`\nТеперь вы можете запросить код."
        elif action == "code":
            msgs = await client.get_messages(777000, limit=1)
            if msgs and msgs[0].message:
                res = f"📩 **Код от Telegram:**\n\n`{msgs[0].message}`"
            else:
                res = "⚠️ Код еще не пришел. Подождите и попробуйте снова."
                
        await client.disconnect()
        return res
    except Exception as e:
        return f"❌ Ошибка чтения сессии. Обратитесь к администратору."
    finally:
        # ЖЕСТКАЯ ОЧИСТКА: удаляем саму сессию и любые временные файлы SQLite (-journal, -wal)
        for ext in ["", "-journal", "-wal", "-shm"]:
            p = temp_path + ext
            if os.path.exists(p):
                try: os.remove(p)
                except: pass

# --- ОБРАБОТЧИКИ СТАРТА И МЕНЮ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    data = load_data()
    uid = str(message.from_user.id)
    
    if uid not in data["users"]:
        data["users"][uid] = {"balance": 0, "spent": 0, "reg_date": time.time()}
        save_data(data)

    text = (
        "👋 **Добро пожаловать в Sifon Market!**\n\n"
        "🛒 Автоматический магазин качественных аккаунтов.\n"
        "⚡️ Мгновенная выдача файлов и кодов.\n"
        "🤝 Гарантия на момент покупки!"
    )
    await message.answer(text, reply_markup=main_kb(message.from_user.id), parse_mode="Markdown")

@dp.message(F.text == "📋 Информация")
async def info(message: types.Message):
    text = (
        "📋 **Информация о магазине**\n\n"
        "Мы магазин по покупке физических аккаунтов (и авторегов).\n"
        "✅ Мы обеспечиваем возврат средств или замену, если аккаунт оказался невалидным в момент выдачи!\n\n"
        "Для входа используйте выданный .session файл или получайте коды прямо здесь."
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🏆 Топ покупателей")
async def top_buyers(message: types.Message):
    data = load_data()
    users = data["users"]
    top = sorted(users.items(), key=lambda x: x[1].get("spent", 0), reverse=True)[:5]
    
    text = "🏆 **Топ 5 покупателей Sifon Market:**\n\n"
    for i, (uid, udata) in enumerate(top, 1):
        spent = round(udata.get('spent', 0), 2)
        if spent > 0:
            text += f"{i}. 👤 ID: `{uid}` — **{spent} TON**\n"
            
    if "👤 ID" not in text:
        text += "Пока нет покупателей. Станьте первым!"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📜 История операций")
async def history(message: types.Message):
    data = load_data()
    uid = str(message.from_user.id)
    my_history = [p for p in data["purchases"] if p["uid"] == uid][-5:]
    
    if not my_history: return await message.answer("📜 У вас еще нет операций.")
    
    text = "📜 **Ваши последние операции:**\n\n"
    for h in my_history:
        date = time.strftime('%d.%m %H:%M', time.localtime(h['time']))
        text += f"🔹 Аккаунт `{h['phone']}` — {h['price']} TON ({date})\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    data = load_data()
    uid = str(message.from_user.id)
    user = data["users"].get(uid, {"balance": 0, "spent": 0})
    text = (
        f"👤 **Ваш профиль**\n\n"
        f"🆔 ID: `{uid}`\n"
        f"💰 Баланс: **{round(user['balance'], 2)} TON**\n"
        f"🛍 Всего потрачено: **{round(user.get('spent', 0), 2)} TON**"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💰 Пополнить баланс")
async def topup(message: types.Message):
    text = (
        "💎 **Пополнение баланса (TON)**\n\n"
        f"📍 Переведите нужную сумму на адрес:\n`{TON_WALLET}`\n\n"
        f"💬 **В комментарии к переводу обязательно укажите:**\n`{message.from_user.id}`\n\n"
        "⚠️ Если вы не укажете этот ID в комментарии, деньги не будут зачислены!"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🆘 Поддержка")
async def support(message: types.Message):
    await message.answer("🆘 Возникли проблемы? Пишите: @zyozp")

# --- МАГАЗИН И ПОКУПКА ---
@dp.message(F.text == "🛒 Купить аккаунты")
async def shop(message: types.Message):
    data = load_data()
    geos = {}
    for p in data["products"]:
        if not p.get("is_sold"):
            geos[p["geo"]] = geos.get(p["geo"], 0) + 1
    
    if not geos: return await message.answer("📦 В наличии пока ничего нет.")
    
    kb = InlineKeyboardBuilder()
    for geo, count in geos.items():
        kb.row(types.InlineKeyboardButton(text=f"📍 {geo} ({count} шт.)", callback_data=f"cat_{geo}"))
    await message.answer("🌍 **Каталог аккаунтов. Выберите страну:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def show_geo_items(callback: types.CallbackQuery):
    geo = callback.data.split("_")[1]
    data = load_data()
    kb = InlineKeyboardBuilder()
    for i, p in enumerate(data["products"]):
        if p["geo"] == geo and not p.get("is_sold"):
            # Формат кнопки: Тип | Отлега | Цена
            btn_text = f"⚙️ {p['type']} | ⏳ {p['stay']} | 💵 {p['price']} TON"
            kb.row(types.InlineKeyboardButton(text=btn_text, callback_data=f"buy_{i}"))
    
    await callback.message.edit_text(f"📱 **Аккаунты ({geo}):**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("buy_"))
async def process_purchase(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    uid = str(callback.from_user.id)
    data = load_data()
    prod = data["products"][idx]
    user = data["users"][uid]

    if user["balance"] >= prod["price"]:
        user["balance"] -= prod["price"]
        user["spent"] = user.get("spent", 0) + prod["price"]
        prod["is_sold"] = True
        
        data["purchases"].append({
            "uid": uid, "phone": prod["phone"], "price": prod["price"], 
            "prod_idx": idx, "time": time.time()
        })
        save_data(data)
        
        await callback.message.answer(f"✅ **Покупка прошла успешно!**\nСписано: {prod['price']} TON.\n\nФайл сессии отправлен ниже. Чтобы узнать номер и код, нажмите 'Получить код' в меню.")
        
        # МАГИЯ: Отправляем файл покупателю напрямую из памяти серверов Telegram через file_id
        await callback.message.answer_document(document=prod["file_id"])
    else:
        await callback.answer("❌ Недостаточно средств на балансе!", show_alert=True)

# --- УПРАВЛЕНИЕ АККАУНТОМ (МОИ ПОКУПКИ И КОДЫ) ---
@dp.message(F.text.in_({"🔐 Получить код", "🛍 Мои покупки"}))
async def get_code_menu(message: types.Message):
    data = load_data()
    uid = str(message.from_user.id)
    my_prods = [p for p in data["purchases"] if p["uid"] == uid]
    
    if not my_prods: return await message.answer("🛍 У вас еще нет купленных аккаунтов.")
    
    kb = InlineKeyboardBuilder()
    for i, p in enumerate(my_prods):
        kb.row(types.InlineKeyboardButton(text=f"📱 Аккаунт {p['phone']}", callback_data=f"selacc_{p['prod_idx']}"))
    await message.answer("⬇️ **Выберите аккаунт для работы:**", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("selacc_"))
async def select_account(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📞 Показать номер", callback_data=f"getnum_{idx}"))
    kb.row(types.InlineKeyboardButton(text="📩 Запросить код", callback_data=f"getmsg_{idx}"))
    await callback.message.edit_text("⚙️ **Что вы хотите сделать?**\n*Сначала узнайте номер, затем запрашивайте код.*", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("getnum_"))
async def get_number(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    data = load_data()
    prod = data["products"][idx]
    
    await callback.answer("⏳ Авторизуемся для получения номера...", show_alert=False)
    # Передаем file_id для временного скачивания
    res = await fetch_telethon_data(prod["file_id"], prod["phone"] + ".session", "number")
    await callback.message.answer(res, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("getmsg_"))
async def get_message(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    data = load_data()
    prod = data["products"][idx]
    
    await callback.answer("🔎 Ищу новые сообщения...", show_alert=False)
    res = await fetch_telethon_data(prod["file_id"], prod["phone"] + ".session", "code")
    await callback.message.answer(res, parse_mode="Markdown")

# --- АДМИН ПАНЕЛЬ ---
@dp.message(F.text == "➕ Добавить товар", F.from_user.id == ADMIN_ID)
async def admin_add(message: types.Message, state: FSMContext):
    await message.answer("📎 Отправьте файл `.session` (он не будет сохранен на сервере, бот запомнит его ID):", parse_mode="Markdown")
    await state.set_state(ShopStates.wait_acc_file)

@dp.message(ShopStates.wait_acc_file, F.document)
async def admin_file(message: types.Message, state: FSMContext):
    if not message.document.file_name.endswith(".session"):
        return await message.answer("❌ Это не .session файл!")
    
    # Сохраняем ТОЛЬКО file_id
    await state.update_data(
        file_id=message.document.file_id, 
        phone=message.document.file_name.replace(".session", "")
    )
    await message.answer("💰 Цена (в TON, например 1.5):")
    await state.set_state(ShopStates.wait_acc_price)

@dp.message(ShopStates.wait_acc_price)
async def admin_price(message: types.Message, state: FSMContext):
    try:
        await state.update_data(price=float(message.text))
        await message.answer("🌍 Страна (Гео):")
        await state.set_state(ShopStates.wait_acc_geo)
    except:
        await message.answer("❌ Цена должна быть числом!")

@dp.message(ShopStates.wait_acc_geo)
async def admin_geo(message: types.Message, state: FSMContext):
    await state.update_data(geo=message.text)
    await message.answer("⏳ Отлега (например, '7 дней'):")
    await state.set_state(ShopStates.wait_acc_stay)

@dp.message(ShopStates.wait_acc_stay)
async def admin_stay(message: types.Message, state: FSMContext):
    await state.update_data(stay=message.text)
    await message.answer("🛠 Тип (например, 'Авторег / Фиш'):")
    await state.set_state(ShopStates.wait_acc_type)

@dp.message(ShopStates.wait_acc_type)
async def admin_finish(message: types.Message, state: FSMContext):
    d = await state.get_data()
    data = load_data()
    data["products"].append({
        "phone": d["phone"], 
        "price": d["price"], 
        "file_id": d["file_id"], # Сохраняем идентификатор телеграма!
        "geo": d["geo"], 
        "stay": d["stay"], 
        "type": message.text, 
        "is_sold": False
    })
    save_data(data)
    await message.answer(f"✅ Товар добавлен!\nСервер пуст, файл находится в облаке Telegram.")
    await state.clear()

@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
async def broad_1(message: types.Message, state: FSMContext):
    await message.answer("📝 Отправьте текст для рассылки всем пользователям:")
    await state.set_state(ShopStates.wait_broadcast_text)

@dp.message(ShopStates.wait_broadcast_text)
async def broad_2(message: types.Message, state: FSMContext):
    data = load_data()
    count = 0
    for uid in data["users"]:
        try: 
            await bot.send_message(int(uid), message.text)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Рассылка доставлена {count} пользователям.")
    await state.clear()

@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
async def give_bal(message: types.Message, state: FSMContext):
    await message.answer("Введите ID пользователя:")
    await state.set_state(ShopStates.wait_bal_id)

@dp.message(ShopStates.wait_bal_id)
async def give_bal_2(message: types.Message, state: FSMContext):
    await state.update_data(uid=message.text)
    await message.answer("Сколько TON зачислить?")
    await state.set_state(ShopStates.wait_bal_amount)

@dp.message(ShopStates.wait_bal_amount)
async def give_bal_3(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        d = await state.get_data()
        data = load_data()
        if d["uid"] in data["users"]:
            data["users"][d["uid"]]["balance"] += amount
            save_data(data)
            await message.answer("✅ Баланс успешно выдан!")
        else:
            await message.answer("❌ Пользователь не найден в базе (пусть напишет /start).")
        await state.clear()
    except:
        await message.answer("❌ Ошибка ввода числа.")

# --- ЗАПУСК ---
async def main():
    print("Sifon Market Cloud Edition запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
