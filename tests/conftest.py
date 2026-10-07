"""Garde-fou global : AUCUN test ne peut envoyer une vraie touche ou un vrai clic (verrou bas niveau dans io_win)."""
import os

os.environ["QTE_BOT_DRY_RUN"] = "1"
