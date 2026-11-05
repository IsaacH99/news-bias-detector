from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Import your core functions
from core import analyze_url, get_llm

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs on startup
    print("Starting server... Loading AI model (this may take a moment)...")
    get_llm()
    print("AI model loaded successfully!")
    
    yield # The server runs while yielded here
    
    # This runs on shutdown (optional)
    print("Shutting down server...")

# Initialize FastAPI with the lifespan
app = FastAPI(title="Claim & Bias Checker", lifespan=lifespan)

# Allow the Chrome extension to talk to the server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalyzeReq(BaseModel):
    url: str

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/analyze")
def analyze(req: AnalyzeReq):
    try:
        return analyze_url(req.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)