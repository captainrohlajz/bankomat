# data_processor.py

import logging # <<< Standardní import
import pandas as pd
import re
import json
import numpy as np

# Importujeme potřebné funkce z utils
from utils import ConfigError, DataError, ProcessingError, extract_account_number, is_iban # <<< Importujeme konkrétní funkce

# Importujeme konstanty z config_manager (s fallbackem)
# UVNITŘ data_processor.py (na začátku, u ostatních importů)

# ... (ostatní importy) ...
# Importujeme nové konstanty z config_manager
try:
    import config_manager
    TRANSACTION_RULE_CONDITIONS_KEYS = config_manager.TRANSACTION_RULE_CONDITIONS_KEYS
    DEFAULT_RULE_SEARCH_COLUMNS = config_manager.SEARCHABLE_COLUMNS
    CONDITIONS_WITHOUT_KEYWORDS = config_manager.CONDITIONS_WITHOUT_KEYWORDS # <<< NOVÝ IMPORT
except ImportError:
    # ... (stávající fallback) ...
    CONDITIONS_WITHOUT_KEYWORDS = {"notempty", "isempty", "isnumber", "ispositive", "isnegative"} # Fallback

# ... (definice loggeru a dalších konstant) ...
# Definice loggeru pro tento modul
logger = logging.getLogger(__name__) # <<< Standardní způsob

# Konstanty specifické pro data_processor (zůstávají stejné)
FINAL_COLUMN_ORDER = [
    'UCET_CISLO', 'UCET_NAZEV', 'DISPONENT1', 'DISPONENT2', 'DISPONENT3', 'MENA', 'DATUM', 'CASTKA', 'POPLATKY',
    'KREDIT', 'DEBET', 'TYP TRANSAKCE', 'PREDCISLI', 'PROTIUCET_CISLO', 'PROTIUCET', 'KOD_BANKY_PROTIÚČET',
    'PROTIUCET_NAZEV', 'PROTIUCET+NAZEV', 'VS', 'KS', 'SS', 'POPIS', 'POPIS 2', 'POZNÁMKA', 'KURZ', 'ZDROJ'
]
NUMERIC_FINAL_COLS = {'CASTKA', 'POPLATKY', 'KREDIT', 'DEBET', 'KURZ'}
STRING_NUMERIC_COLS = {'PREDCISLI', 'PROTIUCET_CISLO', 'KOD_BANKY_PROTIÚČET', 'VS', 'KS', 'SS'}
UNKNOWN_TRANSACTION_TYPE = "Neznámý"

# --- Pomocné funkce ---
# UVNITŘ data_processor.py

# UVNITŘ data_processor.py

def _apply_single_rule(text_to_search, rules):
    """
    Aplikuje JEDNO pravidlo (podmínku) na daný text.
    Vrací True/False. Podporuje nové podmínky bez klíčových slov.
    Vyvolá ConfigError při neznámé podmínce.
    """
    if not isinstance(rules, dict) or len(rules) != 1:
         logger.warning(f"_apply_single_rule: Neplatný vstup 'rules': {rules}")
         return False
    if text_to_search is None: text_to_search = ""
    else: text_to_search = str(text_to_search).strip() # Pracujeme s očištěným stringem

    text_lower = text_to_search.lower()
    condition = list(rules.keys())[0]
    keywords_input = rules.get(condition) # Může být None

    if condition not in TRANSACTION_RULE_CONDITIONS_KEYS:
        raise ConfigError(f"Neznámá podmínka pravidla: '{condition}'.")

    # --- Logika pro podmínky bez klíčových slov ---
    if condition in CONDITIONS_WITHOUT_KEYWORDS:
        if condition == "notempty":
             return bool(text_to_search) # Vrátí True, pokud string není prázdný
        elif condition == "isempty":
             return not bool(text_to_search) # Vrátí True, pokud je string prázdný
        elif condition in ["isnumber", "ispositive", "isnegative"]:
             # Pokusíme se převést na číslo
             try:
                 # Nahradíme čárku tečkou pro bezpečnější převod
                 num_val = float(str(text_to_search).replace(',', '.'))
                 # Vyhodnotíme podmínku
                 if condition == "isnumber": return True # Úspěšně převedeno na číslo
                 elif condition == "ispositive": return num_val > 0
                 elif condition == "isnegative": return num_val < 0
             except (ValueError, TypeError):
                 # Pokud převod selže, není to číslo
                 return False
        # Pokud by se sem dostala jiná podmínka z CONDITIONS_WITHOUT_KEYWORDS (nemělo by)
        logger.warning(f"Neočekávaná podmínka bez klíč. slov: {condition}")
        return False # Pro jistotu

    # --- Logika pro podmínky S klíčovými slovy ---
    else:
        # Zpracování klíčových slov (stejné jako dříve)
        if keywords_input is None: keywords_list = []
        elif isinstance(keywords_input, list): keywords_list = [str(kw).strip() for kw in keywords_input if kw is not None]
        elif isinstance(keywords_input, (str, int, float)): keywords_list = [str(keywords_input).strip()]
        else: logger.warning(f"Neplatný formát klíč. slov pro '{condition}': {keywords_input}. Ignoruji."); keywords_list = []
        keywords_lower = [kw.lower() for kw in keywords_list if kw]

        # Pokud nejsou klíčová slova (a nejsou to 'ne' podmínky), výsledek je False
        if not keywords_lower and condition not in ["necontains", "neendswith"]: return False
        # Pokud je text prázdný (a nejsou to 'ne' podmínky), výsledek je False
        if not text_lower and condition not in ["necontains", "neendswith"]: return False

        # Aplikace textových podmínek (stejné jako dříve)
        try:
            if condition == "contains": return any(kw in text_lower for kw in keywords_lower)
            elif condition == "necontains": return not any(kw in text_lower for kw in keywords_lower)
            elif condition == "startswith": return any(text_lower.startswith(kw) for kw in keywords_lower)
            elif condition == "endswith": return any(text_lower.endswith(kw) for kw in keywords_lower)
            elif condition == "neendswith": return not any(text_lower.endswith(kw) for kw in keywords_lower)
            elif condition == "exact": return any(text_lower == kw for kw in keywords_lower)
            else: logger.warning(f"Neošetřená textová podmínka: {condition}"); return False
        except Exception as e: logger.error(f"Chyba aplikace text. podmínky '{condition}': {e}"); return False

# KONEC METODY _apply_single_rule# UVNITŘ data_processor.py

