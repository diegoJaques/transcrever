import asyncio
import os
from typing import Optional
import whisper
from edge_tts import Communicate

class AudioManager:
    def __init__(self, model_size: str = "base", voice: str = "pt-BR-FranciscaNeural"):
        """
        Inicializa o gerenciador de áudio
        
        Args:
            model_size: Tamanho do modelo Whisper ('tiny', 'base', 'small', 'medium', 'large')
            voice: Voz a ser usada para TTS (ex: 'pt-BR-FranciscaNeural')
        """
        self.model = whisper.load_model(model_size)
        self.voice = voice
        
    def transcribe_audio(self, audio_path: str) -> dict:
        """
        Transcreve um arquivo de áudio para texto
        
        Args:
            audio_path: Caminho para o arquivo de áudio/vídeo
            
        Returns:
            Dict contendo a transcrição e outros metadados
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {audio_path}")
            
        result = self.model.transcribe(audio_path, language="pt")
        return result
    
    async def generate_speech(self, text: str, output_path: str) -> None:
        """
        Gera um arquivo de áudio a partir de texto
        
        Args:
            text: Texto para converter em fala
            output_path: Caminho onde salvar o arquivo de áudio
        """
        communicate = Communicate(text, self.voice)
        await communicate.save(output_path)
    
    def transcribe_and_save(self, audio_path: str, output_text_path: Optional[str] = None) -> str:
        """
        Transcreve áudio e opcionalmente salva em arquivo
        
        Args:
            audio_path: Caminho do arquivo de áudio
            output_text_path: Caminho para salvar a transcrição (opcional)
            
        Returns:
            Texto transcrito
        """
        result = self.transcribe_audio(audio_path)
        text = result["text"]
        
        if output_text_path:
            with open(output_text_path, "w", encoding="utf-8") as f:
                f.write(text)
                
        return text
    
    async def text_to_speech_file(self, input_text_path: str, output_audio_path: str) -> None:
        """
        Converte um arquivo de texto em áudio
        
        Args:
            input_text_path: Caminho do arquivo de texto
            output_audio_path: Caminho para salvar o áudio
        """
        with open(input_text_path, "r", encoding="utf-8") as f:
            text = f.read()
            
        await self.generate_speech(text, output_audio_path)

# Exemplo de uso
async def main():
    # Inicializa o gerenciador
    manager = AudioManager(model_size="base", voice="pt-BR-FranciscaNeural")
    
    # Exemplo 1: Transcrição de áudio para texto
    try:
        texto = manager.transcribe_and_save(
            audio_path="exemplo_video.mp4",
            output_text_path="transcricao.txt"
        )
        print("Transcrição concluída e salva em 'transcricao.txt'")
        
        # Exemplo 2: Geração de áudio a partir do texto transcrito
        await manager.generate_speech(
            text=texto,
            output_path="audio_gerado.mp3"
        )
        print("Áudio gerado com sucesso em 'audio_gerado.mp3'")
        
    except FileNotFoundError as e:
        print(f"Erro: {e}")
    except Exception as e:
        print(f"Erro inesperado: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 