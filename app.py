from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from database import crear_conexion, crear_tablas
from config import Config
from werkzeug.security import check_password_hash, generate_password_hash
import mysql.connector
import json
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

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
    conexion = crear_conexion()
    if conexion:
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
            user_data = cursor.fetchone()
            if user_data:
                # Cargar permisos desde JSON
                permisos = {}
                if user_data.get('permisos'):
                    try:
                        permisos = json.loads(user_data['permisos'])
                    except:
                        permisos = {}
                
                return User(
                    user_data['id'], 
                    user_data['usuario'], 
                    user_data['rol'],
                    permisos
                )
        except mysql.connector.Error as e:
            print(f"Error: {e}")
        finally:
            cursor.close()
            conexion.close()
    return None

# Decorador personalizado para permisos
def permiso_requerido(permiso):
    def decorator(f):
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.puede(permiso):
                flash('No tienes permisos para acceder a esta página', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator

# Rutas de autenticación
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Si el usuario ya está autenticado, redirigir al index
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']
        
        conexion = crear_conexion()
        if conexion:
            try:
                cursor = conexion.cursor(dictionary=True)
                cursor.execute("SELECT * FROM usuarios WHERE usuario = %s", (usuario,))
                user_data = cursor.fetchone()
                
                if user_data and user_data['password'] and user_data['password'].strip():
                    if check_password_hash(user_data['password'], password):
                        # Cargar permisos desde JSON
                        permisos = {}
                        if user_data.get('permisos'):
                            try:
                                permisos = json.loads(user_data['permisos'])
                            except:
                                permisos = {}
                        
                        user = User(user_data['id'], user_data['usuario'], user_data['rol'], permisos)
                        login_user(user)
                        flash('¡Inicio de sesión exitoso!', 'success')
                        return redirect(url_for('index'))
                    else:
                        flash('Usuario o contraseña incorrectos', 'error')
                else:
                    flash('Usuario no encontrado', 'error')
                    
            except Exception as e:
                flash('Error de base de datos', 'error')
                print(f"Error: {e}")
            finally:
                cursor.close()
                conexion.close()
        else:
            flash('Error de conexión a la base de datos', 'error')
    
    return render_template('login.html')


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

# Agregar esta ruta en app.py
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
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '💯 **PLANES DE TV E INTERNET** 💯',
                        '400 megas + TV: $85.000',
                        '500 megas + TV: $95.000', 
                        '600 megas + TV: $105.000',
                        '',
                        '💯 **PLANES SOLO TV** 💯',
                        '10Mb + TV: $50.000',
                        '',
                        '🌐 **PLANES SOLO INTERNET** 🌐',
                        '400 megas: $75.000',
                        '500 megas: $85.000',
                        '600 megas: $95.000'
                    ]
                },
                {
                    'subtitulo': 'Planes Corporativos',
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '💯 **PLANES CORPORATIVOS** 💯',
                        '1Mb: $12.000',
                        '30Mb (mínimo): $360.000 + 19% IVA = $428.400',
                         '**Planes hogar:** se agrega 19% IVA',
                        '**Equipo:** robusto para configuraciones especiales'
                    ]
                },
                
                 {
                    'subtitulo': 'Planes Guamal y Sanmartin',  # NUEVA SUBSECCIÓN
                    'contenido_items': [
                        '🎯 *PLANES DE TV + INTERNET* 🎯',
                        'TV + 200MB: $65.000',
                        'TV + 300MB: $75.000', 
                        'TV + 400MB: $85.000',
                        '',
                        '📺 *PLAN SOLO TV* 📺',
                        'Solo TV: $50.000'
                    ]
                },
                 
                {
                    'subtitulo': 'Planes Acacías',
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '💯 **PLANES DE TV E INTERNET** 💯',
                        'TV + Internet 200MB: $85.000',
                        'TV + Internet 300MB: $95.000',
                        'TV + Internet 400MB: $105.000',
                        '',
                        '💯 **PLANES SOLO TV** 💯',
                        'Solo TV: $50.000',
                        '',
                        '🌐 **PLANES SOLO INTERNET** 🌐',
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
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**La afiliación no tiene costo**',
                        '**Instalación sin costo** en zona urbana (rural: $150.000)',
                        '',
                        '**Requisitos:**',
                        '• 1 Fotocopia de la cédula',
                        '• 1 Fotocopia del recibo de agua o luz',
                        '• Pago del primer mes por anticipado',
                        '• Servicio de TV para 2 televisores',
                        '',
                        '**Puntos adicionales de TV:**',
                        '• Cada punto: $20.000 (solo instalación)',
                        '• Mensualidad no cambia',
                        '• Solo para el mismo predio',
                        '',
                        '**Señal Digital:**',
                        '• Decodificador: $58.000 (único pago)',
                        '• Para TVs clásicos con señal analógica',
                        '',
                        '**Tiempo de instalación:** 2-4 días hábiles'
                    ]
                },
                {
                    'subtitulo': 'Afiliación San Joaquín',
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Costo de instalación:** $60.000',
                        '**Fibra incluida:** primeros 70 metros',
                        '**Costo metro adicional:** $1.700',
                        '',
                        '**Servicio de TV:** 1 televisor',
                        '**Puntos adicionales:** $35.000 c/u',
                        '**Requisitos y tiempos iguales**  a afiliación general'
                    ]
                },
                {
                    'subtitulo': 'Información Adicional',
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Para asesores solicitar:**',
                        '• Barrio',
                        '• Dirección exacta', 
                        '• Nombre del titular',
                        '• 2 números de teléfono',
                        '',
                        '**Sin cláusula de permanencia**',
                        '**Pago por adelantado** después de firmar contrato',
                        '**Contrato**  se envía y recibe por el mismo medio'
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
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Precio:** $35.000 adicionales al mes',
                        '**Incluye:**',
                        '• Acceso a Win Sports +',
                        '• 14 canales premium',
                        '• Y mucho más contenido deportivo',
                        '',
                        '**TV Box:** $100.000 (costo único)',
                        '**No necesario** si TV es Android (con Google Play Store)',
                        '**Cláusula:** 6 meses',
                        '**Requisito:** Tener plan de internet con nosotros'
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
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Lunes a Viernes:** 8:00 AM - 5:00 PM',
                        '**Sábados:** 8:00 AM - 12:00 PM'
                    ]
                },
                {
                    'subtitulo': 'Direcciones de Oficinas',
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Facatativá:** Cl 11 #7A-04, Diurba',
                        '**Bojacá:** Cr 6 #5-146, Barrio Centro',
                        '**Zipacón:** Crr 4 #5-57, Frente al parque',
                        '**Rosal:** Cr 8 #8-08, Local 3 Centro',
                        '**El Triunfo:** Crr 3 #2-40, Frente al coliseo',
                        '**Viotá:** Cl 20 #11-10, Frente a estación de policía',
                        '**Girardot:** Crr 10 #18-44, Barrio Centro / Frente a Bancamía',
                        '**Cachipay:** Crr 3 #3-36, Barrio Centro',
                        '**Sasaima:** Crr 2 #3-30, Barrio 3 Esquinas',
                        '**La Mesa:** Cl 8 #16-59, Barrio Santa Bárbara',
                        '**Anolaima:** Crr 7 #02-57, Barrio Centro',
                        '**Mesitas del Colegio:** Cl 10 #6-37, Barrio Centro',
                        '**Anapoima:** Cr 2 #7-32, Local 2 Centro',
                        '**Albán:** Cl 4 #2-04, Punto de Servientrega',
                        '**Madrid:** Cl 12 #3-64, Barrio Arrayane',
                        '**Guayabal de Síquima:** Cl 3 #5-28',
                        '**Tocaima:** Cl 4 #9-75',
                        '**San Joaquín:** Cr 4 N 4-55, Al lado del árbol de los aburridos',
                        '**Apulo:** Cl 14 #6-23, Local 102',
                        '**Villeta:** Cr 5 #3-43, Local 6 Torre 4 Conjunto Santa Cruz',
                        '**Acacías:** Cl 15 #22-40, Local 12, Edificio Dark Gym',
                        '**San Martín:** Cl 7 #5-34, Barrio Fundadores',
                        '**Guamal:** Cl 10 #4A-04, Barrio Las Villas',
                        '**Quipile:** Crr 2 #6-07'
                    ]
                },
                {
                    'subtitulo': 'Puntos Autorizados Facatativá',
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Bolos el Tunjo:** Cr 2 #6-105',
                        '**CLT Comunicaciones:** Cl 19 #1A-28 Sur, Prado de Cartagenita',
                        '**Portal de María:** Transversal 11 #5-04, Manzana 5 Casa 30 S.M.A.',
                        '**Papelería Expresate:** Cl 8 #10-05, Zambrano',
                        '**One Books:** Diagonal 5 Este #9E-02, Juan Pablo II',
                        '**Papelería Chico 1:** Cr 3 #5B-08 Este, Chico 1'
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
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Requisitos:**',
                        '• Acercarse a la oficina',
                        '• Carta indicando razón de cancelación',
                        '• Paz y salvo',
                        '• Equipos instalados (equipos y cargadores)'
                    ]
                },
                {
                    'subtitulo': 'Cambio de Titular',
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Requisitos:**',
                        '• Carta solicitando cambio, firmada por antiguo y nuevo titular',
                        '• Copia de cédula del nuevo titular',
                        '• Estar al día en los pagos'
                    ]
                },
                {
                    'subtitulo': 'Cambio de Plan',
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Procedimiento:**',
                        '• Acercarse a la oficina',
                        '• Carta solicitando cambio de plan',
                        '• Estar al día en pagos',
                        '• Cancelar por adelantado valor del nuevo plan',
                        '• Ideal realizarlo a finales de mes'
                    ]
                },
                {
                    'subtitulo': 'Traslado de Domicilio',
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Costo:** $20.000',
                        '**Puntos adicionales:** $10.000 c/u (movimiento)',
                        '**Tiempo:** 2-3 días hábiles',
                        '**Requisito:** Llevar equipos a la nueva residencia'
                    ]
                },
                {
                    'subtitulo': 'Solicitud de Facturas',
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Datos requeridos:**',
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
                        '**Empresas:** enviar foto del RUT'
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
                    'contenido_items': [  # CAMBIADO: items -> contenido_items
                        '**Email PQR:** pqr@mastvproducciones.net.co',
                        '**Email CARTERA:** auxiliaradministrativo@mastvproducciones.net.co',
                        '**Email INGENIERIA: ingenieria@mastvproducciones.net.co',
                        '**Email RECURSOS HUMANOS:** rh@mastvproducciones.net.co',
                        '**Chat de Soporte:** Solo mensajes escritos 3187777771',
                        '**No se reciben:** audios ni llamadas por WhatsApp'
                    ]
                }
            ]
        }
    }
    
    return render_template('informacion_general.html', informacion=informacion)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('login'))

