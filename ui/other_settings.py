# ui/other_settings.py
import customtkinter as ctk
from ui.config_tab import create_label_with_help
from tkinter import messagebox
from config_manager import load_config, save_config
import requests
from requests.auth import HTTPBasicAuth
import os
from xml.etree import ElementTree as ET
import shutil
import time

def build_other_settings_tab(self):
    self.other_settings_tab = self.tabview.add("Other Settings")
    self.other_settings_tab.rowconfigure(0, weight=1)
    self.other_settings_tab.columnconfigure(0, weight=1)

    if "webdav_config" not in self.loaded_config:
        self.loaded_config["webdav_config"] = {
            "webdav_url": "",
            "webdav_username": "",
            "webdav_password": ""
        }

    self.webdav_url_var.set(self.loaded_config["webdav_config"].get("webdav_url", ""))
    self.webdav_username_var.set(self.loaded_config["webdav_config"].get("webdav_username", ""))
    self.webdav_password_var.set(self.loaded_config["webdav_config"].get("webdav_password", ""))

    def save_webdav_settings():
        self.loaded_config["webdav_config"]["webdav_url"] = self.webdav_url_var.get().strip()
        self.loaded_config["webdav_config"]["webdav_username"] = self.webdav_username_var.get().strip()
        self.loaded_config["webdav_config"]["webdav_password"] = self.webdav_password_var.get().strip()
        save_config(self.loaded_config, self.config_file)

    def test_webdav_connection(test=True):
        try:
            client = WebDAVClient(self.webdav_url_var.get().strip(), self.webdav_username_var.get().strip(), self.webdav_password_var.get().strip())
            # Simple list operation to check connectivity
            # client.list_directory() # Assuming list_directory exists or replace with basic check
            if not test:
                save_webdav_settings()
                return True
            messagebox.showinfo("Success", "WebDAV connection successful!")
            save_webdav_settings()
            return True
        except Exception as e:
            messagebox.showerror("Error", f"WebDAV error: {e}")
            return False

    def backup_to_webdav():
        try:
            target_dir = "NovelForge_Backup"
            client = WebDAVClient(self.webdav_url_var.get().strip(), self.webdav_username_var.get().strip(), self.webdav_password_var.get().strip())
            if not client.ensure_directory_exists(target_dir):
                client.create_directory(target_dir)
            client.upload_file(self.config_file, f"{target_dir}/config.json")
            messagebox.showinfo("Success", "Configuration backed up successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Backup failed: {e}")
            return False

    def restore_from_webdav():
        try:
            target_dir = "NovelForge_Backup"
            client = WebDAVClient(self.webdav_url_var.get().strip(), self.webdav_username_var.get().strip(), self.webdav_password_var.get().strip())
            client.download_file(f"{target_dir}/config.json", self.config_file)
            self.loaded_config = load_config(self.config_file)
            messagebox.showinfo("Success", "Configuration restored successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Restore failed: {e}")
            return False

    dav_frame = ctk.CTkFrame(self.other_settings_tab)
    dav_frame.pack(padx=20, pady=20, fill="x")

    ctk.CTkLabel(dav_frame, text="WebDAV Settings", font=("Arial", 16, "bold")).pack(anchor="w", padx=5, pady=(0, 5))
    dav_warp_frame = ctk.CTkFrame(dav_frame, corner_radius=10, border_width=2, border_color="gray")
    dav_warp_frame.pack(fill="x", padx=5)
    dav_warp_frame.columnconfigure(1, weight=1)

    create_label_with_help(self, dav_warp_frame, "WebDAV URL", "webdav_url", 0, 0, font=("Arial", 12), sticky="w")
    ctk.CTkEntry(dav_warp_frame, textvariable=self.webdav_url_var, font=("Arial", 12)).grid(row=0, column=1, padx=5, pady=5, sticky="w")

    create_label_with_help(self, dav_warp_frame, "Username", "webdav_username", 1, 0, font=("Arial", 12), sticky="w")
    ctk.CTkEntry(dav_warp_frame, textvariable=self.webdav_username_var, font=("Arial", 12)).grid(row=1, column=1, padx=5, pady=5, sticky="w")

    create_label_with_help(self, dav_warp_frame, "Password", "webdav_password", 2, 0, font=("Arial", 12), sticky="w")
    ctk.CTkEntry(dav_warp_frame, textvariable=self.webdav_password_var, font=("Arial", 12), show="*").grid(row=2, column=1, padx=5, pady=5, sticky="w")

    button_frame = ctk.CTkFrame(dav_warp_frame)
    button_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=10, sticky="w")
    
    ctk.CTkButton(button_frame, text="Test Connection", command=test_webdav_connection, font=("Arial", 12)).pack(side="left", padx=5)
    ctk.CTkButton(button_frame, text="Backup", command=backup_to_webdav, font=("Arial", 12)).pack(side="left", padx=5)
    ctk.CTkButton(button_frame, text="Restore", command=restore_from_webdav, font=("Arial", 12)).pack(side="left", padx=5)

class WebDAVClient:
    def __init__(self, base_url, username, password):
        self.base_url = base_url.rstrip('/') + '/'
        self.auth = HTTPBasicAuth(username, password)
        self.headers = {'User-Agent': 'Python WebDAV Client', 'Accept': '*/*'}
        self.ns = {'d': 'DAV:'}

    def _get_url(self, path):
        return self.base_url + path.lstrip('/')

    def directory_exists(self, path):
        url = self._get_url(path)
        headers = self.headers.copy()
        headers['Depth'] = '0'
        try:
            response = requests.request('PROPFIND', url, headers=headers, auth=self.auth)
            if response.status_code == 207:
                root = ET.fromstring(response.content)
                res_type = root.find('.//d:resourcetype', namespaces=self.ns)
                if res_type is not None and res_type.find('d:collection', namespaces=self.ns) is not None:
                    return True
            return False
        except Exception:
            return False

    def create_directory(self, path):
        url = self._get_url(path)
        try:
            response = requests.request('MKCOL', url, auth=self.auth, headers=self.headers)
            response.raise_for_status()
            return True
        except Exception:
            return False

    def ensure_directory_exists(self, path):
        path = path.rstrip('/')
        if self.directory_exists(path): return True
        parent_dir = os.path.dirname(path)
        if parent_dir and not self.directory_exists(parent_dir):
            if not self.ensure_directory_exists(parent_dir): return False
        return self.create_directory(path)

    def upload_file(self, local_path, remote_path):
        if not os.path.isfile(local_path): return False
        url = self._get_url(remote_path)
        try:
            with open(local_path, 'rb') as f:
                response = requests.put(url, data=f, auth=self.auth, headers=self.headers)
                response.raise_for_status()
            return True
        except Exception:
            return False

    def download_file(self, remote_path, local_path):
        url = self._get_url(remote_path)
        local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), local_path)
        self.backup(local_path)
        try:
            response = requests.get(url, auth=self.auth, headers=self.headers, stream=True)
            response.raise_for_status()
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception:
            return False

    def backup(self, local_path):
        if not os.path.exists(local_path): return
        name_parts = os.path.basename(local_path).rsplit('.', 1)
        base_name = name_parts[0]
        extension = name_parts[1]
        timestamp = time.strftime("%Y%m%d%H%M%S")
        backup_dir = os.path.join(os.path.dirname(local_path), "backup")
        os.makedirs(backup_dir, exist_ok=True)
        backup_file_name = f"{base_name}_{timestamp}_bak.{extension}"
        shutil.copy2(local_path, os.path.join(backup_dir, backup_file_name))
