import re
import time
import requests
from bs4 import BeautifulSoup
from db_functions import (
   get_connection,
   save_course,
)
from helpers import clean_text

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
NAVIGATION_URL = "https://netology.ru/navigation"
HEADERS = {"User-Agent": "Mozilla/5.0"}
DB_NAME = "dpo_db"
ORGANIZATION_ID = 3
DELAY = 0.2


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------



def parse_price(text: str) -> str | None:
   """
   Из строки вида 'или 80\u00a0300\u00a0₽' или '103\u00a0200'
   возвращает числовую строку без пробелов и символа ₽.
   """
   if not text:
      return None
   digits = re.sub(r"[^\d]", "", text)
   return digits if digits else None


# ---------------------------------------------------------------------------
# Сбор карточек из каталога /navigation
# ---------------------------------------------------------------------------
def collect_cards(soup: BeautifulSoup) -> list[dict]:
   """
   Находит все карточки программ на странице /navigation.
   Возвращает список dict: {url, course_type, duration, price_free}
   """
   cards_data = []

   # Путь: .styles_container__dX63N > .styles_root__2bQ3Y > .styles_programsList__i81MP
   programs_list = soup.find("div", class_=re.compile(r"styles_programsList"))
   if not programs_list:
      # Попробуем найти сразу карточки по всей странице
      programs_list = soup

   cards = programs_list.find_all(
      "div", class_=re.compile(r"programCard_newCatalogExperimentRoot")
   )
   if not cards:
      # Более широкий поиск
      cards = soup.find_all("div", class_=re.compile(r"programCard_newCatalog"))

   for card in cards:
      data = {
         "url": None,
         "course_type": None,
         "duration": None,
         "price_free": False,
      }

      # URL — ищем любую ссылку внутри карточки
      a_tag = card.find("a", href=True)
      if a_tag:
         href = a_tag.get("href", "")
         if href.startswith("/"):
               href = "https://netology.ru" + href
         data["url"] = href.split("?")[0].split("#")[0]  # убираем query/fragment

      # course_type и признак бесплатности — из badge
      badges = card.find_all("div", class_=re.compile(r"programCard_newCatalogBadge"))
      for badge in badges:
         text = badge.get_text(strip=True)
         if text.lower() == "бесплатно":
               data["price_free"] = True
         elif text:
               data["course_type"] = text

      # duration
      duration_tag = card.find("div", class_=re.compile(r"programCard_newCatalogDuration"))
      if duration_tag:
         data["duration"] = duration_tag.get_text(strip=True) or None

      if data["url"]:
         cards_data.append(data)

   return cards_data


# ---------------------------------------------------------------------------
# Парсинг страницы курса
# ---------------------------------------------------------------------------
def parse_course_page(url: str, html: str, card_data: dict) -> dict:
   soup = BeautifulSoup(html, "html.parser")

   course = {
      "organization_id": ORGANIZATION_ID,
      "url": url,
      "title": None,
      "price": "0" if card_data.get("price_free") else None,
      "format": None,
      "course_type": card_data.get("course_type"),
      "duration": card_data.get("duration"),
      "duration_in_hours": "Не указана",
      "description": "Не указано",
      "language": "русский",
      "document": None,
      "date": "Не указана",
      "admission_requirements": "Не указаны",
      "schedule": "Не указан",
      "department_id": None,
   }

   # -----------------------------------------------------------------------
   # Блок coursePresentationUpd_row
   # -----------------------------------------------------------------------
   
   # row = soup.find("div", class_=re.compile(r"coursePresentationUpd_row"))
   # if row:
   # Заголовок
   h1 = soup.find("h1", attrs={"name": "title"})
   if not h1:
      h1 = soup.find("h1", class_=re.compile(r"coursePresentationUpd_title"))
   if h1:
      course["title"] = clean_text(h1)

   # Описание: собираем все p.presentationDescription_text
   desc_tags = soup.find_all("p", class_=re.compile(r"presentationDescription_text"))
   if desc_tags:
      texts = []
      for p in desc_tags:
            t = clean_text(p)
            if t:
               texts.append(t)
      if texts:
            course["description"] = "\n".join(texts)
               
               
               

   # -----------------------------------------------------------------------
   # Блок stats (дата, формат, уровень/требования, документ)
   # -----------------------------------------------------------------------
   
   # stats_block = soup.find(
   #    "div", class_=re.compile(r"stats_root__VXIIB")
   # )
   
   # Список возможных классов/паттернов для поиска stats блока
   stats_patterns = [
      r"stats_root__VXIIB",
      r"stats_root__IPQhX"
   ]

   stats_block = None
   for pattern in stats_patterns:
      stats_block = soup.find("div", class_=re.compile(pattern))
      if stats_block:
         break
      
      
   if stats_block:
      for stat in stats_block.find_all("div", class_=re.compile(r"stats_stat__")):
         title_tag = stat.find("p", class_=re.compile(r"stats_statTitle"))
         value_tag = stat.find("p", class_=re.compile(r"stats_statValue"))

         if not title_tag or not value_tag:
               continue

         title_text = clean_text(title_tag) or ""
         value_text = clean_text(value_tag)

         if "Когда" in title_text:
               # date: берём атрибут name="customDate" если есть, иначе текст
               date_p = stat.find("p", attrs={"name": "customDate"})
               if date_p:
                  course["date"] = clean_text(date_p)
               else:
                  course["date"] = value_text

         elif "Формат" in title_text:
               course["format"] = value_text

         elif "Уровень" in title_text:
               course["admission_requirements"] = value_text or "Не указаны"

         elif "Документ" in title_text:
               course["document"] = value_text

   # -----------------------------------------------------------------------
   # Цена: блок bemjbnt bhhdltp o136jz4i
   # Логика: найти styles_root__NoDqQ → первый styles_root__BN7U1
   #   → styles_innerContent__MFvW4 → styles_root__B5IdH
   #   → styles_price__ylvL2 (или styles_currentPrice__vR_wT / styles_free__)
   # -----------------------------------------------------------------------
   if not card_data.get("price_free"):
      price_str = _extract_price(soup)
      if price_str:
         course["price"] = price_str

   return course


