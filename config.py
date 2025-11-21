import os
from datetime import timedelta

class Config:
    # Es recomendable definir un valor por defecto solo para desarrollo local
    SECRET_KEY = os.environ.get('SECRET_KEY', 'manual-soporte-secret-key-2025-mastv')

     # Configuración de sesión
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # Configuración de Flask-Login
    SESSION_PROTECTION = 'strong'
    
    # URL completa de conexión para PostgreSQL - USAR ESTA
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    # Si no hay DATABASE_URL, usar la nueva base de datos por defecto
    if not DATABASE_URL:
        DATABASE_URL = 'postgresql://soporte_tecnico_bujd_user:4O43zJ3NiE5NrvdeMYD3hxsXgIOWVonw@dpg-d4g6i23e5dus739l1c80-a.oregon-postgres.render.com/soporte_tecnico_bujd'
    
    # Asegurar que la URL use postgresql:// en lugar de postgres://
    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    # Mantener las variables individuales por compatibilidad (opcional)
    # Pero ya no son necesarias para la conexión principal
    DB_HOST = os.environ.get('DB_HOST', 'dpg-d4g6i23e5dus739l1c80-a.oregon-postgres.render.com')
    DB_NAME = os.environ.get('DB_NAME', 'soporte_tecnico_bujd')
    DB_USER = os.environ.get('DB_USER', 'soporte_tecnico_bujd_user')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '4O43zJ3NiE5NrvdeMYD3hxsXgIOWVonw')
    DB_PORT = os.environ.get('DB_PORT', '5432')
