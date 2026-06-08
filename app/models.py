from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash


DB_NAME = 'dpo_db'


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://root:zxcvbnasdqwe@localhost/{DB_NAME}'
app.config['SECRET_KEY'] = 'dpo_secret_key_diploma_2024'
db = SQLAlchemy(app)


class Organization(db.Model):
   __tablename__ = 'organizations'
   id = db.Column(db.Integer, primary_key=True)
   name = db.Column(db.String)


class Department(db.Model):
   __tablename__ = 'departments'
   id = db.Column(db.Integer, primary_key=True)
   name = db.Column(db.String(500))
   address = db.Column(db.String(500))
   organization_id = db.Column(db.Integer)

   phones = db.relationship('DepartmentPhone', backref='department', lazy='select')
   emails = db.relationship('DepartmentEmail', backref='department', lazy='select')


class DepartmentPhone(db.Model):
   __tablename__ = 'department_phones'
   id = db.Column(db.Integer, primary_key=True)
   department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
   phone = db.Column(db.String(50))


class DepartmentEmail(db.Model):
   __tablename__ = 'department_emails'
   id = db.Column(db.Integer, primary_key=True)
   department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
   email = db.Column(db.String(255))


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
   description = db.Column(db.Text)
   date = db.Column(db.String(150))
   norm_date = db.Column(db.Date)      
   schedule = db.Column(db.String(255))
   admission_requirements = db.Column(db.Text)
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

   courses = db.relationship('Course', secondary='rel_course_category', viewonly=False)


class Subcategory(db.Model):
   __tablename__ = 'subcategories'
   id = db.Column(db.Integer, primary_key=True)
   name = db.Column(db.String(255), nullable=False)
   parent_category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)

   category = db.relationship('Category', backref='subcategories')
   courses = db.relationship('Course', secondary='rel_course_subcategory', viewonly=False)


# Связующие таблицы
rel_course_category = db.Table('rel_course_category',
   db.Column('course_id', db.Integer, db.ForeignKey('dpo_courses.id'), primary_key=True),
   db.Column('category_id', db.Integer, db.ForeignKey('categories.id'), primary_key=True)
)

rel_course_subcategory = db.Table('rel_course_subcategory',
   db.Column('course_id', db.Integer, db.ForeignKey('dpo_courses.id'), primary_key=True),
   db.Column('subcategory_id', db.Integer, db.ForeignKey('subcategories.id'), primary_key=True)
)


class User(db.Model):
   __tablename__ = 'users'
   id = db.Column(db.Integer, primary_key=True)
   login = db.Column(db.String(150), unique=True, nullable=False)
   password_hash = db.Column(db.String(255), nullable=False)

   def set_password(self, password):
      self.password_hash = generate_password_hash(password)

   def check_password(self, password):
      return check_password_hash(self.password_hash, password)


class FavoriteCourse(db.Model):
   __tablename__ = 'favorite_courses'
   id = db.Column(db.Integer, primary_key=True)
   user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
   course_id = db.Column(db.Integer, db.ForeignKey('dpo_courses.id'), nullable=False)

   user = db.relationship('User', backref='favorites')
   course = db.relationship('Course', backref='favorited_by')


class DraftCourse(db.Model):
   __tablename__ = 'draft_dpo_courses'
   id = db.Column(db.Integer, primary_key=True)
   title = db.Column(db.String(500), nullable=False)
   price = db.Column(db.String(100), nullable=True)
   format = db.Column(db.String(150), nullable=True)
   duration = db.Column(db.String(100), nullable=True)
   date = db.Column(db.String(150), nullable=True)
   description = db.Column(db.Text, nullable=True)
   language = db.Column(db.String(100), nullable=True)
   document = db.Column(db.String(100), nullable=True)
   created_at = db.Column(db.DateTime, server_default=db.func.now())
   updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
   course_type = db.Column(db.String(100), nullable=True)
   admission_requirements = db.Column(db.Text, nullable=True)
   schedule = db.Column(db.String(255), nullable=True)
   duration_in_hours = db.Column(db.String(100), nullable=True)
   competitiveness_score = db.Column(db.Integer, nullable=True)
   has_document = db.Column(db.Boolean, default=False)
   has_installment = db.Column(db.Boolean, default=False)
   has_date = db.Column(db.Boolean, default=False)
   notes = db.Column(db.Text, nullable=True)
   category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
   subcategory_id = db.Column(db.Integer, db.ForeignKey('subcategories.id'), nullable=True)

   category = db.relationship('Category', foreign_keys='DraftCourse.category_id')
   subcategory = db.relationship('Subcategory', foreign_keys='DraftCourse.subcategory_id')


class UserDraft(db.Model):
   __tablename__ = 'user_drafts'
   id = db.Column(db.Integer, primary_key=True)
   user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
   draft_course_id = db.Column(db.Integer, db.ForeignKey('draft_dpo_courses.id'), nullable=False)

   user = db.relationship('User', backref='drafts')
   draft = db.relationship('DraftCourse', backref='user_link')


class Specialization(db.Model):
   __tablename__ = 'specializations'
   id = db.Column(db.Integer, primary_key=True)
   name = db.Column(db.String)