# Ruta para cambiar contraseña (todos los usuarios)
@app.route('/cambiar_password', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    if request.method == 'POST':
        password_actual = request.form['password_actual']
        nueva_password = request.form['nueva_password']
        confirmar_password = request.form['confirmar_password']
        
        # Validaciones
        if not password_actual or not nueva_password or not confirmar_password:
            flash('Todos los campos son obligatorios', 'error')
            return render_template('cambiar_password.html')
        
        if nueva_password != confirmar_password:
            flash('Las nuevas contraseñas no coinciden', 'error')
            return render_template('cambiar_password.html')
        
        if len(nueva_password) < 6:
            flash('La nueva contraseña debe tener al menos 6 caracteres', 'error')
            return render_template('cambiar_password.html')
        
        # Verificar contraseña actual
        conexion = crear_conexion()
        if conexion:
            try:
                cursor = conexion.cursor(dictionary=True)
                cursor.execute("SELECT password FROM usuarios WHERE id = %s", (current_user.id,))
                usuario = cursor.fetchone()
                
                if usuario and check_password_hash(usuario['password'], password_actual):
                    # Actualizar contraseña
                    hash_nueva_password = generate_password_hash(nueva_password)
                    cursor.execute(
                        "UPDATE usuarios SET password = %s WHERE id = %s",
                        (hash_nueva_password, current_user.id)
                    )
                    conexion.commit()
                    flash('Contraseña actualizada correctamente', 'success')
                    return redirect(url_for('index'))
                else:
                    flash('La contraseña actual es incorrecta', 'error')
                    
            except mysql.connector.Error as e:
                flash('Error al cambiar la contraseña', 'error')
                print(f"Error: {e}")
            finally:
                cursor.close()
                conexion.close()
    
    return render_template('cambiar_password.html')

# Ruta para gestionar usuarios (solo admin)
@app.route('/usuarios')
@login_required
def gestion_usuarios():
    if current_user.rol != 'admin':
        flash('No tienes permisos para acceder a esta página', 'error')
        return redirect(url_for('index'))
    
    conexion = crear_conexion()
    usuarios = []
    if conexion:
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("SELECT * FROM usuarios ORDER BY fecha_creacion DESC")
            usuarios = cursor.fetchall()
            
            # Parsear permisos JSON para cada usuario
            for usuario in usuarios:
                if usuario.get('permisos'):
                    try:
                        usuario['permisos_parsed'] = json.loads(usuario['permisos'])
                    except:
                        usuario['permisos_parsed'] = {}
                else:
                    usuario['permisos_parsed'] = {}
                    
        except mysql.connector.Error as e:
            flash('Error al cargar los usuarios', 'error')
            print(f"Error: {e}")
        finally:
            cursor.close()
            conexion.close()
    
    return render_template('gestion_usuarios.html', usuarios=usuarios)

# Ruta para editar usuario (solo admin)
@app.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if current_user.rol != 'admin':
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('index'))
    
    conexion = crear_conexion()
    usuario_data = None
    if conexion:
        try:
            cursor = conexion.cursor(dictionary=True)
            
            if request.method == 'POST':
                usuario = request.form['usuario']
                password = request.form['password']
                rol = request.form['rol']
                
                # Obtener permisos del formulario (sin gestionar_usuarios)
                permisos = {
                    'ver_fichas': True,  # Siempre activo
                    'agregar_fichas': 'agregar_fichas' in request.form,
                    'editar_fichas': 'editar_fichas' in request.form,
                    'eliminar_fichas': 'eliminar_fichas' in request.form,
                    'cambiar_password': True  # Siempre permitido
                }
                
                permisos_json = json.dumps(permisos)
                
                if password:
                    hash_password = generate_password_hash(password)
                    cursor.execute(
                        "UPDATE usuarios SET usuario = %s, password = %s, rol = %s, permisos = %s WHERE id = %s",
                        (usuario, hash_password, rol, permisos_json, id)
                    )
                else:
                    cursor.execute(
                        "UPDATE usuarios SET usuario = %s, rol = %s, permisos = %s WHERE id = %s",
                        (usuario, rol, permisos_json, id)
                    )
                
                conexion.commit()
                flash('Usuario actualizado correctamente', 'success')
                return redirect(url_for('gestion_usuarios'))
            
            # GET: Cargar datos del usuario
            cursor.execute("SELECT * FROM usuarios WHERE id = %s", (id,))
            usuario_data = cursor.fetchone()
            
            if usuario_data and usuario_data.get('permisos'):
                try:
                    usuario_data['permisos_parsed'] = json.loads(usuario_data['permisos'])
                except:
                    usuario_data['permisos_parsed'] = {}
            else:
                usuario_data['permisos_parsed'] = {}
            
        except mysql.connector.IntegrityError:
            flash('El usuario ya existe', 'error')
        except mysql.connector.Error as e:
            flash('Error al editar el usuario', 'error')
            print(f"Error: {e}")
        finally:
            cursor.close()
            conexion.close()
    
    if not usuario_data:
        flash('Usuario no encontrado', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    return render_template('editar_usuario.html', usuario=usuario_data)

# Ruta para agregar usuario (solo admin)
@app.route('/agregar_usuario', methods=['GET', 'POST'])
@login_required
def agregar_usuario():
    if current_user.rol != 'admin':
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']
        rol = request.form['rol']
        
        if not usuario or not password:
            flash('Usuario y contraseña son obligatorios', 'error')
            return render_template('agregar_usuario.html')
        
        # Obtener permisos del formulario (sin gestionar_usuarios)
        permisos = {
            'ver_fichas': True,  # Siempre activo
            'agregar_fichas': 'agregar_fichas' in request.form,
            'editar_fichas': 'editar_fichas' in request.form,
            'eliminar_fichas': 'eliminar_fichas' in request.form,
            'cambiar_password': True  # Siempre permitido
        }
        
        permisos_json = json.dumps(permisos)
        hash_password = generate_password_hash(password)
        
        conexion = crear_conexion()
        if conexion:
            try:
                cursor = conexion.cursor()
                cursor.execute(
                    "INSERT INTO usuarios (usuario, password, rol, permisos) VALUES (%s, %s, %s, %s)",
                    (usuario, hash_password, rol, permisos_json)
                )
                conexion.commit()
                flash('Usuario agregado correctamente', 'success')
                return redirect(url_for('gestion_usuarios'))
            except mysql.connector.IntegrityError:
                flash('El usuario ya existe', 'error')
            except mysql.connector.Error as e:
                flash('Error al agregar el usuario', 'error')
                print(f"Error: {e}")
            finally:
                cursor.close()
                conexion.close()
    
    return render_template('agregar_usuario.html')

# Ruta para eliminar usuario (solo admin)
@app.route('/eliminar_usuario/<int:id>')
@login_required
def eliminar_usuario(id):
    if current_user.rol != 'admin':
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('index'))
    
    if id == current_user.id:
        flash('No puedes eliminar tu propio usuario', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    conexion = crear_conexion()
    if conexion:
        try:
            cursor = conexion.cursor()
            cursor.execute("DELETE FROM usuarios WHERE id = %s", (id,))
            conexion.commit()
            flash('Usuario eliminado correctamente', 'success')
        except mysql.connector.Error as e:
            flash('Error al eliminar el usuario', 'error')
            print(f"Error: {e}")
        finally:
            cursor.close()
            conexion.close()
    
    return redirect(url_for('gestion_usuarios'))

# Rutas principales
@app.route('/')
@login_required
def index():
    if not current_user.puede('ver_fichas'):
        flash('No tienes permisos para ver las fichas', 'error')
        return redirect(url_for('login'))
    
    conexion = crear_conexion()
    fichas = []
    if conexion:
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fichas ORDER BY fecha_actualizacion DESC")
            fichas = cursor.fetchall()
        except mysql.connector.Error as e:
            flash('Error al cargar las fichas', 'error')
            print(f"Error: {e}")
        finally:
            cursor.close()
            conexion.close()
    
    return render_template('index.html', fichas=fichas, user=current_user)

@app.route('/agregar', methods=['GET', 'POST'])
@login_required
def agregar_ficha():
    if not current_user.puede('agregar_fichas'):
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Obtener datos del formulario - manejar problema real o seleccionado
        categoria = request.form['categoria']
        problema = request.form.get('problema_real') or request.form['problema']
        descripcion = request.form['descripcion']
        causas = request.form['causas']
        solucion = request.form['solucion']
        palabras_clave = request.form['palabras_clave']
        
        # Validar campos requeridos
        if not all([categoria, problema, causas, solucion]):
            flash('Por favor, complete todos los campos requeridos', 'error')
            return render_template('agregar_ficha.html')
        
        # Procesar causas (convertir saltos de línea a |)
        causas_items = [item.strip() for item in causas.split('\n') if item.strip()]
        causas_str = '|'.join(causas_items)
        
        conexion = crear_conexion()
        if conexion:
            try:
                cursor = conexion.cursor()
                cursor.execute('''
                    INSERT INTO fichas (categoria, problema, descripcion, causas, solucion, palabras_clave)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (categoria, problema, descripcion, causas_str, solucion, palabras_clave))
                conexion.commit()
                flash('Ficha agregada correctamente', 'success')
                return redirect(url_for('index'))
            except mysql.connector.Error as e:
                flash('Error al agregar la ficha', 'error')
                print(f"Error: {e}")
            finally:
                cursor.close()
                conexion.close()
    
    return render_template('agregar_ficha.html')

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_ficha(id):
    if not current_user.puede('editar_fichas'):
        flash('No tienes permisos para realizar esta acción', 'error')
        return redirect(url_for('index'))
    
    conexion = crear_conexion()
    ficha = None
    if conexion:
        try:
            cursor = conexion.cursor(dictionary=True)
            
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
                
                cursor.execute('''
                    UPDATE fichas 
                    SET categoria=%s, problema=%s, descripcion=%s, 
                    causas=%s, solucion=%s, palabras_clave=%s 
                    WHERE id=%s
                ''', (categoria, problema, descripcion, causas_str, solucion, palabras_clave, id))
                
                conexion.commit()
                flash('Ficha actualizada correctamente', 'success')
                return redirect(url_for('index'))
            
            # GET: Cargar datos de la ficha
            cursor.execute("SELECT * FROM fichas WHERE id = %s", (id,))
            ficha = cursor.fetchone()
            
            # Convertir | de vuelta a saltos de línea para el formulario
            if ficha and ficha['causas']:
                ficha['causas'] = ficha['causas'].replace('|', '\n')
            
        except mysql.connector.Error as e:
            flash('Error al cargar/editar la ficha', 'error')
            print(f"Error: {e}")
        finally:
            cursor.close()
            conexion.close()
    
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
    
    conexion = crear_conexion()
    if conexion:
        try:
            cursor = conexion.cursor()
            cursor.execute("DELETE FROM fichas WHERE id = %s", (id,))
            conexion.commit()
            flash('Ficha eliminada correctamente', 'success')
        except mysql.connector.Error as e:
            flash('Error al eliminar la ficha', 'error')
            print(f"Error: {e}")
        finally:
            cursor.close()
            conexion.close()
    
    return redirect(url_for('index'))

@app.route('/buscar')
@login_required
def buscar():
    if not current_user.puede('ver_fichas'):
        flash('No tienes permisos para ver las fichas', 'error')
        return redirect(url_for('index'))
    
    query = request.args.get('q', '')
    categoria = request.args.get('categoria', '')
    
    conexion = crear_conexion()
    fichas = []
    if conexion:
        try:
            cursor = conexion.cursor(dictionary=True)
            
            if categoria and query:
                sql = "SELECT * FROM fichas WHERE categoria = %s AND (problema LIKE %s OR palabras_clave LIKE %s)"
                cursor.execute(sql, (categoria, f'%{query}%', f'%{query}%'))
            elif categoria:
                sql = "SELECT * FROM fichas WHERE categoria = %s"
                cursor.execute(sql, (categoria,))
            elif query:
                sql = "SELECT * FROM fichas WHERE problema LIKE %s OR palabras_clave LIKE %s"
                cursor.execute(sql, (f'%{query}%', f'%{query}%'))
            else:
                cursor.execute("SELECT * FROM fichas ORDER BY fecha_actualizacion DESC")
            
            fichas = cursor.fetchall()
        except mysql.connector.Error as e:
            flash('Error en la búsqueda', 'error')
            print(f"Error: {e}")
        finally:
            cursor.close()
            conexion.close()
    
    return render_template('buscar.html', fichas=fichas, query=query, categoria=categoria)

@app.route('/ficha/<int:id>')
@login_required
def ver_ficha(id):
    if not current_user.puede('ver_fichas'):
        flash('No tienes permisos para ver las fichas', 'error')
        return redirect(url_for('index'))
    
    conexion = crear_conexion()
    ficha = None
    if conexion:
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("SELECT * FROM fichas WHERE id = %s", (id,))
            ficha = cursor.fetchone()
        except mysql.connector.Error as e:
            flash('Error al cargar la ficha', 'error')
            print(f"Error: {e}")
        finally:
            cursor.close()
            conexion.close()
    
    if not ficha:
        flash('Ficha no encontrada', 'error')
        return redirect(url_for('index'))
    
    return render_template('ver_ficha.html', ficha=ficha)

# API para obtener problemas por categoría
@app.route('/api/problemas/<categoria>')
@login_required
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

if __name__ == '__main__':
    with app.app_context():
        crear_tablas()
    app.run(host='0.0.0.0', port=5000)