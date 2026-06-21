import re


def normalize_column(conn, select_column, update_column, transform_func, table="dpo_courses",):
   try:
      with conn.cursor() as cursor:
         cursor.execute(f"SELECT id, {select_column} FROM {table}")
         courses = cursor.fetchall()
         updated = 0
         skipped = 0
         print(f"\n{select_column}: всего записей {len(courses)}")

         for course_id, old_value in courses:
            new_value = transform_func(old_value)
            if new_value != old_value:
               cursor.execute(
                  f"UPDATE {table} SET {update_column} = %s WHERE id = %s",
                  (new_value, course_id),
               )
               updated += 1
            else:
               skipped += 1

         conn.commit()
         print(f"   Обновлено: {updated}")
         print(f"   Пропущено: {skipped}")

   except Exception as e:
      print(f"Ошибка: {e}")
      conn.rollback()


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


def normalize_language_string(lang_val):
   if not lang_val or str(lang_val).strip() == '':
      return 'русский'
   s = str(lang_val).lower().strip('"')
   # Проверяем ключевые слова по порядку
   if 'рус' in s:
      return 'русский'
   if 'анг' in s:
      return 'английский'
   if 'франц' in s:
      return 'французский'
   if 'кит' in s:
      return 'китайский'
   if 'испан' in s:
      return 'испанский'
   if 'араб' in s:
      return 'арабский'
   return 'русский'


def normalize_price_string(value: str, ) -> int:
   """Извлекает цену в рублях из строки с различными форматами. Возвращает целое число """
   MAX_PRICE = 4000000
   # 1. Приводим к строке и очищаем
   if value is None:
      return None
   s = str(value).strip()
   if not s or s.lower() in ('', 'null', 'nan'):
      return None
   s_lower = s.lower()
   # 2. Бесплатно
   if 'бесплат' in s_lower:
      return 0
   # 3. Неопределённые фразы (уточнять, по запросу и т.п.)
   uncertain_pattern = r'(уточ\w+.*телефон|стоимост\w+.*уточ|по\s+запросу|по\s+телефону|уточнять)'
   if re.search(uncertain_pattern, s_lower, re.I):
      return None
   # 4. Ищем все числа (включая десятичные, с пробелами-разделителями тысяч)
   num_pattern = r'(\d[\d\s]*[\d.,]?\d*)'
   candidates = []
   for match in re.finditer(num_pattern, s):
      num_str = match.group()
      num_clean = re.sub(r'\s+', '', num_str)
      if ',' in num_clean and '.' not in num_clean:
         num_clean = num_clean.replace(',', '.')
      try:
         val = float(num_clean)
      except ValueError:
         continue
      if val > MAX_PRICE:
         continue
      # Проверяем, есть ли символ валюты рядом
      start, end = match.span()
      context_before = s[max(0, start-10):start]
      context_after = s[end:min(len(s), end+10)]
      has_currency = bool(re.search(r'[₽руб]', context_before + context_after, re.I))
      candidates.append((val, start, has_currency))
   if not candidates:
      return None
   # 5. Сортируем кандидатов: сначала с валютой, потом по позиции
   candidates.sort(key=lambda x: (not x[2], x[1]))
   best_val = candidates[0][0]
   # 6. Преобразуем в целое с округлением
   price_int = int(round(best_val))
   # 7. Дополнительная фильтрация мусорных чисел 
   if price_int < 10 and price_int != 0:
      return None

   return price_int
   
   
def normalize_format_string(value: str) ->str:
   """
   Нормализует строку с форматом обучения в одно из значений:
   """
   # 1. Приводим к строке и очищаем
   if value is None:
      return None
   s = str(value).strip()
   if not s or s.lower() in ('', 'null', 'nan', 'none'):
      return None

   s_lower = s.lower()

   # 2. Неопределённые фразы
   if 'не указан' in s_lower:
      return None

   # 3. Приоритет: смешанный / гибридный
   mixed_pattern = r'(смешанн|гибрид|очно-заочн|очн.*дист|очная.*дист|очно-дист)'
   if re.search(mixed_pattern, s_lower):
      return "Смешанный"

   # 4. Очный формат
   online_indicators = ['онла', 'вебинар', 'видеолекц', 'в запи', 'асинхронн', 'синхронн']
   has_online = any(ind in s_lower for ind in online_indicators)

   if re.search(r'(очн(ый|ая|ое)|офлайн|очно)', s_lower) and not has_online:
      return "Очный"

   # 5. Онлайн формат
   # Прямые указания на онлайн
   if re.search(r'(онлайн|вебинар|видеолекц|видеозап|асинхронн|синхронн|в записи|связь|практика|дист)', s_lower):
      return "Онлайн"

   # Заочная форма – приравниваем к онлайн (дистант)
   if 'заочн' in s_lower:
      return "Онлайн"

   # 6. Если остались какие-то длинные описания с глаголами обучения – вероятно, онлайн
   # Но чтобы не ошибиться, лучше вернуть None для нераспознанных
   # Проверяем, нет ли слов, характерных для описания контента, без явного формата
   # Если есть упоминание занятий, лекций, но нет ключевых слов формата – None
   content_words = ['лекци', 'практик', 'кейс', 'задани', 'тест', 'тренажёр', 'наставничество']
   if any(w in s_lower for w in content_words):
      return None

   # 7. Если ничего не подошло, возвращаем None
   return None


