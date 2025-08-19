#!/usr/bin/env python

import re
from urllib.parse import urljoin, urlparse


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

    # Remove Facebook's image processing parameters
    img_url = re.sub(r'[?&]_nc_.*', '', img_url)
    img_url = re.sub(r'[?&]ccb=.*', '', img_url)
    img_url = re.sub(r'[?&]_nc_ht=.*', '', img_url)

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
        'scontent-',  # scontent-xxx.xx.fbcdn.net
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
