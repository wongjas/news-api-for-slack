import logging
from typing import List
from dataclasses import dataclass
from datetime import datetime

import pytz
import requests

logger = logging.getLogger(__name__)


@dataclass
class Source:
    id: str
    name: str


@dataclass
class Article:
    source: Source
    author: str
    title: str
    description: str
    url: str
    urlToImage: str
    publishedAt: datetime
    content: str

    def __post_init__(self):
        self.publishedAt = datetime.fromisoformat(self.publishedAt[:-1]).replace(
            tzinfo=pytz.timezone("UTC")
        )


def fetch_articles(
    api_key: str, query: str, num_articles: int = 3, language: str = "jp"
) -> List[Article]:
    params = {
        "apiKey": api_key,
        "language": language,
        "q": query,
        "pageSize": num_articles,
        "sortBy": "publishedAt",
    }
    url = (
        "https://newsapi.org/v2/everything"
        if query
        else "https://newsapi.org/v2/top-headlines"
    )

    if query:
        params["q"] = query.replace(",", " OR ").replace("、", " OR ")
    else:
        del params["q"]

    response = requests.get(url=url, params=params)
    response_body = response.json()

    return [Article(**article) for article in response_body.get("articles")]


def format_article(article: Article) -> List[dict]:
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": article.title},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"⏱ {article.publishedAt.astimezone(pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M:%S')} ",
                }
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": article.description},
            "accessory": {
                "type": "image",
                "image_url": article.urlToImage,
                "alt_text": "ニュース記事の画像",
            },
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"全文を読む：{article.url}"}],
        },
    ]

    # 画像がない場合、イメージブロックを外します
    if not article.urlToImage:
        del blocks[2]["accessory"]

    return blocks
