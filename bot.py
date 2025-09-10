"""
Stock Tracker Telegram Bot - Main Bot Logic
Using python-telegram-bot 22.3 with 2025 best practices
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

# Telegram Bot API 22.3
from telegram import (
    Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from telegram.error import TelegramError, Forbidden, BadRequest

# Async Task Scheduling
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

# Local imports
from config import config, SUPPORTED_CLUBS, BOT_MESSAGES, KEYBOARD_LAYOUTS
from database import DatabaseManager, ProductTracking, TrackingStatus, UserProfile, StockAlert
from scrapers import StockScraper

logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_URL, WAITING_FOR_OPTION, SETTING_FREQUENCY = range(3)

class StockTrackerBot:
    """Main bot class handling all Telegram interactions"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.scraper = StockScraper()
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.bot: Optional[Bot] = None
        
        # Rate limiting cache
        self.rate_limit_cache: Dict[int, List[datetime]] = {}
        
    async def start_scheduler(self):
        """Start the background scheduler for stock checks"""
        try:
            jobstores = {'default': MemoryJobStore()}
            executors = {'default': AsyncIOExecutor()}
            job_defaults = {
                'coalesce': False,
                'max_instances': 3,
                'misfire_grace_time': 30
            }
            
            self.scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults
            )
            
            # Add recurring job to check stocks
            self.scheduler.add_job(
                self._check_all_stocks,
                'interval',
                minutes=config.DEFAULT_CHECK_INTERVAL,
                id='stock_checker',
                replace_existing=True
            )
            
            # Add cleanup job for old data
            self.scheduler.add_job(
                self._cleanup_old_data,
                'interval',
                hours=24,
                id='data_cleanup',
                replace_existing=True
            )
            
            self.scheduler.start()
            logger.info("⏰ Scheduler started successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to start scheduler: {e}")
            raise
    
    async def stop_scheduler(self):
        """Stop the scheduler"""
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("⏰ Scheduler stopped")
    
    def setup_handlers(self, application: Application):
        """Setup all bot command and message handlers"""
        self.bot = application.bot
        
        # Command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("mystocks", self.my_stocks_command))
        application.add_handler(CommandHandler("stats", self.stats_command))
        
        # Conversation handler for adding stock tracking
        conv_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex(r"^➕ הוסף מעקב$"), self.add_tracking_start),
                MessageHandler(filters.Regex(r"^https?://"), self.handle_url_message)
            ],
            states={
                WAITING_FOR_URL: [
                    MessageHandler(filters.Regex(r"^(?:🔙\s*)?חזרה$"), self.cancel_conversation),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url_input)
                ],
                WAITING_FOR_OPTION: [
                    CallbackQueryHandler(self.handle_option_selection, pattern=r"^opt_")
                ],
                SETTING_FREQUENCY: [
                    CallbackQueryHandler(self.handle_frequency_selection, pattern=r"^freq_")
                ]
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel_conversation),
                MessageHandler(filters.Regex(r"^(?:🔙\s*)?חזרה$"), self.cancel_conversation)
            ]
        )
        application.add_handler(conv_handler)
        
        # Keyboard button handlers
        application.add_handler(MessageHandler(filters.Regex(r"^📜 הרשימה שלי$"), self.my_stocks_command))
        application.add_handler(MessageHandler(filters.Regex(r"^❓ עזרה$"), self.help_command))
        application.add_handler(MessageHandler(filters.Regex(r"^⚙️ הגדרות$"), self.settings_command))
        
        # Callback query handlers
        application.add_handler(CallbackQueryHandler(self.handle_remove_tracking, pattern=r"^remove_"))
        application.add_handler(CallbackQueryHandler(self.handle_pause_tracking, pattern=r"^pause_"))
        application.add_handler(CallbackQueryHandler(self.handle_resume_tracking, pattern=r"^resume_"))
        application.add_handler(CallbackQueryHandler(self.handle_rename_tracking, pattern=r"^rename_"))
        application.add_handler(CallbackQueryHandler(self.handle_settings, pattern=r"^settings_"))
        
        # Generic message handler (for URLs)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_generic_message))
        
        # Error handler
        application.add_error_handler(self.error_handler)
        
        logger.info("🎛️ Bot handlers configured successfully")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        try:
            user = update.effective_user
            await self.db.get_or_create_user(user.to_dict())
            
            # Create main keyboard
            keyboard = ReplyKeyboardMarkup(
                KEYBOARD_LAYOUTS['main'],
                resize_keyboard=True,
                one_time_keyboard=False
            )
            
            await update.message.reply_text(
                BOT_MESSAGES['welcome'],
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"❌ Error in start command: {e}")
            await update.message.reply_text(BOT_MESSAGES['error_occurred'])
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        try:
            await update.effective_message.reply_text(
                BOT_MESSAGES['help'],
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"❌ Error in help command: {e}")
    
    async def add_tracking_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the add tracking conversation"""
        try:
            if not await self._check_rate_limit(update.effective_user.id):
                await update.message.reply_text(BOT_MESSAGES['rate_limit_exceeded'])
                return ConversationHandler.END
            
            await update.message.reply_text(
                "🔗 אנא שלחו קישור למוצר שתרצו לעקוב אחריו:",
                reply_markup=ReplyKeyboardMarkup(
                    [['🔙 חזרה']],
                    resize_keyboard=True
                )
            )
            return WAITING_FOR_URL
            
        except Exception as e:
            logger.error(f"❌ Error starting tracking conversation: {e}")
            return ConversationHandler.END
    
    async def handle_url_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle direct URL message"""
        return await self.handle_url_input(update, context)
    
    async def handle_url_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process URL input and add tracking"""
        try:
            url = update.message.text.strip()
            user_id = update.effective_user.id
            
            # Validate URL
            store_info = self._validate_url(url)
            if not store_info:
                await update.message.reply_text(BOT_MESSAGES['invalid_url'])
                return WAITING_FOR_URL
            
            # Show loading indicator and get product info from scraper
            try:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            except Exception:
                pass
            loading_msg = None
            try:
                loading_msg = await update.message.reply_text("⏳ טוען...")
            except Exception:
                loading_msg = None
            product_info = await self.scraper.get_product_info(url, store_info['store_id'])
            if (
                not product_info or
                getattr(product_info, 'error_message', None) or
                product_info.name in {"שגיאה בטעינת המוצר", "שגיאת זמן קצוב", "שגיאה"}
            ):
                await update.message.reply_text(
                    "❌ לא הצלחתי לטעון את פרטי המוצר. נסו שוב מאוחר יותר או שלחו קישור מוצר ישיר."
                )
                return WAITING_FOR_URL
            
            # Get initial page hash for change detection
            initial_hash = getattr(product_info, 'page_hash', None)

            # Detect invalid/placeholder product name to trigger manual rename prompt later
            try:
                normalized_name = (product_info.name or '').strip().strip('"\'')
                invalid_product_name = (
                    not normalized_name or
                    len(normalized_name) < 3 or
                    normalized_name in {store_info['name'].strip(), 'משקארד', 'לא זמין'}
                )
            except Exception:
                invalid_product_name = False
            
            # Determine default check interval (user-specific if available)
            user_doc = await self.db.collections['users'].find_one({'user_id': user_id})
            default_interval = config.DEFAULT_CHECK_INTERVAL
            if user_doc:
                default_interval = int(user_doc.get('default_check_interval', default_interval))
                # Clamp to configured min/max
                default_interval = max(config.MIN_CHECK_INTERVAL, min(config.MAX_CHECK_INTERVAL, default_interval))

            # Derive stable product key for deduplication
            try:
                product_key = self.scraper.get_product_key(url, store_info['store_id'])
            except Exception:
                product_key = None

            # Check for existing tracking by URL or product_key
            or_conditions = [{'product_url': url}]
            if product_key:
                or_conditions.append({'product_key': product_key, 'store_id': store_info['store_id']})
            existing = await self.db.collections['trackings'].find_one({'user_id': user_id, '$or': or_conditions})

            if existing and existing.get('status') == 'error':
                # Revive ERROR tracking
                await self.db.collections['trackings'].update_one(
                    {'_id': existing['_id']},
                    {'$set': {
                        'status': 'active',
                        'error_count': 0,
                        'updated_at': datetime.utcnow(),
                        'product_name': product_info.name,
                        'notification_sent': False
                    }}
                )
                tracking_id = existing['_id']
            elif existing:
                existing_id = str(existing.get('_id'))
                existing_status = existing.get('status', 'active')
                status_map = {
                    'active': 'פעיל',
                    'paused': 'מושהה',
                    'in_stock': 'במלאי',
                    'out_of_stock': 'אזל',
                    'error': 'שגיאה'
                }
                keyboard_buttons = []
                if existing_status == 'paused':
                    keyboard_buttons.append([InlineKeyboardButton("▶️ חידוש מעקב", callback_data=f"resume_{existing_id}")])
                else:
                    keyboard_buttons.append([InlineKeyboardButton("⏸ השהה מעקב", callback_data=f"pause_{existing_id}")])
                keyboard_buttons.append([InlineKeyboardButton("🗑 הסר מעקב", callback_data=f"remove_{existing_id}")])

                await update.message.reply_text(
                    f"✅ כבר קיים מעקב למוצר הזה.\n\n"
                    f"📦 {existing.get('product_name', 'מוצר')}\n"
                    f"🏪 {existing.get('store_name', store_info['name'])}\n"
                    f"📊 סטטוס: {status_map.get(existing_status, existing_status)}",
                    reply_markup=InlineKeyboardMarkup(keyboard_buttons)
                )
                return ConversationHandler.END
            else:
                # If multiple purchase options exist, ask user to select which one to track
                try:
                    options = await self.scraper.get_purchase_options(url, store_info['store_id'])
                except Exception:
                    options = []
                if options:
                    # Keep context for next step
                    context.user_data['pending_track'] = {
                        'url': url,
                        'product_key': product_key,
                        'product_name': product_info.name,
                        'store_name': store_info['name'],
                        'store_id': store_info['store_id'],
                        'default_interval': default_interval
                    }
                    # Build options keyboard (top 8)
                    buttons: List[List[InlineKeyboardButton]] = []
                    for idx, opt in enumerate(options[:8]):
                        label = opt.get('label') or opt.get('price') or f"אפשרות {idx+1}"
                        key = opt.get('key') or re.sub(r"\s+", " ", label).strip().lower()
                        buttons.append([InlineKeyboardButton(label, callback_data=f"opt_{idx}_{key}")])
                    buttons.append([InlineKeyboardButton("דלג - עקוב אחרי כל האופציות", callback_data="opt_skip_all")])
                    if loading_msg:
                        try:
                            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_msg.message_id)
                        except Exception:
                            pass
                    await update.message.reply_text(
                        "🛒 נמצא יותר מאפשרות רכישה. בחרו את האופציה הספציפית שתרצו לעקוב אחריה:",
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                    return WAITING_FOR_OPTION
                else:
                    # Check if store requires change detection mode (like Shufersal)
                    store_config = SUPPORTED_CLUBS.get(store_info['store_id'], {})
                    tracking_mode = 'changes' if store_config.get('force_change_detection', False) else 'changes'
                    
                    # Create tracking object and insert
                    tracking = ProductTracking(
                        user_id=user_id,
                        product_url=url,
                        product_key=product_key,
                        product_name=product_info.name,
                        store_name=store_info['name'],
                        store_id=store_info['store_id'],
                        check_interval=default_interval,
                        status=TrackingStatus.ACTIVE,
                        tracking_mode=tracking_mode,  # Always use 'changes' mode now
                        last_page_hash=initial_hash
                    )
                    tracking_id = await self.db.add_tracking(tracking)
                    if not tracking_id:
                        await update.message.reply_text(BOT_MESSAGES['error_occurred'])
                        return ConversationHandler.END
            
            # Create frequency selection keyboard (add rename button only if name זוהה)
            keyboard_rows = [
                [
                    InlineKeyboardButton("⏱ כל 10 דקות", callback_data=f"freq_{tracking_id}_10"),
                    InlineKeyboardButton("🕐 כל שעה", callback_data=f"freq_{tracking_id}_60")
                ],
                [
                    InlineKeyboardButton("🕒 כל 3 שעות", callback_data=f"freq_{tracking_id}_180"),
                    InlineKeyboardButton("🕕 כל 6 שעות", callback_data=f"freq_{tracking_id}_360")
                ],
                [
                    InlineKeyboardButton("✅ השתמש בברירת מחדל (שעה)", callback_data=f"freq_{tracking_id}_60")
                ]
            ]
            if not invalid_product_name:
                keyboard_rows.append([InlineKeyboardButton("✍️ עדכן שם מוצר", callback_data=f"rename_{tracking_id}")])
            keyboard = InlineKeyboardMarkup(keyboard_rows)
            # Delete loading message
            try:
                if loading_msg:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_msg.message_id)
            except Exception:
                pass

            # Send message with a small retry for transient network errors
            await update.message.reply_text(
                f"🎉 נוסף מעקב חדש!\n\n"
                f"📦 **{product_info.name}**\n"
                f"🏪 {store_info['name']}\n"
                f"🔄 מעקב אחרי שינויים בעמוד\n\n"
                f"⏰ באיזו תדירות לבדוק?",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )

            # If name looks invalid, prompt user for a manual name and store the pending tracking id
            if invalid_product_name:
                try:
                    context.user_data['awaiting_rename_id'] = str(tracking_id)
                    await update.message.reply_text("✍️ שם המוצר לא זוהה. שלחו עכשיו את השם המדויק, ואני אעדכן אותו במעקב.")
                except Exception:
                    pass
            
            return SETTING_FREQUENCY
            
        except Exception as e:
            logger.error(f"❌ Error handling URL input: {e}")
            await update.message.reply_text(BOT_MESSAGES['error_occurred'])
            return ConversationHandler.END
    
    async def handle_frequency_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle frequency selection callback"""
        try:
            query = update.callback_query
            await query.answer()
            
            # Parse callback data
            parts = query.data.split('_')
            if len(parts) != 3 or parts[0] != 'freq':
                return ConversationHandler.END
            
            tracking_id = parts[1]
            frequency = int(parts[2])
            
            # Update tracking frequency
            from bson import ObjectId
            await self.db.collections['trackings'].update_one(
                {'_id': ObjectId(tracking_id)},
                {'$set': {'check_interval': frequency}}
            )
            
            # Create management keyboard
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⏸ השהה מעקב", callback_data=f"pause_{tracking_id}"),
                    InlineKeyboardButton("🗑 הסר מעקב", callback_data=f"remove_{tracking_id}")
                ]
            ])
            
            frequency_text = self._get_frequency_text(frequency)
            
            await query.edit_message_text(
                f"✅ המעקב הוגדר בהצלחה!\n\n"
                f"⏰ תדירות בדיקה: {frequency_text}\n"
                f"🔔 תקבלו התראה ברגע שהמוצר יחזור למלאי.",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Reset keyboard
            main_keyboard = ReplyKeyboardMarkup(
                KEYBOARD_LAYOUTS['main'],
                resize_keyboard=True
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🏠 חזרתם לתפריט הראשי",
                reply_markup=main_keyboard
            )
            
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"❌ Error in frequency selection: {e}")
            return ConversationHandler.END

    async def handle_option_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user selecting a specific purchase option/deal to track"""
        try:
            query = update.callback_query
            await query.answer()
            data = query.data or ""
            pending = context.user_data.get('pending_track') or {}
            if not pending:
                await query.edit_message_text("❌ פג תוקף הבחירה. נסו להוסיף את המעקב שוב.")
                return ConversationHandler.END

            user_id = update.effective_user.id
            url = pending['url']
            product_key = pending.get('product_key')
            product_name = pending.get('product_name')
            store_name = pending.get('store_name')
            store_id = pending.get('store_id')
            default_interval = pending.get('default_interval', config.DEFAULT_CHECK_INTERVAL)

            option_label: Optional[str] = None
            option_key: Optional[str] = None

            if data == 'opt_skip_all':
                pass
            else:
                try:
                    parts = data.split('_', 2)
                    if len(parts) >= 3:
                        option_key = parts[2]
                except Exception:
                    option_key = None
                try:
                    options = await self.scraper.get_purchase_options(url, store_id)
                except Exception:
                    options = []
                for opt in options:
                    label = opt.get('label') or opt.get('price')
                    key = opt.get('key') or (re.sub(r"\s+", " ", (label or '')).strip().lower())
                    if option_key and key == option_key:
                        option_label = label
                        break

            # Get initial page hash
            initial_info = await self.scraper.get_product_info(url, store_id)
            initial_hash = getattr(initial_info, 'page_hash', None) if initial_info else None
            
            tracking = ProductTracking(
                user_id=user_id,
                product_url=url,
                original_url=url,
                product_key=product_key,
                product_name=product_name,
                store_name=store_name,
                store_id=store_id,
                option_label=option_label,
                option_key=option_key,
                check_interval=default_interval,
                status=TrackingStatus.ACTIVE,
                tracking_mode='changes',
                last_page_hash=initial_hash
            )
            tracking_id = await self.db.add_tracking(tracking)
            if not tracking_id:
                await query.edit_message_text(BOT_MESSAGES['error_occurred'])
                return ConversationHandler.END

            keyboard_rows = [
                [
                    InlineKeyboardButton("⏱ כל 10 דקות", callback_data=f"freq_{tracking_id}_10"),
                    InlineKeyboardButton("🕐 כל שעה", callback_data=f"freq_{tracking_id}_60")
                ],
                [
                    InlineKeyboardButton("🕒 כל 3 שעות", callback_data=f"freq_{tracking_id}_180"),
                    InlineKeyboardButton("🕕 כל 6 שעות", callback_data=f"freq_{tracking_id}_360")
                ],
                [
                    InlineKeyboardButton("✅ השתמש בברירת מחדל (שעה)", callback_data=f"freq_{tracking_id}_60")
                ]
            ]
            keyboard = InlineKeyboardMarkup(keyboard_rows)

            suffix = f"\n🎯 אופציה: {option_label}" if option_label else ""
            await query.edit_message_text(
                f"🎉 נוסף מעקב חדש!{suffix}\n\n"
                f"📦 **{product_name}**\n"
                f"🏪 {store_name}\n"
                f"⏰ באיזו תדירות לבדוק?",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )

            context.user_data.pop('pending_track', None)
            return SETTING_FREQUENCY

        except Exception as e:
            logger.error(f"❌ Error handling option selection: {e}")
            try:
                await update.effective_message.reply_text(BOT_MESSAGES['error_occurred'])
            except Exception:
                pass
            return ConversationHandler.END
    
    async def my_stocks_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's tracked stocks"""
        try:
            user_id = update.effective_user.id
            trackings = await self.db.get_user_trackings(user_id)
            
            if not trackings:
                await update.effective_message.reply_text(BOT_MESSAGES['no_trackings'])
                return
            
            # Group by status
            active_trackings = [t for t in trackings if t.status == TrackingStatus.ACTIVE]
            paused_trackings = [t for t in trackings if t.status == TrackingStatus.PAUSED]
            
            message = "📜 **הרשימה שלכם:**\n\n"
            
            if active_trackings:
                message += "🟢 **פעילים:**\n"
                for i, tracking in enumerate(active_trackings[:10], 1):
                    # For change tracking mode, show different emoji
                    if getattr(tracking, 'tracking_mode', 'stock') == 'changes':
                        status_emoji = "🔄"  # Change tracking mode
                        change_count = getattr(tracking, 'change_count', 0)
                        if change_count > 0:
                            status_emoji = f"🔔({change_count})"  # Show number of changes detected
                    else:
                        # Legacy stock mode
                        status_emoji = "✅" if tracking.status == TrackingStatus.IN_STOCK else "❌"
                    
                    last_check = ""
                    if tracking.last_checked:
                        time_diff = datetime.utcnow() - tracking.last_checked
                        if time_diff.total_seconds() < 3600:
                            last_check = f" (נבדק לפני {int(time_diff.total_seconds() / 60)} דקות)"
                        else:
                            last_check = f" (נבדק לפני {int(time_diff.total_seconds() / 3600)} שעות)"
                    
                    opt = f" | 🎯 {tracking.option_label}" if getattr(tracking, 'option_label', None) else ""
                    message += f"{i}. {status_emoji} **{tracking.product_name[:30]}{'...' if len(tracking.product_name) > 30 else ''}**{opt}\n"
                    message += f"   🏪 {tracking.store_name} | ⏰ {self._get_frequency_text(tracking.check_interval)}{last_check}\n\n"
            
            if paused_trackings:
                message += "\n⏸ **מושהים:**\n"
                for tracking in paused_trackings[:5]:
                    opt = f" | 🎯 {tracking.option_label}" if getattr(tracking, 'option_label', None) else ""
                    message += f"• **{tracking.product_name[:30]}{'...' if len(tracking.product_name) > 30 else ''}**{opt}\n"
                    message += f"  🏪 {tracking.store_name}\n"
            
            # Create inline keyboard for management
            keyboard_buttons = []
            for i, tracking in enumerate(active_trackings[:5]):
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        f"⏸ השהה #{i+1}",
                        callback_data=f"pause_{tracking._id}"
                    ),
                    InlineKeyboardButton(
                        f"🗑 הסר #{i+1}",
                        callback_data=f"remove_{tracking._id}"
                    )
                ])
            
            if keyboard_buttons:
                keyboard = InlineKeyboardMarkup(keyboard_buttons)
            else:
                keyboard = None
            
            await update.effective_message.reply_text(
                message,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"❌ Error in my_stocks command: {e}")
            await update.effective_message.reply_text(BOT_MESSAGES['error_occurred'])
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show settings menu"""
        try:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 הגדרות התראות", callback_data="settings_notifications")],
                [InlineKeyboardButton("⏰ תדירות בדיקה כללית", callback_data="settings_frequency")],
                [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="settings_stats")]
            ])
            
            await update.effective_message.reply_text(
                "⚙️ **הגדרות הבוט**\n\nבחרו את ההגדרה שתרצו לשנות:",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"❌ Error in settings command: {e}")
    
    async def handle_remove_tracking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle remove tracking callback"""
        try:
            query = update.callback_query
            await query.answer()
            
            tracking_id = query.data.split('_')[1]
            from bson import ObjectId
            
            success = await self.db.remove_tracking(
                update.effective_user.id,
                ObjectId(tracking_id)
            )
            
            if success:
                await query.edit_message_text("✅ המעקב הוסר בהצלחה!")
            else:
                await query.answer("❌ שגיאה בהסרת המעקב", show_alert=True)
                
        except Exception as e:
            logger.error(f"❌ Error removing tracking: {e}")
    
    async def handle_pause_tracking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pause tracking callback"""
        try:
            query = update.callback_query
            await query.answer()
            
            tracking_id = query.data.split('_')[1]
            from bson import ObjectId
            
            await self.db.update_tracking_status(
                ObjectId(tracking_id),
                TrackingStatus.PAUSED
            )
            
            await query.edit_message_text("⏸ המעקב הושהה זמנית")
            
        except Exception as e:
            logger.error(f"❌ Error pausing tracking: {e}")
    
    async def handle_resume_tracking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle resume tracking callback"""
        try:
            query = update.callback_query
            await query.answer()
            
            tracking_id = query.data.split('_')[1]
            from bson import ObjectId
            
            await self.db.update_tracking_status(
                ObjectId(tracking_id),
                TrackingStatus.ACTIVE
            )
            
            await query.edit_message_text("▶️ המעקב חודש!")
            
        except Exception as e:
            logger.error(f"❌ Error resuming tracking: {e}")
    
    async def handle_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle settings callbacks"""
        try:
            query = update.callback_query
            await query.answer()
            
            parts = query.data.split('_')
            setting = parts[1] if len(parts) > 1 else ''
            
            # Helper: show main settings menu
            async def show_main_settings_menu():
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔔 הגדרות התראות", callback_data="settings_notifications")],
                    [InlineKeyboardButton("⏰ תדירות בדיקה כללית", callback_data="settings_frequency")],
                    [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="settings_stats")]
                ])
                await query.edit_message_text(
                    "⚙️ **הגדרות הבוט**\n\nבחרו את ההגדרה שתרצו לשנות:",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )

            if setting == "stats":
                stats = await self.db.get_bot_stats()
                message = f"""📊 **סטטיסטיקות הבוט**

