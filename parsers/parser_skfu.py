import re
import time
import requests
from bs4 import BeautifulSoup

from db_functions import (
   get_connection, 
   get_or_create_department,
   get_or_create_specialization,
   link_course_specialization,
   save_course
)
from utilit import clean_text, truncate_string

# -------------------------------------------------------------------
# НАСТРОЙКИ
# -------------------------------------------------------------------
URL = "https://dpo.ncfu.ru/"
ORGANIZATION_NAME = "СКФУ"
ORGANIZATION_ID = 10
DB_NAME = "buff_dpo_db"          
DELAY = 0.3

# -------------------------------------------------------------------
# ПАРСИНГ ОДНОГО КУРСА
# -------------------------------------------------------------------
def parse_course(card_div, hidden_div):
   course = {
      "title": None,
      "url": None,
      "price": None,
      "format": None,
      "course_type": None,
      "duration": "Не указана",
      "date": None,
      "description": "Не указано",
      "document": None,
      "admission_requirements": "Не указаны",
      "schedule": "Не указан",
      "duration_in_hours": None,
      "department_name": None,
      "specializations": []
   }

   card = card_div.find("div", class_="card")
   if not card:
      return course

   # URL
   a_tag = card.find("a", class_="button")
   if a_tag and a_tag.get("href"):
      course["url"] = a_tag["href"]

   # Заголовок
   title_tag = card.find("p", class_="card__title")
   if title_tag:
      course["title"] = clean_text(title_tag.get_text())

   # Теги (tag tag_inline) – определяем department, course_type, specializations
   for tag in card.find_all("p", class_="tag tag_inline"):
      text = clean_text(tag.get_text())
      if not text:
         continue
      lower = text.lower()
      # Определяем department: если содержит одно из ключевых слов
      if any(kw in lower for kw in ("институт", "факультет", "школа", "кафедра", "филиал")):
         course["department_name"] = f"{ORGANIZATION_NAME} {text}"
      # Определяем course_type
      elif lower in ("повышение квалификации", "профессиональная переподготовка", "дополнительная образовательная программа"):
         course["course_type"] = text
      else:
         # Всё остальное считаем специализацией
         course["specializations"].append(text)

   # Дата старта
   date_val = card.find("p", class_="card__value card__value_color_primary")
   if date_val:
      course["date"] = clean_text(date_val.get_text())

   #  Данные из скрытого блока 
   if hidden_div:
      detail = hidden_div.find("div", class_="js-content-detail")
      if detail:
         #  часы, стоимость 
         for icon in detail.find_all("div", class_="icon-item"):
            img = icon.find("img")
            if not img:
               continue
            src = img.get("src", "")
            info = icon.find("div", class_="icon-item__info-container")
            if not info:
               continue
            title = info.find("p", class_="icon-item__title")
            subtitle = info.find("p", class_="icon-item__subtitle")
            title_text = clean_text(title.get_text()) if title else ""
            sub_text = clean_text(subtitle.get_text()) if subtitle else ""
            if "clock" in src:
               course["duration"] = f"{title_text} {sub_text}".strip()
               if sub_text and "час" in sub_text.lower():
                  course["duration_in_hours"] = title_text
            elif "wallet" in src:
               course["price"] = title_text

         # Описание  
         desc_container = detail.find("div", class_="content__text")
         if desc_container:
            # Удаляем лишние блоки (диплом, списки)
            for bad in desc_container.find_all(["div", "h3"]):
               bad.decompose()
            course["description"] = clean_text(desc_container.get_text())

         # Документ об обучении 
         diplom_card = detail.find("div", class_="diplom-card")
         if diplom_card:
            doc_paragraph = diplom_card.find("p", class_="diplom-card__text")
            if doc_paragraph:
               raw_doc = clean_text(doc_paragraph.get_text())
               if raw_doc:
                  m = re.search(r'(диплом о профессиональной переподготовке|удостоверение о повышении квалификации|свидетельство|сертификат)', raw_doc, re.IGNORECASE)
                  if m:
                     course["document"] = m.group(1).lower()
                  else:
                     course["document"] = truncate_string(raw_doc, 100)
         # Если не нашли, ищем в блоке "Как проходят занятия"
         if not course["document"]:
            for block in detail.find_all("div", class_="content__block"):
               sub = block.find("p", class_="content__subtitle")
               if sub and "Как проходят занятия" in sub.get_text():
                  text_container = block.find("div", class_="content__text-container")
                  if text_container:
                        full_text = clean_text(text_container.get_text())
                        if full_text:
                           m = re.search(r"Документ об обучении:\s*(.+?)(?:\n|$)", full_text, re.IGNORECASE)
                           if m:
                              raw = m.group(1).strip()
                              m2 = re.search(r'(диплом о профессиональной переподготовке|удостоверение о повышении квалификации|свидетельство|сертификат)', raw, re.IGNORECASE)
                              if m2:
                                 course["document"] = m2.group(1).lower()
                              else:
                                 course["document"] = truncate_string(raw, 100)
                  break

         # Для кого 
         for block in detail.find_all("div", class_="content__block"):
            sub = block.find("p", class_="content__subtitle")
            if sub and "Для кого" in sub.get_text():
               text_container = block.find("div", class_="content__text-container")
               if text_container:
                  course["admission_requirements"] = clean_text(text_container.get_text())
               break

         for block in detail.find_all("div", class_="content__block"):
            sub = block.find("p", class_="content__subtitle")
            if sub and "Как проходят занятия" in sub.get_text():
               text_container = block.find("div", class_="content__text-container")
               if text_container:
                  full = clean_text(text_container.get_text())
                  course["schedule"] = full
                  if full:
                     # формат обучения
                     fm = re.search(r"Форма обучения:\s*(.+?)(?:\n|$)", full)
                     if fm:
                        course["format"] = truncate_string(fm.group(1).strip(), 150)
                     # длительность 
                     dur = re.search(r"Срок обучения:\s*(.+?)(?:\n|$)", full)
                     if dur and course["duration"] == "Не указана":
                           course["duration"] = dur.group(1).strip()
                     # Объём в часах
                     hrs = re.search(r"Объём программы:\s*(\d+)\s*час", full)
                     if hrs and not course["duration_in_hours"]:
                        course["duration_in_hours"] = hrs.group(1)
               break

   # Если документ всё ещё None
   if not course["document"] and course["course_type"]:
      if "повышение квалификации" in course["course_type"].lower():
         course["document"] = "удостоверение о повышении квалификации"
      elif "профессиональная переподготовка" in course["course_type"].lower():
         course["document"] = "диплом о профессиональной переподготовке"
      else:
         course["document"] = "сертификат"

   # Обрезаем поля
   course["document"] = truncate_string(course["document"], 100)
   course["format"] = truncate_string(course["format"], 150)
   course["course_type"] = truncate_string(course["course_type"], 100)
   course["duration"] = truncate_string(course["duration"], 100)
   course["duration_in_hours"] = truncate_string(course["duration_in_hours"], 100)
   course["date"] = truncate_string(course["date"], 150)
   course["description"] = truncate_string(course["description"], 65535)  # text
   course["admission_requirements"] = truncate_string(course["admission_requirements"], 65535)
   course["schedule"] = truncate_string(course["schedule"], 255)
   course["title"] = truncate_string(course["title"], 500)
   course["price"] = truncate_string(course["price"], 100)

   return course

