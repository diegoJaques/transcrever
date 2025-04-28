# Sistema de Transcrição de Vídeos

Sistema web para transcrição de vídeos do YouTube e arquivos locais usando o modelo Whisper, com geração de insights usando Gemini Flash 2.0.

## 🚀 Funcionalidades

- Transcrição de vídeos do YouTube
- Transcrição de vídeos locais
- Seleção de diferentes modelos Whisper (tiny até large-v3)
- Barra de progresso em tempo real
- Sistema de recuperação em caso de falhas
- Geração de insights usando IA
- Download das transcrições em TXT
- Interface web moderna e responsiva

## 📋 Pré-requisitos

- Python 3.8 ou superior
- FFmpeg instalado no sistema
- Conexão com a internet
- Chave API do OpenRouter (para geração de insights)

## 🔧 Instalação

1. Clone o repositório:
```bash
git clone [url-do-repositorio]
cd transcricao_videos
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Configure o arquivo `.env`:
```
OPENROUTER_API_KEY=sua_chave_api_aqui
```

## 🎮 Como Usar

1. Inicie o servidor:
```bash
uvicorn app:app --reload
```

2. Acesse no navegador:
```
http://localhost:8000
```

3. Na interface:
   - Selecione o modelo Whisper desejado
   - Escolha entre YouTube ou arquivo local
   - Aguarde a transcrição (acompanhe o progresso)
   - Gere insights após a conclusão
   - Faça o download do texto transcrito

## 📝 Modelos Disponíveis

- `tiny`: Mais rápido, menos preciso
- `base`: Bom equilíbrio
- `small`: Recomendado para uso geral
- `medium`: Mais preciso
- `large`: Máxima precisão
- `large-v2`: Versão atualizada
- `large-v3`: Última versão

## ⚠️ Observações

- Para vídeos longos, recomenda-se usar modelos menores (tiny, base ou small)
- A geração de insights requer uma chave API válida do OpenRouter
- Em caso de falha, o sistema permite retomar a transcrição do ponto onde parou
- Os arquivos de áudio são salvos temporariamente e depois removidos

## 🛠️ Solução de Problemas

1. Se o FFmpeg não estiver instalado:
   - Windows: Baixe do site oficial e adicione ao PATH
   - Linux: `sudo apt-get install ffmpeg`
   - Mac: `brew install ffmpeg`

2. Se a transcrição falhar:
   - Verifique sua conexão com a internet
   - Tente um modelo menor
   - Use o botão "Retomar" para continuar do ponto onde parou

3. Se os insights não funcionarem:
   - Verifique se a chave API está correta no arquivo .env
   - Confirme se há conexão com a internet

## 📝 Licença

Este projeto está sob a licença MIT. Veja o arquivo LICENSE para mais detalhes. 