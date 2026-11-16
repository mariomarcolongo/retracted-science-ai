"""Minimal OpenRouter client (Python standard library only), used by every script that calls a model.

- API key: environment variable OPENROUTER_API_KEY, or the file ~/.config/retracted-science-ai/openrouter.key
  (outside the repository). The key is never printed, logged or written anywhere.
- Every request is pinned to one provider endpoint, with fallbacks off and required parameters enforced (D50).
- Errors are classified from the HTTP status and from error objects inside 200 responses: out of credit (402) and
  authentication errors stop the run (StopRun); rate limits (429) raise RateLimited (with Retry-After if given), so
  the caller can pause that model only; transient errors (network, 408, 5xx) are retried here and only here, 4
  attempts in all; any other error raises CallFailed at once (not retried: a rejected request will be rejected again).
  An error inside a 200 response with a numeric code written as text ("503") is read as that code; one with no
  usable code is treated as transient. A connection lost while the reply is being read is transient (D66).
- With log=..., every attempt is logged at the HTTP boundary: the exact body before sending, the full response or the
  redacted error after.
- usage_fields() returns only the allow-listed fields of data/costs/README.md (D55).
"""
import datetime, http.client, json, os, re, time, urllib.error, urllib.request, uuid

BASE = "https://openrouter.ai/api/v1/"
KEY_FILE = os.path.expanduser("~/.config/retracted-science-ai/openrouter.key")


class StopRun(Exception):
    """Out of credit, bad key or account problem: stop everything; the request is not counted as missing."""


class RateLimited(Exception):
    """429 from OpenRouter or the provider: pause this model, do not count the request as missing."""


class CallFailed(Exception):
    """Request rejected by the provider (4xx other than 401/402/403/429)."""


class Unavailable(CallFailed):
    """The pinned endpoint could not be reached: still failing after 4 attempts (network, timeout, 408/5xx,
    malformed response), or OpenRouter reports no endpoint for it. Not the model's answer: callers pause and retry
    later instead of recording a missing answer."""


def _key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k and os.path.exists(KEY_FILE):
        k = open(KEY_FILE).read().strip()
    if not k:
        raise StopRun("no API key: set OPENROUTER_API_KEY or create " + KEY_FILE)
    return k


SECRET = re.compile(r"(sk-or-[A-Za-z0-9_-]+|Bearer\s+\S+)")


def redact(s):
    return SECRET.sub("[redacted]", str(s))


TRANSIENT = {408, 500, 502, 503, 504, 520, 522, 524, 529}


def _classify(code, msg, retry_after=None):
    """Map an HTTP status or an in-body error code to an exception, or None if the error is transient."""
    if code == 402:
        return StopRun("out of credit or key limit reached (402): " + msg)
    if code in (401, 403):
        return StopRun(f"authentication or permission error ({code}): " + msg)
    if code == 429:
        e = RateLimited(msg)
        e.retry_after = retry_after
        return e
    if code in TRANSIENT:
        return None
    if code == 404 and "no endpoints" in (msg or "").lower():
        return Unavailable(f"no endpoint available ({code}): " + msg)
    return CallFailed(f"request rejected ({code}): " + msg)


