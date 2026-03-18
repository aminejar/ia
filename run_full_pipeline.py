#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# Load environment variables
env_file = Path(__file__).parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

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

def run_pipeline(config):
    topics    = config.get('topics', [])
    threshold = config.get('filter_threshold', 0.30)
    
    # Step 1: Collect articles
    print("Step 1: Collecting articles...")
    articles = collect_all_feeds(config)
    print(f"Collected: {len(articles)} articles")
    
    if len(articles) == 0:
        print("ERROR: No articles collected!")
        print("Check your RSS feeds in Data Sources")
        return None
    
    # Step 2: Smart filter per topic
    print("Step 2: Filtering by topic...")
    smart_filter = SmartFilter(topics, threshold)
    filtered_by_topic = smart_filter.filter_all(articles)
    
    # Log results
    for topic, arts in filtered_by_topic.items():
        print(f"  {topic}: {len(arts)} articles")
    
    # Init LLM client
    try:
        api_provider = config.get('api_provider', 'groq')
        api_model = config.get('api_model', 'llama3-70b-8192')
        llm_client = APILLMAdapter(provider=api_provider, model=api_model)
    except Exception as e:
        print(f"ERROR initializing LLM client: {e}")
        return None

    # Step 3: Generate report per topic
    print("Step 3: Generating report...")
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
    
    print(f"Report saved: {filename}")
    
    # Diagnostic output
    print("\n" + "="*50)
    print("PIPELINE SUMMARY")
    print("="*50)
    print(f"Articles collected: {len(articles)}")
    for topic, arts in filtered_by_topic.items():
        status = "✓" if len(arts) > 0 else "✗"
        print(f"{status} {topic}: {len(arts)} articles")
    print(f"Report: {filename}")
    print("="*50)
    
    return filename

if __name__ == "__main__":
    cfg = load_config() or {}
    run_pipeline(cfg)
