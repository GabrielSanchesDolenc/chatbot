// script.js
if (!String.prototype.normalize) {
  String.prototype.normalize = function() {
    return this.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  };
}

const chat = document.getElementById('chat');
const form = document.getElementById('form');
const input = document.getElementById('pergunta');
const sendBtn = document.getElementById('send');
const statusEl = document.getElementById('status');

// Variáveis globais
let ultimoContexto = null;
let carrinhoItens = [];

// Inicialização
function inicializar() {
    // Verificar se há carrinho salvo no localStorage
    const carrinhoSalvo = localStorage.getItem('carrinho');
    if (carrinhoSalvo) {
        carrinhoItens = JSON.parse(carrinhoSalvo);
        atualizarContadorCarrinho();
    }
    
    // Adicionar event listeners
    form.addEventListener('submit', handleFormSubmit);
    sendBtn.addEventListener('click', handleFormSubmit);
    
    // Mensagem de boas-vindas
    setTimeout(() => {
        addMsg('Olá! Sou seu assistente virtual. Como posso ajudar?', 'bot');
    }, 500);
}

// Função para prevenir recarregamento
function handleFormSubmit(e) {
    e.preventDefault();
    submitQuestion();
}

async function submitQuestion() {
    const text = input.value.trim();
    if (!text) return;

    addMsg(text, 'user');
    input.value = '';
    input.focus();

    sendBtn.disabled = true;
    statusEl.textContent = 'digitando...';
    const typing = addTyping();

    try {
        const res = await fetch('/perguntar', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: new URLSearchParams({ pergunta: text })
        });
        
        if (!res.ok) throw new Error(`Erro HTTP: ${res.status}`);
        
        const data = await res.json();
        typing.remove();
        statusEl.textContent = 'online';

        // Armazenar contexto para possível confirmação
        ultimoContexto = {
            pergunta: text,
            tipo: data.status,
            dados: data
        };

        // Processar diferentes tipos de resposta
        switch(data.status) {
            case 'ask_accept':
                mostrarConfirmacao(data);
                break;
            case 'ask_accept_product':
                mostrarConfirmacaoProduto(data);
                break;
            case 'categoria_encontrada':
                mostrarProdutosCategoria(data);
                break;
            case 'carrinho':
                mostrarCarrinho(data);
                break;
            case 'finalizar_compra':
                finalizarCompra(data);
                break;
            case 'teach':
                pedirEnsino(text);
                break;
            case 'ok':
                addMsg(data.answer, 'bot');
                break;
            default:
                addMsg('Resposta não reconhecida: ' + JSON.stringify(data), 'bot');
        }
    } catch (err) {
        typing.remove();
        statusEl.textContent = 'offline';
        addMsg('Erro de conexão. Tente novamente.', 'bot');
        console.error(err);
    } finally {
        sendBtn.disabled = false;
    }
}

// Função para mostrar confirmação de resposta geral
function mostrarConfirmacao(data) {
    const wrap = addMsg(data.suggested_answer, 'bot', 'resposta sugerida');
    
    // Adicionar mensagem de confirmação clara
    const confirmacaoMsg = document.createElement('div');
    confirmacaoMsg.innerHTML = '<br><strong>✅ Esta resposta está correta?</strong>';
    wrap.querySelector('.text').appendChild(confirmacaoMsg);
    
    const btnContainer = document.createElement('div');
    btnContainer.style.marginTop = '10px';
    btnContainer.className = 'confirmation-buttons';

    // Botão Sim
    const btnYes = document.createElement('button');
    btnYes.className = 'btn confirm-yes';
    btnYes.textContent = '✅ Sim, está certo';
    btnYes.onclick = () => confirmarResposta(data);

    // Botão Não
    const btnNo = document.createElement('button');
    btnNo.className = 'btn confirm-no';
    btnNo.textContent = '❌ Não, está errado';
    btnNo.onclick = () => rejeitarResposta(data);

    btnContainer.append(btnYes, btnNo);
    wrap.querySelector('.text').appendChild(btnContainer);
}

