import logging
import time
import datetime
import os
import json
import requests
import yt_dlp
import queue
from threading import Thread
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ====== LOGGING ======
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===== CONFIG =====
OUTPUT_FOLDER = "downloads/tiktok"
WAIT_SCROLL = 3
MAX_IDLE_MINUTES = 5
SCROLL_TIMEOUT = 30  # minutes
ELEMENT_TIMEOUT = 10
MAX_RETRIES = 3
VIDEO_DOWNLOAD_TIMEOUT = 60


# ========= UTILS ========= #


def save_video_entry(json_file, video_info, target, is_hashtag):
    """Save a video entry to JSON immediately after download"""
    data = {"target": target, "type": "hashtag" if is_hashtag else "profile", "videos": []}

    if os.path.exists(json_file):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            logging.warning(f"⚠️ Corrupted JSON file, starting fresh: {json_file}")

    existing_links = {v["link"] for v in data["videos"]}
    if video_info["link"] in existing_links:
        return None  # Duplicate

    video_info["index"] = len(data["videos"]) + 1
    data["videos"].append(video_info)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    logging.info(f"💾 Saved video {video_info['index']} to JSON")
    return video_info["index"]


def download_file_with_timeout(url, filename, folder, timeout=30):
    """Download file with timeout (e.g., thumbnails)"""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)

    try:
        r = requests.get(url, stream=True, timeout=timeout)
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        logging.info(f"Saved: {path}")
        return path
    except Exception as e:
        logging.error(f"❌ Failed to download {url}: {e}")
        return None


def download_video_threaded(link, folder, timeout=VIDEO_DOWNLOAD_TIMEOUT):
    """Download video using yt-dlp in a thread (with timeout)"""

    def worker(url, folder, result_queue):
        try:
            os.makedirs(folder, exist_ok=True)
            ydl_opts = {
                "outtmpl": f"{folder}/%(id)s.%(ext)s",
                "quiet": True,
                "socket_timeout": 30,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            result_queue.put(("success", f"Downloaded {url}"))
        except Exception as e:
            result_queue.put(("error", str(e)))

    result_queue = queue.Queue()
    thread = Thread(target=worker, args=(link, folder, result_queue), daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        logging.warning(f"⏳ Timeout downloading {link}")
        return False

    try:
        status, msg = result_queue.get_nowait()
        if status == "success":
            logging.info(msg)
            return True
        else:
            logging.warning(f"yt-dlp error: {msg}")
            return False
    except queue.Empty:
        logging.warning(f"No result from downloader for {link}")
        return False


# ========= MAIN CRAWLER ========= #
class TikTokCrawler:
    def __init__(self):
        self.driver = None
        self.wait = None

    # ---------- DRIVER ---------- #
    def setup_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--page-load-strategy=eager")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(30)
        self.wait = WebDriverWait(self.driver, ELEMENT_TIMEOUT)

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
                logging.info("🔒 Browser closed")
            except Exception as e:
                logging.warning(f"Error closing driver: {e}")

    # ---------- HELPERS ---------- #
    def _scroll_to_load_more(self):
        """Smart scrolling strategies to trigger new content"""
        try:
            current_height = self.driver.execute_script("return document.body.scrollHeight")
            for pos in [0.7, 0.85, 1.0]:
                self.driver.execute_script(f"window.scrollTo(0, {int(current_height * pos)});")
                time.sleep(1)
            time.sleep(3)
        except Exception as e:
            logging.warning(f"Scroll failed: {e}")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(WAIT_SCROLL)

    # ---------- MAIN FLOW ---------- #
    def crawl(self, profile=None, hashtag=None, limit=None):
        if not (profile or hashtag):
            logging.error("Provide either profile or hashtag")
            return None

        target = hashtag or profile
        is_hashtag = bool(hashtag)
        url = f"https://www.tiktok.com/tag/{target}" if is_hashtag else f"https://www.tiktok.com/@{target}"
        target_folder = os.path.join(OUTPUT_FOLDER, target)
        json_file = os.path.join(OUTPUT_FOLDER, f"{target}_{'hashtag' if is_hashtag else 'profile'}.json")
        os.makedirs(target_folder, exist_ok=True)

        try:
            self.setup_driver()
            logging.info(f"🚀 Crawling: {url}")
            self.driver.get(url)
            time.sleep(5)

            existing_links = set()
            if os.path.exists(json_file):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                        existing_links = {v["link"] for v in existing_data.get("videos", [])}
                        logging.info(f"📚 Loaded {len(existing_links)} existing videos")
                except Exception as e:
                    logging.warning(f"Could not read JSON ({e}), starting fresh")

            new_videos, retries, last_count, no_new = 0, 0, 0, 0
            MAX_NO_NEW = 5
            start_time = datetime.datetime.now()

            while True:
                # stop if global timeout
                if (datetime.datetime.now() - start_time).total_seconds() > SCROLL_TIMEOUT * 60:
                    logging.warning("⏳ Global timeout reached")
                    break

                try:
                    videos = self.wait.until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/video/']"))
                    )
                except TimeoutException:
                    retries += 1
                    if retries >= MAX_RETRIES:
                        logging.error("❌ No more videos found after retries")
                        break
                    logging.warning(f"⚠️ No videos found, retry {retries}/{MAX_RETRIES}")
                    self._scroll_to_load_more()
                    continue

                if len(videos) == last_count:
                    no_new += 1
                    if no_new >= MAX_NO_NEW:
                        logging.info("🏁 End of content")
                        break
                    self._scroll_to_load_more()
                    continue

                last_count, no_new = len(videos), 0
                for video in videos:
                    link = video.get_attribute("href")
                    if not link or link in existing_links:
                        continue

                    try:
                        img = video.find_element(By.TAG_NAME, "img")
                        title = img.get_attribute("alt") or "(No caption)"
                        thumbnail = img.get_attribute("src") or img.get_attribute("srcset")
                    except NoSuchElementException:
                        title, thumbnail = "(No caption)", None

                    video_info = {
                        "title": title,
                        "link": link,
                        "thumbnail": thumbnail,
                        "download_date": datetime.datetime.now().isoformat()
                    }

                    if download_video_threaded(link, target_folder):
                        idx = save_video_entry(json_file, video_info, target, is_hashtag)
                        if idx:
                            if thumbnail and thumbnail.startswith("http"):
                                download_file_with_timeout(thumbnail, f"thumb_{idx}.jpg", target_folder, 15)
                            existing_links.add(link)
                            new_videos += 1
                            if limit and new_videos >= limit:
                                logging.info(f"🎯 Reached limit {limit}")
                                return {"total_new_videos": new_videos, "target": target}
                self._scroll_to_load_more()

            logging.info(f"🏆 Done. Total new videos: {new_videos}")
            return {"total_new_videos": new_videos, "target": target}

        except Exception as e:
            logging.error(f"💥 Crawl failed: {e}")
            return None
        finally:
            self.close_driver()
