import flet as ft
import logfire

from draftpilot.core import telemetry

telemetry.setup(ui=True)

logfire.info("Telemetry setup complete")


def main(page: ft.Page):
    counter = ft.Text("0", size=50, data=0)

    # Create a counter metric
    counter_increments = logfire.metric_counter("counter_increments")

    def increment_click(e):
        counter.data += 1
        counter_increments.add(1)
        counter.value = str(counter.data)
        counter.update()

    page.floating_action_button = ft.FloatingActionButton(
        icon=ft.Icons.ADD, on_click=increment_click
    )
    page.add(
        ft.SafeArea(
            ft.Container(
                counter,
                alignment=ft.alignment.center,
            ),
            expand=True,
        )
    )


ft.app(main)
