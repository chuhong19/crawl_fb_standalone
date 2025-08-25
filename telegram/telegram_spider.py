import os
import json
import logging
import asyncio
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

# ====== LOGGING ======
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===== CONFIG =====
api_id = 18907678
api_hash = "251e195c220d85782f653060052734d1"
phone_number = "+84823503786"

OUTPUT_FOLDER = "downloads/telegram"


class TelegramCrawler:
    async def _crawl_async(self, channel: str, limit: int = 50):
        """Async crawler for Telegram channel messages"""
        client = TelegramClient(None, api_id, api_hash)
        await client.start(phone_number)

        safe_channel = channel.strip().replace("https://t.me/", "").replace("/", "_")
        channel_media_folder = os.path.join(OUTPUT_FOLDER, safe_channel)
        os.makedirs(channel_media_folder, exist_ok=True)

        JSON_FILENAME = os.path.join(OUTPUT_FOLDER, f"{safe_channel}_datas.json")

        existing_messages = []
        existing_ids = set()
        if os.path.exists(JSON_FILENAME):
            with open(JSON_FILENAME, "r", encoding="utf-8") as f:
                existing_messages = json.load(f)
                existing_ids = {msg["id"] for msg in existing_messages}
            logging.info(f"Loaded {len(existing_messages)} existing messages from {JSON_FILENAME}")

        messages_data = []

        async for message in client.iter_messages(channel, limit=limit):
            if message.id in existing_ids:
                logging.info(f"⏭️ Skipping duplicate message ID={message.id}")
                continue

            logging.info(f"Fetched new message ID={message.id} | text={(message.text or '')[:50]}")

            msg_dict = {
                "id": message.id,
                "date": str(message.date),
                "text": message.text,
                "sender_id": message.sender_id,
                "media_type": None,
                "media_path": None
            }

            if isinstance(message.media, MessageMediaPhoto):
                msg_dict["media_type"] = "photo"
                file_path = await client.download_media(message, file=channel_media_folder)
                msg_dict["media_path"] = file_path
                logging.info(f"Downloaded photo → {file_path}")

            elif isinstance(message.media, MessageMediaDocument):
                msg_dict["media_type"] = "document"
                file_path = await client.download_media(message, file=channel_media_folder)
                msg_dict["media_path"] = file_path
                logging.info(f"Downloaded document → {file_path}")

            messages_data.append(msg_dict)

        all_messages = existing_messages + messages_data

        with open(JSON_FILENAME, "w", encoding="utf-8") as f:
            json.dump(all_messages, f, indent=2, ensure_ascii=False)

        logging.info(f"✅ Saved {len(all_messages)} total messages ({len(messages_data)} new) to {JSON_FILENAME}")

    def crawl(self, channel: str, limit: int = 50):
        """
        Crawl a Telegram channel.

        Args:
            channel (str): Telegram channel name or link
            limit (int): Number of messages to fetch (default=50)
        """
        asyncio.run(self._crawl_async(channel, limit))
