import csv
import hashlib
import hmac
import io
import json
import os
import re
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
# Put only the API root here, not /chat/completions.
# Examples:
#   OpenRouter: LLM_BASE_URL=https://openrouter.ai/api/v1
#   LM Studio:  LLM_BASE_URL=http://localhost:1234/v1
LLM_BASE_URL = os.getenv("LLM_BASE_URL", os.getenv("LOCAL_LLM_BASE_URL", "https://openrouter.ai/api/v1"))
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("OPENROUTER_API_KEY", os.getenv("LOCAL_LLM_API_KEY", "")))
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "LLM Engagement Study")

# OpenRouter model IDs must exist exactly. These two are valid OpenRouter IDs.
# If you run LM Studio, set these to the local model IDs shown in LM Studio.
SMALL_LLM_MODEL = os.getenv("SMALL_LLM_MODEL", "google/gemma-3n-e4b-it")
MEDIUM_LLM_MODEL = os.getenv("MEDIUM_LLM_MODEL", "google/gemma-3-27b-it")
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.9"))
DEFAULT_MAX_AGENT_TOKENS = int(os.getenv("DEFAULT_MAX_AGENT_TOKENS", "70"))
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
        CREATE TABLE IF NOT EXISTS participants (
            participant_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            current_step TEXT NOT NULL DEFAULT 'consent',
            updated_at TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS progress (
            participant_id TEXT PRIMARY KEY,
            consent_json TEXT NOT NULL DEFAULT '{}',
            pre_json TEXT NOT NULL DEFAULT '{}',
            big5_answers_json TEXT NOT NULL DEFAULT '{}',
            big5_scores_json TEXT NOT NULL DEFAULT '{}',
            most_topics_json TEXT NOT NULL DEFAULT '[]',
            least_topics_json TEXT NOT NULL DEFAULT '[]'
        );

        -- Anonymous participant login codes. Create these from the researcher dashboard/API
        -- and email one code to each participant. No public self-registration is needed.
        CREATE TABLE IF NOT EXISTS participant_access_codes (
            access_code TEXT PRIMARY KEY,
            participant_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            used_at TEXT,
            last_login_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        );

        -- Kept for backward compatibility with older exports/code.
        CREATE TABLE IF NOT EXISTS experiment_sessions (
            participant_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            variation_id TEXT NOT NULL,
            topic_prompt TEXT NOT NULL,
            style_name TEXT NOT NULL,
            model_name TEXT NOT NULL,
            personality_context_enabled INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
        );

        -- New architecture: one participant has randomized conversation assignments. In test mode this file creates only 2 conversations.
        CREATE TABLE IF NOT EXISTS conversation_assignments (
            session_id TEXT PRIMARY KEY,
            participant_id TEXT NOT NULL,
            conversation_order INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            variation_id TEXT NOT NULL,
            topic_prompt TEXT NOT NULL,
            topic_preference TEXT NOT NULL,
            style_name TEXT NOT NULL,
            model_size TEXT NOT NULL,
            model_name TEXT NOT NULL,
            personality_context_enabled INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            UNIQUE(participant_id, conversation_order)
        );

        CREATE TABLE IF NOT EXISTS conversation_turns (
            turn_id TEXT PRIMARY KEY,
            participant_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            speaker TEXT NOT NULL,
            text TEXT NOT NULL,
            turn_index INTEGER NOT NULL,
            session_id TEXT
        );
        """)
        # Safe migration for existing local SQLite databases created before session_id existed.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(conversation_turns)").fetchall()]
        if "session_id" not in cols:
            conn.execute("ALTER TABLE conversation_turns ADD COLUMN session_id TEXT")
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


def create_participant_record(pid: Optional[str] = None):
    """Create a participant and empty progress row. Used by access-code generation."""
    init_db()
    pid = pid or f"P-{uuid.uuid4().hex[:10].upper()}"
    with connect() as conn:
        existing = conn.execute("SELECT * FROM participants WHERE participant_id=?", (pid,)).fetchone()
        if existing:
            return dict(existing)
        conn.execute(
            "INSERT INTO participants(participant_id,created_at,current_step,updated_at) VALUES(?,?,?,?)",
            (pid, now(), "consent", now()),
        )
        conn.execute("INSERT OR IGNORE INTO progress(participant_id) VALUES(?)", (pid,))
        conn.commit()
        return dict(conn.execute("SELECT * FROM participants WHERE participant_id=?", (pid,)).fetchone())


def normalize_access_code(code: str) -> str:
    return "".join(str(code or "").strip().upper().split())


def make_access_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "P-" + "".join(random.choice(alphabet) for _ in range(4)) + "-" + "".join(random.choice(alphabet) for _ in range(4))


def create_access_codes(count: int = 1) -> List[Dict[str, str]]:
    count = max(1, min(int(count or 1), 200))
    created = []
    init_db()
    with connect() as conn:
        for _ in range(count):
            for _attempt in range(50):
                access_code = make_access_code()
                if not conn.execute("SELECT 1 FROM participant_access_codes WHERE access_code=?", (access_code,)).fetchone():
                    break
            else:
                raise HTTPException(500, "Could not generate a unique access code")

            pid = f"P-{uuid.uuid4().hex[:10].upper()}"
            conn.execute(
                "INSERT INTO participants(participant_id,created_at,current_step,updated_at) VALUES(?,?,?,?)",
                (pid, now(), "consent", now()),
            )
            conn.execute("INSERT INTO progress(participant_id) VALUES(?)", (pid,))
            conn.execute(
                "INSERT INTO participant_access_codes(access_code,participant_id,created_at,is_active) VALUES(?,?,?,1)",
                (access_code, pid, now()),
            )
            created.append({"access_code": access_code, "participant_id": pid})
        conn.commit()
    return created


def login_with_access_code(access_code: str):
    code = normalize_access_code(access_code)
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM participant_access_codes WHERE access_code=? AND is_active=1",
            (code,),
        ).fetchone()
        if not row:
            raise HTTPException(401, "Invalid participant code")

        participant = conn.execute(
            "SELECT * FROM participants WHERE participant_id=?",
            (row["participant_id"],),
        ).fetchone()
        if not participant:
            conn.execute(
                "INSERT INTO participants(participant_id,created_at,current_step,updated_at) VALUES(?,?,?,?)",
                (row["participant_id"], now(), "consent", now()),
            )
            conn.execute("INSERT OR IGNORE INTO progress(participant_id) VALUES(?)", (row["participant_id"],))

        if not row["used_at"]:
            conn.execute("UPDATE participant_access_codes SET used_at=?, last_login_at=? WHERE access_code=?", (now(), now(), code))
        else:
            conn.execute("UPDATE participant_access_codes SET last_login_at=? WHERE access_code=?", (now(), code))
        conn.commit()
    progress = get_progress(row["participant_id"])
    progress["access_code"] = code
    return progress

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


def shuffled_for_participant(pid: str, salt: str, values: List[Any]) -> List[Any]:
    """Stable randomization: randomized once per participant but reproducible."""
    rng = random.Random(int(hashlib.sha256(f"{pid}:{salt}".encode()).hexdigest(), 16))
    out = list(values)
    rng.shuffle(out)
    return out


def selected_experiment_topics(pid: str) -> List[str]:
    """Return exactly the 4 selected topics: 2 most interesting + 2 least interesting."""
    prog = get_progress(pid)
    selected = list(dict.fromkeys((prog.get("most_topics") or []) + (prog.get("least_topics") or [])))
    if len(selected) != 4:
        raise HTTPException(400, "Participant must select exactly 2 most and 2 least interesting topics before chat assignment.")
    return selected


def topic_preference_label(pid: str, topic_id: str) -> str:
    prog = get_progress(pid)
    if topic_id in (prog.get("most_topics") or []):
        return "most"
    if topic_id in (prog.get("least_topics") or []):
        return "least"
    return "selected"


def generate_conversation_assignments(pid: str, reset_existing: bool = False):
    """Create conversation assignments for one participant.

    TEST MODE used here:
    - participant still selects 2 favorite + 2 least favorite topics
    - only 2 conversations are created
    - 1 conversation uses one favorite topic
    - 1 conversation uses one least favorite topic
    - after these 2 conversations, the participant reaches the thank-you page

    For the full thesis run, replace this test block with the original 16-condition logic.
    """
    prog = get_progress(pid)
    most_topics = list(prog.get("most_topics") or [])
    least_topics = list(prog.get("least_topics") or [])

    if len(most_topics) != 2 or len(least_topics) != 2:
        raise HTTPException(
            400,
            "Participant must select exactly 2 most and 2 least interesting topics before chat assignment.",
        )

    with connect() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) FROM conversation_assignments WHERE participant_id=?",
            (pid,),
        ).fetchone()[0]
        if existing and not reset_existing:
            return
        if reset_existing:
            session_rows = conn.execute(
                "SELECT session_id FROM conversation_assignments WHERE participant_id=?",
                (pid,),
            ).fetchall()
            session_ids = [r[0] for r in session_rows]
            if session_ids:
                conn.executemany("DELETE FROM conversation_turns WHERE session_id=?", [(sid,) for sid in session_ids])
            conn.execute("DELETE FROM conversation_assignments WHERE participant_id=?", (pid,))
            conn.execute("DELETE FROM experiment_sessions WHERE participant_id=?", (pid,))

        favorite_topic = shuffled_for_participant(pid, "test-favorite-topic", most_topics)[0]
        least_topic = shuffled_for_participant(pid, "test-least-topic", least_topics)[0]

        test_rows = [
            {
                "topic_id": favorite_topic,
                "topic_preference": "most",
                "model_size": "small",
                "personality_context_enabled": True,
            },
            {
                "topic_id": least_topic,
                "topic_preference": "least",
                "model_size": "medium",
                "personality_context_enabled": False,
            },
        ]

        # Randomize whether the favorite or least topic appears first.
        test_rows = shuffled_for_participant(pid, "test-two-conversation-order", test_rows)

        rows = []
        for idx, row in enumerate(test_rows):
            topic_id = row["topic_id"]
            variation_id = stable_choice(
                f"{pid}:{topic_id}:test-variant",
                list(TOPICS[topic_id]["variations"].keys()),
            )
            model_size = row["model_size"]
            rows.append({
                "topic_id": topic_id,
                "variation_id": variation_id,
                "topic_prompt": TOPICS[topic_id]["variations"][variation_id],
                "topic_preference": row["topic_preference"],
                "style_name": stable_choice(f"{pid}:{topic_id}:test-style", list(STYLE_PROMPTS.keys())),
                "model_size": model_size,
                "model_name": MEDIUM_LLM_MODEL if model_size == "medium" else SMALL_LLM_MODEL,
                "personality_context_enabled": row["personality_context_enabled"],
            })

        for order, row in enumerate(rows, start=1):
            conn.execute(
                """
                INSERT INTO conversation_assignments(
                    session_id, participant_id, conversation_order, created_at, updated_at,
                    topic_id, variation_id, topic_prompt, topic_preference, style_name,
                    model_size, model_name, personality_context_enabled, status
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()), pid, order, now(), now(),
                    row["topic_id"], row["variation_id"], row["topic_prompt"], row["topic_preference"], row["style_name"],
                    row["model_size"], row["model_name"], int(row["personality_context_enabled"]), "pending",
                ),
            )
        conn.commit()


