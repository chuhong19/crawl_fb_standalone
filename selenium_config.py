#!/usr/bin/env python

def get_selenium_settings():
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
        "LOG_ENABLED": False,
        "LOG_LEVEL": "CRITICAL",
    }


def get_chrome_options():
    from selenium.webdriver.chrome.options import Options

    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--headless')

    return chrome_options


if __name__ == "__main__":
    settings = get_selenium_settings()
    print("🔧 Selenium Settings:")
    for key, value in settings.items():
        print(f"  {key}: {value}")

    print("\n🌐 Chrome Options:")
    options = get_chrome_options()
    print(f"  Arguments: {options.arguments}")
