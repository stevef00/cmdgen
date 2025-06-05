#!/usr/bin/env python3
import os
import sys
import json
import time
import signal
import openai
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory, InMemoryHistory
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import typer

# Initialize rich console and typer app
console = Console()
app = typer.Typer()

def is_terminal() -> bool:
    """Check if stdout is a terminal."""
    return sys.stdout.isatty()

class Settings(BaseModel):
    """Application settings."""
    api_key_path: Path = Field(default=Path.home() / '.cmdgen_apikey')
    history_file: Path = Field(default=Path.home() / '.cmdgen_history')
    max_history: int = Field(default=1000)
    model: str = Field(default='gpt-4o')
    developer_prompt: str = Field(
        default='Output a shell command to satisfy the user prompt. '
                'Do not include any markdown in the output, just the command. '
                'Assume bash shell unless the user specifies otherwise.'
    )

class APIResponse(BaseModel):
    """OpenAI API response model."""
    output: list[dict]
    usage: Optional[dict] = None

def load_settings() -> Settings:
    """Load application settings from environment or defaults."""
    load_dotenv()  # Load .env file if it exists
    return Settings(
        api_key_path=os.getenv('API_KEY_PATH', str(Path.home() / '.cmdgen_apikey')),
        history_file=os.getenv('HISTORY_FILE', str(Path.home() / '.cmdgen_history')),
        max_history=int(os.getenv('MAX_HISTORY', '1000')),
        model=os.getenv('MODEL', 'gpt-4o'),
        developer_prompt=os.getenv('DEVELOPER_PROMPT', Settings().developer_prompt)
    )

def check_api_key_permissions(api_key_path: Path) -> None:
    """Check if API key file has secure permissions (0600)."""
    try:
        stat = api_key_path.stat()
        mode = stat.st_mode & 0o777  # Get last 3 octal digits
        if mode != 0o600:
            console.print(
                f"[yellow]Warning: API key file has insecure permissions {oct(mode)[-3:]} "
                f"(should be 600). Run: chmod 600 {api_key_path}[/yellow]"
            )
    except FileNotFoundError:
        pass  # File doesn't exist, will be handled by load_api_key

def load_api_key(settings: Settings) -> str:
    """Load and validate the OpenAI API key."""
    if not settings.api_key_path.exists():
        console.print(f"[red]Error: API key file not found at {settings.api_key_path}[/red]")
        sys.exit(1)

    check_api_key_permissions(settings.api_key_path)
    return settings.api_key_path.read_text().strip()

def setup_prompt_session(settings: Settings, persistent: bool = True) -> PromptSession:
    """Set up the prompt session with history."""
    settings.history_file.parent.mkdir(parents=True, exist_ok=True)
    if persistent:
        return PromptSession(history=FileHistory(str(settings.history_file)))

    # Load history for in-memory use only and filter out non-prompt lines.
    hist = InMemoryHistory()
    if settings.history_file.exists():
        for line in settings.history_file.read_text().splitlines():
            if line.startswith("+"):
                hist.append_string(line[1:])
    return PromptSession(history=hist)

def trim_history(settings: Settings) -> None:
    """Keep only the last ``settings.max_history`` lines in the history file."""
    try:
        lines = settings.history_file.read_text().splitlines()
    except FileNotFoundError:
        return

    if len(lines) > settings.max_history:
        # Write back only the most recent entries so the file doesn't grow
        settings.history_file.write_text(
            "\n".join(lines[-settings.max_history:]) + "\n"
        )

def make_api_request(settings: Settings, api_key: str, prompt: object) -> APIResponse:
    """Make the OpenAI API request and return the response."""
    try:
        client = openai.OpenAI(api_key=api_key)
        if isinstance(prompt, list):
            messages = [{'role': 'system', 'content': settings.developer_prompt}] + prompt
        else:
            messages = [
                {'role': 'developer', 'content': settings.developer_prompt},
                {'role': 'user', 'content': str(prompt)}
            ]
        resp = client.responses.create(
            model=settings.model,
            input=messages
        )
        return APIResponse(**resp.model_dump())
    except Exception as e:
        console.print(f"[red]Error: Failed to contact OpenAI: {e}[/red]")
        sys.exit(1)

