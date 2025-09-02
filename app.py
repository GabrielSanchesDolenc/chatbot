# app.py
from flask import Flask, render_template, request, jsonify, session
import os
import random
import pandas as pd
import unicodedata
import re
import json
import csv
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import joblib
from uuid import uuid4

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'

dataset_path = 'qa_dataset_improved.csv'
estoque_path = 'estoque_eletronicos.csv'
model_path = 'trained_model.joblib'
historico_compras_path = 'historico_compras.csv'
historico_interacoes_path = 'historico_interacoes.csv'

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

HIGH_SIM_THRESHOLD = 0.78
LOW_SIM_THRESHOLD = 0.50

# ---------------- INICIALIZAÇÃO DE ARQUIVOS ----------------
def inicializar_arquivos():
    # Criar arquivo de histórico de compras se não existir
    if not os.path.exists(historico_compras_path):
        with open(historico_compras_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['session_id', 'produtos', 'valor_total', 'data_hora'])
    
    # Criar arquivo de histórico de interações se não existir
    if not os.path.exists(historico_interacoes_path):
        with open(historico_interacoes_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['session_id', 'pergunta', 'resposta', 'intent', 'timestamp', 'confirmada'])

# ---------------- MELHORIAS: STOPWORDS E NORMALIZAÇÃO ----------------
stopwords_pt = set([
    'a', 'ao', 'aos', 'aquela', 'aquelas', 'aquele', 'aquiles', 'aquilo', 'as', 'até', 
    'com', 'como', 'da', 'das', 'de', 'dela', 'delas', 'dele', 'deles', 'depois', 
    'do', 'dos', 'e', 'ela', 'elas', 'ele', 'eles', 'em', 'entre', 'eu', 'isso', 
    'isto', 'já', 'lhe', 'lhes', 'mais', 'mas', 'me', 'mesmo', 'meu', 'meus', 
    'minha', 'minhas', 'na', 'nas', 'no', 'nos', 'nós', 'o', 'os', 'ou', 'para', 
    'pela', 'pelas', 'pelo', 'pelos', 'por', 'quando', 'que', 'quem', 'se', 'sem', 
    'só', 'sua', 'suas', 'também', 'te', 'tem', 'têm', 'teu', 'teus', 'tu', 'tua', 
    'tuas', 'um', 'uma', 'umas', 'você', 'vocês', 'vos', 'vosso', 'vossos', 'vossa', 'vossas'
])

def normalize_text(text: str, remove_stopwords: bool = True) -> str:
    if not isinstance(text, str):
        return ''
    nfkd = unicodedata.normalize('NFD', text)
    no_accents = ''.join([c for c in nfkd if unicodedata.category(c) != 'Mn'])
    s = re.sub(r'[^\w\s]', '', no_accents)
    s = re.sub(r'\s+', ' ', s).strip().lower()
    
    if remove_stopwords:
        words = s.split()
        words = [w for w in words if w not in stopwords_pt and len(w) > 2]
        s = ' '.join(words)
    
    return s

# ---------------- INICIALIZAÇÃO DA SESSÃO ----------------
@app.before_request
def before_request():
    if 'session_id' not in session:
        session['session_id'] = str(uuid4())
        session['cart'] = []
        session.permanent = True

