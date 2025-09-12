from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
import whisper
import os
import yt_dlp
import sys
from datetime import datetime
import asyncio
import json
import uuid
import time
from dotenv import load_dotenv
import requests
import shutil
from pathlib import Path
from audio_manager import AudioManager
import glob
import pytube
import ssl
import certifi
from pydantic import BaseModel
from typing import Optional

# Carrega variáveis de ambiente
load_dotenv()

# Configuração para contornar problemas de SSL
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['SSL_CERT_FILE'] = certifi.where()

app = FastAPI()

# Configuração para funcionar atrás de proxy reverso (Traefik)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Aceita todos os hosts
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuração de arquivos estáticos e templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Modelos disponíveis
MODELOS = {
    "tiny": "Tiny (mais rápido, menos preciso)",
    "base": "Base (bom equilíbrio)",
    "small": "Small (recomendado)",
    "medium": "Medium (mais preciso)",
    "large": "Large (máxima precisão)",
    "large-v2": "Large V2 (versão mais recente)",
    "large-v3": "Large V3 (versão mais recente)"
}

# Carrega o modelo inicial (pode ser alterado via API)
modelo_atual = None
modelo_atual_nome = 'small'  # Variável para armazenar o nome do modelo atual

# Gerenciador de conexões WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
        self.connection_states = {}  # Rastreia estado das conexões

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_states[client_id] = {
            "connected": True,
            "last_ping": time.time(),
            "transcricao_id": None
        }
        print(f"WebSocket conectado: {client_id}")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.connection_states:
            self.connection_states[client_id]["connected"] = False
        print(f"WebSocket desconectado: {client_id}")

    def is_connected(self, client_id: str) -> bool:
        """Verifica se a conexão ainda está ativa"""
        return (client_id in self.active_connections and 
                client_id in self.connection_states and 
                self.connection_states[client_id]["connected"])

    async def send_message(self, message: str, client_id: str):
        if not self.is_connected(client_id):
            print(f"Tentativa de enviar mensagem para conexão inativa: {client_id}")
            return False
        
        try:
            websocket = self.active_connections.get(client_id)
            if websocket and websocket.client_state.name == "CONNECTED":
                await websocket.send_text(message)
                self.connection_states[client_id]["last_ping"] = time.time()
                return True
            else:
                self.disconnect(client_id)
                return False
        except Exception as e:
            print(f"Erro ao enviar mensagem WebSocket para {client_id}: {e}")
            self.disconnect(client_id)
            return False

    def set_transcricao_id(self, client_id: str, transcricao_id: str):
        """Associa uma transcrição a uma conexão"""
        if client_id in self.connection_states:
            self.connection_states[client_id]["transcricao_id"] = transcricao_id

manager = ConnectionManager()

# Armazena informações sobre as transcrições em andamento
transcricoes_ativas = {}

# Cria diretórios para armazenar arquivos se não existirem
UPLOAD_DIR = Path("uploads")
TRANSCRIPTION_DIR = Path("transcriptions")
AUDIO_DIR = Path("generated_audio")

for directory in [UPLOAD_DIR, TRANSCRIPTION_DIR, AUDIO_DIR]:
    directory.mkdir(exist_ok=True)

# Inicializa o gerenciador de áudio
audio_manager = AudioManager(model_size="base", voice="pt-BR-FranciscaNeural")

def carregar_modelo(nome_modelo):
    global modelo_atual, modelo_atual_nome
    try:
        print(f"Iniciando carregamento do modelo {nome_modelo}...")
        print(f"Baixando e carregando o modelo Whisper {nome_modelo}...")
        modelo_atual = whisper.load_model(nome_modelo)
        modelo_atual_nome = nome_modelo
        print(f"Modelo {nome_modelo} carregado com sucesso!")
        return True
    except Exception as e:
        print(f"Erro ao carregar modelo: {str(e)}")
        return False

# Carrega o modelo inicial (usando 'small' que é mais leve e rápido)
carregar_modelo('small')

# Armazena as últimas transcrições
ultima_transcricao = None

def verificar_ffmpeg():
    try:
        os.system('ffmpeg -version')
        return True
    except:
        return False

def criar_diretorios():
    diretorios = ['audios', 'videos', 'transcricoes', 'tmp']
    for dir in diretorios:
        os.makedirs(dir, exist_ok=True)

