# Logging in Python — from zero to useful

_A learning note for someone who has never used the `logging` library._

## 1. Why not just use `print()`?

`print()` is fine for quick checks. But in a real app it has problems:

- You can't turn it off. To hide it you must delete the line.
- Every print looks the same. You can't tell "just info" from "something broke".
- No timestamp, no file name, no line number — you don't know *where* it came from.
- It always goes to the screen. You can't easily send it to a file instead.

`logging` fixes all of this. Think of it as **print with a volume knob and labels.**

## 2. The 5 levels (this is the core idea)

Every log message has a **level** = how serious it is. Low to high:

| Level | Use it for | Example |
|-------|-----------|---------|
| `DEBUG` | tiny details, only useful while fixing bugs | "loop index = 42" |
| `INFO` | normal events, things going right | "Loaded 4998 rows" |
| `WARNING` | something odd, but we handled it | "Fixed 3 negative values" |
| `ERROR` | something failed | "Could not read file" |
| `CRITICAL` | app is basically dead | "Database gone" |

Order: `DEBUG < INFO < WARNING < ERROR < CRITICAL`

## 3. The "volume knob" — this is what *level* means

You set **one line**: the minimum level you care about right now.

```python
logging.basicConfig(level=logging.WARNING)
```

This says: **"Only show me WARNING and above. Hide DEBUG and INFO."**

So the level is a filter. Same code, different knob:

- Knob at `DEBUG` → you see everything (noisy, for debugging).
- Knob at `WARNING` → you see only warnings and errors (quiet, for production).

You don't delete log lines to quiet down. You just **turn the knob**. That's the whole point.

## 4. Your question: can I just use `getLogger(__name__)` without setting a level?

Yes, you can write this and it works:

```python
import logging
logger = logging.getLogger(__name__)

logger.warning("something odd happened")
```

But here's the catch. `getLogger(__name__)` only **creates** the logger. It does **not** decide where messages go or what the knob is set to.

- If **nobody** in the whole program ever called `basicConfig(...)`, Python uses a hidden default: it shows `WARNING` and above, and hides `INFO`/`DEBUG`. So your `INFO` lines silently disappear and you think logging is "not working".
- The moment **someone** (usually your `main` / entry script) calls `logging.basicConfig(level=...)`, the knob is set for everyone.

**The rule of thumb (very important):**

- **Library / helper files** (like your `cleaning.py`, `validation.py`): only do `logger = logging.getLogger(__name__)` and log messages. **Never** call `basicConfig` here. These files should not decide the volume for the whole app.
- **The entry point** (your `main`, a script, or a test setup): calls `basicConfig(level=...)` **once**. This one place sets the knob.

Why? Because a helper file doesn't know if it's running in production (quiet) or while you debug (noisy). Only the app that *uses* it knows. So the app decides.

`__name__` just means "use this file's name as the logger's name" — so later your logs can show *which file* they came from. Free traceability.

## 5. Basic → Advanced, step by step

**Level 1 — absolute basic**

```python
import logging
logging.basicConfig(level=logging.INFO)

logging.info("hello")     # uses the default "root" logger
```

**Level 2 — named logger (what you should do)**

```python
import logging
logger = logging.getLogger(__name__)   # one per file, top of file

logger.info("Loaded data")
```

**Level 3 — set the knob once, in the entry point only**

```python
# in main.py / your script
logging.basicConfig(level=logging.INFO)   # ONE place decides volume
```

**Level 4 — nicer format (timestamp + level + file)**

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
# output: 2026-08-28 10:00:00 | WARNING | mental_health.data.cleaning | Fixed 3 rows
```

**Level 5 — the `%s` trick (why not f-string in logging)**

```python
logger.info("Fixed %s rows", count)     # do this in logging
logger.info(f"Fixed {count} rows")      # avoid this in logging
```

- f-string builds the text **immediately**, even if the message is hidden by the knob → wasted work.
- `%s` builds the text **only if** the message actually prints → no waste.

Everywhere *else* in normal code, f-strings are better. This `%s` rule is **only** for `logger.xxx(...)` lines.

## 6. The one-paragraph summary

`logging` is `print` with a volume knob (the **level**) and labels. Each file makes its own logger with `getLogger(__name__)` and just logs. The **entry point** sets the knob once with `basicConfig(level=...)`. Helper files never set the knob. Inside `logger.xxx()`, use `%s` not f-strings so hidden messages cost nothing.
