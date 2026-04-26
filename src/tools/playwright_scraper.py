import os
import sys
from bs4 import BeautifulSoup
from langchain_core.tools import tool

# Import conditionnel pour gérer les erreurs si l'utilisateur ne l'a pas encore installé
try:
    from playwright.async_api import async_playwright
except ImportError:
    pass

@tool
async def fetch_page_content(url: str) -> str:
    """
    Fetches the textual content of a webpage using the user's local Chrome browser.
    Useful for scraping job offers from recruitment websites like Welcome to the Jungle or LinkedIn.
    It first tries to connect to an existing Chrome instance on port 9222 (Method 2).
    If it fails, it tries to launch a persistent context using the local Chrome profile (Method 1).
    Returns the parsed text of the webpage.
    """
    if "playwright" not in sys.modules:
        return "Error: playwright is not installed. Please run 'uv pip install playwright' and 'playwright install chromium'."
    
    mac_chrome_path = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    
    async with async_playwright() as p:
        browser = None
        context = None
        page = None
        
        # Try Method 2: Connect over CDP
        try:
            print(f"Tentative de connexion à Chrome via CDP (port 9222)...")
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
            else:
                context = await browser.new_context()
            page = await context.new_page()
            print("Connecté à Chrome via CDP avec succès (Méthode 2).")
        except Exception as e:
            print(f"Échec de la connexion CDP. Tentative de lancement du Persistent Context...")
            # Try Method 1: Launch persistent context
            try:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=mac_chrome_path,
                    channel="chrome",
                    headless=False,
                    ignore_default_args=["--enable-automation", "--no-sandbox"]
                )
                print("Lancement du contexte terminé, récupération de l'onglet...")
                # Playwright ouvre déjà un onglet par défaut dans un contexte persistant
                if context.pages:
                    page = context.pages[0]
                else:
                    page = await context.new_page()
                print("Lancement d'un nouveau Chrome avec le profil local réussi (Méthode 1).")
            except Exception as e2:
                return (
                    f"Erreur fatale: Impossible de lancer Chrome.\n"
                    f"Vérifiez que Google Chrome est TOTALEMENT fermé (Cmd+Q) avant de lancer le script.\n"
                    f"Détails: {e2}"
                )

        # Navigation and extraction
        try:
            print(f"Navigation vers {url}...")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # Attente de quelques secondes pour les chargements asynchrones (React/Vue)
            await page.wait_for_timeout(4000)
            
            html = await page.content()
            
            # Nettoyage du HTML avec BeautifulSoup pour renvoyer un texte clair à l'agent
            soup = BeautifulSoup(html, "html.parser")
            # Suppression des balises non pertinentes
            for elem in soup(["script", "style", "noscript", "header", "footer", "nav", "svg", "img"]):
                elem.decompose()
            
            text = soup.get_text(separator="\n", strip=True)
            
            # On renvoie les 15 000 premiers caractères pour éviter de dépasser la fenêtre de contexte du LLM
            return text[:15000]
        except Exception as e:
            return f"Error while navigating to {url}: {e}"
        finally:
            if page:
                try:
                    await page.close()
                except:
                    pass
            # Si on a lancé un Persistent Context (Method 1), on le ferme.
            # Si on s'est connecté via CDP (Method 2), on NE FERME PAS le navigateur de l'utilisateur !
            if context and not browser:
                await context.close()
