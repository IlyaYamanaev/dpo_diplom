import re
from datetime import date

def normalize_date_string(value: str) -> date:
   """Извлекает дату из строки с различными форматами. Возвращает объект date или None."""
   if value is None:
      return None
   
   s = str(value).strip()
   if not s or s.lower() in ('', 'null', 'nan', 'none'):
      return None
   
   s_lower = s.lower()
   ref_date = date.today()
   
   # Бессрочные/неопределённые фразы
   if re.search(r'(не указан|любое время|сразу после|доступ сразу|начните учиться|в удобное время|по мере комплектования|по запросу|будние дни|еженедельно|по рабочим дням|новые группы формируются)', s_lower, re.I):
      return None
   
   # 2. Специальные случаи
   # Ежемесячно -> первое число следующего месяца
   if 'ежемесячно' in s_lower:
      if ref_date.month == 12:
         return date(ref_date.year + 1, 1, 1)
      else:
         return date(ref_date.year, ref_date.month + 1, 1)
   
   # 3. Обработка "Ноябрь - декабрь 2026" (интервал месяцев)
   month_interval_pattern = r'([а-я]+)\s*[-–—]\s*([а-я]+)\s+(\d{4})'
   match = re.search(month_interval_pattern, s_lower, re.I)
   if match:
      months_ru = {
         'январь': 1, 'февраль': 2, 'март': 3, 'апрель': 4, 'май': 5, 'июнь': 6,
         'июль': 7, 'август': 8, 'сентябрь': 9, 'октябрь': 10, 'ноябрь': 11, 'декабрь': 12
      }
      first_month = match.group(1)
      if first_month in months_ru:
         year = int(match.group(3))
         return date(year, months_ru[first_month], 1)
   
   # 4. Сезоны
   seasons = {'весна': 3, 'лето': 6, 'осень': 9, 'зима': 12}
   for season, month in seasons.items():
      if season in s_lower:
         year_match = re.search(r'\b(20\d{2})\b', s)
         year = int(year_match.group(1)) if year_match else ref_date.year + (1 if month < ref_date.month else 0)
         return date(year, month, 1)
   
   # 5. Очистка от приставок
   for prefix in ['с ', 'со ', 'до ']:
      if s_lower.startswith(prefix):
         s = s[2:].strip()
         break
   
   # 6. Поиск даты начала
   return extract_first_date(s, ref_date)


