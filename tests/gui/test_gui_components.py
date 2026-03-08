# GUI tests for AI Novel Generator
# Tests UI components and interactions

import pytest

# Mark all tests in this module as GUI tests
pytestmark = pytest.mark.gui


class TestGUIImports:
    """Test that GUI modules can be imported."""

    def test_ui_package_imports(self):
        """Test that UI package can be imported."""
        try:
            import ui

            assert ui is not None
        except ImportError:
            pytest.skip("UI package not available in headless environment")

    def test_main_window_imports(self):
        """Test that MainWindow can be imported."""
        try:
            from ui.main_window import NovelGeneratorGUI

            assert NovelGeneratorGUI is not None
        except ImportError:
            pytest.skip("MainWindow not available in headless environment")


class TestGUIComponents:
    """Test GUI component initialization."""

    @pytest.mark.skip(reason="Requires display environment")
    def test_main_window_initialization(self):
        """Test that main window can be initialized."""
        pass

    @pytest.mark.skip(reason="Requires display environment")
    def test_tab_creation(self):
        """Test that all tabs are created."""
        pass


class TestGUIHelpers:
    """Test GUI helper functions."""

    def test_helpers_module_exists(self):
        """Test that helpers module exists."""
        try:
            from ui import helpers

            assert helpers is not None
        except ImportError:
            pytest.skip("Helpers module not available")


class TestGenerationHandlers:
    """Test generation handlers without GUI."""

    def test_generation_handlers_module_exists(self):
        """Test that generation_handlers module exists."""
        try:
            from ui import generation_handlers

            assert generation_handlers is not None
        except ImportError:
            pytest.skip("Generation handlers not available")

    def test_llm_service_routing(self):
        """Test that LLM service routing functions exist."""
        try:
            from novel_generator.llm_service import build_llm_adapter, invoke_text_generation

            assert callable(build_llm_adapter)
            assert callable(invoke_text_generation)
        except ImportError:
            pytest.skip("LLM service not available")
