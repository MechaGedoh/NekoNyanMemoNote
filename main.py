# -*- coding: utf-8 -*-

import sys
import platform
import ctypes

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QSharedMemory, Qt
from PyQt6.QtGui import QIcon

try:
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    QTNETWORK_AVAILABLE = True
except ImportError:
    QTNETWORK_AVAILABLE = False

from NekoNyanMemoNote.app import MemoApp
from NekoNyanMemoNote.constants import APP_NAME, UNIQUE_KEY, RESOURCE_DIR, ENABLE_DEBUG_OUTPUT
from NekoNyanMemoNote.di_container import get_container
from NekoNyanMemoNote.app_factory import AppFactory

def setup_application_icon(app):
    """QApplication全体のアイコンを設定する"""
    import os
    import sys
    
    icon_filename = "favicon.ico"
    
    # PyInstallerの実行環境を考慮したパス設定
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller onefileモードの場合
        base_path = sys._MEIPASS
        if ENABLE_DEBUG_OUTPUT:
            print(f"DEBUG: PyInstaller onefile mode detected, base_path: {base_path}")
    elif getattr(sys, 'frozen', False):
        # PyInstaller onedirモードの場合
        base_path = os.path.dirname(sys.executable)
        if ENABLE_DEBUG_OUTPUT:
            print(f"DEBUG: PyInstaller onedir mode detected, base_path: {base_path}")
    else:
        # 通常のPython実行の場合
        base_path = os.path.dirname(__file__)
        if ENABLE_DEBUG_OUTPUT:
            print(f"DEBUG: Normal Python execution, base_path: {base_path}")
    
    icon_paths = [
        # PyInstaller対応の基本パス
        os.path.join(base_path, icon_filename),
        # RESOURCE_DIR使用
        os.path.join(RESOURCE_DIR, icon_filename),
        # 実行ファイルと同じディレクトリ（配布時）
        os.path.join(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__), icon_filename),
        # カレントディレクトリ
        os.path.join(os.getcwd(), icon_filename),
        # 絶対パス指定
        icon_filename,
    ]
    
    if ENABLE_DEBUG_OUTPUT:
        print(f"DEBUG: アイコンファイル検索パス: {icon_paths}")
    
    for icon_path in icon_paths:
        try:
            if ENABLE_DEBUG_OUTPUT:
                print(f"DEBUG: アイコンパスをチェック中: {icon_path}")
            if os.path.exists(icon_path):
                if ENABLE_DEBUG_OUTPUT:
                    print(f"DEBUG: アイコンファイルを発見: {icon_path}")
                icon = QIcon(icon_path)
                if not icon.isNull():
                    app.setWindowIcon(icon)
                    if ENABLE_DEBUG_OUTPUT:
                        print(f"DEBUG: アプリケーションアイコン設定成功: {icon_path}")
                    return True
                else:
                    if ENABLE_DEBUG_OUTPUT:
                        print(f"DEBUG: アイコンファイルが無効: {icon_path}")
            else:
                if ENABLE_DEBUG_OUTPUT:
                    print(f"DEBUG: アイコンファイルが存在しない: {icon_path}")
        except Exception as e:
            if ENABLE_DEBUG_OUTPUT:
                print(f"DEBUG: アイコン設定エラー {icon_path}: {e}")
    
    if ENABLE_DEBUG_OUTPUT:
        print("DEBUG: アプリケーションアイコンが見つかりませんでした")
    return False

