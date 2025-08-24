"""
Basic Unit Tests for Stock Tracker Bot
Tests core functionality without external dependencies
"""

import asyncio
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from urllib.parse import urlparse
import json

# Test environment setup
os.environ['TELEGRAM_TOKEN'] = 'test_token'
os.environ['MONGODB_URI'] = 'mongodb://test:27017'
os.environ['ENVIRONMENT'] = 'testing'

# Imports after environment setup
from config import config, SUPPORTED_CLUBS, BOT_MESSAGES, KEYBOARD_LAYOUTS
from database import (
    DatabaseManager, ProductTracking, UserProfile, StockAlert, 
    TrackingStatus
)
from scrapers import StockScraper, ProductInfo
from bot import StockTrackerBot

# ========================================
# FIXTURES
# ========================================

@pytest.fixture
def sample_user_data():
    """Sample Telegram user data for testing"""
    return {
        'id': 123456789,
        'first_name': 'Test',
        'last_name': 'User',
        'username': 'testuser',
        'language_code': 'he'
    }

@pytest.fixture  
def sample_product_tracking():
    """Sample product tracking object"""
    return ProductTracking(
        user_id=123456789,
        product_url='https://www.mashkarcard.co.il/product/12345',
        product_name='אייפון 15 פרו',
        store_name='משקארד',
        store_id='mashkar',
        check_interval=60,
        status=TrackingStatus.ACTIVE,
        created_at=datetime.utcnow()
    )

@pytest.fixture
def sample_user_profile():
    """Sample user profile"""
    return UserProfile(
        user_id=123456789,
        username='testuser',
        first_name='Test',
        last_name='User',
        language_code='he',
        created_at=datetime.utcnow()
    )

@pytest.fixture
def mock_db_manager():
    """Mock database manager"""
    db_manager = Mock(spec=DatabaseManager)
    db_manager.connect = AsyncMock()
    db_manager.close = AsyncMock()
    db_manager.health_check = AsyncMock(return_value=True)
    db_manager.get_or_create_user = AsyncMock()
    db_manager.add_tracking = AsyncMock()
    db_manager.get_user_trackings = AsyncMock(return_value=[])
    db_manager.get_trackings_to_check = AsyncMock(return_value=[])
    db_manager.update_tracking_status = AsyncMock()
    db_manager.remove_tracking = AsyncMock(return_value=True)
    db_manager.save_alert = AsyncMock()
    db_manager.get_bot_stats = AsyncMock(return_value={
        'total_users': 100,
        'active_users': 50,
        'total_trackings': 200,
        'active_trackings': 150,
        'top_stores': []
    })
    return db_manager

@pytest.fixture
def mock_scraper():
    """Mock web scraper"""
    scraper = Mock(spec=StockScraper)
    scraper.get_product_info = AsyncMock()
    scraper.check_stock_status = AsyncMock()
    scraper.close = AsyncMock()
    return scraper

# ========================================
# CONFIG TESTS
# ========================================

class TestConfig:
    """Test configuration management"""
    
    def test_bot_config_initialization(self):
        """Test that bot configuration initializes correctly"""
        assert config.TELEGRAM_TOKEN == 'test_token'
        assert config.MONGODB_URI == 'mongodb://test:27017'
        assert config.ENVIRONMENT == 'testing'
        assert config.DEBUG is False
        assert config.WEBHOOK_PORT == 10000
        
    def test_supported_clubs_structure(self):
        """Test supported clubs configuration structure"""
        assert isinstance(SUPPORTED_CLUBS, dict)
        assert len(SUPPORTED_CLUBS) > 0
        
        for club_id, club_config in SUPPORTED_CLUBS.items():
            assert 'name' in club_config
            assert 'base_url' in club_config  
            assert 'stock_selector' in club_config
            assert 'out_of_stock_indicators' in club_config
            assert isinstance(club_config['out_of_stock_indicators'], list)
            
            # Test URL validity
            parsed_url = urlparse(club_config['base_url'])
            assert parsed_url.scheme in ['http', 'https']
            assert parsed_url.netloc
    
    def test_bot_messages_completeness(self):
        """Test that all required bot messages are present"""
        required_messages = [
            'welcome', 'help', 'invalid_url', 'already_tracking',
            'tracking_added', 'no_trackings', 'back_in_stock',
            'error_occurred', 'rate_limit_exceeded'
        ]
        
        for msg in required_messages:
            assert msg in BOT_MESSAGES
            assert isinstance(BOT_MESSAGES[msg], str)
            assert len(BOT_MESSAGES[msg]) > 0
    
    def test_keyboard_layouts(self):
        """Test keyboard layout configurations"""
        assert 'main' in KEYBOARD_LAYOUTS
        assert 'settings' in KEYBOARD_LAYOUTS
        assert 'frequency' in KEYBOARD_LAYOUTS
        
        for layout_name, layout in KEYBOARD_LAYOUTS.items():
            assert isinstance(layout, list)
            assert len(layout) > 0
            for row in layout:
                assert isinstance(row, list)
                assert len(row) > 0

