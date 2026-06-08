from db_functions import (
   clear_course_links, 
   get_or_create_category, 
   get_or_create_subcategory
)
from kw import CATEGORIES, SUBCATEGORIES
from normalization_functions import normalize_text



def classify_course(title):
   """Классифицирует курс по названию с учётом исключений"""
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
         keywords = category_data 
         exceptions = []
      # Проверяем, есть ли исключения в названии
      has_exception = False
      for exc in exceptions:
         if exc.lower() in title_lower:
            has_exception = True
            break
      if has_exception:
         continue
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
         
         for course_id, title in courses:               
            result = classify_course(title)
            if not result["categories"] and not result["subcategories"]:
               no_categories_count += 1
               with open('unclassified_courses.txt', 'a', encoding='utf-8') as f:
                  f.write(f"{course_id}\t{title}\n")
               continue
            if not result["subcategories"]:
               with open('unSUBclassified_courses.txt', 'a', encoding='utf-8') as f:
                  f.write(f"{course_id}\t{title}\n")
               no_subcategories_count += 1
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
   
   
   
   
   
   
   
#  Функции для подгрузки ключевых слов из kw.py 
# def build_search_structure():
#    """
#    Строит структуру для быстрого поиска по ключевым словам
#    Возвращает: {
#       "category_name": {
#          "subcategory_name": ["keyword1", "keyword2", ...],
#          ...
#       }
#    }
#    """
#    search_structure = {}
   
#    # Инициализируем структуру категориями из CATEGORIES
#    for category_name in CATEGORIES.keys():
#       search_structure[category_name] = {}
   
#    # Заполняем подкатегориями из SUBCATEGORIES
#    for subcat_name, subcat_data in SUBCATEGORIES.items():
#       category_name = subcat_data["category"]
#       keywords = subcat_data["keywords"]
      
#       if category_name not in search_structure:
#          search_structure[category_name] = {}
      
#       search_structure[category_name][subcat_name] = keywords
   
#    # Для категорий без подкатегорий добавляем пустой словарь
#    return search_structure

# def build_category_keywords():
#    """
#    Строит структуру ключевых слов для категорий (без подкатегорий)
#    Возвращает: {"category_name": ["keyword1", "keyword2", ...]}
#    """
#    category_keywords = {}
   
#    for category_name, keywords in CATEGORIES.items():
#       category_keywords[category_name] = keywords
   
#    return category_keywords