def apply_ignore_rules(df, ignore_rules_list):
    """
    Odfiltruje řádky z DataFrame, které odpovídají zadaným pravidlům pro ignorování.
    Vyvolává ConfigError při neplatném pravidle.
    """
    if not ignore_rules_list: logger.info("Žádná pravidla pro ignorování."); return df

    logger.info(f"Aplikuji {len(ignore_rules_list)} pravidel pro ignorování řádků...")
    initial_rows = len(df)
    mask_to_keep = pd.Series(True, index=df.index)

    for i, rule_dict in enumerate(ignore_rules_list):
        rule_desc = f"Ignore pravidlo #{i+1}"
        logger.debug(f"Zpracovávám {rule_desc}: {rule_dict}")

        # --- Validace struktury pravidla ---
        if not isinstance(rule_dict, dict):
             raise ConfigError(f"{rule_desc}: Položka není slovník (objekt JSON). Pravidlo: {rule_dict}")
        conditions_dict = rule_dict.get("conditions")
        search_cols = rule_dict.get("search_in")
        if not isinstance(conditions_dict, dict) or not conditions_dict:
            raise ConfigError(f"{rule_desc}: Chybí nebo je neplatná povinná sekce 'conditions' (musí být neprázdný objekt JSON). Pravidlo: {rule_dict}")
        if not isinstance(search_cols, list) or not search_cols:
            raise ConfigError(f"{rule_desc}: Chybí nebo je neplatná povinná sekce 'search_in' (musí být neprázdné pole JSON). Pravidlo: {rule_dict}")
        # --- Konec validace ---

        try: # Obalíme zpracování pravidla pro odchyt chyb z _apply_single_rule
            rule_match_mask = pd.Series(True, index=df.index)

            for condition_key, keywords in conditions_dict.items():
                # _apply_single_rule nyní vyvolá ConfigError při neznámé podmínce
                single_rule = {condition_key: keywords}
                condition_met_mask = pd.Series(False, index=df.index)

                for col_name in search_cols:
                     if col_name in df.columns:
                         col_not_na = df[col_name].notna()
                         if col_not_na.any():
                             # Volání _apply_single_rule může vyvolat ConfigError
                             matches = df.loc[col_not_na, col_name].apply(_apply_single_rule, rules=single_rule)
                             condition_met_mask.loc[matches[matches].index] = True
                     else: logger.warning(f"{rule_desc}: Sloupec '{col_name}' pro hledání neexistuje.")

                rule_match_mask &= condition_met_mask
                if not rule_match_mask.any(): break # Optimalizace

            if rule_match_mask.any():
                mask_to_keep[rule_match_mask] = False
                logger.debug(f"{rule_desc}: Nalezeno {rule_match_mask.sum()} řádků k ignorování.")

        except ConfigError as ce:
             # Přidáme informaci o kterém pravidle jde
             raise ConfigError(f"{rule_desc}: {ce}") from ce
        except Exception as e:
             # Neočekávaná chyba během aplikace pravidla
             logger.error(f"Neočekávaná chyba při aplikaci {rule_desc}: {e}", exc_info=True)
             raise ProcessingError(f"Neočekávaná chyba při aplikaci {rule_desc}: {e}") from e


    df_filtered = df[mask_to_keep]; dropped_count = initial_rows - len(df_filtered)
    if dropped_count > 0: logger.info(f"Ignorováno celkem {dropped_count} řádků.");
    else: logger.info("Žádné řádky neodpovídaly ignore pravidlům.");
    return df_filtered

# KONEC METODY apply_ignore_rules
# --- Základní zpracování ---
def map_columns(df, column_mapping):
    # (Beze změny - z předchozí verze)
    logger.info("Mapování sloupců."); result_df = pd.DataFrame(index=df.index); present=[]; missing=[]
    if not isinstance(column_mapping, dict): logger.error("column_mapping není slovník!"); return result_df
    for i, u in column_mapping.items():
        if i in df.columns: result_df[u] = df[i]; present.append(i)
        else: logger.warning(f"Mapovaný '{i}' (-> {u}) nenalezen."); missing.append(i); result_df[u] = pd.NA
    logger.debug(f"Mapované: {present}");
    if missing: logger.warning(f"Chyběly: {missing}");
    return result_df

def add_metadata(df, metadata_dict, source_filename):
    # (Beze změny - z předchozí verze)
    logger.info("Přidávám metadata."); df_copy = df.copy()
    if not isinstance(metadata_dict, dict): logger.error("metadata_dict není slovník!"); metadata_dict = {}
    df_copy['UCET_CISLO']=metadata_dict.get('account_number',''); df_copy['UCET_NAZEV']=metadata_dict.get('account_name','')
    df_copy['MENA']=metadata_dict.get('currency',''); df_copy['DISPONENT1']=metadata_dict.get('disponent1','')
    df_copy['DISPONENT2']=metadata_dict.get('disponent2',''); df_copy['DISPONENT3']=metadata_dict.get('disponent3',''); df_copy['ZDROJ']=source_filename or ''
    logger.debug(f"Meta: Účet='{metadata_dict.get('account_number', '')}', Měna='{metadata_dict.get('currency', '')}'"); return df_copy

# UVNITŘ data_processor.py

