import os
import json
import logging
import asyncio
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from tqdm import tqdm

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
    async def _crawl_async(self, channel: str, limit: int = None):
        """Async crawler for Telegram channel messages"""
        client = TelegramClient(None, api_id, api_hash)
        await client.start(phone_number)

        safe_channel = channel.strip().replace("https://t.me/", "").replace("/", "_")
        channel_media_folder = os.path.join(OUTPUT_FOLDER, safe_channel)
        os.makedirs(channel_media_folder, exist_ok=True)

        JSON_FILENAME = os.path.join(OUTPUT_FOLDER, f"{safe_channel}_datas.json")

        existing_messages = []
        messages_data = []
        existing_ids = set()

        if os.path.exists(JSON_FILENAME):
            with open(JSON_FILENAME, "r", encoding="utf-8") as f:
                existing_messages = json.load(f)
                existing_ids = {msg["id"] for msg in existing_messages}
            logging.info(f"Loaded {len(existing_messages)} existing messages from {JSON_FILENAME}")


        def save_progress():
            all_messages = existing_messages + messages_data
            with open(JSON_FILENAME, "w", encoding="utf-8") as f:
                json.dump(all_messages, f, indent=2, ensure_ascii=False)

            if len(messages_data) > 0:
                logging.info(f"💾 Saved {len(messages_data)} new messages")

        async def process_message(message):
            if message.id in existing_ids:
                return

            msg_dict = {
                "id": message.id,
                "date": str(message.date),
                "text": message.text,
                "media_type": None,
                "media_path": None
            }

            # --- helper: tqdm bar for file download ---
            def make_progress_bar(desc, total):
                bar = tqdm(total=total, unit="B", unit_scale=True, desc=desc, leave=False)

                def progress_callback(current, _total):
                    bar.update(current - bar.n)
                    if current >= total:
                        bar.close()

                return progress_callback

            # --- photo ---
            if isinstance(message.media, MessageMediaPhoto):
                msg_dict["media_type"] = "photo"
                file_path = os.path.join(channel_media_folder, f"{message.id}.jpg")

                total = getattr(message.media.photo, "sizes", [None])[-1]
                size = getattr(total, "size", 0) or None

                progress_cb = make_progress_bar(f"Downloading photo {message.id}", size) if size else None
                await client.download_media(message, file=file_path, progress_callback=progress_cb)
                msg_dict["media_path"] = file_path

            # --- document ---
            elif isinstance(message.media, MessageMediaDocument):
                ext = ".bin"
                if message.media.document and message.media.document.mime_type:
                    mime = message.media.document.mime_type
                    if "video" in mime:
                        ext = ".mp4"
                    elif "png" in mime:
                        ext = ".png"
                    elif "jpg" in mime or "jpeg" in mime:
                        ext = ".jpg"
                    elif "gif" in mime:
                        ext = ".gif"
                    elif "pdf" in mime:
                        ext = ".pdf"

                msg_dict["media_type"] = "document"
                file_path = os.path.join(channel_media_folder, f"{message.id}{ext}")

                size = getattr(message.media.document, "size", 0) or None
                progress_cb = make_progress_bar(f"Downloading doc {message.id}", size) if size else None
                await client.download_media(message, file=file_path, progress_callback=progress_cb)
                msg_dict["media_path"] = file_path

            messages_data.append(msg_dict)
            save_progress()

        if limit is None:
            offset_id = 0
            while True:
                batch = []
                async for msg in client.iter_messages(channel, limit=100, offset_id=offset_id):
                    batch.append(msg)
                if not batch:
                    break

                for message in batch:
                    await process_message(message)

                offset_id = batch[-1].id
                logging.info(f"📥 Crawled up to message ID={offset_id}, continuing...")

        else:
            async for message in client.iter_messages(channel, limit=limit):
                await process_message(message)
            logging.info(f"📥 Crawled {limit} lastest messages")


        logging.info("✅ Crawl finished.")

    def crawl(self, channel: str, limit: int = None):
        asyncio.run(self._crawl_async(channel, limit))


class SpiderCrawler:
    def telegram(self, channel=None, limit=None):
        """Crawl Telegram"""
        TelegramCrawler().crawl(channel=channel, limit=limit)


## sender_id is redundant, since in a channel, only the founder can send message

## if json file is open while crawling -> cannot override and raise error, also stop crawling process

