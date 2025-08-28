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
import time


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


def extract_all_images_from_facebook_post(driver, article_element, save_dir="image_downloads"):
    """
    Extract ALL images from Facebook post by clicking through photo galleries

    Args:
        driver: Selenium WebDriver instance
        article_element: WebElement for the article/post
        save_dir: Directory to save images

    Returns:
        list: List of downloaded image file paths
    """
    downloaded_images = []

    try:
        print("🔍 Looking for photo galleries in post...")

        # Skip visible images extraction - they're duplicates of gallery images
        # visible_images = extract_visible_images_from_post(driver, article_element)

        # Find photo gallery triggers
        gallery_triggers = find_photo_gallery_triggers(driver, article_element)

        if gallery_triggers:
            print(
                f"🖼️  Found {len(gallery_triggers)} photo gallery trigger(s)")

            for i, trigger in enumerate(gallery_triggers):
                print(f"📂 Processing gallery {i+1}/{len(gallery_triggers)}")

                gallery_images = extract_images_from_gallery(
                    driver, trigger, save_dir)

                downloaded_images.extend(gallery_images)

                # Small delay between galleries
                time.sleep(1)
        else:
            print("❌ No photo galleries found in post")
            # Fallback: extract visible images only if no galleries found
            visible_images = extract_visible_images_from_post(
                driver, article_element)
            if visible_images:
                print(
                    f"📷 Found {len(visible_images)} directly visible images as fallback")
                for img_url in visible_images:
                    downloaded_path = download_facebook_image_with_session(
                        driver, img_url, save_dir)
                    if downloaded_path:
                        downloaded_images.append(downloaded_path)

        # Remove any duplicates at the end level
        unique_images = list(dict.fromkeys(downloaded_images))

        print(f"✅ Total unique images extracted: {len(unique_images)}")
        return unique_images

    except Exception as e:
        print(f"❌ Error extracting images from post: {e}")
        return downloaded_images


def find_photo_gallery_triggers(driver, article_element):
    """
    Find clickable elements that open photo galleries in Facebook posts

    Args:
        driver: Selenium WebDriver instance
        article_element: WebElement for the article/post

    Returns:
        list: List of WebElements that can trigger photo galleries (deduplicated)
    """
    triggers = []

    try:
        # Multiple selectors for photo gallery triggers
        gallery_selectors = [
            # Photo count indicators like "+5 more photos"
            ".//div[contains(text(), 'more photo') or contains(text(), '+')]",
            ".//span[contains(text(), 'more photo') or contains(text(), '+')]",

            # Photo grid containers (multiple photos in a grid)
            ".//div[contains(@class, 'photoGrid') or contains(@class, 'photo-grid')]",
            ".//div[contains(@class, 'photoContainer') and count(.//img) > 1]",

            # Clickable photo containers
            ".//div[@role='button'][.//img]",
            ".//a[@role='link'][.//img]",

            # Facebook specific photo gallery triggers
            ".//div[contains(@class, 'uiMediaThumb')]",
            ".//div[contains(@class, 'scaledImageFitWidth')][@role='button']",

            # Images that are clickable (lead to galleries)
            ".//img[@role='button' or @tabindex='0']",
            ".//img[parent::div[@role='button'] or parent::a[@role='link']]",
        ]

        for selector in gallery_selectors:
            try:
                elements = article_element.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        # Check if element might lead to a gallery
                        if is_likely_gallery_trigger(element):
                            triggers.append(element)
            except Exception:
                continue

    except Exception as e:
        print(f"❌ Error finding gallery triggers: {e}")

    # Deduplicate triggers that lead to the same gallery
    unique_triggers = deduplicate_gallery_triggers(triggers)

    if len(triggers) > len(unique_triggers):
        print(
            f"🔍 Found {len(triggers)} potential triggers, deduplicated to {len(unique_triggers)} unique galleries")

    return unique_triggers