# Upravená metoda calculate_amounts s vyvoláním DataError
def calculate_amounts(df):
    """
    Převede sloupce částek na numerický typ a vypočítá DEBET/KREDIT nebo CASTKA.
    Vyvolá DataError, pokud chybí potřebné sloupce.
    """
    logger.info("Počítám částky (Kredit/Debet/Castka).")
    df_copy = df.copy()
    cols_to_process = ['CASTKA', 'DEBET', 'KREDIT', 'POPLATKY', 'KURZ']
    numeric_cols_status = {} # Zda je sloupec numerický nebo převoditelný

    # Pokus o převod na numerický typ a zjištění stavu
    for col in cols_to_process:
        if col in df_copy.columns:
            original_dtype = df_copy[col].dtype
            # Nahradíme čárky tečkami a odstraníme mezery jen pokud je to string
            if pd.api.types.is_string_dtype(df_copy[col]):
                 try:
                     # Regex pro odstranění mezer (včetně nedělitelných)
                     cleaned_col = df_copy[col].str.replace(',', '.', regex=False).str.replace(r'\s+', '', regex=True)
                     df_copy[col] = pd.to_numeric(cleaned_col, errors='coerce')
                 except Exception as e_conv:
                     logger.warning(f"Chyba při čištění/konverzi sloupce '{col}' (typ: {original_dtype}): {e_conv}. Pokus o přímou konverzi.")
                     # Pokud čištění selže, zkusíme přímou konverzi
                     df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')
            else:
                # Pokud to není string, zkusíme rovnou konverzi
                df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')

            # Zkontrolujeme, zda je sloupec nyní numerický
            is_numeric = pd.api.types.is_numeric_dtype(df_copy[col])
            numeric_cols_status[col] = is_numeric
            if not is_numeric and not df_copy[col].isna().all(): # Logujeme, jen pokud tam byly nějaké hodnoty
                 logger.warning(f"Nepodařilo se převést sloupec '{col}' (původní typ: {original_dtype}) na numerický typ.")
        else:
            # Sloupec ve vstupních datech vůbec neexistuje
            numeric_cols_status[col] = False
            logger.debug(f"Sloupec '{col}' pro výpočet částek chybí ve vstupních datech.")

    # Výpočet DEBET/KREDIT z CASTKA nebo naopak
    if numeric_cols_status.get('CASTKA'):
        # Máme CASTKA, dopočítáme DEBET/KREDIT, pokud chybí nebo nejsou numerické
        df_copy['CASTKA'] = df_copy['CASTKA'].fillna(0.0)
        if not numeric_cols_status.get('DEBET'):
            logger.debug("Dopočítávám DEBET z CASTKA.")
            df_copy['DEBET'] = df_copy['CASTKA'].apply(lambda x: x if pd.notna(x) and x < 0 else 0.0)
            numeric_cols_status['DEBET'] = True # Teď už je numerický
        else:
            df_copy['DEBET'] = df_copy['DEBET'].fillna(0.0) # Vyplníme případné NaN

        if not numeric_cols_status.get('KREDIT'):
            logger.debug("Dopočítávám KREDIT z CASTKA.")
            df_copy['KREDIT'] = df_copy['CASTKA'].apply(lambda x: x if pd.notna(x) and x > 0 else 0.0)
            numeric_cols_status['KREDIT'] = True
        else:
            df_copy['KREDIT'] = df_copy['KREDIT'].fillna(0.0)

    elif numeric_cols_status.get('DEBET') and numeric_cols_status.get('KREDIT'):
        # Máme DEBET a KREDIT, dopočítáme CASTKA
        logger.debug("Dopočítávám CASTKA z DEBET a KREDIT.")
        df_copy['DEBET'] = df_copy['DEBET'].fillna(0.0)
        df_copy['KREDIT'] = df_copy['KREDIT'].fillna(0.0)
        df_copy['CASTKA'] = df_copy['KREDIT'] + df_copy['DEBET']
        numeric_cols_status['CASTKA'] = True
        # Varování pro nelogické hodnoty
        if (df_copy['DEBET'] > 0).any(): logger.warning("Nalezeny kladné hodnoty ve sloupci DEBET!")
        if (df_copy['KREDIT'] < 0).any(): logger.warning("Nalezeny záporné hodnoty ve sloupci KREDIT!")

    else:
        # Nemáme ani CASTKA, ani kombinaci DEBET/KREDIT
        # Vyvoláme naši specifickou výjimku DataError
        missing_info = "'CASTKA' nebo ('DEBET' a 'KREDIT')"
        logger.error(f"Chybí potřebné sloupce pro výpočet částek: {missing_info}")
        raise DataError(f"Chyba dat: Ve vstupních datech (po mapování) chybí sloupec 'CASTKA' nebo platná kombinace sloupců 'DEBET' a 'KREDIT' pro výpočet celkové částky transakce.")

    # Zpracování POPLATKY a KURZ (pokud neexistují nebo nejsou numerické, nastavíme 0.0)
    for col in ['POPLATKY', 'KURZ']:
        if not numeric_cols_status.get(col):
            logger.debug(f"Sloupec '{col}' chybí nebo není numerický, nastavuji na 0.0.")
            df_copy[col] = 0.0
        else:
            # Pokud existuje a je numerický, jen vyplníme NaN
            df_copy[col] = df_copy[col].fillna(0.0)

    logger.info("Výpočet částek dokončen.")
    return df_copy
# UVNITŘ data_processor.py
# UVNITŘ data_processor.py

# Nezapomeňte na importy na začátku:
# from utils import DataError
# import pandas as pd
# import logging
# Musíme importovat i messagebox pro dotaz ZDE (není ideální, ale nejjednodušší)
try:
    from tkinter import messagebox
except ImportError:
    # Fallback, pokud tkinter není dostupný (např. běh bez GUI)
    messagebox = None
    logging.warning("Modul tkinter.messagebox není dostupný. Dotaz na pokračování při chybě data nebude zobrazen.")


logger = logging.getLogger(__name__)

# Metoda format_dates s flexibilní kontrolou a dotazem
# UVNITŘ data_processor.py

# Metoda format_dates - NÁVRAT K JEDNODUŠŠÍ A SPOLEHLIVĚJŠÍ VERZI
# UVNITŘ data_processor.py

# Metoda format_dates - NÁVRAT K JEDNODUŠŠÍ A SPOLEHLIVĚJŠÍ VERZI
def format_dates(df, date_column='DATUM', target_format='%d.%m.%Y'):
    """Převede sloupec s datem na zadaný formát stringu.
       Neplatné hodnoty nahradí prázdným stringem."""
    logger.info(f"Formátuji datum ve sloupci: {date_column}")
    df_copy = df.copy()

    if date_column not in df_copy.columns:
        logger.warning(f"Sloupec data '{date_column}' nebyl nalezen. Formátování přeskočeno.")
        if date_column in FINAL_COLUMN_ORDER: df_copy[date_column] = ''
        return df_copy # Vrátíme kopii

    # Pokud je sloupec prázdný, nemá smysl ho formátovat
    if df_copy[date_column].isna().all():
        logger.info(f"Sloupec data '{date_column}' je prázdný. Formátování přeskočeno.")
        df_copy[date_column] = '' # Zajistíme prázdné stringy místo NaN
        return df_copy # Vrátíme kopii

    original_dtype = df_copy[date_column].dtype
    logger.debug(f"Původní datový typ sloupce '{date_column}': {original_dtype}")

    # Pokus o konverzi na datetime objekty
    converted_dates = pd.to_datetime(df_copy[date_column], errors='coerce', dayfirst=True) # Zkusíme dayfirst=True

    # Pokud většina selhala, zkusíme dayfirst=False
    total_rows = len(df_copy)
    na_count_d1 = converted_dates.isna().sum()
    if total_rows > 0 and (na_count_d1 / total_rows) > 0.8:
        logger.debug(f"Většina datumů nerozpoznána s dayfirst=True. Zkouším dayfirst=False.")
        converted_dates_alt = pd.to_datetime(df_copy[date_column], errors='coerce', dayfirst=False)
        na_count_d0 = converted_dates_alt.isna().sum()
        if na_count_d0 < na_count_d1:
            logger.info("Formát data YYYY-MM-DD (dayfirst=False) byl úspěšnější.")
            converted_dates = converted_dates_alt
        else:
             logger.debug("Formát data bez dayfirst=True nebyl lepší.")

    # Získáme masku úspěšných konverzí
    success_mask = converted_dates.notna()
    converted_count = success_mask.sum()
    failed_count = total_rows - converted_count # Počítáme i původní NaN/prázdné jako neúspěch formátování

    logger.info(f"Formátování data: Úspěšně {converted_count}/{total_rows}, Selhalo/Prázdné {failed_count}/{total_rows}.")

    if failed_count > 0 and converted_count > 0: # Varujeme jen pokud něco selhalo, ale něco se i povedlo
         failed_indices = df_copy.index[converted_dates.isna() & df_copy[date_column].notna() & (df_copy[date_column] != '')]
         failed_examples = df_copy.loc[failed_indices, date_column].unique()[:3]
         failed_examples_str = ", ".join(f"'{str(x)[:20]}'" for x in failed_examples)
         logger.warning(f"{len(failed_indices)} neprázdných hodnot ve sloupci '{date_column}' nemohlo být rozpoznáno jako datum (např. {failed_examples_str}). Budou nahrazeny prázdným stringem.")
    elif converted_count == 0 and total_rows > 0:
         logger.error(f"Nepodařilo se rozpoznat žádné datumy ve sloupci '{date_column}'. Výstup bude prázdný.")
         # V tomto případě nevyvoláváme chybu, jen logujeme

    # Formátování úspěšných na string a nahrazení ostatních prázdným stringem
    # Použijeme .loc pro bezpečnější přiřazení
    # Nejdříve převedeme vše na string a nahradíme None/NA
    df_copy[date_column] = df_copy[date_column].fillna('').astype(str)
    # Pak aplikujeme formát na úspěšně konvertované
    if converted_count > 0:
        try:
            df_copy.loc[success_mask, date_column] = converted_dates[success_mask].dt.strftime(target_format)
        except Exception as e_format:
             logger.error(f"Chyba při finálním formátování data: {e_format}", exc_info=True)
             # Pokud formátování selže, necháme původní stringy nebo prázdné

    # Zajistíme, že všechny neúspěšné jsou prázdné stringy
    df_copy.loc[~success_mask, date_column] = ''

    # Finální kontrola typu
    if df_copy[date_column].dtype != 'object':
         df_copy[date_column] = df_copy[date_column].astype(str)

    return df_copy # Vždy vrátíme DataFrame