def baixar_audio_youtube(url):
    # Cria diretório audios se não existir
    os.makedirs('audios', exist_ok=True)
    download_id = str(uuid.uuid4())
    last_error = None

    # --- Tentativa 1: yt-dlp (Principal) ---
    print(f"Iniciando download do YouTube (Tentativa 1 - yt-dlp principal): {url}")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'audios/audio_{download_id}.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        'geo_bypass': True, 'geo_bypass_country': 'US',
        'nocheckcertificate': True,  # Ignora verificação de certificado SSL
        'ignoreerrors': False, 'noplaylist': True,
        # Mais opções de robustez
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'skip_download': False,
        'hls_prefer_native': False,
        'hls_use_mpegts': True,
        'extractor_args': {'youtube': {'skip': ['dash', 'hls']}},
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5', 'Sec-Fetch-Mode': 'navigate',
        },
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Extraindo informações do vídeo...")
            info_dict = ydl.extract_info(url, download=True)
            if not info_dict:
                raise Exception("Não foi possível obter informações do vídeo (info_dict vazio)")
            video_title = info_dict.get('title', 'Video sem título')
            possible_files = glob.glob(f'audios/audio_{download_id}.*')
            if not possible_files:
                raise Exception("Arquivo de áudio não foi criado após o download (yt-dlp principal)")
            actual_file = possible_files[0]
            print(f"Download (Tentativa 1) concluído com sucesso: {actual_file}")
            return actual_file, video_title
    except Exception as e:
        print(f"Tentativa 1 (yt-dlp principal) falhou: {e}")
        last_error = e

    # --- Tentativa 2: pytube ---
    if last_error: # Só tenta se a anterior falhou
        print("Tentando download alternativo (Tentativa 2 - pytube)...")
        try:
            # (Código de baixar_audio_youtube_pytube adaptado)
            yt = pytube.YouTube(url)
            video_title = yt.title
            audio_stream = yt.streams.filter(only_audio=True).first()
            if not audio_stream:
                raise Exception("Nenhum stream de áudio disponível (pytube)")
            filename_pytube = audio_stream.download(output_path='audios', filename=f"audio_{download_id}_pytube") # Nome diferente para evitar conflito
            if not os.path.exists(filename_pytube):
                 raise Exception(f"Falha ao baixar o arquivo (pytube): {filename_pytube}")
            output_mp3 = f"audios/audio_{download_id}.mp3"
            if not filename_pytube.endswith('.mp3'):
                print(f"Convertendo para MP3 (pytube): {filename_pytube} -> {output_mp3}")
                comando = f'ffmpeg -y -i "{filename_pytube}" -vn -acodec mp3 "{output_mp3}"'
                os.system(comando)
                if os.path.exists(output_mp3):
                    os.remove(filename_pytube)
                    actual_file = output_mp3
                else:
                     raise Exception("Falha na conversão para MP3 (pytube)")
            else:
                # Se já for mp3 (raro), renomeia para o padrão
                os.rename(filename_pytube, output_mp3)
                actual_file = output_mp3
            print(f"Download (Tentativa 2 - pytube) concluído com sucesso: {actual_file}")
            return actual_file, video_title
        except Exception as e_pytube:
            print(f"Tentativa 2 (pytube) falhou: {e_pytube}")
            last_error = e_pytube

    # --- Tentativa 3: yt-dlp (Alternativo com lista de formatos) ---
    if last_error: # Só tenta se as anteriores falharam
        print("Tentando download alternativo (Tentativa 3 - yt-dlp com lista de formatos)...")
        try:
            # Primeiro, listar os formatos disponíveis
            list_opts = {
                'listformats': True,
                'quiet': False,
                'no_warnings': False,
                'geo_bypass': True,
                'nocheckcertificate': True,
            }
            with yt_dlp.YoutubeDL(list_opts) as ydl_list:
                print("Listando formatos disponíveis...")
                info = ydl_list.extract_info(url, download=False)
                
            # Tenta baixar com formato específico (começando pelo áudio)
            alt_opts = {
                'format': '140/bestaudio/best', # Tenta formato 140 (m4a) primeiro, depois outros
                'outtmpl': f'audios/audio_{download_id}.%(ext)s',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                'noplaylist': True, 'geo_bypass': True, 'nocheckcertificate': True,
                'ignoreerrors': False, 'quiet': False, 'no_warnings': False,
                'socket_timeout': 30,
                'retries': 10,
                'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'},
            }
            with yt_dlp.YoutubeDL(alt_opts) as ydl_alt:
                info_dict = ydl_alt.extract_info(url, download=True)
                if not info_dict:
                     raise Exception("Não foi possível obter informações do vídeo (info_dict vazio - alt)")
                video_title = info_dict.get('title', 'Video sem título')
                possible_files = glob.glob(f'audios/audio_{download_id}.*')
                if not possible_files:
                    raise Exception("Arquivo de áudio não foi criado após o download (yt-dlp alternativo)")
                actual_file = possible_files[0]
                print(f"Download (Tentativa 3 - yt-dlp formato específico) concluído com sucesso: {actual_file}")
                return actual_file, video_title
        except Exception as e_alt:
            print(f"Tentativa 3 (yt-dlp formato específico) falhou: {e_alt}")
            last_error = e_alt
            
    # --- Tentativa 4: Usando YouTube API --- 
    if last_error:
        print("Tentando download final (Tentativa 4 - método direto)...")
        try:
            import urllib.request
            from urllib.parse import parse_qs, urlparse
            
            # Extrair video_id da URL
            query = urlparse(url)
            if query.hostname == 'youtu.be':
                video_id = query.path[1:]
            elif query.hostname in ('www.youtube.com', 'youtube.com'):
                if query.path == '/watch':
                    video_id = parse_qs(query.query)['v'][0]
                elif query.path[:7] == '/embed/':
                    video_id = query.path.split('/')[2]
                elif query.path[:3] == '/v/':
                    video_id = query.path.split('/')[2]
            else:
                video_id = None
                
            if not video_id:
                raise Exception("Não foi possível extrair o ID do vídeo da URL")
                
            # Usar API para obter o título
            api_url = f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&part=snippet&key=YOUR_API_KEY"
            video_title = f"Video {video_id}"  # Título padrão se não conseguir pela API
            
            # URL direta para o áudio (pode não funcionar para todos os vídeos)
            direct_url = f"https://www.youtube.com/get_video_info?video_id={video_id}"
            output_file = f"audios/audio_{download_id}.mp3"
            
            # Baixar usando urllib
            print(f"Tentando baixar diretamente: {direct_url}")
            req = urllib.request.Request(
                direct_url,
                data=None,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
                }
            )
            with urllib.request.urlopen(req) as response, open(output_file, 'wb') as out_file:
                data = response.read()
                out_file.write(data)
                
            if os.path.exists(output_file) and os.path.getsize(output_file) > 1000:  # Verificar se tem conteúdo
                print(f"Download (Tentativa 4 - método direto) concluído com sucesso: {output_file}")
                return output_file, video_title
            else:
                raise Exception("Arquivo baixado parece estar vazio ou é muito pequeno")
                
        except Exception as e_direct:
            print(f"Tentativa 4 (método direto) falhou: {e_direct}")
            last_error = e_direct

    # --- Falha Total ---
    print(f"Todas as tentativas de download para {url} falharam.")
    # Levanta a última exceção ocorrida para ser tratada pela função chamadora
    raise last_error

