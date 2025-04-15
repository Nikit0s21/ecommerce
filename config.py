import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:oquojdar@localhost:5432/ecommerce'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_PROTECTION = 'strong'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = True  # Для HTTPS