def extract_first_date(text: str, ref_date: date) -> date:
   """Извлекает первую дату из текста (левая граница интервала или первая дата из списка)."""
   months_ru = {
      'янв': 1, 'январь': 1, 'января': 1, 
      'фев': 2, 'февраль': 2, 'февраля': 2,
      'мар': 3, 'март': 3, 'марта': 3, 
      'апр': 4, 'апрель': 4, 'апреля': 4,
      'май': 5, 'мая': 5, 
      'июн': 6, 'июнь': 6, 'июня': 6, 
      'июл': 7, 'июль': 7, 'июля': 7,
      'авг': 8, 'август': 8, 'августа': 8, 
      'сен': 9, 'сентябрь': 9, 'сентября': 9,
      'окт': 10, 'октябрь': 10, 'октября': 10, 
      'ноя': 11, 'ноябрь': 11, 'ноября': 11,
      'дек': 12, 'декабрь': 12, 'декабря': 12,
   }
   
   # Отдельная обработка для названий месяцев в верхнем регистре (МАЙ, ИЮНЬ и т.д.)
   upper_month_pattern = r'^([А-Я]{3,})$'
   match = re.match(upper_month_pattern, text.strip())
   if match:
      month_name = match.group(1).lower()
      if month_name in months_ru:
         month = months_ru[month_name]
         year = ref_date.year
         if month < ref_date.month:
               year += 1
         return date(year, month, 1)
   
   # Паттерны в порядке приоритета
   patterns = [
      # Ключевые слова начала
      (r'(?:начал[оа]|набор|старт)\s*(?:в группу)?\s*[-–—с]+\s*(\d{1,2})?\s*([а-я]+)\s*(\d{4})?', True),
      (r'(?:начал[оа]|набор|старт)\s*(?:в группу)?\s*[-–—]\s*([а-я]+)\s*(\d{4})?', True),
      # Интервалы
      (r'(\d{1,2})-(\d{1,2})\s+([а-я]+)(?:\s+(\d{4}))?', False),
      (r'(\d{1,2}\.\d{1,2}(?:\.\d{4})?)\s*[-–—]\s*\d{1,2}\.\d{1,2}(?:\.\d{4})?', False),
      (r'(\d{1,2})\s+([а-я]+)(?:\s+(\d{4}))?\s*[-–—]', False),
      # Списки через запятую или пробел
      (r'(\d{1,2}\.\d{1,2}\.\d{4})(?=[,\s]|$)', False),
      (r'(\d{1,2})\s+([а-я]+)(?:\s+(\d{4}))?(?=[,\s]|$)', False),
      (r'(\d{1,2}\.\d{1,2}\.\d{4})', False),
      # Одиночные даты и названия месяцев
      (r'(\d{1,2})\s+([а-я]+)\s+(\d{4})', False),
      (r'(\d{1,2}\.\d{1,2}\.\d{4})', False),
      (r'(\d{1,2})\s+([а-я]+)', False),
      (r'([а-я]+)\s+(\d{4})', False),
      (r'^([а-я]+)$', False),
   ]
   
   for pattern, has_keyword in patterns:
      matches = list(re.finditer(pattern, text, re.I))
      if not matches:
         continue
      
      for match in matches:
         groups = match.groups()
         
         if has_keyword:
               # Обработка с ключевыми словами
               if len(groups) == 3 and groups[0] is None:
                  # "начало - октябрь 2026"
                  month_name, year_str = groups[1], groups[2]
                  if month_name and month_name.lower() in months_ru:
                     month = months_ru[month_name.lower()]
                     year = int(year_str) if year_str else ref_date.year
                     if year == ref_date.year and month < ref_date.month:
                        year += 1
                     return date(year, month, 1)
               elif len(groups) >= 2:
                  # "набор с 15 января 2026"
                  if len(groups) > 2:
                     day_str, month_name, year_str = groups[0], groups[1], groups[2]  
                  else: 
                     day_str, month_name, year_str = None
                  if month_name and month_name.lower() in months_ru:
                     month = months_ru[month_name.lower()]
                     day = int(day_str) if day_str and day_str.isdigit() else 1
                     year = int(year_str) if year_str else ref_date.year
                     if year == ref_date.year and (month < ref_date.month or 
                           (month == ref_date.month and day < ref_date.day)):
                        year += 1
                     return date(year, month, day)
         else:
               # Обычные паттерны дат
               # Обработка просто названия месяца
               if len(groups) == 1 and groups[0] and groups[0].lower() in months_ru:
                  month_name = groups[0].lower()
                  month = months_ru[month_name]
                  year = ref_date.year
                  if month < ref_date.month:
                     year += 1
                  return date(year, month, 1)
               
               result = parse_date_from_match(groups, months_ru, ref_date)
               if result:
                  return result
   
   return None


def parse_date_from_match(groups: tuple, months_ru: dict, ref_date: date) -> date:
   """Парсит matched группы в дату."""
   if not groups:
      return None
   groups = [g for g in groups if g is not None]
   # Формат: ДД.ММ.ГГГГ
   if len(groups) == 1 and '.' in groups[0]:
      parts = groups[0].split('.')
      if len(parts) == 3:
         d, m, y = map(int, parts)
         try:
               return date(y, m, d)
         except ValueError:
               pass
   # Формат: ДД месяц ГГГГ или месяц ГГГГ
   if len(groups) >= 2:
      # Ищем месяц среди групп
      month_idx = next((i for i, g in enumerate(groups) if g and g.lower() in months_ru), None)
      if month_idx is not None:
         month_name = groups[month_idx].lower()
         month = months_ru[month_name]
         # Ищем день
         day = 1
         for i, g in enumerate(groups):
               if i != month_idx and g and g.isdigit() and len(g) <= 2 and 1 <= int(g) <= 31:
                  day = int(g)
                  break
         # Ищем год
         year = ref_date.year
         for g in groups:
               if g and g.isdigit() and len(g) == 4:
                  year = int(g)
                  break
         # Корректировка года для прошедших дат
         if year == ref_date.year:
               try:
                  if date(year, month, day) < ref_date:
                     year += 1
               except ValueError:
                  pass
         try:
               return date(year, month, day)
         except ValueError:
               pass
   return None