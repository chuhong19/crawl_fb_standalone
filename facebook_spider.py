#!/usr/bin/env python
"""
Standalone Facebook Hashtag Spider
Không phụ thuộc vào bigdata_* modules gốc
"""

import os
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
# Tắt hoàn toàn tất cả logging
os.environ['WDM_LOG_LEVEL'] = '0'  # Tắt WebDriver Manager logs

# Tắt tất cả logging
logging.disable(logging.CRITICAL)

# Tắt cụ thể từng thư viện
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger('selenium').disabled = True
logging.getLogger('urllib3').disabled = True
logging.getLogger('webdriver_manager').disabled = True
logging.getLogger('scrapy').disabled = True
logging.getLogger('twisted').disabled = True
logging.getLogger('scrapy.core.engine').disabled = True
logging.getLogger('scrapy.crawler').disabled = True
logging.getLogger('scrapy.extensions').disabled = True
logging.getLogger('scrapy.middleware').disabled = True
logging.getLogger('scrapy.utils').disabled = True

# Tắt tất cả handlers
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

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
                # Xóa log thành công - không cần thiết
                break
        except TimeoutException:
            # Chỉ giữ log khi có lỗi quan trọng
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
        # Chỉ hiện thông tin quan trọng

        for article in articles:
            if fb_article := self.parse_article(article):
                self.upload_callback(fb_article)
        time.sleep(10)

    def parse_article(self, article):
        # Thử nhiều XPath selectors để tìm URL
        url_selectors = [
            # Original
            ".//div//span/a[@aria-label!='확대하기' and @role='link']/@href",
            ".//a[contains(@href, '/posts/')]/@href",  # Posts links
            ".//a[contains(@href, '/stories/')]/@href",  # Stories links
            ".//a[contains(@href, '/reel/')]/@href",  # Reel links
            ".//a[contains(@href, '/photo/')]/@href",  # Photo links
            ".//a[@role='link'][1]/@href",  # First link with role
            ".//a[1]/@href",  # First link as fallback
        ]

        article_url = None
        for selector in url_selectors:
            urls = article.xpath(selector).getall()
            if urls:
                article_url = urls[0]
                break

        # Convert relative URL to absolute URL
        if article_url and article_url.startswith('/'):
            article_url = f"https://www.facebook.com{article_url}"

        # Lấy header info cho timestamp
        article_header = article.xpath(self.article_header_xpath)
        publish_date = article_header.xpath("./@aria-label").get()
        descriptions = article.xpath(self.description_xpath).getall()
        description = " ".join(descriptions).strip()

        # Parse thời gian tương đối từ Facebook
        actual_timestamp = None
        if article_url and description:
            # Lấy tất cả text để tìm thời gian
            all_texts = article.xpath(".//text()").getall()
            filtered_texts = [text.strip()
                              for text in all_texts if text.strip()]

            # Tìm text có chứa pattern thời gian
            import re
            patterns = [
                # Relative time patterns
                r'\b\d+\s*[mhdwy](?:[a-z]*)?(?:\s+ago)?\b',  # 12m, 2h, 3d
                # 12 minutes
                r'\b\d+\s+(?:min|hour|day|week|month|year)s?(?:\s+ago)?\b',
                r'\b(?:yesterday|today)\b',  # yesterday, today
                r'\b(?:just now|a moment ago)\b',  # just now
                r'\b\d+\s*[分時日週月年](?:前|ago)?\b',  # Asian format
                # Absolute date patterns
                # 30 June
                r'\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\b',
                # June 30
                r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\b',
                # 30 Jun
                r'\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b',
                # Jun 30
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
                # Fallback: dùng current time
                from datetime import datetime, timezone
                actual_timestamp = datetime.now(timezone.utc)

        if article_url and description:
            # Chỉ hiện kết quả crawl thành công
            print(
                f"✓ Crawled: {self.keyword} | Content: {description[:50]}...")

            if self.upload_callback:
                self.upload_callback({
                    MockFacebook.kwrd.name: self.keyword,
                    MockFacebook.feed_url.name: article_url,
                    MockFacebook.publish_date.name: actual_timestamp,  # Dùng parsed datetime
                    MockFacebook.content.name: description,
                })


# ========== SELENIUM MIDDLEWARE SIMPLIFIED ==========
def get_selenium_settings():
    """
    Tạo settings cho Scrapy với Selenium middleware
    """
    return {
        "USER_AGENT": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        ),
        "DOWNLOADER_MIDDLEWARES": {
            "facebook_spider.SimpleSeleniumMiddleware": 585,
        },
        "CONCURRENT_REQUESTS": 1,
        "DOWNLOAD_DELAY": 2,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 2,
        "AUTOTHROTTLE_MAX_DELAY": 10,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
        "HEADLESS": True,
        # Tắt hoàn toàn logging của Scrapy
        "LOG_ENABLED": False,
        "LOG_LEVEL": "CRITICAL",
        "LOG_STDOUT": False,
        "TELNETCONSOLE_ENABLED": False,
        "STATS_CLASS": None,  # Tắt stats
        "EXTENSIONS": {},  # Tắt tất cả extensions
    }


