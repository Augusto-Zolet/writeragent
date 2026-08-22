# WriterAgent - Native UNO Test for Hamburger Menu
from plugin.testing_runner import native_test


@native_test
def test_popup_menu_methods(ctx):
    smgr = ctx.getServiceManager()
    popup = smgr.createInstanceWithContext("com.sun.star.awt.PopupMenu", ctx)
    print("ALL POPUP METHODS:")
    for attr in sorted(dir(popup)):
        if not attr.startswith("_"):
            print(f"  {attr}")

    # Let's test inserting item and setting image / graphic / command
    popup.insertItem(1, "Test Item", 0, 0)
    print("Has setItemGraphic:", hasattr(popup, "setItemGraphic"))
    print("Has setItemImage:", hasattr(popup, "setItemImage"))
    print("Has setCommand:", hasattr(popup, "setCommand"))

    from plugin.chatbot.hamburger_menu import _load_graphic
    g = _load_graphic(ctx, "python_32.png")
    print("Loaded python_32.png graphic:", g)

    if hasattr(popup, "setItemGraphic") and g is not None:
        try:
            popup.setItemGraphic(1, g)
            print("setItemGraphic succeeded!")
        except Exception as e:
            print("setItemGraphic failed:", e)

    if hasattr(popup, "setItemImage") and g is not None:
        try:
            popup.setItemImage(1, g, False)
            print("setItemImage(1, g, False) succeeded!")
        except Exception as e:
            print("setItemImage(1, g, False) failed:", e)
