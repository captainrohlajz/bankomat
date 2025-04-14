# data_loader.py
import pandas as pd
import logging
import os
import chardet # Knihovna pro detekci kódování (je třeba doinstalovat: pip install chardet)

logger = logging.getLogger(__name__)

def load_data(file_path, sample_rows=None):
    """
    Načte data z CSV, XLSX nebo XLS souboru do Pandas DataFrame.
    Pro CSV zkouší běžná kódování a oddělovače.
    Pokud je sample_rows zadáno, načte jen daný počet řádků.
    """
    operation = "Načítám vzorek dat" if sample_rows else "Načítám kompletní data"
    logger.info(f"{operation} ze souboru: {file_path}")
    file_extension = os.path.splitext(file_path)[1].lower()
    df = None

    try:
        if file_extension == '.csv':
            # --- Logika pro CSV ---
            encodings_to_try = ['utf-8', 'cp1250', 'latin1']
            separators_to_try = [';', ',']
            detected_encoding = None

            # 1. Pokus o detekci kódování pomocí chardet
            try:
                with open(file_path, 'rb') as f_detect:
                    raw_data = f_detect.read(1024 * 10) # Přečteme max 10KB
                    result = chardet.detect(raw_data)
                    detected_encoding = result['encoding']
                    confidence = result['confidence']
                    if detected_encoding and confidence > 0.7:
                        logger.info(f"Chardet detekoval kódování: {detected_encoding} (jistota: {confidence:.2f})")
                        detected_encoding_lower = detected_encoding.lower()
                        current_encodings_lower = [e.lower() for e in encodings_to_try]
                        if detected_encoding_lower not in current_encodings_lower:
                             encodings_to_try.insert(0, detected_encoding)
                        else:
                             # Přesuneme existující na začátek
                             existing_index = current_encodings_lower.index(detected_encoding_lower)
                             encodings_to_try.insert(0, encodings_to_try.pop(existing_index))
                    else:
                        logger.info(f"Chardet detekoval {detected_encoding} s nízkou jistotou ({confidence:.2f}), spoléhám na běžná kódování.")
            except Exception as e_chardet:
                logger.warning(f"Chyba při detekci kódování pomocí chardet: {e_chardet}. Pokračuji s běžnými kódováními.")

            # 2. Zkoušení kombinací
            loaded_ok = False
            last_exception = None # Uchová poslední výjimku
            logger.debug(f"Zkoušená kódování: {encodings_to_try}")
            logger.debug(f"Zkoušené oddělovače: {separators_to_try}")

            for enc in encodings_to_try:
                for sep in separators_to_try:
                    logger.debug(f"Zkouším CSV načíst s encoding='{enc}', sep='{sep}'")
                    try:
                        df = pd.read_csv(
                            file_path,
                            encoding=enc,
                            sep=sep,
                            nrows=sample_rows,
                            skipinitialspace=True,
                            low_memory=False
                        )
                        logger.info(f"CSV soubor úspěšně načten (encoding='{enc}', sep='{sep}', řádků={len(df) if df is not None else 0}).")
                        loaded_ok = True
                        break
                    except UnicodeDecodeError as ude: # <<< OPRAVA ZDE
                        logger.debug(f"Selhalo: UnicodeDecodeError s encoding='{enc}', sep='{sep}'")
                        last_exception = ude # <<< Uložíme původní výjimku
                        continue
                    except pd.errors.EmptyDataError:
                         logger.warning(f"Soubor '{os.path.basename(file_path)}' je prázdný nebo neobsahuje data.")
                         # Považujeme za "načteno", ale výsledek bude prázdný DF
                         df = pd.DataFrame() # Vytvoříme prázdný DF
                         loaded_ok = True
                         break # Ukončíme hledání
                    except Exception as read_err:
                        logger.warning(f"Selhalo: Jiná chyba při čtení CSV (encoding='{enc}', sep='{sep}'): {read_err}")
                        last_exception = read_err # <<< OPRAVA ZDE
                        continue
                if loaded_ok:
                    break

            if not loaded_ok:
                logger.error(f"Nepodařilo se načíst CSV soubor '{os.path.basename(file_path)}' s žádnou zkoušenou kombinací encoding/separator.")
                if last_exception: # <<< OPRAVA ZDE
                    raise last_exception # Vyvoláme poslední zachycenou chybu
                else:
                    # Pokud žádná výjimka nebyla zachycena (divné, ale může se stát)
                    raise ValueError("Nepodařilo se načíst CSV soubor (neznámá chyba).")

        elif file_extension in ['.xlsx', '.xls']:
            # --- Logika pro Excel ---
            logger.debug(f"Načítám Excel soubor (nrows={sample_rows or 'vše'})")
            try:
                df = pd.read_excel(
                    file_path,
                    nrows=sample_rows
                )
                logger.info(f"Excel soubor úspěšně načten (řádků={len(df) if df is not None else 0}).")
            except Exception as read_err:
                logger.error(f"Chyba při načítání Excel souboru: {read_err}", exc_info=True)
                raise read_err

        else:
            raise ValueError(f"Nepodporovaný formát souboru: {file_extension}")

        # Pokud se načtení podařilo a máme DataFrame (může být i prázdný z EmptyDataError)
        if df is not None:
            # Očistíme názvy sloupců, i když je DF prázdný (může mít sloupce)
            if not df.empty or len(df.columns) > 0:
                 df.columns = df.columns.map(lambda x: str(x).strip())
                 logger.debug(f"Načtené a očištěné sloupce: {list(df.columns)}")
            else:
                 logger.debug("Načten prázdný DataFrame bez sloupců.")
            return df
        else:
            logger.error("Načítání dat vrátilo None DataFrame i bez výjimky.")
            return None

    except FileNotFoundError:
        logger.error(f"Vstupní soubor nebyl nalezen: {file_path}")
        raise
    except Exception as e:
        # Zachytíme i chyby, které mohly být znovu vyvolány (např. UnicodeDecodeError)
        logger.error(f"Neočekávaná chyba při načítání dat ze souboru {file_path}: {e}", exc_info=True)
        raise

# KONEC SOUBORU data_loader.py