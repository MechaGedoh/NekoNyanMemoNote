# -*- coding: utf-8 -*-

import os
import sys
import tempfile
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop, QTimer

# テスト用のパス設定
test_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, test_dir)

from NekoNyanMemoNote.file_system import FileSystemManager

def simple_test():
    """シンプルな非同期テスト"""
    print("シンプル非同期テスト開始")
    
    app = QApplication([])
    fs_manager = FileSystemManager()
    
    # テストファイル作成
    temp_dir = tempfile.mkdtemp()
    test_file = os.path.join(temp_dir, "test.txt")
    test_content = "テストコンテンツ\n" * 100
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    result = {}
    
    def callback(content):
        result['content'] = content
        result['length'] = len(content) if content else 0
        print(f"コールバック実行: {result['length']} 文字")
    
    # 非同期読み込み実行
    print(f"ファイルサイズ: {os.path.getsize(test_file)} bytes")
    print("非同期読み込み開始...")
    
    fs_manager.load_memo_content_async(test_file, callback)
    
    # 1秒待機
    loop = QEventLoop()
    QTimer.singleShot(1000, loop.quit)
    loop.exec()
    
    if 'content' in result:
        print(f"[OK] 非同期読み込み成功: {result['length']} 文字")
    else:
        print("[ERROR] 非同期読み込み失敗")
    
    fs_manager.cleanup()
    
    # クリーンアップ
    import shutil
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    
    app.quit()

if __name__ == "__main__":
    simple_test()