// Função para mostrar confirmação de produto
function mostrarConfirmacaoProduto(data) {
    const wrap = addMsg(data.suggested_answer, 'bot', 'produto encontrado');
    
    // Adicionar mensagem de confirmação clara
    const confirmacaoMsg = document.createElement('div');
    confirmacaoMsg.innerHTML = '<br><strong>✅ Este produto está correto?</strong>';
    wrap.querySelector('.text').appendChild(confirmacaoMsg);
    
    const btnContainer = document.createElement('div');
    btnContainer.style.marginTop = '10px';
    btnContainer.className = 'confirmation-buttons';

    // Botão Sim - Adicionar ao carrinho
    const btnYes = document.createElement('button');
    btnYes.className = 'btn confirm-yes';
    btnYes.textContent = '✅ Sim, adicionar ao carrinho';
    btnYes.onclick = () => adicionarAoCarrinho(data.product);

    // Botão Não
    const btnNo = document.createElement('button');
    btnNo.className = 'btn confirm-no';
    btnNo.textContent = '❌ Não, procurar outro';
    btnNo.onclick = () => rejeitarResposta(data);

    btnContainer.append(btnYes, btnNo);
    wrap.querySelector('.text').appendChild(btnContainer);
}

// Função para mostrar produtos de uma categoria
function mostrarProdutosCategoria(data) {
    const wrap = addMsg(data.suggested_answer, 'bot', `categoria: ${data.category_name}`);
    
    const produtosContainer = document.createElement('div');
    produtosContainer.style.marginTop = '15px';
    produtosContainer.className = 'products-grid';
    
    // Adicionar cada produto como um botão
    data.products.forEach((produto, index) => {
        const produtoBtn = document.createElement('button');
        produtoBtn.className = 'product-btn';
        produtoBtn.innerHTML = `
            <strong>${produto.nome_produto}</strong><br>
            <span>R$ ${produto.preco.toFixed(2)}</span>
        `;
        produtoBtn.onclick = () => adicionarAoCarrinho(produto);
        produtosContainer.appendChild(produtoBtn);
        
        // Adicionar quebra de linha a cada 2 produtos
        if ((index + 1) % 2 === 0) {
            produtosContainer.appendChild(document.createElement('br'));
        }
    });
    
    wrap.querySelector('.text').appendChild(produtosContainer);
}

// Função para adicionar produto ao carrinho
async function adicionarAoCarrinho(produto) {
    addMsg(`Quero adicionar "${produto.nome_produto}" ao carrinho.`, 'user');
    
    const typing = addTyping();
    try {
        const res = await fetch('/carrinho/adicionar', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: new URLSearchParams({ product_id: produto.id })
        });
        
        const data = await res.json();
        typing.remove();
        
        if (data.status === 'ok') {
            // Atualizar carrinho local
            carrinhoItens.push({...produto, quantity: 1});
            localStorage.setItem('carrinho', JSON.stringify(carrinhoItens));
            atualizarContadorCarrinho();
            
            addMsg(data.message, 'bot');
            
            // Perguntar se quer ver o carrinho
            const wrap = addMsg('Deseja ver seu carrinho ou continuar comprando?', 'bot');
            
            const btnContainer = document.createElement('div');
            btnContainer.style.marginTop = '10px';
            btnContainer.className = 'confirmation-buttons';
            
            const btnCarrinho = document.createElement('button');
            btnCarrinho.className = 'btn';
            btnCarrinho.textContent = '🛒 Ver Carrinho';
            btnCarrinho.onclick = () => verCarrinho();
            
            const btnContinuar = document.createElement('button');
            btnContinuar.className = 'btn';
            btnContinuar.textContent = '➡️ Continuar Comprando';
            btnContinuar.onclick = () => addMsg('Ok, o que mais você deseja?', 'bot');
            
            btnContainer.append(btnCarrinho, btnContinuar);
            wrap.querySelector('.text').appendChild(btnContainer);
        } else {
            addMsg('Erro: ' + data.message, 'bot');
        }
    } catch(e) {
        typing.remove();
        addMsg('Erro de conexão ao adicionar ao carrinho.', 'bot');
        console.error(e);
    }
}

