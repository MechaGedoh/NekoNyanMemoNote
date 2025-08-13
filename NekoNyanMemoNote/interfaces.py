# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any, Tuple
from PyQt6.QtCore import QSettings

class ISettingsManager(ABC):
    """設定管理インターフェース"""
    
    @abstractmethod
    def load_window_settings(self) -> Tuple[Any, Any, Any]:
        """ウィンドウ設定の読み込み"""
        pass
    
    @abstractmethod
    def save_window_settings(self, main_window) -> None:
        """ウィンドウ設定の保存"""
        pass
    
    @abstractmethod
    def get_font_size(self) -> int:
        """フォントサイズの取得"""
        pass
    
    @abstractmethod
    def set_font_size(self, size: int) -> None:
        """フォントサイズの設定"""
        pass
    
    @abstractmethod
    def load_json_setting(self, key: str, schema_name: str, default_value=None) -> Any:
        """安全なJSON設定読み込み"""
        pass
    
    @abstractmethod
    def save_json_setting(self, key: str, data: Any, schema_name: str) -> bool:
        """安全なJSON設定保存"""
        pass


class IFileSystemManager(ABC):
    """ファイルシステム管理インターフェース"""
    
    @abstractmethod
    def create_new_folder(self, base_path: str, default_name: str = "新規フォルダ") -> Tuple[Optional[str], Optional[str]]:
        """新しいフォルダの作成"""
        pass
    
    @abstractmethod
    def create_new_memo(self, current_folder_path: str, default_name: str = "新規メモ") -> Optional[str]:
        """新しいメモファイルの作成"""
        pass
    
    @abstractmethod
    def load_memo_content(self, file_path: str, force_sync: bool = False) -> str:
        """メモ内容の読み込み（デフォルトは非同期）"""
        pass
    
    @abstractmethod
    def save_memo_content(self, file_path: str, content: str, force_sync: bool = False) -> bool:
        """メモ内容の保存（デフォルトは非同期）"""
        pass


class ITabManager(ABC):
    """タブ管理インターフェース"""
    
    @abstractmethod
    def create_tab_widget(self):
        """タブウィジェットの作成"""
        pass
    
    @abstractmethod
    def add_memo_tab(self, file_path: str, content: str = "") -> Any:
        """メモタブの追加"""
        pass
    
    @abstractmethod
    def close_tab(self, index: int) -> None:
        """タブを閉じる"""
        pass
    
    @abstractmethod
    def get_current_text_edit(self) -> Any:
        """現在のテキストエディットを取得"""
        pass


class IHotkeyManager(ABC):
    """ホットキー管理インターフェース"""
    
    @abstractmethod
    def start_hotkey_listener_global(self) -> None:
        """グローバルホットキーリスナーの開始"""
        pass
    
    @abstractmethod
    def stop_hotkey_listener(self) -> None:
        """ホットキーリスナーの停止"""
        pass
    
    @abstractmethod
    def update_auto_text_settings(self, enabled: bool, text: str, hotkey: str) -> None:
        """自動テキスト設定の更新"""
        pass


class IConfigValidator(ABC):
    """設定検証インターフェース"""
    
    @abstractmethod
    def validate_json_string(self, json_str: str, schema_name: str) -> Tuple[bool, Any, Optional[str]]:
        """JSON文字列の検証"""
        pass
    
    @abstractmethod
    def sanitize_file_paths(self, data: Any) -> Any:
        """ファイルパスのサニタイズ"""
        pass