# Command Generator

A command-line tool that uses OpenAI's API to generate shell commands
based on natural language prompts. The tool provides a convenient
way to get shell commands without having to remember exact syntax
or consult documentation.

## Features

- Natural language to shell command conversion
- Command history management
- Multiple output options:
  - Copy to tmux buffer
  - Copy to X11 clipboard
  - Direct command line output
- Token usage statistics
- Quiet mode for scripting
- Direct prompt input for automation

## Installation

1. Clone the repository:
```bash
git clone https://github.com/stevef00/cmdgen.git
cd cmdgen
```

2. Install the required Python packages:
```bash
pip install -r requirements.txt
```

3. Create an API key file:
```bash
echo "your-openai-api-key" > ~/.cmdgen_apikey
chmod 600 ~/.cmdgen_apikey
```

## Usage

### Basic Usage

```bash
./cmdgen.py
```

This will start an interactive prompt where you can enter your
request in natural language.

### Command Line Options

- `-s, --stats`: Show token usage statistics
- `-t, --tmux`: Copy command to tmux paste buffer
- `-x, --xsel`: Copy command to X11 clipboard
- `-p, --prompt TEXT`: Provide prompt directly (bypasses terminal input)
- `-q, --quiet`: Minimal output (no borders, no progress)

### Examples

1. Interactive mode with stats:
```bash
./cmdgen.py --stats
```

2. Direct prompt with tmux buffer:
```bash
./cmdgen.py --prompt "list all processes" --tmux
```

3. Quiet mode for scripting:
```bash
./cmdgen.py --quiet --prompt "find all pdf files"
```

4. Copy to X11 clipboard:
```bash
./cmdgen.py --xsel --prompt "show disk usage"
```

5. Use in a script:
```bash
command=$(./cmdgen.py -q -p "list processes")
echo "Generated command: $command"
```

6. Pipe to another command:
```bash
./cmdgen.py -q -p "find files" | xargs -I {} sh -c "{}"
```

### Environment Variables

The following environment variables can be set to customize the tool's behavior:

- `API_KEY_PATH`: Path to the API key file (default: `~/.cmdgen_apikey`)
- `HISTORY_FILE`: Path to the history file (default: `~/.cmdgen_history`)
- `MAX_HISTORY`: Maximum number of history entries (default: `1000`)
- `MODEL`: OpenAI model to use (default: `gpt-4o`)
- `API_URL`: OpenAI API URL (default: `https://api.openai.com/v1/responses`)
- `DEVELOPER_PROMPT`: Custom developer prompt

### History

The tool maintains a history of your prompts in `~/.cmdgen_history`.
You can use the up/down arrow keys to cycle through previous prompts
when in interactive mode.

## Dependencies

- Python 3.6+
- rich
- prompt_toolkit
- pydantic
- python-dotenv
- requests
- typer
- xsel (for X11 clipboard support)
- tmux (for tmux buffer support)

## License

Public Domain
