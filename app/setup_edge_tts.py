#!/usr/bin/env python3
"""
Script para instalar y verificar Edge TTS
"""

import subprocess
import sys
import asyncio

def install_package(package):
    """Instalar un paquete con pip"""
    print(f"📦 Instalando {package}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    print(f"✅ {package} instalado\n")

def check_installation():
    """Verificar las instalaciones"""
    packages = {
        'flask': False,
        'flask-cors': False,
        'edge-tts': False,
        'requests': False
    }
    
    print("🔍 Verificando paquetes instalados...")
    print("-" * 40)
    
    for package in packages:
        try:
            if package == 'flask-cors':
                __import__('flask_cors')
            elif package == 'edge-tts':
                __import__('edge_tts')
            else:
                __import__(package)
            packages[package] = True
            print(f"✅ {package} está instalado")
        except ImportError:
            print(f"❌ {package} NO está instalado")
    
    return packages

async def test_edge_tts():
    """Probar Edge TTS con diferentes voces"""
    import edge_tts
    
    print("\n🎤 Probando Edge TTS con diferentes voces...")
    print("-" * 40)
    
    test_voices = {
        'Helena (España)': 'es-ES-HelenaNeural',
        'Dalia (México)': 'es-MX-DaliaNeural',
        'Elena (Argentina)': 'es-AR-ElenaNeural',
        'Salomé (Colombia)': 'es-CO-SalomeNeural'
    }
    
    test_text = "Hola, soy una voz de prueba"
    
    for name, voice_id in test_voices.items():
        print(f"\n🔊 Probando {name}...")
        try:
            communicate = edge_tts.Communicate(test_text, voice_id)
            filename = f"test_{voice_id.split('-')[1]}.mp3"
            await communicate.save(filename)
            print(f"   ✅ Audio guardado como: {filename}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n💡 Los archivos de audio se guardaron en la carpeta actual")
    print("   Puedes reproducirlos para verificar las diferentes voces")

def main():
    """Función principal"""
    print("=" * 50)
    print("🚀 Configurador de Edge TTS para Chat con Voz")
    print("=" * 50)
    
    # Verificar instalaciones
    packages = check_installation()
    
    # Instalar paquetes faltantes
    missing = [pkg for pkg, installed in packages.items() if not installed]
    
    if missing:
        print(f"\n⚠️  Faltan {len(missing)} paquetes")
        print("¿Deseas instalarlos ahora? (s/n): ", end="")
        
        if input().lower() == 's':
            for package in missing:
                try:
                    install_package(package)
                    packages[package] = True
                except Exception as e:
                    print(f"❌ Error instalando {package}: {e}")
    else:
        print("\n✅ Todos los paquetes necesarios están instalados")
    
    # Probar Edge TTS si está instalado
    if packages.get('edge-tts'):
        print("\n¿Deseas probar las voces de Edge TTS? (s/n): ", end="")
        if input().lower() == 's':
            asyncio.run(test_edge_tts())
    
    # Instrucciones finales
    print("\n" + "=" * 50)
    print("📋 Instrucciones para ejecutar el chat:")
    print("=" * 50)
    
    if all(packages.values()):
        print("✅ Todo está listo!")
        print("\n1. Asegúrate de que Ollama esté ejecutándose:")
        print("   ollama serve")
        print("\n2. Ejecuta el servidor Flask:")
        print("   python app_edge_tts_fixed.py")
        print("\n3. Abre tu navegador en:")
        print("   http://localhost:5000")
        print("\n4. ¡Disfruta de las voces naturales!")
    else:
        print("⚠️  Algunos paquetes no están instalados")
        print("   Instálalos manualmente con:")
        for pkg in missing:
            print(f"   pip install {pkg}")
    
    print("\n💡 Tips:")
    print("   - Helena (España) es la voz más natural")
    print("   - Ajusta la velocidad a 0.9 para mejor naturalidad")
    print("   - Prueba diferentes voces según tu preferencia")
    print("=" * 50)

if __name__ == "__main__":
    main()