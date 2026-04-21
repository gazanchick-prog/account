diff --git a/main.py b/main.py
index 2a670b1efb80aa0d9fed98432317746c99a77df8..31b832f8b7e5c2aed6f3a8a7070788cd01c1733e 100644
--- a/main.py
+++ b/main.py
@@ -1,31 +1,593 @@
+import asyncio
+import logging
+import os
+from pathlib import Path
+from typing import Optional
 
-from langchain.chains import RetrievalQA
-from langchain.vectorstores import Chroma
-from langchain.prompts import PromptTemplate
-from langchain_openai import OpenAIEmbeddings
-from langchain.chat_models import ChatOpenAI
-
-# Настройка векторной базы
-texts = [
-    "Привет, друзья! Сегодня поговорим о технологиях будущего.",
-    "Искусственный интеллект уже меняет нашу жизнь.",
-    "Квантовые компьютеры — это революция в обработке данных."
-]
-embeddings = OpenAIEmbeddings()
-vector_store = Chroma.from_texts(texts, embeddings)
-
-# Настройка цепочки RetrievalQA
-llm = ChatOpenAI(model="gpt-4")
-retrieval_chain = RetrievalQA.from_chain_type(
-    llm=llm,
-    retriever=vector_store.as_retriever(),
-    return_source_documents=False
-)
-
-# Выполнение запроса
-query = "Как технологии изменят будущее?"
-result = retrieval_chain.run(query)
-
-# Вывод результата
-print("Сгенерированный пост:")
-print(result)
+import aiosqlite
+from aiogram import Bot, Dispatcher, F, types
+from aiogram.filters import CommandStart
+from aiogram.fsm.context import FSMContext
+from aiogram.fsm.state import State, StatesGroup
+from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
+from dotenv import load_dotenv
+from telethon import TelegramClient
+
+
+load_dotenv()
+
+BOT_TOKEN = os.getenv("BOT_TOKEN", "")
+ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
+API_ID = int(os.getenv("API_ID", "0"))
+API_HASH = os.getenv("API_HASH", "")
+TON_WALLET = os.getenv("TON_WALLET", "UQDlFKmdWxZqtT1ueKC58L6Kj77RLY6tGu3wW_aaZHGXt46O")
+SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@zyozp")
+REFERRAL_PERCENT = float(os.getenv("REFERRAL_PERCENT", "0.10"))
+DB_NAME = os.getenv("DB_NAME", "sifon_market.db")
+SESSIONS_DIR = Path(os.getenv("SESSIONS_DIR", "sessions"))
+
+bot = Bot(BOT_TOKEN)
+dp = Dispatcher()
+BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@")
+
+
+class ShopStates(StatesGroup):
+    wait_bal_id = State()
+    wait_bal_amount = State()
+    wait_acc_file = State()
+    wait_acc_price = State()
+    wait_acc_geo = State()
+    wait_acc_stay = State()
+    wait_acc_type = State()
+    wait_broadcast_text = State()
+
+
+class UserbotPool:
+    def __init__(self) -> None:
+        self._clients: dict[str, TelegramClient] = {}
+
+    async def get_client(self, session_path: str) -> TelegramClient:
+        if session_path in self._clients:
+            client = self._clients[session_path]
+            if not client.is_connected():
+                await client.connect()
+            return client
+
+        client = TelegramClient(session_path, API_ID, API_HASH)
+        await client.connect()
+        self._clients[session_path] = client
+        return client
+
+    async def is_valid_authorized(self, session_path: str) -> bool:
+        try:
+            client = await self.get_client(session_path)
+            return await client.is_user_authorized()
+        except Exception:
+            return False
+
+    async def read_login_code(self, session_path: str) -> Optional[str]:
+        client = await self.get_client(session_path)
+        messages = await client.get_messages(777000, limit=1)
+        if not messages:
+            return None
+        return messages[0].message
+
+    async def resolve_phone(self, session_path: str) -> str:
+        client = await self.get_client(session_path)
+        me = await client.get_me()
+        return f"+{me.phone}" if me and me.phone else "unknown"
+
+    async def close_all(self) -> None:
+        for client in self._clients.values():
+            if client.is_connected():
+                await client.disconnect()
+
+
+userbot_pool = UserbotPool()
+
+
+async def init_db() -> None:
+    async with aiosqlite.connect(DB_NAME) as db:
+        await db.execute(
+            """
+            CREATE TABLE IF NOT EXISTS users (
+                user_id INTEGER PRIMARY KEY,
+                balance REAL DEFAULT 0,
+                referrer_id INTEGER,
+                referral_earned REAL DEFAULT 0,
+                created_at TEXT DEFAULT CURRENT_TIMESTAMP
+            )
+            """
+        )
+        await db.execute(
+            """
+            CREATE TABLE IF NOT EXISTS products (
+                id INTEGER PRIMARY KEY AUTOINCREMENT,
+                phone TEXT,
+                price REAL,
+                session_path TEXT,
+                geo TEXT,
+                stay TEXT,
+                type TEXT,
+                is_sold INTEGER DEFAULT 0,
+                added_at TEXT DEFAULT CURRENT_TIMESTAMP
+            )
+            """
+        )
+        await db.execute(
+            """
+            CREATE TABLE IF NOT EXISTS purchases (
+                id INTEGER PRIMARY KEY AUTOINCREMENT,
+                user_id INTEGER,
+                product_id INTEGER,
+                amount REAL,
+                purchased_at TEXT DEFAULT CURRENT_TIMESTAMP
+            )
+            """
+        )
+        await db.commit()
+
+
+def main_kb(user_id: int) -> types.ReplyKeyboardMarkup:
+    builder = ReplyKeyboardBuilder()
+    builder.row(types.KeyboardButton(text="🛒 Купить аккаунты"), types.KeyboardButton(text="👤 Профиль"))
+    builder.row(types.KeyboardButton(text="💰 Пополнить баланс"), types.KeyboardButton(text="🛍 Мои покупки"))
+    builder.row(types.KeyboardButton(text="🆘 Поддержка"))
+    if user_id == ADMIN_ID:
+        builder.row(types.KeyboardButton(text="➕ Добавить товар"), types.KeyboardButton(text="💎 Выдать баланс"))
+        builder.row(types.KeyboardButton(text="📢 Рассылка"))
+    return builder.as_markup(resize_keyboard=True)
+
+
+def parse_referrer(text: str) -> Optional[int]:
+    parts = text.split(maxsplit=1)
+    if len(parts) < 2:
+        return None
+    payload = parts[1].strip()
+    if payload.startswith("ref_"):
+        payload = payload[4:]
+    return int(payload) if payload.isdigit() else None
+
+
+@dp.message(CommandStart())
+async def cmd_start(message: types.Message) -> None:
+    user_id = message.from_user.id
+    referrer_id = parse_referrer(message.text or "")
+    if referrer_id == user_id:
+        referrer_id = None
+
+    async with aiosqlite.connect(DB_NAME) as db:
+        cur = await db.execute("SELECT user_id, referrer_id FROM users WHERE user_id = ?", (user_id,))
+        row = await cur.fetchone()
+        if not row:
+            await db.execute(
+                "INSERT INTO users (user_id, referrer_id) VALUES (?, ?)",
+                (user_id, referrer_id),
+            )
+            await db.commit()
+
+    welcome = (
+        "👋 <b>Добро пожаловать в Minon Shop!</b>\n\n"
+        "🛒 Покупайте качественные Telegram аккаунты\n"
+        "⚡ Моментальная выдача после оплаты\n"
+        "💰 Пополнение баланса: CryptoBot (USDT) и TON\n"
+        "🔐 Автоматическое получение кодов входа\n"
+        "🎁 Реферальная система: 10% с покупок друзей\n"
+        "🆘 Круглосуточная поддержка\n\n"
+        "💡 Приглашайте друзей и получайте 10% с их покупок!"
+    )
+    await message.answer(welcome, reply_markup=main_kb(user_id), parse_mode="HTML")
+
+
+@dp.message(F.text == "🆘 Поддержка")
+async def support(message: types.Message) -> None:
+    await message.answer(f"🆘 По всем вопросам обратитесь к {SUPPORT_USERNAME}")
+
+
+@dp.message(F.text == "💰 Пополнить баланс")
+async def topup(message: types.Message) -> None:
+    text = (
+        "💎 <b>Пополнение баланса (TON)</b>\n\n"
+        f"📍 <b>Адрес:</b>\n<code>{TON_WALLET}</code>\n\n"
+        f"💬 <b>Комментарий (СТРОГО ваш ID):</b>\n<code>{message.from_user.id}</code>\n\n"
+        "⚠️ Без комментария зачисление не выполняется."
+    )
+    await message.answer(text, parse_mode="HTML")
+
+
+@dp.message(F.text == "👤 Профиль")
+async def profile(message: types.Message) -> None:
+    uid = message.from_user.id
+    async with aiosqlite.connect(DB_NAME) as db:
+        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
+        await db.commit()
+        cur = await db.execute(
+            "SELECT balance, referral_earned FROM users WHERE user_id = ?",
+            (uid,),
+        )
+        row = await cur.fetchone()
+    if not row:
+        row = (0.0, 0.0)
+
+    username = BOT_USERNAME
+    if not username:
+        me = await bot.get_me()
+        username = me.username or ""
+    ref_link = f"https://t.me/{username}?start=ref_{uid}" if username else "Недоступно (нет username у бота)"
+    await message.answer(
+        "👤 <b>Профиль</b>\n"
+        f"🆔 ID: <code>{uid}</code>\n"
+        f"💰 Баланс: <b>{row[0]:.2f} TON</b>\n"
+        f"🎁 Заработано по рефералке: <b>{row[1]:.2f} TON</b>\n\n"
+        f"🔗 Ваша реф-ссылка:\n<code>{ref_link}</code>",
+        parse_mode="HTML",
+    )
+
+
+@dp.message(F.text == "🛒 Купить аккаунты")
+async def shop_categories(message: types.Message) -> None:
+    async with aiosqlite.connect(DB_NAME) as db:
+        cur = await db.execute("SELECT geo, COUNT(*) FROM products WHERE is_sold = 0 GROUP BY geo")
+        categories = await cur.fetchall()
+    if not categories:
+        await message.answer("📦 Сейчас нет аккаунтов в наличии.")
+        return
+
+    kb = InlineKeyboardBuilder()
+    for geo, count in categories:
+        kb.row(types.InlineKeyboardButton(text=f"📍 {geo} ({count} шт.)", callback_data=f"cat:{geo}"))
+    await message.answer("📁 Выберите локацию:", reply_markup=kb.as_markup())
+
+
+@dp.callback_query(F.data.startswith("cat:"))
+async def show_items(callback: types.CallbackQuery) -> None:
+    geo = callback.data.split(":", 1)[1]
+    async with aiosqlite.connect(DB_NAME) as db:
+        cur = await db.execute(
+            "SELECT id, type, stay, price FROM products WHERE geo = ? AND is_sold = 0 ORDER BY id DESC",
+            (geo,),
+        )
+        items = await cur.fetchall()
+
+    if not items:
+        await callback.answer("Товары закончились", show_alert=True)
+        return
+
+    kb = InlineKeyboardBuilder()
+    for pid, acc_type, stay, price in items:
+        kb.row(
+            types.InlineKeyboardButton(
+                text=f"⚙️ {acc_type} | ⏳ {stay} | 💵 {price:.2f} TON",
+                callback_data=f"buy:{pid}",
+            )
+        )
+    await callback.message.edit_text(f"📱 Аккаунты {geo}:", reply_markup=kb.as_markup())
+    await callback.answer()
+
+
+@dp.callback_query(F.data.startswith("buy:"))
+async def process_buy(callback: types.CallbackQuery) -> None:
+    user_id = callback.from_user.id
+    product_id = int(callback.data.split(":", 1)[1])
+
+    async with aiosqlite.connect(DB_NAME) as db:
+        await db.execute("BEGIN IMMEDIATE")
+
+        cur = await db.execute(
+            "SELECT price, session_path, phone, is_sold FROM products WHERE id = ?",
+            (product_id,),
+        )
+        product = await cur.fetchone()
+        if not product:
+            await db.rollback()
+            await callback.answer("Товар не найден", show_alert=True)
+            return
+
+        price, session_path, phone, is_sold = product
+        if is_sold:
+            await db.rollback()
+            await callback.answer("Этот товар уже продан", show_alert=True)
+            return
+
+        cur = await db.execute("SELECT balance, referrer_id FROM users WHERE user_id = ?", (user_id,))
+        user = await cur.fetchone()
+        if not user:
+            await db.rollback()
+            await callback.answer("Пользователь не найден", show_alert=True)
+            return
+
+        balance, referrer_id = user
+        if balance < price:
+            await db.rollback()
+            await callback.answer("❌ Недостаточно средств", show_alert=True)
+            return
+
+        valid = await userbot_pool.is_valid_authorized(session_path)
+        if not valid:
+            await db.rollback()
+            await callback.answer("Ошибка сессии. Обратитесь в поддержку.", show_alert=True)
+            return
+
+        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
+        await db.execute("UPDATE products SET is_sold = 1 WHERE id = ?", (product_id,))
+        await db.execute(
+            "INSERT INTO purchases (user_id, product_id, amount) VALUES (?, ?, ?)",
+            (user_id, product_id, price),
+        )
+
+        if referrer_id:
+            bonus = round(price * REFERRAL_PERCENT, 2)
+            await db.execute(
+                "UPDATE users SET balance = balance + ?, referral_earned = referral_earned + ? WHERE user_id = ?",
+                (bonus, bonus, referrer_id),
+            )
+            try:
+                await bot.send_message(
+                    referrer_id,
+                    f"🎁 Вам начислено {bonus:.2f} TON по реферальной программе.",
+                )
+            except Exception:
+                pass
+
+        await db.commit()
+
+    await callback.message.answer_document(
+        types.FSInputFile(session_path),
+        caption=f"✅ Покупка успешна\n📱 Номер: <code>{phone}</code>",
+        parse_mode="HTML",
+    )
+    await callback.message.answer("Аккаунт добавлен в раздел «🛍 Мои покупки».")
+    await callback.answer("Успешно")
+
+
+@dp.message(F.text == "🛍 Мои покупки")
+async def my_purchases(message: types.Message) -> None:
+    async with aiosqlite.connect(DB_NAME) as db:
+        cur = await db.execute(
+            """
+            SELECT p.id, pr.phone
+            FROM purchases p
+            JOIN products pr ON p.product_id = pr.id
+            WHERE p.user_id = ?
+            ORDER BY p.id DESC
+            """,
+            (message.from_user.id,),
+        )
+        rows = await cur.fetchall()
+
+    if not rows:
+        await message.answer("🛍 У вас пока нет покупок.")
+        return
+
+    kb = InlineKeyboardBuilder()
+    for purchase_id, phone in rows:
+        kb.row(types.InlineKeyboardButton(text=f"📱 {phone}", callback_data=f"view:{purchase_id}"))
+    await message.answer("🛍 Ваши покупки:", reply_markup=kb.as_markup())
+
+
+@dp.callback_query(F.data.startswith("view:"))
+async def view_item(callback: types.CallbackQuery) -> None:
+    purchase_id = int(callback.data.split(":", 1)[1])
+    async with aiosqlite.connect(DB_NAME) as db:
+        cur = await db.execute(
+            """
+            SELECT pr.phone
+            FROM purchases p
+            JOIN products pr ON p.product_id = pr.id
+            WHERE p.id = ? AND p.user_id = ?
+            """,
+            (purchase_id, callback.from_user.id),
+        )
+        row = await cur.fetchone()
+
+    if not row:
+        await callback.answer("Покупка не найдена", show_alert=True)
+        return
+
+    kb = InlineKeyboardBuilder()
+    kb.row(types.InlineKeyboardButton(text="📩 Получить код", callback_data=f"get:{purchase_id}"))
+    await callback.message.answer(f"📱 Аккаунт: <code>{row[0]}</code>", reply_markup=kb.as_markup(), parse_mode="HTML")
+    await callback.answer()
+
+
+@dp.callback_query(F.data.startswith("get:"))
+async def get_code(callback: types.CallbackQuery) -> None:
+    purchase_id = int(callback.data.split(":", 1)[1])
+
+    async with aiosqlite.connect(DB_NAME) as db:
+        cur = await db.execute(
+            """
+            SELECT pr.session_path
+            FROM purchases p
+            JOIN products pr ON p.product_id = pr.id
+            WHERE p.id = ? AND p.user_id = ?
+            """,
+            (purchase_id, callback.from_user.id),
+        )
+        row = await cur.fetchone()
+
+    if not row:
+        await callback.answer("Покупка не найдена", show_alert=True)
+        return
+
+    try:
+        code_message = await userbot_pool.read_login_code(row[0])
+        if code_message:
+            await callback.message.answer(f"📩 Последний код:\n<code>{code_message}</code>", parse_mode="HTML")
+        else:
+            await callback.message.answer("Код пока не найден в 777000.")
+    except Exception:
+        await callback.message.answer("❌ Ошибка сессии. Обратитесь в поддержку.")
+
+    await callback.answer()
+
+
+@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
+async def broadcast_step_1(message: types.Message, state: FSMContext) -> None:
+    await message.answer("📝 Введите текст для рассылки:")
+    await state.set_state(ShopStates.wait_broadcast_text)
+
+
+@dp.message(ShopStates.wait_broadcast_text)
+async def broadcast_step_2(message: types.Message, state: FSMContext) -> None:
+    async with aiosqlite.connect(DB_NAME) as db:
+        cur = await db.execute("SELECT user_id FROM users")
+        users = await cur.fetchall()
+
+    sent = 0
+    for (uid,) in users:
+        try:
+            await bot.send_message(uid, message.text)
+            sent += 1
+        except Exception:
+            continue
+
+    await message.answer(f"✅ Рассылка завершена. Получили: {sent} пользователей.")
+    await state.clear()
+
+
+@dp.message(F.text == "➕ Добавить товар", F.from_user.id == ADMIN_ID)
+async def add_product_step_1(message: types.Message, state: FSMContext) -> None:
+    await message.answer("📎 Отправьте .session файл:")
+    await state.set_state(ShopStates.wait_acc_file)
+
+
+@dp.message(ShopStates.wait_acc_file, F.document)
+async def add_product_step_2(message: types.Message, state: FSMContext) -> None:
+    if not message.document.file_name.endswith(".session"):
+        await message.answer("Нужен именно файл с расширением .session")
+        return
+
+    file_path = SESSIONS_DIR / message.document.file_name
+    await bot.download(message.document, destination=file_path)
+
+    try:
+        is_valid = await userbot_pool.is_valid_authorized(str(file_path))
+        if not is_valid:
+            await message.answer("❌ Сессия невалидная или неавторизованная.")
+            file_path.unlink(missing_ok=True)
+            return
+
+        phone = await userbot_pool.resolve_phone(str(file_path))
+    except Exception:
+        await message.answer("❌ Не удалось открыть сессию.")
+        file_path.unlink(missing_ok=True)
+        return
+
+    await state.update_data(path=str(file_path), phone=phone)
+    await message.answer(f"📱 Номер определён: <code>{phone}</code>\n💰 Введите цену (TON):", parse_mode="HTML")
+    await state.set_state(ShopStates.wait_acc_price)
+
+
+@dp.message(ShopStates.wait_acc_price)
+async def add_product_step_3(message: types.Message, state: FSMContext) -> None:
+    try:
+        price = float(message.text.replace(",", "."))
+    except ValueError:
+        await message.answer("Введите число, например: 12.5")
+        return
+
+    await state.update_data(price=price)
+    await message.answer("🌍 Введите GEO:")
+    await state.set_state(ShopStates.wait_acc_geo)
+
+
+@dp.message(ShopStates.wait_acc_geo)
+async def add_product_step_4(message: types.Message, state: FSMContext) -> None:
+    await state.update_data(geo=message.text.strip())
+    await message.answer("⏳ Введите отлёгу:")
+    await state.set_state(ShopStates.wait_acc_stay)
+
+
+@dp.message(ShopStates.wait_acc_stay)
+async def add_product_step_5(message: types.Message, state: FSMContext) -> None:
+    await state.update_data(stay=message.text.strip())
+    await message.answer("🛠 Введите тип аккаунта:")
+    await state.set_state(ShopStates.wait_acc_type)
+
+
+@dp.message(ShopStates.wait_acc_type)
+async def add_product_step_6(message: types.Message, state: FSMContext) -> None:
+    data = await state.get_data()
+    async with aiosqlite.connect(DB_NAME) as db:
+        await db.execute(
+            """
+            INSERT INTO products (phone, price, session_path, geo, stay, type)
+            VALUES (?, ?, ?, ?, ?, ?)
+            """,
+            (
+                data["phone"],
+                data["price"],
+                data["path"],
+                data["geo"],
+                data["stay"],
+                message.text.strip(),
+            ),
+        )
+        await db.commit()
+
+    await message.answer("✅ Товар добавлен в магазин.")
+    await state.clear()
+
+
+@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
+async def give_balance_step_1(message: types.Message, state: FSMContext) -> None:
+    await message.answer("Введите ID пользователя:")
+    await state.set_state(ShopStates.wait_bal_id)
+
+
+@dp.message(ShopStates.wait_bal_id)
+async def give_balance_step_2(message: types.Message, state: FSMContext) -> None:
+    if not message.text.isdigit():
+        await message.answer("ID должен состоять только из цифр.")
+        return
+    await state.update_data(uid=int(message.text))
+    await message.answer("Сколько TON начислить?")
+    await state.set_state(ShopStates.wait_bal_amount)
+
+
+@dp.message(ShopStates.wait_bal_amount)
+async def give_balance_step_3(message: types.Message, state: FSMContext) -> None:
+    try:
+        amount = float(message.text.replace(",", "."))
+    except ValueError:
+        await message.answer("Введите число, например: 3.25")
+        return
+
+    data = await state.get_data()
+    uid = data["uid"]
+
+    async with aiosqlite.connect(DB_NAME) as db:
+        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
+        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, uid))
+        await db.commit()
+
+    await message.answer("✅ Баланс успешно начислен.")
+    await state.clear()
+
+
+async def main() -> None:
+    if not BOT_TOKEN:
+        raise RuntimeError("BOT_TOKEN is missing in .env")
+    if not API_ID or not API_HASH:
+        raise RuntimeError("API_ID/API_HASH is missing in .env")
+
+    global BOT_USERNAME
+
+    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
+    await init_db()
+    try:
+        BOT_USERNAME = (await bot.get_me()).username or BOT_USERNAME
+    except Exception:
+        pass
+
+    logging.basicConfig(level=logging.INFO)
+    try:
+        await dp.start_polling(bot)
+    finally:
+        await userbot_pool.close_all()
+        await bot.session.close()
+
+
+if __name__ == "__main__":
+    asyncio.run(main())
