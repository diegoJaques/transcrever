import asyncio
from edge_tts import Communicate

async def text_to_speech(text, output_file, voice="pt-BR-FranciscaNeural"):
    """
    Converte texto em fala e salva em um arquivo
    
    Args:
        text (str): Texto para converter em fala
        output_file (str): Nome do arquivo de saída (deve terminar em .mp3)
        voice (str): Nome da voz a ser usada
    """
    communicate = Communicate(text, voice)
    await communicate.save(output_file)

async def main():
    text = "Olá! Este é um teste de conversão de texto em fala usando o Edge TTS."
    await text_to_speech(text, "teste.mp3")
    print("Arquivo de áudio gerado com sucesso!")

if __name__ == "__main__":
    asyncio.run(main()) 