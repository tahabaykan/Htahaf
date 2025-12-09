"""
Modern UI Theme Configuration

Provides consistent styling, colors, and layout for the modernized Tkinter interface.
"""

import tkinter as tk
from tkinter import ttk


class ModernTheme:
    """
    Modern theme configuration for JanAllModern application.
    
    Provides consistent colors, fonts, padding, and styling throughout the UI.
    """
    
    # Color Palette - Modern, Professional
    COLORS = {
        # Primary Colors
        'primary': '#2563eb',      # Blue
        'primary_dark': '#1e40af',  # Dark Blue
        'primary_light': '#3b82f6', # Light Blue
        
        # Secondary Colors
        'secondary': '#64748b',     # Slate
        'secondary_dark': '#475569',
        'secondary_light': '#94a3b8',
        
        # Accent Colors
        'accent': '#10b981',       # Green
        'accent_dark': '#059669',
        'accent_light': '#34d399',
        
        # Warning/Error Colors
        'warning': '#f59e0b',       # Amber
        'error': '#ef4444',         # Red
        'success': '#10b981',       # Green
        
        # Background Colors
        'bg_primary': '#ffffff',    # White
        'bg_secondary': '#f8fafc', # Light Gray
        'bg_tertiary': '#f1f5f9',  # Lighter Gray
        
        # Text Colors
        'text_primary': '#1e293b',  # Dark Gray
        'text_secondary': '#64748b', # Medium Gray
        'text_light': '#94a3b8',    # Light Gray
        
        # Border Colors
        'border': '#e2e8f0',        # Light Border
        'border_dark': '#cbd5e1',    # Dark Border
        
        # Table Colors
        'table_header': '#f1f5f9',
        'table_row_even': '#ffffff',
        'table_row_odd': '#f8fafc',
        'table_selected': '#dbeafe', # Light Blue
    }
    
    # Font Configuration
    FONTS = {
        'default': ('Segoe UI', 9),
        'small': ('Segoe UI', 8),
        'medium': ('Segoe UI', 10),
        'large': ('Segoe UI', 12),
        'bold': ('Segoe UI', 9, 'bold'),
        'title': ('Segoe UI', 14, 'bold'),
        'heading': ('Segoe UI', 11, 'bold'),
    }
    
    # Spacing Configuration
    SPACING = {
        'xs': 2,
        'sm': 4,
        'md': 8,
        'lg': 12,
        'xl': 16,
        'xxl': 24,
    }
    
    # Button Configuration
    BUTTON = {
        'width_small': 8,
        'width_medium': 12,
        'width_large': 16,
        'height': 28,
        'padding_x': 12,
        'padding_y': 6,
    }
    
    @staticmethod
    def configure_styles():
        """
        Configure ttk.Style with modern theme.
        
        This should be called once at application startup.
        """
        style = ttk.Style()
        
        # Use modern theme if available
        try:
            style.theme_use('clam')
        except:
            pass
        
        # Configure Button style
        style.configure(
            'Modern.TButton',
            font=ModernTheme.FONTS['default'],
            padding=(ModernTheme.BUTTON['padding_x'], ModernTheme.BUTTON['padding_y']),
            borderwidth=1,
            relief='flat',
        )
        
        style.map(
            'Modern.TButton',
            background=[('active', ModernTheme.COLORS['primary_light']),
                       ('!active', ModernTheme.COLORS['primary'])],
            foreground=[('active', 'white'), ('!active', 'white')],
        )
        
        # Configure Accent Button style
        style.configure(
            'Accent.TButton',
            font=ModernTheme.FONTS['default'],
            padding=(ModernTheme.BUTTON['padding_x'], ModernTheme.BUTTON['padding_y']),
            borderwidth=1,
            relief='flat',
        )
        
        style.map(
            'Accent.TButton',
            background=[('active', ModernTheme.COLORS['accent_light']),
                       ('!active', ModernTheme.COLORS['accent'])],
            foreground=[('active', 'white'), ('!active', 'white')],
        )
        
        # Configure Treeview (Table) style
        style.configure(
            'Modern.Treeview',
            font=ModernTheme.FONTS['small'],
            background=ModernTheme.COLORS['bg_primary'],
            foreground=ModernTheme.COLORS['text_primary'],
            fieldbackground=ModernTheme.COLORS['bg_primary'],
            borderwidth=1,
            relief='flat',
        )
        
        style.configure(
            'Modern.Treeview.Heading',
            font=ModernTheme.FONTS['bold'],
            background=ModernTheme.COLORS['table_header'],
            foreground=ModernTheme.COLORS['text_primary'],
            borderwidth=1,
            relief='flat',
        )
        
        style.map(
            'Modern.Treeview',
            background=[('selected', ModernTheme.COLORS['table_selected'])],
            foreground=[('selected', ModernTheme.COLORS['text_primary'])],
        )
        
        # Configure Frame style
        style.configure(
            'Modern.TFrame',
            background=ModernTheme.COLORS['bg_primary'],
            borderwidth=0,
        )
        
        # Configure Label style
        style.configure(
            'Modern.TLabel',
            font=ModernTheme.FONTS['default'],
            background=ModernTheme.COLORS['bg_primary'],
            foreground=ModernTheme.COLORS['text_primary'],
        )
        
        style.configure(
            'Heading.TLabel',
            font=ModernTheme.FONTS['heading'],
            background=ModernTheme.COLORS['bg_primary'],
            foreground=ModernTheme.COLORS['text_primary'],
        )
        
        # Configure Entry style
        style.configure(
            'Modern.TEntry',
            font=ModernTheme.FONTS['default'],
            borderwidth=1,
            relief='solid',
            padding=4,
        )
        
        return style
    
    @staticmethod
    def create_button(parent, text, command=None, style='Modern.TButton', **kwargs):
        """
        Create a modern styled button.
        
        Args:
            parent: Parent widget
            text: Button text
            command: Command callback
            style: Button style
            **kwargs: Additional button arguments
            
        Returns:
            ttk.Button instance
        """
        return ttk.Button(
            parent,
            text=text,
            command=command,
            style=style,
            **kwargs
        )
    
    @staticmethod
    def create_frame(parent, style='Modern.TFrame', **kwargs):
        """
        Create a modern styled frame.
        
        Args:
            parent: Parent widget
            style: Frame style
            **kwargs: Additional frame arguments
            
        Returns:
            ttk.Frame instance
        """
        return ttk.Frame(parent, style=style, **kwargs)
    
    @staticmethod
    def create_label(parent, text, style='Modern.TLabel', **kwargs):
        """
        Create a modern styled label.
        
        Args:
            parent: Parent widget
            text: Label text
            style: Label style
            **kwargs: Additional label arguments
            
        Returns:
            ttk.Label instance
        """
        return ttk.Label(parent, text=text, style=style, **kwargs)
    
    @staticmethod
    def create_entry(parent, style='Modern.TEntry', **kwargs):
        """
        Create a modern styled entry.
        
        Args:
            parent: Parent widget
            style: Entry style
            **kwargs: Additional entry arguments
            
        Returns:
            ttk.Entry instance
        """
        return ttk.Entry(parent, style=style, **kwargs)



