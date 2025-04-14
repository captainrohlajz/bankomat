# gui.py (Kompletní verze s finálními úpravami statistik a layoutu)
# gui.py (Verze 2025-04-06 - Kompletní s Batch Processingem v hlavním vlákně)
import sys
import customtkinter as ctk
from tkinter import (filedialog, messagebox, Toplevel, Listbox, Scrollbar, Frame, Label, Button,
                     Entry, StringVar, W, E, END, SINGLE, MULTIPLE, ttk, Checkbutton, BooleanVar,
                     OptionMenu, Text, LEFT, RIGHT, BOTH, Y, X, TOP, BOTTOM, YES, NO, EXTENDED) # Přidáno EXTENDED
import os
import threading
from datetime import datetime
import pandas as pd
import json
import time
import traceback
import uuid # Pro GUI ID pravidel
import re # Pro extrakci mapování
import logging # Standardní import
from queue import Queue # Přidáno pro synchronizaci dialogu metadat ve vlákně (pokud bychom se k tomu vraceli)

# Importujeme naše moduly
import config_manager # Importujeme celý modul
import data_loader
import data_processor
import data_exporter
# Importujeme vlastní výjimky z utils
from utils import ProcessingError, ConfigError, DataError

# --- Konfigurace loggeru ---
logger = logging.getLogger(__name__) # Standardní logger

# --- Globální Konstanty a Nastavení ---
SETTINGS_FILE = "app_settings.json" # Název souboru s nastavením

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Konstanty odkazující na data_processor (pro přehlednost)
ALL_TARGET_COLUMNS = data_processor.FINAL_COLUMN_ORDER
UNKNOWN_TRANSACTION_TYPE = data_processor.UNKNOWN_TRANSACTION_TYPE

# Cílové sloupce specificky pro mapování v GUI
TARGET_COLUMNS_FOR_MAPPING = sorted([
    col for col in ALL_TARGET_COLUMNS if col not in [
        'UCET_CISLO', 'UCET_NAZEV', 'DISPONENT1', 'DISPONENT2', 'DISPONENT3', 'MENA',
        'PROTIUCET', 'PROTIUCET+NAZEV', 'ZDROJ', 'TYP TRANSAKCE'
    ]
])

# Konstanty pro barvy (mohou být i v nastavení motivu)
MAPPED_ITEM_COLOR = "#404E67"
UNMAPPED_ITEM_COLOR = "#2B2B2B"

# Konstanty importované z config_manager pro pravidla a dialogy
try:
    TRANSACTION_RULE_CONDITIONS_MAP = config_manager.TRANSACTION_RULE_CONDITIONS_MAP
    TRANSACTION_RULE_CONDITIONS_KEYS = config_manager.TRANSACTION_RULE_CONDITIONS_KEYS
    TRANSACTION_RULE_DISPLAY_NAMES = config_manager.TRANSACTION_RULE_DISPLAY_NAMES
    POTENTIAL_SEARCH_COLUMNS = sorted(list(set(TARGET_COLUMNS_FOR_MAPPING + ALL_TARGET_COLUMNS))) # Kombinace pro výběr
    DEFAULT_SEARCH_COLUMNS = config_manager.SEARCHABLE_COLUMNS
    DEFAULT_TRANSACTION_TYPES = config_manager.DEFAULT_TRANSACTION_TYPES
    CONDITIONS_WITHOUT_KEYWORDS = config_manager.CONDITIONS_WITHOUT_KEYWORDS # <<< PŘIDÁNO ZDE
except AttributeError as e_attr:
     logger.error(f"Chyba: Nepodařilo se načíst konstanty z config_manager.py: {e_attr}")
     # Nastavení nouzových hodnot, pokud config_manager není dostupný nebo nemá konstanty
     TRANSACTION_RULE_CONDITIONS_MAP = {"Obsahuje": "contains"}
     TRANSACTION_RULE_CONDITIONS_KEYS = ["contains"]
     TRANSACTION_RULE_DISPLAY_NAMES = ["Obsahuje"]
     POTENTIAL_SEARCH_COLUMNS = TARGET_COLUMNS_FOR_MAPPING
     DEFAULT_SEARCH_COLUMNS = ["POPIS"]
     DEFAULT_TRANSACTION_TYPES = ["Neznámý"]
     CONDITIONS_WITHOUT_KEYWORDS = {"notempty", "isempty", "isnumber", "ispositive", "isnegative"} # Manuální fallback

# --- Definice Tříd (MetadataDialog, AddRuleDialog, App, ConfigManagerWindow) ---

# ... (kód třídy MetadataDialog) ...
# ... (kód třídy AddRuleDialog - včetně upravené on_ok) ...
# ... (kód třídy App - včetně upravených metod) ...
# ... (kód třídy ConfigManagerWindow) ...
# ... (blok if __name__ == '__main__':) ...

# --- Třída MetadataDialog ---
# (Beze změny - z předchozích verzí)
# gui.py

# ... (importy a konstanty na začátku souboru) ...

# --- Třída MetadataDialog (s checkboxem "Použít pro všechny" - KONTROLA) ---
class MetadataDialog(ctk.CTkToplevel):
    def __init__(self, master, filename, is_batch=False, current_file_num=0, total_files=0):
        """
        Inicializuje dialog pro zadání metadat.
        is_batch: True, pokud jde o dávkové zpracování.
        current_file_num, total_files: Pro zobrazení informace v titulku při batchi.
        """
        super().__init__(master)
        self.master_app = master

        title_prefix = f"[{current_file_num}/{total_files}] " if is_batch and total_files > 1 else ""
        self.title(f"{title_prefix}Zadat Metadata pro: {os.path.basename(filename)}")
        self.geometry("450x350")
        self.resizable(False, False)
        self.lift(); self.attributes("-topmost", True); self.grab_set()

        # --- Inicializace atributů ---
        self.metadata_result = None # Výsledek: slovník metadat
        self.apply_to_all = False   # Výsledek: stav checkboxu
        self.metadata_vars = {}   # Pro Entry widgety
        self.apply_to_all_var = BooleanVar(value=False) # Proměnná pro Checkbox!
        # --- Konec inicializace ---

        ctk.CTkLabel(self, text="Zadejte info o účtu:", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 15))
        main_frame = ctk.CTkFrame(self, fg_color="transparent"); main_frame.pack(fill=X, padx=20)
        meta_fields = ["account_number", "account_name", "currency", "disponent1", "disponent2", "disponent3"]
        labels = ["Číslo účtu*", "Název účtu", "Měna (CZK)*", "Disponent 1", "Disponent 2", "Disponent 3"]
        req_fields = ["account_number", "currency"]
        first_entry = None

        for i, field in enumerate(meta_fields):
            fr = ctk.CTkFrame(main_frame, fg_color="transparent"); fr.pack(fill=X, pady=3)
            ctk.CTkLabel(fr, text=labels[i] + ":", width=120, anchor="w").pack(side=LEFT, padx=(0, 5))
            var = StringVar(); self.metadata_vars[field] = var
            entry = ctk.CTkEntry(fr, textvariable=var, width=250); entry.pack(side=LEFT, fill=X, expand=True)
            if i == 0: first_entry = entry
            if field == "currency": var.set("CZK")

        if first_entry: first_entry.focus_set()

        # Zobrazíme checkbox jen pokud je to batch a je více než 1 soubor
        self.show_checkbox = is_batch and (total_files > 1)
        if self.show_checkbox:
            checkbox_frame = ctk.CTkFrame(self, fg_color="transparent")
            checkbox_frame.pack(pady=(15, 0), padx=20, anchor="w")
            # Ujistěte se, že je CheckBox správně propojen s self.apply_to_all_var
            self.apply_all_checkbox = ctk.CTkCheckBox(
                checkbox_frame,
                text="Použít tato metadata i pro všechny následující soubory",
                variable=self.apply_to_all_var, # <<< SPRÁVNÉ PROPOJENÍ
                onvalue=True, offvalue=False
            )
            self.apply_all_checkbox.pack(anchor="w")
        else:
             # Pokud checkbox není zobrazen, nastavíme proměnnou explicitně na False
             self.apply_to_all_var.set(False)


        btn_frame = ctk.CTkFrame(self, fg_color="transparent"); btn_frame.pack(pady=(15, 10))
        ctk.CTkButton(btn_frame, text="OK", command=self.on_ok, width=100).pack(side=LEFT, padx=10)
        ctk.CTkButton(btn_frame, text="Storno", command=self.on_cancel, width=100, fg_color="gray").pack(side=LEFT, padx=10)
        self.bind("<Return>", lambda event: self.on_ok())

    def on_ok(self):
        """Zvaliduje vstup, uloží výsledek (včetně stavu checkboxu) a zavře dialog."""
        result = {}; missing = []
        req_fields_map = {"account_number": "Číslo účtu", "currency": "Měna"}
        for field, var in self.metadata_vars.items():
            value = var.get().strip(); result[field] = value
            if field in req_fields_map and not value: missing.append(req_fields_map[field])

        if missing:
            messagebox.showerror("Chybí Povinná Pole", f"Prosím, vyplňte:\n- {', '.join(missing)}", parent=self)
            return

        # Uložíme metadata a stav checkboxu do atributů instance
        self.metadata_result = result
        # Čteme hodnotu z BooleanVar spojené s checkboxem
        self.apply_to_all = self.apply_to_all_var.get()

        log_suffix = " (a pro další)" if self.apply_to_all else ""
        try: self.master_app.log_message(f"INFO: Metadata úspěšně zadána{log_suffix}.")
        except AttributeError: pass
        # Zavřeme okno až po uložení hodnot
        self.destroy()

    def on_cancel(self):
        """Zavře dialog bez uložení výsledku."""
        self.metadata_result = None
        self.apply_to_all = False # Explicitně nastavíme False
        try: self.master_app.log_message("INFO: Zadávání metadat zrušeno.")
        except AttributeError: pass
        self.destroy()

    def get_metadata(self):
        """Počká na zavření dialogu a vrátí uložené výsledky."""
        self.wait_window()
        # Vrátíme n-tici s uloženými hodnotami atributů
        logger.debug(f"MetadataDialog.get_metadata vrací: ({'slovník' if self.metadata_result else 'None'}, {self.apply_to_all})")
        return (self.metadata_result, self.apply_to_all)

# --- KONEC TŘÍDY MetadataDialog ---# --- Třída AddRuleDialog ---
# (Beze změny - z předchozích verzí)
class AddRuleDialog(ctk.CTkToplevel):
    # UVNITŘ TŘÍDY AddRuleDialog(ctk.CTkToplevel):

    # Opravený __init__ s aktualizovanými hodnotami pro OptionMenu
    def __init__(self, master, existing_types, searchable_columns_list, is_ignore_rule=False, rule_data=None):
        super().__init__(master)
        self.calling_window = master; self.is_ignore_rule = is_ignore_rule
        self.is_edit_mode = rule_data is not None; self.rule_data_in = rule_data if rule_data else {}
        dialog_title = "Upravit" if self.is_edit_mode else "Přidat"; dialog_title += " Pravidlo Ignorování" if is_ignore_rule else " Pravidlo Typu Transakce"; self.title(dialog_title)
        self.resizable(True, True); self.lift(); self.attributes("-topmost", True); self.grab_set(); self.minsize(550, 550)

        self.rule_result = None
        self.initial_existing_types = list(existing_types)
        self.current_available_types = sorted(list(set(DEFAULT_TRANSACTION_TYPES + self.initial_existing_types)))
        self.searchable_columns = searchable_columns_list

        initial_type = self.rule_data_in.get("type", "")
        initial_search_in = self.rule_data_in.get("search_in", DEFAULT_SEARCH_COLUMNS if not self.is_edit_mode else [])
        conditions_in = self.rule_data_in.get("conditions", {}) if isinstance(self.rule_data_in.get("conditions"), dict) else {}
        cond_keys = list(conditions_in.keys())
        initial_condition_key_1 = cond_keys[0] if len(cond_keys) > 0 else "contains"
        initial_keywords_1 = conditions_in.get(initial_condition_key_1, [])
        initial_condition_key_2 = cond_keys[1] if len(cond_keys) > 1 else "contains"
        initial_keywords_2 = conditions_in.get(initial_condition_key_2, []) if len(cond_keys) > 1 else []

        self.trans_type_var = StringVar(value=initial_type)
        # Nastavíme proměnné pro OptionMenu
        self.condition_var_1 = StringVar(value=self._get_display_condition(initial_condition_key_1))
        self.condition_var_2 = StringVar(value=self._get_display_condition(initial_condition_key_2))
        self.search_cols_vars = {}

        # --- GUI ---
        main_frame = ctk.CTkFrame(self, fg_color="transparent"); main_frame.pack(padx=15, pady=15, fill=BOTH, expand=True); main_frame.grid_columnconfigure(1, weight=1); current_row = 0

        # Typ Transakce (Readonly)
        if not self.is_ignore_rule:
            type_frame = ctk.CTkFrame(main_frame, fg_color="transparent"); type_frame.grid(row=current_row, column=0, columnspan=2, padx=5, pady=5, sticky=W+E);
            ctk.CTkLabel(type_frame, text="Typ Transakce:", width=130, anchor="w").pack(side=LEFT)
            self.type_combobox = ctk.CTkComboBox(type_frame, values=self.current_available_types, variable=self.trans_type_var, state="readonly"); self.type_combobox.pack(side=LEFT, fill=X, expand=True, padx=(0, 5))
            if initial_type in self.current_available_types: self.type_combobox.set(initial_type)
            elif self.current_available_types: self.type_combobox.set(self.current_available_types[0])
            else: self.type_combobox.set("")
            current_row += 1

        # --- Podmínka 1 ---
        ctk.CTkLabel(main_frame, text="Podmínka 1:", font=ctk.CTkFont(weight="bold")).grid(row=current_row, column=0, columnspan=2, padx=5, pady=(10, 0), sticky=W); current_row += 1
        cond_frame_1 = ctk.CTkFrame(main_frame, fg_color="transparent"); cond_frame_1.grid(row=current_row, column=0, columnspan=2, padx=5, pady=2, sticky=W+E);
        ctk.CTkLabel(cond_frame_1, text="Podmínka:", width=130, anchor="w").pack(side=LEFT)
        # Použijeme aktuální TRANSACTION_RULE_DISPLAY_NAMES, které už obsahují nové podmínky
        self.cond_optionmenu_1 = ctk.CTkOptionMenu(cond_frame_1, variable=self.condition_var_1, values=TRANSACTION_RULE_DISPLAY_NAMES, width=150, command=self._on_condition_change) # <<< Přidán command
        self.cond_optionmenu_1.pack(side=LEFT); current_row += 1

        kw_frame_1 = ctk.CTkFrame(main_frame, fg_color="transparent"); kw_frame_1.grid(row=current_row, column=0, columnspan=2, padx=5, pady=2, sticky=W+E);
        self.kw_label_1 = ctk.CTkLabel(kw_frame_1, text="Klíčová slova 1\n(oddělená čárkou):", width=130, anchor="nw"); self.kw_label_1.pack(side=LEFT, pady=(0,5))
        self.keywords_text_1 = ctk.CTkTextbox(kw_frame_1, height=40); self.keywords_text_1.pack(side=LEFT, fill=X, expand=True);
        if isinstance(initial_keywords_1, list): self.keywords_text_1.insert("1.0", ", ".join(map(str, initial_keywords_1)))
        current_row += 1

        # --- Podmínka 2 ---
        ctk.CTkLabel(main_frame, text="Podmínka 2 (nepovinná):", font=ctk.CTkFont(weight="bold")).grid(row=current_row, column=0, columnspan=2, padx=5, pady=(10, 0), sticky=W); current_row += 1
        cond_frame_2 = ctk.CTkFrame(main_frame, fg_color="transparent"); cond_frame_2.grid(row=current_row, column=0, columnspan=2, padx=5, pady=2, sticky=W+E);
        ctk.CTkLabel(cond_frame_2, text="Podmínka:", width=130, anchor="w").pack(side=LEFT)
        self.cond_optionmenu_2 = ctk.CTkOptionMenu(cond_frame_2, variable=self.condition_var_2, values=TRANSACTION_RULE_DISPLAY_NAMES, width=150, command=self._on_condition_change) # <<< Přidán command
        self.cond_optionmenu_2.pack(side=LEFT); current_row += 1
        kw_frame_2 = ctk.CTkFrame(main_frame, fg_color="transparent"); kw_frame_2.grid(row=current_row, column=0, columnspan=2, padx=5, pady=2, sticky=W+E);
        self.kw_label_2 = ctk.CTkLabel(kw_frame_2, text="Klíčová slova 2\n(oddělená čárkou):", width=130, anchor="nw"); self.kw_label_2.pack(side=LEFT, pady=(0,5))
        self.keywords_text_2 = ctk.CTkTextbox(kw_frame_2, height=40); self.keywords_text_2.pack(side=LEFT, fill=X, expand=True);
        if isinstance(initial_keywords_2, list): self.keywords_text_2.insert("1.0", ", ".join(map(str, initial_keywords_2)))
        current_row += 1

        # --- Hledat ve sloupcích ---
        # ... (kód pro sloupce beze změny) ...
        cols_frame = ctk.CTkFrame(main_frame); cols_frame.grid(row=current_row, column=0, columnspan=2, padx=5, pady=(15, 10), sticky=W+E);
        ctk.CTkLabel(cols_frame, text="Hledat ve sloupcích (platí pro obě podmínky):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=5); cols_scroll_frame = ctk.CTkScrollableFrame(cols_frame, height=100, fg_color="transparent"); cols_scroll_frame.pack(fill=X, padx=5);
        selected_cols = set(initial_search_in); r, c, MCOLS = 0, 0, 3
        for col_name in self.searchable_columns:
            var = ctk.BooleanVar(value=(col_name in selected_cols)); self.search_cols_vars[col_name] = var; cb = ctk.CTkCheckBox(cols_scroll_frame, text=col_name, variable=var); cb.grid(row=r, column=c, padx=5, pady=2, sticky=W); c += 1;
            if c >= MCOLS: c = 0; r += 1
        current_row += 1

        # Tlačítka OK/Storno
        # ... (kód pro tlačítka beze změny) ...
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent"); button_frame.grid(row=current_row, column=0, columnspan=2, pady=(15, 10));
        ok_text = "Uložit Pravidlo"; ok_button = ctk.CTkButton(button_frame, text=ok_text, command=self.on_ok, width=120); ok_button.pack(side=LEFT, padx=10); cancel_button = ctk.CTkButton(button_frame, text="Storno", command=self.on_cancel, width=100, fg_color="gray"); cancel_button.pack(side=LEFT, padx=10)

        # Zavoláme kontrolu stavu keyword polí na začátku
        self._on_condition_change()

    # --- Metoda on_ok (upravená validace klíčových slov) ---
    def on_ok(self):
        trans_type = self.trans_type_var.get().strip() if not self.is_ignore_rule else None
        search_cols = [col for col, var in self.search_cols_vars.items() if var.get()]
        conditions = {}

        # Podmínka 1
        condition_display_1 = self.condition_var_1.get()
        condition_key_1 = self._get_internal_condition(condition_display_1)
        keywords_raw_1 = self.keywords_text_1.get("1.0", END).strip()
        keywords_1 = [kw.strip() for kw in keywords_raw_1.split(',') if kw.strip()]
        # Validace pro podmínku 1
        # Musí mít klíčová slova, POKUD to není podmínka bez klíčových slov
        if not keywords_1 and condition_key_1 not in config_manager.CONDITIONS_WITHOUT_KEYWORDS:
             messagebox.showerror("Chyba Validace", f"Podmínka 1 ('{condition_display_1}') vyžaduje zadání klíčových slov.", parent=self); return
        # Pokud podmínka nevyžaduje klíčová slova, uložíme prázdný seznam (nebo null?) - pro konzistenci prázdný seznam
        conditions[condition_key_1] = keywords_1 if condition_key_1 not in config_manager.CONDITIONS_WITHOUT_KEYWORDS else []

        # Podmínka 2 (jen pokud je vyplněna)
        condition_display_2 = self.condition_var_2.get()
        condition_key_2 = self._get_internal_condition(condition_display_2)
        keywords_raw_2 = self.keywords_text_2.get("1.0", END).strip()
        keywords_2 = [kw.strip() for kw in keywords_raw_2.split(',') if kw.strip()]
        # Zpracujeme, jen pokud byla zadána nějaká klíčová slova pro druhou podmínku
        if keywords_raw_2:
            # Validace pro podmínku 2
            if not keywords_2 and condition_key_2 not in config_manager.CONDITIONS_WITHOUT_KEYWORDS:
                 messagebox.showerror("Chyba Validace", f"Podmínka 2 ('{condition_display_2}') vyžaduje platná klíčová slova, pokud je použita.", parent=self); return
            # Kontrola duplicity klíče podmínky
            if condition_key_2 in conditions:
                 messagebox.showwarning("Varování", f"Podmínka '{condition_display_2}' je zadána vícekrát. Druhá instance bude ignorována.", parent=self)
            else:
                 conditions[condition_key_2] = keywords_2 if condition_key_2 not in config_manager.CONDITIONS_WITHOUT_KEYWORDS else []

        # Finální validace
        if not self.is_ignore_rule and not trans_type: messagebox.showerror("Chyba Validace", "Zadejte Typ transakce.", parent=self); return
        if not search_cols: messagebox.showerror("Chyba Validace", "Vyberte Sloupec pro hledání.", parent=self); return
        if not conditions: messagebox.showerror("Chyba Validace", "Definujte alespoň jednu platnou podmínku.", parent=self); return

        # Sestavení výsledku
        self.rule_result = {"search_in": search_cols, "conditions": conditions}
        if not self.is_ignore_rule: self.rule_result["type"] = trans_type
        if self.is_edit_mode and "_id" in self.rule_data_in: self.rule_result["_id"] = self.rule_data_in["_id"]

        logger.info(f"AddRuleDialog on_ok: Vytvořeno/upraveno pravidlo: {self.rule_result}")
        self.destroy()

    # <<< NOVÁ METODA pro změnu stavu keyword polí >>>
    def _on_condition_change(self, *args):
        """Volá se při změně hodnoty v OptionMenu podmínky.
           Zakáže/povolí a vymaže pole pro klíčová slova, pokud je nepotřebuje."""
        # Podmínka 1
        cond1_key = self._get_internal_condition(self.condition_var_1.get())
        kw1_state = "disabled" if cond1_key in config_manager.CONDITIONS_WITHOUT_KEYWORDS else "normal"
        # Nastavíme stav a případně vymažeme obsah
        self.keywords_text_1.configure(state=kw1_state)
        self.kw_label_1.configure(text_color=("gray60" if kw1_state == "disabled" else ctk.ThemeManager.theme["CTkLabel"]["text_color"]))
        if kw1_state == "disabled":
            self.keywords_text_1.delete("1.0", END)

        # Podmínka 2
        cond2_key = self._get_internal_condition(self.condition_var_2.get())
        kw2_state = "disabled" if cond2_key in config_manager.CONDITIONS_WITHOUT_KEYWORDS else "normal"
        self.keywords_text_2.configure(state=kw2_state)
        self.kw_label_2.configure(text_color=("gray60" if kw2_state == "disabled" else ctk.ThemeManager.theme["CTkLabel"]["text_color"]))
        if kw2_state == "disabled":
            self.keywords_text_2.delete("1.0", END)

    # ... (metody _get_internal_condition, _get_display_condition, on_cancel, get_rule_data zůstávají) ...

# KONEC TŘÍDY AddRuleDialog
    # --- Pomocné metody pro podmínky ---
    def _get_internal_condition(self, display_name):
        return TRANSACTION_RULE_CONDITIONS_MAP.get(display_name, "contains") # Default

    def _get_display_condition(self, internal_key):
        for disp, intern in TRANSACTION_RULE_CONDITIONS_MAP.items():
            if intern == internal_key:
                return disp
        return "Obsahuje" # Default

    # --- Metody tlačítek ---
    # UVNITŘ TŘÍDY AddRuleDialog(ctk.CTkToplevel):

    # Opravená metoda on_ok - správná validace pro podmínky bez klíčových slov
    def on_ok(self):
        trans_type = self.trans_type_var.get().strip() if not self.is_ignore_rule else None
        search_cols = [col for col, var in self.search_cols_vars.items() if var.get()]
        conditions = {} # Výsledný slovník {podmínka_klic: keywords_list}

        # --- Zpracování a validace Podmínky 1 ---
        condition_display_1 = self.condition_var_1.get()
        condition_key_1 = self._get_internal_condition(condition_display_1)
        keywords_raw_1 = self.keywords_text_1.get("1.0", END).strip()
        keywords_1 = [kw.strip() for kw in keywords_raw_1.split(',') if kw.strip()]

        # Podmínka 1 je platná, pokud:
        # a) Je to typ podmínky bez klíčových slov NEBO
        # b) Je to typ podmínky s klíčovými slovy A klíčová slova jsou zadána (nebo je to necontains/neendswith)
        is_cond1_valid = False
        if condition_key_1 in config_manager.CONDITIONS_WITHOUT_KEYWORDS:
            conditions[condition_key_1] = [] # Uložíme prázdný seznam
            is_cond1_valid = True
        elif keywords_1 or condition_key_1 in ["necontains", "neendswith"]:
            conditions[condition_key_1] = keywords_1
            is_cond1_valid = True
        else:
             # Pokud to NENÍ podmínka bez klíč. slov A keywords_1 jsou prázdné (a není to necontains/neendswith) -> chyba
             messagebox.showerror("Chyba Validace", f"Podmínka 1 ('{condition_display_1}') vyžaduje zadání klíčových slov.", parent=self); return

        # --- Zpracování a validace Podmínky 2 (jen pokud jsou zadána klíčová slova) ---
        condition_display_2 = self.condition_var_2.get()
        condition_key_2 = self._get_internal_condition(condition_display_2)
        keywords_raw_2 = self.keywords_text_2.get("1.0", END).strip()
        keywords_2 = [kw.strip() for kw in keywords_raw_2.split(',') if kw.strip()]

        # Podmínku 2 přidáme, POUZE pokud pro ni byla zadána klíčová slova NEBO je to typ bez klíč. slov
        is_cond2_to_add = bool(keywords_raw_2) or (condition_key_2 in config_manager.CONDITIONS_WITHOUT_KEYWORDS)
        if is_cond2_to_add:
            is_cond2_valid = False
            if condition_key_2 in config_manager.CONDITIONS_WITHOUT_KEYWORDS:
                 is_cond2_valid = True
            elif keywords_2 or condition_key_2 in ["necontains", "neendswith"]:
                 is_cond2_valid = True
            else:
                  messagebox.showerror("Chyba Validace", f"Podmínka 2 ('{condition_display_2}') vyžaduje platná klíčová slova, pokud je pro ni aktivní pole.", parent=self); return

            if is_cond2_valid:
                # Kontrola duplicity klíče podmínky
                if condition_key_2 in conditions:
                     messagebox.showwarning("Varování", f"Podmínka '{condition_display_2}' je zadána vícekrát. Druhá instance bude ignorována.", parent=self)
                else:
                     conditions[condition_key_2] = [] if condition_key_2 in config_manager.CONDITIONS_WITHOUT_KEYWORDS else keywords_2


        # --- Finální validace ---
        if not self.is_ignore_rule and not trans_type:
            messagebox.showerror("Chyba Validace", "Zadejte Typ transakce.", parent=self); return
        if not search_cols:
            messagebox.showerror("Chyba Validace", "Vyberte alespoň jeden Sloupec pro hledání.", parent=self); return
        if not conditions: # Musí být definována alespoň jedna podmínka
            messagebox.showerror("Chyba Validace", "Definujte alespoň jednu platnou podmínku.", parent=self); return

        # --- Sestavení výsledku ---
        self.rule_result = {"search_in": search_cols, "conditions": conditions}
        if not self.is_ignore_rule: self.rule_result["type"] = trans_type
        if self.is_edit_mode and "_id" in self.rule_data_in: self.rule_result["_id"] = self.rule_data_in["_id"]

        logger.info(f"AddRuleDialog on_ok: Vytvořeno/upraveno pravidlo: {self.rule_result}")
        self.destroy()

# KONEC METODY on_ok v AddRuleDialog
    def on_cancel(self):
        self.rule_result = None # Nevracíme nic
        self.destroy() # Zavřeme dialog

    def get_rule_data(self):
        self.wait_window() # Počkáme na zavření dialogu
        return self.rule_result # Vrátíme výsledek (data nebo None)

# --- Třída App (Hlavní aplikace) ---
class App(ctk.CTk):
    # --- Metoda __init__ ---
    # (Nová verze s grid layoutem a novým labelem)
    # UVNITŘ TŘÍDY App(ctk.CTk):

    # UVNITŘ TŘÍDY App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Zpracování Bankovních Výpisů")
        self.geometry("1100x750")
        self.minsize(900, 650)

        # --- Inicializace proměnných ---
        self.last_import_dir = "."
        self.last_export_dir = "."
        self.last_config_dir = config_manager.CONFIGS_DIR
        self.load_app_settings() # Načteme uložené cesty

        self.selected_file_paths = [] # Seznam cest k vybraným souborům
        self.processing_thread = None # Pro budoucí použití nebo odstranění
        self.config_window = None
        self.batch_results = []       # Seznam výsledků pro batch {original_filename, dataframe}
        self.file_info_widgets = {}   # Slovník pro widgety kartiček {filepath: {'frame':..., 'status_label':...}}
        self.file_checkbox_vars = {}  # <<< NOVÝ SLOVNÍK pro proměnné checkboxů {filepath: BooleanVar} >>>

        # --- Horní Frame (Import a Správa) ---
        # ... (zbytek __init__ zůstává stejný jako v poslední funkční verzi) ...
        # --- Horní Frame (Import a Správa) ---
        self.frame_top = ctk.CTkFrame(self)
        self.frame_top.pack(pady=(10,0), padx=10, fill=X)
        self.frame_top.grid_columnconfigure(0, weight=0) # Import Soubory
        # self.frame_top.grid_columnconfigure(1, weight=0) # Import Adresář (odstraněno)
        self.frame_top.grid_columnconfigure(1, weight=1) # Počet souborů (roztáhne se)
        self.frame_top.grid_columnconfigure(2, weight=0) # Konfigy

        self.button_import = ctk.CTkButton(self.frame_top, text="1. Importovat soubor(y)", command=self.select_files)
        self.button_import.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="w")
        self.label_file_count = ctk.CTkLabel(self.frame_top, text="Nebyly vybrány žádné soubory", anchor="w")
        self.label_file_count.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.button_manage_configs = ctk.CTkButton(self.frame_top, text="Správa Konfigurací", width=150, command=self.open_config_manager_window)
        self.button_manage_configs.grid(row=0, column=2, padx=(10, 0), pady=5, sticky="e")

        # --- Frame pro seznam souborů s detaily ---
        ctk.CTkLabel(self, text="Vybrané soubory:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(pady=(5,0), padx=10, fill=X)
        self.files_info_frame = ctk.CTkScrollableFrame(self, height=150) # Scrollable frame pro "kartičky"
        self.files_info_frame.pack(pady=5, padx=10, fill=BOTH, expand=True) # Roztáhne se

        # --- Prostřední Frame (Zpracování) ---
        self.frame_middle = ctk.CTkFrame(self)
        self.frame_middle.pack(pady=5, padx=10, fill=X)
        self.button_process = ctk.CTkButton(self.frame_middle, text="2. Zpracovat vybrané soubory", command=self.start_processing, state="disabled")
        self.button_process.pack(side=LEFT, padx=(0, 10))
        # Tlačítko Spočítat Typy bylo odstraněno
        self.progressbar = ctk.CTkProgressBar(self.frame_middle, orientation="horizontal"); self.progressbar.set(0)
        self.progressbar.pack(side=LEFT, fill=X, expand=True, padx=5)

        # --- Frame pro Ukládání (přidáno CSV s tečkou) ---
        self.frame_save = ctk.CTkFrame(self)
        self.frame_save.pack(pady=(5, 10), padx=10, fill=X)
        ctk.CTkLabel(self.frame_save, text="3. Uložit výsledky do adresáře jako:").pack(side=LEFT, padx=5)

        # Tlačítko CSV (s čárkou - původní)
        self.button_save_csv = ctk.CTkButton(self.frame_save, text="CSV (,)", command=lambda: self.save_batch_results(format_type='csv', decimal_separator=','), state="disabled", width=90) # Upraven text a přidán parametr
        self.button_save_csv.pack(side=LEFT, padx=5)

        # <<< NOVÉ TLAČÍTKO CSV (s tečkou) >>>
        self.button_save_csv_dot = ctk.CTkButton(self.frame_save, text="CSV (.)", command=lambda: self.save_batch_results(format_type='csv', decimal_separator='.'), state="disabled", width=90)
        self.button_save_csv_dot.pack(side=LEFT, padx=5)
        # <<< KONEC NOVÉHO TLAČÍTKA >>>

        # Tlačítko XLSX
        self.button_save_xlsx = ctk.CTkButton(self.frame_save, text="XLSX", command=lambda: self.save_batch_results(format_type='xlsx'), state="disabled", width=80) # Odstraněn dec. sep.
        self.button_save_xlsx.pack(side=LEFT, padx=5)
        # --- Frame pro informace o PRŮBĚHU ZPRACOVÁNÍ ---
        self.info_frame = ctk.CTkFrame(self)
        self.info_frame.pack(pady=(0,5), padx=10, fill=X)
        self.info_frame.grid_columnconfigure(0, weight=1) # Info label
        # Ponecháme jen jeden label pro info o průběhu
        self.label_progress_info = ctk.CTkLabel(self.info_frame, text="", anchor="w")
        self.label_progress_info.grid(row=0, column=0, padx=5, sticky="ew")
        # Staré labely row_count a transaction_stats už zde nepotřebujeme

        # --- Spodní Frame (Log) ---
        self.frame_bottom = ctk.CTkFrame(self)
        self.frame_bottom.pack(pady=(0, 10), padx=10, fill=BOTH, expand=True) # Roztáhne se vertikálně
        self.textbox_log = ctk.CTkTextbox(self.frame_bottom, wrap="word", state="disabled", font=("Consolas", 11))
        self.textbox_log.pack(fill=BOTH, expand=True)

        self.log_message("INFO: Aplikace spuštěna.")
        logger.info("GUI aplikace spuštěna.")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

# KONEC METODY __init__
        

    # --- Ostatní metody třídy App ---
    def log_message(self, message):
        """Zobrazí zprávu v logovacím textboxu."""
        try:
            self.textbox_log.configure(state="normal") # Povolit zápis
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}\n"
            self.textbox_log.insert("end", formatted_message)
            self.textbox_log.see("end") # Scroll dolů
            self.textbox_log.configure(state="disabled") # Znovu zakázat zápis
        except Exception as e:
            # Fallback pro případ chyby v GUI logování
            print(f"CHYBA ZÁPISU DO GUI LOGU: {e}")
            logger.error(f"Chyba zápisu do GUI logu: {e}", exc_info=True)

