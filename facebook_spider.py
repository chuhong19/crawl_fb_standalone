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

        for article in articles:
            if fb_article := self.parse_article(article):
                self.upload_callback(fb_article)
        time.sleep(10)

    def parse_article(self, article):
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
            print(
                f"✓ Crawled: {self.keyword} | Content: {description[:50]}...")

            if self.upload_callback:
                self.upload_callback({
                    MockFacebook.kwrd.name: self.keyword,
                    MockFacebook.feed_url.name: article_url,
                    MockFacebook.publish_date.name: actual_timestamp,
                    MockFacebook.content.name: description,
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
        return HtmlResponse(
            url=request.url,
            body=body,
            encoding='utf-8',
            request=request
        )

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
    print("=" * 80)


def run_facebook_spider(keyword="test"):
    print(f"🚀 Starting crawl for: {keyword}")

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
        print("✅ Crawl completed!")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    import sys

    keyword = "test"
    if len(sys.argv) > 1:
        keyword = sys.argv[1]

    print(f"🔍 Facebook Spider - Keyword: {keyword}")
    time.sleep(1)
    run_facebook_spider(keyword)
