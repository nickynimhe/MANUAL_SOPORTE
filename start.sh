#!/bin/bash

# Iniciar la aplicación con Gunicorn
echo "🚀 Iniciando la aplicación Flask con Gunicorn..."

# Crear tablas en la base de datos si no existen
python -c "
from app import app, crear_tablas
with app.app_context():
    crear_tablas()
    print('✅ Tablas verificadas/creadas')
"

# Iniciar Gunicorn
gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 4 --threads 2 --timeout 120 app:app
