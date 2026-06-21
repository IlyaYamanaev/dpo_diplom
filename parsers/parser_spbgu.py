import re
import time
import requests
from bs4 import BeautifulSoup

from db_functions import (
   get_connection,
   save_course,
   get_or_create_department,
   update_department_contacts,
)

from utilit import clean_text


# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
BASE_URL = "https://spbu.ru"
CATALOG_URL = "https://spbu.ru/postupayushchim/programms/dopolnitelnyeprogrammy?view=table"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DB_NAME = "buff_dpo_db"
ORGANIZATION_ID = 7
ORGANIZATION_NAME = "СПбГУ"
DELAY = 0.3

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def extract_text_except_link(soup_elem, link_class="bt-link"):
   """Извлекает текст, исключая содержимое тегов <a> с указанным классом."""
   if soup_elem is None:
      return ""
   result_parts = []
   stack = [soup_elem]
   while stack:
      node = stack.pop()
      if isinstance(node, str):
         result_parts.append(node)
      elif hasattr(node, 'children'):
         if node.name == 'a' and link_class in node.get('class', []):
               continue
         for child in reversed(list(node.children)):
               stack.append(child)
   return clean_text(''.join(result_parts))

# ---------------------------------------------------------------------------
# 1. Сбор ссылок из каталога
# ---------------------------------------------------------------------------
def collect_course_urls() -> list:
   """Загружает страницу каталога и возвращает список URL всех программ."""
   print(f"Загружаю каталог: {CATALOG_URL}")
   resp = requests.get(CATALOG_URL, headers=HEADERS, timeout=30)
   resp.raise_for_status()
   soup = BeautifulSoup(resp.text, "html.parser")

   urls = []
   for table_block in soup.find_all("div", class_="table-programs"):
      table = table_block.find("div", class_="table")
      if not table:
         continue
      for row in table.find_all("div", class_="table__row--link"):
         link_tag = row.find("a", class_="table__cover-link")
         if link_tag and link_tag.get("href"):
               href = link_tag["href"]
               full_url = BASE_URL + href if href.startswith("/") else href
               urls.append(full_url)

   # Убираем дубликаты
   seen = set()
   unique_urls = []
   for u in urls:
      if u not in seen:
         seen.add(u)
         unique_urls.append(u)
   print(f"Найдено уникальных курсов: {len(unique_urls)}")
   return unique_urls

# ---------------------------------------------------------------------------
# 2. Парсинг страницы курса
# ---------------------------------------------------------------------------
def parse_course_page(html: str, url: str) -> dict:
   soup = BeautifulSoup(html, "html.parser")

   # Название
   title_tag = soup.find("h1", class_=re.compile(r"program-headline__title"))
   title = clean_text(title_tag.get_text()) if title_tag else None

   # Описание
   editor_div = soup.find("div", class_="editor editor--sans")
   description = extract_text_except_link(editor_div) if editor_div else None

   # Блок с деталями
   details_container = soup.find("div", class_="program-details")
   details = {}
   if details_container:
      for p in details_container.find_all("p", class_="program-details__info"):
         span = p.find("span")
         if not span:
               continue
         key = clean_text(span.get_text())
         # Берём значение как весь текст
         full_text = clean_text(p.get_text())
         span_text = clean_text(span.get_text())
         if full_text.startswith(span_text):
               value = full_text[len(span_text):].strip()
         else:
               value = full_text.replace(span_text, "").strip()
         if key and value:
               details[key] = value

   # функции для цены и часов
   def parse_price(price_str):
      if not price_str:
         return None
      price_str = clean_text(price_str)
      if "(" in price_str:
         price_str = price_str.split("(")[0].strip()
      if "/" in price_str:
         price_str = price_str.split("/")[0].strip()

      return price_str

   def parse_hours(hours_str):
      if not hours_str:
         return None
      hours_str = clean_text(hours_str)
      if "(" in hours_str:
         hours_str = hours_str.split("(")[0].strip()
      return hours_str

   course_type = details.get("Тип программы")
   duration = details.get("Продолжительность обучения")
   duration_in_hours = parse_hours(details.get("Объем обучения"))
   format_val = details.get("Форма обучения")
   doc = details.get("Выдаваемый документ")
   document = doc.split("/")[0].strip()
   price = parse_price(details.get("Стоимость обучения"))
   schedule_info = details.get("График обучения")
   date = schedule_info
   language = details.get("Язык обучения")
   address = details.get("Место обучения")

   department_name = None
   b_tag = details_container.find("b", id="dop_prog_centr") if details_container else None
   if b_tag:
      department_name = clean_text(b_tag.get_text())

   # Контакты
   emails = []
   email_link = details_container.find("a", href=lambda x: x and x.startswith("mailto:")) if details_container else None
   if email_link:
      emails.append(clean_text(email_link.get_text()))

   phones = []
   phone_links = details_container.find_all("a", href=lambda x: x and x.startswith("tel:")) if details_container else []
   for tel in phone_links:
      phone_text = clean_text(tel.get_text())
      for ph in re.split(r"[;,]\s*", phone_text):
         if ph:
               phones.append(ph)

   return {
      "organization_id": ORGANIZATION_ID,
      "title": title,
      "price": price,
      "format": format_val,
      "course_type": course_type,
      "duration": duration,
      "date": date,
      "description": description,
      "url": url,
      "language": language,
      "document": document,
      "admission_requirements": None,
      "schedule": schedule_info,
      "duration_in_hours": duration_in_hours,
      "department_name": department_name,
      "department_address": address,
      "department_phones": phones,
      "department_emails": emails,
   }

