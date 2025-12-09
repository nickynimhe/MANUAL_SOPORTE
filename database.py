import psycopg2
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from config import Config
import mimetypes
import time
import logging

# Configurar logging
logger = logging.getLogger(__name__)

def crear_conexion():
    """Crear conexión a la base de datos PostgreSQL con reintentos y SSL mejorado"""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Configuración mejorada para Render PostgreSQL
            conexion = psycopg2.connect(
                host=Config.DB_HOST,
                database=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                port=Config.DB_PORT,
                sslmode='require',  # Forzar SSL para Render
                connect_timeout=30,  # Timeout de conexión aumentado
                keepalives=1,
                keepalives_idle=60,  # Mantener conexión activa
                keepalives_interval=10,
                keepalives_count=5,
                options='-c statement_timeout=60000'  # Timeout de consulta de 60 segundos
            )
            
            # Configurar para manejar archivos grandes
            conexion.autocommit = False
            
            logger.info(f"✅ Conexión a BD establecida (intento {attempt + 1})")
            return conexion
            
        except psycopg2.OperationalError as e:
            logger.warning(f"⚠️  Error de conexión (intento {attempt + 1}): {e}")
            
            # Verificar si es error SSL
            error_str = str(e).lower()
            is_ssl_error = any(keyword in error_str for keyword in ['ssl', 'connection', 'closed'])
            
            if is_ssl_error and attempt < max_retries - 1:
                logger.info(f"🔄 Reintentando conexión SSL en {retry_delay} segundos...")
                time.sleep(retry_delay * (attempt + 1))  # Retry exponencial
                continue
            else:
                logger.error(f"❌ Error al conectar a la base de datos después de {max_retries} intentos: {e}")
                raise
                
        except Exception as e:
            logger.error(f"❌ Error inesperado al conectar: {e}")
            raise

def ejecutar_consulta(query, params=None, fetch=False, commit=False):
    """Ejecuta una consulta SQL con manejo de errores y depuración - VERSIÓN MEJORADA"""
    conexion = None
    cursor = None
    resultado = None
    
    try:
        # Crear conexión con reintentos
        conexion = crear_conexion()
        if not conexion:
            logger.error("❌ ERROR SQL: No se pudo crear la conexión")
            return None
        
        cursor = conexion.cursor()
        
        # Depuración
        logger.debug(f"📊 DEBUG SQL [Inicio]")
        logger.debug(f"📊 DEBUG SQL Query: {query[:200]}...")
        logger.debug(f"📊 DEBUG SQL Params: {params}")
        
        # Verificar si es una operación con archivos grandes
        is_large_operation = False
        if params:
            for param in params:
                if isinstance(param, bytes) and len(param) > 5 * 1024 * 1024:  # >5MB
                    is_large_operation = True
                    logger.info(f"📦 Operación con archivo grande detectada: {len(param)} bytes")
                    break
        
        # Ejecutar consulta
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        # Manejar resultado según tipo de operación
        if commit:
            # Para operaciones con archivos grandes, commit inmediato
            if is_large_operation:
                logger.info("🔄 Realizando commit inmediato para archivo grande...")
            
            conexion.commit()
            resultado = True
            logger.debug(f"📊 DEBUG SQL [Commit OK] - Filas afectadas: {cursor.rowcount}")
        elif fetch:
            resultado = cursor.fetchall()
            logger.debug(f"📊 DEBUG SQL [Fetch OK] - {len(resultado) if resultado else 0} filas obtenidas")
        else:
            resultado = True
            logger.debug(f"📊 DEBUG SQL [Execute OK] - Filas afectadas: {cursor.rowcount}")
            
    except psycopg2.OperationalError as e:
        logger.error(f"❌ ERROR SQL (Operacional): {e}")
        logger.error(f"❌ ERROR SQL Query: {query[:500]}")
        logger.error(f"❌ ERROR SQL Params: {'[DATOS BINARIOS OMITIDOS]' if any(isinstance(p, bytes) for p in params or []) else params}")
        
        # Rollback en caso de error con commit
        if commit and conexion:
            try:
                conexion.rollback()
                logger.debug("📊 DEBUG SQL: Rollback realizado")
            except Exception as rollback_error:
                logger.error(f"❌ Error en rollback: {rollback_error}")
        
        # Re-lanzar la excepción para manejo superior
        raise e
        
    except psycopg2.DatabaseError as e:
        logger.error(f"❌ ERROR SQL (Database): {e}")
        logger.error(f"❌ ERROR SQL Query: {query[:500]}")
        
        if commit and conexion:
            try:
                conexion.rollback()
                logger.debug("📊 DEBUG SQL: Rollback realizado")
            except:
                pass
        
        raise e
        
    except Exception as e:
        logger.error(f"❌ ERROR SQL (General): {e}")
        logger.error(f"❌ ERROR SQL Query: {query[:500]}")
        
        if commit and conexion:
            try:
                conexion.rollback()
                logger.debug("📊 DEBUG SQL: Rollback realizado")
            except:
                pass
        
        raise e
        
    finally:
        # Cerrar cursor y conexión
        try:
            if cursor:
                cursor.close()
                logger.debug("📊 DEBUG SQL: Cursor cerrado")
        except Exception as e:
            logger.warning(f"⚠️  Error al cerrar cursor: {e}")
            
        try:
            if conexion:
                conexion.close()
                logger.debug("📊 DEBUG SQL: Conexión cerrada")
        except Exception as e:
            logger.warning(f"⚠️  Error al cerrar conexión: {e}")
    
    return resultado