def deduplicate_gallery_triggers(triggers):
    """
    Remove duplicate triggers that lead to the same gallery

    Args:
        triggers: List of WebElements that can trigger galleries

    Returns:
        list: Deduplicated list of unique gallery triggers
    """
    unique_triggers = []
    seen_locations = set()
    seen_containers = set()

    for trigger in triggers:
        try:
            # Method 1: Check if triggers are in the same container/parent
            parent_element = trigger.find_element(By.XPATH, "./..")
            parent_id = id(parent_element)

            if parent_id in seen_containers:
                print(f"  🔄 Skipping duplicate trigger in same container")
                continue

            # Method 2: Check location proximity (triggers close together likely same gallery)
            location = trigger.location
            # Group by 50px grid
            location_key = (
                round(location['x'] / 50) * 50, round(location['y'] / 50) * 50)

            if location_key in seen_locations:
                print(f"  🔄 Skipping duplicate trigger at similar location")
                continue

            # Method 3: Check if trigger contains similar text/images
            trigger_text = trigger.text.lower().strip()
            trigger_images = trigger.find_elements(By.TAG_NAME, "img")

            # Skip if we already have a trigger with similar characteristics
            is_duplicate = False
            for existing_trigger in unique_triggers:
                try:
                    existing_text = existing_trigger.text.lower().strip()
                    existing_images = existing_trigger.find_elements(
                        By.TAG_NAME, "img")

                    # Check text similarity
                    if trigger_text and existing_text and trigger_text == existing_text:
                        is_duplicate = True
                        break

                    # Check if both have images and similar count
                    if len(trigger_images) > 0 and len(existing_images) > 0:
                        if abs(len(trigger_images) - len(existing_images)) <= 1:
                            # Compare first image source if available
                            try:
                                trigger_img_src = trigger_images[0].get_attribute(
                                    'src')
                                existing_img_src = existing_images[0].get_attribute(
                                    'src')
                                if trigger_img_src and existing_img_src and trigger_img_src == existing_img_src:
                                    is_duplicate = True
                                    break
                            except:
                                pass

                except Exception:
                    continue

            if is_duplicate:
                print(f"  🔄 Skipping duplicate trigger with similar content")
                continue

            # This trigger seems unique, add it
            unique_triggers.append(trigger)
            seen_locations.add(location_key)
            seen_containers.add(parent_id)

        except Exception as e:
            # If we can't analyze this trigger, include it to be safe
            unique_triggers.append(trigger)
            continue

    return unique_triggers


def is_likely_gallery_trigger(element):
    """
    Check if element is likely to trigger a photo gallery

    Args:
        element: WebElement to check

    Returns:
        bool: True if likely a gallery trigger
    """
    try:
        # Check text content for gallery indicators
        text = element.text.lower()
        gallery_indicators = [
            'more photo', '+', 'photos', 'see all', 'view all',
            'more images', 'additional', 'others'
        ]

        for indicator in gallery_indicators:
            if indicator in text:
                return True

        # Check if element contains multiple images
        images = element.find_elements(By.TAG_NAME, "img")
        if len(images) > 1:
            return True

        # Check for gallery-related attributes or classes
        class_name = element.get_attribute("class") or ""
        gallery_classes = [
            'photo', 'gallery', 'media', 'grid', 'thumb',
            'container', 'viewer', 'lightbox'
        ]

        for gallery_class in gallery_classes:
            if gallery_class in class_name.lower():
                return True

        return False

    except Exception:
        return False