// Função para ver carrinho
async function verCarrinho() {
    addMsg('Quero ver meu carrinho.', 'user');
    
    const typing = addTyping();
    try {
        const res = await fetch('/carrinho');
        const data = await res.json();
        typing.remove();
        
        if (data.status === 'ok') {
            mostrarCarrinho(data);
        } else {
            addMsg('Erro ao carregar carrinho: ' + data.message, 'bot');
        }
    } catch(e) {
        typing.remove();
        addMsg('Erro de conexão ao carregar carrinho.', 'bot');
        console.error(e);
    }
}

// Função para mostrar carrinho
function mostrarCarrinho(data) {
    if (data.cart && data.cart.length > 0) {
        const wrap = addMsg(data.summary, 'bot', 'seu carrinho');
        
        // Adicionar botões de ação do carrinho
        const btnContainer = document.createElement('div');
        btnContainer.style.marginTop = '15px';
        btnContainer.className = 'cart-actions';
        
        const btnFinalizar = document.createElement('button');
        btnFinalizar.className = 'btn confirm-yes';
        btnFinalizar.textContent = '✅ Finalizar Compra';
        btnFinalizar.onclick = () => finalizarCompra();
        
        const btnLimpar = document.createElement('button');
        btnLimpar.className = 'btn confirm-no';
        btnLimpar.textContent = '🗑️ Limpar Carrinho';
        btnLimpar.onclick = () => limparCarrinho();
        
        btnContainer.append(btnFinalizar, btnLimpar);
        wrap.querySelector('.text').appendChild(btnContainer);
    } else {
        addMsg('Seu carrinho está vazio. Que tal dar uma olhada em nossos produtos?', 'bot');
    }
}

// Função para limpar carrinho
async function limparCarrinho() {
    addMsg('Quero limpar meu carrinho.', 'user');
    
    const typing = addTyping();
    try {
        const res = await fetch('/carrinho/limpar', {
            method: 'POST'
        });
        
        const data = await res.json();
        typing.remove();
        
        if (data.status === 'ok') {
            // Limpar carrinho local
            carrinhoItens = [];
            localStorage.removeItem('carrinho');
            atualizarContadorCarrinho();
            
            addMsg(data.message, 'bot');
        } else {
            addMsg('Erro: ' + data.message, 'bot');
        }
    } catch(e) {
        typing.remove();
        addMsg('Erro de conexão ao limpar carrinho.', 'bot');
        console.error(e);
    }
}

// Função para finalizar compra
async function finalizarCompra(data = null) {
    if (!data) {
        addMsg('Quero finalizar minha compra.', 'user');
    }
    
    const typing = addTyping();
    try {
        const res = await fetch('/finalizar-compra', {
            method: 'POST'
        });
        
        const data = await res.json();
        typing.remove();
        
        if (data.status === 'ok') {
            // Limpar carrinho local
            carrinhoItens = [];
            localStorage.removeItem('carrinho');
            atualizarContadorCarrinho();
            
            // Mostrar resumo da compra
            const wrap = addMsg(data.resumo, 'bot', 'compra finalizada');
            
            // Adicionar botão para nova compra
            const btnContainer = document.createElement('div');
            btnContainer.style.marginTop = '15px';
            
            const btnNovaCompra = document.createElement('button');
            btnNovaCompra.className = 'btn confirm-yes';
            btnNovaCompra.textContent = '🛍️ Fazer Nova Compra';
            btnNovaCompra.onclick = () => {
                addMsg('Vamos fazer uma nova compra! O que você está procurando?', 'bot');
            };
            
            btnContainer.appendChild(btnNovaCompra);
            wrap.querySelector('.text').appendChild(btnContainer);
        } else {
            addMsg('Erro: ' + data.message, 'bot');
        }
    } catch(e) {
        typing.remove();
        addMsg('Erro de conexão ao finalizar compra.', 'bot');
        console.error(e);
    }
}

// Atualizar contador de itens no carrinho
function atualizarContadorCarrinho() {
    const cartCount = document.getElementById('cart-count');
    if (cartCount) {
        cartCount.textContent = carrinhoItens.length;
        cartCount.style.display = carrinhoItens.length > 0 ? 'inline-flex' : 'none';
    }
}

