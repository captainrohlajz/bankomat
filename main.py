# main.py (Verze bez basicConfig na začátku)
import sys
import os
import logging # Importujeme logging, ale nekonfigurujeme zde
import traceback

# --- Přidání cesty k projektu do sys.path (pokud je potřeba) ---
project_root = os.path.dirname(os.path.abspath(__file__))
print(f"DEBUG (main.py): Project root directory: {project_root}")
if project_root not in sys.path:
    print(f"INFO (main.py): Přidávám do sys.path: {project_root}")
    sys.path.insert(0, project_root)
else:
    print(f"DEBUG (main.py): Cesta {project_root} již je v sys.path.")

# --- ZDE UŽ NENÍ BASICCONFIG ---
# logger = logging.getLogger(__name__) # Logger pro main získáme až po importu utils
print("DEBUG (main.py): Zahajuji importy...")

# --- Import GUI a vlastních modulů ---
try:
    # Importujeme utils jako první, aby se nastavilo detailní logování
    print("DEBUG (main.py): Pokus o import utils...")
    import utils # Toto by mělo nastavit logování
    print("DEBUG (main.py): Import utils OK.")

    # Nyní můžeme získat logger pro main
    logger = logging.getLogger(__name__)
    logger.info("Logování nastaveno modulem utils.") # Logovací zpráva po nastavení

    # Importujeme zbytek
    print("DEBUG (main.py): Pokus o import gui a dalších...")
    import gui
    import pandas
    import openpyxl
    import customtkinter
    import chardet
    print("DEBUG (main.py): Import gui a dalších OK.")

except ImportError as e:
    # ... (zbytek except ImportError bloku beze změny) ...
    # Zachytíme chybu importu zde, abychom mohli dát specifickou zprávu
    # logger.critical(...) # Logger zde ještě nemusí být správně nastaven
    print(f"\nFATÁLNÍ CHYBA: Nepodařilo se importovat modul: {e.name}")
    print(f"Traceback (pokud je k dispozici): {e.msg}") # Může obsahovat více info
    print("Ujistěte se, že všechny potřebné soubory (.py) a knihovny jsou správně nainstalovány a dostupné.")
    if e.name in ['pandas', 'openpyxl', 'customtkinter', 'chardet']:
         print("\nPravděpodobně chybí některá z požadovaných knihoven."); print("Zkuste spustit: pip install pandas openpyxl customtkinter chardet")
    elif e.name == 'utils':
         print(f"\nChyba při importu modulu 'utils'. Zkontrolujte 'utils.py' v '{project_root}'.")
    else:
         print(f"\nChyba při importu modulu '{e.name}'. Zkontrolujte projekt.")
    sys.exit(1)
except Exception as e:
     # ... (zbytek except Exception bloku beze změny) ...
     # logger.critical(...) # Logger zde ještě nemusí být správně nastaven
     print(f"\nFATÁLNÍ CHYBA při inicializaci nebo importu: {e}")
     traceback.print_exc() # Vypíšeme traceback na konzoli
     sys.exit(1)

# --- Hlavní spouštěcí blok ---
# ... (zbytek main.py beze změny) ...

except ImportError as e:
    # Zachytíme chybu importu zde, abychom mohli dát specifickou zprávu
    logger.critical(f"FATÁLNÍ CHYBA: Nepodařilo se importovat modul: {e.name}", exc_info=True)
    print(f"\nFATÁLNÍ CHYBA: Nepodařilo se importovat modul: {e.name}")
    print("Ujistěte se, že všechny potřebné soubory (.py) a knihovny jsou správně nainstalovány a dostupné.")
    # Dáme konkrétnější nápovědu pro běžné knihovny
    if e.name in ['pandas', 'openpyxl', 'customtkinter', 'chardet']:
         print("\nPravděpodobně chybí některá z požadovaných knihoven.")
         print("Zkuste spustit instalaci v terminálu:")
         print(f"pip install {e.name}") # Navrhneme instalaci konkrétní chybějící
         print("(nebo: pip install pandas openpyxl customtkinter chardet)")
    elif e.name == 'utils':
         print(f"\nChyba při importu modulu 'utils'. Zkontrolujte, zda soubor 'utils.py' existuje v adresáři '{project_root}' a neobsahuje syntaktické chyby.")
    else:
         print(f"\nChyba při importu modulu '{e.name}'. Zkontrolujte, zda máte všechny potřebné soubory projektu (gui.py, data_processor.py, atd.) ve stejném adresáři.")
    sys.exit(1) # Ukončíme aplikaci
except Exception as e:
     # Zachytíme jiné chyby během importů
     logger.critical(f"FATÁLNÍ CHYBA při inicializaci nebo importu: {e}", exc_info=True)
     print(f"\nFATÁLNÍ CHYBA při inicializaci: {e}")
     sys.exit(1)


# --- Hlavní spouštěcí blok ---
if __name__ == '__main__':
    # Kontrola knihoven zde už není nutná, protože proběhla úspěšně v `try` bloku výše.

    try:
        logger.info("Spouštím GUI aplikaci (App)...")
        app = gui.App() # Vytvoříme instanci aplikace z gui.py
        app.mainloop() # Spustíme hlavní smyčku Tkinter
        logger.info("GUI aplikace byla úspěšně ukončena.")
    except Exception as e:
        # Zachytíme případné neočekávané chyby během běhu GUI
        logger.critical(f"Došlo k neočekávané fatální chybě během běhu aplikace: {e}", exc_info=True)
        print(f"\nFATÁLNÍ CHYBA: {e}. Aplikace bude ukončena.")
        # Zkusíme zobrazit chybovou hlášku uživateli (pokud je to možné)
        try:
            # Potřebujeme importovat customtkinter a messagebox i zde pro zobrazení chyby
            import customtkinter as ctk
            from tkinter import messagebox
            root = ctk.CTk()
            root.withdraw() # Skryjeme prázdné okno
            messagebox.showerror("Fatální Chyba Aplikace", f"Došlo k neočekávané chybě:\n{e}\n\nAplikace bude ukončena. Zkontrolujte prosím log soubor (logs/app.log).")
            root.destroy()
        except Exception as e_msg:
             logger.error(f"Nepodařilo se zobrazit finální chybovou zprávu uživateli: {e_msg}")
             # Chyba už byla vypsána do konzole
        sys.exit(1) # Ukončíme aplikaci

    print("\nAplikace dokončila svou práci.")
    logger.info("Skript main.py dokončen.")

# --- Konec souboru main.py ---