def count_assignments(pid: str) -> Dict[str, int]:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM conversation_assignments WHERE participant_id=?", (pid,)).fetchone()[0]
        complete = conn.execute("SELECT COUNT(*) FROM conversation_assignments WHERE participant_id=? AND status='complete'", (pid,)).fetchone()[0]
    return {"total": int(total), "complete": int(complete), "remaining": int(total - complete)}


def ensure_assignment(pid):
    generate_conversation_assignments(pid)
    with connect() as conn:
        # Continue an already-started active conversation first.
        row = conn.execute(
            """
            SELECT * FROM conversation_assignments
            WHERE participant_id=? AND status='active'
            ORDER BY conversation_order ASC
            LIMIT 1
            """,
            (pid,),
        ).fetchone()
        if row:
            return dict(row)

        # Otherwise open the next randomized pending conversation.
        row = conn.execute(
            """
            SELECT * FROM conversation_assignments
            WHERE participant_id=? AND status='pending'
            ORDER BY conversation_order ASC
            LIMIT 1
            """,
            (pid,),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE conversation_assignments SET status='active', updated_at=? WHERE session_id=?",
            (now(), row["session_id"]),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM conversation_assignments WHERE session_id=?", (row["session_id"],)).fetchone())


def mark_assignment_complete(session_id: str):
    with connect() as conn:
        conn.execute("UPDATE conversation_assignments SET status='complete', updated_at=? WHERE session_id=?", (now(), session_id))
        conn.commit()


def load_transcript(pid, session_id: Optional[str] = None):
    with connect() as conn:
        if session_id:
            rows = conn.execute(
                "SELECT speaker,text,created_at FROM conversation_turns WHERE participant_id=? AND session_id=? ORDER BY turn_index ASC",
                (pid, session_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT speaker,text,created_at FROM conversation_turns WHERE participant_id=? ORDER BY turn_index ASC",
                (pid,),
            ).fetchall()
    return [dict(r) for r in rows]


def save_turn(pid, speaker, text, session_id: Optional[str] = None):
    with connect() as conn:
        idx = conn.execute(
            "SELECT COALESCE(MAX(turn_index),-1)+1 FROM conversation_turns WHERE participant_id=? AND COALESCE(session_id,'')=COALESCE(?, '')",
            (pid, session_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO conversation_turns(turn_id,participant_id,created_at,speaker,text,turn_index,session_id) VALUES(?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), pid, now(), speaker, text, int(idx), session_id),
        )
        conn.commit()

def personality_context(pid):
    prog = get_progress(pid)
    scores = prog.get("big5_scores") or {}
    return ", ".join(f"{k}: {v}" for k, v in scores.items())

def system_prompt(style_prompt: str, context: str = ""):
    base = """You are Alex, the Engagement Agent in a research experiment about realistic mobile text conversations.
Your job is to keep the participant engaged while sounding like a normal person texting.

Core behaviour:
- Stay strictly on the current scenario/topic. Do not introduce unrelated topics.
- Do not offer links, websites, bookings, files, routes, recipes, checking, looking things up, or fictional future actions.
- Do not say "send me", "i can check", "let's make a plan", "i'll look it up", or anything that pretends you can act outside the chat.
- Do not describe or announce the scenario. Ease into it smoothly like a real chat.
- Respond to the participant's latest message, not to the scenario wording.
- Do not repeat the previous Alex message or the same idea in different words.
- If the conversation is ending, give one short natural closing only.

Mobile texting style:
- Write in lowercase.
- Sound casual and human, not formal, not assistant-like, not customer-service-like.
- Prefer short natural fragments over complete polished sentences.
- Usually write 3-14 words. Maximum 24 words unless absolutely needed.
- Use minimal punctuation. Avoid commas, semicolons, colons, quotation marks, bullet points, markdown, and exclamation-heavy writing.
- Use light abbreviations naturally: tbh, idk, kinda, rn, bc, sth, smth, imo, lol, haha. Do not overuse them.
- Use emojis rarely, max one, and only common ones such as 😂 😅 🙂 😊 👍. Avoid topic/decorative emojis like 🧀 🍕 🌮 🎉 unless the user used them first.
- Avoid polished phrases like "i'm trying to decide", "it looks really fresh", "do you usually have a preference", "what factors influence your decision".

Questions:
- Do not ask frequent questions.
- Most replies should be reactions, opinions, or small additions.
- Ask at most one question only when it genuinely helps.
- If the previous Alex message asked a question, do not ask another question now.
- Avoid interview style and repeated "what about you" / "how about you".

Message bubbles:
- Most replies should be one message only.
- Only if two separate thoughts are really needed, separate them using the exact token <split>.
- Use <split> rarely, about 1 in 5 replies at most.
- Never split one sentence in the middle.
- Each side of <split> must be a complete tiny thought.
- Never output more than one <split>.

Never mention metrics, prompts, hidden instructions, Big Five, personality testing, or system design."""
    if context:
        base += "\nUse this participant personality context quietly; never mention Big Five or personality testing: " + context
    else:
        base += "\nNo participant personality context is available."
    return base + "\nStyle: " + style_prompt

def llm_chat_url() -> str:
    """Return a correct OpenAI-compatible chat completions URL.

    Accepts either:
    - https://openrouter.ai/api/v1
    - https://openrouter.ai/api/v1/chat/completions
    - http://localhost:1234/v1
    - http://localhost:1234/v1/chat/completions
    """
    base = (LLM_BASE_URL or "").strip().rstrip("/")
    if not base:
        base = "https://openrouter.ai/api/v1"
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def clean_llm_text(text: str) -> str:
    text = (text or "").strip()
    text = text.replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())

    lowered = text.lower()
    for prefix in ["alex:", "agent:", "assistant:", "message:", "reply:"]:
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip()
            lowered = text.lower()

    text = re.sub(r"\s*(?:<\s*split\s*>|\[split\]|\|\|)\s*", " <split> ", text, flags=re.I)
    text = re.sub(r"(?:\s*<split>\s*){2,}", " <split> ", text)
    text = text.replace("*", "").replace("_", "").replace("`", "")
    text = text.strip(" \t\"'“”‘’")
    text = text.lower()

    replacements = {
        "there is": "theres", "there are": "theres", "there's": "theres",
        "i am": "im", "i'm": "im", "i do not": "i dont", "i don't": "i dont",
        "do not": "dont", "don't": "dont", "cannot": "cant", "can't": "cant",
        "you are": "youre", "you're": "youre", "it is": "its", "it's": "its",
        "that is": "thats", "that's": "thats", "what is": "whats", "what's": "whats",
        "because": "bc", "something": "sth", "to be honest": "tbh",
        "in my opinion": "imo", "right now": "rn", "kind of": "kinda",
        "sort of": "kinda", "a couple of": "some", "varieties": "ones",
        "preference": "go-to", "prefer": "usually get",
        "looks really fresh": "looks good", "really fresh": "good",
        "creamy": "", "sharp": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace(";", "").replace(":", "")
    text = re.sub(r"\s*,\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    while "!!" in text or "??" in text or ".." in text:
        text = text.replace("!!", "!").replace("??", "?").replace("..", ".")

    if text.count("?") > 1:
        first = text.find("?")
        text = text[: first + 1] + text[first + 1:].replace("?", "")

    if text.count("<split>") > 1:
        first = text.find("<split>")
        text = text[: first + len("<split>")] + text[first + len("<split>"):].replace("<split>", " ")

    if "<split>" in text:
        parts = [p.strip() for p in text.split("<split>", 1)]
        parts = [p[:90].rsplit(" ", 1)[0].strip() if len(p) > 90 else p for p in parts]
        parts = [p for p in parts if p]
        text = " <split> ".join(parts[:2])
    elif len(text) > 120:
        text = text[:120].rsplit(" ", 1)[0].strip()

    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(" .,!\\\"'“”‘’")
    return text

def call_llm(model_name, messages):
    url = llm_chat_url()
    headers = {"Content-Type": "application/json"}

    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    # OpenRouter requires/recommends these app attribution headers.
    if "openrouter.ai" in url:
        headers["HTTP-Referer"] = OPENROUTER_SITE_URL or "http://localhost:5173"
        headers["X-Title"] = OPENROUTER_APP_NAME

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_AGENT_TOKENS,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=120)

        # Give a useful error instead of a vague 404/400.
        if not r.ok:
            detail = r.text[:800]
            raise RuntimeError(
                f"{r.status_code} from {url}. Model={model_name!r}. Response={detail}"
            )

        data = r.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        content = clean_llm_text(content)
        if not content:
            raise RuntimeError(f"Empty LLM response from {url}. Raw={str(data)[:800]}")
        return content

    except Exception as exc:
        return f"[LLM server unavailable or misconfigured: {exc}]"

def previous_agent_asked_question(transcript: List[Dict[str, Any]]) -> bool:
    for turn in reversed(transcript or []):
        if str(turn.get("speaker", "")).lower() == "agent":
            return "?" in str(turn.get("text", ""))
    return False


def make_opening(pid, assignment):
    ctx = personality_context(pid) if assignment["personality_context_enabled"] else ""
    messages = [
        {"role": "system", "content": system_prompt(STYLE_PROMPTS[assignment["style_name"]], ctx)},
        {
            "role": "user",
            "content": (
                "Start a smooth casual mobile chat inspired by the scenario. "
                "Do not summarize it. Do not list options. Do not sound like a questionnaire. "
                "Use lowercase. Keep it very short. Usually one bubble only. "
                "Ask at most one easy natural question, or just make a small comment.\n"
                "Scenario: " + assignment["topic_prompt"]
            ),
        },
    ]
    return call_llm(assignment["model_name"], messages)

def make_reply(pid, assignment, transcript):
    ctx = personality_context(pid) if assignment["personality_context_enabled"] else ""
    no_question = previous_agent_asked_question(transcript)
    instruction = (
        "Continue naturally as Alex. Stay strictly on the scenario. "
        "Reply to the participant's latest message only. "
        "Do not restate the scenario. Do not list options unless the participant already listed them. "
        "Do not offer links, checking, booking, planning, or fictional actions. "
        "Use lowercase casual mobile texting. Say less. Minimal punctuation. "
        "Most of the time send one short thought only. "
        "Use <split> only rarely if there are two separate tiny thoughts."
    )
    if no_question:
        instruction += " The previous Alex message already asked a question, so do not ask a question now."

    messages = [
        {"role": "system", "content": system_prompt(STYLE_PROMPTS[assignment["style_name"]], ctx)},
        {"role": "user", "content": "Scenario context only, do not restate it: " + assignment["topic_prompt"] + "\n" + instruction},
    ]
    for t in transcript[-12:]:
        messages.append({"role": "user" if t["speaker"] == "Human" else "assistant", "content": t["text"]})
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
class ParticipantLoginIn(BaseModel): access_code: str
class AccessCodeBatchIn(BaseModel): count: int = 1

@app.get("/")
def root():
    return {"status": "ok", "app": "LLM Engagement Study API", "docs": "/docs"}

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/api/meta")
def meta():
    return {"topics": TOPICS, "bfi_items": BFI_ITEMS, "target_total_turns": TARGET_TOTAL_TURNS}

@app.post("/api/session")
def session(data: SessionIn):
    # Backward-compatible session restore from localStorage.
    # For real participant recruitment, prefer /api/participant/login with an access code.
    p = get_or_create_participant(data.participant_id)
    return get_progress(p["participant_id"])


@app.post("/api/participant/login")
def participant_login(data: ParticipantLoginIn):
    return login_with_access_code(data.access_code)

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
    required = [
        "age_group", "gender", "education", "messaging_app_use",
        "text_communication_ease_1_5", "message_style_one_two_words",
        "message_style_single_sentence", "message_style_short_2_3_sentences",
        "message_style_long_detailed", "used_ai_before",
    ]
    missing = [key for key in required if data.answers.get(key) in (None, "")]
    if data.answers.get("used_ai_before") == "Yes":
        for key in ["ai_use_general_purpose", "ai_use_specific_purpose"]:
            if data.answers.get(key) in (None, ""):
                missing.append(key)
        emotions = data.answers.get("ai_experience_emotions") or {}
        for emotion in [
            "insecure", "helpless", "excluded", "threatened", "critical", "frustrated",
            "humiliated", "bitter", "hurt", "guilty", "powerless", "lonely",
            "powerful", "excited", "proud", "hopeful", "startled", "disapproving",
            "awful", "repelled",
        ]:
            if emotions.get(emotion) in (None, ""):
                missing.append(f"emotion_{emotion}")
    if missing:
        raise HTTPException(400, "Please complete all required questions.")
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
    generate_conversation_assignments(data.participant_id, reset_existing=True)
    set_step(data.participant_id, "chat")
    return get_progress(data.participant_id)

@app.get("/api/chat/{participant_id}")
def chat(participant_id: str):
    assignment = ensure_assignment(participant_id)
    counts = count_assignments(participant_id)
    if not assignment:
        set_step(participant_id, "done", completed=1)
        return {"done": True, "all_done": True, "transcript": [], "turns": 0, "target_total_turns": TARGET_TOTAL_TURNS, "assignment_counts": counts}

    transcript = load_transcript(participant_id, assignment["session_id"])
    if not transcript:
        save_turn(participant_id, "Agent", make_opening(participant_id, assignment), assignment["session_id"])
        transcript = load_transcript(participant_id, assignment["session_id"])

    return {
        "done": False,
        "all_done": False,
        "assignment": {
            "session_id": assignment["session_id"],
            "conversation_order": assignment["conversation_order"],
            "total_conversations": counts["total"],
            "completed_conversations": counts["complete"],
            "remaining_conversations": counts["remaining"],
            "topic_id": assignment["topic_id"],
            "variation_id": assignment["variation_id"],
            "topic_prompt": assignment["topic_prompt"],
            "topic_preference": assignment["topic_preference"],
            "style_name": assignment["style_name"],
            "model_size": assignment["model_size"],
            "model_name": assignment["model_name"],
            "personality_context_enabled": bool(assignment["personality_context_enabled"]),
            "status": assignment["status"],
        },
        "assignment_counts": counts,
        "transcript": transcript,
        "turns": len(transcript),
        "target_total_turns": TARGET_TOTAL_TURNS,
    }


@app.post("/api/chat")
def chat_send(data: ChatIn):
    text = data.text.strip()
    if not text:
        raise HTTPException(400, "Message is empty")

    assignment = ensure_assignment(data.participant_id)
    if not assignment:
        set_step(data.participant_id, "done", completed=1)
        return {"done": True, "all_done": True, "transcript": []}

    session_id = assignment["session_id"]
    save_turn(data.participant_id, "Human", text, session_id)
    transcript = load_transcript(data.participant_id, session_id)

    if len(transcript) >= TARGET_TOTAL_TURNS:
        mark_assignment_complete(session_id)
        counts = count_assignments(data.participant_id)
        all_done = counts["remaining"] == 0
        if all_done:
            set_step(data.participant_id, "done", completed=1)
        return {"done": True, "all_done": all_done, "transcript": transcript, "assignment_counts": counts}

    reply = make_reply(data.participant_id, assignment, transcript)
    save_turn(data.participant_id, "Agent", reply, session_id)
    transcript = load_transcript(data.participant_id, session_id)

    conversation_done = len(transcript) >= TARGET_TOTAL_TURNS
    if conversation_done:
        mark_assignment_complete(session_id)
    counts = count_assignments(data.participant_id)
    all_done = counts["remaining"] == 0
    if all_done and conversation_done:
        set_step(data.participant_id, "done", completed=1)

    return {"done": conversation_done, "all_done": all_done, "transcript": transcript, "assignment_counts": counts}


@app.post("/api/finish/{participant_id}")
def finish(participant_id: str):
    with connect() as conn:
        active = conn.execute(
            """
            SELECT * FROM conversation_assignments
            WHERE participant_id=? AND status='active'
            ORDER BY conversation_order ASC
            LIMIT 1
            """,
            (participant_id,),
        ).fetchone()

    if active:
        mark_assignment_complete(active["session_id"])

    counts = count_assignments(participant_id)

    if counts["remaining"] <= 0:
        set_step(participant_id, "done", completed=1)
    else:
        set_step(participant_id, "chat", completed=0)

    return get_progress(participant_id)

@app.post("/api/researcher/login")
def researcher_login(data: LoginIn):
    if not hmac.compare_digest(data.password, RESEARCHER_PASSWORD): raise HTTPException(401, "Wrong password")
    return {"token": researcher_token()}


@app.post("/api/researcher/access-codes", dependencies=[Depends(require_researcher)])
def researcher_create_access_codes(data: AccessCodeBatchIn):
    init_db()
    return {"codes": create_access_codes(data.count)}

@app.get("/api/researcher/overview", dependencies=[Depends(require_researcher)])
def overview():
    init_db()
    with connect() as conn:
        participants = [dict(r) for r in conn.execute("SELECT * FROM participants ORDER BY created_at DESC").fetchall()]
        sessions = [dict(r) for r in conn.execute("SELECT * FROM conversation_assignments ORDER BY participant_id, conversation_order ASC").fetchall()]
        access_codes = [dict(r) for r in conn.execute("SELECT access_code,participant_id,created_at,used_at,last_login_at,is_active FROM participant_access_codes ORDER BY created_at DESC").fetchall()]
    return {"participants": participants, "sessions": sessions, "access_codes": access_codes}


@app.get("/api/researcher/participant/{participant_id}", dependencies=[Depends(require_researcher)])
def participant_detail(participant_id: str):
    assignment = ensure_assignment(participant_id)
    session_id = assignment["session_id"] if assignment else None
    with connect() as conn:
        assignments = [dict(r) for r in conn.execute("SELECT * FROM conversation_assignments WHERE participant_id=? ORDER BY conversation_order ASC", (participant_id,)).fetchall()]
    return {"progress": get_progress(participant_id), "assignment": assignment, "assignments": assignments, "transcript": load_transcript(participant_id, session_id)}


@app.get("/api/researcher/export.csv", dependencies=[Depends(require_researcher)])
def export_csv():
    init_db()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "participant_id", "access_code", "participant_created_at", "current_step", "completed",
        "session_id", "conversation_order", "assignment_status", "topic_id", "variation_id",
        "topic_preference", "model_size", "model_name", "personality_context_enabled",
        "style_name", "speaker", "text", "timestamp"
    ])
    with connect() as conn:
        rows = conn.execute("""
            SELECT
                p.participant_id, ac.access_code, p.created_at AS participant_created_at, p.current_step, p.completed,
                a.session_id, a.conversation_order, a.status AS assignment_status, a.topic_id, a.variation_id,
                a.topic_preference, a.model_size, a.model_name, a.personality_context_enabled, a.style_name,
                c.speaker, c.text, c.created_at AS turn_time, c.turn_index
            FROM participants p
            LEFT JOIN participant_access_codes ac ON p.participant_id=ac.participant_id
            LEFT JOIN conversation_assignments a ON p.participant_id=a.participant_id
            LEFT JOIN conversation_turns c ON a.session_id=c.session_id
            ORDER BY p.created_at DESC, a.conversation_order ASC, c.turn_index ASC
        """).fetchall()
    for r in rows:
        writer.writerow([
            r["participant_id"], r["access_code"] or "", r["participant_created_at"], r["current_step"], r["completed"],
            r["session_id"] or "", r["conversation_order"] or "", r["assignment_status"] or "", r["topic_id"] or "", r["variation_id"] or "",
            r["topic_preference"] or "", r["model_size"] or "", r["model_name"] or "", r["personality_context_enabled"] if r["personality_context_enabled"] is not None else "",
            r["style_name"] or "", r["speaker"] or "", r["text"] or "", r["turn_time"] or "",
        ])
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=llm_engagement_export.csv"})