# KONEC METODY format_dates
# KONEC METODY format_dates# KONEC METODY format_dates# KONEC METODY format_dates# <<< ZMĚNA: Nová funkce pro sestavení čísla účtu (s detailním logováním) >>>
def _assemble_account_number(row):
        """
        Sestaví číslo účtu z PREDCISLI, PROTIUCET_CISLO a KOD_BANKY_PROTIUCET.
        Vrací string ve formátu 'PPP-CCC/BBBB' nebo 'CCC/BBBB' nebo None.
        Čistí '.0', opravuje logiku pro chybějící/neplatné předčíslí ('nan').
        """
        logger_func = logging.getLogger(__name__)

        prefix_raw = row.get('PREDCISLI', '')
        account_num_raw = row.get('PROTIUCET_CISLO', '')
        bank_code_raw = row.get('KOD_BANKY_PROTIÚČET', '')

        prefix = str(prefix_raw).strip() if pd.notna(prefix_raw) else ''
        account_num = str(account_num_raw).strip() if pd.notna(account_num_raw) else ''
        bank_code = str(bank_code_raw).strip() if pd.notna(bank_code_raw) else ''

        logger_func.debug(f"Assembling account for row {row.name}: Input PREDCISLI='{prefix}', PROTIUCET_CISLO='{account_num}', KOD_BANKY_PROTIUCET='{bank_code}'")

        prefix_clean = prefix.removesuffix('.0')
        account_num_clean = account_num.removesuffix('.0')
        bank_code_clean = bank_code.removesuffix('.0')

        if prefix != prefix_clean or account_num != account_num_clean or bank_code != bank_code_clean:
            logger_func.debug(f"Assembling account for row {row.name}: Cleaned PREDCISLI='{prefix_clean}', PROTIUCET_CISLO='{account_num_clean}', KOD_BANKY_PROTIUCET='{bank_code_clean}'")

        # --- Validace základních částí (po čištění) ---
        if not account_num_clean:
            logger_func.debug(f"Row {row.name}: Assembly failed - PROTIUCET_CISLO is missing or empty after cleaning.")
            return None
        if not bank_code_clean:
            logger_func.debug(f"Row {row.name}: Assembly failed - KOD_BANKY_PROTIUCET is missing or empty after cleaning.")
            return None

        # --- Validace a formátování kódu banky ---
        if not bank_code_clean.isdigit():
            logger_func.debug(f"Row {row.name}: Assembly failed - KOD_BANKY_PROTIUCET '{bank_code_clean}' is not purely digits.")
            return None
        if len(bank_code_clean) == 3:
            bank_code_final = "0" + bank_code_clean
        elif len(bank_code_clean) == 4:
            bank_code_final = bank_code_clean
        else:
            logger_func.debug(f"Row {row.name}: Assembly failed - KOD_BANKY_PROTIUCET '{bank_code_clean}' has invalid length ({len(bank_code_clean)}). Expected 3 or 4.")
            return None

        # --- Rozhodnutí o sestavení ---
        # OPRAVA ZDE: Podmínka nyní kontroluje, zda je prefix_clean neprázdný A ZÁROVEŇ obsahuje pouze číslice
        if prefix_clean and prefix_clean.isdigit():
            # --- Větev pro PŘÍTOMNÉ a PLATNÉ předčíslí ---
            logger_func.debug(f"Row {row.name}: Valid PREDCISLI '{prefix_clean}' found.")
            if not account_num_clean.isdigit():
                logger_func.debug(f"Row {row.name}: Assembly failed - PREDCISLI exists, but PROTIUCET_CISLO '{account_num_clean}' is not purely digits.")
                return None # Pokud máme platné předčíslí, očekáváme i platné číslo účtu

            # Sestavíme s předčíslím
            assembled = f"{prefix_clean}-{account_num_clean}/{bank_code_final}"
            logger_func.debug(f"Row {row.name}: Assembled account with prefix: {assembled}")
            return assembled
        else:
            # --- Větev pro CHYBĚJÍCÍ nebo NEPLATNÉ předčíslí (prázdné, 'nan', jiné nečíselné) ---
            if prefix_clean: # Pokud bylo neprázdné, ale nebylo číslicové, zalogujeme to
                logger_func.debug(f"Row {row.name}: Treating as 'no prefix' because PREDCISLI '{prefix_clean}' is not purely digits.")

            # Zpracujeme číslo účtu (account_num_clean)
            if account_num_clean.isdigit():
                # Je to číslo - zkontrolujeme, jestli už neobsahuje kód banky
                if f"/{bank_code_final}" in account_num: # Raději kontrolujeme původní 'account_num' pro tento případ
                    logger_func.debug(f"Row {row.name}: PROTIUCET_CISLO '{account_num}' already contains the bank code. Returning as is.")
                    return account_num
                elif '/' in account_num:
                    logger_func.debug(f"Row {row.name}: PROTIUCET_CISLO '{account_num}' contains '/' but not the expected bank code '{bank_code_final}'. Skipping assembly.")
                    return None # Neriskujeme spojení
                else:
                    # Sestavíme bez předčíslí
                    assembled = f"{account_num_clean}/{bank_code_final}"
                    logger_func.debug(f"Row {row.name}: Assembled account without prefix: {assembled}")
                    return assembled
            else:
                # Není to číslo - zkusíme, jestli to není IBAN
                iban_check = re.sub(r'\s+', '', account_num) # Použijeme původní 'account_num'
                if is_iban(iban_check):
                    iban_upper = iban_check.upper()
                    logger_func.debug(f"Row {row.name}: PROTIUCET_CISLO is not digits, but identified as IBAN: {iban_upper}")
                    return iban_upper
                else:
                    logger_func.debug(f"Row {row.name}: Assembly failed - No valid PREDCISLI, and PROTIUCET_CISLO '{account_num_clean}' is not digits and not a valid IBAN ('{iban_check}').")
                    return None