def crear_tablas():
    """Crear todas las tablas necesarias si no existen"""
    logger.info("🔧 Creando/verificando tablas...")
    
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
        logger.info("✅ Tabla de usuarios creada/existe correctamente")
        
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
            logger.info("✅ Usuario admin creado por defecto")
        
        # Crear tabla de fichas
        ejecutar_consulta(query_fichas, commit=True)
        logger.info("✅ Tabla de fichas creada/existe correctamente")
        
        # Crear tablas SST MEJORADAS
        crear_tablas_sst_mejoradas()
        
        logger.info("✅ Todas las tablas creadas/verificadas")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al crear tablas: {e}")
        return False

def crear_tablas_sst_mejoradas():
    """Crear tablas SST con estructura MEJORADA (archivos en base de datos)"""
    logger.info("🔧 Creando/verificando tablas SST...")
    
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
        logger.info("✅ Tabla sst_categorias creada")
        
        # Crear tabla de contenido SST MEJORADA
        ejecutar_consulta(query_contenido, commit=True)
        logger.info("✅ Tabla sst_contenido MEJORADA creada")
        
        # Verificar y crear categorías por defecto
        verificar_y_crear_categorias_sst()
        
        logger.info("✅ Tablas SST MEJORADAS creadas correctamente")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al crear tablas SST: {e}")
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
            
            logger.info(f"✅ {len(categorias)} categorías SST creadas por defecto")
        else:
            logger.info(f"📊 Categorías SST existentes: {resultado[0][0]}")
            
    except Exception as e:
        logger.error(f"❌ Error al verificar/crear categorías SST: {e}")

def obtener_categorias_sst():
    """Obtener todas las categorías SST"""
    try:
        resultado = ejecutar_consulta(
            "SELECT id, nombre, color, icono FROM sst_categorias ORDER BY nombre",
            fetch=True
        )
        return resultado or []
    except Exception as e:
        logger.error(f"❌ Error al obtener categorías SST: {e}")
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
        logger.error(f"❌ Error al obtener contenido SST: {e}")
        return []

def guardar_archivo_en_bd(file):
    """Guardar archivo en la base de datos - VERSIÓN OPTIMIZADA"""
    try:
        # Leer el archivo en chunks para archivos grandes
        file.seek(0, 2)  # Ir al final
        file_size = file.tell()
        file.seek(0)  # Volver al inicio
        
        logger.info(f"📦 Procesando archivo: {file.filename} ({file_size} bytes)")
        
        # Estrategia diferente según tamaño
        if file_size > 10 * 1024 * 1024:  # >10MB
            logger.info("📦 Archivo grande detectado, leyendo en chunks...")
            
            # Leer en chunks para evitar sobrecargar memoria
            chunks = []
            while True:
                chunk = file.read(8192)  # Chunks de 8KB
                if not chunk:
                    break
                chunks.append(chunk)
            
            file_data = b''.join(chunks)
        else:
            # Para archivos pequeños, lectura normal
            file_data = file.read()
        
        file_name = secure_filename(file.filename)
        file_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
        
        archivo_data = {
            'data': file_data,
            'nombre': file_name,
            'tipo': file_type,
            'tamano': len(file_data)
        }
        
        logger.info(f"✅ Archivo preparado para BD: {file_name} ({len(file_data)} bytes)")
        return archivo_data
        
    except Exception as e:
        logger.error(f"❌ Error al guardar archivo en BD: {e}")
        return None

