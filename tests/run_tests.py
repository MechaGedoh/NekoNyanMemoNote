# -*- coding: utf-8 -*-

import unittest
import sys
import os

# テスト用のパス設定
test_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(test_dir)
sys.path.insert(0, parent_dir)

def run_all_tests():
    """すべてのテストを実行"""
    # テストスイートを作成
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # テストファイルを自動発見
    test_modules = loader.discover(test_dir, pattern='test_*.py')
    suite.addTest(test_modules)
    
    # テストを実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 結果を返す
    return result.wasSuccessful()

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)