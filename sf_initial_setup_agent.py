"""SF Initial Setup Agent — supervisor mode (v0.2.x).

The bootstrap workflow lives in shell/Python scripts under scripts/, run by
run_pipeline.sh. This agent's job is:

  1. Collect inputs from the user.
  2. Resolve an Anthropic API key (prompt + persist if missing).
  3. Invoke the pipeline as a subprocess and stream its output.
  4. On failure, enter REPAIR MODE: hand Claude the failed step's log, give
     it focused tools (read_log, rerun_step, resume_pipeline, read_file,
     write_file, run_sf, run_shell), and let it diagnose + fix + retry.
  5. On success, offer the user an optional follow-up loop with Claude.

This split keeps the LLM out of the happy path (cost, speed, determinism)
and reserves it for the moments that actually need reasoning.
"""
import os, subprocess, json, time, re, getpass, sys
from pathlib import Path
from anthropic import Anthropic, APIStatusError, APIConnectionError, RateLimitError

AGENT_VERSION = "0.2.0"
REPO_ROOT = Path(__file__).resolve().parent
PIPELINE = REPO_ROOT / "run_pipeline.sh"

# Shared env file for all 5GL agents. The agent reads it directly so it works
# even if the current shell hasn't sourced it (or if ~/.zshrc never did).
ENV_FILE = Path.home() / ".5gl-agents-env"

# Set in __main__ once the key has been resolved.
client = None

CONFIG_PATH = Path.home() / ".sf-initial-setup-agent-config.json"

# Set by run_supervisor() before any tool can fire.
PROJECT_ROOT = None

# Substrings we never let the file or shell tools touch, even via a symlink
# rooted in the project directory.
DENY_SUBSTRINGS = (
    "/.sfdx/", "/.ssh/", "/.aws/", "/.anthropic",
    "/.zshrc", "/.bashrc", "/.bash_profile", "/.profile",
    "/.config/gh/", "/.5gl-agents-env",
)

# Bail at 180K input tokens so the next turn's tool result doesn't push us
# past Sonnet 4.6's 200K window.
CONTEXT_TOKEN_SOFT_LIMIT = 180_000


# ---------- api key ----------
_ENV_LINE = re.compile(r'^\s*(?:export\s+)?(\w+)\s*=\s*(.*?)\s*$')


def _read_env_file_var(var_name):
    if not ENV_FILE.exists():
        return None
    try:
        for raw in ENV_FILE.read_text().splitlines():
            line = raw.split("#", 1)[0]
            m = _ENV_LINE.match(line)
            if not m or m.group(1) != var_name:
                continue
            val = m.group(2)
            if len(val) >= 2 and val[0] == val[-1] and val[0] == '"':
                val = val[1:-1]
                val = re.sub(r'\\([\\"`$])', r'\1', val)
            elif len(val) >= 2 and val[0] == val[-1] and val[0] == "'":
                val = val[1:-1]
            return val
    except Exception:
        return None
    return None


def _write_env_file_var(var_name, value):
    lines = []
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text().splitlines():
            stripped = raw.split("#", 1)[0]
            m = _ENV_LINE.match(stripped)
            if m and m.group(1) == var_name:
                continue
            lines.append(raw)
    safe = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    lines.append(f'export {var_name}="{safe}"')
    ENV_FILE.write_text("\n".join(lines) + "\n")
    ENV_FILE.chmod(0o600)


