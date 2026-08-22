# WriterAgent - Native UNO Test for Hamburger Menu
from plugin.testing_runner import native_test


@native_test
def test_popup_menu_image_and_command(ctx):
    """Verify PopupMenu supports setItemImage with 3 args and setCommand."""
    smgr = ctx.getServiceManager()
    popup = smgr.createInstanceWithContext("com.sun.star.awt.PopupMenu", ctx)
    assert popup is not None, "PopupMenu service creation failed"

    popup.insertItem(1, "Test Item", 0, 0)
    assert popup.getItemCount() == 1

    # Verify command binding
    popup.setCommand(1, "org.extension.writeragent:scripting.run_python_dialog")
    assert popup.getCommand(1) == "org.extension.writeragent:scripting.run_python_dialog"

    # Verify graphic loading and 3-arg setItemImage
    from plugin.chatbot.hamburger_menu import _load_graphic

    graphic = _load_graphic(ctx, "python_32.png")
    assert graphic is not None, "Failed to load python_32.png graphic"
    popup.setItemImage(1, graphic, False)
