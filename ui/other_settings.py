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


    def test_webdav_connection(test = True):
        try:
            client = WebDAVClient(self.webdav_url_var.get().strip(),self.webdav_username_var.get().strip(),self.webdav_password_var.get().strip())
            client.list_directory()
            if not test:
                save_webdav_settings()
                return True
            messagebox.showinfo("成功", "WebDAV 连接成功！")
            save_webdav_settings()
            return True

        except Exception as e:
            print(e)

            messagebox.showerror("错误", f"发生未知错误: {e}")
            return False

    def backup_to_webdav():
        try:
            target_dir = "AI_Novel_Generator"
            client = WebDAVClient(self.webdav_url_var.get().strip(),self.webdav_username_var.get().strip(),self.webdav_password_var.get().strip())
            if not client.ensure_directory_exists(target_dir):
                client.create_directory(target_dir)
            client.upload_file(self.config_file, f"{target_dir}/config.json")
            messagebox.showinfo("成功", "配置备份成功！")
        except Exception as e:
            print(e)
            messagebox.showerror("错误", f"发生未知错误: {e}")
            return False







    def restore_from_webdav():
        try:
            target_dir = "AI_Novel_Generator"
            client = WebDAVClient(self.webdav_url_var.get().strip(),self.webdav_username_var.get().strip(),self.webdav_password_var.get().strip())
            client.download_file(f"{target_dir}/config.json", self.config_file)
            self.loaded_config = load_config(self.config_file)
            messagebox.showinfo("成功", "配置恢复成功！")

        except Exception as e:
            print(e)
            messagebox.showerror("错误", f"发生未知错误: {e}")
            return False




    dav_frame = ctk.CTkFrame(self.other_settings_tab)
    dav_frame.pack(padx=20, pady=20, fill="x")

    dav_title = ctk.CTkLabel(dav_frame, text="webdav设置", font=("Microsoft YaHei", 16, "bold"))
    dav_title.pack(anchor="w", padx=5, pady=(0, 5))
    dav_warp_frame = ctk.CTkFrame(dav_frame, corner_radius=10, border_width=2, border_color="gray")
    dav_warp_frame.pack(fill="x", padx=5)
    dav_warp_frame.columnconfigure(1, weight=1)

    

    create_label_with_help(self, parent=dav_warp_frame, label_text="Webdav URL", tooltip_key="webdav_url",row=0, column=0, font=("Microsoft YaHei", 12), sticky="w")
    dav_url_entry = ctk.CTkEntry(dav_warp_frame, textvariable=self.webdav_url_var, font=("Microsoft YaHei", 12))
    dav_url_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

    create_label_with_help(self, parent=dav_warp_frame, label_text="Webdav用户名", tooltip_key="webdav_username",row=1, column=0, font=("Microsoft YaHei", 12), sticky="w")
    dav_username_entry = ctk.CTkEntry(dav_warp_frame, textvariable=self.webdav_username_var, font=("Microsoft YaHei", 12))
    dav_username_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

    create_label_with_help(self, parent=dav_warp_frame, label_text="Webdav密码", tooltip_key="webdav_password",row=2, column=0, font=("Microsoft YaHei", 12), sticky="w")
    dav_password_entry = ctk.CTkEntry(dav_warp_frame, textvariable=self.webdav_password_var, font=("Microsoft YaHei", 12), show="*")
    dav_password_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

    button_frame = ctk.CTkFrame(dav_warp_frame)
    button_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=10, sticky="w")
    
    # 测试连接按钮
    test_btn = ctk.CTkButton(button_frame, text="测试连接", font=("Microsoft YaHei", 12),
                            command=test_webdav_connection)
    test_btn.pack(side="left", padx=5)
    
    # 保存设置按钮
    save_btn = ctk.CTkButton(button_frame, text="备份", font=("Microsoft YaHei", 12),
                            command=backup_to_webdav)
    save_btn.pack(side="left", padx=5)
    
    # 重置按钮
    reset_btn = ctk.CTkButton(button_frame, text="恢复", font=("Microsoft YaHei", 12),
                             command=restore_from_webdav)
    reset_btn.pack(side="left", padx=5)