# ========================================
# DATABASE MODEL TESTS  
# ========================================

class TestDatabaseModels:
    """Test database models and operations"""
    
    def test_product_tracking_model(self, sample_product_tracking):
        """Test ProductTracking model"""
        tracking = sample_product_tracking
        
        assert tracking.user_id == 123456789
        assert tracking.product_name == 'אייפון 15 פרו'
        assert tracking.store_id == 'mashkar'
        assert tracking.status == TrackingStatus.ACTIVE
        assert tracking.check_interval == 60
        
        # Test to_dict method
        tracking_dict = tracking.to_dict()
        assert isinstance(tracking_dict, dict)
        assert tracking_dict['user_id'] == 123456789
        assert tracking_dict['status'] == 'active'
    
    def test_user_profile_model(self, sample_user_profile):
        """Test UserProfile model"""
        profile = sample_user_profile
        
        assert profile.user_id == 123456789
        assert profile.username == 'testuser'
        assert profile.first_name == 'Test'
        assert profile.notifications_enabled is True
        assert profile.default_check_interval == 60
    
    def test_tracking_status_enum(self):
        """Test TrackingStatus enum"""
        assert TrackingStatus.ACTIVE.value == 'active'
        assert TrackingStatus.PAUSED.value == 'paused'
        assert TrackingStatus.OUT_OF_STOCK.value == 'out_of_stock'
        assert TrackingStatus.IN_STOCK.value == 'in_stock'
        assert TrackingStatus.ERROR.value == 'error'
        
        # Test enum comparison
        assert TrackingStatus('active') == TrackingStatus.ACTIVE
    
    @pytest.mark.asyncio
    async def test_database_manager_initialization(self):
        """Test DatabaseManager can be initialized"""
        db_manager = DatabaseManager()
        
        assert db_manager.client is None
        assert db_manager.db is None
        assert db_manager.collections == {}
        
        # Test that connect method exists and can be called
        with patch('motor.motor_asyncio.AsyncIOMotorClient'):
            with patch.object(db_manager, '_create_indexes', new_callable=AsyncMock):
                await db_manager.connect()

# ========================================
# WEB SCRAPER TESTS
# ========================================

class TestStockScraper:
    """Test web scraping functionality"""
    
    @pytest.mark.asyncio
    async def test_scraper_initialization(self):
        """Test scraper initialization"""
        scraper = StockScraper()
        
        assert scraper.browser is None
        assert scraper.session is None
        assert isinstance(scraper.headers, dict)
        assert 'User-Agent' in scraper.headers
        assert scraper.store_configs == SUPPORTED_CLUBS
    
    def test_product_info_model(self):
        """Test ProductInfo data model"""
        product_info = ProductInfo(
            name='Test Product',
            price='₪100',
            in_stock=True,
            stock_text='במלאי',
            last_checked='12345'
        )
        
        assert product_info.name == 'Test Product'
        assert product_info.price == '₪100'
        assert product_info.in_stock is True
        assert product_info.stock_text == 'במלאי'
        assert product_info.error_message is None
    
    @pytest.mark.asyncio
    async def test_url_validation(self, mock_scraper):
        """Test URL validation for different stores"""
        scraper = StockScraper()
        
        test_urls = [
            ('https://www.mashkarcard.co.il/product/12345', 'mashkar'),
            ('https://www.hot.net.il/item/67890', 'hot'),
            ('https://corporate.co.il/products/test', 'corporate'),
            ('https://invalid-store.com/product/123', None)  # Should fail
        ]
        
        for url, expected_store in test_urls:
            # This would normally be a method in the scraper
            # Testing the logic that would validate URLs
            parsed = urlparse(url.lower())
            domain = parsed.netloc.replace('www.', '')
            
            found_store = None
            for store_id, store_config in SUPPORTED_CLUBS.items():
                store_domain = urlparse(store_config['base_url']).netloc.replace('www.', '')
                if domain == store_domain:
                    found_store = store_id
                    break
            
            if expected_store:
                assert found_store == expected_store
            else:
                assert found_store is None

