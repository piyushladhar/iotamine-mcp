"""Run commands and read/write files inside a VPS — the reliable way for
an AI tool to work on a server (install packages, edit configs, check
services) without driving an SSH session.

Maps to vps.commands in iotamine_backend_django: commands run as root
through qemu-guest-agent on the compute node, detached inside the guest,
so a long install keeps running even if this tool call returns first.
Two things must be true before any of these work, both on the dashboard:
command access is switched on for that server, and the API key (or the
connected app) has "Read, write & run commands" access. The API explains
which one is missing when it isn't.
"""
import time

from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
# Destructive, so MCP clients ask the user before each call: a command or a
# file write can change anything on the server.
RUNS_ON_SERVER = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)
CANCEL = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

TERMINAL = {"succeeded", "failed", "timed_out", "cancelled", "error"}

# Added to every command/file tool's description: what the model must do
# when the server or the key isn't set up for this.
SETUP_HELP = """

If this fails because command access is off for the server, or because this key/app can't run
commands, don't try another way in (SSH, a console, asking for passwords). Stop and give the user
the exact steps from the error message, which include a direct link, for example: open the server
in the Iotamine dashboard, go to the Commands tab, switch on "Allow commands" and confirm; or, for
an app connected through OAuth, reconnect it and choose "Read, write & run commands". Only the
account owner can do this, from the dashboard; you can't do it for them. Offer to retry once
they say it's done."""


def _with_setup_help(fn):
    fn.__doc__ = (fn.__doc__ or "").rstrip() + SETUP_HELP
    return fn
MAX_WAIT_SECONDS = 120
DEFAULT_OUTPUT_CHARS = 20000
MAX_OUTPUT_CHARS = 200000


def _clip(result, max_output_chars):
    """Keeps the end of long output (where errors and results usually are)
    and says how much was left out."""
    if not isinstance(result, dict):
        return result
    output = result.get("output")
    limit = max(1000, min(int(max_output_chars or DEFAULT_OUTPUT_CHARS), MAX_OUTPUT_CHARS))
    if isinstance(output, str) and len(output) > limit:
        result = {**result, "output": output[-limit:], "output_omitted_chars": len(output) - limit}
        result["output_note"] = (f"Only the last {limit} characters are shown. Pass a larger max_output_chars, "
                                 "or redirect the output to a file and read it with read_file.")
    return result


def _wait(client, vps_id, command_id, wait_seconds):
    deadline = time.monotonic() + max(0, min(int(wait_seconds or 0), MAX_WAIT_SECONDS))
    delay = 0.5
    while True:
        result = client.get(f"vps/{vps_id}/commands/{command_id}/")
        if result.get("status") in TERMINAL or time.monotonic() >= deadline:
            return result
        time.sleep(min(delay, max(0.1, deadline - time.monotonic())))
        delay = min(delay * 1.5, 3)


def _with_hint(result):
    if isinstance(result, dict) and result.get("status") not in TERMINAL:
        result = {**result, "next_step": (
            "Still running. Call get_command_result with this command id (wait_seconds up to 120) to follow it; "
            "the command keeps running on the server either way.")}
    return result


