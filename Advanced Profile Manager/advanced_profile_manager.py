"""
Advanced Profile Manager Plugin for Mod Organizer 2
Powerful profile manager with advanced features
Opens with F7 (toggle: open/close)
Autosave with F8 (at any time, regardless of focus)

ENHANCED FEATURES:
1. Automatic profile switching (no restart)
2. Detailed profile comparison with diff visualization
3. Automatic backup management in profiles folder
4. Autosave with F8 (cyclic, max 5 autosaves)
5. Full history of all mod and plugin actions
"""
import os
import sys
import shutil
import json
import subprocess
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QDir, QProcess, QTimer, QPoint, QRect, QEvent

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, 
                             QListWidgetItem, QPushButton, QLabel, QGroupBox,
                             QMessageBox, QInputDialog, QFileDialog, QTextEdit,
                             QCheckBox, QTabWidget, QWidget, QSplitter, QComboBox,
                             QProgressDialog, QTableWidget, QTableWidgetItem, QHeaderView,
                             QApplication, QMainWindow, QToolBar, QToolButton, QMenu)
from PyQt6.QtGui import QKeySequence, QShortcut, QIcon, QFont, QColor

try:
    import mobase
except ImportError:
    class mobase:
        class IPluginTool:
            pass
        class VersionInfo:
            def __init__(self, *args): pass
        class PluginSetting:
            def __init__(self, *args): pass
        class ModState:
            ACTIVE = 1
        class PluginState:
            ACTIVE = 1