def assemble_and_normalize_protiucet(df):
    """
    Vytvoří sloupec 'PROTIUCET'.
    Priorita 1: Sestaví z PREDCISLI, PROTIUCET_CISLO, KOD_BANKY_PROTIUCET.
    Priorita 2: Pokud sestavení selže, hledá IBAN nebo CZ formát v PROTIUCET_CISLO.
    Výsledkem je normalizovaný string nebo prázdný string.
    """
    logger.info("Sestavuji a normalizuji sloupec 'PROTIUCET'.");
    df_copy = df.copy()

    # Zajistíme existenci sloupců jako string a vyplníme NaN
    required_cols = ['PREDCISLI', 'PROTIUCET_CISLO', 'KOD_BANKY_PROTIÚČET']
    for col in required_cols:
        if col not in df_copy.columns:
            logger.debug(f"Sloupec '{col}' pro sestavení protiúčtu chybí, bude považován za prázdný.")
            df_copy[col] = ''
        else:
            df_copy[col] = df_copy[col].astype(str).fillna('')

    # 1. Pokus o sestavení
    assembled_accounts = df_copy.apply(_assemble_account_number, axis=1)

    # 2. Fallback - hledání v PROTIUCET_CISLO tam, kde sestavení selhalo (None)
    fallback_mask = assembled_accounts.isnull()
    if fallback_mask.any():
        logger.info(f"Pro {fallback_mask.sum()} řádků se pokouším najít účet/IBAN přímo v 'PROTIUCET_CISLO'.")
        # Použijeme původní utils.extract_account_number jako fallback
        fallback_accounts = df_copy.loc[fallback_mask, 'PROTIUCET_CISLO'].apply(extract_account_number)
        # Přiřadíme nalezené fallback účty
        assembled_accounts.loc[fallback_mask] = fallback_accounts

    # Uložíme výsledek do sloupce PROTIUCET, nahradíme None prázdným stringem
    df_copy['PROTIUCET'] = assembled_accounts.fillna('')

    ok = (df_copy['PROTIUCET'] != '').sum(); total = len(df_copy)
    logger.info(f"Sloupec 'PROTIUCET' vytvořen. Nalezeno/sestaveno {ok}/{total} účtů.")
    if ok < total: logger.warning(f"{total-ok} protiúčtů se nepodařilo sestavit/nalézt.")

    return df_copy

# <<< ZMĚNA: create_counterparty_details používá nový PROTIUCET >>>
# UVNITŘ data_processor.py

def create_counterparty_details(df):
    """Vytvoří sloupec 'PROTIUCET+NAZEV' spojením 'PROTIUCET' a 'PROTIUCET_NAZEV',
       pouze pokud jsou obě hodnoty přítomny.""" # Aktualizován docstring
    logger.info("Vytvářím 'PROTIUCET+NAZEV'."); df_copy = df.copy()
    req_cols = ['TYP TRANSAKCE', 'PROTIUCET', 'PROTIUCET_NAZEV']
    for c in req_cols:
        if c not in df_copy.columns: logger.warning(f"Chybí '{c}'."); df_copy[c] = ''
        else:
             # Lepší čištění NaN/None před konverzí na string
             df_copy[c] = df_copy[c].fillna('').replace([pd.NA, np.nan, None, pd.NaT], '').astype(str)
             try: df_copy[c] = df_copy[c].str.replace(r'^(nan|none|nat|<na>)$', '', regex=True, case=False, na='')
             except Exception as e_rep_str: logger.warning(f"Chyba čištění '{c}': {e_rep_str}")


    def _generate(row):
        excluded = ["Banka", "Výběr", "Vklad", "Poplatek"]; ttype = row.get('TYP TRANSAKCE', '').strip().lower()
        if any(ex.lower() in ttype for ex in excluded if ex): return ''

        protiucet = row.get('PROTIUCET', '').strip()
        nazev = row.get('PROTIUCET_NAZEV', '').strip()

        # --- ZMĚNĚNÁ LOGIKA ---
        if protiucet and nazev:
            return f"{protiucet} + {nazev}"
        else:
            return ''
        # --- KONEC ZMĚNĚNÉ LOGIKY ---

    df_copy['PROTIUCET+NAZEV'] = df_copy.apply(_generate, axis=1)
    logger.info("'PROTIUCET+NAZEV' vytvořen (pouze pro řádky s účtem i názvem).") # Aktualizován log
    return df_copy

# KONEC METODY create_counterparty_details

    def _generate(row): # <<<<<< TATO FUNKCE <<<<<<
        excluded = ["Banka", "Výběr", "Vklad", "Poplatek"]; ttype = row.get('TYP TRANSAKCE', '').strip().lower()
        if any(ex.lower() in ttype for ex in excluded if ex): return ''

        protiucet = row.get('PROTIUCET', '').strip()
        nazev = row.get('PROTIUCET_NAZEV', '').strip()

        # --- ZMĚNĚNÁ LOGIKA ---
        # Spojíme POUZE pokud máme obojí
        if protiucet and nazev:
            return f"{protiucet} + {nazev}"
        else:
            # Jinak vrátíme prázdný string
            return ''
        # --- KONEC ZMĚNĚNÉ LOGIKY ---

    # Zbytek metody create_counterparty_details zůstává stejný
    # df_copy['PROTIUCET+NAZEV'] = df_copy.apply(_generate, axis=1); logger.info("'PROTIUCET+NAZEV' vytvořen.")
    # return df_copy

    df_copy['PROTIUCET+NAZEV'] = df_copy.apply(_generate, axis=1); logger.info("'PROTIUCET+NAZEV' vytvořen.")
    return df_copy

# --- Funkce pro typy transakcí (pracují se seznamem pravidel) ---
# UVNITŘ data_processor.py

# --- Funkce pro typy transakcí (s vylepšeným error handlingem) ---

