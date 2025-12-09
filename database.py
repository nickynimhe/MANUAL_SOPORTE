import psycopg2
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from config import Config
import mimetypes

def crear_conexion():
    """Crear conexión a la base de datos PostgreSQL"""
    try:
        conexion = psycopg2.connect(
            host=Config.DB_HOST,
            database=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            port=Config.DB_PORT
        )
        return conexion
    except Exception as e:
        print(f"❌ Error al conectar a la base de datos: {e}")
        return None

def ejecutar_consulta(query, params=None, fetch=False, commit=False):
    """Ejecuta una consulta SQL con manejo de errores y depuración"""
    conexion = None
    cursor = None
    resultado = None
    
    try:
        # Crear conexión
        conexion = crear_conexion()
        if not conexion:
            print("❌ ERROR SQL: No se pudo crear la conexión")
            return None
        
        cursor = conexion.cursor()
        
        # Depuración
        print(f"📊 DEBUG SQL [Inicio]")
        print(f"📊 DEBUG SQL Query: {query[:200]}...")
        print(f"📊 DEBUG SQL Params: {params}")
        
        # Ejecutar consulta
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        # Manejar resultado según tipo de operación
        if commit:
            conexion.commit()
            resultado = True
            print(f"📊 DEBUG SQL [Commit OK] - Filas afectadas: {cursor.rowcount}")
        elif fetch:
            resultado = cursor.fetchall()
            print(f"📊 DEBUG SQL [Fetch OK] - {len(resultado) if resultado else 0} filas obtenidas")
        else:
            resultado = True
            print(f"📊 DEBUG SQL [Execute OK] - Filas afectadas: {cursor.rowcount}")
            
    except Exception as e:
        print(f"❌ ERROR SQL: {e}")
        print(f"❌ ERROR SQL Query: {query[:500]}")
        print(f"❌ ERROR SQL Params: {params}")
        
        # Rollback en caso de error con commit
        if commit and conexion:
            try:
                conexion.rollback()
                print("📊 DEBUG SQL: Rollback realizado")
            except:
                pass
        
        # Re-lanzar la excepción para manejo superior
        raise e
        
    finally:
        # Cerrar cursor y conexión
        if cursor:
            cursor.close()
            print("📊 DEBUG SQL: Cursor cerrado")
        if conexion:
            conexion.close()
            print("📊 DEBUG SQL: Conexión cerrada")
    
    return resultado