def _extract_price(soup: BeautifulSoup) -> str | None:
   """
   Пытается извлечь цену из блока тарифов.
   Приоритет: styles_price__ylvL2 → styles_currentPrice__vR_wT → styles_free__
   Берётся первое найденное значение.
   """
   # Вариант 1: через styles_root__NoDqQ
   nodo = soup.find("div", class_=re.compile(r"styles_root__NoDqQ"))
   search_root = nodo if nodo else soup

   # Первый BN7U1
   bn7u1 = search_root.find("div", class_=re.compile(r"styles_root__BN7U1"))

   # innerContent → B5IdH
   if bn7u1:
      inner = bn7u1.find("div", class_=re.compile(r"styles_innerContent__MFvW4"))
      b5idh = inner.find("div", class_=re.compile(r"styles_root__B5IdH")) if inner else None
      price_search = b5idh or inner or bn7u1
   else:
      price_search = search_root

   if price_search is None:
      price_search = soup

   # Бесплатно
   free_tag = price_search.find("p", class_=re.compile(r"styles_free__"))
   if free_tag and "бесплатно" in free_tag.get_text(strip=True).lower():
      return "0"

   # или X ₽
   price_tag = price_search.find("div", class_=re.compile(r"styles_price__ylvL2"))
   if price_tag:
      return parse_price(price_tag.get_text())

   # currentPrice (X ₽)
   cur_tag = price_search.find("div", class_=re.compile(r"styles_currentPrice__vR_wT"))
   if cur_tag:
      return parse_price(cur_tag.get_text())

   # Широкий поиск по всей странице
   price_tag = soup.find("div", class_=re.compile(r"styles_price__ylvL2"))
   if price_tag:
      return parse_price(price_tag.get_text())

   cur_tag = soup.find("div", class_=re.compile(r"styles_currentPrice__vR_wT"))
   if cur_tag:
      return parse_price(cur_tag.get_text())
   
      # ↓↓↓ ДОБАВИТЬ ЭТОТ БЛОК ↓↓↓
   # Для бакалавриата и подобных: ищем creditPrice или текст с ценой
   # credit_tag = soup.find("div", class_=re.compile(r"styles_creditPrice__ez4sv"))
   # if credit_tag:
   #    price_text = credit_tag.get_text()
   #    price = parse_price(price_text)
   #    if price:
   #       return price
   
   # body_text = soup.get_text()
   # match = re.search(r'(\d[\d\s]*\d)\s*₽', body_text)
   # if match:
   #    price = parse_price(match.group(1))
   #    # Отсекаем слишком маленькие числа (не цены)
   #    if price and int(price) > 10000:
   #       return price
   # # ↑↑↑ КОНЕЦ ДОБАВЛЕННОГО БЛОКА ↑↑↑

   return None


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main():
   print("=== Парсер Нетология ===\n")

   print("Шаг 1: Загружаю страницу каталога...")
   try:
      resp = requests.get(NAVIGATION_URL, headers=HEADERS, timeout=30)
      resp.raise_for_status()
   except requests.RequestException as e:
      print(f"Ошибка запроса каталога: {e}")
      return

   soup_nav = BeautifulSoup(resp.text, "html.parser")
   cards_data = collect_cards(soup_nav)
   print(f"Найдено курсов в каталоге: {len(cards_data)}\n")

   conn = get_connection(DB_NAME)
   cursor = conn.cursor()

   # Убедимся что организация Нетология существует
   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (3, 'Нетология') "
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

      time.sleep(DELAY)

   cursor.close()
   conn.close()

   print(f"\n=== Итог ===")
   print(f"Сохранено:  {saved}")
   print(f"Дубликатов: {skipped}")
   print(f"Ошибок:     {errors}")


