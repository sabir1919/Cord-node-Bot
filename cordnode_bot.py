# cordnode_bot.py
import aiohttp
import asyncio
import json
from aiohttp_socks import ProxyConnector
from datetime import datetime
import pytz
import os

class CordNodeBot:
    def __init__(self, token, proxy=None, config=None):
        self.token = token
        self.proxy = proxy
        self.config = config or {}
        self.retry_delay = self.config.get("retry_delay_sec", 10)
        self.max_retries = self.config.get("max_retries", 5)
        self.api_key = self.config.get("2captcha_api_key")
        self.claim_interval = self.config.get("claim_interval_sec", 600)
        self.site_key = "0x4AAAAAAANMKl3UyGcySBFP"
        self.site_url = "https://cordnode.xyz"
        self.telegram_token = self.config.get("telegram_bot_token")
        self.telegram_chat_id = self.config.get("telegram_chat_id")
        self.tz = pytz.timezone(self.config.get("timezone", "UTC"))
        self.session = None
        self.username = None

    def timestamp(self):
        now = datetime.now(self.tz)
        return now.strftime("[%Y-%m-%d %H:%M:%S]")

    def log(self, msg):
        prefix = f"[{self.username or self.token[:6]}]"
        full = f"{self.timestamp()} {prefix} {msg}"
        print(full)
        with open("log.txt", "a") as f:
            f.write(full + "\n")
        asyncio.create_task(self.send_telegram(full))

    async def send_telegram(self, message):
        if not self.telegram_token or not self.telegram_chat_id:
            return
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {"chat_id": self.telegram_chat_id, "text": message}
        try:
            async with self.session.post(url, json=payload) as resp:
                if resp.status != 200:
                    print(f"⚠️ Telegram send failed ({resp.status})")
        except Exception as e:
            print(f"⚠️ Telegram error: {e}")

    async def start(self):
        connector = None
        if self.proxy:
            proxy_url = f'socks5://{self.proxy}' if not self.proxy.startswith("http") else f'http://{self.proxy}'
            connector = ProxyConnector.from_url(proxy_url)

        self.session = aiohttp.ClientSession(connector=connector)

        try:
            await self.retry_loop(self.register_node)
            await self.run_claim_loop()
        except Exception as e:
            self.log(f"❌ Fatal error: {e}")
        finally:
            await self.session.close()

    async def retry_loop(self, func):
        for attempt in range(1, self.max_retries + 1):
            try:
                await func()
                return
            except Exception as e:
                self.log(f"⚠️ Retry {attempt}/{self.max_retries} - {e}")
                await asyncio.sleep(self.retry_delay * attempt)
        self.log(f"❌ Failed after {self.max_retries} retries.")

    async def solve_turnstile(self):
        self.log("🔐 Solving Turnstile via 2captcha...")
        data = {
            "key": self.api_key,
            "method": "turnstile",
            "sitekey": self.site_key,
            "pageurl": self.site_url,
            "json": 1
        }

        async with self.session.post("http://2captcha.com/in.php", data=data) as resp:
            result = await resp.json()
            if result.get("status") != 1:
                raise Exception("2Captcha task create failed")
            task_id = result["request"]

        for _ in range(30):
            await asyncio.sleep(5)
            async with self.session.get(f"http://2captcha.com/res.php?key={self.api_key}&action=get&id={task_id}&json=1") as resp:
                result = await resp.json()
                if result.get("status") == 1:
                    self.log("✅ Captcha solved")
                    return result["request"]
        raise Exception("2Captcha timeout")

    async def register_node(self):
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json"
        }

        async with self.session.get("https://discord.com/api/v10/users/@me", headers=headers) as resp:
            if resp.status != 200:
                raise Exception("Invalid Discord token")
            user = await resp.json()

        self.username = f"{user['username']}#{user['discriminator']}"
        self.log("🔓 Logged in successfully")

        snowflake = int(user['id'])
        timestamp = (snowflake >> 22) + 1420070400000
        created_date = datetime.utcfromtimestamp(timestamp / 1000).isoformat()

        captcha_token = await self.solve_turnstile()

        payload = {
            "discord_id": user['id'],
            "username": self.username,
            "account_created": created_date,
            "cf_turnstile_token": captcha_token
        }

        async with self.session.post("https://cordnode.xyz/api/register", json=payload) as resp:
            text = await resp.text()
            self.log(f"📦 Register response: {resp.status} - {text}")

    async def run_claim_loop(self):
        while True:
            try:
                await self.claim()
                await asyncio.sleep(self.claim_interval)
            except Exception as e:
                self.log(f"⚠️ Claim error: {e}")
                await asyncio.sleep(self.retry_delay)

    async def claim(self):
        self.log("⛏️ Attempting to claim rewards...")
        payload = {"token": self.token}

        async with self.session.post("https://cordnode.xyz/api/claim", json=payload) as resp:
            text = await resp.text()
            self.log(f"🎁 Claim response: {resp.status} - {text}")