def extrair_audio_video(caminho_video):
    try:
        # Gera um ID único para o arquivo
        file_id = str(uuid.uuid4())
        nome_arquivo = os.path.splitext(os.path.basename(caminho_video))[0]
        extensao_original = os.path.splitext(caminho_video)[1].lower()
        
        # Se já for um arquivo WAV, apenas copia para o diretório de áudios
        if extensao_original == '.wav':
            nome_audio = f"{nome_arquivo}_{file_id}.wav"
            caminho_audio = os.path.join('audios', nome_audio)
            # Copia o arquivo WAV
            shutil.copy2(caminho_video, caminho_audio)
        else:
            # Para outros formatos, converte para MP3
            nome_audio = f"{nome_arquivo}_{file_id}.mp3"
            caminho_audio = os.path.join('audios', nome_audio)
            comando = f'ffmpeg -y -i "{caminho_video}" -vn -acodec mp3 "{caminho_audio}"'
            os.system(comando)
        
        return caminho_audio, nome_arquivo
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def salvar_transcricao_parcial(transcricao_id, texto, concluido=False):
    """Salva a transcrição parcial em um arquivo"""
    caminho = f"transcricoes/{transcricao_id}.json"
    dados = {
        "texto": texto,
        "timestamp": datetime.now().isoformat(),
        "concluido": concluido
    }
    
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    
    return caminho

def carregar_transcricao_parcial(transcricao_id):
    """Carrega uma transcrição parcial salva anteriormente"""
    caminho = f"transcricoes/{transcricao_id}.json"
    if os.path.exists(caminho):
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

