import json
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from src.db.operations import upsert_job_offer

# Note: In a real production setup, we would use Playwright to render JS.
# For simplicity and robust generic extraction in this example, we define a tool
# that the Deep Agent can call.

@tool
def scrape_and_save_jobs(url: str, category: str, html_content: str) -> str:
    """
    Extracts job offers from the provided HTML content and saves them to the database.
    The agent should first fetch the HTML using a web fetching tool, then pass it here.
    Wait, to make it easier for the agent, let's make a tool that fetches AND extracts.
    """
    # Placeholder: In a real system we'd use Playwright.
    # Here we simulate the extraction for the architecture.
    soup = BeautifulSoup(html_content, "html.parser")
    
    # We would use specific selectors or an LLM to parse `soup.text`.
    # For the sake of the architecture, let's assume the agent uses this tool
    # to directly save structured data it has already extracted.
    pass

@tool
def save_extracted_job(title: str, company: str, url: str, category: str, description: str) -> str:
    """
    Saves a job offer into the database. 
    Use this tool after you have extracted a job offer from a recruitment website.
    """
    success = upsert_job_offer(title, company, url, category, description)
    if success:
        return f"Successfully saved job: {title} at {company}"
    else:
        return f"Job already exists or failed to save: {url}"

from src.config import settings
from src.tools.playwright_scraper import fetch_page_content

scraper_agent = {
    "name": "scraper_agent",
    "description": "Scrapes job offers from recruitment websites and saves them to the database.",
    "model": settings.MODEL_NAME,
    "system_prompt": (
        "You are a specialized web scraping agent. Your goal is to visit recruitment websites.\n"
        "1. First, use the 'fetch_page_content' tool with the URL of the website to get the page text.\n"
        "2. Parse the text to extract job offers (title, company, url, description).\n"
        "3. Save each extracted job using the 'save_extracted_job' tool.\n"
        "Focus on jobs related to Data, AI, and Tech."
    ),
    "tools": [fetch_page_content, save_extracted_job]
}
