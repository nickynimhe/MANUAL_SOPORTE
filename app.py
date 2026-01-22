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

# ===== DECORADORES DE PERMISOS MEJORADOS =====
def requiere_permiso(permiso):
    """Decorador para verificar permisos específicos"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Debes iniciar sesión para acceder a esta página', 'error')
                return redirect(url_for('login'))
            
            if not current_user.puede(permiso):
                flash(f'No tienes permisos para {permiso.replace("_", " ")}', 'error')
                return redirect_a_modulo_principal()
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

def requiere_rol(*roles):
    """Decorador para verificar roles específicos"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Debes iniciar sesión para acceder a esta página', 'error')
                return redirect(url_for('login'))
            
            if current_user.rol not in roles:
                flash('No tienes los permisos necesarios para acceder a esta página', 'error')
                return redirect_a_modulo_principal()
            
            return func(*args, **kwargs)
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

# ===== FUNCIONES DE UTILIDAD =====
def obtener_template_base():
    """Determina qué template base usar según el rol del usuario"""
    if not current_user.is_authenticated:
        return 'base.html'
    
    rol = current_user.rol.lower()
    
    if rol == 'admin':
        return 'base_admin.html'
    elif rol == 'sst':
        return 'base_sst.html'
    elif rol == 'soporte':
        return 'base_soporte.html'
    else:
        return 'base.html'

def redirect_a_modulo_principal():
    """Redirige al usuario a su módulo principal"""
    if current_user.is_authenticated:
        if current_user.rol == 'admin':
            return redirect(url_for('dashboard_admin'))
        elif current_user.rol == 'sst':
            return redirect(url_for('sst_dashboard'))
        elif current_user.rol == 'soporte':
            return redirect(url_for('index'))
    
    return redirect(url_for('login'))

# ===== CONTEXT PROCESSORS MEJORADOS =====
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

@app.context_processor
def inject_template_base():
    """Inyecta la función para obtener el template base correcto"""
    return dict(obtener_template_base=obtener_template_base)

@app.context_processor
def inject_permissions():
    def tiene_permiso(permiso):
        if current_user.is_authenticated:
            return current_user.puede(permiso)
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
    
    def obtener_color_por_rol(rol=None):
        """Devuelve el color principal según el rol"""
        if not rol:
            rol = current_user.rol if current_user.is_authenticated else 'soporte'
        
        colores = {
            'admin': '#052398',
            'sst': '#198754',
            'soporte': '#0d6efd'
        }
        return colores.get(rol.lower(), '#0d6efd')
    
    def obtener_icono_por_rol(rol=None):
        """Devuelve el icono según el rol"""
        if not rol:
            rol = current_user.rol if current_user.is_authenticated else 'soporte'
        
        iconos = {
            'admin': 'fa-crown',
            'sst': 'fa-shield-alt',
            'soporte': 'fa-headset'
        }
        return iconos.get(rol.lower(), 'fa-user')
    
    return dict(
        tiene_permiso=tiene_permiso,
        puede_acceder_modulo=puede_acceder_modulo,
        obtener_modulo_principal=obtener_modulo_principal,
        obtener_color_por_rol=obtener_color_por_rol,
        obtener_icono_por_rol=obtener_icono_por_rol
    )

# ===== FILTROS TEMPLATE =====
@app.template_filter('format_date')
def format_date_filter(date_value, format='%d/%m/%Y'):
    """Filtro para formatear fechas"""
    if date_value is None:
        return 'Sin fecha'
    try:
        return date_value.strftime(format)
    except:
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

@app.template_filter('badge_color_rol')
def badge_color_rol_filter(rol):
    """Devuelve el color de badge según el rol"""
    colores = {
        'admin': 'danger',
        'sst': 'success',
        'soporte': 'warning'
    }
    return colores.get(rol.lower(), 'secondary')

