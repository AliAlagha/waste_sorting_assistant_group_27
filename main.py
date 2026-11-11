import logging
import os

from dotenv import load_dotenv

# settings such as OPENAI_API_KEY are read from the file .env (never committed)
load_dotenv()

from webapp.app import create_app  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = create_app()

if __name__ == "__main__":
    # port 5000 is used by AirPlay on macOS, so 5050 is the local default
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5050)), debug=False)
