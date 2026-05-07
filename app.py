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
                    is_ssl_error = any(keyword in error_str for keyword in ['ssl', 'connection', 'closed'])
                    
                    if is_ssl_error and attempt < max_retries - 1:
                        logger.warning(f"⚠️ Error SSL en {func.__name__} (intento {attempt + 1}), reintentando...")
                        time.sleep(delay * (attempt + 1))
                        continue
                    else:
                        logger.error(f"❌ Error en {func.__name__}: {e}")
                        raise
            return None
        return wrapper
    return decorator

# ===== CONFIGURACIÓN DE LA APLICACIÓN =====
app = Flask(__name__)
app.config.from_object(Config)

# ===== CONFIGURACIÓN PARA SUBIDA DE ARCHIVOS SST =====
app.config['UPLOAD_FOLDER_SST'] = 'static/uploads/sst'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {
    'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
    'jpg', 'jpeg', 'png', 'gif', 'mp4', 'avi', 'mov', 'mkv', 'webm'
}

upload_path = app.config['UPLOAD_FOLDER_SST']
os.makedirs(upload_path, exist_ok=True)
print(f"📁 Directorio de uploads: {upload_path}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generar_nombre_seguro(filename):
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
            if modulo == 'rh' and current_user.rol in ['admin', 'rh']:
                return True
        return False
    
    def puede_gestionar(modulo):
        if current_user.is_authenticated:
            if current_user.rol == 'admin':
                return True
            if modulo == 'rh' and current_user.rol == 'rh':
                return True
            if modulo == 'sst' and current_user.rol == 'sst':
                return True
            if modulo == 'soporte' and current_user.rol == 'soporte':
                return True
        return False
    
    def obtener_modulo_principal():
        if current_user.is_authenticated:
            return getattr(current_user, 'modulo_principal', 'soporte')
        return 'soporte'
    
    def obtener_rol_display():
        if current_user.is_authenticated:
            rol = current_user.rol
            display_map = {
                'admin': 'Administrador',
                'sst': 'SST',
                'soporte': 'Soporte Técnico',
                'rh': 'Recursos Humanos'
            }
            return display_map.get(rol, rol.capitalize())
        return ''
    
    return dict(
        tiene_permiso=tiene_permiso,
        puede_acceder_modulo=puede_acceder_modulo,
        puede_gestionar=puede_gestionar,
        obtener_modulo_principal=obtener_modulo_principal,
        obtener_rol_display=obtener_rol_display
    )

# ===== FILTROS TEMPLATE =====
@app.template_filter('format_date')
def format_date_filter(date_value, format='%d/%m/%Y'):
    if date_value is None:
        return 'Sin fecha'
    try:
        if hasattr(date_value, 'strftime'):
            return date_value.strftime(format)
        if isinstance(date_value, str):
            date_str = date_value.split('.')[0] if '.' in date_value else date_value
            formats_to_try = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y']
            for fmt in formats_to_try:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime(format)
                except ValueError:
                    continue
            return date_str[:10] if len(date_str) >= 10 else date_str
        return str(date_value)
    except Exception as e:
        logger.error(f"Error en format_date_filter: {e}")
        return 'Fecha inválida'

@app.template_filter('safe_tags')
def safe_tags_filter(tags_value):
    if tags_value is None:
        return []
    if isinstance(tags_value, str):
        return [tag.strip() for tag in tags_value.split(',') if tag.strip()]
    return []

@app.template_filter('is_video_url')
def is_video_url_filter(url):
    if not url:
        return False
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
    return any(url.lower().endswith(ext) for ext in video_extensions)

@app.template_filter('file_extension')
def file_extension_filter(filename):
    if not filename:
        return ''
    return os.path.splitext(filename)[1].lower().replace('.', '')

@app.template_filter('format_currency')
def format_currency(value):
    if value is None:
        return '$0'
    try:
        return f'${float(value):,.0f}'.replace(',', '.')
    except:
        return f'${value}'

# ===== MODELO DE USUARIO =====
class User(UserMixin):
    def __init__(self, id, usuario, rol, modulo_principal, permisos=None):
        self.id = id
        self.usuario = usuario
        self.rol_original = rol
        self.rol = self._normalizar_rol(rol)
        self.modulo_principal = modulo_principal if modulo_principal else 'soporte'
        self.redireccionar_sst = False
        self.permisos = self._obtener_permisos_base()
        if permisos:
            self.permisos.update(permisos)

    def _normalizar_rol(self, rol):
        if not rol:
            return 'soporte'
        rol_str = str(rol).strip().lower()
        if rol_str in ['admin', 'administrador', 'administradora']:
            return 'admin'
        elif rol_str in ['sst', 'seguridad', 'salud']:
            return 'sst'
        elif rol_str in ['soporte', 'tecnico', 'técnico']:
            return 'soporte'
        elif rol_str in ['rh', 'recursos', 'recursos humanos', 'talento humano']:
            return 'rh'
        return 'soporte'

    def _obtener_permisos_base(self):
        permisos = {'cambiar_password': True}
        
        if self.rol == 'admin':
            permisos.update({
                'ver_rh': True, 'gestionar_rh': True,
                'ver_empleados': True, 'gestionar_empleados': True,
                'ver_contratos': True, 'gestionar_contratos': True,
                'ver_nomina': True, 'gestionar_nomina': True,
                'ver_capacitaciones': True, 'gestionar_capacitaciones': True,
                'ver_evaluaciones': True, 'gestionar_evaluaciones': True,
                'ver_ascensos': True, 'gestionar_ascensos': True,
                'ver_sanciones': True, 'gestionar_sanciones': True,
                'ver_reportes_rh': True,
                'ver_sst': True, 'gestionar_sst': True,
                'ver_soporte': True, 'gestionar_soporte': True,
                'gestion_usuarios': True, 'administrar_sistema': True,
                'acceder_sst': True, 'acceder_soporte': True, 'acceder_rh': True,
                'gestionar_plan_anual': True, 'agregar_evidencias': True
            })
        elif self.rol == 'rh':
            permisos.update({
                'ver_rh': True, 'gestionar_rh': True,
                'ver_empleados': True, 'gestionar_empleados': True,
                'ver_contratos': True, 'gestionar_contratos': True,
                'ver_nomina': True, 'gestionar_nomina': True,
                'ver_capacitaciones': True, 'gestionar_capacitaciones': True,
                'ver_evaluaciones': True, 'gestionar_evaluaciones': True,
                'ver_ascensos': True, 'gestionar_ascensos': True,
                'ver_sanciones': True, 'gestionar_sanciones': True,
                'ver_reportes_rh': True, 'acceder_rh': True
            })
        elif self.rol == 'sst':
            permisos.update({
                'ver_sst': True, 'gestionar_sst': True,
                'ver_contenido_sst': True, 'agregar_contenido_sst': True,
                'editar_contenido_sst': True, 'eliminar_contenido_sst': True,
                'ver_plan_anual': True, 'gestionar_plan_anual': True,
                'agregar_evidencias': True, 'acceder_sst': True
            })
        elif self.rol == 'soporte':
            permisos.update({
                'ver_soporte': True, 'gestionar_soporte': True,
                'ver_fichas': True, 'agregar_fichas': True,
                'editar_fichas': True, 'eliminar_fichas': True,
                'acceder_soporte': True
            })
        
        return permisos

    def puede(self, permiso):
        return self.permisos.get(permiso, False)
    
    def get_rol_display(self):
        display_map = {
            'admin': 'Administrador',
            'sst': 'SST (Salud y Seguridad)',
            'soporte': 'Soporte Técnico',
            'rh': 'Recursos Humanos'
        }
        return display_map.get(self.rol, self.rol.capitalize())

@login_manager.user_loader
def load_user(user_id):
    try:
        conn = crear_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, usuario, password, rol, modulo_principal, permisos, redireccionar_sst 
            FROM usuarios WHERE id = %s
        """, (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user_data:
            permisos = {}
            if user_data[5]:
                try:
                    permisos = json.loads(user_data[5])
                except:
                    permisos = {}
            
            user = User(user_data[0], user_data[1], user_data[3], user_data[4], permisos)
            user.redireccionar_sst = user_data[6] if len(user_data) > 6 else False
            return user
    except Exception as e:
        logger.error(f"Error al cargar usuario: {e}")
    return None

def redirect_a_modulo_principal():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    if hasattr(current_user, 'redireccionar_sst') and current_user.redireccionar_sst:
        return redirect(url_for('sst_dashboard'))
    
    if current_user.rol == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif current_user.rol == 'sst':
        return redirect(url_for('sst_dashboard'))
    elif current_user.rol == 'rh':
        return redirect(url_for('rh_dashboard'))
    else:
        return redirect(url_for('index'))

# ===== RUTAS DE AUTENTICACIÓN =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_a_modulo_principal()
    
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        password = request.form.get('password')
        
        try:
            conn = crear_conexion()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, usuario, password, rol, modulo_principal, permisos, redireccionar_sst 
                FROM usuarios WHERE usuario = %s
            """, (usuario,))
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user_data and user_data[2] and check_password_hash(user_data[2], password):
                permisos = {}
                if user_data[5]:
                    try:
                        permisos = json.loads(user_data[5])
                    except:
                        permisos = {}
                
                user = User(user_data[0], user_data[1], user_data[3], user_data[4], permisos)
                user.redireccionar_sst = user_data[6] if len(user_data) > 6 else False
                login_user(user)
                flash(f'¡Bienvenido {user.usuario}!', 'success')
                return redirect_a_modulo_principal()
            else:
                flash('Usuario o contraseña incorrectos', 'error')
        except Exception as e:
            flash(f'Error al iniciar sesión: {str(e)}', 'error')
    
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
                (current_user.id,), fetch=True
            )
            
            if resultado and resultado[0] and check_password_hash(resultado[0][0], password_actual):
                hash_nueva_password = generate_password_hash(nueva_password)
                ejecutar_consulta(
                    "UPDATE usuarios SET password = %s WHERE id = %s",
                    (hash_nueva_password, current_user.id), commit=True
                )
                flash('Contraseña actualizada correctamente', 'success')
                return redirect_a_modulo_principal()
            else:
                flash('La contraseña actual es incorrecta', 'error')
        except Exception as e:
            flash('Error al cambiar la contraseña', 'error')
    
    return render_template('cambiar_password.html')

