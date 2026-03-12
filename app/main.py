# main.py
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.transcript import get_transcript
import os
from app.auth import is_token_valid, has_quota, update_quota  # 👈 Nouveau
import requests
WEBHOOK_URL = os.environ["N8N_WEBHOOK_URL"]

# Vérifier que les variables d'environnement obligatoires sont présentes
REQUIRED_ENV_VARS = ["PROXY_USERNAME", "PROXY_PASSWORD", "PROXY_HOST", "PROXY_PORT"]
for var in REQUIRED_ENV_VARS:
    if var not in os.environ:
        raise RuntimeError(f"Variable d'environnement manquante: {var}")

app = FastAPI(title="YouTube Transcript API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TranscriptRequest(BaseModel):
    video_id: str

class TranscriptAuthRequest(BaseModel): 
    video_id: str

def notify_n8n(video_id: str, transcript: str, token: str):
    try:
        requests.post(f"https://n8n.alanbouo.com/webhook/transcript-event/{WEBHOOK_URL}", json={
            "video_id": video_id,
            "transcript": transcript,
            "token": token
        }, timeout=3)
    except Exception as e:
        print(f"Webhook error: {e}")



@app.post("/transcript")
def transcript(req: TranscriptRequest):
    print(">> Request received:", req)
    proxies = {
        "http": f"http://{os.environ['PROXY_USERNAME']}:{os.environ['PROXY_PASSWORD']}@{os.environ['PROXY_HOST']}:{os.environ['PROXY_PORT']}",
        "https": f"http://{os.environ['PROXY_USERNAME']}:{os.environ['PROXY_PASSWORD']}@{os.environ['PROXY_HOST']}:{os.environ['PROXY_PORT']}"
    }
    try:
        text = get_transcript(req.video_id, proxies=proxies)
        notify_n8n(video_id=req.video_id, transcript=text, token="no-token")
        return {"video_id": req.video_id, "transcript": text}
    except Exception as e:
        print("❌ Transcript error:", str(e))
        raise HTTPException(status_code=400, detail="Erreur lors de la récupération du transcript.")


@app.post("/transcript/auth")
def transcript_with_auth(req: TranscriptAuthRequest, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token.")

    token = authorization.replace("Bearer ", "").strip()

    if not is_token_valid(token):
        raise HTTPException(status_code=401, detail="Invalid token.")

    if not has_quota(token):
        raise HTTPException(status_code=429, detail="Quota exceeded (1/day).")

    try:
        proxies = {
            "http": f"http://{os.environ['PROXY_USERNAME']}:{os.environ['PROXY_PASSWORD']}@{os.environ['PROXY_HOST']}:{os.environ['PROXY_PORT']}",
            "https": f"http://{os.environ['PROXY_USERNAME']}:{os.environ['PROXY_PASSWORD']}@{os.environ['PROXY_HOST']}:{os.environ['PROXY_PORT']}"
        }
        text = get_transcript(req.video_id, proxies=proxies)
        update_quota(token)
        notify_n8n(video_id=req.video_id, transcript=text, token=token)
        return {"video_id": req.video_id, "transcript": text}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
