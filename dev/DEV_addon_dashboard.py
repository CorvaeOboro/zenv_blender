"""
ZENV Blender Addon Dashboard
-----------------------------
Visual dashboard for reviewing the project's addon metadata.

Features:
- View all addons in sortable/filterable table
- Edit bl_info metadata across multiple addons
- Filter by status, approval, group, missing fields

VERSION: 20251108
"""

import os
import sys
import ast
import re
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from typing import Dict, List, Any, Optional
import json
from datetime import datetime
import re

# Import the validator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from DEV_blender_addon_metadata_validator import AddonMetadataValidator, AddonMetadata

# Dark mode color scheme
COLORS = {
    'bg_dark': '#1a1a1a',      # Very dark basalt background
    'bg_medium': '#2d2d2d',     # Medium gray for panels
    'bg_light': '#3a3a3a',      # Lighter gray for inputs
    'bg_black': '#000000',      # Pure black for scrollbars and dropdowns
    'fg_text': '#ffffff',       # White text
    'fg_dim': '#b0b0b0',        # Dimmed text
    'accent_blue': '#4a7ba7',   # Muted blue
    'accent_blue_muted': '#3a5a6a',  # More muted blue for scrollbar
    'accent_green': '#5a8a5a',  # Muted green
    'accent_green_muted': '#3a5a3a',  # More muted green for up arrow
    'accent_red': '#a75a5a',    # Muted red
    'accent_yellow': '#a79a5a', # Muted yellow
    'accent_purple': '#8a5a8a', # Muted purple
    'accent_purple_muted': '#5a3a5a',  # More muted purple for down arrow
    'border': '#404040',        # Border color
}

