#!/usr/bin/env python

import re
from urllib.parse import urljoin, urlparse
import requests
import os
import hashlib
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


def extract_images_from_article(article):
    """
    Extract image URLs from Facebook article element

    Args:
        article: Scrapy selector object for article

    Returns:
        list: List of image URLs
    """
    images = []

    # Multiple XPath selectors for content images (not UI elements)
    image_selectors = [
        # Content images in posts/articles - prioritize content containers
        ".//div[contains(@data-ad-comet-preview, 'message')]//img/@src",
        ".//div[contains(@class, 'scaledImageFitWidth')]//img/@src",
        ".//div[contains(@class, 'uiScaledImageContainer')]//img/@src",
        # Attachment images
        ".//div[contains(@class, 'attachment')]//img/@src",
        ".//div[contains(@class, 'photoContainer')]//img/@src",
        # Story/post content images
        ".//div[contains(@class, 'story')]//img/@src",
        ".//div[contains(@class, 'userContent')]//img/@src",
        # Data attributes for lazy loading
        ".//div[contains(@class, 'scaledImageFitWidth')]//img/@data-src",
        ".//div[contains(@class, 'photoContainer')]//img/@data-src",
        # Background images in content (not UI)
        ".//div[contains(@class, 'scaledImageFitWidth')]//*[contains(@style, 'background-image')]/@style",
        # Broader fallback selectors
        ".//img/@src",
        ".//img/@data-src",
    ]

    for selector in image_selectors:
        try:
            found_images = article.xpath(selector).getall()
            for img in found_images:
                cleaned_url = clean_image_url(img)
                if cleaned_url and is_valid_image_url(cleaned_url):
                    images.append(cleaned_url)
        except Exception:
            continue

    # Remove duplicates while preserving order
    seen = set()
    unique_images = []
    for img in images:
        if img not in seen:
            seen.add(img)
            unique_images.append(img)

    return unique_images


def extract_videos_from_article(article):
    """
    Extract video URLs from Facebook article element

    Args:
        article: Scrapy selector object for article

    Returns:
        list: List of video URLs
    """
    videos = []

    # Multiple XPath selectors for videos
    video_selectors = [
        # Standard video tags
        ".//video/@src",
        ".//video/source/@src",
        # Data attributes for lazy loading
        ".//video/@data-src",
        ".//video/source/@data-src",
        # Facebook specific video containers
        ".//div[contains(@class, 'videoContainer')]//video/@src",
        ".//div[contains(@class, 'videoWrapper')]//video/@src",
        # Links to video pages
        ".//a[contains(@href, '/videos/')]/@href",
        ".//a[contains(@href, '/watch/')]/@href",
        # Embedded video iframes
        ".//iframe[contains(@src, 'video')]/@src",
        # Background video sources
        ".//*[contains(@data-video-src, 'http')]/@data-video-src",
    ]

    for selector in video_selectors:
        try:
            found_videos = article.xpath(selector).getall()
            for video in found_videos:
                cleaned_url = clean_video_url(video)
                if cleaned_url and is_valid_video_url(cleaned_url):
                    videos.append(cleaned_url)
        except Exception:
            continue

        # Remove duplicates and normalize URLs
    seen = set()
    unique_videos = []
    for video in videos:
        # Normalize video URL to remove duplicates
        normalized = normalize_video_url(video)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_videos.append(normalized)

    return unique_videos


def clean_image_url(img_url):
    """
    Clean and normalize image URL

    Args:
        img_url: Raw image URL or style attribute

    Returns:
        str: Cleaned image URL or None
    """
    if not img_url:
        return None

        # Extract URL from CSS background-image style
    if 'background-image' in img_url:
        bg_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', img_url)
        if bg_match:
            img_url = bg_match.group(1)
        else:
            return None

    # Only remove specific tracking parameters, keep image processing ones like stp=
    # DON'T remove stp (image size/processing), only remove tracking
    img_url = re.sub(r'[?&]_nc_cat=[^&]*', '', img_url)
    img_url = re.sub(r'[?&]_nc_oc=[^&]*', '', img_url)
    img_url = re.sub(r'[?&]_nc_ht=[^&]*', '', img_url)
    img_url = re.sub(r'[?&]ccb=[^&]*', '', img_url)
    img_url = re.sub(r'[?&]oh=[^&]*', '', img_url)
    img_url = re.sub(r'[?&]oe=[^&]*', '', img_url)

    # Clean up multiple & and trailing ?
    img_url = re.sub(r'&+', '&', img_url)
    img_url = re.sub(r'[?&]$', '', img_url)

    # Convert relative URLs to absolute
    if img_url.startswith('//'):
        img_url = 'https:' + img_url
    elif img_url.startswith('/'):
        img_url = 'https://www.facebook.com' + img_url

        return img_url.strip()


