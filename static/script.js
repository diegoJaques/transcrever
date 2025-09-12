document.addEventListener('DOMContentLoaded', function() {
    const youtubeForm = document.getElementById('youtube-form');
    const arquivoForm = document.getElementById('arquivo-form');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.querySelector('.progress-bar');
    const statusText = document.getElementById('status-text');
    const transcricaoTexto = document.getElementById('transcricao-texto');
    const transcricaoTitulo = document.getElementById('transcricao-titulo');
    const insightsTexto = document.getElementById('insights-texto');
    const gerarInsightsBtn = document.getElementById('gerar-insights');
    const modeloSelect = document.getElementById('modelo-select');
    const btnCancelar = document.getElementById('btn-cancel');
    const btnRetomar = document.getElementById('btn-retomar');
    const btnBaixar = document.getElementById('btn-baixar');
    const listaTranscricoes = document.getElementById('lista-transcricoes');
    const transcricoesContainer = document.getElementById('transcricoes-container');

    // Elementos da clonagem de voz
    const clonagemVozSection = document.getElementById('clonagem-voz-section');
    const clonagemVozForm = document.getElementById('clonagem-voz-form');
    const textoParaAudio = document.getElementById('texto-para-audio');
    const btnPlayAudio = document.getElementById('btn-play-audio');
    const btnDownloadAudio = document.getElementById('btn-download-audio');
    const audioStatus = document.getElementById('audio-status');

    // Elementos da interface
    const btnFalar = document.getElementById('btn-falar');
    const audioPlayerContainer = document.getElementById('audio-player');
    const audioElement = document.getElementById('audio-element');
    const btnBaixarAudio = document.getElementById('btn-baixar-audio');

    // Referências para a nova seção 'Ask AI' (Adicionado)
    const askAiSection = document.getElementById('ask-ai-section');
    const aiQuestionInput = document.getElementById('ai-question-input');
    const askAiButton = document.getElementById('ask-ai-button');
    const aiResponseArea = document.getElementById('ai-response-area');

    // Variáveis para controle de websocket e transcrição atual
    let ws = null;
    let transcricaoAtual = null;
    let transcricaoEmAndamento = false;
    let transcricaoId = null;
    let audioUrl = null;
    let clientId = null;
    let transcricoesAtivas = {};
    let socket = null;
    let currentAiRequestId = 0; // Para evitar condições de corrida nas respostas da IA

    // Variável para armazenar o nome do arquivo de áudio atual
    let currentAudioFile = null;

    // Carrega transcrições do localStorage
    function carregarTranscricoesLocais() {
        const transcricoesSalvas = localStorage.getItem('transcricoes');
        if (transcricoesSalvas) {
            try {
                transcricoesAtivas = JSON.parse(transcricoesSalvas);
                atualizarListaTranscricoes();
            } catch (e) {
                console.error('Erro ao carregar transcrições:', e);
                localStorage.removeItem('transcricoes');
                transcricoesAtivas = {};
            }
        }
    }

    // Salva transcrições no localStorage
    function salvarTranscricoesLocais() {
        localStorage.setItem('transcricoes', JSON.stringify(transcricoesAtivas));
        atualizarListaTranscricoes();
    }

    // Atualiza a lista de transcrições
    function atualizarListaTranscricoes() {
        transcricoesContainer.innerHTML = '';
        
        const keys = Object.keys(transcricoesAtivas);
        if (keys.length > 0) {
            listaTranscricoes.classList.remove('d-none');
            
            keys.forEach(id => {
                const info = transcricoesAtivas[id];
                const item = document.createElement('a');
                item.href = '#';
                item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
                
                let status = 'Em andamento';
                let statusClass = 'badge bg-primary';
                
                if (info.status === 'concluida') {
                    status = 'Concluída';
                    statusClass = 'badge bg-success';
                } else if (info.status === 'falha') {
                    status = 'Falha';
                    statusClass = 'badge bg-danger';
                } else if (info.status === 'cancelada') {
                    status = 'Cancelada';
                    statusClass = 'badge bg-secondary';
                }
                
                item.innerHTML = `
                    <div>
                        <strong>${info.titulo || (info.tipo === 'youtube' ? 'Vídeo do YouTube' : info.nome_arquivo || 'Arquivo local')}</strong>
                        <br>
                        <small class="text-muted">${new Date(info.iniciado_em).toLocaleString()}</small>
                    </div>
                    <span class="${statusClass}">${status}</span>
                `;
                
                item.addEventListener('click', (e) => {
                    e.preventDefault();
                    carregarTranscricao(id);
                });
                
                transcricoesContainer.appendChild(item);
            });
        } else {
            listaTranscricoes.classList.add('d-none');
        }
    }

    // Carrega uma transcrição específica
    async function carregarTranscricao(id) {
        try {
            toggleProgress(true, 10);
            statusText.textContent = 'Carregando transcrição...';
            adicionarStatusHistorico('Tentando carregar transcrição...', 'info');
            hideAskAiSection(); // Oculta a seção AI ao carregar nova transcrição
            
            const response = await fetch(`/transcricao/${id}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Erro ao carregar transcrição');
            }
            
            const data = await response.json();
            
            // Atualiza a interface
            transcricaoId = id;
            transcricaoTexto.textContent = data.texto || 'Texto da transcrição não disponível';
            transcricaoTitulo.textContent = data.titulo || 'Transcrição';
            
            // Atualiza visibilidade dos botões
            if (data.texto && data.texto !== 'Texto da transcrição não disponível') {
                btnFalar.classList.remove('d-none');
                gerarInsightsBtn.disabled = false;
            } else {
                btnFalar.classList.add('d-none');
                gerarInsightsBtn.disabled = true;
            }
            
            adicionarStatusHistorico(`Transcrição carregada: ${data.titulo || 'Sem título'}`, 'success');
            
            // Armazena a transcrição atual nos dados locais se não existir
            if (!transcricoesAtivas[id]) {
                transcricoesAtivas[id] = {
                    status: data.status || 'desconhecido',
                    titulo: data.titulo || 'Transcrição Recuperada',
                    iniciado_em: data.iniciado_em || new Date().toISOString(),
                    texto: data.texto || ''
                };
                salvarTranscricoesLocais();
            }
            
            // Habilita/desabilita botões conforme o status
            if (data.status === 'falha') {
                btnRetomar.classList.remove('d-none');
                
                // Mostra mensagem explicativa sobre como retomar
                const mensagemFalha = document.createElement('div');
                mensagemFalha.className = 'alert alert-warning mt-3';
                mensagemFalha.innerHTML = `
                    <h5><i class="bi bi-exclamation-triangle"></i> Transcrição interrompida</h5>
                    <p>Esta transcrição foi interrompida. Clique em "Retomar Transcrição" para continuar de onde parou.</p>
                `;
                
                // Adiciona mensagem antes do texto da transcrição
                if (!document.querySelector('.alert-warning')) {
                    transcricaoTexto.parentNode.insertBefore(mensagemFalha, transcricaoTexto);
                }
                
                adicionarStatusHistorico('Esta transcrição foi interrompida e pode ser retomada', 'warning');
            } else {
                btnRetomar.classList.add('d-none');
                // Remove mensagem de falha se existir
                const mensagemFalha = document.querySelector('.alert-warning');
                if (mensagemFalha) {
                    mensagemFalha.remove();
                }
            }
            
            // Mostra botão de download se texto estiver disponível
            if (data.texto) {
                btnBaixar.classList.remove('d-none');
                // Mostra a seção 'Ask AI' se a transcrição estiver concluída e tiver texto
                if (data.status === 'concluida') {
                    showAskAiSection(); 
                }
            } else {
                btnBaixar.classList.add('d-none');
                hideAskAiSection();
            }
            
            // Se a transcrição estiver em andamento, conecta ao WebSocket
            if (data.status === 'em_andamento' && data.client_id) {
                clientId = data.client_id;
                conectarWebSocket();
            }
            
            // Após carregar a transcrição com sucesso
            if (data.texto) {
                mostrarClonagemVoz(data.texto);
            }
            
            toggleProgress(false);
            
        } catch (error) {
            console.error('Erro:', error);
            toggleProgress(false);
            
            // Cria uma mensagem de erro para o usuário
            const errorMessage = document.createElement('div');
            errorMessage.className = 'alert alert-danger mt-3';
            errorMessage.innerHTML = `
                <h5><i class="bi bi-exclamation-triangle"></i> Erro ao carregar transcrição</h5>
                <p>${error.message}</p>
                <p>A transcrição solicitada pode não existir ou ter sido corrompida.</p>
            `;
            
            // Limpa mensagens de erro anteriores
            const prevError = document.querySelector('.alert-danger');
            if (prevError) prevError.remove();
            
            // Adiciona a mensagem de erro à interface
            transcricaoTexto.parentNode.insertBefore(errorMessage, transcricaoTexto);
            transcricaoTexto.textContent = 'Nenhuma transcrição disponível';
            
            adicionarStatusHistorico(`Erro ao carregar transcrição: ${error.message}`, 'error');
            
            // Remove essa transcrição da lista local se ela existir
            if (transcricoesAtivas[id]) {
                delete transcricoesAtivas[id];
                salvarTranscricoesLocais();
            }
            hideAskAiSection(); // Oculta seção AI em caso de erro
        }
    }

    // Função para mostrar/ocultar a barra de progresso
    function toggleProgress(show, progress = null) {
        progressContainer.classList.toggle('d-none', !show);
        if (show) {
            if (progress !== null) {
                progressBar.style.width = `${progress}%`;
                progressBar.setAttribute('aria-valuenow', progress);
            } else {
                progressBar.style.width = '100%';
            }
            progressBar.classList.add('progress-bar-striped', 'progress-bar-animated');
            hideAskAiSection(); // Oculta seção AI ao iniciar progresso
        } else {
            progressBar.classList.remove('progress-bar-striped', 'progress-bar-animated');
        }
    }

    // Função para atualizar o histórico de status
    function adicionarStatusHistorico(mensagem, tipo = 'info') {
        // Cria o elemento para o histórico de status se não existir
        if (!document.getElementById('status-historico')) {
            const statusHistoricoDiv = document.createElement('div');
            statusHistoricoDiv.id = 'status-historico';
            statusHistoricoDiv.className = 'status-historico mt-2 small';
            statusHistoricoDiv.style.maxHeight = '100px';
            statusHistoricoDiv.style.overflowY = 'auto';
            statusText.parentNode.appendChild(statusHistoricoDiv);
        }
        
        const historicoDiv = document.getElementById('status-historico');
        const timestamp = new Date().toLocaleTimeString();
        const statusItem = document.createElement('div');
        
        let badge = '';
        if (tipo === 'info') badge = '<span class="badge bg-info">Info</span>';
        else if (tipo === 'success') badge = '<span class="badge bg-success">Sucesso</span>';
        else if (tipo === 'warning') badge = '<span class="badge bg-warning">Aviso</span>';
        else if (tipo === 'error') badge = '<span class="badge bg-danger">Erro</span>';
        
        statusItem.innerHTML = `${badge} <small>${timestamp}</small>: ${mensagem}`;
        
        historicoDiv.appendChild(statusItem);
        historicoDiv.scrollTop = historicoDiv.scrollHeight;
        
        // Limita o número de itens no histórico
        while (historicoDiv.childNodes.length > 10) {
            historicoDiv.removeChild(historicoDiv.firstChild);
        }
    }

    // Função para conectar ao WebSocket
    function conectarWebSocket() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            console.log("WebSocket já está conectado.");
            return;
        }
        
        if (!clientId) {
            console.error("Client ID não definido para conexão WebSocket");
            adicionarStatusHistorico("Erro interno: Client ID ausente.", "error");
            return;
        }

        const wsUrl = `ws://${window.location.host}/ws/${clientId}`;
        ws = new WebSocket(wsUrl);
        console.log(`Tentando conectar a: ${wsUrl}`);
        adicionarStatusHistorico("Conectando para receber atualizações...", "info");

        ws.onopen = function() {
            console.log("WebSocket conectado!");
            transcricaoEmAndamento = true;
            adicionarStatusHistorico("Conectado! Aguardando progresso da transcrição.", "success");
            btnCancelar.classList.remove('d-none');
        };

        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                console.log("Mensagem recebida:", data);
                adicionarStatusHistorico(`Mensagem: ${data.tipo} - ${data.mensagem || data.etapa || ''}`, 'debug');

                switch (data.tipo) {
                    case 'status':
                        statusText.textContent = data.mensagem;
                        adicionarStatusHistorico(`Status: ${data.mensagem}`, 'info');
                        break;
                    case 'baixando':
                    case 'preparando':
                        toggleProgress(true, data.progresso || 10);
                        statusText.textContent = data.mensagem;
                        adicionarStatusHistorico(`Progresso: ${data.mensagem}`, 'info');
                        break;
                    case 'transcricao_parcial':
                        toggleProgress(true, data.progresso);
                        transcricaoTexto.textContent = data.texto;
                        transcricaoTitulo.textContent = data.titulo || 'Transcrição em Andamento';
                        statusText.textContent = data.etapa || `Progresso: ${data.progresso}%`;
                        transcricaoId = data.transcricao_id;
                        
                        // Atualiza dados locais com validação melhorada
                        if (!transcricoesAtivas[data.transcricao_id]) {
                             transcricoesAtivas[data.transcricao_id] = { 
                                 iniciado_em: new Date().toISOString(),
                                 client_id: clientId
                             };
                        }
                        
                        // Atualiza status baseado no progresso
                        if (data.progresso >= 100) {
                            transcricoesAtivas[data.transcricao_id].status = 'concluida';
                        } else {
                            transcricoesAtivas[data.transcricao_id].status = 'em_andamento';
                        }
                        
                        transcricoesAtivas[data.transcricao_id].titulo = data.titulo;
                        transcricoesAtivas[data.transcricao_id].texto = data.texto;
                        transcricoesAtivas[data.transcricao_id].progresso = data.progresso;
                        transcricoesAtivas[data.transcricao_id].etapa = data.etapa;
                        
                        salvarTranscricoesLocais();
                        break;
                        
                    case 'transcricao_concluida':
                        toggleProgress(false);
                        transcricaoEmAndamento = false;
                        statusText.textContent = 'Transcrição concluída!';
                        adicionarStatusHistorico("Transcrição concluída com sucesso!", "success");
                        btnCancelar.classList.add('d-none');
                        btnBaixar.classList.remove('d-none');
                        gerarInsightsBtn.disabled = false;
                        btnFalar.classList.remove('d-none');
                        transcricaoId = data.transcricao_id;
                        
                        // Atualiza status final
                        if (transcricoesAtivas[data.transcricao_id]) {
                            transcricoesAtivas[data.transcricao_id].status = 'concluida';
                            transcricoesAtivas[data.transcricao_id].progresso = 100;
                            transcricoesAtivas[data.transcricao_id].concluida_em = new Date().toISOString();
                            salvarTranscricoesLocais();
                        }
                        
                        showAskAiSection();
                        break;
                        
                    case 'erro':
                        toggleProgress(false);
                        transcricaoEmAndamento = false;
                        statusText.textContent = `Erro: ${data.mensagem}`;
                        adicionarStatusHistorico(`Erro na transcrição: ${data.mensagem}`, 'error');
                        
                        // Não mostra alert para não ser intrusivo
                        console.error("Erro na transcrição:", data.mensagem);
                        
                        btnCancelar.classList.add('d-none');
                        hideAskAiSection();
                        
                        // Atualiza status local com mais informações
                        if (data.transcricao_id && transcricoesAtivas[data.transcricao_id]) {
                            transcricoesAtivas[data.transcricao_id].status = 'falha';
                            transcricoesAtivas[data.transcricao_id].erro = data.mensagem;
                            transcricoesAtivas[data.transcricao_id].erro_em = new Date().toISOString();
                            salvarTranscricoesLocais();
                        }
                        
                        // Mostra botão de retomar se aplicável
                        btnRetomar.classList.remove('d-none');
                        break;
                        
                    case 'cancelada':
                         toggleProgress(false);
                         transcricaoEmAndamento = false;
                         statusText.textContent = 'Transcrição cancelada pelo usuário.';
                         adicionarStatusHistorico('Transcrição cancelada.', 'warning');
                         btnCancelar.classList.add('d-none');
                         hideAskAiSection();
                         
                         if (data.transcricao_id && transcricoesAtivas[data.transcricao_id]) {
                            transcricoesAtivas[data.transcricao_id].status = 'cancelada';
                            transcricoesAtivas[data.transcricao_id].cancelada_em = new Date().toISOString();
                            salvarTranscricoesLocais();
                        }
                         break;
                         
                    default:
                        console.warn("Tipo de mensagem desconhecido:", data.tipo);
                        adicionarStatusHistorico(`Mensagem desconhecida: ${event.data}`, 'warning');
                }
            } catch (error) {
                console.error("Erro ao processar mensagem WebSocket:", error);
                adicionarStatusHistorico(`Erro no WebSocket: ${error}`, 'error');
            }
        };

        ws.onerror = function(error) {
            console.error("Erro no WebSocket:", error);
            transcricaoEmAndamento = false;
            adicionarStatusHistorico("Erro na conexão WebSocket.", "error");
            
            // Marca como falha apenas se estava realmente em andamento
            if (transcricaoId && transcricoesAtivas[transcricaoId] && 
                transcricoesAtivas[transcricaoId].status === 'em_andamento') {
                 transcricoesAtivas[transcricaoId].status = 'falha';
                 transcricoesAtivas[transcricaoId].erro = "Erro de conexão WebSocket";
                 transcricoesAtivas[transcricaoId].erro_em = new Date().toISOString();
                 salvarTranscricoesLocais();
                 
                 // Mostra botão de retomar
                 btnRetomar.classList.remove('d-none');
            }
        };

        ws.onclose = function(event) {
            console.log("WebSocket desconectado:", event.code, event.reason);
            transcricaoEmAndamento = false;
            ws = null;
            
            const isUnexpectedClose = event.code !== 1000 && event.code !== 1005;
            const isTranscriptionActive = transcricaoId && transcricoesAtivas[transcricaoId] && 
                                         transcricoesAtivas[transcricaoId].status === 'em_andamento';
            
            if (isUnexpectedClose && isTranscriptionActive) {
                adicionarStatusHistorico("Conexão WebSocket fechada inesperadamente.", "warning");
                
                // Marca como falha por desconexão
                transcricoesAtivas[transcricaoId].status = 'falha';
                transcricoesAtivas[transcricaoId].erro = `Desconexão inesperada (código: ${event.code})`;
                transcricoesAtivas[transcricaoId].erro_em = new Date().toISOString();
                salvarTranscricoesLocais();
                
                // Oferece possibilidade de retomar
                btnRetomar.classList.remove('d-none');
                statusText.textContent = 'Conexão perdida. Use "Retomar" para continuar.';
            } else {
                adicionarStatusHistorico("Conexão WebSocket fechada.", "info");
            }
            
            btnCancelar.classList.add('d-none');
        };
    }

    // Função para mudar o modelo
    async function mudarModelo(nomeModelo) {
        try {
            toggleProgress(true);
            statusText.textContent = 'Carregando novo modelo...';

            const response = await fetch(`/mudar-modelo/${nomeModelo}`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error('Erro ao carregar modelo');
            }

            statusText.textContent = 'Modelo carregado com sucesso!';
            
            setTimeout(() => {
                toggleProgress(false);
            }, 1000);

        } catch (error) {
            console.error('Erro:', error);
            statusText.textContent = 'Erro ao carregar modelo. Tente novamente.';
        }
    }

    // Função para iniciar transcrição do YouTube
    async function iniciarTranscricaoYoutube(url) {
        adicionarStatusHistorico(`Iniciando transcrição do YouTube: ${url}`, 'info');
        hideAskAiSection(); // Oculta seção AI
        try {
            toggleProgress(true, 0);
            statusText.textContent = 'Iniciando processo de transcrição...';
            adicionarStatusHistorico('Iniciando transcrição de vídeo do YouTube', 'info');
            
            const formData = new FormData();
            formData.append('url', url);
            
            const response = await fetch('/iniciar-transcricao-youtube', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('Erro ao iniciar transcrição');
            }

            const data = await response.json();
            clientId = data.client_id;
            transcricaoId = data.transcricao_id;
            
            // Salva localmente
            transcricoesAtivas[transcricaoId] = {
                client_id: clientId,
                tipo: 'youtube',
                url: url,
                status: 'em_andamento',
                iniciado_em: new Date().toISOString()
            };
            salvarTranscricoesLocais();
            
            adicionarStatusHistorico('Requisição de transcrição aceita pelo servidor', 'success');
            
            // Conecta ao WebSocket
            conectarWebSocket();

        } catch (error) {
            console.error('Erro:', error);
            statusText.textContent = 'Erro ao iniciar transcrição. Tente novamente.';
            adicionarStatusHistorico(`Erro: ${error.message}`, 'error');
            toggleProgress(false);
        }
    }

    // Função para iniciar transcrição de arquivo local
    async function iniciarTranscricaoArquivo(file) {
        adicionarStatusHistorico(`Iniciando transcrição do arquivo: ${file.name}`, 'info');
        hideAskAiSection(); // Oculta seção AI
        try {
            toggleProgress(true, 0);
            statusText.textContent = 'Enviando arquivo...';
            adicionarStatusHistorico(`Iniciando upload de ${file.name} (${(file.size/1024/1024).toFixed(2)} MB)`, 'info');
            
            const formData = new FormData();
            formData.append('file', file);
            
            const response = await fetch('/iniciar-transcricao-arquivo', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('Erro ao iniciar transcrição');
            }

            const data = await response.json();
            clientId = data.client_id;
            transcricaoId = data.transcricao_id;
            
            // Salva localmente
            transcricoesAtivas[transcricaoId] = {
                client_id: clientId,
                tipo: 'arquivo',
                nome_arquivo: file.name,
                status: 'em_andamento',
                iniciado_em: new Date().toISOString()
            };
            salvarTranscricoesLocais();
            
            adicionarStatusHistorico('Arquivo enviado com sucesso', 'success');
            
            // Conecta ao WebSocket
            conectarWebSocket();

        } catch (error) {
            console.error('Erro:', error);
            statusText.textContent = 'Erro ao iniciar transcrição. Tente novamente.';
            adicionarStatusHistorico(`Erro: ${error.message}`, 'error');
            toggleProgress(false);
        }
    }

    // Função para retomar transcrição
    async function retomarTranscricao() {
        adicionarStatusHistorico(`Tentando retomar transcrição ID: ${transcricaoId}`, 'info');
        hideAskAiSection();
        
        if (!transcricaoId) {
            alert('Nenhuma transcrição selecionada para retomar');
            return;
        }
        
        try {
            toggleProgress(true, 0);
            statusText.textContent = 'Verificando status da transcrição...';
            adicionarStatusHistorico('Iniciando processo de retomada', 'info');
            
            const response = await fetch(`/retomar-transcricao/${transcricaoId}`, {
                method: 'POST'
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Erro ao retomar transcrição');
            }

            const data = await response.json();
            console.log('Resposta de retomada:', data);
            
            // Verifica se a transcrição já estava concluída
            if (data.status === 'concluida') {
                adicionarStatusHistorico('Transcrição já estava concluída!', 'success');
                statusText.textContent = 'Transcrição já estava completa!';
                
                // Atualiza interface diretamente
                transcricaoTexto.textContent = data.texto || 'Texto não disponível';
                transcricaoTitulo.textContent = 'Transcrição Completa';
                
                // Atualiza dados locais
                if (transcricoesAtivas[transcricaoId]) {
                    transcricoesAtivas[transcricaoId].status = 'concluida';
                    transcricoesAtivas[transcricaoId].texto = data.texto;
                    salvarTranscricoesLocais();
                }
                
                // Habilita botões apropriados
                btnBaixar.classList.remove('d-none');
                gerarInsightsBtn.disabled = false;
                btnFalar.classList.remove('d-none');
                btnRetomar.classList.add('d-none');
                
                showAskAiSection();
                toggleProgress(false);
                return;
            }
            
            // Se não está concluída, inicia processo de retomada
            clientId = data.client_id;
            
            // Atualiza dados locais com informações de retomada
            if (transcricoesAtivas[transcricaoId]) {
                transcricoesAtivas[transcricaoId].status = 'preparando_retomada';
                transcricoesAtivas[transcricaoId].client_id = clientId;
                
                // Se há progresso anterior, mostra na interface
                if (data.progresso_anterior && data.texto_parcial) {
                    transcricoesAtivas[transcricaoId].texto = data.texto_parcial;
                    transcricaoTexto.textContent = data.texto_parcial;
                    adicionarStatusHistorico(`Progresso anterior encontrado: ${data.texto_parcial.length} caracteres`, 'info');
                }
                
                salvarTranscricoesLocais();
            }
            
            statusText.textContent = 'Reconectando para retomar...';
            adicionarStatusHistorico('Preparando reconexão WebSocket...', 'info');
            
            // Esconde botão de retomar e mostra cancelar
            btnRetomar.classList.add('d-none');
            btnCancelar.classList.remove('d-none');
            
            // Reconecta ao WebSocket
            conectarWebSocket();
            
            adicionarStatusHistorico('Retomada iniciada com sucesso', 'success');

        } catch (error) {
            console.error('Erro ao retomar:', error);
            statusText.textContent = `Erro: ${error.message}`;
            adicionarStatusHistorico(`Erro ao retomar: ${error.message}`, 'error');
            toggleProgress(false);
            
            // Mantém botão de retomar visível em caso de erro
            btnRetomar.classList.remove('d-none');
        }
    }

    // Função para baixar transcrição
    function baixarTranscricao() {
        const texto = transcricaoTexto.textContent;
        if (!texto || texto === 'Nenhuma transcrição disponível') {
            alert('Não há transcrição para baixar');
            return;
        }
        
        // Cria um blob e link para download
        const blob = new Blob([texto], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `transcricao_${new Date().getTime()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // Event listener para mudança de modelo
    modeloSelect.addEventListener('change', async function(e) {
        const novoModelo = e.target.value;
        await mudarModelo(novoModelo);
    });

    // Event listener para o formulário do YouTube
    youtubeForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        const url = document.getElementById('youtube-url').value;
        await iniciarTranscricaoYoutube(url);
    });

    // Event listener para o formulário de arquivo local
    arquivoForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        const file = document.getElementById('video-file').files[0];
        if (!file) {
            alert('Por favor, selecione um arquivo.');
            return;
        }
        await iniciarTranscricaoArquivo(file);
    });

    // Event listener para o botão de gerar insights
    gerarInsightsBtn.addEventListener('click', async function() {
        try {
            gerarInsightsBtn.disabled = true;
            statusText.textContent = 'Gerando insights...';
            toggleProgress(true);

            // Usa o transcricaoId atual, se disponível
            let url = '/generate-insights';
            if (transcricaoId) {
                url += `?transcricao_id=${transcricaoId}`;
            }

            const response = await fetch(url);
            if (!response.ok) {
                throw new Error('Erro ao gerar insights');
            }

            const data = await response.json();
            insightsTexto.textContent = data.insights;
            statusText.textContent = 'Insights gerados com sucesso!';

            setTimeout(() => {
                toggleProgress(false);
            }, 1000);

        } catch (error) {
            console.error('Erro:', error);
            statusText.textContent = 'Erro ao gerar insights. Tente novamente.';
            insightsTexto.textContent = 'Erro ao processar os insights.';
        } finally {
            gerarInsightsBtn.disabled = false;
        }
    });

    // Event listener para o botão de cancelar
    btnCancelar.addEventListener('click', function() {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({
                acao: 'cancelar'
            }));
        }
    });

    // Event listener para o botão de retomar
    btnRetomar.addEventListener('click', function() {
        retomarTranscricao();
    });

    // Event listener para o botão de baixar
    btnBaixar.addEventListener('click', function() {
        baixarTranscricao();
    });

    // Função para mostrar seção de clonagem de voz
    function mostrarClonagemVoz(texto) {
        clonagemVozSection.classList.remove('d-none');
        textoParaAudio.value = texto;
        btnPlayAudio.classList.add('d-none');
        btnDownloadAudio.classList.add('d-none');
        if (audioPlayer) {
            audioPlayer.pause();
            audioPlayer = null;
        }
        if (audioUrl) {
            URL.revokeObjectURL(audioUrl);
            audioUrl = null;
        }
    }

    // Event listener para o formulário de clonagem de voz
    clonagemVozForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const amostraVoz = document.getElementById('amostra-voz').files[0];
        if (!amostraVoz) {
            alert('Por favor, selecione um arquivo de áudio com sua voz.');
            return;
        }
        
        try {
            // Prepara os dados
            const formData = new FormData();
            formData.append('file', amostraVoz);
            formData.append('texto', textoParaAudio.value);
            formData.append('transcricao_id', transcricaoId);
            
            // Mostra status
            audioStatus.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-hourglass-split"></i> Gerando áudio com sua voz...
                </div>
            `;
            
            // Envia para o servidor
            const response = await fetch('/clonar-voz', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Erro ao gerar áudio');
            }
            
            const data = await response.json();
            
            // Cria player de áudio
            if (audioPlayer) {
                audioPlayer.pause();
            }
            
            audioPlayer = new Audio(data.arquivo);
            btnPlayAudio.classList.remove('d-none');
            btnDownloadAudio.classList.remove('d-none');
            
            audioStatus.innerHTML = `
                <div class="alert alert-success">
                    <i class="bi bi-check-circle"></i> Áudio gerado com sucesso!
                </div>
            `;
            
        } catch (error) {
            console.error('Erro:', error);
            audioStatus.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i> Erro ao gerar áudio: ${error.message}
                </div>
            `;
        }
    });

    // Event listener para o botão de play
    btnPlayAudio.addEventListener('click', function() {
        if (audioPlayer) {
            if (audioPlayer.paused) {
                audioPlayer.play();
                this.innerHTML = '<i class="bi bi-pause-circle"></i> Pausar';
            } else {
                audioPlayer.pause();
                this.innerHTML = '<i class="bi bi-play-circle"></i> Reproduzir';
            }
        }
    });

    // Event listener para o botão de download
    btnDownloadAudio.addEventListener('click', async function() {
        try {
            const response = await fetch(`/download-audio/${transcricaoId}`);
            if (!response.ok) throw new Error('Erro ao baixar áudio');
            
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = `audio_clonado_${transcricaoId}.wav`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Erro:', error);
            alert('Erro ao baixar o áudio');
        }
    });

    // Função para converter texto em fala
    async function converterParaFala() {
        const texto = document.getElementById('transcricao-texto').textContent;
        if (!texto || texto === 'Nenhuma transcrição disponível') {
            alert('Nenhum texto disponível para converter em fala.');
            return;
        }

        try {
            btnFalar.disabled = true;
            btnFalar.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Gerando áudio...';

            const response = await fetch('/text-to-speech/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ text: texto })
            });

            if (!response.ok) {
                throw new Error('Erro ao gerar áudio');
            }

            const blob = await response.blob();
            audioUrl = URL.createObjectURL(blob);
            
            // Atualiza o player de áudio
            audioElement.src = audioUrl;
            audioPlayerContainer.classList.remove('d-none');
            
            // Extrai o nome do arquivo do header Content-Disposition
            const contentDisposition = response.headers.get('Content-Disposition');
            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
                if (filenameMatch) {
                    currentAudioFile = filenameMatch[1];
                }
            }

        } catch (error) {
            console.error('Erro:', error);
            alert('Erro ao gerar áudio. Por favor, tente novamente.');
        } finally {
            btnFalar.disabled = false;
            btnFalar.innerHTML = '<i class="bi bi-volume-up"></i> Converter para Fala';
        }
    }

    // Função para baixar o áudio gerado
    async function baixarAudio() {
        if (!currentAudioFile) {
            alert('Nenhum áudio disponível para download.');
            return;
        }

        try {
            const response = await fetch(`/get-audio/${currentAudioFile}`);
            if (!response.ok) {
                throw new Error('Erro ao baixar áudio');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = currentAudioFile;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();
        } catch (error) {
            console.error('Erro:', error);
            alert('Erro ao baixar áudio. Por favor, tente novamente.');
        }
    }

    // Event listeners
    btnFalar.addEventListener('click', converterParaFala);
    btnBaixarAudio.addEventListener('click', baixarAudio);

    // Função para mostrar o botão de fala quando houver uma transcrição
    function atualizarTranscricao(texto) {
        // ... código existente ...
        
        // Mostra o botão de converter para fala
        if (texto && texto !== 'Nenhuma transcrição disponível') {
            btnFalar.classList.remove('d-none');
        } else {
            btnFalar.classList.add('d-none');
            audioPlayerContainer.classList.add('d-none');
        }
    }

    // Funções para mostrar/ocultar/limpar a seção 'Ask AI' (Adicionado)
    function showAskAiSection() {
        askAiSection.classList.remove('d-none');
        aiQuestionInput.value = ''; // Limpa campo
        aiResponseArea.innerHTML = 'Aguardando sua pergunta...'; // Limpa resposta anterior
        askAiButton.disabled = false; // Habilita botão
    }

    function hideAskAiSection() {
        askAiSection.classList.add('d-none');
    }

    function setAiLoading(isLoading) {
        if (isLoading) {
            aiResponseArea.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"><span class="visually-hidden">Carregando...</span></div> Gerando resposta...';
            askAiButton.disabled = true;
        } else {
            askAiButton.disabled = false;
            // Não limpa a área aqui, a resposta será preenchida
        }
    }

    // Event listener para o novo botão 'Ask AI' (Adicionado)
    askAiButton.addEventListener('click', async function() {
        const pergunta = aiQuestionInput.value.trim();
        if (!pergunta) {
            alert('Por favor, digite sua pergunta.');
            aiQuestionInput.focus();
            return;
        }
        
        if (!transcricaoId) {
            alert('Erro: ID da transcrição não encontrado.');
            return;
        }

        setAiLoading(true);
        currentAiRequestId++; // Incrementa ID da requisição
        const thisRequestId = currentAiRequestId;
        adicionarStatusHistorico(`Enviando pergunta para IA (ID: ${transcricaoId}): "${pergunta}"`, 'info');

        try {
            const response = await fetch('/generate-insights', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    transcricao_id: transcricaoId,
                    pergunta: pergunta
                }),
            });

            // Só atualiza a interface se esta for a resposta da última requisição enviada
            if (thisRequestId === currentAiRequestId) {
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || `Erro ${response.status}`);
                }
                
                const data = await response.json();
                aiResponseArea.textContent = data.insights || 'Nenhuma resposta recebida.';
                adicionarStatusHistorico(`Resposta da IA recebida.`, 'success');
            } else {
                 console.log("Resposta da IA ignorada (requisição antiga).");
                 adicionarStatusHistorico(`Resposta da IA ignorada (requisição antiga ID ${thisRequestId}).`, 'warning');
            }

        } catch (error) {
             console.error('Erro ao enviar pergunta à IA:', error);
             adicionarStatusHistorico(`Erro ao gerar resposta da IA: ${error.message}`, 'error');
             // Só atualiza a interface se esta for a resposta da última requisição enviada
             if (thisRequestId === currentAiRequestId) {
                 aiResponseArea.textContent = `Erro ao obter resposta: ${error.message}`;
             }
        } finally {
             // Só reabilita se esta for a última requisição
             if (thisRequestId === currentAiRequestId) {
                 setAiLoading(false);
             }
        }
    });

    // Inicializa: carrega transcrições salvas localmente
    carregarTranscricoesLocais();

    // Limpa campo de URL do YouTube ao mostrar a aba
    const youtubeTab = document.getElementById('youtube-tab');
    youtubeTab.addEventListener('shown.bs.tab', function () {
        document.getElementById('youtube-url').value = '';
    });

    // Limpa campo de arquivo ao mostrar a aba
    const arquivoTab = document.getElementById('arquivo-tab');
    arquivoTab.addEventListener('shown.bs.tab', function () {
        document.getElementById('video-file').value = '';
    });

    // Adiciona status inicial
    adicionarStatusHistorico("Interface carregada.", "info");
}); 