if __name__ == "__main__":
   main()
    
    
# import re
# import time
# import requests
# from bs4 import BeautifulSoup
# from db import (
#    get_connection,
#    save_course,
# )

# # ---------------------------------------------------------------------------
# # Настройки
# # ---------------------------------------------------------------------------
# BASE_URL = "https://netology.ru/navigation"
# HEADERS = {
#    "User-Agent": "Mozilla/5.0"
# }
# ORGANIZATION_ID = 3
# DELAY = 0.3
# DB_NAME = "buff_dpo_db"



# # ---------------------------------------------------------------------------
# # Утилиты
# # ---------------------------------------------------------------------------
# def clean_text(text):
#    if not text:
#       return None

#    text = text.replace("\xa0", " ")
#    text = re.sub(r"\s+", " ", text)
#    return text.strip()


# def extract_price(text):
#    if not text:
#       return None

#    text = clean_text(text).lower()

#    if "бесплат" in text:
#       return "0"

#    digits = re.findall(r"\d+", text.replace(" ", ""))
#    if digits:
#       return "".join(digits)

#    return None


# # ---------------------------------------------------------------------------
# # Каталог
# # ---------------------------------------------------------------------------
# def parse_catalog(html):
#    soup = BeautifulSoup(html, "html.parser")

#    root = soup.find(
#       "div",
#       class_="styles_programsList__i81MP"
#    )

#    if not root:
#       return []

#    cards = root.find_all(
#       "div",
#       class_="programCard_newCatalogExperimentRoot__aMYZX"
#    )

#    result = []

#    for card in cards:
#       course = {
#          "organization_id": ORGANIZATION_ID,
#          "title": None,
#          "price": None,
#          "format": None,
#          "duration": None,
#          "date": None,
#          "description": None,
#          "url": None,
#          "language": "русский",
#          "document": None,
#          "department_id": None,
#          "course_type": None,
#          "admission_requirements": "Не указаны",
#          "schedule": "Не указан",
#          "duration_in_hours": "Указан не явно",
#       }

#       # URL
#       a = card.find("a", href=True)
#       if a:
#          href = a.get("href")

#          if href.startswith("/"):
#                href = "https://netology.ru" + href

#          course["url"] = href

#       # Тип курса
#       badges = card.find_all(
#          "div",
#          class_="programCard_newCatalogBadge__4LBHb"
#       )

#       for badge in badges:
#          badge_text = clean_text(badge.get_text())

#          if not badge_text:
#                continue

#          if badge_text.lower() == "бесплатно":
#                course["price"] = "0"
#          else:
#                course["course_type"] = badge_text

#       # Длительность
#       duration = card.find(
#          "div",
#          class_="programCard_newCatalogDuration__oEdNP"
#       )

#       if duration:
#          course["duration"] = clean_text(duration.get_text())

#       if course["url"]:
#          result.append(course)

#    return result


# # ---------------------------------------------------------------------------
# # Парсинг страницы курса
# # ---------------------------------------------------------------------------
# def parse_course_page(course, html):
#    soup = BeautifulSoup(html, "html.parser")

#    # -----------------------------------------------------------------------
#    # Главный блок
#    # -----------------------------------------------------------------------
#    presentation = soup.find(
#       "div",
#       class_="coursePresentationUpd_row__4HRb6"
#    )

#    if presentation:

#       # TITLE
#       h1 = presentation.find(
#          "h1",
#          class_="coursePresentationUpd_title__AtZkq"
#       )

#       if h1:
#          course["title"] = clean_text(h1.get_text(" ", strip=True))

#       # DESCRIPTION
#       desc_root = presentation.find(
#          "div",
#          class_=lambda c: c and "presentationDescription_root__" in c
#       )

#       if desc_root:
#          texts = []

#          paragraphs = desc_root.find_all(
#                "p",
#                class_="presentationDescription_text__bgskR"
#          )

#          for p in paragraphs:
#                text = clean_text(p.get_text(" ", strip=True))

