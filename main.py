# main.py
# -*- coding: utf-8 -*-
import customtkinter as ctk
from ui import NovelGeneratorGUI

def main():
    app = ctk.CTk()
    gui = NovelGeneratorGUI(app)
    app.mainloop()

if __name__ == "__main__":
    main()
