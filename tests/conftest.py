"""Test-suite isolation.

These are offline unit tests. Force the in-process Band stub so a populated
``.env`` (with ``BAND_BACKEND=live`` + real agent creds) can never make tests hit
the live Band API / network. Set before ``app.config`` runs ``load_dotenv()``
(which uses ``override=False``, so a value set here wins).
"""
import os

os.environ["BAND_BACKEND"] = "stub"
