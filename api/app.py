from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

@app.post("/api/webhook")
async def webhook():
    return {"ok": True}
