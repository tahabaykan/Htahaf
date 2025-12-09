"""
Exception List Manager - Trade edilmemesi gereken hisseleri yönetir.
"""

import pandas as pd
import os
from tkinter import messagebox

class ExceptionListManager:
    def __init__(self, csv_file_path="exception_list.csv"):
        """
        Exception listesi yöneticisi.
        
        Args:
            csv_file_path: Exception listesinin kaydedileceği CSV dosya yolu
        """
        self.csv_file_path = csv_file_path
        self.exception_tickers = set()
        self.load_exception_list()
    
    def load_exception_list(self):
        """Exception listesini CSV dosyasından yükler."""
        try:
            if os.path.exists(self.csv_file_path):
                df = pd.read_csv(self.csv_file_path)
                if 'ticker' in df.columns:
                    self.exception_tickers = set(df['ticker'].dropna().astype(str).str.strip())
                else:
                    self.exception_tickers = set()
            else:
                # Dosya yoksa boş liste ile başla
                self.exception_tickers = set()
                self.save_exception_list()
        except Exception as e:
            print(f"Exception listesi yüklenirken hata: {e}")
            self.exception_tickers = set()
    
    def save_exception_list(self):
        """Exception listesini CSV dosyasına kaydeder."""
        try:
            df = pd.DataFrame({'ticker': list(self.exception_tickers)})
            df.to_csv(self.csv_file_path, index=False)
        except Exception as e:
            print(f"Exception listesi kaydedilirken hata: {e}")
            messagebox.showerror("Hata", f"Exception listesi kaydedilemedi: {e}")
    
    def add_ticker(self, ticker):
        """Exception listesine yeni ticker ekler."""
        ticker = str(ticker).strip().upper()
        if ticker:
            self.exception_tickers.add(ticker)
            self.save_exception_list()
            return True
        return False
    
    def remove_ticker(self, ticker):
        """Exception listesinden ticker çıkarır."""
        ticker = str(ticker).strip().upper()
        if ticker in self.exception_tickers:
            self.exception_tickers.remove(ticker)
            self.save_exception_list()
            return True
        return False
    
    def is_exception_ticker(self, ticker):
        """Ticker'ın exception listesinde olup olmadığını kontrol eder."""
        ticker = str(ticker).strip().upper()
        return ticker in self.exception_tickers
    
    def get_exception_list(self):
        """Exception listesini döndürür."""
        return sorted(list(self.exception_tickers))
    
    def clear_exception_list(self):
        """Exception listesini temizler."""
        self.exception_tickers.clear()
        self.save_exception_list()
    
    def filter_exception_tickers(self, ticker_list):
        """
        Verilen ticker listesinden exception olanları filtreler.
        
        Args:
            ticker_list: Kontrol edilecek ticker listesi
            
        Returns:
            tuple: (allowed_tickers, exception_tickers)
        """
        allowed_tickers = []
        exception_tickers = []
        
        for ticker in ticker_list:
            ticker_str = str(ticker).strip().upper()
            if self.is_exception_ticker(ticker_str):
                exception_tickers.append(ticker_str)
            else:
                allowed_tickers.append(ticker_str)
        
        return allowed_tickers, exception_tickers
