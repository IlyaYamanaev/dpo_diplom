import re
import time
import requests
from bs4 import BeautifulSoup
from db_functions import (
   get_connection,
   save_course,
   get_or_create_specialization,
   link_course_specialization
)
import random
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
BASE_URL = "https://practicum.yandex.ru"
CATALOG_URL = "https://practicum.yandex.ru/catalog/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"}

ORGANIZATION_ID = 8  
DB_NAME = "buff_dpo_db"

# ---------------------------------------------------------------------------
# Браузер
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
]

class BrowserManager:
   def __init__(self):
      self.playwright = sync_playwright().start()
      self.browser = self.playwright.chromium.launch(
         headless=False,
         slow_mo=random.randint(50, 150),
         args=[
               "--disable-blink-features=AutomationControlled",
               "--disable-dev-shm-usage",
               "--no-sandbox",
         ]
      )
      self.context = self.browser.new_context(
         user_agent=random.choice(USER_AGENTS),
         locale="ru-RU",
         timezone_id="Europe/Moscow",
         viewport={
               "width": random.randint(770, 800),
               "height": random.randint(580, 600)
         }
      )
      self.page = self.context.new_page()

      # Скрываем webdriver
      self.page.add_init_script("""
      Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
      window.chrome = {runtime: {}};
      Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru']});
      Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
      """)

   def human_delay(self, a=1.5, b=2.5):
      time.sleep(random.uniform(a, b))

   def simulate_human(self):
      self.page.mouse.move(
         random.randint(100, 600),
         random.randint(100, 500),
         steps=random.randint(10, 30)
      )
      self.human_delay(0.5, 1.5)
      self.page.mouse.wheel(
         0,
         random.randint(300, 1500)
      )
      self.human_delay(1, 2)

   def get_html(self, url):
      self.page.goto(
         url,
         wait_until="domcontentloaded",
         timeout=60000
      )
      self.human_delay(1, 3)
      self.simulate_human()
      current_url = self.page.url.lower()
      html = self.page.content().lower()
      if "captcha" in current_url or "captcha" in html:
         print("КАПЧА ОБНАРУЖЕНА")
         print("РЕШИ КАПЧУ ВРУЧНУЮ")
         input("Нажми ENTER после решения капчи...")
         try:
            self.page.wait_for_load_state(
               "networkidle",
               timeout=60000
            )
         except:
            pass
         self.human_delay(1, 3)
         time.sleep(random.uniform(2, 5))
      return self.page.content()

   def close(self):

      self.context.storage_state(path="state.json")

      self.browser.close()
      self.playwright.stop()

# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------
def build_full_url(href: str) -> str:
   """Строит абсолютный URL из href."""
   if href.startswith("http"):
      return href
   return BASE_URL + href


def extract_duration(footer_text: str):
   """
   Из 'PRO, 6 месяцев' → '6 месяцев'
   Из 'С нуля, PRO, 22 месяца' → '22 месяца'
   Из 'С нуля' → None (нет информации о месяцах)
   """
   footer_text = clean_text(footer_text)
   match = re.search(r"(\d+\s*месяц\w*)", footer_text)
   if match:
      return match.group(1).strip()
   return None


def extract_price_from_text(text):
   if not text:
      return None
   text = str(text)
   text = clean_text(text)
   if not text:
      return None
   match = re.search(r"([\d][\d\s]*)\s*₽", text)
   if match:
      number = re.sub(r"\s", "", match.group(1))
      return number
   return None


def clean_text(tag) -> str:
   """Очищает текст из BeautifulSoup тега или строки"""
   if tag is None:
      return ""
   # Если передана строка
   if isinstance(tag, str):
      text = tag
   # Если BeautifulSoup
   else:
      text = tag.get_text(separator=" ", strip=True)
   text = re.sub(r"[\u00a0\s]+", " ", text).strip()
   text = text.replace("&nbsp;", " ")
   return text

