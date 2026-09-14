"""Settings dialog field specs (Image tab aspect dropdown)."""

from unittest.mock import MagicMock, patch

from plugin.chatbot.settings_dialog import IMAGE_ASPECT_RATIO_LABELS, get_settings_field_specs


def test_image_default_aspect_has_sidebar_matching_options():
    """Settings Image tab must list the same five aspect labels as the sidebar."""
    with (
        patch("plugin.chatbot.settings_dialog.get_current_endpoint", return_value="https://openrouter.ai/api/v1"),
        patch("plugin.chatbot.settings_dialog.get_config_str", return_value="Square"),
        patch("plugin.chatbot.settings_dialog.get_config_int", return_value=512),
        patch("plugin.chatbot.settings_dialog.get_config_float", return_value=0.7),
        patch("plugin.chatbot.settings_dialog.get_config_bool", return_value=True),
        patch("plugin.chatbot.settings_dialog.get_config", return_value=""),
        patch("plugin.chatbot.settings_dialog.get_api_key_for_endpoint", return_value=""),
        patch("plugin.chatbot.settings_dialog.get_text_model", return_value="m"),
        patch("plugin.chatbot.settings_dialog.get_image_model", return_value="img"),
        patch("plugin.chatbot.settings_dialog._get_module_field_specs", return_value=[]),
    ):
        specs = get_settings_field_specs(MagicMock())

    aspect = next(s for s in specs if s["name"] == "image_default_aspect")
    labels = tuple(o["label"] for o in aspect["options"])
    values = tuple(o["value"] for o in aspect["options"])
    assert labels == IMAGE_ASPECT_RATIO_LABELS
    assert values == IMAGE_ASPECT_RATIO_LABELS
    assert IMAGE_ASPECT_RATIO_LABELS == (
        "Square",
        "Landscape (16:9)",
        "Portrait (9:16)",
        "Landscape (3:2)",
        "Portrait (2:3)",
    )
