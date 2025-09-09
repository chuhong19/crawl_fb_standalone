import os, requests, json, logging, yt_dlp

OUTPUT_FOLDER = "downloads/tiktok"

def download_file(url, filename, folder=OUTPUT_FOLDER):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        logging.info(f"Saved file: {path}")
        return path
    else:
        logging.error(f"Failed to download {url}")
        return None


def download_video(link, folder=OUTPUT_FOLDER):
    os.makedirs(folder, exist_ok=True)
    ydl_opts = {
        "retries": 5,
        "socket_timeout": 60,
        "outtmpl": f"{folder}/%(id)s.%(ext)s",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([link])
    logging.info(f"Downloaded video: {link}")
    return True

def save_progress(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    logging.info(f"✅ Saved {len(data['videos'])} total videos to {path}")