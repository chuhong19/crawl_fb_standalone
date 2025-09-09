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
# BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAPNU3gEAAAAAs3SojN1eRkG5Oei3LGG9%2FSeyqvs%3DymVvkUOo68cSVpOH1QComY009OE6nC2LYAjKhuBXyKWua1O36E"
# BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAFDR3wEAAAAA99ICr1iFK57SCTi6rxjqz5rZzxk%3D25VRv1OUTa9mXnF8ssM56F7jaVKMNg8nwBQX9k77Fvip7Fz2MS"
# BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAJzR3wEAAAAAxC7Wsx3m8ug9RTRounw1ieuYEhU%3DfOSNHczXh2za1fsNdhgGxZ9xxYZxQrnrbBHHgEGmqzB0YRcoTt"
# BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAM3R3wEAAAAAnC%2B6IQgwyrMbERZsFSF5XN4aZOU%3DISho4l9W8iLnTta6hd5t4FR8C6lu91iG3HjETQLAJ6RONX5s9A"
BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAAPS3wEAAAAAgs7hG9UlcJmC%2BWuEIZdfJFtcuVY%3DJKC0afClSezvq05it2MxvLfEVkKqZRO8EXq86AebTY5lQpYJkr"

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

def get_latest_saved_id(json_filename):
    """Return the max tweet ID already saved, or None if no file."""
    path = os.path.join(OUTPUT_FOLDER, json_filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        return None
    # Tweet IDs are numeric strings → pick the max
    return max(int(t["id"]) for t in data if "id" in t)

def extract_tweet_media(tweets_data):
    """Attach all media (including from quoted/retweeted tweets) to each tweet."""
    media_map = {}
    includes = tweets_data.get("includes", {})

    # Build media lookup
    for media in includes.get("media", []):
        media_map[media["media_key"]] = media

    # Build referenced tweets lookup (quotes/retweets)
    ref_map = {}
    for ref_tweet in includes.get("tweets", []):
        ref_map[ref_tweet["id"]] = ref_tweet

    for tweet in tweets_data.get("data", []):
        tweet["media_files"] = []

        # 1️⃣ Direct media on this tweet
        attachments = tweet.get("attachments", {})
        for key in attachments.get("media_keys", []):
            if key in media_map:
                tweet["media_files"].append(media_map[key])

        # 2️⃣ Media from referenced tweets (quotes / retweets)
        for ref in tweet.get("referenced_tweets", []):
            ref_tweet = ref_map.get(ref["id"])
            if ref_tweet:
                for key in ref_tweet.get("attachments", {}).get("media_keys", []):
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


def append_tweet_json(tweet, filename):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    path = os.path.join(OUTPUT_FOLDER, filename)

    # If file doesn’t exist, create empty array
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f)

    # Load existing data
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Append new tweet if not already stored
    if not any(t["id"] == tweet["id"] for t in data):
        data.append(tweet)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info(f"💾 Appended tweet {tweet['id']} → {path}")


def process_and_save(tweets_data, subfolder_name, json_filename):
    """Attach media, download them, and append tweets to JSON"""
    tweets_data = extract_tweet_media(tweets_data)

    for tweet in tweets_data.get("data", []):
        tweet_id = tweet["id"]

        # Save media
        for media in tweet.get("media_files", []):
            if media["type"] == "photo":
                url = media.get("url")
                if url:
                    download_file(url, f"{tweet_id}.jpg", OUTPUT_FOLDER, subfolder_name)
            elif media["type"] in ("video", "animated_gif"):
                download_video(media, tweet_id, OUTPUT_FOLDER, subfolder_name)

        # Append JSON
        append_tweet_json(tweet, json_filename)

    return tweets_data


def crawl_user_tweets(user_id, subfolder_name, limit):
    headers = create_headers(BEARER_TOKEN)
    url = f"https://api.x.com/2/users/{user_id}/tweets"
    params = {
        "tweet.fields": "created_at,public_metrics,attachments,referenced_tweets",
        "expansions": "attachments.media_keys,referenced_tweets.id",
        "media.fields": "media_key,type,url,preview_image_url,variants,alt_text",
        "max_results": 5,
    }

    fetched = 0
    next_token = None
    json_filename = f"{subfolder_name}.json"

    since_id = get_latest_saved_id(json_filename)
    if since_id:
        params["since_id"] = since_id
        logging.info(f"⏩ Skipping old tweets, fetching only newer than ID {since_id}")

    while True:
        if next_token:
            params["pagination_token"] = next_token

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            logging.error(f"Error fetching tweets: {response.status_code} {response.text}")
            break

        data = response.json()
        processed = process_and_save(data, subfolder_name, json_filename)

        fetched += len(processed.get("data", []))
        if limit and fetched >= limit:
            logging.info(f"Reached limit of {limit} tweets.")
            break

        meta = data.get("meta", {})
        next_token = meta.get("next_token")
        if not next_token:
            logging.info("No more tweets available.")
            break


def crawl_hashtag_tweets(hashtag, subfolder_name, limit):
    headers = create_headers(BEARER_TOKEN)
    url = "https://api.x.com/2/tweets/search/recent"
    params = {
        "query": f"#{hashtag} -is:retweet",
        "tweet.fields": "created_at,public_metrics,attachments,referenced_tweets",
        "expansions": "attachments.media_keys,referenced_tweets.id",
        "media.fields": "media_key,type,url,preview_image_url,variants,alt_text",
        "max_results": 5
    }

    fetched = 0
    next_token = None
    json_filename = f"{subfolder_name}.json"

    since_id = get_latest_saved_id(json_filename)
    if since_id:
        params["since_id"] = since_id
        logging.info(f"⏩ Skipping old tweets, fetching only newer than ID {since_id}")

    while True:
        if next_token:
            params["next_token"] = next_token

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            logging.error(f"Error fetching hashtag tweets: {response.status_code} {response.text}")
            break

        data = response.json()
        processed = process_and_save(data, subfolder_name, json_filename)

        fetched += len(processed.get("data", []))
        if limit and fetched >= limit:
            logging.info(f"Reached limit of {limit} tweets.")
            break

        meta = data.get("meta", {})
        next_token = meta.get("next_token")
        if not next_token:
            logging.info("No more tweets available.")
            break


class TwitterCrawler:
    @staticmethod
    def crawl(profile=None, hashtag=None, limit=None):
        """Crawl tweets by user or hashtag.
        - If limit is given: fetch up to that many tweets.
        - If limit is None: fetch all available tweets.
        """
        if profile:
            subfolder_name = profile
            logging.info(f"Fetching tweets for @{profile}...")
            user_id = get_user_id(profile)
            crawl_user_tweets(user_id, subfolder_name, limit)
        elif hashtag:
            subfolder_name = f"hashtag_{hashtag}"
            logging.info(f"Fetching tweets for #{hashtag}...")
            crawl_hashtag_tweets(hashtag, subfolder_name, limit)
        else:
            logging.error("You must provide either a profile or a hashtag.")

