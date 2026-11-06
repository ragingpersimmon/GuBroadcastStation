"""World-coverage feed list, grouped by desk.

5protocol's DEFAULT_FEEDS are market-tuned (Fed, SEC, EIA, CNBC...).
The broadcast needs global general news, so we pass our own feed map
into 5protocol's NewsFeedPoller and keep its dedupe / timeout / HTML
cleaning / sentiment scoring. Verify each URL before relying on it --
outlets move RSS endpoints without notice. Keys are "<desk>:<outlet>".
"""

WORLD_FEEDS = {
    # World / wire-style
    "world:bbc": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "world:aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "world:guardian": "https://www.theguardian.com/world/rss",
    "world:npr": "https://feeds.npr.org/1004/rss.xml",
    "world:dw": "https://rss.dw.com/rdf/rss-en-world",
    "world:france24": "https://www.france24.com/en/rss",
    "world:un_news": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
    # Regional desks
    # CBC (cbc.ca/webfeed) times out from DigitalOcean IPs (verified 2026-11-06); Global News instead
    "world:globalnews_world": "https://globalnews.ca/world/feed/",
    "americas:globalnews_canada": "https://globalnews.ca/canada/feed/",
    "europe:bbc_europe": "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
    "asia:bbc_asia": "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
    "asia:nhk": "https://www3.nhk.or.jp/rss/news/cat6.xml",
    "asia:korea_herald": "https://www.koreaherald.com/rss/020000000000.xml",
    "mideast:bbc_mideast": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "africa:bbc_africa": "https://feeds.bbci.co.uk/news/world/africa/rss.xml",
    # Topic desks
    "business:bbc_business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "tech:bbc_tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "tech:ars": "https://feeds.arstechnica.com/arstechnica/index",
    "science:bbc_science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "science:nasa": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    # Beat desks (newsroom.json assigns each to a reporter)
    "politics:npr_politics": "https://feeds.npr.org/1014/rss.xml",
    "politics:guardian_politics": "https://www.theguardian.com/politics/rss",
    "politics:globalnews_politics": "https://globalnews.ca/politics/feed/",
    "business:globalnews_money": "https://globalnews.ca/money/feed/",
    "consumer:guardian_money": "https://www.theguardian.com/money/rss",
    "entertainment:bbc_entertainment": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "entertainment:guardian_culture": "https://www.theguardian.com/culture/rss",
    "sports:bbc_sport": "https://feeds.bbci.co.uk/sport/rss.xml",
    "sports:globalnews_sports": "https://globalnews.ca/sports/feed/",
}

DESKS = ["world", "americas", "europe", "asia", "mideast", "africa", "politics", "business",
         "consumer", "tech", "science", "entertainment", "sports", "weather", "traffic"]


def desk_of(source_key: str) -> str:
    desk = source_key.split(":", 1)[0]
    return desk if desk in DESKS else "world"


def outlet_of(source_key: str) -> str:
    return source_key.split(":", 1)[-1]
