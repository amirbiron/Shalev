# 🤖 Stock Tracker Telegram Bot

<div align="center">

[![Deploy](https://github.com/your-username/stock-tracker-bot/workflows/🚀%20Deploy%20Stock%20Tracker%20Bot/badge.svg)](https://github.com/your-username/stock-tracker-bot/actions)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11%2B-brightgreen)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot%20API-blue.svg)](https://core.telegram.org/bots/api)

**בוט טלגרם מתקדם למעקב אחר זמינות מוצרים במועדוני הקניות הישראליים**

[English](#english) | [עברית](#hebrew)

</div>

---

## 🇮🇱 עברית {#hebrew}

### 📋 תוכן עניינים

- [תיאור הפרויקט](#תיאור-הפרויקט)
- [מועדונים נתמכים](#מועדונים-נתמכים)
- [תכונות עיקריות](#תכונות-עיקריות)
- [התקנה מקומית](#התקנה-מקומית)
- [פריסה לענן](#פריסה-לענן)
- [שימוש בבוט](#שימוש-בבוט)
- [הגדרות מתקדמות](#הגדרות-מתקדמות)
- [פיתוח ותרומה](#פיתוח-ותרומה)

### 🎯 תיאור הפרויקט

בוט טלגרם חכם שעוקב אחר זמינות מוצרים במועדוני הקניות הישראליים ושולח התראות ברגע שמוצר חוזר למלאי. הבוט בנוי עם טכנולוגיות מתקדמות של 2025 ומותאם לפריסה בענן.

**🔥 חדש ב-2025:**
- שימוש ב-**UV Package Manager** למהירות מקסימלית
- **Ruff Linter** כתוב ב-Rust לביצועים מעולים  
- **PyMongo 4.14** עם תמיכה מלאה ב-MongoDB 8.0
- **python-telegram-bot 22.3** עם כל התכונות החדשות
- **Playwright 1.46** לסקרייפינג אתרים דינמיים

### 🏪 מועדונים נתמכים

- 💳 **משקארד** - משקארד
- 📱 **מועדון הוט** - Hot Mobile
- 🏢 **Corporate** - קורפורייט
- 🏠 **Living** - ליווינג
- 🎖️ **בהצדעה** - צה"ל ומשטרה
- 💪 **Buff** - חברת באפ
- 🛍️ **Bttru** - בטרו
- 👥 **חבר** - מועדון חבר
- 🏛️ **אשמורת** - מועדון אשמורת
- 👨‍🏫 **ארגון המורים** - מועדון מורים
- 💻 **אינטל** - מועדון אינטל

### ⭐ תכונות עיקריות

#### 🚀 יכולות בסיסיות
- ✅ **מעקב אוטומטי** - הוספת מוצרים למעקב בשליחת קישור
- 🔔 **התראות מיידיות** - הודעה ברגע שמוצר חוזר למלאי
- ⏰ **תדירות מותאמת** - בחירת תדירות בדיקה לכל מוצר
- 📊 **ניהול מעקבים** - צפיה, השהיה והסרה של מעקבים

#### 🔧 תכונות מתקדמות  
- 🤖 **ממשק עברית מלא** - כפתורים וההודעות בעברית
- 🔄 **בדיקות אסינכרוניות** - עבודה מהירה ויעילה
- 🛡️ **Rate Limiting** - מניעת שימוש לרעה
- 📈 **מעקב סטטיסטיקות** - נתונים על השימוש
- 🏥 **Health Checks** - בדיקות תקינות אוטומטיות

#### 🕷️ טכנולוגיות סקרייפינג
- 🎭 **Playwright** - לאתרים עם JavaScript
- 🌐 **HTTP Requests** - לאתרים סטטיים  
- 🔍 **BeautifulSoup** - ניתוח HTML מתקדם
- ⚡ **Batch Processing** - עיבוד מקביל מהיר

### 🚀 התקנה מקומית

#### דרישות מערכת

- **Python 3.11+** (מומלץ 3.12 או 3.13)
- **MongoDB** (מקומי או Atlas)
- **Git**
- **UV Package Manager** (אופציונלי אבל מומלץ)

#### 1. הורדת הפרויקט

```bash
# שכפול הפרויקט
git clone https://github.com/your-username/stock-tracker-bot.git
cd stock-tracker-bot
```

#### 2. הגדרת סביבה וירטואלית

```bash
# עם UV (מהיר יותר)
uv venv .venv
source .venv/bin/activate  # Linux/Mac
# או
.venv\Scripts\activate     # Windows

# עם Python רגיל
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# או  
.venv\Scripts\activate     # Windows
```

#### 3. התקנת תלויות

```bash
# עם UV (מהיר מאוד!)
uv pip install -r requirements.txt

# עם pip רגיל
pip install -r requirements.txt
```

#### 4. התקנת Playwright

```bash
# התקנת דפדפנים לסקרייפינג
playwright install chromium
```

#### 5. הגדרת משתני סביבה

```bash
# העתקת קובץ הדוגמה
cp .env.example .env

# עריכת הקובץ עם הנתונים שלכם
nano .env  # או עורך טקסט אחר
```

**הגדרות חובה ב-.env:**
```bash
TELEGRAM_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz  # מ-@BotFather
MONGODB_URI=mongodb://localhost:27017/                    # MongoDB
DB_NAME=stock_tracker_bot
ENVIRONMENT=development
```

#### 6. הפעלת המערכת

```bash
# הפעלת הבוט
python main.py
```

**הבוט אמור להיות זמין ב-** `http://localhost:10000` 🎉

### ☁️ פריסה לענן

#### 🌐 Render.com (מומלץ)

1. **Fork הפרויקט** ב-GitHub
2. **צור חשבון** ב-[Render.com](https://render.com)
3. **צור Web Service חדש** וחבר לrepository
4. **Render יזהה אוטומטית** את `render.yaml`
5. **הגדר משתני סביבה:**
   - `TELEGRAM_TOKEN` - מ-@BotFather
   - `MONGODB_URI` - מ-MongoDB Atlas
   - השאר יוגדרו אוטומטית

#### 🗄️ MongoDB Atlas

1. **צור חשבון חינמי** ב-[MongoDB Atlas](https://cloud.mongodb.com)
2. **צור Cluster חדש** (M0 - חינמי)
3. **הוסף משתמש** עם הרשאות קריאה/כתיבה
4. **הגדר IP Access List** - הוסף `0.0.0.0/0` לפיתוח
5. **קבל את ה-Connection String**

#### 🤖 יצירת בוט טלגרם

1. **פנה ל-@BotFather** בטלגרם
2. **שלח:** `/newbot`
3. **בחר שם ויוזרניים** לבוט
4. **שמור את הTOKEN** שתקבל
5. **הגדר commands:** `/setcommands`

```
start - התחל לעבוד עם הבוט
help - עזרה ומדריך שימוש  
mystocks - הצג את המעקבים שלי
stats - סטטיסטיקות הבוט
```

### 🎮 שימוש בבוט

#### הוספת מעקב חדש

1. **שלח קישור למוצר** או לחץ "➕ הוסף מעקב"
2. **הבוט יבדק** את פרטי המוצר
3. **בחר תדירות בדיקה** (10 דקות - 24 שעות)
4. **קבל התראות** כשהמוצר חוזר למלאי!

#### ניהול מעקבים

- **📜 הרשימה שלי** - צפיה בכל המעקבים
- **⏸ השהה מעקב** - עצירה זמנית
- **▶️ חידוש מעקב** - המשכת בדיקות
- **🗑 הסרת מעקב** - מחיקה סופית

#### פקודות נוספות

- `/help` - מדריך שימוש מלא
- `/stats` - סטטיסטיקות ומידע על הבוט
- `/mystocks` - רשימת המעקבים שלכם

### ⚙️ הגדרות מתקדמות

#### 🔧 קובץ config.py

```python
# תדירות בדיקה כללית (דקות)
DEFAULT_CHECK_INTERVAL = 60

# מגבלות בקשות למשתמש  
RATE_LIMIT_PER_USER = 50
RATE_LIMIT_WINDOW = 86400  # 24 שעות

# הגדרות סקרייפינג
SCRAPER_TIMEOUT = 30
MAX_CONCURRENT_REQUESTS = 10
```

#### 🏪 הוספת מועדון חדש

ב-`config.py`, הוסף ל-`SUPPORTED_CLUBS`:

```python
'new_club': {
    'name': 'מועדון חדש',
    'base_url': 'https://newclub.co.il',
    'stock_selector': '.stock-status',  # CSS selector
    'out_of_stock_indicators': ['אזל', 'לא זמין'],
    'requires_js': False,  # True אם צריך Playwright
    'headers': {'User-Agent': 'Custom Bot'}
}
```

### 🔄 GitHub Actions CI/CD

הפרויקט כולל pipeline מתקדם עם:

- ✅ **Quality Checks** - Black, Ruff, MyPy
- 🛡️ **Security Scans** - Bandit, Safety, Trivy
- 🧪 **Testing Matrix** - Ubuntu/Windows/macOS
- 🚀 **Auto Deploy** - Staging + Production
- 📊 **Monitoring** - Health checks ו-notifications

**הפעלה:**
1. Push ל-`main` → Deploy לProduction
2. Push ל-`develop` → Deploy לStaging  
3. Pull Request → רק testing

### 📊 מעקב וניטור

#### Health Endpoints

- `GET /` - Basic health check
- `GET /health` - Detailed health status
- `GET /stats` - Bot usage statistics

#### Logs

```bash
# צפיה ב-logs ב-Render
render logs -f your-service-name

# Logs מקומיים
tail -f app.log
```

### 🧪 פיתוח ותרומה

#### הרצת בדיקות

```bash
# התקנת dependencies לפיתוח
uv pip install pytest pytest-asyncio pytest-cov pytest-mock

# הרצת כל הבדיקות  
pytest

# בדיקות עם coverage
pytest --cov=. --cov-report=html
```

#### Code Quality

```bash
# התקנת כלים
uv pip install black ruff mypy bandit

# Format code
black .

# Lint
ruff check .

# Type checking  
mypy .

# Security scan
bandit -r .
```

#### מבנה הפרויקט

```
stock-tracker-bot/
├── main.py              # Entry point
├── bot.py               # Bot logic  
├── config.py            # Configuration
├── database.py          # MongoDB operations
├── scrapers.py          # Web scraping
├── requirements.txt     # Dependencies
├── render.yaml          # Render deployment
├── .env.example         # Environment template
├── .github/workflows/   # CI/CD pipeline
├── tests/               # Unit tests
└── docs/                # Documentation
```

### 🐛 פתרון בעיות נפוצות

#### בוט לא מגיב

```bash
# בדוק שהTOKEN נכון
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe

# בדוק logs
tail -f app.log
```

#### שגיאות MongoDB

```bash
# בדוק חיבור
python -c "from database import DatabaseManager; import asyncio; asyncio.run(DatabaseManager().connect())"
```

#### סקרייפינג לא עובד

```bash
# בדוק Playwright
playwright install chromium

# בדוק חיבור לאתר
curl -I https://www.mashkarcard.co.il
```

### 📄 רישיון

פרויקט זה מפורסם תחת [רישיון MIT](LICENSE).

### 🤝 תמיכה ועזרה

- 🐛 **באגים:** [GitHub Issues](https://github.com/your-username/stock-tracker-bot/issues)
- 💡 **רעיונות:** [GitHub Discussions](https://github.com/your-username/stock-tracker-bot/discussions)  
- 📧 **יצירת קשר:** your-email@example.com

---

## 🇺🇸 English {#english}

### 🎯 Project Description

An advanced Telegram bot for tracking product availability in Israeli shopping clubs with instant notifications when items return to stock. Built with cutting-edge 2025 technologies and optimized for cloud deployment.

### 🏪 Supported Stores

- Mashkar Card, Hot Club, Corporate, Living, BeHatza'a
- Buff, Bttru, Haver, Ashmurat, Teachers Organization, Intel

### ⭐ Key Features

- **Automatic Tracking** - Add products by sending URL
- **Instant Notifications** - Get alerts when back in stock  
- **Custom Frequency** - Choose check intervals per product
- **Hebrew Interface** - Full Hebrew UI and messages
- **Advanced Scraping** - Playwright + BeautifulSoup + HTTP
- **Cloud Ready** - Optimized for Render deployment

### 🚀 Quick Start

1. **Clone repository**
2. **Install dependencies:** `uv pip install -r requirements.txt`
3. **Setup environment:** Copy `.env.example` to `.env`
4. **Configure bot token and MongoDB**
5. **Run:** `python main.py`

### 🌐 Deploy to Render

1. Fork this repository
2. Connect to Render.com
3. Set environment variables:
   - `TELEGRAM_TOKEN`
   - `MONGODB_URI`
4. Deploy automatically with `render.yaml`

### 📊 Tech Stack

- **Python 3.12+** with asyncio
- **python-telegram-bot 22.3** (Bot API 9.1)
- **PyMongo 4.14** (MongoDB 8.0)
- **Playwright 1.46** + BeautifulSoup
- **FastAPI** + Uvicorn
- **APScheduler** for background jobs

### 🧪 Testing & CI/CD

- **GitHub Actions** with UV and Ruff
- **Matrix testing** (Ubuntu/Windows/macOS)
- **Security scans** (Bandit, Safety, Trivy)
- **Auto deploy** to staging/production

---

<div align="center">

**⭐ אם הפרויקט עזר לכם, אשמח לכוכב ב-GitHub! ⭐**

Made with ❤️ in Israel 🇮🇱

</div>
