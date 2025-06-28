#!/usr/bin/env python
"""
UI components and display functions for StockTracker
"""
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import datetime
import time
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

def create_status_bar(parent):
    """Create status bar at the bottom of the application"""
    status_frame = ttk.Frame(parent)
    status_frame.pack(side=tk.BOTTOM, fill=tk.X)
    
    status_label = ttk.Label(status_frame, text="Hazır", anchor=tk.W, padding=(5, 2))
    status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    connection_indicator = ttk.Label(
        status_frame, text="✘ Bağlantı Yok", foreground="red", padding=(5, 2))
    connection_indicator.pack(side=tk.RIGHT)
    
    # Store both labels in the frame for easy access
    status_frame.status_label = status_label
    status_frame.connection_indicator = connection_indicator
    
    return status_frame

def update_status_bar(status_bar, status_text, is_connected=False):
    """Update the status bar with new text and connection status"""
    status_bar.status_label.config(text=status_text)
    
    if is_connected:
        status_bar.connection_indicator.config(
            text="✓ Bağlı", foreground="green")
    else:
        status_bar.connection_indicator.config(
            text="✘ Bağlantı Yok", foreground="red")

def create_tab_control(parent, tab_names):
    """Create a tabbed interface with the given tab names"""
    tab_control = ttk.Notebook(parent)
    tab_control.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
    
    tabs = {}
    
    for i, tab_name in enumerate(tab_names):
        tab = ttk.Frame(tab_control)
        tab_control.add(tab, text=tab_name)
        tabs[i] = tab
    
    return tab_control, tabs

def create_control_frame(parent):
    """Create the top control frame with buttons"""
    control_frame = ttk.Frame(parent)
    control_frame.pack(fill=tk.X, pady=(0, 10))
    
    return control_frame

def create_filter_frame(parent, filter_var, apply_callback, clear_callback):
    """Create the filter input and buttons"""
    filter_frame = ttk.Frame(parent)
    filter_frame.pack(side=tk.LEFT, padx=5)
    
    ttk.Label(filter_frame, text="Filtre:").pack(side=tk.LEFT)
    
    filter_entry = ttk.Entry(filter_frame, textvariable=filter_var, width=15)
    filter_entry.pack(side=tk.LEFT, padx=5)
    
    apply_button = ttk.Button(filter_frame, text="Uygula", command=apply_callback)
    apply_button.pack(side=tk.LEFT)
    
    clear_button = ttk.Button(filter_frame, text="Temizle", command=clear_callback)
    clear_button.pack(side=tk.LEFT, padx=5)
    
    return filter_frame

def create_page_navigation_frame(parent, prev_callback, next_callback, jump_callback):
    """Create page navigation controls frame"""
    page_frame = ttk.Frame(parent)
    page_frame.pack(fill=tk.X, pady=(0, 5))
    
    # Previous page button
    prev_btn = ttk.Button(page_frame, text="Önceki Sayfa", command=prev_callback)
    prev_btn.pack(side=tk.LEFT, padx=5)
    
    # Next page button
    next_btn = ttk.Button(page_frame, text="Sonraki Sayfa", command=next_callback)
    next_btn.pack(side=tk.LEFT, padx=5)
    
    # Page info label
    page_info = ttk.Label(page_frame, text="Sayfa: 1/1")
    page_info.pack(side=tk.LEFT, padx=20)
    
    # Jump to page
    ttk.Label(page_frame, text="Sayfaya Git:").pack(side=tk.LEFT, padx=5)
    
    jump_to_page_var = tk.StringVar()
    jump_entry = ttk.Entry(page_frame, textvariable=jump_to_page_var, width=5)
    jump_entry.pack(side=tk.LEFT, padx=5)
    
    jump_btn = ttk.Button(page_frame, text="Git", command=jump_callback)
    jump_btn.pack(side=tk.LEFT, padx=5)
    
    return page_frame, page_info, jump_to_page_var

