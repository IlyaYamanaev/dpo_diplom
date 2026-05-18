import re
from playwright.sync_api import sync_playwright



def clean_text(tag) -> str | None:
   """Убирает HTML-мусор (&nbsp;, <font>, <span> и т.д.) и возвращает чистый текст."""
   if tag is None:
      return None
   text = tag.get_text(separator=" ", strip=True)
   # Нормализуем пробелы (включая неразрывные)
   text = re.sub(r"[\u00a0\s]+", " ", text).strip()
   return text or None


def clean_text(text: str) -> str:
   """Убирает &nbsp; и лишние пробелы."""
   text = text.replace("\u00a0", " ")
   text = re.sub(r"\s+", " ", text)
   text = text.replace("&nbsp;", " ")
   return text.strip()


def extract_duration(footer_text: str):
   """
   Из 'PRO, 6 месяцев' → '6 месяцев'
   Из 'С нуля, PRO, 22 месяца' → '22 месяца'
   Из 'С нуля' → None (нет информации о месяцах)
   """
   footer_text = clean_text(footer_text)
   # Ищем фрагмент с числом и словом месяц/месяца/месяцев
   match = re.search(r"(\d+\s*месяц\w*)", footer_text)
   if match:
      return match.group(1).strip()
   return None


def extract_price_from_text(text: str):
   """
   Извлекает целое число рублей из строки вида:
   'на 36 месяцев или 105 000 ₽ одним платежом...'
   Возвращает строку с числом (без пробелов) или None.
   """   
   text = clean_text(text)   
   # Ищем число перед знаком ₽ (с пробелами внутри числа)
   match = re.search(r"([\d][\d\s]*)\s*₽", text)
   if match:
      number = re.sub(r"\s", "", match.group(1))
      return number
   return None


def get_html_with_playwright(url: str) -> str:
   """Возвращает HTML страницы с ДЕЙСТВИТЕЛЬНОЙ ценой курса"""
   with sync_playwright() as p:
      browser = p.chromium.launch(headless=True)  # headless=True для скрытого режима
      page = browser.new_page()
      page.goto(url)
      
      page.wait_for_timeout(3000)      
      
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
      
      
    