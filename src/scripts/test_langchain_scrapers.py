import asyncio
from bs4 import BeautifulSoup
from langchain_community.document_loaders import WebBaseLoader, AsyncHtmlLoader

URL_TEST = "https://www.welcometothejungle.com/fr/jobs?query=data&page=1"

def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for elem in soup(["script", "style", "noscript", "svg", "img"]):
        elem.decompose()
    return soup.get_text(separator="\n", strip=True)

def test_web_base_loader():
    print("\n--- Test 1: LangChain WebBaseLoader (urllib/requests) ---")
    try:
        loader = WebBaseLoader(URL_TEST)
        docs = loader.load()
        text = docs[0].page_content
        print(f"✅ Succès! Longueur: {len(text)}")
        print(f"Extrait: {text[:200]}...")
    except Exception as e:
        print(f"❌ Échec: {e}")

async def test_async_html_loader():
    print("\n--- Test 2: LangChain AsyncHtmlLoader (aiohttp) ---")
    try:
        loader = AsyncHtmlLoader([URL_TEST])
        docs = loader.load()
        html = docs[0].page_content
        text = extract_text(html)
        print(f"✅ Succès! Longueur: {len(text)}")
        print(f"Extrait: {text[:200]}...")
    except Exception as e:
        print(f"❌ Échec: {e}")

if __name__ == "__main__":
    test_web_base_loader()
    asyncio.run(test_async_html_loader())