# POZNÁMKA: _determine_type_for_row nyní může vyvolat ConfigError
def _determine_type_for_row(row, transaction_rules_list, default_search_cols):
    """Určí typ transakce pro jeden řádek na základě seznamu pravidel.
       Může vyvolat ConfigError, pokud narazí na neplatnou podmínku."""
    # Tato funkce je volána pro každý řádek, logování by mělo být omezené
    if not transaction_rules_list: return None # Žádná pravidla

    # Iterujeme přes pravidla v daném pořadí
    for i, rule_dict in enumerate(transaction_rules_list):
        rule_desc = f"Pravidlo typu #{i+1}" # Pro chybové hlášky

        # --- Validace struktury pravidla ---
        # Základní kontrola, zda je to slovník (měla by být zajištěna výše)
        if not isinstance(rule_dict, dict):
             # Tuto chybu by měla zachytit už assign_transaction_types, ale pro jistotu logujeme a přeskočíme
             logger.error(f"{rule_desc}: Položka pravidel není slovník (očekáván objekt JSON). Pravidlo ignorováno: {rule_dict}")
             continue # Přeskočíme toto neplatné pravidlo

        rule_type = rule_dict.get("type")
        conditions = rule_dict.get("conditions")
        # Použijeme sloupce z pravidla, nebo výchozí, pokud nejsou specifikovány
        search_cols_input = rule_dict.get("search_in") # Může být None

        # Validace povinných polí a jejich typů
        if not rule_type or not isinstance(rule_type, str):
            logger.warning(f"{rule_desc}: Chybí nebo není textový řetězec 'type'. Pravidlo ignorováno.")
            continue
        if not isinstance(conditions, dict) or not conditions:
            logger.warning(f"{rule_desc} (typ '{rule_type}'): Chybí nebo je neplatná sekce 'conditions' (musí být neprázdný objekt JSON). Pravidlo ignorováno.")
            continue
        # Validace search_cols - musí být seznam stringů, pokud je zadán
        if search_cols_input is not None: # Pokud je klíč přítomen
            if isinstance(search_cols_input, list) and all(isinstance(item, str) for item in search_cols_input) and search_cols_input:
                search_cols = search_cols_input # Použijeme zadaný seznam
            else:
                logger.warning(f"{rule_desc} (typ '{rule_type}'): Sekce 'search_in' má neplatný formát (očekáván neprázdný seznam textových řetězců). Používám výchozí sloupce.")
                search_cols = default_search_cols # Použijeme výchozí jako fallback
        else: # Pokud klíč 'search_in' chybí, použijeme výchozí
             search_cols = default_search_cols
        # --- Konec validace pravidla ---


        # Zkontrolujeme, zda řádek splňuje VŠECHNY podmínky tohoto pravidla
        all_conditions_met = True
        # Iterujeme přes všechny definované podmínky (např. "contains", "startswith")
        for condition_key, keywords in conditions.items():
            # Vytvoříme slovník pro jednu podmínku pro _apply_single_rule
            single_rule = {condition_key: keywords}
            # _apply_single_rule nyní může vyvolat ConfigError při neznámé podmínce
            # Tuto výjimku zde zachytíme a přidáme kontext

            match_in_any_col = False
            # Hledáme shodu v ALESPON jednom ze specifikovaných sloupců
            for col_name in search_cols:
                # Zkontrolujeme, zda sloupec existuje v řádku a není NaN
                if col_name in row.index and pd.notna(row[col_name]):
                    try:
                        # Volání _apply_single_rule může vyvolat ConfigError
                        if _apply_single_rule(row[col_name], single_rule):
                            match_in_any_col = True
                            break # Našli jsme shodu v tomto sloupci, pro tuto podmínku stačí
                    except ConfigError as ce:
                         # Chyba v konfiguraci pravidla (např. neznámá podmínka), předáme dál
                         # Přidáme informaci o pravidle a typu pro lepší kontext
                         raise ConfigError(f"{rule_desc} (typ: '{rule_type}'): {ce}") from ce
                    except Exception as e_apply:
                        # Jiná neočekávaná chyba při aplikaci pravidla
                        logger.error(f"Neočekávaná chyba při aplikaci {rule_desc}, podmínka '{condition_key}', sloupec '{col_name}': {e_apply}", exc_info=True)
                        # Považujeme podmínku za nesplněnou a zastavíme hledání v dalších sloupcích pro tuto podmínku
                        match_in_any_col = False
                        break

            # Pokud TATO podmínka nebyla splněna v ŽÁDNÉM sloupci, celé pravidlo neplatí
            if not match_in_any_col:
                all_conditions_met = False
                break # Nemá smysl kontrolovat další podmínky tohoto pravidla, jdeme na další pravidlo

        # Pokud byly splněny VŠECHNY podmínky tohoto pravidla, našli jsme typ
        if all_conditions_met:
            # logger.debug(f"Řádek {row.name}: Přiřazen typ '{rule_type}' podle {rule_desc}.") # Může být příliš ukecané
            return rule_type

    # Pokud žádné pravidlo ze seznamu neodpovídalo, vrátíme None
    return None


def assign_transaction_types(df, transaction_type_rules_list, default_search_cols=DEFAULT_RULE_SEARCH_COLUMNS):
    """Přiřadí typy transakcí k řádkům DataFrame na základě seznamu pravidel.
       Vyvolává ConfigError při neplatném pravidle."""
    logger.info("Přiřazuji typy transakcí podle pravidel...")
    df_copy = df.copy()

    # Základní kontrola vstupního seznamu pravidel
    if not transaction_type_rules_list or not isinstance(transaction_type_rules_list, list):
        logger.warning("Seznam pravidel pro typy transakcí ('transaction_types') chybí nebo není seznam. Všechny transakce budou nezařazené.")
        df_copy['TYP TRANSAKCE'] = '' # Vytvoříme prázdný sloupec
        return df_copy

    # --- Validace struktury každého pravidla v seznamu PŘED aplikací ---
    # (Můžeme to udělat zde, abychom odchytili chyby dříve než v apply)
    for i, rule in enumerate(transaction_type_rules_list):
         rule_desc = f"Pravidlo typu #{i+1}"
         if not isinstance(rule, dict):
              raise ConfigError(f"{rule_desc}: Položka v 'transaction_types' není slovník (objekt JSON). Pravidlo: {rule}")
         if "type" not in rule or not isinstance(rule.get("type"), str) or not rule.get("type"):
              raise ConfigError(f"{rule_desc}: Chybí nebo je neplatný klíč 'type' (musí být neprázdný text). Pravidlo: {rule}")
         if "conditions" not in rule or not isinstance(rule.get("conditions"), dict) or not rule.get("conditions"):
              raise ConfigError(f"{rule_desc} (typ '{rule.get('type', '?')}'): Chybí nebo je neplatná sekce 'conditions' (musí být neprázdný objekt JSON). Pravidlo: {rule}")
         if "search_in" in rule and (not isinstance(rule.get("search_in"), list) or not rule.get("search_in")):
              # Pokud 'search_in' existuje, musí to být neprázdný seznam
               raise ConfigError(f"{rule_desc} (typ '{rule.get('type', '?')}'): Sekce 'search_in' je přítomna, ale má neplatný formát (musí být neprázdné pole/seznam textových řetězců). Pravidlo: {rule}")
         # Další validace (např. kontrola klíčů v conditions) proběhne v _determine_type_for_row
    logger.debug("Struktura všech pravidel typů transakcí byla základně validována.")
    # --- Konec validace struktury ---


    # Aplikace pravidel na každý řádek (obaleno v try...except)
    try:
        # Použijeme apply; _determine_type_for_row může vyvolat ConfigError
        assigned_types = df_copy.apply(
            _determine_type_for_row,
            axis=1,
            transaction_rules_list=transaction_type_rules_list,
            default_search_cols=default_search_cols
        )
        # Výsledek apply uložíme do sloupce
        df_copy['TYP TRANSAKCE'] = assigned_types

    except ConfigError as ce:
         # Zachytíme ConfigError z _determine_type_for_row a předáme dál
         logger.error(f"Chyba v konfiguraci pravidla při přiřazování typů: {ce}", exc_info=True)
         raise ce # Předáme GUI pro zobrazení
    except Exception as e:
        # Jiná neočekávaná chyba během apply
        logger.error(f"Došlo k neočekávané chybě během hromadného přiřazování typů transakcí: {e}", exc_info=True)
        # V případě chyby nastavíme všude prázdný string a vyvoláme obecnou ProcessingError
        df_copy['TYP TRANSAKCE'] = ''
        raise ProcessingError(f"Neočekávaná chyba při přiřazování typů: {e}") from e

    # Nahradíme None (pokud nějaké zbyly) prázdným stringem
    df_copy['TYP TRANSAKCE'] = df_copy['TYP TRANSAKCE'].fillna('')

    # Spočítáme statistiky
    assigned_count = (df_copy['TYP TRANSAKCE'] != '').sum()
    unassigned_count = len(df_copy) - assigned_count
    logger.info(f"Přiřazování typů dokončeno. Zařazeno: {assigned_count}, Nezařazeno (prázdný typ): {unassigned_count}.")

    return df_copy
