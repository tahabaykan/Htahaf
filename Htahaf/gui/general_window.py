import tkinter as tk
from tkinter import ttk
import tkinter.font as tkFont

class GeneralWindow(tk.Toplevel):
    def __init__(self, parent, title, columns, long_header, short_header):
        super().__init__(parent)
        self.title(title)
        font_bold = tkFont.Font(family="Arial", size=8, weight="bold")
        font_normal = tkFont.Font(family="Arial", size=8)
        style = ttk.Style()
        style.configure("Treeview.Heading", font=("Arial", 8))
        self.table = ttk.Treeview(self, columns=columns, show='headings', height=20)
        for i, col in enumerate(columns):
            if col in [
                'Bid buy Ucuzluk Skoru', 'Front buy ucuzluk skoru', 'Ask buy ucuzluk skoru',
                'Ask sell pahalilik skoru', 'Front sell pahalilik skoru', 'Bid sell pahalilik skoru']:
                self.table.heading(col, text=col)
                self.table.column(col, width=110, anchor='center')
            else:
                self.table.heading(col, text=col)
                self.table.column(col, width=80, anchor='center')
        self.table.tag_configure('bold', font=font_bold)
        self.table.tag_configure('normal', font=font_normal)
        self.table.pack(fill='both', expand=True)
        # Long/Short açıklama satırları
        self.table.insert('', 'end', iid='desc_long', values=(['']*2 + [long_header] + ['']*(len(columns)-3)), tags=('bold',))
        self.table.insert('', 'end', iid='desc_short', values=(['']*11 + [short_header] + ['']*(len(columns)-12)), tags=('bold',)) 
