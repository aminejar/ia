import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def call_llm(prompt, config):
    def get_config_value(config, *keys, default=''):
        for key in keys:
            if key in config and config[key]:
                return config[key]
        return default

    provider = get_config_value(config, 'provider', 'api_provider', default='groq')
    model    = get_config_value(config, 'model', 'api_model', default='')
    
    if provider == 'gemini':
        import google.generativeai as genai
        import os
        api_key = os.environ.get('GEMINI_API_KEY', '')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env")
        genai.configure(api_key=api_key)
        m    = genai.GenerativeModel(model or 'gemini-2.0-flash')
        resp = m.generate_content(prompt)
        return resp.text
    
    elif provider == 'groq':
        from groq import Groq
        import os
        api_key = os.environ.get('GROQ_API_KEY', '')
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in .env")
        client = Groq(api_key=api_key)
        resp   = client.chat.completions.create(
            model=model or 'llama-3.3-70b-versatile',
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.5
        )
        return resp.choices[0].message.content
    
    elif provider == 'ollama':
        import requests
        resp = requests.post(
            'http://localhost:11434/api/generate',
            json={
                "model": model or "llama3",
                "prompt": prompt,
                "stream": False
            },
            timeout=60
        )
        return resp.json().get('response', '')
    
    else:
        raise ValueError(f"Unknown provider: {provider}")

import os

def generate_topic_section(topic, articles, config):
    if not articles:
        return f"## {topic}\nAucun article trouvé.\n"
    
    articles_text = ""
    for i, art in enumerate(articles[:8], 1):
        title   = (art.get('title','') or '')[:100]
        summary = (art.get('summary','') or '')[:150]
        source  = art.get('source','')
        articles_text += f"[{i}] {title}\n"
        articles_text += f"Source: {source}\n"
        articles_text += f"Résumé: {summary}\n\n"
    
    prompt = f"""Analyse ces articles sur le sujet "{topic}".
    
Articles:
{articles_text}

Écris en français une analyse de 3-4 phrases
sur les développements clés concernant {topic}.
Puis liste 3 points clés concrets tirés des articles.
Puis liste les sources.

Format EXACT à respecter:
[2-3 phrases d'analyse]

**Points clés:**
• [point concret 1]
• [point concret 2]  
• [point concret 3]

**Sources:** [noms des sources]
"""
    
    try:
        content = call_llm(prompt, config)
        return f"## {topic} — {len(articles)} articles\n{content}\n"
    
    except Exception as e:
        error_msg = f"LLM Error for {topic}: {str(e)}"
        print(error_msg)
        titles = [a.get('title','')[:80] for a in articles[:5]]
        titles_str = "\n".join(f"• {t}" for t in titles)
        return f"## {topic} — {len(articles)} articles\n\n**Erreur LLM:** `{error_msg}`\n\n{titles_str}\n"

def generate_trends(filtered_by_topic, articles):
    dominant = max(
        filtered_by_topic.items(),
        key=lambda x: len(x[1]),
        default=('Aucun', [])
    )[0]
    
    all_titles = " ".join(
        a.get('title','') for arts in 
        filtered_by_topic.values() for a in arts
    ).lower()
    
    alert = "Aucune alerte majeure"
    if 'hack' in all_titles or 'breach' in all_titles:
        alert = "Incident de sécurité détecté"
    elif 'crash' in all_titles or 'chute' in all_titles:
        alert = "Baisse de marché détectée"
    elif 'launch' in all_titles or 'lancement' in all_titles:
        alert = "Nouveau lancement important"
    
    return f"""## Tendances de la semaine
- **Topic dominant:** {dominant}
- **Alerte prioritaire:** {alert}
- **Articles totaux:** {sum(len(v) for v in filtered_by_topic.values())}
"""


