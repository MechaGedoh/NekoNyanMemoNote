# -*- coding: utf-8 -*-

from .di_container import DIContainer
from .interfaces import ISettingsManager, IFileSystemManager, ITabManager, IHotkeyManager
from .settings_manager import SettingsManager
from .file_system import FileSystemManager
from .tab_manager import TabManager
from .hotkey_manager import HotkeyManager

class AppFactory:
    """アプリケーションファクトリ - DI設定とインスタンス作成を担当"""
    
    @staticmethod
    def configure_container(container: DIContainer) -> None:
        """DIコンテナの設定"""
        # インターフェースと実装をマッピング
        container.register_type(ISettingsManager, SettingsManager)
        container.register_type(IFileSystemManager, FileSystemManager)
        container.register_type(ITabManager, TabManager)
        container.register_type(IHotkeyManager, HotkeyManager)
    
    @staticmethod
    def create_memo_app(container: DIContainer):
        """MemoAppインスタンスの作成"""
        from .app import MemoApp
        
        # 最初にMemoAppのインスタンスを作成（デフォルト依存関係で）
        memo_app = MemoApp()
        
        # 作成後に依存関係を設定（循環参照を回避）
        memo_app.settings_manager = container.resolve(ISettingsManager)
        memo_app.fs_manager = container.resolve(IFileSystemManager)
        memo_app.tab_manager = container.resolve(ITabManager)  
        memo_app.hotkey_manager = container.resolve(IHotkeyManager)
        
        # 親子関係を設定
        if hasattr(memo_app.settings_manager, 'parent'):
            memo_app.settings_manager.parent = memo_app
        if hasattr(memo_app.fs_manager, 'parent'):
            memo_app.fs_manager.parent = memo_app
        if hasattr(memo_app.tab_manager, 'parent'):
            memo_app.tab_manager.parent = memo_app
        if hasattr(memo_app.hotkey_manager, 'parent'):
            memo_app.hotkey_manager.parent = memo_app
        
        # 後方互換性の設定
        memo_app.settings = memo_app.settings_manager.settings
        
        return memo_app