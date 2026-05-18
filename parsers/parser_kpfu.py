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
BASE_URL = "https://dpo.kpfu.ru/course/"
HEADERS = {"User-Agent": "Mozilla/5.0"}
ORGANIZATION_ID = 2
DELAY = 0.3
DB_NAME = "buff_dpo_db"


# ---------------------------------------------------------------------------
# Сбор данных с карточки в каталоге
# ---------------------------------------------------------------------------
def parse_catalog_card(card) -> dict:
   """
   Из карточки каталога берём: url, course_type, duration,
   specialization_name (direction). Остальное — со страницы курса.
   """
   data = {
      "url": None,
      "course_type": None,
      "duration": None,
      "specialization_name": None,
   }

   # URL — из заголовка карточки
   title_a = card.find("a", class_="course-card__title")
   if title_a:
      data["url"] = title_a.get("href")

   header = card.find("div", class_="course-card__header")
   if header:
      # Специализация / направление
      direction_tag = header.find("p", class_="course-card__direction")
      if direction_tag:
         data["specialization_name"] = direction_tag.get_text(strip=True) or None

      # Тип курса
      type_tag = header.find("p", class_="course-card__type")
      if type_tag:
         # Убираем span с иконкой, берём только текст
         for span in type_tag.find_all("span"):
               span.decompose()
         data["course_type"] = type_tag.get_text(strip=True) or None

   # Срок освоения — ищем p.course-card__dl где dt = "Сроки освоения:"
   body = card.find("div", class_="course-card__body")
   if body:
      for dl in body.find_all("p", class_="course-card__dl"):
         dt = dl.find("span", class_="course-card__dt")
         dd = dl.find("span", class_="course-card__dd")
         if dt and dd and "Сроки освоения" in dt.get_text():
               data["duration"] = dd.get_text(strip=True) or None

   return data


# ---------------------------------------------------------------------------
# Парсинг страницы курса
# ---------------------------------------------------------------------------
def parse_course_page(url: str, html: str, card_data: dict) -> dict:
   soup = BeautifulSoup(html, "html.parser")

   course = {
      "organization_id": ORGANIZATION_ID,
      "url": url,
      "title": None,
      "price": None,
      "format": "Очный",
      "course_type": card_data.get("course_type"),
      "duration": card_data.get("duration"),
      "duration_in_hours": "Не указана",
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
   }

   # Специализация из карточки каталога (если есть)
   if card_data.get("specialization_name"):
      course["specialization_names"].append(card_data["specialization_name"])

   # -----------------------------------------------------------------------
   # Шапка курса: class="page__heading page__heading--cover"
   # -----------------------------------------------------------------------
   heading = soup.find("header", class_="page__heading")
   if not heading:
      heading = soup.find("div", class_="page__heading")

   if heading:
      course_head = heading.find("div", class_="course-head")
      if course_head:

         # Название
         title_tag = course_head.find("h1", class_="course-head__title")
         if title_tag:
               course["title"] = title_tag.get_text(strip=True) or None

         # Специализация со страницы курса 
         type_tag = course_head.find("p", class_="course-head__type")
         if type_tag:
               spec_name = type_tag.get_text(strip=True)
               if spec_name and spec_name not in course["specialization_names"]:
                  course["specialization_names"].append(spec_name)

         # Параметры: document, duration_in_hours, price
         for item in course_head.find_all("p", class_="course-parametrs__item"):
               bold = item.find("span", class_="course-parametrs__bold")
               plain = item.find("span", class_="course-parametrs__plain")
               if not bold:
                  continue
               bold_text = bold.get_text(strip=True)
               plain_text = plain.get_text(strip=True) if plain else ""

               if bold_text == "Документ":
                  course["document"] = plain_text or None
               elif "Стоимость обучения" in plain_text:
                  course["price"] = bold_text or None
               elif "часов" in bold_text:
                  course["duration_in_hours"] = bold_text or None

   # -----------------------------------------------------------------------
   # Описание: section.course-description
   # -----------------------------------------------------------------------
   desc_section = soup.find("section", class_="course-description")
   if desc_section:
      paragraphs = desc_section.find_all("p")
      texts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
      if texts:
         course["description"] = "\n".join(texts)

   # -----------------------------------------------------------------------
   # Контакты: section > h2 "Контакты центра"
   # -----------------------------------------------------------------------
   for section in soup.find_all("section", class_="page__section"):
      h2 = section.find("h2")
      if not h2 or "Контакты центра" not in h2.get_text():
         continue

      contacts_div = section.find("div", class_="course-contacts")
      if not contacts_div:
         continue

      # Название подразделения
      headname = contacts_div.find("p", class_="course-contacts__headname")
      if headname:
         course["department_name"] = headname.get_text(strip=True) or None

      # Секции внутри контактов
      for contact_section in contacts_div.find_all("div", class_="course-contacts__section"):
         section_title = contact_section.find("h3", class_="course-contacts__title")
         if not section_title:
               continue
         title_text = section_title.get_text(strip=True)

         if "Способы связи" in title_text:
               for li in contact_section.find_all("li"):
                  a = li.find("a")
                  if not a:
                     continue
                  href = a.get("href", "")
                  text = a.get_text(strip=True)
                  if href.startswith("tel:"):
                     if text:
                           course["department_phones"].append(text)
                  elif href.startswith("mailto:"):
                     if text:
                           course["department_emails"].append(text)

         elif "Адрес" in title_text:
               for li in contact_section.find_all("li"):
                  span = li.find("span", class_="icon-text")
                  if span:
                     # убираем вложенный span с иконкой
                     for inner in span.find_all("span"):
                           inner.decompose()
                     addr = span.get_text(strip=True)
                     if addr:
                           course["department_address"] = addr
                           break
      break  # нашли секцию контактов — дальше не ищем

   return course