👥 סה"כ משתמשים: {stats.get('total_users', 0)}
🟢 משתמשים פעילים (שבוע אחרון): {stats.get('active_users', 0)}
📦 סה"כ מעקבים: {stats.get('total_trackings', 0)}
⚡ מעקבים פעילים: {stats.get('active_trackings', 0)}

🏪 **חנויות פופולריות:**"""
                
                for store in stats.get('top_stores', [])[:5]:
                    message += f"\n• {store['_id']}: {store['count']} מעקבים"
                
                await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN)
            elif setting == "back":
                await show_main_settings_menu()
            elif setting == "notifications":
                # Toggle notifications submenu or apply toggle
                # patterns: settings_notifications, settings_notifications_on, settings_notifications_off
                action = parts[2] if len(parts) > 2 else None
                user_doc = await self.db.collections['users'].find_one({'user_id': update.effective_user.id})
                current_enabled = True if not user_doc else user_doc.get('notifications_enabled', True)
                
                if action in ("on", "off"):
                    new_value = True if action == "on" else False
                    await self.db.collections['users'].update_one(
                        {'user_id': update.effective_user.id},
                        {'$set': {'notifications_enabled': new_value, 'updated_at': datetime.utcnow()}},
                        upsert=True
                    )
                    status_text = "פעילות" if new_value else "כבויות"
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ חזרה", callback_data="settings_back")]
                    ])
                    await query.edit_message_text(
                        f"✅ התראות כעת {status_text} למשתמש זה.",
                        reply_markup=keyboard
                    )
                else:
                    # Show submenu with appropriate toggle option
                    if current_enabled:
                        toggle_button = InlineKeyboardButton("🔕 כבה התראות", callback_data="settings_notifications_off")
                    else:
                        toggle_button = InlineKeyboardButton("🔔 הפעל התראות", callback_data="settings_notifications_on")
                    keyboard = InlineKeyboardMarkup([
                        [toggle_button],
                        [InlineKeyboardButton("⬅️ חזרה", callback_data="settings_back")]
                    ])
                    status_text = "מופעלות" if current_enabled else "כבויות"
                    await query.edit_message_text(
                        f"🔔 הגדרות התראות\n\nמצב נוכחי: {status_text}",
                        reply_markup=keyboard
                    )
            elif setting == "frequency":
                # patterns: settings_frequency, settings_frequency_<minutes>
                if len(parts) == 3 and parts[2].isdigit():
                    minutes = int(parts[2])
                    minutes = max(config.MIN_CHECK_INTERVAL, min(config.MAX_CHECK_INTERVAL, minutes))
                    await self.db.collections['users'].update_one(
                        {'user_id': update.effective_user.id},
                        {'$set': {'default_check_interval': minutes, 'updated_at': datetime.utcnow()}},
                        upsert=True
                    )
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬅️ חזרה", callback_data="settings_back")]
                    ])
                    await query.edit_message_text(
                        f"✅ התדירות הכללית עודכנה ל-{self._get_frequency_text(minutes)}.",
                        reply_markup=keyboard
                    )
                else:
                    # Show frequency options submenu
                    keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("⏱ כל 10 דקות", callback_data="settings_frequency_10"),
                            InlineKeyboardButton("🕐 כל שעה", callback_data="settings_frequency_60")
                        ],
                        [
                            InlineKeyboardButton("🕒 כל 3 שעות", callback_data="settings_frequency_180"),
                            InlineKeyboardButton("🕕 כל 6 שעות", callback_data="settings_frequency_360")
                        ],
                        [InlineKeyboardButton("⬅️ חזרה", callback_data="settings_back")]
                    ])
                    await query.edit_message_text(
                        "⏰ תדירות בדיקה כללית\n\nבחרו את ברירת המחדל לבדיקה של מוצרים חדשים:",
                        reply_markup=keyboard
                    )
            else:
                # Unknown or main menu request: show menu again
                await show_main_settings_menu()
            
        except Exception as e:
            logger.error(f"❌ Error in settings handler: {e}")
    
    async def handle_generic_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle generic text messages (mainly URLs)"""
        try:
            text = update.message.text.strip()
            
            # Check if it's a URL
            if text.startswith(('http://', 'https://')):
                return await self.handle_url_input(update, context)
            else:
                # If awaiting manual rename, update the last tracking name
                pending_id = context.user_data.get('awaiting_rename_id')
                if pending_id:
                    from bson import ObjectId
                    new_name = text[:120].strip()
                    if new_name:
                        await self.db.collections['trackings'].update_one(
                            {'_id': ObjectId(pending_id)},
                            {'$set': {'product_name': new_name}}
                        )
                        context.user_data.pop('awaiting_rename_id', None)
                        await update.message.reply_text(f"✅ השם עודכן ל: {new_name}")
                        return
                # Otherwise guide user
                await update.message.reply_text("🤖 שלחו קישור למוצר כדי להתחיל לעקוב, או השתמשו בכפתורים למטה.")
                
        except Exception as e:
            logger.error(f"❌ Error in generic message handler: {e}")

    async def handle_rename_tracking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Initiate manual rename flow via button"""
        try:
            query = update.callback_query
            await query.answer()
            parts = query.data.split('_')
            if len(parts) != 2:
                return
            tracking_id = parts[1]
            context.user_data['awaiting_rename_id'] = tracking_id
            await query.edit_message_text(
                "✍️ שלחו עכשיו את השם המדויק למוצר, ואני אעדכן אותו במעקב.")
        except Exception as e:
            logger.error(f"❌ Error in handle_rename_tracking: {e}")
    
    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel current conversation"""
        keyboard = ReplyKeyboardMarkup(
            KEYBOARD_LAYOUTS['main'],
            resize_keyboard=True
        )
        
        await update.effective_message.reply_text(
            "🔙 חזרתם לתפריט הראשי",
            reply_markup=keyboard
        )
        return ConversationHandler.END
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics"""
        try:
            stats = await self.get_stats()
            
            message = f"""📊 **סטטיסטיקות הבוט**

