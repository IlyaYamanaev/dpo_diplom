def percentile(sorted_list, p):
   """Возвращает p-й перцентиль отсортированного списка."""
   if not sorted_list:
      return 0
   n = len(sorted_list)
   idx = (p / 100) * (n - 1)
   lo = int(idx)
   hi = lo + 1
   frac = idx - lo
   if hi >= n:
      return int(sorted_list[lo])
   return int(sorted_list[lo] + frac * (sorted_list[hi] - sorted_list[lo]))


MONTH_NAMES = {
   1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
   5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
   9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
}


def build_analytics(courses):
   """Полный расчёт аналитики по списку курсов."""
   if not courses:
      return {}

   prices = []
   hours_list = []
   price_per_hour_list = []
   formats_count = {}
   types_count = {}
   month_count = {}
   org_count = {}

   for c in courses:
      # Цена
      p = None
      try:
         raw = (c.price or '').strip().replace(' ', '')
         if raw and raw.lstrip('-').isdigit():
            p = int(raw)
            if p > 0:
               prices.append(p)
      except Exception:
         pass

      # Часы
      h = None
      try:
         raw_h = (c.duration_in_hours or '').strip()
         if raw_h and raw_h.lstrip('-').isdigit():
            h = int(raw_h)
            if h > 0:
               hours_list.append(h)
      except Exception:
         pass

      # Цена за час
      if p and h and h > 0:
         price_per_hour_list.append(p / h)

      # Форматы
      if c.format:
         formats_count[c.format] = formats_count.get(c.format, 0) + 1

      # Типы
      if c.course_type:
         types_count[c.course_type] = types_count.get(c.course_type, 0) + 1

      # Месяцы запуска
      if c.norm_date:
         m = c.norm_date.month
         month_count[m] = month_count.get(m, 0) + 1

      # Организации
      if c.organization_id:
         name = c.organization.name if c.organization else f'Орг. {c.organization_id}'
         if c.organization_id not in org_count:
            org_count[c.organization_id] = {'id': c.organization_id, 'name': name, 'count': 0}
         org_count[c.organization_id]['count'] += 1

   total = len(courses)

   #  Цены 
   sp = sorted(prices)
   avg_price    = int(sum(sp) / len(sp)) if sp else 0
   median_price = percentile(sp, 50)
   min_price    = sp[0] if sp else 0
   max_price    = sp[-1] if sp else 0
   q1_price     = percentile(sp, 25)
   q3_price     = percentile(sp, 75)

   #  Цена за час 
   avg_price_per_hour    = int(sum(price_per_hour_list) / len(price_per_hour_list)) if price_per_hour_list else 0
   median_price_per_hour = int(percentile(sorted(price_per_hour_list), 50)) if price_per_hour_list else 0

   #  Часы 
   sh = sorted(hours_list)
   avg_hours    = int(sum(sh) / len(sh)) if sh else 0
   median_hours = percentile(sh, 50)
   q1_hours     = percentile(sh, 25)
   q3_hours     = percentile(sh, 75)
   typical_range = f'{q1_hours}–{q3_hours} ак.ч.' if q1_hours and q3_hours else ''

   #  Форматы: полное распределение 
   formats_dist = [
      (k, round(v / total * 100))
      for k, v in sorted(formats_count.items(), key=lambda x: -x[1])
   ]
   top_format = formats_dist[0][0] if formats_dist else '-'

   #  Типы: полное распределение 
   types_dist = [
      (k, round(v / total * 100))
      for k, v in sorted(types_count.items(), key=lambda x: -x[1])
   ]
   top_type = types_dist[0][0] if types_dist else '-'

   #  Месяцы запуска 
   launch_months = []
   if month_count and len(month_count) >= 2:
      max_m = max(month_count.values())
      sorted_months = sorted(month_count.items(), key=lambda x: -x[1])[:5]
      launch_months = [
         (MONTH_NAMES[m], round(cnt / sum(month_count.values()) * 100))
         for m, cnt in sorted_months
      ]

   #  Организации для фильтра 
   org_list = sorted(org_count.values(), key=lambda x: -x['count'])

   #  Инсайты 
   insights = []

   if total >= 5:
      # Конкуренция
      if total >= 70:
         insights.append({'icon': '🔥', 'type': 'warn', 'text': f'Высококонкурентная категория - {total} программ на рынке'})
      elif total <= 20:
         insights.append({'icon': '💡', 'type': 'ok', 'text': f'Малоконкурентная ниша - всего {total} программ'})

      # Форматы
      if formats_dist:
         top_fmt, top_pct = formats_dist[0]
         if top_pct > 60:
            insights.append({'icon': '📺', 'type': '', 'text': f'Рынок доминирован форматом «{top_fmt}» ({top_pct}%)'})
         # Дефицит очного
         offline_pct = next((pct for fmt, pct in formats_dist if 'очн' in fmt.lower()), 0)
         if offline_pct < 15 and total >= 10:
            insights.append({'icon': '🏫', 'type': 'ok', 'text': f'В категории мало очных программ ({offline_pct}%) - свободная ниша'})

      # Цены
      if avg_price and min_price:
         if min_price > 80000:
            insights.append({'icon': '💰', 'type': 'warn', 'text': f'Нет курсов дешевле {min_price:,} ₽ - рынок дорогой'.replace(',', ' ')})
         if max_price > avg_price * 3:
            insights.append({'icon': '📊', 'type': '', 'text': 'Большой разброс цен - рынок сегментирован'})

      # Часы
      if avg_hours:
         if avg_hours < 36:
            insights.append({'icon': '⚡', 'type': 'ok', 'text': f'Большинство программ короткие (≈{avg_hours} ч) - есть спрос на глубокие курсы'})
         elif avg_hours > 200:
            insights.append({'icon': '📚', 'type': '', 'text': f'Рынок ориентирован на длинные программы (≈{avg_hours} ч)'})

   insights = insights[:5]

   return {
      'count':                  total,
      'avg_price':              avg_price,
      'median_price':           median_price,
      'min_price':              min_price,
      'max_price':              max_price,
      'q1_price':               q1_price,
      'q3_price':               q3_price,
      'avg_price_per_hour':     avg_price_per_hour,
      'median_price_per_hour':  median_price_per_hour,
      'avg_hours':              avg_hours,
      'median_hours':           median_hours,
      'q1_hours':               q1_hours,
      'q3_hours':               q3_hours,
      'typical_range':          typical_range,
      'formats_dist':           formats_dist,
      'top_format':             top_format,
      'types_dist':             types_dist,
      'top_type':               top_type,
      'launch_months':          launch_months,
      'org_list':               org_list,
      'insights':               insights,
      'all_formats':            [f for f, _ in formats_dist],
      'all_types':              [t for t, _ in types_dist],
   }



