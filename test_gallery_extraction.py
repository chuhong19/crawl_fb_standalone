#!/usr/bin/env python
"""
Test script for Facebook gallery image extraction functionality

This script demonstrates the new capability to extract ALL images from Facebook posts,
including hidden images in photo galleries that require clicking to access.
"""

from facebook.facebook_spider_page import FacebookPageCrawler
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def test_gallery_extraction():
    """
    Test the new gallery image extraction feature
    """
    print("🧪 Testing Facebook Gallery Image Extraction")
    print("=" * 60)

    # Test with a page that likely has multiple images per post
    test_pages = [
        "test",  # Default test page
        # Add more test pages here if needed
    ]

    for page in test_pages:
        print(f"\n🔍 Testing with page: {page}")
        print("-" * 40)

        try:
            crawler = FacebookPageCrawler()
            crawler.crawl(pagename=page)

        except Exception as e:
            print(f"❌ Error testing page {page}: {e}")
            continue

    print("\n✅ Gallery extraction test completed!")
    print("\nNOTE: Check the 'image_downloads' folder for extracted images")
    print("The new system will:")
    print("  🎯 Find gallery triggers (like '+3 more photos')")
    print("  🖱️  Click to open photo viewers")
    print("  🔄 Navigate through all images in galleries")
    print("  💾 Download high-resolution versions")


if __name__ == "__main__":
    test_gallery_extraction()