class AddonDashboard:
    """Main dashboard application."""
    
    def __init__(self, root, addon_dir: str):
        self.root = root
        self.addon_dir = addon_dir
        self.validator = AddonMetadataValidator(addon_dir)
        self.addons: List[AddonMetadata] = []
        self.filtered_addons: List[AddonMetadata] = []
        self.selected_addon: Optional[AddonMetadata] = None
        
        self.setup_ui()
        self.load_addons()
    
    def apply_dark_theme(self):
        """Apply dark mode theme to the application."""
        self.root.configure(bg=COLORS['bg_dark'])
        
        # Configure ttk styles
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors for all ttk widgets
        style.configure('.',
                       background=COLORS['bg_medium'],
                       foreground=COLORS['fg_text'],
                       fieldbackground=COLORS['bg_light'],
                       bordercolor=COLORS['border'],
                       darkcolor=COLORS['bg_dark'],
                       lightcolor=COLORS['bg_light'])
        
        # Treeview
        style.configure('Treeview',
                       background=COLORS['bg_medium'],
                       foreground=COLORS['fg_text'],
                       fieldbackground=COLORS['bg_medium'],
                       borderwidth=0)
        style.configure('Treeview.Heading',
                       background=COLORS['bg_dark'],
                       foreground=COLORS['fg_text'],
                       relief='flat')
        style.map('Treeview.Heading',
                 background=[('active', COLORS['bg_light'])])
        
        # Buttons - color coded
        style.configure('TButton',
                       background=COLORS['accent_blue'],
                       foreground=COLORS['fg_text'],
                       borderwidth=1,
                       relief='flat',
                       padding=6)
        style.map('TButton',
                 background=[('active', COLORS['bg_light'])])
        
        # Combobox - pure black background
        style.configure('TCombobox',
                       fieldbackground=COLORS['bg_black'],
                       background=COLORS['bg_black'],
                       foreground=COLORS['fg_text'],
                       arrowcolor=COLORS['fg_text'],
                       borderwidth=1,
                       relief='flat')
        style.map('TCombobox',
                 fieldbackground=[('readonly', COLORS['bg_black'])],
                 selectbackground=[('readonly', COLORS['bg_black'])],
                 selectforeground=[('readonly', COLORS['fg_text'])])
        
        # Scrollbar - custom colors
        # Vertical scrollbar
        style.configure('Vertical.TScrollbar',
                       background=COLORS['accent_blue_muted'],  # Slider/thumb
                       troughcolor=COLORS['bg_black'],  # Background track
                       borderwidth=0,
                       arrowcolor=COLORS['fg_text'])
        style.map('Vertical.TScrollbar',
                 background=[('active', COLORS['accent_blue']), ('!active', COLORS['accent_blue_muted'])])
        
        # Horizontal scrollbar
        style.configure('Horizontal.TScrollbar',
                       background=COLORS['accent_blue_muted'],  # Slider/thumb
                       troughcolor=COLORS['bg_black'],  # Background track
                       borderwidth=0,
                       arrowcolor=COLORS['fg_text'])
        style.map('Horizontal.TScrollbar',
                 background=[('active', COLORS['accent_blue']), ('!active', COLORS['accent_blue_muted'])])
        
        # Try to style arrow buttons (limited in ttk)
        try:
            style.element_create('uparrow', 'from', 'default')
            style.element_create('downarrow', 'from', 'default')
            style.layout('Vertical.TScrollbar', [
                ('Vertical.Scrollbar.trough', {
                    'children': [
                        ('Vertical.Scrollbar.uparrow', {'side': 'top', 'sticky': ''}),
                        ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'}),
                        ('Vertical.Scrollbar.downarrow', {'side': 'bottom', 'sticky': ''})
                    ],
                    'sticky': 'ns'
                })
            ])
        except:
            pass  # Fallback if element styling not supported
        
        # Notebook
        style.configure('TNotebook',
                       background=COLORS['bg_medium'],
                       borderwidth=0)
        style.configure('TNotebook.Tab',
                       background=COLORS['bg_dark'],
                       foreground=COLORS['fg_text'],
                       padding=[10, 5])
        style.map('TNotebook.Tab',
                 background=[('selected', COLORS['bg_medium'])],
                 foreground=[('selected', COLORS['fg_text'])])
        
        # Labels
        style.configure('TLabel',
                       background=COLORS['bg_medium'],
                       foreground=COLORS['fg_text'])
        
        # Frame
        style.configure('TFrame',
                       background=COLORS['bg_medium'])
        
        # Checkbutton
        style.configure('TCheckbutton',
                       background=COLORS['bg_medium'],
                       foreground=COLORS['fg_text'])
    
    def customize_scrollbar_arrows(self):
        """Customize scrollbar arrow button colors (called after UI is built)."""
        # This is a workaround for ttk's limited arrow styling
        # We'll use tk's option_add to set arrow colors
        self.root.option_add('*TScrollbar*uparrow*background', COLORS['accent_green_muted'])
        self.root.option_add('*TScrollbar*downarrow*background', COLORS['accent_purple_muted'])
        self.root.option_add('*TScrollbar*uparrow*activeBackground', COLORS['accent_green'])
        self.root.option_add('*TScrollbar*downarrow*activeBackground', COLORS['accent_purple'])
    
    def setup_ui(self):
        """Setup the user interface."""
        self.root.title("ZENV Addon Dashboard")
        
        # Get screen dimensions and set window to 90% of screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = int(screen_width * 0.9)
        window_height = int(screen_height * 0.9)
        
        # Center the window
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # Apply dark theme
        self.apply_dark_theme()
        
        # Main container
        main_frame = tk.Frame(self.root, bg=COLORS['bg_dark'], padx=10, pady=10)
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Top toolbar
        self.create_toolbar(main_frame)
        
        # Main content (split pane)
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Left: Addon list (60% of space)
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=3)
        self.create_addon_list(left_frame)
        
        # Right: Details/Editor (40% of space)
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)
        self.create_details_panel(right_frame)
        
        # Bottom status bar
        self.create_status_bar(main_frame)
        
        # Apply custom scrollbar arrow colors
        self.customize_scrollbar_arrows()
    
    def create_toolbar(self, parent):
        """Create top toolbar with filters and actions."""
        # Use canvas for scrollable toolbar if needed
        toolbar_container = ttk.Frame(parent)
        toolbar_container.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        toolbar_container.columnconfigure(0, weight=1)
        
        toolbar = ttk.Frame(toolbar_container)
        toolbar.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Filters
        ttk.Label(toolbar, text="Filter:").pack(side=tk.LEFT, padx=5)
        
        # Status filter
        ttk.Label(toolbar, text="Status:").pack(side=tk.LEFT)
        self.status_filter = ttk.Combobox(toolbar, width=12, state='readonly')
        self.status_filter['values'] = ['All', 'wip', 'working', 'stable', 'deprecated', 'Missing']
        self.status_filter.current(0)
        self.status_filter.bind('<<ComboboxSelected>>', lambda e: self.apply_filters())
        self.status_filter.pack(side=tk.LEFT, padx=5)
        
        # Approval filter
        ttk.Label(toolbar, text="Approved:").pack(side=tk.LEFT, padx=(10, 0))
        self.approval_filter = ttk.Combobox(toolbar, width=10, state='readonly')
        self.approval_filter['values'] = ['All', 'True', 'False', 'Missing']
        self.approval_filter.current(0)
        self.approval_filter.bind('<<ComboboxSelected>>', lambda e: self.apply_filters())
        self.approval_filter.pack(side=tk.LEFT, padx=5)
        
        # Group filter
        ttk.Label(toolbar, text="Group:").pack(side=tk.LEFT, padx=(10, 0))
        self.group_filter = ttk.Combobox(toolbar, width=12, state='readonly')
        self.group_filter['values'] = ['All']
        self.group_filter.current(0)
        self.group_filter.bind('<<ComboboxSelected>>', lambda e: self.apply_filters())
        self.group_filter.pack(side=tk.LEFT, padx=5)
        
        # Issues filter
        self.show_issues_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Issues Only", variable=self.show_issues_only,
                       command=self.apply_filters).pack(side=tk.LEFT, padx=10)
        
        # Category filters
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Label(toolbar, text="Show:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.show_main = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="Main", variable=self.show_main,
                       command=self.apply_filters).pack(side=tk.LEFT, padx=2)
        
        self.show_wip = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="WIP", variable=self.show_wip,
                       command=self.apply_filters).pack(side=tk.LEFT, padx=2)
        
        self.show_removed = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Removed", variable=self.show_removed,
                       command=self.apply_filters).pack(side=tk.LEFT, padx=2)
        
        # Actions
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Button(toolbar, text="Refresh", command=self.load_addons).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Validate All", command=self.validate_all).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Export Report", command=self.export_report).pack(side=tk.LEFT, padx=5)
    
    def create_addon_list(self, parent):
        """Create addon list with tree view."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        
        # Header
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        ttk.Label(header, text="Addons", font=('TkDefaultFont', 10, 'bold')).pack(side=tk.LEFT)
        self.addon_count_label = ttk.Label(header, text="(0)")
        self.addon_count_label.pack(side=tk.LEFT, padx=5)
        
        # Tree view
        tree_frame = ttk.Frame(parent)
        tree_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Tree
        self.tree = ttk.Treeview(tree_frame, 
                                 columns=('category', 'name', 'status', 'approved', 'group', 'version', 'issues'),
                                 show='tree headings',
                                 yscrollcommand=vsb.set,
                                 xscrollcommand=hsb.set)
        
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        # Configure columns with minwidth and stretch
        self.tree.column('#0', width=30, minwidth=30, stretch=False)
        self.tree.column('category', width=80, minwidth=60, stretch=False)
        self.tree.column('name', width=300, minwidth=200, stretch=True)
        self.tree.column('status', width=80, minwidth=60, stretch=False)
        self.tree.column('approved', width=80, minwidth=60, stretch=False)
        self.tree.column('group', width=100, minwidth=80, stretch=False)
        self.tree.column('version', width=100, minwidth=80, stretch=False)
        self.tree.column('issues', width=60, minwidth=50, stretch=False)
        
        self.tree.heading('category', text='Category', command=lambda: self.sort_by('category'))
        self.tree.heading('name', text='Name', command=lambda: self.sort_by('name'))
        self.tree.heading('status', text='Status', command=lambda: self.sort_by('status'))
        self.tree.heading('approved', text='Approved', command=lambda: self.sort_by('approved'))
        self.tree.heading('group', text='Group', command=lambda: self.sort_by('group'))
        self.tree.heading('version', text='Version', command=lambda: self.sort_by('version'))
        self.tree.heading('issues', text='Issues', command=lambda: self.sort_by('issues'))
        
        # Grid layout
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        vsb.grid(row=0, column=1, sticky=(tk.N, tk.S))
        hsb.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        # Bind selection
        self.tree.bind('<<TreeviewSelect>>', self.on_addon_select)
        
        # Tags for coloring 
        self.tree.tag_configure('error', background=COLORS['accent_red'], foreground=COLORS['fg_text'])
        self.tree.tag_configure('warning', background=COLORS['accent_yellow'], foreground=COLORS['fg_text'])
        self.tree.tag_configure('ok', background=COLORS['accent_green'], foreground=COLORS['fg_text'])
    
    def create_details_panel(self, parent):
        """Create details/editor panel."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        
        # Header with Save button
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        header.columnconfigure(1, weight=1)
        
        ttk.Label(header, text="Details & Editor", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky=tk.W)
        
        # Git timestamp info
        self.git_timestamp_label = ttk.Label(header, text="", font=('TkDefaultFont', 8))
        self.git_timestamp_label.grid(row=0, column=1, sticky=tk.W, padx=(15, 0))
        
        # Save button on the right
        ttk.Button(header, text="Save Changes", command=self.save_metadata).grid(row=0, column=2, sticky=tk.E, padx=(10, 0))
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Tab 1: Metadata viewer/editor
        self.create_metadata_tab()
        
        # Tab 2: Issues
        self.create_issues_tab()
        
        # Tab 3: Statistics
        self.create_stats_tab()
    
    def create_metadata_tab(self):
        """Create metadata editor tab."""
        # Use canvas with scrollbar for all fields
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text='Metadata')
        
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        
        # Canvas and scrollbar
        canvas = tk.Canvas(frame, bg=COLORS['bg_medium'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind canvas resize to update window width
        def on_canvas_resize(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', on_canvas_resize)
        
        # Mouse wheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=10)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        scrollable_frame.columnconfigure(1, weight=1)
        
        # Metadata fields - show ALL fields from bl_info
        self.metadata_widgets = {}
        self.metadata_frame = scrollable_frame  # Store reference for dynamic updates
        row = 0
        
        # Common editable fields (shown first)
        primary_fields = [
            ('name', 'Name', 'entry'),
            ('author', 'Author', 'entry'),
            ('blender', 'Blender Version', 'entry'),
            ('version', 'Version', 'entry'),
            ('category', 'Category', 'entry'),
            ('description', 'Description', 'entry'),
            ('status', 'Status', 'combo'),
            ('approved', 'Approved', 'combo'),
            ('group', 'Group', 'entry'),
            ('group_prefix', 'Group Prefix', 'entry'),
            ('sort_priority', 'Sort Priority', 'entry'),
            ('description_short', 'Short Desc', 'entry'),
            ('description_medium', 'Medium Desc', 'entry'),
            ('image_overview', 'Image Path', 'entry'),
        ]
        
        for field, label, widget_type in primary_fields:
            ttk.Label(scrollable_frame, text=f"{label}:").grid(row=row, column=0, sticky=tk.W, pady=2)
            
            if widget_type == 'combo':
                widget = ttk.Combobox(scrollable_frame, state='readonly')
                if field == 'status':
                    widget['values'] = ['', 'wip', 'working', 'stable', 'deprecated']
                elif field == 'approved':
                    widget['values'] = ['', 'True', 'False']
            else:
                widget = ttk.Entry(scrollable_frame)
            
            widget.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
            self.metadata_widgets[field] = widget
            row += 1
        
        # Tags (special handling)
        ttk.Label(scrollable_frame, text="Tags:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.tags_widget = ttk.Entry(scrollable_frame)
        self.tags_widget.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        row += 1
        
        # Description long (text area)
        ttk.Label(scrollable_frame, text="Long Desc:").grid(row=row, column=0, sticky=(tk.W, tk.N), pady=2)
        self.desc_long_widget = scrolledtext.ScrolledText(scrollable_frame, height=8, wrap=tk.WORD,
                                                          bg=COLORS['bg_light'],
                                                          fg=COLORS['fg_text'],
                                                          insertbackground=COLORS['fg_text'])
        self.desc_long_widget.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        row += 1
        
        # Additional fields (dynamically added when addon selected)
        ttk.Separator(scrollable_frame, orient='horizontal').grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        row += 1
        
        ttk.Label(scrollable_frame, text="Other Fields:", font=('TkDefaultFont', 9, 'bold')).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=(5, 2))
        row += 1
        
        self.other_fields_text = scrolledtext.ScrolledText(scrollable_frame, height=6, wrap=tk.WORD,
                                                           bg=COLORS['bg_light'],
                                                           fg=COLORS['fg_dim'],
                                                           insertbackground=COLORS['fg_text'])
        self.other_fields_text.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=2)
    
    def create_issues_tab(self):
        """Create issues display tab."""
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text='Issues')
        
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        
        self.issues_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, state='disabled',
                                                     bg=COLORS['bg_light'],
                                                     fg=COLORS['fg_text'])
        self.issues_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    
    def create_stats_tab(self):
        """Create statistics tab."""
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text='Statistics')
        
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        
        self.stats_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, state='disabled', 
                                                    font=('Courier', 10),
                                                    bg=COLORS['bg_light'],
                                                    fg=COLORS['fg_text'])
        self.stats_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    
    def create_status_bar(self, parent):
        """Create bottom status bar."""
        self.status_bar = ttk.Label(parent, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
    
    def load_addons(self):
        """Load all addons from directory."""
        self.status_bar.config(text="Loading addons...")
        self.root.update()
        
        self.validator.scan_directory()
        self.addons = self.validator.addons
        
        # Update group filter
        groups = set()
        for addon in self.addons:
            if 'group' in addon.bl_info:
                groups.add(addon.bl_info['group'])
        self.group_filter['values'] = ['All'] + sorted(groups)
        
        self.apply_filters()
        self.update_statistics()
        self.status_bar.config(text=f"Loaded {len(self.addons)} addons")
    
    def apply_filters(self):
        """Apply current filters to addon list."""
        self.filtered_addons = []
        
        status_filter = self.status_filter.get()
        approval_filter = self.approval_filter.get()
        group_filter = self.group_filter.get()
        issues_only = self.show_issues_only.get()
        
        # Category filters
        show_main = self.show_main.get()
        show_wip = self.show_wip.get()
        show_removed = self.show_removed.get()
        
        for addon in self.addons:
            # Category filter
            if addon.folder_category == "main" and not show_main:
                continue
            if addon.folder_category == "wip" and not show_wip:
                continue
            if addon.folder_category == "removed" and not show_removed:
                continue
            
            # Status filter
            if status_filter != 'All':
                if status_filter == 'Missing':
                    if 'status' in addon.bl_info:
                        continue
                elif addon.bl_info.get('status') != status_filter:
                    continue
            
            # Approval filter
            if approval_filter != 'All':
                if approval_filter == 'Missing':
                    if 'approved' in addon.bl_info:
                        continue
                else:
                    approved_val = str(addon.bl_info.get('approved', ''))
                    if approved_val != approval_filter:
                        continue
            
            # Group filter
            if group_filter != 'All':
                if addon.bl_info.get('group') != group_filter:
                    continue
            
            # Issues filter
            if issues_only and not addon.issues:
                continue
            
            self.filtered_addons.append(addon)
        
        self.populate_tree()
    
    def populate_tree(self):
        """Populate tree view with filtered addons."""
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add addons
        for addon in self.filtered_addons:
            category = addon.folder_category.upper()
            name = addon.bl_info.get('name', addon.file_name)
            status = addon.bl_info.get('status', 'N/A')
            approved = str(addon.bl_info.get('approved', 'N/A'))
            group = addon.bl_info.get('group', 'N/A')
            version = addon.bl_info.get('version', 'N/A')
            issue_count = len(addon.issues)
            
            # Determine tag
            if addon.has_errors:
                tag = 'error'
            elif addon.has_warnings:
                tag = 'warning'
            else:
                tag = 'ok'
            
            self.tree.insert('', 'end', values=(category, name, status, approved, group, version, issue_count),
                           tags=(tag,))
        
        self.addon_count_label.config(text=f"({len(self.filtered_addons)})")
    
    def sort_by(self, column):
        """Sort tree by column."""
        # Implementation would sort filtered_addons and repopulate
        pass
    
    def on_addon_select(self, event):
        """Handle addon selection."""
        selection = self.tree.selection()
        if not selection:
            return
        
        item = self.tree.item(selection[0])
        name = item['values'][1]  # Name is now second column (after category)
        
        # Find addon
        for addon in self.filtered_addons:
            if addon.bl_info.get('name', addon.file_name) == name:
                self.selected_addon = addon
                self.display_addon_details(addon)
                break
    
    def reselect_addon(self, file_path: str, name: str):
        """Reselect an addon in the tree after reload."""
        # Find the addon in the tree by matching name or file path
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            item_name = values[1]  # Name is second column
            
            # Find the addon to check file path
            for addon in self.filtered_addons:
                if addon.bl_info.get('name', addon.file_name) == item_name:
                    if addon.file_path == file_path or item_name == name:
                        # Select this item
                        self.tree.selection_set(item)
                        self.tree.see(item)
                        self.selected_addon = addon
                        self.display_addon_details(addon)
                        return
        
        # If not found in filtered list, clear selection
        self.selected_addon = None
    
    def get_git_timestamp(self, file_path: str) -> str:
        """Get last git commit timestamp for file in YYYYMMDDHHMMSS format."""
        try:
            # Get last commit timestamp for this file
            result = subprocess.run(
                ['git', 'log', '-1', '--format=%ct', '--', file_path],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(file_path),
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                timestamp = int(result.stdout.strip())
                dt = datetime.fromtimestamp(timestamp)
                return dt.strftime('%Y%m%d%H%M%S')
            else:
                return "No git history"
        except Exception as e:
            return f"Git unavailable"
    
    def display_addon_details(self, addon: AddonMetadata):
        """Display addon details in right panel."""
        # Update git timestamp
        git_timestamp = self.get_git_timestamp(addon.file_path)
        self.git_timestamp_label.config(text=f"Last Update: {git_timestamp}")
        
        # Populate metadata fields
        for field, widget in self.metadata_widgets.items():
            value = addon.bl_info.get(field, '')
            
            # Special handling for blender version tuple
            if field == 'blender' and isinstance(value, tuple):
                value = '.'.join(map(str, value))
            
            if isinstance(widget, ttk.Combobox):
                widget.set(str(value) if value != '' else '')
            else:
                widget.delete(0, tk.END)
                if value:
                    widget.insert(0, str(value))
        
        # Tags
        tags = addon.bl_info.get('tags', [])
        self.tags_widget.delete(0, tk.END)
        self.tags_widget.insert(0, ', '.join(tags) if isinstance(tags, list) else str(tags))
        
        # Long description
        self.desc_long_widget.delete('1.0', tk.END)
        self.desc_long_widget.insert('1.0', addon.bl_info.get('description_long', ''))
        
        # Other fields (show all fields not in primary list)
        primary_field_names = set(self.metadata_widgets.keys()) | {'tags', 'description_long'}
        other_fields = {k: v for k, v in addon.bl_info.items() if k not in primary_field_names}
        
        self.other_fields_text.delete('1.0', tk.END)
        if other_fields:
            for field, value in sorted(other_fields.items()):
                self.other_fields_text.insert(tk.END, f"{field}: {repr(value)}\n")
        else:
            self.other_fields_text.insert(tk.END, "(No additional fields)")
        
        # Issues
        self.issues_text.config(state='normal')
        self.issues_text.delete('1.0', tk.END)
        
        if addon.issues:
            for issue in addon.issues:
                self.issues_text.insert(tk.END, f"[{issue.severity.upper()}] {issue.field}\n")
                self.issues_text.insert(tk.END, f"  {issue.message}\n\n")
        else:
            self.issues_text.insert(tk.END, "No issues found.")
        
        self.issues_text.config(state='disabled')
    
    def save_metadata(self):
        """Save metadata changes to file."""
        if not self.selected_addon:
            self.status_bar.config(text="ERROR: No addon selected")
            return
        
        try:
            # Collect new values from widgets
            new_bl_info = {}
            for field, widget in self.metadata_widgets.items():
                if isinstance(widget, ttk.Combobox):
                    value = widget.get()
                    # Convert string to proper type
                    if field == 'approved':
                        if value == 'True':
                            value = True
                        elif value == 'False':
                            value = False
                        else:
                            value = None  # Empty/invalid
                else:
                    value = widget.get().strip()
                
                # Special handling for blender version - convert to tuple
                if field == 'blender' and value:
                    try:
                        # Parse "4.0.0" or "4, 0, 0" to (4, 0, 0)
                        parts = [int(p.strip()) for p in value.replace('.', ',').split(',') if p.strip()]
                        value = tuple(parts)
                    except:
                        pass  # Keep as string if parsing fails
                
                # Only add non-empty, non-None values
                if value is not None and value != '':
                    new_bl_info[field] = value
            
            # Tags (parse comma-separated)
            tags_str = self.tags_widget.get().strip()
            if tags_str:
                new_bl_info['tags'] = [t.strip() for t in tags_str.split(',') if t.strip()]
            
            # Long description
            desc_long = self.desc_long_widget.get('1.0', tk.END).strip()
            if desc_long:
                new_bl_info['description_long'] = desc_long
            
            # Store current selection info
            selected_file_path = self.selected_addon.file_path
            
            # Update bl_info in the file
            self.update_bl_info_in_file(selected_file_path, new_bl_info)
            
            # Force validator to clear cache and reload
            self.validator.addons = []
            
            # Reload to reflect changes
            self.status_bar.config(text=f"Reloading...")
            self.root.update()
            self.load_addons()
            
            # Reselect the addon in the tree by file path
            self.reselect_addon(selected_file_path, new_bl_info.get('name', ''))
            
            self.status_bar.config(text=f"Saved: {os.path.basename(selected_file_path)}")
            
        except Exception as e:
            self.status_bar.config(text=f"ERROR: {str(e)}")
    
    def update_bl_info_in_file(self, file_path: str, new_values: Dict[str, Any]):
        """Update bl_info dictionary in addon file without changing other code."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the file to find bl_info
        tree = ast.parse(content)
        bl_info_node = None
        bl_info_lineno = None
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "bl_info":
                        bl_info_node = node.value
                        bl_info_lineno = node.lineno
                        break
        
        if not bl_info_node:
            raise ValueError("No bl_info dictionary found in file")
        
        # Read current bl_info
        current_bl_info = ast.literal_eval(bl_info_node)
        
        # Merge with new values
        current_bl_info.update(new_values)
        
        # Format the new bl_info dictionary
        new_bl_info_str = self.format_bl_info(current_bl_info)
        
        # Replace bl_info in content using regex
        # Find the bl_info assignment
        pattern = r'bl_info\s*=\s*\{[^}]*\}'
        
        # For multi-line dicts, 
        lines = content.split('\n')
        
        # Find start and end of bl_info
        start_line = None
        end_line = None
        brace_count = 0
        in_bl_info = False
        
        for i, line in enumerate(lines):
            if 'bl_info' in line and '=' in line:
                start_line = i
                in_bl_info = True
                brace_count = line.count('{') - line.count('}')
            elif in_bl_info:
                brace_count += line.count('{') - line.count('}')
                if brace_count == 0:
                    end_line = i
                    break
        
        if start_line is not None and end_line is not None:
            # Replace the bl_info section
            new_lines = lines[:start_line] + [new_bl_info_str] + lines[end_line + 1:]
            new_content = '\n'.join(new_lines)
            
            # Write back to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        else:
            raise ValueError("Could not locate bl_info boundaries in file")
    
    def format_bl_info(self, bl_info: Dict[str, Any]) -> str:
        """Format bl_info dictionary as properly indented Python code."""
        lines = ["bl_info = {"]
        
        # Order: standard fields first, then extended fields
        standard_fields = ['name', 'blender', 'category', 'version', 'description']
        extended_fields = ['status', 'approved', 'sort_priority', 'group', 'group_prefix',
                          'tags', 'description_short', 'description_medium', 'description_long',
                          'image_overview']
        
        # Deprecated fields to skip
        deprecated_fields = ['author']
        
        # Add standard fields
        for field in standard_fields:
            if field in bl_info and field not in deprecated_fields:
                value = bl_info[field]
                lines.append(f'    "{field}": {repr(value)},')
        
        # Add extended fields (with blank line separator)
        has_extended = any(field in bl_info for field in extended_fields)
        if has_extended:
            lines.append('')
        
        for field in extended_fields:
            if field in bl_info:
                value = bl_info[field]
                if field == 'description_long' and isinstance(value, str) and '\n' in value:
                    # Multi-line string
                    lines.append(f'    "{field}": """')
                    lines.append(value)
                    lines.append('""",')
                else:
                    lines.append(f'    "{field}": {repr(value)},')
        
        # Add any other fields not in our lists (but skip deprecated)
        for field, value in bl_info.items():
            if field not in standard_fields and field not in extended_fields and field not in deprecated_fields:
                lines.append(f'    "{field}": {repr(value)},')
        
        lines.append('}')
        
        return '\n'.join(lines)
    
    def validate_all(self):
        """Run validation on all addons."""
        self.status_bar.config(text="Validating all addons...")
        self.root.update()
        self.load_addons()
    
    def export_report(self):
        """Export validation report."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        
        if filename:
            self.validator.generate_report(filename)
            self.status_bar.config(text=f"Report exported: {os.path.basename(filename)}")
    
    def update_statistics(self):
        """Update statistics tab."""
        self.stats_text.config(state='normal')
        self.stats_text.delete('1.0', tk.END)
        
        total = len(self.addons)
        errors = sum(1 for a in self.addons if a.has_errors)
        warnings = sum(1 for a in self.addons if a.has_warnings)
        ok = total - errors - warnings
        
        # Status breakdown
        status_counts = {}
        for addon in self.addons:
            status = addon.bl_info.get('status', 'Missing')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Group breakdown
        group_counts = {}
        for addon in self.addons:
            group = addon.bl_info.get('group', 'Missing')
            group_counts[group] = group_counts.get(group, 0) + 1
        
        stats = f"""
PROJECT STATISTICS
{'=' * 60}

Total Addons: {total}
  OK:       {ok}
  Warnings: {warnings}
  Errors:   {errors}

STATUS BREAKDOWN
{'-' * 60}
"""
        for status in sorted(status_counts.keys()):
            stats += f"  {status:15} {status_counts[status]:3}\n"
        
        stats += f"\nGROUP BREAKDOWN\n{'-' * 60}\n"
        for group in sorted(group_counts.keys()):
            stats += f"  {group:15} {group_counts[group]:3}\n"
        
        self.stats_text.insert('1.0', stats)
        self.stats_text.config(state='disabled')

def main():
    # Determine addon directory
    if len(sys.argv) > 1:
        addon_dir = sys.argv[1]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        addon_dir = os.path.join(script_dir, "..", "addon")
    
    if not os.path.exists(addon_dir):
        print(f"ERROR: Directory '{addon_dir}' does not exist")
        sys.exit(1)
    
    root = tk.Tk()
    app = AddonDashboard(root, addon_dir)
    root.mainloop()

if __name__ == "__main__":
    main()
