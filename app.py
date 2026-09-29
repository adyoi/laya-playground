from __future__ import annotations

import argparse
import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

import laya
import laya.serve
import laya.structured
from laya import Router

from presets import GROUPS, PRESETS
from redact import PATTERNS, RedactionHook, redact_state

STATIC_DIR = Path(__file__).parent / "static"

KNOWN_MODELS = tuple(getattr(laya, "DEFAULT_MODELS", {}) or ("english", "multilingual", "typed-decisions"))
KNOWN_QTYPES = sorted(getattr(laya, "QTYPES", {}) or {"choice", "score", "noul"})

MAX_QUESTIONS = getattr(laya.serve, "MAX_QUESTIONS", 64)
MAX_STATE_CHARS = getattr(laya.serve, "MAX_STATE_CHARS", 50_000)
MAX_STATES = 64

CONFIG: Dict[str, Any] = {
    "preload": [m.strip() for m in os.getenv("LAYA_PRELOAD", "").split(",") if m.strip()],
    "device": os.getenv("LAYA_DEVICE") or None,
    "default": os.getenv("LAYA_DEFAULT_MODEL", "english"),
    "max_loaded": int(os.getenv("LAYA_MAX_LOADED", "1")),
    "threads": int(os.getenv("LAYA_THREADS", "0")) or None,
    "redact_kinds": [k.strip() for k in os.getenv("LAYA_REDACT", "").split(",") if k.strip()],
    "warnings": [],
}

ROUTER: Optional[Router] = None
REDACTION_HOOK: Optional[RedactionHook] = None