def extract_images_from_gallery(driver, gallery_trigger, save_dir="image_downloads"):
    """
    Click on gallery trigger and extract all images from the opened gallery

    Args:
        driver: Selenium WebDriver instance
        gallery_trigger: WebElement that opens the gallery
        save_dir: Directory to save images

    Returns:
        list: List of downloaded image file paths
    """
    gallery_images = []
    start_time = time.time()
    max_gallery_time = 300  # 5 minutes max per gallery

    try:
        print("🖱️  Clicking gallery trigger...")

        # Scroll trigger into view and click
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", gallery_trigger)
        time.sleep(1)

        # Try to click the trigger
        try:
            gallery_trigger.click()
        except Exception:
            # Fallback: JavaScript click
            driver.execute_script("arguments[0].click();", gallery_trigger)

        time.sleep(2)  # Wait for gallery to open

        # Check if photo viewer/modal opened
        if is_photo_viewer_open(driver):
            print("📸 Photo viewer opened, extracting images...")
            gallery_images = navigate_and_extract_gallery_images(
                driver, save_dir)
        else:
            print("⚠️  Photo viewer did not open, trying direct image extraction...")
            # Fallback: try to extract images from current page
            gallery_images = extract_visible_images_after_click(
                driver, save_dir)

        # Check if we've been processing too long
        elapsed_time = time.time() - start_time
        if elapsed_time > max_gallery_time:
            print(
                f"⏰ Gallery processing timeout ({elapsed_time:.1f}s), stopping")

    except Exception as e:
        print(f"❌ Error extracting from gallery: {e}")

    return gallery_images


def is_photo_viewer_open(driver):
    """
    Check if Facebook photo viewer/modal is currently open

    Args:
        driver: Selenium WebDriver instance

    Returns:
        bool: True if photo viewer is open
    """
    try:
        # Common selectors for Facebook photo viewer
        viewer_selectors = [
            # Facebook photo viewer container
            "//div[@role='dialog'][.//img]",
            "//div[@data-testid='photo-viewer']",
            "//div[contains(@class, 'photoViewer')]",

            # Modal containers with large images
            "//div[@role='dialog'][contains(@style, 'position') and .//img]",
            "//div[contains(@class, 'modal') and .//img[@class and string-length(@src) > 50]]",

            # Lightbox indicators
            "//div[contains(@class, 'lightbox')]",
            "//div[@aria-modal='true'][.//img]",
        ]

        for selector in viewer_selectors:
            elements = driver.find_elements(By.XPATH, selector)
            if elements:
                for element in elements:
                    if element.is_displayed():
                        return True

        return False

    except Exception:
        return False


def navigate_and_extract_gallery_images(driver, save_dir="image_downloads", max_images=50):
    """
    Navigate through Facebook photo gallery and extract all images

    Args:
        driver: Selenium WebDriver instance
        save_dir: Directory to save images
        max_images: Maximum number of images to extract (safety limit)

    Returns:
        list: List of downloaded image file paths
    """
    extracted_images = []
    seen_images = set()
    consecutive_failures = 0
    max_consecutive_failures = 1  # Stop immediately when duplicate detected
    last_image_url = None
    start_time = time.time()
    max_extraction_time = 240  # 4 minutes max for gallery navigation

    try:
        print("🔄 Navigating through gallery...")

        for i in range(max_images):
            # Check timeout
            elapsed_time = time.time() - start_time
            if elapsed_time > max_extraction_time:
                print(
                    f"⏰ Gallery extraction timeout ({elapsed_time:.1f}s), stopping at image {i+1}")
                break

            print(f"📷 Processing image {i+1}...")

            # Extract current image
            current_image_url = get_current_gallery_image_url(driver)

            # Check if we got the same image as before (stuck/end)
            if current_image_url == last_image_url:
                consecutive_failures += 1
                print(
                    f"⚠️  Same image detected ({consecutive_failures}/{max_consecutive_failures})")

                if consecutive_failures >= max_consecutive_failures:
                    print("📍 Detected end of gallery (same image repeated)")
                    break
            else:
                consecutive_failures = 0  # Reset counter when we get a new image
                last_image_url = current_image_url

            if current_image_url and current_image_url not in seen_images:
                seen_images.add(current_image_url)

                # Download current image
                downloaded_path = download_facebook_image_with_session(
                    driver, current_image_url, save_dir
                )
                if downloaded_path:
                    extracted_images.append(downloaded_path)
                    print(
                        f"  ✅ Downloaded: {os.path.basename(downloaded_path)}")
                else:
                    print(
                        f"  ❌ Failed to download: {current_image_url[:50]}...")

            elif current_image_url in seen_images:
                print(f"  ⏭️  Already processed this image")
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    print("📍 Detected circular navigation, ending extraction")
                    break
            else:
                print(f"  ❌ No valid image URL found")
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    print("📍 No more valid images found, ending extraction")
                    break

            # If we already detected enough consecutive failures, don't try to navigate further
            if consecutive_failures >= max_consecutive_failures:
                print("📍 Stopping navigation due to consecutive failures")
                break

            # Try to navigate to next image
            if not go_to_next_gallery_image(driver):
                print("📍 Reached end of gallery or cannot navigate further")
                break

            time.sleep(1)  # Wait between navigation

        elapsed_time = time.time() - start_time
        print(
            f"✅ Gallery extraction complete: {len(extracted_images)} images in {elapsed_time:.1f}s")

    except Exception as e:
        print(f"❌ Error navigating gallery: {e}")

    return extracted_images


