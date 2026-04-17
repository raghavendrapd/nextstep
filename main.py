from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, Response, Cookie, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List
import requests
import sqlite3
import json
import logging
import os
import re
import hashlib
import secrets
from datetime import datetime, timedelta
import csv
import io

app = FastAPI(title="NextStep AI - Sales Copilot", version="3.1.0")

# Session storage (in-memory for simplicity)
sessions = {}

def get_session(session_id: str):
    return sessions.get(session_id)

def create_session(user_id: int, username: str):
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {
        "user_id": user_id,
        "username": username,
        "created": datetime.now()
    }
    return session_id

def hash_password(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${hashed.hex()}", salt

def verify_password(password: str, stored: str):
    try:
        salt, _ = stored.split("$")
        new_hash, _ = hash_password(password, salt)
        return new_hash == stored
    except:
        return False

# -------------------- GROQ AI --------------------
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nextstep")

def log_activity(user_id: int, action: str, details: str = ""):
    """Log user activity"""
    try:
        db = get_db()
        db.execute("""
            INSERT INTO activity_logs (user_id, action, details, ip_address)
            VALUES (?, ?, ?, ?)
        """, (user_id, action, details, ""))
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Log error: {e}")

def get_client_ip(request) -> str:
    """Get client IP from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0]
    return request.client.host
def call_groq(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        },
        timeout=30
    )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Groq API error: {response.text}")

    return response.json()["choices"][0]["message"]["content"]


def transcribe_audio_groq(audio_file_path: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")

    # Get file size
    file_size = os.path.getsize(audio_file_path)
    print(f"Transcribing file: {audio_file_path}, size: {file_size} bytes")
    
    # Use longer timeout for larger files
    timeout = 60 if file_size < 10_000_000 else 120

    with open(audio_file_path, "rb") as f:
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": f},
            data={"model": "whisper-large-v3"},
            timeout=timeout
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Transcription error: {response.text}")

    return response.json().get("text", "")

# -------------------- CORS --------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- SERVE UI --------------------
@app.get("/")
def serve_ui():
    return FileResponse("templates/index.html")

@app.get("/login")
def serve_login():
    return FileResponse("templates/login.html")

@app.get("/test-screen")
def serve_test():
    return FileResponse("screentest.html")

# Health check endpoint for UptimeRobot
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "NextStep AI"}

# -------------------- ADMIN ANALYTICS --------------------
@app.get("/admin/analytics")
def get_analytics(session_id: str = Cookie(None)):
    """Get admin analytics - protected endpoint"""
    
    # Simple password protection
    admin_key = request.headers.get("X-Admin-Key")
    correct_key = os.environ.get("ADMIN_KEY", "nextstep2024")
    
    if admin_key != correct_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    db = get_db()
    
    # Total users
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    
    # Total calls analyzed
    total_calls = db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    
    # Guest users
    guest_users = db.execute("SELECT COUNT(*) FROM users WHERE username LIKE 'guest_%'").fetchone()[0]
    
    # Regular users
    regular_users = total_users - guest_users
    
    # Calls by deal stage
    deal_stages = db.execute("SELECT deal_stage, COUNT(*) FROM calls GROUP BY deal_stage").fetchall()
    
    # Lead scores
    lead_scores = db.execute("SELECT lead_score, COUNT(*) FROM calls GROUP BY lead_score").fetchall()
    
    # Recent activity (last 10)
    recent_calls = db.execute("""
        SELECT c.summary, c.deal_stage, c.lead_score, c.created_at, u.display_name
        FROM calls c
        JOIN users u ON c.user_id = u.id
        ORDER BY c.id DESC LIMIT 10
    """).fetchall()
    
    db.close()
    
    return {
        "total_users": total_users,
        "guest_users": guest_users,
        "regular_users": regular_users,
        "total_calls": total_calls,
        "deal_stages": [{"stage": d[0], "count": d[1]} for d in deal_stages],
        "lead_scores": [{"score": l[0], "count": l[1]} for l in lead_scores],
        "recent_calls": [
            {"summary": r[0][:100], "stage": r[1], "score": r[2], "date": r[3], "user": r[4]}
            for r in recent_calls
        ]
    }

# Guest login endpoint
@app.post("/guest-login")
def guest_login():
    """Create a guest session without registration"""
    import random
    import string
    
    # Create a random guest username
    guest_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    guest_username = f"guest_{guest_id}"
    
    # Check if guest user exists, if not create one
    db = get_db()
    user = db.execute("SELECT id, username, password, display_name FROM users WHERE username = ?", (guest_username,)).fetchone()
    
    if not user:
        # Create guest user
        hashed_pw, _ = hash_password("guest_" + guest_id)
        db.execute("INSERT INTO users (username, password, display_name) VALUES (?, ?, ?)",
                   (guest_username, hashed_pw, "Guest"))
        db.commit()
        user = db.execute("SELECT id, username, password, display_name FROM users WHERE username = ?", (guest_username,)).fetchone()
    
    db.close()
    
    # Create session
    session_id = create_session(user[0], user[1])
    response = JSONResponse({
        "success": True,
        "username": user[1],
        "display_name": user[3] or "Guest",
        "is_guest": True
    })
    response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=24*60*60)  # 24 hours for guest
    return response


# -------------------- DB SETUP --------------------
# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("nextstep")

def get_db():
    """Get database connection with better settings"""
    conn = sqlite3.connect("calls.db", timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Initialize tables with a fresh connection
init_conn = sqlite3.connect("calls.db")
init_conn.execute("""
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT,
    summary TEXT,
    deal_stage TEXT,
    next_steps TEXT,
    pain_points TEXT,
    action_items TEXT,
    lead_score TEXT,
    user_id INTEGER DEFAULT 1,
    created_at TEXT
)
""")
init_conn.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT
)
""")
init_conn.execute("""
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    details TEXT,
    ip_address TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")
init_conn.commit()

# Create default user if none exists
init_conn.execute("SELECT id FROM users LIMIT 1")
if init_conn.execute("SELECT id FROM users LIMIT 1").fetchone() is None:
    default_pw, _ = hash_password("demo123")
    init_conn.execute("INSERT INTO users (username, password, display_name) VALUES (?, ?, ?)",
                   ("demo", default_pw, "Demo User"))
    init_conn.commit()

# Add columns if missing
try:
    init_conn.execute("ALTER TABLE calls ADD COLUMN user_id INTEGER DEFAULT 1")
    init_conn.commit()
except:
    pass
try:
    init_conn.execute("ALTER TABLE calls ADD COLUMN created_at TEXT")
    init_conn.commit()
except:
    pass
init_conn.close()


# -------------------- MODELS --------------------
class TranscriptRequest(BaseModel):
    transcript: str
    call_id: Optional[str] = None


class AnalysisResponse(BaseModel):
    call_id: Optional[str]
    summary: str
    deal_stage: str
    pain_points: List[str]
    action_items: List[str]
    next_steps: str
    lead_score: str
    word_count: int
    status: str


class FollowUpRequest(BaseModel):
    transcript: str
    pain_points: List[str]
    deal_stage: str
    customer_type: Optional[str] = "startup"
    tone: Optional[str] = "friendly"
    company_context: Optional[str] = "AI tool that helps manage leads and automate follow-ups"


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    display_name: str


# -------------------- TRANSCRIBE --------------------
@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    try:
        audio_data = await file.read()
        logger.info(f"Received audio: {len(audio_data)} bytes, type: {file.content_type}")
        
        # Minimum 50KB required for meaningful audio
        if len(audio_data) < 50000:
            logger.warning(f"Audio too small: {len(audio_data)} bytes")
            return {"transcript": "", "error": "Audio too short. Please record longer."}
        
        temp_path = "temp_audio.webm"
        with open(temp_path, "wb") as f:
            f.write(audio_data)
        
        logger.info("Transcribing audio...")
        transcript = transcribe_audio_groq(temp_path)
        os.remove(temp_path)
        
        logger.info(f"Transcription complete: {len(transcript)} chars")
        return {"transcript": transcript}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return {"transcript": "", "error": "Transcription failed. Please try again."}
    except Exception as e:
        print(f"Transcribe error: {e}")
        if os.path.exists("temp_audio.webm"):
            os.remove("temp_audio.webm")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- ANALYZE --------------------
@app.post("/analyze", response_model=AnalysisResponse)
def analyze_transcript(request: TranscriptRequest, session_id: str = Cookie(None)):
    if not request.transcript or len(request.transcript.strip()) < 5:
        raise HTTPException(status_code=400, detail="Transcript too short")

    word_count = len(request.transcript.split())
    transcript = request.transcript[:1000]

    prompt = f"""Analyze this sales call. Return ONLY this exact JSON format with single words only:

{{"summary":"brief summary","deal_stage":"Interested","pain_points":["pain point"],"action_items":["action"],"next_steps":"next step","lead_score":"Hot"}}

Use ONLY these values:
- deal_stage: Interested, Evaluation, Negotiation, Closing, Not Interested
- lead_score: Hot, Warm, Cold

Transcript:
{transcript}"""

    llm_response = call_groq(prompt)
    
    cleaned = llm_response.strip()
    cleaned = cleaned.strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    
    try:
        parsed = json.loads(cleaned)
    except:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        try:
            parsed = json.loads(match.group()) if match else {}
        except:
            parsed = {}

    def to_string(val):
        if isinstance(val, list):
            return ", ".join(str(v) for v in val)
        return str(val) if val else ""

    def to_list(val):
        if isinstance(val, list):
            return [str(v) for v in val]
        if isinstance(val, str):
            return [v.strip() for v in val.split(",") if v.strip()]
        return []

    summary = to_string(parsed.get("summary", ""))
    deal_stage = to_string(parsed.get("deal_stage", ""))
    pain_points = to_list(parsed.get("pain_points", []))
    action_items = to_list(parsed.get("action_items", []))
    next_steps = to_string(parsed.get("next_steps", ""))
    lead_score = to_string(parsed.get("lead_score", "Warm"))

    user_id = 1
    if session_id and session_id in sessions:
        user_id = sessions[session_id]["user_id"]

    try:
        db = get_db()
        db.execute("""
        INSERT INTO calls (call_id, summary, deal_stage, next_steps, pain_points, action_items, lead_score, user_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.call_id,
            summary,
            deal_stage,
            next_steps,
            json.dumps(pain_points),
            json.dumps(action_items),
            lead_score,
            user_id,
            datetime.now().isoformat()
        ))
        db.commit()
        db.close()
    except Exception as e:
        print(f"DB Error: {e}")
        raise

    return AnalysisResponse(
        call_id=request.call_id,
        summary=summary,
        deal_stage=deal_stage,
        pain_points=pain_points,
        action_items=action_items,
        next_steps=next_steps,
        lead_score=lead_score,
        word_count=word_count,
        status="success"
    )


