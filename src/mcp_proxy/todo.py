import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class TodoItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    priority: str = "medium"  # low, medium, high
    completed: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

class TodoManager:
    """
    管理系統待辦事項的類別，使用 JSON 文件進行持久化存儲。
    """
    def __init__(self, storage_file: str = "todos.json"):
        self.storage_file = storage_file
        self.todos: Dict[str, TodoItem] = self._load_todos()

    def _load_todos(self) -> Dict[str, TodoItem]:
        """ 從 JSON 文件加載待辦事項 """
        if not os.path.exists(self.storage_file):
            return {}
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: TodoItem(**v) for k, v in data.items()}
        except Exception as e:
            print(f"加載待辦事項失敗: {e}")
            return {}

    def _save_todos(self):
        """ 將待辦事項保存到 JSON 文件 """
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                # 將 TodoItem 模型轉換為字典進行保存
                data = {k: v.model_dump() for k, v in self.todos.items()}
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存待辦事項失敗: {e}")

    def add_todo(self, content: str, priority: str = "medium") -> TodoItem:
        """ 創建新的待辦事項 """
        todo = TodoItem(content=content, priority=priority)
        self.todos[todo.id] = todo
        self._save_todos()
        return todo

    def get_all_todos(self) -> List[TodoItem]:
        """ 獲取所有待辦事項，按創建時間排序 """
        return sorted(self.todos.values(), key=lambda x: x.created_at, reverse=True)

    def update_todo(self, todo_id: str, updates: Dict[str, Any]) -> Optional[TodoItem]:
        """ 更新待辦事項內容 """
        if todo_id not in self.todos:
            return None
        
        todo = self.todos[todo_id]
        for key, value in updates.items():
            if hasattr(todo, key):
                setattr(todo, key, value)
        
        todo.updated_at = datetime.now().isoformat()
        self.todos[todo_id] = todo
        self._save_todos()
        return todo

    def toggle_todo(self, todo_id: str) -> Optional[TodoItem]:
        """ 切換完成狀態 """
        if todo_id not in self.todos:
            return None
        
        todo = self.todos[todo_id]
        todo.completed = not todo.completed
        todo.updated_at = datetime.now().isoformat()
        self.todos[todo_id] = todo
        self._save_todos()
        return todo

    def delete_todo(self, todo_id: str) -> bool:
        """ 刪除待辦事項 """
        if todo_id in self.todos:
            del self.todos[todo_id]
            self._save_todos()
            return True
        return False