# ========== SIMPLE SELENIUM MIDDLEWARE ==========


class SimpleSeleniumMiddleware:
    """Simplified Selenium middleware cho Scrapy"""

    def __init__(self):
        self.driver = None

    def _init_driver(self, spider):
        """Initialize Chrome driver"""
        if self.driver is None:
            chrome_options = Options()
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--headless')
            # Tắt logs của Chrome
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_argument('--silent')
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_experimental_option(
                'excludeSwitches', ['enable-logging'])
            chrome_options.add_experimental_option(
                'useAutomationExtension', False)

            # Use webdriver-manager với logging tắt
            service = Service(ChromeDriverManager(log_level=0).install())
            service.log_path = os.devnull  # Redirect logs to devnull
            self.driver = webdriver.Chrome(
                service=service, options=chrome_options)

    def process_request(self, request, spider):
        """Process request with Selenium"""
        if self.driver is None:
            self._init_driver(spider)

        # Navigate to URL
        self.driver.get(request.url)

        # Handle cookies if callback is provided
        if 'callback' in request.meta:
            callback = request.meta['callback']
            if callback:
                callback(self.driver)

        # Wait for page load
        time.sleep(3)

        # Create HtmlResponse
        body = self.driver.page_source.encode('utf-8')
        return HtmlResponse(
            url=request.url,
            body=body,
            encoding='utf-8',
            request=request
        )

    def spider_closed(self, spider):
        """Clean up driver when spider closes"""
        if self.driver:
            self.driver.quit()
            # Xóa log đóng driver - không cần thiết


# ========== TEST FUNCTIONS ==========
def test_callback(data):
    """Callback function để xử lý dữ liệu crawl được"""
    print("\n" + "=" * 80)
    print("📊 CRAWLED DATA:")
    print("=" * 80)
    print(f"🔤 KEYWORD (kwrd): {data.get('keyword', 'N/A')}")
    print(f"🔗 FEED_URL: {data.get('url', 'N/A')}")
    print(f"📅 PUBLISH_DATE: {data.get('publish_date', 'N/A')}")
    content = data.get('content', 'N/A')
    print(f"📝 CONTENT: {content}")
    print("=" * 80)


def run_facebook_spider(keyword="test"):
    """Chạy Facebook spider với keyword cụ thể"""
    print(f"🚀 Starting crawl for: {keyword}")

    # URL to crawl
    start_urls = [f"https://www.facebook.com/hashtag/{keyword}"]

    # Settings
    settings = get_selenium_settings()

    # Run spider
    try:
        process = CrawlerProcess(settings)
        process.crawl(
            FacebookHashtagSpider,
            keyword=keyword,
            upload_callback=test_callback,
            start_urls=start_urls
        )
        process.start()
        print("✅ Crawl completed!")
    except Exception as e:
        print(f"❌ Error: {e}")


