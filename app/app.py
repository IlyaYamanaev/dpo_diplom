from flask import Flask, render_template, request, jsonify, redirect, url_for
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
   rel_course_subcategory
)


@app.route('/')
def index():
   # Загружаем курсы с категориями и подкатегориями
   query = Course.query.options(
      joinedload(Course.organization),
      joinedload(Course.department),
      selectinload(Course.categories),  # Загружаем категории
      selectinload(Course.subcategories)  # Загружаем подкатегории
   )

   # фильтры
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
   
   # Фильтры по категориям
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
   
   # Фильтры по подкатегориям
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
         
   # Фильтр по названию
   search_query = request.args.get('search', '')
   if search_query:
      query = query.filter(Course.title.ilike(f'%{search_query}%'))
      
   # Фильтр по цене
   price_min = request.args.get('price_min', '')
   price_max = request.args.get('price_max', '')
   if price_min and price_min.isdigit():
        query = query.filter(Course.price.cast(db.Integer) >= int(price_min))
   if price_max and price_max.isdigit():
        query = query.filter(Course.price.cast(db.Integer) <= int(price_max))
   
   # Фильтр по академическим часам
   hours_min = request.args.get('hours_min', '')
   hours_max = request.args.get('hours_max', '')
   if hours_min and hours_min.isdigit():
        query = query.filter(Course.duration_in_hours.cast(db.Integer) >= int(hours_min))
   if hours_max and hours_max.isdigit():
        query = query.filter(Course.duration_in_hours.cast(db.Integer) <= int(hours_max))
   
   # Случайный порядок
   query = query.order_by(func.rand())
   
   courses = query.all()
   
   # Минимальные и максимальные значения для фильтров
   min_price = db.session.query(func.min(Course.price.cast(db.Integer))).scalar() or 0
   max_price = db.session.query(func.max(Course.price.cast(db.Integer))).scalar() or 1000000
   min_hours = db.session.query(func.min(Course.duration_in_hours.cast(db.Integer))).scalar() or 0
   max_hours = db.session.query(func.max(Course.duration_in_hours.cast(db.Integer))).scalar() or 1000
   
   # Текущие значения фильтров
   current_price_min = request.args.get('price_min', '')
   current_price_max = request.args.get('price_max', '')
   current_hours_min = request.args.get('hours_min', '')
   current_hours_max = request.args.get('hours_max', '')

   # Получаем значения для фильтров
   organizations = Organization.query.all()
   formats = db.session.query(Course.format).distinct()
   languages = db.session.query(Course.language).distinct()
   types = db.session.query(Course.course_type).distinct()
   
   # Получаем категории с подкатегориями
   all_categories = Category.query.all()
   
   categories_with_subcats = []
   for category in all_categories:
      # Получаем подкатегории
      subcategories_list = Subcategory.query.filter_by(parent_category_id=category.id).all()
      
      # Подсчитываем количество курсов
      course_count = db.session.query(rel_course_category).filter_by(category_id=category.id).count()
      
      categories_with_subcats.append({
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
   

   return render_template(
      'index.html',
      courses=courses,
      organizations=organizations,
      formats=formats,
      languages=languages,
      types=types,
      categories=categories_with_subcats,
      min_price=min_price,
      max_price=max_price,
      min_hours=min_hours,
      max_hours=max_hours,
      current_price_min=current_price_min,
      current_price_max=current_price_max,
      current_hours_min=current_hours_min,
      current_hours_max=current_hours_max
   )


@app.route('/course/<int:id>')
def course(id):
   course = Course.query.options(
      joinedload(Course.organization),
      joinedload(Course.department),
      selectinload(Course.categories),
      selectinload(Course.subcategories)
   ).get_or_404(id)

   return render_template('course.html', course=course)

@app.template_filter('delete_param')
def delete_param(params, param_name, param_value):
    """Удаляет конкретное значение параметра из словаря GET-параметров"""
    new_params = params.copy()
    if param_name in new_params:
        values = new_params[param_name]
        if isinstance(values, list):
            # Удаляем только конкретное значение
            new_values = [v for v in values if v != param_value]
            if new_values:
                new_params[param_name] = new_values
            else:
                del new_params[param_name]
        else:
            # Если одно значение и оно совпадает - удаляем параметр
            if values == param_value:
                del new_params[param_name]
    return new_params

@app.template_filter('remove_param')
def remove_param(params, param_name):
    """Удаляет параметр целиком из словаря GET-параметров"""
    new_params = params.copy()
    if param_name in new_params:
        del new_params[param_name]
    return new_params


if __name__ == '__main__':
   with app.app_context():
      db.create_all()
   app.run(debug=True)