import time
import requests
from bs4 import BeautifulSoup
from db_functions import (
   get_connection,
   save_course,
   get_or_create_specialization,
   get_or_create_department,
   update_department_contacts,
   link_course_specialization,
)

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
BASE_URL = "https://www.hse.ru/edu/dpo/"
PARAMS_BASE = {"onlyActual": "0"}
HEADERS = {"User-Agent": "Mozilla/5.0"}
DB_NAME = "dpo_db"
ORGANIZATION_ID = 1
DELAY = 0.3  


# ---------------------------------------------------------------------------
# Парсинг страницы курса
# ---------------------------------------------------------------------------
def parse_course_page(url: str, html: str) -> dict:
   soup = BeautifulSoup(html, "html.parser")
   course = {
      "organization_id": ORGANIZATION_ID,
      "url": url,
      "title": None,
      "price": None,
      "format": None,
      "course_type": None,
      "duration": "Не указана",
      "description": "Не указано",
      "language": "русский",
      "date": "Не указана",
      "document": None,
      "admission_requirements": "Не указаны",
      "schedule": "Не указан",
      "department_name": None,
      "department_address": None,
      "department_phones": [],
      "department_emails": [],
      "specialization_names": [],
      "department_id": None,
      "duration_in_hours": "Не указана",
   }

   card = soup.find("section", class_="dpo-program-card")
   if not card:
      return course

   # Специализации
   tags_div = card.find("div", class_="dpo-program-card__tags")
   if tags_div:
      for tag in tags_div.find_all("a", class_="dpo-tag"):
         name = tag.get_text(strip=True)
         if name:
               course["specialization_names"].append(name)

   # course_type, подразделение 
   crumbs = card.find("div", class_="dpo-crumbs")
   if crumbs:
      crumb_items = crumbs.find_all("a", class_="dpo-crumb__item")
      # crumb[0] = тип (ПК / ПП)
      if len(crumb_items) >= 1:
         course["course_type"] = crumb_items[0].get_text(strip=True)
      # crumb[1] = кампус/город — используем как запасной адрес
      if len(crumb_items) >= 2:
         course["department_address"] = crumb_items[1].get_text(strip=True)
      # crumb[2] = подразделение
      if len(crumb_items) >= 3:
         course["department_name"] = crumb_items[2].get_text(strip=True)
      else:
         # нет третьего crumb — подразделение = кампус/город
         course["department_name"] = course["department_address"]

   # Название 
   title_tag = card.find("h1", class_="dpo-program-card__title")
   if title_tag:
      # Убираем вложенные теги (логотип GSB и прочее)
      for nested in title_tag.find_all(["div", "a", "img", "svg"]):
         nested.decompose()
      course["title"] = title_tag.get_text(strip=True) or None

   # Описание
   desc_blocks = card.find_all(
      lambda t: t.name in ("p", "div") and "dpo-program-card__desc" in (t.get("class") or [])
   )
   descs = [b.get_text(strip=True) for b in desc_blocks if b.get_text(strip=True)]
   if descs:
      course["description"] = "\n".join(descs)

   # Свойства
   for prop in card.find_all("li", class_="dpo-program-card__property"):
      name_tag = prop.find("p", class_="dpo-program-card__property-name")
      value_tag = prop.find("p", class_="dpo-program-card__property-value")
      if not name_tag or not value_tag:
         continue
      name = name_tag.get_text(strip=True)
      value = value_tag.get_text(strip=True)
      if name == "Стоимость обучения":
         course["price"] = value
      elif name == "Продолжительность":
         course["duration"] = value
      elif name == "Формат обучения":
         course["format"] = value
      elif name == "Документ":
         course["document"] = value
      elif name == "Старт курса":
         course["date"] = value

   # Секция "Формат обучения" 
   format_section = soup.find("section", class_="dpo-format")
   if format_section:
      h2 = format_section.find("h2", class_="dpo-section__title")
      if h2 and "Формат обучения" in h2.get_text():
         for item in format_section.find_all("li", class_="dpo-format__li"):
               term_tag = item.find("p", class_="dpo-format__term")
               val_tag = item.find("p", class_="dpo-format__value")
               if not term_tag or not val_tag:
                  continue
               term = term_tag.get_text(strip=True)
               val = val_tag.get_text(strip=True)
               if term == "Условия приема":
                  course["admission_requirements"] = val
               elif term == "Язык обучения":
                  course["language"] = val
               elif term == "График обучения":
                  course["schedule"] = val
               elif term == "Продолжительность общая в часах":
                  course["duration_in_hours"] = val
                  

   #  контакты 
   contacts_section = soup.find(
      "section",
      class_=lambda c: c and "dpo-contacts" in c.split() and "dpo-section_theme_dark" in c.split()
   )
   if contacts_section:
      # если есть секция берём полные контакты
      contacts_list = contacts_section.find("ul", class_="dpo-contacts__list")
      if contacts_list:
         for item in contacts_list.find_all("li", class_="dpo-contacts__item"):
               caption_tag = item.find("p", class_="dpo-contacts__caption")
               text_tag = item.find("p", class_="dpo-contacts__text")
               if not caption_tag or not text_tag:
                  continue
               caption = caption_tag.get_text(strip=True).lower()
               if "адрес" in caption:
                  course["department_address"] = text_tag.get_text(strip=True)
               elif "телефон" in caption:
                  for a in text_tag.find_all("a", class_="dpo-phone"):
                     phone = a.get_text(strip=True)
                     if phone:
                           course["department_phones"].append(phone)
               elif "почта" in caption:
                  for a in text_tag.find_all("a"):
                     email = a.get_text(strip=True)
                     if email:
                           course["department_emails"].append(email)

   return course


