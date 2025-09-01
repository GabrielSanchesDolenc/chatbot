from flask import Flask, render_template, request, jsonify
import os
import random
import pandas as pd
import unicodedata
import re
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)

dataset_path = 'qa_dataset_improved.csv'
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

HIGH_SIM_THRESHOLD = 0.78
LOW_SIM_THRESHOLD = 0.50

teacher_name = "anonimo" 

def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ''
    nfkd = unicodedata.normalize('NFD', text)
    no_accents = ''.join([c for c in nfkd if unicodedata.category(c) != 'Mn'])
    s = re.sub(r'\s+', ' ', no_accents).strip().lower()
    return s

def create_initial_dataset(path: str):
    perguntas = [
        "Qual é o jogo mais popular atualmente?",
        "Qual a melhor motocicleta para iniciantes?",
        "Quais jogos têm o melhor modo multiplayer?",
        "Qual moto tem o melhor desempenho em pistas?",
        "Qual é a moto mais veloz do mundo?",
        "Qual jogo tem a melhor história?",
        "Qual moto o Rogerio tem?"
    ]
    respostas = [
        "O jogo mais popular atualmente é League of Legends.",
        "A melhor motocicleta para iniciantes é o patinete elétrico.",
        "Os jogos com o melhor modo multiplayer são [Jogo A] e [Jogo B].",
        "A moto com o melhor desempenho em pistas é a [Moto Z].",
        "A moto mais veloz do mundo é a do Marc Marques.",
        "O jogo com a melhor história é Tomb Raider.",
        "Ele tem uma TDM 850 e uma NC 750x, ambas são bem bacanas."
    ]
    intents = [
        "informacao_jogo",
        "informacao_moto",
        "informacao_jogo",
        "informacao_moto",
        "informacao_moto",
        "informacao_jogo",
        "informacao_rogerio"
    ]
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

def train_model(df: pd.DataFrame):
    le = LabelEncoder()
    intents = df['intent'].fillna('unknown').astype(str).values
    labels = le.fit_transform(intents)
    pipeline = make_pipeline(
        TfidfVectorizer(ngram_range=(1,2), min_df=1),
        SVC(kernel='linear', probability=True, random_state=RANDOM_SEED)
    )
    pipeline.fit(df['normalized_question'].values, labels)
    return {
        'pipeline': pipeline,
        'label_encoder': le
    }

model_bundle = train_model(df)

def find_similar_questions(user_question: str, top_k: int = 3):
    q_norm = normalize_text(user_question)
    vect = model_bundle['pipeline'].named_steps['tfidfvectorizer']
    matrix = vect.transform(df['normalized_question'].values)
    q_vec = vect.transform([q_norm])
    sims = cosine_similarity(q_vec, matrix).flatten()
    idx_sorted = sims.argsort()[::-1]
    results = []
    for idx in idx_sorted[:top_k]:
        results.append({
            'index': int(idx),
            'score': float(sims[idx]),
            'question': df.iloc[idx]['question'],
            'answer': df.iloc[idx]['answer'],
            'intent': df.iloc[idx].get('intent', '')
        })
    return results

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/perguntar', methods=['POST'])
def perguntar():
    global df, model_bundle
    user_q = request.form.get('pergunta')
    sims = find_similar_questions(user_q)

    # Caso 1: Similaridade alta - APRENDER AUTOMATICAMENTE
    if sims and sims[0]['score'] >= HIGH_SIM_THRESHOLD:
        # Verifica se já não existe exatamente a mesma pergunta
        if user_q not in df['question'].values:
            # Adiciona nova variação da pergunta
            q_norm = normalize_text(user_q)
            now = datetime.utcnow().isoformat()
            
            new_row = {
                'question': user_q,
                'answer': sims[0]['answer'],
                'intent': sims[0]['intent'],
                'normalized_question': q_norm,
                'created_at': now,
                'taught_by': 'auto_learn'
            }
            
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_dataset(df)
            model_bundle = train_model(df)
        
        return jsonify({
            'status': 'ok',
            'answer': sims[0]['answer'],
            'reason': f"similaridade alta ({sims[0]['score']:.2f})"
        })

    # Caso 2: Similaridade média
    if sims and LOW_SIM_THRESHOLD <= sims[0]['score'] < HIGH_SIM_THRESHOLD:
        return jsonify({
            'status': 'ask_accept',
            'suggested_answer': sims[0]['answer'],
            'suggested_question': sims[0]['question'],
            'score': sims[0]['score']
        })

    return jsonify({
        'status': 'teach',
        'message': 'Não sei responder. Por favor, ensine.'
    })

@app.route('/confirmar', methods=['POST'])
def confirmar():
    global df, model_bundle
    pergunta_usuario = request.form.get('pergunta_usuario')
    pergunta_similar = request.form.get('pergunta_similar')
    resposta_confirmada = request.form.get('resposta_confirmada')
    intent = request.form.get('intent')
    
    # Encontra a intenção da pergunta similar original
    pergunta_original = df[df['question'] == pergunta_similar].iloc[0]
    intent_original = pergunta_original['intent']
    
    # Cria nova linha com a MESMA resposta e intenção, mas pergunta diferente
    q_norm = normalize_text(pergunta_usuario)
    now = datetime.utcnow().isoformat()
    
    new_row = {
        'question': pergunta_usuario,
        'answer': resposta_confirmada,
        'intent': intent_original, 
        'normalized_question': q_norm,
        'created_at': now,
        'taught_by': teacher_name
    }
    
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_dataset(df)
    model_bundle = train_model(df)
    
    return jsonify({
        'status': 'ok', 
        'message': 'Aprendi uma nova forma de perguntar!'
    })

@app.route('/ensinar', methods=['POST'])
def ensinar():
    global df, model_bundle
    pergunta = request.form.get('pergunta')
    resposta = request.form.get('resposta')
    intent = request.form.get('intent') or 'unknown'
    q_norm = normalize_text(pergunta)
    now = datetime.utcnow().isoformat()

    new_row = {
        'question': pergunta,
        'answer': resposta,
        'intent': intent,
        'normalized_question': q_norm,
        'created_at': now,
        'taught_by': teacher_name
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_dataset(df)
    model_bundle = train_model(df)

    return jsonify({'status': 'ok', 'message': 'Aprendido com sucesso!'})

if __name__ == '__main__':
    app.run(debug=True)