# ========================================
# TELEGRAM BOT TESTS
# ========================================

class TestStockTrackerBot:
    """Test Telegram bot functionality"""
    
    def test_bot_initialization(self, mock_db_manager):
        """Test bot initialization"""
        bot = StockTrackerBot(mock_db_manager)
        
        assert bot.db == mock_db_manager
        assert bot.scheduler is None
        assert bot.bot is None
        assert isinstance(bot.rate_limit_cache, dict)
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self, mock_db_manager):
        """Test rate limiting functionality"""
        bot = StockTrackerBot(mock_db_manager)
        user_id = 123456789
        
        # Clear any existing cache
        bot.rate_limit_cache.clear()
        
        # Test within limits
        for i in range(5):  # Well below limit
            result = await bot._check_rate_limit(user_id)
            assert result is True
        
        # Test exceeding limits
        with patch('config.config.RATE_LIMIT_PER_USER', 3):
            # Add enough requests to exceed limit
            current_time = datetime.utcnow()
            bot.rate_limit_cache[user_id] = [current_time] * 4  # Above limit of 3
            
            result = await bot._check_rate_limit(user_id)
            assert result is False
    
    def test_frequency_text_conversion(self, mock_db_manager):
        """Test frequency text conversion helper"""
        bot = StockTrackerBot(mock_db_manager)
        
        test_cases = [
            (10, "כל 10 דקות"),
            (60, "כל שעה"),
            (120, "כל 2 שעות"),
            (1440, "כל יום"),
            (2880, "כל 2 ימים")
        ]
        
        for minutes, expected_text in test_cases:
            result = bot._get_frequency_text(minutes)
            assert result == expected_text
    
    def test_url_validation_helper(self, mock_db_manager):
        """Test URL validation helper method"""
        bot = StockTrackerBot(mock_db_manager)
        
        # Test valid URLs
        valid_urls = [
            'https://www.mashkarcard.co.il/product/12345',
            'https://hot.net.il/item/67890',
            'https://www.corporate.co.il/products/test'
        ]
        
        for url in valid_urls:
            result = bot._validate_url(url)
            assert result is not None
            assert 'store_id' in result
            assert 'name' in result
        
        # Test invalid URL
        invalid_url = 'https://unknown-store.com/product/123'
        result = bot._validate_url(invalid_url)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_stats(self, mock_db_manager):
        """Test bot statistics retrieval"""
        bot = StockTrackerBot(mock_db_manager)
        
        # Mock scheduler
        mock_scheduler = Mock()
        mock_job = Mock()
        mock_job.next_run_time = datetime.utcnow() + timedelta(minutes=30)
        mock_job.id = 'stock_checker'
        mock_scheduler.get_jobs.return_value = [mock_job]
        bot.scheduler = mock_scheduler
        
        stats = await bot.get_stats()
        
        assert 'users' in stats
        assert 'trackings' in stats
        assert 'alerts' in stats
        assert 'next_check' in stats
        assert stats['users']['total'] == 100
        assert stats['trackings']['active'] == 150

# ========================================
# INTEGRATION TESTS
# ========================================

