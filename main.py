# main.py
# -*- coding: utf-8 -*-
import customtkinter as ctk
from ui import NovelGeneratorGUI

# 设置默认外观模式和颜色主题
ctk.set_appearance_mode("System")  # 可选: "System", "Light", "Dark"
ctk.set_default_color_theme("blue")  # 可选: "blue", "green", "dark-blue"

def main():
    app = ctk.CTk()
    gui = NovelGeneratorGUI(app)
    app.mainloop()

if __name__ == "__main__":
    main()
