from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from database import crear_conexion, crear_tablas, verificar_y_crear_categorias_sst, obtener_categorias_sst, obtener_contenido_sst, ejecutar_consulta
from config import Config
from werkzeug.security import check_password_hash, generate_password_hash
import psycopg2
import json
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import urllib.parse

# Crear la instancia de Flask PRIMERO
app = Flask(__name__)
app.config.from_object(Config)

# ===== CONFIGURACIÓN PARA SUBIDA DE ARCHIVOS SST =====
app.config['UPLOAD_FOLDER_SST'] = 'static/uploads/sst'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB máximo
app.config['ALLOWED_EXTENSIONS'] = {
    'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
    'jpg', 'jpeg', 'png', 'gif', 'mp4', 'avi', 'mov', 'mkv'
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
    # Reemplazar espacios y caracteres especiales
    name = name.replace(' ', '_').replace('-', '_')
    return f"{timestamp}_{name}{ext}"

# Configurar Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Inyectar función de permisos a todos los templates
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

class User(UserMixin):
    def __init__(self, id, usuario, rol, permisos=None):
        self.id = id
        self.usuario = usuario
        self.rol = rol
        self.permisos = permisos or {
            'ver_fichas': True,
            'agregar_fichas': False,
            'editar_fichas': False,
            'eliminar_fichas': False,
            'cambiar_password': True
        }

    def puede(self, permiso):
        if self.rol == 'admin':
            return True
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
                'permisos': user_data[4]
            }
            
            # Cargar permisos desde JSON
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
                permisos
            )
    except Exception as e:
        print(f"Error en load_user: {e}")
    return None

# ===== RUTAS DE AUTENTICACIÓN =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
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
                    'permisos': user_data[4]
                }
                
                if check_password_hash(user_dict['password'], password):
                    permisos = {}
                    if user_dict.get('permisos'):
                        try:
                            permisos = json.loads(user_dict['permisos'])
                        except:
                            permisos = {}
                    
                    user = User(user_dict['id'], user_dict['usuario'], user_dict['rol'], permisos)
                    login_user(user)
                    flash('¡Inicio de sesión exitoso!', 'success')
                    return redirect(url_for('index'))
                else:
                    flash('Usuario o contraseña incorrectos', 'error')
            else:
                flash('Usuario no encontrado', 'error')
                
        except Exception as e:
            flash('Error de base de datos', 'error')
            print(f"Error en login: {e}")
    
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
                return redirect(url_for('index'))
            else:
                flash('La contraseña actual es incorrecta', 'error')
                    
        except Exception as e:
            flash('Error al cambiar la contraseña', 'error')
            print(f"Error en cambiar_password: {e}")
    
    return render_template('cambiar_password.html')

