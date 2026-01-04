
import asyncio
import ccxt.async_support as ccxt

async def main():
    exchange = ccxt.binance({
        'options': {'defaultType': 'future'}
    })
    await exchange.load_markets()
    
    # Check for likely candidates
    candidates = [
        'fapiPublic_get_klines',
        'fapi_public_get_klines',
        'fapiPublicGetKlines',
        'public_get_klines',
        'fetch_ohlcv'
    ]
    
    print("Checking methods...")
    for c in candidates:
        if hasattr(exchange, c):
            print(f"FOUND: {c}")
        else:
            print(f"MISSING: {c}")
            
    # Also print all attributes starting with fapi
    print("\nAll 'fapi' attributes:")
    for d in dir(exchange):
        if 'fapi' in d and 'klines' in d.lower():
            print(d)

    await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
