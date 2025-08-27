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
            from .media_extractor import screenshot_full_page
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
                r'\b\d+\s*[분時日週月年](?:前|ago)?\b',
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
            # Extract and download images from article
            driver = response.request.meta.get('driver')
            images = []

            if driver:
                # Extract image URLs from article
                image_urls = self.extract_images_from_facebook_post(article)

                if image_urls:
                    print(f"🖼️  Found {len(image_urls)} images in post")
                    # Download images using Selenium session
                    downloaded_paths = self.download_facebook_images(
                        driver, image_urls, save_dir="image_downloads"
                    )
                    images.extend(downloaded_paths)

                # Also add screenshot as backup
                if screenshot_path:
                    images.append(screenshot_path)
                    print(f"📸 Added screenshot: {screenshot_path}")
            else:
                # Fallback to screenshot only if no driver
                if screenshot_path:
                    images = [screenshot_path]
                    print(f"📸 Using screenshot only: {screenshot_path}")

            print(
                f"✓ Crawled: {self.pagename} | Content: {description[:50]}... | Total images: {len(images)}")

            if self.upload_callback:
                self.upload_callback({
                    MockFacebook.kwrd.name: self.pagename,
                    MockFacebook.feed_url.name: article_url,
                    MockFacebook.publish_date.name: actual_timestamp,
                    MockFacebook.content.name: description,
                    MockFacebook.images.name: images,
                })

    def extract_images_from_facebook_post(self, article):
        """
        Extract image URLs từ Facebook post article (exclude emoji/icons)
        """
        images = []

        # Multiple XPath selectors for Facebook images (exclude small emoji images)
        image_selectors = [
            # Standard img tags with Facebook CDN sources, exclude small images
            ".//img[contains(@src, 'scontent') and not(contains(@src, '16x16')) and not(contains(@src, '20x20')) and not(contains(@src, '24x24')) and not(contains(@src, '32x32'))]/@src",
            ".//img[contains(@src, 'fbcdn.net') and not(contains(@src, 'emoji')) and not(contains(@src, 'icon'))]/@src",
            ".//img[contains(@src, 'facebook.com') and not(contains(@src, 'emoji'))]/@src",
            # Lazy loaded images
            ".//img[@data-src and contains(@data-src, 'scontent') and not(contains(@data-src, 'emoji'))]/@data-src",
            ".//img[@data-src and contains(@data-src, 'fbcdn') and not(contains(@data-src, 'emoji'))]/@data-src",
            # General img tags but exclude obvious emoji classes and attributes
            ".//img[contains(@class, 'x') and @src and not(contains(@alt, 'emoji')) and not(contains(@class, 'emoji')) and not(contains(@class, 'icon'))]/@src",
            # Background images in style attributes
            ".//*[contains(@style, 'background-image') and contains(@style, 'scontent') and not(contains(@style, 'emoji'))]/@style"
        ]

        for selector in image_selectors:
            found_images = article.xpath(selector).getall()
            for img_url in found_images:
                # Clean and validate image URL
                cleaned_url = self.clean_facebook_image_url(img_url)
                if cleaned_url and self.is_valid_facebook_image(cleaned_url):
                    # Additional size-based filtering for content images
                    if self._is_likely_content_image(cleaned_url):
                        images.append(cleaned_url)

        print(
            f"🔍 Filtered to {len(images)} content images (excluded emoji/icons)")

        # Remove duplicates while preserving order
        return list(dict.fromkeys(images))

    def _is_likely_content_image(self, url):
        """
        Additional check to ensure image is likely content (not emoji/icon)
        based on URL patterns and characteristics
        """
        # Skip if URL contains obvious emoji/icon indicators
        emoji_patterns = [
            'emoji', 'icon', 'reaction', 'sticker', 'emoticon',
            '_16x16', '_20x20', '_24x24', '_32x32', '_48x48',
            'u00', 'static.xx.fbcdn.net/images/emoji',
            'static.facebook.com/images/emoji'
        ]

        for pattern in emoji_patterns:
            if pattern in url.lower():
                return False

        # Content images usually have these characteristics:
        # 1. From scontent CDN (user-uploaded content)
        # 2. Larger dimensions or no explicit small dimensions
        # 3. Not from static resources

        if 'scontent' in url:
            # This is likely user content from scontent CDN
            return True

        # Additional checks for other Facebook CDNs
        if 'fbcdn.net' in url and 'static' not in url:
            # Non-static fbcdn content
            return True

        return False

    def clean_facebook_image_url(self, img_url):
        """
        Clean Facebook image URL từ style attribute hoặc raw URL
        """
        if not img_url:
            return None

        # Extract URL from CSS background-image style
        if 'background-image' in img_url:
            import re
            bg_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', img_url)
            if bg_match:
                img_url = bg_match.group(1)
            else:
                return None

        # Convert relative URLs to absolute
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = 'https://www.facebook.com' + img_url

        return img_url.strip()

    def is_valid_facebook_image(self, url):
        """
        Validate if URL is valid Facebook content image (exclude emoji/icons)
        """
        if not url or len(url) < 20:
            return False

        # Must be from Facebook content domains
        valid_domains = [
            'scontent.com',
            'scontent-',  # scontent-xxx.xx.fbcdn.net
            'scontent.',  # scontent.fsgn2-*.fna.fbcdn.net
            'fbcdn.net',
            'cdninstagram.com'
        ]

        # Skip UI elements, tiny images, placeholders, and EMOJI/ICONS
        skip_patterns = [
            'blank.gif',
            'spacer.gif',
            '1x1',
            'pixel.png',
            '/rsrc.php',  # Facebook static resources
            'sprites/',
            'icons/',
            'emoji/',
            'profile_pic_header',
            '/assets/',
            '/static/',
            # Emoji/icon specific patterns
            'images/emoji.php',
            '/emoji/',
            '/emoticons/',
            '/reactions/',
            '/stickers/',
            'emoji_',
            'icon_',
            'reaction_',
            # Facebook emoji URLs patterns
            'static.xx.fbcdn.net/images/emoji',
            'static.facebook.com/images/emoji',
            '/images/icons/',
            '/images/emoji/',
            # Small image dimensions (likely emoji)
            '_16x16',
            '_20x20',
            '_24x24',
            '_32x32',
            # Emoji Unicode patterns in URLs
            'u00',  # Unicode emoji codes
        ]

        for pattern in skip_patterns:
            if pattern in url.lower():
                return False

        # Additional emoji detection by checking URL parameters
        if self._is_likely_emoji_by_params(url):
            return False

        return any(domain in url for domain in valid_domains)

    def _is_likely_emoji_by_params(self, url):
        """
        Detect emoji images by URL parameters and characteristics
        """
        from urllib.parse import urlparse, parse_qs

        try:
            parsed = urlparse(url)

            # Check if URL has very small dimensions (typical for emoji)
            if any(dim in url.lower() for dim in ['16x16', '20x20', '24x24', '32x32', '48x48']):
                return True

            # Check for emoji-specific parameters in Facebook URLs
            emoji_indicators = [
                'emoji',
                'icon',
                'reaction',
                'sticker',
                'emoticon'
            ]

            # Check path for emoji indicators
            path = parsed.path.lower()
            if any(indicator in path for indicator in emoji_indicators):
                return True

            # Check query parameters
            query_params = parse_qs(parsed.query)
            for param_name, param_values in query_params.items():
                param_str = f"{param_name}={','.join(param_values)}".lower()
                if any(indicator in param_str for indicator in emoji_indicators):
                    return True

            return False

        except Exception:
            return False

    def download_facebook_images(self, driver, image_urls, save_dir="image_downloads"):
        """
        Download Facebook images sử dụng Selenium session
        """
        import os
        import requests
        import hashlib
        from urllib.parse import urlparse

        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        downloaded_paths = []

        print(f"🔽 Downloading {len(image_urls)} images...")

        for i, img_url in enumerate(image_urls, 1):
            try:
                print(f"  {i}/{len(image_urls)}: {img_url[:50]}...")

                # Get cookies from Selenium session
                cookies = driver.get_cookies()
                session = requests.Session()

                # Transfer cookies from Selenium to requests
                for cookie in cookies:
                    session.cookies.set(
                        cookie['name'],
                        cookie['value'],
                        domain=cookie.get('domain')
                    )

                # Set browser-like headers
                headers = {
                    'User-Agent': driver.execute_script("return navigator.userAgent;"),
                    'Referer': 'https://www.facebook.com/',
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Sec-Fetch-Dest': 'image',
                    'Sec-Fetch-Mode': 'no-cors',
                    'Sec-Fetch-Site': 'cross-site'
                }

                # Download image
                response = session.get(
                    img_url, headers=headers, stream=True, timeout=30)

                if response.status_code == 200:
                    # Generate unique filename từ URL
                    url_hash = hashlib.md5(img_url.encode()).hexdigest()[:12]

                    # Extract file extension from URL or Content-Type
                    content_type = response.headers.get('content-type', '')
                    if 'jpeg' in content_type or 'jpg' in content_type:
                        ext = '.jpg'
                    elif 'png' in content_type:
                        ext = '.png'
                    elif 'webp' in content_type:
                        ext = '.webp'
                    else:
                        # Fallback: extract from URL
                        parsed = urlparse(img_url)
                        if '.jpg' in parsed.path:
                            ext = '.jpg'
                        elif '.png' in parsed.path:
                            ext = '.png'
                        else:
                            ext = '.jpg'  # Default

                    filename = f"fb_image_{url_hash}{ext}"
                    filepath = os.path.join(save_dir, filename)

                    # Save image
                    with open(filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                    downloaded_paths.append(filepath)
                    print(f"    ✅ Saved: {filepath}")

                else:
                    print(
                        f"    ❌ HTTP {response.status_code}: {img_url[:50]}...")

            except Exception as e:
                print(f"    ❌ Error: {e}")
                continue

        print(f"✅ Downloaded {len(downloaded_paths)}/{len(image_urls)} images")
        return downloaded_paths


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


# =========================================
# Runner class for Fire
# =========================================
class FacebookPageCrawler:
    def crawl(self, pagename="test"):
        """Crawl Facebook page posts"""
        logging.info(f"🚀 Starting page crawl for: {pagename}")

        start_urls = [f"https://www.facebook.com/{pagename}"]
        settings = get_selenium_settings()

        try:
            process = CrawlerProcess(settings)
            process.crawl(
                FacebookPageSpider,
                pagename=pagename,
                upload_callback=test_callback_page,
                start_urls=start_urls
            )
            process.start()
            logging.info("✅ Page crawl completed!")
        except Exception as e:
            logging.error(f"❌ Error: {e}")


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
