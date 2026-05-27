from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload
from models import (
   db,
   app,
   Organization,
   Department,
   Course,
   Category,
   Subcategory,
   rel_course_category,
   rel_course_subcategory,
   User,
   FavoriteCourse,
   DraftCourse,
   UserDraft
)


# ─────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────

def get_current_user():
   """Возвращает текущего пользователя из сессии или None."""
   user_id = session.get('user_id')
   if user_id:
      return User.query.get(user_id)
   return None


def get_categories_with_subcats():
   """Возвращает список категорий с подкатегориями и счётчиками курсов."""
   all_categories = Category.query.all()
   result = []
   for category in all_categories:
      subcategories_list = Subcategory.query.filter_by(parent_category_id=category.id).all()
      course_count = db.session.query(rel_course_category).filter_by(category_id=category.id).count()
      result.append({
         'id': category.id,
         'name': category.name,
         'course_count': course_count,
         'subcategories': [
               {
                  'id': subcat.id,
                  'name': subcat.name,
                  'course_count': db.session.query(rel_course_subcategory).filter_by(subcategory_id=subcat.id).count()
               }
               for subcat in subcategories_list
         ]
      })
   return result


def apply_course_filters(query):
   """Применяет GET-параметры фильтрации к запросу курсов."""
   org = request.args.getlist('organization')
   if org:
      query = query.filter(Course.organization_id.in_(org))

   fmt = request.args.getlist('format')
   if fmt:
      query = query.filter(Course.format.in_(fmt))

   lang = request.args.getlist('language')
   if lang:
      query = query.filter(Course.language.in_(lang))

   ctype = request.args.getlist('course_type')
   if ctype:
      query = query.filter(Course.course_type.in_(ctype))

   categories = request.args.getlist('category')
   if categories:
      category_ids = [int(c) for c in categories if c.isdigit()]
      if category_ids:
         query = query.filter(
               Course.id.in_(
                  db.session.query(rel_course_category.c.course_id).filter(
                     rel_course_category.c.category_id.in_(category_ids)
                  )
               )
         )

   subcategories = request.args.getlist('subcategory')
   if subcategories:
      subcategory_ids = [int(sc) for sc in subcategories if sc.isdigit()]
      if subcategory_ids:
         query = query.filter(
               Course.id.in_(
                  db.session.query(rel_course_subcategory.c.course_id).filter(
                     rel_course_subcategory.c.subcategory_id.in_(subcategory_ids)
                  )
               )
         )

   search_query = request.args.get('search', '')
   if search_query:
      query = query.filter(Course.title.ilike(f'%{search_query}%'))

   price_min = request.args.get('price_min', '')
   price_max = request.args.get('price_max', '')
   if price_min and price_min.isdigit():
      query = query.filter(Course.price.cast(db.Integer) >= int(price_min))
   if price_max and price_max.isdigit():
      query = query.filter(Course.price.cast(db.Integer) <= int(price_max))

   hours_min = request.args.get('hours_min', '')
   hours_max = request.args.get('hours_max', '')
   if hours_min and hours_min.isdigit():
      query = query.filter(Course.duration_in_hours.cast(db.Integer) >= int(hours_min))
   if hours_max and hours_max.isdigit():
      query = query.filter(Course.duration_in_hours.cast(db.Integer) <= int(hours_max))

   return query


def get_price_hours_bounds():
   min_price = db.session.query(func.min(Course.price.cast(db.Integer))).scalar() or 0
   max_price = db.session.query(func.max(Course.price.cast(db.Integer))).scalar() or 1000000
   min_hours = db.session.query(func.min(Course.duration_in_hours.cast(db.Integer))).scalar() or 0
   max_hours = db.session.query(func.max(Course.duration_in_hours.cast(db.Integer))).scalar() or 1000
   return min_price, max_price, min_hours, max_hours


def get_favorite_ids(user):
   if not user:
      return set()
   favs = FavoriteCourse.query.filter_by(user_id=user.id).all()
   return {f.course_id for f in favs}


