// En tu script.js o dentro de <script> tags
document.addEventListener('DOMContentLoaded', function() {
    const causasTextarea = document.getElementById('causas');
    
    if (causasTextarea) {
        // Formatear causas existentes (para editar)
        if (causasTextarea.value.includes('|')) {
            causasTextarea.value = causasTextarea.value.split('|').join('\n');
        }
        
        // Procesar al enviar el formulario
        const form = causasTextarea.closest('form');
        form.addEventListener('submit', function() {
            const lineas = causasTextarea.value.split('\n')
                .filter(linea => linea.trim())
                .map(linea => linea.trim());
            causasTextarea.value = lineas.join('|');
        });
    }
});