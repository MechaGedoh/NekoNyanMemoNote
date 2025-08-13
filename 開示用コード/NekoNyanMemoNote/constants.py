# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path
from PyQt6.QtGui import QTextFormat

# --- アプリケーション設定 ---
APP_NAME = "NekoNyanMemoNote"
APP_VERSION = "v1.2.1"

# --- パス設定 ---

# リソースファイル（アイコンなど）の場所を決定
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # PyInstaller で onefile モードの場合
    RESOURCE_DIR = str(Path(sys._MEIPASS).resolve())
    print(f"DEBUG: Running as frozen (onefile). RESOURCE_DIR: {RESOURCE_DIR}")
elif getattr(sys, 'frozen', False):
    # PyInstaller で onedir モードの場合
    RESOURCE_DIR = str(Path(sys.executable).parent.resolve())
    print(f"DEBUG: Running as frozen (onedir). RESOURCE_DIR: {RESOURCE_DIR}")
else:
    # 通常のPythonスクリプトとして実行されている場合
    RESOURCE_DIR = str(Path(__file__).parent.resolve())
    print(f"DEBUG: Running as script. RESOURCE_DIR: {RESOURCE_DIR}")

# ユーザーデータ（PyMemoNoteData）の場所を決定
if getattr(sys, 'frozen', False):
    # PyInstallerなどで実行ファイル化されている場合
    APP_DATA_BASE_DIR = str(Path(sys.executable).parent.resolve())
    print(f"DEBUG: APP_DATA_BASE_DIR (frozen): {APP_DATA_BASE_DIR}")
else:
    # 通常のPythonスクリプトとして実行されている場合
    APP_DATA_BASE_DIR = str(Path(__file__).parent.resolve())
    print(f"DEBUG: APP_DATA_BASE_DIR (script): {APP_DATA_BASE_DIR}")

# --- 定数 ---
PLUS_TAB_PROPERTY = "_is_plus_tab"
DEFAULT_FONT_SIZE = 10
PREEDIT_PROPERTY_ID = QTextFormat.Property.UserProperty + 1
UNIQUE_KEY = f"{APP_NAME}_Instance_{os.path.expanduser('~')}"

# --- UI定数 ---
DEFAULT_WINDOW_WIDTH = 900
DEFAULT_WINDOW_HEIGHT = 700
DEFAULT_WINDOW_X = 100
DEFAULT_WINDOW_Y = 100
MAIN_LAYOUT_MARGIN = 5
MAIN_LAYOUT_SPACING = 5
FONT_BUTTON_SIZE = 20
FONT_LAYOUT_SPACING = 2
TIMER_INTERVAL_MS = 60000  # 1分
HOTKEY_DEBOUNCE_TIME = 0.3
CHAR_WRAP_WIDTH = 36  # 全角36文字分の幅
WINDOWS_API_TIMER_DELAY = 50
WINDOWS_API_RESTORE_DELAY = 100

# --- 機能フラグ ---
ENABLE_DEBUG_OUTPUT = False  # 本番環境では False に設定

# --- Windows API エラーコード ---
WINDOWS_API_ERROR_CODES = {
    0: "No error (success)",
    5: "ERROR_ACCESS_DENIED - アクセスが拒否されました",
    6: "ERROR_INVALID_HANDLE - ハンドルが無効です",
    87: "ERROR_INVALID_PARAMETER - パラメータが無効です",
    1400: "ERROR_INVALID_WINDOW_HANDLE - ウィンドウハンドルが無効です",
    1401: "ERROR_INVALID_MENU_HANDLE - メニューハンドルが無効です",
    1402: "ERROR_INVALID_CURSOR_HANDLE - カーソルハンドルが無効です",
    1403: "ERROR_INVALID_ACCEL_HANDLE - アクセラレータハンドルが無効です",
    1404: "ERROR_INVALID_HOOK_HANDLE - フックハンドルが無効です",
    1405: "ERROR_INVALID_DWP_HANDLE - DWPハンドルが無効です"
}