# UVNITŘ data_processor.py

def assign_transaction_types(df, transaction_type_rules_list, default_search_cols=DEFAULT_RULE_SEARCH_COLUMNS):
    """Přiřadí typy transakcí. Vyvolává ConfigError při neplatném pravidle nebo podmínce."""
    logger.info("Přiřazuji typy transakcí podle pravidel...")
    df_copy = df.copy()

    if not transaction_type_rules_list or not isinstance(transaction_type_rules_list, list):
        logger.warning("Seznam pravidel pro typy transakcí chybí nebo je neplatný."); df_copy['TYP TRANSAKCE'] = ''; return df_copy

    # Validace struktury pravidel PŘED apply
    for i, rule in enumerate(transaction_type_rules_list):
         rule_desc = f"Pravidlo typu #{i+1}"
         if not isinstance(rule, dict): raise ConfigError(f"{rule_desc}: Není slovník.")
         if "type" not in rule or not isinstance(rule.get("type"), str) or not rule.get("type"): raise ConfigError(f"{rule_desc}: Chybí/neplatný 'type'.")
         if "conditions" not in rule or not isinstance(rule.get("conditions"), dict) or not rule.get("conditions"): raise ConfigError(f"{rule_desc} (typ '{rule.get('type', '?')}'): Chybí/neplatné 'conditions'.")
         if "search_in" in rule and (not isinstance(rule.get("search_in"), list) or not rule.get("search_in")): raise ConfigError(f"{rule_desc} (typ '{rule.get('type', '?')}'): Neplatné 'search_in'.")
    logger.debug("Struktura pravidel typů validována.")

    # --- Aplikace pravidel ---
    # Zde potřebujeme zachytit chyby z apply a předat je dál
    try:
        # Funkce, která se aplikuje na každý řádek a může vyvolat výjimku
        def apply_rules_to_row(row):
            return _determine_type_for_row(row, transaction_type_rules_list, default_search_cols)

        # Výsledek apply může obsahovat None nebo typy transakcí
        assigned_types = df_copy.apply(apply_rules_to_row, axis=1)
        df_copy['TYP TRANSAKCE'] = assigned_types

    except ConfigError as ce:
         # Pokud _determine_type_for_row vyvolalo ConfigError, zachytíme ji a předáme dál
         logger.error(f"Chyba v konfiguraci pravidla při apply: {ce}", exc_info=True)
         raise ce # Předáme specifickou chybu výše
    except Exception as e:
        # Jiná neočekávaná chyba během apply
        logger.error(f"Neočekávaná chyba během apply v assign_transaction_types: {e}", exc_info=True)
        df_copy['TYP TRANSAKCE'] = '' # V případě chyby nastavíme prázdné
        raise ProcessingError(f"Neočekávaná chyba při přiřazování typů: {e}") from e

    # Nahradíme None prázdným stringem
    df_copy['TYP TRANSAKCE'] = df_copy['TYP TRANSAKCE'].fillna('')
    assigned_count = (df_copy['TYP TRANSAKCE'] != '').sum(); unassigned_count = len(df_copy) - assigned_count
    logger.info(f"Přiřazování typů dokončeno. Zařazeno: {assigned_count}, Nezařazeno: {unassigned_count}.")
    return df_copy

# KONEC METODY assign_transaction_types
def resolve_unknown_transactions(df, strategy='mark_unknown'):
    # (Beze změny - z předchozí verze, hledá '')
    logger.info(f"Řeším nezařazené (strategie: {strategy}).");
    if 'TYP TRANSAKCE' not in df.columns: logger.warning("'TYP TRANSAKCE' chybí."); return df
    df_copy = df.copy(); unknown_mask = df_copy['TYP TRANSAKCE'] == ''; count = unknown_mask.sum()
    if count > 0:
        if strategy == 'mark_unknown': logger.info(f"Označuji {count} prázdných jako '{UNKNOWN_TRANSACTION_TYPE}'."); df_copy.loc[unknown_mask, 'TYP TRANSAKCE'] = UNKNOWN_TRANSACTION_TYPE
        else: logger.warning(f"Neznámá strategie '{strategy}'.")
    else: logger.info("Nenalezeny žádné transakce bez typu (prázdný string).")
    return df_copy

def classify_unknown_by_amount(df):
    # (Beze změny - z předchozí verze)
    logger.info(f"Klasifikuji '{UNKNOWN_TRANSACTION_TYPE}' podle částky.");
    if 'TYP TRANSAKCE' not in df.columns or 'CASTKA' not in df.columns: logger.warning("Chybí 'TYP TRANSAKCE'/'CASTKA'."); return df
    df_copy = df.copy(); unknown_mask = df_copy['TYP TRANSAKCE'] == UNKNOWN_TRANSACTION_TYPE; count = unknown_mask.sum()
    if count == 0: logger.info(f"Nenalezeny žádné '{UNKNOWN_TRANSACTION_TYPE}'."); return df_copy
    logger.info(f"Nalezeno {count} '{UNKNOWN_TRANSACTION_TYPE}' ke klasifikaci."); classified = 0
    for index in df_copy[unknown_mask].index:
        castka = pd.to_numeric(df_copy.loc[index, 'CASTKA'], errors='coerce'); new_type = UNKNOWN_TRANSACTION_TYPE
        if pd.notna(castka):
            if castka > 0: new_type = "Příchozí"; classified += 1
            elif castka < 0: new_type = "Odchozí"; classified += 1
        df_copy.loc[index, 'TYP TRANSAKCE'] = new_type
    logger.info(f"Dodatečně klasifikováno {classified} transakcí."); return df_copy

