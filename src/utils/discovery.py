
import asyncio
import ccxt.async_support as ccxt
from typing import Set, List, Dict
from src.utils.logger import logger

class SymbolDiscovery:
    def __init__(self):
        self.exchanges = {
            'binance': ccxt.binance(),
            'okx': ccxt.okx(),
            'bybit': ccxt.bybit(),
            'coinbase': ccxt.coinbase()
        }

    async def fetch_symbols(self, exchange_id: str, exchange) -> Set[str]:
        try:
            await exchange.load_markets()
            symbols = set()
            for s in exchange.symbols:
                # Filter for USDT pairs (linear futures or spot depending on preference, 
                # but let's stick to standard format like BTC/USDT)
                # Note: Coinbase uses USD mostly, not USDT for many pairs, but has USDT books.
                # However, our connectors mapped things. 
                # Let's standardize: Base/USDT.
                if '/USDT' in s:
                    symbols.add(s)
                elif exchange_id == 'coinbase' and '/USD' in s:
                     # Coinbase often has USD pairs. We might map them if we want broader coverage
                     # But our current system heavily implies USDT standardization.
                     # Let's check if Coinbase has USDT pairs.
                     if '/USDT' in s:
                         symbols.add(s)
            
            logger.info(f"[{exchange_id}] Found {len(symbols)} USDT pairs")
            return symbols
        except Exception as e:
            logger.error(f"[{exchange_id}] Failed to fetch symbols: {e}")
            return set()
        finally:
            await exchange.close()

    async def get_common_symbols(self) -> List[str]:
        tasks = []
        for name, ex in self.exchanges.items():
            tasks.append(self.fetch_symbols(name, ex))
        
        results = await asyncio.gather(*tasks)
        
        # Intersection
        common = set(results[0])
        for res in results[1:]:
            if res:
               common &= res
               
        # Sort? Maybe by alphabetical for now. 
        # Ideally by volume but that requires fetching tickers.
        sorted_symbols = sorted(list(common))
        logger.info(f"✅ Found {len(sorted_symbols)} common symbols across all 4 platforms.")
        return sorted_symbols

if __name__ == "__main__":
    sd = SymbolDiscovery()
    loop = asyncio.get_event_loop()
    common = loop.run_until_complete(sd.get_common_symbols())
    print("\nCommon Symbols:")
    print(", ".join(common))