class TestIntegration:
    """Integration tests for component interactions"""
    
    @pytest.mark.asyncio
    async def test_bot_database_integration(self, mock_db_manager, sample_user_data):
        """Test bot and database integration"""
        bot = StockTrackerBot(mock_db_manager)
        
        # Mock user creation
        sample_profile = UserProfile(
            user_id=sample_user_data['id'],
            username=sample_user_data.get('username'),
            first_name=sample_user_data.get('first_name'),
            created_at=datetime.utcnow()
        )
        mock_db_manager.get_or_create_user.return_value = sample_profile
        
        # Test user creation flow
        result = await mock_db_manager.get_or_create_user(sample_user_data)
        assert result.user_id == sample_user_data['id']
        mock_db_manager.get_or_create_user.assert_called_once()
    
    def test_config_bot_integration(self, mock_db_manager):
        """Test configuration and bot integration"""
        bot = StockTrackerBot(mock_db_manager)
        
        # Test that bot uses config values correctly
        assert bot.scraper is not None
        
        # Test that bot has access to all configured stores
        for store_id in SUPPORTED_CLUBS.keys():
            store_config = SUPPORTED_CLUBS[store_id]
            assert 'name' in store_config
            assert 'stock_selector' in store_config

# ========================================
# ERROR HANDLING TESTS
# ========================================

class TestErrorHandling:
    """Test error handling and edge cases"""
    
    @pytest.mark.asyncio
    async def test_database_connection_error(self):
        """Test database connection error handling"""
        db_manager = DatabaseManager()
        
        with patch('motor.motor_asyncio.AsyncIOMotorClient') as mock_client:
            mock_client.side_effect = Exception("Connection failed")
            
            with pytest.raises(Exception):
                await db_manager.connect()
    
    @pytest.mark.asyncio 
    async def test_scraper_timeout_handling(self, mock_scraper):
        """Test scraper timeout handling"""
        mock_scraper.get_product_info.side_effect = asyncio.TimeoutError("Request timeout")
        
        with pytest.raises(asyncio.TimeoutError):
            await mock_scraper.get_product_info("https://test.com", "test_store")
    
    def test_invalid_tracking_status(self):
        """Test invalid tracking status handling"""
        with pytest.raises(ValueError):
            TrackingStatus('invalid_status')
    
    def test_empty_configuration(self):
        """Test handling of empty/missing configuration"""
        # Test with missing environment variables
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                # This should fail because TELEGRAM_TOKEN is required
                from config import BotConfig
                BotConfig()

# ========================================
# UTILITY FUNCTIONS
# ========================================

def create_mock_update(text: str, user_data: dict):
    """Create a mock Telegram update for testing"""
    mock_update = Mock()
    mock_update.message = Mock()
    mock_update.message.text = text
    mock_update.effective_user = Mock()
    
    for key, value in user_data.items():
        setattr(mock_update.effective_user, key, value)
    
    return mock_update

def create_mock_context():
    """Create a mock Telegram context for testing"""
    mock_context = Mock()
    mock_context.bot = Mock()
    mock_context.bot.send_message = AsyncMock()
    return mock_context

# ========================================
# PERFORMANCE TESTS
# ========================================

class TestPerformance:
    """Basic performance and load tests"""
    
    @pytest.mark.slow
    def test_config_loading_performance(self):
        """Test that configuration loading is fast"""
        import time
        
        start_time = time.time()
        
        # Import and initialize config multiple times
        for _ in range(100):
            from config import config, SUPPORTED_CLUBS
            assert config.TELEGRAM_TOKEN
            assert len(SUPPORTED_CLUBS) > 0
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete in under 1 second
        assert duration < 1.0
    
    @pytest.mark.slow
    def test_model_creation_performance(self):
        """Test model creation performance"""
        import time
        
        start_time = time.time()
        
        # Create many model instances
        for i in range(1000):
            tracking = ProductTracking(
                user_id=i,
                product_url=f'https://test.com/product/{i}',
                product_name=f'Product {i}',
                store_name='Test Store',
                store_id='test',
                check_interval=60,
                status=TrackingStatus.ACTIVE
            )
            assert tracking.user_id == i
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete in under 0.5 seconds
        assert duration < 0.5

# ========================================
# PYTEST MARKERS AND HOOKS
# ========================================

def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"  
    )

@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment before each test"""
    # Ensure test environment variables
    os.environ['ENVIRONMENT'] = 'testing'
    os.environ['DEBUG'] = 'true'
    
    yield
    
    # Cleanup after test
    pass

if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