def _check_model(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if value not in KNOWN_MODELS:
        raise ValueError(f"unknown model {value!r}; expected one of {sorted(KNOWN_MODELS)} or omit it")
    return value


GUARDRAIL_ACTIONS = ("annotate", "filter", "raise")


def _check_action(value: str) -> str:
    if value not in GUARDRAIL_ACTIONS:
        raise ValueError(f"unknown action {value!r}; expected one of {list(GUARDRAIL_ACTIONS)}")
    return value


class Question(BaseModel):
    type: str
    instructions: str
    criteria: Optional[Union[Dict[str, Any], List[Any]]] = None
    model_config = {"extra": "allow"}

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if KNOWN_QTYPES and value not in KNOWN_QTYPES:
            raise ValueError(f"unknown question type {value!r}; expected one of {KNOWN_QTYPES}")
        return value

    @model_validator(mode="after")
    def _criteria_present(self) -> "Question":
        if self.type in ("choice", "score") and not self.criteria:
            raise ValueError(f"'{self.type}' questions require non-empty criteria")
        return self


class PredictRequest(BaseModel):
    state: Union[str, Dict[str, Any], List[Any]]
    questions: Dict[str, Question] = Field(..., min_length=1)
    model: Optional[str] = None
    task: Optional[str] = None
    lang: Optional[str] = None
    redact: Optional[List[str]] = None
    lang_guess: Optional[str] = None

    _v_model = field_validator("model")(classmethod(lambda cls, v: _check_model(v)))

    @field_validator("state")
    @classmethod
    def _non_empty(cls, value):
        if not value:
            raise ValueError("state must not be empty")
        return value


class BatchRequest(BaseModel):
    states: List[Union[str, Dict[str, Any], List[Any]]] = Field(..., min_length=1, max_length=MAX_STATES)
    questions: Dict[str, Question] = Field(..., min_length=1)
    model: Optional[str] = None
    lang: Optional[str] = None

    _v_model = field_validator("model")(classmethod(lambda cls, v: _check_model(v)))

    @field_validator("states")
    @classmethod
    def _non_empty_states(cls, value):
        for index, state in enumerate(value):
            if not state:
                raise ValueError(f"states[{index}] must not be empty")
        return value


class StructuredRequest(BaseModel):
    state: Union[str, Dict[str, Any], List[Any]]
    schema_: Optional[Dict[str, Any]] = Field(default=None, alias="schema")
    questions: Optional[Dict[str, Question]] = None
    model: Optional[str] = None
    lang: Optional[str] = None
    redact: Optional[List[str]] = None

    _v_model = field_validator("model")(classmethod(lambda cls, v: _check_model(v)))

    @field_validator("state")
    @classmethod
    def _non_empty(cls, value):
        if not value:
            raise ValueError("state must not be empty")
        return value

    @model_validator(mode="after")
    def _exactly_one(self) -> "StructuredRequest":
        if bool(self.schema_) == bool(self.questions):
            raise ValueError("provide exactly one of 'schema' or 'questions'")
        return self


class ShortlistRequest(BaseModel):
    state: Union[str, Dict[str, Any], List[Any]]
    questions: Dict[str, Question] = Field(..., min_length=1)
    k: int = Field(default=20, ge=2, le=256)
    model: Optional[str] = None
    lang: Optional[str] = None

    _v_model = field_validator("model")(classmethod(lambda cls, v: _check_model(v)))

    @field_validator("state")
    @classmethod
    def _non_empty(cls, value):
        if not value:
            raise ValueError("state must not be empty")
        return value


class GuardrailRequest(BaseModel):
    state: Union[str, Dict[str, Any], List[Any]]
    questions: Optional[Dict[str, Question]] = None
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    action: str = "annotate"
    state_key: Optional[str] = None
    model: Optional[str] = None
    lang: Optional[str] = None
    normalize_scores: bool = True

    _v_model = field_validator("model")(classmethod(lambda cls, v: _check_model(v)))
    _v_action = field_validator("action")(classmethod(lambda cls, v: _check_action(v)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ROUTER, REDACTION_HOOK
    if CONFIG["threads"]:
        import torch

        torch.set_num_threads(CONFIG["threads"])
    router = Router(
        device=CONFIG["device"],
        default=CONFIG["default"],
        max_loaded=CONFIG["max_loaded"],
    )
    ROUTER = router
    if CONFIG["redact_kinds"]:
        REDACTION_HOOK = RedactionHook(CONFIG["redact_kinds"])
        router.add_hook(REDACTION_HOOK)
    if CONFIG["preload"]:
        try:
            router.preload(CONFIG["preload"])
        except OSError as exc:
            CONFIG["warnings"].append(
                f"preload {CONFIG['preload']} failed ({exc}); falling back to lazy loading"
            )
    try:
        yield
    finally:
        ROUTER = None
        REDACTION_HOOK = None
        router.unload()


app = FastAPI(
    title="Laya Example — Support Triage",
    version="1.1.0",
    description="Typed decisions (choice / score / noul) over any text, with a language router.",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next: Any) -> Any:
    """Stamp every response with a request id and funnel errors through one envelope.

    The body is not read here, so pydantic validation still sees the original stream. The
    id is only attached to responses this app produced; framework-level 404/500 fallbacks
    are normalized by the handlers below.
    """
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except HTTPException as exc:
        response = _error_response(exc.status_code, exc.detail, request_id)
    except Exception as exc:
        response = _error_response(500, f"{type(exc).__name__}: {exc}", request_id)
    response.headers["x-request-id"] = request_id
    return response


def _error_response(status: int, detail: Any, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"status": status, "detail": detail, "request_id": request_id}},
        headers={"x-request-id": request_id},
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _router() -> Router:
    if ROUTER is None:
        raise HTTPException(status_code=503, detail="router not ready")
    return ROUTER


class ModelLoadTimeout(HTTPException):
    """A checkpoint took longer than LAYA_LOAD_TIMEOUT to become resident.

    Subclasses HTTPException so the 503 travels the same path as every other error envelope
    instead of being swallowed by the handlers' `except Exception` fallback.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=503, detail=detail)


class ModelGate:
    """Single-flight checkpoint loading with a hard timeout.

    `Router.load` already shares one Agent between concurrent callers, but the *download*
    that precedes it is not deduplicated: two requests arriving on a cold cache each start
    their own `snapshot_download` of the same files, which is how one `/predict` turned into
    a 14-minute stall with two competing `.incomplete` files in the Hugging Face cache.
    Here the first caller for a given checkpoint owns the load and every later caller awaits
    that same task instead of starting another.

    The wait is `shield`ed, so one caller giving up does not cancel the shared load for the
    rest — the model still finishes warming and stays resident for the next request.
    """

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self._tasks: Dict[str, Any] = {}
        self._started: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def ensure(self, name: str) -> None:
        if not name:
            return
        async with self._lock:
            task = self._tasks.get(name)
            if task is None or (task.done() and task.exception() is not None):
                self._started[name] = time.time()
                self._tasks[name] = task = asyncio.ensure_future(
                    run_in_threadpool(_router().load, name)
                )
        if task.done() and task.exception() is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), self.timeout)
        except asyncio.TimeoutError as exc:
            waited = round(time.time() - self._started.get(name, time.time()))
            raise ModelLoadTimeout(
                f"checkpoint {name!r} was still loading after {self.timeout:.0f}s "
                f"(waited {waited}s). It is not lost: the load keeps running in the "
                f"background and the next request finds it resident. On a machine with less "
                f"free memory than the checkpoint, this is paging, not downloading."
            ) from exc

    async def ensure_many(self, names: List[str]) -> None:
        for name in dict.fromkeys(n for n in names if n):
            await self.ensure(name)

    def loading(self) -> Dict[str, float]:
        """Checkpoints currently warming, mapped to seconds elapsed. Resolved loads are dropped
        whether they succeeded or failed, so only in-flight work is reported."""
        now = time.time()
        out: Dict[str, float] = {}
        for name, task in self._tasks.items():
            if task.done():
                continue
            out[name] = round(now - self._started.get(name, now), 1)
        return out


GATE = ModelGate(float(os.getenv("LAYA_LOAD_TIMEOUT", "600")))


async def _guarded(awaitable: Any, seconds: float, message: str) -> Any:
    """Bound one awaitable, converting a timeout into a 504 with an actionable detail."""
    try:
        return await asyncio.wait_for(asyncio.shield(asyncio.ensure_future(awaitable)), seconds)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail=message) from exc


def _predict_timeout() -> float:
    return float(os.getenv("LAYA_PREDICT_TIMEOUT", "600"))


async def _predict(state: Any, questions: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    """Route, make sure the chosen checkpoint is resident, then predict under a timeout.

    The explicit `route` + `ensure` pair is what stops the duplicate-load race: the routing
    pass is pure Python and sub-millisecond, and it names the checkpoint so the load can be
    deduplicated before `Router.predict` would otherwise trigger it lazily.
    """
    router = _router()
    decision = router.route(state, questions, **kwargs)
    await GATE.ensure(decision.model)
    return await _guarded(
        run_in_threadpool(router.predict, state, questions, **kwargs),
        _predict_timeout(),
        f"inference did not finish within {_predict_timeout():.0f}s on this device",
    )


def _plain(questions: Dict[str, Question]) -> Dict[str, Any]:
    return {k: v.model_dump(exclude_none=True) for k, v in questions.items()}


def _check_limits(state: Any, questions: Dict[str, Any]) -> None:
    if len(questions) > MAX_QUESTIONS:
        raise HTTPException(status_code=413, detail=f"too many questions ({len(questions)} > {MAX_QUESTIONS})")
    size = len(state) if isinstance(state, str) else len(str(state))
    if size > MAX_STATE_CHARS:
        raise HTTPException(status_code=413, detail=f"state too large ({size} > {MAX_STATE_CHARS} chars)")


async def _run(state: Any, questions: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    return await _predict(state, questions, **kwargs)


def _check_redact_kinds(kinds: Optional[List[str]]) -> None:
    if not kinds:
        return
    unknown = [k for k in kinds if k not in PATTERNS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown redaction kind(s) {unknown}; available: {sorted(PATTERNS)}",
        )


@app.get("/redaction/kinds")
def redaction_kinds() -> Dict[str, Any]:
    return {
        "kinds": sorted(PATTERNS),
        "patterns": PATTERNS,
        "router_hook": CONFIG["redact_kinds"],
        "redacted_so_far": REDACTION_HOOK.total_redactions if REDACTION_HOOK else 0,
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health(request: Request) -> Dict[str, Any]:
    """Liveness plus config. Never blocks on the router.

    `Router.loaded` takes the router's internal lock, which inference also holds, so it is
    read through a short-timeout threadpool hop: a busy or stuck router degrades this field
    to `null` instead of hanging the one endpoint a supervisor polls.
    """
    loaded: Optional[List[str]]
    if ROUTER is None:
        loaded = None
    else:
        try:
            loaded = await asyncio.wait_for(run_in_threadpool(lambda: sorted(ROUTER.loaded)), 1.0)
        except Exception:
            loaded = None
    return {
        "status": "ok" if ROUTER is not None else "loading",
        "request_id": _request_id(request),
        "config": CONFIG,
        "loaded_checkpoints": loaded,
        "loading_checkpoints": GATE.loading(),
        "load_timeout_s": GATE.timeout,
        "predict_timeout_s": _predict_timeout(),
        "max_questions": MAX_QUESTIONS,
        "max_state_chars": MAX_STATE_CHARS,
        "max_states_per_batch": MAX_STATES,
        "redacted_so_far": REDACTION_HOOK.total_redactions if REDACTION_HOOK else 0,
    }


@app.get("/models")
def models() -> Dict[str, Any]:
    # `DEFAULT_MODELS` maps a checkpoint name to a `(repo, revision)` pair, where revision is
    # None for the main branch. Keep the two apart instead of flattening the tuple into a list,
    # which put a repo id and a revision side by side under the key "repos".
    repos: Dict[str, Dict[str, Optional[str]]] = {}
    for name, spec in (getattr(laya, "DEFAULT_MODELS", {}) or {}).items():
        repo, revision = spec if isinstance(spec, (tuple, list)) else (spec, None)
        repos[name] = {"repo": repo, "revision": revision}
    return {
        "default": CONFIG["default"],
        "allowed": sorted(KNOWN_MODELS),
        "repos": repos,
    }


@app.get("/qtypes")
def qtypes() -> Dict[str, Any]:
    return {"types": KNOWN_QTYPES}


@app.get("/presets")
def presets() -> Dict[str, Any]:
    return {"groups": GROUPS, "presets": PRESETS}


@app.post("/predict")
async def predict(req: PredictRequest, request: Request) -> Dict[str, Any]:
    _check_limits(req.state, req.questions)
    _check_redact_kinds(req.redact)
    state = req.state
    if req.redact:
        state, counts = redact_state(state, req.redact)
    else:
        counts = {}
    started = time.perf_counter()
    try:
        result = await _run(
            state,
            _plain(req.questions),
            model=req.model,
            task=req.task,
            lang=req.lang,
            lang_guess=req.lang_guess,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"model could not be loaded: {exc}. This machine looks memory-constrained; "
                "close other apps or raise the Windows page file size."
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    result["request_id"] = _request_id(request)
    if counts:
        result["redaction"] = {"applied": True, "counts": counts}
    return result


@app.post("/predict/batch")
async def predict_batch(req: BatchRequest, request: Request) -> Dict[str, Any]:
    for state in req.states:
        _check_limits(state, req.questions)
    questions = _plain(req.questions)
    requests = [{"state": s, "questions": questions} for s in req.states]
    if req.model:
        for r in requests:
            r["model"] = req.model
    if req.lang:
        for r in requests:
            r["lang"] = req.lang
    started = time.perf_counter()
    try:
        router = _router()
        await GATE.ensure_many([d.model for d in router.route_batch(requests)])
        results = await _guarded(
            run_in_threadpool(router.predict_batch, requests),
            _predict_timeout(),
            f"batch inference did not finish within {_predict_timeout():.0f}s on this device",
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"model could not be loaded: {exc}") from exc
    return {
        "count": len(results),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "request_id": _request_id(request),
        "results": results,
    }


@app.post("/structured/questions")
async def structured_questions(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Preview which Laya questions a JSON schema maps to, before spending a forward pass."""
    try:
        return {
            "questions": laya.structured.questions_from_json_schema(schema),
            "fields": [f.name for f in laya.structured.plan_from_json_schema(schema)],
        }
    except laya.structured.SchemaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"{type(exc).__name__}: {exc}") from exc


@app.post("/structured/decide")
async def structured_decide(req: StructuredRequest, request: Request) -> Dict[str, Any]:
    """Answer a state against a JSON schema (or an explicit question set) and project the
    result back onto the schema's own value types."""
    _check_redact_kinds(req.redact)
    state = req.state
    if req.redact:
        state, counts = redact_state(state, req.redact)
    else:
        counts = {}
    questions = _plain(req.questions) if req.questions else None
    if questions:
        _check_limits(state, questions)
    started = time.perf_counter()
    try:
        await _preload_best_effort(state, questions or {}, req.model, req.lang)
        result = await _guarded(
            run_in_threadpool(
                _decide,
                state,
                req.schema_,
                questions,
                req.model,
                req.lang,
            ),
            _predict_timeout(),
            f"structured decision did not finish within {_predict_timeout():.0f}s on this device",
        )
    except laya.structured.SchemaError as exc:
        raise HTTPException(status_code=422, detail=f"SchemaError: {exc}") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"model could not be loaded: {exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    result["request_id"] = _request_id(request)
    if counts:
        result["redaction"] = {"applied": True, "counts": counts}
    return result


def _decide(
    state: Any,
    schema: Optional[Dict[str, Any]],
    questions: Optional[Dict[str, Any]],
    model: Optional[str],
    lang: Optional[str],
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {"return_details": True}
    if model:
        kwargs["model"] = model
    if lang:
        kwargs["lang"] = lang
    detail = laya.structured.decide(
        _router(), state, schema=schema, questions=questions, **kwargs
    )
    payload = {
        "values": detail.values,
        "confidence": detail.confidence,
        "probabilities": detail.probabilities,
        "answers": detail.answers,
        "usage": detail.usage,
        "routing": detail.routing,
    }
    return payload


@app.post("/shortlist")
async def shortlist(req: ShortlistRequest, request: Request) -> Dict[str, Any]:
    """Narrow every choice question to its top-k labels by embedding similarity, then run
    one forward pass over the reduced option set.

    This is the supported way past the per-question option budget: a question with 500
    labels is not rejected, it is shortlisted to k first.
    """
    questions = _plain(req.questions)
    _check_limits(req.state, questions)
    started = time.perf_counter()
    try:
        await GATE.ensure(_shortlist_model(req.state, questions, req.model, req.lang))
        result = await _guarded(
            run_in_threadpool(_shortlist, req.state, questions, req.k, req.model, req.lang),
            _predict_timeout(),
            f"shortlist did not finish within {_predict_timeout():.0f}s on this device",
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"model could not be loaded: {exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    result["request_id"] = _request_id(request)
    return result


async def _preload_best_effort(
    state: Any,
    questions: Dict[str, Any],
    model: Optional[str],
    lang: Optional[str],
) -> None:
    """Deduplicate the load when the checkpoint can be named ahead of time, stay quiet when
    it cannot. `/structured/decide` accepts a schema instead of questions, so the routing
    probe here is only an optimisation -- the timeout still bounds the request either way.
    """
    try:
        name = _shortlist_model(state, questions, model, lang)
    except (KeyError, ValueError):
        return
    await GATE.ensure(name)


def _shortlist_model(
    state: Any,
    questions: Dict[str, Any],
    model: Optional[str],
    lang: Optional[str],
) -> str:
    """Name the checkpoint `/shortlist` will land on, without running any inference."""
    kwargs: Dict[str, Any] = {}
    if model:
        kwargs["model"] = model
    if lang:
        kwargs["lang"] = lang
    return _router().route(state, questions, **kwargs).model


def _shortlist(
    state: Any,
    questions: Dict[str, Any],
    k: int,
    model: Optional[str],
    lang: Optional[str],
) -> Dict[str, Any]:
    router = _router()
    kwargs: Dict[str, Any] = {}
    if model:
        kwargs["model"] = model
    if lang:
        kwargs["lang"] = lang
    decision = router.route(state, questions, **kwargs)
    agent = router.load(decision.model)
    embed_fn = laya.embed_fn_from_agent(agent)
    return laya.predict_shortlist(router, state, questions, embed_fn, k=k, **kwargs)


def _normalize_score_questions(
    questions: Dict[str, Any], threshold: float
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Turn multi-level `score` questions into boundary `noul` questions.

    LayaGuardrail compares `answer.score >= threshold` with one threshold for every
    question type. A score answer is an *expected value* on a 0..N-1 scale, not a
    probability, so with the shipped `harm_severity` question (4 levels) a threshold of
    0.5 fires on any non-zero harm expectation -- a text the model rates "harmless"
    scores 1.0 and trips it. That is a scale mismatch, not a policy decision.

    Rewriting the question as "is it at least level K?" restores a probability scale, so
    the same threshold means the same thing for score and noul questions alike. The
    original graded question is still answered in the response, so nothing is lost.
    """
    normalized: Dict[str, Any] = {}
    rewritten: Dict[str, str] = {}
    for qid, q in questions.items():
        if q.get("type") != "score" or not isinstance(q.get("criteria"), list):
            normalized[qid] = q
            continue
        levels = q["criteria"]
        top = len(levels) - 1
        if top < 1:
            normalized[qid] = q
            continue
        boundary = threshold * top
        index = min(top, max(1, int(boundary) + 1))
        normalized[qid] = {
            "type": "noul",
            "instructions": "Answer yes only if %s is %r or worse on that scale." % (
                q.get("instructions", qid).strip().rstrip("?"),
                levels[index],
            ),
            "criteria": {"true": levels[index], "false": "below level %d" % index},
        }
        rewritten[qid] = "score(0..%d) -> noul at level >= %d" % (top, index)
    return normalized, rewritten


@app.post("/guardrail")
async def guardrail(req: GuardrailRequest, request: Request) -> Dict[str, Any]:
    """Screen a state with LayaGuardrail before it reaches any downstream model.

    `action=annotate` reports the verdict, `filter` substitutes the rejection message, and
    `raise` turns a violation into HTTP 403 so a proxy can enforce it.
    """
    source = _plain(req.questions) if req.questions else laya.guard_questions()
    _check_limits(req.state, source)
    questions, rewritten = (
        _normalize_score_questions(source, req.threshold)
        if req.normalize_scores
        else (source, {})
    )
    started = time.perf_counter()
    try:
        await GATE.ensure(_shortlist_model(req.state, questions, req.model, req.lang))
        verdict = await _guarded(
            run_in_threadpool(_guard, req, questions),
            _predict_timeout(),
            f"guardrail did not finish within {_predict_timeout():.0f}s on this device",
        )
    except laya.LayaGuardrailError as exc:
        return JSONResponse(
            status_code=403,
            content={
                "blocked": True,
                "action": "raise",
                "violations": exc.violations,
                "answers": exc.raw_decision.get("answers", {}),
                "routing": exc.raw_decision.get("routing"),
                "score_questions_rewritten": rewritten,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "request_id": _request_id(request),
            },
            headers={"x-request-id": _request_id(request)},
        )
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"model could not be loaded: {exc}") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    verdict["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    verdict["request_id"] = _request_id(request)
    verdict["score_questions_rewritten"] = rewritten
    return verdict


REJECTION_MESSAGE = "I cannot fulfill this request because it violates safety guidelines."


def _guard(req: GuardrailRequest, questions: Dict[str, Any]) -> Dict[str, Any]:
    """Decide with `action="annotate"` and derive the filter output from that verdict.

    LayaGuardrail's own `filter` path returns the input untouched when it passes, which for
    a string state is indistinguishable from a rejection by type alone. Asking for the
    structured verdict first means `blocked` always comes from the real decision rather
    than from inspecting the return value. `action="raise"` is left to the library, which
    raises LayaGuardrailError carrying the violations.
    """
    kwargs: Dict[str, Any] = {}
    if req.model:
        kwargs["model"] = req.model
    if req.lang:
        kwargs["lang"] = req.lang

    if req.action == "raise":
        rail = laya.LayaGuardrail(
            questions=questions,
            action="raise",
            rejection_message=REJECTION_MESSAGE,
            threshold=req.threshold,
            state_key=req.state_key,
            agent=_router(),
            **kwargs,
        )
        rail.invoke(req.state)
        return {"blocked": False, "action": "raise", "answers": {}, "threshold": req.threshold}

    rail = laya.LayaGuardrail(
        questions=questions,
        action="annotate",
        rejection_message=REJECTION_MESSAGE,
        threshold=req.threshold,
        state_key=req.state_key,
        agent=_router(),
        **kwargs,
    )
    info = rail.invoke(req.state)["guardrails"]
    blocked = not info.get("passed", True)
    verdict: Dict[str, Any] = {
        "blocked": blocked,
        "action": req.action,
        "violations": info.get("violations", {}),
        "answers": info.get("answers", {}),
        "threshold": req.threshold,
    }
    if req.action == "filter":
        if blocked:
            if isinstance(req.state, dict):
                verdict["output"] = {**req.state, "output": REJECTION_MESSAGE}
            else:
                verdict["output"] = REJECTION_MESSAGE
        else:
            verdict["output"] = req.state
    return verdict


@app.exception_handler(StarletteHTTPException)
def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_response(exc.status_code, exc.detail, _request_id(request))


@app.exception_handler(RequestValidationError)
def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Validation failures in the same envelope as every other error.

    `input` is dropped on purpose: FastAPI echoes the offending value, so rejecting a
    5 MB state would return a 5 MB error body and turn a size limit into an amplifier.
    """
    errors = [
        {"loc": list(err.get("loc", ()))[1:], "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return _error_response(422, errors, _request_id(request))


@app.exception_handler(404)
def not_found(request: Request, exc: Any) -> JSONResponse:
    return _error_response(404, "not found: %s" % request.url.path, _request_id(request))


@app.exception_handler(500)
def server_error(request: Request, exc: Any) -> JSONResponse:
    return _error_response(500, "internal error", _request_id(request))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Laya example web app.")
    parser.add_argument("--host", default=os.getenv("LAYA_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("LAYA_PORT", "8000")))
    parser.add_argument("--device", choices=["cpu", "cuda", "mps", "xpu"], default=None)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if args.device:
        CONFIG["device"] = args.device
    if args.reload:
        CONFIG["preload"] = []

    if not args.reload:
        uvicorn.run(app, host=args.host, port=args.port)
        return

    # With --reload uvicorn runs this process as the reloader and the app in a *child* that
    # re-imports `app` from scratch, which rebuilds CONFIG from the environment. Anything set
    # on the CONFIG dict above is therefore invisible to the process that actually serves, so
    # `--device cuda` would silently fall back to auto and `LAYA_PRELOAD` would still preload.
    # Publish the decisions as env vars the child will read instead of mutating CONFIG.
    if args.device:
        os.environ["LAYA_DEVICE"] = args.device
    os.environ["LAYA_PRELOAD"] = ""
    os.environ["LAYA_HOST"] = args.host
    os.environ["LAYA_PORT"] = str(args.port)
    uvicorn.run("app:app", host=args.host, port=args.port, reload=True)


if __name__ == "__main__":
    main()