# -------------------------------------------------------------------
# ОСНОВНАЯ ФУНКЦИЯ
# -------------------------------------------------------------------
def main_skfu(DB_NAME):
   db_name = DB_NAME
   print("=== Парсер СКФУ ДПО ===\n")
   print(f"Загружаем {URL} ...")
   try:
      resp = requests.get(URL, timeout=30)
      resp.raise_for_status()
   except Exception as e:
      print(f"Ошибка загрузки: {e}")
      return

   soup = BeautifulSoup(resp.text, "html.parser")

   programs_section = soup.find("section", class_="programs", id="detail")
   if not programs_section:
      programs_section = soup.find("section", class_="programs")
   if not programs_section:
      print("Не удалось найти секцию с программами ДПО, парсинг остановлен.")
      return

   cards = programs_section.find_all("div", class_="select-grid__card")
   print(f"Найдено карточек: {len(cards)}\n")

   conn = get_connection(db_name)
   cursor = conn.cursor()

   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (10, 'CКФУ') "
      "ON DUPLICATE KEY UPDATE name = name"
   )
   conn.commit()

   saved = 0
   skipped = 0
   errors = 0

   for idx, card_div in enumerate(cards, 1):
      hidden_div = card_div.find_next_sibling("div", class_="content content_hidden")
      if not hidden_div:
         print(f"[{idx}/{len(cards)}] нет hidden-блока, пропуск")
         skipped += 1
         continue

      course_data = parse_course(card_div, hidden_div)

      if not course_data["title"] or not course_data["url"]:
         print(f"[{idx}/{len(cards)}] {course_data['title'] or 'без названия'} — нет title/url, пропуск")
         skipped += 1
         continue

      print(f"[{idx}/{len(cards)}] {course_data['title']} ({course_data['url']})", end=" ... ")

      try:
         dept_id = None
         if course_data["department_name"]:
               dept_id = get_or_create_department(cursor, course_data["department_name"], ORGANIZATION_ID)

         db_course = {
            "organization_id": ORGANIZATION_ID,
            "title": course_data["title"],
            "price": course_data["price"],
            "format": course_data["format"],
            "course_type": course_data["course_type"],
            "duration": course_data["duration"],
            "date": course_data["date"],
            "description": course_data["description"],
            "url": course_data["url"],
            "language": "русский",
            "document": course_data["document"],
            "admission_requirements": course_data["admission_requirements"],
            "schedule": course_data["schedule"],
            "department_id": dept_id,
            "duration_in_hours": course_data["duration_in_hours"]
         }

         course_id = save_course(cursor, db_course)
         if course_id is None:
            print("дубликат — пропущен")
            skipped += 1
            conn.commit()
            continue

         for spec_name in course_data["specializations"]:
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

   print(f"\n=== ИТОГ ===")
   print(f"Сохранено:  {saved}")
   print(f"Дубликатов: {skipped}")
   print(f"Ошибок:     {errors}")

if __name__ == "__main__":
   main_skfu(DB_NAME)