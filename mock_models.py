#!/usr/bin/env python

class MockFacebook:
    class Field:
        def __init__(self, name):
            self.name = name

    kwrd = Field("keyword")
    feed_url = Field("url")
    publish_date = Field("publish_date")
    content = Field("content")
    images = Field("images")
    videos = Field("videos")


class FacebookData:
    def __init__(self, keyword=None, url=None, publish_date=None, content=None, images=None, videos=None):
        self.keyword = keyword
        self.url = url
        self.publish_date = publish_date
        self.content = content
        self.images = images or []
        self.videos = videos or []

    def to_dict(self):
        return {
            MockFacebook.kwrd.name: self.keyword,
            MockFacebook.feed_url.name: self.url,
            MockFacebook.publish_date.name: self.publish_date,
            MockFacebook.content.name: self.content,
            MockFacebook.images.name: self.images,
            MockFacebook.videos.name: self.videos,
        }

    def __repr__(self):
        return (f"FacebookData(keyword='{self.keyword}', "
                f"url='{self.url[:50] if self.url else None}...', "
                f"publish_date='{self.publish_date}', "
                f"content='{self.content[:50] if self.content else None}...', "
                f"images={len(self.images) if self.images else 0}, "
                f"videos={len(self.videos) if self.videos else 0})")


if __name__ == "__main__":
    print("📝 Testing MockFacebook fields:")
    print(f"  kwrd.name: {MockFacebook.kwrd.name}")
    print(f"  feed_url.name: {MockFacebook.feed_url.name}")
    print(f"  publish_date.name: {MockFacebook.publish_date.name}")
    print(f"  content.name: {MockFacebook.content.name}")
    print(f"  images.name: {MockFacebook.images.name}")
    print(f"  videos.name: {MockFacebook.videos.name}")

    print("\n📊 Testing FacebookData:")
    from datetime import datetime, timezone

    data = FacebookData(
        keyword="test",
        url="https://facebook.com/posts/123",
        publish_date=datetime.now(timezone.utc),
        content="This is a test post content",
        images=["https://scontent.com/image1.jpg",
                "https://scontent.com/image2.jpg"],
        videos=["https://video.com/video1.mp4"]
    )

    print(f"  Object: {data}")
    print(f"  Dict: {data.to_dict()}")
