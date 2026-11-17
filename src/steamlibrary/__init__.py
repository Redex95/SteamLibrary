from pathlib import Path
import runpy


def main() -> None:
    """Run the Flask application from a source checkout."""
    candidates = (Path(__file__).resolve().parents[2] / "app.py", Path.cwd() / "app.py")
    app_script = next((path for path in candidates if path.is_file()), None)
    if app_script is None:
        raise SystemExit("Cannot find app.py. Run this command from the Steam Library Explorer project folder.")
    runpy.run_path(str(app_script), run_name="__main__")
