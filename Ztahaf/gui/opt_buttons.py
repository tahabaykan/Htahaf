import tkinter as tk
from tkinter import ttk

def create_opt_buttons(parent, main_window):
    btn_opt50 = ttk.Button(parent, text='Opt50', command=main_window.open_opt50_window)
    btn_maturex = ttk.Button(parent, text='Maturex', command=main_window.open_maturex_window)
    btn_nffex = ttk.Button(parent, text='NFFex', command=main_window.open_nffex_window)
    btn_ffex = ttk.Button(parent, text='FFex', command=main_window.open_ffex_window)
    btn_flrex = ttk.Button(parent, text='FLRex', command=main_window.open_flrex_window)
    btn_duzex = ttk.Button(parent, text='Duzex', command=main_window.open_duzex_window)
    
    btn_opt50.pack(side='left', padx=2)
    btn_maturex.pack(side='left', padx=2)
    btn_nffex.pack(side='left', padx=2)
    btn_ffex.pack(side='left', padx=2)
    btn_flrex.pack(side='left', padx=2)
    btn_duzex.pack(side='left', padx=2)
    
    btn_opt50_maltopla = ttk.Button(parent, text='Opt50 maltopla', command=main_window.open_opt50_maltopla_window)
    btn_maturex_maltopla = ttk.Button(parent, text='Maturex maltopla', command=main_window.open_maturex_maltopla_window)
    btn_nffex_maltopla = ttk.Button(parent, text='NFFex maltopla', command=main_window.open_nffex_maltopla_window)
    btn_ffex_maltopla = ttk.Button(parent, text='FFex maltopla', command=main_window.open_ffex_maltopla_window)
    btn_flrex_maltopla = ttk.Button(parent, text='FLRex maltopla', command=main_window.open_flrex_maltopla_window)
    btn_duzex_maltopla = ttk.Button(parent, text='Duzex maltopla', command=main_window.open_duzex_maltopla_window)
    
    btn_opt50_maltopla.pack(side='left', padx=2)
    btn_maturex_maltopla.pack(side='left', padx=2)
    btn_nffex_maltopla.pack(side='left', padx=2)
    btn_ffex_maltopla.pack(side='left', padx=2)
    btn_flrex_maltopla.pack(side='left', padx=2)
    btn_duzex_maltopla.pack(side='left', padx=2)
    
    return (btn_opt50, btn_maturex, btn_nffex, btn_ffex, btn_flrex, btn_duzex,
            btn_opt50_maltopla, btn_maturex_maltopla, btn_nffex_maltopla, 
            btn_ffex_maltopla, btn_flrex_maltopla, btn_duzex_maltopla) 