# ---------------- LOGS E HISTÓRICOS ----------------
def log_interacao(pergunta, resposta, intent, confirmada=False):
    """Registra uma interação no histórico"""
    try:
        with open(historico_interacoes_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow([
                session.get('session_id', 'unknown'),
                pergunta,
                resposta,
                intent,
                datetime.now().isoformat(),
                confirmada
            ])
    except Exception as e:
        print(f"Erro ao registrar interação: {e}")

def log_compra(produtos, valor_total):
    """Registra uma compra no histórico"""
    try:
        with open(historico_compras_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow([
                session.get('session_id', 'unknown'),
                json.dumps(produtos),
                valor_total,
                datetime.now().isoformat()
            ])
    except Exception as e:
        print(f"Erro ao registrar compra: {e}")

# ---------------- CARRINHO DE COMPRAS ----------------
def get_cart():
    return session.get('cart', [])

def add_to_cart(product):
    cart = get_cart()
    # Verificar se o produto já está no carrinho
    for item in cart:
        if item['id'] == product['id']:
            item['quantity'] += 1
            session['cart'] = cart
            return True
    
    # Adicionar novo produto
    product['quantity'] = 1
    cart.append(product)
    session['cart'] = cart
    return True

def remove_from_cart(product_id):
    cart = get_cart()
    cart = [item for item in cart if item['id'] != product_id]
    session['cart'] = cart
    return True

def clear_cart():
    session['cart'] = []
    return True

def get_cart_total():
    cart = get_cart()
    total = sum(item['preco'] * item['quantity'] for item in cart)
    return total

def get_cart_summary():
    cart = get_cart()
    if not cart:
        return "Seu carrinho está vazio."
    
    summary = "🛒 **Carrinho de Compras**\n\n"
    for i, item in enumerate(cart, 1):
        summary += f"{i}. {item['nome_produto']} - R$ {item['preco']:.2f} x {item['quantity']}\n"
    
    summary += f"\n💵 **Total: R$ {get_cart_total():.2f}**"
    return summary

# ---------------- CARREGAR ESTOQUE ----------------
if os.path.exists(estoque_path):
    estoque_df = pd.read_csv(estoque_path, sep=';', encoding='utf-8-sig')
    estoque_df['normalized_produto'] = estoque_df['nome_produto'].apply(
        lambda x: normalize_text(x, remove_stopwords=False)
    )
else:
    # Criar estoque de exemplo se não existir
    estoque_df = pd.DataFrame({
        'id': [1, 2, 3, 4, 5],
        'nome_produto': ['Notebook Dell i5', 'Notebook HP i7', 'PC Gamer Ryzen 5', 'PC Gamer i7', 'Mouse Gamer'],
        'categoria': ['notebook', 'notebook', 'pc', 'pc', 'acessorio'],
        'quantidade': [10, 5, 8, 3, 20],
        'preco': [2500.00, 3200.00, 4500.00, 5200.00, 150.00],
        'normalized_produto': ['notebook dell i5', 'notebook hp i7', 'pc gamer ryzen 5', 'pc gamer i7', 'mouse gamer']
    })
    estoque_df.to_csv(estoque_path, index=False, sep=';', encoding='utf-8-sig')

# ---------------- DATASET COM MELHORIAS ----------------
def create_initial_dataset(path: str):
    perguntas = [
        "Qual é o jogo mais popular atualmente?",
        "Que produtos vocês têm disponíveis?",
        "Vocês vendem celulares?",
        "Quais marcas de computador vocês têm?",
        "Preciso de um notebook",
        "Tem iPhone?",
        "Quanto custa um Samsung?",
        "Vocês têm tablets?",
        "Como faço para comprar?",
        "Vocês entregam em casa?",
        "Quero ver meu carrinho",
        "Finalizar compra",
        "Adicionar ao carrinho",
        "Remover do carrinho",
        "Limpar carrinho"
    ]
    respostas = [
        "O jogo mais popular atualmente é League of Legends.",
        "Temos diversos produtos eletrônicos incluindo celulares, computadores e acessórios.",
        "Sim, temos uma variedade de celulares das melhores marcas.",
        "Trabalhamos com marcas como Apple, Samsung, Dell e HP.",
        "Temos vários modelos de notebook disponíveis. Qual marca você prefere?",
        "Sim, temos iPhones disponíveis. Qual modelo você está procurando?",
        "Temos vários modelos Samsung. Você pode especificar qual modelo?",
        "Sim, temos tablets das principais marcas.",
        "Você pode comprar online ou visitar nossa loja física.",
        "Sim, fazemos entregas em toda a cidade.",
        "Vou mostrar seu carrinho de compras.",
        "Vamos finalizar sua compra!",
        "Qual produto você gostaria de adicionar?",
        "Qual produto você gostaria de remover?",
        "Carrinho limpo com sucesso!"
    ]
    intents = ["informacao_jogo", "consulta_estoque", "consulta_estoque", "consulta_estoque", 
               "consulta_estoque", "consulta_estoque", "consulta_estoque", "consulta_estoque",
               "informacao_compra", "informacao_entrega", "ver_carrinho", "finalizar_compra",
               "adicionar_carrinho", "remover_carrinho", "limpar_carrinho"]
    now = datetime.utcnow().isoformat()
    df_init = pd.DataFrame({
        'question': perguntas,
        'answer': respostas,
        'intent': intents,
        'normalized_question': [normalize_text(q) for q in perguntas],
        'created_at': [now]*len(perguntas),
        'taught_by': ['seed']*len(perguntas)
    })
    df_init.to_csv(path, index=False, encoding='utf-8-sig')
    return df_init

if not os.path.exists(dataset_path):
    df = create_initial_dataset(dataset_path)
else:
    df = pd.read_csv(dataset_path, encoding='utf-8-sig')
    if 'normalized_question' not in df.columns:
        df['normalized_question'] = df['question'].apply(normalize_text)
    if 'created_at' not in df.columns:
        df['created_at'] = datetime.utcnow().isoformat()
    if 'taught_by' not in df.columns:
        df['taught_by'] = 'unknown'

def save_dataset(df: pd.DataFrame, path: str = dataset_path):
    df.to_csv(path, index=False, encoding='utf-8-sig')

# ---------------- MODELO SVC COM PIPELINE ----------------
def create_model():
    return make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=1),
        SVC(kernel='linear', probability=True, random_state=RANDOM_SEED)
    )

