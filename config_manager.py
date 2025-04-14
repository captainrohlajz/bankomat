# config_manager.py
import json
import os
import logging
import pandas as pd
from collections import OrderedDict # Potřebujeme pro mapu podmínek

logger = logging.getLogger(__name__)

CONFIGS_DIR = 'configs'

# --- KONSTANTY PRO PRAVIDLA (Přesunuto sem z gui.py) ---
# UVNITŘ config_manager.py

# --- Konstanty pro Pravidla a Zobrazení ---
# Používáme OrderedDict pro zachování pořadí v GUI
TRANSACTION_RULE_CONDITIONS_MAP = OrderedDict([
    # Původní textové podmínky
    ("Obsahuje", "contains"),
    ("Neobsahuje", "necontains"),
    ("Začíná na", "startswith"),
    ("Končí na", "endswith"),
    ("Nekončí na", "neendswith"),
    ("Přesná hodnota", "exact"),
    # Nové strukturní/typové podmínky
    ("Není prázdné", "notempty"), # <<< NOVÉ
    ("Je prázdné", "isempty"),   # <<< NOVÉ
    ("Je číslo", "isnumber"),     # <<< NOVÉ
    ("Je kladné číslo", "ispositive"), # <<< NOVÉ
    ("Je záporné číslo", "isnegative") # <<< NOVÉ
])
# Odvozené seznamy pro interní použití a GUI
TRANSACTION_RULE_CONDITIONS_KEYS = list(TRANSACTION_RULE_CONDITIONS_MAP.values())
TRANSACTION_RULE_DISPLAY_NAMES = list(TRANSACTION_RULE_CONDITIONS_MAP.keys())

# Nová sada klíčů pro podmínky, které NEVYŽADUJÍ klíčová slova
CONDITIONS_WITHOUT_KEYWORDS = {"notempty", "isempty", "isnumber", "ispositive", "isnegative"} # <<< NOVÉ

# Sloupce, kde se defaultně hledají klíčová slova (pokud není specifikováno v pravidle)
SEARCHABLE_COLUMNS = ["POPIS", "POPIS 2", "PROTIUCET_NAZEV", "POZNÁMKA", "PROTIUCET_CISLO", "PROTIUCET"] # Přidán PROTIUCET

# Výchozí seznam typů transakcí pro nabídku v GUI
DEFAULT_TRANSACTION_TYPES = ["Banka", "Výběr", "Vklad", "Platba kartou", "Odchozí", "Příchozí", "Vratka", "Inkaso", "Poplatek"]
# ---------------------------------------------------------

