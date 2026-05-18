import mysql.connector
from mysql.connector import IntegrityError
import pymysql
from kw import CATEGORIES, SUBCATEGORIES


# conn = mysql.connector.connect(
#    host="localhost",
#    user="root",
#    password="zxcvbnasdqwe",
#    database="dpo_db"
# )

# cursor = conn.cursor()


def get_connection(db_name):
   return mysql.connector.connect(
      host="localhost",
      user="root",
      password="zxcvbnasdqwe",
      database=db_name,
   )


# Вспомогательные функции для работы с БД

def get_or_create_specialization(cursor, name: str) -> int:
   """Возвращает id специализации, создаёт если не существует."""
   cursor.execute("SELECT id FROM specializations WHERE name = %s", (name,))
   row = cursor.fetchone()
   if row:
      return row[0]
   cursor.execute("INSERT INTO specializations (name) VALUES (%s)", (name,))
   return cursor.lastrowid


def get_or_create_department(cursor, name: str, organization_id: int) -> int:
   """Возвращает id подразделения, создаёт если не существует."""
   cursor.execute("SELECT id FROM departments WHERE name = %s", (name,))
   row = cursor.fetchone()
   if row:
      return row[0]
   cursor.execute("INSERT INTO departments (name, organization_id) VALUES (%s, %s)", (name, organization_id,))
   return cursor.lastrowid


def update_department_contacts(cursor, dept_id: int, address: str,
                              phones: list, emails: list):
   """Обновляет адрес и добавляет контакты подразделения (без дублей)."""
   if address:
      cursor.execute(
         "UPDATE departments SET address = %s "
         "WHERE id = %s AND (address IS NULL OR address = '')",
         (address, dept_id)
      )
   for phone in phones:
      cursor.execute(
         "SELECT 1 FROM department_phones WHERE department_id = %s AND phone = %s",
         (dept_id, phone)
      )
      if not cursor.fetchone():
         cursor.execute(
               "INSERT INTO department_phones (department_id, phone) VALUES (%s, %s)",
               (dept_id, phone)
         )
   for email in emails:
      cursor.execute(
         "SELECT 1 FROM department_emails WHERE department_id = %s AND email = %s",
         (dept_id, email)
      )
      if not cursor.fetchone():
         cursor.execute(
               "INSERT INTO department_emails (department_id, email) VALUES (%s, %s)",
               (dept_id, email)
         )


def save_course(cursor, course: dict): 
   # Проверка данных перед сохранением 
   # print("\n---")
   # print(f"organization_id: {course['organization_id']}")
   # print(f"Title: {course['title'][:100] if course['title'] else None}")
   # print(f"URL: {course['url']}")
   # print(f"Price: {course['price']}")
   # print(f"Format: {course['format']}")
   # print(f"Course Type: {course['course_type']}")
   # print(f"Duration: {course['duration']}")
   # print(f"Date: {course['date']}")
   # print(f"Description: {course['description'][:100] if course['description'] else None}")
   # print(f"Language: {course['language']}")
   # print(f"Document: {course['document']}")
   # print(f"Admission Requirements: {course['admission_requirements']}")
   # print(f"Schedule: {course['schedule']}")
   # print(f"Department ID: {course['department_id']}")
   # print(f"Duration in hours: {course['duration_in_hours']}")
   # print("---")
   
   """Сохраняет курс. Возвращает id новой записи или None если дубликат."""
   query = """
      INSERT INTO dpo_courses (
         organization_id, title, price, format, course_type,
         duration, date, description, url, language, document,
         admission_requirements, schedule, department_id, duration_in_hours
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
   """
   try:
      cursor.execute(query, (
         course["organization_id"],
         course["title"],
         course["price"],
         course["format"],
         course["course_type"],
         course["duration"],
         course["date"],
         course["description"],
         course["url"],
         course["language"],
         course["document"],
         course["admission_requirements"],
         course["schedule"],
         course["department_id"],
         course["duration_in_hours"],
      ))
      return cursor.lastrowid
   except IntegrityError:
      return None  # дубликат по url
   
   
def link_course_specialization(cursor, course_id: int, spec_id: int):
   """Привязывает специализацию к курсу (many-to-many), игнорирует дубль."""
   try:
      cursor.execute(
         "INSERT INTO dpo_course_specializations (course_id, specialization_id) "
         "VALUES (%s, %s)",
         (course_id, spec_id)
      )
   except IntegrityError:
      pass


def get_or_create_category(cursor, name, conn=None):
   """Возвращает id категории, создаёт если нет"""
   try:
      cursor.execute("SELECT id FROM categories WHERE name = %s", (name,))
      row = cursor.fetchone()
      if row:
         return row[0]
      cursor.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
      if conn:
         conn.commit()
      return cursor.lastrowid
   except Exception as e:
      print(f"Ошибка при создании категории '{name}': {e}")
      raise


def get_or_create_subcategory(cursor, name, parent_category_id, conn=None):
   """Возвращает id подкатегории, создаёт если нет"""
   try:
      cursor.execute(
         "SELECT id FROM subcategories WHERE name = %s AND parent_category_id = %s", 
         (name, parent_category_id)
      )
      row = cursor.fetchone()
      if row:
         return row[0]
      cursor.execute(
         "INSERT INTO subcategories (name, parent_category_id) VALUES (%s, %s)", 
         (name, parent_category_id)
      )
      if conn:
         conn.commit()
      return cursor.lastrowid
   except Exception as e:
      print(f"Ошибка при создании подкатегории '{name}': {e}")
      raise

