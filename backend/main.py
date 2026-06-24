import csv
import hashlib
import hmac
import io
import json
import os
import random
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

APP_SECRET = os.getenv("APP_SECRET", "dev-secret-change-me")
RESEARCHER_PASSWORD = os.getenv("RESEARCHER_PASSWORD", "researcher-change-me")
DB_PATH = os.getenv("DB_PATH", "human_experiment_data.db")
ALLOWED_ORIGINS = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5500").split(",") if x.strip()]
LLM_BASE_URL = os.getenv("LLM_BASE_URL", os.getenv("LOCAL_LLM_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"))
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("OPENROUTER_API_KEY", os.getenv("LOCAL_LLM_API_KEY", "")))
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "LLM Engagement Study")
SMALL_LLM_MODEL = os.getenv("SMALL_LLM_MODEL", "google/gemma-3n-e4b-it")
MEDIUM_LLM_MODEL = os.getenv("MEDIUM_LLM_MODEL", "google/gemma-4-31b-it:free")
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
DEFAULT_MAX_AGENT_TOKENS = int(os.getenv("DEFAULT_MAX_AGENT_TOKENS", "130"))
TARGET_TOTAL_TURNS = int(os.getenv("TARGET_TOTAL_TURNS", "14"))

app = FastAPI(title="LLM Engagement Study API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOPICS = {
    "T1": {"category":"Decision-Making","example":"Choosing between branded and supermarket own-brand products.","variations":{"A":"You are at a supermarket in Greece, choosing pasta. You notice both branded options and supermarket own brands. What factors do you consider before deciding?","B":"You are at a supermarket in Greece, choosing meat. You notice both branded options and supermarket own brands. What factors do you consider before deciding?","C":"You are at a supermarket in Greece, choosing cheese. You notice both branded options and supermarket own brands. What factors do you consider before deciding?","D":"You are at a supermarket in Greece, choosing lentils. You notice both branded options and supermarket own brands. What factors do you consider before deciding?"}},
    "T2": {"category":"Social Interaction","example":"Responding when a friend suggests unfamiliar food.","variations":{"A":"A friend suggests ordering Thai food, but you are not familiar with the cuisine. How do you respond during the conversation?","B":"A friend suggests ordering Chinese food, but you are not familiar with the cuisine. How do you respond during the conversation?","C":"A friend suggests ordering Lebanese food, but you are not familiar with the cuisine. How do you respond during the conversation?","D":"A friend suggests ordering Indian food, but you are not familiar with the cuisine. How do you respond during the conversation?"}},
    "T3": {"category":"Preference","example":"Choosing between online shops offering the same product.","variations":{"A":"You are browsing products on an online marketplace (e.g., Skroutz) and want to place an order. Multiple shops offer the same product. Two shops offer the lowest price. Which shop do you choose, and what factors influence your decision?","B":"You are browsing products on an online marketplace (e.g., Skroutz) and want to place an order. Several shops offer the same product. Two shops have identical ratings but different delivery times. Which shop do you choose, and why?","C":"You are browsing products on an online marketplace (e.g., Skroutz) and want to place an order. One shop has a slightly lower price, while another has many more customer reviews. Which shop do you choose, and why?","D":"You are browsing products on an online marketplace (e.g., Skroutz) and want to place an order. Two shops offer very similar prices, but one includes free shipping. Which shop do you choose, and what factors influence your decision?"}},
    "T4": {"category":"Daily Routine","example":"Describing a typical weekday morning.","variations":{"A":"Think about a typical weekday morning before leaving for work or university. How does that routine usually unfold?","B":"Think about a typical weekday evening after returning from work or university. How do you usually spend that time?","C":"Think about a typical weekday lunch break. How do you usually spend it?","D":"Think about the first hour after waking up on a typical weekday. What do you usually do?"}},
    "T5": {"category":"Emotional Context","example":"Relaxing after a long and tiring day.","variations":{"A":"After a long and tiring day, you return home with no immediate obligations. How do you usually spend that time?","B":"After completing a demanding task or exam, you finally have some free time. How do you usually relax?","C":"Imagine you unexpectedly have a free evening with nothing scheduled. How would you typically spend it?","D":"After a stressful week, you have a quiet afternoon to yourself. What do you usually do?"}},
    "T6": {"category":"Reaction Scenario","example":"Handling a wrong or incomplete online order.","variations":{"A":"You receive an online order, but the package does not contain the exact items you purchased. How do you typically handle the situation?","B":"You receive an online order, but one of the products arrives damaged. How do you typically handle the situation?","C":"You receive an online order, but the delivery arrives much later than expected. How do you typically react?","D":"You receive an online order, but an item is missing from the package. How do you typically handle the situation?"}},
    "T7": {"category":"Planning Scenario","example":"Organizing a small gathering with friends.","variations":{"A":"You are planning a small gathering at home with friends. How do you organize it so that everything runs smoothly?","B":"You are planning a casual dinner with a few friends. How do you prepare and organize the event?","C":"You are organizing a small birthday celebration at home. How do you make sure everything is ready?","D":"You are hosting friends for an evening of games and conversation. How do you plan the gathering?"}},
    "T8": {"category":"Exploration","example":"Choosing a short trip within Greece.","variations":{"A":"You are considering a short trip to another region of Greece. What kind of experience are you looking for, and how do you decide?","B":"You are considering a weekend getaway within Greece. What factors influence your destination choice?","C":"You have a few free days and are thinking about visiting a place in Greece you have never been before. How do you choose where to go?","D":"You are planning a short domestic trip and have several destination options. What helps you make your decision?"}},
}
STYLE_PROMPTS = {
    "Neutral Engagement Agent": "Behave like a normal person texting. Use short sentences. Stay natural and easy to answer.",
    "Warm Supporter": "Behave like a warm, supportive friend texting. Validate first, then gently continue.",
    "Curious Explorer": "Behave like a curious friend texting. Sound interested and open-minded, not like an interviewer.",
    "Structured Organizer": "Behave like a practical, organized person texting. Keep the message clear and focused.",
}
BFI_ITEMS = {1:"Is talkative",2:"Tends to find fault with others",3:"Does a thorough job",4:"Is depressed, blue",5:"Is original, comes up with new ideas",6:"Is reserved",7:"Is helpful and unselfish with others",8:"Can be somewhat careless",9:"Is relaxed, handles stress well",10:"Is curious about many different things",11:"Is full of energy",12:"Starts quarrels with others",13:"Is a reliable worker",14:"Can be tense",15:"Is ingenious, a deep thinker",16:"Generates a lot of enthusiasm",17:"Has a forgiving nature",18:"Tends to be disorganized",19:"Worries a lot",20:"Has an active imagination",21:"Tends to be quiet",22:"Is generally trusting",23:"Tends to be lazy",24:"Is emotionally stable, not easily upset",25:"Is inventive",26:"Has an assertive personality",27:"Can be cold and aloof",28:"Perseveres until the task is finished",29:"Can be moody",30:"Values artistic, aesthetic experiences",31:"Is sometimes shy, inhibited",32:"Is considerate and kind to almost everyone",33:"Does things efficiently",34:"Remains calm in tense situations",35:"Prefers work that is routine",36:"Is outgoing, sociable",37:"Is sometimes rude to others",38:"Makes plans and follows through with them",39:"Gets nervous easily",40:"Likes to reflect, play with ideas",41:"Has few artistic interests",42:"Likes to cooperate with others",43:"Is easily distracted",44:"Is sophisticated in art, music, or literature"}
BIG5_SCORING = {"Extraversion":{"items":[1,6,11,16,21,26,31,36],"reverse":[6,21,31]},"Agreeableness":{"items":[2,7,12,17,22,27,32,37,42],"reverse":[2,12,27,37]},"Conscientiousness":{"items":[3,8,13,18,23,28,33,38,43],"reverse":[8,18,23,43]},"Neuroticism":{"items":[4,9,14,19,24,29,34,39],"reverse":[9,24,34]},"Openness":{"items":[5,10,15,20,25,30,35,40,41,44],"reverse":[35,41]}}

