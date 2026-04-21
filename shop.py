diff --git a/shop.py b/shop.py
new file mode 100644
index 0000000000000000000000000000000000000000..2c5ad351c533585dff7f907303a2850aa70bb8dd
--- /dev/null
+++ b/shop.py
@@ -0,0 +1,414 @@
+"""
+Lite Telegram shop bot (single-file, no database).
+
+.env required:
+- BOT_TOKEN
+- ADMIN_ID
+
+Optional:
+- TON_WALLET
+- SUPPORT_USERNAME
+- REFERRAL_PERCENT
+"""
+
+import asyncio
+import logging
+import os
+from dataclasses import dataclass
+from typing import Dict, List, Optional
+
+from aiogram import Bot, Dispatcher, F, types
+from aiogram.filters import CommandStart
+from aiogram.fsm.context import FSMContext
+from aiogram.fsm.state import State, StatesGroup
+from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
+from dotenv import load_dotenv
+
+load_dotenv()
+
+BOT_TOKEN = os.getenv("BOT_TOKEN", "")
+ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
+TON_WALLET = os.getenv("TON_WALLET", "UQDlFKmdWxZqtT1ueKC58L6Kj77RLY6tGu3wW_aaZHGXt46O")
+SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@zyozp")
+REFERRAL_PERCENT = float(os.getenv("REFERRAL_PERCENT", "0.10"))
+
+bot = Bot(BOT_TOKEN)
+dp = Dispatcher()
+
+
+@dataclass
+class UserData:
+    balance: float = 0.0
+    referrer_id: Optional[int] = None
+    referral_earned: float = 0.0
+    purchases: List[int] = None
+
+    def __post_init__(self):
+        if self.purchases is None:
+            self.purchases = []
+
+
+@dataclass
+class Product:
+    id: int
+    file_id: str
+    file_name: str
+    phone: str
+    price: float
+    geo: str
+    stay: str
+    acc_type: str
+    sold: bool = False
+
+
+USERS: Dict[int, UserData] = {}
+PRODUCTS: Dict[int, Product] = {}
+LAST_PRODUCT_ID = 0
+BOT_USERNAME = ""
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
+def ensure_user(user_id: int, referrer: Optional[int] = None) -> UserData:
+    if user_id not in USERS:
+        USERS[user_id] = UserData(referrer_id=referrer if referrer != user_id else None)
+    return USERS[user_id]
+
+
+def main_kb(user_id: int) -> types.ReplyKeyboardMarkup:
+    kb = ReplyKeyboardBuilder()
+    kb.row(types.KeyboardButton(text="🛒 Купить аккаунты"), types.KeyboardButton(text="👤 Профиль"))
+    kb.row(types.KeyboardButton(text="💰 Пополнить баланс"), types.KeyboardButton(text="🛍 Мои покупки"))
+    kb.row(types.KeyboardButton(text="🆘 Поддержка"))
+    if user_id == ADMIN_ID:
+        kb.row(types.KeyboardButton(text="➕ Добавить товар"), types.KeyboardButton(text="💎 Выдать баланс"))
+        kb.row(types.KeyboardButton(text="📢 Рассылка"))
+    return kb.as_markup(resize_keyboard=True)
+
+
+def parse_referral_payload(text: str) -> Optional[int]:
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
+async def cmd_start(message: types.Message):
+    referrer = parse_referral_payload(message.text or "")
+    ensure_user(message.from_user.id, referrer)
+    text = (
+        "👋 <b>Добро пожаловать в Minon Shop!</b>\n\n"
+        "🛒 Покупайте качественные Telegram аккаунты\n"
+        "⚡ Моментальная выдача после оплаты\n"
+        "🎁 Реферальная система: 10% с покупок друзей\n"
+        "🆘 Поддержка 24/7"
+    )
+    await message.answer(text, parse_mode="HTML", reply_markup=main_kb(message.from_user.id))
+
+
+@dp.message(F.text == "👤 Профиль")
+async def profile(message: types.Message):
+    user = ensure_user(message.from_user.id)
+    if BOT_USERNAME:
+        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{message.from_user.id}"
+    else:
+        ref_link = "Недоступно"
+
+    await message.answer(
+        "👤 <b>Профиль</b>\n"
+        f"🆔 ID: <code>{message.from_user.id}</code>\n"
+        f"💰 Баланс: <b>{user.balance:.2f} TON</b>\n"
+        f"🎁 Реф. доход: <b>{user.referral_earned:.2f} TON</b>\n\n"
+        f"🔗 Ваша ссылка:\n<code>{ref_link}</code>",
+        parse_mode="HTML",
+    )
+
+
+@dp.message(F.text == "💰 Пополнить баланс")
+async def topup(message: types.Message):
+    await message.answer(
+        "💎 <b>Пополнение баланса (TON)</b>\n\n"
+        f"📍 <b>Адрес:</b>\n<code>{TON_WALLET}</code>\n\n"
+        f"💬 <b>Комментарий (СТРОГО ваш ID):</b>\n<code>{message.from_user.id}</code>\n\n"
+        "⚠️ Без комментария зачисление не выполняется.",
+        parse_mode="HTML",
+    )
+
+
+@dp.message(F.text == "🆘 Поддержка")
+async def support(message: types.Message):
+    await message.answer(f"🆘 По всем вопросам: {SUPPORT_USERNAME}")
+
+
+@dp.message(F.text == "🛒 Купить аккаунты")
+async def show_categories(message: types.Message):
+    categories: Dict[str, int] = {}
+    for p in PRODUCTS.values():
+        if not p.sold:
+            categories[p.geo] = categories.get(p.geo, 0) + 1
+
+    if not categories:
+        await message.answer("📦 Сейчас нет товаров в наличии.")
+        return
+
+    kb = InlineKeyboardBuilder()
+    for geo, count in categories.items():
+        kb.row(types.InlineKeyboardButton(text=f"📍 {geo} ({count} шт.)", callback_data=f"cat:{geo}"))
+    await message.answer("📁 Выберите локацию:", reply_markup=kb.as_markup())
+
+
+@dp.callback_query(F.data.startswith("cat:"))
+async def show_products(callback: types.CallbackQuery):
+    geo = callback.data.split(":", 1)[1]
+    kb = InlineKeyboardBuilder()
+    for p in PRODUCTS.values():
+        if not p.sold and p.geo == geo:
+            kb.row(types.InlineKeyboardButton(text=f"⚙️ {p.acc_type} | ⏳ {p.stay} | 💵 {p.price:.2f} TON", callback_data=f"buy:{p.id}"))
+
+    if not kb.buttons:
+        await callback.answer("Товаров нет", show_alert=True)
+        return
+
+    await callback.message.edit_text(f"📱 Аккаунты {geo}:", reply_markup=kb.as_markup())
+    await callback.answer()
+
+
+@dp.callback_query(F.data.startswith("buy:"))
+async def buy_product(callback: types.CallbackQuery):
+    uid = callback.from_user.id
+    ensure_user(uid)
+    pid = int(callback.data.split(":", 1)[1])
+    p = PRODUCTS.get(pid)
+
+    if not p or p.sold:
+        await callback.answer("Товар недоступен", show_alert=True)
+        return
+
+    user = USERS[uid]
+    if user.balance < p.price:
+        await callback.answer("❌ Недостаточно средств", show_alert=True)
+        return
+
+    user.balance -= p.price
+    p.sold = True
+    user.purchases.append(pid)
+
+    if user.referrer_id and user.referrer_id in USERS:
+        bonus = round(p.price * REFERRAL_PERCENT, 2)
+        USERS[user.referrer_id].balance += bonus
+        USERS[user.referrer_id].referral_earned += bonus
+        try:
+            await bot.send_message(user.referrer_id, f"🎁 Реферальный бонус: +{bonus:.2f} TON")
+        except Exception:
+            pass
+
+    await callback.message.answer_document(
+        p.file_id,
+        caption=f"✅ Покупка успешна\n📱 Номер: <code>{p.phone}</code>",
+        parse_mode="HTML",
+    )
+    await callback.answer("Успешно")
+
+
+@dp.message(F.text == "🛍 Мои покупки")
+async def my_purchases(message: types.Message):
+    user = ensure_user(message.from_user.id)
+    if not user.purchases:
+        await message.answer("🛍 Покупок пока нет.")
+        return
+
+    kb = InlineKeyboardBuilder()
+    for pid in user.purchases:
+        p = PRODUCTS.get(pid)
+        if p:
+            kb.row(types.InlineKeyboardButton(text=f"📱 {p.phone}", callback_data=f"view:{pid}"))
+    await message.answer("🛍 Ваши покупки:", reply_markup=kb.as_markup())
+
+
+@dp.callback_query(F.data.startswith("view:"))
+async def view_purchase(callback: types.CallbackQuery):
+    pid = int(callback.data.split(":", 1)[1])
+    user = ensure_user(callback.from_user.id)
+    if pid not in user.purchases:
+        await callback.answer("Покупка не найдена", show_alert=True)
+        return
+
+    p = PRODUCTS.get(pid)
+    if not p:
+        await callback.answer("Покупка не найдена", show_alert=True)
+        return
+
+    kb = InlineKeyboardBuilder()
+    kb.row(types.InlineKeyboardButton(text="📤 Получить .session", callback_data=f"session:{pid}"))
+    kb.row(types.InlineKeyboardButton(text="📩 Получить код", callback_data=f"code:{pid}"))
+    await callback.message.answer(f"📱 Аккаунт: <code>{p.phone}</code>", parse_mode="HTML", reply_markup=kb.as_markup())
+    await callback.answer()
+
+
+@dp.callback_query(F.data.startswith("session:"))
+async def resend_session(callback: types.CallbackQuery):
+    pid = int(callback.data.split(":", 1)[1])
+    user = ensure_user(callback.from_user.id)
+    if pid not in user.purchases:
+        await callback.answer("Нет доступа", show_alert=True)
+        return
+    p = PRODUCTS.get(pid)
+    if not p:
+        await callback.answer("Файл не найден", show_alert=True)
+        return
+    await callback.message.answer_document(p.file_id, caption="📎 Ваш .session файл")
+    await callback.answer()
+
+
+@dp.callback_query(F.data.startswith("code:"))
+async def get_code_notice(callback: types.CallbackQuery):
+    await callback.answer()
+    await callback.message.answer("ℹ️ В lite-версии без БД и userbot код не читается автоматически. Используйте выданный .session.")
+
+
+@dp.message(F.text == "📢 Рассылка", F.from_user.id == ADMIN_ID)
+async def broadcast_start(message: types.Message, state: FSMContext):
+    await message.answer("📝 Введите текст рассылки:")
+    await state.set_state(ShopStates.wait_broadcast_text)
+
+
+@dp.message(ShopStates.wait_broadcast_text)
+async def broadcast_send(message: types.Message, state: FSMContext):
+    sent = 0
+    for uid in USERS.keys():
+        try:
+            await bot.send_message(uid, message.text)
+            sent += 1
+        except Exception:
+            pass
+    await message.answer(f"✅ Отправлено: {sent}")
+    await state.clear()
+
+
+@dp.message(F.text == "💎 Выдать баланс", F.from_user.id == ADMIN_ID)
+async def balance_start(message: types.Message, state: FSMContext):
+    await message.answer("Введите ID пользователя:")
+    await state.set_state(ShopStates.wait_bal_id)
+
+
+@dp.message(ShopStates.wait_bal_id)
+async def balance_user(message: types.Message, state: FSMContext):
+    if not message.text.isdigit():
+        await message.answer("ID должен быть числом")
+        return
+    await state.update_data(uid=int(message.text))
+    await message.answer("Сколько TON начислить?")
+    await state.set_state(ShopStates.wait_bal_amount)
+
+
+@dp.message(ShopStates.wait_bal_amount)
+async def balance_amount(message: types.Message, state: FSMContext):
+    try:
+        amount = float(message.text.replace(",", "."))
+    except ValueError:
+        await message.answer("Введите корректное число")
+        return
+
+    data = await state.get_data()
+    u = ensure_user(data["uid"])
+    u.balance += amount
+    await message.answer("✅ Баланс начислен")
+    await state.clear()
+
+
+@dp.message(F.text == "➕ Добавить товар", F.from_user.id == ADMIN_ID)
+async def add_start(message: types.Message, state: FSMContext):
+    await message.answer("📎 Отправьте .session файл")
+    await state.set_state(ShopStates.wait_acc_file)
+
+
+@dp.message(ShopStates.wait_acc_file, F.document)
+async def add_file(message: types.Message, state: FSMContext):
+    doc = message.document
+    if not doc.file_name.lower().endswith(".session"):
+        await message.answer("Нужен файл .session")
+        return
+
+    await state.update_data(file_id=doc.file_id, file_name=doc.file_name, phone=doc.file_name.replace('.session', ''))
+    await message.answer("💰 Введите цену (TON):")
+    await state.set_state(ShopStates.wait_acc_price)
+
+
+@dp.message(ShopStates.wait_acc_price)
+async def add_price(message: types.Message, state: FSMContext):
+    try:
+        price = float(message.text.replace(",", "."))
+    except ValueError:
+        await message.answer("Введите число")
+        return
+    await state.update_data(price=price)
+    await message.answer("🌍 Введите GEO:")
+    await state.set_state(ShopStates.wait_acc_geo)
+
+
+@dp.message(ShopStates.wait_acc_geo)
+async def add_geo(message: types.Message, state: FSMContext):
+    await state.update_data(geo=message.text.strip())
+    await message.answer("⏳ Введите отлёгу:")
+    await state.set_state(ShopStates.wait_acc_stay)
+
+
+@dp.message(ShopStates.wait_acc_stay)
+async def add_stay(message: types.Message, state: FSMContext):
+    await state.update_data(stay=message.text.strip())
+    await message.answer("🛠 Введите тип:")
+    await state.set_state(ShopStates.wait_acc_type)
+
+
+@dp.message(ShopStates.wait_acc_type)
+async def add_finish(message: types.Message, state: FSMContext):
+    global LAST_PRODUCT_ID
+    data = await state.get_data()
+    LAST_PRODUCT_ID += 1
+    PRODUCTS[LAST_PRODUCT_ID] = Product(
+        id=LAST_PRODUCT_ID,
+        file_id=data["file_id"],
+        file_name=data["file_name"],
+        phone=data["phone"],
+        price=data["price"],
+        geo=data["geo"],
+        stay=data["stay"],
+        acc_type=message.text.strip(),
+    )
+    await message.answer(f"✅ Товар добавлен: #{LAST_PRODUCT_ID}")
+    await state.clear()
+
+
+async def main():
+    if not BOT_TOKEN:
+        raise RuntimeError("BOT_TOKEN not found in .env")
+    if ADMIN_ID == 0:
+        raise RuntimeError("ADMIN_ID not found in .env")
+
+    logging.basicConfig(level=logging.INFO)
+
+    global BOT_USERNAME
+    try:
+        me = await bot.get_me()
+        BOT_USERNAME = me.username or ""
+    except Exception as e:
+        raise RuntimeError("BOT_TOKEN невалидный (Unauthorized). Проверь токен в .env") from e
+
+    await dp.start_polling(bot)
+
+
+if __name__ == "__main__":
+    asyncio.run(main())
