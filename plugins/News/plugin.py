import asyncio
from datetime import datetime
import os

import requests
from base.SchedulerPlugin import SchedulerPlugin
from loguru import logger
from base.util import Util
from core.coreInterface import CoreInterface
class NewsPlugin(SchedulerPlugin):
    def __init__(self, coreInst: CoreInterface):
        super().__init__(coreInst=coreInst)  
        # Automatically determine the path to the config.yml file
        logger.debug('NewsPlugin __init__...')
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.yml')
        logger.debug(f'config_path: {config_path}')
        if not os.path.exists(config_path):
            logger.debug(f"Config file does not exist: {config_path}")  # Debugging line
            return
        self.config = Util().load_yml_config(config_path)
        logger.debug(f'NewsPlugin description: {self.config["description"]}')
        self.date = datetime.now().strftime("%Y-%m-%d")
        self.news = []
        self.prompt = """
            You are an expert at summarizing and refining news articles.

            Guidelines:
            1. Read through the provided news articles.
            2. Select the top 3 latest news articles.
            3. Reorganize and summarize the main points of each article in a concise manner.
            4. Refine the content to enhance readability and clarity.
            5. Generate a final summary to be sent to the user.

            News Articles:
            {news_articles}

            Final Summary:
        """
        logger.debug(f'NewsPlugin config: {self.config}')  

    async def fetch_latest_news(self):
        """Fetch latest news and return raw articles text. When called by Core with capability (post_process), Core runs LLM on this. When called from run(), run() may post-process and send."""
        try:
            date = datetime.now().strftime("%Y-%m-%d")
            if self.date != date:
                self.date = date
                self.news = []
            base_url = self.config.get('base_url') or ''
            api_key = self.config.get('apiKey') or ''
            country = self.config.get('country') or 'us'
            category = self.config.get('category') or 'business'
            sources = self.config.get('sources') or ''
            urls = [
                f"{base_url}?country={country}&category={category}&apiKey={api_key}",
                f"{base_url}?sources={sources}&apiKey={api_key}" if sources else None,
            ]
            urls = [u for u in urls if u]
            raw_parts = []
            for url in urls:
                resp = requests.get(url, timeout=10)
                data = resp.json()
                news = data.get('articles') or []
                if not news:
                    continue
                sorted_news = sorted(news, key=lambda x: x.get('publishedAt', ''), reverse=True)
                for j, article in enumerate(sorted_news[:3]):
                    if article not in self.news:
                        self.news.append(article)
                    title = article.get('title') or ''
                    content = (article.get('content') or article.get('description') or '')[:500]
                    raw_parts.append(f"{j+1}. {title}\n{content}")
            if not raw_parts:
                return "No news articles found."
            return "\n\n".join(raw_parts)
        except requests.RequestException as e:
            logger.error("Failed to fetch news: %s", e)
            return f"Failed to fetch news: {e}"

    async def run(self):
        """Return raw news articles text. Core decides whether to post_process (LLM) or send directly."""
        return await self.fetch_latest_news()

    def initialize(self):
        if self.initialized:
            return
        logger.debug("Initializing News plugin")
        super().initialize()
        self.initialized = True