def train_model(df: pd.DataFrame):
    le = LabelEncoder()
    intents = df['intent'].fillna('unknown').astype(str).values
    labels = le.fit_transform(intents)
    
    pipeline = create_model()
    pipeline.fit(df['normalized_question'].values, labels)
    
    return {
        'pipeline': pipeline,
        'label_encoder': le
    }

def load_or_train_model():
    if os.path.exists(model_path):
        try:
            model_bundle = joblib.load(model_path)
            print("Modelo carregado do arquivo")
            return model_bundle
        except:
            print("Erro ao carregar modelo, treinando novo...")
            return train_model(df)
    else:
        print("Treinando novo modelo...")
        return train_model(df)

# Carregar ou treinar modelo
model_bundle = load_or_train_model()

def save_model():
    joblib.dump(model_bundle, model_path)

def add_to_dataset(pergunta, resposta, intent="unknown", taught_by="system"):
    global df, model_bundle
    
    q_norm = normalize_text(pergunta)
    now = datetime.utcnow().isoformat()
    
    new_row = {
        'question': pergunta,
        'answer': resposta,
        'intent': intent,
        'normalized_question': q_norm,
        'created_at': now,
        'taught_by': taught_by
    }
    
    # Adicionar ao DataFrame
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_dataset(df)
    
    # Retreinar o modelo completo
    model_bundle = train_model(df)
    save_model()
    
    return True

# ---------------- FUNÇÕES DE BUSCA MELHORADAS ----------------
def find_similar_questions(user_question: str, top_k: int = 3, allow_estoque=True):
    q_norm = normalize_text(user_question)
    
    # Usar o vectorizer do pipeline para calcular similaridade
    vect = model_bundle['pipeline'].named_steps['tfidfvectorizer']
    matrix = vect.transform(df['normalized_question'].values)
    q_vec = vect.transform([q_norm])
    
    sims = cosine_similarity(q_vec, matrix).flatten()
    idx_sorted = sims.argsort()[::-1]
    
    results = []
    for idx in idx_sorted[:top_k]:
        if sims[idx] < LOW_SIM_THRESHOLD:
            continue
            
        row = df.iloc[idx]
        intent = row.get('intent', '')
        
        # Filtrar intenções de estoque se não permitido
        if not allow_estoque and intent == "consulta_estoque":
            continue
            
        results.append({
            'index': int(idx),
            'score': float(sims[idx]),
            'question': row['question'],
            'answer': row['answer'],
            'intent': intent
        })
    
    return results

def buscar_produto(texto):
    texto_norm = normalize_text(texto, remove_stopwords=False)
    
    # Busca exata
    for idx, row in estoque_df.iterrows():
        produto_norm = row['normalized_produto']
        if produto_norm in texto_norm or texto_norm in produto_norm:
            return row.to_dict(), True
    
    # Busca por palavras-chave
    palavras_chave = texto_norm.split()
    produtos_encontrados = []
    
    for palavra in palavras_chave:
        if len(palavra) > 3:
            for idx, row in estoque_df.iterrows():
                if palavra in row['normalized_produto']:
                    produtos_encontrados.append((row.to_dict(), palavra))
    
    if produtos_encontrados:
        produtos_encontrados.sort(key=lambda x: len(x[1]), reverse=True)
        return produtos_encontrados[0][0], False
    
    return None, False

