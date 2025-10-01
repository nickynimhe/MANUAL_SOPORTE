-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Servidor: 127.0.0.1
-- Tiempo de generación: 01-10-2025 a las 19:30:52
-- Versión del servidor: 10.4.32-MariaDB
-- Versión de PHP: 8.0.30

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Base de datos: `soporte_tecnico`
--

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `fichas`
--

CREATE TABLE `fichas` (
  `id` int(11) NOT NULL,
  `categoria` varchar(20) NOT NULL DEFAULT 'Equipo',
  `problema` varchar(255) NOT NULL,
  `descripcion` text DEFAULT NULL,
  `causas` text DEFAULT NULL,
  `solucion` text DEFAULT NULL,
  `palabras_clave` text DEFAULT NULL,
  `fecha_creacion` timestamp NOT NULL DEFAULT current_timestamp(),
  `fecha_actualizacion` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Volcado de datos para la tabla `fichas`
--

INSERT INTO `fichas` (`id`, `categoria`, `problema`, `descripcion`, `causas`, `solucion`, `palabras_clave`, `fecha_creacion`, `fecha_actualizacion`) VALUES
(4, 'TV', 'No hay señal en el televisor', 'Usuario indica que el televisor no muestra ningún canal, aparece en pantalla negra o con el mensaje sin señal.', 'Micronodo/CATV alarmado, apagado|Problemas con el decodificador', 'Encender el CATV.|Validar que el Micronodo no esté alarmado.|Confirmar que CATV y Micronodo estén conectados correctamente.|Verificar que el decodificador esté programado adecuadamente.', 'Sin señal, CATV, Micronodo, Decodificador', '2025-09-30 13:29:02', '2025-10-01 09:33:14'),
(5, 'TV', 'Imagen pixelada o con interferencias', 'Usuario indica que la imagen se ve con cuadritos, borrosa, congelada o con rayas', 'Cable de señal dañado|Problemas con la antena/servicio|Reprogramacion mal ejecutada', 'Validar si el inconveniente no corresponde al proveedor.|Indicar al usuario que reprograme en modo Aire/Antena.|Brindar el paso a paso para la reprogramación.|Si persiste la falla, generar orden de servicio en Softv para enviar personal técnico.', 'Pixeleado, lluvioso, intermitencia', '2025-09-30 13:34:03', '2025-10-01 09:36:18'),
(6, 'TV', 'Sin sonido en algunos canales', 'Usuario indica que en ciertos canales tiene imagen pero no hay sonido.', 'Falla temporal del canal|Configuración de audio del canal', 'Validar que no sea falla del proveedor.|Indagar con el usuario si el problema es solo con un canal o con varios.|Consultar con el área encargada.|Indicar al usuario que reprograme.|Si son varios canales afectados, generar orden en Softv para enviar personal técnico.', 'Sin sonido', '2025-09-30 13:37:07', '2025-10-01 09:36:51'),
(7, 'TV', 'Problemas con la guía de programación', 'Usuario indica que ingreso a un apartado del TV pero no aparece las opciones que se le dan en la guia, en algunos casos no saben reprogramar.', 'No sabe como reprogramar|Esta reprogramando en modo cable|La guia de reprogramacion no es clara', 'Enviar al usuario el paso a paso de cómo hacerlo por WhatsApp.|Confirmar con el usuario si reprogramó en modo aérea/antena.|Si no funciona, generar orden de servicio en Softv y enviar personal técnico.', 'Reprogramar', '2025-09-30 13:47:05', '2025-10-01 09:31:23'),
(8, 'Internet', 'Internet lento o intermitente', 'Usuario indica que la conexión se cae constantemente o que la velocidad es muy baja.', 'Congestión de la red|Potencias mayores a -27', 'Validar potencias del módem.|Realizar Reboot en Vortex y esperar 1 minuto.|Ejecutar Resync Config en Vortex y esperar 1 minuto.|Indicar al usuario desconectar el módem por 3 minutos.', 'Lento, Intermitente', '2025-09-30 13:52:13', '2025-10-01 09:38:24'),
(9, 'Internet', 'Sin conexión a internet', 'Usuario indica que no puede navegar en ningún dispositivo y aparece como sin acceso a la red, tiene un LED rojo encendido.', 'Router/módem apagado|patchcord desconectado/Dañado', 'Habilitar nuevamente el módem en Vortex.|Si presenta LOS, generar orden de falla en Softv para enviar personal técnico.', 'LOS , Modem', '2025-09-30 13:55:27', '2025-10-01 09:40:18'),
(10, 'Internet', 'Sin conexión a internet', 'Usuario indica que no le aparece la red estuvo con intermitencias y no volvio a funcionar.', 'PON intermitente', 'Eliminar la ONU en Vortex.|Autorizarla en la sección Unconfigured.|Subir la ONU con las características anteriores.|Realizar Reboot en Vortex y esperar 1 minuto.|Ejecutar Resync Config en Vortex y esperar 1 minuto.|Validar si muestra navegacion, de lo contario pedir que desconecte por 3 minutos|Enviar personal tecnico si continua la falla', 'PON', '2025-09-30 14:01:47', '2025-10-01 09:44:54'),
(11, 'Internet', 'Sin conexión a internet', 'Usuario indica que no le aparece el nombre de la red, sino un nombre raro.', 'ONU desconfigurada', 'Validar que no sea una HWTC - SBX4T, ya que se desconfigura si se le aplica Reboot.|Indicar al usuario identificar la red con “nombre raro”.|Proporcionar la contraseña 12345678.|Preguntar si cuentan con computador para configurar de forma remota.|Validar en Vortex si la ONU da gestión|Enviar personal tecnico', 'ONU Desconfigurada', '2025-09-30 14:11:11', '2025-10-01 09:45:42'),
(12, 'Internet', 'Sin conexión a internet', 'Usuario indica que se quedo sin internet de manera inesperada.', 'IP 192.168.xxx', 'Validar la IP en Vortex.|Realizar Reboot en Vortex y esperar 1 minuto.|Ejecutar Resync Config en Vortex y esperar 1 minuto.|Validar si la IP cambió.|Cambiar la VLAN según la zona y validar si da MAC y la IP cambia.|Si cambia, repetir Reboot y Resync Config en Vortex.', 'IP, 196.168', '2025-09-30 14:15:03', '2025-10-01 09:46:38'),
(13, 'Internet', 'Problemas con WiFi', 'Usuario indica que la señal WiFi no llega a todos los espacios, presenta cortes o es débil.', 'Señal WiFi débil|Interferencia en la red', 'Realizar Resync Config en Vortex y esperar 1 minuto.|Solicitar al usuario desconectar el módem por 3 minutos.|Indicar que pruebe navegación en alguna app o sitio web.|Recomendar seguimiento; si persiste la falla, generar orden de mantenimiento en Softv.', 'Interferencia, Wifi ', '2025-09-30 14:20:49', '2025-10-01 09:48:02'),
(14, 'Internet', 'Problemas con WiFi', 'Usuario indica que los dispositivos de la vivienda no estan funcionando de manera optima con la red. ', 'Límite de dispositivos conectados', 'Indagar cuántas megas tiene contratadas.|Validar cuántos dispositivos están conectados.|Realizar Resync Config en Vortex y esperar 1 minuto.|Si la falencia persiste, sugerir un cambio de plan.', 'Dispositivos, Megas, Cambio plan', '2025-09-30 14:24:22', '2025-10-01 09:48:54'),
(15, 'Internet', 'Problemas con WiFi', 'Usuario indica que en ciertas partes de la vivienda no llega la red de internet de manera optima.', 'Router en ubicación demasiado lejos', 'Consultar con el usuario en qué parte se encuentra el router.|Validar en qué zonas no llega la red o si la vivienda es muy amplia.|Realizar Resync Config en Vortex y esperar 1 minuto.|Recomendar un repetidor o un traslado interno del router.', 'Repetidor, traslado', '2025-09-30 14:31:24', '2025-10-01 09:52:52'),
(16, 'Internet', 'No puedo conectarme a sitios específicos', 'Usuario indica que no se puede conectar a ciertos sitios con la red de proveedor pero si con datos moviles.', 'Problemas con la IP actual|Bloqueos de proveedor|IP en lista negra', 'Solicitar captura de la IP con el servicio activo.|Solicitar captura del error mostrado.|Pedir el link de la página bloqueada.|Si es servicio de Microsoft, indicar uso de VPN.|Escalar el caso al área de NOC con los datos del usuario y la información recopilada.', 'IP, paginas, datos, VPN', '2025-09-30 14:35:10', '2025-10-01 09:54:49'),
(17, 'Internet', 'Velocidad inferior a la contratada', 'Usuario indica que tras hacer el test de velocidad, las megas son mas bajas a las contratadas.', 'Usuario esta haciendo el test por medio de wifi, no es preciso|El cable de red no esta conectado en el puerto LAN indicado|El modem no tiene capacidad de dar las megas por medio de red', 'Validar con el usuario cómo está realizando el test.|Indicar que debe hacerse por cable de red para mayor precisión.|Revisar en Get Status (Vortex) en qué puerto está conectado el cable.|Solicitar que conecte el cable en el puerto LAN1 en casi de ser un modem antiguo, los modernos los 4 puertos cuentan todos con la misma capacidad.|Realizar Resync Config en Vortex.|Indicar al usuario desconectar el módem por 3 minutos.|Solicitar que realice nuevamente el test.|Validar que el computador negocie en 100 Mbps (ya que se manejan planes de 10 Mbps, 100 Mbps o 1 Gbps).', 'Test, Velocidad, Lentitud', '2025-09-30 14:41:43', '2025-10-01 09:57:14'),
(18, 'Internet', 'Problemas con el módem/router', 'Usuario indica que el modem se enciende y apaga solo.', 'Conectado en una toma de corriente poco eficiente|No tiene un estabilizador|Boton OFF/ON atascado', 'Sugerir al usuario conectar el módem a otra toma de corriente.|Recomendar el uso de estabilizador.|Validar el estado del botón (OFF/ON).|Si el usuario se vuelve a comunicar, generar orden en Softv para enviar personal técnico.', 'Toma de corriente, estabilizador ', '2025-09-30 14:50:39', '2025-10-01 09:58:08'),
(19, 'Equipo', 'Equipo no enciende', 'Usuario indica que el dispositivo no prende ni muestra luces aunque esté conectado a la corriente.', 'Cargador del modem desconectado|Boton OFF/ON Sin presionar', 'Indicar al usuario validar el cableado del cargador del módem.|Sugerir conectarlo en otra toma de corriente.|Realizar Resync Config en Vortex y esperar que el equipo cambie de estado.|Recomendar revisar el botón trasero del módem.|Si persiste la falla, generar orden en Softv para enviar personal técnico.', 'Apagado, No enciende, Modem', '2025-09-30 14:53:51', '2025-10-01 10:04:29'),
(20, 'Equipo', 'Equipo no enciende', 'Usuario indica que el modem enciende, pero solo el LED POWER.', 'Equipo quemado', 'Corroborar que solo sea ese LED el afectado.|Preguntar al usuario si es la primera vez que ocurre o si ya ha sucedido antes.|Indicar que conecte el módem en otra toma de corriente.|Si persiste, generar orden en Softv para enviar personal técnico y realizar el cambio de módem.', 'Quemado, Power, CAPAT', '2025-09-30 14:59:29', '2025-10-01 10:03:29'),
(21, 'Equipo', 'Problemas con puertos', 'Usuario indica que al conectar el cable de red al puerto no da servico.', 'Puerto físico dañado|Cable defectuoso', 'Indagar con el usuario el estado físico del cableado.|Solicitar evidencia fotográfica de los puertos para descartar daño físico.|Validar que el cable de red soporte la capacidad del servicio contratado.|Sugerir al usuario adquirir un cable más adecuado según su necesidad (mínimo categoría 5e).', 'Puerto, Red', '2025-09-30 15:05:15', '2025-10-01 10:01:26'),
(22, 'Equipo', 'Problemas con puertos', 'Usuario indica que el cable da 1GB pero al momento de conectar no alcanza esas megas.', 'Conexion de  puertos erronea', 'Validar en Get Status (Vortex) cómo están conectados los cables.|Solicitar al usuario evidencia fotográfica de la conexión.|Recomendar el uso del puerto LAN1 si el modem es anitguo, si es moderno todos los puertos estan en capacidad de entregar lo indicado.|Indagar con el usuario la capacidad del cable de red.|Si persiste la falla, generar orden en Softv para enviar personal técnico.', 'Puertos erroneos, Mala conexcion, LAN', '2025-09-30 15:09:49', '2025-10-01 10:00:46'),
(23, 'Equipo', 'Problemas con puertos', 'Usuario indica liberar un puerto especifico al tener dichos puertos bloqueados.', 'Puerto bloqueado por software', 'Solicitar al usuario acceso remoto por medio de computador.|Escalar el caso con el área encargada NOC.|Realizar un DMZ para liberar todos los puertos.|Si persiste, generar orden de falla en Softv para enviar personal técnico.', 'Puerto bloqueado, DMZ', '2025-09-30 15:14:48', '2025-10-01 09:59:06'),
(30, 'Equipo', 'Dispositivo no da MAC', 'Usuario indica que no tiene servicio pero el modem presenta condiciones optimas.', 'VLAN incorrecta|Fallo en el sistema operativo|Dispositivo desconfigurado', 'Validar en Vortex que la VLAN corresponda a la zona.|Realizar Resync Config en Vortex y esperar 1 minuto.|Revisar en Get Status en Vortex si ya entrega MAC.|Probar con otras VLAN de la zona en Vortex.|Si no genera MAC, crear orden de falla en Softv para enviar personal técnico.', 'MAC, VLAN', '2025-09-30 17:04:40', '2025-10-01 10:06:03');

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `usuarios`
--

CREATE TABLE `usuarios` (
  `id` int(11) NOT NULL,
  `usuario` varchar(50) NOT NULL,
  `password` varchar(255) NOT NULL,
  `rol` enum('admin','asesor') NOT NULL DEFAULT 'asesor',
  `fecha_creacion` timestamp NOT NULL DEFAULT current_timestamp(),
  `fecha_actualizacion` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `permisos` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT '{\r\n    "ver_fichas": true,\r\n    "agregar_fichas": false,\r\n    "editar_fichas": false,\r\n    "eliminar_fichas": false,\r\n    "cambiar_password": true\r\n}' CHECK (json_valid(`permisos`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Volcado de datos para la tabla `usuarios`
--

INSERT INTO `usuarios` (`id`, `usuario`, `password`, `rol`, `fecha_creacion`, `fecha_actualizacion`, `permisos`) VALUES
(1, 'admin', 'scrypt:32768:8:1$GYLitI11BqRpnnNx$3adb3a1bf184477ed191740551bacc0554b711f78d020526a6a63fbb97562da618e5ce5ef2b2af88eae7015aa202672e22f452568aee17b2f289d34aaad96646', 'admin', '2025-09-16 00:01:07', '2025-10-01 14:01:51', '{\r\n    \"ver_fichas\": true,\r\n    \"agregar_fichas\": false,\r\n    \"editar_fichas\": false,\r\n    \"eliminar_fichas\": false,\r\n    \"cambiar_password\": true\r\n}'),
(2, 'asesor', 'scrypt:32768:8:1$y4mBv6yET3dE1AOG$a0f2ae79026b6d3accb5bd80c610f8c6c0bc1fbc70d11b8b5825188947a64abe24114f439b89f935f704416d7bc6868e37920714c8177a7eb2276c3f61095b6e', 'asesor', '2025-09-16 00:01:07', '2025-10-01 14:01:51', '{\r\n    \"ver_fichas\": true,\r\n    \"agregar_fichas\": false,\r\n    \"editar_fichas\": false,\r\n    \"eliminar_fichas\": false,\r\n    \"cambiar_password\": true\r\n}'),
(25, 'Prueba', 'scrypt:32768:8:1$Ow5hSktsozHLQHd9$c056bc8af82325ab48a0f2d35ba16b55dbe957f3aa636238a780f7899140f6d0144bda9907194b528be7ce94720f29ae338ed8d439e8918cad995d2b3a67c769', 'asesor', '2025-09-16 13:15:34', '2025-09-16 13:15:34', '{\r\n    \"ver_fichas\": true,\r\n    \"agregar_fichas\": false,\r\n    \"editar_fichas\": false,\r\n    \"eliminar_fichas\": false,\r\n    \"cambiar_password\": true\r\n}');

--
-- Índices para tablas volcadas
--

--
-- Indices de la tabla `fichas`
--
ALTER TABLE `fichas`
  ADD PRIMARY KEY (`id`);

--
-- Indices de la tabla `usuarios`
--
ALTER TABLE `usuarios`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `usuario` (`usuario`);

--
-- AUTO_INCREMENT de las tablas volcadas
--

--
-- AUTO_INCREMENT de la tabla `fichas`
--
ALTER TABLE `fichas`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=31;

--
-- AUTO_INCREMENT de la tabla `usuarios`
--
ALTER TABLE `usuarios`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=554;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
