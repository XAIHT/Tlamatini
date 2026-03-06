// Agentic Control Panel - Undo/Redo Manager
// LOAD ORDER: #3 - Depends on: nothing (standalone class)

// ========================================
// UNDO/REDO MANAGER
// ========================================
/**
 * UndoManager - Manages undo/redo history for canvas operations.
 * Implements a command pattern with LIFO stacks for undo and redo.
 */
class UndoManager {
    constructor(maxActions = 1024) {
        this.undoStack = [];  // Actions that can be undone
        this.redoStack = [];  // Actions that can be redone
        this.maxActions = maxActions;
        this.isProcessing = false;  // Prevent recursive undo/redo recording
    }

    /**
     * Record an action that can be undone.
     * @param {Object} action - { type, data, undo(), redo() }
     */
    record(action) {
        if (this.isProcessing) return;  // Don't record during undo/redo operations

        this.undoStack.push(action);
        this.redoStack = [];  // Clear redo stack on new action

        // Enforce max limit
        while (this.undoStack.length > this.maxActions) {
            this.undoStack.shift();  // Remove oldest action
        }

        console.log(`[UndoManager] Recorded action: ${action.type}, stack size: ${this.undoStack.length}`);
    }

    /**
     * Undo the last action.
     * @returns {boolean} True if an action was undone
     */
    async undo() {
        if (this.undoStack.length === 0) {
            console.log('[UndoManager] Nothing to undo');
            return false;
        }

        this.isProcessing = true;
        try {
            const action = this.undoStack.pop();
            console.log(`[UndoManager] Undoing action: ${action.type}`);
            await action.undo();
            this.redoStack.push(action);
            return true;
        } catch (error) {
            console.error('[UndoManager] Undo failed:', error);
            return false;
        } finally {
            this.isProcessing = false;
        }
    }

    /**
     * Redo the last undone action.
     * @returns {boolean} True if an action was redone
     */
    async redo() {
        if (this.redoStack.length === 0) {
            console.log('[UndoManager] Nothing to redo');
            return false;
        }

        this.isProcessing = true;
        try {
            const action = this.redoStack.pop();
            console.log(`[UndoManager] Redoing action: ${action.type}`);
            await action.redo();
            this.undoStack.push(action);
            return true;
        } catch (error) {
            console.error('[UndoManager] Redo failed:', error);
            return false;
        } finally {
            this.isProcessing = false;
        }
    }

    canUndo() { return this.undoStack.length > 0; }
    canRedo() { return this.redoStack.length > 0; }
    clear() {
        this.undoStack = [];
        this.redoStack = [];
        console.log('[UndoManager] History cleared');
    }
}

// ========================================
// AGENT STATUS POLLING CONSTANTS
// ========================================
let agentStatusPollerInterval = null;
const AGENT_STATUS_POLL_INTERVAL = 300; // Poll every 300ms for faster updates

// Initialize UndoManager with 1024 action limit
const undoManager = new UndoManager(1024);