# ---------------------------------------------------------------------------
# 3. Основной цикл
# ---------------------------------------------------------------------------
def main_spbgu(DB_NAME):
   db_name = DB_NAME
   print("=== Парсер дополнительных программ СПбГУ ===\n")

   print("Шаг 1: Сбор ссылок на программы...")
   urls = collect_course_urls()
   if not urls:
      print("Не найдено ни одной ссылки.")
      return
   print(f"Всего ссылок: {len(urls)}\n")

   conn = get_connection(db_name)
   cursor = conn.cursor()

   cursor.execute("SELECT id FROM organizations WHERE id = %s", (ORGANIZATION_ID,))
   if not cursor.fetchone():
      cursor.execute("INSERT INTO organizations (id, name) VALUES (%s, %s)", (ORGANIZATION_ID, ORGANIZATION_NAME))
      print(f"Создана организация: id={ORGANIZATION_ID}, name={ORGANIZATION_NAME}")
   conn.commit()

   saved = 0
   skipped = 0
   errors = 0

   print("Шаг 2: Обработка страниц курсов...\n")
   for idx, url in enumerate(urls, 1):
      print(f"  [{idx}/{len(urls)}] {url}", end=" ... ", flush=True)
      try:
         resp = requests.get(url, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"ошибка загрузки: {e}")
         errors += 1
         continue

      try:
         course = parse_course_page(resp.text, url)
         if not course["title"]:
               print("нет названия, пропуск")
               skipped += 1
               continue

         department_id = None
         if course["department_name"]:
               dept_id = get_or_create_department(cursor, course["department_name"], ORGANIZATION_ID)
               update_department_contacts(
                  cursor,
                  dept_id,
                  course["department_address"],
                  course["department_phones"],
                  course["department_emails"],
               )
               department_id = dept_id

         db_course = {k: course[k] for k in (
               "organization_id", "title", "price", "format", "course_type",
               "duration", "date", "description", "url", "language", "document",
               "admission_requirements", "schedule", "duration_in_hours"
         )}
         db_course["department_id"] = department_id

         course_id = save_course(cursor, db_course)
         if course_id is None:
               print("дубликат")
               skipped += 1
               conn.commit()
               continue

         conn.commit()
         print(f"OK (id={course_id})")
         saved += 1

      except Exception as e:
         conn.rollback()
         print(f"ошибка при парсинге: {e}")
         errors += 1

      time.sleep(DELAY)

   cursor.close()
   conn.close()

   print(f"\n=== Итог ===")
   print(f"Сохранено:   {saved}")
   print(f"Пропущено:   {skipped}")
   print(f"Ошибок:      {errors}")

if __name__ == "__main__":
   main_spbgu(DB_NAME)