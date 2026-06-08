import random
import time
import requests
from bs4 import BeautifulSoup
from db_functions import (
   get_connection,
   save_course,
)
from utilit import clean_text

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
BASE_URL = "https://ino.sfu-kras.ru"
CATALOG_URL = "https://ino.sfu-kras.ru/programs_catalog"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
ORGANIZATION_ID = 12
TOTAL_PAGES = 10 
DELAY = 0.8
DB_NAME = "dpo_db"

# ---------------------------------------------------------------------------
# 1. Обход каталога — сбор карточек со всех страниц пагинации
# ---------------------------------------------------------------------------
def collect_catalog_courses() -> list:
   """
   Проходит по всем страницам каталога ,
   парсит карточки курсов и возвращает список словарей
   с предварительными данными + url каждого курса.
   """
   courses_preview = []

   for page in range(TOTAL_PAGES):
      url = f"{CATALOG_URL}?page={page}#programs-store"
      print(f"  Страница {page + 1}/{TOTAL_PAGES}: {url}")

      try:
         resp = requests.get(url, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"    Ошибка загрузки: {e}")
         continue

      soup = BeautifulSoup(resp.text, "html.parser")

      programs_store = soup.find("div", id="programs-store")
      if not programs_store:
         print("    Блок #programs-store не найден")
         continue

      row = programs_store.find("div", class_="row")
      if not row:
         print("    Список курсов (row) не найден")
         continue

      cards = row.find_all("div", class_=lambda c: c and
         "col-lg-4" in c and "col-md-6" in c and "col-xs-12" in c)

      if not cards:
         print("    Карточки курсов не найдены")
         continue

      page_count = 0
      for card in cards:
         link_tag = card.find("a", class_="program-banner-link")
         if not link_tag:
               continue

         href = link_tag.get("href", "")
         if not href:
               continue
         if href.startswith("/"):
               full_url = BASE_URL + href
         else:
               full_url = href

         # Заголовок
         h3 = link_tag.find("h3")
         title = clean_text(h3.get_text(strip=True)) if h3 else None

         # Дивы внутри ссылки: цена, дата, формат, часы
         divs = link_tag.find_all("div")
         price = None
         date = None
         fmt = None
         duration_in_hours = None

         if len(divs) >= 1:
               price = clean_text(divs[0].get_text(strip=True))
         if len(divs) >= 2:
               date = clean_text(divs[1].get_text(strip=True))
         if len(divs) >= 3:
               fmt = clean_text(divs[2].get_text(strip=True))
         if len(divs) >= 4:
               duration_in_hours = clean_text(divs[3].get_text(strip=True))

         courses_preview.append({
               "url": full_url,
               "title": title,
               "price": price,
               "date": date,
               "format": fmt,
               "duration_in_hours": duration_in_hours,
         })
         page_count += 1

      print(f"    Найдено карточек: {page_count}")
      time.sleep(random.uniform(2, 3))

   print(f"\nВсего карточек со всех страниц: {len(courses_preview)}")
   return courses_preview


