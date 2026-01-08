import os
import json
from typing import List, Optional, Dict, Any
from openai import OpenAI
from emailcred import open_ai_key, user_context

# API configuration
# Option 1 (preferred if set): OpenRouter
OPENROUTER_API_KEY = open_ai_key
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "")  # optional referer
OPENROUTER_SITE_TITLE = os.getenv("OPENROUTER_SITE_TITLE", "")  # optional title
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")

# Option 2: OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Load basic user profile from data_set.json to personalize answers
_USER_PROFILE_TEXT = ""
try:
    ds_path = os.path.join(os.path.dirname(__file__), "data_set.json")
    if os.path.exists(ds_path):
        with open(ds_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Build a compact profile string from common fields
        parts = []
        def add(k):
            v = (data.get(k) or "").strip()
            if v:
                parts.append(f"{k}: {v}")
        for key in [
            "Current Employer",
            "Current Role",
            "Total Experience",
            "Current Annual CTC",
            "Expected Salary (Annual)",
            "Current Location",
            "Preferred Locations",
            "Hometown",
            "Highest Qualification",
            "College/ University",
            "Year of Passing",
            "Skill Set",
            "Notice Period",
            "Reason For Change",
        ]:
            add(key)
        _USER_PROFILE_TEXT = " | ".join(parts)
except Exception:
    _USER_PROFILE_TEXT = ""


def _sanitize(text: str) -> str:
    """Remove framework tokens like <|start|>assistant<|channel|>final<|message|> and trim."""
    try:
        import re
        text = re.sub(r"<\|[^>]*\|>", "", text or "")
    except Exception:
        pass
    return (text or "").strip()


def _get_client_and_model():
    use_openrouter = bool(OPENROUTER_API_KEY)
    if use_openrouter:
        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)
        model = OPENROUTER_MODEL
    elif OPENAI_API_KEY:
        client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
        model = OPENAI_MODEL
    else:
        return None, None, False
    extra_headers = {}
    if use_openrouter:
        if OPENROUTER_SITE_URL:
            extra_headers["HTTP-Referer"] = OPENROUTER_SITE_URL
        if OPENROUTER_SITE_TITLE:
            extra_headers["X-Title"] = OPENROUTER_SITE_TITLE
    return client, model, use_openrouter


def llm_answer(question: str, kind: str, choices: Optional[List[str]] = None) -> str:
    """
    Ask an LLM for an appropriate value for a form question.
    - kind: text | number | email | phone | url | radio | select | textarea
    - choices: when provided (radio/select), model should select one value exactly.

    Returns a plain string answer. For choices, it will try to return exactly
    one of the provided values (case-insensitive match will be normalized).
    """
    question = (question or "").strip()
    kind = (kind or "text").strip().lower()

    

    sys = (
        f"User Context: --- {user_context}\n ---"
        "You are an assistant that fills job application forms realistically and concisely. "
        "Always return only the final answer without explanations."
    )

    if choices:
        choices_text = "\n".join(f"- {c}" for c in choices)
        user = (
            f"Question: {question}\n"
            f"Type: {kind}\n"
            f"Choices (select exactly one):\n{choices_text}\n"
            f"Respond with exactly one of the choices."
        )
    else:
        user = (
            f"Question: {question}\n"
            f"Type: {kind}\n"
            f"Respond with a concise, realistic value only."
        )

    # Fallback helper
    def _fallback() -> str:
        if choices:
            for c in choices:
                if c and c.strip().lower() == "yes":
                    return c
            return choices[0]
        return "NA"

    # Build system prompt with user profile context
    profile_line = f" User Profile: {_USER_PROFILE_TEXT}." if _USER_PROFILE_TEXT else ""
    system_prompt = sys + profile_line

    # Choose client: OpenRouter if key present, else OpenAI
    client = None
    use_openrouter = bool(OPENROUTER_API_KEY)
    try:
        client, model, use_openrouter = _get_client_and_model()
        if client is None:
            return _fallback()

        extra_headers = {}
        if use_openrouter:
            if OPENROUTER_SITE_URL:
                extra_headers["HTTP-Referer"] = OPENROUTER_SITE_URL
            if OPENROUTER_SITE_TITLE:
                extra_headers["X-Title"] = OPENROUTER_SITE_TITLE

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            extra_headers=extra_headers or None,
        )
        content = _sanitize(completion.choices[0].message.content or "")
        if not content:
            return _fallback()
        # Normalize to one of the choices for radio/select
        if choices:
            lc_map = {c.lower(): c for c in choices}
            pick = content.strip().strip('\"\'').lower()
            if pick in lc_map:
                return lc_map[pick]
            for k, v in lc_map.items():
                if pick in k or k in pick:
                    return v
            return choices[0]
        return content
    except Exception as e:
        print(e)
        return _fallback()


