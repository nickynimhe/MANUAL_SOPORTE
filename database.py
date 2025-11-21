import psycopg2
import os
from datetime import datetime
from config import Config

def crear_conexion():
    """Crear conexión a la base de datos PostgreSQL de Render"""
    try:
        # Usar la DATABASE_URL de la configuración
        database_url = Config.DATABASE_URL
        
        if not database_url:
            print("❌ DATABASE_URL no configurada")
            return None
        
        print(f"🔗 Conectando a: {database_url.split('@')[1] if '@' in database_url else database_url}")
        
        # Conectar usando la URL completa
        conexion = psycopg2.connect(database_url)
        print("✅ Conectado a la base de datos PostgreSQL de Render")
        return conexion
        
    except Exception as e:
        print(f"❌ Error conectando a la base de datos: {e}")
        return None

def crear_tablas_usuarios():
    """Crear tabla de usuarios"""
    conexion = crear_conexion()
    if conexion:
        try:
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
                print("✅ Usuario admin creado por defecto")
            
            conexion.commit()
            print("✅ Tabla de usuarios creada/existe correctamente")
            
        except Exception as e:
            print(f"❌ Error creando tabla de usuarios: {e}")
            conexion.rollback()
        finally:
            cursor.close()
            conexion.close()

def crear_tablas_fichas():
    """Crear tabla de fichas técnicas"""
    conexion = crear_conexion()
    if conexion:
        try:
            cursor = conexion.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fichas (
                    id SERIAL PRIMARY KEY,
                    categoria VARCHAR(100) NOT NULL,
                    problema TEXT NOT NULL,
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
            print(f"❌ Error creando tabla de fichas: {e}")
            conexion.rollback()
        finally:
            cursor.close()
            conexion.close()

def crear_tablas_sst():
    """Crear tablas específicas para SST"""
    conexion = crear_conexion()
    if conexion:
        try:
            cursor = conexion.cursor()
            
            # Tabla de categorías SST
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sst_categorias (
                    id SERIAL PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL,
                    color VARCHAR(20),
                    descripcion TEXT,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla de contenido SST
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sst_contenido (
                    id SERIAL PRIMARY KEY,
                    titulo VARCHAR(200) NOT NULL,
                    descripcion TEXT,
                    tipo VARCHAR(50) NOT NULL,
                    archivo_url TEXT,
                    archivo_local VARCHAR(500),
                    video_url TEXT,
                    categoria_id INTEGER REFERENCES sst_categorias(id),
                    es_obligatorio BOOLEAN DEFAULT FALSE,
                    tags TEXT,
                    fecha_publicacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario_creador INTEGER REFERENCES usuarios(id)
                )
            ''')
            
            # Tabla de seguimiento de visualizaciones
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sst_seguimiento (
                    id SERIAL PRIMARY KEY,
                    usuario_id INTEGER REFERENCES usuarios(id),
                    contenido_id INTEGER REFERENCES sst_contenido(id),
                    fecha_visualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completado BOOLEAN DEFAULT FALSE,
                    UNIQUE(usuario_id, contenido_id)
                )
            ''')
            
            # Insertar categorías por defecto
            categorias = [
                ('Seguridad General', '#FF6B6B', 'Contenido general de seguridad'),
                ('Procedimientos', '#4ECDC4', 'Procedimientos de seguridad'),
                ('Equipos de Protección', '#45B7D1', 'Uso de EPP'),
                ('Emergencias', '#FFA07A', 'Procedimientos de emergencia'),
                ('Salud Ocupacional', '#98D8C8', 'Salud en el trabajo')
            ]
            
            cursor.execute("SELECT COUNT(*) FROM sst_categorias")
            if cursor.fetchone()[0] == 0:
                cursor.executemany(
                    "INSERT INTO sst_categorias (nombre, color, descripcion) VALUES (%s, %s, %s)",
                    categorias
                )
                print("✅ Categorías SST creadas por defecto")
            
            conexion.commit()
            print("✅ Tablas SST creadas/existen correctamente")
            
        except Exception as e:
            print(f"❌ Error creando tablas SST: {e}")
            conexion.rollback()
        finally:
            cursor.close()
            conexion.close()

def crear_tablas():
    """Crear todas las tablas necesarias"""
    print("🔧 Creando/verificando tablas...")
    crear_tablas_usuarios()
    crear_tablas_fichas()
    crear_tablas_sst()
    print("✅ Todas las tablas creadas/verificadas")

def resetear_secuencias():
    """Resetear secuencias de IDs si es necesario"""
    conexion = crear_conexion()
    if conexion:
        try:
            cursor = conexion.cursor()
            
            # Resetear secuencia de fichas
            cursor.execute("SELECT setval('fichas_id_seq', COALESCE((SELECT MAX(id) FROM fichas), 0) + 1, false)")
            
            # Resetear secuencia de usuarios
            cursor.execute("SELECT setval('usuarios_id_seq', COALESCE((SELECT MAX(id) FROM usuarios), 0) + 1, false)")
            
            conexion.commit()
            print("✅ Secuencias reseteadas correctamente")
            
        except Exception as e:
            print(f"❌ Error reseteando secuencias: {e}")
            conexion.rollback()
        finally:
            cursor.close()
            conexion.close()