# ─────────────────────────────────────────────
# ГЛАВНАЯ СТРАНИЦА
# ─────────────────────────────────────────────

@app.route('/')
def index():
   query = Course.query.options(
      joinedload(Course.organization),
      joinedload(Course.department),
      selectinload(Course.categories),
      selectinload(Course.subcategories)
   )
   query = apply_course_filters(query)
   query = query.order_by(func.rand())
   courses = query.all()

   min_price, max_price, min_hours, max_hours = get_price_hours_bounds()

   organizations = Organization.query.all()
   formats = db.session.query(Course.format).distinct()
   languages = db.session.query(Course.language).distinct()
   types = db.session.query(Course.course_type).distinct()
   categories = get_categories_with_subcats()

   current_user = get_current_user()
   favorite_ids = get_favorite_ids(current_user)

   return render_template(
      'index.html',
      courses=courses,
      organizations=organizations,
      formats=formats,
      languages=languages,
      types=types,
      categories=categories,
      min_price=min_price,
      max_price=max_price,
      min_hours=min_hours,
      max_hours=max_hours,
      current_price_min=request.args.get('price_min', ''),
      current_price_max=request.args.get('price_max', ''),
      current_hours_min=request.args.get('hours_min', ''),
      current_hours_max=request.args.get('hours_max', ''),
      current_user=current_user,
      favorite_ids=favorite_ids,
   )


# ─────────────────────────────────────────────
# СТРАНИЦА КУРСА
# ─────────────────────────────────────────────

@app.route('/course/<int:id>')
def course(id):
   course_obj = Course.query.options(
      joinedload(Course.organization),
      joinedload(Course.department),
      selectinload(Course.categories),
      selectinload(Course.subcategories)
   ).get_or_404(id)

   current_user = get_current_user()
   is_favorite = False
   if current_user:
      is_favorite = FavoriteCourse.query.filter_by(user_id=current_user.id, course_id=id).first() is not None

   return render_template('course.html', course=course_obj, current_user=current_user,
                        is_favorite=is_favorite, is_draft=False)


# ─────────────────────────────────────────────
# СТРАНИЦА ЧЕРНОВИКА
# ─────────────────────────────────────────────

@app.route('/draft/<int:id>')
def draft_view(id):
   current_user = get_current_user()
   if not current_user:
      return redirect(url_for('index'))

   draft = DraftCourse.query.get_or_404(id)
   # Проверяем, что это черновик текущего пользователя
   link = UserDraft.query.filter_by(user_id=current_user.id, draft_course_id=id).first()
   if not link:
      return redirect(url_for('index'))

   return render_template('course.html', course=draft, current_user=current_user,
                        is_favorite=False, is_draft=True)


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ
# ─────────────────────────────────────────────

@app.route('/register', methods=['POST'])
def register():
   data = request.get_json()
   login = (data.get('login') or '').strip()
   password = (data.get('password') or '').strip()

   if not login or not password:
      return jsonify({'success': False, 'error': 'Заполните все поля'})

   if User.query.filter_by(login=login).first():
      return jsonify({'success': False, 'error': 'Пользователь с таким логином уже существует'})

   user = User(login=login)
   user.set_password(password)
   db.session.add(user)
   db.session.commit()

   session['user_id'] = user.id
   return jsonify({'success': True, 'login': user.login})


@app.route('/login', methods=['POST'])
def login():
   data = request.get_json()
   login_val = (data.get('login') or '').strip()
   password = (data.get('password') or '').strip()

   user = User.query.filter_by(login=login_val).first()
   if not user or not user.check_password(password):
      return jsonify({'success': False, 'error': 'Неверный логин или пароль'})

   session['user_id'] = user.id
   return jsonify({'success': True, 'login': user.login})


@app.route('/logout', methods=['POST'])
def logout():
   session.pop('user_id', None)
   return jsonify({'success': True})


# ─────────────────────────────────────────────
# ИЗБРАННОЕ
# ─────────────────────────────────────────────