# -------------------- FOLLOW-UP --------------------
@app.post("/generate-followup")
def generate_followup(req: FollowUpRequest):
    prompt = f"Write a short 4-5 line follow-up message. Stage: {req.deal_stage}. Pain: {', '.join(req.pain_points)}"
    try:
        response = call_groq(prompt)
        return {"followup_message": response.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- AUTH --------------------
@app.post("/register")
def register(req: RegisterRequest):
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE username = ?", (req.username,)).fetchone()
    if user:
        db.close()
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed_pw, _ = hash_password(req.password)
    display_name = req.display_name or req.username

    db.execute("INSERT INTO users (username, password, display_name) VALUES (?, ?, ?)",
                   (req.username, hashed_pw, display_name))
    db.commit()

    user = db.execute("SELECT id FROM users WHERE username = ?", (req.username,)).fetchone()
    db.close()

    session_id = create_session(user[0], req.username)
    response = JSONResponse({"success": True, "username": req.username, "display_name": display_name})
    response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=7*24*60*60)
    return response


@app.post("/login")
def login(req: LoginRequest):
    db = get_db()
    user = db.execute("SELECT id, username, password, display_name FROM users WHERE username = ?", (req.username,)).fetchone()
    db.close()

    if not user or not verify_password(req.password, user[2]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id = create_session(user[0], user[1])
    response = JSONResponse({
        "success": True,
        "username": user[1],
        "display_name": user[3] or user[1]
    })
    response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=7*24*60*60)
    return response


