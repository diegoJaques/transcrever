import whisper
import os
import yt_dlp
import sys
from datetime import datetime

def verificar_ffmpeg():
    """Verifica se o FFmpeg está instalado e acessível"""
    try:
        os.system('ffmpeg -version')
        return True
    except:
        print("\n❌ ERRO: FFmpeg não encontrado!")
        print("Por favor, instale o FFmpeg:")
        print("1. Windows: Baixe de https://www.gyan.dev/ffmpeg/builds/")
        print("2. Linux: sudo apt install ffmpeg")
        print("3. MacOS: brew install ffmpeg")
        return False

def criar_diretorios():
    """Cria os diretórios necessários se não existirem"""
    diretorios = ['audios', 'videos', 'transcricoes']
    for dir in diretorios:
        os.makedirs(dir, exist_ok=True)
        print(f"✓ Diretório '{dir}' verificado")

def baixar_audio_youtube(url):
    """Baixa o áudio de um vídeo do YouTube"""
    print(f"\n📥 Baixando áudio do YouTube: {url}")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'audios/audio.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }],
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("✓ Áudio baixado com sucesso!")
        return 'audios/audio.mp3'
    except Exception as e:
        print(f"❌ Erro ao baixar vídeo: {str(e)}")
        return None

def extrair_audio_video(caminho_video):
    """Extrai o áudio de um vídeo local"""
    print(f"\n🎵 Extraindo áudio do vídeo: {caminho_video}")
    nome_audio = os.path.splitext(os.path.basename(caminho_video))[0] + ".mp3"
    caminho_audio = os.path.join('audios', nome_audio)
    
    try:
        comando = f'ffmpeg -y -i "{caminho_video}" -vn -acodec mp3 "{caminho_audio}"'
        os.system(comando)
        print("✓ Áudio extraído com sucesso!")
        return caminho_audio
    except Exception as e:
        print(f"❌ Erro ao extrair áudio: {str(e)}")
        return None

def transcrever_audio(caminho_audio, idioma='pt'):
    """Transcreve o áudio usando o modelo Whisper"""
    print(f"\n🎯 Iniciando transcrição...")
    try:
        resultado = modelo.transcribe(caminho_audio, language=idioma)
        print("✓ Transcrição concluída!")
        return resultado['text']
    except Exception as e:
        print(f"❌ Erro na transcrição: {str(e)}")
        return None

def salvar_transcricao(texto, nome_arquivo):
    """Salva a transcrição em um arquivo"""
    if not texto:
        print("❌ Nenhum texto para salvar!")
        return False
        
    try:
        caminho = os.path.join('transcricoes', nome_arquivo)
        with open(caminho, 'w', encoding='utf-8') as arquivo:
            arquivo.write(texto)
        print(f"✓ Transcrição salva em: {caminho}")
        return True
    except Exception as e:
        print(f"❌ Erro ao salvar transcrição: {str(e)}")
        return False

def menu():
    """Menu principal do programa"""
    while True:
        print("\n" + "="*50)
        print("🎥 SISTEMA DE TRANSCRIÇÃO DE VÍDEOS")
        print("="*50)
        print("[1] 📺 Transcrever vídeo do YouTube")
        print("[2] 📁 Transcrever vídeo local")
        print("[3] ℹ️  Informações sobre o sistema")
        print("[4] ❌ Sair")
        print("="*50)
        
        escolha = input("\nEscolha uma opção (1-4): ")

        if escolha == '4':
            print("\n👋 Obrigado por usar o sistema!")
            break

        elif escolha == '3':
            print("\nℹ️  Informações do Sistema:")
            print(f"Python: {sys.version.split()[0]}")
            print(f"Whisper Modelo: {modelo.model_name}")
            print(f"Diretório atual: {os.getcwd()}")
            print(f"FFmpeg instalado: {'Sim' if verificar_ffmpeg() else 'Não'}")
            input("\nPressione ENTER para continuar...")

        elif escolha == '1':
            url = input("\n🔗 Cole a URL do vídeo do YouTube: ")
            if not url:
                print("❌ URL inválida!")
                continue
                
            audio = baixar_audio_youtube(url)
            if audio and os.path.exists(audio):
                texto = transcrever_audio(audio)
                if texto:
                    nome_arquivo = f"youtube_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    salvar_transcricao(texto, nome_arquivo)

        elif escolha == '2':
            caminho_video = input("\n📁 Digite o caminho completo do vídeo: ")
            if not os.path.exists(caminho_video):
                print("❌ Arquivo não encontrado!")
                continue
                
            audio = extrair_audio_video(caminho_video)
            if audio and os.path.exists(audio):
                texto = transcrever_audio(audio)
                if texto:
                    nome_arquivo = os.path.splitext(os.path.basename(caminho_video))[0] + ".txt"
                    salvar_transcricao(texto, nome_arquivo)

        else:
            print("❌ Opção inválida!")

if __name__ == "__main__":
    try:
        print("\n🚀 Iniciando sistema de transcrição...")
        
        # Verifica FFmpeg
        if not verificar_ffmpeg():
            sys.exit(1)
            
        # Cria diretórios necessários
        criar_diretorios()
        
        # Carrega o modelo Whisper
        print("\n📦 Carregando modelo Whisper (pode demorar alguns minutos na primeira vez)...")
        modelo = whisper.load_model('small')
        print("✓ Modelo carregado com sucesso!")
        
        # Inicia o menu principal
        menu()
        
    except KeyboardInterrupt:
        print("\n\n👋 Programa encerrado pelo usuário.")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {str(e)}")
        sys.exit(1) 