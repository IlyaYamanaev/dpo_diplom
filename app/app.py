from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from sqlalchemy import Integer, case, cast, func
from sqlalchemy.orm import joinedload, selectinload
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
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
from analytical_functions import build_analytics
from weekly_update import start_scheduler



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
      
      
   # Фильтр по дате (несколько чекбоксов объединяются через OR)
   # Фильтр по дате (несколько чекбоксов объединяются через OR)
   date_options = request.args.getlist('date_option')
   if date_options:
      today = date.today()
      conditions = []
      for opt in date_options:
         if opt == 'no_date':
               conditions.append(Course.norm_date.is_(None))
         elif opt == 'has_date':
               conditions.append(Course.norm_date.isnot(None))
         elif opt == 'past':
               conditions.append(Course.norm_date < today)
         elif opt == '2weeks':
               end_date = today + timedelta(days=14)
               conditions.append(Course.norm_date.between(today, end_date))
         elif opt == '1month':
               end_date = today + relativedelta(months=1)
               conditions.append(Course.norm_date.between(today, end_date))
         elif opt == '3months':
               end_date = today + relativedelta(months=3)
               conditions.append(Course.norm_date.between(today, end_date))
         elif opt == '6months':
               end_date = today + relativedelta(months=6)
               conditions.append(Course.norm_date.between(today, end_date))
      if conditions:
         from sqlalchemy import or_
         query = query.filter(or_(*conditions))

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
   
   # Сортировка
   sort_param = request.args.get('sort', '')
   if sort_param == 'title_asc':
      query = query.order_by(Course.title.asc())
   elif sort_param == 'title_desc':
      query = query.order_by(Course.title.desc())
   elif sort_param == 'price_asc':
      query = query.order_by(
         case((Course.price == None, 1), else_=0),
         cast(Course.price, Integer).asc()
      )
   elif sort_param == 'price_desc':
      query = query.order_by(
         case((Course.price == None, 1), else_=0),
         cast(Course.price, Integer).desc()
      )
   elif sort_param == 'hours_asc':
      query = query.order_by(
         case((Course.duration_in_hours == None, 1), else_=0),
         cast(Course.duration_in_hours, Integer).asc()
      )
   elif sort_param == 'hours_desc':
      query = query.order_by(
         case((Course.duration_in_hours == None, 1), else_=0),
         cast(Course.duration_in_hours, Integer).desc()
      )
   elif sort_param == 'date_asc':
      # Только будущие курсы, от ближайших к дальним
      query = query.filter(Course.norm_date >= func.current_date()).order_by(Course.norm_date.asc())
   else:
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
   # Перенаправляем на страницу редактирования
   return redirect(url_for('edit', id=id))


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
# API: АНАЛИТИКА КАТЕГОРИИ (для draft_edit)
# ─────────────────────────────────────────────
@app.route('/api/category_analytics/<int:cat_id>')
def api_category_analytics(cat_id):
   courses = Course.query.filter(
      Course.id.in_(
         db.session.query(rel_course_category.c.course_id).filter(
            rel_course_category.c.category_id == cat_id
         )
      )
   ).all()

   if not courses:
      return jsonify({'success': False, 'analytics': {}})

   a = build_analytics(courses)
   return jsonify({
      'success': True,
      'analytics': {
         'medianPrice':     a.get('median_price', 0),
         'avgPrice':        a.get('avg_price', 0),
         'q1Price':         a.get('q1_price', 0),
         'q3Price':         a.get('q3_price', 0),
         'q1Hours':         a.get('q1_hours', 0),
         'q3Hours':         a.get('q3_hours', 0),
         'avgPricePerHour': a.get('avg_price_per_hour', 0),
         'topFormat':       a.get('top_format', ''),
         'count':           a.get('count', 0),
      }
   })