def insertar_contenido_con_archivo(titulo, descripcion, tipo, categoria_id, es_obligatorio, 
                                   tags, usuario_creador, archivo_data=None, video_url=None, archivo_url=None):
    """Insertar contenido SST con archivo en base de datos - VERSIÓN MEJORADA"""
    try:
        if archivo_data:
            # Verificar tamaño del archivo
            file_size = archivo_data['tamano']
            
            if file_size > 5 * 1024 * 1024:  # >5MB
                logger.info(f"📦 Insertando archivo grande: {archivo_data['nombre']} ({file_size} bytes)")
                
                # Para archivos grandes, usar transacción explícita
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
                
                # Ejecutar con commit inmediato
                ejecutar_consulta(query, params, commit=True)
                
            else:
                # Para archivos pequeños, procedimiento normal
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
                
                ejecutar_consulta(query, params, commit=True)
                
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
        
        logger.info(f"✅ Contenido SST insertado correctamente: {titulo}")
        return True
        
    except psycopg2.OperationalError as e:
        logger.error(f"❌ Error SSL/operacional al insertar contenido SST: {e}")
        # Intentar estrategia alternativa para archivos grandes
        if archivo_data and archivo_data['tamano'] > 5 * 1024 * 1024:
            logger.info("🔄 Intentando estrategia alternativa para archivo grande...")
            return insertar_contenido_sin_archivo_primero(titulo, descripcion, tipo, categoria_id, 
                                                         es_obligatorio, tags, usuario_creador, 
                                                         video_url, archivo_url, archivo_data)
        return False
        
    except Exception as e:
        logger.error(f"❌ Error al insertar contenido SST: {e}")
        return False

def insertar_contenido_sin_archivo_primero(titulo, descripcion, tipo, categoria_id, es_obligatorio, 
                                          tags, usuario_creador, video_url, archivo_url, archivo_data):
    """Estrategia alternativa: Insertar primero sin archivo, luego actualizar"""
    try:
        # Paso 1: Insertar sin archivo
        query1 = """
            INSERT INTO sst_contenido 
            (titulo, descripcion, tipo, archivo_url, video_url, categoria_id, 
             es_obligatorio, tags, usuario_creador)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        params1 = (
            titulo, descripcion, tipo, archivo_url, video_url,
            categoria_id, es_obligatorio, tags, usuario_creador
        )
        
        resultado = ejecutar_consulta(query1, params1, fetch=True, commit=True)
        
        if not resultado:
            return False
        
        contenido_id = resultado[0][0]
        logger.info(f"✅ Contenido creado (sin archivo) con ID: {contenido_id}")
        
        # Paso 2: Actualizar con archivo (opcional, si es necesario)
        if archivo_data:
            # Intentar actualizar en un paso separado
            time.sleep(1)  # Pequeña pausa
            
            query2 = """
                UPDATE sst_contenido 
                SET archivo_data = %s, archivo_nombre = %s, 
                    archivo_tipo = %s, archivo_tamano = %s,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id = %s
            """
            params2 = (
                psycopg2.Binary(archivo_data['data']), archivo_data['nombre'],
                archivo_data['tipo'], archivo_data['tamano'],
                contenido_id
            )
            
            ejecutar_consulta(query2, params2, commit=True)
            logger.info(f"✅ Archivo actualizado para contenido ID: {contenido_id}")
        
        logger.info(f"✅ Contenido SST insertado (estrategia alternativa): {titulo}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en estrategia alternativa: {e}")
        return False

def obtener_archivo_desde_bd(contenido_id):
    """Obtener archivo desde la base de datos - VERSIÓN MEJORADA"""
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
            logger.info(f"✅ Archivo obtenido de BD: {archivo['nombre']} ({archivo['tamano']} bytes)")
            return archivo
        
        logger.warning(f"⚠️ No se encontró archivo para contenido ID: {contenido_id}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Error al obtener archivo desde BD: {e}")
        return None
