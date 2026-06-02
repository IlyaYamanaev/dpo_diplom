import time
import requests
from bs4 import BeautifulSoup
from db_functions import (
   get_connection,
   save_course,
   get_or_create_specialization,
   link_course_specialization,
)
from helpers import clean_text

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
BASE_URL = "https://dpo.kantiana.ru/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
ORGANIZATION_ID = 6
DELAY = 0.4
DB_NAME = "buff_dpo_db"


# ---------------------------------------------------------------------------
# Получение списка категорий с главной страницы
# ---------------------------------------------------------------------------
def get_categories(soup):
   """
   Извлекает URL всех категорий (направлений) с главной страницы.
   Ищет слайдер с классами swiper-categories и swiper-wrapper
   """
   categories_urls = []
   
   # Ищем контейнер категорий
   categories_slider = soup.find("div", class_="swiper-container")
   if not categories_slider:
      # Пробуем найти по другому классу
      categories_slider = soup.find("div", class_=lambda x: x and "swiper-categories" in x)
   
   if categories_slider:
      swiper_wrapper = categories_slider.find("div", class_="swiper-wrapper")
      if swiper_wrapper:
         for slide in swiper_wrapper.find_all("div", class_="swiper-slide"):
               # Ищем ссылку на категорию внутри categories__item
               cat_link = slide.find("a", href=True)
               if cat_link and cat_link.get("href"):
                  href = cat_link["href"]
                  if href.startswith("/"):
                     href = "https://dpo.kantiana.ru" + href
                  if href not in categories_urls and "/napravleniya/" in href:
                     categories_urls.append(href)
   
   # Если не нашли через слайдер, ищем через меню "Направления"
   if not categories_urls:
      nav_dropdown = soup.find("div", class_="header__nav-dropdown")
      if nav_dropdown:
         for link in nav_dropdown.find_all("a", href=True):
               href = link["href"]
               if "/napravleniya/" in href and href not in categories_urls:
                  categories_urls.append(href)
   
   return categories_urls


# ---------------------------------------------------------------------------
# Сбор URL курсов со страницы категории
# ---------------------------------------------------------------------------
def get_course_urls_from_category(category_url: str) -> list:
   """
   Парсит страницу категории и возвращает список URL всех курсов на ней.
   Поддерживает пагинацию (если есть).
   """
   course_urls = []
   page = 1
   
   while True:
      if page == 1:
         url = category_url
      else:
         # Формат пагинации: category_url?page=N или /page/N/
         if "?" in category_url:
               url = category_url + f"&page={page}"
         else:
               url = category_url.rstrip("/") + f"/page/{page}/"
      
      try:
         resp = requests.get(url, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"ошибка: {e}")
         break
      
      soup = BeautifulSoup(resp.text, "html.parser")
      
      # Ищем список курсов
      products_list = soup.find("ul", class_="products__list")
      if not products_list:
         products_list = soup.find("div", class_="products__list")
      
      if not products_list:
         print("нет списка курсов")
         break
      
      # Ищем все карточки курсов
      items = products_list.find_all("li")
      if not items:
         # Может быть другая структура
         items = products_list.find_all("div", class_="products__item")
      
      if not items:
         print("нет карточек курсов")
         break
      
      page_urls = []
      for item in items:
         title_link = item.find("a", class_="products__item-title")
         if not title_link:
               title_link = item.find("a", href=True, class_=lambda x: x and "products__item" in str(x))
         if title_link and title_link.get("href"):
               href = title_link["href"]
               if href.startswith("/"):
                  href = "https://dpo.kantiana.ru" + href
               if href not in page_urls:
                  page_urls.append(href)
      
      print(f"    Hайдено {len(page_urls)} курсов")
      course_urls.extend(page_urls)
      
      # Проверяем наличие следующей страницы
      pagination = soup.find("ul", class_="pagination")
      if pagination:
         next_li = pagination.find("li", class_="pagination__item--next")
         if next_li:
               next_link = next_li.find("a")
               if not next_link:
                  break
         else:
               break
      else:
         # Проверяем альтернативную пагинацию
         next_link = soup.find("a", rel="next")
         if not next_link:
               break
      
      page += 1
      time.sleep(DELAY)
   
   return course_urls


