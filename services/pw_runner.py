"""
Esegue le coroutine Playwright su un event loop dedicato in un thread separato.

Su Windows il loop di uvicorn è un SelectorEventLoop, che non supporta i
sottoprocessi: Playwright non può avviare il browser da lì (NotImplementedError).
Qui viene mantenuto un thread con un loop Proactor su cui girano tutte le
automazioni; essendo sempre lo stesso loop, il browser può restare aperto
tra una richiesta e l'altra.
"""

import asyncio
import sys
import threading

_lock = threading.Lock()
_loop: "asyncio.AbstractEventLoop | None" = None


def _new_loop() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        try:
            return asyncio.ProactorEventLoop()
        except AttributeError:
            return asyncio.WindowsProactorEventLoopPolicy().new_event_loop()
    return asyncio.new_event_loop()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _lock:
        if _loop is None or _loop.is_closed():
            loop = _new_loop()
            threading.Thread(target=loop.run_forever, daemon=True).start()
            _loop = loop
        return _loop


def esegui(coro, timeout: float = 600):
    """Esegue una coroutine sul loop Playwright (bloccante — usare in un thread)."""
    fut = asyncio.run_coroutine_threadsafe(coro, _ensure_loop())
    try:
        return fut.result(timeout)
    except TimeoutError:
        fut.cancel()
        raise
