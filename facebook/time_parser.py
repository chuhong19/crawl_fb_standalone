#!/usr/bin/env python

from datetime import datetime, timezone, timedelta
import re


def parse_relative_time(relative_text):
    if not relative_text:
        return None

    text = relative_text.lower().strip()

    absolute_patterns = [
        r'(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)',
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})',
        r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})',
    ]

    months_map = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
        'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9,
        'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }

    for pattern in absolute_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                groups = match.groups()
                if groups[0].isdigit():
                    day = int(groups[0])
                    month = months_map.get(groups[1])
                else:
                    month = months_map.get(groups[0])
                    day = int(groups[1])

                if month and 1 <= day <= 31:
                    current_year = datetime.now().year
                    return datetime(current_year, month, day, tzinfo=timezone.utc)
            except (ValueError, KeyError):
                continue

    patterns = [
        (r'(\d+)\s*m(?:in|inutes?)?(?:\s+ago)?', 'minutes'),
        (r'(\d+)\s*h(?:r|rs|ours?)?(?:\s+ago)?', 'hours'),
        (r'(\d+)\s*d(?:ay|ays?)?(?:\s+ago)?', 'days'),
        (r'(\d+)\s*w(?:eek|eeks?)?(?:\s+ago)?', 'weeks'),
        (r'(\d+)\s*mo(?:nth|nths?)?(?:\s+ago)?', 'months'),
        (r'(\d+)\s*y(?:ear|ears?)?(?:\s+ago)?', 'years'),
    ]

    for pattern, unit in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            now = datetime.now(timezone.utc)

            if unit == 'minutes':
                return now - timedelta(minutes=value)
            elif unit == 'hours':
                return now - timedelta(hours=value)
            elif unit == 'days':
                return now - timedelta(days=value)
            elif unit == 'weeks':
                return now - timedelta(weeks=value)
            elif unit == 'months':
                return now - timedelta(days=value * 30)
            elif unit == 'years':
                return now - timedelta(days=value * 365)

    if 'yesterday' in text:
        return datetime.now(timezone.utc) - timedelta(days=1)
    elif 'today' in text:
        return datetime.now(timezone.utc)
    elif any(word in text for word in ['just now', 'moment ago', 'now']):
        return datetime.now(timezone.utc)

    print(f"⚠️  Cannot parse time: '{relative_text}', using current time")
    return datetime.now(timezone.utc)


if __name__ == "__main__":
    test_cases = [
        "12m", "2h", "3d", "1w", "2mo", "1y",
        "12 minutes ago", "2 hours ago", "3 days ago",
        "yesterday", "today", "just now",
        "30 June", "July 15", "15 Dec", "Dec 25"
    ]

    print("🧪 Testing time parser:")
    for case in test_cases:
        result = parse_relative_time(case)
        print(f"'{case}' → {result}")
