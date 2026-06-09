import asyncio
import random
import requests
from bs4 import BeautifulSoup
from db_functions import (
   get_connection,
   save_course,
)
from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
BASE_URL = "https://skills.tsu.ru/catalog/"
ORGANIZATION_ID = 14
DB_NAME = "dpo_db"
HEADERS = {
   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

DOCUMENT_BY_TYPE = {
   "ПОВЫШЕНИЕ КВАЛИФИКАЦИИ": "Удостоверение о повышении квалификации",
   "ПРОФЕССИОНАЛЬНАЯ ПЕРЕПОДГОТОВКА": "Диплом о профессиональной переподготовке",
   "Программа для школьников": "Сертификат",
}

# ---------------------------------------------------------------------------
# 1. Обход каталога
# ---------------------------------------------------------------------------
async def collect_cards(page) -> list[dict]:
   """
   Загружает каталог полностью (жмёт все кнопки 'Загрузить ещё'),
   возвращает список dict с url и базовыми данными карточек.
   """
   await page.goto(BASE_URL)
   await page.wait_for_selector(".catalog__item, .related__item", timeout=10000)

   # Жмём все кнопки "Загрузить ещё" по всем контейнерам
   for container in await page.query_selector_all(".wrap_load_more"):
      while True:
         button = await container.query_selector(".btn:has-text('Загрузить ещё')")
         if not button or not await button.is_visible():
               break
         current_count = len(await page.query_selector_all(".catalog__item, .related__item"))
         await button.scroll_into_view_if_needed()
         await button.click()
         try:
               await page.wait_for_function(
                  f"() => document.querySelectorAll('.catalog__item, .related__item').length > {current_count}",
                  timeout=10000,
               )
         except Exception:
               pass
         await asyncio.sleep(1)

   cards_data = []
   for card in await page.query_selector_all(".catalog__item, .related__item"):
      try:
         link_elem = await card.query_selector(".title-2 a, .related__block a")
         if not link_elem:
               continue
         href = await link_elem.get_attribute("href")
         if not href:
               continue
         url = f"https://skills.tsu.ru{href}" if href.startswith("/") else href
         title = (await link_elem.inner_text()).strip()

         type_elem = await card.query_selector(".catalog__subtitle, .related__subtitle")
         course_type = (await type_elem.inner_text()).strip() if type_elem else ""

         comment_ps = await card.query_selector_all(".catalog__comment p, .related__bottom p")
         duration = (await comment_ps[0].inner_text()).strip() if len(comment_ps) > 0 else ""
         date = (await comment_ps[1].inner_text()).strip() if len(comment_ps) > 1 else ""

         if title:
               cards_data.append({
                  "url": url,
                  "title": title,
                  "course_type": course_type,
                  "duration": duration,
                  "date": date,
               })
      except Exception as e:
         print(f"  Ошибка карточки: {e}")

   print(f"Всего карточек: {len(cards_data)}")
   return cards_data


# ---------------------------------------------------------------------------
# 2. Парсинг страницы курса
# ---------------------------------------------------------------------------
def parse_course_page(url: str, html: str, card_data: dict) -> dict:
   """
   Извлекает детальную информацию со страницы курса.
   card_data содержит данные из карточки каталога.
   """
   soup = BeautifulSoup(html, "html.parser")

   course = {
      "organization_id": ORGANIZATION_ID,
      "url": url,
      "title": card_data.get("title"),
      "course_type": card_data.get("course_type"),
      "duration": card_data.get("duration"),
      "date": card_data.get("date"),
      "language": "русский",
      "description": None,
      "duration_in_hours": None,
      "price": None,
      "format": None,
      "document": DOCUMENT_BY_TYPE.get(card_data.get("course_type")),
      "admission_requirements": None,
      "schedule": None,
      "department_id": None,
   }

   # ---- Описание ----
   about_section = soup.find("section", class_="about--course")
   if about_section:
      about_text_div = about_section.find("div", class_="about__text")
      if about_text_div:
         paragraphs = about_text_div.find_all("p")
         course["description"] = "\n\n".join(
               p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
         )

   # ---- Длительность в часах ----
   program_section = soup.find("section", class_="about--faq")
   if program_section:
      about_list = program_section.find("ul", class_="about__list--course")
      if about_list:
         for item in about_list.find_all("li", class_="about__item"):
               value_elem = item.find("p", class_="about__value")
               cur_elem = item.find("p", class_="about__cur")
               if value_elem and cur_elem and "час" in cur_elem.get_text():
                  course["duration_in_hours"] = value_elem.get_text(strip=True)
                  break

   # ---- Цена ----
   price_section = soup.find("section", class_="price")
   if price_section:
      price_new = price_section.find("p", class_="price__new")
      if price_new:
         course["price"] = price_new.get_text(strip=True)

   return course


# ---------------------------------------------------------------------------
# 3. Основная функция
# ---------------------------------------------------------------------------
async def main_tsu(db_name: str = DB_NAME):
   print("=== Парсер ТГУ ДПО ===\n")

   conn = get_connection(db_name)
   cursor = conn.cursor()
   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (%s, 'ТГУ') "
      "ON DUPLICATE KEY UPDATE name = name",
      (ORGANIZATION_ID,),
   )
   conn.commit()

   saved = skipped = errors = 0

   async with async_playwright() as p:
      browser = await p.chromium.launch(headless=False)
      page = await browser.new_page()

      print("Шаг 1: Собираю карточки из каталога...")
      cards = await collect_cards(page)
      print(f"Всего курсов: {len(cards)}\n")

      await browser.close()

   session = requests.Session()
   session.headers.update(HEADERS)

   print("Шаг 2: Обрабатываю каждый курс...\n")
   for i, card_data in enumerate(cards, 1):
      url = card_data["url"]
      print(f"  [{i}/{len(cards)}] {card_data['title']}", end=" ... ", flush=True)

      try:
         resp = session.get(url, timeout=15)
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
         else:
               conn.commit()
               print(f"OK (id={course_id})")
               saved += 1

      except Exception as e:
         conn.rollback()
         print(f"ошибка парсинга: {e}")
         errors += 1

      await asyncio.sleep(0.4 + random.uniform(0, 0.2))

   cursor.close()
   conn.close()

   print(f"\n=== Итог ===")
   print(f"Сохранено:  {saved}")
   print(f"Дубликатов: {skipped}")
   print(f"Ошибок:     {errors}")


def main_tsu_sync(db_name):
    """Синхронная обёртка для асинхронной функции"""
    return asyncio.run(main_tsu(db_name))


if __name__ == "__main__":
   main_tsu_sync(DB_NAME)