def clean_video_url(video_url):
    """
    Clean and normalize video URL

    Args:
        video_url: Raw video URL

    Returns:
        str: Cleaned video URL or None
    """
    if not video_url:
        return None

    # Convert relative URLs to absolute
    if video_url.startswith('//'):
        video_url = 'https:' + video_url
    elif video_url.startswith('/'):
        video_url = 'https://www.facebook.com' + video_url

    return video_url.strip()


def normalize_video_url(video_url):
    """
    Normalize video URL to remove duplicates

    Args:
        video_url: Video URL to normalize

    Returns:
        str: Normalized video URL
    """
    if not video_url:
        return None

    # Extract video ID from Facebook video URLs
    import re

    # Pattern for Facebook video URLs: /videos/123456/
    video_id_match = re.search(r'/videos/(\d+)/', video_url)
    if video_id_match:
        video_id = video_id_match.group(1)
        # Return standardized format
        return f"https://www.facebook.com/videos/{video_id}/"

    # Pattern for watch URLs: /watch/123456 or /watch/?v=123456
    watch_id_match = re.search(r'/watch/(?:\?v=)?(\d+)', video_url)
    if watch_id_match:
        video_id = watch_id_match.group(1)
        return f"https://www.facebook.com/watch/{video_id}/"

    # For other video URLs, remove common tracking parameters
    cleaned_url = re.sub(r'[?&]__cft__\[.*?\]', '', video_url)
    cleaned_url = re.sub(r'[?&]__tn__=.*?(?=&|$)', '', cleaned_url)
    cleaned_url = re.sub(r'[?&]_nc_.*?(?=&|$)', '', cleaned_url)

    # Remove trailing ? if no parameters left
    cleaned_url = re.sub(r'\?$', '', cleaned_url)

    return cleaned_url


def is_valid_image_url(url):
    """
    Check if URL is a valid image

    Args:
        url: Image URL to validate

    Returns:
        bool: True if valid image URL
    """
    if not url or len(url) < 10:
        return False

    # Skip data URLs, placeholder images, and tiny images
    skip_patterns = [
        'data:image',
        'blank.gif',
        'spacer.gif',
        'transparent.gif',
        '1x1',
        'pixel.png',
        '/assets/',
        '/static/',
        # Facebook static UI resources (not content images)
        'static.xx.fbcdn.net/rsrc.php',
        'static.facebook.com/rsrc.php',
        '/rsrc.php',
        # Common Facebook UI icons and sprites
        'sprites/',
        'icons/',
        'emoji/',
        '/images/emoji.php',
        # Profile picture placeholders
        'profile_pic_header',
        'default_profile',
        # UI elements
        '/ui/',
        '/chrome/',
        '/images/icons/',
    ]

    for pattern in skip_patterns:
        if pattern in url.lower():
            return False

    # Must be from Facebook content domains (not static UI domains)
    valid_domains = [
        'scontent.com',
        'scontent-',       # scontent-xxx.xx.fbcdn.net
        'scontent.',       # scontent.fsgn2-*.fna.fbcdn.net
        'cdninstagram.com',
    ]

    # But exclude static resource domains
    invalid_domains = [
        'static.xx.fbcdn.net',
        'static.facebook.com',
    ]

    for invalid_domain in invalid_domains:
        if invalid_domain in url:
            return False

    return any(domain in url for domain in valid_domains)


def is_valid_video_url(url):
    """
    Check if URL is a valid video

    Args:
        url: Video URL to validate

    Returns:
        bool: True if valid video URL
    """
    if not url or len(url) < 10:
        return False

    # Must contain video indicators
    video_indicators = [
        '.mp4',
        '.mov',
        '.avi',
        '.webm',
        '/videos/',
        '/watch/',
        'video',
    ]

    has_video_indicator = any(indicator in url.lower()
                              for indicator in video_indicators)

    # Must be from Facebook domains
    valid_domains = [
        'facebook.com',
        'fbcdn.net',
        'scontent.com',
        'video.',
    ]

    has_valid_domain = any(domain in url for domain in valid_domains)

    return has_video_indicator and has_valid_domain


