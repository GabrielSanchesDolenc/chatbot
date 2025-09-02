const chat = document.getElementById('chat');
const form = document.getElementById('form');
const input = document.getElementById('pergunta');
const sendBtn = document.getElementById('send');
const statusEl = document.getElementById('status');

// Adicione esta função para prevenir recarregamento
function handleFormSubmit(e) {
    e.preventDefault();
    submitQuestion();
}

// Mova a lógica de submit para uma função separada
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
    const data = await res.json();

    typing.remove();
    statusEl.textContent = 'online';

    // Adicione um log para debug (pode remover depois)
    console.log('Resposta do servidor:', data);

    if (data.status === 'ok') {
        // Verifica se é uma resposta de produto ou do dataset
        if (data.is_product) {
            addMsg(data.answer, 'bot', data.reason || 'produto encontrado');
        } else {
            addMsg(data.answer, 'bot', data.reason || '');
        }
    } 
      else if (data.status === 'ask_accept') {
          const perguntaSug = data.suggested_question || data.suggested_product || '';
          const isProduct = !!data.suggested_product;
          const respostaParaSalvar = data.clean_answer || data.suggested_answer;
          
          const wrap = addMsg(
              data.suggested_answer || 'Achei algo parecido, deseja confirmar?',
              'bot',
              data.score ? `similaridade ${data.score.toFixed(2)}` : ''
          );
          
          const btnContainer = document.createElement('div');
          btnContainer.style.marginTop = '10px';

          const btnYes = document.createElement('button');
          btnYes.className = 'btn';
          btnYes.textContent = 'Sim';
          btnYes.onclick = () => confirmarResposta(respostaParaSalvar, perguntaSug, isProduct);

          const btnNo = document.createElement('button');
          btnNo.className = 'btn';
          btnNo.style.marginLeft = '8px';
          btnNo.textContent = 'Não';
          btnNo.onclick = () => pedirEnsino(text);

          btnContainer.append(btnYes, btnNo);
          wrap.querySelector('.text').appendChild(btnContainer);
      } 
      else if (data.status === 'teach') {
          pedirEnsino(text);
      } 
      else {
          addMsg('Não entendi a resposta do servidor: ' + JSON.stringify(data), 'bot');
      }
  } catch (err) {
      typing.remove();
      statusEl.textContent = 'offline';
      addMsg('Erro ao conectar com o servidor.', 'bot');
      console.error(err);
   } finally {
        sendBtn.disabled = false;
    }
}

// Altere o event listener para usar a nova função
form.addEventListener('submit', handleFormSubmit);

// Adicione também um event listener para o botão de enviar
sendBtn.addEventListener('click', handleFormSubmit);

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

function escapeHtml(s){
    return s.replace(/[&<>"']/g, c => ({
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
}

async function confirmarResposta(suggested_answer, suggested_question, isProduct = false){
    const userMessages = document.querySelectorAll('.msg.user');
    const lastUserMessage = userMessages[userMessages.length - 1];
    const pergunta_usuario = lastUserMessage.querySelector('.text').textContent;
    
    addMsg('Sim, use essa resposta.', 'user');
    const typing = addTyping();
    try {
        const params = {
            pergunta_usuario: pergunta_usuario,
            pergunta_similar: suggested_question,
            resposta_confirmada: suggested_answer
        };
        
        // Adiciona intent apenas para produtos
        if (isProduct) {
            params.intent = 'consulta_estoque';
        }
        
        const res = await fetch('/confirmar', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: new URLSearchParams(params)
        });
        const data = await res.json();
        typing.remove();
        if (data.status === 'ok') {
            addMsg(data.message || 'Resposta confirmada e salva!', 'bot', 'confirmada pelo usuário');
        } else {
            addMsg('Erro: ' + (data.message || 'Não consegui confirmar'), 'bot');
        }
    } catch(e){
        typing.remove();
        addMsg('Erro de conexão. Tente de novo.', 'bot');
        console.error(e);
    }
}

function pedirEnsino(pergunta){
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

function styleInput(el){
    el.style.width = '100%';
    el.style.margin = '6px 0';
    el.style.padding = '10px 12px';
    el.style.borderRadius = '10px';
    el.style.border = '1px solid var(--border)';
    el.style.background = 'var(--panel-2)';
    el.style.color = 'var(--text)';
}

async function salvarEnsino(pergunta, resposta, intent){
    if(!resposta?.trim()){
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
    } catch(e){
        typing.remove();
        addMsg('Falha ao salvar. Tente novamente.', 'bot');
        console.error(e);
    }
}