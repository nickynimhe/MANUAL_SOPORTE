import os
import psycopg2
from werkzeug.security import generate_password_hash
import json
import time

def crear_conexion():
    """Conexión mejorada y simplificada para Render"""
    max_intentos = 3
    for intento in range(max_intentos):
        try:
            print(f"🔗 Intento {intento + 1} de conexión a PostgreSQL...")
            
            # Obtener DATABASE_URL desde config o variables de entorno
            try:
                from config import Config
                database_url = Config.DATABASE_URL
            except:
                database_url = os.getenv('DATABASE_URL')
            
            if not database_url:
                print("❌ DATABASE_URL no encontrada en configuración")
                return None
            
            # Asegurar formato correcto
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)
            
            # Agregar sslmode para Render si es necesario
            if 'render.com' in database_url and 'sslmode=' not in database_url:
                database_url += '?sslmode=require'
            
            # Ocultar credenciales en logs
            url_para_logs = database_url
            if '@' in database_url:
                partes = database_url.split('@')
                url_para_logs = f"postgresql://*@{partes[1]}"
            print(f"🔗 Conectando a: {url_para_logs}")
            
            # Crear conexión
            conexion = psycopg2.connect(database_url)
            
            # Verificar que la conexión funciona
            cursor = conexion.cursor()
            cursor.execute("SELECT version()")
            version_info = cursor.fetchone()
            cursor.close()
            
            print(f"✅ ¡CONEXIÓN EXITOSA! PostgreSQL: {version_info[0].split(',')[0]}")
            return conexion
            
        except Exception as err:
            print(f"❌ Intento {intento + 1} falló: {str(err)}")
            if intento < max_intentos - 1:
                print("🔄 Reintentando en 3 segundos...")
                time.sleep(3)
            else:
                print("💥 Todos los intentos de conexión fallaron")
                return None

