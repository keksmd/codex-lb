import aiohttp
import  asyncio
async def main_():
    URL = "https://google.com"
    async with aiohttp.ClientSession( trust_env=True) as session:
        async with session.get(URL,
                               proxy="http://zS2odG:120dbh@161.0.5.119:8000"
                               ) as resp:
            if resp.status != 200:
                logger.warning("GitHub releases API returned HTTP %d", resp.status)
                return None
            data = await resp.json(content_type=None)

if __name__ == "__main__":
    asyncio.run(main_())