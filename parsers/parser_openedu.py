import asyncio
import csv
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

async def collect_links_and_basic_info():
   """Собирает ссылки на курсы, названия, организации, статус с главной страницы"""
   async with async_playwright() as p:
      browser = await p.chromium.launch(headless=False)  # можно headless=True, но для отладки оставим False
      page = await browser.new_page()
      await page.goto("https://openedu.ru/course/?status=all")
      
      # Ждём, пока появятся первые карточки
      await page.wait_for_selector("li.list-module__IWPZ_q__item", timeout=10000)
      
      # Прокручиваем вниз, чтобы кнопка точно появилась
      await page.evaluate("window.scrollBy(0, 800)")
      await asyncio.sleep(1)
      
      # Ищем кнопку "Загрузить ещё" по тексту или классу
      load_button = None
      for attempt in range(3):  # несколько попыток
         load_button = await page.query_selector("button:has-text('Загрузить ещё')")
         if load_button:
               break
         # Если не нашли, возможно, нужно ещё прокрутить
         await page.evaluate("window.scrollBy(0, 500)")
         await asyncio.sleep(1)
      
      if not load_button:
         print("Кнопка 'Загрузить ещё' не найдена даже после прокрутки. Возможно, сайт изменился.")
         # Всё равно соберём то, что есть
      else:
         print("Кнопка найдена, начинаем подгружать курсы...")
      
      previous_count = 0
      while load_button and await load_button.is_visible():
         await load_button.click()
         await page.wait_for_timeout(500)  # ждём подгрузки
         # Снова прокрутим, чтобы кнопка оставалась в поле зрения
         await page.evaluate("window.scrollBy(0, 300)")
         await asyncio.sleep(0.5)
         
         cards = await page.query_selector_all("li.list-module__IWPZ_q__item")
         current_count = len(cards)
         if current_count == previous_count:
               print(f"Количество курсов не изменилось ({current_count}), выходим.")
               break
         previous_count = current_count
         print(f"Загружено курсов: {current_count}")
         # Заново ищем кнопку (возможно, после клика она заменяется новой)
         load_button = await page.query_selector("button:has-text('Загрузить ещё')")
         if not load_button:
               print("Кнопка пропала — все курсы загружены.")
               break
      
      # Собираем все карточки
      cards = await page.query_selector_all("li.list-module__IWPZ_q__item")
      print(f"\nВсего найдено карточек: {len(cards)}. Собираем информацию...")
      
      all_courses = []
      for card in cards:
         try:
               title_elem = await card.query_selector(".catalog-card-module__yPiKeq__title")
               title = (await title_elem.inner_text()).strip() if title_elem else ""
               org_elem = await card.query_selector(".university-module__sJ7OcG__universityInfo")
               org = (await org_elem.inner_text()).strip() if org_elem else ""
               link_elem = await card.query_selector(".catalog-card-module__yPiKeq__title")
               href = await link_elem.get_attribute("href") if link_elem else None
               full_url = "https://openedu.ru" + href if href else None
               status_elem = await card.query_selector(".dates-module__uK3cjq__status span")
               status = (await status_elem.inner_text()).strip() if status_elem else ""
               if full_url:
                  all_courses.append({
                     "title": title,
                     "org": org,
                     "status": status,
                     "url": full_url
                  })
         except Exception as e:
               print(f"Ошибка при чтении карточки: {e}")
               continue
      
      await browser.close()
      return all_courses

def parse_course_details(url):
   """Через requests + BeautifulSoup получает цену и дни до конца записи"""
   try:
      headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0"}
      resp = requests.get(url, headers=headers, timeout=10)
      if resp.status_code != 200:
         return "—", "—"
      soup = BeautifulSoup(resp.text, "html.parser")
      price_elem = soup.select_one(".course-info-module__r7MVta__price")
      price = price_elem.get_text(strip=True) if price_elem else "—"
      days_elem = soup.select_one(".course-info-module__r7MVta__days")
      days = days_elem.get_text(strip=True) if days_elem else "—"
      return price, days
   except Exception as e:
      print(f"Ошибка при парсинге {url}: {e}")
      return "—", "—"

async def main():
   print("1. Собираем ссылки и базовую информацию через Playwright...")
   courses = await collect_links_and_basic_info()
   if not courses:
      print("Не найдено ни одного курса.")
      return
   
   print(f"2. Парсим детали для {len(courses)} курсов через requests...")
   for i, course in enumerate(courses, 1):
      price, days = parse_course_details(course["url"])
      course["price"] = price
      course["days_left"] = days
      print(f"  {i}/{len(courses)}: {course['title'][:50]} – {price} – {days}")
   
   with open("openedu_courses.csv", "w", newline="", encoding="utf-8-sig") as f:
      writer = csv.DictWriter(f, fieldnames=["title", "org", "status", "price", "days_left", "url"])
      writer.writeheader()
      writer.writerows(courses)
   
   print(f"\n✅ Готово! Сохранено {len(courses)} курсов в файл openedu_courses.csv")

if __name__ == "__main__":
   asyncio.run(main())