# UVNITŘ TŘÍDY App(ctk.CTk):

    # def calculate_full_stats_action(self):
    #     """Spustí výpočet statistik z celého souboru ve vlákně."""
    #     if not self.selected_file_path or not self.identified_config_path:
    #         messagebox.showwarning("Chybí vstup", "Nejprve vyberte soubor a musí být nalezena konfigurace.", parent=self)
    #         return
    #     # Zkontrolujeme, zda už neběží jiné vlákno (zpracování nebo výpočet statistik)
    #     if (self.processing_thread and self.processing_thread.is_alive()) or \
    #        (hasattr(self, 'stats_thread') and self.stats_thread and self.stats_thread.is_alive()):
    #          messagebox.showwarning("Obsazeno", "Počkejte na dokončení předchozí operace (zpracování nebo výpočet statistik).", parent=self)
    #          return

    #     # Zakázat relevantní tlačítka
    #     self.button_import.configure(state="disabled")
    #     self.button_process.configure(state="disabled")
    #     self.button_calc_stats.configure(state="disabled") # Zakážeme i sebe
    #     self.button_manage_configs.configure(state="disabled")

    #     # Spustit progress bar
    #     self.progressbar.configure(mode="indeterminate")
    #     self.progressbar.start()
    #     self.label_transaction_stats.configure(text="Statistika: Počítám (celkem)...")
    #     self.log_message("INFO: Spouštím výpočet statistik z celého souboru...")

    #     # Spuštění výpočtu v samostatném vlákně
    #     self.stats_thread = threading.Thread(
    #         target=self._calculate_full_stats_logic,
    #         args=(self.selected_file_path, self.identified_config_path),
    #         daemon=True
    #     )
    #     self.stats_thread.start()
    #     # Pravidelně kontrolujeme stav vlákna statistik
    #     self.after(100, self.check_stats_thread)

        # UVNITŘ TŘÍDY App(ctk.CTk):
# UVNITŘ TŘÍDY App(ctk.CTk):

    # UVNITŘ TŘÍDY App(ctk.CTk):

   # UVNITŘ TŘÍDY App(ctk.CTk):

    # Metoda _get_file_info - Verze s oranžovou pro chybu konfigu/dat
    def _get_file_info(self, file_path):
        """Zkusí získat informace pro soubor. Chyby konfigu/dat značí oranžově."""
        info = { "filename": os.path.basename(file_path), "config_name": "N/A", "config_path": None,
                 "row_count": "N/A", "stats_known": "N/A", "stats_unknown": "",
                 "error": None, "config_color": "gray", "is_valid": False }
        SAMPLE_SIZE = 200
        config_data = None
        config_name_found = "N/A" # Pomocná proměnná

        try:
            # 1. Identifikace konfigurace
            logger.debug(f"_get_file_info: Identifikuji konfig pro {info['filename']}")
            config_path = config_manager.identify_config_for_file(file_path, config_manager.CONFIGS_DIR)
            if not config_path:
                info["config_name"] = "NENALEZENO"; info["config_color"] = "red"; info["error"] = "Konfigurace nenalezena"; info["is_valid"] = False
                logger.warning(f"Konfigurace pro '{info['filename']}' nenalezena.")
                return info # Vracíme info s chybou konfigu

            info["config_path"] = config_path; config_name_found = os.path.basename(config_path)
            info["config_name"] = config_name_found; info["config_color"] = "green" # Předpoklad úspěchu
            logger.info(f"Nalezena konfigurace '{config_name_found}' pro '{info['filename']}'.")

            # 2. Načtení konfigurace - Může vyvolat ConfigError
            logger.debug(f"_get_file_info: Načítám konfig {config_name_found}")
            config_data = config_manager.load_config(config_path) # Chybu zachytíme níže
            column_mapping = config_data.get("column_mapping", {})
            transaction_rules = config_data.get("transaction_types", [])

            # 3. Načtení počtu řádků - Může vyvolat DataError/ValueError
            logger.debug(f"_get_file_info: Načítám celý soubor pro počet řádků: {info['filename']}")
            df_full = data_loader.load_data(file_path)
            if df_full is None: raise DataError("Chyba načítání dat.")
            info["row_count"] = str(len(df_full)); del df_full

            # 4. Načtení vzorku - Může vyvolat DataError/ValueError
            logger.debug(f"_get_file_info: Načítám vzorek ({SAMPLE_SIZE} ř.): {info['filename']}")
            df_sample = data_loader.load_data(file_path, sample_rows=SAMPLE_SIZE)
            if df_sample is None: raise DataError("Chyba načítání vzorku.")

            if df_sample.empty:
                 info["stats_known"] = "0"; info["stats_unknown"] = "0"; info["is_valid"] = True
            else:
                 # 5. Aplikace mapování a pravidel - Může vyvolat ConfigError/ProcessingError
                 df_sample.columns = df_sample.columns.str.strip()
                 mapped_sample = data_processor.map_columns(df_sample, column_mapping)
                 typed_sample = data_processor.assign_transaction_types(mapped_sample, transaction_rules) # Chybu zachytíme níže

                 # 6. Výpočet statistiky
                 if 'TYP TRANSAKCE' in typed_sample.columns:
                     total_sample = len(typed_sample); unknown_mask = typed_sample['TYP TRANSAKCE'].isin([None, ''])
                     untyped_count = unknown_mask.sum(); typed_count = total_sample - untyped_count
                     info["stats_known"] = str(typed_count); info["stats_unknown"] = str(untyped_count)
                 else: info["stats_known"] = "Chybí sl."; info["stats_unknown"] = ""
                 info["is_valid"] = True

            info["error"] = None # Vše OK

        # <<< ZMĚNA ZACHYTÁVÁNÍ CHYB ZDE >>>
        # Zachytíme VŠECHNY naše specifické chyby + běžné chyby
        except (ConfigError, DataError, ProcessingError, ValueError, FileNotFoundError) as e:
            logger.warning(f"Chyba při získávání informací pro '{info['filename']}': {e}")
            info["error"] = str(e); info["is_valid"] = False
            # Nastavíme barvu na ORANŽOVOU pro všechny tyto chyby
            info["config_color"] = "orange"
            # Pokud konfig nebyl nalezen (z kontroly výše), necháme "NENALEZENO" a červenou
            if info["config_name"] != "NENALEZENO":
                 # Jinak zobrazíme nalezený (nebo N/A, pokud chyba nastala dříve) a označíme jako chybu
                 info["config_name"] = f"{config_name_found} (Chyba!)"
            # Nastavíme N/A pro ostatní info
            if info["row_count"] == "N/A": info["row_count"] = "N/A"
            if info["stats_known"] == "N/A": info["stats_known"] = "N/A"; info["stats_unknown"] = ""
        except Exception as e: # Obecná neočekávaná chyba
            logger.error(f"Neočekávaná chyba při získávání informací pro '{info['filename']}': {e}", exc_info=True)
            info["error"] = f"Neoček. chyba: {e}"; info["is_valid"] = False
            info["config_name"] = "CHYBA"; info["config_color"] = "red"
            info["row_count"] = "N/A"; info["stats_known"] = "N/A"; info["stats_unknown"] = ""
        # <<< KONEC ZMĚNY ZACHYTÁVÁNÍ CHYB >>>

        return info

# KONEC METODY _get_file_info
# KONEC METODY _get_file_info
    def load_app_settings(self):
        """Načte poslední použité adresáře ze souboru nastavení."""
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.last_import_dir = settings.get("last_import_dir", self.last_import_dir)
                    self.last_export_dir = settings.get("last_export_dir", self.last_export_dir)
                    # Pro config dir ponecháme výchozí, pokud není explicitně uloženo
                    # self.last_config_dir = settings.get("last_config_dir", self.last_config_dir)
                    logger.info(f"Načtena nastavení aplikace: Import='{self.last_import_dir}', Export='{self.last_export_dir}'")
            else:
                 logger.info(f"Soubor nastavení '{SETTINGS_FILE}' nenalezen, použity výchozí adresáře.")
        except (json.JSONDecodeError, IOError, Exception) as e:
            logger.error(f"Chyba při načítání nastavení aplikace ({SETTINGS_FILE}): {e}")
            # V případě chyby použijeme výchozí hodnoty

    def save_app_settings(self):
        """Uloží aktuální poslední použité adresáře do souboru nastavení."""
        settings = {
            "last_import_dir": self.last_import_dir,
            "last_export_dir": self.last_export_dir,
            # "last_config_dir": self.last_config_dir # Zatím neukládáme
        }
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            logger.info(f"Nastavení aplikace uložena do {SETTINGS_FILE}")
        except (IOError, Exception) as e:
            logger.error(f"Chyba při ukládání nastavení aplikace ({SETTINGS_FILE}): {e}")
            # Zobrazíme chybu i uživateli, pokud je to kritické
            # messagebox.showwarning("Chyba ukládání", f"Nepodařilo se uložit nastavení aplikace:\n{e}", parent=self)

    # Přidáme volání save_app_settings při zavření okna
    def on_closing(self):
         """Metoda volaná při zavírání hlavního okna."""
         logger.info("Zavírání aplikace, ukládám nastavení...")
         self.save_app_settings()
         self.destroy() # Zavřeme okno

    # UVNITŘ TŘÍDY App(ctk.CTk):

    # def _calculate_full_stats_logic(self, file_path, config_path):
    #     """Logika pro výpočet statistik z celého souboru (běží ve vlákně)."""
    #     stats_text = "Statistika: Chyba"
    #     try:
    #         logger.info(f"_calculate_full_stats_logic: Načítám config: {config_path}")
    #         config_data = config_manager.load_config(config_path) # Může vyvolat ConfigError, ValueError
    #         column_mapping = config_data.get("column_mapping")
    #         transaction_rules = config_data.get("transaction_types")
    #         if not isinstance(column_mapping, dict) or not isinstance(transaction_rules, list):
    #              raise ConfigError("Konfigurace neobsahuje platné 'column_mapping' nebo 'transaction_types'.")

    #         logger.info(f"_calculate_full_stats_logic: Načítám kompletní data: {file_path}")
    #         df_full = data_loader.load_data(file_path) # Může vyvolat ValueError, FileNotFoundError, atd.
    #         if df_full is None or df_full.empty:
    #              raise DataError("Načtená kompletní data jsou prázdná nebo None.")

    #         actual_row_count = len(df_full)
    #         self.after(0, lambda count=actual_row_count: self.label_row_count.configure(text=f"Řádků: {count}"))
    #         logger.info(f"_calculate_full_stats_logic: Načteno {actual_row_count} řádků.")

    #         df_full.columns = df_full.columns.str.strip()

    #         logger.info("_calculate_full_stats_logic: Aplikuji mapování sloupců.")
    #         mapped_full = data_processor.map_columns(df_full, column_mapping)

    #         logger.info("_calculate_full_stats_logic: Aplikuji pravidla typů.")
    #         typed_full = data_processor.assign_transaction_types(mapped_full, transaction_rules)

    #         if 'TYP TRANSAKCE' in typed_full.columns:
    #             total_full = len(typed_full)
    #             unknown_mask = typed_full['TYP TRANSAKCE'].isin([None, ''])
    #             untyped_count = unknown_mask.sum()
    #             typed_count = total_full - untyped_count
    #             stats_text = f"Známé: {typed_count} | Neznámé: {untyped_count} (Celkem)" # Váš formát
    #             logger.info(f"Finální statistika z celého souboru: {stats_text}")
    #         else:
    #             stats_text = "Statistika: Chyba sloupce"
    #             logger.warning("_calculate_full_stats_logic: Chybí sloupec 'TYP TRANSAKCE'.")

    #     # <<< UPRAVENÉ ZACHYTÁVÁNÍ VÝJIMEK >>>
    #     except (ConfigError, DataError, ValueError, FileNotFoundError, ProcessingError) as e: # Přidáno ProcessingError
    #         # Zachytíme naše specifické chyby + chyby načítání/hodnot
    #         logger.error(f"_calculate_full_stats_logic: Chyba při výpočtu statistik: {e}", exc_info=True)
    #         stats_text = "Statistika: Chyba výpočtu"
    #         self.after(0, lambda e=e: messagebox.showerror("Chyba výpočtu statistik", f"Nepodařilo se spočítat statistiky:\n{e}", parent=self))
    #     except Exception as e:
    #         # Obecná chyba
    #         logger.error(f"_calculate_full_stats_logic: Neočekávaná chyba při výpočtu statistik: {e}", exc_info=True)
    #         stats_text = "Statistika: Chyba výpočtu"
    #         self.after(0, lambda e=e: messagebox.showerror("Chyba výpočtu statistik", f"Došlo k neočekávané chybě:\n{e}", parent=self))
    #     # <<< KONEC ÚPRAVY ZACHYTÁVÁNÍ >>>
    #     finally:
    #         self.after(0, lambda text=stats_text: self.label_transaction_stats.configure(text=text))
            # Ukončení progress baru a povolení tlačítek je v check_stats_thread

# KONEC METODY _calculate_full_stats_logic
    # def check_stats_thread(self):
    #     """Kontroluje, zda vlákno výpočtu statistik stále běží."""
    #     if hasattr(self, 'stats_thread') and self.stats_thread and self.stats_thread.is_alive():
    #         self.after(100, self.check_stats_thread)
    #     else:
    #         logger.info("Vlákno výpočtu statistik dokončeno.")
    #         # Zastavit progress bar
    #         self.progressbar.stop()
    #         self.progressbar.set(0)
    #         self.progressbar.configure(mode="determinate")

    #         # Povolit relevantní tlačítka (pokud neběží jiné zpracování)
    #         if not (self.processing_thread and self.processing_thread.is_alive()):
    #             self.button_import.configure(state="normal")
    #             self.button_manage_configs.configure(state="normal")
    #             # Tlačítka Zpracovat a Spočítat povolíme jen pokud máme soubor a config
    #             btn_state = "normal" if self.selected_file_path and self.identified_config_path else "disabled"
    #             self.button_process.configure(state=btn_state)
    #             self.button_calc_stats.configure(state=btn_state)

# KONEC NOVÝCH METOD


    # --- Metoda select_file ---
    # (Nová verze s resetem labelů)
# UVNITŘ TŘÍDY App(ctk.CTk):

    # ... (ostatní metody) ...

    # UVNITŘ TŘÍDY App(ctk.CTk):

    def _reset_selection_and_ui(self):
        """Pomocná metoda pro resetování seznamu souborů a stavu UI."""
        logger.debug("Resetuji výběr souborů a stav UI.")
        self.selected_file_paths = []
        self.batch_results = []
        self.last_processed_df = None

        # Vyčistíme listbox/frame se soubory
        if hasattr(self, 'files_listbox') and self.files_listbox.winfo_exists():
            self.files_listbox.delete(0, END)
        elif hasattr(self, 'files_info_frame') and self.files_info_frame.winfo_exists():
             for widget in self.files_info_frame.winfo_children():
                 widget.destroy()
             self.file_info_widgets = {}

        # Vyčistíme informační labely
        if hasattr(self, 'label_file_count'):
             self.label_file_count.configure(text="Nebyly vybrány žádné soubory")
        if hasattr(self, 'label_row_count'):
            self.label_row_count.configure(text="")
        if hasattr(self, 'label_transaction_stats'):
            self.label_transaction_stats.configure(text="")
        if hasattr(self, 'label_progress_info'):
             self.label_progress_info.configure(text="")

        # Zakážeme tlačítka
        if hasattr(self, 'button_process'):
            self.button_process.configure(state="disabled")
        # Odkaz na button_calc_stats odstraněn

        # Save tlačítka
        self._enable_save_buttons_if_ready(is_batch=True)

# KONEC METODY _reset_selection_and_ui
   # UVNITŘ TŘÍDY App(ctk.CTk):

    # Metoda _update_file_info_ui - Verze s 1 kartičkou, info pod konfigem
    
    # UVNITŘ TŘÍDY App(ctk.CTk):

    def edit_config_for_file(self, source_file_path, config_path):
        """Otevře Config Manager a vybere/vytvoří konfiguraci pro daný soubor."""
        logger.info(f"Požadavek na editaci/vytvoření konfigu pro soubor: {os.path.basename(source_file_path)}")
        logger.debug(f"  -> Source file: {source_file_path}")
        logger.debug(f"  -> Config path (může být None): {config_path}")

        # 1. Otevřeme nebo aktivujeme okno Config Manageru
        if self.config_window is None or not self.config_window.winfo_exists():
            self.log_message("INFO: Otevírám Správce Konfigurací...")
            try:
                 self.config_window = ConfigManagerWindow(self) # Vytvoříme nové okno
                 self.config_window.grab_set()
                 # Zavoláme metodu pro výběr/vytvoření až po inicializaci okna
                 self.after(100, lambda: self.config_window.select_or_create_config(config_path, source_file_path))
            except Exception as e_cfg_win:
                 logger.error(f"Chyba při vytváření ConfigManagerWindow: {e_cfg_win}", exc_info=True)
                 messagebox.showerror("Chyba", f"Nepodařilo se otevřít správce konfigurací:\n{e_cfg_win}", parent=self)
        else:
            self.log_message("INFO: Aktivuji Správce Konfigurací...")
            try:
                self.config_window.focus() # Přeneseme focus
                # Zavoláme metodu v existujícím okně (s malým zpožděním)
                if hasattr(self.config_window, 'select_or_create_config'):
                     self.after(50, lambda: self.config_window.select_or_create_config(config_path, source_file_path))
                else:
                     logger.error("Chyba: ConfigManagerWindow nemá metodu 'select_or_create_config'")
                     messagebox.showerror("Interní chyba", "Funkce pro otevření konfigurace není dostupná.", parent=self)
            except Exception as e_focus:
                logger.error(f"Chyba při aktivaci nebo volání ConfigManagerWindow: {e_focus}", exc_info=True)
                messagebox.showerror("Chyba", f"Nepodařilo se aktivovat správce konfigurací:\n{e_focus}", parent=self)

