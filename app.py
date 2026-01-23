from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from database import crear_conexion, crear_tablas, verificar_y_crear_categorias_sst, obtener_categorias_sst, obtener_contenido_sst, ejecutar_consulta, guardar_archivo_en_bd, insertar_contenido_con_archivo, obtener_archivo_desde_bd
from config import Config
from werkzeug.security import check_password_hash, generate_password_hash
import psycopg2
import json
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import mimetypes
from io import BytesIO
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== CONFIGURACIÓN DE LA APLICACIÓN =====
app = Flask(__name__)
app.config.from_object(Config)

# ===== CONFIGURACIÓN PARA SUBIDA DE ARCHIVOS SST =====
app.config['UPLOAD_FOLDER_SST'] = 'static/uploads/sst'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {
    'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
    'jpg', 'jpeg', 'png', 'gif', 'mp4', 'avi', 'mov', 'mkv', 'webm'
}

upload_path = app.config['UPLOAD_FOLDER_SST']
os.makedirs(upload_path, exist_ok=True)

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
            if current_user.rol == 'admin':
                return True
            if hasattr(current_user, 'permisos'):
                return current_user.permisos.get(permiso, False)
        return False
    
    return dict(tiene_permiso=tiene_permiso)

# ===== FILTROS TEMPLATE =====
@app.template_filter('format_date')
def format_date_filter(date_value, format='%d/%m/%Y'):
    if date_value is None:
        return 'Sin fecha'
    try:
        return date_value.strftime(format)
    except:
        return 'Fecha inválida'

# ===== MODELO DE USUARIO =====
class User(UserMixin):
    def __init__(self, id, usuario, rol, modulo_principal, permisos=None):
        self.id = id
        self.usuario = usuario
        self.rol = rol
        self.modulo_principal = modulo_principal
        self.permisos = permisos or {}
        
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
                'gestionar_contenido_sst': False
            }

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
            permisos = {}
            if user_data[5]:
                try:
                    permisos = json.loads(user_data[5])
                except:
                    permisos = {}
            
            return User(
                user_data[0], 
                user_data[1], 
                user_data[3],
                user_data[4] if user_data[4] else 'soporte',
                permisos
            )
    except Exception as e:
        logger.error(f"Error en load_user: {e}")
    return None

# ===== FUNCIÓN DE REDIRECCIÓN =====
def redirect_a_modulo_principal():
    if current_user.is_authenticated:
        if current_user.rol == 'admin':
            return redirect(url_for('index'))
        elif current_user.rol == 'sst':
            return redirect(url_for('sst_dashboard'))
        elif current_user.rol == 'soporte':
            return redirect(url_for('index'))
    return redirect(url_for('login'))

