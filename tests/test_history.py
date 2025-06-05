import sys
import pathlib
TEST_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR / "stubs"))
sys.path.insert(0, str(TEST_DIR.parent))
import cmdgen

def test_trim_history_truncates(tmp_path):
    history_file = tmp_path / "history"
    lines = [f"cmd{i}" for i in range(5)]
    history_file.write_text("\n".join(lines) + "\n")
    settings = cmdgen.Settings(history_file=history_file, max_history=3)
    cmdgen.trim_history(settings)
    assert history_file.read_text().splitlines() == lines[-3:]


def test_trim_history_no_change(tmp_path):
    history_file = tmp_path / "history"
    lines = [f"cmd{i}" for i in range(3)]
    history_file.write_text("\n".join(lines) + "\n")
    settings = cmdgen.Settings(history_file=history_file, max_history=5)
    cmdgen.trim_history(settings)
    assert history_file.read_text().splitlines() == lines
