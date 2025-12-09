#!/bin/bash

echo "🚀 Iniciando la aplicación Flask..."

# Verificar dependencias
echo "📦 Verificando dependencias..."
pip list | grep -E "Flask|psycopg2|gunicorn"

# Crear tablas en la base de datos si no existen
echo "🗄️ Verificando/Creando tablas de base de datos..."
python -c "
from app import app, crear_tablas
with app.app_context():
    crear_tablas()
    print('✅ Tablas verificadas/creadas')
    print('🌐 URL base:', app.config.get('SERVER_NAME', 'localhost:5000'))
"

# Verificar si existe gunicorn
if command -v gunicorn &> /dev/null; then
    echo "🐳 Iniciando con Gunicorn..."
    gunicorn --bind 0.0.0.0:${PORT:-5000} \
             --workers 4 \
             --threads 2 \
             --timeout 120 \
             --access-logfile - \
             --error-logfile - \
             app:app
else
    echo "⚡ Iniciando con Flask (modo desarrollo)..."
    python app.py
fi
