"""
FMP Endpoints Manager -- GUI application for managing fmp_endpoints.json.

Features:
- Hierarchical tree view of categories and endpoints
- Form editor with parameter management
- Live JSON preview window
- API key manager (add/remove/test/switch)
- Live endpoint testing with parameter inputs
- Import/export JSON
- Ctrl+S / Ctrl+O / Ctrl+N keyboard shortcuts
"""

import json
import os
import re
import base64
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from typing import Any, Dict, List, Optional

# --- FMP integration ---
FMP = None
FMP_AVAILABLE = False
try:
    from fmp_stable_api import FMP
    FMP_AVAILABLE = True
except ImportError as e:
    print(f"Warning: FMP client not available. Import error: {e}")

# --- Endpoint data source ---
def _load_initial_endpoints() -> Dict:
    """Load endpoints from updater cache or bundled fallback."""
    try:
        from fmp_stable_api.updater import load_endpoints
        return load_endpoints()
    except Exception:
        return {}


ICON_PATH = os.path.join(os.path.dirname(__file__), "FMP_icon.png")
_FMP_DIR = os.path.expanduser("~/.fmp")
API_KEYS_FILE = os.path.join(_FMP_DIR, "api_keys.json")
CONFIG_FILE = os.path.join(_FMP_DIR, "manager_config.json")

DEFAULT_CONFIG = {
    "window_geometry": "1400x900",
    "min_window_size": "1000x600",
    "json_indent": 2,
    "auto_save": False,
    "validation_strict": False,
}

API_KEY_TYPES = ["Basic", "Starter", "Premium", "Ultimate", "Enterprise", "Custom"]
TIERS = ["FREE", "STARTER", "PREMIUM", "ULTIMATE"]
ACCESS_LEVELS = ["FULL", "LIMITED", "NO_ACCESS"]


###############################################################################
# Utility Classes
###############################################################################

class ConfigManager:
    """Loads and saves ~/.fmp/manager_config.json."""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.config = self._load()

    def _load(self) -> Dict:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                merged.update(data)
                return merged
        except Exception as exc:
            print(f"ConfigManager: error loading config: {exc}")
        return DEFAULT_CONFIG.copy()

    def save_config(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"ConfigManager: error saving config: {exc}")

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value) -> None:
        self.config[key] = value

    def update(self, updates: Dict) -> None:
        self.config.update(updates)


class APIKeyManager:
    """Loads/saves ~/.fmp/api_keys.json with base64 obfuscation."""

    def __init__(self, keys_file: str = API_KEYS_FILE):
        self.keys_file = keys_file
        self.api_keys: Dict = self._load()
        self.current_key_id: Optional[str] = None
        self.current_client: Optional[Any] = None

    # --- persistence helpers ---

    def _encode(self, key: str) -> str:
        return base64.b64encode(key.encode()).decode()

    def _decode(self, encoded: str) -> str:
        try:
            return base64.b64decode(encoded.encode()).decode()
        except Exception:
            return encoded

    def _load(self) -> Dict:
        try:
            if os.path.exists(self.keys_file):
                with open(self.keys_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as exc:
            print(f"APIKeyManager: error loading keys: {exc}")
        return {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.keys_file), exist_ok=True)
            with open(self.keys_file, "w", encoding="utf-8") as f:
                json.dump(self.api_keys, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"APIKeyManager: error saving keys: {exc}")

    # --- public API ---

    def add_api_key(
        self,
        name: str,
        key_type: str,
        api_key: str,
        custom_limit: Optional[int] = None,
        description: str = "",
    ) -> bool:
        if not name or not api_key or name in self.api_keys:
            return False
        self.api_keys[name] = {
            "name": name,
            "key_type": key_type,
            "api_key": self._encode(api_key),
            "custom_limit": custom_limit,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "last_used": None,
        }
        self._save()
        return True

    def remove_api_key(self, name: str) -> bool:
        if name not in self.api_keys:
            return False
        del self.api_keys[name]
        self._save()
        if self.current_key_id == name:
            self.current_key_id = None
            self.current_client = None
        return True

    def get_api_key(self, name: str) -> Optional[Dict]:
        if name not in self.api_keys:
            return None
        entry = self.api_keys[name].copy()
        entry["api_key"] = self._decode(entry["api_key"])
        return entry

    def list_api_keys(self) -> List[Dict]:
        result = []
        for name, entry in self.api_keys.items():
            safe = entry.copy()
            raw = entry["api_key"]
            safe["api_key"] = "***" + raw[-4:] if len(raw) > 4 else "***"
            result.append(safe)
        return result

    def set_current_key(self, name: str) -> bool:
        if name not in self.api_keys:
            return False
        try:
            key_data = self.get_api_key(name)
            if not key_data:
                return False
            if FMP is not None:
                self.current_client = FMP(
                    client_type=key_data["key_type"],
                    client_key=key_data["api_key"],
                    custom_daily_limit=key_data.get("custom_limit"),
                )
            else:
                self.current_client = None
            self.current_key_id = name
            self.api_keys[name]["last_used"] = datetime.now().isoformat()
            self._save()
            return True
        except Exception as exc:
            print(f"APIKeyManager: error setting key: {exc}")
            return False

    def get_current_client(self) -> Optional[Any]:
        return self.current_client

    def get_current_key_info(self) -> Optional[Dict]:
        if self.current_key_id and self.current_key_id in self.api_keys:
            return self.api_keys[self.current_key_id].copy()
        return None

    def test_api_key(self, name: str):
        """Return (bool, str) with success flag and message."""
        key_data = self.get_api_key(name)
        if not key_data:
            return False, "API key not found"
        if FMP is None:
            return False, "FMP client not available"
        try:
            client = FMP(
                client_type=key_data["key_type"],
                client_key=key_data["api_key"],
                custom_daily_limit=key_data.get("custom_limit"),
            )
            result = client.request(
                "https://financialmodelingprep.com/api/v3/changelog"
            )
            if result:
                return True, "API key is valid and working"
            return False, "API key returned no data"
        except Exception as exc:
            return False, f"API key test failed: {exc}"

    def update_api_key(self, name: str, **updates) -> bool:
        if name not in self.api_keys:
            return False
        if "api_key" in updates:
            updates["api_key"] = self._encode(updates["api_key"])
        self.api_keys[name].update(updates)
        self._save()
        return True


class JSONValidator:
    """JSON validation and formatting utilities."""

    @staticmethod
    def validate_json_structure(data: Dict) -> List[str]:
        errors: List[str] = []
        if not isinstance(data, dict):
            errors.append("Root data must be a dictionary")
            return errors
        if "endpoints" in data:
            endpoints = data["endpoints"]
            if not isinstance(endpoints, dict):
                errors.append("'endpoints' should be a dictionary")
            else:
                for cat, cat_data in endpoints.items():
                    if not isinstance(cat_data, dict):
                        errors.append(f"Category '{cat}' should be a dictionary")
                        continue
                    for ep_name, ep_data in cat_data.items():
                        if not isinstance(ep_data, dict):
                            errors.append(
                                f"Endpoint '{ep_name}' in '{cat}' should be a dictionary"
                            )
                            continue
                        if "path" in ep_data and not isinstance(ep_data["path"], str):
                            errors.append(
                                f"Endpoint '{ep_name}' in '{cat}' has invalid 'path'"
                            )
                        for ptype in ("required_params", "optional_params"):
                            if ptype in ep_data:
                                if not isinstance(ep_data[ptype], list):
                                    errors.append(
                                        f"Endpoint '{ep_name}' in '{cat}' has "
                                        f"invalid '{ptype}' (should be list)"
                                    )
                                else:
                                    for p in ep_data[ptype]:
                                        if not isinstance(p, str):
                                            errors.append(
                                                f"Parameter in '{ep_name}' should be a string"
                                            )
                        if "access" in ep_data:
                            access = ep_data["access"]
                            if not isinstance(access, dict):
                                errors.append(
                                    f"Endpoint '{ep_name}' in '{cat}' has invalid 'access' (should be dict)"
                                )
                            else:
                                for tier, level in access.items():
                                    if tier not in ["FREE", "STARTER", "PREMIUM", "ULTIMATE"]:
                                        errors.append(
                                            f"Endpoint '{ep_name}' has unknown tier '{tier}' in 'access'"
                                        )
                                    if level not in ["FULL", "LIMITED", "NO_ACCESS"]:
                                        errors.append(
                                            f"Endpoint '{ep_name}' has invalid access level '{level}' for tier '{tier}'"
                                        )
        return errors

    @staticmethod
    def format_json(data: Dict, indent: int = 2) -> str:
        return json.dumps(data, indent=indent, ensure_ascii=False)