def main():
    try:
        print(f"DEBUG: Starting {APP_NAME} {sys.argv}")
        
        # Ensure proper High-DPI handling on PyQt6
        try:
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
        except Exception:
            pass  # Fallback silently if attributes are unavailable

        if platform.system() == "Windows":
            try:
                # Windows API: フォアグラウンドウィンドウの設定を許可
                result = ctypes.windll.user32.AllowSetForegroundWindow(-1)
                if not result:
                    last_error = ctypes.windll.kernel32.GetLastError()
                    print(f"WARNING: AllowSetForegroundWindow failed. Error code: {last_error}")
            except OSError as e:
                print(f"ERROR: Failed to load Windows API function: {e}")
            except Exception as e:
                print(f"ERROR: Unexpected error in AllowSetForegroundWindow: {e}")

        print("DEBUG: Creating QApplication")
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        print("DEBUG: QApplication created successfully")
        
        # アプリケーション全体のアイコンを設定
        setup_application_icon(app)

        if QTNETWORK_AVAILABLE:
            print("DEBUG: QtNetwork available, checking for existing instance")
            shared_memory = QSharedMemory(UNIQUE_KEY)
            should_create_new_instance = True
            if shared_memory.attach(QSharedMemory.AccessMode.ReadOnly):
                print("DEBUG: Found existing instance, attempting to connect")
                socket = QLocalSocket()
                socket.connectToServer(UNIQUE_KEY)
                if socket.waitForConnected(500):
                    socket.write(b'activate')
                    socket.waitForBytesWritten(500)
                    socket.disconnectFromServer()
                    print("DEBUG: Successfully activated existing instance")
                    sys.exit(0)
                else:
                    # Stale lock recovery: detach and continue to launch a new instance
                    warn_msg = (
                        f"既に起動している {APP_NAME} に接続できませんでした。\n"
                        f"({socket.errorString()})\n\n古いロックを解放して再起動します。"
                    )
                    try:
                        QMessageBox.warning(None, "起動警告", warn_msg)
                    except Exception:
                        # If GUI not ready, continue silently
                        print(f"WARNING: {warn_msg}")
                    try:
                        shared_memory.detach()
                    except Exception:
                        pass
                    try:
                        QLocalServer.removeServer(UNIQUE_KEY)
                    except Exception:
                        pass
                    should_create_new_instance = True
            else:
                print("DEBUG: No existing instance found.")
                should_create_new_instance = True

            if should_create_new_instance:
                print("DEBUG: Creating new instance")
                if not shared_memory.create(1):
                    error_msg = f"共有メモリの作成に失敗しました。\n{shared_memory.errorString()}"
                    print(f"ERROR: {error_msg}")
                    QMessageBox.critical(None, "起動エラー", error_msg)
                    sys.exit(1)

                print("DEBUG: Creating MemoApp instance with DI")
                # DIコンテナを設定
                container = get_container()
                AppFactory.configure_container(container)
                main_win = AppFactory.create_memo_app(container)
                print("DEBUG: MemoApp instance created with DI")
                
                main_win.local_server = QLocalServer()
                QLocalServer.removeServer(UNIQUE_KEY)
                if main_win.local_server.listen(UNIQUE_KEY):
                    main_win.local_server.newConnection.connect(main_win.handle_new_connection)
                    print("DEBUG: Local server started successfully")
                else:
                    error_msg = f"ローカルサーバーの起動に失敗しました。\n{main_win.local_server.errorString()}"
                    print(f"ERROR: {error_msg}")
                    QMessageBox.critical(main_win, "起動エラー", error_msg)
                    shared_memory.detach()
                    sys.exit(1)

                print("DEBUG: Showing main window")
                main_win.show()
                
                # アプリケーション終了時のクリーンアップをQApplicationが有効な間に実行
                def cleanup_and_exit():
                    print("DEBUG: Application is about to quit, performing cleanup")
                    try:
                        main_win.cleanup_resources()
                    except Exception as e:
                        print(f"DEBUG: Cleanup error: {e}")
                
                app.aboutToQuit.connect(cleanup_and_exit)
                
                print("DEBUG: Starting event loop")
                exit_code = app.exec()
                print(f"DEBUG: Event loop ended with code: {exit_code}")
                
                if shared_memory.isAttached():
                    shared_memory.detach()
                
                print("DEBUG: Application cleanup completed")
                sys.exit(exit_code)
        else:
            print("DEBUG: QtNetwork not available, single instance mode")
            print("DEBUG: Creating MemoApp instance with DI")
            # DIコンテナを設定
            container = get_container()
            AppFactory.configure_container(container)
            main_win = AppFactory.create_memo_app(container)
            print("DEBUG: MemoApp instance created with DI, showing window")
            main_win.show()
            
            # アプリケーション終了時のクリーンアップをQApplicationが有効な間に実行
            def cleanup_and_exit():
                print("DEBUG: Application is about to quit, performing cleanup")
                try:
                    main_win.cleanup_resources()
                except Exception as e:
                    print(f"DEBUG: Cleanup error: {e}")
            
            app.aboutToQuit.connect(cleanup_and_exit)
            
            print("DEBUG: Starting event loop")
            exit_code = app.exec()
            print(f"DEBUG: Event loop ended with code: {exit_code}")
            
            print("DEBUG: Application cleanup completed")
            sys.exit(exit_code)
            
    except Exception as e:
        error_msg = f"アプリケーション起動中に致命的なエラーが発生しました: {e}"
        print(f"CRITICAL ERROR: {error_msg}")
        import traceback
        traceback.print_exc()
        try:
            QMessageBox.critical(None, "致命的なエラー", error_msg)
        except:
            pass  # GUI表示もできない場合はスキップ
        sys.exit(1)

if __name__ == '__main__':
    main()