# ---------------------------------------------------------------------------
# Сбор ссылок из каталога 
# ---------------------------------------------------------------------------
def collect_course_urls() -> list:
   urls = []
   page = 1 
   while True:
      params = {**PARAMS_BASE, "page": page}
      print(f"  Каталог, страница {page}...", end=" ", flush=True)
      try:
         resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"\nОшибка запроса: {e}")
         break

      soup = BeautifulSoup(resp.text, "html.parser")
      container = soup.find("div", class_="dpob-cards__list")
      if not container:
         print("нет контейнера — стоп")
         break

      cards = container.find_all("div", class_="dpob-card")
      if not cards:
         print("нет карточек — стоп")
         break

      page_urls = []
      for card in cards:
         a = card.find("a", class_="dpob-card__title-inner")
         if a and a.get("href"):
               page_urls.append(a["href"])

      print(f"найдено: {len(page_urls)}")
      urls.extend(page_urls)
      page += 1
      time.sleep(DELAY)

   return urls


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main_hse(DB_NAME):
   db_name = DB_NAME
   print("=== Парсер ВШЭ ДПО ===\n")

   print("Шаг 1: Собираю ссылки из каталога...")
   course_urls = collect_course_urls()
   print(f"\nВсего ссылок: {len(course_urls)}\n")

   conn = get_connection(db_name)
   cursor = conn.cursor()
   
   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (1, 'ВШЭ') "
      "ON DUPLICATE KEY UPDATE name = name"
   )
   conn.commit()

   saved = 0
   skipped = 0
   errors = 0

   print("Шаг 2: Обрабатываю каждый курс...\n")
   for i, url in enumerate(course_urls, 1):
      print(f"  [{i}/{len(course_urls)}] {url}", end=" ... ", flush=True)

      try:
         resp = requests.get(url, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"ошибка запроса: {e}")
         errors += 1
         continue

      try:
         course = parse_course_page(url, resp.text)
         # Подразделение
         if course["department_name"]:
               dept_id = get_or_create_department(cursor, course["department_name"], ORGANIZATION_ID)
               update_department_contacts(
                  cursor, dept_id,
                  course["department_address"],
                  course["department_phones"],
                  course["department_emails"],
               )
               course["department_id"] = dept_id

         course_id = save_course(cursor, course)

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

      time.sleep(DELAY)

   cursor.close()
   conn.close()

   print(f"\n=== Итог ===")
   print(f"Сохранено:  {saved}")
   print(f"Дубликатов: {skipped}")
   print(f"Ошибок:     {errors}")


if __name__ == "__main__":
   main_hse(DB_NAME)