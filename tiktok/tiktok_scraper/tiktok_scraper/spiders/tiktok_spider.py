import scrapy, os, re, time, json, logging
from scrapy_selenium import SeleniumRequest
from selenium.webdriver.common.by import By

from ..items import TikTokVideo
from ..utils import download_file, download_video, save_progress, OUTPUT_FOLDER

WAIT_SCROLL = 10


class TikTokSpider(scrapy.Spider):
    name = "tiktok"

    def __init__(self, profile=None, hashtag=None, limit=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not profile and not hashtag:
            raise ValueError("❌ Must provide either profile or hashtag")

        self.profile = profile
        self.hashtag = hashtag
        self.limit = int(limit) if limit else None
        self.target = hashtag if hashtag else profile
        self.is_hashtag = bool(hashtag)

        # Prepare JSON path
        self.json_file = os.path.join(
            OUTPUT_FOLDER, f"{self.target}_{'hashtag' if self.is_hashtag else 'profile'}.json"
        )

        # Load existing data
        self.data = {"target": self.target, "type": "hashtag" if self.is_hashtag else "profile", "videos": []}
        self.existing_links = set()
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                    self.existing_links = {v["link"] for v in self.data.get("videos", [])}
                    logging.info(f"📂 Loaded {len(self.existing_links)} existing videos from {self.json_file}")
            except Exception as e:
                logging.warning(f"⚠️ Could not load existing JSON ({e}), starting fresh")

        self.new_videos = 0

    def start_requests(self):
        if self.hashtag:
            url = f"https://www.tiktok.com/tag/{self.hashtag}"
        else:
            url = f"https://www.tiktok.com/@{self.profile}"

        yield SeleniumRequest(url=url, callback=self.parse_page)

    def parse_page(self, response):
        driver = response.meta.get("driver")
        if not driver:
            self.logger.error("❌ No Selenium driver found in response.meta")
            return

        thumbnail_dir = os.path.join(OUTPUT_FOLDER, self.target, "thumbnails")
        video_dir = os.path.join(OUTPUT_FOLDER, self.target, "videos")

        last_height = driver.execute_script("return document.body.scrollHeight")

        while not self.limit or self.new_videos < self.limit:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(WAIT_SCROLL)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                logging.info("🚫 No more new videos loaded, stopping crawl.")
                break
            last_height = new_height

            videos = driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/']")
            for video in videos:
                link = video.get_attribute("href")
                if not link or "/video/" not in link or link in self.existing_links:
                    continue

                try:
                    img_element = video.find_element(By.TAG_NAME, "img")
                    driver.execute_script("arguments[0].scrollIntoView(true);", img_element)
                    time.sleep(1)
                    thumbnail = img_element.get_attribute("src") or img_element.get_attribute("srcset")
                    title = img_element.get_attribute("alt") or "(No caption)"
                except:
                    thumbnail, title = None, "(No caption)"

                match = re.search(r"/video/(\d+)", link)
                if not match:
                    continue
                video_id = match.group(1)

                video_info = {
                    "index": len(self.data["videos"]) + 1,
                    "title": title,
                    "link": link,
                    "thumbnail": thumbnail,
                }

                logging.info(f"▶ Processing video {video_info['index']} {link}")

                if thumbnail and thumbnail.startswith("http"):
                    download_file(thumbnail, f"thumb_{video_id}.jpg", thumbnail_dir)

                success = False
                while not success:
                    try:
                        success = download_video(link, video_dir)
                    except Exception as e:
                        logging.warning(f"yt-dlp failed for {link}: {e}")

                self.data["videos"].append(video_info)
                self.existing_links.add(link)
                self.new_videos += 1

                save_progress(self.data, self.json_file)

                yield TikTokVideo(**video_info)

                if self.limit and self.new_videos >= self.limit:
                    logging.info(f"✅ Reached limit {self.limit}, stopping.")
                    return
