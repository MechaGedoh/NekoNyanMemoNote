# -*- coding: utf-8 -*-

import os
from PyQt6.QtWidgets import QTabWidget, QWidget, QMessageBox
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from .widgets import MemoTextEdit, CustomTabBar
from .constants import PLUS_TAB_PROPERTY
from .interfaces import ITabManager

class TabManager(ITabManager):
    """タブ管理を担当するクラス"""
    
    def __init__(self, parent=None):
        self.parent = parent
        self.tab_widget = None
        self._last_selected_normal_tab_index = 0
        
        # メモリ最適化のための非アクティブタブ管理
        self.inactive_tab_content = {}  # ファイルパス -> {"content": str, "cursor_pos": int, "scroll_pos": int}
        self.memory_optimization_enabled = True  # メモリ最適化の有効/無効フラグ
    
    def create_tab_widget(self):
        """タブウィジェットの作成"""
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabBar(CustomTabBar())
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        
        # タブ移動の監視
        if hasattr(self.parent, 'save_tab_order'):
            self.tab_widget.tabBar().tabMoved.connect(self.parent.save_tab_order)
        
        # "+" タブを追加
        self.add_plus_tab()
        
        return self.tab_widget
    
    def add_plus_tab(self):
        """+ タブの追加"""
        plus_widget = QWidget()
        plus_widget.setProperty(PLUS_TAB_PROPERTY, True)
        self.tab_widget.addTab(plus_widget, "+")
        from PyQt6.QtWidgets import QTabBar
        self.tab_widget.tabBar().setTabButton(
            self.tab_widget.count() - 1, 
            QTabBar.ButtonPosition.RightSide, 
            None
        )
    
    def add_memo_tab(self, file_path, content=""):
        """メモタブの追加"""
        if not file_path:
            return None
            
        # 既存タブをチェック
        for i in range(self.tab_widget.count() - 1):
            widget = self.tab_widget.widget(i)
            if hasattr(widget, 'file_path') and widget.file_path == file_path:
                self.tab_widget.setCurrentIndex(i)
                return widget
        
        # 新しいタブを作成
        text_edit = MemoTextEdit()
        text_edit.file_path = file_path
        text_edit.setPlainText(content)
        text_edit.document().setModified(False)
        
        # 現在のフォントサイズを適用
        if self.parent and hasattr(self.parent, 'current_font_size'):
            print(f"DEBUG: TabManager - applying font size {self.parent.current_font_size} to new text_edit")
            text_edit.set_font_size(self.parent.current_font_size)
        
        # タブタイトル設定
        tab_title = os.path.basename(file_path)
        insert_index = self.tab_widget.count() - 1  # "+" タブの前に挿入
        self.tab_widget.insertTab(insert_index, text_edit, tab_title)
        self.tab_widget.setCurrentIndex(insert_index)
        
        return text_edit
    
    def close_tab(self, index):
        """タブを閉じる"""
        if index >= self.tab_widget.count() - 1:  # "+" タブは閉じない
            return
            
        widget = self.tab_widget.widget(index)
        if not widget:
            return
            
        # メモリ最適化: 閉じるタブのキャッシュを削除
        if isinstance(widget, MemoTextEdit) and hasattr(widget, 'file_path'):
            file_path = widget.file_path
            if file_path and file_path in self.inactive_tab_content:
                del self.inactive_tab_content[file_path]
                print(f"DEBUG: タブクローズ - キャッシュ削除: {os.path.basename(file_path)}")
            
        # 変更があるかチェック
        if hasattr(widget, 'document') and widget.document().isModified():
            reply = QMessageBox.question(
                self.parent,
                "保存確認",
                f"'{self.tab_widget.tabText(index)}' に変更があります。\n保存しますか？",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Save:
                if hasattr(self.parent, 'save_current_memo'):
                    self.parent.save_current_memo()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        
        # タブを削除
        self.tab_widget.removeTab(index)
        
        # "+" タブ以外のタブがない場合は "+" タブを選択
        if self.tab_widget.count() == 1:
            self.tab_widget.setCurrentIndex(0)
    
    def on_tab_changed(self, index):
        """タブ変更時の処理（メモリ最適化機能付き）"""
        if index < 0:
            return
            
        # 前のタブを非アクティブ化（メモリ解放）
        if self.memory_optimization_enabled:
            self._deactivate_previous_tab()
            
        widget = self.tab_widget.widget(index)
        if not widget:
            return
            
        # "+" タブの場合
        if widget.property(PLUS_TAB_PROPERTY):
            if hasattr(self.parent, 'on_plus_tab_clicked'):
                self.parent.on_plus_tab_clicked()
            return
        
        # 通常のタブの場合
        self._last_selected_normal_tab_index = index
        
        # 現在のタブをアクティブ化（メモリ復元）
        if self.memory_optimization_enabled:
            self._activate_current_tab(widget)
        
        # ファイルパスをステータスバーに表示
        if hasattr(widget, 'file_path') and hasattr(self.parent, 'status_bar'):
            self.parent.status_bar.showMessage(widget.file_path)
        
        # 読み取り専用状態の更新
        if hasattr(self.parent, 'update_read_only_state'):
            self.parent.update_read_only_state()
    
    def get_current_text_edit(self):
        """現在のテキストエディットを取得"""
        current_widget = self.tab_widget.currentWidget()
        if current_widget and not current_widget.property(PLUS_TAB_PROPERTY):
            return current_widget
        return None
    
    def get_tab_count(self):
        """通常タブの数を取得（"+" タブを除く）"""
        return self.tab_widget.count() - 1 if self.tab_widget else 0
    
    def update_tab_title(self, index, title):
        """タブタイトルの更新"""
        if 0 <= index < self.tab_widget.count() - 1:
            self.tab_widget.setTabText(index, title)
    
    def find_tab_by_file_path(self, file_path):
        """ファイルパスでタブを検索"""
        for i in range(self.tab_widget.count() - 1):
            widget = self.tab_widget.widget(i)
            if hasattr(widget, 'file_path') and widget.file_path == file_path:
                return i
        return -1
    
    def close_all_tabs(self):
        """すべてのタブを閉じる"""
        while self.tab_widget.count() > 1:  # "+" タブを残す
            self.close_tab(0)
    
    def _deactivate_previous_tab(self):
        """前のアクティブタブを非アクティブ化（メモリ解放）"""
        if not hasattr(self, '_last_active_index'):
            return
            
        prev_index = self._last_active_index
        if 0 <= prev_index < self.tab_widget.count():
            prev_widget = self.tab_widget.widget(prev_index)
            
            # 前のタブが通常のタブ（+タブでない）場合のみ処理
            if prev_widget and not prev_widget.property(PLUS_TAB_PROPERTY):
                if isinstance(prev_widget, MemoTextEdit) and hasattr(prev_widget, 'file_path'):
                    file_path = prev_widget.file_path
                    if file_path:
                        # 現在の状態を保存
                        content = prev_widget.toPlainText()
                        cursor_pos = prev_widget.textCursor().position()
                        scroll_pos = prev_widget.verticalScrollBar().value()
                        
                        self.inactive_tab_content[file_path] = {
                            'content': content,
                            'cursor_pos': cursor_pos,
                            'scroll_pos': scroll_pos,
                            'modified': prev_widget.document().isModified()
                        }
                        
                        # メモリ解放（内容をクリア）
                        prev_widget.clear()
                        print(f"DEBUG: タブ非アクティブ化 - メモリ解放: {os.path.basename(file_path)}")
    
    def _activate_current_tab(self, widget):
        """現在のタブをアクティブ化（メモリ復元）"""
        if isinstance(widget, MemoTextEdit) and hasattr(widget, 'file_path'):
            file_path = widget.file_path
            if file_path and file_path in self.inactive_tab_content:
                # 保存された状態を復元
                saved_state = self.inactive_tab_content[file_path]
                
                widget.setPlainText(saved_state['content'])
                
                # カーソル位置を復元
                cursor = widget.textCursor()
                cursor.setPosition(saved_state['cursor_pos'])
                widget.setTextCursor(cursor)
                
                # スクロール位置を復元
                widget.verticalScrollBar().setValue(saved_state['scroll_pos'])
                
                # 変更状態を復元
                widget.document().setModified(saved_state['modified'])
                
                # キャッシュから削除
                del self.inactive_tab_content[file_path]
                print(f"DEBUG: タブアクティブ化 - メモリ復元: {os.path.basename(file_path)}")
        
        # 現在のインデックスを更新
        self._last_active_index = self.tab_widget.currentIndex()
    
    def get_memory_usage_info(self):
        """メモリ使用状況の情報を取得"""
        active_tabs = 0
        inactive_cached_tabs = len(self.inactive_tab_content)
        
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if widget and not widget.property(PLUS_TAB_PROPERTY):
                if isinstance(widget, MemoTextEdit) and widget.toPlainText():
                    active_tabs += 1
        
        return {
            'active_tabs': active_tabs,
            'inactive_cached_tabs': inactive_cached_tabs,
            'total_tabs': self.get_tab_count(),
            'optimization_enabled': self.memory_optimization_enabled
        }
    
    def toggle_memory_optimization(self):
        """メモリ最適化の有効/無効を切り替え"""
        self.memory_optimization_enabled = not self.memory_optimization_enabled
        
        if not self.memory_optimization_enabled:
            # 最適化を無効にする場合、すべてのキャッシュを復元
            self._restore_all_cached_content()
        
        return self.memory_optimization_enabled
    
    def _restore_all_cached_content(self):
        """キャッシュされたすべての内容を復元"""
        for file_path, saved_state in self.inactive_tab_content.items():
            tab_index = self.find_tab_by_file_path(file_path)
            if tab_index != -1:
                widget = self.tab_widget.widget(tab_index)
                if isinstance(widget, MemoTextEdit):
                    widget.setPlainText(saved_state['content'])
                    
                    cursor = widget.textCursor()
                    cursor.setPosition(saved_state['cursor_pos'])
                    widget.setTextCursor(cursor)
                    
                    widget.verticalScrollBar().setValue(saved_state['scroll_pos'])
                    widget.document().setModified(saved_state['modified'])
        
        # キャッシュをクリア
        self.inactive_tab_content.clear()
        print("DEBUG: メモリ最適化無効化 - 全キャッシュ復元完了")
