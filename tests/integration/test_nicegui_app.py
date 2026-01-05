"""Integration tests for NiceGUI application using user fixture."""

from nicegui import ui
from nicegui.testing import User


class TestNiceGUIApp:
    """Integration tests for NiceGUI application using User fixture.

    These tests use NiceGUI's User fixture which provides fast, lightweight
    simulation of user interactions without requiring a browser or Selenium.
    """

    async def test_main_page_loads(self, user: User):
        """Test that the main page loads and displays correctly."""
        await user.open("/")
        await user.should_see("DraftPilot")
        await user.should_see("Counter: 0")

    async def test_counter_increment(self, user: User):
        """Test that the counter increment button works."""
        await user.open("/")
        await user.should_see("Counter: 0")

        # Find and click the Increment button
        user.find("Increment").click()
        await user.should_see("Counter: 1")

        # Click again
        user.find("Increment").click()
        await user.should_see("Counter: 2")

    async def test_counter_decrement(self, user: User):
        """Test that the counter decrement button works."""
        await user.open("/")

        # First increment a few times
        user.find("Increment").click()
        user.find("Increment").click()
        await user.should_see("Counter: 2")

        # Then decrement
        user.find("Decrement").click()
        await user.should_see("Counter: 1")

        user.find("Decrement").click()
        await user.should_see("Counter: 0")

    async def test_counter_interaction(self, user: User):
        """Test complex counter interactions."""
        await user.open("/")
        await user.should_see("Counter: 0")

        # Increment multiple times
        for _ in range(5):
            user.find("Increment").click()

        await user.should_see("Counter: 5")

        # Decrement
        user.find("Decrement").click()
        await user.should_see("Counter: 4")

    async def test_page_elements_exist(self, user: User):
        """Test that all expected page elements are present."""
        await user.open("/")

        # Check for main label
        await user.should_see("DraftPilot")

        # Check for buttons using find (without clicking)
        user.find("Increment")
        user.find("Decrement")

        # Check for counter display
        await user.should_see("Counter:")

    async def test_find_by_kind(self, user: User):
        """Test finding elements by type/kind."""
        await user.open("/")

        # Find buttons by type
        increment_button = user.find(kind=ui.button, content="Increment")
        assert increment_button is not None

        # Find label by type
        await user.should_see(kind=ui.label, content="DraftPilot")

    async def test_counter_negative_values(self, user: User):
        """Test that counter can go negative."""
        await user.open("/")
        await user.should_see("Counter: 0")

        # Decrement from 0
        user.find("Decrement").click()
        await user.should_see("Counter: -1")

        # Decrement again
        user.find("Decrement").click()
        await user.should_see("Counter: -2")

    async def test_should_not_see(self, user: User):
        """Test that should_not_see works correctly."""
        await user.open("/")

        # Should not see a value that doesn't exist
        await user.should_not_see("Counter: 999")

        # After incrementing, should not see the old value
        user.find("Increment").click()
        await user.should_see("Counter: 1")
        await user.should_not_see("Counter: 0")

