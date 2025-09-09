import fire
from twitter.twitter_spider import TwitterCrawler
from telegram.telegram_spider import TelegramCrawler
from facebook.facebook_spider import FacebookPageCrawler


class SpiderCrawler:
    def twitter(self, profile=None, hashtag=None, limit=None):
        """Crawl Twitter"""
        TwitterCrawler().crawl(profile=profile, hashtag=hashtag, limit=limit)

    def telegram(self, channel=None, limit=None):
        """Crawl Telegram"""
        TelegramCrawler().crawl(channel=channel, limit=limit)

    def facebook(self, pagename=None):
        """Crawl Facebook page by pagename"""
        FacebookPageCrawler().crawl(pagename=pagename)


if __name__ == "__main__":
    fire.Fire(SpiderCrawler)
