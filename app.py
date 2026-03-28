"""Entry point — run with: python app.py"""

import uvicorn

from services.analysis.main import app  # noqa: F401

if __name__ == "__main__":
    uvicorn.run(
        "services.analysis.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