class WebDAVClient:
    def __init__(self, base_url, username, password):
        """初始化WebDAV客户端"""
        self.base_url = base_url.rstrip('/') + '/'
        self.auth = HTTPBasicAuth(username, password)
        self.headers = {
            'User-Agent': 'Python WebDAV Client',
            'Accept': '*/*'
        }
        # WebDAV命名空间
        self.ns = {'d': 'DAV:'}

    def _get_url(self, path):
        """获取完整的资源URL"""
        return self.base_url + path.lstrip('/')

    def directory_exists(self, path):
        """
        检查目录是否存在
        :param path: 目录路径
        :return: 布尔值，表示目录是否存在
        """
        url = self._get_url(path)
        headers = self.headers.copy()
        headers['Depth'] = '0'  # 只检查当前资源
        
        try:
            # 发送PROPFIND请求检查资源是否存在
            response = requests.request('PROPFIND', url, headers=headers, auth=self.auth)
            
            # 207 Multi-Status表示成功，说明资源存在
            if response.status_code == 207:
                # 解析XML响应，确认是目录
                root = ET.fromstring(response.content)
                # 查找资源类型属性
                res_type = root.find('.//d:resourcetype', namespaces=self.ns)
                # 如果包含collection元素，则是目录
                if res_type is not None and res_type.find('d:collection', namespaces=self.ns) is not None:
                    return True
            return False
        except requests.exceptions.RequestException as e:
            print(f"检查目录存在性时出错: {e}")
            return False

    def create_directory(self, path):
        """
        创建远程目录
        :param path: 要创建的目录路径
        :return: 是否创建成功
        """
        url = self._get_url(path)
        
        try:
            response = requests.request('MKCOL', url, auth=self.auth, headers=self.headers)
            response.raise_for_status()
            
            print(f"目录创建成功: {path}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"目录创建失败: {e}")
            return False

    def ensure_directory_exists(self, path):
        """
        确保目录存在，如果不存在则创建
        :param path: 目录路径
        :return: 布尔值，表示最终目录是否存在
        """
        # 移除末尾的斜杠（如果有）
        path = path.rstrip('/')
        
        # 如果目录已经存在，直接返回True
        if self.directory_exists(path):
            print(f"目录已存在: {path}")
            return True
            
        # 递归创建父目录
        parent_dir = os.path.dirname(path)
        if parent_dir and not self.directory_exists(parent_dir):
            # 如果父目录不存在，则先创建父目录
            if not self.ensure_directory_exists(parent_dir):
                print(f"创建父目录失败: {parent_dir}")
                return False
                
        # 创建当前目录
        return self.create_directory(path)
    def upload_file(self, local_path, remote_path):
        """
        上传文件到WebDAV服务器
        :param local_path: 本地文件路径
        :param remote_path: 远程文件路径
        :return: 是否上传成功
        """
        if not os.path.isfile(local_path):
            print(f"本地文件不存在: {local_path}")
            return False

        url = self._get_url(remote_path)
        
        try:
            with open(local_path, 'rb') as f:
                response = requests.put(url, data=f, auth=self.auth, headers=self.headers)
                response.raise_for_status()
            
            print(f"文件上传成功: {local_path} -> {remote_path}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"文件上传失败: {e}")
            return False
    def download_file(self, remote_path, local_path):
        """
        从WebDAV服务器下载文件
        :param remote_path: 远程文件路径
        :param local_path: 本地保存路径
        :return: 是否下载成功
        """
        url = self._get_url(remote_path)
        local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), local_path)
        self.backup(local_path)
        try:
            response = requests.get(url, auth=self.auth, headers=self.headers, stream=True)
            response.raise_for_status()
            
            # 创建本地目录（如果需要）
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"文件下载成功: {remote_path} -> {local_path}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"文件下载失败: {e}")
            return False
    def backup(self, local_path):
        name_parts = os.path.basename(local_path).rsplit('.', 1)  # 只分割最后一个点
        base_name = name_parts[0]
        extension = name_parts[1]
        timestamp = time.strftime("%Y%m%d%H%M%S")
        if not os.path.exists(os.path.join(os.path.dirname(local_path), "backup")):
            os.makedirs(os.path.join(os.path.dirname(local_path), "backup"))
        backup_file_name = f"{base_name}_{timestamp}_bak.{extension}"
        shutil.copy2(local_path, os.path.join(os.path.dirname(local_path), "backup", backup_file_name))