# ===== RUTAS DE SOPORTE TÉCNICO =====
@app.route('/')
@login_required
def index():
    if current_user.rol == 'sst':
        return redirect(url_for('sst_dashboard'))
    if current_user.rol == 'rh':
        return redirect(url_for('rh_dashboard'))
    
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos para acceder al módulo de soporte', 'error')
        return redirect_a_modulo_principal()
    
    fichas = []
    try:
        resultado = ejecutar_consulta("SELECT * FROM fichas ORDER BY fecha_actualizacion DESC", fetch=True)
        for ficha in resultado or []:
            fichas.append({
                'id': ficha[0], 'categoria': ficha[1], 'problema': ficha[2],
                'descripcion': ficha[3], 'causas': ficha[4], 'solucion': ficha[5],
                'palabras_clave': ficha[6], 'fecha_creacion': ficha[7], 'fecha_actualizacion': ficha[8]
            })
    except Exception as e:
        flash('Error al cargar las fichas', 'error')
    
    return render_template('index.html', fichas=fichas)

@app.route('/agregar', methods=['GET', 'POST'])
@login_required
def agregar_ficha():
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    if not current_user.puede('agregar_fichas'):
        flash('No tienes permisos', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        categoria = request.form.get('categoria', '')
        problema = request.form.get('problema', '')
        descripcion = request.form.get('descripcion', '')
        causas = request.form.get('causas', '')
        solucion = request.form.get('solucion', '')
        palabras_clave = request.form.get('palabras_clave', '')
        
        if not categoria or not problema or not causas or not solucion:
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
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    if not current_user.puede('editar_fichas'):
        flash('No tienes permisos', 'error')
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
            
            causas_items = [item.strip() for item in causas.split('\n') if item.strip()]
            causas_str = '|'.join(causas_items)
            
            ejecutar_consulta('''
                UPDATE fichas SET categoria=%s, problema=%s, descripcion=%s, 
                causas=%s, solucion=%s, palabras_clave=%s WHERE id=%s
            ''', (categoria, problema, descripcion, causas_str, solucion, palabras_clave, id), commit=True)
            flash('Ficha actualizada correctamente', 'success')
            return redirect(url_for('index'))
        
        resultado = ejecutar_consulta("SELECT * FROM fichas WHERE id = %s", (id,), fetch=True)
        if resultado and resultado[0]:
            ficha_data = resultado[0]
            ficha = {
                'id': ficha_data[0], 'categoria': ficha_data[1], 'problema': ficha_data[2],
                'descripcion': ficha_data[3], 'causas': ficha_data[4], 'solucion': ficha_data[5],
                'palabras_clave': ficha_data[6]
            }
            if ficha and ficha['causas']:
                ficha['causas'] = ficha['causas'].replace('|', '\n')
    except Exception as e:
        flash('Error al cargar/editar la ficha', 'error')
    
    if not ficha:
        flash('Ficha no encontrada', 'error')
        return redirect(url_for('index'))
    
    return render_template('editar_ficha.html', ficha=ficha)

@app.route('/eliminar/<int:id>')
@login_required
def eliminar_ficha(id):
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    if not current_user.puede('eliminar_fichas'):
        flash('No tienes permisos', 'error')
        return redirect(url_for('index'))
    
    try:
        ejecutar_consulta("DELETE FROM fichas WHERE id = %s", (id,), commit=True)
        flash('Ficha eliminada correctamente', 'success')
    except Exception as e:
        flash('Error al eliminar la ficha', 'error')
    
    return redirect(url_for('index'))

@app.route('/buscar')
@login_required
def buscar():
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    if not current_user.puede('ver_fichas'):
        flash('No tienes permisos', 'error')
        return redirect(url_for('index'))
    
    query = request.args.get('q', '')
    categoria = request.args.get('categoria', '')
    fichas = []
    
    try:
        if categoria and query:
            resultado = ejecutar_consulta(
                "SELECT * FROM fichas WHERE categoria = %s AND (problema LIKE %s OR palabras_clave LIKE %s)",
                (categoria, f'%{query}%', f'%{query}%'), fetch=True
            )
        elif categoria:
            resultado = ejecutar_consulta("SELECT * FROM fichas WHERE categoria = %s", (categoria,), fetch=True)
        elif query:
            resultado = ejecutar_consulta(
                "SELECT * FROM fichas WHERE problema LIKE %s OR palabras_clave LIKE %s",
                (f'%{query}%', f'%{query}%'), fetch=True
            )
        else:
            resultado = ejecutar_consulta("SELECT * FROM fichas ORDER BY fecha_actualizacion DESC", fetch=True)
        
        for ficha in resultado or []:
            fichas.append({
                'id': ficha[0], 'categoria': ficha[1], 'problema': ficha[2],
                'descripcion': ficha[3], 'causas': ficha[4], 'solucion': ficha[5],
                'palabras_clave': ficha[6]
            })
    except Exception as e:
        flash('Error en la búsqueda', 'error')
    
    return render_template('buscar.html', fichas=fichas, query=query, categoria=categoria)

@app.route('/ficha/<int:id>')
@login_required
def ver_ficha(id):
    if not current_user.puede('acceder_soporte'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    if not current_user.puede('ver_fichas'):
        flash('No tienes permisos', 'error')
        return redirect(url_for('index'))
    
    ficha = None
    try:
        resultado = ejecutar_consulta("SELECT * FROM fichas WHERE id = %s", (id,), fetch=True)
        if resultado and resultado[0]:
            ficha_data = resultado[0]
            ficha = {
                'id': ficha_data[0], 'categoria': ficha_data[1], 'problema': ficha_data[2],
                'descripcion': ficha_data[3], 'causas': ficha_data[4], 'solucion': ficha_data[5],
                'palabras_clave': ficha_data[6]
            }
    except Exception as e:
        flash('Error al cargar la ficha', 'error')
    
    if not ficha:
        flash('Ficha no encontrada', 'error')
        return redirect(url_for('index'))
    
    return render_template('ver_ficha.html', ficha=ficha)

# ===== RUTAS DE GESTIÓN DE USUARIOS =====
@app.route('/usuarios')
@login_required
def gestion_usuarios():
    if not current_user.puede('gestion_usuarios'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    
    usuarios = []
    try:
        resultado = ejecutar_consulta("SELECT id, usuario, rol, modulo_principal, permisos, fecha_creacion FROM usuarios ORDER BY fecha_creacion DESC", fetch=True)
        for usuario in resultado or []:
            permisos_parsed = {}
            if usuario[4]:
                try:
                    permisos_parsed = json.loads(usuario[4])
                except:
                    pass
            usuarios.append({
                'id': usuario[0], 'usuario': usuario[1], 'rol': usuario[2],
                'modulo_principal': usuario[3] if usuario[3] else 'soporte',
                'permisos_parsed': permisos_parsed, 'fecha_creacion': usuario[5]
            })
    except Exception as e:
        flash('Error al cargar los usuarios', 'error')
    
    return render_template('gestion_usuarios.html', usuarios=usuarios)

@app.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if not current_user.puede('gestion_usuarios'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form.get('password', '')
        rol = request.form['rol']
        modulo_principal = request.form['modulo_principal']
        
        permisos = {
            'ver_fichas': 'ver_fichas' in request.form,
            'agregar_fichas': 'agregar_fichas' in request.form,
            'editar_fichas': 'editar_fichas' in request.form,
            'eliminar_fichas': 'eliminar_fichas' in request.form,
            'cambiar_password': True,
            'ver_rh': rol in ['admin', 'rh'],
            'gestionar_rh': rol in ['admin', 'rh'],
            'acceder_rh': rol in ['admin', 'rh']
        }
        
        permisos_json = json.dumps(permisos)
        
        if password:
            hash_password = generate_password_hash(password)
            ejecutar_consulta(
                "UPDATE usuarios SET usuario=%s, password=%s, rol=%s, modulo_principal=%s, permisos=%s WHERE id=%s",
                (usuario, hash_password, rol, modulo_principal, permisos_json, id), commit=True
            )
        else:
            ejecutar_consulta(
                "UPDATE usuarios SET usuario=%s, rol=%s, modulo_principal=%s, permisos=%s WHERE id=%s",
                (usuario, rol, modulo_principal, permisos_json, id), commit=True
            )
        flash('Usuario actualizado correctamente', 'success')
        return redirect(url_for('gestion_usuarios'))
    
    usuario_data = None
    try:
        resultado = ejecutar_consulta("SELECT * FROM usuarios WHERE id = %s", (id,), fetch=True)
        if resultado and resultado[0]:
            usuario = resultado[0]
            usuario_data = {
                'id': usuario[0], 'usuario': usuario[1], 'rol': usuario[3],
                'modulo_principal': usuario[4] if usuario[4] else 'soporte'
            }
    except Exception as e:
        flash('Error al cargar usuario', 'error')
    
    return render_template('editar_usuario.html', usuario=usuario_data)

@app.route('/agregar_usuario', methods=['GET', 'POST'])
@login_required
def agregar_usuario():
    if not current_user.puede('gestion_usuarios'):
        flash('No tienes permisos', 'error')
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
            'ver_fichas': rol in ['admin', 'soporte'],
            'agregar_fichas': rol in ['admin', 'soporte'],
            'editar_fichas': rol in ['admin', 'soporte'],
            'eliminar_fichas': rol in ['admin', 'soporte'],
            'cambiar_password': True,
            'ver_rh': rol in ['admin', 'rh'],
            'gestionar_rh': rol in ['admin', 'rh'],
            'acceder_rh': rol in ['admin', 'rh'],
            'ver_sst': rol in ['admin', 'sst'],
            'gestionar_sst': rol in ['admin', 'sst'],
            'acceder_sst': rol in ['admin', 'sst']
        }
        
        permisos_json = json.dumps(permisos)
        hash_password = generate_password_hash(password)
        
        try:
            ejecutar_consulta(
                "INSERT INTO usuarios (usuario, password, rol, modulo_principal, permisos) VALUES (%s, %s, %s, %s, %s)",
                (usuario, hash_password, rol, modulo_principal, permisos_json), commit=True
            )
            flash('Usuario agregado correctamente', 'success')
            return redirect(url_for('gestion_usuarios'))
        except psycopg2.IntegrityError:
            flash('El usuario ya existe', 'error')
        except Exception as e:
            flash('Error al agregar el usuario', 'error')
    
    return render_template('agregar_usuario.html')

@app.route('/eliminar_usuario/<int:id>')
@login_required
def eliminar_usuario(id):
    if not current_user.puede('gestion_usuarios'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    
    if id == current_user.id:
        flash('No puedes eliminar tu propio usuario', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    try:
        ejecutar_consulta("DELETE FROM usuarios WHERE id = %s", (id,), commit=True)
        flash('Usuario eliminado correctamente', 'success')
    except Exception as e:
        flash('Error al eliminar el usuario', 'error')
    
    return redirect(url_for('gestion_usuarios'))

# ===== RUTAS DE INFORMACIÓN =====
@app.route('/soluciones_visuales')
@login_required
def soluciones_visuales():
    soluciones = [
        {'id': 1, 'titulo': '¿Como consultamos clientes?', 'categoria': 'Softv',
         'imagenes': ['softv/softv1.png', 'softv/softv2.png', 'softv/softv3.png', 'softv/softv4.png'],
         'descripcion': 'Busqueda del cliente paso a paso'},
        {'id': 2, 'titulo': '¿Como vemos las facturas del usuario?', 'categoria': 'Softv',
         'imagenes': ['softv/softv5.png', 'softv/softv6.png', 'softv/softv7.png', 'softv/softv8.png'],
         'descripcion': 'Consultar historial de pagos del usuario'},
        {'id': 3, 'titulo': '¿Como consultamos las ordenes de servicio de los usuarios?', 'categoria': 'Softv',
         'imagenes': ['softv/softv9.png', 'softv/softv10.png', 'softv/softv11.png', 'softv/softv12.png'],
         'descripcion': 'Consultar historial de ordenes de servicio del usuario'},
        {'id': 4, 'titulo': '¿Como consultamos reportes de fallas de los usuarios?', 'categoria': 'Softv',
         'imagenes': ['softv/softv13.png', 'softv/softv14.png', 'softv/softv15.png', 'softv/softv16.png'],
         'descripcion': 'Consultar historial de reportes de falla del usuario'},
        {'id': 5, 'titulo': '¿Como creamos un reporte de falla?', 'categoria': 'Softv', 
         'imagenes': ['softv/softv15.png', 'softv/softv16.png', 'softv/softv17.png', 'softv/softv19.png', 'softv/softv21.png', 'softv/softv22.png'],
         'descripcion': 'Crear un reporte de falla'},
        {'id': 6, 'titulo': '¿Como creamos una orden de servicio?', 'categoria': 'Softv',
         'imagenes': ['softv/softv23.png', 'softv/softv24.png', 'softv/softv26.png', 'softv/softv27.png', 'softv/softv28.png'],
         'descripcion': 'Crear una orden de servicio'},
        {'id': 7, 'titulo': '¿Como borramos un reporte de falla en caso necesario?', 'categoria': 'Softv',
         'imagenes': ['softv/softv29.png', 'softv/softv29.png', 'softv/softv29.png'],
         'descripcion': 'Como eliminar un reporte de falla'},
        {'id': 8, 'titulo': '¿Como ingresamos un nuevo cliente?', 'categoria': 'Softv',
         'imagenes': ['softv/softv30.png', 'softv/softv31.png', 'softv/softv32.png', 'softv/softv33.png', 'softv/softv32.png'],
         'descripcion': 'Crear un nuevo cliente'},
        {'id': 9, 'titulo': '¿Como buscar un usuario?', 'categoria': 'Vortex',
         'imagenes': ['vortex/vortex1.png', 'vortex/vortex2.png', 'vortex/vortex3.png'],
         'descripcion': 'Buscar a un usuario'},
        {'id': 10, 'titulo': '¿Como validar puertos en uso y la MAC del equipo?', 'categoria': 'Vortex',
         'imagenes': ['vortex/vortex4.png', 'vortex/vortex5.png'],
         'descripcion': 'Como validar puertos en uso y MAC'},
        {'id': 11, 'titulo': '¿Como validar consumo del servicio?', 'categoria': 'Vortex',
         'imagenes': ['vortex/vortex7.png'], 'descripcion': 'Validar consumo del usuario'},
        {'id': 12, 'titulo': '¿Como cambiar la VLAN?', 'categoria': 'Vortex',
         'imagenes': ['vortex/vortex8.png', 'vortex/vortex9.png'], 'descripcion': 'Cambiar VLAN acorde a la zona'},
        {'id': 13, 'titulo': '¿Como realizar un resync config?', 'categoria': 'Vortex',
         'imagenes': ['vortex/vortex10.png', 'vortex/vortex11.png'], 'descripcion': 'Realizar resync config'},
        {'id': 14, 'titulo': '¿Como realizar un reboot?', 'categoria': 'Vortex',
         'imagenes': ['vortex/vortex12.png', 'vortex/vortex13.png'], 'descripcion': 'Realizar reboot'},
        {'id': 15, 'titulo': '¿Como identificar si el servicio está activado?', 'categoria': 'Vortex',
         'imagenes': ['vortex/vortex14.png'], 'descripcion': 'Validar si el servicio está activo'}
    ]
    return render_template('soluciones_visuales.html', soluciones=soluciones)

@app.route('/atencion_telefonica')
@login_required
def atencion_telefonica():
    return render_template('atencion_telefonica.html')

@app.route('/informacion-general')
@login_required
def informacion_general():
    return render_template('informacion_general.html')

# ===== RUTAS DE RECURSOS HUMANOS (RH) =====
@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.rol != 'admin':
        flash('No tienes permisos de administrador', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_dashboard.html')

@app.route('/rh')
@login_required
def rh_dashboard():
    if not current_user.puede('acceder_rh'):
        flash('No tienes permisos para acceder a Recursos Humanos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_dashboard.html')

@app.route('/rh/empleados')
@login_required
def rh_empleados():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_empleados.html')

@app.route('/rh/empleado/<int:id>')
@login_required
def rh_empleado_detalle(id):
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_empleado_detalle.html', empleado_id=id)

@app.route('/rh/empleado/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def rh_empleado_editar(id):
    if not current_user.puede('gestionar_rh'):
        flash('No tienes permisos para editar empleados', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_empleado_editar.html', empleado_id=id)

@app.route('/rh/empleado/nuevo', methods=['GET', 'POST'])
@login_required
def rh_empleado_nuevo():
    if not current_user.puede('gestionar_rh'):
        flash('No tienes permisos para crear empleados', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_empleado_nuevo.html')

@app.route('/rh/contratos')
@login_required
def rh_contratos():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_contratos.html')

@app.route('/rh/contrato/<int:id>')
@login_required
def rh_contrato_detalle(id):
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_contrato_detalle.html', contrato_id=id)

@app.route('/rh/contrato/nuevo', methods=['GET', 'POST'])
@login_required
def rh_contrato_nuevo():
    if not current_user.puede('gestionar_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_contrato_nuevo.html')

@app.route('/rh/capacitaciones')
@login_required
def rh_capacitaciones():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_capacitaciones.html')

@app.route('/rh/capacitacion/<int:id>')
@login_required
def rh_capacitacion_detalle(id):
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_capacitacion_detalle.html', capacitacion_id=id)

@app.route('/rh/capacitacion/nueva', methods=['GET', 'POST'])
@login_required
def rh_capacitacion_nueva():
    if not current_user.puede('gestionar_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_capacitacion_nueva.html')

@app.route('/rh/evaluaciones')
@login_required
def rh_evaluaciones():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_evaluaciones.html')

@app.route('/rh/evaluacion/nueva', methods=['GET', 'POST'])
@login_required
def rh_evaluacion_nueva():
    if not current_user.puede('gestionar_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_evaluacion_nueva.html')

@app.route('/rh/ascensos')
@login_required
def rh_ascensos():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_ascensos.html')

@app.route('/rh/ascenso/nuevo', methods=['GET', 'POST'])
@login_required
def rh_ascenso_nuevo():
    if not current_user.puede('gestionar_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_ascenso_nuevo.html')

@app.route('/rh/cargos')
@login_required
def rh_cargos():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_cargos.html')

@app.route('/rh/cargo/nuevo', methods=['GET', 'POST'])
@login_required
def rh_cargo_nuevo():
    if not current_user.puede('gestionar_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_cargo_nuevo.html')

@app.route('/rh/sanciones')
@login_required
def rh_sanciones():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_sanciones.html')

@app.route('/rh/sancion/nueva', methods=['GET', 'POST'])
@login_required
def rh_sancion_nueva():
    if not current_user.puede('gestionar_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_sancion_nueva.html')

@app.route('/rh/departamentos')
@login_required
def rh_departamentos():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_departamentos.html')

@app.route('/rh/organigrama')
@login_required
def rh_organigrama():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_organigrama.html')

@app.route('/rh/reportes')
@login_required
def rh_reportes():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_reportes.html')

@app.route('/rh/reporte/asistencia')
@login_required
def rh_reporte_asistencia():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_reporte_asistencia.html')

@app.route('/rh/reporte/nomina')
@login_required
def rh_reporte_nomina():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_reporte_nomina.html')

@app.route('/rh/reporte/rotacion')
@login_required
def rh_reporte_rotacion():
    if not current_user.puede('ver_rh'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('rh/rh_reporte_rotacion.html')

# ===== RUTAS SST =====
@app.route('/sst')
@login_required
def sst_dashboard():
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos para acceder al módulo de SST', 'error')
        return redirect_a_modulo_principal()
    return render_template('sst/dashboard.html')

@app.route('/sst/contenido')
@login_required
def sst_contenido():
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    
    contenido = []
    categorias = []
    
    try:
        categorias_data = obtener_categorias_sst()
        for cat in categorias_data:
            categorias.append({'id': cat[0], 'nombre': cat[1], 'color': cat[2]})
        
        filtros = {'query': request.args.get('q', ''), 'categoria': request.args.get('categoria', ''), 'tipo': request.args.get('tipo', '')}
        contenido_data = obtener_contenido_sst(filtros)
        
        for item in contenido_data:
            tags_str = str(item[12]) if item[12] is not None else ''
            contenido.append({
                'id': item[0], 'titulo': item[1], 'descripcion': item[2], 'tipo': item[3],
                'archivo_url': item[4], 'tiene_archivo': item[5] is not None, 'archivo_nombre': item[6],
                'archivo_tipo': item[7], 'archivo_tamano': item[8], 'video_url': item[9],
                'categoria_id': item[10], 'es_obligatorio': item[11], 'tags': tags_str,
                'fecha_publicacion': item[13], 'categoria_nombre': item[15], 'categoria_color': item[16]
            })
    except Exception as e:
        flash('Error al cargar el contenido SST', 'error')
    
    return render_template('sst/contenido.html', contenido=contenido, categorias=categorias)

@app.route('/sst/agregar', methods=['GET', 'POST'])
@login_required
def sst_agregar_contenido():
    if not current_user.puede('acceder_sst') or current_user.rol not in ['admin', 'sst']:
        flash('No tienes permisos', 'error')
        return redirect(url_for('sst_dashboard'))
    
    categorias = []
    try:
        categorias_data = obtener_categorias_sst()
        for cat in categorias_data:
            categorias.append({'id': cat[0], 'nombre': cat[1], 'color': cat[2]})
        
        if request.method == 'POST':
            titulo = request.form.get('titulo', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            tipo = request.form.get('tipo', '').strip()
            categoria_id = int(request.form.get('categoria_id', 0))
            es_obligatorio = 'es_obligatorio' in request.form
            tags = request.form.get('tags', '').strip()
            video_url = request.form.get('video_url', '').strip()
            archivo_url = request.form.get('archivo_url', '').strip()
            
            if not titulo or not tipo or not categoria_id:
                flash('Todos los campos obligatorios deben ser completados', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            
            archivo_data = None
            file = request.files.get('archivo_local')
            
            if file and file.filename and allowed_file(file.filename):
                archivo_data = guardar_archivo_en_bd(file)
                if archivo_data:
                    video_url = None
                    archivo_url = None
            
            if tipo == 'video' and not video_url and not archivo_data:
                flash('Para video debe proporcionar una URL o subir un archivo', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            elif tipo in ['documento', 'imagen'] and not archivo_url and not archivo_data:
                flash('Debe proporcionar una URL o subir un archivo', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            
            success = insertar_contenido_con_archivo(
                titulo=titulo, descripcion=descripcion or None, tipo=tipo,
                categoria_id=categoria_id, es_obligatorio=es_obligatorio,
                tags=tags or None, usuario_creador=current_user.id,
                archivo_data=archivo_data, video_url=video_url or None,
                archivo_url=archivo_url or None
            )
            
            if success:
                flash('Contenido agregado correctamente', 'success')
                return redirect(url_for('sst_contenido'))
            else:
                flash('Error al guardar', 'error')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return render_template('sst/agregar_contenido.html', categorias=categorias)

@app.route('/sst/archivo/<int:id>')
@login_required
def sst_descargar_archivo(id):
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    
    try:
        archivo = obtener_archivo_desde_bd(id)
        if not archivo or not archivo.get('data'):
            flash('Archivo no encontrado', 'error')
            return redirect(url_for('sst_contenido'))
        
        file_data = BytesIO(archivo['data'])
        return send_file(file_data, mimetype=archivo['tipo'], as_attachment=False, download_name=archivo['nombre'])
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('sst_contenido'))

@app.route('/sst/archivo/descargar/<int:id>')
@login_required
def sst_descargar_archivo_forzado(id):
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    
    try:
        archivo = obtener_archivo_desde_bd(id)
        if not archivo or not archivo.get('data'):
            flash('Archivo no encontrado', 'error')
            return redirect(url_for('sst_contenido'))
        
        file_data = BytesIO(archivo['data'])
        return send_file(file_data, mimetype=archivo['tipo'], as_attachment=True, download_name=archivo['nombre'])
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('sst_contenido'))

@app.route('/sst/contenido/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def sst_editar_contenido(id):
    if not current_user.puede('acceder_sst') or current_user.rol not in ['admin', 'sst']:
        flash('No tienes permisos', 'error')
        return redirect(url_for('sst_dashboard'))
    
    contenido = None
    categorias = []
    
    try:
        categorias_data = obtener_categorias_sst()
        for cat in categorias_data:
            categorias.append({'id': cat[0], 'nombre': cat[1], 'color': cat[2]})
        
        if request.method == 'POST':
            titulo = request.form.get('titulo', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            tipo = request.form.get('tipo', '').strip()
            categoria_id = int(request.form.get('categoria_id', 0))
            es_obligatorio = 'es_obligatorio' in request.form
            tags = request.form.get('tags', '').strip()
            video_url = request.form.get('video_url', '').strip() or None
            archivo_url = request.form.get('archivo_url', '').strip() or None
            
            if not titulo or not tipo or not categoria_id:
                flash('Todos los campos son obligatorios', 'error')
                return render_template('sst/editar_contenido.html', contenido=contenido, categorias=categorias)
            
            archivo_data = None
            file = request.files.get('archivo_local')
            if file and file.filename and allowed_file(file.filename):
                archivo_data = guardar_archivo_en_bd(file)
                if archivo_data:
                    video_url = None
                    archivo_url = None
            
            if archivo_data:
                ejecutar_consulta("""
                    UPDATE sst_contenido SET titulo=%s, descripcion=%s, tipo=%s, archivo_url=%s,
                    archivo_data=%s, archivo_nombre=%s, archivo_tipo=%s, archivo_tamano=%s,
                    video_url=%s, categoria_id=%s, es_obligatorio=%s, tags=%s, fecha_actualizacion=CURRENT_TIMESTAMP
                    WHERE id=%s
                """, (titulo, descripcion, tipo, archivo_url, psycopg2.Binary(archivo_data['data']),
                      archivo_data['nombre'], archivo_data['tipo'], archivo_data['tamano'],
                      video_url, categoria_id, es_obligatorio, tags, id), commit=True)
            else:
                ejecutar_consulta("""
                    UPDATE sst_contenido SET titulo=%s, descripcion=%s, tipo=%s, archivo_url=%s,
                    video_url=%s, categoria_id=%s, es_obligatorio=%s, tags=%s, fecha_actualizacion=CURRENT_TIMESTAMP
                    WHERE id=%s
                """, (titulo, descripcion, tipo, archivo_url, video_url, categoria_id, es_obligatorio, tags, id), commit=True)
            
            flash('Contenido actualizado correctamente', 'success')
            return redirect(url_for('sst_contenido'))
        
        resultado = ejecutar_consulta("""
            SELECT sc.*, cat.nombre as categoria_nombre FROM sst_contenido sc
            LEFT JOIN sst_categorias cat ON sc.categoria_id = cat.id WHERE sc.id = %s
        """, (id,), fetch=True)
        
        if resultado and resultado[0]:
            cd = resultado[0]
            contenido = {
                'id': cd[0], 'titulo': cd[1], 'descripcion': cd[2], 'tipo': cd[3],
                'archivo_url': cd[4], 'archivo_nombre': cd[6], 'video_url': cd[9],
                'categoria_id': cd[10], 'es_obligatorio': cd[11],
                'tags': str(cd[12]) if cd[12] is not None else '', 'categoria_nombre': cd[15]
            }
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return render_template('sst/editar_contenido.html', contenido=contenido, categorias=categorias)

@app.route('/sst/contenido/<int:id>/eliminar', methods=['POST'])
@login_required
def sst_eliminar_contenido(id):
    if not current_user.puede('acceder_sst') or current_user.rol not in ['admin', 'sst']:
        flash('No tienes permisos', 'error')
        return redirect(url_for('sst_contenido'))
    
    try:
        ejecutar_consulta("DELETE FROM sst_contenido WHERE id = %s", (id,), commit=True)
        flash('Contenido eliminado correctamente', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('sst_contenido'))

@app.route('/sst/video/<int:id>')
@login_required
def sst_ver_video(id):
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    
    video = None
    try:
        resultado = ejecutar_consulta("""
            SELECT sc.*, cat.nombre as categoria_nombre FROM sst_contenido sc
            LEFT JOIN sst_categorias cat ON sc.categoria_id = cat.id WHERE sc.id = %s
        """, (id,), fetch=True)
        
        if resultado and resultado[0]:
            cd = resultado[0]
            video = {
                'id': cd[0], 'titulo': cd[1], 'descripcion': cd[2], 'tipo': cd[3],
                'video_url': cd[9], 'tiene_archivo': cd[5] is not None,
                'archivo_nombre': cd[6], 'categoria_nombre': cd[15], 'fecha_publicacion': cd[13]
            }
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return render_template('sst/ver_video.html', video=video)

# ===== RUTAS DEL PLAN ANUAL SST =====
@app.route('/sst/plan-anual')
@login_required
def sst_plan_anual():
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('sst/plan_anual_dashboard.html')

@app.route('/sst/plan-anual/actividades')
@login_required
def sst_plan_anual_actividades():
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('sst/plan_anual_actividades.html')

@app.route('/sst/plan-anual/actividad/<int:id>')
@login_required
def sst_plan_anual_actividad_detalle(id):
    if not current_user.puede('acceder_sst'):
        flash('No tienes permisos', 'error')
        return redirect_a_modulo_principal()
    return render_template('sst/plan_anual_detalle.html', actividad_id=id)

# ===== INICIALIZACIÓN =====
if __name__ == '__main__':
    with app.app_context():
        print("🚀 Iniciando la aplicación Flask...")
        print("📊 Creando tablas en la base de datos...")
        crear_tablas()
        
        print("📊 Creando tablas de RRHH...")
        try:
            conn = crear_conexion()
            cursor = conn.cursor()
            
            # Tablas RH
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rh_departamentos (
                    id SERIAL PRIMARY KEY, nombre VARCHAR(100) NOT NULL, descripcion TEXT,
                    nivel INTEGER DEFAULT 3, jefe_id INTEGER, padre_id INTEGER,
                    presupuesto DECIMAL(12,2), ubicacion VARCHAR(200), activo BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rh_cargos (
                    id SERIAL PRIMARY KEY, nombre VARCHAR(100) NOT NULL, descripcion TEXT,
                    departamento VARCHAR(100), nivel VARCHAR(50), salario_base DECIMAL(12,2),
                    rango_min DECIMAL(12,2), rango_max DECIMAL(12,2), requisitos TEXT,
                    competencias TEXT, activo BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rh_empleados (
                    id SERIAL PRIMARY KEY, tipo_documento VARCHAR(10), documento VARCHAR(20) NOT NULL UNIQUE,
                    primer_nombre VARCHAR(50) NOT NULL, segundo_nombre VARCHAR(50),
                    primer_apellido VARCHAR(50) NOT NULL, segundo_apellido VARCHAR(50),
                    email VARCHAR(100) UNIQUE, telefono VARCHAR(20), celular VARCHAR(20),
                    direccion TEXT, fecha_nacimiento DATE, cargo VARCHAR(100), departamento VARCHAR(100),
                    cargo_id INTEGER, departamento_id INTEGER, fecha_ingreso DATE, fecha_retiro DATE,
                    estado VARCHAR(20) DEFAULT 'activo', salario DECIMAL(12,2), tipo_contrato VARCHAR(50),
                    jefe_inmediato VARCHAR(100), eps VARCHAR(100), arl VARCHAR(100), tipo_sangre VARCHAR(5),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rh_contratos (
                    id SERIAL PRIMARY KEY, empleado_id INTEGER NOT NULL REFERENCES rh_empleados(id) ON DELETE CASCADE,
                    tipo_contrato VARCHAR(50) NOT NULL, fecha_inicio DATE NOT NULL, fecha_fin DATE,
                    salario_contratado DECIMAL(12,2), archivo_pdf VARCHAR(255), observaciones TEXT,
                    estado VARCHAR(20) DEFAULT 'activo', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rh_procesos (
                    id SERIAL PRIMARY KEY, nombre VARCHAR(100) NOT NULL, descripcion TEXT,
                    tipo VARCHAR(50), responsable VARCHAR(100), prioridad VARCHAR(20) DEFAULT 'media',
                    estado VARCHAR(20) DEFAULT 'pendiente', fecha_inicio DATE, fecha_limite DATE,
                    avance INTEGER DEFAULT 0, observaciones TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rh_capacitaciones (
                    id SERIAL PRIMARY KEY, nombre VARCHAR(200) NOT NULL, descripcion TEXT,
                    tipo VARCHAR(50), instructor VARCHAR(100), fecha_inicio DATE, fecha_fin DATE,
                    duracion_horas INTEGER, costo DECIMAL(12,2), ubicacion VARCHAR(200),
                    estado VARCHAR(20) DEFAULT 'programada', observaciones TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rh_capacitacion_participantes (
                    id SERIAL PRIMARY KEY, capacitacion_id INTEGER NOT NULL REFERENCES rh_capacitaciones(id) ON DELETE CASCADE,
                    empleado_id INTEGER NOT NULL REFERENCES rh_empleados(id) ON DELETE CASCADE,
                    asistio BOOLEAN DEFAULT FALSE, nota DECIMAL(5,2), certificado_generado BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rh_evaluaciones (
                    id SERIAL PRIMARY KEY, empleado_id INTEGER NOT NULL REFERENCES rh_empleados(id) ON DELETE CASCADE,
                    evaluador_id INTEGER NOT NULL REFERENCES rh_empleados(id), periodo VARCHAR(20),
                    fecha_evaluacion DATE DEFAULT CURRENT_DATE, puntaje_cumplimiento INTEGER DEFAULT 0,
                    puntaje_trabajo_equipo INTEGER DEFAULT 0, puntaje_iniciativa INTEGER DEFAULT 0,
                    puntaje_calidad INTEGER DEFAULT 0, puntaje_total INTEGER DEFAULT 0,
                    observaciones TEXT, plan_mejora TEXT, estado VARCHAR(20) DEFAULT 'pendiente',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rh_ascensos (
                    id SERIAL PRIMARY KEY, empleado_id INTEGER NOT NULL REFERENCES rh_empleados(id) ON DELETE CASCADE,
                    cargo_anterior_id INTEGER, cargo_nuevo_id INTEGER, fecha_ascenso DATE,
                    salario_anterior DECIMAL(12,2), salario_nuevo DECIMAL(12,2), justificacion TEXT,
                    acta_ascenso VARCHAR(255), estado VARCHAR(20) DEFAULT 'propuesto', observaciones TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rh_sanciones (
                    id SERIAL PRIMARY KEY, empleado_id INTEGER NOT NULL REFERENCES rh_empleados(id) ON DELETE CASCADE,
                    tipo VARCHAR(30) NOT NULL, fecha DATE NOT NULL, motivo TEXT NOT NULL,
                    descripcion TEXT, duracion VARCHAR(100), documento VARCHAR(255), observaciones TEXT,
                    estado VARCHAR(20) DEFAULT 'vigente', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("SELECT COUNT(*) FROM rh_departamentos")
            if cursor.fetchone()[0] == 0:
                deptos = [('Dirección General', 1), ('Gerencia General', 2), ('Recursos Humanos', 3),
                         ('Seguridad y Salud en el Trabajo', 3), ('Operaciones', 3), ('Comercial', 3),
                         ('Tecnología', 3), ('Financiero', 3)]
                for d in deptos:
                    cursor.execute("INSERT INTO rh_departamentos (nombre, nivel) VALUES (%s, %s)", d)
                print("✅ Departamentos RH iniciales insertados")
            
            conn.commit()
            cursor.close()
            conn.close()
            print("✅ Tablas RH creadas")
        except Exception as e:
            print(f"⚠️ Error en tablas RH: {e}")
        
        print("📋 Verificando categorías SST...")
        try:
            verificar_y_crear_categorias_sst()
            print("✅ Categorías SST verificadas")
        except Exception as e:
            print(f"⚠️ Error: {e}")
    
    print("🌐 Aplicación lista en http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
