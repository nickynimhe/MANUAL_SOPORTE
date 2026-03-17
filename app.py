from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, send_from_directory, make_response, Response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from database import crear_conexion, crear_tablas, verificar_y_crear_categorias_sst, obtener_categorias_sst, obtener_contenido_sst, ejecutar_consulta, guardar_archivo_en_bd, insertar_contenido_con_archivo, obtener_archivo_desde_bd
from config import Config
from werkzeug.security import check_password_hash, generate_password_hash
import psycopg2
import json
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import urllib.parse
import mimetypes
from io import BytesIO
import time
import logging
from functools import wraps

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== DECORADOR DE REINTENTO PARA ERRORES SSL =====
def retry_on_ssl_error(max_retries=2, delay=3):
    """Decorador para reintentar operaciones con errores SSL"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    # Verificar si es error SSL o de conexión
                    is_ssl_error = any(keyword in error_str for keyword in ['ssl', 'connection', 'closed'])
                    
                    if is_ssl_error and attempt < max_retries - 1:
                        logger.warning(f"⚠️  Error SSL en {func.__name__} (intento {attempt + 1}), reintentando en {delay} segundos...")
                        time.sleep(delay * (attempt + 1))  # Retry exponencial
                        continue
                    else:
                        # Si es otro error o ya agotamos reintentos, relanzar
                        logger.error(f"❌ Error en {func.__name__} después de {attempt + 1} intentos: {e}")
                        raise
            return None
        return wrapper
    return decorator

# ===== CONFIGURACIÓN DE LA APLICACIÓN =====
app = Flask(__name__)
app.config.from_object(Config)

# ===== CONFIGURACIÓN PARA SUBIDA DE ARCHIVOS SST =====
app.config['UPLOAD_FOLDER_SST'] = 'static/uploads/sst'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB máximo
app.config['ALLOWED_EXTENSIONS'] = {
    'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
    'jpg', 'jpeg', 'png', 'gif', 'mp4', 'avi', 'mov', 'mkv', 'webm'
}

# Crear directorio de uploads si no existe
upload_path = app.config['UPLOAD_FOLDER_SST']
os.makedirs(upload_path, exist_ok=True)
print(f"📁 Directorio de uploads: {upload_path}")
print(f"📁 ¿Existe el directorio?: {os.path.exists(upload_path)}")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generar_nombre_seguro(filename):
    """Generar nombre seguro para archivo con timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name, ext = os.path.splitext(secure_filename(filename))
    name = name.replace(' ', '_').replace('-', '_')
    return f"{timestamp}_{name}{ext}"

# ===== CONFIGURACIÓN FLASK-LOGIN =====
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'

# ===== CONTEXT PROCESSORS =====
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

@app.context_processor
def inject_permissions():
    def tiene_permiso(permiso):
        if current_user.is_authenticated:
            if hasattr(current_user, 'permisos'):
                return current_user.permisos.get(permiso, False)
        return False
    
    def puede_acceder_modulo(modulo):
        if current_user.is_authenticated:
            if current_user.rol == 'admin':
                return True
            if modulo == 'sst' and current_user.rol in ['admin', 'sst']:
                return True
            if modulo == 'soporte' and current_user.rol in ['admin', 'soporte']:
                return True
            if modulo == 'dashboard' and current_user.rol == 'admin':
                return True
        return False
    
    def obtener_modulo_principal():
        if current_user.is_authenticated:
            return getattr(current_user, 'modulo_principal', 'soporte')
        return 'soporte'
    
    def obtener_rol_display():
        """Obtener nombre legible del rol"""
        if current_user.is_authenticated:
            rol = current_user.rol
            display_map = {
                'admin': 'Administrador',
                'sst': 'SST',
                'soporte': 'Soporte Técnico'
            }
            return display_map.get(rol, rol.capitalize())
        return ''
    
    return dict(
        tiene_permiso=tiene_permiso,
        puede_acceder_modulo=puede_acceder_modulo,
        obtener_modulo_principal=obtener_modulo_principal,
        obtener_rol_display=obtener_rol_display
    )

# ===== FILTROS TEMPLATE =====
@app.template_filter('format_date')
def format_date_filter(date_value, format='%d/%m/%Y'):
    """Filtro para formatear fechas - MANEJA STRINGS, DATETIME Y NONE"""
    if date_value is None:
        return 'Sin fecha'
    
    try:
        # Si ya es datetime, formatear directamente
        if hasattr(date_value, 'strftime'):
            return date_value.strftime(format)
        
        # Si es string, intentar convertirlo
        if isinstance(date_value, str):
            # Limpiar el string (quitar microsegundos si existen)
            date_str = date_value.split('.')[0] if '.' in date_value else date_value
            
            # Intentar diferentes formatos comunes de PostgreSQL
            formats_to_try = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%d %H:%M',
                '%Y-%m-%d',
                '%d/%m/%Y %H:%M:%S',
                '%d/%m/%Y %H:%M',
                '%d/%m/%Y'
            ]
            
            for fmt in formats_to_try:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime(format)
                except ValueError:
                    continue
            
            # Si no se pudo parsear, devolver los primeros caracteres
            if len(date_str) >= 10:
                return date_str[:10] + " " + date_str[11:16] if len(date_str) >= 16 else date_str[:10]
            return date_str
        
        # Para otros tipos, devolver string
        return str(date_value)
        
    except Exception as e:
        logger.error(f"❌ Error en format_date_filter: {e}")
        return 'Fecha inválida'

@app.template_filter('safe_tags')
def safe_tags_filter(tags_value):
    """Filtro seguro para manejar tags"""
    if tags_value is None:
        return []
    
    if isinstance(tags_value, str):
        return [tag.strip() for tag in tags_value.split(',') if tag.strip()]
    elif isinstance(tags_value, (int, float)):
        return [str(tags_value)]
    else:
        return []

@app.template_filter('is_video_url')
def is_video_url_filter(url):
    """Verificar si una URL es de video"""
    if not url:
        return False
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
    return any(url.lower().endswith(ext) for ext in video_extensions)

@app.template_filter('file_extension')
def file_extension_filter(filename):
    """Obtener extensión del archivo"""
    if not filename:
        return ''
    return os.path.splitext(filename)[1].lower().replace('.', '')

# ===== MODELO DE USUARIO MEJORADO =====
class User(UserMixin):
    def __init__(self, id, usuario, rol, modulo_principal, permisos=None):
        self.id = id
        self.usuario = usuario
        self.rol_original = rol
        self.rol = self._normalizar_rol(rol)  # Rol normalizado
        self.modulo_principal = modulo_principal if modulo_principal else 'soporte'
        self.redireccionar_sst = False
        
        # Definir permisos según rol normalizado
        self.permisos = self._obtener_permisos_base()
        
        # Sobreescribir con permisos personalizados si existen
        if permisos:
            self.permisos.update(permisos)

    def _normalizar_rol(self, rol):
        """Normalizar diferentes variaciones de roles a valores estándar"""
        if not rol:
            return 'soporte'
        
        rol_str = str(rol).strip().lower()
        
        # Mapear variaciones comunes
        if rol_str in ['admin', 'administrador', 'administradora', 'superadmin', 'super usuario']:
            return 'admin'
        elif rol_str in ['sst', 'seguridad', 'salud', 'salud y seguridad', 'seguridad y salud', 'seguridad laboral']:
            return 'sst'
        elif rol_str in ['soporte', 'tecnico', 'técnico', 'asistente', 'ayudante', 'operador', 'soporte técnico']:
            return 'soporte'
        else:
            # Si no reconocemos el rol, usar soporte por defecto
            logger.warning(f"Rol desconocido '{rol}', normalizando a 'soporte'")
            return 'soporte'

    def _obtener_permisos_base(self):
        """Definir permisos base según rol normalizado"""
        if self.rol == 'admin':
            return {
                'ver_fichas': True,
                'agregar_fichas': True,
                'editar_fichas': True,
                'eliminar_fichas': True,
                'cambiar_password': True,
                'gestion_usuarios': True,
                'acceder_sst': True,
                'gestionar_plan_anual': True,
                'agregar_evidencias': True,
                'acceder_soporte': True,
                'acceder_dashboard': True,
                'administrar_sistema': True
            }
        elif self.rol == 'sst':
            return {
                'ver_fichas': False,
                'agregar_fichas': False,
                'editar_fichas': False,
                'eliminar_fichas': False,
                'cambiar_password': True,
                'gestion_usuarios': False,
                'acceder_sst': True,
                'gestionar_plan_anual': True,
                'agregar_evidencias': True,
                'acceder_soporte': False,
                'acceder_dashboard': False,
                'administrar_sistema': False
            }
        elif self.rol == 'soporte':
            return {
                'ver_fichas': True,
                'agregar_fichas': True,
                'editar_fichas': True,
                'eliminar_fichas': True,
                'cambiar_password': True,
                'gestion_usuarios': False,
                'acceder_sst': False,
                'gestionar_plan_anual': False,
                'agregar_evidencias': False,
                'acceder_soporte': True,
                'acceder_dashboard': False,
                'administrar_sistema': False
            }
        else:
            # Por defecto, permisos de soporte
            return {
                'ver_fichas': True,
                'agregar_fichas': True,
                'editar_fichas': True,
                'eliminar_fichas': True,
                'cambiar_password': True,
                'gestion_usuarios': False,
                'acceder_sst': False,
                'acceder_soporte': True,
                'acceder_dashboard': False,
                'administrar_sistema': False
            }

    def puede(self, permiso):
        return self.permisos.get(permiso, False)
    
    def get_rol_display(self):
        """Obtener nombre legible del rol"""
        display_map = {
            'admin': 'Administrador',
            'sst': 'SST (Salud y Seguridad)',
            'soporte': 'Soporte Técnico'
        }
        return display_map.get(self.rol, self.rol.capitalize())

