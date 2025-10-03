import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash
from config import Config
import json

def crear_conexion():
    """
    Crea y retorna una conexión a la base de datos MySQL
    """
    try:
        conexion = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            database=Config.MYSQL_DB,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci'
        )
        return conexion
    except Error as e:
        print(f"❌ Error al conectar a MySQL: {e}")
        return None

def crear_tablas():
    """
    Crea las tablas necesarias en la base de datos
    e inserta los usuarios por defecto
    """
    conexion = crear_conexion()
    if conexion:
        try:
            cursor = conexion.cursor()

            # Crear base de datos si no existe
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {Config.MYSQL_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute(f"USE {Config.MYSQL_DB}")

            # Crear tabla usuarios
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    usuario VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    rol ENUM('admin', 'asesor') NOT NULL,
                    permisos TEXT,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            ''')
            print("✅ Tabla 'usuarios' creada")

            # Crear tabla fichas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fichas (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    categoria ENUM('TV', 'Internet', 'Equipo') NOT NULL,
                    problema VARCHAR(255) NOT NULL,
                    descripcion TEXT,
                    causas TEXT,
                    solucion TEXT,
                    palabras_clave TEXT,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            ''')
            print("✅ Tabla 'fichas' creada")

            # Crear usuarios con contraseñas hasheadas CORRECTAMENTE
            admin_pass = generate_password_hash('admin123')
            asesor_pass = generate_password_hash('asesor123')
            
            default_perms = json.dumps({
                'ver_fichas': True,
                'agregar_fichas': False,
                'editar_fichas': False,
                'eliminar_fichas': False,
                'cambiar_password': True
            })

            # Insertar o actualizar usuario admin
            cursor.execute('''
                INSERT INTO usuarios (usuario, password, rol, permisos)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    password = VALUES(password), 
                    rol = VALUES(rol),
                    permisos = VALUES(permisos)
            ''', ('admin', admin_pass, 'admin', default_perms))

            # Insertar o actualizar usuario asesor
            cursor.execute('''
                INSERT INTO usuarios (usuario, password, rol, permisos)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    password = VALUES(password), 
                    rol = VALUES(rol),
                    permisos = VALUES(permisos)
            ''', ('asesor', asesor_pass, 'asesor', default_perms))

            # Insertar algunas fichas de ejemplo
            cursor.execute("SELECT COUNT(*) FROM fichas")
            if cursor.fetchone()[0] == 0:
                fichas_ejemplo = [
                    ('TV', 'No hay señal en el televisor', 
                     'El usuario reporta pantalla negra o sin señal', 
                     'Cable HDMI mal conectado|Decodificador apagado|Problema de alimentación',
                     '1. Verificar que el decodificador esté encendido\n2. Revisar conexiones de cables (HDMI, energía)\n3. Reiniciar el decodificador',
                     'pantalla negra,sin señal,decodificador apagado'),
                    
                    ('Internet', 'Internet lento o intermitente',
                     'El usuario reporta velocidad baja o conexión que se cae',
                     'Router sobrecargado|Interferencia de señal|Problema con el proveedor',
                     '1. Reiniciar el router\n2. Verificar conexión por cable\n3. Comprobar velocidad con test de velocidad',
                     'internet lento,velocidad baja,conexión intermitente')
                ]
                
                for ficha in fichas_ejemplo:
                    cursor.execute(
                        "INSERT INTO fichas (categoria, problema, descripcion, causas, solucion, palabras_clave) VALUES (%s, %s, %s, %s, %s, %s)",
                        ficha
                    )
                print("✅ Fichas de ejemplo insertadas")

            conexion.commit()
            print("🎉 Base de datos inicializada correctamente")
            print("📋 Credenciales:")
            print("   Admin: usuario 'admin' / contraseña 'admin123'")
            print("   Asesor: usuario 'asesor' / contraseña 'asesor123'")

        except Error as e:
            print(f"❌ Error al crear tablas: {e}")
            conexion.rollback()
        finally:
            cursor.close()
            conexion.close()

def verificar_usuarios():
    """
    Verifica que los usuarios se hayan creado correctamente
    """
    conexion = crear_conexion()
    if conexion:
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("SELECT usuario, LENGTH(password) as pass_length FROM usuarios")
            usuarios = cursor.fetchall()
            
            print("🔍 Verificación de usuarios:")
            for usuario in usuarios:
                status = "✅" if usuario['pass_length'] > 0 else "❌"
                print(f"   {status} {usuario['usuario']} - Longitud password: {usuario['pass_length']}")
            
            return usuarios
        except Error as e:
            print(f"❌ Error al verificar usuarios: {e}")
            return None
        finally:
            cursor.close()
            conexion.close()

# Para ejecutar este módulo directamente
if __name__ == "__main__":
    print("🔧 Inicializando base de datos...")
    crear_tablas()
    verificar_usuarios()