async def transcrever_audio_em_chunks(caminho_audio, client_id, transcricao_id, titulo, idioma='pt'):
    """Transcreve o áudio em chunks e envia atualizações via WebSocket com sistema de retomada aprimorado"""
    try:
        if not modelo_atual:
            raise Exception("Modelo não carregado")
        
        # Verifica se a conexão ainda está ativa antes de começar
        if not manager.is_connected(client_id):
            print(f"Conexão WebSocket inativa para {client_id}, abortando transcrição")
            return None
        
        # Notifica o cliente que o processamento começou
        sent = await manager.send_message(json.dumps({
            "tipo": "status",
            "mensagem": f"Preparando áudio para transcrição ({modelo_atual_nome})..."
        }), client_id)
        
        if not sent:
            print("Falha ao enviar mensagem inicial, abortando transcrição")
            return None
        
        # Verifica se há uma transcrição parcial salva e se está realmente completa
        transcricao_parcial = carregar_transcricao_parcial(transcricao_id)
        texto_atual = ""
        
        # CORREÇÃO PRINCIPAL: Só usa transcrição parcial se for uma retomada legítima
        if transcricao_parcial and transcricao_parcial.get("concluido", False):
            # Se já está concluída, retorna o resultado salvo
            texto_completo = transcricao_parcial["texto"]
            print(f"Transcrição {transcricao_id} já estava completa, usando resultado salvo")
            
            # Atualiza interface diretamente para 100%
            await manager.send_message(json.dumps({
                "tipo": "transcricao_parcial", 
                "texto": texto_completo,
                "progresso": 100,
                "transcricao_id": transcricao_id,
                "titulo": titulo,
                "etapa": "Transcrição já concluída"
            }), client_id)
            
            # Marca como concluída
            transcricoes_ativas[transcricao_id]["status"] = "concluida"
            transcricoes_ativas[transcricao_id]["texto"] = texto_completo
            
            await manager.send_message(json.dumps({
                "tipo": "transcricao_concluida", 
                "transcricao_id": transcricao_id,
                "titulo": titulo,
                "tempo_processamento": "0.0s (cache)"
            }), client_id)
            
            return texto_completo
        
        elif transcricao_parcial and not transcricao_parcial.get("concluido", False):
            # Se há transcrição parcial incompleta, mostra progresso parcial mas refaz
            texto_atual = transcricao_parcial["texto"]
            print(f"Encontrada transcrição parcial para {transcricao_id}, mas refazendo processamento")
            
            await manager.send_message(json.dumps({
                "tipo": "transcricao_parcial", 
                "texto": texto_atual,
                "progresso": 25,  # Progresso parcial
                "transcricao_id": transcricao_id,
                "titulo": titulo,
                "etapa": "Retomando processamento..."
            }), client_id)
        
        # Verifica conexão antes de iniciar processamento pesado
        if not manager.is_connected(client_id):
            print(f"Conexão perdida durante preparação para {client_id}")
            return None
        
        # Notifica sobre o início da transcrição
        await manager.send_message(json.dumps({
            "tipo": "status",
            "mensagem": f"Iniciando transcrição com modelo {modelo_atual_nome}..."
        }), client_id)
        
        # Notifica o processamento de áudio
        await manager.send_message(json.dumps({
            "tipo": "transcricao_parcial", 
            "texto": "",
            "progresso": 30,
            "transcricao_id": transcricao_id,
            "titulo": titulo,
            "etapa": "Processando áudio"
        }), client_id)
        
        # Verifica conexão antes do processamento principal
        if not manager.is_connected(client_id):
            print(f"Conexão perdida antes do processamento principal para {client_id}")
            return None
        
        # Inicia a transcrição efetivamente
        tempo_inicio = time.time()
        print(f"Iniciando transcrição Whisper para {transcricao_id}")
        
        # PROCESSAMENTO PRINCIPAL - sempre executa para garantir resultado completo
        transcricao = modelo_atual.transcribe(caminho_audio, language=idioma)
        tempo_total = time.time() - tempo_inicio
        texto_completo = transcricao['text']
        
        print(f"Transcrição Whisper concluída para {transcricao_id} em {tempo_total:.1f}s")
        
        # Verifica conexão após processamento
        if not manager.is_connected(client_id):
            print(f"Conexão perdida após processamento para {client_id}, salvando resultado")
            # Salva o resultado mesmo se a conexão caiu
            salvar_transcricao_parcial(transcricao_id, texto_completo, True)
            transcricoes_ativas[transcricao_id]["status"] = "concluida"
            transcricoes_ativas[transcricao_id]["texto"] = texto_completo
            return texto_completo
        
        # Simula processamento em chunks para mostrar progresso
        pontos = [50, 70, 85, 95, 100]
        
        for i, ponto in enumerate(pontos):
            # Verifica conexão antes de cada envio
            if not manager.is_connected(client_id):
                print(f"Conexão perdida durante envio de progresso para {client_id}")
                break
                
            if ponto == 100:
                texto_atual = texto_completo
                etapa = "Transcrição completa"
            else:
                # Mostra progresso gradual do texto
                char_position = int((ponto/100) * len(texto_completo))
                texto_atual = texto_completo[:char_position]
                etapa = f"Finalizando transcrição ({i+1}/{len(pontos)})"
            
            # Salva transcrição parcial
            salvar_transcricao_parcial(transcricao_id, texto_atual, ponto == 100)
            
            # Envia atualização se conexão ativa
            success = await manager.send_message(json.dumps({
                "tipo": "transcricao_parcial", 
                "texto": texto_atual,
                "progresso": ponto,
                "transcricao_id": transcricao_id,
                "titulo": titulo,
                "etapa": etapa,
                "tempo_processamento": f"{tempo_total:.1f}s"
            }), client_id)
            
            if not success:
                print(f"Falha ao enviar progresso {ponto}% para {client_id}")
                break
            
            # Pausa menor para mostrar progresso
            await asyncio.sleep(0.3)
        
        # Marca como concluída sempre (independente da conexão)
        transcricoes_ativas[transcricao_id]["status"] = "concluida"
        transcricoes_ativas[transcricao_id]["texto"] = texto_completo
        
        # Tenta enviar mensagem de conclusão
        await manager.send_message(json.dumps({
            "tipo": "transcricao_concluida", 
            "transcricao_id": transcricao_id,
            "titulo": titulo,
            "tempo_processamento": f"{tempo_total:.1f}s"
        }), client_id)
        
        global ultima_transcricao
        ultima_transcricao = texto_completo
        
        print(f"Transcrição {transcricao_id} concluída com sucesso")
        return texto_completo
        
    except Exception as e:
        # Marca como falha
        if transcricao_id in transcricoes_ativas:
            transcricoes_ativas[transcricao_id]["status"] = "falha"
            transcricoes_ativas[transcricao_id]["erro"] = str(e)
        
        # Tenta notificar o cliente sobre o erro
        await manager.send_message(json.dumps({
            "tipo": "erro", 
            "mensagem": f"Erro na transcrição: {str(e)}",
            "transcricao_id": transcricao_id
        }), client_id)
        
        print(f"Erro na transcrição {transcricao_id}: {str(e)}")
        return None

def transcrever_audio(caminho_audio, idioma='pt'):
    """Versão síncrona para compatibilidade com código existente"""
    try:
        if not modelo_atual:
            raise Exception("Modelo não carregado")
        resultado = modelo_atual.transcribe(caminho_audio, language=idioma)
        return resultado['text']
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Define o modelo para o corpo da requisição de insights
class InsightsRequest(BaseModel):
    transcricao_id: Optional[str] = None
    pergunta: str

