#!/usr/bin/env python
import os
import sys
import subprocess
import platform

def print_header(message):
    print(f"\n{'=' * 50}")
    print(f" {message}")
    print(f"{'=' * 50}")

def run_command(command, description):
    print(f"\n> {description}...")
    try:
        result = subprocess.run(command, 
                              shell=True, 
                              check=True,
                              capture_output=True,
                              text=True)
        print(f"✅ Comando executado com sucesso")
        if result.stdout.strip():
            print(f"Saída: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao executar o comando: {e}")
        if e.stdout:
            print(f"Saída: {e.stdout}")
        if e.stderr:
            print(f"Erro: {e.stderr}")
        return False

def setup_environment():
    print_header("Configuração do Ambiente para Transcrição de Vídeos")
    
    # Verifica Python
    python_version = sys.version_info
    print(f"\nVersão do Python: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
        print("❌ Versão do Python não suportada. Use Python 3.8 ou superior.")
        return False
    
    # Cria diretórios necessários
    print("\nCriando diretórios necessários...")
    dirs = ["audios", "videos", "transcricoes", "uploads", "transcriptions", "generated_audio", "static", "templates"]
    for d in dirs:
        try:
            os.makedirs(d, exist_ok=True)
            print(f"✅ Diretório '{d}' criado ou já existe")
        except Exception as e:
            print(f"❌ Erro ao criar diretório '{d}': {e}")
    
    # Atualiza pip
    run_command(f"{sys.executable} -m pip install --upgrade pip", "Atualizando pip")
    
    # Instala/atualiza pacotes
    run_command(f"{sys.executable} -m pip install -U -r requirements.txt", "Instalando dependências Python do requirements.txt")
    
    # Verifica e instala FFmpeg se necessário
    print_header("Verificando FFmpeg")
    try:
        subprocess.run(['ffmpeg', '-version'], 
                       stdout=subprocess.PIPE, 
                       stderr=subprocess.PIPE,
                       check=True)
        print("✅ FFmpeg já está instalado")
    except (subprocess.SubprocessError, FileNotFoundError):
        print("❌ FFmpeg não encontrado")
        
        system = platform.system().lower()
        if system == 'linux':
            print("\nNo Linux, você pode instalar o FFmpeg com o seguinte comando:")
            print("sudo apt-get update && sudo apt-get install -y ffmpeg")
            
            choice = input("\nDeseja tentar instalar o FFmpeg automaticamente? (s/n): ")
            if choice.lower() == 's':
                run_command("sudo apt-get update && sudo apt-get install -y ffmpeg", "Instalando FFmpeg")
                
        elif system == 'windows':
            if os.path.exists('ffmpeg.exe') and os.path.exists('ffplay.exe') and os.path.exists('ffprobe.exe'):
                print("✅ Executáveis do FFmpeg encontrados no diretório atual")
                print("   Para torná-los disponíveis globalmente, adicione este diretório ao seu PATH")
            else:
                print("\nNo Windows, baixe o FFmpeg do site oficial:")
                print("https://ffmpeg.org/download.html")
                print("Extraia os arquivos ffmpeg.exe, ffplay.exe e ffprobe.exe para este diretório")
                print("ou adicione o diretório do FFmpeg ao seu PATH")
                
        elif system == 'darwin':  # macOS
            print("\nNo macOS, você pode instalar o FFmpeg com Homebrew:")
            print("brew install ffmpeg")
            
            choice = input("\nDeseja tentar instalar o FFmpeg automaticamente via Homebrew? (s/n): ")
            if choice.lower() == 's':
                run_command("brew install ffmpeg", "Instalando FFmpeg via Homebrew")
    
    # Verifica instalação do yt-dlp
    print_header("Verificando instalação do yt-dlp")
    try:
        result = subprocess.run([sys.executable, '-m', 'yt_dlp', '--version'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE,
                              text=True)
        print(f"✅ yt-dlp versão: {result.stdout.strip()}")
    except Exception as e:
        print(f"❌ Erro ao verificar yt-dlp: {e}")
        run_command(f"{sys.executable} -m pip install -U yt-dlp", "Instalando/atualizando yt-dlp")
    
    # Verifica Whisper
    print_header("Verificando Whisper")
    try:
        subprocess.run([sys.executable, '-c', 'import whisper; print(f"✅ Whisper instalado")'], 
                     check=True)
    except Exception:
        print("❌ Whisper não está instalado corretamente")
        print("  Tentando reinstalar...")
        run_command(f"{sys.executable} -m pip install -U openai-whisper", "Reinstalando Whisper")
    
    # Verifica PyTorch (necessário para Whisper)
    print_header("Verificando PyTorch")
    try:
        subprocess.run([sys.executable, '-c', 'import torch; print(f"✅ PyTorch {torch.__version__} instalado")'], 
                     check=True)
    except Exception:
        print("❌ PyTorch não está instalado corretamente")
        print("  Instalando PyTorch (pode demorar um pouco)...")
        if platform.system().lower() == 'windows':
            run_command(f"{sys.executable} -m pip install torch torchvision torchaudio", "Instalando PyTorch para Windows")
        else:
            run_command(f"{sys.executable} -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu", "Instalando PyTorch para CPU")
    
    # Teste final
    print_header("Executando verificação final do ambiente")
    run_command(f"{sys.executable} check_environment.py", "Verificando ambiente")
    
    print_header("Configuração Concluída")
    print("\nPara iniciar o servidor:")
    print(f"   {sys.executable} -m uvicorn app:app --reload")
    print("\nOu usando o Python diretamente:")
    print(f"   {sys.executable} app.py")

if __name__ == "__main__":
    setup_environment() 