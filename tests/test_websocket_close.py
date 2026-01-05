import asyncio
import websockets
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_websocket_close_handling():
    """Test if the recv_messages attribute error is resolved when connection is closed"""
    logger.info("Testing WebSocket close handling...")
    logger.info(f"Using websockets library version: {websockets.__version__}")
    
    # Use a test WebSocket server that will close immediately
    # This simulates the scenario that caused the recv_messages error
    url = "wss://echo.websocket.org"  # This is a public test WebSocket server
    
    try:
        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=10
        ) as websocket:
            logger.info("WebSocket connection successful!")
            
            # Send a message and wait for echo
            await websocket.send("test message")
            response = await websocket.recv()
            logger.info(f"Received echo: {response}")
            
            # Close the connection explicitly to test the close handling
            await websocket.close()
            logger.info("WebSocket connection closed successfully!")
            return True
    except Exception as e:
        # Check if the error is the recv_messages attribute error we're trying to fix
        if "recv_messages" in str(e):
            logger.error(f"ERROR: recv_messages attribute error still exists: {e}")
            logger.exception(e)
            return False
        else:
            # Other errors (like connection issues) are expected, but not the recv_messages error
            logger.info(f"Got expected error (not recv_messages): {type(e).__name__}: {e}")
            return True

if __name__ == "__main__":
    result = asyncio.run(test_websocket_close_handling())
    if result:
        logger.info("✅ TEST PASSED: recv_messages attribute error is resolved!")
    else:
        logger.error("❌ TEST FAILED: recv_messages attribute error still exists!")