# KONEC METODY edit_config_for_file
    
    
    # UVNITŘ TŘÍDY App(ctk.CTk):

    # Metoda _update_file_info_ui - Verze s 1 kartičkou, info pod konfigem
    # (Tato metoda zůstává stejná, jen zobrazí info vrácené z _get_file_info)
    def _update_file_info_ui(self):
        """Překreslí seznam souborů jako jednu kartičku pro soubor,
           s informacemi o řádcích/stat pod konfigem."""
        logger.debug(f"Aktualizuji UI pro {len(self.selected_file_paths)} souborů.")
        # Vyčistíme staré widgety
        for widget in self.files_info_frame.winfo_children(): widget.destroy()
        self.file_info_widgets = {}; self.file_checkbox_vars = {}

        if not self.selected_file_paths: self._reset_selection_and_ui(); return

        count = len(self.selected_file_paths)
        count_text = f"Vybráno souborů: {count}. Načítám informace..."; self.label_file_count.configure(text=count_text)
        self.log_message(f"INFO: {count_text}"); logger.info(f"Zobrazuji info pro {count} souborů.")
        self.update_idletasks()

        all_configs_found = True; files_with_errors = 0; valid_files_count = 0

        # --- Vytvoření "kartiček" ---
        for file_path in self.selected_file_paths:
            self.label_progress_info.configure(text=f"Načítám info: {os.path.basename(file_path)}..."); self.update_idletasks()
            # Získáme info (včetně případné chyby a barvy)
            info = self.file_info_data.get(file_path) # ZÍSKÁME PŘEDEM NAČTENÁ DATA

            if info is None: # Pokud data z nějakého důvodu chybí
                 logger.error(f"Chybí předem načtená data pro {file_path}! Přeskakuji.")
                 errors_occurred = True # Označíme chybu
                 continue # Přeskočíme tento soubor

            # --- Hlavní Frame Kartičky ---
            file_frame = ctk.CTkFrame(self.files_info_frame, fg_color="gray20", border_width=1, border_color="gray40")
            file_frame.pack(fill=X, pady=(3,3), padx=3)
            file_frame.grid_columnconfigure(0, weight=0, minsize=30); file_frame.grid_columnconfigure(1, weight=1); file_frame.grid_columnconfigure(2, weight=0)

            # --- Sloupec 0: Checkbox ---
            is_valid_for_processing = info["is_valid"]
            check_var = BooleanVar(value=is_valid_for_processing)
            self.file_checkbox_vars[file_path] = check_var
            checkbox_state = "normal" if is_valid_for_processing else "disabled"
            checkbox = ctk.CTkCheckBox(file_frame, text="", variable=check_var, width=10, state=checkbox_state); checkbox.grid(row=0, column=0, padx=(5, 5), pady=5, sticky="nw")

            # --- Sloupec 1: Hlavní obsah ---
            main_content_frame = ctk.CTkFrame(file_frame, fg_color="transparent"); main_content_frame.grid(row=0, column=1, padx=(0, 5), pady=3, sticky="nsew")
            filename_label = ctk.CTkLabel(main_content_frame, text=info["filename"], anchor="w", font=ctk.CTkFont(weight="bold", size=13)); filename_label.pack(fill=X, anchor="w", pady=(0, 1))
            config_frame = ctk.CTkFrame(main_content_frame, fg_color="transparent"); config_frame.pack(fill=X, anchor="w", pady=(1, 1))
            config_path_for_edit = info.get("config_path")
            edit_conf_button = ctk.CTkButton(config_frame, text="✎", font=ctk.CTkFont(size=14), width=25, height=25, fg_color="transparent", border_width=1, text_color="gray60", hover_color="gray40", command=lambda fp=file_path, cp=config_path_for_edit: self.edit_config_for_file(fp, cp)); edit_conf_button.pack(side=LEFT, pady=0, padx=(0,3))
            config_text = f"Konfig: {info['config_name']}"; config_label = ctk.CTkLabel(config_frame, text=config_text, text_color=info["config_color"], anchor="w", font=ctk.CTkFont(size=11)); config_label.pack(side=LEFT, anchor="w")
            stats_info_frame = ctk.CTkFrame(main_content_frame, fg_color="transparent"); stats_info_frame.pack(fill=X, anchor="w", pady=(1, 0))
            stats_info_frame.grid_columnconfigure(0, weight=0, minsize=120); stats_info_frame.grid_columnconfigure(1, weight=0, minsize=150); stats_info_frame.grid_columnconfigure(2, weight=1)
            rows_text = f"Počet řádků: {info['row_count']}"; rows_label = ctk.CTkLabel(stats_info_frame, text=rows_text, anchor="w", font=ctk.CTkFont(size=11)); rows_label.grid(row=0, column=0, sticky="w")
            stats_known_text = f"Známé trn.(vz): {info['stats_known']}"; stats_known_label = ctk.CTkLabel(stats_info_frame, text=stats_known_text, anchor="w", font=ctk.CTkFont(size=11)); stats_known_label.grid(row=0, column=1, padx=(10,5), sticky="w")
            stats_unknown_text = f"Neznámé trn.(vz): {info['stats_unknown']}"; stats_unknown_label = ctk.CTkLabel(stats_info_frame, text=stats_unknown_text, anchor="w", font=ctk.CTkFont(size=11)); stats_unknown_label.grid(row=0, column=2, padx=(5,10), sticky="w")

            # --- Sloupec 2: Tlačítko X ---
            remove_button = ctk.CTkButton(file_frame, text="X", width=25, height=25, fg_color="gray30", hover_color="gray40", command=lambda fp=file_path: self.remove_file_from_list(fp)); remove_button.grid(row=0, column=2, padx=(5, 5), pady=5, sticky="ne")

            # Uložení widgetů
            self.file_info_widgets[file_path] = {'frame': file_frame, 'config_label': config_label, 'rows_label': rows_label, 'stats_known_label': stats_known_label, 'stats_unknown_label': stats_unknown_label, 'checkbox_var': check_var}

            # Počítání chyb/validity
            if info["error"]: files_with_errors += 1
            if info["is_valid"]: valid_files_count += 1
            else: all_configs_found = False # Nepotřebujeme sledovat?

        # --- Dokončení aktualizace UI ---
        self.label_progress_info.configure(text="")
        final_count_text = f"Vybráno souborů: {count}" + (f" (Problémy u {files_with_errors})" if files_with_errors > 0 else "")
        self.label_file_count.configure(text=final_count_text)
        any_checked_valid = any(var.get() for var in self.file_checkbox_vars.values())
        process_state = "normal" if any_checked_valid else "disabled"
        self.button_process.configure(state=process_state)
        self.log_message(f"INFO: Informace pro {count} souborů zobrazeny ({valid_files_count} připraveno).")
        logger.info(f"Informace pro {count} souborů zobrazeny.")

# KONEC METODY _update_file_info_ui
# KONEC METODY _update_file_info_ui
    # Metoda select_files - Verze s přidáváním a kartičkami s CHECKBOXY
   # UVNITŘ TŘÍDY App(ctk.CTk):

    # Metoda select_files - Verze s ukládáním info do self.file_info_data
    def select_files(self):
        ftypes=(('Podporované', '*.csv *.xlsx *.xls'), ('Všechny', '*.*'))
        initial_dir_import = self.last_import_dir if os.path.isdir(self.last_import_dir) else "."
        logger.debug(f"Otevírám dialog pro import (přidání), initialdir='{initial_dir_import}'")

        filepaths_tuple = filedialog.askopenfilenames(title='Vyberte soubor(y) k přidání', initialdir=initial_dir_import, filetypes=ftypes, parent=self)
        new_filepaths = list(filepaths_tuple) if filepaths_tuple else []

        if not new_filepaths: self.log_message("INFO: Výběr zrušen."); logger.info("Výběr zrušen."); return

        self.last_import_dir = os.path.dirname(new_filepaths[0]); logger.debug(f"Nový last_import_dir: '{self.last_import_dir}'")

        added_count = 0; current_paths_set = set(self.selected_file_paths)
        files_to_process_info = []
        for fp in new_filepaths:
            if fp not in current_paths_set: self.selected_file_paths.append(fp); current_paths_set.add(fp); files_to_process_info.append(fp); added_count += 1
            else: logger.debug(f"Soubor '{os.path.basename(fp)}' již v seznamu.")

        if added_count > 0:
            logger.info(f"Přidáno {added_count} nových souborů."); self.selected_file_paths.sort()

            # --- Načtení informací pro VŠECHNY soubory ---
            count = len(self.selected_file_paths)
            self.file_info_data = {} # Slovník pro uložení výsledků _get_file_info
            self.log_message(f"INFO: Načítám informace pro {count} souborů...")
            logger.info(f"Načítám informace pro {count} souborů...")
            self.label_file_count.configure(text=f"Vybráno souborů: {count}. Načítám informace...")
            self.update_idletasks()
            any_errors_during_info = False

            for file_path in self.selected_file_paths:
                 self.label_progress_info.configure(text=f"Analyzuji: {os.path.basename(file_path)}..."); self.update_idletasks()
                 # Zde voláme _get_file_info a výsledek ULOŽÍME
                 # Chyby ConfigError nejsou zachyceny zde, ale ostatní ano (vrátí info s chybou)
                 try:
                    info = self._get_file_info(file_path)
                    self.file_info_data[file_path] = info
                    if info.get("error"): # Pokud _get_file_info vrátilo chybu
                         any_errors_during_info = True
                 except ConfigError as ce:
                      # Zachytíme ConfigError ZDE
                      fname = os.path.basename(file_path)
                      logger.error(f"Chyba konfigurace pro '{fname}': {ce}", exc_info=False)
                      any_errors_during_info = True
                      # Uložíme chybové info
                      self.file_info_data[file_path] = { "filename": fname, "config_name": "CHYBA KONFIGU!", "config_path": None,"row_count": "N/A", "stats_known": "N/A", "stats_unknown": "", "error": str(ce), "config_color": "red", "is_valid": False }
                      messagebox.showerror(f"Chyba Konfigurace ({fname})", f"Chyba v konfigu:\n\n{ce}", parent=self)
                 except Exception as e:
                      fname = os.path.basename(file_path)
                      logger.error(f"Neočekávaná chyba v _get_file_info pro '{fname}': {e}", exc_info=True)
                      any_errors_during_info = True
                      self.file_info_data[file_path] = { "filename": fname, "config_name": "FATÁLNÍ CHYBA!", "config_path": None, "row_count": "N/A", "stats_known": "N/A", "stats_unknown": "", "error": str(e), "config_color": "red", "is_valid": False }
                      messagebox.showerror(f"Neočekávaná Chyba ({fname})", f"Chyba info:\n\n{e}", parent=self)


            # --- Aktualizace UI po načtení všech informací ---
            self.label_progress_info.configure(text="")
            # Zavoláme překreslení, které použije data z self.file_info_data
            self._update_file_info_ui()
            self.log_message(f"INFO: Informace pro {count} souborů načteny" + (" (některé s chybami)." if any_errors_during_info else "."))

        else:
            self.log_message("INFO: Nebyly přidány žádné nové unikátní soubory.")

# KONEC METODY select_files
# UVNITŘ TŘÍDY App(ctk.CTk):

    # Metoda _update_file_info_ui - Verze s 1 kartičkou, info pod konfigem, OPRAVA gridu
    def _update_file_info_ui(self):
        """Překreslí seznam souborů jako jednu kartičku pro soubor,
           s informacemi o řádcích/stat pod konfigem."""
        logger.debug(f"Aktualizuji UI pro {len(self.selected_file_paths)} souborů.")
        for widget in self.files_info_frame.winfo_children(): widget.destroy()
        self.file_info_widgets = {}; self.file_checkbox_vars = {}

        if not self.selected_file_paths: self._reset_selection_and_ui(); return

        count = len(self.selected_file_paths)
        count_text = f"Vybráno souborů: {count}. Načítám informace..."; self.label_file_count.configure(text=count_text)
        self.log_message(f"INFO: {count_text}"); logger.info(f"Zobrazuji info pro {count} souborů.")
        self.update_idletasks()

        all_configs_found = True; files_with_errors = 0; valid_files_count = 0

        # --- Vytvoření "kartiček" ---
        for file_path in self.selected_file_paths:
            self.label_progress_info.configure(text=f"Načítám info: {os.path.basename(file_path)}..."); self.update_idletasks()
            info = self._get_file_info(file_path)

            # --- Hlavní Frame Kartičky ---
            file_frame = ctk.CTkFrame(self.files_info_frame, fg_color="gray20", border_width=1, border_color="gray40")
            file_frame.pack(fill=X, pady=(3,3), padx=3)
            # Grid: [Checkbox] [Hlavní obsah] [X]
            file_frame.grid_columnconfigure(0, weight=0, minsize=30)  # Checkbox
            file_frame.grid_columnconfigure(1, weight=1)               # Hlavní obsah (roztáhne se)
            file_frame.grid_columnconfigure(2, weight=0)               # Tlačítko X (pevná šířka)

            # --- Sloupec 0: Checkbox ---
            is_valid_for_processing = info["is_valid"]
            check_var = BooleanVar(value=is_valid_for_processing)
            self.file_checkbox_vars[file_path] = check_var
            checkbox_state = "normal" if is_valid_for_processing else "disabled"
            checkbox = ctk.CTkCheckBox(file_frame, text="", variable=check_var, width=10, state=checkbox_state)
            checkbox.grid(row=0, column=0, padx=(5, 5), pady=5, sticky="nw")

            # --- Sloupec 1: Hlavní obsah (Název, Konfig, Info pod sebou) ---
            main_content_frame = ctk.CTkFrame(file_frame, fg_color="transparent")
            main_content_frame.grid(row=0, column=1, padx=(0, 5), pady=3, sticky="nsew") # Roztáhne se vertikálně i horizontálně

            # Název souboru
            filename_label = ctk.CTkLabel(main_content_frame, text=info["filename"], anchor="w", font=ctk.CTkFont(weight="bold", size=13))
            filename_label.pack(fill=X, anchor="w", pady=(0, 1)) # Pack v rámci main_content_frame

            # Rámeček pro Konfig + Tužka
            config_frame = ctk.CTkFrame(main_content_frame, fg_color="transparent")
            config_frame.pack(fill=X, anchor="w", pady=(1, 1)) # Pack pod název
            config_path_for_edit = info.get("config_path")
            edit_conf_button = ctk.CTkButton(config_frame, text="✎", font=ctk.CTkFont(size=14), width=25, height=25, fg_color="transparent", border_width=1, text_color="gray60", hover_color="gray40",
                                               command=lambda fp=file_path, cp=config_path_for_edit: self.edit_config_for_file(fp, cp))
            edit_conf_button.pack(side=LEFT, pady=0, padx=(0,3))
            config_text = f"Konfigurace: {info['config_name']}"
            config_label = ctk.CTkLabel(config_frame, text=config_text, text_color=info["config_color"], anchor="w", font=ctk.CTkFont(size=12))
            config_label.pack(side=LEFT, anchor="w")

            # Rámeček pro Řádky a Statistiky
            stats_info_frame = ctk.CTkFrame(main_content_frame, fg_color="transparent")
            stats_info_frame.pack(fill=X, anchor="w", pady=(1, 0)) # Pack pod konfig
            # Použijeme grid pro zarovnání vedle sebe v tomto rámci
            stats_info_frame.grid_columnconfigure(0, weight=0, minsize=120) # Řádky
            stats_info_frame.grid_columnconfigure(1, weight=0, minsize=150) # Známé
            stats_info_frame.grid_columnconfigure(2, weight=1)               # Neznámé (roztáhne zbytek)

            rows_text = f"Počet řádků: {info['row_count']}"
            rows_label = ctk.CTkLabel(stats_info_frame, text=rows_text, anchor="w", font=ctk.CTkFont(size=12))
            rows_label.grid(row=0, column=0, sticky="w")

            stats_known_text = f"Známé trn.: {info['stats_known']}"
            stats_known_label = ctk.CTkLabel(stats_info_frame, text=stats_known_text, anchor="w", font=ctk.CTkFont(size=12))
            stats_known_label.grid(row=0, column=1, padx=(10,5), sticky="w")

            stats_unknown_text = f"Neznámé trn.: {info['stats_unknown']}"
            stats_unknown_label = ctk.CTkLabel(stats_info_frame, text=stats_unknown_text, anchor="w", font=ctk.CTkFont(size=12))
            stats_unknown_label.grid(row=0, column=2, padx=(5,10), sticky="w")


            # --- Sloupec 2: Tlačítko X ---
            remove_button = ctk.CTkButton(file_frame, text="X", width=25, height=25, fg_color="gray30", hover_color="gray40", command=lambda fp=file_path: self.remove_file_from_list(fp))
            remove_button.grid(row=0, column=2, padx=(5, 5), pady=5, sticky="ne") # Vpravo nahoře, sloupec 2

            # --- Uložení widgetů ---
            self.file_info_widgets[file_path] = {'frame': file_frame, 'config_label': config_label, 'rows_label': rows_label, 'stats_known_label': stats_known_label, 'stats_unknown_label': stats_unknown_label, 'checkbox_var': check_var}

            # Kontrola chyb a validity
            if info["error"]: files_with_errors += 1
            if info["is_valid"]: valid_files_count += 1
            else: all_configs_found = False

        # --- Dokončení aktualizace UI ---
        self.label_progress_info.configure(text="")
        final_count_text = f"Vybráno souborů: {count}" + (f" (Problémy u {files_with_errors})" if files_with_errors > 0 else "")
        self.label_file_count.configure(text=final_count_text)
        any_checked_valid = False
        if valid_files_count > 0:
            for fp, var in self.file_checkbox_vars.items():
                 if var.get(): any_checked_valid = True; break
        process_state = "normal" if any_checked_valid else "disabled"
        self.button_process.configure(state=process_state)
        self.log_message(f"INFO: Informace pro {count} souborů zobrazeny ({valid_files_count} validních).")
        logger.info(f"Informace pro {count} souborů zobrazeny.")

# KONEC METODY _update_file_info_ui
    def _calculate_sample_stats(self, file_path, config_path):
        """
        Pomocná metoda pro načtení vzorku dat (pomocí data_loader),
        aplikaci mapování a pravidel a výpočet odhadované statistiky.
        Vrací string pro zobrazení v labelu.
        """
        SAMPLE_SIZE = 300 # Počet řádků pro vzorek
        logger.info(f"Výpočet statistik ze vzorku ({SAMPLE_SIZE} řádků) pro {os.path.basename(file_path)}")
        stats_text = "Statistika: Chyba vzorku"

        try:
            # 1. Načtení konfigurace
            logger.debug(f"_calculate_sample_stats: Načítám config: {config_path}")
            config_data = config_manager.load_config(config_path)
            column_mapping = config_data.get("column_mapping", {})
            transaction_rules = config_data.get("transaction_types", [])
            if not column_mapping or not transaction_rules:
                 logger.warning("_calculate_sample_stats: Konfigurace neobsahuje mapování nebo pravidla.")
                 return "Statistika (vz): Chybí map./prav."

            # 2. Načtení vzorku dat pomocí data_loader.load_data
            logger.debug(f"_calculate_sample_stats: Načítám vzorek dat (nrows={SAMPLE_SIZE}) pomocí data_loader")
            df_sample = data_loader.load_data(file_path, sample_rows=SAMPLE_SIZE) # <<< ZDE VOLÁME NOVOU FUNKCI

            if df_sample is None or df_sample.empty:
                 logger.warning("_calculate_sample_stats: Vzorek dat je prázdný nebo se nepodařilo načíst.")
                 # Zkontrolujeme, zda load_data nevyvolalo chybu (mělo by)
                 # Pro jistotu vrátíme informativní text
                 return "Statistika (vz): Prázdný/Chyba čtení"

            # Sloupce už by měly být očištěné v load_data

            # 3. Aplikace mapování sloupců
            logger.debug("_calculate_sample_stats: Aplikuji mapování sloupců na vzorek.")
            mapped_sample = data_processor.map_columns(df_sample, column_mapping)

            # 4. Aplikace pravidel pro typy transakcí
            logger.debug("_calculate_sample_stats: Aplikuji pravidla typů na vzorek.")
            typed_sample = data_processor.assign_transaction_types(mapped_sample, transaction_rules)

            # 5. Výpočet statistiky ze vzorku
            if 'TYP TRANSAKCE' in typed_sample.columns:
                total_sample = len(typed_sample)
                unknown_mask = typed_sample['TYP TRANSAKCE'].isin([None, ''])
                untyped_count = unknown_mask.sum()
                typed_count = total_sample - untyped_count
                # Použijeme vámi preferovaný text
                stats_text = f"Známé (vz): {typed_count} | Neznámé (vz): {untyped_count}"
                logger.info(f"Statistika ze vzorku: {stats_text}")
            else:
                logger.warning("_calculate_sample_stats: Chybí sloupec 'TYP TRANSAKCE' po aplikaci pravidel.")
                stats_text = "Statistika (vz): Chyba prav."

        except Exception as e:
            logger.error(f"Chyba při výpočtu statistiky ze vzorku: {e}", exc_info=True)
            stats_text = "Statistika (vz): Chyba výp."
            # Můžeme zobrazit i messagebox zde? Raději ne, je to jen náhled.

        return stats_text
# UVNITŘ TŘÍDY App(ctk.CTk):

    # Metoda start_processing - OPRAVA č. 5 pro logiku metadat v batchi
    # UVNITŘ TŘÍDY App(ctk.CTk):

    # Metoda start_processing - Verze se zpracováním jen zaškrtnutých souborů
    # UVNITŘ TŘÍDY App(ctk.CTk):

    def remove_file_from_list(self, file_path_to_remove):
        """Odebere zadaný soubor ze seznamu selected_file_paths a aktualizuje UI."""
        logger.info(f"Pokus o odebrání souboru ze seznamu: {os.path.basename(file_path_to_remove)}")
        if file_path_to_remove in self.selected_file_paths:
            # Odebereme ze seznamu cest
            self.selected_file_paths.remove(file_path_to_remove)
            logger.debug(f"Soubor '{os.path.basename(file_path_to_remove)}' odebrán ze selected_file_paths.")

            # Odstraníme widgety a proměnnou checkboxu z cache
            widgets_to_remove = self.file_info_widgets.pop(file_path_to_remove, None) # Odebereme a získáme
            if file_path_to_remove in self.file_checkbox_vars:
                 del self.file_checkbox_vars[file_path_to_remove]

            # Zničíme hlavní frame kartičky pro tento soubor
            if widgets_to_remove and 'frame' in widgets_to_remove:
                try:
                     widgets_to_remove['frame'].destroy()
                     logger.debug(f"Frame pro '{os.path.basename(file_path_to_remove)}' zničen.")
                except Exception as e_destroy:
                     logger.warning(f"Chyba při ničení frame: {e_destroy}")
            else:
                 logger.warning(f"Pokus o zničení frame pro '{os.path.basename(file_path_to_remove)}', ale nebyl nalezen v cache.")


            # Aktualizujeme label s počtem souborů a stav tlačítek
            count = len(self.selected_file_paths)
            # Znovu spočítáme chyby z remaining widgets
            errors_count = 0
            valid_files_count = 0
            for fp, info_widgets in self.file_info_widgets.items():
                 # Předpokládáme, že error je označen barvou nebo stavem checkboxu
                 # Jednodušší je znovu spočítat validní
                 if fp in self.file_checkbox_vars and self.file_checkbox_vars[fp].get():
                      is_valid = True # Pokud je checkbox zaškrtnutý a povolený (kontrola stavu by byla lepší)
                      # Můžeme přidat kontrolu chyby z config_label, pokud ji ukládáme
                      if info_widgets['config_label'].cget("text_color").lower() in ["red", "orange"]:
                           is_valid = False
                           errors_count += 1
                      if is_valid:
                            valid_files_count +=1
                 elif fp in self.file_checkbox_vars and not self.file_checkbox_vars[fp].get():
                      # Odškrtnutý, ale možná validní - nepočítáme do validních pro zpracování
                      pass
                 else: # Nemá checkbox? Chyba
                      errors_count += 1


            count_text = f"Vybráno souborů: {count}" + (f" (Problémy u {errors_count})" if errors_count > 0 else "")
            self.label_file_count.configure(text=count_text)

            # Znovu zkontrolujeme, zda je co zpracovat
            any_checked_valid = False
            for fp, var in self.file_checkbox_vars.items():
                 if var.get(): any_checked_valid = True; break
            process_state = "normal" if any_checked_valid else "disabled"
            self.button_process.configure(state=process_state)

            # Aktualizujeme stav Save tlačítek
            self._enable_save_buttons_if_ready(is_batch=True)

            self.log_message(f"INFO: Soubor '{os.path.basename(file_path_to_remove)}' odebrán ze seznamu.")
        else:
            logger.warning(f"Pokus o odebrání souboru, který není v seznamu: {file_path_to_remove}")

