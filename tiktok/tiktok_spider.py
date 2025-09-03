import json
import time
import requests
import os
import yt_dlp
import logging
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from tqdm import tqdm

# ====== LOGGING ======
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===== CONFIG =====
OUTPUT_FOLDER = "downloads/tiktok"
WAIT_SCROLL = 10


def download_file(url, filename, folder=OUTPUT_FOLDER):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        logging.info(f"Saved file: {path}")
        return path
    else:
        logging.error(f"Failed to download {url}")
        return None


def download_video(link, folder=OUTPUT_FOLDER):
    os.makedirs(folder, exist_ok=True)
    ydl_opts = {
        "retries": 5,
        "socket_timeout": 60,
        "outtmpl": f"{folder}/%(id)s.%(ext)s",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([link])
    logging.info(f"Downloaded video: {link}")
    return True

def save_progress(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    logging.info(f"✅ Saved {len(data['videos'])} total videos to {path}")


class TikTokCrawler:
    def crawl(self, profile=None, hashtag=None, limit=None, save_json=True):
        """Crawl TikTok profile or hashtag (scroll until limit reached or until no more found)"""

        if hashtag:
            url = f"https://www.tiktok.com/tag/{hashtag}"
            is_hashtag = True
            target = hashtag
        elif profile:
            url = f"https://www.tiktok.com/@{profile}"
            is_hashtag = False
            target = profile
        else:
            logging.error("You must provide either profile or hashtag")
            return

        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        driver = webdriver.Chrome(options=options)

        logging.info(f"Opening URL: {url}")
        driver.get(url)
        time.sleep(10)

        driver.refresh()
        time.sleep(10)

        json_file = os.path.join(
            OUTPUT_FOLDER, f"{target}_{'hashtag' if is_hashtag else 'profile'}.json"
        )

        existing_data = {"target": target, "type": "hashtag" if is_hashtag else "profile", "videos": []}
        existing_links = set()
        if os.path.exists(json_file):
            with open(json_file, "r", encoding="utf-8") as f:
                try:
                    existing_data = json.load(f)
                    existing_links = {v["link"] for v in existing_data.get("videos", [])}
                    logging.info(f"Loaded {len(existing_links)} existing videos from {json_file}")
                except Exception as e:
                    logging.warning(f"Could not load existing JSON ({e}), starting fresh")

        data = existing_data

        # --- Crawl loop ---
        new_videos = 0
        last_height = driver.execute_script("return document.body.scrollHeight")

        # tqdm progress bar (only if limit set, otherwise we show per-video log)
        pbar = tqdm(total=limit, desc="Crawling videos", unit="vid") if limit else None
        thumbnail_dir = os.path.join(OUTPUT_FOLDER, target, "thumbnails")
        video_dir = os.path.join(OUTPUT_FOLDER, target, "videos")

        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(WAIT_SCROLL)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                logging.info("No more new videos loaded, stopping crawl.")
                break
            last_height = new_height

            videos = driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/']")
            logging.info(f"Collected {len(videos)} potential videos so far...")

            for video in videos:
                link = video.get_attribute("href")
                if not link or '/video/' not in link:
                    continue
                if link in existing_links:
                    continue

                try:
                    img_element = video.find_element(By.TAG_NAME, "img")

                    driver.execute_script("arguments[0].scrollIntoView(true);", img_element)
                    time.sleep(1)  # give time for lazy load

                    thumbnail = img_element.get_attribute("src") or img_element.get_attribute("srcset")
                    title = img_element.get_attribute("alt") or "(No caption)"
                except:
                    thumbnail, title = None, "(No caption)"

                video_info = {
                    "index": len(data["videos"]) + 1,
                    "title": title,
                    "link": link,
                    "thumbnail": thumbnail,
                }

                # Per-post progress handler
                logging.info(f"▶ Processing video {video_info['index']}...")

                match = re.search(r"/video/(\d+)", link)
                if not match:
                    return None
                video_id = match.group(1)

                if thumbnail and thumbnail.startswith("http"):
                    download_file(thumbnail, f"thumb_{video_id}.jpg", thumbnail_dir)

                is_video_download = False
                while not is_video_download:
                    try:
                        is_video_download = download_video(link, video_dir)
                    except Exception as e:
                        logging.warning(f"yt-dlp failed for {link}: {e}")

                data["videos"].append(video_info)
                existing_links.add(link)
                new_videos += 1

                logging.info(f"✅ Added video {video_info['index']}: {link}")
                if save_json:
                    save_progress(data, json_file)

                if pbar:
                    pbar.update(1)

                # stop if limit reached
                if limit and new_videos >= limit:
                    break

            if limit and new_videos >= limit:
                break

        if pbar:
            pbar.close()
        driver.quit()

        return data

