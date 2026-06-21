import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from db_functions import (
   get_connection,
   get_or_create_specialization,
   save_course,
   link_course_specialization,
)
from utilit import clean_text, get_html_with_playwright_selector

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------
BASE_URL = "https://dpo.dvfu.ru/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
}
DB_NAME = "buff_dpo_db"
ORGANIZATION_ID = 6  
DELAY = 0.7  

SPECIALIZATIONS = [
   "Бухгалтерский учет и налогообложение",
   "Военный учебный центр",
   "Закупочная деятельность",
   "Здоровьесберегающие технологии",
   "Инженерия",
   "Информационные технологии",
   "Кибербезопасность",
   "Креативные индустрии",
   "Медицина",
   "Педагогика",
   "Физическая культура и спорт",
   "Экология и природопользование",
   "Экономика и менеджмент",
]

# ---------------------------------------------------------------------------
# Сбор ссылок на курсы по каждой специализации
# ---------------------------------------------------------------------------
def collect_course_urls_by_specialization(session, spec_name: str) -> dict:
   """
   Собирает URL курсов для конкретной специализации.
   Возвращает словарь {url: specialization_name}
   """
   print(f"\n  Обработка специализации: {spec_name}")
   
   # Формируем URL с параметром фильтрации
   filter_url = f"{BASE_URL}?tfc_quantity%5B656736118%5D=y&tfc_charact:6443178%5B656736118%5D={spec_name}&tfc_div=:::"
   
   course_urls = {}
   page = 1
   
   while True:
      print(f"    Страница {page}...", end=" ", flush=True)
      
      # Проверяем наличие параметра page в URL
      if page == 1:
         page_url = filter_url
      else:
         page_url = f"{BASE_URL}?tfc_quantity%5B656736118%5D=y&tfc_charact:6443178%5B656736118%5D={spec_name}&tfc_page%5B656736118%5D={page}&tfc_div=:::"

      try:
         resp = session.get(page_url, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"ошибка: {e}")
         break
      
      html = get_html_with_playwright_selector(page_url, "div.t-store__card-list")
      soup = BeautifulSoup(html, "html.parser")
      
      card_list = soup.find("div", class_="t-store__card-list")
      if not card_list:
         card_list = soup.find("div", class_="t951__grid-cont")
      
      if not card_list:
         print("нет карточек - стоп")
         break
      
      cards = card_list.find_all("div", class_=lambda c: c and "t-store__card" in c.split())
      if not cards:
         print("нет карточек - стоп")
         break
      
      new_urls = 0
      for card in cards:
         link = card.find("a", href=True)
         if link and link.get("href"):
               url = urljoin(BASE_URL, link["href"])
               if url not in course_urls:
                  course_urls[url] = spec_name
                  new_urls += 1
      
      print(f"найдено {len(cards)} карточек, новых {new_urls}")
      
      # Проверяем наличие следующей страницы
      pagination = soup.find("div", class_="t-store__pagination")
      if pagination:
         next_btn = pagination.find("div", class_=lambda c: c and "t-store__pagination__item_next" in (c or ""))
         if not next_btn or "t-store__pagination__item_disabled" in (next_btn.get("class") or []):
               break
      else:
         break
      
      page += 1
      time.sleep(DELAY)
   
   print(f"    Всего URL для '{spec_name}': {len(course_urls)}")
   return course_urls

def collect_all_course_urls(session) -> dict:
   """Собирает URL всех курсов по всем специализациям"""
   all_urls = {}
   
   for spec in SPECIALIZATIONS:
      urls = collect_course_urls_by_specialization(session, spec)
      for url, spec_name in urls.items():
         if url not in all_urls:
               all_urls[url] = []
         all_urls[url].append(spec_name)
      time.sleep(DELAY)
   
   return all_urls

