import os, sys
sys.path.insert(0,'backend')
os.environ.setdefault('PYTHONPATH','backend')
import os
import uvicorn
from app.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("BACKEND_PORT", "8000")))
    uvicorn.run(app, host="127.0.0.1", port=port)
