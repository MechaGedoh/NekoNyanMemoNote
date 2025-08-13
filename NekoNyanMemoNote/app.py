# -*- coding: utf-8 -*- 

import sys
import os
import datetime
import json
import traceback
import platform
import ctypes
import time
import threading

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QSplitter, QTextEdit, QStatusBar, QLabel,
    QMenu, QMessageBox, QPushButton, QSizePolicy, QTreeView, QDialog
)
from PyQt6.QtGui import (
    QAction, QKeySequence, QShortcut, QIcon, QActionGroup, QTextCursor
)
from PyQt6.QtCore import (
    Qt, QDir, QTimer, QSettings, QPoint, QSize, QRect, pyqtSignal, QEvent
)

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

from .constants import (
    APP_NAME, APP_VERSION, DEFAULT_FONT_SIZE, PLUS_TAB_PROPERTY, RESOURCE_DIR,
    WINDOWS_API_ERROR_CODES, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_X, DEFAULT_WINDOW_Y, MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_SPACING,
    FONT_BUTTON_SIZE, FONT_LAYOUT_SPACING, TIMER_INTERVAL_MS, HOTKEY_DEBOUNCE_TIME,
    CHAR_WRAP_WIDTH, WINDOWS_API_TIMER_DELAY, WINDOWS_API_RESTORE_DELAY,
    ENABLE_DEBUG_OUTPUT
)
from .widgets import (
    MemoTextEdit, ReadOnlyFileSystemModel, CustomTreeView, CustomTabBar, AutoTextSettingsDialog, UpdateDebouncer
)
from .file_system import FileSystemManager, BASE_MEMO_DIR, safe_error_message, get_safe_path
from .settings_manager import SettingsManager
from .tab_manager import TabManager
from .hotkey_manager import HotkeyManager
from .interfaces import ISettingsManager, IFileSystemManager, ITabManager, IHotkeyManager

