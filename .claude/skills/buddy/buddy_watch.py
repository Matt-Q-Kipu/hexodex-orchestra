#!/usr/bin/env python3
"""
Buddy Watch — a live Textual viewer for your coding companion.

Run in a separate terminal pane alongside Claude Code:
    python3 .claude/skills/buddy/buddy_watch.py

The app watches .buddy_state.json for changes and live-updates
the buddy card with animation and a scrolling reaction log.

Press q or ctrl+c to quit.
"""

import json
import os
import sys
from pathlib import Path

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Static, RichLog, Footer
    from textual.containers import Vertical
    from textual.reactive import reactive
except ImportError:
    print("buddy_watch requires Textual: pip3 install textual")
    sys.exit(1)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("buddy_watch requires watchdog: pip3 install watchdog")
    sys.exit(1)

BUDDY_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BUDDY_DIR)

from buddy import (
    load_state,
    render_buddy_card_rich,
    render_ascii,
    HAS_RICH,
)

BUDDY_FILE = os.path.join(BUDDY_DIR, ".buddy_state.json")


class BuddyCard(Static):
    """Renders the Rich buddy card with animation frame cycling."""

    frame = reactive(0)

    def __init__(self, buddy_state=None, **kwargs):
        super().__init__(**kwargs)
        self.buddy_state = buddy_state

    def render(self):
        if not self.buddy_state or not HAS_RICH:
            from rich.text import Text
            return Text("  No buddy hatched yet. Run /buddy first.", style="dim")
        return render_buddy_card_rich(self.buddy_state, frame=self.frame)

    def watch_frame(self, _old, _new):
        self.refresh()


class StateFileHandler(FileSystemEventHandler):
    """Watchdog handler that notifies the Textual app on state file changes."""

    def __init__(self, app):
        self.app = app
        self._last_mtime = 0

    def on_modified(self, event):
        if not event.src_path.endswith(".buddy_state.json"):
            return
        try:
            mtime = os.path.getmtime(event.src_path)
        except OSError:
            return
        if mtime == self._last_mtime:
            return
        self._last_mtime = mtime
        self.app.call_from_thread(self.app.reload_state)


class BuddyWatch(App):
    """Live buddy viewer with animation and reaction log."""

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }
    #card-container {
        height: auto;
        max-height: 80%;
        margin: 1 2;
    }
    #reaction-log {
        height: 1fr;
        min-height: 5;
        margin: 0 2 1 2;
        border: round $accent;
        background: $surface-darken-1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.buddy_state = None
        self._observer = None
        self._prev_reaction = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            BuddyCard(id="buddy-card"),
            id="card-container",
        )
        yield RichLog(id="reaction-log", wrap=True, highlight=True, markup=True)
        yield Footer()

    def on_mount(self):
        self._load_initial_state()
        self.set_interval(1.5, self._cycle_frame)
        self._start_watcher()

    def _load_initial_state(self):
        self.buddy_state = load_state()
        card = self.query_one("#buddy-card", BuddyCard)
        card.buddy_state = self.buddy_state
        card.refresh()
        if self.buddy_state:
            self._prev_reaction = self.buddy_state.get("last_reaction")
            log = self.query_one("#reaction-log", RichLog)
            name = self.buddy_state.get("name", "Buddy")
            log.write(f"[dim]watching {name}...[/dim]")

    def reload_state(self):
        old_state = self.buddy_state
        self.buddy_state = load_state()
        card = self.query_one("#buddy-card", BuddyCard)
        card.buddy_state = self.buddy_state
        card.refresh()

        if not self.buddy_state:
            return

        new_reaction = self.buddy_state.get("last_reaction")
        if new_reaction and new_reaction != self._prev_reaction:
            name = self.buddy_state.get("name", "Buddy")
            log = self.query_one("#reaction-log", RichLog)
            log.write(f"[bold]{name}:[/bold] [italic]{new_reaction}[/italic]")
            self._prev_reaction = new_reaction

        old_happiness = old_state.get("happiness", 0) if old_state else 0
        new_happiness = self.buddy_state.get("happiness", 0)
        if old_state and new_happiness != old_happiness:
            delta = new_happiness - old_happiness
            sign = "+" if delta > 0 else ""
            log = self.query_one("#reaction-log", RichLog)
            log.write(f"[dim]  mood {sign}{delta} → {new_happiness}[/dim]")

    def _cycle_frame(self):
        if not self.buddy_state:
            return
        card = self.query_one("#buddy-card", BuddyCard)
        card.frame = (card.frame + 1) % 3

    def _start_watcher(self):
        handler = StateFileHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, BUDDY_DIR, recursive=False)
        self._observer.daemon = True
        self._observer.start()

    def on_unmount(self):
        if self._observer:
            self._observer.stop()


def main():
    app = BuddyWatch()
    app.run()


if __name__ == "__main__":
    main()
