"""
Database Manager for Stock Tracker Bot
MongoDB operations with PyMongo 4.14.1 - 2025 Edition
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError
from bson import ObjectId
from pymongo import ReturnDocument

from config import config

logger = logging.getLogger(__name__)

class TrackingStatus(Enum):
    """Product tracking status"""
    ACTIVE = "active"
    PAUSED = "paused"
    OUT_OF_STOCK = "out_of_stock"
    IN_STOCK = "in_stock"
    ERROR = "error"

@dataclass
class ProductTracking:
    """Product tracking model"""
    user_id: int
    product_url: str
    product_name: str
    store_name: str
    store_id: str
    check_interval: int  # minutes
    status: TrackingStatus
    # Optional: canonical URL without option augmentation (for display/back-compat)
    original_url: Optional[str] = None
    # Optional selected option/deal to track (e.g., "20%", "דיל 85₪")
    option_label: Optional[str] = None
    # Normalized key for the selected option (used for dedup/uniqueness)
    option_key: Optional[str] = None
    last_checked: Optional[datetime] = None
    last_status_change: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    error_count: int = 0
    notification_sent: bool = False
    product_key: Optional[str] = None
    # For change detection mode
    tracking_mode: str = 'changes'  # 'stock' or 'changes'
    last_page_hash: Optional[str] = None
    change_count: int = 0
    _id: Optional[ObjectId] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB"""
        data = asdict(self)
        data['status'] = self.status.value
        return data

@dataclass
class UserProfile:
    """User profile model"""
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    language_code: Optional[str]
    is_premium: bool = False
    total_trackings: int = 0
    active_trackings: int = 0
    notifications_enabled: bool = True
    default_check_interval: int = 60  # minutes
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    _id: Optional[ObjectId] = None

@dataclass
class StockAlert:
    """Stock alert/notification model"""
    user_id: int
    product_tracking_id: ObjectId
    product_name: str
    product_url: str
    store_name: str
    alert_type: str  # 'back_in_stock', 'error', 'status_change'
    message: str
    sent_at: Optional[datetime] = None
    delivered: bool = False
    _id: Optional[ObjectId] = None

