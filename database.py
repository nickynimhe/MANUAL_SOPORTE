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
    """Crear tablas para el módulo SST - VERSIÓN SIMPLIFICADA"""
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
            
            # Tabla de contenido SST
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
            
            conexion.commit()
            print("✅ Tablas SST base creadas correctamente")
            
    except Exception as e:
        print(f"❌ Error al crear tablas SST: {e}")
        if conexion:
            conexion.rollback()
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

def verificar_y_crear_categorias_sst():
    """Verificar y crear categorías SST si no existen - VERSIÓN MEJORADA"""
    conexion = None
    cursor = None
    try:
        conexion = crear_conexion()
        if conexion:
            cursor = conexion.cursor()
            
            # Verificar si hay categorías
            cursor.execute("SELECT COUNT(*) FROM sst_categorias")
            count = cursor.fetchone()[0]
            
            print(f"📊 Categorías SST existentes: {count}")
            
            if count == 0:
                print("🔧 No hay categorías SST, creando categorías básicas...")
                
                categorias = [
                    ('Videos de Capacitación', '#007bff', 'fa-video'),
                    ('Procedimientos de Seguridad', '#28a745', 'fa-clipboard-list'),
                    ('Primeros Auxilios', '#dc3545', 'fa-first-aid'),
                    ('Equipos de Protección', '#ffc107', 'fa-hard-hat'),
                    ('Emergencias', '#17a2b8', 'fa-exclamation-triangle'),
                    ('Normativa Legal', '#6c757d', 'fa-gavel')
                ]
                
                categorias_insertadas = 0
                for nombre, color, icono in categorias:
                    try:
                        # Usar INSERT ON CONFLICT para evitar duplicados
                        cursor.execute("""
                            INSERT INTO sst_categorias (nombre, color, icono) 
                            VALUES (%s, %s, %s)
                            ON CONFLICT (nombre) DO NOTHING
                        """, (nombre, color, icono))
                        
                        # Verificar si se insertó
                        cursor.execute("SELECT COUNT(*) FROM sst_categorias WHERE nombre = %s", (nombre,))
                        if cursor.fetchone()[0] > 0:
                            categorias_insertadas += 1
                            print(f"✅ Categoría '{nombre}' creada/verificada")
                        else:
                            print(f"⚠ Categoría '{nombre}' ya existe")
                            
                    except Exception as e:
                        print(f"❌ Error al crear categoría '{nombre}': {e}")
                        continue
                
                conexion.commit()
                print(f"✅ {categorias_insertadas} categorías SST creadas/verificadas correctamente")
            else:
                print(f"✅ Ya existen {count} categorías SST, no es necesario crear más")
                
    except Exception as e:
        print(f"❌ Error al verificar categorías SST: {e}")
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
    crear_tablas_sst()
    verificar_y_crear_categorias_sst()  # <-- AGREGAR ESTA LÍNEA
    
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
                try:
                    cursor.execute(f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), coalesce(max(id), 1), false) FROM {tabla}")
                    print(f"🔄 Secuencia resetada para {tabla}")
                except Exception as e:
                    print(f"⚠ No se pudo resetear secuencia para {tabla}: {e}")
                    continue
            
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

# Función para verificar el estado de las tablas
def verificar_tablas():
    """Verificar que todas las tablas existan"""
    conexion = None
    cursor = None
    try:
        conexion = crear_conexion()
        if conexion:
            cursor = conexion.cursor()
            
            tablas = ['usuarios', 'fichas', 'sst_categorias', 'sst_contenido']
            
            for tabla in tablas:
                cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)", (tabla,))
                existe = cursor.fetchone()[0]
                if existe:
                    print(f"✅ Tabla '{tabla}' existe")
                    
                    # Contar registros en cada tabla
                    cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
                    count = cursor.fetchone()[0]
                    print(f"   📊 Registros: {count}")
                else:
                    print(f"❌ Tabla '{tabla}' NO existe")
            
    except Exception as e:
        print(f"❌ Error al verificar tablas: {e}")
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

# Función para limpiar y resetear completamente (solo desarrollo)
def resetear_base_datos():
    """Resetear completamente la base de datos (SOLO DESARROLLO)"""
    print("⚠️  ADVERTENCIA: Esto eliminará todos los datos. Solo para desarrollo.")
    respuesta = input("¿Estás seguro? (escribe 'SI' para continuar): ")
    
    if respuesta != 'SI':
        print("❌ Operación cancelada")
        return
    
    conexion = None
    cursor = None
    try:
        conexion = crear_conexion()
        if conexion:
            cursor = conexion.cursor()
            
            # Eliminar tablas en orden correcto (por dependencias)
            tablas = ['sst_contenido', 'sst_categorias', 'fichas', 'usuarios']
            
            for tabla in tablas:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {tabla} CASCADE")
                    print(f"🗑️  Tabla {tabla} eliminada")
                except Exception as e:
                    print(f"⚠ Error al eliminar tabla {tabla}: {e}")
            
            conexion.commit()
            print("✅ Base de datos reseteada completamente")
            
            # Volver a crear las tablas
            crear_tablas()
            
    except Exception as e:
        print(f"❌ Error al resetear base de datos: {e}")
        if conexion:
            conexion.rollback()
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

# Si se ejecuta este archivo directamente
if __name__ == '__main__':
    print("🔧 Ejecutando configuración de base de datos...")
    crear_tablas()
    verificar_tablas()
    
    # Opción para resetear si es necesario
    print("\n¿Deseas resetear la base de datos? (solo desarrollo)")
    reset = input("Escribe 'RESET' para resetear o Enter para continuar: ")
    if reset == 'RESET':
        resetear_base_datos()
