import asyncio
from curl_cffi import requests
from bs4 import BeautifulSoup

URL_TEST = "https://www.welcometothejungle.com/fr/jobs?query=data&page=1"

def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for elem in soup(["script", "style", "noscript", "svg", "img"]):
        elem.decompose()
    return soup.get_text(separator="\n", strip=True)

def test_curl_cffi():
    print("\n--- Test 1: Curl-CFFI (Usurpation d'empreinte TLS Chrome sans ouvrir de navigateur) ---")
    print("Cet outil est magique car il simule parfaitement la signature réseau de Chrome 120,")
    print("ce qui trompe Cloudflare et DataDome, sans lancer de vrai navigateur !")
    try:
        # On imite Chrome 120 pour passer sous le radar
        response = requests.get(URL_TEST, impersonate="chrome120")
        
        if response.status_code == 200:
            text = extract_text(response.text)
            print(f"✅ Succès! Code: {response.status_code} | Longueur: {len(text)}")
            print(f"Extrait: {text[:200]}...")
        else:
            print(f"❌ Échec: Statut {response.status_code} (Le site nous a bloqué !)")
    except Exception as e:
        print(f"❌ Échec: {e}")

def test_seleniumbase_uc():
    print("\n--- Test 2: SeleniumBase UC Mode (Undetected ChromeDriver) ---")
    print("C'est la méthode ultime si le site requiert que du Javascript soit exécuté.")
    print("Cela lance un navigateur Chrome modifié pour être intraçable par les anti-bots.")
    
    try:
        from seleniumbase import Driver
        # uc=True active le mode "Undetected"
        # headless=True peut être détecté, il vaut mieux le laisser False si on est bloqué
        driver = Driver(uc=True, headless=False)
        driver.get(URL_TEST)
        
        # On attend un peu que la page charge
        driver.sleep(4)
        
        html = driver.page_source
        text = extract_text(html)
        
        print(f"✅ Succès! Longueur: {len(text)}")
        print(f"Extrait: {text[:200]}...")
        
        driver.quit()
    except Exception as e:
        print(f"❌ Échec: {e}")

if __name__ == "__main__":
    test_curl_cffi()
    test_seleniumbase_uc()
