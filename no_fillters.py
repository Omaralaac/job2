import requests
from bs4 import BeautifulSoup
import time
import json
import os

# ==============================
# 🔑 بيانات البوت
# ==============================
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    print("❌ TOKEN or CHAT_ID not found!")
    exit(1)

# ==============================
# 📁 ملف حفظ المشاريع
# ==============================
SEEN_FILE = "seen.json"

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

seen = load_seen()

# ==============================
# 🆕 أول تشغيل (تجاهل القديم)
# ==============================
FIRST_RUN_FILE = "first_run_done.txt"

def is_first_run():
    return not os.path.exists(FIRST_RUN_FILE)

def mark_first_run_done():
    with open(FIRST_RUN_FILE, "w") as f:
        f.write("done")

# ==============================
# 📲 إرسال Telegram
# ==============================
def send_telegram(project):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

        message = f"""🔥 *مشروع جديد*

🌐 *الموقع:* {project['site']}
📌 *العنوان:* {project['title']}
💰 *الميزانية:* {project['budget']}
⏳ *المدة:* {project['duration']}
"""

        data = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "reply_markup": json.dumps({
                "inline_keyboard": [
                    [
                        {
                            "text": "🔎 فتح المشروع",
                            "url": project['link']
                        }
                    ]
                ]
            })
        }

        requests.post(url, data=data)

    except Exception as e:
        print("Telegram Error:", e)

# ==============================
# 🟢 Mostaql
# ==============================
def get_mostaql():
    url = "https://mostaql.com/projects"
    headers = {"User-Agent": "Mozilla/5.0"}

    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    projects = []

    for c in soup.select("h2 a"):
        title = c.text.strip()
        href = c["href"]
        link = href if href.startswith("http") else "https://mostaql.com" + href

        # تفاصيل
        try:
            page = requests.get(link, headers=headers)
            psoup = BeautifulSoup(page.text, "html.parser")

            budget_span = psoup.select_one('div.meta-row:has(div.meta-label:contains("الميزانية")) span')
            budget = budget_span.text.strip() if budget_span else "غير محدد"

            duration_div = psoup.select_one('div.meta-row:has(div.meta-label:contains("مدة التنفيذ")) div.meta-value')
            duration = duration_div.text.strip() if duration_div else "غير محدد"
        except:
            budget = "غير محدد"
            duration = "غير محدد"

        projects.append({
            "site": "Mostaql",
            "title": title,
            "link": link,
            "budget": budget,
            "duration": duration
        })

    return projects

# ==============================
# 🟡 Khamsat
# ==============================
def get_khamsat():
    url = "https://khamsat.com/community/requests"
    headers = {"User-Agent": "Mozilla/5.0"}

    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    projects = []

    for c in soup.select("h3 a"):
        title = c.text.strip()
        link = "https://khamsat.com" + c["href"]

        projects.append({
            "site": "Khamsat",
            "title": title,
            "link": link,
            "budget": "غير محدد",
            "duration": "غير محدد"
        })

    return projects

# ==============================
# 🔵 Baaeed
# ==============================
def get_baaeed():
    url = "https://baaeed.com/jobs"
    headers = {"User-Agent": "Mozilla/5.0"}

    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    jobs = []

    for c in soup.select("h2 a"):
        title = c.text.strip()
        link = "https://baaeed.com" + c["href"]

        jobs.append({
            "site": "Baaeed",
            "title": title,
            "link": link,
            "budget": "غير محدد",
            "duration": "غير محدد"
        })

    return jobs

# ==============================
# 🟣 Guru
# ==============================
def get_guru():
    url = "https://www.guru.com/work/online"
    headers = {"User-Agent": "Mozilla/5.0"}

    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    projects = []

    for job in soup.select("li div.record.jobRecord"):
        # العنوان
        a_tag = job.select_one("h2.jobRecord__title a")
        if not a_tag:
            continue
        title = a_tag.text.strip()
        href = a_tag["href"].split("&")[0]  # تنظيف الرابط
        link = "https://www.guru.com" + href

        # الميزانية
        budget_div = job.select_one("div.jobRecord__budget")
        budget = budget_div.get_text(separator=" | ").strip() if budget_div else "غير محدد"

        # المدة / الموعد النهائي
        deadline_p = job.select_one("p.copy.small.grey")
        duration = deadline_p.get_text(strip=True) if deadline_p else "غير محدد"

        projects.append({
            "site": "Guru",
            "title": title,
            "link": link,
            "budget": budget,
            "duration": duration
        })

    return projects

# ==============================
# 🌐 كل المواقع
# ==============================
SITES = [get_mostaql, get_khamsat, get_baaeed, get_guru]

# ==============================
# 🔁 تشغيل البوت
# ==============================
print("🚀 Bot is running (Multi Sites)...")

while True:
    all_projects = []

    for site_func in SITES:
        try:
            all_projects.extend(site_func())
        except Exception as e:
            print("Site Error:", e)

    # أول تشغيل: خزّن كل المشاريع بدون إرسال
    if is_first_run():
        print("⚡ First run: saving existing projects only...")
        for p in all_projects:
            seen.add(p["link"])
        save_seen(seen)
        mark_first_run_done()
        print("✅ Done. Restarting loop...")
        time.sleep(10)
        continue

    # التشغيل الطبيعي
    for p in all_projects:
        if p["link"] not in seen:
            seen.add(p["link"])
            save_seen(seen)
            send_telegram(p)
            time.sleep(3)

    time.sleep(180)