# ========== UTILITY FUNCTIONS ==========
def parse_relative_time(relative_text):
    """
    Parse relative time text (12m, 2h, 3d) hoặc absolute date (30 June) thành datetime thực tế
    Args:
        relative_text: Text như "12m", "2 hrs", "3 days ago", "30 June", "July 15", etc.
    Returns:
        datetime object hoặc None nếu không parse được
    """
    from datetime import datetime, timezone, timedelta
    import re

    if not relative_text:
        return None

    # Clean text và lowercase
    text = relative_text.lower().strip()

    # 1. Thử parse absolute dates trước (30 June, July 15, December 2024)
    absolute_patterns = [
        # "30 June", "15 July", "3 December"
        r'(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)',
        # "June 30", "July 15", "December 3"
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})',
        # "30 Jun", "15 Jul", "3 Dec" (short form)
        r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
        # "Jun 30", "Jul 15", "Dec 3"
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})',
    ]

    months_map = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
        'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9,
        'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }

    for pattern in absolute_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                groups = match.groups()
                if groups[0].isdigit():  # "30 June" format
                    day = int(groups[0])
                    month = months_map.get(groups[1])
                else:  # "June 30" format
                    month = months_map.get(groups[0])
                    day = int(groups[1])

                if month and 1 <= day <= 31:
                    # Assume current year if not specified
                    current_year = datetime.now().year
                    return datetime(current_year, month, day, tzinfo=timezone.utc)
            except (ValueError, KeyError):
                continue

    # 2. Patterns cho relative time (existing code)
    patterns = [
        # Minutes: "12m", "12 min", "12 minutes"
        (r'(\d+)\s*m(?:in|inutes?)?(?:\s+ago)?', 'minutes'),
        # Hours: "2h", "2 hr", "2 hours"
        (r'(\d+)\s*h(?:r|rs|ours?)?(?:\s+ago)?', 'hours'),
        # Days: "3d", "3 day", "3 days"
        (r'(\d+)\s*d(?:ay|ays?)?(?:\s+ago)?', 'days'),
        # Weeks: "1w", "1 week", "2 weeks"
        (r'(\d+)\s*w(?:eek|eeks?)?(?:\s+ago)?', 'weeks'),
        # Months: "1mo", "1 month", "2 months"
        (r'(\d+)\s*mo(?:nth|nths?)?(?:\s+ago)?', 'months'),
        # Years: "1y", "1 year", "2 years"
        (r'(\d+)\s*y(?:ear|ears?)?(?:\s+ago)?', 'years'),
    ]

    for pattern, unit in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            now = datetime.now(timezone.utc)

            if unit == 'minutes':
                return now - timedelta(minutes=value)
            elif unit == 'hours':
                return now - timedelta(hours=value)
            elif unit == 'days':
                return now - timedelta(days=value)
            elif unit == 'weeks':
                return now - timedelta(weeks=value)
            elif unit == 'months':
                return now - timedelta(days=value * 30)  # Approximation
            elif unit == 'years':
                return now - timedelta(days=value * 365)  # Approximation

    # 3. Special cases
    if 'yesterday' in text:
        return datetime.now(timezone.utc) - timedelta(days=1)
    elif 'today' in text:
        return datetime.now(timezone.utc)
    elif any(word in text for word in ['just now', 'moment ago', 'now']):
        return datetime.now(timezone.utc)

    # Nếu không match pattern nào, return current time
    print(f"⚠️  Cannot parse time: '{relative_text}', using current time")
    return datetime.now(timezone.utc)


if __name__ == "__main__":
    import sys

    keyword = "test"
    if len(sys.argv) > 1:
        keyword = sys.argv[1]

    print(f"🔍 Facebook Spider - Keyword: {keyword}")
    time.sleep(1)
    run_facebook_spider(keyword)
