from pathlib import Path
import unittest


import re
CARD = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "wiser"
    / "frontend"
    / "wiser-schedule-card.js"
)
CONST = Path(__file__).resolve().parents[1] / "custom_components" / "wiser" / "const.py"
WEBSOCKETS = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "wiser"
    / "websockets.py"
)


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
            'const $t="1.5.6"' in card_source,
            "schedule card should advertise version 1.5.6",
        )
        self.assertTrue(
            '"version": "1.5.6"' in const_source,
            "registered Lovelace module version should match the card version",
        )

    def test_delete_confirmation_uses_current_home_assistant_dialog_footer(self):
        card_source = CARD.read_text()

        self.assertTrue(
            'header-title=${Vt("wiser.headings.delete_schedule")}' in card_source,
            "delete dialog should use the current Home Assistant title attribute",
        )
        self.assertTrue(
            '<ha-dialog-footer slot="footer">' in card_source,
            "delete dialog should put its controls in the dialog footer",
        )
        self.assertTrue(
            'slot="primaryAction"' in card_source,
            "delete dialog should expose its confirmation control as the primary action",
        )
        self.assertTrue(
            'slot="secondaryAction"' in card_source,
            "delete dialog should expose its cancellation control as the secondary action",
        )
        self.assertTrue(
            'data-dialog="close"' in card_source,
            "delete dialog actions should use the current Home Assistant close API",
        )

    def test_delete_websocket_reconciles_ambiguous_hub_errors(self):
        websocket_source = WEBSOCKETS.read_text()

        self.assertTrue(
            "from aioWiserHeatAPI.exceptions import WiserScheduleError"
            in websocket_source,
            "delete websocket should identify schedule transport errors",
        )
        self.assertTrue(
            "except WiserScheduleError as ex:" in websocket_source,
            "delete websocket should reconcile an ambiguous schedule transport error",
        )
        self.assertTrue(
            "await d.async_refresh()" in websocket_source,
            "delete websocket should refresh hub state after a transport error",
        )
        self.assertTrue(
            "if d.wiserhub.schedules.get_by_id(schedule_type_enum, schedule_id):"
            in websocket_source,
            "delete websocket should report an error only when the schedule remains",
        )

    def test_successful_delete_notifies_parent_to_return_to_overview(self):
        card_source = CARD.read_text()

        self.assertTrue(
            'new CustomEvent("schedule-deleted",{bubbles:!0,composed:!0})'
            in card_source,
            "successful deletion should emit an event across card boundaries",
        )
        self.assertTrue(
            "@schedule-deleted=${this._scheduleDeleted}" in card_source,
            "parent card should listen for the standard delete completion event",
        )
        self.assertTrue(
            "_scheduleDeleted(){this._schedule_id=0,this._schedule_type=\"\",this._view=Et.Overview}"
            in card_source,
            "parent card should clear the deleted selection before returning to overview",
        )

    def test_delete_confirmation_explains_delayed_ui_update(self):
        card_source = CARD.read_text()

        self.assertTrue(
            "Note : UI can take 5-10 seconds to reflect change" in card_source,
            "delete dialog should set expectations for the hub response delay",
        )

    def test_schedule_name_forms_use_current_home_assistant_input(self):
        card_source = CARD.read_text()
        inputs = re.findall(
            r"<ha-input\s+class=\"schedule-name\"(?P<body>.*?)</ha-input>",
            card_source,
            re.DOTALL,
        )

        self.assertEqual(len(inputs), 2)
        self.assertNotIn("<ha-textfield", card_source)
        for input_body in inputs:
            self.assertIn("auto-validate", input_body)
            self.assertIn("required", input_body)
            self.assertIn(
                "validation-message=${Vt(\"wiser.common.name_required\")}",
                input_body,
            )
            self.assertIn("@input=${this._valueChanged}", input_body)

        self.assertIn(".configValue=${\"Name\"}", inputs[0])
        self.assertIn("value=${this._schedule.Name}", inputs[1])
        self.assertIn(".configValue=${\"Name\"}", inputs[1])
        self.assertIn("@input=${this._valueChanged}", card_source)

if __name__ == "__main__":
    unittest.main()