def gerar_insights(texto: str, pergunta_usuario: str):
    """Gera insights usando a API OpenRouter com base na pergunta do usuário"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Aviso: Chave API do OpenRouter não configurada. Não será possível gerar insights.")
        return "Chave API do OpenRouter não configurada."

    # Construir o prompt dinâmico
    prompt = f"""
    Com base na seguinte transcrição, responda à pergunta do usuário da melhor forma possível.

    Transcrição:
    ---
    {texto}
    ---

    Pergunta do Usuário:
    {pergunta_usuario}

    Resposta:
    """

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}"
            },
            json={
                "model": "google/gemini-2.5-flash-preview", # Modelo atualizado
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
        )
        response.raise_for_status() # Levanta erro para status HTTP 4xx/5xx
        data = response.json()
        
        # Verificação robusta da resposta da API
        if data.get('choices') and len(data['choices']) > 0:
            if data['choices'][0].get('message') and data['choices'][0]['message'].get('content'):
                return data['choices'][0]['message']['content']
            else:
                print(f"Resposta da API malformada (faltando message/content): {data}")
                return "Erro: Resposta da API inválida."
        else:
            print(f"Resposta da API malformada (faltando choices): {data}")
            return "Erro: Resposta da API inválida."
            
    except requests.exceptions.RequestException as e:
        print(f"Erro ao chamar a API OpenRouter: {e}")
        error_detail = str(e)
        if e.response is not None:
            try:
                # Tenta obter detalhes do corpo da resposta do erro, se houver
                error_detail = f"{e} - {e.response.text}"
            except Exception:
                pass # Ignora se não conseguir ler o corpo da resposta
        return f"Erro ao gerar insights: {error_detail}"
    except Exception as e:
        print(f"Erro inesperado ao gerar insights: {e}")
        return f"Erro inesperado ao gerar insights."

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "modelos": MODELOS,
        "modelo_atual": modelo_atual_nome
    })

@app.get("/modelos")
async def listar_modelos():
    return {"modelos": MODELOS}

@app.post("/mudar-modelo/{nome_modelo}")
async def mudar_modelo(nome_modelo: str):
    if nome_modelo not in MODELOS:
        raise HTTPException(status_code=400, detail="Modelo não disponível")
    
    if carregar_modelo(nome_modelo):
        return {"status": "success", "modelo": nome_modelo}
    else:
        raise HTTPException(status_code=500, detail="Erro ao carregar modelo")

@app.post("/iniciar-transcricao-youtube")
async def iniciar_transcricao_youtube(url: str = Form(...), background_tasks: BackgroundTasks = None):
    try:
        client_id = str(uuid.uuid4())
        transcricao_id = str(uuid.uuid4())
        
        # Registra a transcrição como "em andamento"
        transcricoes_ativas[transcricao_id] = {
            "client_id": client_id,
            "tipo": "youtube",
            "url": url,
            "status": "em_andamento",
            "iniciado_em": datetime.now().isoformat()
        }
        
        return {
            "status": "iniciado", 
            "client_id": client_id, 
            "transcricao_id": transcricao_id,
            "message": "Transcrição iniciada. Conecte-se ao WebSocket para receber atualizações."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/iniciar-transcricao-arquivo")
async def iniciar_transcricao_arquivo(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    try:
        client_id = str(uuid.uuid4())
        transcricao_id = str(uuid.uuid4())
        
        # Salva o arquivo temporariamente
        temp_path = f"videos/{transcricao_id}_{file.filename}"
        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Registra a transcrição como "em andamento"
        transcricoes_ativas[transcricao_id] = {
            "client_id": client_id,
            "tipo": "arquivo",
            "caminho": temp_path,
            "nome_arquivo": file.filename,
            "status": "em_andamento",
            "iniciado_em": datetime.now().isoformat()
        }
        
        return {
            "status": "iniciado", 
            "client_id": client_id, 
            "transcricao_id": transcricao_id,
            "message": "Transcrição iniciada. Conecte-se ao WebSocket para receber atualizações."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcricoes")
async def listar_transcricoes():
    return {"transcricoes": transcricoes_ativas}

@app.get("/transcricao/{transcricao_id}")
async def obter_transcricao(transcricao_id: str):
    # Verifica se a transcrição existe na lista de ativas
    if transcricao_id not in transcricoes_ativas:
        # Se não estiver nas ativas, verifica se existe um arquivo salvo
        caminho = f"transcricoes/{transcricao_id}.json"
        if os.path.exists(caminho):
            try:
                with open(caminho, 'r', encoding='utf-8') as f:
                    dados_arquivo = json.load(f)
                    
                # Recria o registro da transcrição com os dados básicos
                transcricoes_ativas[transcricao_id] = {
                    "status": "falha",  # Assume que foi interrompida
                    "texto": dados_arquivo.get("texto", ""),
                    "iniciado_em": dados_arquivo.get("timestamp", datetime.now().isoformat()),
                    "tipo": "desconhecido",
                    "titulo": "Transcrição Recuperada",
                    "concluido": dados_arquivo.get("concluido", False)
                }
                
                return transcricoes_ativas[transcricao_id]
            except Exception as e:
                print(f"Erro ao recuperar transcrição do arquivo: {str(e)}")
                raise HTTPException(status_code=404, detail="Transcrição não encontrada ou corrompida")
        else:
            raise HTTPException(status_code=404, detail="Transcrição não encontrada")
    
    dados = transcricoes_ativas[transcricao_id]
    
    # Carrega a transcrição do arquivo
    transcricao = carregar_transcricao_parcial(transcricao_id)
    if transcricao:
        dados["texto"] = transcricao["texto"]
        dados["concluido"] = transcricao["concluido"]
    
    return dados

@app.post("/retomar-transcricao/{transcricao_id}")
async def retomar_transcricao(transcricao_id: str):
    print(f"Tentativa de retomar transcrição: {transcricao_id}")
    
    # Verifica se a transcrição existe na lista de ativas
    if transcricao_id not in transcricoes_ativas:
        # Tenta recuperar do arquivo
        caminho = f"transcricoes/{transcricao_id}.json"
        if os.path.exists(caminho):
            try:
                with open(caminho, 'r', encoding='utf-8') as f:
                    dados_arquivo = json.load(f)
                
                # Se a transcrição já está concluída no arquivo, não precisa retomar
                if dados_arquivo.get("concluido", False):
                    print(f"Transcrição {transcricao_id} já estava concluída")
                    transcricoes_ativas[transcricao_id] = {
                        "status": "concluida",
                        "texto": dados_arquivo.get("texto", ""),
                        "iniciado_em": dados_arquivo.get("timestamp", datetime.now().isoformat()),
                        "tipo": "arquivo_recuperado",
                        "titulo": "Transcrição Recuperada (Completa)",
                        "concluido": True
                    }
                    
                    # Retorna status concluído
                    return {
                        "status": "concluida",
                        "transcricao_id": transcricao_id,
                        "message": "Transcrição já estava concluída.",
                        "texto": dados_arquivo.get("texto", "")
                    }
                
                # Recria o registro da transcrição para retomada
                transcricoes_ativas[transcricao_id] = {
                    "status": "falha",  # Marca como falha para poder retomar
                    "texto": dados_arquivo.get("texto", ""),
                    "iniciado_em": dados_arquivo.get("timestamp", datetime.now().isoformat()),
                    "tipo": "arquivo_recuperado",
                    "titulo": "Transcrição Recuperada",
                    "progresso_anterior": len(dados_arquivo.get("texto", "")) > 0,
                    "dados_salvos": dados_arquivo  # Preserva dados originais
                }
                
                print(f"Transcrição {transcricao_id} recuperada do arquivo para retomada")
                print(f"Texto parcial encontrado: {len(dados_arquivo.get('texto', ''))} caracteres")
                
            except Exception as e:
                print(f"Erro ao recuperar transcrição do arquivo para retomada: {str(e)}")
                raise HTTPException(status_code=404, detail="Transcrição não encontrada ou corrompida")
        else:
            raise HTTPException(status_code=404, detail="Transcrição não encontrada")
    
    transcricao = transcricoes_ativas[transcricao_id]
    
    # Verifica se podemos retomar
    if transcricao["status"] == "concluida":
        print(f"Transcrição {transcricao_id} já está concluída")
        return {
            "status": "concluida",
            "transcricao_id": transcricao_id,
            "message": "Transcrição já está concluída.",
            "texto": transcricao.get("texto", "")
        }
    
    if transcricao["status"] not in ["falha", "cancelada"] and not transcricao.get("progresso_anterior", False):
        raise HTTPException(status_code=400, detail=f"Não é possível retomar transcrição com status: {transcricao['status']}")
    
    # Preserva informações importantes para a retomada
    dados_anteriores = {
        "texto_parcial": transcricao.get("texto", ""),
        "titulo_anterior": transcricao.get("titulo", ""),
        "tipo_original": transcricao.get("tipo", ""),
        "url_original": transcricao.get("url", ""),
        "caminho_original": transcricao.get("caminho", ""),
        "nome_arquivo_original": transcricao.get("nome_arquivo", "")
    }
    
    # Atualiza o status para retomada
    transcricao["status"] = "preparando_retomada"
    transcricao["dados_anteriores"] = dados_anteriores
    
    # Retorna um novo client_id para reconexão
    novo_client_id = str(uuid.uuid4())
    transcricao["client_id"] = novo_client_id
    
    print(f"Retomando transcrição {transcricao_id} com novo client_id {novo_client_id}")
    print(f"Dados anteriores preservados: {dados_anteriores}")
    
    return {
        "status": "preparando_retomada", 
        "client_id": novo_client_id, 
        "transcricao_id": transcricao_id,
        "message": "Transcrição preparada para retomada. Conecte-se ao WebSocket para receber atualizações.",
        "progresso_anterior": transcricao.get("progresso_anterior", False),
        "texto_parcial": dados_anteriores["texto_parcial"]
    }

@app.post("/generate-insights")
async def generate_insights_endpoint(request_data: InsightsRequest):
    """Gera insights a partir de uma transcrição concluída, com base na pergunta do usuário."""
    global ultima_transcricao

    texto_para_analise = None
    transcricao_id = request_data.transcricao_id
    pergunta = request_data.pergunta

    if not pergunta or not pergunta.strip(): # Verifica se a pergunta não está vazia
         raise HTTPException(status_code=400, detail="A pergunta do usuário não pode estar vazia.")

    if transcricao_id:
        # Tenta carregar a transcrição final
        caminho_final = TRANSCRIPTION_DIR / f"{transcricao_id}.txt"
        if caminho_final.exists():
             with open(caminho_final, 'r', encoding='utf-8') as f:
                 texto_para_analise = f.read()
        else:
            # Tenta carregar a transcrição parcial se a final não existir
            parcial = carregar_transcricao_parcial(transcricao_id)
            if parcial and parcial['texto']:
                texto_para_analise = parcial['texto']
                print(f"Aviso: Usando transcrição parcial para ID {transcricao_id} para gerar insights.")
            else:
                 raise HTTPException(status_code=404, detail=f"Transcrição com ID {transcricao_id} não encontrada.")
    elif ultima_transcricao:
        texto_para_analise = ultima_transcricao
        print("Aviso: Usando a última transcrição global para gerar insights, pois nenhum ID foi fornecido.")
    else:
        raise HTTPException(status_code=400, detail="Nenhuma transcrição disponível. Forneça um ID ou realize uma transcrição primeiro.")

    if not texto_para_analise:
         # Adicionado para robustez, embora as verificações anteriores devam cobrir isso
         raise HTTPException(status_code=404, detail="Texto da transcrição está vazio ou não pôde ser carregado.")

    # Chama a função para gerar insights com a pergunta
    insights = gerar_insights(texto_para_analise, pergunta)
    return {"insights": insights}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    transcricao_id = None
    try:
        await manager.connect(websocket, client_id)
        print(f"Cliente WebSocket conectado: {client_id}")
        
        # Busca transcrição associada a este client_id
        for tid, info in transcricoes_ativas.items():
            if info.get("client_id") == client_id:
                transcricao_id = tid
                manager.set_transcricao_id(client_id, transcricao_id)
                break
        
        if not transcricao_id:
            await manager.send_message(json.dumps({
                "tipo": "erro",
                "mensagem": "Nenhuma transcrição associada a este cliente"
            }), client_id)
            return
        
        info = transcricoes_ativas[transcricao_id]
        print(f"Transcrição associada: {transcricao_id}, Status: {info.get('status', 'desconhecido')}")
        
        # Verifica o status atual
        if info["status"] in ["concluida", "falha"]:
            # Se já concluiu ou falhou, envia o status
            await manager.send_message(json.dumps({
                "tipo": info["status"],
                "transcricao_id": transcricao_id
            }), client_id)
            
            # Se concluída, envia o texto
            if info["status"] == "concluida" and "texto" in info:
                await manager.send_message(json.dumps({
                    "tipo": "transcricao_parcial",
                    "texto": info["texto"],
                    "progresso": 100,
                    "transcricao_id": transcricao_id
                }), client_id)
            
            return
        
        # Atualiza status para processamento
        transcricoes_ativas[transcricao_id]["status"] = "processando"
        
        # Realiza a transcrição em background
        if info["tipo"] == "youtube":
            # Notifica que está baixando o vídeo do YouTube
            await manager.send_message(json.dumps({
                "tipo": "baixando",
                "mensagem": "Baixando áudio do YouTube...",
                "progresso": 10,
                "transcricao_id": transcricao_id
            }), client_id)
            
            # Baixa o áudio do YouTube
            try:
                caminho_audio, titulo = await asyncio.to_thread(baixar_audio_youtube, info["url"])
                
                # Verifica se conexão ainda está ativa após download
                if not manager.is_connected(client_id):
                    print(f"Conexão perdida após download para {client_id}")
                    return
                
                # Atualiza o título na transcrição
                transcricoes_ativas[transcricao_id]["titulo"] = titulo
                
                # Notifica que o download foi concluído
                await manager.send_message(json.dumps({
                    "tipo": "preparando",
                    "mensagem": f"Áudio baixado com sucesso: {titulo}",
                    "progresso": 20,
                    "transcricao_id": transcricao_id
                }), client_id)
                
                # Inicia a transcrição SEM create_task para melhor controle
                await transcrever_audio_em_chunks(caminho_audio, client_id, transcricao_id, titulo)
                
            except Exception as e:
                # Atualiza o status da transcrição
                transcricoes_ativas[transcricao_id]["status"] = "falha"
                transcricoes_ativas[transcricao_id]["erro"] = str(e)
                
                # Notifica o cliente sobre o erro
                await manager.send_message(json.dumps({
                    "tipo": "erro", 
                    "mensagem": f"Erro ao baixar áudio do YouTube: {str(e)}",
                    "transcricao_id": transcricao_id
                }), client_id)
                print(f"Erro no download do YouTube para {transcricao_id}: {e}")
            
        elif info["tipo"] == "arquivo":
            # Notifica que está extraindo o áudio
            await manager.send_message(json.dumps({
                "tipo": "preparando",
                "mensagem": "Extraindo áudio do vídeo...",
                "progresso": 15,
                "transcricao_id": transcricao_id
            }), client_id)
            
            # Extrai áudio do vídeo
            try:
                caminho_audio, titulo = await asyncio.to_thread(extrair_audio_video, info["caminho"])
                
                # Verifica se conexão ainda está ativa após extração
                if not manager.is_connected(client_id):
                    print(f"Conexão perdida após extração para {client_id}")
                    return
                
                # Atualiza o título na transcrição
                transcricoes_ativas[transcricao_id]["titulo"] = titulo
                
                # Notifica que a extração foi concluída
                await manager.send_message(json.dumps({
                    "tipo": "preparando",
                    "mensagem": f"Áudio extraído com sucesso: {info['nome_arquivo']}",
                    "progresso": 25,
                    "transcricao_id": transcricao_id
                }), client_id)
                
                # Inicia a transcrição SEM create_task para melhor controle
                await transcrever_audio_em_chunks(caminho_audio, client_id, transcricao_id, titulo)
                
            except Exception as e:
                transcricoes_ativas[transcricao_id]["status"] = "falha"
                transcricoes_ativas[transcricao_id]["erro"] = str(e)
                
                await manager.send_message(json.dumps({
                    "tipo": "erro", 
                    "mensagem": f"Erro ao extrair áudio do vídeo: {str(e)}",
                    "transcricao_id": transcricao_id
                }), client_id)
                print(f"Erro na extração de áudio para {transcricao_id}: {e}")
        
        # Mantém a conexão aberta para receber comandos do cliente
        while manager.is_connected(client_id):
            try:
                # Timeout para evitar bloqueio infinito
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                cmd = json.loads(data)
                
                if cmd["acao"] == "cancelar":
                    # Cancela a transcrição
                    transcricoes_ativas[transcricao_id]["status"] = "cancelada"
                    await manager.send_message(json.dumps({
                        "tipo": "cancelada",
                        "transcricao_id": transcricao_id
                    }), client_id)
                    break
                    
            except asyncio.TimeoutError:
                # Timeout normal, continua o loop
                continue
            except WebSocketDisconnect:
                print(f"Cliente {client_id} desconectou durante loop de comandos")
                break
    
    except WebSocketDisconnect:
        print(f"Cliente {client_id} desconectou")
        # Cliente desconectou mas a transcrição pode continuar em background
        if transcricao_id and transcricao_id in transcricoes_ativas:
            if transcricoes_ativas[transcricao_id]["status"] in ["em_andamento", "processando"]:
                print(f"Transcrição {transcricao_id} continua em background após desconexão")
    except Exception as e:
        print(f"Erro no WebSocket para {client_id}: {e}")
        # Qualquer erro, tenta enviar ao cliente se possível
        try:
            await manager.send_message(json.dumps({
                "tipo": "erro",
                "mensagem": str(e)
            }), client_id)
        except:
            pass
    finally:
        print(f"Finalizando conexão WebSocket: {client_id}")
        manager.disconnect(client_id)

# Rotas antigas para compatibilidade
@app.post("/transcribe-youtube")
async def transcribe_youtube(url: str = Form(...)):
    try:
        audio, _ = baixar_audio_youtube(url)
        texto = transcrever_audio(audio)
        global ultima_transcricao
        ultima_transcricao = texto
        return {"transcription": texto}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe-file")
async def transcribe_file(file: UploadFile = File(...)):
    try:
        # Salva o arquivo temporariamente
        temp_path = f"videos/{file.filename}"
        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Extrai o áudio
        audio, _ = extrair_audio_video(temp_path)
        texto = transcrever_audio(audio)
        
        # Limpa arquivos temporários
        os.remove(temp_path)
        if os.path.exists(audio):
            os.remove(audio)
            
        global ultima_transcricao
        ultima_transcricao = texto
        return {"transcription": texto}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe/")
async def transcribe_file(file: UploadFile = File(...)):
    """
    Endpoint para transcrever um arquivo de áudio/vídeo
    """
    # Salva o arquivo enviado
    file_path = UPLOAD_DIR / file.filename
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo: {str(e)}")
    
    # Nome do arquivo de transcrição
    transcription_path = TRANSCRIPTION_DIR / f"{file_path.stem}.txt"
    
    try:
        # Transcreve o arquivo
        text = audio_manager.transcribe_and_save(
            str(file_path),
            str(transcription_path)
        )
        
        return {
            "message": "Transcrição concluída com sucesso",
            "text": text,
            "transcription_file": transcription_path.name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na transcrição: {str(e)}")
    finally:
        # Limpa o arquivo enviado
        file_path.unlink(missing_ok=True)

@app.post("/text-to-speech/")
async def text_to_speech(request: Request):
    """
    Endpoint para converter texto em fala usando edge-tts
    """
    try:
        # Recebe o texto do corpo da requisição JSON
        data = await request.json()
        text = data.get('text')
        
        if not text:
            raise HTTPException(status_code=400, detail="Texto não fornecido")
        
        # Gera um nome único para o arquivo de áudio
        audio_path = AUDIO_DIR / f"audio_{len(os.listdir(AUDIO_DIR))}.mp3"
        
        # Gera o áudio
        await audio_manager.generate_speech(text, str(audio_path))
        
        # Retorna o arquivo de áudio
        return FileResponse(
            str(audio_path),
            media_type="audio/mpeg",
            filename=audio_path.name
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na geração de áudio: {str(e)}")

@app.post("/transcribe-and-speak/")
async def transcribe_and_speak(file: UploadFile = File(...)):
    """
    Endpoint para transcrever um arquivo e gerar áudio da transcrição usando edge-tts
    """
    # Salva o arquivo enviado
    file_path = UPLOAD_DIR / file.filename
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo: {str(e)}")
    
    try:
        # Transcreve o arquivo
        text = audio_manager.transcribe_and_save(str(file_path))
        
        # Gera um nome único para o arquivo de áudio
        audio_path = AUDIO_DIR / f"audio_{len(os.listdir(AUDIO_DIR))}.mp3"
        
        # Gera o áudio
        await audio_manager.generate_speech(text, str(audio_path))
        
        return {
            "message": "Processamento concluído com sucesso",
            "transcription": text,
            "audio_file": audio_path.name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no processamento: {str(e)}")
    finally:
        # Limpa o arquivo enviado
        file_path.unlink(missing_ok=True)

@app.get("/get-audio/{filename}")
async def get_audio(filename: str):
    """
    Endpoint para baixar um arquivo de áudio gerado
    """
    audio_path = AUDIO_DIR / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    return FileResponse(
        str(audio_path),
        media_type="audio/mpeg",
        filename=filename
    )

if __name__ == "__main__":
    criar_diretorios() 