@login_manager.user_loader
def load_user(user_id):
    """Cargar usuario desde la base de datos"""
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, usuario, password, rol, modulo_principal, permisos, redireccionar_sst 
            FROM usuarios 
            WHERE id = %s
        """, (user_id,))
        
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user_data:
            user_dict = {
                'id': user_data[0],
                'usuario': user_data[1],
                'rol': user_data[3],
                'modulo_principal': user_data[4],
                'permisos': user_data[5]
            }
            
            # Cargar permisos desde JSON si existen
            permisos = {}
            if user_dict.get('permisos'):
                try:
                    permisos = json.loads(user_dict['permisos'])
                except:
                    permisos = {}
            
            user = User(
                user_dict['id'], 
                user_dict['usuario'], 
                user_dict['rol'],
                user_dict['modulo_principal'],
                permisos
            )
            
            # Agregar campo de redirección SST
            user.redireccionar_sst = user_data[6] if len(user_data) > 6 else False
            
            return user
            
    except Exception as e:
        logger.error(f"Error al cargar usuario: {e}")
    
    return None

# ===== FUNCIÓN DE REDIRECCIÓN MEJORADA =====
def redirect_a_modulo_principal():
    """Redirige al usuario a su módulo principal - VERSIÓN SEGURA"""
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    logger.info(f"Redirigiendo usuario {current_user.usuario} (rol: {current_user.rol})")
    
    # Verificar si hay que redirigir a SST automáticamente
    if hasattr(current_user, 'redireccionar_sst') and current_user.redireccionar_sst:
        logger.info(f"Redirección automática a SST activada para {current_user.usuario}")
        return redirect(url_for('sst_dashboard'))
    
    # Redirección normal según rol
    if current_user.rol == 'admin':
        return redirect(url_for('index'))
    elif current_user.rol == 'sst':
        return redirect(url_for('sst_dashboard'))
    elif current_user.rol == 'soporte':
        return redirect(url_for('index'))
    
    # Si llegamos aquí, usar módulo principal de la BD
    modulo = getattr(current_user, 'modulo_principal', 'soporte')
    if modulo == 'sst':
        return redirect(url_for('sst_dashboard'))
    else:
        return redirect(url_for('index'))

# ===== RUTAS DE AUTENTICACIÓN =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login de usuarios con redirección automática según rol"""
    # Si ya está autenticado, redirigir según su perfil
    if current_user.is_authenticated:
        logger.info(f"Usuario {current_user.usuario} ya autenticado, redirigiendo...")
        return redirect_a_modulo_principal()
    
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        password = request.form.get('password')
        
        try:
            conn = crear_conexion()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, usuario, password, rol, modulo_principal, permisos, redireccionar_sst 
                FROM usuarios 
                WHERE usuario = %s
            """, (usuario,))
            
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user_data and user_data[2] and user_data[2].strip():
                if check_password_hash(user_data[2], password):
                    user_dict = {
                        'id': user_data[0],
                        'usuario': user_data[1],
                        'rol': user_data[3],
                        'modulo_principal': user_data[4],
                        'permisos': user_data[5]
                    }
                    
                    # Cargar permisos desde JSON si existen
                    permisos = {}
                    if user_dict.get('permisos'):
                        try:
                            permisos = json.loads(user_dict['permisos'])
                        except:
                            permisos = {}
                    
                    user = User(
                        user_dict['id'], 
                        user_dict['usuario'], 
                        user_dict['rol'],
                        user_dict['modulo_principal'],
                        permisos
                    )
                    
                    # Agregar campo de redirección SST
                    user.redireccionar_sst = user_data[6] if len(user_data) > 6 else False
                    
                    login_user(user)
                    flash(f'¡Bienvenido {user.usuario}!', 'success')
                    
                    logger.info(f"Login exitoso: {user.usuario}, rol: {user.rol}, módulo: {user.modulo_principal}")
                    
                    # Redirigir según configuración
                    if user.redireccionar_sst and user.puede('acceder_sst'):
                        logger.info(f"Redirección automática a SST para {user.usuario}")
                        return redirect(url_for('sst_dashboard'))
                    
                    return redirect_a_modulo_principal()
                else:
                    flash('Usuario o contraseña incorrectos', 'error')
            else:
                flash('Usuario no encontrado', 'error')
                
        except Exception as e:
            flash(f'Error al iniciar sesión: {str(e)}', 'error')
            logger.error(f"Error en login: {e}")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('login'))

@app.route('/cambiar_password', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    if request.method == 'POST':
        password_actual = request.form['password_actual']
        nueva_password = request.form['nueva_password']
        confirmar_password = request.form['confirmar_password']
        
        if not password_actual or not nueva_password or not confirmar_password:
            flash('Todos los campos son obligatorios', 'error')
            return render_template('cambiar_password.html')
        
        if nueva_password != confirmar_password:
            flash('Las nuevas contraseñas no coinciden', 'error')
            return render_template('cambiar_password.html')
        
        if len(nueva_password) < 6:
            flash('La nueva contraseña debe tener al menos 6 caracteres', 'error')
            return render_template('cambiar_password.html')
        
        try:
            resultado = ejecutar_consulta(
                "SELECT password FROM usuarios WHERE id = %s", 
                (current_user.id,), 
                fetch=True
            )
            
            if resultado and resultado[0] and check_password_hash(resultado[0][0], password_actual):
                hash_nueva_password = generate_password_hash(nueva_password)
                ejecutar_consulta(
                    "UPDATE usuarios SET password = %s WHERE id = %s",
                    (hash_nueva_password, current_user.id),
                    commit=True
                )
                flash('Contraseña actualizada correctamente', 'success')
                return redirect_a_modulo_principal()
            else:
                flash('La contraseña actual es incorrecta', 'error')
                    
        except Exception as e:
            flash('Error al cambiar la contraseña', 'error')
            logger.error(f"Error en cambiar_password: {e}")
    
    return render_template('cambiar_password.html')

# ===== RUTAS DE SOPORTE TÉCNICO =====
@app.route('/')
@login_required
def index():
    """Dashboard principal - solo para admin y soporte"""
    # Si es usuario SST, redirigir a su dashboard
    if current_user.rol == 'sst':
        return redirect(url_for('sst_dashboard'))
    
    # Verificar permisos para soporte
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos para acceder al módulo de soporte', 'error')
        return redirect_a_modulo_principal()
    
    fichas = []
    try:
        resultado = ejecutar_consulta(
            "SELECT * FROM fichas ORDER BY fecha_actualizacion DESC",
            fetch=True
        )
        
        for ficha in resultado or []:
            fichas.append({
                'id': ficha[0],
                'categoria': ficha[1],
                'problema': ficha[2],
                'descripcion': ficha[3],
                'causas': ficha[4],
                'solucion': ficha[5],
                'palabras_clave': ficha[6],
                'fecha_creacion': ficha[7],
                'fecha_actualizacion': ficha[8]
            })
                
    except Exception as e:
        flash('Error al cargar las fichas', 'error')
        logger.error(f"Error en index: {e}")
    
    return render_template('index.html', fichas=fichas, user=current_user)

@app.route('/agregar', methods=['GET', 'POST'])
@login_required
def agregar_ficha():
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos para acceder al módulo de soporte', 'error')
        return redirect_a_modulo_principal()
    
    if not current_user.puede('agregar_fichas'):
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        categoria = request.form.get('categoria', '')
        problema = request.form.get('problema', '')
        descripcion = request.form.get('descripcion', '')
        causas = request.form.get('causas', '')
        solucion = request.form.get('solucion', '')
        palabras_clave = request.form.get('palabras_clave', '')
        
        # Validar campos requeridos
        campos_requeridos = {
            'categoria': categoria,
            'problema': problema, 
            'causas': causas,
            'solucion': solucion
        }
        
        campos_faltantes = [campo for campo, valor in campos_requeridos.items() if not valor]
        
        if campos_faltantes:
            flash('Por favor, complete todos los campos requeridos', 'error')
            return render_template('agregar_ficha.html')
        
        try:
            ejecutar_consulta('''
                INSERT INTO fichas (categoria, problema, descripcion, causas, solucion, palabras_clave)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (categoria, problema, descripcion, causas, solucion, palabras_clave), commit=True)
            
            flash('Ficha agregada correctamente', 'success')
            return redirect(url_for('index'))
                
        except Exception as e:
            flash(f'Error al agregar la ficha: {str(e)}', 'error')
    
    return render_template('agregar_ficha.html')

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_ficha(id):
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos para acceder al módulo de soporte', 'error')
        return redirect_a_modulo_principal()
    
    if not current_user.puede('editar_fichas'):
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('index'))
    
    ficha = None
    
    try:
        if request.method == 'POST':
            categoria = request.form['categoria']
            problema = request.form['problema']
            descripcion = request.form['descripcion']
            causas = request.form['causas']
            solucion = request.form['solucion']
            palabras_clave = request.form['palabras_clave']
            
            # Procesar causas (convertir saltos de línea a |)
            causas_items = [item.strip() for item in causas.split('\n') if item.strip()]
            causas_str = '|'.join(causas_items)
            
            ejecutar_consulta('''
                UPDATE fichas 
                SET categoria=%s, problema=%s, descripcion=%s, 
                causas=%s, solucion=%s, palabras_clave=%s 
                WHERE id=%s
            ''', (categoria, problema, descripcion, causas_str, solucion, palabras_clave, id), commit=True)
            
            flash('Ficha actualizada correctamente', 'success')
            return redirect(url_for('index'))
        
        # GET: Cargar datos de la ficha
        resultado = ejecutar_consulta("SELECT * FROM fichas WHERE id = %s", (id,), fetch=True)
        
        if resultado and resultado[0]:
            ficha_data = resultado[0]
            ficha = {
                'id': ficha_data[0],
                'categoria': ficha_data[1],
                'problema': ficha_data[2],
                'descripcion': ficha_data[3],
                'causas': ficha_data[4],
                'solucion': ficha_data[5],
                'palabras_clave': ficha_data[6],
                'fecha_creacion': ficha_data[7],
                'fecha_actualizacion': ficha_data[8]
            }
            
            # Convertir | de vuelta a saltos de línea para el formulario
            if ficha and ficha['causas']:
                ficha['causas'] = ficha['causas'].replace('|', '\n')
            
    except Exception as e:
        flash('Error al cargar/editar la ficha', 'error')
        logger.error(f"Error en editar_ficha: {e}")
    
    if not ficha:
        flash('Ficha no encontrada', 'error')
        return redirect(url_for('index'))
    
    return render_template('editar_ficha.html', ficha=ficha)

@app.route('/eliminar/<int:id>')
@login_required
def eliminar_ficha(id):
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos para acceder al módulo de soporte', 'error')
        return redirect_a_modulo_principal()
    
    if not current_user.puede('eliminar_fichas'):
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('index'))
    
    try:
        ejecutar_consulta("DELETE FROM fichas WHERE id = %s", (id,), commit=True)
        flash('Ficha eliminada correctamente', 'success')
    except Exception as e:
        flash('Error al eliminar la ficha', 'error')
        logger.error(f"Error en eliminar_ficha: {e}")
    
    return redirect(url_for('index'))

@app.route('/buscar')
@login_required
def buscar():
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos para acceder al módulo de soporte', 'error')
        return redirect_a_modulo_principal()
    
    if not current_user.puede('ver_fichas'):
        flash('No tienes permisos para ver las fichas', 'error')
        return redirect(url_for('index'))
    
    query = request.args.get('q', '')
    categoria = request.args.get('categoria', '')
    
    fichas = []
    try:
        if categoria and query:
            resultado = ejecutar_consulta(
                "SELECT * FROM fichas WHERE categoria = %s AND (problema LIKE %s OR palabras_clave LIKE %s)",
                (categoria, f'%{query}%', f'%{query}%'),
                fetch=True
            )
        elif categoria:
            resultado = ejecutar_consulta(
                "SELECT * FROM fichas WHERE categoria = %s",
                (categoria,),
                fetch=True
            )
        elif query:
            resultado = ejecutar_consulta(
                "SELECT * FROM fichas WHERE problema LIKE %s OR palabras_clave LIKE %s",
                (f'%{query}%', f'%{query}%'),
                fetch=True
            )
        else:
            resultado = ejecutar_consulta(
                "SELECT * FROM fichas ORDER BY fecha_actualizacion DESC",
                fetch=True
            )
        
        # Convertir tuplas a diccionarios
        for ficha in resultado or []:
            fichas.append({
                'id': ficha[0],
                'categoria': ficha[1],
                'problema': ficha[2],
                'descripcion': ficha[3],
                'causas': ficha[4],
                'solucion': ficha[5],
                'palabras_clave': ficha[6],
                'fecha_creacion': ficha[7],
                'fecha_actualizacion': ficha[8]
            })
                
    except Exception as e:
        flash('Error en la búsqueda', 'error')
        logger.error(f"Error en buscar: {e}")
    
    return render_template('buscar.html', fichas=fichas, query=query, categoria=categoria)

@app.route('/ficha/<int:id>')
@login_required
def ver_ficha(id):
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos para acceder al módulo de soporte', 'error')
        return redirect_a_modulo_principal()
    
    if not current_user.puede('ver_fichas'):
        flash('No tienes permisos para ver las fichas', 'error')
        return redirect(url_for('index'))
    
    ficha = None
    try:
        resultado = ejecutar_consulta("SELECT * FROM fichas WHERE id = %s", (id,), fetch=True)
        
        if resultado and resultado[0]:
            ficha_data = resultado[0]
            ficha = {
                'id': ficha_data[0],
                'categoria': ficha_data[1],
                'problema': ficha_data[2],
                'descripcion': ficha_data[3],
                'causas': ficha_data[4],
                'solucion': ficha_data[5],
                'palabras_clave': ficha_data[6],
                'fecha_creacion': ficha_data[7],
                'fecha_actualizacion': ficha_data[8]
            }
                
    except Exception as e:
        flash('Error al cargar la ficha', 'error')
        logger.error(f"Error en ver_ficha: {e}")
    
    if not ficha:
        flash('Ficha no encontrada', 'error')
        return redirect(url_for('index'))
    
    return render_template('ver_ficha.html', ficha=ficha)

# ===== RUTAS DE GESTIÓN DE USUARIOS (Solo Admin) =====
@app.route('/usuarios')
@login_required
def gestion_usuarios():
    """Gestión de usuarios con manejo mejorado de fechas y datos"""
    if not current_user.puede('gestion_usuarios'):
        flash('No tienes permisos para acceder a esta página', 'error')
        return redirect_a_modulo_principal()
    
    usuarios = []
    
    try:
        # Obtener usuarios con información completa
        resultado = ejecutar_consulta("""
            SELECT 
                id, usuario, password, rol, modulo_principal, permisos,
                fecha_creacion, fecha_actualizacion
            FROM usuarios 
            ORDER BY fecha_creacion DESC
        """, fetch=True)
        
        for usuario in resultado or []:
            usuario_dict = {
                'id': usuario[0],
                'usuario': usuario[1],
                'password': usuario[2],
                'rol': usuario[3],
                'modulo_principal': usuario[4] if usuario[4] else 'soporte',
                'permisos': usuario[5],
                'fecha_creacion': usuario[6],
                'fecha_actualizacion': usuario[7]
            }
            
            # Parsear permisos JSON si existen
            permisos_parsed = {}
            if usuario_dict.get('permisos'):
                try:
                    permisos_parsed = json.loads(usuario_dict['permisos'])
                except Exception as e:
                    logger.warning(f"Error al parsear permisos del usuario {usuario_dict['id']}: {e}")
                    permisos_parsed = {}
            
            usuario_dict['permisos_parsed'] = permisos_parsed
            
            usuarios.append(usuario_dict)
                    
    except Exception as e:
        flash('Error al cargar los usuarios', 'error')
        logger.error(f"❌ Error en gestion_usuarios: {e}")
    
    return render_template('gestion_usuarios.html', usuarios=usuarios)

@app.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if not current_user.puede('gestion_usuarios'):
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect_a_modulo_principal()
    
    usuario_data = None
    
    try:
        if request.method == 'POST':
            usuario = request.form['usuario']
            password = request.form['password']
            rol = request.form['rol']
            modulo_principal = request.form['modulo_principal']
            
            permisos = {
                'ver_fichas': 'ver_fichas' in request.form,
                'agregar_fichas': 'agregar_fichas' in request.form,
                'editar_fichas': 'editar_fichas' in request.form,
                'eliminar_fichas': 'eliminar_fichas' in request.form,
                'cambiar_password': True
            }
            
            permisos_json = json.dumps(permisos)
            
            if password:
                hash_password = generate_password_hash(password)
                ejecutar_consulta(
                    "UPDATE usuarios SET usuario = %s, password = %s, rol = %s, modulo_principal = %s, permisos = %s WHERE id = %s",
                    (usuario, hash_password, rol, modulo_principal, permisos_json, id),
                    commit=True
                )
            else:
                ejecutar_consulta(
                    "UPDATE usuarios SET usuario = %s, rol = %s, modulo_principal = %s, permisos = %s WHERE id = %s",
                    (usuario, rol, modulo_principal, permisos_json, id),
                    commit=True
                )
            
            flash('Usuario actualizado correctamente', 'success')
            return redirect(url_for('gestion_usuarios'))
        
        resultado = ejecutar_consulta("SELECT * FROM usuarios WHERE id = %s", (id,), fetch=True)
        
        if resultado and resultado[0]:
            usuario = resultado[0]
            usuario_data = {
                'id': usuario[0],
                'usuario': usuario[1],
                'password': usuario[2],
                'rol': usuario[3],
                'modulo_principal': usuario[4] if usuario[4] else 'soporte',
                'permisos': usuario[5],
                'fecha_creacion': usuario[6],
                'fecha_actualizacion': usuario[7]
            }
            
            if usuario_data.get('permisos'):
                try:
                    usuario_data['permisos_parsed'] = json.loads(usuario_data['permisos'])
                except:
                    usuario_data['permisos_parsed'] = {}
            else:
                usuario_data['permisos_parsed'] = {}
            
    except psycopg2.IntegrityError:
        flash('El usuario ya existe', 'error')
    except Exception as e:
        flash('Error al editar el usuario', 'error')
        logger.error(f"Error en editar_usuario: {e}")
    
    if not usuario_data:
        flash('Usuario no encontrado', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    return render_template('editar_usuario.html', usuario=usuario_data)

@app.route('/agregar_usuario', methods=['GET', 'POST'])
@login_required
def agregar_usuario():
    if not current_user.puede('gestion_usuarios'):
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect_a_modulo_principal()
    
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']
        rol = request.form['rol']
        modulo_principal = request.form['modulo_principal']
        
        if not usuario or not password:
            flash('Usuario y contraseña son obligatorios', 'error')
            return render_template('agregar_usuario.html')
        
        permisos = {
            'ver_fichas': 'ver_fichas' in request.form,
            'agregar_fichas': 'agregar_fichas' in request.form,
            'editar_fichas': 'editar_fichas' in request.form,
            'eliminar_fichas': 'eliminar_fichas' in request.form,
            'cambiar_password': True
        }
        
        permisos_json = json.dumps(permisos)
        hash_password = generate_password_hash(password)
        
        try:
            ejecutar_consulta(
                "INSERT INTO usuarios (usuario, password, rol, modulo_principal, permisos) VALUES (%s, %s, %s, %s, %s)",
                (usuario, hash_password, rol, modulo_principal, permisos_json),
                commit=True
            )
            flash('Usuario agregado correctamente', 'success')
            return redirect(url_for('gestion_usuarios'))
        except psycopg2.IntegrityError:
            flash('El usuario ya existe', 'error')
        except Exception as e:
            flash('Error al agregar el usuario', 'error')
            logger.error(f"Error en agregar_usuario: {e}")
    
    return render_template('agregar_usuario.html')

@app.route('/eliminar_usuario/<int:id>')
@login_required
def eliminar_usuario(id):
    if not current_user.puede('gestion_usuarios'):
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect_a_modulo_principal()
    
    if id == current_user.id:
        flash('No puedes eliminar tu propio usuario', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    try:
        ejecutar_consulta("DELETE FROM usuarios WHERE id = %s", (id,), commit=True)
        flash('Usuario eliminado correctamente', 'success')
    except Exception as e:
        flash('Error al eliminar el usuario', 'error')
        logger.error(f"Error en eliminar_usuario: {e}")
    
    return redirect(url_for('gestion_usuarios'))

# ===== RUTAS DE INFORMACIÓN =====
@app.route('/soluciones_visuales')
@login_required
def soluciones_visuales():
    soluciones = [
        {
            'id': 1,
            'titulo': '¿Como consultamos clientes?',
            'categoria': 'Softv',
            'imagenes': ['softv/softv1.png', 'softv/softv2.png', 'softv/softv3.png', 'softv/softv4.png'],
            'descripcion': 'Busqueda del cliente paso a paso'
        },
        {
            'id': 2,
            'titulo': '¿Como vemos las facturas del usuario?',
            'categoria': 'Softv',
            'imagenes': ['softv/softv5.png', 'softv/softv6.png', 'softv/softv7.png', 'softv/softv8.png'],
            'descripcion': 'Consultar historial de pagos del usuario'
        },
        {
            'id': 3,
            'titulo': '¿Como consultamos las ordenes de servicio de los usuarios?',
            'categoria': 'Softv',
            'imagenes': ['softv/softv9.png', 'softv/softv10.png', 'softv/softv11.png', 'softv/softv12.png'],
            'descripcion': 'Consultar historial de ordenes de servicio del usuario'
        },
        {
            'id': 4,
            'titulo': '¿Como consultamos reportes de fallas de los usuarios?',
            'categoria': 'Softv',
            'imagenes': ['softv/softv13.png', 'softv/softv14.png', 'softv/softv15.png', 'softv/softv16.png'],
            'descripcion': 'Consultar historial de reportes de falla del usuario'
        },
        {
            'id': 5,
            'titulo': '¿Como creamos un reporte de falla?',
            'categoria': 'Softv', 
            'imagenes': ['softv/softv15.png', 'softv/softv16.png', 'softv/softv17.png', 'softv/softv19.png', 'softv/softv21.png', 'softv/softv22.png'],
            'descripcion': 'Crear un reporte de falla'
        },
        {
            'id': 6,
            'titulo': '¿Como creamos una orden de servicio?',
            'categoria': 'Softv',
            'imagenes': ['softv/softv23.png', 'softv/softv24.png', 'softv/softv26.png', 'softv/softv27.png', 'softv/softv28.png'],
            'descripcion': 'Crear una orden de servicio'
        },
        {
            'id': 7,
            'titulo': '¿Como borramos un reporte de falla en caso necesario?',
            'categoria': 'Softv',
            'imagenes': ['softv/softv29.png', 'softv/softv29.png', 'softv/softv29.png'],
            'descripcion': 'Como eliminar un reporte de falla'
        },
        {
            'id': 8,
            'titulo': '¿Como ingresamos un nuevo cliente?',
            'categoria': 'Softv',
            'imagenes': ['softv/softv30.png', 'softv/softv31.png', 'softv/softv32.png', 'softv/softv33.png', 'softv/softv32.png'],
            'descripcion': 'Crear un nuevo cliente'
        },
        {
            'id': 9,
            'titulo': '¿Como buscar un usuario?',
            'categoria': 'Vortex',
            'imagenes': ['vortex/vortex1.png', 'vortex/vortex2.png', 'vortex/vortex3.png'],
            'descripcion': 'Buscar a un usuario'
        },
        {
            'id': 10,
            'titulo': '¿Como validar puertos en uso y la MAC del equipo?',
            'categoria': 'Vortex',
            'imagenes': ['vortex/vortex4.png', 'vortex/vortex5.png'],
            'descripcion': 'Como validar si el usuario esta haciendo uso de los puertos o el dispositivo no da MAC'
        },
        {
            'id': 11,
            'titulo': '¿Como validar si el usuario esta teniendo consumo del servicio?',
            'categoria': 'Vortex',
            'imagenes': ['vortex/vortex7.png'],
            'descripcion': 'Como validar el consumo del usuario'
        },
        {
            'id': 12,
            'titulo': '¿Como cambiar la VLAN?',
            'categoria': 'Vortex',
            'imagenes': ['vortex/vortex8.png', 'vortex/vortex9.png'],
            'descripcion': 'Como cambiar la VLAN acorde a la zona'
        },
        {
            'id': 13,
            'titulo': '¿Como realizar un resync config?',
            'categoria': 'Vortex',
            'imagenes': ['vortex/vortex10.png', 'vortex/vortex11.png'],
            'descripcion': 'Como realizar un resync config'
        },
        {
            'id': 14,
            'titulo': '¿Como realizar un reboot?',
            'categoria': 'Vortex',
            'imagenes': ['vortex/vortex12.png', 'vortex/vortex13.png'],
            'descripcion': 'Como realizar un reebot'
        },
        {
            'id': 15,
            'titulo': '¿Como identificar si el servicio de internet y TV estan activados?',
            'categoria': 'Vortex',
            'imagenes': ['vortex/vortex14.png'],
            'descripcion': 'Validar si el servicio esta activo'
        }
    ]
    return render_template('soluciones_visuales.html', soluciones=soluciones)

@app.route('/atencion_telefonica')
@login_required
def atencion_telefonica():
    return render_template('atencion_telefonica.html')

@app.route('/informacion-general')
@login_required
def informacion_general():
    informacion = {
        'planes': {
            'titulo': '📡 Planes de Servicio',
            'icono': 'fa-tv',
            'contenido': [
                {
                    'subtitulo': 'Planes Básicos',
                    'contenido_items': [
                        '💯 *PLANES DE TV E INTERNET* 💯',
                        '400 megas + TV: $85.000',
                        '500 megas + TV: $95.000', 
                        '600 megas + TV: $105.000',
                        '',
                        '💯 *PLANES SOLO TV* 💯',
                        '10Mb + TV: $50.000',
                        '',
                        '🌐 *PLANES SOLO INTERNET* 🌐',
                        '400 megas: $75.000',
                        '500 megas: $85.000',
                        '600 megas: $95.000'
                    ]
                },
                {
                    'subtitulo': 'Planes Corporativos',
                    'contenido_items': [
                        '💯 *PLANES CORPORATIVOS* 💯',
                        '1Mb: $12.000',
                        '30Mb (mínimo): $360.000 + 19% IVA = $428.400',
                         '*Planes hogar:* se agrega 19% IVA',
                        '*Equipo:* robusto para configuraciones especiales'
                    ]
                },
                {
                    'subtitulo': 'Planes Guamal y Sanmartin',
                    'contenido_items': [
                        '🎯 PLANES DE TV + INTERNET 🎯',
                        'TV + 200MB: $65.000',
                        'TV + 300MB: $75.000', 
                        'TV + 400MB: $85.000',
                        '',
                        '📺 PLAN SOLO TV 📺',
                        'Solo TV: $50.000'
                    ]
                },
                {
                    'subtitulo': 'Planes Acacías',
                    'contenido_items': [
                        '💯 *PLANES DE TV E INTERNET* 💯',
                        'TV + Internet 200MB: $85.000',
                        'TV + Internet 300MB: $95.000',
                        'TV + Internet 400MB: $105.000',
                        '',
                        '💯 *PLANES SOLO TV* 💯',
                        'Solo TV: $50.000',
                        '',
                        '🌐 *PLANES SOLO INTERNET* 🌐',
                        '200MB: $75.000',
                        '300MB: $85.000',
                        '400MB: $95.000'
                    ]
                }
            ]
        },
        'afiliaciones': {
            'titulo': '👥 Afiliaciones',
            'icono': 'fa-user-plus',
            'contenido': [
                {
                    'subtitulo': 'Información General para Afiliar',
                    'contenido_items': [
                        '*La afiliación no tiene costo*',
                        '*Instalación sin costo* en zona urbana (rural: $150.000)',
                        '',
                        '*Requisitos:*',
                        '• 1 Fotocopia de la cédula',
                        '• 1 Fotocopia del recibo de agua o luz',
                        '• Pago del primer mes por anticipado',
                        '• Servicio de TV para 2 televisores',
                        '',
                        '*Puntos adicionales de TV:*',
                        '• Cada punto: $20.000 (solo instalación)',
                        '• Mensualidad no cambia',
                        '• Solo para el mismo predio',
                        '',
                        '*Señal Digital:*',
                        '• Decodificador: $58.000 (único pago)',
                        '• Para TVs clásicos con señal analógica',
                        '',
                        '*Tiempo de instalación:* 2-4 días hábiles'
                    ]
                },
                {
                    'subtitulo': 'Afiliación San Joaquín',
                    'contenido_items': [
                        '*Costo de instalación:* $60.000',
                        '*Fibra incluida:* primeros 70 metros',
                        '*Costo metro adicional:* $1.700',
                        '',
                        '*Servicio de TV:* 1 televisor',
                        '*Puntos adicionales:* $35.000 c/u',
                        '*Requisitos y tiempos iguales*  a afiliación general'
                    ]
                },
                {
                    'subtitulo': 'Información Adicional',
                    'contenido_items': [
                        '*Para asesores solicitar:*',
                        '• Barrio',
                        '• Dirección exacta', 
                        '• Nombre del titular',
                        '• 2 números de teléfono',
                        '',
                        '*Sin cláusula de permanencia*',
                        '*Pago por adelantado* después de firmar contrato',
                        '*Contrato*  se envía y recibe por el mismo medio'
                    ]
                }
            ]
        },
        'win_sports': {
            'titulo': '⚽ Win Sports +',
            'icono': 'fa-futbol',
            'contenido': [
                {
                    'subtitulo': '¡Llegó Win Sports + a M@STV Producciones!',
                    'contenido_items': [
                        '*Precio:* $35.000 adicionales al mes',
                        '*Incluye:*',
                        '• Acceso a Win Sports +',
                        '• 14 canales premium',
                        '• Y mucho más contenido deportivo',
                        '',
                        '*TV Box:* $100.000 (costo único)',
                        '*No necesario* si TV es Android (con Google Play Store)',
                        '*Cláusula:* 6 meses',
                        '*Requisito:* Tener plan de internet con nosotros'
                    ]
                }
            ]
        },
        'oficinas': {
            'titulo': '🏢 Oficinas y Horarios',
            'icono': 'fa-building',
            'contenido': [
                {
                    'subtitulo': 'Horarios de Atención',
                    'contenido_items': [
                        '*Lunes a Viernes:* 8:00 AM - 5:00 PM',
                        '*Sábados:* 8:00 AM - 12:00 PM'
                    ]
                },
                {
                    'subtitulo': 'Direcciones de Oficinas',
                    'contenido_items': [
                        '*Facatativá:* Cl 11 #7A-04, Diurba',
                        '*Bojacá:* Cr 6 #5-146, Barrio Centro',
                        '*Zipacón:* Crr 4 #5-57, Frente al parque',
                        '*Rosal:* Cr 8 #8-08, Local 3 Centro',
                        '*El Triunfo:* Crr 3 #2-40, Frente al coliseo',
                        '*Viotá:* Cl 20 #11-10, Frente a estación de policía',
                        '*Girardot:* Crr 10 #18-44, Barrio Centro / Frente a Bancamía',
                        '*Cachipay:* Crr 3 #3-36, Barrio Centro',
                        '*Sasaima:* Crr 2 #3-30, Barrio 3 Esquinas',
                        '*La Mesa:* Cl 8 #16-59, Barrio Santa Bárbara',
                        '*Anolaima:* Crr 7 #02-57, Barrio Centro',
                        '*Mesitas del Colegio:* Cl 10 #6-37, Barrio Centro',
                        '*Anapoima:* Cr 2 #7-32, Local 2 Centro',
                        '*Albán:* Cl 4 #2-04, Punto de Servientrega',
                        '*Madrid:* Cl 12 #3-64, Barrio Arrayane',
                        '*Guayabal de Síquima:* Cl 3 #5-28',
                        '*Tocaima:* Cl 4 #9-75',
                        '*San Joaquín:* Cr 4 N 4-55, Al lado del árbol de los aburridos',
                        '*Apulo:* Cl 14 #6-23, Local 102',
                        '*Villeta:* Cr 5 #3-43, Local 6 Torre 4 Conjunto Santa Cruz',
                        '*Acacías:* Cl 15 #22-40, Local 12, Edificio Dark Gym',
                        '*San Martín:* Cl 7 #5-34, Barrio Fundadores',
                        '*Guamal:* Cl 10 #4A-04, Barrio Las Villas',
                        '*Quipile:* Crr 2 #6-07'
                    ]
                },
                {
                    'subtitulo': 'Puntos Autorizados Facatativá',
                    'contenido_items': [
                        '*Bolos el Tunjo:* Cr 2 #6-105',
                        '*CLT Comunicaciones:* Cl 19 #1A-28 Sur, Prado de Cartagenita',
                        '*Portal de María:* Transversal 11 #5-04, Manzana 5 Casa 30 S.M.A.',
                        '*Papelería Expresate:* Cl 8 #10-05, Zambrano',
                        '*One Books:* Diagonal 5 Este #9E-02, Juan Pablo II',
                        '*Papelería Chico 1:* Cr 3 #5B-08 Este, Chico 1'
                    ]
                }
            ]
        },
        'procesos': {
            'titulo': '📋 Procesos y Trámites',
            'icono': 'fa-clipboard-list',
            'contenido': [
                {
                    'subtitulo': 'Cancelación de Servicio',
                    'contenido_items': [
                        '*Requisitos:*',
                        '• Acercarse a la oficina',
                        '• Carta indicando razón de cancelación',
                        '• Paz y salvo',
                        '• Equipos instalados (equipos y cargadores)'
                    ]
                },
                {
                    'subtitulo': 'Cambio de Titular',
                    'contenido_items': [
                        '*Requisitos:*',
                        '• Carta solicitando cambio, firmada por antiguo y nuevo titular',
                        '• Copia de cédula del nuevo titular',
                        '• Estar al día en los pagos'
                    ]
                },
                {
                    'subtitulo': 'Cambio de Plan',
                    'contenido_items': [
                        '*Procedimiento:*',
                        '• Acercarse a la oficina',
                        '• Carta solicitando cambio de plan',
                        '• Estar al día en pagos',
                        '• Cancelar por adelantado valor del nuevo plan',
                        '• Ideal realizarlo a finales de mes'
                    ]
                },
                {
                    'subtitulo': 'Traslado de Domicilio',
                    'contenido_items': [
                        '*Costo:* $20.000',
                        '*Puntos adicionales:* $10.000 c/u (movimiento)',
                        '*Tiempo:* 2-3 días hábiles',
                        '*Requisito:* Llevar equipos a la nueva residencia'
                    ]
                },
                {
                    'subtitulo': 'Solicitud de Facturas',
                    'contenido_items': [
                        '*Datos requeridos:*',
                        '• Contrato',
                        '• Nombre completo',
                        '• Cédula',
                        '• Correo electrónico',
                        '• Teléfono',
                        '• Dirección completa',
                        '• Municipio y barrio',
                        '• Plan de internet',
                        '• Valor del plan',
                        '• Estrato',
                        '*Empresas:* enviar foto del RUT'
                    ]
                }
            ]
        },
        'contacto': {
            'titulo': '📞 Contacto y Soporte',
            'icono': 'fa-headset',
            'contenido': [
                {
                    'subtitulo': 'Información de Contacto',
                    'contenido_items': [
                        '*Email PQR:* pqr@mastvproducciones.net.co',
                        '*Email CARTERA:* auxiliaradministrativo@mastvproducciones.net.co',
                        '*Email INGENIERIA:* ingenieria@mastvproducciones.net.co',
                        '*Email RECURSOS HUMANOS:* rh@mastvproducciones.net.co',
                        '*Chat de Soporte:* Solo mensajes escritos 3187777771',
                        '*No se reciben:* audios ni llamadas por WhatsApp'
                    ]
                }
            ]
        }
    }
    
    return render_template('informacion_general.html', informacion=informacion)

# ===== RUTAS SST MEJORADAS =====
@app.route('/sst')
@login_required
def sst_dashboard():
    """Dashboard principal de SST"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    return render_template('sst/dashboard.html')

