# -*- coding: utf-8 -*-

import json
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication
from .constants import APP_NAME, DEFAULT_FONT_SIZE
from .config_validator import ConfigValidator
from .interfaces import ISettingsManager

class SettingsManager(ISettingsManager):
    """設定管理を担当するクラス"""
    
    def __init__(self, parent=None):
        self.parent = parent
        self.settings = QSettings("MechaGodeh", APP_NAME)
    
    def load_window_settings(self):
        """ウィンドウ設定の読み込み"""
        geometry = self.settings.value("geometry")
        window_state = self.settings.value("windowState")
        splitter_state = self.settings.value("splitterState")
        
        return geometry, window_state, splitter_state
    
    def save_window_settings(self, main_window):
        """ウィンドウ設定の保存"""
        if main_window:
            self.settings.setValue("geometry", main_window.saveGeometry())
            self.settings.setValue("windowState", main_window.saveState())
            if hasattr(main_window, 'splitter'):
                self.settings.setValue("splitterState", main_window.splitter.saveState())
    
    def load_tab_settings(self):
        """タブ設定の読み込み"""
        open_tabs = self.settings.value("openTabs", [])
        current_tab_index = self.settings.value("currentTabIndex", 0, type=int)
        
        return open_tabs, current_tab_index
    
    def save_tab_settings(self, tab_widget):
        """タブ設定の保存"""
        if not tab_widget:
            return
            
        open_tabs = []
        for i in range(tab_widget.count() - 1):  # "+" タブを除く
            widget = tab_widget.widget(i)
            if hasattr(widget, 'file_path') and widget.file_path:
                open_tabs.append(widget.file_path)
        
        self.settings.setValue("openTabs", open_tabs)
        self.settings.setValue("currentTabIndex", tab_widget.currentIndex())
    
    def get_font_size(self):
        """フォントサイズの取得"""
        return self.settings.value("fontSize", DEFAULT_FONT_SIZE, type=int)
    
    def set_font_size(self, size):
        """フォントサイズの設定"""
        self.settings.setValue("fontSize", size)
    
    def get_auto_text_settings(self):
        """自動テキスト設定の取得"""
        return {
            'enabled': self.settings.value("autoText/enabled", False, type=bool),
            'text': self.settings.value("autoText/text", "", type=str),
            'hotkey': self.settings.value("autoText/hotkey", "ctrl+shift+v", type=str)
        }
    
    def set_auto_text_settings(self, enabled, text, hotkey):
        """自動テキスト設定の保存"""
        self.settings.setValue("autoText/enabled", enabled)
        self.settings.setValue("autoText/text", text)
        self.settings.setValue("autoText/hotkey", hotkey)
    
    def get_read_only_files(self):
        """読み取り専用ファイルリストの取得"""
        return set(self.settings.value("readOnlyFiles", [], type=list))
    
    def set_read_only_files(self, read_only_files):
        """読み取り専用ファイルリストの設定"""
        self.settings.setValue("readOnlyFiles", list(read_only_files))
    
    def get_theme_mode(self):
        """テーマモードの取得"""
        return self.settings.value("themeMode", "auto", type=str)
    
    def set_theme_mode(self, mode):
        """テーマモードの設定"""
        self.settings.setValue("themeMode", mode)
    
    def load_json_setting(self, key: str, schema_name: str, default_value=None):
        """
        安全なJSON設定読み込み（スキーマ検証付き）
        
        Args:
            key: 設定キー
            schema_name: スキーマ名 ('lastOpenedFiles' または 'tabOrder')
            default_value: デフォルト値（Noneの場合は自動設定）
            
        Returns:
            パース・検証済みのデータ、またはデフォルト値
        """
        if default_value is None:
            default_value = ConfigValidator.get_safe_default(schema_name)
        
        try:
            # 設定から JSON 文字列を取得
            json_str = self.settings.value(key, json.dumps(default_value), type=str)
            
            # スキーマ検証付きでパース
            is_valid, data, error_msg = ConfigValidator.validate_json_string(json_str, schema_name)
            
            if not is_valid:
                print(f"警告: {key} の設定が無効です - {error_msg}")
                print(f"デフォルト値を使用します: {default_value}")
                return default_value
            
            # ファイルパスのサニタイズ
            sanitized_data = ConfigValidator.sanitize_file_paths(data)
            
            return sanitized_data
            
        except Exception as e:
            print(f"エラー: {key} の読み込みに失敗しました - {e}")
            print(f"デフォルト値を使用します: {default_value}")
            return default_value
    
    def save_json_setting(self, key: str, data, schema_name: str):
        """
        安全なJSON設定保存（スキーマ検証付き）
        
        Args:
            key: 設定キー
            data: 保存するデータ
            schema_name: スキーマ名
            
        Returns:
            bool: 保存成功フラグ
        """
        try:
            # データのスキーマ検証
            is_valid, error_msg = ConfigValidator._validate_data(data, schema_name)
            if not is_valid:
                print(f"警告: {key} の保存データが無効です - {error_msg}")
                return False
            
            # JSON文字列に変換して保存
            json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
            self.settings.setValue(key, json_str)
            return True
            
        except Exception as e:
            print(f"エラー: {key} の保存に失敗しました - {e}")
            return False