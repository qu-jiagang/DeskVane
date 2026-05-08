from __future__ import annotations

from deskvane.core.tasks import TaskManager


def test_task_manager_pause_resume_use_task_specific_hooks() -> None:
    events: list[str] = []
    manager = TaskManager()
    manager.register(
        "translator",
        lambda: events.append("start"),
        lambda: events.append("stop"),
        lambda: events.append("pause"),
        lambda: events.append("resume"),
    )

    manager.start("translator")
    manager.pause("translator")
    manager.resume("translator")
    manager.stop("translator")

    assert events == ["start", "pause", "resume", "stop"]
    assert manager.state("translator") == "stopped"


def test_task_manager_resume_stopped_task_falls_back_to_start() -> None:
    events: list[str] = []
    manager = TaskManager()
    manager.register("subconverter", lambda: events.append("start"), lambda: events.append("stop"))

    manager.resume("subconverter")
    manager.pause("subconverter")
    manager.resume("subconverter")

    assert events == ["start", "stop", "start"]
    assert manager.state("subconverter") == "running"


def test_task_manager_pause_and_resume_all_preserve_order() -> None:
    events: list[str] = []
    manager = TaskManager()
    manager.register(
        "tray",
        lambda: events.append("tray.start"),
        lambda: events.append("tray.stop"),
        lambda: events.append("tray.pause"),
        lambda: events.append("tray.resume"),
    )
    manager.register(
        "translator",
        lambda: events.append("translator.start"),
        lambda: events.append("translator.stop"),
        lambda: events.append("translator.pause"),
        lambda: events.append("translator.resume"),
    )

    manager.start_all()
    manager.pause_all()
    manager.resume_all()
    manager.stop_all()

    assert events == [
        "tray.start",
        "translator.start",
        "translator.pause",
        "tray.pause",
        "tray.resume",
        "translator.resume",
        "translator.stop",
        "tray.stop",
    ]
