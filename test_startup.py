# -*- coding: utf-8 -*-
import sys
import time
from PyQt6.QtWidgets import QApplication
from NekoNyanMemoNote.app import MemoApp
from NekoNyanMemoNote.constants import APP_NAME, UNIQUE_KEY
from NekoNyanMemoNote.di_container import get_container
from NekoNyanMemoNote.app_factory import AppFactory

def main():
    print("=== Application Startup Test ===")
    
    # QApplication作成
    app = QApplication(sys.argv)
    print("[OK] QApplication created successfully")
    
    # DIコンテナの設定
    container = get_container()
    AppFactory.configure_container(container)
    print("[OK] DI container configured")
    
    # MemoApp作成
    main_win = AppFactory.create_memo_app(container)
    print("[OK] MemoApp instance created")
    
    # ウィンドウ表示
    main_win.show()
    print("[OK] Main window displayed")
    
    # 基本情報表示
    print(f"[INFO] Application: {APP_NAME}")
    print(f"[INFO] Unique Key: {UNIQUE_KEY[:40]}...")
    
    # タブ情報
    if hasattr(main_win, 'tab_widget'):
        tab_count = main_win.tab_widget.count()
        print(f"[INFO] Tab count: {tab_count}")
    
    # メモフォルダのチェック
    try:
        from NekoNyanMemoNote.file_system import BASE_MEMO_DIR
        import os
        if os.path.exists(BASE_MEMO_DIR):
            print(f"[OK] Memo directory exists: {BASE_MEMO_DIR}")
            folders = [f for f in os.listdir(BASE_MEMO_DIR) if os.path.isdir(os.path.join(BASE_MEMO_DIR, f))]
            print(f"[INFO] Available folders: {len(folders)}")
        else:
            print(f"[INFO] Memo directory will be created: {BASE_MEMO_DIR}")
    except Exception as e:
        print(f"[WARNING] Could not check memo directory: {e}")
    
    print("=== Test completed successfully ===")
    print("Application is ready for compilation!")
    
    # 短時間表示
    for i in range(3):
        QApplication.processEvents()
        time.sleep(1)
        print(f"Application running... {3-i}")
    
    print("Closing application...")
    return 0

if __name__ == "__main__":
    sys.exit(main())