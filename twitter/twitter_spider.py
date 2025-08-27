import os
import sys
import json
import logging
import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===== CONFIG =====
BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAPNU3gEAAAAAs3SojN1eRkG5Oei3LGG9%2FSeyqvs%3DymVvkUOo68cSVpOH1QComY009OE6nC2LYAjKhuBXyKWua1O36E"
OUTPUT_FOLDER = "downloads/twitter"
MEDIA_FOLDER = f"{OUTPUT_FOLDER}/medias"

def create_headers(bearer_token):
    return {"Authorization": f"Bearer {bearer_token}"}

def get_user_id(username):
    url = f"https://api.x.com/2/users/by/username/{username}"
    headers = create_headers(BEARER_TOKEN)
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logging.error(f"Error fetching user ID: {response.status_code} {response.text}")
        sys.exit(1)
    return response.json()["data"]["id"]


def get_user_tweets(user_id, max_results=10):
    url = f"https://api.x.com/2/users/{user_id}/tweets"
    params = {
        "max_results": max_results,
        "tweet.fields": "created_at,public_metrics",
        "expansions": "attachments.media_keys",
        "media.fields": "url,preview_image_url,type,variants"
    }
    headers = create_headers(BEARER_TOKEN)
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        logging.error(f"Error fetching tweets: {response.status_code} {response.text}")
        sys.exit(1)
    return response.json()


def get_hashtag_tweets(hashtag, max_results=10):
    url = "https://api.x.com/2/tweets/search/recent"
    query = f"#{hashtag} -is:retweet"
    params = {
        "query": query,
        "max_results": max_results,
        "tweet.fields": "created_at,public_metrics,author_id",
        "expansions": "attachments.media_keys",
        "media.fields": "url,preview_image_url,type,variants"
    }
    headers = create_headers(BEARER_TOKEN)
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        logging.error(f"Error fetching hashtag tweets: {response.status_code} {response.text}")
        sys.exit(1)
    return response.json()


def extract_tweet_media(tweets_data):
    media_map = {}
    includes = tweets_data.get("includes", {})
    for media in includes.get("media", []):
        media_map[media["media_key"]] = media

    for tweet in tweets_data.get("data", []):
        tweet["media_files"] = []
        attachments = tweet.get("attachments", {})
        for key in attachments.get("media_keys", []):
            if key in media_map:
                tweet["media_files"].append(media_map[key])
    return tweets_data


def download_file(url, filename, base_folder, subfolder_name):
    folder = os.path.join(base_folder, subfolder_name)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        logging.info(f"✅ Saved {path}")
    else:
        logging.error(f"❌ Failed to download {url}")


def download_video(media, filename, base_folder, subfolder_name):
    variants = media.get("variants", [])
    mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
    if not mp4s:
        logging.warning("No MP4 variant found for video")
        return None
    best = max(mp4s, key=lambda v: v.get("bit_rate", 0))
    url = best["url"]
    return download_file(url, f"{filename}.mp4", base_folder, subfolder_name)


class TwitterCrawler:
    def crawl(self, user=None, hashtag=None, limit=10):
        """Crawl tweets by user or hashtag"""
        if user:
            subfolder_name = user
            logging.info(f"Fetching tweets for @{user}...")
            user_id = get_user_id(user)
            tweets_data = get_user_tweets(user_id, limit)
            filename = os.path.join(OUTPUT_FOLDER, f"{user}_twitter.json")
        elif hashtag:
            subfolder_name = f"hashtag_{hashtag}"
            logging.info(f"Fetching tweets for #{hashtag}...")
            tweets_data = get_hashtag_tweets(hashtag, limit)
            filename = os.path.join(OUTPUT_FOLDER, f"hashtag_{hashtag}_twitter.json")
        else:
            logging.error("You must specify either --user or --hashtag")
            return

        tweets_data = extract_tweet_media(tweets_data)

        for i, tweet in enumerate(tweets_data.get("data", []), 1):
            text = tweet["text"].replace("\n", " ")
            logging.info(f"{i}. {text}")

            for j, media in enumerate(tweet.get("media_files", []), 1):
                idx = f"tweet_{i}_{j}"
                if media["type"] == "photo":
                    download_file(media["url"], f"{idx}.jpg", MEDIA_FOLDER, subfolder_name)
                elif media["type"] in ["video", "animated_gif"]:
                    download_video(media, idx, MEDIA_FOLDER, subfolder_name)

        # Save to JSON
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(tweets_data, f, indent=2, ensure_ascii=False)

        logging.info(f"✅ Tweets saved to {filename}")
