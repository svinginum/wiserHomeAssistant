from pathlib import Path
import unittest


CARD = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "wiser"
    / "frontend"
    / "wiser-schedule-card.js"
)
CONST = Path(__file__).resolve().parents[1] / "custom_components" / "wiser" / "const.py"


class ScheduleCardHideHotWaterScheduleTest(unittest.TestCase):
    def test_schedule_card_filters_hot_water_schedule_when_configured(self):
        card_source = CARD.read_text()

        self.assertTrue(
            "hide_hw_schedule" in card_source,
            "schedule card should read the hide_hw_schedule config option",
        )
        self.assertTrue(
            "filter(e=>1e3!=e.Id)" in card_source,
            "schedule card should remove the hot water schedule when configured",
        )

    def test_schedule_card_editor_exposes_hide_hot_water_schedule_option(self):
        card_source = CARD.read_text()

        self.assertTrue(
            "get _hide_hw_schedule()" in card_source,
            "card editor should expose the hide_hw_schedule getter",
        )
        self.assertTrue(
            "Hide Hot Water Schedule" in card_source,
            "card editor should show the hot water schedule toggle",
        )
        self.assertTrue(
            'configValue=${"hide_hw_schedule"}' in card_source,
            "card editor should write the hide_hw_schedule config value",
        )

    def test_registered_schedule_card_resource_version_matches_card_version(self):
        card_source = CARD.read_text()
        const_source = CONST.read_text()

        self.assertTrue(
            'const $t="1.5.1"' in card_source,
            "schedule card should advertise version 1.5.1",
        )
        self.assertTrue(
            '"version": "1.5.1"' in const_source,
            "registered Lovelace module version should match the card version",
        )


if __name__ == "__main__":
    unittest.main()
