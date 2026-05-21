from kw import CATEGORIES, SUBCATEGORIES
from normalization_functions import ( 
   normalize_price_string, 
   normalize_format_string,
   normalize_text,
   normalize_course_type_string,
   normalize_duration_string,
   build_search_structure,
   build_category_keywords
)

from db_functions import (
   get_connection,
   clear_course_links,
   get_or_create_category,
   get_or_create_subcategory,
   init_categories_and_subcategories,
)


DB_NAME = "buff_dpo_db"

# Создаём структуры для поиска
SEARCH_STRUCTURE = build_search_structure()
CATEGORY_KEYWORDS = build_category_keywords()



# --------------------------------------------------------------
#     Функции классификации, фильтрации и нормализации курсов
# --------------------------------------------------------------
def classify_course(title):
   """
   Классифицирует курс по названию с учётом исключений
   """
   title_lower = normalize_text(title)  
   
   result_categories = set()
   result_subcategories = []
   
   # Проверяем категории (с учётом исключений)
   for category_name, category_data in CATEGORIES.items():
      # Поддержка как старого формата (список), так и нового (словарь)
      if isinstance(category_data, dict):
         keywords = category_data.get("keywords", category_data.get("inc", []))
         exceptions = category_data.get("exceptions", category_data.get("exc", []))
      else:
         keywords = category_data  # старый формат - просто список
         exceptions = []
      
      # Проверяем, есть ли исключения в названии
      has_exception = False
      for exc in exceptions:
         if exc.lower() in title_lower:
            has_exception = True
            break
      
      if has_exception:
         continue  # пропускаем эту категорию, если есть исключение
      
      # Ищем ключевые слова
      for keyword in keywords:
         if keyword.lower() in title_lower:
            result_categories.add(category_name)
            break
   
   # Аналогично для подкатегорий (если нужно добавить исключения)
   for subcat_name, subcat_data in SUBCATEGORIES.items():
      category_name = subcat_data["category"]
      keywords = subcat_data["keywords"]
      exceptions = subcat_data.get("exceptions", [])
      
      # Проверяем исключения
      has_exception = False
      for exc in exceptions:
         if exc.lower() in title_lower:
            has_exception = True
            break
      
      if has_exception:
         continue
      
      for keyword in keywords:
         if keyword.lower() in title_lower:
            result_subcategories.append((category_name, subcat_name))
            result_categories.add(category_name)
            break
   
   return {
      "categories": list(result_categories),
      "subcategories": result_subcategories
   }


def process_all_courses(conn):
   """Основная функция: читает все курсы из dpo_courses, классифицирует и заполняет связи"""
   processed_count = 0
   no_categories_count = 0
   no_subcategories_count = 0
   
   try:
      with conn.cursor() as cursor:
         # Получаем все курсы с id и title
         cursor.execute("SELECT id, title FROM dpo_courses WHERE title IS NOT NULL AND title != ''")
         courses = cursor.fetchall()
         
         print(f" Всего курсов для обработки: {len(courses)}")
         print("=" * 60)
         
         for course_id, title in courses:
               # print(f"Обработка курса {course_id}: {title[:50]}...")
               
            result = classify_course(title)
            
            if not result["categories"] and not result["subcategories"]:
               no_categories_count += 1
               # Записываем неклассифицированный курс в файл
               with open('unclassified_courses.txt', 'a', encoding='utf-8') as f:
                  f.write(f"{course_id}\t{title}\n")
               continue
            
            if not result["subcategories"]:
               with open('unSUBclassified_courses.txt', 'a', encoding='utf-8') as f:
                  f.write(f"{course_id}\t{title}\n")
               no_subcategories_count += 1
            
            # Удаляем старые связи
            clear_course_links(cursor, course_id)
            
            # Добавляем связи с категориями
            for cat_name in result["categories"]:
               cat_id = get_or_create_category(cursor, cat_name, conn)
               cursor.execute(
                  "INSERT IGNORE INTO rel_course_category (course_id, category_id) VALUES (%s, %s)",
                  (course_id, cat_id)
               )
            
            # Добавляем связи с подкатегориями
            for cat_name, subcat_name in result["subcategories"]:
               cat_id = get_or_create_category(cursor, cat_name, conn)
               subcat_id = get_or_create_subcategory(cursor, subcat_name, cat_id, conn)
               cursor.execute(
                  "INSERT IGNORE INTO rel_course_subcategory (course_id, subcategory_id) VALUES (%s, %s)",
                  (course_id, subcat_id)
               )
            
            processed_count += 1
            conn.commit()
         
         print("=" * 60)
         print(f" Статистика:")
         print(f"  - Обработано курсов: {processed_count}")
         print(f"  - Без категорий и подкатегорий: {no_categories_count}")
         print(f"  - Только с категориями (без подкатегорий): {no_subcategories_count}")
         
   except Exception as e:
      print(f" Ошибка при обработке: {e}")
      conn.rollback()
      raise
   finally:
      pass
   
   
# --------------------------------------------------------------
#     Функции нормализации данных
# --------------------------------------------------------------