def download_image_during_crawl(driver, img_url, save_dir="downloaded_images"):
    """
    Download image using the same browser session and save locally

    Args:
        driver: Selenium WebDriver instance (same session)
        img_url: Facebook image URL
        save_dir: Directory to save images

    Returns:
        str: Local file path or None if failed
    """
    try:
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Use selenium to get image with same session/cookies
        driver.get(img_url)

        # Get image content from page source or use requests with driver's cookies
        cookies = driver.get_cookies()
        session = requests.Session()

        # Transfer cookies from selenium to requests
        for cookie in cookies:
            session.cookies.set(
                cookie['name'], cookie['value'], domain=cookie.get('domain'))

        # Set same headers as browser
        headers = {
            'User-Agent': driver.execute_script("return navigator.userAgent;"),
            'Referer': 'https://www.facebook.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        }

        response = session.get(img_url, headers=headers, stream=True)

        if response.status_code == 200:
            # Generate filename from URL hash
            url_hash = hashlib.md5(img_url.encode()).hexdigest()[:12]
            filename = f"fb_image_{url_hash}.jpg"
            filepath = os.path.join(save_dir, filename)

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return filepath
        else:
            print(f"❌ Failed to download image: HTTP {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Error downloading image: {e}")
        return None


def extract_and_download_images_from_article(article, driver, save_dir="downloaded_images"):
    """
    Extract image URLs and download them during crawl

    Args:
        article: Scrapy selector object for article
        driver: Selenium WebDriver instance
        save_dir: Directory to save images

    Returns:
        list: List of local file paths
    """
    local_paths = []

    # Get image URLs using existing logic
    image_urls = extract_images_from_article(article)

    print(f"🔽 Downloading {len(image_urls)} images...")

    for i, img_url in enumerate(image_urls, 1):
        print(f"  {i}/{len(image_urls)}: Downloading...")
        local_path = download_image_during_crawl(driver, img_url, save_dir)
        if local_path:
            local_paths.append(local_path)
            print(f"    ✅ Saved: {local_path}")
        else:
            print(f"    ❌ Failed: {img_url[:50]}...")

    return local_paths


def screenshot_article(driver, article_element, save_dir="screenshots", article_index=0):
    """
    Take screenshot of specific article element

    Args:
        driver: Selenium WebDriver instance
        article_element: Scrapy selector (we need to find corresponding WebElement)
        save_dir: Directory to save screenshots
        article_index: Index for unique filename

    Returns:
        str: Local screenshot file path or None if failed
    """
    try:
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Scroll article into view for better screenshot
        # Since we have Scrapy selector, we need to find the corresponding WebElement
        # Get all article elements and use index to match
        web_articles = driver.find_elements(By.XPATH, "//div[@role='article']")

        if article_index < len(web_articles):
            article_web_element = web_articles[article_index]

            # Scroll element into view
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", article_web_element)

            # Wait a moment for content to load
            import time
            time.sleep(1)

            # Take screenshot of the specific element
            screenshot_data = article_web_element.screenshot_as_png

            # Generate filename
            timestamp = int(time.time())
            filename = f"article_{article_index}_{timestamp}.png"
            filepath = os.path.join(save_dir, filename)

            # Save screenshot
            with open(filepath, 'wb') as f:
                f.write(screenshot_data)

            print(f"📸 Screenshot saved: {filepath}")
            return filepath
        else:
            print(f"❌ Article index {article_index} not found in WebDriver")
            return None

    except Exception as e:
        print(f"❌ Error taking screenshot: {e}")
        return None


def screenshot_full_page(driver, save_dir="screenshots"):
    """
    Take full page screenshot

    Args:
        driver: Selenium WebDriver instance
        save_dir: Directory to save screenshots

    Returns:
        str: Local screenshot file path or None if failed
    """
    try:
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Dismiss any popup/modal first
        print("🔍 Checking for popups to dismiss...")
        dismiss_facebook_popup(driver)

        # Scroll to top first
        driver.execute_script("window.scrollTo(0, 0);")

        # Wait a moment for content to settle
        import time
        time.sleep(2)

        # Take full page screenshot
        timestamp = int(time.time())
        filename = f"full_page_{timestamp}.png"
        filepath = os.path.join(save_dir, filename)

        # Full page screenshot
        driver.save_screenshot(filepath)

        print(f"📸 Full page screenshot saved: {filepath}")
        return filepath

    except Exception as e:
        print(f"❌ Error taking full page screenshot: {e}")
        return None


def screenshot_articles_on_page(driver, save_dir="screenshots"):
    """
    Take screenshots of all articles on current page

    Args:
        driver: Selenium WebDriver instance
        save_dir: Directory to save screenshots

    Returns:
        list: List of screenshot file paths
    """
    screenshots = []

    try:
        # Find all article elements
        web_articles = driver.find_elements(By.XPATH, "//div[@role='article']")

        print(f"📸 Found {len(web_articles)} articles to screenshot")

        for i, article_element in enumerate(web_articles):
            try:
                # Scroll article into view
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", article_element)

                # Wait for content to load
                import time
                time.sleep(1)

                # Take screenshot
                screenshot_data = article_element.screenshot_as_png

                # Generate filename
                timestamp = int(time.time())
                filename = f"article_{i}_{timestamp}.png"
                filepath = os.path.join(save_dir, filename)

                if not os.path.exists(save_dir):
                    os.makedirs(save_dir)

                # Save screenshot
                with open(filepath, 'wb') as f:
                    f.write(screenshot_data)

                screenshots.append(filepath)
                print(f"  📸 Article {i+1}: {filepath}")

            except Exception as e:
                print(f"  ❌ Failed to screenshot article {i}: {e}")
                continue

        return screenshots

    except Exception as e:
        print(f"❌ Error in screenshot_articles_on_page: {e}")
        return []


def dismiss_facebook_popup(driver):
    """
    Dismiss Facebook login popup/modal that blocks content

    Args:
        driver: Selenium WebDriver instance

    Returns:
        bool: True if popup was found and dismissed, False otherwise
    """
    try:
        # Wait a moment for popup to appear
        import time
        time.sleep(2)

        # Multiple selectors for close button on Facebook login popup
        close_selectors = [
            # X button in top right corner
            "//div[@aria-label='Close']",
            "//button[@aria-label='Close']",
            "[aria-label='Close']",
            # Close button variations
            "//div[contains(@class, 'close')]",
            "//button[contains(@class, 'close')]",
            # X symbol
            "//div[text()='×']",
            "//span[text()='×']",
            # Skip or dismiss options
            "//a[contains(text(), 'Not Now')]",
            "//button[contains(text(), 'Not Now')]",
            "//div[contains(text(), 'Skip')]",
            "//button[contains(text(), 'Skip')]",
        ]

        for selector in close_selectors:
            try:
                if selector.startswith("//"):
                    # XPath selector
                    elements = driver.find_elements(By.XPATH, selector)
                else:
                    # CSS selector
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)

                if elements:
                    # Click the first visible element
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            element.click()
                            print(
                                f"✅ Dismissed popup using selector: {selector}")
                            time.sleep(1)  # Wait for popup to close
                            return True
            except Exception as e:
                # Continue trying other selectors
                continue

        # Try pressing ESC key as fallback
        try:
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.action_chains import ActionChains

            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            print("✅ Dismissed popup using ESC key")
            time.sleep(1)
            return True
        except Exception:
            pass

        print("ℹ️  No popup found to dismiss")
        return False

    except Exception as e:
        print(f"❌ Error dismissing popup: {e}")
        return False