👥 משתמשים רשומים: {stats['users']['total']}
🟢 פעילים השבוע: {stats['users']['active_week']}
📦 סה"כ מעקבים: {stats['trackings']['total']}
⚡ מעקבים פעילים: {stats['trackings']['active']}
🔔 התראות נשלחו היום: {stats['alerts']['today']}

⏰ הבדיקה הבאה: {stats['next_check']}"""
            
            await update.effective_message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"❌ Error in stats command: {e}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"❌ Telegram error: {context.error}")
        
        if isinstance(context.error, Forbidden):
            # User blocked the bot
            if update and update.effective_user:
                await self.db.collections['users'].update_one(
                    {'user_id': update.effective_user.id},
                    {'$set': {'blocked_bot': True}}
                )
        elif isinstance(context.error, BadRequest):
            logger.warning(f"Bad request: {context.error}")
        else:
            # Generic error
            if update and update.effective_message:
                try:
                    await update.effective_message.reply_text(BOT_MESSAGES['error_occurred'])
                except:
                    pass
    
    # Stock checking logic
    async def _check_all_stocks(self):
        """Background job to check all stocks"""
        try:
            logger.info("🔍 Starting stock check cycle...")
            
            # Get trackings that need checking
            trackings = await self.db.get_trackings_to_check(config.DEFAULT_CHECK_INTERVAL)
            
            if not trackings:
                logger.info("📭 No trackings to check")
                return
            
            logger.info(f"📦 Checking {len(trackings)} products...")
            
            # Process in batches
            batch_size = config.MAX_CONCURRENT_REQUESTS
            for i in range(0, len(trackings), batch_size):
                batch = trackings[i:i + batch_size]
                await asyncio.gather(*[self._check_single_stock(t) for t in batch])
                
                # Small delay between batches
                await asyncio.sleep(1)
            
            logger.info("✅ Stock check cycle completed")
            
        except Exception as e:
            logger.error(f"❌ Error in stock check cycle: {e}")
    
    async def _check_single_stock(self, tracking: ProductTracking):
        """Check for page changes and send notification if needed"""
        try:
            # Get current page state
            store_config = SUPPORTED_CLUBS.get(tracking.store_id)
            if not store_config:
                logger.warning(f"⚠️ Unknown store: {tracking.store_id}")
                return
            
            # Check if tracking mode is 'changes' (new mode) or 'stock' (legacy)
            if getattr(tracking, 'tracking_mode', 'stock') == 'changes':
                # New change detection mode
                change_result = await self.scraper.check_page_changes(
                    tracking.product_url,
                    tracking.store_id,
                    getattr(tracking, 'last_page_hash', None)
                )
                
                if change_result['change_type'] == 'error':
                    # Error checking - increment error count
                    error_count = tracking.error_count + 1
                    if error_count >= 5:
                        await self.db.update_tracking_status(
                            tracking._id,
                            TrackingStatus.ERROR,
                            error_count=error_count
                        )
                    else:
                        await self.db.update_tracking_status(
                            tracking._id,
                            tracking.status,
                            error_count=error_count
                        )
                    return
                
                # Check if page changed
                if change_result['changed'] and change_result['change_type'] != 'initial':
                    # Page changed - send notification
                    await self.db.update_tracking_status(
                        tracking._id,
                        TrackingStatus.ACTIVE,
                        error_count=0,
                        notification_sent=True,
                        page_hash=change_result['current_hash'],
                        change_detected=True
                    )
                    # Check if there are new deals/items
                    new_items = change_result.get('new_items', [])
                    await self._send_change_notification(tracking, new_items)
                else:
                    # No change - just update last checked
                    await self.db.update_tracking_status(
                        tracking._id,
                        TrackingStatus.ACTIVE,
                        error_count=0,
                        notification_sent=False,
                        page_hash=change_result['current_hash']
                    )
            else:
                # Legacy stock checking mode
                current_status = await self.scraper.check_stock_status(
                    tracking.product_url,
                    tracking.store_id
                )
                
                if current_status is None:
                    # Error checking
                    error_count = tracking.error_count + 1
                    if error_count >= 5:
                        await self.db.update_tracking_status(
                            tracking._id,
                            TrackingStatus.ERROR,
                            error_count=error_count
                        )
                    else:
                        await self.db.update_tracking_status(
                            tracking._id,
                            tracking.status,
                            error_count=error_count
                        )
                    return
                
                # Determine if we should send notification
                should_notify = False
                new_status = TrackingStatus.IN_STOCK if current_status else TrackingStatus.OUT_OF_STOCK
                
                # Check if status changed from out-of-stock to in-stock
                if (tracking.status == TrackingStatus.OUT_OF_STOCK and 
                    new_status == TrackingStatus.IN_STOCK and 
                    not tracking.notification_sent):
                    should_notify = True
                
                # Update tracking status
                await self.db.update_tracking_status(
                    tracking._id,
                    new_status,
                    error_count=0,
                    notification_sent=should_notify
                )
                
                # Send notification if needed
                if should_notify:
                    await self._send_stock_notification(tracking)
                
        except Exception as e:
            logger.error(f"❌ Error checking for {tracking.product_name}: {e}")
    
    async def _send_change_notification(self, tracking: ProductTracking, new_items: List[Dict[str, str]] = None):
        """Send page change notification"""
        try:
            # Respect user's notification settings
            user_doc = await self.db.collections['users'].find_one({'user_id': tracking.user_id})
            if user_doc and user_doc.get('notifications_enabled', True) is False:
                logger.info(f"🔕 Notifications disabled for user {tracking.user_id}, skipping alert")
                return

            # Build message based on whether we have new items
            if new_items:
                message = (
                    f"🎉 **זוהו פריטים חדשים בעמוד!**\n\n"
                    f"📦 {tracking.product_name}\n"
                    f"🏪 {tracking.store_name}\n\n"
                    f"**פריטים חדשים:**\n"
                )
                for item in new_items[:3]:  # Show max 3 items
                    message += f"• {item.get('title', 'פריט חדש')}\n"
                if len(new_items) > 3:
                    message += f"• ועוד {len(new_items) - 3} פריטים...\n"
                message += f"\n🔗 [לחצו כאן לצפייה בעמוד]({tracking.product_url})"
            else:
                message = (
                    f"🔔 **זוהה שינוי בעמוד!**\n\n"
                    f"📦 {tracking.product_name}\n"
                    f"🏪 {tracking.store_name}\n"
                    f"🔗 [לחצו כאן לצפייה בעמוד]({tracking.product_url})\n\n"
                    f"ℹ️ ייתכן שהסטטוס של המוצר השתנה או שהתווסף מידע חדש"
                )
            
            # Create action keyboard
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🛒 צפה בעמוד", url=tracking.product_url)
                ],
                [
                    InlineKeyboardButton("⏸ השהה מעקב", callback_data=f"pause_{tracking._id}"),
                    InlineKeyboardButton("🗑 הסר מעקב", callback_data=f"remove_{tracking._id}")
                ]
            ])
            
            await self.bot.send_message(
                chat_id=tracking.user_id,
                text=message,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Save alert to database
            alert = StockAlert(
                user_id=tracking.user_id,
                product_tracking_id=tracking._id,
                product_name=tracking.product_name,
                product_url=tracking.product_url,
                store_name=tracking.store_name,
                alert_type='page_change',
                message=message,
                delivered=True
            )
            
            await self.db.save_alert(alert)
            
            logger.info(f"🔔 Change notification sent to user {tracking.user_id}: {tracking.product_name}")
            
        except Forbidden:
            # User blocked the bot
            logger.info(f"🚫 User {tracking.user_id} blocked the bot")
            await self.db.collections['users'].update_one(
                {'user_id': tracking.user_id},
                {'$set': {'blocked_bot': True}}
            )
        except Exception as e:
            logger.error(f"❌ Error sending notification: {e}")
    
    async def _send_stock_notification(self, tracking: ProductTracking):
        """Send stock available notification (legacy)"""
        try:
            # Respect user's notification settings
            user_doc = await self.db.collections['users'].find_one({'user_id': tracking.user_id})
            if user_doc and user_doc.get('notifications_enabled', True) is False:
                logger.info(f"🔕 Notifications disabled for user {tracking.user_id}, skipping alert")
                return

            message = BOT_MESSAGES['back_in_stock'].format(
                product_name=tracking.product_name,
                store_name=tracking.store_name,
                product_url=tracking.product_url
            )
            
            # Create action keyboard
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🛒 קנה עכשיו", url=tracking.product_url)
                ],
                [
                    InlineKeyboardButton("⏸ השהה מעקב", callback_data=f"pause_{tracking._id}"),
                    InlineKeyboardButton("🗑 הסר מעקב", callback_data=f"remove_{tracking._id}")
                ]
            ])
            
            await self.bot.send_message(
                chat_id=tracking.user_id,
                text=message,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Save alert to database
            alert = StockAlert(
                user_id=tracking.user_id,
                product_tracking_id=tracking._id,
                product_name=tracking.product_name,
                product_url=tracking.product_url,
                store_name=tracking.store_name,
                alert_type='back_in_stock',
                message=message,
                delivered=True
            )
            
            await self.db.save_alert(alert)
            
            logger.info(f"🔔 Stock notification sent to user {tracking.user_id}: {tracking.product_name}")
            
        except Forbidden:
            # User blocked the bot
            logger.info(f"🚫 User {tracking.user_id} blocked the bot")
            await self.db.collections['users'].update_one(
                {'user_id': tracking.user_id},
                {'$set': {'blocked_bot': True}}
            )
        except Exception as e:
            logger.error(f"❌ Error sending notification: {e}")
    
    # Helper methods
    def _validate_url(self, url: str) -> Optional[Dict[str, str]]:
        """Validate URL and return store info"""
        try:
            parsed = urlparse(url.lower())
            domain = parsed.netloc.replace('www.', '')
            
            for store_id, store_config in SUPPORTED_CLUBS.items():
                store_domain = urlparse(store_config['base_url']).netloc.replace('www.', '')
                # Accept either the primary base_url domain or any additional domains listed
                extra_domains = set([d.replace('www.', '') for d in store_config.get('domains', [])])
                if domain == store_domain or domain in extra_domains:
                    return {
                        'store_id': store_id,
                        'name': store_config['name']
                    }
            
            return None
            
        except Exception:
            return None
    
    def _get_frequency_text(self, minutes: int) -> str:
        """Convert minutes to readable frequency text"""
        if minutes < 60:
            return f"כל {minutes} דקות"
        elif minutes < 1440:
            hours = minutes // 60
            return f"כל {hours} שעות" if hours > 1 else "כל שעה"
        else:
            days = minutes // 1440
            return f"כל {days} ימים" if days > 1 else "כל יום"
    
    async def _check_rate_limit(self, user_id: int) -> bool:
        """Check if user is within rate limits"""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=config.RATE_LIMIT_WINDOW)
        
        if user_id not in self.rate_limit_cache:
            self.rate_limit_cache[user_id] = []
        
        # Clean old entries
        self.rate_limit_cache[user_id] = [
            timestamp for timestamp in self.rate_limit_cache[user_id]
            if timestamp > cutoff
        ]
        
        # Check limit
        if len(self.rate_limit_cache[user_id]) >= config.RATE_LIMIT_PER_USER:
            return False
        
        # Add current request
        self.rate_limit_cache[user_id].append(now)
        return True
    
    async def _cleanup_old_data(self):
        """Clean up old alerts and inactive trackings"""
        try:
            # Remove old alerts (older than 30 days)
            cutoff = datetime.utcnow() - timedelta(days=30)
            result = await self.db.collections['alerts'].delete_many({
                'sent_at': {'$lt': cutoff}
            })
            
            if result.deleted_count > 0:
                logger.info(f"🧹 Cleaned up {result.deleted_count} old alerts")
                
        except Exception as e:
            logger.error(f"❌ Error in cleanup: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive bot statistics"""
        try:
            base_stats = await self.db.get_bot_stats()
            
            # Add scheduler info
            next_check = "לא זמין"
            if self.scheduler:
                jobs = self.scheduler.get_jobs()
                stock_job = next((job for job in jobs if job.id == 'stock_checker'), None)
                if stock_job and stock_job.next_run_time:
                    next_check = stock_job.next_run_time.strftime('%H:%M:%S')
            
            return {
                'users': {
                    'total': base_stats.get('total_users', 0),
                    'active_week': base_stats.get('active_users', 0)
                },
                'trackings': {
                    'total': base_stats.get('total_trackings', 0),
                    'active': base_stats.get('active_trackings', 0)
                },
                'alerts': {
                    'today': len([
                        alert for alert in await self.db.collections['alerts'].find({
                            'sent_at': {
                                '$gte': datetime.utcnow().replace(hour=0, minute=0, second=0)
                            }
                        }).to_list(1000)
                    ])
                },
                'next_check': next_check,
                'stores': base_stats.get('top_stores', [])
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {}