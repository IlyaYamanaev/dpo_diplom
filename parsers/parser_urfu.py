import asyncio
import random
import time
from db_functions import (
   get_connection,
   save_course,
)
from playwright.async_api import async_playwright

#-----------------------------------------------------------------------
# Настройки
#-----------------------------------------------------------------------
BASE_URL = "https://dpo.urfu.ru/programs"
ORGANIZATION_ID = 13 
DB_NAME = "dpo_db"
DELAY = 0.5

CHECKBOX_LABEL_TEXT = "Только доступные для регистрации"
CARD_SELECTOR = "a.service-content.programs_card--item"
NEXT_BUTTON_SELECTOR = "button:has(mat-icon:has-text('navigate_next'))"

DOCUMENT_BY_TYPE = {
   "Повышение квалификации": "Удостоверение о повышении квалификации",
   "Профессиональная переподготовка": "Диплом о профессиональной переподготовке",
   "Дополнительное образование": "Сертификат",
}


#-----------------------------------------------------------------------
# 1. Обход каталога
#-----------------------------------------------------------------------
async def collect_cards(page) -> list[dict]:
   """
   Проходит все страницы каталога, собирает базовые данные карточек:
   url, title, course_type, duration_in_hours.
   """
   await page.goto(BASE_URL)
   await page.wait_for_selector(CARD_SELECTOR, timeout=10000)

   # Снимаем фильтр "Только доступные для регистрации"
   checkbox = page.locator(f"mat-checkbox:has-text('{CHECKBOX_LABEL_TEXT}') input")
   if await checkbox.count() and await checkbox.is_checked():
      await checkbox.click()
      await page.wait_for_timeout(2000)
      print("Фильтр снят")

   all_cards = []
   page_num = 1

   while True and page_num:
      print(f"  Каталог, страница {page_num}...", end=" ", flush=True)
      await page.wait_for_selector(CARD_SELECTOR, timeout=5000)

      page_cards = []
      for card in await page.query_selector_all(CARD_SELECTOR):
         try:
               href = await card.get_attribute("href")
               if not href:
                  continue

               course_type_elem = await card.query_selector(".programs_card--type")
               course_type = (await course_type_elem.inner_text()).strip() if course_type_elem else ""

               title_elem = await card.query_selector(".programs--title h6")
               title = (await title_elem.inner_text()).strip() if title_elem else ""
               if not title:
                  continue

               duration = ""
               for span in await card.query_selector_all("span.category__item"):
                  text = (await span.inner_text()).strip()
                  if "час" in text.lower():
                     duration = text
                     break
               
               await page.wait_for_timeout(300)


               page_cards.append({
                  "url": f"https://dpo.urfu.ru{href}",
                  "title": title,
                  "course_type": course_type,
                  "duration_in_hours": duration,
               })
         except Exception as e:
               print(f"\n  Ошибка карточки: {e}")

      print(f"найдено: {len(page_cards)}")
      all_cards.extend(page_cards)

      next_btn = page.locator(NEXT_BUTTON_SELECTOR)
      if not await next_btn.count() or not await next_btn.is_visible() or not await next_btn.is_enabled():
         break
      await next_btn.scroll_into_view_if_needed()
      await next_btn.click()
      page_num += 1

   return all_cards


#-----------------------------------------------------------------------
# 2. Парсинг страницы курса
#-----------------------------------------------------------------------
async def parse_course_page(page, course_url: str, card_data: dict) -> dict:
   """
   Переходит на страницу курса и извлекает детальную информацию.
   card_data содержит данные из карточки каталога.
   """
   course_type = card_data.get("course_type", "")

   course = {
      "organization_id": ORGANIZATION_ID,
      "url": course_url,
      "title": card_data.get("title"),
      "course_type": course_type,
      "duration_in_hours": card_data.get("duration_in_hours") or "Не указана",
      "duration": None,
      "date": None,
      "format": None,
      "price": None,
      "description": None,
      "language": "русский",
      "document": DOCUMENT_BY_TYPE.get(course_type),
      "admission_requirements": None,
      "schedule": None,
      "department_id": None,
   }

   try:
      await page.goto(course_url, wait_until="domcontentloaded", timeout=30000)
      await page.wait_for_timeout(2000)

      # Даты
      stream_item = page.locator(".splash__stream .stream__item").first
      if await stream_item.count():
         date_text = (await stream_item.locator(".stream__item--title").inner_text()).strip()
         course["date"] = date_text
         if " - " in date_text:
               start, end = date_text.split(" - ", 1)
               course["duration"] = f"{start.strip()} — {end.strip()}"

      # Формат 
      format_value = ""
      items = page.locator(".program__properties--item")
      count = await items.count()
      for i in range(count):
         item = items.nth(i)
         # подпись в subtitle
         subtitle = item.locator(".program__properties--item--subtitle")
         if await subtitle.count() and "Формат обучения" in (await subtitle.inner_text()):
            title_elem = item.locator(".program__properties--item--title")
            if await title_elem.count():
                  format_value = (await title_elem.inner_text()).strip()
                  break
         # подпись в title
         title_elem = item.locator(".program__properties--item--title")
         if await title_elem.count() and "Формат обучения" in (await title_elem.inner_text()):
            value_elem = item.locator(".program__properties--item--text")
            if await value_elem.count():
                  format_value = (await value_elem.inner_text()).strip()
                  break
      course["format"] = format_value

      # Цена
      price_elem = page.locator(".price-card .new-price-header").first
      if await price_elem.count():
         course["price"] = (await price_elem.inner_text()).strip()

      # Описание
      desc_elem = page.locator(".main__description--text").first
      if await desc_elem.count():
         course["description"] = (await desc_elem.inner_text()).strip()[:500]

   except Exception as e:
      print(f"Ошибка при парсинге страницы {course_url}: {e}")

   return course


#-----------------------------------------------------------------------
# 3. Основная функция
#-----------------------------------------------------------------------
async def main_urfu(db_name: str = DB_NAME):
   print("=== Парсер УРФУ ДПО ===\n")

   conn = get_connection(db_name)
   cursor = conn.cursor()
   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (%s, 'УРФУ') "
      "ON DUPLICATE KEY UPDATE name = name",
      (ORGANIZATION_ID,),
   )
   conn.commit()

   saved = skipped = errors = 0

   async with async_playwright() as p:
      browser = await p.chromium.launch(headless=True)
      page = await browser.new_page()

      print("Шаг 1: Собираю карточки из каталога...")
      cards = await collect_cards(page)
      print(f"Всего курсов: {len(cards)}\n")

      print("Шаг 2: Обрабатываю каждый курс...\n")
      for i, card_data in enumerate(cards, 1):
         print(f"  [{i}/{len(cards)}] {card_data['title']}", end=" ... ", flush=True)
         try:
               course = await parse_course_page(page, card_data["url"], card_data)
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
               print(f"ошибка: {e}")
               errors += 1

         await asyncio.sleep(DELAY + random.uniform(0, 0.2))

      await browser.close()

   cursor.close()
   conn.close()

   print(f"\n=== Итог ===")
   print(f"Сохранено:  {saved}")
   print(f"Дубликатов: {skipped}")
   print(f"Ошибок:     {errors}")

def main_urfu_sync(db_name):
    """Синхронная обёртка для асинхронной функции"""
    return asyncio.run(main_urfu(db_name))

if __name__ == "__main__":
   main_urfu_sync(DB_NAME)