# ---------------------------------------------------------------------------
# Сбор всех URL курсов со всех категорий
# ---------------------------------------------------------------------------
def collect_all_course_urls() -> list:
   """
   Парсит главную страницу, находит все категории и собирает URL курсов.
   Возвращает список уникальных URL.
   """
   print("Шаг 1: Получение списка категорий с главной страницы...")
   
   try:
      resp = requests.get(BASE_URL, headers=HEADERS, timeout=30)
      resp.raise_for_status()
   except requests.RequestException as e:
      print(f"Ошибка загрузки главной страницы: {e}")
      return []
   
   soup = BeautifulSoup(resp.text, "html.parser")
   categories = get_categories(soup)
      
   print(f"Найдено категорий: {len(categories)}")
      
   all_urls = []
   print("\nШаг 2: Сбор URL курсов из категорий...")
   for i, cat_url in enumerate(categories, 1):
      print(f"  Категория {i}/{len(categories)}: {cat_url}")
      urls = get_course_urls_from_category(cat_url)
      all_urls.extend(urls)
      time.sleep(DELAY)
   # Удаляем дубликаты
   unique_urls = list(dict.fromkeys(all_urls))
   print(f"\nВсего уникальных курсов: {len(unique_urls)}")
   return unique_urls


# ---------------------------------------------------------------------------
# Парсинг страницы курса
# ---------------------------------------------------------------------------
def parse_course_page(url: str, html: str, specialization_name: str = None) -> dict:
   """Парсит страницу курса и возвращает словарь с данными"""
   soup = BeautifulSoup(html, "html.parser")
   
   course = {
      "organization_id": ORGANIZATION_ID,
      "url": url,
      "title": None,
      "price": None,
      "format": None,
      "course_type": "Не указан",
      "duration": "Не указана",
      "duration_in_hours": "Не указана",
      "description": "Не указано",
      "language": "русский",
      "date": "Не указана",
      "document": None,
      "admission_requirements": "Не указаны",
      "schedule": "Не указан",
      "department_id": None,
      "specialization_names": [],
   }
   
   # Добавляем специализацию из категории, если передана
   if specialization_name:
      course["specialization_names"].append(specialization_name)
   
   # -------------------------------------------------------------------
   # Заголовок курса
   # -------------------------------------------------------------------
   title_tag = soup.find("h1", class_="breadcrumbs__title")
   if title_tag:
      course["title"] = clean_text(title_tag.get_text(strip=True))
   
   # -------------------------------------------------------------------
   # Специализации из хлебных крошек (breadcrumbs)
   # -------------------------------------------------------------------
   breadcrumbs = soup.find("ul", class_="breadcrumbs__menu")
   if breadcrumbs:
      for li in breadcrumbs.find_all("li"):
         link = li.find("a", class_="breadcrumbs__link")
         if link:
               spec_name = clean_text(link.get_text(strip=True))
               # Исключаем "Главная"
               if spec_name and spec_name != "Главная" and spec_name not in course["specialization_names"]:
                  course["specialization_names"].append(spec_name)
   
   # -------------------------------------------------------------------
   # Цена
   # -------------------------------------------------------------------
   price_tag = soup.find("p", class_="sku__price")
   if price_tag:
      price_text = clean_text(price_tag.get_text(strip=True))
      if price_text:
         course["price"] = price_text
   
   # -------------------------------------------------------------------
   # Характеристики (таблица sku__details-table)
   # -------------------------------------------------------------------
   details_table = soup.find("table", class_="sku__details-table")
   if details_table:
      # Проходим по всем строкам таблицы
      for row in details_table.find_all("tr"):
         # В каждой строке может быть несколько ячеек с параметрами
         cells = row.find_all("td")
         for cell in cells:
               # Ищем small внутри ячейки - это название параметра
               small = cell.find("small")
               if small:
                  param_name = clean_text(small.get_text(strip=True))
                  # Удаляем small, чтобы получить значение
                  small.decompose()
                  param_value = clean_text(cell.get_text(strip=True))
                  
                  # Определяем тип параметра и заполняем соответствующие поля
                  if "Продолжительность" in param_name:
                     course["duration_in_hours"] = param_value
                  elif "Срок обучения" in param_name:
                     course["duration"] = param_value
                  elif "Формат обучения" in param_name:
                     course["format"] = param_value
                  # Можно добавить и другие параметры, если нужно
                  # elif "Авторы" in param_name:
                  #     pass  # Авторы не сохраняются в текущей схеме БД
   
   # -------------------------------------------------------------------
   # Описание (product-description-text)
   # -------------------------------------------------------------------
   desc_block = soup.find("div", class_="product-description-text")
   if desc_block:
      editor = desc_block.find("div", class_="editor")
      if editor:
         # Берём все параграфы, кроме пустых
         paragraphs = []
         for p in editor.find_all("p"):
               p_text = clean_text(p.get_text(strip=True))
               if p_text and len(p_text) > 10:  # игнорируем слишком короткие
                  paragraphs.append(p_text)
         if paragraphs:
               course["description"] = "\n\n".join(paragraphs[:5])  # ограничиваем длину
   
   # -------------------------------------------------------------------
   # Определение document и course_type по тексту на странице
   # -------------------------------------------------------------------
   page_text = soup.get_text().lower()
   
   if "диплом о профессиональной переподготовке" in page_text:
      course["document"] = "Диплом о профессиональной переподготовке"
      course["course_type"] = "Профессиональная переподготовка"
   elif "удостоверение о повышении квалификации" in page_text:
      course["document"] = "Удостоверение о повышении квалификации"
      course["course_type"] = "Повышение квалификации"
   
   # Если не нашли, но в тексте есть "повышение квалификации"
   if course["course_type"] == "Не указан":
      if "повышение квалификации" in page_text:
         course["course_type"] = "Повышение квалификации"
         if not course["document"]:
               course["document"] = "Удостоверение о повышении квалификации"
      elif "профессиональная переподготовка" in page_text:
         course["course_type"] = "Профессиональная переподготовка"
         if not course["document"]:
               course["document"] = "Диплом о профессиональной переподготовке"
   
   # Очищаем все текстовые поля
   for key in ["title", "price", "format", "duration", "duration_in_hours", 
               "description", "language", "document", "admission_requirements", 
               "schedule", "course_type"]:
      if course.get(key):
         course[key] = clean_text(course[key])
   
   return course


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main_bfu(DB_NAME):
   db_name = DB_NAME
   print("=== Парсер БФУ ДПO ===\n")
   print(f"Organization ID: {ORGANIZATION_ID} (БФУ)\n")
   
   # Шаг 1: Собираем все URL курсов
   course_urls = collect_all_course_urls()
   
   if not course_urls:
      print("Не найдено ни одного курса. Проверьте доступность сайта.")
      return
   
   print(f"\nШаг 3: Обработка {len(course_urls)} курсов...\n")
   
   # Подключаемся к БД
   conn = get_connection(db_name)
   cursor = conn.cursor()
   
   # Убеждаемся, что организация существует
   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (6, 'БФУ') "
      "ON DUPLICATE KEY UPDATE name = name"
   )  
   conn.commit()
   
   saved = 0
   skipped = 0
   errors = 0
   
   for i, url in enumerate(course_urls, 1):
      print(f"  [{i}/{len(course_urls)}] {url}", end=" ... ", flush=True)
      
      try:
         resp = requests.get(url, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"ошибка загрузки: {e}")
         errors += 1
         continue
      
      try:
         # Парсим страницу курса
         course = parse_course_page(url, resp.text)
         
         if not course["title"]:
               print("нет заголовка — пропущен")
               skipped += 1
               continue
         
         # Сохраняем курс
         course_id = save_course(cursor, course)
         
         if course_id is None:
               print("дубликат — пропущен")
               skipped += 1
               conn.commit()
               continue
         
         # Привязываем специализации
         for spec_name in course["specialization_names"]:
               if spec_name and spec_name != "Главная":
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
   print(f"Сохранено:   {saved}")
   print(f"Дубликатов:  {skipped}")
   print(f"Ошибок:      {errors}")


if __name__ == "__main__":
   main_bfu(DB_NAME)