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
from helpers import (
   clean_text,
   extract_price_from_text,
   extract_duration,
   get_html_with_playwright,
   get_html_with_playwright_selector
)
import random

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
BASE_URL = "https://practicum.yandex.ru"
CATALOG_URL = "https://practicum.yandex.ru/catalog/"
HEADERS = {"User-Agent": "Mozilla/5.0"}
ORGANIZATION_ID = 4  #####klvnbdxfbdlfkjg;dfsj'gjbf;gldfbgldsfng ldfb
DELAY = random.randint(5, 7) 
DB_NAME = "buff_dpo_db"


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------
def build_full_url(href: str) -> str:
   """Строит абсолютный URL из href."""
   if href.startswith("http"):
      return href
   return BASE_URL + href


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

      # Убираем ?from=catalog и прочие параметры для чистого URL
      url_clean = url.split("?")[0].rstrip("/") + "/"

      # Цена (Бесплатно)
      price = None
      badge = card_a.find("div", class_="prof-window-v2__card-badge_free")
      if badge and "Бесплатно" in badge.get_text():
         price = "0"

      # Специализации (через запятую в direction)
      specialization_names = []
      direction_div = card_a.find("div", class_="prof-window-v2__card-direction")
      if direction_div:
         direction_text = clean_text(direction_div.get_text())
         if direction_text:
               specialization_names = [s.strip() for s in direction_text.split(",") if s.strip()]

      # Название
      title_tag = card_a.find("h2", class_="prof-window-v2__card-title")
      title = clean_text(title_tag.get_text()) if title_tag else None

      # Срок (duration)
      footer_div = card_a.find("div", class_="prof-window-v2__card-footer")
      duration = None
      if footer_div:
         duration = extract_duration(footer_div.get_text())

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
def parse_course_page(url: str, html: str, card_data: dict) -> dict:
     
   soup = BeautifulSoup(html, "html.parser")
   
   html = get_html_with_playwright_selector(url, "span.common-flow-price__message")  # НАДО попробовать убрать селектор
   soup = BeautifulSoup(html, "html.parser")
   
   
   
   # if needs_playwright(soup, url):
   #    print(f" [DEBUG] Страница динамическая, использую Playwright...")
   #    html = get_html_with_playwright(url, "span.common-flow-price__message")
   #    soup = BeautifulSoup(html, "html.parser")
   # else:
   #    print(f" [WARN] Страница требует JS, но Playwright отключён")
   #    soup = BeautifulSoup(html, "html.parser")
   # Сначала проверяем, есть ли в HTML элемент заглушки цены. 
   # has_loading = soup.find(class_=lambda c: c and (
   #    "common-flow-card_loading" in c or 
   #    "prisma-skeleton" in c
   # ) if c else False)
   # if has_loading:
   #       print(" [DEBUG] Обнаружена заглушка, запускаю Playwright...")
   #       html = get_html_with_playwright(url,"пофик")
   #       soup = BeautifulSoup(html, "html.parser")
   # else:
   #    print(" [DEBUG] Цена уже в HTML, Playwright не нужен")
   

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

   # -------------------------------------------------------------------
   # Description
   # -------------------------------------------------------------------
   # Вариант 1: head-section__duration
   desc_div = soup.find("div", class_="head-section__duration")
   if desc_div:
      course["description"] = clean_text(desc_div.get_text())

   # Вариант 2: lc-grid2-item → first-description section → lc-styled-text__text
   if course["description"] == "Не указано":
      first_desc_section = soup.find("section", id="first-description")
      if first_desc_section:
         text_div = first_desc_section.find("div", class_="lc-styled-text__text")
         if text_div:
               course["description"] = clean_text(text_div.get_text())

   # -------------------------------------------------------------------
   # Date: ищем "Ближайший старт —"
   # -------------------------------------------------------------------
   # Вариант 1: .squad-surge-info span
   surge_div = soup.find("div", class_="squad-surge-info")
   if surge_div:
      span = surge_div.find("span")
      if span:
         text = clean_text(span.get_text())
         if "Ближайший старт" in text:
               # Берём всё после "— "
               parts = text.split("—", 1)
               if len(parts) > 1:
                  course["date"] = parts[1].strip()

   # Вариант 2: p.squad-dates
   if course["date"] == "Не указана":
      squad_dates = soup.find("p", class_="squad-dates")
      if squad_dates:
         text = clean_text(squad_dates.get_text())
         if "Ближайший старт" in text:
               parts = text.split("—", 1)
               if len(parts) > 1:
                  course["date"] = parts[1].strip()

   # -------------------------------------------------------------------
   # Document & course_type
   # Ищем маркеры в порядке приоритета:
   # 1. bullets-block (шапка курса) — самый надёжный источник
   # 2. paragraph-блоки в теле страницы (но не в FAQ)
   # 3. lc-styled-text__text — маркеры "Ваш диплом" / "Ваше свидетельство"
   # -------------------------------------------------------------------

   def _find_doc_in_container(container) -> tuple:
      """Возвращает (document, course_type) или (None, None)."""
      text = clean_text(container.get_text(" "))
      if re.search(r"[Дд]иплом\s+о\s+профессиональной\s+переподготовке", text):
         return "Диплом о профессиональной переподготовке", "Профессиональная переподготовка"
      if re.search(r"[Уу]достоверение\s+о\s+повышении\s+квалификации", text):
         return "Удостоверение о повышении квалификации", "Повышение квалификации"
      if re.search(r"[Вв]аш\s+диплом\s+после\s+обучения", text):
         return "Диплом после обучения", None
      if re.search(r"[Вв]аше\s+свидетельство\s+об\s+обучении", text):
         return "Свидетельство об обучении", None
      return None, None

   doc, ctype = None, None

   # Приоритет 1: bullets-block в шапке
   bullets_block = soup.find("ul", class_=lambda c: c and "bullets-block" in c)
   if bullets_block:
      doc, ctype = _find_doc_in_container(bullets_block)

   # Приоритет 2: paragraph-блоки (только те, что содержат слово "Выдадим" / "Получите")
   if not doc:
      for para in soup.find_all("div", class_="paragraph"):
         text = clean_text(para.get_text())
         if re.search(r"[Вв]ыдадим\s+диплом\s+о\s+профессиональной\s+переподготовке", text):
               doc, ctype = "Диплом о профессиональной переподготовке", "Профессиональная переподготовка"
               break
         if re.search(r"[Пп]олучите\s+удостоверение\s+о\s+повышении\s+квалификации", text):
               doc, ctype = "Удостоверение о повышении квалификации", "Повышение квалификации"
               break

   # Приоритет 3: lc-styled-text__text — для маркеров "Ваш диплом" / "Ваше свидетельство"
   if not doc:
      for styled in soup.find_all("div", class_=lambda c: c and "lc-styled-text__text" in c):
         text = clean_text(styled.get_text())
         if re.search(r"[Вв]аш\s+диплом\s+после\s+обучения", text):
               doc = "Диплом после обучения"
               break
         if re.search(r"[Вв]аше\s+свидетельство\s+об\s+обучении", text):
               doc = "Свидетельство об обучении"
               break

   # Приоритет 4: на странице явно есть "свидетельство об обучении" как основной документ
   # (ищем только в первых 5 FAQ-ответах, которые говорят о документах)
   if not doc:
      for styled in soup.find_all("div", class_=lambda c: c and "lc-styled-text__text" in c):
         text = clean_text(styled.get_text())
         if re.search(r"свидетельство\s+об\s+обучении", text):
               doc = "Свидетельство об обучении"
               break

   course["document"] = doc
   course["course_type"] = ctype

   # -------------------------------------------------------------------
   # Price (если ещё не установлена — price != "0")
   # -------------------------------------------------------------------
   if course["price"] is None:
       
      # Вариант 1: common-flow__row_tariff → первая карточка displayed → common-flow-price__message
      tariff_row = soup.find("ul", class_=lambda c: c and "common-flow__row_tariff" in c)
      
      if tariff_row:
         # Берём первую li.common-flow-card с классом displayed
         first_card = tariff_row.find(
               "li",
               class_=lambda c: c and "common-flow-card" in c and "common-flow-card_plus" not in c
         )
         if not first_card:
               first_card = tariff_row.find("li", class_=lambda c: c and "common-flow-card" in c)

         if first_card:
               # Вариант 1a: common-flow-price__message
               price_msg = first_card.find("span", class_="common-flow-price__message")
               if price_msg:
                  course["price"] = extract_price_from_text(price_msg.get_text())
         
         if first_card:
               # Вариант 1a: common-flow-price__message
               price_msg = first_card.find("span", class_="common-flow-price__message")
               if price_msg:
                  price_text = price_msg.get_text()
                  course["price"] = extract_price_from_text(price_text)

               # Вариант 1b: price-overall
               if course["price"] is None:
                  price_overall = first_card.find("span", class_="price-overall")
                  if price_overall:
                     course["price"] = extract_price_from_text(price_overall.get_text())

               # Вариант 1c: price_description
               if course["price"] is None:
                  price_desc = first_card.find("div", class_="price_description")
                  if price_desc:
                     course["price"] = extract_price_from_text(price_desc.get_text())
   return course


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main():
   print("=== Парсер Яндекс Практикум ===\n")

   print("Шаг 1: Загружаю каталог курсов...")
   try:
      resp = requests.get(CATALOG_URL, headers=HEADERS, timeout=30)
      resp.raise_for_status()
   except requests.RequestException as e:
      print(f"Ошибка загрузки каталога: {e}")
      return

   # cards_data = parse_catalog(resp.text)
   
   cards_data = [
      {
         "url": "https://practicum.yandex.ru/project-manager/", # Ломается
         "title": "Менеджер проектов",
         "price": None,
         "duration": "За 6 месяцев освоите востребованную IT-профессию, в которой не нужно писать код",
         "specialization_names": ["Менеджмент"]
      },
      {
         "url": "https://practicum.yandex.ru/product-manager-start/", # Ломается
         "title": "ЧМенеджер продукта",
         "price": None,
         "duration": "За 6 месяцев освоите востребованную IT-профессию, в которой не нужно писать код",
         "specialization_names": ["Менеджмент"]
      },
      {
         "url": "https://start.practicum.yandex/start-in-marketing/", # стоит 0
         "title": "Какую профессию выбрать в маркетинге",
         "price": None,  
         "duration": "Зuufudsuufsdufsdufusй не нужно писать код",
         "specialization_names": ["куда податься"]
      },
      {
         "url": "https://practicum.yandex.ru/interface-designer/", # Не ломается
         "title": "Дизайнер интерфейсов",
         "price": None,
         "duration": "oiweorhwkfbsdjfklsdk нужно писать код",
         "specialization_names": ["Дизайн"]
      },
      {
         "url": "https://practicum.yandex.ru/1c-programmer/", # Ломается
         "title": "Разработчик 1С",
         "price": None,
         "duration": "За 6 АХАХАХАХАХАХАХАХАХАХАХАХААХА",
         "specialization_names": ["Программирование"]
      },
      
   ]

   print(f"Найдено курсов в каталоге: {len(cards_data)}\n")

   conn = get_connection(DB_NAME)
   cursor = conn.cursor()

   # Убеждаемся, что организация Яндекс Практикум существует (id=4)
   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (4, 'Яндекс Практикум') "
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
         course = parse_course_page(url, resp.text, card_data)

         # Готовим dict для INSERT (только нужные поля)
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

         # Специализации (many-to-many)
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

      time.sleep(DELAY)

   cursor.close()
   conn.close()

   print(f"\n=== Итог ===")
   print(f"Сохранено:  {saved}")
   print(f"Дубликатов: {skipped}")
   print(f"Ошибок:     {errors}")


if __name__ == "__main__":
   main()
   