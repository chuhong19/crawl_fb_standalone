# Facebook Gallery Image Extraction

## 🎯 Mục đích

Tính năng mới này giải quyết vấn đề **Facebook chỉ hiển thị một số ảnh giới hạn trên giao diện chính** của post. Nhiều ảnh bị ẩn và chỉ có thể xem được khi click vào photo gallery.

## ⚡ Tính năng mới

### 🔍 **Smart Gallery Detection**

- Tự động tìm các photo gallery triggers như:
  - Text indicators: `"+5 more photos"`, `"See all photos"`
  - Photo grid containers
  - Clickable photo elements
  - Multiple image containers

### 🖱️ **Interactive Navigation**

- Click vào gallery triggers để mở photo viewer
- Navigate qua tất cả ảnh trong gallery bằng:
  - Next/Previous buttons
  - Arrow key navigation
  - Automatic modal detection

### 💾 **High-Quality Downloads**

- Download ảnh full-resolution từ photo viewer
- Sử dụng session cookies để bypass restrictions
- Intelligent file naming và organization
- Support multiple formats (JPG, PNG, WebP)

### 🛡️ **Robust Error Handling**

- Graceful fallbacks nếu gallery không mở được
- Continue crawling nếu có lỗi với individual posts
- Smart duplicate detection
- Modal closing after extraction

## 🏗️ **Architecture**

### **Core Functions**

```python
# Main entry point - extract ALL images from a post
extract_all_images_from_facebook_post(driver, article_element, save_dir)

# Find gallery triggers in a post
find_photo_gallery_triggers(driver, article_element)

# Click and extract from gallery
extract_images_from_gallery(driver, gallery_trigger, save_dir)

# Navigate through gallery images
navigate_and_extract_gallery_images(driver, save_dir)
```

### **Workflow**

1. **Visible Images**: Extract directly visible images first
2. **Gallery Detection**: Scan for gallery triggers
3. **Gallery Interaction**: Click triggers to open photo viewers
4. **Navigation**: Loop through all images in gallery
5. **Download**: Get high-res versions with session cookies
6. **Cleanup**: Close modals and continue to next post

## 📊 **Usage**

### **Automatic Integration**

Tính năng đã được tích hợp vào existing spiders:

```bash
# Facebook page crawling (with gallery extraction)
python main.py facebook_page --pagename "your_page_name"

# Facebook hashtag crawling (with gallery extraction)
python main.py facebook --keyword "your_hashtag"
```

### **Test Script**

```bash
# Test gallery extraction functionality
python test_gallery_extraction.py
```

## 🔧 **Configuration**

### **Settings trong `media_extractor.py`**

```python
# Maximum images per gallery (safety limit)
max_images = 50

# Save directory
save_dir = "image_downloads"

# Timeout cho navigation
navigation_timeout = 30  # seconds
```

### **Gallery Selectors**

Có thể customize các XPath selectors để detect galleries:

```python
gallery_selectors = [
    # Photo count indicators
    ".//div[contains(text(), 'more photo') or contains(text(), '+')]",
    ".//span[contains(text(), 'more photo') or contains(text(), '+')]",

    # Photo grid containers
    ".//div[contains(@class, 'photoGrid')]",
    ".//div[contains(@class, 'photoContainer') and count(.//img) > 1]",

    # Clickable elements
    ".//div[@role='button'][.//img]",
    ".//a[@role='link'][.//img]",
]
```

## 📈 **Performance**

### **Before vs After**

| Aspect              | Before        | After           |
| ------------------- | ------------- | --------------- |
| **Images per post** | 1-3 visible   | 5-50+ total     |
| **Image quality**   | Thumbnails    | Full resolution |
| **Hidden content**  | ❌ Missed     | ✅ Extracted    |
| **Gallery posts**   | ❌ Incomplete | ✅ Complete     |

### **Example Output**

```
🔍 Looking for photo galleries in post...
📷 Found 2 directly visible images
🖼️  Found 1 photo gallery trigger(s)
📂 Processing gallery 1/1
🖱️  Clicking gallery trigger...
📸 Photo viewer opened, extracting images...
🔄 Navigating through gallery...
📷 Processing image 1...
  ✅ Downloaded: fb_gallery_a1b2c3d4e5f6.jpg
📷 Processing image 2...
  ✅ Downloaded: fb_gallery_b2c3d4e5f6a1.jpg
📷 Processing image 3...
  ✅ Downloaded: fb_gallery_c3d4e5f6a1b2.jpg
📍 Reached end of gallery or cannot navigate further
✅ Gallery extraction complete: 3 images
🎯 Extracted 5 images from post (including galleries)
```

## 🚫 **Limitations**

1. **Facebook Rate Limiting**: Facebook có thể throttle requests nếu crawl quá nhanh
2. **Dynamic Content**: Some galleries load với complex JavaScript
3. **Login Requirements**: Một số content cần login để access
4. **Modal Variations**: Facebook thường thay đổi UI structure

## 🛠️ **Troubleshooting**

### **Gallery không mở được**

```python
# Check selectors trong find_photo_gallery_triggers()
# Update XPath patterns nếu Facebook thay đổi UI
```

### **Navigation thất bại**

```python
# Check next button selectors trong go_to_next_gallery_image()
# Try arrow key fallback
```

### **Download lỗi**

```python
# Check session cookies transfer
# Verify image URL validation
```

## 🔄 **Future Improvements**

- [ ] Support video galleries
- [ ] Parallel gallery processing
- [ ] Advanced deduplication
- [ ] Instagram integration
- [ ] Performance monitoring
- [ ] Auto-retry mechanisms

## 📝 **Technical Notes**

- **WebElement Mapping**: Convert Scrapy selectors to Selenium WebElements
- **Session Persistence**: Maintain cookies across requests
- **Modal Management**: Proper cleanup để avoid UI conflicts
- **Memory Management**: Close resources after extraction
- **Error Recovery**: Multiple fallback strategies

---

**Note**: Tính năng này significantly tăng số lượng và chất lượng ảnh được extract từ Facebook posts, đặc biệt hữu ích cho data collection và content analysis.