# ===== RUTAS PRINCIPALES =====
@app.route('/')
@login_required
def index():
    if not current_user.puede('ver_fichas'):
        flash('No tienes permisos para ver las fichas', 'error')
        return redirect(url_for('login'))
    
    fichas = []
    try:
        resultado = ejecutar_consulte(
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
        print(f"Error en index: {e}")
    
    return render_template('index.html', fichas=fichas, user=current_user)

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
        print(f"Error en editar_ficha: {e}")
    
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
        print(f"Error en eliminar_ficha: {e}")
    
    return redirect(url_for('index'))

@app.route('/buscar')
@login_required
def buscar():
    if not current_user.puede('ver_fichas'):
        flash('No tienes permisos para ver las fichas', 'error')
        return redirect(url_for('index'))
    
    query = request.args.get('q', '')
    categoria = request.args.get('categoria', '')
    
    fichas = []
    try:
        if categoria and query:
            resultado = ejecutar_consulte(
                "SELECT * FROM fichas WHERE categoria = %s AND (problema LIKE %s OR palabras_clave LIKE %s)",
                (categoria, f'%{query}%', f'%{query}%'),
                fetch=True
            )
        elif categoria:
            resultado = ejecutar_consulte(
                "SELECT * FROM fichas WHERE categoria = %s",
                (categoria,),
                fetch=True
            )
        elif query:
            resultado = ejecutar_consulte(
                "SELECT * FROM fichas WHERE problema LIKE %s OR palabras_clave LIKE %s",
                (f'%{query}%', f'%{query}%'),
                fetch=True
            )
        else:
            resultado = ejecutar_consulte(
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
        print(f"Error en buscar: {e}")
    
    return render_template('buscar.html', fichas=fichas, query=query, categoria=categoria)

@app.route('/ficha/<int:id>')
@login_required
def ver_ficha(id):
    if not current_user.puede('ver_fichas'):
        flash('No tienes permisos para ver las fichas', 'error')
        return redirect(url_for('index'))
    
    ficha = None
    try:
        resultado = ejecutar_consulte("SELECT * FROM fichas WHERE id = %s", (id,), fetch=True)
        
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
        print(f"Error en ver_ficha: {e}")
    
    if not ficha:
        flash('Ficha no encontrada', 'error')
        return redirect(url_for('index'))
    
    return render_template('ver_ficha.html', ficha=ficha)

# ===== RUTAS SST MEJORADAS =====

@app.route('/sst')
@login_required
def sst_dashboard():
    """Dashboard principal de SST"""
    return render_template('sst/dashboard.html')

@app.route('/sst/contenido')
@login_required
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
            'tipo': request.args.get('tipo', '')
        }
        
        # Obtener contenido
        contenido_data = obtener_contenido_sst(filtros)
        
        for item in contenido_data:
            contenido_dict = {
                'id': item[0],
                'titulo': item[1],
                'descripcion': item[2],
                'tipo': item[3],
                'archivo_url': item[4],
                'archivo_local': item[5],
                'video_url': item[6],
                'categoria_id': item[7],
                'es_obligatorio': item[8],
                'tags': item[9],
                'fecha_publicacion': item[10],
                'usuario_creador': item[11],
                'categoria_nombre': item[12],
                'categoria_color': item[13],
                'creador_nombre': item[14]
            }
            contenido.append(contenido_dict)
                
    except Exception as e:
        flash('Error al cargar el contenido SST', 'error')
        print(f"❌ Error en sst_contenido: {e}")
    
    return render_template('sst/contenido.html', contenido=contenido, categorias=categorias)

@app.route('/sst/agregar', methods=['GET', 'POST'])
@login_required
def sst_agregar_contenido():
    """Agregar nuevo contenido SST - VERSIÓN CORREGIDA"""
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
            
            # Procesar archivo subido
            archivo_local = None
            file = request.files.get('archivo_local')
            
            if file and file.filename != '':
                if allowed_file(file.filename):
                    # Generar nombre seguro y guardar archivo
                    filename = generar_nombre_seguro(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER_SST'], filename)
                    
                    # Asegurar que el directorio existe
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    
                    # Guardar archivo
                    file.save(file_path)
                    
                    # Verificar que el archivo se guardó
                    if os.path.exists(file_path):
                        archivo_local = filename
                        print(f"✅ Archivo guardado: {filename}")
                        
                        # SI SE SUBIÓ ARCHIVO LOCAL, LIMPIAR AMBAS URLs
                        video_url = None
                        archivo_url = None
                        print("📁 Archivo local detectado - Limpiando video_url y archivo_url")
                    else:
                        flash('❌ Error al guardar el archivo en el servidor', 'error')
                        return render_template('sst/agregar_contenido.html', categorias=categorias)
                else:
                    extensiones_permitidas = ', '.join(app.config['ALLOWED_EXTENSIONS'])
                    flash(f'❌ Tipo de archivo no permitido. Extensiones válidas: {extensiones_permitidas}', 'error')
                    return render_template('sst/agregar_contenido.html', categorias=categorias)
            
            # Validaciones específicas por tipo
            validation_error = None
            if tipo == 'video':
                if not video_url and not archivo_local:
                    validation_error = 'Para video debe proporcionar una URL de video o subir un archivo'
            elif tipo in ['documento', 'imagen']:
                if not archivo_url and not archivo_local:
                    validation_error = 'Debe proporcionar una URL o subir un archivo'
            elif tipo == 'enlace':
                if not archivo_url:
                    validation_error = 'Debe proporcionar una URL para enlaces'
                # Para enlaces, no permitir archivos locales
                archivo_local = None
                video_url = None
            
            if validation_error:
                flash(f'❌ {validation_error}', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            
            # Limpiar valores para la base de datos
            video_url = video_url if video_url else None
            archivo_url = archivo_url if archivo_url else None
            descripcion = descripcion if descripcion else None
            tags = tags if tags else None
            
            # Insertar en la base de datos
            try:
                ejecutar_consulta("""
                    INSERT INTO sst_contenido 
                    (titulo, descripcion, tipo, archivo_url, archivo_local, video_url, 
                     categoria_id, es_obligatorio, tags, usuario_creador)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    titulo,
                    descripcion,
                    tipo,
                    archivo_url,
                    archivo_local,  # <-- ESTE ES EL VALOR IMPORTANTE
                    video_url,
                    categoria_id_int,
                    es_obligatorio,
                    tags,
                    current_user.id
                ), commit=True)
                
                flash('✅ Contenido SST agregado correctamente', 'success')
                return redirect(url_for('sst_contenido'))
                
            except Exception as db_error:
                flash(f'❌ Error de base de datos: {str(db_error)}', 'error')
                return render_template('sst/agregar_contenido.html', categorias=categorias)
            
    except Exception as e:
        flash(f'❌ Error al agregar contenido SST: {str(e)}', 'error')
        print(f"❌ ERROR GENERAL EN SST_AGREGAR_CONTENIDO: {e}")
    
    return render_template('sst/agregar_contenido.html', categorias=categorias)

@app.route('/sst/contenido/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def sst_editar_contenido(id):
    """Editar contenido SST existente"""
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
            archivo_local = None
            file = request.files.get('archivo_local')
            if file and file.filename != '':
                if allowed_file(file.filename):
                    filename = generar_nombre_seguro(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER_SST'], filename)
                    file.save(file_path)
                    archivo_local = filename
                    
                    # Si se subió nuevo archivo, limpiar URLs
                    video_url = None
                    archivo_url = None
                else:
                    flash('Tipo de archivo no permitido', 'error')
                    return render_template('sst/editar_contenido.html', contenido=contenido, categorias=categorias)
            
            # Actualizar en base de datos
            if archivo_local:
                # Si se subió nuevo archivo, actualizar archivo_local
                ejecutar_consulta("""
                    UPDATE sst_contenido 
                    SET titulo=%s, descripcion=%s, tipo=%s, archivo_url=%s, 
                        archivo_local=%s, video_url=%s, categoria_id=%s, 
                        es_obligatorio=%s, tags=%s, fecha_actualizacion=CURRENT_TIMESTAMP
                    WHERE id=%s
                """, (titulo, descripcion, tipo, archivo_url, archivo_local, 
                      video_url, categoria_id, es_obligatorio, tags, id), commit=True)
            else:
                # Mantener el archivo_local existente
                ejecutar_consulte("""
                    UPDATE sst_contenido 
                    SET titulo=%s, descripcion=%s, tipo=%s, archivo_url=%s, 
                        video_url=%s, categoria_id=%s, es_obligatorio=%s, 
                        tags=%s, fecha_actualizacion=CURRENT_TIMESTAMP
                    WHERE id=%s
                """, (titulo, descripcion, tipo, archivo_url, video_url, 
                      categoria_id, es_obligatorio, tags, id), commit=True)
            
            flash('✅ Contenido actualizado correctamente', 'success')
            return redirect(url_for('sst_contenido'))
        
        # GET: Cargar datos del contenido
        resultado = ejecutar_consulte("""
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
                'archivo_local': contenido_data[5],
                'video_url': contenido_data[6],
                'categoria_id': contenido_data[7],
                'es_obligatorio': contenido_data[8],
                'tags': contenido_data[9],
                'fecha_publicacion': contenido_data[10],
                'usuario_creador': contenido_data[11],
                'categoria_nombre': contenido_data[12],
                'categoria_color': contenido_data[13],
                'creador_nombre': contenido_data[14]
            }
                
    except Exception as e:
        flash(f'Error al editar contenido SST: {str(e)}', 'error')
        print(f"❌ Error en sst_editar_contenido: {e}")
    
    if not contenido:
        flash('Contenido no encontrado', 'error')
        return redirect(url_for('sst_contenido'))
    
    return render_template('sst/editar_contenido.html', contenido=contenido, categorias=categorias)

@app.route('/sst/contenido/<int:id>/eliminar', methods=['POST'])
@login_required
def sst_eliminar_contenido(id):
    """Eliminar contenido SST"""
    if current_user.rol != 'admin':
        flash('No tienes permisos para eliminar contenido SST', 'error')
        return redirect(url_for('sst_dashboard'))
    
    try:
        # Primero obtener información del archivo para eliminarlo físicamente
        resultado = ejecutar_consulte(
            "SELECT archivo_local FROM sst_contenido WHERE id = %s", 
            (id,), 
            fetch=True
        )
        
        if resultado and resultado[0] and resultado[0][0]:
            # Eliminar archivo físico
            archivo_path = os.path.join(app.config['UPLOAD_FOLDER_SST'], resultado[0][0])
            if os.path.exists(archivo_path):
                os.remove(archivo_path)
                print(f"🗑️ Archivo eliminado: {resultado[0][0]}")
        
        # Eliminar de la base de datos
        ejecutar_consulte("DELETE FROM sst_contenido WHERE id = %s", (id,), commit=True)
        
        flash('✅ Contenido eliminado correctamente', 'success')
        
    except Exception as e:
        flash(f'Error al eliminar contenido SST: {str(e)}', 'error')
        print(f"❌ Error en sst_eliminar_contenido: {e}")
    
    return redirect(url_for('sst_contenido'))

@app.route('/sst/video/<int:id>')
@login_required
def sst_ver_video(id):
    """Ver video específico de SST"""
    video = None
    
    try:
        resultado = ejecutar_consulte("""
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
                'archivo_url': str(video_data[4]) if video_data[4] else None,
                'archivo_local': str(video_data[5]) if video_data[5] else None,
                'video_url': str(video_data[6]) if video_data[6] else None,
                'categoria_nombre': video_data[12],
                'categoria_color': video_data[13],
                'fecha_publicacion': video_data[10]
            }
                
    except Exception as e:
        flash('Error al cargar el contenido', 'error')
        print(f"❌ Error en sst_ver_video: {e}")
    
    if not video:
        flash('Contenido no encontrado', 'error')
        return redirect(url_for('sst_contenido'))
    
    return render_template('sst/ver_video.html', video=video)

@app.route('/sst/archivos/<filename>')
@login_required
def sst_servir_archivo(filename):
    """Servir archivos subidos localmente"""
    try:
        # Verificar seguridad del filename
        if '..' in filename or filename.startswith('/'):
            flash('Ruta de archivo inválida', 'error')
            return redirect(url_for('sst_contenido'))
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER_SST'], filename)
        
        if not os.path.isfile(file_path):
            flash(f'Archivo no encontrado: {filename}', 'error')
            return redirect(url_for('sst_contenido'))
        
        # Determinar el tipo MIME
        mime_types = {
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        
        # Obtener extensión del archivo
        _, ext = os.path.splitext(filename.lower())
        mimetype = mime_types.get(ext, 'application/octet-stream')
        
        return send_from_directory(
            app.config['UPLOAD_FOLDER_SST'], 
            filename, 
            as_attachment=False,
            mimetype=mimetype
        )
    
    except Exception as e:
        flash(f'Error al cargar el archivo: {str(e)}', 'error')
        print(f"❌ Error en sst_servir_archivo: {e}")
        return redirect(url_for('sst_contenido'))

# ===== RUTAS RESTANTES (se mantienen igual) =====
# [Las rutas de gestión de usuarios, información general, etc. se mantienen igual]

if __name__ == '__main__':
    with app.app_context():
        print("🚀 Iniciando la aplicación Flask...")
        crear_tablas()
    app.run(host='0.0.0.0', port=5000, debug=True)
