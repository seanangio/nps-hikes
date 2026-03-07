"""Unit tests for NLQ prompt building and tool definitions."""

from api.nlq.prompt import TOOLS, build_chat_messages, build_system_message


class TestToolDefinitions:
    """Tests for the TOOLS constant."""

    def test_two_tools_defined(self):
        assert len(TOOLS) == 2

    def test_search_trails_tool_exists(self):
        names = [t["function"]["name"] for t in TOOLS]
        assert "search_trails" in names

    def test_search_parks_tool_exists(self):
        names = [t["function"]["name"] for t in TOOLS]
        assert "search_parks" in names

    def test_search_trails_has_expected_params(self):
        trails_tool = next(t for t in TOOLS if t["function"]["name"] == "search_trails")
        props = trails_tool["function"]["parameters"]["properties"]
        expected = {
            "park_code",
            "state",
            "source",
            "hiked",
            "min_length",
            "max_length",
            "trail_type",
            "limit",
        }
        assert set(props.keys()) == expected

    def test_search_parks_has_visited_param(self):
        parks_tool = next(t for t in TOOLS if t["function"]["name"] == "search_parks")
        props = parks_tool["function"]["parameters"]["properties"]
        assert "visited" in props

    def test_no_required_params(self):
        """All parameters should be optional (no required fields)."""
        for tool in TOOLS:
            required = tool["function"]["parameters"].get("required", [])
            assert required == []


class TestBuildSystemMessage:
    """Tests for system message construction."""

    def test_includes_park_lookup(self):
        lookup_text = "- yosemite national park → yose\n- zion national park → zion"
        message = build_system_message(lookup_text)
        assert "yose" in message
        assert "zion" in message

    def test_includes_instructions(self):
        message = build_system_message("- test → test")
        assert "park_code" in message
        assert "4 lowercase letters" in message


class TestBuildChatMessages:
    """Tests for chat message list construction."""

    def test_returns_two_messages(self):
        messages = build_chat_messages("find trails", "system msg")
        assert len(messages) == 2

    def test_system_message_first(self):
        messages = build_chat_messages("find trails", "system msg")
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "system msg"

    def test_user_message_second(self):
        messages = build_chat_messages("find trails in Yosemite", "system msg")
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "find trails in Yosemite"
