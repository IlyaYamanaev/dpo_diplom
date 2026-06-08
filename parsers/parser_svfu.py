import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from db_functions import get_connection, save_course
from utilit import clean_text, get_html_with_playwright_selector   # важный импорт!

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
BASE_URL = "https://opensvfu.ru"
CATALOG_PP_URL = "https://opensvfu.ru/?tfc_storepartuid%5B857393129%5D=Профессиональная+переподготовка&tfc_div=:::"
CATALOG_PK_URL = "https://opensvfu.ru/?tfc_storepartuid%5B857393129%5D=Повышение+квалификации&tfc_div=:::"
HEADERS = {
   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
ORGANIZATION_ID = 11
ORGANIZATION_NAME = "СВФУ"
DB_NAME = "dpo_db"
DELAY = 0.5

# ---------------------------------------------------------------------------
# 1. Сбор ссылок на курсы для заданного типа (с пагинацией)
# ---------------------------------------------------------------------------
def collect_course_urls_by_type(catalog_url: str, course_type: str) -> list:
   """
   Парсит все страницы каталога для одного типа курсов,
   используя Playwright для получения динамической разметки.
   Возвращает список URL курсов.
   """
   urls = []
   page = 1
   print(f"\n  Обработка типа: {course_type}")

   while True:
      # Для пагинации добавляем параметр ?page=N (если он поддерживается)
      if page == 1:
         page_url = catalog_url
      else:
         # Формируем URL с параметром страницы (проверено на opensvfu.ru)
         # Если site использует tfc_page, можно использовать:
         if "tfc_page" not in catalog_url:
               sep = "&" if "?" in catalog_url else "?"
               page_url = f"{catalog_url}{sep}tfc_page%5B857393129%5D={page}"
         else:
               page_url = catalog_url

      print(f"    Страница {page}: {page_url}")

      # Ждём появления хотя бы одной карточки (селектор .js-product)
      html = get_html_with_playwright_selector(page_url, ".js-product")
      soup = BeautifulSoup(html, "html.parser")

      # Контейнер со списком карточек
      card_list = soup.find("div", class_="t-store__card-list")
      if not card_list:
         # Попробуем альтернативный контейнер
         card_list = soup.find("div", class_="t-store__grid-cont")
      if not card_list:
         print("    Не найден контейнер с карточками — останов")
         break

      cards = card_list.find_all("div", class_=lambda c: c and "js-product" in c and "t-store__card" in c)
      if not cards:
         # Попробуем другой класс
         cards = card_list.find_all("div", class_="t-store__card")
      if not cards:
         print("    Нет карточек на странице — останов")
         break

      page_urls = []
      for card in cards:
         link = card.find("a", href=True)
         if link and link.get("href"):
               href = link["href"]
               full_url = urljoin(BASE_URL, href)
               if full_url not in urls:
                  page_urls.append(full_url)

      print(f"    Найдено карточек: {len(cards)}, новых ссылок: {len(page_urls)}")
      urls.extend(page_urls)

      # Проверяем наличие следующей страницы
      pagination = soup.find("div", class_="t-store__pagination")
      if pagination:
         next_btn = pagination.find("div", class_=lambda c: c and "t-store__pagination__item_next" in (c or ""))
         if not next_btn or "t-store__pagination__item_disabled" in (next_btn.get("class") or []):
               break
      else:
         # Если пагинации нет, значит это единственная страница
         break

      page += 1
      time.sleep(DELAY)

   print(f"    Всего URL для '{course_type}': {len(urls)}")
   return urls


def collect_all_course_urls() -> dict:
   """
   Собирает URL курсов для обоих типов (профпереподготовка и повышение квалификации).
   Возвращает словарь {url: course_type}
   """
   all_urls = {}

   # Профессиональная переподготовка
   pp_urls = collect_course_urls_by_type(CATALOG_PP_URL, "Профессиональная переподготовка")
   for url in pp_urls:
      all_urls[url] = "Профессиональная переподготовка"

   # Повышение квалификации
   pk_urls = collect_course_urls_by_type(CATALOG_PK_URL, "Повышение квалификации")
   for url in pk_urls:
      all_urls[url] = "Повышение квалификации"

   return all_urls


# ---------------------------------------------------------------------------
# 2. Парсинг страницы курса (остаётся без изменений, он работает)
# ---------------------------------------------------------------------------
def parse_course_page(url: str, html: str, course_type: str) -> dict:
   """Парсит страницу курса и возвращает словарь с данными для сохранения в БД."""
   soup = BeautifulSoup(html, "html.parser")

   # Блок с основной информацией
   info_block = soup.find("div", class_="t-store__prod-popup__info")
   if not info_block:
      # Возможно, попап открывается в другом блоке
      info_block = soup.find("div", class_="t-store__prod-popup")

   if not info_block:
      # fallback: ищем поля по всей странице
      info_block = soup

   course = {
      "organization_id": ORGANIZATION_ID,
      "url": url,
      "title": None,
      "price": None,
      "format": None,
      "course_type": course_type,
      "duration": None,
      "description": None,
      "language": "русский",
      "date": None,
      "document": None,
      "admission_requirements": "Не указаны",
      "schedule": "Не указан",
      "duration_in_hours": "Не указана",
      "department_id": None,
   
   }

   # --- Название ---
   title_tag = info_block.find("h1", class_="js-store-prod-name")
   if not title_tag:
      title_tag = soup.find("h1", class_="t-store__prod-popup__name")
   if title_tag:
      course["title"] = clean_text(title_tag.get_text(strip=True))

   # --- Цена ---
   price_tag = info_block.find("div", class_="js-product-price")
   if not price_tag:
      price_tag = info_block.find("div", class_="js-store-prod-price-val")

   if price_tag:
      # Пробуем взять значение из data-атрибута (может быть "2000" или "2000.00")
      price_def = price_tag.get("data-product-price-def")
      if price_def:
         # Преобразуем в число с плавающей точкой, затем в целое (отбрасываем копейки)
         try:
               price_clean = str(int(float(price_def)))
               course["price"] = price_clean
         except ValueError:
               pass
      else:
         # Если data-атрибута нет – парсим текст, удаляя всё кроме цифр
         price_val = price_tag.get_text(strip=True)
         import re
         price_clean = re.sub(r'[^\d]', '', price_val)
         if price_clean:
               course["price"] = price_clean

   # --- Описание ---
   desc_block = info_block.find("div", class_="js-store-prod-all-text")
   if desc_block:
      desc_text = clean_text(desc_block.get_text(separator="\n", strip=True))
      if desc_text:
         course["description"] = desc_text

   # --- Характеристики (часы, срок, формат) ---
   charcs_block = info_block.find("div", class_="js-store-prod-all-charcs")
   if charcs_block:
      # Ищем все <p> с классом js-store-prod-charcs (он есть именно у характеристик)
      for p in charcs_block.find_all("p", class_="js-store-prod-charcs"):
         text = p.get_text(strip=True)
         if not text:
               continue

         # Разделяем по двоеточию, если оно есть
         if ":" in text:
               key, value = text.split(":", 1)
               key = key.strip().lower()
               value = value.strip()
         else:
               key = text.lower()
               value = ""

         # Гибкое сравнение (не жёсткое "количество часов", а по ключевым словам)
         if "часов" in key or "количество часов" in key:
               course["duration_in_hours"] = value
         elif "срок" in key and "обучения" in key:
               course["duration"] = value
         elif "форма" in key and "обучения" in key:
               course["format"] = value

   # --- Определение документа по типу курса ---
   if course_type == "Профессиональная переподготовка":
      course["document"] = "Диплом о профессиональной переподготовке"
   elif course_type == "Повышение квалификации":
      course["document"] = "Удостоверение о повышении квалификации"

   # Дополнительная очистка
   for key in ["title", "price", "format", "duration", "description", "duration_in_hours"]:
      if course[key] is not None:
         course[key] = clean_text(course[key])

   return course


# ---------------------------------------------------------------------------
# 3. Основная функция
# ---------------------------------------------------------------------------
def main_svfu(db_name):
   print("=== Парсер СВФУ (программы ДПО) ===\n")

   # Подключение к БД
   conn = get_connection(db_name)
   cursor = conn.cursor()

   # Убеждаемся, что организация существует
   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (%s, %s) "
      "ON DUPLICATE KEY UPDATE name = name",
      (ORGANIZATION_ID, ORGANIZATION_NAME)
   )
   conn.commit()
   print(f"Организация '{ORGANIZATION_NAME}' (id={ORGANIZATION_ID}) готова.\n")

   print("Шаг 1: Сбор ссылок на курсы по типам (с использованием Playwright)...")
   course_urls = collect_all_course_urls()
   print(f"\nВсего уникальных курсов: {len(course_urls)}\n")

   saved = 0
   skipped = 0
   errors = 0

   print("Шаг 2: Парсинг страниц курсов и сохранение...\n")
   session = requests.Session()
   session.headers.update({"User-Agent": HEADERS["User-Agent"]})

   for i, (url, ctype) in enumerate(course_urls.items(), 1):
      print(f"  [{i}/{len(course_urls)}] {url}", end=" ... ", flush=True)

      try:
         resp = session.get(url, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"ошибка запроса: {e}")
         errors += 1
         time.sleep(DELAY)
         continue

      try:
         course = parse_course_page(url, resp.text, ctype)

         # Сохраняем курс (функция save_course возвращает id или None при дубликате)
         course_id = save_course(cursor, course)

         if course_id is None:
               print("дубликат — пропущен")
               skipped += 1
               conn.commit()
               time.sleep(DELAY)
               continue

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
   print(f"Сохранено:   {saved}")
   print(f"Дубликатов:  {skipped}")
   print(f"Ошибок:      {errors}")


if __name__ == "__main__":
   main_svfu(DB_NAME)