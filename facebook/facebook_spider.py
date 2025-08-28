#!/usr/bin/env python

from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from scrapy.http import HtmlResponse
import time
import logging
from typing import Any, Iterable

import scrapy
from scrapy.http import HtmlResponse, Request
from scrapy.crawler import CrawlerProcess
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .mock_models import MockFacebook
from .time_parser import parse_relative_time
from .selenium_config import get_selenium_settings, get_chrome_options
from .media_extractor import extract_images_from_article


logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

logging.getLogger('selenium').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('webdriver_manager').setLevel(logging.ERROR)
logging.getLogger('scrapy').setLevel(logging.ERROR)


def click_allowed_cookies_button(driver):
    labels = ["모든 쿠키 허용", "Allow all cookies"]

    for label in labels:
        allowed_cookies_button_xpath = (
            ".//div[@role='button' "
            f"and @aria-label='{label}' "
            "and not(@aria-disabled)]"
        )
        try:
            if button := WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, allowed_cookies_button_xpath)
                )
            ):
                button.click()
                break
        except TimeoutException:
            pass


class FacebookHashtagSpider(scrapy.Spider):
    name = "facebook_hashtag"

    cookies_allowed_button_xpath = (
        ".//div[@role='button' ",
        "and @aria-label='Allow all cookies' and not(@aria-disabled)]",
    )
    articles_xpath = "//div[@role='article']/div"
    description_xpath = (
        ".//div[@data-ad-comet-preview='message']//span[@dir='auto']//text()"
    )
    article_header_xpath = (
        ".//div//span/a[@aria-label!='확대하기' and @role='link']"
    )

    def __init__(self, keyword, upload_callback, *args, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.keyword = keyword
        self.upload_callback = upload_callback

    def start_requests(self) -> Iterable[Request]:
        """Deprecated method - use start() instead"""
        for url in self.start_urls:
            yield Request(
                url,
                callback=self.parse,
                meta={
                    "callback": click_allowed_cookies_button,
                },
                dont_filter=True,
            )

    async def start(self):
        """New async start method for Scrapy 2.13+"""
        for url in self.start_urls:
            yield Request(
                url,
                callback=self.parse,
                meta={
                    "callback": click_allowed_cookies_button,
                },
                dont_filter=True,
            )

    def parse(self, response: HtmlResponse) -> dict:
        # Take ONE screenshot of the entire Facebook hashtag page
        driver = response.request.meta.get('driver')
        page_screenshot_path = None
        if driver:
            print("📸 Taking full page screenshot...")
            from .media_extractor import screenshot_full_page
            page_screenshot_path = screenshot_full_page(
                driver, save_dir="downloads/facebook")
            print(f"📊 Captured full page screenshot: {page_screenshot_path}")

        articles = response.xpath(self.articles_xpath)

        for article in articles:
            # All articles will use the same full page screenshot
            if fb_article := self.parse_article(article, response, page_screenshot_path):
                self.upload_callback(fb_article)
        time.sleep(10)

    def parse_article(self, article, response, screenshot_path=None):
        url_selectors = [
            ".//div//span/a[@aria-label!='확대하기' and @role='link']/@href",
            ".//a[contains(@href, '/posts/')]/@href",
            ".//a[contains(@href, '/stories/')]/@href",
            ".//a[contains(@href, '/reel/')]/@href",
            ".//a[contains(@href, '/photo/')]/@href",
            ".//a[@role='link'][1]/@href",
            ".//a[1]/@href",
        ]

        article_url = None
        for selector in url_selectors:
            urls = article.xpath(selector).getall()
            if urls:
                article_url = urls[0]
                break

        if article_url and article_url.startswith('/'):
            article_url = f"https://www.facebook.com{article_url}"

        article_header = article.xpath(self.article_header_xpath)
        publish_date = article_header.xpath("./@aria-label").get()
        descriptions = article.xpath(self.description_xpath).getall()
        description = " ".join(descriptions).strip()

        actual_timestamp = None
        if article_url and description:
            all_texts = article.xpath(".//text()").getall()
            filtered_texts = [text.strip()
                              for text in all_texts if text.strip()]

            import re
            patterns = [
                r'\b\d+\s*[mhdwy](?:[a-z]*)?(?:\s+ago)?\b',
                r'\b\d+\s+(?:min|hour|day|week|month|year)s?(?:\s+ago)?\b',
                r'\b(?:yesterday|today)\b',
                r'\b(?:just now|a moment ago)\b',
                r'\b\d+\s*[分時日週月年](?:前|ago)?\b',
                r'\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\b',
                r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\b',
                r'\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b',
                r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\b',
            ]

            for text in filtered_texts:
                text_lower = text.lower()
                for pattern in patterns:
                    if re.search(pattern, text_lower):
                        parsed_time = parse_relative_time(text)
                        if parsed_time:
                            actual_timestamp = parsed_time
                            break
                if actual_timestamp:
                    break

            if not actual_timestamp:
                from datetime import datetime, timezone
                actual_timestamp = datetime.now(timezone.utc)

        if article_url and description:
            # Extract ALL images including hidden gallery images
            driver = response.request.meta.get('driver')
            images = []

            if driver:
                # Convert Scrapy selector to WebElement for advanced image extraction
                try:
                    # Find the corresponding WebElement for this article
                    web_articles = driver.find_elements(
                        By.XPATH, "//div[@role='article']")
                    article_index = self.get_article_index(article, response)

                    if 0 <= article_index < len(web_articles):
                        article_web_element = web_articles[article_index]

                        # Use new comprehensive image extraction
                        from .media_extractor import extract_all_images_from_facebook_post
                        downloaded_paths = extract_all_images_from_facebook_post(
                            driver, article_web_element, save_dir="image_downloads"
                        )
                        images.extend(downloaded_paths)

                        print(
                            f"🎯 Extracted {len(downloaded_paths)} images from post (including galleries)")
                    else:
                        print(
                            f"⚠️  Could not find WebElement for article {article_index}")
                        # Fallback to traditional image extraction
                        images = extract_images_from_article(article)
                        print(
                            f"🔍 Fallback: extracted {len(images)} individual images")

                except Exception as e:
                    print(f"❌ Error in advanced image extraction: {e}")
                    # Fallback to traditional image extraction
                    images = extract_images_from_article(article)
                    print(
                        f"🔍 Fallback: extracted {len(images)} individual images")
            else:
                # Fallback to traditional image extraction if no driver
                images = extract_images_from_article(article)
                print(
                    f"🔍 No driver available: extracted {len(images)} individual images")

            # Also add screenshot as backup
            if screenshot_path:
                images.append(screenshot_path)
                print(f"📸 Added screenshot: {screenshot_path}")

            print(
                f"✓ Crawled: {self.keyword} | Content: {description[:50]}... | Images: {len(images)}")

            if self.upload_callback:
                self.upload_callback({
                    MockFacebook.kwrd.name: self.keyword,
                    MockFacebook.feed_url.name: article_url,
                    MockFacebook.publish_date.name: actual_timestamp,
                    MockFacebook.content.name: description,
                    MockFacebook.images.name: images,
                })

    def get_article_index(self, scrapy_article, response):
        """
        Find the index of Scrapy article selector in the list of all articles

        Args:
            scrapy_article: Scrapy selector for the article
            response: Scrapy response object

        Returns:
            int: Index of the article or -1 if not found
        """
        try:
            # Get all articles from the response
            all_articles = response.xpath(self.articles_xpath)

            # Try to find matching article by comparing some unique attributes
            for i, article in enumerate(all_articles):
                # Compare article content or URLs to find the match
                try:
                    # Compare URLs as unique identifier
                    current_urls = article.xpath(
                        ".//a[contains(@href, '/posts/') or contains(@href, '/photo/')]/@href").getall()
                    target_urls = scrapy_article.xpath(
                        ".//a[contains(@href, '/posts/') or contains(@href, '/photo/')]/@href").getall()

                    if current_urls and target_urls and current_urls[0] == target_urls[0]:
                        return i

                    # Fallback: compare text content
                    current_text = ' '.join(article.xpath(
                        ".//text()").getall()[:10])  # First 10 text nodes
                    target_text = ' '.join(
                        scrapy_article.xpath(".//text()").getall()[:10])

                    if current_text and target_text and current_text == target_text:
                        return i

                except Exception:
                    continue

            return -1  # Not found

        except Exception as e:
            print(f"❌ Error finding article index: {e}")
            return -1


class SimpleSeleniumMiddleware:
    def __init__(self):
        self.driver = None

    def _init_driver(self, spider):
        if self.driver is None:
            chrome_options = get_chrome_options()
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(
                service=service, options=chrome_options)

    def process_request(self, request, spider):
        if self.driver is None:
            self._init_driver(spider)

        self.driver.get(request.url)

        if 'callback' in request.meta:
            callback = request.meta['callback']
            if callback:
                callback(self.driver)

        time.sleep(3)

        body = self.driver.page_source.encode('utf-8')
        response = HtmlResponse(
            url=request.url,
            body=body,
            encoding='utf-8',
            request=request
        )
        # Store driver in request meta for access in parse methods
        request.meta['driver'] = self.driver
        return response

    def spider_closed(self, spider):
        if self.driver:
            self.driver.quit()


def test_callback(data):
    print("\n" + "=" * 80)
    print("📊 CRAWLED DATA:")
    print("=" * 80)
    print(f"🔤 KEYWORD (kwrd): {data.get('keyword', 'N/A')}")
    print(f"🔗 FEED_URL: {data.get('url', 'N/A')}")
    print(f"📅 PUBLISH_DATE: {data.get('publish_date', 'N/A')}")
    content = data.get('content', 'N/A')
    print(f"📝 CONTENT: {content}")

    images = data.get('images', [])
    print(f"🖼️  IMAGES ({len(images)}):")
    for i, img in enumerate(images, 1):
        print(f"  {i}. {img}")

    print("=" * 80)


# =========================================
# Runner class for Fire
# =========================================
class FacebookCrawler:
    def crawl(self, keyword="test"):
        """Crawl Facebook posts by hashtag keyword"""
        logging.info(f"🚀 Starting crawl for: {keyword}")

        start_urls = [f"https://www.facebook.com/hashtag/{keyword}"]
        settings = get_selenium_settings()

        try:
            process = CrawlerProcess(settings)
            process.crawl(
                FacebookHashtagSpider,
                keyword=keyword,
                upload_callback=test_callback,
                start_urls=start_urls
            )
            process.start()
            logging.info("✅ Crawl completed!")
        except Exception as e:
            logging.error(f"❌ Error: {e}")


# =========================================
# Fire entrypoint
# =========================================
if __name__ == "__main__":
    import fire
    fire.Fire(FacebookCrawler)