def normalize_all_prices(conn):
   """Нормализует все цены в таблице dpo_courses"""
   try:
      with conn.cursor() as cursor:
         # Получаем все курсы
         cursor.execute("SELECT id, price FROM dpo_courses")
         courses = cursor.fetchall()
         
         updated = 0
         skipped = 0
         print(f"Всего записей: {len(courses)}")
         
         for course_id, price in courses:
            new_price = normalize_price_string(price)
            # Если цена изменилась
            if new_price != price:
               cursor.execute(
                  "UPDATE dpo_courses SET price = %s WHERE id = %s",
                  (new_price, course_id)
               )
               updated += 1
            else:
               skipped += 1
         conn.commit()
         print(f" Обновлено {updated} записей")
         print(f" Пропущено {skipped} записей")

   except Exception as e:
      print(f" Ошибка: {e}")
      conn.rollback()



def normalize_all_formats(conn):
   """Нормализует все форматы в таблице dpo_courses"""
   try:
      with conn.cursor() as cursor:
         # Получаем все курсы
         cursor.execute("SELECT id, format FROM dpo_courses")
         courses = cursor.fetchall()
         
         updated = 0
         skipped = 0
         print(f"Всего записей: {len(courses)}")

         for course_id, format_val in courses:
            new_format = normalize_format_string(format_val)
            # Если формат изменился
            if new_format != format_val:
               cursor.execute(
                  "UPDATE dpo_courses SET format = %s WHERE id = %s",
                  (new_format, course_id)
               )
               updated += 1
            else:
               skipped += 1
         conn.commit()
         print(f" Обновлено {updated} записей")
         print(f" Пропущено {skipped} записей")
         
   except Exception as e:
      print(f" Ошибка: {e}")
      conn.rollback()

def normalize_all_languagues(conn):
   """Нормализует все языки в таблице dpo_courses"""
   try:
      with conn.cursor() as cursor:
         # Получаем все курсы
         cursor.execute("SELECT id, language FROM dpo_courses")
         courses = cursor.fetchall()
         
         updated = 0
         skipped = 0
         print(f"Всего записей: {len(courses)}")

         for course_id, lang_val in courses:
            new_val = lang_val
            if 'Не указан' in lang_val:
               new_val = "русский"
            # Если язык изменился
            if new_val != lang_val:
               cursor.execute(
                  "UPDATE dpo_courses SET language = %s WHERE id = %s",
                  (new_val, course_id)
               )
               updated += 1
            else:
               skipped += 1
         conn.commit()
         print(f" Обновлено {updated} записей")
         print(f" Пропущено {skipped} записей")
         
   except Exception as e:
      print(f" Ошибка: {e}")
      conn.rollback()
      
      
def normalize_all_course_types(conn):
   """Нормализует все типы курсов в таблице dpo_courses"""
   try:
      with conn.cursor() as cursor:
         # Получаем все курсы
         cursor.execute("SELECT id, course_type FROM dpo_courses")
         courses = cursor.fetchall()
         
         updated = 0
         skipped = 0
         print(f"Всего записей: {len(courses)}")
         
         for course_id, course_type_val in courses:
               new_type = normalize_course_type_string(course_type_val)
               # Если тип изменился
               if new_type != course_type_val:
                  cursor.execute(
                     "UPDATE dpo_courses SET course_type = %s WHERE id = %s",
                     (new_type, course_id)
                  )
                  updated += 1
               else:
                  skipped += 1
         
         conn.commit()
         print(f"  Обновлено {updated} записей")
         print(f"  Пропущено {skipped} записей")
         
   except Exception as e:
      print(f"Ошибка: {e}")
      conn.rollback()


def normalize_all_durations(conn):
   """Нормализует все durations_in_hours в таблице dpo_courses"""
   try:
      with conn.cursor() as cursor:
         # Получаем все курсы
         cursor.execute("SELECT id, duration_in_hours FROM dpo_courses")
         courses = cursor.fetchall()
         
         updated = 0
         skipped = 0
         print(f" Всего записей: {len(courses)}")
         
         for course_id, duration_val in courses:
               new_duration = normalize_duration_string(duration_val)
               # Если значение изменилось
               if new_duration != duration_val:
                  cursor.execute(
                     "UPDATE dpo_courses SET duration_in_hours = %s WHERE id = %s",
                     (new_duration, course_id)
                  )
                  updated += 1
               else:
                  skipped += 1
         
         conn.commit()
         print(f"   Обновлено {updated} записей")
         print(f"   Пропущено {skipped} записей")
         
   except Exception as e:
      print(f"Ошибка: {e}")
      conn.rollback()
# --------------------------------------------------------------
#     Основной блок
# --------------------------------------------------------------
if __name__ == "__main__":
   conn = get_connection(DB_NAME)

   # Нормализация данных
   # normalize_all_formats(conn)
   # normalize_all_prices(conn)
   # normalize_all_languagues(conn)
   # normalize_all_course_types(conn)
   # normalize_all_durations(conn)

   # Очищаем файлы с неклассифицированными курсами
   with open('unclassified_courses.txt', 'w', encoding='utf-8') as f:
      f.write("НЕКЛАССИФИЦИРОВАННЫЕ КУРСЫ\n")
      f.write("=" * 60 + "\n")
   
   # Инициализируем категории и подкатегории в БД
   print(" Инициализация категорий и подкатегорий...")
   init_categories_and_subcategories(conn)
   
   # Классифицируем все курсы
   print("\n Классификация курсов...")
   process_all_courses(conn)
      
   conn.close()
   print("\n Работа завершена!")