def update_page_info(page_info_label, current_page, total_pages):
    """Update the page information label"""
    page_info_label.config(text=f"Sayfa: {current_page}/{total_pages}")

def create_benchmark_frame(parent):
    """Create frame for benchmark data display"""
    benchmark_frame = ttk.Frame(parent)
    benchmark_frame.pack(fill=tk.X, pady=5, side=tk.BOTTOM)
    
    # PFF label
    pff_label = ttk.Label(benchmark_frame, text="PFF: $0.00 (0.00%)")
    pff_label.pack(side=tk.LEFT, padx=10)
    
    # TLT label
    tlt_label = ttk.Label(benchmark_frame, text="TLT: $0.00 (0.00%)")
    tlt_label.pack(side=tk.LEFT, padx=10)
    
    # Benchmark label
    benchmark_label = ttk.Label(benchmark_frame, text="Benchmark: 0.00%")
    benchmark_label.pack(side=tk.LEFT, padx=10)
    
    # Time label
    time_label = ttk.Label(benchmark_frame, text="Son Güncelleme: --:--:--")
    time_label.pack(side=tk.RIGHT, padx=10)
    
    return benchmark_frame, pff_label, tlt_label, benchmark_label, time_label

def update_benchmark_labels(pff_label, tlt_label, benchmark_label, time_label,
                           pff_price, pff_change, tlt_price, tlt_change, benchmark_change):
    """Update benchmark labels with current data"""
    # Format values
    pff_color = "green" if pff_change > 0 else "red" if pff_change < 0 else "black"
    tlt_color = "green" if tlt_change > 0 else "red" if tlt_change < 0 else "black"
    benchmark_color = "green" if benchmark_change > 0 else "red" if benchmark_change < 0 else "black"
    
    # Update labels
    pff_label.config(
        text=f"PFF: ${pff_price:.2f} ({pff_change:+.2f}%)",
        foreground=pff_color
    )
    
    tlt_label.config(
        text=f"TLT: ${tlt_price:.2f} ({tlt_change:+.2f}%)",
        foreground=tlt_color
    )
    
    benchmark_label.config(
        text=f"Benchmark: {benchmark_change:+.2f} cent",
        foreground=benchmark_color
    )
    
    # Update time
    now_time = datetime.datetime.now().strftime("%H:%M:%S")
    time_label.config(text=f"Son Güncelleme: {now_time}")

def create_simple_popup(title, message, parent=None):
    """Create a simple information popup"""
    messagebox.showinfo(title, message, parent=parent)

def create_error_popup(title, message, parent=None):
    """Create an error popup"""
    messagebox.showerror(title, message, parent=parent)

def create_question_popup(title, message, parent=None):
    """Create a yes/no question popup, returns True if Yes is selected"""
    return messagebox.askyesno(title, message, parent=parent)

def create_simple_chart(df, x_column, y_column, title, xlabel, ylabel, figsize=(10, 6)):
    """
    Basit bir grafik oluştur
    
    Args:
        df (DataFrame): Veri çerçevesi
        x_column (str): X ekseni sütun adı
        y_column (str): Y ekseni sütun adı
        title (str): Grafik başlığı
        xlabel (str): X ekseni etiketi
        ylabel (str): Y ekseni etiketi
        figsize (tuple): Grafik boyutu
        
    Returns:
        Figure: Oluşturulan matplotlib figürü
    """
    fig = Figure(figsize=figsize)
    ax = fig.add_subplot(111)
    
    ax.plot(df[x_column], df[y_column])
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    
    fig.tight_layout()
    return fig

def embed_chart_in_frame(frame, fig):
    """
    Grafiği bir çerçeveye yerleştir
    
    Args:
        frame: Hedef çerçeve
        fig: Matplotlib figürü
        
    Returns:
        FigureCanvasTkAgg: Oluşturulan canvas nesnesi
    """
    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.draw()
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    return canvas 