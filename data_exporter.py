# data_exporter.py (Zjednodušená verze spoléhající na čištění v process_data)
import pandas as pd
import os
from data_processor import NUMERIC_FINAL_COLS, STRING_NUMERIC_COLS, UNKNOWN_TRANSACTION_TYPE
import logging
import numpy as np # Pro np.nan
from tkinter import messagebox

logger = logging.getLogger(__name__)

OUTPUT_DIR = 'output'
UNKNOWN_PREFIX = 'nezname_'
CSV_ENCODING = 'utf-8-sig'
CSV_SEPARATOR = ';'
CSV_DECIMAL = ','

# Sloupce, které chceme jako celé číslo bez .0 v CSV (pokud je to možné)
SYMBOL_COLS_FOR_CSV = ['VS', 'KS', 'SS', 'PREDCISLI', 'PROTIUCET_CISLO', 'KOD_BANKY_PROTIÚČET'] # Přidány další

# UVNITŘ data_exporter.py

# ... (importy a konstanty na začátku) ...
logger = logging.getLogger(__name__)
# ... (definice konstant CSV_*, SYMBOL_COLS_FOR_CSV, atd.) ...
# UVNITŘ data_exporter.py

def _format_df_for_csv_export(df, decimal_separator=','):
    """Pomocná funkce pro finální formátování DataFrame PŘED CSV exportem.
       Formátuje VŠECHNA čísla na stringy: celá bez .0, desetinná s TEČKOU.
       to_csv pak pomocí 'decimal' parametru zajistí finální oddělovač."""
    if df is None: return None
    df_copy = df.copy()
    logger.debug(f"_format_df_for_csv_export: Formátuji pro CSV (výstupní oddělovač bude '{decimal_separator}')")

    # Sloupce, které určitě chceme formátovat jako čísla (pokud existují)
    numeric_cols_to_format = list(NUMERIC_FINAL_COLS.union(SYMBOL_COLS_FOR_CSV))

    # Funkce pro formátování čísla na string
    def format_number_for_export(val):
        if pd.isna(val) or val == '':
            return '' # Prázdné pro chybějící hodnoty
        try:
            f_val = float(val)
            # Je to celé číslo? (S tolerancí pro nepřesnosti floatu)
            if abs(f_val - round(f_val)) < 1e-9: # Malá tolerance
                return str(int(round(f_val))) # Vracíme jako int string
            else:
                # Není celé číslo, vrátíme jako string s TEČKOU
                # to_csv si pak poradí s parametrem 'decimal'
                return str(f_val).replace(',', '.') # Zajistíme tečku pro jistotu
        except (ValueError, TypeError):
            # Pokud to není číslo, vrátíme původní string (očištěný)
            return str(val).strip()

    # Projdeme všechny sloupce v kopii DataFrame
    for col in df_copy.columns:
        logger.debug(f"Formátuji sloupec '{col}' pro CSV export...")
        # Je sloupec v seznamu těch, které mají být čísla?
        if col in numeric_cols_to_format:
            # Aplikujeme naši formátovací funkci
            try:
                # Nejprve zajistíme, že NaN jsou '' pro apply
                df_copy[col] = df_copy[col].fillna('')
                df_copy[col] = df_copy[col].apply(format_number_for_export)
                logger.debug(f" -> Sloupec '{col}' naformátován jako číslo/string.")
            except Exception as e_format:
                logger.error(f"Chyba formátování numerického sloupce '{col}': {e_format}. Ponechávám jako string.")
                # Záložní převod na string
                df_copy[col] = df_copy[col].fillna('').astype(str)
        else:
            # Ostatní sloupce převedeme na string a vyčistíme
            df_copy[col] = df_copy[col].fillna('').replace([pd.NA, np.nan, None, pd.NaT], '').astype(str)
            try:
                df_copy[col] = df_copy[col].str.replace(r'^(nan|none|nat|<na>)$', '', regex=True, case=False)
            except AttributeError: pass

    logger.debug("_format_df_for_csv_export: Formátování dokončeno.")
    return df_copy

# KONEC METODY _format_df_for_csv_export

