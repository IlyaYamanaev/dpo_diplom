from kw import CATEGORIES, SUBCATEGORIES
import re



# --------------------------------------------------------------
#     Преобразование структур
# --------------------------------------------------------------

# Нормализация названия (текста в принципе)курса 
def normalize_text(text):
   if not text:
      return ""
   # Приводим к нижнему регистру
   text = text.lower()
   # Заменяем все виды дефисов и тире на обычный дефис
   text = re.sub(r'[‐‑‒–—―−]', '-', text)
   # Убираем все виды кавычек
   text = re.sub(r'[«»„“”‘’‚]', '', text)
   # Заменяем специальные пробелы на обычные
   text = re.sub(r'[\u00A0\u2000-\u200A\u202F\u205F]', ' ', text)
   # Убираем знаки препинания в конце (но не внутри)
   text = re.sub(r'[.,!?;:]+$', '', text)
   # Убираем множественные пробелы
   text = re.sub(r'\s+', ' ', text).strip()
   # ё на е
   text = re.sub(r'ё', 'е', text)
   return text    


def normalize_price_string(price_str):
   """Нормализация строки с ценой курса. Убирает символы валюты, пробелы, оставляет только цифры и точку."""
   if price_str is None:
      return None
   # Приводим к строке и удаляем лишние пробелы
   price_str = str(price_str).strip()
   # Пустая строка
   if price_str == '':
      return None
   # Бесплатно и подобные - оставляем как есть
   if price_str.lower() in ['бесплатно']:
      return "Бесплатно"
   # Удаляем пробелы
   price_str = re.sub(r'\s+', '', price_str)
   # Удаляем символы ₽, р, р., руб, руб.
   price_str = re.sub(r'[₽р]\.?', '', price_str)
   price_str = re.sub(r'руб\.?', '', price_str, flags=re.IGNORECASE)
   # Заменяем запятую на точку
   price_str = price_str.replace(',', '.')
   # Оставляем только цифры и точку
   price_str = re.sub(r'[^\d.]', '', price_str)
   if price_str == '':
      return None
   # Преобразуем в число, отбрасываем копейки
   try:
      if '.' in price_str:
         return str(int(float(price_str)))
      else:
         return str(int(price_str))
   except ValueError:
      return None
   

def normalize_format_string(format_str):
   """Нормализация формата курса (format) на основе ключевых слов и правил."""
   if format_str is None:
      return None
   # Приводим к строке и нормализуем текст
   format_str = str(format_str).strip()
   # Пустая строка
   if format_str == '' or format_str.lower() == 'null':
      return None
   
   # Применяем normalize_text из вашего кода (предполагается что она импортирована)
   normalized = normalize_text(format_str).lower()
   
   # Список ключевых слов для каждого формата 
   # "не указан" -> None
   if 'не указан' in normalized:
      return None
   # "Очный" - проверяем первым, чтобы не перекрылось "онлайн"
   if 'очный' in normalized or 'очная' in normalized or 'офлайн' in normalized:
      return "Очный"
   # "Очно-заочная" -> Смешанный
   if 'очно-заочная' in normalized:
      return "Смешанный"
   # "Смешанный", "гибридный", "гибрид" -> Смешанный
   if any(word in normalized for word in ['смешанный', 'гибридный', 'гибрид']):
      return "Смешанный"
   # "онлайн асинхронный" -> Онлайн
   if 'онлайн асинхронный' in normalized:
      return "Онлайн"
   # Проверки для "Очно, онлайн" (смешанный формат с живым участием)
   if any(word in normalized for word in ['вебинар', 'онлай', 'онлайн-занятия', 'мини-группах', 'обратная связь']):
      # Если есть "вебинар" или "онлайн" - это онлайн-формат
      return "Онлайн"
   # Если есть и "очн" и "дист" одновременно
   if 'очн' in normalized and 'дист' in normalized:
      return "Онлайн"
   # онлайн по ключевым словам
   online_keywords = [
      'видеолекц', 'видеоурок', 'видеозаписи', 'разборная сессия',
      'лонгриды', 'практические задания', 'вебинар в записи',
      'марафон', 'вебинара в записи', 'онлайн синхронный', 'онлайн асинхронный', 'в записи', 'воркшопы', 'раза в неделю'
   ]
   if any(word in normalized for word in online_keywords):
      return "Онлайн"
   # Если ничего не подошло и есть слово "онлайн" - тоже Онлайн
   if 'онлайн' in normalized:
      return "Онлайн"
   # Если есть слово "вебинар" (уже проверяли, но на всякий случай)
   if 'вебинар' in normalized:
      return "Онлайн"
   # Если ничего не найдено, возвращаем оригинал (или None)
   if format_str and len(format_str) > 0:
      return format_str
   return None


