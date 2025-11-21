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
                url_para_logs = f"postgresql://***@{partes[1]}"
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
            print("ℹ️ Secuencia 'usuarios_id_seq' no existe aún")
        
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
            print("ℹ️ Secuencia 'fichas_id_seq' no existe aún")
        
        # Resetear secuencia de soluciones_visuales si existe
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.sequences 
                WHERE sequence_name = 'soluciones_visuales_id_seq'
            )
        """)
        if cursor.fetchone()[0]:
            cursor.execute("""
                SELECT setval('soluciones_visuales_id_seq', COALESCE((SELECT MAX(id) FROM soluciones_visuales), 1), false)
            """)
            print("✅ Secuencia 'soluciones_visuales_id_seq' reseteada")
        else:
            print("ℹ️ Secuencia 'soluciones_visuales_id_seq' no existe aún")
        
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

        # NUEVA TABLA: soluciones_visuales
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS soluciones_visuales (
                id SERIAL PRIMARY KEY,
                titulo VARCHAR(255) NOT NULL,
                categoria VARCHAR(50) NOT NULL,
                descripcion TEXT,
                pasos JSONB NOT NULL,
                activo BOOLEAN DEFAULT TRUE,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Tabla 'soluciones_visuales' lista")

        # Insertar usuario admin por defecto si no existe
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE usuario = 'admin'")
        if cursor.fetchone()[0] == 0:
            password_hash = generate_password_hash('admin123')
            permisos_admin = json.dumps({
                'ver_fichas': True, 
                'agregar_fichas': True,
                'editar_fichas': True, 
                'eliminar_fichas': True,
                'cambiar_password': True,
                'gestionar_soluciones': True  # Nuevo permiso
            })
            cursor.execute(
                "INSERT INTO usuarios (usuario, password, rol, permisos) VALUES (%s, %s, %s, %s)",
                ('admin', password_hash, 'admin', permisos_admin)
            )
            print("✅ Usuario 'admin' creado (password: admin123)")
        else:
            print("ℹ️ Usuario 'admin' ya existe")

        # Insertar datos de ejemplo para soluciones visuales
        cursor.execute("SELECT COUNT(*) FROM soluciones_visuales")
        if cursor.fetchone()[0] == 0:
            soluciones_ejemplo = [
                {
                    'titulo': 'Consultar cliente en Softv',
                    'categoria': 'Softv',
                    'descripcion': 'Guía completa para buscar y consultar información de clientes en la plataforma Softv',
                    'pasos': [
                        {
                            'imagen': 'softv/softv1.png',
                            'titulo': 'Paso 1: Ingresar a Softv y acceder al menú lateral',
                            'descripcion': 'Dentro de la plataforma Softv, ubique el menú desplegable lateral y seleccione la opción Facturación para continuar con el proceso.'
                        },
                        {
                            'imagen': 'softv/softv2.png',
                            'titulo': 'Paso 2: Ingresar al apartado de Cajas',
                            'descripcion': 'Haga clic en la opción Cajas. Se abrirá una ventana con las herramientas disponibles para realizar la búsqueda del cliente.'
                        },
                        {
                            'imagen': 'softv/softv3.png',
                            'titulo': 'Paso 3: Buscar al cliente',
                            'descripcion': 'Digite el número de documento del titular en el campo correspondiente. Una vez aparezca el registro del usuario, haga clic en el botón Seleccionar.'
                        },
                        {
                            'imagen': 'softv/softv4.png',
                            'titulo': 'Paso 4: Visualizar la información del cliente',
                            'descripcion': 'Después de seleccionar al usuario, se mostrarán sus datos generales junto con los servicios activos y otra información relevante.'
                        }
                    ]
                },
                {
                    'titulo': 'Consultar facturas de usuarios',
                    'categoria': 'Softv',
                    'descripcion': 'Cómo consultar el historial de pagos y facturas de los clientes en Softv',
                    'pasos': [
                        {
                            'imagen': 'softv/softv5.png',
                            'titulo': 'Paso 1: Acceder al botón Historial',
                            'descripcion': 'En la parte inferior de la pantalla de información del usuario, ubique el botón Historial y haga clic en él.'
                        },
                        {
                            'imagen': 'softv/softv6.png',
                            'titulo': 'Paso 2: Ingresar al apartado de Pagos',
                            'descripcion': 'Al abrir el historial, se mostrarán tres opciones. Seleccione la primera opción: Pagos.'
                        }
                    ]
                },
                {
                    'titulo': 'Buscar usuario en Vortex',
                    'categoria': 'Vortex',
                    'descripcion': 'Guía para localizar usuarios en la plataforma Vortex mediante número de contrato',
                    'pasos': [
                        {
                            'imagen': 'vortex/vortex1.png',
                            'titulo': 'Paso 1: Acceder al menú Configure',
                            'descripcion': 'En la parte superior del sistema, ubique la barra de menús y haga clic en la opción Configured.'
                        },
                        {
                            'imagen': 'vortex/vortex2.png',
                            'titulo': 'Paso 2: Ingresar el contrato en el área de búsqueda',
                            'descripcion': 'Dentro de la sección Configured, en la parte superior encontrará el campo Search. Ingrese el número de contrato del usuario en este espacio.'
                        }
                    ]
                }
            ]
            
            for solucion in soluciones_ejemplo:
                cursor.execute(
                    "INSERT INTO soluciones_visuales (titulo, categoria, descripcion, pasos) VALUES (%s, %s, %s, %s)",
                    (solucion['titulo'], solucion['categoria'], solucion['descripcion'], json.dumps(solucion['pasos']))
                )
            print("✅ Datos de ejemplo para soluciones visuales insertados")
        else:
            print("ℹ️ Tabla 'soluciones_visuales' ya tiene datos")

        # Crear o resetear secuencias
        try:
            cursor.execute("""
                SELECT setval('usuarios_id_seq', COALESCE((SELECT MAX(id) FROM usuarios), 1), true)
            """)
            cursor.execute("""
                SELECT setval('fichas_id_seq', COALESCE((SELECT MAX(id) FROM fichas), 1), true)
            """)
            cursor.execute("""
                SELECT setval('soluciones_visuales_id_seq', COALESCE((SELECT MAX(id) FROM soluciones_visuales), 1), true)
            """)
            print("✅ Secuencias configuradas")
        except Exception as seq_err:
            print(f"ℹ️ Las secuencias se crearán automáticamente: {seq_err}")

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
        
        # Verificar tabla soluciones_visuales
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'soluciones_visuales'
            )
        """)
        soluciones_existe = cursor.fetchone()[0]
        
        # Verificar datos en usuarios
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        total_usuarios = cursor.fetchone()[0]
        
        # Verificar datos en soluciones_visuales
        cursor.execute("SELECT COUNT(*) FROM soluciones_visuales")
        total_soluciones = cursor.fetchone()[0]
        
        print(f"📊 Tabla 'usuarios' existe: {usuarios_existe} ({total_usuarios} usuarios)")
        print(f"📊 Tabla 'fichas' existe: {fichas_existe}")
        print(f"📊 Tabla 'soluciones_visuales' existe: {soluciones_existe} ({total_soluciones} soluciones)")
        
        return usuarios_existe and fichas_existe and soluciones_existe
        
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
        print("ℹ️ Las tablas ya existen, solo reseteando secuencias...")
        if resetear_secuencias():
            print("✅ Base de datos ya está lista")
        else:
            print("⚠️ Problemas reseteando secuencias")
    else:
        print("🔧 Creando tablas...")
        if crear_tablas():
            print("🎉 ¡Base de datos inicializada correctamente!")
        else:
            print("💥 Error inicializando base de datos")