class DatabaseManager:
    """Async MongoDB database manager using Motor"""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.collections = {}
        
    async def connect(self):
        """Connect to MongoDB"""
        try:
            logger.info(f"🔌 Connecting to MongoDB: {config.MONGODB_URI}")
            
            # Create async client
            self.client = AsyncIOMotorClient(
                config.MONGODB_URI,
                maxPoolSize=10,
                minPoolSize=2,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000
            )
            
            # Get database
            self.db = self.client[config.DB_NAME]
            
            # Initialize collections
            self.collections = {
                'users': self.db.users,
                'trackings': self.db.product_trackings,
                'alerts': self.db.stock_alerts,
                'stats': self.db.bot_stats
            }
            
            # Test connection
            await self.client.admin.command('ping')
            
            # Create indexes for better performance
            await self._create_indexes()
            
            logger.info("✅ Connected to MongoDB successfully")
            
        except ConnectionFailure as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")
            raise
    
    async def _create_indexes(self):
        """Create database indexes for optimal performance"""
        try:
            # Users collection indexes
            await self.collections['users'].create_index('user_id', unique=True)
            await self.collections['users'].create_index('username')
            await self.collections['users'].create_index('last_activity')
            
            # Trackings collection indexes
            # Unique on (user_id, product_url) remains, but we will also de-duplicate in app by product_key
            await self.collections['trackings'].create_index([
                ('user_id', 1), ('product_url', 1), ('option_key', 1)
            ], unique=True)
            await self.collections['trackings'].create_index('status')
            await self.collections['trackings'].create_index('last_checked')
            await self.collections['trackings'].create_index('store_id')
            await self.collections['trackings'].create_index('product_key')
            await self.collections['trackings'].create_index('option_label')
            await self.collections['trackings'].create_index('tracking_mode')
            await self.collections['trackings'].create_index([
                ('status', 1), ('last_checked', 1)
            ])
            
            # Alerts collection indexes
            await self.collections['alerts'].create_index('user_id')
            await self.collections['alerts'].create_index('sent_at')
            await self.collections['alerts'].create_index('delivered')
            await self.collections['alerts'].create_index([
                ('user_id', 1), ('sent_at', -1)
            ])
            
            logger.info("📊 Database indexes created successfully")
            
        except Exception as e:
            logger.warning(f"⚠️ Index creation warning: {e}")
    
    async def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            logger.info("🔌 MongoDB connection closed")
    
    async def health_check(self) -> bool:
        """Check database health"""
        try:
            if not self.client:
                return False
            await self.client.admin.command('ping')
            return True
        except Exception:
            return False
    
    # User Management
    async def get_or_create_user(self, user_data: Dict[str, Any]) -> UserProfile:
        """Get existing user or create new one"""
        try:
            user_id = user_data['id']
            
            # Try to find existing user
            existing_user = await self.collections['users'].find_one({'user_id': user_id})
            
            if existing_user:
                # Update last activity and basic info
                update_data = {
                    'last_activity': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
                
                # Update user info if provided
                if 'username' in user_data:
                    update_data['username'] = user_data['username']
                if 'first_name' in user_data:
                    update_data['first_name'] = user_data['first_name']
                if 'last_name' in user_data:
                    update_data['last_name'] = user_data['last_name']
                
                await self.collections['users'].update_one(
                    {'user_id': user_id},
                    {'$set': update_data}
                )
                
                # Convert to UserProfile
                return UserProfile(
                    user_id=existing_user['user_id'],
                    username=existing_user.get('username'),
                    first_name=existing_user.get('first_name'),
                    last_name=existing_user.get('last_name'),
                    language_code=existing_user.get('language_code'),
                    is_premium=existing_user.get('is_premium', False),
                    total_trackings=existing_user.get('total_trackings', 0),
                    active_trackings=existing_user.get('active_trackings', 0),
                    notifications_enabled=existing_user.get('notifications_enabled', True),
                    default_check_interval=existing_user.get('default_check_interval', 60),
                    created_at=existing_user.get('created_at'),
                    updated_at=update_data['updated_at'],
                    last_activity=update_data['last_activity'],
                    _id=existing_user['_id']
                )
            else:
                # Create new user
                now = datetime.utcnow()
                new_user = UserProfile(
                    user_id=user_id,
                    username=user_data.get('username'),
                    first_name=user_data.get('first_name'),
                    last_name=user_data.get('last_name'),
                    language_code=user_data.get('language_code'),
                    created_at=now,
                    updated_at=now,
                    last_activity=now
                )
                
                result = await self.collections['users'].insert_one(asdict(new_user))
                new_user._id = result.inserted_id
                
                logger.info(f"👤 New user created: {user_id}")
                return new_user
                
        except Exception as e:
            logger.error(f"❌ Error managing user {user_data.get('id')}: {e}")
            raise
    
    # Product Tracking Management
    async def add_tracking(self, tracking: ProductTracking) -> Optional[ObjectId]:
        """Add new product tracking atomically and return its _id (always)."""
        try:
            now = datetime.utcnow()
            tracking.created_at = now
            tracking.updated_at = now
            tracking.status = TrackingStatus.ACTIVE
            doc = tracking.to_dict()
            # Ensure MongoDB generates a proper ObjectId
            if doc.get('_id') is None:
                doc.pop('_id', None)

            # Atomic upsert that returns the document in one round-trip
            filter_q = {'user_id': tracking.user_id, 'product_url': tracking.product_url}
            update_q = {
                '$setOnInsert': doc
            }
            result = await self.collections['trackings'].find_one_and_update(
                filter_q,
                update_q,
                upsert=True,
                return_document=ReturnDocument.AFTER
            )

            if result and result.get('_id'):
                # If this was an insert, increment user counters (best-effort)
                if result.get('created_at') == now:
                    await self.collections['users'].update_one(
                        {'user_id': tracking.user_id},
                        {
                            '$inc': {
                                'total_trackings': 1,
                                'active_trackings': 1
                            },
                            '$set': {'updated_at': now}
                        },
                        upsert=True
                    )
                return result['_id']

            return None
            
        except DuplicateKeyError:
            # Return existing id on duplicate
            existing = await self.collections['trackings'].find_one({
                'user_id': tracking.user_id,
                'product_url': tracking.product_url
            })
            if existing:
                return existing.get('_id')
            elif tracking.product_key:
                existing = await self.collections['trackings'].find_one({
                    'user_id': tracking.user_id,
                    'product_key': tracking.product_key,
                    'store_id': tracking.store_id
                })
                if existing:
                    return existing.get('_id')
            return None
        except Exception as e:
            logger.error(f"❌ Error adding tracking: {e}")
            raise
    
    async def get_user_trackings(self, user_id: int, status: Optional[TrackingStatus] = None) -> List[ProductTracking]:
        """Get all trackings for a user"""
        try:
            query = {'user_id': user_id}
            if status:
                query['status'] = status.value
            
            cursor = self.collections['trackings'].find(query).sort('created_at', -1)
            trackings = []
            
            async for doc in cursor:
                tracking = ProductTracking(
                    user_id=doc['user_id'],
                    product_url=doc['product_url'],
                    product_key=doc.get('product_key'),
                    product_name=doc['product_name'],
                    store_name=doc['store_name'],
                    store_id=doc['store_id'],
                    check_interval=doc['check_interval'],
                    status=TrackingStatus(doc['status']),
                    tracking_mode=doc.get('tracking_mode', 'stock'),
                    last_page_hash=doc.get('last_page_hash'),
                    change_count=doc.get('change_count', 0),
                    last_checked=doc.get('last_checked'),
                    last_status_change=doc.get('last_status_change'),
                    created_at=doc.get('created_at'),
                    updated_at=doc.get('updated_at'),
                    error_count=doc.get('error_count', 0),
                    notification_sent=doc.get('notification_sent', False),
                    _id=doc['_id']
                )
                trackings.append(tracking)
            
            return trackings
            
        except Exception as e:
            logger.error(f"❌ Error getting trackings for user {user_id}: {e}")
            return []
    
    async def get_trackings_to_check(self, max_age_minutes: int = 60) -> List[ProductTracking]:
        """Get trackings that need to be checked"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(minutes=max_age_minutes)
            
            query = {
                'status': TrackingStatus.ACTIVE.value,
                '$or': [
                    {'last_checked': {'$lt': cutoff_time}},
                    {'last_checked': {'$exists': False}}
                ]
            }
            
            cursor = self.collections['trackings'].find(query).limit(100)
            trackings = []
            
            async for doc in cursor:
                tracking = ProductTracking(
                    user_id=doc['user_id'],
                    product_url=doc['product_url'],
                    product_name=doc['product_name'],
                    store_name=doc['store_name'],
                    store_id=doc['store_id'],
                    check_interval=doc['check_interval'],
                    status=TrackingStatus(doc['status']),
                    tracking_mode=doc.get('tracking_mode', 'stock'),
                    last_page_hash=doc.get('last_page_hash'),
                    change_count=doc.get('change_count', 0),
                    last_checked=doc.get('last_checked'),
                    last_status_change=doc.get('last_status_change'),
                    created_at=doc.get('created_at'),
                    updated_at=doc.get('updated_at'),
                    error_count=doc.get('error_count', 0),
                    notification_sent=doc.get('notification_sent', False),
                    _id=doc['_id']
                )
                trackings.append(tracking)
            
            return trackings
            
        except Exception as e:
            logger.error(f"❌ Error getting trackings to check: {e}")
            return []
    
    async def update_tracking_status(self, tracking_id: ObjectId, new_status: TrackingStatus, 
                                   error_count: int = 0, notification_sent: bool = False,
                                   page_hash: Optional[str] = None, change_detected: bool = False):
        """Update tracking status"""
        try:
            now = datetime.utcnow()
            update_data = {
                'status': new_status.value,
                'last_checked': now,
                'updated_at': now,
                'error_count': error_count,
                'notification_sent': notification_sent
            }
            
            # Update page hash if provided
            if page_hash:
                update_data['last_page_hash'] = page_hash
            
            # If change detected, increment counter
            if change_detected:
                update_data['change_count'] = {'$inc': 1}
            
            # If status changed, update timestamp
            current_tracking = await self.collections['trackings'].find_one({'_id': tracking_id})
            if current_tracking and current_tracking.get('status') != new_status.value:
                update_data['last_status_change'] = now
            
            # Handle increment operations separately
            inc_ops = {}
            if 'change_count' in update_data:
                inc_ops['change_count'] = 1
                del update_data['change_count']
            
            update_ops = {'$set': update_data}
            if inc_ops:
                update_ops['$inc'] = inc_ops
            
            await self.collections['trackings'].update_one(
                {'_id': tracking_id},
                update_ops
            )
            
        except Exception as e:
            logger.error(f"❌ Error updating tracking status: {e}")
            raise
    
    async def remove_tracking(self, user_id: int, tracking_id: ObjectId) -> bool:
        """Remove a tracking"""
        try:
            result = await self.collections['trackings'].delete_one({
                '_id': tracking_id,
                'user_id': user_id
            })
            
            if result.deleted_count > 0:
                # Update user stats
                await self.collections['users'].update_one(
                    {'user_id': user_id},
                    {
                        '$inc': {'active_trackings': -1},
                        '$set': {'updated_at': datetime.utcnow()}
                    }
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error removing tracking: {e}")
            return False
    
    # Alerts Management
    async def save_alert(self, alert: StockAlert) -> ObjectId:
        """Save stock alert"""
        try:
            alert.sent_at = datetime.utcnow()
            result = await self.collections['alerts'].insert_one(asdict(alert))
            return result.inserted_id
        except Exception as e:
            logger.error(f"❌ Error saving alert: {e}")
            raise
    
    # Statistics
    async def get_bot_stats(self) -> Dict[str, Any]:
        """Get bot usage statistics"""
        try:
            total_users = await self.collections['users'].count_documents({})
            active_users = await self.collections['users'].count_documents({
                'last_activity': {'$gte': datetime.utcnow() - timedelta(days=7)}
            })
            total_trackings = await self.collections['trackings'].count_documents({})
            active_trackings = await self.collections['trackings'].count_documents({
                'status': TrackingStatus.ACTIVE.value
            })
            
            # Top stores
            pipeline = [
                {'$group': {'_id': '$store_name', 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}},
                {'$limit': 10}
            ]
            top_stores = await self.collections['trackings'].aggregate(pipeline).to_list(10)
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'total_trackings': total_trackings,
                'active_trackings': active_trackings,
                'top_stores': top_stores,
                'generated_at': datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {}