import re
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
from helpers import clean_text, get_html_with_playwright_selector

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
CATALOG_URL = "https://www.ranepa.ru/catalog-dpo/#page="
BASE_URL = "https://www.ranepa.ru"
HEADERS = {"User-Agent": "Mozilla/5.0"}
ORGANIZATION_ID = 4
DB_NAME = "buff_dpo_db"
DELAY = 0.3

BADGE_TO_COURSE_TYPE = {
   "ПК": "Повышение квалификации",
   "ПП": "Профессиональная переподготовка",
   "ГУ": "Государственное управление",
   "БО": "Бизнес-образование",
}

COURSE_TYPE_TO_DOCUMENT = {
   "Повышение квалификации": "Удостоверение о повышении квалификации",
   "Профессиональная переподготовка": "Диплом о профессиональной переподготовке",
}


# ---------------------------------------------------------------------------
# Парсинг одной карточки из каталога
# ---------------------------------------------------------------------------
def parse_card(li_tag) -> dict:
   """
   Извлекает данные из одной карточки <li class="pp-dpo-program">.
   Возвращает dict с полями: url, title, course_type, specialization_names,
   duration_in_hours, format, date, price.
   """
   data = {
      "url": None,
      "title": None,
      "course_type": None,
      "specialization_names": [],
      "duration_in_hours": None,
      "format": None,
      "date": None,
      "price": None,
   }

   # --- Тип курса (badge) ---
   badge = li_tag.find(
      "p",
      class_=lambda c: c and "pp-dpo-program__badge" in c and "badge--city" not in c,
   )
   if badge:
      badge_text = clean_text(badge.get_text())
      data["course_type"] = BADGE_TO_COURSE_TYPE.get(badge_text, badge_text)

   # --- Специализации (через «•») ---
   tags_p = li_tag.find("p", class_="pp-dpo-program__tags-list")
   if tags_p:
      tags_text = clean_text(tags_p.get_text())
      data["specialization_names"] = [
         s.strip() for s in tags_text.split("•") if s.strip()
      ]

   # --- Название ---
   title_tag = li_tag.find("h2", class_="pp-dpo-program__title")
   if title_tag:
      data["title"] = clean_text(title_tag.get_text())
   else:
      title_tag = li_tag.find("h3", class_="pp-dpo-program__title")
      if title_tag:
         data["title"] = clean_text(title_tag.get_text())

   # --- info-list: часы, формат, дата, цена ---
   for info in li_tag.find_all("li", class_="pp-dpo-program__info"):
      p_tag = info.find("p", class_="pp-dpo-program__info-text")
      text = clean_text(p_tag.get_text()) if p_tag else ""
      if not text:
         continue

      if "ак. ч" in text or "ак.ч" in text:
         data["duration_in_hours"] = text
      elif re.match(r"\d{2}\.\d{2}\.\d{4}", text):
         data["date"] = text
      elif "₽" in text:
         price_str = re.sub(r"[₽\s\u00a0]", "", text)
         data["price"] = price_str if price_str.isdigit() else text
      elif text in (
         "Онлайн", "Офлайн", "Гибрид", "Очно",
         "Заочно", "Очно-заочно", "Дистанционно",
      ):
         data["format"] = text

   # --- URL ---
   link_a = li_tag.find("a", class_="pp-dpo-program__link")
   if link_a:
      href = link_a.get("href", "").strip()
      if href:
         if href.startswith("http"):
               data["url"] = href
         else:
               data["url"] = BASE_URL + "/" + href.lstrip("/")

   return data


# ---------------------------------------------------------------------------
# Пагинация каталога — сбор карточек со всех страниц
# ---------------------------------------------------------------------------
def collect_cards() -> list:
   """
   Обходит все страницы каталога через Playwright.
   Возвращает список dict-карточек (результат parse_card).
   """
   all_cards = []
   page_num = 1

   while True:
      page_url = f"{CATALOG_URL}{page_num}"
      print(f"  Каталог, страница {page_num}...", end=" ", flush=True)

      try:
         html = get_html_with_playwright_selector(page_url, "li.pp-dpo-program")
      except Exception as e:
         print(f"ошибка загрузки: {e}")
         break

      soup = BeautifulSoup(html, "html.parser")
      cards_tags = soup.find_all("li", class_="pp-dpo-program")

      if not cards_tags:
         print("нет карточек — стоп")
         break

      page_cards = [parse_card(li) for li in cards_tags]
      # Отбрасываем карточки без URL и без названия
      page_cards = [c for c in page_cards if c["url"] or c["title"]]

      print(f"найдено: {len(page_cards)}")
      all_cards.extend(page_cards)

      # Если карточек меньше ожидаемого — скорее всего последняя страница
      if len(cards_tags) < 10:
         print("  Мало карточек — последняя страница")
         break

      page_num += 1
      time.sleep(DELAY)

   return all_cards


# ---------------------------------------------------------------------------
# Парсинг страницы курса (дополняет данные из карточки)
# ---------------------------------------------------------------------------
def parse_course_page(url: str, html: str, card_data: dict) -> dict:
   """
   Дополняет card_data данными со страницы курса:
   description, title (h1 если нет из карточки), department, contacts.
   Возвращает полный dict курса.
   """
   soup = BeautifulSoup(html, "html.parser")

   course = {
      "organization_id": ORGANIZATION_ID,
      "url": url,
      "title": card_data.get("title"),
      "price": card_data.get("price"),
      "format": card_data.get("format"),
      "course_type": card_data.get("course_type"),
      "duration": "Не указана",
      "duration_in_hours": card_data.get("duration_in_hours"),
      "description": "Не указано",
      "language": "русский",
      "date": card_data.get("date"),
      "document": None,
      "admission_requirements": "Не указаны",
      "schedule": "Не указан",
      "department_name": None,
      "department_address": None,
      "department_phones": [],
      "department_emails": [],
      "specialization_names": list(card_data.get("specialization_names", [])),
      "department_id": None,
   }

   # Документ по типу курса
   if course["course_type"]:
      course["document"] = COURSE_TYPE_TO_DOCUMENT.get(course["course_type"])

   main_container = soup.find("div", class_="pp-dpo-main__container") or soup

   # --- Город → название подразделения ---
   tag_list = main_container.find("ul", class_="pp-dpo-main__tag-list")
   if tag_list:
      for li in tag_list.find_all("li"):
         p = li.find("p", class_="pp-dpo-main__tag")
         if p and "pp-dpo-main__tag--type" not in " ".join(p.get("class", [])):
               city = clean_text(p.get_text())
               if city:
                  course["department_name"] = f"РАНХиГС {city}"
                  break

   # --- Описание ---
   desc_div = main_container.find("div", class_="pp-dpo-main__description")
   if desc_div:
      # Специализации из details-list (добавляем к тем что из карточки)
      details_ul = desc_div.find("ul", class_="pp-dpo-main__details-list")
      if details_ul:
         for li in details_ul.find_all("li"):
               det = clean_text(li.get_text())
               if det and det not in course["specialization_names"]:
                  course["specialization_names"].append(det)
         details_ul.decompose()  # убираем из дерева, чтобы не попало в description

      # Убираем h1 — title уже есть из карточки
      h1 = desc_div.find("h1")
      if h1:
         # Если title не был получен из карточки — берём отсюда
         if not course["title"]:
               course["title"] = clean_text(h1.get_text())
         h1.decompose()

      parts = [
         clean_text(p.get_text())
         for p in desc_div.find_all("p")
         if clean_text(p.get_text())
      ]
      if parts:
         course["description"] = "\n".join(parts)

   # --- Контакты программы ---
   contacts_div = soup.find("div", class_="pp-dpo-contacts__program")
   if contacts_div:
      dl = contacts_div.find("dl")
      if dl:
         for dt_tag, dd_tag in zip(dl.find_all("dt"), dl.find_all("dd")):
               for a in dd_tag.find_all("a", href=lambda h: h and h.startswith("tel:")):
                  for phone in re.split(r"[;,]\s*", clean_text(a.get_text())):
                     if phone.strip():
                           course["department_phones"].append(phone.strip())
               for a in dd_tag.find_all("a", href=lambda h: h and h.startswith("mailto:")):
                  email = clean_text(a.get_text())
                  if email:
                     course["department_emails"].append(email)

   return course


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main_ranepa(DB_NAME):
   
   db_name = DB_NAME
   print("=== Парсер РАНХиГС ДПO ===\n")

   print("Шаг 1: Собираю карточки из каталога...")
   cards_data = collect_cards()
   print(f"\nВсего карточек: {len(cards_data)}\n")

   conn = get_connection(db_name)
   cursor = conn.cursor()

   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (4, 'РАНХиГС') "
      "ON DUPLICATE KEY UPDATE name = name"
   )
   conn.commit()

   saved = 0
   skipped = 0
   errors = 0

   print("Шаг 2: Обрабатываю страницы курсов...\n")
   for i, card_data in enumerate(cards_data, 1):
      url = card_data.get("url")
      title = card_data.get("title", "—")

      if not url:
         print(f"  [{i}/{len(cards_data)}] {title[:60]} — нет URL, пропуск")
         skipped += 1
         continue

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

         if course["department_name"]:
               dept_id = get_or_create_department(
                  cursor, course["department_name"], ORGANIZATION_ID
               )
               update_department_contacts(
                  cursor, dept_id,
                  course["department_address"],
                  course["department_phones"],
                  course["department_emails"],
               )
               course["department_id"] = dept_id

         db_course = {k: course[k] for k in (
               "organization_id", "title", "price", "format", "course_type",
               "duration", "date",  "description", "url", "language", "document",
               "admission_requirements", "schedule", "department_id", "duration_in_hours",
         )}

         course_id = save_course(cursor, db_course)

         if course_id is None:
               print("дубликат — пропущен")
               skipped += 1
               conn.commit()
               continue

         for spec_name in course["specialization_names"]:
               spec_id = get_or_create_specialization(cursor, spec_name)
               link_course_specialization(cursor, course_id, spec_id)

         conn.commit()
         print(f"OK (id={course_id})")
         saved += 1

      except Exception as e:
         conn.rollback()
         print(f"ошибка: {e}")
         errors += 1

      time.sleep(DELAY)

   cursor.close()
   conn.close()

   print(f"\n=== Итог ===")
   print(f"Сохранено:  {saved}")
   print(f"Дубликатов: {skipped}")
   print(f"Ошибок:     {errors}")


if __name__ == "__main__":
   main_ranepa(DB_NAME)