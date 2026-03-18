import re
from datetime import datetime

def build_report_prompt(topic, articles, date):
    articles_text = ""
    for i, art in enumerate(articles[:8], 1):
        title   = art.get('title','')[:100]
        source  = art.get('source','')
        summary = art.get('summary','')[:200]
        articles_text += f"""
[{i}] {title}
Source: {source}
Résumé: {summary}
"""
    
    return f"""Tu es un analyste en veille stratégique.

Date: {date}
Topic: {topic}
Articles ({len(articles)}):
{articles_text}

Écris en français une section de rapport 
pour le topic "{topic}".

RÈGLES STRICTES:
1. Parle UNIQUEMENT de {topic}
2. Base toi UNIQUEMENT sur les articles fournis
3. Si les articles ne parlent pas de {topic}, 
   dis "Peu d'actualité ce jour sur ce sujet"
4. Sois factuel et précis
5. Maximum 3 points clés

FORMAT DE RÉPONSE:
[2-3 phrases de résumé sur {topic}]

**Points clés:**
- [fait concret tiré des articles]
- [fait concret tiré des articles]
- [fait concret tiré des articles]

**Sources:**
- [titre article] — [source]
"""


def call_llm_with_timeout(prompt, client, timeout=60):
    import os
    if os.name == 'nt':
        # Windows: use threading timeout
        import threading
        result = [None]
        error  = [None]
        
        def target():
            try:
                result[0] = client.generate(prompt)
            except Exception as e:
                error[0] = e
        
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            print(f"LLM timeout after {timeout}s")
            return "Rapport non disponible — timeout LLM"
        if error[0]:
            raise error[0]
        return result[0]
    else:
        # Linux/Mac: use signal
        import signal
        signal.alarm(timeout)
        try:
            return client.generate(prompt)
        finally:
            signal.alarm(0)


def generate_report(filtered_by_topic, config, llm_client):
    date = datetime.now().strftime("%B %d, %Y")
    topics = config.get('topics', [])
    provider = config.get('api_provider', 'Local')
    model = config.get('api_model', 'Default')
    
    report_sections = []
    all_articles = []
    
    for topic in topics:
        articles = filtered_by_topic.get(topic, [])
        all_articles.extend(articles)
        
        if len(articles) == 0:
            report_sections.append(
                f"## {topic} — 0 articles\n"
                f"Aucun article récent trouvé pour ce sujet.\n"
            )
            continue
        
        prompt = build_report_prompt(topic, articles, date)
        
        try:
            response = call_llm_with_timeout(prompt, llm_client, timeout=60)
            # Remove reasoning blocks
            response = re.sub(r'<think>.*?</think>', '', response, flags=re.IGNORECASE | re.DOTALL).strip()
            section_content = f"## {topic} — {len(articles)} articles\n" + response + "\n"
            report_sections.append(section_content)
        except Exception as e:
            report_sections.append(
                f"## {topic} — {len(articles)} articles\n"
                f"Erreur de génération: {e}\n"
            )
            
    # Executive Summary Generation
    total_arts = len(all_articles)
    all_sources = len(set(a.get('source', '') for a in all_articles if a.get('source')))
    
    exec_prompt = f"""Tu es rédacteur en chef. Date: {date}.
Nous avons {total_arts} articles sur les sujets: {', '.join(topics)}.
Génère UNIQUEMENT un court résumé exécutif (2-3 phrases) de l'actualité globale, sans titres."""
    try:
        exec_summary = call_llm_with_timeout(exec_prompt, llm_client, timeout=60)
        exec_summary = re.sub(r'<think>.*?</think>', '', exec_summary, flags=re.IGNORECASE | re.DOTALL).strip()
    except:
        exec_summary = "Période de veille complétée avec succès sur l'ensemble des sujets configurés."

    # Trends Generation
    topic_counts = {t: len(filtered_by_topic.get(t, [])) for t in topics}
    dominant_topic = max(topic_counts, key=topic_counts.get) if topic_counts else "Indéfini"
    
    trends_prompt = f"""Donne 3 tendances basées sur '{dominant_topic}' (qui a le plus d'articles).
Format strict (3 lignes exactes, sans autre texte ni intro):
- **Topic dominant:** [Nom du topic et pourquoi]
- **Alerte prioritaire:** [Info critique ou "Rien à signaler"]
- **À surveiller:** [Une tendance émergente]"""
    try:
        trends = call_llm_with_timeout(trends_prompt, llm_client, timeout=60)
        trends = re.sub(r'<think>.*?</think>', '', trends, flags=re.IGNORECASE | re.DOTALL).strip()
    except:
        trends = f"- **Topic dominant:** {dominant_topic}\n- **Alerte prioritaire:** Aucune alerte majeure\n- **À surveiller:** Développements en cours"

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
