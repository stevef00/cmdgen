#!/usr/bin/env python3
import os
import sys
import json
import requests
import subprocess
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
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
    api_url: str = Field(default='https://api.openai.com/v1/responses')
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
        api_url=os.getenv('API_URL', 'https://api.openai.com/v1/responses'),
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

def setup_prompt_session(settings: Settings) -> PromptSession:
    """Set up the prompt session with history."""
    settings.history_file.parent.mkdir(parents=True, exist_ok=True)
    return PromptSession(history=FileHistory(str(settings.history_file)))

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

def make_api_request(settings: Settings, api_key: str, prompt: str) -> APIResponse:
    """Make the OpenAI API request and return the response."""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    data = {
        'model': settings.model,
        'input': [
            {'role': 'developer', 'content': settings.developer_prompt},
            {'role': 'user', 'content': prompt}
        ]
    }

    try:
        resp = requests.post(settings.api_url, headers=headers, data=json.dumps(data))
        resp.raise_for_status()
        return APIResponse(**resp.json())
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Error: Failed to contact OpenAI: {e}[/red]")
        sys.exit(1)

def display_stats(usage: Optional[dict]) -> None:
    """Display token usage statistics."""
    if not usage:
        console.print("[yellow]Token statistics not available in API response.[/yellow]")
        return

    table = Table(title="Token Usage")
    table.add_column("Type", style="cyan")
    table.add_column("Count", style="green")

    for key, value in usage.items():
        if value is not None:
            table.add_row(key.replace('_', ' ').title(), str(value))

    console.print(table)

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

@app.command()
def main(
    stats: bool = typer.Option(
        False,
        "--stats",
        "-s",
        help="Show token usage statistics"
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
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Provide prompt directly (bypasses terminal input)"
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

    settings = load_settings()
    api_key = load_api_key(settings)
    session = setup_prompt_session(settings)

    try:
        # Get prompt either from command line or terminal
        if prompt is None:
            prompt = session.prompt("prompt> ").strip()
        else:
            prompt = prompt.strip()
            # Add to history even when provided via command line
            session.history.append_string(prompt)

        # Trim history after each entry regardless of how the prompt was provided
        trim_history(settings)

        if not prompt:
            console.print("[red]Error: Empty prompt[/red]", file=sys.stderr)
            sys.exit(1)

        if not quiet:
            with console.status("[bold green]Waiting for OpenAI response..."):
                result = make_api_request(settings, api_key, prompt)
        else:
            result = make_api_request(settings, api_key, prompt)

        command = result.output[0]['content'][0]['text']

        # Copy to tmux buffer if requested
        if tmux:
            copy_to_tmux_buffer(command)

        # Copy to X11 clipboard if requested
        if xsel:
            copy_to_x11_clipboard(command)

        # Display the command
        if quiet:
            print(command)
        else:
            console.print(Panel(command,
                              title="Generated Command",
                              border_style="green"))

        # Display stats only if --stats flag is used and not in quiet mode
        if stats and result.usage and not quiet:
            display_stats(result.usage)

    except KeyboardInterrupt:
        if not quiet:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        if not quiet:
            console.print(f"[red]Error: {e}[/red]")
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    app()
