# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod
from typing import TypeVar, Type, Dict, Any, Callable, Optional
import inspect

T = TypeVar('T')

class DIContainer:
    """シンプルな依存性注入コンテナ"""
    
    def __init__(self):
        self._services: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable] = {}
        self._singletons: Dict[Type, Any] = {}
    
    def register_singleton(self, interface: Type[T], instance: T) -> None:
        """シングルトンインスタンスを登録"""
        self._singletons[interface] = instance
    
    def register_factory(self, interface: Type[T], factory: Callable[[], T]) -> None:
        """ファクトリ関数を登録（呼び出し毎に新しいインスタンス）"""
        self._factories[interface] = factory
    
    def register_type(self, interface: Type[T], implementation: Type[T]) -> None:
        """型を登録（シングルトンとして動作）"""
        self._services[interface] = implementation
    
    def resolve(self, interface: Type[T]) -> T:
        """依存関係を解決してインスタンスを取得"""
        # シングルトンをチェック
        if interface in self._singletons:
            return self._singletons[interface]
        
        # ファクトリをチェック
        if interface in self._factories:
            return self._factories[interface]()
        
        # 登録された型をチェック
        if interface in self._services:
            implementation = self._services[interface]
            # 既にインスタンス化済みかチェック
            if not inspect.isclass(implementation):
                return implementation
            
            # コンストラクタで依存関係を自動解決
            instance = self._create_instance(implementation)
            self._singletons[interface] = instance  # シングルトンとして保存
            return instance
        
        # 直接インスタンス化を試行
        if inspect.isclass(interface):
            instance = self._create_instance(interface)
            self._singletons[interface] = instance
            return instance
        
        raise ValueError(f"Service {interface} is not registered")
    
    def _create_instance(self, cls: Type[T]) -> T:
        """依存関係を自動解決してインスタンスを作成"""
        try:
            # コンストラクタのシグネチャを取得
            sig = inspect.signature(cls.__init__)
            args = {}
            
            # 各パラメータを解決
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                
                # 型ヒントがある場合は依存関係を解決
                if param.annotation != inspect.Parameter.empty:
                    try:
                        args[param_name] = self.resolve(param.annotation)
                    except ValueError:
                        # 解決できない場合はNoneまたはデフォルト値を使用
                        if param.default != inspect.Parameter.empty:
                            args[param_name] = param.default
                        else:
                            args[param_name] = None
                elif param.default != inspect.Parameter.empty:
                    args[param_name] = param.default
            
            return cls(**args)
        
        except Exception as e:
            # フォールバック: パラメータなしでの作成を試行
            try:
                return cls()
            except Exception:
                raise ValueError(f"Cannot create instance of {cls}: {e}")
    
    def clear(self) -> None:
        """全ての登録をクリア"""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()


# グローバルDIコンテナ（シングルトンパターン）
_global_container: Optional[DIContainer] = None

def get_container() -> DIContainer:
    """グローバルDIコンテナを取得"""
    global _global_container
    if _global_container is None:
        _global_container = DIContainer()
    return _global_container

def reset_container() -> None:
    """グローバルDIコンテナをリセット（主にテスト用）"""
    global _global_container
    _global_container = None