@app.route('/sst/contenido')
@login_required
def sst_contenido():
    """Lista de todo el contenido SST"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    contenido = []
    categorias = []
    
    try:
        # Obtener categorías para filtros
        categorias_data = obtener_categorias_sst()
        for cat in categorias_data:
            categorias.append({
                'id': cat[0],
                'nombre': cat[1],
                'color': cat[2]
            })
        
        # Obtener filtros
        filtros = {
            'query': request.args.get('q', ''),
            'categoria': request.args.get('categoria', ''),
            'tipo': request.args.get('tipo', '')
        }
        
        # Obtener contenido
        contenido_data = obtener_contenido_sst(filtros)
        
        for item in contenido_data:
            # Manejar tags de forma segura
            tags_value = item[12]
            if tags_value is None:
                tags_str = ''
            elif isinstance(tags_value, (int, float)):
                tags_str = str(tags_value)
            else:
                tags_str = str(tags_value)
            
            contenido_dict = {
                'id': item[0],
                'titulo': item[1],
                'descripcion': item[2],
                'tipo': item[3],
                'archivo_url': item[4],
                'tiene_archivo': item[5] is not None,
                'archivo_nombre': item[6],
                'archivo_tipo': item[7],
                'archivo_tamano': item[8],
                'video_url': item[9],
                'categoria_id': item[10],
                'es_obligatorio': item[11],
                'tags': tags_str,
                'fecha_publicacion': item[13],
                'usuario_creador': item[14],
                'categoria_nombre': item[15],
                'categoria_color': item[16],
                'creador_nombre': item[17]
            }
            contenido.append(contenido_dict)
                
    except Exception as e:
        flash('Error al cargar el contenido SST', 'error')
        logger.error(f"❌ Error en sst_contenido: {e}")
    
    return render_template('sst/contenido.html', contenido=contenido, categorias=categorias)

@app.route('/sst/agregar', methods=['GET', 'POST'])
@login_required
@retry_on_ssl_error(max_retries=2, delay=3)
def sst_agregar_contenido():
    """Agregar nuevo contenido SST - VERSIÓN MEJORADA CON BD"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    if current_user.rol != 'admin':
        flash('No tienes permisos para agregar contenido SST', 'error')
        return redirect(url_for('sst_dashboard'))
    
    categorias = []
    
    try:
        # Cargar categorías
        categorias_data = obtener_categorias_sst()
        for cat in categorias_data:
            categorias.append({
                'id': cat[0],
                'nombre': cat[1],
                'color': cat[2]
            })
        
        if request.method == 'POST':
            # Obtener datos del formulario
            titulo = request.form.get('titulo', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            tipo = request.form.get('tipo', '').strip()
            categoria_id = request.form.get('categoria_id', '').strip()
            es_obligatorio = 'es_obligatorio' in request.form
            tags = request.form.get('tags', '').strip()
            video_url = request.form.get('video_url', '').strip()
            archivo_url = request.form.get('archivo_url', '').strip()
            
            # Validaciones básicas
            if not titulo or not tipo or not categoria_id:
                flash('❌ Todos los campos obligatorios deben ser completados', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            
            # Validar que categoria_id sea un número
            try:
                categoria_id_int = int(categoria_id)
            except (ValueError, TypeError):
                flash('❌ Categoría inválida', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            
            # Procesar archivo subido - CON MANEJO DE ARCHIVOS GRANDES
            archivo_data = None
            file = request.files.get('archivo_local')
            
            if file and file.filename != '':
                if allowed_file(file.filename):
                    # Verificar tamaño para estrategia diferente
                    file.seek(0, 2)  # Ir al final
                    file_size = file.tell()
                    file.seek(0)  # Volver al inicio
                    
                    logger.info(f"📦 Procesando archivo: {file.filename} ({file_size} bytes)")
                    
                    if file_size > 5 * 1024 * 1024:  # Si es mayor a 5MB
                        logger.info(f"📦 Archivo grande detectado, procesando por chunks...")
                        
                        # Leer en chunks para evitar sobrecargar la memoria
                        chunks = []
                        while True:
                            chunk = file.read(8192)  # Leer en chunks de 8KB
                            if not chunk:
                                break
                            chunks.append(chunk)
                        
                        file_data = b''.join(chunks)
                        file_name = generar_nombre_seguro(file.filename)
                        file_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
                        
                        archivo_data = {
                            'data': file_data,
                            'nombre': file_name,
                            'tipo': file_type,
                            'tamano': len(file_data)
                        }
                        
                        logger.info(f"✅ Archivo grande procesado: {file_name} ({len(file_data)} bytes)")
                    else:
                        # Para archivos pequeños, procesamiento normal
                        archivo_data = guardar_archivo_en_bd(file)
                    
                    if not archivo_data:
                        flash('❌ Error al procesar el archivo', 'error')
                        return render_template('sst/agregar_contenido.html', categorias=categorias)
                    
                    logger.info(f"✅ Archivo preparado para BD: {archivo_data['nombre']} ({archivo_data['tamano']} bytes)")
                    
                    # Si se subió archivo local, limpiar URLs
                    video_url = None
                    archivo_url = None
                else:
                    extensiones_permitidas = ', '.join(app.config['ALLOWED_EXTENSIONS'])
                    flash(f'❌ Tipo de archivo no permitido. Extensiones válidas: {extensiones_permitidas}', 'error')
                    return render_template('sst/agregar_contenido.html', categorias=categorias)
            
            # Validaciones específicas por tipo
            validation_error = None
            if tipo == 'video':
                if not video_url and not archivo_data:
                    validation_error = 'Para video debe proporcionar una URL de video o subir un archivo'
            elif tipo in ['documento', 'imagen']:
                if not archivo_url and not archivo_data:
                    validation_error = 'Debe proporcionar una URL o subir un archivo'
            elif tipo == 'enlace':
                if not archivo_url:
                    validation_error = 'Debe proporcionar una URL para enlaces'
                # Para enlaces, no permitir archivos locales
                archivo_data = None
                video_url = None
            
            if validation_error:
                flash(f'❌ {validation_error}', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            
            # Limpiar valores para la base de datos
            video_url = video_url if video_url else None
            archivo_url = archivo_url if archivo_url else None
            descripcion = descripcion if descripcion else None
            tags = tags if tags else None
            
            # Insertar en la base de datos usando la nueva función
            try:
                success = insertar_contenido_con_archivo(
                    titulo=titulo,
                    descripcion=descripcion,
                    tipo=tipo,
                    categoria_id=categoria_id_int,
                    es_obligatorio=es_obligatorio,
                    tags=tags,
                    usuario_creador=current_user.id,
                    archivo_data=archivo_data,
                    video_url=video_url,
                    archivo_url=archivo_url
                )
                
                if success:
                    flash('✅ Contenido SST agregado correctamente', 'success')
                    return redirect(url_for('sst_contenido'))
                else:
                    flash('❌ Error al guardar en la base de datos', 'error')
                
            except Exception as db_error:
                flash(f'❌ Error de base de datos: {str(db_error)}', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            
    except Exception as e:
        flash(f'❌ Error al agregar contenido SST: {str(e)}', 'error')
        logger.error(f"❌ ERROR GENERAL EN SST_AGREGAR_CONTENIDO: {e}")
    
    return render_template('sst/agregar_contenido.html', categorias=categorias)

@app.route('/sst/archivo/<int:id>')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_descargar_archivo(id):
    """Descargar archivo desde la base de datos"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    try:
        archivo = obtener_archivo_desde_bd(id)
        
        if not archivo:
            flash('Archivo no encontrado', 'error')
            return redirect(url_for('sst_contenido'))
        
        # Verificar que el archivo tenga datos
        if not archivo.get('data'):
            flash('El archivo está vacío', 'error')
            return redirect(url_for('sst_contenido'))
        
        # Crear un objeto BytesIO con los datos
        file_data = BytesIO(archivo['data'])
        
        # Usar send_file para devolver el archivo correctamente
        return send_file(
            file_data,
            mimetype=archivo['tipo'],
            as_attachment=False,
            download_name=archivo['nombre']
        )
        
    except Exception as e:
        flash(f'Error al descargar el archivo: {str(e)}', 'error')
        logger.error(f"❌ Error en sst_descargar_archivo: {e}")
        return redirect(url_for('sst_contenido'))

@app.route('/sst/archivo/descargar/<int:id>')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_descargar_archivo_forzado(id):
    """Descargar archivo forzadamente - SOLO SI QUIERES DESCARGAR"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    try:
        archivo = obtener_archivo_desde_bd(id)
        
        if not archivo or not archivo.get('data'):
            flash('Archivo no encontrado', 'error')
            return redirect(url_for('sst_contenido'))
        
        file_data = BytesIO(archivo['data'])
        
        # ESTA SÍ fuerza la descarga
        return send_file(
            file_data,
            mimetype=archivo['tipo'],
            as_attachment=True,  # Esto SÍ fuerza descarga
            download_name=archivo['nombre']
        )
        
    except Exception as e:
        flash(f'Error al descargar el archivo: {str(e)}', 'error')
        logger.error(f"❌ Error en sst_descargar_archivo_forzado: {e}")
        return redirect(url_for('sst_contenido'))

@app.route('/sst/contenido/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_editar_contenido(id):
    """Editar contenido SST existente"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    if current_user.rol != 'admin':
        flash('No tienes permisos para editar contenido SST', 'error')
        return redirect(url_for('sst_dashboard'))
    
    contenido = None
    categorias = []
    
    try:
        # Cargar categorías
        categorias_data = obtener_categorias_sst()
        for cat in categorias_data:
            categorias.append({
                'id': cat[0],
                'nombre': cat[1],
                'color': cat[2]
            })
        
        if request.method == 'POST':
            # Obtener datos del formulario
            titulo = request.form.get('titulo', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            tipo = request.form.get('tipo', '').strip()
            categoria_id = request.form.get('categoria_id', '').strip()
            es_obligatorio = 'es_obligatorio' in request.form
            tags = request.form.get('tags', '').strip()
            video_url = request.form.get('video_url', '').strip() or None
            archivo_url = request.form.get('archivo_url', '').strip() or None
            
            # Validaciones
            if not titulo or not tipo or not categoria_id:
                flash('Todos los campos obligatorios deben ser completados', 'error')
                return render_template('sst/editar_contenido.html', contenido=contenido, categorias=categorias)
            
            # Procesar archivo subido
            archivo_data = None
            file = request.files.get('archivo_local')
            if file and file.filename != '':
                if allowed_file(file.filename):
                    archivo_data = guardar_archivo_en_bd(file)
                    if not archivo_data:
                        flash('Error al procesar el archivo', 'error')
                        return render_template('sst/editar_contenido.html', contenido=contenido, categorias=categorias)
                    
                    # Si se subió nuevo archivo, limpiar URLs
                    video_url = None
                    archivo_url = None
                else:
                    flash('Tipo de archivo no permitido', 'error')
                    return render_template('sst/editar_contenido.html', contenido=contenido, categorias=categorias)
            
            # Actualizar en base de datos
            if archivo_data:
                # Si se subió nuevo archivo, actualizar con archivo
                ejecutar_consulta("""
                    UPDATE sst_contenido 
                    SET titulo=%s, descripcion=%s, tipo=%s, archivo_url=%s, 
                        archivo_data=%s, archivo_nombre=%s, archivo_tipo=%s, archivo_tamano=%s,
                        video_url=%s, categoria_id=%s, es_obligatorio=%s, 
                        tags=%s, fecha_actualizacion=CURRENT_TIMESTAMP
                    WHERE id=%s
                """, (
                    titulo, descripcion, tipo, archivo_url,
                    psycopg2.Binary(archivo_data['data']), archivo_data['nombre'], 
                    archivo_data['tipo'], archivo_data['tamano'],
                    video_url, categoria_id, es_obligatorio, tags, id
                ), commit=True)
            else:
                # Mantener el archivo existente, solo actualizar otros campos
                ejecutar_consulta("""
                    UPDATE sst_contenido 
                    SET titulo=%s, descripcion=%s, tipo=%s, archivo_url=%s, 
                        video_url=%s, categoria_id=%s, es_obligatorio=%s, 
                        tags=%s, fecha_actualizacion=CURRENT_TIMESTAMP
                    WHERE id=%s
                """, (
                    titulo, descripcion, tipo, archivo_url, video_url, 
                    categoria_id, es_obligatorio, tags, id
                ), commit=True)
            
            flash('✅ Contenido actualizado correctamente', 'success')
            return redirect(url_for('sst_contenido'))
        
        # GET: Cargar datos del contenido
        resultado = ejecutar_consulta("""
            SELECT sc.*, cat.nombre as categoria_nombre, cat.color as categoria_color,
                   u.usuario as creador_nombre
            FROM sst_contenido sc
            LEFT JOIN sst_categorias cat ON sc.categoria_id = cat.id
            LEFT JOIN usuarios u ON sc.usuario_creador = u.id
            WHERE sc.id = %s
        """, (id,), fetch=True)
        
        if resultado and resultado[0]:
            contenido_data = resultado[0]
            contenido = {
                'id': contenido_data[0],
                'titulo': contenido_data[1],
                'descripcion': contenido_data[2],
                'tipo': contenido_data[3],
                'archivo_url': contenido_data[4],
                'tiene_archivo': contenido_data[5] is not None,
                'archivo_nombre': contenido_data[6],
                'archivo_tipo': contenido_data[7],
                'archivo_tamano': contenido_data[8],
                'video_url': contenido_data[9],
                'categoria_id': contenido_data[10],
                'es_obligatorio': contenido_data[11],
                'tags': str(contenido_data[12]) if contenido_data[12] is not None else '',
                'fecha_publicacion': contenido_data[13],
                'usuario_creador': contenido_data[14],
                'categoria_nombre': contenido_data[15],
                'categoria_color': contenido_data[16],
                'creador_nombre': contenido_data[17]
            }
                
    except Exception as e:
        flash(f'Error al editar contenido SST: {str(e)}', 'error')
        logger.error(f"❌ Error en sst_editar_contenido: {e}")
    
    if not contenido:
        flash('Contenido no encontrado', 'error')
        return redirect(url_for('sst_contenido'))
    
    return render_template('sst/editar_contenido.html', contenido=contenido, categorias=categorias)

@app.route('/sst/contenido/<int:id>/eliminar', methods=['POST'])
@login_required
def sst_eliminar_contenido(id):
    """Eliminar contenido SST"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    if current_user.rol != 'admin':
        flash('No tienes permisos para eliminar contenido SST', 'error')
        return redirect(url_for('sst_dashboard'))
    
    try:
        # Eliminar de la base de datos (el archivo se elimina automáticamente)
        ejecutar_consulta("DELETE FROM sst_contenido WHERE id = %s", (id,), commit=True)
        
        flash('✅ Contenido eliminado correctamente', 'success')
        
    except Exception as e:
        flash(f'Error al eliminar contenido SST: {str(e)}', 'error')
        logger.error(f"❌ Error en sst_eliminar_contenido: {e}")
    
    return redirect(url_for('sst_contenido'))

@app.route('/sst/video/<int:id>')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_ver_video(id):
    """Ver detalles de un video - VERSIÓN CORREGIDA"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    video = None
    
    try:
        # Obtener datos básicos del video
        resultado = ejecutar_consulta("""
            SELECT sc.*, cat.nombre as categoria_nombre, cat.color as categoria_color
            FROM sst_contenido sc
            LEFT JOIN sst_categorias cat ON sc.categoria_id = cat.id
            WHERE sc.id = %s
        """, (id,), fetch=True)
        
        if resultado and resultado[0]:
            video_data = resultado[0]
            video = {
                'id': video_data[0],
                'titulo': video_data[1],
                'descripcion': video_data[2],
                'tipo': video_data[3],
                'archivo_nombre': video_data[6],
                'archivo_tipo': video_data[7],
                'archivo_tamano': video_data[8],
                'video_url': video_data[9],
                'tiene_archivo': video_data[5] is not None,
                'categoria_nombre': video_data[15] if len(video_data) > 15 else '',
                'categoria_color': video_data[16] if len(video_data) > 16 else '#007bff',
                'fecha_publicacion': video_data[13],
                'es_obligatorio': video_data[11]
            }
        else:
            flash('Video no encontrado', 'error')
            return redirect(url_for('sst_contenido'))
    
    except Exception as e:
        flash(f'Error al cargar el video: {str(e)}', 'error')
        logger.error(f"❌ Error en sst_ver_video: {e}")
        return redirect(url_for('sst_contenido'))
    
    if not video:
        flash('Video no encontrado', 'error')
        return redirect(url_for('sst_contenido'))
    
    return render_template('sst/ver_video.html', video=video)

@app.route('/sst/video/stream/<int:id>')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_stream_video(id):
    """Stream de video desde la base de datos"""
    if not current_user.puede('acceder_sst'):
        return Response('No autorizado', status=403)
    
    try:
        archivo = obtener_archivo_desde_bd(id)
        
        if not archivo or not archivo.get('data'):
            return Response('Video no encontrado', status=404)
        
        # Verificar que sea un video
        if not archivo['tipo'].startswith('video/'):
            return Response('El archivo no es un video', status=400)
        
        # Crear respuesta con el video
        file_data = BytesIO(archivo['data'])
        
        return send_file(
            file_data,
            mimetype=archivo['tipo'],
            as_attachment=False
        )
        
    except Exception as e:
        logger.error(f"❌ Error en sst_stream_video: {e}")
        return Response('Error interno del servidor', status=500)

# ===== RUTAS PARA SERVIR ARCHIVOS ESTÁTICOS =====
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Servir archivos estáticos"""
    return send_from_directory('static', filename)

# ===== API PARA PROBLEMAS =====
@app.route('/api/problemas/<categoria>')
@login_required
def obtener_problemas(categoria):
    if not current_user.puede('acceder_soporte'):
        return jsonify([])
    
    problemas_por_categoria = {
        'TV': [
            'No hay señal en el televisor',
            'Imagen pixelada o con interferencias',
            'Sin sonido en algunos canales',
            'Problemas con la guía de programación',
            'Otro problema con TV'
        ],
        'Internet': [
            'Internet lento o intermitente',
            'Sin conexión a internet',
            'Problemas con WiFi',
            'No puedo conectarme a sitios específicos',
            'Velocidad inferior a la contratada',
            'Problemas con el módem/router',
            'Otro problema con Internet'
        ],
        'Equipo': [
            'Equipo no enciende',
            'Problemas con puertos HDMI/USB',
            'Dispositivo no da MAC',
            'Problemas niveles opticos',
            'Otro problema con Equipo'
        ]
    }
    
    problemas = problemas_por_categoria.get(categoria, [])
    return jsonify(problemas)

# ===== RUTAS PARA GESTIÓN DEL PLAN ANUAL DE TRABAJO PESV =====
@app.route('/sst/plan-anual')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_plan_anual():
    """Dashboard principal del Plan Anual de Trabajo"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Obtener estadísticas generales
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN estado = 'completado' THEN 1 ELSE 0 END) as completadas,
                SUM(CASE WHEN estado = 'en_proceso' THEN 1 ELSE 0 END) as en_proceso,
                SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) as pendientes,
                ROUND(AVG(porcentaje_avance), 2) as promedio_avance
            FROM plan_anual_trabajo
        """)
        stats = cursor.fetchone()
        
        # Obtener actividades por ciclo PHVA
        cursor.execute("""
            SELECT 
                ciclo_phva,
                COUNT(*) as total,
                SUM(CASE WHEN estado = 'completado' THEN 1 ELSE 0 END) as completadas,
                ROUND(AVG(porcentaje_avance), 2) as promedio
            FROM plan_anual_trabajo
            WHERE ciclo_phva IS NOT NULL
            GROUP BY ciclo_phva
            ORDER BY 
                CASE ciclo_phva 
                    WHEN 'Planear' THEN 1 
                    WHEN 'Hacer' THEN 2 
                    WHEN 'Verificar' THEN 3 
                    WHEN 'Actuar' THEN 4 
                    ELSE 5 
                END
        """)
        stats_phva = cursor.fetchall()
        
        # Obtener actividades recientes
        cursor.execute("""
            SELECT 
                id, actividad, ciclo_phva, responsables, estado, 
                porcentaje_avance, fecha_actualizacion
            FROM plan_anual_trabajo
            ORDER BY fecha_actualizacion DESC
            LIMIT 10
        """)
        actividades_recientes = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('sst/plan_anual_dashboard.html',
                             stats=stats,
                             stats_phva=stats_phva,
                             actividades_recientes=actividades_recientes)
        
    except Exception as e:
        flash(f'Error al cargar el plan anual: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual: {e}")
        return redirect(url_for('sst_dashboard'))

@app.route('/sst/plan-anual/actividades')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_plan_anual_actividades():
    """Listar todas las actividades del plan anual"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    # Filtros
    ciclo = request.args.get('ciclo', '')
    estado = request.args.get('estado', '')
    responsable = request.args.get('responsable', '')
    mes = request.args.get('mes', '')
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Construir query con filtros
        query = """
            SELECT 
                id, actividad, evidencia, ciclo_phva, responsables, 
                estado, porcentaje_avance, nivel_pesv
            FROM plan_anual_trabajo
            WHERE 1=1
        """
        params = []
        
        if ciclo:
            query += " AND ciclo_phva = %s"
            params.append(ciclo)
        
        if estado:
            query += " AND estado = %s"
            params.append(estado)
        
        if responsable:
            query += " AND responsables ILIKE %s"
            params.append(f'%{responsable}%')
        
        # Si se filtra por mes, verificar que tenga actividad planificada ese mes
        if mes:
            meses = {
                'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
                'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
                'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
            }
            mes_lower = mes.lower()
            if mes_lower in meses:
                # Verificar si tiene al menos una semana planificada en ese mes
                query += f" AND ({mes_lower}_semana1_p = TRUE OR {mes_lower}_semana2_p = TRUE OR {mes_lower}_semana3_p = TRUE OR {mes_lower}_semana4_p = TRUE)"
        
        query += " ORDER BY ciclo_phva, actividad"
        
        cursor.execute(query, params)
        actividades = cursor.fetchall()
        
        # Obtener opciones únicas para filtros
        cursor.execute("SELECT DISTINCT ciclo_phva FROM plan_anual_trabajo WHERE ciclo_phva IS NOT NULL ORDER BY ciclo_phva")
        ciclos_disponibles = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT responsables FROM plan_anual_trabajo WHERE responsables IS NOT NULL")
        responsables_disponibles = set()
        for row in cursor.fetchall():
            if row[0]:
                # Separar por comas y limpiar
                for r in row[0].split('-'):
                    responsables_disponibles.add(r.strip())
        responsables_disponibles = sorted(list(responsables_disponibles))
        
        cursor.close()
        conn.close()
        
        return render_template('sst/plan_anual_actividades.html',
                             actividades=actividades,
                             ciclos=ciclos_disponibles,
                             responsables_list=responsables_disponibles,
                             filtro_ciclo=ciclo,
                             filtro_estado=estado,
                             filtro_responsable=responsable,
                             filtro_mes=mes)
        
    except Exception as e:
        flash(f'Error al cargar actividades: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual_actividades: {e}")
        return redirect(url_for('sst_plan_anual'))

# ===== REEMPLAZA ESTA RUTA EN TU app.py =====

# ===== REEMPLAZA LA RUTA sst_plan_anual_actividad_detalle EN app.py =====

@app.route('/sst/plan-anual/actividad/<int:id>')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_plan_anual_actividad_detalle(id):
    """Ver detalle completo de una actividad"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para ver esta actividad', 'error')
        return redirect(url_for('sst_plan_anual'))
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Obtener actividad con nombres de columnas específicos
        cursor.execute("""
            SELECT 
                id, actividad, evidencia, ciclo_phva, articulos_decreto, 
                nivel_pesv, responsables, recursos,
                enero_semana1_p, enero_semana1_e, enero_semana2_p, enero_semana2_e,
                enero_semana3_p, enero_semana3_e, enero_semana4_p, enero_semana4_e,
                febrero_semana1_p, febrero_semana1_e, febrero_semana2_p, febrero_semana2_e,
                febrero_semana3_p, febrero_semana3_e, febrero_semana4_p, febrero_semana4_e,
                marzo_semana1_p, marzo_semana1_e, marzo_semana2_p, marzo_semana2_e,
                marzo_semana3_p, marzo_semana3_e, marzo_semana4_p, marzo_semana4_e,
                abril_semana1_p, abril_semana1_e, abril_semana2_p, abril_semana2_e,
                abril_semana3_p, abril_semana3_e, abril_semana4_p, abril_semana4_e,
                mayo_semana1_p, mayo_semana1_e, mayo_semana2_p, mayo_semana2_e,
                mayo_semana3_p, mayo_semana3_e, mayo_semana4_p, mayo_semana4_e,
                junio_semana1_p, junio_semana1_e, junio_semana2_p, junio_semana2_e,
                junio_semana3_p, junio_semana3_e, junio_semana4_p, junio_semana4_e,
                julio_semana1_p, julio_semana1_e, julio_semana2_p, julio_semana2_e,
                julio_semana3_p, julio_semana3_e, julio_semana4_p, julio_semana4_e,
                agosto_semana1_p, agosto_semana1_e, agosto_semana2_p, agosto_semana2_e,
                agosto_semana3_p, agosto_semana3_e, agosto_semana4_p, agosto_semana4_e,
                septiembre_semana1_p, septiembre_semana1_e, septiembre_semana2_p, septiembre_semana2_e,
                septiembre_semana3_p, septiembre_semana3_e, septiembre_semana4_p, septiembre_semana4_e,
                octubre_semana1_p, octubre_semana1_e, octubre_semana2_p, octubre_semana2_e,
                octubre_semana3_p, octubre_semana3_e, octubre_semana4_p, octubre_semana4_e,
                noviembre_semana1_p, noviembre_semana1_e, noviembre_semana2_p, noviembre_semana2_e,
                noviembre_semana3_p, noviembre_semana3_e, noviembre_semana4_p, noviembre_semana4_e,
                diciembre_semana1_p, diciembre_semana1_e, diciembre_semana2_p, diciembre_semana2_e,
                diciembre_semana3_p, diciembre_semana3_e, diciembre_semana4_p, diciembre_semana4_e,
                observaciones, estado, porcentaje_avance, fecha_creacion, fecha_actualizacion, usuario_actualizacion
            FROM plan_anual_trabajo 
            WHERE id = %s
        """, (id,))
        
        actividad_raw = cursor.fetchone()
        
        if not actividad_raw:
            flash('❌ Actividad no encontrada', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('sst_plan_anual_actividades'))
        
        # Mapear datos básicos (primeras 8 columnas)
        actividad = {
            'id': actividad_raw[0],
            'actividad': actividad_raw[1],
            'evidencia': actividad_raw[2],
            'ciclo_phva': actividad_raw[3],
            'articulos_decreto': actividad_raw[4],
            'nivel_pesv': actividad_raw[5],
            'responsables': actividad_raw[6],
            'recursos': actividad_raw[7],
        }
        
        # Extraer programación mensual (columnas 8-103)
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        
        programacion = {}
        semanas_planificadas = 0
        semanas_ejecutadas = 0
        col_idx = 8  # Empieza después de las 8 columnas básicas
        
        for mes in meses:
            programacion[mes] = []
            for semana in range(1, 5):
                planificado = actividad_raw[col_idx] if actividad_raw[col_idx] else False
                ejecutado = actividad_raw[col_idx + 1] if actividad_raw[col_idx + 1] else False
                
                if planificado:
                    semanas_planificadas += 1
                if ejecutado:
                    semanas_ejecutadas += 1
                
                programacion[mes].append({
                    'semana': semana,
                    'planificado': planificado,
                    'ejecutado': ejecutado
                })
                
                col_idx += 2  # Avanzar a la siguiente semana (planificado + ejecutado)
        
        # Agregar datos finales (después de las 96 columnas de semanas)
        # col_idx ahora está en 104 (8 + 96)
        actividad['observaciones'] = actividad_raw[104] if len(actividad_raw) > 104 else ''
        actividad['estado'] = actividad_raw[105] if len(actividad_raw) > 105 else 'pendiente'
        
        # IMPORTANTE: Convertir porcentaje_avance a float de forma segura
        try:
            porcentaje_raw = actividad_raw[106] if len(actividad_raw) > 106 else 0
            if porcentaje_raw is None or porcentaje_raw == '':
                actividad['porcentaje_avance'] = 0.0
            else:
                actividad['porcentaje_avance'] = float(porcentaje_raw)
        except (ValueError, TypeError):
            actividad['porcentaje_avance'] = 0.0
            logger.warning(f"Error al convertir porcentaje_avance para actividad {id}")
        
        actividad['fecha_creacion'] = actividad_raw[107] if len(actividad_raw) > 107 else None
        actividad['fecha_actualizacion'] = actividad_raw[108] if len(actividad_raw) > 108 else None
        actividad['usuario_actualizacion'] = actividad_raw[109] if len(actividad_raw) > 109 else None
        
        # Agregar programación y estadísticas
        actividad['programacion'] = programacion
        actividad['semanas_planificadas'] = semanas_planificadas
        actividad['semanas_ejecutadas'] = semanas_ejecutadas
        
        # Obtener evidencias
        try:
            cursor.execute("""
                SELECT id, titulo, descripcion, nombre_archivo, fecha_creacion
                FROM plan_evidencias
                WHERE actividad_id = %s
                ORDER BY fecha_creacion DESC
            """, (id,))
            evidencias = cursor.fetchall()
        except Exception as e:
            logger.warning(f"No se pudieron cargar evidencias: {e}")
            evidencias = []
        
        # Obtener seguimientos
        try:
            cursor.execute("""
                SELECT s.id, s.comentario, s.tipo, s.fecha, u.usuario
                FROM plan_seguimiento s
                LEFT JOIN usuarios u ON s.usuario_id = u.id
                WHERE s.actividad_id = %s
                ORDER BY s.fecha DESC
            """, (id,))
            seguimientos = cursor.fetchall()
        except Exception as e:
            logger.warning(f"No se pudieron cargar seguimientos: {e}")
            seguimientos = []
        
        cursor.close()
        conn.close()
        
        return render_template('sst/plan_anual_detalle.html',
                             actividad=actividad,
                             evidencias=evidencias,
                             seguimientos=seguimientos)
        
    except Exception as e:
        flash(f'❌ Error al cargar detalle: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual_actividad_detalle: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return redirect(url_for('sst_plan_anual_actividades'))

@app.route('/sst/plan-anual/actividad/<int:id>/actualizar', methods=['POST'])
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_plan_anual_actualizar_actividad(id):
    """Actualizar estado de ejecución de una actividad"""
    if not current_user.puede('gestionar_plan_anual'):
        flash('No tienes permisos para modificar el plan anual', 'error')
        return redirect(url_for('sst_plan_anual_actividad_detalle', id=id))
    
    try:
        # Obtener datos del formulario
        mes = request.form.get('mes')
        semana = request.form.get('semana')
        ejecutado = request.form.get('ejecutado') == 'true'
        
        if not mes or not semana:
            flash('Datos incompletos', 'error')
            return redirect(url_for('sst_plan_anual_actividad_detalle', id=id))
        
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Actualizar la semana específica
        columna = f"{mes}_semana{semana}_e"
        query = f"""
            UPDATE plan_anual_trabajo 
            SET {columna} = %s,
                fecha_actualizacion = CURRENT_TIMESTAMP,
                usuario_actualizacion = %s
            WHERE id = %s
        """
        
        cursor.execute(query, (ejecutado, current_user.id, id))
        
        # Recalcular porcentaje y estado
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM (
                    SELECT enero_semana1_p, enero_semana2_p, enero_semana3_p, enero_semana4_p,
                           febrero_semana1_p, febrero_semana2_p, febrero_semana3_p, febrero_semana4_p,
                           marzo_semana1_p, marzo_semana2_p, marzo_semana3_p, marzo_semana4_p,
                           abril_semana1_p, abril_semana2_p, abril_semana3_p, abril_semana4_p,
                           mayo_semana1_p, mayo_semana2_p, mayo_semana3_p, mayo_semana4_p,
                           junio_semana1_p, junio_semana2_p, junio_semana3_p, junio_semana4_p,
                           julio_semana1_p, julio_semana2_p, julio_semana3_p, julio_semana4_p,
                           agosto_semana1_p, agosto_semana2_p, agosto_semana3_p, agosto_semana4_p,
                           septiembre_semana1_p, septiembre_semana2_p, septiembre_semana3_p, septiembre_semana4_p,
                           octubre_semana1_p, octubre_semana2_p, octubre_semana3_p, octubre_semana4_p,
                           noviembre_semana1_p, noviembre_semana2_p, noviembre_semana3_p, noviembre_semana4_p,
                           diciembre_semana1_p, diciembre_semana2_p, diciembre_semana3_p, diciembre_semana4_p
                    FROM plan_anual_trabajo WHERE id = %s
                ) AS p WHERE TRUE IN (
                    enero_semana1_p, enero_semana2_p, enero_semana3_p, enero_semana4_p,
                    febrero_semana1_p, febrero_semana2_p, febrero_semana3_p, febrero_semana4_p,
                    marzo_semana1_p, marzo_semana2_p, marzo_semana3_p, marzo_semana4_p,
                    abril_semana1_p, abril_semana2_p, abril_semana3_p, abril_semana4_p,
                    mayo_semana1_p, mayo_semana2_p, mayo_semana3_p, mayo_semana4_p,
                    junio_semana1_p, junio_semana2_p, junio_semana3_p, junio_semana4_p,
                    julio_semana1_p, julio_semana2_p, julio_semana3_p, julio_semana4_p,
                    agosto_semana1_p, agosto_semana2_p, agosto_semana3_p, agosto_semana4_p,
                    septiembre_semana1_p, septiembre_semana2_p, septiembre_semana3_p, septiembre_semana4_p,
                    octubre_semana1_p, octubre_semana2_p, octubre_semana3_p, octubre_semana4_p,
                    noviembre_semana1_p, noviembre_semana2_p, noviembre_semana3_p, noviembre_semana4_p,
                    diciembre_semana1_p, diciembre_semana2_p, diciembre_semana3_p, diciembre_semana4_p
                )) as planificadas
        """, (id,))
        
        # Actualizar estado basado en ejecución
        nuevo_estado = 'en_proceso' if ejecutado else 'pendiente'
        
        cursor.execute("""
            UPDATE plan_anual_trabajo
            SET estado = %s
            WHERE id = %s
        """, (nuevo_estado, id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Actividad actualizada exitosamente', 'success')
        
    except Exception as e:
        flash(f'Error al actualizar: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual_actualizar_actividad: {e}")
    
    return redirect(url_for('sst_plan_anual_actividad_detalle', id=id))

@app.route('/sst/plan-anual/actividad/<int:id>/evidencia', methods=['POST'])
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_plan_anual_agregar_evidencia(id):
    """Agregar evidencia a una actividad"""
    if not current_user.puede('agregar_evidencias'):
        flash('No tienes permisos para agregar evidencias', 'error')
        return redirect(url_for('sst_plan_anual_actividad_detalle', id=id))
    
    try:
        titulo = request.form.get('titulo', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        archivo = request.files.get('archivo')
        
        if not titulo:
            flash('El título es obligatorio', 'error')
            return redirect(url_for('sst_plan_anual_actividad_detalle', id=id))
        
        archivo_data = None
        if archivo and archivo.filename != '':
            if allowed_file(archivo.filename):
                archivo_data = guardar_archivo_en_bd(archivo)
            else:
                flash('Tipo de archivo no permitido', 'error')
                return redirect(url_for('sst_plan_anual_actividad_detalle', id=id))
        
        conn = crear_conexion()
        cursor = conn.cursor()
        
        if archivo_data:
            cursor.execute("""
                INSERT INTO plan_evidencias (
                    plan_id, titulo, descripcion, archivo_nombre, archivo_tipo,
                    archivo_tamano, archivo_data, usuario_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                id, titulo, descripcion, archivo_data['nombre'],
                archivo_data['tipo'], archivo_data['tamano'],
                psycopg2.Binary(archivo_data['data']), current_user.id
            ))
        else:
            cursor.execute("""
                INSERT INTO plan_evidencias (
                    plan_id, titulo, descripcion, usuario_id
                ) VALUES (%s, %s, %s, %s)
            """, (id, titulo, descripcion, current_user.id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Evidencia agregada exitosamente', 'success')
        
    except Exception as e:
        flash(f'Error al agregar evidencia: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual_agregar_evidencia: {e}")
    
    return redirect(url_for('sst_plan_anual_actividad_detalle', id=id))

@app.route('/sst/plan-anual/cronograma')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_plan_anual_cronograma():
    """Vista de cronograma completo tipo Gantt"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Obtener todas las actividades con su programación
        cursor.execute("""
            SELECT 
                id, actividad, ciclo_phva, responsables, estado,
                enero_semana1_p, enero_semana1_e, enero_semana2_p, enero_semana2_e,
                enero_semana3_p, enero_semana3_e, enero_semana4_p, enero_semana4_e,
                febrero_semana1_p, febrero_semana1_e, febrero_semana2_p, febrero_semana2_e,
                febrero_semana3_p, febrero_semana3_e, febrero_semana4_p, febrero_semana4_e,
                marzo_semana1_p, marzo_semana1_e, marzo_semana2_p, marzo_semana2_e,
                marzo_semana3_p, marzo_semana3_e, marzo_semana4_p, marzo_semana4_e,
                abril_semana1_p, abril_semana1_e, abril_semana2_p, abril_semana2_e,
                abril_semana3_p, abril_semana3_e, abril_semana4_p, abril_semana4_e,
                mayo_semana1_p, mayo_semana1_e, mayo_semana2_p, mayo_semana2_e,
                mayo_semana3_p, mayo_semana3_e, mayo_semana4_p, mayo_semana4_e,
                junio_semana1_p, junio_semana1_e, junio_semana2_p, junio_semana2_e,
                junio_semana3_p, junio_semana3_e, junio_semana4_p, junio_semana4_e,
                julio_semana1_p, julio_semana1_e, julio_semana2_p, julio_semana2_e,
                julio_semana3_p, julio_semana3_e, julio_semana4_p, julio_semana4_e,
                agosto_semana1_p, agosto_semana1_e, agosto_semana2_p, agosto_semana2_e,
                agosto_semana3_p, agosto_semana3_e, agosto_semana4_p, agosto_semana4_e,
                septiembre_semana1_p, septiembre_semana1_e, septiembre_semana2_p, septiembre_semana2_e,
                septiembre_semana3_p, septiembre_semana3_e, septiembre_semana4_p, septiembre_semana4_e,
                octubre_semana1_p, octubre_semana1_e, octubre_semana2_p, octubre_semana2_e,
                octubre_semana3_p, octubre_semana3_e, octubre_semana4_p, octubre_semana4_e,
                noviembre_semana1_p, noviembre_semana1_e, noviembre_semana2_p, noviembre_semana2_e,
                noviembre_semana3_p, noviembre_semana3_e, noviembre_semana4_p, noviembre_semana4_e,
                diciembre_semana1_p, diciembre_semana1_e, diciembre_semana2_p, diciembre_semana2_e,
                diciembre_semana3_p, diciembre_semana3_e, diciembre_semana4_p, diciembre_semana4_e
            FROM plan_anual_trabajo
            ORDER BY ciclo_phva, actividad
            LIMIT 50
        """)
        actividades = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('sst/plan_anual_cronograma.html',
                             actividades=actividades)
        
    except Exception as e:
        flash(f'Error al cargar cronograma: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual_cronograma: {e}")
        return redirect(url_for('sst_plan_anual'))

def inicializar_plan_anual():
    """Crear tabla e importar datos del plan anual basados en el Excel"""
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Verificar si la tabla existe, si no, crearla con estructura completa
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plan_anual_trabajo (
                id SERIAL PRIMARY KEY,
                actividad TEXT NOT NULL,
                evidencia TEXT,
                ciclo_phva VARCHAR(50),
                articulos VARCHAR(200),
                nivel_pesv VARCHAR(100),
                responsables VARCHAR(200),
                recursos TEXT,
                
                -- Enero
                enero_semana1_p BOOLEAN DEFAULT FALSE,
                enero_semana1_e BOOLEAN DEFAULT FALSE,
                enero_semana2_p BOOLEAN DEFAULT FALSE,
                enero_semana2_e BOOLEAN DEFAULT FALSE,
                enero_semana3_p BOOLEAN DEFAULT FALSE,
                enero_semana3_e BOOLEAN DEFAULT FALSE,
                enero_semana4_p BOOLEAN DEFAULT FALSE,
                enero_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Febrero
                febrero_semana1_p BOOLEAN DEFAULT FALSE,
                febrero_semana1_e BOOLEAN DEFAULT FALSE,
                febrero_semana2_p BOOLEAN DEFAULT FALSE,
                febrero_semana2_e BOOLEAN DEFAULT FALSE,
                febrero_semana3_p BOOLEAN DEFAULT FALSE,
                febrero_semana3_e BOOLEAN DEFAULT FALSE,
                febrero_semana4_p BOOLEAN DEFAULT FALSE,
                febrero_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Marzo
                marzo_semana1_p BOOLEAN DEFAULT FALSE,
                marzo_semana1_e BOOLEAN DEFAULT FALSE,
                marzo_semana2_p BOOLEAN DEFAULT FALSE,
                marzo_semana2_e BOOLEAN DEFAULT FALSE,
                marzo_semana3_p BOOLEAN DEFAULT FALSE,
                marzo_semana3_e BOOLEAN DEFAULT FALSE,
                marzo_semana4_p BOOLEAN DEFAULT FALSE,
                marzo_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Abril
                abril_semana1_p BOOLEAN DEFAULT FALSE,
                abril_semana1_e BOOLEAN DEFAULT FALSE,
                abril_semana2_p BOOLEAN DEFAULT FALSE,
                abril_semana2_e BOOLEAN DEFAULT FALSE,
                abril_semana3_p BOOLEAN DEFAULT FALSE,
                abril_semana3_e BOOLEAN DEFAULT FALSE,
                abril_semana4_p BOOLEAN DEFAULT FALSE,
                abril_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Mayo
                mayo_semana1_p BOOLEAN DEFAULT FALSE,
                mayo_semana1_e BOOLEAN DEFAULT FALSE,
                mayo_semana2_p BOOLEAN DEFAULT FALSE,
                mayo_semana2_e BOOLEAN DEFAULT FALSE,
                mayo_semana3_p BOOLEAN DEFAULT FALSE,
                mayo_semana3_e BOOLEAN DEFAULT FALSE,
                mayo_semana4_p BOOLEAN DEFAULT FALSE,
                mayo_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Junio
                junio_semana1_p BOOLEAN DEFAULT FALSE,
                junio_semana1_e BOOLEAN DEFAULT FALSE,
                junio_semana2_p BOOLEAN DEFAULT FALSE,
                junio_semana2_e BOOLEAN DEFAULT FALSE,
                junio_semana3_p BOOLEAN DEFAULT FALSE,
                junio_semana3_e BOOLEAN DEFAULT FALSE,
                junio_semana4_p BOOLEAN DEFAULT FALSE,
                junio_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Julio
                julio_semana1_p BOOLEAN DEFAULT FALSE,
                julio_semana1_e BOOLEAN DEFAULT FALSE,
                julio_semana2_p BOOLEAN DEFAULT FALSE,
                julio_semana2_e BOOLEAN DEFAULT FALSE,
                julio_semana3_p BOOLEAN DEFAULT FALSE,
                julio_semana3_e BOOLEAN DEFAULT FALSE,
                julio_semana4_p BOOLEAN DEFAULT FALSE,
                julio_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Agosto
                agosto_semana1_p BOOLEAN DEFAULT FALSE,
                agosto_semana1_e BOOLEAN DEFAULT FALSE,
                agosto_semana2_p BOOLEAN DEFAULT FALSE,
                agosto_semana2_e BOOLEAN DEFAULT FALSE,
                agosto_semana3_p BOOLEAN DEFAULT FALSE,
                agosto_semana3_e BOOLEAN DEFAULT FALSE,
                agosto_semana4_p BOOLEAN DEFAULT FALSE,
                agosto_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Septiembre
                septiembre_semana1_p BOOLEAN DEFAULT FALSE,
                septiembre_semana1_e BOOLEAN DEFAULT FALSE,
                septiembre_semana2_p BOOLEAN DEFAULT FALSE,
                septiembre_semana2_e BOOLEAN DEFAULT FALSE,
                septiembre_semana3_p BOOLEAN DEFAULT FALSE,
                septiembre_semana3_e BOOLEAN DEFAULT FALSE,
                septiembre_semana4_p BOOLEAN DEFAULT FALSE,
                septiembre_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Octubre
                octubre_semana1_p BOOLEAN DEFAULT FALSE,
                octubre_semana1_e BOOLEAN DEFAULT FALSE,
                octubre_semana2_p BOOLEAN DEFAULT FALSE,
                octubre_semana2_e BOOLEAN DEFAULT FALSE,
                octubre_semana3_p BOOLEAN DEFAULT FALSE,
                octubre_semana3_e BOOLEAN DEFAULT FALSE,
                octubre_semana4_p BOOLEAN DEFAULT FALSE,
                octubre_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Noviembre
                noviembre_semana1_p BOOLEAN DEFAULT FALSE,
                noviembre_semana1_e BOOLEAN DEFAULT FALSE,
                noviembre_semana2_p BOOLEAN DEFAULT FALSE,
                noviembre_semana2_e BOOLEAN DEFAULT FALSE,
                noviembre_semana3_p BOOLEAN DEFAULT FALSE,
                noviembre_semana3_e BOOLEAN DEFAULT FALSE,
                noviembre_semana4_p BOOLEAN DEFAULT FALSE,
                noviembre_semana4_e BOOLEAN DEFAULT FALSE,
                
                -- Diciembre
                diciembre_semana1_p BOOLEAN DEFAULT FALSE,
                diciembre_semana1_e BOOLEAN DEFAULT FALSE,
                diciembre_semana2_p BOOLEAN DEFAULT FALSE,
                diciembre_semana2_e BOOLEAN DEFAULT FALSE,
                diciembre_semana3_p BOOLEAN DEFAULT FALSE,
                diciembre_semana3_e BOOLEAN DEFAULT FALSE,
                diciembre_semana4_p BOOLEAN DEFAULT FALSE,
                diciembre_semana4_e BOOLEAN DEFAULT FALSE,
                
                observaciones TEXT,
                estado VARCHAR(20) DEFAULT 'pendiente',
                porcentaje_avance DECIMAL(5,2) DEFAULT 0.00,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usuario_actualizacion INTEGER
            )
        """)
        
        # Crear tabla de evidencias si no existe
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plan_evidencias (
                id SERIAL PRIMARY KEY,
                plan_id INTEGER REFERENCES plan_anual_trabajo(id) ON DELETE CASCADE,
                titulo VARCHAR(200) NOT NULL,
                descripcion TEXT,
                archivo_nombre VARCHAR(300),
                archivo_tipo VARCHAR(100),
                archivo_tamano INTEGER,
                archivo_data BYTEA,
                usuario_id INTEGER,
                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Crear tabla de seguimiento
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plan_seguimiento (
                id SERIAL PRIMARY KEY,
                plan_id INTEGER REFERENCES plan_anual_trabajo(id) ON DELETE CASCADE,
                comentario TEXT NOT NULL,
                tipo VARCHAR(50),
                usuario_id INTEGER,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        
        # Verificar si ya hay datos
        cursor.execute("SELECT COUNT(*) FROM plan_anual_trabajo")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print("📥 Importando datos del plan anual desde el Excel...")
            
            # Datos de ejemplo basados en tu Excel
            actividades_pesv = [
                # PLANEAR: DISEÑO Y PLANIFICACIÓN DEL SG-SST
                {
                    'actividad': 'Responsable del Sistema de Gestión de Seguridad y Salud en el Trabajo SG-SST',
                    'evidencia': 'Documento en el que consta la asignación, con la respectiva determinación de responsabilidades y constatar la hoja de vida con soportes de la persona asignada.',
                    'ciclo_phva': 'Planear',
                    'articulos': '2.2.4.6.8',
                    'nivel_pesv': 'N/A',
                    'responsables': 'SST - COPASST - GERENCIA',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Asignación inicial del responsable',
                    'programacion': {
                        'enero': [True, False, False, False],  # Semana 1
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Lider del diseño e implementacion del PESV',
                    'evidencia': 'Documento en el que consta la asignación, con la respectiva determinación de responsabilidades, evidencia de la competencia del Líder; por lo que se debe definir y documentar',
                    'ciclo_phva': 'Planear',
                    'articulos': 'N/A',
                    'nivel_pesv': 'Todos los niveles - Paso 1',
                    'responsables': 'SST - GERENCIA',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Designación del líder PESV',
                    'programacion': {
                        'enero': [True, True, False, False],  # Semanas 1 y 2
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Politica de Seguridad y Salud en el Trabajo SST y del Plan Estrategico de Seguridad Vial PESV',
                    'evidencia': 'Política del Sistema de Gestión deSeguridad y Salud en elTrabajo SG-SST firmada, fecha y comunicada al COPASST',
                    'ciclo_phva': 'Planear',
                    'articulos': '2.2.4.6.5, 2.2.4.6.6, 2.2.4.6.12',
                    'nivel_pesv': 'Todos los niveles (Paso 3)',
                    'responsables': 'SST - COPASST - COMITE DE SEGURIDAD VIAL',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Política institucional',
                    'programacion': {
                        'enero': [True, True, True, False],  # Semanas 1-3
                        'febrero': [False, True, False, False],  # Semana 2
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Objetivos del Sistema de Gestión de la Seguridad y Salud en el Trabajo SG-SST y del Plan Estrategico de Seguridad Vial PESV',
                    'evidencia': 'Objetivos definidos, claros, medibles, cuantificables, con metas, documentados, revisados del SG-SST y del PESV',
                    'ciclo_phva': 'Planear',
                    'articulos': '2.2.4.6.7',
                    'nivel_pesv': 'Estandar (Paso 7)',
                    'responsables': 'SST - COPASST - COMITE DE SEGURIDAD VIAL- LIDER PESV',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Definición anual de objetivos',
                    'programacion': {
                        'enero': [True, True, True, True],  # Todo enero
                        'febrero': [True, False, False, False],  # Semana 1
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Responsabilidades en el Sistema de Gestión deSeguridad y Salud en el Trabajo SG - SST y del Plan Estrategico de Seguridad Vial PESV',
                    'evidencia': 'Debe asignar, documentar y comunicar las responsabilidades específicas en SST y PESV a todos los niveles de la organización, incluida la alta dirección',
                    'ciclo_phva': 'Planear',
                    'articulos': '2.2.4.6.8, 2.2.4.6.9, 2.2.4.6.10, 2.2.4.6.8.12',
                    'nivel_pesv': 'Estandar (Paso 11)',
                    'responsables': 'SST - COPASST - COMITE DE SEGURIDAD VIAL',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos',
                    'observaciones': 'Asignación de responsabilidades',
                    'programacion': {
                        'enero': [True, True, False, False],  # Semanas 1-2
                        'febrero': [True, True, False, False],  # Semanas 1-2
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Asignación de recursos para el Sistema de Gestión de Seguridad y Salud en elTrabajo SG-SST y del Plan Estrategico de Seguridad Vial PESV',
                    'evidencia': 'Establecer y asignar el presupuesto requerido para la ejecución de las actividades establecidas en el SG SST y PESV para el 2026',
                    'ciclo_phva': 'Planear',
                    'articulos': '2.2.4.6.8',
                    'nivel_pesv': 'N/A',
                    'responsables': 'SST - COPASST - COMITE DE SEGURIDAD VIAL',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Presupuesto anual',
                    'programacion': {
                        'enero': [True, False, False, False],  # Semana 1
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Matriz legal',
                    'evidencia': 'Debe contener Normatividad nacional vigente y aplicable en materia de SST y PESV',
                    'ciclo_phva': 'Planear',
                    'articulos': '2.2.4.6.8, 2.2.4.6.8.12',
                    'nivel_pesv': 'N/A',
                    'responsables': 'SST - COPASST - COMITE DE SEGURIDAD VIAL',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Actualización normativa',
                    'programacion': {
                        'enero': [True, True, False, False],  # Semanas 1-2
                        'febrero': [False, False, True, False],  # Semana 3
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Afiliación al Sistema General de Riesgos Laborales',
                    'evidencia': 'Planilla de pago de aportes a la seguridad social',
                    'ciclo_phva': 'Planear',
                    'articulos': '',
                    'nivel_pesv': 'N/A',
                    'responsables': 'SST - COPASST - TALENTO HUMANO',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Pago mensual',
                    'programacion': {
                        'enero': [True, False, False, False],
                        'febrero': [True, False, False, False],
                        'marzo': [True, False, False, False],
                        'abril': [True, False, False, False],
                        'mayo': [True, False, False, False],
                        'junio': [True, False, False, False],
                        'julio': [True, False, False, False],
                        'agosto': [True, False, False, False],
                        'septiembre': [True, False, False, False],
                        'octubre': [True, False, False, False],
                        'noviembre': [True, False, False, False],
                        'diciembre': [True, False, False, False]
                    }
                },
                {
                    'actividad': 'Identificación de trabajadores de alto riesgo y cotización de pensión especial',
                    'evidencia': 'En el caso que aplique, identificar a los trabajadores que se dediquen en forma permanente al ejercicio de las actividades de alto riesgo...',
                    'ciclo_phva': 'Planear',
                    'articulos': '',
                    'nivel_pesv': 'N/A',
                    'responsables': 'SST',
                    'recursos': 'Tecnologicos, Humanos',
                    'observaciones': 'Identificación trimestral',
                    'programacion': {
                        'enero': [True, False, False, False],
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [True, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [True, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [True, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Conformación COPASST',
                    'evidencia': 'convocatoria, elección, conformación del Comité Paritario de Seguridad y Salud en el Trabajo y el acta de constitución.',
                    'ciclo_phva': 'Planear',
                    'articulos': '2.2.4.6.12',
                    'nivel_pesv': 'N/A',
                    'responsables': 'SST - GERENCIA',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Renovación anual',
                    'programacion': {
                        'enero': [True, True, True, True],  # Todo enero
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                # HACER: IMPLEMENTACIÓN Y EJECUCIÓN DEL PESV (algunas actividades)
                {
                    'actividad': 'Descripción sociodemográfica. Diagnostico de Condiciones de Salud',
                    'evidencia': 'Recolectar la siguiente información actualizada de todos los trabajadores del último año...',
                    'ciclo_phva': 'Hacer',
                    'articulos': '',
                    'nivel_pesv': '',
                    'responsables': '',
                    'recursos': '',
                    'observaciones': 'Anual',
                    'programacion': {
                        'enero': [True, True, True, True],  # Todo enero
                        'febrero': [True, True, True, True],  # Todo febrero
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Reuniones mensuales y/o extraordinarias COPASST',
                    'evidencia': 'Actas de reunión mensuales del último año del Comité Paritario y verificar el cumplimiento de sus funciones.',
                    'ciclo_phva': 'Hacer',
                    'articulos': '2.2.4.6.12',
                    'nivel_pesv': 'N/A',
                    'responsables': 'SST - COPASST - GERENCIA',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Mensual',
                    'programacion': {
                        'enero': [True, False, False, False],
                        'febrero': [True, False, False, False],
                        'marzo': [True, False, False, False],
                        'abril': [True, False, False, False],
                        'mayo': [True, False, False, False],
                        'junio': [True, False, False, False],
                        'julio': [True, False, False, False],
                        'agosto': [True, False, False, False],
                        'septiembre': [True, False, False, False],
                        'octubre': [True, False, False, False],
                        'noviembre': [True, False, False, False],
                        'diciembre': [True, False, False, False]
                    }
                },
                {
                    'actividad': 'Reuniones trimestrales y/o extraordinarias COMITE DE SEGURIDAD VIAL',
                    'evidencia': 'Actas de reunión trimestrales del COMITE DE SEGURIDAD VIAL y verificar el cumplimiento de sus funciones.',
                    'ciclo_phva': 'Hacer',
                    'articulos': 'N/A',
                    'nivel_pesv': 'Estandar y Avanzado (Paso 2)',
                    'responsables': 'SST - GERENCIA - COMITE DE SEGURIDAD VIAL',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Trimestral',
                    'programacion': {
                        'enero': [False, False, False, True],  # Última semana
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, True, False],  # Tercera semana
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, True],  # Última semana
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, True],  # Última semana
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, True]   # Última semana
                    }
                },
                {
                    'actividad': 'Capacitacion COMITE DE SEGURIDAD VIAL',
                    'evidencia': 'Capacitar a lo integrantes del COMITE DE SEGURIDAD VIAL para el cumplimiento efectivo de las responsabilidades que les asigna la ley.',
                    'ciclo_phva': 'Hacer',
                    'articulos': 'N/A',
                    'nivel_pesv': 'Estandar y Avanzado (Paso 2)',
                    'responsables': 'SST - GERENCIA - COMITE DE SEGURIDAD VIAL',
                    'recursos': 'Tecnologicos, Infraestructura, Humanos, Financieros',
                    'observaciones': 'Capacitación inicial',
                    'programacion': {
                        'enero': [True, True, False, False],  # Semanas 1-2
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Divulgación de los objetivos específicos y metas de SST y seguridad vial. (Anual)',
                    'evidencia': '',
                    'ciclo_phva': 'Hacer',
                    'articulos': '',
                    'nivel_pesv': 'Todos los niveles (Paso 7)',
                    'responsables': 'SST - COPASST - COMITÉ DE SEGURIDAD VIAL / LÍDER PESV',
                    'recursos': '',
                    'observaciones': 'Comunicación interna',
                    'programacion': {
                        'enero': [True, False, False, False],
                        'febrero': [True, False, False, False],
                        'marzo': [True, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Elaboración del plan de preparación y respuesta ante emergencias viales (PPRAEV).',
                    'evidencia': '',
                    'ciclo_phva': 'Hacer',
                    'articulos': '',
                    'nivel_pesv': 'Todos los niveles (Paso 12)',
                    'responsables': 'Seguridad y Salud en el Trabajo',
                    'recursos': '',
                    'observaciones': 'Plan de emergencias',
                    'programacion': {
                        'enero': [True, False, False, False],
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Realización del simulacro anual de emergencias viales. (Anual)',
                    'evidencia': '',
                    'ciclo_phva': 'Paso 12',
                    'articulos': '',
                    'nivel_pesv': 'Todos los niveles',
                    'responsables': 'Seguridad y Salud en el Trabajo',
                    'recursos': '',
                    'observaciones': 'Simulacro anual',
                    'programacion': {
                        'enero': [True, True, False, False],  # Semanas 1-2
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Desarrollo y/o actualización del procedimiento y mecanismos para el registro de la inspección preoperacional de vehículos motorizados y no motorizados que se utilizan en desplazamientos laborales.',
                    'evidencia': '',
                    'ciclo_phva': 'Paso 16',
                    'articulos': '',
                    'nivel_pesv': 'Todos los niveles',
                    'responsables': 'Responsable Vehículos Seguros',
                    'recursos': '',
                    'observaciones': 'Inspección vehicular',
                    'programacion': {
                        'enero': [False, False, False, False],
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [True, True, False, False],  # Semanas 1-2 de abril
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Diseño e implementación del plan de mantenimiento preventivo para vehículos automotores y no automotores que se utilizan para los desplazamientos laborales.',
                    'evidencia': '',
                    'ciclo_phva': 'Paso 17',
                    'articulos': '',
                    'nivel_pesv': 'Todos los niveles',
                    'responsables': 'Líder Vehículos Seguros',
                    'recursos': '',
                    'observaciones': 'Mantenimiento vehicular',
                    'programacion': {
                        'enero': [False, False, False, False],
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [True, False, False, False],  # Semana 1 de abril
                        'mayo': [True, True, True, False],  # Semanas 1-3 de mayo
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Desarrollo del Protocolo o Manual para la gestión de contratistas',
                    'evidencia': '',
                    'ciclo_phva': 'Paso 18',
                    'articulos': '',
                    'nivel_pesv': 'Estándar y Avanzado',
                    'responsables': 'Define Empresa',
                    'recursos': '',
                    'observaciones': 'Gestión de contratistas',
                    'programacion': {
                        'enero': [True, True, False, False],  # Semanas 1-2
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                {
                    'actividad': 'Desarrollo del sistema de archivo y retención documental, para los registros y documentos que soportan el PESV.',
                    'evidencia': '',
                    'ciclo_phva': 'Paso 19',
                    'articulos': '',
                    'nivel_pesv': 'Estándar y Avanzado',
                    'responsables': 'Define Empresa',
                    'recursos': '',
                    'observaciones': 'Gestión documental',
                    'programacion': {
                        'enero': [True, True, False, False],  # Semanas 1-2
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                },
                # VERIFICAR: SEGUIMIENTO POR LA ORGANIZACIÓN
                {
                    'actividad': 'Revisión del PESV (Trimestral)',
                    'evidencia': '',
                    'ciclo_phva': 'Verificar',
                    'articulos': '',
                    'nivel_pesv': 'Todos los niveles (Paso 2)',
                    'responsables': 'Comité de seguridad vial / Líder PESV',
                    'recursos': '',
                    'observaciones': 'Revisión trimestral',
                    'programacion': {
                        'enero': [False, False, False, True],  # Última semana
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, True],  # Última semana
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, True],  # Última semana
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, True],  # Última semana
                        'octubre': [False, False, False, False],
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, True]   # Última semana
                    }
                },
                {
                    'actividad': 'Auditoria interna al PESV. (Anual)',
                    'evidencia': '',
                    'ciclo_phva': 'Verificar',
                    'articulos': '',
                    'nivel_pesv': 'Todos los niveles (Paso 22)',
                    'responsables': 'Comité de seguridad vial / Líder PESV',
                    'recursos': '',
                    'observaciones': 'Auditoría anual',
                    'programacion': {
                        'enero': [False, False, False, False],
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [False, False, False, False],
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [False, False, False, False],
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [False, False, False, False],
                        'noviembre': [True, True, True, True],  # Todo noviembre
                        'diciembre': [False, False, False, False]
                    }
                },
                # ACTUAR: MEJORA CONTINUA DEL PESV
                {
                    'actividad': 'Definición e implementación de acciones preventivas y/o correctivas con base a los resultados de medición de los indicadores y auditorías al PESV (Trimestral)',
                    'evidencia': '',
                    'ciclo_phva': 'Actuar',
                    'articulos': '',
                    'nivel_pesv': 'Todos los niveles (Paso 23)',
                    'responsables': 'Líder del PESV / Comité de Seguridad Vial',
                    'recursos': '',
                    'observaciones': 'Acciones de mejora trimestrales',
                    'programacion': {
                        'enero': [False, False, False, False],
                        'febrero': [True, False, False, False],  # Primera semana
                        'febrero': [False, False, False, False],
                        'marzo': [False, False, False, False],
                        'abril': [True, False, False, False],  # Primera semana
                        'mayo': [False, False, False, False],
                        'junio': [False, False, False, False],
                        'julio': [True, False, False, False],  # Primera semana
                        'agosto': [False, False, False, False],
                        'septiembre': [False, False, False, False],
                        'octubre': [True, False, False, False],  # Primera semana
                        'noviembre': [False, False, False, False],
                        'diciembre': [False, False, False, False]
                    }
                }
            ]
            
            # Insertar cada actividad con su programación
            for act in actividades_pesv:
                # Construir query dinámica
                columns = [
                    'actividad', 'evidencia', 'ciclo_phva', 'articulos', 
                    'nivel_pesv', 'responsables', 'recursos', 'observaciones',
                    'estado'
                ]
                placeholders = ['%s'] * len(columns)
                values = [
                    act['actividad'], act['evidencia'], act['ciclo_phva'],
                    act['articulos'], act['nivel_pesv'], act['responsables'],
                    act['recursos'], act['observaciones'], 'pendiente'
                ]
                
                # Agregar programación mensual
                meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
                
                for mes in meses:
                    if mes in act['programacion']:
                        programacion = act['programacion'][mes]
                        for semana in range(1, 5):
                            # Columna planificada (p)
                            columns.append(f"{mes}_semana{semana}_p")
                            placeholders.append('%s')
                            values.append(programacion[semana-1])
                            
                            # Columna ejecutada (e) - inicialmente False
                            columns.append(f"{mes}_semana{semana}_e")
                            placeholders.append('%s')
                            # Marcar algunas como ejecutadas para mostrar datos de prueba
                            ejecutado = programacion[semana-1] and (semana % 2 == 0)  # Ejecutadas en semanas pares
                            values.append(ejecutado)
                    else:
                        # Si no hay programación para este mes, llenar con False
                        for semana in range(1, 5):
                            columns.append(f"{mes}_semana{semana}_p")
                            placeholders.append('%s')
                            values.append(False)
                            
                            columns.append(f"{mes}_semana{semana}_e")
                            placeholders.append('%s')
                            values.append(False)
                
                # Insertar
                query = f"""
                    INSERT INTO plan_anual_trabajo ({', '.join(columns)})
                    VALUES ({', '.join(placeholders)})
                """
                cursor.execute(query, values)
            
            conn.commit()
            print(f"✅ {len(actividades_pesv)} actividades del PESV insertadas")
            
            # Insertar algunas evidencias de ejemplo
            evidencias_ejemplo = [
                (1, 'Acta de designación de responsable SST', 'Documento firmado por gerencia designando al responsable del SG-SST', None, None, None, None, 1),
                (3, 'Política de SST y PESV', 'Documento oficial de la política institucional', 'politica_sst.pdf', 'application/pdf', 102400, None, 1),
                (10, 'Actas de reunión COPASST Enero', 'Acta de la primera reunión del año', 'acta_copasst_enero.pdf', 'application/pdf', 153600, None, 1),
                (15, 'Presentación objetivos PESV', 'Diapositivas para divulgación de objetivos', 'presentacion_objetivos.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 204800, None, 1),
            ]
            
            for evidencia in evidencias_ejemplo:
                cursor.execute("""
                    INSERT INTO plan_evidencias 
                    (plan_id, titulo, descripcion, archivo_nombre, archivo_tipo, archivo_tamano, usuario_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, evidencia)
            
            # Insertar seguimientos de ejemplo
            seguimientos_ejemplo = [
                (1, 'Se designó al Ing. Juan Pérez como responsable SST', 'asignacion', 1),
                (3, 'Política revisada y aprobada por comité directivo', 'aprobacion', 1),
                (10, 'Primera reunión del año realizada con quórum completo', 'reunion', 1),
                (15, 'Objetivos comunicados a todo el personal', 'comunicacion', 1),
            ]
            
            for seguimiento in seguimientos_ejemplo:
                cursor.execute("""
                    INSERT INTO plan_seguimiento 
                    (plan_id, comentario, tipo, usuario_id)
                    VALUES (%s, %s, %s, %s)
                """, seguimiento)
            
            conn.commit()
            print("✅ Evidencias y seguimientos de ejemplo insertados")
            
        else:
            print(f"✅ Ya existen {count} actividades en el plan anual")
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error al inicializar plan anual: {e}")
        import traceback
        traceback.print_exc()

# También necesitamos actualizar la función para calcular porcentajes de avance automáticamente
# ===== FUNCIÓN MEJORADA PARA ACTUALIZAR PORCENTAJES =====
# Reemplaza la función existente en app.py

def actualizar_porcentaje_avance(id):
    """
    Actualizar automáticamente el porcentaje de avance de una actividad
    basándose en semanas planificadas vs ejecutadas
    """
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Nombres de los meses
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        
        # Construir lista de columnas planificadas y ejecutadas
        columnas_planificadas = []
        columnas_ejecutadas = []
        
        for mes in meses:
            for semana in range(1, 5):
                columnas_planificadas.append(f'{mes}_semana{semana}_p')
                columnas_ejecutadas.append(f'{mes}_semana{semana}_e')
        
        # Contar semanas planificadas (TRUE)
        query_planificadas = f"""
            SELECT 
                {' + '.join([f'CASE WHEN {col} = TRUE THEN 1 ELSE 0 END' for col in columnas_planificadas])} as total_planificadas
            FROM plan_anual_trabajo 
            WHERE id = %s
        """
        cursor.execute(query_planificadas, (id,))
        resultado_p = cursor.fetchone()
        total_planificadas = resultado_p[0] if resultado_p else 0
        
        # Contar semanas ejecutadas (TRUE)
        query_ejecutadas = f"""
            SELECT 
                {' + '.join([f'CASE WHEN {col} = TRUE THEN 1 ELSE 0 END' for col in columnas_ejecutadas])} as total_ejecutadas
            FROM plan_anual_trabajo 
            WHERE id = %s
        """
        cursor.execute(query_ejecutadas, (id,))
        resultado_e = cursor.fetchone()
        total_ejecutadas = resultado_e[0] if resultado_e else 0
        
        # Calcular porcentaje
        porcentaje = 0
        if total_planificadas > 0:
            porcentaje = round((total_ejecutadas / total_planificadas) * 100, 2)
        
        # Determinar estado automáticamente
        if porcentaje == 100:
            estado = 'completado'
        elif porcentaje > 0:
            estado = 'en_proceso'
        else:
            estado = 'pendiente'
        
        # Actualizar en la base de datos
        cursor.execute("""
            UPDATE plan_anual_trabajo 
            SET porcentaje_avance = %s, 
                estado = %s,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (porcentaje, estado, id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Porcentaje actualizado para actividad {id}: {porcentaje}% ({estado})")
        return porcentaje, estado
        
    except Exception as e:
        logger.error(f"❌ Error al actualizar porcentaje: {e}")
        return 0, 'pendiente'
# ===== RUTAS NUEVAS PARA INICIALIZAR EL PLAN ANUAL =====

@app.route('/sst/plan-anual/inicializar-datos-simple')
@login_required
def sst_inicializar_datos_simple():
    """Inicializar datos básicos del plan anual - VERSIÓN SIMPLE"""
    if current_user.rol != 'admin':
        flash('No tienes permisos', 'error')
        return redirect(url_for('sst_dashboard'))
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Verificar si ya hay datos
        cursor.execute("SELECT COUNT(*) FROM plan_anual_trabajo")
        count = cursor.fetchone()[0]
        
        if count > 0:
            flash(f'⚠️ Ya existen {count} actividades. No se insertarán duplicados.', 'warning')
            cursor.close()
            conn.close()
            return redirect(url_for('sst_plan_anual'))
        
        # Datos de ejemplo simplificados
        actividades = [
            {
                'actividad': 'Responsable del Sistema de Gestión de Seguridad y Salud en el Trabajo SG-SST',
                'evidencia': 'Documento en el que consta la asignación',
                'ciclo_phva': 'Planear',
                'articulos': '2.2.4.6.8',
                'nivel_pesv': 'N/A',
                'responsables': 'SST - COPASST - GERENCIA',
                'recursos': 'Tecnologicos, Infraestructura, Humanos',
                'estado': 'completado',
                'enero_s1_p': True, 'enero_s1_e': True
            },
            {
                'actividad': 'Lider del diseño e implementacion del PESV',
                'evidencia': 'Documento de asignación del líder',
                'ciclo_phva': 'Planear',
                'articulos': 'N/A',
                'nivel_pesv': 'Paso 1',
                'responsables': 'SST - GERENCIA',
                'recursos': 'Humanos, Financieros',
                'estado': 'en_proceso',
                'enero_s1_p': True, 'enero_s1_e': True,
                'enero_s2_p': True, 'enero_s2_e': False
            },
            {
                'actividad': 'Politica de SST y PESV',
                'evidencia': 'Política firmada y comunicada',
                'ciclo_phva': 'Planear',
                'articulos': '2.2.4.6.5, 2.2.4.6.6',
                'nivel_pesv': 'Paso 3',
                'responsables': 'SST - COPASST',
                'recursos': 'Humanos',
                'estado': 'pendiente',
                'enero_s1_p': True, 'enero_s2_p': True, 'enero_s3_p': True
            },
            {
                'actividad': 'Reuniones mensuales COPASST',
                'evidencia': 'Actas de reunión',
                'ciclo_phva': 'Hacer',
                'articulos': '2.2.4.6.12',
                'nivel_pesv': 'N/A',
                'responsables': 'SST - COPASST',
                'recursos': 'Humanos',
                'estado': 'en_proceso',
                'enero_s1_p': True, 'febrero_s1_p': True, 'marzo_s1_p': True,
                'abril_s1_p': True, 'mayo_s1_p': True, 'junio_s1_p': True
            },
            {
                'actividad': 'Revisión trimestral del PESV',
                'evidencia': 'Actas de revisión',
                'ciclo_phva': 'Verificar',
                'articulos': 'N/A',
                'nivel_pesv': 'Paso 2',
                'responsables': 'Comité de seguridad vial',
                'recursos': 'Humanos',
                'estado': 'pendiente',
                'marzo_s4_p': True, 'junio_s4_p': True,
                'septiembre_s4_p': True, 'diciembre_s4_p': True
            },
            {
                'actividad': 'Auditoria interna al PESV',
                'evidencia': 'Informe de auditoría',
                'ciclo_phva': 'Verificar',
                'articulos': 'N/A',
                'nivel_pesv': 'Paso 22',
                'responsables': 'Líder PESV',
                'recursos': 'Humanos, Financieros',
                'estado': 'pendiente',
                'noviembre_s1_p': True, 'noviembre_s2_p': True,
                'noviembre_s3_p': True, 'noviembre_s4_p': True
            },
            {
                'actividad': 'Acciones preventivas y correctivas',
                'evidencia': 'Plan de acción de mejora',
                'ciclo_phva': 'Actuar',
                'articulos': 'N/A',
                'nivel_pesv': 'Paso 23',
                'responsables': 'Líder PESV',
                'recursos': 'Todos',
                'estado': 'pendiente',
                'febrero_s1_p': True, 'abril_s1_p': True,
                'julio_s1_p': True, 'octubre_s1_p': True
            }
        ]
        
        # Insertar cada actividad
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        
        for act in actividades:
            # Construir columnas y valores dinámicamente
            columnas = ['actividad', 'evidencia', 'ciclo_phva', 'articulos_decreto',
                       'nivel_pesv', 'responsables', 'recursos', 'estado']
            valores = [
                act['actividad'], act['evidencia'], act['ciclo_phva'],
                act['articulos'], act['nivel_pesv'], act['responsables'],
                act['recursos'], act['estado']
            ]
            
            # Agregar programación mensual
            for mes in meses:
                for semana in [1, 2, 3, 4]:
                    key_p = f'{mes}_s{semana}_p'
                    key_e = f'{mes}_s{semana}_e'
                    
                    columnas.append(f'{mes}_semana{semana}_p')
                    valores.append(act.get(key_p, False))
                    
                    columnas.append(f'{mes}_semana{semana}_e')
                    valores.append(act.get(key_e, False))
            
            # Crear query
            query = f"""
                INSERT INTO plan_anual_trabajo ({', '.join(columnas)})
                VALUES ({', '.join(['%s'] * len(valores))})
            """
            
            cursor.execute(query, valores)
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash(f'✅ {len(actividades)} actividades del plan anual insertadas correctamente', 'success')
        logger.info(f"✅ Plan anual inicializado con {len(actividades)} actividades")
        
    except Exception as e:
        flash(f'❌ Error al inicializar: {str(e)}', 'error')
        logger.error(f"❌ Error en sst_inicializar_datos_simple: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('sst_plan_anual'))


@app.route('/sst/plan-anual/verificar-tablas')
@login_required
def sst_verificar_tablas():
    """Verificar que las tablas del plan anual existan - DEBUG"""
    if current_user.rol != 'admin':
        flash('No tienes permisos', 'error')
        return redirect(url_for('sst_dashboard'))
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Verificar tabla principal
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'plan_anual_trabajo'
            )
        """)
        tabla_existe = cursor.fetchone()[0]
        
        if tabla_existe:
            cursor.execute("SELECT COUNT(*) FROM plan_anual_trabajo")
            count = cursor.fetchone()[0]
            flash(f'✅ Tabla plan_anual_trabajo existe con {count} registros', 'success')
        else:
            flash('❌ Tabla plan_anual_trabajo NO existe. Crear tablas primero.', 'error')
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'error')
        logger.error(f"Error en verificar_tablas: {e}")

# ===== AGREGAR ESTAS 2 RUTAS A TU app.py =====

@app.route('/sst/plan-anual/subir-excel', methods=['GET', 'POST'])
@login_required
def sst_subir_excel():
    """Subir archivo Excel del Plan Anual"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    
    if request.method == 'POST':
        try:
            file = request.files.get('excel_file')
            
            if not file or file.filename == '':
                flash('❌ No se seleccionó ningún archivo', 'error')
                return redirect(url_for('sst_subir_excel'))
            
            # Verificar que sea un archivo Excel
            if not file.filename.endswith(('.xlsx', '.xls')):
                flash('❌ El archivo debe ser un Excel (.xlsx o .xls)', 'error')
                return redirect(url_for('sst_subir_excel'))
            
            # Guardar el archivo temporalmente
            excel_path = os.path.join('/tmp', 'Plan_Anual_de_Trabajo_2026.xlsx')
            file.save(excel_path)
            
            flash('✅ Archivo Excel subido correctamente. Ahora puedes importar los datos.', 'success')
            return redirect(url_for('sst_importar_desde_excel'))
            
        except Exception as e:
            flash(f'❌ Error al subir archivo: {str(e)}', 'error')
            logger.error(f"Error en sst_subir_excel: {e}")
    
    return render_template('sst/subir_excel.html')


@app.route('/sst/plan-anual/importar-desde-excel')
@login_required
def sst_importar_desde_excel():
    """Importar TODAS las actividades del Excel completo"""
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    
    try:
        import openpyxl
        
        # Buscar el archivo en /tmp (donde se sube)
        excel_path = '/tmp/Plan_Anual_de_Trabajo_2026.xlsx'
        
        # Verificar que existe
        if not os.path.exists(excel_path):
            flash('❌ Archivo Excel no encontrado. Debes subirlo primero.', 'error')
            return redirect(url_for('sst_subir_excel'))
        
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Verificar si ya hay datos
        cursor.execute("SELECT COUNT(*) FROM plan_anual_trabajo")
        count = cursor.fetchone()[0]
        
        if count > 10:
            flash(f'⚠️ Ya existen {count} actividades. Elimínalas primero desde la ruta /sst/plan-anual/limpiar-datos', 'warning')
            cursor.close()
            conn.close()
            return redirect(url_for('sst_plan_anual'))
        
        # Cargar Excel
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
        
        # Extraer actividades
        actividades = []
        fila_actual = 13
        
        logger.info("📥 Extrayendo actividades del Excel...")
        
        while fila_actual <= ws.max_row:
            actividad = ws.cell(fila_actual, 2).value
            evidencia = ws.cell(fila_actual, 3).value
            ciclo_phva = ws.cell(fila_actual, 4).value
            articulos = ws.cell(fila_actual, 5).value
            nivel_pesv = ws.cell(fila_actual, 6).value
            responsables = ws.cell(fila_actual, 7).value
            recursos = ws.cell(fila_actual, 8).value
            
            if not actividad or isinstance(actividad, str) and (
                'PLANEAR' in actividad.upper() or 
                'HACER' in actividad.upper() or 
                'VERIFICAR' in actividad.upper() or 
                'ACTUAR' in actividad.upper() or
                'DISEÑO' in actividad.upper()
            ):
                fila_actual += 1
                continue
            
            programacion = {}
            meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            
            col_inicio = 9
            
            for idx, mes in enumerate(meses):
                programacion[mes] = []
                mes_col_inicio = col_inicio + (idx * 8)
                
                for semana in range(4):
                    col_p = mes_col_inicio + (semana * 2)
                    col_e = col_p + 1
                    
                    val_p = ws.cell(fila_actual, col_p).value
                    val_e = ws.cell(fila_actual, col_e).value
                    
                    planificado = val_p in ['x', 'X', True, 1, '1'] if val_p else False
                    ejecutado = val_e in ['x', 'X', True, 1, '1'] if val_e else False
                    
                    programacion[mes].append({
                        'planificado': planificado,
                        'ejecutado': ejecutado
                    })
            
            actividades.append({
                'actividad': str(actividad).strip() if actividad else '',
                'evidencia': str(evidencia).strip() if evidencia else '',
                'ciclo_phva': str(ciclo_phva).strip() if ciclo_phva else '',
                'articulos': str(articulos).strip() if articulos else '',
                'nivel_pesv': str(nivel_pesv).strip() if nivel_pesv else '',
                'responsables': str(responsables).strip() if responsables else '',
                'recursos': str(recursos).strip() if recursos else '',
                'programacion': programacion
            })
            
            fila_actual += 1
        
        logger.info(f"✅ {len(actividades)} actividades extraídas")
        
        # Insertar en BD
        insertadas = 0
        
        for act in actividades:
            try:
                columnas = ['actividad', 'evidencia', 'ciclo_phva', 'articulos_decreto',
                           'nivel_pesv', 'responsables', 'recursos', 'estado']
                valores = [
                    act['actividad'][:500] if act['actividad'] else None,
                    act['evidencia'][:500] if act['evidencia'] else None,
                    act['ciclo_phva'][:50] if act['ciclo_phva'] else None,
                    act['articulos'][:200] if act['articulos'] else None,
                    act['nivel_pesv'][:100] if act['nivel_pesv'] else None,
                    act['responsables'][:200] if act['responsables'] else None,
                    act['recursos'][:200] if act['recursos'] else None,
                    'pendiente'
                ]
                
                for mes in meses:
                    if mes in act['programacion']:
                        semanas = act['programacion'][mes]
                        for semana_idx, semana in enumerate(semanas, 1):
                            columnas.append(f'{mes}_semana{semana_idx}_p')
                            valores.append(semana['planificado'])
                            columnas.append(f'{mes}_semana{semana_idx}_e')
                            valores.append(semana['ejecutado'])
                    else:
                        for semana in range(1, 5):
                            columnas.append(f'{mes}_semana{semana}_p')
                            valores.append(False)
                            columnas.append(f'{mes}_semana{semana}_e')
                            valores.append(False)
                
                placeholders = ', '.join(['%s'] * len(valores))
                query = f"""
                    INSERT INTO plan_anual_trabajo ({', '.join(columnas)})
                    VALUES ({placeholders})
                """
                
                cursor.execute(query, valores)
                insertadas += 1
                
            except Exception as e:
                logger.error(f"Error insertando: {e}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash(f'✅ {insertadas} actividades importadas correctamente desde el Excel', 'success')
        logger.info(f"✅ {insertadas} actividades importadas")
        
    except Exception as e:
        flash(f'❌ Error al importar: {str(e)}', 'error')
        logger.error(f"❌ Error en importar_desde_excel: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('sst_plan_anual'))


# Ruta adicional para limpiar datos si es necesario
@app.route('/sst/plan-anual/limpiar-datos')
@login_required
def sst_limpiar_datos():
    """Eliminar todas las actividades del plan anual"""
    if current_user.rol != 'admin':
        flash('Solo el administrador puede eliminar datos', 'error')
        return redirect(url_for('sst_plan_anual'))
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM plan_anual_trabajo")
        conn.commit()
        cursor.close()
        conn.close()
        flash('✅ Todas las actividades han sido eliminadas', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'error')
    
    return redirect(url_for('sst_plan_anual'))

# ===== COPIA TODO ESTE CÓDIGO Y PÉGALO EN TU app.py =====
# ===== PÉGALO JUSTO ANTES DE LA LÍNEA: if __name__ == '__main__': =====

# ========================================
# RUTAS DE GESTIÓN DEL PLAN ANUAL (CRUD)
# ========================================

@app.route('/sst/plan-anual/gestionar')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_plan_anual_gestionar():
    """Panel de gestión de actividades - CRUD completo"""
    if not current_user.puede('gestionar_plan_anual'):
        flash('No tienes permisos para gestionar actividades', 'error')
        return redirect(url_for('sst_plan_anual'))
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Obtener estadísticas
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE ciclo_phva = 'Planear') as planear,
                COUNT(*) FILTER (WHERE ciclo_phva = 'Hacer') as hacer,
                COUNT(*) FILTER (WHERE ciclo_phva = 'Verificar') as verificar,
                COUNT(*) FILTER (WHERE ciclo_phva = 'Actuar') as actuar,
                COUNT(*) FILTER (WHERE estado = 'completado') as completadas,
                COUNT(*) FILTER (WHERE estado = 'en_proceso') as en_proceso,
                COUNT(*) FILTER (WHERE estado = 'pendiente') as pendientes
            FROM plan_anual_trabajo
        """)
        stats = cursor.fetchone()
        
        # Obtener todas las actividades
        filtro_ciclo = request.args.get('ciclo', '')
        filtro_estado = request.args.get('estado', '')
        busqueda = request.args.get('q', '')
        
        query = """
            SELECT 
                id, actividad, ciclo_phva, responsables, estado,
                porcentaje_avance, fecha_actualizacion
            FROM plan_anual_trabajo
            WHERE 1=1
        """
        params = []
        
        if filtro_ciclo:
            query += " AND ciclo_phva = %s"
            params.append(filtro_ciclo)
        
        if filtro_estado:
            query += " AND estado = %s"
            params.append(filtro_estado)
        
        if busqueda:
            query += " AND (actividad ILIKE %s OR responsables ILIKE %s)"
            params.extend([f'%{busqueda}%', f'%{busqueda}%'])
        
        query += " ORDER BY ciclo_phva, actividad LIMIT 100"
        
        cursor.execute(query, params)
        actividades = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('sst/plan_anual_gestionar.html',
                             stats=stats,
                             actividades=actividades,
                             filtro_ciclo=filtro_ciclo,
                             filtro_estado=filtro_estado,
                             busqueda=busqueda)
        
    except Exception as e:
        flash(f'❌ Error al cargar panel de gestión: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual_gestionar: {e}")
        return redirect(url_for('sst_plan_anual'))


@app.route('/sst/plan-anual/actividad/nueva', methods=['GET', 'POST'])
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_plan_anual_nueva_actividad():
    """Crear una nueva actividad del plan anual"""
    if not current_user.puede('gestionar_plan_anual'):
        flash('No tienes permisos para crear actividades', 'error')
        return redirect(url_for('sst_plan_anual_actividades'))
    
    try:
        if request.method == 'POST':
            # Obtener datos del formulario
            actividad = request.form.get('actividad', '').strip()
            evidencia = request.form.get('evidencia', '').strip()
            ciclo_phva = request.form.get('ciclo_phva', '').strip()
            articulos = request.form.get('articulos_decreto', '').strip()
            nivel_pesv = request.form.get('nivel_pesv', '').strip()
            responsables = request.form.get('responsables', '').strip()
            recursos = request.form.get('recursos', '').strip()
            observaciones = request.form.get('observaciones', '').strip()
            estado = request.form.get('estado', 'pendiente')
            
            if not actividad or not ciclo_phva:
                flash('❌ La actividad y el ciclo PHVA son obligatorios', 'error')
                return render_template('sst/plan_anual_nueva.html')
            
            conn = crear_conexion()
            cursor = conn.cursor()
            
            # Construir columnas y valores
            columnas = ['actividad', 'evidencia', 'ciclo_phva', 'articulos_decreto',
                       'nivel_pesv', 'responsables', 'recursos', 'observaciones',
                       'estado', 'usuario_actualizacion']
            
            valores = [
                actividad[:500], evidencia[:500] if evidencia else None, ciclo_phva[:50],
                articulos[:200] if articulos else None, nivel_pesv[:100] if nivel_pesv else None, 
                responsables[:200] if responsables else None,
                recursos[:200] if recursos else None, observaciones, estado, current_user.id
            ]
            
            # Agregar programación mensual
            meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            
            for mes in meses:
                for semana in range(1, 5):
                    key_p = f'{mes}_semana{semana}_p'
                    key_e = f'{mes}_semana{semana}_e'
                    
                    columnas.append(key_p)
                    valores.append(request.form.get(key_p) == 'on')
                    
                    columnas.append(key_e)
                    valores.append(request.form.get(key_e) == 'on')
            
            # Insertar
            placeholders = ', '.join(['%s'] * len(valores))
            query = f"""
                INSERT INTO plan_anual_trabajo ({', '.join(columnas)})
                VALUES ({placeholders})
                RETURNING id
            """
            
            cursor.execute(query, valores)
            new_id = cursor.fetchone()[0]
            
            conn.commit()
            
            # Recalcular porcentaje
            actualizar_porcentaje_avance(new_id)
            
            cursor.close()
            conn.close()
            
            flash('✅ Actividad creada correctamente', 'success')
            logger.info(f"Nueva actividad {new_id} creada por usuario {current_user.id}")
            
            return redirect(url_for('sst_plan_anual_actividad_detalle', id=new_id))
        
        # GET: Mostrar formulario vacío
        return render_template('sst/plan_anual_nueva.html')
        
    except Exception as e:
        flash(f'❌ Error al crear actividad: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual_nueva_actividad: {e}")
        return redirect(url_for('sst_plan_anual_actividades'))


@app.route('/sst/plan-anual/actividad/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_plan_anual_editar_actividad(id):
    """Editar una actividad del plan anual"""
    if not current_user.puede('gestionar_plan_anual'):
        flash('No tienes permisos para editar actividades', 'error')
        return redirect(url_for('sst_plan_anual_actividades'))
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        if request.method == 'POST':
            # Obtener datos del formulario
            actividad = request.form.get('actividad', '').strip()
            evidencia = request.form.get('evidencia', '').strip()
            ciclo_phva = request.form.get('ciclo_phva', '').strip()
            articulos = request.form.get('articulos_decreto', '').strip()
            nivel_pesv = request.form.get('nivel_pesv', '').strip()
            responsables = request.form.get('responsables', '').strip()
            recursos = request.form.get('recursos', '').strip()
            observaciones = request.form.get('observaciones', '').strip()
            estado = request.form.get('estado', 'pendiente')
            
            if not actividad or not ciclo_phva:
                flash('❌ La actividad y el ciclo PHVA son obligatorios', 'error')
                return redirect(url_for('sst_plan_anual_editar_actividad', id=id))
            
            # Construir query de actualización
            query = """
                UPDATE plan_anual_trabajo 
                SET actividad = %s, evidencia = %s, ciclo_phva = %s, 
                    articulos_decreto = %s, nivel_pesv = %s, responsables = %s,
                    recursos = %s, observaciones = %s, estado = %s,
                    fecha_actualizacion = CURRENT_TIMESTAMP,
                    usuario_actualizacion = %s
                WHERE id = %s
            """
            
            cursor.execute(query, (
                actividad[:500], evidencia[:500] if evidencia else None, ciclo_phva[:50],
                articulos[:200] if articulos else None, nivel_pesv[:100] if nivel_pesv else None, 
                responsables[:200] if responsables else None,
                recursos[:200] if recursos else None, observaciones, estado, current_user.id, id
            ))
            
            # Actualizar programación mensual
            meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            
            for mes in meses:
                for semana in range(1, 5):
                    # Planificado
                    key_p = f'{mes}_semana{semana}_p'
                    val_p = request.form.get(key_p) == 'on'
                    
                    # Ejecutado
                    key_e = f'{mes}_semana{semana}_e'
                    val_e = request.form.get(key_e) == 'on'
                    
                    cursor.execute(f"""
                        UPDATE plan_anual_trabajo 
                        SET {key_p} = %s, {key_e} = %s
                        WHERE id = %s
                    """, (val_p, val_e, id))
            
            conn.commit()
            
            # Recalcular porcentaje
            actualizar_porcentaje_avance(id)
            
            flash('✅ Actividad actualizada correctamente', 'success')
            cursor.close()
            conn.close()
            return redirect(url_for('sst_plan_anual_actividad_detalle', id=id))
        
        # GET: Cargar actividad
        cursor.execute("SELECT * FROM plan_anual_trabajo WHERE id = %s", (id,))
        actividad_data = cursor.fetchone()
        
        if not actividad_data:
            flash('❌ Actividad no encontrada', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('sst_plan_anual_actividades'))
        
        # Estructurar datos
        actividad = {
            'id': actividad_data[0],
            'actividad': actividad_data[1],
            'evidencia': actividad_data[2],
            'ciclo_phva': actividad_data[3],
            'articulos_decreto': actividad_data[4],
            'nivel_pesv': actividad_data[5],
            'responsables': actividad_data[6],
            'recursos': actividad_data[7],
            'observaciones': actividad_data[103] if len(actividad_data) > 103 else '',
            'estado': actividad_data[104] if len(actividad_data) > 104 else 'pendiente',
            'porcentaje_avance': actividad_data[105] if len(actividad_data) > 105 else 0
        }
        
        # Extraer programación mensual
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        
        programacion = {}
        col_offset = 8
        
        for i, mes in enumerate(meses):
            programacion[mes] = []
            for semana in range(1, 5):
                idx_p = col_offset + (i * 8) + ((semana - 1) * 2)
                idx_e = idx_p + 1
                
                programacion[mes].append({
                    'semana': semana,
                    'planificado': actividad_data[idx_p] if idx_p < len(actividad_data) else False,
                    'ejecutado': actividad_data[idx_e] if idx_e < len(actividad_data) else False
                })
        
        actividad['programacion'] = programacion
        
        cursor.close()
        conn.close()
        
        return render_template('sst/plan_anual_editar.html', actividad=actividad)
        
    except Exception as e:
        flash(f'❌ Error al editar actividad: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual_editar_actividad: {e}")
        return redirect(url_for('sst_plan_anual_actividades'))


@app.route('/sst/plan-anual/actividad/<int:id>/eliminar', methods=['POST'])
@login_required
def sst_plan_anual_eliminar_actividad(id):
    """Eliminar una actividad del plan anual"""
    if not current_user.puede('gestionar_plan_anual'):
        flash('No tienes permisos para eliminar actividades', 'error')
        return redirect(url_for('sst_plan_anual_actividades'))
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Verificar que existe
        cursor.execute("SELECT actividad FROM plan_anual_trabajo WHERE id = %s", (id,))
        actividad = cursor.fetchone()
        
        if not actividad:
            flash('❌ Actividad no encontrada', 'error')
        else:
            # Eliminar
            cursor.execute("DELETE FROM plan_anual_trabajo WHERE id = %s", (id,))
            conn.commit()
            flash(f'✅ Actividad "{actividad[0][:50]}..." eliminada correctamente', 'success')
            logger.info(f"Actividad {id} eliminada por usuario {current_user.id}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        flash(f'❌ Error al eliminar: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual_eliminar_actividad: {e}")
    
    return redirect(url_for('sst_plan_anual_actividades'))


@app.route('/sst/plan-anual/gestionar/limpiar-masivo', methods=['POST'])
@login_required
def sst_plan_anual_limpiar_masivo():
    """Eliminar múltiples actividades seleccionadas"""
    if current_user.rol != 'admin':
        flash('Solo el administrador puede eliminar masivamente', 'error')
        return redirect(url_for('sst_plan_anual_gestionar'))
    
    try:
        ids = request.form.getlist('actividad_ids')
        
        if not ids:
            flash('❌ No se seleccionaron actividades', 'warning')
            return redirect(url_for('sst_plan_anual_gestionar'))
        
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Convertir a enteros
        ids_int = [int(id) for id in ids]
        
        # Eliminar
        placeholders = ', '.join(['%s'] * len(ids_int))
        query = f"DELETE FROM plan_anual_trabajo WHERE id IN ({placeholders})"
        cursor.execute(query, ids_int)
        
        eliminadas = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        flash(f'✅ {eliminadas} actividades eliminadas correctamente', 'success')
        logger.info(f"Eliminación masiva de {eliminadas} actividades por admin {current_user.id}")
        
    except Exception as e:
        flash(f'❌ Error en eliminación masiva: {str(e)}', 'error')
        logger.error(f"Error en sst_plan_anual_limpiar_masivo: {e}")
    
    return redirect(url_for('sst_plan_anual_gestionar'))


# ========================================
# RUTA MEJORADA PARA LIMPIAR DATOS (CON CONFIRMACIÓN)
# ========================================

@app.route('/sst/plan-anual/limpiar-datos', methods=['GET', 'POST'])
@login_required
def sst_plan_anual_limpiar_datos():
    """Eliminar todas las actividades del plan anual - CON CONFIRMACIÓN"""
    if current_user.rol != 'admin':
        flash('❌ Solo el administrador puede eliminar todos los datos', 'error')
        return redirect(url_for('sst_plan_anual'))
    
    if request.method == 'POST':
        # Solo se ejecuta si se confirmó el formulario
        confirmacion = request.form.get('confirmacion', '')
        
        if confirmacion != 'ELIMINAR TODO':
            flash('❌ Debes escribir "ELIMINAR TODO" para confirmar', 'error')
            return redirect(url_for('sst_plan_anual_limpiar_datos'))
        
        try:
            conn = crear_conexion()
            cursor = conn.cursor()
            
            # Contar antes de eliminar
            cursor.execute("SELECT COUNT(*) FROM plan_anual_trabajo")
            total = cursor.fetchone()[0]
            
            # Eliminar todo
            cursor.execute("DELETE FROM plan_anual_trabajo")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            flash(f'✅ {total} actividades eliminadas correctamente', 'success')
            logger.info(f"Admin {current_user.id} eliminó {total} actividades del plan anual")
            
        except Exception as e:
            flash(f'❌ Error al eliminar: {str(e)}', 'error')
            logger.error(f"Error en sst_plan_anual_limpiar_datos: {e}")
        
        return redirect(url_for('sst_plan_anual'))
    
    # GET: Mostrar página de confirmación
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Obtener estadísticas antes de eliminar
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE ciclo_phva = 'Planear') as planear,
                COUNT(*) FILTER (WHERE ciclo_phva = 'Hacer') as hacer,
                COUNT(*) FILTER (WHERE ciclo_phva = 'Verificar') as verificar,
                COUNT(*) FILTER (WHERE ciclo_phva = 'Actuar') as actuar
            FROM plan_anual_trabajo
        """)
        stats = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return render_template('sst/plan_anual_limpiar_confirmacion.html', stats=stats)
        
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'error')
        return redirect(url_for('sst_plan_anual'))


# ========================================
# FUNCIÓN AUXILIAR (actualizar_porcentaje_avance)
# ========================================
# IMPORTANTE: Esta función debe existir para que las rutas anteriores funcionen

def actualizar_porcentaje_avance(id):
    """Actualizar automáticamente el porcentaje de avance de una actividad"""
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
        
        # Construir lista de columnas planificadas
        columnas_p = []
        for mes in meses:
            for semana in range(1, 5):
                columnas_p.append(f'{mes}_semana{semana}_p')
        
        # Contar semanas planificadas
        query_p = f"""
            SELECT {' + '.join([f'CASE WHEN {col} = TRUE THEN 1 ELSE 0 END' for col in columnas_p])}
            FROM plan_anual_trabajo WHERE id = %s
        """
        cursor.execute(query_p, (id,))
        total_planificadas = cursor.fetchone()[0]
        
        # Construir lista de columnas ejecutadas
        columnas_e = [col.replace('_p', '_e') for col in columnas_p]
        
        # Contar semanas ejecutadas
        query_e = f"""
            SELECT {' + '.join([f'CASE WHEN {col} = TRUE THEN 1 ELSE 0 END' for col in columnas_e])}
            FROM plan_anual_trabajo WHERE id = %s
        """
        cursor.execute(query_e, (id,))
        total_ejecutadas = cursor.fetchone()[0]
        
        # Calcular porcentaje
        porcentaje = 0
        if total_planificadas > 0:
            porcentaje = round((total_ejecutadas / total_planificadas) * 100, 2)
        
        # Determinar estado
        if porcentaje == 100:
            estado = 'completado'
        elif porcentaje > 0:
            estado = 'en_proceso'
        else:
            estado = 'pendiente'
        
        # Actualizar
        cursor.execute("""
            UPDATE plan_anual_trabajo 
            SET porcentaje_avance = %s, estado = %s
            WHERE id = %s
        """, (porcentaje, estado, id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return porcentaje, estado
        
    except Exception as e:
        logger.error(f"Error al actualizar porcentaje: {e}")
        return 0, 'pendiente'
    # ===== AGREGAR ESTAS RUTAS A app.py =====
# ===== PEGA ANTES DE: if __name__ == '__main__': =====

# ========================================
# RUTAS DE GESTIÓN DE CONTENIDO SST
# ========================================

@app.route('/sst/agregar-contenido', methods=['GET', 'POST'])
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_agregar_contenido():
    """Agregar nuevo contenido de capacitación SST"""
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden agregar contenido', 'error')
        return redirect(url_for('sst_contenido'))
    
    try:
        if request.method == 'POST':
            titulo = request.form.get('titulo', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            categoria_id = request.form.get('categoria_id')
            tipo_contenido = request.form.get('tipo_contenido')
            es_obligatorio = request.form.get('es_obligatorio') == 'on'
            
            if not titulo or not categoria_id:
                flash('El título y la categoría son obligatorios', 'error')
                return redirect(url_for('sst_agregar_contenido'))
            
            conn = crear_conexion()
            cursor = conn.cursor()
            
            # Manejar archivos
            archivo = None
            ruta_archivo = None
            tamano_archivo = None
            
            if 'archivo' in request.files:
                file = request.files['archivo']
                if file and file.filename:
                    from werkzeug.utils import secure_filename
                    import os
                    
                    filename = secure_filename(file.filename)
                    
                    # Crear directorio si no existe
                    upload_dir = 'static/uploads/sst'
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    # Guardar archivo
                    filepath = os.path.join(upload_dir, filename)
                    file.save(filepath)
                    
                    ruta_archivo = filepath
                    tamano_archivo = os.path.getsize(filepath)
                    archivo = filename
            
            # Manejar URL de video
            url_video = request.form.get('url_video', '').strip()
            duracion_minutos = request.form.get('duracion_minutos')
            
            # Insertar contenido
            cursor.execute("""
                INSERT INTO sst_contenido 
                (titulo, descripcion, categoria_id, tipo_contenido, es_obligatorio,
                 archivo, ruta_archivo, tamano_archivo, url_video, duracion_minutos,
                 creado_por, fecha_creacion)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, (titulo, descripcion, categoria_id, tipo_contenido, es_obligatorio,
                  archivo, ruta_archivo, tamano_archivo, url_video, duracion_minutos,
                  current_user.id))
            
            new_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()
            
            flash(f'✅ Contenido "{titulo}" agregado correctamente', 'success')
            logger.info(f"Contenido SST {new_id} creado por usuario {current_user.id}")
            
            return redirect(url_for('sst_contenido'))
        
        # GET: Mostrar formulario
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Obtener categorías
        cursor.execute("SELECT id, nombre FROM sst_categorias ORDER BY nombre")
        categorias = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('sst/agregar_contenido.html', categorias=categorias)
        
    except Exception as e:
        flash(f'❌ Error al agregar contenido: {str(e)}', 'error')
        logger.error(f"Error en sst_agregar_contenido: {e}")
        return redirect(url_for('sst_contenido'))


@app.route('/sst/editar-contenido/<int:id>', methods=['GET', 'POST'])
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
def sst_editar_contenido(id):
    """Editar contenido SST existente"""
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden editar contenido', 'error')
        return redirect(url_for('sst_contenido'))
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        if request.method == 'POST':
            titulo = request.form.get('titulo', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            categoria_id = request.form.get('categoria_id')
            tipo_contenido = request.form.get('tipo_contenido')
            es_obligatorio = request.form.get('es_obligatorio') == 'on'
            
            if not titulo or not categoria_id:
                flash('El título y la categoría son obligatorios', 'error')
                return redirect(url_for('sst_editar_contenido', id=id))
            
            # Manejar nuevo archivo (si se sube)
            archivo = None
            ruta_archivo = None
            tamano_archivo = None
            
            if 'archivo' in request.files:
                file = request.files['archivo']
                if file and file.filename:
                    from werkzeug.utils import secure_filename
                    import os
                    
                    filename = secure_filename(file.filename)
                    upload_dir = 'static/uploads/sst'
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    filepath = os.path.join(upload_dir, filename)
                    file.save(filepath)
                    
                    ruta_archivo = filepath
                    tamano_archivo = os.path.getsize(filepath)
                    archivo = filename
            
            url_video = request.form.get('url_video', '').strip()
            duracion_minutos = request.form.get('duracion_minutos')
            
            # Actualizar contenido
            if archivo:  # Si se subió nuevo archivo
                cursor.execute("""
                    UPDATE sst_contenido 
                    SET titulo = %s, descripcion = %s, categoria_id = %s,
                        tipo_contenido = %s, es_obligatorio = %s,
                        archivo = %s, ruta_archivo = %s, tamano_archivo = %s,
                        url_video = %s, duracion_minutos = %s,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (titulo, descripcion, categoria_id, tipo_contenido, es_obligatorio,
                      archivo, ruta_archivo, tamano_archivo, url_video, duracion_minutos, id))
            else:  # Sin cambiar archivo
                cursor.execute("""
                    UPDATE sst_contenido 
                    SET titulo = %s, descripcion = %s, categoria_id = %s,
                        tipo_contenido = %s, es_obligatorio = %s,
                        url_video = %s, duracion_minutos = %s,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (titulo, descripcion, categoria_id, tipo_contenido, es_obligatorio,
                      url_video, duracion_minutos, id))
            
            conn.commit()
            flash(f'✅ Contenido "{titulo}" actualizado correctamente', 'success')
            logger.info(f"Contenido SST {id} editado por usuario {current_user.id}")
            
            cursor.close()
            conn.close()
            return redirect(url_for('sst_contenido'))
        
        # GET: Cargar datos del contenido
        cursor.execute("""
            SELECT 
                c.id, c.titulo, c.descripcion, c.categoria_id, c.tipo_contenido,
                c.es_obligatorio, c.archivo, c.url_video, c.duracion_minutos,
                cat.nombre as categoria_nombre
            FROM sst_contenido c
            LEFT JOIN sst_categorias cat ON c.categoria_id = cat.id
            WHERE c.id = %s
        """, (id,))
        
        contenido = cursor.fetchone()
        
        if not contenido:
            flash('❌ Contenido no encontrado', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('sst_contenido'))
        
        # Obtener categorías
        cursor.execute("SELECT id, nombre FROM sst_categorias ORDER BY nombre")
        categorias = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('sst/editar_contenido.html', 
                             contenido=contenido, 
                             categorias=categorias)
        
    except Exception as e:
        flash(f'❌ Error al editar contenido: {str(e)}', 'error')
        logger.error(f"Error en sst_editar_contenido: {e}")
        return redirect(url_for('sst_contenido'))


@app.route('/sst/eliminar-contenido/<int:id>', methods=['POST'])
@login_required
def sst_eliminar_contenido(id):
    """Eliminar contenido SST"""
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden eliminar contenido', 'error')
        return redirect(url_for('sst_contenido'))
    
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        
        # Obtener info antes de eliminar
        cursor.execute("SELECT titulo, ruta_archivo FROM sst_contenido WHERE id = %s", (id,))
        contenido = cursor.fetchone()
        
        if not contenido:
            flash('❌ Contenido no encontrado', 'error')
        else:
            # Eliminar archivo físico si existe
            if contenido[1]:
                import os
                try:
                    if os.path.exists(contenido[1]):
                        os.remove(contenido[1])
                except Exception as e:
                    logger.warning(f"No se pudo eliminar archivo físico: {e}")
            
            # Eliminar de BD
            cursor.execute("DELETE FROM sst_contenido WHERE id = %s", (id,))
            conn.commit()
            
            flash(f'✅ Contenido "{contenido[0]}" eliminado correctamente', 'success')
            logger.info(f"Contenido SST {id} eliminado por admin {current_user.id}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        flash(f'❌ Error al eliminar: {str(e)}', 'error')
        logger.error(f"Error en sst_eliminar_contenido: {e}")
    
    return redirect(url_for('sst_contenido'))

# EN LA SECCIÓN DE INICIALIZACIÓN DEL APP
if __name__ == '__main__':
    with app.app_context():
        print("🚀 Iniciando la aplicación Flask...")
        print("📊 Creando tablas en la base de datos...")
        crear_tablas()
        print("✅ Tablas creadas/verificadas correctamente")
        
        print("📋 Verificando categorías SST...")
        try:
            verificar_y_crear_categorias_sst()
            print("✅ Categorías SST verificadas correctamente")
        except Exception as e:
            print(f"⚠️  Advertencia al crear categorías SST: {e}")
        
        # AÑADE ESTA LÍNEA:
        print("📥 Inicializando datos del plan anual...")
        inicializar_plan_anual()
    
    print("🌐 Aplicación lista en http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
