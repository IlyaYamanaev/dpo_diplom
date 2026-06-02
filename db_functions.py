import mysql.connector
from mysql.connector import IntegrityError
import logging
from kw import CATEGORIES, SUBCATEGORIES


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
   # print("---\n")
   
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
   
   
# --------------------------------------------------------------
#     Категории и подкатегории для классификации курсов
# --------------------------------------------------------------

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

   
 
def init_categories_and_subcategories(conn):
   """   Инициализирует таблицы categories и subcategories"""
   try:
      with conn.cursor() as cursor:
         cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
         cursor.execute("TRUNCATE TABLE rel_course_category;")
         cursor.execute("TRUNCATE TABLE rel_course_subcategory;")
         cursor.execute("TRUNCATE TABLE subcategories;")
         cursor.execute("TRUNCATE TABLE categories;")
         cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
         conn.commit()

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
   
# --------------------------------------------------------------
# Функции для еженедельного обновления
# --------------------------------------------------------------

   
def clear_buffer_db(BUFFER_DB):
   conn = get_connection(BUFFER_DB)

   try:
      with conn.cursor() as cursor:
         cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

         tables = [
               "rel_course_category",
               "rel_course_subcategory",
               "dpo_course_specializations",
               "department_emails",
               "department_phones",
               "subcategories",
               "categories",
               "dpo_courses",
               "departments",
               "specializations",
               "organizations"
         ]

         for table in tables:
               try:
                  cursor.execute(f"TRUNCATE TABLE {table}")
               except Exception as e:
                  logging.warning(f"Не удалось очистить {table}: {e}")

         cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

      conn.commit()

   finally:
      conn.close()


def replace_production_data(PROD_DB, BUFFER_DB):
   prod_conn = get_connection(PROD_DB)
   buff_conn = get_connection(BUFFER_DB)

   try:
      prod_cursor = prod_conn.cursor()
      buff_cursor = buff_conn.cursor()

      prod_cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

      tables = [
         "rel_course_category",
         "rel_course_subcategory",
         "dpo_course_specializations",
         "department_emails",
         "department_phones",
         "subcategories",
         "categories",
         "dpo_courses",
         "departments",
         "specializations",
         "organizations"
      ]

      for table in tables:
         prod_cursor.execute(f"TRUNCATE TABLE {table}")

      prod_cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

      copy_order = [
         "organizations",
         "specializations",
         "departments",
         "dpo_courses",
         "categories",
         "subcategories",
         "department_emails",
         "department_phones",
         "dpo_course_specializations",
         "rel_course_category",
         "rel_course_subcategory",
      ]

      for table in copy_order:

         buff_cursor.execute(f"SELECT * FROM {table}")
         rows = buff_cursor.fetchall()

         if not rows:
               continue

         placeholders = ",".join(["%s"] * len(rows[0]))

         prod_cursor.executemany(
               f"INSERT INTO {table} VALUES ({placeholders})",
               rows
         )

      prod_conn.commit()

   except Exception:
      prod_conn.rollback()
      raise

   finally:
      buff_conn.close()
      prod_conn.close()
