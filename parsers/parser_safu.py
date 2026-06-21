import os
from bs4 import BeautifulSoup

from db_functions import (
   get_connection,
   link_course_specialization,
   save_course,
   get_or_create_department,
   get_or_create_specialization,
)
from utilit import clean_text

BASE_URL = "https://narfu.ru"
DB_NAME = "buff_dpo_db"
ORGANIZATION_ID = 9         
ORGANIZATION_NAME = "САФУ"

FILES = ["parsers\\txts\\table1.txt", 
         "parsers\\txts\\table2.txt"]

# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ 
def parse_course_row(row):
   """Извлекает данные из одной строки <tr>."""
   cells = row.find_all("td")
   if len(cells) < 7:
      return None
   # Название и ссылка
   first_cell = cells[0]
   a_tag = first_cell.find("a")
   if not a_tag:
      return None
   title = clean_text(a_tag.get_text())
   href = a_tag.get("href")
   url = BASE_URL + href if href.startswith("/") else href
   # duration_in_hours
   duration_hours = clean_text(cells[1].get_text())
   # Цена
   price = clean_text(cells[2].get_text())
   if price and '.' in price:
      price = price.split('.')[0]
   # Тип курса
   course_type = clean_text(cells[3].get_text())
   # Подразделение (department)
   dept_cell = cells[4]
   dept_span = dept_cell.find("span", class_="multiplayProp")
   if dept_span:
      dept_a = dept_span.find("a")
      department_name = clean_text(dept_a.get_text()) if dept_a else clean_text(dept_span.get_text())
   else:
      department_name = clean_text(dept_cell.get_text())
   # Дата
   date = clean_text(cells[5].get_text())
   # Специализации (направления)
   spec_cell = cells[6]
   spec_span = spec_cell.find("span", class_="NAPRAVLENIE")
   if spec_span:
      raw_specs = spec_span.decode_contents().split("<br/>")
      specs = [clean_text(s) for s in raw_specs if clean_text(s)]
   else:
      specs = []
   # Определяем документ по типу курса
   document = None
   if course_type == "Краткосрочные курсы и тренинги (сертификат)":
      document = "Сертификат"
   elif course_type == "Повышение квалификации (удостоверение)":
      document = "Удостоверение о повышении квалификации"
   elif course_type == "Профессиональная переподготовка (диплом)":
      document = "Диплом о профессиональной переподготовке"
   elif course_type == "Профессиональное обучение (свидетельство)":
      document = "Свидетельство о профессиональном обучении"

   return {
      "title": title,
      "url": url,
      "duration_in_hours": duration_hours if duration_hours else None,
      "price": price if price else None,
      "course_type": course_type if course_type else None,
      "department_name": department_name if department_name else None,
      "date": date if date else None,
      "specializations": specs,
      "document": document,
      "organization_id": ORGANIZATION_ID,
   }


# ОСНОВНАЯ ФУНКЦИЯ 
def main_safu(DB_NAME):
   db_name = DB_NAME
   print("=== Парсер программ ДПО САФУ (из файлов) ===\n")

   conn = get_connection(db_name)
   cursor = conn.cursor()

   cursor.execute("SELECT id FROM organizations WHERE id = %s", (ORGANIZATION_ID,))
   if not cursor.fetchone():
      cursor.execute(
         "INSERT INTO organizations (id, name) VALUES (%s, %s)",
         (ORGANIZATION_ID, ORGANIZATION_NAME)
      )
      conn.commit()
      print(f"Создана организация: id={ORGANIZATION_ID}, name={ORGANIZATION_NAME}")

   saved = 0
   skipped = 0
   errors = 0
   total_rows = 0

   for filename in FILES:
      if not os.path.exists(filename):
         print(f"Файл {filename} не найден, пропускаем.")
         continue
      
      print(f"\n--- Обработка файла: {filename} ---")
      with open(filename, "r", encoding="utf-8") as f:
         content = f.read()
      
      soup = BeautifulSoup(content, "html.parser")
      tbody = soup.find("tbody")
      if not tbody:
         print(f"В файле {filename} не найден <tbody>")
         continue
      
      rows = tbody.find_all("tr")
      print(f"Найдено строк в файле: {len(rows)}")
      total_rows += len(rows)

      for idx, row in enumerate(rows, 1):
         print(f"  [{idx}/{len(rows)}] Обработка...", end=" ")
         try:
            course_data = parse_course_row(row)
            if not course_data or not course_data["title"]:
               print("нет названия → пропуск")
               skipped += 1
               continue

            department_id = None
            if course_data["department_name"]:
               department_id = get_or_create_department(
                  cursor, course_data["department_name"], ORGANIZATION_ID
               )

            db_course = {
               "organization_id": course_data["organization_id"],
               "title": course_data["title"],
               "price": course_data["price"],
               "format": None,
               "course_type": course_data["course_type"],
               "duration": None,
               "date": course_data["date"],
               "description": None,
               "url": course_data["url"],
               "language": None,
               "document": course_data["document"],
               "admission_requirements": None,
               "schedule": None,
               "duration_in_hours": course_data["duration_in_hours"],
               "department_id": department_id,
            }

            course_id = save_course(cursor, db_course)
            if course_id is None:
               print("дубликат → пропуск")
               skipped += 1
               conn.commit()
               continue

            for spec_name in course_data["specializations"]:
               spec_id = get_or_create_specialization(cursor, spec_name)
               if spec_id:
                  link_course_specialization(cursor, course_id, spec_id)

            conn.commit()
            print(f"OK (id={course_id})")
            saved += 1

         except Exception as e:
            conn.rollback()
            print(f"ошибка: {e}")
            errors += 1

   cursor.close()
   conn.close()

   print(f"\n=== Итог ===")
   print(f"Всего строк: {total_rows}")
   print(f"Сохранено:   {saved}")
   print(f"Пропущено:   {skipped}")
   print(f"Ошибок:      {errors}")

if __name__ == "__main__":
   main_safu(DB_NAME)