# KONEC METODY remove_file_from_list
    
    def start_processing(self):
        """Spustí proces zpracování POUZE pro zaškrtnuté soubory v seznamu."""

        # --- Získání seznamu zaškrtnutých souborů ---
        files_to_process = []
        if not hasattr(self, 'file_checkbox_vars'): # Pojistka
             logger.error("Chyba: Atribut 'file_checkbox_vars' neexistuje.")
             messagebox.showerror("Interní chyba", "Chyba při získávání seznamu souborů.", parent=self)
             return

        for file_path, check_var in self.file_checkbox_vars.items():
            # Ujistíme se, že cesta stále existuje v hlavním seznamu (pro případ race condition?)
            if file_path in self.selected_file_paths and check_var.get(): # Zkontrolujeme hodnotu BooleanVar
                files_to_process.append(file_path)
        # --- Konec získání seznamu ---

        if not files_to_process:
            messagebox.showwarning("Není vybráno", "Zaškrtněte alespoň jeden validní soubor ke zpracování.", parent=self)
            return

        # Máme seznam souborů ke zpracování (files_to_process)

        # Reset výsledků a zakázání UI (stejné jako předtím)
        self.batch_results = []
        self.last_processed_df = None
        self._enable_save_buttons_if_ready(is_batch=True)
        try:
            self.button_import.configure(state="disabled"); self.button_process.configure(state="disabled")
            self.button_manage_configs.configure(state="disabled"); self.button_save_csv.configure(state="disabled"); self.button_save_xlsx.configure(state="disabled")
        except Exception as e: logger.warning(f"Chyba při zakazování tlačítek: {e}")
        self.progressbar.set(0); self.progressbar.configure(mode="determinate")

        total_files_to_process = len(files_to_process) # Celkový počet ke zpracování
        processed_count = 0; errors_occurred = False
        apply_all_metadata = False; first_metadata = None

        self.log_message(f"INFO: Zahajuji zpracování {total_files_to_process} zaškrtnutých souborů...")
        logger.info(f"start_processing: Zahajuji zpracování {total_files_to_process} zaškrtnutých souborů.")

        # --- Získání metadat pro první ZAŠKRTNUTÝ soubor ---
        if total_files_to_process > 0:
            try:
                # Použijeme první soubor ze seznamu files_to_process
                metadata_result, apply_all = self._ask_metadata_for_file(files_to_process[0], 1, total_files_to_process)
                if metadata_result is None:
                    self._finalize_processing(processed_count, total_files_to_process, errors_occurred, canceled=True)
                    return
                first_metadata = metadata_result
                apply_all_metadata = apply_all
            except Exception as e:
                 logger.error(f"Chyba při získávání metadat pro první soubor: {e}", exc_info=True)
                 messagebox.showerror("Chyba Metadat", f"Nepodařilo se získat metadata:\n{e}", parent=self)
                 self._finalize_processing(processed_count, total_files_to_process, True, canceled=False)
                 return
        else: return # Nemáme co zpracovávat

        self.log_message(f"INFO: Zahajuji cyklus zpracování...")
        logger.info(f"start_processing: Zahajuji cyklus zpracování. Použít pro všechny: {apply_all_metadata}")

        # --- Cyklus zpracování ZAŠKRTNUTÝCH souborů ---
        # Iterujeme přes files_to_process místo self.selected_file_paths
        for i, file_path in enumerate(files_to_process):
            current_process_num = i + 1 # Číslo v rámci zpracovávaných
            fname = os.path.basename(file_path)
            self.label_progress_info.configure(text=f"Zpracovávám {current_process_num}/{total_files_to_process}: '{fname}'...")
            logger.info(f"start_processing: Zpracovávám {current_process_num}/{total_files_to_process}: {fname}")
            progress_value = float(i) / total_files_to_process; self.progressbar.set(progress_value); self.update_idletasks()

            identified_config_path = None; cfg = None; success_this_file = False
            processed_df_this_file = None; current_metadata = None
            stats_text = "" ; untyped_count = 0; config_name = "N/A"

            # --- Aktualizace stavu na kartičce ---
            # Označíme, že se soubor zpracovává
            if file_path in self.file_info_widgets:
                try:
                     self.file_info_widgets[file_path]['frame'].configure(border_color="yellow")
                     # Můžeme přidat i textový status label na kartičku později
                except KeyError: pass

            try:
                # 1. Identifikace a načtení konfigurace
                self.log_message(f"INFO [{current_process_num}/{total_files_to_process}]: Hledám konfig...")
                identified_config_path = config_manager.identify_config_for_file(file_path, config_manager.CONFIGS_DIR)
                if not identified_config_path: raise ConfigError(f"Konfigurace nenalezena.")
                config_name = os.path.basename(identified_config_path)
                self.log_message(f"INFO [{current_process_num}/{total_files_to_process}]: Konfig: '{config_name}'")
                cfg = config_manager.load_config(identified_config_path)

                # 2. Získání/Použití metadat
                if i == 0: # Pro první zpracovávaný soubor
                    current_metadata = first_metadata
                elif apply_all_metadata:
                    current_metadata = first_metadata
                else: # Pro další, pokud apply_all bylo False
                    metadata_result, _ = self._ask_metadata_for_file(file_path, current_process_num, total_files_to_process)
                    if metadata_result is None: raise ProcessingError("Zpracování zrušeno uživatelem (metadata).")
                    current_metadata = metadata_result
                if current_metadata is None: raise ProcessingError("Interní chyba: Chybí metadata.")

                # 3. Načtení dat
                self.log_message(f"INFO [{current_process_num}/{total_files_to_process}]: Načítám data...")
                df_in = data_loader.load_data(file_path)
                if df_in is None: raise ValueError("Načtení dat selhalo.")
                actual_row_count = len(df_in); self.log_message(f"INFO [{current_process_num}/{total_files_to_process}]: Načteno řádků: {actual_row_count}")
                self.label_progress_info.configure(text=f"Zpracovávám {current_process_num}/{total_files_to_process}: '{fname}' ({actual_row_count} ř.)"); self.update_idletasks()

                # 4. Zpracování dat
                self.log_message(f"INFO [{current_process_num}/{total_files_to_process}]: Zpracovávám...");
                processed_df_this_file = data_processor.process_data(df_in, cfg, fname, current_metadata)
                self.log_message(f"INFO [{current_process_num}/{total_files_to_process}]: Data zpracována.")

                # 5. Výpočet statistiky a zjištění neznámých
                if processed_df_this_file is not None and isinstance(processed_df_this_file, pd.DataFrame):
                    stats_text = "Typy: N/A"; typed_count = 0
                    try:
                        if 'TYP TRANSAKCE' in processed_df_this_file.columns:
                            total_count = len(processed_df_this_file); unknown_mask = (processed_df_this_file['TYP TRANSAKCE'] == data_processor.UNKNOWN_TRANSACTION_TYPE); untyped_count = unknown_mask.sum()
                            typed_count = total_count - untyped_count; stats_text = f"Známé: {typed_count} | Neznámé: {untyped_count}"
                        else: stats_text = "Typy: Chyba sl."; untyped_count = 0
                    except Exception as e_stats: stats_text = "Typy: Chyba výp."; untyped_count = 0; logger.error(f"Chyba stat. pro '{fname}': {e_stats}")
                    # Aktualizujeme kartičku
                    if file_path in self.file_info_widgets:
                         try: self.file_info_widgets[file_path]['stats_label'].configure(text=stats_text); self.file_info_widgets[file_path]['rows_label'].configure(text=f"({actual_row_count} ř.)"); self.file_info_widgets[file_path]['config_label'].configure(text=f"Konfig: {config_name}", text_color="green")
                         except KeyError: pass
                    self.update_idletasks()
                else: untyped_count = 0

                # 6. Dotaz na klasifikaci pro tento soubor
                if untyped_count > 0:
                    logger.info(f"Soubor '{fname}' obsahuje {untyped_count} neznámých."); self.log_message(f"INFO [{current_process_num}/{total_files_to_process}]: Nalezeno {untyped_count} neznámých v '{fname}'.")
                    if messagebox.askyesno("Neznámé Transakce", f"Soubor '{fname}' ({untyped_count} nezn.).\nRozdělit podle částky?", icon='warning', parent=self):
                        self.log_message(f"INFO [{current_process_num}/{total_files_to_process}]: Aplikuji třídění..."); logger.info(f"Aplikuji classify na '{fname}'.")
                        try:
                            processed_df_this_file = data_processor.classify_unknown_by_amount(processed_df_this_file)
                            if processed_df_this_file is not None and 'TYP TRANSAKCE' in processed_df_this_file.columns:
                                # Přepočet a aktualizace statistik na kartičce
                                unknown_mask_after = (processed_df_this_file['TYP TRANSAKCE'] == data_processor.UNKNOWN_TRANSACTION_TYPE); untyped_count_after = unknown_mask_after.sum()
                                typed_count_after = len(processed_df_this_file) - untyped_count_after; stats_text_after = f"Známé: {typed_count_after} | Neznámé: {untyped_count_after}"
                                if file_path in self.file_info_widgets:
                                     try: self.file_info_widgets[file_path]['stats_label'].configure(text=stats_text_after)
                                     except KeyError: pass
                                logger.info(f"Statistika po klasifikaci: {stats_text_after}"); self.update_idletasks()
                        except Exception as e_classify: logger.error(f"Chyba klasifikace '{fname}': {e_classify}", exc_info=True); self.log_message(f"CHYBA: Klasifikace '{fname}' selhala."); messagebox.showerror(f"Chyba klasifikace '{fname}'", f"Klasifikace selhala:\n{e_classify}", parent=self)
                        success_this_file = True
                    else: self.log_message(f"INFO [{current_process_num}/{total_files_to_process}]: Třídění přeskočeno."); logger.info(f"Uživatel odmítl klasifikaci."); success_this_file = True
                elif processed_df_this_file is not None: success_this_file = True

            # Zpracování výjimek pro TENTO soubor
            except (ConfigError, DataError, ProcessingError, ValueError, FileNotFoundError) as e:
                 errors_occurred = True; success_this_file = False
                 msg = f"CHYBA [{current_process_num}/{total_files_to_process}] u '{fname}': {e}"; self.log_message(msg); logger.error(f"start_processing: {msg}", exc_info=isinstance(e, (ProcessingError, Exception)))
                 messagebox.showerror(f"Chyba souboru '{fname}'", f"Chyba: {e}", parent=self)
                 if file_path in self.file_info_widgets: # Označíme chybu na kartičce
                      try: err_color = "red"; self.file_info_widgets[file_path]['frame'].configure(border_color=err_color); self.file_info_widgets[file_path]['config_label'].configure(text="CHYBA", text_color=err_color); self.file_info_widgets[file_path]['rows_label'].configure(text=""); self.file_info_widgets[file_path]['stats_label'].configure(text="")
                      except KeyError: pass
                 if isinstance(e, ProcessingError) and "zrušeno uživatelem" in str(e):
                      if not messagebox.askyesno("Pokračovat?", "Zpracování zrušeno.\nPokračovat se zbytkem?", parent=self): self.log_message("INFO: Zpracování dávky přerušeno."); logger.info("Zpracování přerušeno."); break
                      else: self.log_message("INFO: Pokračuji..."); logger.info("Pokračuji dávkou.")
            except Exception as e:
                 errors_occurred = True; success_this_file = False
                 msg = f"FATÁLNÍ CHYBA [{current_process_num}/{total_files_to_process}] u '{fname}': {e}"; self.log_message(msg); logger.exception(f"start_processing: Neočekávaná chyba u '{fname}': {e}")
                 messagebox.showerror(f"Chyba souboru '{fname}'", f"Neočekávaná chyba:\n{e}\nLog.", parent=self)
                 if file_path in self.file_info_widgets:
                      try: self.file_info_widgets[file_path]['frame'].configure(border_color="red"); self.file_info_widgets[file_path]['config_label'].configure(text="FATÁLNÍ CHYBA", text_color="red")
                      except KeyError: pass

            # Přidání výsledku
            if success_this_file and processed_df_this_file is not None:
                self.batch_results.append({"original_filename": fname, "dataframe": processed_df_this_file}); processed_count += 1
                if file_path in self.file_info_widgets: # Označení úspěchu
                      try: self.file_info_widgets[file_path]['frame'].configure(border_color="green")
                      except KeyError: pass
            else: # Neúspěch nebo None výsledek
                logger.warning(f"Soubor '{fname}' nebyl úspěšně zpracován nebo výsledek byl None.")
                errors_occurred=True
                if file_path in self.file_info_widgets and not success_this_file: # Označíme chybu jen pokud už není označena výjimkou
                     try:
                           current_color = self.file_info_widgets[file_path]['config_label'].cget("text_color")
                           if isinstance(current_color, str) and current_color.lower() != "red": # Pokud už není červená
                                self.file_info_widgets[file_path]['frame'].configure(border_color="orange"); self.file_info_widgets[file_path]['config_label'].configure(text="CHYBA/PŘESKOČENO", text_color="orange")
                     except KeyError: pass

            # Konec cyklu for

        # --- Po dokončení všech souborů ---
        self._finalize_processing(processed_count, total_files_to_process, errors_occurred)

# KONEC METODY start_processing

    # <<< NOVÁ POMOCNÁ METODA PRO ZOBRAZENÍ DIALOGU METADAT >>>
    def _ask_metadata_for_file(self, file_path, current_num, total_num):
        """Zobrazí dialog metadat pro daný soubor a vrátí výsledek."""
        fname = os.path.basename(file_path)
        metadata_dialog = MetadataDialog(
            master=self, filename=fname,
            is_batch=(total_num > 1),
            current_file_num=current_num,
            total_files=total_num
        )
        self.log_message(f"INFO [{current_num}/{total_num}]: Čekám na metadata pro '{fname}'...")
        logger.info(f"_ask_metadata_for_file: Zobrazuji dialog pro '{fname}'")
        # get_metadata() nyní vrací (metadata_dict|None, apply_all_bool)
        metadata_result, apply_all = metadata_dialog.get_metadata()
        logger.info(f"_ask_metadata_for_file: Výsledek pro '{fname}': Metadata={' задана' if metadata_result else ' zrušena'}, Použít pro všechny={apply_all}")
        return metadata_result, apply_all

    # <<< NOVÁ POMOCNÁ METODA PRO FINALIZACI ZPRACOVÁNÍ >>>
    def _finalize_processing(self, processed_count, total_files, errors_occurred, canceled=False):
        """Dokončí zpracování, zobrazí zprávu a povolí tlačítka."""
        logger.info(f"_finalize_processing: Dokončeno. Zpracováno: {processed_count}/{total_files}. Chyby: {errors_occurred}. Zrušeno: {canceled}")
        if not canceled: # Pokud nebylo přerušeno uživatelem hned na začátku
             self.log_message(f"INFO: Dokončeno zpracování dávky. Úspěšně: {processed_count}/{total_files}.")
             self.progressbar.set(1.0)
             self.label_progress_info.configure(text="")

             # Finální zpráva
             final_message = f"Zpracování dávky dokončeno.\n\nÚspěšně zpracováno: {processed_count} souborů\nSelhalo/Přeskočeno: {total_files - processed_count} souborů."
             msg_func = messagebox.showinfo
             if errors_occurred: final_message += "\n\nDošlo k chybám během zpracování (viz log)."; msg_func = messagebox.showwarning
             if processed_count > 0: final_message += "\n\nMůžete uložit výsledky."
             else: final_message += "\n\nŽádná data k uložení."; msg_func = messagebox.showerror if errors_occurred else messagebox.showinfo
             # Použijeme self.after pro zobrazení zprávy
             self.after(10, lambda m=final_message, f=msg_func: f("Zpracování Dokončeno", m, parent=self))

        # Povolit tlačítka po dokončení (nebo zrušení)
        try:
            self.button_import.configure(state="normal"); self.button_manage_configs.configure(state="normal")
            btn_state = "normal" if self.selected_file_paths else "disabled"; self.button_process.configure(state=btn_state)
            self._enable_save_buttons_if_ready(is_batch=True)
        except Exception as e_ui: logger.warning(f"Chyba povolování UI: {e_ui}")

# KONEC DEFINIC _ask_metadata_for_file a _finalize_processingONEC METODY start_processingNEC METODY start_processing
    def check_processing_thread(self):
        """Kontroluje, zda vlákno zpracování stále běží."""
        # Kontrola hlavního zpracovávacího vlákna
        processing_running = self.processing_thread and self.processing_thread.is_alive()
        # Kontrola vlákna pro výpočet statistik (pokud existuje)
        stats_running = hasattr(self, 'stats_thread') and self.stats_thread and self.stats_thread.is_alive()

        if processing_running or stats_running:
            # Pokud běží alespoň jedno vlákno, zkontrolujeme znovu za 100ms
            self.after(100, self.check_processing_thread)
        else:
            # Žádné relevantní vlákno neběží
            logger.info("Žádné aktivní vlákno (zpracování/statistiky). Povoluji UI.")
            # Zastavit progress bar (pokud běžel)
            self.progressbar.stop()
            self.progressbar.set(0)
            self.progressbar.configure(mode="determinate")

            # Povolit hlavní tlačítka
            self.button_import.configure(state="normal")
            self.button_manage_configs.configure(state="normal")

            # Tlačítka Zpracovat a Spočítat povolíme jen pokud máme soubor a config
            btn_state = "normal" if self.selected_file_paths and self.identified_config_path else "disabled" # Používáme selected_file_paths
            # Musíme ošetřit, pokud identified_config_path ještě není definován
            if not hasattr(self, 'identified_config_path'): self.identified_config_path = None
            btn_state = "normal" if self.selected_file_paths and self.identified_config_path else "disabled"

            try: # Ošetření pro případ, že UI už neexistuje
                 self.button_process.configure(state=btn_state)
                 self.button_calc_stats.configure(state=btn_state)

                 # Povolíme tlačítka Uložit, pokud máme výsledek (pro jistotu voláme)
                 self._enable_save_buttons_if_ready(is_batch=bool(self.selected_file_paths and len(self.selected_file_paths) > 1)) # Odhad is_batch
            except Exception as e_ui:
                 logger.warning(f"Chyba při povolování UI po dokončení vlákna: {e_ui}")


    def process_file_logic(self, file_path, config_path, user_metadata):
        """Logika pro kompletní zpracování souboru (běží ve vlákně)."""
        fname=os.path.basename(file_path)
        cfg=None
        success=False
        final_stats_text = "" # Text pro finální statistiku
        untyped_count = 0 # Inicializace

        # Zakázat tlačítko pro výpočet statistik, pokud běží zpracování
        # (Musíme to dělat přes self.after, protože jsme ve vlákně)
        # self.after(0, lambda: self.button_calc_stats.configure(state="disabled"))

        try:
            # 1. Načtení konfigurace
            self.log_message(f"INFO: Používám config: {os.path.basename(config_path)}")
            logger.info(f"process_file_logic: Načítám konfiguraci: {config_path}")
            cfg=config_manager.load_config(config_path) # Může vyvolat ConfigError, ValueError

            # 2. Načtení CELÝCH dat
            self.log_message(f"INFO: Načítám kompletní data souboru...")
            logger.info(f"process_file_logic: Načítám kompletní data: {file_path}")
            df_in=data_loader.load_data(file_path) # Načteme všechna data, může vyvolat chyby
            if df_in is None: raise ValueError("Načtení kompletních dat selhalo (vrátilo None).")

            # 3. Zjištění a zobrazení PŘESNÉHO počtu řádků
            actual_row_count = len(df_in)
            self.log_message(f"INFO: Načteno {actual_row_count} řádků (kompletní data).")
            logger.info(f"process_file_logic: Načteno {actual_row_count} řádků.")
            # Aktualizujeme label v GUI přes self.after
            self.after(0, lambda count=actual_row_count: self.label_row_count.configure(text=f"Řádků: {count}"))

            # 4. Zpracování dat (kompletní pipeline)
            self.log_message(f"INFO: Zpracovávám data...")
            logger.info("process_file_logic: Zpracovávám kompletní data...")
            # Toto volání může vyvolat ConfigError, DataError, ProcessingError
            processed_df = data_processor.process_data(df_in, cfg, fname, user_metadata)

            self.log_message(f"INFO: Data zpracována.")
            logger.info("process_file_logic: Kompletní data zpracována.")
            self.last_processed_df = processed_df # Uložíme finální výsledek

            # 5. Výpočet FINÁLNÍ statistiky typů (po kompletním zpracování)
            if self.last_processed_df is not None and isinstance(self.last_processed_df, pd.DataFrame):
                try:
                    if 'TYP TRANSAKCE' in self.last_processed_df.columns:
                        total_count = len(self.last_processed_df)
                        # Zde už počítáme finální stav, včetně případných 'Neznámý'
                        # které byly nastaveny v data_processor.resolve_unknown_transactions
                        unknown_mask = (self.last_processed_df['TYP TRANSAKCE'] == data_processor.UNKNOWN_TRANSACTION_TYPE)
                        untyped_count = unknown_mask.sum() # Uložíme pro pozdější použití v dialogu
                        typed_count = total_count - untyped_count
                        # Použijeme vámi preferovaný text
                        final_stats_text = f"Známé: {typed_count} | Neznámé: {untyped_count}"
                        logger.info(f"Finální statistika typů (po zpracování): {final_stats_text}")
                    else:
                        final_stats_text = "Typy: Chyba sloupce"
                        logger.warning("process_file_logic: Nelze spočítat finální statistiku - chybí 'TYP TRANSAKCE'.")
                        untyped_count = 0 # Důležité pro logiku dialogu
                except Exception as e_stats:
                    final_stats_text = "Typy: Chyba výpočtu"
                    logger.error(f"process_file_logic: Chyba při výpočtu finální statistiky typů: {e_stats}", exc_info=True)
                    untyped_count = 0 # Důležité pro logiku dialogu
            else:
                 final_stats_text = ""
                 logger.warning("process_file_logic: Přeskakuji výpočet finálních statistik - processed_df není platný DF.")
                 untyped_count = 0 # Důležité pro logiku dialogu

            # Aktualizujeme label v GUI s FINÁLNÍ statistikou
            self.after(0, lambda text=final_stats_text: self.label_transaction_stats.configure(text=text))
            # --- Konec výpočtu finální statistiky ---

            # 6. Kontrola neznámých (pro dialog)
            unknown_count_for_dialog = untyped_count

            if unknown_count_for_dialog > 0:
                self.log_message(f"INFO: Nalezeno {unknown_count_for_dialog} nezařazených ('{data_processor.UNKNOWN_TRANSACTION_TYPE}').")
                logger.info(f"process_file_logic: Nalezeno {unknown_count_for_dialog} nezařazených.")

                user_choice = [None] # List pro předání hodnoty z dialogu
                def ask_and_classify(choice_list, u_count, filename_for_msg, parent):
                    # Tato funkce se spustí v hlavním vlákně
                    choice_list[0] = messagebox.askyesno(
                        "Neznámé Transakce",
                        f"Nalezeno {u_count} nezařazených.\nChcete je zkusit rozdělit podle částky (Příchozí/Odchozí)?",
                        icon='warning', parent=parent)

                def ask_and_continue_wrapper():
                    # Spustí dialog v hlavním vlákně
                    ask_and_classify(user_choice, unknown_count_for_dialog, fname, parent=self)
                    # Po zavření dialogu zavolá pokračování (stále ve vlákně, ale naplánované přes after)
                    self.continue_processing_after_ask(user_choice[0], self.last_processed_df, fname)

                # Naplánuje spuštění wrapperu v hlavním vlákně
                self.after(0, ask_and_continue_wrapper)
                # Vlákno zde může skončit, UI se aktualizuje v check_processing_thread
                # po dokončení continue_processing_after_ask

            else: # Případ, kdy NEJSOU žádné neznámé transakce
                logger.info("process_file_logic: Nebyly nalezeny žádné neznámé transakce.")
                success=True
                # Zobrazíme info zprávu
                self.after(50, lambda fname=fname: messagebox.showinfo("Připraveno", f"'{fname}' zpracován.\nMůžete uložit výsledek.", parent=self))
                # Povolení tlačítek řeší check_processing_thread

        # --- Zpracování výjimek ---
        except FileNotFoundError as e:
             success = False; self.last_processed_df = None; msg=f"CHYBA: Soubor nenalezen: {e}"; self.log_message(msg); logger.error(f"process_file_logic: FileNotFoundError: {e}", exc_info=True); self.after(0, lambda e=e: messagebox.showerror("Chyba Souboru", f"Soubor nenalezen:\n{e}", parent=self))
        except (ConfigError, DataError, ProcessingError, ValueError) as e: # Zachytáváme naše chyby + ValueError
             success = False; self.last_processed_df = None; msg=f"CHYBA ZPRACOVÁNÍ: {e}"; self.log_message(msg); logger.error(f"process_file_logic: Chyba zpracování/dat/konfigurace: {e}", exc_info=True); self.after(0, lambda e=e: messagebox.showerror("Chyba Zpracování", f"Při zpracování došlo k chybě:\n\n{e}", parent=self))
        except Exception as e:
             # Obecná chyba
             success = False; self.last_processed_df = None; msg=f"FATÁLNÍ CHYBA: {e}"; self.log_message(msg); logger.exception(f"process_file_logic: Neočekávaná chyba ve vlákně: {e}"); self.after(0, lambda e=e: messagebox.showerror("Neočekávaná Chyba", f"Došlo k neočekávané chybě:\n{e}\n\nZkontrolujte log.", parent=self))
        # finally blok zde není nutný, UI se aktualizuje v check_processing_thread

    # KONEC METODY process_file_logic


    def continue_processing_after_ask(self, user_answer, df_processed, filename):
        """Zpracuje odpověď uživatele na dotaz o klasifikaci a aktualizuje stav."""
        # df_processed je DF *před* dodatečnou klasifikací (ale už po hlavním zpracování)
        final_df_to_save = df_processed
        process_success = True # Předpokládáme úspěch, pokud klasifikace neselže
        stats_text_after = "" # Text pro statistiku PO klasifikaci

        if user_answer is True:
            self.log_message("INFO: Aplikuji dodatečné třídění dle částky...")
            logger.info("continue_processing_after_ask: Aplikuji dodatečné třídění.")
            if hasattr(data_processor, 'classify_unknown_by_amount'):
                try:
                    if df_processed is not None:
                        # Výsledek klasifikace uložíme
                        classified_df = data_processor.classify_unknown_by_amount(df_processed.copy()) # Pracujeme s kopií
                        # Ověříme, zda vrácená data jsou platná
                        if classified_df is not None and isinstance(classified_df, pd.DataFrame):
                            final_df_to_save = classified_df
                            self.log_message("INFO: Dodatečné třídění dokončeno.")
                            logger.info("continue_processing_after_ask: Dodatečné třídění dokončeno.")
                        else:
                            logger.error("continue_processing_after_ask: Funkce classify_unknown_by_amount vrátila neplatná data.")
                            process_success = False # Označíme jako neúspěch
                            # Ponecháme původní df_processed
                    else:
                         logger.error("continue_processing_after_ask: Nelze klasifikovat, vstupní DF je None.")
                         process_success = False
                         # final_df_to_save zůstává None nebo původní hodnota
                except Exception as e:
                    logger.error(f"continue_processing_after_ask: Chyba při dodatečné klasifikaci: {e}", exc_info=True)
                    self.log_message(f"CHYBA: Klasifikace selhala: {e}")
                    process_success = False
                    # final_df_to_save zůstává původní df_processed
                    messagebox.showerror("Chyba klasifikace", f"Dodatečná klasifikace selhala:\n{e}", parent=self)
            else:
                self.log_message("WARN: Funkce classify_unknown_by_amount není implementována.")
                logger.warning("continue_processing_after_ask: Funkce classify_unknown_by_amount není dostupná.")
                # final_df_to_save zůstává původní df_processed
        elif user_answer is False:
            self.log_message("INFO: Neznámé transakce nebudou tříděny.")
            logger.info("continue_processing_after_ask: Uživatel odmítl třídění.")
            # final_df_to_save zůstává původní df_processed
        else: # Odpověď byla None (zrušeno)
            self.log_message("INFO: Dodatečné třídění nebylo provedeno (dialog zrušen).")
            logger.info("continue_processing_after_ask: Dodatečné třídění zrušeno.")
            # final_df_to_save zůstává původní df_processed
            # Stále to považujeme za "úspěšné" dokončení procesu z hlediska uživatele

        # Uložíme finální DataFrame (může být upravený nebo původní)
        self.last_processed_df = final_df_to_save

        # --- PŘEPOČÍTÁNÍ STATISTIKY PO KLASIFIKACI ---
        if self.last_processed_df is not None and isinstance(self.last_processed_df, pd.DataFrame):
            try:
                if 'TYP TRANSAKCE' in self.last_processed_df.columns:
                    total_count = len(self.last_processed_df)
                    unknown_mask = (self.last_processed_df['TYP TRANSAKCE'] == data_processor.UNKNOWN_TRANSACTION_TYPE)
                    untyped_count_after = unknown_mask.sum()
                    typed_count_after = total_count - untyped_count_after
                    # Použijeme váš formát
                    stats_text_after = f"Známé: {typed_count_after} | Neznámé: {untyped_count_after}"
                    logger.info(f"Statistika typů (po klasifikaci/dialogu): {stats_text_after}")
                else:
                    stats_text_after = "Typy: Chyba sloupce"
            except Exception as e_stats:
                stats_text_after = "Typy: Chyba výpočtu"
                logger.error(f"continue_processing_after_ask: Chyba při přepočtu statistiky: {e_stats}", exc_info=True)
        else:
            stats_text_after = "" # Pokud DF není platný

        # Aktualizujeme label v GUI s novou (nebo stejnou) statistikou
        self.after(0, lambda text=stats_text_after: self.label_transaction_stats.configure(text=text))
        # --- KONEC PŘEPOČÍTÁNÍ ---

        # Zobrazíme finální zprávu (pokud byl proces úspěšný i po klasifikaci)
        if process_success:
             # Zobrazíme zprávu jen pokud uživatel dialog nezrušil (user_answer není None)
             if user_answer is not None:
                self.after(50, lambda fname=filename: messagebox.showinfo("Připraveno", f"'{fname}' zpracován.\nMůžete uložit výsledek.", parent=self))
        # else: # Chybová hláška byla zobrazena už výše

     # UVNITŘ TŘÍDY App(ctk.CTk):

    def _enable_save_buttons_if_ready(self, is_batch=False):
        """Povolí nebo zakáže VŠECHNA tlačítka pro uložení podle stavu výsledků."""
        can_save = False
        if is_batch:
            # V batch režimu povolíme save, pokud máme seznam platných výsledků
            can_save = hasattr(self, 'batch_results') and isinstance(self.batch_results, list) and bool(self.batch_results)
            # Můžeme přidat kontrolu, zda batch_results nejsou jen prázdné DF, ale zatím ne
        else:
            # V režimu jednoho souboru (aktuálně nepoužíváme, ale pro úplnost)
            can_save = (hasattr(self, 'last_processed_df') and
                        self.last_processed_df is not None and
                        isinstance(self.last_processed_df, pd.DataFrame) and
                        not self.last_processed_df.empty)

        state = "normal" if can_save else "disabled"
        logger.debug(f"Nastavuji stav tlačítek Uložit na: {state} (is_batch={is_batch})")
        try:
            # Povolíme/zakážeme VŠECHNA tlačítka najednou
            if hasattr(self, 'button_save_csv'):
                 self.button_save_csv.configure(state=state)
            if hasattr(self, 'button_save_csv_dot'): # <<< PŘIDÁNA KONTROLA A NASTAVENÍ
                 self.button_save_csv_dot.configure(state=state)
            if hasattr(self, 'button_save_xlsx'):
                 self.button_save_xlsx.configure(state=state)
        except Exception as e:
            logger.warning(f"Nepodařilo se nastavit stav tlačítek Uložit: {e}")