@app.post("/logout")
def logout(session_id: str = Cookie(None)):
    if session_id:
        sessions.pop(session_id, None)
    response = JSONResponse({"success": True})
    response.delete_cookie("session_id")
    return response


@app.get("/me")
def get_current_user(session_id: str = Cookie(None)):
    if not session_id or session_id not in sessions:
        return {"authenticated": False}
    session = sessions[session_id]
    db = get_db()
    user = db.execute("SELECT username, display_name FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    db.close()
    if user:
        return {
            "authenticated": True,
            "username": user[0],
            "display_name": user[1] or user[0],
            "user_id": session["user_id"]
        }
    return {"authenticated": False}


@app.put("/profile")
def update_profile(req: UpdateProfileRequest, session_id: str = Cookie(None)):
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = sessions[session_id]
    db = get_db()
    db.execute("UPDATE users SET display_name = ? WHERE id = ?", (req.display_name, session["user_id"]))
    db.commit()
    db.close()
    return {"success": True}


# -------------------- HISTORY --------------------
@app.get("/history")
def get_history(session_id: str = Cookie(None)):
    user_id = 1
    if session_id and session_id in sessions:
        user_id = sessions[session_id]["user_id"]

    db = get_db()
    rows = db.execute("SELECT * FROM calls WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    db.close()

    result = []

    for row in rows:
        item = {
            "id": row[0],
            "call_id": row[1],
            "summary": row[2],
            "deal_stage": row[3],
            "next_steps": row[4],
            "pain_points": json.loads(row[5] or "[]"),
            "action_items": json.loads(row[6] or "[]"),
            "lead_score": row[7] if len(row) > 7 else "Unknown",
            "created_at": row[8] if len(row) > 8 else None
        }
        result.append(item)

    return result


# -------------------- EXPORT --------------------
@app.get("/export/csv")
def export_csv(session_id: str = Cookie(None)):
    user_id = 1
    if session_id and session_id in sessions:
        user_id = sessions[session_id]["user_id"]

    db = get_db()
    rows = db.execute("SELECT * FROM calls WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    db.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Call ID", "Summary", "Deal Stage", "Next Steps", "Pain Points", "Action Items", "Lead Score", "Created At"])

    for row in rows:
        writer.writerow([
            row[0], row[1], row[2], row[3], row[4],
            "; ".join(json.loads(row[5] or "[]")),
            "; ".join(json.loads(row[6] or "[]")),
            row[7] if len(row) > 7 else "Unknown",
            row[8] if len(row) > 8 else None
        ])

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nextstep_calls.csv"}
    )


