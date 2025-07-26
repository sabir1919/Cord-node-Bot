import asyncio
import json
from cordnode_bot import CordNodeBot

async def main():
    with open("nodes.txt") as f:
        tokens = [line.strip() for line in f if line.strip()]

    try:
        with open("proxies.txt") as f:
            proxies = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        proxies = [None] * len(tokens)

    with open("config.json") as f:
        config = json.load(f)

    bots = []
    for i, token in enumerate(tokens):
        proxy = proxies[i % len(proxies)] if proxies else None
        bot = CordNodeBot(token, proxy, config)
        bots.append(bot.start())

    await asyncio.gather(*bots)

if __name__ == "__main__":
    asyncio.run(main())