def resetear_secuencias():
    """Resetea las secuencias de las tablas"""
    conexion = None
    cursor = None
    
    try:
        conexion = crear_conexion()
        if not conexion:
            print("💥 No se pudo conectar para resetear secuencias")
            return False

        cursor = conexion.cursor()
        
        print("🔄 Reseteando secuencias...")
        
        # Resetear secuencia de usuarios si existe
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.sequences 
                WHERE sequence_name = 'usuarios_id_seq'
            )
        """)
        if cursor.fetchone()[0]:
            cursor.execute("""
                SELECT setval('usuarios_id_seq', COALESCE((SELECT MAX(id) FROM usuarios), 1), false)
            """)
            print("✅ Secuencia 'usuarios_id_seq' reseteada")
        else:
            print("ℹ Secuencia 'usuarios_id_seq' no existe aún")
        
        # Resetear secuencia de fichas si existe
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.sequences 
                WHERE sequence_name = 'fichas_id_seq'
            )
        """)
        if cursor.fetchone()[0]:
            cursor.execute("""
                SELECT setval('fichas_id_seq', COALESCE((SELECT MAX(id) FROM fichas), 1), false)
            """)
            print("✅ Secuencia 'fichas_id_seq' reseteada")
        else:
            print("ℹ Secuencia 'fichas_id_seq' no existe aún")
        
        # Resetear secuencias SST si existen
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.sequences 
                WHERE sequence_name = 'sst_categorias_id_seq'
            )
        """)
        if cursor.fetchone()[0]:
            cursor.execute("""
                SELECT setval('sst_categorias_id_seq', COALESCE((SELECT MAX(id) FROM sst_categorias), 1), false)
            """)
            print("✅ Secuencia 'sst_categorias_id_seq' reseteada")
        
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.sequences 
                WHERE sequence_name = 'sst_contenido_id_seq'
            )
        """)
        if cursor.fetchone()[0]:
            cursor.execute("""
                SELECT setval('sst_contenido_id_seq', COALESCE((SELECT MAX(id) FROM sst_contenido), 1), false)
            """)
            print("✅ Secuencia 'sst_contenido_id_seq' reseteada")
        
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.sequences 
                WHERE sequence_name = 'sst_seguimiento_id_seq'
            )
        """)
        if cursor.fetchone()[0]:
            cursor.execute("""
                SELECT setval('sst_seguimiento_id_seq', COALESCE((SELECT MAX(id) FROM sst_seguimiento), 1), false)
            """)
            print("✅ Secuencia 'sst_seguimiento_id_seq' reseteada")
        
        conexion.commit()
        print("🎉 Secuencias reseteadas correctamente")
        return True

    except Exception as err:
        print(f"💥 Error reseteando secuencias: {str(err)}")
        if conexion:
            conexion.rollback()
        return False
        
    finally:
        if cursor:
            cursor.close()
        if conexion:
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
            
            # Tabla de contenido SST - VERSIÓN CORREGIDA
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sst_contenido (
                    id SERIAL PRIMARY KEY,
                    titulo VARCHAR(200) NOT NULL,
                    descripcion TEXT,
                    tipo VARCHAR(50) NOT NULL,
                    archivo_url TEXT,
                    archivo_local VARCHAR(500),  -- Aumentado a 500 caracteres
                    video_url TEXT,
                    categoria_id INTEGER REFERENCES sst_categorias(id),
                    es_obligatorio BOOLEAN DEFAULT FALSE,
                    duracion_video INTEGER,
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
            
            conexion.commit()
            print("✅ Tablas SST creadas/existen correctamente")
            
        except Exception as e:
            print(f"❌ Error creando tablas SST: {e}")
            conexion.rollback()
        finally:
            cursor.close()
            conexion.close()

def crear_tablas():
    """Función mejorada para crear tablas"""
    print("🔧 Iniciando creación de tablas...")
    
    conexion = None
    cursor = None
    
    try:
        conexion = crear_conexion()
        if not conexion:
            print("💥 No se pudo conectar para crear tablas")
            return False

        cursor = conexion.cursor()

        # Tabla usuarios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                usuario VARCHAR(50) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                rol VARCHAR(50) NOT NULL DEFAULT 'asesor',
                permisos JSONB,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Tabla 'usuarios' lista")

        # Tabla fichas
        cursor.execute("""
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
        """)
        print("✅ Tabla 'fichas' lista")

        # Insertar usuario admin por defecto si no existe
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE usuario = 'admin'")
        if cursor.fetchone()[0] == 0:
            password_hash = generate_password_hash('admin123')
            permisos_admin = json.dumps({
                'ver_fichas': True, 
                'agregar_fichas': True,
                'editar_fichas': True, 
                'eliminar_fichas': True,
                'cambiar_password': True
            })
            cursor.execute(
                "INSERT INTO usuarios (usuario, password, rol, permisos) VALUES (%s, %s, %s, %s)",
                ('admin', password_hash, 'admin', permisos_admin)
            )
            print("✅ Usuario 'admin' creado (password: admin123)")
        else:
            print("ℹ Usuario 'admin' ya existe")

        # Crear o resetear secuencias
        try:
            cursor.execute("""
                SELECT setval('usuarios_id_seq', COALESCE((SELECT MAX(id) FROM usuarios), 1), true)
            """)
            cursor.execute("""
                SELECT setval('fichas_id_seq', COALESCE((SELECT MAX(id) FROM fichas), 1), true)
            """)
            print("✅ Secuencias configuradas")
        except Exception as seq_err:
            print(f"ℹ Las secuencias se crearán automáticamente: {seq_err}")

        # Crear tablas SST
        print("🔧 Creando tablas SST...")
        crear_tablas_sst()

        conexion.commit()
        print("🎉 Base de datos inicializada CORRECTAMENTE")
        return True

    except Exception as err:
        print(f"💥 Error en creación de tablas: {str(err)}")
        if conexion:
            conexion.rollback()
        return False
        
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

def verificar_tablas():
    """Verificar que las tablas existen"""
    conexion = None
    cursor = None
    
    try:
        conexion = crear_conexion()
        if not conexion:
            return False

        cursor = conexion.cursor()
        
        # Verificar tabla usuarios
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'usuarios'
            )
        """)
        usuarios_existe = cursor.fetchone()[0]
        
        # Verificar tabla fichas
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'fichas'
            )
        """)
        fichas_existe = cursor.fetchone()[0]
        
        # Verificar tablas SST
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'sst_categorias'
            )
        """)
        sst_categorias_existe = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'sst_contenido'
            )
        """)
        sst_contenido_existe = cursor.fetchone()[0]
        
        # Verificar datos en usuarios
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        total_usuarios = cursor.fetchone()[0]
        
        print(f"📊 Tabla 'usuarios' existe: {usuarios_existe} ({total_usuarios} usuarios)")
        print(f"📊 Tabla 'fichas' existe: {fichas_existe}")
        print(f"📊 Tabla 'sst_categorias' existe: {sst_categorias_existe}")
        print(f"📊 Tabla 'sst_contenido' existe: {sst_contenido_existe}")
        
        return usuarios_existe and fichas_existe and sst_categorias_existe and sst_contenido_existe
        
    except Exception as err:
        print(f"💥 Error verificando tablas: {err}")
        return False
        
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

def verificar_conexion():
    """Verificar solo la conexión sin crear tablas"""
    conexion = None
    try:
        conexion = crear_conexion()
        if conexion:
            print("✅ Conexión a PostgreSQL verificada correctamente")
            return True
        else:
            print("❌ No se pudo establecer conexión")
            return False
    finally:
        if conexion:
            conexion.close()

if __name__ == "__main__":
    print("🚀 Inicializando base de datos...")
    
    # Primero verificar conexión
    print("🔍 Verificando conexión...")
    if not verificar_conexion():
        print("💥 No se puede continuar sin conexión a la base de datos")
        exit(1)
    
    # Verificar si las tablas ya existen
    print("🔍 Verificando tablas existentes...")
    if verificar_tablas():
        print("ℹ Las tablas ya existen, solo reseteando secuencias...")
        if resetear_secuencias():
            print("✅ Base de datos ya está lista")
        else:
            print("⚠ Problemas reseteando secuencias")
    else:
        print("🔧 Creando tablas...")
        if crear_tablas():
            print("🎉 ¡Base de datos inicializada correctamente!")
        else:
            print("💥 Error inicializando base de datos")