def buscar_produto_similar(texto):
    texto_norm = normalize_text(texto, remove_stopwords=False)
    
    if estoque_df.empty:
        return None
    
    # Busca por similaridade
    produtos = estoque_df['normalized_produto'].tolist()
    vect = TfidfVectorizer().fit(produtos)
    matriz = vect.transform(produtos)
    q_vec = vect.transform([texto_norm])
    sims = cosine_similarity(q_vec, matriz).flatten()
    idx = sims.argmax()
    
    if sims[idx] > 0.3:
        return estoque_df.iloc[idx].to_dict()
    
    return None

def buscar_por_categoria(texto):
    texto_norm = normalize_text(texto)
    categorias_disponiveis = estoque_df['categoria'].apply(
        lambda x: normalize_text(x, remove_stopwords=False)
    ).unique()
    
    categoria_encontrada = None
    for cat in categorias_disponiveis:
        if cat in texto_norm:
            categoria_encontrada = cat
            break
    
    if categoria_encontrada:
        produtos_categoria = estoque_df[
            estoque_df['categoria'].apply(
                lambda x: normalize_text(x, remove_stopwords=False)
            ) == categoria_encontrada
        ]
        return produtos_categoria.to_dict('records'), categoria_encontrada
    
    return None, None

def gerar_sugestoes(user_q):
    sugestoes = []
    
    # Buscar produtos primeiro
    produto, _ = buscar_produto(user_q)
    if produto is not None:
        sugestoes.append(f'O produto "{produto["nome_produto"]}" custa R$ {produto["preco"]:.2f}.')
    
    # Buscar por categoria
    produtos_categoria, categoria_nome = buscar_por_categoria(user_q)
    if produtos_categoria:
        sugestoes.append(f"Temos {len(produtos_categoria)} produtos na categoria '{categoria_nome}'")
    
    # Buscar perguntas similares
    sims = find_similar_questions(user_q, top_k=2, allow_estoque=True)
    for s in sims:
        if s['score'] > LOW_SIM_THRESHOLD:
            sugestoes.append(s['answer'])
    
    # Remover duplicatas
    return list(dict.fromkeys(sugestoes))