def generate_report(filtered_by_topic, config, llm_client):
    date = datetime.now().strftime("%B %d, %Y")
    topics = config.get('topics', [])
    
    model = config.get('model') or config.get('api_model', '')
    if not model or model in ['llama3-70b-8192', 'llama3-8b-8192', 'Default', '', None]:
        provider = config.get('provider', 'groq')
        if provider == 'gemini':
            model = 'gemini-2.0-flash'
        else:
            model = 'llama-3.3-70b-versatile'
            
    provider = config.get('provider', 'groq').upper()
    
    report_sections = []
    all_articles = []
    
    for topic in topics:
        articles = filtered_by_topic.get(topic, [])
        all_articles.extend(articles)
        
        section_content = generate_topic_section(topic, articles, config)
        report_sections.append(section_content)
            
    # Executive Summary Generation
    total_arts = len(all_articles)
    all_sources = len(set(a.get('source', '') for a in all_articles if a.get('source')))
    
    exec_prompt = f"""Tu es rédacteur en chef. Date: {date}.
Nous avons {total_arts} articles sur les sujets: {', '.join(topics)}.
Génère UNIQUEMENT un court résumé exécutif (2-3 phrases) de l'actualité globale, sans titres."""
    try:
        exec_summary = call_llm(exec_prompt, config)
        exec_summary = re.sub(r'<think>.*?</think>', '', exec_summary, flags=re.IGNORECASE | re.DOTALL).strip()
    except:
        exec_summary = "Période de veille complétée avec succès sur l'ensemble des sujets configurés."

    # Trends Generation
    trends = generate_trends(filtered_by_topic, all_articles)

    separator = "\n---\n\n"
    
    full_report = f"""# Rapport Intelligence — {date}
**Généré par VeilleAI · {provider} · {model}**

---

## Résumé Exécutif
{exec_summary}

Topics: {', '.join(topics)} | Articles: {total_arts} | Sources: {all_sources}

---

{separator.join(report_sections)}

---

## Tendances de la semaine
{trends}

---
*Rapport généré le {date} par VeilleAI*
"""
    return full_report

def get_friendly_error(error, provider):
    error_str = str(error).lower()
    
    if '429' in error_str or 'quota' in error_str:
        other = 'groq' if provider == 'gemini' \
                else 'gemini'
        return {
            'type':    'quota',
            'title':   'Limite journalière atteinte',
            'message': f'Tes requêtes {provider} '
                       f'gratuites sont épuisées '
                       f'pour aujourd\'hui.',
            'solution':f'✓ {provider.title()} '
                       f'repart demain matin\n'
                       f'✓ {other.title()} '
                       f'fonctionne maintenant',
            'action':  f'switch_to_{other}',
            'action_label': f'Passer à {other.title()} maintenant'
        }
    
    elif '401' in error_str or 'unauthorized' in error_str:
        key_name = f'{provider.upper()}_API_KEY'
        return {
            'type':    'auth',
            'title':   'Clé API invalide',
            'message': f'Ta {key_name} est incorrecte ou expirée.',
            'solution':f'1. Va sur console.{provider}.com\n'
                       f'2. Copie ta clé\n'
                       f'3. Mets dans .env : {key_name}=ta-clé',
            'action':  None
        }
    
    elif 'decommissioned' in error_str or '400' in error_str:
        defaults = {
            'groq':   'llama-3.3-70b-versatile',
            'gemini': 'gemini-2.0-flash',
        }
        new_model = defaults.get(provider, 
                                 'llama-3.3-70b-versatile')
        return {
            'type':    'model',
            'title':   'Modèle non disponible',
            'message': 'Ce modèle n\'existe plus.',
            'solution':f'Nouveau modèle recommandé : {new_model}',
            'action':  f'fix_model_{new_model}',
            'action_label': 'Corriger automatiquement'
        }
    
    elif 'timeout' in error_str or 'connection' in error_str:
        return {
            'type':    'network',
            'title':   'Pas de connexion',
            'message': 'Impossible de contacter le serveur IA.',
            'solution':'Vérifie ta connexion internet et réessaie.',
            'action':  'retry'
        }
    
    elif 'api_key' in error_str or 'not found' in error_str:
        key_name = f'{provider.upper()}_API_KEY'
        return {
            'type':    'missing_key',
            'title':   'Clé API manquante',
            'message': f'{key_name} introuvable dans ton fichier .env',
            'solution':f'console.{provider}.com → clé gratuite',
            'action':  None
        }
    
    else:
        return {
            'type':    'unknown',
            'title':   'Erreur inattendue',
            'message': str(error)[:100],
            'solution':'Réessaie dans quelques minutes.',
            'action':  'retry'
        }