def llm_answer_batch(items: List[Dict[str, Any]]) -> List[str]:
    """
    Batch version of llm_answer. Each item is a dict with keys:
      - question: str
      - kind: str (text | number | email | phone | url | radio | select | textarea)
      - choices: Optional[List[str]] (for radio/select)

    Returns a list of strings, same order as items. Falls back per-item when needed.
    """
    # Per-item fallback
    def _fb(it: Dict[str, Any]) -> str:
        ch = it.get("choices") or []
        if ch:
            for c in ch:
                if c and str(c).strip().lower() == "yes":
                    return c
            return ch[0]
        return "NA"

    if not items:
        return []

    # Build messages
    profile_line = f"User Profile: {_USER_PROFILE_TEXT}." if _USER_PROFILE_TEXT else ""
    sys = (
        f"User Context: --- {user_context}\n ---"
        "You are an assistant that fills job application forms realistically and concisely. "
        "Always return only the final answer without explanations. Return JSON only."
    )
    system_prompt = sys + (" " + profile_line if profile_line else "")

    # Compose a single user prompt listing all items, requiring JSON array of answers
    lines = [
        "Answer the following questions strictly as a JSON array of strings, same order as listed.",
        "Do not include any keys or explanations. For radio/select, answer must be exactly one of the provided choices.",
        "Questions:",
    ]
    for idx, it in enumerate(items):
        q = str(it.get("question") or "").strip()
        k = str(it.get("kind") or "text").strip().lower()
        ch = it.get("choices") or []
        lines.append(f"{idx+1}. question={q} | type={k}")
        if ch:
            joined = " | ".join(str(c) for c in ch)
            lines.append(f"   choices=[{joined}]")
    lines.append("Respond with only the JSON array, e.g., [\"A\", \"B\"].")
    user_content = "\n".join(lines)

    try:
        client, model, use_openrouter = _get_client_and_model()
        if client is None:
            return [_fb(it) for it in items]
        extra_headers = {}
        if use_openrouter:
            if OPENROUTER_SITE_URL:
                extra_headers["HTTP-Referer"] = OPENROUTER_SITE_URL
            if OPENROUTER_SITE_TITLE:
                extra_headers["X-Title"] = OPENROUTER_SITE_TITLE
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            extra_headers=extra_headers or None,
        )
        raw = _sanitize(completion.choices[0].message.content or "")
        import json as _json
        answers = []
        try:
            answers = _json.loads(raw)
        except Exception:
            # try to extract JSON array substring
            import re
            m = re.search(r"\[(.*)\]", raw, re.DOTALL)
            if m:
                try:
                    answers = _json.loads("[" + m.group(1) + "]")
                except Exception:
                    answers = []
        if not isinstance(answers, list):
            answers = []
        # Normalize and map choices
        out: List[str] = []
        for i, it in enumerate(items):
            ans = str(answers[i]).strip() if i < len(answers) else ""
            ans = _sanitize(ans)
            ch = it.get("choices") or []
            if ch:
                lc_map = {str(c).lower(): str(c) for c in ch}
                pick = ans.strip().strip('\"\'').lower()
                if pick in lc_map:
                    out.append(lc_map[pick]); continue
                chosen = None
                for k, v in lc_map.items():
                    if pick in k or k in pick:
                        chosen = v; break
                out.append(chosen if chosen else ch[0])
            else:
                out.append(ans if ans else _fb(it))
        return out
    except Exception as e:
        print(e)
        return [_fb(it) for it in items]