class ParameterManager:
    """Manages parameter lists for endpoints."""

    @staticmethod
    def validate_parameter_name(name: str) -> bool:
        if not name or not isinstance(name, str):
            return False
        return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))

    @staticmethod
    def add_parameter(param_list: List[str], param_name: str):
        """Return (bool, str) — success flag and message."""
        if not ParameterManager.validate_parameter_name(param_name):
            return False, "Invalid parameter name format"
        if param_name in param_list:
            return False, "Parameter already exists"
        param_list.append(param_name)
        return True, "Parameter added successfully"

    @staticmethod
    def remove_parameter(param_list: List[str], param_name: str) -> bool:
        if param_name in param_list:
            param_list.remove(param_name)
            return True
        return False


###############################################################################
# Main Application
###############################################################################

class FMPEndpointsManager:
    """Main application class — tkinter root wrapper."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = ConfigManager()

        # Window setup
        self.root.title("FMP Endpoints Manager")
        geometry = self.config.get("window_geometry", "1400x900")
        self.root.geometry(geometry)
        min_size = self.config.get("min_window_size", "1000x600").split("x")
        self.root.minsize(int(min_size[0]), int(min_size[1]))
        self._set_icon()

        # State
        self.endpoints_data: Dict = {}
        self.current_file: str = ""
        self.modified: bool = False
        self.edit_mode: bool = False
        self.current_editing_item: Optional[Dict] = None

        # API key manager
        self.api_key_manager = APIKeyManager()
        self.fmp_client: Optional[Any] = None

        # Build UI then load data
        self._setup_ui()
        self._load_endpoints()

        # Window-level bindings
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.bind("<Control-s>", lambda e: self._save_file())
        self.root.bind("<Control-o>", lambda e: self._open_file())
        self.root.bind("<Control-n>", lambda e: self._new_file())

    # ------------------------------------------------------------------
    # Icon
    # ------------------------------------------------------------------

    def _set_icon(self) -> None:
        if os.path.exists(ICON_PATH):
            try:
                img = tk.PhotoImage(file=ICON_PATH)
                self.root.iconphoto(True, img)
                self._icon_ref = img  # prevent GC
            except Exception as exc:
                print(f"Could not set icon: {exc}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self._create_menu()

        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        self._create_tree_panel(paned)
        self._create_editor_panel(paned)
        self._create_status_bar()

    def _create_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self._new_file, accelerator="Ctrl+N")
        file_menu.add_command(label="Open", command=self._open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self._save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self._save_as_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_closing)

        # Edit
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Add Category", command=self._add_category)
        edit_menu.add_command(label="Add Endpoint", command=self._add_endpoint)
        edit_menu.add_command(label="Delete Selected", command=self._delete_selected)
        edit_menu.add_separator()
        edit_menu.add_command(label="Validate JSON", command=self._validate_json)

        # View
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="JSON Preview", command=self.show_json_preview_window)
        view_menu.add_separator()
        view_menu.add_command(label="Refresh Tree", command=self._refresh_tree)
        view_menu.add_command(label="Expand All", command=self._expand_all)
        view_menu.add_command(label="Collapse All", command=self._collapse_all)

        # Settings
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Manage API Keys", command=self.manage_api_keys)
        settings_menu.add_command(label="Update Endpoints", command=self._update_endpoints)
        settings_menu.add_separator()
        settings_menu.add_command(label="Preferences", command=self.show_preferences)
        settings_menu.add_command(label="Reset to Defaults", command=self._reset_to_defaults)

        # Help
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

    def _create_tree_panel(self, parent: ttk.PanedWindow) -> None:
        tree_frame = ttk.Frame(parent)
        parent.add(tree_frame, weight=1)

        # --- API info panel ---
        info_frame = ttk.LabelFrame(tree_frame, text="API Information", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(info_frame, text="Introduction:", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        self.intro_text = tk.Text(
            info_frame, height=2, wrap=tk.WORD, state="disabled",
            font=("TkDefaultFont", 9), bg="#f0f0f0",
        )
        self.intro_text.pack(fill=tk.X, pady=(2, 5))

        url_frame = ttk.Frame(info_frame)
        url_frame.pack(fill=tk.X)
        ttk.Label(url_frame, text="Base URL:", font=("TkDefaultFont", 9, "bold")).pack(side=tk.LEFT)
        self.stable_url_var = tk.StringVar()
        ttk.Entry(url_frame, textvariable=self.stable_url_var, state="readonly",
                  font=("TkDefaultFont", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # API key switcher
        api_frame = ttk.Frame(info_frame)
        api_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(api_frame, text="API Key:", font=("TkDefaultFont", 9, "bold")).pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar()
        self.api_key_combo = ttk.Combobox(
            api_frame, textvariable=self.api_key_var,
            state="readonly", font=("TkDefaultFont", 9), width=20,
        )
        self.api_key_combo.pack(side=tk.LEFT, padx=(5, 5))
        self.api_key_combo.bind("<<ComboboxSelected>>", self._on_api_key_changed)
        ttk.Button(api_frame, text="Manage", command=self.manage_api_keys).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(api_frame, text="Test", command=self._test_current_api_key).pack(side=tk.LEFT)
        self._refresh_api_key_list()

        # Update endpoints button
        ttk.Button(info_frame, text="Update Endpoints", command=self._update_endpoints).pack(
            anchor=tk.W, pady=(5, 0)
        )

        # --- Tree ---
        ttk.Label(tree_frame, text="Categories & Endpoints",
                  font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))

        tree_container = ttk.Frame(tree_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_container, show="tree")
        tree_sb = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-3>", lambda e: None)  # placeholder for future context menu

        # Tree buttons
        btn_frame = ttk.Frame(tree_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_frame, text="Add Category", command=self._add_category).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Add Endpoint", command=self._add_endpoint).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Delete", command=self._delete_selected).pack(side=tk.LEFT)

    def _create_editor_panel(self, parent: ttk.PanedWindow) -> None:
        editor_frame = ttk.Frame(parent)
        parent.add(editor_frame, weight=2)

        self.notebook = ttk.Notebook(editor_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._create_endpoint_editor_tab()
        self._create_access_view_tab()

    def _create_endpoint_editor_tab(self) -> None:
        editor_tab = ttk.Frame(self.notebook)
        self.notebook.add(editor_tab, text="Endpoint Editor")

        canvas = tk.Canvas(editor_tab)
        scrollbar = ttk.Scrollbar(editor_tab, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            w = canvas.winfo_width()
            if w > 1:
                canvas.itemconfig(cw, width=w)

        scrollable.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_frame_configure)

        cw = canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Basic Information ---
        basic = ttk.LabelFrame(scrollable, text="Basic Information", padding=10)
        basic.pack(fill=tk.X, padx=5, pady=5)
        basic.grid_columnconfigure(1, weight=1)

        ttk.Label(basic, text="Endpoint Name:").grid(row=0, column=0, sticky=tk.W, pady=2, padx=(0, 10))
        self.endpoint_name_var = tk.StringVar()
        self.endpoint_name_entry = ttk.Entry(basic, textvariable=self.endpoint_name_var, state="readonly")
        self.endpoint_name_entry.grid(row=0, column=1, sticky=tk.EW, pady=2)

        ttk.Label(basic, text="Path:").grid(row=1, column=0, sticky=tk.W, pady=2, padx=(0, 10))
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(basic, textvariable=self.path_var, state="readonly")
        self.path_entry.grid(row=1, column=1, sticky=tk.EW, pady=2)

        ttk.Label(basic, text="Description:").grid(row=2, column=0, sticky=tk.NW, pady=2, padx=(0, 10))
        self.description_text = tk.Text(basic, height=3, state="disabled")
        self.description_text.grid(row=2, column=1, sticky=tk.EW, pady=2)

        # --- Parameters ---
        params = ttk.LabelFrame(scrollable, text="Parameters", padding=10)
        params.pack(fill=tk.X, padx=5, pady=5)
        params.grid_columnconfigure(0, weight=2)
        params.grid_columnconfigure(1, weight=1)

        # Required
        ttk.Label(params, text="Required Parameters:").grid(row=0, column=0, sticky=tk.W, pady=2, padx=(0, 10))
        req_frame = ttk.Frame(params)
        req_frame.grid(row=1, column=0, sticky=tk.EW, pady=2)
        req_frame.grid_columnconfigure(0, weight=1)

        self.required_listbox = tk.Listbox(req_frame, height=6, state="disabled")
        req_sb = ttk.Scrollbar(req_frame, orient=tk.VERTICAL, command=self.required_listbox.yview)
        self.required_listbox.configure(yscrollcommand=req_sb.set)
        self.required_listbox.grid(row=0, column=0, sticky=tk.EW, padx=(0, 2))
        req_sb.grid(row=0, column=1, sticky=tk.NS)

        req_ctrl = ttk.Frame(params)
        req_ctrl.grid(row=1, column=1, sticky=tk.NW, padx=(10, 0), pady=2)
        self.required_param_var = tk.StringVar()
        self.required_param_entry = ttk.Entry(req_ctrl, textvariable=self.required_param_var, width=25, state="disabled")
        self.required_param_entry.pack(pady=2)
        self.add_required_btn = ttk.Button(req_ctrl, text="Add", command=self._add_required_param, state="disabled")
        self.add_required_btn.pack(pady=2)
        self.remove_required_btn = ttk.Button(req_ctrl, text="Remove", command=self._remove_required_param, state="disabled")
        self.remove_required_btn.pack(pady=2)

        # Optional
        ttk.Label(params, text="Optional Parameters:").grid(row=2, column=0, sticky=tk.W, pady=(10, 2), padx=(0, 10))
        opt_frame = ttk.Frame(params)
        opt_frame.grid(row=3, column=0, sticky=tk.EW, pady=2)
        opt_frame.grid_columnconfigure(0, weight=1)

        self.optional_listbox = tk.Listbox(opt_frame, height=6, state="disabled")
        opt_sb = ttk.Scrollbar(opt_frame, orient=tk.VERTICAL, command=self.optional_listbox.yview)
        self.optional_listbox.configure(yscrollcommand=opt_sb.set)
        self.optional_listbox.grid(row=0, column=0, sticky=tk.EW, padx=(0, 2))
        opt_sb.grid(row=0, column=1, sticky=tk.NS)

        opt_ctrl = ttk.Frame(params)
        opt_ctrl.grid(row=3, column=1, sticky=tk.NW, padx=(10, 0), pady=2)
        self.optional_param_var = tk.StringVar()
        self.optional_param_entry = ttk.Entry(opt_ctrl, textvariable=self.optional_param_var, width=25, state="disabled")
        self.optional_param_entry.pack(pady=2)
        self.add_optional_btn = ttk.Button(opt_ctrl, text="Add", command=self._add_optional_param, state="disabled")
        self.add_optional_btn.pack(pady=2)
        self.remove_optional_btn = ttk.Button(opt_ctrl, text="Remove", command=self._remove_optional_param, state="disabled")
        self.remove_optional_btn.pack(pady=2)

        # --- Access by Tier ---
        access_frame = ttk.LabelFrame(scrollable, text="Access by Tier", padding=10)
        access_frame.pack(fill=tk.X, padx=5, pady=5)

        self._access_vars = {}
        self._access_combos = {}
        for i, tier in enumerate(TIERS):
            ttk.Label(access_frame, text=f"{tier}:", width=10).grid(row=i, column=0, sticky=tk.W, pady=2, padx=(0, 10))
            var = tk.StringVar(value="FULL")
            combo = ttk.Combobox(access_frame, textvariable=var, values=ACCESS_LEVELS, state="disabled", width=15)
            combo.grid(row=i, column=1, sticky=tk.W, pady=2)
            self._access_vars[tier] = var
            self._access_combos[tier] = combo

        # --- Action Buttons ---
        action_frame = ttk.Frame(scrollable)
        action_frame.pack(fill=tk.X, padx=5, pady=10)
        for i in range(5):
            action_frame.grid_columnconfigure(i, weight=1)

        self.edit_btn = ttk.Button(action_frame, text="Edit", command=self._toggle_edit_mode)
        self.edit_btn.grid(row=0, column=0, padx=2, pady=2, sticky=tk.EW)

        self.save_btn = ttk.Button(action_frame, text="Save Changes", command=self.save_endpoint_changes, state="disabled")
        self.save_btn.grid(row=0, column=1, padx=2, pady=2, sticky=tk.EW)

        self.cancel_btn = ttk.Button(action_frame, text="Cancel", command=self._cancel_edit, state="disabled")
        self.cancel_btn.grid(row=0, column=2, padx=2, pady=2, sticky=tk.EW)

        self.reset_btn = ttk.Button(action_frame, text="Reset", command=self._reset_endpoint_form, state="disabled")
        self.reset_btn.grid(row=0, column=3, padx=2, pady=2, sticky=tk.EW)

        self.test_btn = ttk.Button(action_frame, text="Test Endpoint", command=self.test_endpoint, state="disabled")
        self.test_btn.grid(row=0, column=4, padx=2, pady=2, sticky=tk.EW)

        # --- Endpoint JSON Preview ---
        ep_json_frame = ttk.LabelFrame(scrollable, text="Endpoint JSON Preview", padding=10)
        ep_json_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.endpoint_json_text = scrolledtext.ScrolledText(
            ep_json_frame, wrap=tk.NONE, font=("Consolas", 9), height=8, state="disabled"
        )
        self.endpoint_json_text.pack(fill=tk.BOTH, expand=True)

        ep_json_ctrl = ttk.Frame(ep_json_frame)
        ep_json_ctrl.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(ep_json_ctrl, text="Refresh", command=self._refresh_endpoint_json).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(ep_json_ctrl, text="Copy JSON", command=self._copy_endpoint_json).pack(side=tk.LEFT)

    def _create_access_view_tab(self) -> None:
        access_tab = ttk.Frame(self.notebook)
        self.notebook.add(access_tab, text="Access View")

        # --- Header ---
        header = ttk.Frame(access_tab, padding=(5, 5))
        header.pack(fill=tk.X)

        ttk.Label(header, text="Tier:", font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        self._access_view_tier = tk.StringVar(value="FREE")
        tier_combo = ttk.Combobox(
            header, textvariable=self._access_view_tier,
            values=TIERS, state="readonly", width=12,
        )
        tier_combo.pack(side=tk.LEFT, padx=(0, 20))
        tier_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_access_view())

        ttk.Separator(header, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Label(header, text="Set all to:").pack(side=tk.LEFT, padx=(0, 5))
        self._bulk_access_var = tk.StringVar(value="FULL")
        ttk.Combobox(
            header, textvariable=self._bulk_access_var,
            values=ACCESS_LEVELS, state="readonly", width=12,
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(header, text="Apply", command=self._bulk_set_access).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Button(header, text="Save Changes", command=self._save_access_view).pack(side=tk.RIGHT)

        # --- Treeview ---
        tree_frame = ttk.Frame(access_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(3, 5))

        self._access_tree = ttk.Treeview(tree_frame, columns=("access",), show="tree headings")
        self._access_tree.heading("#0", text="Category / Endpoint")
        self._access_tree.heading("access", text="Access Level")
        self._access_tree.column("#0", width=350, stretch=True)
        self._access_tree.column("access", width=140, stretch=False)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._access_tree.yview)
        self._access_tree.configure(yscrollcommand=vsb.set)
        self._access_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Tag colours
        self._access_tree.tag_configure("full", foreground="#1a7a1a")
        self._access_tree.tag_configure("limited", foreground="#a06000")
        self._access_tree.tag_configure("noaccess", foreground="#cc0000")
        self._access_tree.tag_configure("mixed", foreground="#666666")
        self._access_tree.tag_configure("category", font=("TkDefaultFont", 9, "bold"))

        # Floating combobox for inline editing
        self._access_edit_combo = ttk.Combobox(
            self._access_tree, values=ACCESS_LEVELS, state="readonly", width=13,
        )
        self._access_edit_combo.bind("<<ComboboxSelected>>", self._on_access_edit_selected)
        self._access_edit_combo.bind("<Escape>", lambda e: self._access_edit_combo.place_forget())
        self._access_edit_item = None

        self._access_tree.bind("<ButtonRelease-1>", self._on_access_tree_click)

    def _access_tag(self, level: str) -> str:
        return {"FULL": "full", "LIMITED": "limited", "NO_ACCESS": "noaccess"}.get(level, "full")

    def _category_summary(self, cat_item: str) -> str:
        levels = {self._access_tree.set(ep, "access") for ep in self._access_tree.get_children(cat_item)}
        if not levels:
            return ""
        return next(iter(levels)) if len(levels) == 1 else "Mixed"

    def _update_category_summary(self, cat_item: str) -> None:
        summary = self._category_summary(cat_item)
        tag = self._access_tag(summary) if summary != "Mixed" else "mixed"
        self._access_tree.set(cat_item, "access", summary)
        self._access_tree.item(cat_item, tags=("category", tag))

    def _refresh_access_view(self) -> None:
        if not hasattr(self, "_access_tree"):
            return
        self._access_edit_combo.place_forget()
        for item in self._access_tree.get_children():
            self._access_tree.delete(item)

        tier = self._access_view_tier.get()
        for cat_name, cat_data in self.endpoints_data.get("endpoints", {}).items():
            if not isinstance(cat_data, dict):
                continue
            cat_item = self._access_tree.insert(
                "", "end", text=cat_name, values=("",), open=True, tags=("category",),
            )
            for ep_name, ep_data in cat_data.items():
                if not isinstance(ep_data, dict) or "path" not in ep_data:
                    continue
                level = ep_data.get("access", {}).get(tier, "FULL")
                self._access_tree.insert(
                    cat_item, "end", text=f"  {ep_name}", values=(level,),
                    tags=(self._access_tag(level),),
                )
            self._update_category_summary(cat_item)

    def _on_access_tree_click(self, event) -> None:
        region = self._access_tree.identify_region(event.x, event.y)
        col = self._access_tree.identify_column(event.x)
        item = self._access_tree.identify_row(event.y)
        if region != "cell" or col != "#1" or not item:
            self._access_edit_combo.place_forget()
            return
        bbox = self._access_tree.bbox(item, col)
        if not bbox:
            return
        x, y, width, height = bbox
        self._access_edit_item = item
        current = self._access_tree.set(item, "access")
        self._access_edit_combo.set("" if current == "Mixed" else current)
        self._access_edit_combo.place(x=x, y=y, width=width, height=height)
        self._access_edit_combo.focus()

    def _on_access_edit_selected(self, event) -> None:
        if not self._access_edit_item:
            return
        new_val = self._access_edit_combo.get()
        item = self._access_edit_item
        self._access_edit_combo.place_forget()
        self._access_edit_item = None

        is_category = not self._access_tree.parent(item)
        if is_category:
            # Apply to all endpoints in the category
            for ep_item in self._access_tree.get_children(item):
                self._access_tree.set(ep_item, "access", new_val)
                self._access_tree.item(ep_item, tags=(self._access_tag(new_val),))
            self._update_category_summary(item)
        else:
            self._access_tree.set(item, "access", new_val)
            self._access_tree.item(item, tags=(self._access_tag(new_val),))
            self._update_category_summary(self._access_tree.parent(item))

        self._mark_modified()

    def _bulk_set_access(self) -> None:
        level = self._bulk_access_var.get()
        for cat_item in self._access_tree.get_children():
            for ep_item in self._access_tree.get_children(cat_item):
                self._access_tree.set(ep_item, "access", level)
                self._access_tree.item(ep_item, tags=(self._access_tag(level),))
            self._update_category_summary(cat_item)
        self._mark_modified()

    def _save_access_view(self) -> None:
        tier = self._access_view_tier.get()
        endpoints = self.endpoints_data.get("endpoints", {})
        for cat_item in self._access_tree.get_children():
            cat_name = self._access_tree.item(cat_item)["text"]
            if cat_name not in endpoints:
                continue
            for ep_item in self._access_tree.get_children(cat_item):
                ep_name = self._access_tree.item(ep_item)["text"].strip()
                level = self._access_tree.set(ep_item, "access")
                if ep_name not in endpoints[cat_name]:
                    continue
                ep = endpoints[cat_name][ep_name]
                if "access" not in ep:
                    ep["access"] = {t: "FULL" for t in TIERS}
                ep["access"][tier] = level
        self._save_file()
        self._refresh_tree(preserve_expansion=True)
        self.status_var.set(f"Access settings saved for {tier} tier")

    def _create_status_bar(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(
            side=tk.BOTTOM, fill=tk.X
        )

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_endpoints(self) -> None:
        """Load from updater/cache; populate tree and info panel."""
        try:
            self.endpoints_data = _load_initial_endpoints()
            from fmp_stable_api.updater import BUNDLED_ENDPOINTS
            self.current_file = BUNDLED_ENDPOINTS
        except Exception:
            self.endpoints_data = {}
            self.current_file = ""

        self._populate_info_panel()
        self._refresh_tree()
        self._refresh_access_view()
        self.modified = False
        self.status_var.set("Endpoints loaded")

    def load_endpoints(self) -> None:
        """Public alias for loading endpoints (called from menu/button)."""
        self._load_endpoints()

    def _populate_info_panel(self) -> None:
        intro = self.endpoints_data.get("Introduction", "")
        self.intro_text.config(state="normal")
        self.intro_text.delete(1.0, tk.END)
        self.intro_text.insert(1.0, intro)
        self.intro_text.config(state="disabled")
        self.stable_url_var.set(self.endpoints_data.get("stable_url", ""))

    def _clear_info_panel(self) -> None:
        self.intro_text.config(state="normal")
        self.intro_text.delete(1.0, tk.END)
        self.intro_text.insert(1.0, "No file loaded")
        self.intro_text.config(state="disabled")
        self.stable_url_var.set("")

    # ------------------------------------------------------------------
    # Tree
    # ------------------------------------------------------------------

    def _refresh_tree(self, preserve_expansion: bool = False) -> None:
        expanded = self._get_expanded_items() if preserve_expansion else []
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._build_tree_recursive("", self.endpoints_data)
        self._expand_all()
        if preserve_expansion and expanded:
            self._restore_expanded_items(expanded)

    def _get_expanded_items(self) -> List[str]:
        result: List[str] = []
        for item in self.tree.get_children():
            if self.tree.item(item, "open"):
                result.append(self.tree.item(item, "text"))
                result.extend(self._get_expanded_children(item))
        return result

    def _get_expanded_children(self, parent: str) -> List[str]:
        result: List[str] = []
        for child in self.tree.get_children(parent):
            if self.tree.item(child, "open"):
                result.append(self.tree.item(child, "text"))
                result.extend(self._get_expanded_children(child))
        return result

    def _restore_expanded_items(self, names: List[str]) -> None:
        for item in self.tree.get_children():
            if self.tree.item(item, "text") in names:
                self.tree.item(item, open=True)
                self._restore_expanded_children(item, names)

    def _restore_expanded_children(self, parent: str, names: List[str]) -> None:
        for child in self.tree.get_children(parent):
            if self.tree.item(child, "text") in names:
                self.tree.item(child, open=True)
                self._restore_expanded_children(child, names)

    def _build_tree_recursive(self, parent: str, data, level: int = 0) -> None:
        if isinstance(data, dict):
            for key, value in data.items():
                if key in ("Introduction", "stable_url"):
                    continue
                if isinstance(value, dict):
                    if "path" in value and isinstance(value["path"], str):
                        access = value.get("access", {})
                        min_tier = next((t for t in TIERS if access.get(t, "FULL") != "NO_ACCESS"), None) if access else None
                        badge = f" [{min_tier}+]" if min_tier and min_tier != "FREE" else ""
                        self.tree.insert(parent, "end", text=f"{key}{badge}", values=("endpoint", value.get("path", "")))
                    else:
                        cat_item = self.tree.insert(parent, "end", text=key, values=("category",))
                        self.tree.item(cat_item, open=True)
                        self._build_tree_recursive(cat_item, value, level + 1)
                elif isinstance(value, list):
                    lst_item = self.tree.insert(parent, "end", text=f"{key} ({len(value)} items)", values=("list",))
                    self.tree.item(lst_item, open=True)
                    for i, v in enumerate(value):
                        self.tree.insert(lst_item, "end", text=f"[{i}] {v}", values=("list_item",))
                else:
                    self.tree.insert(parent, "end", text=f"{key}: {value}", values=("value",))
        elif isinstance(data, list):
            for i, v in enumerate(data):
                self.tree.insert(parent, "end", text=f"[{i}] {v}", values=("list_item",))

    def _expand_all(self) -> None:
        def expand(item):
            self.tree.item(item, open=True)
            for child in self.tree.get_children(item):
                expand(child)
        for item in self.tree.get_children():
            expand(item)

    def _collapse_all(self) -> None:
        for item in self.tree.get_children():
            self.tree.item(item, open=False)

    # public aliases for menu
    def refresh_tree(self, preserve_expansion: bool = False) -> None:
        self._refresh_tree(preserve_expansion)

    # ------------------------------------------------------------------
    # JSON Preview window
    # ------------------------------------------------------------------

    def show_json_preview_window(self) -> None:
        if hasattr(self, "_json_preview_win") and self._json_preview_win.winfo_exists():
            self._json_preview_win.lift()
            self._json_preview_win.focus()
            return

        win = tk.Toplevel(self.root)
        win.title("JSON Preview")
        win.geometry("800x600")
        self._json_preview_win = win

        self._json_text_widget = scrolledtext.ScrolledText(
            win, wrap=tk.NONE, font=("Consolas", 10), height=25
        )
        self._json_text_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        ctrl = ttk.Frame(win)
        ctrl.pack(fill=tk.X, padx=5, pady=(0, 5))
        ttk.Button(ctrl, text="Refresh", command=self._refresh_json_preview).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(ctrl, text="Validate", command=self._validate_json).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(ctrl, text="Format", command=self._refresh_json_preview).pack(side=tk.LEFT)

        self._refresh_json_preview()
        win.protocol("WM_DELETE_WINDOW", self._close_json_preview_window)

    def _close_json_preview_window(self) -> None:
        if hasattr(self, "_json_preview_win"):
            self._json_preview_win.destroy()

    def _refresh_json_preview(self) -> None:
        if not hasattr(self, "_json_text_widget"):
            return
        try:
            if not self._json_text_widget.winfo_exists():
                return
        except Exception:
            return
        try:
            indent = self.config.get("json_indent", 2)
            text = JSONValidator.format_json(self.endpoints_data, indent)
            self._json_text_widget.delete(1.0, tk.END)
            self._json_text_widget.insert(1.0, text)
        except Exception as exc:
            self._json_text_widget.delete(1.0, tk.END)
            self._json_text_widget.insert(1.0, f"Error: {exc}")

    # ------------------------------------------------------------------
    # Tree selection / endpoint editing
    # ------------------------------------------------------------------

    def _on_tree_select(self, event) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        item = self.tree.item(sel[0])
        item_type = item["values"][0] if item["values"] else ""

        if self.edit_mode and self.current_editing_item:
            if messagebox.askyesno("Unsaved Changes", "Save changes before switching?"):
                self.save_endpoint_changes()
            else:
                self._set_edit_mode(False)

        if item_type == "endpoint":
            self.load_endpoint_for_editing(item["text"], self.tree.parent(sel[0]))
        else:
            self._clear_endpoint_form()

    def load_endpoint_for_editing(self, endpoint_name: str, category_item: str) -> None:
        path = self._get_item_path(category_item, endpoint_name)
        ep_data = self._get_data_at_path(path)

        if not ep_data or not isinstance(ep_data, dict):
            self.status_var.set("No data found for selected endpoint")
            return

        self.current_editing_item = {
            "name": endpoint_name,
            "category_item": category_item,
            "path": path,
        }

        self.endpoint_name_var.set(endpoint_name)
        self.path_var.set(ep_data.get("path", ""))

        self.description_text.config(state="normal")
        self.description_text.delete(1.0, tk.END)
        self.description_text.insert(1.0, ep_data.get("description", ""))
        self.description_text.config(state="disabled")

        self.required_listbox.config(state="normal")
        self.optional_listbox.config(state="normal")

        self.required_listbox.delete(0, tk.END)
        for p in ep_data.get("required_params", []):
            self.required_listbox.insert(tk.END, p)

        self.optional_listbox.delete(0, tk.END)
        for p in ep_data.get("optional_params", []):
            self.optional_listbox.insert(tk.END, p)

        self.required_listbox.config(state="disabled")
        self.optional_listbox.config(state="disabled")

        access = ep_data.get("access", {})
        for tier in TIERS:
            self._access_vars[tier].set(access.get(tier, "FULL"))

        self._set_edit_mode(False)
        self.test_btn.config(state="normal")
        self.status_var.set(f"Viewing: {endpoint_name} (Click Edit to modify)")
        self._refresh_endpoint_json()

    def _get_item_path(self, category_item: str, endpoint_name: str) -> List[str]:
        category_name = self.tree.item(category_item)["text"]
        return ["endpoints", category_name, endpoint_name]

    def _get_data_at_path(self, path: List[str]):
        current = self.endpoints_data
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _clear_endpoint_form(self) -> None:
        self.endpoint_name_var.set("")
        self.path_var.set("")
        self.description_text.config(state="normal")
        self.description_text.delete(1.0, tk.END)
        self.description_text.config(state="disabled")
        self.required_listbox.config(state="normal")
        self.required_listbox.delete(0, tk.END)
        self.required_listbox.config(state="disabled")
        self.optional_listbox.config(state="normal")
        self.optional_listbox.delete(0, tk.END)
        self.optional_listbox.config(state="disabled")
        self.required_param_var.set("")
        self.optional_param_var.set("")
        for tier in TIERS:
            self._access_vars[tier].set("FULL")
        self.current_editing_item = None
        self._set_edit_mode(False)

        self.endpoint_json_text.config(state="normal")
        self.endpoint_json_text.delete(1.0, tk.END)
        self.endpoint_json_text.insert(1.0, "No endpoint selected")
        self.endpoint_json_text.config(state="disabled")
        self.status_var.set("Ready")

    # ------------------------------------------------------------------
    # Edit mode
    # ------------------------------------------------------------------

    def _toggle_edit_mode(self) -> None:
        if not self.current_editing_item:
            messagebox.showwarning("Warning", "No item selected for editing")
            return
        self._set_edit_mode(not self.edit_mode)

    def _set_edit_mode(self, active: bool) -> None:
        self.edit_mode = active
        state_rw = "normal" if active else "readonly"
        state_dis = "normal" if active else "disabled"

        self.endpoint_name_entry.config(state=state_rw)
        self.path_entry.config(state=state_rw)
        self.description_text.config(state=state_dis)
        self.required_listbox.config(state=state_dis)
        self.optional_listbox.config(state=state_dis)
        self.required_param_entry.config(state=state_dis)
        self.optional_param_entry.config(state=state_dis)

        btn_state = "normal" if active else "disabled"
        self.add_required_btn.config(state=btn_state)
        self.remove_required_btn.config(state=btn_state)
        self.add_optional_btn.config(state=btn_state)
        self.remove_optional_btn.config(state=btn_state)
        self.save_btn.config(state=btn_state)
        self.cancel_btn.config(state=btn_state)
        self.reset_btn.config(state=btn_state)
        combo_state = "readonly" if active else "disabled"
        for combo in self._access_combos.values():
            combo.config(state=combo_state)
        self.test_btn.config(state="normal" if self.current_editing_item else "disabled")
        self.edit_btn.config(text="Cancel Edit" if active else "Edit")

        if self.current_editing_item:
            name = self.current_editing_item["name"]
            self.status_var.set(
                f"Editing: {name}" if active else f"Viewing: {name} (Click Edit to modify)"
            )

    def _cancel_edit(self) -> None:
        if self.edit_mode and self.current_editing_item:
            self.load_endpoint_for_editing(
                self.current_editing_item["name"],
                self.current_editing_item["category_item"],
            )

    def _reset_endpoint_form(self) -> None:
        if self.current_editing_item and self.edit_mode:
            self.load_endpoint_for_editing(
                self.current_editing_item["name"],
                self.current_editing_item["category_item"],
            )
            self._set_edit_mode(True)

    # ------------------------------------------------------------------
    # Parameter editing
    # ------------------------------------------------------------------

    def _add_required_param(self) -> None:
        name = self.required_param_var.get().strip()
        if not name:
            return
        current = [self.required_listbox.get(i) for i in range(self.required_listbox.size())]
        ok, msg = ParameterManager.add_parameter(current, name)
        if ok:
            self.required_listbox.insert(tk.END, name)
            self.required_param_var.set("")
            self._mark_modified()
        else:
            messagebox.showwarning("Warning", msg)

    def _remove_required_param(self) -> None:
        sel = self.required_listbox.curselection()
        if sel:
            self.required_listbox.delete(sel[0])
            self._mark_modified()

    def _add_optional_param(self) -> None:
        name = self.optional_param_var.get().strip()
        if not name:
            return
        current = [self.optional_listbox.get(i) for i in range(self.optional_listbox.size())]
        ok, msg = ParameterManager.add_parameter(current, name)
        if ok:
            self.optional_listbox.insert(tk.END, name)
            self.optional_param_var.set("")
            self._mark_modified()
        else:
            messagebox.showwarning("Warning", msg)

    def _remove_optional_param(self) -> None:
        sel = self.optional_listbox.curselection()
        if sel:
            self.optional_listbox.delete(sel[0])
            self._mark_modified()

    # ------------------------------------------------------------------
    # Save endpoint changes
    # ------------------------------------------------------------------

    def save_endpoint_changes(self) -> None:
        if not self.edit_mode or not self.current_editing_item:
            messagebox.showwarning("Warning", "Not in edit mode or no item selected")
            return

        ep_name = self.endpoint_name_var.get().strip()
        path = self.path_var.get().strip()
        description = self.description_text.get(1.0, tk.END).strip()

        if not ep_name or not path:
            messagebox.showwarning("Warning", "Endpoint name and path are required")
            return

        normalized = ep_name.replace(" ", "_").replace("-", "_")
        if normalized != ep_name:
            if not messagebox.askyesno(
                "Name Normalized",
                f"Endpoint name will be normalized to '{normalized}'. Continue?",
            ):
                return
            ep_name = normalized

        required_params = [self.required_listbox.get(i) for i in range(self.required_listbox.size())]
        optional_params = [self.optional_listbox.get(i) for i in range(self.optional_listbox.size())]

        path_parts = self.current_editing_item["path"]
        current = self.endpoints_data
        for key in path_parts[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        access = {tier: self._access_vars[tier].get() for tier in TIERS}
        current[path_parts[-1]] = {
            "path": path,
            "description": description,
            "required_params": required_params,
            "optional_params": optional_params,
            "access": access,
        }

        try:
            self._save_file()
            self.status_var.set(f"Saved: {ep_name}")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to save: {exc}")
            return

        self._refresh_tree(preserve_expansion=True)
        self._refresh_json_preview()
        self._refresh_endpoint_json()
        self._set_edit_mode(False)

    # ------------------------------------------------------------------
    # Test endpoint
    # ------------------------------------------------------------------

    def test_endpoint(self) -> None:
        if not self.current_editing_item:
            messagebox.showwarning("Warning", "No endpoint selected for testing")
            return

        if not FMP_AVAILABLE:
            messagebox.showerror("Error", "FMP Client not available")
            return

        if not self.fmp_client:
            if messagebox.askyesno("API Not Configured", "No API key selected. Manage API keys now?"):
                self.manage_api_keys()
            if not self.fmp_client:
                return

        ep_data = self._get_data_at_path(self.current_editing_item["path"])
        if not ep_data:
            messagebox.showerror("Error", "No endpoint data found")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Test: {self.current_editing_item['name']}")
        dlg.geometry("700x600")
        dlg.transient(self.root)
        dlg.grab_set()

        main_frame = ttk.Frame(dlg, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(main_frame)
        sb = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        sf = ttk.Frame(canvas)
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Info
        info = ttk.LabelFrame(sf, text="Endpoint Information", padding=10)
        info.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(info, text=f"Name: {self.current_editing_item['name']}", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        ttk.Label(info, text=f"Path: {ep_data.get('path', '')}").pack(anchor=tk.W)
        ttk.Label(info, text=f"Description: {ep_data.get('description', '')}", wraplength=600).pack(anchor=tk.W)

        # Parameters
        params_frame = ttk.LabelFrame(sf, text="Parameters", padding=10)
        params_frame.pack(fill=tk.X, pady=(0, 10))
        required_params = ep_data.get("required_params", [])
        optional_params = ep_data.get("optional_params", [])
        param_vars: Dict[str, tk.StringVar] = {}

        if required_params:
            ttk.Label(params_frame, text="Required Parameters:", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W, pady=(0, 5))
            for p in required_params:
                pf = ttk.Frame(params_frame)
                pf.pack(fill=tk.X, pady=2)
                ttk.Label(pf, text=f"{p}:", width=20).pack(side=tk.LEFT)
                param_vars[p] = tk.StringVar()
                ttk.Entry(pf, textvariable=param_vars[p]).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        if optional_params:
            ttk.Label(params_frame, text="Optional Parameters:", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W, pady=(10, 5))
            for p in optional_params:
                pf = ttk.Frame(params_frame)
                pf.pack(fill=tk.X, pady=2)
                ttk.Label(pf, text=f"{p}:", width=20).pack(side=tk.LEFT)
                param_vars[p] = tk.StringVar()
                ttk.Entry(pf, textvariable=param_vars[p]).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # Test method
        opts_frame = ttk.LabelFrame(sf, text="Test Options", padding=10)
        opts_frame.pack(fill=tk.X, pady=(0, 10))
        method_var = tk.StringVar(value="dynamic")
        ttk.Radiobutton(opts_frame, text="Use Dynamic Function (Recommended)", variable=method_var, value="dynamic").pack(anchor=tk.W)
        ttk.Radiobutton(opts_frame, text="Use Direct Request", variable=method_var, value="direct").pack(anchor=tk.W)

        # Results
        results_frame = ttk.LabelFrame(sf, text="Results", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True)
        results_text = scrolledtext.ScrolledText(results_frame, height=15, font=("Consolas", 9), wrap=tk.WORD)
        results_text.pack(fill=tk.BOTH, expand=True)

        def run_test():
            params = {p: v.get().strip() for p, v in param_vars.items() if v.get().strip()}
            missing = [p for p in required_params if p not in params]
            if missing:
                messagebox.showerror("Error", f"Missing required parameters: {', '.join(missing)}")
                return

            results_text.delete(1.0, tk.END)
            results_text.insert(tk.END, "Testing endpoint...\n\n")
            dlg.update()

            try:
                if method_var.get() == "dynamic":
                    cat_name = self.tree.item(self.current_editing_item["category_item"])["text"]
                    cat_attr = "".join(w.title() for w in cat_name.replace("-", " ").split())
                    ep_func_name = self.current_editing_item["name"].replace("-", "_").replace(" ", "_").lower()
                    if ep_func_name and ep_func_name[0].isdigit():
                        ep_func_name = f"_{ep_func_name}"
                    cat_proxy = getattr(self.fmp_client, cat_attr)
                    result = getattr(cat_proxy, ep_func_name)(**params)
                    method_used = f"Dynamic: {cat_attr}.{ep_func_name}"
                else:
                    ep_path = ep_data.get("path", "")
                    base = self.fmp_client._base_url
                    url = f"{base}/{ep_path.lstrip('/')}"
                    result = self.fmp_client.request(url, params)
                    method_used = f"Direct: {url}"

                results_text.delete(1.0, tk.END)
                results_text.insert(tk.END, "SUCCESS\n")
                results_text.insert(tk.END, f"Method: {method_used}\n")
                results_text.insert(tk.END, f"Parameters: {json.dumps(params, indent=2)}\n\n")
                results_text.insert(tk.END, f"Response:\n{json.dumps(result, indent=2)}\n")

                usage = self.fmp_client.get_usage_info()
                results_text.insert(tk.END, f"\nUsage Info:\n{json.dumps(usage, indent=2)}\n")

            except Exception as exc:
                results_text.delete(1.0, tk.END)
                results_text.insert(tk.END, f"ERROR\n{exc}\n")

        btn_frame = ttk.Frame(sf)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="Run Test", command=run_test).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Copy Results", command=lambda: self._copy_text(results_text)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Close", command=dlg.destroy).pack(side=tk.LEFT)

    def _copy_text(self, widget: scrolledtext.ScrolledText) -> None:
        content = widget.get(1.0, tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.status_var.set("Copied to clipboard")
        else:
            messagebox.showwarning("Warning", "Nothing to copy")

    # ------------------------------------------------------------------
    # API Key management
    # ------------------------------------------------------------------

    def _refresh_api_key_list(self) -> None:
        keys = [k["name"] for k in self.api_key_manager.list_api_keys()]
        self.api_key_combo["values"] = keys
        cur = self.api_key_manager.current_key_id
        if cur and cur in keys:
            self.api_key_var.set(cur)
        elif keys:
            self.api_key_var.set(keys[0])
            self._on_api_key_changed(None)
        else:
            self.api_key_var.set("")

    def _on_api_key_changed(self, event) -> None:
        selected = self.api_key_var.get()
        if selected and selected != self.api_key_manager.current_key_id:
            if self.api_key_manager.set_current_key(selected):
                self.fmp_client = self.api_key_manager.get_current_client()
                if hasattr(self, 'status_var'):
                    self.status_var.set(f"Active key: {selected}")
            else:
                messagebox.showerror("Error", f"Failed to switch to: {selected}")
                self._refresh_api_key_list()

    def _test_current_api_key(self) -> None:
        key = self.api_key_var.get()
        if not key:
            messagebox.showwarning("Warning", "No API key selected")
            return
        ok, msg = self.api_key_manager.test_api_key(key)
        (messagebox.showinfo if ok else messagebox.showerror)("API Key Test", msg)

    def manage_api_keys(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Manage API Keys")
        dlg.geometry("800x600")
        dlg.transient(self.root)
        dlg.grab_set()

        main_frame = ttk.Frame(dlg, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="API Key Management", font=("TkDefaultFont", 14, "bold")).pack(pady=(0, 15))

        list_frame = ttk.LabelFrame(main_frame, text="Saved API Keys", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        cols = ("Name", "Type", "Description", "Created", "Last Used")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=8)
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=120)
        tree_sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=tree_sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_sb.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_list():
            for item in tree.get_children():
                tree.delete(item)
            for k in self.api_key_manager.list_api_keys():
                created = (k.get("created_at") or "")[:10]
                last_used = (k.get("last_used") or "Never")[:10]
                desc = k.get("description", "")
                if len(desc) > 30:
                    desc = desc[:30] + "..."
                tree.insert("", "end", values=(k["name"], k["key_type"], desc, created, last_used))

        def add_key():
            add_dlg = tk.Toplevel(dlg)
            add_dlg.title("Add API Key")
            add_dlg.geometry("420x380")
            add_dlg.transient(dlg)
            add_dlg.grab_set()

            form = ttk.Frame(add_dlg, padding=15)
            form.pack(fill=tk.BOTH, expand=True)

            ttk.Label(form, text="Name:", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
            name_var = tk.StringVar()
            ttk.Entry(form, textvariable=name_var, width=42).pack(fill=tk.X, pady=(0, 8))

            ttk.Label(form, text="Key Type:", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
            type_var = tk.StringVar(value="Premium")
            type_combo = ttk.Combobox(form, textvariable=type_var, values=API_KEY_TYPES, state="readonly", width=40)
            type_combo.pack(fill=tk.X, pady=(0, 8))

            ttk.Label(form, text="API Key:", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
            key_var = tk.StringVar()
            ttk.Entry(form, textvariable=key_var, show="*", width=42).pack(fill=tk.X, pady=(0, 8))

            ttk.Label(form, text="Description (optional):", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
            desc_var = tk.StringVar()
            ttk.Entry(form, textvariable=desc_var, width=42).pack(fill=tk.X, pady=(0, 8))

            limit_frame = ttk.Frame(form)
            limit_frame.pack(fill=tk.X, pady=(0, 8))
            limit_label = ttk.Label(limit_frame, text="Custom Limit (req/min):")
            limit_var = tk.StringVar()
            limit_entry = ttk.Entry(limit_frame, textvariable=limit_var, width=20)

            def on_type_change(event):
                if type_var.get() in ("Enterprise", "Custom"):
                    limit_label.pack(side=tk.LEFT, padx=(0, 5))
                    limit_entry.pack(side=tk.LEFT)
                else:
                    limit_label.pack_forget()
                    limit_entry.pack_forget()

            type_combo.bind("<<ComboboxSelected>>", on_type_change)

            def save_key():
                n = name_var.get().strip()
                k = key_var.get().strip()
                kt = type_var.get()
                d = desc_var.get().strip()
                if not n or not k:
                    messagebox.showerror("Error", "Name and API Key are required", parent=add_dlg)
                    return
                custom_limit = None
                if kt in ("Enterprise", "Custom"):
                    lv = limit_var.get().strip()
                    if not lv:
                        messagebox.showerror("Error", "Custom limit required for Enterprise/Custom", parent=add_dlg)
                        return
                    try:
                        custom_limit = int(lv)
                        if custom_limit <= 0:
                            raise ValueError
                    except ValueError:
                        messagebox.showerror("Error", "Custom limit must be a positive integer", parent=add_dlg)
                        return
                if self.api_key_manager.add_api_key(n, kt, k, custom_limit, d):
                    messagebox.showinfo("Success", f"API key '{n}' added!", parent=add_dlg)
                    add_dlg.destroy()
                    refresh_list()
                    self._refresh_api_key_list()
                else:
                    messagebox.showerror("Error", f"Key named '{n}' already exists", parent=add_dlg)

            btn_row = ttk.Frame(form)
            btn_row.pack(fill=tk.X, pady=(10, 0))
            ttk.Button(btn_row, text="Save", command=save_key).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(btn_row, text="Cancel", command=add_dlg.destroy).pack(side=tk.LEFT)

        def delete_key():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Warning", "Select a key to delete", parent=dlg)
                return
            name = tree.item(sel[0])["values"][0]
            if messagebox.askyesno("Confirm", f"Delete key '{name}'?", parent=dlg):
                if self.api_key_manager.remove_api_key(name):
                    refresh_list()
                    self._refresh_api_key_list()
                else:
                    messagebox.showerror("Error", "Failed to delete key", parent=dlg)

        def test_key():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Warning", "Select a key to test", parent=dlg)
                return
            name = tree.item(sel[0])["values"][0]
            ok, msg = self.api_key_manager.test_api_key(name)
            (messagebox.showinfo if ok else messagebox.showerror)("API Key Test", msg, parent=dlg)

        btn_row = ttk.Frame(main_frame)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="Add New", command=add_key).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Delete", command=delete_key).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Test", command=test_key).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Refresh", command=refresh_list).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Close", command=dlg.destroy).pack(side=tk.RIGHT)

        refresh_list()

    # ------------------------------------------------------------------
    # Update endpoints
    # ------------------------------------------------------------------

    def _update_endpoints(self) -> None:
        try:
            from fmp_stable_api import update_endpoints
            self.status_var.set("Updating endpoints...")
            self.root.update_idletasks()
            updated = update_endpoints(force=True)
            if updated:
                self._load_endpoints()
                messagebox.showinfo("Update", "Endpoints updated successfully!")
            else:
                messagebox.showinfo(
                    "Update",
                    "No update performed (GitHub URLs may not be configured, or content unchanged).",
                )
        except Exception as exc:
            messagebox.showerror("Update Failed", str(exc))
        self.status_var.set("Ready")

    # ------------------------------------------------------------------
    # Endpoint JSON preview helpers
    # ------------------------------------------------------------------

    def _refresh_endpoint_json(self) -> None:
        if not self.current_editing_item:
            self.endpoint_json_text.config(state="normal")
            self.endpoint_json_text.delete(1.0, tk.END)
            self.endpoint_json_text.insert(1.0, "No endpoint selected")
            self.endpoint_json_text.config(state="disabled")
            return
        try:
            ep_data = self._get_data_at_path(self.current_editing_item["path"])
            if ep_data and isinstance(ep_data, dict):
                preview = {
                    "name": self.current_editing_item["name"],
                    "path": ep_data.get("path", ""),
                    "description": ep_data.get("description", ""),
                    "required_params": ep_data.get("required_params", []),
                    "optional_params": ep_data.get("optional_params", []),
                    "access": ep_data.get("access", {tier: "FULL" for tier in TIERS}),
                }
                text = JSONValidator.format_json(preview, self.config.get("json_indent", 2))
            else:
                text = "No data available"
        except Exception as exc:
            text = f"Error: {exc}"
        self.endpoint_json_text.config(state="normal")
        self.endpoint_json_text.delete(1.0, tk.END)
        self.endpoint_json_text.insert(1.0, text)
        self.endpoint_json_text.config(state="disabled")

    def _copy_endpoint_json(self) -> None:
        if not self.current_editing_item:
            messagebox.showwarning("Warning", "No endpoint selected")
            return
        content = self.endpoint_json_text.get(1.0, tk.END).strip()
        if content and not content.startswith(("No ", "Error")):
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.status_var.set("Endpoint JSON copied")
        else:
            messagebox.showwarning("Warning", "No valid JSON to copy")

    # ------------------------------------------------------------------
    # Category / endpoint CRUD
    # ------------------------------------------------------------------

    def _add_category(self) -> None:
        name = simpledialog.askstring("Add Category", "Enter category name:", parent=self.root)
        if not name:
            return
        name = name.strip()
        normalized = name.replace(" ", "_").replace("-", "_")
        if normalized != name:
            if not messagebox.askyesno("Name Normalized", f"Normalize to '{normalized}'?"):
                return
            name = normalized
        if "endpoints" not in self.endpoints_data:
            self.endpoints_data["endpoints"] = {}
        if name in self.endpoints_data["endpoints"]:
            messagebox.showwarning("Warning", "Category already exists")
            return
        self.endpoints_data["endpoints"][name] = {}
        self._refresh_tree(preserve_expansion=True)
        self._refresh_json_preview()
        self._mark_modified()
        self.status_var.set(f"Added category: {name}")

    def _add_endpoint(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select a category first")
            return
        item = self.tree.item(sel[0])
        if item["values"] and item["values"][0] == "category":
            cat_name = item["text"]
        else:
            parent = self.tree.parent(sel[0])
            cat_name = self.tree.item(parent)["text"]

        ep_name = simpledialog.askstring("Add Endpoint", "Enter endpoint name:", parent=self.root)
        if not ep_name:
            return
        ep_name = ep_name.strip()
        normalized = ep_name.replace(" ", "_").replace("-", "_")
        if normalized != ep_name:
            if not messagebox.askyesno("Name Normalized", f"Normalize to '{normalized}'?"):
                return
            ep_name = normalized

        cat = self.endpoints_data.get("endpoints", {}).get(cat_name)
        if cat is None:
            messagebox.showerror("Error", f"Category '{cat_name}' not found")
            return
        if ep_name in cat:
            messagebox.showwarning("Warning", "Endpoint already exists")
            return
        cat[ep_name] = {
            "path": "",
            "description": "",
            "required_params": [],
            "optional_params": [],
            "access": {tier: "FULL" for tier in TIERS},
        }
        self._refresh_tree(preserve_expansion=True)
        self._refresh_json_preview()
        self._mark_modified()
        self.status_var.set(f"Added endpoint: {cat_name}/{ep_name}")

    def _delete_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Select an item to delete")
            return
        item = self.tree.item(sel[0])
        item_type = item["values"][0] if item["values"] else ""

        if item_type == "category":
            if messagebox.askyesno("Confirm", f"Delete category '{item['text']}' and all its endpoints?"):
                eps = self.endpoints_data.get("endpoints", {})
                if item["text"] in eps:
                    del eps[item["text"]]
                    self._refresh_tree()
                    self._refresh_json_preview()
                    self._mark_modified()
                    self.status_var.set(f"Deleted category: {item['text']}")
        elif item_type == "endpoint":
            cat_item = self.tree.parent(sel[0])
            cat_name = self.tree.item(cat_item)["text"]
            if messagebox.askyesno("Confirm", f"Delete endpoint '{item['text']}'?"):
                eps = self.endpoints_data.get("endpoints", {})
                if cat_name in eps and item["text"] in eps[cat_name]:
                    del eps[cat_name][item["text"]]
                    self._refresh_tree()
                    self._refresh_json_preview()
                    self._mark_modified()
                    self.status_var.set(f"Deleted: {cat_name}/{item['text']}")

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _mark_modified(self) -> None:
        self.modified = True
        self.root.title(f"FMP Endpoints Manager - {self.current_file} *")

    def _save_file(self) -> None:
        if not self.current_file:
            self._save_as_file()
            return
        with open(self.current_file, "w", encoding="utf-8") as f:
            json.dump(self.endpoints_data, f, indent=self.config.get("json_indent", 2), ensure_ascii=False)
        self.modified = False
        self.root.title(f"FMP Endpoints Manager - {self.current_file}")
        self.status_var.set(f"Saved {self.current_file}")

    def _save_as_file(self) -> None:
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if filename:
            self.current_file = filename
            self._save_file()

    def _open_file(self) -> None:
        if self.modified:
            if messagebox.askyesno("Unsaved Changes", "Save before opening?"):
                self._save_file()
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8") as f:
                self.endpoints_data = json.load(f)
            self.current_file = filename
            self.modified = False
            self._populate_info_panel()
            self._refresh_tree()
            self._refresh_json_preview()
            self.status_var.set(f"Opened: {filename}")
            self.root.title(f"FMP Endpoints Manager - {filename}")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to open file: {exc}")

    def _new_file(self) -> None:
        if self.modified:
            if messagebox.askyesno("Unsaved Changes", "Save before creating new file?"):
                self._save_file()
        self.endpoints_data = {}
        self.current_file = "new_endpoints.json"
        self.modified = False
        self._clear_info_panel()
        self._refresh_tree()
        self._refresh_json_preview()
        self.status_var.set("New file created")
        self.root.title("FMP Endpoints Manager - new_endpoints.json")

    # ------------------------------------------------------------------
    # JSON validation
    # ------------------------------------------------------------------

    def _validate_json(self) -> None:
        errors = JSONValidator.validate_json_structure(self.endpoints_data)
        if errors:
            messagebox.showerror("Validation Errors", "\n".join(f"- {e}" for e in errors))
        else:
            messagebox.showinfo("Validation", "JSON structure is valid!")

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def show_preferences(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Preferences")
        win.geometry("400x250")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        auto_save_var = tk.BooleanVar(value=self.config.get("auto_save", False))
        indent_var = tk.IntVar(value=self.config.get("json_indent", 2))
        strict_var = tk.BooleanVar(value=self.config.get("validation_strict", False))

        ttk.Checkbutton(frame, text="Auto Save", variable=auto_save_var).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)

        ttk.Label(frame, text="JSON Indent:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(frame, from_=0, to=8, textvariable=indent_var, width=10).grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Checkbutton(frame, text="Strict Validation", variable=strict_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=5)

        def save():
            self.config.set("auto_save", auto_save_var.get())
            self.config.set("json_indent", indent_var.get())
            self.config.set("validation_strict", strict_var.get())
            self.config.save_config()
            messagebox.showinfo("Success", "Preferences saved!", parent=win)
            win.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=3, column=0, columnspan=2, pady=20)
        ttk.Button(btn_row, text="Save", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side=tk.LEFT, padx=5)

    def _reset_to_defaults(self) -> None:
        if messagebox.askyesno("Reset", "Reset all settings to defaults?"):
            self.config.config = DEFAULT_CONFIG.copy()
            self.config.save_config()
            messagebox.showinfo("Success", "Settings reset to defaults!")

    # ------------------------------------------------------------------
    # About
    # ------------------------------------------------------------------

    def show_about(self) -> None:
        messagebox.showinfo(
            "About FMP Endpoints Manager",
            "FMP Endpoints Manager\n\n"
            "A GUI application for managing fmp_endpoints.json.\n\n"
            "Features:\n"
            "- Hierarchical tree view of categories and endpoints\n"
            "- Form editor with parameter management\n"
            "- Live JSON preview window\n"
            "- API key manager (add/remove/test/switch)\n"
            "- Live endpoint testing\n"
            "- Import/export JSON\n"
            "- Update Endpoints from GitHub\n\n"
            "Keys stored in ~/.fmp/api_keys.json (base64 obfuscated).",
        )

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def _on_closing(self) -> None:
        if self.modified:
            if messagebox.askyesno("Quit", "You have unsaved changes. Save before quitting?"):
                self._save_file()
        self.root.destroy()


###############################################################################
# Entry point
###############################################################################

def main() -> None:
    """Launch the FMP Endpoints Manager GUI."""
    root = tk.Tk()
    app = FMPEndpointsManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
