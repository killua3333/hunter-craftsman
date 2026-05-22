from hunter.main import _is_make_command


def test_is_make_command_exact():
    assert _is_make_command("/make")
    assert _is_make_command("  /MAKE  ")


def test_is_make_command_rejects_variants():
    assert not _is_make_command("/make now")
    assert not _is_make_command("帮我制作")
    assert not _is_make_command("/maker")