def get_current_gallery_image_url(driver):
    """
    Get the URL of currently displayed image in photo viewer

    Args:
        driver: Selenium WebDriver instance

    Returns:
        str: Image URL or None
    """
    try:
        # Selectors for the main image in photo viewer
        image_selectors = [
            # Facebook photo viewer main image
            "//div[@role='dialog']//img[contains(@class, 'spotlight') or @data-visualcompletion='media-vc-image']",
            "//div[@data-testid='photo-viewer']//img",
            "//div[contains(@class, 'photoViewer')]//img[not(contains(@class, 'thumbnail'))]",

            # Large modal images
            "//div[@role='dialog']//img[@class and string-length(@src) > 50]",
            "//div[@aria-modal='true']//img[not(contains(@class, 'icon')) and not(contains(@class, 'emoji'))]",

            # Primary image (largest)
            "//img[@src and contains(@src, 'scontent') and not(contains(@src, 'emoji'))]",
        ]

        for selector in image_selectors:
            try:
                images = driver.find_elements(By.XPATH, selector)

                # Find the largest/main image
                main_image = None
                max_size = 0

                for img in images:
                    if img.is_displayed():
                        try:
                            size = img.size
                            total_size = size['height'] * size['width']
                            if total_size > max_size:
                                max_size = total_size
                                main_image = img
                        except:
                            continue

                if main_image:
                    src = main_image.get_attribute('src')
                    if src and is_valid_facebook_content_image(src):
                        return src

            except Exception:
                continue

        return None

    except Exception:
        return None