class AdvancedProfileManagerDialog(QDialog):
    """Dialog for advanced profile management"""
   
    def __init__(self, organizer, parent=None):
        super().__init__(parent)
        self.organizer = organizer
        self.setWindowTitle("Advanced Profile Manager")
        self.resize(950, 750)
        
        # Backup folder path
        self.backups_folder = os.path.join(self.organizer.basePath(), "profiles", "_backups")
        os.makedirs(self.backups_folder, exist_ok=True)
        
        # Autosave folder path
        self.autosave_folder = os.path.join(self.organizer.basePath(), "profiles", "_autosaves")
        os.makedirs(self.autosave_folder, exist_ok=True)
        
        # History file path
        self.history_file = os.path.join(self.organizer.basePath(), "profiles", "_history.json")
        self.history_data = self.loadHistory()
        
        # Maximum number of autosaves
        self.max_autosaves = 5
        
        # Register event handlers for history (WITHOUT autosave)
        self.registerEventHandlers()
        
        self.initUI()
        
        # Shortcut for F7
        try:
            dialog_shortcut = QShortcut(QKeySequence("F7"), self)
            dialog_shortcut.activated.connect(self.close)
        except Exception as e:
            print(f"PLUGIN: Shortcut error in dialog: {e}")
   
    def initUI(self):
        """Initialize the interface"""
        main_layout = QVBoxLayout()
       
        # Title
        title = QLabel("⚙️ Advanced Profile Manager Pro")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        main_layout.addWidget(title)
       
        # Tabs for different functions
        tabs = QTabWidget()
       
        # Tab 1: Profile Management
        tab_manage = self.createManageTab()
        tabs.addTab(tab_manage, "📁 Management")
       
        # Tab 2: Cloning
        tab_clone = self.createCloneTab()
        tabs.addTab(tab_clone, "🔄 Cloning")
       
        # Tab 3: Backups (enhanced)
        tab_backup = self.createBackupTab()
        tabs.addTab(tab_backup, "💾 Backups")
       
        # Tab 4: Comparison (enhanced)
        tab_compare = self.createCompareTab()
        tabs.addTab(tab_compare, "🔍 Comparison")
        
        # Tab 5: Autosave (NEW)
        tab_autosave = self.createAutosaveTab()
        tabs.addTab(tab_autosave, "💾 Autosaves")
        
        # Tab 6: History (NEW)
        tab_history = self.createHistoryTab()
        tabs.addTab(tab_history, "📜 History")
       
        main_layout.addWidget(tabs)
       
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        main_layout.addWidget(close_btn)
       
        self.setLayout(main_layout)
        self.refreshProfiles()

    def event(self, e):
        if e.type() == QEvent.Type.WindowDeactivate:
            # Не прячем сразу — даём время дочернему диалогу (Rename и т.д.) взять фокус
            QTimer.singleShot(150, self._check_should_hide)
        return super().event(e)

    def _check_should_hide(self):
        """Прячем flyout, только если фокус ушёл НЕ в дочерний диалог."""
        if not self.isVisible():
            return

        # Если flyout снова активен — не трогаем
        active = QApplication.activeWindow()
        if active is self:
            return

        # Если открыт дочерний диалог (QInputDialog, QMessageBox, QFileDialog…) — не трогаем
        if active is not None and active.parent() is self:
            return

        # Если открыт любой модальный виджет — не трогаем
        modal = QApplication.activeModalWidget()
        if modal is not None:
            return

        self.hide()

    def createManageTab(self):
        """Create the profile management tab"""
        widget = QWidget()
        layout = QVBoxLayout()
       
        # Profile list
        profile_group = QGroupBox("Profiles")
        profile_layout = QVBoxLayout()
       
        self.profile_list = QListWidget()
        self.profile_list.itemSelectionChanged.connect(self.onProfileSelected)
        self.profile_list.itemDoubleClicked.connect(self.switchProfileImproved)
        profile_layout.addWidget(self.profile_list)
       
        # Selected profile info
        self.profile_info = QTextEdit()
        self.profile_info.setReadOnly(True)
        self.profile_info.setMaximumHeight(150)
        profile_layout.addWidget(QLabel("📝 Info:"))
        profile_layout.addWidget(self.profile_info)
       
        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)
       
        # Management buttons
        btn_layout = QHBoxLayout()
       
        create_btn = QPushButton("➕ Create")
        create_btn.clicked.connect(self.createProfile)
        btn_layout.addWidget(create_btn)
        
        copy_btn = QPushButton("📄 Create Copy")
        copy_btn.clicked.connect(self.copyProfile)
        copy_btn.setToolTip("Quick copy of the selected profile")
        btn_layout.addWidget(copy_btn)
       
        rename_btn = QPushButton("✏️ Rename")
        rename_btn.clicked.connect(self.renameProfile)
        btn_layout.addWidget(rename_btn)
       
        delete_btn = QPushButton("🗑️ Delete")
        delete_btn.clicked.connect(self.deleteProfile)
        btn_layout.addWidget(delete_btn)
       
        switch_btn = QPushButton("🔄 Switch")
        switch_btn.clicked.connect(self.switchProfileImproved)
        switch_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        btn_layout.addWidget(switch_btn)
       
        layout.addLayout(btn_layout)
        widget.setLayout(layout)
        return widget
   

    def createCloneTab(self):
        """Create the profile cloning tab"""
        widget = QWidget()
        layout = QVBoxLayout()
       
        layout.addWidget(QLabel("Select profile to clone:"))
        self.clone_combo = QComboBox()
        layout.addWidget(self.clone_combo)
       
        layout.addWidget(QLabel("\nWhat to clone:"))
       
        self.clone_modlist = QCheckBox("Mod list and order (modlist.txt)")
        self.clone_modlist.setChecked(True)
        layout.addWidget(self.clone_modlist)
       
        self.clone_loadorder = QCheckBox("Plugin load order (loadorder.txt)")
        self.clone_loadorder.setChecked(True)
        layout.addWidget(self.clone_loadorder)

        self.clone_plugins = QCheckBox("Plugin states (plugins.txt)")
        self.clone_plugins.setChecked(True)
        layout.addWidget(self.clone_plugins)
       
        self.clone_archives = QCheckBox("Archives list (archives.txt)")
        self.clone_archives.setChecked(True)
        layout.addWidget(self.clone_archives)

        self.clone_settings = QCheckBox("Profile settings (settings.txt) — LocalSaves, Archive Invalidation")
        self.clone_settings.setChecked(True)
        layout.addWidget(self.clone_settings)

        self.clone_initweaks = QCheckBox("INI tweaks (initweaks.txt)")
        self.clone_initweaks.setChecked(True)
        layout.addWidget(self.clone_initweaks)

        self.clone_lockedorder = QCheckBox("Locked load order (lockedorder.txt)")
        self.clone_lockedorder.setChecked(True)
        layout.addWidget(self.clone_lockedorder)
       
        self.clone_ini = QCheckBox("INI files (game settings)")
        self.clone_ini.setChecked(False)
        layout.addWidget(self.clone_ini)
       
        self.clone_saves = QCheckBox("Game saves")
        self.clone_saves.setChecked(False)
        layout.addWidget(self.clone_saves)
       
        layout.addStretch()
       
        clone_btn = QPushButton("🔄 Clone Profile")
        clone_btn.clicked.connect(self.cloneProfile)
        layout.addWidget(clone_btn)
       
        widget.setLayout(layout)
        return widget
   

    def createBackupTab(self):
        """Create the ENHANCED backups tab"""
        widget = QWidget()
        layout = QVBoxLayout()
       
        # Info
        info_label = QLabel(f"📂 Backups folder: {self.backups_folder}")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
       
        # Existing backups list
        backup_group = QGroupBox("💾 Existing Backups")
        backup_layout = QVBoxLayout()
       
        self.backup_list = QListWidget()
        self.backup_list.itemSelectionChanged.connect(self.onBackupSelected)
        backup_layout.addWidget(self.backup_list)
       
        # Selected backup info
        self.backup_info = QTextEdit()
        self.backup_info.setReadOnly(True)
        self.backup_info.setMaximumHeight(100)
        backup_layout.addWidget(self.backup_info)
       
        backup_group.setLayout(backup_layout)
        layout.addWidget(backup_group)
       
        # Backup management buttons
        backup_btn_layout = QHBoxLayout()
       
        create_backup_btn = QPushButton("💾 Create Backup")
        create_backup_btn.clicked.connect(self.createBackup)
        backup_btn_layout.addWidget(create_backup_btn)
       
        restore_backup_btn = QPushButton("📥 Restore")
        restore_backup_btn.clicked.connect(self.restoreBackup)
        backup_btn_layout.addWidget(restore_backup_btn)
       
        delete_backup_btn = QPushButton("🗑️ Delete Backup")
        delete_backup_btn.clicked.connect(self.deleteBackup)
        backup_btn_layout.addWidget(delete_backup_btn)
       
        refresh_backup_btn = QPushButton("🔄 Refresh")
        refresh_backup_btn.clicked.connect(self.refreshBackups)
        backup_btn_layout.addWidget(refresh_backup_btn)
       
        layout.addLayout(backup_btn_layout)
       
        # Cleanup old backups button
        cleanup_btn = QPushButton("🧹 Delete Old Backups (>30 days)")
        cleanup_btn.clicked.connect(self.cleanupOldBackups)
        layout.addWidget(cleanup_btn)
       
        widget.setLayout(layout)
        return widget
   

    def createCompareTab(self):
        """Create the ENHANCED profile comparison tab"""
        widget = QWidget()
        layout = QVBoxLayout()
       
        selection_layout = QHBoxLayout()
       
        # Profile 1
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Profile 1:"))
        self.compare_combo1 = QComboBox()
        left_layout.addWidget(self.compare_combo1)
        selection_layout.addLayout(left_layout)
       
        # Profile 2
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Profile 2:"))
        self.compare_combo2 = QComboBox()
        right_layout.addWidget(self.compare_combo2)
        selection_layout.addLayout(right_layout)
       
        layout.addLayout(selection_layout)
       
        # Comparison options
        options_layout = QHBoxLayout()
        self.compare_order = QCheckBox("Consider mod order")
        self.compare_order.setChecked(True)
        options_layout.addWidget(self.compare_order)
       
        self.compare_status = QCheckBox("Consider status (enabled/disabled)")
        self.compare_status.setChecked(True)
        options_layout.addWidget(self.compare_status)
       
        layout.addLayout(options_layout)
       
        compare_btn = QPushButton("🔍 Compare Profiles (Detailed)")
        compare_btn.clicked.connect(self.compareProfilesDetailed)
        layout.addWidget(compare_btn)
       
        # Results tabs
        self.compare_tabs = QTabWidget()
       
        # Tab: Summary
        self.compare_summary = QTextEdit()
        self.compare_summary.setReadOnly(True)
        self.compare_tabs.addTab(self.compare_summary, "📊 Summary")
       
        # Tab: Differences table
        self.compare_table = QTableWidget()
        self.compare_table.setColumnCount(4)
        self.compare_table.setHorizontalHeaderLabels(["Mod/Plugin", "Profile 1", "Profile 2", "Type"])
        self.compare_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.compare_tabs.addTab(self.compare_table, "📋 Details")
       
        # Tab: Full text output
        self.compare_full = QTextEdit()
        self.compare_full.setReadOnly(True)
        self.compare_tabs.addTab(self.compare_full, "📄 Full Report")
       
        layout.addWidget(self.compare_tabs)
       
        widget.setLayout(layout)
        return widget
    
    def createAutosaveTab(self):
        """Create the AUTOSAVE tab for profiles"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Info
        info_group = QGroupBox("ℹ️ About Autosave")
        info_layout = QVBoxLayout()
        
        info_text = QLabel(
            "Autosave creates backup copies of the current profile\n"
            "by pressing the hotkey F8.\n\n"
            f"📂 Autosave folder: {self.autosave_folder}\n"
            f"🔄 Max autosaves: {self.max_autosaves} (new ones replace old)\n\n"
            "⌨️ Press F8 anytime to create an autosave!\n"
            
            "Action history is logged automatically on:\n"
            "  • Enabling/disabling mods\n"
            "  • Moving mods\n"
            "  • Installing new mods\n"
            "  • Removing mods\n"
            "  • Changing plugin states\n"
            "  • Moving plugins"
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Autosaves list
        autosave_group = QGroupBox("💾 Available Autosaves")
        autosave_layout = QVBoxLayout()
        
        self.autosave_list = QListWidget()
        self.autosave_list.itemSelectionChanged.connect(self.onAutosaveSelected)
        autosave_layout.addWidget(self.autosave_list)
        
        # Selected autosave info
        self.autosave_info = QTextEdit()
        self.autosave_info.setReadOnly(True)
        self.autosave_info.setMaximumHeight(100)
        autosave_layout.addWidget(self.autosave_info)
        
        autosave_group.setLayout(autosave_layout)
        layout.addWidget(autosave_group)
        
        # Autosave management buttons
        autosave_btn_layout = QHBoxLayout()
        
        create_autosave_btn = QPushButton("💾 Create Autosave (F8)")
        create_autosave_btn.clicked.connect(self.createManualAutosave)
        create_autosave_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        autosave_btn_layout.addWidget(create_autosave_btn)
        
        restore_autosave_btn = QPushButton("📥 Restore Autosave")
        restore_autosave_btn.clicked.connect(self.restoreAutosave)
        autosave_btn_layout.addWidget(restore_autosave_btn)
        
        delete_autosave_btn = QPushButton("🗑️ Delete Autosave")
        delete_autosave_btn.clicked.connect(self.deleteAutosave)
        autosave_btn_layout.addWidget(delete_autosave_btn)
        
        refresh_autosave_btn = QPushButton("🔄 Refresh")
        refresh_autosave_btn.clicked.connect(self.refreshAutosaves)
        autosave_btn_layout.addWidget(refresh_autosave_btn)
        
        layout.addLayout(autosave_btn_layout)
        
        # Clear all autosaves button
        clear_all_btn = QPushButton("🧹 Delete All Autosaves")
        clear_all_btn.clicked.connect(self.clearAllAutosaves)
        layout.addWidget(clear_all_btn)
        
        widget.setLayout(layout)
        return widget
    
    def createHistoryTab(self):
        """Create the ACTION HISTORY tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Info
        info_label = QLabel("📜 History of all mod and plugin actions")
        info_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(info_label)
        
        # Filters
        filter_group = QGroupBox("🔍 Filters")
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Action Type:"))
        self.history_filter_combo = QComboBox()
        self.history_filter_combo.addItems([
            "All",
            "Mods - addition",
            "Mods - removal", 
            "Mods - enable/disable",
            "Mods - move",
            "Plugins - enable/disable",
            "Plugins - move",
            "Separators - addition"
        ])
        self.history_filter_combo.currentTextChanged.connect(self.filterHistory)
        filter_layout.addWidget(self.history_filter_combo)
        
        filter_layout.addWidget(QLabel("Profile:"))
        self.history_profile_combo = QComboBox()
        self.history_profile_combo.addItem("All Profiles")
        self.history_profile_combo.currentTextChanged.connect(self.filterHistory)
        filter_layout.addWidget(self.history_profile_combo)
        
        filter_layout.addStretch()
        
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # History table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels([
            "Date/Time", "Profile", "Action Type", "Object", "Details"
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.history_table)
        
        # History management buttons
        history_btn_layout = QHBoxLayout()
        
        refresh_history_btn = QPushButton("🔄 Refresh")
        refresh_history_btn.clicked.connect(self.refreshHistory)
        history_btn_layout.addWidget(refresh_history_btn)
        
        export_history_btn = QPushButton("📤 Export History")
        export_history_btn.clicked.connect(self.exportHistory)
        history_btn_layout.addWidget(export_history_btn)
        
        clear_history_btn = QPushButton("🗑️ Clear History")
        clear_history_btn.clicked.connect(self.clearHistory)
        history_btn_layout.addWidget(clear_history_btn)
        
        layout.addLayout(history_btn_layout)
        
        widget.setLayout(layout)
        return widget
   

    def refreshProfiles(self):
        """Refresh the profiles list"""
        try:
            self.profile_list.clear()
            self.clone_combo.clear()
            self.compare_combo1.clear()
            self.compare_combo2.clear()
           
            profiles_path = os.path.join(self.organizer.basePath(), "profiles")
           
            if not os.path.exists(profiles_path):
                return
           
            current_profile = self.organizer.profileName()
            current_index = -1
           
            for idx, profile_name in enumerate(sorted(os.listdir(profiles_path))):
                profile_dir = os.path.join(profiles_path, profile_name)
                if os.path.isdir(profile_dir) and not profile_name.startswith('_'):
                    item = QListWidgetItem(profile_name)
                    if profile_name == current_profile:
                        item.setText(f"⭐ {profile_name} (current)")
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        current_index = self.profile_list.count()
                    self.profile_list.addItem(item)
                   
                    # Add to comboboxes
                    self.clone_combo.addItem(profile_name)
                    self.compare_combo1.addItem(profile_name)
                    self.compare_combo2.addItem(profile_name)
                    
                    # Remember current profile index in comboboxes
                    if profile_name == current_profile:
                        combo_current_index = self.clone_combo.count() - 1
           
            # AUTO-FOCUS on current profile
            if current_index >= 0:
                self.profile_list.setCurrentRow(current_index)
                
            # AUTO-FOCUS in comboboxes
            if current_profile:
                for combo in [self.clone_combo, self.compare_combo1, self.compare_combo2]:
                    index = combo.findText(current_profile)
                    if index >= 0:
                        combo.setCurrentIndex(index)
           
            # Refresh backups list
            self.refreshBackups()
            
            # Update profile history in filter
            current_profile = self.organizer.profileName()
            self.history_profile_combo.clear()
            self.history_profile_combo.addItem("All Profiles")
            for i in range(self.profile_list.count()):
                profile = self.profile_list.item(i).text().replace("⭐ ", "").replace(" (current)", "")
                self.history_profile_combo.addItem(profile)
            
            # Refresh autosaves
            self.refreshAutosaves()
           
        except Exception as e:
            print(f"PLUGIN: Error refreshing profiles list: {e}")
   

    def refreshBackups(self):
        """Refresh the backups list"""
        try:
            self.backup_list.clear()
           
            if not os.path.exists(self.backups_folder):
                return
           
            backups = []
            for filename in os.listdir(self.backups_folder):
                if filename.endswith('.zip'):
                    filepath = os.path.join(self.backups_folder, filename)
                    mtime = os.path.getmtime(filepath)
                    size = os.path.getsize(filepath)
                    backups.append((filename, mtime, size))
           
            # Sort by time (newest on top)
            backups.sort(key=lambda x: x[1], reverse=True)
           
            for filename, mtime, size in backups:
                date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                size_mb = size / (1024 * 1024)
                item = QListWidgetItem(f"📦 {filename}")
                item.setData(Qt.ItemDataRole.UserRole, {'filename': filename, 'mtime': mtime, 'size': size})
                item.setToolTip(f"Date: {date_str}\nSize: {size_mb:.2f} MB")
                self.backup_list.addItem(item)
           
        except Exception as e:
            print(f"PLUGIN: Error refreshing backups list: {e}")
   

    def onBackupSelected(self):
        """Handle backup selection"""
        selected = self.backup_list.selectedItems()
        if not selected:
            self.backup_info.clear()
            return
       
        data = selected[0].data(Qt.ItemDataRole.UserRole)
        filename = data['filename']
        mtime = data['mtime']
        size = data['size']
       
        date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        size_mb = size / (1024 * 1024)
       
        # Parse filename
        parts = filename.replace('.zip', '').split('_')
        profile_name = '_'.join(parts[:-2]) if len(parts) >= 3 else "unknown"
       
        info = []
        info.append(f"📦 Backup: {filename}")
        info.append(f"📁 Profile: {profile_name}")
        info.append(f"📅 Creation Date: {date_str}")
        info.append(f"💾 Size: {size_mb:.2f} MB")
       
        self.backup_info.setText("\n".join(info))
   

    def onProfileSelected(self):
        """Handle profile selection"""
        selected = self.profile_list.selectedItems()
        if not selected:
            self.profile_info.clear()
            return
       
        profile_name = selected[0].text().replace("⭐ ", "").replace(" (current)", "")
        self.showProfileInfo(profile_name)
   

    def showProfileInfo(self, profile_name):
        """Display profile information"""
        try:
            profiles_path = os.path.join(self.organizer.basePath(), "profiles")
            profile_path = os.path.join(profiles_path, profile_name)
           
            info = []
            info.append(f"📁 Profile: {profile_name}")
            info.append(f"📂 Path: {profile_path}")
            info.append("")
           
            # Count mods
            modlist_file = os.path.join(profile_path, "modlist.txt")
            if os.path.exists(modlist_file):
                with open(modlist_file, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                    enabled = sum(1 for line in lines if line.startswith('+'))
                    disabled = sum(1 for line in lines if line.startswith('-'))
                    info.append(f"📦 Mods: {len(lines)} (✅ {enabled}, ❌ {disabled})")
            else:
                info.append("📦 Mods: modlist.txt not found")
           
            # Count plugins
            plugins_file = os.path.join(profile_path, "plugins.txt")
            if os.path.exists(plugins_file):
                with open(plugins_file, 'r', encoding='utf-8', errors='ignore') as f:
                    enabled = 0
                    disabled = 0
                    for raw_line in f.readlines():
                        line = raw_line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if line.startswith('*'):
                            enabled += 1
                        else:
                            disabled += 1
                    info.append(f"🔌 Plugins: {enabled + disabled} (✅ {enabled}, ❌ {disabled})")
            else:
                info.append("🔌 Plugins: plugins.txt not found")

            settings = self.getProfileSettings(profile_path)
            info.append("")
            info.append("⚙️ Profile Settings:")
            info.append(f"  💾 Local Saves: {'✅ Yes' if settings.get('LocalSaves', False) else '❌ No'}")
            info.append(f"  📄 Local Settings: {'✅ Yes' if settings.get('LocalSettings', False) else '❌ No'}")
            info.append(f"  📦 Archive Invalidation: {'✅ Yes' if settings.get('AutomaticArchiveInvalidation', False) else '❌ No'}")

            if settings.get('LocalSaves', False):
                saves_path = os.path.join(profile_path, "saves")
                save_files = 0
                if os.path.exists(saves_path):
                    save_files = sum(1 for name in os.listdir(saves_path) if os.path.isfile(os.path.join(saves_path, name)))
                info.append(f"  🎮 Save files: {save_files}")
           
            # Check files
            info.append("")
            info.append("📄 Profile Files:")
            for filename in ["modlist.txt", "plugins.txt", "loadorder.txt", "archives.txt", "settings.txt", "initweaks.txt", "lockedorder.txt"]:
                filepath = os.path.join(profile_path, filename)
                if os.path.exists(filepath):
                    size = os.path.getsize(filepath)
                    info.append(f"  ✅ {filename} ({size} bytes)")
                else:
                    info.append(f"  ❌ {filename}")
           
            self.profile_info.setText("\n".join(info))
           
        except Exception as e:
            self.profile_info.setText(f"Error: {str(e)}")
   

    def createProfile(self):
        """Create a new profile"""
        name, ok = QInputDialog.getText(self, "Create Profile", 
                                         "Enter new profile name:")
        if ok and name:
            try:
                profiles_path = os.path.join(self.organizer.basePath(), "profiles")
                new_profile_path = os.path.join(profiles_path, name)
               
                if os.path.exists(new_profile_path):
                    QMessageBox.warning(self, "Error", "Profile with this name already exists!")
                    return
               
                os.makedirs(new_profile_path)
                open(os.path.join(new_profile_path, "modlist.txt"), 'w').close()
                open(os.path.join(new_profile_path, "loadorder.txt"), 'w').close()
               
                QMessageBox.information(self, "Success", f"Profile '{name}' created!")
                self.refreshProfiles()
               
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create profile:\n{str(e)}")
    

    def copyProfile(self):
        """Quick profile copy"""
        selected = self.profile_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "Select a profile to copy!")
            return
        
        source_name = selected[0].text().replace("⭐ ", "").replace(" (current)", "")
        new_name, ok = QInputDialog.getText(
            self, "Create Profile Copy",
            "Name for profile copy:",
            text=f"{source_name} - Copy"
        )
        
        if ok and new_name:
            try:
                profiles_path = os.path.join(self.organizer.basePath(), "profiles")
                source_path = os.path.join(profiles_path, source_name)
                dest_path = os.path.join(profiles_path, new_name)
                
                if os.path.exists(dest_path):
                    QMessageBox.warning(self, "Error", "Profile with this name already exists!")
                    return
                
                # Full profile copy
                shutil.copytree(source_path, dest_path)
                
                QMessageBox.information(self, "Success", f"Profile copy '{new_name}' created!")
                self.refreshProfiles()
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to copy profile:\n{str(e)}")
   

    def renameProfile(self):
        """Rename profile"""
        selected = self.profile_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "Select a profile!")
            return
       
        old_name = selected[0].text().replace("⭐ ", "").replace(" (current)", "")
        new_name, ok = QInputDialog.getText(self, "Rename Profile",
                                             "New name:", text=old_name)
       
        if ok and new_name and new_name != old_name:
            try:
                profiles_path = os.path.join(self.organizer.basePath(), "profiles")
                old_path = os.path.join(profiles_path, old_name)
                new_path = os.path.join(profiles_path, new_name)
               
                if os.path.exists(new_path):
                    QMessageBox.warning(self, "Error", "Profile with this name already exists!")
                    return
               
                os.rename(old_path, new_path)
                QMessageBox.information(self, "Success", "Profile renamed!")
                self.refreshProfiles()
               
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to rename:\n{str(e)}")
   

    def deleteProfile(self):
        """Delete profile"""
        selected = self.profile_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "Select a profile!")
            return
       
        profile_name = selected[0].text().replace("⭐ ", "").replace(" (current)", "")
       
        reply = QMessageBox.question(self, "Confirmation",
                                     f"Delete profile '{profile_name}'?\n\nThis action is irreversible!",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
       
        if reply == QMessageBox.StandardButton.Yes:
            try:
                profiles_path = os.path.join(self.organizer.basePath(), "profiles")
                profile_path = os.path.join(profiles_path, profile_name)
               
                shutil.rmtree(profile_path)
                QMessageBox.information(self, "Success", f"Profile '{profile_name}' deleted!")
                self.refreshProfiles()
               
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete:\n{str(e)}")

    def _find_profile_combobox(self):
        current_profile = self.organizer.profileName()
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMainWindow):
                for cb in w.findChildren(QComboBox):
                    try:
                        if current_profile in [cb.itemText(i) for i in range(cb.count())]:
                            return cb
                    except Exception:
                        continue
        return None

    def _switch_profile_via_ui(self, profile_name):
        cb = self._find_profile_combobox()
        if cb is None:
            return False
        index = cb.findText(profile_name)
        if index < 0:
            return False
        if cb.currentIndex() == index:
            return True
        cb.setCurrentIndex(index)
        try:
            cb.activated.emit(index)
        except Exception:
            pass
        return True
   
    def switchProfileImproved(self):
        """ENHANCED profile switching without restart"""
        selected = self.profile_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "Select a profile!")
            return
       
        profile_name = selected[0].text().replace("⭐ ", "").replace(" (current)", "")
        current_profile = self.organizer.profileName()
       
        if profile_name == current_profile:
            QMessageBox.information(self, "Info", "This profile is already active!")
            return
       
        reply = QMessageBox.question(
            self, "Switch Profile",
            f"Switch to profile '{profile_name}'?\n\n"
            "Changes will be applied immediately.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
       
        if reply == QMessageBox.StandardButton.Yes:
            try:
                switched = self._switch_profile_via_ui(profile_name)
                if not switched:
                    QMessageBox.warning(
                        self, "Warning",
                        "Profile selector not found in MO2 UI.\n"
                        "Switch profile manually using MO2 profile selector."
                    )
                    return
                try:
                    self.organizer.refresh(True)
                except Exception:
                    pass
                QTimer.singleShot(400, self.refreshProfiles)
            except Exception as e:
                QMessageBox.critical(self, "Error", 
                    f"Failed to switch profile:\n{str(e)}\n\n"
                    "Try switching profile manually in MO2.")
   

    def cloneProfile(self):
        """Clone profile"""
        source_name = self.clone_combo.currentText()
        if not source_name:
            QMessageBox.warning(self, "Warning", "Select a profile!")
            return
       
        new_name, ok = QInputDialog.getText(self, "Clone Profile",
                                            "New profile name:",
                                            text=f"{source_name} - Copy")
       
        if ok and new_name:
            try:
                profiles_path = os.path.join(self.organizer.basePath(), "profiles")
                source_path = os.path.join(profiles_path, source_name)
                dest_path = os.path.join(profiles_path, new_name)
               
                if os.path.exists(dest_path):
                    QMessageBox.warning(self, "Error", "Profile with this name already exists!")
                    return
               
                os.makedirs(dest_path)
               
                files_to_copy = []
                if self.clone_modlist.isChecked():
                    files_to_copy.append("modlist.txt")
                if self.clone_loadorder.isChecked():
                    files_to_copy.append("loadorder.txt")
                if self.clone_plugins.isChecked():
                    files_to_copy.append("plugins.txt")
                if self.clone_archives.isChecked():
                    files_to_copy.append("archives.txt")
                if self.clone_settings.isChecked():
                    files_to_copy.append("settings.txt")
                if self.clone_initweaks.isChecked():
                    files_to_copy.append("initweaks.txt")
                if self.clone_lockedorder.isChecked():
                    files_to_copy.append("lockedorder.txt")
                if self.clone_ini.isChecked():
                    for filename in os.listdir(source_path):
                        if filename.lower().endswith(".ini"):
                            files_to_copy.append(filename)
               
                for filename in files_to_copy:
                    src = os.path.join(source_path, filename)
                    dst = os.path.join(dest_path, filename)
                    if os.path.exists(src):
                        shutil.copy2(src, dst)
               
                settings = self.getProfileSettings(source_path)

                if self.clone_saves.isChecked() and not settings.get("LocalSaves", False):
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "LocalSaves is disabled in settings.txt.\n"
                        "Save files are stored in the system folder and may not exist in this profile."
                    )

                if self.clone_saves.isChecked() and not self.clone_settings.isChecked():
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "You are copying saves without settings.txt.\n"
                        "MO2 will not see these saves unless LocalSaves=true in the new profile."
                    )

                if self.clone_saves.isChecked():
                    saves_src = os.path.join(source_path, "saves")
                    saves_dst = os.path.join(dest_path, "saves")
                    if os.path.exists(saves_src):
                        shutil.copytree(saves_src, saves_dst)
               
                QMessageBox.information(self, "Success", f"Profile '{new_name}' created!")
                self.refreshProfiles()
               
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clone:\n{str(e)}")
   

    def createBackup(self):
        """ENHANCED backup creation (auto to _backups folder)"""
        # Get current profile for auto-focus
        current_profile = self.organizer.profileName()
        
        # Create profiles list
        profiles = [self.profile_list.item(i).text().replace("⭐ ", "").replace(" (current)", "") 
                   for i in range(self.profile_list.count())]
        
        # Determine current profile index
        current_index = 0
        if current_profile in profiles:
            current_index = profiles.index(current_profile)
        
        # Selection dialog with auto-focus on current profile
        profile_name, ok = QInputDialog.getItem(
            self, "Create Backup", 
            "Select profile for backup:", 
            profiles, 
            current_index,  # AUTO-FOCUS on current profile
            False
        )
       
        if ok and profile_name:
            try:
                profiles_path = os.path.join(self.organizer.basePath(), "profiles")
                profile_path = os.path.join(profiles_path, profile_name)
               
                # Auto filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_filename = f"{profile_name}_{timestamp}.zip"
                backup_path = os.path.join(self.backups_folder, backup_filename)
               
                # Create archive
                progress = QProgressDialog("Creating backup...", "Cancel", 0, 0, self)
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.show()
               
                shutil.make_archive(
                    backup_path.replace('.zip', ''), 
                    'zip', 
                    profile_path
                )
               
                progress.close()
               
                size_mb = os.path.getsize(backup_path) / (1024 * 1024)
                QMessageBox.information(
                    self, "Success",
                    f"Backup created!\n\n"
                    f"File: {backup_filename}\n"
                    f"Size: {size_mb:.2f} MB\n"
                    f"Folder: {self.backups_folder}"
                )
               
                self.refreshBackups()
               
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create backup:\n{str(e)}")
   

    def restoreBackup(self):
        """ENHANCED restore from backup"""
        selected = self.backup_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "Select a backup to restore!")
            return
       
        data = selected[0].data(Qt.ItemDataRole.UserRole)
        backup_filename = data['filename']
        backup_path = os.path.join(self.backups_folder, backup_filename)

        if not zipfile.is_zipfile(backup_path):
            QMessageBox.critical(self, "Error", "Invalid backup архив или файл повреждён.")
            return
       
        # Extract profile name from filename
        parts = backup_filename.replace('.zip', '').split('_')
        original_profile_name = '_'.join(parts[:-2]) if len(parts) >= 3 else "restored_profile"
       
        # Ask for restored profile name
        new_name, ok = QInputDialog.getText(
            self, "Restore Backup",
            "Enter name for restored profile:",
            text=f"{original_profile_name}_restored"
        )
       
        if ok and new_name:
            try:
                profiles_path = os.path.join(self.organizer.basePath(), "profiles")
                dest_path = os.path.join(profiles_path, new_name)
               
                if os.path.exists(dest_path):
                    reply = QMessageBox.question(
                        self, "Profile Exists",
                        f"Profile '{new_name}' already exists.\n\n"
                        "Replace its contents with backup?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                   
                    if reply == QMessageBox.StandardButton.No:
                        return
                   
                    shutil.rmtree(dest_path)
               
                # Unpack backup
                progress = QProgressDialog("Restoring from backup...", "Cancel", 0, 0, self)
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.show()
               
                shutil.unpack_archive(backup_path, dest_path)
               
                progress.close()
               
                QMessageBox.information(
                    self, "Success",
                    f"Profile '{new_name}' restored from backup!"
                )
               
                self.refreshProfiles()
               
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to restore:\n{str(e)}")
   

    def deleteBackup(self):
        """Delete backup"""
        selected = self.backup_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "Select a backup to delete!")
            return
       
        data = selected[0].data(Qt.ItemDataRole.UserRole)
        backup_filename = data['filename']
        backup_path = os.path.join(self.backups_folder, backup_filename)
       
        reply = QMessageBox.question(
            self, "Delete Backup",
            f"Delete backup '{backup_filename}'?\n\nThis action is irreversible!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
       
        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.remove(backup_path)
                QMessageBox.information(self, "Success", "Backup deleted!")
                self.refreshBackups()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete:\n{str(e)}")
   

    def cleanupOldBackups(self):
        """Delete old backups (>30 days)"""
        try:
            current_time = datetime.now().timestamp()
            thirty_days = 30 * 24 * 60 * 60
            deleted_count = 0
           
            for filename in os.listdir(self.backups_folder):
                if filename.endswith('.zip'):
                    filepath = os.path.join(self.backups_folder, filename)
                    mtime = os.path.getmtime(filepath)
                   
                    if (current_time - mtime) > thirty_days:
                        os.remove(filepath)
                        deleted_count += 1
           
            if deleted_count > 0:
                QMessageBox.information(
                    self, "Cleanup Complete",
                    f"Deleted old backups: {deleted_count}"
                )
            else:
                QMessageBox.information(
                    self, "Cleanup Complete",
                    "No old backups (>30 days) found."
                )
           
            self.refreshBackups()
           
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to cleanup:\n{str(e)}")
   

    def compareProfilesDetailed(self):
        """ENHANCED detailed profile comparison with diff visualization"""
        profile1 = self.compare_combo1.currentText()
        profile2 = self.compare_combo2.currentText()
       
        if not profile1 or not profile2:
            QMessageBox.warning(self, "Warning", "Select both profiles!")
            return
       
        if profile1 == profile2:
            QMessageBox.warning(self, "Warning", "Select different profiles!")
            return
       
        try:
            profiles_path = os.path.join(self.organizer.basePath(), "profiles")
            path1 = os.path.join(profiles_path, profile1)
            path2 = os.path.join(profiles_path, profile2)
           
            # Read profile data
            mods1 = self.readProfileFileDetailed(path1, "modlist.txt")
            mods2 = self.readProfileFileDetailed(path2, "modlist.txt")
           
            plugins1 = self.readPluginsFileDetailed(path1)
            plugins2 = self.readPluginsFileDetailed(path2)

            archives1 = self.readProfileFile(path1, "archives.txt")
            archives2 = self.readProfileFile(path2, "archives.txt")

            settings1 = self.getProfileSettings(path1)
            settings2 = self.getProfileSettings(path2)
           
            # SUMMARY
            summary = self.generateComparisonSummary(
                profile1, profile2, mods1, mods2, plugins1, plugins2, archives1, archives2, settings1, settings2
            )
            self.compare_summary.setText(summary)
           
            # DIFFERENCES TABLE
            self.populateComparisonTable(profile1, profile2, mods1, mods2, plugins1, plugins2)
           
            # FULL REPORT
            full_report = self.generateFullReport(
                profile1, profile2, mods1, mods2, plugins1, plugins2, archives1, archives2, settings1, settings2
            )
            self.compare_full.setText(full_report)
           
        except Exception as e:
            error_msg = f"Comparison error:\n{str(e)}"
            self.compare_summary.setText(error_msg)
            self.compare_full.setText(error_msg)
   

    def generateComparisonSummary(self, profile1, profile2, mods1, mods2, plugins1, plugins2, archives1, archives2, settings1, settings2):
        """Generate comparison summary"""
        lines = []
        lines.append("=" * 70)
        lines.append("📊 PROFILE COMPARISON SUMMARY")
        lines.append("=" * 70)
        lines.append(f"\n📁 Profile 1: {profile1}")
        lines.append(f"📁 Profile 2: {profile2}\n")
       
        # Mods stats
        lines.append("=" * 70)
        lines.append("📦 MODS:")
        lines.append("=" * 70)
       
        mods1_names = {m['name'] for m in mods1}
        mods2_names = {m['name'] for m in mods2}
       
        only_in_1 = mods1_names - mods2_names
        only_in_2 = mods2_names - mods1_names
        common = mods1_names & mods2_names
       
        lines.append(f"  Total mods in profile 1: {len(mods1)}")
        lines.append(f"  Total mods in profile 2: {len(mods2)}")
        lines.append(f"  ✅ Common mods: {len(common)}")
        lines.append(f"  ➕ Only in '{profile1}': {len(only_in_1)}")
        lines.append(f"  ➕ Only in '{profile2}': {len(only_in_2)}")
       
        # Status differences analysis
        if self.compare_status.isChecked():
            status_diff = 0
            for mod1 in mods1:
                for mod2 in mods2:
                    if mod1['name'] == mod2['name'] and mod1['enabled'] != mod2['enabled']:
                        status_diff += 1
            lines.append(f"  ⚠️  Status differences (enabled/disabled): {status_diff}")
       
        # Order differences analysis
        if self.compare_order.isChecked():
            order_diff = 0
            mods1_dict = {m['name']: m['order'] for m in mods1}
            mods2_dict = {m['name']: m['order'] for m in mods2}
            for name in common:
                if mods1_dict.get(name) != mods2_dict.get(name):
                    order_diff += 1
            lines.append(f"  🔄 Order differences: {order_diff}")
       
        # Plugins stats
        lines.append("\n" + "=" * 70)
        lines.append("🔌 PLUGINS:")
        lines.append("=" * 70)
       
        plugins1_names = {p['name'] for p in plugins1}
        plugins2_names = {p['name'] for p in plugins2}
        plugins1_enabled = sum(1 for p in plugins1 if p['enabled'])
        plugins2_enabled = sum(1 for p in plugins2 if p['enabled'])
        plugins1_disabled = len(plugins1) - plugins1_enabled
        plugins2_disabled = len(plugins2) - plugins2_enabled
       
        only_plugins_1 = plugins1_names - plugins2_names
        only_plugins_2 = plugins2_names - plugins1_names
        common_plugins = plugins1_names & plugins2_names
       
        lines.append(f"  Total plugins in profile 1: {len(plugins1)} (✅ {plugins1_enabled}, ❌ {plugins1_disabled})")
        lines.append(f"  Total plugins in profile 2: {len(plugins2)} (✅ {plugins2_enabled}, ❌ {plugins2_disabled})")
        lines.append(f"  ✅ Common plugins: {len(common_plugins)}")
        lines.append(f"  ➕ Only in '{profile1}': {len(only_plugins_1)}")
        lines.append(f"  ➕ Only in '{profile2}': {len(only_plugins_2)}")

        if self.compare_status.isChecked():
            plugin_status_diff = 0
            plugins1_dict = {p['name']: p for p in plugins1}
            plugins2_dict = {p['name']: p for p in plugins2}
            for name in common_plugins:
                if plugins1_dict[name]['enabled'] != plugins2_dict[name]['enabled']:
                    plugin_status_diff += 1
            lines.append(f"  ⚠️  Status differences (enabled/disabled): {plugin_status_diff}")
       
        # Plugin order differences
        if self.compare_order.isChecked():
            plugin_order_diff = 0
            plugins1_order = {p['name']: p['order'] for p in plugins1}
            plugins2_order = {p['name']: p['order'] for p in plugins2}
            for name in common_plugins:
                if plugins1_order.get(name) != plugins2_order.get(name):
                    plugin_order_diff += 1
            lines.append(f"  🔄 Load order differences: {plugin_order_diff}")

        lines.append("\n" + "=" * 70)
        lines.append("📦 ARCHIVES:")
        lines.append("=" * 70)

        archives1_set = set(archives1)
        archives2_set = set(archives2)
        only_archives_1 = archives1_set - archives2_set
        only_archives_2 = archives2_set - archives1_set
        common_archives = archives1_set & archives2_set

        lines.append(f"  Total archives in profile 1: {len(archives1)}")
        lines.append(f"  Total archives in profile 2: {len(archives2)}")
        lines.append(f"  ✅ Common archives: {len(common_archives)}")
        lines.append(f"  ➕ Only in '{profile1}': {len(only_archives_1)}")
        lines.append(f"  ➕ Only in '{profile2}': {len(only_archives_2)}")

        lines.append("\n" + "=" * 70)
        lines.append("⚙️ PROFILE SETTINGS:")
        lines.append("=" * 70)

        settings_keys = ["LocalSaves", "LocalSettings", "AutomaticArchiveInvalidation"]
        for key in settings_keys:
            v1 = settings1.get(key, False)
            v2 = settings2.get(key, False)
            mark1 = "✅ Yes" if v1 else "❌ No"
            mark2 = "✅ Yes" if v2 else "❌ No"
            diff_marker = " ⚠️" if v1 != v2 else ""
            lines.append(f"  {key}: {mark1} / {mark2}{diff_marker}")
       
        lines.append("\n" + "=" * 70)
       
        return "\n".join(lines)
   

    def populateComparisonTable(self, profile1, profile2, mods1, mods2, plugins1, plugins2):
        """Populate differences table"""
        self.compare_table.setRowCount(0)
       
        mods1_dict = {m['name']: m for m in mods1}
        mods2_dict = {m['name']: m for m in mods2}
       
        all_mods = sorted(set(mods1_dict.keys()) | set(mods2_dict.keys()))
       
        row = 0
        for mod_name in all_mods:
            mod1 = mods1_dict.get(mod_name)
            mod2 = mods2_dict.get(mod_name)
           
            # Determine difference type
            if mod1 and not mod2:
                diff_type = f"Only in {profile1}"
                status1 = "✅" if mod1['enabled'] else "❌"
                status2 = "-"
                color = QColor(255, 200, 200)  # Light red
            elif mod2 and not mod1:
                diff_type = f"Only in {profile2}"
                status1 = "-"
                status2 = "✅" if mod2['enabled'] else "❌"
                color = QColor(200, 255, 200)  # Light green
            elif mod1['enabled'] != mod2['enabled']:
                diff_type = "Different Status"
                status1 = "✅" if mod1['enabled'] else "❌"
                status2 = "✅" if mod2['enabled'] else "❌"
                color = QColor(255, 255, 200)  # Light yellow
            elif self.compare_order.isChecked() and mod1['order'] != mod2['order']:
                diff_type = "Different Order"
                status1 = f"✅ (#{mod1['order']})"
                status2 = f"✅ (#{mod2['order']})"
                color = QColor(200, 200, 255)  # Light blue
            else:
                # Identical - skip
                continue
           
            self.compare_table.insertRow(row)
           
            # Columns: Name, Profile1, Profile2, Diff Type
            name_item = QTableWidgetItem(mod_name)
            status1_item = QTableWidgetItem(status1)
            status2_item = QTableWidgetItem(status2)
            type_item = QTableWidgetItem(diff_type)
           
            # Color highlighting
            for item in [name_item, status1_item, status2_item, type_item]:
                item.setBackground(color)
           
            self.compare_table.setItem(row, 0, name_item)
            self.compare_table.setItem(row, 1, status1_item)
            self.compare_table.setItem(row, 2, status2_item)
            self.compare_table.setItem(row, 3, type_item)
           
            row += 1

        plugins1_dict = {p['name']: p for p in plugins1}
        plugins2_dict = {p['name']: p for p in plugins2}

        all_plugins = sorted(set(plugins1_dict.keys()) | set(plugins2_dict.keys()))

        for plugin_name in all_plugins:
            plugin1 = plugins1_dict.get(plugin_name)
            plugin2 = plugins2_dict.get(plugin_name)

            if plugin1 and not plugin2:
                status1 = "✅" if plugin1['enabled'] else "❌"
                status2 = "-"
                color = QColor(255, 200, 200)
            elif plugin2 and not plugin1:
                status1 = "-"
                status2 = "✅" if plugin2['enabled'] else "❌"
                color = QColor(200, 255, 200)
            elif plugin1['enabled'] != plugin2['enabled']:
                status1 = "✅" if plugin1['enabled'] else "❌"
                status2 = "✅" if plugin2['enabled'] else "❌"
                color = QColor(255, 255, 200)
            elif self.compare_order.isChecked() and plugin1['order'] != plugin2['order']:
                status1 = f"✅ (#{plugin1['order']})"
                status2 = f"✅ (#{plugin2['order']})"
                color = QColor(200, 200, 255)
            else:
                continue

            self.compare_table.insertRow(row)

            name_item = QTableWidgetItem(plugin_name)
            status1_item = QTableWidgetItem(status1)
            status2_item = QTableWidgetItem(status2)
            type_item = QTableWidgetItem("Plugin")

            for item in [name_item, status1_item, status2_item, type_item]:
                item.setBackground(color)

            self.compare_table.setItem(row, 0, name_item)
            self.compare_table.setItem(row, 1, status1_item)
            self.compare_table.setItem(row, 2, status2_item)
            self.compare_table.setItem(row, 3, type_item)

            row += 1
   

    def generateFullReport(self, profile1, profile2, mods1, mods2, plugins1, plugins2, archives1, archives2, settings1, settings2):
        """Generate full report"""
        lines = []
        lines.append("=" * 80)
        lines.append("📄 FULL PROFILE COMPARISON REPORT")
        lines.append("=" * 80)
        lines.append(f"\n📁 Profile 1: {profile1}")
        lines.append(f"📁 Profile 2: {profile2}")
        lines.append(f"📅 Comparison Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
       
        # Detailed list of mods only in profile 1
        mods1_names = {m['name'] for m in mods1}
        mods2_names = {m['name'] for m in mods2}
        only_in_1 = sorted(mods1_names - mods2_names)
       
        if only_in_1:
            lines.append("\n" + "=" * 80)
            lines.append(f"➕ MODS ONLY IN '{profile1}' ({len(only_in_1)}):")
            lines.append("=" * 80)
            for mod_name in only_in_1:
                mod = next(m for m in mods1 if m['name'] == mod_name)
                status = "✅ Enabled" if mod['enabled'] else "❌ Disabled"
                lines.append(f"  {status} - {mod_name}")
       
        # Detailed list of mods only in profile 2
        only_in_2 = sorted(mods2_names - mods1_names)
        if only_in_2:
            lines.append("\n" + "=" * 80)
            lines.append(f"➕ MODS ONLY IN '{profile2}' ({len(only_in_2)}):")
            lines.append("=" * 80)
            for mod_name in only_in_2:
                mod = next(m for m in mods2 if m['name'] == mod_name)
                status = "✅ Enabled" if mod['enabled'] else "❌ Disabled"
                lines.append(f"  {status} - {mod_name}")
       
        # Status differences
        if self.compare_status.isChecked():
            status_diffs = []
            mods1_dict = {m['name']: m for m in mods1}
            mods2_dict = {m['name']: m for m in mods2}
           
            for name in sorted(mods1_names & mods2_names):
                mod1 = mods1_dict[name]
                mod2 = mods2_dict[name]
                if mod1['enabled'] != mod2['enabled']:
                    status_diffs.append((name, mod1['enabled'], mod2['enabled']))
           
            if status_diffs:
                lines.append("\n" + "=" * 80)
                lines.append(f"⚠️  MOD STATUS DIFFERENCES ({len(status_diffs)}):")
                lines.append("=" * 80)
                for name, enabled1, enabled2 in status_diffs:
                    s1 = "✅ Enabled" if enabled1 else "❌ Disabled"
                    s2 = "✅ Enabled" if enabled2 else "❌ Disabled"
                    lines.append(f"  {name}:")
                    lines.append(f"    {profile1}: {s1}")
                    lines.append(f"    {profile2}: {s2}")
       
        # Plugin differences
        plugins1_names = {p['name'] for p in plugins1}
        plugins2_names = {p['name'] for p in plugins2}
        only_plugins_1 = sorted(plugins1_names - plugins2_names)
        only_plugins_2 = sorted(plugins2_names - plugins1_names)
        common_plugins = sorted(plugins1_names & plugins2_names)
       
        if only_plugins_1:
            lines.append("\n" + "=" * 80)
            lines.append(f"🔌 PLUGINS ONLY IN '{profile1}' ({len(only_plugins_1)}):")
            lines.append("=" * 80)
            plugins1_dict = {p['name']: p for p in plugins1}
            for plugin in only_plugins_1:
                status = "✅ Enabled" if plugins1_dict[plugin]['enabled'] else "❌ Disabled"
                lines.append(f"  {status} - {plugin}")
       
        if only_plugins_2:
            lines.append("\n" + "=" * 80)
            lines.append(f"🔌 PLUGINS ONLY IN '{profile2}' ({len(only_plugins_2)}):")
            lines.append("=" * 80)
            plugins2_dict = {p['name']: p for p in plugins2}
            for plugin in only_plugins_2:
                status = "✅ Enabled" if plugins2_dict[plugin]['enabled'] else "❌ Disabled"
                lines.append(f"  {status} - {plugin}")

        if self.compare_status.isChecked():
            plugin_status_diffs = []
            plugins1_dict = {p['name']: p for p in plugins1}
            plugins2_dict = {p['name']: p for p in plugins2}
            for name in common_plugins:
                p1 = plugins1_dict[name]
                p2 = plugins2_dict[name]
                if p1['enabled'] != p2['enabled']:
                    plugin_status_diffs.append((name, p1['enabled'], p2['enabled']))

            if plugin_status_diffs:
                lines.append("\n" + "=" * 80)
                lines.append(f"⚠️  PLUGIN STATE DIFFERENCES ({len(plugin_status_diffs)}):")
                lines.append("=" * 80)
                for name, enabled1, enabled2 in plugin_status_diffs:
                    s1 = "✅ Enabled" if enabled1 else "❌ Disabled"
                    s2 = "✅ Enabled" if enabled2 else "❌ Disabled"
                    lines.append(f"  {name}:")
                    lines.append(f"    {profile1}: {s1}")
                    lines.append(f"    {profile2}: {s2}")

        archives1_set = set(archives1)
        archives2_set = set(archives2)
        only_archives_1 = sorted(archives1_set - archives2_set)
        only_archives_2 = sorted(archives2_set - archives1_set)

        if only_archives_1:
            lines.append("\n" + "=" * 80)
            lines.append(f"📦 ARCHIVES ONLY IN '{profile1}' ({len(only_archives_1)}):")
            lines.append("=" * 80)
            for archive in only_archives_1:
                lines.append(f"  • {archive}")

        if only_archives_2:
            lines.append("\n" + "=" * 80)
            lines.append(f"📦 ARCHIVES ONLY IN '{profile2}' ({len(only_archives_2)}):")
            lines.append("=" * 80)
            for archive in only_archives_2:
                lines.append(f"  • {archive}")

        settings_keys = ["LocalSaves", "LocalSettings", "AutomaticArchiveInvalidation"]
        settings_diffs = []
        for key in settings_keys:
            v1 = settings1.get(key, False)
            v2 = settings2.get(key, False)
            if v1 != v2:
                settings_diffs.append((key, v1, v2))

        if settings_diffs:
            lines.append("\n" + "=" * 80)
            lines.append("⚙️ PROFILE SETTINGS DIFFERENCES:")
            lines.append("=" * 80)
            for key, v1, v2 in settings_diffs:
                s1 = "✅ Yes" if v1 else "❌ No"
                s2 = "✅ Yes" if v2 else "❌ No"
                lines.append(f"  {key}:")
                lines.append(f"    {profile1}: {s1}")
                lines.append(f"    {profile2}: {s2}")
       
        lines.append("\n" + "=" * 80)
        lines.append("END OF REPORT")
        lines.append("=" * 80)
       
        return "\n".join(lines)
   

    def readProfileFile(self, profile_path, filename):
        """Read profile file (simple list)"""
        filepath = os.path.join(profile_path, filename)
        if not os.path.exists(filepath):
            return []
       
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return [line.strip() for line in f.readlines() if line.strip()]
   

    def readProfileFileDetailed(self, profile_path, filename):
        """Read profile file with details (for modlist.txt)"""
        filepath = os.path.join(profile_path, filename)
        if not os.path.exists(filepath):
            return []
       
        mods = []
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for order, line in enumerate(f.readlines()):
                line = line.strip()
                if not line:
                    continue
               
                enabled = line.startswith('+')
                name = line[1:] if line[0] in ['+', '-'] else line
               
                mods.append({
                    'name': name,
                    'enabled': enabled,
                    'order': order
                })
       
        return mods

    def readPluginsFileDetailed(self, profile_path):
        filepath = os.path.join(profile_path, "plugins.txt")
        if not os.path.exists(filepath):
            return []

        plugins = []
        order = 0
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for raw_line in f.readlines():
                line = raw_line.strip()
                if not line or line.startswith('#'):
                    continue
                enabled = line.startswith('*')
                name = line[1:].strip() if enabled else line
                plugins.append({
                    'name': name,
                    'enabled': enabled,
                    'order': order
                })
                order += 1

        return plugins

    def getProfileSettings(self, profile_path):
        settings_file = os.path.join(profile_path, "settings.txt")
        settings = {
            "LocalSaves": False,
            "LocalSettings": False,
            "AutomaticArchiveInvalidation": False
        }
        if not os.path.exists(settings_file):
            return settings

        with open(settings_file, 'r', encoding='utf-8', errors='ignore') as f:
            for raw_line in f.readlines():
                line = raw_line.strip()
                if not line or line.startswith('#') or line.startswith(';'):
                    continue
                if line.startswith('[') and line.endswith(']'):
                    continue
                if '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().lower()
                if key in settings:
                    settings[key] = value in ('true', '1', 'yes', 'on')

        return settings
    
    # ==================== AUTOSAVE ====================
    
    def registerEventHandlers(self):
        """Register event handlers for history (WITHOUT autosave)"""
        try:
            mod_list = self.organizer.modList()
            plugin_list = self.organizer.pluginList()
            
            # Mod handlers - ONLY FOR HISTORY
            mod_list.onModStateChanged(self.onModStateChanged)
            mod_list.onModMoved(self.onModMoved)
            mod_list.onModInstalled(self.onModInstalled)
            mod_list.onModRemoved(self.onModRemoved)
            
            # Plugin handlers - ONLY FOR HISTORY
            plugin_list.onPluginStateChanged(self.onPluginStateChanged)
            plugin_list.onPluginMoved(self.onPluginMoved)
            
            print("PLUGIN: Event handlers registered")
        except Exception as e:
            print(f"PLUGIN: Error registering handlers: {e}")
    
    def onModStateChanged(self, mods_dict):
        """Mod state change handler - ONLY HISTORY"""
        try:
            current_profile = self.organizer.profileName()
            for mod_name, state in mods_dict.items():
                enabled = bool(state & mobase.ModState.ACTIVE)
                action = "enabled" if enabled else "disabled"
                self.addToHistory("Mods - enable/disable", mod_name, 
                                f"Mod {action}", current_profile)
        except Exception as e:
            print(f"PLUGIN: Error in onModStateChanged: {e}")
    
    def onModMoved(self, mod_name, old_priority, new_priority):
        """Mod move handler - ONLY HISTORY"""
        try:
            current_profile = self.organizer.profileName()
            self.addToHistory("Mods - move", mod_name,
                            f"Priority changed: {old_priority} → {new_priority}",
                            current_profile)
        except Exception as e:
            print(f"PLUGIN: Error in onModMoved: {e}")
    
    def onModInstalled(self, mod_interface):
        """New mod install handler - ONLY HISTORY"""
        try:
            current_profile = self.organizer.profileName()
            mod_name = mod_interface.name()
            
            # Check for separator
            if mod_interface.isSeparator():
                self.addToHistory("Separators - addition", mod_name,
                                "New separator added", current_profile)
            else:
                self.addToHistory("Mods - addition", mod_name,
                                "New mod installed", current_profile)
        except Exception as e:
            print(f"PLUGIN: Error in onModInstalled: {e}")
    
    def onModRemoved(self, mod_name):
        """Mod removal handler - ONLY HISTORY"""
        try:
            current_profile = self.organizer.profileName()
            self.addToHistory("Mods - removal", mod_name,
                            "Mod removed", current_profile)
        except Exception as e:
            print(f"PLUGIN: Error in onModRemoved: {e}")
    
    def onPluginStateChanged(self, plugins_dict):
        """Plugin state change handler - ONLY HISTORY"""
        try:
            current_profile = self.organizer.profileName()
            for plugin_name, state in plugins_dict.items():
                enabled = bool(state & mobase.PluginState.ACTIVE)
                action = "enabled" if enabled else "disabled"
                self.addToHistory("Plugins - enable/disable", plugin_name,
                                f"Plugin {action}", current_profile)
        except Exception as e:
            print(f"PLUGIN: Error in onPluginStateChanged: {e}")
    
    def onPluginMoved(self, plugin_name, old_priority, new_priority):
        """Plugin move handler - ONLY HISTORY"""
        try:
            current_profile = self.organizer.profileName()
            self.addToHistory("Plugins - move", plugin_name,
                            f"Load order changed: {old_priority} → {new_priority}",
                            current_profile)
        except Exception as e:
            print(f"PLUGIN: Error in onPluginMoved: {e}")
    
    def createAutosave(self):
        """Create automatic profile save (called on F8)"""
        try:
            current_profile = self.organizer.profileName()
            profiles_path = os.path.join(self.organizer.basePath(), "profiles")
            profile_path = os.path.join(profiles_path, current_profile)
            
            # Autosave name with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            autosave_name = f"{current_profile}_autosave_{timestamp}.zip"
            autosave_path = os.path.join(self.autosave_folder, autosave_name)
            
            # Create archive
            shutil.make_archive(
                autosave_path.replace('.zip', ''),
                'zip',
                profile_path
            )
            
            print(f"PLUGIN: Autosave created on F8: {autosave_name}")
            
            # Manage autosave count (delete old)
            self.cleanupAutosaves(current_profile)
            
            # Show notification (if window open)
            if self.isVisible():
                self.refreshAutosaves()
            
            return True
            
        except Exception as e:
            print(f"PLUGIN: Autosave creation error: {e}")
            return False
    
    def cleanupAutosaves(self, profile_name):
        """Delete old autosaves (keep only last max_autosaves)"""
        try:
            autosaves = []
            prefix = f"{profile_name}_autosave_"
            
            for filename in os.listdir(self.autosave_folder):
                if filename.startswith(prefix) and filename.endswith('.zip'):
                    filepath = os.path.join(self.autosave_folder, filename)
                    mtime = os.path.getmtime(filepath)
                    autosaves.append((filename, mtime, filepath))
            
            # Sort by time (oldest first)
            autosaves.sort(key=lambda x: x[1])
            
            # Delete old autosaves
            while len(autosaves) > self.max_autosaves:
                old_autosave = autosaves.pop(0)
                os.remove(old_autosave[2])
                print(f"PLUGIN: Deleted old autosave: {old_autosave[0]}")
                
        except Exception as e:
            print(f"PLUGIN: Autosave cleanup error: {e}")
    
    def refreshAutosaves(self):
        """Refresh autosaves list"""
        try:
            self.autosave_list.clear()
            
            if not os.path.exists(self.autosave_folder):
                return
            
            autosaves = []
            for filename in os.listdir(self.autosave_folder):
                if filename.endswith('.zip') and '_autosave_' in filename:
                    filepath = os.path.join(self.autosave_folder, filename)
                    mtime = os.path.getmtime(filepath)
                    size = os.path.getsize(filepath)
                    autosaves.append((filename, mtime, size))
            
            # Sort by time (newest on top)
            autosaves.sort(key=lambda x: x[1], reverse=True)
            
            for filename, mtime, size in autosaves:
                date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                size_mb = size / (1024 * 1024)
                item = QListWidgetItem(f"💾 {filename}")
                item.setData(Qt.ItemDataRole.UserRole, {
                    'filename': filename,
                    'mtime': mtime,
                    'size': size
                })
                item.setToolTip(f"Date: {date_str}\nSize: {size_mb:.2f} MB")
                self.autosave_list.addItem(item)
                
        except Exception as e:
            print(f"PLUGIN: Autosaves refresh error: {e}")
    
    def onAutosaveSelected(self):
        """Autosave selection handler"""
        selected = self.autosave_list.selectedItems()
        if not selected:
            self.autosave_info.clear()
            return
        
        data = selected[0].data(Qt.ItemDataRole.UserRole)
        filename = data['filename']
        mtime = data['mtime']
        size = data['size']
        
        date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        size_mb = size / (1024 * 1024)
        
        # Parse filename
        parts = filename.replace('.zip', '').split('_autosave_')
        profile_name = parts[0] if len(parts) >= 2 else "unknown"
        
        info = []
        info.append(f"💾 Autosave: {filename}")
        info.append(f"📁 Profile: {profile_name}")
        info.append(f"📅 Creation Date: {date_str}")
        info.append(f"💾 Size: {size_mb:.2f} MB")
        
        self.autosave_info.setText("\n".join(info))
    
    def createManualAutosave(self):
        """Manual autosave creation (or on F8)"""
        try:
            success = self.createAutosave()
            if success:
                QMessageBox.information(self, "Success", "Autosave created!")
                self.refreshAutosaves()
            else:
                QMessageBox.warning(self, "Error", "Failed to create autosave!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create autosave:\n{str(e)}")
    
    def restoreAutosave(self):
        """Restore from autosave"""
        selected = self.autosave_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "Select an autosave to restore!")
            return
       
        data = selected[0].data(Qt.ItemDataRole.UserRole)
        autosave_filename = data['filename']
        autosave_path = os.path.join(self.autosave_folder, autosave_filename)
       
        # Extract profile name
        parts = autosave_filename.replace('.zip', '').split('_autosave_')
        original_profile_name = parts[0] if len(parts) >= 2 else "restored_profile"
       
        reply = QMessageBox.question(
            self, "Restore Autosave",
            f"Restore profile '{original_profile_name}' from autosave?\n\n"
            "Current profile state will be overwritten!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
       
        if reply == QMessageBox.StandardButton.Yes:
            try:
                profiles_path = os.path.join(self.organizer.basePath(), "profiles")
                dest_path = os.path.join(profiles_path, original_profile_name)
               
                # Delete current profile
                if os.path.exists(dest_path):
                    shutil.rmtree(dest_path)
               
                # Unpack autosave
                shutil.unpack_archive(autosave_path, dest_path)
               
                QMessageBox.information(
                    self, "Success",
                    f"Profile '{original_profile_name}' restored from autosave!\n\n"
                    "Now updating MO2 state."
                )
               
                # Update plugin UI
                self.refreshProfiles()
               
                # Offer update options
                current_profile = self.organizer.profileName()
                if original_profile_name == current_profile:
                    # If restored is current, offer update
                    update_reply = QMessageBox.question(
                        self, "Update Modlist",
                        f"Changes in profile '{original_profile_name}' applied to files.\n\n"
                        "Choose MO2 update method:\n"
                        "• Yes: Restart MO2 (automatic, ~10 sec)\n"
                        "• No: Manual switch (go to another profile and back)",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                   
                    if update_reply == QMessageBox.StandardButton.Yes:
                        # Auto-restart MO2 on same profile
                        try:
                            mo2_exe = os.path.join(self.organizer.basePath(), "ModOrganizer.exe")
                            if os.path.exists(mo2_exe):
                                subprocess.Popen([mo2_exe, "-p", original_profile_name])
                                QApplication.quit()  # Close current MO2
                            else:
                                QMessageBox.warning(self, "Warning", "ModOrganizer.exe not found — restart manually.")
                        except Exception as e:
                            QMessageBox.critical(self, "Error", f"Failed to restart:\n{str(e)}")
                    else:
                        # Manual switch instructions
                        QMessageBox.information(
                            self, "Manual Update",
                            f"To apply changes:\n"
                            "1. In MO2, switch to any other profile (Profiles button).\n"
                            "2. Switch back to '{original_profile_name}'.\n"
                            "3. Modlist will update automatically.\n\n"
                            "Or close/reopen MO2."
                        )
               
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to restore:\n{str(e)}")    
                
    def deleteAutosave(self):
        """Delete autosave"""
        selected = self.autosave_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "Select an autosave to delete!")
            return
        
        data = selected[0].data(Qt.ItemDataRole.UserRole)
        autosave_filename = data['filename']
        autosave_path = os.path.join(self.autosave_folder, autosave_filename)
        
        reply = QMessageBox.question(
            self, "Delete Autosave",
            f"Delete autosave '{autosave_filename}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.remove(autosave_path)
                QMessageBox.information(self, "Success", "Autosave deleted!")
                self.refreshAutosaves()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete:\n{str(e)}")
    
    def clearAllAutosaves(self):
        """Delete all autosaves"""
        reply = QMessageBox.question(
            self, "Delete All Autosaves",
            "Delete ALL autosaves?\n\nThis action is irreversible!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                count = 0
                for filename in os.listdir(self.autosave_folder):
                    if filename.endswith('.zip'):
                        filepath = os.path.join(self.autosave_folder, filename)
                        os.remove(filepath)
                        count += 1
                
                QMessageBox.information(self, "Success", f"Deleted autosaves: {count}")
                self.refreshAutosaves()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete:\n{str(e)}")
    
    # ==================== HISTORY ====================
    
    def loadHistory(self):
        """Load history from file"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            print(f"PLUGIN: History load error: {e}")
            return []
    
    def saveHistory(self):
        """Save history to file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"PLUGIN: History save error: {e}")
    
    def addToHistory(self, action_type, object_name, details, profile_name):
        """Add entry to history"""
        try:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'profile': profile_name,
                'action_type': action_type,
                'object': object_name,
                'details': details
            }
            
            self.history_data.append(entry)
            self.saveHistory()
            
            print(f"PLUGIN: History: {action_type} - {object_name}")
        except Exception as e:
            print(f"PLUGIN: Add to history error: {e}")
    
    def refreshHistory(self):
        """Refresh history display"""
        self.filterHistory()
    
    def filterHistory(self):
        """Filter and display history"""
        try:
            self.history_table.setRowCount(0)
            
            filter_type = self.history_filter_combo.currentText()
            filter_profile = self.history_profile_combo.currentText()
            
            # Filter data
            filtered_data = []
            for entry in reversed(self.history_data):  # Newest on top
                # Type filter
                if filter_type != "All" and entry['action_type'] != filter_type:
                    continue
                
                # Profile filter
                if filter_profile != "All Profiles" and entry['profile'] != filter_profile:
                    continue
                
                filtered_data.append(entry)
            
            # Fill table
            for row, entry in enumerate(filtered_data):
                self.history_table.insertRow(row)
                
                # Format date
                timestamp = datetime.fromisoformat(entry['timestamp'])
                date_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                
                # Fill cells
                self.history_table.setItem(row, 0, QTableWidgetItem(date_str))
                self.history_table.setItem(row, 1, QTableWidgetItem(entry['profile']))
                self.history_table.setItem(row, 2, QTableWidgetItem(entry['action_type']))
                self.history_table.setItem(row, 3, QTableWidgetItem(entry['object']))
                self.history_table.setItem(row, 4, QTableWidgetItem(entry['details']))
                
                # Color by action type
                color = None
                if "removal" in entry['action_type'].lower():
                    color = QColor(255, 200, 200)  # Red
                elif "addition" in entry['action_type'].lower():
                    color = QColor(200, 255, 200)  # Green
                elif "move" in entry['action_type'].lower():
                    color = QColor(200, 200, 255)  # Blue
                elif "enable" in entry['action_type'].lower() or "disable" in entry['action_type'].lower():
                    color = QColor(255, 255, 200)  # Yellow
                
                if color:
                    for col in range(5):
                        item = self.history_table.item(row, col)
                        if item:
                            item.setBackground(color)
            
        except Exception as e:
            print(f"PLUGIN: History filter error: {e}")
    
    def exportHistory(self):
        """Export history to file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export History",
            f"history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON files (*.json);;Text files (*.txt)"
        )
        
        if filename:
            try:
                if filename.endswith('.txt'):
                    # Text export
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write("=" * 80 + "\n")
                        f.write("MO2 ACTION HISTORY\n")
                        f.write("=" * 80 + "\n\n")
                        
                        for entry in reversed(self.history_data):
                            timestamp = datetime.fromisoformat(entry['timestamp'])
                            f.write(f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}]\n")
                            f.write(f"Profile: {entry['profile']}\n")
                            f.write(f"Action: {entry['action_type']}\n")
                            f.write(f"Object: {entry['object']}\n")
                            f.write(f"Details: {entry['details']}\n")
                            f.write("-" * 80 + "\n\n")
                else:
                    # JSON export
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(self.history_data, f, ensure_ascii=False, indent=2)
                
                QMessageBox.information(self, "Success", f"History exported to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export:\n{str(e)}")
    
    def clearHistory(self):
        """Clear history"""
        reply = QMessageBox.question(
            self, "Clear History",
            "Delete ALL action history?\n\nThis action is irreversible!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.history_data = []
                self.saveHistory()
                QMessageBox.information(self, "Success", "History cleared!")
                self.refreshHistory()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear history:\n{str(e)}")

class AdvancedProfileManagerPlugin(mobase.IPluginTool):
    """Main plugin class"""
   
    def __init__(self):
        super().__init__()
        self._organizer = None
        self._dialog = None
        self._parentWidget = None
        self._shortcut = None
        self._autosave_shortcut = None
        self._toolbar_button = None
        self._retry_count = 0
        self._tools_menu = None
        print("PLUGIN: Initializing AdvancedProfileManagerPlugin")
   
    def init(self, organizer):
        """Plugin initialization"""
        print("PLUGIN: init() start")
        try:
            self._organizer = organizer
            print("PLUGIN: init() OK, organizer received")
            QTimer.singleShot(3000, self._setup_toolbar)
            return True
        except Exception as e:
            print(f"PLUGIN: Error in init(): {e}")
            return False
   
    def name(self):
        """Plugin name"""
        return "Advanced Profile Manager"
   
    def author(self):
        """Plugin author"""
        return "Claude"
   
    def description(self):
        """Plugin description"""
        return ("Powerful Pro profile manager: auto-switching, detailed comparison, "
                "auto-backups, F8 autosave, full action history. "
                "F7 - open window, F8 - create autosave")
   
    def version(self):
        """Plugin version"""
        return mobase.VersionInfo(3, 1, 0, 0)
   
    def isActive(self):
        """Check plugin activity"""
        try:
            return self._organizer.pluginSetting(self.name(), "enabled")
        except:
            return True
   
    def settings(self):
        """Plugin settings"""
        return [
            mobase.PluginSetting("enabled", "Enable plugin", True)
        ]
   
    def displayName(self):
        """Display name in MO2"""
        return "Advanced Profile Manager Pro"
   
    def tooltip(self):
        """Tooltip text"""
        return "F7 - open manager window | F8 - create profile autosave"
   
    def icon(self):
        """Plugin icon"""
        return QIcon()
   
    def setParentWidget(self, widget):
        """Set parent widget"""
        self._parentWidget = widget
        print("PLUGIN: setParentWidget called")

        self._setup_hotkeys(widget)

    def _setup_hotkeys(self, widget):
        if widget is None:
            return

        try:
            if self._shortcut is None:
                self._shortcut = QShortcut(QKeySequence("F7"), widget)
                self._shortcut.activated.connect(self.display)
                print("PLUGIN: F7 shortcut created successfully")
            self._shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)

            if self._autosave_shortcut is None:
                self._autosave_shortcut = QShortcut(QKeySequence("F8"), widget)
                self._autosave_shortcut.activated.connect(self.triggerAutosave)
                print("PLUGIN: F8 shortcut (autosave) created successfully")
            self._autosave_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)

        except Exception as e:
            print(f"PLUGIN: Hotkey creation error: {e}")
   
    def display(self):
        """Toggle dialog"""
        print("PLUGIN: display() toggle called")
        try:
            mw = self._main_window() or self._parentWidget
            dialog = self._dialog
            if dialog is not None:
                try:
                    if dialog.isVisible():
                        dialog.close()
                        print("PLUGIN: Dialog hidden")
                        return
                except RuntimeError:
                    self._dialog = None
                    dialog = None

            if dialog is None:
                parent = mw or self._parentWidget
                dialog = AdvancedProfileManagerDialog(self._organizer, parent)
                dialog.setWindowFlags(
                    Qt.WindowType.Tool
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.WindowStaysOnTopHint
                )
                dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
                dialog.destroyed.connect(self._on_dialog_destroyed)
                self._dialog = dialog
            else:
                try:
                    dialog.refreshProfiles()
                except RuntimeError:
                    self._dialog = None
                    dialog = None
                    parent = mw or self._parentWidget
                    dialog = AdvancedProfileManagerDialog(self._organizer, parent)
                    dialog.setWindowFlags(
                        Qt.WindowType.Tool
                        | Qt.WindowType.FramelessWindowHint
                        | Qt.WindowType.WindowStaysOnTopHint
                    )
                    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
                    dialog.destroyed.connect(self._on_dialog_destroyed)
                    self._dialog = dialog

            anchor = self._toolbar_button or mw or self._parentWidget
            if isinstance(anchor, QToolButton):
                global_pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
            else:
                global_pos = anchor.mapToGlobal(QPoint(0, 0)) if anchor is not None else QPoint(0, 0)

            dialog.move(global_pos)
            dialog.show()
            dialog.activateWindow()
            dialog.raise_()
            print("PLUGIN: Dialog opened as flyout")
        except Exception as e:
            print(f"PLUGIN: Window toggle error: {e}")

    def _on_dialog_destroyed(self, _obj=None):
        self._dialog = None
    
    def triggerAutosave(self):
        """F8 autosave trigger (works always, regardless of focus)"""
        print("PLUGIN: F8 pressed - creating autosave")
        try:
            # If dialog open, use its method
            if self._dialog is not None and self._dialog.isVisible():
                success = self._dialog.createAutosave()
                if success:
                    # Show notification via dialog
                    QMessageBox.information(
                        self._dialog, "Autosave",
                        "✅ Autosave created successfully!",
                        QMessageBox.StandardButton.Ok
                    )
                    self._dialog.refreshAutosaves()
            else:
                # Dialog closed - create autosave directly
                current_profile = self._organizer.profileName()
                profiles_path = os.path.join(self._organizer.basePath(), "profiles")
                profile_path = os.path.join(profiles_path, current_profile)
                autosave_folder = os.path.join(self._organizer.basePath(), "profiles", "_autosaves")
                os.makedirs(autosave_folder, exist_ok=True)
                
                # Create autosave
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                autosave_name = f"{current_profile}_autosave_{timestamp}.zip"
                autosave_path = os.path.join(autosave_folder, autosave_name)
                
                shutil.make_archive(
                    autosave_path.replace('.zip', ''),
                    'zip',
                    profile_path
                )
                
                print(f"PLUGIN: Autosave created (background mode): {autosave_name}")
                
                # Cleanup old autosaves
                self.cleanupAutosavesDirect(current_profile, autosave_folder)
                
                # Show system notification
                QMessageBox.information(
                    self._parentWidget, "Autosave",
                    f"✅ Autosave created successfully!\n\n"
                    f"Profile: {current_profile}\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}",
                    QMessageBox.StandardButton.Ok
                )
                
        except Exception as e:
            print(f"PLUGIN: F8 autosave error: {e}")
            QMessageBox.critical(
                self._parentWidget, "Autosave Error",
                f"Failed to create autosave:\n{str(e)}",
                QMessageBox.StandardButton.Ok
            )
    
    def cleanupAutosavesDirect(self, profile_name, autosave_folder, max_autosaves=5):
        """Helper method for old autosave cleanup"""
        try:
            autosaves = []
            prefix = f"{profile_name}_autosave_"
            
            for filename in os.listdir(autosave_folder):
                if filename.startswith(prefix) and filename.endswith('.zip'):
                    filepath = os.path.join(autosave_folder, filename)
                    mtime = os.path.getmtime(filepath)
                    autosaves.append((filename, mtime, filepath))
            
            # Sort by time (oldest first)
            autosaves.sort(key=lambda x: x[1])
            
            # Delete old autosaves
            while len(autosaves) > max_autosaves:
                old_autosave = autosaves.pop(0)
                os.remove(old_autosave[2])
                print(f"PLUGIN: Deleted old autosave: {old_autosave[0]}")
                
        except Exception as e:
            print(f"PLUGIN: Autosave cleanup error: {e}")

    def _main_window(self):
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMainWindow):
                return w
        return None

    def _normalize_text(self, text):
        return text.replace("&", "").replace("—", "-").replace("–", "-").strip().lower()

    def _menu_title_matches(self, menu):
        title = self._normalize_text(menu.title())
        return title in ("tool plugins", "плагины-программы")

    def _menu_has_plugin_action(self, menu):
        target = self._normalize_text(self.displayName())
        for a in menu.actions():
            if self._normalize_text(a.text()) == target:
                return True
        return False

    def _is_tools_menu(self, menu):
        if not menu:
            return False
        return self._menu_title_matches(menu) or self._menu_has_plugin_action(menu)

    def _find_menu(self, toolbar_action, toolbar):
        menu = toolbar_action.menu()
        if menu:
            return menu

        widget = toolbar.widgetForAction(toolbar_action)
        if isinstance(widget, QToolButton):
            da = widget.defaultAction()
            if da:
                menu = da.menu()
                if menu:
                    return menu
        return None

    def _find_tools_menu_in_window(self, mw):
        menus = mw.findChildren(QMenu)
        for menu in menus:
            if self._menu_title_matches(menu):
                return menu
        for menu in menus:
            if self._menu_has_plugin_action(menu):
                return menu
        return None

    def _setup_toolbar(self):
        mw = self._main_window()
        if not mw:
            self._retry_toolbar()
            return

        self._setup_hotkeys(mw)

        # Находим любой тулбар (обычно основной — первый подходящий)
        for tb in mw.findChildren(QToolBar):
            # Пытаемся найти меню Tools — нужно только для внутреннего состояния
            actions_list = tb.actions()
            tools_found = False

            for action in actions_list:
                menu = self._find_menu(action, tb)
                if self._is_tools_menu(menu):
                    self._tools_menu = menu  # сохраняем ссылку, если она тебе нужна дальше
                    tools_found = True
                    break

            # ─────────────── Вставка кнопки всегда в начало ───────────────
            btn = QToolButton(tb)
            btn.setToolTip("Advanced Profile Manager Pro")
            btn.setAutoRaise(True)
            btn.setText("🗃️")
            btn.clicked.connect(self.display)
            btn_font = QFont()
            btn_font.setPointSize(13)
            btn.setFont(btn_font)

            if actions_list:
                tb.insertWidget(actions_list[0], btn)     # ← всегда в самое начало
            else:
                tb.addWidget(btn)

            self._toolbar_button = btn
            return   # вышли после первой удачной вставки

        # Если вообще не нашли подходящий тулбар — можно оставить retry или лог
        self._retry_toolbar()


                    


        self._retry_toolbar()

    def _retry_toolbar(self):
        self._retry_count += 1
        if self._retry_count < 5:
            QTimer.singleShot(2000, self._setup_toolbar)

def createPlugin():
    """Create plugin instance"""
    return AdvancedProfileManagerPlugin()
