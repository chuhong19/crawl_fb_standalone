import fire
from twitter.twitter_spider import TwitterCrawler
from tiktok.tiktok_spider import TikTokCrawler
from telegram.telegram_spider import TelegramCrawler
from facebook.facebook_spider import FacebookPageCrawler


class SpiderCrawler:
    def twitter(self, user=None, hashtag=None, limit=10):
        """Crawl Twitter"""
        TwitterCrawler().crawl(user=user, hashtag=hashtag, limit=limit)

    def tiktok(self, profile=None, hashtag=None, limit=None):
        """Crawl TikTok"""
        TikTokCrawler().crawl(profile=profile, hashtag=hashtag, limit=limit)

    def telegram(self, channel=None, limit=None):
        """Crawl Telegram"""
        TelegramCrawler().crawl(channel=channel, limit=limit)

    def facebook(self, pagename=None):
        """Crawl Facebook page by pagename"""
        FacebookPageCrawler().crawl(pagename=pagename)


if __name__ == "__main__":
    fire.Fire(SpiderCrawler)