# UVNITŘ TŘÍDY App(ctk.CTk):

    # Metoda save_batch_results - OPRAVA č. X+1 - Konzistentní _vysledek
    def save_batch_results(self, format_type, decimal_separator=','):
        """Uloží výsledky dávkového zpracování do vybraného adresáře.
           Umožňuje uživateli upravit část názvu PŘED '_vysledek'.
           Výstupní názvy jsou vždy <upraveny_zaklad>_vysledek.<format> nebo
           <upraveny_zaklad>_<orig_nazev>_vysledek.<format>."""
        if not hasattr(self, 'batch_results') or not self.batch_results:
            messagebox.showerror("Žádná Data", "Nejsou výsledky k uložení.", parent=self); return

        num_results = len(self.batch_results)
        format_desc = format_type.upper()
        if format_type == 'csv': format_desc += f" (des. odd. '{decimal_separator}')"
        logger.info(f"Zahajuji ukládání {num_results} souborů jako {format_desc}.")

        # --- Dialog pro výběr cíle a úpravu základu názvu ---
        try: first_original_filename = self.batch_results[0].get("original_filename", "vysledek"); default_first_base = os.path.splitext(first_original_filename)[0]
        except IndexError: default_first_base = "vysledek"
        file_ext = f".{format_type}"; initial_filename = f"{default_first_base}_vysledek{file_ext}"
        filetypes = [(f"{format_type.upper()} (*{file_ext})", f"*{file_ext}"), ("Všechny", "*.*")]
        initial_dir_export = self.last_export_dir if os.path.isdir(self.last_export_dir) else "."

        save_filepath_template = filedialog.asksaveasfilename(
            title=f"Uložit jako {format_desc} - Upravte název (část PŘED _vysledek) a vyberte adresář",
            initialfile=initial_filename, # Nabídneme název včetně _vysledek
            defaultextension=file_ext,
            filetypes=filetypes,
            initialdir=initial_dir_export,
            parent=self
        )

        if not save_filepath_template: self.log_message("INFO: Ukládání zrušeno."); logger.info("Ukládání zrušeno."); return

        # Získáme adresář a CELÝ název souboru zadaný uživatelem
        output_directory = os.path.dirname(save_filepath_template)
        user_filename = os.path.basename(save_filepath_template)
        # Z CELÉHO názvu odstraníme POUZE příponu, abychom získali základ VČETNĚ _vysledek (nebo co tam uživatel napsal)
        user_name_without_ext = os.path.splitext(user_filename)[0]
        # Pokud je výsledek prázdný (uživatel smazal vše), použijeme výchozí
        if not user_name_without_ext:
            user_name_without_ext = f"{default_first_base}_vysledek"

        self.last_export_dir = output_directory
        logger.info(f"Cílový adresář: '{output_directory}', Vzorový název (bez přípony): '{user_name_without_ext}'")
        # --- Konec dialogu ---

        # --- Ukládání jednotlivých souborů ---
        saved_count = 0; error_count = 0; skipped_count = 0; errors_occurred = False
        self.progressbar.set(0); self.progressbar.configure(mode="determinate")
        self.log_message(f"INFO: Ukládám {num_results} výsledků do adresáře: {output_directory}"); self.update_idletasks()

        for i, result_item in enumerate(self.batch_results):
            current_file_num = i + 1; progress_value = float(i) / num_results
            self.progressbar.set(progress_value); self.update_idletasks()
            original_filename = result_item.get("original_filename"); df_to_save = result_item.get("dataframe")

            if original_filename is None or df_to_save is None or not isinstance(df_to_save, pd.DataFrame) or df_to_save.empty:
                 is_empty = " (prázdný)" if df_to_save is not None and df_to_save.empty else " (neplatná data)"
                 log_msg = f"INFO [{current_file_num}/{num_results}]: Přeskakuji '{original_filename or '?'}'{is_empty}."; self.log_message(log_msg); logger.info(f"save_batch_results: {log_msg}"); skipped_count += 1; continue

            # <<< OPRAVENÉ SESTAVENÍ NÁZVU >>>
            base_name_orig = os.path.splitext(original_filename)[0]
            # Pokud zpracováváme jen jeden soubor, použijeme přímo název z dialogu (bez přípony) + přípona
            if num_results == 1:
                 output_filename = f"{user_name_without_ext}.{format_type}"
            else:
                 # Pokud je více souborů, použijeme název z dialogu a přidáme původní název pro rozlišení
                 # Zajistíme, že tam nebude dvakrát "_vysledek", pokud ho uživatel nechal
                 base_for_multi = user_name_without_ext
                 if base_for_multi.lower().endswith("_vysledek"): base_for_multi = base_for_multi[:-len("_vysledek")]
                 output_filename = f"{base_for_multi}_{base_name_orig}_vysledek.{format_type}" # Přidáme _vysledek explicitně
                 # Alternativní číslování:
                 # output_filename = f"{base_for_multi}_{current_file_num}_vysledek.{format_type}"

            output_filepath = os.path.join(output_directory, output_filename)
            # <<< KONEC OPRAVENÉHO SESTAVENÍ >>>

            self.log_message(f"INFO [{current_file_num}/{num_results}]: Ukládám '{output_filename}'...")
            try:
                save_kwargs = {};
                if format_type == 'csv': save_kwargs['decimal_separator'] = decimal_separator
                save_success = data_exporter.save_data(df_to_save.copy(), output_filepath, format_type, **save_kwargs)

                if save_success:
                    try: data_exporter.save_unknown_transactions(df_to_save.copy(), base_name_orig, output_directory)
                    except Exception as e_unk: logger.error(f"Chyba ukládání neznámých pro '{base_name_orig}': {e_unk}", exc_info=True); self.log_message(f"VAROVÁNÍ: Uložení neznámých pro '{output_filename}' selhalo.")
                    saved_count += 1
            except (IOError, ValueError, Exception) as e_save:
                 error_count += 1; errors_occurred = True
                 msg = f"CHYBA [{current_file_num}/{num_results}]: Uložení '{output_filename}' selhalo: {e_save}"; self.log_message(msg); logger.error(f"save_batch_results: {msg}", exc_info=True)
                 if not messagebox.askyesno("Chyba při ukládání", f"Nepodařilo se uložit:\n'{output_filename}'\n\nChyba: {e_save}\n\nPokračovat?", parent=self):
                      self.log_message("INFO: Ukládání přerušeno."); logger.info("Ukládání přerušeno."); break

        # --- Po dokončení ---
        # (Zbytek metody pro zobrazení finální zprávy zůstává stejný)
        self.progressbar.set(1.0)
        final_save_message = f"Ukládání dávky dokončeno.\n\nAdresář: {output_directory}\n\nÚspěšně: {saved_count}\nPřeskočeno: {skipped_count}\nSelhalo: {error_count}"; msg_func = messagebox.showinfo
        if errors_occurred or error_count > 0: final_save_message += "\n\nDošlo k chybám (viz log)."; msg_func = messagebox.showwarning
        # Použijeme self.after pro zobrazení zprávy
        self.after(10, lambda m=final_save_message, f=msg_func: f("Ukládání Dokončeno", m, parent=self))
        self.log_message(f"INFO: Ukládání dokončeno. {saved_count}/{num_results} uloženo.")

# KONEC METODY save_batch_results (Oprava 6)# KONEC METODY save_batch_resultsONEC METODY save_batch_resultsNEC METODY save_batch_resultsNEC METODY save_as
    def open_config_manager_window(self):
        """Otevře okno pro správu konfigurací."""
        # Zkontroluje, zda okno již existuje a je viditelné
        if self.config_window is None or not self.config_window.winfo_exists():
            self.config_window = ConfigManagerWindow(self) # Vytvoří nové okno
            self.config_window.grab_set() # Zajistí, že je modální
            self.log_message("INFO: Otevřen Správce Konfigurací.")
        else:
            self.config_window.focus() # Pokud již existuje, přenese ho do popředí
            self.log_message("INFO: Aktivován existující Správce Konfigurací.")

# --- Třída ConfigManagerWindow ---
# (Verze se všemi předchozími opravami mapování a jump-to-char)
class ConfigManagerWindow(ctk.CTkToplevel):
    # Konstruktor __init__
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("Správa Konfigurací")
        self.geometry("1200x900") # Dostatečná velikost pro komplexní UI
        self.minsize(1000, 700) # Minimální rozumná velikost

        self.selected_config_path = None
        self.loaded_config_data = None
        self.source_columns = [] # Sloupce ze vzorového souboru
        self.sample_data = None  # DataFrame s náhledem dat
        self.current_mapping = {} # Aktuálně nastavené mapování sloupců {zdroj: cíl}
        self.config_filename_var = StringVar() # Pro název konfiguračního souboru
        self.all_expected_columns_vars = {} # Pro checkboxy očekávaných sloupců

        # Pravidla jsou nyní SEZNAMY slovníků, každý s unikátním GUI ID
        self.current_rules = []
        self.current_ignore_rules = []

        # Proměnné pro statistiky a náhled
        self.rule_stats_label = None
        self.show_only_untyped_var = BooleanVar(value=False) # Pro budoucí filtrování náhledu
        self.full_sample_data_stats = None # Pro případné počítání statistik z celého vzorku
        self.calculating_stats_thread = None # Pro výpočty na pozadí
        self.current_sample_filepath = None # Cesta k načtenému vzorovému souboru

        # Vytvoření UI
        self._setup_ui_layout()
        # Načtení seznamu konfigurací
        self.refresh_config_list()

      # UVNITŘ TŘÍDY ConfigManagerWindow(ctk.CTkToplevel):

    def select_or_create_config(self, config_path_to_select, source_file_path_for_sample):
        """Vybere existující konfiguraci v seznamu a načte ji pro editaci,
           nebo spustí vytvoření nové a načte vzorový soubor."""
        logger.info(f"select_or_create_config: config_path='{config_path_to_select}', source_file='{source_file_path_for_sample}'")
        self.focus() # Přeneseme focus na toto okno

        if config_path_to_select and os.path.exists(config_path_to_select):
            # --- MÁME EXISTUJÍCÍ KONFIGURACI ---
            config_name = os.path.basename(config_path_to_select)
            logger.debug(f"Hledám a vybírám '{config_name}' v seznamu...")
            try:
                listbox_items = list(self.config_listbox.get(0, END))
                if config_name in listbox_items:
                    idx = listbox_items.index(config_name)
                    # Potřebujeme zajistit, že starý výběr je zrušen a nový nastaven
                    # a že se spustí on_config_select, aby se aktualizoval self.selected_config_path
                    self.config_listbox.selection_clear(0, END)
                    self.config_listbox.selection_set(idx)
                    self.config_listbox.see(idx)
                    self.config_listbox.activate(idx)
                    # Manuálně zavoláme on_config_select, aby se nastavila cesta
                    self.on_config_select()
                    logger.info(f"Konfigurace '{config_name}' vybrána.")

                    # <<< IHNED SPUSTÍME EDITACI >>>
                    # Potřebujeme krátké zpoždění, aby se stihl aktualizovat self.selected_config_path v on_config_select
                    self.after(50, self.edit_selected_config)
                    # self.edit_selected_config() # Přímé volání nemusí fungovat kvůli časování

                    # Pokud máme vzorový soubor, načteme ho PO zobrazení editoru
                    if source_file_path_for_sample and os.path.exists(source_file_path_for_sample):
                         # Naplánujeme načtení vzorku až po krátké pauze, aby se stihl načíst editor
                         self.after(150, lambda: self._load_specific_sample(source_file_path_for_sample))

                else: # Konfig existuje, ale není v seznamu
                    logger.warning(f"Konfigurace '{config_name}' ({config_path_to_select}) nalezena, ale není v seznamu. Obnovuji.")
                    self.refresh_config_list()
                    messagebox.showinfo("Seznam Obnoven", f"Konfigurace '{config_name}' nebyla v seznamu. Seznam byl obnoven, vyberte ji prosím ručně.", parent=self)

            except Exception as e:
                logger.error(f"Chyba při výběru/editaci konfigurace '{config_name}': {e}", exc_info=True)
                messagebox.showerror("Chyba výběru", f"Nepodařilo se automaticky vybrat/načíst konfiguraci '{config_name}'.", parent=self)

        elif source_file_path_for_sample and os.path.exists(source_file_path_for_sample):
            # --- KONFIGURACE NEEXISTUJE, VYTVÁŘÍME NOVOU ---
            logger.info(f"Konfigurace nenalezena nebo neplatná. Vytvářím novou s použitím vzoru: {os.path.basename(source_file_path_for_sample)}")
            # Spustíme standardní proces vytvoření nové
            self.create_new_config_ui()
            # A hned se pokusíme načíst daný soubor jako vzorový
            # Použijeme after, aby se nejprve stihlo vytvořit UI editoru
            self.after(50, lambda: self._load_specific_sample(source_file_path_for_sample))

        else:
            # Nemáme ani existující konfig, ani platný zdrojový soubor
            logger.warning("select_or_create_config voláno bez platných parametrů.")
            messagebox.showwarning("Chybí informace", "Nelze určit konfiguraci k úpravě ani soubor pro vytvoření nové.", parent=self)

# KONEC METODY select_or_create_config
    def _load_specific_sample(self, file_path):
        """Načte specifický soubor jako vzorový bez otevření dialogu."""
        if not file_path or not os.path.exists(file_path):
             logger.warning(f"_load_specific_sample: Neplatná cesta k souboru: {file_path}")
             return

        self.current_sample_filepath = file_path
        self.full_sample_data_stats = None
        logger.info(f"Načítám specifický vzorový soubor: {file_path}")

        try:
            # Stejná logika načítání jako v load_sample_file, ale bez dialogu
            df_preview=None; df_columns_only=None; NROWS_PREVIEW=20
            file_extension = os.path.splitext(file_path)[1].lower()

            if file_extension == '.csv':
                 # ... (zkopírovaná logika pro načtení CSV s více pokusy) ...
                 encodings_to_try = ['cp1250', 'utf-8', 'latin1']; separators_to_try = [';', ',']; loaded_ok = False
                 for enc in encodings_to_try:
                      for sep in separators_to_try:
                          try:
                              df_preview = pd.read_csv(file_path, encoding=enc, sep=sep, nrows=NROWS_PREVIEW, skipinitialspace=True, low_memory=False)
                              df_columns_only = pd.read_csv(file_path, encoding=enc, sep=sep, nrows=0, skipinitialspace=True)
                              logger.info(f"_load_specific_sample: CSV načteno ({enc}, '{sep}')."); loaded_ok = True; break
                          except Exception: continue
                      if loaded_ok: break
                 if not loaded_ok: raise ValueError("Nepodařilo se načíst CSV vzorek.")
            elif file_extension in ['.xlsx', '.xls']:
                 df_preview = pd.read_excel(file_path, nrows=NROWS_PREVIEW)
                 df_columns_only = pd.read_excel(file_path, nrows=0)
                 logger.info("_load_specific_sample: Excel načten.")
            else: raise ValueError("Nepodporovaný formát.")

            if df_preview is None or df_columns_only is None: raise ValueError("Chyba při načítání dat vzorku.")

            self.sample_data = df_preview
            self.source_columns = sorted([str(c).strip() for c in df_columns_only.columns])

            fname = os.path.basename(file_path)
            self.sample_file_label.configure(text=f"Vzor: {fname} ({len(self.source_columns)} sl.)")
            log_msg=f"Automaticky načten vzor '{fname}' ({len(self.source_columns)} sl.)."
            self.master_app.log_message(f"INFO: {log_msg}"); logger.info(log_msg)

            # Aktualizujeme UI editoru
            self.update_source_columns_list(); self.update_data_preview(); self.update_mapping_display();
            self.update_expected_columns_checklist(); self.update_rule_statistics()

        except Exception as e:
            fname = os.path.basename(file_path) if file_path else "neznámý"
            log_msg=f"Automatické načtení vzoru '{fname}' selhalo: {e}"; self.master_app.log_message(f"CHYBA: {log_msg}"); logger.error(log_msg, exc_info=True)
            messagebox.showerror("Chyba Načítání Vzorku", f"Automatické načtení vzorku selhalo:\n{e}", parent=self)
            self.source_columns=[]; self.sample_data=None; self.current_sample_filepath=file_path # Cestu necháme
            self.sample_file_label.configure(text="Chyba načtení vzorku!"); self.update_source_columns_list(); self.update_data_preview(); self.update_expected_columns_checklist(); self.update_rule_statistics()

# KONEC METODY _load_specific_sample

    def edit_selected_ignore_rule_ui(self):
        """Otevře dialog pro úpravu vybraného pravidla ignorování."""
        selected_items = self.ignore_rules_tree.selection()
        if not selected_items:
            messagebox.showwarning("Není vybráno", "Nejprve vyberte pravidlo ignorování, které chcete upravit.", parent=self)
            return

        selected_rule_id = selected_items[0]
        # Najdeme data pravidla podle jeho GUI ID v seznamu ignore pravidel
        rule_data_to_edit = self._get_rule_data_by_id(selected_rule_id, self.current_ignore_rules)

        if not rule_data_to_edit:
            logger.error(f"Nepodařilo se najít data pro ignore pravidlo s ID: {selected_rule_id}")
            messagebox.showerror("Chyba", "Data vybraného pravidla ignorování nebyla nalezena.", parent=self)
            return

        # Otevřeme dialog AddRuleDialog v režimu pro ignore pravidla a předáme data
        dialog = AddRuleDialog(
            master=self,
            existing_types=[], # Ignorujeme typy
            searchable_columns_list=POTENTIAL_SEARCH_COLUMNS,
            is_ignore_rule=True, # Důležité - říkáme, že jde o ignore pravidlo
            rule_data=rule_data_to_edit # Předáme data k editaci
        )
        updated_rule_data = dialog.get_rule_data() # Získáme upravená data

        if updated_rule_data:
            # Najdeme původní pravidlo v seznamu a nahradíme ho upraveným
            updated = False
            original_id = updated_rule_data.get("_id") # ID by mělo zůstat stejné
            if isinstance(self.current_ignore_rules, list) and original_id:
                 for i, rule in enumerate(self.current_ignore_rules):
                      if isinstance(rule, dict) and rule.get("_id") == original_id:
                          self.current_ignore_rules[i] = updated_rule_data # Nahradíme
                          updated = True
                          break
            if updated:
                log_msg = f"Upraveno ignore pravidlo (ID:{original_id}): {updated_rule_data}"
                self.master_app.log_message("INFO: Upraveno pravidlo ignorování.")
                logger.info(log_msg)
                # Aktualizujeme zobrazení seznamu ignore pravidel
                self.update_ignore_rules_display()
                # self.update_data_preview() # Změna ignore pravidla neovlivní náhled
                # self.update_rule_statistics() # Ani statistiky typů
            else:
                logger.error(f"Nepodařilo se najít ignore pravidlo ID {original_id} pro uložení úprav.")
                messagebox.showerror("Chyba Uložení", "Uložení změn pravidla ignorování selhalo.", parent=self)

