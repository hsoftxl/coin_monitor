import asyncio
import websockets
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_websocket_connection():
    """Test WebSocket connection to Binance"""
    # Simple Binance WebSocket URL for a single symbol
    url = "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"
    
    logger.info("Testing WebSocket connection...")
    logger.info(f"Using websockets library version: {websockets.__version__}")
    
    try:
        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=10
        ) as websocket:
            logger.info("WebSocket connection successful!")
            
            # Receive 5 messages to verify connection is working
            for i in range(5):
                message = await asyncio.wait_for(websocket.recv(), timeout=30)
                logger.info(f"Received message {i+1}: {message[:100]}...")
            
            logger.info("WebSocket test completed successfully!")
            return True
    except Exception as e:
        logger.error(f"WebSocket test failed: {e}")
        logger.exception(e)
        return False

if __name__ == "__main__":
    asyncio.run(test_websocket_connection())