@app.route('/favorites/toggle', methods=['POST'])
def toggle_favorite():
   current_user = get_current_user()
   if not current_user:
      return jsonify({'success': False, 'require_auth': True})

   data = request.get_json()
   course_id = data.get('course_id')

   existing = FavoriteCourse.query.filter_by(user_id=current_user.id, course_id=course_id).first()
   if existing:
      db.session.delete(existing)
      db.session.commit()
      return jsonify({'success': True, 'is_favorite': False})
   else:
      fav = FavoriteCourse(user_id=current_user.id, course_id=course_id)
      db.session.add(fav)
      db.session.commit()
      return jsonify({'success': True, 'is_favorite': True})


@app.route('/favorites')
def favorites():
   current_user = get_current_user()
   if not current_user:
      return redirect(url_for('index'))

   fav_records = FavoriteCourse.query.filter_by(user_id=current_user.id).all()
   course_ids = [f.course_id for f in fav_records]

   search_query = request.args.get('search', '')
   query = Course.query.options(
      joinedload(Course.organization),
      joinedload(Course.department),
      selectinload(Course.categories),
      selectinload(Course.subcategories)
   ).filter(Course.id.in_(course_ids))

   if search_query:
      query = query.filter(Course.title.ilike(f'%{search_query}%'))

   courses = query.all()
   favorite_ids = set(course_ids)

   return render_template('favorites.html', courses=courses, current_user=current_user,
                        favorite_ids=favorite_ids, search_query=search_query)


# ─────────────────────────────────────────────
# CREATOR MODE
# ─────────────────────────────────────────────