def register(mcp, client):
    @mcp.tool(annotations=RUNS_ON_SERVER)
    @_with_setup_help
    def run_command(vps_id: str, command: str, timeout_seconds: int = 600, working_directory: str = None,
                    environment: dict = None, wait_seconds: int = 60, max_output_chars: int = DEFAULT_OUTPUT_CHARS) -> dict:
        """Run a shell command on a VPS as root and return its output and exit code.

        Use this instead of SSH for installing packages, editing configs, checking or
        restarting services, reading logs, and so on. Before running anything that
        changes the server, tell the user exactly what you're about to run.

        - command: run with /bin/sh as a script, so pipes, &&, if/for and multi-line
          scripts all work. stdin is empty, so it must not wait for input: use
          non-interactive flags (apt-get -y, DEBIAN_FRONTEND=noninteractive is already
          set, yum -y, --yes, ...). stdout and stderr come back as one stream.
        - timeout_seconds (1-3600, default 600): the command is killed after this.
        - wait_seconds (0-120, default 60): how long this call waits for it to finish.
          A longer command keeps running; follow it with get_command_result.
        - working_directory: absolute path, default /root. environment: extra
          NAME: value variables (PATH/HOME can't be changed).

        Status: succeeded (exit code 0), failed (non-zero; see exit_code and output),
        timed_out, cancelled, or error (couldn't run, e.g. the server stopped).
        Needs command access switched on for the server and an API key/app with
        "Read, write & run commands" access; the error says which is missing.
        Linux servers only, with iotamine-agent running (it is on Iotamine images)."""
        body = {"command": command, "timeout_seconds": timeout_seconds}
        if working_directory:
            body["working_directory"] = working_directory
        if environment:
            body["environment"] = environment
        started = client.post(f"vps/{vps_id}/commands/", json=body)
        result = _wait(client, vps_id, started["id"], wait_seconds) if wait_seconds else started
        return _clip(_with_hint(result), max_output_chars)

    @mcp.tool(annotations=READ_ONLY)
    @_with_setup_help
    def get_command_result(vps_id: str, command_id: str, wait_seconds: int = 0, output_offset: int = 0,
                           max_output_chars: int = DEFAULT_OUTPUT_CHARS) -> dict:
        """Status, exit code and output of a command started with run_command.

        wait_seconds (0-120): wait up to this long for it to finish first.
        output_offset: return only output after this many characters (pass the
        output_length you already have to get just what's new)."""
        if wait_seconds:
            result = _wait(client, vps_id, command_id, wait_seconds)
            if output_offset and isinstance(result.get("output"), str):
                result = {**result, "output": result["output"][int(output_offset):]}
        else:
            params = {"output_offset": int(output_offset)} if output_offset else None
            result = client.get(f"vps/{vps_id}/commands/{command_id}/", params=params)
        return _clip(_with_hint(result), max_output_chars)

    @mcp.tool(annotations=CANCEL)
    @_with_setup_help
    def cancel_command(vps_id: str, command_id: str) -> dict:
        """Stop a running command (kills it and everything it started)."""
        return client.post(f"vps/{vps_id}/commands/{command_id}/cancel/", json={})

    @mcp.tool(annotations=READ_ONLY)
    @_with_setup_help
    def list_commands(vps_id: str, status: str = None, page: int = 1) -> dict:
        """Command history for a VPS, newest first: who ran each command (dashboard,
        API key or an AI app), status and exit code. status filters, e.g. "running"
        or "failed,error". Also shows whether command access is switched on."""
        params = {"page": page}
        if status:
            params["status"] = status
        return client.get(f"vps/{vps_id}/commands/", params=params)

    @mcp.tool(annotations=READ_ONLY)
    @_with_setup_help
    def read_file(vps_id: str, path: str, max_bytes: int = None) -> dict:
        """Read a file on a VPS (absolute path, up to 1 MB). Text comes back as-is
        (encoding "utf-8"); binary files come back base64 (encoding "base64").
        truncated is true when the file is bigger than what was returned."""
        body = {"path": path}
        if max_bytes:
            body["max_bytes"] = max_bytes
        return client.post(f"vps/{vps_id}/files/read/", json=body)

    @mcp.tool(annotations=RUNS_ON_SERVER)
    @_with_setup_help
    def write_file(vps_id: str, path: str, content: str, mode: str = None, create_dirs: bool = False,
                   content_is_base64: bool = False) -> dict:
        """Create or replace a file on a VPS (absolute path, up to 1 MB). Much more
        reliable than echo/heredoc tricks for config files and scripts. Tell the user
        which file you're writing before you do.

        The file is written to a temporary file and renamed into place, so nothing
        ever sees half a file. Replacing a file keeps its owner and, unless mode is
        given, its permissions; a new file gets mode 644. mode: octal like "600" or
        "755". create_dirs: create missing parent directories.
        content_is_base64: set when content is base64-encoded binary data."""
        body = {"path": path, "create_dirs": create_dirs}
        body["content_base64" if content_is_base64 else "content"] = content
        if mode:
            body["mode"] = mode
        return client.post(f"vps/{vps_id}/files/write/", json=body)