def go_to_next_gallery_image(driver):
    """
    Navigate to next image in Facebook photo gallery

    Args:
        driver: Selenium WebDriver instance

    Returns:
        bool: True if successfully navigated to next image
    """
    try:
        # Get current image URL before trying to navigate
        current_image_before = get_current_gallery_image_url(driver)

        # Selectors for next button in photo viewer
        next_selectors = [
            # Standard next button
            "//div[@role='dialog']//div[@role='button'][@aria-label='Next photo' or @aria-label='Next' or @aria-label='다음']",
            "//button[@aria-label='Next photo' or @aria-label='Next' or @aria-label='다음']",

            # Arrow buttons
            "//div[@role='dialog']//*[contains(@class, 'next') or contains(@class, 'arrow-right')]",
            "//div[contains(@class, 'photoViewer')]//*[@role='button'][contains(@aria-label, 'Next')]",

            # Generic navigation - look for clickable elements on the right side
            "//div[@role='dialog']//div[@role='button'][position() > 1 and contains(@style, 'right')]",
            "//div[@role='dialog']//div[@role='button'][contains(@aria-label, 'next') or contains(@aria-label, 'Next')]",
        ]

        navigation_attempted = False

        for selector in next_selectors:
            try:
                next_buttons = driver.find_elements(By.XPATH, selector)
                for button in next_buttons:
                    if button.is_displayed() and button.is_enabled():
                        # Check if button is actually clickable (not disabled)
                        button_classes = button.get_attribute("class") or ""
                        button_style = button.get_attribute("style") or ""

                        # Skip if button appears disabled
                        if "disabled" in button_classes.lower() or "opacity: 0" in button_style:
                            continue

                        # Try to make button clickable by scrolling it into view
                        try:
                            # Scroll button into center of view
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                                button
                            )
                            time.sleep(0.5)

                            # Wait for any overlays to disappear
                            # Trigger any lazy overlays
                            driver.execute_script("window.scrollBy(0, 0);")
                            time.sleep(0.5)

                            # Try normal click first
                            button.click()
                            navigation_attempted = True
                            time.sleep(1)  # Wait for navigation

                            # Check if image actually changed
                            current_image_after = get_current_gallery_image_url(
                                driver)
                            if current_image_after != current_image_before:
                                return True
                            else:
                                print("⚠️  Button clicked but image didn't change")

                        except Exception as click_error:
                            # If normal click fails, try JavaScript click
                            try:
                                print(
                                    f"⚠️  Normal click failed, trying JavaScript click: {click_error}")
                                driver.execute_script(
                                    "arguments[0].click();", button)
                                navigation_attempted = True
                                time.sleep(1)

                                # Check if image changed with JS click
                                current_image_after = get_current_gallery_image_url(
                                    driver)
                                if current_image_after != current_image_before:
                                    return True
                                else:
                                    print(
                                        "⚠️  JavaScript click didn't change image")

                            except Exception as js_error:
                                print(
                                    f"⚠️  JavaScript click also failed: {js_error}")
                                continue

            except Exception:
                continue

        # Fallback: try arrow key navigation only if no buttons were found
        if not navigation_attempted:
            try:
                from selenium.webdriver.common.keys import Keys
                from selenium.webdriver.common.action_chains import ActionChains

                # Try to focus on the photo viewer dialog
                dialogs = driver.find_elements(
                    By.XPATH, "//div[@role='dialog']")
                focused = False

                for dialog in dialogs:
                    try:
                        if dialog.is_displayed():
                            # Click in the center of the dialog to focus it
                            driver.execute_script(
                                "arguments[0].focus(); arguments[0].click();",
                                dialog
                            )
                            time.sleep(0.5)
                            focused = True
                            break
                    except:
                        continue

                if focused:
                    # Send arrow key to focused dialog
                    ActionChains(driver).send_keys(Keys.ARROW_RIGHT).perform()
                    time.sleep(1)

                    # Check if image changed with arrow key
                    current_image_after = get_current_gallery_image_url(driver)
                    if current_image_after != current_image_before:
                        return True
                    else:
                        print("⚠️  Arrow key navigation didn't change image")
                else:
                    print("⚠️  Could not focus dialog for arrow key navigation")

            except Exception as key_error:
                print(f"⚠️  Arrow key navigation failed: {key_error}")

        # If we reach here, navigation failed
        print("❌ All navigation methods failed")
        return False

    except Exception as e:
        print(f"❌ Error in navigation: {e}")
        return False


def close_photo_viewer(driver):
    """
    Close Facebook photo viewer/modal

    Args:
        driver: Selenium WebDriver instance

    Returns:
        bool: True if successfully closed
    """
    try:
        # Selectors for close button
        close_selectors = [
            "//div[@role='dialog']//div[@aria-label='Close' or @aria-label='닫기']",
            "//button[@aria-label='Close' or @aria-label='닫기']",
            "//div[@role='dialog']//*[text()='×' or text()='✕']",
            "//div[contains(@class, 'close')][@role='button']",
        ]

        for selector in close_selectors:
            try:
                close_buttons = driver.find_elements(By.XPATH, selector)
                for button in close_buttons:
                    if button.is_displayed() and button.is_enabled():
                        button.click()
                        time.sleep(1)
                        return True
            except Exception:
                continue

        # Fallback: ESC key
        try:
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.action_chains import ActionChains

            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1)
            return True
        except Exception:
            pass

        return False

    except Exception:
        return False