# ---------------------------------------------------------------------------
# Парсинг главной страницы каталога
# ---------------------------------------------------------------------------
def parse_catalog(html: str) -> list:
   """
   Возвращает список dict:
      {url, title, price, duration, specialization_names}
   """
   soup = BeautifulSoup(html, "html.parser")
   
   catalog_list = soup.find("ul", class_="prof-window-v2__list")
   if not catalog_list:
      print("  [!] Не найден список prof-window-v2__list")
      return []

   courses = []
   for li in catalog_list.find_all("li"):
      card_a = li.find("a", class_="prof-window-v2__card")
      if not card_a:
         continue

      href = card_a.get("href", "")
      if not href:
         continue
      url = build_full_url(href)

      url_clean = url.split("?")[0].rstrip("/") + "/"

      # Цена 
      price = None
      badge = card_a.find("div", class_="prof-window-v2__card-badge_free")
      if badge and "Бесплатно" in badge.get_text():
         price = "0"

      # Специализации
      specialization_names = []
      direction_div = card_a.find("div", class_="prof-window-v2__card-direction")
      if direction_div:
         direction_text = clean_text(direction_div.get_text())
         if direction_text:
               specialization_names = [s.strip() for s in direction_text.split(",") if s.strip()]

      # Название
      title_tag = card_a.find("h2", class_="prof-window-v2__card-title")
      title = clean_text(title_tag.get_text()) if title_tag else None

      # Срок 
      footer_div = card_a.find("div", class_="prof-window-v2__card-footer")
      duration = None
      if footer_div:
         duration = extract_duration(footer_div.get_text())
         
      if price == "0":
         duration = "1 день"

      courses.append({
         "url": url_clean,
         "title": title,
         "price": price,
         "duration": duration,
         "specialization_names": specialization_names,
      })

   return courses

# ---------------------------------------------------------------------------
# Парсинг страницы курса
# ---------------------------------------------------------------------------
def parse_course_page(url: str, html: str, card_data: dict, browser: BrowserManager) -> dict:
   
   html = browser.get_html(url)
   
   soup = BeautifulSoup(html, "html.parser")

   course = {
      "organization_id": ORGANIZATION_ID,
      "url": url,
      "title": card_data.get("title"),
      "price": card_data.get("price"),
      "format": "Онлайн",
      "course_type": None,
      "duration": card_data.get("duration"),
      "duration_in_hours": "Не указана",
      "description": "Не указано",
      "language": "русский",
      "date": "Не указана",
      "document": None,
      "admission_requirements": "Не указаны",
      "schedule": "Не указан",
      "department_id": None,
      "specialization_names": list(card_data.get("specialization_names", [])),
   }

   # Description
   desc_div = soup.find("div", class_="head-section__duration")
   if desc_div:
      course["description"] = clean_text(desc_div.get_text())

   if course["description"] == "Не указано":
      first_desc_section = soup.find("section", id="first-description")
      if first_desc_section:
         text_div = first_desc_section.find("div", class_="lc-styled-text__text")
         if text_div:
               course["description"] = clean_text(text_div.get_text())

   # Date
   surge_div = soup.find("div", class_="squad-surge-info")
   if surge_div:
      span = surge_div.find("span")
      if span:
         text = clean_text(span.get_text())
         if "Ближайший старт" in text:
               parts = text.split("—", 1)
               if len(parts) > 1:
                  course["date"] = parts[1].strip()

   if course["date"] == "Не указана":
      squad_dates = soup.find("p", class_="squad-dates")
      if squad_dates:
         text = clean_text(squad_dates.get_text())
         if "Ближайший старт" in text:
               parts = text.split("—", 1)
               if len(parts) > 1:
                  course["date"] = parts[1].strip()

   # Document и course_type
   def _find_doc_in_container(container) -> tuple:
      """Возвращает (document, course_type) или (None, None)."""
      text = clean_text(container.get_text(" "))
      if re.search(r"[Дд]иплом\s+о\s+профессиональной\s+переподготовке", text):
         return "Диплом о профессиональной переподготовке", "Профессиональная переподготовка"
      if re.search(r"[Уу]достоверение\s+о\s+повышении\s+квалификации", text):
         return "Удостоверение о повышении квалификации", "Повышение квалификации"
      if re.search(r"[Вв]аш\s+диплом\s+после\s+обучения", text):
         return "Диплом после обучения", "Курс"
      if re.search(r"[Вв]аше\s+свидетельство\s+об\s+обучении", text):
         return "Свидетельство об обучении", "Курс"
      return None, None

   doc, ctype = None, None

   bullets_block = soup.find("ul", class_=lambda c: c and "bullets-block" in c)
   if bullets_block:
      doc, ctype = _find_doc_in_container(bullets_block)

   if not doc:
      for para in soup.find_all("div", class_="paragraph"):
         text = clean_text(para.get_text())
         if re.search(r"[Вв]ыдадим\s+диплом\s+о\s+профессиональной\s+переподготовке", text):
               doc, ctype = "Диплом о профессиональной переподготовке", "Профессиональная переподготовка"
               break
         if re.search(r"[Пп]олучите\s+удостоверение\s+о\s+повышении\s+квалификации", text):
               doc, ctype = "Удостоверение о повышении квалификации", "Повышение квалификации"
               break

   if not doc:
      for styled in soup.find_all("div", class_=lambda c: c and "lc-styled-text__text" in c):
         text = clean_text(styled.get_text())
         if re.search(r"[Вв]аш\s+диплом\s+после\s+обучения", text):
               doc = "Диплом после обучения"
               break
         if re.search(r"[Вв]аше\s+свидетельство\s+об\s+обучении", text):
               doc = "Свидетельство об обучении"
               break

   if not doc:
      for styled in soup.find_all("div", class_=lambda c: c and "lc-styled-text__text" in c):
         text = clean_text(styled.get_text())
         if re.search(r"свидетельство\s+об\s+обучении", text):
               doc = "Свидетельство об обучении"
               break

   course["document"] = doc
   course["course_type"] = ctype


   # Price
   if course["price"] is None:
      # common-flow__row_tariff → первая карточка displayed → common-flow-price__message
      tariff_row = soup.find("ul", class_=lambda c: c and "common-flow__row_tariff" in c)
      if tariff_row:
         # первую li.common-flow-card с классом displayed
         first_card = tariff_row.find(
            "li",
            class_=lambda c: c and "common-flow-card" in c and "common-flow-card_plus" not in c
         )
         if not first_card:
            first_card = tariff_row.find("li", class_=lambda c: c and "common-flow-card" in c)
         if first_card:
            # common-flow-price__message
            price_msg = first_card.find("span", class_="common-flow-price__message")
            if price_msg:
               course["price"] = extract_price_from_text(price_msg.get_text())
         
         if first_card:
            # common-flow-price__message
            price_msg = first_card.find("span", class_="common-flow-price__message")
            if price_msg:
               price_text = price_msg.get_text()
               course["price"] = extract_price_from_text(price_text)
            # price-overall
            if course["price"] is None:
               price_overall = first_card.find("span", class_="price-overall")
               if price_overall:
                  course["price"] = extract_price_from_text(price_overall.get_text())
            # price_description
            if course["price"] is None:
               price_desc = first_card.find("div", class_="price_description")
               if price_desc:
                  course["price"] = extract_price_from_text(price_desc.get_text())
   return course


