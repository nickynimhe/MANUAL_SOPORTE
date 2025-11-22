import psycopg2
import os
from config import Config

def crear_conexion():
    """Crear conexión a la base de datos PostgreSQL en Render"""
    try:
        # Usar DATABASE_URL de Render
        database_url = os.environ.get('DATABASE_URL')
        
        if database_url:
            # Render usa formato postgresql://, pero psycopg2 necesita postgresql://
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
            
            conexion = psycopg2.connect(database_url)
            print(f"🔗 Conectado a la base de datos PostgreSQL de Render")
            return conexion
        else:
            # Fallback a configuración local
            conexion = psycopg2.connect(
                host=Config.DB_HOST,
                database=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                port=Config.DB_PORT
            )
            print(f"🔗 Conectado a: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
            return conexion
            
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return None

def crear_tabla_usuarios():
    """Crear tabla de usuarios si no existe"""
    conexion = None
    cursor = None
    try:
        conexion = crear_conexion()
        if conexion:
            cursor = conexion.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    usuario VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    rol VARCHAR(20) DEFAULT 'usuario',
                    permisos TEXT,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insertar usuario admin por defecto si no existe
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE usuario = 'admin'")
            if cursor.fetchone()[0] == 0:
                from werkzeug.security import generate_password_hash
                password_hash = generate_password_hash('admin123')
                cursor.execute(
                    "INSERT INTO usuarios (usuario, password, rol) VALUES (%s, %s, %s)",
                    ('admin', password_hash, 'admin')
                )
                print("✅ Usuario admin creado: admin / admin123")
            
            conexion.commit()
            print("✅ Tabla de usuarios creada/existe correctamente")
            
    except Exception as e:
        print(f"❌ Error al crear tabla usuarios: {e}")
        if conexion:
            conexion.rollback()
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

def crear_tabla_fichas():
    """Crear tabla de fichas técnicas si no existe"""
    conexion = None
    cursor = None
    try:
        conexion = crear_conexion()
        if conexion:
            cursor = conexion.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fichas (
                    id SERIAL PRIMARY KEY,
                    categoria VARCHAR(50) NOT NULL,
                    problema VARCHAR(255) NOT NULL,
                    descripcion TEXT,
                    causas TEXT,
                    solucion TEXT NOT NULL,
                    palabras_clave TEXT,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conexion.commit()
            print("✅ Tabla de fichas creada/existe correctamente")
            
    except Exception as e:
        print(f"❌ Error al crear tabla fichas: {e}")
        if conexion:
            conexion.rollback()
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

def crear_tablas_sst():
    """Crear tablas para el módulo SST (SIMPLIFICADO - sin estadísticas)"""
    conexion = None
    cursor = None
    try:
        conexion = crear_conexion()
        if conexion:
            cursor = conexion.cursor()
            print("🔧 Creando/verificando tablas SST...")
            
            # Tabla de categorías SST
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sst_categorias (
                    id SERIAL PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL UNIQUE,
                    color VARCHAR(7) DEFAULT '#007bff',
                    icono VARCHAR(50) DEFAULT 'fa-folder',
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla de contenido SST (SIMPLIFICADA - sin estadísticas)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sst_contenido (
                    id SERIAL PRIMARY KEY,
                    titulo VARCHAR(255) NOT NULL,
                    descripcion TEXT,
                    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('video', 'documento', 'imagen', 'enlace')),
                    archivo_url VARCHAR(500),
                    archivo_local VARCHAR(255),
                    video_url VARCHAR(500),
                    categoria_id INTEGER REFERENCES sst_categorias(id),
                    es_obligatorio BOOLEAN DEFAULT FALSE,
                    tags VARCHAR(500),
                    fecha_publicacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario_creador INTEGER REFERENCES usuarios(id),
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # INSERTAR CATEGORÍAS BÁSICAS (si no existen)
            cursor.execute("""
                INSERT INTO sst_categorias (nombre, color, icono) 
                VALUES 
                    ('Videos de Capacitación', '#007bff', 'fa-video'),
                    ('Procedimientos de Seguridad', '#28a745', 'fa-clipboard-list'),
                    ('Primeros Auxilios', '#dc3545', 'fa-first-aid'),
                    ('Equipos de Protección', '#ffc107', 'fa-hard-hat'),
                    ('Emergencias', '#17a2b8', 'fa-exclamation-triangle'),
                    ('Normativa Legal', '#6c757d', 'fa-gavel')
                ON CONFLICT (nombre) DO NOTHING
            """)
            
            conexion.commit()
            print("✅ Tablas SST creadas/existen correctamente")
            
    except Exception as e:
        print(f"❌ Error al crear tablas SST: {e}")
        if conexion:
            conexion.rollback()
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

def crear_tablas():
    """Función principal para crear todas las tablas"""
    print("🔧 Creando/verificando tablas...")
    
    crear_tabla_usuarios()
    crear_tabla_fichas() 
    crear_tablas_sst()  # Tablas SST simplificadas
    
    print("✅ Todas las tablas creadas/verificadas")

# Función para resetear secuencias (útil en desarrollo)
def resetear_secuencias():
    """Resetear secuencias de IDs (útil en desarrollo)"""
    conexion = None
    cursor = None
    try:
        conexion = crear_conexion()
        if conexion:
            cursor = conexion.cursor()
            
            # Resetear secuencias para todas las tablas
            tablas = ['usuarios', 'fichas', 'sst_contenido', 'sst_categorias']
            
            for tabla in tablas:
                cursor.execute(f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), coalesce(max(id), 1), false) FROM {tabla}")
            
            conexion.commit()
            print("🔄 Secuencias reseteadas correctamente")
            
    except Exception as e:
        print(f"⚠ Error al resetear secuencias: {e}")
        if conexion:
            conexion.rollback()
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()
