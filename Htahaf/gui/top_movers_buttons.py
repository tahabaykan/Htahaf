import tkinter as tk
from tkinter import ttk

def create_top_movers_buttons(parent, main_window):
    btn_t_down = ttk.Button(parent, text='T-çok düşenler', command=main_window.open_t_top_losers_window)
    btn_t_up = ttk.Button(parent, text='T-çok yükselenler', command=main_window.open_t_top_gainers_window)
    
    # C-prefs için yeni butonlar
    btn_maturex_down = ttk.Button(parent, text='Maturex-çok düşenler', command=main_window.open_maturex_top_losers_window)
    btn_maturex_up = ttk.Button(parent, text='Maturex-çok yükselenler', command=main_window.open_maturex_top_gainers_window)
    
    btn_nffex_down = ttk.Button(parent, text='NFFex-çok düşenler', command=main_window.open_nffex_top_losers_window)
    btn_nffex_up = ttk.Button(parent, text='NFFex-çok yükselenler', command=main_window.open_nffex_top_gainers_window)
    
    btn_ffex_down = ttk.Button(parent, text='FFex-çok düşenler', command=main_window.open_ffex_top_losers_window)
    btn_ffex_up = ttk.Button(parent, text='FFex-çok yükselenler', command=main_window.open_ffex_top_gainers_window)
    
    btn_flrex_down = ttk.Button(parent, text='FLRex-çok düşenler', command=main_window.open_flrex_top_losers_window)
    btn_flrex_up = ttk.Button(parent, text='FLRex-çok yükselenler', command=main_window.open_flrex_top_gainers_window)
    
    btn_duzex_down = ttk.Button(parent, text='Duzex-çok düşenler', command=main_window.open_duzex_top_losers_window)
    btn_duzex_up = ttk.Button(parent, text='Duzex-çok yükselenler', command=main_window.open_duzex_top_gainers_window)
    
    # Butonları yerleştir
    btn_t_down.pack(side='left', padx=2)
    btn_t_up.pack(side='left', padx=2)
    
    btn_maturex_down.pack(side='left', padx=2)
    btn_maturex_up.pack(side='left', padx=2)
    
    btn_nffex_down.pack(side='left', padx=2)
    btn_nffex_up.pack(side='left', padx=2)
    
    btn_ffex_down.pack(side='left', padx=2)
    btn_ffex_up.pack(side='left', padx=2)
    
    btn_flrex_down.pack(side='left', padx=2)
    btn_flrex_up.pack(side='left', padx=2)
    
    btn_duzex_down.pack(side='left', padx=2)
    btn_duzex_up.pack(side='left', padx=2)
    
    return (btn_t_down, btn_t_up,
            btn_maturex_down, btn_maturex_up,
            btn_nffex_down, btn_nffex_up,
            btn_ffex_down, btn_ffex_up,
            btn_flrex_down, btn_flrex_up,
            btn_duzex_down, btn_duzex_up) 
