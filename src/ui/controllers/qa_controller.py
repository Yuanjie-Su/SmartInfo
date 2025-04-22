from PySide6.QtCore import QObject, Signal, QThreadPool
from src.services.qa_service import QAService
from src.ui.workers.async_runner import AsyncTaskRunner


class QAController(QObject):
    """
    Controller for Q&A tab, handling service calls and threading decoupled from the UI.
    """

    history_loaded = Signal(list)
    answer_received = Signal(dict)
    error_occurred = Signal(Exception)

    def __init__(self, qa_service: QAService, parent=None):
        super().__init__(parent)
        self._service = qa_service
        self.answer_sources = []  # 存储参考源，如果有的话

    def load_history(self, limit: int = 20):
        """
        Load QA history and emit history_loaded signal.
        """
        try:
            history = self._service.get_qa_history(limit=limit)
            self.history_loaded.emit(history)
        except Exception as e:
            self.error_occurred.emit(e)

    def send_question(self, question: str):
        """
        Send question to QAService asynchronously and emit answer_received or error_occurred signals.
        """
        runner = AsyncTaskRunner(self._service.answer_question, question)
        runner.setAutoDelete(True)
        runner.signals.finished.connect(self.answer_received)
        runner.signals.error.connect(self.error_occurred)
        QThreadPool.globalInstance().start(runner)
        
    def clear_answer_sources(self):
        """Clear the answer sources from the last query."""
        self.answer_sources = []
        
    def add_answer_sources(self, sources):
        """Add sources to the answer source list."""
        if sources:
            self.answer_sources = sources
            
    def clear_qa_history(self):
        """Clear all Q&A history."""
        try:
            return self._service.clear_qa_history()
        except Exception as e:
            self.error_occurred.emit(e)
            return False