# ---------------------------------------------------------------------------
# 2. Парсинг страницы курса — дополняем данные из карточки
# ---------------------------------------------------------------------------
def parse_course_page(preview: dict, html: str) -> dict:
   """
   Принимает предварительные данные из карточки каталога и HTML страницы курса.
   Дополняет запись полем document, course_type и description.
   Возвращает итоговый словарь для сохранения в БД.
   """
   soup = BeautifulSoup(html, "html.parser")

   course = {
      "organization_id": ORGANIZATION_ID,
      "url": preview["url"],
      "title": preview.get("title"),
      "price": preview.get("price"),
      "format": preview.get("format"),
      "date": preview.get("date"),
      "duration_in_hours": preview.get("duration_in_hours"),
      "document": None,
      "course_type": None,
      "description": None,
      "duration": None,
      "language": None,
      "admission_requirements": None,
      "schedule": None,
      "department_id": None,
   }

   # -------------------------------------------------------------------
   # Ищем блок с деталями курса: .node.node-program > .content
   # -------------------------------------------------------------------
   content = None
   node = soup.find("div", class_="node-program")
   if node:
      content = node.find("div", class_="content")

   if content:
      # Выдаваемый документ — ищем label-ячейку и следующую за ней
      rows = content.find_all("div", class_="row")
      for row in rows:
         label_divs = row.find_all("div", class_=lambda c: c and "text-secondary" in c)
         for label_div in label_divs:
            label_text = label_div.get_text(strip=True)
            if "Выдаваемый документ" in label_text:
               # Значение — следующий sibling div
               value_div = label_div.find_next_sibling("div")
               if value_div:
                  doc_text = clean_text(value_div.get_text(strip=True))
                  course["document"] = doc_text

                  # Определяем course_type по документу
                  if "Удостоверение о повышении квалификации" in doc_text:
                     course["course_type"] = "Повышение квалификации"
                  elif "Диплом о профессиональной переподготовке" in doc_text:
                     course["course_type"] = "Профессиональная переподготовка"
                  elif "Сертификат" in doc_text:
                     course["course_type"] = "Курс"
                  elif "Свидетельство о профессии рабочего, должности служащего" in doc_text:
                     course["course_type"] = "Профессиональная переподготовка"
      # Описание — весь текст из блока mt-5 (очищенный и обрезанный до 500 символов)
      mt5_block = content.find("div", class_="mt-5")
      if mt5_block:
         # Берём весь текст, разделитель пробел, убираем лишние пробелы и переводы строк
         desc_text = clean_text(mt5_block.get_text(separator=" ", strip=True))
         if desc_text:
            # Обрезаем до 500 символов (можно изменить при необходимости)
            course["description"] = desc_text[:500]

   # Финальная очистка текстовых полей
   for key in ["title", "price", "format", "date", "duration_in_hours",
            "document", "course_type", "description"]:
      if course.get(key):
         course[key] = clean_text(course[key])

   return course


# ---------------------------------------------------------------------------
# 3. Основная функция
# ---------------------------------------------------------------------------
def main_sfu(db_name=DB_NAME):
   print("=== Парсер СФУ ДПО ===\n")
   print(f"Organization ID: {ORGANIZATION_ID} (СФУ)\n")

   # Шаг 1: Обходим каталог — собираем карточки
   print("Шаг 1: Сбор карточек из каталога...\n")
   courses_preview = collect_catalog_courses()

   if not courses_preview:
      print("Не найдено ни одного курса. Проверьте доступность сайта.")
      return

   conn = get_connection(db_name)
   cursor = conn.cursor()

   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (12, 'СФУ') "
      "ON DUPLICATE KEY UPDATE name = name"
   )
   conn.commit()

   # Шаг 3: Парсим страницы курсов и сохраняем в БД
   print(f"\nШаг 2: Обработка {len(courses_preview)} курсов...\n")

   saved = 0
   skipped = 0
   errors = 0

   for i, preview in enumerate(courses_preview, 1):
      url = preview["url"]
      print(f"  [{i}/{len(courses_preview)}] {url}", end=" ... ", flush=True)

      try:
         resp = requests.get(url, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"ошибка загрузки: {e}")
         errors += 1
         continue

      try:
         course = parse_course_page(preview, resp.text)

         if not course["title"]:
               print("нет заголовка — пропущен")
               skipped += 1
               continue

         course_id = save_course(cursor, course)

         if course_id is None:
               print("дубликат — пропущен")
               skipped += 1
               conn.commit()
               continue

         conn.commit()
         print(f"OK (id={course_id})")
         saved += 1

      except Exception as e:
         conn.rollback()
         print(f"ошибка парсинга: {e}")
         errors += 1

      time.sleep(random.uniform(2, 3))

   cursor.close()
   conn.close()

   print(f"\n=== Итог ===")
   print(f"Сохранено:   {saved}")
   print(f"Дубликатов:  {skipped}")
   print(f"Ошибок:      {errors}")


if __name__ == "__main__":
   main_sfu(DB_NAME)