import asyncio
import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery, Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8732592385:AAF2TWsYOhRSZRDpXdYDHGL8Q0CUyY5U3SA"          # Замените на свой токен
ADMIN_ID = 8754872846                          # Ваш Telegram ID (для логов/уведомлений)

# Товары: id -> название, цена (в Stars), путь к файлу, описание
PRODUCTS = {
    1: {
        "name": "AutoTurret AI",
        "price": 50,
        "file": "plugins/AutoTurret.cs",
        "desc": "Автоматическая турель с искусственным интеллектом. Стреляет только по врагам."
    },
    2: {
        "name": "RaidAlert",
        "price": 30,
        "file": "plugins/RaidAlert.cs",
        "desc": "Оповещает всю команду о начале рейда на вашу базу."
    },
    3: {
        "name": "NightVision",
        "price": 20,
        "file": "plugins/NightVision.cs",
        "desc": "Включает ночное зрение для всех игроков на сервере."
    }
}

# Создаём папку для файлов плагинов, если её нет
Path("plugins").mkdir(exist_ok=True)

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            purchased TEXT   -- JSON список купленных id товаров
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            user_id INTEGER,
            product_id INTEGER,
            amount INTEGER,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_purchase(user_id: int, username: str, product_id: int):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("SELECT purchased FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row:
        purchased = json.loads(row[0])
        if product_id not in purchased:
            purchased.append(product_id)
        c.execute("UPDATE users SET purchased = ? WHERE user_id = ?", (json.dumps(purchased), user_id))
    else:
        c.execute("INSERT INTO users (user_id, username, purchased) VALUES (?, ?, ?)",
                  (user_id, username, json.dumps([product_id])))
    conn.commit()
    conn.close()

def has_purchased(user_id: int, product_id: int) -> bool:
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("SELECT purchased FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        purchased = json.loads(row[0])
        return product_id in purchased
    return False

def get_user_purchases(user_id: int) -> List[int]:
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("SELECT purchased FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else []

def log_payment(payment_id: str, user_id: int, product_id: int, amount: int, status: str):
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO payments (payment_id, user_id, product_id, amount, status) VALUES (?,?,?,?,?)",
              (payment_id, user_id, product_id, amount, status))
    conn.commit()
    conn.close()

# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Магазин", callback_data="shop")
    builder.button(text="📦 Мои покупки", callback_data="my_purchases")
    builder.adjust(1)
    return builder.as_markup()

def get_products_keyboard():
    builder = InlineKeyboardBuilder()
    for pid, info in PRODUCTS.items():
        builder.button(text=f"{info['name']} — {info['price']}⭐", callback_data=f"buy_{pid}")
    builder.button(text="◀ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="◀ Назад", callback_data="back_to_main")
    return builder.as_markup()

# ==================== ОБРАБОТЧИКИ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🤖 *Добро пожаловать в магазин плагинов для Rust!*\n\n"
        "Здесь вы можете купить уникальные плагины для вашего сервера.\n"
        "Оплата производится *Telegram Stars* — внутренней валютой.\n\n"
        "Используйте кнопки ниже для навигации.",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data == "shop")
async def show_shop(callback: CallbackQuery):
    await callback.message.edit_text(
        "📦 *Каталог плагинов:*\n\n" +
        "\n".join([f"{p['name']} — {p['price']}⭐\n_{p['desc']}_" for p in PRODUCTS.values()]),
        reply_markup=get_products_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "my_purchases")
async def show_my_purchases(callback: CallbackQuery):
    user_id = callback.from_user.id
    purchases = get_user_purchases(user_id)
    if not purchases:
        text = "У вас пока нет покупок. Перейдите в «Магазин», чтобы приобрести плагины."
        reply_markup = get_back_keyboard()
    else:
        text = "✅ *Ваши приобретённые плагины:*\n\n"
        buttons = []
        for pid in purchases:
            if pid in PRODUCTS:
                text += f"• {PRODUCTS[pid]['name']}\n"
                buttons.append([types.InlineKeyboardButton(
                    text=f"📥 Скачать {PRODUCTS[pid]['name']}",
                    callback_data=f"download_{pid}"
                )])
        buttons.append([types.InlineKeyboardButton(text="◀ Назад", callback_data="back_to_main")])
        reply_markup = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = PRODUCTS.get(product_id)
    if not product:
        await callback.answer("Товар не найден!", show_alert=True)
        return

    # Проверяем, не куплен ли уже
    if has_purchased(callback.from_user.id, product_id):
        await callback.answer("Вы уже покупали этот плагин! Скачайте его в «Мои покупки».", show_alert=True)
        return

    # Создаём инвойс (счёт) в Telegram Stars
    prices = [LabeledPrice(label=product["name"], amount=product["price"])]
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Покупка плагина {product['name']}",
        description=product["desc"],
        payload=f"plugin_{product_id}",
        provider_token="",  # Для Stars оставляем пустым
        currency="XTR",     # XTR = Telegram Stars
        prices=prices,
        start_parameter="buy_plugin",
        need_name=False,
        need_phone_number=False,
        need_email=False,
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout: PreCheckoutQuery):
    # Всегда подтверждаем (можно добавить проверку наличия файла)
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload  # "plugin_1"
    product_id = int(payload.split("_")[1])
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.full_name

    # Логируем оплату
    log_payment(payment.telegram_payment_charge_id, user_id, product_id, payment.total_amount, "success")

    # Добавляем покупку в БД
    add_purchase(user_id, username, product_id)

    # Отправляем файл
    file_path = PRODUCTS[product_id]["file"]
    try:
        with open(file_path, "rb") as f:
            await message.answer_document(
                document=types.BufferedInputFile(f.read(), filename=Path(file_path).name),
                caption=f"✅ Спасибо за покупку!\nВаш плагин **{PRODUCTS[product_id]['name']}** готов к использованию.",
                parse_mode="Markdown"
            )
    except FileNotFoundError:
        await message.answer(
            f"❌ Ошибка: файл плагина не найден на сервере. Обратитесь к администратору @admin.\n"
            f"Вы купили: {PRODUCTS[product_id]['name']}"
        )
        # Уведомляем админа
        await bot.send_message(ADMIN_ID, f"Файл {file_path} не найден! Пользователь {user_id} купил {product_id}")

    # Также показываем кнопку назад
    await message.answer("Вы можете вернуться в магазин или посмотреть свои покупки.", reply_markup=get_main_keyboard())

@dp.callback_query(lambda c: c.data.startswith("download_"))
async def download_plugin(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    if not has_purchased(user_id, product_id):
        await callback.answer("Вы не приобретали этот плагин!", show_alert=True)
        return

    file_path = PRODUCTS[product_id]["file"]
    try:
        with open(file_path, "rb") as f:
            await callback.message.answer_document(
                document=types.BufferedInputFile(f.read(), filename=Path(file_path).name),
                caption=f"📥 Вы запросили файл плагина **{PRODUCTS[product_id]['name']}**"
            )
    except FileNotFoundError:
        await callback.message.answer(f"❌ Файл временно недоступен. Попробуйте позже или свяжитесь с администратором.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🤖 Главное меню магазина плагинов для Rust",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

# ==================== ЗАПУСК ====================
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
