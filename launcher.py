import sys
import subprocess
import os
REQUIRED = ["customtkinter", "minecraft-launcher-lib"]

def _check_and_install():
    import importlib
    mapping = {"minecraft-launcher-lib": "minecraft_launcher_lib"}
    missing = []
    for pkg in REQUIRED:
        mod = mapping.get(pkg, pkg.replace("-", "_"))
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        import tkinter as _tk
        import tkinter.messagebox as _mb
        root = _tk.Tk(); root.withdraw()
        _mb.showinfo("Installation des dépendances",
            f"Installation des modules manquants :\n{', '.join(missing)}\n\nCela peut prendre quelques secondes…")
        root.destroy()
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet"] + missing)

_check_and_install()
import customtkinter as ctk
import minecraft_launcher_lib
import threading
import uuid
import json
import shutil
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import webbrowser
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

UA = {"User-Agent": "Mozilla/5.0 WwheatyLauncher/1.0"}

MICROSOFT_CLIENT_ID = "6aa81b53-37c8-4c02-80f7-1677618e4f33"

FORGE_META_URL    = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
FORGE_JAR_URL     = "https://maven.minecraftforge.net/net/minecraftforge/forge/{v}/forge-{v}-installer.jar"
NEOFORGE_META_URL = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
NEOFORGE_JAR_URL  = "https://maven.neoforged.net/releases/net/neoforged/neoforge/{v}/neoforge-{v}-installer.jar"
FABRIC_LOADER_URL = "https://meta.fabricmc.net/v2/versions/loader"
VANILLA_MANIFEST  = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
ELYBY_AUTH_URL    = "https://authserver.ely.by/auth/authenticate"
AUTHLIB_JAR_URL   = "https://github.com/yushijinhun/authlib-injector/releases/download/v1.2.5/authlib-injector-1.2.5.jar"
AUTHLIB_LOCAL     = os.path.abspath("./wwheaty_launcher_data/authlib-injector.jar")

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def http_post_json(url, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", **UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def http_download(url, dest, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        f.write(r.read())


class WwheatyLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.base_dir    = os.path.abspath("./wwheaty_launcher_data")
        self.mods_dir    = os.path.join(self.base_dir, "mods")
        self.config_path = os.path.join(self.base_dir, "launcher_profiles.json")

        for d in [self.base_dir, self.mods_dir]:
            os.makedirs(d, exist_ok=True)

        self.load_settings()
        self._auth = {
            "mode":     self.settings.get("auth_mode", "offline"),
            "username": self.settings.get("pseudo", "Player"),
            "uuid":     self.settings.get("auth_uuid", ""),
            "token":    self.settings.get("auth_token", "0"),
        }

        self.title("Wwheaty Launcher")
        self.geometry("680x760")
        self.resizable(False, False)

        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(pady=(14, 4), padx=30, fill="x")
        ctk.CTkButton(top_frame, text="⚙  Gestionnaire de mods",
                      command=self.open_mods_window,
                      fg_color="transparent", border_width=1).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(top_frame, text="⬇  Installer une version",
                      command=self.open_install_window,
                      fg_color="transparent", border_width=1).pack(side="left", expand=True, fill="x")

        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(pady=6, padx=30, fill="both", expand=True)

        ctk.CTkLabel(self.main_frame, text="Compte", font=("Roboto", 13, "bold")).pack(pady=(10, 2))

        self.account_label = ctk.CTkLabel(
            self.main_frame,
            text=self._account_display(),
            text_color=self._account_color()
        )
        self.account_label.pack()

        self.btn_account = ctk.CTkButton(
            self.main_frame, text="Changer de compte",
            command=self.open_account_window,
            fg_color="transparent", border_width=1, width=220
        )
        self.btn_account.pack(pady=(4, 10))

        ctk.CTkLabel(self.main_frame, text="Version à lancer :").pack(pady=(4, 0))
        self.update_profile_list()
        self.combo_profile = ctk.CTkOptionMenu(self.main_frame, values=self.profile_names, width=380)
        self.combo_profile.pack(pady=10)

        self.btn_play = ctk.CTkButton(
            self, text="▶  Jouer",
            command=self.start_launch_thread,
            font=("Roboto", 20, "bold"), height=56, fg_color="#2ecc71"
        )
        self.btn_play.pack(pady=(10, 4), padx=30, fill="x")

        self.status_label = ctk.CTkLabel(self, text="Prêt", text_color="gray")
        self.status_label.pack(pady=(2, 2))

        self.progress_bar = ctk.CTkProgressBar(self, width=600, height=12)
        self.progress_bar.pack(padx=30, pady=(0, 10), fill="x")
        self.progress_bar.set(0)
        self.progress_bar.configure(mode="determinate")

    def _account_display(self):
        mode = self._auth["mode"]
        name = self._auth["username"]
        if mode == "offline":
            return f"Hors-ligne  —  {name}"
        elif mode == "elyby":
            return f"Ely.by  —  {name}"
        elif mode == "microsoft":
            return f"Microsoft  —  {name}"
        return name

    def _account_color(self):
        mode = self._auth["mode"]
        if mode == "microsoft": return "#3498db"
        if mode == "elyby":     return "#e67e22"
        return "gray"

    def _refresh_account_label(self):
        self.account_label.configure(
            text=self._account_display(),
            text_color=self._account_color()
        )
    def open_account_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Choisir un compte")
        win.geometry("500x480")
        win.attributes("-topmost", True)

        tabs = ctk.CTkTabview(win)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        tabs.add("Hors-ligne")
        tabs.add("Ely.by")
        tabs.add("Microsoft")

        self._build_offline_tab(tabs.tab("Hors-ligne"), win)
        self._build_elyby_tab(tabs.tab("Ely.by"), win)
        self._build_microsoft_tab(tabs.tab("Microsoft"), win)

    def _build_offline_tab(self, tab, win):
        ctk.CTkLabel(tab, text="MODE HORS-LIGNE", font=("Roboto", 13, "bold")).pack(pady=(18, 4))
        ctk.CTkLabel(tab, text="Joue sur les serveurs crackés (online-mode=false).\nAucun compte requis.",
                     text_color="gray", justify="center").pack(pady=4)

        ctk.CTkLabel(tab, text="Pseudo :").pack(pady=(14, 0))
        entry = ctk.CTkEntry(tab, width=260, placeholder_text="Ton pseudo")
        entry.pack(pady=6)
        entry.insert(0, self._auth["username"] if self._auth["mode"] == "offline" else "Player")

        def apply():
            name = entry.get().strip() or "Player"
            self._auth = {"mode": "offline", "username": name, "uuid": str(uuid.uuid4()), "token": "0"}
            self._save_auth()
            self._refresh_account_label()
            win.destroy()

        ctk.CTkButton(tab, text="Jouer en hors-ligne", fg_color="#2ecc71",
                      command=apply).pack(pady=18)

    def _build_elyby_tab(self, tab, win):
        ctk.CTkLabel(tab, text="COMPTE ELY.BY", font=("Roboto", 13, "bold")).pack(pady=(18, 4))
        ctk.CTkLabel(tab,
                     text="Crée un compte gratuit sur ely.by\nPermet de jouer sur les serveurs qui utilisent authlib-injector.",
                     text_color="gray", justify="center").pack(pady=4)

        ctk.CTkLabel(tab, text="Email :").pack(pady=(12, 0))
        entry_email = ctk.CTkEntry(tab, width=300, placeholder_text="email@example.com")
        entry_email.pack(pady=4)

        ctk.CTkLabel(tab, text="Mot de passe :").pack(pady=(6, 0))
        entry_pass = ctk.CTkEntry(tab, width=300, show="*", placeholder_text="••••••••")
        entry_pass.pack(pady=4)

        status = ctk.CTkLabel(tab, text="", text_color="gray")
        status.pack(pady=4)

        def login():
            email = entry_email.get().strip()
            pwd   = entry_pass.get()
            if not email or not pwd:
                status.configure(text="Remplis les champs.", text_color="red")
                return
            status.configure(text="Connexion…", text_color="gray")
            threading.Thread(target=_do_elyby, args=(email, pwd), daemon=True).start()

        def _do_elyby(email, pwd):
            try:
                resp = http_post_json(ELYBY_AUTH_URL, {
                    "username": email,
                    "password": pwd,
                    "clientToken": str(uuid.uuid4()),
                    "agent": {"name": "Minecraft", "version": 1}
                })
                name  = resp["selectedProfile"]["name"]
                uid   = resp["selectedProfile"]["id"]
                token = resp["accessToken"]
                self._auth = {"mode": "elyby", "username": name, "uuid": uid, "token": token}
                self._save_auth()
                self._refresh_account_label()

                if not os.path.exists(AUTHLIB_LOCAL):
                    status.configure(text="Téléchargement authlib-injector…", text_color="gray")
                    http_download(AUTHLIB_JAR_URL, AUTHLIB_LOCAL)

                status.configure(text=f"Connecté en tant que {name} !", text_color="green")
                win.after(1200, win.destroy)
            except urllib.error.HTTPError as e:
                body = e.read().decode()
                try:
                    msg = json.loads(body).get("errorMessage", body)
                except Exception:
                    msg = body
                status.configure(text=f"Erreur : {msg}", text_color="red")
            except Exception as e:
                status.configure(text=f"Erreur : {e}", text_color="red")

        ctk.CTkButton(tab, text="Se connecter à Ely.by", fg_color="#e67e22",
                      command=login).pack(pady=12)
        ctk.CTkButton(tab, text="Créer un compte ely.by",
                      fg_color="transparent", border_width=1,
                      command=lambda: webbrowser.open("https://account.ely.by/register")).pack(pady=2)

  
    def _build_microsoft_tab(self, tab, win):
        ctk.CTkLabel(tab, text="COMPTE MICROSOFT", font=("Roboto", 13, "bold")).pack(pady=(18, 4))
        ctk.CTkLabel(tab,
                     text="Joue sur tous les serveurs (online-mode=true).\nNécessite un compte Minecraft acheté.",
                     text_color="gray", justify="center").pack(pady=4)

        status = ctk.CTkLabel(tab, text="", text_color="gray", wraplength=420)
        status.pack(pady=8)

        def login_ms():
            status.configure(text="Ouverture du navigateur…", text_color="gray")
            threading.Thread(target=_do_microsoft, daemon=True).start()

        def _do_microsoft():
            try:
                import http.server
                import socketserver

                REDIRECT = "http://localhost:9876"
                login_url, state, code_verifier = minecraft_launcher_lib.microsoft_account.get_secure_login_data(
                    MICROSOFT_CLIENT_ID, REDIRECT
                )

                auth_code_holder = {}

                class Handler(http.server.BaseHTTPRequestHandler):
                    def do_GET(self):
                        full_url = f"http://localhost:9876{self.path}"
                        if minecraft_launcher_lib.microsoft_account.url_contains_auth_code(full_url):
                            auth_code_holder["url"] = full_url
                        self.send_response(200)
                        self.send_header("Content-type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(
                            b"<html><body style='font-family:sans-serif;text-align:center;padding-top:80px'>"
                            b"<h2>Connexion r&#233;ussie !</h2>"
                            b"<p>Tu peux fermer cette page et revenir au launcher.</p>"
                            b"</body></html>"
                        )
                    def log_message(self, *args):
                        pass  

                with socketserver.TCPServer(("localhost", 9876), Handler) as server:
                    server.timeout = 1
                    status.configure(text="Connecte-toi dans le navigateur qui vient de s'ouvrir…", text_color="gray")
                    webbrowser.open(login_url)
                    for _ in range(180):
                        server.handle_request()
                        if "url" in auth_code_holder:
                            break

                if "url" not in auth_code_holder:
                    status.configure(text="Timeout — réessaie.", text_color="red")
                    return

                status.configure(text="Authentification en cours…", text_color="gray")
                auth_code = minecraft_launcher_lib.microsoft_account.parse_auth_code_url(
                    auth_code_holder["url"], state
                )
                acc = minecraft_launcher_lib.microsoft_account.complete_login(
                    MICROSOFT_CLIENT_ID, REDIRECT, auth_code, code_verifier
                )

                self._auth = {
                    "mode":          "microsoft",
                    "username":      acc["name"],
                    "uuid":          acc["id"],
                    "token":         acc["access_token"],
                    "refresh_token": acc.get("refresh_token", "")
                }
                self._save_auth()
                self._refresh_account_label()
                status.configure(text=f"Connecté : {acc['name']} !", text_color="green")
                win.after(1500, win.destroy)

            except Exception as e:
                status.configure(text=f"Erreur : {e}", text_color="red")

        ctk.CTkButton(tab, text="Se connecter avec Microsoft", fg_color="#3498db",
                      command=login_ms).pack(pady=12)
        ctk.CTkLabel(tab,
                     text="WORK IN PROGRESS.",
                     text_color="gray", justify="center", font=("Roboto", 11)).pack(pady=4)

    def load_settings(self):
        if os.path.exists(self.config_path):
            with open(self.config_path) as f:
                self.settings = json.load(f)
        else:
            self.settings = {"pseudo": "Player", "ram": "4G"}

    def save_settings(self):
        self.settings["pseudo"] = self._auth["username"]
        with open(self.config_path, "w") as f:
            json.dump(self.settings, f, indent=4)

    def _save_auth(self):
        self.settings["auth_mode"]  = self._auth["mode"]
        self.settings["pseudo"]     = self._auth["username"]
        self.settings["auth_uuid"]  = self._auth["uuid"]
        self.settings["auth_token"] = self._auth["token"]
        with open(self.config_path, "w") as f:
            json.dump(self.settings, f, indent=4)

    def set_status(self, msg, color="gray"):
        self.status_label.configure(text=msg, text_color=color)

    def update_profile_list(self):
        installed = minecraft_launcher_lib.utils.get_installed_versions(self.base_dir)
        self.profile_names = [v["id"] for v in installed] if installed else ["Aucune version"]

    def refresh_main_list(self):
        self.update_profile_list()
        self.ensure_launcher_profiles()
        self.combo_profile.configure(values=self.profile_names)
        if self.profile_names:
            self.combo_profile.set(self.profile_names[0])

    def ensure_launcher_profiles(self):
        profiles_path = os.path.join(self.base_dir, "launcher_profiles.json")
        installed = minecraft_launcher_lib.utils.get_installed_versions(self.base_dir)
        if not installed:
            return
        if os.path.exists(profiles_path):
            try:
                with open(profiles_path) as f:
                    data = json.load(f)
            except Exception:
                data = {}
        else:
            data = {}
        if "profiles" not in data or not isinstance(data["profiles"], dict):
            data["profiles"] = {}
        data.setdefault("clientToken", str(uuid.uuid4()).replace("-", ""))
        data.setdefault("launcherVersion", {"format": 21, "name": "1.6.84", "profilesFormat": 2})
        data.setdefault("settings", {"enableAdvanced": False, "profileSorting": "ByLastPlayed"})
        for v in installed:
            vid = v["id"]
            if vid not in data["profiles"]:
                data["profiles"][vid] = {
                    "created": "1970-01-01T00:00:00.000Z",
                    "gameDir": self.base_dir,
                    "icon": "Grass",
                    "lastUsed": "1970-01-01T00:00:00.000Z",
                    "lastVersionId": vid,
                    "name": vid,
                    "type": "custom",
                    "javaArgs": f"-Xmx{self.settings.get('ram', '4G')} -XX:+UnlockExperimentalVMOptions -XX:+UseG1GC"
                }
        if self.profile_names and self.profile_names[0] != "Aucune version":
            data["selectedProfile"] = self.profile_names[0]
        with open(profiles_path, "w") as f:
            json.dump(data, f, indent=2)

    def open_install_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Installer une version")
        win.geometry("640x580")
        win.attributes("-topmost", True)
        tabs = ctk.CTkTabview(win)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        tabs.add("Vanilla")
        tabs.add("Forge")
        tabs.add("NeoForge")
        tabs.add("Fabric")
        tabs.add("Installeur .jar")
        self._build_vanilla_tab(tabs.tab("Vanilla"))
        self._build_forge_tab(tabs.tab("Forge"))
        self._build_neoforge_tab(tabs.tab("NeoForge"))
        self._build_fabric_tab(tabs.tab("Fabric"))
        self._build_external_tab(tabs.tab("Installeur .jar"))

    def _build_vanilla_tab(self, tab):
        ctk.CTkLabel(tab, text="INSTALLER VANILLA", font=("Roboto", 13, "bold")).pack(pady=(18, 6))
        ctk.CTkLabel(tab, text="1. Type de version :").pack()
        self.vanilla_type_combo = ctk.CTkOptionMenu(tab, values=["release", "snapshot", "old_beta", "old_alpha"], width=300)
        self.vanilla_type_combo.pack(pady=6)
        ctk.CTkButton(tab, text="Chercher les versions", width=260, command=self._load_vanilla_versions).pack(pady=4)
        ctk.CTkLabel(tab, text="2. Version :").pack(pady=(10, 0))
        self.vanilla_combo = ctk.CTkOptionMenu(tab, values=["(cliquez sur Chercher)"], width=420)
        self.vanilla_combo.pack(pady=6)n
        self.vanilla_progress_label = ctk.CTkLabel(tab, text="", text_color="gray", font=("Roboto", 11))
        self.vanilla_progress_label.pack(pady=(6, 0))
        self.vanilla_progress_bar = ctk.CTkProgressBar(tab, width=400, height=14)
        self.vanilla_progress_bar.pack(pady=(4, 8))
        self.vanilla_progress_bar.set(0)

        self.btn_vanilla_install = ctk.CTkButton(tab, text="⬇  INSTALLER", fg_color="#3498db",
            font=("Roboto", 13, "bold"), height=44, command=self._start_install_vanilla)
        self.btn_vanilla_install.pack(pady=8)
        ctk.CTkButton(tab, text="Rafraîchir la liste principale", command=self.refresh_main_list,
            fg_color="transparent", border_width=1).pack()

    def _load_vanilla_versions(self):
        self.vanilla_combo.configure(values=["Chargement..."])
        threading.Thread(target=self.__fetch_vanilla_versions, daemon=True).start()

    def __fetch_vanilla_versions(self):
        try:
            data = json.loads(http_get(VANILLA_MANIFEST))
            typ = self.vanilla_type_combo.get()
            versions = [v["id"] for v in data["versions"] if v["type"] == typ]
            if versions:
                self.vanilla_combo.configure(values=versions)
                self.vanilla_combo.set(versions[0])
                self.set_status(f"{len(versions)} version(s) {typ} disponible(s)")
            else:
                self.vanilla_combo.configure(values=["Aucune version"])
                self.vanilla_combo.set("Aucune version")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def _start_install_vanilla(self):
        v = self.vanilla_combo.get()
        if v in ("(cliquez sur Chercher)", "Chargement...", "Aucune version"):
            messagebox.showwarning("Attention", "Sélectionnez une version valide.")
            return
        threading.Thread(target=self._install_vanilla, args=(v,), daemon=True).start()

    def _install_vanilla(self, v):
        try:
            self.btn_vanilla_install.configure(state="disabled")
            self.vanilla_progress_bar.set(0)
            self.set_status(f"Téléchargement de Vanilla {v}…")

            self._vanilla_total = 0

            def on_progress(current, total, status):
                if total > 0:
                    self.vanilla_progress_bar.set(current / total)
                    self.progress_bar.set(current / total)
                self.vanilla_progress_label.configure(text=status[:60] if status else "")
                self.set_status(status[:80] if status else f"Installation de {v}…")

            def on_max(total):
                self._vanilla_total = total

            callback = {
                "setStatus":   lambda s: on_progress(0, 1, s),
                "setProgress": lambda c: self.vanilla_progress_bar.set(
                    c / self._vanilla_total if self._vanilla_total else 0
                ),
                "setMax":      on_max,
            }

            minecraft_launcher_lib.install.install_minecraft_version(v, self.base_dir, callback)
            self.vanilla_progress_bar.set(1)
            self.progress_bar.set(1)
            self.refresh_main_list()
            self.set_status(f"Vanilla {v} installé !", "green")
            self.vanilla_progress_label.configure(text="Installation terminée !")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))
            self.set_status("Erreur installation Vanilla", "red")
        finally:
            self.btn_vanilla_install.configure(state="normal")

    def _build_forge_tab(self, tab):
        ctk.CTkLabel(tab, text="INSTALLER FORGE", font=("Roboto", 13, "bold")).pack(pady=(18, 6))
        ctk.CTkLabel(tab, text="1. Version Minecraft cible :").pack()
        row = ctk.CTkFrame(tab, fg_color="transparent"); row.pack(pady=4)
        self.entry_forge_mc = ctk.CTkEntry(row, placeholder_text="Ex: 1.20.1", width=180)
        self.entry_forge_mc.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Chercher", width=140,
            command=lambda: self._load_maven_versions(FORGE_META_URL, self.forge_combo,
                self.entry_forge_mc.get().strip(), "Forge")).pack(side="left")
        ctk.CTkLabel(tab, text="2. Version Forge :").pack(pady=(10, 0))
        self.forge_combo = ctk.CTkOptionMenu(tab, values=["(entrez une version MC)"], width=420)
        self.forge_combo.pack(pady=6)
        self.btn_forge_install = ctk.CTkButton(tab, text="⬇  INSTALLER FORGE", fg_color="#e67e22",
            font=("Roboto", 13, "bold"), height=44,
            command=lambda: self._start_install_jar_loader(FORGE_JAR_URL, self.forge_combo, self.btn_forge_install, "Forge"))
        self.btn_forge_install.pack(pady=14)
        ctk.CTkButton(tab, text="Rafraîchir la liste principale", command=self.refresh_main_list,
            fg_color="transparent", border_width=1).pack()

    def _build_neoforge_tab(self, tab):
        ctk.CTkLabel(tab, text="INSTALLER NEOFORGE", font=("Roboto", 13, "bold")).pack(pady=(18, 6))
        ctk.CTkLabel(tab, text="1. Version Minecraft cible :").pack()
        row = ctk.CTkFrame(tab, fg_color="transparent"); row.pack(pady=4)
        self.entry_neo_mc = ctk.CTkEntry(row, placeholder_text="Ex: 1.21.1", width=180)
        self.entry_neo_mc.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Chercher", width=140,
            command=lambda: self._load_neoforge_versions(self.entry_neo_mc.get().strip())).pack(side="left")
        ctk.CTkLabel(tab, text="2. Version NeoForge :").pack(pady=(10, 0))
        self.neo_combo = ctk.CTkOptionMenu(tab, values=["(entrez une version MC)"], width=420)
        self.neo_combo.pack(pady=6)
        self.btn_neo_install = ctk.CTkButton(tab, text="⬇  INSTALLER NEOFORGE", fg_color="#9b59b6",
            font=("Roboto", 13, "bold"), height=44,
            command=lambda: self._start_install_jar_loader(NEOFORGE_JAR_URL, self.neo_combo, self.btn_neo_install, "NeoForge"))
        self.btn_neo_install.pack(pady=14)
        ctk.CTkButton(tab, text="Rafraîchir la liste principale", command=self.refresh_main_list,
            fg_color="transparent", border_width=1).pack()

    def _load_neoforge_versions(self, mc_version):
        if not mc_version: return
        neo_prefix = mc_version[2:] if mc_version.startswith("1.") else mc_version
        self.neo_combo.configure(values=["Chargement..."])
        self.set_status("Récupération des versions NeoForge…")
        threading.Thread(target=self.__fetch_maven_versions_filtered,
            args=(NEOFORGE_META_URL, self.neo_combo, neo_prefix, "NeoForge"), daemon=True).start()

    def _build_fabric_tab(self, tab):
        ctk.CTkLabel(tab, text="INSTALLER FABRIC", font=("Roboto", 13, "bold")).pack(pady=(18, 6))
        ctk.CTkLabel(tab, text="1. Version Minecraft cible :").pack()
        row = ctk.CTkFrame(tab, fg_color="transparent"); row.pack(pady=4)
        self.entry_fabric_mc = ctk.CTkEntry(row, placeholder_text="Ex: 1.21.4", width=180)
        self.entry_fabric_mc.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Chercher", width=140,
            command=lambda: self._load_fabric_versions(self.entry_fabric_mc.get().strip())).pack(side="left")
        ctk.CTkLabel(tab, text="2. Version du loader Fabric :").pack(pady=(10, 0))
        self.fabric_combo = ctk.CTkOptionMenu(tab, values=["(entrez une version MC)"], width=420)
        self.fabric_combo.pack(pady=6)
        self.btn_fabric_install = ctk.CTkButton(tab, text="⬇  INSTALLER FABRIC", fg_color="#1abc9c",
            font=("Roboto", 13, "bold"), height=44, command=self._start_install_fabric)
        self.btn_fabric_install.pack(pady=14)
        ctk.CTkButton(tab, text="Rafraîchir la liste principale", command=self.refresh_main_list,
            fg_color="transparent", border_width=1).pack()

    def _load_fabric_versions(self, mc_version):
        if not mc_version: return
        self.fabric_combo.configure(values=["Chargement..."])
        self.set_status("Récupération des versions Fabric…")
        threading.Thread(target=self.__fetch_fabric_versions, args=(mc_version,), daemon=True).start()

    def __fetch_fabric_versions(self, mc_version):
        try:
            data = json.loads(http_get(FABRIC_LOADER_URL))
            versions = [v["version"] for v in data]
            if versions:
                self.fabric_combo.configure(values=versions)
                self.fabric_combo.set(versions[0])
                self._fabric_mc_version = mc_version
                self.set_status(f"{len(versions)} version(s) Fabric trouvée(s)")
            else:
                self.fabric_combo.configure(values=["Aucune version"])
                self.fabric_combo.set("Aucune version")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def _start_install_fabric(self):
        loader = self.fabric_combo.get()
        mc = getattr(self, "_fabric_mc_version", "").strip()
        if not mc or loader in ("(entrez une version MC)", "Chargement...", "Aucune version"):
            messagebox.showwarning("Attention", "Sélectionnez une version Fabric valide.")
            return
        threading.Thread(target=self._install_fabric, args=(mc, loader), daemon=True).start()

    def _install_fabric(self, mc_version, loader_version):
        try:
            self.btn_fabric_install.configure(state="disabled")
            installed_ids = [v["id"] for v in minecraft_launcher_lib.utils.get_installed_versions(self.base_dir)]
            if mc_version not in installed_ids:
                self.set_status(f"Installation de Vanilla {mc_version} (requis)…")
                minecraft_launcher_lib.install.install_minecraft_version(mc_version, self.base_dir)
            self.set_status(f"Installation de Fabric {loader_version} pour MC {mc_version}…")
            minecraft_launcher_lib.fabric.install_fabric(mc_version, self.base_dir, loader_version)
            self.refresh_main_list()
            self.set_status(f"Fabric {loader_version} installé !", "green")
            messagebox.showinfo("Succès", f"Fabric {loader_version} installé pour Minecraft {mc_version} !")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))
            self.set_status("Erreur installation Fabric", "red")
        finally:
            self.btn_fabric_install.configure(state="normal")

    def _build_external_tab(self, tab):
        guide = (
            "INSTALLATION MANUELLE (Forge / Fabric / autre)\n\n"
            "1. Téléchargez l'installeur .jar officiel.\n"
            "2. Cliquez sur le bouton ci-dessous pour le lancer.\n"
            "3. Choisissez 'Install Client'.\n"
            "4. IMPORTANT — Définissez ce dossier comme cible :\n"
            f"   ➔  {self.base_dir}\n\n"
            "5. Une fois terminé, cliquez sur 'Rafraîchir'."
        )
        ctk.CTkLabel(tab, text=guide, justify="left", wraplength=540, text_color="white").pack(pady=20, padx=10)
        ctk.CTkButton(tab, text="LANCER UN INSTALLEUR EXTERNE (.JAR)", fg_color="#e67e22", height=44,
            command=self._run_external_installer).pack(pady=10)
        ctk.CTkButton(tab, text="Rafraîchir la liste principale", command=self.refresh_main_list,
            fg_color="transparent", border_width=1).pack(pady=5)

    def _run_external_installer(self):
        path = filedialog.askopenfilename(filetypes=[("Java Installer", "*.jar")])
        if path:
            subprocess.Popen(["java", "-jar", path])

    def _load_maven_versions(self, meta_url, combo_widget, mc_version, loader_name):
        if not mc_version: return
        combo_widget.configure(values=["Chargement..."])
        self.set_status(f"Récupération des versions {loader_name}…")
        threading.Thread(target=self.__fetch_maven_versions_filtered,
            args=(meta_url, combo_widget, mc_version, loader_name), daemon=True).start()

    def __fetch_maven_versions_filtered(self, meta_url, combo_widget, prefix, loader_name):
        try:
            xml_data = http_get(meta_url)
            root = ET.fromstring(xml_data)
            all_versions = [v.text for v in root.iter("version") if v.text]
            versions = [v for v in all_versions if v.startswith(prefix + "-") or v.startswith(prefix + ".")]
            versions = list(reversed(versions))
            if versions:
                combo_widget.configure(values=versions)
                combo_widget.set(versions[0])
                self.set_status(f"{len(versions)} version(s) {loader_name} trouvée(s)")
            else:
                combo_widget.configure(values=["Aucune version trouvée"])
                combo_widget.set("Aucune version trouvée")
                self.set_status(f"Aucune version {loader_name} pour cette MC")
        except Exception as e:
            messagebox.showerror("Erreur réseau", f"Impossible de récupérer {loader_name} :\n{e}")

    def _start_install_jar_loader(self, jar_url_template, combo_widget, btn, loader_name):
        version = combo_widget.get()
        if not version or version in ("Chargement...", "Aucune version trouvée", "(entrez une version MC)"):
            messagebox.showwarning("Attention", f"Sélectionnez une version {loader_name} valide.")
            return
        threading.Thread(target=self._install_jar_loader,
            args=(jar_url_template, version, btn, loader_name), daemon=True).start()

    def _install_jar_loader(self, jar_url_template, version, btn, loader_name):
        try:
            btn.configure(state="disabled")
            mc_base = version.split("-")[0]
            installed_ids = [v["id"] for v in minecraft_launcher_lib.utils.get_installed_versions(self.base_dir)]
            if mc_base not in installed_ids:
                self.set_status(f"Installation de Vanilla {mc_base} (requis)…")
                minecraft_launcher_lib.install.install_minecraft_version(mc_base, self.base_dir)
            url = jar_url_template.format(v=version)
            installer_path = os.path.join(self.base_dir, f"{loader_name.lower()}-{version}-installer.jar")
            self.set_status(f"Téléchargement de {loader_name} {version}…")
            http_download(url, installer_path)
            self.set_status(f"Installation silencieuse de {loader_name} {version}…")
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                ["java", "-jar", installer_path, "--installClient", self.base_dir],
                capture_output=True, text=True, **kwargs)
            if result.returncode == 0:
                try: os.remove(installer_path)
                except Exception: pass
                self.refresh_main_list()
                self.set_status(f"{loader_name} {version} installé !", "green")
                messagebox.showinfo("Succès", f"{loader_name} {version} installé !")
            else:
                self.set_status("Ouverture de l'installeur graphique…")
                self._show_installer_guide(loader_name, installer_path)
        except Exception as e:
            messagebox.showerror("Erreur", f"Échec installation {loader_name} :\n{e}")
            self.set_status(f"Erreur installation {loader_name}", "red")
        finally:
            btn.configure(state="normal")

    def _show_installer_guide(self, loader_name, installer_path):
        import tkinter as tk
        guide_win = tk.Toplevel()
        guide_win.title(f"Installation {loader_name}")
        guide_win.geometry("520x320")
        guide_win.attributes("-topmost", True)
        guide_win.configure(bg="#1a1a2e")
        tk.Label(guide_win, text=f"Installation {loader_name}", font=("Arial", 14, "bold"),
            fg="white", bg="#1a1a2e").pack(pady=(20, 5))
        tk.Label(guide_win,
            text=(f"L'installeur {loader_name} va s'ouvrir.\n\n"
                  f"  1  Choisissez 'Install Client'\n\n"
                  f"  2  Changez le dossier d'installation :\n\n"
                  f"       {self.base_dir}\n\n"
                  f"  3  Cliquez OK dans l'installeur\n\n"
                  f"  4  Revenez ici et cliquez 'Terminé'"),
            font=("Arial", 11), fg="#cccccc", bg="#1a1a2e", justify="left", wraplength=460).pack(padx=20, pady=5)
        def launch_and_wait():
            kwargs = {}
            if os.name == "nt": kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            subprocess.Popen(["java", "-jar", installer_path], **kwargs).wait()
        threading.Thread(target=launch_and_wait, daemon=True).start()
        def on_done():
            guide_win.destroy()
            self.refresh_main_list()
            self.set_status("Liste rafraîchie !", "green")
        tk.Button(guide_win, text="Terminé — Rafraîchir", font=("Arial", 12, "bold"),
            fg="white", bg="#2ecc71", relief="flat", padx=20, pady=8, command=on_done).pack(pady=15)
    def open_mods_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Gestionnaire de Mods")
        win.geometry("560x560")
        win.attributes("-topmost", True)
        ctk.CTkButton(win, text="Ajouter un mod (.jar)", command=self.import_mod).pack(pady=10)
        self.mod_list_frame = ctk.CTkScrollableFrame(win, height=460)
        self.mod_list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.refresh_mod_list()

    def import_mod(self):
        path = filedialog.askopenfilename(filetypes=[("Mod file", "*.jar")])
        if path:
            shutil.copy(path, os.path.join(self.mods_dir, os.path.basename(path)))
            self.refresh_mod_list()

    def refresh_mod_list(self):
        for w in self.mod_list_frame.winfo_children(): w.destroy()
        if not os.path.exists(self.mods_dir): return
        for f in os.listdir(self.mods_dir):
            if f.endswith((".jar", ".disabled")):
                fr = ctk.CTkFrame(self.mod_list_frame); fr.pack(fill="x", pady=2)
                cb = ctk.CTkCheckBox(fr, text=f[:35], command=lambda n=f: self.toggle_mod(n))
                cb.pack(side="left", padx=5)
                if f.endswith(".jar"): cb.select()
                ctk.CTkButton(fr, text="Supprimer", width=70, fg_color="#c0392b",
                    command=lambda n=f: self.delete_mod(n)).pack(side="right", padx=5)

    def toggle_mod(self, n):
        p = os.path.join(self.mods_dir, n)
        os.rename(p, p.replace(".jar", ".disabled") if n.endswith(".jar") else p.replace(".disabled", ".jar"))
        self.refresh_mod_list()

    def delete_mod(self, n):
        os.remove(os.path.join(self.mods_dir, n))
        self.refresh_mod_list()

    def start_launch_thread(self):
        self._save_auth()
        threading.Thread(target=self.launch_game, daemon=True).start()

    def launch_game(self):
        version = self.combo_profile.get()
        if version == "Aucune version": return
        self.btn_play.configure(state="disabled")
        self.progress_bar.set(0)
        try:
            self.set_status("Préparation…")
            installed_ids = [v["id"] for v in minecraft_launcher_lib.utils.get_installed_versions(self.base_dir)]
            if version not in installed_ids:
                messagebox.showerror("Erreur", f"Version '{version}' introuvable dans :\n{self.base_dir}")
                return

            options = {
                "username":      self._auth["username"],
                "uuid":          self._auth["uuid"] or str(uuid.uuid4()),
                "token":         self._auth["token"],
                "gameDirectory": self.base_dir,
                "jvmArguments":  [
                    f"-Xmx{self.settings.get('ram', '4G')}",
                    "-XX:+UnlockExperimentalVMOptions",
                    "-XX:+UseG1GC"
                ]
            }

            # Ely.by : injecter authlib-injector
            if self._auth["mode"] == "elyby" and os.path.exists(AUTHLIB_LOCAL):
                options["jvmArguments"].insert(0, f"-javaagent:{AUTHLIB_LOCAL}=ely.by")

            cmd = minecraft_launcher_lib.command.get_minecraft_command(version, self.base_dir, options)
            if not cmd:
                messagebox.showerror("Erreur", f"Impossible de générer la commande pour '{version}'.")
                return

            kwargs = {}
            if os.name == "nt": kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            self.set_status("Jeu lancé !", "green")
            subprocess.Popen(cmd, **kwargs).wait()

        except Exception as e:
            import traceback
            self.set_status("Erreur lancement", "red")
            messagebox.showerror("Erreur de lancement", f"{e}\n\n{traceback.format_exc()}")
        finally:
            self.btn_play.configure(state="normal")
            self.set_status("Prêt")


if __name__ == "__main__":
    app = WwheatyLauncher()
    app.mainloop()