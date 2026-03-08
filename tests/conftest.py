from __future__ import annotations

import importlib.util
from importlib.machinery import ModuleSpec
import sys
import types
from dataclasses import dataclass


def _ensure_module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is not None:
        return module
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


def _install_openai_stubs() -> None:
    try:
        import openai  # type: ignore
    except ModuleNotFoundError:
        openai = _ensure_module("openai")
        setattr(openai, "ChatCompletion", type("ChatCompletion", (), {"create": staticmethod(lambda *_a, **_k: None)}))
        setattr(openai, "OpenAI", type("OpenAI", (), {}))


def _install_langchain_openai_stubs() -> None:
    try:
        import langchain_openai  # type: ignore
    except ModuleNotFoundError:
        module = _ensure_module("langchain_openai")

        class _Base:
            def __init__(self, *args, **kwargs) -> None:
                self.args = args
                self.kwargs = kwargs

            def invoke(self, *_args, **_kwargs):
                return None

            def embed_documents(self, _texts):
                return []

            def embed_query(self, _text):
                return []

        setattr(module, "ChatOpenAI", _Base)
        setattr(module, "AzureChatOpenAI", _Base)
        setattr(module, "AzureOpenAIEmbeddings", _Base)
        setattr(module, "OpenAIEmbeddings", _Base)


def _install_azure_stubs() -> None:
    try:
        import azure.ai.inference  # type: ignore
        import azure.core.credentials  # type: ignore
    except ModuleNotFoundError:
        _ensure_module("azure")
        _ensure_module("azure.ai")
        inference_module = _ensure_module("azure.ai.inference")
        inference_models_module = _ensure_module("azure.ai.inference.models")
        core_module = _ensure_module("azure.core")
        credentials_module = _ensure_module("azure.core.credentials")

        setattr(inference_module, "ChatCompletionsClient", type("ChatCompletionsClient", (), {}))
        setattr(credentials_module, "AzureKeyCredential", type("AzureKeyCredential", (), {}))
        setattr(inference_models_module, "SystemMessage", type("SystemMessage", (), {}))
        setattr(inference_models_module, "UserMessage", type("UserMessage", (), {}))
        setattr(core_module, "credentials", credentials_module)


def _install_langchain_core_stubs() -> None:
    try:
        import langchain_core.documents  # type: ignore
        import langchain_core.embeddings  # type: ignore
    except ModuleNotFoundError:
        _ensure_module("langchain_core")
        documents_module = _ensure_module("langchain_core.documents")
        embeddings_module = _ensure_module("langchain_core.embeddings")

        @dataclass
        class Document:
            page_content: str

        class Embeddings:
            def embed_documents(self, texts):
                raise NotImplementedError

            def embed_query(self, text):
                raise NotImplementedError

        setattr(documents_module, "Document", Document)
        setattr(embeddings_module, "Embeddings", Embeddings)


def _install_tkinter_stubs() -> None:
    if importlib.util.find_spec("tkinter") is not None:
        return

    tkinter_module = _ensure_module("tkinter")
    filedialog_module = _ensure_module("tkinter.filedialog")
    messagebox_module = _ensure_module("tkinter.messagebox")
    customtkinter_module = _ensure_module("customtkinter")

    class _DummyWidget:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args: tuple[object, ...] = args
            self.kwargs: dict[str, object] = dict(kwargs)

        def __call__(self, *args: object, **kwargs: object) -> None:
            return None

        def __getattr__(self, _name: str):
            return self._noop

        def _noop(self, *args: object, **kwargs: object) -> None:
            return None

    class _DummyVariable:
        def __init__(self, value: object | None = None, *args: object, **kwargs: object) -> None:
            self._value: object | None = value

        def get(self) -> object | None:
            return self._value

        def set(self, value: object) -> None:
            self._value = value

    class _DummyTclError(Exception):
        pass

    def _return_empty_string(*_args, **_kwargs) -> str:
        return ""

    def _return_false(*_args, **_kwargs) -> bool:
        return False

    def _return_none(*_args, **_kwargs) -> None:
        return None

    setattr(filedialog_module, "askdirectory", _return_empty_string)
    setattr(filedialog_module, "askopenfilename", _return_empty_string)
    setattr(filedialog_module, "asksaveasfilename", _return_empty_string)

    setattr(messagebox_module, "askyesno", _return_false)
    setattr(messagebox_module, "showinfo", _return_none)
    setattr(messagebox_module, "showwarning", _return_none)
    setattr(messagebox_module, "showerror", _return_none)

    setattr(tkinter_module, "filedialog", filedialog_module)
    setattr(tkinter_module, "messagebox", messagebox_module)
    setattr(tkinter_module, "Tk", _DummyWidget)
    setattr(tkinter_module, "Toplevel", _DummyWidget)
    setattr(tkinter_module, "Text", _DummyWidget)
    setattr(tkinter_module, "TclError", _DummyTclError)
    setattr(tkinter_module, "END", "end")
    setattr(tkinter_module, "INSERT", "insert")
    setattr(tkinter_module, "BOTH", "both")

    tkinter_module.__spec__ = ModuleSpec("tkinter", loader=None)
    filedialog_module.__spec__ = ModuleSpec("tkinter.filedialog", loader=None)
    messagebox_module.__spec__ = ModuleSpec("tkinter.messagebox", loader=None)
    customtkinter_module.__spec__ = ModuleSpec("customtkinter", loader=None)

    setattr(customtkinter_module, "CTkToplevel", _DummyWidget)
    setattr(customtkinter_module, "CTkTextbox", _DummyWidget)
    setattr(customtkinter_module, "CTkLabel", _DummyWidget)
    setattr(customtkinter_module, "CTkFrame", _DummyWidget)
    setattr(customtkinter_module, "CTkButton", _DummyWidget)
    setattr(customtkinter_module, "CTkEntry", _DummyWidget)
    setattr(customtkinter_module, "CTkCheckBox", _DummyWidget)
    setattr(customtkinter_module, "BooleanVar", _DummyVariable)


_install_openai_stubs()
_install_langchain_openai_stubs()
_install_azure_stubs()
_install_langchain_core_stubs()
_install_tkinter_stubs()
