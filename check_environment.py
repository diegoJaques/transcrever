#!/usr/bin/env python
import os
import sys
import platform
import subprocess
import importlib.util

def check_ffmpeg():
    print("\n--- Verificando FFmpeg ---")
    try:
        # Tenta executar ffmpeg -version
        result = subprocess.run(['ffmpeg', '-version'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE,
                               text=True)
        if result.returncode == 0:
            version_line = result.stdout.splitlines()[0]
            print(f"✅ FFmpeg instalado: {version_line}")
            return True
        else:
            print("❌ FFmpeg não pôde ser executado")
            print(f"Erro: {result.stderr}")
            return False
    except FileNotFoundError:
        print("❌ FFmpeg não encontrado no PATH")
        if os.path.exists('./ffmpeg.exe'):
            print("   - ffmpeg.exe encontrado no diretório atual, mas não está no PATH")
        return False
    except Exception as e:
        print(f"❌ Erro ao verificar FFmpeg: {e}")
        return False

def check_package_version(package_name):
    try:
        package = importlib.__import__(package_name)
        version = getattr(package, "__version__", "versão desconhecida")
        print(f"✅ {package_name}: {version}")
        return True
    except ImportError:
        print(f"❌ {package_name} não instalado")
        return False
    except Exception as e:
        print(f"❌ Erro ao verificar {package_name}: {e}")
        return False

def check_environment():
    print("=== Verificação do Ambiente ===")
    print(f"Sistema: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version}")
    
    # Verifica FFmpeg
    ffmpeg_ok = check_ffmpeg()
    
    # Verifica pacotes críticos
    print("\n--- Verificando Pacotes Críticos ---")
    critical_packages = ["yt_dlp", "whisper", "pytube"]
    all_critical_ok = True
    
    for package in critical_packages:
        if not check_package_version(package):
            all_critical_ok = False
    
    # Verifica outros pacotes
    print("\n--- Verificando Outros Pacotes ---")
    other_packages = ["fastapi", "edge_tts", "requests"]
    
    for package in other_packages:
        check_package_version(package)
    
    # Verifica diretórios necessários
    print("\n--- Verificando Diretórios ---")
    needed_dirs = ["audios", "videos", "transcricoes", "uploads", "transcriptions", "generated_audio"]
    
    for dir_name in needed_dirs:
        if os.path.exists(dir_name) and os.path.isdir(dir_name):
            print(f"✅ Diretório {dir_name} existe")
        else:
            print(f"❌ Diretório {dir_name} não existe")
            try:
                os.makedirs(dir_name, exist_ok=True)
                print(f"   - Criado diretório {dir_name}")
            except Exception as e:
                print(f"   - Erro ao criar diretório: {e}")
    
    # Resumo
    print("\n=== Resumo ===")
    if ffmpeg_ok and all_critical_ok:
        print("✅ Todas as dependências críticas estão disponíveis.")
    else:
        print("❌ Algumas dependências críticas estão faltando ou têm problemas:")
        if not ffmpeg_ok:
            print("   - FFmpeg não está disponível corretamente")
        if not all_critical_ok:
            print("   - Alguns pacotes críticos estão faltando")
        
        print("\nSugestões:")
        if not ffmpeg_ok:
            print("1. Instale FFmpeg:")
            print("   - Linux: sudo apt-get install ffmpeg")
            print("   - Windows: baixe de https://ffmpeg.org/download.html e adicione ao PATH")
        
        print("2. Atualize os pacotes Python:")
        print("   pip install -U -r requirements.txt")

if __name__ == "__main__":
    check_environment() 