# ---------------- ROTAS PRINCIPAIS ----------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/perguntar', methods=['POST'])
def perguntar():
    user_q = request.form.get('pergunta')
    if not user_q:
        return jsonify({'status': 'error', 'message': 'Pergunta não fornecida'})

    # 1) Comandos do carrinho - não precisam de confirmação
    user_q_lower = user_q.lower()
    cart_commands = ['carrinho', 'cart', 'finalizar', 'comprar', 'adicionar', 'remover', 'limpar']
    
    if any(cmd in user_q_lower for cmd in cart_commands):
        if 'ver' in user_q_lower or 'mostrar' in user_q_lower:
            carrinho_data = {
                'status': 'carrinho',
                'carrinho': get_cart_summary(),
                'items': get_cart()
            }
            log_interacao(user_q, "Visualização do carrinho", "ver_carrinho", True)
            return jsonify(carrinho_data)
        elif 'limpar' in user_q_lower or 'esvaziar' in user_q_lower:
            clear_cart()
            log_interacao(user_q, "Carrinho limpo", "limpar_carrinho", True)
            return jsonify({
                'status': 'ok',
                'answer': 'Carrinho limpo com sucesso!',
                'is_cart_action': True
            })
        elif 'finalizar' in user_q_lower or 'comprar' in user_q_lower:
            compra_data = {
                'status': 'finalizar_compra',
                'resumo': get_cart_summary(),
                'total': get_cart_total(),
                'items': get_cart()
            }
            log_interacao(user_q, "Finalização de compra", "finalizar_compra", True)
            return jsonify(compra_data)

    # 2) Produto direto no estoque - precisa de confirmação
    produto, correspondencia_direta = buscar_produto(user_q)
    if produto is not None:
        resposta_completa = f'Encontrei: {produto["nome_produto"]} - R$ {produto["preco"]:.2f}'
        
        response_data = {
            'status': 'ask_accept_product',
            'suggested_answer': resposta_completa,
            'is_product': True,
            'product': produto,
            'product_name': produto['nome_produto'],
            'intent': 'consulta_estoque',
            'needs_confirmation': True,
            'suggestions': gerar_sugestoes(user_q)
        }
        
        # Log da interação (ainda não confirmada)
        log_interacao(user_q, resposta_completa, "consulta_estoque", False)
        return jsonify(response_data)

    # 3) Buscar por categoria (MELHORADO)
    produtos_categoria, categoria_nome = buscar_por_categoria(user_q)
    if produtos_categoria:
        resposta = f"Encontrei {len(produtos_categoria)} produtos na categoria '{categoria_nome}':\n"
        for i, produto in enumerate(produtos_categoria[:5], 1):
            resposta += f"{i}. {produto['nome_produto']} - R$ {produto['preco']:.2f}\n"
        
        if len(produtos_categoria) > 5:
            resposta += f"... e mais {len(produtos_categoria) - 5} produtos\n"
        
        resposta += "\nQual desses você quer adicionar ao carrinho?"
        
        response_data = {
            'status': 'categoria_encontrada',
            'suggested_answer': resposta,
            'is_category': True,
            'category_name': categoria_nome,
            'products': produtos_categoria[:10],
            'intent': 'consulta_estoque',
            'needs_confirmation': False,
            'show_products': True
        }
        
        # Log da interação
        log_interacao(user_q, resposta, "consulta_estoque", True)
        return jsonify(response_data)

    # 4) Produto similar - precisa de confirmação
    produto_similar = buscar_produto_similar(user_q)
    if produto_similar is not None:
        resposta_completa = f'Não encontrei exatamente, mas temos "{produto_similar["nome_produto"]}" por R$ {produto_similar["preco"]:.2f}.'
        
        response_data = {
            'status': 'ask_accept_product',
            'suggested_answer': resposta_completa,
            'is_product': True,
            'product': produto_similar,
            'product_name': produto_similar['nome_produto'],
            'intent': 'consulta_estoque',
            'needs_confirmation': True,
            'suggestions': gerar_sugestoes(user_q)
        }
        
        # Log da interação (ainda não confirmada)
        log_interacao(user_q, resposta_completa, "consulta_estoque", False)
        return jsonify(response_data)

    # 5) Buscar no dataset de perguntas e respostas - precisa de confirmação
    sims = find_similar_questions(user_q, top_k=3, allow_estoque=False)
    if sims and sims[0]['score'] > HIGH_SIM_THRESHOLD:
        response_data = {
            'status': 'ask_accept',
            'suggested_answer': sims[0]['answer'],
            'matched_question': sims[0]['question'],
            'score': sims[0]['score'],
            'intent': sims[0]['intent'],
            'needs_confirmation': True,
            'suggestions': gerar_sugestoes(user_q)
        }
        
        # Log da interação (ainda não confirmada)
        log_interacao(user_q, sims[0]['answer'], sims[0]['intent'], False)
        return jsonify(response_data)

    # 6) Nada encontrado - pedir para ensinar
    log_interacao(user_q, "Não sei responder", "unknown", False)
    return jsonify({
        'status': 'teach',
        'message': 'Não sei responder. Pode me ensinar?',
        'needs_confirmation': False,
        'suggestions': []
    })

@app.route('/confirmar', methods=['POST'])
def confirmar_resposta():
    pergunta_usuario = request.form.get('pergunta_usuario')
    resposta_confirmada = request.form.get('resposta_confirmada')
    intent = request.form.get('intent', 'unknown')
    
    if not pergunta_usuario or not resposta_confirmada:
        return jsonify({'status': 'error', 'message': 'Dados incompletos'})
    
    # Registrar no dataset com confirmação do usuário
    add_to_dataset(pergunta_usuario, resposta_confirmada, intent=intent, taught_by="user_confirmation")
    
    # Atualizar o log de interação para marcar como confirmada
    log_interacao(pergunta_usuario, resposta_confirmada, intent, True)
    
    return jsonify({'status': 'ok', 'message': 'Resposta confirmada e aprendida!'})

