#!/usr/bin/env python3
from pathlib import Path
import os

def load_env_file():
    env_path = Path('.env')
    if not env_path.exists():
        print("WARNING: .env file not found!")
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()
    print("Loaded .env file successfully")

load_env_file()  # call this FIRST before anything else

import sys
import io

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, 
    encoding='utf-8', 
    errors='replace'
)
sys.stderr = io.TextIOWrapper(
    sys.stderr.buffer,
    encoding='utf-8',
    errors='replace'
)

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(str(text).encode('ascii', 'replace').decode('ascii'))

sys.path.insert(0, str(Path(__file__).parent))

from watcher.config import load_config
from watcher.storage.store import Storage
from watcher.agents.collector import CollectorAgent
from watcher.agents.filter import SmartFilter
from watcher.agents.synthesizer import generate_report
from watcher.agents.llm_api_adapter import APILLMAdapter

def collect_all_feeds(config):
    db_path = config.get('database', 'watcher.db')
    storage = Storage(db_path)
    collector = CollectorAgent(storage=storage)
    # The default CollectorAgent collects and persists, then returns a list
    return collector.collect_new()

FINANCE_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
    "https://feeds.feedburner.com/entrepreneur/latest",
]

def ensure_feeds_for_topics(config):
    topics = config.get('topics', [])
    feeds  = config.get('feeds', [])
    
    finance_keywords = [
        'crypto', 'bitcoin', 'fintech', 
        'stock', 'venture', 'startup', 'funding'
    ]
    
    needs_finance = any(
        any(kw in t.lower() for kw in finance_keywords)
        for t in topics
    )
    
    if needs_finance:
        for feed in FINANCE_FEEDS:
            if feed not in feeds:
                feeds.append(feed)
        config['feeds'] = feeds
    
    return config

def run_pipeline(config):
    config = ensure_feeds_for_topics(config)
    topics    = config.get('topics', [])
    threshold = min(config.get('relevance_threshold', 0.25), 0.30)
    
    # Step 1: Collect articles
    safe_print("Step 1: Collecting articles...")
    articles = collect_all_feeds(config)
    safe_print(f"Collected: {len(articles)} articles")
    
    if len(articles) == 0:
        safe_print("ERROR: No articles collected!")
        safe_print("Check your RSS feeds in Data Sources")
        return None
        
    def is_google_news(url):
        if not url: return False
        return 'news.google.com' in str(url)

    for article in articles:
        if is_google_news(article.get('feed_url','')):
            article['skip_filter'] = True
    
    # Step 2: Smart filter per topic
    safe_print("Step 2: Filtering by topic...")
    smart_filter = SmartFilter(topics, threshold)
    filtered_by_topic = smart_filter.filter_all(articles)
    
    # Log results
    for topic, arts in filtered_by_topic.items():
        safe_print(f"  {topic}: {len(arts)} articles")
    
    # Init LLM client
    def get_config_value(config, *keys, default=''):
        for key in keys:
            if key in config and config[key]:
                return config[key]
        return default

    try:
        api_provider = get_config_value(
            config, 
            'provider', 'api_provider',
            default='groq'
        )
        api_model = get_config_value(
            config,
            'model', 'api_model', 
            default='llama-3.3-70b-versatile'
        )
        llm_client = APILLMAdapter(provider=api_provider, model=api_model)
    except Exception as e:
        safe_print(f"ERROR initializing LLM client: {e}")
        return None

    # Step 3: Generate report per topic
    safe_print("Step 3: Generating report...")
    report = generate_report(
        filtered_by_topic, config, llm_client
    )
    
    # Step 4: Save report
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"reports/intelligence_report_{timestamp}.md"
    
    os.makedirs("reports", exist_ok=True)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(report)
    
    safe_print(f"Report saved: {filename}")
    
    # Diagnostic output
    safe_print("\n" + "="*50)
    safe_print("PIPELINE SUMMARY")
    safe_print("="*50)
    safe_print(f"Articles collected: {len(articles)}")
    for topic, arts in filtered_by_topic.items():
        status = "[OK]" if len(arts) > 0 else "[--]"
        safe_print(f"{status} {topic}: {len(arts)} articles")
    safe_print(f"Report: {filename}")
    safe_print("="*50)
    
    return filename

if __name__ == "__main__":
    cfg = load_config() or {}
    run_pipeline(cfg)