@app.route('/creator')
def creator():
   current_user = get_current_user()
   if not current_user:
      return redirect(url_for('index'))

   categories = get_categories_with_subcats()

   # Фильтрация курсов по выбранной категории/подкатегории
   query = Course.query.options(
      joinedload(Course.organization),
      joinedload(Course.department),
      selectinload(Course.categories),
      selectinload(Course.subcategories)
   )

   selected_category = request.args.get('category', '')
   selected_subcategory = request.args.get('subcategory', '')

   if selected_subcategory and selected_subcategory.isdigit():
      query = query.filter(
         Course.id.in_(
               db.session.query(rel_course_subcategory.c.course_id).filter(
                  rel_course_subcategory.c.subcategory_id == int(selected_subcategory)
               )
         )
      )
   elif selected_category and selected_category.isdigit():
      query = query.filter(
         Course.id.in_(
               db.session.query(rel_course_category.c.course_id).filter(
                  rel_course_category.c.category_id == int(selected_category)
               )
         )
      )

   courses = query.order_by(func.rand()).all()

   # Аналитика
   analytics = {}
   if courses:
      prices = []
      hours_list = []
      formats_count = {}
      types_count = {}

      for c in courses:
         try:
               p = int(c.price) if c.price and c.price.isdigit() else None
               if p is not None:
                  prices.append(p)
         except Exception:
               pass
         try:
               h = int(c.duration_in_hours) if c.duration_in_hours and c.duration_in_hours.isdigit() else None
               if h is not None:
                  hours_list.append(h)
         except Exception:
               pass
         if c.format:
               formats_count[c.format] = formats_count.get(c.format, 0) + 1
         if c.course_type:
               types_count[c.course_type] = types_count.get(c.course_type, 0) + 1

      if prices:
         avg_price = int(sum(prices) / len(prices))
         sorted_prices = sorted(prices)
         n = len(sorted_prices)
         if n % 2 == 0:
               median_price = int((sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2)
         else:
               median_price = sorted_prices[n // 2]
      else:
         avg_price = median_price = 0

      avg_hours = int(sum(hours_list) / len(hours_list)) if hours_list else 0

      top_format = max(formats_count, key=formats_count.get) if formats_count else '—'
      top_format_pct = int(formats_count[top_format] / len(courses) * 100) if formats_count else 0
      other_formats = [(k, int(v / len(courses) * 100)) for k, v in sorted(formats_count.items(), key=lambda x: -x[1]) if k != top_format]

      top_type = max(types_count, key=types_count.get) if types_count else '—'
      top_type_pct = int(types_count[top_type] / len(courses) * 100) if types_count else 0
      other_types = [(k, int(v / len(courses) * 100)) for k, v in sorted(types_count.items(), key=lambda x: -x[1]) if k != top_type]

      analytics = {
         'count': len(courses),
         'avg_price': avg_price,
         'median_price': median_price,
         'avg_hours': avg_hours,
         'top_format': top_format,
         'top_format_pct': top_format_pct,
         'other_formats': other_formats[:3],
         'top_type': top_type,
         'top_type_pct': top_type_pct,
         'other_types': other_types[:3],
         'all_formats': list(formats_count.keys()),
         'all_types': list(types_count.keys()),
      }

   selected_cat_name = ''
   if selected_subcategory and selected_subcategory.isdigit():
      sub = Subcategory.query.get(int(selected_subcategory))
      if sub:
         selected_cat_name = sub.name
   elif selected_category and selected_category.isdigit():
      cat = Category.query.get(int(selected_category))
      if cat:
         selected_cat_name = cat.name

   return render_template('creator.html',
                        current_user=current_user,
                        categories=categories,
                        courses=courses,
                        analytics=analytics,
                        selected_category=selected_category,
                        selected_subcategory=selected_subcategory,
                        selected_cat_name=selected_cat_name)


# ─────────────────────────────────────────────
# ЧЕРНОВИКИ
# ─────────────────────────────────────────────

@app.route('/drafts')
def drafts():
   current_user = get_current_user()
   if not current_user:
      return redirect(url_for('index'))

   search_query = request.args.get('search', '')
   user_draft_links = UserDraft.query.filter_by(user_id=current_user.id).all()
   draft_ids = [ud.draft_course_id for ud in user_draft_links]

   query = DraftCourse.query.filter(DraftCourse.id.in_(draft_ids))
   if search_query:
      query = query.filter(DraftCourse.title.ilike(f'%{search_query}%'))

   draft_courses = query.all()
   return render_template('drafts.html', drafts=draft_courses, current_user=current_user,
                        search_query=search_query)


@app.route('/drafts/create', methods=['POST'])
def create_draft():
   current_user = get_current_user()
   if not current_user:
      return jsonify({'success': False, 'error': 'Не авторизован'})

   data = request.get_json()

   draft = DraftCourse(
      title=data.get('title') or 'Без названия',
      price=data.get('price'),
      format=data.get('format'),
      course_type=data.get('course_type'),
      duration_in_hours=data.get('duration_in_hours'),
      duration=data.get('duration'),
      schedule=data.get('schedule'),
      language='Русский',
   )
   db.session.add(draft)
   db.session.flush()

   link = UserDraft(user_id=current_user.id, draft_course_id=draft.id)
   db.session.add(link)
   db.session.commit()

   return jsonify({'success': True, 'draft_id': draft.id})


@app.route('/drafts/delete/<int:id>', methods=['POST'])
def delete_draft(id):
   current_user = get_current_user()
   if not current_user:
      return jsonify({'success': False})

   link = UserDraft.query.filter_by(user_id=current_user.id, draft_course_id=id).first()
   if not link:
      return jsonify({'success': False})

   draft = DraftCourse.query.get(id)
   db.session.delete(link)
   if draft:
      db.session.delete(draft)
   db.session.commit()

   return jsonify({'success': True})


# ─────────────────────────────────────────────
# ФИЛЬТРЫ ШАБЛОНОВ
# ─────────────────────────────────────────────

@app.template_filter('delete_param')
def delete_param(params, param_name, param_value):
   new_params = params.copy()
   if param_name in new_params:
      values = new_params[param_name]
      if isinstance(values, list):
         new_values = [v for v in values if v != param_value]
         if new_values:
               new_params[param_name] = new_values
         else:
               del new_params[param_name]
      else:
         if values == param_value:
               del new_params[param_name]
   return new_params


@app.template_filter('remove_param')
def remove_param(params, param_name):
   new_params = params.copy()
   if param_name in new_params:
      del new_params[param_name]
   return new_params


if __name__ == '__main__':
   with app.app_context():
      db.create_all()
   app.run(debug=True)