def resolve_api_key():
    key = os.environ.get("FIVEGL_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    key = _read_env_file_var("FIVEGL_ANTHROPIC_API_KEY") or _read_env_file_var("ANTHROPIC_API_KEY")
    if key:
        return key
    print("\nAnthropic API key not found.")
    print(f"It will be saved to {ENV_FILE} as the shared key for all 5GL agents.")
    print("(Get one at https://console.anthropic.com/settings/keys)\n")
    while True:
        key = getpass.getpass("Anthropic API key (input hidden): ").strip()
        if key:
            break
        print("  (required)")
    _write_env_file_var("FIVEGL_ANTHROPIC_API_KEY", key)
    print(f"→ Saved to {ENV_FILE}\n")
    return key


# ---------- config ----------
def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# ---------- startup wizard ----------
def ask(label, default=None, required=True):
    suffix = f" [{default}]" if default else ""
    while True:
        v = input(f"{label}{suffix}: ").strip() or (default or "")
        if v or not required:
            return v
        print("  (required)")


def pick_folder(default=None):
    default_clause = ""
    if default and Path(default).exists():
        default_clause = f' default location POSIX file "{default}"'
    script = f'POSIX path of (choose folder with prompt "Select project parent directory"{default_clause})'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        print("  (picker cancelled — type path instead)")
        return ask("Project parent directory", default)
    return r.stdout.strip().rstrip("/")


def startup_wizard():
    cfg = load_config()
    print("\n" + "=" * 60)
    print(f"  5GL Salesforce Initial Setup Agent  v{AGENT_VERSION}")
    print("=" * 60 + "\n")
    username = ask("Salesforce username (email)", cfg.get("last_username"))
    sandbox = ask("Sandbox? (y/n)", "y" if cfg.get("last_sandbox") else "n").lower().startswith("y")
    alias = ask("Org alias", cfg.get("last_alias"))
    print("\nOpening folder picker...")
    directory = pick_folder(cfg.get("last_directory", str(Path.home())))
    save_config({
        "last_username": username, "last_alias": alias,
        "last_directory": directory, "last_sandbox": sandbox,
    })
    print(f"\n→ Saved for next time: {CONFIG_PATH}\n")
    return {"username": username, "alias": alias,
            "directory": directory, "sandbox": sandbox}


# ---------- pipeline runner ----------
def _pipeline_env(extra=None):
    env = os.environ.copy()
    if extra:
        env.update(extra)
    return env


def exec_pipeline(extra_env=None):
    """Run run_pipeline.sh, stream output to stdout, capture for the agent.
    Returns (returncode, combined_output_str)."""
    proc = subprocess.Popen(
        ["bash", str(PIPELINE)],
        env=_pipeline_env(extra_env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    chunks = []
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        chunks.append(line)
    proc.wait()
    return proc.returncode, "".join(chunks)


def detect_failed_step(output):
    """Parse run_pipeline.sh output for the '❌ FAILED: <name> (exit N)' marker."""
    m = re.search(r'❌ FAILED:\s*(\S+)\s+\(exit\s+(\d+)\)', output)
    if m:
        return m.group(1), int(m.group(2))
    return None, None


# ---------- repair-mode tools ----------
TOOLS = [
    {"name": "read_log",
     "description": "Read a pipeline step's log. step is the script filename, e.g. '05_complete_profiles.py' or '10_retrieve.sh'.",
     "input_schema": {"type": "object", "properties": {
         "step": {"type": "string"}}, "required": ["step"]}},
    {"name": "rerun_step",
     "description": "Re-run exactly one pipeline step. step is the script filename.",
     "input_schema": {"type": "object", "properties": {
         "step": {"type": "string"}}, "required": ["step"]}},
    {"name": "resume_pipeline",
     "description": "Run the pipeline starting from a step (and continuing through the rest). from_step is the script filename.",
     "input_schema": {"type": "object", "properties": {
         "from_step": {"type": "string"}}, "required": ["from_step"]}},
    {"name": "run_sf",
     "description": "Run a Salesforce CLI command directly. Include --json when parsing output.",
     "input_schema": {"type": "object", "properties": {
         "args": {"type": "array", "items": {"type": "string"}},
         "cwd": {"type": "string"}}, "required": ["args"]}},
    {"name": "run_shell",
     "description": "Run a general shell command (10-minute timeout). Refuses paths that touch sensitive locations.",
     "input_schema": {"type": "object", "properties": {
         "cmd": {"type": "string"}, "cwd": {"type": "string"}}, "required": ["cmd"]}},
    {"name": "write_file",
     "description": "Create or overwrite a file. Confined to the project directory.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"}, "content": {"type": "string"}},
         "required": ["path", "content"]}},
    {"name": "read_file",
     "description": "Read a file (truncated to 20KB). Confined to the project directory.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"}}, "required": ["path"]}},
]


def _is_path_safe(p):
    if PROJECT_ROOT is None:
        return False
    try:
        target = Path(p).expanduser().resolve()
    except Exception:
        return False
    s = str(target)
    if any(bad in s for bad in DENY_SUBSTRINGS):
        return False
    root = PROJECT_ROOT.resolve()
    return target == root or root in target.parents


def _shell_looks_dangerous(cmd):
    low = cmd.lower()
    return any(bad.strip("/") in low for bad in DENY_SUBSTRINGS)


def _format_pipeline_result(rc, output):
    tail = output[-15000:]
    return f"exit={rc}\nOUTPUT (tail, last 15KB):\n{tail}"


