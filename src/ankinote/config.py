import os

from dotenv import load_dotenv

load_dotenv()


class EnvVars:
    GOOGLE_TTS_KEY: str = os.getenv("GOOGLE_TTS_KEY", "")
    ANKI_CONNECT_URL: str = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
    # Which Anki backend the client factory builds: ``connect`` (AnkiConnect)
    # or ``collection`` (in-process Anki collection). Blank means nobody chose
    # yet and acts as ``connect``; it stays blank so saving settings.json
    # doesn't record a choice the user never made.
    ANKI_BACKEND: str = os.getenv("ANKI_BACKEND", "")
    # Filesystem path to the Anki collection directory; required when
    # ``ANKI_BACKEND=collection``.
    ANKI_COLLECTION_PATH: str = os.getenv("ANKI_COLLECTION_PATH", "")

    ANKIWEB_USERNAME: str = os.getenv("ANKIWEB_USERNAME", "")
    ANKIWEB_PASSWORD: str = os.getenv("ANKIWEB_PASSWORD", "")


envs = EnvVars()