def load_config(config_path):
    """Načtení konfigurace ze souboru JSON."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.info(f"Konfigurace úspěšně načtena z: {config_path}")

            # Základní validace (už nevalidujeme metadata zde)
            if "column_mapping" not in config or "transaction_types" not in config:
                raise ValueError("Konfigurace neobsahuje povinné sekce 'column_mapping' nebo 'transaction_types'")
            if "identification" not in config or not config.get("identification"):
                 logger.warning(f"Konfig {config_path} nemá sekci 'identification'.")
            elif not config.get("identification", {}).get("all_expected_columns") and not config.get("identification", {}).get("required_columns"):
                 logger.warning(f"V 'identification' v {config_path} chybí 'all_expected_columns' nebo 'required_columns'.")

            return config
    except FileNotFoundError:
        logger.error(f"Konfigurační soubor nebyl nalezen: {config_path}"); raise
    except json.JSONDecodeError as e:
        logger.error(f"Chyba parsování JSON v {config_path}: {e}"); raise ValueError(f"Neplatný JSON: {e}")
    except Exception as e:
        logger.error(f"Neočekávaná chyba načítání configu {config_path}: {e}"); raise ValueError(f"Chyba načítání configu: {e}")

def save_config(config_data, config_path):
    """Uložení konfigurace do souboru JSON."""
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        # Ukládáme data tak, jak přišla (bez metadat)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        logger.info(f"Konfigurace úspěšně uložena do: {config_path}")
    except Exception as e:
        logger.error(f"Chyba při ukládání konfigurace do {config_path}: {e}"); raise

def get_all_config_files(configs_dir=CONFIGS_DIR):
    """Vrátí seznam cest ke všem .json souborům v adresáři konfigurací."""
    if not os.path.isdir(configs_dir):
        logger.warning(f"Adresář konfigurací '{configs_dir}' neexistuje."); return []
    return [os.path.join(configs_dir, f) for f in os.listdir(configs_dir) if f.endswith('.json') and not f.startswith('~')]

# Funkce identify_config_for_file zůstává stejná jako v předchozí verzi
def identify_config_for_file(file_path, configs_dir=CONFIGS_DIR):
    logger.info(f"Identifikuji konfiguraci pro soubor: {os.path.basename(file_path)}")
    config_files = get_all_config_files(configs_dir)
    if not config_files: logger.error("Nebyly nalezeny žádné konfigurační soubory."); return None

    potential_configs = []
    header_df = None; input_columns = set()

    try:
        file_extension = os.path.splitext(file_path)[1].lower()
        if file_extension == '.csv':
            encodings_to_try = ['cp1250', 'utf-8', 'latin1']
            for enc in encodings_to_try:
                try:
                    header_df = pd.read_csv(file_path, encoding=enc, sep=';', nrows=5, skipinitialspace=True)
                    df_cols_only = pd.read_csv(file_path, encoding=enc, sep=';', nrows=0, skipinitialspace=True)
                    logger.debug(f"CSV hlavička načtena s kódováním: {enc}"); break
                except UnicodeDecodeError: continue
                except Exception as read_err: logger.warning(f"Chyba čtení CSV ({enc}): {read_err}"); break
            if header_df is None: raise ValueError("Nepodařilo se načíst CSV hlavičku.")
        elif file_extension in ['.xlsx', '.xls']:
            header_df = pd.read_excel(file_path, nrows=5)
            df_cols_only = pd.read_excel(file_path, nrows=0)
        else: logger.warning(f"Nepodporovaný formát souboru: {file_path}"); return None

        input_columns = set(str(col).strip() for col in df_cols_only.columns)
        logger.debug(f"Nalezené sloupce ({len(input_columns)}): {input_columns}")
    except Exception as e:
        logger.error(f"Chyba při čtení hlavičky {file_path}: {e}"); return None

    for config_path in config_files:
        try:
            config = load_config(config_path)
            ident_rules = config.get("identification")
            if not ident_rules: logger.debug(f"Konfig {os.path.basename(config_path)} nemá 'identification'."); continue

            score = 0; match_details = []; passes = True

            all_expected_cols = ident_rules.get("all_expected_columns")
            if all_expected_cols:
                all_expected_set = set(all_expected_cols)
                if input_columns == all_expected_set:
                    score += 50; match_details.append(f"Přesná shoda všech {len(all_expected_cols)} očekávaných sloupců.")
                else:
                    missing = all_expected_set - input_columns; extra = input_columns - all_expected_set
                    logger.debug(f"Konfig '{os.path.basename(config_path)}': Neshoda 'all_expected_columns'. Chybí: {missing or 'žádné'}, Navíc: {extra or 'žádné'}.")
                    passes = False
            else:
                required_cols = ident_rules.get("required_columns", [])
                if required_cols:
                    missing_req = set(required_cols) - input_columns
                    if not missing_req: score += 15; match_details.append(f"Všechny povinné sloupce ({len(required_cols)}) nalezeny.")
                    else: logger.debug(f"Konfig '{os.path.basename(config_path)}': Chybí povinné sloupce: {missing_req}."); passes = False

            if passes:
                # header_contains = ident_rules.get("header_contains", [])
                # if header_contains and header_df is not None:
                #     header_text = header_df.to_string(index=False).lower()
                #     found_all_header = True; missing_texts = []
                #     for text in header_contains:
                #         if text.lower() not in header_text: found_all_header = False; missing_texts.append(text)
                #     if found_all_header: score += 5; match_details.append(f"Texty v hlavičce ({len(header_contains)}) OK.")
                #     else: logger.debug(f"Konfig '{os.path.basename(config_path)}': Chybí texty v hlavičce: {missing_texts}."); passes = False

                if passes and score > 0:
                    logger.info(f"Kandidát: '{os.path.basename(config_path)}', Skóre: {score}, Detaily: {' '.join(match_details)}")
                potential_configs.append({"path": config_path, "score": score})

        except Exception as e: logger.warning(f"Chyba zpracování konfigu {config_path} při identifikaci: {e}")

    if not potential_configs: logger.error(f"Pro {os.path.basename(file_path)} nenalezena vyhovující konfigurace."); return None
    potential_configs.sort(key=lambda x: x["score"], reverse=True); best_match = potential_configs[0]
    MIN_SCORE_THRESHOLD = 20
    if best_match["score"] >= MIN_SCORE_THRESHOLD:
         top_score = best_match["score"]; top_matches = [c for c in potential_configs if c["score"] == top_score]
         if len(top_matches) > 1: logger.warning(f"Nalezeno více konfigurací se skóre {top_score}: {[os.path.basename(c['path']) for c in top_matches]}. Nejednoznačné."); return None
         logger.info(f"Identifikována nejlepší konfigurace: {os.path.basename(best_match['path'])} (Skóre: {best_match['score']})")
         return best_match['path']
    else: logger.error(f"Pro {os.path.basename(file_path)} nenalezena konfigurace s dostatečným skóre (Nejlepší: {os.path.basename(best_match['path'])} skóre {best_match['score']}, práh: {MIN_SCORE_THRESHOLD})."); return None