#                if text and text not in texts:
#                   texts.append(text)

#          if texts:
#                course["description"] = "\n".join(texts)

#    # -----------------------------------------------------------------------
#    # STATS
#    # -----------------------------------------------------------------------
#    # stats_root = soup.find(
#    #    "div",
#    #    class_=lambda c: c and "stats_root__VXIIB" in c
#    # )
#    stats_root = soup.find(
#       "div",
#       class_=lambda c: c and "stats_root__" in c and "stats_black__" in c
#    )

#    if stats_root:
#       stats = stats_root.find_all(
#          "div",
#          class_="stats_stat__Ekzjy"
#       )

#       for stat in stats:

#          title = stat.find(
#                "p",
#                class_=lambda c: c and "stats_statTitle__QmBeU" in c
#          )

#          value = stat.find(
#                "p",
#                class_=lambda c: c and "stats_statValue__Ha8NU" in c
#          )

#          if not title or not value:
#                continue

#          title_text = clean_text(title.get_text(" ", strip=True))
#          value_text = clean_text(value.get_text(" ", strip=True))

#          if not title_text or not value_text:
#                continue

#          title_lower = title_text.lower()

#          if "когда" in title_lower:
#                course["date"] = value_text

#          elif "формат" in title_lower:
#                course["format"] = value_text

#          elif "уровень" in title_lower:
#                course["admission_requirements"] = value_text

#          elif "документ" in title_lower:
#                course["document"] = value_text

#    # -----------------------------------------------------------------------
#    # PRICE
#    # -----------------------------------------------------------------------
#    if not course["price"]:

#       # Бесплатно
#       free = soup.find(
#          "p",
#          class_="styles_free__ByWwb"
#       )

#       if free:
#          course["price"] = "0"

#       # current price
#       if not course["price"]:
#          current_prices = soup.find_all(
#                "div",
#                class_="styles_currentPrice__vR_wT"
#          )

#          for price_block in current_prices:
#                text = clean_text(price_block.get_text(" ", strip=True))
#                price = extract_price(text)

#                if price:
#                   course["price"] = price
#                   break

#       # old/simple price
#       if not course["price"]:
#          prices = soup.find_all(
#                "div",
#                class_="styles_price__ylvL2"
#          )

#          for price_block in prices:
#                text = clean_text(price_block.get_text(" ", strip=True))
#                price = extract_price(text)

#                if price:
#                   course["price"] = price
#                   break

#    return course


# # ---------------------------------------------------------------------------
# # MAIN
# # ---------------------------------------------------------------------------
# def main():
#    print("=== Парсер Нетологии ===\n")

#    conn = get_connection(DB_NAME)
#    cursor = conn.cursor()

#    # -----------------------------------------------------------------------
#    # ORGANIZATION
#    # -----------------------------------------------------------------------
#    cursor.execute("""
#       INSERT INTO organizations (id, name)
#       VALUES (3, 'Нетология')
#       ON DUPLICATE KEY UPDATE name = name
#    """)

#    conn.commit()

#    # -----------------------------------------------------------------------
#    # Каталог
#    # -----------------------------------------------------------------------
#    print("Шаг 1: Загружаю каталог...\n")

#    resp = requests.get(BASE_URL, headers=HEADERS, timeout=60)
#    resp.raise_for_status()

#    courses = parse_catalog(resp.text)

#    print(f"Найдено курсов: {len(courses)}\n")

#    # -----------------------------------------------------------------------
#    # Курсы
#    # -----------------------------------------------------------------------
#    saved = 0
#    skipped = 0
#    errors = 0

#    print("Шаг 2: Обрабатываю курсы...\n")

#    for i, course in enumerate(courses, 1):

#       print(f"[{i}/{len(courses)}] {course['url']} ... ", end="", flush=True)

#       try:
#          resp = requests.get(
#                course["url"],
#                headers=HEADERS,
#                timeout=60
#          )

#          resp.raise_for_status()

#          course = parse_course_page(course, resp.text)

#          course_id = save_course(cursor, course)

#          if course_id is None:
#                conn.commit()
#                skipped += 1
#                print("дубликат")
#                continue

#          conn.commit()

#          saved += 1
#          print(f"OK ({course_id})")

#       except Exception as e:
#          conn.rollback()
#          errors += 1
#          print(f"ошибка: {e}")

#       time.sleep(DELAY)

#    cursor.close()
#    conn.close()

#    print("\n=== ИТОГ ===")
#    print(f"Сохранено:  {saved}")
#    print(f"Дубликатов: {skipped}")
#    print(f"Ошибок:     {errors}")


# if __name__ == "__main__":
#    main()