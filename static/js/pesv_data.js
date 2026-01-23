// static/js/pesv_data.js
// Sistema de gestión de actividades PESV con localStorage

const PESV_STORAGE_KEY = 'pesv_actividades_2026';

// Inicializar datos de ejemplo si no existen
function inicializarDatosEjemplo() {
    if (!localStorage.getItem(PESV_STORAGE_KEY)) {
        const datosEjemplo = [
            {
                id: 1,
                actividad: "Conformación COMITE DE SEGURIDAD VIAL",
                evidencia: "convocatoria, elección, conformación del Comité de seguridad vial y el acta de constitución.",
                ciclo: "Planear",
                articulo: "N/A",
                nivel: "Estandar y Avanzado (Paso 2)",
                responsables: "SST - GERENCIA",
                recursos: "Tecnologicos, Infraestructura, Humanos, Financieros",
                estado: "pendiente",
                avance: 0,
                fecha_creacion: "2026-01-15",
                observaciones: "",
                // Cronograma mensual (48 semanas = 12 meses * 4 semanas)
                cronograma: {
                    enero: { p1: true, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    febrero: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    marzo: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    abril: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    mayo: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    junio: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    julio: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    agosto: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    septiembre: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    octubre: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    noviembre: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    diciembre: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false }
                }
            },
            {
                id: 2,
                actividad: "Responsable del Sistema de Gestión de Seguridad y Salud en el Trabajo SG-SST",
                evidencia: "Documento en el que consta la asignación, con la respectiva determinación de responsabilidades y constatar la hoja de vida con soportes de la persona asignada.",
                ciclo: "Planear",
                articulo: "2.2.4.6.8",
                nivel: "N/A",
                responsables: "SST - COPASST - GERENCIA",
                recursos: "Tecnologicos, Infraestructura, Humanos, Financieros",
                estado: "completado",
                avance: 100,
                fecha_creacion: "2026-01-10",
                observaciones: "Asignación completada",
                cronograma: {
                    enero: { p1: true, p2: true, p3: true, p4: true, e1: true, e2: true, e3: true, e4: true },
                    febrero: { p1: false, p2: false, p3: false, p4: false, e1: false, e2: false, e3: false, e4: false },
                    // ... resto de meses
                }
            }
        ];
        localStorage.setItem(PESV_STORAGE_KEY, JSON.stringify(datosEjemplo));
    }
}

// Obtener todas las actividades
function obtenerActividades(filtros = {}) {
    const actividades = JSON.parse(localStorage.getItem(PESV_STORAGE_KEY)) || [];
    
    if (Object.keys(filtros).length === 0) {
        return actividades;
    }
    
    return actividades.filter(act => {
        let coincide = true;
        
        if (filtros.ciclo && act.ciclo !== filtros.ciclo) coincide = false;
        if (filtros.estado && act.estado !== filtros.estado) coincide = false;
        if (filtros.responsable && !act.responsables.includes(filtros.responsable)) coincide = false;
        
        return coincide;
    });
}

// Obtener actividad por ID
function obtenerActividadPorId(id) {
    const actividades = obtenerActividades();
    return actividades.find(act => act.id == id);
}

// Guardar nueva actividad
function guardarActividad(datos) {
    const actividades = obtenerActividades();
    const nuevaId = actividades.length > 0 ? Math.max(...actividades.map(a => a.id)) + 1 : 1;
    
    const nuevaActividad = {
        id: nuevaId,
        actividad: datos.actividad,
        evidencia: datos.evidencia,
        ciclo: datos.ciclo,
        articulo: datos.articulo,
        nivel: datos.nivel,
        responsables: datos.responsables,
        recursos: datos.recursos,
        estado: datos.estado || 'pendiente',
        avance: datos.avance || 0,
        fecha_creacion: new Date().toISOString().split('T')[0],
        observaciones: datos.observaciones || '',
        cronograma: datos.cronograma || generarCronogramaVacio()
    };
    
    actividades.push(nuevaActividad);
    localStorage.setItem(PESV_STORAGE_KEY, JSON.stringify(actividades));
    return nuevaId;
}

