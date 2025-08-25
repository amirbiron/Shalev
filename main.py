"""
Stock Tracker Telegram Bot - Main Entry Point
Optimized for Render deployment with 2025 best practices
"""

import asyncio
import os
import logging
import sys
import signal
from contextlib import asynccontextmanager
from typing import Optional

# FastAPI for health check (Render requirement)
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
import uvicorn

# Telegram Bot
from telegram import Bot
from telegram.ext import Application, ContextTypes
from telegram.request import HTTPXRequest
from telegram.error import NetworkError as TgNetworkError

# Local imports
from config import config, BOT_MESSAGES
from bot import StockTrackerBot
from database import DatabaseManager

# Configure logging
logging.basicConfig(
    format=config.LOG_FORMAT,
    level=getattr(logging, config.LOG_LEVEL.upper()),
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)
DEPLOY_SHA = os.getenv('DEPLOY_SHA') or os.getenv('RENDER_GIT_COMMIT') or os.getenv('COMMIT_SHA') or ''
if not DEPLOY_SHA:
    # Try reading from common version files if available
    for _p in ('/app/commit.txt', '/app/version.txt', 'VERSION', 'version.txt'):
        try:
            with open(_p, 'r') as _f:
                DEPLOY_SHA = _f.read().strip()
                break
        except Exception:
            continue
if DEPLOY_SHA:
    logger.info(f"🧩 Deploy SHA: {DEPLOY_SHA}")

