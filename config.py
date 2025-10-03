import os

class Config:
    # Clave secreta para sesiones Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-super-secreta-para-desarrollo'
    
    # Configuración de MySQL
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost'
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD') or ''
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'soporte_tecnico'
    
    # Configuración adicional
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')