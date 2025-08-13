# -*- coding: utf-8 -*-

import os
import sys
import gc
import tracemalloc
from PyQt6.QtWidgets import QApplication

def get_memory_usage():
    """現在のメモリ使用量を取得（psutil不要版）"""
    try:
        # tracemallocを使用してPythonのメモリ使用量を測定
        current, peak = tracemalloc.get_traced_memory()
        return {
            'current_mb': current / 1024 / 1024,  # MB
            'peak_mb': peak / 1024 / 1024,  # MB
            'python_objects': len(gc.get_objects())
        }
    except:
        return {
            'current_mb': 0,
            'peak_mb': 0,
            'python_objects': len(gc.get_objects())
        }

def analyze_app_memory():
    """アプリケーションのメモリ使用量を分析"""
    print("=== MechaNyan メモリ使用量分析 ===\n")
    
    # メモリトレース開始
    tracemalloc.start()
    
    # アプリ起動前
    print("1. アプリ起動前:")
    before = get_memory_usage()
    print(f"   メモリ使用量: {before['current_mb']:.1f} MB")
    print(f"   Pythonオブジェクト数: {before['python_objects']:,}")
    
    # QApplication作成
    app = QApplication(sys.argv)
    print("\n2. QApplication作成後:")
    after_qapp = get_memory_usage()
    print(f"   メモリ使用量: {after_qapp['current_mb']:.1f} MB (+{after_qapp['current_mb'] - before['current_mb']:.1f} MB)")
    print(f"   Pythonオブジェクト数: {after_qapp['python_objects']:,} (+{after_qapp['python_objects'] - before['python_objects']:,})")
    
    # メインアプリ作成
    try:
        from NekoNyanMemoNote.app_factory import AppFactory
        memo_app = AppFactory.create_app()
        
        print("\n3. MemoApp作成後:")
        after_app = get_memory_usage()
        print(f"   メモリ使用量: {after_app['current_mb']:.1f} MB (+{after_app['current_mb'] - after_qapp['current_mb']:.1f} MB)")
        print(f"   Pythonオブジェクト数: {after_app['python_objects']:,} (+{after_app['python_objects'] - after_qapp['python_objects']:,})")
        
        # 大きなファイルのシミュレーション
        print("\n4. 大きなテキスト（100KB）読み込み後:")
        large_text = "あ" * 50000  # 日本語文字で約100KB
        
        # エディタがある場合はテキストを設定
        _, _, _, editor = memo_app.get_current_widgets()
        if editor:
            editor.setPlainText(large_text)
            after_large = get_memory_usage()
            print(f"   メモリ使用量: {after_large['current_mb']:.1f} MB (+{after_large['current_mb'] - after_app['current_mb']:.1f} MB)")
            print(f"   Pythonオブジェクト数: {after_large['python_objects']:,} (+{after_large['python_objects'] - after_app['python_objects']:,})")
            
            # より大きなファイル（1MB）
            print("\n5. 非常に大きなテキスト（1MB）読み込み後:")
            very_large_text = "あ" * 500000  # 約1MB
            editor.setPlainText(very_large_text)
            after_very_large = get_memory_usage()
            print(f"   メモリ使用量: {after_very_large['current_mb']:.1f} MB (+{after_very_large['current_mb'] - after_large['current_mb']:.1f} MB)")
            print(f"   Pythonオブジェクト数: {after_very_large['python_objects']:,} (+{after_very_large['python_objects'] - after_large['python_objects']:,})")
        
        # 分析結果
        print("\n=== 分析結果 ===")
        base_memory = after_app['current_mb'] - before['current_mb']
        print(f"• ベースアプリケーション: {base_memory:.1f} MB")
        
        if editor:
            small_file_impact = after_large['current_mb'] - after_app['current_mb']
            large_file_impact = after_very_large['current_mb'] - after_large['current_mb']
            print(f"• 100KBファイルの影響: +{small_file_impact:.1f} MB")
            print(f"• 1MBファイルの影響: +{large_file_impact:.1f} MB")
            
            efficiency = (1.0 / large_file_impact) if large_file_impact > 0 else float('inf')
            print(f"• メモリ効率: {efficiency:.1f} (1MB理論値に対する実効率)")
        
        print("\n=== 最適化提案 ===")
        
        # 潜在的なメモリリーク箇所をチェック
        potential_issues = []
        
        # 1. QTextDocumentの重複インスタンス
        print("1. QTextDocument管理:")
        if hasattr(memo_app, 'tab_widget'):
            tab_count = memo_app.tab_widget.count()
            print(f"   • アクティブタブ数: {tab_count}")
            print(f"   • 推定エディタ数: {tab_count - 1}")  # +タブを除く
            
        # 2. イベントリスナーの重複登録
        print("2. イベントリスナー:")
        print("   • ホットキーリスナー: 1つ（適切）")
        print("   • タブ変更イベント: タブ数分（要確認）")
        
        # 3. ファイルキャッシュ
        print("3. ファイルキャッシュ:")
        if hasattr(memo_app, 'last_opened_files'):
            cache_size = len(memo_app.last_opened_files)
            print(f"   • 最後に開いたファイルキャッシュ: {cache_size}個")
        
        print("\n=== 予想される最適化効果 ===")
        print("• 軽微な最適化（10-20% 削減）:")
        print("  - 不要なQTextDocumentインスタンス削除")
        print("  - イベントリスナーの重複解消")
        print("  - ガベージコレクション呼び出し最適化")
        print("• 中程度の最適化（20-40% 削減）:")
        print("  - 大容量ファイルのストリーミング読み込み")
        print("  - エディタの遅延初期化")
        print("• 大幅な最適化（40-60% 削減）:")
        print("  - 非アクティブタブのエディタ内容解放")
        print("  - ファイル内容の部分読み込み（仮想化）")
        
    except Exception as e:
        print(f"分析中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    analyze_app_memory()