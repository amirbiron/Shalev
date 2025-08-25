"""
Bot Configuration - Stock Tracker Bot 2025
Configuration management for Telegram bot deployment on Render
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
env_path = Path('.') / '.env'
if env_path.exists():
    load_dotenv(env_path)

@dataclass
class BotConfig:
    """Main bot configuration"""
    # Telegram Bot Settings
    TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN', '')
    WEBHOOK_URL: str = os.getenv('WEBHOOK_URL', '')
    WEBHOOK_PORT: int = int(os.getenv('PORT', '10000'))  # Render default port
    
    # Database Configuration  
    MONGODB_URI: str = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    DB_NAME: str = os.getenv('DB_NAME', 'stock_tracker_bot')
    
    # Scraping Settings
    SCRAPER_TIMEOUT: int = int(os.getenv('SCRAPER_TIMEOUT', '30'))
    MAX_CONCURRENT_REQUESTS: int = int(os.getenv('MAX_CONCURRENT_REQUESTS', '10'))
    USER_AGENT: str = os.getenv('USER_AGENT', 'StockTracker Bot/1.0')
    
    # Scheduling Configuration
    DEFAULT_CHECK_INTERVAL: int = int(os.getenv('DEFAULT_CHECK_INTERVAL', '60'))  # minutes
    MIN_CHECK_INTERVAL: int = int(os.getenv('MIN_CHECK_INTERVAL', '10'))  # minutes
    MAX_CHECK_INTERVAL: int = int(os.getenv('MAX_CHECK_INTERVAL', '1440'))  # 24 hours
    
    # Rate Limiting
    RATE_LIMIT_PER_USER: int = int(os.getenv('RATE_LIMIT_PER_USER', '50'))  # requests per day
    RATE_LIMIT_WINDOW: int = int(os.getenv('RATE_LIMIT_WINDOW', '86400'))  # seconds
    
    # Environment
    ENVIRONMENT: str = os.getenv('ENVIRONMENT', 'development')
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Runtime toggles
    FORCE_POLLING: bool = os.getenv('FORCE_POLLING', 'False').lower() == 'true'
    
    # Logging
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        if not self.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN is required")
        
        # In production, WEBHOOK_URL is required unless FORCE_POLLING is enabled
        if self.ENVIRONMENT == 'production' and not self.WEBHOOK_URL and not self.FORCE_POLLING:
            raise ValueError("WEBHOOK_URL is required in production (unless FORCE_POLLING=true)")

# Supported clubs/stores configuration
SUPPORTED_CLUBS: Dict[str, Dict[str, str]] = {
    'mashkar': {
        'name': 'משקארד',
        'base_url': 'https://www.mashkarcard.co.il',
        'domains': ['meshekard.co.il', 'mashkarcard.co.il'],
        'stock_selector': '.product-stock-status',
        'out_of_stock_indicators': ['אזל מהמלאי', 'לא זמין'],
        'requires_js': False,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (compatible; StockTracker/1.0)',
            # Avoid brotli to prevent decode issues with some environments
            'Accept-Encoding': 'gzip, deflate'
        }
    },
    'hot': {
        'name': 'מועדון הוט',
        'base_url': 'https://www.hot.net.il',
        'stock_selector': '.availability-status',
        'out_of_stock_indicators': ['אזל', 'לא זמין'],
        'requires_js': False
    },
    'corporate': {
        'name': 'Corporate',
        'base_url': 'https://www.corporate.co.il',
        'domains': ['mycorporate.co.il'],
        'stock_selector': '.stock-status',
        'out_of_stock_indicators': ['אזל מהמלאי', 'Out of Stock'],
        'requires_js': True
    },
    'living': {
        'name': 'Living',
        'base_url': 'https://www.living.co.il',
        'domains': ['living.co.il', 'www.living.co.il', 'livingclub.co.il', 'www.livingclub.co.il'],
        'stock_selector': '.product-availability',
        'out_of_stock_indicators': ['אזל', 'לא זמין', 'זמנית לא זמין'],
        'requires_js': False
    },
    'behazdaa': {
        'name': 'בהצדעה',
        'base_url': 'https://www.behazdaa.co.il',
        'stock_selector': '.availability',
        'out_of_stock_indicators': ['אזל מהמלאי'],
        'requires_js': True
    },
    'buff': {
        'name': 'Buff',
        'base_url': 'https://www.buff.co.il',
        'stock_selector': '.stock-info',
        'out_of_stock_indicators': ['אזל', 'Out of Stock'],
        'requires_js': True
    },
    'bttru': {
        'name': 'Bttru',
        'base_url': 'https://www.bttru.co.il',
        'stock_selector': '.product-stock',
        'out_of_stock_indicators': ['אזל מהמלאי', 'לא זמין'],
        'requires_js': False
    },
    'haver': {
        'name': 'חבר',
        'base_url': 'https://www.haver.co.il',
        'stock_selector': '.availability-status',
        'out_of_stock_indicators': ['אזל', 'זמנית לא זמין'],
        'requires_js': True
    },
    'ashmurat': {
        'name': 'אשמורת',
        'base_url': 'https://www.ashmurat.co.il',
        'stock_selector': '.stock-status',
        'out_of_stock_indicators': ['אזל מהמלאי', 'לא זמין'],
        'requires_js': False
    },
    'teachers': {
        'name': 'ארגון המורים',
        'base_url': 'https://shop.itu.org.il',
        'stock_selector': '.product-availability',
        'out_of_stock_indicators': ['אזל', 'לא זמין במלאי'],
        'requires_js': True
    },
    'intel': {
        'name': 'אינטל',
        'base_url': 'https://intel-shop.co.il',
        'stock_selector': '.availability',
        'out_of_stock_indicators': ['אזל מהמלאי', 'Out of Stock'],
        'requires_js': False
    },
    'shufersal4u': {
        'name': 'שופרסל 4U',
        'base_url': 'https://www.shufersal4u.co.il',
        'stock_selector': '.product-availability',
        'out_of_stock_indicators': ['אזל', 'לא זמין', 'זמנית לא זמין'],
        'requires_js': True
    }
}

# Bot messages and interface
BOT_MESSAGES: Dict[str, str] = {
    'welcome': '''🤖 ברוכים הבאים לבוט מעקב המלאי!

אני יכול לעזור לכם לקבל התראות כאשר מוצרים חוזרים למלאי במועדוני הקניות השונים.

מועדונים נתמכים:
• משקארד • מועדון הוט • Corporate • Living
• בהצדעה • Buff • Bttru • חבר
• אשמורת • ארגון המורים • אינטל

השתמשו בכפתורים למטה או שלחו קישור למוצר שתרצו לעקוב אחריו.''',
    
    'help': '''📖 עזרה - איך להשתמש בבוט:

🔗 **הוספת מעקב:**
שלחו קישור למוצר מאחד המועדונים הנתמכים

📜 **ניהול מעקבים:**
• "הרשימה שלי" - צפיה בכל המעקבים
• הפסקת מעקב - לחיצה על כפתור במסר ההתראה

⏰ **תדירות בדיקה:**
• כל 10-60 דקות (ברירת מחדל: כל שעה)
• ניתן לשנות לכל מוצר בנפרד

🔔 **התראות:**
תקבלו הודעה מיד כשהמוצר חוזר למלאי!''',
    
    'invalid_url': '❌ הקישור לא תקין או לא נתמך. אנא בדקו שהקישור מאחד המועדונים הנתמכים.',
    'already_tracking': '✅ כבר עוקבים אחרי המוצר הזה!',
    'tracking_added': '🎉 נוסף מעקב חדש! אקבל התראה כשהמוצר יחזור למלאי.',
    'no_trackings': '📭 אין לכם מעקבים פעילים כרגע.\nשלחו קישור למוצר כדי להתחיל לעקוב.',
    'back_in_stock': '🚨 **המוצר חזר למלאי!**\n\n📦 {product_name}\n🏪 {store_name}\n🔗 [לחצו כאן לרכישה]({product_url})',
    'error_occurred': '❌ אירעה שגיאה. אנא נסו שוב מאוחר יותר.',
    'rate_limit_exceeded': '⏰ חרגתם ממגבלת הבקשות היומית. נסו שוב מחר.'
}

# Bot keyboard layouts
KEYBOARD_LAYOUTS: Dict[str, List[List[str]]] = {
    'main': [
        ['➕ הוסף מעקב', '📜 הרשימה שלי'],
        ['❓ עזרה', '⚙️ הגדרות']
    ],
    'settings': [
        ['🔔 הגדרות התראות', '⏰ תדירות בדיקה'],
        ['🔙 חזרה לתפריט הראשי']
    ],
    'frequency': [
        ['⏱ כל 10 דקות', '🕐 כל שעה'],
        ['🕒 כל 3 שעות', '🕕 כל 6 שעות'],
        ['🔙 חזרה']
    ]
}

# Initialize configuration
config = BotConfig()

# Export for easy importing
__all__ = ['config', 'SUPPORTED_CLUBS', 'BOT_MESSAGES', 'KEYBOARD_LAYOUTS']