class MemoApp(QMainWindow):
    toggle_visibility_signal = pyqtSignal()

    def __init__(self, 
                 settings_manager: ISettingsManager = None,
                 file_system_manager: IFileSystemManager = None,
                 tab_manager: ITabManager = None,
                 hotkey_manager: IHotkeyManager = None):
        super().__init__()
        
        # 依存性注入 - インターフェースベース
        self.settings_manager = settings_manager or SettingsManager(self)
        self.fs_manager = file_system_manager or FileSystemManager(self)
        self.tab_manager = tab_manager or TabManager(self)
        self.hotkey_manager = hotkey_manager or HotkeyManager(self)
        
        # 後方互換性のためのプロパティ設定
        if hasattr(self.settings_manager, 'parent') and self.settings_manager.parent is None:
            self.settings_manager.parent = self
        if hasattr(self.tab_manager, 'parent') and self.tab_manager.parent is None:
            self.tab_manager.parent = self
        if hasattr(self.hotkey_manager, 'parent'):
            self.hotkey_manager.parent = self
        
        self.read_only_files = set()
        self.ignore_save = False
        self.settings = self.settings_manager.settings  # 後方互換性のため
        self._last_selected_normal_tab_index = 0
        self.last_opened_files = {}
        self.current_font_size = DEFAULT_FONT_SIZE
        self.current_tab_order = []
        self.local_server = None
        self.last_hotkey_press_time = 0
        self.hotkey_debounce_time = HOTKEY_DEBOUNCE_TIME
        self.memory_optimization_enabled = False
        self.inactive_tab_content = {}
        
        # DOM更新最適化のデバウンサー初期化
        self.footer_update_debouncer = UpdateDebouncer(delay_ms=100, parent=self)
        
        # 遅延読み込み機能の初期化
        self.lazy_load_enabled = True
        self.lazy_load_timer = QTimer(self)
        self.lazy_load_timer.setSingleShot(True)
        self.lazy_load_timer.timeout.connect(self._perform_lazy_load)
        self.pending_lazy_loads = set()
        self.lazy_load_delay = 500  # 500ms遅延

        self.auto_texts = self.settings.value("autoTexts", [
            "こんにちは", "ありがとう", "お疲れ様です", "よろしくお願いします",
            "承知しました", "了解しました", "確認しました", "検討します",
            "後ほど", "失礼します"
        ], type=list)

        self.auto_text_menu_visible = False
        self.auto_text_menu = None

        if not os.path.exists(BASE_MEMO_DIR):
            try:
                os.makedirs(BASE_MEMO_DIR)
            except OSError as e:
                QMessageBox.critical(self, "致命的なエラー", f"ベースディレクトリを作成できませんでした。\n{e}")
                sys.exit(1)

        self.init_ui()
        self.load_settings()
        self.apply_font_size_to_all_editors()
        self.setup_hotkeys()
        
        # ホットキーマネージャーのシグナル接続
        self.hotkey_manager.toggle_visibility_signal.connect(self._safe_toggle_window_visibility)
        self.hotkey_manager.auto_text_signal.connect(self._on_auto_text_hotkey)
        
        # ホットキーリスナー開始
        if PYNPUT_AVAILABLE:
            self.hotkey_manager.start_hotkey_listener_global()
        else:
            QMessageBox.warning(self, "警告", "pynputライブラリが見つからないため、\nシステムワイドホットキー機能は利用できません。")

        self.date_timer = QTimer(self)
        self.date_timer.timeout.connect(self.update_footer_date)
        self.date_timer.start(TIMER_INTERVAL_MS)
        self.update_footer_status()
        
        # アプリケーション終了時のシグナル接続（保険）
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.connect(self._on_about_to_quit)
        print("DEBUG: aboutToQuit シグナルに接続しました")
        
        # 強制的な終了処理タイマー（最後の手段）
        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.timeout.connect(self._force_cleanup_check)
        self.cleanup_timer.start(100)  # 100msごとにチェック（高頻度）
        self._cleanup_performed = False
        print("DEBUG: 強制クリーンアップタイマーを開始しました（100ms間隔）")
        
        # Python atexitでプロセス終了時の最終防衛線
        import atexit
        atexit.register(self._atexit_cleanup)
        print("DEBUG: atexit終了ハンドラーを登録しました")
        
        # 即座にFileIOWorkerスレッドを停止（QThreadエラー回避）
        QTimer.singleShot(1000, self._immediate_thread_cleanup)  # 1秒後に実行
        print("DEBUG: 即座スレッド停止タイマーを設定しました")

    def _immediate_thread_cleanup(self):
        """アプリ起動後すぐにFileIOWorkerスレッドを停止"""
        print("DEBUG: _immediate_thread_cleanup が呼ばれました")
        try:
            if hasattr(self, 'fs_manager') and self.fs_manager:
                if hasattr(self.fs_manager, 'worker_thread') and self.fs_manager.worker_thread:
                    if self.fs_manager.worker_thread.isRunning():
                        print("DEBUG: 即座停止 - MainFileIOWorkerThreadを停止中...")
                        # 即座にfinishedを発火してスレッドを停止
                        if hasattr(self.fs_manager, 'worker') and self.fs_manager.worker:
                            self.fs_manager.worker.finished.emit()
                        # 少し待ってから状態確認
                        QTimer.singleShot(100, self._check_thread_stopped)
                    else:
                        print("DEBUG: MainFileIOWorkerThreadは既に停止済み")
                else:
                    print("DEBUG: worker_threadが存在しません")
            else:
                print("DEBUG: fs_managerが存在しません")
        except Exception as e:
            print(f"DEBUG: _immediate_thread_cleanup error: {e}")

    def _check_thread_stopped(self):
        """スレッド停止確認"""
        try:
            if hasattr(self, 'fs_manager') and self.fs_manager:
                if hasattr(self.fs_manager, 'worker_thread') and self.fs_manager.worker_thread:
                    if self.fs_manager.worker_thread.isRunning():
                        print("DEBUG: スレッドがまだ動作中です")
                    else:
                        print("DEBUG: スレッドが正常に停止しました")
        except Exception as e:
            print(f"DEBUG: _check_thread_stopped error: {e}")

    def _atexit_cleanup(self):
        """Python atexit による最終防衛線"""
        print("DEBUG: _atexit_cleanup が呼ばれました（プロセス終了時）")
        try:
            # HotkeyWorkerThreadの強制終了
            if hasattr(self, 'hotkey_manager') and self.hotkey_manager:
                if hasattr(self.hotkey_manager, 'hotkey_worker') and self.hotkey_manager.hotkey_worker:
                    if self.hotkey_manager.hotkey_worker.isRunning():
                        print("DEBUG: atexit - HotkeyWorkerThreadを強制終了")
                        self.hotkey_manager.hotkey_worker.terminate()
                        self.hotkey_manager.hotkey_worker.wait(500)
                        print("DEBUG: atexit - HotkeyWorkerThread強制終了完了")
            
            # MainFileIOWorkerThreadの強制終了（念のため）
            if hasattr(self, 'fs_manager') and self.fs_manager:
                if hasattr(self.fs_manager, 'worker_thread') and self.fs_manager.worker_thread:
                    if self.fs_manager.worker_thread.isRunning():
                        print("DEBUG: atexit - MainFileIOWorkerThreadを強制終了")
                        # 最も直接的な方法で終了
                        if hasattr(self.fs_manager, 'worker') and self.fs_manager.worker:
                            self.fs_manager.worker.finished.emit()
                        self.fs_manager.worker_thread.terminate()
                        self.fs_manager.worker_thread.wait(500)
        except Exception as e:
            print(f"DEBUG: atexit cleanup error: {e}")

    def _on_about_to_quit(self):
        """アプリケーション終了前の処理（保険）"""
        print("DEBUG: _on_about_to_quit が呼ばれました")
        self.cleanup_resources()
    
    def _force_cleanup_check(self):
        """強制的なクリーンアップチェック（最後の手段）"""
        # より積極的な条件でクリーンアップをトリガー
        should_cleanup = False
        reason = ""
        
        # 条件1: ウィンドウが非表示
        if not self.isVisible():
            should_cleanup = True
            reason = "ウィンドウが非表示"
        
        # 条件2: アプリケーションが非アクティブかつMainFileIOWorkerThreadが動いている
        elif hasattr(self, 'fs_manager') and self.fs_manager and hasattr(self.fs_manager, 'worker_thread'):
            if self.fs_manager.worker_thread and self.fs_manager.worker_thread.isRunning():
                from PyQt6.QtWidgets import QApplication
                if QApplication.instance() and not QApplication.instance().activeWindow():
                    should_cleanup = True
                    reason = "アプリケーションが非アクティブでスレッドが動作中"
        
        if should_cleanup and not self._cleanup_performed:
            print(f"DEBUG: {reason}のため強制クリーンアップを実行")
            self._cleanup_performed = True
            self.cleanup_timer.stop()
            self.cleanup_resources()

    def setup_hotkeys(self):
        """ホットキーの設定"""
        self.insert_date_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        self.insert_date_shortcut.activated.connect(self.insert_date)
    
    def _on_auto_text_hotkey(self):
        """自動テキストホットキーが押された時の処理"""
        self.hotkey_manager.send_auto_text()

    def _setup_windows_api(self):
        """Windows API関連の設定"""
        if platform.system() == "Windows":
            def bring_to_front_windows_impl(self_ptr):
                try:
                    # Windows API が利用可能かチェック
                    if not hasattr(ctypes.windll, 'user32') or not hasattr(ctypes.windll, 'kernel32'):
                        print("    Windows API: user32.dll or kernel32.dll not available")
                        # フォールバック処理
                        self_ptr.raise_()
                        self_ptr.activateWindow()
                        return
                    
                    hwnd = self_ptr.winId()
                    if hwnd:
                        def deferred_set_foreground():
                            try:
                                hwnd_int = int(hwnd)
                                success = ctypes.windll.user32.SetForegroundWindow(hwnd_int)
                                if not success:
                                     last_error = ctypes.windll.kernel32.GetLastError()
                                     # Windows API エラーハンドリング強化
                                     error_msg = WINDOWS_API_ERROR_CODES.get(last_error, f"Unknown error code: {last_error}")
                                     print(f"    Windows API: SetForegroundWindow failed. {error_msg}")
                                     
                                     if last_error == 0 or last_error == 5:  # アクセス拒否の場合も代替手段を試行
                                        self_ptr.showMinimized()
                                        def _restore_and_activate():
                                            try:
                                                self_ptr.showNormal()
                                                self_ptr.raise_()
                                                # 再度SetForegroundWindowを試行
                                                retry_success = ctypes.windll.user32.SetForegroundWindow(hwnd_int)
                                                if not retry_success:
                                                    retry_error = ctypes.windll.kernel32.GetLastError()
                                                    print(f"    Windows API: SetForegroundWindow retry failed. Error: {retry_error}")
                                                if not self_ptr.isActiveWindow():
                                                    QApplication.setActiveWindow(self_ptr)
                                                    self_ptr.activateWindow()
                                            except Exception as e_restore:
                                                print(f"    Windows API: Error in _restore_and_activate: {e_restore}")
                                        QTimer.singleShot(WINDOWS_API_RESTORE_DELAY, _restore_and_activate)
                                        return
                                if success and not self_ptr.isActiveWindow():
                                    QApplication.setActiveWindow(self_ptr)
                                    self_ptr.activateWindow()
                            except OSError as e_os:
                                print(f"    Windows API (deferred): OS Error in deferred_set_foreground: {e_os}")
                                traceback.print_exc()
                            except ctypes.ArgumentError as e_arg:
                                print(f"    Windows API (deferred): Invalid argument error: {e_arg}")
                                traceback.print_exc()
                            except Exception as e_deferred_api:
                                print(f"    Windows API (deferred): Unexpected error in deferred_set_foreground: {e_deferred_api}")
                                traceback.print_exc()
                        QTimer.singleShot(WINDOWS_API_TIMER_DELAY, deferred_set_foreground)
                except OSError as e_os:
                    print(f"    Windows API: OS Error in bring_to_front_windows: {e_os}")
                    traceback.print_exc()
                except ctypes.ArgumentError as e_arg:
                    print(f"    Windows API: Invalid argument error: {e_arg}")
                    traceback.print_exc()
                except Exception as e_api:
                    print(f"    Windows API: Unexpected error in bring_to_front_windows: {e_api}")
                    traceback.print_exc()
            self.bring_to_front_windows = lambda: bring_to_front_windows_impl(self)
    
    def _setup_window_basic(self):
        """ウィンドウの基本設定"""
        self.setWindowTitle(f"{APP_NAME} - {APP_VERSION}")
        self.setGeometry(DEFAULT_WINDOW_X, DEFAULT_WINDOW_Y, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        
        # アイコン設定
        self._setup_window_icon()
    
    def _setup_main_layout(self):
        """メインレイアウトの設定"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN, MAIN_LAYOUT_MARGIN)
        main_layout.setSpacing(MAIN_LAYOUT_SPACING)
        return main_layout
    
    def _setup_window_icon(self):
        """ウィンドウアイコンの設定"""
        icon_filename = "favicon.ico"
        
        # アイコンの候補パスリスト
        icon_paths = [
            # 通常実行時のパス（プロジェクトルート）
            os.path.join(os.path.dirname(os.path.dirname(__file__)), icon_filename),
            # PyInstaller onefile モードのパス（sys._MEIPASS）
            os.path.join(RESOURCE_DIR, icon_filename),
            # 実行ファイルと同じディレクトリ（配布時）
            os.path.join(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(__file__))), icon_filename),
            # 現在のディレクトリ
            icon_filename,
        ]
        
        for icon_path in icon_paths:
            try:
                if os.path.exists(icon_path):
                    if ENABLE_DEBUG_OUTPUT:
                        print(f"DEBUG: アイコンファイルを発見: {icon_path}")
                    icon = QIcon(icon_path)
                    if not icon.isNull():
                        # ウィンドウアイコンを設定
                        self.setWindowIcon(icon)
                        # アプリケーション全体のアイコンも設定（タスクバー等用）
                        from PyQt6.QtWidgets import QApplication
                        QApplication.instance().setWindowIcon(icon)
                        if ENABLE_DEBUG_OUTPUT:
                            print(f"DEBUG: ウィンドウアイコン設定成功: {icon_path}")
                        return
                    else:
                        if ENABLE_DEBUG_OUTPUT:
                            print(f"DEBUG: アイコンファイルが無効: {icon_path}")
            except Exception as e:
                if ENABLE_DEBUG_OUTPUT:
                    print(f"DEBUG: アイコン設定エラー: {icon_path} - {e}")
        
        if ENABLE_DEBUG_OUTPUT:
            print("WARNING: アイコンファイルが見つかりませんでした")
    
    def _setup_tab_widget(self, main_layout):
        """タブウィジェットの設定"""
        # TabManagerを使用してタブウィジェットを作成
        self.tab_widget = self.tab_manager.create_tab_widget()
        
        # カスタム設定
        self.tab_widget.setTabsClosable(False)
        
        # コンテキストメニュー設定
        tab_bar = self.tab_widget.tabBar()
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self.show_tab_context_menu)
        self.tab_widget.tabBarDoubleClicked.connect(self.on_tab_double_clicked)
        
        # カスタム"+"ボタンの設定
        custom_tab_bar = self.tab_widget.tabBar()
        if hasattr(custom_tab_bar, 'plusTabClicked'):
            custom_tab_bar.plusTabClicked.connect(lambda: self.create_new_folder(use_default_on_empty=True, select_new_tab=True))
        
        main_layout.addWidget(self.tab_widget)

    def init_ui(self):
        """UI初期化のメインメソッド"""
        self.setStyleSheet("""
            QWidget {
                background-color: #282a36;
                color: #f8f8f2;
            }
            QMainWindow, QWidget {
                /* font-size: 10pt; - フォントサイズはプログラムで動的に設定 */
            }
            MemoTextEdit, QTextEdit, QTreeView {
                background-color: #21222c;
                color: #f8f8f2;
                border: 1px solid #44475a;
                selection-background-color: #8be9fd;
                selection-color: #282a36;
            }
            QTreeView {
                alternate-background-color: #242530;
                show-decoration-selected: 1;
                outline: none;
            }
            QTreeView::branch:selected {
                background-color: #6272a4;
            }
            QTreeView::branch:selected:active {
                background-color: #8be9fd;
            }
            QTreeView::item:selected {
                background-color: #6272a4;
                color: #ffffff;
                font-weight: bold;
            }
            QTreeView::item:selected:active {
                background-color: #8be9fd;
                color: #282a36;
                font-weight: bold;
            }
            QTreeView::item:hover {
                background-color: #50566b;
                color: #f8f8f2;
            }
            QTreeView::item:focus {
                outline: 2px solid #8be9fd;
            }
            QHeaderView::section {
                background-color: #44475a;
                color: #f8f8f2;
                padding: 4px;
                border: 1px solid #282a36;
            }
            QTabWidget::pane {
                border-top: 1px solid #44475a;
            }
            QTabBar::tab {
                background-color: #282a36;
                color: #bd93f9;
                border: 1px solid #21222c;
                border-bottom: none;
                padding: 8px 16px;
                margin-right: 1px;
            }
            QTabBar::tab:selected {
                background-color: #44475a;
                color: #f8f8f2;
            }
            QTabBar::tab:!selected:hover {
                background-color: #3a3c4a;
            }
            QPushButton {
                background-color: #44475a;
                color: #f8f8f2;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5a5c6d;
            }
            QPushButton:pressed {
                background-color: #3a3c4a;
            }
            QStatusBar {
                background-color: #21222c;
            }
            QStatusBar QLabel {
                color: #bd93f9;
                padding: 0 5px;
            }
            QStatusBar QPushButton {
                background-color: #44475a;
                color: #f8f8f2;
                border: none;
                padding: 2px 5px;
                border-radius: 3px;
                margin: 2px;
            }
            QStatusBar QPushButton:hover {
                background-color: #5a5c6d;
            }
            QStatusBar QPushButton:pressed {
                background-color: #3a3c4a;
            }
            QMenu {
                background-color: #21222c;
                color: #f8f8f2;
                border: 1px solid #44475a;
            }
            QMenu::item:selected {
                background-color: #44475a;
            }
            QSplitter::handle {
                background-color: #44475a;
                width: 1px;
            }
            QScrollBar:vertical {
                border: none;
                background: #21222c;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #44475a;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar:horizontal {
                border: none;
                background: #21222c;
                height: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:horizontal {
                background: #44475a;
                min-width: 20px;
                border-radius: 5px;
            }
        """)
        self._setup_windows_api()
        self._setup_window_basic()
        main_layout = self._setup_main_layout()
        self._setup_tab_widget(main_layout)
        self._setup_status_bar()
        self._setup_menus_and_buttons()
        self._setup_event_filter()
    
    def _setup_status_bar(self):
        # ステータスバーの設定
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # 日付ラベル
        self.status_label_date = QLabel()
        self.update_footer_date()
        self.status_bar.addWidget(self.status_label_date)
        
        # 情報ラベル
        self.status_label_wrap = QLabel("折り返し: ウィンドウ幅")
        self.status_bar.addWidget(self.status_label_wrap)
        self.status_label_cursor = QLabel("カーソル: -")
        self.status_bar.addWidget(self.status_label_cursor)
        self.status_label_chars = QLabel("文字数: -")
        self.status_bar.addWidget(self.status_label_chars)
        
        # スペーサー
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.status_bar.addWidget(spacer)
        
        # フォントサイズコントロール
        self._create_font_size_widget()
    
    def _create_font_size_widget(self):
        # フォントサイズ調整ウィジェットの作成
        font_size_widget = QWidget()
        font_size_layout = QHBoxLayout(font_size_widget)
        font_size_layout.setContentsMargins(0, 0, 0, 0)
        font_size_layout.setSpacing(FONT_LAYOUT_SPACING)
        
        # マイナスボタン
        font_decrease_button = QPushButton("-")
        font_decrease_button.setFixedSize(FONT_BUTTON_SIZE, FONT_BUTTON_SIZE)
        font_decrease_button.setToolTip("文字サイズを小さくする")
        font_decrease_button.clicked.connect(self.decrease_font_size)
        font_size_layout.addWidget(font_decrease_button)
        
        # サイズ表示ラベル
        self.font_size_label = QLabel(f"{self.current_font_size}pt")
        self.font_size_label.setToolTip("現在の文字サイズ")
        font_size_layout.addWidget(self.font_size_label)
        
        # プラスボタン
        font_increase_button = QPushButton("+")
        font_increase_button.setFixedSize(FONT_BUTTON_SIZE, FONT_BUTTON_SIZE)
        font_increase_button.setToolTip("文字サイズを大きくする")
        font_increase_button.clicked.connect(self.increase_font_size)
        font_size_layout.addWidget(font_increase_button)
        
        self.status_bar.addPermanentWidget(font_size_widget)
    
    def _setup_menus_and_buttons(self):
        # メニューとボタンの設定
        self._create_wrap_menu()
        self._create_auto_text_button()
        self._setup_shortcuts()
    
    def _create_wrap_menu(self):
        # 折り返し設定メニューの作成
        wrap_menu = QMenu("折り返し", self)
        wrap_group = QActionGroup(self)
        wrap_group.setExclusive(True)
        
        # 折り返さない
        no_wrap_action = QAction("折り返さない", self, checkable=True)
        no_wrap_action.triggered.connect(lambda: self.set_current_editor_wrap_mode(QTextEdit.LineWrapMode.NoWrap))
        wrap_group.addAction(no_wrap_action)
        wrap_menu.addAction(no_wrap_action)
        
        # 文字数で折り返し（36文字固定）
        char_wrap_action = QAction("全角36文字分で折り返す", self, checkable=True)
        char_wrap_action.triggered.connect(lambda: self.set_current_editor_wrap_mode(QTextEdit.LineWrapMode.FixedPixelWidth))
        wrap_group.addAction(char_wrap_action)
        wrap_menu.addAction(char_wrap_action)
        
        
        # ウィンドウ幅で折り返し（デフォルト）
        window_wrap_action = QAction("ウィンドウ幅で折り返す", self, checkable=True)
        window_wrap_action.triggered.connect(lambda: self.set_current_editor_wrap_mode(QTextEdit.LineWrapMode.WidgetWidth))
        wrap_group.addAction(window_wrap_action)
        wrap_menu.addAction(window_wrap_action)
        window_wrap_action.setChecked(True)
        
        
        # 折り返し設定ボタン
        wrap_button = QPushButton("折り返し設定")
        wrap_button.setObjectName("wrap_button")
        wrap_button.setMenu(wrap_menu)
        self.status_bar.addPermanentWidget(wrap_button)
    
    def _create_auto_text_button(self):
        # 自動挿入ボタンの作成
        settings_button = QPushButton("自動挿入")
        settings_button.setToolTip("自動入力テキスト設定")
        settings_button.clicked.connect(self.show_auto_text_settings)
        self.status_bar.addPermanentWidget(settings_button)
    
    def _setup_shortcuts(self):
        # ショートカットの設定
        self.auto_text_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        self.auto_text_shortcut.activated.connect(self.show_auto_text_menu)
    
    def _setup_event_filter(self):
        # イベントフィルターの設定
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if self.auto_text_menu_visible and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                if self.auto_text_menu:
                    self.auto_text_menu.close()
                    self.auto_text_menu_visible = False
                return True
            if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
                number = key - Qt.Key.Key_0
                if number == 0:
                    self.insert_auto_text(9)
                else:
                    self.insert_auto_text(number - 1)
                return True
            elif Qt.KeyboardModifier.KeypadModifier & event.modifiers() and Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
                number = key - Qt.Key.Key_0
                if number == 0:
                    self.insert_auto_text(9)
                else:
                    self.insert_auto_text(number - 1)
                return True
            return True
        return super().eventFilter(obj, event)

    def get_current_widgets(self, index=None):
        target_index = index if index is not None else self.tab_widget.currentIndex()
        if target_index < 0 or target_index >= self.tab_widget.count(): return None, None, None, None
        widget = self.tab_widget.widget(target_index)
        if isinstance(widget, QSplitter) and widget.count() == 2:
            tree_widget_container = widget.widget(0); editor = widget.widget(1)
            if tree_widget_container:
                tree = tree_widget_container.findChild(CustomTreeView)
                if tree and isinstance(editor, MemoTextEdit):
                    model = tree.model()
                    if isinstance(model, ReadOnlyFileSystemModel): return widget, model, tree, editor
        return None, None, None, None

    def closeEvent(self, event):
        print("DEBUG: closeEvent が呼ばれました")
        self.update_last_opened_file_for_current_tab()
        self.save_current_memo()
        self.save_settings()
        
        print("DEBUG: cleanup_resources() を呼び出し中...")
        # リソースクリーンアップを実行
        self.cleanup_resources()
        print("DEBUG: cleanup_resources() 完了")
        
        event.accept()
        print("DEBUG: closeEvent 完了")
    
    def cleanup_resources(self):
        """アプリケーション終了時のリソースクリーンアップ"""
        print("DEBUG: cleanup_resources() メソッドが呼ばれました")
        
        # 重複実行を防ぐ
        if hasattr(self, '_cleanup_performed') and self._cleanup_performed:
            print("DEBUG: クリーンアップは既に実行済みです")
            return
        
        self._cleanup_performed = True
        try:
            print("DEBUG: リソースクリーンアップを開始...")
            
            # HotkeyManagerを使用してホットキーリスナーを停止
            if hasattr(self, 'hotkey_manager') and self.hotkey_manager:
                try:
                    print("DEBUG: ホットキーマネージャーの停止中...")
                    self.hotkey_manager.stop_hotkey_listener()
                    # スレッドの停止を確実に待つため、追加の待機時間
                    QApplication.processEvents()  # イベント処理を強制実行
                    time.sleep(0.5)  # 待機時間を延長
                    print("DEBUG: ホットキーマネージャーが停止されました")
                except Exception as e:
                    print(f"ERROR: ホットキーマネージャー停止エラー: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("DEBUG: ホットキーマネージャーが存在しません")
            
            # ローカルサーバーを停止
            if hasattr(self, 'local_server') and self.local_server:
                print("DEBUG: ローカルサーバーを停止中...")
                self.local_server.close()
                print("DEBUG: ローカルサーバーが停止されました")
            
            # タイマーを停止
            if hasattr(self, 'date_timer') and self.date_timer:
                self.date_timer.stop()
            
            if hasattr(self, 'lazy_load_timer') and self.lazy_load_timer:
                self.lazy_load_timer.stop()
            
            # デバウンサーを停止
            if hasattr(self, 'footer_update_debouncer') and self.footer_update_debouncer:
                self.footer_update_debouncer.stop()
            
            # ファイルシステムマネージャーのクリーンアップ
            if hasattr(self, 'fs_manager') and self.fs_manager:
                try:
                    print("DEBUG: fs_manager.cleanup()を呼び出し中...")
                    self.fs_manager.cleanup()
                    print("DEBUG: fs_manager.cleanup()完了")
                except Exception as e:
                    print(f"Error cleaning up file system manager: {e}")
            else:
                print("DEBUG: fs_manager が存在しないか、None です")
            
            # 遅延読み込みの未処理タスクをクリア
            if hasattr(self, 'pending_lazy_loads'):
                self.pending_lazy_loads.clear()
            
            # メモリ最適化のキャッシュをクリア
            if hasattr(self, 'inactive_tab_content'):
                self.inactive_tab_content.clear()
            
            print("リソースクリーンアップ完了")
            
        except Exception as e:
            print(f"Error during resource cleanup: {e}")
            import traceback
            traceback.print_exc()

    def load_settings(self):
        try:
            geometry = self.settings.value("geometry")
            if geometry: self.restoreGeometry(geometry)
            state = self.settings.value("windowState")
            if state: self.restoreState(state)
            self.current_font_size = self.settings.value("fontSize", DEFAULT_FONT_SIZE, type=int)
            self.font_size_label.setText(f"{self.current_font_size}pt")
            read_only_paths = self.settings.value("readOnlyFiles", "", type=str)
            self.read_only_files = {os.path.normcase(os.path.abspath(p)) for p in filter(None, read_only_paths.split('||'))}
            # 安全なJSON設定読み込み（スキーマ検証付き）
            self.last_opened_files = self.settings_manager.load_json_setting(
                "lastOpenedFiles", "lastOpenedFiles", {}
            )
            self.saved_tab_order = self.settings_manager.load_json_setting(
                "tabOrder", "tabOrder", []
            )
            self.load_folders()
            last_tab_index = self.settings.value("lastTabIndex", 0, type=int)
            plus_tab_idx = self._find_plus_tab_index()
            valid_last_index = last_tab_index if plus_tab_idx == -1 or last_tab_index != plus_tab_idx else 0
            num_normal_tabs = self.tab_widget.count() - (1 if plus_tab_idx != -1 else 0)
            target_index = -1
            if 0 <= valid_last_index < num_normal_tabs: target_index = valid_last_index
            elif num_normal_tabs > 0: target_index = 0
            if target_index != -1: self.tab_widget.setCurrentIndex(target_index)
        except Exception as e:
            print(f"設定読み込みエラー: {e}")
            # より詳細なエラー情報をログ出力
            import traceback
            traceback.print_exc()
            
            # ユーザーには簡潔なメッセージを表示
            QMessageBox.warning(
                self,
                "設定読み込みエラー",
                "設定の読み込みに失敗しました。\n" \
                "デフォルト設定で起動します。\n\n" \
                "詳細はコンソールログをご確認ください。"
            )

    def save_settings(self):
        try:
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("windowState", self.saveState())
            self.settings.setValue("fontSize", self.current_font_size)
            self.settings.setValue("readOnlyFiles", "||".join(self.read_only_files))
            # 安全なJSON設定保存（スキーマ検証付き）
            self.settings_manager.save_json_setting(
                "lastOpenedFiles", self.last_opened_files, "lastOpenedFiles"
            )
            self.save_tab_order()
            self.settings_manager.save_json_setting(
                "tabOrder", self.current_tab_order, "tabOrder"
            )
            current_index = self.tab_widget.currentIndex()
            widget = self.tab_widget.widget(current_index) if 0 <= current_index < self.tab_widget.count() else None
            if widget and widget.property(PLUS_TAB_PROPERTY): self.settings.setValue("lastTabIndex", self._last_selected_normal_tab_index)
            elif current_index >= 0: self.settings.setValue("lastTabIndex", current_index)
            else: self.settings.setValue("lastTabIndex", 0)
            _, _, _, editor = self.get_current_widgets()
            if editor: self.settings.setValue("wrapMode", editor.lineWrapMode().value)
            if editor and editor.lineWrapMode() == QTextEdit.LineWrapMode.FixedPixelWidth: self.settings.setValue("wrapColumn", 36)
            elif editor: self.settings.setValue("wrapColumn", editor.lineWrapColumnOrWidth())
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"設定の保存中にエラーが発生しました。\n{e}")

    def _safe_toggle_window_visibility(self):
        print("DEBUG: _safe_toggle_window_visibility() called")
        self.toggle_window_visibility()

    def toggle_window_visibility(self):
        is_visible = self.isVisible()
        is_minimized = self.isMinimized()
        is_active = self.isActiveWindow()
        print(f"DEBUG: toggle_window_visibility - visible={is_visible}, minimized={is_minimized}, active={is_active}")

        if self.windowState() & Qt.WindowState.WindowMinimized or not is_visible:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QApplication.setActiveWindow(self)
            if platform.system() == "Windows" and hasattr(self, 'bring_to_front_windows') and not self.isActiveWindow():
                self.bring_to_front_windows()
        elif not is_active:
            self.setWindowState(Qt.WindowState.WindowNoState)
            self.showNormal()
            self.raise_()
            self.activateWindow()
            QApplication.setActiveWindow(self)
            if platform.system() == "Windows" and hasattr(self, 'bring_to_front_windows'):
                self.bring_to_front_windows()
        else:
            self.showMinimized()

    def handle_new_connection(self):
        socket = self.local_server.nextPendingConnection()
        if socket:
            socket.readyRead.connect(lambda: self._handle_socket_ready_read(socket))
            QTimer.singleShot(0, self.activate_window_from_external)

    def _handle_socket_ready_read(self, socket):
        try:
            data = socket.readAll()
            socket.disconnectFromServer()
        except Exception as e:
            print(f"Error reading from socket: {e}")

    def activate_window_from_external(self):
        self.showNormal()
        self.raise_()
        QApplication.setActiveWindow(self)

    def load_file_content(self, editor):
        """ファイル内容を読み込み（遅延読み込み対応）"""
        if not isinstance(editor, MemoTextEdit):
            return
            
        file_path = editor.file_path
        if not file_path or not os.path.isfile(file_path):
            return
            
        # 既に読み込み済みの場合はスキップ
        if editor.is_loaded:
            return
            
        # 遅延読み込みが有効な場合
        if self.lazy_load_enabled:
            self._schedule_lazy_load(file_path, editor)
        else:
            self._load_file_immediately(file_path, editor)
    
    def _schedule_lazy_load(self, file_path, editor):
        """遅延読み込みをスケジュール"""
        self.pending_lazy_loads.add((file_path, id(editor)))
        
        # タイマーを再開始
        self.lazy_load_timer.stop()
        self.lazy_load_timer.start(self.lazy_load_delay)
    
    def _perform_lazy_load(self):
        """蓄積された遅延読み込みを実行"""
        for file_path, editor_id in self.pending_lazy_loads.copy():
            editor = self._find_editor_by_id(editor_id)
            if editor and not editor.is_loaded:
                self._load_file_immediately(file_path, editor)
        
        self.pending_lazy_loads.clear()
    
    def _find_editor_by_id(self, editor_id):
        """エディタIDからエディタオブジェクトを検索"""
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QSplitter) and widget.count() > 1:
                editor = widget.widget(1)
                if isinstance(editor, MemoTextEdit) and id(editor) == editor_id:
                    return editor
        return None
    
    def _load_file_immediately(self, file_path, editor):
        """ファイルを即座に読み込み"""
        # ファイルサイズをチェック
        file_size = self.fs_manager.get_file_size(file_path)
        
        if file_size > 1024 * 1024:  # 1MB以上の場合はストリーミング読み込み
            self._load_file_streaming(file_path, editor)
        else:
            # 小さいファイルは非同期読み込み
            self.fs_manager.load_memo_content_async(
                file_path, 
                lambda content: self._on_content_loaded_immediate(editor, content)
            )
    
    def _load_file_streaming(self, file_path, editor):
        """大容量ファイルをストリーミングで読み込み"""
        # ストリーミング読み込み用のコールバック
        def on_chunk(chunk_content, current_pos, total_size):
            if current_pos == -1 and total_size == -1:
                # 完了時
                editor.setPlainText(chunk_content)
                editor.is_loaded = True
                editor.document().setModified(False)
                self.update_footer_status()
            else:
                # プログレス表示（必要に応じて）
                pass
        
        self.fs_manager.load_memo_content_streaming(file_path, on_chunk)
    
    def _on_content_loaded_immediate(self, editor, content):
        """非同期読み込み完了時の処理"""
        if content is not None and not editor.is_loaded:
            editor.setPlainText(content)
            editor.is_loaded = True
            editor.document().setModified(False)
            self.update_footer_status()

    def on_tab_double_clicked(self, index):
        widget = self.tab_widget.widget(index)
        if index >= 0 and widget and not widget.property(PLUS_TAB_PROPERTY):
            self.rename_folder(index)

    def show_tab_context_menu(self, position):
        menu = QMenu(self)
        tab_bar = self.tab_widget.tabBar()
        tab_index = tab_bar.tabAt(position)
        widget = self.tab_widget.widget(tab_index) if tab_index != -1 else None
        new_folder_action = QAction("新規フォルダを作成", self)
        new_folder_action.triggered.connect(lambda: self.create_new_folder(use_default_on_empty=True, select_new_tab=True))
        menu.addAction(new_folder_action)
        if tab_index != -1 and widget and not widget.property(PLUS_TAB_PROPERTY):
            menu.addSeparator()
            rename_action = QAction("フォルダ名を変更", self)
            rename_action.triggered.connect(lambda: self.rename_folder(tab_index))
            menu.addAction(rename_action)
            delete_action = QAction("フォルダを削除", self)
            delete_action.triggered.connect(lambda: self.delete_folder(tab_index))
            menu.addAction(delete_action)
        menu.exec(tab_bar.mapToGlobal(position))

    def on_file_tree_double_clicked(self, index):
        tree = self.sender()
        if not isinstance(tree, CustomTreeView): return
        model = tree.model()
        if not isinstance(model, ReadOnlyFileSystemModel): return
        if index.isValid():
            file_path = model.filePath(index)
            if not model.isDir(index):
                self.rename_memo(index, model)

    def on_file_tree_empty_area_double_clicked(self):
        self.create_new_memo()

    def on_file_selection_changed(self, selected, deselected):
        selection_model = self.sender()
        if not selection_model: return
        splitter, model, tree, editor = self.get_current_widgets()
        if not tree or tree.selectionModel() != selection_model: return
        self.save_current_memo()
        indexes = selected.indexes()
        if indexes:
            index = indexes[0]
            file_path = model.filePath(index)
            if not model.isDir(index):
                self.load_memo(file_path)
                self.update_last_opened_file(file_path)
            else:
                if editor and editor.file_path:
                    self.ignore_save = True
                    editor.clear()
                    editor.setReadOnly(True)
                    editor.file_path = None
                    self.update_footer_status()
                    self.ignore_save = False
                    self.clear_last_opened_file_for_current_tab()
        else:
            if editor and editor.file_path:
                self.ignore_save = True
                editor.clear()
                editor.setReadOnly(True)
                editor.file_path = None
                self.update_footer_status()
                self.ignore_save = False
                self.clear_last_opened_file_for_current_tab()

    def show_file_tree_context_menu(self, position):
        splitter, model, tree, editor = self.get_current_widgets()
        if not tree: return
        index = tree.indexAt(position)
        menu = QMenu(self)
        new_memo_action = QAction("新規メモを作成", self)
        new_memo_action.triggered.connect(self.create_new_memo)
        menu.addAction(new_memo_action)
        if index.isValid():
            file_path = model.filePath(index)
            is_dir = model.isDir(index)
            if not is_dir:
                menu.addSeparator()
                rename_action = QAction("メモ名を変更", self)
                rename_action.triggered.connect(lambda checked=False, idx=index, mdl=model: self.rename_memo(idx, mdl))
                menu.addAction(rename_action)
                delete_action = QAction("メモを削除", self)
                delete_action.triggered.connect(lambda checked=False, idx=index, mdl=model: self.delete_memo(idx, mdl))
                menu.addAction(delete_action)
                menu.addSeparator()
                norm_path = os.path.normcase(os.path.abspath(file_path))
                read_only_action = QAction("メモを編集不可にする", self, checkable=True)
                read_only_action.setChecked(norm_path in self.read_only_files)
                read_only_action.triggered.connect(lambda checked, path=file_path, mdl=model: self.toggle_read_only(path, checked, mdl))
                menu.addAction(read_only_action)
        menu.exec(tree.viewport().mapToGlobal(position))

    def get_current_folder_path(self):
        splitter, _, _, _ = self.get_current_widgets()
        return splitter.property("folder_path") if splitter else None

    def create_new_folder(self, default_name="新しいフォルダ", use_default_on_empty=False, select_new_tab=False):
        final_folder_name, new_folder_path = self.fs_manager.create_new_folder(default_name=default_name, use_default_on_empty=use_default_on_empty)
        if final_folder_name and new_folder_path:
            new_tab_index = self.add_folder_tab(final_folder_name, new_folder_path)
            if select_new_tab and new_tab_index is not None:
                self.tab_widget.setCurrentIndex(new_tab_index)
                self._last_selected_normal_tab_index = new_tab_index

    def create_new_memo(self):
        current_folder_path = self.get_current_folder_path()
        new_file_path = self.fs_manager.create_new_memo(current_folder_path)
        if new_file_path:
            _, model, tree, _ = self.get_current_widgets()
            if tree:
                QTimer.singleShot(200, lambda path=new_file_path, tr=tree: self.select_file_in_tree(path, tr))

    def rename_folder(self, tab_index):
        widget = self.tab_widget.widget(tab_index)
        if not widget or widget.property(PLUS_TAB_PROPERTY): return
        old_name = self.tab_widget.tabText(tab_index)
        splitter = widget
        if not isinstance(splitter, QSplitter): return
        old_folder_path = os.path.normcase(os.path.abspath(splitter.property("folder_path")))
        new_name, new_folder_path = self.fs_manager.rename_folder(old_folder_path, old_name)
        if new_name and new_folder_path:
            self.tab_widget.setTabText(tab_index, new_name)
            splitter.setProperty("folder_path", new_folder_path)
            if old_folder_path in self.last_opened_files:
                file_val = self.last_opened_files.pop(old_folder_path)
                if file_val and file_val.startswith(old_folder_path + os.sep):
                    new_file_val = new_folder_path + file_val[len(old_folder_path):]
                    self.last_opened_files[new_folder_path] = new_file_val
                else:
                    self.last_opened_files[new_folder_path] = file_val
            updated_read_only = set()
            for ro_path in self.read_only_files:
                if ro_path.startswith(old_folder_path + os.sep):
                    new_ro_path = new_folder_path + ro_path[len(old_folder_path):]
                    updated_read_only.add(new_ro_path)
                else:
                    updated_read_only.add(ro_path)
            self.read_only_files = updated_read_only
            if self.tab_widget.currentIndex() == tab_index:
                _, model, tree, editor = self.get_current_widgets(tab_index)
                if model and tree:
                    root_index = model.setRootPath(new_folder_path)
                    tree.setRootIndex(root_index)
                    if isinstance(model, ReadOnlyFileSystemModel):
                        model.read_only_files = self.read_only_files
                    if editor and editor.file_path and editor.file_path.startswith(old_folder_path + os.sep):
                        new_editor_path = new_folder_path + editor.file_path[len(old_folder_path):]
                        editor.file_path = new_editor_path
            self.save_tab_order()

    def delete_folder(self, tab_index):
        widget = self.tab_widget.widget(tab_index)
        if not widget or widget.property(PLUS_TAB_PROPERTY): return
        folder_name = self.tab_widget.tabText(tab_index)
        splitter = widget
        if not isinstance(splitter, QSplitter): return
        folder_path = os.path.normcase(os.path.abspath(splitter.property("folder_path")))
        if self.fs_manager.delete_folder(folder_path, folder_name):
            current_idx = self.tab_widget.currentIndex()
            removing_current = (current_idx == tab_index)
            index_to_select_after_remove = -1
            if removing_current:
                if self.tab_widget.count() > 2:
                    index_to_select_after_remove = max(0, current_idx - 1)
            elif current_idx > tab_index:
                index_to_select_after_remove = current_idx - 1
            else:
                index_to_select_after_remove = current_idx
            self.tab_widget.removeTab(tab_index)
            self.save_tab_order()
            plus_idx_after_remove = self._find_plus_tab_index()
            num_normal_tabs_after_remove = self.tab_widget.count() - (1 if plus_idx_after_remove != -1 else 0)
            if num_normal_tabs_after_remove == 0:
                self.create_new_folder(default_name="デフォルト", use_default_on_empty=True, select_new_tab=True)
            elif index_to_select_after_remove != -1:
                 if plus_idx_after_remove != -1 and index_to_select_after_remove >= plus_idx_after_remove:
                     index_to_select_after_remove = max(0, plus_idx_after_remove - 1)
                 if 0 <= index_to_select_after_remove < num_normal_tabs_after_remove:
                     self.tab_widget.setCurrentIndex(index_to_select_after_remove)
                 else:
                      if num_normal_tabs_after_remove > 0:
                          self.tab_widget.setCurrentIndex(0)
            else:
                 if num_normal_tabs_after_remove > 0:
                     self.tab_widget.setCurrentIndex(0)

    def select_file_in_tree(self, file_path, tree_view):
        if not tree_view: return
        model = tree_view.model()
        if not model: return
        norm_path = os.path.normcase(os.path.abspath(file_path))
        index = model.index(norm_path)
        if not index.isValid():
            index = model.index(file_path)
        if index.isValid():
            tree_view.setCurrentIndex(index)
            tree_view.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)
            actual_path = model.filePath(index)
            self.load_memo(actual_path)
            self.update_last_opened_file(actual_path)
        else:
            current_root = model.rootPath()
            if current_root:
                model.setRootPath("")
                model.setRootPath(current_root)
                QTimer.singleShot(100, lambda p=file_path, t=tree_view: self._select_file_in_tree_retry(p, t))

    def _select_file_in_tree_retry(self, file_path, tree_view):
        if not tree_view: return
        model = tree_view.model()
        if not model: return
        norm_path = os.path.normcase(os.path.abspath(file_path))
        index = model.index(norm_path)
        if not index.isValid(): index = model.index(file_path)
        if index.isValid():
            tree_view.setCurrentIndex(index)
            tree_view.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)
            actual_path = model.filePath(index)
            self.load_memo(actual_path)
            self.update_last_opened_file(actual_path)

    def rename_memo(self, index, model):
        if not index.isValid() or not model or model.isDir(index): return
        self.save_current_memo()
        old_file_path = model.filePath(index)
        old_name = model.fileName(index)
        new_file_path = self.fs_manager.rename_memo(old_file_path, old_name)
        if new_file_path:
            _, _, tree, editor = self.get_current_widgets()
            old_file_path_norm = os.path.normcase(os.path.abspath(old_file_path))
            if old_file_path_norm in self.read_only_files:
                self.read_only_files.discard(old_file_path_norm)
                self.read_only_files.add(new_file_path)
                if isinstance(model, ReadOnlyFileSystemModel):
                    model.read_only_files = self.read_only_files
            folder_path = os.path.normcase(os.path.abspath(os.path.dirname(old_file_path)))
            if folder_path in self.last_opened_files and self.last_opened_files[folder_path] == old_file_path_norm:
                self.last_opened_files[folder_path] = new_file_path
            if isinstance(model, ReadOnlyFileSystemModel):
                 model.update_item(new_file_path)
            current_root = model.rootPath()
            if current_root:
                model.setRootPath("")
                model.setRootPath(current_root)
            if editor and editor.file_path == old_file_path_norm:
                editor.file_path = new_file_path
            if tree:
                QTimer.singleShot(200, lambda path=new_file_path, tr=tree: self.select_file_in_tree(path, tr))

    def delete_memo(self, index, model):
        if not index.isValid() or not model or model.isDir(index): return
        file_path = model.filePath(index)
        file_name = model.fileName(index)
        if self.fs_manager.delete_memo(file_path, file_name):
            _, _, _, editor = self.get_current_widgets()
            file_path_norm = os.path.normcase(os.path.abspath(file_path))
            if editor and editor.file_path == file_path_norm:
                self.ignore_save = True
                editor.clear()
                editor.setReadOnly(True)
                editor.file_path = None
                self.update_footer_status()
                self.ignore_save = False
            self.read_only_files.discard(file_path_norm)
            folder_path_norm = os.path.dirname(file_path_norm)
            if folder_path_norm in self.last_opened_files and self.last_opened_files[folder_path_norm] == file_path_norm:
                del self.last_opened_files[folder_path_norm]
            current_root = model.rootPath()
            if current_root:
                model.setRootPath("")
                model.setRootPath(current_root)

    def toggle_read_only(self, file_path, read_only, model):
        norm_path = os.path.normcase(os.path.abspath(file_path))
        
        # 編集不可にする前に現在のエディタの内容を保存
        _, _, _, editor = self.get_current_widgets()
        if read_only and editor and editor.file_path == norm_path and not editor.isReadOnly():
            if editor.document().isModified():
                content = editor.toPlainText()
                
                def on_save_before_readonly(success):
                    """読み取り専用設定前の保存完了コールバック"""
                    if success:
                        editor.document().setModified(False)
                        if ENABLE_DEBUG_OUTPUT:
                            print(f"読み取り専用設定前の保存完了: {os.path.basename(norm_path)}")
                
                # 非同期保存を実行
                self.fs_manager.save_memo_content_async(norm_path, content, on_save_before_readonly)
        
        if read_only: self.read_only_files.add(norm_path)
        else: self.read_only_files.discard(norm_path)
        if isinstance(model, ReadOnlyFileSystemModel): 
            model.read_only_files = self.read_only_files
            model.update_item(file_path)
        if editor and editor.file_path == norm_path: 
            editor.setReadOnly(read_only)
            self.update_footer_status()

    def load_memo(self, file_path):
        """メモを読み込み（ストリーミング対応）"""
        _, _, _, editor = self.get_current_widgets()
        if not editor: 
            return
            
        norm_path = os.path.normcase(os.path.abspath(file_path))
        if not os.path.isfile(norm_path):
            QMessageBox.warning(self, "エラー", f"ファイルが見つかりません: {norm_path}")
            self.ignore_save = True
            editor.clear()
            editor.setReadOnly(True)
            editor.file_path = None
            self.update_footer_status()
            self.ignore_save = False
            folder_path = os.path.dirname(norm_path)
            if folder_path in self.last_opened_files and self.last_opened_files[folder_path] == norm_path:
                del self.last_opened_files[folder_path]
            return
            
        # ファイルサイズを確認
        file_size = self.fs_manager.get_file_size(norm_path)
        is_large_file = file_size > 1024 * 1024  # 1MB以上
        
        self.ignore_save = True
        
        # エディタの基本設定
        is_read_only = norm_path in self.read_only_files
        editor.file_path = norm_path
        editor.setReadOnly(is_read_only)
        
        if is_large_file:
            # 大容量ファイルはストリーミング読み込み
            self._load_memo_streaming(norm_path, editor)
        else:
            # 小容量ファイルは非同期読み込み
            self._load_memo_async(norm_path, editor)
    
    def _load_memo_streaming(self, file_path, editor):
        """大容量メモをストリーミング読み込み"""
        accumulated_content = []
        
        def on_chunk(chunk_content, current_pos, total_size):
            if current_pos == -1 and total_size == -1:
                # ストリーミング完了
                complete_content = ''.join(accumulated_content)
                editor.setPlainText(complete_content)
                editor.document().setModified(False)
                editor.moveCursor(QTextCursor.MoveOperation.Start)
                self.update_footer_status()
                editor.setFocus()
                self.ignore_save = False
            else:
                # チャンク受信中
                accumulated_content.append(chunk_content)
                # プログレス表示（オプション）
                if total_size > 0:
                    progress = (current_pos / total_size) * 100
                    self.status_label_chars.setText(f"読み込み中: {progress:.1f}%")
        
        self.fs_manager.load_memo_content_streaming(file_path, on_chunk)
    
    def _load_memo_async(self, file_path, editor):
        """小容量メモを非同期読み込み"""
        def on_content_loaded(content):
            if content is not None:
                editor.setPlainText(content)
                editor.document().setModified(False)
                editor.moveCursor(QTextCursor.MoveOperation.Start)
                self.update_footer_status()
                editor.setFocus()
            else:
                editor.clear()
                editor.setReadOnly(True)
                editor.file_path = None
                self.update_footer_status()
            self.ignore_save = False
        
        self.fs_manager.load_memo_content_async(file_path, on_content_loaded)

    def save_current_memo(self, index=None):
        _, _, _, editor = self.get_current_widgets(index)
        if not editor or self.ignore_save or not editor.file_path or editor.isReadOnly() or not editor.document().isModified(): 
            return
        
        file_path = editor.file_path
        content = editor.toPlainText()
        
        def on_content_saved(success):
            """保存完了時のコールバック"""
            if success:
                editor.document().setModified(False)
                if ENABLE_DEBUG_OUTPUT:
                    print(f"非同期保存完了: {os.path.basename(file_path)}")
        
        # 非同期保存を実行
        self.fs_manager.save_memo_content_async(file_path, content, on_content_saved)

    def insert_date(self):
        focused_widget = QApplication.focusWidget()
        if isinstance(focused_widget, MemoTextEdit) and not focused_widget.isReadOnly():
            today = datetime.date.today().strftime("%Y%m%d")
            date_string = f"_{today}_"
            focused_widget.textCursor().insertText(date_string)

    def calculate_char_width_in_pixels(self, editor, char_count=36):
        """現在のフォント設定に基づいて、指定文字数分のピクセル幅を計算する（確実に36文字で折り返すように大きめに設定）"""
        font_metrics = editor.fontMetrics()
        
        # より確実に36文字で折り返すため、大幅に余裕を持たせた計算に変更
        test_text = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"  # 46文字
        
        if len(test_text) >= char_count:
            # 実際に36文字のテキスト幅を測定
            actual_36_chars = test_text[:char_count]
            base_pixel_width = font_metrics.horizontalAdvance(actual_36_chars)
            
            # 29文字になってしまう問題を解決するため、大幅に余裕を持たせる
            # PyQt6のFixedPixelWidthが予想以上に早く折り返すため、30%の余裕を追加
            pixel_width = int(base_pixel_width * 1.30)
            
        else:
            # フォールバック：単一文字の最大幅を使用
            max_char_width = 0
            test_chars = ['あ', 'ア', '山', '■', '○', '１', 'Ａ', 'Ｗ', '漢']
            for char in test_chars:
                char_width = font_metrics.horizontalAdvance(char)
                max_char_width = max(max_char_width, char_width)
            
            # 最大文字幅 × 文字数で計算（30%の余裕を持たせる）
            pixel_width = int(max_char_width * char_count * 1.30)
        
        if ENABLE_DEBUG_OUTPUT:
            print(f"DEBUG: フォント「{editor.font().family()}」サイズ{editor.font().pointSize()}pt")
            if len(test_text) >= char_count:
                print(f"DEBUG: 36文字テキスト「{actual_36_chars[:20]}...」")
                print(f"DEBUG: 基本実測幅: {base_pixel_width}px → 余裕30%込み: {pixel_width}px")
                avg_per_char = pixel_width / char_count
                print(f"DEBUG: 1文字あたりの平均幅: {avg_per_char:.2f}px")
            else:
                print(f"DEBUG: フォールバック計算での幅: {pixel_width}px")
        
        return pixel_width

    def update_wrap_width_for_editor(self, editor):
        """指定されたエディタの折り返し幅を現在のフォントサイズに合わせて更新する"""
        if not editor or editor.lineWrapMode() != QTextEdit.LineWrapMode.FixedPixelWidth:
            return
        
        # 固定で36文字
        column_width = 36
        
        # フォントサイズに応じて再計算
        pixel_width = self.calculate_char_width_in_pixels(editor, column_width)
        editor.setLineWrapColumnOrWidth(pixel_width)
        
        if ENABLE_DEBUG_OUTPUT:
            print(f"DEBUG: 折り返し幅を更新: {column_width}文字 → {pixel_width}px")


    def set_current_editor_wrap_mode(self, mode, column_width=None):
        """エディタの折り返しモードを設定する"""
        _, _, _, editor = self.get_current_widgets()
        if not editor: return
        
        # 固定で36文字
        column_width = 36
        
        current_mode_text = "不明"
        if mode == QTextEdit.LineWrapMode.NoWrap:
            editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            current_mode_text = "折り返さない"
        elif mode == QTextEdit.LineWrapMode.FixedPixelWidth:
            editor.setLineWrapMode(QTextEdit.LineWrapMode.FixedPixelWidth)
            # フォントサイズに応じた動的なピクセル幅計算
            pixel_width = self.calculate_char_width_in_pixels(editor, column_width)
            editor.setLineWrapColumnOrWidth(pixel_width)
            current_mode_text = f"全角{column_width}文字分"
        else:
            editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            current_mode_text = "ウィンドウ幅"
            
        self.status_label_wrap.setText(f"折り返し: {current_mode_text}")
        
        # 設定を保存
        self.settings.setValue("wrapMode", mode.value)
        self.settings.setValue("wrapColumn", column_width)
            
        self.update_wrap_menu_state()

    def update_wrap_menu_state(self):
        _, _, _, editor = self.get_current_widgets()
        wrap_button = self.status_bar.findChild(QPushButton, "wrap_button")
        if not editor or not wrap_button: return
        mode = editor.lineWrapMode()
        wrap_menu = wrap_button.menu()
        if not wrap_menu: return
        actions = wrap_menu.actions()
        if len(actions) < 3: return
        actions[0].setChecked(mode == QTextEdit.LineWrapMode.NoWrap)
        actions[1].setChecked(mode == QTextEdit.LineWrapMode.FixedPixelWidth)
        actions[2].setChecked(mode == QTextEdit.LineWrapMode.WidgetWidth)

    def load_folders(self):
        self.tab_widget.clear()
        folder_paths = {}
        try:
            if not os.path.exists(BASE_MEMO_DIR):
                os.makedirs(BASE_MEMO_DIR, exist_ok=True)
            items = os.listdir(BASE_MEMO_DIR)
            for item in items:
                item_path = os.path.join(BASE_MEMO_DIR, item)
                if os.path.isdir(item_path):
                    norm_path = os.path.normcase(os.path.abspath(item_path))
                    folder_paths[norm_path] = item
            if not folder_paths:
                self.create_new_folder(default_name="デフォルト", use_default_on_empty=True, select_new_tab=False)
                self._add_plus_tab()
            else:
                ordered_paths = []
                if hasattr(self, 'saved_tab_order') and self.saved_tab_order:
                    for path in self.saved_tab_order:
                        if path in folder_paths:
                            ordered_paths.append(path)
                    remaining_paths = sorted([p for p in folder_paths.keys() if p not in ordered_paths])
                    ordered_paths.extend(remaining_paths)
                else:
                    ordered_paths = sorted(folder_paths.keys())
                for norm_path in ordered_paths:
                    name = folder_paths[norm_path]
                    self.add_folder_tab(name, norm_path, add_plus_tab_after=False)
                self._add_plus_tab()
                self.save_tab_order()
        except OSError as e:
            error_msg = f"フォルダの作成または読み込みに失敗しました: {e}"
            print(f"ERROR: {error_msg}")
            QMessageBox.critical(self, "クリティカルエラー", error_msg)
        except Exception as e:
            error_msg = f"フォルダの読み込み中に予期しないエラーが発生しました: {e}"
            print(f"ERROR: {error_msg}")
            traceback.print_exc()
            QMessageBox.critical(self, "クリティカルエラー", error_msg)
        
        # エラー処理後も適切な状態を保つ
        plus_idx = self._find_plus_tab_index()
        num_normal_tabs = self.tab_widget.count() - (1 if plus_idx != -1 else 0)
        if num_normal_tabs == 0:
             self.create_new_folder(default_name="デフォルト", use_default_on_empty=True, select_new_tab=True)

    def add_folder_tab(self, name, path, add_plus_tab_after=True):
        plus_tab_index = self._find_plus_tab_index()
        if plus_tab_index != -1: self.tab_widget.removeTab(plus_tab_index)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        norm_path = os.path.normcase(os.path.abspath(path))
        splitter.setProperty("folder_path", norm_path)
        left_column_widget = QWidget()
        left_layout = QVBoxLayout(left_column_widget)
        left_layout.setContentsMargins(0,0,0,0)
        file_model = ReadOnlyFileSystemModel(self.read_only_files)
        file_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.Files | QDir.Filter.Dirs)
        root_index = file_model.setRootPath(norm_path)
        file_tree = CustomTreeView()
        file_tree.setModel(file_model)
        file_tree.setRootIndex(root_index)
        file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        file_tree.customContextMenuRequested.connect(self.show_file_tree_context_menu)
        file_tree.doubleClicked.connect(self.on_file_tree_double_clicked)
        file_tree.emptyAreaDoubleClicked.connect(self.on_file_tree_empty_area_double_clicked)
        file_tree.selectionModel().selectionChanged.connect(self.on_file_selection_changed)
        file_tree.setHeaderHidden(True)
        for i in range(1, file_model.columnCount()): file_tree.hideColumn(i)
        left_layout.addWidget(file_tree)
        splitter.addWidget(left_column_widget)
        memo_edit = MemoTextEdit()
        self.apply_font_size(memo_edit)
        memo_edit.setReadOnly(True)
        memo_edit.textChanged.connect(self._schedule_footer_update)
        memo_edit.cursorPositionChanged.connect(self._schedule_footer_update)
        splitter.addWidget(memo_edit)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        insert_index = plus_tab_index if plus_tab_index != -1 else self.tab_widget.count()
        new_index = self.tab_widget.insertTab(insert_index, splitter, name)
        if add_plus_tab_after: self._add_plus_tab()
        self.save_tab_order()
        return new_index

    def _add_plus_tab(self):
        if self._find_plus_tab_index() == -1:
            plus_widget = QWidget()
            plus_widget.setProperty(PLUS_TAB_PROPERTY, True)
            plus_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            index = self.tab_widget.addTab(plus_widget, "+")
            self.tab_widget.setTabToolTip(index, "新しいフォルダ(タブ)を作成します")

    def _find_plus_tab_index(self):
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if widget and widget.property(PLUS_TAB_PROPERTY):
                return i
        return -1

    def _schedule_footer_update(self):
        """フッターステータス更新をスケジュール"""
        self.footer_update_debouncer.schedule_update("footer_status", 
                                                    lambda: self.update_footer_status())
    
    def update_footer_status(self):
        current_index = self.tab_widget.currentIndex()
        if current_index < 0 or current_index >= self.tab_widget.count():
            self.status_label_chars.setText("文字数: -")
            self.status_label_cursor.setText("カーソル: -")
            return
        widget = self.tab_widget.widget(current_index)
        if widget and widget.property(PLUS_TAB_PROPERTY):
            self.status_label_chars.setText("文字数: -")
            self.status_label_cursor.setText("カーソル: -")
            return
        _, _, _, editor = self.get_current_widgets()
        if editor and editor.file_path:
            if editor.isReadOnly():
                self.status_label_chars.setText("文字数: - (編集不可)")
                self.status_label_cursor.setText("カーソル: -")
            else:
                char_count = len(editor.toPlainText())
                self.status_label_chars.setText(f"文字数: {char_count}")
                cursor = editor.textCursor()
                line = cursor.blockNumber() + 1
                col = cursor.columnNumber() + 1
                self.status_label_cursor.setText(f"カーソル: {line}行 {col}桁")
        else:
            self.status_label_chars.setText("文字数: -")
            self.status_label_cursor.setText("カーソル: -")

    def update_footer_date(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        self.status_label_date.setText(now)

    def on_activate_toggle(self):
        self.toggle_visibility_signal.emit()

    def on_press(self, key):
        # 古いホットキー関連メソッド - HotkeyManagerに移行済み
        # Insertキーは HotkeyManager で処理される
        return True

    def on_release(self, key): 
        # 古いホットキー関連メソッド - HotkeyManagerに移行済み
        pass

    def increase_font_size(self):
        print(f"DEBUG: increase_font_size() called. Current: {self.current_font_size}")
        self.current_font_size = min(self.current_font_size + 1, 72)
        print(f"DEBUG: New font size: {self.current_font_size}")
        self.font_size_label.setText(f"{self.current_font_size}pt")
        self.apply_font_size_to_all_editors()
        self.settings.setValue("fontSize", self.current_font_size)

    def decrease_font_size(self):
        print(f"DEBUG: decrease_font_size() called. Current: {self.current_font_size}")
        self.current_font_size = max(self.current_font_size - 1, 6)
        print(f"DEBUG: New font size: {self.current_font_size}")
        self.font_size_label.setText(f"{self.current_font_size}pt")
        self.apply_font_size_to_all_editors()
        self.settings.setValue("fontSize", self.current_font_size)

    def apply_font_size(self, editor):
        if editor: 
            if ENABLE_DEBUG_OUTPUT:
                print(f"DEBUG: apply_font_size() - setting size {self.current_font_size} to editor")
            editor.set_font_size(self.current_font_size)
            # フォント変更後、折り返しモードが文字数固定の場合は再計算
            self.update_wrap_width_for_editor(editor)
        else:
            if ENABLE_DEBUG_OUTPUT:
                print(f"DEBUG: apply_font_size() - editor is None")

    def apply_font_size_to_all_editors(self):
        if ENABLE_DEBUG_OUTPUT:
            print(f"DEBUG: apply_font_size_to_all_editors() called with font_size={self.current_font_size}")
            print(f"DEBUG: Tab count: {self.tab_widget.count()}")
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QSplitter):
                editor = widget.widget(1)
                if isinstance(editor, MemoTextEdit):
                    if ENABLE_DEBUG_OUTPUT:
                        print(f"DEBUG: Applying font size to editor in tab {i}")
                    self.apply_font_size(editor)
                else:
                    if ENABLE_DEBUG_OUTPUT:
                        print(f"DEBUG: Tab {i} - widget(1) is not MemoTextEdit: {type(editor)}")
            else:
                if ENABLE_DEBUG_OUTPUT:
                    print(f"DEBUG: Tab {i} - widget is not QSplitter: {type(widget)}")

    def update_last_opened_file(self, file_path):
        current_folder_path = self.get_current_folder_path()
        if current_folder_path and file_path:
            norm_folder_path = os.path.normcase(os.path.abspath(current_folder_path))
            norm_file_path = os.path.normcase(os.path.abspath(file_path))
            if norm_file_path.startswith(norm_folder_path + os.sep):
                if self.last_opened_files.get(norm_folder_path) != norm_file_path:
                    self.last_opened_files[norm_folder_path] = norm_file_path

    def update_last_opened_file_for_current_tab(self):
        _, _, _, editor = self.get_current_widgets()
        if editor and editor.file_path: self.update_last_opened_file(editor.file_path)
        else: self.clear_last_opened_file_for_current_tab()

    def update_last_opened_file_for_tab(self, index):
         splitter, _, _, editor = self.get_current_widgets(index)
         if splitter:
             folder_path = splitter.property("folder_path")
             if folder_path:
                 norm_folder_path = os.path.normcase(os.path.abspath(folder_path))
                 if editor and editor.file_path:
                     norm_file_path = os.path.normcase(os.path.abspath(editor.file_path))
                     if norm_file_path.startswith(norm_folder_path + os.sep):
                         if self.last_opened_files.get(norm_folder_path) != norm_file_path:
                             self.last_opened_files[norm_folder_path] = norm_file_path
                     else:
                         if norm_folder_path in self.last_opened_files:
                             del self.last_opened_files[norm_folder_path]
                 else:
                     if norm_folder_path in self.last_opened_files:
                         del self.last_opened_files[norm_folder_path]

    def load_last_opened_file_for_tab(self, index):
        folder_path = self.get_folder_path_for_tab(index)
        if folder_path:
            norm_folder_path = os.path.normcase(os.path.abspath(folder_path))
            last_opened = self.last_opened_files.get(norm_folder_path)
            _, _, tree, editor = self.get_current_widgets(index)
            if last_opened and os.path.isfile(last_opened):
                if editor:
                    if tree:
                        QTimer.singleShot(0, lambda p=last_opened, t=tree: self.select_file_in_tree_only(p, t))
                    self.load_memo(last_opened)
            else:
                if last_opened:
                    if norm_folder_path in self.last_opened_files:
                        del self.last_opened_files[norm_folder_path]
                if editor and editor.file_path:
                    self.ignore_save = True
                    editor.clear()
                    editor.setReadOnly(True)
                    editor.file_path = None
                    self.update_footer_status()
                    self.ignore_save = False
                if tree:
                    tree.clearSelection()

    def select_file_in_tree_only(self, file_path, tree_view):
        if not tree_view: return
        model = tree_view.model()
        if not model: return
        norm_path = os.path.normcase(os.path.abspath(file_path))
        index = model.index(norm_path)
        if not index.isValid():
            index = model.index(file_path)
        if index.isValid():
            tree_view.setCurrentIndex(index)
            tree_view.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)
        else:
            current_root = model.rootPath()
            if current_root:
                model.setRootPath("")
                model.setRootPath(current_root)
                QTimer.singleShot(100, lambda p=file_path, t=tree_view: self._select_file_in_tree_only_retry(p, t))

    def _select_file_in_tree_only_retry(self, file_path, tree_view):
        if not tree_view: return
        model = tree_view.model()
        if not model: return
        norm_path = os.path.normcase(os.path.abspath(file_path))
        index = model.index(norm_path)
        if not index.isValid(): index = model.index(file_path)
        if index.isValid():
            tree_view.setCurrentIndex(index)
            tree_view.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)

    def clear_last_opened_file_for_current_tab(self):
        current_folder_path = self.get_current_folder_path()
        if current_folder_path:
            norm_folder_path = os.path.normcase(os.path.abspath(current_folder_path))
            if norm_folder_path in self.last_opened_files:
                del self.last_opened_files[norm_folder_path]

    def get_folder_path_for_tab(self, index):
        if 0 <= index < self.tab_widget.count():
            widget = self.tab_widget.widget(index)
            if isinstance(widget, QSplitter):
                return widget.property("folder_path")
        return None

    def save_tab_order(self, *args):
        new_order = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QSplitter):
                folder_path = widget.property("folder_path")
                if folder_path:
                    new_order.append(os.path.normcase(os.path.abspath(folder_path)))
        if self.current_tab_order != new_order:
            self.current_tab_order = new_order

    def show_auto_text_settings(self):
        dialog = AutoTextSettingsDialog(self)
        dialog.set_texts(self.auto_texts)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.auto_texts = dialog.get_texts()
            self.settings.setValue("autoTexts", self.auto_texts)

    def show_auto_text_menu(self):
        if self.auto_text_menu_visible: return
        self.auto_text_menu = QMenu(self)
        for i in range(1, 10):
            action = self.auto_text_menu.addAction(f"{i}: {self.auto_texts[i-1]}")
            action.triggered.connect(lambda checked, idx=i-1: self.insert_auto_text(idx))
        action = self.auto_text_menu.addAction(f"0: {self.auto_texts[9]}")
        action.triggered.connect(lambda checked, idx=9: self.insert_auto_text(idx))
        editor = self.get_current_widgets()[3]
        if editor:
            cursor_pos = editor.mapToGlobal(editor.cursorRect().bottomRight())
            self.auto_text_menu_visible = True
            self.auto_text_menu.aboutToHide.connect(self.on_menu_hidden)
            self.setFocus()
            QApplication.instance().installEventFilter(self)
            self.auto_text_menu.exec(cursor_pos)

    def on_menu_hidden(self):
        self.auto_text_menu_visible = False
        if self.auto_text_menu:
            self.auto_text_menu.aboutToHide.disconnect(self.on_menu_hidden)
            self.auto_text_menu = None
        QApplication.instance().removeEventFilter(self)

    def handle_number_key(self, number):
        if self.auto_text_menu_visible:
            if number == 0:
                self.insert_auto_text(9)
            else:
                self.insert_auto_text(number - 1)
            if self.auto_text_menu:
                self.auto_text_menu.close()

    def insert_auto_text(self, index):
        if 0 <= index < len(self.auto_texts):
            editor = self.get_current_widgets()[3]
            if editor and not editor.isReadOnly():
                editor.textCursor().insertText(self.auto_texts[index])
                if self.auto_text_menu:
                    self.auto_text_menu.close()
                self.auto_text_menu_visible = False
                editor.setFocus()

    def _deactivate_tab_memory(self, tab_widget):
        # タブのメモリを非アクティブ化(内容を退避してクリア)
        if not isinstance(tab_widget, QSplitter):
            return
            
        # エディタを取得
        editor = tab_widget.widget(1) if tab_widget.count() > 1 else None
        if not isinstance(editor, MemoTextEdit):
            return
            
        file_path = editor.file_path
        if not file_path or not editor.toPlainText():
            return
            
        # 現在の状態を保存
        content = editor.toPlainText()
        cursor_pos = editor.textCursor().position()
        scroll_pos = editor.verticalScrollBar().value()
        is_modified = editor.document().isModified()
        
        self.inactive_tab_content[file_path] = {
            'content': content,
            'cursor_pos': cursor_pos,
            'scroll_pos': scroll_pos,
            'modified': is_modified
        }
        
        # メモリ解放（内容をクリア）
        self.ignore_save = True
        editor.clear()
        editor.document().setModified(False)
        self.ignore_save = False
        
        print(f"DEBUG: メモリ解放 - {os.path.basename(file_path)} ({len(content)}文字)")
    
    def _activate_tab_memory(self, editor):
        # タブのメモリをアクティブ化(退避内容を復元)
        if not isinstance(editor, MemoTextEdit):
            return
            
        file_path = editor.file_path
        if not file_path or file_path not in self.inactive_tab_content:
            return
            
        # 保存された状態を復元
        saved_state = self.inactive_tab_content[file_path]
        
        self.ignore_save = True
        editor.setPlainText(saved_state['content'])
        
        # カーソル位置を復元
        cursor = editor.textCursor()
        cursor.setPosition(min(saved_state['cursor_pos'], len(saved_state['content'])))
        editor.setTextCursor(cursor)
        
        # スクロール位置を復元（少し遅延させて確実に適用）
        QTimer.singleShot(100, lambda: editor.verticalScrollBar().setValue(saved_state['scroll_pos']))
        
        # 変更状態を復元
        editor.document().setModified(saved_state['modified'])
        self.ignore_save = False
        
        # キャッシュから削除
        del self.inactive_tab_content[file_path]
        print(f"DEBUG: メモリ復元 - {os.path.basename(file_path)} ({len(saved_state['content'])}文字)")
    
    def get_memory_usage_info(self):
        # メモリ使用状況の情報を取得
        active_tabs = 0
        inactive_cached_tabs = len(self.inactive_tab_content)
        total_active_chars = 0
        total_cached_chars = 0
        
        # アクティブタブの文字数カウント
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QSplitter) and not widget.property(PLUS_TAB_PROPERTY):
                editor = widget.widget(1) if widget.count() > 1 else None
                if isinstance(editor, MemoTextEdit):
                    content = editor.toPlainText()
                    if content:
                        active_tabs += 1
                        total_active_chars += len(content)
        
        # キャッシュされたタブの文字数カウント
        for cached_data in self.inactive_tab_content.values():
            total_cached_chars += len(cached_data['content'])
        
        return {
            'active_tabs': active_tabs,
            'inactive_cached_tabs': inactive_cached_tabs,
            'total_tabs': active_tabs + inactive_cached_tabs,
            'total_active_chars': total_active_chars,
            'total_cached_chars': total_cached_chars,
            'optimization_enabled': self.memory_optimization_enabled,
            'estimated_memory_saved_mb': (total_cached_chars * 3) / (1024 * 1024)
        }
    
    def update_memory_status(self):
# メモリ使用状況をステータスバーに表示
        if not hasattr(self, 'status_label_memory'):
            return
            
        memory_info = self.get_memory_usage_info()
        
        if memory_info['optimization_enabled']:
            status_text = f"メモリ: {memory_info['active_tabs']}A/{memory_info['inactive_cached_tabs']}C"
            if memory_info['estimated_memory_saved_mb'] > 0.1:
                status_text += f" (-{memory_info['estimated_memory_saved_mb']:.1f}MB)"
        else:
            status_text = "メモリ: 最適化OFF"
            
        self.status_label_memory.setText(status_text)
