import asyncio
from edge_tts import list_voices

async def main():
    voices = await list_voices()
    for voice in voices:
        if "pt" in voice["Locale"].lower():  # Filtrando apenas vozes em português
            print(f"Nome: {voice['ShortName']}")
            print(f"Gênero: {voice['Gender']}")
            print(f"Localidade: {voice['Locale']}")
            print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main()) 