# KONEC METODY edit_selected_ignore_rule_ui

    # --- Metody pro sestavení UI ---
    def _setup_ui_layout(self):
        """Rozdělí okno na levý (seznam) a pravý (editor) panel."""
        self.grid_columnconfigure(1, weight=1) # Pravý panel se roztáhne
        self.grid_rowconfigure(0, weight=1)    # Oba panely se roztáhnou vertikálně

        # --- Levý panel ---
        self.left_panel = ctk.CTkFrame(self, width=280)
        self.left_panel.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ns") # Jen vertikálně
        self.left_panel.grid_rowconfigure(1, weight=1) # Listbox se roztáhne

        ctk.CTkLabel(self.left_panel, text="Dostupné Konfigurace:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")

        # Rámec pro Listbox a Scrollbar
        self.config_list_frame = ctk.CTkFrame(self.left_panel)
        self.config_list_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

        # Listbox pro zobrazení konfigurací (používáme standardní Tkinter pro barvy)
        self.config_listbox = Listbox(
            self.config_list_frame,
            borderwidth=0,
            selectmode=SINGLE,
            activestyle='none', # Bez podtržení aktivní položky
            bg=UNMAPPED_ITEM_COLOR, # Barva pozadí
            fg="white",             # Barva textu
            selectbackground=MAPPED_ITEM_COLOR, # Barva pozadí vybrané
            selectforeground="white",          # Barva textu vybrané
            font=("Segoe UI", 12),
            exportselection=False # Aby výběr nezmizel při focusu jinam
            )
        # Scrollbar pro Listbox (používáme CTk Scrollbar)
        self.config_list_scrollbar = ctk.CTkScrollbar(self.config_list_frame, command=self.config_listbox.yview)
        self.config_listbox.configure(yscrollcommand=self.config_list_scrollbar.set)
        self.config_list_scrollbar.pack(side=RIGHT, fill=Y)
        self.config_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        # Navázání události výběru na metodu
        self.config_listbox.bind("<<ListboxSelect>>", self.on_config_select)

        # Tlačítka pod seznamem konfigurací
        button_frame_left = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        button_frame_left.grid(row=2, column=0, padx=10, pady=(10, 10), sticky="ew")

        ctk.CTkButton(button_frame_left, text="Nová Konfigurace", command=self.create_new_config_ui).pack(pady=3, fill=X)
        self.button_edit_config = ctk.CTkButton(button_frame_left, text="Upravit Vybranou", command=self.edit_selected_config, state="disabled")
        self.button_edit_config.pack(pady=3, fill=X)
        self.button_delete_config = ctk.CTkButton(button_frame_left, text="Smazat Vybranou", command=self.delete_selected_config, state="disabled", fg_color="#D32F2F", hover_color="#B71C1C")
        self.button_delete_config.pack(pady=3, fill=X)
        ctk.CTkButton(button_frame_left, text="Obnovit Seznam", command=self.refresh_config_list).pack(pady=(10, 3), fill=X)

        # --- Pravý panel (Scrollable Frame pro editor) ---
        self.right_panel = ctk.CTkScrollableFrame(self)
        self.right_panel.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")

        # Placeholder pro případ, že nic není vybráno
        self.placeholder_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.placeholder_label = ctk.CTkLabel(self.placeholder_frame, text="", wraplength=400)

        # Hlavní rámec pro editor (bude se zobrazovat/skrývat)
        self.editor_main_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")

    # Metoda pro obnovení seznamu konfigurací
    def refresh_config_list(self):
        """Načte znovu seznam .json souborů z adresáře konfigurací."""
        self.config_listbox.delete(0, END) # Vymaže starý seznam
        self.selected_config_path = None
        # Zakáže tlačítka Upravit/Smazat
        self.button_edit_config.configure(state="disabled")
        self.button_delete_config.configure(state="disabled")
        # Skryje editor a zobrazí placeholder
        self.clear_editor_panel(show_placeholder=True, text="Vyberte konfiguraci ze seznamu vlevo nebo vytvořte novou.")
        try:
            configs = config_manager.get_all_config_files()
            config_names = sorted([os.path.basename(p) for p in configs])
            for name in config_names:
                self.config_listbox.insert(END, name)
            self.master_app.log_message(f"INFO: Načteno {len(config_names)} konfiguračních souborů.")
        except Exception as e:
            self.master_app.log_message(f"CHYBA: Načtení seznamu konfigurací selhalo: {e}")
            logger.error(f"Chyba při načítání seznamu konfigurací: {e}", exc_info=True)
            messagebox.showerror("Chyba Načítání", f"Načtení seznamu konfigurací selhalo:\n{e}", parent=self)

    # Metoda volaná při výběru konfigurace v listboxu
    def on_config_select(self, event=None):
        """Zpracuje výběr konfigurace v levém listboxu."""
        idxs = self.config_listbox.curselection() # Získá index vybrané položky
        if not idxs: # Pokud nic není vybráno
            self.selected_config_path = None
            self.button_edit_config.configure(state="disabled")
            self.button_delete_config.configure(state="disabled")
            # self.clear_editor_panel(show_placeholder=True) # Zakomentováno pro debug
            logger.debug("on_config_select: No selection, clear_editor_panel skipped (debug).")
            return

        # Získáme název a sestavíme cestu
        name = self.config_listbox.get(idxs[0])
        self.selected_config_path = os.path.join(config_manager.CONFIGS_DIR, name)
        # Povolíme tlačítka
        self.button_edit_config.configure(state="normal")
        self.button_delete_config.configure(state="normal")
        self.master_app.log_message(f"INFO: Vybrána konfigurace: {name}")
        # Zobrazíme výzvu v pravém panelu
        # self.clear_editor_panel(show_placeholder=True, text=f"Vybrána konfigurace '{name}'.\n\nKlikněte na 'Upravit Vybranou'.") # Zakomentováno pro debug
        logger.debug(f"on_config_select: Selected '{name}', clear_editor_panel skipped (debug).")

    # Metoda pro smazání vybrané konfigurace
    def delete_selected_config(self):
        """Smaže soubor vybrané konfigurace po potvrzení."""
        if not self.selected_config_path:
            messagebox.showwarning("Není vybráno", "Nejprve vyberte konfiguraci, kterou chcete smazat.", parent=self)
            return

        name = os.path.basename(self.selected_config_path)
        if messagebox.askyesno("Potvrdit smazání", f"Opravdu chcete trvale smazat konfigurační soubor '{name}'?", icon='warning', parent=self):
            try:
                os.remove(self.selected_config_path)
                self.master_app.log_message(f"INFO: Konfigurace '{name}' byla smazána.")
                logger.info(f"Smazána konfigurace: {self.selected_config_path}")
                self.refresh_config_list() # Obnovíme seznam
                # Po smazání zobrazíme placeholder
                self.clear_editor_panel(show_placeholder=True)
            except Exception as e:
                self.master_app.log_message(f"CHYBA: Smazání konfigurace '{name}' selhalo: {e}")
                logger.error(f"Chyba při mazání konfigurace {self.selected_config_path}: {e}", exc_info=True)
                messagebox.showerror("Chyba Mazání", f"Smazání konfigurace selhalo:\n{e}", parent=self)

    # Metoda pro vytvoření UI pro novou konfiguraci
    def create_new_config_ui(self):
        """Připraví editor pro zadání nové konfigurace."""
        self.master_app.log_message("INFO: Vytváření nové konfigurace...")
        self.selected_config_path = None # Není vybrán žádný existující soubor
        self.config_listbox.selection_clear(0, END) # Zrušíme výběr v seznamu
        # Zakážeme tlačítka Upravit/Smazat
        self.button_edit_config.configure(state="disabled")
        self.button_delete_config.configure(state="disabled")

        # Inicializujeme prázdná data pro novou konfiguraci
        self.loaded_config_data = {
            "identification": {"all_expected_columns": [], "header_contains": []},
            "column_mapping": {},
            "transaction_types": [],
            "ignore_rows_rules": []
        }
        self.source_columns = []
        self.sample_data = None
        self.current_mapping = {}
        self.current_rules = []
        self.current_ignore_rules = []
        self.current_sample_filepath = None
        self.config_filename_var.set("nova_konfigurace.json") # Výchozí název

        # Zobrazíme editor
        self.display_config_editor(is_new=True)

    # Metoda pro načtení a zobrazení existující konfigurace
    def edit_selected_config(self):
        """Načte data vybrané konfigurace a zobrazí je v editoru."""
        if not self.selected_config_path:
            messagebox.showwarning("Není vybráno", "Nejprve vyberte konfiguraci, kterou chcete upravit.", parent=self)
            return

        name = os.path.basename(self.selected_config_path)
        self.master_app.log_message(f"INFO: Načítání konfigurace pro úpravu: {name}")
        try:
            # Načteme data z JSON souboru
            self.loaded_config_data = config_manager.load_config(self.selected_config_path)
            if not isinstance(self.loaded_config_data, dict):
                raise ValueError("Načtená konfigurace není platný slovník.")

            # Resetujeme stav editoru před načtením nových dat
            self.config_filename_var.set(name)
            self.source_columns = []
            self.sample_data = None
            self.current_sample_filepath = None

            # Načteme mapování (s kontrolou typu)
            self.current_mapping = self.loaded_config_data.get("column_mapping", {})
            if not isinstance(self.current_mapping, dict):
                logger.warning(f"Neplatný formát 'column_mapping' v {name}. Používám prázdné.")
                self.current_mapping = {}

            # Načteme pravidla typů (jako seznam a přidáme GUI ID)
            loaded_rules = self.loaded_config_data.get("transaction_types", [])
            self.current_rules = []
            if isinstance(loaded_rules, list):
                 for rule in loaded_rules:
                      if isinstance(rule, dict):
                          rule_copy = rule.copy()
                          rule_copy["_id"] = str(uuid.uuid4()) # Přidáme unikátní ID pro GUI
                          self.current_rules.append(rule_copy)
            else:
                 logger.warning(f"'transaction_types' v {name} není seznam!")

            # Načteme ignore pravidla (jako seznam a přidáme GUI ID)
            loaded_ignore_rules = self.loaded_config_data.get("ignore_rows_rules", [])
            self.current_ignore_rules = []
            if isinstance(loaded_ignore_rules, list):
                 for rule in loaded_ignore_rules:
                      if isinstance(rule, dict):
                          rule_copy = rule.copy()
                          rule_copy["_id"] = str(uuid.uuid4()) # Přidáme unikátní ID pro GUI
                          self.current_ignore_rules.append(rule_copy)
            else:
                 logger.warning(f"'ignore_rows_rules' v {name} není seznam!")

            # Zobrazíme editor s načtenými daty
            self.display_config_editor(is_new=False)

        except Exception as e:
            self.master_app.log_message(f"CHYBA: Načtení konfigurace '{name}' selhalo: {e}")
            logger.error(f"Chyba při načítání konfigurace {self.selected_config_path}: {e}", exc_info=True)
            messagebox.showerror("Chyba Načítání", f"Načtení konfigurace selhalo:\n{e}", parent=self)
            self.loaded_config_data = None
            self.clear_editor_panel(show_placeholder=True) # Zobrazíme placeholder v případě chyby

    # Metoda pro vyčištění pravého panelu
    def clear_editor_panel(self, show_placeholder=False, text=""):
        """Skryje editor a volitelně zobrazí placeholder text."""
        # Skryjeme hlavní rámec editoru, pokud existuje a je viditelný
        if hasattr(self, 'editor_main_frame') and self.editor_main_frame.winfo_exists():
             if self.editor_main_frame.winfo_ismapped():
                 self.editor_main_frame.pack_forget()

        # Skryjeme placeholder, pokud existuje a je viditelný
        if hasattr(self, 'placeholder_frame') and self.placeholder_frame.winfo_exists():
             if self.placeholder_frame.winfo_ismapped():
                 self.placeholder_frame.pack_forget()

        # Zobrazíme placeholder, pokud je požadováno
        if show_placeholder:
            # Ujistíme se, že placeholder existuje
            if not hasattr(self, 'placeholder_frame') or not self.placeholder_frame.winfo_exists():
                self.placeholder_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
                self.placeholder_label = ctk.CTkLabel(self.placeholder_frame, text="", wraplength=400)
                self.placeholder_label.pack(pady=50, padx=20) # Centrovaný text

            # Nastavíme text placeholderu
            self.placeholder_label.configure(text=text if text else "Vyberte nebo vytvořte novou konfiguraci.")
            # Zobrazíme placeholder
            self.placeholder_frame.pack(fill=BOTH, expand=True)

    # Metoda pro zobrazení editoru konfigurace
    def display_config_editor(self, is_new=False):
        """Sestaví a zobrazí UI editoru konfigurace v pravém panelu."""
        self.clear_editor_panel(show_placeholder=False) # Skryjeme placeholder

        # Ujistíme se, že hlavní rámec editoru existuje
        if not hasattr(self, 'editor_main_frame') or not self.editor_main_frame.winfo_exists():
             self.editor_main_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")

        # Odstraníme starý obsah editoru (pokud existuje)
        for widget in self.editor_main_frame.winfo_children():
            widget.destroy()

        # Zobrazíme rámec editoru
        self.editor_main_frame.pack(fill=BOTH, expand=True)

        try:
            # Sestavíme jednotlivé sekce editoru
            self._build_filename_section(self.editor_main_frame, is_new)
            self._build_sample_and_id_section(self.editor_main_frame)
            self._build_preview_section(self.editor_main_frame)
            self._build_mapping_section(self.editor_main_frame)
            self._build_transaction_rules_section(self.editor_main_frame)
            self._build_ignore_rules_section(self.editor_main_frame)
            self._build_save_button_section(self.editor_main_frame, is_new)

            # Aktualizujeme obsah widgetů na základě načtených dat
            self.update_source_columns_list()
            self.update_mapping_display() # Zobrazí aktuální mapování
            self.update_data_preview()    # Zobrazí náhled dat
            self.update_expected_columns_checklist() # Aktualizuje checkboxy očekávaných sloupců
            # self.update_header_contains_text() # Pokud byste tuto sekci vrátili zpět
            self.update_rules_display()      # Zobrazí pravidla typů
            self.update_ignore_rules_display() # Zobrazí ignore pravidla
            self.update_rule_statistics()    # Aktualizuje statistiky pravidel

            logger.info("Editor konfigurace byl úspěšně sestaven a zobrazen.")
        except Exception as e:
             logger.error(f"Chyba při sestavování editoru konfigurace: {e}", exc_info=True)
             messagebox.showerror("Chyba Editoru", f"Došlo k chybě při zobrazování editoru:\n{e}", parent=self)
             # V případě chyby zobrazíme placeholder
             self.clear_editor_panel(show_placeholder=True, text="Chyba při načítání editoru.")

    # --- Metody pro sestavení jednotlivých sekcí UI editoru ---
    def _build_filename_section(self, parent, is_new):
        """Sestaví sekci pro zadání názvu konfiguračního souboru."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill=X, pady=(0, 10), padx=5)
        ctk.CTkLabel(frame, text="Název konfig. souboru:", width=160, anchor="w").pack(side=LEFT, padx=(5, 5))
        self.config_filename_entry = ctk.CTkEntry(frame, textvariable=self.config_filename_var, width=350)
        self.config_filename_entry.pack(side=LEFT, padx=5)
        if not is_new and self.selected_config_path:
            # Zobrazíme původní název v šedé barvě pro informaci
            ctk.CTkLabel(frame, text=f"(Původní: {os.path.basename(self.selected_config_path)})", text_color="gray").pack(side=LEFT, padx=(10, 5))
        else:
            ctk.CTkLabel(frame, text=".json", text_color="gray").pack(side=LEFT, padx=(0, 5))

    def _build_sample_and_id_section(self, parent):
        """Sestaví sekci pro načtení vzorového souboru a nastavení identifikace."""
        outer_frame = ctk.CTkFrame(parent)
        outer_frame.pack(fill=X, pady=5, padx=5)

        # Sekce pro vzorový soubor
        sample_frame = ctk.CTkFrame(outer_frame, fg_color="transparent")
        sample_frame.pack(fill=X, pady=(0, 10))
        ctk.CTkButton(sample_frame, text="Načíst vzorový soubor (.csv/.xlsx)", command=self.load_sample_file).pack(side=LEFT, padx=(0, 10))
        self.sample_file_label = ctk.CTkLabel(sample_frame, text="Vzorový soubor nebyl načten.")
        self.sample_file_label.pack(side=LEFT, padx=5)

        # Sekce pro identifikaci
        id_frame = ctk.CTkFrame(outer_frame)
        id_frame.pack(fill=X)
        ctk.CTkLabel(id_frame, text="Identifikace Formátu:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=5, pady=(5, 5))

        # Očekávané sloupce
        ctk.CTkLabel(id_frame, text="Očekávané sloupce (musí být všechny přítomny pro identifikaci):").pack(anchor="w", padx=5, pady=(0, 3))
        # Scrollable frame pro checkboxy sloupců
        self.expected_cols_frame = ctk.CTkScrollableFrame(id_frame, height=100, border_width=1, border_color="gray50")
        self.expected_cols_frame.pack(fill=X, padx=5, pady=(0, 10))
        # Obsah se naplní v update_expected_columns_checklist

        # Sekce pro header_contains (pokud by byla potřeba)
        # header_frame = ctk.CTkFrame(id_frame, fg_color="transparent")
        # header_frame.pack(fill=X, padx=5)
        # ctk.CTkLabel(header_frame, text="Texty v hlavičce\n(musí být v prvních 5 řádcích,\nkaždý na nový řádek):", anchor="nw").pack(side=LEFT, padx=(0, 10))
        # self.header_contains_text = ctk.CTkTextbox(header_frame, height=60, wrap="none")
        # self.header_contains_text.pack(side=LEFT, fill=X, expand=True)
        # Obsah se naplní v update_header_contains_text

    def _build_preview_section(self, parent):
        """Sestaví sekci pro náhled dat včetně Treeview."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill=X, pady=10, padx=5)
        title_frame = ctk.CTkFrame(frame, fg_color="transparent")
        title_frame.pack(fill=X, pady=(0, 5))
        ctk.CTkLabel(title_frame, text="Náhled dat ze vzorového souboru (prvních 20 řádků):", font=ctk.CTkFont(weight="bold")).pack(side=LEFT, anchor="w", padx=0)

        tree_frame = ctk.CTkFrame(frame) # Rámec pro Treeview a scrollbary
        tree_frame.pack(fill=X)

        # Konfigurace stylu pro Treeview
        style = ttk.Style()
        try:
            style.theme_use("clam") # Preferované téma pro tmavý režim
            logger.info("Nastaveno ttk téma: clam")
        except Exception:
            logger.warning("Nepodařilo se nastavit ttk téma 'clam'. Používá se výchozí.")
            try: style.theme_use("default")
            except Exception: pass # Pokud selže i default

        # Nastavení vzhledu Treeview a jeho hlaviček
        listbox_font_size = 11 # Můžete upravit
        heading_font_size = 11 # Můžete upravit
        row_height = 25        # Můžete upravit

        style.configure("Treeview",
                        background="#2B2B2B", foreground="white", fieldbackground="#2B2B2B",
                        borderwidth=0, font=('Segoe UI', listbox_font_size), rowheight=row_height)
        style.configure("Treeview.Heading",
                        background="#565B5E", foreground="white", relief="flat",
                        font=('Segoe UI', heading_font_size, 'bold'))
        style.map("Treeview.Heading", background=[('active', '#656A6D')]) # Barva při najetí myší
        # Barva vybraného řádku
        style.map("Treeview", background=[('selected', MAPPED_ITEM_COLOR)], foreground=[('selected', 'white')])

        # Vytvoření Treeview widgetu
        self.data_preview_tree = ttk.Treeview(tree_frame, show='headings', height=8, style="Treeview")

        # Definice tagu pro podbarvení zařazených řádků
        highlight_color = "#004D00" # Tmavě zelená
        self.data_preview_tree.tag_configure("matched", background=highlight_color)

        # Scrollbary pro Treeview (používáme CTk Scrollbar)
        tree_scroll_x = ctk.CTkScrollbar(tree_frame, orientation="horizontal", command=self.data_preview_tree.xview)
        tree_scroll_y = ctk.CTkScrollbar(tree_frame, orientation="vertical", command=self.data_preview_tree.yview)
        self.data_preview_tree.configure(xscrollcommand=tree_scroll_x.set, yscrollcommand=tree_scroll_y.set)

        # Umístění scrollbarů a Treeview
        tree_scroll_y.pack(side=RIGHT, fill=Y)
        tree_scroll_x.pack(side=BOTTOM, fill=X)
        self.data_preview_tree.pack(side=LEFT, fill=BOTH, expand=True)
        # Obsah se naplní v update_data_preview

    # --- Metoda _build_mapping_section ---
    # (Nová verze s bindem na Frame)
    def _build_mapping_section(self, parent):
        outer_frame = ctk.CTkFrame(parent)
        outer_frame.pack(fill=X, expand=False, pady=10, padx=5)
        outer_frame.grid_columnconfigure(0, weight=2)
        outer_frame.grid_columnconfigure(1, weight=0)
        outer_frame.grid_columnconfigure(2, weight=2)
        outer_frame.grid_columnconfigure(3, weight=3)
        outer_frame.grid_rowconfigure(1, weight=0)
        ctk.CTkLabel(outer_frame, text="Vstupní sloupce").grid(row=0, column=0, padx=5, pady=(0,5), sticky=W)
        ctk.CTkLabel(outer_frame, text="Cílové sloupce").grid(row=0, column=2, padx=5, pady=(0,5), sticky=W)
        ctk.CTkLabel(outer_frame, text="Aktuální Mapování").grid(row=0, column=3, padx=5, pady=(0,5), sticky=W)

        mapovaci_listbox_font = ("Segoe UI", 12)

        # --- Zdrojový Listbox ---
        self.source_list_frame = Frame(outer_frame, height=150) # Standardní Frame
        self.source_list_frame.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")
        self.source_list_frame.pack_propagate(False)
        # Navážeme kliknutí na FRAME
        self.source_list_frame.bind("<Button-1>", self._focus_listbox_in_frame) # <<< ZDE

        self.source_listbox = Listbox(self.source_list_frame, exportselection=False, selectmode=SINGLE,
                                      bg=UNMAPPED_ITEM_COLOR, fg="white", selectbackground=MAPPED_ITEM_COLOR,
                                      font=mapovaci_listbox_font)
        src_scroll = Scrollbar(self.source_list_frame, orient="vertical", command=self.source_listbox.yview)
        self.source_listbox.configure(yscrollcommand=src_scroll.set)
        src_scroll.pack(side=RIGHT, fill=Y)
        self.source_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        self.source_listbox.bind("<<ListboxSelect>>", self.update_listbox_colors)
        self.source_listbox.bind("<KeyPress>", self._jump_to_char)

        # --- Tlačítka ---
        btn_frame = ctk.CTkFrame(outer_frame, fg_color="transparent")
        btn_frame.grid(row=1, column=1, padx=5, pady=5, sticky="n")
        ctk.CTkButton(btn_frame, text="-->\nPřiřadit", width=70, height=50, command=self.add_mapping).pack(pady=10)
        ctk.CTkButton(btn_frame, text="<--\nOdebrat", width=70, height=50, command=self.remove_mapping).pack(pady=10)

        # --- Cílový Listbox ---
        self.target_list_frame = Frame(outer_frame, height=150) # Standardní Frame
        self.target_list_frame.grid(row=1, column=2, padx=5, pady=5, sticky="nsew")
        self.target_list_frame.pack_propagate(False)
        # Navážeme kliknutí na FRAME
        self.target_list_frame.bind("<Button-1>", self._focus_listbox_in_frame) # <<< ZDE

        self.target_listbox = Listbox(self.target_list_frame, exportselection=False, selectmode=SINGLE,
                                      bg=UNMAPPED_ITEM_COLOR, fg="white", selectbackground=MAPPED_ITEM_COLOR,
                                      font=mapovaci_listbox_font)
        tgt_scroll = Scrollbar(self.target_list_frame, orient="vertical", command=self.target_listbox.yview)
        self.target_listbox.configure(yscrollcommand=tgt_scroll.set)
        tgt_scroll.pack(side=RIGHT, fill=Y)
        self.target_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        self.target_listbox.bind("<<ListboxSelect>>", self.update_listbox_colors)
        self.target_listbox.bind("<KeyPress>", self._jump_to_char)
        self.target_listbox.delete(0, END)
        [self.target_listbox.insert(END, c) for c in TARGET_COLUMNS_FOR_MAPPING]

        # --- Zobrazení mapování Listbox ---
        self.map_disp_frame = Frame(outer_frame, height=150)
        self.map_disp_frame.grid(row=1, column=3, padx=5, pady=5, sticky="nsew")
        self.map_disp_frame.pack_propagate(False)
        self.map_display = Listbox(self.map_disp_frame, selectmode=None, # Je pouze pro čtení
                                   bg=UNMAPPED_ITEM_COLOR, fg="white", selectbackground=MAPPED_ITEM_COLOR,
                                   font=mapovaci_listbox_font)
        map_scroll = Scrollbar(self.map_disp_frame, orient="vertical", command=self.map_display.yview)
        self.map_display.configure(yscrollcommand=map_scroll.set)
        map_scroll.pack(side=RIGHT, fill=Y)
        self.map_display.pack(side=LEFT, fill=BOTH, expand=True)

    def _build_transaction_rules_section(self, parent):
        """Sestaví sekci pro správu pravidel typů transakcí."""
        outer_frame = ctk.CTkFrame(parent)
        outer_frame.pack(fill=BOTH, expand=True, pady=10, padx=5) # Expanduje vertikálně

        # Horní část s titulkem a tlačítky
        title_frame = ctk.CTkFrame(outer_frame, fg_color="transparent")
        title_frame.pack(fill=X, pady=(0, 5))
        ctk.CTkLabel(title_frame, text="Pravidla pro Typy Transakcí (pořadí je důležité):", font=ctk.CTkFont(weight="bold")).pack(side=LEFT, anchor="w", padx=0)

        # Rámec pro tlačítka vpravo
        rule_button_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        rule_button_frame.pack(side=RIGHT)
        ctk.CTkButton(rule_button_frame, text="Přidat Pravidlo", width=120, command=self.add_transaction_rule_ui).pack(side=LEFT, padx=3)
        self.edit_rule_button = ctk.CTkButton(rule_button_frame, text="Upravit", width=80, state="disabled", command=self.edit_selected_rule_ui)
        self.edit_rule_button.pack(side=LEFT, padx=3)
        self.delete_rule_button = ctk.CTkButton(rule_button_frame, text="Smazat", width=80, state="disabled", fg_color="#D32F2F", hover_color="#B71C1C", command=self.remove_selected_rule)
        self.delete_rule_button.pack(side=LEFT, padx=3)
        self.move_rule_up_button = ctk.CTkButton(rule_button_frame, text="Nahoru ↑", width=90, state="disabled", command=self.move_rule_up)
        self.move_rule_up_button.pack(side=LEFT, padx=(10, 3))
        self.move_rule_down_button = ctk.CTkButton(rule_button_frame, text="Dolů ↓", width=90, state="disabled", command=self.move_rule_down)
        self.move_rule_down_button.pack(side=LEFT, padx=3)

        # Rámec pro Treeview s pravidly
        self.rules_tree_frame = ctk.CTkFrame(outer_frame)
        self.rules_tree_frame.pack(fill=BOTH, expand=True, padx=0, pady=0)

        # Treeview pro zobrazení pravidel
        self.rules_tree = ttk.Treeview(
            self.rules_tree_frame,
            columns=("Typ", "Podmínka", "Klíč. slova", "Sloupce"),
            show='headings', # Nezobrazovat první prázdný sloupec
            style="Treeview" # Použijeme styl definovaný v _build_preview_section
        )
        # Definice sloupců
        self.rules_tree.column("Typ", anchor=W, width=150, stretch=False)
        self.rules_tree.heading("Typ", text="Typ Transakce")
        self.rules_tree.column("Podmínka", anchor=W, width=120, stretch=False)
        self.rules_tree.heading("Podmínka", text="Podmínka")
        self.rules_tree.column("Klíč. slova", anchor=W, width=350) # Více místa pro klíčová slova
        self.rules_tree.heading("Klíč. slova", text="Klíčová slova (náhled)")
        self.rules_tree.column("Sloupce", anchor=W, width=250) # Více místa pro sloupce
        self.rules_tree.heading("Sloupce", text="Hledat ve Sloupcích")

        # Scrollbar pro Treeview
        rules_scroll_y = ctk.CTkScrollbar(self.rules_tree_frame, orientation="vertical", command=self.rules_tree.yview)
        self.rules_tree.configure(yscrollcommand=rules_scroll_y.set)
        rules_scroll_y.pack(side=RIGHT, fill=Y)
        self.rules_tree.pack(side=LEFT, fill=BOTH, expand=True)
        # Navázání události výběru
        self.rules_tree.bind("<<TreeviewSelect>>", self.on_rule_select)

        # Sekce pro statistiky pod Treeview
        stats_frame = ctk.CTkFrame(outer_frame, fg_color="transparent")
        stats_frame.pack(fill=X, padx=0, pady=(5, 0))
        self.rule_stats_label = ctk.CTkLabel(stats_frame, text="Statistiky pravidel (ze vzorku): Načtěte vzorový soubor...", text_color="gray", font=ctk.CTkFont(size=11))
        self.rule_stats_label.pack(side=LEFT, anchor="w")
        # Obsah se naplní v update_rules_display a update_rule_statistics

    # UVNITŘ TŘÍDY ConfigManagerWindow(ctk.CTkToplevel):

    def _build_ignore_rules_section(self, parent):
        """Sestaví sekci pro správu pravidel ignorování řádků."""
        outer_frame = ctk.CTkFrame(parent)
        outer_frame.pack(fill=X, expand=False, pady=10, padx=5)

        title_frame = ctk.CTkFrame(outer_frame, fg_color="transparent")
        title_frame.pack(fill=X, pady=(0, 5))
        ctk.CTkLabel(title_frame, text="Pravidla pro Ignorování Řádků:", font=ctk.CTkFont(weight="bold")).pack(side=LEFT, anchor="w", padx=0)

        ignore_button_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        ignore_button_frame.pack(side=RIGHT)

        ctk.CTkButton(ignore_button_frame, text="Přidat Ign. Pravidlo", width=160, command=self.add_ignore_rule_ui).pack(side=LEFT, padx=3)

        # <<< PŘIDÁNÍ TLAČÍTKA UPRAVIT >>>
        self.edit_ignore_rule_button = ctk.CTkButton(ignore_button_frame, text="Upravit", width=80, state="disabled", command=self.edit_selected_ignore_rule_ui)
        self.edit_ignore_rule_button.pack(side=LEFT, padx=3)
        # <<< KONEC PŘIDÁNÍ >>>

        self.delete_ignore_rule_button = ctk.CTkButton(ignore_button_frame, text="Smazat", width=80, state="disabled", fg_color="#D32F2F", hover_color="#B71C1C", command=self.remove_selected_ignore_rule)
        self.delete_ignore_rule_button.pack(side=LEFT, padx=3)

        # Rámec a Treeview (beze změny)
        self.ignore_tree_frame = ctk.CTkFrame(outer_frame)
        self.ignore_tree_frame.pack(fill=X, padx=0, pady=0)
        self.ignore_rules_tree = ttk.Treeview(
            self.ignore_tree_frame,
            columns=("Podmínka", "Klíč. slova", "Sloupce"),
            show='headings', height=3, style="Treeview"
        )
        self.ignore_rules_tree.column("Podmínka", anchor=W, width=100, stretch=False)
        self.ignore_rules_tree.heading("Podmínka", text="Podmínka")
        self.ignore_rules_tree.column("Klíč. slova", anchor=W, width=450)
        self.ignore_rules_tree.heading("Klíč. slova", text="Klíčová slova (náhled)")
        self.ignore_rules_tree.column("Sloupce", anchor=W, width=300)
        self.ignore_rules_tree.heading("Sloupce", text="Hledat ve Sloupcích")
        ignore_scroll_y = ctk.CTkScrollbar(self.ignore_tree_frame, orientation="vertical", command=self.ignore_rules_tree.yview)
        self.ignore_rules_tree.configure(yscrollcommand=ignore_scroll_y.set)
        ignore_scroll_y.pack(side=RIGHT, fill=Y)
        self.ignore_rules_tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.ignore_rules_tree.bind("<<TreeviewSelect>>", self.on_ignore_rule_select)