def run_tool(name, inp):
    try:
        if name == "read_log":
            step = inp["step"]
            log_path = PROJECT_ROOT / "logs" / f"{Path(step).stem}.log"
            if not log_path.exists():
                return f"ERROR: no log at {log_path}"
            return log_path.read_text()[-20000:]
        if name == "rerun_step":
            rc, out = exec_pipeline({"ONLY": inp["step"], "START_FROM": ""})
            return _format_pipeline_result(rc, out)
        if name == "resume_pipeline":
            rc, out = exec_pipeline({"START_FROM": inp["from_step"], "ONLY": ""})
            return _format_pipeline_result(rc, out)
        if name == "run_sf":
            r = subprocess.run(["sf"] + inp["args"], capture_output=True,
                               text=True, cwd=inp.get("cwd"), timeout=3600)
            return f"exit={r.returncode}\nSTDOUT:\n{r.stdout[-15000:]}\nSTDERR:\n{r.stderr[-3000:]}"
        if name == "run_shell":
            cmd = inp["cmd"]
            if _shell_looks_dangerous(cmd):
                return f"ERROR: refusing shell command that references a sensitive path ({cmd!r})"
            r = subprocess.run(cmd, shell=True, capture_output=True,
                               text=True, cwd=inp.get("cwd") or str(PROJECT_ROOT), timeout=600)
            return f"exit={r.returncode}\nSTDOUT:\n{r.stdout[-10000:]}\nSTDERR:\n{r.stderr[-3000:]}"
        if name == "write_file":
            if not _is_path_safe(inp["path"]):
                return f"ERROR: refusing to write outside project directory ({PROJECT_ROOT})"
            p = Path(inp["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(inp["content"])
            return f"wrote {len(inp['content'])} bytes to {p}"
        if name == "read_file":
            if not _is_path_safe(inp["path"]):
                return f"ERROR: refusing to read outside project directory ({PROJECT_ROOT})"
            return Path(inp["path"]).read_text()[:20000]
        return f"ERROR: unknown tool '{name}'"
    except subprocess.TimeoutExpired as e:
        return f"ERROR: command timed out after {e.timeout}s"
    except Exception as e:
        return f"ERROR: {e}"


# ---------- claude loop ----------
SYSTEM = """You are the SF Initial Setup Agent in supervisor mode for 5GL.ai consulting.

The metadata bootstrap workflow is a deterministic pipeline of scripts under
scripts/, run by run_pipeline.sh. You are NOT executing the workflow yourself.
Your job is to react to what the pipeline did:

  - REPAIR MODE: the pipeline failed at a specific step. Read its log,
    diagnose, fix, and re-run (or resume).
  - FOLLOW-UP MODE: the pipeline succeeded and the user wants to ask
    something or make an adjustment.

Available tools:
  - read_log(step) — read a step's log file
  - read_file(path) / write_file(path, content) — project-confined
  - rerun_step(step) — re-execute exactly one step
  - resume_pipeline(from_step) — re-run from a step through the end
  - run_sf(args) — ad-hoc Salesforce CLI command
  - run_shell(cmd) — ad-hoc shell command (cwd defaults to project root)

Rules:
  - The pipeline scripts live in scripts/NN_*.{sh,py}. Step names are filenames.
  - Confirm with the user before destructive operations (deleting files,
    overwriting a manifest with wildcards that would balloon the retrieve, etc.).
  - File tools refuse anything outside the project directory or that touches
    ~/.sfdx, ~/.ssh, dotfiles, the gh config, or the 5GL env file.
  - Prefer minimal, focused fixes over wholesale changes. Edit a manifest
    rather than regenerating it from scratch unless you're sure.
  - When you don't know what's wrong, ask the user — don't guess.
  - When the failure is fixed and the pipeline succeeds, summarize and stop.
"""


def _call_api_with_retry(**kwargs):
    delays = [2, 5, 15, 30, 60]
    last_err = None
    for attempt in range(len(delays) + 1):
        try:
            return client.messages.create(**kwargs)
        except (APIConnectionError, RateLimitError) as e:
            last_err = e
        except APIStatusError as e:
            status = getattr(e, "status_code", None)
            if status is None or status < 500:
                raise
            last_err = e
        if attempt >= len(delays):
            raise last_err
        wait = delays[attempt]
        print(f"  (API error: {type(last_err).__name__} — retrying in {wait}s)")
        time.sleep(wait)


def claude_loop(initial_user_message):
    """Run a Claude conversation until end_turn, then prompt the user, repeat."""
    history = [{"role": "user", "content": initial_user_message}]
    while True:
        while True:
            try:
                resp = _call_api_with_retry(
                    model="claude-sonnet-4-6", max_tokens=4096,
                    system=SYSTEM, tools=TOOLS, messages=history,
                )
            except APIStatusError as e:
                status = getattr(e, "status_code", "?")
                print(f"\nAPI error ({status}): {e}")
                return
            except Exception as e:
                print(f"\nAPI error after retries: {type(e).__name__}: {e}")
                return

            history.append({"role": "assistant", "content": resp.content})
            for b in resp.content:
                if b.type == "text" and b.text.strip():
                    print(f"\nAgent: {b.text}")

            usage = getattr(resp, "usage", None)
            if usage and getattr(usage, "input_tokens", 0) >= CONTEXT_TOKEN_SOFT_LIMIT:
                print(f"\n⚠️  Context at {usage.input_tokens} tokens — stopping before overflow.")
                return

            stop = resp.stop_reason
            if stop == "end_turn":
                break
            if stop == "max_tokens":
                print("\n⚠️  Response hit max_tokens. Stopping turn.")
                break
            if stop == "refusal":
                print("\n⚠️  Model refused. Stopping.")
                return
            if stop == "pause_turn":
                print("\n⚠️  pause_turn. Stopping turn; re-prompt to continue.")
                break

            results = []
            for b in resp.content:
                if b.type == "tool_use":
                    print(f"  → {b.name} {json.dumps(b.input)[:160]}")
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": run_tool(b.name, b.input)})
            if not results:
                print(f"\n⚠️  No tool calls and stop_reason={stop!r}; stopping turn.")
                break
            history.append({"role": "user", "content": results})

        msg = input("\nYou (or Enter to quit): ").strip()
        if not msg:
            return
        history.append({"role": "user", "content": msg})


# ---------- supervisor entrypoint ----------
def run_supervisor(params):
    global PROJECT_ROOT
    PROJECT_ROOT = (Path(params["directory"]).expanduser().resolve()
                    / f"{params['alias']}-metadata")

    pipeline_env = {
        "ALIAS": params["alias"],
        "USERNAME": params["username"],
        "SANDBOX": "1" if params["sandbox"] else "0",
        "PROJECT_PARENT_DIR": str(Path(params["directory"]).expanduser().resolve()),
        "AGENT_VERSION": AGENT_VERSION,
    }
    for k, v in pipeline_env.items():
        os.environ[k] = v

    rc, output = exec_pipeline()

    if rc == 0:
        print("\n→ Pipeline succeeded. Press Enter to exit, or type a follow-up "
              "request for Claude (e.g., 'remove the Reports type from the manifest "
              "and re-retrieve').\n")
        msg = input("You: ").strip()
        if not msg:
            return
        claude_loop(
            f"The metadata bootstrap pipeline completed successfully. The user "
            f"now asks: {msg}\n\n"
            f"Project: {PROJECT_ROOT}\n"
            f"Org alias: {params['alias']}\n"
        )
        return

    failed_step, exit_code = detect_failed_step(output)
    print(f"\n→ Pipeline failed at step '{failed_step}' (exit {exit_code}). "
          f"Engaging repair mode.\n")

    initial = (
        f"The metadata bootstrap pipeline failed.\n\n"
        f"Failed step: {failed_step}\n"
        f"Exit code:   {exit_code}\n"
        f"Project:     {PROJECT_ROOT}\n"
        f"Org alias:   {params['alias']}\n"
        f"Sandbox:     {params['sandbox']}\n\n"
        f"Start by reading the failed step's log via read_log('{failed_step}'). "
        f"Diagnose, propose a fix, and either rerun_step('{failed_step}') or "
        f"resume_pipeline(from_step) once the cause is addressed. If you need "
        f"input from the user, just ask in plain text."
    )
    claude_loop(initial)


if __name__ == "__main__":
    api_key = resolve_api_key()
    # max_retries=5 lets the SDK ride out brief 5xx/429 blips on its own. The
    # _call_api_with_retry() wrapper adds a more patient second layer.
    client = Anthropic(api_key=api_key, max_retries=5)
    params = startup_wizard()
    run_supervisor(params)