def normalize_course_type_string(value: str) -> str:
   """
   Нормализует строку с типом курса в одно из значений
   """
   # 1. Приводим к строке и очищаем
   if value is None:
      return None
   s = str(value).strip()
   if not s or s.lower() in ('', 'null', 'nan', 'none'):
      return None

   s_lower = s.lower()

   # 2. Мусорные значения (проценты, символы)
   if re.match(r'^[-+]?\d+%$', s_lower):
      return None

   # 3. Неопределённые фразы
   if 'не указан' in s_lower:
      return None

   # 4. Приоритетные правила (первые сработавшие возвращаются)
   rules = [
      (r'(профессиональной? переподготовки?|профессиональное обучение|профессиональная переподготовка|профессия|профессиональной подготовки)', 'Профессиональная переподготовка'),
      (r'(повышения? квалификации|программа повышения квалификации|повышение квалификации)', 'Повышение квалификации'),
      (r'(mba|executive master|specialized master|бизнес-образование|doctor)', 'Бизнес-образование'),
      (r'(магистратура|specialized master|государственное управление)', 'Магистратура'),
      (r'бакалавриат', 'Бакалавриат'),
      (r'(дополнительн(?:ое|ая|ые)?\s*(?:образование|общеразвивающ|общеобразовательн)|специализация|курс|школьник|общеобразовательная|общеразвивающая|доп\.?\s*образование)', 'Дополнительное образование'),
   ]

   for pattern, result in rules:
      if re.search(pattern, s_lower):
         return result

   return value


def normalize_duration_in_hours_string(value: str) -> int:
   """
   Извлекает количество часов из строки с различными форматами.
   Возвращает целое число (часы) или None, если длительность не указана или не может быть однозначно преобразована.
   """
   MAX_HOURS = 10_000  # максимальное разумное количество часов (более 10k часов ~ 416 дней)

   # 1. Приводим к строке и очищаем
   if value is None:
      return None
   s = str(value).strip()
   if not s or s.lower() in ('', 'null', 'nan', 'none'):
      return None

   s_lower = s.lower()

   # 2. Неопределённые фразы
   uncertain_pattern = r'(не указан|не указана|не указано|уточн|по запросу|по телефону)'
   if re.search(uncertain_pattern, s_lower, re.I):
      return None

   # 3. Если есть указание на недели, дни и т.п. – не можем однозначно перевести в часы
   vague_units = r'(недел|дней|дня|день|месяц|месяца|год|года)'
   if re.search(vague_units, s_lower, re.I):
      return None

   # 4. Ищем все числа (включая десятичные, с пробелами-разделителями)
   num_pattern = r'(\d[\d\s]*[\d.,]?\d*)'
   candidates = []

   for match in re.finditer(num_pattern, s):
      num_str = match.group()
      num_clean = re.sub(r'\s+', '', num_str)
      if ',' in num_clean and '.' not in num_clean:
         num_clean = num_clean.replace(',', '.')
      try:
         val = float(num_clean)
      except ValueError:
         continue

      # Отбрасываем слишком большие
      if val > MAX_HOURS:
         continue

      # Проверяем, есть ли рядом единица измерения (часы, ак.ч., контактные и т.п.)
      start, end = match.span()
      context_before = s[max(0, start-15):start]
      context_after = s[end:min(len(s), end+15)]
      context = (context_before + context_after).lower()
      has_hour_unit = bool(re.search(r'(час|ак\.?ч|академич|контактн|ч\.)', context, re.I))

      # Сохраняем кандидата (число, позиция, флаг наличия часовой единицы)
      candidates.append((val, start, has_hour_unit))

   if not candidates:
      return None

   # 5. Сортируем: сначала те, у которых есть единица измерения, потом по позиции
   candidates.sort(key=lambda x: (not x[2], x[1]))
   best_val = candidates[0][0]

   # 6. Округляем до целых часов
   hours = int(round(best_val))

   # 7. Отсекаем слишком маленькие значения (менее 1 часа) – обычно это ошибка
   if hours < 1:
      return None

   return hours