@app.route('/ensinar', methods=['POST'])
def ensinar():
    pergunta = request.form.get('pergunta')
    resposta = request.form.get('resposta')
    intent = request.form.get('intent', 'unknown')
    
    if not pergunta or not resposta:
        return jsonify({'status': 'error', 'message': 'Pergunta e resposta são obrigatórias'})
    
    # Adicionar ao dataset
    add_to_dataset(pergunta, resposta, intent=intent, taught_by="user_teach")
    
    # Registrar no log de interações
    log_interacao(pergunta, resposta, intent, True)
    
    return jsonify({'status': 'ok', 'message': 'Obrigado por me ensinar! Aprendi algo novo.'})

# ---------------- ROTAS DO CARRINHO ----------------
@app.route('/carrinho/adicionar', methods=['POST'])
def adicionar_carrinho():
    product_id = request.form.get('product_id')
    if not product_id:
        return jsonify({'status': 'error', 'message': 'ID do produto não fornecido'})
    
    # Buscar produto no estoque
    produto = estoque_df[estoque_df['id'] == int(product_id)]
    if produto.empty:
        return jsonify({'status': 'error', 'message': 'Produto não encontrado'})
    
    product_dict = produto.iloc[0].to_dict()
    add_to_cart(product_dict)
    
    # Registrar no log
    log_interacao(f"Adicionar produto ID {product_id}", f"Produto {product_dict['nome_produto']} adicionado ao carrinho", "adicionar_carrinho", True)
    
    return jsonify({
        'status': 'ok', 
        'message': f'Produto "{product_dict["nome_produto"]}" adicionado ao carrinho!',
        'cart_count': len(get_cart())
    })

@app.route('/carrinho/remover', methods=['POST'])
def remover_carrinho():
    product_id = request.form.get('product_id')
    if not product_id:
        return jsonify({'status': 'error', 'message': 'ID do produto não fornecido'})
    
    # Buscar produto no carrinho para logging
    cart = get_cart()
    produto = next((item for item in cart if item['id'] == int(product_id)), None)
    
    remove_from_cart(int(product_id))
    
    # Registrar no log
    if produto:
        log_interacao(f"Remover produto ID {product_id}", f"Produto {produto['nome_produto']} removido do carrinho", "remover_carrinho", True)
    
    return jsonify({
        'status': 'ok', 
        'message': 'Produto removido do carrinho!',
        'cart_count': len(get_cart())
    })

@app.route('/carrinho/limpar', methods=['POST'])
def limpar_carrinho():
    clear_cart()
    log_interacao("Limpar carrinho", "Carrinho limpo", "limpar_carrinho", True)
    return jsonify({'status': 'ok', 'message': 'Carrinho limpo!'})

@app.route('/carrinho', methods=['GET'])
def ver_carrinho():
    carrinho_data = {
        'status': 'ok',
        'cart': get_cart(),
        'total': get_cart_total(),
        'summary': get_cart_summary()
    }
    log_interacao("Ver carrinho", "Visualização do carrinho", "ver_carrinho", True)
    return jsonify(carrinho_data)

@app.route('/finalizar-compra', methods=['POST'])
def finalizar_compra():
    cart = get_cart()
    if not cart:
        return jsonify({'status': 'error', 'message': 'Carrinho vazio'})
    
    # Gerar resumo da compra
    resumo = "✅ **COMPRA FINALIZADA** ✅\n\n"
    resumo += get_cart_summary()
    resumo += "\n\n📧 **Esta compra foi enviada para nosso team de vendas!**"
    resumo += "\n📞 **Em breve entraremos em contato para confirmar o pedido.**"
    
    # Registrar a compra no histórico
    log_compra(cart, get_cart_total())
    
    # Limpar carrinho após finalização
    clear_cart()
    
    # Registrar no log de interações
    log_interacao("Finalizar compra", "Compra finalizada com sucesso", "finalizar_compra", True)
    
    return jsonify({
        'status': 'ok',
        'message': 'Compra finalizada com sucesso!',
        'resumo': resumo,
        'total': get_cart_total()
    })

@app.route('/status')
def status():
    return jsonify({
        'dataset_size': len(df),
        'estoque_size': len(estoque_df),
        'cart_size': len(get_cart()),
        'cart_total': get_cart_total(),
        'model_trained': True,
        'intents': list(model_bundle['label_encoder'].classes_)
    })

# Inicializar arquivos ao iniciar o app
inicializar_arquivos()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)