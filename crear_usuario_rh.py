#!/usr/bin/env python3
from app import app
from werkzeug.security import generate_password_hash
from database import ejecutar_consulta

def crear_usuario_rh():
    with app.app_context():
        # Verificar si ya existe
        resultado = ejecutar_consulta(
            "SELECT id, usuario FROM usuarios WHERE usuario = %s",
            ('rh',),
            fetch=True
        )
        
        if resultado:
            print(f"✅ El usuario 'rh' ya existe (ID: {resultado[0][0]})")
            # Actualizar contraseña
            nueva_password = generate_password_hash('rh123')
            ejecutar_consulta(
                "UPDATE usuarios SET password = %s WHERE usuario = %s",
                (nueva_password, 'rh'),
                commit=True
            )
            print("🔑 Contraseña actualizada a: rh123")
        else:
            # Crear nuevo usuario
            password_hash = generate_password_hash('rh123')
            ejecutar_consulta("""
                INSERT INTO usuarios (usuario, password, rol, modulo_principal, permisos) 
                VALUES (%s, %s, %s, %s, %s)
            """, (
                'rh', 
                password_hash, 
                'rh', 
                'rh',
                '{"ver_rh": true, "gestionar_rh": true, "cambiar_password": true}'
            ), commit=True)
            print("✅ Usuario 'rh' creado correctamente")
            print("👤 Usuario: rh")
            print("🔑 Contraseña: rh123")
        
        # Verificar
        verificar = ejecutar_consulta(
            "SELECT id, usuario, rol FROM usuarios WHERE usuario = %s",
            ('rh',),
            fetch=True
        )
        if verificar:
            print(f"📋 Verificación: ID={verificar[0][0]}, Usuario={verificar[0][1]}, Rol={verificar[0][2]}")

if __name__ == "__main__":
    crear_usuario_rh()