def _parse_usage(usage: dict) -> Dict[str, int]:
    """Normalize usage fields from the API into prompt/completion/cached/total."""
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    cached_tokens = usage.get("cached_tokens")
    total_tokens = usage.get("total_tokens")

    if prompt_tokens is None:
        prompt_tokens = usage.get("input_tokens", usage.get("tokens", 0))

    if completion_tokens is None:
        completion_tokens = usage.get("output_tokens", 0)

    if cached_tokens is None:
        cached_tokens = usage.get("input_tokens_details", {}).get("cached_tokens", 0)

    if total_tokens is None:
        total_tokens = usage.get("tokens", 0)

    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "cached_tokens": int(cached_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }


def _format_stats(usage: Dict[str, int]) -> str:
    return (
        f"tokens: prompt={usage['prompt_tokens']}  "
        f"completion={usage['completion_tokens']}  "
        f"cached={usage['cached_tokens']}  total={usage['total_tokens']}"
    )


def display_stats(usage: Optional[dict], level: str = "basic") -> None:
    """Display token usage statistics."""
    if not usage:
        console.print("[yellow]Token statistics not available in API response.[/yellow]")
        return

    if level == "debug":
        console.print(json.dumps(usage, indent=2))
        return

    parsed = _parse_usage(usage)
    console.print(_format_stats(parsed))

def copy_to_tmux_buffer(text: str) -> None:
    """Copy text to tmux paste buffer."""
    try:
        # Use subprocess.run to pipe the text to tmux load-buffer
        process = subprocess.run(
            ['tmux', 'load-buffer', '-'],
            input=text.encode(),
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]Warning: Failed to copy to tmux buffer: {e}[/yellow]")
    except FileNotFoundError:
        console.print("[yellow]Warning: tmux command not found[/yellow]")

def copy_to_x11_clipboard(text: str) -> None:
    """Copy text to X11 clipboard using xsel."""
    try:
        # Use subprocess.run to pipe the text to xsel
        process = subprocess.run(
            ['xsel', '--input', '--clipboard'],
            input=text.encode(),
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]Warning: Failed to copy to X11 clipboard: {e}[/yellow]")
    except FileNotFoundError:
        console.print("[yellow]Warning: xsel command not found[/yellow]")

def update_stats(cumulative: Dict[str, int], usage: Dict[str, int]) -> None:
    """Update cumulative statistics."""
    parsed = _parse_usage(usage)
    for k, v in parsed.items():
        cumulative[k] = cumulative.get(k, 0) + v

