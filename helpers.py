import re
from playwright.sync_api import sync_playwright



def clean_text(tag) -> str | None:
    """Очищает текст из BeautifulSoup тега или строки"""
    if tag is None:
        return None
    
    # Если передана строка
    if isinstance(tag, str):
        text = tag
    else:
        # Если передан тег BeautifulSoup
        text = tag.get_text(separator=" ", strip=True)
    
    # Нормализуем пробелы
    text = re.sub(r"[\u00a0\s]+", " ", text).strip()
    text = text.replace("&nbsp;", " ")
    return text or None


def truncate_string(s, max_len):
    """Обрезает строку до max_len символов"""
    if s and len(s) > max_len:
        return s[:max_len]
    return s


def get_html_with_playwright(url: str) -> str:
   """Возвращает HTML страницы с ДЕЙСТВИТЕЛЬНОЙ ценой курса"""
   with sync_playwright() as p:
      browser = p.chromium.launch(headless=False)  # headless=True для скрытого режима
      page = browser.new_page()
      page.goto(url)
      
      page.wait_for_timeout(12000)      
      
      html = page.content()
      browser.close()
      return html
   
   
def get_html_with_playwright_selector(url: str, element_selector: str) -> str:
   """Возвращает HTML страницы с ДЕЙСТВИТЕЛЬНОЙ ценой курса"""
   with sync_playwright() as p:
      browser = p.chromium.launch(headless=True)  # headless=True для скрытого режима
      page = browser.new_page()
      page.goto(url)
      
      # Ждём КОНКРЕТНЫЙ элемент с ценой
      page.wait_for_selector(element_selector, timeout=17000)
      
      page.wait_for_timeout(2000)      
      
      html = page.content()
      browser.close()
      return html
      
      
    