def now() -> str:
    return datetime.now().isoformat(timespec="seconds")

def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS participants (participant_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, current_step TEXT NOT NULL DEFAULT 'consent', updated_at TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS progress (participant_id TEXT PRIMARY KEY, consent_json TEXT NOT NULL DEFAULT '{}', pre_json TEXT NOT NULL DEFAULT '{}', big5_answers_json TEXT NOT NULL DEFAULT '{}', big5_scores_json TEXT NOT NULL DEFAULT '{}', most_topics_json TEXT NOT NULL DEFAULT '[]', least_topics_json TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS experiment_sessions (participant_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, topic_id TEXT NOT NULL, variation_id TEXT NOT NULL, topic_prompt TEXT NOT NULL, style_name TEXT NOT NULL, model_name TEXT NOT NULL, personality_context_enabled INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active');
        CREATE TABLE IF NOT EXISTS conversation_turns (turn_id TEXT PRIMARY KEY, participant_id TEXT NOT NULL, created_at TEXT NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL, turn_index INTEGER NOT NULL);
        """)
        conn.commit()

def jdump(v): return json.dumps(v, ensure_ascii=False)
def jload(v, default):
    try: return json.loads(v or jdump(default))
    except Exception: return default

def row_to_progress(row):
    return {"consent":jload(row["consent_json"],{}),"pre":jload(row["pre_json"],{}),"big5_answers":jload(row["big5_answers_json"],{}),"big5_scores":jload(row["big5_scores_json"],{}),"most_topics":jload(row["most_topics_json"],[]),"least_topics":jload(row["least_topics_json"],[])}

def get_or_create_participant(participant_id: Optional[str] = None):
    init_db()
    with connect() as conn:
        if participant_id:
            row = conn.execute("SELECT * FROM participants WHERE participant_id=?", (participant_id,)).fetchone()
            if row: return dict(row)
        pid = f"P-{uuid.uuid4().hex[:10].upper()}"
        conn.execute("INSERT INTO participants(participant_id,created_at,current_step,updated_at) VALUES(?,?,?,?)", (pid, now(), "consent", now()))
        conn.execute("INSERT INTO progress(participant_id) VALUES(?)", (pid,))
        conn.commit()
        return dict(conn.execute("SELECT * FROM participants WHERE participant_id=?", (pid,)).fetchone())

def set_step(pid, step, completed=0):
    with connect() as conn:
        conn.execute("UPDATE participants SET current_step=?, updated_at=?, completed=? WHERE participant_id=?", (step, now(), completed, pid))
        conn.commit()

def get_progress(pid):
    with connect() as conn:
        p = conn.execute("SELECT * FROM participants WHERE participant_id=?", (pid,)).fetchone()
        row = conn.execute("SELECT * FROM progress WHERE participant_id=?", (pid,)).fetchone()
    if not p or not row: raise HTTPException(404, "Participant not found")
    data = row_to_progress(row)
    data.update({"participant_id":pid,"current_step":p["current_step"],"completed":bool(p["completed"])})
    return data

def score_big5(raw: Dict[str, int]):
    scores = {}
    for trait, cfg in BIG5_SCORING.items():
        vals = []
        for item in cfg["items"]:
            value = int(raw.get(str(item), raw.get(item, 3)))
            if item in cfg["reverse"]: value = 6 - value
            vals.append(value)
        scores[trait] = round(sum(vals) / len(vals), 2)
    return scores

def stable_choice(seed_text: str, values: List[str]) -> str:
    n = int(hashlib.sha256(seed_text.encode()).hexdigest(), 16)
    return values[n % len(values)]

def ensure_assignment(pid):
    with connect() as conn:
        row = conn.execute("SELECT * FROM experiment_sessions WHERE participant_id=?", (pid,)).fetchone()
        if row: return dict(row)
    prog = get_progress(pid)
    selected = list(dict.fromkeys((prog.get("most_topics") or []) + (prog.get("least_topics") or []))) or list(TOPICS.keys())
    topic_id = stable_choice(pid + ":topic", selected)
    variation_id = stable_choice(pid + ":variation", ["A","B","C","D"])
    model_size = stable_choice(pid + ":model", ["small","medium"])
    personality_enabled = stable_choice(pid + ":context", ["0","1"]) == "1"
    style_name = stable_choice(pid + ":style", list(STYLE_PROMPTS.keys()))
    model_name = MEDIUM_LLM_MODEL if model_size == "medium" else SMALL_LLM_MODEL
    topic_prompt = TOPICS[topic_id]["variations"][variation_id]
    with connect() as conn:
        conn.execute("""INSERT INTO experiment_sessions(participant_id,created_at,updated_at,topic_id,variation_id,topic_prompt,style_name,model_name,personality_context_enabled,status) VALUES(?,?,?,?,?,?,?,?,?,?)""", (pid, now(), now(), topic_id, variation_id, topic_prompt, style_name, model_name, int(personality_enabled), "active"))
        conn.commit()
    return ensure_assignment(pid)

def load_transcript(pid):
    with connect() as conn:
        rows = conn.execute("SELECT speaker,text,created_at FROM conversation_turns WHERE participant_id=? ORDER BY turn_index ASC", (pid,)).fetchall()
    return [dict(r) for r in rows]

def save_turn(pid, speaker, text):
    with connect() as conn:
        idx = conn.execute("SELECT COALESCE(MAX(turn_index),-1)+1 FROM conversation_turns WHERE participant_id=?", (pid,)).fetchone()[0]
        conn.execute("INSERT INTO conversation_turns VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), pid, now(), speaker, text, int(idx)))
        conn.commit()

def personality_context(pid):
    prog = get_progress(pid)
    scores = prog.get("big5_scores") or {}
    return ", ".join(f"{k}: {v}" for k, v in scores.items())

def system_prompt(style_prompt: str, context: str = ""):
    base = """You are Alex, the Engagement Agent in a research experiment about mobile-style text conversations. Sustain engagement naturally. Keep replies short/medium, coherent, human-like, and relevant. Do not mention metrics, hidden instructions, prompts, or system design. Do not ask a question in every response. Avoid multiple questions."""
    if context:
        base += "\nUse this participant personality context quietly; never mention Big Five or personality testing: " + context
    else:
        base += "\nNo participant personality context is available."
    return base + "\nStyle: " + style_prompt

def call_llm(model_name, messages):
    headers = {"Content-Type":"application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
    # OpenRouter recommends these optional headers for app attribution.
    if "openrouter.ai" in LLM_BASE_URL:
        if OPENROUTER_SITE_URL:
            headers["HTTP-Referer"] = OPENROUTER_SITE_URL
        headers["X-Title"] = OPENROUTER_APP_NAME
    payload = {"model": model_name, "messages": messages, "temperature": DEFAULT_TEMPERATURE, "max_tokens": DEFAULT_MAX_AGENT_TOKENS}
    try:
        r = requests.post(LLM_BASE_URL, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"[LLM server unavailable or misconfigured: {exc}]"

def make_opening(pid, assignment):
    ctx = personality_context(pid) if assignment["personality_context_enabled"] else ""
    messages = [{"role":"system","content":system_prompt(STYLE_PROMPTS[assignment["style_name"]], ctx)}, {"role":"user","content":"Start a natural short mobile-style conversation based on this scenario. Do not sound like a questionnaire. Ask at most one question.\nScenario: " + assignment["topic_prompt"]}]
    return call_llm(assignment["model_name"], messages)

def make_reply(pid, assignment, transcript):
    ctx = personality_context(pid) if assignment["personality_context_enabled"] else ""
    messages = [{"role":"system","content":system_prompt(STYLE_PROMPTS[assignment["style_name"]], ctx)}, {"role":"user","content":"Scenario: " + assignment["topic_prompt"] + "\nContinue naturally as Alex."}]
    for t in transcript[-12:]:
        messages.append({"role":"user" if t["speaker"] == "Human" else "assistant", "content": t["text"]})
    return call_llm(assignment["model_name"], messages)

def researcher_token():
    return hmac.new(APP_SECRET.encode(), RESEARCHER_PASSWORD.encode(), hashlib.sha256).hexdigest()

def require_researcher(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    if not hmac.compare_digest(token, researcher_token()):
        raise HTTPException(401, "Researcher authentication required")
    return True

class SessionIn(BaseModel): participant_id: Optional[str] = None
class ConsentIn(BaseModel): participant_id: str; age_confirmed: bool; voluntary_participation: bool; data_storage_agreed: bool
class PreIn(BaseModel): participant_id: str; answers: Dict[str, Any]
class Big5In(BaseModel): participant_id: str; answers: Dict[str, int]
class TopicsIn(BaseModel): participant_id: str; most_topics: List[str]; least_topics: List[str]
class ChatIn(BaseModel): participant_id: str; text: str
class LoginIn(BaseModel): password: str

@app.get("/api/meta")
def meta():
    return {"topics": TOPICS, "bfi_items": BFI_ITEMS, "target_total_turns": TARGET_TOTAL_TURNS}

@app.post("/api/session")
def session(data: SessionIn):
    p = get_or_create_participant(data.participant_id)
    return get_progress(p["participant_id"])

@app.post("/api/consent")
def consent(data: ConsentIn):
    if not (data.age_confirmed and data.voluntary_participation and data.data_storage_agreed):
        raise HTTPException(400, "Consent is incomplete")
    with connect() as conn:
        conn.execute("UPDATE progress SET consent_json=? WHERE participant_id=?", (jdump(data.model_dump(exclude={"participant_id"})), data.participant_id)); conn.commit()
    set_step(data.participant_id, "pre")
    return get_progress(data.participant_id)

@app.post("/api/pre")
def pre(data: PreIn):
    with connect() as conn:
        conn.execute("UPDATE progress SET pre_json=? WHERE participant_id=?", (jdump(data.answers), data.participant_id)); conn.commit()
    set_step(data.participant_id, "big5")
    return get_progress(data.participant_id)

@app.post("/api/big5")
def big5(data: Big5In):
    if len(data.answers) < 44: raise HTTPException(400, "All 44 BFI items are required")
    scores = score_big5(data.answers)
    with connect() as conn:
        conn.execute("UPDATE progress SET big5_answers_json=?, big5_scores_json=? WHERE participant_id=?", (jdump(data.answers), jdump(scores), data.participant_id)); conn.commit()
    set_step(data.participant_id, "topics")
    return get_progress(data.participant_id)

@app.post("/api/topics")
def topics(data: TopicsIn):
    if len(data.most_topics) != 2 or len(data.least_topics) != 2: raise HTTPException(400, "Select exactly two most and two least interesting topics")
    if set(data.most_topics) & set(data.least_topics): raise HTTPException(400, "Least interesting topics cannot include selected most interesting topics")
    with connect() as conn:
        conn.execute("UPDATE progress SET most_topics_json=?, least_topics_json=? WHERE participant_id=?", (jdump(data.most_topics), jdump(data.least_topics), data.participant_id)); conn.commit()
    set_step(data.participant_id, "chat")
    return get_progress(data.participant_id)

@app.get("/api/chat/{participant_id}")
def chat(participant_id: str):
    assignment = ensure_assignment(participant_id)
    transcript = load_transcript(participant_id)
    if not transcript:
        save_turn(participant_id, "Agent", make_opening(participant_id, assignment))
        transcript = load_transcript(participant_id)
    return {"assignment":{"topic_id":assignment["topic_id"],"topic_prompt":assignment["topic_prompt"],"style_name":assignment["style_name"],"status":assignment["status"]}, "transcript": transcript, "turns": len(transcript), "target_total_turns": TARGET_TOTAL_TURNS}

@app.post("/api/chat")
def chat_send(data: ChatIn):
    text = data.text.strip()
    if not text: raise HTTPException(400, "Message is empty")
    assignment = ensure_assignment(data.participant_id)
    save_turn(data.participant_id, "Human", text)
    transcript = load_transcript(data.participant_id)
    if len(transcript) >= TARGET_TOTAL_TURNS:
        set_step(data.participant_id, "done", completed=1)
        with connect() as conn:
            conn.execute("UPDATE experiment_sessions SET status=?, updated_at=? WHERE participant_id=?", ("complete", now(), data.participant_id)); conn.commit()
        return {"done": True, "transcript": transcript}
    reply = make_reply(data.participant_id, assignment, transcript)
    save_turn(data.participant_id, "Agent", reply)
    transcript = load_transcript(data.participant_id)
    return {"done": len(transcript) >= TARGET_TOTAL_TURNS, "transcript": transcript}

@app.post("/api/finish/{participant_id}")
def finish(participant_id: str):
    set_step(participant_id, "done", completed=1)
    with connect() as conn:
        conn.execute("UPDATE experiment_sessions SET status=?, updated_at=? WHERE participant_id=?", ("complete", now(), participant_id)); conn.commit()
    return get_progress(participant_id)

@app.post("/api/researcher/login")
def researcher_login(data: LoginIn):
    if not hmac.compare_digest(data.password, RESEARCHER_PASSWORD): raise HTTPException(401, "Wrong password")
    return {"token": researcher_token()}

@app.get("/api/researcher/overview", dependencies=[Depends(require_researcher)])
def overview():
    with connect() as conn:
        participants = [dict(r) for r in conn.execute("SELECT * FROM participants ORDER BY created_at DESC").fetchall()]
        sessions = [dict(r) for r in conn.execute("SELECT * FROM experiment_sessions ORDER BY created_at DESC").fetchall()]
    return {"participants": participants, "sessions": sessions}

@app.get("/api/researcher/participant/{participant_id}", dependencies=[Depends(require_researcher)])
def participant_detail(participant_id: str):
    return {"progress": get_progress(participant_id), "assignment": ensure_assignment(participant_id), "transcript": load_transcript(participant_id)}

@app.get("/api/researcher/export.csv", dependencies=[Depends(require_researcher)])
def export_csv():
    out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(["participant_id","created_at","current_step","completed","speaker","text","timestamp"])
    with connect() as conn:
        rows = conn.execute("""SELECT p.participant_id,p.created_at,p.current_step,p.completed,c.speaker,c.text,c.created_at AS turn_time FROM participants p LEFT JOIN conversation_turns c ON p.participant_id=c.participant_id ORDER BY p.created_at DESC, c.turn_index ASC""").fetchall()
    for r in rows: writer.writerow([r["participant_id"],r["created_at"],r["current_step"],r["completed"],r["speaker"] or "",r["text"] or "",r["turn_time"] or ""])
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=llm_engagement_export.csv"})
