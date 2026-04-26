import asyncio
from src.tools.playwright_scraper import fetch_page_content

async def main():
    print("Test du scraper Playwright...")
    url = "https://www.welcometothejungle.com/fr/jobs?query=data&page=1"
    
    # Appel de l'outil directement
    try:
        # En tant que tool langchain, il faut l'invoquer correctement
        result = await fetch_page_content.ainvoke({"url": url})
        
        print("\n--- RÉSULTAT OBTENU ---")
        print(f"Longueur du texte extrait : {len(result)} caractères")
        print("Aperçu (500 premiers caractères) :")
        print("-" * 40)
        print(result[:500])
        print("-" * 40)
        
        if "Error:" in result[:100] or "Erreur fatale" in result[:100]:
            print("\n❌ Une erreur s'est produite lors de l'exécution.")
        else:
            print("\n✅ Succès ! L'extraction a fonctionné.")
            
    except Exception as e:
        print(f"\n❌ Erreur inattendue : {e}")

if __name__ == "__main__":
    asyncio.run(main())
