# SNS Crawl Data

## 🚀 Installation

### 1. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Chrome browser

- Make sure Chrome browser is installed
- Spider will automatically download ChromeDriver via `webdriver-manager`

## 📖 Usage

### SNS Crawling

```bash
# Facebook
python main.py facebook <pagename>

# Twitter
python main.py twitter --profile <profile_name> --limit <limit>
python main.py twitter --hashtag <hashtag> --limit <limit>

# Telegram
python main.py telegram --channel <channel_name> --limit <limit>

# TikTok
python main.py tiktok --profile <profile_name> --limit <limit>
python main.py tiktok --hashtag <hashtag> --limit <limit>
```