def clear_course_links(cursor, course_id):
   """Удаляет старые связи курса с категориями и подкатегориями"""
   cursor.execute("DELETE FROM rel_course_category WHERE course_id = %s", (course_id,))
   cursor.execute("DELETE FROM rel_course_subcategory WHERE course_id = %s", (course_id,))
   
   

# --------------------------------------------------------------
#     Функции для получения курсов по категориям/подкатегориям (для сайта)
# --------------------------------------------------------------

def get_courses_by_category(conn, category_id, limit=100, offset=0):
   """Возвращает список курсов (id, title, url и т.д.) для заданной категории"""
   try:
      with conn.cursor(pymysql.cursors.DictCursor) as cursor:
         cursor.execute("""
            SELECT c.id, c.title, c.url, c.price, c.duration, c.format
            FROM dpo_courses c
            JOIN rel_course_category rcc ON c.id = rcc.course_id
            WHERE rcc.category_id = %s
            LIMIT %s OFFSET %s
         """, (category_id, limit, offset))
         return cursor.fetchall()
   except Exception as e:
      print(f" Ошибка получения курсов по категории: {e}")
      return []

def get_courses_by_subcategory(conn, subcategory_id, limit=100, offset=0):
   """Возвращает список курсов для заданной подкатегории"""
   try:
      with conn.cursor(pymysql.cursors.DictCursor) as cursor:
         cursor.execute("""
            SELECT c.id, c.title, c.url, c.price, c.duration, c.format
            FROM dpo_courses c
            JOIN rel_course_subcategory rcs ON c.id = rcs.course_id
            WHERE rcs.subcategory_id = %s
            LIMIT %s OFFSET %s
         """, (subcategory_id, limit, offset))
         return cursor.fetchall()
   except Exception as e:
      print(f" Ошибка получения курсов по подкатегории: {e}")
      return []

def get_courses_count_by_category(conn, category_id):
   """Возвращает количество курсов в категории"""
   try:
      with conn.cursor() as cursor:
         cursor.execute("""
            SELECT COUNT(*) 
            FROM dpo_courses c
            JOIN rel_course_category rcc ON c.id = rcc.course_id
            WHERE rcc.category_id = %s
         """, (category_id,))
         return cursor.fetchone()[0]
   except Exception as e:
      print(f" Ошибка подсчета курсов: {e}")
      return 0


def get_all_categories_with_subcategories(conn):
   """Возвращает дерево категорий для построения фильтра"""
   try:
      with conn.cursor() as cursor:  # Убрали DictCursor
         cursor.execute("SELECT id, name FROM categories ORDER BY name")
         categories = cursor.fetchall()  # кортежи (id, name)
         
         result = []
         for cat_id, cat_name in categories:
            cursor.execute(
               "SELECT id, name FROM subcategories WHERE parent_category_id = %s ORDER BY name", 
               (cat_id,)
            )
            subcategories = cursor.fetchall()
            
            subcats_list = []
            for sub_id, sub_name in subcategories:
               cursor.execute("""
                  SELECT COUNT(*) FROM rel_course_subcategory 
                  WHERE subcategory_id = %s
               """, (sub_id,))
               count = cursor.fetchone()[0]
               subcats_list.append({
                  'id': sub_id, 
                  'name': sub_name, 
                  'courses_count': count
               })
            
            cursor.execute("""
               SELECT COUNT(DISTINCT course_id) FROM rel_course_category 
               WHERE category_id = %s
            """, (cat_id,))
            cat_count = cursor.fetchone()[0]
            
            result.append({
               'id': cat_id,
               'name': cat_name,
               'courses_count': cat_count,
               'subcategories': subcats_list
            })
         
         return result
   except Exception as e:
      print(f"Ошибка: {e}")
      return []

def search_courses_by_keyword(conn, keyword, limit=50):
   """Поиск курсов по ключевому слову в названии"""
   try:
      with conn.cursor(pymysql.cursors.DictCursor) as cursor:
         cursor.execute("""
            SELECT id, title, url, price, duration, format
            FROM dpo_courses
            WHERE title LIKE %s
            LIMIT %s
         """, (f"%{keyword}%", limit))
         return cursor.fetchall()
   except Exception as e:
      print(f" Ошибка поиска курсов: {e}")
      return []
   
   
def init_categories_and_subcategories(conn):
   """
   Инициализирует таблицы categories и subcategories
   на основе данных из CATEGORIES и SUBCATEGORIES
   """
   try:
      with conn.cursor() as cursor:
         # Вставляем категории
         print(" Добавление категорий...")
         for category_name in CATEGORIES.keys():
               cat_id = get_or_create_category(cursor, category_name, conn)
               print(f"   {category_name} (ID: {cat_id})")
         
         # Вставляем подкатегории
         print("\n Добавление подкатегорий...")
         for subcat_name, subcat_data in SUBCATEGORIES.items():
               category_name = subcat_data["category"]
               # Получаем ID категории
               cursor.execute("SELECT id FROM categories WHERE name = %s", (category_name,))
               row = cursor.fetchone()
               if row:
                  cat_id = row[0]
                  subcat_id = get_or_create_subcategory(cursor, subcat_name, cat_id, conn)
                  print(f"   {category_name} -> {subcat_name} (ID: {subcat_id})")
               else:
                  print(f"   Ошибка: категория '{category_name}' не найдена для подкатегории '{subcat_name}'")
         
         conn.commit()
         print("\n Инициализация категорий и подкатегорий завершена!")
         
   except Exception as e:
      print(f" Ошибка при инициализации: {e}")
      conn.rollback()
      raise