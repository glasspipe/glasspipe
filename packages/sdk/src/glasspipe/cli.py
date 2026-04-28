"""Click-based CLI entrypoint."""
import threading
import time
import webbrowser

import click


@click.group()
def cli():
    pass


@cli.command()
def dashboard():
    """Start the GlassPipe dashboard at http://localhost:3000."""
    try:
        from glasspipe._dashboard import app
    except ImportError:
        raise click.ClickException(
            "Flask is not installed. Run: pip install 'glasspipe[dashboard]'"
        )

    url = "http://localhost:3000"
    click.echo(f"GlassPipe dashboard running at {url}")
    click.echo("Press Ctrl+C to stop.")

    def _open():
        time.sleep(1.0)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()
    app.run(host="127.0.0.1", port=3000, debug=False, use_reloader=False)
