# utils.py (Verze s konfigurací root loggeru a vlastními výjimkami)
import logging
import re
import os
import pandas as pd # Přidáno pro pd.notna
import chardet # Přidáno pro detekci kódování

# --- Nastavení logování ---
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, "app.log")

# Získáme root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# Formátovač
formatter = logging.Formatter(
    fmt="[%(asctime)s] %(levelname)-8s %(name)-20s: %(message)s", # Upravená šířka názvu
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Přidáme handlery pouze pokud root logger ještě žádné nemá
if not root_logger.hasHandlers():
    # Handler pro soubor
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8", mode='a')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Handler pro konzoli
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    root_logger.info("--- Logging byl inicializován (root logger) ---")
else:
    logging.getLogger(__name__).debug("Modul utils znovu importován, logování již inicializováno.")


# --- Pomocné funkce ---

def extract_account_number(text):
    """
    Extrahování čísla účtu (včetně předčíslí a kódu banky) nebo IBANu z textového řetězce.
    Vrací normalizovaný formát nebo None.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    text = text.strip()
    log = logging.getLogger(__name__)

    iban_cleaned = re.sub(r'\s+', '', text)
    iban_match = re.match(r'^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$', iban_cleaned, re.IGNORECASE)
    if iban_match:
        iban_found = iban_match.group(0).upper()
        log.debug(f"Identifikován IBAN: {iban_found} z textu: '{text}'")
        return iban_found

    account_match = re.search(r'([\d-]{2,17})\s*/\s*(\d{4})', text)
    if account_match:
        account_part = account_match.group(1)
        bank_code = account_match.group(2)
        full_account = f"{account_part}/{bank_code}"
        log.debug(f"Nalezeno standardní číslo účtu: {full_account} v textu: '{text}'")
        return full_account

    log.debug(f"Nebylo nalezeno žádné rozpoznatelné číslo účtu (CZ/IBAN) v textu: '{text}'")
    return None

def is_iban(account_number):
    """Zjednodušená kontrola, zda řetězec vypadá jako IBAN (po očištění)."""
    if not isinstance(account_number, str): return False
    cleaned = re.sub(r'\s+', '', account_number)
    # Přesnější regex pro IBAN (začíná 2 písmeny, pak 2 čísla, pak alfanum)
    return re.match(r'^[A-Z]{2}\d{2}[A-Z0-9]{10,}$', cleaned, re.IGNORECASE) is not None

# --- Vlastní třídy výjimek ---

class ProcessingError(Exception):
    """Obecná chyba během zpracování dat."""
    pass

class ConfigError(ProcessingError):
    """Chyba související s konfigurací (mapování, pravidla)."""
    pass

class DataError(ProcessingError):
    """Chyba související s neplatným formátem nebo chybějícími vstupními daty."""
    pass

# --- Konec souboru utils.py ---