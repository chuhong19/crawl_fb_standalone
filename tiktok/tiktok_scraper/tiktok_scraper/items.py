# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class TikTokVideo(scrapy.Item):
    index = scrapy.Field()
    title = scrapy.Field()
    link = scrapy.Field()
    thumbnail = scrapy.Field()
