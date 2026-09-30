


```bash

# ============== WATCH SOURCES ==============
## -------ArXiv - API
ARXIV_BASE_URL=https://export.arxiv.org/api/query
ARXIV_TOPICS=[{"name":"cs.CR","keywords":["prompt injection","jailbreak","LLM security","adversarial attack","red teaming","agent hijacking"]}]
# ARXIV_MAX_RESULTS=
# ARXIV_MAX_PAGES=
ARXIV_MIN_YEAR=2026

## -------Github releases - API
GITHUB_API_URL=https://api.github.com
GITHUB_RELEASES_TOKEN=
GITHUB_WATCHED_REPOS=[{"owner":"langchain-ai","name":"langchain"},{"owner":"langchain-ai","name":"langgraph"}]

## -------TLDR.tech - scraping
TLDR_BASE_URL=https://tldr.tech/
TLDR_EDITIONS=[{"name":"ai"},{"name":"infosec"},{"name":"it"},{"name":"design"},{"name":"dev"},{"name":"devops"},{"name":"tech"},{"name":"data"},{"name":"hardware"}]
# TLDR_START_DATE=

## -------RSS feeds
RSS_FEEDS=[{"url":"https://openai.com/news/rss.xml","name":"OpenAI"},{"url":"https://huggingface.co/blog/feed.xml","name":"Hugging Face"}]
# RSS_MAX_ITEMS_PER_FEED=
# RSS_START_DATE=

```