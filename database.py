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

def ejecutar_consulta(query, params=None, fetch=False, commit=False):
    """Función helper para ejecutar consultas de forma segura"""
    conexion = None
    cursor = None
    try:
        conexion = crear_conexion()
        if conexion:
            cursor = conexion.cursor()
            cursor.execute(query, params or ())
            
            if commit:
                conexion.commit()
                return True
            elif fetch:
                return cursor.fetchall()
            else:
                return cursor.rowcount
                
    except Exception as e:
        print(f"❌ Error en consulta: {e}")
        if conexion:
            conexion.rollback()
        return None
    finally:
        if cursor:
            cursor.close()
        if conexion:
            conexion.close()

def crear_tabla_usuarios():
    """Crear tabla de usuarios si no existe"""
    try:
        # Crear tabla
        ejecutar_consulta('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                usuario VARCHAR(50) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                rol VARCHAR(20) DEFAULT 'usuario',
                permisos TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''', commit=True)
        
        # Insertar usuario admin por defecto si no existe
        from werkzeug.security import generate_password_hash
        resultado = ejecutar_consulta(
            "SELECT COUNT(*) FROM usuarios WHERE usuario = 'admin'",
            fetch=True
        )
        
        if resultado and resultado[0][0] == 0:
            password_hash = generate_password_hash('admin123')
            ejecutar_consulta(
                "INSERT INTO usuarios (usuario, password, rol) VALUES (%s, %s, %s)",
                ('admin', password_hash, 'admin'),
                commit=True
            )
            print("✅ Usuario admin creado: admin / admin123")
        
        print("✅ Tabla de usuarios creada/existe correctamente")
        
    except Exception as e:
        print(f"❌ Error al crear tabla usuarios: {e}")

def crear_tabla_fichas():
    """Crear tabla de fichas técnicas si no existe"""
    try:
        ejecutar_consulta('''
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
        ''', commit=True)
        
        print("✅ Tabla de fichas creada/existe correctamente")
        
    except Exception as e:
        print(f"❌ Error al crear tabla fichas: {e}")

def crear_tablas_sst():
    """Crear tablas para el módulo SST"""
    try:
        print("🔧 Creando/verificando tablas SST...")
        
        # Tabla de categorías SST
        ejecutar_consulta("""
            CREATE TABLE IF NOT EXISTS sst_categorias (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL UNIQUE,
                color VARCHAR(7) DEFAULT '#007bff',
                icono VARCHAR(50) DEFAULT 'fa-folder',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, commit=True)
        
        # Tabla de contenido SST
        ejecutar_consulte("""
            CREATE TABLE IF NOT EXISTS sst_contenido (
                id SERIAL PRIMARY KEY,
                titulo VARCHAR(255) NOT NULL,
                descripcion TEXT,
                tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('video', 'documento', 'imagen', 'enlace')),
                archivo_url VARCHAR(500),
                archivo_local VARCHAR(500),  <!-- Aumentado de 255 a 500 -->
                video_url VARCHAR(500),
                categoria_id INTEGER REFERENCES sst_categorias(id),
                es_obligatorio BOOLEAN DEFAULT FALSE,
                tags VARCHAR(500),
                fecha_publicacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usuario_creador INTEGER REFERENCES usuarios(id),
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, commit=True)
        
        print("✅ Tablas SST base creadas correctamente")
        
    except Exception as e:
        print(f"❌ Error al crear tablas SST: {e}")

def verificar_y_crear_categorias_sst():
    """Verificar y crear categorías SST si no existen"""
    try:
        resultado = ejecutar_consulta("SELECT COUNT(*) FROM sst_categorias", fetch=True)
        count = resultado[0][0] if resultado else 0
        
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
                    ejecutar_consulte(
                        "INSERT INTO sst_categorias (nombre, color, icono) VALUES (%s, %s, %s)",
                        (nombre, color, icono),
                        commit=True
                    )
                    categorias_insertadas += 1
                    print(f"✅ Categoría '{nombre}' creada")
                except Exception as e:
                    print(f"⚠ Error al crear categoría '{nombre}': {e}")
                    continue
            
            print(f"✅ {categorias_insertadas} categorías SST creadas correctamente")
        else:
            print(f"✅ Ya existen {count} categorías SST")
            
    except Exception as e:
        print(f"❌ Error al verificar categorías SST: {e}")

def crear_tablas():
    """Función principal para crear todas las tablas"""
    print("🔧 Creando/verificando tablas...")
    
    crear_tabla_usuarios()
    crear_tabla_fichas() 
    crear_tablas_sst()
    verificar_y_crear_categorias_sst()
    
    print("✅ Todas las tablas creadas/verificadas")

def obtener_categorias_sst():
    """Obtener todas las categorías SST"""
    try:
        resultado = ejecutar_consulte(
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
            SELECT sc.*, cat.nombre as categoria_nombre, cat.color as categoria_color,
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
                params.extend([f'%{filtros["query"]}%', f'%{filtros["query"]}%', f'%{filtros["query"]}%'])
            
            if filtros.get('categoria'):
                query += " AND sc.categoria_id = %s"
                params.append(int(filtros['categoria']))
            
            if filtros.get('tipo'):
                query += " AND sc.tipo = %s"
                params.append(filtros['tipo'])
        
        query += " ORDER BY sc.fecha_publicacion DESC"
        
        resultado = ejecutar_consulte(query, params, fetch=True)
        return resultado or []
        
    except Exception as e:
        print(f"❌ Error al obtener contenido SST: {e}")
        return []

# Si se ejecuta este archivo directamente
if __name__ == '__main__':
    print("🔧 Ejecutando configuración de base de datos...")
    crear_tablas()
