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

from mock_models import MockFacebook
from time_parser import parse_relative_time
from selenium_config import get_selenium_settings, get_chrome_options
from media_extractor import extract_images_from_article


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


class FacebookPageSpider(scrapy.Spider):
    name = "facebook_page"

    cookies_allowed_button_xpath = (
        ".//div[@role='button' ",
        "and @aria-label='Allow all cookies' and not(@aria-disabled)]",
    )
    articles_xpath = "//div[@role='article']/div"
    description_xpath = (
        ".//div[@data-ad-comet-preview='message']//span[@dir='auto']//text()"
    )
    # Additional XPath selectors for Facebook pages (different structure)
    page_content_selectors = [
        # Primary selector (works for hashtags)
        ".//div[@data-ad-comet-preview='message']//span[@dir='auto']//text()",
        # Page post content
        ".//div[contains(@class, 'userContent')]//span//text()",
        ".//div[contains(@class, 'text_exposed_root')]//text()",
        # General content in posts
        ".//span[@dir='auto']//text()",
        ".//div[contains(@style, 'text-align')]//text()",
        # Fallback - any text in the article
        ".//text()[normalize-space() and string-length() > 10]"
    ]
    article_header_xpath = (
        ".//div//span/a[@aria-label!='확대하기' and @role='link']"
    )

    def __init__(self, pagename, upload_callback, *args, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.pagename = pagename
        self.upload_callback = upload_callback

    def start_requests(self) -> Iterable[Request]:
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
        articles = response.xpath(self.articles_xpath)

        if len(articles) == 0:
            page_text = response.text
            if any(indicator in page_text for indicator in ["You must log in to continue", "Log Into Facebook"]):
                print("⚠️  Page requires login to view content")
            else:
                print("⚠️  No articles found on this page")

        # Take ONE screenshot of the entire Facebook page
        driver = response.request.meta.get('driver')
        page_screenshot_path = None
        if driver:
            print("📸 Taking full page screenshot...")
            from media_extractor import screenshot_full_page
            page_screenshot_path = screenshot_full_page(
                driver, save_dir="screenshots")
            print(f"📊 Captured full page screenshot: {page_screenshot_path}")

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

        if not article_url:
            return None

        if article_url and article_url.startswith('/'):
            article_url = f"https://www.facebook.com{article_url}"

        article_header = article.xpath(self.article_header_xpath)
        publish_date = article_header.xpath("./@aria-label").get()

        # Try multiple content selectors for different page structures
        description = ""
        for selector in self.page_content_selectors:
            descriptions = article.xpath(selector).getall()
            if descriptions:
                description = " ".join(descriptions).strip()
                break

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
            # Use screenshot as primary "image" instead of extracting individual images
            if screenshot_path:
                # Screenshot contains all visual content
                images = [screenshot_path]
                print(f"📸 Using screenshot: {screenshot_path}")
            else:
                # Fallback to traditional image extraction if no screenshot
                images = extract_images_from_article(article)
                print(f"🔍 Fallback: extracted {len(images)} individual images")

            print(
                f"✓ Crawled: {self.pagename} | Content: {description[:50]}... | Images: {len(images)}")

            if self.upload_callback:
                self.upload_callback({
                    MockFacebook.kwrd.name: self.pagename,
                    MockFacebook.feed_url.name: article_url,
                    MockFacebook.publish_date.name: actual_timestamp,
                    MockFacebook.content.name: description,
                    MockFacebook.images.name: images,
                })


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


def test_callback_page(data):
    print("\n" + "=" * 80)
    print("📊 CRAWLED PAGE DATA:")
    print("=" * 80)
    print(f"🔤 PAGE NAME: {data.get('keyword', 'N/A')}")
    print(f"🔗 FEED_URL: {data.get('url', 'N/A')}")
    print(f"📅 PUBLISH_DATE: {data.get('publish_date', 'N/A')}")
    content = data.get('content', 'N/A')
    print(f"📝 CONTENT: {content}")

    images = data.get('images', [])
    print(f"🖼️  IMAGES ({len(images)}):")
    for i, img in enumerate(images, 1):
        print(f"  {i}. {img}")

    print("=" * 80)


def run_facebook_page_spider(pagename="test"):
    print(f"🚀 Starting crawl for page: {pagename}")

    start_urls = [f"https://www.facebook.com/{pagename}"]

    settings = get_selenium_settings()
    settings["DOWNLOADER_MIDDLEWARES"] = {
        "facebook_spider_page.SimpleSeleniumMiddleware": 585,
    }

    try:
        process = CrawlerProcess(settings)
        process.crawl(
            FacebookPageSpider,
            pagename=pagename,
            upload_callback=test_callback_page,
            start_urls=start_urls
        )
        process.start()
        print("✅ Page crawl completed!")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    import sys

    pagename = "test"
    if len(sys.argv) > 1:
        pagename = sys.argv[1]

    print(f"🔍 Facebook Page Spider - Page: {pagename}")
    time.sleep(1)
    run_facebook_page_spider(pagename)