# ---------------------------------------------------------------------------
# Парсинг страницы курса
# ---------------------------------------------------------------------------
def parse_course_page(url: str, html: str) -> dict:
   """Парсит страницу курса и возвращает словарь с данными"""
   soup = BeautifulSoup(html, "html.parser")
   
   # Значения по умолчанию
   course = {
      "organization_id": ORGANIZATION_ID,
      "url": url,
      "title": None,
      "price": "Не указана",
      "format": "не указан",
      "course_type": None,
      "duration": "Не указана",
      "description": "Не указано",
      "language": "русский",
      "date": "Не указана",
      "document": "Не указан",
      "department_id": None,
      "admission_requirements": "Не указаны",
      "schedule": "Не указан",
      "duration_in_hours": "Не указана",
   }
   
   artboards = soup.find_all("div", class_="t396__artboard")
   
   for artboard in artboards:
      # названия курса
      if not course["title"]:
         title = clean_text(soup.title.get_text(strip=True))
         if title:
            course["title"] = title
            
      #  типа курса 
      if not course["course_type"]:
         type_elem = artboard.find("div", class_="tn-atom", attrs={"field": "tn_text_1708345124122"})
         if not type_elem:
               type_elem = artboard.find("div", class_="tn-atom", attrs={"field": "tn_text_1719373050096"})
         if type_elem:
               course["course_type"] = clean_text(type_elem.get_text(strip=True))
      
      for elem in artboard.find_all("div", class_="tn-atom"):
         field = elem.get("field", "")
         text = clean_text(elem.get_text(strip=True))
    
         # Формат обучения
         if field in ["tn_text_1708346943593", "tn_text_1708346812788"]:
            if "Форма обучения" in field or "Очн" in text or "Заоч" in text or "Онла" in text:
               if "Форма обучения" not in text and len(text) < 50:
                  course["format"] = text
         
         # Дата начала
         elif field in ["tn_text_1708346953726", "tn_text_1777355302112000003", "tn_text_1730811009400",
                        "tn_text_1772616356369000002", "tn_text_1742794723272", "tn_text_1774426426693000001",
                        "tn_text_1770364096663000007",
                        ]:
            course["date"] = text
         
         # Цена
         elif field in ["tn_text_1708346975066","tn_text_1739781250893", "tn_text_1730811009375",
                        "tn_text_1770364096663000006", "tn_text_1752828284975",
                        "tn_text_1752809916324", 
                        ]:
            course["price"] = text.strip('*')
         
         # Объем в часах
         elif field in ["tn_text_1708346907917", "tn_text_1714268331576"]:
            if text.isdigit() or (text.replace(" ", "").isdigit()): 
               hours_part = text
               # Ищем  единицы измерения
               units_elem = artboard.find("div", class_="tn-atom", attrs={"field": ["tn_text_1710228431103", "tn_text_1714268331598"]})
               if units_elem:
                  units = clean_text(units_elem.get_text(strip=True))
                  course["duration_in_hours"] = f"{hours_part} {units}"
               else:
                  course["duration_in_hours"] = hours_part
            else:
               if any(word in text for word in ['час']):
                  course["duration_in_hours"] = text
               else:
                  course["duration"] = text
               
         
         # Длительность 
         elif field in [
            "tn_text_1715773843427", "tn_text_1718260354294", "tn_text_1715675098007",
            "tn_text_1715580075697", "tn_text_1715768151382", "tn_text_1715774238928",
            "tn_text_1715773618655", 'tn_text_1715772778434', "tn_text_1715773432786",
            "tn_text_1716961325600", "tn_text_1715767070586", "tn_text_1723034691253",
            "tn_text_1715767335704", "tn_text_1715768238664", "tn_text_1730811009363",
            "tn_text_1730811009365", "tn_text_1715672278504", ]:
            
            if any(word in text for word in ['ден', 'дней', 'дня', 'мес', 'недел', 'год']):
               course["duration"] = text
            else:
               duration_value = text            
               duration_units_elem = None
               for pattern in [
                  "tn_text_1715675098020", "tn_text_1715773843434", "tn_text_1715580075705",
                  "tn_text_1715768151388", "tn_text_1715774238935", "tn_text_1715773618663",
                  "tn_text_1715772778441", "tn_text_1715773432793", "tn_text_1718260358750",
                  "tn_text_1716961329001", "tn_text_1715767070593", "tn_text_1723034691230",
                  "tn_text_1715767335713", "tn_text_1715768238672", "tn_text_1730811009365", 
                  "tn_text_1715672278520"]:
                  duration_units_elem = artboard.find("div", class_="tn-atom", 
                     attrs={"field": pattern})
                  if duration_units_elem:
                     break

               if duration_units_elem:
                  units = clean_text(duration_units_elem.get_text(strip=True))
                  course["duration"] = f"{duration_value} {units}"
               else:
                  course["duration"] = duration_value

   # Поиск описания 
   desc_elem = soup.find("div", class_="tn-atom", attrs={"field": ["tn_text_1719373250507", 
                  "tn_text_1708392663521", "tn_text_1751952982013"]})
   if not desc_elem:
      desc_elem = soup.find("div", class_="t-store__card__textwrapper")
   if desc_elem:
      course["description"] = clean_text(desc_elem.get_text(strip=True))[:1000]
   
   # Обработка title 
   if course["title"]:
      all_h1 = soup.find_all("h1", class_="tn-atom")
      if len(all_h1) >= 2:
         full_title = " ".join([clean_text(h.get_text(strip=True)) for h in all_h1])
         if len(full_title) > len(course["title"]):
               course["title"] = full_title
   
   # документ 
   if course["course_type"]:
      if "профессиональной переподготовки" in course["course_type"].lower():
         course["document"] = "Диплом о профессиональной переподготовке"
      elif "повышение квалификации" in course["course_type"].lower():
         course["document"] = "Удостоверение о повышении квалификации"
      else:
         course["document"] = "Сертификат"
      
   
   # Очистка текстовых полей 
   for key in ["title", "price", "format", "course_type", "duration", 
               "description", "date", "duration_in_hours"]:
      if course[key]:
         course[key] = clean_text(course[key])

   
   return course

# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------
def main_dvfu(DB_NAME):
   db_name = DB_NAME
   print("=== Парсер ДПO ДВФУ ===\n")
   
   conn = get_connection(db_name)
   cursor = conn.cursor()
   
   cursor.execute(
      "INSERT INTO organizations (id, name) VALUES (6, 'ДВФУ') "
      "ON DUPLICATE KEY UPDATE name = name"
   )
   conn.commit()
   
   print("Шаг 1: Сбор cсылок курсов по специализациям...")
   session = requests.Session()
   session.get(BASE_URL, headers=HEADERS)
   
   
   all_course_urls = collect_all_course_urls(session)
   
   print(f"\nВсего уникальных курсов найдено: {len(all_course_urls)}")
   
   print("\nШаг 2: Парсинг страниц курсов...")
   
   saved = 0
   skipped = 0
   errors = 0
   
   for i, (url, specializations) in enumerate(all_course_urls.items(), 1):
      print(f"  [{i}/{len(all_course_urls)}] {url}", end=" ... ", flush=True)
      
      try:
         resp = session.get(url, headers=HEADERS, timeout=30)
         resp.raise_for_status()
      except requests.RequestException as e:
         print(f"    Ошибка запроса: {e}")
         errors += 1
         time.sleep(DELAY)
         continue
      
      try:
         course = parse_course_page(url, resp.text)
         course_id = save_course(cursor, course)
         
         if course_id is None:
               print(f"    Дубликат - пропущен")
               skipped += 1
               conn.commit()
               time.sleep(DELAY)

               continue
         
         for spec_name in specializations:
               spec_id = get_or_create_specialization(cursor, spec_name)
               if spec_id:
                  link_course_specialization(cursor, course_id, spec_id)
         
         conn.commit()
         print(f"OK (id={course_id})")
         saved += 1
         
      except Exception as e:
         conn.rollback()
         print(f"    Ошибка парсинга: {e}")
         time.sleep(DELAY)

         errors += 1
      
      time.sleep(DELAY)
   
   cursor.close()
   conn.close()
   
   print(f"\n=== Итог ===")
   print(f"Сохранено:   {saved}")
   print(f"Дубликатов:  {skipped}")
   print(f"Ошибок:      {errors}")
   print(f"Всего курсов: {len(all_course_urls)}")

if __name__ == "__main__":
   main_dvfu(DB_NAME)