# <<< ZMĚNA: sort_and_finalize_columns zajišťuje správné typy a nahrazuje NaN/None >>>
def sort_and_finalize_columns(df, column_order=FINAL_COLUMN_ORDER):
    """Seřadí sloupce, doplní chybějící, zajistí správné typy a nahradí NaN/None."""
    logger.info("Finalizuji, čistím a řadím sloupce."); df_copy = df.copy()
    current_columns = set(df_copy.columns)

    # Doplnění chybějících sloupců
    for col in column_order:
        if col not in current_columns:
            default_value = 0.0 if col in NUMERIC_FINAL_COLS else ''
            df_copy[col] = default_value; current_columns.add(col)
            logger.debug(f"Doplněn '{col}'='{default_value}'.")

    # Vynucení typů a čištění NaN/None
    for col in df_copy.columns:
        # Číselné sloupce
        if col in NUMERIC_FINAL_COLS:
            df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce').fillna(0.0)
        # Sloupce, které mají být text, i když vypadají jako číslo (včetně těch problémových)
        elif col in STRING_NUMERIC_COLS: # {'PREDCISLI', 'PROTIUCET_CISLO', 'KOD_BANKY_PROTIÚČET', 'VS', 'KS', 'SS'}
             def clean_numeric_string(val):
                 if pd.isna(val): return ''
                 s_val = str(val)
                 if s_val.endswith('.0'): return s_val[:-2]
                 # Explicitní kontrola pro 'nan', 'None', 'NaT' (case-insensitive)
                 if s_val.lower() in ['nan', 'none', 'nat']: return ''
                 return s_val
             # Aplikujeme funkci a pro jistotu ještě fillna('')
             df_copy[col] = df_copy[col].apply(clean_numeric_string).fillna('')
        # Ostatní sloupce (předpokládáme text)
        else:
             # Nahradíme různé formy NaN/None a převedeme na string
             df_copy[col] = df_copy[col].fillna('').replace([pd.NA, np.nan, None], '').astype(str)
             # Explicitní nahrazení stringů 'nan', 'None', 'NaT'
             try:
                  df_copy[col] = df_copy[col].str.replace(r'^(nan|none|nat)$', '', regex=True, case=False)
             except Exception as e_rep_str:
                  logger.warning(f"Chyba při nahrazování 'nan'/'None' ve sloupci '{col}': {e_rep_str}")


    # Extra sloupce
    extra_cols = sorted(list(current_columns - set(column_order)))
    if extra_cols: logger.warning(f"Extra sloupce: {extra_cols}.")
    final_list = [c for c in column_order if c in current_columns] + extra_cols
    final_df = df_copy[final_list]; logger.info(f"Sloupce ({len(final_df.columns)}) finalizovány.")
    return final_df


# --- Hlavní funkce pro zpracování ---
# UVNITŘ data_processor.py

# Nezapomeňte na importy na začátku souboru:
# import logging
# from utils import ConfigError, DataError # Import výjimek

logger = logging.getLogger(__name__) # Standardní logger

# --- Hlavní funkce pro zpracování ---
def process_data(df_input, config, source_filename, metadata_values):
    """
    Hlavní funkce pro orchestraci zpracování datového rámce.
    Používá specifické výjimky pro lepší hlášení chyb.
    """
    if df_input is None or df_input.empty:
        logger.warning("Vstupní DataFrame pro process_data je prázdný.")
        # Vrátíme prázdný DF s definovanými sloupci, aby navazující kód neselhal
        return pd.DataFrame(columns=FINAL_COLUMN_ORDER)

    logger.info(f"Zahajuji zpracování souboru: {source_filename}")
    df = df_input.copy() # Pracujeme s kopií
    original_rows = len(df)

    # --- Získání a základní validace konfigurace a metadat ---
    try:
        # Získání sekcí z konfigurace
        column_mapping = config.get("column_mapping")
        ignore_rules = config.get("ignore_rows_rules", []) # Default prázdný seznam
        transaction_rules = config.get("transaction_types", []) # Default prázdný seznam

        # Validace typů hlavních sekcí
        if not isinstance(column_mapping, dict):
            raise ConfigError("Chyba konfigurace: Sekce 'column_mapping' chybí nebo není platný slovník (objekt JSON).")
        if not isinstance(ignore_rules, list):
            raise ConfigError("Chyba konfigurace: Sekce 'ignore_rows_rules' musí být seznam (pole JSON).")
        if not isinstance(transaction_rules, list):
            raise ConfigError("Chyba konfigurace: Sekce 'transaction_types' musí být seznam (pole JSON).")

        # Validace metadat (jen logujeme varování)
        if not isinstance(metadata_values, dict):
            logger.warning("Vstupní metadata_values nejsou slovník! Používám prázdný slovník.")
            metadata_values = {}

    except KeyError as ke:
         # Pokud by config nebyl slovník a .get selhalo
         raise ConfigError(f"Chyba konfigurace: Chybí očekávaný klíč '{ke}' v hlavním objektu konfigurace.")
    # --- Konec validace ---

    # --- Jednotlivé kroky zpracování ---
    try:
        logger.info("1. Mapování sloupců...")
        mapped_df = map_columns(df, column_mapping)

        logger.info("2. Aplikace pravidel pro ignorování...")
        filtered_df = apply_ignore_rules(mapped_df, ignore_rules)
        if filtered_df.empty:
            logger.warning("Po aplikaci pravidel pro ignorování nezůstaly žádné řádky.")
            # Vrátíme prázdný DF se správnými sloupci
            return sort_and_finalize_columns(pd.DataFrame(columns=FINAL_COLUMN_ORDER))

        logger.info("3. Přidání metadat...")
        meta_df = add_metadata(filtered_df, metadata_values, source_filename)

        logger.info("4. Výpočet částek (Kredit/Debet)...")
        amount_df = calculate_amounts(meta_df) # Může vyvolat DataError

        logger.info("5. Sestavení a normalizace protiúčtu...")
        counterparty_df = assemble_and_normalize_protiucet(amount_df)

        logger.info("6. Přiřazení typů transakcí...")
        typed_df = assign_transaction_types(counterparty_df, transaction_rules)

        logger.info("7. Zpracování neznámých typů...")
        resolved_df = resolve_unknown_transactions(typed_df) # Označí jako 'Neznámý'

        logger.info("8. Formátování data...")
        date_formatted_df = format_dates(resolved_df)

        logger.info("9. Vytvoření detailu protiúčtu...")
        detailed_df = create_counterparty_details(date_formatted_df)

        logger.info("10. Finalizace sloupců (čištění, typy, řazení)...")
        final_df = sort_and_finalize_columns(detailed_df)

    # Zachytíme naše specifické chyby a předáme je dál
    except (ConfigError, DataError) as specific_error:
         logger.error(f"Chyba při zpracování dat: {specific_error}", exc_info=True)
         raise specific_error # Předáme dál, aby GUI zobrazilo detail
    # Zachytíme i jiné neočekávané chyby během kroků zpracování
    except Exception as general_error:
         logger.error(f"Neočekávaná chyba během kroků zpracování dat: {general_error}", exc_info=True)
         # Zabalíme obecnou chybu do naší ProcessingError pro konzistenci
         raise ProcessingError(f"Neočekávaná chyba zpracování: {general_error}")
    # --- Konec kroků zpracování ---

    processed_rows = len(final_df)
    logger.info(f"Zpracování souboru {source_filename} dokončeno. Výsledný počet řádků: {processed_rows} (z původních {original_rows}).")
    return final_df

# KONEC METODY process_data