# ===== MODELO DE USUARIO MEJORADO =====
class User(UserMixin):
    def __init__(self, id, usuario, rol, modulo_principal, permisos=None):
        self.id = id
        self.usuario = usuario
        self.rol = rol
        self.modulo_principal = modulo_principal
        self.permisos = permisos or {}
        
        # Definir permisos por rol (esto es un fallback)
        if rol == 'admin':
            self.permisos = {
                'ver_fichas': True,
                'agregar_fichas': True,
                'editar_fichas': True,
                'eliminar_fichas': True,
                'cambiar_password': True,
                'gestion_usuarios': True,
                'acceder_sst': True,
                'acceder_soporte': True,
                'acceder_dashboard': True,
                'gestionar_contenido_sst': True
            }
        elif rol == 'sst':
            self.permisos = {
                'ver_fichas': False,
                'agregar_fichas': False,
                'editar_fichas': False,
                'eliminar_fichas': False,
                'cambiar_password': True,
                'gestion_usuarios': False,
                'acceder_sst': True,
                'acceder_soporte': False,
                'acceder_dashboard': False,
                'gestionar_contenido_sst': False
            }
        elif rol == 'soporte':
            self.permisos = {
                'ver_fichas': True,
                'agregar_fichas': True,
                'editar_fichas': True,
                'eliminar_fichas': True,
                'cambiar_password': True,
                'gestion_usuarios': False,
                'acceder_sst': False,
                'acceder_soporte': True,
                'acceder_dashboard': False,
                'gestionar_contenido_sst': False
            }
        
        # Sobrescribir con permisos personalizados si existen
        if permisos:
            self.permisos.update(permisos)

    def puede(self, permiso):
        return self.permisos.get(permiso, False)

@login_manager.user_loader
def load_user(user_id):
    try:
        resultado = ejecutar_consulta(
            "SELECT * FROM usuarios WHERE id = %s", 
            (user_id,), 
            fetch=True
        )
        
        if resultado and resultado[0]:
            user_data = resultado[0]
            user_dict = {
                'id': user_data[0],
                'usuario': user_data[1],
                'password': user_data[2],
                'rol': user_data[3],
                'modulo_principal': user_data[4] if user_data[4] else 'soporte',
                'permisos': user_data[5]
            }
            
            # Cargar permisos desde JSON si existen
            permisos = {}
            if user_dict.get('permisos'):
                try:
                    permisos = json.loads(user_dict['permisos'])
                except:
                    permisos = {}
            
            return User(
                user_dict['id'], 
                user_dict['usuario'], 
                user_dict['rol'],
                user_dict['modulo_principal'],
                permisos
            )
    except Exception as e:
        logger.error(f"Error en load_user: {e}")
    return None

# ===== RUTAS DE AUTENTICACIÓN =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_a_modulo_principal()
    
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']
        
        try:
            resultado = ejecutar_consulta(
                "SELECT * FROM usuarios WHERE usuario = %s", 
                (usuario,), 
                fetch=True
            )
            
            if resultado and resultado[0] and resultado[0][2] and resultado[0][2].strip():
                user_data = resultado[0]
                user_dict = {
                    'id': user_data[0],
                    'usuario': user_data[1],
                    'password': user_data[2],
                    'rol': user_data[3],
                    'modulo_principal': user_data[4] if user_data[4] else 'soporte',
                    'permisos': user_data[5]
                }
                
                if check_password_hash(user_dict['password'], password):
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
                    login_user(user)
                    flash(f'¡Bienvenido {user.usuario}!', 'success')
                    return redirect_a_modulo_principal()
                else:
                    flash('Usuario o contraseña incorrectos', 'error')
            else:
                flash('Usuario no encontrado', 'error')
                
        except Exception as e:
            flash('Error de base de datos', 'error')
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