def normalize_duration_string(duration_str):
   if duration_str is None:
      return None

   s = str(duration_str).strip()
   if not s or s.lower() in ('null', 'nan', 'не указ'):
      return None

   # 2. Удаляем скобки и всё, что внутри них
   s = re.sub(r'\s*\([^)]*\)', '', s)

   # 3. Удаляем мусорные слова (учебных, учетных, ак.ч., часов и т.д.)
   #    Но не трогаем предлоги (от, до) и диапазоны.
   garbage_words = [
      r'\b(?:учебных?|учебные|учетные|учетных?|ак\.?\s*ч\.?|академических?\s*часов?|часов?|занятий?|тренинговых?\s*дней?|персональных?\s*практик?)\b',
      r'\b(?:модуль|программы|набор|интенсив)\b',
   ]
   for gw in garbage_words:
      s = re.sub(gw, '', s, flags=re.IGNORECASE)

   # 4. Очистка от лишних запятых, дефисов в конце и пробелов
   s = re.sub(r',\s*$', '', s)
   s = re.sub(r'\s*[-–—]\s*$', '', s)
   s = s.strip()

   # 5. Паттерны для поиска ДЛИТЕЛЬНОСТЕЙ (сохраняем регистр, падежи, «от/до», пропись)
   # Единицы измерения (корни, включая «год» и «месяц»)
   units = r'(?:месяц[ае]?в?|мес|недел[ьяи]?|нед|день|дня|дней|дн|год[ае]?в?|года|лет)'

   # Прописные числа (1–12)
   words_num = r'(?:одна|одну|одной|один|две|два|три|четыре|пять|шесть|семь|восемь|девять|десять|одиннадцать|двенадцать)'

   # Цифровые числа (целые, дробные, диапазоны)
   digits_num = r'\d+(?:[.,]\d+)?(?:[-–—]\d+(?:[.,]\d+)?)?'

   # Префиксы (от, до, более, менее, около, ~) — не захватываем, чтобы они остались
   prefix = r'(?:от|до|более|менее|около|~)?\s*'

   # Ищем все вхождения (число + единица) в строке последовательно
   pattern = re.compile(
      prefix + r'(' + words_num + r'|' + digits_num + r')\s*(?:[-–—]?х?\s*)?' + units,
      re.IGNORECASE
   )

   matches = list(pattern.finditer(s))
   if not matches:
      return None

   result_parts = []
   for m in matches:
      result_parts.append(m.group(0).strip())

   # Склеиваем пробелом (например "1 год 5 месяцев")
   result = ' '.join(result_parts).strip()
   return result if result else None


def extract_last4(phone: str) -> str:
   """
   Извлекает последние 4 цифры номера.
   
   Игнорирует:
   - всё после *
   - (доб.1234)
   - любые скобки
   - пробелы, дефисы и т.д.
   """
   if not phone:
      return ""
   phone = str(phone)
   # Удаляем всё после *
   phone = phone.split("*")[0]
   # Удаляем (доб.1234) и подобное
   phone = re.sub(r'\(.*?доб.*?\)', '', phone, flags=re.IGNORECASE)
   # Оставляем только цифры
   digits = re.sub(r'\D', '', phone)
   if len(digits) < 4:
      return ""
   return digits[-4:]


def has_plus7(phone: str) -> bool:
   """Проверяет, есть ли +7 в начале номера"""
   if not phone:
      return False
   normalized = re.sub(r'\s+', '', phone)
   return normalized.startswith("+7")


def remove_duplicate_department_phones(conn):
   """Удаляет дубликаты телефонов в department_phones."""

   try:
      with conn.cursor() as cursor:
         cursor.execute("""
            SELECT id, department_id, phone
            FROM department_phones
            ORDER BY department_id, id
         """)

         rows = cursor.fetchall()
         print(f"Всего записей: {len(rows)}")
         grouped = {}

         # Группируем по department_id + last4
         for row in rows:
               row_id, department_id, phone = row
               last4 = extract_last4(phone)
               
               if not last4:
                  continue
               key = (department_id, last4)
               if key not in grouped:
                  grouped[key] = []
               grouped[key].append({
                  "id": row_id,
                  "phone": phone,
                  "plus7": has_plus7(phone)
               })
         to_delete = []

         # Ищем дубликаты
         for key, items in grouped.items():
               if len(items) <= 1:
                  continue
               # Сначала пытаемся оставить номер с +7
               plus7_items = [x for x in items if x["plus7"]]
               if plus7_items:
                  keep = plus7_items[0]
               else:
                  # иначе оставляем первую запись
                  keep = items[0]
               # Остальные удаляем
               for item in items:
                  if item["id"] != keep["id"]:
                     to_delete.append(item)
         deleted = 0
         # Удаление
         for item in to_delete:
            cursor.execute(
               "DELETE FROM department_phones WHERE id = %s",
               (item["id"],)
            )
            deleted += 1
         conn.commit()
         print(f"\nУдалено дублей: {deleted}")
         
   except Exception as e:
      print(f"Ошибка: {e}")
      conn.rollback()