def extract_visible_images_from_post(driver, article_element):
    """
    Extract visible images from Facebook post (non-gallery images)

    Args:
        driver: Selenium WebDriver instance
        article_element: WebElement for the article

    Returns:
        list: List of image URLs
    """
    images = []

    try:
        # Find visible images in the post
        img_elements = article_element.find_elements(By.TAG_NAME, "img")

        for img in img_elements:
            if img.is_displayed():
                src = img.get_attribute('src')
                if src and is_valid_facebook_content_image(src):
                    images.append(src)

                # Also check data-src for lazy loaded images
                data_src = img.get_attribute('data-src')
                if data_src and is_valid_facebook_content_image(data_src):
                    images.append(data_src)

    except Exception as e:
        print(f"❌ Error extracting visible images: {e}")

    return list(dict.fromkeys(images))  # Remove duplicates


def extract_visible_images_after_click(driver, save_dir):
    """
    Extract images from page after clicking (fallback when modal doesn't open)

    Args:
        driver: Selenium WebDriver instance
        save_dir: Directory to save images

    Returns:
        list: List of downloaded image file paths
    """
    downloaded_images = []

    try:
        # Wait for page to update after click
        time.sleep(2)

        # Find all images on current page
        all_images = driver.find_elements(By.TAG_NAME, "img")

        for img in all_images:
            if img.is_displayed():
                src = img.get_attribute('src')
                if src and is_valid_facebook_content_image(src):
                    downloaded_path = download_facebook_image_with_session(
                        driver, src, save_dir)
                    if downloaded_path:
                        downloaded_images.append(downloaded_path)

    except Exception as e:
        print(f"❌ Error in fallback image extraction: {e}")

    return downloaded_images


def is_valid_facebook_content_image(url):
    """
    Check if URL is a valid Facebook content image (not emoji/icon)

    Args:
        url: Image URL to validate

    Returns:
        bool: True if valid content image
    """
    if not url or len(url) < 20:
        return False

    # Must be from Facebook content domains
    valid_domains = [
        'scontent.com',
        'scontent-',
        'scontent.',
        'fbcdn.net',
        'cdninstagram.com'
    ]

    # Skip UI elements and emoji
    skip_patterns = [
        'emoji', 'icon', 'static', 'rsrc.php', '_16x16', '_20x20', '_24x24', '_32x32',
        'blank.gif', 'spacer.gif', '1x1', 'pixel.png'
    ]

    for pattern in skip_patterns:
        if pattern in url.lower():
            return False

    return any(domain in url for domain in valid_domains)


def download_facebook_image_with_session(driver, img_url, save_dir="image_downloads"):
    """
    Download Facebook image using Selenium session cookies

    Args:
        driver: Selenium WebDriver instance
        img_url: Image URL to download
        save_dir: Directory to save image

    Returns:
        str: Local file path or None if failed
    """
    try:
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Get cookies from Selenium session
        cookies = driver.get_cookies()
        session = requests.Session()

        # Transfer cookies
        for cookie in cookies:
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=cookie.get('domain')
            )

        # Set headers
        headers = {
            'User-Agent': driver.execute_script("return navigator.userAgent;"),
            'Referer': 'https://www.facebook.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        }

        response = session.get(img_url, headers=headers,
                               stream=True, timeout=30)

        if response.status_code == 200:
            # Generate filename
            url_hash = hashlib.md5(img_url.encode()).hexdigest()[:12]

            # Determine file extension
            content_type = response.headers.get('content-type', '')
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'webp' in content_type:
                ext = '.webp'
            else:
                ext = '.jpg'  # Default

            filename = f"fb_gallery_{url_hash}{ext}"
            filepath = os.path.join(save_dir, filename)

            # Save image
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            return filepath
        else:
            print(f"❌ HTTP {response.status_code}: {img_url[:50]}...")
            return None

    except Exception as e:
        print(f"❌ Download error: {e}")
        return None


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