# ===== DASHBOARD ADMIN MEJORADO =====
@app.route('/admin/dashboard')
@login_required
@requiere_rol('admin')
def dashboard_admin():
    """Dashboard exclusivo para administradores"""
    
    try:
        stats = {}
        
        # Contar usuarios totales
        resultado = ejecutar_consulta("SELECT COUNT(*) FROM usuarios", fetch=True)
        stats['total_usuarios'] = resultado[0][0] if resultado else 0
        
        # Contar por rol
        resultado = ejecutar_consulta("SELECT rol, COUNT(*) FROM usuarios GROUP BY rol", fetch=True)
        stats['usuarios_por_rol'] = {row[0]: row[1] for row in resultado} if resultado else {}
        
        # Contar fichas de soporte
        resultado = ejecutar_consulta("SELECT COUNT(*) FROM fichas", fetch=True)
        stats['total_fichas'] = resultado[0][0] if resultado else 0
        
        # Contar contenido SST
        resultado = ejecutar_consulta("SELECT COUNT(*) FROM sst_contenido", fetch=True)
        stats['total_contenido_sst'] = resultado[0][0] if resultado else 0
        
        # Últimos usuarios registrados
        resultado = ejecutar_consulta(
            "SELECT id, usuario, rol, fecha_creacion FROM usuarios ORDER BY fecha_creacion DESC LIMIT 5", 
            fetch=True
        )
        stats['ultimos_usuarios'] = [
            {
                'id': row[0],
                'usuario': row[1],
                'rol': row[2],
                'fecha_creacion': row[3]
            }
            for row in resultado
        ] if resultado else []
        
        # Últimas fichas creadas
        resultado = ejecutar_consulta(
            "SELECT id, categoria, problema, fecha_creacion FROM fichas ORDER BY fecha_creacion DESC LIMIT 5",
            fetch=True
        )
        stats['ultimas_fichas'] = [
            {
                'id': row[0],
                'categoria': row[1],
                'problema': row[2],
                'fecha_creacion': row[3]
            }
            for row in resultado
        ] if resultado else []
        
    except Exception as e:
        flash('Error al cargar estadísticas', 'error')
        logger.error(f"Error en dashboard_admin: {e}")
        stats = {}
    
    return render_template('admin/dashboard.html', stats=stats)

# ===== RUTAS DE SOPORTE TÉCNICO =====
@app.route('/')
@app.route('/soporte')
@app.route('/soporte/index')
@login_required
@requiere_permiso('acceder_soporte')
def index():
    """Página principal del módulo de soporte"""
    
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
    
    return render_template('soporte/index.html', fichas=fichas)

