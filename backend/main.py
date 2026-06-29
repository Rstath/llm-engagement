import csv
import hashlib
import hmac
import io
import json
import math
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
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
WINDOW_SIZE = int(os.getenv("METRIC_WINDOW_SIZE", "3"))
_embedding_model = None

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
            least_topics_json TEXT NOT NULL DEFAULT '[]',
            post_json TEXT NOT NULL DEFAULT '{}'
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

        -- New architecture: one participant has a randomized queue of 16 conversations.
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

        CREATE TABLE IF NOT EXISTS conversation_turn_metrics (
            turn_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            participant_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL,
            speaker TEXT NOT NULL,
            text TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            token_count INTEGER NOT NULL,
            is_question INTEGER NOT NULL,
            embedding_json TEXT NOT NULL DEFAULT '[]',
            topic_similarity REAL,
            prev_similarity REAL,
            windowed_similarity REAL,
            novelty REAL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_session_metrics (
            session_id TEXT PRIMARY KEY,
            participant_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            topic_preference TEXT NOT NULL,
            model_size TEXT NOT NULL,
            model_name TEXT NOT NULL,
            personality_context_enabled INTEGER NOT NULL,
            style_name TEXT NOT NULL,
            topic_prompt TEXT NOT NULL,
            topic_embedding_json TEXT NOT NULL DEFAULT '[]',
            total_turns INTEGER NOT NULL,
            human_turns INTEGER NOT NULL,
            agent_turns INTEGER NOT NULL,
            total_words INTEGER NOT NULL,
            total_tokens INTEGER NOT NULL,
            coherence REAL,
            windowed_coherence REAL,
            topic_consistency REAL,
            novelty REAL,
            turn_balance REAL,
            token_balance REAL,
            question_rate REAL,
            engagement_score REAL,
            updated_at TEXT NOT NULL
        );
        """)
        # Safe migration for existing local SQLite databases created before session_id existed.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(conversation_turns)").fetchall()]
        if "session_id" not in cols:
            conn.execute("ALTER TABLE conversation_turns ADD COLUMN session_id TEXT")

        progress_cols = [r[1] for r in conn.execute("PRAGMA table_info(progress)").fetchall()]
        if "post_json" not in progress_cols:
            conn.execute("ALTER TABLE progress ADD COLUMN post_json TEXT NOT NULL DEFAULT '{}'")
        conn.commit()

def jdump(v): return json.dumps(v, ensure_ascii=False)
def jload(v, default):
    try: return json.loads(v or jdump(default))
    except Exception: return default

def row_to_progress(row):
    return {
        "consent": jload(row["consent_json"], {}),
        "pre": jload(row["pre_json"], {}),
        "big5_answers": jload(row["big5_answers_json"], {}),
        "big5_scores": jload(row["big5_scores_json"], {}),
        "most_topics": jload(row["most_topics_json"], []),
        "least_topics": jload(row["least_topics_json"], []),
        "post": jload(row["post_json"] if "post_json" in row.keys() else "{}", {}),
    }

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

    TEST MODE:
    - Creates only 1 conversation so you can quickly reach the post-questionnaire
      and thank-you page.
    - Uses the first "most interesting" selected topic.
    - Uses medium model with personality context enabled.

    For the real study, restore the full 16-condition assignment logic.
    """
    selected_topics = selected_experiment_topics(pid)

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

        rows = []

        # ---------- TEST MODE ----------
        # Only ONE conversation is generated so you can quickly test:
        # conversation -> post-experiment questionnaire -> thank-you page.
        #
        # It uses the participant's first "most interesting" selected topic.
        # Condition: medium model + personality context enabled.
        # For the real study, restore the full 16-condition block.
        prog = get_progress(pid)
        topic_id = (prog.get("most_topics") or selected_topics)[0]

        variation_id = stable_choice(
            f"{pid}:{topic_id}:single-test-variant",
            list(TOPICS[topic_id]["variations"].keys()),
        )

        rows.append({
            "topic_id": topic_id,
            "variation_id": variation_id,
            "topic_prompt": TOPICS[topic_id]["variations"][variation_id],
            "topic_preference": topic_preference_label(pid, topic_id),
            "style_name": stable_choice(
                f"{pid}:{topic_id}:single-test-style",
                list(STYLE_PROMPTS.keys()),
            ),
            "model_size": "medium",
            "model_name": MEDIUM_LLM_MODEL,
            "personality_context_enabled": True,
        })

        # No shuffle needed because there is only one test conversation.
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
- Every reply should give the participant something easy to react to.
For the FIRST message only:
- Never react to imaginary previous messages.
- Never start with agreement.
- Never start with sympathy.
- Never start with "yeah", "exactly", "same", "good point", "fair enough", "thats annoying", "its tricky".
- Introduce the situation naturally first.
- Make it obvious what the chat is about within the first one or two bubbles.
- Avoid vague filler like "good point", "yeah true", "fair enough", "its tricky", or "it depends" unless you add a concrete opinion right after.
- After agreeing, add one clear opinion, observation, preference, or small personal reaction.
- Have your own small opinion. Do not only mirror the participant.
- Slight friendly disagreement is okay.
- Every message should move the conversation forward with one new detail, preference, reaction, or experience.
- Avoid sounding too uncertain too often. Prefer "id go for", "id rather", "i usually" over constant "maybe", "i guess", or "probably".
- Never explain your reasoning like an assistant. Do not teach, summarize, or give balanced pros and cons. Just chat.
- If the conversation is ending, give one short natural closing only.
- When ending, do not repeat yourself, do not summarize the discussion, and do not suddenly thank the participant.

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
- Only ask a question when the conversation would naturally stop without one.
- Otherwise make a statement instead.
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

    # Reduce vague chatbot-like acknowledgements that confuse participants.
    vague_prefixes = [
        "oh no ",
        "oh yeah ",
        "yeah ",
        "exactly ",
        "same ",
        "good point ",
        "fair enough ",
        "thats annoying ",
        "thats frustrating ",
        "its tricky ",
        "yeah true ",
        "true true ",
    ]
    for prefix in vague_prefixes:
        if text.startswith(prefix) and len(text) > len(prefix) + 8:
            text = text[len(prefix):].strip()
            break

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

def fallback_opening_for_topic(assignment):
    topic_id = assignment["topic_id"]
    prompt = assignment["topic_prompt"].lower()

    if topic_id == "T1":
        return "way too many options at the supermarket rn"
    if topic_id == "T2":
        return "my friend wants to order food i barely know 😅"
    if topic_id == "T3":
        return "im stuck between two online shops rn"
    if topic_id == "T4":
        return "my mornings are always a bit rushed"
    if topic_id == "T5":
        return "finally got home after a long day"
    if topic_id == "T6":
        return "my order came wrong and im annoyed tbh"
    if topic_id == "T7":
        return "thinking about having a few friends over"
    if topic_id == "T8":
        return "kinda wanna plan a short trip in greece"
    return "need ur opinion on sth"

def make_opening(pid, assignment):
    ctx = personality_context(pid) if assignment["personality_context_enabled"] else ""
    messages = [
        {"role": "system", "content": system_prompt(STYLE_PROMPTS[assignment["style_name"]], ctx)},
        {
            "role": "user",
            "content": (
                "Generate ONLY the first message(s) of a new mobile conversation.\n\n"

                "The participant has NOT seen the scenario.\n"
                "Never assume they know what happened.\n\n"

                "Start by naturally introducing the situation.\n"
                "Do NOT react to something that hasn't been mentioned yet.\n"
                "Do NOT start with agreement.\n"
                "Do NOT start with sympathy.\n"
                "Do NOT start with 'good point', 'yeah', 'thats annoying', 'same', 'exactly', etc.\n\n"
                "The first message MUST mention one concrete element from the scenario (e.g. cheese, supermarket, online shop, order, dinner, morning, trip)."
                "Do not start with an emotion or reaction."
                "Start with the situation itself."

                "Good openings:\n"
                "- need ur opinion 😅 <split> im looking at 2 online shops rn\n"
                "- way too many cheeses here lol\n"
                "- went out for dinner earlier\n"
                "- my mornings are always rushed 😂\n\n"

                "Bad openings:\n"
                "- thats frustrating\n"
                "- yeah id do the same\n"
                "- exactly\n"
                "- good point\n"
                "- price vs reviews is tricky\n\n"

                "The participant should immediately understand what the conversation is about.\n"
                "Do not explain the scenario.\n"
                "Just ease into it naturally.\n\n"

                "Scenario:\n"
                + assignment["topic_prompt"]
            ),
        },
    ]
    opening = call_llm(assignment["model_name"], messages)

    bad_starts = (
        "yeah",
        "exactly",
        "same",
        "good point",
        "fair enough",
        "thats frustrating",
        "its tricky",
        "oh no",
    )

    if opening.lower().startswith(bad_starts):
        return fallback_opening_for_topic(assignment)

    return opening

def make_reply(pid, assignment, transcript):
    ctx = personality_context(pid) if assignment["personality_context_enabled"] else ""
    no_question = previous_agent_asked_question(transcript)
    instruction = (
        "Continue naturally as Alex. Stay strictly on the scenario. "
        "Reply mainly to the participant's latest message, but keep the last 2-3 turns in mind so the chat feels continuous. "
        "Each reply should answer what the participant said, add one new concrete thought, and make it obvious how they could naturally continue. "
        "Do not restate the scenario. Do not list options unless the participant already listed them. "
        "Do not offer links, checking, booking, planning, or fictional actions. "
        "Avoid vague filler like good point, yeah true, fair enough, its tricky, or it depends unless followed by a clear opinion. "
        "Have your own small opinion or preference. Do not just mirror the participant. "
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


def clamp01(value: Optional[float]) -> float:
    if value is None or not isinstance(value, (int, float)) or math.isnan(float(value)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def approx_token_count(text: str) -> int:
    # Good enough for interaction analytics without adding tokenizer dependencies.
    return max(1, round(len(str(text or '').split()) * 1.3))


def is_question_text(text: str) -> bool:
    s = str(text or '').lower()
    question_words = ('what', 'why', 'how', 'when', 'where', 'which', 'who', 'would you', 'do you', 'did you', 'are you', 'can you')
    return '?' in s or any(s.startswith(q + ' ') for q in question_words)


def hash_embedding(text: str, dim: int = 384) -> List[float]:
    """Deterministic fallback if sentence-transformers is not installed."""
    vec = [0.0] * dim
    tokens = re.findall(r"[\w']+", str(text or '').lower())
    if not tokens:
        tokens = ['empty']
    for tok in tokens:
        digest = hashlib.sha256(tok.encode('utf-8')).digest()
        for i, b in enumerate(digest):
            idx = (b + i * 31) % dim
            vec[idx] += 1.0 if b % 2 else -1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


def get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        return _embedding_model
    except Exception:
        _embedding_model = False
        return None


def embed_texts(texts: List[str]) -> List[List[float]]:
    model = get_embedding_model()
    if model:
        vectors = model.encode(texts, normalize_embeddings=True).tolist()
        return [[round(float(x), 6) for x in v] for v in vectors]
    return [hash_embedding(t) for t in texts]


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = math.sqrt(sum(float(x) * float(x) for x in a[:n]))
    nb = math.sqrt(sum(float(x) * float(x) for x in b[:n]))
    if not na or not nb:
        return 0.0
    # Convert cosine from [-1, 1] to [0, 1] for easier dashboard interpretation.
    return round((dot / (na * nb) + 1.0) / 2.0, 4)


def average_vector(vectors: List[List[float]]) -> List[float]:
    vectors = [v for v in vectors if v]
    if not vectors:
        return []
    n = min(len(v) for v in vectors)
    avg = [sum(v[i] for v in vectors) / len(vectors) for i in range(n)]
    norm = math.sqrt(sum(x * x for x in avg)) or 1.0
    return [x / norm for x in avg]


def compute_and_store_session_metrics(session_id: str):
    init_db()
    with connect() as conn:
        assignment = conn.execute(
            "SELECT * FROM conversation_assignments WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if not assignment:
            return None
        turns = conn.execute(
            """
            SELECT turn_id, participant_id, created_at, speaker, text, turn_index, session_id
            FROM conversation_turns
            WHERE session_id=?
            ORDER BY turn_index ASC
            """,
            (session_id,),
        ).fetchall()
        if not turns:
            return None

    texts = [assignment['topic_prompt']] + [r['text'] for r in turns]
    vectors = embed_texts(texts)
    topic_embedding = vectors[0]
    turn_embeddings = vectors[1:]

    turn_metric_rows = []
    prev_sims = []
    topic_sims = []
    window_sims = []
    novelties = []

    for i, r in enumerate(turns):
        emb = turn_embeddings[i]
        topic_sim = cosine(emb, topic_embedding)
        prev_sim = cosine(emb, turn_embeddings[i - 1]) if i > 0 else None
        if i > 0:
            window_start = max(0, i - WINDOW_SIZE)
            context_vec = average_vector(turn_embeddings[window_start:i])
            window_sim = cosine(emb, context_vec)
        else:
            window_sim = None
        novelty = round(1.0 - prev_sim, 4) if prev_sim is not None else None

        if prev_sim is not None:
            prev_sims.append(prev_sim)
            novelties.append(novelty)
        if window_sim is not None:
            window_sims.append(window_sim)
        topic_sims.append(topic_sim)

        wc = len(str(r['text'] or '').split())
        tc = approx_token_count(r['text'])
        turn_metric_rows.append((
            r['turn_id'], session_id, r['participant_id'], int(r['turn_index']), r['speaker'], r['text'],
            wc, tc, int(is_question_text(r['text'])), jdump(emb), topic_sim, prev_sim, window_sim, novelty, now()
        ))

    human_turns = [r for r in turns if r['speaker'] == 'Human']
    agent_turns = [r for r in turns if r['speaker'] == 'Agent']
    human_tokens = sum(approx_token_count(r['text']) for r in human_turns)
    agent_tokens = sum(approx_token_count(r['text']) for r in agent_turns)
    total_tokens = human_tokens + agent_tokens
    total_words = sum(len(str(r['text'] or '').split()) for r in turns)

    coherence = round(sum(prev_sims) / max(1, len(prev_sims)), 4)
    windowed_coherence = round(sum(window_sims) / max(1, len(window_sims)), 4)
    topic_consistency = round(sum(topic_sims) / max(1, len(topic_sims)), 4)
    novelty = round(sum(novelties) / max(1, len(novelties)), 4)
    turn_balance = round(min(len(human_turns), len(agent_turns)) / max(1, max(len(human_turns), len(agent_turns))), 4)
    token_balance = round(min(human_tokens, agent_tokens) / max(1, max(human_tokens, agent_tokens)), 4)
    question_rate = round(sum(1 for r in turns if is_question_text(r['text'])) / max(1, len(turns)), 4)
    engagement_score = round(
        0.30 * coherence
        + 0.25 * topic_consistency
        + 0.20 * novelty
        + 0.10 * turn_balance
        + 0.15 * question_rate,
        4,
    )

    with connect() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO conversation_turn_metrics(
                turn_id, session_id, participant_id, turn_index, speaker, text,
                word_count, token_count, is_question, embedding_json,
                topic_similarity, prev_similarity, windowed_similarity, novelty, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            turn_metric_rows,
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO conversation_session_metrics(
                session_id, participant_id, topic_id, topic_preference, model_size, model_name,
                personality_context_enabled, style_name, topic_prompt, topic_embedding_json,
                total_turns, human_turns, agent_turns, total_words, total_tokens,
                coherence, windowed_coherence, topic_consistency, novelty,
                turn_balance, token_balance, question_rate, engagement_score, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                session_id, assignment['participant_id'], assignment['topic_id'], assignment['topic_preference'],
                assignment['model_size'], assignment['model_name'], int(assignment['personality_context_enabled']),
                assignment['style_name'], assignment['topic_prompt'], jdump(topic_embedding), len(turns),
                len(human_turns), len(agent_turns), total_words, total_tokens, coherence,
                windowed_coherence, topic_consistency, novelty, turn_balance, token_balance,
                question_rate, engagement_score, now(),
            ),
        )
        conn.commit()

    return {
        'session_id': session_id,
        'coherence': coherence,
        'windowed_coherence': windowed_coherence,
        'topic_consistency': topic_consistency,
        'novelty': novelty,
        'turn_balance': turn_balance,
        'token_balance': token_balance,
        'question_rate': question_rate,
        'engagement_score': engagement_score,
    }


def compute_all_completed_metrics():
    with connect() as conn:
        rows = conn.execute("SELECT session_id FROM conversation_assignments WHERE status='complete'").fetchall()
    for r in rows:
        compute_and_store_session_metrics(r['session_id'])


def avg_float(rows, key: str) -> float:
    vals = [float(r[key]) for r in rows if r[key] is not None]
    return round(sum(vals) / max(1, len(vals)), 4)


def group_average(rows, group_key: str, metric_key: str) -> List[Dict[str, Any]]:
    groups: Dict[str, List[float]] = {}
    for r in rows:
        label = str(r[group_key])
        if r[metric_key] is not None:
            groups.setdefault(label, []).append(float(r[metric_key]))
    return [
        {'label': label, 'value': round(sum(vals) / max(1, len(vals)), 4), 'count': len(vals)}
        for label, vals in sorted(groups.items())
    ]


def group_count(rows, group_key: str) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for r in rows:
        counts[str(r[group_key])] = counts.get(str(r[group_key]), 0) + 1
    return [{'label': k, 'value': v} for k, v in sorted(counts.items())]


# ---------------- Research dashboard statistics ----------------
def percentile(values: List[float], p: float) -> float:
    vals = sorted(float(v) for v in values if v is not None)
    if not vals:
        return 0.0
    if len(vals) == 1:
        return round(vals[0], 4)
    k = (len(vals) - 1) * p
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return round(vals[lo], 4)
    return round(vals[lo] * (hi - k) + vals[hi] * (k - lo), 4)


def descriptive_stats(values: List[float]) -> Dict[str, Any]:
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if not vals:
        return {"n": 0, "mean": 0, "median": 0, "sd": 0, "min": 0, "max": 0, "q1": 0, "q3": 0, "ci95_low": 0, "ci95_high": 0}
    mean = sum(vals) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in vals) / max(1, n - 1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n > 1 else 0.0
    return {
        "n": n,
        "mean": round(mean, 4),
        "median": percentile(vals, 0.5),
        "sd": round(sd, 4),
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
        "q1": percentile(vals, 0.25),
        "q3": percentile(vals, 0.75),
        "ci95_low": round(mean - 1.96 * se, 4),
        "ci95_high": round(mean + 1.96 * se, 4),
    }


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))


def chi_square_sf_approx(x: float, df: int) -> float:
    if df <= 0:
        return 1.0
    if x <= 0:
        return 1.0
    # Wilson-Hilferty transformation approximation.
    z = ((x / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    return round(max(0.0, min(1.0, 1.0 - norm_cdf(z))), 6)


def rank_values(values: List[float]) -> List[float]:
    indexed = sorted((float(v), i) for i, v in enumerate(values))
    ranks = [0.0] * len(values)
    pos = 0
    while pos < len(indexed):
        end = pos
        while end + 1 < len(indexed) and indexed[end + 1][0] == indexed[pos][0]:
            end += 1
        rank = (pos + 1 + end + 1) / 2.0
        for j in range(pos, end + 1):
            ranks[indexed[j][1]] = rank
        pos = end + 1
    return ranks


def pearson_corr(x: List[float], y: List[float]) -> float:
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    xs = [float(v) for v in x[:n]]
    ys = [float(v) for v in y[:n]]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    denx = math.sqrt(sum((v - mx) ** 2 for v in xs))
    deny = math.sqrt(sum((v - my) ** 2 for v in ys))
    return 0.0 if not denx or not deny else num / (denx * deny)


def spearman_corr(x: List[float], y: List[float]) -> Dict[str, Any]:
    n = min(len(x), len(y))
    if n < 4:
        return {"n": n, "rho": 0, "p": None, "note": "need at least 4 paired observations"}
    rho = pearson_corr(rank_values(x[:n]), rank_values(y[:n]))
    # Normal approximation for Spearman via t approximation, then normal fallback.
    t = rho * math.sqrt((n - 2) / max(1e-12, 1 - rho * rho))
    # p approximate using normal when scipy is unavailable.
    p = 2 * (1 - norm_cdf(abs(t)))
    return {"n": n, "rho": round(rho, 4), "p": round(max(0.0, min(1.0, p)), 6)}


def wilcoxon_signed_rank(x: List[float], y: List[float]) -> Dict[str, Any]:
    diffs = [float(a) - float(b) for a, b in zip(x, y) if a is not None and b is not None and abs(float(a) - float(b)) > 1e-12]
    n = len(diffs)
    if n < 5:
        return {"test": "Wilcoxon signed-rank", "n": n, "statistic": None, "p": None, "effect_size_r": None, "note": "need at least 5 non-zero paired differences"}
    abs_diffs = [abs(d) for d in diffs]
    ranks = rank_values(abs_diffs)
    w_plus = sum(r for r, d in zip(ranks, diffs) if d > 0)
    w_minus = sum(r for r, d in zip(ranks, diffs) if d < 0)
    w = min(w_plus, w_minus)
    mean = n * (n + 1) / 4.0
    var = n * (n + 1) * (2 * n + 1) / 24.0
    z = (w - mean) / math.sqrt(var) if var else 0.0
    p = 2 * (1 - norm_cdf(abs(z)))
    return {"test": "Wilcoxon signed-rank", "n": n, "statistic": round(w, 4), "p": round(max(0.0, min(1.0, p)), 6), "effect_size_r": round(abs(z) / math.sqrt(n), 4)}


def paired_by_participant(rows: List[Dict[str, Any]], condition_key: str, a: Any, b: Any, metric_key: str) -> Dict[str, List[float]]:
    grouped: Dict[str, Dict[str, List[float]]] = {}
    for r in rows:
        if r.get(metric_key) is None:
            continue
        pid = str(r.get("participant_id"))
        label = str(r.get(condition_key))
        grouped.setdefault(pid, {}).setdefault(label, []).append(float(r[metric_key]))
    xs, ys = [], []
    for vals in grouped.values():
        if str(a) in vals and str(b) in vals:
            xs.append(sum(vals[str(a)]) / len(vals[str(a)]))
            ys.append(sum(vals[str(b)]) / len(vals[str(b)]))
    return {"x": xs, "y": ys}


def friedman_test_by_participant(rows: List[Dict[str, Any]], condition_key: str, metric_key: str) -> Dict[str, Any]:
    labels = sorted({str(r.get(condition_key)) for r in rows if r.get(metric_key) is not None})
    if len(labels) < 3:
        return {"test": "Friedman", "n": 0, "k": len(labels), "statistic": None, "p": None, "note": "need at least 3 repeated conditions"}
    by_pid: Dict[str, Dict[str, List[float]]] = {}
    for r in rows:
        if r.get(metric_key) is None:
            continue
        by_pid.setdefault(str(r.get("participant_id")), {}).setdefault(str(r.get(condition_key)), []).append(float(r[metric_key]))
    complete = []
    for vals in by_pid.values():
        if all(label in vals for label in labels):
            complete.append([sum(vals[label]) / len(vals[label]) for label in labels])
    n = len(complete)
    k = len(labels)
    if n < 2:
        return {"test": "Friedman", "n": n, "k": k, "statistic": None, "p": None, "note": "need at least 2 participants with all repeated conditions"}
    rank_sums = [0.0] * k
    for row in complete:
        ranks = rank_values(row)
        for i, rank in enumerate(ranks):
            rank_sums[i] += rank
    chi2 = (12 / (n * k * (k + 1))) * sum(rs * rs for rs in rank_sums) - 3 * n * (k + 1)
    p = chi_square_sf_approx(chi2, k - 1)
    return {"test": "Friedman", "n": n, "k": k, "conditions": labels, "statistic": round(chi2, 4), "p": p}


def histogram(values: List[float], bins: int = 10, lo: float = 0.0, hi: float = 1.0) -> List[Dict[str, Any]]:
    counts = [0] * bins
    for v in values:
        try:
            x = float(v)
        except Exception:
            continue
        idx = int((x - lo) / max(1e-12, hi - lo) * bins)
        idx = max(0, min(bins - 1, idx))
        counts[idx] += 1
    out = []
    for i, count in enumerate(counts):
        start = lo + i * (hi - lo) / bins
        end = lo + (i + 1) * (hi - lo) / bins
        out.append({"label": f"{start:.1f}-{end:.1f}", "value": count})
    return out


def boxplot_groups(rows: List[Dict[str, Any]], group_key: str, metric_key: str) -> List[Dict[str, Any]]:
    groups: Dict[str, List[float]] = {}
    for r in rows:
        if r.get(metric_key) is not None:
            groups.setdefault(str(r.get(group_key)), []).append(float(r[metric_key]))
    result = []
    for label, vals in sorted(groups.items()):
        st = descriptive_stats(vals)
        result.append({"label": label, **st})
    return result


def grouped_metric_matrix(rows: List[Dict[str, Any]], group_key: str, metrics: List[str]) -> List[Dict[str, Any]]:
    groups = sorted({str(r.get(group_key)) for r in rows})
    out = []
    for metric in metrics:
        row = {"metric": metric}
        for group in groups:
            vals = [float(r[metric]) for r in rows if str(r.get(group_key)) == group and r.get(metric) is not None]
            row[group] = round(sum(vals) / max(1, len(vals)), 4)
        out.append(row)
    return out


def topic_context_heatmap(rows: List[Dict[str, Any]], metric_key: str = "engagement_score") -> List[Dict[str, Any]]:
    topics = sorted({str(r.get("topic_id")) for r in rows})
    out = []
    for topic in topics:
        row = {"topic": topic}
        for ctx_label, ctx_value in [("no_context", 0), ("context", 1)]:
            vals = [float(r[metric_key]) for r in rows if str(r.get("topic_id")) == topic and int(r.get("personality_context_enabled") or 0) == ctx_value and r.get(metric_key) is not None]
            row[ctx_label] = round(sum(vals) / max(1, len(vals)), 4) if vals else None
            row[f"{ctx_label}_n"] = len(vals)
        out.append(row)
    return out


def compute_research_statistics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    metric_keys = ["engagement_score", "coherence", "windowed_coherence", "topic_consistency", "novelty", "turn_balance", "token_balance", "question_rate"]
    descriptives = {m: descriptive_stats([r.get(m) for r in rows]) for m in metric_keys}

    model_pair = paired_by_participant(rows, "model_size", "medium", "small", "engagement_score")
    context_pair = paired_by_participant(rows, "personality_context_enabled", "1", "0", "engagement_score")

    return {
        "descriptives": descriptives,
        "tests": {
            "model_medium_vs_small_engagement": wilcoxon_signed_rank(model_pair["x"], model_pair["y"]),
            "context_vs_no_context_engagement": wilcoxon_signed_rank(context_pair["x"], context_pair["y"]),
            "topic_effect_engagement": friedman_test_by_participant(rows, "topic_id", "engagement_score"),
        },
        "distributions": {
            "engagement_histogram": histogram([r.get("engagement_score") for r in rows if r.get("engagement_score") is not None]),
            "engagement_box_by_model": boxplot_groups(rows, "model_size", "engagement_score"),
            "engagement_box_by_context": boxplot_groups(rows, "personality_context_enabled", "engagement_score"),
        },
        "matrices": {
            "model_metrics": grouped_metric_matrix(rows, "model_size", ["engagement_score", "coherence", "topic_consistency", "novelty", "question_rate"]),
            "context_metrics": grouped_metric_matrix(rows, "personality_context_enabled", ["engagement_score", "coherence", "topic_consistency", "novelty", "question_rate"]),
            "topic_context_heatmap": topic_context_heatmap(rows, "engagement_score"),
        },
    }


def compute_big5_correlations(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_pid: Dict[str, List[float]] = {}
    for r in rows:
        if r.get("engagement_score") is not None:
            by_pid.setdefault(str(r.get("participant_id")), []).append(float(r["engagement_score"]))
    if not by_pid:
        return []
    with connect() as conn:
        progress = [dict(r) for r in conn.execute("SELECT participant_id,big5_scores_json FROM progress").fetchall()]
    traits = ["Extraversion", "Agreeableness", "Conscientiousness", "Neuroticism", "Openness"]
    result = []
    for trait in traits:
        xs, ys = [], []
        for p in progress:
            pid = str(p["participant_id"])
            scores = jload(p.get("big5_scores_json"), {})
            if pid in by_pid and trait in scores:
                xs.append(float(scores[trait]))
                ys.append(sum(by_pid[pid]) / len(by_pid[pid]))
        stat = spearman_corr(xs, ys)
        result.append({"trait": trait, **stat})
    return result

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
class PostQuestionnaireIn(BaseModel): participant_id: str; answers: Dict[str, Any]
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
    set_step(data.participant_id, "instructions")
    return get_progress(data.participant_id)

@app.post("/api/instructions/{participant_id}")
def instructions_acknowledged(participant_id: str):
    set_step(participant_id, "pre")
    return get_progress(participant_id)

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
        # All conversations are finished. The next required step is the single post-experiment questionnaire.
        set_step(participant_id, "post", completed=0)
        return {"done": True, "all_done": True, "needs_post": True, "transcript": [], "turns": 0, "target_total_turns": TARGET_TOTAL_TURNS, "assignment_counts": counts}

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
        set_step(data.participant_id, "post", completed=0)
        return {"done": True, "all_done": True, "needs_post": True, "transcript": []}

    session_id = assignment["session_id"]
    save_turn(data.participant_id, "Human", text, session_id)
    transcript = load_transcript(data.participant_id, session_id)

    if len(transcript) >= TARGET_TOTAL_TURNS:
        mark_assignment_complete(session_id)
        compute_and_store_session_metrics(session_id)
        counts = count_assignments(data.participant_id)
        all_done = counts["remaining"] == 0
        if all_done:
            set_step(data.participant_id, "post", completed=0)
        return {"done": True, "all_done": all_done, "needs_post": all_done, "transcript": transcript, "assignment_counts": counts}

    reply = make_reply(data.participant_id, assignment, transcript)
    save_turn(data.participant_id, "Agent", reply, session_id)
    transcript = load_transcript(data.participant_id, session_id)

    conversation_done = len(transcript) >= TARGET_TOTAL_TURNS
    if conversation_done:
        mark_assignment_complete(session_id)
        compute_and_store_session_metrics(session_id)
    counts = count_assignments(data.participant_id)
    all_done = counts["remaining"] == 0
    if all_done and conversation_done:
        set_step(data.participant_id, "post", completed=0)

    return {"done": conversation_done, "all_done": all_done, "needs_post": all_done and conversation_done, "transcript": transcript, "assignment_counts": counts}


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
        compute_and_store_session_metrics(active["session_id"])

    counts = count_assignments(participant_id)

    if counts["remaining"] <= 0:
        set_step(participant_id, "post", completed=0)
    else:
        set_step(participant_id, "chat", completed=0)

    return get_progress(participant_id)


@app.post("/api/post")
def post_questionnaire(data: PostQuestionnaireIn):
    required = [
        "engagement", "naturalness", "responsiveness", "coherence",
        "topic_consistency", "willingness_continue", "overall_satisfaction",
    ]
    missing = [key for key in required if data.answers.get(key) in (None, "")]
    if missing:
        raise HTTPException(400, "Please complete all required post-experiment questions.")

    clean_answers = dict(data.answers)
    for key in required:
        try:
            value = int(clean_answers[key])
        except Exception:
            raise HTTPException(400, "Post-experiment ratings must be numbers from 1 to 5.")
        if value < 1 or value > 5:
            raise HTTPException(400, "Post-experiment ratings must be numbers from 1 to 5.")
        clean_answers[key] = value

    clean_answers["submitted_at"] = now()
    with connect() as conn:
        conn.execute(
            "UPDATE progress SET post_json=? WHERE participant_id=?",
            (jdump(clean_answers), data.participant_id),
        )
        conn.commit()

    set_step(data.participant_id, "done", completed=1)
    return get_progress(data.participant_id)

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



@app.get("/api/researcher/metrics", dependencies=[Depends(require_researcher)])
def researcher_metrics():
    init_db()

    metrics_error = None
    try:
        compute_all_completed_metrics()
    except Exception as e:
        metrics_error = str(e)

    with connect() as conn:
        rows = [dict(r) for r in conn.execute("""
            SELECT * FROM conversation_session_metrics
            ORDER BY updated_at DESC
        """).fetchall()]
        turn_rows = [dict(r) for r in conn.execute("""
            SELECT * FROM conversation_turn_metrics
            ORDER BY participant_id, session_id, turn_index ASC
        """).fetchall()]
        participant_rows = [dict(r) for r in conn.execute("SELECT participant_id, current_step, completed FROM participants").fetchall()]

    participant_count = len(participant_rows)
    completed_participants = sum(1 for p in participant_rows if p.get("completed"))
    expected_conversations = participant_count * max(1, len(rows) // max(1, participant_count)) if rows else participant_count

    summary = {
        "embedding_model": EMBEDDING_MODEL_NAME if get_embedding_model() else "hash-fallback-no-sentence-transformers",
        "metrics_error": metrics_error,
        "participants": participant_count,
        "completed_participants": completed_participants,
        "participant_completion_rate": round(completed_participants / max(1, participant_count), 4),
        "total_scored_conversations": len(rows),
        "avg_engagement_score": avg_float(rows, "engagement_score"),
        "avg_coherence": avg_float(rows, "coherence"),
        "avg_windowed_coherence": avg_float(rows, "windowed_coherence"),
        "avg_topic_consistency": avg_float(rows, "topic_consistency"),
        "avg_novelty": avg_float(rows, "novelty"),
        "avg_turn_balance": avg_float(rows, "turn_balance"),
        "avg_token_balance": avg_float(rows, "token_balance"),
        "avg_question_rate": avg_float(rows, "question_rate"),
    }

    statistics = compute_research_statistics(rows)
    statistics["big5_correlations"] = compute_big5_correlations(rows)

    return {
        "summary": summary,
        "sessions": rows,
        "turn_metrics": turn_rows,
        "statistics": statistics,
        "charts": {
            "engagement_by_model": group_average(rows, "model_size", "engagement_score"),
            "engagement_by_context": group_average(rows, "personality_context_enabled", "engagement_score"),
            "engagement_by_topic": group_average(rows, "topic_id", "engagement_score"),
            "coherence_by_model": group_average(rows, "model_size", "coherence"),
            "topic_consistency_by_topic": group_average(rows, "topic_id", "topic_consistency"),
            "question_rate_by_model": group_average(rows, "model_size", "question_rate"),
            "token_balance_by_model": group_average(rows, "model_size", "token_balance"),
            "conversations_by_topic": group_count(rows, "topic_id"),
            "engagement_histogram": statistics["distributions"]["engagement_histogram"],
        },
    }

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
        "participant_id", "access_code", "participant_created_at", "current_step", "completed", "post_json",
        "session_id", "conversation_order", "assignment_status", "topic_id", "variation_id",
        "topic_preference", "model_size", "model_name", "personality_context_enabled",
        "style_name", "speaker", "text", "timestamp",
        "word_count", "token_count", "is_question", "topic_similarity", "prev_similarity",
        "windowed_similarity", "novelty", "coherence", "windowed_coherence",
        "topic_consistency", "session_novelty", "turn_balance", "token_balance",
        "question_rate", "engagement_score"
    ])
    with connect() as conn:
        rows = conn.execute("""
            SELECT
                p.participant_id, ac.access_code, p.created_at AS participant_created_at, p.current_step, p.completed, pr.post_json,
                a.session_id, a.conversation_order, a.status AS assignment_status, a.topic_id, a.variation_id,
                a.topic_preference, a.model_size, a.model_name, a.personality_context_enabled, a.style_name,
                c.speaker, c.text, c.created_at AS turn_time, c.turn_index,
                tm.word_count, tm.token_count, tm.is_question, tm.topic_similarity,
                tm.prev_similarity, tm.windowed_similarity, tm.novelty AS turn_novelty,
                sm.coherence, sm.windowed_coherence, sm.topic_consistency, sm.novelty AS session_novelty,
                sm.turn_balance, sm.token_balance, sm.question_rate, sm.engagement_score
            FROM participants p
            LEFT JOIN participant_access_codes ac ON p.participant_id=ac.participant_id
            LEFT JOIN progress pr ON p.participant_id=pr.participant_id
            LEFT JOIN conversation_assignments a ON p.participant_id=a.participant_id
            LEFT JOIN conversation_turns c ON a.session_id=c.session_id
            LEFT JOIN conversation_turn_metrics tm ON c.turn_id=tm.turn_id
            LEFT JOIN conversation_session_metrics sm ON a.session_id=sm.session_id
            ORDER BY p.created_at DESC, a.conversation_order ASC, c.turn_index ASC
        """).fetchall()
    for r in rows:
        writer.writerow([
            r["participant_id"], r["access_code"] or "", r["participant_created_at"], r["current_step"], r["completed"], r["post_json"] or "{}",
            r["session_id"] or "", r["conversation_order"] or "", r["assignment_status"] or "", r["topic_id"] or "", r["variation_id"] or "",
            r["topic_preference"] or "", r["model_size"] or "", r["model_name"] or "", r["personality_context_enabled"] if r["personality_context_enabled"] is not None else "",
            r["style_name"] or "", r["speaker"] or "", r["text"] or "", r["turn_time"] or "",
            r["word_count"] if r["word_count"] is not None else "",
            r["token_count"] if r["token_count"] is not None else "",
            r["is_question"] if r["is_question"] is not None else "",
            r["topic_similarity"] if r["topic_similarity"] is not None else "",
            r["prev_similarity"] if r["prev_similarity"] is not None else "",
            r["windowed_similarity"] if r["windowed_similarity"] is not None else "",
            r["turn_novelty"] if r["turn_novelty"] is not None else "",
            r["coherence"] if r["coherence"] is not None else "",
            r["windowed_coherence"] if r["windowed_coherence"] is not None else "",
            r["topic_consistency"] if r["topic_consistency"] is not None else "",
            r["session_novelty"] if r["session_novelty"] is not None else "",
            r["turn_balance"] if r["turn_balance"] is not None else "",
            r["token_balance"] if r["token_balance"] is not None else "",
            r["question_rate"] if r["question_rate"] is not None else "",
            r["engagement_score"] if r["engagement_score"] is not None else "",
        ])
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=llm_engagement_export.csv"})
