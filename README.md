# Standalone Facebook Spider

Đây là phiên bản độc lập của Facebook Hashtag Spider

## Cài đặt

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

## Cách sử dụng

### Chạy với keyword mặc định

```bash
python facebook_spider.py
```

### Chạy với keyword tùy chỉnh

```bash
python facebook_spider.py vietnam
python facebook_spider.py "artificial intelligence"
```

### Chạy headless (ẩn browser)

Sửa trong file `facebook_spider.py`:

```python
"HEADLESS": True,  # Thay False thành True
```

## Tính năng

- ✅ Crawl bài viết từ Facebook hashtag
- ✅ Xử lý popup cookies tự động
- ✅ Hỗ trợ tiếng Hàn và tiếng Anh
- ✅ Tự động quản lý ChromeDriver
- ✅ Log chi tiết quá trình crawling
- ✅ Không phụ thuộc external database

## Dữ liệu thu thập

Spider thu thập:

- **Keyword**: Hashtag tìm kiếm
- **URL**: Link bài viết
- **Publish Date**: Ngày đăng (nếu có)
- **Content**: Nội dung bài viết

## Cấu trúc files

```
standalone_facebook_spider/
├── facebook_spider.py      # Spider chính
├── requirements.txt        # Dependencies
└── README.md              # Hướng dẫn này
```

## Customization

### Thay đổi XPath selectors

Trong class `FacebookHashtagSpider`:

```python
articles_xpath = "//div[@role='article']/div"
description_xpath = ".//div[@data-ad-comet-preview='message']//span[@dir='auto']//text()"
article_header_xpath = ".//div//span/a[@aria-label!='확대하기' and @role='link']"
```

### Thay đổi callback function

```python
def custom_callback(data):
    # Xử lý dữ liệu theo ý muốn
    print(f"Got data: {data}")

    # Lưu vào file
    with open('facebook_data.json', 'a') as f:
        json.dump(data, f)
        f.write('\n')

# Sử dụng
run_facebook_spider_with_callback(keyword="test", callback=custom_callback)
```

### Thêm scroll để lấy nhiều posts

Trong `click_allowed_cookies_button`:

```python
def click_allowed_cookies_button(driver):
    # Existing code...

    # Scroll để load thêm posts
    for i in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
```

## Troubleshooting

### ChromeDriver issues

```bash
# Xóa cache ChromeDriver cũ
rm -rf ~/.wdm  # Linux/Mac
# hoặc
rmdir /s %USERPROFILE%\.wdm  # Windows
```

### Facebook chặn requests

- Thay đổi User-Agent trong `get_selenium_settings()`
- Tăng `DOWNLOAD_DELAY`
- Sử dụng proxy

### Memory issues

- Set `HEADLESS=True`
- Giảm `CONCURRENT_REQUESTS`
- Restart spider định kỳ

## Giới hạn

- Facebook có thể chặn automated requests
- Số lượng posts thu thập phụ thuộc vào Facebook's infinite scroll
- Cần internet connection
- Chrome browser dependency

## So sánh với bản gốc

| Feature      | Original            | Standalone    |
| ------------ | ------------------- | ------------- |
| Database     | ✅ PostgreSQL       | ❌ Mock data  |
| Config       | ✅ TOML files       | ❌ Hardcoded  |
| Celery       | ✅ Async tasks      | ❌ Direct run |
| Logging      | ✅ Advanced         | ✅ Basic      |
| Dependencies | ❌ Heavy            | ✅ Minimal    |
| Portability  | ❌ Project-specific | ✅ Standalone |
