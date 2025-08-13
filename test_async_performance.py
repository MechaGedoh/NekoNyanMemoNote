# -*- coding: utf-8 -*-

import os
import sys
import tempfile
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop

# テスト用のパス設定
test_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, test_dir)

from NekoNyanMemoNote.file_system import FileSystemManager

def create_test_files():
    """テスト用ファイルを作成"""
    temp_dir = tempfile.mkdtemp(prefix="async_test_")
    
    # 小さいファイル (32KB)
    small_file = os.path.join(temp_dir, "small_file.txt")
    small_content = "テストコンテンツ\n" * 1000  # 約32KB
    with open(small_file, 'w', encoding='utf-8') as f:
        f.write(small_content)
    
    # 中サイズファイル (256KB)
    medium_file = os.path.join(temp_dir, "medium_file.txt")
    medium_content = "中サイズテストコンテンツ\n" * 8000  # 約256KB
    with open(medium_file, 'w', encoding='utf-8') as f:
        f.write(medium_content)
    
    # 大きいファイル (1MB)
    large_file = os.path.join(temp_dir, "large_file.txt")
    large_content = "大容量テストコンテンツ\n" * 32000  # 約1MB
    with open(large_file, 'w', encoding='utf-8') as f:
        f.write(large_content)
    
    return temp_dir, small_file, medium_file, large_file

def test_file_load_strategies():
    """ファイル読み込み戦略のテスト"""
    print("=== ファイル読み込み戦略テスト ===")
    
    fs_manager = FileSystemManager()
    temp_dir, small_file, medium_file, large_file = create_test_files()
    
    try:
        # 戦略判定テスト
        small_strategy = fs_manager.get_file_load_strategy(small_file)
        medium_strategy = fs_manager.get_file_load_strategy(medium_file)
        large_strategy = fs_manager.get_file_load_strategy(large_file)
        
        print(f"小ファイル ({os.path.getsize(small_file):,} bytes): {small_strategy}")
        print(f"中ファイル ({os.path.getsize(medium_file):,} bytes): {medium_strategy}")
        print(f"大ファイル ({os.path.getsize(large_file):,} bytes): {large_strategy}")
        
        # 戦略が正しく判定されているかチェック
        assert small_strategy == 'sync', f"Expected 'sync', got '{small_strategy}'"
        assert medium_strategy == 'async', f"Expected 'async', got '{medium_strategy}'"
        assert large_strategy == 'streaming', f"Expected 'streaming', got '{large_strategy}'"
        
        print("[OK] 戦略判定テスト成功")
        
    finally:
        fs_manager.cleanup()
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def test_async_operations():
    """非同期操作のテスト"""
    print("\n=== 非同期操作テスト ===")
    
    app = QApplication([])
    fs_manager = FileSystemManager()
    temp_dir, small_file, medium_file, large_file = create_test_files()
    
    try:
        results = {}
        
        def test_callback(file_path, content, current_pos=-1, total_size=-1):
            results[file_path] = {
                'content_length': len(content) if content else 0,
                'completed': current_pos == -1 and total_size == -1
            }
        
        # 非同期読み込みテスト
        print("非同期読み込み開始...")
        start_time = time.time()
        
        fs_manager.auto_load_memo_content(small_file, lambda c, p, s: test_callback(small_file, c, p, s))
        fs_manager.auto_load_memo_content(medium_file, lambda c, p, s: test_callback(medium_file, c, p, s))
        fs_manager.auto_load_memo_content(large_file, lambda c, p, s: test_callback(large_file, c, p, s))
        
        # イベントループで完了を待つ
        loop = QEventLoop()
        
        def check_completion():
            if len(results) == 3 and all(r['completed'] for r in results.values()):
                loop.quit()
        
        from PyQt6.QtCore import QTimer
        timer = QTimer()
        timer.timeout.connect(check_completion)
        timer.start(100)  # 100ms間隔でチェック
        
        # 最大5秒待機
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        
        elapsed_time = time.time() - start_time
        
        print(f"処理時間: {elapsed_time:.3f}秒")
        print(f"完了した読み込み: {len(results)}/3")
        
        for file_path, result in results.items():
            filename = os.path.basename(file_path)
            status = "[完了]" if result['completed'] else "[未完了]"
            print(f"  {filename}: {result['content_length']:,} chars - {status}")
        
        if len(results) == 3:
            print("[OK] 非同期操作テスト成功")
        else:
            print("[WARNING] 一部の操作が未完了")
        
    finally:
        fs_manager.cleanup()
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        app.quit()

def test_performance_monitoring():
    """パフォーマンス監視のテスト"""
    print("\n=== パフォーマンス監視テスト ===")
    
    # constants.py でパフォーマンス監視を有効にする必要がある
    try:
        from NekoNyanMemoNote.constants import ENABLE_ASYNC_PERFORMANCE_MONITORING
        if ENABLE_ASYNC_PERFORMANCE_MONITORING:
            print("[OK] パフォーマンス監視が有効")
        else:
            print("[WARNING] パフォーマンス監視が無効 - constants.py で ENABLE_ASYNC_PERFORMANCE_MONITORING = True に設定")
    except ImportError:
        print("[ERROR] constants.py からのインポートに失敗")

def main():
    """メインテスト関数"""
    print("非同期ファイル操作パフォーマンステスト開始")
    
    try:
        test_file_load_strategies()
        test_async_operations()
        test_performance_monitoring()
        
        print("\nすべてのテストが完了しました！")
        
    except Exception as e:
        print(f"\nテスト中にエラーが発生: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()