# ===== RUTAS DE AUTENTICACIÓN =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_a_modulo_principal()
    
    if request.method == 'POST':
        usuario = request.form.get('usuario', '')
        password = request.form.get('password', '')
        
        try:
            resultado = ejecutar_consulta(
                "SELECT * FROM usuarios WHERE usuario = %s", 
                (usuario,), 
                fetch=True
            )
            
            if resultado and resultado[0] and resultado[0][2]:
                user_data = resultado[0]
                
                if check_password_hash(user_data[2], password):
                    permisos = {}
                    if user_data[5]:
                        try:
                            permisos = json.loads(user_data[5])
                        except:
                            permisos = {}
                    
                    user = User(
                        user_data[0], 
                        user_data[1], 
                        user_data[3],
                        user_data[4] if user_data[4] else 'soporte',
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

# ===== RUTAS DE SOPORTE =====
@app.route('/')
@login_required
def index():
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
    
    return render_template('index.html', fichas=fichas)

@app.route('/agregar', methods=['GET', 'POST'])
@login_required
def agregar_ficha():
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
    
    return render_template('editar_ficha.html', ficha=ficha)

@app.route('/eliminar/<int:id>')
@login_required
def eliminar_ficha(id):
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
    
    return render_template('buscar.html', fichas=fichas, query=query, categoria=categoria)

@app.route('/ficha/<int:id>')
@login_required
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
    
    return render_template('ver_ficha.html', ficha=ficha)

# ===== RUTAS DE ADMIN =====
@app.route('/usuarios')
@login_required
def gestion_usuarios():
    if not current_user.puede('gestion_usuarios'):
        flash('No tienes permisos para acceder a esta página', 'error')
        return redirect_a_modulo_principal()
    
    usuarios = []
    
    try:
        resultado = ejecutar_consulta("SELECT * FROM usuarios ORDER BY fecha_creacion DESC", fetch=True)
        
        for usuario in resultado or []:
            usuario_dict = {
                'id': usuario[0],
                'usuario': usuario[1],
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
            password = request.form.get('password', '')
            rol = request.form['rol']
            modulo_principal = request.form.get('modulo_principal', 'soporte')
            
            permisos = {
                'ver_fichas': 'ver_fichas' in request.form,
                'agregar_fichas': 'agregar_fichas' in request.form,
                'editar_fichas': 'editar_fichas' in request.form,
                'eliminar_fichas': 'eliminar_fichas' in request.form,
                'acceder_sst': 'acceder_sst' in request.form,
                'gestionar_contenido_sst': 'gestionar_contenido_sst' in request.form,
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
        modulo_principal = request.form.get('modulo_principal', 'soporte')
        
        if not usuario or not password:
            flash('Usuario y contraseña son obligatorios', 'error')
            return render_template('agregar_usuario.html')
        
        permisos = {
            'ver_fichas': 'ver_fichas' in request.form,
            'agregar_fichas': 'agregar_fichas' in request.form,
            'editar_fichas': 'editar_fichas' in request.form,
            'eliminar_fichas': 'eliminar_fichas' in request.form,
            'acceder_sst': 'acceder_sst' in request.form,
            'gestionar_contenido_sst': 'gestionar_contenido_sst' in request.form,
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
        {'id': 1, 'titulo': '¿Como consultamos clientes?', 'categoria': 'Softv', 'imagenes': ['softv/softv1.png', 'softv/softv2.png', 'softv/softv3.png', 'softv/softv4.png'], 'descripcion': 'Busqueda del cliente paso a paso'},
        {'id': 2, 'titulo': '¿Como vemos las facturas del usuario?', 'categoria': 'Softv', 'imagenes': ['softv/softv5.png', 'softv/softv6.png', 'softv/softv7.png', 'softv/softv8.png'], 'descripcion': 'Consultar historial de pagos del usuario'},
        {'id': 3, 'titulo': '¿Como consultamos las ordenes de servicio de los usuarios?', 'categoria': 'Softv', 'imagenes': ['softv/softv9.png', 'softv/softv10.png', 'softv/softv11.png', 'softv/softv12.png'], 'descripcion': 'Consultar historial de ordenes de servicio del usuario'},
        {'id': 4, 'titulo': '¿Como consultamos reportes de fallas de los usuarios?', 'categoria': 'Softv', 'imagenes': ['softv/softv13.png', 'softv/softv14.png', 'softv/softv15.png', 'softv/softv16.png'], 'descripcion': 'Consultar historial de reportes de falla del usuario'},
        {'id': 5, 'titulo': '¿Como creamos un reporte de falla?', 'categoria': 'Softv', 'imagenes': ['softv/softv15.png', 'softv/softv16.png', 'softv/softv17.png', 'softv/softv19.png', 'softv/softv21.png', 'softv/softv22.png'], 'descripcion': 'Crear un reporte de falla'},
        {'id': 6, 'titulo': '¿Como creamos una orden de servicio?', 'categoria': 'Softv', 'imagenes': ['softv/softv23.png', 'softv/softv24.png', 'softv/softv26.png', 'softv/softv27.png', 'softv/softv28.png'], 'descripcion': 'Crear una orden de servicio'},
        {'id': 7, 'titulo': '¿Como borramos un reporte de falla en caso necesario?', 'categoria': 'Softv', 'imagenes': ['softv/softv29.png', 'softv/softv29.png', 'softv/softv29.png'], 'descripcion': 'Como eliminar un reporte de falla'},
        {'id': 8, 'titulo': '¿Como ingresamos un nuevo cliente?', 'categoria': 'Softv', 'imagenes': ['softv/softv30.png', 'softv/softv31.png', 'softv/softv32.png', 'softv/softv33.png', 'softv/softv32.png'], 'descripcion': 'Crear un nuevo cliente'},
        {'id': 9, 'titulo': '¿Como buscar un usuario?', 'categoria': 'Vortex', 'imagenes': ['vortex/vortex1.png', 'vortex/vortex2.png', 'vortex/vortex3.png'], 'descripcion': 'Buscar a un usuario'},
        {'id': 10, 'titulo': '¿Como validar puertos en uso y la MAC del equipo?', 'categoria': 'Vortex', 'imagenes': ['vortex/vortex4.png', 'vortex/vortex5.png'], 'descripcion': 'Como validar si el usuario esta haciendo uso de los puertos o el dispositivo no da MAC'},
        {'id': 11, 'titulo': '¿Como validar si el usuario esta teniendo consumo del servicio?', 'categoria': 'Vortex', 'imagenes': ['vortex/vortex7.png'], 'descripcion': 'Como validar el consumo del usuario'},
        {'id': 12, 'titulo': '¿Como cambiar la VLAN?', 'categoria': 'Vortex', 'imagenes': ['vortex/vortex8.png', 'vortex/vortex9.png'], 'descripcion': 'Como cambiar la VLAN acorde a la zona'},
        {'id': 13, 'titulo': '¿Como realizar un resync config?', 'categoria': 'Vortex', 'imagenes': ['vortex/vortex10.png', 'vortex/vortex11.png'], 'descripcion': 'Como realizar un resync config'},
        {'id': 14, 'titulo': '¿Como realizar un reboot?', 'categoria': 'Vortex', 'imagenes': ['vortex/vortex12.png', 'vortex/vortex13.png'], 'descripcion': 'Como realizar un reebot'},
        {'id': 15, 'titulo': '¿Como identificar si el servicio de internet y TV estan activados?', 'categoria': 'Vortex', 'imagenes': ['vortex/vortex14.png'], 'descripcion': 'Validar si el servicio esta activo'}
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
                        '*Requisitos y tiempos iguales* a afiliación general'
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
                        '*Contrato* se envía y recibe por el mismo medio'
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
        
        filtros = {
            'query': request.args.get('q', ''),
            'categoria': request.args.get('categoria', ''),
            'tipo': request.args.get('tipo', '')
        }
        
        contenido_data = obtener_contenido_sst(filtros)
        
        for item in contenido_data:
            tags_value = item[12]
            tags_str = str(tags_value) if tags_value is not None else ''
            
            contenido.append({
                'id': item[0],
                'titulo': item[1],
                'descripcion': item[2],
                'tipo': item[3],
                'archivo_url': item[4],
                'tiene_archivo': item[5] is not None,
                'archivo_nombre': item[6],
                'video_url': item[9],
                'categoria_id': item[10],
                'es_obligatorio': item[11],
                'tags': tags_str,
                'fecha_publicacion': item[13],
                'categoria_nombre': item[15],
                'categoria_color': item[16]
            })
                
    except Exception as e:
        flash('Error al cargar el contenido SST', 'error')
        logger.error(f"Error en sst_contenido: {e}")
    
    return render_template('sst/contenido.html', contenido=contenido, categorias=categorias)

# ===== API =====
@app.route('/api/problemas/<categoria>')
@login_required
def obtener_problemas(categoria):
    problemas_por_categoria = {
        'TV': ['No hay señal en el televisor', 'Imagen pixelada o con interferencias', 'Sin sonido en algunos canales', 'Problemas con la guía de programación', 'Otro problema con TV'],
        'Internet': ['Internet lento o intermitente', 'Sin conexión a internet', 'Problemas con WiFi', 'No puedo conectarme a sitios específicos', 'Velocidad inferior a la contratada', 'Problemas con el módem/router', 'Otro problema con Internet'],
        'Equipo': ['Equipo no enciende', 'Problemas con puertos HDMI/USB', 'Dispositivo no da MAC', 'Problemas niveles opticos', 'Otro problema con Equipo']
    }
    return jsonify(problemas_por_categoria.get(categoria, []))

# ===== INICIALIZACIÓN =====
if __name__ == '__main__':
    with app.app_context():
        print("🚀 Iniciando la aplicación Flask...")
        crear_tablas()
        verificar_y_crear_categorias_sst()
        print("✅ Aplicación lista")
    app.run(host='0.0.0.0', port=5000, debug=True)