def normalize_course_type_string(course_type_str):
   """Нормализация типа курса (course_type) на основе ключевых слов и правил."""
   # Обработка NULL и пустых значений
   if course_type_str is None:
      return "Не указан"
   # Приводим к строке и нормализуем текст
   course_type_str = str(course_type_str).strip()
   # Пустая строка
   if course_type_str == '' or course_type_str.lower() == 'null':
      return "Не указан"
   # Применяем normalize_text из вашего кода
   try:
      from filtration import normalize_text
      normalized = normalize_text(course_type_str).lower()
   except ImportError:
      normalized = course_type_str.lower()
   # Список правил в порядке приоритета
   rules = [
      ('профессия', 'Профессия'),
      ('бакалавриат', 'Бакалавриат'),
      ('магистратура', 'Магистратура'),
      ('specialized master', 'Магистратура'),
      ('государственное управление', 'Магистратура'),
      ('курс', 'Курс'),
      ('повышения квалификации', 'Повышение квалификации'),
      ('повышение квалификации', 'Повышение квалификации'),
      ('профессиональной переподготовки', 'Профессиональная переподготовка'),
      ('профессиональная переподготовка', 'Профессиональная переподготовка'),
      ('профессиональное обучение', 'Профессиональная переподготовка'),
      ('профессиональной подготовки', 'Профессиональная переподготовка'),
      ('образовательная программа', 'Дополнительное образование'),
      ('общеразвивающая программа', 'Дополнительное образование'),
      ('специализация', 'Дополнительное образование'),
      ('дополнительное образование', 'Дополнительное образование'),
      ('executive master', 'Бизнес-образование'),
      ('бизнес-образование', 'Бизнес-образование'),
      ('mba', 'Бизнес-образование'),
   ]
   for keyword, result in rules:
      if keyword in normalized:
         return result
   # Если ничего не подошло
   if course_type_str and len(course_type_str) > 0:
      return "Не указан"
   return "Не указан"



def normalize_duration_string(duration_str):
   """
   Нормализует одну запись длительности курса.
   Оставляет только цифры (число часов).
   """   
   # Обработка NULL и пустых значений
   if duration_str is None:
      return "Не указан"
   # Приводим к строке и удаляем лишние пробелы
   duration_str = str(duration_str).strip()
   # Пустая строка или null
   if duration_str == '' or duration_str.lower() == 'null':
      return "Не указан"
   # "Не указана" и подобные
   if any(word in duration_str.lower() for word in 
          ['не указан', 'не указана', 'не указано']):
      return "Не указан"
   # Нормализуем текст (убираем лишние пробелы, приводим к нижнему регистру)
   try:
      from filtration import normalize_text
      normalized = normalize_text(duration_str).lower()
   except ImportError:
      normalized = duration_str.lower()
   # Удаляем слова-маркеры
   words_to_remove = [
      'часа', 'часов', 'час', 'ак. ч.', 'ак.ч.', 'ак ч', 'акч',
      'академических', 'академический', 'академических', 'академического',
      'ак.', 'дней', 'день', 'дня', 'всего', 'около', 'до', 'более'
   ]
   for word in words_to_remove:
      normalized = normalized.replace(word, ' ')
   # Оставляем только цифры и пробелы
   normalized = re.sub(r'[^\d\s]', ' ', normalized)
   # Разбиваем на части и берем первую группу цифр
   parts = normalized.split()
   for part in parts:
      if part.isdigit():
         return str(int(part))  # убираем ведущие нули
   # Если ничего не нашли
   if duration_str and len(duration_str) > 0:
      return "Не указан"
   return "Не указан"


def build_search_structure():
   """
   Строит структуру для быстрого поиска по ключевым словам
   Возвращает: {
      "category_name": {
         "subcategory_name": ["keyword1", "keyword2", ...],
         ...
      }
   }
   """
   search_structure = {}
   
   # Инициализируем структуру категориями из CATEGORIES
   for category_name in CATEGORIES.keys():
      search_structure[category_name] = {}
   
   # Заполняем подкатегориями из SUBCATEGORIES
   for subcat_name, subcat_data in SUBCATEGORIES.items():
      category_name = subcat_data["category"]
      keywords = subcat_data["keywords"]
      
      if category_name not in search_structure:
         search_structure[category_name] = {}
      
      search_structure[category_name][subcat_name] = keywords
   
   # Для категорий без подкатегорий добавляем пустой словарь
   return search_structure

def build_category_keywords():
   """
   Строит структуру ключевых слов для категорий (без подкатегорий)
   Возвращает: {"category_name": ["keyword1", "keyword2", ...]}
   """
   category_keywords = {}
   
   for category_name, keywords in CATEGORIES.items():
      category_keywords[category_name] = keywords
   
   return category_keywords