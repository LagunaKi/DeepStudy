// UndoRedoManager.ts
export interface NodeOperation {
  type: 'add' | 'delete' | 'update';
  nodeData?: any;
  nodeId?: string;
  parentId?: string;
}

class UndoRedoManager {
  private history: NodeOperation[] = [];
  private currentIndex: number = -1;
  private maxSize: number = 50; // 最大历史记录数

  push(operation: NodeOperation) {
    // 如果当前不在历史记录的末尾，截断后面的记录
    if (this.currentIndex < this.history.length - 1) {
      this.history = this.history.slice(0, this.currentIndex + 1);
    }

    this.history.push(operation);
    
    // 如果超过最大容量，移除最早的记录
    if (this.history.length > this.maxSize) {
      this.history.shift();
      this.currentIndex = this.history.length - 1;
    } else {
      this.currentIndex++;
    }
  }

  undo(): NodeOperation | null {
    if (this.canUndo()) {
      const operation = this.history[this.currentIndex];
      this.currentIndex--;
      return operation;
    }
    return null;
  }

  redo(): NodeOperation | null {
    if (this.canRedo()) {
      this.currentIndex++;
      return this.history[this.currentIndex];
    }
    return null;
  }

  canUndo(): boolean {
    return this.currentIndex >= 0;
  }

  canRedo(): boolean {
    return this.currentIndex < this.history.length - 1;
  }

  clear() {
    this.history = [];
    this.currentIndex = -1;
  }
}

export default new UndoRedoManager();