// Confirmar resposta (para respostas não relacionadas a produtos)
async function confirmarResposta(data) {
    addMsg('Sim, está correto.', 'user');
    
    const typing = addTyping();
    try {
        const params = {
            pergunta_usuario: ultimoContexto.pergunta,
            resposta_confirmada: data.suggested_answer,
            intent: data.intent || 'unknown'
        };

        const res = await fetch('/confirmar', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: new URLSearchParams(params)
        });
        
        const result = await res.json();
        typing.remove();
        
        if (result.status === 'ok') {
            addMsg('Obrigado pela confirmação! Aprendi com sua resposta.', 'bot');
        } else {
            addMsg('Erro ao confirmar: ' + result.message, 'bot');
        }
    } catch(e) {
        typing.remove();
        addMsg('Erro de conexão ao confirmar.', 'bot');
        console.error(e);
    }
}

// Rejeitar resposta
async function rejeitarResposta(data) {
    addMsg('Não, está incorreto.', 'user');
    
    // Se for um produto, tentar buscar alternativas
    if (data.is_product) {
        addMsg('Vou tentar encontrar outra opção...', 'bot');
        // Buscar alternativas (implementar lógica se necessário)
        setTimeout(() => pedirEnsino(ultimoContexto.pergunta), 1000);
    } else {
        pedirEnsino(ultimoContexto.pergunta);
    }
}

// Pedir para ensinar uma resposta
function pedirEnsino(pergunta) {
    const wrap = addMsg('Não sei responder. Pode me ensinar?', 'bot');
    const box = document.createElement('div');
    box.style.marginTop = '10px';

    const inAns = document.createElement('input');
    inAns.type = 'text';
    inAns.placeholder = 'Resposta correta';
    styleInput(inAns);

    const inIntent = document.createElement('input');
    inIntent.type = 'text';
    inIntent.placeholder = 'Etiqueta de intenção (opcional)';
    styleInput(inIntent);

    const btnSave = document.createElement('button');
    btnSave.className = 'btn';
    btnSave.textContent = 'Salvar';
    btnSave.onclick = () => salvarEnsino(pergunta, inAns.value, inIntent.value);

    box.append(inAns, document.createElement('br'), inIntent, document.createElement('br'), btnSave);
    wrap.querySelector('.text').appendChild(box);
    chat.scrollTop = chat.scrollHeight;
}

// Salvar ensino
async function salvarEnsino(pergunta, resposta, intent) {
    if(!resposta?.trim()) {
        addMsg('Digite a resposta antes de salvar.', 'bot');
        return;
    }
    const typing = addTyping();
    try {
        const res = await fetch('/ensinar', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: new URLSearchParams({ pergunta, resposta, intent })
        });
        const data = await res.json();
        typing.remove();
        addMsg(data.message || 'Aprendido com sucesso!', 'bot');
    } catch(e) {
        typing.remove();
        addMsg('Falha ao salvar. Tente novamente.', 'bot');
        console.error(e);
    }
}

// Funções auxiliares de UI
function addMsg(text, who = 'bot', meta = '') {
    const wrap = document.createElement('div');
    wrap.className = `msg ${who}`;
    wrap.innerHTML = `
        <div class="text">${escapeHtml(text)}</div>
        <div class="meta">
            <span class="time">${timeNow()}</span>
            ${meta ? `<span class="extra">${escapeHtml(meta)}</span>` : ''}
        </div>
    `;
    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
    return wrap;
}

function addTyping() {
    const wrap = document.createElement('div');
    wrap.className = 'msg bot';
    wrap.innerHTML = `
        <div class="typing">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
        <div class="meta"><span class="time">${timeNow()}</span></div>
    `;
    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
    return wrap;
}

function timeNow() {
    const d = new Date();
    return d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
}

function escapeHtml(s) {
    if (typeof s !== 'string') return '';
    return s.replace(/[&<>"']/g, c => ({
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
}

function styleInput(el) {
    el.style.width = '100%';
    el.style.margin = '6px 0';
    el.style.padding = '10px 12px';
    el.style.borderRadius = '10px';
    el.style.border = '1px solid var(--border)';
    el.style.background = 'var(--panel-2)';
    el.style.color = 'var(--text)';
}

// Inicializar quando o documento estiver pronto
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inicializar);
} else {
    inicializar();
}