@app.get("/export/json")
def export_json(session_id: str = Cookie(None)):
    user_id = 1
    if session_id and session_id in sessions:
        user_id = sessions[session_id]["user_id"]

    db = get_db()
    rows = db.execute("SELECT * FROM calls WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    db.close()

    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "call_id": row[1],
            "summary": row[2],
            "deal_stage": row[3],
            "next_steps": row[4],
            "pain_points": json.loads(row[5] or "[]"),
            "action_items": json.loads(row[6] or "[]"),
            "lead_score": row[7] if len(row) > 7 else "Unknown",
            "created_at": row[8] if len(row) > 8 else None
        })

    return Response(
        content=json.dumps(result, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=nextstep_calls.json"}
    )


@app.get("/export/pdf")
def export_pdf(session_id: str = Cookie(None)):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import inch
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF export not available. Install reportlab: pip install reportlab")

    user_id = 1
    if session_id and session_id in sessions:
        user_id = sessions[session_id]["user_id"]

    db = get_db()
    rows = db.execute("SELECT * FROM calls WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    db.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    elements = []

    title = Paragraph("<b>NextStep AI - Call Analysis Report</b>", styles["Title"])
    elements.append(title)
    elements.append(Spacer(1, 0.25*inch))

    if rows:
        data = [["ID", "Summary", "Deal Stage", "Lead Score", "Next Steps"]]
        for row in rows[:50]:
            summary = (row[2][:50] + "...") if row[2] and len(row[2]) > 50 else row[2]
            next_steps = (row[4][:40] + "...") if row[4] and len(row[4]) > 40 else row[4]
            data.append([
                str(row[0]),
                summary or "",
                row[3] or "",
                row[7] if len(row) > 7 else "Unknown",
                next_steps or ""
            ])

        table = Table(data, colWidths=[0.5*inch, 2*inch, 1*inch, 0.9*inch, 2.5*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#50eede")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#1a1a1a"), colors.HexColor("#2a2a2a")]),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.white),
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("No call analyses found.", styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=nextstep_calls.pdf"}
    )


# -------------------- RUN --------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)