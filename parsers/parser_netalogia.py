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
DB_NAME = "buff_dpo_db"
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

   if not card_data.get("price_free"):
      price_str = _extract_price(soup)
      if price_str:
         course["price"] = price_str
   

   return course


      
def _extract_price(soup: BeautifulSoup) -> str | None:
   """Пытается извлечь цену из блока тарифов."""
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

   return None


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main_netalogia(DB_NAME):
   db_name = DB_NAME
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

   conn = get_connection(db_name)
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
   main_netalogia(DB_NAME)