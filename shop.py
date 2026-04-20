import asyncio
import sqlite3
import logging
import os
import re
import requests # Не забудь установить: pip install requests
from datetime import datetime
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
API_ID = 37668790 
API_HASH = '84a0450f9bbf15d1e1d09b47ee25cb49'

# ДАННЫЕ ИЗ СКРИНШОТОВ
TONCENTER_API_KEY = "0e458295f7b90487efe40b089ee219a0d6faa842cba6c3dee5046de3db1532f"
MY_WALLET = "UQDlFKmdWxZqtT1ueKC58L6Kj77RLY6tGu3wW_aaZHGXt46O"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- ГЛОБАЛЬНЫЕ ДАННЫЕ ДЛЯ ВИКТОРИНЫ ---
quiz_config = {
    "answer": None,
    "prize_file_id": None,
    "is_active": False
}

# --- СОСТОЯНИЯ ---
class QuizState(StatesGroup):
    waiting_answer = State()
    waiting_prize = State()

class DepositStars(StatesGroup):
    amount = State()

# --- ЛОГИКА ПРОВЕРКИ TON ---
async def check_ton_payment_logic(user_id, amount_needed, comment):
    url = f"https://toncenter.com/api/v2/getTransactions?address={MY_WALLET}&limit=20&api_key={TONCENTER_API_KEY}"
    try:
        response = requests.get(url).json()
        if not response.get("ok"): return False
        
        for tx in response.get("result", []):
            in_msg = tx.get("in_msg", {})
            value = int(in_msg.get("value", 0)) / 10**9
            msg_comment = in_msg.get("message", "")
            
            # Если коммент совпадает с ID юзера и сумма верная
            if msg_comment == str(user_id) and value >= amount_needed:
                return True
    except Exception as e:
        logging.error(f"Ошибка проверки TON: {e}")
    return False

# --- ВИКТОРИНА (АДМИНКА) ---
@dp.callback_query(F.data == "admin_quiz", F.from_user.id == ADMIN_ID)
async def start_quiz_setup(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("🌍 Введи правильный ответ (ГЕО):")
    await state.set_state(QuizState.waiting_answer)

@dp.message(QuizState.waiting_answer)
async def quiz_answer_set(m: types.Message, state: FSMContext):
    await state.update_data(ans=m.text.lower())
    await m.answer("🎁 Отправь .session файл, который будет призом:")
    await state.set_state(QuizState.waiting_prize)

@dp.message(QuizState.waiting_prize, F.document)
async def quiz_finish_setup(m: types.Message, state: FSMContext):
    data = await state.get_data()
    quiz_config["answer"] = data['ans']
    quiz_config["prize_file_id"] = m.document.file_id
    quiz_config["is_active"] = True
    await m.answer(f"✅ Викторина запущена!\nОтвет: {data['ans']}\nПриз заряжен.")
    await state.clear()

# --- ОБРАБОТКА ГЕО (ДЛЯ ВСЕХ) ---
@dp.message(lambda m: quiz_config["is_active"])
async def handle_guesses(m: types.Message):
    if m.text.lower() == quiz_config["answer"]:
        quiz_config["is_active"] = False # Останавливаем
        await m.answer(f"🥳 КРАСАВА! Ты угадал ГЕО!\nТвой приз (аккаунт):")
        await bot.send_document(m.from_user.id, quiz_config["prize_file_id"])
        await bot.send_message(ADMIN_ID, f"👤 @{m.from_user.username} (ID: {m.from_user.id}) выиграл в викторине!")
        quiz_config["answer"] = None

# --- ПОПОЛНЕНИЕ ---
@dp.callback_query(F.data == "deposit")
async def select_dep_method(c: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="💎 TON (Кошелек)", callback_data="dep_ton"))
    b.row(types.InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="dep_stars"))
    b.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="profile"))
    await c.message.edit_text("Выберите способ пополнения:", reply_markup=b.as_markup())

# ПОПОЛНЕНИЕ TON
@dp.callback_query(F.data == "dep_ton")
async def dep_ton_info(c: types.CallbackQuery):
    text = (f"💠 **Пополнение через TON**\n\n"
            f"Отправьте нужную сумму на адрес:\n`{MY_WALLET}`\n\n"
            f"⚠️ **ВАЖНО:** В комментарии к платежу укажите ваш ID: `{c.from_user.id}`\n\n"
            f"После отправки нажмите кнопку ниже.")
    b = InlineKeyboardBuilder()
    b.row(types.InlineKeyboardButton(text="✅ Я оплатил", callback_data="check_ton"))
    await c.message.edit_text(text, reply_markup=b.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "check_ton")
async def check_payment_call(c: types.CallbackQuery):
    # Допустим, минималка 0.1 TON, проверка по ID пользователя в комменте
    is_paid = await check_ton_payment_logic(c.from_user.id, 0.1, str(c.from_user.id))
    if is_paid:
        # Тут логика начисления (нужно обновить в БД)
        # db_query("UPDATE users SET balance = balance + 0.1 ...")
        await c.message.answer("✅ Платеж найден! Баланс пополнен.")
    else:
        await c.answer("❌ Транзакция не найдена. Подождите 1-2 минуты.", show_alert=True)

# ПОПОЛНЕНИЕ STARS
@dp.callback_query(F.data == "dep_stars")
async def stars_invoice(c: types.CallbackQuery):
    await c.message.answer_invoice(
        title="Пополнение баланса",
        description=f"Пополнение баланса SifonShop для ID {c.from_user.id}",
        prices=[LabeledPrice(label="⭐ 50 Stars", amount=50)],
        provider_token="", # Для Stars пусто
        payload=f"topup_{c.from_user.id}",
        currency="XTR"
    )

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: types.Message):
    # Stars приходят как 1 star = 1 unit
    stars_amount = m.successful_payment.total_amount
    # Добавь логику зачисления в БД здесь
    await m.answer(f"⭐ Успешно! Вам зачислено {stars_amount} Stars.")

# --- ОБНОВЛЕННАЯ АДМИН-КЛАВИАТУРА ---
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
        builder.row(types.InlineKeyboardButton(text="🎁 Запустить Викторину", callback_data="admin_quiz"))
        builder.row(types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    return builder.as_markup()
