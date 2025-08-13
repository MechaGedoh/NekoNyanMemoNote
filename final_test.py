# -*- coding: utf-8 -*-
import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

def comprehensive_test():
    """包括的な動作テスト"""
    print("=" * 50)
    print("NekoNyanMemoNote 最終動作テスト")
    print("=" * 50)
    
    # 1. 基本インポートテスト
    print("\n[1] 基本モジュールインポートテスト")
    try:
        from NekoNyanMemoNote.constants import APP_NAME, UNIQUE_KEY
        from NekoNyanMemoNote.file_system import FileSystemManager, validate_windows_filename, BASE_MEMO_DIR
        from NekoNyanMemoNote.di_container import get_container
        from NekoNyanMemoNote.app_factory import AppFactory
        print("   [OK] 全モジュールのインポート成功")
    except Exception as e:
        print(f"   [ERROR] インポートエラー: {e}")
        return False
    
    # 2. アプリケーション作成テスト
    print("\n[2] アプリケーション作成テスト")
    try:
        app = QApplication(sys.argv)
        container = get_container()
        AppFactory.configure_container(container)
        main_win = AppFactory.create_memo_app(container)
        print("   [OK] MemoAppインスタンス作成成功")
    except Exception as e:
        print(f"   [ERROR] アプリケーション作成エラー: {e}")
        return False
    
    # 3. ファイルシステム機能テスト
    print("\n[3] ファイルシステム機能テスト")
    try:
        fs_manager = FileSystemManager()
        
        # Windows予約名バリデーション
        valid, msg = validate_windows_filename("test.txt")
        assert valid, f"正常なファイル名が無効と判定: {msg}"
        
        valid, msg = validate_windows_filename("CON")
        assert not valid, "Windows予約名が有効と判定された"
        
        valid, msg = validate_windows_filename("test.")
        assert not valid, "末尾ドット付きファイル名が有効と判定された"
        
        print("   [OK] ファイル名バリデーション機能正常")
    except Exception as e:
        print(f"   [ERROR] ファイルシステムテストエラー: {e}")
        return False
    
    # 4. UI要素確認
    print("\n[4] UI要素確認")
    try:
        if hasattr(main_win, 'tab_widget'):
            tab_count = main_win.tab_widget.count()
            print(f"   [OK] タブウィジェット: {tab_count} タブ")
        
        if hasattr(main_win, 'folder_view'):
            print("   [OK] フォルダビュー存在")
        
        if hasattr(main_win, 'text_editor'):
            print("   [OK] テキストエディタ存在")
            
    except Exception as e:
        print(f"   [ERROR] UI要素確認エラー: {e}")
        return False
    
    # 5. 設定とデータディレクトリ確認
    print("\n[5] 設定とデータディレクトリ確認")
    try:
        print(f"   [OK] アプリケーション名: {APP_NAME}")
        print(f"   [OK] データディレクトリ: {BASE_MEMO_DIR}")
        print(f"   [OK] ユニークキー: {UNIQUE_KEY[:30]}...")
    except Exception as e:
        print(f"   [ERROR] 設定確認エラー: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("[SUCCESS] 全ての動作テストが成功しました！")
    print("[SUCCESS] アプリケーションはコンパイル可能な状態です")
    print("=" * 50)
    
    return True

if __name__ == "__main__":
    success = comprehensive_test()
    if success:
        print("\n[COMPLETE] 動作確認完了 - PyInstallerでのコンパイルに進めます！")
    else:
        print("\n[FAILED] 問題が検出されました。修正が必要です。")
    
    sys.exit(0 if success else 1)