@app.route('/soporte/agregar', methods=['GET', 'POST'])
@login_required
@requiere_permiso('agregar_fichas')
def agregar_ficha():
    if request.method == 'POST':
        categoria = request.form.get('categoria', '')
        problema = request.form.get('problema', '')
        descripcion = request.form.get('descripcion', '')
        causas = request.form.get('causas', '')
        solucion = request.form.get('solucion', '')
        palabras_clave = request.form.get('palabras_clave', '')
        
        campos_requeridos = {
            'categoria': categoria,
            'problema': problema, 
            'causas': causas,
            'solucion': solucion
        }
        
        campos_faltantes = [campo for campo, valor in campos_requeridos.items() if not valor]
        
        if campos_faltantes:
            flash('Por favor, complete todos los campos requeridos', 'error')
            return render_template('soporte/agregar_ficha.html')
        
        try:
            ejecutar_consulta('''
                INSERT INTO fichas (categoria, problema, descripcion, causas, solucion, palabras_clave)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (categoria, problema, descripcion, causas, solucion, palabras_clave), commit=True)
            
            flash('Ficha agregada correctamente', 'success')
            return redirect(url_for('index'))
                
        except Exception as e:
            flash(f'Error al agregar la ficha: {str(e)}', 'error')
    
    return render_template('soporte/agregar_ficha.html')

@app.route('/soporte/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@requiere_permiso('editar_fichas')
def editar_ficha(id):
    ficha = None
    
    try:
        if request.method == 'POST':
            categoria = request.form['categoria']
            problema = request.form['problema']
            descripcion = request.form['descripcion']
            causas = request.form['causas']
            solucion = request.form['solucion']
            palabras_clave = request.form['palabras_clave']
            
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
            
            if ficha and ficha['causas']:
                ficha['causas'] = ficha['causas'].replace('|', '\n')
            
    except Exception as e:
        flash('Error al cargar/editar la ficha', 'error')
        logger.error(f"Error en editar_ficha: {e}")
    
    if not ficha:
        flash('Ficha no encontrada', 'error')
        return redirect(url_for('index'))
    
    return render_template('soporte/editar_ficha.html', ficha=ficha)

@app.route('/soporte/eliminar/<int:id>')
@login_required
@requiere_permiso('eliminar_fichas')
def eliminar_ficha(id):
    try:
        ejecutar_consulta("DELETE FROM fichas WHERE id = %s", (id,), commit=True)
        flash('Ficha eliminada correctamente', 'success')
    except Exception as e:
        flash('Error al eliminar la ficha', 'error')
        logger.error(f"Error en eliminar_ficha: {e}")
    
    return redirect(url_for('index'))

@app.route('/soporte/buscar')
@login_required
@requiere_permiso('ver_fichas')
def buscar():
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
    
    return render_template('soporte/buscar.html', fichas=fichas, query=query, categoria=categoria)

@app.route('/soporte/ficha/<int:id>')
@login_required
@requiere_permiso('ver_fichas')
def ver_ficha(id):
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
    
    return render_template('soporte/ver_ficha.html', ficha=ficha)

# ===== RUTAS DE GESTIÓN DE USUARIOS (Solo Admin) =====
@app.route('/admin/usuarios')
@login_required
@requiere_rol('admin')
def gestion_usuarios():
    usuarios = []
    
    try:
        resultado = ejecutar_consulta("SELECT * FROM usuarios ORDER BY fecha_creacion DESC", fetch=True)
        
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
            
            if usuario_dict.get('permisos'):
                try:
                    usuario_dict['permisos_parsed'] = json.loads(usuario_dict['permisos'])
                except:
                    usuario_dict['permisos_parsed'] = {}
            else:
                usuario_dict['permisos_parsed'] = {}
            
            usuarios.append(usuario_dict)
                    
    except Exception as e:
        flash('Error al cargar los usuarios', 'error')
        logger.error(f"Error en gestion_usuarios: {e}")
    
    return render_template('admin/gestion_usuarios.html', usuarios=usuarios)

@app.route('/admin/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@requiere_rol('admin')
def editar_usuario(id):
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
                'cambiar_password': True,
                'gestion_usuarios': rol == 'admin',
                'acceder_sst': rol in ['admin', 'sst'],
                'acceder_soporte': rol in ['admin', 'soporte'],
                'acceder_dashboard': rol == 'admin',
                'gestionar_contenido_sst': rol == 'admin'
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
    
    return render_template('admin/editar_usuario.html', usuario=usuario_data)

@app.route('/admin/usuarios/agregar', methods=['GET', 'POST'])
@login_required
@requiere_rol('admin')
def agregar_usuario():
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']
        rol = request.form['rol']
        modulo_principal = request.form['modulo_principal']
        
        if not usuario or not password:
            flash('Usuario y contraseña son obligatorios', 'error')
            return render_template('admin/agregar_usuario.html')
        
        permisos = {
            'ver_fichas': 'ver_fichas' in request.form,
            'agregar_fichas': 'agregar_fichas' in request.form,
            'editar_fichas': 'editar_fichas' in request.form,
            'eliminar_fichas': 'eliminar_fichas' in request.form,
            'cambiar_password': True,
            'gestion_usuarios': rol == 'admin',
            'acceder_sst': rol in ['admin', 'sst'],
            'acceder_soporte': rol in ['admin', 'soporte'],
            'acceder_dashboard': rol == 'admin',
            'gestionar_contenido_sst': rol == 'admin'
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
    
    return render_template('admin/agregar_usuario.html')

@app.route('/admin/usuarios/eliminar/<int:id>')
@login_required
@requiere_rol('admin')
def eliminar_usuario(id):
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

# ===== RUTAS DE INFORMACIÓN (Accesibles para todos los roles autenticados) =====
@app.route('/informacion/soluciones-visuales')
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
        # Agrega aquí el resto de soluciones visuales
    ]
    return render_template('informacion/soluciones_visuales.html', soluciones=soluciones)

@app.route('/informacion/atencion-telefonica')
@login_required
def atencion_telefonica():
    return render_template('informacion/atencion_telefonica.html')

@app.route('/informacion/general')
@login_required
def informacion_general():
    informacion = {
        'planes': {
            'titulo': '📡 Planes de Servicio',
            'icono': 'fa-tv',
            'contenido': []
        },
    }
    
    return render_template('informacion/general.html', informacion=informacion)

# ===== RUTAS SST MEJORADAS =====
@app.route('/sst/dashboard')
@login_required
@requiere_permiso('acceder_sst')
def sst_dashboard():
    """Dashboard principal de SST"""
    try:
        # Obtener estadísticas para el dashboard SST
        stats = {}
        
        # Contar contenido por tipo
        resultado = ejecutar_consulta(
            "SELECT tipo, COUNT(*) FROM sst_contenido GROUP BY tipo",
            fetch=True
        )
        stats['contenido_por_tipo'] = {row[0]: row[1] for row in resultado} if resultado else {}
        
        # Contar contenido obligatorio vs opcional
        resultado = ejecutar_consulta(
            "SELECT es_obligatorio, COUNT(*) FROM sst_contenido GROUP BY es_obligatorio",
            fetch=True
        )
        stats['obligatorios_vs_opcionales'] = {
            'Obligatorio': 0,
            'Opcional': 0
        }
        if resultado:
            for row in resultado:
                if row[0]:
                    stats['obligatorios_vs_opcionales']['Obligatorio'] = row[1]
                else:
                    stats['obligatorios_vs_opcionales']['Opcional'] = row[1]
        
        # Último contenido agregado
        resultado = ejecutar_consulta(
            """SELECT sc.id, sc.titulo, sc.tipo, sc.fecha_publicacion, cat.nombre 
               FROM sst_contenido sc 
               LEFT JOIN sst_categorias cat ON sc.categoria_id = cat.id 
               ORDER BY sc.fecha_publicacion DESC LIMIT 5""",
            fetch=True
        )
        stats['ultimo_contenido'] = [
            {
                'id': row[0],
                'titulo': row[1],
                'tipo': row[2],
                'fecha': row[3],
                'categoria': row[4]
            }
            for row in resultado
        ] if resultado else []
        
    except Exception as e:
        flash('Error al cargar estadísticas SST', 'error')
        logger.error(f"Error en sst_dashboard: {e}")
        stats = {}
    
    return render_template('sst/dashboard.html', stats=stats)

@app.route('/sst/contenido')
@login_required
@requiere_permiso('acceder_sst')
def sst_contenido():
    """Lista de todo el contenido SST"""
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
            'tipo': request.args.get('tipo', ''),
            'es_obligatorio': request.args.get('obligatorio', '')
        }
        
        # Obtener contenido
        contenido_data = obtener_contenido_sst(filtros)
        
        for item in contenido_data:
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

@app.route('/sst/contenido/agregar', methods=['GET', 'POST'])
@login_required
@requiere_permiso('gestionar_contenido_sst')
def sst_agregar_contenido():
    """Agregar nuevo contenido SST"""
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
            
            try:
                categoria_id_int = int(categoria_id)
            except (ValueError, TypeError):
                flash('❌ Categoría inválida', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            
            # Procesar archivo subido
            archivo_data = None
            file = request.files.get('archivo_local')
            
            if file and file.filename != '':
                if allowed_file(file.filename):
                    archivo_data = guardar_archivo_en_bd(file)
                    
                    if not archivo_data:
                        flash('❌ Error al procesar el archivo', 'error')
                        return render_template('sst/agregar_contenido.html', categorias=categorias)
                    
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
                archivo_data = None
                video_url = None
            
            if validation_error:
                flash(f'❌ {validation_error}', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            
            # Limpiar valores
            video_url = video_url if video_url else None
            archivo_url = archivo_url if archivo_url else None
            descripcion = descripcion if descripcion else None
            tags = tags if tags else None
            
            # Insertar en la base de datos
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

@app.route('/sst/contenido/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@requiere_permiso('gestionar_contenido_sst')
def sst_editar_contenido(id):
    """Editar contenido SST existente"""
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
@requiere_permiso('gestionar_contenido_sst')
def sst_eliminar_contenido(id):
    """Eliminar contenido SST"""
    try:
        ejecutar_consulta("DELETE FROM sst_contenido WHERE id = %s", (id,), commit=True)
        flash('✅ Contenido eliminado correctamente', 'success')
    except Exception as e:
        flash(f'Error al eliminar contenido SST: {str(e)}', 'error')
        logger.error(f"❌ Error en sst_eliminar_contenido: {e}")
    
    return redirect(url_for('sst_contenido'))

@app.route('/sst/archivo/<int:id>')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
@requiere_permiso('acceder_sst')
def sst_descargar_archivo(id):
    """Descargar archivo desde la base de datos"""
    try:
        archivo = obtener_archivo_desde_bd(id)
        
        if not archivo:
            flash('Archivo no encontrado', 'error')
            return redirect(url_for('sst_contenido'))
        
        if not archivo.get('data'):
            flash('El archivo está vacío', 'error')
            return redirect(url_for('sst_contenido'))
        
        file_data = BytesIO(archivo['data'])
        
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
@requiere_permiso('acceder_sst')
def sst_descargar_archivo_forzado(id):
    """Descargar archivo forzadamente"""
    try:
        archivo = obtener_archivo_desde_bd(id)
        
        if not archivo or not archivo.get('data'):
            flash('Archivo no encontrado', 'error')
            return redirect(url_for('sst_contenido'))
        
        file_data = BytesIO(archivo['data'])
        
        return send_file(
            file_data,
            mimetype=archivo['tipo'],
            as_attachment=True,
            download_name=archivo['nombre']
        )
        
    except Exception as e:
        flash(f'Error al descargar el archivo: {str(e)}', 'error')
        logger.error(f"❌ Error en sst_descargar_archivo_forzado: {e}")
        return redirect(url_for('sst_contenido'))

@app.route('/sst/video/<int:id>')
@login_required
@retry_on_ssl_error(max_retries=2, delay=2)
@requiere_permiso('acceder_sst')
def sst_ver_video(id):
    """Ver detalles de un video"""
    video = None
    
    try:
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
@requiere_permiso('acceder_sst')
def sst_stream_video(id):
    """Stream de video desde la base de datos"""
    try:
        archivo = obtener_archivo_desde_bd(id)
        
        if not archivo or not archivo.get('data'):
            return Response('Video no encontrado', status=404)
        
        if not archivo['tipo'].startswith('video/'):
            return Response('El archivo no es un video', status=400)
        
        file_data = BytesIO(archivo['data'])
        
        return send_file(
            file_data,
            mimetype=archivo['tipo'],
            as_attachment=False
        )
        
    except Exception as e:
        logger.error(f"❌ Error en sst_stream_video: {e}")
        return Response('Error interno del servidor', status=500)

# ===== API PARA PROBLEMAS =====
@app.route('/api/problemas/<categoria>')
@login_required
@requiere_permiso('acceder_soporte')
def obtener_problemas(categoria):
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

# ===== RUTAS PARA SERVIR ARCHIVOS ESTÁTICOS =====
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Servir archivos estáticos"""
    return send_from_directory('static', filename)

# ===== INICIALIZACIÓN =====
if __name__ == '__main__':
    with app.app_context():
        print("🚀 Iniciando la aplicación Flask...")
        print("📊 Creando tablas de la base de datos...")
        crear_tablas()
        print("✅ Tablas creadas correctamente")
        print("🎨 Configurando categorías SST...")
        verificar_y_crear_categorias_sst()
        print("✅ Configuración completada")
        print(f"👤 Usuarios en el sistema: ")
        try:
            resultado = ejecutar_consulta("SELECT COUNT(*) FROM usuarios", fetch=True)
            if resultado:
                print(f"   - Total de usuarios: {resultado[0][0]}")
        except:
            print("   - No se pudo contar usuarios")
    
    print("\n🌐 Servidor iniciado en: http://localhost:5000")
    print("📁 Directorio de uploads: static/uploads/sst")
    print("🔐 Sistema de autenticación activado")
    print("🎭 Templates base por rol: Admin, SST, Soporte")
    app.run(host='0.0.0.0', port=5000, debug=True)
