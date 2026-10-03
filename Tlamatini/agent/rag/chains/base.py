# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from typing import Optional, Dict, Any
from langchain_core.callbacks import BaseCallbackHandler
from ...global_state import global_state
from ...context_governor import measure_async as _context_measure_async
from ...context_governor import next_seq as _context_next_seq
from ...context_governor import note_run_seq as _context_note_run_seq
from ...context_governor import record_call_usage as _context_record_call
from ...context_governor import report_run_usage as _context_report_run_usage
from ...context_governor import usage_from_llm_result as _context_usage_from


class GenerationCancelledException(Exception):
    """Exception raised when generation is cancelled by user."""
    pass


def _ollama_config() -> Dict[str, Any]:
    """The live config.json (cached by config_loader).  Fail-open to {}."""
    try:
        from ...config_loader import load_config
        cfg = load_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _model_name_from(serialized: Any, kwargs: Dict[str, Any]) -> str:
    """Which Ollama model this call goes to, from LangChain's own run data."""
    try:
        params = kwargs.get('invocation_params') or {}
        name = params.get('model') or params.get('model_name')
        if not name:
            name = (kwargs.get('metadata') or {}).get('ls_model_name')
        if not name and isinstance(serialized, dict):
            name = (serialized.get('kwargs') or {}).get('model')
        return str(name or '')
    except Exception:  # noqa: BLE001
        return ''


class Callbacks(BaseCallbackHandler):
    """Cancellation for every chain LLM - and, for the MAIN answering call only,
    the context gauge.

    ``main=True`` marks the ONE call that is Tlamatini's own inference - the
    answer the user is waiting for.  The question rewriter and the history
    summarizer share this class but are side calls: Angela, 2026-09-28 -
    *"JUST THE METERING MUST BE IN THE MODEL OF THE MAIN CONNECTION CHAIN FROM
    TLAMATINI, THE THREAD WHICH TLAMATINI USE TO INFERE WITH."*  A side call
    that fed the ring used to flash its own small size over the real one.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, *, main: bool = False):
        self.config = config or {}
        self.cancelled = False
        self.main = bool(main)

    def on_llm_new_token(self, token, **kwargs):
        # Check for cancellation on EVERY token - this is the key to fast cancellation
        if global_state.get_state('cancel_generation'):
            self.cancelled = True
            print("\n--- [CANCEL] Generation cancelled by user during streaming ---")
            raise GenerationCancelledException("Generation cancelled by user")
        print(token, end='', flush=True)

    def on_llm_start(self, *args, **kwargs):
        # Check before starting
        if global_state.get_state('cancel_generation'):
            self.cancelled = True
            raise GenerationCancelledException("Generation cancelled before start")
        # A completion model (OllamaLLM, /api/generate) never reaches
        # on_chat_model_start: its whole request is ONE prompt string.
        if self.main:
            try:
                prompts = kwargs.get('prompts')
                if prompts is None and len(args) > 1:
                    prompts = args[1]
                if isinstance(prompts, (list, tuple)) and prompts:
                    self._measure_main(prompts[0], args[0] if args else None, kwargs)
            except Exception:  # noqa: BLE001 - the gauge owes the answer nothing
                pass

    def _measure_main(self, batch: Any, serialized: Any, kwargs: Dict[str, Any]) -> None:
        """Snapshot the MAIN request and remember its run id for the real count."""
        seq = _context_next_seq()
        cfg = _ollama_config()
        _context_measure_async(
            None,                        # the request bound the user id
            batch,
            label=(self.config or {}).get('label') or 'answering',
            source='one-shot',
            prefix_message_count=1,
            seq=seq,
            model=_model_name_from(serialized, kwargs),
            base_url=str(cfg.get('ollama_base_url') or ''),
            config=cfg,
        )
        _context_note_run_seq(kwargs.get('run_id'), seq)

    def on_chat_model_start(self, serialized, messages, **kwargs):
        """EVERY chat-model call in EVERY chain passes through here.

        This is the One-Shot / RAG counterpart of the Multi-Turn executor's
        ``_model_step``. LangChain hands us the REAL messages it is about to
        send, so the context gauge now updates for a plain One-Shot question
        too - it never did before, and the ring simply sat frozen on whatever
        the last Multi-Turn request had left there (Angela, 2026-09-21).

        SNAPSHOT AND SIGNAL ONLY. The meter's worker thread does the
        arithmetic; nothing here is allowed to cost the user latency, and the
        whole body is guarded because a gauge must never break an answer.

        NOTE: this deliberately does NOT repeat ``on_llm_start``'s cancellation
        check. Changing when a generation can be cancelled is a separate
        decision from measuring it, and must not ride in on this change.
        """
        if not self.main:
            return                            # a side call - never metered
        try:
            batch = messages
            if isinstance(messages, (list, tuple)) and messages and \
                    isinstance(messages[0], (list, tuple)):
                batch = messages[0]          # List[List[BaseMessage]]
            self._measure_main(batch, serialized, kwargs)
        except Exception:  # noqa: BLE001 - the gauge owes the answer nothing
            pass

    def on_llm_end(self, *args, **kwargs):
        # Reset cancelled state
        self.cancelled = False
        if not self.main:
            return
        # Ollama's REAL prompt_eval_count for the main answer, paired to the
        # frame measured in on_*_start through the shared run id.
        try:
            response = kwargs.get('response') if 'response' in kwargs else (args[0] if args else None)
            usage = _context_usage_from(response)
            if usage:
                label = (self.config or {}).get('label') or 'answering'
                _context_report_run_usage(kwargs.get('run_id'), usage, label=label)
                _context_record_call(
                    usage.get('prompt_tokens'), usage.get('completion_tokens'),
                    model=str(usage.get('model') or ''), source='one-shot answer',
                )
        except Exception:  # noqa: BLE001
            pass


def summarize_or_none(llm, msgs):
    """The chat-history summary, or None when the summary call failed.

    The summary is an optimisation, never a reason to lose the answer: on
    2026-10-03 a cloud model refused the summarizer's request (HTTP 400, too
    many stop sequences) and Angela's whole question failed before any work
    was done. Any failure here is logged and the caller sends the history
    unsummarized. A user's Cancel still propagates.
    """
    try:
        out = llm.with_config({"callbacks": [Callbacks()]}).invoke(msgs)
    except GenerationCancelledException:
        raise
    except Exception as exc:
        print(f"--- [HISTORY-SUMMARY] the chat-history summary failed ({exc}); "
              f"sending the history unsummarized ---")
        return None
    summary = getattr(out, "content", str(out))
    print(f"--- [HISTORY-SUMMARY] chat history summarized ({len(str(summary))} chars) ---")
    return summary
