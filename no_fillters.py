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

ADMIN_ID = os.getenv("ADMIN_ID")
VODAFONE_NUMBER = os.getenv("VODAFONE_NUMBER")

PROFIT_PERCENT = 2  # 200% ربح

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========= DATABASE =========
conn = sqlite3.connect("bot.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0
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
        cur.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0))
        conn.commit()
        return (user_id, 0)
    return user

def update_balance(user_id, amount):
    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (amount, user_id))
    conn.commit()

def add_balance(user_id, amount):
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def deduct_balance(user_id, amount):
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    bal = cur.fetchone()[0]

    if bal < amount:
        return False

    cur.execute("UPDATE users SET balance=? WHERE user_id=?", (bal - amount, user_id))
    conn.commit()
    return True

def calc_price(rate, quantity):
    base = (float(rate) / 1000) * quantity
    return round(base + (base * PROFIT_PERCENT), 4)

def get_telegram_services():
    services = get_services()
    return [s for s in services if "telegram" in s["name"].lower()]

# ========= START =========
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    get_user(msg.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 رصيدي", callback_data="balance")],
        [InlineKeyboardButton(text="🛒 طلب جديد", callback_data="new")],
        [InlineKeyboardButton(text="📦 طلباتي", callback_data="orders")],
        [InlineKeyboardButton(text="💳 شحن رصيد", callback_data="charge")]
    ])

    await msg.answer("👋 أهلا بيك في بوت الخدمات", reply_markup=kb)

# ========= BALANCE =========
@dp.callback_query(F.data == "balance")
async def balance(call: types.CallbackQuery):
    user = get_user(call.from_user.id)
    await call.message.answer(f"💰 رصيدك: {user[1]}$")

# ========= CHARGE =========
@dp.callback_query(F.data == "charge")
async def charge(call: types.CallbackQuery):
    await call.message.answer(
        f"💳 حول على الرقم:\n{VODAFONE_NUMBER}\n\n"
        "📸 ابعت صورة التحويل + اكتب المبلغ في الكابشن"
    )

# ========= PROOF =========
@dp.message(F.photo)
async def proof(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        return

    caption = msg.caption

    if not caption or not caption.isdigit():
        await msg.answer("❌ اكتب المبلغ في الكابشن")
        return

    amount = float(caption)

    await bot.send_photo(
        ADMIN_ID,
        msg.photo[-1].file_id,
        caption=f"طلب شحن\nID: {msg.from_user.id}\nAmount: {amount}"
    )

    await msg.answer("⏳ تم إرسال طلبك للأدمن")

# ========= ADMIN CONFIRM =========
@dp.message(F.text.startswith("/add"))
async def admin_add(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return

    try:
        _, user_id, amount = msg.text.split()
        add_balance(int(user_id), float(amount))
        await msg.answer("✅ تم الشحن")
    except:
        await msg.answer("❌ صيغة غلط")

# ========= NEW ORDER =========
user_state = {}

@dp.callback_query(F.data == "new")
async def new_order(call: types.CallbackQuery):
    services = get_telegram_services()

    buttons = []
    for s in services[:10]:
        buttons.append([
            InlineKeyboardButton(
                text=f"{s['name']} | {s['rate']}$",
                callback_data=f"service_{s['service']}"
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.answer("اختار الخدمة 👇", reply_markup=kb)

# ========= SELECT SERVICE =========
@dp.callback_query(F.data.startswith("service_"))
async def select_service(call: types.CallbackQuery):
    service_id = int(call.data.split("_")[1])
    user_state[call.from_user.id] = {"service": service_id}

    await call.message.answer("🔗 ابعت اللينك")

# ========= FLOW =========
@dp.message()
async def handle(msg: types.Message):
    user_id = msg.from_user.id

    if user_id not in user_state:
        return

    data = user_state[user_id]

    # أول خطوة: اللينك
    if "link" not in data:
        data["link"] = msg.text
        await msg.answer("📊 ابعت الكمية")
        return

    # التحقق من الكمية
    if "quantity" not in data:
        try:
            quantity = int(msg.text)  # يحاول يحول النص لرقم
            if quantity <= 0:
                raise ValueError  # لو الرقم صفر أو أقل، نعتبره خطأ
            data["quantity"] = quantity
        except ValueError:
            await msg.answer("❌ من فضلك اكتب الرقم بشكل صحيح")
            return  # يرجع للمستخدم لحد ما يكتب رقم صحيح

        # لو الرقم صح، يكمل
        services = get_telegram_services()
        service = next((s for s in services if s["service"] == data["service"]), None)

        price = calc_price(service["rate"], quantity)

        if not deduct_balance(user_id, price):
            await msg.answer("❌ رصيدك مش كفاية")
            user_state.pop(user_id)
            return

        res = create_order(data["service"], data["link"], quantity)

        if "order" in res:
            order_id = res["order"]

            cur.execute("""
                INSERT INTO orders (user_id, service_id, link, quantity, order_id, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, data["service"], data["link"], quantity, order_id, "Pending"))
            conn.commit()

            await msg.answer(
                f"✅ تم الطلب\n\n"
                f"📦 ID: {order_id}\n"
                f"💰 السعر: {price}$"
            )
        else:
            await msg.answer("❌ فشل الطلب")

        user_state.pop(user_id)

# ========= ORDERS =========
@dp.callback_query(F.data == "orders")
async def orders(call: types.CallbackQuery):
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