// Actualizar actividad
function actualizarActividad(id, datos) {
    const actividades = obtenerActividades();
    const index = actividades.findIndex(act => act.id == id);
    
    if (index !== -1) {
        actividades[index] = { ...actividades[index], ...datos };
        localStorage.setItem(PESV_STORAGE_KEY, JSON.stringify(actividades));
        return true;
    }
    return false;
}

// Eliminar actividad
function eliminarActividad(id) {
    let actividades = obtenerActividades();
    actividades = actividades.filter(act => act.id != id);
    localStorage.setItem(PESV_STORAGE_KEY, JSON.stringify(actividades));
    return true;
}

// Actualizar estado de semana en cronograma
function actualizarSemana(id, mes, semana, tipo, valor) {
    const actividades = obtenerActividades();
    const index = actividades.findIndex(act => act.id == id);
    
    if (index !== -1) {
        actividades[index].cronograma[mes][`${tipo}${semana}`] = valor;
        
        // Calcular nuevo avance
        const cronograma = actividades[index].cronograma;
        let totalSemanas = 0;
        let semanasEjecutadas = 0;
        
        Object.values(cronograma).forEach(mesData => {
            for (let i = 1; i <= 4; i++) {
                if (mesData[`p${i}`]) totalSemanas++;
                if (mesData[`e${i}`]) semanasEjecutadas++;
            }
        });
        
        actividades[index].avance = totalSemanas > 0 ? Math.round((semanasEjecutadas / totalSemanas) * 100) : 0;
        
        // Actualizar estado general
        if (actividades[index].avance >= 100) {
            actividades[index].estado = 'completado';
        } else if (actividades[index].avance > 0) {
            actividades[index].estado = 'en_proceso';
        } else {
            actividades[index].estado = 'pendiente';
        }
        
        localStorage.setItem(PESV_STORAGE_KEY, JSON.stringify(actividades));
        return actividades[index];
    }
    return null;
}

// Generar cronograma vacío
function generarCronogramaVacio() {
    const meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 
                  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
    const cronograma = {};
    
    meses.forEach(mes => {
        cronograma[mes] = {
            p1: false, e1: false,
            p2: false, e2: false,
            p3: false, e3: false,
            p4: false, e4: false
        };
    });
    
    return cronograma;
}

// Obtener estadísticas
function obtenerEstadisticas() {
    const actividades = obtenerActividades();
    const total = actividades.length;
    const completadas = actividades.filter(a => a.estado === 'completado').length;
    const enProceso = actividades.filter(a => a.estado === 'en_proceso').length;
    const avancePromedio = total > 0 ? actividades.reduce((sum, act) => sum + act.avance, 0) / total : 0;
    
    // Estadísticas por ciclo PHVA
    const ciclos = ['Planear', 'Hacer', 'Verificar', 'Actuar'];
    const statsCiclos = ciclos.map(ciclo => {
        const actsCiclo = actividades.filter(a => a.ciclo === ciclo);
        const totalCiclo = actsCiclo.length;
        const completadasCiclo = actsCiclo.filter(a => a.estado === 'completado').length;
        const avanceCiclo = totalCiclo > 0 ? 
            actsCiclo.reduce((sum, act) => sum + act.avance, 0) / totalCiclo : 0;
        
        return [ciclo, totalCiclo, completadasCiclo, avanceCiclo];
    });
    
    // Actividades recientes (últimas 5)
    const recientes = actividades
        .sort((a, b) => new Date(b.fecha_creacion) - new Date(a.fecha_creacion))
        .slice(0, 5)
        .map(act => ({
            id: act.id,
            actividad: act.actividad,
            ciclo: act.ciclo,
            responsables: act.responsables,
            estado: act.estado,
            avance: act.avance,
            fecha_creacion: act.fecha_creacion
        }));
    
    return {
        total,
        completadas,
        enProceso,
        avancePromedio: Math.round(avancePromedio),
        statsCiclos,
        actividades_recientes: recientes
    };
}

// Exportar para usar en otros archivos
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        inicializarDatosEjemplo,
        obtenerActividades,
        obtenerActividadPorId,
        guardarActividad,
        actualizarActividad,
        eliminarActividad,
        actualizarSemana,
        obtenerEstadisticas
    };
}
