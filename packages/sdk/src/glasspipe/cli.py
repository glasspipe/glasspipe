"""Click-based CLI entrypoint."""
import threading
import time
import webbrowser

import click


@click.group()
@click.version_option(package_name="glasspipe")
def cli():
    """GlassPipe — the flight recorder for AI agents."""


@cli.command()
@click.option("--port", "-p", default=3000, show_default=True, help="Port to listen on.")
@click.option("--no-browser", is_flag=True, help="Don't open the dashboard in a browser.")
def dashboard(port, no_browser):
    """Start the local GlassPipe dashboard."""
    from glasspipe._dashboard import app

    url = f"http://localhost:{port}"
    click.echo(f"GlassPipe dashboard running at {url}")
    click.echo("Press Ctrl+C to stop.")

    if not no_browser:
        def _open():
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    try:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    except OSError as exc:
        if "Address already in use" in str(exc) or getattr(exc, "errno", None) == 48:
            raise click.ClickException(
                f"Port {port} is already in use. "
                f"Try: glasspipe dashboard --port {port + 1}"
            )
        raise


@cli.command()
def demo():
    """Seed a few realistic sample traces so the dashboard has data to show."""
    from glasspipe._demo import seed_demo_traces

    click.echo("Seeding sample traces…")
    count = seed_demo_traces()
    click.echo(f"✔ {count} sample runs recorded (research agent ×2 versions, "
               "support agent ok + error).")
    click.echo("Now run: glasspipe dashboard")
