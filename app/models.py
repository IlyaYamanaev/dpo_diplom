from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:zxcvbnasdqwe@localhost/buff_dpo_db'
db = SQLAlchemy(app)


class Organization(db.Model):
   __tablename__ = 'organizations'
   id = db.Column(db.Integer, primary_key=True)
   name = db.Column(db.String)

class Department(db.Model):
   __tablename__ = 'departments'
   id = db.Column(db.Integer, primary_key=True)
   name = db.Column(db.String)

class Course(db.Model):
   __tablename__ = 'dpo_courses'
   id = db.Column(db.Integer, primary_key=True)
   title = db.Column(db.String)
   price = db.Column(db.String)
   format = db.Column(db.String)
   url = db.Column(db.String)
   duration = db.Column(db.String)
   duration_in_hours = db.Column(db.String)
   language = db.Column(db.String)
   document = db.Column(db.String)
   course_type = db.Column(db.String)
   organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
   department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
   
   organization = db.relationship('Organization', backref='courses')
   department = db.relationship('Department', backref='courses')
   
   categories = db.relationship('Category', secondary='rel_course_category', viewonly=False)
   subcategories = db.relationship('Subcategory', secondary='rel_course_subcategory', viewonly=False)

class Category(db.Model):
   __tablename__ = 'categories'
   id = db.Column(db.Integer, primary_key=True)
   name = db.Column(db.String(255), nullable=False)
   
   # Добавьте обратную связь
   courses = db.relationship('Course', secondary='rel_course_category', viewonly=False)

class Subcategory(db.Model):
   __tablename__ = 'subcategories'
   id = db.Column(db.Integer, primary_key=True)
   name = db.Column(db.String(255), nullable=False)
   parent_category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
   
   # Добавьте обратную связь
   category = db.relationship('Category', backref='subcategories')
   courses = db.relationship('Course', secondary='rel_course_subcategory', viewonly=False)

# Связующие таблицы (без моделей)
rel_course_category = db.Table('rel_course_category',
   db.Column('course_id', db.Integer, db.ForeignKey('dpo_courses.id'), primary_key=True),
   db.Column('category_id', db.Integer, db.ForeignKey('categories.id'), primary_key=True)
)

rel_course_subcategory = db.Table('rel_course_subcategory',
   db.Column('course_id', db.Integer, db.ForeignKey('dpo_courses.id'), primary_key=True),
   db.Column('subcategory_id', db.Integer, db.ForeignKey('subcategories.id'), primary_key=True)
)

class CourseSpecialization(db.Model):
   __tablename__ = 'dpo_course_specializations'
   course_id = db.Column(db.Integer, db.ForeignKey('dpo_courses.id'), primary_key=True)
   specialization_id = db.Column(db.Integer, db.ForeignKey('specializations.id'), primary_key=True)

class Specialization(db.Model):
   __tablename__ = 'specializations'
   id = db.Column(db.Integer, primary_key=True)
   name = db.Column(db.String)