# KONEC METODY _build_ignore_rules_section
    def _build_save_button_section(self, parent, is_new):
        """Sestaví sekci s tlačítkem pro uložení konfigurace."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(pady=(20, 10)) # Odsazení nahoře a dole
        save_btn_text = "Uložit Novou Konfiguraci" if is_new else "Uložit Změny Konfigurace"
        save_btn = ctk.CTkButton(frame, text=save_btn_text, command=self.save_config_changes, width=250, height=40)
        save_btn.pack()

    # --- Metody pro načítání a aktualizaci dat v editoru ---
    # UVNITŘ TŘÍDY ConfigManagerWindow(ctk.CTkToplevel):

    # UVNITŘ TŘÍDY ConfigManagerWindow(ctk.CTkToplevel):

    def load_sample_file(self):
        """Načte vzorový soubor (pomocí data_loader) a aktualizuje UI editoru."""
        ftypes=(('Podporované', '*.csv *.xlsx *.xls'), ('Všechny', '*.*'))
        initial_dir_sample = self.master_app.last_import_dir if os.path.isdir(self.master_app.last_import_dir) else "."
        logger.debug(f"Otevírám dialog pro vzorek, initialdir='{initial_dir_sample}'")
        fpath = filedialog.askopenfilename(
            title='Vyberte vzorový soubor',
            initialdir=initial_dir_sample,
            filetypes=ftypes,
            parent=self
            )

        if not fpath:
            logger.info("Výběr vzorového souboru zrušen.")
            return

        self.current_sample_filepath = fpath
        self.full_sample_data_stats = None
        logger.info(f"Pokus o načtení vzorového souboru: {fpath}")

        try:
            # <<< ZJEDNODUŠENÉ NAČÍTÁNÍ POMOCÍ data_loader >>>
            NROWS_PREVIEW = 20 # Počet řádků pro náhled v editoru
            # Načteme vzorek pro náhled
            df_preview = data_loader.load_data(fpath, sample_rows=NROWS_PREVIEW)
            # Načteme jen hlavičku pro získání všech sloupců (nrows=0 efektivně)
            # Musíme to udělat znovu, protože load_data s nrows=20 nemusí načíst všechny sloupce, pokud jsou prázdné
            df_columns_only = data_loader.load_data(fpath, sample_rows=0)
            # <<< KONEC ZJEDNODUŠENÍ >>>

            if df_preview is None or df_columns_only is None:
                 # data_loader.load_data by měl vyvolat výjimku, ale pro jistotu
                 raise ValueError("Nepodařilo se načíst data vzorového souboru.")

            # Zpracujeme načtená data
            self.sample_data = df_preview
            # Sloupce bereme z načtení s nrows=0, které by mělo mít všechny
            self.source_columns = sorted(list(df_columns_only.columns))

            # Aktualizujeme UI
            fname = os.path.basename(fpath)
            self.sample_file_label.configure(text=f"Vzor: {fname} ({len(self.source_columns)} sl.)")
            log_msg=f"Načten vzorový soubor '{fname}' ({len(self.source_columns)} sloupců)."
            self.master_app.log_message(f"INFO: {log_msg}")
            logger.info(log_msg)

            # Aktualizujeme poslední adresář v hlavní aplikaci
            self.master_app.last_import_dir = os.path.dirname(fpath)
            logger.debug(f"Aktualizován last_import_dir v App na: '{self.master_app.last_import_dir}'")

            # Aktualizujeme všechny části editoru
            self.update_source_columns_list()
            self.update_data_preview()
            self.update_mapping_display()
            self.update_expected_columns_checklist()
            self.update_rule_statistics()

        except Exception as e:
            # Zpracování chyb zůstává podobné
            fname = os.path.basename(fpath) if fpath else "neznámý"
            log_msg=f"Načtení vzorového souboru '{fname}' selhalo: {e}"
            self.master_app.log_message(f"CHYBA: {log_msg}")
            logger.error(log_msg, exc_info=True)
            messagebox.showerror("Chyba Načítání Vzorku", f"Načtení vzorového souboru selhalo:\n{e}", parent=self)
            self.source_columns=[]; self.sample_data=None
            self.full_sample_data_stats = None
            self.sample_file_label.configure(text="Chyba načtení vzorku!")
            self.update_source_columns_list()
            self.update_data_preview()
            self.update_expected_columns_checklist()
            self.update_rule_statistics()

# KONEC METODY load_sample_file
# KONEC METODY load_sample_file
    # --- Metoda update_data_preview ---
    # (Verze s podbarvením)
    def update_data_preview(self):
        """Aktualizuje obsah Treeview s náhledem dat a podbarví zařazené řádky."""
        # Vymažeme starý obsah Treeview
        for item in self.data_preview_tree.get_children():
            try: self.data_preview_tree.delete(item)
            except Exception: pass # Ignorujeme chyby při mazání (může nastat)

        self.data_preview_tree['columns'] = [] # Reset sloupců

        data_to_display = self.sample_data
        matched_indices = set() # Sada indexů řádků, které byly zařazeny pravidly

        # --- Simulace zařazení pro podbarvení ---
        if data_to_display is not None and not data_to_display.empty and \
           isinstance(self.current_rules, list) and self.current_rules and \
           isinstance(self.current_mapping, dict) and self.current_mapping:
            try:
                # 1. Vytvoříme mapovaný náhled dat
                mapped_preview = pd.DataFrame(index=data_to_display.index)
                for source_col, target_col in self.current_mapping.items():
                    if source_col in data_to_display.columns:
                        mapped_preview[target_col] = data_to_display[source_col]
                    else:
                        mapped_preview[target_col] = "" # Prázdný sloupec, pokud zdroj chybí

                # 2. Aplikujeme pravidla na mapovaný náhled (použijeme kopii!)
                # Předpokládáme, že assign_transaction_types vrací DF s novým sloupcem 'TYP TRANSAKCE'
                # Musíme zajistit, že tato funkce nekoliduje s hlavní aplikací (např. nemění self.last_processed_df)
                typed_preview = data_processor.assign_transaction_types(
                    mapped_preview.copy(), # Důležitá kopie!
                    self.current_rules # Aktuální pravidla z editoru
                )

                # 3. Získáme indexy řádků, které byly úspěšně zařazeny
                if 'TYP TRANSAKCE' in typed_preview.columns:
                    # Bereme řádky, kde typ není None ani prázdný string
                    valid_type_mask = typed_preview['TYP TRANSAKCE'].notna() & (typed_preview['TYP TRANSAKCE'] != '')
                    matched_indices = set(typed_preview.loc[valid_type_mask].index)
                    logger.debug(f"Podbarvení náhledu: {len(matched_indices)} řádků zařazeno pravidly.")
                else:
                    logger.warning("Podbarvení náhledu: Chybí sloupec 'TYP TRANSAKCE' po assign_transaction_types.")

            except Exception as e_highlight:
                 logger.error(f"Chyba při simulaci zařazení pro podbarvení náhledu: {e_highlight}", exc_info=True)
                 matched_indices = set() # V případě chyby nic nepodbarvíme
        # --- Konec simulace ---

        # --- Vykreslení Treeview ---
        if data_to_display is not None and not data_to_display.empty:
            # Nastavíme sloupce Treeview
            tree_cols = list(data_to_display.columns)
            self.data_preview_tree['columns'] = tree_cols
            self.data_preview_tree.column("#0", width=0, stretch=False) # Skryjeme první prázdný sloupec

            # Nastavíme hlavičky a šířky sloupců
            for c in tree_cols:
                # Odhad šířky sloupce podle obsahu a hlavičky
                try:
                    header_width = len(str(c)) * 9 + 10 # Přibližná šířka hlavičky
                    # Šířka nejdelšího textu ve sloupci (omezeno na prvních N řádků)
                    max_len = data_to_display[c].astype(str).str.len().max()
                    content_width = int(max_len * 7.5 + 15) if pd.notna(max_len) else 0
                except Exception:
                    header_width = 100; content_width = 0 # Záložní hodnoty

                col_width = max(header_width, content_width, 60) # Minimální šířka 60
                col_width = min(col_width, 300) # Maximální šířka 300

                self.data_preview_tree.heading(c, text=c, anchor=W)
                self.data_preview_tree.column(c, anchor=W, width=col_width, minwidth=50, stretch=False)

            # Vložíme řádky s případným tagem pro podbarvení
            logger.debug("--- Vkládání řádků do náhledu ---")
            for idx, row in data_to_display.iterrows():
                # Převedeme všechny hodnoty na string pro zobrazení
                vals = [str(v) if pd.notna(v) else "" for v in row.values]
                # Určíme tagy pro tento řádek
                row_tags = ("matched",) if idx in matched_indices else () # Prázdná tuple, pokud není shoda
                if row_tags: logger.debug(f"Řádek index={idx} dostává tag: {row_tags}")

                row_iid = f"preview_{idx}" # Unikátní ID pro řádek v Treeview
                try:
                    # Vložíme řádek s hodnotami a tagy
                    self.data_preview_tree.insert("", "end", iid=row_iid, values=vals, tags=row_tags)
                except Exception as e_ins_prev:
                     logger.error(f"Chyba vkládání řádku {idx} do náhledu: {e_ins_prev}")
            logger.debug("--- Konec vkládání řádků do náhledu ---")

        elif self.source_columns:
            # Pokud máme sloupce, ale žádná data (např. chyba načítání dat, ale sloupce známe)
            tree_cols = self.source_columns
            self.data_preview_tree['columns'] = tree_cols
            self.data_preview_tree.column("#0", width=0, stretch=False)
            for c in tree_cols:
                self.data_preview_tree.heading(c, text=c + " (bez dat)", anchor=W)
                self.data_preview_tree.column(c, anchor=W, width=150, stretch=False)
        else:
            # Pokud nemáme ani sloupce (nebyl načten vzorek)
             tree_cols = ('Info',)
             self.data_preview_tree['columns'] = tree_cols
             self.data_preview_tree.column("#0", width=0, stretch=False)
             self.data_preview_tree.heading('Info', text='Pro náhled dat načtěte vzorový soubor.', anchor=W)
             self.data_preview_tree.column('Info', anchor=W, width=500)

    def update_expected_columns_checklist(self):
        """Aktualizuje checkboxy pro výběr očekávaných sloupců."""
        # Vymažeme starý obsah framu
        for widget in self.expected_cols_frame.winfo_children():
            widget.destroy()
        self.all_expected_columns_vars = {} # Resetujeme slovník proměnných

        # Získáme aktuálně nastavené očekávané sloupce z loaded_config_data
        expected = set()
        if self.loaded_config_data and isinstance(self.loaded_config_data, dict):
            # Bezpečný přístup k vnořeným klíčům
            ident_data = self.loaded_config_data.get("identification", {})
            if isinstance(ident_data, dict):
                 expected_list = ident_data.get("all_expected_columns", [])
                 if isinstance(expected_list, list):
                      expected = set(expected_list)

        # Pokud nemáme zdrojové sloupce (nebyl načten vzorek), zobrazíme zprávu
        if not self.source_columns:
            ctk.CTkLabel(self.expected_cols_frame, text="Pro výběr očekávaných sloupců načtěte vzorový soubor.").pack(pady=10)
            return

        # Vytvoříme checkboxy pro každý zdrojový sloupec
        r, c, MAX_COLS_PER_ROW = 0, 0, 3 # Rozložení do gridu
        for col_name in self.source_columns:
             # Určíme, zda má být checkbox zaškrtnutý
             # Je zaškrtnutý, pokud jde o novou konfiguraci NEBO pokud je sloupec v 'expected'
             is_new_config = self.selected_config_path is None
             initial_value = is_new_config or (col_name in expected)
             var = ctk.BooleanVar(value=initial_value)

             # Vytvoříme checkbox a uložíme jeho proměnnou
             cb = ctk.CTkCheckBox(self.expected_cols_frame, text=col_name, variable=var)
             cb.grid(row=r, column=c, padx=5, pady=2, sticky=W)
             self.all_expected_columns_vars[col_name] = var
             c += 1
             if c >= MAX_COLS_PER_ROW:
                 c = 0; r += 1

    # Metody pro mapování (add, remove, update colors) - beze změny oproti poslední funkční verzi
    # --- Metoda _focus_listbox_in_frame ---
    # (Nová verze pro nastavení focusu na listbox uvnitř framu)
    def _focus_listbox_in_frame(self, event):
        """
        Najde Listbox uvnitř Frame, který vyvolal událost, a nastaví mu focus.
        Voláno při kliknutí na source_list_frame nebo target_list_frame.
        """
        frame_widget = event.widget
        listbox_child = None
        # Najdeme první widget typu Listbox uvnitř tohoto Frame
        for child in frame_widget.winfo_children():
            if isinstance(child, Listbox):
                listbox_child = child
                break

        if listbox_child:
            widget_id = "UnknownFrame"
            try:
                if frame_widget is self.source_list_frame: widget_id = "Source"
                elif frame_widget is self.target_list_frame: widget_id = "Target"
            except AttributeError: pass # Ignorujeme, pokud atributy ještě neexistují
            logger.debug(f"_focus_listbox_in_frame: Kliknuto na {widget_id} Frame. Nastavuji focus na jeho Listbox ({listbox_child}).")
            listbox_child.focus_set() # Nastavíme focus PŘÍMO na nalezený Listbox
        else:
            logger.warning(f"_focus_listbox_in_frame: Nepodařilo se najít Listbox uvnitř {frame_widget}.")

    # --- Metoda _jump_to_char ---
    # (Verze s rozšířeným logováním)
    def _jump_to_char(self, event):
        widget = event.widget
        widget_name = widget.winfo_class()
        char = event.char.lower()

        logger.debug(f"--- _jump_to_char START ---")
        logger.debug(f"Widget class: {widget_name}, Event char: '{char}', Event keysym: '{event.keysym}'")

        listbox_id = "Unknown"
        try:
             if widget is self.source_listbox: listbox_id = "Source"
             elif widget is self.target_listbox: listbox_id = "Target"
             elif widget is self.map_display: listbox_id = "MapDisplay"
             logger.debug(f"Identified as: {listbox_id} Listbox")
        except AttributeError:
             logger.error("_jump_to_char: Nemohu porovnat widget, chybí self.source/target_listbox?")
             return

        if not char or not char.isalnum() or len(char) > 1:
            logger.debug(f"_jump_to_char ({listbox_id}): Ignoruji znak (non-alnum).")
            logger.debug(f"--- _jump_to_char END (ignored char) ---")
            return

        try:
            items = widget.get(0, END)
            if not items:
                logger.debug(f"_jump_to_char ({listbox_id}): Listbox je prázdný.")
                logger.debug(f"--- _jump_to_char END (empty listbox) ---")
                return

            logger.debug(f"_jump_to_char ({listbox_id}): Počet položek: {len(items)}. Hledám znak: '{char}'")
            logger.debug(f"_jump_to_char ({listbox_id}): Prvních pár položek: {items[:5]}")

            current_selection = widget.curselection()
            current_index = current_selection[0] if current_selection else -1
            start_index = current_index + 1
            logger.debug(f"_jump_to_char ({listbox_id}): Aktuální index: {current_index}, Start hledání od: {start_index}")

            found_index = -1
            logger.debug(f"_jump_to_char ({listbox_id}): Hledám od {start_index} do {len(items)-1}")
            for i in range(start_index, len(items)):
                if items[i].lower().startswith(char):
                    found_index = i
                    logger.debug(f"  Našel shodu v pass 1: index {i}, hodnota '{items[i]}'")
                    break

            if found_index == -1:
                logger.debug(f"_jump_to_char ({listbox_id}): Nic v pass 1, hledám od 0 do {start_index-1}")
                for i in range(0, start_index):
                    if items[i].lower().startswith(char):
                        found_index = i
                        logger.debug(f"  Našel shodu v pass 2: index {i}, hodnota '{items[i]}'")
                        break

            if found_index != -1:
                logger.debug(f"_jump_to_char ({listbox_id}): NAŠEL JSEM! Nastavuji výběr na index {found_index}.")
                widget.selection_clear(0, END)
                widget.selection_set(found_index)
                widget.see(found_index)
                widget.activate(found_index)
            else:
                 logger.debug(f"_jump_to_char ({listbox_id}): Nenalezena žádná položka začínající na '{char}'.")

        except Exception as e:
            logger.warning(f"Chyba v _jump_to_char ({listbox_id}): {e}", exc_info=True)

        logger.debug(f"--- _jump_to_char END ---")


    def update_source_columns_list(self):
        """Aktualizuje obsah listboxu zdrojových sloupců."""
        if hasattr(self, 'source_listbox') and self.source_listbox.winfo_exists():
            self.source_listbox.delete(0, END)
            for col in self.source_columns:
                self.source_listbox.insert(END, col)
            self.update_listbox_colors() # Aktualizujeme barvy po naplnění

    def update_target_columns_list(self):
         """Aktualizuje barvy v cílovém listboxu (obsah se nemění)."""
         if hasattr(self, 'target_listbox') and self.target_listbox.winfo_exists():
             self.update_listbox_colors()

    def update_mapping_display(self):
        """Aktualizuje obsah listboxu zobrazujícího aktuální mapování."""
        if hasattr(self, 'map_display') and self.map_display.winfo_exists():
            self.map_display.delete(0, END)
            if not isinstance(self.current_mapping, dict):
                logger.error("update_mapping_display: self.current_mapping není slovník!")
                return
            try:
                # Seřadíme mapování podle pořadí cílových sloupců v FINAL_COLUMN_ORDER
                sorted_map = sorted(
                    self.current_mapping.items(),
                    key=lambda item: ALL_TARGET_COLUMNS.index(item[1]) if item[1] in ALL_TARGET_COLUMNS else float('inf')
                )
            except Exception as e:
                logger.error(f"Chyba při řazení mapování: {e}")
                sorted_map = self.current_mapping.items() # Záložní neřazené zobrazení

            # Vložíme položky do listboxu
            for src, tgt in sorted_map:
                # Přidáme varování, pokud zdrojový sloupec není ve vzorku
                src_warning = " (! VZOR NEOBSAHUJE !)" if self.source_columns and src not in self.source_columns else ""
                display_text = f'"{src}"{src_warning}  ->  "{tgt}"'
                self.map_display.insert(END, display_text)

            # Aktualizujeme barvy v ostatních listboxech (nepřímo, přes metodu)
            self.update_listbox_colors()

    def update_listbox_colors(self, event=None):
        """Naplánuje (nebo rovnou zavolá) aktualizaci barev v listboxech."""
        # Voláme přímo bez self.after
        self._apply_listbox_colors_job()

    def _apply_listbox_colors_job(self):
        """Aplikuje barvy na položky v source a target listboxech."""
        logger.debug("_apply_listbox_colors_job: Spuštěno.")
        if not hasattr(self, 'current_mapping') or not isinstance(self.current_mapping, dict):
             logger.error("_apply_listbox_colors_job: Chybí nebo je neplatné 'current_mapping'.")
             return
        mapped_src = set(self.current_mapping.keys())
        mapped_tgt = set(self.current_mapping.values())
        logger.debug(f"_apply_listbox_colors_job: Aktuální mapped_src: {mapped_src}")
        logger.debug(f"_apply_listbox_colors_job: Aktuální mapped_tgt: {mapped_tgt}")

        try:
            if hasattr(self, 'source_listbox') and self.source_listbox.winfo_exists():
                logger.debug(f"_apply_listbox_colors_job: Aplikuji barvy na source_listbox (velikost: {self.source_listbox.size()}).")
                for i in range(self.source_listbox.size()):
                    item_text = self.source_listbox.get(i)
                    color = MAPPED_ITEM_COLOR if item_text in mapped_src else UNMAPPED_ITEM_COLOR
                    logger.debug(f"  Source item {i} ('{item_text}'): Barva {'MAPPED' if item_text in mapped_src else 'UNMAPPED'} ({color})")
                    self.source_listbox.itemconfig(i, {'bg': color})

            if hasattr(self, 'target_listbox') and self.target_listbox.winfo_exists():
                logger.debug(f"_apply_listbox_colors_job: Aplikuji barvy na target_listbox (velikost: {self.target_listbox.size()}).")
                for i in range(self.target_listbox.size()):
                    item_text = self.target_listbox.get(i)
                    color = MAPPED_ITEM_COLOR if item_text in mapped_tgt else UNMAPPED_ITEM_COLOR
                    logger.debug(f"  Target item {i} ('{item_text}'): Barva {'MAPPED' if item_text in mapped_tgt else 'UNMAPPED'} ({color})")
                    self.target_listbox.itemconfig(i, {'bg': color})

            logger.debug("_apply_listbox_colors_job: Dokončeno nastavení barev, vynucuji update...")
            self.update_idletasks() # Vynutí překreslení

        except Exception as e:
            logger.warning(f"Chyba aplikace barev listboxů: {e}", exc_info=True)

    def add_mapping(self):
        """Přidá nové mapování na základě výběru v source a target listboxech."""
        src_idxs=self.source_listbox.curselection()
        tgt_idxs=self.target_listbox.curselection()

        if not src_idxs:
            messagebox.showwarning("Chybí Vstup", "Vyberte vstupní sloupec ze seznamu vlevo.", parent=self)
            return
        if not tgt_idxs:
            messagebox.showwarning("Chybí Cíl", "Vyberte cílový sloupec ze seznamu uprostřed.", parent=self)
            return

        src=self.source_listbox.get(src_idxs[0])
        tgt=self.target_listbox.get(tgt_idxs[0])

        # Kontrola existujících mapování
        existing_src_for_tgt = next((s for s,t in self.current_mapping.items() if t==tgt), None)
        existing_tgt_for_src = self.current_mapping.get(src)

        proceed = True
        # Pokud je cíl už mapován z jiného zdroje
        if existing_src_for_tgt and existing_src_for_tgt != src:
            proceed = messagebox.askyesno("Přepsat Cílové?",
                                          f"Cílový sloupec '{tgt}' je již mapován ze zdrojového sloupce '{existing_src_for_tgt}'.\n\nChcete přepsat mapování na zdroj '{src}'?",
                                          icon='question', parent=self)
            if proceed:
                 # Odstraníme staré mapování pro tento cíl
                 del self.current_mapping[existing_src_for_tgt]
                 logger.info(f"Původní mapování pro cíl '{tgt}' (ze zdroje '{existing_src_for_tgt}') bude přepsáno.")
            else:
                 return # Uživatel nechtěl přepsat

        # Pokud je zdroj už mapován na jiný cíl
        elif existing_tgt_for_src and existing_tgt_for_src != tgt:
            proceed = messagebox.askyesno("Přepsat Zdrojové?",
                                          f"Zdrojový sloupec '{src}' je již mapován na cílový sloupec '{existing_tgt_for_src}'.\n\nChcete přepsat mapování na cíl '{tgt}'?",
                                          icon='question', parent=self)
            # Pokud uživatel nechce přepsat, nic neděláme
            if not proceed:
                 return

        # Pokud jsme prošli kontrolami nebo uživatel souhlasil s přepsáním
        if proceed:
            self.current_mapping[src]=tgt
            log_msg = f"Přidáno/aktualizováno mapování: '{src}' -> '{tgt}'"
            self.master_app.log_message(f"INFO: {log_msg}")
            logger.info(log_msg)
            # Aktualizujeme UI
            self.update_mapping_display()
            self.update_listbox_colors() # Barvy se změní
            self.update_data_preview()   # Náhled se může změnit
            self.update_rule_statistics() # Statistiky se mohou změnit

    # --- Metoda remove_mapping ---
    # (Verze pracující s výběrem v levých boxech)
    def remove_mapping(self):
        """
        Odebere mapování na základě výběru ve VSTUPNÍM nebo CÍLOVÉM sloupci.
        Prioritu má VSTUPNÍ sloupec. Pokud není vybrán, hledá podle CÍLOVÉHO.
        """
        src_idxs = self.source_listbox.curselection()
        tgt_idxs = self.target_listbox.curselection()

        src_to_remove = None
        tgt_removed = None

        # Priorita 1: Odstranit podle vybraného VSTUPNÍHO sloupce
        if src_idxs:
            selected_src = self.source_listbox.get(src_idxs[0])
            if selected_src in self.current_mapping:
                src_to_remove = selected_src
                tgt_removed = self.current_mapping.pop(src_to_remove) # Odebereme ze slovníku
                logger.info(f"Odstraňuji mapování podle VSTUPNÍHO sloupce: '{src_to_remove}' -> '{tgt_removed}'")
            else:
                messagebox.showinfo("Nenalezeno", f"Vstupní sloupec '{selected_src}' není aktuálně namapován.", parent=self)
                return # Není co odstraňovat

        # Priorita 2: Pokud nebyl vybrán vstupní, zkusit podle CÍLOVÉHO
        elif tgt_idxs:
            selected_tgt = self.target_listbox.get(tgt_idxs[0])
            # Musíme najít, který zdrojový sloupec je mapován na tento cíl
            found_src = None
            for src, tgt in self.current_mapping.items():
                if tgt == selected_tgt:
                    found_src = src
                    break

            if found_src:
                src_to_remove = found_src
                tgt_removed = self.current_mapping.pop(src_to_remove) # Odebereme ze slovníku
                logger.info(f"Odstraňuji mapování podle CÍLOVÉHO sloupce: '{src_to_remove}' -> '{tgt_removed}'")
            else:
                messagebox.showinfo("Nenalezeno", f"Cílový sloupec '{selected_tgt}' není aktuálně namapován.", parent=self)
                return # Není co odstraňovat
        else:
            # Nic nebylo vybráno ani v jednom listboxu
            messagebox.showwarning("Chybí výběr", "Vyberte VSTUPNÍ nebo CÍLOVÝ sloupec, jehož mapování chcete zrušit.", parent=self)
            return

        # Pokud jsme úspěšně něco odstranili (src_to_remove je nastaven)
        if src_to_remove is not None:
            log_msg = f"Odebráno mapování: '{src_to_remove}' -> '{tgt_removed}'"
            self.master_app.log_message(f"INFO: {log_msg}")
            # Aktualizujeme všechny relevantní části UI
            self.update_mapping_display()   # Znovu vykreslíme seznam aktuálního mapování
            self.update_listbox_colors()    # Aktualizujeme barvy v listboxech
            self.update_data_preview()      # Aktualizujeme náhled dat
            self.update_rule_statistics()   # Přepočítáme statistiky
        else:
             logger.warning("remove_mapping: Nepodařilo se určit sloupec k odstranění, i když byl výběr.")


    # --- Metody pro správu pravidel (Typy transakcí) ---
    def _get_rule_data_by_id(self, rule_id, rule_list):
         """Najde slovník pravidla v seznamu podle jeho GUI ID."""
         if not isinstance(rule_list, list): return None
         for rule in rule_list:
              if isinstance(rule, dict) and rule.get("_id") == rule_id:
                  return rule # Vrátíme nalezené pravidlo
         return None # Nenalezeno

    def update_rules_display(self):
        """Aktualizuje Treeview se seznamem pravidel typů transakcí."""
        # Vymažeme starý obsah
        for item in self.rules_tree.get_children():
            try: self.rules_tree.delete(item)
            except Exception: pass # Ignorujeme případné chyby při mazání

        if not isinstance(self.current_rules, list):
             logger.error("update_rules_display: self.current_rules není seznam!")
             return

        # Iterujeme přes SEZNAM pravidel a vkládáme je do Treeview
        for rule_dict in self.current_rules:
            if not isinstance(rule_dict, dict): continue # Přeskočíme neplatné položky

            rule_type = rule_dict.get("type", "N/A")
            conditions = rule_dict.get("conditions", {}) # Měl by to být slovník
            search_in = rule_dict.get("search_in", [])
            rule_id = rule_dict.get("_id") # GUI ID

            if not rule_id: # Pojistka, kdyby ID chybělo
                 rule_id = str(uuid.uuid4()); rule_dict["_id"] = rule_id

            # --- Logika pro zobrazení podmínek a klíčových slov ---
            condition_display = "---" # Výchozí pro chybu nebo 0 podmínek
            keywords_str = ""      # Výchozí

            if isinstance(conditions, dict):
                num_conditions = len(conditions)
                if num_conditions == 1:
                    # Zobrazíme detaily jediné podmínky
                    condition_key = list(conditions.keys())[0]
                    keywords = conditions.get(condition_key, [])
                    condition_display = self._get_display_condition(condition_key)
                    # Zobrazíme jen prvních pár klíčových slov
                    keywords_str = ", ".join(map(str, keywords[:5])) + ("..." if len(keywords) > 5 else "")
                elif num_conditions > 1:
                    # Zobrazíme indikaci více podmínek
                    condition_display = f"Podmínky({num_conditions})"
                    keywords_str = "(Více podmínek - viz Úprava)" # Uživatel musí kliknout na Upravit
                elif num_conditions == 0:
                     condition_display = "ŽÁDNÁ PODMÍNKA!"
                     keywords_str = "---"
            else:
                 condition_display = "CHYBA FORMÁTU"
                 keywords_str = "---"
            # --- Konec logiky zobrazení ---

            # Zobrazení sloupců pro hledání (zkráceně)
            search_cols_str = ", ".join(search_in[:4]) + ("..." if len(search_in) > 4 else "") if search_in else "(Výchozí)"

            # Vložíme řádek do Treeview s _id jako iid (interní ID řádku)
            try:
                 self.rules_tree.insert("", "end", iid=rule_id, values=(rule_type, condition_display, keywords_str, search_cols_str))
            except Exception as e_ins:
                 logger.error(f"Chyba při vkládání pravidla do Treeview (ID: {rule_id}): {e_ins}")

        self.on_rule_select() # Aktualizuje stav tlačítek (Upravit, Smazat, Posunout)
        # Statistiky se aktualizují samostatně v update_rule_statistics

    def add_transaction_rule_ui(self):
        """Otevře dialog pro přidání nového pravidla typu transakce."""
        # Získáme existující typy pro nabídku v comboboxu
        existing_types = []
        if isinstance(self.current_rules, list):
            existing_types = list(set(r.get("type") for r in self.current_rules if isinstance(r, dict) and r.get("type")))

        dialog = AddRuleDialog(self, existing_types, POTENTIAL_SEARCH_COLUMNS, is_ignore_rule=False)
        new_rule_data = dialog.get_rule_data() # Získáme data z dialogu (nebo None)

        if new_rule_data:
            new_rule_data["_id"] = str(uuid.uuid4()) # Přidáme unikátní GUI ID
            if not isinstance(self.current_rules, list): self.current_rules = [] # Pojistka
            self.current_rules.append(new_rule_data) # Přidáme nové pravidlo do seznamu
            log_msg = f"Přidáno pravidlo typu transakce: {new_rule_data}"
            self.master_app.log_message(f"INFO: Přidáno pravidlo typu '{new_rule_data.get('type', 'N/A')}'.")
            logger.info(log_msg)
            # Aktualizujeme zobrazení
            self.update_rules_display()
            self.update_data_preview() # Podbarvení se může změnit
            self.update_rule_statistics() # Statistiky se změní

    def edit_selected_rule_ui(self):
        """Otevře dialog pro úpravu vybraného pravidla typu transakce."""
        selected_items = self.rules_tree.selection() # Získáme vybrané iid
        if not selected_items:
            messagebox.showwarning("Není vybráno", "Nejprve vyberte pravidlo typu transakce, které chcete upravit.", parent=self)
            return

        selected_rule_id = selected_items[0] # Bereme první vybrané (mělo by být jen jedno)
        # Najdeme data pravidla podle jeho ID
        rule_data_to_edit = self._get_rule_data_by_id(selected_rule_id, self.current_rules)

        if not rule_data_to_edit:
            logger.error(f"Nepodařilo se najít data pro pravidlo s ID: {selected_rule_id}")
            messagebox.showerror("Chyba", "Data vybraného pravidla nebyla nalezena.", parent=self)
            return

        # Získáme existující typy pro combobox
        existing_types = []
        if isinstance(self.current_rules, list):
            existing_types = list(set(r.get("type") for r in self.current_rules if isinstance(r, dict) and r.get("type")))

        # Otevřeme dialog v editačním režimu
        dialog = AddRuleDialog(self, existing_types, POTENTIAL_SEARCH_COLUMNS, is_ignore_rule=False, rule_data=rule_data_to_edit)
        updated_rule_data = dialog.get_rule_data() # Získáme upravená data

        if updated_rule_data:
            # Najdeme původní pravidlo v seznamu a nahradíme ho upraveným
            updated = False
            original_id = updated_rule_data.get("_id") # ID by se nemělo měnit
            if isinstance(self.current_rules, list) and original_id:
                 for i, rule in enumerate(self.current_rules):
                      if isinstance(rule, dict) and rule.get("_id") == original_id:
                          self.current_rules[i] = updated_rule_data # Nahradíme pravidlo
                          updated = True
                          break # Našli jsme a nahradili, končíme hledání
            if updated:
                log_msg = f"Upraveno pravidlo (ID:{original_id}): {updated_rule_data}"
                self.master_app.log_message(f"INFO: Upraveno pravidlo typu '{updated_rule_data.get('type', 'N/A')}'.")
                logger.info(log_msg)
                # Aktualizujeme zobrazení
                self.update_rules_display()
                self.update_data_preview()
                self.update_rule_statistics()
            else:
                logger.error(f"Nepodařilo se najít pravidlo ID {original_id} pro uložení úprav.")
                messagebox.showerror("Chyba Uložení", "Uložení změn pravidla selhalo.", parent=self)

    def remove_selected_rule(self):
        """Odstraní vybrané pravidlo typu transakce ze seznamu."""
        selected_items = self.rules_tree.selection()
        if not selected_items:
            messagebox.showwarning("Není vybráno", "Nejprve vyberte pravidlo typu transakce, které chcete smazat.", parent=self)
            return

        selected_rule_id = selected_items[0]
        # Najdeme data pravidla pro zobrazení v potvrzení
        rule_data = self._get_rule_data_by_id(selected_rule_id, self.current_rules)
        if not rule_data:
            logger.error(f"Nepodařilo se najít data pro pravidlo ID {selected_rule_id} ke smazání.")
            messagebox.showerror("Chyba", "Data vybraného pravidla nebyla nalezena.", parent=self)
            return

        # Sestavíme text pro potvrzovací dialog
        rule_type = rule_data.get('type', 'N/A')
        conditions = rule_data.get("conditions", {})
        cond_key = next(iter(conditions), None) # První klíč podmínky
        cond_str = self._get_display_condition(cond_key) if cond_key else "Žádná"
        confirm_msg = f"Opravdu chcete smazat toto pravidlo?\n\nTyp: {rule_type}\nPodmínka: {cond_str}\n(Tato akce je nevratná)"

        # Zeptáme se uživatele
        if messagebox.askyesno("Potvrdit smazání pravidla", confirm_msg, icon='warning', parent=self):
            deleted = False
            original_id = rule_data.get("_id")
            if isinstance(self.current_rules, list) and original_id:
                 # Najdeme index pravidla a odstraníme ho
                 index_to_remove = -1
                 for i, rule in enumerate(self.current_rules):
                      if isinstance(rule, dict) and rule.get("_id") == original_id:
                          index_to_remove = i
                          break
                 if index_to_remove != -1:
                      del self.current_rules[index_to_remove]
                      deleted = True

            if deleted:
                log_msg = f"Smazáno pravidlo typu transakce (ID:{original_id}) typu '{rule_type}'."
                self.master_app.log_message("INFO: Pravidlo typu transakce smazáno.")
                logger.info(log_msg)
                # Aktualizujeme zobrazení
                self.update_rules_display()
                self.update_data_preview()
                self.update_rule_statistics()
            else:
                logger.error(f"Nepodařilo se najít pravidlo ID {original_id} v seznamu ke smazání.")
                messagebox.showerror("Chyba Mazání", "Smazání pravidla selhalo.", parent=self)

    def move_rule_up(self):
        """Posune vybrané pravidlo typu transakce o jednu pozici nahoru."""
        selected_items = self.rules_tree.selection()
        if not selected_items: return # Nic není vybráno

        selected_rule_id = selected_items[0]
        if isinstance(self.current_rules, list):
            current_index = -1
            # Najdeme index vybraného pravidla
            for i, rule in enumerate(self.current_rules):
                if isinstance(rule, dict) and rule.get("_id") == selected_rule_id:
                    current_index = i
                    break
            # Pokud jsme ho našli a není to první položka
            if current_index > 0:
                # Prohodíme ho s předchozí položkou
                self.current_rules.insert(current_index - 1, self.current_rules.pop(current_index))
                logger.info(f"Pravidlo (ID: {selected_rule_id}) posunuto nahoru.")
                # Aktualizujeme zobrazení a zachováme výběr
                self.update_rules_display()
                self.rules_tree.selection_set(selected_rule_id)
                self.rules_tree.focus(selected_rule_id) # Udržíme focus na položce

    def move_rule_down(self):
        """Posune vybrané pravidlo typu transakce o jednu pozici dolů."""
        selected_items = self.rules_tree.selection()
        if not selected_items: return

        selected_rule_id = selected_items[0]
        if isinstance(self.current_rules, list):
            current_index = -1
            # Najdeme index
            for i, rule in enumerate(self.current_rules):
                if isinstance(rule, dict) and rule.get("_id") == selected_rule_id:
                    current_index = i
                    break
            # Pokud jsme ho našli a není to poslední položka
            if current_index != -1 and current_index < len(self.current_rules) - 1:
                # Prohodíme ho s následující položkou
                self.current_rules.insert(current_index + 1, self.current_rules.pop(current_index))
                logger.info(f"Pravidlo (ID: {selected_rule_id}) posunuto dolů.")
                # Aktualizujeme zobrazení a zachováme výběr
                self.update_rules_display()
                self.rules_tree.selection_set(selected_rule_id)
                self.rules_tree.focus(selected_rule_id)

    def on_rule_select(self, event=None):
        """Aktualizuje stav tlačítek pro úpravu/mazání/posun pravidel typů."""
        selected_items = self.rules_tree.selection()
        is_selected = bool(selected_items)

        # Povolíme/zakážeme tlačítka Upravit a Smazat
        self.edit_rule_button.configure(state="normal" if is_selected else "disabled")
        self.delete_rule_button.configure(state="normal" if is_selected else "disabled")

        # Povolíme/zakážeme tlačítka Nahoru/Dolů
        can_move_up = False
        can_move_down = False
        if is_selected and isinstance(self.current_rules, list):
             selected_id = selected_items[0]
             current_index = -1
             # Najdeme index vybrané položky
             for i, rule in enumerate(self.current_rules):
                 if isinstance(rule, dict) and rule.get("_id") == selected_id:
                     current_index = i
                     break
             if current_index != -1:
                 can_move_up = current_index > 0 # Můžeme posunout nahoru, pokud nejsme první
                 can_move_down = current_index < len(self.current_rules) - 1 # Můžeme dolů, pokud nejsme poslední

        self.move_rule_up_button.configure(state="normal" if can_move_up else "disabled")
        self.move_rule_down_button.configure(state="normal" if can_move_down else "disabled")

    # --- Metody pro správu pravidel (Ignorování řádků) ---
    def update_ignore_rules_display(self):
        """Aktualizuje Treeview se seznamem pravidel pro ignorování."""
        # Vymažeme starý obsah
        for item in self.ignore_rules_tree.get_children():
            try: self.ignore_rules_tree.delete(item)
            except Exception: pass

        if not isinstance(self.current_ignore_rules, list):
             logger.error("update_ignore_rules_display: self.current_ignore_rules není seznam!")
             return

        # Vložíme ignore pravidla do Treeview
        for rule_dict in self.current_ignore_rules:
             if not isinstance(rule_dict, dict): continue

             conditions = rule_dict.get("conditions", {})
             search_in = rule_dict.get("search_in", [])
             rule_id = rule_dict.get("_id")
             if not rule_id: # Pojistka
                 rule_id = str(uuid.uuid4()); rule_dict["_id"] = rule_id

             # Zobrazíme první podmínku a klíčová slova (podobně jako u type pravidel)
             condition_key = next(iter(conditions), None) if isinstance(conditions, dict) else None
             keywords = conditions.get(condition_key, []) if condition_key else []
             condition_display = self._get_display_condition(condition_key) if condition_key else "---"
             keywords_str = ", ".join(map(str,keywords[:5])) + ("..." if len(keywords) > 5 else "")
             search_cols_str = ", ".join(search_in[:4]) + ("..." if len(search_in) > 4 else "") if search_in else "(Výchozí)"

             # Vložíme řádek
             try:
                  self.ignore_rules_tree.insert("", "end", iid=rule_id, values=(condition_display, keywords_str, search_cols_str))
             except Exception as e_ins_ign:
                   logger.error(f"Chyba při vkládání ignore pravidla do Treeview (ID: {rule_id}): {e_ins_ign}")

        # Aktualizujeme stav tlačítka Smazat
        self.on_ignore_rule_select()

    def add_ignore_rule_ui(self):
        """Otevře dialog pro přidání nového pravidla ignorování."""
        dialog = AddRuleDialog(self, [], POTENTIAL_SEARCH_COLUMNS, is_ignore_rule=True)
        new_rule_data = dialog.get_rule_data()

        if new_rule_data:
            new_rule_data["_id"] = str(uuid.uuid4()) # Přidáme GUI ID
            if not isinstance(self.current_ignore_rules, list): self.current_ignore_rules = [] # Pojistka
            self.current_ignore_rules.append(new_rule_data) # Přidáme do seznamu
            self.master_app.log_message("INFO: Přidáno pravidlo pro ignorování řádků.")
            logger.info(f"Přidáno ignore pravidlo: {new_rule_data}")
            # Aktualizujeme zobrazení
            self.update_ignore_rules_display()
            # self.update_data_preview() # Ignorování se v náhledu neprojeví

    def remove_selected_ignore_rule(self):
        """Odstraní vybrané pravidlo ignorování ze seznamu."""
        selected_items = self.ignore_rules_tree.selection()
        if not selected_items:
            messagebox.showwarning("Není vybráno", "Nejprve vyberte pravidlo ignorování, které chcete smazat.", parent=self)
            return

        selected_rule_id = selected_items[0]
        # Najdeme data pro potvrzení
        rule_data = self._get_rule_data_by_id(selected_rule_id, self.current_ignore_rules)
        if not rule_data:
            logger.error(f"Nepodařilo se najít data pro ignore pravidlo ID {selected_rule_id} ke smazání.")
            messagebox.showerror("Chyba", "Data vybraného pravidla nebyla nalezena.", parent=self)
            return

        # Sestavíme potvrzovací zprávu
        conditions = rule_data.get("conditions", {}); cond_key = next(iter(conditions), None)
        cond_str = self._get_display_condition(cond_key) if cond_key else "Žádná"
        confirm_msg = f"Opravdu chcete smazat toto pravidlo ignorování?\n(Podmínka: {cond_str})\n(Tato akce je nevratná)"

        if messagebox.askyesno("Potvrdit smazání Ignore?", confirm_msg, icon='warning', parent=self):
            deleted = False
            original_id = rule_data.get("_id")
            if isinstance(self.current_ignore_rules, list) and original_id:
                 # Najdeme a odstraníme
                 index_to_remove = -1
                 for i, rule in enumerate(self.current_ignore_rules):
                      if isinstance(rule, dict) and rule.get("_id") == original_id:
                          index_to_remove = i; break
                 if index_to_remove != -1:
                      del self.current_ignore_rules[index_to_remove]
                      deleted = True

            if deleted:
                log_msg = f"Smazáno ignore pravidlo (ID:{original_id})."
                self.master_app.log_message("INFO: Pravidlo ignorování smazáno.")
                logger.info(log_msg)
                self.update_ignore_rules_display()
                # self.update_data_preview() # Ignorování se v náhledu neprojeví
            else:
                logger.error(f"Nepodařilo se najít ignore pravidlo ID {original_id} v seznamu ke smazání.")
                messagebox.showerror("Chyba Mazání", "Smazání pravidla ignorování selhalo.", parent=self)

    # UVNITŘ TŘÍDY ConfigManagerWindow(ctk.CTkToplevel):

    def on_ignore_rule_select(self, event=None):
        """Aktualizuje stav tlačítek pro úpravu/mazání ignore pravidel."""
        is_selected = bool(self.ignore_rules_tree.selection())
        # Povolíme/zakážeme tlačítko Upravit
        self.edit_ignore_rule_button.configure(state="normal" if is_selected else "disabled") # <<< PŘIDÁNO ZDE
        # Povolíme/zakážeme tlačítko Smazat
        self.delete_ignore_rule_button.configure(state="normal" if is_selected else "disabled")

# KONEC METODY on_ignore_rule_select
    # --- Metoda pro aktualizaci statistik pravidel ---
    def update_rule_statistics(self):
        """Vypočítá a zobrazí statistiky zařazení transakcí na základě vzorku dat."""
        if not hasattr(self, 'rule_stats_label') or not self.rule_stats_label or not self.rule_stats_label.winfo_exists():
            return # Widget ještě neexistuje nebo už byl zničen

        source_desc = "z náhledu (prvních 20 řádků)"
        # Pokud nemáme vzorová data, zobrazíme výchozí zprávu
        if self.sample_data is None or self.sample_data.empty:
            self.rule_stats_label.configure(text=f"Statistiky ({source_desc}): Načtěte vzorový soubor.")
            return
        # Pokud nemáme platná pravidla nebo mapování, nemůžeme počítat
        if not isinstance(self.current_rules, list):
            self.rule_stats_label.configure(text=f"Statistiky ({source_desc}): Chyba načítání pravidel.")
            return
        if not isinstance(self.current_mapping, dict):
            self.rule_stats_label.configure(text=f"Statistiky ({source_desc}): Chyba načítání mapování.")
            return

        total = len(self.sample_data)
        # Pokud nejsou pravidla NEBO není mapování, nemůže být nic zařazeno
        if not self.current_rules or not self.current_mapping:
            stats_text = f"Statistiky ({source_desc}): Zařazeno=0, Nezařazeno={total} (z {total}) - definujte mapování a pravidla."
            self.rule_stats_label.configure(text=stats_text, text_color="gray")
            return

        # Pokusíme se simulovat zpracování a spočítat statistiky
        try:
            # Vytvoříme mapovaný náhled
            mapped_preview = pd.DataFrame(index=self.sample_data.index)
            missing_src = []
            for s, t in self.current_mapping.items():
                if s in self.sample_data.columns: mapped_preview[t] = self.sample_data[s]
                else: mapped_preview[t] = ""; missing_src.append(s)
            if missing_src: logger.warning(f"Pro výpočet statistik chybí ve vzorku zdrojové sloupce: {missing_src}")

            # Aplikujeme pravidla (na kopii!)
            typed_preview = data_processor.assign_transaction_types(mapped_preview.copy(), self.current_rules)

            # Spočítáme nezařazené (prázdný string nebo None)
            untyped_count = 0
            if 'TYP TRANSAKCE' in typed_preview.columns:
                 untyped_count = typed_preview['TYP TRANSAKCE'].isin([None, '']).sum()
            else:
                 logger.warning("Statistiky: Chybí sloupec 'TYP TRANSAKCE' po assign_transaction_types.")
                 untyped_count = total # Všechny jsou nezařazené

            typed_count = total - untyped_count
            stats_text = f"Statistiky ({source_desc}): Zařazeno={typed_count}, Nezařazeno={untyped_count} (z {total})"
            self.rule_stats_label.configure(text=stats_text, text_color="gray") # Standardní barva

        except Exception as e:
            logger.error(f"Chyba při výpočtu statistik pravidel: {e}", exc_info=True)
            self.rule_stats_label.configure(text=f"Statistiky ({source_desc}): Chyba výpočtu.", text_color="red")


    def _get_display_condition(self, internal_key):
        """Přeloží interní klíč podmínky na zobrazovaný název."""
        for disp, intern in TRANSACTION_RULE_CONDITIONS_MAP.items():
            if intern == internal_key:
                return disp
        return internal_key # Pokud nenajdeme, vrátíme původní klíč

    # --- Metoda pro uložení konfigurace ---
    def save_config_changes(self):
        """Sestaví a uloží aktuální konfiguraci do JSON souboru."""
        logger.info("Pokus o uložení změn konfigurace...")

        # --- Sestavení dat pro uložení ---
        # 1. Identifikace
        expected_cols = [c for c, v in self.all_expected_columns_vars.items() if v.get()]
        # header_texts = [line for line in self.header_contains_text.get("1.0", END).splitlines() if line.strip()] # Pokud by se používalo
        current_identification = {"all_expected_columns": expected_cols} # Bez header_contains

        # 2. Mapování sloupců
        current_map = self.current_mapping

        # 3. Pravidla typů transakcí (odstranění GUI ID '_id')
        final_transaction_rules = []
        if isinstance(self.current_rules, list):
             for rule in self.current_rules:
                  if isinstance(rule, dict):
                      rule_copy = rule.copy()
                      rule_copy.pop("_id", None) # Odstraníme interní ID
                      final_transaction_rules.append(rule_copy)

        # 4. Ignore pravidla (odstranění GUI ID '_id')
        final_ignore_rules = []
        if isinstance(self.current_ignore_rules, list):
             for rule in self.current_ignore_rules:
                  if isinstance(rule, dict):
                      rule_copy = rule.copy()
                      rule_copy.pop("_id", None) # Odstraníme interní ID
                      final_ignore_rules.append(rule_copy)

        # Sestavení finálního slovníku pro uložení
        config_to_save = {
            "identification": current_identification,
            "column_mapping": current_map,
            "transaction_types": final_transaction_rules,
            "ignore_rows_rules": final_ignore_rules
        }

        # --- Logika pro určení cesty a uložení ---
        save_path = None
        is_new = self.selected_config_path is None
        original_path = self.selected_config_path
        delete_original = False

        # Získáme nový název souboru z entry widgetu
        new_filename = self.config_filename_var.get().strip()
        if not new_filename:
            messagebox.showerror("Chybí název", "Zadejte název pro konfigurační soubor.", parent=self)
            return
        if not new_filename.lower().endswith(".json"):
            new_filename += ".json" # Přidáme příponu, pokud chybí

        new_save_path = os.path.join(config_manager.CONFIGS_DIR, new_filename)

        if is_new:
            # Ukládáme novou konfiguraci
            save_path = new_save_path
            if os.path.exists(save_path):
                if not messagebox.askyesno("Soubor existuje", f"Konfigurační soubor '{new_filename}' již existuje.\nChcete jej přepsat?", icon='warning', parent=self):
                    return # Uživatel nechce přepsat
        else:
            # Ukládáme existující konfiguraci (možná pod novým názvem)
            if original_path is None:
                 # Toto by nemělo nastat, pokud is_new je False
                 logger.critical("Pokus o uložení existující konfigurace bez platné original_path!")
                 messagebox.showerror("Interní Chyba", "Došlo k interní chybě při ukládání (chybí původní cesta).", parent=self)
                 return

            if original_path == new_save_path:
                # Ukládáme pod stejným názvem
                save_path = original_path
            else:
                # Ukládáme pod novým názvem
                save_path = new_save_path
                logger.info(f"Konfigurace bude uložena pod novým názvem: {new_filename}")
                if os.path.exists(save_path):
                     if not messagebox.askyesno("Soubor existuje", f"Konfigurační soubor '{new_filename}' již existuje.\nChcete jej přepsat?", icon='warning', parent=self):
                          return # Uživatel nechce přepsat
                # Zeptáme se, zda smazat původní soubor
                delete_original = messagebox.askyesno("Smazat původní?", f"Chcete smazat původní konfigurační soubor\n'{os.path.basename(original_path)}'?", parent=self)

        if save_path is None:
             logger.error("Nepodařilo se určit cestu pro uložení konfigurace!")
             messagebox.showerror("Chyba Uložení", "Nelze určit cílovou cestu pro uložení konfigurace.", parent=self)
             return

        # --- Provedeme samotné uložení ---
        try:
            config_manager.save_config(config_to_save, save_path)
            name_saved = os.path.basename(save_path)
            log_msg=f"Konfigurace '{name_saved}' byla úspěšně uložena."
            self.master_app.log_message(f"INFO: {log_msg}")
            logger.info(f"Konfigurace uložena do: {save_path}")
            messagebox.showinfo("Uloženo", log_msg, parent=self)

            # Pokud jsme přejmenovali a uživatel chtěl smazat původní
            if not is_new and original_path != save_path and delete_original:
                 try:
                      os.remove(original_path)
                      orig_name=os.path.basename(original_path)
                      log_msg=f"Původní konfigurační soubor '{orig_name}' byl smazán."
                      self.master_app.log_message(f"INFO: {log_msg}")
                      logger.info(log_msg)
                 except Exception as del_e:
                      logger.error(f"Chyba při mazání původního souboru {original_path}: {del_e}")
                      messagebox.showerror("Chyba Mazání", f"Nepodařilo se smazat původní konfigurační soubor:\n{del_e}", parent=self)

            # Obnovíme seznam a vybereme nově uložený/přejmenovaný soubor
            self.refresh_config_list()
            try:
                 # Najdeme index nově uloženého souboru v listboxu
                 listbox_items = list(self.config_listbox.get(0, END))
                 idx = listbox_items.index(name_saved)
                 self.config_listbox.selection_clear(0, END)
                 self.config_listbox.selection_set(idx) # Vybereme ho
                 self.config_listbox.see(idx) # Zajistíme viditelnost
                 self.on_config_select() # Vyvoláme akci pro výběr
            except ValueError:
                 # Pokud se z nějakého důvodu nenajde, jen vyčistíme panel
                 self.clear_editor_panel(show_placeholder=True)

        except Exception as e:
            name_failed = os.path.basename(save_path)
            log_msg=f"Uložení konfigurace '{name_failed}' selhalo: {e}"
            self.master_app.log_message(f"CHYBA: {log_msg}")
            logger.error(f"Chyba při ukládání konfigurace {save_path}: {e}", exc_info=True)
            messagebox.showerror("Chyba Uložení", f"Uložení konfigurace selhalo:\n{e}", parent=self)

# --- Konec Třídy ConfigManagerWindow ---


# --- Spuštění aplikace ---
if __name__ == "__main__":
    # Kontrola základních knihoven před importem GUI
    missing_libs = []
    try: import pandas
    except ImportError: missing_libs.append("pandas")
    try: import openpyxl
    except ImportError: missing_libs.append("openpyxl")
    try: import customtkinter
    except ImportError: missing_libs.append("customtkinter")

    if missing_libs:
        msg = f"CHYBA: Chybí potřebné knihovny: {', '.join(missing_libs)}\n\nNainstalujte je prosím pomocí příkazu:\npip install {' '.join(missing_libs)}"
        print(msg)
        # Pokusíme se zobrazit messagebox, i když CTk nemusí být nainstalován
        try:
            root = ctk.CTk() # Potřebujeme root okno pro messagebox
            root.withdraw()  # Skryjeme hlavní okno
            messagebox.showerror("Chybějící Knihovny", msg)
            root.destroy()
        except Exception:
            pass # Pokud ani toto nefunguje, chyba už byla vypsána do konzole
        sys.exit(1) # Ukončíme aplikaci

    # Pokud knihovny máme, pokračujeme
    try:
        logger.info("Spouštím GUI aplikaci...")
        app = App() # Vytvoříme instanci naší aplikace
        app.mainloop() # Spustíme hlavní smyčku GUI
        logger.info("GUI aplikace byla ukončena.")
    except Exception as e:
        # Zachytíme případné neočekávané chyby během běhu GUI
        try:
            # Pokusíme se zalogovat chybu
            logger.critical(f"Došlo k neočekávané fatální chybě aplikace: {e}", exc_info=True)
        except NameError: # Pokud logger není definován (chyba importu utils?)
            print(f"FATÁLNÍ CHYBA aplikace (logger nedostupný): {e}")
            traceback.print_exc() # Vypíšeme traceback do konzole

        print(f"\nFATÁLNÍ CHYBA: {e}. Aplikace bude ukončena.")
        # Zkusíme zobrazit chybovou hlášku uživateli
        try:
            root = ctk.CTk()
            root.withdraw()
            messagebox.showerror("Fatální Chyba", f"Došlo k neočekávané chybě:\n{e}\n\nAplikace bude ukončena. Zkontrolujte prosím log soubor.")
            root.destroy()
        except Exception:
             pass # Pokud selže i messagebox
        sys.exit(1)

    print("\nAplikace dokončila svou práci.")