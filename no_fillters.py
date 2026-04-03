import os
import asyncio
import sqlite3
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========= CONFIG =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
API_URL = os.getenv("API_URL")

ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========= DATABASE =========
conn = sqlite3.connect("bot.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    approved INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    service_id INTEGER,
    link TEXT,
    quantity INTEGER,
    order_id INTEGER,
    status TEXT
)
""")

conn.commit()

# ========= API =========
def get_services():
    return requests.post(API_URL, data={
        "key": API_KEY,
        "action": "services"
    }).json()

def create_order(service, link, quantity):
    return requests.post(API_URL, data={
        "key": API_KEY,
        "action": "add",
        "service": service,
        "link": link,
        "quantity": quantity
    }).json()

# ========= HELPERS =========
def get_user(user_id):
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cur.fetchone()

    if not user:
        cur.execute("INSERT INTO users (user_id, approved) VALUES (?, 0)", (user_id,))
        conn.commit()
        return (user_id, 0)

    return user

def approve_user(user_id):
    cur.execute("UPDATE users SET approved=1 WHERE user_id=?", (user_id,))
    conn.commit()

def is_approved(user_id):
    cur.execute("SELECT approved FROM users WHERE user_id=?", (user_id,))
    result = cur.fetchone()
    return result and result[0] == 1

def get_telegram_services():
    services = get_services()
    return [s for s in services if "telegram" in s["name"].lower()]

# ========= START =========
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    user = get_user(msg.from_user.id)

    # لو مش متوافق عليه
    if user[1] == 0:
        await bot.send_message(
            ADMIN_ID,
            f"👤 مستخدم جديد\n\nID: {msg.from_user.id}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✅ موافقة",
                    callback_data=f"approve_{msg.from_user.id}"
                )]
            ])
        )

        await msg.answer("⏳ تم إرسال طلبك للإدارة للموافقة")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 طلب جديد", callback_data="new")],
        [InlineKeyboardButton(text="📦 طلباتي", callback_data="orders")]
    ])

    await msg.answer("👋 أهلا بيك في البوت", reply_markup=kb)

# ========= APPROVE =========
@dp.callback_query(F.data.startswith("approve_"))
async def approve(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    user_id = int(call.data.split("_")[1])
    approve_user(user_id)

    await call.message.edit_text("✅ تم قبول المستخدم")
    await bot.send_message(user_id, "✅ تم قبولك، تقدر تستخدم البوت الآن")

# ========= NEW ORDER =========
user_state = {}

@dp.callback_query(F.data == "new")
async def new_order(call: types.CallbackQuery):
    if not is_approved(call.from_user.id):
        await call.message.answer("❌ مش مسموح لك تستخدم البوت")
        return

    services = get_telegram_services()

    buttons = []
    for s in services[:10]:
        buttons.append([
            InlineKeyboardButton(
                text=f"{s['name']}",
                callback_data=f"service_{s['service']}"
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.answer("اختار الخدمة 👇", reply_markup=kb)

# ========= SELECT SERVICE =========
@dp.callback_query(F.data.startswith("service_"))
async def select_service(call: types.CallbackQuery):
    if not is_approved(call.from_user.id):
        return

    service_id = int(call.data.split("_")[1])
    user_state[call.from_user.id] = {"service": service_id}

    await call.message.answer("🔗 ابعت اللينك")

# ========= FLOW =========
@dp.message()
async def handle(msg: types.Message):
    user_id = msg.from_user.id

    if not is_approved(user_id):
        return

    if user_id not in user_state:
        return

    data = user_state[user_id]

    if "link" not in data:
        data["link"] = msg.text
        await msg.answer("📊 ابعت الكمية")
        return

    if "quantity" not in data:
        try:
            quantity = int(msg.text)
            if quantity <= 0:
                raise ValueError
            data["quantity"] = quantity
        except ValueError:
            await msg.answer("❌ اكتب رقم صحيح")
            return

        res = create_order(data["service"], data["link"], quantity)

        if "order" in res:
            order_id = res["order"]

            cur.execute("""
                INSERT INTO orders (user_id, service_id, link, quantity, order_id, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, data["service"], data["link"], quantity, order_id, "Pending"))
            conn.commit()

            await msg.answer(f"✅ تم الطلب\n📦 ID: {order_id}")
        else:
            await msg.answer("❌ فشل الطلب")

        user_state.pop(user_id)

# ========= ORDERS =========
@dp.callback_query(F.data == "orders")
async def orders(call: types.CallbackQuery):
    if not is_approved(call.from_user.id):
        await call.message.answer("❌ مش مسموح لك")
        return

    cur.execute("SELECT order_id, quantity, status FROM orders WHERE user_id=?", (call.from_user.id,))
    rows = cur.fetchall()

    if not rows:
        await call.message.answer("❌ مفيش طلبات")
        return

    text = "📦 طلباتك:\n\n"
    for r in rows:
        text += f"ID: {r[0]} | {r[1]} | {r[2]}\n"

    await call.message.answer(text)

# ========= RUN =========
async def main():
    print("Bot Started...")
    await dp.start_polling(bot)

asyncio.run(main())
