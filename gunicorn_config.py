# gunicorn_config.py
# Configuración para Gunicorn con soporte para archivos grandes

import os
import multiprocessing

# ===== WORKERS Y THREADS =====
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
threads = int(os.environ.get('GUNICORN_THREADS', 2))
worker_class = 'gthread'

# ===== TIMEOUTS (AUMENTADOS PARA ARCHIVOS GRANDES) =====
timeout = 300  # 5 minutos (300 segundos)
keepalive = 5
graceful_timeout = 120

# ===== LÍMITES DE TAMAÑO DE REQUEST (SIN LÍMITE) =====
limit_request_line = 0  # Sin límite en línea de request
limit_request_fields = 100
limit_request_field_size = 0  # Sin límite en tamaño de campos

# ===== LOGGING =====
accesslog = '-'  # Log a stdout
errorlog = '-'   # Log a stderr
loglevel = 'info'

# ===== BINDING =====
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# ===== PRELOAD =====
preload_app = False

# ===== WORKER CONFIGURATION =====
worker_tmp_dir = '/dev/shm'  # Usar memoria compartida para mejorar rendimiento
