from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import speech_recognition as sr
import yt_dlp
import os
from moviepy.editor import VideoFileClip
import tempfile
from typing import Optional
import logging
import traceback

# Configurar logging com mais detalhes
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configuração do CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar o reconhecedor de fala
recognizer = sr.Recognizer()

@app.post("/transcribe-file")
async def transcribe_file(file: UploadFile = File(...)):
    try:
        # Criar um arquivo temporário para salvar o vídeo
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        # Extrair áudio do vídeo
        video = VideoFileClip(temp_file_path)
        audio_path = temp_file_path + "_audio.wav"
        video.audio.write_audiofile(audio_path)
        video.close()

        # Transcrever o áudio
        with sr.AudioFile(audio_path) as source:
            audio = recognizer.record(source)
            text = recognizer.recognize_google(audio, language='pt-BR')

        # Limpar arquivos temporários
        os.unlink(temp_file_path)
        os.unlink(audio_path)

        return JSONResponse(content={"transcription": text})

    except Exception as e:
        logger.error(f"Erro ao processar arquivo: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe-youtube")
async def transcribe_youtube(url: str = Form(...)):
    try:
        if not url:
            raise HTTPException(status_code=400, detail="URL não pode estar vazia")
            
        logger.info(f"Iniciando processamento do vídeo: {url}")
        
        # Configuração do yt-dlp com mais opções de debug
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
            }],
            'outtmpl': 'temp_%(id)s',
            'verbose': True,
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'force_generic_extractor': False,
            'ignoreerrors': False,
            'no_color': True
        }

        # Baixar áudio do YouTube
        try:
            logger.info("Iniciando download com yt-dlp...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info("Extraindo informações do vídeo...")
                try:
                    # Primeiro verifica se o vídeo existe e está acessível
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        raise Exception("Não foi possível obter informações do vídeo")
                    
                    video_id = info.get('id')
                    if not video_id:
                        raise Exception("ID do vídeo não encontrado")
                        
                    logger.info(f"Vídeo encontrado: {video_id}")
                    
                    # Agora faz o download
                    info = ydl.extract_info(url, download=True)
                    audio_path = f"temp_{info['id']}.wav"
                    
                    if not os.path.exists(audio_path):
                        raise Exception(f"Arquivo de áudio não foi criado: {audio_path}")
                        
                    logger.info(f"Áudio baixado com sucesso: {audio_path}")
                    
                except Exception as extract_error:
                    logger.error(f"Erro ao extrair informações do vídeo: {str(extract_error)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    raise
                    
        except Exception as ydl_error:
            logger.error(f"Erro ao baixar vídeo do YouTube: {str(ydl_error)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao baixar vídeo do YouTube: {str(ydl_error)}"
            )

        # Transcrever o áudio
        try:
            if not os.path.exists(audio_path):
                raise Exception(f"Arquivo de áudio não encontrado: {audio_path}")
                
            logger.info(f"Iniciando transcrição do arquivo: {audio_path}")
            with sr.AudioFile(audio_path) as source:
                logger.info("Gravando áudio para transcrição...")
                audio = recognizer.record(source)
                logger.info("Enviando para API do Google Speech Recognition...")
                text = recognizer.recognize_google(audio, language='pt-BR')
                logger.info("Transcrição concluída com sucesso")
        except Exception as trans_error:
            logger.error(f"Erro na transcrição: {str(trans_error)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail=f"Erro na transcrição: {str(trans_error)}"
            )
        finally:
            # Limpar arquivo temporário
            try:
                if 'audio_path' in locals() and os.path.exists(audio_path):
                    os.unlink(audio_path)
                    logger.info("Arquivo temporário removido com sucesso")
            except Exception as cleanup_error:
                logger.error(f"Erro ao limpar arquivo temporário: {str(cleanup_error)}")

        return JSONResponse(content={"transcription": text})

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}")
        logger.error(f"Traceback completo: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {str(e)}")

# Montar arquivos estáticos (HTML, CSS, JS)
app.mount("/", StaticFiles(directory="static", html=True), name="static") 