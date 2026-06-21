from normalization_functions import ( 
   normalize_language_string,
   normalize_price_string, 
   normalize_format_string,
   normalize_course_type_string,
   normalize_duration_in_hours_string,
   normalize_duration_string,
   remove_duplicate_department_phones,
   normalize_column
)
from normalization_date import normalize_date_string
from classification_functions import process_all_courses
from db_functions import get_connection, init_categories_and_subcategories


DB_NAME = "dpo_db"

def normalize_all_courses(DB_NAME):
   conn = get_connection(DB_NAME)

   print("Нормализация данных")
   normalize_column(conn, "language", "language", normalize_language_string) 
   normalize_column(conn, "format", "format", normalize_format_string)  
   normalize_column(conn, "price", "price", normalize_price_string)       
   normalize_column(conn, "course_type", "course_type", normalize_course_type_string)   
   normalize_column(conn, "duration_in_hours", "duration_in_hours", normalize_duration_in_hours_string)   
   normalize_column(conn, "duration", "duration", normalize_duration_string) 
   normalize_column(conn, "date", "norm_date", normalize_date_string)       
   remove_duplicate_department_phones(conn)    
   print("Нормализация данных завершена")
   
   conn.close()
  
  
def classify_all_courses(DB_NAME):
   conn = get_connection(DB_NAME)

   # Очищаем файлы с неклассифицированными курсами
   with open('unclassified_courses.txt', 'w', encoding='utf-8') as f:
      f.write("КУРСЫ без категорий\n")
   with open('unSUBclassified_courses.txt', 'w', encoding='utf-8') as f:
      f.write("КУРСЫ без подкатегорий\n")

   print(" Инициализация категорий и подкатегорий...")
   init_categories_and_subcategories(conn)

   print("\n Классификация курсов...")
   process_all_courses(conn)

   print("\n Работа завершена!")
   conn.close()


if __name__ == "__main__":
   normalize_all_courses(DB_NAME)
   classify_all_courses(DB_NAME)
   
   
   
   
   
   
   
   
   