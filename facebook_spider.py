#!/usr/bin/env python
"""
Standalone Facebook Hashtag Spider
Không phụ thuộc vào bigdata_* modules gốc
"""

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


# ========== MOCK DATA MODELS ==========
class MockFacebook:
    """Mock Facebook model để thay thế bigdata_backend.postgres_models.facebook"""

    class Field:
        def __init__(self, name):
            self.name = name

    kwrd = Field("keyword")
    feed_url = Field("url")
    publish_date = Field("publish_date")
    content = Field("content")


# ========== LOGGER SETUP ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s|%(levelname)s|%(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


# ========== SELENIUM CALLBACK ==========
def click_allowed_cookies_button(driver):
    """
    Selenium callback để xử lý popup cookies
    """
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
                logger.info(f"Clicked cookie button: {label}")
                break
        except TimeoutException:
            logger.warning(f"Timeout waiting for cookie button: {label}")
            pass


# ========== MAIN SPIDER ==========
class FacebookHashtagSpider(scrapy.Spider):
    name = "facebook_hashtag"

    # XPath selectors
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
        logger.info(f"Found {len(articles)} articles")

        for article in articles:
            if fb_article := self.parse_article(article):
                self.upload_callback(fb_article)
        time.sleep(10)

    def parse_article(self, article):
        article_header = article.xpath(self.article_header_xpath)
        publish_date = article_header.xpath("./@aria-label").get()
        article_url = article_header.xpath("./@href").get()
        descriptions = article.xpath(self.description_xpath).getall()
        description = " ".join(descriptions).strip()

        if article_url and description:
            logger.info(
                "Collected facebook article: pub_dt: %s, url: %s",
                publish_date,
                article_url,
            )
            return {
                MockFacebook.kwrd.name: self.keyword,
                MockFacebook.feed_url.name: article_url,
                MockFacebook.publish_date.name: publish_date,
                MockFacebook.content.name: description,
            }
        return None


# ========== SELENIUM MIDDLEWARE SIMPLIFIED ==========
def get_selenium_settings():
    """
    Tạo settings cho Scrapy với Selenium middleware
    """
    return {
        "USER_AGENT": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "CONCURRENT_REQUESTS": 1,
        "DOWNLOAD_DELAY": 5,
        "RETRY_ENABLED": False,
        "ROBOTSTXT_OBEY": False,
        "LOG_LEVEL": logging.INFO,
        # Selenium settings
        "HEADLESS": False,  # Set True để ẩn browser
        "SELENIUM_DRIVER_NAME": "chrome",
        # Custom downloader middleware (sẽ cần implement)
        "DOWNLOADER_MIDDLEWARES": {
            'facebook_spider.SimpleSeleniumMiddleware': 800,
        },
    }


# ========== SIMPLE SELENIUM MIDDLEWARE ==========


class SimpleSeleniumMiddleware:
    """
    Middleware đơn giản để tích hợp Selenium với Scrapy
    """

    def __init__(self):
        self.driver = None

    def process_request(self, request, spider):
        """Process request with Selenium"""
        if not self.driver:
            self._init_driver(spider)

        self.driver.get(request.url)

        # Execute callback if provided
        if 'callback' in request.meta:
            callback_func = request.meta['callback']
            if callable(callback_func):
                callback_func(self.driver)

        # Wait for page to load
        time.sleep(3)

        # Return Scrapy response
        body = self.driver.page_source
        return HtmlResponse(
            url=request.url,
            body=body,
            encoding='utf-8',
            request=request
        )

    def _init_driver(self, spider):
        """Initialize Chrome driver"""
        chrome_options = Options()

        # Get headless setting from spider settings
        settings = spider.settings
        if settings.getbool('HEADLESS', True):
            chrome_options.add_argument('--headless')

        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')

        # Use webdriver-manager to handle driver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

        logger.info("Chrome driver initialized")

    def spider_closed(self, spider):
        """Clean up driver when spider closes"""
        if self.driver:
            self.driver.quit()
            logger.info("Chrome driver closed")


# ========== TEST FUNCTIONS ==========
def test_callback(data):
    """Callback function để xử lý dữ liệu crawl được"""
    print("=" * 50)
    print("DATA CRAWLED:")
    print(f"Keyword: {data.get('keyword', 'N/A')}")
    print(f"URL: {data.get('url', 'N/A')}")
    print(f"Publish Date: {data.get('publish_date', 'N/A')}")
    content = data.get('content', 'N/A')
    print(f"Content: {content[:100]}..." if len(
        content) > 100 else f"Content: {content}")
    print("=" * 50)


def run_facebook_spider(keyword="test"):
    """Chạy Facebook spider với keyword cụ thể"""
    print(f"Starting Facebook spider with keyword: {keyword}")

    # URL to crawl
    start_urls = [f"https://www.facebook.com/hashtag/{keyword}"]

    # Settings
    settings = get_selenium_settings()

    try:
        # Create process
        process = CrawlerProcess(settings=settings)

        # Crawl
        process.crawl(
            FacebookHashtagSpider,
            keyword=keyword,
            upload_callback=test_callback,
            start_urls=start_urls,
        )

        # Start crawling
        process.start()

        print("Spider completed successfully!")

    except Exception as e:
        print(f"Error running spider: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys

    # Get keyword from command line or use default
    keyword = sys.argv[1] if len(sys.argv) > 1 else "AI"

    print("Standalone Facebook Spider")
    print(f"Keyword: {keyword}")
    print("Starting in 3 seconds...")

    time.sleep(3)
    run_facebook_spider(keyword)
