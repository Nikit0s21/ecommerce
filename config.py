import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get('SECRET_KEY')