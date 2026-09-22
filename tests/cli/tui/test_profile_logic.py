import pytest

from ankinote.cli.tui.profile_logic import add_profile, remove_profile, rename_profile
from ankinote.settings import ProviderProfile


class TestAddProfile:
    def test_adds_profile_with_first_model_option(self):
        providers = {}
        profile = add_profile(
            providers,
            name="OpenAI 2",
            vendor="OpenAI",
            base_url="https://api.openai.com/v1",
            model_options=["gpt-4o", "gpt-4o-mini"],
        )
        assert providers["OpenAI 2"] is profile
        assert profile.model == "gpt-4o"
        assert profile.vendor == "OpenAI"
        assert profile.base_url == "https://api.openai.com/v1"

    def test_no_model_options_leaves_model_blank(self):
        providers = {}
        profile = add_profile(
            providers,
            name="Custom",
            vendor="Custom / Other",
            base_url="",
            model_options=[],
        )
        assert profile.model == ""

    def test_duplicate_name_raises(self):
        providers = {"OpenAI": ProviderProfile(vendor="OpenAI")}
        with pytest.raises(ValueError, match="already exists"):
            add_profile(
                providers,
                name="OpenAI",
                vendor="OpenAI",
                base_url="",
                model_options=[],
            )


class TestRemoveProfile:
    def test_removes_inactive_profile_keeps_active(self):
        providers = {
            "OpenAI": ProviderProfile(vendor="OpenAI"),
            "Anthropic": ProviderProfile(vendor="Anthropic"),
        }
        active = remove_profile(providers, active="OpenAI", name="Anthropic")
        assert active == "OpenAI"
        assert list(providers) == ["OpenAI"]

    def test_removes_active_profile_falls_back_to_remaining(self):
        providers = {
            "OpenAI": ProviderProfile(vendor="OpenAI"),
            "Anthropic": ProviderProfile(vendor="Anthropic"),
        }
        active = remove_profile(providers, active="OpenAI", name="OpenAI")
        assert active == "Anthropic"
        assert list(providers) == ["Anthropic"]

    def test_refuses_to_remove_last_profile(self):
        providers = {"OpenAI": ProviderProfile(vendor="OpenAI")}
        with pytest.raises(ValueError, match="last remaining profile"):
            remove_profile(providers, active="OpenAI", name="OpenAI")
        assert list(providers) == ["OpenAI"]


class TestRenameProfile:
    def test_renames_and_updates_active(self):
        providers = {"OpenAI": ProviderProfile(vendor="OpenAI")}
        active = rename_profile(
            providers, active="OpenAI", old_name="OpenAI", new_name="Work"
        )
        assert active == "Work"
        assert list(providers) == ["Work"]

    def test_renames_inactive_profile_keeps_active(self):
        providers = {
            "OpenAI": ProviderProfile(vendor="OpenAI"),
            "Anthropic": ProviderProfile(vendor="Anthropic"),
        }
        active = rename_profile(
            providers, active="OpenAI", old_name="Anthropic", new_name="Personal"
        )
        assert active == "OpenAI"
        assert list(providers) == ["OpenAI", "Personal"]

    def test_blank_name_raises(self):
        providers = {"OpenAI": ProviderProfile(vendor="OpenAI")}
        with pytest.raises(ValueError, match="must not be empty"):
            rename_profile(providers, active="OpenAI", old_name="OpenAI", new_name="  ")

    def test_collision_raises(self):
        providers = {
            "OpenAI": ProviderProfile(vendor="OpenAI"),
            "Anthropic": ProviderProfile(vendor="Anthropic"),
        }
        with pytest.raises(ValueError, match="already exists"):
            rename_profile(
                providers, active="OpenAI", old_name="OpenAI", new_name="Anthropic"
            )
