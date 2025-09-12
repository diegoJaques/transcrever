# 📋 GUIA DE DEPLOY NO SERVIDOR

## PASSO 1: NO SEU COMPUTADOR LOCAL
```bash
# Fazer commit e push das últimas alterações
git add .
git commit -m "Adicionar configuração Docker para deploy"
git push origin master
```

## PASSO 2: NO SERVIDOR (via SSH)

### 2.1 - Clonar ou atualizar o repositório
```bash
# Se ainda não tem o repositório clonado:
cd /home/jaques  # ou diretório onde ficam seus projetos
git clone https://github.com/diegoJaques/transcrever.git transcricao_videos

# Se já tem o repositório:
cd /home/jaques/transcricao_videos
git pull origin master
```

### 2.2 - Criar arquivo .env no servidor
```bash
cd /home/jaques/transcricao_videos
nano .env

# Adicionar:
OPENROUTER_API_KEY=sua_chave_real_aqui
# Salvar com Ctrl+X, Y, Enter
```

### 2.3 - Editar o docker-compose.yml principal
```bash
cd /home/jaques  # onde está seu docker-compose.yml
nano docker-compose.yml
```

Adicionar este serviço dentro de "services:" do seu docker-compose.yml:

```yaml
  transcricao:
    build:
      context: ./transcricao_videos
      dockerfile: Dockerfile
    container_name: transcricao
    restart: always
    env_file:
      - ./transcricao_videos/.env  # Usa o .env da pasta da aplicação
    volumes:
      - ./transcricao_uploads:/app/uploads
      - ./transcricao_videos_data:/app/videos
      - ./transcricao_audios:/app/audios
      - ./transcricao_transcricoes:/app/transcricoes
      - ./transcricao_generated_audio:/app/generated_audio
      - ./transcricao_tmp:/app/tmp
    networks:
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.transcricao.rule=Host(`transcricao.celintelligence.com`)"
      - "traefik.http.routers.transcricao.entrypoints=websecure"
      - "traefik.http.routers.transcricao.tls.certresolver=leresolver"
      - "traefik.http.services.transcricao.loadbalancer.server.port=8000"
```

**IMPORTANTE:** O `env_file` aponta para `./transcricao_videos/.env`, garantindo que o Docker use o arquivo .env que está dentro da pasta da aplicação.

### 2.4 - Criar diretórios de volumes (opcional)
```bash
mkdir -p transcricao_uploads transcricao_videos_data transcricao_audios
mkdir -p transcricao_transcricoes transcricao_generated_audio transcricao_tmp
```

### 2.5 - Build e deploy
```bash
# Fazer build da nova imagem
docker-compose build transcricao

# Subir o serviço
docker-compose up -d transcricao

# Verificar se está rodando
docker-compose ps
docker-compose logs transcricao
```

## PASSO 3: CONFIGURAR DNS (se necessário)

Adicionar registro DNS apontando `transcricao.celintelligence.com` para o IP do seu servidor.

## COMANDOS ÚTEIS

```bash
# Ver logs em tempo real
docker-compose logs -f transcricao

# Reiniciar o serviço
docker-compose restart transcricao

# Parar o serviço
docker-compose stop transcricao

# Remover e recriar (se precisar)
docker-compose down transcricao
docker-compose up -d transcricao

# Acessar o container
docker exec -it transcricao bash

# Atualizar após mudanças no código
cd /home/jaques/transcricao_videos
git pull
docker-compose build transcricao
docker-compose up -d transcricao
```

## TROUBLESHOOTING

### Se der erro de permissão:
```bash
sudo chown -R $USER:$USER transcricao_*
```

### Se der erro de porta em uso:
Verificar se a porta 8000 não está sendo usada internamente por outro container.

### Se der erro de build:
```bash
docker-compose build --no-cache transcricao
```

### Verificar se o Traefik está redirecionando corretamente:
```bash
curl -I https://transcricao.celintelligence.com
```

## ESTRUTURA FINAL NO SERVIDOR
```
/home/jaques/
├── docker-compose.yml (atualizado)
├── transcricao_videos/ (repositório clonado)
│   ├── .env (com OPENROUTER_API_KEY)
│   ├── Dockerfile
│   ├── app.py
│   └── ...
├── transcricao_uploads/
├── transcricao_videos_data/
├── transcricao_audios/
├── transcricao_transcricoes/
├── transcricao_generated_audio/
└── transcricao_tmp/
```

## 🎉 PRONTO!
Após esses passos, o sistema estará acessível em:
https://transcricao.celintelligence.com