def run_repl(
    settings: Settings,
    api_key: str,
    stats_level: Optional[str],
    quiet: bool,
    tmux: bool = False,
    xsel: bool = False,
) -> None:
    """Run the interactive REPL loop."""
    session = setup_prompt_session(settings, persistent=False)
    transcript: List[Dict[str, str]] = []
    cumulative: Dict[str, int] = {}

    in_request = False
    last_sigint = 0.0

    def handle_sigint(signum, frame):
        nonlocal last_sigint, in_request
        now = time.time()
        if in_request:
            raise KeyboardInterrupt
        if now - last_sigint < 1:
            raise typer.Exit()
        last_sigint = now
        console.print("\nPress Ctrl-C again to exit")

    signal.signal(signal.SIGINT, handle_sigint)

    while True:
        try:
            text = session.prompt("prompt> ").strip()
        except EOFError:
            break

        if text in {"exit", "quit"}:
            break
        if not text:
            continue

        if text.startswith(":"):
            cmd = text[1:]
            if cmd == "stats":
                display_stats(cumulative, stats_level or "basic")
            elif cmd == "undo":
                if len(transcript) >= 2:
                    transcript.pop()
                    transcript.pop()
                else:
                    console.print("[yellow]Nothing to undo[/yellow]")
            elif cmd == "help":
                console.print(":stats :undo :help exit quit")
            else:
                console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
            continue

        transcript.append({"role": "user", "content": text})
        try:
            in_request = True
            if not quiet:
                with console.status("[bold green]Waiting for OpenAI response..."):
                    result = make_api_request(settings, api_key, transcript)
            else:
                result = make_api_request(settings, api_key, transcript)
        finally:
            in_request = False

        command = result.output[0]["content"][0]["text"]
        transcript.append({"role": "assistant", "content": command})

        if tmux:
            copy_to_tmux_buffer(command)
        if xsel:
            copy_to_x11_clipboard(command)

        if quiet:
            print(command)
        else:
            console.print(Panel(command, title="Generated Command", border_style="green"))

        if stats_level and result.usage:
            display_stats(result.usage, stats_level)
            update_stats(cumulative, result.usage)

    if transcript:
        summary_prompt = transcript + [
            {
                "role": "user",
                "content": "Summarize the prompt that produced the final command. One line, no markdown."
            }
        ]
        summary_resp = make_api_request(settings, api_key, summary_prompt)
        summary = summary_resp.output[0]["content"][0]["text"].splitlines()[0]
        if stats_level and summary_resp.usage:
            display_stats(summary_resp.usage, stats_level)
            update_stats(cumulative, summary_resp.usage)
        with open(settings.history_file, "a") as f:
            f.write(f"\n# {datetime.now().isoformat()}\n+{summary}\n")
        trim_history(settings)

    if stats_level and cumulative:
        console.print("summary: " + _format_stats(_parse_usage(cumulative)))

@app.command()
def main(
    stats: Optional[str] = typer.Option(
        None,
        "--stats",
        "-s",
        help="Show token usage statistics (basic or debug)",
    ),
    tmux: bool = typer.Option(
        False,
        "--tmux",
        "-t",
        help="Copy command to tmux paste buffer"
    ),
    xsel: bool = typer.Option(
        False,
        "--xsel",
        "-x",
        help="Copy command to X11 clipboard"
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Start a REPL loop (cannot be used with --prompt/-p)"
    ),
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt",
        "-p",
        help="One-shot generation (cannot be used with --interactive)"
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Minimal output (no borders, no progress)",
    )
):
    """Ask for a shell command from OpenAI based on a prompt."""
    # Enable quiet mode when stdout is not a terminal or --quiet is specified
    quiet = quiet or not is_terminal()

    if interactive and prompt is not None:
        console.print("error: --interactive and --prompt are mutually exclusive", style="red")
        raise typer.Exit(code=1)

    if prompt is None and not interactive:
        interactive = True

    settings = load_settings()
    api_key = load_api_key(settings)
    session = setup_prompt_session(settings)

    try:
        if interactive:
            run_repl(
                settings,
                api_key,
                stats,
                quiet,
                tmux,
                xsel,
            )
            return

        prompt = prompt.strip()
        session.history.append_string(prompt)
        trim_history(settings)

        if not prompt:
            console.print("[red]Error: Empty prompt[/red]", file=sys.stderr)
            raise typer.Exit(1)

        if not quiet:
            with console.status("[bold green]Waiting for OpenAI response..."):
                result = make_api_request(settings, api_key, prompt)
        else:
            result = make_api_request(settings, api_key, prompt)

        command = result.output[0]['content'][0]['text']

        if tmux:
            copy_to_tmux_buffer(command)

        if xsel:
            copy_to_x11_clipboard(command)

        if quiet:
            print(command)
        else:
            console.print(Panel(command, title="Generated Command", border_style="green"))

        if stats and result.usage and not quiet:
            display_stats(result.usage, stats)

    except KeyboardInterrupt:
        if not quiet:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        if not quiet:
            console.print(f"[red]Error: {e}[/red]")
        else:
            print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(1)

if __name__ == '__main__':
    app()