if __name__ == "__main__":
    # Test the media extraction functions
    print("🖼️  Testing image URL cleaning and filtering:")
    test_images = [
        "https://scontent.com/image.jpg?_nc_cat=123",  # Valid content image
        "https://static.xx.fbcdn.net/rsrc.php/v4/yA/r/WftEU-JN8-j.png",  # Invalid UI image
        "//scontent-hkg4-1.xx.fbcdn.net/photo.png",  # Valid content CDN
        "/static/image.gif",  # Invalid static
        # Valid background
        "background-image: url('https://scontent.com/bg.jpg')",
        "data:image/gif;base64,R0lGOD...",  # Invalid data URL
    ]

    for img in test_images:
        cleaned = clean_image_url(img)
        valid = is_valid_image_url(cleaned) if cleaned else False
        print(f"  '{img[:60]}...' → Valid: {valid}")

    print("\n🎥 Testing video URL normalization:")
    test_videos = [
        "https://www.facebook.com/61561110231062/videos/1790230575171441/?__cft__[0]=AZUf0Reb",
        "https://www.facebook.com/61561110231062/videos/1790230575171441/?__tn__=%2CO%2CP-R",
        "/videos/123456/",
        "https://facebook.com/watch/456789",
    ]

    for video in test_videos:
        cleaned = clean_video_url(video)
        normalized = normalize_video_url(cleaned) if cleaned else None
        valid = is_valid_video_url(normalized) if normalized else False
        print(f"  Original: {video[:60]}...")
        print(f"  Normalized: {normalized} (valid: {valid})")
        print()