def _code(value):
    """An in-body error code as an int, or None if there is no usable code ("503" -> 503)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _post(path, body, timeout=600, log=None):
    """POST with the only retry layer of the project: transient errors are retried, 4 attempts in all.
    log(record) is called before every attempt (the exact body sent, without headers) and after it (the full
    response, or the redacted error and whether it is retried). A request record without a matching response
    record means the request may have reached the provider (uncertain)."""
    data = json.dumps(body).encode()
    key = _key()  # Resolve credentials before recording a request that cannot be sent.
    last = None
    for attempt in range(1, 5):
        uid = uuid.uuid4().hex
        if log:
            log({"uid": uid, "kind": "request", "utc": _now(), "attempt": attempt, "path": path, "body": body})
        req = urllib.request.Request(BASE + path, data=data, method="POST", headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            "User-Agent": "research-script", "X-Title": "research-script"})
        t0 = time.time()
        err = None
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            secs = round(time.time() - t0, 2)
            out = json.loads(raw)
            if isinstance(out, dict) and out.get("error"):
                e = out["error"]
                code = e.get("code") if isinstance(e, dict) else None
                msg = redact(e)[:1000]
                if log:
                    log({"uid": uid, "kind": "response", "utc": _now(), "http_status": 200, "seconds": secs,
                         "body": json.loads(redact(json.dumps(out)))})
                code = _code(code)
                err = None if code is None else _classify(code, "error in a 200 response: " + msg)
                if err is None:
                    last = "error in a 200 response: " + msg
            else:
                if log:
                    log({"uid": uid, "kind": "response", "utc": _now(), "http_status": 200, "seconds": secs,
                         "body": out})
                return out, secs
        except urllib.error.HTTPError as e:
            try:
                body_text = e.read().decode(errors="replace")
            except (http.client.HTTPException, OSError, ValueError):
                body_text = "(error body could not be read)"
            msg = redact(body_text)[:1000]
            ra = e.headers.get("Retry-After") if e.headers else None
            err = _classify(e.code, msg, float(ra) if ra and ra.replace(".", "", 1).isdigit() else None)
            last = f"HTTP {e.code}: {msg}"
            if log:
                log({"uid": uid, "kind": "error", "utc": _now(), "http_status": e.code, "error": msg,
                     "retried": err is None and attempt < 4})
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError, ValueError,
                OSError) as e:  # HTTPException: the connection was lost while the reply was read (IncompleteRead)
            last = redact(e)[:1000]
            if log:
                log({"uid": uid, "kind": "error", "utc": _now(), "http_status": None, "error": last,
                     "retried": attempt < 4})
        if err is not None:
            raise err
        if attempt < 4:
            time.sleep(5 * attempt)
    raise Unavailable("failed after 4 attempts: " + str(last))


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def _provider(provider):
    return {"only": [provider], "allow_fallbacks": False, "require_parameters": True}


def chat(model, provider, messages, tools=None, max_tokens=16000, response_format=None, tool_choice=None, log=None,
         temperature=None, top_p=None):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "provider": _provider(provider)}
    if temperature is not None:
        body["temperature"] = temperature
    if top_p is not None:
        body["top_p"] = top_p
    if tools:
        body["tools"] = tools
    if tool_choice:
        body["tool_choice"] = tool_choice
    if response_format:
        body["response_format"] = response_format
    return _post("chat/completions", body, log=log)


def responses(model, provider, input_items, tools=None, max_output_tokens=16000, tool_choice=None, log=None):
    body = {"model": model, "input": input_items, "max_output_tokens": max_output_tokens,
            "provider": _provider(provider)}
    if tools:
        body["tools"] = tools
    if tool_choice:
        body["tool_choice"] = tool_choice
    return _post("responses", body, log=log)


def usage_fields(resp, api):
    """Allow-listed usage and identity fields (data/costs/README.md). Missing values stay None (unknown)."""
    u = resp.get("usage") or {}
    if api == "responses":
        it, ot = u.get("input_tokens"), u.get("output_tokens")
        rt = (u.get("output_tokens_details") or {}).get("reasoning_tokens")
        ct = (u.get("input_tokens_details") or {}).get("cached_tokens")
        stop = resp.get("status")
    else:
        it, ot = u.get("prompt_tokens"), u.get("completion_tokens")
        rt = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
        ct = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
        ch = (resp.get("choices") or [{}])[0]
        stop = ch.get("finish_reason")
    return {"model_returned": resp.get("model"), "provider": resp.get("provider"), "response_id": resp.get("id"),
            "input_tokens": it, "output_tokens": ot, "reasoning_tokens": rt, "cached_tokens": ct,
            "cost_usd": u.get("cost"), "stop_reason": stop}