# Global variables for bot and database
bot_instance: Optional[StockTrackerBot] = None
db_manager: Optional[DatabaseManager] = None
telegram_app: Optional[Application] = None
polling_task: Optional[asyncio.Task] = None
init_task: Optional[asyncio.Task] = None
initialized: bool = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle without blocking server readiness"""
    global bot_instance, db_manager, telegram_app, polling_task, init_task, initialized

    async def initialize_services():
        global initialized
        logger.info("🚀 Starting Stock Tracker Bot (background init)...")
        try:
            # Initialize database
            logger.info("📊 Connecting to database...")
            local_db_manager = DatabaseManager()
            await local_db_manager.connect()

            # Initialize bot
            logger.info("🤖 Initializing Telegram bot...")
            local_bot_instance = StockTrackerBot(local_db_manager)

            # Create Telegram application with robust HTTP client (timeouts, no HTTP/2)
            request = HTTPXRequest(
                connect_timeout=20,
                read_timeout=90,
                write_timeout=30,
                pool_timeout=20,
                http_version="1.1",
            )
            local_telegram_app = (
                Application.builder()
                .token(config.TELEGRAM_TOKEN)
                .request(request)
                .build()
            )

            # Setup bot handlers
            local_bot_instance.setup_handlers(local_telegram_app)

            # Global error handler for better diagnostics of transient network errors
            async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
                if isinstance(context.error, TgNetworkError):
                    logger.warning(f"Transient Telegram network error: {context.error}")
                    return
                logger.exception("Unhandled error", exc_info=context.error)
            local_telegram_app.add_error_handler(on_error)

            # Start the bot
            if config.ENVIRONMENT == 'production' and config.WEBHOOK_URL and not config.FORCE_POLLING:
                logger.info(f"🌐 Starting webhook on {config.WEBHOOK_URL}")
                await local_telegram_app.bot.set_webhook(
                    url=f"{config.WEBHOOK_URL}/telegram-webhook",
                    allowed_updates=['message', 'callback_query']
                )
                await local_telegram_app.initialize()
                await local_telegram_app.start()
            else:
                logger.info("🔄 Starting polling mode...")
                await local_telegram_app.initialize()
                await local_telegram_app.start()
                try:
                    await local_telegram_app.bot.delete_webhook(drop_pending_updates=True)
                except Exception as e:
                    logger.warning(f"Failed to delete webhook before polling: {e}")
                # Start polling in background with explicit long-poll timeout and no backlog
                local_polling_task = asyncio.create_task(
                    local_telegram_app.updater.start_polling(
                        drop_pending_updates=True,
                        allowed_updates=['message', 'callback_query'],
                        timeout=60
                    )
                )
                # Assign to globals after creation
                globals()['polling_task'] = local_polling_task

            # Start the scheduler
            logger.info("⏰ Starting stock check scheduler...")
            await local_bot_instance.start_scheduler()

            # Publish to globals on success
            globals()['db_manager'] = local_db_manager
            globals()['bot_instance'] = local_bot_instance
            globals()['telegram_app'] = local_telegram_app
            initialized = True

            logger.info("✅ Bot started successfully!")
        except Exception as e:
            logger.error(f"❌ Background init failed: {e}")

    # Kick off background initialization and immediately yield to start HTTP server
    init_task = asyncio.create_task(initialize_services())
    yield

    # Cleanup (best-effort)
    logger.info("🛑 Shutting down bot...")
    try:
        if bot_instance:
            await bot_instance.stop_scheduler()

        if telegram_app:
            if polling_task:
                try:
                    if telegram_app.updater and telegram_app.updater.running:
                        await telegram_app.updater.stop()
                except Exception as e:
                    logger.warning(f"Error stopping updater: {e}")
                try:
                    await polling_task
                except Exception as e:
                    logger.warning(f"Error awaiting polling task: {e}")
                finally:
                    globals()['polling_task'] = None
            else:
                try:
                    await telegram_app.bot.delete_webhook(drop_pending_updates=False)
                except Exception as e:
                    logger.warning(f"Error deleting webhook during shutdown: {e}")
            await telegram_app.stop()
            await telegram_app.shutdown()

        if db_manager:
            await db_manager.close()
        # Ensure scraper (browser/session) is closed to avoid unclosed session errors
        try:
            if bot_instance and bot_instance.scraper:
                await bot_instance.scraper.close()
        except Exception as e:
            logger.warning(f"Error closing scraper on shutdown: {e}")
    finally:
        logger.info("👋 Bot stopped.")

# Create FastAPI app for health checks and webhook
app = FastAPI(
    title="Stock Tracker Bot",
    description="Telegram bot for tracking product availability",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    """Root endpoint for basic health check"""
    return {
        "status": "running",
        "bot": "Stock Tracker Telegram Bot",
        "version": "1.0.0",
        "environment": config.ENVIRONMENT
    }

@app.head("/")
async def root_head():
    """HEAD support for uptime monitors"""
    return Response(status_code=200)

@app.get("/uptime")
async def uptime():
    """Simple liveness probe that always returns 200 OK"""
    return {"status": "ok"}

@app.head("/uptime")
async def uptime_head():
    """HEAD support for uptime monitors"""
    return Response(status_code=200)

@app.get("/health")
async def health_check():
    """Detailed health check for monitoring"""
    try:
        # Check database connection
        db_healthy = await db_manager.health_check() if db_manager else False
        
        # Check bot status
        bot_healthy = telegram_app.running if telegram_app else False
        
        # Check scheduler status
        scheduler_healthy = (
            bot_instance.scheduler.running 
            if bot_instance and hasattr(bot_instance, 'scheduler') 
            else False
        )
        
        overall_health = db_healthy and bot_healthy
        
        return JSONResponse(
            status_code=200 if overall_health else 503,
            content={
                "status": "healthy" if overall_health else "unhealthy",
                "components": {
                    "database": "healthy" if db_healthy else "unhealthy",
                    "telegram_bot": "healthy" if bot_healthy else "unhealthy",
                    "scheduler": "healthy" if scheduler_healthy else "unhealthy"
                },
                "environment": config.ENVIRONMENT,
                "timestamp": asyncio.get_event_loop().time()
            }
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time()
            }
        )

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """Handle Telegram webhook (production only)"""
    if not telegram_app:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    try:
        # Get update from request
        update_data = await request.json()
        
        # Process update
        from telegram import Update
        update = Update.de_json(update_data, telegram_app.bot)
        
        # Add to update queue
        await telegram_app.update_queue.put(update)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/telegram-webhook")
async def telegram_webhook_get():
    """Allow GET on webhook path for uptime checks (returns 200 OK)"""
    return {"status": "ok"}

@app.get("/stats")
async def get_stats():
    """Get bot usage statistics"""
    if not bot_instance:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    
    try:
        stats = await bot_instance.get_stats()
        return stats
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/version")
async def version():
    return {"sha": DEPLOY_SHA or "unknown"}


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    # FastAPI will handle the cleanup through lifespan
    sys.exit(0)

async def run_development():
    """Run in development mode with polling"""
    logger.info("🔧 Running in development mode...")
    
    # Just run the FastAPI server, lifespan will handle the bot
    config_uvicorn = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=config.WEBHOOK_PORT,
        log_level=config.LOG_LEVEL.lower()
    )
    server = uvicorn.Server(config_uvicorn)
    await server.serve()


def main():
    """Main entry point"""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🎯 Stock Tracker Bot starting...")
    logger.info(f"Environment: {config.ENVIRONMENT}")
    logger.info(f"Port: {config.WEBHOOK_PORT}")
    
    try:
        if config.ENVIRONMENT == 'production':
            # Production: Run with uvicorn server
            uvicorn.run(
                app,
                host="0.0.0.0",
                port=config.WEBHOOK_PORT,
                log_level=config.LOG_LEVEL.lower()
            )
        else:
            # Development: Run with asyncio
            asyncio.run(run_development())
            
    except KeyboardInterrupt:
        logger.info("👋 Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()