def crear_tablas():
    """Crear todas las tablas necesarias si no existen"""
    print("🔧 Creando/verificando tablas...")
    
    # Tabla de usuarios
    query_usuarios = """
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            usuario VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            rol VARCHAR(20) NOT NULL DEFAULT 'soporte',
            modulo_principal VARCHAR(20) DEFAULT 'soporte',
            permisos TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    
    # Tabla de fichas (soporte técnico)
    query_fichas = """
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
    """
    
    try:
        # Crear tabla de usuarios
        ejecutar_consulta(query_usuarios, commit=True)
        print("✅ Tabla de usuarios creada/existe correctamente")
        
        # Verificar si existe usuario admin
        resultado = ejecutar_consulta(
            "SELECT COUNT(*) FROM usuarios WHERE usuario = 'admin'", 
            fetch=True
        )
        
        if resultado and resultado[0][0] == 0:
            # Crear usuario admin por defecto
            from werkzeug.security import generate_password_hash
            hash_password = generate_password_hash('admin123')
            ejecutar_consulta(
                "INSERT INTO usuarios (usuario, password, rol, modulo_principal) VALUES (%s, %s, %s, %s)",
                ('admin', hash_password, 'admin', 'soporte'),
                commit=True
            )
            print("✅ Usuario admin creado por defecto")
        
        # Crear tabla de fichas
        ejecutar_consulta(query_fichas, commit=True)
        print("✅ Tabla de fichas creada/existe correctamente")
        
        # Crear tablas SST MEJORADAS
        crear_tablas_sst_mejoradas()
        
        print("✅ Todas las tablas creadas/verificadas")
        return True
        
    except Exception as e:
        print(f"❌ Error al crear tablas: {e}")
        return False

def crear_tablas_sst_mejoradas():
    """Crear tablas SST con estructura MEJORADA (archivos en base de datos)"""
    print("🔧 Creando/verificando tablas SST...")
    
    # Tabla de categorías SST
    query_categorias = """
        CREATE TABLE IF NOT EXISTS sst_categorias (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL UNIQUE,
            color VARCHAR(7) DEFAULT '#007bff',
            icono VARCHAR(50) DEFAULT 'fas fa-folder',
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    
    # Tabla de contenido SST MEJORADA (con archivos en base de datos)
    query_contenido = """
        CREATE TABLE IF NOT EXISTS sst_contenido (
            id SERIAL PRIMARY KEY,
            titulo VARCHAR(255) NOT NULL,
            descripcion TEXT,
            tipo VARCHAR(50) NOT NULL,
            archivo_url TEXT,
            archivo_data BYTEA,
            archivo_nombre VARCHAR(255),
            archivo_tipo VARCHAR(100),
            archivo_tamano INTEGER,
            video_url TEXT,
            categoria_id INTEGER REFERENCES sst_categorias(id) ON DELETE SET NULL,
            es_obligatorio BOOLEAN DEFAULT FALSE,
            tags TEXT,
            fecha_publicacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario_creador INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    
    try:
        # Crear tabla de categorías SST
        ejecutar_consulta(query_categorias, commit=True)
        print("✅ Tabla sst_categorias creada")
        
        # Crear tabla de contenido SST MEJORADA
        ejecutar_consulta(query_contenido, commit=True)
        print("✅ Tabla sst_contenido MEJORADA creada")
        
        # Verificar y crear categorías por defecto
        verificar_y_crear_categorias_sst()
        
        print("✅ Tablas SST MEJORADAS creadas correctamente")
        return True
        
    except Exception as e:
        print(f"❌ Error al crear tablas SST: {e}")
        return False

def verificar_y_crear_categorias_sst():
    """Verificar y crear categorías SST por defecto"""
    try:
        resultado = ejecutar_consulta("SELECT COUNT(*) FROM sst_categorias", fetch=True)
        
        if resultado and resultado[0][0] == 0:
            categorias = [
                ('Videos de Capacitación', '#FF6B6B', 'fas fa-video'),
                ('Procedimientos de Seguridad', '#4ECDC4', 'fas fa-file-contract'),
                ('Equipos de Protección Personal', '#FFD166', 'fas fa-hard-hat'),
                ('Seguridad Industrial', '#06D6A0', 'fas fa-helmet-safety'),
                ('Prevención de Incendios', '#EF476F', 'fas fa-fire-extinguisher'),
                ('Normativa Legal', '#118AB2', 'fas fa-gavel')
            ]
            
            for nombre, color, icono in categorias:
                ejecutar_consulta(
                    "INSERT INTO sst_categorias (nombre, color, icono) VALUES (%s, %s, %s)",
                    (nombre, color, icono),
                    commit=True
                )
            
            print(f"✅ {len(categorias)} categorías SST creadas por defecto")
        else:
            print(f"📊 Categorías SST existentes: {resultado[0][0]}")
            
    except Exception as e:
        print(f"❌ Error al verificar/crear categorías SST: {e}")

def obtener_categorias_sst():
    """Obtener todas las categorías SST"""
    try:
        resultado = ejecutar_consulta(
            "SELECT id, nombre, color, icono FROM sst_categorias ORDER BY nombre",
            fetch=True
        )
        return resultado or []
    except Exception as e:
        print(f"❌ Error al obtener categorías SST: {e}")
        return []

def obtener_contenido_sst(filtros=None):
    """Obtener contenido SST con filtros opcionales"""
    try:
        query = """
            SELECT sc.id, sc.titulo, sc.descripcion, sc.tipo, sc.archivo_url, 
                   sc.archivo_data, sc.archivo_nombre, sc.archivo_tipo, sc.archivo_tamano,
                   sc.video_url, sc.categoria_id, sc.es_obligatorio, sc.tags,
                   sc.fecha_publicacion, sc.usuario_creador,
                   cat.nombre as categoria_nombre, cat.color as categoria_color,
                   u.usuario as creador_nombre
            FROM sst_contenido sc
            LEFT JOIN sst_categorias cat ON sc.categoria_id = cat.id
            LEFT JOIN usuarios u ON sc.usuario_creador = u.id
            WHERE 1=1
        """
        
        params = []
        
        if filtros:
            if filtros.get('query'):
                query += " AND (sc.titulo ILIKE %s OR sc.descripcion ILIKE %s OR sc.tags ILIKE %s)"
                search_term = f"%{filtros['query']}%"
                params.extend([search_term, search_term, search_term])
            
            if filtros.get('categoria'):
                query += " AND sc.categoria_id = %s"
                params.append(filtros['categoria'])
            
            if filtros.get('tipo'):
                if filtros['tipo'] == 'obligatorio':
                    query += " AND sc.es_obligatorio = TRUE"
                elif filtros['tipo'] == 'video':
                    query += " AND sc.tipo = 'video'"
                elif filtros['tipo'] == 'documento':
                    query += " AND sc.tipo IN ('documento', 'presentacion')"
        
        query += " ORDER BY sc.fecha_publicacion DESC"
        
        resultado = ejecutar_consulta(query, params, fetch=True)
        return resultado or []
        
    except Exception as e:
        print(f"❌ Error al obtener contenido SST: {e}")
        return []

def guardar_archivo_en_bd(file):
    """Guardar archivo en la base de datos"""
    try:
        # Leer el archivo
        file_data = file.read()
        file_name = secure_filename(file.filename)
        file_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
        file_size = len(file_data)
        
        archivo_data = {
            'data': file_data,
            'nombre': file_name,
            'tipo': file_type,
            'tamano': file_size
        }
        
        print(f"✅ Archivo preparado para BD: {file_name} ({file_size} bytes)")
        return archivo_data
        
    except Exception as e:
        print(f"❌ Error al guardar archivo en BD: {e}")
        return None

def insertar_contenido_con_archivo(titulo, descripcion, tipo, categoria_id, es_obligatorio, 
                                   tags, usuario_creador, archivo_data=None, video_url=None, archivo_url=None):
    """Insertar contenido SST con archivo en base de datos"""
    try:
        if archivo_data:
            # Insertar con archivo en base de datos
            query = """
                INSERT INTO sst_contenido 
                (titulo, descripcion, tipo, archivo_url, archivo_data, archivo_nombre, 
                 archivo_tipo, archivo_tamano, video_url, categoria_id, es_obligatorio, 
                 tags, usuario_creador)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                titulo, descripcion, tipo, archivo_url,
                psycopg2.Binary(archivo_data['data']), archivo_data['nombre'],
                archivo_data['tipo'], archivo_data['tamano'],
                video_url, categoria_id, es_obligatorio, tags, usuario_creador
            )
        else:
            # Insertar sin archivo (solo URLs)
            query = """
                INSERT INTO sst_contenido 
                (titulo, descripcion, tipo, archivo_url, video_url, categoria_id, 
                 es_obligatorio, tags, usuario_creador)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                titulo, descripcion, tipo, archivo_url, video_url,
                categoria_id, es_obligatorio, tags, usuario_creador
            )
        
        ejecutar_consulta(query, params, commit=True)
        print(f"✅ Contenido SST insertado correctamente: {titulo}")
        return True
        
    except Exception as e:
        print(f"❌ Error al insertar contenido SST: {e}")
        return False

def obtener_archivo_desde_bd(contenido_id):
    """Obtener archivo desde la base de datos"""
    try:
        query = """
            SELECT archivo_data, archivo_nombre, archivo_tipo, archivo_tamano
            FROM sst_contenido
            WHERE id = %s AND archivo_data IS NOT NULL
        """
        
        resultado = ejecutar_consulta(query, (contenido_id,), fetch=True)
        
        if resultado and resultado[0]:
            archivo = {
                'data': resultado[0][0],
                'nombre': resultado[0][1],
                'tipo': resultado[0][2],
                'tamano': resultado[0][3]
            }
            print(f"✅ Archivo obtenido de BD: {archivo['nombre']} ({archivo['tamano']} bytes)")
            return archivo
        
        print(f"⚠️ No se encontró archivo para contenido ID: {contenido_id}")
        return None
        
    except Exception as e:
        print(f"❌ Error al obtener archivo desde BD: {e}")
        return None