# ---------------------------------------------------------------------------
# Сбор карточек из каталога (все страницы пагинации)
# ---------------------------------------------------------------------------
def collect_cards() -> list:
   """
   Возвращает список dict: {"url": ..., "course_type": ...,
   "duration": ..., "specialization_name": ...}
   Пагинация: https://dpo.kpfu.ru/course/page/N/
   """
   all_cards = []
   page = 1

   while True:
      if page == 1:
         url = BASE_URL
      else:
         url = f"{BASE_URL}page/{page}/"

      print(f"  Каталог, страница {page}...", end=" ", flush=True)
      try:
         resp = requests.get(url, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"\nОшибка запроса: {e}")
         break

      soup = BeautifulSoup(resp.text, "html.parser")

      catalog = soup.find("div", class_="catalog__list")
      if not catalog:
         print("нет каталога — стоп")
         break

      cards = catalog.find_all("div", class_="course-card")
      if not cards:
         print("нет карточек — стоп")
         break

      page_data = []
      for card in cards:
         card_data = parse_catalog_card(card)
         if card_data["url"]:
               page_data.append(card_data)

      print(f"найдено: {len(page_data)}")
      all_cards.extend(page_data)

      # Проверяем наличие кнопки "следующая страница"
      next_btn = soup.find("li", class_="pagination__item--next")
      if next_btn:
         next_a = next_btn.find("a")
         if not next_a:
               break  # кнопка есть но недоступна
      else:
         break

      page += 1
      time.sleep(DELAY)

   return all_cards


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main():
   print("=== Парсер КФУ ДПО ===\n")

   print("Шаг 1: Собираю карточки из каталога...")
   cards_data = collect_cards()
   print(f"\nВсего курсов: {len(cards_data)}\n")

   conn = get_connection(DB_NAME)
   cursor = conn.cursor()

   # Убедимся что организация КФУ существует
   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (2, 'КФУ') "
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