# Upravená save_data s kontrolou zápisu
def save_data(df, output_filepath, save_format, **kwargs):
    """
    Uloží zpracovaný DataFrame do CSV nebo XLSX.
    Přidána kontrola existence a velikosti souboru po zápisu.
    Vrací True při úspěchu, False při chybě (a vyvolává výjimku).
    """
    if df is None or not isinstance(df, pd.DataFrame):
        msg = f"Nelze uložit neplatná data (typ: {type(df)})."; logger.error(msg); raise ValueError(msg)
    if df.empty: logger.warning(f"Pokus o uložení prázdného DF do {output_filepath}. Přeskakuji."); return True # Prázdný DF není chyba

    logger.info(f"Ukládám data do: {output_filepath} (formát: {save_format})")
    write_successful = False # Flag pro kontrolu
    try:
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)

        if save_format == 'csv':
            decimal_sep = kwargs.get('decimal_separator', CSV_DECIMAL)
            logger.info(f"Exportuji CSV s desetinným oddělovačem: '{decimal_sep}'")
            df_formatted = _format_df_for_csv_export(df, decimal_separator=decimal_sep)
            if df_formatted is None: raise ValueError("Formátování pro CSV selhalo.")

            df_formatted.to_csv(output_filepath, index=False, encoding=CSV_ENCODING, sep=CSV_SEPARATOR, decimal=decimal_sep, na_rep='')
            # Kontrola po zápisu
            if os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 0:
                 write_successful = True
                 logger.info(f"CSV soubor úspěšně zapsán (velikost: {os.path.getsize(output_filepath)} B).")
            else:
                 logger.error(f"CSV soubor '{os.path.basename(output_filepath)}' nebyl vytvořen nebo je prázdný po volání to_csv!")

        elif save_format == 'xlsx':
            df_excel = df.copy().fillna('')
            df_excel.to_excel(output_filepath, index=False, engine='openpyxl')
            # Kontrola po zápisu
            if os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 10: # Excel má malou hlavičku i prázdný
                 write_successful = True
                 logger.info(f"Excel soubor úspěšně zapsán (velikost: {os.path.getsize(output_filepath)} B).")
            else:
                 logger.error(f"Excel soubor '{os.path.basename(output_filepath)}' nebyl vytvořen nebo je příliš malý po volání to_excel!")

        else:
             msg = f"Nepodporovaný formát pro uložení: {save_format}"; logger.error(msg); raise ValueError(msg)

        # Pokud zápis selhal (podle naší kontroly), vyvoláme chybu
        if not write_successful:
            raise IOError(f"Zápis do souboru '{os.path.basename(output_filepath)}' se nezdařil (soubor neexistuje nebo je prázdný).")

        return True # Vše proběhlo úspěšně

    except Exception as e:
        logger.error(f"Chyba při ukládání souboru {output_filepath}: {e}", exc_info=True)
        # Předáme chybu dál, aby ji GUI mohlo zobrazit
        # Zabalíme do IOError pro konzistenci
        raise IOError(f"Uložení souboru '{os.path.basename(output_filepath)}' selhalo: {e}") from e

# KONEC METODY save_data
# ... (funkce save_unknown_transactions zůstává stejná) ...
def save_unknown_transactions(df, base_filename, output_dir=OUTPUT_DIR, unknown_marker=UNKNOWN_TRANSACTION_TYPE):
    """Uloží neznámé transakce (vždy jako CSV)."""
    if df is None or df.empty: return
    if 'TYP TRANSAKCE' not in df.columns: logger.info("Chybí 'TYP TRANSAKCE'."); return

    try: unknown_df = df[df['TYP TRANSAKCE'] == unknown_marker].copy()
    except KeyError: logger.warning("Chyba přístupu k 'TYP TRANSAKCE'."); return

    if not unknown_df.empty:
        try:
            os.makedirs(output_dir, exist_ok=True)
            unknown_fn_base = f"{UNKNOWN_PREFIX}{os.path.splitext(base_filename)[0]}.csv"
            unknown_output_fn = os.path.join(output_dir, unknown_fn_base)
            logger.info(f"Nalezeno {len(unknown_df)} '{unknown_marker}' transakcí. Ukládám do: {unknown_output_fn}")
            df_formatted = _format_df_for_csv_export(unknown_df) # Formátujeme pro CSV
            if df_formatted is None: raise ValueError("Formátování neznámých pro CSV selhalo.")
            df_formatted.to_csv(unknown_output_fn, index=False, encoding=CSV_ENCODING, sep=CSV_SEPARATOR, decimal=CSV_DECIMAL, na_rep='')
            logger.info(f"Neznámé transakce uloženy.")
        except Exception as e:
            logger.error(f"Chyba ukládání neznámých {unknown_output_fn}: {e}", exc_info=True)
            messagebox.showerror("Chyba Ukládání (Neznámé)", f"Uložení neznámých selhalo:\n{e}")
    else: logger.info(f"Nenalezeny žádné '{unknown_marker}' transakce k uložení.")