# ─────────────────────────────────────────────
# СТРАНИЦА СОЗДАТЕЛЯ КУРСА
# ─────────────────────────────────────────────
@app.route('/creator')
def creator():
   current_user = get_current_user()
   if not current_user:
      return redirect(url_for('index'))

   categories = get_categories_with_subcats()

   query = Course.query.options(
      joinedload(Course.organization),
      joinedload(Course.department),
      selectinload(Course.categories),
      selectinload(Course.subcategories)
   )

   selected_category    = request.args.get('category', '')
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

   sort_param = request.args.get('sort', '')
   if sort_param == 'title_asc':
      query = query.order_by(Course.title.asc())
   elif sort_param == 'title_desc':
      query = query.order_by(Course.title.desc())
   elif sort_param == 'price_asc':
      query = query.order_by(case((Course.price == None, 1), else_=0), cast(Course.price, Integer).asc())
   elif sort_param == 'price_desc':
      query = query.order_by(case((Course.price == None, 1), else_=0), cast(Course.price, Integer).desc())
   elif sort_param == 'hours_asc':
      query = query.order_by(case((Course.duration_in_hours == None, 1), else_=0), cast(Course.duration_in_hours, Integer).asc())
   elif sort_param == 'hours_desc':
      query = query.order_by(case((Course.duration_in_hours == None, 1), else_=0), cast(Course.duration_in_hours, Integer).desc())
   elif sort_param == 'date_asc':
      query = query.filter(Course.norm_date >= func.current_date()).order_by(Course.norm_date.asc())
   else:
      query = query.order_by(func.rand())

   courses = query.all()

   analytics = build_analytics(courses) if courses else {}

   selected_cat_name = ''
   if selected_subcategory and selected_subcategory.isdigit():
      sub = Subcategory.query.get(int(selected_subcategory))
      if sub:
         selected_cat_name = sub.name
   elif selected_category and selected_category.isdigit():
      cat = Category.query.get(int(selected_category))
      if cat:
         selected_cat_name = cat.name

   # Глобальные форматы и типы из всей базы (не только из текущей категории)
   global_formats = sorted(set(
      c.format for c in Course.query.with_entities(Course.format).filter(Course.format != None).all()
      if c.format and c.format.strip()
   ))
   global_types = sorted(set(
      c.course_type for c in Course.query.with_entities(Course.course_type).filter(Course.course_type != None).all()
      if c.course_type and c.course_type.strip()
   ))

   return render_template('creator.html',
                          current_user=current_user,
                          categories=categories,
                          courses=courses,
                          analytics=analytics,
                          selected_category=selected_category,
                          selected_subcategory=selected_subcategory,
                          selected_cat_name=selected_cat_name,
                          global_formats=global_formats,
                          global_types=global_types)


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

   cat_id = data.get('category_id')
   sub_id = data.get('subcategory_id')

   draft = DraftCourse(
      title=data.get('title') or 'Без названия',
      price=data.get('price') or None,
      format=data.get('format') or None,
      course_type=data.get('course_type') or None,
      duration_in_hours=data.get('duration_in_hours') or None,
      duration=data.get('duration') or None,
      schedule=data.get('schedule') or None,
      date=data.get('date') or None,
      language='Русский',
      description=data.get('description') or None,
      competitiveness_score=data.get('competitiveness_score') or None,
      has_document=bool(data.get('has_document')),
      has_installment=bool(data.get('has_installment')),
      has_date=bool(data.get('has_date')),
      notes=data.get('notes') or None,
      category_id=int(cat_id) if cat_id else None,
      subcategory_id=int(sub_id) if sub_id else None,
   )
   db.session.add(draft)
   db.session.flush()

   link = UserDraft(user_id=current_user.id, draft_course_id=draft.id)
   db.session.add(link)
   db.session.commit()

   return jsonify({'success': True, 'draft_id': draft.id})


@app.route('/draft/edit/<int:id>', methods=['GET'])
def draft_edit(id):
   current_user = get_current_user()
   if not current_user:
      return redirect(url_for('index'))

   draft = DraftCourse.query.get_or_404(id)
   link = UserDraft.query.filter_by(user_id=current_user.id, draft_course_id=id).first()
   if not link:
      return redirect(url_for('drafts'))

   categories = get_categories_with_subcats()

   global_formats = sorted(set(
      c.format for c in Course.query.with_entities(Course.format).filter(Course.format != None).all()
      if c.format and c.format.strip()
   ))
   global_types = sorted(set(
      c.course_type for c in Course.query.with_entities(Course.course_type).filter(Course.course_type != None).all()
      if c.course_type and c.course_type.strip()
   ))

   return render_template('edit.html',
                          draft=draft,
                          current_user=current_user,
                          categories=categories,
                          global_formats=global_formats,
                          global_types=global_types)


@app.route('/draft/update/<int:id>', methods=['POST'])
def draft_update(id):
   current_user = get_current_user()
   if not current_user:
      return jsonify({'success': False, 'error': 'Не авторизован'})

   link = UserDraft.query.filter_by(user_id=current_user.id, draft_course_id=id).first()
   if not link:
      return jsonify({'success': False, 'error': 'Доступ запрещён'})

   draft = DraftCourse.query.get_or_404(id)
   data = request.get_json()

   if data.get('title'):
      draft.title = data['title']
   cat_id = data.get('category_id')
   sub_id = data.get('subcategory_id')
   if cat_id is not None:
      draft.category_id = int(cat_id) if cat_id else None
   if sub_id is not None:
      draft.subcategory_id = int(sub_id) if sub_id else None
   draft.price               = data.get('price') or None 
   draft.format              = data.get('format') or None
   draft.course_type         = data.get('course_type') or None
   draft.duration_in_hours   = data.get('duration_in_hours') or None
   draft.duration            = data.get('duration') or None
   draft.schedule            = data.get('schedule') or None
   draft.date                = data.get('date') or None
   draft.description         = data.get('description') or None
   draft.admission_requirements = data.get('admission_requirements') or None
   draft.language            = data.get('language') or 'Русский'
   draft.document            = data.get('document') or None
   draft.has_document        = bool(data.get('has_document'))
   draft.has_installment     = bool(data.get('has_installment'))
   draft.has_date            = bool(data.get('has_date'))
   draft.notes               = data.get('notes') or None
   if data.get('competitiveness_score') is not None:
      draft.competitiveness_score = data.get('competitiveness_score')

   db.session.commit()
   return jsonify({'success': True})


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

   start_scheduler()

   app.run(
      host='0.0.0.0',
      port=5000,
      debug=False
   )