"""Light sanity checks for the command model."""
from algent_backend.commands import CommandDispatcher
from algent_backend.commands.models import Command


def test_dispatcher_handles_registered_command():
    dispatcher = CommandDispatcher()
    dispatcher.register("ping", lambda cmd: {"echo": cmd.payload})
    result = dispatcher.dispatch(Command(name="ping", payload={"a": 1}))
    assert result == {"echo": {"a": 1}}


def test_dispatcher_handles_unknown_command():
    dispatcher = CommandDispatcher()
    result = dispatcher.dispatch(Command(name="missing"))
    assert result["status"] == "unhandled"
