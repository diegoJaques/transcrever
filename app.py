from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
from pydantic import BaseModel
from typing import Optional

# Carrega variáveis de ambiente
load_dotenv()

app = FastAPI()

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

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_message(self, message: str, client_id: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(message)

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

def baixar_audio_youtube_pytube(url):
    """Método alternativo para baixar áudio do YouTube usando pytube"""
    try:
        # Cria diretório audios se não existir
        os.makedirs('audios', exist_ok=True)
        
        # Gera um ID único para o download
        download_id = str(uuid.uuid4())
        
        print(f"Iniciando download com pytube: {url}")
        
        # Cria o objeto YouTube
        yt = pytube.YouTube(url)
        
        # Obtém o título do vídeo
        video_title = yt.title
        print(f"Título: {video_title}")
        
        # Seleciona o stream de áudio com maior qualidade
        audio_stream = yt.streams.filter(only_audio=True).first()
        if not audio_stream:
            raise Exception("Nenhum stream de áudio disponível para este vídeo")
            
        # Baixa o arquivo
        print(f"Baixando stream: {audio_stream}")
        filename = audio_stream.download(output_path='audios', filename=f"audio_{download_id}")
        
        # Verifica se o download foi bem-sucedido
        if not os.path.exists(filename):
            raise Exception(f"Falha ao baixar o arquivo: {filename}")
            
        print(f"Arquivo baixado: {filename}")
        
        # Converter para MP3 se não for MP3
        output_mp3 = f"audios/audio_{download_id}.mp3"
        if not filename.endswith('.mp3'):
            print(f"Convertendo para MP3: {filename} -> {output_mp3}")
            comando = f'ffmpeg -y -i "{filename}" -vn -acodec mp3 "{output_mp3}"'
            os.system(comando)
            
            # Verifica se a conversão foi bem-sucedida
            if os.path.exists(output_mp3):
                # Remove o arquivo original
                os.remove(filename)
                filename = output_mp3
            else:
                print(f"Aviso: Falha na conversão para MP3. Usando o arquivo original.")
        
        print(f"Download com pytube concluído: {filename}")
        return filename, video_title
        
    except Exception as e:
        print(f"Erro ao baixar com pytube: {str(e)}")
        raise Exception(f"Falha no download com pytube: {str(e)}")

def baixar_audio_youtube(url):
    try:
        # Cria diretório audios se não existir
        os.makedirs('audios', exist_ok=True)
        
        # Gera um ID único para o download
        download_id = str(uuid.uuid4())
        filename = f"audios/audio_{download_id}.mp3"
        
        print(f"Iniciando download do YouTube: {url}")
        
        # Configuração robusta para contornar restrições
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'audios/audio_{download_id}.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'geo_bypass_ip_block': '8.8.8.8',
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'noplaylist': True,  # Apenas o vídeo, não a playlist inteira
            'source_address': '0.0.0.0',
            'force_generic_extractor': False,
            'sleep_interval': 1,  # Espera entre requisições
            'max_sleep_interval': 5,
            'external_downloader_args': ['-timeout', '10'],
            'extractor_retries': 5,
            'file_access_retries': 5,
            'fragment_retries': 5,
            'retry_sleep_functions': {'http': lambda n: 5},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Extraindo informações do vídeo...")
            try:
                info_dict = ydl.extract_info(url, download=True)
                if not info_dict:
                    raise Exception("Não foi possível obter informações do vídeo")
                
                video_title = info_dict.get('title', 'Video sem título')
                
                # Procura o arquivo gerado
                possible_files = glob.glob(f'audios/audio_{download_id}.*')
                if not possible_files:
                    raise Exception("Arquivo de áudio não foi criado após o download")
                    
                # Usa o primeiro arquivo encontrado (normalmente será o MP3)
                actual_file = possible_files[0]
                print(f"Arquivo criado: {actual_file}")
            
                print(f"Download concluído com sucesso: {actual_file}")
                return actual_file, video_title
            except Exception as e:
                print(f"Erro na extração de informações: {str(e)}")
                raise
        
    except Exception as e:
        print(f"Erro ao baixar vídeo: {str(e)}")
        
        # Tenta usar o método alternativo com pytube
        try:
            print("Tentando download alternativo com pytube...")
            return baixar_audio_youtube_pytube(url)
        except Exception as pytube_error:
            print(f"Erro no pytube: {str(pytube_error)}")
            
            # Tenta usar métodos alternativos do yt-dlp
            try:
                print("Tentando método alternativo de download com yt-dlp...")
                alt_opts = {
                    'format': 'bestaudio',
                    'outtmpl': f'audios/audio_{download_id}.%(ext)s',
                    'noplaylist': True,
                    'geo_bypass': True,
                    'nocheckcertificate': True,
                    'ignoreerrors': False,
                    'quiet': False,
                    'no_warnings': False,
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
                    },
                }
                
                with yt_dlp.YoutubeDL(alt_opts) as ydl:
                    info_dict = ydl.extract_info(url, download=True)
                    video_title = info_dict.get('title', 'Video sem título')
                    
                    # Procura o arquivo gerado
                    possible_files = glob.glob(f'audios/audio_{download_id}.*')
                    if possible_files:
                        actual_file = possible_files[0]
                        print(f"Download alternativo bem-sucedido: {actual_file}")
                        return actual_file, video_title
                    else:
                        raise Exception("Não foi possível baixar o vídeo com método alternativo")
                    
            except Exception as alt_e:
                print(f"Erro no método alternativo: {str(alt_e)}")
                # Propaga a última exceção ocorrida (alt_e ou pytube_error ou e)
                raise alt_e

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
    """Transcreve o áudio em chunks e envia atualizações via WebSocket"""
    try:
        if not modelo_atual:
            raise Exception("Modelo não carregado")
        
        # Notifica o cliente que o processamento começou
        await manager.send_message(json.dumps({
            "tipo": "status",
            "mensagem": f"Preparando áudio para transcrição ({modelo_atual_nome})..."
        }), client_id)
        
        # Verifica se há uma transcrição parcial salva
        transcricao_parcial = carregar_transcricao_parcial(transcricao_id)
        if transcricao_parcial and not transcricao_parcial["concluido"]:
            texto_atual = transcricao_parcial["texto"]
            await manager.send_message(json.dumps({
                "tipo": "transcricao_parcial", 
                "texto": texto_atual,
                "progresso": 50,  # Valor aproximado
                "transcricao_id": transcricao_id,
                "titulo": titulo,
                "etapa": "Retomando transcrição anterior"
            }), client_id)
        else:
            texto_atual = ""
        
        # Notifica sobre o início da transcrição
        await manager.send_message(json.dumps({
            "tipo": "status",
            "mensagem": f"Iniciando transcrição com modelo {modelo_atual_nome}..."
        }), client_id)
        
        # Para uma implementação real, podemos dividir o áudio em chunks
        # Aqui vamos usar o Whisper padrão mas com mais atualizações de status
        
        # Notifica o processamento de áudio
        await manager.send_message(json.dumps({
            "tipo": "transcricao_parcial", 
            "texto": "",
            "progresso": 5,
            "transcricao_id": transcricao_id,
            "titulo": titulo,
            "etapa": "Processando áudio"
        }), client_id)
        
        # Aguarda um pouco para permitir que a interface atualize
        await asyncio.sleep(1)
        
        # Inicia a transcrição - enviar status de detecção de idioma
        await manager.send_message(json.dumps({
            "tipo": "transcricao_parcial", 
            "texto": "",
            "progresso": 15,
            "transcricao_id": transcricao_id,
            "titulo": titulo,
            "etapa": "Detectando idioma"
        }), client_id)
        
        # Inicia a transcrição efetivamente
        tempo_inicio = time.time()
        transcricao = modelo_atual.transcribe(caminho_audio, language=idioma)
        tempo_total = time.time() - tempo_inicio
        texto_completo = transcricao['text']
        
        # Após completar o processo principal, faça atualizações graduais
        total_chars = len(texto_completo)
        
        # Se já temos uma transcrição parcial, enviamos somente as atualizações
        if not texto_atual:
            # Simulamos processamento em chunks para mostrar progresso
            pontos = [30, 50, 75, 90, 100]
            
            for i, ponto in enumerate(pontos):
                if ponto == 100:
                    texto_atual = texto_completo
                    etapa = "Transcrição completa"
                else:
                    char_position = int((ponto/100) * total_chars)
                    texto_atual = texto_completo[:char_position]
                    etapa = f"Transcrição em andamento ({i+1}/{len(pontos)-1})"
                
                # Salva transcrição parcial
                salvar_transcricao_parcial(transcricao_id, texto_atual, ponto == 100)
                
                # Envia atualização
                await manager.send_message(json.dumps({
                    "tipo": "transcricao_parcial", 
                    "texto": texto_atual,
                    "progresso": ponto,
                    "transcricao_id": transcricao_id,
                    "titulo": titulo,
                    "etapa": etapa,
                    "tempo_processamento": f"{tempo_total:.1f}s"
                }), client_id)
                
                # Simula tempo de processamento (mais rápido)
                await asyncio.sleep(0.5)
        else:
            # Se já temos uma transcrição parcial, enviamos a completa
            salvar_transcricao_parcial(transcricao_id, texto_completo, True)
            await manager.send_message(json.dumps({
                "tipo": "transcricao_parcial", 
                "texto": texto_completo,
                "progresso": 100,
                "transcricao_id": transcricao_id,
                "titulo": titulo,
                "etapa": "Transcrição completa"
            }), client_id)
        
        # Marca como concluída
        transcricoes_ativas[transcricao_id]["status"] = "concluida"
        transcricoes_ativas[transcricao_id]["texto"] = texto_completo
        
        # Envia mensagem de conclusão
        await manager.send_message(json.dumps({
            "tipo": "transcricao_concluida", 
            "transcricao_id": transcricao_id,
            "titulo": titulo,
            "tempo_processamento": f"{tempo_total:.1f}s"
        }), client_id)
        
        global ultima_transcricao
        ultima_transcricao = texto_completo
        
        return texto_completo
        
    except Exception as e:
        # Marca como falha
        if transcricao_id in transcricoes_ativas:
            transcricoes_ativas[transcricao_id]["status"] = "falha"
            transcricoes_ativas[transcricao_id]["erro"] = str(e)
        
        # Notifica o cliente sobre o erro
        await manager.send_message(json.dumps({
            "tipo": "erro", 
            "mensagem": f"Erro na transcrição: {str(e)}",
            "transcricao_id": transcricao_id
        }), client_id)
        
        print(f"Erro na transcrição: {str(e)}")
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
    # Verifica se a transcrição existe na lista de ativas
    if transcricao_id not in transcricoes_ativas:
        # Tenta recuperar do arquivo
        caminho = f"transcricoes/{transcricao_id}.json"
        if os.path.exists(caminho):
            try:
                with open(caminho, 'r', encoding='utf-8') as f:
                    dados_arquivo = json.load(f)
                
                # Recria o registro da transcrição com os dados básicos
                transcricoes_ativas[transcricao_id] = {
                    "status": "falha",  # Marca como falha para poder retomar
                    "texto": dados_arquivo.get("texto", ""),
                    "iniciado_em": dados_arquivo.get("timestamp", datetime.now().isoformat()),
                    "tipo": "desconhecido",
                    "titulo": "Transcrição Recuperada"
                }
                
                print(f"Transcrição {transcricao_id} recuperada do arquivo para retomada")
            except Exception as e:
                print(f"Erro ao recuperar transcrição do arquivo para retomada: {str(e)}")
                raise HTTPException(status_code=404, detail="Transcrição não encontrada ou corrompida")
        else:
            raise HTTPException(status_code=404, detail="Transcrição não encontrada")
    
    transcricao = transcricoes_ativas[transcricao_id]
    
    # Verifica se podemos retomar (deve estar em falha ou foi criada agora)
    if transcricao["status"] != "falha" and transcricao.get("recriada") != True:
        raise HTTPException(status_code=400, detail="Só é possível retomar transcrições que falharam")
    
    # Atualiza o status
    transcricao["status"] = "retomando"
    
    # Retorna um novo client_id para reconexão
    novo_client_id = str(uuid.uuid4())
    transcricao["client_id"] = novo_client_id
    
    # Adiciona mensagem de retomada para o log
    print(f"Retomando transcrição {transcricao_id} com novo client_id {novo_client_id}")
    
    return {
        "status": "retomando", 
        "client_id": novo_client_id, 
        "transcricao_id": transcricao_id,
        "message": "Transcrição retomada. Conecte-se ao WebSocket para receber atualizações."
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
    await manager.connect(websocket, client_id)
    try:
        # Busca transcrição associada a este client_id
        transcricao_id = None
        for tid, info in transcricoes_ativas.items():
            if info.get("client_id") == client_id:
                transcricao_id = tid
                break
        
        if not transcricao_id:
            await manager.send_message(json.dumps({
                "tipo": "erro",
                "mensagem": "Nenhuma transcrição associada a este cliente"
            }), client_id)
            return
        
        info = transcricoes_ativas[transcricao_id]
        
        # Verifica o status
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
                
                # Notifica que o download foi concluído
                await manager.send_message(json.dumps({
                    "tipo": "preparando",
                    "mensagem": f"Áudio baixado com sucesso: {titulo}",
                    "progresso": 20,
                    "transcricao_id": transcricao_id
                }), client_id)
                
                # Inicia a transcrição
                asyncio.create_task(transcrever_audio_em_chunks(caminho_audio, client_id, transcricao_id, titulo))
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
                raise e
            
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
                
                # Notifica que a extração foi concluída
                await manager.send_message(json.dumps({
                    "tipo": "preparando",
                    "mensagem": f"Áudio extraído com sucesso: {info['nome_arquivo']}",
                    "progresso": 25,
                    "transcricao_id": transcricao_id
                }), client_id)
                
                # Inicia a transcrição
                asyncio.create_task(transcrever_audio_em_chunks(caminho_audio, client_id, transcricao_id, titulo))
            except Exception as e:
                await manager.send_message(json.dumps({
                    "tipo": "erro", 
                    "mensagem": f"Erro ao extrair áudio do vídeo: {str(e)}",
                    "transcricao_id": transcricao_id
                }), client_id)
                raise e
        
        # Mantém a conexão aberta para receber comandos do cliente
        while True:
            data = await websocket.receive_text()
            cmd = json.loads(data)
            
            if cmd["acao"] == "cancelar":
                # Cancela a transcrição
                transcricoes_ativas[transcricao_id]["status"] = "cancelada"
                await manager.send_message(json.dumps({
                    "tipo": "cancelada",
                    "transcricao_id": transcricao_id
                }), client_id)
                break
    
    except WebSocketDisconnect:
        # Cliente desconectou mas a transcrição continua em background
        pass
    except Exception as e:
        # Qualquer erro, enviamos ao cliente se possível
        try:
            await manager.send_message(json.dumps({
                "tipo": "erro",
                "mensagem": str(e)
            }), client_id)
        except:
            pass
    finally:
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