# -------------------------------------------------------------------
# ОСНОВНАЯ ФУНКЦИЯ
# -------------------------------------------------------------------
def main_yandex_practic(DB_NAME):
   browser = BrowserManager()
   db_name = DB_NAME
   print("=== Парсер Яндекс Практикум ===\n")
   print("Шаг 1: Загружаю каталог курсов...")
   html = browser.get_html(CATALOG_URL)
   cards_data = parse_catalog(html)
   print(f"Найдено курсов в каталоге: {len(cards_data)}\n")
   
   conn = get_connection(db_name)
   cursor = conn.cursor()

   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (8, 'Яндекс Практикум') "
      "ON DUPLICATE KEY UPDATE name = name"
   )
   conn.commit()

   saved = 0
   skipped = 0
   errors = 0
   
   print("Шаг 2: Обрабатываю каждый курс...\n")
   for i, card_data in enumerate(cards_data, 1):
      url = card_data["url"]
      print(f"  [{i}/{len(cards_data)}] {url}", end=" ... ", flush=True)

      try:
         resp = requests.get(url, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"ошибка запроса: {e}")
         errors += 1
         continue

      try:
         course = parse_course_page(url, resp.text, card_data, browser)
         db_course = {
               "organization_id": course["organization_id"],
               "title": course["title"],
               "price": course["price"],
               "format": course["format"],
               "duration": course["duration"],
               "date": course["date"],
               "description": course["description"],
               "url": course["url"],
               "language": course["language"],
               "document": course["document"],
               "course_type": course["course_type"],
               "admission_requirements": course["admission_requirements"],
               "schedule": course["schedule"],
               "duration_in_hours": course["duration_in_hours"],
               "department_id": course["department_id"],
         }
         course_id = save_course(cursor, db_course)
         
         if course_id is None:
               print("дубликат — пропущен")
               skipped += 1
               conn.commit()
               continue

         # Специализации
         for spec_name in course["specialization_names"]:
               spec_id = get_or_create_specialization(cursor, spec_name)
               link_course_specialization(cursor, course_id, spec_id)

         conn.commit()
         print(f"OK (id={course_id})")
         saved += 1

      except Exception as e:
         conn.rollback()
         print(f"ошибка парсинга: {e}")
         errors += 1

      time.sleep(random.uniform(2, 4))

   cursor.close()
   conn.close()

   print(f"\n=== Итог ===")
   print(f"Сохранено:  {saved}")
   print(f"Дубликатов: {skipped}")
   print(f"Ошибок:     {errors}")


if __name__ == "__main__":
   main_yandex_practic(DB_NAME)