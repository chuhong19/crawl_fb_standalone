# SNS Crawl Data

## 🚀 Cài đặt

### 1. Tạo môi trường ảo

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# hoặc
venv\Scripts\activate     # Windows
```

### 2. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 3. Cài đặt Chrome browser

- Đảm bảo có Chrome browser được cài đặt
- Spider sẽ tự động download ChromeDriver qua `webdriver-manager`

## 📖 Cách sử dụng

### Facebook Page Crawling

```bash
# Syntax đơn giản
python main.py facebook <pagename>

# Hoặc với parameter rõ ràng
python main.py facebook --pagename <pagename>

# Ví dụ
python main.py facebook lailyhuynh
python main.py facebook --pagename lailyhuynh
```

### Các Platform khác (nếu cần)

```bash
# Twitter
python main.py twitter --profile <tên profile> --limit <giới hạn>
python main.py twitter --hashtag <hashtag> --limit <giới hạn>

# Telegram
python main.py telegram --channel <tên channel> --limit <giới hạn>

# TikTok
python main.py tiktok --profile <tên profile> --limit <giới hạn>
python main.py tiktok --hashtag <hashtag> --limit <giới hạn>
```
